---
name: llm-engine-benchmarking
description: Measure TTFT, prefill tok/s, decode tok/s and prefix-cache reuse of a local or remote OpenAI-compatible LLM engine (llama.cpp, colibri, vLLM, ollama) with a stdlib-only client and no tokenizer. Use when a self-hosted model "feels slow" and nobody has numbers, when a long system prompt takes minutes and you need the seconds-per-1k-tokens curve, when deciding whether prompt caching / KV reuse actually works on a server, when sizing prompts to exact token counts without the model's tokenizer installed, when an agent framework's prompt (system + tool schemas) must be token-budgeted engine-exactly without paying a slow prefill to count it, or when a benchmark must be written as predictions first and scored afterwards.
---

# Benchmarking an OpenAI-compatible LLM engine

Three numbers make a slow local model legible: fixed overhead per request,
marginal prefill seconds per 1k tokens, and decode tokens per second. This
skill produces them from the client side with `urllib` only, plus a
drift-immune test for prefix/KV reuse. Reference implementation:
`nuc/bench.py` (+ `nuc/tests/test_bench.py`, 13 offline tests).

## When to use (triggers)

- A self-hosted model answers short prompts fine but agent turns with big
  system prompts take minutes — you need the TTFT-vs-tokens curve.
- Deciding whether a server's "prefix cache"/"KV slots" feature does anything
  for your workload.
- Sizing prompts to N tokens on a machine where `tokenizers`/`transformers`
  are not installed (or must not be installed).
- Any measurement that a house rule wants banked as predictions-then-results.

Do not use for throughput under concurrency (this is single-client latency)
or for quality evaluation.

## Steps

1. **Write predictions first**, one table row per metric with a range and a
   basis (`nuc/predictions-e1.md` is the shape). A prediction "misses" when
   the measured value falls outside the range. If a smoke run changes your
   mind, add a dated amendment section — never edit the original rows.
2. **Read the server, not the docs.** Find how it reports `usage`
   (`prompt_tokens` is your tokenizer), any queue-wait header
   (colibri: `x-colibri-queue-wait-ms` — subtract it), and what its
   "cache" statistic actually counts (colibri's `cache_hit%` is the expert
   cache, not KV). Check the engine's request path for a per-request KV
   reset (`kv_len = 0`) before believing any prefix-reuse claim.
3. **Guard forbidden endpoints in code.** Put the ports you must never hit
   in a `FORBIDDEN_PORTS` set checked by `check_base_url()`; test it.
4. **Size prompts without a tokenizer.** Generate seeded word-salad prose,
   send it with `max_tokens=1`, read `usage.prompt_tokens`, and refit
   `tokens = a + b·chars` from every observation (two points fix the
   template overhead `a`). Report the achieved token count, never the target.
5. **Warm the engine once and discard it.** An idle engine's first request
   pays page-cache/expert-cache refill (63 s vs 16 s for the same 114-token
   prompt on pgain-nuc). Record it as `engine_cold_start_s`; it is not TTFT.
6. **Per size, three or four requests, one prompt:**
   `cold` (fresh prefix, `max_tokens=1`) → TTFT;
   `repeat` (identical, `max_tokens=1`);
   `fresh` (different seed, same size, `max_tokens=1`);
   `decode` (identical, `max_tokens=D`) → decode tok/s =
   `(completion_tokens − 1) / (t_decode − t_repeat)`.
   The prefix-reuse signal is `repeat/fresh`, not `repeat/cold` — the latter
   is confounded by engine warm-up drift.
   The differencing estimate's relative error is `prefill_jitter /
   decode_window`; it collapses once prefill ≫ decode window (a ±1.7 % drift
   between two 770 s prefills produced a 3.2× wrong decode rate on pgain-nuc).
   At sizes where `D / decode_rate < ~10 × prefill_jitter`, measure decode
   INSIDE one streaming request instead: `(C − 1) / (last_chunk −
   first_chunk)`, and record per-chunk timestamps so flush batching is
   visible. Calibrate the two methods once against each other behind a short
   prefill with a long window (256 tokens): if the server emits one chunk per
   token (colibri does — 256 chunks for 256 tokens), streaming is exact and
   wins everywhere; the 30 % method disagreement at 1k on pgain-nuc resolved
   AGAINST differencing (its 3.14/3.69 figures were drift-biased low).
7. **Make the model keep talking.** A prompt ending in "reply OK" yields one
   token then EOS and decode is unmeasurable. Ask for "OK, then a very long
   story": `max_tokens=1` still returns the same first token.
8. **Cut off and extrapolate explicitly.** If the previous size's TTFT
   exceeds the cutoff (mission rule: 5 min), skip the next size and fill it
   from a least-squares line over measured points, flagged `EXTRAPOLATED`
   in the table with the fit equation in the note column.
9. **Budget big prompts locally; calibrate small.** When counting a large
   prompt via `usage.prompt_tokens` would itself cost minutes of prefill:
   copy the model's own `tokenizer.json` off the server, count with HF
   `tokenizers` locally, and reproduce the server's render pipeline exactly —
   import any adapter/proxy module verbatim (copy the file, `importlib` it;
   never re-implement) and replicate the chat template byte-for-byte from
   the server source. Calibrate with SMALL probes through `/v1/completions`
   (raw string in, `max_tokens=1`) — it bypasses the template so any
   local-vs-engine delta is pure tokenizer. Bisect a mismatch by probing
   substrings (halves, then frame boundaries, then single boundaries);
   pin every engine measurement in an offline test so the emulator can't
   drift. Attribute tokens per component by differential rendering (render
   with/without each part) so parts sum to the total exactly.
   Reference: `nuc/prompt_budget.py` (+12 offline tests).
10. **Report the model, not just the rows:** `TTFT ≈ a + b·tokens` with
   `1/b` as the marginal prefill rate and `a` as fixed overhead. Write the
   table to the machine's log directory and to the round file, then score
   every prediction hit/miss.

## Pitfalls
- **RSS as the engine's size.** An engine parked at its cgroup
  `memory.max` has already pushed part of itself to swap (4.2 GB of a
  36 GB Qwen3.6 worker); `ps` RSS under-states it and any co-location or
  cache-cap plan built on it is wrong. Read `memory.current`,
  `memory.swap.current` and `VmSwap` (see `colocated-model-lane`).

- `print` to a redirected file is block-buffered: launch long runs with
  `python3 -u` or you get an empty log until exit.
- Backgrounding over `ssh 'nohup … &'` hangs the launching ssh session — the
  nohup'd process inherits and holds the session's stdin socket. Redirect it
  at launch (`nohup cmd > log 2>&1 < /dev/null &`), verify the process with a
  separate `ssh -n` check, and never make the round's control flow wait on
  the launching call returning (this killed round 10 and re-bit round 16).
- Sanity-check the table before publishing: decode rate should fall (mildly)
  with prompt size and prefill rate should not jump around by >2×. A number
  that violates monotonicity is usually the measurement method breaking, not
  the engine getting faster (the 11.84 tok/s decode@4k artifact rendered
  straight into round 10's results table).
- "Decode tok/s" is not one number — it falls with KV size (pgain-nuc: 5.3
  @ ~300-token KV, 4.8 @ ~1k, 3.3 @ ~4k). Always report decode WITH the KV
  size it was measured at, or the numbers look mutually contradictory.
- Default-argument `opener=_post` binds at import; monkeypatching the module
  attribute then does nothing. Default to `None` and resolve inside.
- Repeating the same prompt across sizes (100 → 1k as prefix extension)
  would let a real prefix cache leak between sizes; seed every size
  differently.
- The server's reported decode `tps` (colibri STAT) starts its clock after
  prefill and is not exposed to clients — client-side subtraction is the
  only portable path; keep `D ≥ 64` so decode time is not swamped by
  prefill jitter at large sizes.
- Engine tokenizers are NOT the HF tokenizer, even loading the same
  tokenizer.json. Two measured divergences on colibri/qwen36: (1) a special
  token directly preceded by punctuation is not matched and its literal text
  falls to plain BPE (+4 tokens per `<|im_end|>` after `.`/`!`/`}`/`]` — and
  the model then sees a TEXT-SPELLED control token; nearly every JSON tool
  frame hits this); (2) whitespace-heavy text drifts ~±3 % from HF counts in
  BOTH directions. Never assume local count == engine count without probes;
  never chase exact C-BPE emulation past the accuracy your budget needs.
- Timing predictions must state their warm/cold precondition. An engine idle
  for ~10 min cost +45–50 s on the next request (more than the recorded
  25.7 s cold-start figure); a "±20 %" band written without the qualifier
  scores as a miss even though the warm model was right within 7 %.
- macOS has no `timeout`; wrap suites in `perl -e 'alarm N; exec @ARGV'`.

## Commands

```bash
# offline tests (fake engine, virtual clock)
python3 -m pytest -q nuc/tests/test_bench.py
# smoke against a live engine (never port 8001)
python3 nuc/bench.py --base-url http://127.0.0.1:8000 --sizes 100 --decode-tokens 16 --stream-check
# full curve, repeat/fresh probes only at the cheap sizes, unbuffered log, detached
nohup python3 -u bench.py --sizes 100,1000,4000,8000 --decode-tokens 64 --warm-sizes 100,1000 \
  --json-out /work/logs/nuc-bench.json --md-out /work/logs/nuc-bench-table.md > bench-run.log 2>&1 &
```

## Verification

- `python3 -m pytest -q nuc/tests/test_bench.py` → 13 passed (fake engine
  with a virtual clock: prefill 12 tok/s, decode 3.5 tok/s, template 12 tok;
  asserts recovered decode == 3.5, warm/cold == 1.0, cutoff extrapolation
  within 2 %, port-8001 refusal, CLI writes JSON+MD).
- Live smoke: `python3 bench.py --sizes 100 --decode-tokens 16 --stream-check`
  and check `stream TTFT ≈ non-stream TTFT` (15.68 vs 15.82 s on pgain-nuc).
- The final table has a `Prefill model:` line, every skipped size is marked
  `EXTRAPOLATED`, and the predictions file has a scored hit/miss per row.

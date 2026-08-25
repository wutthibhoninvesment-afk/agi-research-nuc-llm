---
name: engine-prefix-reuse-audit
description: Audit a self-hosted LLM inference engine's serve loop (colibri, llama.cpp-style C engines, custom Python servers) for cross-request KV/prefix reuse and produce a compile-verified upstream patch without running the weights. Use when every chat turn re-prefills the whole transcript and turn time grows with conversation length, when a server advertises kv-slots / cache_slot / prefix caching but identical repeat prompts are no faster, when the model is a hybrid (Mamba, DeltaNet, KDA, linear attention + attention layers) and nobody knows what "the KV cache" even means for it, when you must propose an engine change for a read-only production box you cannot restart, or when an agent framework's re-rendered assistant turns silently defeat a prefix cache. Not for client-side prompt caching (Anthropic cache_control — see agent-context-budgeting) and not for measuring the TTFT curve itself (see llm-engine-benchmarking).
---

# Auditing an inference engine for prefix/KV reuse

An engine that re-prefills the whole prompt every request turns a 5 tok/s
prefill machine into an 86-minute-per-turn agent. The audit answers, from the
source alone, whether state can persist across requests, what would have to
change, and ships a patch that compiles and passes unit tests against a
*shaped* model (geometry only, no weights). Reference: `nuc/kv_reuse/`
(round 28: `make_patch.py`, `test_qwen36_prefix.c`, `PROPOSAL.md`,
`kv_reuse_model.py`).

## When to use (triggers)

- Repeat/fresh TTFT ratio ≈ 1.0 on identical prompts (measured with
  llm-engine-benchmarking) although the server has a slot/cache option.
- Turn N of a conversation costs as much as turns 1..N together.
- The deployment is read-only or cannot be restarted: the deliverable is a
  proposal + patch, and the only test bed is a copy of the sources.
- The model is a hybrid: recurrent layers hold state that cannot be rewound.

## Steps

1. **Bank predictions first** (`state/round-NNN-predictions.md`): what the
   slot field does, whether the reset is unconditional, bytes per KV position,
   patch size, and one cheap live probe. Before banking any "only X uses this
   header" claim, run `grep -l <header> *.c` — the tree usually has prior art.
2. **Find the reset and the slot.** `grep -n "kv_len *= *0\|reset_\|(void)slot\|cache_slot\|kv_slots"` over
   the worker and the gateway. Follow the slot from HTTP body → scheduler →
   SUBMIT header → worker parse. A worker that discards it, or a family
   registry that caps `max_kv_slots = 1`, means the documented feature is inert
   for this engine even if `/health` reports slots.
3. **Confirm cheaply, never expensively.** Two probes that pay no prefill:
   `GET /health` (slot count) and a request with an out-of-range `cache_slot`
   (expect a fast 400). Then one warm repeat triple (three identical short
   prompts, ratio of 3rd/2nd TTFT) — only the last two are comparable; state
   the warm/cold precondition.
4. **Inventory every piece of per-position and per-conversation state.** For
   each layer type: K/V rows (bytes/token = 2 × layers × kv_heads × head_dim ×
   dtype), recurrent state (fixed size per layer — compute it: it decides the
   design), conv rings, indexer caches, router EMAs. Check whether the EMA or
   any other carried state changes *outputs* (routing) or only performance
   (prefetch) — that decides whether reuse must reset it.
5. **Check the two silent killers before designing anything.** (a) Growth
   policy: does the KV allocation free-and-reallocate when `max_t` grows? A
   conversation grows every turn, so reuse can never fire unless growth
   copies. (b) Stride: are rows indexed with the request's `max_t` or the
   allocation's capacity? They only agree while every request starts at 0.
6. **Prove where the next prompt diverges — with the real template.** Render
   turn 1 and turn 2 through the real gateway/adapter code and the model's own
   tokenizer; find the longest common byte and token prefix. Expect: the
   generation suffix (e.g. Qwen's empty think block, 4 tokens) is absent
   from history, and adapters re-render tool calls. Strict continuation
   (kv_prefix.h pattern) then reuses zero; the snapshot must sit at the
   *assistant header*, not the prompt end.
7. **Design from the asymmetry.** Position-indexed K/V rows stay valid for
   every position whose token still matches (a row depends only on its
   prefix); only the recurrent state needs snapshots, and it is small and
   context-independent. Decision order: strict continuation → deepest
   snapshot at/below the LCP → cold. Snapshots above the kept prefix are
   dropped. Gateway hints (byte offsets, tokenized and accepted only as exact
   token prefixes) place the snapshots: system boundary + stable prompt end.
8. **Generate the patch reproducibly.** A script of asserted-unique
   `str.replace` edits against the pristine file with its md5 pinned
   (`make_patch.py`), emitting `diff -u`. An upstream drift then fails loudly.
9. **Test without weights, upstream style.** `#define main x_unused` /
   `#include "../engine.c"` / a `shape_model()` that fills only geometry
   fields; simulate `step()` by recording ids and moving `kv_len`. Cover:
   growth keeps rows at the new stride, strict continuation, snapshot across
   a re-rendered reply, deepest snapshot wins, every rejection rule, header
   parsing. Build with the shipped flags and diff the *warning set* (line
   numbers stripped) against pristine — it must be identical.
10. **Write a Python reference model of the decision** and pin the same
    scenarios plus the real-tokenizer boundary facts; project per-turn time
    from the measured curve for real rendered sessions under none / strict /
    snapshot policies. The projection table is the proposal's headline.
11. **Ship** `PROPOSAL.md` (problem, why prior pattern is insufficient, design,
    projected effect, verification done, *not verified*, risks) and a
    results log on the target box; leave the operator a one-line A/B recipe.

## Commands

```bash
# 2. slot and reset sites (worker + gateway)
grep -n -iE "kv_len *= *0|reset_recurrent|\(void\)slot|cache_slot|kv_slots|kv_prefix" engine.c server.py
grep -l kv_prefix.h *.c            # who already has reuse
# 3. cheap probes
curl -s http://127.0.0.1:8000/health
curl -s -w "\nHTTP %{http_code} %{time_total}s\n" http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' -d '{"model":"m","messages":[{"role":"user","content":"hi"}],"max_tokens":1,"cache_slot":1}'
# 9. build + test a shaped-model unit test with the shipped flags
gcc -O1 -march=native -fopenmp -pthread -Wall -Wextra tests/test_engine_prefix.c -o t -lm -fopenmp -pthread && ./t
diff <(sed -E 's/:[0-9]+:[0-9]+:/:/' w_pristine.txt) <(sed -E 's/:[0-9]+:[0-9]+:/:/' w_patched.txt)
```

## Pitfalls

- **Strict continuation is not agent-safe.** kimi_k3/inkling-style "prompt
  begins with everything fed" never fires when the client re-renders the
  reply or the template appends a generation suffix. Measure the divergence
  point with the real renderer before choosing the pattern (round 28: a
  prompt-END snapshot would have reused 317/415 instead of 335/415).
- **Growth that frees the buffer defeats reuse in the only case it exists
  for** — the conversation whose prompt grows every turn. Copy on growth and
  grow the record with it (kv_prefix_grow), or reuse silently never fires.
- **Row stride tied to the request's max_t** misreads reused rows as soon as a
  later request sends a different `max_tokens`. Index with the allocation.
- **A snapshot must be labelled by the ids that produced it** and taken only
  when the state is exactly at that position (`kv_len == pos`); a partial or
  derived record answers from another conversation's state and does not crash.
- **Warm-repeat ratios need three requests**: the first carries whatever cold
  effect exists (post-restart page-cache warm-up masquerades as "idle
  penalty"); compare 3rd/2nd.
- **Extrapolate decode in seconds-per-token, not tokens-per-second** — the
  tok/s series is hyperbolic in KV size; a linear fit crosses zero.
- **Backgrounded remote jobs hang the ssh session** even with redirections;
  launch with `ssh -n … 'nohup … > log 2>&1 < /dev/null &'` and accept the
  client timeout, then verify with a fresh `ssh -n pgrep`.
- **`cd` inside a compound shell command persists** into later tool calls;
  use absolute paths for every script and venv (bit twice this round).

## Verification

- Predictions file scored with a per-item HIT/MISS and a miss-pattern note.
- `/health` + out-of-range slot probe outputs recorded; warm triple recorded
  with the ratio computed from requests 2 and 3.
- New unit test passes; the engine's existing tests pass against the patched
  file; pristine-vs-patched warning sets identical; full engine binary links.
- Python reference-model tests pass, including the real-tokenizer divergence
  facts (byte prefix, token prefix, suffix token ids).
- Projection table produced from real rendered sessions, none/strict/snapshot.
- PROPOSAL.md lists what was NOT verified (live weights) and the A/B recipe.

# E3 — KV/prefix reuse analysis for qwen36 (read-only) — 2026-08-24, round 28

Predictions banked first in `state/round-028-predictions.md` (Mac); ledger 7 HIT / 5 MISS.
NO colibri/hermes sources edited. No engine restart. Port 8001 untouched.
Written on the NUC: `~/nuc-research/{kv_probe.py,probe_p1.json}`, `~/nuc-research/kvreuse/**`
(a COPY of /work/src/colibri-v170/c with the proposed patch applied + built), `/tmp/r28_probe.*`.

## Answer to the mission question

**Can KV state persist across requests so a stable prefix is computed once?**
Not today; yes with a ~250-line engine patch that follows the tree's own pattern.

- `qwen36.c` `serve_one()`: `reset_recurrent(m); ensure_kv(m); m->kv_len = 0;` per
  request, unconditionally. SUBMIT `slot` is parsed then `(void)slot;`.
- `--kv-slots` is inert AND rejected >1: `family_registry.py:552` gives qwen36
  `max_kv_slots = 1`; `coli:1472` exits otherwise. Live: `/health` → `kv_slots: 1`,
  `cache_slot: 1` → HTTP 400 "between 0 and 0" in 3 ms. `docs/serve_protocol.md`'s
  slot-reuse promise is written for GLM and does not hold for this engine.
- `kv_prefix.h` (strict continuation of the fed token record) is shared and already
  wired into kimi_k3.c, inkling.c, deepseek_v4 — qwen36 is the only non-GLM engine
  without it. DSV4 additionally keeps LRU checkpoints (system prefix + prompt end)
  and takes an 8th SUBMIT field as the system-boundary hint.
- Model geometry (config.json): 40 layers = 30 Gated DeltaNet + 10 Gated Attention,
  2 KV heads × 256 dim f32 → 40,960 B/token of K/V; DeltaNet state 65.9 MB total,
  context-independent. `ensure_kv` FREES the cache whenever `max_t = np + max_tok`
  grows (every turn) and attention indexes rows with `max_t` as the stride — both
  must change for any reuse to survive a turn.

## Live probes (:8000 only)

3 identical 339-token raw prompts (`/v1/completions`, stream, temp 0, max_tokens 40),
after ~2 h idle: TTFT **48.33 / 47.58 / 47.57 s**, 19 chunks each, identical text
`{"tool_calls":[{"name":"run_shell","arguments":{"command":"df -h /"}}]}`.
Ratio 3rd/2nd = 1.000 → no reuse. No idle-cold penalty (+0.75 s on the first);
round 22's 45–50 s "idle penalty" was most likely the first request after the
10:34 engine restart.

## Retokenization finding (drives the design)

Turn 2's rendered prompt continues turn 1's prompt only up to `<|im_start|>assistant\n`
(335 of 339 tokens): the empty `<think>\n\n</think>\n\n` block (4 tokens) is
omitted from history, and the tool-proxy re-renders the tool call with json.dumps
spacing. Strict continuation (kimi_k3 pattern) therefore reuses 0; a prompt-END
snapshot is unreachable; a snapshot at the assistant header reuses 335.

## Proposed patch (compiled + unit-tested here, never run with weights)

`~/nuc-research/kvreuse/c/qwen36.c` = upstream + `qwen36-prefix-reuse.patch`:
record fed ids (`kv_prefix.h`), grow-preserving `ensure_kv` (kv_cap stride),
two 65.9 MB DeltaNet snapshots (system boundary via gateway hint or LCP plan;
stable prompt end via a 2nd hint), decision = strict → deepest snapshot ≤ LCP → cold.
Server: emit both hints for qwen36 (`openai_server-prefix-hint.patch`).
Build: identical 6-warning set vs pristine (gcc 13.3, shipped flags).
Tests: `tests/test_qwen36_prefix.c` 37/37, `tests/test_qwen36_ctx.c` 14/14,
`tests/test_kv_prefix.c` ok, `python3 -m unittest tests.test_openai_server` 144 OK.

## Projection (E1 curve, real rendered conversations)

nuc-mini 4-turn: prefill 55/67/72/86 s today → 55/15/8/17 s. Hermes 26.5k: 86 min
per turn today → 86 min once, then 18 s / 9 s prefill; decode at 26k KV ≈ 1 tok/s
becomes the ceiling (~3.6 min per 200-token reply).

## Next (needs an operator decision — not done in E3)

Run the patched binary on :8000 for an A/B (`Q36_PREFIX=0` vs `1`, same 3-turn
conversation, temperature 0: identical tokens + TTFT). Requires one engine
restart with `SNAP=/work/models/qwen36_i4_gs64 SERVE=1 KV_SLOTS=1 Q36_MAXT=32768
NGEN=8192 ~/nuc-research/kvreuse/c/qwen36_prefix 256` behind the same server.

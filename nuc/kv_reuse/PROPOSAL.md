# Proposal: KV/prefix reuse for the qwen36 engine (colibri v1.7.0)

Status: patch compiles warning-identical to upstream, unit-tested without model
weights, **not yet run against live weights** (the only deployment is a
read-only production box). Author: agi-research round 28 (E3), 2026-08-24.

## Problem

`qwen36.c` is the only non-GLM engine in the tree that re-prefills the whole
prompt on every request. `serve_one()` does `reset_recurrent(m); ensure_kv(m);
m->kv_len = 0;` unconditionally, and the SUBMIT `slot` field is parsed and
discarded (`(void)slot;`). `family_registry.py` caps the family at
`max_kv_slots = 1`, so `--kv-slots` cannot even be raised. Meanwhile
`docs/serve_protocol.md` promises for every engine that "a slot holds one
conversation's KV; the engine matches the tokenized payload against the slot's
history and reuses the common prefix" — true for GLM (`colibri.c`, #639),
kimi_k3, inkling and deepseek_v4 (all via the shared `kv_prefix.h`), false for
qwen36.

Measured cost on an i5-7260U (2c/4t, 31 GB): prefill 5.1 tok/s marginal, so a
26.5k-token Hermes agent turn is ~86 min of TTFT re-paid every turn; even the
purpose-built 339-token profile pays 48 s per turn (three identical requests:
48.33 / 47.58 / 47.57 s — ratio 1.00, i.e. zero reuse today).

## Why the kimi_k3 pattern alone is not enough here

`kv_prefix.h`'s strict continuation ("the new prompt begins with every id the
state was built from") never fires for an agent turn on this template:

1. The Qwen chat template's generation prompt ends with an empty
   `<think>\n\n</think>\n\n` block (4 tokens) that the history rendering omits.
2. The tool-proxy re-renders the assistant reply (`json.dumps` spacing for tool
   calls; reasoning stripped), so the raw emission is not what comes back.

So turn 2 diverges from turn 1's *fed* sequence 4 tokens before the end of
turn 1's prompt. Verified with the model's own tokenizer on a real reply from
the live engine (`nuc/tests/test_kv_reuse_model.py`).

The engine is a hybrid (30 Gated DeltaNet + 10 Gated Attention layers). The
attention K/V rows are per position and stay valid for every position whose
token still matches (a row depends only on its prefix). The DeltaNet recurrent
state cannot be rewound — but it is small and context-independent:
30 × (32×128×128 + 8192×3) × 4 B = **65.9 MB** per snapshot, versus 40 KB per
position of K/V. That asymmetry is the design.

## Design (`qwen36-prefix-reuse.patch`, +250/−27 lines)

1. **Record what was fed** (`kv_prefix.h`, unchanged): `kv_prefix_record()` in
   `step()` right where `kv_len` advances. The record is the only description
   of the state anyone consults.
2. **Grow, don't restart**: `ensure_kv()` copies the first `kvp.len` rows of
   every head into the grown buffers (`[kv_heads][kv_cap][kvd]`, one strided
   memcpy per head) and grows the record with `kv_prefix_grow()`. Without this,
   reuse could never fire: a conversation asks for a larger `max_t` every turn.
   Attention now indexes rows with the allocated stride `kv_cap`, not the
   request's `max_t` (they only agreed before because every request restarted
   at position 0).
3. **Two DeltaNet snapshots** (`Q36Snap`, allocated once): slot 0 = the
   system-prefix boundary, slot 1 = the *stable* end of the prompt. A snapshot
   is taken only when `kv_len == pos` and the record covers `pos`.
4. **Decision before mutation** (`prepare_request_state`): strict continuation
   → else the deepest snapshot at or below the LCP of record and prompt
   (restore the DeltaNet state, truncate the record to it, keep the K/V rows)
   → else cold. Snapshots above the kept prefix are dropped (their positions
   are about to be overwritten). Bit-for-bit the cold run's logits in every
   case: positions are absolute and chunked prefill is exactly how decode
   already extends the state.
5. **Two gateway hints** on the SUBMIT line (8th/9th fields; older engines
   parse six or seven and ignore the rest): `prefix_bytes` = end of the system
   turn (same field the DSV4 engine takes), `stable_bytes` = end of the last
   `<|im_start|>assistant\n` header. Each is tokenized and accepted only as an
   exact token prefix of the prompt. Without the first hint, a cold miss plans
   the system snapshot at the LCP with the previous prompt (DSV4's rule);
   without the second, the prompt end is used.
6. `Q36_PREFIX=0` disables everything; `Q36_PREFIX_LOG=1` reports the decision
   either way (K3/INK convention); `Q36_PREFIX_MIN` (default 64) is the
   smallest boundary worth a snapshot.

Server side (`openai_server-prefix-hint.patch`, +73 lines incl. test): emit
both hints when `ARCH == "qwen36"`, with a byte-exact transcript test next to
the existing DSV4 one. No change to `family_registry.py` is needed —
`max_kv_slots` stays 1; the single slot now keeps state.

## Projected effect (E1 curve, real rendered conversations)

| session | turn | today | strict-only | this patch |
|---|---|---|---|---|
| nuc-mini (339-tok profile), 4 turns | t2 / t3 / t4 prefill | 67 / 72 / 86 s | same | **14.8 / 7.7 / 17.3 s** |
| Hermes (26,475 tok), 3 turns | t2 / t3 prefill | 86 / 87 min | same | **18 / 9 s** |

"Strict-only" (kimi_k3 pattern, no snapshots) buys nothing on this template.
For Hermes, decode at 26k KV (~1 tok/s, hyperbolic fit of the E1 series)
becomes the ceiling: ~3.6 min for a 200-token reply instead of 86+ min.

## Verification done

- `tests/test_qwen36_prefix.c` (new, upstream style: `#include "../qwen36.c"`,
  shaped Model, no weights): 37 checks — growth keeps rows at the new stride,
  strict continuation, prompt-end snapshot across a re-rendered reply, deepest
  snapshot wins / deeper dropped, every rejection rule, header parsing.
- Upstream `tests/test_qwen36_ctx.c` (14) and `tests/test_kv_prefix.c` pass
  against the patched engine; `tests/test_openai_server.py` 144 tests pass with
  the new hint test.
- Engine builds with the shipped flags (`-O3 -march=native -fopenmp -Wall
  -Wextra`) with a warning set identical to pristine (6, all pre-existing).
- Python reference model of the decision (`nuc/kv_reuse_model.py`) pins the
  same scenarios and the real-tokenizer boundary facts.

## Not verified — what a maintainer should run

1. Live differential: `Q36_PREFIX=0` vs `1` on the same 3-turn conversation,
   compare emitted tokens (should be identical at temperature 0) and TTFT.
2. `Q36_PREFIX_LOG=1` on an agent client: expect `reusing N of M` with
   `stable_cut` set on turn 1 and `reuse == stable_cut` on turn 2.
3. Memory: +2 × 65.9 MB resident for the snapshots; K/V growth copies are
   `kvp.len × 40 KB` per turn (22 MB for a 550-token prefix).
4. Sampling determinism across a reuse boundary is not affected (the sampler
   sees the same logits), but the pilot prefetch EMA is now kept across a kept
   prefix — prefetch-only, routing uses the raw logits (`moe()`).

## Risks / open questions

- The worker tokenizer's special-after-punctuation quirk (round 22): the hints
  are tokenized by the same `encode_text`, so prefix equality is checked in the
  engine's own token space — consistent, but the boundary must not fall right
  after punctuation (template markers follow `\n`, so it does not).
- If the client sends `max_tokens` such that `np + max_tok` shrinks below the
  record length, `ensure_kv` early-returns and nothing is lost; the record
  capacity is the old, larger cap.
- `generate()`/`tf_nll()` (CLI/eval paths) now call `model_state_reset()`;
  behaviour unchanged (they always started cold).

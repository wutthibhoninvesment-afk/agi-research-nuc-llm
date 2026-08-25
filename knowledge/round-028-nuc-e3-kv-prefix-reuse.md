# Round 028 — NUC-integration(E): E3 prefix/KV reuse analysis → compile-verified patch

Date: 2026-08-24. Track E, mission **E3 — prefix/KV reuse analysis (READ-ONLY)**.
Predictions banked before reading the serve path (`state/round-028-predictions.md`);
ledger **7 HIT / 5 MISS**, every miss root-caused there. No colibri/hermes source
edited, no engine restart, port 8001 untouched.

## Inheritance audit

Round 27 (skills) left trigger_eval v4 edits, `skills/canary.json`, a canary
baseline, transcripts and UNSCORED `state/round-027-predictions.md`, with no
knowledge file and an unfinished state stub. Its offline suite is green
(116 tests; P9's 110–135 band would have hit). Not re-run here — recorded for the
next skills round (33). Also untracked: `languages/whence/tests/test_timetravel_debugger.py`
(the concurrent interactive session's work, not mine).

## The answer to E3

**KV state cannot persist across requests on qwen36 today, and the documented
slot feature is inert for this engine.** Evidence, all from the tree:

- `qwen36.c` `serve_one()`: `reset_recurrent(m); ensure_kv(m); m->kv_len = 0;`
  per request, unconditionally; the SUBMIT `slot` is parsed then `(void)slot;`.
- `family_registry.py:552` caps qwen36 at `max_kv_slots = 1`; `coli:1472` exits
  on more. Live: `/health` → `kv_slots: 1`; `cache_slot: 1` → HTTP 400 in 3 ms.
- `docs/serve_protocol.md` promises per-slot prefix reuse for every engine
  ("truncate-and-extend") — true for GLM (`colibri.c`, #639), kimi_k3, inkling,
  deepseek_v4 (all through the shared `kv_prefix.h`), false for qwen36. It is
  the only non-GLM engine without reuse (P2 under-predicted this).
- Live triple (339-token prompt ×3, `/v1/completions` streaming): TTFT
  48.33 / 47.58 / 47.57 s, ratio 1.000 → nothing reused (P8 hit). The
  round-22 "idle-cold penalty" did not reproduce after 2 h idle (+0.75 s);
  re-diagnosis: that turn was the first request after the 10:34 engine
  restart — post-restart page-cache warm-up, not idleness.

## What the model is, and why that decides the design

Qwen3.6-35B-A3B in this engine: 40 layers = **30 Gated DeltaNet + 10 Gated
Attention** (`i % 4 == 3`), attention K/V fp32 with 2 KV heads × 256 dim →
**40,960 B/token**; DeltaNet recurrent state 32×128×128 f32 per layer + conv
ring 8192×3 → **65.9 MB for the whole model, independent of context**.
Position-indexed K/V rows stay valid for every position whose token still
matches (a row depends only on its prefix); the recurrent state cannot be
rewound but is cheap to snapshot. So: keep the K/V buffer, snapshot only the
DeltaNet state at chosen positions, and reuse = deepest snapshot at or below
the longest common prefix.

Two pre-existing properties of `qwen36.c` would silently defeat ANY reuse and
had to change: `ensure_kv()` frees and reallocates when `max_t = np + max_tok`
grows (every turn of a conversation), and `attention()` indexes rows with the
request's `max_t` as the stride rather than the allocation's — they agreed only
because every request restarted at position 0.

## The finding that changed the design: where turn 2 diverges

Rendering turn 1 and turn 2 through the byte-identical adapter copy and the
model's own tokenizer, with the REAL reply the engine produced in the live probe:
turn 2's prompt continues turn 1's prompt only up to `<|im_start|>assistant\n` —
**335 of 339 tokens**. The template's empty `<think>\n\n</think>\n\n` generation
suffix (4 tokens: 248068, 271, 248069, 271) is not in the history rendering,
and the tool-proxy re-renders the tool call (`json.dumps` spacing) so the raw
emission `{"tool_calls":[{...}]}` never reappears. Consequences:

- The kimi_k3/inkling pattern (strict continuation) reuses **0** on agent turns.
- A prompt-END snapshot sits past the divergence: the first projection showed
  every turn falling back to the system boundary (317/415 instead of 335/415).
- Fix: a second gateway hint (`stable_bytes` = end of the last assistant
  header) so the engine snapshots there. Found by the test, not by reading.

## Built (all real, all run)

`nuc/kv_reuse/`:
- `make_patch.py` → `qwen36-prefix-reuse.patch` (+250/−27; md5 of the pristine
  file pinned; asserted-unique replacements). Design: `kv_prefix_record` in
  `step()`; grow-preserving `ensure_kv` (strided copy per head, `kv_cap`
  stride in attention, `kv_prefix_grow`); `Q36Snap` ×2 (system boundary,
  stable prompt end); `prepare_request_state` = strict → deepest snapshot ≤
  LCP → cold, decided BEFORE mutation; 3-chunk prefill with snapshots at the
  cuts; SUBMIT header fields 8/9 (`prefix_bytes`, `stable_bytes`) parsed,
  extension payload drained; `Q36_PREFIX=0`, `Q36_PREFIX_LOG`, `Q36_PREFIX_MIN`.
- `make_server_patch.py` → `openai_server-prefix-hint.patch` (+73 incl. a
  byte-exact transcript test mirroring the DSV4 one).
- `test_qwen36_prefix.c` — upstream style (`#include "../qwen36.c"`, shaped
  Model, no weights): **37/37** on the NUC (gcc 13.3). Upstream
  `test_qwen36_ctx.c` **14/14** and `test_kv_prefix.c` pass against the patched
  engine; `python3 -m unittest tests.test_openai_server` **144 OK**.
- Engine builds with the shipped flags in 4 s; **warning set identical to
  pristine** (6, all pre-existing). `patch` reproduces the built file byte-for-byte.
- `nuc/kv_reuse_model.py` + `nuc/tests/test_kv_reuse_model.py` (13 tests, nuc
  total 36): geometry, the decision as a Python mirror of the C, E1 timing,
  and the real-tokenizer divergence facts pinned.
- `build_scenarios.py` → projections from real rendered sessions:

| session | policy | prefill per turn |
|---|---|---|
| nuc-mini 4 turns (339→537 tok) | none / strict | 55 / 67 / 72 / 86 s |
| | **snapshot** | 55 / **14.8 / 7.7 / 17.3 s** (4.7 → 1.6 min total) |
| Hermes 3 turns (26,475 tok) | none / strict | 86 / 87 / 87 min |
| | **snapshot** | 86 min once, then **18 s / 9 s** |

For Hermes the ceiling becomes decode at 26k KV ≈ 1.0 tok/s (hyperbolic fit of
E1's 5.3/4.78/3.32 series in s/token) → ~3.6 min per 200-token reply: from
impossible to merely slow (P10's decode band was a linear extrapolation — miss).

- `PROPOSAL.md` (upstream write-up incl. "not verified" + A/B recipe),
  `/work/logs/nuc-kv-reuse.md` on the NUC, patches + built binary in
  `~/nuc-research/kvreuse/`.
- New skill `skills/engine-prefix-reuse-audit/` (+3 trigger cases epr-near/mid/far
  in `skills/trigger-cases.json`, now 42). Native probe, sonnet ×2:
  **6/6 exact, 0 foreign fires** (`state/trigger-eval/round-028-epr.json`);
  lint `--house --strict` clean across 10 skills.

## What is NOT verified

The patch has never run with weights: the only deployment is the production
engine (31 GB resident, 585 MB free — no second instance possible) and E3 is
read-only. Chunked-prefill exactness and snapshot/restore correctness are
argued from the code (decode already extends the state one token at a time)
and unit-tested on the bookkeeping, not on activations. The A/B recipe is in
the proposal; running it is an operator decision (one restart).

## Honest failures

- P2/P5 under-predicted prior art in the tree; a `grep -l kv_prefix.h *.c`
  before banking would have fixed both.
- First patch version snapshotted at the prompt end; the projection exposed
  it. Tests that render the REAL template caught a design error that reading
  the code did not.
- P9's band assumed 100-token deltas (real: 30–96) and P10 extrapolated
  tok/s linearly — computed bands built on the wrong model, again.
- `cd` persistence (rule 10) cost one silent empty run; the ssh-backgrounding
  hang re-tripped despite `< /dev/null` (the skill now says: accept the
  client timeout and verify with a fresh `ssh -n`).
- Pinned a token count by guess (334) instead of computing it (335); fixed
  by pinning the actual suffix token ids.

## Tests / regression

nuc 36 (23 + 13 new), harness 284, whence 465, skill lint clean (10 skills).

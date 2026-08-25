# E2 — Hermes prompt budget for the NUC (round 22, 2026-08-24)

Method: exact local reproduction of the full render pipeline (Hermes request
→ tool-proxy adapter → colibri qwen36 chat template → the model's own
tokenizer.json via HF tokenizers), calibrated against `usage.prompt_tokens`
from :8000 with small probes. Predictions banked before every measurement
(D-013); scores in nuc/predictions-e2.md (Mac).

## The Hermes turn, measured (this machine's real config: 22 tools enabled)

| component | engine tokens | share |
|---|---|---|
| tool schemas (rendered by adapter) | 19,682 | 74.3 % |
| system prompt (SOUL + guidance + skills index + memory + profile) | 6,773 | 25.6 % |
| conversation (1 short user msg) + framing | 28 | 0.1 % |
| **total first-turn prompt** | **26,483** | — |

Projected TTFT at the E1 curve: **≈ 86 min per turn, re-paid every turn**
(no cross-request KV reuse). The standing "26.5k-token Hermes turn" estimate
is confirmed exactly. Costliest tools: computer_use 3,446, cronjob 2,684,
session_search 1,901, delegate_task 1,609, skill_manage 1,256.

Even a maximally trimmed real-Hermes (8 cheapest file/terminal/web tools
≈ 5.0k + system prompt 6.8k) ≈ 12k tokens ⇒ ~40 min/turn. Zeroing skills
index + memory + profile too still leaves ≳ 5.5k ⇒ ~18 min/turn.
**Conclusion: do not point stock Hermes at this engine. A purpose-built
minimal profile is required.**

## nuc-mini — the recommended config (verified live end-to-end)

Profile in `~/nuc-research/nuc_mini.py` (also Mac `nuc/nuc_mini.py`):
short environment-stating system prompt + tight schemas, POSTed to the
existing tool-proxy :8080 unchanged.

| tier | tools | engine prompt tok | wall (warm) | behavior |
|---|---|---|---|---|
| micro | run_shell | 338 | **55.7 s** | correct `df -h / \| tail -1` call |
| mini turn 1 | run_shell, read_file, write_file | 546 | 142.3 s (idle-cold) | correct `df -h /` call |
| mini turn 2 | + tool result in history | 646 | **102.8 s** | correct plain-text answer "80 GB free" |

- A complete 2-turn agent loop (question → tool call → result → answer) ran
  correctly on qwen36 through the JSON tool protocol: **~4.1 min total**.
- Warm turns sit on the E1 curve (turn 2: 646 tok in ~100 s prefill
  ≈ 6.4 tok/s gross, E1 @904 was 6.32). Idle-cold turn 1 paid ~45–50 s over
  the warm projection — bigger than E1's 25.7 s cold-start figure; budget
  ~1 min extra for the first turn after an idle gap.
- History growth for one small tool exchange: +100 tokens ≈ +16 s/turn.
  A 10-turn mini session stays under ~1.4k tokens/turn ≈ 3.5 min/turn.

**Per-turn budget recommendation: micro ≈ 1 min, mini ≈ 1.7–2.5 min,
+~1 min on the first turn after idle. Keep every tool description to one
clause; each ~5 tokens of schema costs ~1 s of prefill on every turn.**

## Colibri worker tokenizer findings (new, exact)

1. **Special-token match fails after punctuation.** A special token
   (`<|im_end|>`, `<|im_start|>`, `</think>`) directly preceded by a
   punctuation/symbol char is NOT matched by the worker; its literal text
   falls through to plain BPE (+4 tokens for `<|im_end|>`). Preceded by
   letters/digits/whitespace it matches fine. Measured exactly via
   /v1/completions probes (k1–k6 series, 19 pinned data points, all
   reproduced by the Mac-side emulator `prompt_budget.Counter.n_engine`).
   Consequence: any chat turn whose text ends with `.`/`!`/`]`/`}` feeds
   the model a TEXT-SPELLED `<|im_end|>` instead of the control token —
   nearly every tool-protocol frame (`}`/`]`) hits this. The model coped in
   all live runs, but it is a real prompt-hygiene wart and inflates
   prompt_tokens by ~4/frame. Likely cause: pretokenizer runs before special
   matching, gluing the punctuation run to the special's leading `<`.
   Upstream fix candidate: match specials before/independent of
   pretokenization in the worker's encoder.
2. **Worker BPE ≠ HF tokenizers on whitespace-heavy text (~±3 %).** The
   worker counted the 561-HF-token mini prompt as 546 (−2.7 %) and a
   leading-space text probe 2 tokens HIGHER (m4). Prose-only and JSON-style
   probes matched exactly. For budgeting this is noise; for byte-exact work,
   calibrate against usage.prompt_tokens.

Raw artifacts: /tmp/mini_turn{1,2}_resp.json, /tmp/micro_turn1_resp.json
(NUC), request payloads and emulator + 12 offline tests on the Mac
(`nuc/prompt_budget.py`, `nuc/nuc_mini.py`, `nuc/tests/test_prompt_budget.py`).
No engine restarts were performed; no request touched port 8001.

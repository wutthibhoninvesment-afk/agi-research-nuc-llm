# Round 022 — NUC-integration(E): E2 prompt budget, nuc-mini verified live

Date: 2026-08-24. Track E, mission **E2 — prompt budget for Hermes** (first
unchecked). Predictions banked before every measurement (`nuc/predictions-e2.md`);
final ledger **P 2/7, A 2/5** with each miss root-caused.

## Method: count engine tokens without paying prefill

The E1 method ("usage.prompt_tokens is your tokenizer") is unusable at E2's
scale — counting a ~26k-token prompt that way costs the very 86-minute
prefill we're budgeting. The round's method instead:

1. **Local exact pipeline.** Copied the model's own
   `/work/models/qwen36_i4_gs64/tokenizer.json` off the NUC → HF `tokenizers`
   locally (`nuc/.venv`). Copied `/work/src/qwen36-toolproxy/adapter.py`
   byte-identically (`nuc/nuc-adapter-copy.py`) and **imported** it — its
   `messages_to_text`/`render_tools` run verbatim, so the adapter stage
   cannot drift. Replicated colibri's `render_chat_qwen` (openai_server.py:921,
   read this round; `enable_thinking=False` → pre-closed `<think>` block).
2. **Calibrate small.** `/v1/completions` takes a raw string (no template),
   so tiny probes isolate pure tokenizer behavior at seconds of prefill each.
3. **Differential component attribution.** Render with/without each part
   (tools, system, conversation, per-tool) so components sum to the total
   exactly (`prompt_budget.breakdown`).

Artifacts: `nuc/prompt_budget.py`, `nuc/nuc_mini.py`,
`nuc/tests/test_prompt_budget.py` (12 tests; 25 total nuc tests green).

## Finding 1 — colibri worker tokenizer ≠ HF tokenizers (two distinct bugs)

Calibration prompt 1 measured **+8 vs local** (73 vs 65). Bisection down to
single boundaries (19 `/v1/completions` probes, all pinned in the test file):

- **Specials fail to match after punctuation.** `<|im_end|>` / `<|im_start|>`
  / `</think>` directly preceded by a punctuation/symbol char (`.` `!` `}`
  `]`…) is NOT matched by the worker; its literal text falls through to
  plain BPE (+4 tokens for `<|im_end|>`). After letters/digits/whitespace it
  matches as one id. Mechanism (inferred): pretokenization runs before
  special matching, so the punctuation run glues onto the special's leading
  `<`, hiding it. **Consequence beyond counting: the model receives a
  TEXT-SPELLED `<|im_end|>` instead of the control token at nearly every
  JSON tool-protocol frame** (they end `}`/`]`). qwen36 coped in all live
  runs, but this is a real prompt-hygiene wart and an upstream fix candidate
  (match specials before/independent of pretokenization). Documented in
  `/work/logs/nuc-prompt-budget.md`; NO colibri sources touched.
- **Whitespace-heavy text drifts ~±3 % in BOTH directions.** The mini
  profile's 561-HF-token prompt counts 546 on the engine (−2.7 %); a
  leading-space text probe counts +2. Prose and JSON-style probes match
  exactly. I stopped short of emulating the C BPE — ±3 % is far below
  budgeting significance, and the live turns report exact counts anyway.

The emulator `Counter.n_engine` models bug 1 exactly (19/19 pinned probes
reproduced, incl. rebuilding the tokenizer with added-tokens neutralized to
get plain-BPE fallback counts) and accepts bug 2 as ±3 % noise.

## Finding 2 — the Hermes turn is 26,483 tokens; tools are ¾ of it

Dumped the REAL configured Hermes agent (not a hypothetical): shipped
`hermes prompt-size --platform cli --json`, then the inspection-agent recipe
(`AIAgent(api_key="inspect-only", …)` → `build_system_prompt(agent)` +
`agent.tools`). This machine's config: 18 toolsets → **22 tools**.

| component | engine tokens | share |
|---|---|---|
| tool schemas (adapter-rendered JSON protocol) | 19,682 | 74.3 % |
| system prompt (SOUL/guidance/skills-index/memory/profile) | 6,773 | 25.6 % |
| conversation + framing | 28 | 0.1 % |
| **total** | **26,483** | ⇒ **~86 min TTFT/turn** |

The standing "26.5k Hermes turn" estimate from round 10 was accurate to
0.1 %. Costliest tools: computer_use 3,446, cronjob 2,684, session_search
1,901, delegate_task 1,609, skill_manage 1,256 — schema verbosity, not tool
count, is the budget. Trim analysis: 8 cheapest useful tools ≈ 5.0k + fixed
system 6.8k ≈ 12k ⇒ ~40 min/turn; even zeroing skills-index/memory/profile
leaves ≳5.5k ⇒ ~18 min/turn. **Stock Hermes cannot reach the ~1k usable
ceiling by configuration; a purpose-built profile is required.** (Hermes
sends native OpenAI `tools=[...]`; the :8080 adapter renders them to a
system-prompt JSON protocol — so every schema byte is paid as prefill.)

## Finding 3 — nuc-mini: a real agent loop on the NUC in ~1–2.5 min/turn

`nuc/nuc_mini.py` (deployed to `~/nuc-research/nuc_mini.py`): environment-
stating one-paragraph system prompt + one-clause tool schemas, POSTed to the
EXISTING tool-proxy — zero server-side changes. Live results (:8080, real
qwen36):

| tier | tools | prompt tok (engine) | wall | behavior |
|---|---|---|---|---|
| micro | run_shell | 338 | 55.7 s | `df -h / \| tail -1` — valid, even elegant |
| mini t1 | +read_file, write_file | 546 | 142.3 s (idle-cold) | `df -h /` valid call |
| mini t2 | + tool result | 646 | 102.8 s | "The root filesystem has 80 GB of free disk space." |

- **A complete correct 2-turn agent loop in ~4.1 min total** — question →
  tool call → real df output → correct plain-text answer. The JSON protocol
  parsed cleanly both turns (`finish_reason: tool_calls` then `stop`).
- Warm turns sit ON the E1 curve: turn 2 ≈ 6.4 tok/s gross vs E1's 6.32
  @904. The piecewise-anchor projection (NOT the 1k–8k marginal fit, which
  over-predicts small prompts ~25 %) was within 7 % warm.
- **Idle-cold penalty ≈ 45–50 s** (turn 1) — nearly double E1's 25.7 s
  cold-start figure; the worker sits at 95.7 % RAM, so an idle gap
  plausibly costs page-cache refill. Budget +~1 min for the first turn
  after idle; state warm/cold preconditions in every timing prediction.
- History growth: one small tool exchange ≈ +100 tokens ≈ +16 s/turn;
  a 10-turn session stays ≤ ~1.4k tok/turn ≈ 3.5 min/turn.

**Config recommendation (the E2 deliverable):** don't point stock Hermes at
the NUC. Use nuc-mini (mini tier default, micro for shell-only tasks):
~1.7–2.5 min/turn warm, +1 min after idle. Every ~5 schema tokens cost ~1 s
of prefill EVERY turn — one-clause descriptions, no examples, no per-param
prose. End controllable message texts on a word (not punctuation) so the
frame's `<|im_end|>` stays a real control token (Finding 1).

## Honest failures

- **P1 predicted exact tokenizer agreement; reality had two separate
  divergence mechanisms.** The banked calibration design (2 probes) was too
  small to notice bug 2 at all — the mini-profile live run caught it by
  accident (546 vs 565). A third calibration probe with JSON-ish content
  would have caught it deliberately.
- **Cold-start bit the timing prediction AGAIN** (A2, after E1's F1) — the
  known 25.7 s figure was in my context and I still wrote a warm-only band.
  Now a skill pitfall: state the warm/cold precondition, predict both.
- The D-013 meta-pattern flipped: after E1's systematic optimism I padded
  ranges pessimistically and missed LOW three times (P5, P7-growth, A4).
  New rule in predictions-e2.md: computed-by-me quantities get narrow bands
  centered on the computation; machine-state quantities get explicit
  preconditions.
- An Edit put literal NUL bytes into `prompt_budget.py` (`"\x00"` intended
  as escape, written as raw bytes) — Python refuses to import such a file;
  fixed by byte-level replace. Watch for this when writing escape sequences
  through tool calls.
- A `cd`-in-compound + heredoc Bash call died oddly ("null bytes"), initially
  misattributed to the heredoc; the real cause was the NUL bytes already in
  the file being imported.

## Tests / regression

- nuc: **25 passed** (13 bench + 12 new prompt_budget, incl. the 19-probe
  engine-emulation pin). Harness: **266 passed**. Whence: **430 passed**.
  `skill_lint.py --house --strict skills/`: **9 skills, 0 errors,
  0 warnings** (llm-engine-benchmarking updated: +step 9 budget-locally
  method, +2 pitfalls, description +prompt-budget trigger).
- NUC state: no restarts, no writes outside `/work/logs`, `~/nuc-research`,
  `/tmp`; port 8001 never touched.

## Files

- Mac: `nuc/prompt_budget.py`, `nuc/nuc_mini.py`, `nuc/nuc-adapter-copy.py`,
  `nuc/tokenizer-qwen36.json`, `nuc/predictions-e2.md` (scored),
  `nuc/nuc-prompt-budget.md`, `nuc/hermes-dump/{system_prompt.txt,tools.json,
  parts_chars.json,full_turn_request.json}`, `nuc/tests/test_prompt_budget.py`.
- NUC: `/work/logs/nuc-prompt-budget.md`, `~/nuc-research/nuc_mini.py`,
  `/tmp/{mini_turn1,mini_turn2,micro_turn1}_resp.json`.

# Round 31 — predictions BEFORE measuring (banked 2026-08-24, ~21:40)

Context held, not predicted: harness 298 green + 1 inherited red
(`test_swe_campaign` selection bug, round 35's), whence 506, lint clean 10
skills. No API credentials (`ANTHROPIC_API_KEY`/`_AUTH_TOKEN` unset, no
`ant`); `claude` CLI 2.1.241 on PATH. Prices: opus-5 $5/$25 per MTok,
cache read 0.1×, cache write 1.25× (5m).

Design being built (harness v5): `ToolResult.usage`/`meta` (generic LLM-
spend roll-up from tools into the run's usage + caps, checked after
dispatch too); `DelegateTool` (factory-built child Agent, fresh history,
depth limit, footer + trace meta); `TraceLogger.tagged()` for nested
traces; `Checkpoint` (atomic JSON per step; `Agent.run(task,
checkpoint=)` resumes; completed runs are idempotent); `CachingSimLLM`
(wrapper double: fixed chars/token + longest-common-prefix cache over a
shared store → cache_read / cache_creation usage); `bench_delegation.py`.

- **P1 (suite):** harness ≥ 335 green (≥ 37 new tests), same single
  inherited failure, no existing test edited except for the
  `ToolResult` dataclass gaining optional fields (no test should need to
  change). Confidence 70 %.
- **P2 (resume identity):** a run crashed after step 2 and resumed in a
  fresh process/Agent sends request 3 BYTE-IDENTICAL (json.dumps of the
  wire messages, `_chars` stripped) to the uninterrupted run's request 3,
  including replayed raw_content and elided stubs. Confidence 80 %.
- **P3 (delegation break-even, computed):** for a sub-task whose
  observations total V = 8k tokens, a child overhead O = 1.5k tokens
  (system+tools), the analytic break-even in REMAINING parent steps R is
  ≈ O·1.25 / (V·0.1) ≈ 2.3 → the bench reports break-even **R between 2
  and 4** for that row. Confidence 60 %.
- **P4 (sim vs analytic):** the CachingSimLLM run of the same scenario
  through the REAL Agent loop gives an inline−delegated cost difference
  within **±20 %** of the analytic model's difference (the simulator
  prices exactly what the model prices; residual = child's own
  observations being uncached the first time + the report tokens).
  Confidence 55 %.
- **P5 (live CLI delegation):** `live_smoke.py cli-delegate` (sonnet-5
  parent + child through `claude -p`) completes with ≥ 1 delegate call,
  child stop_reason completed, total CLI-reported cost ≤ $0.15, on the
  FIRST attempt. Confidence 45 % (the CLI backend is one-tool-per-reply
  and the parent may just do the work itself — that would be a MISS on
  "≥ 1 delegate call").
- **P6 (base rate):** ≥ 1 of my own new tests fails on first run.
  Confidence 55 % YES (three consecutive clean rounds; the checkpoint
  identity test is the likeliest to bite — call-id counters).
- **P7 (cap after child):** a child that overspends the PARENT's USD cap
  ends the parent run with `budget_exhausted` immediately after the
  delegate observation is appended (no further LLM call). Confidence 90 %.
- **P8 (checkpoint cost):** saving a 200-message / 400 kB history every
  step costs < 5 ms per save on this machine (json.dumps + atomic
  replace). Confidence 65 %.

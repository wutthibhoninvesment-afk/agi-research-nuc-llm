# Round 109 — predictions BEFORE measuring (banked 2026-08-25, 19:05)

Context held, not predicted: harness suite = 361 tests at round 107 (364
counted there incl. 3 in a file since moved?) with ONE red inherited from
round 108 (`test_swe_killers::test_find_killer_for_a_real_semantic_mutant`,
anchor on the v0.6 concat line); whence 613; lint clean 13 skills; no API
credentials (`ANTHROPIC_API_KEY`/`_AUTH_TOKEN` unset, no `ant`); `claude`
CLI 2.1.245 on PATH; load avg 1.7–1.9 (no other round's campaign running;
orphan check clean). Prices: sonnet-5 via the CLI's own cost report.

Design being built (harness v6): `agentloop/guards.py` — `Guard.check(text,
ctx) -> Rejection|None`; `EmptyAnswerGuard`, `ProseToolCallGuard`
(python-call style `name(k=v, …)`, `tool call: name`, unfenced/malformed
JSON `{"name": …}` with commentary, XML `<tool_call>`/`<invoke>` forms;
`recover=True` dispatches a parsed call when the tool exists, is
`parallel_safe`, and every arg is a declared param), `JsonAnswerGuard`
(last ```json fence must parse and carry required keys), `PatternGuard`.
`AgentConfig.guards` + `max_guard_retries` (default 2); a rejection appends
a corrective user message and continues; exhausted → stop_reason
`"rejected"`; recovery → the turn is dispatched as if it had been a real
tool call (`guard_recovered` trace). `BashTool` → own session +
`killpg` on timeout, monotonic seconds, partial output kept.

## Round-31 ledger (its predictions, scored this round from the artifacts)
Not predictions of mine — scored in the knowledge file §1.

## Predictions (this round)

- **P1 (suite) [computed]:** harness ≥ 395 green (≥ 30 new tests: guards
  ≥ 22, bash ≥ 3, agent integration ≥ 5), 0 red after the killers
  re-anchor; whence 613 unchanged; lint clean. Confidence 75 %.
- **P2 (corpus detector) [computed]:** over the 17 recorded final texts of
  rounds 101/107 (8 kill + 6 repair + 2 review + 1 control) the guards
  reject EXACTLY the 4 known failures (`read_file(path=…)`, empty,
  `tool call: search`, the unfenced-malformed JSON with commentary) and
  the round-101 control's empty text (5 rejections), with **0 false
  positives** on the 12 good answers. Confidence 80 %. Sub-bet: the
  python-call case is the ONLY one that is recoverable (dispatchable)
  without a nudge; the malformed-JSON one needs the nudge. 70 %.
- **P3 (BashTool grandchild) [computed]:** with `sleep 3 & …` holding the
  pipe and a 0.5 s cap, the CURRENT tool returns after ≥ 2.8 s and the
  sleep survives; the new tool returns in < 1.5 s and the sleep is dead.
  Confidence 85 %.
- **P4 (live CLI guard smoke, cli-guards mode) [machine-state]:** the
  standard notes task with a `JsonAnswerGuard(["files"])` the TASK does
  NOT mention: warm branch — the first final answer is prose → 1 guard
  rejection → the nudge's format hint yields a valid JSON answer on the
  next completion → `completed` with `guard_rejections == 1`; 0 prose-
  tool-call false positives across the run; total ≤ $0.10. Confidence
  60 % (the model might volunteer JSON unprompted → 0 rejections, which is
  a MISS on the mechanism demo but still a HIT on false positives).
- **P5 (live cli-delegate, round-31 P5 finally run) [machine-state]:**
  completes with ≥ 1 delegate call, child `completed`, on the first
  attempt, CLI-reported total ≤ $0.15. Confidence 50 % (same reasons as
  round 31: the one-tool-per-reply CLI parent may just do the job itself).
- **P6 (base rate):** ≥ 1 of my new tests fails on first run. 65 % YES
  (the recovery arg-coercion or the grandchild timing are the likeliest).
- **P7 (recovery precision) [computed]:** the kwargs parser turns
  `read_file(path=whence/interp.py, start=1260, end=1320)` into
  `{"path": "whence/interp.py", "start": 1260, "end": 1320}` and refuses
  `bash(command=rm -rf x)` (not parallel_safe) — designed in, so 95 %; the
  bet is on the NEGATIVE cases not leaking: `search(query=a, b)` (positional
  → refuse) 90 %.
- **P8 (cost of a rejection) [computed]:** in the CachingSimLLM, a nudge
  costs one extra completion whose input is ≥ 95 % cache-read (the
  corrective user message is appended, nothing before it changes) — the
  sim's cache_hit_rate for that step ≥ 0.95. Confidence 80 %.
- **P9 (wall) [machine-state]:** full harness suite ≤ 9 min under this
  load (round 107: 7 min); the round's two live smokes ≤ 6 min combined.
  70 %.

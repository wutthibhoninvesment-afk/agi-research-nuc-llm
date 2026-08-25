# Round 006 — harness(A): context budgeting, usage/cost caps, Anthropic API adapter, parallel dispatch

**Artifacts:** `harness/agentloop/usage.py` (new), `agentloop/context.py` (new),
`agentloop/adapters.py` (+`AnthropicAPILLM`; `ClaudeCLILLM` now reports per-turn
usage), `agentloop/agent.py` (rewritten loop: compaction, spend caps, parallel
dispatch, timing), `agentloop/tools.py` (`parallel_safe`, `registry.get`),
`agentloop/evals.py` (usage/cost/compactions in outcomes + totals line),
`harness/demo.py` (4th task: long-run-compaction), `harness/live_smoke.py`
(real-model run, self-skips without credentials). Tests: 102 → **148**
(+4 usage, +9 context, +14 API adapter, +14 loop behaviours, +1 CLI usage, +1 killers docstring regression).
Skills: new `skills/agent-context-budgeting/`; `offline-agent-testing` upgraded
(fake transport, barrier concurrency proof, 2 pitfalls). Lint: 7 skills clean.

Run: `cd harness && python3 -m pytest -q` · `python3 demo.py` ·
`python3 live_smoke.py cli|api`.

## Test output
```
$ python3 -m pytest -q          # harness/
148 passed in 5.96s
$ python3 demo.py
eval report: 4/4 passed (100%)
  [PASS] write-and-verify         steps=3 tools=2 stop=completed  greeting.txt: 'hello, demo'
  [PASS] recover-from-error       steps=3 tools=2 stop=completed  recovered.txt: 'created after noticing the read error'
  [PASS] use-scratchpad           steps=2 tools=1 stop=completed  pad has note
  [PASS] long-run-compaction      steps=8 tools=7 stop=completed compactions=5  compactions=5, elided=5
$ python3 -m pytest -q          # languages/whence/ (regression, after the killers fix below)
212 passed in 4.60s
$ python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/
skill-lint: 7 skill(s), 0 error(s), 0 warning(s)
```

## 1. Usage and cost as first-class loop state (`usage.py`)
- `Usage` is a frozen dataclass with `+`; `AssistantTurn` gained `usage` and
  `raw_stop_reason`, so the accounting lives at the LLM interface and every
  backend (Mock, CLI, API) feeds the same sums.
- Pricing table per model (USD/MTok, from the claude-api skill's cached table);
  cache reads ×0.1, cache writes ×1.25. **Unknown model prices to `None`, not 0**
  — a cost cap on an unpriced model stops the run with "unpriced" instead of
  running blind (tested).
- `AgentConfig.max_total_tokens` / `max_cost_usd` → `stop_reason="budget_exhausted"`
  with `error` naming the cap. Checked after each completion but *before*
  dispatching tools, so a final text answer that crosses the line is still
  `completed`. `run_end` carries totals even on `llm_error`.

## 2. Context budgeting (`context.py`)
```
before each request:
  compact(messages, budget, estimator, tool_specs)
    stage 1: elide oldest un-elided tool observations (keep newest K) — stub
             "[observation elided …: <tool> returned N chars; call it again …]"
    stage 2: drop whole oldest steps (assistant + its tool results) down to
             min_steps_kept, replaced by ONE merged summary user message
  → CompactionReport(before, after, elided, dropped, fits) → trace event
```
Decisions and why:
- **In place and monotonic.** Rebuilding a fresh view per request changes the
  prefix every step and kills provider prompt caching; mutation only moves
  content raw → elided → dropped. Test asserts elided messages are
  byte-identical after later compactions (I first wrote this test as "the whole
  prefix is unchanged", which is wrong — a formerly-recent observation may age
  into elision; fixed the test, not the code).
- **Pairing invariant.** Steps are atomic units; `_steps()` groups an assistant
  turn with the tool messages that follow it. The API rejects a `tool_use`
  without its `tool_result` with a 400, so stage 2 never splits them (tested by
  walking the compacted history).
- **System prompt and task are untouchable**; `fits=False` is reported when even
  the floor is over budget rather than mutilating the task.
- **Self-calibrating estimator.** `chars / ratio` (+ serialized tool specs);
  `observe(chars_sent, actual_input_tokens)` — first sample replaces the 4.0
  prior, then EMA(0.3), clamped [1.5, 10]. `AnthropicAPILLM.count_tokens` is the
  exact fallback.
- Cost: incremental char accounting in stage 1 (no O(n·elisions) re-estimate).
  Measured, 8 KB observations, 100k-token budget: 200 steps 0.24 s total,
  1000 steps (2002 messages) 6.2 s total / 16 ms worst step — dominated by
  `json.dumps` of tool args in `chars_of`, negligible next to a 3 s LLM call.
- Demo task: six 1500-char observations against a 1200-token budget →
  `compactions=5, elided=5`, and the final `write_file` still lands.

## 3. `AnthropicAPILLM` — Messages API over stdlib `urllib`
Rationale: the project is stdlib-first on Python 3.9; the official SDK 1.x
needs ≥3.10 and isn't installed, no API key exists on this machine. Wire shape
taken from the claude-api skill's cURL reference (not from memory):
- history → `system` + messages; assistant → `[text, tool_use…]`; a **run of tool
  messages → ONE user message of `tool_result` blocks** (the parallel-tool-use
  rule: split results silently train the model out of parallel calls);
  `ok=False` → `is_error: true` (the loop now stores `ok` on tool messages).
- response → text joined, `tool_use` → `ToolCall(call_id=provider id)`; non-dict
  `input` becomes an error arg the registry rejects readably; `thinking` blocks
  ignored (not replayed — the harness keeps text only; a known limitation for
  same-model thinking continuity).
- `stop_reason == "refusal"` → tool calls dropped, text labelled with the
  `stop_details.category`, so the loop ends `completed` and never acts on a
  refused turn.
- Errors: 408/409/429/500/502/503/529 → `RetryableLLMError`, other ≥400 →
  `FatalLLMError` (parametrized test over 7 codes); URL/timeout faults →
  retryable; non-JSON 200 → fatal. Auth: `x-api-key` or `Authorization: Bearer`
  + `anthropic-beta: oauth-2025-04-20`. `effort` → `output_config`, `thinking`
  passthrough, `extra_body` for betas. Default model `claude-opus-5`.
- Transport injected: `FakeTransport` tests body/headers/URL, parsing, mapping,
  and a full `Agent` run (529 → retry → 2 parallel tool_use → merged results →
  priced usage) — 14 tests, no network.
- **Not done:** live call (no credentials; `live_smoke.py api` exits 2 = skip),
  streaming, server-side `fallbacks` for Fable 5, `retry-after` hints.

## 4. Parallel tool dispatch
- `Tool.parallel_safe` (read_file/list_dir/search True; write/bash/scratchpad
  False). All-or-nothing per turn: if any call names an unsafe or unknown tool
  the whole batch runs serially in call order; else `ThreadPoolExecutor`,
  results reassembled in **call order** regardless of completion. Trace event
  `dispatch {mode, n}`.
- Proof without timing: a tool whose `run()` waits on
  `threading.Barrier(n, timeout)` — succeeds only if n calls are in flight,
  and in serial mode returns a barrier-timeout *observation* (the loop survives).
  Tests cover parallel, default-serial, unsafe-in-batch (order preserved),
  unknown-tool-in-batch.

## 5. Live run (ClaudeCLILLM, claude-sonnet-5, `live_smoke.py cli`)
Task: read 3 notes files, write summary.txt with word counts.
- `completed` in 6 steps / 5 tool calls, summary correct (7/12/3), 25.7 s total
  (first step 9.0 s, then 3.1–3.5 s).
- Usage 12 in + 7593 cache-read + 1905 cache-write + 313 out; our price table
  says $0.01415, the CLI reported $0.0133 (6 % apart — the CLI applies its own
  rates; treat table pricing as an estimate, the provider's number as truth).
- Estimator: step-1 estimate 424 vs 1289 actual (the CLI appends our tool
  protocol to *its* system prompt, outside our history); after calibration
  step-6 estimate 1441 vs 1905 — within 25 % with no counting endpoint.
- **All five dispatches were serial**: the CLI protocol permits one tool block
  per reply, so parallelism is structurally unavailable on that backend — only
  the API adapter (native multi-`tool_use`) can exercise it.
- **Compaction is inert on the CLI backend**: with `--resume` the CLI holds
  the transcript and we send only the newest observation, so local elision
  never reaches the wire. Written into the new skill's "When NOT to use".

## Key learnings
1. **Budget is loop state, cap is a stop reason.** Once usage rides on the
   turn, caps, pricing, eval totals, and trace fields are one addition each.
2. **Monotonic in-place compaction is the cache-compatible one.** Any design
   that recomputes a view per request throws away the prefix cache.
3. **Pairing is the invariant that makes compaction wire-safe**; treat steps as
   atoms and never orphan a call or a result.
4. **Calibrate against what you actually sent.** The estimator only converges
   if `chars_sent` and `actual_input` describe the same bytes; a backend that
   adds hidden prompt skews the ratio (it clamped at 1.5 on step 1).
5. **A backend's protocol bounds the harness's features**: one-tool-per-reply
   ⇒ no parallelism; server-held transcript ⇒ no local compaction. Feature
   tests must run over the backend that can express the feature.
6. **Barrier > sleep for concurrency tests**: deterministic, sub-second, and
   the failure mode (timeout observation) is itself an assertion target.

## Honest failures / gaps
- Wrote one wrong test expectation (prefix-stable ≠ nothing-changes) — third
  round in a row this happens; the process rule "decide test-or-code, write the
  decided semantics down" held (documented in the module docstring).
- The stage-1 incremental optimization did not change the benchmark (6.2 s vs
  5.1 s before at 1000 steps — noise); the real cost is the full-history char
  walk per step. Left as-is with numbers; a per-message char cache is the fix.
- `AnthropicAPILLM` has never touched the network. Its wire shape is from the
  documented cURL reference, but 14 offline tests cannot catch a doc drift.
- Thinking blocks are dropped on replay; on same-model continuations this
  loses reasoning continuity (and Fable 5 wants them echoed unchanged).
- Price table is a snapshot and disagreed with the CLI by 6 %.
- Parallel dispatch shares one `ToolRegistry`; tools with internal state that
  are marked `parallel_safe` are the author's responsibility — no guard.
- **Round-5 regression found by the standing whence run:** the generated
  \`tests/test_generated_killers.py\` did not compile — two docstrings ended in a
  \`"\` that fused with the closing \`"""\` (\`SyntaxError\`, whole suite
  uncollectable). Root cause: \`killers.py\` interpolated raw JSON into a
  triple-quoted docstring. Fixed with \`docstring_safe()\` (no backslashes, no
  double quotes, no newlines, bounded) in the generator + applied to the 64
  existing docstrings; regression test added in \`test_swe_killers.py\`. Whence
  suite: 212 green. Lesson: a generator's output must be *compiled* in its
  own tests, not just written.
- Round-5 left its state entry as "IN PROGRESS"; finalized this round from its
  knowledge file. The process rule "write state early" still needs a
  finishing step: **write the round entry before the last test run**.

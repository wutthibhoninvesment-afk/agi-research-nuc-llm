# Round 001 — Harness core: tool loop, eval harness, offline test suite

**Track:** A (harness engineering) · **Date:** 2026-08-24 · **Status:** done, all tests green

## What was built

Completed `harness/agentloop/` — a stdlib-only Python 3.9 agent harness — plus its
first full test suite and a runnable offline demo.

Starting state (important, honest note): a **previous interrupted attempt** had
already written 6 modules (`llm.py`, `tools.py`, `memory.py`, `retry.py`,
`trace.py`, `truncate.py`) but the package **did not even import** —
`__init__.py` imported `agentloop.agent` which did not exist, there were **zero
tests**, no knowledge file, and no round log entry. `logs/driver.log` shows the
round-1 driver had started at 03:53 and evidently died mid-round. This round
audited the orphaned code, completed the missing core, and tested everything.

New this round:
- `agentloop/agent.py` — the tool loop (`Agent`, `AgentConfig`, `AgentResult`).
- `agentloop/evals.py` — eval harness (`EvalTask`, `run_evals`, `EvalReport`).
- `tests/` — 72 tests across 6 files, all offline, run in ~0.27s.
- `demo.py` — end-to-end 3-task eval suite with MockLLM, JSONL traces, scratchpad.
- Fixed `__init__.py` exports (added evals; package now imports cleanly).

## Architecture (as completed)

```
Agent.run(task)
  messages = [system(+scratchpad notes), user]
  loop (≤ max_steps):
    turn = retry_call(llm.complete, retry_on=RetryableLLMError)   # backoff+jitter
    append assistant msg {text, tool_calls[{name,args,call_id}]}
    if no tool calls -> AgentResult("completed", turn.text)
    for each call: registry.dispatch(name, args)  # NEVER raises
                   -> truncate_observation(result, max_obs_chars)
                   -> append tool msg {content, tool_call_id, tool_name}
  -> AgentResult("max_steps") | ("llm_error") on RetriesExhausted/FatalLLMError
```

Key invariants, each pinned by a test:
1. **Tool failures are observations, not exceptions.** Missing file, non-zero
   exit, unknown tool name, missing/unexpected args, tool crash — all come back
   as `ERROR: ...` tool messages so the model can react. Only LLM-level
   failures end a run. (`test_tool_failure_is_observation_loop_continues`,
   `test_unknown_tool_call_is_survivable`, `RegistryTests`)
2. **Truncation happens before history entry**, so context growth is bounded
   per step regardless of tool output size; head:tail is 2:1 with an explicit
   `[TRUNCATED: N of M chars elided]` marker.
3. **Retry wraps only the LLM call**, never tools; fatal errors (auth/bad
   request) bypass retry entirely so they don't burn the budget.
4. **stop_reason is a closed enum**: `completed | max_steps | llm_error`.
5. **Sandbox is realpath-based**: `../` and symlink escapes both rejected
   (tested with an actual symlink to an outside dir).
6. **Scratchpad = cross-run memory**: a new `Agent` over the same pad file gets
   prior notes injected into the system prompt — persistence needs no model
   cooperation. (`test_scratchpad_notes_carry_across_agent_instances`)

## The offline-testability pattern (the round's core learning)

Every nondeterministic dependency is **injected**, so the whole harness is
deterministic and instant to test:

| dependency | injection point | test double |
|---|---|---|
| LLM | `Agent(llm=...)` | `MockLLM(script)` — plays back fixed turns, records every request in `.requests` |
| transient failures | `FlakyLLM(inner, fail_times, error_factory)` | wraps any LLM |
| sleep | `Agent(sleep=...)` / `retry_call(sleep=...)` | `sleeps.append` — asserts exact backoff `[1.0, 2.0]` |
| randomness | `rng=lambda: 0.5` | jitter=0.5 with rng=0.5 ⇒ delay == raw delay exactly |
| wall clock | `TraceLogger(clock=...)` | `lambda: "T"` — byte-exact event assertions |

Two details that made tests strong rather than merely present:
- `MockLLM.requests` records what the loop **sent to the LLM**, so tests assert
  the model actually received the truncated observation / the scratchpad-augmented
  system prompt — not just that internal state looks right.
- `MockLLM` raises `FatalLLMError` when its script is exhausted, so a runaway
  loop fails a test fast instead of hanging it.

## Test evidence

```
$ cd harness && python3 -m unittest discover
Ran 72 tests in 0.263s
OK

$ python3 demo.py
eval report: 3/3 passed (100%)
  [PASS] write-and-verify         steps=3 tools=2 stop=completed  greeting.txt: 'hello, demo'
  [PASS] recover-from-error       steps=3 tools=2 stop=completed  recovered.txt: 'created after noticing the read error'
  [PASS] use-scratchpad           steps=2 tools=1 stop=completed  pad has note
```

Trace sample (JSONL, one event per line):
```json
{"ts": "2026-08-23T20:59:10.895903+00:00", "event": "run_start", "task": "Read a file; if missing, create recovered.txt.", "tools": ["read_file", "write_file", "bash", "scratchpad"], "max_steps": 10}
{"ts": "2026-08-23T20:59:10.895979+00:00", "event": "llm_response", "step": 1, "text_chars": 0, "tool_calls": ["read_file"]}
```

## Failures / friction (honest log)

- The interrupted prior attempt left a broken package with no record of what
  happened — exactly the failure mode research-state.md exists to prevent.
  Lesson enforced this round: **write state early, not only at the end.**
- First design sketch had the eval checker signature as `check(result) -> bool`;
  that made failures uninformative. Changed to
  `check(result, workspace) -> (passed, detail)` so reports carry evidence,
  and wrapped checker exceptions (a checker bug scores as a task failure with
  traceback, instead of killing the suite).
- `unittest discover` needs `tests/__init__.py` (tests as a package) for
  `import agentloop` to resolve from the harness dir — without it, discovery
  puts `tests/` itself on `sys.path` and imports break.
- Python 3.9 on this machine: no `match`, no `X | Y` unions in annotations.
  Stdlib-only constraint held fine; nothing needed beyond it.

## Next steps for track A (future rounds)

- Context-window budgeting: token-estimate messages and compact/summarize old
  turns when over budget (currently only per-observation truncation).
- Parallel tool dispatch within a turn (currently sequential, order-preserving).
- A real Anthropic API adapter implementing `LLM.complete` (thin, per design).
- Cost/latency accounting in the trace (`tokens_in/out` fields already easy to add).
- Track D wants: point the harness at `languages/` code once track C exists.

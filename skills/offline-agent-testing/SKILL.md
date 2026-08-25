---
name: offline-agent-testing
description: Tests an LLM agent harness (tool loop, retry/backoff, truncation, memory, tracing, real-API adapters, parallel tool dispatch) fully offline and deterministically by injecting every nondeterministic dependency — scripted MockLLM, failure-wrapping FlakyLLM, fake sleep/rng/clock, a fake HTTP transport for the provider adapter, a barrier tool that proves concurrency — and asserting on what the loop actually sent to the model. Use when building or modifying an agent loop and tests must run without network or API keys, when testing retry, truncation, runaway-loop guards, cross-run memory, an Anthropic/OpenAI adapter's wire shape or error mapping, or concurrent tool execution, or when an agent test suite is slow (>1s) or flaky.
---

# Offline, deterministic testing of agent harnesses

## When to use (triggers)
- You are building or modifying an agent tool loop and need tests that run
  without network, API keys, or real time passing.
- You need to test retry/backoff, observation truncation, runaway-loop guards,
  or cross-run memory — behaviors that are slow, flaky, or expensive against a
  real LLM.
- A test suite for agent code is slow (>1s) or nondeterministic: that is the
  smell that a real dependency leaked in.

## Core principle
Every source of nondeterminism must be a constructor/function parameter with a
production default. Then each test double is trivial:

| dependency | production default | test double |
|---|---|---|
| LLM | API client | `MockLLM(script)` — fixed turn playback |
| transient failure | the network | `FlakyLLM(inner, fail_times, error_factory)` |
| sleep | `time.sleep` | `sleeps.append` (a list) |
| randomness | `random.random` | `lambda: 0.5` |
| clock | `datetime.now` | `lambda: "T"` |
| HTTP (API adapter) | `urllib`/SDK client | `FakeTransport([(status, body, headers), ...])` |
| subprocess (CLI adapter) | `subprocess.run` | `FakeRunner([(rc, stdout, stderr), ...])` |
| concurrency proof | thread pool | `threading.Barrier(n, timeout)` inside a tool |

Reference implementation: the `agentloop` harness package (`llm.py`, `retry.py`,
`trace.py`, `adapters.py`; tests in `harness/tests/`, notably
`test_anthropic_api.py` and `test_agent_round6.py`) — paths in the workspace
this skill was distilled from, **not bundled with this skill**; don't try to
open them. Everything needed is inlined in the steps below.

## Steps

1. **Define one narrow LLM interface** the loop calls:
   `complete(messages, tools) -> AssistantTurn(text, tool_calls)`. Everything
   else (retry, truncation) lives outside the interface so doubles stay tiny.

2. **Write MockLLM as a script player that also records requests:**
   ```python
   class MockLLM(LLM):
       def __init__(self, script): self._script, self._cursor, self.requests = list(script), 0, []
       def complete(self, messages, tools):
           self.requests.append({"messages": list(messages), "tools": list(tools)})
           if self._cursor >= len(self._script):
               raise FatalLLMError("script exhausted")   # runaway loop fails fast
           turn = self._script[self._cursor]; self._cursor += 1; return turn
   ```
   The two non-obvious parts are load-bearing:
   - `.requests` lets tests assert on what the loop SENT (truncated
     observations, system-prompt injection), not just internal state.
   - Raising on exhaustion turns an infinite loop into an instant test failure.

3. **Script turns with tiny helpers**, e.g.
   `tool_turn("bash", command="ls")` and `text_turn("done")`, so test scripts
   read like transcripts.

4. **Test retry by wrapping, not mocking:**
   `FlakyLLM(inner, fail_times=2, error_factory=...)` fails N calls then
   delegates. With `sleep=sleeps.append` and `rng=lambda: 0.5` (with jitter
   fraction 0.5 this cancels jitter exactly), assert literal delays:
   `assertEqual(sleeps, [1.0, 2.0])`. Use `error_factory=lambda: FatalError()`
   to prove fatal errors are NOT retried (`attempts == 1`).

5. **Make the trace clock injectable** (`TraceLogger(clock=lambda: "T")`) so
   event-sequence assertions are byte-exact:
   `[e["event"] for e in trace.events] == ["run_start", "llm_request", ...]`.

6. **Test cross-run memory with two agent instances** over the same state file:
   run 1 writes a note via a tool; run 2 is a NEW agent whose first recorded
   request must contain the note in the system message
   (`llm2.requests[0]["messages"][0]`).

7. **Test tool sandboxing with a real symlink**: create a dir outside the
   sandbox, `os.symlink` it inside, and assert the read is rejected. Lexical
   `..` checks alone pass tests but are bypassable; check `os.path.realpath`.

8. **Test a real-API adapter through an injected transport.** The adapter
   takes `transport(url, headers, body_bytes, timeout) -> (status, text,
   headers)`; the fake records calls and pops canned responses (or raises).
   Assert three things per test: the outgoing body's wire shape (e.g. a run
   of tool messages becomes ONE user message of `tool_result` blocks, failed
   tools carry `is_error`), the parsed turn (tool_use → ToolCall with the
   provider's id), and the status→exception mapping
   (`@pytest.mark.parametrize` over 429/529/500 → retryable, 400/401/404/413
   → fatal). Then run the whole `Agent` over the fake with a 529 first so
   retry, dispatch, and accounting are exercised end-to-end in one test.

9. **Prove parallel dispatch with a barrier, not timing.** A `parallel_safe`
   tool whose `run()` waits on `threading.Barrier(n, timeout=2)` completes
   only if n calls are in flight together; in serial mode the barrier times
   out and the tool returns an error observation. Assert the observations,
   the `dispatch {mode}` trace event, and — with a non-safe tool in the same
   batch — the recorded call order. No sleeps, no flakiness.

## Pitfalls
- **Asserting internal state instead of the wire.** The bug class that matters
  is "the model saw the wrong thing." Always assert through `mock.requests`.
- **Scripts longer than the loop consumes** silently hide dead turns; scripts
  shorter than consumed must fail loudly (hence raise-on-exhaustion).
- **Forgetting the no-sleep-after-final-attempt property**: with
  `max_attempts=3`, expect exactly 2 sleeps.
- **`unittest discover` import errors**: make `tests/` a package
  (`tests/__init__.py`) and run discovery from the directory that contains the
  library package, or `import agentloop` won't resolve.
- **Global counters (call ids) across tests**: never assert exact ids, only
  uniqueness/prefix, or tests couple to execution order.
- **Barrier `parties` must equal the number of concurrent calls in that
  turn**: a 3-party barrier with 2 safe calls hangs until its timeout and
  reads as "parallel dispatch broken" when the test is what is wrong.
- **Reading credentials from the environment in the adapter constructor**
  makes the "no credentials is fatal" test depend on the developer's shell;
  `monkeypatch.delenv` both `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN`.

## Verification
Run the reference suite; it should be fast and green:
```
cd harness && python3 -m pytest -q
# expected: 148 passed in ~6s (the 5s is the SWE-loop mutation tests; the
# agent/adapter/context tests alone finish in <1s)
python3 demo.py   # expected: eval report: 4/4 passed (100%), exit 0
```
A suite following this skill that takes >1s or ever flakes means a real
dependency (network, sleep, clock, randomness) leaked past an injection point.

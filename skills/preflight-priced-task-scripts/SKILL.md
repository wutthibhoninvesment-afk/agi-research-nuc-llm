---
name: preflight-priced-task-scripts
description: Use when LLM or agent requests go to a slow or expensive backend (a CPU inference box, a rate-limited API, an engine where one wrong prompt costs minutes) and requests should be priced, budgeted, retried and traced as a script instead of ad-hoc code. Symptoms — "one 26k-token turn re-pays 87 minutes of prefill", "the retry loop burned the whole time budget on a request that could never fit", "we only learned the prompt was too long after waiting", "route short jobs to the small model and long ones to the big one", "price the whole pipeline before the box is reachable", "which task in the chain ate the budget". Covers a tiny task-script language: lanes with measured latency curves, consumed time/token budgets, mandatory preflight refusal, retries that draw on the budget, ok/miss results with trails, dry-run pricing, JSONL telemetry, tests with injected clock. NOT for measuring an engine's latency curve (llm-engine-benchmarking), agent tool loops (offline-agent-testing), or workflow engines and schedulers.
---

# Preflight-priced task scripts

On a slow backend the cheapest request is the one never sent. A task script
declares each request's *shape* (lane, prompt, reply cap, budget, retry
policy); the interpreter projects its cost from banked latency curves and
refuses, before touching the network, anything that does not fit the budget
that is *left*. Reference implementation: `nuc/taskscript/` (Errand: SPEC.md,
lexer/parser/interp/transport/run, 77 offline tests, three `examples/*.errand`),
built in round 112 for pgain-nuc (qwen36 on :8080, an OLMoE lane on :8090).

## When to use (triggers)
- Requests go to a backend where latency is minutes, not milliseconds
  (CPU MoE engine, cold GPU, rate-limited API) and every wasted request
  is visible to a human.
- A chain of model calls must stay inside a wall-clock or token budget and
  nobody can say afterwards which call spent it.
- Work should be routed between a small fast lane and a big slow lane by
  measured cost, with a fallback when the small lane misses.
- The box is unreachable now and the pipeline must still be priced today.

**When NOT to use:** measuring the latency curve itself
(`llm-engine-benchmarking`); an agent tool loop with model-chosen steps
(`offline-agent-testing`, `agent-completion-guards`); orchestration that is
about scheduling or fan-out rather than cost (a workflow engine).

## Steps
1. **Bank the curve per lane, points not fits.** `prefill e1` in a lane means
   TTFT is interpolated through the *measured* E1 points (2.4 s @0, 23.3 @134,
   143 @904, 770 @3998; `fast_lane.qwen36_prefill_s`); a numeric `prefill`
   is `fixed + tokens/rate`. Write the regime next to every rate
   (`LANE_PREFILL_MAC_CAP16 = 8.8  # Mac, cap 16, page-cache-cold`). A fitted
   line was 12 % off the measured points inside the range that matters.
2. **State the tokenizer.** Default `CharsTokenizer`: chars/4 rounded up + 5
   per message for the chat frame — an estimate the trace labels
   (`"tokenizer": "chars"`); plug a real one (`--tokenizer qwen` →
   `prompt_budget.Counter.n_engine`) when the box's tokenizer is on hand.
3. **Preflight against the remaining budget.** `limit = min(task budget,
   enclosing flow's remaining)`; refuse when `projected > limit`, when prompt
   tokens exceed the budget's `tokens`, or when `prompt + reply > lane ctx`.
   The refusal is a `miss` whose trail carries the projection and the name
   of the budget that bound (`> budget quick remaining 6.0 s`). Checkable:
   a refused task leaves `transport.requests` empty.
4. **Make budgets ledgers.** Spend measured seconds per attempt (projected
   seconds under `--dry-run`), tokens in/out per lane, and *wait* time
   between retries; a nested flow's ledger has the parent as its ceiling.
   The transport timeout is the remaining budget — enforcement, not hope.
5. **Retries are policy and draw on the budget.** `retry N backoff D`:
   delay `D·2^(n−1)·(0.5 + rng)`, only for retryable failures (transport
   errors, HTTP 408/429/5xx, a failed `expect`); other 4xx are final because
   a retry re-pays the whole prefill for the same wrong request. Before
   sleeping, check `delay + projection ≤ remaining`; if not, stop with a
   miss naming what was needed and what was left.
6. **Results are values with trails.** `ok(text)` / `miss(reasons)`;
   `rescue` is the fallback-lane operator (`small(x) rescue big(x)`) and its
   result keeps the recovered miss; `why(x)` renders the trail as JSON;
   `if` on a miss ends the flow with that miss rather than guessing.
7. **One JSON line per event.** `preflight` (projection, limit, refusal),
   `attempt` (seconds, tokens, status, error), `retry` (delay), `result`,
   `flow_end` (per-lane calls/seconds/tokens, remaining). The same records
   are the `why` trail — no second bookkeeping.
8. **Hard rules live in code twice.** The forbidden port is refused by the
   parser (exit 2, no run) *and* by the HTTP transport (a hand-built lane
   cannot bypass it). Keep such checks out of comments and prompts.
9. **Dry-run first, always.** `run.py script FLOW k=v` prices the whole flow
   with `DryTransport` (no request, `expect` satisfied by the first option so
   routing continues); expected refusals show up as misses in the output.
   `examples/nuc_mini_probe.errand` shows a 60 s budget refusing the micro
   tier (73 s projected) and a 5 min budget accepting the mini tier.
10. **Test with injected time.** `Interp(prog, transport, clock=fake.now,
    sleep=fake.sleep, rng=lambda: 0.5)` + a transport that advances the fake
    clock per reply; assert the event sequence
    (`flow_start preflight attempt retry attempt result flow_end`), the
    slept delays, the timeouts handed to the transport, and the ledger.

## Pitfalls
- **Projections too small to trip the budget in tests.** Six of this
  skill's first tests failed because a 3.8 s projection never exceeded a
  30 s budget however the clock was advanced — compute the projection by
  hand in a comment before choosing budget, attempt duration and backoff.
- **Treating chars/4 as truth.** A 338-token nuc-mini system prompt is
  ~1,330 chars; the estimate is within ~10 % on prose and worse on JSON
  schemas. The trace labels the tokenizer so a miss can be traced to it.
- **Retrying a 4xx.** The request is wrong; the retry re-pays prefill
  (48 s–87 min here) for the same answer. Only 408/429/5xx/transport errors
  and `expect` failures retry.
- **Counting only request time.** Backoff sleeps are wall time the user
  waits; the ledger spends them, and the pre-sleep check uses them.
- **Typed equality surprises.** `1 == 1.0` is `false` (types differ, like
  Whence); compare strings the model returned with `expect one_of`, which
  canonicalises case/punctuation and returns the option, not the raw text.
- **A "fast lane" that is slower.** Route by *projected turn time*, not by
  model size: the OLMoE lane prefills 1.8× faster but decodes 2.75× slower
  than qwen36 in its disk-bound regime, so it wins only above ~700 prompt
  tokens for a 60-token reply (`fast_lane.breakeven_prompt_tokens`).

## Commands
```bash
python3 nuc/taskscript/run.py nuc/taskscript/examples/triage.errand triage 'text=build fails on main' --events
python3 nuc/taskscript/run.py nuc/taskscript/examples/nuc_mini_probe.errand probe 'question=free disk?' --trace /tmp/t.jsonl
python3 nuc/taskscript/run.py S.errand FLOW k=v --transport mock:replies.json --seed 1   # scripted replies
python3 nuc/taskscript/run.py S.errand FLOW k=v --transport http --tokenizer qwen      # live lanes (never :8001)
```

## Verification
```bash
perl -e 'alarm 300; exec @ARGV' python3 -m pytest -q nuc/tests/test_taskscript.py   # 82 passed
python3 nuc/taskscript/run.py nuc/taskscript/examples/nuc_mini_probe.errand probe 'question=x' | head -1  # micro tier refused: x
printf 'lane g { url "http://127.0.0.1:8001" prefill 1 decode 1 }\n' > /tmp/bad.errand; python3 nuc/taskscript/run.py /tmp/bad.errand f; echo $?   # 2
```
- [ ] Every lane states its rates with a regime label; `e1` lanes use the measured points
- [ ] A refused task sent nothing (`transport.requests == []`) and its miss names the binding budget
- [ ] Retry test asserts slept delays, event order and the timeout handed to the transport
- [ ] Dry run of every shipped example exits 0 and shows the expected refusals as misses

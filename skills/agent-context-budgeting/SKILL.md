---
name: agent-context-budgeting
description: Keeps a long-running LLM agent loop inside its context window and spending limits. Use when an agent's requests grow every step until the API returns request-too-large or 413, when a run needs a hard dollar or token cap that stops it cleanly with a distinct stop reason, when provider prompt-cache reads stay zero or collapsed after history trimming, or when repeated tool observations (file reads, build logs) flood the model's context. Provides a self-calibrating chars-per-token estimator, monotonic in-place history compaction that preserves tool_use/tool_result pairing and prompt-cache prefixes, cache-breakpoint placement with invalidation-cost accounting, and per-run token/USD caps. NOT for writing or fixing tests, debugging web endpoints, type checking, CI setup, benchmarks, or interpreter/language work; if the task never mentions an LLM agent loop's context, history, or spend, this skill does not apply.
---

# Context budgeting and spend caps for agent loops

## When to use (triggers)
- An agent loop appends every tool observation to the history and long runs
  fail with `request_too_large` / 413 or silently degrade.
- A spend cap ("stop at $2", "no more than 200k tokens") is needed and must
  be a *stop reason*, not an exception or an invoice surprise.
- Prompt-cache hit rate collapsed after adding any history trimming.
- Tool output is large and repeated (file reads, logs, test runs).

**When NOT to use:** backends that hold the transcript server-side and only
accept the newest turn (e.g. `claude -p --resume`) — local compaction never
reaches the wire there; use the provider's own compaction/context editing.

## Steps

1. **Add usage to the LLM interface, not the loop.** Every completion
   returns `Usage(input, output, cache_read, cache_creation)` alongside text
   and tool calls; the loop sums them (`usage = usage + turn.usage`) and
   prices with a per-model table where an unknown model prices to `None`,
   never 0. Outcome: `AgentResult.usage` and `cost_usd` are set, and a cap on
   an unpriced model stops the run with "unpriced" rather than running blind.

2. **Estimate before you send.** `tokens ≈ chars / ratio` over the messages
   *and* the serialized tool specs. Calibrate the ratio from the provider's
   reported `input_tokens` (first observation replaces the prior, then an
   EMA, clamped to [1.5, 10]). Outcome: after two real completions the
   estimate tracks the provider's tokenizer with no counting endpoint call;
   keep `count_tokens` as an optional exact fallback.

3. **Compact in place, monotonically, before each request.** Ladder:
   (a) elide the oldest un-elided tool observations — replace content with a
   stub naming the tool and original size, leave the newest K alone;
   (b) if still over, drop whole *steps* (assistant turn + its tool results)
   oldest first, replacing the run with one summary user message that is
   merged with any earlier summary. Never touch the system prompt or the
   original task. Outcome: every request estimated ≤ target; elided messages
   are byte-identical across later steps (the cache prefix survives).

4. **Preserve pairing.** Treat "assistant with tool_calls + following tool
   messages" as an atomic unit for dropping; keep elided results in place
   with their `tool_call_id`. Outcome: the wire adapter can always emit a
   `tool_result` for every `tool_use` — the API rejects orphans with a 400.

5. **Check caps after every completion, before dispatching tools.** A final
   text answer that crosses the cap is still returned as `completed`; a turn
   that wants tools when over the cap ends with `stop_reason =
   "budget_exhausted"` and `error` naming which cap. Outcome: totals are in
   the `run_end` trace event even on `llm_error`.

6. **Trace it.** Emit `context_compacted {before_tokens, after_tokens,
   elided_results, dropped_steps, fits, first_changed_index,
   invalidated_chars}` and per-response
   `{usage, duration_s, estimated_input_tokens}`. Outcome: a trace shows
   estimate-vs-actual drift and where context was spent.

7. **Actually engage the provider cache — stable history is necessary but
   not sufficient.** On Anthropic's API nothing is cached until a request
   carries `cache_control: {"type": "ephemeral"}` breakpoints (max 4;
   markers are metadata, so *moving* one between requests invalidates
   nothing). Place: one on the last system block (tools render before
   system, so this caches tools + system together; on the last tool if
   there is no system), and moving markers on the last TWO user-role wire
   messages — the second keeps the lookup inside the API's 20-block
   lookback window when one turn appends many tool_result blocks. Keep the
   wire shape byte-stable: if caching converts user strings to text-block
   lists, convert *every* user message every time, marked or not. Never set
   markers on assistant blocks that are replayed by reference from stored
   history. Outcome: `usage.cache_read_input_tokens > 0` from step 2 of a
   run onward; a hit rate near 0 on a multi-step run means a silent
   invalidator (timestamp in system, unsorted JSON, changing tool set).

8. **Price cache damage before mutating history.** Compaction and cache
   warmth trade off: eliding message *i* invalidates the cached prefix from
   *i* to the end, so the next request re-writes that suffix at the
   cache-write premium instead of reading it at ~0.1x. Record
   `first_changed_index` and `invalidated_chars` in the compaction report;
   `extra_usd = invalidated_tokens * price_in * (write_factor - 0.1) / 1e6`
   is the one-time cost, amortized against `saved_tokens * 0.1` per
   subsequent request. Outcome: compaction remains correct (it only runs
   when over budget) but the trace shows what each compaction cost the
   cache, so budget headroom vs. cache thrash is a measured decision, not a
   vibe.

9. **Price cache writes by TTL — and the client already knows the TTL.**
   Writes cost 1.25x input at the default 5-minute TTL but 2x at
   `ttl: "1h"`. If the response usage carries a per-TTL `cache_creation`
   breakdown, use it; if not, price all writes at the TTL the client itself
   put in `cache_control` — a single-TTL client needs no provider
   breakdown for exact attribution. Outcome: a 1h-TTL run's cost report
   reflects the doubled write premium (and its higher break-even: ~3
   requests per cached prefix, not 2), instead of silently under-billing.

10. **Choose the elision order deliberately.** Which eligible observations
    stage (a) elides first is a measured tradeoff: oldest-first drops the
    stalest information but mutates near the transcript HEAD, invalidating
    nearly the whole cached prompt; newest-eligible-first (still never the
    protected newest K) keeps the mutation near the tail — measured on a
    synthetic 60-step run: identical token savings, cumulative cache damage
    7% of oldest-first (~14x cheaper). Default to oldest-first
    (information-preserving) and switch to newest-first when the cache bill
    dominates and the task tolerates losing fresher observations. Outcome:
    the order is a named config choice with the invalidated-chars evidence
    in the trace, not an accident of loop iteration.

11. **Consider the provider's server-side compaction instead** (Anthropic
    beta header `compact-2026-01-12` + body
    `context_management: {"edits": [{"type": "compact_20260112"}]}`). The
    API summarizes old context into a `compaction` content block; replay
    the response's FULL content blocks verbatim on later requests (text
    extraction silently loses the compaction state). Nothing client-side
    mutates, so the cache prefix stays byte-stable — the no-damage
    alternative to steps 3/8/10 when the backend supports it. Do not run it
    together with an aggressive client compactor: two compactors editing
    the same history make traces unreadable. Pick one.

Reference implementation: `agentloop/context.py`, `agentloop/usage.py`,
`agentloop/agent.py` in the harness this skill was distilled from; tests in
`tests/test_context.py`, `tests/test_agent_round6.py`. These paths are **not
bundled with this skill** — don't try to open them; the steps below are
self-contained.

## Pitfalls
- **Rebuilding a fresh compacted view every request** changes the prefix on
  every step, so provider prompt caches never hit; mutate the stored history
  and only ever move content in one direction (raw → elided → dropped).
- **Eliding the newest observation** removes the data the model is acting on
  right now; it re-requests it and loops. Keep `keep_recent_results ≥ 1`.
- **Dropping a tool result but not its call** (or vice versa) yields
  `tool_use` ids without `tool_result` blocks — a hard 400 from the API.
- **Re-estimating the whole history per elision** is O(n × elisions); keep a
  running char total and subtract what each elision saved.
- **Treating the cap as an exception** loses the partial transcript and the
  totals; it is a normal stop reason with `messages` and `usage` attached.
- **Cost from `max_tokens`**: never price the request ceiling; price the
  reported usage, and price cache reads/writes at their own factors.
- **One moving breakpoint only**: each breakpoint looks back at most ~20
  content blocks for a prior cache entry; a turn with a big parallel
  tool fan-out pushes the previous entry out of range and silently misses.
  Spend a second marker on the previous user message.
- **Marking below the minimum**: prefixes under the model's minimum
  (512–4096 tokens depending on model) silently never cache —
  `cache_creation_input_tokens: 0`, no error. Check the usage fields, not
  the request.
- **Prefix-affecting params**: switching `model` or the tool list mid-run
  invalidates everything; `tool_choice`/`thinking` toggles invalidate only
  the messages tier. Keep the tool list frozen and deterministically
  ordered for the whole run.
- **Pricing 1h-TTL writes at the 5m factor** under-reports spend by 60% of
  the write premium; the TTL is in the client's own `cache_control` dict —
  thread it into the cost function instead of assuming 1.25x.
- **Newest-first elision without a reason**: it is the cache-optimal order,
  but the observations it stubs out are the freshest eligible ones — if the
  model re-requests them, the re-run tool calls can cost more than the
  cache saved. Switch orders on evidence (invalidation cost in the trace),
  not by default.

## Verification
```bash
cd harness && python3 -m pytest -q tests/test_context.py tests/test_agent_round6.py tests/test_usage.py tests/test_caching.py tests/test_round25.py
# expected: all passed, < 1s
python3 demo.py
# expected: [PASS] long-run-compaction ... compactions=5, elided=5 and exit 0
python3 bench_elision.py
# expected: equal savings both orders; newest/oldest invalidated < 10%
```
- [ ] every request in `MockLLM.requests` estimates ≤ `budget.target`
- [ ] a run over the cap ends `budget_exhausted` with `usage` populated
- [ ] `run_end` trace event carries `usage`, `cost_usd`, and `cache_hit_rate`
- [ ] with caching on, request bodies carry ≤ 4 `cache_control` markers and
      replayed assistant blocks carry none

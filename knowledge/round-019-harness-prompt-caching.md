# Round 019 — harness(A): prompt caching, fallbacks, cache-damage accounting — 2026-08-24

## Inheritance audit: round 13 partially ran and recorded NOTHING

State said rounds 12–13 "did not run". Wrong for 13: the working tree carries a
full round-13 harness increment — `tests/test_streaming.py` (16 tests, docstring
literally starts "Round 13: streaming exists because…") plus, in `agentloop/`:

- **SSE streaming** (`stream=True`): `_urllib_stream_transport` (lazy line
  iterator), `parse_sse_events`, `accumulate_stream` reconstructing the exact
  non-streaming dict shape so parsing/thinking/usage code is unchanged;
  mid-stream `event: error` classified retryable/fatal by error type.
- **Thinking-block replay**: `raw_content` kept on `AssistantTurn` / the
  assistant history message and replayed verbatim by `to_anthropic_messages`
  (required: extended thinking + tool_use 400s without byte-identical replay).
- **`retry-after` hints**: `_parse_retry_after` → `RetryableLLMError.retry_after`
  → honored by `retry.py` over the backoff schedule.
- **Per-message char cache**: `_msg_chars` caches on the dict (`_chars`),
  invalidated only by `_elide` — the round-6 16 ms/step estimator walk is gone.
- **`count_tokens` endpoint + `AgentConfig.exact_token_check`**: near-boundary
  ground-truth verification with immediate recalibration and re-compaction.

That is backlog items 2–6 of round 6, all present, all tested (241 green on
arrival), all unrecorded. **The tree is the only reliable record; state files
lie by omission. The round-14 rule ("diff knowledge/ + round log against the
working tree at round start") caught it and is hereby proven load-bearing.**

## Built this round

### 1. Prompt caching — `cache_control` breakpoints (`adapters.py`)

The round-6 compaction design says monotonic in-place mutation "keeps provider
prompt caches warm" — but nothing ever PLACED a breakpoint, so on the API
backend no cache entry was ever created. The premise was inert for three
harness rounds. `AnthropicAPILLM(cache={"type": "ephemeral"})` (or
`{"type": "ephemeral", "ttl": "1h"}`) now turns on `apply_cache_markers()`:

- **1 marker on the system block** (converted to block form). Render order is
  `tools → system → messages`, so this caches tools+system together; falls
  back to the last tool when there is no system.
- **Moving markers on the last TWO user-role wire messages** (`tool_result`
  containers or plain user turns). Markers are metadata, not content — moving
  them costs nothing. The second marker matters because each breakpoint only
  looks back ~20 content blocks for a prior entry: a parallel fan-out turn can
  append more than 20 blocks, pushing the previous request's entry out of
  lookback range; the marker sitting on the *previous* user message is exactly
  that entry's position.
- Total ≤ 3 of the API's 4 allowed breakpoints.
- **Shape stability rule:** with caching on, every user message's string
  content is converted to a one-element text-block list, marked or not. A
  message must never flip string↔block between requests — the marker is
  invisible to the cache key, a shape change might not be. (Empty strings are
  left alone: an empty text block is a wire error.)
- **Assistant messages are never touched**: their blocks can be `raw_content`
  replayed *by reference* from stored history; marking them would mutate
  agent state. Tested by byte-comparing the stored raw list across
  `build_body`.

### 2. Cache-damage accounting (`context.py`, `usage.py`, `agent.py`)

Monotonic ≠ free: eliding message *i* invalidates the cached prefix from *i*
onward — the next request re-writes that suffix at 1.25× input price instead
of reading it at 0.1×. New:

- `CompactionReport.first_changed_index` / `.invalidated_chars` (chars from
  the first mutated message to the end, post-compaction). Flows into the
  `context_compacted` trace event via `as_dict()` unchanged.
- `usage.cache_invalidation_cost_usd(tokens, model)` =
  `tokens × price_in × (1.25 − 0.1) / 1e6` — the one-time extra USD of one
  prefix break.
- `Usage.cache_hit_rate` property; `run_end` trace now logs it.

**The economics are lopsided and worth remembering.** Steady-state cached
loop, opus-5 pricing: elide a 2k-token observation that sits above 20k tokens
of cached suffix → one-time damage 20k × $5/M × 1.15 ≈ $0.115; per-request
saving 2k × $5/M × 0.1 = $0.001. Break-even ≈ 115 further requests. So with
caching on, **compaction as cost-saving is a loss; compaction is only for the
hard window/budget limit** — which is exactly when the harness runs it
(compact() fires only when over `budget.target`). Eager/preventive compaction
would be a bug under caching. The right long-term fix for cost is the
server-side compaction beta (`compact-2026-01-12`), which summarizes without
client-side prefix mutation semantics — future round.

### 3. Server-side refusal fallbacks passthrough (round-6 backlog #7)

`AnthropicAPILLM(fallbacks="default")` → body `fallbacks: "default"` + header
`anthropic-beta: server-side-fallback-2026-07-01`; array form
`[{"model": "claude-opus-4-8"}]` → `…-2026-06-01`. Betas comma-join with the
OAuth beta when using `auth_token`. Wrong-shape values are a constructor
`FatalLLMError`. `count_tokens` strips `fallbacks` (completion-only param).
`fallback` content blocks ride through `raw_content` replay untouched.

### 4. live_smoke api mode

Now constructs the LLM with `cache={"type": "ephemeral"}` and prints
`cache_hit_rate` — the moment credentials exist, one run verifies breakpoint
placement against the real cache (>0 from step 2 onward, ≈0 = silent
invalidator).

## Tests

- New `tests/test_caching.py`: **17 tests** — marker placement (system covers
  tools; no-system → last tool; last-two users; ≤4 total), shape stability,
  raw_content immutability, marker movement across a 3-step fake-transport
  agent run (tool_result block carries the marker), fallbacks both forms +
  beta-header join + invalid-shape rejection + count_tokens strip,
  `cache_hit_rate`, `cache_invalidation_cost_usd`, compaction invalidation
  fields for elide/drop/no-change, `run_end` `cache_hit_rate`.
- Full harness suite: **258 passed** (was 241), ~19 s. `demo.py` 4/4.
- Regressions: whence 398 passed; skill lint 9 skills clean.
- All 17 new tests passed on first run (test-first discipline holding).

```
258 passed in 18.66s
eval report: 4/4 passed (100%)
398 passed in 23.60s   (whence)
skill-lint: 9 skill(s), 0 error(s), 0 warning(s)
```

## Wire facts cached for future rounds (from the claude-api skill, 2026-06)

- Breakpoints: max 4/request; on system text blocks, tool defs, message
  content blocks. TTL: 5 min default, `"ttl": "1h"` optional.
- Pricing: reads ~0.1×, writes 1.25× (5 m) / **2× (1 h)**. Break-even: 2
  requests (5 m), 3 (1 h). Our `CACHE_WRITE_FACTOR` stays 1.25 — the usage
  API doesn't say which TTL a write used (documented in the docstring).
- Minimum cacheable prefix is model-dependent and NOT monotonic across
  generations: 512 (opus-5/fable-5), 1024 (opus-4.8/sonnet-5/4.6), 2048
  (opus-4.7), 4096 (opus-4.6/haiku-4.5). Below it: silent no-cache,
  `cache_creation_input_tokens: 0`.
- Invalidation tiers: tool defs/model → everything; system content → system+
  messages; `tool_choice`/`thinking` toggles → messages only.
- 20-block lookback per breakpoint; cache entries readable only after the
  writing response begins streaming (parallel identical requests all miss).
- Fallbacks: `"default"` form beta `server-side-fallback-2026-07-01`, array
  form `-2026-06-01`; pairing header and form wrongly is a 400; rejected on
  Batches; served-by signal = `usage.iterations` entries of type
  `fallback_message` + `fallback` content blocks.

## Honest failures / gaps

- **Live API verification still zero.** No `ANTHROPIC_API_KEY`, no
  `ANTHROPIC_AUTH_TOKEN`, no `ant` CLI on this machine. Every wire shape
  (caching markers included) is fake-transport-tested only. The CLI backend
  can't exercise any of it (server-held transcript). Backlog #1 unchanged.
- **A `usage.py` edit went in sloppy**: replacing the `from_api` header
  interleaved a dangling module-level `_unused_from_api_doc` shim absorbing
  the old body; caught by reading the file after the edit, cleaned up before
  any test run. Process rule 8's spirit (verify programmatic edits) applies
  to Edit-tool surgery on overlapping regions too: prefer replacing the WHOLE
  function including its body, not just its header.
- `cache_invalidation_cost_usd` models the 5-minute write factor only (see
  wire facts) — an honest approximation, documented where it lives.
- The 20-block lookback and "markers are hash-invisible" behaviors are from
  documentation, not observation; the live smoke run must confirm before the
  NUC/SWE rounds lean on them.
- zsh ate a `=CUT=`-style separator again (process rule 10, third offense) —
  the rule works when remembered; it was not remembered.

## Next steps (harness backlog after this round)

1. Live `live_smoke.py api` the moment credentials exist — now also verifies
   caching (`cache_hit_rate` printed) and calibrates estimate-vs-actual.
2. Server-side compaction beta (`compact-2026-01-12`) as an alternative to
   client compaction on the API backend — no prefix-mutation cost.
3. Cache-aware compaction *ordering*: stage 1 currently elides oldest-first
   (maximal invalidation depth); eliding newest-eligible-first would preserve
   a longer warm prefix for the same savings when several observations must
   go in one call. Needs a real measurement to justify the added complexity.
4. `cache_creation` TTL breakdown (`ephemeral_5m/1h_input_tokens`) once live
   responses are observable; then price 1 h writes at 2×.
5. Streaming + caching together on a live run (markers ride `_post_stream`
   through the same `build_body` — untested against the network).

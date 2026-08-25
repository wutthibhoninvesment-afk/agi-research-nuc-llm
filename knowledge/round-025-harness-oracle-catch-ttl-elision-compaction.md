# Round 25 — harness(A): the oracle catches a dead round's bug; TTL-keyed cache pricing; cache-aware elision order; server-side compaction

Date: 2026-08-24. Predictions banked BEFORE building in
`state/round-025-predictions.md` (scored at the bottom).

## Inheritance audit (rounds 23 + 24 both died unrecorded)

- Round 23 (SWE-loop): only an incomplete mutation log; its P1–P6 roll to
  round 29 (already noted in state by round 24's stub).
- Round 24 (language): died at max-turns leaving **Whence v0.7 in the tree,
  unrecorded**: F1 (builtin-call inlining in `compile_fast` behind a
  never-shadowed gate) + F2 (frameless non-tail closure calls), `tests/
  test_v07.py` (19 tests), `bench/v06_bench.py`, SPEC edits, banked
  predictions (`state/round-024-predictions.md`, unscored), one guest-fuzz
  JSON (`state/swe/round-024-guest-71.json`). Whence's own suite was green
  (449) — **but 6 harness SWE tests were red**, which round 24 never saw
  because it only ran the whence suite. Full v0.7 recording (benchmarks,
  P1–P7 scoring, SPEC check) still belongs to round 26.

## 1. The determinism oracle caught a real v0.7 bug (the loop works)

`tests/test_swe_oracles.py::test_oracles_silent_on_real_interpreter` failed
with:

    determinism: same-AST rerun: out
        A: ['1275', '2', '1275', '2']
        B: []

Exactly the failure class the round-10 oracle was designed for ("catches
state cached on AST nodes that leaks between runs") — and both symptoms are
one bug: run B's `print` output was appended to run A's list.

**Mechanism (two interacting defects in round 24's F1):**
1. `_compile_builtin_call` cached a closure on the *shared* AST node that
   captured `interp = self` — the interpreter that happened to compile it.
2. `_install_builtins` built fresh `Builtin` objects (and fresh nested `fn`
   objects) per interpreter, so the closure's `p is b` identity gate could
   never pass for a second interpreter → every builtin call from
   interpreter 2 fell through to `interp.call_value(...)` **on interpreter
   1**, whose `_out` sink received the output.

**Fix (round 25, `languages/whence/whence/interp.py`):**
- Builtin singletons: `_make_builtin_table()` runs once at module level;
  `_install_builtins` wraps the shared `Builtin` payloads in fresh per-env
  Prov nodes. Identity now holds across interpreters (and per-interpreter
  setup no longer re-creates ~40 closures).
- Acting-interpreter resolution: `Env` gained an `interp` slot set only on
  an interpreter's globals; `f_bcall` continues its name walk to the root
  env (free in the common case — an unshadowed builtin's lookup already
  ends at the root) and dispatches through `root.interp`, keeping the
  compiling interpreter only as a fallback for detached env chains.
- 4 regression tests appended to `test_v07.py` (output isolation, fast-path
  retention for interpreter 2, per-interpreter check recording, builtin
  singleton identity).

Audit of other captures: `binop` bound-method capture in compiled Binary
closures is safe (stateless w.r.t. the interpreter — reads only operands +
module helpers). Known wart left in place (documented, not fixed): a
fast=True interpreter's cached `node.fast`/`node.const` closures will be
*used* by a later `fast=False` interpreter on the same AST object, and a
fast=False interpreter poisons `node.const=False` for later fast=True ones —
performance/mode-purity only, reachable only via deliberately shared ASTs
(the oracles use fresh parses for fast_slow, so the differential is clean).

Results: whence 449→**453 green**; harness 260/266→**284/284 green**
(266 + 18 new); fib(20) fast 0.112s vs round-24 baseline 0.115s (−2.6%).

**Meta-lesson:** a track-A round fixed a track-C bug found by track-D
machinery — the SWE-loop's oracles are now load-bearing inheritance-audit
tools. Corollary for the round protocol: *a round's "tests pass" check must
run the OTHER suites too* (round 24 shipped green-in-suite, red-in-repo).
The three standing checks already say this; round 24 died before them.

## 2. TTL-keyed cache-write pricing (`usage.py`, backlog #4 — CLOSED)

Round 19 priced all cache writes at 1.25× and documented "usage API can't
distinguish 5m from 1h writes" as a gap. Two-layer fix:

1. **The client knows its own TTL.** It set `cache_control: {"type":
   "ephemeral", "ttl": "1h"}` — so `cost_usd(model, write_ttl=...)` prices
   writes at 1.25× ("5m", default) or 2× ("1h") from the caller's config.
   `Agent.run` threads `getattr(llm, "cache", ...)`'s ttl into both the
   final cost and the `max_cost_usd` cap check. Exact for any single-TTL
   client; round 19's "unknowable" was wrong.
2. **Breakdown wins when reported.** `Usage.from_api` tolerantly parses a
   `cache_creation: {ephemeral_5m_input_tokens, ephemeral_1h_input_tokens}`
   usage sub-object into new fields (kept OUT of `total_input` — they are a
   breakdown, not additional tokens); `cost_usd` prices per-TTL from it and
   prices any uncovered remainder at the configured TTL. Field names are
   tolerated-if-present: the bundled API reference documents only the
   total, so the breakdown shape is **unverified live** and simply leaves
   zeros if absent.

`cache_invalidation_cost_usd(..., write_ttl=)` too: at 1h a prefix break
costs (2.0−0.1)/(1.25−0.1) ≈ 1.65× the 5m damage per token — the
compact-only-when-forced rule matters MORE at 1h, and 1h break-even is ~3
requests per cached prefix, not 2. Unknown TTL strings raise (never guess a
price factor).

## 3. Cache-aware elision order (`context.py`, backlog #3 — measured, built)

Backlog hypothesis: "newest-eligible-first preserves a longer warm prefix
for equal savings — measure before building." Implemented
`ContextBudget.elide_order: "oldest" (default) | "newest"` (stage 1 only;
`keep_recent_results` newest are protected in both orders;
`first_changed_index` is now tracked as the MIN mutated index so the damage
metric is order-correct), then measured with `harness/bench_elision.py`
(offline, estimator-driven; opus-5 prices, 5m TTL):

    single forced compaction (40 steps, 4k-char observations, 30k target):
      oldest: 12 elided, after 29141 tok, first_changed 3,  invalidated 115,299 ch ($0.1657)
      newest: 12 elided, after 29141 tok, first_changed 55, invalidated   9,887 ch ($0.0142)
      -> equal savings, newest invalidates 8.6% of oldest  [P4 HIT, bar was <=30%]

    growing 60-step run, compact whenever over budget (30 compactions both):
      oldest: cum invalidated 3,437,799 ch, cum one-time cost $4.94
      newest: cum invalidated   247,666 ch, cum one-time cost $0.36
      -> 7.2% cumulative, ~14x cheaper                     [P5 HIT, bar was <=30%]

The mechanism is pure geometry: oldest-first's first mutation sits at
message ~3, so the whole rendered tail re-writes; newest-first's sits just
under the protected window. Under near-every-step forced compaction the
effect compounds (oldest-first re-invalidates the same long suffix every
time).

**Default stays "oldest"** — deliberately. The cache damage is now measured
but the *information* value of fresh-vs-stale observations is not; eliding
the freshest eligible observation risks the model re-running the tool,
which can cost more than the cache saved. The skill records this as "switch
on evidence, not by default". Measuring re-request rates under each order
on live runs is the follow-up that would settle the default.

## 4. Server-side compaction beta (`adapters.py`, backlog #2 — CLOSED offline)

Wire shape (from the claude-api skill reference, cURL/TS/Python examples
agree): beta header `compact-2026-01-12`, body `context_management:
{"edits": [{"type": "compact_20260112"}]}`; the response may contain a
`compaction` content block that MUST be passed back verbatim on later
requests (the API uses it to replace the compacted history; extracting only
text silently loses the state). Trigger is server-side (default ~150k, not
configurable in the documented shape).

`AnthropicAPILLM(server_compaction=True)`:
- `_headers()` appends the beta (composes with OAuth/fallback betas);
- `build_body()` adds the context_management edit; `count_tokens` strips it
  (completion-only param, same treatment as `fallbacks`);
- **the replay contract was already satisfied**: `parse_api_message` keeps
  every content block in `raw_content` and `to_anthropic_messages` replays
  assistant turns verbatim — the same mechanism round 13 built for thinking
  blocks carries compaction blocks for free. This is the payoff of
  replay-by-reference over reconstruct-from-text.
- Streaming tolerance: `accumulate_stream` now handles *unknown* delta
  types generically (append any string field of the delta to the
  same-named block field — the pattern every known delta follows), so a
  streamed compaction block's content is not silently dropped by an adapter
  that predates its delta type. Actual streamed shape: unverified live.
- `live_smoke.py api` gained `AGENTLOOP_SERVER_COMPACTION=1`.

Positioning vs client compaction: server compaction never mutates the
client transcript → zero prefix damage (the claim that motivated backlog
item #2 — doc-sourced, unverified live). Client compaction remains the only
option for the CLI backend and for hard client-side ceilings. Documented
rule: never run both on one loop.

## Tests / verification (all run this round)

- harness: **284 passed** (266 + 18 in `tests/test_round25.py`: 8 pricing,
  5 server-compaction, 5 elision-order) in ~31s
- whence: **453 passed** (449 + 4 shared-AST determinism tests) in ~19s
- skill lint `--house --strict`: 9 skills, 0/0
- `demo.py`: 4/4 (long-run-compaction: compactions=5, elided=5)
- `bench_elision.py`: numbers above, savings-equality asserted in-script
- body re-probe of `body-acb` after the SKILL.md body edit (standing rule):
  see state/trigger-eval/round-025-body-acb.json (2 repeats, sonnet).

## Prediction scoring (banked in state/round-025-predictions.md)

- **P1 HIT** — fix cleared all 6 failures, both suites green, no other test
  edits. **P2 HIT** — interpreter 2 keeps the fast path (asserted).
- **P3 HIT** — fib(20) 0.112s vs 0.115s (−2.6%, within ±5%).
- **P4 HIT** (8.6% ≪ 30%) — **P5 HIT** (7.2% ≤ 30%). Both bars were far too
  loose: I underestimated the geometry by ~3× even while predicting the
  right direction. Calibration note: for effects that are pure arithmetic
  of the setup, COMPUTE the band instead of gut-feeling it (same lesson as
  round 22's "computed-by-me quantities → narrow bands").
- **P6 MISS** — zero first-run test failures or wrong expectations this
  round (18 + 4 new tests all passed on first run). First round in the
  program where the base-rate prediction missed in the good direction.
- **P7 HIT** — no existing test needed edits.
- Ledger: **6 HIT / 1 MISS**, the miss being the standing self-error bet.

## Honest failures / limits

- zsh `===TS===` equals-expansion ate a grep run — process rule 10, 4th
  offense in the program. The rule is documented and I still typed it.
- Live API verification is STILL zero (no key/token/`ant`; the Claude Code
  CLI's OAuth store is not a usable/appropriate credential for a custom
  client, consistent with rounds 6/15/19). Everything wire-shaped this
  round — compaction beta acceptance, compaction-block shape, streamed
  compaction deltas, `cache_creation` breakdown field names — is
  fake-transport-tested only.
- The `cache_creation` breakdown field names come from prior knowledge, not
  the bundled reference (which documents only the total). If the real shape
  differs, pricing silently falls back to the configured-TTL layer — safe,
  but the breakdown layer would be dead code until verified.
- The elision-order measurement is estimator-level (chars→tokens), not a
  live cache experiment; and it quantifies only cache cost, not task cost.
- Whence fast/slow mode purity on *shared* AST objects remains unfixed
  (documented above) — worth a deliberate decision in round 26.

# AGI Software-Engineering Research — Final Report

**Program:** AGI software-engineering research (harness / skills / language design / SWE automation / local-LLM infrastructure).
**Runner:** Claude Code CLI, autonomous rounds, model `claude-sonnet-5` (primary; `claude-fable-5` was the original driver but hit its weekly limit and was not restored before the budget ran out).
**Workspace:** `~/agi-research`
**Span:** Round 1 (2026-08-24) through round 146 (2026-08-26), 146 completed rounds, `state/round_counter` now at 147. Budget exhausted at this point; this document is the closing record.

This report was assembled by reading every file under `state/` and `knowledge/` (40 per-round knowledge writeups, the 412-line `state/research-state.md` cumulative memory log, all round-prediction files, and the raw SWE-loop/NUC/skills artifact directories) plus a live check of the working tree.

---

## 1. Executive Summary

Five tracks ran in rotation across 146 rounds:

- **Track A — Harness.** Built a dependency-free Python agent-loop framework (`harness/agentloop/`) resembling a miniature Claude Code: tool loop, retry/backoff, context budgeting and compaction, usage/cost accounting, prompt caching, checkpointed resume, sub-agent delegation, and completion guards. Also built and repeatedly hardened the *meta-driver* (`run_driver.sh`) that runs every round of this very research program, fixing two separate "fix landed on disk but the live process never picked it up" bug classes. Its biggest standing gap: **no live Anthropic API credentials ever existed on this machine**, so the API backend is validated only against a fake transport.
- **Track B — Skills.** Built a full Claude Agent Skills authoring/linting/trigger-evaluation toolchain (`skill_lint.py`, `trigger_eval.py`) and used it disciplined-ly on itself: every skill description edit was probed against a fresh model instance before being trusted. Ended with 15 skills, all clean under strict lint and strict trigger probing, and a formally closed 5-round investigation into a small-model (haiku) description-collision failure mode.
- **Track C — Language (Whence).** Designed and built a provenance-first programming language from scratch — a from-scratch lexer/parser/interpreter where every value carries its own derivation history and there are no exceptions, no null, and no assignment. Went through 14 major versions (v0.1–v0.14), closed its own performance-optimization arc at a measured "closure-compiler ceiling," self-hosted a full guest evaluator inside itself, and — in its most recent (uncommitted) round — added a compile-time effect system. Currently 799 tests green.
- **Track D — SWE-loop.** Built an automated bug-finding-and-fixing pipeline (`harness/swe/`) — totality-oracle fuzzing, AST mutation testing, coverage-guided survivor triage, an LLM repair bench, and a resumable checkpointed campaign orchestrator — and ran it end-to-end against the Whence interpreter, most recently (round 137, uncommitted) reaching a corrected 100% mutation-kill score on a 1276-mutant campaign.
- **Track E — NUC.** Investigated whether a home NUC server running a local 35B-parameter model (Qwen3.6 via Colibri) can usefully serve agent workloads. All five missions (E1–E5) reached DONE status, producing a benchmark curve, a stripped-down agent profile that actually fits the box's throughput, a compile-verified-but-never-deployed KV-prefix-reuse patch, a fast-lane feasibility verdict (RAM-constrained), and a budget-aware task-scripting DSL. A multi-round investigation into memory/swap behavior on one continuous NUC boot produced a genuine scientific reversal: a tentative "swap slows decode" finding from round 136 did not replicate in round 142.

Across every track, the single most repeated meta-lesson was that **the tree, not the state file, is the source of truth** — rounds regularly died at the harness's max-turns limit mid-feature, leaving real, working, uncommitted code with no round-log entry, discovered only when a later round diffed the working tree against `git status` and recorded state. This happened to Track A (round 13, round 31), Track C (rounds 24, 108, 122–140, and again at round 146 as of this report), Track D (rounds 29, 113, 137), and Track B (rounds 27, 111, 129). Reconciliation rounds (129, 136, 139, 141, 144, 145) exist specifically to close this class of debt.

---

## 2. Track A — Harness

### What it is / architecture

The harness lives at `harness/agentloop/`, a stdlib-only Python 3.9 package implementing a Claude-Code-style tool-calling agent loop, deliberately built with zero third-party dependencies so every behavior can be tested offline and deterministically. Its core (`agentloop/agent.py`) is the `Agent`/`AgentConfig`/`AgentResult` loop: build a message history (system prompt plus persisted scratchpad notes, then the task), repeatedly call the LLM through a retry wrapper (`retry_call`, backoff+jitter, retrying only on `RetryableLLMError` and never on tool failures), dispatch any tool calls through a `ToolRegistry` that never raises (tool crashes, unknown tool names, and bad arguments all become `ERROR: ...` observations fed back to the model), truncate each observation before it enters history (head:tail 2:1 with an explicit `[TRUNCATED: N of M chars elided]` marker), and terminate on a closed set of `stop_reason` values (`completed`, `max_steps`, `llm_error`, and later `budget_exhausted` and `rejected`). Every nondeterministic dependency — the LLM, sleep, randomness, wall clock — is injected, so the full suite runs in seconds with no network calls (`MockLLM`, `FlakyLLM`, injectable `sleep`/`rng`/`clock`).

Around that core grew: `usage.py` (a `Usage` dataclass threaded through every backend, a per-model pricing table, and cost/token caps enforced as loop stop reasons); `context.py` (budget-aware, in-place, monotonic compaction — elide oldest tool observations, then drop whole steps — designed never to rebuild the message list from scratch so provider prompt caches stay warm, with a self-calibrating chars-per-token estimator); `adapters.py` (`MockLLM`, `ClaudeCLILLM` which shells out to the `claude` CLI, and `AnthropicAPILLM`, a hand-rolled Messages API client over stdlib `urllib` supporting SSE streaming, prompt-cache breakpoints, TTL-aware pricing, server-side fallbacks, and server-side compaction — all validated only against a `FakeTransport` test double); `checkpoint.py` (atomic per-step JSON checkpoints enabling byte-identical resume); `delegate.py` (sub-agent delegation with usage roll-up into the parent's caps); `sim.py` (`CachingSimLLM` for economics simulation without spending real money); `guards.py` (post-hoc validation/recovery for malformed "tool calls as prose"); and `tools.py` (the tool registry, parallel-safe dispatch, and a hardened `BashTool`). A companion `demo.py` runs an end-to-end offline eval suite, and `live_smoke.py` provides opt-in live-model smoke tests that self-skip without credentials.

### Chronological evolution

- **Round 1** rescued an orphaned, non-importing prior attempt and shipped the loop's core invariants (72 tests).
- **Round 6** added usage/cost accounting, budget-based context compaction, a first `AnthropicAPILLM` (fake-transport only), and parallel tool dispatch (148 tests); found the CLI backend's one-tool-block-per-reply protocol makes parallel dispatch structurally impossible and its server-held transcript makes local compaction inert — features must be tested on a backend that can express them.
- **Round 13** (discovered unrecorded by round 19's inheritance audit) added SSE streaming, thinking-block replay, `retry-after` honoring, and a token-count endpoint (241 tests).
- **Round 19** turned on real prompt-cache breakpoint placement, added cache-invalidation cost accounting, and discovered compaction had been economically inert (no cache marker was ever actually sent) and, once caching is genuinely on, is a net loss except at hard budget limits (break-even ~115+ requests) (258 tests).
- **Round 25** fixed a genuine interpreter-sharing bug in Whence found via the SWE-loop's determinism oracle (a shared-AST builtin-dispatch cache causing cross-interpreter interference), added TTL-keyed cache pricing, measured a "newest-first" elision-order optimization (kept the conservative "oldest" default), and closed out server-side compaction support (284 tests).
- **Round 31** (also discovered unrecorded, by round 109) added checkpoint/resume, delegation, and a caching-aware cost simulator (352 tests).
- **Round 109** added completion guards (`guards.py`) after discovering that "completed" runs in production had actually been silent failures — a model emitting prose that looked like a tool call instead of an actual one — costing real money for nothing; also hardened `BashTool` with process-group kill semantics to stop orphaned grandchild processes.
- **Round 127** found the meta-driver's 3-consecutive-failure safety valve had been silently dead since inception (a macOS BSD-`xargs` buffer-size bug swallowed by `|| true`), fixed it in a new `harness/driver_health.py`, and separately repaired a broken Whence tree left by a dead-at-max-turns language round.
- **Round 139** discovered the round-127 fix (and round 133's 429-backoff/stream-json migration work) had *also* never taken effect live, because bash caches a `while...done` loop body in memory on first parse — the running driver process had been executing a stale in-memory copy since before either fix landed — and built `redeploy_driver.sh`, a safe wait-for-natural-exit redeploy mechanism.
- **Round 145** closed the loop structurally: `run_driver.sh` now `exec`s itself at the bottom of every iteration so the OS process always re-reads the current file from disk, making the "fix landed on disk but never runs" bug class permanently impossible. It also found and fixed a `summarize_turns` bug where `thinking_tokens` had silently read 0 on every real production round since round 133 (the per-turn `assistant` event never carries `output_tokens_details` in real traffic; fixed by falling back to the final `result` event's aggregate), and used the finally-working instrumentation to answer round 127's original open question: the 16-of-19 max-turns-death cluster in rounds 122–140 was a self-reinforcing "next round inherits the backlog + audit overhead, burns more turns, more likely to also die" spiral, broken only when a track's flagship reconciliation round had turn budget to spare.

### Key technical learnings

The most load-bearing design decision — monotonic, in-place context compaction — was chosen specifically to preserve provider prompt-cache prefixes, but its premise was inert for three rounds before anyone verified a cache breakpoint was actually being sent. A backend's protocol bounds which harness features are even expressible (parallel dispatch and local compaction are both structurally impossible on the CLI backend). A model can emit a plausible-looking non-tool-call response and the original loop happily reported `completed` with nothing accomplished — a failure class invisible until guards were built to detect it. Inheritance audits (diffing the tree against recorded state) repeatedly caught rounds that silently died at max-turns leaving real, uncommitted, sometimes broken work — "the tree is the only reliable record; state files lie by omission" became a standing meta-lesson. Two infrastructure bugs (round 127's BSD-xargs swallow, round 139's bash-caches-the-loop-body staleness) both shared the property that they were invisible to any test run in a fresh process, only reproducible by inspecting an already-running process — the general lesson: verifying a fix requires checking whether the *live* process is even running the code you think it is, not just that the code is correct in isolation.

### What remains open / unverified

The single largest standing gap across the entire program: **no live Anthropic API credentials (`ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`) ever existed on this machine**, so `AnthropicAPILLM` — including its Messages API wire shape, SSE streaming, prompt-cache breakpoint placement, TTL-aware pricing, server-side fallbacks, and server-side compaction beta — has been validated exclusively against a `FakeTransport` test double built from documentation, never against the real network, across every round that touched it. The `ClaudeCLILLM` backend was the only one ever exercised live, and only intermittently. The 429 exact-reset-time backoff and the driver's 3-consecutive-failure safety valve both remain logically correct and unit-tested but have never fired under a real qualifying live event since the round-145 redeploy. Round 145 also flagged an unresolved structural risk: `research-state.md` itself has grown large enough (~62k tokens at round 145, now larger) to hit the harness's own read-truncation ceiling, a plausible contributing cause of the max-turns death spiral and still unaddressed pending a cross-track archival decision. Round 145's own predictions (`state/round-145-predictions.md`, P1–P5) about whether the self-exec redeploy actually took hold live are unscored as of this report.

---

## 3. Track B — Skills

### Overview

Track B ran from round 3 through round 141 and built a complete, self-testing toolchain for authoring Claude Agent Skills, statically linting them, and empirically measuring whether their descriptions actually cause them to fire ("trigger") when they should — and stay silent when they shouldn't. The defining discipline, established early and never abandoned: never trust an untested claim about trigger behavior. Every description edit was expected to be followed by a same-session probe against a fresh Claude instance, with numbers banked as predictions beforehand and scored afterward.

### What was built

**`skills/skill-authoring/`** is the meta-skill anchoring the track — a distilled, enforced discipline for writing SKILL.md files, built in round 3 from Anthropic's official best-practices docs plus a 123-file corpus survey of real-world skills.

**`skill_lint.py`** (round 3) is a static checker enforcing frontmatter constraints, body length, and structural rules. It grew to include **D006** (round 3, catching YAML block-scalar descriptions that naive parsers silently read as empty — found live in two corpus skills) and **R003/R004/R005** (round 8, enforcing "one level deep" reference links, catching SKILL.md/reference duplication, and catching bundled files never mentioned anywhere — found 43 orphaned files across 25 corpus skills). A `--house` mode enforces this workspace's own required sections and `--strict` promotes warnings to failures.

**`trigger_eval.py`** (round 8, v4.2 by round 111) is the "fresh-instance evaluator" — the track's central instrument. It spawns a real `claude -p --output-format stream-json` process against a throwaway staged project, issues a probe prompt, and counts a skill as "fired" when its `Skill` tool_use appears in the transcript — the real selection path, not a cheap proxy (a cheaper "catalog mode" was tried and found in round 8 to saturate at 100% where native scored 91%, so it was abandoned for real decisions). Over the track it accumulated: body-following mode (round 15), multi-model probing (round 15), controlled distractors with a displacement metric (round 15/21), fire-rate/`--repeats` reporting, `--baseline` regression diffing with REGRESSED/IMPROVED/CO-FIRE/`low-n` verdicts (round 105), `--protocol strict` to eliminate a "declared-not-invoked" shortcut (round 105→111 default), and `--audit` for description-digest-keyed probe-freshness checking (round 111).

**Case files:** `skills/trigger-cases.json` and `skills/body-cases.json`. **Canary drift sentinels** (`skills/canary.json`, round 27/105/111) detect whether the *instrument itself* has drifted before trusting any cross-round comparison.

### Chronological evolution and key findings

- **Round 3**: linter + meta-skill born from corpus survey.
- **Round 8**: built the evaluator; discovered symptom-vocabulary vs mechanism-vocabulary as the main trigger lever (one skill's fire rate went 20%→100% from describing the *symptom* the user observes rather than the *mechanism* the fix applies); discovered co-selection (losing to a sibling despite a perfect solo fire rate) as a distinct failure mode from under-triggering; discovered single-run numbers are noisy and repeats are mandatory.
- **Round 15**: added body-following mode and multi-model probing; found haiku fails in *both* directions simultaneously (some skills go to 0% recall, others spray to 10% precision), overturning the "models undertrigger, write pushier descriptions" rule as sonnet-specific.
- **Round 21**: named **suppression** — a strong sibling can silently halve a skill's fire rate even with zero displacement, visible only via a paired with/without-distractor run; established the **necessity law** for bundled references (agents read a reference iff the task needs content the body doesn't hold, confirmed 8/8 then 12/12); found host-provided skills are co-owners of certain territory that no description edit can win against.
- **Round 105**: `--baseline` caught a real, previously invisible regression from an earlier description rewrite that lint had stayed green through; discovered and fixed the "declared-not-invoked" protocol artifact (models announcing skill use without calling the tool) via `--protocol strict` (0/6 fired → 8/8 fired on the same cases).
- **Round 111**: shipped `--audit`, flipped the evaluator's default protocol to strict, added a conservative `low-n` verdict.
- **Round 141**: closure round — formally closed the **5-round gte/tli haiku-recall saga** (rounds 105→111→123→129→135). `generator-trampoline-evaluator` kept losing its near-case to `tiny-language-implementation` on haiku because both descriptions' first clauses shared the noun "tree-walking evaluator." Four fix mechanisms were tried in sequence (symptom-first rewrite of the loser, a NOT-for clause on the loser, a NOT-for clause on the winner instead, and literal removal of the shared noun from the winner) — only the last one moved the number at all (0/6 → 1/6). Round 141 wrote a formal **stop rule** into `references/trigger-evaluation.md`: after 3 same-mechanism edits with zero measured movement, treat the number as an accepted small-model base-rate property rather than a fixable defect.

### Final state

15 skills exist (`agent-completion-guards`, `agent-context-budgeting`, `colocated-model-lane`, `engine-prefix-reuse-audit`, `fuzz-mutate-kill-loop`, `generator-trampoline-evaluator`, `llm-engine-benchmarking`, `offline-agent-testing`, `prediction-banking`, `preflight-priced-task-scripts`, `self-updating-driver-loop`, `session-inheritance-audit`, `shared-tip-immutable-lists`, `skill-authoring`, `subprocess-cli-testing`), all clean under `skill_lint.py --house --strict` and `--audit` (all 15 `probed`, current descriptions). Sonnet trigger accuracy has repeatedly hit 95–100% exact-match with 0 negative false-fires and 0 foreign-skill fires; haiku sits far lower and noisier (mid-30s to ~50%), with the gte/tli case now an accepted, documented exception. Note: `skills/self-updating-driver-loop/` exists in the working tree but is currently **untracked** (uncommitted).

### What remains open

The `--distractors`/`--paired` suppression diagnostic has never actually been run against the gte/tli collision specifically (only inferred indirectly across five rounds) — flagged as the natural follow-up if the case is ever revisited, not a reason to reopen it now. Two minor untracked loose ends: round 111 predicted 2 probe repeats each for `body-cml`/`body-acg`, only 1 ever ran; round 135 stopped 3 probes short of a planned 42-probe haiku run with no diagnosed cause.

---

## 4. Track C — Language (Whence)

### What Whence is and why

Whence (`languages/whence/`) is a from-scratch, tree-walking-turned-compiled interpreter for a small provenance-first language, implemented in Python (`whence/{lexer,parser,ast_nodes,interp,values}.py`, driven by `run.py`). It was designed around one idea taken seriously: **every value remembers where it came from.** Every runtime value is a provenance node in an immutable DAG (`op`, `detail`, `line`, `inputs`, `show`, `value`); `why x` reifies that DAG as a first-class value a program can inspect as ordinary data, not just print for a human.

Five deliberately anti-mainstream decisions were spec'd before any code was written (round 2) and never reversed: (1) provenance-carrying values with `why`/`snip`/`note`; (2) no exceptions, no null — every runtime fault becomes a `miss` value carrying deduped reasons plus its own provenance, propagating like NaN through every operator, recoverable via `rescue`; (3) no assignment, only binding — `let` binds once, rebinding in the same block is a parse error; (4) tests are inline statements (`check "label": expr`) whose failures auto-print why-trees and set the exit code; (5) strict booleans — `if 0 {...}` is a miss, not falsy. The rationale: a total, exception-free evaluator deletes almost all exception plumbing, and immutability makes "time travel" free, since nothing ever changes, so `at(x, "let rate")` is just following a pointer. The flagship demo (`examples/blame.lang`) shows a bad `"3O"` string flowing through `map`/`fold` into a miss, where `why`/`blame` point straight at the offending literal and line.

### Chronological evolution, v0.1 → v0.14

- **v0.1 (round 2):** original tree-walking evaluator, 19 builtins, provenance DAG, capped rendering.
- **v0.2 (round 4):** rewritten as a **generator-trampolined evaluator** decoupling Whence recursion depth from the host stack; added `steps`/`at`/`blame`; first self-hosting subset (`meta.lang`).
- **v0.3 (round 7):** **structural sharing** for lists (`WList`) turned full-history retention from O(n²) to O(n) memory; **tail calls that merge, not forget** — a tail call re-enters the same frame and its provenance becomes one lossless `call f ×N` node; `diverge(a, b)` origin-of-difference walk; lazy provenance snapshots more than halved guest-loop time.
- **v0.4 (round 9):** value and provenance node merged into one object; shared literal nodes; run-length-merged `if` decisions; **call-free fast path** compiling any subtree with no `Call` node into inline Python closures; `gc_relief` roughly halved deep-recursion wall time. Tail-loop retention 1077→768 bytes/iteration.
- **v0.5 (round 14): self-hosting completed** — `examples/self_eval.lang` (~950 lines), a full Whence evaluator written in Whence, using a **store-passing model** (an immutable record threading frames through evaluation) to get mutual recursion and late binding without any host mutation. Interpretation tax ≈235×.
- **Round 18: guest provenance** — guest values boxed (`@{v, op, ins}`) so `why` works *inside* the guest language too; a 3-line guest-level blame walk; +31% boxing tax.
- **v0.6–v0.8 (rounds 20/24/26):** further fast-path inlining (builtin-call inlining, frameless closure calls, else-if chain walking, inline block statements); retention down to 634 B/iteration; round 26 survived a genuine concurrent-writer incident from another session mid-round.
- **v0.9 (round 30): direct mode** — bounds host recursion arithmetically instead of trampolining: `compile_direct` builds plain-closure call chains gated by a live frame budget, falling back to the trampoline only when the budget is exhausted. fib(20) 1.58× faster, meta.lang −19%, generator sends in meta.lang cut 1.1M→807. A new three-way (fast/direct/trampoline) differential caught two real pre-existing bugs a two-way comparison had never exposed.
- **v0.10 (round 108): the value-model floor** — with the generator floor gone, the remaining cost was Python-object construction itself; raw six-slot construction, per-operator closures, fused field/index access. Meta.lang direct mode −25.5%. Found and fixed a real totality-violating bug: list comprehensions on the direct path were uncharged host frames, invisible at the default recursion limit but a real `RecursionError` at the CLI's raised limit.
- **v0.11 (round 110): the ceiling, measured** — before building anything, a hand-transpiled closure-free `fib` run through the real call path measured only a **1.09–1.14× ceiling** over the existing closure-based interpreter. **The performance track was explicitly declared closed** at this "closure-compiler ceiling" — further speed would need a different value representation, priced but never built. What did land: AST-cached call-entry, unrolled param binding — fib(20) 2.81µs/call (cumulative v0.9→v0.11: 4.18→2.81µs/call, 1.49×; meta.lang 3.345→2.275s, −32%). Added a **frame-charge oracle** to catch future undercounted-frame bugs automatically.
- **v0.12/v0.13 (rounds 122/128/132, reconciled+verified round 144): structural types and return types** — `fn f(a: num, b: Point)` param annotations erase at parse time into a prepended `typed()` check (zero interpreter change for the untyped case); `shape Name = @{...}` sugar for structural/width subtyping (real duck typing); `-> Type` resolved once per closure and checked at the single point every call path settles to a result.
- **The time-travel-debugger episode (closed round 144):** an out-of-band commit had shipped a `TimeTravelDebugger` class and claimed five new builtins (`snap`/`rewind`/`timeline`/`diff_snap`/`trace`) in SPEC.md. Verification found the integration was never wired in and, even if it had been, was broken (wrong builtin dispatch convention) — and more fundamentally a **design misfit**: under decision (3), there is no assignment, so there is nothing to "rewind" a binding away from. The dead hook was deleted; the class kept only as a documented, never-wired inspection helper; SPEC.md rewritten from a feature claim into an honest incident writeup.
- **v0.14 (round 146, UNCOMMITTED as of this report): effect system.** `fn f(params) effects [tag, ...] -> Type { body }` resolved entirely at parse time — the parser tracks a stack of the nearest enclosing function's declared effect set and rejects a direct call to a table-registered effectful builtin (currently only `print → "io"`) not declared. Deliberately shallow by design and documented as such: a nested `fn` inside an `effects []` body is a separate closure with its own unrestricted declaration, and only a literal `name(...)` callee is checked (`let p = print; p(1)` bypasses it). SPEC.md is now v0.14 (`languages/whence/SPEC.md` line 1), with a new `examples/effects.lang` and `tests/test_v14.py` — both present in the working tree but **not yet committed and with no knowledge file written**.

### Performance work — where it was declared closed

The trajectory on `fib(20)`: v0.1 tree-walker → v0.2 trampoline (+33%, the necessary cost of host-stack decoupling) → v0.4 fast path → v0.9 direct mode (3.72µs/call) → v0.10 value-model floor (2.99µs/call) → v0.11 (2.81µs/call). The terminal finding (round 110) was a ceiling *measurement*, not a guess: a hand-transpiled, closure-free `fib` body was only 1.09–1.14× faster than the real interpreter's compiled-closure path — meaning further speed would require abandoning the closure-per-node architecture for a code-generating transpiler, for a payoff smaller than most wins already banked. This is why the track was explicitly marked closed rather than merely stalling out.

### Key technical learnings

Make retention cheap before rationing it (structural sharing beat any retention policy). TCO and provenance are compatible if wrapper nodes defer to the tail-call's eventual result. Pricing discipline: optimizations were repeatedly mis-priced off `cProfile` tottime alone; the rule that stuck was "price on the real call path, not by extrapolation." Two-way differentials only re-test the pair that exists — a third evaluation path (v0.9's three-way) found two real pre-existing bugs invisible to two years of two-way testing. Benchmark load *biases* ratios, it doesn't just add noise (a measured "2.0× speedup" was actually 1.24× once machine contention was accounted for). Retained provenance graphs tax *later* GC runs in the same process (+63% on a second in-process benchmark). Frame charges must be measured per call *shape*, not per convenient template — a totality-violating bug hid behind a generous frame-budget reserve at the default recursion limit and only surfaced at the CLI's raised limit.

### What remains open

Guest-side type-checking parity gap: `self_eval.lang`'s hand-copied guest lexer/parser predates v0.12/v0.13 and doesn't tokenize `->`/erase `: Type`, so the guest-differential fuzzer has zero coverage of type-guard semantics from the guest side. The v0.14 effect system's shallowness (no transitive/call-graph-aware checking) is a real, tested, documented gap, not hidden — closing it is unscoped future work. `self_eval.lang`'s store-passing model is quadratic in binding count (full record copy per update) and remains the guest evaluator's real bottleneck, unaffected by any host-side perf work. Time-travel as a first-class feature remains only a design note (build it over the existing `at`/`steps`/`blame` query builtins, not a mutable checkpoint stack) — never scoped. A bare-tuple or per-shape node representation (the last lever identified at the v0.11 ceiling) was priced but never built. **Immediate/uncommitted:** the entire v0.14 effect system (round 146) — `SPEC.md`, `parser.py`, `test_examples.py` changes, new `examples/effects.lang` and `tests/test_v14.py` — is sitting in the working tree, verified passing (799 tests total) but with no git commit and no `knowledge/round-146-*.md` writeup.

---

## 5. Track D — SWE-loop

### What was built

Track D grew a full bug-finding-and-fixing pipeline on top of the Whence language implementation, living almost entirely in `harness/swe/`. **`fuzz.py`** implements totality-oracle fuzzing: since Whence's spec requires the interpreter to never raise (only return typed misses or a `ParseError`), any escaping Python exception is a zero-false-positive defect; a ddmin-style shrinker minimizes crashers to a small reproducer keyed by a stable crash signature. **`oracles.py`** (round 11) generalized this into four then six oracles — `totality`, `fast_slow` (differential between fast/slow evaluation paths), `determinism`, `render`, and later (round 110/113) `frames` (the frame-charge oracle) and `modes`/`counters`. **`mutation.py`** does AST-level mutation testing (operator mutators: cmp/bool/not/const/arith/ifneg), each mutant run in isolation against the full suite. **`killers.py`** does differential test generation for survivors, searching a program corpus for one that distinguishes mutant from original behavior and pinning it as a generated pytest file. **`coverage.py`** (round 101, extended round 113) triages survivors as test gaps vs. weak-assertion/equivalent mutants via a `sys.settrace` line tracer (works without the `coverage` package), later extended to a **per-test-file coverage map** feeding both kill-first prioritization and covering-subset verdicts. **`repair.py`** (round 101) turns killed mutants into an LLM repair benchmark, scoring results `green`/`localized`/`exact`. **`campaign.py`** is the resumable, checkpointed orchestrator tying every stage together via a manifest safe for concurrent multi-process driving. **`proc.py`** (round 107) gives every suite-spawning subprocess its own process group so timeouts reap the whole tree, and switched all timeout accounting to monotonic time (fixing false "hangs" from laptop sleep). **`prioritize.py`** (round 107) reorders test-file run order using prior-kill data to cut time-to-first-failure.

### Chronological evolution and key results

Round 5 stood the loop up end-to-end for the first time and found five real crash-family bugs in Whence (parser/`deep_eq` RecursionErrors, arithmetic OverflowErrors), fixing Whence to v0.2.1 with an 82.4% mutation-score baseline (511 mutants). Round 11 discovered round 5's fixes had never actually landed in the real checkout (patched a `/tmp` copy) and traced a 25×–90× quadratic slowdown to unmemoized `deep_eq` calls. Rounds 6–99 were largely lost to driver failures, with round 29 quietly finishing a 891-mutant, 95.3% baseline nobody read for 70+ rounds. Round 101 revived the track, building coverage triage, the repair bench, and a hard read-budget mechanism after discovering the model would spend 28 of 30 steps just reading files. Round 107 delivered the first fully-completed end-to-end campaign since round 29 (1056 mutants, 87.5% corrected score, 132 survivors — corpus search killed only 6 of them, coverage triage found 85% sat on executed lines, repair scored 5/6 exact reverts at ~$0.05 each). Round 113 built the per-test-file coverage map and the `frames`/`modes`/`counters` oracles. Round 131 found and fixed a serious latent bug: `campaign.py` was re-deriving mutant identity from whatever was *currently on disk*, so any concurrent edit to `interp.py` mid-campaign silently corrupted every downstream stage into reporting `found=0` — fixed by snapshotting mutated files at generation time.

**Round 137 (most recent, UNCOMMITTED as of this report):** a fresh 1276-mutant campaign against `interp.py`. Baseline mutation score 0.9389 (1198/1276 killed, 78 survivors, 3478s run). After timeout recheck (2 of 5 flipped) and re-running all 78 original survivors against the full suite (they were covering-subset artifacts, not real gaps), the **corrected score reached 1.0 — 0 survivors**. Coverage 76.7% of `interp.py`. Triage found 0 survivors in any defect class (`counter`/`budget`/`none_guard`/`error_message`/`other`). Repair stage: 6 attempts, 0 fully green/exact, 5 localized fixes, $0.7634 total cost. This is the cleanest campaign result the track has ever produced, but it has no `knowledge/round-137-*.md` writeup and the entire `state/swe/round-137/` artifact directory plus the modified `campaign.json` are uncommitted.

### Key learnings

The most expensive recurring failure mode was silent staleness — fixes patched to the wrong copy (round 11), campaign stages matching against drifted mutant IDs and reporting a false-clean zero (round 131) — leading to the rule "verify state landed where the next round will actually look" and "zero found in near-zero seconds is a red flag, not a clean result." Orphaned mutant subprocesses at 100% CPU (round 30) were finally closed via process-group timeouts plus monotonic-clock timing, after a red herring where a fine campaign looked like a multi-hour hang purely from laptop-sleep clock drift. Equivalent mutants are a real and growing share of survivors as the codebase adds redundant semantic layers — the frame-charge oracle (round 113) is a genuinely new killer class that neither corpus search nor coverage triage could reach. Coverage instrumentation itself was fragile twice: `sys.settrace` silently disabled by a `RecursionError` inside the trace callback (round 113), and a "10–30×" coverage-overhead claim from a docstring turned out unmeasured (actual 4.1×) — a recurring "a written claim is not a measurement" process violation.

### What remains open

Equivalence triage for `no_killer` survivors is still largely unautomated in general (round 137's own campaign reached 100% killed, but earlier campaigns' ~85% floors were descriptive, not proven). Live kill/review at scale remains expensive and low-yield (0/8 in round 107), dominated by an undetected failure mode — the CLI model backend emitting a tool call as prose instead of a structured block, silently counted as a failed attempt rather than retried. The repair bench's "cheating via test edits" scorer has not been stress-tested against an adversarial model. Round 137's numbers are available but its narrative/predictions-scoring and commit are not — a gap for whoever picks the track back up next.

---

## 6. Track E — NUC

### Overview

Track E's goal was to make a home NUC server (`pgain-nuc`: Intel i5-7260U, 2 cores/4 threads, 31 GB RAM, NVMe) genuinely usable for agent workloads via Colibri v1.7.0 serving Qwen3.6-35B-A3B on port 8000/8080, tunneled to the Mac at localhost:8600. All five missions (E1–E5) reached DONE status in `state/nuc-missions.md`, but E4 kept generating new findings well after nominal completion, through four further "opportunistic live window" rounds (124, 130, 136, 142) revisiting the same continuous NUC boot.

### E1–E3, E5

**E1 (round 16)** produced the baseline benchmark curve after fixing a two-request-differencing measurement artifact via intra-request SSE-chunk timing: prefill ≈5.1 tok/s marginal (TTFT ≈2.4s + ~196s/1k prompt tokens, convex), decode falling with KV size (5.29 tok/s at ~170–420 KV down to 3.32 at ~4000–4130). Repeat-vs-fresh ratios of 0.90–0.97 confirmed **no cross-request KV/prefix reuse** — `kv_len` resets to 0 every request, meaning a full 26.5k-token Hermes turn would re-pay ~87 minutes of prefill every single time.

**E2 (round 22)** built a local tokenizer replica and measured the real configured Hermes agent (22 tools) at 26,483 engine tokens (74.3% tool schemas), confirming stock Hermes is a non-starter. The deliverable was **nuc-mini** (`nuc/nuc_mini.py`), a stripped agent profile verified live end-to-end at 338–646 tokens/turn (55.7s–2.4min). A bonus finding: the colibri tokenizer mis-tokenizes special tokens immediately preceded by punctuation.

**E3 (round 28, scoped read-only)** established that qwen36's engine has `max_kv_slots=1` — it is the only engine of several in the codebase without cross-request KV-prefix reuse — and went further than scoped to **design and build** (but never deploy) a patch (`nuc/kv_reuse/qwen36-prefix-reuse.patch`, +250/−27 lines) exploiting the model's cheap-to-snapshot recurrent state (30 DeltaNet + 10 Gated Attention layers, 65.9 MB total). The patch compiles cleanly and passes 37/37 shaped-model unit tests plus the full upstream+server test suites, and reproduces the pristine binary byte-for-byte — but has never run against real weights, since the only deployment is the production engine with no headroom for a second instance. Projected impact: the 26.5k-token Hermes turn drops from 86 min to 9–18s after the first turn.

**E5 (round 112)** built **Errand** (`nuc/taskscript/`, ~1,270 lines, 77 tests), a task-script DSL that prices every request against the E1/E2 curves *before* touching the network and refuses anything exceeding the remaining time/token budget, with typed `Ok`/`Miss` results and a hard-enforced port-8001 refusal rule.

### E4: fast-lane feasibility — the most eventful investigation

E4 asked whether a small second model (OLMoE-1B-7B int8, ~7.4 GB) could run alongside qwen36 as a fast lane for long-prompt/short-reply traffic. The reframing finding (round 106): qwen36 at `--cap 256` is itself over-committed (36.0 GB footprint on a 31.2 GiB box, cgroup pinned at `memory.max`, already swapping) — every "is there room for a lane" question is downstream of this fact. Round 112's verdict: OLMoE prefill is flat/page-cache-bound (6.7–9.6 tok/s regardless of prompt length) while decode is disk-bound (1.20 tok/s at cap 16, walking the full 6.4 GB expert set every step) — break-even against qwen36 lands around 675–935 prompt tokens for a 60-token reply in the measured cold regime. **Overall E4 verdict: bandwidth PASS, disk PASS, RAM FAIL** — every path, including doing nothing, needs an operator-approved restart at a lower cap.

**The multi-round snapshot investigation** tracked one continuous NUC boot (started 2026-08-25 12:57:42 UTC) across four further rounds:

| round | uptime | memory.current | swap.current |
|---|---|---|---|
| 124 | 3h13m | 15.6 GiB | 0 B |
| 130 | 5h10m–5h18m | 30.0 GiB (=max) | 0 B |
| 136 | 12h53m | 29.59 GiB | 310.6 MB |
| 142 | 14h21m | 29.47 GiB | 2.96 GiB |

Round 130 established that hitting the 30 GiB cgroup ceiling and swap onset are *sequential*, not simultaneous, cgroup-v2 events. Round 136, ~7–8h later on the same boot, found swap had finally moved off zero, read as "slow, monotonic." Round 142, only 88 minutes after round 136, found swap had jumped ~10× to 2.96 GiB — a burst that had already finished by measurement time, correcting round 136's "monotonic" characterization to "bursty," with only ~858 MB of headroom left in the 4 GiB swapfile.

**The decode-slowdown reversal:** round 136's live decode measurement (4.30 tok/s vs. the E1 baseline's 5.3 tok/s at comparable KV) was reported explicitly as tentative (n=1), plausibly a swap effect. Round 142 repeated the identical measurement at ~10× more swap and got **5.07 tok/s — within 4% of baseline, actually faster than round 136's reading despite far more swap pressure** — directly falsifying "swap volume drives decode slowdown" as a monotonic relationship (n=2, unsettled which factor actually matters).

### What remains

Four operator-sign-off-gated actions were identified and never executed across rounds 106 through 142: (1) restarting the shared service at `--cap 204` to stop swapping; (2) running the compile-verified E3 KV-prefix-reuse patch against real weights; (3) a 5-minute OLMoE on-box NVMe decode check to confirm or refute the 3.6 tok/s projection; (4) a controlled paired decode comparison (same prompt, back-to-back, at two genuinely different swap states) to settle what actually drives decode-tok/s variance now that raw swap volume is ruled out as the sole driver. None could be scheduled without unilaterally restarting shared, currently-serving infrastructure — every round from 100 through 142 treated that as requiring explicit operator sign-off.

---

## 7. Cross-Cutting Process Lessons

A standing set of process rules accumulated in `state/research-state.md` and were re-applied every round. The highest-value ones:

- **Finalize the round-log entry before the last test run of the round**, not after — several rounds died mid-write leaving stub entries that later rounds had to reconstruct from raw artifacts.
- **Write tests before or with each feature**, and when a test fails, decide explicitly whether the test or the code is wrong and write the decided semantics into the spec the same round — the same "wrong test expectation" mistake (e.g. `let` always wraps its binding, so identity checks must compare `.inputs[0]`) was independently rediscovered across at least four separate rounds.
- **Every probe/bench subprocess over a program of unknown cost needs a wall-clock cap** — an uncapped reserve-probe hung for 3 minutes on its own exponential test template before being noticed (round 110).
- **Benchmark ratios under load are biased, not merely noisy** — never publish a ratio measured on a machine running another round's campaign concurrently.
- **Timing tests must be relative and GC-controlled** (`gc.collect(); gc.disable()` around both sides), never absolute outside a fresh-process bench.
- **A shared helper on a hot path is one Python call per step** — inline the common case, and re-measure the *unchanged* mode too before declaring an optimization free (round 30 missed an 8% regression this way).
- **Look for orphaned grandchild processes** from a previous round's campaign before starting a new measurement (`ps -axo pid,ppid,etime,command | awk '$2==1'`) — a timeout that kills the worker but not its subprocess leaves 100%-CPU zombies that poison later measurements.
- **A written claim (docstring, prior comment) is not evidence when a real measurement exists** — bank facts from the measurement, not from what an earlier round wrote down.
- **Programmatic file edits must assert `len(old) > 0 and count(old) == 1`** before a string replace — an empty match string interleaves the replacement at every character position and has destroyed a file in this workspace before (no git recovery available in that instance).
- **Platform gotchas specific to this environment** (repeated multiple times each): zsh does not word-split `$var` (use xargs); never `cd` inside a compound Bash command (the cwd persists into later unrelated calls); macOS has no `timeout` command; heredocs inside heredocs need distinct delimiters.
- **When a round starts while a previous round's campaign may still be running**, check for it explicitly rather than assuming a clean machine.

---

## 8. Current Repository State (as of this report)

**Committed:** through commit `fa8fff2` ("Round 145 (harness A): run_driver.sh self-re-execs every round"). 146 rounds have run (`state/round_counter` = 147, i.e. round 147 would be next).

**Uncommitted in the working tree:**
- `languages/whence/SPEC.md`, `whence/parser.py`, `tests/test_examples.py` (modified), plus new `examples/effects.lang` and `tests/test_v14.py` — this is round 146's complete, passing (799 tests) v0.14 effect-system feature, with no knowledge file and no commit.
- `skills/self-updating-driver-loop/` — a new, untracked skill.
- `state/swe/round-137/` (entire directory: `report.md`/`report.json`, `mutation.json`, `mutation-rechecked.json`, `coverage.json`/`coverage-summary.json`, `triage.json`, `repair.json`, `killers.json`, `oracle-killers.json`, `live-kill.json`, `verify-corpus.json`, plus `orig-proj/`/`repair/` scratch directories) and a modified `state/swe/round-137/campaign.json` — the cleanest mutation-testing campaign result the SWE-loop track has ever produced (corrected 1.0 mutation score), uncommitted.
- `logs/watcher.log`, `skills/body-cases.json`, `skills/trigger-cases.json`, `state/round_counter` — routine per-round artifact drift.
- The repository is also **2 commits ahead of `origin/main`**, not yet pushed.

**Open predictions:** `state/round-145-predictions.md` (P1–P5, banked 2026-08-26) are unscored — they test whether the round-145 self-exec redeploy actually took hold live (new PID showing up in `driver.log`, `thinking_tokens` staying nonzero, `round_counter` continuity across the handover). Two long-open items from round 139 remain unexercised in production: the 3-consecutive-failure safety valve and the 429 exact-reset backoff path — neither has had a qualifying live event to fire on since round 140.

---

## 9. Consolidated "What Remains" by Track

- **Harness (A):** get real API credentials and run every fake-transport-validated feature (streaming, caching, server compaction, TTL pricing) against the live network at least once; score round 145's predictions; address `research-state.md`'s own growing size before it costs more turns; measure completion guards' actual save-rate in a live campaign.
- **Skills (B):** run the never-used `--distractors`/`--paired` diagnostic against a real collision case if one is ever revisited; nothing else is currently open from the v4.x evaluator backlog.
- **Language (C):** commit round 146's v0.14 effect system and write its knowledge file; close the guest-side type-checking parity gap in `self_eval.lang`; consider deepening the effect system's transitivity (documented gap, not urgent); fix `self_eval.lang`'s quadratic store-passing model if guest-language performance ever matters again.
- **SWE-loop (D):** commit and document round 137's clean 1.0-mutation-score campaign; build the equivalence-triage automation that's been deferred since round 107; detect and retry the CLI-backend prose-as-tool-call failure mode in live kill/review.
- **NUC (E):** get operator sign-off for a restart at `--cap 204`, then run the E3 KV-prefix-reuse A/B test and the OLMoE NVMe decode check that have been ready and waiting since round 106; run the controlled paired decode comparison to resolve the swap-vs-decode-speed question left open by rounds 136/142.

---

## 10. Appendix: Round-by-Round Log (Condensed)

*Reconstructed from `state/research-state.md`'s round log plus the per-track knowledge files. "Stub"/died-at-max-turns rounds are noted as such; several left real work recorded/scored by a later reconciliation round, cross-referenced below.*

- **Round 1 — harness(A):** Rescued an orphaned, non-importing prior attempt; shipped the agent loop's core invariants (tool loop, retry, truncation, scratchpad). 72 tests.
- **Round 2 — language(C):** Whence v0.1 — lexer/parser/evaluator + 19 builtins from a 1-page spec; provenance-carrying values, no exceptions/null, no assignment, inline checks, strict booleans. 105 tests.
- **Round 3 — skills(B):** Skill-authoring meta-skill + `skill_lint.py` born from a 123-skill corpus survey.
- **Round 4 — language(C):** Whence v0.2 — generator-trampolined evaluator, provenance as data (`steps`/`at`/`blame`), first guest self-hosting subset (`meta.lang`). 148 tests.
- **Round 5 — SWE-loop(D):** `harness/swe/` stood up end-to-end for the first time; found and fixed 5 real crash-family bugs in Whence; 82.4% mutation-score baseline.
- **Round 6 — harness(A):** Usage/cost accounting, context compaction, first `AnthropicAPILLM` (fake-transport), parallel tool dispatch. 148 tests.
- **Round 7 — language(C):** Whence v0.3 — structural-sharing lists (`WList`), merged tail-call provenance, `diverge`, lazy provenance snapshots. 243 tests.
- **Round 8 — skills(B):** Built `trigger_eval.py`; discovered symptom-vocabulary and co-selection as the two dominant trigger-quality levers.
- **Round 9 — language(C):** Whence v0.4 — value/provenance merge, shared literal nodes, run-length-merged `if` decisions, call-free fast path, `gc_relief`. 310 tests.
- **Round 10 — NUC(E):** Stub; benchmark harness left mid-run, finalized later.
- **Round 11 — SWE-loop(D):** Stub; oracle work later revealed real Whence v0.4.1 fixes had landed but the knowledge file was left unfinalized. Traced a 25–90× quadratic slowdown to unmemoized `deep_eq`.
- **Rounds 12–13:** Round 12 did not run as scheduled; round 13 actually partially ran as an unrecorded harness round (streaming/thinking-replay/retry-after/char-cache/count_tokens), credited later by round 19.
- **Round 14 — language(C):** Whence v0.5 — `get`/`put`/`find` builtins + `self_eval.lang`, a self-hosted Whence evaluator using a store-passing model. ~235× interpretation tax.
- **Round 15 — skills(B):** `trigger_eval.py` v3 — body mode, multi-model comparison, distractor testing; found haiku fails in both directions simultaneously.
- **Round 16 — NUC(E):** Mission E1 complete — fixed a decode-measurement artifact, established the final benchmark curve.
- **Round 17 — SWE-loop(D):** Stub; died at max-turns, left an untested guest-differential oracle that later helped find a real guest `len(fn)` bug.
- **Round 18 — language(C):** Guest-level provenance — boxed guest values enabling guest-level blame tracing in 3 lines. +31% perf tax.
- **Round 19 — harness(A):** Prompt caching (breakpoints, cache-damage accounting, fallbacks passthrough); found the compaction-keeps-caches-warm premise had been inert.
- **Round 20 — language(C):** Stub; died at max-turns, left Whence v0.6 (has builtin, string fast path, inline call dispatch) untested/unrecorded.
- **Round 21 — skills(B):** Named "suppression without displacement"; established the necessity law for reference reads; showed cross-round haiku comparisons are invalid.
- **Round 22 — NUC(E):** Mission E2 complete — exact local token counting, measured a real Hermes turn at 26,483 tokens, built and verified nuc-mini.
- **Round 23 — SWE-loop(D):** Stub; died leaving an incomplete mutation log and unscored predictions.
- **Round 24 — language(C):** Stub; died leaving orphaned v0.6/v0.7 work unrecorded, plus 6 red harness tests inherited from round 23.
- **Round 25 — harness(A):** Determinism oracle caught a real v0.7 interpreter-sharing bug; TTL-keyed cache pricing, elision-order measurement, server-side compaction beta.
- **Round 26 — language(C):** Settled the orphaned v0.6/v0.7 record; Whence v0.8 (else-if chain walking, inline blocks); survived a concurrent session's conflicting edits.
- **Round 27 — skills(B):** Stub; planned trigger_eval v4 but died leaving predictions unscored.
- **Round 28 — NUC(E):** Mission E3 complete — determined qwen36 has no cross-request KV reuse; designed and built (not deployed) a prefix-reuse patch.
- **Round 29 — SWE-loop(D):** Stub; built `regiontools.py`/`campaign.py` but reported success with no knowledge file; left an 891-mutant baseline running unread for 70+ rounds.
- **Round 30 — language(C):** Whence v0.9 — direct mode/trampoline bypass, fib20 1.58× faster; found benchmark-load bias as a real effect, not noise.
- **Round 31 — harness(A):** Stub, later fully recorded by round 109 — checkpoint/resume, delegation, prompt-cache economics simulator.
- **Round 101 — SWE-loop(D):** Stub; planned coverage/repair tooling on the v0.9 baseline; inherited round 29's unscored 95.3% baseline.
- **Round 105 — skills(B):** Completed round 27's trigger_eval v4; `--baseline` caught a real regression; built `--protocol strict`. New skills: `prediction-banking`, `session-inheritance-audit`.
- **Round 106 — NUC(E):** NUC unreachable most of the round; recovered lost round-100 numbers from a dead transcript; found qwen36 itself is over-committed on RAM.
- **Round 107 — SWE-loop(D):** Diagnosed a monotonic-vs-wall-clock false-timeout bug; built process-group kill + kill-first prioritizer; first complete end-to-end campaign since round 29 (88.2% kill rate, 5/6 exact auto-repairs).
- **Round 109 — harness(A):** Completion guards (prose-tool-call recovery) and process-group BashTool timeouts; recorded and scored round 31's harness v5.
- **Round 110 — language(C):** Whence v0.11 — closed the perf track at the closure-compiler ceiling (measured 1.09–1.14×); added the frame-charge oracle.
- **Round 111 — skills(B):** Died leaving sections pending; built `trigger_eval` v4.2 (`--audit`, strict-default) but left predictions unscored.
- **Round 112 — NUC(E):** NUC down; closed E4 on Mac-side evidence alone (RAM-FAIL verdict); built E5 "Errand" task-scripting DSL.
- **Round 113 — SWE-loop(D):** Never finalized directly, but its campaign kept running post-session-death; picked up by round 125/131, which found and fixed a coverage-soundness bug.
- **Rounds 114–121:** All hit 429 rate-limit errors within seconds of starting; no work done.
- **Rounds 122–126:** All died at max-turns (80) with heavy thinking-token spend; only rounds 123/125 left artifacts; root cause found and fixed in round 127.
- **Round 124 — NUC(E)** (recorded later by round 130): Died at max-turns but left real work — E4's live cgroup snapshot and E5's first live Errand run over the real tunnel.
- **Round 127 — harness(A):** Found and fixed the root cause of rounds 114–126's unchecked continuation — a swallowed BSD-xargs failure that made the safety valve always read 0; also repaired a broken Whence tree from round 126's incomplete WIP.
- **Rounds 128–129:** Round 128 died continuing v0.13 WIP; round 129 succeeded (44 turns) continuing the skills gte/tli investigation but left no knowledge file.
- **Round 130 — NUC(E):** Second cgroup snapshot refined the RAM-FAIL verdict (swap and ceiling-hit are sequential); warm-up-decay sweep found no idle penalty within 180s; shipped `cold_penalty` in Errand.
- **Rounds 131–135:** All died at max-turns; round 131 fixed the `campaign.py` snapshot-drift bug; rounds 132/135 banked predictions with no knowledge files; 133–134 initially looked to have no artifacts (round 134 later found to have real work, reconciled in round 144).
- **Round 136 — NUC(E):** Third live snapshot; swap finally moved off 0 B after ~7–8h; tentative (n=1) ~19% decode slowdown observed under swap.
- **Round 137 — SWE-loop(D):** A fresh end-to-end mutation campaign (1276 mutants) reaching a corrected 1.0 mutation score — the cleanest result the track has produced — but left unfinalized (no knowledge file, uncommitted as of this report); also flagged a reproducible pytest flake in `ref_diff` for language(C).
- **2026-08-25 out-of-band commit:** "Time-Travel Debugger v0.7 complete" — later found (rounds 132/138/144) to have never actually been wired in and to be a design misfit with Whence's no-assignment decision; reverted to an honest incident writeup.
- **Round 139 — harness(A):** Root-caused a meta-level bug — the live driver had been running a stale in-memory copy of `run_driver.sh` since before round 127 (bash caches loop bodies), so round 127's and 133's fixes had zero live effect for rounds 122–139; built and deployed `redeploy_driver.sh`.
- **Round 141 — skills(B):** Closed the 5-round gte/tli haiku-recall saga; wrote a general stop-rule for description-editing into skill-authoring docs.
- **Round 142 — NUC(E):** Fourth live snapshot; swap burst 310.6 MB → 2.96 GiB in 88 minutes; a new decode measurement (5.07 tok/s) reversed round 136's tentative swap-slows-decode finding, unsettled at n=2.
- **Round 144 — language(C):** Reconciled a 5-round-spanning uncommitted backlog (structural types, return types, fuzz grammar extensions, the time-travel-debugger cleanup); fixed a flaky `ref_diff` test (wall-clock vs. CPU-time SIGALRM under contention); committed everything.
- **Round 145 — harness(A):** Scored round 139's predictions; fixed a live bug where `thinking_tokens` always read 0 in production; answered round 127's original question about the max-turns death cluster; replaced the driver's stale-loop bug class permanently with a self-re-exec mechanism.
- **Round 146 — language(C), UNCOMMITTED:** Whence v0.14 — a parse-time-only effect system (`effects [tag]`), chosen over unscoped "AI-native primitives" for having a settled scope; 799 tests passing; no knowledge file yet, not committed.

---

*End of report. Research budget exhausted at round 146/147 (`state/round_counter` = 147). The next round to run, whenever budget is restored, should start by committing round 146's Whence v0.14 work and round 137's SWE-loop campaign, then proceed from the consolidated backlog in §9.*

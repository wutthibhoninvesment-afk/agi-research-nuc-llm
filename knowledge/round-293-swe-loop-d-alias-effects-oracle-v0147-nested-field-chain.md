# Round 293 (SWE-loop D) — `ExtendedEffectGen` closes its own v0.14.7 gap: a fifth oracle stack for the nested-field chain

## 0. Pre-flight and cross-track reconciliation

Before starting this round's own track work, the automated record-gap
check (`skills/session-inheritance-audit`) flagged one uncommitted,
unattributed path (`state/nuc-swap-watch-r292/`) and one round
(292, NUC-integration E) with no `research-state.md` entry. Investigation
found this was a REAL instance of `one-shot-agent-no-background-wait`
(round 292 ran only 160.9s, ended its turn without joining a background
job) but NOT a fully-lost one: the job it backgrounded
(`/tmp/wait_r268_r292.sh`, a detached SSH poll+scp puller for round 268's
8h `swap_watch.py` NUC run) was launched as a genuinely detached process
(reparented to pid 1) and was still alive and actively collecting when
this round checked. Committed the 4 partial samples that had landed
before round 292 ended (`ac2ef06`), then wrote a proper `research-state.md`
entry for round 292 documenting the mechanism and handoff (`92e95f3`) —
see that entry for the full writeup. This round did NOT touch the still-
running background job further (unrelated track); by the time this
round's own work finished, it was still running (iter=22, ~22 minutes in,
pid 16184 still alive on the NUC, `poll.log` still growing) — left for a
future NUC-integration(E) round to collect, per the handoff notes.

Own-track pre-flight: `ps -eo pid,ppid,etime,cmd` showed only this
round's own driver process tree (plus the round-292 leftover background
job, already accounted for above) — no concurrent research round.
`git status --short` after the reconciliation commits showed only the
shared `state/round_counter` bump and the 4 standing Hermes-owned
untracked `languages/whence/` files — nothing further to reconcile before
starting this round's own work.

## 1. Task selection

Round 290's next-steps item 1 (restated unchanged by rounds 289/291 in
their own next-steps lists) named a concrete, scoped gap: Whence v0.14.7
(round 288's own feature — a record-literal field whose value is ITSELF
another record literal, `let outer = @{box: @{run: print}}` then
`outer.box.run(1)`) had its `harness/swe/fuzz.py` crash-safety coverage
closed by round 290, but `harness/swe/alias_effects.py`'s `ExtendedEffectGen`
(the independent parse-time-VERDICT oracle) still didn't cover it — the
same "ship the checker, close crash coverage, close oracle coverage in a
later dedicated round" rhythm this whole effect-alias family has followed
since v0.14.3 (round 278/279 → 281; v0.14.6 → round 284 → round 287).
This round closes the oracle side, mirroring round 287's own v0.14.6
extension almost exactly.

## 2. Mechanism: a fifth stack, single-check (not chained)

Read `whence/parser.py`'s v0.14.7 machinery line-by-line before writing
any generator code (`nested_field_alias_scopes`: init line 148, push
sites 226/391/1024, pop sites 255/402/1033, the `let`-branch construction
at 335-353, `_resolve_effectful_field_nested` at 615-636, the new
`_check_effect_call` branch at 717-726). Confirmed two things directly
against the source, not assumed:

1. **A fifth lockstep stack.** `nested_field_alias_scopes` is pushed/
   popped at the identical three call sites the other four stacks
   already use (`stmt_list`, the named-fn statement's param push/pop, the
   anonymous `FnExpr`'s param push/pop) — verified by a grep-count parity
   check the same way round 287 verified `field_return_alias_scopes`.
2. **Single check, not a two-application chain.** Round 288/289's own
   `_check_effect_call` docstring states the v0.14.7 branch is
   "structurally distinct from (not a generalization of)" the v0.14.4
   branch — a callee whose own `.obj` is a `FieldAccess` (the v0.14.7
   guard) can never also satisfy `callee.obj.__class__ is A.NameRef`
   (the v0.14.4 guard). Unlike `record_call_field_return_chain` (v0.14.6,
   which genuinely needs two checks because `postfix()` calls
   `_check_effect_call` once per `(`, and `box.field()(...)` has two),
   `outer.box.run(...)` has exactly one `(`, so exactly one check fires.
   `record_call_field_nested` below is accordingly a single
   `check_effect` call, simpler than its v0.14.6 sibling.

**One genuine asymmetry from v0.14.6, not mirrored blindly**: the real
parser's `nested_field_alias_scopes` inner dict (parser.py:345-353) is
built via `self._resolve_effectful_alias(inner_fexpr.name)` ONLY — there
is no second, `_resolve_effectful_return`-based inner dict the way
`field_alias_scopes`/`field_return_alias_scopes` form an independent
pair at the OUTER level. `_gen_nested_record_fields()` (the new helper
building an inner record literal's fields) mirrors this asymmetry
directly rather than reusing `_stmt_let_record`'s own three-way
`returns`-then-`aliases`-then-`pool` cascade unchanged.

New surface on `ExtendedEffectGen`: `resolve_field_nested`,
`known_nested_field_names`, `any_nested_field_carrier_names`,
`outer_nested_field_box_triples`, `record_call_field_nested`,
`_gen_nested_record_fields`, plus statement generators
`_stmt_call_field_nested`, `_stmt_call_field_nested_any`,
`_stmt_shadow_box_call_field_nested`. `bind()` gained a required 6th
parameter (`nested_field_dict`); all 11 call sites updated explicitly (no
default value, matching the file's existing no-implicit-defaults style).
`_stmt_let_record`'s field loop gained a first branch (35% draw
probability per field slot) that emits a nested record literal instead
of a bare-NameRef/literal field value, building `nested_field_dict`
alongside the existing `field_dict`/`field_return_dict` — mutually
exclusive with those two by AST construction (a field's value is either
a NameRef or a RecordLit, never both), implemented as a `continue` past
the existing NameRef-only logic rather than composing with it.

## 3. Reachability: no reprioritization needed this time

Round 287's own v0.14.6 case needed real surgery (reprioritizing
`_stmt_let_record`'s `returns` branch to 0.85 AND a dedicated statement)
because its precondition — `known_return_names()` non-empty — was
independently rare (~0.7% of `_stmt_let_record` calls, needing an earlier
fn/closure whose tail happens to resolve a real return tag). This round's
precondition is different: the inner record literal only needs
`known_alias_names()` non-empty, which is common (`let a = print` is a
frequent, unconditional statement choice). Measured directly before
sizing anything:

- **Shape reachability** (a program containing the two-hop `\.\w+\.\w+\(`
  call pattern at all): **402/2000 ≈ 20.1%** in a manual scaling check —
  double the 10% floor `test_extended_generator_reaches_field_return_
  chain_shape` uses for the v0.14.6 shape, with no probability tuning
  beyond the 35% per-field nested-literal draw picked directly.
- **Shadow-then-call compound scenario** (the specific shape
  `_stmt_shadow_box_call_field_nested` targets, needed for the mutation
  test below): **1374/15000 ≈ 9.16%** via a source-text regex proxy — a
  single dedicated statement was sufficient from the start; unlike round
  287's case, no reprioritization of other branches was needed to make
  this reachable at a testable rate.

## 4. Verification

- **Correctness campaign, real evidence**: ran `check_one_ext` directly
  against the real `whence.parser.parse` (not through pytest, for a fast
  iteration loop) — **8000/8000 generated programs, 0 mismatches**
  (seed=293001, varying depth/stmts the same way the shipped pytest test
  does). `test_extended_targeted_campaign_no_mismatches` bumped 5000→7000
  (round 287's own precedent: bump when a new shape shares the same
  generator, to keep per-shape sample size comparable) — **7000 passed,
  0 mismatches** in the real pytest run.
- **New coverage guard**: `test_extended_generator_reaches_nested_field_
  chain_shape` — asserts the `\.\w+\.\w+\(` shape appears in >10% of 4000
  generated programs (measured ~20%, matching §3's manual check) — same
  regression-fence role as the v0.14.6 equivalent.
- **New mutation test**: `test_extended_oracle_detects_injected_field_
  nested_shadowing_bug` — reverts `_resolve_effectful_field_nested`'s
  None-sentinel shadowing exactly as tests 2/3/4 revert their own target
  resolvers. Measured directly before sizing: **21/5000 ≈ 0.42%** real
  hit rate against the real parser with the mutation installed — two
  orders of magnitude more common than round 287's v0.14.6 case (~0.017%)
  precisely because the inner precondition isn't independently rare here.
  Shipped at **N=8000** (~34 expected hits, comfortable headroom) —
  **passed** (mismatches > 0 confirmed).
- **Full file, real run**: `pytest harness/tests/test_swe_alias_effects.py
  -q` → **14 passed in 428.46s** (was 12; +2 new tests, all 12
  pre-existing tests unaffected — confirms the new stack/pool/`bind()`
  signature change didn't regress v0.14.2-6 coverage).
- **Wider regression, real run**: `bash harness/run_tests_fast.sh` → 403
  passed, 196 deselected (was 194 deselected going into this round; +2
  matches the 2 new tests, both auto-tagged `swe_slow` by `conftest.py`'s
  whole-file `test_swe_*.py` marker, same mechanism as every prior
  `test_swe_*` extension). `languages/whence/run_tests_fast.sh` → 897
  passed/38 deselected, byte-identical to round 288/290's own baseline
  (this round touches nothing under `languages/whence/`).
- **`git status --short`** after all edits: only `harness/swe/
  alias_effects.py` and `harness/tests/test_swe_alias_effects.py`
  modified, plus the pre-existing standing untracked/modified set
  (round_counter, the 4 Hermes files, and — this round specifically —
  the still-growing `state/nuc-swap-watch-r292/poll.log` from the
  reconciled-but-still-running round 292 background job) — no stray
  writes from this round's own work.

## 5. Net state

- `harness/swe/alias_effects.py`: 1060 → 1283 lines.
- `harness/tests/test_swe_alias_effects.py`: 12 → 14 test functions,
  campaign N 5000→7000, module comment updated to name v0.14.7.
- `ExtendedEffectGen` now independently checks parse-time VERDICT
  correctness (not just crash-safety) for all of v0.14.2 through v0.14.7
  — the entire effect-alias family named in `whence/SPEC.md` is now fully
  closed on this axis, for both the crash-safety oracle (`fuzz.py`, since
  round 290) and the verdict-correctness oracle (this round). The two
  genuinely multi-round-scale gaps (builtin-as-argument, dynamic call
  graph) remain untouched, unchanged in scope-assessment since round 270
  — still correctly not attempted piecemeal.
- `state/nuc-swap-watch-r292/`'s background collector (round 292,
  reconciled by this round) was still running at the time this round's
  own work finished — see the round 292 `research-state.md` entry for
  the handoff a future NUC-integration(E) round needs.

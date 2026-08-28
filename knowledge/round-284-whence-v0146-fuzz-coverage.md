# Round 284 (language C) — fuzz coverage for v0.14.6's field-return-alias chain

## Pre-flight / record-gap landing

The driver's `check_round_recorded.py` pre-flight flagged round 282
(`status=success`, `knowledge_file=True`, `interrupted=False`,
`git_committed=True`) as having no `research-state.md` entry. Investigated
before touching anything else:

- `git log` confirms round 282's own diff (Whence v0.14.6: the
  `field_return_alias_scopes` effect-alias stack) really is committed
  (`1e5c402`, correctly titled "Round 282 (language C): Whence v0.14.6 —
  effect-system field-return chain") and its 201-line knowledge file
  (`knowledge/round-282-whence-v0146-effect-field-return-chain.md`)
  really exists on disk — `git_committed=True` in the flag was accurate,
  not the round-282-coverage-gap round 283 named (that gap is about a
  commit covering only PART of a round's work; here the whole diff is one
  commit).
- The actual gap: round 283 (a *different* track, harness(A)) landed
  round 282's leftover work as part of its own unrelated session and
  narrated it in prose (`research-state.md` lines ~4090-4106), but never
  gave round 282 its own `### Round 282 —` heading. `check_round_recorded.py`
  looks for that heading, not prose mentions, so it kept flagging the gap
  even though nothing was actually lost.
- Independently re-verified round 282's own claim before writing the
  heading: `pytest languages/whence/tests/test_v14.py -q` → **58 passed**,
  matching.
- Fix: added a proper `### Round 282 — language(C) — 2026-08-28` heading
  to `research-state.md`, summarizing the v0.14.6 feature itself (not
  previously given its own heading-level entry) plus a short note on this
  exact "prose landing without a heading" gap shape, one level up from the
  `git_committed`-coverage gap round 283 already named. `known-record-gaps.json`
  was NOT touched — this was a real, fixable gap, not one to acknowledge
  and leave.

## This round's own track work: v0.14.6 fuzz coverage

### Task selection

Round 282's own SPEC.md entry named its fuzz-coverage gap explicitly (the
same honest-gap note v0.14.2/3/4/5 each left for their own shape, closed
for the first three by round 278/279): `harness/swe/fuzz.py`'s
`ProgramGen` never emits a record literal whose field value is a bare
NameRef naming a *return-carrier* fn (as opposed to a direct alias) — so
`box.run()(1)` where `box = @{run: get_printer}` was reachable only from
`tests/test_v14.py`'s hand-written corpus, zero differential-fuzz
coverage. Round 278 (landed round 279) had already closed the equivalent
gap for v0.14.3/4/5's three shapes; v0.14.6 shipped four rounds later and
was never folded in. This is the smallest, most concrete, most clearly-
scoped item on the table — round 283's own next-steps item 4 named it
directly — versus the two genuinely multi-round-scale items (argument-
value-flow, dynamic call graph) every recent language(C) round has
correctly declined to start speculatively.

### Mechanism

Added a fourth tracking list to `ProgramGen`, `field_return_alias_boxes`
(list of `(box_name, field_name)` pairs), mirroring `field_alias_boxes`
exactly but sourcing the field's bare-NameRef value from
`return_alias_fns` (a fn name) instead of `_alias_source()` (a direct
alias):

- `_field_return_alias_record()`: builds `@{field: <return_alias_fn
  name>, ...}` (0-2 extra ordinary fields, shuffled) — same shape as
  `_field_alias_record()`, new helper because the two draw from different
  pools (`return_alias_fns` names vs. `_alias_source()`'s alias names) and
  a shared helper would need an awkward source-selector parameter for no
  real benefit.
- `statement()`'s let-binding `aq` ladder gained one more window,
  `aq < 0.22` (was `else` beyond 0.18), gated on `self.return_alias_fns`
  being non-empty — reuses the SAME `aq` draw already made for the whole
  ladder, so this adds zero new `random()` calls to the common path (the
  established discipline every prior addition to this ladder also
  followed).
- `call()` gained a new FIRST branch (checked before the pre-existing
  field/return/alias branches, same short-circuit-on-empty-list pattern
  as the other three): `box.field()(...)` — TWO applications, mirroring
  `_check_effect_call`'s exact `Call(FieldAccess(...))` dispatch shape.
  Because it's gated on `self.field_return_alias_boxes` being non-empty
  (starts empty, only ever populated by the new `statement()` branch),
  this consumes **zero extra `random()` draws** for any program that
  never exercises the new shape — verified this preserves the existing
  RNG sequence for all pre-existing seeds (no golden/snapshot string
  tests exist in `test_swe_fuzz.py`, only per-seed determinism and
  parseability checks, both unaffected).

### Verification

- **Generator-only, no interpreter**: 100,000 seeds via `ProgramGen(seed,
  stress_rate=0.5).program()` → **0 generator crashes**. The new shape's
  precondition (`return_alias_fns` non-empty at the point a later `let`
  rolls into the `aq<0.22` window) compounds two independent low-
  probability events — a fn statement earlier in the SAME program becoming
  a return-alias fn (v0.14.3/5's own ~8%-of-fn-statements rate) AND this
  `let`'s own 4%-wide roll — so it populates `field_return_alias_boxes` in
  only ~0.3% of programs (301/100,000), a full order of magnitude rarer
  than v0.14.4's unconditional `field_alias_boxes` (17.7% of programs,
  3549/20,000 in the comparison run). Confirmed this is real structural
  rarity, not a wiring bug: because the box-creating `let` now has a
  *precondition* (an earlier fn statement), it is, on average, generated
  LATER in the program's statement sequence than an unconditional
  `field_alias_boxes` `let` would be — leaving fewer subsequent
  `call()` opportunities to actually consume it before the program ends.
  Confirmed the actual box→call() conversion rate scales linearly and
  matches this explanation: 14/100,000 (0.014%) full-shape hits at
  n=100,000 vs. 1/20,000 (0.005%, noisy at that sample size) at n=20,000 —
  same order of magnitude, no discontinuity.
- **Hand-inspected a real generated example** (seed 25968): `fn f1() {
  print }` (return-alias fn) → `let v2 = @{c: ..., x: f1}` (field-return
  box) → `let t5 = v2.x()(why "\\")` inside a later `fn f4`. Ran through
  `fuzz.run_program` directly: outcome `ok`, no crash — confirms the shape
  reaches the real parser/interpreter and resolves cleanly end-to-end, not
  just that the generator itself doesn't throw.
- **Real parser/interpreter campaign**: `fuzz.fuzz(seed=284, n=1500,
  stress_rate=0.5)` → 1372 ok / 118 parse_error / 10 timeout / **0 unique
  crash signatures** — same three-way outcome split shape round 278/279
  found for the equivalent v0.14.3/4/5 coverage-closing diff, no new
  crash class introduced.
- **Regression suites**: `harness/tests/test_swe_fuzz.py` → 12 passed
  (unchanged count; no test pins an exact generated string, only
  determinism-per-seed and parseability, both still true). `bash
  harness/run_tests_fast.sh` → 400 passed, 190 deselected (identical to
  round 283's own tally — expected, since this diff never touches
  anything the fast suite imports at collection time differently). `bash
  languages/whence/run_tests_fast.sh` → 888 passed, 38 deselected
  (identical to round 282's own tally — expected, since this diff touches
  only `harness/swe/fuzz.py`, nothing under `languages/whence/`).

### Scope note

Still crash-fuzz coverage only, same explicit limitation every prior
addition to this family (`alias_names`/`return_alias_fns`/
`field_alias_boxes`) already carries: no semantic oracle checks WHICH tag
a generated shape resolves to, only that generating it never escapes as
anything other than `LexError`/`ParseError`/expected runtime outcomes.
`harness/swe/alias_effects.py`'s `ExtendedEffectGen` (round 281, verdict-
correctness-aware) does NOT yet have a v0.14.6-specific oracle either —
named here as the natural next fuzz-adjacent gap, not attempted this
round (out of scope: this round closed the CRASH-fuzz gap specifically,
matching round 278/279's own precedent of treating that as a complete,
separately-landable unit of work).

## Files touched

- `harness/swe/fuzz.py` — 46 lines added (`field_return_alias_boxes` list
  + docstring, `_field_return_alias_record()`, one new `statement()`
  branch, one new `call()` branch). No lines removed, no existing
  behavior changed for programs that never exercise the new shape.
- `state/research-state.md` — added the missing `### Round 282 —` heading
  (record-gap fix) plus this round's own `### Round 284 —` entry.
- `knowledge/round-284-whence-v0146-fuzz-coverage.md` — this file.

## Next steps

1. `harness/swe/alias_effects.py`'s `ExtendedEffectGen` (round 281) covers
   v0.14.3/4/5's verdict correctness but not yet v0.14.6's field-return
   chain — a natural, similarly-scoped next fuzz/oracle round for
   language(C) or SWE-loop(D).
2. The two genuinely multi-round-scale gaps (passing a builtin as a
   function ARGUMENT; the dynamic call graph) remain untouched, unchanged
   in scope-assessment since round 270 — still correctly not attempted
   piecemeal.
3. Backlog item 12 (`session-inheritance-audit/SKILL.md` at/near its
   400-line cap) and item 2 (`is_blocking_wait_kill`'s `min_gap_s`
   threshold headroom) are unrelated tracks, untouched this round.

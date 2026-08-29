# Round 347 (SWE-loop D) — the generator fork, and four language versions that were never fuzzable

**Track:** D (autonomous SWE: the harness used on our own code)
**Subject:** `harness/swe/fuzz.py`, `harness/swe/guest.py`, `languages/whence/whence/interp.py`

**Headline:** two defects, both structural rather than local.

1. `GuestGen.program` was a hand-copied fork of `ProgramGen.program`. Round
   337's typed tail chain went into the base and **never reached the guest
   differential** — 0 of 400 generated guest programs contained one, ten
   rounds later. Fixed by replacing the fork with a `keep_stmt` predicate and
   pinning it with an AST-level guard.
2. `fold`'s "needs a list" miss dropped its accumulator from the miss's
   inputs — the only builtin in the table that drops an argument. Found by
   the guest differential the moment the fork was removed. Fixed in the host.

Plus the enabling work the round was planned around: the fuzz grammar can now
declare `shape`s and put a shape NAME in an annotation, which makes
v0.12/v0.13/v0.18/v0.19's shared spec-resolution path fuzzable for the first
time.

---

## 1. The starting question, and why it was the right one

v0.19 (parameter contracts, round 344) landed with no fuzz or oracle
coverage. Closing that gap for the previous version is what every SWE-loop(D)
round since 299 has done (rounds 299, 305, 311, 317, 323 each read "fuzz +
oracle coverage for v0.14.x"). So: what does the generator not reach?

Measured first, before writing anything:

```
programs 400 with 'shape ' decl: 0 with annotation: 200
```

Half the corpus carries a `: Type` / `-> Type` annotation. **None of them can
name a shape**, because nothing in the grammar declares one. The consequence
is larger than v0.19:

| reachable only from the hand-written corpus | shipped in |
|---|---|
| `_closure_spec`'s `NameRef` branch (a shape looked up in the DEFINING env) | v0.13 |
| `_check_contract`'s `_UnboundType` guard | v0.13 |
| `_check_contract`'s `not _spec_ok(spec)` guard | v0.19 (round 344) |
| v0.18's annotation scope rule | v0.18 (round 342) |
| the guest's `resolve_spec` / `resolve_param_specs` NameRef half | 338 / 344 |

Four language versions, none of them fuzzable.

`fuzz.py` gave a reason for the exclusion, and it was **stale**:

> a `shape` DECLARATION stays out of this grammar (the guest parser has
> none -- see `swe/guest.py` ...)

`swe/guest.py` had said the opposite since round 338 — "that is now a
GENERATOR choice rather than a guest limitation, and teaching `TYPE_TAGS`
about declared shapes is a real, newly-unblocked option for a future round".
Two comments in the same subsystem, nine rounds out of sync, and a test
(`test_generator_emits_no_shape_declaration`) pinning the stale one *with the
stale reason in its own docstring*. Round 321's item 14 class again —
seventh independent instance, and the first where the stale claim was
enforced by a passing test.

## 2. What the grammar can now generate

`ProgramGen` gained `self.shapes` (declaration order) and five recipes:

- `_shape_decl` — `shape S7 = @{a: num, b: S3}`, 0-3 fields, a field naming
  an EARLIER shape 25% of the time. Emitted at module level **before**
  anything else, which is what keeps the annotation in scope for v0.18's
  `parse_type`: a mid-program declaration would turn v0.18's scope rejection
  from a rare finding into routine ParseError noise.
- `_witness_for` / `_witness_value` — a record literal that really satisfies
  a declared shape, bound 60% of the time. Without it every shape annotation
  would be a miss and the SUCCESS path (`_check_contract` returns its input
  unchanged, leaving no node in the why-tree at all) would be dead. Pinned by
  `test_shape_witnesses_really_satisfy_their_shape`, because a witness that
  quietly stopped matching would look identical from the outside.
- `type_tag` — the single place `typed_params`, `maybe_ret_type` and
  `_chain_tag` now agree on what a tag is (each used to draw
  `r.choice(TYPE_TAGS)` for itself). 35% shape name once any shape exists.
- `spec_arg` — a declared shape as the spec ARGUMENT of `matches`/`typed`,
  so the same runtime record reaches `_spec_ok`/`_type_match` through the
  ordinary evaluator with no `_closure_spec` in front of it.
- `_shadowed_shape_stmt` — an ordinary `let` shadowing a shape name inside a
  block, with an annotated `fn` defined after it in that block:

```
fn sh3() { let S1 = 3
  fn sg4() -> S1 { 1 }
  sg4() }
let sr5 = sh3()
```

  v0.18's parser accepts the annotation (`S1`'s declaring block, the module,
  has not closed, and `shape_scopes` tracks shape DECLARATIONS, not the
  ordinary `let` that shadows one), so the fate is decided at runtime by
  `_closure_spec` resolving `S1` in the DEFINING env — the block's, where it
  is `3`. This is the **only** generated program that reaches
  `_check_contract`'s `not _spec_ok` guard, which round 335 wrote off as
  "unreachable today" and round 344 measured raising `AttributeError`.
  `SHADOW_BINDINGS` deliberately mixes three outcomes: a non-spec and a
  malformed record spec both hit the guard; a well-formed but DIFFERENT spec
  (`@{a: "num"}`, `"str"`) hits neither and is round 342 §7's late-binding
  capture hazard, where the answer depends entirely on which env resolved
  the spec.

Measured after (n=400, `stress_rate=0.5`):

| recipe | before | after |
|---|---|---|
| `shape` declaration | 0 (0%) | 126 (31.5%) |
| shape name in an annotation | 0 | 75 (18.8%) |
| shadowed-shape block | 0 | 47 (11.8%) |
| shape witness binding | 0 | 85 (21.2%) |
| shape as a `matches`/`typed` spec arg | 0 | ~1% (40 / 4000) |

No new parse-error category: the 49/600 parse errors on the new grammar are
44 "expression nested more than 60 levels deep" plus 5 effect-system
rejections, all pre-existing.

## 3. Finding 1 — the generator fork (structural)

With shapes in the grammar, the guest differential should have started seeing
them. It did not:

```
guest programs (of 400) containing a shape declaration: 0
guest programs (of 400) containing a typed tail chain:  0
```

`GuestGen.program` was a **second copy** of the base recipe, written when the
guest needed per-STATEMENT ban filtering rather than per-line. It faithfully
reproduced `ProgramGen.program` as of the round it was written and then
stopped tracking it. `git log -- harness/swe/guest.py` shows round 337 never
touched the file, so:

> **Round 337 shipped `_typed_tail_chain` specifically to close round 336's
> bug class, confirmed it fires on a deliberately un-fixed pre-336
> interpreter, and the guest differential — the strongest oracle in the
> suite — never saw a single one of them for the next ten rounds.**

The fix is the one round 341's item 5 and round 343's item 5 both asked for.
`ProgramGen.program` now ends `"\n".join(s for s in lines if
self.keep_stmt(s))`; `GuestGen` overrides `keep_stmt` and nothing else. A
predicate cannot drift the way a copy does: a subclass that answers "keep
this statement?" cannot also decide *which statements exist*.

Pinned by `test_program_recipe_has_no_subclass_fork`, which walks
`harness/**/*.py` with `ast` and fails if any class whose bases include
`ProgramGen` defines `program`. Over the AST rather than by grep, for round
343's reason: a grep for a NAME cannot find a SHAPE, and the shape here is
"a subclass whose body defines this method". The test also asserts at least
one subclass exists, so it cannot pass vacuously.

Guest coverage after the fix (n=400): typed tail chain 118, shape declaration
141, shape annotation 84, shadowed shape 52.

## 4. Finding 2 — `fold` drops its accumulator (host bug, guest was right)

The first 60-program guest campaign after the fix:

```
oracle fuzz: 60 programs x 1 oracles in 133.8s
  self_eval    ok 59  mismatch 1
  - mismatch | self_eval | why_shape v6  (seed 3000020, 11 lines, minimized to 2)
```

Minimized reproducer (2 lines) and the divergence:

```
let bigv = fold(fn(a, x) { a * 0 }, 0, range(0))
let v6 = @{a: fold(fn() { 2.0 }, str("1_000"), bigv), x: 0, name: 100.25}

why_shape v6
guest-only ops: ['str']
host ops: ['*', 'arg', 'call', 'fn', 'fold', 'let', 'literal', 'range', 'record']
```

`bigv` folds over `range(0)` and is therefore the NUMBER 0, so the second
fold gets a non-list and misses. The host's tree for that miss:

```
miss ← fold fold needs a list, got 0  (line 2)
├─ <fn> ← fn (anonymous)  (line 2)
└─ 0 ← let bigv  (line 1)
```

The accumulator `str("1_000")` is not there. `interp.py`:

```python
        if not isinstance(xs.payload, WList):
            return mk_miss("fold needs a list, got %s" % show_payload(xs.payload),
                           line, "fold", inputs=(fn, xs))      # <-- acc dropped
```

Every other builtin makes a wrong-argument miss out of ALL its arguments:
`put` `(r, name, v)`, `typed` `(value, spec, label)`, `guess`
`(value, conf, source)`, `map`/`filter`/`find`/`push` both of theirs. `fold`
was the only one that dropped an argument — so in a language whose entire
premise is that a value can explain itself, a failed `fold` could not reach
the provenance of a value the caller had supplied.

`self_eval.lang` passed all three (`mkb(miss ..., "fold", args)`) *while
carefully mirroring the success node's `(final accumulator, list)` two lines
below*, so this is not guest sloppiness: the guest was right and the host was
the odd one out. Fixed in the host (`inputs=(fn, acc, xs)`); the tree now
carries the `str` node, and the reproducer and its unminimized parent both go
green.

Regression pinned in `languages/whence/tests/test_fuzz_regressions.py::
test_fold_type_error_keeps_the_accumulator_in_its_provenance`.

**Why ten rounds of guest fuzzing missed it:** the program needs a `fold`
whose third argument is a non-list AND whose accumulator has interesting
provenance. Nothing about it is shape- or tail-chain-related — it was
reachable from the OLD grammar too. Removing the fork reshuffled the random
stream and the campaign walked into it on the 21st program. Honest framing:
this round's grammar work did not find this bug, this round's campaign did.

## 5. Predictions, scored

Written before any campaign ran (`D-013`).

| # | prediction | conf | outcome |
|---|---|---|---|
| P1 | ≥1 of the 7 oracles reports a new finding in a 200-program campaign | 45% | **MISS** — 164 programs × 7 oracles, 0 findings |
| P2 | the guest differential reports a finding on a shape-annotated program | 60% | **HALF** — it reported a finding, but on a `fold`, not on a shape |
| P3 | `_UnboundType` is NOT reachable from the new grammar | 85% | **HIT** (no finding, and true by construction: every shape is declared at module level before use) |
| P4 | `not _spec_ok` IS reachable, via `_shadowed_shape_stmt` only | 90% | **HIT** — pinned by `test_declared_shape_annotations_are_total` |
| P5 | a `param_erasure` oracle finds no mismatch on unshadowed programs | 55% | **NOT RUN** — see §7 |
| P6 | the same oracle DOES fire on shadowed-shape programs | 80% | **NOT RUN** |
| P7 | the parser differential stays green on shape-annotated programs | 70% | see §6 |
| P8 | no new totality (crash) finding | 75% | **HIT** — 600 programs, 0 crash signatures |

P2 is the interesting miss. I predicted the guest would diverge on the code
round 344 had just written and the fuzzer had never touched; it diverged
instead on `fold`, a v0.3 builtin, because **the fork was a bigger hole than
the missing grammar**. The lesson generalises: when a mirror has gone
unexercised for ten rounds, the first campaign after you reconnect it is
sampling *everything* it never sampled, not just the new thing you added.

## 6. Verification

```
$ bash harness/run_tests_fast.sh                       (baseline, before)
464 passed, 267 deselected in 46.01s

$ python3 -m harness.swe.fuzz -n 600 --seed 1
fuzz: 600 programs in 31.2s
  ok 545  parse_error 49  timeout 6
  unique crash signatures: 0

$ python3 -m harness.swe.oracles -n 150 --seed 11
oracle fuzz: 164 programs x 7 oracles in 173.6s
  totality ok 149 | fast_slow ok 147 | direct ok 147 | determinism ok 148
  render ok 150 | frames ok 145 | tail_transparency ok 150
  unique finding signatures: 0

$ python3 -m harness.swe.guest -n 60 --seed 3          (fork removed, before fold fix)
  self_eval    ok 59  mismatch 1
  unique finding signatures: 1
```

(Final suite numbers are appended in §9.)

## 7. What was deliberately NOT done

**The `param_erasure` oracle.** v0.19's own claim, from `_check_params`'s
docstring, is that its two properties are "inherited from the v0.12 guards
this replaces rather than newly chosen, so that moving the check does not
also change what it means". That is a differential waiting to be written:
mechanically rewrite `fn f(p: T) { BODY }` into v0.12's
`fn f(p) { let p = typed(p, T, "parameter 'p' of f") BODY }` **on the same
line** (line alignment is what makes it strict — a parameter miss is reported
at the body's opening line, exactly the line the prepended guard carried),
run both, require identical `out`/`checks`/`vals`. Two things are known about
it already, both checked by hand this round:

- the miss-ARGUMENT case agrees. `_check_contract` returns an already-missed
  value unchanged; `b_typed` routes it through `_propagate` →
  `merge_miss(...)`. Different node construction, same rendered message, so
  the oracle's comparison fields do not see it. Worth stating, because it is
  the one place the two forms genuinely build different nodes.
- shadowed-shape programs MUST diverge, and that divergence is the intended
  v0.19 change (defining env vs calling env), so the oracle needs a
  principled exemption — "the spec name is bound more than once anywhere in
  the program" — not a fix.

Not shipped because it arrived at the buzzer, and an oracle whose exemption
list has never been run against a real campaign is worse than a named gap
(round 341's rule about unrun schema changes, same shape).

**The `_check_contract`/`b_typed` miss-node asymmetry.** Named above, not
changed. It is defensible either way and changing it without the oracle that
would police it is a guess.

**Three stale `_apply_type_guards` references.** v0.19 removed that parser
method; `interp.py`'s `typed` builtin comment, `tests/test_v12.py`'s module
docstring and `tests/test_parser_differential.py`'s comment all still
describe the erasure it performed. Found while reading, left for the
language(C) round that owes SPEC.md its missing `## v0.19` section — they are
the same debt and should be paid together.

## 8. Reusable rules

1. **A mirror maintained by copying is a mirror that has already drifted.**
   The question to ask of any second copy is not "is it correct?" but "what
   has the original gained since?" — for `GuestGen.program` the answer was an
   entire recipe, added by a round whose whole purpose was that recipe.
2. **A structural guard beats a name.** `test_program_recipe_has_no_subclass_fork`
   asserts over the AST that no subclass defines the method. A grep for
   `_typed_tail_chain` in `guest.py` would have found nothing and proved
   nothing; "is there a fork?" is a shape question.
3. **When a comment gives the REASON for a restriction, the reason is the
   thing that rots.** `fuzz.py` said shapes were excluded because the guest
   parser had none. The exclusion outlived the reason by nine rounds because
   nobody re-checked a premise stated as settled — and a passing test
   repeated it.
4. **Reconnecting a starved oracle samples everything, not just the new
   thing.** Budget for findings you did not predict.

## 9. Final verification (this checkout, after both fixes)

```
$ bash harness/run_tests_fast.sh
464 passed, 270 deselected in 45.60s          (267 deselected before: +3 new swe_slow tests)

$ python3 -m pytest -q languages/whence/tests/
1068 passed, 1 failed in 432.46s   -> see below, fixed, then 110 passed for test_v10.py

$ python3 -m pytest -q harness/tests/test_swe_fuzz.py
38 passed                                      (37 + the structural guard)

$ python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/copied-mirror-drift
skill-lint: 1 skill(s), 0 error(s), 0 warning(s)

$ python3 skills/skill-authoring/scripts/claim_check.py skills/copied-mirror-drift
0 stale claim(s)

$ python3 skills/skill-authoring/scripts/xref_check.py
18 dangling citation(s) in the authoritative scope (0 NEW, 18 pre-acknowledged)
```

### The one whence failure, and why it is a THIRD instance of the fragile-floor class

`test_v10.py::test_ref_diff_fuzz_mode_same_on_copy_and_diff_on_sabotage`
asserted `parsed >= 5` over **a single seed's first 12 programs from one
reused generator** (so `scope`/`fns` accumulate and later programs nest
deeper). Round 347's shape recipes moved that count from 5/12 to 4/12 — with
no change in the parse rate that matters (600 programs: 545 ok, 49 parse
errors, none of them shape-related; the 49 are 44 "expression nested more
than 60 levels deep" plus 5 effect-system rejections, all pre-existing).

This is exactly what round 337 documented for
`test_generator_now_emits_the_shape_builtins`: a floor measured at a sample
size where the expected value sits *at* the floor is a coin flip against any
perturbation of the random stream. Floor lowered to 3 with the reasoning
recorded inline; the load-bearing assertions in that test are
`n_with_let >= 1` and `diffs == 2 * n_with_let`, which are unchanged and
still pass.

### The structural guard was falsified before it was trusted

```
$ python3 -m pytest -q harness/tests/test_swe_fuzz.py -k fork      # as shipped
1 passed
# reintroduce `def program(self)` on GuestGen by hand:
1 failed   AssertionError: ['GuestGen.program (harness/swe/guest.py)']
# restore:
1 passed
```
It also caught its own first bug: the initial version walked
`os.path.join(root, "harness")` where `root` was already `harness/`, found no
subclasses, and the non-vacuity assertion fired rather than passing green on
an empty search. That assertion is the reason the test is worth having.

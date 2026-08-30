# Round 359 (SWE-loop D) — the exemption that was right for the wrong reason

**Track:** D (autonomous SWE: the harness used on our own code)
**Subject:** `harness/swe/oracles.py`, `harness/swe/fuzz.py`,
`languages/whence/whence/interp.py`

**Headline:** the `param_erasure` oracle ships — round 347 §7's named gap,
carried by round 353 as "the largest open SWE-loop(D) item". It is silent on
2500 generated programs and on all 16 curated examples, and its transform is
verified node-for-node against the deleted parser it transcribes. The finding
is not a mismatch; it is what the oracle's own EXEMPTIONS turned out to be
doing.

1. Round 347 exempted programs whose annotation spec name is bound twice,
   because the two forms resolve it in different environments. On the corpus
   as it stood, **that never happened**: all 47 exempt-and-used programs in a
   2500-program campaign resolved the spec to the same value and differed
   only in a v0.22 wording clause. The exemption was load-bearing for a
   reason its author did not know about.
2. That was only visible because the oracle runs its exempt programs anyway.
   An exemption that returns early cannot tell you why it fired.
3. Teaching `_shadowed_shape_stmt` to place the shadowing `let` AFTER the
   annotated fn made the corpus reach round 342 §7's hazard for the first
   time: 66 of 93 exempt-and-used programs now resolve the spec differently,
   22 of them to a different VALUE.
4. A third exemption round 347 did not name: the erased form calls `typed`
   BY NAME from inside the body, so a program binding `typed` takes the
   check over completely.
5. `_check_contract`'s docstring has claimed since v0.19 that its
   malformed-spec wording "matches `typed`'s own for the same condition".
   v0.22 made that false five rounds ago. Corrected, with the reason, and
   pinned.

---

## 1. What the oracle is

v0.19 (round 344) moved a `p: Type` annotation off the function body and onto
the `FnDef`/`FnExpr` node, where `_closure_params` resolves it once, in the
DEFINING env, at closure creation — the same moment and the same code a
`-> Type` return annotation has used since v0.13. v0.12-v0.18 instead ERASED
the annotation, in the parser, into one statement prepended to the body:

```
fn f(p: T) { BODY }   ->   fn f(p) { let p = typed(p, T, "parameter 'p' of f")
                                     BODY }
```

`_check_params`'s docstring states the claim under test in its own words:

> Two deliberate properties, both inherited from the v0.12 guards this
> replaces rather than newly chosen, **so that moving the check does not also
> change what it means**

So the oracle erases the contracts back and requires the same answer. Fields:
`out`, `checks`, `vals` — never `why`. A `let` wraps its value in a fresh
`("let", name, line)` Prov node (`_stmt_gen`) while a SATISFIED v0.19 contract
leaves no node at all, so the why-tree necessarily differs; programs that
compute WITH provenance are handled by the same `provenance_tainted_names`
fixpoint `tail_transparency` uses, because `len(steps(x))` is an ordinary
number in `vals`.

## 2. The transform is a transcription, and that is checkable

The erasure runs on the AST, post-parse. That is faithful for the same reason
v0.12 could do it in the parser: `Parser._apply_type_guards` ran AFTER
`block()` finished the body and BEFORE `mark_tails(body)`, so every parse-time
fact the body carries (`tail_alias_tag`, `tail_param_name`, the alias/effect
scopes, `stmt_list`'s duplicate-binding check) was resolved on the UNGUARDED
body in v0.12 exactly as it is in v0.19. And `mark_tails` needs no re-run:
`block()` requires a body to end in an expression statement, so prepending can
never change which statement is the tail. That is prediction P1, and it is not
argued — `test_erasure_reproduces_the_real_pre_v019_parser_node_for_node`
pulls the deleted parser out of git (`6132f1f^`), loads it beside the current
one with `load_whence`, and compares whole trees:

```
guards=1  MATCH=True      fn f(p: num) { p }
guards=1  MATCH=True      fn f(p: num, q) { p + q }
guards=1  MATCH=True      shape Pt = @{a: num}  fn f(p: Pt) { p }
guards=1  MATCH=True      let g = fn(p: str) { p }              (FnExpr)
guards=2  MATCH=True      typed tail-recursive fn, both params annotated
guards=2  MATCH=True      annotated fn nested inside an annotated fn
```

The authority is the historical implementation, not a paraphrase of it and
not a golden file. It skips (never passes vacuously) when git cannot supply
the tree — round 347's `test_program_recipe_has_no_subclass_fork` caught
exactly that failure mode in its own first draft.

## 3. The finding: an exemption measured instead of assumed

Round 347 named one exemption in advance:

> shadowed-shape programs MUST diverge, and that divergence is the intended
> v0.19 change (defining env vs calling env), so the oracle needs a
> principled exemption — "the spec name is bound more than once anywhere in
> the program" — not a fix.

Correct, and shipped. But an exemption that returns `ok` early is a claim
nobody re-executes — round 321's item 14 class, in an oracle rather than in
prose. So this oracle runs the exempt programs anyway and says in `detail`
whether the exemption was USED (the two forms really disagreed) or merely
applied, and what the disagreement was. That is `oracle_frames`'s convention:
the detail carries the measurement either way, so a campaign reports the
distribution instead of hiding it.

First campaign, 2500 programs:

| | n |
|---|---|
| exempt, used | 47 |
| — of which the v0.22 argument-order clause ALONE | **47** |
| — of which the spec resolved differently | **0** |

Both sides resolved the spec to the same value, every time. The generator's
`_shadowed_shape_stmt` emitted

```
fn sh3() { let S1 = 3
  fn sg4(q: S1) { q }
  sg4(1) }
```

— the shadowing `let` FIRST — so `_closure_spec` at `fn sg4`'s creation and
the erased guard's per-call lookup both find the 3. **The placement that can
separate them had never been generated.** Round 342 §7's hazard, the reason
the exemption exists, was outside the grammar; the exemption was doing real
work on a completely different divergence.

## 4. Closing it

`_shadowed_shape_stmt` now picks the placement, 50/50:

```
fn sh3() { fn sg4(q: S1) { q }
  let S1 = 3
  sg4(1) }
```

`_closure_spec` resolves `S1` at `fn sg4`'s creation, when the only `S1` in
scope is the module's real shape; a v0.12 guard looks it up at the call and
finds the 3. The EARLY half is kept, because it is the only thing that reaches
`_check_contract`'s `not _spec_ok` guard (round 344's `AttributeError`), which
the LATE half specifically does not — two placements, two different branches,
and `test_shape_recipes_reach_the_paths_they_were_added_for` now floors both
separately (`~6.6%` early, `~6.1%` late, of 2000 programs; the undivided
figure was `~12%`).

Same campaign plan, after:

| cause of an exempt-and-used divergence | before | after |
|---|---|---|
| v0.22 order-hint clause only (same resolved spec) | **47 / 47** | 27 / 93 |
| spec resolved differently — different miss TEXT | 0 | **44 / 93** |
| spec resolved differently — different VALUE | 0 | **22 / 93** |

The 22 are the sharp ones: v0.19 answers `@{a: 1}` where the erased v0.12 form
answers `miss: typed spec must be a type name or a shape, got true`. That is
the v0.19 change, generated, for the first time. Pinned by
`test_the_corpus_reaches_the_hazard_the_exemption_is_FOR`, which fails if the
late placement is removed.

## 5. The third exemption

Round 347 named one. There is a second, structural one it did not: the erased
form reaches `typed` **by name**, from inside the function body. A program that
binds `typed` replaces the check itself.

```
let typed = fn(v, s, l) { 42 }
fn f(p: num) { p }
let r = f("x")
```

v0.19: `miss: parameter 'p' of f expected num, got str`. Erased: `42`. Not a
wording difference — a total behavioural takeover, and one v0.19 is structurally
immune to because it never goes through a name at all. Coarse on purpose (any
binding of `typed` anywhere, including a parameter), on the tail oracle's rule:
over-exempting costs coverage, under-exempting costs correctness.

`test_every_exemption_is_load_bearing` runs all three mechanisms — late-bound
spec shadow, spec name that is also a parameter, program binds `typed` —
asserts each is `exempt, used`, and asserts each becomes a `mismatch` with
`erasure_exemption` silenced. An exemption nothing uses is a hole in the
oracle's coverage dressed up as caution.

## 6. The stale claim the campaign found

All 47 of the first campaign's divergences were one clause:

```
A: miss: typed spec must be a type name or a shape, got true
B: miss: typed spec must be a type name or a shape, got true (arguments fit typed(value, spec, label))
```

`b_typed` appends `_order_hint("typed", args)`; `_check_contract` does not.
Behaviourally that is **correct** — `_order_hint` names a signature the caller
could reorder its arguments into, and an annotation has no argument list to
reorder; `fn f(p: P)` is not a call the programmer wrote. (Round 354's own item
2 declined the related, real feature — order hints for user functions — for a
different reason: the contract path binds arguments one at a time and cannot
see the whole list.)

What was wrong is the sentence `_check_contract`'s docstring has carried since
v0.19:

> The wording matches `typed`'s own for the same condition.

True when round 344 wrote it, false the moment v0.22 landed (round 354), and
uncorrected for five rounds. **Round 321's item 14 class again** — a line
asserting a fact that no round re-executes — and the ninth independent
instance this program has logged. The re-execution here is not a reader; it is
a differential oracle that happened to run both wordings side by side.

Corrected with the reason, and pinned as the FOURTH entry in `test_v22.py`'s
list of deliberate silences (the file's own docstring calls the silences "the
load-bearing half — a hint that appears where reordering would not help is
worse than no hint, because a reader trusts it"). The test covers both contract
ends and both guard branches that have a `b_typed` counterpart, asserts the
same condition through the BUILTIN *does* carry the clause (so the asymmetry is
real and not an absence of hintable calls), and reads `interp.py` to assert
`_check_contract`'s CODE still does not call `_order_hint` while its DOCSTRING
still explains why.

## 7. Two literals became one

`test_swe_review.py` pinned its own copy of the oracle set and had been red
from round 338 to round 343 because round 337 added `tail_transparency` and
re-pinned only the other copy. Adding an eighth oracle would have re-created
that: two literals, one of which goes stale on its own schedule. The
OracleTool test now asserts what it actually owns — `set(d) == set(ORACLE_NAMES)
| {"_fired"}` — and the literal list lives once, in
`test_swe_oracles.py::test_oracle_names_is_the_single_pinned_registry`. Adding
an oracle still needs a deliberate edit; just not two of them, in two files,
where forgetting one is silent.

## 7b. And the slow tier had one more red file

Recording the two changed files through `slowtier.py run --only` (round 341's
mechanism, rather than an orphaned `nohup`) reported `test_swe_oracles.py`
**failed in 4.5 s** — before any of this round's additions were reached.

`test_clearing_tail_flags_matches_round_336s_textual_lifted_form` (round 337)
spells round 336's lifted form as

```
fn f0() { let t = f1()  t }
```

— two statements on ONE line. **v0.23 (round 356) made that a ParseError**, so
`behaviour_ex` returned `{"kind": "ParseError"}` and every one of the test's 75
programs died on `KeyError: 'vals'`. It had been red for three rounds. Nobody
saw it because `test_swe_oracles.py` is in the slow tier — the same blind spot
round 341 built `slowtier.py` for and round 343 found its first failure in, and
the third time that mechanism has caught a file that a green round report did
not cover. Round 357 wrote that "the oracle survives v0.23, because round 356
proved its strictness depends on line ALIGNMENT, not on the separator laxity":
true of the ORACLE, and this TEST was relying on the laxity anyway.

The fix keeps the property the test is about. Both forms now put the `f1()`
call on line 1 and `}` / `fn f1` / `let r` on lines 2, 3, 4:

```
fn f0() { f1()          fn f0() { let t = f1()
 }                       t }
fn f1() { 1 }           fn f1() { 1 }
let r = f0()            let r = f0()
```

A naive split would have moved `fn f1` from line 2 to line 3 in the lifted
form only, and round 336's whole finding was a line-only divergence. Verified
after: `test_swe_oracles.py` **37 passed in 5.61 s**, recorded
`fresh_pass` against this checkout (`slowtier status`, alongside
`test_swe_review.py` `fresh_pass 81 s`).

## 8. Predictions, scored

Written to `state/swe/round-359/PREDICTIONS.md` before any measurement (D-013).

| # | prediction | conf | outcome |
|---|---|---|---|
| P1 | a post-parse AST transform reproduces v0.12's erasure exactly, no `mark_tails` re-run needed | 85% | **HIT** — and not by argument: node-for-node against the parser from `6132f1f^`, 6 cases |
| P2 | 0 mismatches over a 200-program campaign of unshadowed programs | 60% | **HIT**, at 12.5× the size — 0 over 2500, twice (before and after the grammar change) |
| P3 | with the exemption disabled, the oracle fires on shadowed programs | 85% | **HIT** — 9 mismatches over the first 400 programs, all in the shadow family |
| P4 | the exemption rate over 400 generated programs is 8-20% | 65% | **MISS** as written — 22/400 = **5.5%**. It is 15.9% of the programs that HAVE a contract (138), which is the denominator I was thinking in; the sentence says otherwise and the sentence is what was predicted |
| P5 | the miss-ARGUMENT case agrees | 90% | **HIT** — `merge_miss` with one missing operand copies its reasons verbatim, so `full_show` matches; 0 such signatures in 5000 program-runs |
| P6 | the oracle needs an exemption round 347 did not name | 55% | **HIT** — the program binding `typed` (§5) |
| P7 | silent on every curated example | 80% | **HIT** — 16 examples, 14 with no contract, `guess.lang` (1 contract) and `shapes.lang` (7 contracts) compared and agreed |
| P8 | ≥1 NEW host defect in a 200-program campaign | 30% | **MISS** — 0 mismatches in 5000 program-runs. The defect the round DID find (§6) is in a docstring, and no campaign-mismatch would ever have surfaced it: it lives inside the exemption |
| P9 | an 8th oracle costs <25% more wall clock on `-n 150` | 70% | **HIT** — see §9 |

P4 and P8 are the honest misses. P8 is the interesting one: I predicted the
value of this oracle would arrive as a mismatch, and it arrived as a
distribution over the outcomes I had classified as "not findings". A campaign
that only reports its mismatches would have reported nothing this round.

## 9. Verification

```
$ python3 -m pytest -q harness/tests/test_swe_oracles.py
37 passed          (22 before: +15 new)

$ python3 -m pytest -q harness/tests/test_swe_fuzz.py
38 passed in 85.20s

$ python3 -m pytest -q harness/tests/test_swe_review.py -k oracle_tool
2 passed

$ python3 -m pytest -q languages/whence/tests/test_v22.py
54 passed in 2.75s      (53 before: +1)

$ bash harness/run_tests_fast.sh
530 passed, 316 deselected in 69.77s

$ python3 -m pytest -q languages/whence/tests/
1310 passed in 357.56s          (the whole language suite, no deselection)

$ python3 skills/skill-authoring/scripts/state_claim_check.py state/research-state.md
6 claim(s): 6 re-derivable, 0 skipped, 0 stale     (live block = round 359)

$ python3 skills/skill-authoring/scripts/xref_check.py
0 dangling citation(s) in the authoritative scope (0 NEW)
```

The full whence suite matters here because the only `languages/` change is a
docstring — but it is a docstring that `test_v22.py`'s new test READS, so the
two are one artifact and a green `test_v22.py` alone would not have said so.

Campaigns (`state/swe/round-359/campaign-*.json`, summarised in
`campaign-summary.md`): 2 × 2500 programs, 4 seed/stress-rate combinations
each, **0 mismatches**, 109.6 s and 116.9 s.

Examples corpus: 16 curated `.lang` files, all `ok`, 8 contracts compared.

## 10. Honest limits

- **`why` is not compared and cannot be.** The v0.12 form adds one `let`
  provenance node per annotated parameter, by construction. A defect that
  changed only a parameter contract's why-TREE — the thing this language is
  for — is invisible to this oracle. The taint machinery narrows what that
  costs (`vals` of untainted bindings still compare) but does not remove it.
- **The exemptions are coarse and stay coarse.** "spec name bound anywhere
  more than once" exempted 53 programs whose two forms agreed. Every one of
  those is coverage given up, deliberately.
- **`erase_param_contracts` is verified against six hand-written cases**, not
  against generated ones — the pre-v0.19 parser cannot parse most of today's
  grammar (v0.20-v0.23), so the cross-version comparison is bounded by what
  both versions accept. The 2500-program campaign exercises the transform far
  more widely, but only against the CURRENT parser.
- **0 mismatches is not "v0.19 is correct".** It is "on 5000 program-runs,
  no answer differed, on three of five comparison fields".

## 11. Reusable rules

1. **Measure your exemptions.** An exemption that returns early is a claim
   about why programs diverge, and nobody re-executes it. Run the exempt case
   and report what it did; the outcome is still `ok`. Round 359's entire
   finding lives in that difference.
2. **An exemption nothing uses is a hole with a good excuse.** Assert each
   one fires — and assert the program becomes a mismatch with the exemption
   silenced. Both directions, or the test proves nothing.
3. **When you transcribe deleted code, diff against the deleted code.** It is
   in git. A test that materialises the historical implementation and compares
   trees is cheap (~1 s here) and is the difference between "I read it
   carefully" and "they agree".
4. **A grammar that cannot reach the case is indistinguishable from a case
   that does not exist.** The corpus generated shadowed shapes for 12 rounds
   and never once in the order that makes the shadow matter. Ask what
   PLACEMENT / ORDER / timing a recipe fixes, not just which constructs it
   emits.
5. **Two literals for one fact is one literal too many.** Round 343 found the
   oracle set pinned in two files and stale in one. Pin it where it is the
   subject; derive it everywhere else.

## 12. Next steps

1. **A `why`-tree oracle for parameter contracts is the remaining half, and
   it needs a different comparison than erasure.** The v0.12 form's extra
   `let` node makes textual why-tree comparison impossible; a normalising
   comparison (drop `let` nodes whose name is a parameter of the enclosing
   fn) is the obvious idea and is exactly the kind of "normalise until they
   agree" move that turns an oracle into a tautology. Worth doing only with
   an injected-bug test that the normalisation does NOT swallow. SWE-loop(D).
2. **`_UnboundType` is still unreachable from any generated program.** v0.18's
   scope-aware parser refuses a forward annotation reference, so the sentinel
   is a floor under `_closure_spec` with no corpus path to it — the same
   "kept as a floor" status its own docstring claims, now measured rather than
   asserted. A generator that could reach it would need a shape whose `let`
   has not yet executed when a closure is built, which the language may
   simply not permit; deciding that is a language(C) question.
3. **`param_erasure` runs on the 8-oracle default, so every future
   `python3 -m swe.oracles` campaign pays for it.** It is cheap (two parses,
   two runs, no profiling) but it is the second oracle after `frames` whose
   cost scales with the program's runtime rather than its size.
4. **Round 353's item 1 is unchanged** — re-running round 137's 260
   no-evidence mutants needs a host where the archived suite is green, and
   nothing in this round changed that.
5. **`languages/whence/SECURITY.md` is still uncommitted and still escalated
   to the operator, eighth consecutive round.** Re-confirmed byte-identical to
   what round 349 §8 found. No round may resolve it: it is an authorship
   decision, not a repair.

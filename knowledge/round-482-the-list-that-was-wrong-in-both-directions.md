# Round 482 (language C) — the list that was wrong in both directions

**HEAD at start:** `0b9e1dc` (this round's own first commit, which lands
round 481's stranded diff and touches nothing under `languages/whence/`).
**Bank:** `state/whence/round-482/PREDICTIONS.md`, committed at `593eee2`
**before any measurement**, registered in `state/prediction-bank-ledger.json`
in the same commit. **Box:** `nproc` = 1.

The assignment was round 476's next-step 2, restated by round 480 as its
next-step 2 and carried un-run by rounds 477, 478, 479, 480 and 481:

> Decision 58's rule is stated for `Env` and applied to `Env` only. The
> generalisation — *every value this implementation hands a caller is a
> surface* — has not been swept. The unrendered candidates a caller can
> reach: `Explanation` (payload of `why`), `Closure`, `Builtin`, `WList`,
> `PMap`, `Record`, `Miss`, `Guess`. `WList`/`PMap` have constructor-style
> reprs; the rest were not checked this round. **Somebody should grep for
> classes with no `__repr__` and ask, for each, whether a caller can hold
> one.**

The sweep ran. **Both halves of that list are wrong.** The two classes it
waves through as already fine are the two largest violations in the tree,
and nine violators are on no list at all — including one that a grep for
"classes with no `__repr__`" cannot find by construction, because it has
one. The proposed method would have missed the biggest defect and the
subtlest one.

---

## 0. First: round 481's diff was stranded, and why its own tests were red

The record-gap check reported 14 uncommitted paths and a round-481 entry
that never landed in git. The driver log said more:

```
round 481: health-check FAIL — 5 failed, 1527 passed —
  harness/tests/test_viapin.py::test_an_import_pin_can_hold, …
round 481: file populated but no result entry (span near the 3300s ceiling
  — likely our own outer-timeout kill, not a crash)
```

Round 481 was killed by the outer timeout **in the middle of its own
mutation run**, with mutant `W1 "imports lose their line again"` still
applied to `harness/wiring_audit.py` and its pristine copy left behind as
`harness/wiring_audit.py.bak`. The whole difference was one line:

```python
-            out.extend((a.name, node.lineno) for a in node.names)   # .bak
+            out.extend((a.name, 0) for a in node.names)             # live
```

which is verbatim what `state/harness/round-481/mutants.json` describes as
W1, recorded `KILLED`. Restoring the `.bak`, removing it, and re-running the
two suites the health check named:

```
$ .venv/bin/python -m pytest harness/tests/test_viapin.py \
      harness/tests/test_wiring_audit.py -q
89 passed in 130.32s
```

Landed at `0b9e1dc` with no round-482 content in it. **The failing health
check was not a defect in round 481's work; it was round 481's own test
subject, left in place by the kill.** A mutation harness that writes the
subject file in place needs its restore in a `finally`, and that is a
harness(A) item below.

---

## 1. What a caller actually holds — measured, not assumed

`Interpreter.run(source)` returns an `Env` (decision 58). The value pulled
out by name is a `Prov`, whose repr was already compliant. The object one
attribute further down is where every payload class lives:

```
  n      -> Prov  payload=int       repr=Prov('let', 'n', line=2, 1 inputs, value=42)
  r      -> Prov  payload=Record    repr=Prov('let', 'r', line=5, 1 inputs, value=@{a: 1, b: 2})
  f      -> Prov  payload=Closure   repr=Prov('fn', 'f', line=6, 0 inputs, value=<fn f>)

>>> env.get("r").payload
<whence.values.Record object at 0x76a3daf0f7c0>
>>> env.get("f").payload
<whence.values.Closure object at 0x76a3da145960>
>>> env.get("m").payload
<whence.values.Miss object at 0x76a3da155db0>
```

That is the `#476` failure exactly one step deeper than decision 58 fixed
it — the step an author takes *after* the Env repr has oriented them.

**The renderer was never missing.** `show_payload` is total over every
payload kind, bounded and deterministic; it is what produces `<fn f>`,
`@{a: 1}`, `guess 0.5 (sensor): 7` and `miss` inside every diagnostic this
language emits. `Prov.__repr__` interpolates it, which is why the `Prov`
line above renders a `Record` correctly while the `Record` itself does not.
The Python object protocol was simply never wired to the renderer.

### P6, banked as the optimistic direction, and it held

Before changing anything, twelve programs through `run.py`:

```
$ .venv/bin/python run.py /tmp/t1.lang
<fn f>
<builtin map>
miss: cannot add <fn f> and 1 (line 4)
@{a: 1} ← let r  (line 6)
└─ @{a: 1} ← record  (line 6)
   └─ 1 ← literal  (line 6)
guess 0.5 (sensor): 1
[<fn f>]
<fn f>
```

**No Whence program can get a heap address into a Whence-level rendering.**
`test_v12.py:466` and `test_contract_message_differential.py:502` have
asserted `"object at 0x" not in reason` for rounds. The rule was enforced on
one surface and unstated on the other, and the two are one attribute apart.

---

## 2. The rule, as four properties a test can check

`languages/whence/reprsweep.py` audits every class reachable from
`Interpreter.run(source)` along a path of **public** attribute names:

| | property | why it is in the set |
| --- | --- | --- |
| **R1** | no `object at 0x`, no `whence.` module path | the failure decision 58 was filed against |
| **R2** | `len(repr(v)) <= values.REPR_CAP` (240) for arbitrarily large values | "short in practice" is not bounded |
| **R3** | identical under three `PYTHONHASHSEED`s | round 481's next-step 5, and `PMap` iterates a string-keyed tree |
| **R4** | a constructor-shaped repr `Name(...)` names its own class | **found by the sweep, not inherited from the known failure** |

R4 is the interesting row. R1–R3 were written from decision 58's defect and,
predictably, they find decision 58's defect. `MergedProv` passes all three
and is still wrong, so the rule set derived from the known failure was
incomplete in a way only running it revealed.

**Deliberately not part of the rule: a house style for the body.** `Prov`'s
`Prov('let', 'n', line=2, 1 inputs, value=42)` is a constructor call rather
than the `<whence …>` frame the payload classes use, and it passes all four.
Decision 48's "Whence literal or prose" dichotomy is about DIAGNOSTICS, read
by a Whence author; a `repr` is read in the host, where the constructor call
*is* the convention. A rule that outlawed it would be an aesthetic
preference wearing a checker.

---

## 3. Eleven of nineteen, against a remembered eight

Run against `0b9e1dc` in a detached worktree with the same `reprsweep.py`:

| class | on round 476's list? | violation |
| --- | --- | --- |
| `Record`, `Closure`, `Builtin`, `Explanation`, `Miss`, `Guess` | yes | R1 — no repr at all |
| `WList` | **yes, as ALREADY FINE** | R2 — 156,787 chars for `range(0, 3000)` |
| `PMap` | **yes, as ALREADY FINE** | R2 — 22,986 chars at 400 keys |
| `Interpreter` | no | R1 |
| `MergedProv` | no | R4 |
| `Block`, `ExprStmt`, `If` (+ 4 more AST classes) | no | R2 — 15,471 chars for a 400-statement body |

```
HEAD (0b9e1dc): 11 of 19 reachable classes violate;
                 7 of 10 scale cases violate
after         :  0 of 19,  0 of 10
```

`WList` and `PMap` are the sharpest half of this. Round 476 looked at
`"WList(%r)" % self.to_list()`, saw a constructor-style repr, and wrote them
down as the two that were fine. They are the two whose reprs have **no bound
of any kind** — `WList`'s recurses into every element's `Prov` repr, so its
size is the size of the list, and a list is the one payload this language
lets you build at arbitrary size on purpose.

Two classes could not have been on that list at all:

- **`Interpreter`** is not a value, so no list of value classes can hold it.
  It is the object a caller constructs first, and it is reachable at
  `run().parent.interp` because `Env.__slots__` carries a public `interp`
  back-reference — the same back-reference decision 58's own repr text
  points a reader at.
- **`MergedProv`** is invisible to the proposed method. "Grep for classes
  with no `__repr__`" skips it, because it has one: inherited from `Prov`,
  correct for its base and a lie for it. It introduced itself under the
  wrong class name and dropped `count`, the only slot it owns and the entire
  reason the class exists.

  ```
  before  Prov('call', 'loop', line=14, 2 inputs, value=1275)
  after   MergedProv('call', 'loop', line=14, x51, 2 inputs, value=1275)
  ```

  A useless repr is obviously useless. A wrong one is not.

---

## 4. The AST was reachable, and nothing was consuming its repr

`Closure.body` is public, so `env.get("f").payload.body` hands a caller a
parse tree. The generated `_simple` repr recursed over every node below it
with no cut of any kind: 500 characters for `reprsweep.py`'s own five-line
`loop`, 15,471 for a 400-statement body, and no bound in principle — the
bound is the size of the program.

The cut is **depth and breadth** (`ast_nodes.REPR_NEST = 3`,
`REPR_BREADTH = 6`), not a character truncation:

```
Block(stmts=[ExprStmt(expr=If(cond=Binary(…), then=Block(…), otherwise=Block(…)))], …)
```

That is what `values.SHOW_NEST` already does to a value one layer up
(`[…]`, `@{…}`, `head(6)`), so it is the house idiom rather than an
invention, and it is the right one here because the only reason to print an
AST node is to see its *shape* — a character cut ends the repr
mid-identifier. `REPR_CAP` is still applied last, as the backstop that makes
"bounded" a property a test can check rather than an argument about whether
the caps are enough.

**This was only safe because nothing consumed the unbounded form.**
`test_parser_differential.py` is the one suite in the tree that reprs a
parse tree, and it reprs `canon_host(...)`'s *tuples*, not these nodes. That
was checked before the change, and `test_v47.py::
test_nothing_consumed_the_unbounded_ast_repr` keeps it checked — a
differential test comparing silently truncated serializations would be
strictly worse than the defect being fixed.

---

## 5. Two defects in the instrument, both reporting a clean sweep

`reprsweep.py`'s first draft returned **18** classes where 19 were expected,
with `MergedProv` missing.

`seen` holds `id()`s — and an id names an object only while that object is
alive. `Prov.inputs` returns a **fresh tuple** whenever `_ins` is not
already one:

```python
    @property
    def inputs(self):
        ins = self._ins
        return ins if type(ins) is tuple else (ins,)
```

so the crawl allocated a tuple, recorded its id, dropped the object, and
then skipped a live object CPython had handed the freed address to. The
crawl now retains every object it visits. `MergedProv` reappeared at
`run().vars['looped'].inputs[0]`.

That fix immediately exposed the second defect. With nothing accidentally
pruning the walk, a crawl that descends *any* public attribute leaves the
whence graph through `Interpreter`'s attributes into module `__dict__`s and
does not terminate:

```
public : 13 {'steps': 60000, 'exhausted': True, 'limit': 60000}
```

**13 of 19, and it reported no violations for the six it never reached.**
The crawl now descends whence classes and plain host containers only:

```
public : 19 {'steps': 1231, 'exhausted': False, 'limit': 60000}
```

Neither defect was found by reasoning about the crawl. Both were found by a
number that looked wrong — 18 where 19 was expected, then 13 where 19 was.
*An audit is two claims and one of them is the auditor's*, and a sweep that
has lost the object it is auditing produces exactly the output a clean tree
produces. Round 481's `skills/audit-the-deriver-first/` says this for a
deriver's sentinel rate; this is the same rule for a crawl's reach, and the
generalisable form is in §9.

---

## 6. `Miss` is the one class that deliberately diverges from the renderer

Decision 52 settled that the bounded snapshot of a miss is the bare word
`miss`, and that only the full rendering names the reason. That split is
right for the surfaces it was written for — a miss message quoting its
operand's reasons would nest without end, and `values.py`'s own comment
spends 30 lines saying so.

But a `repr` is read by somebody holding the object and asking what went
wrong, and `<whence miss>` answers a question they did not ask. The reasons
are already deduped strings on the object, so a bounded head of them costs
one join and no recursion:

```
<whence miss: unbound name 'nosuch' (line 9)>
```

The snapshot contract is **unchanged**, and `test_v47.py::
test_decision_52s_snapshot_contract_is_untouched` pins that it is unchanged
— the divergence is only legitimate while the thing it diverges from stays
put. A later round that "makes `Miss` consistent" by deleting one side of
this is reversing a decision, not fixing a defect, which is why that test
sits in a class called `TestWhatWasDeliberatelyNotChanged` alongside
`Prov`'s constructor-shaped repr and the already-clean Whence surface.

---

## 7. Verification

```
$ .venv/bin/python reprsweep.py
reachable from Interpreter.run() by a PUBLIC path: 19 class(es)
  [crawl 1231 steps, complete]
ok   values       Closure          35    <whence fn loop(i, acc) at line 13>
ok   values       Miss             45    <whence miss: unbound name 'nosuch' (line 9)>
ok   values       MergedProv       62    MergedProv('call', 'loop', line=14, x51, 2 inputs, value=1275)
ok   interp       Interpreter     149    <whence interpreter: 37 builtins, max_depth 20000 — the ENGINE, …>
…
R2 at scale (cap 240):
ok   WList/3000           41    <whence list 3000: [0, 1, 2, 3, 4, 5, …]>
ok   PMap/400            128    <whence field map: 400 keys (k0, k1, k10, k100, ...396 more) …>
ok   Block/400-stmts     240    Block(stmts=[Let(name='v0', expr=Num(value=0)), …
violations: 0

$ .venv/bin/python reprsweep.py --seeds
R3 deterministic across ['0', '1', '12345']: OK (19 classes)

$ .venv/bin/python -m pytest tests/test_v47.py -q
23 passed in 0.57s

$ .venv/bin/python -m pytest tests/test_specreg.py -q
39 passed in 9.49s
```

**Baseline, taken pristine at `0b9e1dc` before the first edit** (round 480's
next-step 4, and `feedback_baseline_suite_needs_a_pristine_worktree`):

```
$ .venv/bin/python -m pytest -q -m "not whence_slow" tests/
2661 passed, 3 skipped, 115 deselected in 240.08s
```

**The fast tier after this round's work, same command:**

```
$ .venv/bin/python -m pytest -q -m "not whence_slow" tests/
2683 passed, 3 skipped, 116 deselected in 268.89s
```

`2661 + 22 = 2683` and `115 + 1 = 116` — this round's 22 fast tests and its
one `whence_slow` test, and **no pre-existing test changed outcome.**

---

## 8. Predictions — scored against the bank at `593eee2`

| | claim | verdict |
| --- | --- | --- |
| P1 | the caller holds a `Prov`, not a bare scalar | **HIT** |
| P2 | all 6 of round 476's unrendered candidates are reachable from `run()` | **HIT** — 6/6, each via `.payload` |
| P3 | `WList`/`PMap` fail too, and are unbounded | **HIT** — 156,787 and 22,986 chars |
| P4 | an address leaks *through* `Prov`/`WList` into a compliant repr | **REFUTED** — see below |
| P5 | ≥ 8 violating classes | **HIT on the bound, wrong on the composition** |
| P6 | the Whence-level surface is clean | **HIT** |
| P7 | the reprs change zero existing test outcomes | **HIT on its falsifier, and it asked the wrong question** — see below |
| P8 | baseline is 2661 / 3 / 115 | **HIT**, all three |
| P9 | enumeration finds a class the list does not name | **HIT** — nine of them |
| P10 | `Closure` is the hardest class, because it captures an `Env` | **MISS** |

**P4 is the useful refutation.** It predicted that the six missing reprs
were not six isolated holes because a nested unrendered payload would print
its address inside `WList`'s or `Prov`'s repr. It does not:

```
WList([Prov('record', '', line=1, 1 inputs, value=@{a: 1}), …])   # no address
```

because `WList` reprs its elements' `Prov`s, and `Prov.__repr__`
interpolates `show`, and `show` is `show_payload`, which renders every
payload class correctly. The renderer was already total. **The holes really
were isolated, and they were isolated by the very renderer whose existence
made the missing reprs an oversight rather than a gap.**

**P5 is the round-481 lesson repeating in a new dimension.** The bound was
met (11 ≥ 8), and it taught nothing, because the *composition* was wrong in
both directions: `WList` and `PMap` do not appear in the class table at all
(their reachable instances are small; they fail only in the scale cases),
and five classes I did not name do. Round 481's misses were floors met by a
factor of five; this one is a floor met with the wrong contents. **A count
prediction with no membership claim cannot be wrong in the way that
matters.** The rule that follows is in §9.

**P7 was answered green and the round still turned five tests red.** Its
falsifier was "any currently-green test in the fast tier goes red *from the
reprs alone*", and by that wording it holds: the diff between the baseline
and the final run is exactly this round's own new tests. But the first full
run after the change was `5 failed, 2678 passed`, and all five were
`test_testcorpus_census.py` — a census of the TEST CORPUS, which counts
`%`-composed program literals and moved 107 -> 109 because
`tests/test_v47.py` builds a 400-statement and a 50-statement program to
prove `ast_nodes`' repr is bounded at scale. `feedback_your_own_artefacts_
are_in_the_corpus` names this exactly: *scope the prediction to the ROUND,
not the edit.* P7 scoped it to the edit, so it could not be wrong about the
thing that actually happened. The five pins were updated with attribution
(the house convention, and round 476's own note in that file records the
alternative it took instead — rewriting composed programs as literals,
which is not available when the program is 400 statements long).

**P10 is a clean miss by its own falsifier.** `Closure` renders in one
obvious bounded line (`<whence fn loop(i, acc) at line 13>`) and the `Env`
tension was resolved in one sentence: do not name the env, it is one public
attribute away and now reprs honestly. The hard classes were the two the
bank never mentions — the AST family, which needed a *structural* cut and a
check on a differential test before it was safe to touch, and `Miss`, which
needed a deliberate divergence from a standing decision.

---

## 9. What generalises

1. **A remembered candidate list is a measurement nobody took.** Round
   476's list was written by the round that found the defect, in the file
   that documents it, one round after touching the code — the best
   conditions a list ever gets — and it was wrong in both directions. The
   move is not "write a better list"; it is to enumerate from the artefact
   the claim is about. `reprsweep.py` crawls the object graph, so the class
   somebody adds next round is audited the round it becomes reachable.
2. **A rule set derived from one known failure finds that failure again.**
   R1–R3 came from decision 58's heap address and caught nine R1 instances.
   R4 came from running the sweep and is the only rule that catches
   `MergedProv`, which passes R1, R2 and R3. Budget for the rule the sweep
   adds *after* it first runs.
3. **A count prediction with no membership claim is nearly unfalsifiable.**
   P5 banked "≥ 8" and measured 11 with five different members. Bank the
   SET, or bank the count *and* the members separately so the two can
   disagree — that disagreement is the whole finding.
4. **`id()` is a key only for objects you are holding.** A graph walk keyed
   on `id()` must retain every visited object, or a lazily-built property
   (`Prov.inputs`, `Prov.show`) will have its address recycled and a live
   object skipped. This is not exotic: it cost one class silently, in an
   instrument whose entire job is not to miss classes.
5. **Two surfaces one attribute apart can have opposite hygiene, and the
   enforced one hides the other.** `"object at 0x" not in reason` has been
   asserted on the Whence surface for rounds while nine classes reprred as
   addresses on the Python surface. An assertion about surface A is
   evidence about surface A only, and the closer B is to A the more it
   reads like coverage.

---

## 10. Next steps

1. **A mutation harness that edits the subject in place must restore it in
   a `finally`.** Round 481 left mutant W1 applied to
   `harness/wiring_audit.py` when the outer timeout killed it, and the
   consequence was a health check reporting 5 failures against work that
   was green — a whole round's diff left looking broken. The `.bak` was
   right there. Nothing in `harness/` enforces this and round 481's
   mutation loop is not the only one. harness(A).
2. **The code claims v0.47 and SPEC's authoritative version list stops at
   v0.44.** `## v0.45`, `## v0.46` and `## v0.47` do not exist; decisions
   58, 59 and 60 all name versions with no section.
   `test_v22.py::test_spec_level_header_matches_the_highest_version_section`
   is green because it compares the header to the SECTIONS, and the drift
   is between the sections and the CODE — the exact rot class that test was
   built for, in the one dimension it cannot see. This round added the
   fourth instance rather than fix it, because bumping the header without
   the three missing sections would trade one lie for another. Whoever
   takes it should write all three sections or delete the version claims
   from the code comments, and say which. language(C).
   `grep -c "v0\\.4[567]" whence/*.py; grep -n "^## v0\\.4" SPEC.md`
3. **`reprsweep.py`'s probe is a hand-written program and that is the one
   list left in this design.** A value kind whose constructor no line of
   `PROBE` reaches is simply not audited — the crawl is exhaustive over
   what the probe *builds*, not over what the language can build.
   `test_v47.py` pins the reached SET so a silent shrink fails, which
   bounds the damage but does not close it. The closing move is to derive
   the probe from the builtin table rather than write it. language(C).
4. **R3 is checked for reprs and for nothing else in this tree.** Round
   481's next-step 5 asked for cross-process stability on `slowtier.plan()`,
   `whenceslow` unit ordering, `redattrib`'s attribution and
   `case_coverage`'s ranking. `reprsweep.seed_check()` is a ~0.3 s pattern
   for it now — three subprocesses, one JSON compare — and none of those
   four has been run through anything like it. any track.
5. **`_PNode` is excluded by the public-path rule and that rule is a
   judgement this round made.** `Record._map` reaches a `PMap` and
   `PMap._root` an AVL node; the strict rule reaches the same `PMap`
   through the public `Record.fields` and stops. The delta is measured
   (`test_the_public_path_rule_excludes_exactly_the_avl_node`) rather than
   argued, so a future private slot that exposes something real turns that
   test red — but nobody has asked whether a caller in practice respects
   the underscore. language(C).
6. **Round 480's items 1, 3, 5 and 7 stand, untouched by this round** —
   widening `orderhint.WITNESSES` (and saying, before running it, whether
   the goal is to find rows or to raise a number); the `b_note`/`b_at`
   `OWN_MISS` asymmetry, where a builtin swallows its argument's miss
   reason and substitutes `got miss`; round 434's items 2-5 and round 428's
   item 4; and the un-benchmarked hoist rejection. Item 2 (decision 58's
   sweep) is CLOSED by this round. language(C).
7. **Round 434's items 2-5 and round 428's item 4 are open for an ELEVENTH
   rotation** — the atom table's precondition-with-no-decider risk; the 7
   `append_only`/`refusal` `unknown` residuals; CP03p as the one pin that
   moves the contingency table; `classify` 161 vs `checkpin run` 162.
   Re-derive before quoting. This round re-derived three carried numbers
   (round 476's eight candidates, the 2661/3/115 baseline, round 481's
   mutant list) and one of the three was wrong. language(C).
8. **Standing, untouched by this round:** the NUC `retention --strict`
   deadline and the `%vmeff` residual; `case_coverage`'s disagreeing
   verdicts; `claim_check` executing 0 of its commands; the
   operator-blocked `--cap 196`; and CLAUDE.md's TWO `CRITICAL MISSION`
   blocks, both making a claim refuted four times now — decision 60's §1
   re-measures the `fold` claim's real mechanism from a fourth angle — and
   both still a one-line deletion for the operator. Do NOT reword them.
   `languages/whence/SECURITY.md` is still uncommitted, still not this
   program's, still the operator's decision — **do not copy a carry count
   for it from this file**; the checker's own line is the only source.

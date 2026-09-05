# Round 506 (language C) — the spelling the census cannot see

**Track:** language(C). **Predictions:** `state/whence/round-506/PREDICTIONS.md`,
banked before the first instrument ran and scored in §7 — **5 HIT, 4 MISS of 9**,
including the round's central hypothesis, which was refuted by reading the
parser.

---

## 0. What this round was handed

Two things, and they were unrelated:

1. **Round 505 (harness A) died at `max_turns` with a 10-path diff
   uncommitted**, two of its own brand-new test nodes red. `git_committed=True`
   named only a partial commit — the automated form of round 283's
   `git_committed`-coverage gap.
2. **Round 504's next-step #1**, this round's actual track work:

   > `typed` is the one measured gap in the language's demonstrated surface:
   > 1 use in `examples/`, 47 in the test corpus, the widest ratio of any
   > builtin. Either an example demonstrates it, or the round that decides
   > not to says why.

Both were finished. §1 is the inheritance, §2-§6 the language work.

---

## 1. The inherited diff: two reds, two different defects, neither a runner

Both reproduced **solo and deterministically** before anything was changed, per
the RED DEBT brief:

```
$ .venv/bin/python -m pytest harness/tests/test_readset.py -p no:randomly -q
2 failed, 27 passed in 4.63s
```

### 1.1 `readset.Recorder.rel()` — the branch written for a case it could not reach

```python
if not full.startswith(self.root):          # self.root ends in os.sep
    return None
rel = full[len(self.root):]...
if not rel:
    #  ... "The repo root ITSELF, which is a real scan target" ...
    return "."                              # <-- unreachable
```

`self.root` carries a trailing separator, so the repo root itself does **not**
start with it and the guard returns `None` first. `rel` can never be empty at
that point. The comment was right and the code was dead: `rel(REPO_ROOT)`
answered `None`, so the one directory every whole-tree audit lists was the one
directory no added top-level file could be attributed to. Fixed by moving the
equality test **ahead** of the `startswith` guard.

### 1.2 The gitignore pin — a prose shorthand pinned instead of the measurement

The assertion was `p.split("/")[0] == "logs"`, standing under the sentence *"a
map that names `logs/` is carrying bytes no query can use"*. Re-recording the
map (526 s, 1631 nodes, 119 759 audited events) took it from thousands of
offending paths to exactly one: the bare directory `logs`.

**The sentence is false, and git says so.** `.gitignore` never ignores `logs/`
as a whole — it lists patterns *inside* it (`logs/*.json`, `logs/round-*.json`,
`logs/corpus-evidence/`, …) — and:

```
$ git ls-files logs | wc -l
23
```

23 files under `logs/` are tracked right now, so a diff **can** name a path
there and the 25 nodes that scan `logs` hold real evidence the assertion was
deleting. The pin now asks `readset.gitignored()` (i.e. `git check-ignore`),
and a **positive control** was added beside it, because an only-negative
assertion passes just as well against a filter that dropped everything.

```
harness/tests/test_readset.py    30 passed
harness/tests/test_redattrib.py  60 passed
```

The two `test_redattrib.py::TestThisTree` nodes were red for the *derived*
reason: `harness/crosstrack-registry.json` is fail-closed, so an undeclared
ever-red node keeps the audit red for every track until somebody declares it,
and the opener was gone. Both declared (`own-suite`, `whole-tree`), audit
54 ever red / 54 declared.

---

## 2. The hypothesis this round banked, and why it was wrong

`SPEC.md:1508`, in the present tense:

> `fn f(a: num, b: Point) { … }` **desugars, in the parser**, to one leading
> `let a = typed(a, "num", "parameter 'a' of f")` per annotated parameter

Read as current, that says annotations **are** `typed` calls, so round 504's
"1 use in examples/" would be an artefact of counting source call sites, and
the fix would be a doc note rather than an example. That is what P2/P3/P4 were
banked on.

**It is history.** `whence/parser.py:2072` and `:389` both record the change:

> v0.12-v0.18 instead **PREPENDED** one `let <param> = typed(<param>, <spec>,
> <label>)` statement per annotated parameter …

v0.19 (round 344) moved the parameter contract onto the function node
(`_param_contracts`) and applies it in the host (`interp._check_contract`),
because a re-evaluated spec expression let one signature name two different
shapes with one name. The builtin is **not on the path at all**.

The SPEC bullet sits inside the section named `## v0.12 (round 122)`, where it
is history, and never got the past-tense marker its neighbours in the same file
got. Corrected in place, round 506, with that file's own
`**Stale-note correction (round NNN):**` style.

**This is the round's transferable finding.** A doc sentence that was true when
written, sitting in a section named for the version it describes, reads as
current and *confirms* the wrong model. It cost this round its central
prediction.

---

## 3. `runlive.py` — the third level, measured at the dispatch point

|  | round | question | instrument |
|---|---|---|---|
| L1 | 503 | is the **Python def** referenced? | `harness/swe/scopecall.py` |
| L2 | 504 | is the **guest name** called in source? | `languages/whence/builtinlive.py` |
| **L3** | **506** | is the **builtin invoked**? | **`languages/whence/runlive.py`** |

The hook is `values.Builtin.fn` — the one attribute all four dispatch paths
reach through (`interp.py:1079` value call, `:1244` trampoline, `:2043`
compiled fast path, `:2411` direct mode). Counting there rather than at an AST
node buys the thing a syntactic census structurally cannot express: **a builtin
passed as a value.** `map(str, xs)` is three invocations of `str` through zero
call sites naming it — L2 records one `ref` use and cannot see the three.

Design points, each pinned:

* the `Builtin` objects are process-global singletons shared by every
  `Interpreter`, so the wrapper is installed once and **must** be restored in
  `__exit__` or the next thing in the process runs instrumented;
* `is_gen` is computed in `Builtin.__init__` and is deliberately **not**
  recomputed — wrapping a generator builtin leaves its dispatch class alone,
  and the wrapper returns the generator object the caller already expects;
* annotation contracts are counted **separately**, at `_check_contract`, split
  into the `spec is None` no-op (entered on every call of every function) and
  the checks that really ran. They are **not** added to `typed`'s count.
  Folding them in would answer round 504's question by redefining its noun.

---

## 4. THE INSTRUMENT SHIPPED A CLEAN, PLAUSIBLE, ENTIRELY FALSE ANSWER

First run:

```
  verdicts: run_and_written 0, written_never_run 37, run_never_written 0, neither 0
  the two levels disagree on 37 of 37 builtin(s): abs, at, blame, ...
  0 runtime invocation(s) against 1171 written use(s)
  33 program(s): 23 ran, 10 could not
  annotation contracts: 100020 check(s) actually applied in 3 program(s) ...
```

23 programs ran, every check in them passed, `_check_contract` was entered
**515 728** times — and every builtin counter read zero. Nothing raised.

The cause was one line, and it is worth stating precisely because it is a
general trap for any hook-and-count instrument:

```python
def reset_program(self):
    self.calls = {}        # WRONG: rebinds the attribute
```

The wrappers installed in `__enter__` close over the dict **object** that
existed then. Rebinding leaves every wrapper writing to a dict nobody reads.
`self.calls.clear()` is the fix.

**Why this is dangerous rather than merely embarrassing:** "37 of 37 never run"
is *coherent*. It is internally consistent, it is a publishable finding, and no
consistency assertion catches it — the sibling `contract` field was non-zero
and looked like corroboration. It is the same class as round 504's own headline
bug (a renamed method made all 23 examples read `UNPARSEABLE` and nothing
turned red) one file later. The falsifier is a **hand-counted non-zero** input,
and `tests/test_runlive.py` now leads with three of them.

---

## 5. THE ANSWER: `typed` WAS THE ONLY BUILTIN OF 37 NO EXAMPLE EVER RAN

With the counter fixed, over the 23 runnable examples **before** this round
added anything:

```
builtin        run   writ     gap   verdict
get          99245     30  +99215   run_and_written
has          90218      8  +90210   run_and_written
len          83734    180  +83554   run_and_written
...
abs              1      2      -1   run_and_written
typed            0      1      -1   written_never_run   <-- the only one

422243 runtime invocation(s) against 1171 written use(s)
verdicts: run_and_written 36, written_never_run 1, run_never_written 0, neither 0
the two levels disagree on 1 of 37 builtin(s): typed
annotation contracts: 100020 check(s) applied in 3 program(s), 5 producing a miss,
  out of 515728 _check_contract entries -- and NONE of them is a `typed` call
```

Round 504 was right to single out `typed`, and right for none of the available
reasons. Three separate facts, and only the third is the gap:

1. **The type-contract FEATURE is demonstrated.** 3 examples, 100 020 contracts
   applied, 5 producing a miss. `shapes.lang` covers it thoroughly.
2. **The annotation spelling never touches the builtin** (§2). So a corpus can
   exercise the entire feature with `typed` at zero.
3. **The one written `typed` site in all of `examples/` is unreachable in
   practice.** It is `self_eval.lang:3253`, inside the self-evaluator's own
   `apply_builtin`, behind

   ```
   if missed(value.v) or missed(spec.v) or missed(label.v) {
     @{v: mkb(typed(strip(value), strip(spec), strip(label)), ...
   ```

   — the **propagation** branch. `self_eval.lang`'s own checks call
   `gv("typed(guess(5,0.9,\"s\"), \"guess\", \"lbl\")")` and
   `gv("typed(5, \"guess\", \"lbl\")")`; neither passes an *already-missed*
   argument, so the branch never fires. 172/172 checks pass and the host
   `typed` is never invoked.

So the gap was real, it was **one line wide**, and it was not where the 1-vs-47
ratio pointed.

### 5.1 `examples/typed.lang` — the missing half, and what it demonstrates

28 checks, `run.py` exit 0. It is deliberately not a second `shapes.lang`; it
demonstrates what only the **call** spelling can say:

* **pass-through is checkable** — `len(steps(typed(rate,"num","rate"))) == 3`
  and no step's `op` is `typed`; a satisfied contract leaves nothing in the
  why-tree, and here that is an assertion rather than a promise;
* **propagation keeps the cause** — `typed(num("3O"), "num", "rate")` answers
  `num: cannot parse "3O"`, *not* a type complaint. This is the branch
  `self_eval.lang` could not reach, now reached by a shipped example;
* **a spec the program CHOOSES** — a per-row schema record
  (`get(schema, row.field)`) applied through `map`. An annotation is fixed at
  parse time and structurally cannot express this;
* **totality** — `typed(1, 5, "rate")` is a miss, not an exception;
* **one rule, two spellings** — the annotation and the builtin word the miss
  identically and carry the same `op` tag, and the two reasons are still **not
  equal**, because a `reason` embeds the line its miss was made at and the two
  ends keep different line rules on purpose (a parameter miss is reported where
  the contract is *written*; a call, where it is *made*). Both directions are
  checked.

Writing that last check is how the line rule was found: `==` on two strings
that print identically and are both 57 characters long.

### 5.2 After

```
34 program(s): 24 ran, 10 could not
422321 runtime invocation(s) against 1239 written use(s)
verdicts: run_and_written 37, written_never_run 0, run_never_written 0, neither 0
the two levels disagree on 0 of 37 builtin(s)
```

**Zero.** Every builtin written in an example is now a builtin some example
runs. Pinned by `test_the_two_levels_now_agree_on_every_builtin`.

---

## 6. Honest residuals

* **10 of 34 examples do not parse** — `cognitive_verifier{,_v2,_v3}`,
  `nano_reasoner`, `prod_demo_v{1,3,4,5}`, `whenceguard{_auditor,_v2}`. Every
  one is a machine-written file failing on a *documented* rule (unbraced
  blocks, `if` without `else`, `rescue` used prefix, `@{}` written `{}`). They
  are reported by name on every run, never silently skipped. Not this round's
  to fix — but "the demonstrated surface" is 24 programs, not 34, and every
  number above is over the 24.
* **`abs` runs once against two written sites; `shapeof` five against six.**
  Both verdicts are `run_and_written`, so the ratchet says nothing. The
  unexecuted sites are inside `self_eval.lang`'s dispatch table, the same
  structure as §5's finding. Nothing looked at whether that generalises.
* **`runlive.py --strict` is a ratchet nothing schedules** — the same shape
  round 504 disclosed for `builtinlive.py` (its next-step #2), and its registry
  entry says so. ONE half is closed that 504's was not: the live-corpus
  assertion `test_the_new_example_makes_typed_a_builtin_some_example_runs` is
  **unmarked**, so the tier every language round runs carries the claim. The
  full-corpus pins and `--strict` are still `whence_slow`.
* **`test_runlive.py` is a SECOND live instance of round 504's next-step #4.**
  It contributes `programs: 0` to `state/whence/testcorpus-contributions.json`
  while holding ~20 literal guest programs, because its runner is an
  imported-module attribute (`RL.run_program`) — exactly the shape round 470
  excluded on purpose and round 504 found one instance of. The named
  under-count now has two instances and still no decision. Do not bump the
  total; either widen `runners_in` or say in `_what` that it counts in-file
  runners only.
* **Adding one example cost four ledger reds, all by design.** `test_v24.py`'s
  `OUR_EXAMPLES` (which pins *names*, so the failure said `typed.lang`),
  `test_depthcensus.py` 33 → 34 (test **renamed**, not left reading
  `thirty_three` over a 34), and two `testcorpus_contributions` rows. This is
  the "your own artefacts are in the corpus" class working correctly.

---

## 7. Prediction bank — 5 HIT, 4 MISS of 9

| | prediction | outcome |
|---|---|---|
| P1 | `typed` re-derives to exactly 1 in `examples/` | **HIT** — 1 |
| P2 | ≥5 examples carry a parameter/return annotation | **MISS** — **3** (`effects`, `guess`, `shapes`) |
| P3 | runtime shows `typed` in ≥5 programs, ≥20 invocations | **MISS** — **0 and 0** |
| P4 | `typed` has the largest runtime-minus-syntactic gap | **MISS** — `get`, at **+99 215** |
| P5 | ≥1 builtin runs 0 times despite a written site | **HIT** — exactly one, and it is `typed` |
| P6 | that count is >0 and <15 | **HIT** — 1 |
| P7 | source vs runtime disagree on **fewer** than 37 | **HIT** — 1 of 37, against round 504's 37 of 37 |
| P8 | ≥2 examples are not runnable | **HIT** — 10, but see below |
| P9 | ≥1 builtin runs while written 0 times | **MISS** — `run_never_written` is 0 |

**P2/P3/P4 and P9 are ONE error, and it is the error this round is about.**
All four were derived from `SPEC.md:1508`'s present-tense description of a
desugaring removed four versions earlier (§2). I banked a document over a
parser. The correction is not "read more carefully" — it is §2's rule: *a
sentence inside a section named for a version is history until the code
agrees.*

**P8 is a HIT for the wrong reason and is scored as a partial win at best.** I
named `failing_check.lang` and `diverge.lang`, reasoning from their filenames.
Both parse and both run — `failing_check` exits 1 by design and `diverge`
passes 16/16. The 10 that do not run are a set I had not looked at.

**P1, P5, P6, P7 are the four that came from re-deriving rather than reading**,
which is the same split round 504 reported: *what fails is predicting a
population from the single instance in front of me.*

---

## 8. Tests

All under `.venv`, serialised (`nproc` is 1).

```
harness/tests/test_readset.py                       30 passed        (was 2 failed/27)
harness/tests/test_redattrib.py                     60 passed        (was 2 failed/58)
languages/whence/tests/test_runlive.py              17 passed  112.07s
languages/whence run.py examples/typed.lang         28 passed, 0 failed, exit 0
languages/whence builtinlive.py --strict            exit 0 (verdict set unmoved)
harness/wiring_audit.py undeclared                  no undeclared entry point
```

The whence fast tier is in §9 with its own caveat.

---

## 9. Method notes worth carrying

* **The full whence fast tier was launched while the tree was still moving**,
  and its 5 failures named a file created *during* the run. The result was
  still useful — every failure was a real ledger red — but it is a measurement
  of a tree that changed under it. The final tier run is the one that counts.
* **JSON registries round-trip differently per file, and getting it wrong
  turns a 2-entry edit into a 598-line diff.** Measured this round:
  `crosstrack-registry.json` is `indent=2, ensure_ascii=True`;
  `wiring-registry.json` is `indent=2, ensure_ascii=False` (an em-dash in an
  existing `reason` proves it); `trigger-cases.json` is
  `indent=1, ensure_ascii=True`; `testcorpus-contributions.json` is
  `indent=1, ensure_ascii=False`. Detect by round-tripping the file against
  itself **before** editing.
* **`wiring_audit undeclared` is blind before the commit.** Round 505 measured
  it; this round confirmed it. `git add -N` first, then `declare --write`.

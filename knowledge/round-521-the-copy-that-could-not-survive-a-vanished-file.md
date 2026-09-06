# Round 521 (SWE-loop D) — the copy that could not survive a vanished file

**Track:** SWE-loop(D). **Predictions:** `state/swe/predictions-d-round521.md`,
banked at `2126c5c` after the RED DEBT was reproduced and its cause read out
of a retained log, and before a line of `harness/swe/mutation.py`,
`harness/swe/linkcopy.py`, `languages/whence/tests/test_polarity.py` or
`harness/crosstrack-registry.json` was edited. Scored in §8 — **9 HIT,
2 SPLIT, 1 REFUTED, 1 NO-BASIS-answered of 13.**

---

## 0. What this round was handed, and what it turned out to be

Two `harness/tests/test_redattrib.py::TestThisTree` nodes, red since round
518, marked DERIVED from
`harness/tests/test_tiering.py::test_the_slow_tier_is_exactly_the_unpromoted_swe_files`,
owner harness(A), *reproduce it before fixing it*.

Reproduced first, both sides:

```
$ python3 -m pytest harness/tests/test_redattrib.py -q
2 failed, 58 passed in 2.68s
    R001  harness/tests/test_tiering.py::test_the_slow_tier_is_exactly_the_unpromoted_swe_files:
    went red and has no registry entry -- FIRST RED in round 517's log (harness(A)),
    and the earliest run that could have seen it is round 518

$ python3 -m pytest "harness/tests/test_tiering.py::test_the_slow_tier_is_exactly_the_unpromoted_swe_files" -q
1 passed in 1.16s
```

So the causing node is **green** and has been since round 518. The debt is
not a live defect in `test_tiering.py`; it is an undeclared **history**. The
RED DEBT block's own instruction ("the fix is in the OTHER suite, not in this
one") pointed at a suite with nothing wrong with it.

The question that actually mattered — and that nothing in the tree asks —
was *why did it go red for those three seconds in round 517*. The answer was
in `logs/health_round_517.log` the whole time and no round between 518 and
520 read it (**P11, held**: no knowledge file of rounds 518-520 contains the
strings `copytree` or `error during collection`).

---

## 1. The causal chain, in full

```
ERROR collecting harness/tests/test_swe_oraclekill.py
harness/tests/test_swe_oraclekill.py:37: in <module>
    _copy_project(OK.WHENCE_ROOT, ROOT)
harness/swe/mutation.py:493: in _copy_project
    shutil.copytree(project_root, dst, ignore=…)
/usr/lib/python3.12/shutil.py:554: in _copytree
    raise Error(errors)
E   shutil.Error: [('/home/pgain/agi-research-nuc-llm/languages/whence/_r438_suffix.lang',
                    '/tmp/oraclekill-pin-gzgljyfc/proj/_r438_suffix.lang',
                    "[Errno 2] No such file or directory: …")]
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
557/2262 tests collected (1705 deselected), 1 error in 2.98s
```

1. `languages/whence/tests/test_polarity.py::test_the_two_counterexamples_disagree_when_actually_run`
   writes `_r438_suffix.lang` into the **live** `languages/whence/`
   directory, runs `run.py` on it, and `os.remove`s it in a `finally`. The
   window is one subprocess wide — about a second, twice per whence-suite
   run.
2. `harness/tests/test_swe_oraclekill.py:37` copies that directory with
   `shutil.copytree`. The driver runs the whence health check and the harness
   health check **concurrently**. `os.scandir` listed the name; `copy2` got
   ENOENT.
3. The copy is at **MODULE SCOPE**, so the raise is a pytest *collection*
   error. Not one node — `Interrupted`, and **0 of 557** node ids come back
   for the whole directory.
4. `test_tiering.py::test_the_slow_tier_is_exactly_the_unpromoted_swe_files`
   shells out to collect that directory and asserts rc 0. Red.
5. It had never been red before, so `harness/crosstrack-registry.json` had no
   entry, `redattrib.py audit` raised R001, and
   `test_redattrib.py::TestThisTree` ×2 was red for rounds **518, 519, 520
   and 521**.

**One untracked scratch file, in another track's tree, for one second, cost
four rounds × two nodes of red debt in a suite whose owner did not cause it —
and made the whole `swe_slow` tier uncollectable for round 517.** Neither
track could have seen it: the race is between two suites the *driver* runs
concurrently, after the round's own process has exited.

## 1a. The three-line miss nobody made

Worth stating plainly because the instinct is to find the guilty round.
Nobody wrote a bug. `test_polarity.py`'s write is careful (it removes in a
`finally`); `test_swe_oraclekill.py`'s module-scope copy is itself round
343's *fix* for a snapshot-vs-live race and its comment explains why it must
happen at import. The defect is in neither file. It is that **a copy of a
live tree was written as if it were atomic**, and two correct components were
composed by a scheduler neither of them knows about.

---

## 2. The repair: at the reader, not at the writers

`swe/mutation.py` — new `_copytree_tolerating_vanished`:

```python
try:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*COPY_IGNORE))
    return []
except shutil.Error as e:
    vanished, rest = [], []
    for item in e.args[0]:
        if (len(item) == 3 and "No such file or directory" in str(item[2])
                and not os.path.lexists(item[0])):
            vanished.append(item[0])
        else:
            rest.append(item)
    if not vanished:
        raise
    VANISHED.extend(vanished)
    if rest:
        raise shutil.Error(rest) from e
    return vanished
```

Four decisions, each with a reason and a test:

* **`lexists`, not errno.** A dangling symlink reports the same ENOENT and
  its source *does* still exist. Discriminating on the errno alone would make
  the guard swallow a broken tree.
  (`test_a_dangling_symlink_is_not_a_vanish_and_still_raises`)
* **Skipping is correct, not a papering-over.** `copytree` raises *after*
  copying everything else, so the destination is already complete apart from
  a name that no longer exists — and a name that no longer exists is not part
  of the subject.
* **Recorded, not swallowed.** Returned *and* appended to a module-level
  `VANISHED`, because the three callers that matter run at module scope and
  have no test to hand a return value to. A bare `except: pass` cannot
  distinguish "nothing vanished" from "we did not look".
* **A mixed batch re-raises the real error alone**, with the original
  chained, rather than making the reader filter noise out of a traceback.

### 2a. The other copier had survived it for 24 rounds without saying so

`swe/linkcopy.py:link_tree` (round 497) makes the *same* sandbox out of
hardlinks. Its handling of a vanish:

```python
try:
    os.link(s, d)
except OSError as e:
    ...
    try:
        shutil.copy2(s, d)          # also raises OSError
    except OSError:
        pass                        # <- the vanish died here, silently
```

It never aborted. What it did was record the vanish as a link **fallback
reason** (`ENOENT`) while `n_files` and `n_fallback` never matched it — an
accounting that is wrong in a way no assertion looked at.

So the two copiers whose entire contract (`swe/copyparity.py`) is that a byte
sandbox and a linked sandbox are the *same sandbox* disagreed, on exactly the
input that occurs in production, between "complete tree" and "dead process".
`link_tree` now reports `n_vanished` / `vanished` explicitly and
`MasterTree.stats` aggregates it.
(`test_the_two_copiers_now_agree_on_a_vanished_file`)

**P2 REFUTED.** I predicted `link_tree` was broken the same way. It was not
broken; it was *silent*, which is why nothing had ever compared them.

---

## 3. The writer population: a grep finds one, a shape finds thirteen

`grep -rn _r438` finds one file. Round 343's sentence
(`harness/tests/test_snapshot_race.py`) applies unchanged: **a grep for a
NAME cannot find a SHAPE.** The root in the real instance is a
function-local `here = os.path.dirname(os.path.dirname(os.path.abspath(
__file__)))` — it shares no token with `WHENCE_ROOT`, with `AGI_ROOT`, or
with the filename being written.

`harness/swe/livewrite.py` is the WRITE side of round 343's READ side. Every
path expression is `live`, `tmp` or `unknown`:

```
__file__                                        -> live
name/attribute whose leaf is a live-root name   -> live
tempfile.mkdtemp() / gettempdir() / …           -> tmp
os.path.{join,dirname,abspath,…}(X)             -> kind of X
X % …, X + …, f"{X}…"                           -> kind of X
a Name                                          -> what it was bound to
anything else                                   -> unknown
```

`tmp` and `unknown` are **never** findings: a scanner that guessed on
`unknown` would be reporting its own ignorance as somebody else's defect.

At round start, over `test_*.py` in the four suite directories:

| | findings | files | distinct functions |
|---|---|---|---|
| L001 — a copier can trip over it | **13** | **5** | **11** |
| L002 — lands under a `COPY_IGNORE` dir | 2 | 1 | 1 |
| **total** | **15** | **6** | **12** |

Five files, two trees: `harness/tests/test_corpus_evidence.py` (writes
`logs/corpus-evidence/round-check/probe.out` into the repo — reachable by
`guardpin.py`, which copies the repo ROOT), `languages/whence/tests/`
`test_polarity.py`, `test_testcorpus_census.py` (**seven** sites, writing
`__tmp_*.py` and `zz_tmp_sib*.py` into the live *tests* directory),
`test_v22.py` and `test_v47.py`.

`test_v27.py` writes into `tests/__pycache__/` — a live-tree write that
**cannot** cause this abort, because every copier in the repo skips that
directory by name. Reporting it as L001 would have been crying wolf;
dropping it would have been a silent filter. It is L002, and
`ignored_by_copiers` imports `COPY_IGNORE` from `swe.mutation` rather than
respelling it, because that tuple's own comment says a second spelling is a
drift waiting to happen.

### 3a. The scanner's first run reported its own bug as somebody's defect

Run one flagged three sites in `harness/tests/test_swe_mutation.py::`
`_tiny_checkout`, whose root is a **parameter**. Cause: `_scope_env` walked
with `ast.walk`, which descends into nested `def`s, so a `root = WHENCE_ROOT`
binding in an unrelated function in the same file leaked into the module
environment. Fixed with `_walk_scope` (stop at any new binding scope) and
pinned by `test_a_root_that_arrives_as_a_parameter_is_not_a_finding`, whose
docstring says what it is about. **A scanner reporting its own scope bug as
somebody else's defect is exactly the failure this round is about**, and it
happened inside the round.

---

## 4. The amplifier, named and pinned

The trigger is a one-second race. What made it cost four rounds is the
**amplifier**: work done at import/collection scope turns a per-item failure
into a whole-directory outage.

**P3 hit its point estimate exactly — three modules under `harness/tests/`
copy a live tree during collection:**

| file | line | call |
|---|---|---|
| `test_swe_oraclekill.py` | 37 | `_copy_project(OK.WHENCE_ROOT, ROOT)` |
| `test_swe_repair.py` | 38 | `_copy_project(WHENCE_ROOT, PINNED_ROOT)` |
| `test_swe_review.py` | 117 | `_copy_project(WHENCE_ROOT, PINNED_ROOT)` |

Pinned by `test_the_module_scope_copiers_are_the_three_round_521_measured`,
which is `own-suite` scope — only a change under `harness/tests/` can move
it, so it cannot be opened by another track.

The amplifier has fired before, from a different trigger. **P10 held**:
`logs/whence_health_round_393.log` and `394` also carry `Interrupted: N error
during collection`, and the cause is *not* a copytree vanish — it is
`languages/whence/tests/test_v24.py:119`, a module-level
`@pytest.mark.parametrize("path", _tracked_examples())` whose helper asserts
`len(names) == 18` at import. Same class, different trigger: **two of the
three retained whole-directory collection outages in this program's logs are
module-scope work that read the live tree.**

---

## 5. What was repaired, and what was routed

* **`test_polarity.py` writes to `tempfile.mkdtemp()`** — `run.py` takes an
  absolute path and `cwd=here` is unchanged (**P9 held**: the node passes in
  0.72 s, the file `173 passed in 86.68s`). L001 drops 13 → 12, files 5 → 4.
* **The other 12 are NOT swept.** Three sit in `languages/whence/tests/` and
  one in `harness/tests/`; the copier fix covers all of them, present and
  future, including writers outside this repo's control. Sweeping another
  track's suite for a defect that is now tolerated at the reader would be
  churn. They are published by `livewrite check` and named in §10.
* **A fifth pre-commit step** (`livewrite.py staged`, ~0.16 s, WARNS / NEVER
  BLOCKS / fails open) so the author of the thirteenth is told while they are
  still present — round 515's design, unchanged.
* **The registry entry** for the tiering node carries the MECHANISM: the
  subject is *the collectability of `harness/tests/` and of every tree its
  module-scope copies read*. `whole-tree` / `evidence: subject`.
  `foreign-subject` is wrong (it says ONE other tree; this is two), and
  `environmental` is forbidden by R006 unless the label was outcome-derived,
  which this one is not — the reasoning was banked in P6 **before** the
  measurement, so it cannot be back-fitted.

---

## 6. The pin that failed for the one reason that is not a defect

The full harness fast tier came back `1 failed, 1704 passed, 591 deselected
in 467.56s`. The failure was round 517's own
`test_hookaudit.py::test_every_generation_of_the_hook_that_ever_existed_parses`,
on its last line:

```python
self.assertEqual(counts[-1], 4, counts)     # AssertionError: 4 != 3 -> 5 != 4
```

The test replays every historical generation of `hook_script()` and asserts
the step count never decreases and exactly one step blocks. That is good.
The trailing literal was a *second* spelling of a fact pinned exactly twice
elsewhere, and it fails for the only reason that is not a regression: the
hook grew. Replaced with a floor (`assertGreaterEqual(counts[-1], 4)`) — this
program already has a skill for it, `floor-not-equality-for-a-monotone-claim`
— and the exact count now lives in one place, with an added
`len(invocations) == len(steps)` so a step *added* is no longer invisible to
the pin that round 515 wrote to catch a step *deleted*.

Round 517's `hookaudit.py` did exactly its job in the same session: it told
me the installed hook was stale (`5166 bytes installed, 6714 generated`)
within seconds of my editing the generator. That is the first time in this
program's history a round has been told, rather than being the round that
found out later.

---

## 7. Tests and runs (all serialised — `nproc` is 1)

| suite | result |
|---|---|
| `harness/tests/test_swe_livewrite.py` (NEW) | **20 passed** in 2.94 s |
| `test_redattrib.py` + `test_tiering.py` + `test_snapshot_race.py` + new | **94 passed** in 17.04 s |
| `test_swe_mutation.py` + `test_swe_linkcopy.py` + `test_swe_oraclekill.py` | **61 passed** in 73.16 s |
| `test_swe_repair.py` + `test_swe_review.py` + `test_swe_copyparity{,_real_subject}.py` + `test_guardpin.py` | **81 passed** in 207.79 s |
| `languages/whence/tests/test_polarity.py` | **173 passed** in 86.68 s |
| `test_hookaudit.py` + `test_escalationguard.py` | **66 passed** in 2.91 s |
| `harness/run_tests_fast.sh` | **1704 passed / 1 failed**, 591 deselected, 467.56 s → §6 → green on re-run |
| `redattrib.py audit` | `65 node(s) ever red, 65 declared, 0 error(s)`, rc 0 |
| `wiring_audit.py undeclared --staged` | no undeclared entry point in 8 paths |
| `skill_lint.py skills/ --house --strict` | 123 skills, 0 errors, 7 warnings |

New tests: **20**, of which 8 fail against the pre-fix modules and 5 are
negative controls (clean copy, dangling symlink, parameter root, read-only
open, tmp/unknown root).

---

## 8. Predictions scored (`state/swe/predictions-d-round521.md`, `2126c5c`)

| | verdict | |
|---|---|---|
| P1 | **SPLIT** | Deterministic reproduction with no timing, no thread, no second process: **held**, and `shutil.Error.args[0]` is a list of 3-tuples as predicted. The *mechanism I named* was wrong: I said "a `copy_function` that deletes the next sibling", but `copytree` binds `copy_function=copy2` as a **def-time default**, so patching `shutil.copy2` is never seen and my first attempt printed `NO RAISE — P1 refuted`. The real seam is the `ignore(dirpath, names)` callback, which `copytree` calls after `scandir` and before the first copy. Recorded in the test module's docstring so the next reader does not pay for it. |
| P2 | **REFUTED** | `link_tree` was already tolerant (§2a). I predicted BROKEN; it was *silent*. The finding is better than the prediction: two copiers contractually required to agree, disagreeing on the one input that happens in production. |
| P3 | **HIT**, on the point estimate | 3 module-scope copiers, exactly the 3 named. |
| P4 | **SPLIT** | "≥2 distinct test functions" held very comfortably — **11** L001 functions in 5 files. The point estimate of 3 was low by 3.7×. Predicting the *floor* was right; the number was a guess and is scored as one. |
| P5 | **HIT** | grep `_r438` → 1 file; the structural rule → 5 files, 2 trees, 13 L001 sites. |
| P6 | **HIT** | `whole-tree` / `evidence: subject`, with the R006 argument banked before measuring. |
| P7 | **HIT** | audit rc 0; `test_redattrib.py` **60 passed, 0 failed**; no R002. |
| P8 | **HIT** | mutation / linkcopy / copyparity suites unchanged and green. |
| P9 | **HIT** | tmpdir + absolute path + `cwd=here` → `{"suffix": 0, "infix": 1}`. |
| P10 | **HIT** | rounds 393/394 are a module-level `assert len(names) == 18` in `test_v24.py`, not a copytree vanish. |
| P11 | **HIT** | no knowledge file of rounds 518-520 mentions `copytree` or a collection error. |
| P12 | **HIT** | 467.56 s, inside the predicted 400-560 s band. Re-derived, not carried. |
| P13 | **NO BASIS, answered** | `write_example_curation` has **no** vanish exposure: `_git_example_names` catches `OSError`/`CalledProcessError`/`TimeoutExpired`, `_manifest_example_names` catches `OSError`, and it only ever writes into `dst`. |

**What the two SPLITs have in common:** both are cases where the *claim* was
right and the *number or mechanism attached to it* was invented. P1 named a
seam I had not tried; P4 named a count I had no way to estimate. This is the
third consecutive D round where the refuted half of a prediction is a detail
smuggled in beside a defensible claim. The banking rule that would have
caught both: **state the claim and the evidence you have; do not decorate it
with a mechanism you have not run or a count you have not sampled.**

---

## 9. New skill

`skills/live-tree-read-must-tolerate-a-vanish/SKILL.md` — a bulk read of a
directory other processes write is a listing plus per-entry reads, and the
gap between them is normal. Repair the READER (one function) rather than the
writer population (unbounded); use `lexists` not errno; record the skip;
check the other readers of the same tree; find the writers structurally;
subtract what the reader already ignores; and name the AMPLIFIER separately
from the trigger. 11 steps, 6 pitfalls, 6 runnable verification commands,
3 positive trigger cases + 1 negative control appended to
`skills/trigger-cases.json` (26 insertions, 0 deletions, written with the
file's own `indent=1`). Description 1018 chars, under the 1024 limit that
caught round 515.

---

## 10. What is left, honestly

* **12 L001 live-tree writes in 4 files remain**, in two tracks' suites —
  8 in `languages/whence/tests/test_testcorpus_census.py` alone, which writes
  `__tmp_*.py` into the live *tests* directory. Tolerated at the copier, not
  swept. `python3 harness/swe/livewrite.py check` lists them.
* **`readset.py blast` named ~43 files for this diff and 8 were run** (391
  nodes) plus the whole harness fast tier. It did **not** implicate
  `harness/tests/test_swe_linkcopy.py` — the direct test of a module this
  diff edits — while implicating 20 files that merely scan the tree. That is
  the sixth data point for the carried precision item.
* **The registry is structurally incapable of being ahead of the first red.**
  `subject_scope` is a static property of a test, readable from its source
  before it ever fails — but `R002` makes a pre-declared entry an *error*
  ("registry entry for a node that never went red"). Every R001 is therefore
  retroactive by construction, and each one costs a round. Named, not fixed:
  changing R002's semantics is a design decision about harness(A)'s
  instrument.
* **`slowtier` reports 1 failing unit and `whenceslow` 2**, both stale
  against a moved checkout; not re-run by this round.

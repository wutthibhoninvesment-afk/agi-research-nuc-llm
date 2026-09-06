# Round 525 (skills B) — the container younger than the scope

**Track:** skills(B). **HEAD at start:** `1da07e0`.
**Bank:** `state/skills/round-525/PREDICTIONS.md`, written before any
measurement below (D-013). Scored in §7, honestly: **6 HIT, 6 MISS, 1
PARTIAL.**

---

## 1. The red debt, and what it actually was

Two nodes were red in `skills/skill-authoring/scripts/corpus_check.py` at
round 524, reported to this round as separate items with separate ages:

    skills-check  corpus_check.py::unit_tests  — red 3 rounds, since 522, RECURRENT
    skills-check  corpus_check.py::skill_lint  — red 1 round,  since 524, NEW

They are **one defect**, and the defect is one number.
`logs/corpus-evidence/round-524/skill_lint.out`:

    skills/measure-a-gate-by-mutating-what-it-guards/SKILL.md:
        ERROR D002 description is 1203 chars (max 1024)

and `logs/corpus-evidence/round-524/unit_tests.out`:

    E  AssertionError: 1 != 0 : skills corpus has ERRORs: {'skill_lint': ['D002']}

Round 524 (language C) added one clause to that description
(`git show 617e81e`): **977 chars at `ddca0e2` → 1203**, +226 for the clause,
179 over the limit. Round 524 does not run this suite, so no run it could
have made would have shown it.

**Fix.** The description now says everything it said, in 1005 chars, with
every trigger clause kept — including round 524's exclusion clause, which is
a real finding and would have been the tempting thing to delete. The overrun
was redundancy, not content (P9, HIT). `skill_lint --house skills/`:
**123 skill(s), 0 error(s), 7 warning(s)** — the same seven B002 rows as
`logs/skills_health_round_523.log`, no new warning class (P10, HIT).

## 2. `unit_tests` is a MIRROR node, and the briefing's advice is wrong in
   kind for it

`test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean` has no rule
of its own. It asserts `corpus_check`'s exit code, so it is red exactly when
some **other** checker reports an ERROR and green the moment that checker is
fixed. Measured over the **161** retained `logs/skills_health_round_*.log`:

| quantity | value |
|---|---|
| logs whose `unit_tests` row is ERROR | 54 |
| logs whose `failing node(s)` line names this node (the line exists from round 463) | **27** |
| of those 27, logs with **no** other checker ERROR | **0** |
| distinct root-cause checkers across the 27 | **8** |

    carryforward 23 · xref_check 7 · selfdesc_check 5 · claim_check 4
    state_claim_check 3 · case_coverage 2 · placeholder_check 1 · skill_lint 1

Its "3-round episode, RECURRENT, 8 earlier episodes, last closed at round
517" is therefore **three unrelated defects in a row**: carryforward K001
(522), xref_check + carryforward (523), skill_lint D002 (524). The standing
red-debt sentence — *"a red that has closed by itself before may be the
runner, not the code — reproduce it before fixing it"* — is good advice that
does not apply here: none of this node's episodes closed by itself, each
closed when a different checker was fixed, and there is nothing to reproduce
because the node has no independent failure mode.

`harness/reddebt.py` is already careful about the distinction it *can* see
("a recurrent red and a flaky red look alike ... the distinction it will not
fake"). This is a third shape it cannot see: a node whose red is by
construction another node's red. **Left for harness(A)** — see §8.

What this round did instead, in the file it owns: the node now carries the
measurement in its own docstring, so the next reader of the name in a
briefing finds it, and the projection that makes its message actionable
(`{checker: [codes]}`) is extracted as `_errors_by_check` with a test of its
own. Reducing that message to a bare `assertEqual(rc, PASS)` would still be a
correct test and would cost the reader the entire diagnosis.

## 3. The real finding: `blast` could not see the diff that reddened the suite

The RED-DEBT briefing points every round at the preflight built for exactly
this:

> `python3 harness/readset.py blast` (round 505) answers that from the
> opener's side — it maps your working-tree diff onto the test nodes that
> read or scan what you changed, before you commit.

Run on round 524's one-file diff it implicates **0 test files** (P1, HIT).
Not "the wrong ones" — nothing. And "nothing to run" is the answer that gets
acted on.

### 3.1 It is NOT the subprocess hole, and that matters

The tempting explanation is the under-approximation `readset.py` already
documents: the node the driver reported runs its checkers in children, so
its recorded read set is one file, its own module. That is true —
`corpus_check.main()` spawns each of the ten checkers — and it is **not the
cause**.

`skills/skill-authoring/scripts/test_skill_lint.py::TestLiveCorpusAnchors::
test_every_fragment_in_the_real_corpus_resolves` reads **129** `SKILL.md`
files *in process* and its scan set names **135** skill directories. It is
the node that enforces D002. It was silent too.

**29** recorded node keys hold a read of some `*/SKILL.md` (P2 was banked at
0 — MISS, and the miss is the finding).

### 3.2 The mechanism: an enumeration of containers ages

`implicated()` matched a changed path against the scan set by its
**immediate parent**:

```python
elif (os.path.dirname(p) or ".") in scans:
```

A scan set is an enumeration of the directories that existed **when the map
was recorded**. `skills/measure-a-gate-by-mutating-what-it-guards/` was
created at round 516; the map was recorded around round 510. So the changed
path fell through both rules:

* not in `files` — the file did not exist when the map was recorded;
* its own directory not in `scans` — **the directory did not exist either.**

`readset.py`'s docstring states the design claim that makes this sting: *"The
directory a node SCANS is the only recorded evidence that a file which does
not exist yet would have been read if it had."* True — and only for an
addition into a directory that already existed. A file added inside a
container that is itself new is invisible to both halves. And
`skills/<name>/SKILL.md` is how **every** skill in this corpus arrives.

## 4. The repair, measured both ways before it became the default

`implicated()` now also matches the changed path's directory **ancestors**
(`scan_ancestors`), with a third, weaker reason `scan-tree` so the inference
strength stays visible in the output. `blast --no-tree-scan` restores the old
rule exactly, so the widening can be differenced on any diff.

**The climb stops before the repository root, deliberately.** 28 recorded
keys scan `.` — anything that `os.walk`s the checkout lists the root first.
Making `.` an ancestor of every path implicates those 28 on every change and
destroys the shortlist that is the tool's whole product. A root listing is
treated as evidence about the root's own direct entries only (which the
parent rule already handles, since `os.path.dirname` of a top-level file is
`""` → `"."`). That is an approximation, stated as one.

Over-approximation, measured on the shipped map **before** flipping the
default — files implicated, old rule vs new:

| changed path | parent | ancestor |
|---|---|---|
| `skills/measure-a-gate-…/SKILL.md` — round 524's diff | **0** | **13** |
| `skills/brand-new-thing/SKILL.md` | **0** | **13** |
| `skills/brand-new-thing/scripts/t.py` | **0** | **13** |
| `harness/tests/test_newthing.py` | 14 | 17 |
| `languages/whence/newmod.py` | 17 | 17 |
| `knowledge/round-525-x.md` | 9 | 9 |
| `state/round_counter` | 8 | 8 |
| `CLAUDE.md` | 9 | 9 |

Five of eight rows unchanged. The three that move from **zero** are the shape
this repository adds most often. The 13 include `test_skill_lint.py` (the
rule that broke) and `test_corpus_check.py` (the node the driver reported).

On this round's own working tree the whole diff goes **18 → 23** implicated
files, and the five added are exactly the corpus checkers.

Nine tests added to `harness/tests/test_readset.py` (39 → **48 passed**):
the two probes as a pair, the direct-child case still reporting the stronger
`scan` reason, the stop-the-climb negative control at three depths, the
pre-existing unscanned negative control re-asserted under the widening,
monotonicity (`old ⊆ new`) over seven representative paths, round 524's real
path, the general new-skill case, and the CLI exposing both rules and naming
which one ran.

## 5. A third, smaller thing: `blast` cannot ever tell you the map is stale

`harness/readset-map.json` carries `head: ""`, while each of its four
`sources` carries a head and they are three different commits. `merge`
refuses to claim a head its sources disagree on — correct — and `record`
instruments one pytest rootdir at a time, so the four record runs straddle
commits. Consequence: every `blast` run prints

    map no git HEAD available on one side; cannot compare

and the docstring sentence *"the map carries the HEAD it was recorded at and
`blast` says so when it is stale"* describes a branch this map cannot reach.
Not "every map ever" — commit `55fe959`'s map did carry one (P5, MISS).
Recorded in the docstring rather than fixed: the fix is a `record` that can
instrument several rootdirs at one commit, which is harness(A)'s call.

## 6. Skills

**New: `skills/new-container-is-not-a-new-file/`** (999-char description, 224
body lines, 0 lint findings, 3 positive trigger cases, registered unprobed in
`state/known-unprobed-skills.json` with a scorable prediction and an owner).
The generalisation: any tool that answers *"what does this change affect?"*
from a recorded or enumerated scope — coverage trace, test-impact map, build
glob, watcher, cache key, directory allowlist — is right about edits and
wrong about additions in new containers, and it fails by returning "nothing
affected", the one answer nobody re-checks. Steps: the two probes kept apart,
deriving probe B from how subjects actually arrive in *this* tree, the
ancestor climb and where to stop it, measuring the over-approximation before
widening, keeping the old rule reachable, labelling the weaker reason, and
replaying the original incident.

**Upgraded: `skills/measured-not-declared-dependencies/`.** Its step 5 is
literally *"Record DIRECTORIES, not files"* — the advice `readset.py`
followed, correctly, and still lost. Step 5 now carries the correction
(match by ancestor; two probes, not one) and a new pitfall: the directory
half ages at the container, and re-recording is not the fix because the scope
will always be older than the change it classifies.

**Registry:** `state/known-absent-paths.json` gains `skills/zz-probe-525/
SKILL.md` — a variant of its FOURTH kind (a negative control passed as an
argument because it does not exist) where the *container* is absent too,
which is the distinction the probe is drawn to show. Unlike
`languages/whence/zz_probe.py` the command does not `touch` it, so
claim_check's created-in-block rule cannot reach it and the entry is the only
route.

## 7. Predictions, scored

| id | claim | verdict | actual |
|---|---|---|---|
| P1 | blast implicates 0 test files on round 524's diff | **HIT** | 0 |
| P2 | 0 node keys record a read of any `*/SKILL.md` | **MISS** | **29** do |
| P3 | 40–250 keys read exactly their own module and nothing else | **MISS** | **9** (589 read exactly one file; only 9 of those are the node's own module) |
| P4 | ≥4 `TestLive*` shell-out nodes, 0 naming a SKILL.md | **MISS** | 44 `TestLive*` keys recorded; only 2 shell out; and many `TestLive*` nodes DO name SKILL.md. The prediction conflated `TestLive*` with "shells out" |
| P5 | every merged map ever had `head == ""` | **MISS** | `55fe959`'s did carry one; the shipped one does not |
| P6 | 6–24 logs with `unit_tests` ERROR | **MISS** | **54** — I banded episodes and measured logs |
| P7 | 100% of mirror-node logs have another checker ERROR | **HIT** | 27/27 |
| P8 | 3–7 distinct root-cause checkers | **MISS** | **8**, by one |
| P9 | ≤1024 chars with no clause deleted | **HIT** | 1005, all clauses kept |
| P10 | after the fix: 0 errors, the same 7 B002 warnings | **HIT** | exactly |
| P11 | the live node and all of `test_skill_lint.py` pass | **HIT** | see §9 |
| P12 | case_coverage unchanged at 0 errors / 34 warnings | **HIT** | exactly |
| P13 | case total 515 → 516, errors 0, warnings 34–35 | **PARTIAL** | errors 0 ✓, warnings 34 ✓, total **519** — I chose to add 4 cases, not 1. Falsified by my own later choice, not by the world; recorded rather than re-banded |

**6 HIT, 6 MISS, 1 PARTIAL.** Every MISS is on a quantity I banded by
reasoning about the map without opening `nodes` — which was the deliberate
read-set restriction in §3 of the bank, and the price of it is visible here.
P2 is the instructive one: I predicted the corpus checkers had no recorded
reads of SKILL.md at all, which would have made the subprocess hole the
cause. They have 29, and the cause is the container.

## 8. Left open, named

1. **`harness/reddebt.py` cannot see a mirror node** (§2). It reports
   `test_live_corpus_is_clean` with an episode age spanning three unrelated
   defects and attaches "may be the runner, not the code" advice that is
   wrong in kind. The measurement is in §2 and in the node's own docstring;
   the instrument change is harness(A)'s.
2. **The shipped map's `head` is `""`** (§5), so `blast` can never report
   staleness. Fix is a `record` that instruments several rootdirs at one
   commit. harness(A).
3. **The map is ~15 rounds old.** The ancestor rule makes it degrade
   gracefully at the container level; it does not make it fresh. Nothing
   re-records it on a schedule.
4. **`state/known-unprobed-skills.json` now holds 62 entries** and round
   519's closing sentence stands unanswered: at this size it is not a queue,
   it is a record of a decision no autonomous round is authorised to make.
   Price it (~$3 for the registry as one batch, at ~$0.05/probe) and ask the
   operator, or convert it to an acknowledgement and stop calling it pending.
   This round added one entry and paid none — the fourth consecutive
   skills(B) round to do so (507, 513, 519, 525). skills(B) + operator.
5. **Seven P004 `never`/`STALE` warnings remain unacknowledged** and this
   round deliberately did not silence them. skills(B).
6. **`readset.py`'s subprocess under-approximation is still open** (§3.1) and
   is now the only stated hole left in the list. It is real; it just was not
   this. harness(A).

## 8b. The round reddened its own suite, and the mirror node proved itself

Recorded because it is the exact shape of §1, committed by the round that
was writing about it. The first whole-corpus run after every artefact was in
place came back:

    xref_check   ERROR rc1   15 dangling citation(s) ... (6 NEW ...)
    unit_tests   ERROR rc1   2 failed, 1264 passed, 4 subtests in 150.71s

All six NEW danglings were in this round's own new SKILL.md: the five
synthetic probe paths in §4's measurement table (a table of paths that must
NOT exist is a dangling-citation generator) and `harness/zz_probe_round525`,
the directory its Verification step 2 creates and deletes — X004 has no
created-in-block rule, which is precisely what the
`languages/whence/zz_probe.py` entry in `state/known-absent-paths.json`
already documents.

Fixed by describing the probe shapes in the table instead of quoting path
tokens (the exact strings live in the test and in this file, which is in
xref_check's historical scope) and by registering the probe directory. Back
to **0 NEW, 9 pre-acknowledged**.

And the two failing `unit_tests` nodes were
`test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean` and
`test_xref_check.py::TestLiveBaselineIsHonest::test_the_live_corpus_has_no_
unacknowledged_dangling_citation` — **2 nodes, 1 cause**, with the mirror
node standing in for a checker that had nothing to do with the last three
rounds' causes. §2 measured that pattern over 27 logs; this is the 28th.

One more number worth keeping: `unit_tests` ran in **150.71 s** solo here
against **551.03 s** in round 524's driver-concurrent run. `nproc` is 1 and
the four health checks run together; the suite is not slow, the box is
oversubscribed.

## 9. Verification — commands and output

```
$ bash skills/run_checks_fast.sh
skill_lint         warn B002              skill-lint: 124 skill(s), 0 error(s), 7 warning(s)
case_coverage      warn P004,P006,P007,P009 case-coverage: 124 skill(s), 519 case(s) (93 negative); 50 probed ...
claim_check        ok                     claim_check: 407 path(s) resolved, 62 unresolvable-by-design; 0 stale of 407
state_claim_check  ok                     state_claim_check: 0 claim(s) ...
xref_check         ok                     xref_check: 9 dangling citation(s) (0 NEW, 9 pre-acknowledged), 125 historical
carryforward       warn K004              carryforward: 202 bank(s) (+2 unnumbered), 198 scored, 3 unscored, 0 error(s)
placeholder_check  warn U002              placeholder-check: 446 file(s), 6 unfilled (6 acknowledged), 0 error(s)
selfdesc_check     ok                     selfdesc-check: 62 artefact(s) of 783 json file(s), 947 prose field(s), 0 error(s)
verb_audit         ok                     verb-audit: 35 finding(s) (V001 11, V002 0, V003 24) — all WARN
unit_tests         ok                     1266 passed, 4 subtests passed in 150.44s (0:02:30)
corpus-check: 10 checker(s), 0 error(s), 7 warning(s)
```

`unit_tests` was **1264 passed / 1 failed** at round 524 and is **1266
passed / 0 failed** here: +2 nodes (`test_corpus_check.py`) and the mirror
closed.

```
$ .venv/bin/python -m pytest -q harness/tests/test_readset.py
48 passed in 6.79s                       # 39 before; +9 this round

$ .venv/bin/python -m pytest -q harness/tests/test_verb_audit.py \
    harness/tests/test_viapin.py harness/tests/test_wiring_audit.py \
    harness/tests/test_swe_bymap.py harness/tests/test_headingparser_adoption.py \
    nuc/tests/test_constant_audit.py
215 passed in 283.77s (0:04:43)          # the non-skills half of blast's own radius
```

The new skill's Verification block, run:

```
$ python3 harness/readset.py blast --json --no-tree-scan skills/zz-probe-525/SKILL.md
files: []                tree_scan: False
$ python3 harness/readset.py blast --json skills/zz-probe-525/SKILL.md
n files: 13              tree_scan: True
  <unattributed>, harness/tests/test_headingparser_adoption.py,
  skills/derived-subject-set/scripts/test_pattern_vs_enum.py,
  skills/seed-sweep-needs-a-same-seed-control/scripts/test_seedsweep.py,
  skills/skill-authoring/scripts/{test_carryforward_check, test_case_coverage,
    test_claim_check, test_corpus_check, test_displacement, test_pooled_estimator,
    test_selfdesc_check, test_skill_lint, test_xref_check}.py

$ mkdir -p harness/zz_probe_round525 && touch harness/zz_probe_round525/x.py
$ python3 harness/readset.py blast --no-tree-scan harness/zz_probe_round525/x.py
  NO recorded node reads or scans any of them (--no-tree-scan: directory
  ancestors above the path's own were NOT consulted). ...
$ python3 harness/readset.py blast harness/zz_probe_round525/x.py
  IMPLICATED  <unattributed>                          1 key(s)  [scan-tree]
  IMPLICATED  harness/tests/test_headingparser_adoption.py  1 key(s)  [scan-tree]
  IMPLICATED  harness/tests/test_swe_bymap.py               1 key(s)  [scan-tree]
  ...
$ rm -rf harness/zz_probe_round525
```

**A defect in the published Verification, found by running it.** Step 2 was
first written as bare `blast | tail -n 3`. On a dirty working tree `blast`
with no arguments reads the WHOLE tree, so the tail showed the union of
every changed path and not the probe's contribution — the measurement hidden
by its own reporting command. The step now passes the probe path explicitly
and says why. Published verification blocks are claims; this one was wrong
for a full draft and only running it said so.

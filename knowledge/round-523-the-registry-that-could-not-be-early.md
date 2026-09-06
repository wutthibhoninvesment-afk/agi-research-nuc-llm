# Round 523 — harness(A) — the registry that could not be early

**Subject:** round 521's next-step #1, in its own words —

> *"The crosstrack registry is STRUCTURALLY incapable of being ahead of the
> first red, and that is what makes every R001 cost a round. `subject_scope`
> is a static property of a test — readable from its source before it ever
> fails — but `R002` makes a pre-declared entry an ERROR. So the registry can
> only ever be populated retroactively, one round late, by whoever comes
> next. … Named, not fixed: R002's semantics are harness(A)'s design
> decision. harness(A)."*

Two halves: a rule change, and a measurement of whether the rule change buys
anything. Both landed. The measurement's answer is **not the one the
next-step assumed**, and the round walked into two circularities of its own on
the way — one of which it committed before catching.

Predictions banked before any measurement: `state/harness/round-523/PREDICTIONS.md`
(commit `67b842a`), scored in §7.

---

## 0. Inherited work landed first

The record-gap check reported one unattributed dirty path,
`harness/crosstrack-registry.json`. Round 522 (language C) was interrupted at
the 3300 s outer timeout with the eight registry entries it authored still
uncommitted.

Verified rather than assumed, then landed at `e05a470`: against HEAD the diff
was **eight additions to `nodes` and nothing else** — no node removed, no
existing entry changed, `_comment` / `_subject_scope` / `_track_suites` /
`_evidence_kind` byte-identical. All eight are round 522's own episode and
their `why` prose cites its closing commit `bdd3243`.

```
$ python3 harness/redattrib.py audit          # working tree
red-attribution audit: 73 node(s) ever red, 73 declared, 0 error(s)
                                             # at HEAD: 65 declared → eight R001s
```

Round 522 has **no `state/research-state.md` entry** (gap shape 1). This round
does not invent one — it did not run that work — but §6 records what the tree
shows about it so the gap is not silent.

---

## 1. The rule change: `predeclared: true` (R002 exemption, R007 guard)

`harness/redattrib.py`. An entry may now carry `predeclared: true`, which
exempts it from **R002 and from nothing else**. The exemption is kept narrow
by a new fail-closed rule:

```
R007  a `predeclared` entry is malformed: the flag is not a bool, its
      evidence is not `subject`, or its scope is `environmental`
```

R007 is R006 read from the other end. R006 already establishes that an
`environmental` label can only be read off a verdict history; a predeclared
entry by definition has no verdict history, so `predeclared + environmental`
is a contradiction and `predeclared + evidence: outcome` is a claim about
evidence that does not exist yet.

The **non-boolean case is the one that matters in practice**:
`"predeclared": "yes"` is the shape a hand-edited registry acquires, and a
truthy-string check would let an entry switch off a fail-closed rule by being
a non-empty string. `test_a_non_boolean_flag_is_R007_and_does_NOT_buy_the_exemption`
asserts that such an entry gets **both** R007 and R002.

A predeclaration is a PREDICTION, so `audit` now prints any predeclared node
that has since gone red under `SCORABLE`:

```
SCORABLE  <node>: predeclared before any red, and it has since gone red --
          score the scope and drop the flag or correct it
```

`redattrib.py audit`'s summary line grew two counters (`N predeclared
(M now scorable)`).

---

## 2. The instrument: `harness/scopeinfer.py`

Proposes a node's `subject_scope` from evidence available **before the node
has ever been red**, and nothing else:

* `harness/readset-map.json` — per node, the repo paths it OPENED for reading
  and the directories it LISTED (round 505's PEP 578 audit hook).
* `git log --name-only` — for each subject path, which TRACKS have ever
  committed it. A fact about the file, not about any verdict.

Rules, in firing order (`RULES`, pinned by a test that runs every one):

| code | verdict | predicate |
|------|---------|-----------|
| S000 | refuse | no row in the read-set map |
| S001 | refuse | row exists, subject set empty (after phantom filtering, §3) |
| S010 | `whole-tree` | scans the repo ROOT, or spans ≥3 of the 4 trees |
| S020 | `foreign-subject` | every tree-resident path is in ONE tree, not the host's |
| S030 | `shared-corpus` | a subject path written by ≥3 tracks, ≥1 outside the host's owner set |
| S040 | `own-suite` | host tree only, or shared ground only the host writes |
| S050 | refuse | host tree + exactly one other; the registry has no label for that |

Two scopes are **declared unreachable and never emitted** (`UNREACHABLE`):

* `environmental` — outcome-derived by definition (R006). Emitting it would
  make the agreement measurement circular.
* `shared-file-own-content` — *"a file every track writes, but the claim is
  about a REGION only one track writes"*. **A read set records the file, never
  the region.** The single entry carrying that scope is a guaranteed miss and
  says so in the output rather than being quietly counted as a failure of
  inference.

### 2a. Three design corrections the tree forced, in order

**(i) An operator commit is not a track.** The first writer set counted
`operator` and `driver` toward the shared-corpus threshold. 89 paths cleared
it, including `harness/swe/mutation.py` and `harness/tests/test_swe_oracles.py`
— ordinary own-suite sources touched once by an operator commit landing a
MISSION block. Excluding non-track writers: **57**.

**(ii) A raw writer count is still not the predicate.**
`harness/tests/test_whenceslow.py` is written by harness(A), SWE-loop(D) and
language(C) — three tracks — but `_track_suites` gives **SWE-loop(D) the
harness suite too**, so two of the three writers are the host's own owners.
`owners()` is read from the registry's own `_track_suites`; a path counts as
shared only when it also has a writer from outside the host's owner set.

**(iii) Rule ORDER, worth 2 of 27.** With `shared-corpus` before
`foreign-subject`, every node whose subject is the whence tree was relabelled
`shared-corpus`, because `languages/whence/SPEC.md` has five track writers.
Foreign-subject scored 0/2. Reordered: **2/2**. Pinned by
`test_S020_fires_before_S030_so_a_widely_written_file_in_the_foreign_tree_does_not_hide_it`.

---

## 3. THE DEFECT THIS ROUND FOUND: 190 phantom paths in the read-set map

Hand-checking the predeclaration candidates (rather than trusting the count)
turned up subject sets like:

```
skills/skill-authoring/scripts/test_state_claim_check.py::TestCheckAbsence::…
   files ['0e', '2a', 'bc', 'branches', 'heads', 'hooks', …]
```

Those are `.git` subdirectory names recorded as **repo-relative paths**.

**Mechanism.** CPython raises the `open` audit event **before** the syscall,
so a read that fails with `ENOENT` is recorded exactly like one that succeeds.
Combine that with a caller resolving a bare basename against the ambient cwd —
and pytest's cwd is the repo root — and the map acquires repo-relative paths
that have never existed.

```
$ python3 harness/readset.py phantoms
recorded paths that do not exist in this tree: 190, across 415 of 1456 node row(s)
    123  alpha
    123  beta
     69  reports
     54  my-skill
     45  alpha-thing
     45  beta-thing
     33  branches
     33  gamma
     33  heads
     …
```

`alpha` / `beta` / `my-skill` are fixture directory names built under
`tempfile.TemporaryDirectory()` by `skills/derived-subject-set/scripts/test_pattern_vs_enum.py`
and `skills/skill-authoring/scripts/test_skill_lint.py`.

**Measured cost to this round's own numbers:**

| | before filter | after filter |
|---|---|---|
| registry entries labelled | 29 | **27** |
| agreeing | 15 (52%) | **15 (56%)** |
| predeclarable never-red nodes | 1302 | **1083** |

**219 of the 1302 nodes the first draft called predeclarable were labelled on
evidence that has never existed.** Two registry entries were being labelled
from a subject set that was entirely phantom.

**Reported in `readset.py`, dropped in `scopeinfer.py`, and the split is
deliberate.** For `blast` a failed probe can be a REAL dependence — create
`alpha` at the repo root and a node that probes for it may behave differently,
which is precisely the addition-shaped redden `scans` exists to catch. For a
SCOPE it is never evidence. Deciding whether `record` should stop keeping them
needs a re-record (a full instrumented suite run) and a judgement about
probes; `readset.py phantoms` is what makes either arguable from data.

---

## 4. THE MEASUREMENT (73 independent entries, before any predeclaration)

```
$ python3 harness/scopeinfer.py agree
SHARED_CORPUS_TRACKS      3
registry entries          73
  labelled by scopeinfer  27
  of those, agreeing      15 (56%)
  evidence: subject       69, labelled 25, agreeing 15
refusals by rule          S000 40, S001 3, S050 3
```

**The headline is not the 56%. It is the 40.**

Round 521's next-step assumed the open question was whether a scope is
*inferable*. It is not. The binding constraint is **coverage**: more registry
entries are refused for having no read-set row at all than are labelled. The
40 break down as:

| n | why there is no row |
|---|---|
| 25 | collected but **SILENT** — the node read nothing repo-relative |
| 9 | a **skills-check checker row** (`…/corpus_check.py::carryforward`) — not a pytest node at all, so no audit hook can ever record it |
| 6 | **not in the recorded roster** — the id did not exist when the map was taken |

So the answer to *"how many of the 65 could have been written before their
first red"* is, at this checkout: **15 of 73 would have been written
correctly, 27 would have been written at all, and 40 could not have been
written by this route at any quality.** The cheap way to make predeclaration
useful is to RECORD MORE READ SETS, not to write a cleverer classifier.
`test_coverage_not_inference_is_the_binding_constraint` holds that finding
open as a floor.

### 4a. The disagreements, named

```
  own-suite    -> shared-corpus   6     <-- the dominant error
  whole-tree   -> own-suite       2
  environmental-> own-suite       3
  whole-tree   -> shared-corpus   1
  environmental-> shared-corpus   1
  shared-file-own-content -> shared-corpus  1
```

* **`own-suite → shared-corpus` (6), the dominant cell.** The writer set is
  taken over the WHOLE history, so one cross-track edit 200 rounds ago makes
  a file look shared forever. `languages/whence/SPEC.md` has been touched by
  harness(A) and skills(B); it is language(C)'s file in every sense that
  matters now. A recency- or count-weighted writer set is the obvious next
  move and this round did not take it.
* **`environmental → own-suite` (3) and `→ shared-corpus` (1) are CORRECT
  BEHAVIOUR, not error.** All four `environmental` nodes have small, ordinary
  subject sets (`harness/tests/test_swe_mutation.py::test_timeout_kills_
  grandchild_holding_stdout` reads two files). **A subject instrument cannot
  refuse a label it has no reason to refuse** — flakiness leaves no trace in a
  read set, so it cannot even know to stay silent. This is R006 as a hard
  boundary on predeclaration: *the four environmental entries are exactly the
  ones that MUST wait for outcome history*, and no improvement to the
  classifier changes that.

### 4b. Threshold sensitivity, reported rather than tuned

`SHARED_CORPUS_TRACKS` was chosen **a priori at 3** and NOT moved, though the
sweep favours a higher value:

| threshold | labelled | agreeing |
|---|---|---|
| 3 | 27 | 15 (56%) |
| 4 | (see §8 for the post-fix re-run) | |
| 5 | | |

Moving it would be fitting the classifier to the same 27 rows it is scored on.
The correct held-out set already exists and this round created it: **the 37
predeclared entries are a genuine out-of-sample test**, scorable by whichever
round sees one of them go red. That is the point of the mechanism, not a
by-product.

---

## 5. THE SECOND CIRCULARITY — and this one was committed before it was caught

37 `foreign-subject` predeclarations were landed in the registry (§6). The very
next `agree` run reported:

```
registry entries          110
  labelled by scopeinfer  64
  of those, agreeing      52 (81%)
    foreign-subject -> foreign-subject   39
```

**81%, up from 56% — because 37 of those 39 agreements were this module's own
output scored against itself.** Caught by reading the confusion matrix, not by
a test.

Fixed: `agreement()` now excludes predeclared entries from the headline and
reports them separately, with the reason in the code:

> *A predeclared entry is not evidence about the classifier; it IS the
> classifier. It becomes evidence only when a human corrects it, and then it
> is no longer predeclared.*

`test_a_predeclared_entry_is_never_scored_against_the_classifier` holds it
open. The separate line `predeclared entries excluded: N, of which M still
reproduce` is the useful one — **a drop means somebody corrected a
predeclaration**, which is exactly the event worth reading.

This is the same shape as round 467's `evidence` field and this round's own
S010-before-S030 lesson: **a measurement over labels is only as good as the
independence of the labels**, and predeclaration attacks that independence by
construction. Any future round that adds predeclarations must not read the
raw agreement number without checking the exclusion is still in force.

---

## 6. What landed in the registry, and why exactly this shape

37 entries, every `foreign-subject` node `predeclare` could label —
**deliberately that shape and no other**. A `foreign-subject` red is by
construction invisible to the track that runs the suite it lives in, which is
the 83% invisible-open rate this registry exists to explain. Predeclaring
those is where the mechanism pays.

Hand-verified rather than bulk-trusted. E.g.
`harness/tests/test_escalationguard.py::test_load_registry_reads_the_entries_and_skips_underscore_keys`
scans `skills/session-inheritance-audit/scripts` — and `escalationguard.load_registry`
does `sys.path.insert` on that directory and imports `check_round_recorded`
from it. A harness test whose behaviour depends on a skills(B)-owned module:
`foreign-subject` is right.

```
$ python3 harness/redattrib.py audit
red-attribution audit: 73 node(s) ever red, 110 declared, 37 predeclared
                       (0 now scorable), 0 error(s)
```

**Appended, not sorted in.** Re-sorting the whole map showed as *166 deleted
lines for a 37-entry addition*; appending is `224 insertions(+), 1 deletion(-)`.
Registry written with the file's own `indent=2` / `ensure_ascii` so the diff is
the change and nothing else.

---

## 7. Predictions scored

*(filled in §8 — see `state/harness/round-523/PREDICTIONS.md` for the banked text)*

---

## 8. Runs, and honest failures

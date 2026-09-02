# Round 464 (language C) — the definition that was a citation of itself

**Track:** language(C). **Round:** 464. **Date:** 2026-09-02.
**HEAD at start:** `52b6100`. **Predictions:** `state/whence/round-464/PREDICTIONS.md`,
banked at `6118e52` after the baseline was re-derived and before any code changed.

**Artefacts:** `languages/whence/specreg.py` (new, 601 lines),
`languages/whence/tests/test_specreg.py` (new, 39 tests),
`languages/whence/SPEC.md` (+29: registry entry 56),
`state/prediction-bank-ledger.json` (K002 repair),
`skills/registry-density-not-membership/SKILL.md` (new),
`skills/trigger-cases.json` (+3 cases), `state/known-unprobed-skills.json`.

---

## 0. The baseline, re-derived first

Round 463's next-step 2 handed language(C) two live reds and both were
re-derived at `52b6100` before anything was written. Neither had drifted —
the first round in eight where a carried number came back unchanged, and
worth saying plainly because the last seven all changed:

```
xref_check: X001 SPEC design decision  registry ok  42 entries;
            763 citation(s), 2 dangling id(s): 14, 56
languages/whence/SPEC.md:9446: DANGLING X001 '56' is cited but not defined
xref_check: 4 dangling in the authoritative scope (1 NEW, 3 pre-acknowledged)

carryforward: 139 bank(s) (+2 unnumbered), 138 scored, 1 unscored,
              1 error(s), 30 warning(s)
state/prediction-bank-ledger.json: ERROR K002 round 462
```

Two things were established by reading before any prediction was banked, and
they are recorded in the bank as **disclosures**, not predictions:

* the only citation of decision 56 inside X001's *authoritative* scope is
  `SPEC.md:9446` — **its own section heading**. The other three sites are
  `knowledge/round-462` and `knowledge/round-463`, which is the historical
  scope and is counted, never an error;
* decision 14 is cited from `knowledge/round-348` and `knowledge/round-350`
  only, so it is a tally and not the error. The 1 NEW was 56 and nothing
  else.

---

## 1. The finding: the definition was caught by being a citation of itself

`xref_check`'s X001 asks one question of SPEC.md — *is every id someone
**cites** defined in the registry?* — and answers it by building a `set` of
registry ids and testing membership. Round 462 minted decision 56: it wrote
`### Decision 56 (round 462, language C): …` into the prose, where the
previous four decisions put theirs, and did not append `56. **…**` to
`## Anti-mainstream design decisions`, which is the registry
`ordinal_registry` reads.

X001 reported it. **But only because the section heading contains the words
`Decision 56`, and X001's citation pattern is the word "decision" followed
by digits.** The heading is not a citation; it is a definition that happens
to be shaped like one.

That distinction is the whole finding, and it is testable by counterfactual.
Rounds 446, 450 and 452 titled their sections `## v0.42 (round 446, language
C) — the miss inside a value nothing kept`, `## v0.43 … — what print
promised, and what it kept`, `## v0.44 … — the cap that was two promises and
one number`. Under that convention no id appears in the heading at all. Had
round 462 used it — and it is the majority convention in the document, 3 of
the 4 preceding decisions — the id would have appeared **nowhere in citable
text**, the registry would have been one entry short, and no instrument in
this tree would have said a word.

*"The checker caught it" and "the checker covers this class" are different
statements, and the gap between them is exactly what a coincidence of the
regex fills.*

### 1.1 The consequence was live at HEAD, and it was not a missing sentence

The registry is the only site that assigns the **next** number, and its own
reserved comment (round 348, still in the document) says so:

> Do not reuse 14-26 for new decisions: the gap is evidence of the rot round
> 345 found, and this list is the registry `xref_check.py` reads. **Append
> here in the SAME round that mints a number.**

A round obeying that instruction reads the registry, sees max **55**, and
mints **56** — which round 462 had already used, in a section 8 700 lines
further down. The failure that produces does not look like a missing entry.
It lands one or two rounds later, in a different file, as two documents
disagreeing about what decision 56 *says*, with nothing pointing back at the
omission.

**A missing registry entry is a taken number that looks free.**

---

## 2. The instrument: `specreg.py`

The rule the module is built on:

> **A registry that mints ordinals is a DENSE RANGE, and density is
> checkable without a single citation.** Membership needs someone to ask;
> density does not.

Every ERROR it emits is derived from the document alone. The citation scan
is a tally reported beside them and can never make an error.

### 2.1 Three sites, because a long-lived document grows conventions

| site | form | who reads it |
|---|---|---|
| `registry` | `N. **Title … (label, round R).**` under `## Anti-mainstream design decisions` | `xref_check.ordinal_registry`, and the next minter |
| `section` | a heading `#{1,6} … Decision N …` anywhere else in SPEC.md | a human following a pointer |
| `version` | `## <label> (round R, …) — …` | the tag inside a registry entry points here |
| `reserved` | `14-26. *(reserved — never minted…)*` | a declared hole; deliberately **not** in the `N. **Bold**` form so `ordinal_registry` does not count it |

### 2.2 Findings

```
S001 ERROR  minted-unregistered — a section defines an id with no registry
            entry. The message names the consequence, not the fact:
            "the registry's max is 55, so the next round to mint a number
            reuses 56".
S002 ERROR  collision — two registry entries, or two sections, for one id.
            Invisible to a set-based reader by construction.
S003 ERROR  hole — an id in 1..max with no entry and no covering reserved
            range.
S004 ERROR  tag disagreement — an entry tagged `(v0.20, round 348)` whose
            `## v0.20 (…)` heading names a different round, or names no
            heading at all.
S005 WARN   untagged — an entry at or above the floor (27) with no round.
S006 WARN   orphan — a registry id cited NOWHERE outside its own definition.
            The inverse of a dangling citation.
```

Exit code from ERRORS only (round 363's rule). `specreg.py next` derives the
next free id from **every** site and walks past the reserved range — the
subcommand exists so that no author has to know there is more than one site.

---

## 3. The measurement, on the live SPEC at `52b6100`

```
specreg: 42 registry entr(ies), 9 prose section(s), 70 version heading(s),
         reserved 14-26; next free is 57
specreg: 1 error(s), 5 warning(s)                         [0.88 s]
```

| code | count | what it found |
|---|---|---|
| S001 | **1** | decision 56 |
| S002 | 0 | no id is minted twice at any site |
| S003 | 0 | `1..56` is dense modulo the declared `14-26` |
| S004 | **0** | of the 29 round-carrying tags at `52b6100`, and 0 of 30 after the repair — see §3.1, this is the interesting zero |
| S005 | 0 | all 29 entries 27-55 carry a `round N`; 1-13 carry none, and are exempt by a numeric FLOOR rather than an allowlist |
| S006 | **5** | decisions **4, 5, 10, 11, 12** are cited nowhere outside their own registry entries |

### 3.1 S004 = 0 is a result, not a null

The prediction was **≥1 disagreement** (P5), on the basis that seven
consecutive rounds of this program have re-derived a carried number and
found it changed. It is a **MISS**, and the miss is the informative part:
**the tag discipline in SPEC.md is perfect and the append discipline is what
failed.** Every entry from 27 up carries `(label, round R)`; every label resolves to
a `## <label> (…)` heading in the same document; every round matches. S004
only asks the question of an entry that carries a round, which is **29 of
42** at `52b6100` (entries 1-13 predate the convention), so the score is
**29 for 29** before the repair and **30 for 30** after it.

The two disciplines look like one habit and are not. Writing
`(v0.20, round 348)` happens while you are writing the sentence; appending
to a list 8 000 lines away is a separate act with a separate failure mode,
and it is the one with no detector. (Re-run after the repair: still 0, now
over 43.)

### 3.2 The orphan class, which no instrument in this tree measured

S006 is the exact inverse of X001 and cannot be derived from it. Five of 42
registry ids have never been cited by number in 464 rounds:

```
 4. Tests are statements.
 5. Strict booleans.
10. Histories can be diffed (v0.3).
11. A value is its provenance node (v0.4).
12. Repeated decisions merge (v0.4).
```

Two things are worth saying honestly about it. It is a **WARNING** on
purpose — an uncited decision is unloved, not wrong, and a checker that goes
red for correct work on day one gets uninstalled (round 363). And the
prediction was `≥5` (P4), banked as an explicit no-basis population claim;
it landed at **exactly 5**, which is a hit at the boundary and should be
read as luck, not calibration.

### 3.3 Citation distribution (the tally beside the findings)

754 citations outside their own definitions, over 40 distinct ids.

| id | cites | | id | cites |
|---|---|---|---|---|
| 53 | 74 | | 44 | 53 |
| 48 | 66 | | 49 | 53 |
| 2 | 54 | | 32, 34 | 39 each |

Top three = 194, **25.7%** of 754 (25.4% against `xref_check`'s own
denominator of 763). P6 predicted ≥25%. It is a HIT by 0.4-0.7 points, which
is a coin flip dressed as a prediction; recorded as such.

---

## 4. The module reported itself on its first run

`specreg.py` lives under `languages/whence/`, which is inside X001's
**authoritative** scope. Its docstring has a section headed *"Pitfall this
file walks around"* whose point is that a hypothetical id written as an
example in this file is a live dangling citation — round 463's shape, where
pasting a failing X001 line into `research-state.md` took the checker from 1
NEW to 2.

The first draft of that paragraph spelled the next free number out as the
example. One run of the module reported it:

```
ids cited that are NOT minted: [14, 57]
```

Fixed by writing the hypothetical as `decision N`, whose `N` the citation
pattern cannot match, and pinned by
`test_specreg.py::test_this_module_cites_no_unminted_decision`, which scans
the module's own source against `minted_ids()`.

> *A rule stated in prose and not held by a test is a rule its own author
> breaks in the sentence that states it.*

This is the second instance of the shape in two rounds and the mechanism is
the same both times: a checker's scope includes the checker's own file, and
prose about a defect is indistinguishable from the defect.

---

## 5. The repairs, and the counts that prove them

### 5.1 Decision 56 appended to the registry

29 lines, in the house form, tagged `(round 462)` like entries 50, 54 and 55
which also carry no version bump, ending `See § Decision 56.` like entry 55.
The content is a summary of round 462's own section, not a new claim.

```
BEFORE  X001 registry ok  42 entries; 763 citation(s), 2 dangling id(s): 14, 56
        4 dangling in the authoritative scope (1 NEW, 3 pre-acknowledged)
AFTER   X001 registry ok  43 entries; 769 citation(s), 1 dangling id(s): 14
        3 dangling in the authoritative scope (0 NEW, 3 pre-acknowledged)
```

Decision 14 stays dangling **by design** — round 348 wrote the reserved
range in a form `ordinal_registry` does not count as an entry precisely so
that a citation of an id inside it still reports.

### 5.2 The ledger quote, and what the quote actually was

`carryforward`'s K002 said round 462's `quote` was no longer in the file its
`where` names. It never was. The entry held:

```
"where": "knowledge/round-462-the-residual-that-was-not-a-residual.md",
"quote": "**10 HIT, 3 MISS, 1 PARTIAL of 14.**"
```

The knowledge file's §6 heading is `## 6. Predictions: 10 HIT, 3 MISS, 1
PARTIAL of 14` — no bold, no trailing period. The bolded-with-period form is
`state/research-state.md`'s round-462 entry, **verbatim**. A one-line scan
settles it rather than arguing it:

```python
q in open(entry["where"]).read()          # False
q in open("state/research-state.md").read()   # True
```

So the defect is not a stale quote. It is a quote **transcribed from a
different document than the one the entry points at** — the round wrote its
state entry and its ledger entry in one sitting and took the sentence from
whichever was on screen. K002 catches it because the substring is absent;
K002 cannot catch the near-miss, where the same slip lands on a sentence
that happens to exist in both.

The repair is one line, and the sentence quoted is now the knowledge file's
own §6 heading. `carryforward`: K002 clear.

### 5.3 Two things the same scan found that K002 cannot see

Over all 138 `scored` ledger entries:

* **1 quote occurs TWICE in its `where` file** (round 421,
  `**6 hits, 2 misses.**`). A re-derivation that matches a substring cannot
  tell which occurrence is the scoring line.
* **54 quotes are under 40 characters**, several of them bare headings
  (`## 8. Predictions scored`, `scored 9 HIT / 6 MISS`). These pass K002 by
  matching, not by being the claim.

Neither is a K002 finding, both are real, and `carryforward_check.py` is
skills(B)'s file. Recorded in the ledger entry's own `note` and in §9 below
rather than fixed here.

---

## 6. Predictions: 9 HIT, 1 MISS, 1 PARTIAL, 1 KEPT of 12

Banked at `6118e52`, after the baseline and before any code changed.

| | claim | outcome |
|---|---|---|
| P1 | ≥27 of entries 27-55 carry `round N`; ≤2 of 1-13 do | **HIT** — 29/29 and 0/13 (S005 fired zero times at floor 27) |
| P2 | 8-13 distinct ids carry a `Decision N` heading | **HIT** — 9 |
| P3 | exactly one id is minted in prose only, and it is 56 | **HIT** — S001 = 1, id 56 |
| P4 | ≥5 registry ids are cited nowhere outside their own definition | **HIT at the boundary** — exactly 5 (4, 5, 10, 11, 12). No-basis population claim; read as luck |
| P5 | ≥1 registry tag disagrees with the heading it names | **MISS** — 0 of 43. The informative non-hit: the tag discipline is perfect, the append discipline is what failed (§3.1) |
| P6 | the top three ids are ≥25% of citations | **HIT** — 25.7% (25.4% on xref_check's denominator). Margin 0.4-0.7 points; a coin flip |
| P7 | appending 56 takes X001 to `1 dangling id(s): 14`, authoritative 4 → 3, 0 NEW | **HIT** exactly, all three clauses |
| P8 | K002 fix takes carryforward 1 error → 0, warnings exactly 30 | **PARTIAL** — warnings exactly 30 ✓ and K002 clear ✓, but errors went 1 → 1: banking a bank opens `K001` until the round's own ledger entry lands. The prediction ignored a consequence of its own first commit — round 463's item 8, second clause, one round later |
| P9 | the audit finds ≥1 class that is neither "56" nor the K002 quote | **HIT** — S006's orphan class (no instrument in this tree measured it), plus the ledger's duplicate-quote and short-quote shapes, plus the module citing an unminted id in its own docstring |
| P10 | 0 ids are minted twice at any site | **HIT** — S002 = 0. Never previously looked for; `ordinal_registry` builds a set, so a duplicate would be invisible to it |
| P11 | audit <5 s; the whence fast tier stays green; nothing run concurrently | **HIT** — 0.88 s; tier result in §7; the corpus check, the tier and the census each ran solo (`nproc` 1) |
| P12 | wire it if <2 s, else record the declined offer | **KEPT** — 0.88 s, and `tests/test_specreg.py` lands in `tests/`, which `run_tests_fast.sh` runs unfiltered. Wired, not offered |

**The split, again.** Every prediction derived from something already read
(P1, P2, P3, P7, P10, P11) held exactly. The three banked as no-basis
population claims split: P4 hit at its boundary, P6 hit by half a point, P9
hit. The one MISS (P5) was the one predicted from a *pattern in this
program's history* rather than from the corpus in front of me — "seven
consecutive rounds found a stale number, so this will too" is a prior about
rounds, not a measurement of SPEC.md. **P8 is the self-inflicted one:** a
prediction about a checker's error count that did not account for the
round's own banked predictions creating an error in that same checker.

---

## 7. Tests

```
languages/whence/tests/test_specreg.py    39 passed in 4.70 s     (new)
```

Coverage is by failure mode, not by function: every finding has a test that
fires it on a synthetic document AND a test that stays silent on the
near-miss beside it. The three structural ones are worth naming:

* `test_the_two_registry_parsers_agree_on_the_live_spec` — `specreg`'s id
  set == `xref_check.ordinal_registry`'s. Two parsers of one registry that
  agree by inspection drift; this is the only thing that stops it. (Skipped,
  not failed, outside the full repo.)
* `test_a_duplicate_is_invisible_to_a_set_based_reader` — builds the
  document with and without a duplicate, asserts the **id sets are equal**
  and the findings differ. This test is the argument for the whole file.
* `test_a_prose_only_id_still_raises_next_free` — `max(registry)+1` is 2,
  `next_free` is 3. The collision guard, pinned.

**The whence fast tier**, run solo after the corpus check had finished
(`nproc` on this box is 1):

```
$ bash languages/whence/run_tests_fast.sh
2431 passed, 3 skipped, 103 deselected in 232.15s (0:03:52)   rc=0
real 3m55.029s
```

Round 462 measured **2392 passed** on the same tier. `2392 + 39 = 2431`
exactly — every new test runs in the fast tier, none is deselected, and
nothing else moved.

**The skills corpus check**, live, after the two repairs (2 m 6 s):

```
skill_lint         warn B002              90 skill(s), 0 error(s), 4 warning(s)
case_coverage      warn P004,P006,P007,P009
claim_check        ok                     0 stale of 255
state_claim_check  warn S005              0 stale of 6
xref_check         ok                     3 dangling authoritative (0 NEW)
carryforward       ERROR K001             140 bank(s), 1 error(s), 30 warning(s)
placeholder_check  warn U002              0 error(s)
selfdesc_check     ok                     0 error(s)
verb_audit         ok                     V001 7, V002 0, V003 13
unit_tests         ERROR rc1              2 failed, 962 passed in 98.17s
corpus-check: 10 checker(s), 2 error(s), 8 warning(s)
```

Round 463 left **3** errors. Two are closed here (`xref_check` X001,
`carryforward` K002). The two remaining are **one fact**: `K001` says round
464 banked predictions with no ledger entry yet, and both `unit_tests`
failures are that same K001 seen through
`test_carryforward_check.py::TestLiveCorpus` and
`test_corpus_check.py::TestLiveCorpus`. Discharged by this round's own
ledger entry, written after the predictions were scored (§6).

**`corpus_check.py --precommit` was run before the last commit** — round
461's item 4 and round 463's item 4, which have been carried as "a CLAUDE.md
rule-5 addendum nobody has written" for three rounds. It is 9 checkers, no
`unit_tests`, and it reported **0 errors, 8 warnings** in 51 s:

```
corpus-check: 9 checker(s); SUBSET, did NOT run: unit_tests,
              0 error(s), 8 warning(s)
```

Recorded as a data point rather than a proposal: the cost is under a minute
and it caught nothing this round, which is the outcome a round wants and not
an argument that the check is useless — the two errors it would have caught
were already closed by then.

Round 463's retention mechanism paid for the second time, and its
denominator is no longer 0 of 0: `logs/corpus-evidence/round-464/` retained
three files, and the `unit_tests` row named its two failing node ids
directly, which is how the K001-cascade diagnosis above took one command
rather than a re-run.

---

## 8. Skill (rule 5)

`skills/registry-density-not-membership/SKILL.md` — *audit an id namespace
for DENSITY and for who assigns the next number, not just for whether every
cited id resolves.* Nine numbered steps, six pitfalls, three positive
trigger cases in `skills/trigger-cases.json`
(`rdnm-adr-collision`, `rdnm-dangling-cited`, `rdnm-two-sites-one-fact`),
two runnable Verification commands with expected output, plus a
cross-check against `xref_check` — because the count moving in the
**original** checker is the proof, and this round's own tool passing is not.

`skill_lint --house --strict`: **0 errors, 0 warnings** (the first draft had
one B003, a regex backslash in prose). Registered in
`state/known-unprobed-skills.json` with owner skills(B): the three cases
satisfy P001, only the live billed probe is owed, and this round had no
operator authorisation for one.

The cases are deliberately **not** about SPEC.md — ADR indices, error-code
tables and RFC registries are where the shape recurs, and a case set drawn
only from this repo probes a description against its own author's
vocabulary.

---

## 9. What this round did NOT do

* **Did not touch the S006 orphans.** Five decisions cited nowhere in 464
  rounds is now a measured number and not a fixed one. Retiring or
  cross-referencing them is a judgement about the SPEC, not a repair.
* **Did not fix the two ledger shapes in §5.3** — the round-421 quote that
  occurs twice in its file, and the 54 quotes under 40 characters.
  `carryforward_check.py` is skills(B)'s.
* **Did not re-run `xref_check --provenance`** on decision 14. Round 346's
  probe answers "was this ever defined"; the reserved comment already says
  no, and re-asking would have cost a git walk to confirm a documented
  design choice.
* **Did not tier `depthcensus.py --tests`.** Round 462's item 1 and round
  463's item 5 have now offered it to harness(A) twice and to language(C)
  three times. This round spent its budget on the registry and says so
  rather than carrying it silently — but note that `specreg.py` demonstrates
  the cheap half: a sub-second audit lands in the fast tier for free just by
  having a test file in `tests/`.
* **Did not measure the pristine-checkout asymmetry** (round 463's item 3).
  skills(B)'s.
* **Left `state/research-state.md`'s `SPEC.md:9446` citations alone.** Two
  sites in round 463's entry, two in this round's banked predictions file.
  All four were correct at the commits that wrote them and all four are now
  off by 29 lines, which is round 462's next-step 4 demonstrating itself:
  *a SPEC citation of a file:line is not durable.* `specreg.py`'s own
  docstring was rewritten mid-round to cite the section rather than the
  line, for exactly this reason.

# Round 449 (SWE-loop D) — one definition, one adopter

**2026-09-02. Track D: the harness turned on this program's own code.**
HEAD at start `69f458b`; bank frozen at `3b0fb3f`.

Round 397 extracted `harness/roundheadings.py` — "ONE definition of a round
entry heading" — after a legal, committed round entry was reported as a
missing round twice, 94 rounds apart. Its docstring tabulates **four**
independent parsers and which headings each accepts, and ends: *"the fix for
a format contract that nothing enforces is not a stricter writer — it is a
reader that accepts what a reasonable writer produces."*

Fifty-two rounds later this round counted the readers that actually adopted
it. **One** — `check_round_recorded.py`, which shipped in the same commit.

---

## 0. What this round inherited, and what it landed first

`state/slow-tier-ledger.jsonl` row 46, written 07:26:46Z by the driver's
post-round `slowtier-slice` for round 448 (`driver.log` 07:26:50, *3
conclusive against checkout `da17658b647a0ae2` (9% recall), 0 failing*).
Round 448's last commit landed 07:11:04Z, fifteen minutes earlier, so 448
could not have committed it. Attributed and committed (`3b0fb3f`), not
allowlisted — the seventh consecutive round to inherit one.

Also inherited, and the round's subject: round 448's entry heading had
drifted to `## Round 448 (NUC-integration E) — …`, which put
`test_roundheadings.py::test_the_live_record_is_fully_canonical` RED on the
round-448 health-check line. **That drift is a natural experiment and it
dies the moment the document is fixed**, so it was measured first and
normalised second. Everything in §2 was taken with it still live.

---

## 1. The adopter count

```
$ grep -rn "roundheadings" --include=*.py --exclude-dir=.venv . \
    | grep -v "roundheadings.py" | grep -v "test_" | cut -d: -f1 | sort -u
./skills/session-inheritance-audit/scripts/check_round_recorded.py
```

One file. The other three parsers round 397 catalogued were at HEAD:

| parser | pattern at HEAD | sees round 448? |
|---|---|---|
| `check_round_recorded` | *delegates to `roundheadings`* | **yes** |
| `swe.toolliveness._STATE_HEAD` | `^#{2,3} Round (\d+)\b` | yes (by luck of this drift) |
| `state_claim_check` block-stop | `^#{1,3}\s` | yes (a stop, not a parser) |
| `carryforward_check._HEADING_RE` | `^###\s+Round\s+(\d{1,4})\b` | **no** |

The extraction landed loudly, in a commit narrating the bug. The
non-adoption is a *non-event*: no file changed, no test went red, no
reviewer saw a diff. That asymmetry is the whole reason it survived 52
rounds, and it is the skill this round shipped.

---

## 2. The live divergence, measured before the document was touched

`state/swe/round-449/divergence-before.txt`.

**Round 448's entry was not dropped. It was ABSORBED.**
`carryforward_check.round_sections` slices from each matched heading to the
next MATCHED heading, so an unrecognised heading does not create a hole — it
hands its text to the *previous* section:

```
448 in round_sections: False              max key seen: 447
len(section[447]): 55,636 chars / 810 lines   'Round 448' in section[447]: True
len(section[446]):  8,623 chars / 121 lines   ratio 6.45x
headings inside section[447]: 10
    ### Round 447 — skills(B) — 2026-09-02 …
    ## Round 448 (NUC-integration E) — 2026-09-02, box DOWN …
    ## Next steps (as of round 448) … (as of round 441)      [8 blocks]
```

`round_sections` feeds `Corpus.own_scope(n)`, which is the evidence
`scan()` reads to decide whether round *n* scored its own predictions. So
for the length of the drift, **round 448's prose was round 447's
evidence**.

Across both prose files, rounds visible to the definition and invisible to
the non-adopter: **22** — round 448 plus 21 archived rounds sitting under
four span headings (`### Rounds 114-126 — driver-level, mostly did not
run`), which `Round\s+` cannot match because the word is `Rounds`.

### 2b. A SECOND defect, 67x larger, that nobody had named

`state/swe/round-449/section-boundary-before.txt`. The boundary was "the
next ROUND heading", and `## Next steps (as of round N)` is not one:

```
state/research-state.md:  260 sections, 67 (26%) carry a foreign level-<=3 heading
                          136 foreign headings swallowed; 135 of them next-steps blocks
                          worst: round 388 swallows 22, round 363 swallows 14
state/research-state-archive.md: 62 sections, 8 polluted; 4 swallow another round's SPAN heading
total text attributed to some round: 1,792,270 chars, of which 26.7% belongs to another round
```

Round 388's `own_scope` contains twenty-two other rounds' next-steps prose.

---

## 3. THE FINDING: extent is not impact, and the small defect is the one that moved

The 2x2, on the same tree, diffing the tool's PUBLISHED findings
(`state/swe/round-449/counterfactual-2x2.txt`):

| variant | sections | attributed chars | verdicts changed |
|---|---|---|---|
| today (own regex, round-heading boundary) | 322 | 1,792,270 | — |
| **drift fix only** (roundheadings keys) | **323** | 1,792,270 | **[448]** |
| **boundary fix only** (level boundary) | 322 | **1,303,990** | **[]** |
| both | 323 | 1,313,746 | [448] |

Correcting the boundary moved **488 KB of prose and flipped zero verdicts**.
Correcting the drift moved **no text at all and flipped exactly one** —
round 448's own scoring, which `--suggest` would otherwise have proposed as
`unscored` while its entry sat in round 447's scope saying *"17 HIT / 1 MISS
/ 1 PARTIAL / 2 no-basis-reported of 21"*.

A big number is not a live consequence. Both are in the round file because
either one alone is a misleading report.

### Why nothing ever noticed

`state/swe/round-449/published-diff.txt` — old parser vs new, same tree:

```
findings: old 29  new 29        only-old: []   only-new: []
published tail: old '1 error(s), 28 warning(s)'  new '1 error(s), 28 warning(s)'
```

`scan()` — the only consumer of `own_scope` in `findings()` — runs *only*
for ledger entries recorded `unscored`. There is exactly **one**, round 132,
whose section is empty in both worlds because its entry lives under an
archive span heading. Twenty-seven of the twenty-nine findings are
ledger-shape checks that never touch a section at all.

**A parser can be wrong about the newest round in the record and publish a
character-identical line.** That is the explanation for the 52-round
latency, not a reason the work was unnecessary.

### A latent one, closed as a side effect

`latest = max(list(banks) + list(corpus.sections) + [0])` drives
`age = latest_round - n` for the K004 "owed for N rounds" warning. A round
that both drifts its heading and banks nothing under `state/round-NNN-` used
to take `latest` down by one. Inert today — the only unscored bank is round
132 at age 317 (`state/swe/round-449/latest-round-effect.txt`) — and the
adoption fixes it without a separate change, because 448 is now a section.

---

## 4. The fixes, and the order they were made in

1. `carryforward_check.round_sections` reads `harness.roundheadings` (with
   the promoted-copy `ImportError` fallback `check_round_recorded` already
   documents) and ends a section at **the next heading of level <= its
   own**. Span headings are boundaries but never keys: handing one block to
   thirteen rounds would give each of them an entry it does not have.
2. `toolliveness._round_of_line` reads `harness.roundheadings` and answers a
   span with its FIRST round. The old scan walked past
   `### Rounds 114-126` and attributed all thirteen rounds' lines to round
   **113**. 16 archive lines change attribution; 0 live lines
   (`state/swe/round-449/toolliveness-span-fix.txt`). Latent, because
   `record_files()` reads only the live record — said here rather than
   dressed up as a live fix.
3. **Then** round 448's heading was normalised to
   `### Round 448 — NUC-integration(E) — 2026-09-02 — box DOWN, …`.

The order is the point. Round 303 edited the DOCUMENT to satisfy the REGEX
(commit `b2e5425`) and `roundheadings.py`'s docstring names that as the
wrong fix. Doing it last, after the readers, with the drifted text kept
verbatim as a test fixture, is a different act that looks identical in a
`git log --stat`. The commit message says so.

`261 heading(s), 261 round(s), 0 non-canonical`;
`test_roundheadings.py` 44 passed, RED → GREEN.

---

## 5. The durable half: `harness/tests/test_headingparser_adoption.py`

9 test functions / 30 collected items.

- Every declared parser × a fixture set that includes **round 448's heading
  verbatim**, asserting all of them equal the definition — plus negatives no
  parser may accept (`## Round log`, `## Next steps (as of round 448)`,
  `## Round 3.5`, an indented heading).
- The live record: `round_sections` keys == `heading_rounds` minus spans, and
  no recorded round is without a section.
- **The parser set is DERIVED from the repo's ASTs**, not from the list in
  the file: every module compiling a heading-shaped `Round` pattern must be
  declared or exempt. A hand-written roster of the tools that might have a
  hand-written roster is the same bug one level up (round 392;
  `skills/derived-subject-set`). And because a derived set that finds nothing
  is indistinguishable from a broken scanner,
  `test_the_census_actually_finds_the_parsers_it_is_meant_to_find` asserts
  it is non-empty on both known holders.

Falsified rather than asserted. Planting
`harness/_r449_census_probe.py` with one heading regex reddens the census and
names the file by path. Reverting each fix in place:

| revert | tests reddened | pre-existing reddened |
|---|---|---|
| `toolliveness._round_of_line` | 3 | 0 |
| `carryforward.round_sections` | 3 | 0 |
| `_grandchild_mutant` (§6) | 1 | 0 |

All three files restored byte-identically (`md5sum -c`: OK).

**One honest limit, stated because normalising the document created it.**
After §4 step 3 the live-record assertions can only fail on a FUTURE
regression — round 402's lesson, that a test whose subject is a live defect
passes only while the defect survives. That is why R448 is a fixture.

---

## 6. Round 447's `health-check FAIL` was a race in the test's own evidence

Not a regression in `swe/mutation.py`. `logs/health_round_447.log:70`:

```
E  FileNotFoundError: [Errno 2] .../test_timeout_kills_grandchild_0/grandchild.pid
```

at `pid = int(pidfile.read_text())`. The first two assertions PASSED
(`status == "timeout"`, `"group" in detail`, `wall < 15`). The
**grandchild** was supposed to write its own pid; the driver runs four
suites at once on a box whose `nproc` is 1; its interpreter was not
scheduled inside the 2.0 s cap. The traceback named neither the race nor
the grandchild.

Round 443's technique — *the spike does not need producing, it needs
SIMULATING*. Delay the grandchild 3.0 s against the **unchanged** 2.0 s cap
(`/tmp/r449/repro.py`, ~2 s on an idle box):

```
cap=2.0  OLD (grandchild writes its own pid)   pidfile: False   FAIL
cap=2.0  NEW (parent writes Popen().pid)       pidfile: True    ok
```

`Popen` returns once the child has EXEC'd; everything CPython does after
exec is schedulable work, and `p.pid` costs the grandchild nothing. The
grandchild still inherits stdout and still outlives the cap, so round 101's
subject is untouched.

**The measured limit, banked in the test's own docstring:** at a 0.3 s cap
BOTH shapes fail, because the mutant is killed before pytest imports it. So
the original test now asserts `pidfile.exists()` with *"this run proved
nothing about killing grandchildren"* instead of dying on a
`FileNotFoundError` — a test that cannot reach its subject should say so,
not raise an unrelated exception. 24 passed in 19.95 s (23 before).

*The first repro attempt was WRONG and is recorded as such: shrinking the
cap to 0.3 s on an idle box does not model contention, because it moves the
deadline and not the latency. It also produced a lucky pass on its first
run and a fail on its second — the flake, demonstrated by accident.*

---

## 7. Predictions (D-013) — `state/round-449-predictions.md`

Thirteen lines banked at 07:31Z, frozen in `d6cc5df` before the divergence
measurement, before any parser edit, and before the heading was normalised.
Seven baselines re-derived this session with their commands.

**7 HIT, 2 MISS, 1 SPLIT, 1 PARTIAL, 1 DISCLOSED, 1 no-basis-reported.**

| # | claim | verdict |
|---|---|---|
| P1 | 448 not a key of `round_sections` | HIT |
| P2 | absorbed, not dropped — `"Round 448" in section[447]` | HIT |
| P3 | 447:446 section ratio ~6.7x | **DISCLOSED**, not scored (line numbers were in hand); measured 6.45x by chars, 6.69x by lines |
| P4 | 20–60 rounds invisible to the non-adopter | HIT (22) — **weak**: the band's top was 2.7x too generous |
| P5 | published line unchanged | **PARTIAL** — outcome right, mechanism wrong |
| P6 | 1 of the 4 parsers blind | HIT |
| P7 | the published line CHANGES in >=1 field after the fix | **MISS** |
| P8 | 8–16 new tests, file < 25 s solo | **SPLIT** |
| P9 | reverting each fix reddens exactly its own tests | HIT |
| P10 | 0 non-canonical, 261/261, pin RED→GREEN | HIT |
| P11 | fast-tier solo wall time | **no-basis-reported** |
| P12 | at least one new test needs editing after its first run | **MISS** |
| P13 | 13 scored lines | HIT |

**P5, the instructive PARTIAL.** The line was right and the reason was not.
I wrote that round 448 had banked no predictions, on the evidence that it
had no bank under the `state/round-NNN-predictions.md` convention. It has
none; it banked
`nuc/predictions-e-round448.md`, and the ledger records it `scored`. The
real mechanism is narrower and more interesting: `scan()` is reached only
for `unscored` entries, of which there is one, round 132, whose section is
empty either way. **I checked a filename and called it a check on the
fact.** A bank line whose mechanism is a `ls` deserves the verdict its
mechanism earns, not the one its conclusion does.

**P7, the MISS, in the same family.** I banded `warning(s)` at 26–31 across
the whole tool without asking what *consumes* `round_sections`. 27 of the 29
findings are ledger-shape checks that never touch a section, so the
reachable surface was two findings wide and the honest band was "no change
unless round 132 gains a section". **Band the reachable path, not the
tool's whole output** — the rule this round earned, and it is P5's rule
seen from the other side.

**P8, the SPLIT that wrote step 12 of the banking skill.** 15 test
functions (inside 8–16) and 36 collected items (2.25x over) — one
parametrised module makes the two counters differ by more than the band's
whole width, and nothing in the bank said which one I meant.
`grep -c '^def test_'` and `pytest --collect-only -q | tail -1` are
different numbers about the same work. Both files ran well inside 25 s solo
(3.21 s and 19.95 s).

**P12, the MISS I would rather have won.** No test needed editing after its
first run (30, 5 and 24 passed first time). Two numbers in the new SKILL.md's
Verification block DID need correcting after being run — `expected: 1` where
pytest prints the path twice, and a `grep -v "/.venv/"` that went `STALE
C001` — which is the same discipline failing in a different artefact. Scored
against what was banked, and reported.

**P11, the decline.** Round 448's item 9 forbids a wall-time band that does
not state the contention condition behind it, and every fast-tier figure on
disk (842–905 s) was measured by the driver while three other suites ran on
this 1-core box. No solo measurement exists at any HEAD, so no band was
banked. The number is in §8 and in the round entry.

---

## 8. Suites, on a settled tree

<!-- filled in after the final run; see state/research-state.md's round-449 entry -->

---

## 9. Artifacts

- `harness/tests/test_headingparser_adoption.py` (new, 9 functions / 30 items)
- `skills/skill-authoring/scripts/carryforward_check.py` — `_marks`,
  `round_sections`, the `roundheadings` import with fallback
- `skills/skill-authoring/scripts/test_carryforward_check.py` —
  `TestSectionBoundary` (5 tests)
- `harness/swe/toolliveness.py` — `_round_of_line`
- `harness/tests/test_swe_mutation.py` — `_grandchild_mutant`, `_wait_dead`,
  `test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap`
- `skills/extracted-definition-needs-an-adoption-test/SKILL.md` (new);
  4 cases in `skills/trigger-cases.json` (346 → 350);
  `state/known-unprobed-skills.json` (27 → 28) + `_round_449_note`
- `skills/prediction-banking/SKILL.md` — steps 11 and 12, two checklist lines
- `state/round-449-predictions.md`; `state/swe/round-449/*.txt` (6 artefacts)
- `state/research-state.md` — round 448's heading normalised
- round 448's slow-tier ledger orphan (`3b0fb3f`)

# Round 495 (skills B) — a pointer to a scoring is not a scoring

**Predictions banked at `6955262` BEFORE any repair and before any suite was
re-run** (`state/skills/round-495/PREDICTIONS.md`, D-013). Scored in section 8
of this file, which exists — the whole round is about a round that wrote that
sentence and did not.

---

## 1. The one-sentence finding

`carryforward_check.py` decided whether a prediction bank had been scored by
matching the vocabulary people use when they have scored one, and that
vocabulary is identical to the vocabulary people use to say **where** they
scored one — so round 492's `Scored in §10.`, in a file that ends at `## 9.`,
read as a completed scoring, and `--suggest` proposed a `"status": "scored"`
ledger entry quoting the promise.

## 2. The four red nodes, and what they actually were

All four skills-check reds were reproduced SOLO at `nproc`=1 before anything
was touched — `4 failed in 67.78s` — so none is an artefact of the driver's
four concurrent suites. That discharges the red-debt instruction for the three
marked RECURRENT: they are real.

| node | red since | root cause |
|---|---|---|
| `corpus_check.py::carryforward` | 490 | rounds 490/491/492 banked and never registered |
| `corpus_check.py::selfdesc_check` | 493 | `banks.493.note` names the path round 493 `git mv`d away from |
| `corpus_check.py::xref_check` | 492 | the same round-493 path, plus the operator's `v1_roadmap_mission.txt` |
| `corpus_check.py::unit_tests` | 490 | **not a fourth defect** — its 4 failing nodes are the `TestLiveCorpus` mirrors of the other three |

Four nodes, three root causes. `unit_tests` closes when the others do and was
never worth diagnosing separately; the health log's node list makes it look
like an independent failure and it is not.

## 3. The repair that is an acknowledgement, not a fix

Two of the three root causes are **prose that is correct and must keep
dangling**.

Round 493 committed its bank under a `languages/whence/…` prefix because a
stale `cd` persisted into its `mkdir`, `git mv`d it to the `state/harness/`
location, and wrote down what had happened. That note now names a path that
does not exist — which is the fact the note is reporting. Rewriting it to
resolve would delete the only record of the mistake. Round 493 reached this
conclusion itself and assigned it to skills(B); this round paid it, with a
content-pinned entry in `state/known-selfdesc-drift.json` (the first entry
that file has carried since round 437 emptied it) and an entry keyed
`X004:languages/whence/state/harness/round-493/predictions.md` in
`state/known-dangling-citations.json`.

**One mistake needed two registries**, because `xref_check` does not scan
`.json` and `selfdesc_check` does not scan `.md`. Neither can see the other's
copy of the same sentence. That is not a bug in either; it is worth writing
down because the next person to fix "the" dangling path will fix one of them
and watch the other suite stay red.

**And the acknowledgement recursed.** The first version of the
`known-selfdesc-drift.json` entry spelled the dangling path in its own `why`
field, and `selfdesc_check` immediately raised a fresh J004 against it: *the
registry that exists to record a broken path could not name the path it was
recording.* `xref_check` already solves this for itself with a declared blind
spot over `skills/*/scripts/` — its summary line says so in as many words,
"the checkers themselves quote the rot they detect" — and the acknowledgement
registries have no equivalent. Round 495 chose to name the path by coordinate
(it is quoted inside the pinned field, one hop away) rather than mint a new
blind spot to suppress its own prose.

`knowledge/v1_roadmap_mission.txt` is the third dangling path and **is not a
round's to close.** CLAUDE.md's MASTER MISSION block instructs every round to
check it before starting; the file has never existed in this repo's history;
the block was landed by commit `7aab36a`, whose own message records that it
was "not authored by a round". A round's two options are to author the
operator's roadmap and then cite it as authority, or to edit the operator's
block. It is filed with `owner: operator` — **not** in
`state/known-absent-paths.json`, which is for prose whose naming of an absent
path is *right*; this prose is an instruction that cannot be followed. The
fix is one line for the operator: add the file or drop the sentence.

## 4. The finding: a promise read as a deed

Rounds 490, 491 and 492 all banked predictions and none registered them. The
first two had scored their banks properly — round 490 a fifteen-row table,
round 491 seven rows — and simply never wrote the ledger row. Round 492 had
not.

Its knowledge file says, at line 11:

    (`state/whence/round-492/predictions.md`). Scored in §10.

and then ends at `## 9. Tests and gates`. There is no §10. There is no `HIT`
and no `MISS` anywhere in the file. Rounds 493 and 494 were checked by hand;
neither scored it. Fourteen predictions, P1–P14, unscored.

`carryforward_check.py --suggest` proposed:

    {"492": {"status": "scored", "quote": "(`state/whence/round-492/predictions.md`). Scored in §10."}}

The mechanism is an **asymmetric vocabulary**. `SCORE_PATTERNS` has four
patterns for "this was scored". `NEGATION_RE` has ten alternatives for "this
was NOT scored" — a list somebody clearly grew over time, and the module
comment says why: *"this corpus does that on purpose and often … without this
the scanner reads its own bug reports as evidence the bug was fixed."* There
was nothing for the third case, **"this was scored over there."**

That asymmetry is not an accident and it generalises. Misreading a negation is
loud: the checker screams about an item everyone knows is closed, and someone
fixes it in a round. Misreading a promise is silent: the item is marked done,
stops being reported, and nobody looks again. **The error mode that gets
fixed is the one that makes noise.**

Had any round accepted that proposal, K001 would have gone green while
D-013's second half stayed undone for round 492 — the ledger laundering the
exact debt it was built to expose.

### The fix

`unkept_pointer(line, text)` in `carryforward_check.py`. A scoring-shaped line
that cites a location and carries **no verdict of its own** is evidence only
if the location resolves to a heading in the text it came from.

The verdict-on-the-line guard is load-bearing and had to come first. Round
490's real tally is `**13 HIT / 1 MISS / 2 OPEN-KEPT of 15** (P14 in §10).` —
a genuine scoring that also points at a section. Without the guard the new
rule would throw away a scoring for saying where the rest of it lives, which
is a worse bug than the one being fixed.

Resolution is against the text the candidate came from, which is all
`score_evidence` is given. The bias is deliberate: a heading that resolves by
accident merely restores the pre-495 behaviour of accepting the pointer,
whereas resolving too strictly would discard real evidence. For a debt
tracker the fail-safe direction is to find LESS evidence — the item stays
open and visible.

## 5. The second defect, which the first was hiding

With the pointer rule in, `--suggest` still proposed `scored` for round 492.
The new quote was:

    | P7 | the five census reds are round 492's own artefacts in the corpus | **HIT** … |

That is `knowledge/round-493-…md:230` — **round 493's own §8 table, scoring
round 493's own P7**, offered as proof that round 492's bank had been scored.

In a scoring table the first cell is the subject and the verdict is the
object, and a prediction id belongs to whoever owns the *table* — a fact the
row never states. `cross_round_scope` joins paragraphs from every prose file
and throws the document coordinate away, so by the time the line reaches the
attribution filter there is nothing left that could say which round's table
it came out of. `credited_rounds` does not catch it: round 489 widened that
regex to `round N's <up to 3 qualifiers> P<n>/predictions/bank`, and the noun
here is `artefacts`.

Fixed with `row_subject_is_a_pid`, applied **only** on the cross-round path —
a round's own table row IS its own scoring, and the veto must never reach
`own_scope`. Both directions are pinned.

Corpus-wide, 18 of 171 banks have cross-round-path evidence only, and 6 of
those are table rows: rounds 23, 125, 137, 340, 401 and 492. Every one was
read by hand and every one is the same shape — the row's subject is the table
owner's `P<n>`, with another round named in a description cell. The veto is
right in all six. Its live blast radius is one verdict, because `scan` only
runs for entries recorded `unscored` or absent from the ledger.

**Two independent false positives, one symptom, and the second was invisible
until the first was gone.** This is the same lesson round 489 recorded when
its attribution repair *moved* round 479's wrong evidence rather than making
it right. Re-run the scan after fixing a filter, and read the new evidence.

## 6. What the round's own bank did to the round

The bank quotes both dangling paths, in its already-observed section, because
it had to name what it was about to acknowledge. `xref_check` then reported
two NEW authoritative danglings at `state/skills/round-495/PREDICTIONS.md:27`
and `:29`, and the acknowledgements written moments later swallowed them —
so the two entries read as covering six sites when a round had inspected
four.

The cause is a scope gap the bank had predicted and mis-priced.
`HISTORICAL_RE` knew two prediction-bank shapes; the corpus had grown three
more (`state/<track>/round-NNN/PREDICTIONS.md` and its lowercase spelling,
`state/<track>/predictions-d-roundNNN.md`, and the trackless
`state/round-403/PREDICTIONS.md`). **62 of 171 banks were being held to the
authoritative standard.**

That standard is one D-013 forbids them from meeting. A bank is committed
BEFORE measuring; editing it afterwards so a citation resolves is precisely
the tampering the rule exists to prevent. **An authoritative classification
demanded a repair the program's own rules ban.** Widened; all 171 banks now
classify `historical` or `frozen`, and `state/research-state.md`, `CLAUDE.md`
and `state/nuc-missions.md` were checked to confirm none was swept in.

The prediction said this gap was latent and costing zero findings. It cost two,
in the round that predicted it, on that round's own bank.

## 7. What this round did NOT do

- **Did not probe the new skill.** `pointer-is-not-the-evidence` is registered
  in `state/known-unprobed-skills.json` with an owner. Both case_coverage
  ERRORS are paid — three positive trigger cases (P001) and a Verification
  section whose commands were run in-round (C001); only the priced probe
  (P004) is outstanding. A fourth case was added as a NEGATIVE control
  expecting `matching-is-not-locating`, whose nearest-neighbour difference is
  exactly one fact: whether the cited target exists.
- **Did not fix the two-registry blind spot** described in section 3. It is
  now written down and nothing enforces it.
- **Did not touch the four reds owned by other tracks** —
  `nuc/tests/test_constant_audit.py` (E), `test_swe_mutation.py` and the two
  `test_redattrib.py` nodes (A).
- **Did not score its own bank before measuring.** Section 8 was written after
  the suites ran.

## 8. Predictions scored

**6 HIT / 2 SPLIT / 2 MISS of 11, plus one pre-registered and unscorable
here.** The bank listed eight already-OBSERVED facts separately (O1-O8) and
they are not scored; folding them in would have banked eight certainties.

| # | claim | verdict |
|---|---|---|
| P1 | >=2 of the 3 unentered banks were actually scored | **HIT** — exactly 2. 490 and 491 scored; 492 not |
| P2 | `--suggest` proposes all 3 and finds a usable anchor for >=2 | **HIT, and too weak to be useful.** It proposed 3 and 2 anchors were usable. The prediction had no clause for the third being actively WRONG, which is the round's whole finding |
| P3 | 3 repairs close 4 nodes, no further repair discovered | **MISS** — three more were needed: the table-row false positive (§5), the `HISTORICAL_RE` scope gap (§6), and the acknowledgement that dangled on its own path (§3) |
| P4 | `v1_roadmap_mission.txt` is not closable by a round; goes to `known-dangling-citations.json` owned by the operator | **HIT** — including the choice against `known-absent-paths.json` |
| P5 | no general quote-vs-cite mechanism outside the `skills/*/scripts/` blind spot | **HIT** — and demonstrated live when this round's own acknowledgement raised a J004 for naming the path it was acknowledging |
| P6 | bank shapes outran the scope regex; >=3 banks authoritative; latent, costing 0 findings | **SPLIT** — 62 of 171, far past the floor. "Latent" is a **MISS**: it cost 2 findings in this round, on this round's own bank |
| P7 | xref 3 dangling / 0 NEW; selfdesc 0 error / 1 acknowledged; carryforward 0 errors; ledger 167 -> 170 | **SPLIT** — "0 NEW" HIT, selfdesc HIT, carryforward HIT. "3 dangling" MISS (7 — acknowledged sites still count in the total, and the 2 new entries cover 4 sites). "167 -> 170" MISS: 171, because the prediction forgot this round's own bank |
| P8 | K001 recurs by round 498 without an instrument reaching the banking round | **PRE-REGISTERED** — unscorable inside round 495 by construction |
| P9 | `unit_tests` solo lands in 400-700 s; fast checkers under 60 s | **MISS** — **187.38 s**, 1 144 tests. The band was built from the 805.12 s CONTENDED figure divided by a remembered contention factor, when `corpus_check.py`'s own source carries round 487's direct solo measurement of **183.92 s**. A number that was in the repo, not re-derived. Fast checkers HIT (xref 7.6 s) |
| P10 | an existing skill already states the two-halves-of-an-obligation shape | **HIT** — `obligation-ledger`'s description names "predictions banked then scored" outright, so the new skill is the narrower one |
| P11 | `--suggest` has no unit test | **HIT** — zero occurrences of `suggest` in `test_carryforward_check.py`. It is the mode a round runs to discharge D-013's second half and nothing pinned it. Now pinned in both directions |

**The two misses point the same way.** P3 and P9 were both over-confident
about work already recorded in the tree: P3 assumed one pass would be enough,
P9 quoted a derived number when a measured one was in the source file it was
predicting about. P6's split is the sharpest of the three — the round
predicted a trap was cold and then stepped in it.

## 9. Tests and gates

**Before** (`logs/skills_health_round_494.log`, and reproduced solo at this
round's HEAD before any edit):

    xref_check     ERROR rc1   7 dangling (4 NEW, 3 pre-acknowledged)
    carryforward   ERROR K001  170 bank(s), 3 error(s), 32 warning(s)
    selfdesc_check ERROR J004  1 error(s), 0 acknowledged
    unit_tests     ERROR rc1   4 failed, 1125 passed in 805.12s

**After** — `python3 skills/skill-authoring/scripts/corpus_check.py`, solo,
`nproc`=1, **3 m 54 s**:

    xref_check     ok  8 dangling (0 NEW, 8 pre-acknowledged), 107 historical
    carryforward   warn K004  171 bank(s), 168 scored, 3 unscored, 0 error(s)
    selfdesc_check ok  0 error(s), 0 warning(s), 8 info, 1 acknowledged
    unit_tests     ok  1147 passed, 4 subtests passed in 186.19s
    corpus-check: 10 checker(s), 0 error(s), 7 warning(s)

`unit_tests` grew 1125 -> 1147 (+22: 12 for the pointer rule and the table-row
rule, 6 for the bank-scope widening, 4 pinning `--suggest`, which had none).
`xref_check`'s authoritative total rose 7 -> 8 because acknowledged sites
still count in it; the number that matters is **0 NEW**.

The new tests falsify rather than assert. Each rule is pinned in BOTH
directions — an unresolvable pointer is vetoed and a resolvable one is not; a
line carrying its own verdict is never treated as a pointer; the table-row
veto fires on the cross-round path and is proved NOT to fire on the round's
own scope; and `--suggest` is driven over two synthetic corpora that differ
only by whether the promised section exists.

The widened `HISTORICAL_RE` is checked against the POPULATION, not a sample:
`test_every_bank_the_ledger_checker_finds_is_dated_scope` takes every path
`carryforward_check.find_banks` returns — the repo's own definition of "a
bank", 171 of them — and requires none to be authoritative, with a companion
test asserting `research-state.md`, `CLAUDE.md` and `nuc-missions.md` were NOT
swept in by the widening.

`state_claim_check` coverage went 1/11 items (9%) at round 494 to **1/8
(12%)**: this round's next-steps item 3 carries a literal absence claim
(`selfdesc_check.py` has no `SELF_EXEMPT_RE`) so a later round can falsify
section 3's diagnosis in one command instead of re-reading this file.

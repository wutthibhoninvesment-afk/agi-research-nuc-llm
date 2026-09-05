# Round 514 (NUC-integration E) — the report that was stale in its own commit

**Date:** 2026-09-05 · **Track:** E (NUC integration) · **Box:** DOWN
(`ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` — `Connection timed out` after a
10 s connect timeout; the LAN path is not available from this host). Offline
round, on committed files. Per CLAUDE.md's two-SSH-failures rule the connection
was attempted once, failed on a timeout rather than an auth error, and no
second attempt was made against a box that is not answering ARP.

**Assignment:** the red debt. `nuc/tests/test_survivor_impact.py::TestThisTree::
test_the_committed_report_is_about_the_subject_at_head` had been red for six
rounds — **past one full rotation** — opened by this track at round 508 and
owned by this track.

---

## 1. Reproduced first, as the debt line demands

```
$ .venv/bin/python -m pytest nuc/tests/test_survivor_impact.py -x -q
E  AssertionError: assert '8082749f713e...ef67200173ea1' == '3b3923df3ee7...1f4e644324b8c'
1 failed, 29 passed in 0.22s
```

`state/nuc/round-502/survivor-impact.json` carries
`subject_digest 8082749f...`; `sha256(nuc/perturbation.py)` at HEAD is
`3b3923df...`. The commit that moved it is `81d0e42`, **round 508, this
track**: +243 lines to the subject, and `nuc/survivor_impact.py`'s `BATTERY`
rewritten in the same commit. The report was not regenerated.

That is the whole of the red. It is **not** the whole of the defect.

## 2. The report was stale along three axes, and the red only saw one

| axis | committed report says | HEAD says | caught by a test? |
|---|---|---|---|
| subject digest | `8082749f…` | `3b3923df…` | **yes** — the red |
| the battery it ran | 5 verbs; `battery_gap` excludes `reclaim`/`gap` | `BATTERY` is 7 verbs, `reclaim`/`gap` **in** it | no |
| survivors it audited | `n_survivors_standing: 32` | **5**, at the report's OWN digest | no |

The third row is the finding. `nuc/survivor_impact.survivors()` is last-wins
over `state/swe/perturbation-mutation-ledger.jsonl`. Asked today, at the
digest the report itself names — no re-run, no new measurement, the same
one-line question the report answered — it returns **5**, not 32.

Of round 502's 32:

```
verdict in the committed report      status in the ledger today
  moves_published_number   11    ->  killed 11    survived 0
  reached_but_identical     9    ->  killed  6    survived 3
  unreached_by_battery     12    ->  killed 10    survived 2
```

**All eleven `moves_published_number` mutants — the only class round 502
called a defect, the class `strict_fails` exits 1 on — are dead.**

## 3. It was stale *before it was committed*

The killing rows are ledger indices 102–133 of 134, all carrying
`suite_digest 7ac31f49…` — the suite round 502 itself wrote. Report and
ledger arrived in the **same commit**, `6ee44a7`, whose own message reads:

> twelve new tests in nuc/tests/test_perturbation.py; the ledger goes
> 55 killed / 32 survived -> 82 / 5.

The commit message says 5. The JSON committed beside it says 32. For twelve
rounds the four `TestThisTree` gates over that file all passed, because not
one of them re-read the ledger the report was built from. A gate that reads
only the artefact can only ever check the artefact against itself.

## 4. Why the fix could not be "re-run it"

`load_ledger` in `harness/swe/nodecampaign.py` keys on `(id, subject_digest)`, and its
docstring already states the reason:

> a mutant id is `basename:line:op#i` and `i` is POSITIONAL … so the same id
> on a moved source is a different mutant and must not be skipped.

Correct, and it has a cost nobody had paid: **there was no way to say which
mutant at the new digest is the same mutation as an old one.** The five
standing survivors, remapped:

| ledger id (old) | id at HEAD | line | `#i` |
|---|---|---|---|
| `perturbation.py:1582:cmp#161` | `perturbation.py:1586:cmp#162` | +4 | +1 |
| `perturbation.py:1638:const#969` | `perturbation.py:1642:const#983` | +4 | +14 |
| `perturbation.py:1638:arith#970` | `perturbation.py:1642:arith#984` | +4 | +14 |
| `perturbation.py:1656:const#1508` | `perturbation.py:1660:const#1547` | +4 | +39 |
| `perturbation.py:1657:const#1559` | `perturbation.py:1661:const#1601` | +4 | +42 |

Both components move, and the `#i` drift is not a constant: it is the count
of mutation sites round 508 inserted *ahead of that point*, so it grows down
the file (+1, +14, +39, +42). A remap that only re-based line numbers would
have scored the wrong mutant four times out of five.

## 5. `nuc/mutant_remap.py` — re-identify a mutant by what it does

```
key = (op, description, stripped text of the mutated line, owner qualname)
```
plus an **ordinal** within the key bucket, so two byte-identical mutations of
two byte-identical lines in one function stay apart. The ordinal is only a
correspondence while the bucket is the same size on both sides; when it is
not, the pair is reported `ambiguous` and **no** id is emitted. Guessing there
would carry a `survived` verdict onto a mutation nobody scored — the direction
that manufactures good news.

Run over every one of the 87 mutants the ledger has ever scored, from
`81d0e42^` to HEAD:

```
n_old_mutants 1794   n_new_mutants 1846
by_status {'matched': 6, 'moved': 81}     n_id_changed 81
gone 0   ambiguous 0
```

**81 of 87 ids changed.** Six did not — lines 581-594, where *both* the line
number and the positional index happened to survive. That is not the same as
"above the first insertion point": mutants at line 558, *below* them, are in
the `moved` set with a line delta of **0**, their id changed by the `#i`
component alone. The line deltas across the 87 are `{0, +4, +113}` — round 508
inserted in more than one place — so neither component alone identifies a
mutant and neither can be repaired by re-basing.

Nothing was lost and nothing was ambiguous, and that is a measurement rather
than luck: the fixture that *does* trigger ambiguity needs the same statement
repeated verbatim in the same function
(`test_a_key_bucket_that_changed_size_refuses_rather_than_guessing`).

Artefacts: `state/nuc/round-514/mutant-remap-all87.json`,
`state/nuc/round-514/mutant-remap.json` (survivors only).

## 6. Re-collecting the map, and re-scoring at HEAD

`state/swe/perturbation-cov-by-test.json` held
`file_hashes {nuc/perturbation.py: 8082749f…}`, so
`MapPrioritizer(require_fresh=True)` would have downgraded every mutant to the
full 257-unit suite: 87 × ~48 s ≈ 70 min. Re-collected at HEAD, targeted on
the 44 remapped lines: **118.9 s**, rc 0, 257 units,
`file_hashes → 3b3923df…`. Its `suite_hashes` already matched
(`test_perturbation.py` is `7ac31f49…`, unchanged since round 502), so
`map_is_stale` was and stayed `false`.

The five remapped survivors, scored at the HEAD digest against the same suite
that graded them last time:

```
perturbation.py:1586:cmp#162     survived  subset  49 units   5.67 s
perturbation.py:1642:const#983   survived  subset  43 units   4.79 s
perturbation.py:1642:arith#984   survived  subset  43 units   5.26 s
perturbation.py:1660:const#1547  survived  full   257 units  46.97 s
perturbation.py:1661:const#1601  survived  full   257 units  48.23 s
by_status {'survived': 5}   kill_rate 0.0   master drift events 0
```

Two fell back to the full suite (their subset was empty or poisoned — sound,
just slow). All five still survive: the mutations round 508's edit carried
across are the same mutations, and the same suite still does not kill them.

## 7. The three gates, and how long each would have been red

`nuc/tests/test_survivor_impact.py` now resolves `REPORT` to the NEWEST
`state/nuc/round-*/survivor-impact.json` instead of pinning `round-502`. That
pin was not cosmetic: it made the red **unfixable by a fresh artefact**, since
any report at HEAD lands under a new round number the test would never read.
The gate keeps its teeth — the newest report still has to be about HEAD.

Two new `TestThisTree` gates, both of which **fail at HEAD against round 502's
report** (verified by running them before writing the new one):

```
FAILED ...::test_the_committed_report_is_about_the_subject_at_head
FAILED ...::test_the_committed_report_names_the_battery_THAT_EXISTS_NOW
FAILED ...::test_the_committed_report_agrees_with_the_ledger_it_READ
3 failed, 33 passed
```

| gate | would have been red since | rounds |
|---|---|---|
| `..._is_about_the_subject_at_head` | round 508 (existed; the debt line) | 6 |
| `..._names_the_battery_THAT_EXISTS_NOW` | round 508 — same commit, `BATTERY` 5→7 | 6 |
| `..._agrees_with_the_ledger_it_READ` | **round 502, its own commit** | **12** |

The last one is not a regression anybody introduced. It is a report that was
never true, kept green by four tests that all read the same file.

## 8. What this round did NOT do

* **The other 82 remapped mutants are not re-scored at HEAD.** All 87 were
  remapped and the map is at HEAD, but only the 5 that were standing
  survivors were re-run. A mutant that round 502's suite KILLED at the old
  digest could survive at HEAD — round 508 rewrote 243 lines — and until
  those 82 are scored the new report's survivor set is a lower bound. The
  command is written down in §10; the ledger is resumable and last-wins, so
  it is one slice, not a re-run.
* **The box was not reached**, so no mission in `state/nuc-missions.md` was
  ticked. E1-E5 are all `[x]`; the open NUC items (the E3 A/B, the OLMoE
  on-box NVMe check) both need a restart on a shared box and operator
  sign-off, and neither is attemptable with the box down.
* **The three `harness/tests/test_swe_copyparity_real_subject.py` reds**
  (owner harness(A), opened by language(C)) were not touched. Not this
  track's suite and not this round's assignment.

## 9. The report at HEAD

`state/nuc/round-514/survivor-impact.json`, `--strict` exit 0 (no `STRICT:`
line on stderr), identity control clean.

```
subject_digest  3b3923df…            (== sha256(nuc/perturbation.py) at HEAD)
battery         window_swap wsweep_swap wsweep_commit wsweep_steal
                population_swap reclaim_all gap_commit          (7, not 5)
n_survivors_standing            5
n_survivors_at_another_digest   5
n_lines_executed_by_battery  1319     (round 502: 1105, +214)
by_verdict   {reached_but_identical: 3, unreached_by_battery: 2}
by_reason    {branch_not_taken: 2}
moves_published_number  []            (round 502: 11)
```

Five survivors, and **not one of them moves a published number.** The eleven
that did were killed by round 502's own twelve tests before that round's
commit landed; the report just never said so.

The `n_survivors_at_another_digest: 5` is the same five mutants under their
old identities — the ledger still stands `survived` at `8082749f…` too. The
field is doing its job and it reads oddly: 5 and 5 are the same mutations, not
ten.

**The widened battery executed 214 more lines of the subject and changed no
verdict.** Every one of the five holds exactly what round 502 gave it:

| id at HEAD | round 502 verdict | round 514 verdict |
|---|---|---|
| `…:1586:cmp#162` (`_hypergeom_atleast`) | `reached_but_identical` | `reached_but_identical` |
| `…:1642:const#983` (`power_floor`) | `reached_but_identical` | `reached_but_identical` |
| `…:1642:arith#984` (`power_floor`) | `reached_but_identical` | `reached_but_identical` |
| `…:1660:const#1547` (`power_floor`) | `unreached_by_battery` / `branch_not_taken` | same |
| `…:1661:const#1601` (`power_floor`) | `unreached_by_battery` / `branch_not_taken` | same |

That is a **negative result about round 508's battery fix, measured**:
`reclaim_all` and `gap_commit` reach real code (+214 lines) but none of it is
code a standing survivor sits in, and the two `branch_not_taken` lines — the
empty-`testable` arm of `power_floor`'s f-string — are still not taken on this
record. Round 508's fix was right and it bought nothing *here*.

## 10. Predictions scored — 2 HIT, 7 MISS, and six misses are one error

`state/round-514-predictions.md`, banked before any measurement (D-013).

| | claim | outcome |
|---|---|---|
| P1 | >= 28 of **32** survivors find a HEAD counterpart | **MISS** — there were 5, not 32 |
| P2 | >= 20 of **32** change id | **MISS** as stated; 81 of 87 did |
| P3 | >= 1 content key is ambiguous | **MISS** — 0 of 87 |
| P4 | >= 30 of the matched still `survived` | **MISS** as stated; 5 of 5 did |
| P5 | >= 3 survivors leave `unreached_by_battery` | **MISS** — 0 did |
| P6 | `n_lines_executed_by_battery` > 1105 | **HIT** — 1319 |
| P7 | `moves_published_number` >= 11 | **MISS** — 0 |
| P8 | audit wall clock 13-20 min | **MISS** as stated — 366 s (6.1 min) for 5 |
| P9 | no gate compares the report's battery to `BATTERY` | **HIT** |

**Six of the seven misses (P1, P2, P4, P5, P7, P8) have one cause, and it is
this round's own finding, committed by me one step before I found it.** Every
one of them is denominated in "the 32 standing survivors" — a number I took
from the committed report instead of re-deriving it from the ledger. The bank
quoted the artefact. Fifteen minutes later the round's headline was that the
artefact had been wrong about that number for twelve rounds.

The rule this earns, and it is stronger than "re-derive carried claims":
**a prediction's DENOMINATOR is a carried claim too.** Rounds re-derive the
quantity they are about to measure and take the population it is measured
over from whatever document is nearest. `state/round-514-predictions.md` is
the demonstration; the one-line command that would have caught it is in the
prediction file's own §"the mutant-identity problem" paragraph, unrun:

```sh
python3 -c "import sys; sys.path.insert(0,'.'); from nuc.survivor_impact import survivors;
print(len(survivors('state/swe/perturbation-mutation-ledger.jsonl', subject_digest='<the report digest>')))"
```

The two independent misses are worth keeping apart from those six:

* **P3 (0 ambiguous)** — content keys discriminate better than predicted.
  Triggering ambiguity needs the *same statement repeated verbatim in the same
  function*; the test fixture that does it is contrived on purpose. Over 87
  real mutants across a 243-line edit, zero.
* **P5/P7 (the battery moved nothing)** — §9. A widened instrument that
  executes 19% more of the subject and changes no verdict is a result, not a
  null.

## 11. Commands, for re-derivation

```sh
# reproduce the red (before this round's report existed)
.venv/bin/python -m pytest nuc/tests/test_survivor_impact.py -x -q

# the staleness, in one line, at the report's OWN digest
.venv/bin/python -c "import sys; sys.path.insert(0,'.'); from nuc.survivor_impact import survivors; \
print(len(survivors('state/swe/perturbation-mutation-ledger.jsonl', \
subject_digest='8082749f713ee07f05e1f9187324280156c547673e35fa39017ef67200173ea1')))"   # -> 5

# remap every scored mutant across round 508's edit
.venv/bin/python nuc/mutant_remap.py --quiet --out state/nuc/round-514/mutant-remap-all87.json
.venv/bin/python nuc/mutant_remap.py --survivors --quiet --out state/nuc/round-514/mutant-remap.json

# re-collect the by-test coverage map at HEAD (118.9 s, 257 units)
#   harness.swe.coverage.collect(root, ['nuc/perturbation.py'], by_test=True,
#       interest=state/nuc/round-514/interest-lines.json,
#       pytest_args=('-q','-p','no:cacheprovider','nuc/tests/test_perturbation.py'))

# re-score the remapped survivors at HEAD
.venv/bin/python -m harness.swe.nodecampaign --root . --lines all --budget 400 \
    --only "perturbation.py:1586:cmp#162,perturbation.py:1642:arith#984,perturbation.py:1642:const#983,perturbation.py:1660:const#1547,perturbation.py:1661:const#1601" \
    --out state/nuc/round-514/rescore-survivors.json

# the report at HEAD
.venv/bin/python nuc/survivor_impact.py --strict --quiet \
    --out state/nuc/round-514/survivor-impact.json

# the suites
.venv/bin/python -m pytest nuc/tests/test_survivor_impact.py nuc/tests/test_mutant_remap.py -q
#   -> 52 passed
python3 skills/skill-authoring/scripts/skill_lint.py --house \
    skills/report-gated-against-its-input/SKILL.md
#   -> 1 skill(s), 0 error(s), 0 warning(s)

# the blast radius of this round's working-tree diff (harness/readset.py blast)
.venv/bin/python -m pytest -q nuc/tests/test_survivor_impact.py \
    nuc/tests/test_mutant_remap.py nuc/tests/test_bench.py \
    nuc/tests/test_constant_audit.py nuc/tests/test_fossil_ledger.py \
    nuc/tests/test_prompt_budget.py skills/skill-authoring/scripts/test_*.py
#   -> 744 passed in 141.99s

python3 skills/skill-authoring/scripts/corpus_check.py --precommit
#   -> 9 checker(s); 0 error(s), 7 warning(s)
#      (both errors it found first time round were this round's own:
#       P001 -- the new skill had 0 of the required 3 positive trigger cases;
#       K001 -- the bank had no state/prediction-bank-ledger.json entry.
#       Round 513's next-step 1 asked for non-skills tracks to run this. It
#       caught two real omissions on the first NUC round to try it.)
```

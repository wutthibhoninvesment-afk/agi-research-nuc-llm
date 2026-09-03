# Round 479 (SWE-loop D) — predictions, banked BEFORE any measurement

Banked 2026-09-03 ~19:0xZ at HEAD `0e372f9`, before any artefact named below
was opened and before any suite was run this round.

**Subject.** Round 473 (the previous SWE-loop D round) died at `--max-turns`
with five `(filled in below)` placeholders in its knowledge file, an unscored
bank of 17 predictions, and two `never_red` test nodes nobody has classified.
Rounds 474 (item 5) and 475 (item 6) both re-assigned that debt to SWE-loop(D)
and neither touched it. Round 477's item 7 additionally asks which TIER
`harness/tests/test_swe_mutation.py::test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap`
belongs to before anyone says whether it is green.

## 0.1 What had already been looked at (read-set) — step 15

READ before banking:
- `knowledge/round-473-the-tests-that-could-not-go-red.md` — whole file (306
  lines): §1, §1.1, §2, §3.0-§3.3, §6, and the five placeholder headings.
- `state/swe/round-473/PREDICTIONS.md` — whole file, all 17 rows P1-P17.
- `state/research-state.md` next-steps blocks for rounds 478, 477, 476, 475,
  474, and the round-478 round-log entry.
- `harness/run_tests_fast.sh` and `languages/whence/run_tests_fast.sh` —
  whole files.
- `CLAUDE.md`, `CURRICULUM.md`.
- `ls state/swe/round-473/` and the top-level KEY NAMES of the four campaign
  JSONs (a `sorted(d.keys())` print — **no values**).

NOT READ before banking (every line below about these is a bet on an
unopened artefact — step 15):
- **any value** inside `state/swe/round-473/{whenceslow,redattrib,scoreaudit,tierbudget}.json`.
- the BODY of `harness/tests/test_whenceslow.py`, `harness/tests/test_redattrib.py`,
  `harness/tests/test_swe_mutation.py`.
- the BODY of `harness/whenceslow.py`, `harness/redattrib.py`,
  `harness/swe/falsifiers.py`, `harness/tests/conftest.py`.
- `skills/skill-authoring/scripts/carryforward_check.py`.

Two numbers in the "derived from" column below were quoted out of
`state/research-state.md`'s round-474 item 5 (`redattrib` score `0.525`,
`never_red` = the one aggregate-line node, `sample` 200) and out of round
473's own §3 table (`scoreaudit` 81.3 % / 0-of-18, `tierbudget` 48.4 % /
3-of-21). Those are BASELINES quoted from prose, not measurements taken this
round, and per round 434's item 9 they are re-derived below before use.

## 0.2 Novelty check (step 5)

`grep -rln "filled in below" --include=*.py .` → **no hits**: no Python in
this tree looks for an unfulfilled placeholder promise in a round file.
`carryforward_check`'s K003 scans for a scored-section PHRASE (round 474's
item 10), which is a different predicate — it is satisfied by a heading.

## 0.3 Baselines, re-derived at HEAD (step 1), each with its command

| quantity | value at HEAD | command |
|---|---|---|
| HEAD | `0e372f9` | `git rev-parse --short HEAD` |
| `nproc` | 1 | `nproc` |
| knowledge files | 322 | `ls knowledge/ \| wc -l` |
| round-473 knowledge file length | 306 lines | `wc -l knowledge/round-473-the-tests-that-could-not-go-red.md` |
| `(filled in below)` occurrences in that ONE file | 5 (lines 232, 236, 288, 306 + one at 297 inside prose) | `grep -n "filled in below" knowledge/round-473-*.md` |
| round-473 bank rows | 17 (P1-P17) | `grep -cE '^\| P[0-9]+ \|' state/swe/round-473/PREDICTIONS.md` |
| campaign JSONs on disk | 4, all with identical top-level key sets | `ls state/swe/round-473/*.json` |
| interpreter | `.venv/bin/python3` exists | `ls .venv/bin/python3` |

## 0.4 Contention condition (step 11)

`nproc` is 1. Every wall time reported this round is for a **solo** run —
nothing else started while it runs. Any timing taken next to a concurrent
process is reported separately and NOT compared to a solo one (round 475's
item 9, round 474's item 9).

## 1. Predictions

| # | tag | basis | prediction | derived from |
|---|---|---|---|---|
| P1 | STRUCTURAL | [GUESS — file unopened] | `test_whenceslow.py::test_plan_default_is_smaller_than_slowtiers` is never-red for a reason that is **NOT round 473's bound 1 (scope)**: its subject is `whenceslow.plan`, which is inside the audited module. It is either a genuine vacuity or an equivalent-mutant region. | The node name mentions `plan` and `slowtiers`, both `whenceslow.py` concepts; a scope miss would need an out-of-module subject. |
| P2 | STRUCTURAL | [GUESS — file unopened] | `test_redattrib.TestCorpusGrammar::test_the_aggregate_line_is_not_a_checker_row` is never-red under **bound 4 (operator coverage)**: its only dependence on the subject is a string/format constant, and `mutation.generate` has no STRING operator. | Round 473 §3.2 names exactly this shape as "the bound most likely to be misread as a vacuous test"; the node name is about a printed LINE. |
| P3 | RATE | [MODEL — bank read in full] | Round 473's 17 predictions score **10–14 HIT** of 17 (58–82 %). | Corpus median bank is 73.5 % (`bank_audit` §F, quoted in the skill's Verification block); 17 × 0.735 = 12.5, band ±2. |
| P4 | STRUCTURAL | [MODEL] | **At least one** of round 473's 17 rows cannot be scored from the on-disk artefacts alone and needs either a re-run or an explicit `unscorable` verdict. | P1 and P2 are per-mutant/median WALL TIMES; the JSONs carry a `seconds` key but nothing says it is per-mutant, and P11/P16 are about work round 473 never finished. |
| P5 | RATE | [GUESS — values unopened] | `whenceslow.json`'s `score` lands inside round 473's own P5 band **0.35–0.60**, i.e. **P5 HITs**. | 1007-line module, one test file, 64 nodes — the same shape as `tierbudget` (0.484), which is in-band. |
| P6 | RATE | [GUESS — values unopened] | `whenceslow.json`'s `never_red` list has **1–6** entries (of 64 collected nodes). | Round 474's item 5 names exactly one whenceslow node by name; `scoreaudit` 0/18 and `tierbudget` 3/21 put the rate under 15 %. 64 × 0.15 = 9.6, floored at 6 because the one named node is the only one anyone quoted. |
| P7 | RATE | [MODEL] | Round 473's **P9 MISSES LOW**: the pooled `never_red` share over its three banded units (scoreaudit + tierbudget + whenceslow, 103 nodes) is **below 25 %** — I predict **0–12 %**. | 0/18 + 3/21 is already 3/39 = 7.7 %; P6 above caps whenceslow's contribution at 6/64. Worst case (0+3+6)/103 = 8.7 %. |
| P8 | STRUCTURAL | [GUESS — `conftest.py` and `test_swe_mutation.py` unopened] | `harness/tests/test_swe_mutation.py` is **`swe_slow`-marked and therefore DESELECTED** by `harness/run_tests_fast.sh` (`-m "not swe_slow"`). Round 477's P10 was RIGHT about the tier and WRONG only about the script's path. | `run_tests_fast.sh`'s own header says a `test_swe_*.py` file absent from `harness/tier-budget.json` is slow, fail-closed. |
| P9 | STRUCTURAL | [GUESS] | `test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap`, run **alone and directly** on this box today, **FAILS**. | Round 475's health check recorded it red and rounds 476-478 did not touch it. |
| P10 | STRUCTURAL | [GUESS] | The cause of P9's failure is **timing/environment on a 1-CPU box** (a cap or sleep the box cannot meet under load), not a logic regression in `harness/swe/mutation.py`. | The node's name is a wall-clock claim ("slower than the cap") and `nproc` is 1. |
| P11 | RATE | [GUESS] | A census of unfulfilled placeholder promises across all 322 `knowledge/` files finds **1–4 FILES** carrying at least one, counting the phrase set `filled in below`, `TBD`, `to be filled`, `to be written`, `(unwritten`. | Round 473 is the only one anyone has named in four next-steps blocks; the driver's max-turns deaths (32 in the log) make 1 an implausible floor. |
| P12 | RATE | [GUESS] | Total placeholder OCCURRENCES (not files) in that census: **5–20**. | 5 are in round 473 alone. |
| P13 | RATE | [MODEL — my own plan] | New test functions this round, counted by `grep -cE '^\s*def test_' <new test file(s)>`: **12–28**. | Comparable new-module test files in this tree run 15–25 (round 473's P14 used the same prior and its own result is in the artefacts). |
| P14 | STRUCTURAL (process, AUTHOR) | [base rate — step 6] | At least one test I write this round is wrong on its first run. | Base rate; round 473's P16 was the same bet. |
| P15 | STRUCTURAL (process, SYSTEM) | [GUESS] | The harness fast tier ends this round **GREEN except for nodes this round did not touch** — i.e. at least one red I did not cause is present when I first run it. | Round 473's P17 made this bet six rounds ago; rounds 465/466/467/473/475 all found whole-tree reds a D round had to clear by hand. |
| P16 | no-basis | [NO BASIS — declared] | **How many mutants across round 473's four campaigns are classified `error` — I have no basis.** Round 473's own P12 banded 0–8 for exactly this quantity and I have not opened a single value in any of the four JSONs, so restating a band would be copying its bet, not making one. I commit to reporting the number whatever it is, and to scoring P12 against it. | — |
| P17 | no-basis | [NO BASIS — declared] | **Whether either never-red node, once repaired, is killed by a re-run mutation campaign — I have no basis.** I have not read either test body or either subject module, so I cannot say whether a repair is even possible within bound 4. I commit to reporting the outcome, including "no repair was possible and here is why". | — |

## 2. Amendments

*(none yet — anything added below is timestamped and states it was written
before the relevant measurement)*

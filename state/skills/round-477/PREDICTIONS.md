# Round 477 (skills B) — predictions, banked BEFORE the measurement

Banked at HEAD `7f4fd07` (2026-09-03), before a single character of
`skills/skill-authoring/scripts/corpus_check.py` was edited, before
`test_bank_audit.py` had ever been timed, and before any glob census was run.
Rule D-013: written and committed BEFORE the thing is measured, scored
honestly afterwards.

Three tagging rules from earlier rounds are applied to every line:

* **round 468's** — every line is `STRUCTURAL` or `RATE`, and a line that
  names a structure and then states how many live instances it has is `RATE`.
* **round 445's** — every line carries a BASIS: `[CMD]` a command run this
  round, `[MODEL]` the implementing source was read, `[SENT]` a previous
  round's prose about an artefact not opened, `[NONE]` no basis.
* **round 475's next-step 10, its FIRST exercise** — every line is `SYSTEM`
  (about the tree under study) or `AUTHOR` (about this round's own future
  output). Round 475 measured 6/6 on SYSTEM and 0/3 on AUTHOR from one bank
  and asked for the axis to be tagged so the hit rate can be reported both
  ways. `grep -c "AUTHOR" skills/prediction-banking/SKILL.md` is 0 at HEAD.

**Carried items attacked:**

* **round 475's next-step 2** (skills B) — "`corpus_check.py`'s description of
  its `unit_tests` checker is false and was left that way. It says 'pytest
  over `skills/*/scripts/test_*.py`' near line 175; the argv near line 476 is
  two named directories. … note that making the argv match it is the same
  edit that discharges the W002 debt below."
* **round 475's next-step 3** (skills B) — "Round 471's `test_bank_audit.py`
  (19 tests) is run by nothing scheduled, now declared `unwired` rather than
  falsely `wired`. W005 starts counting from round 475, so it becomes a
  WARNING after a full rotation."
* **round 475's next-step 10** (skills B) — the AUTHOR/SYSTEM axis, exercised
  here and, if it survives scoring, written into
  `skills/prediction-banking/SKILL.md`.

## 0. Baselines, re-derived at HEAD `7f4fd07` with the command beside each

| # | quantity | value | command |
|---|---|---|---|
| B1 | HEAD | **`7f4fd07`** | `git rev-parse --short HEAD` |
| B2 | wiring audit | **129 entry point(s), 109 in closure, 0 error(s), 0 warning(s)** | `python3 harness/wiring_audit.py check` |
| B3 | `bank_audit.py`'s route in | `run_driver.sh:548` -> `harness/run_tests_fast.sh:51` -> `harness/tests/test_wiring_audit.py:595` -> it | `python3 harness/wiring_audit.py closure --why skills/prediction-banking/scripts/bank_audit.py` |
| B4 | registry entries declared `wired` via `corpus_check.py:- [dir]` | **24** | `python3 -c "import json,collections; d=json.load(open('harness/wiring-registry.json')); c=collections.Counter((v.get('via'),v.get('via_kind')) for v in d['entry_points'].values()); print(c[('skills/skill-authoring/scripts/corpus_check.py:-','dir')])"` |
| B5 | the false sentence | `corpus_check.py:175` — `"pytest over skills/*/scripts/test_*.py, whose tests drive the other checkers…"`; argv at 478-483 names TWO directories | `sed -n '173,178p;476,484p' skills/skill-authoring/scripts/corpus_check.py` |
| B6 | what the glob actually matches | **15 files in 3 directories** (`prediction-banking`, `session-inheritance-audit`, `skill-authoring`) | `ls skills/*/scripts/test_*.py` |
| B7 | pytest collection | **986** nodes over the 2 argv dirs; **1005** over 3 (+19) | `python3 -m pytest -q --collect-only <dirs>` |
| B8 | `unit_tests` contended budget, rounds 474/475/476 | **430s (72%) / 453s (76%) / 464s (77%)** of a 600 s timeout | `grep 'skills-check' logs/driver.log \| tail -3` |
| B9 | skills corpus check at round 476 | **10 checker(s), 0 error(s), 8 warning(s)** | same line |
| B10 | W005 arithmetic | `since_round` 475, round 477, `ROTATION` 6 -> `477-475 = 2 < 6`, so it first WARNS at round **481** | `harness/wiring_audit.py:1015-1021` |
| B11 | registry JSON round-trip | `indent=2, ensure_ascii=False` | round-trip probe against the raw bytes |
| B12 | SKILL.md sizes | prediction-banking **403** lines, derived-subject-set **248** | `wc -l` |

## 0.1 What had ALREADY been read when this file was written

Stated so the bank is not read as more blind than it was.

**READ:** `corpus_check.py`'s `RUNNER_CHECKS`, `checks()`, and the round-451
budget clause; `harness/wiring_audit.py`'s module docstring, `audit()`,
`REGISTRY_NAME`, `ROTATION`, and the `weak_only` W003 suppression; the
`bank_audit.py` registry entry including its 1 200-character `reason`;
`skills/derived-subject-set/SKILL.md` in full; `xref_check.py`'s
`PATH_TOKEN_RE`/`PLACEHOLDER_RE` block and `test_xref_check.py::
test_a_glob_makes_the_token_untruncatable_but_unchecked`; `selfdesc_check.py`'s
J001-J010 header; `carryforward_check.py`'s bank-discovery block.

**NOT READ:** the body of `bank_audit.py` (only its subcommand table);
`test_bank_audit.py` (only its test count and one test's name); anything
under `logs/corpus-evidence/`; `skills/prediction-banking/SKILL.md`'s steps.

**ESTABLISHED, not predicted** (cannot be scored as hits): B1-B12 above, and
in particular that W003 does NOT fire on `bank_audit.py` today — that is a
measured 0-error run plus the read `weak_only` branch, not a bet.

## 1. Predictions

| # | class | basis | scope | prediction |
|---|---|---|---|---|
| P1 | STRUCTURAL | [MODEL] | SYSTEM | Adding `skills/prediction-banking/scripts` to `unit_tests`' argv and touching NOTHING else makes `wiring_audit.py check` report **exactly 1 error, W003 on `bank_audit.py`, and 0 warnings** — the new edge is `[dir]` from a non-test file, so `weak_only` is False and the suppression that keeps B2 clean stops applying. The registry flip is therefore mandatory, not optional. |
| P2 | RATE | [MODEL] | SYSTEM | Making the argv *literally* match the sentence — a runtime `glob` over `skills/*/scripts` — makes the static closure blind to it (`wiring_audit.py:52` names "a `glob`" as its own documented under-approximation), so every entry whose only route in is `corpus_check.py:- [dir]` goes W002. Band: **20-24 errors** (B4 is 24). |
| P3 | RATE | [MODEL] | SYSTEM | `test_bank_audit.py`'s 19 tests, solo, under system `python3` 3.12.3: **25-90 s**, dominated by `test_the_corpus_walk_runs_and_reports_a_rate_in_the_measured_band`. Consequence: `unit_tests` under driver contention goes from B8's 464 s to **500-560 s, i.e. 83-93% of its 600 s timeout**, and the round-451 budget clause names it on the driver line. |
| P4 | STRUCTURAL | [MODEL] | AUTHOR | **Disposition fixed BEFORE the measurement** (round 419's rule, so the number cannot choose the fix): whatever P3 turns out to be, this round will (a) add the directory, because round 363's lesson is that an unrun test is the defect and wiring the TOOL without running its TESTS repeats it; (b) make the sentence true; (c) add a test that derives the argv's directory set from the glob so a 4th skill with tests goes RED instead of silent; (d) flip the registry entry to `wired`; and (e) **if the measured cost puts `unit_tests` past 85% of its timeout, raise the timeout in the same commit and publish the new margin** rather than quietly spending it. |
| P5 | STRUCTURAL | [MODEL] | SYSTEM | All 19 of `test_bank_audit.py`'s tests **PASS** in the 3-directory invocation from the repo root. Named risk: they have never been run under that rootdir, and a bank walk that assumes `cwd` would fail there. |
| P6 | STRUCTURAL | [CMD] | SYSTEM | The false sentence is invisible to **all four** prose checkers — X004 truncates the token at `*` and counts it skipped, `selfdesc_check` reads `.json` only, `claim_check` reads SKILL.md Verification blocks, `wiring_audit` folds no glob — so correcting it changes **no checker's finding count**: `corpus_check.py --precommit` reports the same 0 errors / 8 warnings after as before. |
| P7 | RATE | [NONE] | SYSTEM | **No basis, will report rather than bet.** A loose census of glob-shaped path tokens returned 11 589 candidate lines, which is X004's first draft's history (340 findings, every one inspected a truncation artifact) arriving again. Under X004's anchoring + terminator discipline, the count of glob-containing prose path tokens in this tree that expand to **zero** paths is unknown to me; I will run it and report the number, and I am NOT predicting a band. |
| P8 | RATE | [MODEL] | AUTHOR | Test functions this round adds: **10-20**. |
| P9 | STRUCTURAL | [MODEL] | AUTHOR | This round **UPGRADES `skills/derived-subject-set/SKILL.md`** rather than authoring a new skill: round 434's item 9 makes a new skill owe three positive trigger cases and a runnable Verification block, and this finding's home is beside that skill's own step 3 ("derive the subject set from the artefact"), which this case **bounds** — when a static analyser is a second reader of your literal, deriving the subject set breaks the analyser and you must derive the ORACLE instead. |
| P10 | STRUCTURAL | [MODEL] | SYSTEM | `./run_tests_fast.sh` ends the round **green**, and round 476's next-step 5 red node (`test_swe_mutation.py::test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap`) is **not in the fast tier** — that is how round 476 published 2635 passed while the node was red. Node count: **2650-2700 passed**. |
| P11 | STRUCTURAL | [MODEL] | AUTHOR | At least one of this round's own edits is caught by a checker in this tree before it commits. Base rate: round 476 recorded three self-inflicted checker errors, round 474 one. |
| P12 | STRUCTURAL | [NONE] | SYSTEM | **No basis, will report.** Whether `python3 skills/prediction-banking/scripts/bank_audit.py corpus` exits 0 on this tree today. Its body has not been opened. Declining to bet, per prediction-banking step 9 and round 436's next-step 7. |

## 2. What would falsify the round's premise

If the sentence at `corpus_check.py:175` turns out to be true of some
invocation this round has not found — a second `unit_tests`-like argv, or a
`conftest.py` that widens collection — then round 475's item 2 is wrong and
the registry's `unwired` flip was the mistake. The check is B6 against B7:
986 collected nodes over two directories versus 15 files in three.

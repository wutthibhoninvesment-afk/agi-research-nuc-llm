# Round 475 (harness A) — predictions, banked BEFORE measuring

Subject: `state/known-escalated-diffs.json`'s single entry is reported DEAD
by `check_round_recorded.py`. The checker's message names three possible
fates ("committed, reverted, or the file deleted") and resolves none of
them, and its prescribed remedy — *delete the entry* — is the same action
whichever fate obtained.

Banked at HEAD `43efa2c`, before a line of `harness/escalationguard.py`
existed.

## SS0 — read-set (what was ALREADY read when this bank was written)

Stating this because two things below are ESTABLISHED, not predicted, and
must not be scored as hits.

READ before banking:
- `git show --stat 1cbab86` and `git show 1cbab86 -- languages/whence/SECURITY.md`
- `git show --stat e9ef922` (round 393's restore) and its full message
- `git log --oneline -- languages/whence/SECURITY.md` (4 commits)
- `state/known-escalated-diffs.json` in full
- `check_round_recorded.py` lines 660-860 (`load_escalated_diffs`,
  `classify_escalated_diffs`, the blob-hash helpers) and its reporting
  block at 1030-1075
- `harness/pristine_check.py` grep hits for `escalation` only — NOT the body
- `harness/run_tests_fast.sh` header only
- `.git/hooks/` (samples only) and `git config core.hooksPath` (unset)

NOT read before banking: `harness/escalationguard.py` (does not exist);
`harness/pristine_check.py:620-680`; any test file; `run_driver.sh`'s body
outside its `git commit` grep hits.

ESTABLISHED, NOT PREDICTED (do not score):
- E1. The fate of the dead entry is COMMITTED, and the commit is `1cbab86`
  ("round 474: record the harness tier as UNMEASURED…"), whose message does
  not mention the file.
- E2. The same thing happened once before: round 393's `git add -A` swept it
  in at `49969fb`, and round 393 restored it in a follow-up `e9ef922`.
- E3. `.git/hooks/` contains only `*.sample`; `core.hooksPath` is unset; no
  hook of any kind runs in this repo.

## Baselines, re-derived at HEAD `43efa2c` with the command beside each

| # | Baseline | Command | Value at HEAD |
|---|---|---|---|
| B1 | escalation registry entries | `python3 -c "import json;print(len(json.load(open('state/known-escalated-diffs.json'))['escalations']))"` | `1` |
| B2 | checker's verdict on the entry | `python3 skills/session-inheritance-audit/scripts/check_round_recorded.py` | `1 escalation registry entr(ies) … match nothing in the working tree`, rc `0` |
| B3 | working-tree blob of the path | `git hash-object languages/whence/SECURITY.md` | `61248e50a3f58622529d7669cba35fcc3314f0d9` |
| B4 | HEAD blob of the path | `git rev-parse HEAD:languages/whence/SECURITY.md` | `61248e50a3f58622529d7669cba35fcc3314f0d9` (EQUAL to B3 — that is the whole bug) |
| B5 | registry's pinned pair | `python3 -c "import json;e=json.load(open('state/known-escalated-diffs.json'))['escalations']['languages/whence/SECURITY.md'];print(e['worktree_blob'],e['head_blob'])"` | `61248e50… 929c52c4…` |
| B6 | commits touching the path | `git log --oneline -- languages/whence/SECURITY.md \| wc -l` | `4` |
| B7 | harness fast tier, last reported | `grep -n "1451 passed" knowledge/round-471-the-scores-nobody-added-up.md` | round 471: `1451 passed / 361 deselected in 295.91 s` — round 474 ran it and captured NO number (`tail -6` returned the wrong block) |
| B8 | harness test files | `ls harness/tests/test_*.py \| wc -l` | `86` |
| B9 | `nproc` | `nproc` | `1` — every timing below is a SOLO timing or it is void |

## Predictions

Class tags: **[C]** computed-by-me (narrow band, arithmetic is the check);
**[M]** machine-state (both branches stated).
Scope tags: **STRUCTURAL** (a claim about a shape) / **RATE** (a claim about
a count or a proportion).

| # | Class | Scope | Prediction | Band |
|---|---|---|---|---|
| P1 | [C] | STRUCTURAL | Searching the path's history for the PINNED worktree blob `61248e50…` finds it as the committed blob of exactly TWO commits — `49969fb` (round 393) and `1cbab86` (round 474). The base blob `929c52c4…` is the committed blob of the other two (`ee30654`, `e9ef922`). | exactly 2 and exactly 2, no third value |
| P2 | [C] | RATE | The escalated content has therefore been committed by 2 DISTINCT rounds, 81 rounds apart (393 → 474), out of the 127 rounds the escalation has been open (349…475 inclusive). | 2 rounds; 81 apart; 127 open |
| P3 | [C] | STRUCTURAL | Exactly ONE non-test module in this tree reads `worktree_blob` today (`check_round_recorded.py`); `pristine_check.py` consumes it only through `crr.classify_escalated_diffs`. So the pin has exactly one producer and no commit-time consumer. | 1 non-test module; 3 other files (2 harness tests + 1 skills test) |
| P4 | [M] | RATE | Round 393's violation was VISIBLE in the record: the string `match nothing in the working tree` appears in at least one round log under `logs/`. Warm branch (logs retained back to round 393): 1–4 log files. Cold branch (log rotation dropped them): 0 files, in which case the visibility claim is untestable and I say so rather than scoring a hit. | 1–4 files, or 0-with-explanation |
| P5 | [C] | STRUCTURAL | A `pre-commit` hook that refuses a commit staging an escalated path is ~40 lines of shell delegating to the module, and blocks with exit 1 while an ordinary commit is untouched (exit 0). Both branches will be exercised by a test against a REAL throwaway git repo, not a mock. | hook rc 1 on the staged path, rc 0 otherwise |
| P6 | [C] | RATE | Restoring the path to its escalated base (`929c52c4…` committed, `61248e50…` back in the working tree) flips the checker's line from RESOLVED to ACKNOWLEDGED, and the carried-rounds count it prints is `475 - 349 + 1 = 127`. | exactly `carried 127 round(s)` |
| P7 | [C] | RATE | Before the restore, `harness.pristine_check.escalation_allowed_dirty` returns an EMPTY set (the path is not dirty, so nothing is waived); after the restore it returns exactly `{languages/whence/SECURITY.md}`. The waiver has been silently absent since `1cbab86` landed. | `0` → `1` |
| P8 | [M] | RATE | Harness fast tier, run SOLO at the end of this round: it is GREEN (0 failed). `test_swe_falsifiers.py` (round 473, new) is not in `tier-budget.json`, so the fail-closed rule tiers it slow and the DESELECTED count rises above 361. Warm/solo: 280–340 s. Contended (anything else on this 1-CPU box): void, re-take it. | passed 1451–1500; deselected 375–420; failed 0; 280–340 s solo |
| P9 | [C] | RATE | New tests in `harness/tests/test_escalationguard.py`: 18–30, and EVERY one of them goes red against the pre-round tree — but only trivially (ImportError), because the module is new. I therefore predict the stronger falsifier check will be run per-behaviour with targeted mutants instead, and that at least ONE test will NOT be killed by its intended mutant on the first attempt. | 18–30 tests; ≥1 first-attempt survivor |
| P10 | [C] | STRUCTURAL | Deleting the dead entry — the remedy the checker prints — would erase the ONLY machine-readable record that `languages/whence/SECURITY.md` was ever adjudicated, since `state/known-standing-dirty-paths.json` does not list it and no test asserts its name. Grep will confirm no other state file names the path. | 0 other `state/*.json` files name the path |
| P11 | [C] | RATE | `harness/tests/test_*.py` count goes 86 → 87. Total harness fast-tier passed count rises by exactly the number of tests in the new file that are not `swe_slow`-marked (all of them). | 87 files |

## What would falsify the round's thesis

The thesis is: *the escalation pin is a detector with no commit-time
consumer, and its prescribed remedy destroys the evidence it detected.*

It is FALSIFIED if any of these is true and I will say so:
- some existing hook, CI step, or `run_driver.sh` line already refuses to
  commit a registry path (then the guard is redundant);
- the registry entry is reachable from a test that would go red on its
  deletion (then "delete the entry" is not evidence-destroying);
- `1cbab86`'s blob for the path is NOT the pinned worktree blob (then round
  474 committed something else and E1 is wrong).

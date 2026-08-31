# Round 403 (harness A) — predictions banked COLD, before measuring

Written 2026-08-31 ~15:57 UTC, after reading round 402's logs but BEFORE
re-running anything. Scored honestly in the knowledge file (D-013).

## About the failure already visible in `/tmp/whence_full_402_after.log`

P1. The `F` at collection index 617 is
    `tests/test_self_hosting.py::test_guest_parser_parses_its_own_full_source`.
    (Derived from a char count + `--collect-only` index; counts as a MISS if
    reproducing it names a different test.)
P2. Re-running that ONE test alone against the current live tree (HEAD
    58baf/58bd8f + only SECURITY.md and round_counter dirty) will FAIL.
P3. If P2 fails, the cause is round 402's own v0.37 guest change (the
    `bound` list of `@{n, ln}` records in `self_host.lang`/`self_eval.lang`),
    not a moving-tree artefact.

## About the pristine-worktree recipe (round 402 next-steps item 4)

P4. `git worktree add --detach /tmp/wt-403 HEAD` + `pytest -c pytest.ini
    tests/` in that worktree will NOT collect cleanly: it will abort with
    collection errors, as `/tmp/whence_full_402_pristine.log` already shows
    at 15:12.
P5. The count of collection errors will be exactly 3
    (`test_field_corpus_selector.py`, `test_v33.py`, `test_v34.py`).
P6. Every one of those 3 is a module-level read of a path git does not
    track (the round-355 class), NOT a bug in the test's logic.
P7. Therefore round 402's item 4 ("the fix is one command") is FALSE as
    written, and the correct recipe needs a second ingredient.

## About the completed run nobody read

P8. `/tmp/whence_full_402_baseline2.log`'s `112 failed / 1752 passed /
    6 skipped / 56 errors in 1676.12s` is a run of the LIVE tree that
    started 15:13 and finished 15:41, i.e. it overlapped round 402's edits
    for ~24 of its 28 minutes.
P9. A majority (>56) of those 112 failures will NOT reproduce on a static
    tree — they are the moving-tree artefact round 402 predicted.
P10. At least ONE will reproduce, and it will be the same test as P1.

## About the full tier run this round

P11. A full-tier run on a STATIC tree will complete in 1500-2000 s
     wall-clock on this box once the two orphan processes are gone.
P12. Its failure count will be strictly less than 10.
P13. The two orphaned pytest processes (2166178, 2161852) are reparented
     survivors of a kill round 402 believed succeeded; nothing in the repo
     records either PID or either log path.

## About the artefact

P14. `grep -rn` across the whole repo for `whence_full_402` /
     `harness_402` will find ZERO hits — the two log paths are recorded
     nowhere in tracked content.

# Verification log — pristine-checkout-differential

Every claim in `SKILL.md` that begins "round NNN measured" has its run
recorded here, oldest first. Split out of `SKILL.md` by round 427 when the
body crossed skill-lint's B002 threshold (400 lines): the STEPS are what a
reader needs at 3am, the transcripts are what a reader needs when they doubt
one. Nothing was edited in the move.

## Contents

- [Round 355 — the differential's first finding](#round-355)
- [Round 409 — the ungated baseline mode](#round-409)
- [Round 427 — the skip differential](#round-427)

<a id="round-355"></a>
## Round 355 — the differential's first finding

Round 355 (harness A), on this workspace, `harness/pristine_check.py`:

```
$ python3 harness/pristine_check.py check \
      --suite harness-fast --suite whence-fast \
      --allow-dirty languages/whence/SECURITY.md
ref HEAD   verdict git_incomplete
  18 untracked path(s) exist here and in no fresh clone
  allowed-dirty (rule 1 waived by hand): languages/whence/SECURITY.md
  harness-fast   clean            live={'passed': 476, ...} pristine={'passed': 476, ...}
  whence-fast    git_incomplete   live={'passed': 1192, ...} pristine={'failed': 1, 'passed': 1191, ...}
      GIT-INCOMPLETE  tests/test_lexer_guest_parity.py::test_small_example_files_lex_identically
```

Step 1's blocking rule, observed rather than asserted — one tracked file
was dirty and the check refused to run until it was named:

```
$ python3 harness/pristine_check.py dirt
tracked-modified 2 (blocking 1)  untracked 18  ignored 456
  BLOCKING  languages/whence/SECURITY.md
```

Step 10, the pin reverted on purpose:

```
$ <put the glob back>; python3 -m pytest -c pytest.ini tests/test_lexer_guest_parity.py -q
FAILED tests/test_lexer_guest_parity.py::test_the_corpus_is_what_git_tracks_and_not_what_the_directory_holds
1 failed, 81 passed in 45.76s
```

Step 8's re-derived floors, measured on the curated corpus (2026-08-30):
12 small files / 3972 tokens, 16 files total / 35188 tokens, 0 divergences.
The floors they replaced were 20 and 26, both unreachable by a clone.

The checker's own rules are mutation-checked, not assumed — dropping the
step-1 short-circuit, forcing "the run completed", dropping `--force` from
worktree removal, and disabling the pristine-only comparison each kill 1-2
of the 49 tests in `harness/tests/test_pristine_check.py`. 4/4 caught.
<a id="round-409"></a>
## Round 409 — the ungated baseline mode

Round 409 (harness A), the ungated second mode, first run, at `d71d7cd`
with seven tracked files dirty — a tree in which `check` refuses to run at
all:

```
$ python3 harness/pristine_check.py baseline --ref HEAD
baseline  HEAD (d71d7cd36c81)  verdict=red
  NOTE: taken while the live tree had 7 tracked-modified and 0 untracked
        path(s) — the baseline is of the COMMIT, not of that tree.
  harness-fast   green      269 deselected, 961 passed (98s)
  whence-fast    red        81 deselected, 4 failed, 1933 passed, 10 skipped (89s)
      FAILED tests/test_field_corpus_selector.py::test_ten_of_the_fourteen_still_fail_to_parse
      FAILED tests/test_field_corpus_selector.py::test_the_census_and_the_directory_still_agree
      FAILED tests/test_field_corpus_selector.py::test_the_live_tree_has_no_drift
      FAILED tests/test_v24.py::test_the_tracked_example_set_is_the_one_this_repo_decided_on
```

Those four are the ignored-corpus pitfall above, reproduced exactly: green
in the live tree, red at the same commit in any checkout. Note also what
this run does NOT show — `harness-fast` is green here while the same tier
was red in a hand-made `/tmp/wt-408`, because this command's own worktree
path (`/tmp/pristine-check-<pid>-<ts>`) cannot prefix-match, which is the
substring pitfall from the other side: **the instrument was structurally
incapable of finding the bug in its own test double.**

<a id="round-427"></a>
## Round 427 — the skip differential

ROUND_427_PLACEHOLDER_TRANSCRIPT

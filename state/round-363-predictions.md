# Round 363 (skills B) — predictions, written BEFORE any measurement

Banking rule D-013. Written after: reading `state/research-state.md`,
`CURRICULUM.md`, round 357's knowledge file, `run_driver.sh`'s health-check
block, both `run_tests_fast.sh` scripts, and running the two skill-corpus
checkers ONCE on the current tree (that run is the DISCOVERY that started
this round, not a prediction-bearing measurement).

## What is already known (discovery, not predicted)

- `skill_lint.py skills/ --house --strict` at HEAD: **1 error**,
  `H001 measured-not-declared-dependencies: no trigger section`.
- `case_coverage.py` at HEAD: **1 error**, `P001
  measured-not-declared-dependencies: 0 positive cases, floor is 3`.
- That skill was shipped by round 361 (harness A), commit `83ba9a1`.
- `run_driver.sh` runs exactly TWO per-round health checks —
  `harness/run_tests_fast.sh` (round 241) and
  `languages/whence/run_tests_fast.sh` (round 247). Neither reads `skills/`.
- 59 of this repo's 236 commits touch `skills/`.

## The question

Round 357's thesis was "the difference between a rule that is written down
and a rule that runs". It fixed the *probe* half. The corpus now ships five
checkers and a live-corpus test — and **nothing in the driver runs any of
them**, so a violation is only ever found by the next skills(B) round, one
round in six. Round 361 shipped a corpus its own linter rejects with an
ERROR, and two rounds passed without anyone learning that.

So: **how often, and for how long, has this repo's skill corpus been RED
under the rules it itself shipped at that moment?** Replay every commit
that touched `skills/`, running that commit's OWN checkers against that
commit's OWN corpus.

## Predictions

| # | prediction |
|---|---|
| P1 | Of the 59 commits touching `skills/`, the number that are RED under their own checkers is between **4 and 15**. |
| P2 | The count of distinct RED EPISODES (maximal runs of consecutive red commits in `skills/`-commit order) is **<= 8**. |
| P3 | The MEDIAN episode length is **1 commit**; at least one episode is **>= 3 commits** long. |
| P4 | At least one past episode was closed by a later commit whose message does **not** mention the rule it fixed — i.e. it was fixed as a side effect and no round ever recorded the redness. |
| P5 | The number of distinct rule IDs appearing across all red episodes is **<= 6**, and `H001` is among them. |
| P6 | The current (round 361) episode is **the longest-lived in wall-clock rounds** among episodes whose length is measurable, OR ties — because it is the first one to survive a full non-B stretch of the rotation. |
| P7 | At >= 5 of the 59 commits, that commit's own `skill_lint.py` **cannot be run as invoked today** (flag/positional-arg signature drift). These are recorded as `checker-unrunnable`, not as green. |
| P8 | Re-running TODAY's checkers over every historical corpus makes **>= 25 of 59** commits red — far more than P1 — because `case_coverage.py`'s 3-positive-case floor (round 357) did not exist for most of history. This is rule tightening, not rot, and is reported separately. |
| P9 | `xref_check.py`, `claim_check.py` and `state_claim_check.py` are all **green at HEAD** (only the two run so far are red). |
| P10 | A `skills/run_checks_fast.sh` running all five checkers over the live corpus completes in **< 30 s** on this box — cheap enough to be a third per-round health check. |
| P11 | Fixing the two live errors requires **no change to any checker** — the skill is wrong, not the rules. |
| P12 | In the live trigger probe of the 4 skills owed one (`bounded-not-binary-witness`, `measured-exemption`, `measured-not-declared-dependencies`, `refusal-set-differential`), **at least one skill scores below 100% first-draw recall** — round 357 measured 90% exact over 105 cases and 8 no-fires. |
| P13 | `measured-not-declared-dependencies`, whose cases are written by THIS round (a different round from the one that wrote the description — the independence round 357 item 3 asked for), scores **lower** first-draw recall than the three skills whose cases were written by their own description's author. |
| P14 | The probe batch costs **< $2.00**. |

## Scoring

Scored honestly in `knowledge/round-363-*.md`, misses included.

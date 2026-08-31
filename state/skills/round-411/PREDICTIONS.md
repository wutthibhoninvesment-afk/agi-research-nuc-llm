# Round 411 (skills B) — predictions, written BEFORE measuring

Banking rule D-013. Two deliverables:

* **A** — inherited work. Round 410 (language C) died interrupted with its
  whole diff uncommitted, its knowledge file's §8 Verification an empty
  placeholder, no `research-state.md` entry, and its prediction bank
  unregistered in `state/prediction-bank-ledger.json`. Verify it, score its
  bank from committed artifacts, land it.
* **B** — this round's own track work. `skills/run_checks_fast.sh` is RED at
  arrival. One of the three errors is a FALSE POSITIVE in `claim_check.py`:
  the `cd` fast path in `check_paths()` resolves its target directly and so
  bypasses every one of the four suppression rules the same file documents
  eleven lines above the function that implements them.

## §0 — already measured before this file was written (NOT foresight)

Nothing below §0 may be scored as a prediction if it appears here.

1. `./skills/run_checks_fast.sh` reports `7 checker(s), 3 error(s), 6
   warning(s)`: `claim_check ERROR C001` (1 stale claim),
   `carryforward ERROR K001`, `unit_tests` 3 failed / 744 passed.
2. The three failing unit tests are the three LIVE-CORPUS tests:
   `test_carryforward_check.py::TestLiveCorpus::test_the_live_ledger_accounts_for_every_bank_on_disk`,
   `test_claim_check.py::TestLiveCorpusClaims::test_no_stale_paths_in_the_real_corpus`,
   `test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean`.
   They are consequences of the other two errors, not independent defects.
3. The stale claim is `skills/skip-reason-is-a-claim/SKILL.md:192`:
   ``STALE C001 `cd /tmp/<scratch-worktree>` — no such directory``.
   That skill is round 410's, added in the same uncommitted diff.
4. `check_paths()` matches `^\s*cd\s+(\S+)` FIRST and calls `resolve_token`
   on the target, `continue`-ing before the `UNCHECKED_CATEGORIES`,
   `is_anchored()` and `path_tokens()` gates that every other token passes.
   `path_tokens()` is where `TOKEN_PLACEHOLDER_RE` and `SCRATCH_PREFIXES`
   live.
5. Fed a synthetic Verification fence, `check_paths` emits C001 for all of
   `cd languages/<lang>`, `cd /tmp/<scratch-worktree>` and `cd /tmp/wt-411`,
   while `git worktree add --detach /tmp/<scratch-worktree> HEAD` in the
   same fence is correctly silent.
6. The corpus contains 12 `^\s*cd ` lines across `skills/*/SKILL.md`.
   `cd languages/<lang>` (`tiny-language-implementation:121`) escapes today
   only because it sits under `## Exact commands`, which `claim_check` does
   not read.
7. `claim_check.py` documents the four suppression rules in prose
   (`1. SCRATCH`, `2. PLACEHOLDER`, `3. mutating/network`, `4. UNANCHORED`)
   and records that its first draft "fired 31 times: 2 true, 29 false".
8. Whence fast tier at arrival, with round 410's uncommitted diff in place:
   **1977 passed, 3 skipped, 81 deselected** in 302.12s, exit 0.

## §1 — outcome predictions, deliverable B (the fix)

* **B1.** Routing the `cd` target through the same suppression rules takes
  the live corpus from 1 stale claim to **0**, and no other `claim_check`
  finding appears or disappears. Summary line's `135 path(s) resolved`
  is UNCHANGED (the stale one was never in the resolved count).
* **B2.** The count of `unresolvable-by-design` rises from 29 by exactly
  **1**, to 30.
* **B3.** `test_claim_check.py` already owns at least one test that asserts
  the `cd` branch DOES flag a missing directory. My fix will not break it,
  because such a fixture would use an ordinary relative name
  (`cd nope`/`cd missing`), not a placeholder or a `/tmp/` path. Predict
  **0** existing tests in `test_claim_check.py` go red from the fix.
* **B4.** With all three errors closed, `corpus_check` reports
  **0 error(s)** and the warning count stays at **6** (P004/P006/P007/P009
  from case_coverage, S005 from state_claim_check, and the carryforward
  K004 family). Warnings are debts, not defects; the fix touches none.
* **B5.** After registering round 410's bank, `carryforward_check` reports
  **89 bank(s)** (88 + 1) and **0 error(s)**; the K004 warning count rises
  by at most 1 and only if I mark the row partially discharged.

## §2 — outcome predictions, deliverable B (the sweep)

The interesting question is whether this is one bug or a CLASS. I will
sweep all seven corpus checkers for the same shape: *a branch that
validates a token without passing it through that module's own
"should this be checked at all" gate.*

* **B6.** At least **one more** site exists in the seven checkers with the
  same shape. Predict the total number of confirmed sites (including the
  `cd` one) lands in **2–4**.
* **B7.** `state_claim_check.py` (41 KB, the largest, and it re-derives
  claims against a different document) is the single most likely second
  site. Predict it contains one.
* **B8.** `skill_lint.py` does NOT contain one: it is a pure per-file
  linter with no resolve-then-exempt structure to split.
* **B9.** Every confirmed site will be a branch that was added AFTER the
  gate it bypasses, not before. I.e. in `git log` the special case is the
  younger code. This is the mechanism claim; see M2.

## §3 — outcome predictions, deliverable A (scoring round 410's bank)

Round 410 banked 20 items (A1–A5, B1–B7, M1–M3, plus §0's seven
non-foresight facts which are not scorable).

* **A1.** Round 410's bank scores **≥ 15 HIT of 20**. Its §0 discipline was
  good and its predictions are mostly about its own diff.
* **A2.** Its **B6** (the `KNOWN_DIVERGENT`-empty-loop-goes-vacuous
  prediction) is a HIT: the round file's §7 table records
  `KNOWN_DIVERGENT = []` AND a `CLOSED_DIVERGENCE_HOME`, which is what
  changing the test rather than only the list looks like.
* **A3.** At least one of its predictions is scored **MISS by its own
  §9**, which lists three self-caught errors (the three-state design, the
  two self-satisfying string pins, `fieldfield_census_names`). Predict the
  three-state design failure contradicts no banked item — i.e. its bank did
  not predict its own biggest in-round discovery. That is the informative
  row.
* **A4.** Round 410's diff is GREEN as it stands: the whence fast tier I
  ran at arrival (§0 item 8) is its verification, and 1977 > 1947 (round
  409's figure) by **30**, which should be within a few of the 18 new
  `test_v40.py` tests plus the 6 new `test_field_corpus_selector.py` tests
  plus the 3 new parity rows = 27. Predict the true delta is 27–33 and
  that I can account for every unit of it from its §7 table.

## §4 — mechanism predictions (the falsifiable ones)

* **M1.** The `cd` fast path is not a shortcut for performance; it exists
  because `cd` has a *side effect* on the checker's state (it sets `cwd`
  for every later command in the block). Whoever wrote it was thinking
  about the assignment, not about the check, and the check came along for
  free. Predict the branch's own comment talks about the working directory
  and says nothing about validation.
* **M2.** The suppression rules were written for `path_tokens`, the
  ARGUMENT path — and the `cd` branch predates or postdates them without
  ever being reconciled, because the corpus contained no placeholder `cd`
  until round 410. A latent false positive is invisible until someone
  writes the input that provokes it, so age of the bug ≫ age of its first
  symptom. Predict the `cd` branch is ≥ 20 rounds older than its first
  symptom.
* **M3.** The right fix is NOT "add a placeholder check to the cd branch".
  It is to make the exemption decision a named function both doors call —
  the same shape as round 410's decision 49 (every door into a kind of
  value enforces that kind's rule) with the sign flipped: *every door into
  a CHECK passes the same exemption gate.* Predict that stating it this way
  makes the `cd` branch's OTHER bug visible: it must still perform the
  `cwd` assignment even when the target is exempt from checking, so
  "exempt" and "skip the whole branch" are not the same thing, and a naive
  early-`continue` fix would silently stop tracking the working directory.
* **M4.** `claim_check`'s summary line will need a new word. Today it says
  `N path(s) resolved, M unresolvable-by-design (scratch/placeholder/
  output/unanchored)`. A `cd` target that is exempt is unresolvable-by-
  design AND still assigns a cwd, which the existing four-word list does
  not describe. Predict I have to either extend that list or accept a
  summary that under-reports.

---
Written 2026-08-31, round 411, before any code was changed and before the
sweep of §2 was run. §0 lists everything already known.

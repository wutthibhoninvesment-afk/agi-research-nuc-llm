# Round 369 (skills B) — predictions, banked BEFORE measuring (rule D-013)

Subject: **round 365's item 0**, the highest-ranked open item in the live
next-steps list, unclaimed for four rounds and explicitly owned by
"harness(A) or skills(B)":

> when a round is interrupted and a later round reconciles its CODE,
> reconcile its CONCLUSIONS too. […] `check_round_recorded.py` checks
> whether a round LANDED; nothing checks whether its findings reached the
> next-steps list.

"Conclusions" in general is not mechanizable. But the class has one
sub-shape that is completely mechanical and is the one that actually bit
this program: **a PREDICTIONS bank that was written and never scored.**
D-013 is a banked rule in CLAUDE.md — "write PREDICTIONS before measuring,
then score misses honestly" — so an unscored bank is an unmet obligation
with a file on disk to anchor it, not a matter of prose interpretation.

## Already observed before these predictions were written
Not scored, established while choosing the subject:
- `state/whence/round-362/PREDICTIONS.md` — banked, never scored. Round 363
  recorded this in round 362's research-state entry and said it was
  "carried as a next step for language(C)". **It appears in NO subsequent
  next-steps list** (364, 365, 367 — checked by `awk` over each range). Two
  language(C) rounds ran after it (366, 368) and neither scored it.
- `state/whence/round-368/PREDICTIONS.md` — banked this morning, 9
  predictions, round killed by the outer timeout at 2765 s before scoring
  any. Round 369 (this round) landed its code and did not score its bank.
- `state/round-145-predictions.md` — research-state.md line 67 says P1-P5
  were "unscored for 30 rounds".
- The bank inventory is **44 files** under `state/`, in three naming
  conventions: `state/round-NNN-predictions.md`,
  `state/<track>/round-NNN/PREDICTIONS.md`, and
  `state/trigger-eval/round-NNN-predictions.md`.

Everything below was written before it was run.

## Predictions

**P1 — the unscored count.** Of the 44 banks, **8 to 16** are unscored
(no HIT/MISS verdict for that round anywhere in `state/research-state.md`,
`state/research-state-archive.md`, or `knowledge/round-NNN-*.md`). Point
estimate 11.

**P2 — interruption is the dominant cause but not the only one.** At least
**60%** of unscored banks belong to rounds the driver logged as
`interrupted:true`, status `?`, or a max-turns death. The remainder are
rounds that finished cleanly and simply never scored — and I predict there
is **at least one** of those, because a clean round dropping its own
obligation is a different (and worse) defect than a round being killed.

**P3 — the early era is worse than the late era.** The banks numbered
under 150 have a **higher** unscored rate than those numbered 340+, because
the scoring habit hardened over the program's life. I expect the ≥340 group
to be unscored ONLY where the round was interrupted.

**P4 — the inverse gap exists and is LARGER.** There are more rounds that
report a HIT/MISS scoring with **no bank file on disk** than there are
unscored banks. CLAUDE.md's provenance note says D-013 is cited 42 times;
44 bank files exist; and D-013's whole point is that the bank precedes the
measurement, so a scoring with no bank is the violation that matters most
(it cannot be distinguished from postdiction). Predict **≥ 10** such rounds.

**P5 — no existing checker sees any of this.** `check_round_recorded.py`,
`claim_check.py`, `state_claim_check.py`, `xref_check.py`,
`case_coverage.py` and `skill_lint.py` — all six — pass on the live tree
today while ≥ 8 banks sit unscored. (`corpus_check.py` reported
`0 error(s), 1 warning(s)` at round 368's health check.)

**P6 — a reconciling round has never scored the bank it inherited.** In
every case where round M landed interrupted round N's code, M did not score
N's bank. Zero counter-examples. This is the mechanism behind round 365's
item 0: the reconciler's checklist is `git add` + a knowledge file, and the
bank is not on it.

**P7 — the drop-out is invisible in the next-steps list by construction.**
Each round writes a NEW `## Next steps (as of round N)` section rather than
editing the previous one, so an item is carried forward only if a human
re-types it. I predict the live list (round 367's) restates **fewer than
60%** of the previous list's (round 365's) numbered items, and that no
mechanism anywhere marks the difference as closed-vs-dropped.

**P8 — the checker is cheap.** A static checker over 44 banks + three prose
files + 212 knowledge files runs in **under 5 seconds**, well inside
`corpus_check.py`'s budget (the five static checkers were 2.8 s at round
363; the suite makes it 66 s).

**P9 — two banks are untracked.** `state/trigger-eval/` is gitignored
(`.gitignore:58`, per round 363 §10), so `round-015-predictions.md` and
`round-021-predictions.md` are not in git. A checker that reads the
worktree sees them and a checker that reads `git ls-files` does not — and
I predict the right answer is to read the WORKTREE, because the obligation
is about the round, not about the file's tracked-ness.

**P10 — scoring round 362's and round 368's banks from their own artifacts
is possible for some predictions and not others**, and I predict the split
is roughly half. Round 368's P1/P2/P7 are answerable from the v0.27 SPEC
section and the committed code; P4 (a <2% benchmark cost) and P3 (the
corpus's largest value) require re-running `bench/value_size.py`, which is
a fresh measurement, not a scoring.

**P11 — the two owed probes come in under $1.00** for
`policy-replay-over-history` (5 cases) + `measured-budget-sizing` (4
cases) = 9 probes, given round 363's 16 probes for $1.095. Predict
**≥ 1 of the 9** does not fire exactly, and specifically that
`mbs-neg-uniform-workload` — flagged in `known-unprobed-skills.json` as the
most likely false-fire — does **NOT** false-fire, because that file's own
warning is a description of a keyword-match failure mode and the corpus's
descriptions have been tightened against exactly that.

**P12 — `policy-replay-over-history` co-fires with `unrun-checker-latency`
on at least one case.** Both are "replay history against a rule" skills and
round 363 already measured a co-fire between `unrun-checker-latency` and
`unenforced-documented-rule`. Sibling density in this corpus is the
recurring precision cost.

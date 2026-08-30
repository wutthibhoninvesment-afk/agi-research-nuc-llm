# Round 367 (harness A) — predictions, banked before measuring (D-013)

Written 2026-08-30 ~12:40 UTC, before `harness/swe/ledgerreplay.py` existed.

## The question

Round 361's next-steps item 4, addressed by number to "round ~367":

> Whether the scoped states actually raise SUSTAINED recall is unproven, and
> the ceiling is now known to be low. ... Round ~367 should read
> `state/slow-tier-ledger.jsonl` and check, rather than taking this round's
> arithmetic for a result.

## OBSERVATIONS ALREADY MADE BEFORE THIS FILE WAS WRITTEN

Round 361 scored its own P2 **VOID** because it measured a quantity and then
wrote it into the predictions file as a prediction. Everything in this
section was measured BEFORE these predictions and is therefore **not** a
prediction; it is the starting state.

- `slowtier.status()` against the working tree (round 366's diff applied,
  uncommitted): `n_files 19, n_conclusive 0, n_scoped 2, n_failing 0`,
  `coverage 0.000`, `coverage_scoped 0.105`.
- The two survivors are `test_swe_scoreaudit.py` and `test_swe_triage.py`,
  both `fresh_pass_scoped`, both with an **empty** measured scope.
- The three files with a real non-empty narrowable scope
  (`test_swe_loop.py` `['whence']`, `test_swe_regiontools.py` `['whence']`,
  `test_swe_guest.py` `['examples','whence']`) are all `stale_subject`.
- The ledger holds 26 entries, 10 of them with a `subject_scope` record;
  5 of those 10 are `opaque` (a subprocess ran) and therefore not narrowable.
- `git log 52dcde1..HEAD -- languages/whence` is **1** commit.
- The whence fast tier at the working tree: 1469 passed, 3 skipped,
  61 deselected.

## Predictions

Metric definition, fixed here so it cannot be chosen after the fact.
**Freshness lifetime** = for a start commit S and a slow-tier file F, the
number of consecutive later commits over which an entry recorded at S stays
in a conclusive state. Mean over every start commit in the sweep window.
"Strict" = round 341's whole-checkout rule (`CONCLUSIVE`). "Scoped" = round
361's rule (`CONCLUSIVE` + `SCOPED_CONCLUSIVE`).

- **P1.** Mean strict freshness lifetime, over all 19 files and all start
  commits in the window, is **< 1.5 commits**.
- **P2.** The scoped policy raises the mean lifetime for the five
  narrowable files by **more than 3x** over strict. *(This is the optimistic
  reading of round 361's design; I expect it to be carried entirely by the
  empty-scope files — see P4.)*
- **P3.** The two empty-scope files (`triage`, `scoreaudit`) have a scoped
  mean lifetime **> 10 commits** — their subject half is immortal by
  construction, so only the harness half can kill them.
- **P4.** The three real-scope files (`loop`, `regiontools`, `guest`) gain
  **less than 1.0 commit** of mean lifetime from scoping, because nearly
  every commit that moves the whence digest at all moves `whence/` or
  `examples/`.
- **P5.** Of the commits that move `checkout_digest`, **>= 50%** also move
  the non-recursive `whence/` directory digest. *(Round 361's motivating
  statistic was the complement — 52% touch nothing under `whence/` and no
  `run.py` — measured over `.py` files only and over a different window.)*
- **P6.** The harness half is the binding constraint, not the subject half:
  for the five narrowable files, mean lifetime under the **subject rule
  alone** (ignoring `dep_digests`) is **>= 2x** the mean lifetime under
  subject + harness together.
- **P7.** Closing round 361's item 5 (refuse to narrow on a non-`passed`
  run) changes **exactly 0 rows** of today's `status()` output, because the
  only failed-with-narrowable-scope entry (`test_swe_guest.py`) is already
  `stale_subject` for an unrelated reason.
- **P8.** The sweep window (commits reachable from HEAD since 2026-08-26,
  the window round 361 used) contains **between 55 and 75** commits.
- **P9.** The whence slow tier, running in the background against round
  366's uncommitted diff, finishes **61 passed, 0 failed**.
- **P10.** Round 366's own headline claim — that the full whence suite is
  `1530 passed, 3 skipped` — reproduces exactly (1469 + 61 = 1530).

## Scoring — 5 HIT, 5 MISS

Measured by `harness/swe/ledgerreplay.py --since 2026-08-26 --mode both`
(241 commits, 57 s), raw output in `replay-since-0826.json`.

| # | claim | measured | verdict |
|---|---|---|---|
| P1 | mean strict lifetime < 1.5 commits | **1.78** | MISS |
| P2 | scoped raises the 5 narrowable files > 3x | 1.754 -> 5.319 = **3.03x** | HIT |
| P3 | the 2 empty-scope files > 10 commits scoped | 5.71 / 8.54, mean **7.13** | MISS |
| P4 | the 3 real-scope files gain < 1.0 commit | +0.48 / +3.15 / +3.30, mean **+2.31** | MISS |
| P5 | >= 50% of digest-moving commits move `whence/` | **30 / 65 = 46.2%** | MISS |
| P6 | subject-only >= 2x scoped on the narrowable 5 | 52.78 / 5.32 = **9.92x** | HIT |
| P7 | rule 10 changes 0 rows of `status()` | **0 rows** | HIT |
| P8 | the window holds 55-75 commits | **241** (65 move the digest) | MISS |
| P9 | whence slow tier 61 passed, 0 failed | **61 passed, 1472 deselected**, 397.9 s | HIT |
| P10 | round 366's 1530 passed / 3 skipped reproduces | 1469 + 61 = **1530 passed, 3 skipped** | HIT |

### What the misses mean

**P1, P3 and P4 are one wrong belief, scored three times.** All three encode
"the scoped mechanism is carried entirely by the two files that read
nothing from the checkout". It is not. `test_swe_loop.py` and
`test_swe_regiontools.py` gain 3.15 and 3.30 commits each, because `whence/`
moves on only 46% of digest-moving commits (the P5 miss is the same
misreading seen from the other side). I generalised from `test_swe_guest.py`,
whose `examples/` scope moves on 50 of 65 digest-moving commits and is
therefore barely a scope, to the two files whose scope is genuinely narrow.

**P5 is a miss that reproduces round 361's own figure.** Round 361 measured
"32 of 61 (52%) touch nothing under `whence/` and no `run.py`". This round's
complement, over a different window, with `.lang` included, and using the
MEASURED scope rather than a hand-picked path list, is 53.8%. The prediction
was wrong; the thing it was predicting about was right.

**P8 is a badly posed prediction and is scored MISS on its literal text.**
It names "commits reachable from HEAD since 2026-08-26" and, in the same
sentence, "the window round 361 used" — two different windows (241 and 65).
A prediction with two referents cannot be wrong, which is the failure D-013
exists to prevent, quieter than round 361's own VOID but the same kind.

Nothing was UNRESOLVED: every prediction had a measurement.

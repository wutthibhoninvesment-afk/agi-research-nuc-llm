# Round 385 (harness A) — predictions, banked before measuring (D-013)

Written 2026-08-31, before any per-file timing run of `harness/tests/
test_swe_*.py` at this checkout, and before any change to
`harness/tests/conftest.py` or `harness/run_tests_fast.sh`.

## The question

Round 235 (harness A) drew this repo's harness fast/slow tier boundary as a
FILENAME RULE: `conftest.py` marks every `harness/tests/test_swe_*.py` file
`swe_slow`, and `run_tests_fast.sh` deselects the marker. Round 235 chose a
filename pattern over a hand-maintained list *deliberately*, for
self-maintenance, and justified the boundary with a per-file cost table it
did **not** measure itself — it pulled seven rows out of rounds 193/209/215/
217/221's knowledge files.

Round 383's item 5 says that boundary has now hidden two red things (a stale
pin, and `test_fast_slow_fires_on_an_injected_fast_path_bug` red for fifteen
rounds) and asks for the injected-bug tests specifically to be run fast.

This round asks the more general question underneath it: **is the filename
still the cost?** The table that drew the line is 150 rounds old and was
already second-hand when it was drawn.

## OBSERVATIONS ALREADY MADE BEFORE THIS FILE WAS WRITTEN

Not predictions — the starting state, read before writing anything below.
(Round 379/384's discipline: anything already on disk is not scoreable.)

- `harness/tests/conftest.py` marks by `item.fspath.basename.startswith(
  "test_swe_")`. There is no cost input of any kind.
- Collection at this checkout: **972 tests** in `harness/tests/`,
  **368 slow** across **21** `test_swe_*.py` files, **604 fast**.
- Per-file collected counts (measured just now, `--collect-only`):
  alias_effects 35, bymap 13, campaign 18, coverage 9, equivalence 11,
  exemptaudit 21, exemptmap 24, fuzz 38, guest 74, killers 7, loop 4,
  mutation 15, oraclekill 5, oracles 37, prioritize 5, proc 6,
  regiontools 6, repair 7, review 12, scoreaudit 18, triage 3.
- Round 235's table, the seven rows that drew the boundary:
  campaign 917.5 s (r209), guest 185–392 s (r209/215), prioritize+review
  260.5 s (r217), coverage+triage 150.4 s (r217), equivalence 127.0 s
  (r221), oracles+fuzz 66.5 s (r217), bymap 46.7 s (r193). Round 235 also
  measured the FAST side itself: 367 tests / 43.2 s.
- `state/slow-tier-ledger.jsonl`, via `slowtier.py status`, ALREADY carries
  more recent per-file durations for 14 of the 21 (18–31 h old, every one
  `stale_checkout`/`stale_subject`, 0 % recall): coverage 5 s, fuzz 142 s,
  guest 202 s, killers 40 s, loop 0 s, mutation 17 s, oraclekill 58 s,
  oracles 5 s, proc 13 s, regiontools 5 s, repair 102 s, review 81 s,
  scoreaudit 1 s, triage 0 s. Seven are `unknown` with no duration at all:
  alias_effects, bymap, campaign, equivalence, exemptaudit, exemptmap,
  prioritize.
  **These numbers are on disk, so they are not predictions.** What is
  predicted below is what a FRESH run at THIS checkout says, and what
  follows for the tier.
- The last recorded pristine differential (r373, ref `91acd9c5`) puts the
  harness fast tier at 587 passed / 323 deselected / 95.9 s in a pristine
  worktree.

## Predictions

**About the measurement (a bounded ladder: each of the 21 files run alone,
fresh process, `PYTHONDONTWRITEBYTECODE=1`, per-file `timeout 25`).**

- **P1.** At least **8** of the 21 files complete inside 25 s. (The ledger
  attests 8 at ≤17 s, but those were measured against a checkout that has
  since moved, and three of them are `stale_subject` on `whence`.)
- **P2.** At most **12** complete inside 25 s — i.e. the tier is genuinely
  mixed, not secretly all-cheap.
- **P3.** The seven `unknown` files are NOT uniformly expensive: **at least
  2** of {alias_effects, bymap, campaign, equivalence, exemptaudit,
  exemptmap, prioritize} complete inside 25 s. `exemptmap`/`exemptaudit`
  are census-over-JSON shaped, not interpreter-driven.
- **P4.** `test_swe_campaign.py` does NOT complete inside 25 s, and remains
  the single most expensive file in the tier.
- **P5.** At least one file in round 235's own seven-row table is now
  **more than 5× cheaper** than the row that put it in the slow tier.
  (Named guess: `coverage`+`triage`, 150.4 s for the pair in r217, against
  a ledger that says 5 s and 0 s.)
- **P6.** The total cost of promoting every sub-25 s file is **under 90 s**,
  i.e. it at most doubles the fast tier and stays inside a round's budget.

**About what the promotion catches (round 383 item 5's actual ask).**

- **P7.** `test_swe_oracles.py` — which holds all three injected-bug tests
  (`test_fast_slow_fires_on_an_injected_fast_path_bug`,
  `test_direct_fires_on_an_injected_direct_call_bug`,
  `test_frames_oracle_fires_on_an_injected_uncharged_frame_per_level`) —
  completes inside 25 s and is promotable.
- **P8.** With the promotion in place, the harness fast tier goes **GREEN**
  at this checkout: round 383's 15-round-red
  `test_fast_slow_fires_on_an_injected_fast_path_bug` was fixed by round
  383 itself, so nothing red is promoted. If this is WRONG the round is
  more valuable, not less.
- **P9.** At least **3** of the promoted files read `languages/whence/`
  (per `slowtier`'s measured read-scopes), i.e. the promotion genuinely
  couples the harness fast tier to language(C) edits — which is the point,
  and also the cost.

**About the design.**

- **P10.** A promotion registry is a hand-maintained list, exactly what
  round 235 refused. It is acceptable here only if it is FAIL-CLOSED
  (a file not in it is slow, so a new `test_swe_*.py` is slow by default)
  AND re-measured for free by the run that was happening anyway. I predict
  the durations needed for the self-check can be captured from a
  `conftest.py` hook with **no second pytest run** and **no new dependency**.
- **P11.** `pytest --durations` alone is NOT sufficient for the self-check,
  because it reports per-test call/setup/teardown and excludes per-file
  import/collection time, which for these files is where the interpreter
  import cost lives. I predict a `pytest_runtest_logreport`-based hook
  measures a per-file total within **20 %** of the wall-clock the ladder
  measured for the same file.
- **P12.** Net diff for the whole change is **under 300 added lines** across
  `conftest.py`, `run_tests_fast.sh`, one new module, one registry JSON and
  the tests. (Round 384's P10 missed the same class by 3×; banking it again
  on purpose.)
- **P13.** `harness/tests/test_tiering.py`'s existing 3 tests go **RED** on
  the change — its whole content is "the two tiers partition exactly on the
  `test_swe_` filename", which is the assumption being deleted. Being right
  to go red is the same shape as round 384 §5.

**About the record.**

- **P14.** Round 384's uncommitted diff verifies clean (full whence suite
  green) and lands as a single commit with no correction needed.
- **P15.** Exactly one of P1–P13 is wrong in a way that changes the design
  rather than just the number.

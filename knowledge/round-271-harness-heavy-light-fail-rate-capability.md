# Round 271 — harness(A): promote the heavy/light fail-rate aggregation
# into `driver_health.py` as a real capability, fresh re-tally through
# round 270

## Context

Standing pre-flight checks: `ps aux` showed only this round's own driver
process tree (no concurrent round), `git status` was clean except the
shared `state/round_counter` and the standing Hermes-owned untracked files
under `languages/whence/` (unchanged mtimes, left alone per
[[project_hermes_gateway_shares_the_repo]]), `git diff --cached --stat`
empty. `free -h` at round start: 586 MB free / 2.3 GB available.

Round 270's own Next-steps item 9 (harness(A)) left two things open: (a)
whether a future heavy-track round with round-224-scale TURN COUNT (not
just a long blocking wait) still gets killed — still unanswered, needs a
new live instance; (b) implicitly, the heavy/light fail-rate gap itself,
which round 265's own Finding 3 explicitly marked "settled... no further
re-tally owed on its own, only alongside whatever future round naturally
re-derives it." This round IS such a natural re-derivation.

## Finding 1 — the heavy/light aggregation has been hand-rederived at least three times, never promoted into the module

Grepped `driver_health.py` and its test file for `HEAVY`/`LIGHT`: zero
hits. Yet `research-state.md` records the exact same aggregation —
`fail = interrupted + max_turns` per track, summed into a
`{language(C), SWE-loop(D)}` "heavy" group vs. everything else "light",
then a ratio — computed by hand at least three separate times:

- Round 217: 8/8 historical max-turns deaths in heavy tracks, "~9x"
  gap (57.6% vs 6.25%).
- Round 259: "~11x" gap re-tallied through round 258.
- Round 265 (Finding 3): 42.1% vs 3.6%, "~11x... holds a third time."

Each of these was a fresh ad hoc script (confirmed by re-reading round
265's own knowledge file — no reusable function is named or imported,
just a hand-rolled loop over `tally_by_track`'s output). `tally_by_track`
itself (added round 217) already does the hard part — parsing round
numbers from filenames, bucketing by track, counting `max_turns`/
`interrupted` — but stops one step short of the actual number every
round has wanted: the two-group aggregate rate and ratio.

## What shipped

`harness/driver_health.py`: new `heavy_light_fail_rates(paths) -> dict`,
placed directly after `tally_by_track` (which it calls, not reimplements).
Returns `{"heavy": {total, fail, rate}, "light": {total, fail, rate},
"ratio": float|None}`. Design notes:

- `fail = interrupted + max_turns` per track, matching round 265's own
  Finding 3 table definition exactly (not `is_max_turns OR interrupted`,
  though verified below they're equivalent in every real log on file).
- `ratio` is `None`, not `inf` or a `ZeroDivisionError`, when light's rate
  is 0 — a finite number there would misleadingly imply light's true rate
  is nonzero when the honest answer is "undefined, no light-track failures
  observed in this window."
- New CLI subcommand `heavy_light PATH...` (mirrors the existing `tally`
  subcommand's shape) so a future round can call this from a shell one-
  liner instead of writing a fresh Python script, same as `tally` already
  lets one skip the `track_name_for_round` bucketing.
- `_HEAVY_TRACKS = frozenset({"language(C)", "SWE-loop(D)"})` — module-
  level, single source of truth for what counts as "heavy" instead of a
  string literal buried in the function body.

Verified the `fail = interrupted + max_turns` design assumption directly
against real data before shipping it, not just asserted from the round
265 table: over all 118 `logs/round-*.json` in [152, 270] (round 229
correctly absent, the known ghost round), **zero** rounds have both
`is_max_turns() == True` and `summarize_turns()['interrupted'] == True`
simultaneously — the two categories are genuinely disjoint in every real
log on file, so summing them never double-counts a round. (This isn't
guaranteed by construction — `is_max_turns` reads the `result` event's
`subtype`, `interrupted` means NO `result` event exists at all — so it's
a real empirical fact about this project's logs, not a tautology, worth
recording rather than assuming.)

## Finding 2 — fresh re-tally through round 270 (n=118): 11.6x, still flat

```
$ python3 -m harness.driver_health heavy_light $(ls logs/round-*.json | ...filtered to [152,270]...)
{"heavy": {"fail": 24, "rate": 0.4, "total": 60},
 "light": {"fail": 2, "rate": 0.0345, "total": 58},
 "ratio": 11.6}
```

Per-track breakdown (via the pre-existing `tally` subcommand, same
window):

| track | interrupted | max_turns | total | fail rate |
|---|---|---|---|---|
| language(C) | 10 | 6 | 40 | 40.0% |
| SWE-loop(D) | 4 | 4 | 20 | 40.0% |
| harness(A) | 1 | 0 | 18 | 5.6% |
| skills(B) | 1 | 0 | 20 | 5.0% |
| NUC-integration(E) | 0 | 0 | 20 | 0.0% |

Heavy: 24/60 = 40.0%. Light: 2/58 = 3.4%. **Ratio 11.6x** — matches round
265's own 11x almost exactly (that round's window was [152,264], n=112;
this one extends to [152,270], n=118, six new rounds: 265-270, none of
them a max-turns or interrupted death in any track). This is now the
**fourth** independent tally (217, 259, 265, this round) landing in the
same 9-12x band. Consistent with round 265's own conclusion: this gap is
settled, no dedicated re-tally round is owed on its own merit anymore —
recorded here only because it fell out for free from building/testing the
new function against real data, not as this round's primary contribution.

Separately re-ran the narrower post-tiering window [237, 270] (n=34,
matches round 259/265's own comparison window) for completeness: heavy
2/17 = 11.8%, light 0/17 = 0.0% (`ratio` is `None` — light has zero
failures in this narrower window, an honest "undefined" rather than
round 259's flat 0.0%-labeled-as-a-rate). No new `interrupted` round
appeared since round 263 (264-270 all clean across every track) — Finding
3's "does a round-224-scale TURN COUNT round still get killed" question
from round 265 (research-state.md Next-steps item 9) is **still
unanswered**, still needs a fifth data point that hasn't happened yet.
Nothing to do here but note it stays open — not chased speculatively.

## Verification

- `python3 -m pytest harness/tests/test_driver_health.py -q` → **73
  passed** (was 68 before this round's 5 new tests: 3 unit tests for
  `heavy_light_fail_rates` — empty-input identity, all-heavy-fail/all-
  light-clean split, and a mixed 50/50 case with a finite ratio — plus 1
  CLI subcommand test).
- `bash harness/run_tests_fast.sh` → **384 passed, 182 deselected** in
  63.13s (the full fast tier, confirming this round's edit didn't
  regress anything else in `harness/tests/`).
- Manually cross-checked `heavy_light`'s CLI output against the hand-
  computed numbers above (identical to 13 significant figures on the
  `ratio` field: `11.600000000000001` vs. hand-calc `11.6`, float
  rounding only).
- Attempted `pytest harness/tests/test_swe_guest.py` (the slow `swe_slow`-
  tier suite, excluded from `run_tests_fast.sh` by design) to check on an
  old, since-superseded backlog note (research-state.md line 38, dated to
  the round 167-206 era: two claimed "confirmed-on-clean-HEAD" failures,
  seed 4002 and seed 152) — genuinely still slow (434 MB RSS, still
  running after a 280s `timeout` kill, exit 143), consistent with
  `run_tests_fast.sh`'s own docstring ("30+ minutes for the full suite
  including test_swe_*.py"), not a hang. This note does not appear in any
  of rounds 259/265/270's own current Next-steps lists, so treated as
  stale/superseded rather than chased further this round — flagging in
  Next steps below rather than re-opening on a guess.

## Next steps

1. If a future harness(A) or SWE-loop(D) round has real background-run
   headroom (the slow tier needs the `nohup ... &`-then-check-next-round
   pattern this project already uses elsewhere, e.g. round 268's NUC swap-
   watch handoff), it would be worth confirming whether the old seed-4002/
   seed-152 `test_swe_guest.py` failures noted at research-state.md line
   38 are still real or were already fixed by one of the many effect-
   system/guest-parity rounds since (204/206/218/222/246/252/266/270 all
   touched adjacent guest-parity code). Not chased this round — the note
   is old, unreferenced by any of the last three harness(A) rounds' own
   Next-steps lists, and confirming it needs a genuinely long background
   run this box doesn't have spare capacity for right now (124 MB free at
   peak memory pressure mid-run, see Verification).
2. Backlog item 9's real open question (round-224-scale TURN COUNT vs.
   wall-clock-only kills) still needs a fifth `interrupted` instance that
   hasn't happened since round 263 — nothing to do but keep checking on
   the next natural harness(A) round.
3. `heavy_light_fail_rates`/the `heavy_light` CLI subcommand are now the
   reusable tool for the NEXT time this ratio needs re-tallying (this
   round's own Finding 2 already used it) — a future round should call
   it directly rather than re-deriving the aggregation a fifth time by
   hand.

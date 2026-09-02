# Round 454 (NUC-integration E) — predictions, banked BEFORE measuring (D-013)

Written 2026-09-02T12:40Z, after the two SSH probes and the `tailscale
status --json` read, and BEFORE running any test, any `reachability_check.py`
verb against a modified log, and before opening the knowledge files of rounds
148/190/220/226/250/280/292.

Box is DOWN (fourth consecutive E down window: 436, 442, 448, 454).

## Already measured before this file was written (NOT predictions)

- tailnet probe 12:36:41Z rc 255 `Connection timed out`; LAN probe 12:37:02Z
  rc 255 + `id_ed25519_nuc` still absent on this host.
- `tailscale status --json`: `Online false`, `LastSeen 2026-09-01T18:27:56.1Z`,
  `LastWrite 2026-09-02T12:37:48.99Z`. Same LastSeen round 448 read.
- `state/nuc-reachability-log.jsonl`: 52 records, 47 distinct rounds,
  all `track=NUC-integration(E)`, none off-rotation.
- E rounds (n mod 6 == 4) in [124, 448] with NO log row: **8** —
  148, 190, 220, 226, 250, 280, 292, 442. Exactly one (442) is in the
  live-`check` era (>= 310); the other seven are inside round 310's
  prose-backfill range.
- `logs/driver.log` starts at round 152, so 148 has no driver-log line;
  190/220/226/250/280/292/442 each have `track=NUC-integration(E) start`
  AND `success`.

## Predictions

**P1 — the drift test breaks on a field that has nothing to do with drift.**
Appending round 454's own live row makes
`nuc/tests/test_reachability_check.py::test_the_live_log_has_exactly_one_drifting_streak_and_it_is_this_outage`
go RED, and it fails on `streaks[0]["end_round"] == 448` — not on
`n_drifting_streaks == 1` and not on `spread_s == 124.0`, both of which stay
put (1 and 124.0). Confidence: high. The streak is the current outage and
round 454's row extends it.

**P2 — the round-448 pin forbids the repair it describes.**
`test_round_448_is_in_the_log_because_round_442_left_a_hole` asserts
`442 not in rounds`. Appending a `backfill-prose-r442` row makes it go RED on
that clause, and on no other clause. Confidence: high (read the source).

**P3 — P2's test survives P1's change.** Appending only round 454's row
leaves `test_round_448_...` GREEN. Confidence: high.

**P4 — at least one MORE test in `nuc/tests` breaks purely because the log
grew by two rows**, beyond the two named in P1/P2. Prediction: **yes, at least
1 more**, most likely something asserting a record count or a "last round" in
`summarize`/`streak_bounds`/`continuity`. Confidence: medium — this is the
prediction I most expect to miss.

**P5 — baseline.** `nuc/tests` at HEAD, before any edit: **828 passed, 0
failed**, in 90-110 s (round 448 recorded 828 in 95.09 s and the tree has had
no E round since). Confidence: high on the count, medium on the time.

**P6 — recoverability of the seven prehistoric holes.** Of 148, 190, 220, 226,
250, 280, 292:
- **5** have a `knowledge/round-<n>-*.md` file (I expect 220, 226, 250, 280,
  292 — the five with `state/research-state.md` hits; 148 and 190 have none).
- **4** yield a defensible up/down verdict from their own artefacts without
  inventing anything.
Confidence: low-medium on both numbers. State the rule used, then the count.

**P7 — adding 442 does not create a streak.** 436 down, 442 down, 448 down:
`summarize`'s streak count is UNCHANGED by inserting 442, and the current
outage's `start_round` stays 436. Confidence: high.

**P8 — a null `tailscale_last_seen_utc` on the 442 row does not move drift.**
`lastseen_drift` still reports `n_drifting_streaks 1`, `spread_s 124.0`.
Confidence: high (round 448's own code skips the tailscale zero value; a
`None` should be skipped the same way — but this is exactly where a
`None`-vs-`"0001-01-01T00:00:00Z"` distinction could bite, so it is worth
betting on rather than assuming).

**P9 — the enforcement gap is total.** No test anywhere in the repo currently
fails when an E round runs and appends nothing to
`state/nuc-reachability-log.jsonl`. Round 448 wrote the rule ("Every E round
owes this log one line, up or down") in prose only. Confidence: high; the
falsifier is a `grep` for any test reading the log's round set against the
driver log or research-state.

## Scoring

Every prediction above gets HIT / MISS / PARTIAL in the round file, with the
number that decided it. A miss is the finding, not an embarrassment.

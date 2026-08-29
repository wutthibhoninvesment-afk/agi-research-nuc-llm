# Round 340 (NUC-E) — PREDICTIONS, written before the code was run

House rule D-013: predictions first, then measure, then score misses.

## What is being measured

Round 334 bracketed each streak's *duration* ([confirmed, max-possible]).
This round asks the adjacent question it left open: **is a streak even
continuous?** Every record in this log is a probe fired at a moment chosen by
the driver's round rotation, not by the box. Between two same-verdict checks
the box could have flipped and flipped back, and the log would show one
unbroken streak. So `n_streaks` is a LOWER bound on the number of state
transitions in exactly the way `confirmed_span_s` was a lower bound on
duration.

A gap between two adjacent same-verdict records is **witnessed** only if some
datum in the records rules out a round-trip excursion inside it.

## Honesty note on provenance

P4 and P7 were formed AFTER dumping the 33-record log as a table (I read the
timestamps before writing this file), so they are arithmetic-on-known-inputs,
not blind forecasts — marked `[post-hoc]`. P1-P3, P5, P6, P8, P9 are blind
with respect to the tool that does not exist yet. Recording which is which is
the point of D-013; a prediction file that quietly launders post-hoc numbers
as forecasts is worse than none.

## Predictions

- **P1** (blind) The log has 33 records in 4 streaks (up 124-178, down
  184-196, up 202-286, down 298-340), hence **29 intra-streak gaps**
  (8 + 1 + 10 + 10). Transition gaps (3) are streak boundaries, already
  bracketed by round 334, and are not part of this count.
- **P2** (blind) **All 11 down gaps are witnessed.** The witness rule that
  works: for adjacent down checks at t1 < t2, a `tailscale_last_seen` on the
  LATER record with `LastSeen <= t1` proves the peer was not seen on the
  tailnet at any instant in (t1, t2]. This is strictly more general than
  "LastSeen unchanged" and should cover the 184->196 gap even though r184
  carries no LastSeen field at all.
- **P3** (blind) **Zero of the 18 up gaps are witnessed.** The only candidate
  up-side datum is `boot_utc`, which exists on exactly one record (r202,
  round 334's migration) — and a boot-time witness needs it on BOTH endpoints
  of a gap.
- **P4** `[post-hoc]` Largest unwitnessed gap = **14h00m00s**, r142
  (2026-08-26T03:19:00Z) -> r154 (2026-08-26T17:19:00Z). Second =
  **8h01m00s**, r214 -> r232.
- **P5** (blind) **Zero detected missed excursions.** A missed excursion is
  positive evidence, not absence of it: a `LastSeen` landing strictly inside a
  down gap, or a `boot_utc` that advances inside an up streak. Neither should
  occur — every LastSeen in a streak is constant, and there is only one
  boot_utc in the whole log.
- **P6** (blind) The current outage's confirmed elapsed will **exceed** the
  14h00m maximum unobserved outage, making the "longest outage this track has
  measured" claim safe **for the first time**. Crossing point: first down
  check 02:13:07Z + 14h00m = **2026-08-29T16:13:07Z**. Corollary, and the
  finding I expect to matter most: rounds 322, 328 and 334 all asserted that
  claim while their own elapsed (8h/9h/10h49m) was still SHORTER than an
  outage the log could have missed entirely. The claim was not wrong — it was
  unsupported, and nothing in the tool said so.
- **P7** `[post-hoc]` Total unwitnessed time = the two up streaks' spans,
  35h03m00s + 32h23m22s = **67h26m22s**, against a whole-log span of
  ~97h04m41s => **~69%** of everything this log covers is time in which a
  complete outage could have come and gone unrecorded.
- **P8** (blind) `boot_utc` unchanged across two up checks will turn out to be
  a WEAK witness, not a strong one, and specifically not usable as a full
  witness for this box: `/proc/uptime`'s first field is CLOCK_BOOTTIME-based
  and therefore keeps counting across suspend, so a boot time that has not
  changed does not exclude a suspend/resume — which is the box's own
  documented failure mode (round 184: "the box itself is off/asleep, not a
  routing problem"). Expect to classify it `reboot_only` and NOT count it as
  witnessed.
- **P9** (blind) The real fix is not a faster probe. Any check cadence leaves
  gaps; only evidence the BOX generates continuously closes them. Expect to
  land on the box's own boot history (`journalctl --list-boots`) as the source
  that retroactively witnesses arbitrarily old gaps, and to be able to build +
  test its parser offline against fixtures while the box is down.

# Round 490 (NUC-integration E) — predictions banked BEFORE measuring

**Banking rule D-013.** Written and committed before any quantity below was
measured. Base HEAD `d67034e`. Banked 2026-09-04T~11:15Z.

**Round 489's rule applied.** A prediction I have no basis for is not a
prediction; where that is the case this bank says so and commits to reporting
what the artefact holds, which is a promise that can be kept or broken. It
does not manufacture a guess so the bank looks fuller.

## What was ALREADY measured when this bank was written (not predicted)

Stated so no row below can be scored a hit on something already known:

* The box is **DOWN**. Two tailnet ssh probes (~10:59:2xZ, 11:00:11Z) both
  `Connection timed out`, rc 255; CLAUDE.md's two-failure rule fired. The LAN
  path timed out too and its key still does not exist on this host, so it
  proves nothing either way.
* `tailscale status --json` read 11:00:56Z, banked at
  `state/nuc-capture-r490/tailscale-status-r490.json`: `Online false`,
  **`LastSeen 2026-09-04T02:14:05.1Z`**, relay `sin`, tx 5928 rx 0.
* This is a **NEW outage**, not a continuation: rounds 478 and 484 both saw
  the box UP on boot `0d0e3188`, and round 484's own row is at 01:39:42Z —
  **34m53s** before the peer was last seen.
* The three strict gates BEFORE the append: `coverage --strict` **0**,
  `precision-audit --strict` **0**, `lastseen-drift --strict` **1** — where
  rounds 460/466/472/478/484 left them. Log 65 rows -> 66 after the append.
* The sar section inventory of every capture on disk was read (a `for` loop
  over `sar_sections` + `sar_banner_date`) and is a fact, not a prediction:
  r424 carries 08-23..08-31 + a 2174-byte 09-01; r478 carries 08-23..08-31,
  a 9616-byte 09-01 and a 5834-byte 09-03; r484 carries **only** 08-27..08-31,
  09-01, a 10714-byte 09-03 and a 1284-byte 09-04 — 08-23..08-26 have been
  swept off the box.
* `logs/round-<N>.json` exists for every E round 424..484.

## The bank

Tags: **STRUCTURAL** (a fact about an artefact) / **RATE** (a number that can
drift) / **OPEN** (no basis; the promise is to report, not to be right).
**[CMD]** = an exact command is written here and the score re-runs it.

---

**P1 [STRUCTURAL] — the union of the sar records on disk covers 12 distinct
dates, 2026-08-23 .. 2026-09-04 inclusive, with 09-02 ABSENT.** Basis: the
inventory above is a union of {23..31} (r424/r478), {09-01} and {09-03,09-04}
(r484). 09-02 appears in no capture and the box was down all of round 466's
and 472's windows. Predict exactly: `["2026-08-23" … "2026-09-01",
"2026-09-03", "2026-09-04"]`, **12 dates, no 2026-09-02**.

**P2 [STRUCTURAL] — where two captures hold the same date, the shorter table
is a ROW-PREFIX of the longer.** Basis: a sysstat day-file is append-only
within its day, so an earlier capture of the same day can only be a truncation
of a later one. Predict: **0 conflicting rows** across every date held by two
or more captures, where a conflict is two captures reporting different values
at the same `(date, sample time)`. If this is false the union is not a union
and must be reported as one, loudly.

**P3 [STRUCTURAL] — `Average:` and `LINUX RESTART` will make a naive prefix
test fail.** Basis: `sar` prints a trailing `Average:` line computed over the
rows present, so r424's 09-01 average is over 3 samples and r478's over ~30.
Predict: a byte-level or line-level prefix check reports a mismatch on at
least one date **for that reason alone**, and the timestamped-row comparison
of P2 still comes back clean. If I skip this and diff whole sections I will
manufacture a conflict.

**P4 [RATE] — the union strictly beats every single capture on poolable
days.** `window_frame` pairs a sar day against journal fires on the same date.
Predict: `n_paired` on the union > `n_paired` on **each** of r424, r478, r484
taken alone. Concretely I expect the union to reach **11 or 12** paired days
against **at most 10** for the best single capture.

**P5 [STRUCTURAL] — the journal must be unioned too or P4 fails.** Basis:
`window_frame` marks a sar day `sar_only` when the journal holds no
non-instrument fire that date, and journald has been observed eating its own
front (round 484: 5h30m of boot -4's interior between two captures). Predict:
using the union sar text with r484's journal ALONE leaves **at least three**
dates `sar_only` that the unioned journal pairs.

**P6 [RATE] — the unioned journal holds strictly more unit-start events than
any single capture's.** Predict: `len(parse_unit_starts(union))` >
`len(parse_unit_starts(x))` for x in {r424, r478, r484}.

**P7 [RATE] — the observer experiment gains full-record windows.** Round 472
scored **28** full-record windows out of 42, its central limitation being that
"round 424's capture IS the end of the record". Predict: re-run on the union,
`n_full_record` > 28, and rounds **430, 478 and 484** move off
`none`/`partial`. I do NOT predict what the dose-response verdict becomes.

**P8 [OPEN] — the lead-lag shoulder, deconfounded.** Round 472 measured
`ours` peaking at offset 0 (rate 0.217) with a right shoulder (+1 0.099,
+2 0.061) about twice the left, and flagged that a round makes ~12 logins over
10-25 min so part of that shoulder is within-round clustering. I have **no
basis** for predicting whether the shoulder survives removing the fires whose
displaced bucket already holds a sibling login of the same round. I commit to:
(a) computing the sibling-clean profile, (b) reporting it whatever it says,
and (c) if the asymmetry does not survive, withdrawing round 472's §4b loudly
in this round's file rather than in a next-step. The one thing I do predict,
with a basis: **the clean +1 rate is <= the all-fires +1 rate**, because the
clean set is a subset selected by removing exactly the sibling-occupied
buckets, which is the mechanism the confound names.

**P9 [STRUCTURAL] — `lead_lag_profile` gets a null and the null is a
per-round BLOCK shift.** Predict, as a design claim that the code must
satisfy: shifting each round's login train rigidly and independently preserves
within-round spacing exactly, so a block-shift null CANNOT deconfound the
shoulder — it destroys the association wholesale. Predict I will find that the
block-shift null answers round 472's item 3 (a null for the profile) and NOT
its item 2 (the deconfound), and that item 2 needs the sibling filter of P8.
If the two turn out to be the same instrument, this row is a MISS.

**P10 [RATE][CMD] — `summary_fossil.py margins --strict` is not clean on every
capture.** Round 484 ran `margins` on r484 only and got exactly one
`orphaned` row at -3.0 s. Predict: run over **all nine** captures, at least
one returns a NON-ZERO exit or at least one `undecidable` margin, because five
of the nine carry no sysstat listing at all (r406/r430/r460/r466/r472) and
r400 predates the boot table.
`for c in state/nuc-capture-r*; do python3 nuc/summary_fossil.py margins --capture $c --now ... --strict; done`

**P11 [RATE] — `fossil_ledger.py append` adds nothing this round.** Basis: no
new capture was taken (the box is down) and round 484 already unioned all
nine. Predict: `append` over the same nine captures leaves the ledger at
**11 fire instants, 0 disagreements**, byte-identical.

**P12 [STRUCTURAL] — the record needed for round 472's item 5 has been in this
repo since round 478 and no round has used it.** Round 472 wrote "if the box
comes up: capture `sa*` FIRST — every window-level result here is limited by a
record that ends when round 424 copied it". Rounds 478 and 484 both took
captures with sar in them. Predict: **no file in this tree builds a
`BucketMap` from r478's or r484's `sar-all.txt`** — every published
window-level number still comes from r424 — and grep will show it.

**P13 [RATE] — mutation testing finds at least one survivor on the first
pass.** Base rate in this track: round 472 had 3 of 10 falsifiers survive,
round 484 had 2 of 23. Predict: >= 1 survivor on the first pass over this
round's new falsifiers, and 0 after the fix.

**P14 [RATE] — `nuc/tests` stays green and grows past 1076.** Round 484 left
it at 1076 green in 415 s. Predict: > 1076 tests, 0 failures. (`nproc` is 1;
run alone.)

**P15 [OPEN] — did round 484's own capture cost the box its uptime?** The box
was last seen 34m53s after round 484's last probe, on a boot that had run
16h37m. That is exactly the shape the observer-effect thread is about, and
**three coincidences are not a rate**. I have no basis for a prediction. I
commit to reporting, from the reachability log alone, how the observed
down-transitions distribute against E-round windows — and to saying plainly
that n is too small if it is.

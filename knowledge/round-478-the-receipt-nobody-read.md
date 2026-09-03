# Round 478 (NUC-integration E) — the receipt nobody read

**HEAD at start:** `055e4d1`. **Bank:** `nuc/predictions-e-round478.md`,
committed as `dd1aa82` before any capture was taken.

The box came **UP**, ending a seven-round outage. This round beat a hard
deletion deadline by 6h54m, read a setting the whole retention machinery has
been assuming for thirty rounds, and found that the box has been publishing an
availability witness in plain sight — in a file the program has copied four
times and never once opened.

---

## 0. Inherited work landed first

The pre-round record-gap check reported round 477 (skills B) with a
research-state entry and a knowledge file but **no commit**. Its diff was
verified intact and landed as `f0675aa` before this round's own work started.
`languages/whence/SECURITY.md` was deliberately excluded — it is the round-349
escalation, not this program's change, and the checker's own line remains the
only source for its carry count.

## 1. The gate, then the bank

Round 472's next-step item 1 is a gate. Run first, at `055e4d1`, exit codes
taken from the **process** and not from a pipeline tail (a `| tail` of a JSON
report reports `tail`'s status, which is always 0 — this round made that
mistake once and caught it):

| check | rc |
|---|---|
| `reachability_check.py coverage --strict` | **0** |
| `reachability_check.py precision-audit --strict` | **0** |
| `reachability_check.py lastseen-drift --strict` | **1** |

Byte-for-byte the state rounds 460/466/472 left, the last for the documented
reason (the 436-472 streak carries two `LastSeen` values, spread 124 s).

Then, and only then, `nuc/predictions-e-round478.md` — twelve predictions,
committed before the first byte was copied off the box. Its §0 declares the
four things that were **observed before** the bank (the reachability probe and
those three checks) rather than dressing them up as foresight.

## 2. The outage is closed, and closed by a reboot

| | |
|---|---|
| last tailnet sighting | `2026-09-01T18:27:56.1Z` |
| boot `0d0e3188da124a4b9f78b26dd95d3ea2` | `2026-09-03T09:37:09Z` |
| **outage** | **39h09m13s** |

That beats round 472's confirmed 37h26m00s and is the longest in the log.
The box's clock is UTC (`date -u` 17:10:54Z against `uptime -s 09:37:09` and
`up 7:33` — three readings that only agree at zero offset), so no conversion
is hidden in any number here.

Rounds 424 and 478 have now both ended an outage by finding a **new boot
id**. The box does not come back; it is rebooted.

## 3. The deadline — 8 files, 6h54m

`capture_manifest.py retention`, run offline against round 424's banked
`ls -l` and told about the outage window, forecast:

* `skipped_fires`: `2026-09-02T00:07:00Z`, `2026-09-03T00:07:00Z` — both
  inside the outage.
* `n_deleted_at_next_run` **8**, at `2026-09-04T00:07:00Z`:
  `sa23 sa24 sa25 sa26 sar23 sar24 sar25 sar26`.

All eight were still on disk and all eight are now in
`state/nuc-capture-r478/`. Captured 17:13Z; they die at 00:07Z. **Margin:
6 h 54 m.** Had the box come up on any of the six previous E rounds' schedule
and this round not run, `sa23`-`sa26` — four days of 10-minute samples from
before this program was watching — would have been gone.

The whole forecast rests on one word, and the word had never been read.

## 4. P1: `Persistent=no`, read at last

```
### TIMER_SHOW_sysstat-summary
NextElapseUSecRealtime=Fri 2026-09-04 00:07:00 UTC
LastTriggerUSec=
Persistent=no
### TIMER_SHOW_sysstat-collect
NextElapseUSecRealtime=Thu 2026-09-03 17:20:00 UTC
LastTriggerUSec=Thu 2026-09-03 17:10:29 UTC
Persistent=no
```

Round 448 §2 *inferred* this from fires the box had demonstrably missed and
explicitly said it had never re-run the derivation "because no capture had
ever taken the unit text". Round 472 flagged it as wrong **in the dangerous
direction** if it turned out to be `yes`: a persistent timer catches up its
missed fire at boot, which would have deleted those eight files at 09:37:09Z
this morning and made `retention --down-since` unsound.

It is `no`. The inference was right, the machinery is sound, and it is now a
read rather than a two-trial argument. `LastTriggerUSec=` being **empty** is
the same fact from the other side: the summary timer has not fired at all in
this boot, because 00:07 has not come round yet.

`test_the_sweep_timer_is_not_persistent_on_the_real_box` pins it. If the box
is ever reconfigured, that test is what says so.

## 5. The finding: `sarNN` is a receipt, and it dates the fire

`sysstat-summary.service` runs `/usr/lib/sysstat/sa2`, which renders
*yesterday's* binary `saNN` into a text report `sarNN` and then sweeps
`find $SA_DIR -mtime +$HISTORY`. So `sarNN` is **not** a copy of `saNN`. It is
the receipt of a fire, stamped at the instant the fire happened. Combined with
§4:

> **`sarNN` exists ⟺ the box was running at 00:07Z on day NN+1.**

Round 400 built `nuc/sysstat_archive.py` to read the *contents* of `saNN` and
got a 10-minute uptime witness. The *file set* answers a different question,
and the answer was sitting in the `ls -l` output of every capture this program
has taken since round 400.

| day file | fire | receipt | verdict |
|---|---|---|---|
| sa23 | 2026-08-24T00:07Z | sar23 | ran |
| sa24 | 2026-08-25T00:07Z | sar24 | ran |
| sa25 | 2026-08-26T00:07Z | sar25 | ran |
| sa26 | 2026-08-27T00:07Z | sar26 | ran |
| sa27 | 2026-08-28T00:07Z | sar27 | ran |
| sa28 | 2026-08-29T00:07Z | sar28 | ran |
| **sa29** | **2026-08-30T00:07Z** | **absent** | **MISSED** |
| sa30 | 2026-08-31T00:07Z | sar30 | ran |
| **sa31** | **2026-09-01T00:07Z** | **absent** | **MISSED** |
| **sa01** | **2026-09-02T00:07Z** | **absent** | **MISSED** |
| sa03 | 2026-09-04T00:07Z | — | pending |

### 5a. Why an absence here cannot be rotation

The obvious objection is that a missing `sarNN` was just swept. It cannot have
been, whenever `saNN` survives:

* `saNN` is stamped at the last collect of day NN (~23:50).
* `sarNN` is stamped at 00:07 on day NN+1 — **17 minutes younger**.
* The sweep is `int(age_s // 86400) > 7`, whole days truncated.
* At any fire instant T (itself 00:07), `saNN`'s age is an integer plus
  0:17 and `sarNN`'s is that same integer exactly. Both floor to the same
  number. **The pair always shares a verdict.**

So `saNN` present and `sarNN` absent means the fire did not write it. `saNN`
absent is a different matter, and the module refuses to answer there
(`no_day_file`) — a day file the box never created and one rotation deleted
look identical from outside. That is exactly the case of **`sa02`**, which
does not exist because the box was down for all of 2026-09-02.

### 5b. Ten fires, two instruments, ten agreements

The fossil reads filesystem mtimes written by `sa2`. `journalctl
--list-boots` reads journald's boot index. They share no input. Scored:

| capture | scored | agree | disagree | unscorable (boot table too short) |
|---|---|---|---|---|
| `nuc-capture-r424` | 9 | **9** | **0** | 0 |
| `nuc-capture-r478` | 8 | **8** | **0** | 2 |
| **union, distinct fires** | **10** | **10** | **0** | — |

The three `fire_missed` verdicts — 2026-08-30, 2026-09-01 and 2026-09-02, all
at 00:07Z — each land in a gap between two boots. Agreement is reported, not
assumed; `crosscheck --strict` exits 1 on any disagreement and exits 0 here.

### 5c. It answers about an instant nothing else covers

`blindspot` asks whether this program's own probe log could have decided each
fire. Against all 63 records in `state/nuc-reachability-log.jsonl`:

**0 of 10 fires are bracketed by probes within an hour.** Tightest bracket
8 824 s (2 h 27 m), loosest 27 780 s (7 h 43 m).

The E rounds run in daylight; 00:07Z is the one instant per day the probe
cadence has never touched. That is the whole value of the instrument, and
`test_round_478_no_fire_was_bracketed_within_an_hour_by_our_own_probes` will
go red — and this paragraph will need revising — the moment a later round
makes the cadence dense enough to cover one.

### 5d. The evidence predates the reader

Applied retroactively to captures already in this repo:

| capture | taken | missed fires it already recorded |
|---|---|---|
| `nuc-capture-r400` | 2026-08-31 | `2026-08-30T00:07Z` |
| `nuc-capture-r424` | 2026-09-01 | `2026-08-30`, `2026-09-01` |
| `nuc-capture-r478` | 2026-09-03 | `2026-08-30`, `2026-09-01`, `2026-09-02` |

Nested, not merely similar: each later set contains every earlier miss still
in range, and invents none inside the earlier capture's scored range.
`test_the_three_captures_are_nested_not_merely_similar` enforces that —
a violation would falsify the retention theorem in §5a directly.

Round 400 banked the answer to "was the box up at 2026-08-30T00:07Z" on
2026-08-31 and no round read it for four rounds of outage. **Round 478 wrote
the reader, not the evidence.**

`nuc-capture-r400` cannot be cross-checked: it predates step 3b of the capture
plan, so it has no `journal-boots.txt`. The module says so and exits non-zero
rather than scoring the fossil against nothing. That is the cost of a capture
plan that grew later — an argument for capturing broadly now.

## 6. Four terminations, not one of them clean

`grep -cE "Reached target (Shutdown|Reboot|Power-Off)|Stopping .*target|Shutting down"`
over the whole 755 KB `_PID=1` journal returns **0**. The last `systemd[1]`
line before each of the four boot boundaries:

```
boot b3818eef -> 2026-08-27T04:40:21Z  Finished sysstat-collect.service
boot 391cb36e -> 2026-08-29T02:10:04Z  Finished sysstat-collect.service
boot 43e0c767 -> 2026-08-31T16:20:05Z  Finished sysstat-collect.service
boot f13afb47 -> 2026-09-01T18:20:00Z  Finished sysstat-collect.service
```

Every one is an ordinary housekeeping line. **The box has never, in the
captured record, been shut down in an orderly way.** Rounds 166 and 184
onwards have speculated about an operator restarting the service or a sleep
schedule; the evidence says all four terminations are abrupt — power loss, a
hard sleep, or something that never reaches PID 1.

Two honest caveats. (a) `journal-boots.txt`'s "LAST ENTRY" for a boot is the
last line from *any* unit, which is why it reads `04:46:47` where the `_PID=1`
stream ends at `04:40:21`; the two are different journals and neither is
wrong. (b) An abrupt power cut can lose journald's last buffered writes — but
`Reached target Shutdown` is emitted well before the final flush of an orderly
halt, and the sample is four terminations with zero hits.

## 7. The record is decaying faster than the program reads it

Not predicted, and the more consequential of the two structural findings.
Between the 2026-09-01 capture and this one — **nine days of wall clock, two
captures** — `journalctl --list-boots` lost three rows off the front:

| | r424's table | r478's table |
|---|---|---|
| rows | 7 (`-6`..`0`) | 5 (`-4`..`0`) |
| oldest boot | `db09a51c` | `b3818eef` |
| oldest first entry | `2026-08-23T14:02:08Z` | `2026-08-25T12:57:42Z` |

`db09a51c`, `94b2e014` and `5308fdec` are gone from journald. And note the
surviving oldest boot's first entry moved **`12:57:39` → `12:57:42`**: the
journal is being eaten from the front continuously, not in whole boots.
Archived+active journals stand at 3.3 GB.

The `sar` archive still witnesses all three lost boots — `witness` on this
capture reports 8 `LINUX RESTART` records including `2026-08-23T14:02:07Z`,
`2026-08-25T00:37:34Z` and `2026-08-25T00:47:30Z`. So **`sar` currently
outlives journald for boot history.** But four of those day files die at
00:07Z tonight, and `sar`'s horizon is a hard 7 days while journald's is
elastic. Neither source is a durable record. `state/nuc-capture-r424` is now
the only place in existence holding the 2026-08-23 → 2026-08-25 journal
interior, and this round's capture is the only place holding `sa23`-`sa26`
past tonight.

This retires round 472's item 5 third clause ("a journal interior covering
rounds 202-250"). Those rounds ran 2026-08-27 → 2026-08-28, which
`journal-pid1-full.txt` still covers; the capture has it. What is *not*
recoverable, ever again from the box, is anything before 2026-08-25T12:57:42Z.

## 8. Predictions scored

Bank: `nuc/predictions-e-round478.md`, commit `dd1aa82`.

| | prediction | conf | outcome |
|---|---|---|---|
| P1 | `Persistent=no` | 0.80 | **HIT** — both timers |
| P2 | all 8 doomed files still present | 0.75 | **HIT** |
| P3 | no `sa02` | 0.85 | **HIT** |
| P4 | `sa01` last record 18:10–18:30Z | 0.80 | **HIT** — 18:20:00Z |
| P5 | `sa03` first record 09:37–09:50Z | 0.85 | **HIT** — RESTART 09:37:18Z, first sample 09:40:29Z |
| P6 | boot table gains exactly one row | 0.60 | **HIT, and incomplete** — see below |
| P7 | no clean shutdown for the 09-01 disappearance | 0.55 | **HIT**, and true of all four |
| P8 | exactly 11 `sa??` files, named | 0.60 | **HIT** — exact list |
| P9 | both user units active, started by the boot | 0.70 | **HIT** — 09:37:19Z, `NRestarts=0` |
| P10 | `dose_response` full-record windows 28 → ≥30 | 0.50 | **HIT** — 30, see §9 |
| P11 | tar 1.5–6 MB | 0.65 | **HIT** — 5 355 520 B |
| P12 | `audit --strict` exits 0 first try | 0.40 | **MISS** — exit 1, 2 blocking gaps |

**P6 is the interesting one and it is scored as a hit that missed the point.**
The table did gain exactly one row, as predicted. It also *lost three*, which
the prediction did not consider at all — §7. A prediction phrased as "gains
one row" cannot fail on a table that is being truncated from the other end.
The lesson is the shape, not the score: **a prediction about a monotone
quantity is blind to the direction the quantity is not monotone in.**

**P12 is a clean miss and the reason is worth keeping.** `audit --strict`
exited 1 with two blocking gaps: no `systemd[1]` line dated day 23 or day 24
to pair with `sa23`/`sa24`. That is not a filtered capture — it is §7 again.
The journal no longer reaches those days, so the gap is `only-on-box`
recoverable and the box no longer has it either. The audit is right to block;
what it is reporting is a permanent loss, not a repairable capture.

Score: **11 hits, 1 miss** of 12,
against a mean stated confidence of 0.68. That is well-calibrated on
direction and *over*-cautious on magnitude — the four predictions at ≤0.60
(P6, P8, P10, P12) were the ones carrying the real uncertainty, and two of
them turned on facts the bank had not thought to ask about.

## 9. P10 — the record-coverage question

See the measurement block below; run after the capture, with the new
`sar-all.txt` and `journal-pid1-full.txt` in place.

**P10 is a HIT, and the A/B behind it is the sharper result.**
`dose_response.py run` over the same 54 E rounds, changing only the capture:

| | r424 capture | r478 capture |
|---|---|---|
| `n_scored` | 42 | **44** |
| `n_full_record` | **28** | **30** |
| `n_partial_record` | 4 | 3 |
| `n_no_record` | 10 | 11 |

The r424 column reproduces round 472's published 42/28 exactly, which is what
makes the comparison trustworthy.

**But the new capture is not a superset.** Pooled days:

```
r424: 08-23 08-24 08-25 08-26 08-27 08-28 08-29 08-30 08-31 09-01
r478:             08-25 08-26 08-27 08-28 08-29 08-30 08-31 09-01 09-03
gained: 2026-09-03
lost  : 2026-08-23, 2026-08-24
```

`sa23` and `sa24` are *in* this capture — they are the files the round rushed
to rescue. They drop out of the pooled window anyway, because attribution
needs a fire **and** a bucket in the same window and the journal no longer
reaches those days (§7). That is the same fact `audit --strict` blocked on in
P12, arriving from the analysis side.

**So the correct unit of analysis is the UNION of captures, not the newest
one.** Every round from 400 onward that ran `dose_response` against "the
capture" was silently choosing a window. Nothing in the tooling says so.

**The conclusion does not move.** With n=30 instead of 28 the verdict string
is unchanged — `NULL: no dose reaches p<=0.05` — `dose_beats_every_control`
is still `false`, and the strongest dose is still `bytes_landed`. `n_logins`
goes rho 0.2568 → **0.2881**, p 0.185 → **0.121**: same sign, same story,
still not significant. Round 472's headline replicates on two extra windows.

## 10. What was built

**`nuc/summary_fossil.py`** — pure text-in/dict-out, opens no socket, cannot
reach port 8001. Three subcommands:

* `fires` — per-day verdict on the summary fire, with the fire time-of-day
  **derived from the receipts** rather than hardcoded to 00:07 (round 448's
  rule), a `settle_s` grace so a capture taken seconds after midnight cannot
  manufacture an outage, and explicit `no_day_file` / `orphan_receipts` /
  `compressed_not_scored` / `day_file_month_mismatch` residual classes.
* `crosscheck` — score against `journalctl --list-boots`, with
  `boot_table_too_short` for fires the table can no longer reach (§7 makes
  that a live category, not a hypothetical). `--strict` exits 1 on any
  disagreement.
* `blindspot` — how tightly this program's own probe log brackets each fire.

**`nuc/tests/test_summary_fossil.py`** — 42 tests.

### Two defects the tests found in the module, not the other way round

1. **`Counter.most_common` broke a tie by `ls` ordering.** With two receipts
   at different times of day it picked the later one and scored a real receipt
   1 920 s "early". Fixed to sort by `(-votes, time)`, and
   `test_a_tied_schedule_vote_is_broken_deterministically_and_is_visible`
   re-runs the input reversed to prove order-independence.
2. **The pending/missed boundary was unpinned.** Found by mutation, not by
   review: `fire > now` → `fire >= now` **survived the first mutation pass**,
   which is the definition of untested behaviour. The unpinned direction is
   the one that invents an outage from a capture taken a second after
   midnight. Fixed with an explicit `DEFAULT_SETTLE_S = 600` window (one
   collect interval), tunable, and pinned at all four edges.

### Mutation results

Round 472's lesson — first-run green does not reveal an unfalsifiable test —
applied to this module's own falsifiers. **First pass: 12 mutations, 11
killed, 1 survived** (the boundary above). After the fix, **second pass: 14
mutations, 14 killed, 0 survived.** The mutation list lives in the test file
as `MUTATIONS`, and `test_mutation_list_is_honest` fails if it names a test
that does not exist.

## 11. Tests

```
$ python3 -m pytest nuc/tests -q
1037 passed in 220.22s (0:03:40)
```

Round 472 left the suite at **995**. The delta is **+42**, exactly
`test_summary_fossil.py`; nothing else moved, nothing regressed. `nproc` on
this box is 1, so the suite was run alone — the round's one attempt at
overlapping it with an analysis job was abandoned for that reason.

The new module alone:

```
$ python3 -m pytest nuc/tests/test_summary_fossil.py -q
42 passed in 0.32s
```

Mutation pass, second run (`/tmp/mutate_fossil.py`, 14 mutations, each
reverted after its test): **14 killed, 0 survived.**

## 12. Next E round, in order

1. **`coverage --strict`, `precision-audit --strict`, `lastseen-drift
   --strict` FIRST**, exit codes from the process and not through a `| tail`.
2. **If the box is up, take a capture even if the round does nothing else
   with it.** §5d is the argument: round 400's capture answered a question
   nobody asked until round 478, and §7 is the deadline — journald is eating
   its own front and `sar` has a hard 7-day horizon. A capture is 40 seconds
   and 8 MB.
3. **`sa23`-`sa26` and `sar23`-`sar26` are gone from the box after
   2026-09-04T00:07:00Z.** `state/nuc-capture-r478/sysstat-binary.tar` is the
   only remaining copy. Do not let a later round conclude they are still
   fetchable because a forecast said "next run".
4. **Re-run `summary_fossil.py fires` on every future capture and append to a
   durable ledger.** Right now the verdicts are recomputed from whichever
   captures happen to be on disk; once `sa29` rotates away, the
   `2026-08-30T00:07Z` miss is only recoverable from a capture, exactly like
   the journal interior in §7. The fossil should become a JSONL log the way
   reachability did.
5. **Round 472's items 2, 3 and 4 are UNTOUCHED by this round** and stand:
   deconfound the lead-lag shoulder with a per-round-window resampling;
   `lead_lag_profile` still has no null; `test_perturbation.py` has still
   never been mutation-tested while carrying every published number in this
   track. This round mutation-tested only its own new module.
6. **Round 436's items 4, 5 and 9 stand, untouched for a sixth round** — the
   `commit` channel vs the 9.25 GB weights load, `Consumed` coverage at 4 of
   26 units, and the separability route.
7. **The `--cap 196` decision is still blocked on the operator** (band
   [129, 204], `bounded_by: engine_lru`, 1.096 GB margin — **twenty-seventh**
   round unchanged), as is the E3 A/B with its six-gate table. One new datum
   for whoever decides it: 7 h 33 m into this boot with no engine traffic the
   box is at **15.2 % memory, `Committed_AS` 5.4 GB, swap entirely free** —
   the "36.0 GB at `--cap 256`" figure from E4 is steady-state-after-traffic,
   not at-rest, and the band was derived under the at-rest reading.
8. **E-mission status: E1-E5 all still DONE; nothing new unchecked.**

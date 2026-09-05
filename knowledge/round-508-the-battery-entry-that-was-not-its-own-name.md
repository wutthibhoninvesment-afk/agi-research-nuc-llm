# Round 508 — NUC-integration(E) — the battery entry that was not its own name

**2026-09-05. Box DOWN the whole round** — fourth consecutive down E-window
(490, 496, 502, 508), one continuous outage. All work below is offline, on
records already committed to this repo.

## 0. Reachability, first, before any code ran

* Two tailnet probes, `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111`, at
  **11:27:41Z** (`ConnectTimeout 25`) and **11:28:19Z** (`ConnectTimeout 30`).
  `Connection timed out`, **rc 255** both. CLAUDE.md's two-failure rule fired
  after the second and no further box contact was attempted.
* The LAN path was NOT tried, for the reason rounds 472-502 record and this
  round re-verified: `~/.ssh/id_ed25519_nuc` does not exist on this host
  (`No such file or directory`), so a third probe would prove nothing.
* `tailscale status --json` banked at
  `state/nuc-capture-r508/tailscale-status-r508.json`: `Online false`,
  **`LastSeen 2026-09-04T02:14:05.1Z`**, relay `sin`, tx 6396 rx 0. That
  `LastSeen` is **byte-identical to rounds 490, 496 and 502**, so this is one
  outage, ~33.2 h old at first probe, not four.
* Row appended with `replay`, `source: live-replay-r508`, `precision:
  precise`. The log is now **69 rows**; the current down streak is 4 checks,
  `elapsed_upper 33h15m03s`, still **short of** the longest completed
  same-verdict streak (39h09m12s max-possible).
* Gates, run FIRST per round 472's item 1 and again after the append,
  identical both times: `coverage --strict` **0**, `coverage --strict
  --no-allow-in-flight` **0** (round 502's next-step #6: run the flag, do not
  remember it), `precision-audit --strict` **0**, `lastseen-drift --strict`
  **1** — the documented 436-vs-472 disagreement, unchanged.
* **Zero ssh sessions succeeded. Nothing was read from or written to the box.
  Port 8001 was never contacted. No engine request of any kind was made.**
* E-missions E1-E5 all still DONE; nothing unchecked.

## 1. The headline: a battery entry that ran a different channel than its name

Round 502 built `nuc/survivor_impact.py` to re-run "the module's own published
verbs" per mutation survivor. Its `BATTERY` had five entries. Running all five
against `state/nuc-record-union` and hashing the output:

```
window_swap      rc=0  md5 53d70fba3eb0   78188 bytes
population_swap  rc=0  md5 208968f1e4f3   10061 bytes
wsweep_swap      rc=0  md5 31b8b34f8e9d   35703 bytes
wsweep_commit    rc=0  md5 325d889c59f9   33326 bytes
wsweep_steal     rc=0  md5 31b8b34f8e9d   35703 bytes     <-- identical
```

`wsweep_swap` and `wsweep_steal` are **byte-identical**, and the shared bytes
contain `"channel": "steal"`. The entry was

```python
("wsweep_swap", ["wsweep", "--capture", "{capture}"]),
```

— no `--channel`. And `wsweep` is the **one** `perturbation.py` subcommand
whose `--channel` defaults to `steal`; of the twelve subcommands that take the
flag, **ten default to `swap`** and one (`gap`) to `commit`. Run explicitly:

```
wsweep --channel swap   md5 dfbc9d8d65b5   32002 bytes    <-- never produced before
```

**The battery advertised five published verbs and ran four**, with the steal
channel counted twice and **the swap channel — the only one with a derived
costly-threshold, and the channel every published number in this track is
computed on — never run at all.** Round 502's classification of 32 mutation
survivors into five kinds was made with that battery.

The generalisable shape: **a battery entry that omits a flag is asserting a
default it did not check**, and a suite of "distinct" commands can contain two
copies of one command without anything saying so. The falsifier is cheap and
now committed: `test_no_two_battery_entries_are_the_same_command` plus
`test_every_battery_entry_that_can_take_a_channel_names_one`. There is also a
third test that pins `wsweep`'s default AS `steal`, so that "fixing" the
default is a decision somebody makes on purpose rather than a silent
re-interpretation of every argv in the repo.

Fixed: every entry names its channel; `reclaim`/`gap` added (§2); the battery
is **5 -> 7** entries and `BATTERY_GAP` **9 -> 7**.

## 2. `reclaim`/`gap` could read NO capture — it was never about the union

Round 502 recorded the exclusion as a property of round 490's union:

> `reclaim`/`gap` take a SINGLE sar table (`--sar-b`), and the union's
> `sar-all.txt` is 120 sections: rc 1, "header changed mid-table".

Measured this round, the same call against every record in the repo:

| record | `reclaim --sar-b <its sar-all.txt>` |
|---|---|
| `state/nuc-capture-r400` | rc 1, header changed mid-table |
| `state/nuc-capture-r424` | rc 1, header changed mid-table |
| `state/nuc-capture-r478` | rc 1, header changed mid-table |
| `state/nuc-capture-r484` | rc 1, header changed mid-table |
| `state/nuc-record-union`  | rc 1, header changed mid-table |

**0 of 5.** `nuc-capture-r424` is the capture every published number in this
track was computed from. The verbs have never been able to read a capture;
round 418 ran them on two files it hand-extracted into `B31.txt`/`R31.txt` and
nothing has run them since. Naming the union as the cause pointed the next
round at the newest artefact instead of at the two verbs.

Section census (`sar_sections`), for the record:

```
union  120 sections  SAR_{B,CSW,DEV,IO,NET,Q,R,SWAPSPACE,U,W} x 12 days
r424   101           the same ten kinds x 10 days + SYSSTAT_FILES
r478   111           x 11 + SYSSTAT_FILES
r484    81           x  8 + SYSSTAT_FILES
r400    21           irregular: SAR_B x2, SAR_R x9, SAR_W x9 + SYSSTAT_FILES
```

**New `capture_day_tables(sar_text, prefix)`** walks the sections, dates each
from its own `Linux ... MM/DD/YY` banner, and keeps `window_frame`'s check
that a section named `SAR_B_SA31` whose banner says the 30th is a rejection,
not a silently mis-dated day. `window_frame` now calls it — one place does
section -> date — and the refactor is proved inert: `window`, `population`,
`wsweep --channel steal` and `wsweep --channel commit` are **byte-identical**
to baselines taken before the edit.

`reclaim --capture DIR [--date D]` and `gap --capture DIR [--date D]` now
exist, with `--sar-b`/`--sar-r` still accepted for a hand-extracted table, the
two input styles mutually exclusive, and a `--date` the capture does not hold
raising an error that NAMES the dates it does hold (an empty result would read
as "this day had no reclaim").

## 3. What the record says once the verbs can read it — and round 418's two
days were not a sample

`reclaim --capture state/nuc-record-union`, 12 days, 1145 buckets:

```
2026-08-23  58 buckets  14 loud   7 direct/mixed   110.0 GB stolen
2026-08-24 143          17        1                 30.3 GB
2026-08-25 140          12        0                  9.0 GB
2026-08-26 143          30        0                164.0 GB
2026-08-27  99          13        0                 14.6 GB
2026-08-28 143          11        0                  3.7 GB
2026-08-29  13           2        0                  0.14 GB
2026-08-30 139           4        0                 22.1 GB   <- round 418's day
2026-08-31  98           5        0                  2.6 GB   <- round 418's day
2026-09-01  76           0        0                  0
2026-09-03  85           0        0                  0
2026-09-04   8           0        0                  0
------------------------------------------------------------
pooled    1145         108        8                356.4 GB reported
```

Three of round 418's conclusions do not survive the other ten days:

* **"No allocation ever stalled."** Round 418: *"`pgscand/s` — direct reclaim,
  the path where an allocation waits — is 0.00 in every bucket of both days."*
  Over the union there are **8 mixed buckets with non-zero `pgscand/s`**, seven
  of them on 2026-08-23 (peak `scan_d 3217.07/s` at 18:20:01) and one on
  08-24. Direct reclaim is real on this box; it is confined to two days, and
  neither is one of the two days that were hand-extracted.
* **The largest reclaim bucket is not 08-31's.** Round 418 quoted
  `987,217,920 B` at `04:00:03` on 08-31 as `largest_bucket`. The union's
  largest is **2026-08-26 14:10:21, 49,667,825,664 B reported** — fifty times
  larger — and `24,833,912,832 B` after `reclaim_double_count_check`'s
  divisor-2 correction (`vmeff_reported 199.84 %` -> `99.92 %`).
* **`steal_exceeds_scan` is not rare, it is the norm**: **87 of 108** loud
  buckets, plus 21 `scan_free_steal`. This is the standing `%vmeff` residual
  showing up as a majority phenomenon rather than a curiosity, and it is now
  visible without touching the box — which matters, because that residual has
  been carried as "one read-only command away" for nine E rounds and the box
  has been down for four of them.

`gap --capture state/nuc-record-union --channel commit`, 108 rows over 9 days
(the three zero-reclaim days contribute none), every `SAR_B_` day paired with
its own `SAR_R_` day:

```
n_rows 108   n_level_undefined 1   n_level_zero 46   fraction_level_zero 0.4299
median_ratio 0.00187   max_ratio 163.28
```

Round 418's conclusion — the commit channel is **blind, not coarse** — holds,
but not by the statistic I predicted. Only 43 % of reclaim buckets have a
commit cost of exactly zero; the median bucket's commit cost is **0.19 % of
the bytes reclaimed there**. Blindness shows in the ratio, not in the count of
exact zeroes.

## 4. The refusal that blamed the record

`window --channel commit` on the union exits 1 with

> channel 'commit' has no derived costly-threshold **on this record** (see
> CHANNEL_MIN_BYTES)

and round 502 wrote that down as `"rc 1 on this record: no derived
costly-threshold"`. But `CHANNEL_MIN_BYTES = {"swap": 4825665, "commit": None,
"steal": None}` is a **module constant**, and the raise is a dict lookup that
never reads the record it is describing. No record can satisfy it, and the
same record satisfies the verb the moment a flag that has existed all along is
passed:

```
window --capture state/nuc-record-union --channel commit --min-bytes 4825718  -> rc 0
window --capture state/nuc-record-union --channel steal  --min-bytes 4825718  -> rc 0
```

The *design* refusal is right and stays: round 412 and 418 declined to invent
a threshold for `commit`/`steal` because this record carries no bucket
independently labelled noise to pair against a smallest real event, and a
threshold invented there would BE the result. What was wrong was the message's
**subject**. It now names `CHANNEL_MIN_BYTES`, says out loud that the raise
never read the record, and the `BATTERY_GAP` entries say the same. The two
`window_*` exclusions are KEPT — `wsweep`, which sweeps thresholds, is the
right verb for those channels — but they are now recorded as a design refusal
plus an unpassed flag, not as a fact about a record.

## 5. Tests

`nuc/tests/test_capture_verbs.py`, **35 nodes, 3.22 s** under `.venv`, all
green. Regression run of the affected suites: `test_perturbation.py`,
`test_survivor_impact.py`, `test_record_union.py`,
`test_lead_lag_blocks.py` — **347 passed, 2 failed in 56.67 s**, and both
failures are this round's own doing:

* `test_settrace_resolves_individual_lines_of_a_multi_line_expression` pins
  the LINE NUMBERS of `power_floor`'s two `why` branches, and rewriting the
  refusal message 236 lines above them moved both by +4. Re-pinned
  (1651/1654 -> 1655/1658) with a note that a round shifting `perturbation.py`
  must expect to re-pin here. **Green after.**
* `TestThisTree::test_the_committed_report_is_about_the_subject_at_head`
  compares the committed survivor-impact report's `subject_digest` against
  `perturbation.py` at HEAD. Editing the subject expires it, by design.
  **LEFT RED, deliberately** — see §7 item 1. The digest moved `3b3923df…` ->
  `8082749f…` is the report's, and the file now hashes to `3b3923df…`; the
  87-row mutation ledger is keyed on the old digest too, so round 502's
  campaign is now stale against HEAD.

**Not run, and named rather than implied:** the full `nuc/tests` suite
(round 490 measured 564 s at 1131 nodes; `nproc` is 1), the before/after
`survivor_impact` audit, and any mutation testing of this round's own code.
The audit was attempted and **exceeded 600 s on 5 survivors** before being
killed — the measured reason it was dropped, not a guess. This round ran
inside a 3300 s wall-clock cap and spent it on the findings.

## 6. Predictions scored — 8 HIT, 5 MISS, 1 PARTIAL, 1 UNSCORED of 15

Banked in `nuc/predictions-e-round508.md`, committed as `e6291c3` before any
of it was measured.

**THE FIVE MISSES ARE ONE ERROR, and it is the round's own subject.** P5, P6,
P7, P8 and P9 all extrapolate the 12-day record from the two days round 418
hand-extracted — the exact move §2 exists to criticise. I noticed that a
hand-extracted pair had never been re-derived, built the tool that reads all
twelve days, and then predicted the twelve from the two.

* **P5 MISS.** Predicted `n_direct_reclaim_buckets == 0` across all 12 days
  ("round 418's negative generalises"). Measured **8**, all on 08-23/08-24.
* **P6 MISS.** Predicted 15-60 loud buckets. Measured **108**.
* **P7 MISS.** Predicted 08-31's 987,217,920 B stays the record maximum.
  Measured max **49,667,825,664 B on 2026-08-26**, 50x bigger.
* **P8 MISS.** Predicted `n_steal_exceeds_scan == 0`. Measured **87 of 108**.
* **P9 MISS.** Predicted >= 60 % of reclaim buckets at `level_bytes == 0`.
  Measured **43.0 %** — the conclusion survives on the median ratio (0.0019),
  the statistic I chose does not.
* **P1 HIT.** `reclaim --sar-b` on r424 raises the identical error.
* **P2 HIT.** 0 of 5 records readable.
* **P3 HIT.** Exactly 12 `SAR_B_*` and 12 `SAR_R_*` sections in the union.
* **P4 HIT.** `--min-bytes` lifts the refusal, rc 0 on both channels.
* **P10 HIT.** The "on this record" framing appears outside `BATTERY_GAP` at
  the raise site, `perturbation.py:1342`, `test_perturbation.py:809`,
  `knowledge/round-412:335` and `knowledge/round-502:108`. (Fair to round
  412: *its* sentence is about a labelled noise/real pair genuinely absent
  from the record, which is true. The defect is the RAISE inheriting that
  wording while consulting a constant.)
* **P11 HIT.** Battery 5 -> 7, `BATTERY_GAP` 9 -> 7, the two `window_*`
  entries kept and re-worded.
* **P12 PARTIAL.** 35 new test nodes (predicted 25-40, HIT); the full-suite
  wall clock was never measured (see §5), so the [560, 700] s half is
  **unscored, not passed**.
* **P13 UNSCORED.** No mutation run this round. This is the fourth
  consecutive E round to leave `test_perturbation.py` un-mutation-tested and
  the first to also skip mutating its own new code; recorded as a debt, not
  as a pass.
* **P14 HIT.** Three days (09-01, 09-03, 09-04) parse cleanly and contribute
  only denominator.
* **P15 HIT.** Zero ssh sessions, port 8001 never contacted, both `coverage`
  gates 0.

## 7. What the next E round should take, in order

1. **This round left one test red on purpose and it is mechanical.**
   `test_survivor_impact.py::TestThisTree::test_the_committed_report_is_about_
   the_subject_at_head`. Regenerate with `python3 nuc/survivor_impact.py --out
   state/swe/perturbation-survivor-impact.json` and re-score the 87-row
   mutation ledger, whose rows are keyed on the superseded digest `8082749f…`.
   **Budget it: >600 s for 5 survivors with the OLD 5-verb battery; the new
   battery is 7 verbs, so ~40 % more.** The interesting number is whether any
   of the 5 standing survivors changes verdict now that the swap channel is
   actually in the battery — nobody has ever run it against them.
2. **Every published `survivor_impact` number from round 502 was produced by
   a battery missing the swap channel.** The 32 -> 5 kill-rate story is not
   invalidated (the pytest oracle did that work) but the five-way
   CLASSIFICATION was made on four verbs, one of them counted twice. Re-run
   §1's audit before quoting round 502's kinds again.
3. **The `%vmeff` residual is no longer one command away from the box — it is
   87 buckets in a file already committed.** `steal_exceeds_scan` on 87 of 108
   loud buckets, `scan_free_steal` on 21, `reclaim_double_count_check`'s
   divisor-2 correction already implemented and already halving a 199.8 %
   `vmeff`. Nine E rounds have deferred this to an SSH session. It can be
   settled offline now, and it should be, because the correction is a
   DIVISOR SOMEBODY CHOSE and 87 buckets is enough to test it against
   `pgsteal_kswapd` if a future capture carries that column.
4. **Direct reclaim exists on this box and it is confined to 2026-08-23/24.**
   Seven mixed buckets in eight hours on one day, then one, then never again
   in ten days. That is a shape worth an explanation — what ran on 08-23 —
   and the journal for that date is in the union.
5. **`gap` pairs `SAR_B_` with the level channel's own prefix by DATE, and on
   this union nothing was unpaired.** That will not stay true: r400 is
   irregular (2 `SAR_B` against 9 `SAR_R`) and `dates_without_a_level_table`
   exists to catch it. Run `gap --capture state/nuc-capture-r400` and see what
   the field is for.
6. **Round 502's items 3 and 6 are CLOSED** (6 by running both `coverage`
   forms this round; 3's cost is now measured at >600 s / 5 survivors, in
   item 1). Round 490's items 3, 4, 5 and 6 stand, untouched. Round 502's item
   7 is item 7 below.
7. **Standing and untouched:** the NUC `retention --strict` deadline;
   the operator-blocked `--cap 196` (band [129, 204], **thirtieth** round
   unchanged) and the E3 A/B; and CLAUDE.md's `CRITICAL MISSION` and `MASTER
   MISSION` blocks, still a one-block deletion for the operator. The box has
   now been down since `2026-09-04T02:14:05.1Z` across four E rounds, and
   `~/.ssh/id_ed25519_nuc` is still absent on this host, so the LAN path
   remains untestable rather than failing.

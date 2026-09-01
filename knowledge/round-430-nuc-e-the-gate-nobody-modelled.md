# Round 430 (NUC-integration E) — the gate nobody modelled, and the correction nobody re-ran

**Date:** 2026-09-01 · **Track:** E (NUC integration) · **Box:** `pgain-nuc`,
**UP**, boot `f13afb47`, `uptime -s 2026-09-01 05:33:27Z` — the **same boot**
round 424 saw, 8 h 20 m in at first contact. Second consecutive up round.

**Predictions banked before measurement:** `nuc/predictions-e-round430.md`
(D-013). Scored in §9: **15 HIT · 1 PARTIAL · 5 MISS of 21**, plus 3 hygiene
commitments kept.

**Agenda:** round 424's next-E-round list, items 1-5.

---

## 0. One-paragraph summary

Every ledger, evidence, sweep and power-floor number this program has ever
published was computed on **two of nine** banked `sar` day-files, on a
**one-boot** journal. Round 424 banked a nine-day journal; round 430 built the
instrument that pools the whole window and ran it. **N 218 → 991, K 3 → 52,
16 units → 26, testable occupancy band 2..97 → 3..881.** `supported: []`
survives — and the *reason* it survives is new and is a defect in this
program's own instrument: `attribution_evidence` has **six** gates, round
412's `power_floor` models **one**, and on the full window the pass sets of
`separable` and `chance` are **disjoint**. Three units are one gate from
`supported` and the gate is separability. Separately, running round 424's
`pgsteal` factor-of-two correction over all ten day-files instead of the two
anyone had opened returns **`ceiling_restored: False`** — 21 buckets stole
pages with **zero** scanned — and the missing term was in the same banked
evidence file, one section below the one round 424 read.

---

## 1. Reachability and retention (round 424 item 1 — CLOSED, and it is now a
##    standing first action)

`reachability_check check --round 430` at **2026-09-01T13:53:02Z**: ssh rc 0 on
the tailnet path `jab@100.78.44.111`, `tailscale_online true`,
`boot_utc 2026-09-01T05:33:27Z`, `slept_this_boot false`. Same boot as round
424 (`f13afb47`), so the 406/412/418 outage remains the last one and the box has
now been up ≥ 8 h 20 m on this boot with no sleep.

Round 424 said: *run `capture_manifest.py retention` first, every up-round.*
Done, and it exits 1 as designed:

```
$ python3 nuc/capture_manifest.py retention --capture state/nuc-capture-r424 \
    --next-run 2026-09-02T00:07:00Z --now 2026-09-01T13:54:45Z --strict
n_deleted_at_next_run: 4   [sar24, sa24, sar23, sa23]
EXIT=1
```

All four are inside `state/nuc-capture-r424/sysstat-binary.tar.xz`. **The
exit-1 is a deadline notice, not a loss** — this is what a strict retention
check should feel like on a round where nothing is at risk.

Live inputs, from one read-only ssh: `systemctl list-timers` gives
`sysstat-summary.timer` next at **Wed 2026-09-02 00:07:00 UTC** (predicted
±2 min — exact); `/var/log/sysstat/` holds **the same 17 filenames** round 424
saw, no `sar29`/`sar31`/`sar01`; `HISTORY=7`, `COMPRESSAFTER=10`, `ZIP=xz`
unchanged. `sa01` has grown **36 324 → 111 124 B**.

### 1a. `survives_until_utc` was a day early, always in the alarming direction

The field was `mtime + (HISTORY + 1) days` — the instant `find -mtime +7`
starts matching. That is when a file becomes **sweepable**, not when it is
**swept**: `sa2` runs only when `sysstat-summary.timer` fires at 00:07, so a
file eligible at 23:50 lives another 17 minutes and one eligible at 08:10 lives
**sixteen hours**. The field was named `survives_until` and read as a deletion
time, so every capture deadline taken off it has been early by up to a day.

`retention_forecast` now emits both, plus the pair that dies together:

| field | value on the r424 capture |
|---|---|
| `earliest_sweepable_utc` | `2026-09-02T23:50:00Z` (`sa25`) |
| `earliest_loss_utc` | **`2026-09-03T00:07:00Z`** |
| `next_files_lost` | `["sa25", "sar25"]` |

`survives_until_utc` is kept as an alias so nothing on disk orphans.
`_next_sweep_at_or_after` derives the fire series from the one fire the caller
passes rather than a hardcoded `00:07`, so a box whose timer moves does not
silently keep the old answer. And the answer is still an *earliest possible*
deletion: a box that is DOWN at 00:07 does not sweep, which is the only reason
`sa23` survived to be captured at all (round 424).

**Standing action for every up E round: run `retention --strict` first.** The
archive rolls off at one day-file pair per 00:07 fire and the current window
ends `2026-09-10T00:07:00Z` (`sa01`).

---

## 2. The full window (round 424 item 2 — the headline)

### 2a. The instrument, and why it had to carry a frame

The library could already pool days — `attribution_evidence(ledgers)` takes a
list, `channel_sweep` takes `(table, date)` pairs, `auto_stitches` joins
consecutive files. What did not exist was any way to get from a capture to
those inputs. The splitter lived in `nuc/tests/test_perturbation.py` as
`_sar_sections`, a test helper, from round 418 to round 429. **Three rounds of
analysis reached nine days of banked data only through a test file, and used
two.**

New: `perturbation.py window --capture DIR`. It is not just a loop, because
widening a window is a **false-positive** hazard and not the conservative move
it looks like:

> `attribution_evidence` pools N over its ledgers and tests each unit's `d`
> costly hits against a hypergeometric null on `(N, K, n_distinct)`. A day whose
> `sar` table is present but whose **journal is silent** contributes buckets to
> N and fires to nothing. N rises, the null gets more diffuse, and every
> surviving unit's `p_chance` **falls** — so pooling an unpaired day makes an
> attribution look *more* significant on strictly less evidence.

That is round 412's finding ("the journal, not `sar`, bounds attribution")
turned into a gate. `window_frame` pairs each day-file against the journal
before anything is pooled, and — per `skills/elimination-needs-its-frame`
(round 429) — derives the day list from the capture's **own** section headers
and each date from that section's **own** `Linux ... MM/DD/YY` banner, not from
the `SA<DD>` filename. A banner/name disagreement raises rather than booking a
day of buckets against the wrong date. `SA01` is September and nothing in its
name says so.

### 2b. The frame, published

```
n_day_files 10 · n_paired 10 · n_sar_only 0 · n_journal_only 0
journal 2026-08-23T14:03:06Z → 2026-09-01T08:10:02Z · 1652 unit fires
  (1005 of them `sysstat-collect`, the instrument, excluded → 647 testable)
n_buckets_poolable 991 = n_buckets_if_unpaired_pooled 991
```

`--inflation` runs it both ways and comes back **empty** — `n_dropped_days 0`,
`units_whose_p_moved []`. That is the function earning its keep by having
nothing to say: **the pooled N was not bought by counting buckets from days the
journal cannot see.**

Per-day ledger, swap channel, `min_bytes 4 825 665` (round 400's derived
threshold, unchanged):

| date | buckets | costly | fires | unclassified | total cost |
|---|---|---|---|---|---|
| 2026-08-23 | 58 | 8 | 18 | 6 | 14.40 GiB |
| 2026-08-24 | 143 | 11 | 41 | 0 | 9.54 GiB |
| 2026-08-25 | 140 | 3 | 45 | **154** | 0.18 GiB |
| 2026-08-26 | 143 | 13 | 56 | 0 | 4.84 GiB |
| 2026-08-27 | 99 | 4 | 28 | 59 | 1.29 GiB |
| 2026-08-28 | 143 | 7 | 42 | 0 | 0.86 GiB |
| 2026-08-29 | 13 | 1 | 6 | 0 | 0.04 GiB |
| 2026-08-30 | 139 | 1 | 35 | 62 | 0.01 GiB |
| 2026-08-31 | 98 | 4 | 30 | 0 | 0.38 GiB |
| 2026-09-01 | 15 | 0 | 8 | 57 | 0 |
| **pooled** | **991** | **52** | **309** | **338** | **31.53 GiB** |

**338 of 647 non-instrument fires (52 %) are `unclassified`** — a fire on a day
whose `sar` file does not cover that minute, i.e. inside a reboot or an outage.
They are reported, never counted as free, and 08-25 alone contributes 154
because that day held three reboots.

Two of round 400's headline days are the *quietest* in the window: sa30 has
**one** costly bucket and 6.8 MB of total cost. The busy days — 08-23, 08-24,
08-26 — carry 28.78 of the window's 31.53 GiB and had never been opened.

### 2c. The result

```
N 991 · K 52 · units 26 · testable 17 · supported []
power: occupancies 3..881 clear the bar — 88.7 % of N (was 2..97, 44.0 %)
by_verdict: coincidence 3 · shared-only 9 · no-evidence 7 · insufficient-data 7
```

`supported: []` for the fifth consecutive round — **and this is the first time
the empty list has been produced by an instrument that could plainly have
filled it.** Round 406 had no power. Round 412 showed round 406 had no power.
Round 418 got the first powered null on one channel. Round 430 has 88.7 % of
the record inside the testable band and four units clearing the chance bar.

---

## 3. Why `supported` was empty — a gate `power_floor` cannot see

`attribution_evidence` runs six gates in order and a unit must pass all six.
Round 412 built `power_floor` for **gate 4**. It reports
`supported_was_reachable: True` here, truthfully, about gate 4 — and readers
have taken that for the whole claim, which is strictly stronger.

New `verdict_floor()` runs every gate and intersects the pass sets:

| gate | rule | passed | who |
|---|---|---|---|
| min_fires | ≥ 2 fires | 19 | |
| any_costly | ≥ 1 costly bucket | 15 | |
| **separable** | ≥ 1 costly bucket held **alone** | **3** | `fwupd-refresh`, `man-db`, `motd-news` |
| testable | round 412's power floor | 17 | |
| **chance** | `p_family ≤ 0.05` | **4** | `apt-daily`, `apt-news`, `esm-cache`, `packagekit` |
| consistency | ≥ 50 % of own fires costly | 7 | |

**`separable ∩ chance = ∅`.** `all_gates_passed: []`,
`supported_reachable_all_gates: False`. And:

```
single_gate_from_supported: {"separable": ["apt-news", "esm-cache", "packagekit"]}
blocking_gate_histogram:    {"separable": 9, "any_costly": 7, "min_fires": 7, "chance": 3}
```

**Exactly one gate stands between three units and a `supported` verdict, and it
is not power and not chance.** `packagekit` reaches `p_family = 5.35e-06` —
five orders of magnitude below the bar, the smallest p this track has produced
on any channel — with `consistency 0.636`. It is blocked solely by never having
been alone in a costly bucket.

The structural statement, which is the finding:

> **On a housekeeping box, a unit that fires often enough to be seen alone
> fires too often to be surprising, and a unit rare enough to be surprising is
> started by something else.** The two gates select disjoint populations.

`fwupd-refresh` is the proof of the first half and closes round 400's item 3 /
round 424's item 3 (*prove or drop the fwupd attribution*). Over nine days it
fires **166** times, holds **9** costly buckets alone — up from round 400's
"the only sole-attributable event of the boot" — and fails at `p_chance 0.144`:
occupying 166 of 991 buckets, covering 12 of 52 costly ones is *fewer* than
chance would give. **Consistency 0.072**, below round 418's 0.111 as predicted.
**Drop it.** This is a powered null: occupancy 166 is deep inside the 3..881
testable band.

### 3a. `packagekit` is the deployment's universal confounder

`costly_bucket_cofires()` asks who shares each costly bucket. 19 of the 52
costly buckets hold a named fire at all — **33 have none**, which is its own
frame fact and is consistent with round 418's note that the engine's own load
has no named unit behind it. Of the 19, 11 are sole-occupied and by only three
distinct units. The largest holds **nine**.

`never_without[u]` = the units present in *every* costly bucket `u` occupies:

```
apt-daily          -> apt-news, esm-cache, packagekit
apt-news           -> apt-daily, esm-cache, packagekit
esm-cache          -> apt-daily, apt-news, packagekit
apt-daily-upgrade  -> packagekit
fwupd              -> apt-daily-upgrade, modprobe@sd_mod, packagekit
...
packagekit         -> (no entry)
```

**`packagekit` is a one-way confounder of eleven other units and has none of
its own.** It sits in every costly bucket the apt and fwupd families occupy and
in two more besides. So nothing in either family can ever be sole-attributable
while it exists, and `packagekit`'s own cost cannot be separated either.

### 3b. The composite hypothesis, run honestly, still fails

When the blocking gate is separability the tempting move is to pool the
confounded units into one hypothesis. `inseparable_classes()` derives the
grouping from the **mutual** never-without relation — never from which grouping
would pass — and `cluster_evidence()` relabels and re-runs the same grader.
Both effects are real: the union occupies more buckets (hurts) against a looser
Bonferroni bar over fewer hypotheses (helps).

```
classes: apt-daily+apt-news+esm-cache (5 costly buckets, testable)
         fwupd+modprobe@sd_mod        (2, testable)
         systemd-networkd+systemd-udevd+udisks2+upower (1, NOT testable)
26 units -> 23 hypotheses · supported []
apt-daily+apt-news+esm-cache: costly 5, clean 0, p_family 0.00706 -> shared-only
```

Still `shared-only`, **because the confounding is directed**: `packagekit` is
in every bucket the trio occupies and in two more of its own, so merging the
trio cannot make it sole and cannot rescue `packagekit` either. The
`one_way_confounders` field exists to say that in the output rather than in
prose.

The four-unit class with **one** costly bucket is the trap the
`CLUSTER_MIN_COSTLY_BUCKETS = 2` guard exists for: on a single observation
"they always co-occur" restates the observation.

### 3c. The commit channel, for contrast

`--channel commit --min-bytes 4825665 --stitch`: `N 985, K 83`, seven days
stitched, two refused (`2026-08-30` and `2026-09-01` each follow a
`LINUX RESTART`, so the predecessor describes a different boot's address
space). **Zero** units pass the chance gate; `single_gate_from_supported: {}` —
here nobody is one gate away, everybody is blocked twice. The two channels fail
for genuinely different reasons and only the gate table shows that.

---

## 4. The correction that was validated where somebody happened to be looking

Round 418 found `%vmeff > 100` on six of seven reclaim buckets, proposed a
factor-of-two double count, and round 424 **confirmed the mechanism from the
collector binary**: `sadc` carries `pgscan_kswapd` / `pgscan_direct` as full
field names and `pgsteal_` as a bare **prefix** matching five fields that form
two complete partitions of the same events. Numerator doubled, denominator not.
`RECLAIM_STEAL_DIVISOR = 2`, `corrected_*` shipped beside the raw columns,
carried forward as CONFIRMED.

Every step of that is right. It was validated on **sa30 and sa31** — the two
day-files this track had ever opened. Over all ten:

| | reported | after ÷2 |
|---|---|---|
| reclaim buckets | 108 | 108 |
| over the 100 % ceiling | 66 of 87 scanned | **8** |
| stole pages with **zero** scanned | — | **21** |
| worst | 6107 % | **3053 %** |
| `ceiling_restored` | — | **False** |

Per day, and the shape is the point:

| day | reclaim buckets | scan-free | >100 % raw | >100 % corrected | restored |
|---|---|---|---|---|---|
| 08-23 | 14 | 5 | 5 | 1 | False |
| 08-24 | 17 | 11 | 5 | 2 | False |
| 08-25 | 12 | 2 | 10 | 2 | False |
| 08-26 | 30 | 0 | 20 | 1 | False |
| 08-27 | 13 | 3 | 9 | 2 | False |
| 08-28 | 11 | 0 | 9 | 0 | **True** |
| 08-29 | 2 | 0 | 0 | 0 | **True** |
| 08-30 | 4 | 0 | 4 | 0 | **True** |
| 08-31 | 5 | 0 | 4 | 0 | **True** |
| 09-01 | 0 | 0 | 0 | 0 | — |

**The four days on which the correction holds are the four most recent — the
window anyone had loaded.** `sa23 21:40:03` reads `pgscank/s 0.00,
pgscand/s 0.00, pgsteal/s 4087.96`: 2.4 GiB of pages stolen from a scan of
nothing. No divisor fixes `x/0`.

### 4a. The other half was in the same banked file

`state/nuc-capture-r424/collector-evidence.txt` has two sections. Round 424 read
`SADC_VMSTAT_LITERALS` (the numerator). Seven lines below,
`PROC_VMSTAT_RECLAIM_FIELDS` lists **`pgscan_khugepaged`**, and it is *not* a
sadc literal — while `pgsteal_` collects `pgsteal_khugepaged`. So:

```
numerator   = Σ pgsteal_*  = (kswapd + direct + khugepaged) + (anon + file) = 2T
denominator = pgscan_kswapd + pgscan_direct                                 = S − S_khuge

reported %vmeff = 2T / (S − S_khuge),  not  2T / S
```

Two consequences fall out and both are observed: whenever khugepaged does the
reclaiming the denominator loses ground the numerator keeps, so the residual is
**unbounded** rather than a second constant factor; and in the limit where
khugepaged does all of it the denominator is 0 while the numerator is not,
which is the scan-free bucket exactly. New `scan_undercount_evidence()` derives
this from the banked text — no box access, and none was available: **every
reclaim counter on the box reads 0 across the whole 8 h 30 m boot** (checked
again this round, `pgsteal_*`/`pgscan_*`/`pgdemote_*` all zero, ~20.3 GiB free),
so the direct kernel test is as vacuous now as it was for round 424.

**Round 424's finding is not overturned; it is scoped.** The double count is
real (pinned: sa30 and sa31 still return `ceiling_restored: True`). It is
*incomplete*, so `corrected_*` is an **upper bound** on true efficiency, and a
correction at all only on buckets where `pgscan_khugepaged` did not move.

### 4b. The checker could not have caught it, because it filtered the evidence

`reclaim_double_count_check`'s first line, unchanged since round 418:

```python
evs = [e for e in events if (e.scan_kswapd_s + e.scan_direct_s) > 0]
```

It drops **precisely** the buckets that violate the theorem it is testing, with
no count. `ceiling_restored: True` was computed on a set the counter-examples
had been removed from. Now: `n_scan_free_steal` and `scan_free_steal_buckets`
are output fields, and a non-zero count **blocks** the positive verdict.

`ReclaimEvent` also gains `scan_free_steal` and `vmeff_defined`, because
`vmeff_pct` is documented "0 if no scan" — so the 4 087 pages/s bucket renders
as **0.000 %**, sorting to the *bottom* of an efficiency ranking next to the
genuinely inefficient cases, which are the opposite finding.

### 4c. Round 424 item 4, answered by the same numbers

Round 424 asked what was pinned at 04:00 and not at 15:00, given that
`sa31 04:00:03` at 16.6 % was "the least efficient reclaim in the record". Over
ten days it is not: `sa23 18:20:01` reclaims 8.0 GiB at **27.4 %** with
`pgscand/s 3217.07`, and the whole-window totals are **166.0 GiB corrected**
(331.9 uncorrected) across 108 events, against round 424's 10.99 GiB over
seven. The 04:00:03 event is unremarkable in the full record; the question was
about a two-day sample.

### 4d. Direct reclaim DID happen — round 418's claim does not extend

Round 418: *"`pgscand/s` is 0.00 in every bucket of both days ... no allocation
ever stalled."* True of sa30 and sa31. Over ten day-files there are **8 buckets
with `pgscand/s > 0`**, seven on 08-23 and one on 08-24, peaking at
`pgscand/s 3217.07` (08-23 18:20:01). Allocations *did* stall on this box, on
the busy days nobody had opened. This was prediction **C5** and it is a **MISS**.

---

## 5. `sadf` and the boundary record (round 424 item 5 — CLOSED, retire it)

Reproduced on a second file. On `sa01`: `sadf -d` yields **51** distinct
timestamps, `sar -r` prints **52** stamped lines. Both consume the first record
as the rate baseline; `sar` stamps its column header with it (`05:40:12`) and
`sadf` drops it entirely. Round 424's result on sa01 was 16 vs 17 — the same
one-record difference, so the ratio was not an artefact of that file.

What `sadf` does carry is the true per-record interval in its own column:
**589, 601, 600, 600, …** — the first interval is 589 s, not the assumed 600.
`sar`'s rendering is the only place a reader ever sees the boundary record's
timestamp, and neither tool shows its data. **The 1200 s stitch stays; item 5
is closed as "sadf does not help, and here is the interval column instead".**

---

## 6. Artifacts

| path | change |
|---|---|
| `nuc/perturbation.py` | 1982 → **2749** lines. New: `sar_sections`, `sar_banner_date`, `WindowDay`, `window_frame`, `window_attribution`, `unpaired_inflation`, `verdict_floor`, `costly_bucket_cofires`, `inseparable_classes`, `cluster_evidence`, `scan_undercount_evidence`; `ReclaimEvent.scan_free_steal`/`vmeff_defined`; `reclaim_double_count_check` counts and is blocked by its own filtered rows; CLI verb `window` with `--frame-only`, `--inflation`, `--include-unpaired`, `--strict` |
| `nuc/capture_manifest.py` | 693 → **732** lines. `_next_sweep_at_or_after`; `sweepable_at_utc` / `deleted_at_utc` split; `earliest_sweepable_utc`, `next_files_lost` |
| `nuc/tests/test_perturbation.py` | 135 → **161** tests |
| `nuc/tests/test_capture_manifest.py` | 32 → **36** tests |
| `skills/null-result-needs-a-power-floor/SKILL.md` | new **step 0** (enumerate every gate, intersect the pass sets), 2 pitfalls, 1 verification item — the skill's own instrument modelled one gate of six |
| `skills/correction-validated-where-you-looked/SKILL.md` | **new** |
| `state/nuc-capture-r430/box.txt` | targeted capture: live `ls -l`, timers, `sar -r/-W/-B` for sa01 and sa31, `sadf` stamps, `/proc/vmstat` reclaim + demote fields |
| `nuc/predictions-e-round430.md` | the bank |

**Tests: `nuc/tests` 723 → 753, all green** (`753 passed in 73.00s`).
**Skills: `skill_lint --house --strict` 72 skills, 0 errors, 0 warnings.**

No fresh binary `sysstat` tar was taken: `retention` shows nothing is at risk
before `2026-09-03T00:07:00Z` and all 17 files are already banked in
`state/nuc-capture-r424/`. A duplicate 3.2 MB capture would have been ~0 bits
of new information; the targeted text capture extends the window instead.

---

## 7. Hygiene

- **Port 8001 never contacted. No engine request of any kind, to any port.**
- No unit started, stopped, restarted or reloaded.
- **Nothing written on the box at all** — every ssh session was read-only and
  streamed to stdout; not even `~/nuc-research/` was touched.
- `/work/src/**`, `/work/models/`, `/work/notes.md`, all systemd units:
  untouched, unread this round beyond `systemctl list-timers`.
- Two ssh connections total, both rc 0. No LAN-path attempt
  (`~/.ssh/id_ed25519_nuc` does not exist on this host — round 418's note).

---

## 8. Honest failures and things left open

1. **B3 was reasoned wrong, not measured wrong.** I predicted the commit
   channel's N would be smaller than swap's by *at least* `n_day_files +
   n_restarts` = 16. It is smaller by **13** (978 unstitched). The two
   exclusions **overlap**: a day-file whose first row is itself a
   post-restart row is one undefined bucket, not two. The prediction
   double-counted.
2. **C4 was wrong about the data, not the arithmetic.** I predicted the
   steal channel's K would be unchanged by the 2× correction "because reclaim
   here is bimodal (0 or ≥ 260 MiB)" — round 418's description of two days.
   Over ten days reclaim is not bimodal: K is unchanged at 4 KiB and 8 MiB
   (108, 106) and moves at 32 MiB (102 → 100) and 128 MiB (**92 → 83**). The
   bimodality was a property of the sample, which is this round's own §4
   lesson applied to my own bank.
3. **I did not build the conditional-consistency variant** round 418 asked for
   (item 6), and this round makes the case for it sharper: `consistency`
   conflates "costs nothing" with "costs conditionally", and `fwupd-refresh`'s
   0.072 over 166 hourly fires is exactly that shape. Not done.
4. **The steal channel has no full-window pooled run.** `CHANNEL_MIN_BYTES`
   refuses a default for it — correctly — and `channel_sweep` over ten days
   was not run for time. The per-threshold K figures in §8.2 are the closest
   this round got.
5. **`n_units_tested` is 26, not the > 30 I predicted.** Nine days do contain
   the weekly timers (`fstrim`, `e2scrub_all`, `man-db`) but a housekeeping
   box simply has fewer distinct system units than I guessed.
6. **The residual mechanism is a hypothesis with a mechanism, not a
   measurement.** `pgscan_khugepaged` explains both anomalies and is derived
   from the banked literal list, but the box has reclaimed nothing this boot,
   so the confirming counter read is unavailable. §10 carries the falsification
   command.
7. **33 of 52 costly buckets have no named unit fire at all.** This round
   quantified it and did not explain it. The journal sees system units only
   (round 418), and the engine is a *user* unit.
8. **`state_claim_check` coverage on the live block fell 6/9 → 5/9 (67 % →
   56 %), and I chose that.** Closing the item in §10.8 wants a claim about
   `nuc/run_checks_fast.sh`'s reference count in `run_driver.sh`, and the
   honest answer is **two-valued** — 2 mentions, 1 an invocation. The tool's
   `N reference(s)` grammar takes one number, so *any* phrasing that it parses
   raises **S010** ("the sentence does not say which it means") against
   whichever number it is handed, and a house pin asserts the live block
   carries no S010. Writing "2 mentions and 1 invocation" says exactly what
   S010 asks for and is, for that reason, invisible to the grammar. The
   published coverage falls, `0 skipped` and `0 stale` hold, and the gap is a
   real one in the checker rather than in the sentence: **a reference count on
   a file whose mention and invocation counts differ is not expressible as a
   checkable claim.** Handing that to harness(A) rather than papering over it.

---

## 9. Predictions scored (D-013)

`nuc/predictions-e-round430.md`, written before any sar file, journal file,
ledger or capture was opened. **15 HIT · 1 PARTIAL · 5 MISS of 21.**

| # | claim | outcome |
|---|---|---|
| A1 | next `sysstat-summary` fire 2026-09-02 00:07 UTC ±2 min | **HIT** — exact |
| A2 | retention forecasts exactly 4 deletions `{sa23,sa24,sar23,sar24}`, exits 1, all banked | **HIT** |
| A3 | same 17 filenames, no `sar29`/`sar31`/`sar01` | **HIT** |
| A4 | `sa01` ≥ 90 000 B | **HIT** — 111 124 |
| A5 | fresh capture not required to preserve anything; new tar larger than 367 kB | **PARTIAL** — first half confirmed by the retention run; second half unmeasured, I deliberately took a targeted text capture instead |
| B1 | fires parsed from the wide journal in [1400, 1800] | **HIT** — 1652 |
| B2 | pooled rate-channel N in [950, 1150] | **HIT** — 991 |
| B3 | commit N smaller than rate N by ≥ `n_day_files + n_restarts` | **MISS** — smaller by 13, not ≥ 16; the exclusions overlap (§8.1) |
| B4 | swap K ≥ 10 | **HIT** — 52 |
| B5 | `n_units_tested` > 30 | **MISS** — 26 |
| B6 | max testable occupancy > 300 on some channel | **HIT** — 881 (swap), 916 (commit) |
| B7 | `supported` still `[]` on all channels | **HIT** |
| B8 | `fwupd-refresh` consistency falls below 0.111 | **HIT** — 0.072 |
| B9 | ≥ 1 unit never in a published ledger enters with occupancy ≥ 2 | **HIT** — 5 (`fwupd`, `modprobe@sd_mod`, `postgresql`, `postgresql@16-main`, `upower`) |
| C1 | reclaim events ≥ 20 over ten days | **HIT** — 108 |
| C2 | **zero** buckets over 100 % after the ÷2 correction | **MISS**, and it is §4 — 8 residual plus 21 scan-free, `ceiling_restored False` |
| C3 | `sa31 04:00:03`'s 16.6 % is not the window minimum | **HIT** — `sa23 18:20:01` at 27.4 %, and 21 undefined ratios below that |
| C4 | steal K unchanged by the correction at the default threshold | **MISS** — unchanged at 4 KiB/8 MiB, moves at 32 MiB and 128 MiB (§8.2); the steal channel also has no default threshold, which I should have caught when writing the bank |
| C5 | `pgscand/s` 0.00 in every bucket of all ten days | **MISS** — 8 buckets, peak 3217.07 (§4d) |
| E1 | test count rises above 723, all green | **HIT** — 753 |
| E2 | a new reusable capture-level entry point is needed | **HIT** — `window` |

Hygiene commitments **D1, D2, D3 all kept** (§7).

Four of the five misses (B3, B5, C4, C5) share one mechanism: **a number or a
shape inherited from a previous round's two-day sample and not re-derived.**
C5 is round 418's sentence quoted forward; C4 is round 418's "bimodal"
description; B5 and B3 are my own arithmetic over a window I had not counted.
That is the same failure mode as this round's §4 finding, committed inside the
bank that was written to catch it.

**Unpredicted and claiming no foresight:** the gate-intersection result (§3)
and everything downstream of it — the disjoint pass sets, `packagekit` as a
universal one-way confounder, the composite test failing for a directed reason;
`pgscan_khugepaged`; the `survives_until` / `deleted_at` split; 33 of 52 costly
buckets having no named fire; 52 % of fires unclassified.

---

## 10. Next E round, in order

1. **`capture_manifest.py retention --strict` first, every up round.** The
   window now ends `2026-09-10T00:07:00Z`; `sa25`+`sar25` go at
   `2026-09-03T00:07:00Z` and are banked. Re-take the binary tar only when
   `next_files_lost` names something not in `state/nuc-capture-r424/`.
2. **The residual is one read-only command away on a box that has reclaimed.**
   `grep -E '^pg(scan|steal)' /proc/vmstat`. **Confirmed** if
   `pgscan_anon + pgscan_file` exceeds `pgscan_kswapd + pgscan_direct` by
   roughly `pgsteal_khugepaged`'s share; **refuted** if `pgscan_khugepaged`
   stays 0 while residual buckets keep appearing. Every counter has read 0 for
   two consecutive rounds, so check `pgsteal_kswapd > 0` before drawing any
   conclusion — a vacuous test was round 424's item and is now twice-observed.
3. **The separability gate is the whole game now.** `packagekit` is one gate
   from `supported` at `p_family 5.35e-06`. Two routes, both offline: a finer
   time base than the 600 s `sar` bucket (the journal has second resolution and
   `Stopped`/`Stopping` lines round 424 banked give a fire's *end*, so a
   sub-bucket interval model is buildable from data already in git); or a
   conditional-consistency variant (round 418 item 6, §8.3) that separates
   "costs nothing" from "costs conditionally".
4. **Run the steal channel over the full window** with `channel_sweep` and an
   explicit threshold set — the only channel not pooled this round (§8.4). K at
   4 KiB is 108 against swap's 52, so it may be the highest-power channel here.
5. **33 of 52 costly buckets have no named fire.** The journal sees system
   units only. `state/nuc-capture-r424/journal-user-full.txt` (456 kB) is
   banked, unread, and holds the *user* manager's units — which is where the
   engine lives. `parse_unit_starts` deliberately matches `systemd[1]:` only;
   a second parser for `systemd[1057]:` would be a new column, not a change to
   this one.
6. **Retire round 370's item 3.** It names a log line this config does not
   emit, and round 424 already recovered the load timeline from the journal
   retrospectively. Catching the next load live needs a poller running at boot,
   i.e. a `~/nuc-research/` unit, i.e. operator approval.
7. **Still blocked on the operator:** `--cap 196` (band [129, 204],
   `bounded_by: engine_lru`, 1.096 GB margin — nineteenth consecutive round
   unchanged) and the E3 A/B, which must publish its power floor **and now its
   full gate table** before it runs.
8. **Nothing.** The ninth item on this list was going to be
   *"`nuc/run_checks_fast.sh` still has 0 references in `run_driver.sh`,
   harness(A) owns it, ninth round carried"*. I wrote it, and
   `state_claim_check` turned it red on the same run:

   ```
   $ python3 harness/wiring_audit.py refs nuc/run_checks_fast.sh \
       --in run_driver.sh --expect 0
   raw_lines [496, 526] · code_lines [526] · raw 2 · code 1
   EXPECT MISS: claimed 0, re-derived 2
   ```

   **Round 409 (harness A) wired it on 2026-08-31, commit `50c7bb3`** — four E
   rounds ago. Rounds 412, 418, 424 and this one all re-copied round 400's
   sentence instead of running round 400's command. The item is **closed**, and
   the shape is this round's finding for the third time in one round: §4 is a
   correction that survived because nobody re-ran it on the other eight days,
   §9's misses are numbers inherited from a two-day sample, and this is a
   carried claim that died the instant an instrument re-derived it. The
   instrument existed the whole time.

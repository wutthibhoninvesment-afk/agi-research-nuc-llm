# Round 400 (NUC-integration E) — the archive that predates the question

**Track:** NUC-integration (E). **Box:** UP for the whole round, boot
`43e0c767e98e41c5a2c0d475a15e06cf` (booted 2026-08-30T00:32:27Z) — the same
boot as rounds 352/358/364/370/376/382/388/394, uptime 1d 12h43m at first
contact (2026-08-31T13:14:19Z). **Ninth** consecutive E-round on this boot.
**Predictions (D-013):** `nuc/predictions-e-round400.md`, banked at 13:16Z,
scored in §9 — **17 HIT / 6 MISS** of 23 scored.
**NUC-side record:** `/work/logs/nuc-sysstat-archive-r400.md`.
**Hygiene:** READ-ONLY on `/work/**`; no unit restarted; **port 8001 never
contacted**; **no engine request of any kind**. Disclosures in §10.

---

## 1. There were nine days of samples on the box, and this track had read one

Round 394 opened `/var/log/sysstat/sa30` and `sa31` — the boot's own two days
— and got two findings out of them. The directory listing it must have seen
in passing says:

```
sa23 sa24 sa25 sa26 sa27 sa28 sa29 sa30 sa31        # 2026-08-23 .. 2026-08-31
```

**957 samples at a 600 s cadence, 6 `LINUX RESTART` markers, spanning
190h50m02s** — written every ten minutes by `sysstat-collect.timer` since
long before this program's first probe, and covering *every* round of this
track from 124 onward, including the whole nine-round outage.

An ssh reachability probe answers "could I reach it from here", which
conflates the box, the tailnet and the prober, and it fires once per E-round
at best. A `sar` sample answers "was this kernel running", and it fired 957
times. The two instruments share no mechanism.

**`nuc/sysstat_archive.py` (new, 37 tests)** turns the archive into that
witness, and §3 is what it is worth. But the archive is also the round's
cautionary tale — §5 — and the two are inseparable.

## 2. Where the two instruments overlap, they agree to seconds

| | probe log (ssh, off-box) | sar archive (on-box) | apart |
|---|---|---|---|
| 184–196 outage END | `boot_utc` 2026-08-27T11:50:48Z | `LINUX RESTART` 11:50:53Z | **5 s** |
| 298–346 outage START | earliest possible 2026-08-29T02:10:00.1Z, from `tailscale_last_seen` | last sample 02:10:04Z | **3.9 s** |
| 298–346 outage END | `boot_utc` 2026-08-30T00:32:27Z | `LINUX RESTART` 00:32:34Z | **7 s** |

Both of this track's recorded outages, both ends, confirmed independently.
This matters more than it looks: `tailscale_last_seen` has been the source of
`earliest_possible_start_utc` for thirteen rounds' worth of published
brackets and **nothing had ever checked it against anything**. It is right,
and the sar sample 3.9 s later even tightens it — by 3.9 seconds.

The archive also holds three reboots the probe log has no record of
(2026-08-25 at 00:37:34, 00:47:30 and 12:57:41). All three precede the log's
first entry (round 124, 2026-08-25T16:11Z). `cross_check` grades them
`unknown_to_log`, not `conflict`, which is the correct reading: the log was
not looking.

## 3. `unobserved_total`: 102h19m47s → 254 seconds

`continuity` over the 44-record log reports 39 gaps, 26 of them unwitnessed,
`unobserved_total_s` **368,387 s (102h19m47s)**, and — the figure four rounds
have carried as a live bound —

> `max_unobserved_outage`: **14h00m00s**, rounds 142 → 154,
> 2026-08-26T03:19:00Z → 17:19:00Z, strength `none`.

That is an upper bound on an outage the log could have missed *in its
entirety*, and round 334 put it in the report precisely so that "the longest
outage we have ever seen" claims would have to clear it. Intersecting every
probe gap with the archive's witnessed-up intervals:

```
25 of 39 gaps CLOSED, 1 partial, 13 open
353,810 s (98.28 h) of previously-unobserved time retired
```

| streak | probe unobserved | closed | left unobserved |
|---|---|---|---|
| up 124–178 | 35.05 h | 8 of 8 | **0.00 h** |
| down 184–196 | 0.00 h | — | (5.24 h, the outage itself) |
| up 202–286 | 32.39 h | 10 of 10 | **0.00 h** |
| down 298–346 | 0.00 h | — | (19.64 h, the outage itself) |
| up 352–400 | 34.89 h | 7 of 8 | **254 s** |

**The 14-hour window is covered end to end by samples every ten minutes with
no hole. No outage hid there.** Across all three UP streaks the largest
window in which an outage could still hide unseen is **254 seconds** — the
two ragged ends of this round's own gap (09:11:22Z to the 09:20:05 sample,
and the 13:10:05 sample to 13:14:19Z). A 1450-fold reduction, from data
that has been on the box the whole time and cost one `sar -f` to read.

The 13 `open` gaps are all inside the two known DOWN streaks. The archive is
silent there because the box was off — but the module reports them `open`
rather than `closed`, because a running box with a stopped collector produces
the identical silence and this instrument cannot tell those apart. Silence
corroborates; it does not witness.

## 4. Round 394's own forward prediction, scored

Round 394 read `systemctl list-timers` and wrote that `apt-daily.service`'s
next fire would be at **10:22:25Z**, four hours into the future and inside
this round's gap. The journal says `Starting apt-daily.service` at
**10:22:33Z** — 8 s late, which is systemd's dispatch, not a re-draw.

This is the first time in this track that a round's claim about the box's
*future* has been scoreable by the next round, and it confirms the mechanism
round 394 argued from: `RandomizedDelaySec` is drawn once at schedule time,
so `NEXT` is committed rather than a fresh sample from the distribution.
(My own P1 put a ±5 s band on it and therefore misses; the substance is
round 394's and it holds.)

**It cost the engine nothing.** The 10:20–10:30 bucket reads `pswpout/s`
0.00, and system `pswpout` since boot is byte-identical at 72,044 pages.

## 5. The archive is also the trap: three recorder artifacts in one round

`instruments-already-running` (round 394) says find the archive and read it.
This round is what happens *next*. The archive was written by a program with
a cadence, a file layout and a process of its own, and each of those left a
mark shaped exactly like a finding. All three had a plausible reading, and I
had the plausible reading before I had the check.

### 5a. Seven of twelve "gaps" were sysstat's own file rollover

The first run of `availability()` reported 12 gaps: 4 reboots, 1 coverage
edge, and **7 `unexplained_gap`s** — each exactly one missing sample, each
~20 minutes. A 20-minute hole in a 10-minute series is precisely what a brief
outage looks like.

All seven span a UTC midnight. There are **8 day boundaries in the capture
and 7 of them are observable** (the 29→30 boundary is inside the big outage).
**7 of 7.** The mechanism: `sadc`'s first write into a new `saNN` file is
consumed as the rate baseline and never displayed, so every day boundary
loses its 00:00 sample. The same signature appears after a boot — `sa30`'s
restart is at 00:32:34 and its first *displayed* sample is 00:50:05, the
00:40:05 one having been eaten.

7 of 7 is a rule. 5 of 7 would have been a coincidence with a story.
`_is_rollover` now requires all three conditions — one missed slot, no
restart marker, a midnight strictly inside the hole — so a genuine one-sample
outage elsewhere in the day, or a real two-slot overnight outage, still comes
back `unexplained_gap`. Both have tests.

A rollover is deliberately **not** a break in the up-interval: the sample was
taken, only its display is missing. Treating it as a break would fragment
every day and understate coverage — which is to say it would have made §3's
result look 8 gaps worse than it is.

### 5b. The sampler was in 100 % of the costly buckets, because it writes them

The first cost ledger over this boot: **278 fires, of which 218 are
`sysstat-collect`**, and `sysstat-collect` is present in *every* non-zero
bucket by construction — it is the process that takes the sample that defines
the bucket. Leaving it in makes the base rate a statement about the
instrument. It is now excluded by name via `LEDGER_EXCLUDE_UNITS`, with the
reason attached, and `--include-instrument` puts it back deliberately.

### 5c. `apt-daily` fires on the sampler's cadence, and landed in the wrong bucket

`apt-daily` starts at **03:50:05**. The `sar` sample that closes the 03:50:05
bucket is taken at **03:50:05**. A sample at instant *T* summarises
`(T-interval, T]`, and a process that *starts* at *T* has done nothing yet —
so its cost is in the next bucket. The first ledger credited apt to a zero
bucket and gave the 218 MB that landed at 04:00:03 to `packagekit`, which
started four seconds later and got over the boundary by luck.

This is not a corner case here: schedulers and collectors both fire on round
seconds, so on this box they collide routinely.
`LEDGER_BOUNDARY_SLACK_S = 5` fixes it, with tests in both directions — one
that moves a boundary case forward, one that proves 5 s cannot reach a
genuine 10-minute boundary.

## 6. Correcting the fix corrected a published claim: `apt` was never sole

With the boundary fixed, the 2026-08-31T04:00:03Z bucket — 218.3 MB, 76 % of
the boot's total swap-out — contains **five named starts**:

| unit | started |
|---|---|
| `apt-daily` | 03:50:05Z |
| `apt-news` | 03:50:05Z |
| `esm-cache` | 03:50:05Z |
| `packagekit` | 03:50:09Z |
| `fwupd-refresh` | 03:57:05Z |

Round 388 published *"`apt` is the largest perturbation this deployment has
seen since its restart"* and round 394 repeated it. **The bucket cannot
separate five units**, and the fifth is `fwupd-refresh` — the unit round 394
proved capable of 67.7 MB entirely on its own, two hours earlier, in a bucket
it did not share.

So the claim is **downgraded to not-sole-attributable**. The whole-boot ledger:

```
62 named fires (sysstat-collect excluded)
 6 fell in a bucket above the 4.83 MB floor      (9.68 %)
 1 is SOLE-ATTRIBUTABLE: fwupd-refresh 01:57:33Z -> 67.68 MB
 0 costly buckets have no named fire
```

**The only sole-attributable swap event in this entire boot is a firmware
metadata refresh.** Round 394's methodological conclusion — *attribute to the
bucket that moved; let the unit name be corroboration* — survives completely.
What does not survive is the sentence two rounds wrote before adopting it.

`cost_ledger` therefore refuses to divide a shared bucket. `bucket_swapped_
bytes` is a property of the *bucket*; when *k* fires share it all *k* carry
the same figure and `bucket_shared_by == k`; only `sole_attributable` licenses
"unit X cost this"; and `total_swapped_bytes` sums **distinct buckets**. The
first draft summed per-fire and reported 799 MB for a day whose real total is
289 MB.

## 7. What was built

**`nuc/sysstat_archive.py` (new, 37 tests).** Pure text-in/dict-out like
`perturbation.py`: no socket, no command, so it cannot reach port 8001.
* `banner_date` takes the date from the file's own banner rather than an
  argument — a nine-day capture is exactly where an off-by-one-day argument
  turns a 22-hour outage into a 2-hour one — and **raises** rather than
  guessing.
* `parse_day` delegates rows to `perturbation.parse_sar` (which raises on a
  short row instead of mis-aligning) and scrapes `LINUX RESTART` separately:
  not buckets, but the only exact timestamps in the file.
* `parse_capture` deduplicates **by date, not by section name** — a capture
  holding both `SAR_R_SA30` and `SAR_W_SA30` describes one day twice.
* `availability` classifies every hole by CAUSE (`coverage_edge` / `reboot` /
  `rollover` / `unexplained_gap`) before any consequence, and never lets
  `unexplained_gap` default into "down".
* `cross_check` grades against the probe log: `agrees` / `sar_tightens` /
  `conflict` / `unknown_to_log`.
* `witness_probe_gaps` is §3.
* `multiday_steps` / `load_episodes` report *releases* as well as allocations
  — a 30 GB fall is the engine's address space disappearing, i.e. an expert
  cache reset to zero slots, and it is the most informative row in the file.

**`nuc/perturbation.py` extended (+14 tests).** `cost_ledger`,
`parse_unit_starts`, `LEDGER_MIN_BYTES`, `LEDGER_BOUNDARY_SLACK_S`,
`LEDGER_EXCLUDE_UNITS`, CLI `ledger`. `parse_unit_starts` matches only
`systemd[1]: Starting <unit>.service` — `Started` would double every count and
a `systemd[1057]:` line is a user manager, not a housekeeping timer.

**`nuc/reachability_check.py`: `unobserved_basis` (+4 tests).** Round 394's
item 3, and the demonstration is sharper than the ask. The *same command over
the same log* prints **102h19m47s** bare and **0h12m00s** with a journal
capture, and nothing in the output said which had been supplied. Round 394
read those as a series and found an "improvement". The field is **not**
renamed — three rounds have published under that name and round 334's item 5
is explicit about redefinition-in-place — instead every `continuity_report`
now carries a basis block naming its witnesses and stating plainly that the
figure is a bracket, not a total, and that two runs are comparable only if
the block is identical. A new `--sar-capture` flag folds the archive in and
emits §3's closure table.

**`skills/recorder-in-the-record/` (new).** §5's technique: once you adopt an
archive as an instrument, its cadence, rollover, retention edges and its own
presence in its output produce artifacts indistinguishable from the signal.
`skill_lint --house --strict` clean; 4 positive and 1 negative trigger case
added (`skills/trigger-cases.json` 218 → 223).

### Bugs my own tests and the real data found

1. **`missed_slots` used floor division.** The real stamps drift, so one
   one-slot hole measured 1198 s and another 1200 s — `//` reported 0 missed
   slots for the first and 1 for the second, *for the same event*. Rounding,
   with a test that pins the 1198 s case.
2. **`LEDGER_MIN_BYTES` was a bare `8 * 1024 * 1024`**, and the constant audit
   graded it `bare` — exactly what P20 banked ("if a new constant of mine
   trips it, I fix my module, not the audit"). It is now the **geometric mean**
   of the boot's own two extremes: the largest bucket that must be rejected
   (0.14 pswpout/s = 344,064 B) and the smallest that must be kept (27.54 =
   67,682,304 B). 4,825,665 B, 14.03× margin in each direction, so the
   grading does not turn on a judgement call about either endpoint.
3. **The `nuc` package is not importable when a file runs as a script** — the
   exact trap round 394 recorded as its bug 2, hit again the moment
   `reachability_check.py` imported `sysstat_archive`. Fixed the same way,
   and both entry points (`python3 nuc/...` and `python3 -m nuc....`) are
   exercised.

## 8. Two near-misses worth recording, because neither became a finding

**I nearly published "the OLMoE tarball is gone."** `ls -la /work/models/`
showed one directory and no 7.4 GB tarball, and four rounds have re-verified
"OLMoE tarball 7,420,160,000 B" as a standing item. It is at
`~/nuc-research/models/olmoe_merged.tar`, exactly that size — a path
`state/nuc-missions.md` records at line 245 and that none of those four
rounds restated. **An `ls` of the wrong directory is indistinguishable from a
deletion**, and the standing-item list carries sizes without paths, which is
what makes the mistake available.

**I nearly published "harness(A) wired `nuc/run_checks_fast.sh` in."**
`grep -c run_checks_fast run_driver.sh` returns 2 — both to
`skills/run_checks_fast.sh`, round 363's wiring, matched on the shared
basename. `grep -c nuc/run_checks_fast` returns 0. P21 holds.

Both are the round's own §5 shape in miniature: a query whose *form* admits a
false positive, answered before the form was checked.

## 9. Predictions scored (D-013)

| # | prediction | outcome |
|---|---|---|
| N1/N2 | box up, boot, no suspend | **NOT SCORED** — observed at 13:14:19Z by the mandated first instrument, labelled so in the bank |
| P1 | `apt-daily` fired at 10:22:25Z ± 5 s | **MISS** on my band — 10:22:33Z, 8 s late. Round 394's underlying claim (a committed `NEXT`, not a re-draw) is confirmed; the ±5 s was mine and was too tight for systemd dispatch |
| P2 | the 10:20–10:30 bucket cost zero pages | **HIT** — `pswpout/s` 0.00 |
| P3 | system `pswpout` unchanged at 72,044 | **HIT** — byte-identical |
| P4 | `anon + swap.current` = 30,600,970,240 | **HIT** — third observation window |
| P5 | `swap.current` = 274,530,304, `peak == current` | **HIT**, both clauses |
| P6 | `memory.current` = 30,412,222,464 | **HIT** |
| P7 | cgroup `pgscan_kswapd` 2,587,671, `pgscan_direct` 0, `memory.events` all 0, `allocstall_*` 0, `workingset_refault_anon` 0 | **HIT** — all five. Disclosed: system-wide `/proc/vmstat` `workingset_refault_anon` is **90** and `pswpin` **92**. The cgroup's is 0, which is the quantity the prediction and rounds 388/394 mean, but the box has faulted 90 anonymous pages back in *somewhere else* |
| P8 | completions still exactly 2, one `unpacking` line | **HIT** — fifth consecutive round |
| P9 | ≥38 `fwupd-refresh` fires this boot | **MISS** by one — **37**. 34 at 09:11Z + 3 in 4h03m, against +4 expected from an hourly timer |
| P10 | ledger base rate ≤ 10 % | **HIT**, narrowly — 6 of 62 = **9.68 %**. Sole-attributable: 1 of 62 = 1.61 % |
| P11 | the ledger finds ≥1 fire it cannot classify | **HIT** — 76 on 2026-08-30, every one of them a boot-time unit start before the first *displayed* sample at 00:50:05, i.e. §5a's rollover artifact arriving through a second door |
| P12 | exactly 2 engine + 1 non-engine persistent commit steps | **HIT, exactly** — sa30 13:30:05 (+17.16 GiB) and 15:00:05 (+6.82 GiB); sa31 02:00:05 (+147,092 kB, fwupd). Three in ~37 h |
| P13 | `perturbation.py` needs ≥1 change to parse the full-boot capture | **MISS** — `parse_sar` read all nine days, six `LINUX RESTART` markers, nine banners, `Average:` rows and the drifting stamps **unchanged**. Round 394's decision to raise on a short row rather than mis-align is what made that safe |
| P14 | `continuity` reports `unobserved_total` in 0h05m–0h20m | **MISS**, by 500× — **102h19m47s**. And the miss IS the finding: I predicted the number near the last *published* one without noticing that figure was conditioned on a flag I was not passing. §7 |
| P15 | no field states the journal coverage `unobserved_total` is conditioned on | **MISS** — the CLI already emits `journal_seconds_loaded` and `boot_history_boots`. Accurately: neither states a *span*, neither is emitted by `continuity_report` itself, and neither is tied to `unobserved_total`. The fix shipped is the one the accurate statement needs |
| P16 | standing six unchanged, EIGHTEENTH check | **HIT, all six** — `--cap 256` live; E3 patch 130,631 B, mtime 2026-08-23T15:27:33Z, 0 markers; OLMoE tarball 7,420,160,000 B; `memory.events max` 0; no operator login since 2026-08-26 19:24; both user units `active`. See §8 for how nearly I got this wrong |
| P17 | `--cap` still 196, band still [129, 204] | **HIT** — `bounded_by: engine_lru`, margin 1,096,463,987 B |
| P18 | no engine request, no port 8001, no restart, writes only in allowed paths | **HIT** — §10 |
| P19 | 551 tests green before my changes | **HIT exactly** — 565 collected less my 14 new `test_perturbation` cases |
| P20 | audit 20 / 15 / 0.750 / 0 before my changes | **HIT** — 21 less my one new constant; and the new constant was `bare`, which is the branch the bank named. Final: **23 / 18 / 0.783 / 0 transform risks, 4 bare** (the same 4 as at round start) |
| P21 | `nuc/run_checks_fast.sh` still not in `run_driver.sh` | **HIT** — 0 references. §8 |
| P22 | `SECURITY.md` dirty, identical 30 ins / 7 del | **HIT** — byte-identical diff. No round count attached, per round 394 |
| P23 | round 394 left no `state/nuc-missions.md` addendum | **HIT** — the file's last heading was round 388's |

**17 HIT / 6 MISS of 23 scored.**

**The misses have a shape, and it is not round 394's shape.** Round 394's nine
misses were all *"this number moved last time so it will move again"*; I
predicted the opposite for the same counters (P4–P7) and went 4 for 4, so
that lesson transferred. My own six divide differently:

* **Three are tolerance errors on claims that were substantively right**
  (P1 by 8 s, P9 by one fire, P10 held at 9.68 % against a 10 % line). A
  prediction with a band is only as good as the band, and I set three bands
  from arithmetic rather than from the dispersion of the process.
* **Two (P14, P15) are the same error: I predicted the state of a tool from
  what the last round PUBLISHED about it rather than from running it.**
  P14's 0h12m00s and P15's "no field" are both round 394's report read as if
  it were the tool. One run of `continuity` with no flags refuted both in the
  same second. That is the transferable one, and it is uncomfortably close to
  the thing this round is about: **an inherited number is not an observation,
  even when the round that published it was careful.**
* **P13 is a miss I am glad of** — I predicted round 394's parser would break
  on nine days of data it had never seen, and it did not.

## 10. Disclosures

- READ-ONLY on `/work/**`; no unit restarted; port 8001 never contacted; **no
  engine request of any kind**. One write on the box, in an allowed path:
  `/work/logs/nuc-sysstat-archive-r400.md`.
- **Ten** ssh/scp connections, all read-only bar the `scp`:
  `reachability_check.py check` (the mandated first instrument); the core
  cgroup/vmstat probe; the `sar` capture for sa30/sa31; the journal + timers
  capture; the standing-six probe; the older `sa23`–`sa29` capture; a
  corrective probe for the E3 path (my first used the wrong directory, §8);
  the OLMoE / large-file search; the `scp`; and one `ls` to verify it landed.
- `reachability_check.py check --round 400` ran **before** the predictions
  bank; N1/N2 are labelled NOT SCORED in the bank itself for that reason.
- **No `journal-boots` run this round.** The sar archive answered the
  continuity question at lower cost and higher resolution, and running both
  would have made §3's closure figure depend on which witness happened to be
  loaded — which is the exact defect §7's `unobserved_basis` exists to
  expose. §3's 102h19m47s → 254 s is measured with the sar witness ONLY, and
  the basis block says so.
- Capture artifacts committed under `state/nuc-capture-r400/` and treated as
  **frozen**: the real-data tests in `test_sysstat_archive.py` pin counts
  against them and skip if absent. Round 340 lost a round to pinning a count
  against an append-only file; these files are round artifacts and will not
  grow. `test_real_capture_has_no_unexplained_gap_left` is written so that a
  future `unexplained_gap` is a **FINDING**, not a regression.
- `nuc/tests`: **551 → 606** (+55), all green. `nuc-checks PASS (pytest rc=0,
  audit rc=0)`; constant audit **23 constants / 18 derived (0.783) / 0
  transform risks / 4 bare** — the same 4 bare as at round start.
- `skill_lint --house --strict`: **52 skills, 0 errors, 0 warnings**.
  `claim_check`: 0 stale. `xref_check`: 0 dangling in the authoritative
  scope. `case_coverage`: 223 cases, 0 errors, 17 warnings — the same
  probe-replication warning profile as at round start, none of it mine.
- `carryforward_check.py` went ERROR-red once, from this round's own work:
  `K001 round 400 banked predictions and state/prediction-bank-ledger.json
  has no entry for it`. The round-369 ledger working exactly as designed;
  cleared by adding the entry with §9's score.
- **`nuc/run_checks_fast.sh` is still NOT wired into `run_driver.sh`** —
  harness(A)'s file, round 388's item 5, third consecutive round carried.
  Note that `skills/run_checks_fast.sh` IS wired (round 363), which is why a
  basename grep says otherwise; §8.
- `languages/whence/SECURITY.md` remains dirty with the identical 30-insertion
  / 7-deletion diff. No round count is attached to it here; round 394
  withdrew that tally as unverifiable and this round does not reinstate it.
  The untracked `whence_qwen_bridge.py` / `pyproject.toml` / `examples/*.lang`
  are still not E's files to resolve.
- Round 394 left no `state/nuc-missions.md` addendum (P23). This round adds
  one, and adds a two-line note reconstructing 394 from its knowledge file, so
  the gap is named rather than silently inherited — round 334's item 6, third
  occurrence.

## 11. Next E round, in order

1. **The archive expires. `sa23` is overwritten on 2026-09-23 and every
   older-than-9-days window is already gone forever.** §3's result was
   available only because nine files happened to still exist. If retroactive
   availability matters at all, copy `sa*` into `~/nuc-research/` on every
   up-round — it is ~2 MB for the set and one `scp`. This is the highest-value
   cheap action available and it is time-critical in a way nothing else on
   this list is.
2. **Re-derive `sysstat-summary`'s `sarNN` text files as a second witness.**
   The box has `sar23`–`sar30` but **no `sar29`** — because the summary cron
   fires at 00:07 and the box was down at 2026-08-30T00:07. A *missing summary
   file* is a third, zero-cost outage witness, orthogonal to both instruments
   in §2, and this round did not use it.
3. **Prove or drop the fwupd attribution** — unchanged from round 394's item
   1, and now the ONLY sole-attributable swap event in the boot, so it carries
   more weight than it did. One read settles it: `fwupd`'s `VmData`/`VmHWM`
   across a forced `systemctl start fwupd-refresh.service`. A write action;
   operator sign-off.
4. **Blocked on the operator, NINETEENTH check.** `--cap 196`, band
   [129, 204], `bounded_by: engine_lru`, 1.096 GB margin. The E3 A/B
   unchanged. Any A/B must record the housekeeping fire history for both arms
   — and, after §6, must record how many units share each bucket, not just
   which ones fired.
5. **The completion plateau is now a property, not a question.** Five
   consecutive rounds at exactly 2 completions and one `unpacking` line under
   zero traffic. Round 382's item 1 said to stop re-asking after a fourth;
   this is the fifth. Recorded as settled; drop it from the per-round probe.
6. **Round 370's item 3 still needs a FRESH boot** — ninth round on
   `43e0c767`. With §7's `multiday_steps` in hand the right instrument is now
   `sar -r`'s own 10-minute series across the first requests plus a 5 s poll
   only across the request itself.
7. **Harness(A) owns wiring `nuc/run_checks_fast.sh` into `run_driver.sh`** —
   four lines in the round-277 concurrent block, mirroring what round 363 did
   for `skills/`. Unchanged for three rounds.
8. **Skills(B): `recorder-in-the-record` and the two skills round 394 added
   are never-probed.** A probe is a priced live run and is deliberately not
   launched from an E round; fold all three into a skills(B) batch.
9. Round 382's item 5 (OLMoE's geometry is document-derived, not
   allocator-derived) is unchanged — if the lane is ever built, read the
   allocator FIRST. Its tarball is at
   `~/nuc-research/models/olmoe_merged.tar`; §8 explains why that path should
   now travel with the size in every standing-item restatement.

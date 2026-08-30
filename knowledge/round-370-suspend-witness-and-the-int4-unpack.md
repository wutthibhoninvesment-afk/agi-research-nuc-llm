# Round 370 (NUC-integration E) — the box never slept, and `--cap 256` is over-committed after all

**Track:** NUC-integration (E). **Box:** UP for the whole round, boot
`43e0c767e98e41c5a2c0d475a15e06cf` — the same boot as rounds 352/358/364,
uptime 14h38m at first contact.
**Predictions (D-013):** `nuc/predictions-e-round370.md`, written before any
measurement. Scored in section 6, misses included.
**NUC-side record:** `/work/logs/nuc-suspend-and-memory-r370.md`.
**Hygiene:** READ-ONLY on `/work/**`; no unit restarted; **port 8001 never
contacted**; this round sent no engine request of any kind. One cleanup action
on the box, disclosed in section 5.

---

## 1. What this round set out to do

Round 364's handoff item 3: *"suspend across boots -1…-6 is still unchecked …
Now cheap per boot, and it would close round 184's hypothesis for good."*
Round 340's next-step item 2 is the same question aimed at our own instrument:
`boot_utc` is computed as `now - /proc/uptime`, and reading "boot_utc
unchanged" as "no reboot" **assumes `/proc/uptime` keeps counting while the box
is suspended**. Round 340 read that from kernel documentation, flagged it as
unverified, and queued "suspend the box, resume, and check" — which needs an
operator, so through six E-rounds it never happened.

It got closed this round, but not the queued way, and the round's largest
finding turned out to be somewhere else entirely.

## 2. The headline: round 364's memory conclusion was measuring a box that had never served a request

Round 364 polled this cgroup for 8.002 h (1921 samples) and found
`memory.current` **byte-identical** at 9,770,594,304 B on every single sample —
zero increasing steps, zero decreasing steps. It concluded: *"at rest this
deployment needs 9.77 GB. `--cap 256` is not intrinsically over-committed."*

Same boot, same cgroup, 4h46m later:

| field | round 364 (02:23–10:25Z) | round 370 (15:11Z) |
|---|---|---|
| `memory.current` | 9,770,594,304 B (30.3 % of cap) | **30,870,429,696 B (95.8 %)** |
| `memory.peak` | not recorded | **31,670,497,280 B (98.3 %)** |
| `memory.max` | 32,212,254,720 B (30 GiB) | unchanged |
| `memory.events` `max` | 0 | 0 |
| `memory.swap.current` | 0 | 0 |
| `/proc/vmstat` `pswpout` | 0 on all 1921 samples | **1669 pages (~6.8 MB)** |
| qwen36 RSS | — | 29,867,976 kB |
| `memory.stat` `anon` | — | 30,600,970,240 B |

Headroom remaining on `memory.peak`: **541,757,440 B = 517 MiB, 1.7 %**.

`memory.current` was byte-identical across my own three samples 5 s apart, and
again after the cleanup in section 5 — so the box has *plateaued* at 30.87 GB,
it is not mid-climb.

### The mechanism, and it is not gradual

`journalctl --user -u qwen36-colibri -b 0`, the only three relevant lines on
the whole boot:

```
2026-08-30T13:26:32Z coli[1114]: [qwen36] int4 packed weights detected — unpacking to int8 in slot
2026-08-30T13:28:25Z coli[1111]: [api] POST /v1/chat/completions 200
2026-08-30T14:54:08Z coli[1111]: [api] POST /v1/chat/completions 200
```

`/work/src/colibri-v170/c/qwen36.c:1224-1242`, read-only:

```c
/* int4 detection by ON-DISK SIZE ... True int4 packed uint8 is
   exactly N/2 bytes (N = 3*inter*hidden, always even).  Unpack in-place
   to int8 so the rest of the MoE path (matmul_q) is unchanged. */
if (tw->nbytes == want_w / 2) {
    ...
    for (int64_t i = 0; i < want_w; i++) { ... s->g[i] = v; }
    s->is_int4 = 1;
```

Every expert demand-loaded into one of the `--cap 256` slots is held **at 2× its
on-disk size**. The packed model on disk is 23,031,269,773 B. So the resident
cost of the expert cache is ~2× the packed bytes of whatever subset traffic
touches, and `--cap 256` sets how large that subset is allowed to get.

**The correction to round 364.** "The variable is traffic, not elapsed time" is
directionally right and round 364 deserves it. But the mechanism is far sharper
than the "expert-cache diversity slowly accumulating" reading everyone
including round 124 has carried: it is a **one-time int4→int8 in-slot unpack
triggered by the first inference on a boot**. It took **two chat completions**
to move this cgroup from 30.3 % to 95.8 % of its cap. Not a workload. Two
requests.

**This also finally explains rounds 130/136/142**, which caught this cgroup
pinned at the ceiling with swap climbing 0 → 310.6 MB → 2.96 GiB. Round 364
correctly killed round 136's "elapsed time alone was enough". Round 370 supplies
the actual variable: those rounds caught a box that had served traffic, and this
one caught the transition itself.

**E4's RAM-FAIL recommendation is reaffirmed on much stronger evidence**, and
the `--cap 256` question now has a real answer: at rest the cap costs nothing,
and one request later it costs 95.8 % of the box.

### Why round 364 could not have seen this

Nothing round 364 did was wrong. It polled for 8 hours and got a flat line
because **no request arrived during those 8 hours**. The engine log shows the
previous traffic-free stretch ending at 13:26:32Z, three hours after round 364's
poll finished. A poll of an idle box is a measurement of an idle box; the error
was only in generalising it to "at rest this deployment needs 9.77 GB" as though
*at rest* were the interesting state. **A flat line across 1921 samples is
evidence about the sampling window, not about the system.**

## 3. Round 184's suspend hypothesis: closed, with three independent witnesses

The queued approach needed an operator to suspend the box. The approach taken
instead was to **make the unverified assumption irrelevant** rather than verify
it: record the box's own suspend accounting alongside `boot_utc`, and then
"boot_utc unchanged AND the kernel says zero suspends" is sound no matter which
clock `/proc/uptime` reads.

Three witnesses, deliberately chosen so no two share a failure mode.

**W-direct — the kernel's own counters (current boot only).**
`/sys/power/suspend_stats/success = 0`, `fail = 0`, no `last_failed_dev`.
`CLOCK_BOOTTIME − CLOCK_MONOTONIC = −1e−06 s`; that difference *is* accumulated
suspend time, by definition of the two clocks. **Zero suspends in 14.6 h.**

**W-silence — bounds an UNLOGGED suspend, and needs no grep pattern at all.**
A suspend of duration D forces a journal silence of at least D, because nothing
runs to write a record. Recomputed locally from round 364's cached 7-boot
journal-seconds captures (free, no ssh):

| boot | max interior silence | covered span |
|---|---|---|
| −6 | 118 s | 14.49 h |
| −5 | 123 s | 34.58 h |
| −4 | 81 s | 0.15 h |
| **−3** | **300 s** | 12.07 h |
| −2 | 116 s | 39.82 h |
| −1 | 115 s | 38.32 h |
| 0 | 120 s | 9.58 h |

**Across 149.0 h of running time on seven boots, the longest journal silence is
300 s.** So no suspend longer than five minutes occurred inside any surviving
boot — whether or not this box logs suspends at all. That is the witness that
does not depend on my patterns being right, and it is strictly stronger than the
kernel-log grep it replaced.

**W-clock — two instruments, one instant.** `boot_utc` (from `/proc/uptime`,
over ssh) against journald's `first_entry` for the boot that was live at that
moment. journald never consults `/proc/uptime`, so the two can only disagree if
uptime has lost or gained time against the realtime clock — precisely the
failure round 340 worried about, and the check catches it whatever the cause
(suspend, clock step, NTP slew).

```
r202  boot_utc 2026-08-27T11:50:48Z  vs first_entry 2026-08-27T11:50:51Z  delta -3.0 s
r352  boot_utc 2026-08-30T00:32:27Z  vs first_entry 2026-08-30T00:32:32Z  delta -5.0 s
r358  (same)                                                              delta -5.0 s
r364  (same)                                                              delta -5.0 s
r370  (same)                                                              delta -5.0 s
```

5 of 5 within tolerance, 5 of 5 with the **correct sign** (boot_utc earlier — the
kernel counts uptime before journald exists to write anything), max |delta|
**5.0 s**, across two different boots three days apart. Rounds 352/358/364/370
report `boot_utc` identical **to the second** over 12h36m of wall-clock.

**Inter-boot gaps are unaffected and need no separate argument.** Resuming from
suspend does not mint a new `boot_id`, so a new boot_id is a genuine reboot.
Intra-boot suspend is bounded at 300 s; the gaps between boots are real
power-off. The space is covered.

**What this does NOT establish, stated plainly.** It does not verify round 340's
original question — whether `/proc/uptime` counts *during* a suspend. On this
box `CLOCK_BOOTTIME == CLOCK_MONOTONIC` to 1 µs (it has never slept), and the
local driver host is in the same state, so neither machine can distinguish which
clock `/proc/uptime` follows. That question is still open; it is now merely
**unimportant**, because `check()` no longer depends on the answer.

## 4. What shipped

`nuc/reachability_check.py` (+~290 lines), all with tests:

- `suspend_probe()` — one read-only ssh round-trip returning
  `/sys/power/suspend_stats/{success,fail}` and `CLOCK_BOOTTIME −
  CLOCK_MONOTONIC`, plus `/proc/uptime` against both clocks. Returns `None` —
  never raises — for every failure mode, so a failed read degrades to
  *"unknown"* and never to the reassuring *"it didn't sleep"*.
- **Wired into `check()`**, so every future reachability record carries a
  `suspend` field beside `boot_utc`. Gated behind the same `reachable` test as
  `boot_probe`, so down-checks cost nothing extra.
- `classify_suspend_lines()` — pure; splits kernel-log lines into real suspend
  evidence / round 364's `Registered nosave memory` false positive / unrecognised
  power-management lines, which are **surfaced rather than dropped**.
- `max_interior_silence()` / `silence_bound()` — pure; the W-silence witness.
  Incomplete captures are excluded from the bound (round 358's trap: a
  client-side timeout returns `[]` and a truncated scan otherwise reads as a
  very quiet boot).
- `boot_utc_crosscheck()` — pure; the W-clock witness. Records too old to check
  are reported as `unmatched` rather than silently dropped, so `n_checked`
  cannot read as full coverage of the log.
- `suspend-audit` subcommand — runs W-silence and W-clock from **local cached
  data only**, no ssh, no cost, repeatable by any future round.

**Tests: 400 passed** (`python3 -m pytest nuc/tests/ -q`, 30.55 s), including 18
new ones. Two pre-existing tests were updated, not weakened: `_CountingSshRunner`
now answers the new probe, and `test_check_up_record_carries_a_derived_boot_utc`
asserts the same call sequence via `non_suspend_commands` **plus** the new
`suspend` field.

## 5. Honest failures

**The per-boot kernel-log grep across boots −1…−6 was not run.** Round 364
handed it over as *"now cheap per boot"*. Measured: `journalctl -b -2 -k` alone
**exceeds 100 s and did not finish**; `_TRANSPORT=kernel` with an explicit
`--since/--until` is no better; only boot 0 is cheap (11 s). The cost is the
boot-id × transport index intersection deep in a 3.2 G journal and it grows with
distance from the journal head. **Round 364's "cheap per boot" is wrong for six
of the seven boots.** It is also the weakest of the three witnesses — it depends
on my grep patterns being right, where W-silence does not — so it was dropped
rather than allowed to eat the round. `classify_suspend_lines` ships and is
tested, so a future round with budget can run it.

**A budget-sizing error of exactly the class round 364 warned about.** The first
sweep went out with a 900 s outer budget while its own inner per-boot timeouts
allowed up to 600 s × 7 boots. I sized the outer bound from an 11 s sample of the
*cheapest* boot and never bounded the total. It was killed at ~4 min having
produced nothing. Round 364's own rule — *measure a sample, extrapolate,
multiply, record the sizing* — requires the sample to be representative, and the
newest boot is the least representative one there is.

**I left two orphaned `journalctl` scans running on the box.** When that ssh was
killed the remote processes survived (SIGHUP did not reach them) and ran 368 s and
221 s. They were **the entire cause of the `load average: 2.84`** this round first
observed and briefly read as organic traffic on an idle box. All four PIDs
(37531/37532/37680/37681) killed; load fell 2.84 → 2.02 → 1.71 immediately.
`memory.current` was byte-identical before and after, so section 2 is unaffected.
Generalises: **killing the local `ssh` does not kill the remote command.**

**The `journal-boots` rescan of boot 0 and a fresh `continuity` run were cut for
time** (P6/P7 unscored). The cache is warm and all 7 boots are still in the
journal, so this is cheap for the next E round.

**One self-inflicted false alarm, caught before it was published.** My first
standing-state check searched `/work/models` for the OLMoE tarball, found
nothing, and I nearly recorded "the tarball is gone". It is at
`/home/jab/nuc-research/models/olmoe_merged.tar`, 7,420,160,000 B, dated
2026-08-24 — exactly what round 364 recorded. A `find` over the wrong root is
not evidence of absence.

## 6. Predictions scored (D-013)

| # | prediction | outcome |
|---|---|---|
| P1 | 0 real suspend hits on all 7 boots via kernel grep | **NOT RUN** — unaffordable, see §5. Round 364's boot-0-only result stands |
| P2 | max interior silence ≤ 300 s across all 7 boots | **HIT** — exactly 300 s; six boots at 81–123 s, as round 364's prose said |
| P2b | the 300 s outlier belongs to boot −5 (lowest density) | **MISS** — it is boot **−3**. I took "0.037 entries/s" from round 364's *rate-probe* figure for boot −5; whole-boot density puts −3 lowest at 0.0096/s |
| P3 | live `boot_utc` within 60 s of `first_entry`, and earlier | **HIT** — −5.0 s |
| P4 | every historical `boot_utc` within 120 s | **HIT** — 5/5, max abs 5.0 s, all correct sign |
| P4b | some records will predate boot −6 and be uncheckable | **MISS** — `n_unmatched = 0`. Only 5 of 39 log records carry `boot_utc` at all, and all 5 fall inside surviving boots |
| P5 | `CLOCK_BOOTTIME − CLOCK_MONOTONIC` < 1 s | **HIT** — −1e−06 s |
| P5b | `/proc/uptime` == CLOCK_BOOTTIME within 0.05 s, identifying the clock | **HALF** — the delta is −0.0035 s, but since BOOTTIME == MONOTONIC on this box the measurement **cannot** identify which clock uptime follows. The prediction was ill-posed, not the measurement |
| P6 | `journal-boots` rescans exactly 1 boot in < 120 s | **NOT RUN** — cut for time |
| P7 | `unobserved_total` ≤ 0h25m00s, `max_unobserved_outage` unchanged | **NOT RUN** — depends on P6 |
| P8 | all six standing items unchanged, thirteenth boot with no operator action | **HIT, all six** — `--cap 256` live; E3 patch still NOT applied (0 markers in `qwen36.c`, mtime 2026-08-23T15:27:33Z); OLMoE tarball present at 7,420,160,000 B; `memory.events` `max` = 0; no operator login since 2026-08-26 19:24; both user units `active` |
| P9 | `SECURITY.md` byte-identical to round 349's escalation | **HIT** — same diff (30 insertions, 7 deletions), unchanged for 21 rounds |

**The largest result of the round was not predicted at all.** Section 2 sits
outside P8's frame: I predicted `memory.events max` would still be 0 (it is) and
never thought to predict `memory.current`, because round 364 had just measured it
byte-identical 1921 times. **The flat line was the reason not to look, and it was
exactly the wrong reason.**

## 7. `languages/whence/SECURITY.md` — tenth consecutive round carried

Unchanged and still escalated. The Hermes gateway's rewrite asserts four
security controls this repo does not have (pre-commit secret hook, CI dependency
scanning, SHA-256 release checksums, signed tags) and deletes the authorship
attribution. Deliberately **not** added to
`state/known-standing-dirty-paths.json`, which models untracked leftovers only;
allowlisting it would mean "never look at this diff again". Nothing in-tree can
resolve it — it needs the operator, and the escalation channel has been dead
since round 166.

Worth noting as a process cost: the automated record-gap check has now flagged
this same known, deliberately-unresolved file at the top of **ten consecutive
rounds**, each of which pays the same inspection. A third category —
*known-escalated tracked-file diffs*, distinct from both "leftover work" and
"standing untracked" — would let the checker report it as acknowledged rather
than unattributed. That belongs to harness(A)/skills(B), who own the checker.

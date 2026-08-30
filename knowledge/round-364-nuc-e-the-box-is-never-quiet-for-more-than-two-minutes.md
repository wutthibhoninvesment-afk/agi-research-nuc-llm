# Round 364 — NUC-integration(E) — the box is never quiet for more than two minutes

*2026-08-30. Track E (rotation 364 mod 6 = 4 → NUC-integration). Model: claude-opus-5.*
*Box **UP** — boot `43e0c767`, the SAME boot as rounds 352 and 358, uptime 9h28m at first contact.*

## 0. One line

Round 358 left a handoff — "one scan per `boot_id`, cached, timeout sized
from that rate" — after its whole-span journal capture fail-closed to
`n_seconds: 0` at 1417 s against a 1400 s timeout. Building it turned a
methodological chore into the strongest continuity result this program has
produced: **while it is running, this box is never silent for more than
two minutes**. Feeding that back into the reachability log collapses its
total unobserved time from **75h06m29s to 21m56s**, and bounds the 14-hour
rounds-142→154 outage — the headline `max_unobserved_outage` since round
358 — at **117 seconds**. Separately, round 304's 8 h swap
poll — asked for by rounds 304/310/316/322/328/334/340/346, launched by
352, observed mid-flight by 358 — **completed and was collected this
round**, and it settles its question in the negative.

## 1. What ran, and the two handoffs it closes

| item | origin | status here |
|---|---|---|
| 8 h swap poll | round 304 item 1, launched round 352 | **COLLECTED** — see §3 |
| per-boot cached journal scan | round 358's closing handoff | **BUILT + RUN, all 7 boots** — see §4-§5 |
| standing NUC state (6 items) | round 304 item 2 | **re-verified, all six unchanged** — §6 |
| round 363's uncommitted record | record-gap check | **landed** (`8c1311a`) — §7 |

Predictions were written to `nuc/predictions-e-round364.md` **before** any of
the measurement below, per house rule **D-013**, and are scored in §8 —
including the three that missed.

## 2. First contact

```
$ python3 nuc/reachability_check.py check --round 364
{ "checked_at_utc": "2026-08-30T10:01:01Z", "verdict": "up",
  "ssh_reachable": true, "tailscale_online": true,
  "boot_utc": "2026-08-30T00:32:27Z", "source": "live", "precision": "precise" }
```

Same boot `43e0c767` as rounds 352 and 358 — the third consecutive E-round on
one boot, which is what made the swap poll survivable and what makes the
open-boot rescan in §4 non-trivial. Tailnet path only; the LAN path remains
unusable from this driver host (round 352 closed that: no
`~/.ssh/id_ed25519_nuc`, no route to `192.168.1.37`).

## 3. Round 304 item 1 — the 8 h swap poll, COLLECTED

Asked for by rounds 304, 310, 316, 322, 328, 334, 340 and 346. Launched by
round 352 (remote pid 2337). Found healthy mid-flight by round 358 at 815 of
~1920 samples. **Completed 10:25:07Z this round** and pulled automatically by
round 352's hand-built local watcher, with no intervention:

```
2026-08-30T10:26:1?Z process gone, pulling final files
 10:26:32 up  9:54,  3 users,  load average: 1.03, 1.01, 0.76
PULL_DONE
```

`state/nuc-swap-watch-r352/swap-watch-r352-{long.json,checkpoint-final.jsonl}`.

```
$ python3 nuc/swap_analysis.py state/nuc-swap-watch-r352/swap-watch-r352-long.json
samples: 1921, span: 8.002h
bursts: 0 (0.000/hour average over the full span)
wide-window rate: 0.00 MB/hr
  tail gap (last burst -> run end): 28807.7s
interior gap stats: not enough bursts (need >= 2 interior gaps)
```

Raw, over all 1921 samples at a median 15.00 s interval:

| series | min | max | nonzero samples |
|---|---|---|---|
| `memory.swap.current` | 0 | 0 | **0 / 1921** |
| `pswpin` pages | 0 | 0 | **0 / 1921** |
| `pswpout` pages | 0 | 0 | **0 / 1921** |
| `memory.current` | 9,770,594,304 | 9,770,594,304 | — |

**Round 352's P14 — "on a fresh, idle boot the 8 h poll will record at least
one swap burst" — is a MISS.** Round 358 predicted that miss (its P3) and is
a HIT.

### 3.1 The result is stronger than "no swap", and it corrects round 136

`memory.current` was not merely stable. Across **1921 consecutive samples
spanning 8.002 hours it did not move by one byte** — `first == last == min ==
max == 9,770,594,304`, zero decreasing steps and zero increasing steps. The
cgroup sat at 30.3 % of its 30 GiB ceiling and was, to the byte, frozen.

That is the datum rounds 130/136/142 were missing. Those three rounds caught
this same cgroup **pinned at the 30.0 GiB ceiling**, with `memory.swap.current`
going 0 B → 310.6 MB → 2.96 GiB. Round 130 asked whether the difference was
elapsed time or load mix. **Round 136 answered "elapsed time alone was
enough". This 8-hour trace refutes that answer.** This boot is now ~10 h old,
its cgroup has been byte-identical for 8 of those hours, and
`memory.events`'s `max` counter is still `0` — the ceiling has not been
touched once. Elapsed time on an idle box buys exactly nothing; the variable
is traffic, which is round 124's original "traffic-diversity-dependent"
reading of the RAM-FAIL verdict, now with a clean negative control behind it.

Read the other way: **`--cap 256` is not intrinsically over-committed.** The
36.0 GB figure in the E4 verdict is a ceiling reachable through expert-cache
diversity, not a resting size. At rest this deployment needs 9.77 GB. That
does not overturn the RAM-FAIL recommendation (a real Hermes workload is
exactly the traffic diversity that walks it to the ceiling) but it does mean
an idle NUC is not in distress, and no round should read "swap is growing"
into a box that has simply been sitting there.

## 4. Round 358's handoff — per-boot journal capture, cached

Round 358 tried ONE `journal-seconds` capture over the whole 4.5-day log span.
It returned `n_seconds: 0` after **1417 s against a 1400 s client timeout**:
`journal_seconds_probe` returns `[]` on *every* failure — correct, fail-closed
— so a too-small timeout became a silent absence of evidence. Its handoff was
"one scan per `boot_id`, cached to `state/nuc-journal-<boot_id>.json` (closed
boots are immutable), timeout sized from that rate."

Built as `reachability_check.py journal-boots` (+ `parse_rate_probe`,
`size_scan_timeout`, `journal_rate_probe`, `boot_scan_targets`,
`merge_captures`). Three properties, each of which earns its place:

1. **Per boot, because a closed boot's journal is immutable.** Only the newest
   boot is ever re-scanned. Boot −2 costs a projected 1944 s on this box;
   paying that once ever rather than once per E-round is the difference
   between the sweep being affordable and it never being run.
2. **Timeout sized from a measured rate.** A 300 s window in the middle of the
   boot is timed *on the box* (`date +%s%N` around `journalctl` alone, so ssh
   setup is excluded) and extrapolated with a 3× + 60 s margin.
3. **The sizing is written into the cache**, and `complete` is `False` unless
   the scan returned inside 95 % of its budget. That is the one signal
   separating "this boot really was quiet" from round 358's "we got cut off",
   and an incomplete capture is not a cache hit — the next sweep re-scans it.

### 4.1 Why one constant could never have worked

Mid-boot rate probe, measured 2026-08-30, all seven boots:

| boot | span | entries/s | projected scan | timeout given |
|---|---|---|---|---|
| −6 | 14.49 h | 0.047 | 6.4 s | 79 s |
| −5 | 34.58 h | 0.037 | 14.5 s | 103 s |
| −4 | 0.15 h | 1.023 | 0.3 s | 60 s |
| −3 | 12.07 h | 0.040 | 5.1 s | 75 s |
| −2 | 39.82 h | **58.850** | **1944 s** | 3600 s |
| −1 | 38.32 h | **45.470** | 644 s | 1992 s |
| 0 | 9.58 h | 0.180 | 4.9 s | 74 s |

**A 1605× density spread across boots of the same machine days apart.** Boots
−5 and −2 have comparable spans (34.6 h vs 39.8 h) and scan costs of 14.5 s
and 1944 s — a 134× difference driven entirely by entry density. Round 358's
single 1400 s constant was ~100× too large for six of these boots and too
small for the seventh. That is not a tuning error; it is the wrong parameter.

### 4.2 A correction to round 358's published rate

Round 358 reported boot −1 at "**81 991 entries (2733/s)**". 81 991 entries in
a 30-minute window is 2733 **per minute** — **45.5/s**, which is what this
round's mid-boot probe measures directly (13 641 entries in 300 s). Round
358's *projection* built on it (~10 min for boot −1) was unaffected, because
it came from the timed scan rather than the rate; the rate itself was wrong by
60×. Anyone quoting it should quote 45.5/s.

## 5. The headline: this box is never quiet for more than two minutes

**All seven boots scanned and cached.** Boot −2, the densest and by far the
most expensive, landed at 1493.5 s against its 1932 s projection with ~15
minutes of round left:

| boot | span | entry-seconds | coverage | scan wall | projected | longest interior silence |
|---|---|---|---|---|---|---|
| −6 | 14.49 h | 1 504 | 2.88 % | 1.9 s | 6.4 s | **118 s** |
| −5 | 34.58 h | 3 921 | 3.15 % | 5.8 s | 14.5 s | **123 s** |
| −4 | 0.15 h | 33 | 5.91 % | 2.2 s | 0.3 s | **81 s** |
| −3 | 12.07 h | 419 | 0.96 % | 2.8 s | 5.1 s | **300 s** |
| −2 | 39.82 h | 97 414 | 67.96 % | 1493.5 s | 1932.4 s | **116 s** |
| −1 | 38.32 h | 76 549 | 55.49 % | 340.0 s | 644.3 s | **115 s** |
| 0 | 9.58 h | 2 783 | 8.07 % | 5.7 s | 4.9 s | **120 s** |

**182 623 entry-seconds cached, and every scan `complete`.** Across **149
hours of running time on seven separate boots, the longest stretch with no
journal entry at all is 300 s — and on six of the seven it is 81–123 s.** The
~116–123 s figure recurring across five boots whose traffic differs by 1605×
is a periodic emitter, not a property of load; it is a property of the
machine.

This is what a bound is for. Round 340 could only say "a reboot is ruled out";
round 358 turned that into "at most G seconds could hide here" but had almost
no interior data to put in G. With G measured, **any reachability-log gap
lying inside a single boot can hide an excursion of at most ~2 minutes.**

### 5.1 What it does to the log — the 14-hour outage was 117 seconds

One log snapshot, three method levels:

| | `unobserved_total` | `bounded` gaps | `max_unobserved_outage` |
|---|---|---|---|
| boot history only | 75h06m29s | 0 | 14h00m00s (`reboot_only`) |
| + 6 boots' journal | 35h14m45s | 20 | 14h00m00s (`bounded`) |
| **+ all 7 boots** | **0h21m56s** | **20** | **0h01m57s** (`bounded`) |

```
$ python3 nuc/reachability_check.py continuity \
    --boot-history state/nuc-boot-history-r364/list-boots-r364.json \
    --journal-seconds state/nuc-journal-cache/merged-r364-all7.json
log_span_human:                  113h50m01s
witnessed_gap_count:             13
bounded_gap_count:               20
unobserved_total_human:          0h21m56s
max_unobserved_outage_human:     0h01m57s
max_unobserved_outage_strength:  bounded
max_unobserved_outage_window:    {from_round: 142, to_round: 154,
                                  from_utc: 2026-08-26T03:19:00Z,
                                  to_utc:   2026-08-26T17:19:00Z}
journal_seconds_loaded:          182623
```

**Over a 113h50m log, the total time in which an unobserved excursion could
be hiding falls from 75h06m29s to 21 minutes 56 seconds — and the worst
single case, the 14-hour rounds-142→154 gap that has headlined this figure
since round 358, is bounded at 117 seconds.** The box was logging
continuously straight through it.

Note the middle row: with six of seven boots the headline had not moved at
all, because the 142→154 gap lies entirely inside boot −2 — the one boot
still scanning. A sweep that had stopped one boot short would have reported
"halved, but the worst case is untouched" and been *technically* true and
substantively wrong. That is an argument for finishing a sweep before
publishing a rollup from it, and it is why the middle row is printed here
rather than quietly dropped.

### 5.2 A number that must NOT be read as a regression

Round 358 published `unobserved_total 67h27m58s`. This round's *baseline*
(same method, no journal) is **75h06m29s**. That is not a regression and not a
contradiction: `state/nuc-reachability-log.jsonl` is append-only and the log
span has grown from ~110 h to 113h50m01s since. This is round 340's "live-file
aggregate pin" hazard, exactly as its next-steps item 4 warned. **Compare
methods on one log snapshot; never compare a rollup across rounds.**

### 5.3 Merging across boots is sound — and my own prediction that it was not, was wrong

`continuity --journal-seconds` and `make_silence_fn` take exactly ONE capture,
so per-boot data has to be unioned before it can be used. P15 predicted that a
merged capture would be *unsafe* — that a `covers` window spanning the
inter-boot OFF stretches would let `interior_silence` report a period the box
was switched off as a bounded "silence" of a running box.

**That is wrong, and the direction of the error is what makes it wrong.**
`interior_silence` produces an UPPER bound on a hidden excursion. A hole in
the merged coverage contains no entry-seconds, so a gap landing there comes
back with a bound equal to its own length — no better than unwitnessed, which
is the correct answer for a period the box was off. A coverage hole can only
*weaken* a bound, never overstate liveness. Merging cannot err unsafely; it
can only decline to help. Pinned as
`test_merged_coverage_hole_weakens_the_bound_it_never_inflates_liveness`.

The per-boot design is still right — for round 358's actual reasons
(immutability, and rate-sized timeouts), not for the safety reason I invented.

## 6. Round 304 item 2 — standing state, all six re-verified

| item | reading | vs round 352 |
|---|---|---|
| `--cap 256` | live in `coli serve` cmdline, unchanged | same |
| E3 prefix-reuse patch | **NOT applied** — 0 markers in `qwen36.c`, mtime `Aug 23 15:27` | same |
| OLMoE tarball | present, 7,420,160,000 B, `Aug 24 16:12` | same |
| `memory.events` | `max 0`, `oom 0`, `oom_kill 0` | same |
| operator | 3–4 users, load 0.00–1.03 (this round's own ssh), no action | same |
| escalation channel | **twelfth** consecutive boot with no operator action | dead since round 166 |

Units `qwen36-colibri` and `qwen36-toolproxy` both `active` (user units).

## 7. Housekeeping: round 363's record landed

The record-gap check flagged round 363 as "has a research-state.md entry AND a
knowledge file but never actually landed in git" — it committed its CODE
(`46c1e88`) and was killed before committing its RECORD. Verified green at
this tree *before* committing (`bash skills/run_checks_fast.sh` → 6 checkers,
0 errors, 1 warning; the warning is the knowingly-carried B002 debt) and
landed unmodified as `8c1311a`.

`languages/whence/SECURITY.md` is deliberately still dirty: a TRACKED file
rewritten by the Hermes gateway, escalated to the operator unresolved by round
349 because its rewrite asserts four security controls that do not exist here.
Round 349's registry `_comment` is explicit that allowlisting a tracked file is
the wrong answer.

## 8. Predictions scored (D-013)

Written to `nuc/predictions-e-round364.md` before any measurement.

| # | claim | result |
|---|---|---|
| P1 | poll completes on its own at 10:25:07Z | **HIT** |
| P2 | final checkpoint holds 1919 or 1920 samples | **MISS** — 1921. Off by one: 1920 intervals plus the sample at t=0. A trivial miss, recorded because the alternative is a habit of rounding predictions to whatever arrived. |
| P3 | swap 0 on every sample; round 352's P14 is a MISS | **HIT** |
| P4 | `mem_current` ends 9.77–10.6 GB, grew < 1 GB | **HIT** (in band) — but the band was far too wide: growth was *exactly zero*. |
| P5 | ceiling never reached, `memory.events` max still 0 | **HIT** |
| P6 | `mem_current` monotone non-decreasing — "the one I most expect to be wrong" | **HIT**, for a reason I did not anticipate: not monotone growth but perfect flatness, 0 changing steps in 1920. |
| P7 | watcher pulls and writes `PULL_DONE` before 10:27:00Z, unaided | **HIT** — 10:26:39Z |
| P8 | boot list unchanged, same 7 boots, boot 0 = `43e0c767` | **HIT** |
| P9 | a 300 s rate probe on a closed boot returns in < 20 s | **HIT** — 0.035–4.07 s of journalctl wall |
| P10 | entry density varies by more than 100× between boots | **HIT**, understated — **1605×** |
| P11 | the full sweep of all 6 closed boots does not finish inside this round | **MISS** — it finished, with ~15 min to spare. The 3× margin on the timeouts made the projections conservative: boots −1 and −2 ran at 53 % and 77 % of projection. |
| P12 | 80 000–400 000 distinct entry-seconds over all boots | **HIT** — 182 623 across all seven |
| P13 | at least one closed boot has an interior silence > 600 s | **MISS** — the worst across all seven is 300 s; six of seven are 81–123 s. I predicted the opposite of the round's best finding. |
| P14 | `unobserved_total` falls but **not below 20 h** — "most of that 67 h is inter-boot time when the box was genuinely OFF, which no journal scan can shrink" | **MISS, by two orders of magnitude** — 0h21m56s. The reasoning was the error, not the arithmetic: I assumed the reachability log's gaps mostly straddled OFF periods. They do not. They sit *inside* boots, which is exactly the case a journal scan answers. I wrote "if I am wrong it will be because the reachability log's gaps mostly sit inside boots" — and that is precisely why. |
| P15 | merging across boots would be unsafe; the CLI takes exactly one capture | **SPLIT** — CLI claim **HIT**; safety claim **WRONG**, see §5.3 |
| P16 | all six standing items unchanged, twelfth boot with no operator action | **HIT** |
| P17 | no restart, no engine request, zero contact with port 8001 | **HIT** |

**12 hits, 4 misses, 1 split.** Every miss is worth more than the hits:

- **P13** and **P14** were wrong in the same direction and for the same
  reason — I assumed a quiet idle box with long journal silences and gaps
  straddling OFF periods. The box is chattier than that by orders of
  magnitude, and its gaps sit inside boots. Being wrong here is what produced
  the result: 21m56s instead of the ">20 h" I committed to in writing.
- **P11** was wrong because the 3× safety margin on the sized timeouts made
  the projections systematically conservative. Worth keeping: a margin that
  makes you finish early is the right failure.
- **P15**'s safety argument was a plausible-sounding invention the code
  refutes (§5.3).
- **P2** was off by one, and **P4**'s band was far too wide for a series that
  turned out to be exactly constant.

## 9. Honest limitations

1. **The sweep is complete for these seven boots only.** Journal retention is
   3.2 G and reaches back to 2026-08-19; anything before that is already lost
   (round 352's finding, unchanged). `merged-r364-partial.json` is the
   six-boot intermediate, kept only because §5.1's middle row cites it —
   **use `merged-r364-all7.json`.**
2. **`unobserved_total 0h21m56s` is a property of THIS log snapshot**, 38
   records over 113h50m01s. It is not a running score. See §5.2.
3. **The bound is an upper bound on a *silence*, not proof of liveness.** An
   arbitrarily short excursion always fits between two journal entries. 115 s
   is a ceiling on what can hide, not a floor on what did not.
4. **Bound resolution still anti-correlates with risk** (round 358's caveat,
   unchanged): the journal is densest when we are ssh-ing into the box and
   sparsest on a quiet unattended gap, which is when an excursion is likeliest.
5. **The swap result is one boot, idle.** It refutes "elapsed time alone is
   enough"; it says nothing about how fast a *loaded* box walks to the ceiling.
6. **Suspend remains unobserved, not excluded** — round 358 checked boot 0
   directly and found nothing; boots −1…−6 are still unchecked for the
   `PM: suspend entry` / `Freezing user space` signature.

## 10. Hygiene

No writes on the box outside the pre-existing `~/nuc-research/` poll outputs;
`/work/**` read-only throughout. No unit restarted. **Port 8001 never
contacted.** No engine request of any kind — every probe was
`journalctl`/`ps`/`cat`/`systemctl --user is-active` over ssh.

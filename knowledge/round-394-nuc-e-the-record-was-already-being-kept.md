# Round 394 (NUC-integration E) — the record was already being kept

**Track:** NUC-integration (E). **Box:** UP for the whole round, boot
`43e0c767e98e41c5a2c0d475a15e06cf` (booted 2026-08-30T00:32:27Z) — the same
boot as rounds 352/358/364/370/376/382/388, uptime 1d 8h39m at first contact
(2026-08-31T09:11:22Z). **Eighth** consecutive E-round on this boot.
**Predictions (D-013):** `nuc/predictions-e-round394.md`, banked at 09:14Z,
scored in §9 — **13 HIT / 9 MISS** of 22 scored.
**NUC-side record:** `/work/logs/nuc-perturbation-r394.md`.
**Hygiene:** READ-ONLY on `/work/**`; no unit restarted; **port 8001 never
contacted**; **no engine request of any kind**. Disclosures in §10.

---

## 1. Two questions, one answer: nobody had read the samplers

Round 388 handed forward an unexplained event and a warning:

> *item 2* — the 01:50–02:00 bucket is unexplained: 67.7 MB swapped out,
> +147 MB `Committed_AS` that persisted, ~4 CPU-seconds, **zero journald
> entries**.
> *item 7* — `apt` is a first-class perturbation source. Any future A/B must
> record whether a housekeeping timer fired inside the measurement window.

Both were answered by reading things that had been recording continuously and
that nothing in this track had ever opened: `sar -r`, the journal without a
filter, and a file's mtime. The same archives then overturned a capacity
figure three rounds had published.

**There were 21 journal entries in that window.** One of them is the cause.

## 2. `fwupd-refresh`, at 01:57:33Z, named in the log the whole time

```
2026-08-31T01:57:33Z systemd[1]: Starting fwupd-refresh.service …
2026-08-31T01:57:33Z fwupdmgr[42653]: Updating lvfs
2026-08-31T01:57:35Z fwupdmgr[42653]: Successfully downloaded new metadata
```

Corroboration, none of it from the journal:

| witness | value | reading |
|---|---|---|
| `/var/cache/fwupd/metadata.xmlb` | 15,586,525 B, **mtime Aug 31 01:57** | filesystem witness, inside the bucket |
| `fwupd` (pid 1256) `VmHWM` | 192,760 kB | it *did* reach ~193 MB this boot |
| `VmRSS` now | 45,912 kB | the balloon deflated |
| `VmData` | 185,468 kB | the commitment did **not** |
| `VmSwap` | 0 kB | released with `MADV_DONTNEED`, never swapped |
| `sar -r kbcommit` | +147,092 kB at 02:00:05, never returns | the step |
| `sar -n DEV` rx | 1.78 → 5.23 kB/s | the download |
| `sar -b bread/s` | 0.03 → 8.33 | 2.5 MB read |
| `sar -u` | 0.09 → 0.16 % user | ~1.7 CPU-seconds |

Mechanism: libxmlb rebuilds the 15.6 MB binary-XML silo, and the parse balloons
fwupd's heap ~147 MB. On a box with 0.28 GB free that forces global kswapd
reclaim — 62 MB of page cache dropped **and 67.7 MB of the engine's resident
weights written to swap**. fwupd then frees the buffers; glibc returns the
pages with `MADV_DONTNEED`, so RSS falls and the *commitment* does not. The
engine's 67.7 MB never comes back: `workingset_refault_anon` is 0, because
nothing touches those weights.

**The largest single perturbation of this deployment is `apt`. The second is a
firmware-metadata parse.** Neither has anything to do with inference.

**Graded honestly: attributed, not proven.** No per-process memory history
exists on this box, so this is coincidence in time (to the minute, from a
filesystem stamp), magnitude agreement (`VmData` 185 MB vs a +147 MB step on a
~38 MB base), and a mechanism — not a demonstration. The falsifier is one
read: watch `fwupd`'s `VmData`/`VmHWM` across a forced
`systemctl start fwupd-refresh.service`. That is a write action and is left to
the operator.

## 3. Why it looked unexplained: there are two channels and round 388 had one

| | 01:57 fwupd | 03:50 apt-daily |
|---|---|---|
| channel | **commitment** | **page cache** |
| `kbcommit` | **+147,092 kB, persistent** | −1,620 kB |
| `pgpgin/s` | 4.17 (2.5 MB) | **554.76 (333 MB)** |
| `kbcached` | −62,224 kB | **+141,176 kB** |
| engine swapped out | 67.7 MB | 218.3 MB |

Round 388 read `sar -W` and `sar -B`. Both events appear there; only the apt
one is *explicable* there, because `pgpgin` is the page-cache channel's
instrument and there is no paging signature when a process simply mallocs.
**`sar -r` is the missing instrument.** It has sampled every 10 minutes since
this box booted.

The accounting closes exactly, which is the check that the channels are real
and not a story: system `pswpout` since boot is 72,044 pages; the four
non-zero `sar -W` buckets sum to 72,204; the qwen36-colibri cgroup holds 67,024
pages of swap and every other cgroup on the box holds 5,168 — 12 pages from the
72,192 that `/proc/meminfo` says are in use.

## 4. Three controls — the thing round 388 never had

Round 388's gap (04:52Z → 09:11Z) contains three named housekeeping runs, and
**all three cost the engine nothing**:

| unit | fired | engine cost |
|---|---|---|
| `motd-news.service` | 05:10:05Z | 0 pages |
| `apt-daily-upgrade.service` | 06:20:33Z | 0 pages |
| `fwupd-refresh.service` | 07:49:05Z, 08:43:33Z, 09:07:14Z (+5 more) | 0 pages |

`fwupd-refresh.service` fired **34 times this boot and downloaded 26 times**;
**exactly one of the 34 cost anything.** So a named event in the window is not
a cost, and the timer identity does not predict the cost. Attribute to the
bucket that *moved*; let the unit name be corroboration.

This is the branch the bank flagged in advance as the more interesting one
(P9): a named housekeeping run that cost nothing is a control arm, and round
388 reported "apt is the largest perturbation" with no control at all.

## 5. You cannot schedule around these timers — the guard is the only move

```
fwupd-refresh.timer      OnCalendar=*-*-* *:00:00   RandomizedDelaySec=1h
apt-daily.timer          OnCalendar=*-*-* 6,18:00   RandomizedDelaySec=12h
apt-daily-upgrade.timer  OnCalendar=*-*-* 6:00      RandomizedDelaySec=60m
```

For the first two the **randomization equals the period**, so the fire time is
uniform over the whole period and no quiet slot exists. A one-hour measurement
window contains a `fwupd-refresh` fire with probability 1.0. `apt-daily`'s
03:50Z fire that round 388 read as a fixed daily time is a draw from a 12-hour
uniform; its next is 10:22:25Z.

So round 388's handoff — *record whether a timer fired* — is not merely good
practice, it is **the only available practice**. `nuc/perturbation.py`'s
`window_guard` therefore never returns `clean` for this box; the verdict is
`contaminated_by_construction` with the required practice named.

## 6. The expert-cache fill curve had been recorded, at 10-minute resolution

`sar -r` on `sa30` — the boot's own day — bracketed both of the boot's two
completions:

| bucket (2026-08-30) | `kbcommit` | step |
|---|---|---|
| 13:20:05 — before request 1 | 5,476,700 | — |
| 13:30:05 — after request 1 (13:28:25Z) | 23,472,692 | **+17,995,992 kB = 17.16 GiB** |
| 14:50:05 — before request 2 | 23,484,980 | — |
| 15:00:05 — after request 2 (14:54:08Z) | 30,634,440 | **+7,149,460 kB = 6.82 GiB** |
| 15:30 → 2026-08-31 01:50 | 30,634,440 | flat |

Round 376 wanted a per-request slot denominator. Round 388 predicted (P6) and
confirmed that the journal carries no per-completion token counts and concluded
"the denominator round 376 lacked is not recoverable that way". **That is true
of the journal and false of the box.** Request 1 = 5,513 slots, request 2 =
2,190 slots, decay ratio 0.397.

A difference of two archived samples beats an inversion of one live reading:
it needs no baseline and no model.

## 7. The baseline was a residency reading too — and it is ~2x too large

`NUC_BASELINE = 9,770,594,304` is a **`memory.current`** value: round 364
polled it 1,921 times over 8.002 h before this boot's first completion and got
the identical value every time. Round 388's whole finding was that
`memory.current` is residency, and it replaced the inversion's **numerator**
with `anon + swap.current` — then left the **denominator** as a
`memory.current` reading, with a docstring arguing:

> *"Round 364's 9,770,594,304 was taken with `swap.current == 0`, so it serves
> for both."*

`swap.current == 0` makes `anon + swap == anon`. It does **not** make
`memory.current == anon`. `memory.current = anon + file + kernel + …`, and
`sar -r` shows `kbcached` at **8.15 GB** during exactly that window — the model
file the engine had been reading, charged to the cgroup. The baseline is
inflated by roughly that page cache.

Three independent routes to the true zero-slot **allocation**, and a measured
figure to test them against — the sum of the two request steps, 25.75 GB:

| route | baseline | implied growth | error |
|---|---|---|---|
| model on disk minus packed experts | 4,911,876,493 | 25.69 GB | **−0.23 %** |
| `Committed_AS` pre-request, less non-engine | 4,688,752,640 | 25.91 GB | **+0.63 %** |
| `sar kbmemused` pre-request, less non-engine | 4,783,235,072 | 25.82 GB | **+0.27 %** |
| **modelled residency baseline** | 9,770,594,304 | 20.83 GB | **−19.10 %** |

The three routes share no input — disk geometry, `Committed_AS` minus the
engine's own `VmData`, and `sar`'s anonymous+slab column — and they agree
inside 0.7 % while the modelled one misses by 4.9 GB. `baseline_witness()`
ships this test; it is a difference of observations, not a second model.

**Corrected state of this deployment:**

| | published (r388) | **corrected (r394)** |
|---|---|---|
| slots loaded | 6,232 | **7,686 – 7,753** |
| fill | 60.9 % | **75.1 – 75.7 %** |
| cap-equivalent | 155.8 | **192.1 – 193.8** |
| terminal footprint at `--cap 256` | 43.996 GB | **39.137 GB** |
| sound `--cap` band | [129, 167] | **[129, 204]** |

### The recommendation moves 159 → 196, and round 124 was right

* **Floor 129 unchanged** — the PILOT prefetch queue is 128 deep
  (`qwen36.c:2000/2005`). Round 124's `--cap 16`/`64` stay retracted.
* **Ceiling 204** — the largest cap whose terminal footprint fits `memory.max`
  (32.21 GB). At 205 the cgroup limit binds before the engine's LRU.
  **Round 124's E4 headline was `--cap 204`.** Round 376 rejected it as "over
  by 4.83 GB", round 388 softened that to "over by 0.537 GB" against RAM+swap.
  Both figures were computed from the residency baseline. It fits.
* **`--cap 196`** keeps 1.10 GB of margin against `memory.max` — 4.9x the
  0.223 GB spread between the three routes — and is bounded by the engine's own
  LRU rather than by the kernel.
* Corroboration that uses no model at all: **the box is running at
  cap-equivalent ~192–194 right now, with `memory.events max == 0`.** Round
  388's `--cap 159` would discard ~4.4 GB of usable expert cache.

Round 388's *argument* survives intact and is what makes 196 safe rather than
lucky: at `--cap 256` the engine's own LRU can never engage, so the OOM killer
is the only bound. That is still true — 39.14 GB exceeds both 32.21 GB and
RAM+swap's 36.51 GB. Only the number changed.

### Still unsafe to send a probe — now from measurement as well as from source

Round 388 derived "unsafe" from `qwen36.c`: `topk = 8` × 40 layers ⇒ ≤320
uncached slots/token against 456 slots of headroom. The measured curve agrees
independently: request 3, extrapolated at the observed 0.397 decay, costs
**~870 slots against 456 — 1.906x.** The fit would have to be overstated by
47.5 % before the verdict changed. **No engine request was sent** (P17, banked
before the measurements that would have tempted it).

## 8. What was built

**`nuc/perturbation.py` (new, 36 tests).** Pure text-in/dict-out: it parses
`sar` tables and timer definitions a caller has already captured, opens no
socket and runs no command, so it is importable from any track and cannot
reach port 8001.
* `parse_sar` — handles the banner, `LINUX RESTART`, the `Average:` row,
  repeated headers and 12-hour stamps; **raises** on a short row rather than
  mis-aligning, because a silently mis-aligned column is how this round's
  mystery would have been mis-attributed.
* `commit_steps` — the fwupd finder. Grades a rise **persistent** only if the
  next N buckets hold it. On the real capture it returns exactly one persistent
  step: 02:00:05, +147,092 kB. The 03:50 rise (an ssh session) is graded
  transient, and a step at the end of the file is graded *not* persistent,
  because a verdict with no lookahead would launder every blip.
* `swap_excursions` — rate × interval × page size, with the interval an
  explicit parameter since getting it wrong rescales everything.
* `classify_bucket` — `page_cache` / `commitment` / `both` / `unattributed` /
  `quiet`. `unattributed` is kept as a verdict so a future gap is *named*
  rather than forced into a channel.
* `Timer.avoidable` / `window_guard` — §5.
* `attribute` — puts an event into the bucket it falls in. Buckets are labelled
  by their END, so 01:57:33 belongs to 02:00:05; there is a test for that
  off-by-one and for the exact-boundary case.

**`nuc/expert_cache.py` (extended, 14 tests).** `baseline_witness`,
`alloc_baseline_band`, `fill_curve`, `request_cost_series`, `recommend_cap`,
and CLI modes `baseline` / `curve` / `recommend`. Every new constant is derived
from a named observation; the audit went **19 constants / 14 derived (0.737)**
to **20 / 15 (0.750)**, 0 transform risks.

**Two skills**, both `skill_lint --house` clean, both with trigger cases
(`skills/trigger-cases.json`, 200 → 210) so they can actually be probed:
* `skills/residency-is-not-allocation/` — **round 388 announced this skill in
  its knowledge file and never created the directory.** Written now, because
  this round supplies the second instance (the baseline), which is what turns
  one anecdote into a pattern and which is the instance that moved a published
  number.
* `skills/instruments-already-running/` — the technique that produced both of
  this round's findings.

### Three bugs my own tests found, all in code I had just written

1. **`classify_bucket` graded 2.5 MB a page-cache surge.** A ratio test against
   an idle baseline of ~0.1 KB/s fires on anything; 4.17 KB/s is 41x the
   baseline and is a rounding error. Fixed with an absolute floor
   (`min_pgpgin_s = 50` KB/s ≈ 30 MB/bucket), plus a regression test that
   asserts the ratio-only version *would* have got it wrong.
2. **De-duplicating `PAGE_BYTES` broke the script entry point.** The constant
   audit flagged my `PAGE_BYTES = 4096` as restating
   `swap_analysis.DEFAULT_PAGE_BYTES` — the "one constant, two modules" shape
   rounds 382 and 388 each spent a round finding *after the fact*, caught here
   at authoring time. Importing it broke `python3 nuc/perturbation.py`, because
   `nuc` is not importable when the file runs as a script, and every test used
   `-m`. Both forms now work and both are tested.
3. **A docstring of mine overclaimed.** It said the request-3 estimate "would
   have to be wrong by half to change the verdict". The ratio is 1.906;
   halving 870.2 gives 435.1, *below* the 456.5-slot headroom, so the verdict
   would have flipped. The claim is now the one the arithmetic supports, and
   `test_the_docstrings_robustness_claim_is_the_one_the_arithmetic_supports`
   pins the 1.906 so prose and arithmetic cannot drift apart.

## 9. Predictions scored (D-013)

| # | prediction | outcome |
|---|---|---|
| P1 | box UP, same boot, no suspend | **NOT SCORED** — observed at 09:11:22Z before the bank, labelled so in the bank |
| P2 | completion counter still exactly 2 | **HIT** |
| P3 | `anon + swap.current` still exactly 30,600,970,240 | **HIT** — the round's headline prediction, and the invariant now holds across a *second* observation window |
| P4 | `swap.current` has GROWN; `peak == current` | **MISS** on the headline — byte-identical at 274,530,304. The `peak == current` half held |
| P5 | `memory.current` has FALLEN below 30,412,222,464 | **MISS** — byte-identical |
| P6 | no cgroup-limit pressure; `pgscan_kswapd` strictly increased | **MISS** on the last clause — `pgscan_kswapd` is 2,587,671, unchanged. Everything else held: `memory.events` all 0, `pgscan_direct` 0, `allocstall_*` 0, `workingset_refault_anon` 0 |
| P7 | `apt-daily-upgrade` ran in the gap, in [05:50, 07:00] | **HIT** — 06:20:33Z |
| P8 | it moved less than `apt-daily` did | **HIT** — it moved nothing |
| P9 | ≥1 non-zero `pswpout` bucket in 05:50–07:00 | **MISS**, and the bank named this as the more interesting branch: a named housekeeping run that cost nothing is §4's control arm |
| P10 | 03:50 is a randomized draw and will not repeat | **HIT** — `RandomizedDelaySec=12h`, next fire 10:22:25Z |
| P11 | `sa31` still present; `sa30` present | **HIT** |
| P12 | the engine *process* owns ≥90 % of the box's swap | **MISS** on the literal wording — `qwen36` holds 253,520 of 288,768 kB = **87.8 %**. The qwen36-colibri *cgroup* holds 92.8 %; the 5.0-point difference is the `coli serve` python3 supervisor, 14,576 kB, which accounts for the cgroup's swap to the byte |
| P13 | I will NOT identify the 01:50–02:00 bucket | **MISS**, deliberately stated in the direction I would rather be wrong in — §2 |
| P14 | the +147 MB commit step is NOT the engine | **HIT**, three ways: the cgroup's allocation is byte-identical across it; `VmData − (RssAnon + VmSwap)` is 23,408 kB, far too little to hold 147 MB untouched; `VmPeak == VmSize` |
| P15 | the standing six unchanged, SEVENTEENTH check | **HIT, all six** |
| P16 | exactly one `unpacking to int8 in slot` line | **HIT** |
| P17 | no engine request; port 8001 untouched; no restart | **HIT** |
| P18 | corrected headroom now below 456 slots | **MISS** — 456.5 slots and 274,206,720 B of overstatement, both byte-identical to round 388 |
| P19 | audit unchanged at 19/14/0.737/0 | **MISS** — 20/15/**0.750**/0. The bank said "if the new module trips it I will fix the module, not the audit", and that is what happened (§8, bug 2) |
| P20 | 499 tests green before my changes | **HIT** exactly. 551 after |
| P21 | `nuc/run_checks_fast.sh` still not wired into `run_driver.sh` | **HIT** — 0 references |
| P22 | `unobserved_total` grows; max stays 0h02m01s; `missed_excursions` `[]` | **MISS** on the headline — it *fell*, 0h29m20s → **0h12m00s**. The other two clauses held. See below |
| P23 | `SECURITY.md` still dirty, 30 ins / 7 del | **HIT** on the diff, which is byte-identical. The "fourteenth consecutive round" half of the prediction is **withdrawn as unverifiable**: round 388 says 13 and round 393 says 15, five rounds apart, so no consistent tally exists to be right or wrong about |

**13 HIT / 9 MISS of 22 scored** (P1 excluded by the bank itself).

**The misses have one shape.** P4, P5, P6 and P18 are all *"the number will
move"* and it did not — four predictions, one error, made after reading round
388's own P13 miss (which was the same error in the opposite direction: it
predicted `max_unobserved_outage` would move because the previous round had
found that it *could*). Round 388 turned "it can move" into "it will"; I read
that miss and made it again on four different counters. **The lesson that
transfers is not about any of these numbers — it is that "this number moved
last time" is not evidence about next time.** The honest form of P4/P5 was:
"unchanged unless a perturbation occurred in the gap; here is what would count
as one" — which is exactly the instrument this round then built.

**P22 is a methodology finding, not a miss about the box.** `unobserved_total`
fell while a 4h19m gap was added, because `journal-boots` rescanned the open
boot and grew the merged capture 185,182 → **185,768** entry-seconds, which
*bounded* interior silence that was previously unbounded. So the figure is a
**current best bracket, not a running total**, and round 388's 0h29m20s and
this round's 0h12m00s are two brackets of different tightness rather than a
trend. Nothing in the tool says so, and a future round comparing them as a
series would read an improvement in coverage as an improvement in uptime.

## 10. Disclosures

- READ-ONLY on `/work/**`; no unit restarted; port 8001 never contacted; **no
  engine request of any kind**. One write on the box, in an allowed path:
  `/work/logs/nuc-perturbation-r394.md`.
- **Twelve** ssh/scp connections: the bare reachability probe, `reachability_
  check.py check`, six hand-written read-only diagnostic sessions, the
  boot-history capture, `journal-boots` (which opens its own, plus a rate
  probe), the `scp`, and one `ls` to verify it landed.
- The bare `echo/date/uptime` probe and `reachability_check.py check` both ran
  **before** the predictions bank was written — `check` is the round's mandated
  first instrument. P1 is labelled NOT SCORED in the bank itself for that
  reason.
- `journal-boots` merged **185,768** entry-seconds across 7 boots
  (`state/nuc-journal-cache/merged-r394-all7.json`), 6 boots served from cache,
  boot 0 rescanned. `continuity` ran twice — once without the journal capture,
  which is what exposed §9's P22 finding.
- **Round 388 announced `skills/residency-is-not-allocation/` in its knowledge
  file (§9, "New skill: …") and the directory does not exist.** Its own
  disclosures say "the one skill file edited is `skills/lazy-fill-ceiling/
  SKILL.md`", so the two statements contradict each other inside one round's
  own record. Created this round.
- **Round 388's "zero journald entries between 01:45 and 02:05" is factually
  wrong** — there are 21, including the three-line `fwupd-refresh` block that
  is this round's §2. Recorded plainly because the claim was load-bearing: it
  is why the event was carried forward as a mystery rather than solved in the
  round that found it.
- `skills/run_checks_fast.sh` went ERROR-red **three separate times inside this
  round, each from this round's own work**, and is **0 errors / 6 warnings** at
  round end — the same warning profile it had at round start. In order:
  (a) `carryforward K001` + `unit_tests rc1`, from banking
  `nuc/predictions-e-round394.md` with no ledger entry — the round-369 ledger
  working exactly as designed; cleared by adding the entry with §9's score.
  (b) `case_coverage P001` — the two new skills had **0 positive trigger
  cases** against a floor of 3; cleared by adding 8 positive and 2 negative
  cases to `skills/trigger-cases.json` (200 → 210). A skill with no cases
  cannot be probed and cannot regress, so this is the corpus refusing an
  unprobeable skill, not a formality.
  (c) `claim_check C001`, 3 stale paths — all three in ONE verification block
  of `residency-is-not-allocation`: an ellipsis cgroup path
  (`/sys/fs/cgroup/user.slice/.../…`) and, less obviously, the two regex
  fragments of `awk '/^anon /{print $2}'`, which the checker reads as paths.
  Rewritten to `grep`-based commands that a reader can also copy without
  having to fill in a cgroup path.
  Final: `skill_lint` 49 skills / 0 errors / 0 warnings; `claim_check` 0 stale;
  `xref_check` 0 dangling in the authoritative scope; `carryforward` 0 errors;
  `unit_tests` **695 passed**.
- `nuc/tests`: **499 → 551** (+52), all green. `nuc-checks PASS (pytest rc=0,
  audit rc=0)`; constant audit 20 constants / 15 derived (0.750) / **0
  transform risks**.
- `nuc/run_checks_fast.sh` is still NOT wired into `run_driver.sh` — harness(A)'s
  file, round 388's handoff item 5, unchanged.
- `languages/whence/SECURITY.md` remains dirty and escalated — the same
  30-insertion/7-deletion diff round 388 recorded. **The round count attached
  to it is unreliable and is not restated here:** round 388 published "13
  consecutive rounds" and round 393, five rounds later, published "15". Both
  cannot be a per-round tally, and neither round re-derived it. This is round
  321's item 14 / round 333's widening — "any line asserting a number that no
  round re-executes" — arriving for a fourth time, in the one line every
  recent round copies forward. The observable is the diff. The untracked
  `whence_qwen_bridge.py` / `pyproject.toml` / `examples/*.lang` are still not
  E's files to resolve.

## 11. Next E round, in order

1. **Prove or drop the fwupd attribution.** One read settles it: capture
   `fwupd`'s `VmData`/`VmHWM` before and after a forced
   `systemctl start fwupd-refresh.service`. It is a write action on the box and
   needs operator sign-off; until then §2 stays graded *attributed, not
   proven*.
2. **Blocked on the operator, SEVENTEENTH check — and the ask has changed.**
   The `--cap` recommendation is now **196, not 159**, the ceiling is **204,
   not 167**, and round 124's original E4 headline is vindicated. The E3
   prefix-reuse A/B is unchanged. Any A/B must record the housekeeping fire
   history for both arms (§5).
3. **`unobserved_total` is a bracket, not a total** (§9, P22). Either rename it
   in `reachability_check.py` or emit the journal-coverage figure alongside it,
   so a future round cannot read a coverage improvement as an uptime
   improvement.
4. **Round 370's item 3 still needs a FRESH boot** — poll at ~5 s and watch for
   `unpacking to int8 in slot`. Eighth round on `43e0c767`. The polling target
   is `anon + swap.current`, and with §6 in hand the *right* poll is now
   `sar -r`'s own 10-minute series plus a 5 s poll only across the request.
5. **Harness(A) owns wiring `nuc/run_checks_fast.sh` into `run_driver.sh`** —
   four lines in the round-277 concurrent block plus a `nuc-health-check` log
   line, mirroring the whence check. Round 388's item 5, unchanged; nothing
   under `nuc/` still runs outside an E round.
6. **Skills(B): a round can announce a skill and not create it, and no checker
   notices** (§10). `carryforward_check.py` catches an unscored predictions
   bank by sweeping the repo for bank filenames; the same shape — sweep
   `knowledge/*.md` for "New skill: `skills/<name>/`" and require the directory
   — would have caught this in round 388's own session. Round 388's item 6 (a
   description edit resets probe history) is unchanged.
7. **The two new skills are never-probed**, like most of the corpus. A probe is
   a priced live run and is deliberately not launched from an E round; fold
   both into a skills(B) batch.
8. Round 382's item 5 (OLMoE's geometry is document-derived, not
   allocator-derived) is unchanged — if the lane is ever built, read the
   allocator FIRST.

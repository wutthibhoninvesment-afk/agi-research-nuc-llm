# Round 394 (NUC-integration E) — PREDICTIONS, written before measurement

Written 2026-08-31T09:14Z. Banking rule D-013: predictions first, then measure,
then score misses honestly.

Baseline = round 388 (`knowledge/round-388-nuc-e-the-plateau-that-was-an-instrument.md`,
`nuc/predictions-e-round388.md`), taken 2026-08-31T04:52:43Z on boot
`43e0c767e98e41c5a2c0d475a15e06cf` (booted 2026-08-30T00:32:27Z).
Now is ~4h19m later. This is the **eighth** consecutive E-round on this boot.

**Disclosure up front:** the standing `reachability_check.py check --round 394`
ran at 09:11:22Z, i.e. **before** this file was written, because it is the
round's mandated first instrument. Its output (`verdict up`, `boot_utc
2026-08-30T00:32:27Z`, `slept_this_boot false`) is therefore an OBSERVATION,
not a prediction, and P1 below is marked NOT SCORED. The bare reachability
`echo/date/uptime` probe that preceded it is in the same class. Nothing else in
this round had been measured when this file was written: no cgroup read, no
journal read, no `sar` read, no `/proc` read, no source read.

## Part 1 — the allocation invariant (handoff item 1)

Round 388's headline was that `anon + swap.current` was byte-identical across a
458 MB residency swing, because allocation below `--cap` is monotone
(`slot_ensure_allocated` opens `if (s->g) return;`). That was ONE observation
of the invariant across ONE reclaim event. This round is the first chance to
test it against a second, independent event.

**P1 (NOT SCORED — already observed).** Box UP, same boot, `boot_utc`
2026-08-30T00:32:27Z, `slept_this_boot false`.

**P2. The completion counter is still exactly 2 for this boot.** No third
`POST /v1/chat/completions` since 2026-08-30T15:11Z — 18h00m by now. The only
traffic sources are the operator (absent since 2026-08-26 19:24) and Hermes;
the previous 13h38m produced zero. Confidence: high.

**P3. `anon + memory.swap.current` is still exactly 30,600,970,240 B.** This is
the round's headline prediction and the direct test of round 388's claim. Under
zero traffic nothing mallocs and nothing frees, so the sum is invariant no
matter how the kernel redistributes it between RAM and swap.
Confidence: high. Falsified by any other value.

**P4. `memory.swap.current` has GROWN and is ≥ 274,530,304 B**, and
`memory.swap.peak == memory.swap.current` (monotone, nothing faulted back).
Rationale: `workingset_refault_anon` was 0 and a page only faults back when
touched; with zero traffic nothing touches the swapped weights. Meanwhile at
least one more housekeeping window (P7) has elapsed. Confidence: medium-high on
growth, high on `peak == current`.

**P5. `memory.current` has FALLEN below 30,412,222,464 B** — i.e. the reading
rounds 370/376/382 called a plateau moves for the second consecutive round.
Confidence: medium-high (it is P4 with the opposite sign, plus non-anon slop).

**P6. Still zero pressure from the cgroup's own limit.** `memory.events`
low/high/max/oom/oom_kill all 0; cgroup `pgscan_direct` 0 and system
`allocstall_dma/normal/movable` 0; `pgscan_kswapd` > 2,587,671 and
`pgsteal_kswapd` > 1,975,157 (both strictly increased);
`workingset_refault_anon` still 0. Every page of any new reclaim is global
kswapd, as in round 388. Confidence: high.

## Part 2 — `apt` as a first-class perturbation (handoff item 7)

Round 388 found `apt-daily.service` (03:50Z) accounted for 218 MB — 76 % — of
the boot's swap-out, and handed forward "any future A/B here must record
whether a housekeeping timer fired inside the window". The gap since round 388
(04:52Z → 09:11Z) contains `apt-daily-upgrade.timer`, which round 388 put at
~06:20 UTC. That makes this round a natural second trial.

**P7. `apt-daily-upgrade.service` ran inside the 04:52Z–09:11Z gap**, at a time
in [05:50Z, 07:00Z], and journald names it. Confidence: high that it ran,
medium on the window.

**P8. It moved LESS memory than `apt-daily` did.** Specifically: the largest
`pswpout/s` bucket attributable to it is < 89.88/s (round 388's 03:50–04:00
figure) and the bytes it swapped are < 218 MB. Rationale: `apt-daily` is the
metadata refresh (`update`, plus `apt-news`/`esm-cache`/`packagekit` activation
— several hundred MB pulled through page cache); `apt-daily-upgrade` on a box
with nothing to install does far less work. Confidence: medium.

**P9. At least one non-zero `pswpout/s` bucket exists in `sar -W` between
05:50Z and 07:00Z** — i.e. the perturbation is visible in the instrument, not
just in the journal. Confidence: medium. If P7 holds and P9 fails, that is the
more interesting outcome: it would mean a named housekeeping run that cost the
engine nothing, which is the control arm round 388 never had.

**P10. `apt-daily.timer` will ALSO have fired again** — no. Its window is
06:00–18:00 randomized in Ubuntu's shipped unit, not a fixed 03:50, so I
predict the 03:50 figure round 388 quoted is `apt-daily.timer`'s *randomized*
fire time for that day and will NOT repeat at 03:50 tomorrow. Confidence:
medium-low; this is a prediction about the unit file, which I have not read.

## Part 3 — the unexplained 01:50–02:00 bucket (handoff item 2, TIME-CRITICAL)

Round 388: 67.7 MB swapped out in the bucket ending 02:00:05, `Committed_AS`
+147 MB persisting, ~4 CPU-seconds, and **zero journald entries** between
01:45 and 02:05. `sa31` rotates at 2026-09-01T00:07Z.

**P11. `sa31` is still present and readable now**, and covers 00:00Z through
~09:00Z today. `sa30` is also present and covers 2026-08-30 from the 00:32
boot. Confidence: high.

**P12. Per-process `VmSwap` will show the engine process owns ≥ 90 % of all
swap in use on the box.** Rationale: the cgroup holds 274.5 MB and the engine
is by far the largest anonymous working set. Confidence: medium-high.

**P13. I will NOT identify the 01:50–02:00 bucket's cause.** Zero journald
entries is a strong negative; `sar` has 10-minute granularity and no
per-process attribution; `sa30` covers a different day. I expect to narrow it
(e.g. rule in/out the engine as the *source* of the allocation via `VmSwap`
arithmetic) and to record it as still unexplained. Confidence: medium — stated
so that "narrowed but unexplained" is scored a HIT and "identified" is scored a
MISS in my favour, which is the honest direction for a prediction I would
rather be wrong about.

**P14. The +147 MB `Committed_AS` step is NOT the engine.** The engine's
allocation is monotone below `--cap` and P3 asserts its total is unchanged
across the whole boot; a +147 MB commit that persisted must therefore belong to
something else. Confidence: medium-high. If P3 holds and P14 fails, P3 is
wrong.

## Part 4 — standing state (handoff item 4, SEVENTEENTH check)

**P15. The standing six unchanged, SEVENTEENTH consecutive check.** `--cap 256`
live; E3 patch NOT applied (0 markers in `qwen36.c`, mtime
2026-08-23T15:27:33Z); OLMoE tarball 7,420,160,000 B; `memory.events max` 0; no
operator login since 2026-08-26 19:24; both user units `active`. Confidence:
high.

**P16. Exactly one `unpacking to int8 in slot` line** in the engine journal for
this boot, unchanged — it is the turn-1 artefact and no third request has
arrived. Confidence: high, conditional on P2.

**P17. No engine request of any kind will be sent this round.** Round 388's
arithmetic (topk 8 × 40 layers = ≤320 uncached slots/token against 456 slots of
headroom ⇒ 1 token worst case, 3 expected) has not changed in this round's
favour; P4 predicts headroom has *shrunk*. Port 8001 never contacted; no unit
restarted. Banked as a decision, before the measurements that would tempt it.

**P18. The corrected headroom is now BELOW 456 slots.** If P3 holds, allocated
bytes are unchanged, so headroom against `memory.max` is unchanged in the
allocation model — but the RAM-plus-swap axis has less swap left. I predict
`expert_cache.py snapshot` reports the same `headroom_bytes` (allocation) and a
larger `headroom_overstatement_bytes` (residency artefact) than round 388's
274,206,720. Confidence: medium.

## Part 5 — this repo

**P19. `nuc/constant_audit.py` is unchanged: 19 constants, 14 derived (0.737),
0 transform risks**, before and after this round's edits — the audit grades
defining expressions and this round adds a module whose constants are derived.
Confidence: medium-high (the new module could trip it; if it does I will fix
the module, not the audit).

**P20. `nuc/tests/` is 499 tests, all green, before my changes.** Confidence:
high. After: strictly more, all green.

**P21. `nuc/run_checks_fast.sh` (round 388) is still NOT wired into
`run_driver.sh`** — it was handed to harness(A) and harness(A) ran at round 391
with a different focus (the turn budget). Confidence: medium-high.

**P22. Continuity.** `unobserved_total` grows by roughly this round's own gap;
`max_unobserved_outage` stays at **0h02m01s** (round 388 predicted it would
move and it did not; I am predicting the opposite of my predecessor's miss
deliberately). `missed_excursions` `[]`. Confidence: medium-high.

**P23. `languages/whence/SECURITY.md` is still dirty and escalated** with the
same 30-insertion/7-deletion diff — **fourteenth** consecutive round. Not E's
file to resolve. Confidence: high.

# Round 382 (NUC-integration E) — PREDICTIONS, written before any measurement

Written 2026-08-31T00:05Z, **before** the first ssh of this round and before
reading `nuc/fast_lane.py` / `nuc/expert_cache.py` for this round's code work.
Banking rule D-013: predictions first, then measure, then score misses honestly.

Baseline = round 376 (`knowledge/round-376-nuc-e-the-cache-that-cannot-fill.md`,
`nuc/predictions-e-round376.md`), taken 2026-08-30T19:53Z on boot
`43e0c767e98e41c5a2c0d475a15e06cf` (booted 2026-08-30T00:32:27Z).
Now is 4h11m later.

## Part 1 — the box (handoff item 1, time-sensitive)

**P1. The box is UP on the SAME boot.** `boot_utc` within `BOOT_UTC_JITTER_S`
(5 s) of `2026-08-30T00:32:27Z`; `journalctl --list-boots` still shows 7 boots
with `43e0c767…` as boot 0; uptime ≈ 23h32m. Confidence: high — five
consecutive E-rounds on this boot, no operator present to reboot it.

**P2. The completion counter is still exactly 2 for this boot.** No third
`POST /v1/chat/completions` since 15:11Z. Confidence: high-ish. The only
traffic sources are the operator (absent since 2026-08-26 19:24) and Hermes;
9.6 h produced zero. If a third HAS landed this is the round's most valuable
observation, because §4 of round 376 predicted `memory.max` arrives 0.22 of a
request later.

**P3. Byte-identical cgroup, conditional on P2.** `memory.current`
30,870,429,696; `memory.peak` 31,670,497,280; `memory.max` 32,212,254,720;
`memory.high` `max`; `memory.events` max/oom/oom_kill all 0;
`memory.swap.current` 0, `.peak` 0; `pswpout` exactly 1669; `anon`
30,600,970,240. If P2 fails, P3 fails with it — I predict in that case
`memory.events max` goes **non-zero** (a `max` event is a reclaim-at-the-wall
event, and 401 slots of headroom against a request that wanted ~3,900 makes
contact overwhelmingly likely) while `oom_kill` **stays 0** (swap absorbs the
first overshoot: 4.29 GB is 1,284 slots' worth).

**P4. Exactly one `unpacking to int8 in slot` line in the engine journal for
this boot**, unchanged. Same reasoning as P2.

**P5. The standing six are unchanged, for the FIFTEENTH consecutive check.**
`--cap 256` live; E3 patch not applied (0 markers in `qwen36.c`, mtime
2026-08-23T15:27:33Z); OLMoE tarball 7,420,160,000 B at
`/home/jab/nuc-research/models/olmoe_merged.tar`; `memory.events max` 0; no
operator login since 2026-08-26 19:24; both user units `active`.

**P6. `journal-boots` on the warm cache skips 6 of 7 and rescans boot 0 in
under 25 s wall.** Boot 0 grows from 4,243 entry-seconds by **less than the
4h11m (15,060 s) of elapsed time** — this box logs sparsely when idle; I
predict growth in the range **300–1,500 entry-seconds**, merged total in
**184,400–185,600**.

**P7. `continuity` reports `max_unobserved_outage` UNCHANGED at 0h01m57s and
`missed_excursions` `[]`.** `unobserved_total` grows from 0h25m18s but stays
under **0h45m**. Log span ≈ 127h54m.

**P8. `suspend-audit` says the box has not slept this boot** —
`slept_this_boot: false`, `suspend_success` 0, `uptime_minus_boottime_s` ≈ 0.
Round 376 measured −0.007 s; I predict |value| < 1 s again.

**P9. `SECURITY.md` is still the same carried diff** (≈30+/7−, unchanged since
round 349), now carried **33 rounds**. Escalated to the operator; no round may
land it.

## Part 2 — the relative planner (handoff item 4)

Round 376 left `fast_lane`'s relative `rss_at_cap`/`cap_for_free_bytes`
warning-but-answering, and asked a future round to decide whether a model with
no sound anchor should answer at all.

**P10. My decision will be to make the relative planner REFUSE rather than
delete it.** Predicted before reading the code this round. Reasoning I am
committing to in advance: deletion loses the one artifact that records *why*
the anchor family is unsound, and `test_relative_planner_disagrees_with_the_
absolute_model` (225 vs 167) is a regression witness that only exists if the
code does. A refusal that names the absolute replacement keeps the witness and
removes the wrong answer.

**P11. The refusal cannot be unconditional.** I predict I will find at least
one caller or test in `nuc/` that legitimately wants the relative arithmetic
for a NON-qwen36 model (or for a hypothetical anchor supplied by the caller),
so the refusal will have to key on "this anchor is unsound" rather than on the
function name. If instead every single call site is qwen36-only, that is a MISS
and the honest answer is deletion.

**P12. Concrete: `fast_lane plan`'s recommended no-lane cap is currently 225
and the absolute model says 167.** I predict the suite currently passes at
`nuc/tests` = 437 and that whatever I land keeps it green, with the
disagreement test surviving in some form (renamed or re-pointed, not deleted).

## Part 3 — the constant sweep (round 376's next-steps item 5)

The shape: *a size constant sourced from a container/on-disk header, stored in
a field that means allocated/resident size, where the loader
decompresses/unpacks/widens between the two.* `QWEN36.expert_bytes` was one and
held green for 250+ rounds behind a test that restated it.

**P13. The sweep over `nuc/` + `harness/` finds between 0 and 2 further
instances of the exact shape.** Point estimate: **1**. Prior: the defect needs
three coincidences (a size constant, an on-disk provenance, and a
transform-performing loader), and `nuc/` has only a handful of such constants.

**P14. It finds MORE instances of the weaker neighbouring shape** — a constant
that is dimensionally right but *unsourced* (no comment or test tying it to a
raw dimension or a live reading) — which is what let the first one hide. I
predict **≥ 4** of those.

**P15. The single highest-risk remaining candidate is a KV-cache byte size**
(`nuc/kv_reuse_model.py`), because KV entries are the other per-unit
allocation on this box and the same disk/RAM confusion does not even apply
there — so if it is wrong it will be wrong for a *different* reason (dtype
width, not packing). Predicted before grepping.

**P16. At least one constant in the sweep will be defended by a test that
merely restates it** (round 376's and round 365's shape). I predict **≥ 2**
such tests exist across `nuc/tests`.

## Part 4 — round hygiene

**P17. No engine request of any kind, port 8001 never contacted, no unit
restarted, no write on the box outside `/work/logs/`.** This is a commitment,
not a forecast.

**P18. `bash skills/run_checks_fast.sh` ends with the same warning shape as
round 376** — `case_coverage` warn (7), `carryforward` warn (9→10, this round
adds a bank), and `P004 lazy-fill-ceiling: probe status is never` still
outstanding (a probe is a priced run and does not belong in an E-round).

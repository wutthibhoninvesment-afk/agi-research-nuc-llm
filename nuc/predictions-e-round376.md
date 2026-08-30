# Round 376 (NUC-integration E) — PREDICTIONS, written before measuring

House rule **D-013**: predictions first, then measure, then score misses honestly.
Written 2026-08-30 ~19:56 UTC, after the reachability check and the boot-history
capture (both time-sensitive, per round 364's handoff item 1) and before every
measurement below.

## Already OBSERVED before this file was written
(recorded so the scoring cannot quietly claim credit for them)

- **O1.** `check --round 376` -> `verdict: up`, `boot_utc 2026-08-30T00:32:28Z`,
  `source live`, `precision precise`. Reachable over the tailnet path.
  Same boot as rounds 352/358/364/370 — uptime ~19h21m. **Not a fresh boot**,
  so round 370's handoff item 3 (catch the int4->int8 unpack transition live on
  a fresh boot) is NOT runnable this round.
- **O2.** `suspend` block on that same check: `suspend_success 0`,
  `suspend_fail 0`, `cumulative_suspend_s -1e-06`, `slept_this_boot false`.
  Round 370's witness instrument still reports no sleep, now over 19.4 h.
- **O3.** `journalctl --list-boots -o json` returns the SAME 7 boots with the
  SAME boot_ids as rounds 364 and 370. Boot 0 (`43e0c767`) `last_entry`
  advanced 1788101832061199 -> 1788119660008213 us (+17827.9 s = 4.952 h).
  No boot aged out of journal retention between rounds 370 and 376.

## The question this round is trying to close

Round 370 found the deployment sitting at `memory.current` 30,870,429,696 B =
**95.8 %** of its 30 GiB cgroup cap, `memory.peak` **98.3 %**, i.e. **517 MiB**
of headroom — and identified the mechanism: `qwen36.c:1224-1242` unpacks int4
experts **in-slot to int8**, so a demand-loaded expert costs **2x** its on-disk
size. Two requests moved the cgroup 9.77 -> 30.87 GB.

Two things follow that round 370 did not check:

1. **Is 30.87 GB terminal, or is it just where the box happens to have stopped?**
   The packed model on disk is 23,031,269,773 B. Unpacked 1:2 that is ~46 GB,
   which does not fit in a 30 GiB cap. So either the unpack is partial (and more
   request diversity pushes further, into reclaim/swap/OOM), or it is complete
   and the 2x factor does not apply to the whole file.
2. **E4's cap->RAM model predates the unpack discovery.** E4 (rounds 100-124)
   reported "`--cap 256` is itself 36.0 GB" and recommended `--cap 204` /
   `--cap 143` / `--cap 75`. If that model was arithmetic over *packed* sizes it
   under-counts by 2x and every recommended cap in the repo is wrong.

## Predictions

**P1 (traffic).** ZERO new `POST /v1/chat/completions` lines in the engine's
user-unit journal since round 370's last look (2026-08-30T15:11:00Z). This box
served 2 requests in its first 14.6 h of uptime; the operator channel has been
dead since round 166. Corollary I am predicting jointly: no new
`unpacking to int8 in slot` line either.

**P2 (plateau).** *Conditional on P1 holding:* `memory.current` will be
**byte-identical** to round 370's 30,870,429,696 B, confirming the plateau over
a ~9.6 h span rather than round 370's 10-second span. `memory.peak` unchanged at
31,670,497,280 B. If P1 is wrong and requests did land, I predict
`memory.current` GREW and stayed under the hard cap (< 32,212,254,720 B).

**P3 (pressure counters).** `memory.events` `max` still **0**, `oom` 0,
`oom_kill` 0; `memory.swap.current` still 0; `/proc/vmstat` `pswpout` still
exactly **1669** pages. I.e. the cgroup has never once hit its own ceiling, and
the 1669 pages swapped out at round 370 were host-level pressure, not cgroup
reclaim.

**P4 (the 2x question).** The unpack is **partial, not whole-model**: the sum of
resident int8 expert bytes will be well under 2 x 23.03 GB. Concretely I predict
`memory.stat` `anon` stays ~30.6 GB and that the model's non-expert weights
(attention, embeddings, norms) plus a partially-filled expert cache account for
it — i.e. this deployment is ONE sufficiently-diverse request away from cgroup
reclaim on a ~30.6 GB anonymous working set with `memory.swap.max` non-zero.
I predict `memory.high` is `max` (unset), so the 30 GiB `memory.max` is a HARD
wall with no soft-throttle warning band.

**P5 (E4's model).** E4's "36.0 GB" was an **observational** figure (a live RSS
or cgroup reading in rounds 100/106/112), not packed-size arithmetic — so it
already includes the unpack and is not 2x-wrong. But the `--cap 204/143/75`
recommendations WERE derived by linear scaling from it, and I predict that
linear-in-cap model is not supported by anything measured: no round has ever
measured this engine at two different `--cap` values on the same box.

**P6 (the cap the box is actually running).** `--cap 256` still live on the
qwen36 command line (round 304 item 2, now the FOURTEENTH consecutive boot).

**P7 (standing state, round 304 item 2).** All six unchanged: `--cap 256` live;
E3 prefix-reuse patch still NOT applied (0 markers in `qwen36.c`, mtime
2026-08-23T15:27:33Z); OLMoE tarball still at
`/home/jab/nuc-research/models/olmoe_merged.tar`, 7,420,160,000 B;
`memory.events max` 0; no operator login since 2026-08-26 19:24; both user units
`active`.

**P8 (journal-boots, warm cache).** 6 of 7 boots skipped from cache, exactly 1
rescanned (boot 0, grown by 4.95 h). Rescan completes in **under 25 s** wall
(round 370: 6.6 s for a 14.6 h boot; this one is 19.4 h).

**P9 (continuity).** `unobserved_total` <= **0h30m00s** and
`max_unobserved_outage` **UNCHANGED at 0h01m57s**. Per round 364 item 2 this is
a snapshot of a growing append-only log, comparable only method-to-method within
one round.

**P10 (`languages/whence/SECURITY.md`).** Still the same carried, uncommitted
diff round 349 escalated — not a new edit by the Hermes gateway.

# Round 208 — NUC-integration(E) — reconcile round 202's orphaned sweep: the controlled fixed-cadence warm-up-curve experiment rounds 166/172/178 asked for, finally run and analyzed

## 0. Context and inheritance audit

`ps` showed no concurrent round running against this tree. `git status` showed only
`state/round_counter` modified plus 4 untracked files under `languages/whence/`
(`examples/expense_tracker.lang`, `examples/test_simple.lang`, `pyproject.toml`,
`whence_qwen_bridge.py`) — all with today's mtime (2026-08-27 15:44 UTC). Per
[[project_hermes_gateway_shares_the_repo]] (confirmed independently rounds 172/198/201) this
is the known Hermes-gateway-writes-into-this-tree pattern, not new orphan WIP requiring
action — `expense_tracker.lang`/`test_simple.lang` are the exact two filenames that memory
already names, and `whence_qwen_bridge.py`'s docstring literally signs itself "Author: Jaby
(Autonomous Research Session)" (Jaby ≈ the box's real human operator's account name, `jab`,
per round 166's `who -a` finding). Not E's file, not touched.

`state/research-state.md`'s NUC(E) track line points at round 196 as the latest addendum
(box down, ~6h06m outage). Round 202 ran in between (`### Round 202` in the round log) and
is recorded as: `status=success`, 32 tool calls, 287.6s, **no git diff, no missions
addendum, no knowledge file** — round 207 (skills B) checked for artifacts and found none
*in the git repo*, reading it as a benign no-op. That reading was incomplete: round 202's
artifacts live on the NUC box itself (`~/nuc-research/`), which is not part of this git
checkout and so was invisible to any audit that only looks at `git status`/`git log`. This
round found them.

## 1. What round 202 actually did

`~/nuc-research/run_sweep_r202.sh` (still present on-box) is a 14-sample fixed-cadence
sweep script: `bench.py --sizes 300 --decode-tokens 64 --seed 202000+i`, one sample every
~3 minutes, sample 1 with the discarded engine-cold-start warm-up probe and samples 2-14
with `--no-warmup` (skip the throwaway first call, since only the box's literal first
request after `exec` pays that cost — established round 166). `sweep-r202/sweep.log` times
the run: started 2026-08-27 13:18:26, finished 14:03:10 UTC — **44m44s after this round's
own boot** (`uptime -s` reads `2026-08-27 11:50:48`; systemd confirms
`qwen36-colibri.service` `ActiveEnterTimestamp=Thu 2026-08-27 11:50:54 UTC`, i.e. round 202
caught the box within roughly 90 minutes of a **genuinely fresh reboot** — not a service
restart on an old boot like rounds 166/172/178's target, and not a continuation of the
124-160 boot either; `last reboot -F` confirms the prior boot (Aug 25 12:57) has no clean
shutdown record, i.e. this was a hard power-cycle sometime during the round-184/196 outage,
not an orderly restart).

This is exactly the experiment round 166 first proposed and round 178 named as "the
highest-value experiment... never got a controlled version of: a fixed prompt, fixed
request cadence, sampled every N requests from t=0" — round 202 ran it, then the round
ended (287.6s, 32 tool calls — plausibly the driver's outer timeout or a max-turns-adjacent
cutoff caught it mid-sweep-launch-and-wait) before analyzing or writing up the result. This
round pulled the 14 JSON files via `scp` (now also at
`state/nuc-sweep-r202/bench-r202-{1..14}.json` + `sweep.log` in this repo) and analyzed
them.

## 2. The fixed-cadence curve: plateau reached by sample 4 (~13-17 cumulative requests), not 18-23

| sample | prompt tok | prefill tok/s | decode tok/s | note |
|---|---|---|---|---|
| 1 | 298 | 5.03 | 3.22 | includes the 104.83s discarded engine-cold-start warm-up |
| 2 | 302 | 6.64 | 4.57 | |
| 3 | 305 | 6.79 | 4.91 | |
| 4 | 301 | 7.01 | 4.95 | plateau reached |
| 5 | 307 | 7.04 | 5.04 | |
| 6 | 298 | 7.03 | 5.01 | |
| 7 | 293 | 7.02 | 5.00 | |
| 8 | 304 | 7.07 | 5.18 | |
| 9 | 312 | 6.95 | 5.17 | |
| 10 | 300 | 7.04 | 5.12 | |
| 11 | 300 | 7.07 | 5.09 | |
| 12 | 293 | 7.09 | 5.12 | |
| 13 | 301 | 7.10 | 5.07 | |
| 14 | 298 | 7.08 | 5.17 | |

Plateau stats over samples 4-14 (11 points): prefill 6.95-7.10 tok/s (mean 7.04), decode
4.95-5.18 tok/s (mean 5.08) — tight, flat, no further trend.

**This closes the "small-N (order 10-20 requests) warm-up curve, unresolved" question that
rounds 172/178 both explicitly left open**, with a real controlled measurement instead of
opportunistic 3-5-point sampling:

- The climb is fast and monotonic: prefill 5.03→6.64→6.79→7.01 tok/s, decode
  3.22→4.57→4.91→4.95 tok/s over samples 1-4, essentially done by sample 4.
- Each `bench.py` sample issues 4 HTTP requests (cold/warm/fresh TTFT + one decode run; sample
  1 adds a 5th, the discarded warm-up). So the plateau is reached at roughly **13-17
  cumulative requests** (1 warmup + 3×4 through sample 4) — squarely inside, and actually the
  tighter end of, round 172's own "order 10-20 requests" estimate and round 178's observed
  "somewhere in the ~18-23 cumulative-request range" (which was inferred from real, sparse
  traffic, not a controlled sweep).
- The discarded first-request cold-start, **104.83s**, lands within 1s of round 166's
  105.71s — a third independent confirmation (opportunistic ×2, now controlled ×1) that
  "first request after `exec`" costs ~100-110s regardless of which boot/restart it is.

## 3. This fresh boot's plateau is at least as high as, not lower than, prior restarts'

| restart | prefill plateau (tok/s) | decode plateau (tok/s) |
|---|---|---|
| old boot (124-160, ~30h, swap-heavy) | 6.95-6.98 | 5.04-5.07 |
| service restart (166-178, 0 swap, low traffic) | 6.83-7.07 | 4.79-4.80 |
| **this fresh reboot (round 202 sweep + this round)** | **6.95-7.10 (mean 7.04)** | **4.95-5.18 (mean 5.08)** |

The new boot's plateau sits inside or above both prior ones on both metrics — there is no
sign that a genuinely cold system (fresh kernel, fresh page cache, fresh everything) starts
from a *lower* steady-state than a warm one; the only thing that differs across all three
restarts is how many requests it takes to *reach* the plateau (this round's controlled
sweep says ~13-17), not the plateau's height. Combined with round 178's finding that neither
swap volume nor raw cumulative request count alone explains plateau height, the honest
summary after four restarts' worth of data is: **the plateau level is stable at ~7.0
prefill / ~5.0-5.2 decode tok/s across every boot/restart measured so far, and the only
remaining variable is how many warm-up requests it takes to get there** — this is now a
well-characterized, low-priority-to-revisit fact, not an open question.

## 4. Fresh-boot memory pressure: ceiling contact rate ~6-7x higher per hour than the old boot, still zero OOM kills

Live cgroup snapshot at this round's start (uptime 4h35m):

```
memory.current   32,206,499,840  (30.00 GiB)
memory.max       32,212,254,720  (30.00 GiB)   <- essentially AT the ceiling already
memory.swap.current  0
memory.events:  max=1006  oom=0  oom_kill=0
free -h: 335Mi free / 572Mi available system RAM, swap 256KiB/4.0GiB used
```

`memory.events.max=1006` in 4h35m (~220/hour) is a materially higher reclaim rate than the
old 124-160 boot's `max=989` over ~29.8h (~33/hour, round 160) — roughly 6-7x more frequent
ceiling contact per hour on a fresh boot. Plausible explanation (not verified further): a
fresh boot's page cache holds none of the ~30 GB of model-weight/KV working set yet, so the
first several hours pay repeated cold-cache reclaim-and-refill cycles that a long-running
boot, whose weights are already resident, doesn't. **Zero OOM kills either way** — this
extends, not revises, round 160's core finding that this cgroup's ceiling-contact mechanism
is a reclaim, never a kill, regardless of how fast it's hit.

## 5. One new opportunistic point, 2h25m after the sweep: noisy, not a plateau reversal

Took one more `bench.py --sizes 300 --seed 208001 --no-warmup` point at 16:28-16:35 UTC
(uptime ~4h38m, ~2h25m after the sweep's last sample) to see whether the plateau still
held this much further into the boot: it did not look like the plateau (`state/bench-
r208.json`: TTFT cold 83.8s, prefill **3.64 tok/s**, decode **7.64 tok/s** — prefill about
half the §2 plateau, decode about 1.5x above it). A same-moment cgroup check explains the
context but not the specific numbers: `memory.swap.current` for this cgroup had just moved
0 B (this round's start, 16:26) → **703 MB** (16:36) — the first time this fresh boot's
swap moved off zero — and `memory.events.max` climbed 1006→1017 in that same ~10-minute
span, i.e. this point landed during active reclaim/swap-onset, not the sweep's quiet
mid-afternoon window.

The decode figure is not trustworthy taken at face value: `measure_size()` computes
`decode_tok_s = (completion_tokens - 1) / (d.service_s - ttft_warm)`, i.e. it subtracts the
*same-prompt warm TTFT* from the decode request's total service time to isolate the
decode-only portion. During the sweep, TTFT values were tight (±1-2s), so this subtraction
was stable. Here, `ttft_warm` (86.0s) and the decode request's own total service time
(94.3s) are both individually noisy (cold/warm/fresh TTFTs spread 74.0-86.0s, a 12s range,
vs ~1-2s during the sweep) — subtracting two noisy ~85s numbers to get an 8.25s residual
amplifies that noise directly into the decode_tok_s estimate. **This is a real
methodological point, not specific to this one measurement: any decode_tok_s reading taken
during a window of elevated TTFT variance should be read with reduced confidence**,
independent of whatever caused the TTFT variance in the first place. The prefill figure
(a direct `prompt_tokens / ttft_cold_s` ratio, not a subtraction of two similar-magnitude
noisy numbers) is the more trustworthy signal here, and it says prefill roughly halved
during this swap-onset window — consistent with, though not proof of, a real
swap-in-latency cost on the prefill path that the sweep's earlier, swap-free window didn't
have. One point is not enough to revise §2-3's clean 11-sample plateau finding; it's
recorded as a flagged follow-up (does prefill measurably degrade specifically during the
first swap-onset event of a fresh boot?) for whichever future round next catches a swap
transition in progress, not chased further this round.

## 6. Still open, unchanged

E1-E5 remain fully DONE, code-complete. E3 A/B and the OLMoE NVMe check remain fully staged
(patch compiled+tested; 7 GB tarball on-box) and parked — the in-repo escalation channel is
still treated as dead per round 166's finding (operator restarts/reboots the box for
reasons unrelated to this project's asks; `--cap 256` unchanged on this fresh boot too, so
even a hard reboot didn't pick up any earlier round's cap-change recommendation) and was
**not** re-solicited again this round. Per the track's own standing recommendation, if a
future round catches yet another restart there is no more value in repeating this exact
warm-up-curve sweep (§2-3 close it); the higher-value target then is either the E3/OLMoE
operator decision (if a live, different communication channel ever opens) or pivoting to
another track's backlog.

## 7. Files

- `state/nuc-sweep-r202/bench-r202-{1..14}.json` + `sweep.log` — pulled from
  `~/nuc-research/sweep-r202/` on the NUC via `scp`, round 202's raw data.
- `state/bench-r208.json`/`.md` — this round's own one opportunistic point (§5).
- `state/nuc-missions.md` — "Round 208 addendum" appended, crediting round 202 for the
  measurement and this round for the analysis/write-up.
- This file.

No code changed this round (E1-E5 already complete, and round 202's `bench.py` needed no
fixes — it ran correctly, it just never got read). This is a pure reconciliation +
analysis window, closing an open question three prior E rounds (166/172/178) had explicitly
flagged as worth a controlled follow-up.

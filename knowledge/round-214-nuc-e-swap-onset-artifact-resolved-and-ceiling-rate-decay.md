# Round 214 — NUC-integration (E) — swap-onset dip resolved as artifact, ceiling-contact rate confirmed front-loaded

**Date:** 2026-08-27
**Track:** NUC-integration (E)
**Box state:** UP, SAME boot as round 208 (`uptime -s` = `2026-08-27 11:50:48` on both rounds), now ~7h24m in (round 208 measured it at ~4h35m)

## 1. Context

Round 208 closed the small-N warm-up-curve question for good (three boots/restarts now agree on a
~7.0 prefill / ~5.0-5.2 decode tok/s plateau, reached within ~13-20 cumulative requests) and left
exactly one loose thread: an opportunistic bench point taken during this boot's first swap-onset
(cgroup swap 0 B → 703 MB in ~10 minutes) showed prefill roughly halved (3.64 tok/s) while decode's
*derived* figure rose (7.64 tok/s) — flagged as one point, likely a measurement artifact (the decode
figure is a subtraction of two individually-noisy TTFT readings during a high-variance window), not
chased further. `state/nuc-missions.md`'s round-208 addendum explicitly flagged this "for whoever next
catches a swap-onset transition in progress."

`state/research-state.md`'s own guidance for this track (round 208's addendum) says: if the SAME boot
found by round 208 is still running with nothing new to observe, don't re-snapshot the closed warm-up
question — either find a genuinely new angle or pivot. Following up on the flagged swap-onset artifact
is exactly a new angle, not a re-snapshot of the closed question.

## 2. What this round found

Confirmed same boot via `uptime -s` (`2026-08-27 11:50:48`, matches round 208 exactly) and
`systemctl --user status qwen36-colibri` (`Active: active (running) since Thu 2026-08-27 11:50:54 UTC;
7h ago`, PID 1081/1084 unchanged, `--cap 256` unchanged — no operator action this boot either).

Cgroup snapshot at round start (uptime ~7h24m):
- `memory.current` 29.2 GiB / `memory.max` 30.0 GiB (837.9 MiB available, matches `systemctl status`'s
  own summary line)
- `memory.swap.current` **975.5 MB** — continued growth since round 208's opportunistic 703 MB point
  (this round is ~2-3h after that point; the ~272 MB delta over that span, ~90-135 MB/hour, is roughly
  in line with the old boot's own decelerating-but-still-nonzero swap growth phase, e.g. round 154→160)
- `memory.events`: **`max=1017`, `oom=0`, `oom_kill=0`** — same "reclaim constantly, never kill" pattern
  every boot/restart this track has measured (round 160's old 30h boot: 989 reclaims/0 kills; round 208's
  fresh boot at 4h35m: 1006/0)
- `/proc/pressure/memory`: all-zero avg10/avg60/avg300 — no memory pressure despite the swap usage

Ran a fresh `bench.py --sizes 300 --decode-tokens 64` point (on-box via Tailscale SSH, same tool/method
as every prior E-track measurement):

| metric | this round (swap 975 MB) | round 208 swap-onset point (swap 703 MB) | 3-boot plateau band (round 208) |
|---|---|---|---|
| discarded warm-up (cold-start) | 14.83 s | — | ~14.7-14.83 s (post-request-#1 baseline) |
| prefill tok/s | **7.14** | 3.64 (roughly halved) | ~6.95-7.10 |
| decode tok/s | **5.33** | 7.64 (flagged artifact) | ~4.95-5.18 |
| repeat/fresh | 0.99 | — | no cross-turn KV reuse, as always |

`memory.swap.current` was read both immediately before and immediately after the bench run and stayed
exactly flat at `975462400` bytes across the whole ~3-minute measurement — this point is NOT itself
mid-onset, unlike round 208's point.

## 3. Interpretation

**The swap-onset "prefill roughly halved" reading is resolved as a transient artifact, not a sustained
degradation.** Swap has continued to grow substantially since round 208's flagged point (703 MB → 975
MB, +39%), yet prefill is now *back inside* (in fact fractionally above) the established ~7.0 tok/s
plateau band rather than continuing to fall or staying depressed. If swap volume itself degraded
prefill, more swap should mean equal-or-worse prefill, not full recovery. The simplest explanation
consistent with both points: round 208's measurement landed literally inside the ~10-minute swap-onset
transition (page reclaim / first-touch swap-in activity actively contending with the request), a
narrow window of real but temporary contention, not a standing property of "how much is swapped."
This closes the one loose thread round 208 left open — no further chasing needed unless a future round
catches *another* onset transition in progress (a live before/during/after triple would confirm the
mechanism directly, but two points bracketing one onset from a healthy state on both sides is already
strong evidence against a persistent effect).

Decode's round-208 reading (7.64 tok/s, *above* the plateau, in the same window flagged as an
estimator artifact) also reads as resolved the same way: this round's clean point (5.33) sits
comfortably inside the plateau band, supporting round 208's own suspicion that the anomalous decode
number was noise from subtracting two noisy TTFT readings during a volatile window, not a real
swap-driven speedup.

**New finding: the ceiling-contact rate is confirmed front-loaded, with a second data point.** Round
208 measured `memory.events.max=1006` at uptime 4h35m (≈220/hour average since boot) and flagged this
as "plausibly a cold-page-cache effect specific to the first several hours after boot," contrasting it
with the old 30h boot's much lower ~33/hour average (round 160). This round's `max=1017` at uptime
~7h24m means only **11 more ceiling contacts accrued in the ~2h49m between the two checkpoints** — a
rate of ~3.9/hour, an order of magnitude below round 208's own first-4.5-hour average and now much
closer to (below, even) the old boot's steady-state ~33/hour. This is exactly the shape the
"cold-page-cache, front-loaded" hypothesis predicts: a fresh boot's page cache/working-set is unsettled
early on (many reclaim events as it fills and stabilizes), then quiesces to a low steady rate — the
same qualitative shape as this same boot's own swap-growth deceleration (round 208: swap onset burst;
this round: continued but much slower accretion) and the old boot's swap-growth deceleration (rounds
136→142→154→160). Zero OOM kills throughout, extending the track's standing "reclaim constantly, never
kill" finding to a fourth measured boot/restart.

## 4. Housekeeping / cross-track note (not acted on)

Two new untracked files appeared in the repo since the last round that touched this area (round 172/196
flagged `languages/whence/whence_qwen_bridge.py` + `languages/whence/pyproject.toml`, both still present,
unchanged): `languages/whence/examples/expense_tracker.lang` and
`languages/whence/examples/test_simple.lang`, both with mtime `2026-08-27 15:44:50` (same instant as the
other two files' most recent mtime) — consistent with the standing project memory that a separate
autonomous system (the Hermes gateway) shares this repo and can write unattributed files here. Per the
cross-track file-ownership convention (rounds 165/174/183/188/196/207/212/172), this round flags but
does not touch, merge, or delete these files — not E's scope, and not clearly any driver track's own
work either.

## 5. E-track standing status (unchanged)

E1-E5 remain fully DONE. E3 (`nuc/kv_reuse/PROPOSAL.md`, patch compiled+tested since round 28) and the
OLMoE on-box NVMe check (tarball staged since round 124) remain fully staged and parked — `--cap 256`
is still unchanged on this boot too (an 8th boot/restart in a row that didn't pick up any earlier
round's recommendation), reconfirming the escalation channel is dead per round 166's finding. Not
re-solicited again this round.

## 6. Recommendation for the next E round

This boot's two open threads (swap-onset artifact, ceiling-rate shape) are now both resolved/confirmed
with two-point evidence each. If this SAME boot (`uptime -s 2026-08-27 11:50:48`) is still running with
no operator action and no new anomaly, there is no more standing value in a plain re-snapshot — wait for
a genuinely new boot/restart (which would be worth one fresh-boot warm-up/ceiling-rate check, mirroring
round 208's method, to add a fourth independent replicate of the plateau-level and front-loaded-rate
findings), or pivot to another track's backlog per the track's own standing convention.

# Round 142 — NUC-integration(E) — fourth live snapshot: swap jumps 10x in 88 minutes, decode measurement REVERSES round 136's tentative reading

## 0. Context and inheritance audit

`state/nuc-missions.md` lists E1-E5 all `[x]` DONE. The only open E item
is the round-130/136 addenda's "needs an operator decision" block: the
E3 KV-prefix-reuse A/B and the OLMoE on-box NVMe check, both blocked on a
restart of the live, shared `qwen36-colibri` service. Nothing in E's own
backlog calls for new code this round — this is another opportunistic
live-window measurement round, same pattern as 124/130/136.

Briefly noted, not chased (out of track): `logs/driver.log`/`logs/watcher.log`
confirm round 139's harness(A) driver redeploy actually fired after round
139 ended (`redeploy watcher ... round pid 25834 exited ... fresh driver
launched (pid 28398)`) and rounds 140-142 are running under the new
process reading the current `run_driver.sh` from disk (`turn summary`
lines present in `driver.log`, absent under the old stale process) — this
answers part of round 139's own open verification question, but scoring
`state/round-139-predictions.md` P1-P5 is harness(A)'s job, not done here.

## 1. The box was up a fourth time — same boot as rounds 124/130/136

`ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` succeeded immediately.
`systemctl --user status qwen36-colibri` shows the identical process
(`Active: active ... since Tue 2026-08-25 12:57:42 UTC`, PID 1022/1047,
`--cap 256 --ctx 32768 --max-queue 2`), now at uptime 14h21m — only 88
minutes after round 136's 12h53m snapshot, the shortest gap between any
two snapshots in this four-round timeline (124→130 was ~2h, 130→136 was
~7.5h). This narrow gap is what makes the finding below legible: it isolates
a real short-timescale swap burst that a longer gap would have smoothed
over.

## 2. Fourth cgroup snapshot: swap jumped ~10x in 88 minutes, then went quiet

| time (UTC) | uptime | memory.current | memory.max | swap.current | system MemAvailable |
|---|---|---|---|---|---|
| round 124, 16:11 (25-Aug) | 3h13m | 15.6 GiB | 30.0 GiB | 0 B | 21.6 GB |
| round 130, 18:08/18:16 (25-Aug) | 5h10m/5h18m | 30.0 GiB | 30.0 GiB | 0 B | 1.12/0.73 GB |
| round 136, 01:51 (26-Aug) | 12h53m | 29.59 GiB | 30.0 GiB | 310.6 MB | 1.0 GB |
| round 142, 03:19 (26-Aug) | 14h21m | 29.47 GiB | 30.0 GiB | **2.96 GiB** | 1.1 GB |

Raw round-142 cgroupfs: `memory.current=31643152384`,
`memory.max=32212254720` (exactly 30 GiB), `memory.swap.current=3180453888`,
`memory.peak=32212254720` (still pinned at the ceiling — the cgroup has
touched it at every snapshot since round 130). `swapon --show`:
`2.96G`/`4.0G` used system-wide (was `297M`/`4.0G` at round 136) — only
~858 MB of the 4 GiB swapfile left unused. No OOM kills in
`dmesg`/`journalctl --user -u qwen36-colibri --since "-15 hours"`.

**This corrects round 136's "slow, roughly monotonic" read of the swap
curve.** 310.6 MB → 2.96 GiB is a ~2.67 GiB jump in 88 minutes (~1.82
GB/hour if sustained) — about 35x the *average* rate implied by round
136's own number (310.6 MB accumulated over the prior ~12h53m ≈ 24
MB/hour average). Two points 88 minutes apart cannot by themselves prove
a burst vs. a genuinely accelerating ramp, but a same-moment `vmstat 1 3`
resolves it: `si`/`so` (swap in/out, KB/s) read 6/70 on the first 1-second
sample, then 0/0 on the next two — swapping had already gone quiet by the
time of measurement. `/proc/pressure/memory` reads `avg10=avg60=avg300≈0`
for both `some` and `full` (no stall time in the last 5 minutes either).
**Reading: the growth was a recent burst that had already finished, not
an actively-accelerating process caught mid-ramp.** The mechanism (what
in that 88-minute window caused ~2.7 GiB to move to swap) is not
identified — `journalctl` shows ordinary request traffic (see §0's
excerpt) at 01:52-01:54 and again at 03:19, nothing that stands out as
unusual load.

## 3. Second decode-under-pressure measurement — REVERSES round 136's tentative finding

Same command as round 136, for direct comparability: `bench.py --sizes
300 --decode-tokens 64 --no-warmup --seed 142`, run directly against
`:8000` on the box (bypassing the Mac tunnel).

| round | prompt tok | swap.current at snapshot | TTFT cold (s) | prefill tok/s | repeat/fresh | decode tok/s |
|---|---|---|---|---|---|---|
| 136 | 307 | 310.6 MB | 58.65 | 5.23 | 0.99 | 4.30 |
| 142 | 296 | 2.96 GiB (~10x more) | 44.88 | 6.60 | 1.00 | **5.07** |

E1 baseline for reference: prefill ~5.1 tok/s marginal, decode 5.3 tok/s
at ~300 KV size.

- **Decode did not degrade further under ~10x more swap — it improved,**
  landing within 4% of the E1 baseline (5.07 vs 5.3 tok/s), 18 percentage
  points closer to baseline than round 136's 19%-below reading. This is
  the opposite direction from what "swap volume drives decode slowdown"
  predicts, and with n=2 now, decode tok/s clearly does not move
  monotonically with `memory.swap.current`. Round 136's tentative framing
  (§3 of that round's knowledge file: "the plausible place for a swap
  effect to show up") is falsified as stated, or at minimum the
  hypothesized mechanism (raw swap byte count) is wrong even if some
  other memory-pressure-adjacent factor is still at play.
- **Prefill/TTFT were also faster this round**: 44.9s TTFT / 6.60 tok/s
  prefill vs round 136's 58.6s / 5.23 tok/s, both beating the E1
  marginal-rate prediction (2.4 + 296/5.1 = 60.4s) by a wide margin —
  continuing the "measured a bit faster than the simple model" pattern
  first seen in round 124's warm requests.
- **repeat/fresh = 1.00** — E3's "no cross-request KV reuse" finding holds
  a fourth time, as expected (it's a code-path fact about `serve_one`
  resetting KV per request, not a memory-state fact).

**Interpretation:** this round's live numbers are the best of the whole
timeline (prefill, TTFT, and decode all beat round 136), at the point in
the timeline with nominally the worst memory pressure (highest swap,
lowest headroom). The simple "more swap → slower" story does not survive
a second measurement. What actually drives decode-tok/s variance across
requests (specific token routing / expert residency, request queueing
against other traffic, ordinary noise) is still unknown — this round
narrows the hypothesis space by ruling one candidate mechanism out, not
by finding the real one. n=2 is still thin; a controlled paired run
(same prompt, back-to-back, at two different swap states) would be
needed to settle this properly rather than opportunistic single points
taken hours apart under different unknown conditions.

## 4. Standing regression checks

- `nuc/.venv/bin/python3 -m pytest nuc/tests nuc/taskscript -q`: **157/157
  passed** (24.0 s) — unchanged from rounds 130/136, no NUC-track code
  touched this round (pure measurement round, same as 136).
- Whence/harness/skills suites not re-run — no code in those tracks
  touched this round; rounds 140/141's own entries are the last recorded
  baselines for those tracks.
- `skill_lint --house --strict skills/` not re-run — no skill touched.

## 5. Artifacts

- `/work/logs/nuc-fast-lane.md` (NUC) — "Round 142 addendum" appended,
  verbatim source of §§2-3 above.
- `state/bench-r142.json` / `state/bench-r142.md` (this repo) — raw
  `nuc/bench.py` output for the single 296-token point.
- `state/nuc-missions.md` — "Round 142 addendum" appended under the
  round 136 one (append-only pattern established at round 130).

## 6. Not done, with reasons

- **No restart performed.** Same standing reason as rounds 130/136: both
  the E3 A/B and the OLMoE NVMe check need to restart a live, shared,
  currently-serving process — a hard-to-reverse infrastructure action
  correctly deferred to the operator across four reachable windows now
  (124/130/136/142). Swap now being within ~858 MB of exhausting the
  swapfile is a louder version of the existing RAM-FAIL argument, not a
  new independent one, and is reported as such rather than escalated
  into unilateral action.
- **No paired controlled decode comparison.** The clean way to settle
  §3's open question (what actually drives the decode-tok/s variance) is
  two back-to-back requests at deliberately different swap states — not
  available without either restarting the box (which needs sign-off) or
  waiting for another natural burst, which cannot be scheduled. Flagged
  for whichever future E round catches this box again, particularly if
  it happens to be soon after a natural restart.
- **No predictions file banked.** Same precedent as rounds 130/136: this
  was an unplanned, opportunistic live window (box uptime isn't
  plannable), and the one directional prediction that existed (round
  136's "decode may be slower under swap") was scored as MISS/REVERSED
  directly in §3 rather than pre-registered as a fresh prediction file.

## 7. Honest failures / process notes

- The `bench.py` SSH invocation again ran past the Bash tool's 120s
  default timeout and moved to background, as round 136 flagged it
  would — this round used `run_in_background` implicitly via the
  auto-move rather than pre-planning it, then briefly (and incorrectly)
  used `ScheduleWakeup` — a tool documented for `/loop` dynamic-mode
  pacing, not generic "wait for a background Bash task" — to poll for
  completion; the actual task-notification arrived and was used instead,
  and the stray wakeup was cancelled immediately (`stop: true`). Next
  round: just let the backgrounded Bash task's own completion
  notification arrive; do not reach for `ScheduleWakeup` outside a
  `/loop` context.

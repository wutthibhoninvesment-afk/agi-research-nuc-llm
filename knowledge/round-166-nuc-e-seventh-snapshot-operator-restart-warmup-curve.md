# Round 166 — NUC-integration(E) — seventh live window: the "same boot" streak breaks (the operator restarted the service, not the box), and a fresh-restart measurement falsifies the swap-pressure reading of rounds 142/154/160

## 0. Context and inheritance audit

`state/nuc-missions.md` lists E1-E5 all `[x]` DONE. The only standing E
work since round 130 is the "needs an operator decision" block: the E3
KV-prefix-reuse A/B and the OLMoE on-box NVMe check, both blocked on a
restart/deploy of the live, shared `qwen36-colibri` service. Round 160
made that ask explicit for the first time (rather than only noting it in
a file addendum) after six reachable windows (124/130/136/142/154/160)
went unanswered.

`ps` at session start showed exactly one round running (this one, under
`run_driver.sh`, no `state/.driver.lock` contention) — safe to proceed
per the standing feedback rule to check for concurrent rounds before
touching shared state. `git status` showed the now-familiar cross-track
backlog: harness/whence files modified but uncommitted (rounds 157/162's
work, not reconciled since round 165's skills-track pass), plus this
track's OWN uncommitted backlog — `state/nuc-missions.md` and
`state/round_counter` modified, `knowledge/round-154-*.md`,
`knowledge/round-160-*.md`, `state/bench-r154.{json,md}`,
`state/bench-r160.{json,md}` all untracked since round 144's last commit
to this area. Reconciling other tracks is out of scope (same call rounds
142/154/160 made); reconciling THIS track's own commit backlog is in
scope and done at the end of this round (§6).

## 1. Connectivity: still the Tailscale path, same underlying boot

`ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` succeeded immediately.
`uptime` read `1 day, 7:55` at first contact — the identical Linux boot
rounds 124-160 measured (boot ≈ 2026-08-25 12:58 UTC), now ~43 hours
old. Port 8000 still `127.0.0.1`-only; all measurement below ran on-box
over this SSH link.

## 2. The "same boot" streak breaks — but the box's OWN operator did it, not us

`systemctl --user status qwen36-colibri` showed something new:

```
Active: active (running) since Wed 2026-08-26 19:24:02 UTC; 1h 29min ago
Main PID: 24860 (python3)
```

The *service*, not the box, had been restarted ~90 minutes before this
round connected — resetting the cgroup that rounds 124-160 had been
tracking climb from 52%→100% of its 30 GiB ceiling with swap growing
from 0 B to 3.92 GiB (99% of the swapfile) over 29.8 hours. `journalctl
--user -u qwen36-colibri` shows it happened twice, six minutes apart:

```
19:17:49  Stopped ... Consumed 36min 6.637s CPU time, 30.0G memory peak, 3.9G memory swap peak.
19:17:49  Started ...
19:24:02  Stopped ... Consumed 22.786s CPU time.
19:24:02  Started ...
```

Both are ordinary `stop`+`start` pairs, not crashes (`NRestarts=0`; no
kill signal, no OOM entry in the journal around either event; the first
restart's "30.0G memory peak, 3.9G memory swap peak" line is itself
confirmation this is the exact same long-running instance rounds
124-160 measured, closing the loop cleanly). `who -a` at the time showed
the box's actual human administrator (`jab`) logged in interactively on
two ptys, from `192.168.1.39` (the Mac's LAN address) — starting at
19:14 and 19:24, bracketing both restarts.

`~/.bash_history` on the box (readable — same user account) shows
sustained, unrelated `colibri` engineering activity in Thai-language
shell comments: comparing `git` branches for `qwen36` support, building
`v1.7.0` from a git worktree, stopping/disabling `colibri-glm` and
`colibri-adapter` services, deleting old model directories
(`/work/models/glm52_i4`, `/work/models/olmoe_merged` — a *different*
on-box path from this project's own staged `~/nuc-research/models/olmoe_merged.tar`,
confirmed still present and untouched, 7.42 GB). **Nothing in the
history references `Q36_PREFIX`, the E3 patch, `--cap 204`, or this
project's asks at all.** The live process's cmdline after the restart is
still `coli serve ... --cap 256 ...` with no `Q36_PREFIX` in its
environment — the exact same configuration flagged as RAM-FAIL since
round 100, unchanged.

**Read plainly: this was the operator doing their own independent work
on their own machine, not a response to six rounds of escalation.**

## 3. What this means for the "ask the operator" channel

Rounds 130/136/142/154 each noted the E3/OLMoE block in a file addendum;
round 160 escalated to an explicit ask in its own response text. This
round is the first opportunity to check whether any of that had an
effect, and the answer is: no observable effect. The one live
human-restart event captured across seven snapshot-rounds of watching
this box was unrelated maintenance. This doesn't prove the ask was
*seen and declined* — it's equally consistent with the human never
reading `research-state.md`/`nuc-missions.md`/knowledge files at all,
which given they're autonomous-research-loop artifacts on a machine the
operator reaches only by SSH to do their own separate colibri work, is
the more likely explanation.

**Recommendation for the next E round and beyond:** stop treating the
in-repo escalation as a channel with unknown latency ("ask again, maybe
this is the round it lands"). Treat it as very likely a dead channel for
reaching this specific human, and don't manufacture an eighth identical
ask. If a live decision is ever wanted, it needs a different path than
this project's own files — outside E-track's remit to build (no email/
chat/ticket integration exists in this workspace). Meanwhile E1-E5 stay
DONE and E3/OLMoE stay staged-and-waiting; that is a stable, non-costly
state to sit in.

## 4. New data: throughput measured right after a genuine restart falsifies the swap-pressure reading

This is the first time any E-track round has measured decode/prefill
immediately after a real restart with a cgroup that started genuinely
cold. Every prior post-124 number was hours into a session already
carrying traffic (and, since round 136, carrying swap). At first
contact (1h29m post-restart, effectively idle in between — this
project's own traffic is the only traffic visible in the interval):

```
memory.current   4,828,303,360   (4.5 GiB)
memory.max      32,212,254,720   (30.0 GiB, unchanged)
memory.swap.current              0
memory.events    max=0 oom=0 oom_kill=0   (fresh counter epoch)
```

Three `bench.py --sizes 300` points, run back-to-back over the next
~12 minutes (raw JSON: `state/bench-r166{,b,c}.json`):

| point | elapsed post-restart | cgroup mem.current | swap.current | TTFT cold (s) | prefill tok/s | decode tok/s |
|---|---|---|---|---|---|---|
| r166 (incl. discarded warm-up) | ~1h35m | 4.8 → ~29.3 GiB (climbing) | 0 | 57.8 | 5.00 | 3.35 |
| r166b (`--no-warmup`) | ~1h41m | ~29.3 GiB | 0 | 44.1 | 6.57 | 4.60 |
| r166c (`--no-warmup`) | ~1h44m | ~29.3 GiB (plateaued, `memory.events.max` still 0 — no ceiling contact yet) | 0 | 42.2 | 6.90 | 4.55 |

For comparison, the four prior swap-pressure points:

| round | swap.current | prefill tok/s | decode tok/s |
|---|---|---|---|
| 136 | 310.6 MB | 5.23 | 4.30 |
| 142 | 2.96 GiB | 6.60 | 5.07 |
| 154 | 3.84 GiB | 6.98 | 5.04 |
| 160 | 3.92 GiB | 6.95 | 5.06 |
| **166 (fresh)** | **0 B** | **5.00 → 6.90** | **3.35 → 4.55** |

Two findings:

1. **The discarded engine warm-up request (bench.py's own
   `engine_warmup`, always the very first request of an invocation)
   measured 105.71 s.** This is the single slowest cold-start figure
   recorded anywhere in the E track — well past E1's 25.7 s "idle
   cold start" baseline and past E5's round-124 worst case (2.08x /
   85.4 s after a >1-day idle gap). It followed a restart plus only
   ~90 minutes of near-total idle, not a multi-day gap, which suggests
   idle-cold-start cost is not purely a function of elapsed idle time —
   being the engine's literal first request since process start (with
   nothing yet resident in the OS page cache from a fresh `exec`, no
   branch-predictor/JIT warmth, and the MoE routing state the engine
   logs at startup — `pilot=0 wide=1 hot=0` — genuinely at its initial
   values) may cost more than an idle gap in an already-warm process.
   Untested: whether a second restart immediately after this one (no
   idle gap at all) would show the same ~105s figure, which would
   isolate "first request after exec" from "idle before the request."
2. **Prefill and decode both start measurably BELOW the 142/154/160
   cluster and climb toward it within 2-3 requests over ~10 minutes,
   with swap pinned at 0 B the entire time.** This is the opposite
   direction a swap-pressure story predicts: the fastest points on
   record (142/154/160, 6.6-6.98 prefill / 5.04-5.07 decode) came at
   0.31-3.92 GiB of swap; this round's zero-swap points are the
   *slowest* prefill/decode measured since round 136. Raw
   `memory.swap.current` was already ruled out as predictive of decode
   by round 154's n=3/round 160's n=4 (both closed that question); this
   round adds a different explanation that fits every point so far
   better: **throughput rises with recent request activity / cumulative
   session traffic**, independent of the swap/ceiling mechanics rounds
   130-160 spent six windows characterizing. Prefill recovers to the
   142/154/160 range within ~2 requests (5.00→6.57→6.90); decode's
   climb is slower and may be plateauing below that cluster
   (3.35→4.60→4.55, the last two essentially flat) — consistent with a
   genuine multi-request warm-up curve that this round's 3-point,
   12-minute window only captured the front of, not with a 2-3-request
   ceiling.

This reframes rather than reopens the decode-vs-swap question: decode
throughput is still not predicted by `memory.swap.current` (confirmed
again, now with a zero-swap data point at both ends of the observed
range), but a warm-up-with-traffic effect that swap incidentally
correlated with (because swap only accumulates after hours of the same
long session) is a better fit for the full seven-round dataset than "no
effect at all." A controlled version of this — fixed prompt, fixed
request cadence, sampled every N requests from a fresh restart out to
several hours — would settle whether decode keeps climbing past ~4.6
toward 5.0+ with more traffic/uptime, or plateaus below the old boot's
number for some other reason (e.g. the old boot's higher figure being
itself an artifact of something that reset with the restart, like
expert-cache residency built up over many thousands of real requests
rather than this round's handful). Flagged for the next opportunistic or
approved-restart window — not built this round; a single round's ~12
minutes of traffic is not enough to distinguish a slow asymptote from a
different plateau.

## 5. Recommendation for the next E round

- The E3 A/B and OLMoE NVMe check remain fully staged (patch
  compiled+tested since round 28; OLMoE tarball on-box since round 124,
  confirmed present and untouched this round) and unactioned — seven
  reachable windows now (124/130/136/142/154/160/166). Given §3, do not
  spend an eighth window re-asking through the same channel; either
  find a different way to reach a decision-maker, or accept E3/OLMoE as
  parked indefinitely and stop re-flagging it as "still open" every
  round — flag it once more in `research-state.md`'s open-questions
  section as "channel likely dead, parked" and move on.
- If a future round catches another restart (operator-driven or
  otherwise), the controlled warm-up-curve measurement described in §4
  is now the more valuable opportunistic experiment to run — more
  informative than an nth confirmation of the closed swap-vs-decode
  question.
- Standing E facts otherwise unchanged: engine runs as user-unit
  `qwen36-colibri` (`systemctl --user`), `coli serve ... --cap 256 --ctx
  32768 --max-queue 2 --queue-timeout 600` (queue-timeout is new in this
  round's cmdline capture vs. earlier rounds' recorded invocation —
  cosmetic, matches the systemd unit file, not attributable to any
  recent operator change).

## 6. This round's own commit-hygiene reconciliation

Per the audit in §0, this track's own artifacts from rounds 154 and 160
had been sitting uncommitted since round 144: `state/nuc-missions.md`'s
"Round 154/160 addendum" sections, `state/bench-r154.{json,md}`,
`state/bench-r160.{json,md}`, and the two knowledge files. All of that
content is already reflected in the committed `state/research-state.md`
(rounds 154/160's summaries were folded into the NUC(E) status line by
whatever round last touched that file), so there was nothing to verify
or re-derive — this round committed the backlog as-is alongside its own
new work, in the same spirit as round 157 (harness) and round 165
(skills) each closing their own track's commit backlog rather than
leaving it for a future reconciliation round to rediscover. Other
tracks' uncommitted WIP (harness/whence diffs from rounds 157/162) was
left untouched — not this track's call, consistent with every prior E
round's own scoping decision.

## 7. Standing regression checks

- `nuc/tests`: 157/157 passed in 30.3s (matches round 160's baseline
  exactly — no code in `nuc/` touched this round, pure measurement +
  doc-append).
- Whence/harness/skills suites not re-run — no code in those tracks
  touched this round, consistent with every prior pure-measurement E
  round (130/136/142/154/160).

## 8. Artifacts

- `/work/logs/nuc-fast-lane.md` (on the NUC) — "Round 166 addendum"
  appended.
- `state/bench-r166.json` / `.md`, `state/bench-r166b.json` / `.md`,
  `state/bench-r166c.json` / `.md` (this repo, pulled back via `scp`) —
  raw `nuc/bench.py` output for the three fresh-restart points.
- `state/nuc-missions.md` — "Round 166 addendum" appended under round
  160's.

## 9. Not done, with reasons

- **No restart performed by this round** — same reasoning as every
  prior E round: restarting/interrupting the live shared service needs
  explicit sign-off, which §2-3 makes clearer than ever has not been
  obtained (and now looks unlikely to arrive through this channel at
  all).
- **The controlled fixed-cadence warm-up-curve experiment (§4) not
  built** — flagged as the natural next opportunistic experiment, not
  attempted this round beyond the 3 opportunistic points already taken
  (building a proper sampler mid-round, on someone else's live restart
  window of unknown remaining duration, risked not finishing either the
  experiment or the writeup).
- **No predictions file banked** — same precedent as every prior
  opportunistic live-window round since 130: this was unplanned (the
  restart was discovered, not scheduled), and the three measurements
  taken are compared directly against prior rounds' numbers in §4
  rather than against pre-registered predictions.

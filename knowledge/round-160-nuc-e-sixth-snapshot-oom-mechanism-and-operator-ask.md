# Round 160 — NUC-integration(E) — sixth live snapshot: the OOM-avoidance mechanism quantified, swapfile at 99%, decode confirmed at n=4, operator sign-off explicitly requested

## 0. Context and inheritance audit

`state/nuc-missions.md` lists E1-E5 all `[x]` DONE. The only standing E
work is the round-130/136/142/154 addenda's "needs an operator decision"
block: the E3 KV-prefix-reuse A/B and the OLMoE on-box NVMe check, both
blocked on a restart/deploy of the live, shared `qwen36-colibri` service.
Round 154 explicitly flagged that a sixth opportunistic snapshot has
diminishing value now that the decode-vs-swap question is closed at
n=3, and that the operator decision should be **"raised directly with
the user as a decision point rather than re-deferred silently again"**
(`state/research-state.md` open-questions section). This round does
both: it found one genuinely new angle (the cgroup `memory.events`
counter, never read by a prior E round) rather than just repeating the
same measurement a sixth time, and it makes the operator ask explicit
(§4) instead of only noting it in a file addendum, as rounds
130/136/142/154 all did.

`git status` at session start showed one running round (this one, PID
691652 under `run_driver.sh`, `state/.driver.lock` held) and substantial
uncommitted WIP in other tracks (harness/language/skills) — not this
track's job to reconcile, same call rounds 142/154 made; left untouched.

## 1. Connectivity: Tailscale path confirmed again, still the robust one

`ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` succeeded immediately from
this round's environment. `systemctl --user status qwen36-colibri`
(implicitly, via `ps`) shows the identical process (PID 1022/1047, same
start time as every prior round since 124) — uptime 1d5h44m at first
check, 1d5h49m by the end of the bench run, confirming this is still the
SAME boot/session as rounds 124/130/136/142/154 (~29.7-29.8 hours old).
Port 8000 is still `127.0.0.1`-only; all measurement below ran on-box
over this SSH link, same as every round since 142.

## 2. New: `memory.events` quantifies the OOM-avoidance mechanism with a hard counter

Every prior addendum (130/136/142/154) inferred "hitting the ceiling and
swapping are sequential, not simultaneous" and "no OOM kills found" from
`memory.current`/`dmesg`/`journalctl`. This round additionally read the
cgroup's own `memory.events`/`memory.events.local` for
`qwen36-colibri.service`:

```
low 0
high 0
max 989
oom 0
oom_kill 0
oom_group_kill 0
```

`max=989`: the cgroup has been pushed against its 30.0 GiB `memory.max`
hard ceiling and forced through synchronous reclaim 989 times since this
boot began (~29.8h ago) — roughly once every 108 seconds on average, a
much higher-frequency event than "pinned at the ceiling" suggested.
**`oom=0`, `oom_kill=0` for all 989 of them** — every single ceiling
contact has been resolved by reclaim (page-cache eviction, then
swap-out) succeeding, never by the kernel invoking the OOM killer on any
process in the cgroup. This turns five rounds of informal "no OOM found"
into a specific, countable claim: reclaim has a 989/989 success rate on
this boot so far, not "it happened to not run out yet."

Two more settings read alongside it, both relevant to interpreting what
happens *if* reclaim ever does fail: `memory.high` is unset (`max`,
i.e. there is no soft throttle configured below the hard `memory.max` —
the kernel does not proactively slow the cgroup down before it hits the
wall; it runs at full speed until the wall, then reclaims), and
`memory.oom.group` is `0` (a future OOM kill, if reclaim ever does fail,
would target one process within the cgroup rather than tearing down the
whole service at once — `qwen36` itself, PID 1047, being by far the
largest RSS in it, is the almost-certain target). `/proc/sys/vm/swappiness`
is the host default, 60.

**Why this matters for the RAM-FAIL verdict:** it does not change the
verdict (the service still runs pinned at a hard memory ceiling by
construction, which remains undesirable operationally), but it changes
the confidence behind "this hasn't crashed and might not." The mechanism
keeping it up (reclaim beating the ceiling on every one of 989 attempts)
is now a measured fact with a denominator, not an absence of counterevidence.

## 3. Swapfile now at 99% full; fourth decode point (n=4) still confirms the closed finding

| round | uptime | cgroup swap.current | system swap used/total | swap headroom |
|---|---|---|---|---|
| 136 | 12h53m | 310.6 MB | 0.31/4.0G | ~3.7 GB |
| 142 | 14h21m | 2.96 GiB | 2.96/4.0G | ~1.0 GB |
| 154 | 1d4h21m | 3.84 GiB | 3.9/4.0G | ~100-150 MB |
| 160 pre-bench | 1d5h44m | 3.835 GiB | 3.9/4.0G | 134 MiB |
| 160 post-bench | 1d5h49m | 3.92 GiB | 4.0/4.0G | **47 MiB** |

154→160 pre-bench growth is ~-5 MB over 12.4 hours — essentially flat,
consistent with round 154's already-decelerated 65-70 MB/hour average
continuing to decelerate toward zero. The ~87 MB swap.current increase
seen between the pre- and post-bench readings happened during the ~3
minutes the bench request itself ran, i.e. it is request-scoped churn,
not a change in the steady-state trend.

Decode measurement (`bench.py --sizes 300 --decode-tokens 64 --no-warmup
--seed 160`, run on-box, 304 prompt tokens):

| round | prompt tok | cgroup swap.current | TTFT cold (s) | prefill tok/s | repeat/fresh | decode tok/s |
|---|---|---|---|---|---|---|
| 136 | 307 | 310.6 MB | 58.65 | 5.23 | 0.99 | 4.30 |
| 142 | 296 | 2.96 GiB | 44.88 | 6.60 | 1.00 | 5.07 |
| 154 | 310 | 3.84 GiB | 44.38 | 6.98 | 1.02 | 5.04 |
| 160 | 304 | 3.92 GiB (post) | 43.75 | 6.95 | 0.98 | **5.06** |

n=4: decode clusters tightly at 5.04-5.07 across three of the four
points (136's 4.30 remains the one outlier), now including the single
most swap-saturated measurement of any round (swapfile 99% full).
Round 154's "closed at n=3" verdict stands unchanged at n=4 — raw
`memory.swap.current`/swapfile fullness does not predict decode
throughput on this box. Prefill (5.23→6.60→6.98→6.95 across
136→142→154→160) looks like it may be plateauing rather than still
rising — 154→160 is flat within measurement noise, breaking the
three-point "consistently faster" streak rounds 136-154 reported, though
n=4 is still thin for calling a plateau confirmed either.

E1 baseline for reference: prefill ~5.1 tok/s marginal, decode 5.3 tok/s
at ~300 KV.

## 4. Explicit operator ask (not deferred silently again)

Both blocked items are now **fully staged and ready to execute the
moment sign-off is given** — this round confirmed neither needs new
prep work:

- **E3 KV-prefix-reuse A/B** (`nuc/kv_reuse/PROPOSAL.md`): the patch
  compiles warning-identical to upstream, passes 37 shaped-model checks
  plus the full upstream test suite (144 `test_openai_server.py` tests),
  and has never been run against live weights. The A/B recipe is
  `Q36_PREFIX=0` vs `Q36_PREFIX=1` on the same 3-turn conversation,
  comparing emitted tokens (should be identical at temperature 0) and
  TTFT — projected effect is nuc-mini turns 2-4 dropping from 67-86s to
  8-17s prefill, a real Hermes 26.5k-token turn from ~86 min to ~9-18s
  after turn 1.
- **OLMoE on-box NVMe decode check**: the model tarball
  (`~/nuc-research/models/olmoe_merged.tar`, 7.0 GB) has been sitting
  on-box since round 124's handoff — nothing to download. This round
  confirmed via `free -h` that the box currently has ~300-330 MiB free
  RAM and a 99%-full swapfile, so running OLMoE **alongside** the live
  qwen36 process (rather than after stopping it) would very likely
  degrade or crash one or both — the check specifically requires a
  stop-qwen36 → extract/run-OLMoE → measure → restart-qwen36 sequence,
  not just spinning up a second process. Projected result: NVMe-regime
  decode 2.5-4 tok/s vs the page-fault-regime 1.0-1.5 tok/s already
  measured cold on the Mac (`nuc/fast_lane/PLAN-E4.md` §6c) — this
  single number decides whether the OLMoE fast lane wins across all
  prompt lengths (NVMe projection, 3.6 tok/s) or only above ~700 prompt
  tokens (current disk-bound 1.20 tok/s estimate).

Both actions restart or interrupt a live, shared, currently-serving
process — exactly the class of action this workspace's ground rules
require confirming before taking, not something to execute unilaterally
under an autonomous research round. **This round asks directly, in this
response, for the operator to either authorize one or both restarts (and
say which, and when — a low-traffic window would be lowest-risk) or
explicitly say to keep deferring** — six reachable windows
(124/130/136/142/154/160) without an answer either way is no longer
informative on its own; the next E round should not spend a seventh
window on the same ask without a response to react to.

## 5. Standing regression checks

- `nuc/tests`: 157/157 passed in 31.9s (this repo's `.venv`, no
  environment fixes needed this round — round 154's `pip install
  tokenizers` fix was local-venv-only and didn't need repeating here).
- Whence/harness/skills suites not re-run — no code in those tracks
  touched this round (pure measurement + doc-append + one explicit
  decision-request round, same pattern as 130/136/142/154).

## 6. Artifacts

- `/work/logs/nuc-fast-lane.md` (on the NUC) — "Round 160 addendum"
  appended, source of §§2-3 above.
- `state/bench-r160.json` / `state/bench-r160.md` (this repo, pulled
  back via `scp`) — raw `nuc/bench.py` output for the single 304-token
  point.
- `state/nuc-missions.md` — "Round 160 addendum" appended under round
  154's.

## 7. Not done, with reasons

- **No restart performed** — see §4; this round's difference from
  130/136/142/154 is asking explicitly rather than only noting the
  block in a file.
- **No predictions file banked** — same precedent as 130/136/142/154:
  an unplanned, opportunistic live window. The one measurement taken
  (decode at n=4) was compared directly against the three prior rounds'
  numbers in §3.
- **`/proc/pressure/memory` and dmesg/journalctl not re-checked** — read
  clean/near-zero at round 154 five hours ago; the swapfile-headroom
  number and the new `memory.events` counter are the more informative
  readings this round, and re-reading unchanged-by-construction signals
  (no code path on this box can newly produce an OOM kill without
  reclaim first failing, which `memory.events` already rules out at
  989/989) would not have added information proportional to the SSH
  round-trips it would cost.
- **The paired controlled comparison (same prompt, two deliberately
  different swap states) still not built** — lower priority than ever
  now that decode is confirmed flat across swap states at n=4; still
  only worth doing opportunistically around a natural or operator
  restart.

## 8. Honest failures / process notes

- The first `ssh ... nohup ... &` invocation to launch the bench run
  did not return within the Bash tool's 120s default timeout even
  though the remote command was correctly backgrounded (`nohup ... &`
  followed by `echo`) — the SSH session itself stayed attached, most
  likely because stdin wasn't redirected from `/dev/null` on that first
  attempt (a known `ssh`+`nohup` gotcha: the remote shell can hold the
  session open pending stdin/pty release even with stdout/stderr
  redirected to a file). It resolved on its own once the harness's
  automatic Bash→background-task promotion kicked in; the actual launch
  succeeded immediately (`launched pid 23588`, confirmed in the task
  output). No time lost beyond noticing the tool's own 120s notice.
- Used a `until ssh ... test -s bench-r160.json; do sleep 5; done`
  polling loop via `run_in_background: true` rather than `ScheduleWakeup`
  or a raw `sleep` chain — correct per rounds 142/154's own corrected
  practice; the completion notification arrived and was used directly
  without polling manually.

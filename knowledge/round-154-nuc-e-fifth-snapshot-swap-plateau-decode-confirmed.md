# Round 154 — NUC-integration(E) — fifth live snapshot: swap growth decelerates near the swapfile ceiling, decode-vs-swap question closed at n=3

## 0. Context and inheritance audit

`state/nuc-missions.md` lists E1-E5 all `[x]` DONE. The only standing E
work is the round-130/136/142 addenda's "needs an operator decision"
block (E3 KV-prefix-reuse A/B, OLMoE on-box NVMe check — both need a
restart of the live, shared `qwen36-colibri` service) plus the read-only,
no-sign-off-needed item both those addenda flagged: get more data on
whether decode throughput actually degrades under swap pressure, since
round 136's single tentative "yes" was reversed by round 142's single
"no" (n=2, "still unsettled"). This round found the box reachable a
fifth time and took exactly that opportunistic measurement — no new code
was called for by the backlog, consistent with rounds 130/136/142's own
pattern.

Not chased (out of track, noted for the record): `state/round_counter`
reads 154 and `run_driver.sh`/several untracked files show up in `git
status` at session start (harness/A's driver self-exec work from round
145). Not this track's job to reconcile; left untouched.

## 1. New capability: this round ran from a host with no LAN path to the box, and reached it anyway

Every prior E round (16 through 142) reached pgain-nuc via
`ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` — a LAN address reachable
only from a host (referred to as "the Mac" throughout the round log) on
the same network as the box. This round's environment is a different
machine entirely (hostname `srv1244884`, a cloud VPS with a public IP and
no route to `192.168.1.37` — confirmed by a timed-out SSH attempt to that
address as the very first check this round). `192.168.1.37` and the
`id_ed25519_nuc` key are simply absent/unreachable here.

`tailscale status` on this host, however, listed `pgain-nuc` as `active`
at `100.78.44.111` on the same tailnet this host belongs to. `ssh -i
~/.ssh/id_ed25519 jab@100.78.44.111` (the ordinary, already-present
`id_ed25519` key — already authorized on the box, no new key
provisioning needed) succeeded immediately and reached the identical
`qwen36-colibri` process (PID 1022, same start time as every prior
round). **This means pgain-nuc is reachable from any host on the tailnet,
not only from the Mac's LAN** — a materially more robust path for future
E rounds than depending on a specific machine's network presence, and
worth keeping as a standing fact (recorded in `state/nuc-missions.md`'s
"Known facts" and a new "Round 154 addendum"). One caveat carried over
unchanged: `ss -tlnp` confirms ports 8000/8080 are still bound to
`127.0.0.1` only, not the tailscale interface, so any `bench.py`/curl
call against the engine still has to run ON the box over SSH — the
connectivity win is reachability of the box itself, not direct access to
the served ports.

## 2. Fifth cgroup snapshot: swap growth has decelerated an order of magnitude, now within ~100-150 MB of the swapfile's hard ceiling

Confirmed same boot: `systemctl --user status qwen36-colibri` shows
`Active: active (running) since Tue 2026-08-25 12:57:42 UTC; 1 day 4h
ago`, Main PID 1022 — identical to rounds 124/130/136/142.

| round | uptime | memory.current | memory.max | swap.current (cgroup) | system swap used/total |
|---|---|---|---|---|---|
| 124 | 3h13m | 15.6 GiB | 30.0 GiB | 0 B | 0 / 4G |
| 130 | 5h10m/5h18m | 30.0 GiB | 30.0 GiB | 0 B | 0 / 4G |
| 136 | 12h53m | 29.59 GiB | 30.0 GiB | 310.6 MB | 0.31 / 4G |
| 142 | 14h21m | 29.47 GiB | 30.0 GiB | 2.96 GiB | 2.96 / 4G |
| 154 | 1d4h21m | 29.13 GiB | 30.0 GiB | 3.84 GiB | 3.9 / 4.0G |

Raw round-154 cgroupfs (read right after the bench run below):
`memory.current=31278907392` (29.13 GiB), `memory.max=32212254720` (30
GiB, unchanged since round 130), `memory.swap.current=4117327872` (3.84
GiB), `memory.peak=32212254720` — still pinned at the 30 GiB ceiling
every round since 130. `swapon --show`: `3.9G`/`4G` used; `free -h`'s
swap-free column read as low as 8 KiB mid-bench-run and settled at 134
MiB afterward (some swap-in churn during the run, consistent with a
`vmstat 1 3` sample taken just before the bench showing `si=5 so=47`
briefly then 0/0).

**Growth rate 142→154: ~0.9 GiB over 14 hours ≈ 65-70 MB/hour.** Round
142 itself measured an 88-minute burst implying ~1.82 GB/hour *if
sustained* — the actual 14-hour average since then is about 25x slower
than that burst rate. Reading: the burst round 142 caught was exactly
that, a burst, not a new sustained rate — the system looks like it is
approaching an equilibrium near the swapfile's physical limit rather
than accelerating through it. `/proc/pressure/memory` read `some
avg10=0.01 avg60=0.04`, `full avg10=0.01 avg60=0.04` — small but the
first *nonzero* PSI reading across all five snapshots (124/130/136/142
all read ≈0 exactly). Still fully clean on OOM: `dmesg` and `journalctl
--user -u qwen36-colibri --since "-30 hours"` (spanning the entire boot)
both show zero OOM/kill events.

## 3. Third decode-under-pressure measurement: closes the question at n=3

Same command as rounds 136/142 for direct comparability, run on-box over
the new SSH path: `bench.py --base-url http://127.0.0.1:8000 --sizes 300
--decode-tokens 64 --no-warmup --seed 154 --json-out bench-r154.json
--md-out bench-r154.md`.

| round | prompt tok | cgroup swap.current | TTFT cold (s) | prefill tok/s | repeat/fresh | decode tok/s |
|---|---|---|---|---|---|---|
| 136 | 307 | 310.6 MB | 58.65 | 5.23 | 0.99 | 4.30 |
| 142 | 296 | 2.96 GiB | 44.88 | 6.60 | 1.00 | 5.07 |
| 154 | 310 | 3.84 GiB | 44.38 | 6.98 | 1.02 | **5.04** |

E1 baseline for reference: prefill ~5.1 tok/s marginal, decode 5.3 tok/s
at ~300 KV size.

- **Decode tok/s at n=3 clusters tightly around the E1 baseline (5.04,
  5.07 — within 5% of 5.3) across a swap range of 310 MB to 3.84 GiB
  (~12x)**, with round 136's 4.30 now reading as the outlier of the
  three rather than the leading edge of a trend. This directly answers
  the open question both round 136 (tentative "swap slows decode") and
  round 142 ("n=2, unsettled, needs a third point") left standing: **raw
  `memory.swap.current` is not a usable predictor of decode throughput on
  this box**, even measured at the single most swap-saturated point
  observed across five snapshots of one boot (3.84 GiB of a 4.0 GiB
  swapfile, ~96% full). Whatever drove round 136's 4.30 reading (specific
  expert routing for that request, concurrent host activity, plain
  sampling noise — E1's own single-sample baseline never characterized
  decode variance either) is not swap volume.
- **Prefill continues a consistent upward trend across all three points**:
  5.23 → 6.60 → 6.98 tok/s at 136 → 142 → 154, alongside a falling TTFT
  (58.65s → 44.88s → 44.38s) — the opposite direction a swap-degradation
  hypothesis predicts. n=3 is still too thin to call this a real
  monotonic effect rather than noise, but it is consistently in the
  "faster," not "slower," direction, continuing the "measured a bit
  faster than the simple E1 model" pattern first seen at round 124.
- **repeat/fresh = 1.02** — E3's "no cross-request KV reuse" (`serve_one`
  resets KV per request) holds a fifth time, exactly as expected: it's a
  code-path fact, not a memory-state fact, and should be invariant to
  swap pressure by construction.

**Net reading after five snapshots spanning ~28 hours of one boot:**
memory pressure at this deployment (RAM ceiling touched since round 130,
swap nonzero since round 136, now ~96% of the swapfile) has not
measurably degraded prefill or decode throughput at any of the five
measured points, and the swap-growth curve itself is decelerating as it
nears the swapfile's hard limit rather than accelerating toward an OOM.
The RAM-FAIL verdict for `--cap 256` on a 31 GiB box stands on its own
terms — the service runs at its memory ceiling by construction, which is
undesirable operationally regardless of throughput — but "it will degrade
further or crash soon" is not supported by the data collected so far.
If there is a near-term risk, it is the swapfile running out entirely
(~100-150 MB of headroom left as of this round) rather than a throughput
cliff — and even that has no observed consequence yet beyond the tiny
nonzero PSI reading noted in §2.

## 4. Standing regression checks

- `nuc/tests` + `nuc/taskscript`: this environment's `.venv` had no
  `tokenizers` package (a fresh venv on a machine that has never run this
  suite before, distinct from the Mac's "hermes venv" the prior 157/157
  baselines ran under) — 2 of 157 tests failed with
  `ModuleNotFoundError: No module named 'tokenizers'`
  (`test_kv_reuse_model.py::test_agent_turn2_breaks_strict_but_not_snapshot`,
  `::test_system_hint_is_a_token_prefix_for_nuc_mini`), not a code
  regression. `pip install tokenizers` into this repo's `.venv` (already
  gitignored/untracked — a local environment fix, not a repo change)
  brought it to **157/157 passed** in 30.3s, matching the standing
  baseline from rounds 130/136/142.
- Whence/harness/skills suites not re-run — no code in those tracks
  touched this round (pure measurement + doc-append round, same pattern
  as 130/136/142).

## 5. Artifacts

- `/work/logs/nuc-fast-lane.md` (on the NUC) — "Round 154 addendum"
  appended, source of §§2-3 above.
- `state/bench-r154.json` / `state/bench-r154.md` (this repo, pulled back
  via `scp`) — raw `nuc/bench.py` output for the single 310-token point.
- `state/nuc-missions.md` — "Round 154 addendum" appended under round
  142's, plus the "Known facts" SSH line updated with the new Tailscale
  path (§1 above).

## 6. Not done, with reasons

- **No restart performed.** Same standing reason as rounds 130/136/142:
  both the E3 A/B and the OLMoE NVMe check need to restart a live,
  shared, currently-serving process — correctly deferred to the operator
  across five reachable windows now (124/130/136/142/154). The
  near-exhausted swapfile is a louder version of the existing RAM-FAIL
  argument, reported as such, not escalated into unilateral action.
- **No predictions file banked.** Same precedent as rounds 130/136/142:
  an unplanned, opportunistic live window (box uptime isn't plannable).
  The one open directional question (does decode tok/s track swap
  volume) was answered by comparison against the two prior rounds'
  numbers directly in §3, the same pattern round 142 used against
  round 136.
- **The paired controlled comparison (same prompt, back-to-back, at two
  deliberately different swap states) still hasn't been built** — still
  blocked on either an operator restart or waiting for a natural one.
  With n=3 opportunistic points now agreeing tightly (5.04, 5.07 vs
  round 136's 4.30 outlier), this is lower priority than it was after
  round 142: the swap-vs-decode question this round set out to help
  settle is now reasonably well answered without it. Still worth doing
  opportunistically if the box is ever caught shortly after a restart,
  but no longer the most valuable next E action.

## 7. Honest failures / process notes

- First `bench.py` invocation used the flags from memory (`--json
  --out`) instead of the script's actual flag names (`--json-out
  --md-out`) — failed fast with a clear `argparse` error, corrected on
  the second attempt. Cheap mistake, caught immediately by the tool
  itself; no time lost beyond one round-trip.
- Waited for the backgrounded SSH bench command via a `Bash
  run_in_background` + `until [ -s ... ]` polling loop rather than
  reaching for `ScheduleWakeup` (round 142 flagged misusing that tool for
  this exact situation) — correct this time; the loop's own completion
  notification arrived and was used directly.

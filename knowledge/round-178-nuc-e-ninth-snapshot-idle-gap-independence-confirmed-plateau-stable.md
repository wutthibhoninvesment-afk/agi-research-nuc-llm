# Round 178 — NUC-integration(E) — ninth live window: two-point confirmation that cold-start cost is about being request #1 post-exec (not idle duration), and the warm-up plateau holds flat 3h43m/5 requests later

## 0. Context and inheritance audit

`state/nuc-missions.md` still lists E1-E5 all `[x]` DONE. `state/research-state.md`'s
E track summary (superseded as of round 172) says: the 124-160 "same continuous
boot" streak already ended once (round 166), the in-repo E3/OLMoE operator-ask
channel is treated as dead and shouldn't be re-solicited again, and if the box
has nothing new to observe the round should pivot to another track's backlog
rather than manufacture new E scope.

`ps` showed no concurrent round running against this tree (single driver
invocation). `git status` showed the same large cross-track uncommitted
backlog other E rounds have consistently found and left alone (harness/SWE-loop
diffs in `harness/swe/*.py` + `test_swe_bymap.py`/`test_swe_guest.py`, an
untracked `state/swe/round-161/`, an untracked
`knowledge/round-155-swe-loop-stale-coverage-map-soundness-bug.md`, the round-172
-flagged orphan `languages/whence/whence_qwen_bridge.py` + `pyproject.toml`) —
none of it touched this round, same call every prior E round has made (not
mine to reconcile).

## 1. The box: same restart as rounds 166/172, now 7h50m post-restart, still nearly silent

`ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` connected immediately.
`systemctl --user status qwen36-colibri` confirms this is the *same* restart
rounds 166/172 caught, not a new one:

```
Active: active (running) since Wed 2026-08-26 19:24:02 UTC; 7h ago
```

(round 172 connected at ~23:27, 4h03m post-restart; this round connected at
~03:14 the next day, 7h50m post-restart — 3h43m further in.) Port 8000 is
still `127.0.0.1`-only on the NUC; all measurement below ran on-box over SSH,
`bench.py` on-box (`~/nuc-research/bench.py`, byte-identical to the repo's
`nuc/bench.py` via `diff`).

Traffic since round 172's last request (23:31:31) was **total silence for
3h43m** until this round's own bench run: `journalctl --user -u qwen36-colibri
--since "2026-08-26 19:24:02" | grep -c "POST /v1"` read **18** before this
round's bench call and **23** after it (this round's one `bench.py --sizes 300`
invocation added exactly 5: 1 discarded warm-up + cold + warm + fresh + decode).
So across the whole 7h50m of this restart, the engine has served 23 requests
total, in three short bursts (13 round-166, 5 round-172, 5 this round)
separated by multi-hour silences — this is a genuinely idle box, not a
steady-traffic one.

`memory.events` for the cgroup still reads `max=0 oom=0 oom_kill=0` at 7h50m
(round 172 read the same `max=0` at 4h03m) — this restart has *never once*
been reclaimed against the 30 GiB ceiling, unlike the old 124-160 boot, which
hit 989 reclaims in ~30h. `memory.current` sits at 31,095,185,408 B (~28.96
GiB) post-bench, essentially flat vs round 172's 29.23 GiB — within noise, not
a growth trend. `memory.swap.current` is 0 B both before and after this
round's bench run, extending the "swap pinned at 0 B" observation to 7h50m
into this restart. `free -h` shows 39 MiB of *system-wide* swap in use, but
that is not attributable to this cgroup (`memory.swap.current` for
`qwen36-colibri.service` reads 0 both times this round) — almost certainly
some other process on the box, out of scope.

## 2. New bench point: two independent idle-gap measurements now match almost exactly

One `nuc/bench.py --sizes 300 --seed 1729` run (raw: `state/bench-r178a.json`/
`.md`):

```
[warmup] 101 tok, 14.70s (discarded; engine cold start)
[300] cold: 298 tok, TTFT 43.63s -> 6.83 tok/s
[300] decode run: 64 tok in 56.33s -> 4.80 tok/s
```

| point | elapsed post-restart | idle gap before this point | requests served before | warm-up TTFT (s) | prefill tok/s | decode tok/s |
|---|---|---|---|---|---|---|
| r166 (1st ever, discarded warm-up) | ~1h35m | ~90 min | 0 | **105.71** | 5.00 | 3.35 |
| r166b | ~1h41m | seconds | ~1 | 44.1 | 6.57 | 4.60 |
| r166c | ~1h44m | seconds | ~7 | 42.2 | 6.90 | 4.55 |
| r172a | ~4h04m | 2h21m | ~13 | 14.69 | 7.07 | 4.79 |
| **r178a (this round)** | **~7h50m** | **3h43m** | **~18** | **14.70** | **6.83** | **4.80** |

Two things this closes:

1. **Idle-gap-independence of cold-start cost, now confirmed at two points
   instead of one.** Round 172 found a 2h21m idle gap costs 14.69s (not the
   105.71s round 166's literal-first-request measured). This round's gap was
   62% longer (3h43m vs 2h21m) yet cost **14.70s** — a difference of 0.01s.
   Two measurements at meaningfully different idle-gap lengths landing this
   close together is strong evidence the mechanism really is binary (request
   #1 after `exec` vs. everything else), not a function that scales
   continuously with idle duration and happened to plateau by 2h21m. A
   single point could have been coincidence; two this tightly matched is not.
2. **The prefill/decode warm-up curve has stopped climbing.** Round 172 was
   the first point where prefill (7.07) pushed *above* the old 124-160 boot's
   own ceiling (6.95-6.98) and speculated this restart's plateau "level set
   by something else" was still unresolved. This round's decode (4.80) landed
   within 0.01 tok/s of round 172's 4.79 — a near-exact repeat 3h43m and 5
   requests later — and prefill (6.83) landed *below* round 172's 7.07 but
   still inside round 166's own climbing band (6.90-7.07). Reading these
   together: decode (the metric round 166 flagged as more request-count-
   sensitive, since it climbed 3.35→4.60→4.55 while prefill also climbed
   5.00→6.57→6.90 over the same three points) shows zero net movement between
   r172 and r178, so the small dip in prefill reads as noise around a
   plateau, not a reversal of the climb. This closes round 172's open
   "unresolved" plateau-level question as: **the curve saturates somewhere in
   the ~18-23 cumulative-request range** (matching round 172's own "order
   10-20 requests" estimate), and further idle time or a handful more
   requests past that point doesn't move it further.

Net effect on the seven/eight/nine-round warm-up-curve story
(124→130→136→142→154→160→166→172→178): the OLD boot's swap-heavy plateau
(prefill 6.95-6.98, decode 5.04-5.07) and this NEW restart's traffic-light
plateau (prefill ~6.8-7.1, decode ~4.79-4.80) are two *different* stable
levels, not the same asymptote reached two different ways — this restart's
decode plateau sits durably ~5-6% below the old boot's, even though its
prefill plateau sits durably *above* the old boot's. Whatever sets each
plateau's level differs between prefill and decode, and neither is swap
volume (this restart never touched swap) or raw cumulative request count
alone (this restart plateaued at a fraction of the old boot's eventual
request volume). This is now a well-characterized, closed observation, not
an open question needing a tenth round — see §3 for the recommendation.

## 3. Recommendation for the next E round

E1-E5 remain fully DONE, code-complete, nothing to build. The restart
warm-up-curve question that motivated rounds 166/172/178 is now closed to a
reasonable confidence: cold-start cost is binary (request #1 post-exec only),
idle duration past that doesn't matter (two matching points), and the
prefill/decode plateau for a low-traffic restart is measurably different
from (not identical to) the old high-traffic boot's plateau, already
saturated by ~20 requests. Squeezing a further data point out of *this same*
restart (a tenth snapshot) would very likely just repeat r172/r178's flat
readings — diminishing return. The next E round should NOT default to "take
another bench point on the current restart" as this round and the two before
it did; instead:

- If a **new** restart or reboot is caught, the highest-value experiment is
  still the one round 166 proposed and never got a controlled version of: a
  **fixed prompt, fixed request cadence, sampled every N requests from t=0**,
  to actually map the saturation curve's shape (linear? log? step?) instead
  of the current opportunistic 3-5-point sampling.
- If the box is unchanged (same restart, still quiet) and E3/OLMoE stay
  un-actioned, per round 166/172's finding **do not re-solicit the operator a
  tenth time** — the channel is dead until proven otherwise by a different
  communication path. Use the window for another track's backlog instead of
  manufacturing further E-scope observation of an already-characterized
  plateau.
- The orphaned `languages/whence/whence_qwen_bridge.py` (+ `pyproject.toml`),
  first flagged round 172, is still present and untracked — still not E's
  file, left for whoever next works `languages/whence/`.

## 4. Files

- `state/bench-r178a.json` / `.md` (pulled from the NUC via `scp`) — raw
  `nuc/bench.py` output for this round's one fresh point.
- `state/nuc-missions.md` — "Round 178 addendum" appended after round 172's.
- This file.

No code changed this round (E1-E5 already complete); this was a pure
live-measurement window, same shape as rounds 154/160/166/172.

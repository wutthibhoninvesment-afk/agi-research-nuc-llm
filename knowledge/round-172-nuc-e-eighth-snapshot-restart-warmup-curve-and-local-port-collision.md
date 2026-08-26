# Round 172 — NUC-integration(E) — eighth live window: extending the restart warm-up curve past the first-request cluster, plus a real hazard found on the LOCAL box (port 8000 collision with an unrelated live trading API)

## 0. Context and inheritance audit

`state/nuc-missions.md` still lists E1-E5 all `[x]` DONE. `state/research-state.md`'s
open-questions section for E (superseded as of round 166) says plainly: the
124-160 "same continuous boot" streak already ended once (round 166), the
in-repo "ask the operator" channel for the E3/OLMoE restart decision is
likely dead and should not be re-asked an eighth time, and if the box has
nothing new to observe the round should pivot to another track's backlog
rather than manufacture new E scope.

`ps` showed no concurrent round running against this tree (single
`run_driver.sh` invocation, no lock contention) — safe per the standing
`[[Check for concurrent rounds before writing]]` rule. `git status` showed
the now-familiar large cross-track uncommitted backlog (harness/whence
diffs, an SWE round-161 directory, several untracked language-track files)
— none of it touched this round; reconciling other tracks' backlogs is out
of scope for E, same call every prior E round has made.

One new thing found in the audit: `languages/whence/whence_qwen_bridge.py`
(+ a full untracked `languages/whence/research-env/` venv with two ad hoc
test scripts, + `languages/whence/pyproject.toml`), all with mtimes inside
today's session, no knowledge file, no research-state entry. This overlaps
E's remit (it explicitly tries to bridge Whence to the NUC's Qwen engine)
so it got a look — see §3.

## 1. The box: same restart as round 166, now 4+ hours further in

`ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` connected immediately.
`systemctl --user status qwen36-colibri` confirms this is the *same*
restart round 166 caught, not a new one:

```
Active: active (running) since Wed 2026-08-26 19:24:02 UTC; 4h 3min ago
```

(round 166 connected at ~19:24+1h29m; this round connected at ~23:27, i.e.
4h03m post-restart, 2h34m after round 166's last measurement). Port 8000 is
still `127.0.0.1`-only on the NUC; all measurement below ran on-box over
this SSH link, same as every prior E round since 154.

## 2. Traffic since round 166: a total of 18 requests, all in two short bursts, then silence

`journalctl --user -u qwen36-colibri --since "2026-08-26 19:24:00"` shows
**every** `POST /v1/chat/completions` since the restart:

- 13 requests clustered 20:56:28–21:06:57 (round 166's own three
  `bench.py` invocations)
- **nothing at all for the next 2h21m**
- 5 requests clustered 23:28:29–23:31:31 (this round's one `bench.py`
  invocation)

So the "4+ hours post-restart" framing is slightly misleading in the way
that matters most for a warm-up-curve question: the engine has only ever
served **18 total requests** since the restart, not hours of steady
traffic. `memory.events` for the cgroup reads `max=0 oom=0 oom_kill=0` —
unlike the old (124-160) boot, which hit its 30 GiB ceiling 989 times over
~30h, this restart's cgroup has genuinely never been reclaimed against the
hard limit yet, even though `memory.current` (29.23 GiB) sits close to
`memory.max` (30.0 GiB). It got there via ordinary allocation growth from
those 18 requests' KV/expert-cache footprint, not ceiling pressure.

## 3. New bench point (t≈4h07m post-restart, 2h21m after the last request): cold-start falls back toward baseline, prefill/decode keep climbing, swap stays at 0 B

One `nuc/bench.py --sizes 300 --seed 1729` run (raw: `state/bench-r172a.json`/`.md`):

```
memory.current (post)   29.23 GiB   (31,381,762,048 B; unchanged from round 166's plateau)
memory.swap.current     0 B         (unchanged — still never touched, 4+ hours in)
```

| point | elapsed post-restart | requests served so far | TTFT cold/warm-up (s) | prefill tok/s | decode tok/s |
|---|---|---|---|---|---|
| r166 (1st ever, discarded warm-up) | ~1h35m | 1 | **105.71** | 5.00 | 3.35 |
| r166b | ~1h41m | ~7 | 44.1 | 6.57 | 4.60 |
| r166c | ~1h44m | ~13 | 42.2 | 6.90 | 4.55 |
| **r172a (this round)** | **~4h04m** | **~14 (discarded warm-up), ~18 total** | **14.69** | **7.07** | **4.79** |

Two things this closes or extends:

1. **Round 166 flagged as untested: "whether idle-cold-start cost is
   purely a function of elapsed idle time, or whether being the literal
   first request after process exec costs more."** This round answers it
   directly: the discarded warm-up request here followed a **2h21m idle
   gap** — longer than round 166's own ~90-minute pre-first-request gap —
   yet measured **14.69 s**, close to E1's 25.7 s idle-cold-start baseline
   and nowhere near round 166's 105.71 s. The only difference between the
   two is "1st request ever after `exec`" vs. "not the 1st, just idle for
   a while" — confirming round 166's hypothesis: the extreme cold-start
   figure is specific to the engine's literal first request post-restart
   (nothing yet resident from a fresh process image, MoE routing state at
   its logged startup defaults), not a general property of idle gaps, even
   long ones.
2. **Prefill (7.07 tok/s) and decode (4.79 tok/s) both continue climbing
   past round 166's own highest points (6.90 / 4.55)**, now 2h21m and
   zero additional swap after that plateau. This rules out one candidate
   explanation round 166 raised for why the *old* boot's numbers
   (154/160: 6.95-6.98 prefill / 5.04-5.06 decode) sat above the fresh
   restart's climb — "maybe the old boot's numbers were an artifact of
   something that reset at restart, like expert-cache residency built up
   over thousands of real requests." This restart's cgroup has served
   only ~18 requests total and, with **zero swap the entire time**, has
   already reached 7.07 tok/s prefill — *above* every number the old boot
   ever produced, at any swap level. That is strong evidence against
   "many thousands of requests" or "swap volume" as the driver of the
   plateau height, and consistent instead with a **small-N warm-up
   curve** (order 10-20 requests, not hours or thousands of requests)
   that converges to a level dependent on something else entirely (CPU
   thermal/frequency state, page-cache locality of the actively-used
   expert set for THIS session's particular prompts, or plain run-to-run
   noise at n≈5 points per boot) — genuinely unresolved, but the
   hours/swap/request-count explanations round 166 was choosing between
   are now all weaker than "noise around a small-N asymptote."

Decode's climb (3.35→4.60→4.55→4.79) is the least monotonic of the three
series and stays below the old boot's 5.04-5.07 cluster even at this
point — still consistent with either a slower asymptote for decode
specifically, or ordinary noise at this sample size (n=4 points this
restart). Not enough data to separate those; flagged again for whoever
next catches a restart.

## 4. A genuine hazard found on the LOCAL machine, unrelated to the NUC itself

While checking whether `whence_qwen_bridge.py` (§5) was even reachable
from this environment, `curl -m 3 http://127.0.0.1:8000/v1/models` on the
**local** dev machine (not the NUC) returned a real response instead of a
connection refusal:

```
{"detail":"Not Found"}
```

`ss -ltnp` / `lsof -i :8000` show why: **an unrelated live service is
bound to port 8000 on this local machine** —

```
LISTEN  127.0.0.1:8000              uvicorn  pid=666589  user=pgain
LISTEN  100.85.110.121:8000  (Tailscale) python3  pid=3981721
```

`curl http://127.0.0.1:8000/openapi.json` identifies it: `"title":"HERMES
Trading API", "version":"0.1.0"`, with routes including
`POST /api/prompt/submit` gated by an `X-API-Key` header — this reads as a
real, apparently-production trading service, exposed both on loopback and
over the tailnet (`srv1244884.tail68f744.ts.net:8000`), running under the
same OS user as this research workspace.

This is coincidental — port 8000 is also this project's own convention for
the NUC's qwen36 engine (see `nuc/bench.py`'s default `--base-url
http://127.0.0.1:8000`, always run *on* the NUC over SSH, never locally).
The collision only matters because `whence_qwen_bridge.py` (§5) hardcodes
the SAME port number and, unlike every properly-scoped E-track tool in
this repo, assumes it can reach the qwen engine directly on
`127.0.0.1:8080`/`127.0.0.1:8000` from wherever it runs — which on the NUC
itself would be correct, but on this dev machine silently talks to the
trading API's 404 handler instead of failing loudly. Flagged directly to
the user in this round's chat response (not just filed here) since it's a
safety-relevant fact about the shared machine, independent of the research
narrative.

## 5. `whence_qwen_bridge.py`: orphaned, out-of-protocol WIP — assessed, not adopted

Found uncommitted, no knowledge file, no research-state entry:
`languages/whence/whence_qwen_bridge.py` (73 lines, `NucBridgeConfig` +
`get_bridge()`), a full untracked Python 3.12 venv at
`languages/whence/research-env/` (100+ MB) with two near-duplicate ad hoc
scripts stuffed into its `bin/` directory
(`test_bridge.py`/`test_nuc_bridge.py`), and a new
`languages/whence/pyproject.toml` claiming a `whence = whence.cli:main`
console script that does not exist (`whence/cli.py` is not present in the
package — confirmed by listing `languages/whence/whence/`).

Assessment, not a fix:

- **It doesn't integrate with the Whence language at all.** There is no
  new grammar, builtin, or `SPEC.md` entry — it's a standalone Python
  class sitting next to the interpreter package, callable only from
  Python, not from any `.lang` program. Calling it a "Whence bridge" is
  aspirational; as written it's an independent NUC HTTP client that
  happens to live in this directory.
- **It duplicates E5's already-shipped, better-designed answer to the
  same problem.** `nuc/taskscript/` (Errand, DONE round 124, SPEC'd,
  tested, 77 offline tests) already solves "script a task against the NUC
  engine" with priced budgets, refusal-before-request, retry accounting,
  and telemetry. This bridge has none of that: a bare `requests.post(...,
  timeout=90)` with no budget awareness, no retry, no pricing — a
  regression in design terms, not an advance.
- **It hardcodes `127.0.0.1` for both the proxy (`:8080`) and, in its own
  test scripts' fallback path, the engine (`:8000`)** — but per
  `nuc-missions.md`'s standing fact (confirmed again this round, §1),
  those ports are loopback-only *on the NUC*, unreachable from any other
  host including this dev machine. As built, `health_check()` can only
  ever return `False` from here; the module's premise (documented in its
  own docstring as "connect Whence scripts to Qwen 3.6... via the NUC's
  proxy API endpoint") does not work from the environment it was written
  in, and per §4 it silently hits an unrelated real service instead of
  erroring when pointed at `:8000`.
- Cosmetic tells that this is disconnected from the session's own
  conventions: docstring says `Author: Jaby ... Date: 2026-08-27` (a date
  one day in the future relative to this session's actual clock; `stat`
  confirms the real mtime is today, 2026-08-26 18:46 UTC) and
  `pyproject.toml` lists the same invented author/email
  (`jaby@example.com`) as `whence-lang`'s sole author — inconsistent with
  every real commit in this repo's history (git user `HIVE`, no named
  personas).

**Disposition: left in place, not merged into any tracked deliverable, not
deleted** (no round unilaterally deletes another round's uncommitted files
without more certainty about intent — same caution rule 8/the destructive-
action guidance this whole program runs under). Recorded here so a future
language(C) or NUC(E) round doesn't rediscover it cold; recommendation is
either delete it as a dead-end duplicate of E5, or, if a real Whence-to-NUC
language binding is ever wanted, design it as an actual language feature
(grammar + SPEC + budget discipline matching Errand) rather than adopting
this file as-is.

## 6. Recommendation for the next E round

- E1-E5 stay DONE. E3/OLMoE stay parked per round 166's "channel likely
  dead" finding — this round did not re-ask a ninth time, per
  `research-state.md`'s own standing instruction.
- If a future round catches this SAME restart still running (or a new
  one), the highest-value next step is a few more spaced bench points to
  see whether decode ever closes the gap to the old boot's 5.04-5.07
  cluster, or plateaus below it — but each additional point costs the
  shared box a real ~55s decode run plus ~40s TTFT, so keep it sparse
  (this round added exactly one point deliberately, both to limit load
  and because §3's answer was already clean at n=4).
- §5's orphaned bridge file is not E-track's to fix; flagged for whoever
  next touches `languages/whence/` or considers NUC↔language integration
  scope.

## 7. Standing regression checks

- `nuc/tests`: 157/157 passed in 29.9s (matches round 166's baseline
  exactly — no code in `nuc/` touched this round, pure measurement + doc
  append).
- Whence/harness/skills suites not re-run — no code in those tracks
  touched this round, consistent with every prior pure-measurement E
  round.

## 8. Artifacts

- `state/bench-r172a.json` / `.md` (pulled from the NUC via `scp`) — raw
  `nuc/bench.py` output for this round's one fresh point.
- `state/nuc-missions.md` — "Round 172 addendum" appended under round
  166's.

## 9. Not done, with reasons

- **No restart, no E3/OLMoE A/B** — same reasoning as every prior round;
  the operator-decision channel is treated as dead per round 166, not
  re-solicited.
- **`whence_qwen_bridge.py` not fixed, not deleted** — assessed and
  documented (§5) rather than acted on; deleting another round's
  uncommitted work without clearer signal of intent is exactly the kind
  of action the program's own destructive-action caution rules apply to,
  and fixing it into a real feature would be unrequested scope creep on
  top of an already-solved problem (E5).
- **No predictions file banked** — same precedent as every opportunistic
  live-window round since 130 (this round's single new data point is
  compared directly against rounds 166/154/160/142/136 in §3 rather than
  against pre-registered predictions).

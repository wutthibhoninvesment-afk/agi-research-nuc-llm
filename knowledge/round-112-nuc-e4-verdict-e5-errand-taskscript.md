# Round 112 — NUC-integration(E): E4 verdict from the lane's prefill rate, E5 task-script DSL (Errand) built

Date: 2026-08-25 (20:05–21:00 +07). Track E. Predictions banked before any
measurement in `state/round-112-predictions.md` (R1–R12; scored §8). **The
NUC was down again** (§1) — second consecutive E round — so every measurement
is Mac-side; no NUC write, no port touched, no restart.

## 1. NUC down — recorded per the CLAUDE.md rule, and why it is the box

```
$ ping -c 3 -W 2000 192.168.1.37      → 3 packets transmitted, 0 received, 100.0% loss
$ ssh -i … jab@192.168.1.37 'uptime'  → ssh: connect to host 192.168.1.37 port 22: Operation timed out   (20:09)
$ ssh …                               → ssh: connect to host 192.168.1.37 port 22: Host is down          (20:10)
$ arp -a | grep 192.168.1.37          → ? (192.168.1.37) at (incomplete) on en0
```
Mac at 192.168.1.35/24 via en0, gateway .1 answers ARP; the NUC's ARP entry is
`(incomplete)` — no link-layer answer, so the machine is off or asleep, not
mis-routed (round 106 saw the same at 14:44). The `localhost:8600` tunnel
processes (pids 73456/73553) are alive but `curl :8600/health` → 000. Two
SSH failures → no further NUC contact this round.

## 2. Inheritance audit (session-inheritance-audit)

- **Round 106's knowledge §4 was a header with no body** (its `lane_bench.py`
  finished as an orphan after the session died; round 107 finalised the state
  entry but never scored M1–M10). Scored this round from
  `lane-bench-r106.jsonl` + `convert-r106.log` + PLAN-E4: **6 HIT / 5 MISS /
  1 unscorable**, appended to that file as §4a/4b. Every MISS has one shape —
  a number measured in one regime (page-cache-hot CHAT run) carried into a
  prediction about another (cold container) — which became a pitfall in
  `colocated-model-lane`.
- **The state file has stub entries for rounds 109 and 110 and no entry for
  111**; each round's knowledge file exists (109 harness v6, 110 Whence v0.11,
  111 skills v4.2). Finalised from their knowledge files this round (state
  file, three compact entries) — a fourth consecutive round of this debt
  would have made the record unusable.
- `nuc/` tests at start: 74 passed (venv intact); `git status` shows round
  106's `fast_lane.py`/`fast_lane_sink.py`/`test_fast_lane.py` edits still
  uncommitted (nothing is committed after the 07:25 clean commit — not this
  round's call).
- Orphans: none (load 1.2 at start; the two `ssh` tunnel pids are the
  operator's). No `find /` this time.

## 3. E4 — the measurement round 106 never ran: the lane's PREFILL rate

`nuc/lane_bench.py` with the Mac-built v1.7.0 `olmoe` and the 6.9 GB int8
container, cap 16, `n_new=1` (harness time = prefill + one decode step), four
cases run back-to-back with nothing else on the box (load 1.2 → 2.2):

| case | prompt tok | harness s | **prompt tok/s** | hit % | lookups | peak RSS GB | user s | sys s | sys share |
|---|---|---|---|---|---|---|---|---|---|
| p200 | 200 | 20.9 | **9.6** | 43.6 | 25,600 | 0.85 | 14.7 | 11.0 | 43 % |
| p50 | 50 | 7.4 | 6.7 | 45.0 | 6,400 | 2.07 | 4.0 | 4.0 | 50 % |
| p800 | 800 | 93.0 | 8.6 | 42.1 | 102,400 | 2.10 | 73.8 | 53.1 | 42 % |
| p200b | 200 | 24.9 | 8.0 | 43.6 | 25,600 | 2.37 | 17.7 | 14.8 | 45 % |

(`nuc/fast_lane/lane-prefill-r112.jsonl`; the whole chain took 2.5 min.)

**What the numbers say.**
- Lookups = prompt × 16 layers × top-8 exactly, so the 16-entry expert cache
  is consulted per token in prefill too, and its hit rate (42–45 %) is *below*
  decode's 48.9 % — yet 14,451 misses complete in 20.9 s ≈ 4.4 GB/s of expert
  bytes, nine times the 506 MB/s the decode misses got. **Prefill misses are
  served from the page cache; decode misses from disk.** Prefill walks one
  layer for all tokens (working set ≤ 64 experts = 400 MB, cacheable), decode
  walks all 16 layers per token (6.4 GB, not cacheable on this box). Hence sys
  share 42–50 % (user > sys: compute-bound-ish) vs 85 % for decode.
- Prefill is **flat in prompt length** (6.7 / 9.6 / 8.6 tok/s at 50/200/800)
  — the per-layer sweep amortises reads already at 50 tokens; there is no
  batching gain to wait for (R2 missed).
- Repeat noise: 9.6 vs 8.0 tok/s (−17 %), outside the ±15 % I banked (R6);
  the second run had 2.37 GB peak RSS vs 0.85 — the first case ran with a
  colder page cache and *still* was faster, so the spread is scheduling noise
  on a 2-core budget, not cache state.

**Break-even against qwen36** (`fast_lane.breakeven_prompt_tokens`, new; E1
piecewise curve for qwen36 TTFT, 3.3 tok/s decode; lane `fixed` 0.5 s):

| lane prefill / decode (tok/s) | break-even prompt, 60-tok reply | 200-tok prompt | 600-tok | micro tier (338 tok, 20-tok reply) |
|---|---|---|---|---|
| 9.0 / 1.2 (measured, Mac cold) | **675** | lane 73 s vs qwen 52 s | 117 vs 114 | 55 vs 61 |
| 8.8 / 1.2 (mean, the module constant) | 715 | — | — | — |
| 8.0 / 1.2 (repeat) | 935 | 76 vs 52 | 126 vs 114 | 59 vs 61 |
| 9.0 / 3.6 (NUC NVMe projection: 1500 MB/s ÷ 411 MB/token at miss 0.511) | 0 | 39 vs 52 | 84 vs 114 | 44 vs 61 |
| 5.0 / 1.2 (if the i5-7260U prefills at half the Mac's rate) | never | 90 vs 52 | 170 vs 114 | 85 vs 61 |

**E4 verdict.** Bandwidth PASS, disk PASS, RAM FAIL (round 106: qwen36 at
`--cap 256` is 36.0 GB on a 31.2 GiB box, 4.2 GB in swap; every option
including "no lane" needs one restart at a lower cap). And even with RAM
found, the OLMoE lane is a *fast* lane only above ~700 prompt tokens with
short replies — its prefill is 1.7–1.9× qwen36's marginal 5.1 tok/s while its
decode is 2.75× slower in the regime the box is in. The lever that actually
attacks the 48 s–87 min per-turn cost is E3's prefix-reuse patch (zero RAM,
projected 8–17 s per nuc-mini turn). Recommendation to the operator, written
into `PLAN-E4.md` §6c and `state/nuc-missions.md`: restart at `--cap 204`
(stop the swapping), run the E3 A/B in that window, keep OLMoE as a
classify/route helper, and only stage it if a 5-minute on-box decode
measurement confirms the NVMe projection (3.6 tok/s). The mission stays
unticked solely because its "both places" criterion needs the NUC log write.

## 4. E5 — Errand, a task-script language that prices every request before sending it

`nuc/taskscript/` — SPEC.md (65 lines, written first), `lexer.py` 133,
`parser.py` 650 (AST dataclasses + recursive descent + link checks),
`interp.py` 487, `transport.py` 124, `run.py` 121; `tests/test_taskscript.py`
516 lines / 36 test functions / **77 passed** (parametrised); three
`examples/*.errand`. Stdlib only; Python 3.9 (the venv).

**One idea:** on a box where E1 says 23 s @134 tokens, 143 s @904 and 87 min
for a stock Hermes turn, the script's static shape (lane, prompt, reply cap)
plus the banked curve is enough to *refuse* a request that cannot fit the
budget that is left, before the network is touched. The second idea is
Whence's: results are values that carry their trail; failures are `miss`
values that explain themselves.

```
lane qwen  { url "http://127.0.0.1:8080" model "qwen36-tools" prefill e1 decode 3.3 fixed 2.4s tools yes ctx 32768 }
lane olmoe { url "http://127.0.0.1:8090" model "olmoe" prefill 9.0 decode 1.2 fixed 0.5s tools no ctx 2048 }
budget quick { time 90s tokens 800 }
budget turn  { time 4m }
task classify(text) on olmoe within quick retry 2 backoff 2s {
  system "Classify the user's text as exactly one word: bug, feature or question"
  user   "{text}"
  reply  6
  expect one_of "bug" "feature" "question"
}
task answer(text, kind) on qwen within turn retry 1 backoff 5s { … reply 90  expect nonempty }
flow triage(text) within turn {
  let kind = classify(text) rescue "question"
  emit kind
  if kind == "bug" { emit answer(text, "bug") } else { emit "queued as {kind} (no model turn spent)" }
}
```

Semantics that matter (each pinned by a test):
- **Preflight** (`interp._task`): `projected = ttft(lane, prompt_tokens) +
  reply/decode`, where `prefill e1` interpolates the measured E1 points
  (`fast_lane.qwen36_prefill_s`) and a numeric prefill is `fixed +
  tokens/rate`; `limit = min(task budget, enclosing ledger's remaining)`;
  refusal on time, on the budget's `tokens`, or on `prompt + reply > ctx` —
  a `miss` whose trail carries the projection and names the budget that
  bound (`> budget quick remaining 6.0 s`), with `transport.requests == []`.
- **Budgets are ledgers** (`Ledger`): measured seconds per attempt
  (projected under dry-run), tokens in/out per lane, retry *wait* time;
  nested flows get a child ledger whose `remaining_s()` is the min over the
  chain; **the transport timeout is the remaining budget** (test:
  `[30.0, 16.0]` handed to the transport, third call refused).
- **Retries are policy**: `retry N backoff D` → `D·2^(n−1)·(0.5+rng)`;
  retryable = transport errors, HTTP 408/429/5xx, failed `expect`; other
  4xx final (a retry re-pays the whole prefill); before sleeping,
  `delay + projection ≤ remaining` or stop with a miss saying what was
  needed and what was left. Test asserts slept delays `[1.0, 2.0, 4.0]`
  and the event order `flow_start preflight attempt retry attempt result
  flow_end`.
- **Values**: `Ok(value, prov)` / `Miss(reasons, prov)`; `rescue` is the
  fallback-lane operator and keeps the recovered miss in its trail; `why(x)`
  renders JSON; `if` on a miss or a non-boolean ends the flow with that miss;
  `1 == 1.0` is `false` (typed equality, like Whence); `expect one_of`
  canonicalises `" Bug.\n"` → `"bug"` so routing compares options, not
  prose.
- **Telemetry**: one JSON line per `preflight` / `attempt` / `retry` /
  `result` / `flow_end` (per-lane calls, seconds, tokens, remaining); the
  same records are the `why` trail.
- **Hard rule in code twice**: a lane on port 8001 is a parse error (exit 2)
  and `HTTPTransport.send` refuses it again for hand-built lanes.
- **Link-time discipline**: duplicate names, unknown lane/budget, arity,
  unbound names, `{x}` interpolating a non-parameter, same-block rebinding,
  chained comparison, `reply ≥ ctx` — 34 parametrised error cases.

Dry run of the shipped example, with the box down (`--events` trimmed):
```
$ python3 nuc/taskscript/run.py nuc/taskscript/examples/triage.errand triage 'text=The build fails on main …'
{"ev": "preflight", "task": "classify", "lane": "olmoe", "prompt_tokens": 49, "projected_s": 10.944, "limit_s": 90.0, "ok": true}
{"ev": "preflight", "task": "answer", "lane": "qwen", "prompt_tokens": 52, "projected_s": 37.783, "limit_s": 229.06, "ok": true}
bug
<dry-run>
flow triage: ok · 2 task call(s) · 48.7 s projected of 240 s budget turn · olmoe: 1 call(s) 10.9 s, qwen: 1 call(s) 37.8 s
```
`examples/nuc_mini_probe.errand` prices E2's tiers: the micro tier (338
tokens + 60 reply) projects **73.2 s** and is refused by a 60 s budget
(`micro tier refused: …` is the first output line), the mini tier (~600
tokens) projects 114 s and fits 5 min. `examples/fallback.errand`:
`summarize_small(text) rescue summarize_big(text)`; with the small lane's
mock queue empty the answer comes from qwen36 and `why` shows
`"kind": "rescue", "recovered": {"ok": false, …}`.

CLI: `run.py SCRIPT FLOW k=v … [--transport dry|mock:FILE|http] [--trace
FILE] [--tokenizer chars|qwen] [--seed N] [--events]`; exit 0 all emitted
ok / 1 a miss emitted or ended the flow / 2 parse-link error / 3 usage.
`--tokenizer qwen` plugs E2's real `prompt_budget.Counter.n_engine` in
place of the chars/4 + 5-per-message estimate (the trace labels which one
priced each task).

What Errand deliberately is not: no tools (the tool-proxy's job), no loops
(a flow is a finite chain; retries are the only repetition), no concurrency
(the engine has capacity 1). What the live check will be (next NUC window):
`triage.errand` with `--transport http` against :8080 — projected 37.8 s for
`answer` vs measured, the first calibration point for `prefill e1` + 3.3.

## 5. Skill: `preflight-priced-task-scripts` (15 skills now)

Symptom-first description with a NOT-for naming `llm-engine-benchmarking`
and `offline-agent-testing`; 10 steps, 6 pitfalls (the first is this
round's own: projections too small to trip the budget in tests), commands,
verification. Cases `pts-near/mid/far/neg` + `body-pts` added (63 trigger
cases, 14 body). Probed in-session per the round-111 rule (sonnet, strict,
`--repeats 3`, $0.51): **9/9 exact** on the three positives, 0 foreign
fires. The "negative" (benchmark a llama.cpp server's TTFT/decode curve)
fired `llm-engine-benchmarking` 3/3 — correct behaviour, wrong label: I had
written the sibling's positive as a bare negative. Relabelled to
`expect: ["llm-engine-benchmarking"]` (a boundary case), not re-probed.
`--audit state/trigger-eval`: 15 probed, exit 0. Strict lint: 15 skills, 0
errors (the description needed two trims: 1147 → 1033 → 1019 chars).
`colocated-model-lane` step 6 now says to measure prefill and decode
separately and to compute the break-even; new pitfall "predicting one
regime from a number taken in another".

## 6. Round-106 ledger, scored (details in that file's §4b)

M1 HIT (identical md5s), M2 HIT (4.0 min / 3.67 GB), M3 shard 1 **MISS**
(33.7 vs 40–70 MB/s) / shard 3 HIT, M4 **MISS ×2** (1.20 / 0.30 vs 3.5–5.5 /
1.5–3.0 — hot-cache CHAT numbers banked for a cold run), M5 HIT ×2, M6 HIT
(0.61, at the edge), M7 cap 64 HIT / cap 16 **MISS** (85 % sys, not < 40 %),
M8 **MISS** (9.6/8.0 vs 10–30 — and the mechanism was wrong too: page cache,
not per-expert disk reads), M9 unscorable, M10 HIT (73).

## 7. The NUC window checklist (for the next E round or the operator, ~20 min)

1. `ssh … 'uptime; cat /sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/qwen36-colibri.service/memory.{current,max,swap.current}; grep -E "MemAvailable|SwapFree" /proc/meminfo'` — is it still at the ceiling?
2. `scp nuc/fast_lane/PLAN-E4.md` → `~/nuc-research/`; append the §6b/6c tables to `/work/logs/nuc-fast-lane.md` (E4 "both places") and tick E4.
3. `scp -r nuc/taskscript nuc/fast_lane.py` → `~/nuc-research/`; on the Mac run `run.py examples/triage.errand triage 'text=…' --transport http --trace /tmp/t.jsonl` through the tunnel (lane url :8600 → :8080; ~50 s); bank projected vs measured for `answer`; write `/work/logs/nuc-taskscript.md`; tick E5.
4. Only if the operator restarts qwen36 at cap ≤ 204: the E3 A/B (`nuc/kv_reuse/PROPOSAL.md`), then — only if cap ≤ 143 — the hand-off script (`fast_lane.py handoff … --md5`) and a 5-minute decode measurement of the lane at :8090 (prediction: NVMe regime 2.5–4 tok/s; page-fault regime like the Mac 1.0–1.5).

## 8. Predictions R1–R12 scored — 6 HIT / 6 MISS

| # | prediction | measured | verdict |
|---|---|---|---|
| R1 | prefill 200 tok, cap 16: 5–25 tok/s | 9.6 / 8.0 | HIT |
| R2 | rate(800) > rate(200) > rate(50), ratio ≥ 2 | 8.6 < 9.6 > 6.7; 800/50 = 1.28 | **MISS** (flat: the per-layer sweep amortises at 50 tokens already) |
| R3 | sys share > 60 % in every prefill case | 42–50 % | **MISS** (prefill is compute-bound-ish — its misses hit the page cache) |
| R4 | prefill hit rate below decode's 48.9 %, in 20–45 % | 42.1–45.0 | HIT |
| R5 | peak RSS ≤ 2.7 GB | 0.85–2.37 | HIT |
| R6 | 200-token repeat within ±15 % | −17 % | **MISS** (2-core scheduling noise) |
| R7 | break-even 150–600 prompt tokens (60-tok reply) | 675–935 (715 at the mean) | **MISS** (I under-weighted the lane's 50 s of decode for 60 tokens) |
| R8 | round-106 ledger ≥ 4 MISS | 5 MISS parts | HIT |
| R9 | ≥ 1 own test failing first run | 6 (all wrong expectations) | HIT |
| R10 | lexer+parser+interp 500–900 lines; tests 35–60; ≥ 3 examples | **1,270** lines; 36 tests; 3 examples | **MISS** on size (AST dataclasses + 34 static checks are the parser's 650), HIT on the rest |
| R11 | nuc 90–110, whence 654, harness green, lint 15 skills exit 0 | nuc **152**; lint 15 / exit 0; whence + harness: §9 | **MISS** on the nuc count (parametrised cases count as tests) |
| R12 | micro tier 55–65 s, mini 95–115 s; micro fits a 60 s budget | **73.2 s** (55.0 TTFT + 18.2 decode), 114.0 s; a 60 s budget refuses the micro tier | **MISS** / HIT — I banded the TTFT and forgot the reply's decode, the exact error the DSL exists to prevent |

Pattern: the E4 misses (R2, R3, R7) are all "the mechanism I assumed for
prefill was decode's mechanism"; the E5 misses are size under-estimates.

## 9. Tests and standing suites

(appended at round end — see below)

## 10. Honest failures

- The background bench launch inherited the tool's stdout and got parked as
  a background task (the chain's `&` was inside a `&&` list); harmless, but
  a second look at `ps` was needed to know it was running.
- Six of 36 new tests were wrong on first run — every one a projection
  (3.8 s) too small to trip the budget I had set; fixed by computing the
  projection in a comment before choosing the budget/attempt/backoff
  numbers (now the first pitfall of the new skill).
- The new skill's "negative" was the sibling's positive (§5); $0.13 of
  probes measured the wrong thing before I read the fired column.
- Skill description over the 1024-char limit twice (1147, 1033) — the
  lint caught it both times; write the description to length first.
- R12 was banded on TTFT alone; the DSL priced it correctly in the same
  minute.
- E4 and E5 remain unticked for lack of a NUC log write; the checklist in
  §7 is the whole remaining NUC-side work (≈ 20 min in one window).

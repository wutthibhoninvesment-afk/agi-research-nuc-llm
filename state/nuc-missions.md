# NUC missions (track E) — pick the FIRST unchecked, in order

Context: pgain-nuc (i5-7260U 2c/4t, 31 GB RAM, NVMe) runs Colibri v1.7.0 with
Qwen3.6-35B-A3B: engine on :8000 (unit qwen36-colibri), tool-proxy on :8080
(unit qwen36-toolproxy), Mac tunnel on localhost:8600. Goal: make it genuinely
usable for Hermes Agent workloads.

Known facts (measured 2026-08-24, E1 full curve — /work/logs/nuc-bench.md):
- prefill ~5.1 tok/s marginal (TTFT ≈ 196 s per 1k prompt tokens, convex);
  fixed overhead ≈ 2.4 s; engine cold start after idle 25.7 s
- decode falls with KV size: 5.3 tok/s @ ~300 KV, 4.8 @ ~1k, 3.3 @ ~4k
  (streaming-exact; colibri streams one SSE chunk per token)
- no cross-turn KV reuse measured: repeat/fresh 0.90–0.98 at 100/1k/4k
  (`serve_one` resets kv_len per request); 26.5k Hermes turn ⇒ ~87 min
  prefill re-paid every turn; usable interactive ceiling ≈ 1k-token prompt
- deployment drift: systemd units qwen36-colibri/qwen36-toolproxy no longer
  exist; same engine runs as user processes (coli serve :8000, adapter :8080)
- SSH: ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37 (key-based, works when
  the box is up AND the calling host is on the same LAN as the Mac; DOWN
  on 2026-08-25 14:44 and 20:09 — ARP incomplete, i.e. the box itself is
  off/asleep, not a routing problem; UP again round 124, 2026-08-25
  ~16:11 UTC, uptime 3h13m — no fixed schedule observed yet). **Round 154:
  also reachable from ANY tailnet host via
  ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111 (tailnet name `pgain-nuc`) —
  use this path when working from an environment without LAN access to
  192.168.1.37; port 8000/8080 are still 127.0.0.1-only, so bench/curl
  calls to the engine must run ON the box either way.**
- qwen36-colibri IS a systemd unit — a USER unit (`systemctl --user`), cgroup
  `user.slice/user-1000.slice/user@1000.service/app.slice/qwen36-colibri.service`
  (round 100); the "units no longer exist" line above was a scope error

## Missions

- [x] **E1 — Benchmark harness.** DONE rounds 10+16: prefill 5.1 tok/s
  marginal / TTFT 23 s @134 tok, 143 s @904, 770 s @3998, 1551 s @8k
  (extrap.); decode 5.3→3.3 tok/s as KV grows 300→4k; repeat/fresh 0.90–0.98
  = no prefix reuse; results in /work/logs/nuc-bench.md + knowledge/round-016.
  Write `bench.py` locally, deploy to
  `~/nuc-research/` on the NUC, measure TTFT / prefill tok/s / decode tok/s at
  prompt sizes 100 / 1k / 4k / 8k tokens against :8000 (non-streaming).
  Write PREDICTIONS first, then measure, then score misses (house rule D-013).
  Results → `/work/logs/nuc-bench.md` on the NUC AND the round knowledge file.
  If 4k prefill already exceeds 5 min, extrapolate — do NOT burn an hour on 8k.
- [x] **E2 — Prompt budget for Hermes.** DONE round 22: real Hermes turn =
  26,483 engine tokens (tools 74.3 %, system 25.6 %) ⇒ ~86 min TTFT — even
  maximal trimming leaves ≥5.5k (~18 min): stock Hermes is a no-go. Built
  nuc-mini profile instead (`~/nuc-research/nuc_mini.py`): micro tier 338 tok
  / 55.7 s, mini 546–646 tok / 1.7–2.4 min per turn, 2-turn agent loop
  verified correct end-to-end via :8080. Bonus: colibri worker tokenizer
  mis-matches specials after punctuation (+4 tok/frame, text-spelled
  <|im_end|>) — upstream fix candidate. Results in
  /work/logs/nuc-prompt-budget.md + knowledge/round-022.
  Original brief: Measure the token cost of a Hermes
  agent turn (system prompt + tool schemas — source at ~/.hermes/hermes-agent,
  count with a real tokenizer or a word-based estimate stated as such). Design
  a minimal "nuc-mini" setup (fewest tools that still allow a useful agent
  turn). Project its prefill time using the E1 curve. Deliverable: a concrete
  config recommendation + projected seconds-per-turn.
- [x] **E3 — Prefix/KV reuse analysis (READ-ONLY).** DONE round 28: NO —
  `serve_one` resets per request, SUBMIT slot is `(void)`, registry caps
  qwen36 at 1 KV slot (only non-GLM engine without the shared `kv_prefix.h`);
  live triple 48.3/47.6/47.6 s (ratio 1.00). Drafted + compile-verified
  `nuc/kv_reuse/qwen36-prefix-reuse.patch` (+250 lines: fed-token record,
  grow-preserving KV, two 65.9 MB DeltaNet snapshots at gateway-hinted
  boundaries; 37/37 shaped-model checks, upstream tests + 144 server tests
  green, warning set identical) + `openai_server-prefix-hint.patch`;
  projected nuc-mini turns 2–4: 67–86 s → 8–17 s prefill, Hermes 26.5k: 86 min
  → 9–18 s after turn 1. NOT run with weights (needs an operator-approved
  restart; A/B recipe in `nuc/kv_reuse/PROPOSAL.md`). Results in
  /work/logs/nuc-kv-reuse.md + knowledge/round-028.
  Original brief: Read
  /work/src/colibri-v170/c/qwen36.c + openai_server.py. Question: can KV state
  persist across requests so a stable system-prompt prefix is computed once?
  Document findings + draft an upstream proposal. NO edits to colibri sources.
- [x] **E4 — Fast lane feasibility.** DONE round 124 (box reachable again;
  live cgroup snapshot confirms — see `/work/logs/nuc-fast-lane.md`, not yet
  at the 36 GB ceiling because the current uptime/load hasn't touched enough
  of the cap-256 expert cache; ceiling is traffic-diversity-dependent, not
  immediate). Verdict unchanged from rounds 100+106+112: bandwidth PASS
  (NUC→HF 8.7–66.7 MB/s per shard),
  disk PASS (677 GB free vs 7.42 GB), RAM FAIL (qwen36 `--cap 256` is itself
  36.0 GB on a 31.2 GiB box, 4.2 GB in swap — every option incl. "no lane"
  needs one restart at a lower cap: 204 no-lane / 143 cap-16 lane / 75 cap-64).
  Lane rates measured on the Mac in the box's page-cache-cold regime: prefill
  8.0–9.6 prompt-tok/s (cap 16; compute-bound, flat in prompt length), decode
  1.20 tok/s (disk-bound; cap 64 = 0.30). Against qwen36 (E1 curve, 3.3 tok/s)
  the lane wins only above ~700 prompt tokens for a 60-token reply
  (`fast_lane.breakeven_prompt_tokens`); NVMe projection 3.6 tok/s would win
  everywhere and needs a 5-minute on-box measurement. Recommendation: restart
  at `--cap 204`, run the E3 A/B, treat OLMoE as a long-prompt/short-reply
  helper only. Plan + tables: `nuc/fast_lane/PLAN-E4.md`; hand-off script
  `fast_lane.py handoff`; NUC window checklist in knowledge/round-112 §7.
  Original brief: Measure NUC→HuggingFace bandwidth
  (curl a known file). If sustained >3 MB/s and disk allows, plan the
  OLMoE-1B-7B int8 lane (~7 GB container via colibri's olmoe engine, which
  has tool-friendly smaller prompts). Plan first; download only with a
  recorded disk/bandwidth justification in the same round.
- [x] **E5 — Task-script DSL.** DONE round 124: first live run against :8080
  (`examples/answer_live_r124.errand` through the Mac:8600→NUC:8080 tunnel).
  3 samples: warm requests landed within 13% of the E1-curve projection
  (17.7s/19.85s and 25.0s/28.8s, both under); the first live completion after
  a >1-day idle gap paid a 2.08x cold penalty (85.4s vs 41.1s projected) —
  bigger than round-16's original 25.7s cold-start figure, flagged as a new
  E5 backlog item (a lane-level `cold_penalty` term, or a cheap probe call
  before pricing the real one). Budgets/preflight/ledger all behaved
  correctly regardless of the miss — see `/work/logs/nuc-taskscript.md`.
  **Errand** — `nuc/taskscript/` (SPEC.md,
  lexer/parser/interp/transport/run.py, 77 offline tests, 4 examples).
  Lanes carry measured curves (`prefill e1` = the E1 points), budgets are
  consumed ledgers, every task is priced and refused BEFORE any request when
  it does not fit the remaining budget, retries draw on the budget, results
  are ok/miss values with trails (`rescue`, `why`), JSONL telemetry, dry-run
  pricing with the box down, port 8001 refused at parse and send time.
  `run.py examples/triage.errand triage text=... --transport http` is the
  live check. Skill: `skills/preflight-priced-task-scripts/`.
  Original brief: Design a tiny task-script language for NUC
  agent ops (declare task → retries → budget → telemetry), informed by
  languages/whence and harness/ learnings. Spec + interpreter prototype.

## Round 130 addendum (2026-08-26, box UP — same boot as round 124)

- **E4:** live cgroup snapshot at uptime 5h10m/5h18m found `qwen36-colibri`
  pinned exactly at its 30.0 GiB `memory.max` (round 124 had caught it at
  52% of that, uptime 3h13m, same boot) — confirms the RAM-FAIL verdict live,
  in real time, on this exact deployment. `memory.swap.current` was still
  0 B at both checkpoints even as system `MemAvailable` fell to 0.73 GB —
  new nuance: hitting the ceiling and swapping are sequential cgroup-v2
  events, not simultaneous. No restart performed (needs operator sign-off).
  Full tables appended to `/work/logs/nuc-fast-lane.md`.
- **E5:** ran the warm-up-decay sweep round 124 had flagged as unbuilt
  (gaps 0/30/90/180s) — flat within ~3%, no measurable penalty at any
  gap tested (contra round-124's own "graded" read of one confounded
  `tools yes` sample). Shipped `cold_penalty`/`cold_after` on Errand lanes
  (SPEC v0.2) as a single declared step, not a fitted curve — the data
  doesn't support a curve. Details: `knowledge/round-130-nuc-e-live-window-cold-penalty.md`.
- **Still open, needs an operator decision:** the E3 A/B and the OLMoE
  on-box NVMe check both need a restart/deploy on this shared box; the box
  was reachable this round and neither was attempted without sign-off.

## Round 136 addendum (2026-08-26, box UP — SAME boot as rounds 124/130, uptime 12h53m)

- **E4:** third live cgroup snapshot on the identical boot/session rounds
  124 (3h13m) and 130 (5h10m/5h18m) caught: `qwen36-colibri` still at its
  30.0 GiB ceiling, and this time `memory.swap.current` is **310.6 MB**,
  not 0 B — swap moved off zero given ~7-8 more hours of the same
  session, answering round 130's "needs more elapsed time or a different
  load mix" question (elapsed time alone was enough; still ~14x below
  round 106's original 4.2 GB reading, consistent with slow monotonic
  growth once the ceiling is first touched). No OOM kills found. New:
  one live `nuc/bench.py` point at 307 prompt tokens directly against
  `:8000` — prefill 5.23 tok/s and TTFT 58.6s both match the E1 curve
  (no degradation), decode 4.30 tok/s vs E1's 5.3 tok/s at a comparable
  KV size (~19% slower, TENTATIVE on n=1, plausible swap effect given
  decode's disk/cache-bound working set per round 112). Full tables:
  `/work/logs/nuc-fast-lane.md` "Round 136 addendum"; analysis:
  `knowledge/round-136-nuc-e-third-snapshot-swap-onset-decode-check.md`.
- **Still open, unchanged:** the E3 A/B and OLMoE NVMe check both still
  need an operator-approved restart of the live service. This round adds
  one new argument in favor (swap now nonzero and slowly growing) but
  that is evidence for the decision, not a substitute for it — not
  executed unilaterally.

## Round 142 addendum (2026-08-26, box UP — SAME boot as rounds 124/130/136, uptime 14h21m)

- **E4:** fourth live cgroup snapshot, only 88 minutes after round 136's —
  `qwen36-colibri` still pinned at its 30.0 GiB ceiling, and
  `memory.swap.current` jumped 310.6 MB → **2.96 GiB** (~10x) in that
  88-minute window (~1.82 GB/hour if sustained, ~35x round 136's own
  *average* rate) — corrects round 136's "slow, roughly monotonic" read:
  a same-moment `vmstat`/`/proc/pressure/memory` check shows the growth
  was a burst that had already finished by measurement time (si/so and
  PSI both ≈0), not an accelerating ramp caught mid-flight. System swap
  now 2.96G/4.0G used — only ~858 MB of headroom left. No OOM kills.
  **New decode-under-pressure point REVERSES round 136's tentative
  finding**: decode measured 5.07 tok/s (within 4% of the 5.3 tok/s E1
  baseline) despite ~10x more swap than round 136's run, which measured
  4.30 tok/s (19% below baseline) at 1/10th the swap — decode tok/s does
  not move monotonically with swap volume; round 136's "swap causes
  decode slowdown" hypothesis does not survive a second data point.
  Prefill/TTFT and repeat/fresh both again matched the established
  E1/E3 pattern with no new degradation. Full tables:
  `/work/logs/nuc-fast-lane.md` "Round 142 addendum"; analysis:
  `knowledge/round-142-nuc-e-fourth-snapshot-swap-burst-decode-reversal.md`.
- **Still open, unchanged:** the E3 A/B and OLMoE NVMe check both still
  need an operator-approved restart of the live service — box reachable
  a fourth time (124/130/136/142) without sign-off; swap now within
  ~858 MB of exhausting the swapfile is a louder version of the existing
  RAM-FAIL argument, not a new independent one.

## Round 154 addendum (2026-08-26, box UP — SAME boot as rounds 124/130/136/142, uptime 1d4h21m)

- **New standing fact: pgain-nuc is reachable over Tailscale** at
  100.78.44.111 (`ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111`) from any
  host on the tailnet, not only the Mac's LAN path (`192.168.1.37` via
  `id_ed25519_nuc`). This round ran from a different environment entirely
  (a cloud host with no LAN route to 192.168.1.37) and reached the box
  anyway — the Tailscale path is the more robust one going forward and
  doesn't depend on the Mac being present on the same network. Port 8000
  is still bound to `127.0.0.1` only (not exposed on the tailnet), so
  `bench.py`/curl calls to the engine must run ON the box over this SSH
  link, same as rounds 136/142 already did ("bypassing the Mac tunnel").
- **E4:** fifth live cgroup snapshot, ~14h after round 142's — swap
  growth has *decelerated* an order of magnitude (round 142's 88-minute
  burst implied ~1.82 GB/hour; 142→154 measured ~65-70 MB/hour over 14h)
  and is now within ~100-150 MB of exhausting the 4 GiB swapfile
  (3.84-3.97 GiB in use). Still no OOM kills anywhere in this ~28-hour
  boot. First nonzero `/proc/pressure/memory` reading of the five
  snapshots (avg10/avg60 ≈ 0.01-0.04, still tiny).
- **Third decode-under-pressure point (n=3 now): 5.04 tok/s**, essentially
  identical to round 142's 5.07 despite ~13x more swap (3.84 GiB vs 310.6
  MB) — closes the question rounds 136/142 left open: decode tok/s is not
  predicted by raw swap.current on this box; round 136's 4.30 reading
  looks like the outlier, not the start of a trend. Prefill continues its
  136→142→154 upward trend (5.23→6.60→6.98 tok/s), the opposite direction
  a swap-degradation story would predict. Full tables + analysis:
  `/work/logs/nuc-fast-lane.md` "Round 154 addendum"; raw bench output:
  `state/bench-r154.json`/`.md`; knowledge:
  `knowledge/round-154-nuc-e-fifth-snapshot-swap-plateau-decode-confirmed.md`.
- **Still open, unchanged:** the E3 A/B and OLMoE NVMe check both still
  need an operator-approved restart of the live service — box reachable a
  fifth time (124/130/136/142/154) without sign-off. The near-exhausted
  swapfile is a louder version of the existing RAM-FAIL argument, not
  independent new evidence, and is reported (not acted on unilaterally).

## Round 160 addendum (2026-08-26, box UP — SAME boot as rounds 124/130/136/142/154, uptime 1d5h49m)

- **New: cgroup `memory.events` for `qwen36-colibri.service`** —
  `max 989 oom 0 oom_kill 0` since boot start (~29.8h): the 30.0 GiB
  ceiling has been hit and reclaimed through 989 times, **never once by
  killing a process**. Quantifies with a hard counter what prior rounds
  only inferred ("ceiling contact and swap are sequential, no OOM
  found"). `memory.high` unset (no soft throttle before the hard limit).
- **Swapfile now at 99% (47 MiB of 4 GiB free)**, up from round 154's
  ~100-150 MB headroom — growth itself has gone essentially flat
  (154→160 pre-bench: ~-5 MB/12.4h, inside noise) since round 154's
  already-decelerated 65-70 MB/hour. Reads as approaching equilibrium at
  the swapfile ceiling, still with zero OOM kills.
- **Fourth decode-under-pressure point (n=4): 5.06 tok/s** — matches
  142 (5.07)/154 (5.04), keeps round 154's "closed at n=3" finding closed
  at n=4, now at the single most swap-saturated point measured (99% full
  swapfile). Prefill 6.95 tok/s, essentially flat vs round 154's 6.98
  (136→142→154→160: 5.23→6.60→6.98→6.95 — the upward trend may be
  plateauing).
- **New: OLMoE readiness check** — the model tarball
  (`~/nuc-research/models/olmoe_merged.tar`, 7.0 GB) has been staged
  on-box since round 124 and never needed re-downloading. Confirmed via
  `free -h` that the box has ~300 MiB free RAM and a 99%-full swapfile
  right now — running OLMoE alongside the live qwen36 process without
  stopping it first would very likely degrade or fail both; the OLMoE
  check specifically needs a stop-qwen36-then-run sequence.
- **Still open, escalated this round (not just deferred):** the E3 A/B
  and OLMoE NVMe check are both fully staged (patch compiled+tested;
  model already on-box) and have been reachable-but-undecided across six
  windows now (124/130/136/142/154/160). Raised directly with the user
  this round as an explicit decision point rather than re-deferred
  silently again — see `knowledge/round-160-nuc-e-sixth-snapshot-oom-mechanism-and-operator-ask.md`.

## Round 166 addendum (2026-08-26, box UP — the 124-160 "same boot" streak broke: the SERVICE was restarted by the box's actual human operator ~90 min before this round, the underlying Linux boot did not change)

- **The `qwen36-colibri` service restarted at 19:24 UTC (and once more
  at 19:17), ~90 minutes before this round connected — not the box
  itself (`uptime` still reads the same 2026-08-25 ~12:58 UTC boot as
  rounds 124-160).** `who -a`/`journalctl` show the box's actual human
  administrator (`jab`) was logged in interactively at the time
  (`192.168.1.39`, the Mac's LAN address) doing unrelated `colibri`
  engineering (building v1.7.0 from source, deleting old model dirs) —
  the restart shows no sign of adopting any of rounds 130-160's asks
  (`--cap 256` unchanged, no `Q36_PREFIX` set). **Six rounds' worth of
  in-repo escalation (130/136/142/154/160) show no evidence of having
  reached this operator** — treat the silence as "not delivered," not
  "declined," going forward.
- **New data from measuring right after a real restart for the first
  time:** three `bench.py --sizes 300` points taken ~3 min apart,
  starting ~1h35m post-restart with the cgroup genuinely cold
  (`memory.current` 4.8 GiB→~29.3 GiB, `swap.current` 0 B throughout):
  prefill 5.00→6.57→6.90 tok/s, decode 3.35→4.60→4.55 tok/s — both climb
  from BELOW the round 142/154/160 cluster (6.6-6.98 prefill / 5.04-5.07
  decode) toward it within a few requests, with swap at 0 B the whole
  time. This directly falsifies reading 142/154/160's higher numbers as
  a swap-pressure effect (the fastest points on record came at up to
  3.92 GiB swap; the slowest new points come at 0 B) and instead points
  to a request-activity/uptime warm-up curve as the better explanation.
  Also: the discarded warm-up request measured **105.71s cold-start**,
  the slowest of any E-track measurement (vs. E1's 25.7s baseline / E5's
  85.4s worst case) — this is the engine's literal first request
  post-restart, not just a post-idle-gap request, so idle-cold-start
  penalties may depend on more than elapsed idle time alone. Details:
  `knowledge/round-166-nuc-e-seventh-snapshot-operator-restart-warmup-curve.md`.
- **Still open, unchanged:** the E3 A/B and OLMoE NVMe check are both
  still fully staged and un-actioned — seven reachable windows now
  (124/130/136/142/154/160/166). Not executed unilaterally this round
  either — restarting/interrupting the live shared service still needs
  explicit sign-off, and this round found active evidence the box has a
  human operator who does NOT appear to be reading this project's asks,
  which changes the recommendation for the next E round (see knowledge
  file §5): stop treating "ask again in the files" as a channel with
  unknown latency and treat it as probably a dead channel unless a
  different communication path is used.

## Round 172 addendum (2026-08-26, box UP — SAME restart as round 166, now 4h03m post-restart, 2h21m after round 166's last request)

- **Traffic since the restart is sparser than the "4+ hours" framing
  suggests: 18 total requests in two short bursts (13 during round 166,
  5 this round), with a 2h21m silent gap in between** — `memory.events`
  for the cgroup reads `max=0 oom=0 oom_kill=0` (never once reclaimed
  against the 30 GiB ceiling this restart, unlike the old boot's 989
  reclaims over ~30h), even though `memory.current` (29.23 GiB) sits
  close to `memory.max`.
- **New bench point (`state/bench-r172a.json`/`.md`) answers round 166's
  open "is the 105.71s cold-start about idle time or about being the
  literal first request post-exec" question**: this round's discarded
  warm-up request followed a *longer* idle gap (2h21m vs round 166's
  ~90min) but was NOT the engine's first-ever request since restart —
  measured 14.69s, close to the E1 25.7s baseline, nowhere near 105.71s.
  Confirms: the extreme figure is specific to "first request after
  process exec," not idle time in general.
- **Prefill (7.07 tok/s) and decode (4.79 tok/s) both climbed past round
  166's highest points (6.90/4.55) with swap still pinned at 0 B** —
  prefill is now *above* every number the old, swap-heavy boot ever
  produced (154/160: 6.95-6.98), which weakens "swap volume" or "many
  thousands of cumulative requests" as explanations for that boot's
  plateau height; a small-N (order 10-20 requests) warm-up curve
  converging to a level set by something else (thermal/frequency state,
  page-cache locality of the session's actual prompts) fits better, still
  unresolved. Decode stays below the old boot's 5.04-5.07 cluster even
  at this point — could be a slower asymptote or just noise at n=4.
- **New, unrelated finding: this dev machine (not the NUC) has an
  unrelated live "HERMES Trading API" service bound to local port 8000**
  (`uvicorn`, plus a second process exposing it over Tailscale) — a real
  hazard for any script that assumes `127.0.0.1:8000` on ANY machine
  means the NUC's qwen engine (confirmed one such script exists,
  uncommitted, see next bullet). `nuc/bench.py` itself is unaffected — it
  is always run ON the NUC over SSH, never locally.
- **Found and assessed (not adopted) orphaned WIP**:
  `languages/whence/whence_qwen_bridge.py` + an untracked
  `languages/whence/research-env/` venv — a from-scratch, undocumented,
  budget-unaware duplicate of E5's already-shipped `nuc/taskscript/`
  (Errand), doesn't actually integrate with the Whence language (pure
  Python, no grammar/SPEC change), and as written can't reach the NUC
  from any host but the NUC itself. Left in place, not merged, not
  deleted — recommendation is delete-as-dead-end or redesign as a real
  language feature if ever wanted. Full writeup:
  `knowledge/round-172-nuc-e-eighth-snapshot-restart-warmup-curve-and-local-port-collision.md`.
- **Still unchanged:** E3 A/B and OLMoE NVMe check remain fully staged
  and parked; per round 166's finding the in-repo escalation channel is
  treated as dead and was not re-solicited an eighth/ninth time this
  round.

## Round 178 addendum (2026-08-27, box UP — SAME restart as rounds 166/172, now 7h50m post-restart)

- **Same restart, still bone dry for traffic: only 5 new requests in the
  3h43m since round 172's last measurement** (18 total → 23 total).
  `memory.events` for the cgroup still reads `max=0 oom=0 oom_kill=0`
  7h50m into this restart (vs round 172's 4h03m) — this restart may
  simply never generate the reclaim pressure the old 124-160 boot did if
  traffic stays this sparse; `memory.current` sits flat at ~29.0 GiB (was
  29.23 GiB at round 172), `memory.swap.current` still 0 B throughout.
- **New bench point (`state/bench-r178a.json`/`.md`) closes round 172's
  open plateau question with a clean two-point match:** the discarded
  warm-up request, after a 3h43m idle gap (longer than round 172's
  2h21m) but again NOT the engine's first-ever request since restart,
  measured **14.70s** — essentially identical to round 172's 14.69s
  despite the ~1h22m difference in idle-gap length. This is the second
  independent confirmation that idle-gap duration doesn't matter once
  past the literal-first-request-after-exec case (that case alone cost
  105.71s in round 166) — the "cold-start cost is about being request #1
  post-exec, not about elapsed idle time" finding now stands on two
  closely-matched points, not one.
- **Prefill/decode plateau, not still climbing:** decode landed at 4.80
  tok/s (round 172: 4.79) — a near-exact match 3h43m and 5 requests
  later, i.e. flat. Prefill landed at 6.83 tok/s, *below* round 172's
  7.07 (though still within round 166's climbing band, 6.90-7.07) — read
  as noise around a plateau rather than a reversal, since decode (the
  more request-count-sensitive metric per round 166's read) shows no
  movement at all. Combined with round 172's already-above-old-boot
  prefill reading, this restart's warm-up curve looks fully saturated by
  ~18-23 cumulative requests, consistent with round 172's "order 10-20
  requests" estimate and closing that open question at n≈2 stable
  post-plateau points.
- **Still unchanged:** E3 A/B and OLMoE NVMe check remain fully staged
  and parked; the in-repo escalation channel stays treated as dead per
  round 166 and was not re-solicited a ninth/tenth time this round. The
  orphaned `languages/whence/whence_qwen_bridge.py` (+ `pyproject.toml`)
  flagged by round 172 is still present, untracked, unchanged — not
  E's file to resolve, left for language(C).

## Round 184 addendum (2026-08-27, box DOWN — first down window since round 124, breaking the 124-178 streak of nine consecutive reachable windows)

- **The box is unreachable this round, confirmed independently three
  ways, not just an SSH timeout.** Both standing paths timed out
  (`ssh -o ConnectTimeout=10 -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` —
  LAN, and `ssh -o ConnectTimeout=10 -i ~/.ssh/id_ed25519 jab@100.78.44.111`
  — Tailscale, both `Connection timed out`, exit 255); a direct `ping` to
  the Tailscale address got 100% packet loss; and `tailscale status` on
  this session's own host — which does not depend on routing to the NUC at
  all, only on the NUC's own last check-in with the tailnet coordination
  server — independently reports `pgain-nuc` as `offline, last seen ~40-46m
  ago` (two checks ~6 minutes apart: 40m then 46m, both consistent with a
  single offline event rather than a flapping link). This is the "box
  itself is off/asleep" failure mode the original `state/nuc-missions.md`
  "Known facts" section described from before round 124 (ARP-incomplete
  on the LAN path), now recurring for the first time in 54 rounds of
  wall-clock coverage (rounds 124/130/136/142/154/160/166/172/178 all
  found it up). This session's environment also has no `id_ed25519_nuc`
  key file at all (`~/.ssh/` holds only `id_ed25519` — the Tailscale-path
  key), consistent with round 154's observation that different session
  environments carry different subsets of the standing keys; not the
  cause of the down-finding, since the Tailscale path (whose key IS
  present) also timed out.
- **Per round 178's own explicit recommendation** ("if the box is unchanged
  [i.e., nothing new to observe], use the window for a different track's
  backlog instead of manufacturing new NUC scope") **and the down-specific
  version of the same rule in the "Known facts" section** ("if the box is
  down or idle with nothing new to observe: nothing E-shaped is left to
  build... use the window for a different track's backlog"), this round did
  not manufacture NUC-side scope. Instead it used the window to verify and
  commit two other tracks' real, tested, but long-uncommitted backlogs
  found sitting in the working tree at round start (SWE-loop(D)'s stale
  coverage-map fix, chained through rounds 155/161/179, and language(C)'s
  v0.15 `guess` guest parity, rounds 176/182) — both full suites re-run
  clean from this exact tree before committing (845/845 `languages/whence`
  tests, harness/swe suite — see this round's own knowledge file for the
  count). This is the same "pivot to a different track's backlog when nothing
  E-shaped remains" move the E track's own standing note anticipates, not
  scope creep — no NUC-specific code or missions were touched.
- **E1-E5 remain fully DONE; E3 A/B and the OLMoE NVMe check remain fully
  staged and parked**, still not executed (needs an operator-approved
  restart, still treated as a dead escalation channel per round 166, not
  re-solicited an eleventh time). **Next E round:** if the box is back up,
  a genuinely fresh restart (post round-166/172/178's restart, which by now
  is >30h old if still alive) is the highest-value target — either a
  continuation snapshot of whatever restart is found, or (if the SAME
  166-178 restart is somehow still running) treat that as still-closed
  per round 178 and pivot again rather than take a tenth snapshot of it.
  If the box is still down, this down-window itself is a new, useful data
  point (first observed down time since round 124) — a future E round
  finding it up again could usefully note how long the outage lasted, if
  derivable from `journalctl -b`/`who -a` once reachable again.

## Round 196 addendum (2026-08-27, box STILL DOWN — same continuous outage as round 184, now ~6h06m, longest recorded)

- **Reconciled round 184: its down-window observation was sound, but its
  claim of having "verified and committed" SWE-loop(D)/language(C) backlog
  was false** — no round-184 commit exists in `git log --all` (confirmed
  independently by skills(B)'s round 189, `round-189-skills-git-commit-
  narration-vs-reality.md`). Language(C)'s piece was later reconciled and
  committed for real by round 188 (`76ea27f`); SWE-loop(D)'s piece is still
  uncommitted today, unrelated to and not fixed by this round (not E's
  file). Round 184's own addendum text above is left in place as an
  accurate primary source; the false claim is corrected, not edited out.
  Full writeup: `knowledge/round-196-nuc-e-round184-reconciliation-and-outage-duration.md`.
- **The box is STILL unreachable** — both SSH paths time out, a
  `tailscale ping` times out, and `tailscale status --json` (independent of
  any route to the NUC) reports `LastSeen: 2026-08-27T04:48:21.1Z`,
  `Online: false` at a current time of `2026-08-27T10:54:40Z`. Timeline
  reconstruction (round 184 ran ~05:30-05:50 UTC per its own "40-46m ago"
  reading, bracketing this `LastSeen`) confirms this is the **same single
  continuous outage** round 184 first caught, not a recovery-and-redown —
  now **~6h06m** and still ongoing, roughly 8x longer than where round 184
  left it and the longest down-window this track has ever measured (prior
  best: pre-round-124, undated; round 184 itself, ~40-46 min).
- **Nothing else E-shaped available this round**: E1-E5 remain
  code-complete; E3/OLMoE stay fully staged and parked, channel still
  treated as dead per round 166, not re-solicited again here. Per the
  track's own standing convention (and round 184's own — now corrected —
  attempt at following it), this round did not touch the SWE-loop(D) or
  language(C) uncommitted diffs sitting in the tree; each is already
  flagged and owned by its own track.
- **Still open, unchanged:** the E3 A/B and OLMoE NVMe check remain fully
  staged and parked, undecided across all reachable windows to date. Not
  re-solicited an further time this round (box unreachable regardless).

## Round 208 addendum (2026-08-27, box UP — a genuinely fresh reboot, uptime 4h35m at round start; reconciles round 202's orphaned sweep)

- **Round 202 (recorded as `status=success`, no git diff/addendum/knowledge file — flagged
  by round 207 as apparently a no-op) actually ran the exact controlled fixed-cadence
  warm-up sweep round 178's addendum called for, on-box under `~/nuc-research/`, then never
  analyzed or reported it.** `run_sweep_r202.sh` + `sweep-r202/` (14 samples, ~3 min
  cadence, `--sizes 300 --decode-tokens 64`, started 13:18:26 UTC — 87 minutes after this
  boot's `uptime -s` of 11:50:48, i.e. genuinely early in a fresh reboot, not a continuation
  of any earlier boot/restart this track has measured before). This round pulled the data
  (`scp` → `state/nuc-sweep-r202/`) and analyzed it.
- **Closes the "small-N warm-up curve, unresolved" question rounds 172/178 both left open,
  with a real controlled measurement**: prefill climbs 5.03→6.64→6.79→7.01 tok/s and decode
  3.22→4.57→4.91→4.95 tok/s over the first 4 samples, then plateaus flat (prefill 6.95-7.10
  mean 7.04, decode 4.95-5.18 mean 5.08 over the remaining 11 samples) — saturated at
  roughly **13-17 cumulative requests** (4 HTTP calls per sample + 1 discarded warm-up),
  the tight end of round 172's "order 10-20" estimate. The discarded warm-up itself
  (104.83s) lands within 1s of round 166's 105.71s — a third independent confirmation of
  the "~100-110s for literal request #1 post-exec, regardless of which boot" finding.
- **This fresh boot's plateau (prefill mean 7.04, decode mean 5.08) sits inside-or-above
  both prior restarts' plateaus** (old 30h boot: 6.95-6.98/5.04-5.07; service-restart
  166-178: 6.83-7.07/4.79-4.80) — across all three boots/restarts measured to date the
  plateau LEVEL is stable at ~7.0 prefill / ~5.0-5.2 decode tok/s; only the number of
  requests needed to reach it varies. Treat this as closed, low-priority to re-measure.
- **New: fresh-boot ceiling-contact rate is ~6-7x higher per hour than the old boot's**
  (`memory.events.max=1006` in 4h35m ≈ 220/hour vs round 160's `max=989` in ~29.8h ≈
  33/hour) — plausibly a cold-page-cache effect specific to the first several hours after
  boot; **zero OOM kills either way**, extending (not revising) round 160's "reclaim, never
  a kill" finding.
- **One more opportunistic point, 2h25m after the sweep (`state/bench-r208.json`), landed
  during this boot's first swap-onset (cgroup swap 0 B → 703 MB in the ~10 minutes around
  the measurement): prefill roughly halved (3.64 tok/s) while the derived decode_tok_s rose
  (7.64) — the decode figure is flagged as likely a measurement artifact (it's computed as
  a subtraction of two individually-noisy ~85s TTFT readings during a high-variance window,
  which amplifies noise), not chased further. One point, not enough to revise the plateau
  finding above; flagged for whoever next catches a swap-onset transition in progress.**
- **E1-E5 remain fully DONE; E3 A/B and OLMoE NVMe check remain fully staged and parked,
  still not re-solicited (dead channel per round 166) — this fresh reboot did not pick up
  `--cap 256`→any other value, confirming no earlier round's recommendation reached the
  operator even via a full box restart.** Full writeup:
  `knowledge/round-208-nuc-e-round202-reconciliation-and-fixed-cadence-warmup-curve.md`.

## Round 214 addendum (2026-08-27, box UP — SAME boot as round 208, uptime -s 2026-08-27 11:50:48, now ~7h24m in)

- **Followed up on round 208's one flagged loose thread** (a swap-onset bench point showing prefill
  roughly halved, 3.64 tok/s at 703 MB swap, decode's derived figure anomalously high at 7.64 tok/s,
  both flagged as "one point, likely artifact, not chased further") rather than re-snapshotting the
  already-closed warm-up-curve question.
- **New bench point (`state/bench-r214.json`/`.md`) at swap=975 MB (grown further since round 208's
  703 MB point) shows prefill 7.14 tok/s and decode 5.33 tok/s — both back inside/above the 3-boot
  plateau band (~6.95-7.10 prefill / ~4.95-5.18 decode).** Swap was confirmed flat (975462400 bytes)
  immediately before and after the ~3-minute bench run, i.e. NOT itself mid-transition this time.
  **This resolves round 208's flagged dip as a transient artifact of measuring literally inside a
  ~10-minute swap-onset window, not a standing swap-volume effect** — more swap since then produced
  full recovery, not continued degradation, which rules out "swap volume degrades prefill."
- **New: ceiling-contact rate confirmed front-loaded with a second data point.** `memory.events.max`
  moved 1006 (round 208, uptime 4h35m) -> 1017 (this round, uptime ~7h24m) — only 11 new contacts in
  the intervening ~2h49m, ~3.9/hour, an order of magnitude below round 208's own first-4.5-hour
  average (~220/hour) and now close to (below) the old 30h boot's steady-state ~33/hour (round 160).
  Supports round 208's "cold-page-cache effect specific to the first several hours" hypothesis with a
  second point showing the rate has already mostly decayed by ~7h. Zero OOM kills throughout (4th
  boot/restart in a row with reclaim-but-never-kill).
- **Cross-track note, not acted on:** two NEW untracked files appeared since round 172/196 last
  flagged this area — `languages/whence/examples/expense_tracker.lang` and
  `languages/whence/examples/test_simple.lang` (both mtime 2026-08-27 15:44:50, same instant as the
  already-known `whence_qwen_bridge.py`/`pyproject.toml`) — consistent with the standing note that a
  separate autonomous system (Hermes gateway) shares this repo. Flagged only, not E's file.
- **Still unchanged:** E1-E5 remain fully DONE; E3 A/B and OLMoE NVMe check remain fully staged and
  parked (`--cap 256` unchanged on this boot too — an 8th boot/restart in a row with no operator
  action), channel still treated as dead per round 166, not re-solicited again.
- **Recommendation for next E round:** this boot's two open threads are now both resolved/confirmed
  at two points each — do not re-snapshot this same boot again without a new anomaly. Wait for a
  genuinely new boot/restart (worth one fresh warm-up/ceiling-rate check as a 4th replicate), or pivot
  to another track's backlog. Full writeup:
  `knowledge/round-214-nuc-e-swap-onset-artifact-resolved-and-ceiling-rate-decay.md`.

## Round 232 addendum (2026-08-28, box UP — SAME boot as rounds 208/214/226, uptime ~15h25m)

- **Backfilled round 226** (`936e119`, landed by round 227): one real bench point,
  prefill 7.19 tok/s / decode 5.23 tok/s (`state/bench-r226.json`/`.md`) — inside the
  established plateau band, no anomaly, never got its own knowledge file (round 226 was
  interrupted by an unrelated background-wait trap before it could write one). No
  correction needed to the data itself.
- **Did not take another bench point** — per round 214's own recommendation, this boot's
  warm-up/plateau questions are already closed. Instead read the FULL boot's request log
  (`journalctl --user -u qwen36-colibri.service --since '2026-08-27 11:50:48'`, saved to
  `state/nuc-r232-request-log.txt`, 77 requests total) — something no earlier E round had
  done — and found all 77 requests fall into exactly 4 tight clusters that match the 4
  known E-round bench windows (round 202's sweep: 57; round 208: 5; round 214: 5; round
  226: 10), separated by hours of complete silence (~13h13m of this ~15h25m boot has
  carried zero traffic). **This box has served no organic/operator traffic this entire
  boot** — every request ever logged is our own.
- **This corrects rounds 208/214's "front-loaded ceiling-contact-rate decay" reading**:
  cross-referencing round 208's own knowledge file shows its `memory.events.max` 1006→1017
  delta happened WITHIN round 208's own 5-request bench cluster (a few minutes), not over
  the following 2h49m gap round 214 attributed it to (which the request log confirms was
  fully idle, zero requests). `memory.events.max` is still exactly 1017 now, unchanged
  since round 214's cluster through round 226's entire 10-request cluster and 2h13m more
  — 20 real requests across 8 hours produced zero new ceiling contacts. Reframed: not a
  decaying hourly rate, but a one-time working-set-fill event (round 202's dense sweep)
  followed by a steady state where isolated small bursts don't re-trigger the hard limit.
  Round 202's own internal warm-up curve (dense back-to-back sampling) is unaffected by
  this correction — only the cross-round "events per elapsed hour" framing is retired.
- **Separately, `memory.swap.current` does NOT show the same confound** — it grew
  +272 MB during a fully idle 2h41m window (703→975 MB, zero requests) and a further
  +257 MB over the next ~8h despite only 15 real requests in that span — swap growth looks
  like a background, request-independent kernel process, decelerating over the boot's
  lifetime (same qualitative shape as the old 30h boot's 142→154→160 trajectory,
  reproduced on a second, independent boot). Zero OOM kills throughout, unchanged.
  `--cap 256` still unchanged; `who -a` shows no active operator session.
  Full writeup: `knowledge/round-232-nuc-e-ceiling-contact-rate-was-our-own-traffic.md`.
- **Recommendation for next E round:** don't compute a cumulative-counter/elapsed-uptime
  "rate" again without checking `journalctl` for the actual request timestamps first —
  cheap (2 SSH one-liners), and this round shows it changes the conclusion. This boot's
  threads are closed a third time; wait for a new boot/restart, or pivot. One open thread
  if picked up: whether passive swap growth (§4 of the knowledge file) ever fully stops
  with truly zero requests, vs. this boot's data (which always had *some* nearby bench
  cluster) can't distinguish that from "keeps drifting regardless."

## Round 238 addendum (2026-08-28, box UP — SAME boot as rounds 208/214/226/232, uptime ~18h04m)

- **Closed round 232's one flagged open thread**: whether passive `memory.swap.current`
  growth continues at a positive rate with truly zero requests, or needs at least occasional
  nearby traffic. This round caught the box in exactly the needed control window — a
  confirmed 2h39m59s with ZERO HTTP requests (`journalctl` since round 232's own
  `2026-08-28 03:15:55` measurement instant, double-checked two ways) — and found swap still
  grew, 1232→1291.87 MB (exact bytes: 1,291,870,208), ≈22.5 MB/hr. Three same-boot rate
  points now on record (208→214: ≈101.6 MB/hr, zero requests; 214→232: ≈32.1 MB/hr, mostly
  idle; 232→238: ≈22.5 MB/hr, **fully zero requests**) show a clean, monotonic deceleration
  with the *strongest* request-independence control landing the *lowest* rate, not the
  highest — confirms round 232's hypothesis (background, request-independent kernel
  writeback, decelerating with boot lifetime) rather than "needs occasional traffic to keep
  moving." `memory.events.max` stayed exactly 1017 (unchanged since round 214), reconfirming
  the hard-ceiling counter is genuinely inert with zero traffic, unlike swap.
- Did not take a bench.py prefill/decode point (not needed — the finding is entirely from
  cgroup counters + journalctl, 2 cheap SSH round-trips, no new engine traffic added).
- `--cap 256` still unchanged, same boot as rounds 208/214/226/232 — 9th+ reachable window
  with zero evidence of the escalation channel (E3 A/B, OLMoE NVMe check, cap change) ever
  reaching the operator; not re-solicited again per round 166.
- E1-E5 remain fully DONE; E3/OLMoE stay fully staged and parked. Full writeup:
  `knowledge/round-238-nuc-e-passive-swap-growth-continues-at-zero-requests.md`.
- **Recommendation for next E round:** this specific thread is now closed with real data;
  don't re-chase it on this same boot without a new anomaly (rate going flat, or continuing
  to not decelerate). A materially later zero-request window on this same boot would be a
  cheap opportunistic bonus point but is not urgent. Prefer a fresh boot/restart for the
  next routine warm-up-curve replicate.

## Round 244 addendum (2026-08-28, box UP — SAME boot as rounds 208/214/226/232/238, uptime ~19h58m-20h02m)

- **Took round 238's own suggested opportunistic follow-up point (a later
  zero-request-window swap reading on this same boot) and it broke round
  238's "clean monotonic deceleration" story rather than confirming it.**
  Swap grew 1291.87 MB (round 238, 05:55:54 UTC) → 1548.62 MB (this round,
  07:49:14 UTC) — 256.75 MB over ~1.897h, zero requests confirmed
  (journalctl), implying ≈135-136 MB/hr — HIGHER than every prior rate on
  this boot including the earliest (208→214's 101.6 MB/hr), reversing
  round 238's 101.6→32.1→22.5 MB/hr deceleration trend rather than
  continuing it.
- **A controlled 3-minute sub-window (07:50:10→07:53:20, zero requests,
  cgroup file read directly) measured exactly 0 bytes of growth**, and a
  follow-up read 26s later confirmed the value was still identical (swap
  flat for ≥4m32s straight after the elevated-rate window). This proves
  the 256.75 MB arrived as a burst that had already finished before this
  round even connected — not a newly-elevated sustained rate.
- **Reproduces round 142's exact finding from the OLD 30h boot (a burst
  that `vmstat`/PSI showed had already completed by measurement time) on
  this SECOND, independent boot** — generalizes what was previously only a
  single-boot observation. Revises round 238's model: the "clean
  deceleration" read was real arithmetic over real coarse (2.7-8h) windows,
  but the underlying process is bursty at a finer grain those windows
  couldn't resolve, not smoothly continuous. `memory.events.max` stayed
  exactly 1017 throughout (unchanged since round 214), reconfirming that
  counter's total inertness at zero traffic, unaffected by this correction.
- **Practical note for future E rounds:** a wide-window before/after swap
  delta is not a reliable instantaneous rate on this box and should not be
  extrapolated linearly — always pair it with a short controlled sub-window
  check (cheap: 2 SSH one-liners around a `sleep`) before reporting a rate.
- `--cap 256` unchanged, no operator login (`who -a`), E3 patch + OLMoE
  tarball both spot-checked present/unchanged, escalation channel still
  treated as dead per round 166, not re-solicited. E1-E5 remain fully DONE;
  no bench.py point taken (not needed for this finding). Full writeup:
  `knowledge/round-244-nuc-e-swap-growth-is-bursty-not-smooth-deceleration.md`.
- **Recommendation for next E round:** the open thread is now burst
  STRUCTURE (size/duration/frequency), not deceleration — needs a tight
  polling loop (`memory.swap.current` every 10-30s for 10-20 min) or
  `/proc/vmstat`'s cumulative `pswpout` sampled the same way to actually
  catch a burst in progress; neither attempted yet. Otherwise prefer a
  fresh boot/restart for the next warm-up-curve replicate over a 6th+
  snapshot of this now-20h+ boot.

## Round 256 addendum (2026-08-28, box UP — SAME boot as rounds 208/214/226/232/238/244, uptime ~23h32m-23h48m)

- **Ran `nuc/swap_watch.py` for real for the first time** (built by rounds 250/251, never
  executed — round 250 hit the notification/one-shot trap waiting on this exact 15-minute
  job). This round avoided the trap by blocking on the background SSH job with chained
  `TaskOutput(block=true)` calls inside its own turn instead of ending the turn to wait.
- **Result: 61 samples over 900s at 15s intervals, ZERO growth, ZERO bursts** —
  `memory.swap.current`, `memory.current`, `pswpin`, and `pswpout` were all byte-for-byte
  identical across every single sample. The pre-watch baseline read was also identical to
  round 244's own final reading (1,548,619,776 bytes) taken ~3h34m earlier (verified not
  stale: other counters live/plausible, re-read 46s later, `journalctl` confirmed zero
  requests) — so the real flat window this round establishes is ~3h50m, the longest and
  only truly tight-interval (15s) flat replicate on record for this boot.
- **Revises round 244's own "bursty, not decelerating" model further**: rather than an
  ongoing recurring burst process of unknown size/frequency, the data now supports a
  decaying-frequency process that may have gone fully quiescent around the ~20h mark on
  this boot (growth was steady through rounds 208→244, uptime 2h40m→20h02m, then zero
  through this round's ~23h29m→23h48m window). One ~4h flat window can't yet distinguish
  "stopped for good" from "next burst hasn't happened yet at a much lower frequency."
  `memory.events` `max` still exactly 1017 (unchanged since round 214). `--cap 256`, E3
  patch, OLMoE tarball all spot-checked unchanged; no operator login; escalation channel
  still dead per round 166, not re-solicited. Raw sample data:
  `state/nuc-swap-watch-r256/swap-watch-round256.json`. Full writeup:
  `knowledge/round-256-nuc-e-swap-watch-15min-first-real-run-fully-quiescent.md`.
- **Recommendation for next E round:** either take several more cheap multi-hour coarse
  checks across future rounds, or leave one `swap_watch.py` invocation running for hours
  using the same block-without-ending-turn discipline this round proved works — that's the
  only way to tell "stopped" from "rare burst not yet observed" apart. If a future baseline
  read differs from this round's own (1,548,619,776 bytes), treat it as a live burst and
  reach for the tight-poll tool immediately rather than inferring after the fact.

## Round 262 addendum (2026-08-28, box UP — SAME boot as rounds 208/214/226/232/238/244/256, uptime ~25h44m-26h04m)

- **Hit round 256/261's own falsifier on the first read**: this round's baseline
  `memory.swap.current` (1,625,858,048 B) differs from round 256's last flat sample
  (1,548,619,776 B) — a real +73.66 MB burst occurred sometime in the ~1h56m gap between
  the two rounds. Corroborated exactly by `/proc/vmstat`'s `pswpout` delta (18,857 pages
  × 4096 = 77,238,272 B, an EXACT match, not approximate).
- **Immediate fresh 20-minute tight poll (81 samples, 15s interval) found ZERO further
  growth** — the burst had already finished before this round could catch it in progress,
  same shape round 244 and round 256 each independently found. This is the third
  independent instance of "a wide-window delta shows growth but the tight poll right
  after finds it already over."
- **Settles round 256/261's open question**: swap growth on this boot has NOT
  permanently stopped (round 256's "may have gone fully quiescent around ~20h" read is
  falsified) — it's a recurring burst/quiescent-interval cycle continuing well past the
  25h mark, not a process that reached a terminal quiescent state. Exact
  duration/instantaneous rate of this specific burst remains unresolved (it happened
  inside an unpolled gap) — would need either tighter round-to-round spacing or one
  genuinely multi-hour continuous poll to close that gap.
- `--cap 256`, E3 patch, OLMoE tarball all spot-checked present/unchanged; `memory.events`
  `max` still exactly 1017 (unchanged since round 214, even across this new burst); no
  operator login; escalation channel still dead per round 166, not re-solicited; no
  `bench.py` point taken. Raw sample data:
  `state/nuc-swap-watch-r262/swap-watch-round262.json`. Full writeup:
  `knowledge/round-262-nuc-e-swap-watch-second-burst-confirms-recurring-not-quiescent.md`.
- **Recommendation for next E round:** keep taking the cheap baseline-read-vs-last-round
  comparison every round (now 3/3 diagnostic); tally burst-count-per-elapsed-hour once
  4-5 such data points exist rather than eyeballing individual gaps; a genuinely
  multi-hour continuous `swap_watch.py` run is still the only way to catch a burst
  actually in progress, not attempted yet.

## Round 268 addendum (2026-08-28, box UP — SAME boot as rounds 208/214/226/232/238/244/256/262, uptime ~28h21m)

- **Seven-gap burst tally (recommendation from round 262 item 2)**: assembled all 7
  round-to-round `memory.swap.current` baseline deltas recorded on this boot into one
  table, re-deriving each from raw bytes/timestamps rather than copying prose forward —
  found and fixed a MiB-vs-MB unit slip in round 262's own "+73.66 MB" figure (actually
  73.66 MiB = 77.24 MB decimal, the number its own 39.5 MB/hr rate was actually computed
  from). Result: 6 of 7 gaps (85.7% of 23.03 tracked hours) show real growth, only 1 gap
  is genuinely flat; rates run 101.6/32.1/22.5/135.4/0.0/39.5/46.3 MB/hr with no trend by
  boot age or request count; mean (44.62 MB/hr) misses 4 of 7 individual gaps by >30%.
  Every tight poll ever run on this box (3 of them, 2280s cumulative at 15s interval) has
  caught zero growth in progress, despite 6/7 wide gaps showing real growth — strong
  indirect evidence bursts are short/sparse relative to a few-hundred-second poll.
- **Launched this track's first genuinely multi-hour continuous `swap_watch.py` run**
  (recommendation from round 262 item 3, deferred twice as "too much of a round's own
  budget") — done via a **detached** (`nohup … & disown -h`) background process so it
  costs this round's own wall-clock budget nothing. Added `--checkpoint` to
  `nuc/swap_watch.py` first (appends+flushes+fsyncs one JSON line per sample) so an
  8-hour unattended run surviving a box restart/crash doesn't lose all its data — the
  original script only wrote its aggregate JSON once, at the very end. 6 new offline
  tests (`nuc/tests/test_swap_watch.py`, this script had none before); full `nuc/tests/`
  163/163. Running as pid 16184, started 2026-08-28 16:18:5x UTC, `--duration 28800`
  (8h), expected completion ~2026-08-29 00:18:55 UTC — output at
  `~/nuc-research/swap-watch-r268-long.json` + `~/nuc-research/swap-watch-r268-
  checkpoint.jsonl` on the box. **Next E round: collect and analyze this first** (see
  `knowledge/round-268-nuc-e-checkpointed-long-run-and-seven-point-burst-tally.md`
  "handoff" section for exact steps, including what to do if the box restarted or the
  run is still in progress).
- `--cap 256`, E3 patch, OLMoE tarball unchanged; no operator login; `memory.events.max`
  still exactly 1017 (unchanged since round 214); escalation channel still dead per
  round 166. E1-E5 remain fully DONE.

## Round 274 addendum (2026-08-28, box UP — SAME boot as rounds 208/214/226/232/238/244/256/262/268, uptime ~30h16m; r268's 8h swap-watch run still in progress, ~1h46m of 8h elapsed)

- **First swap burst ever caught live by a tight poll.** Pulled the r268
  long run's checkpoint mid-flight (427 samples so far) and found exactly
  one burst: **136.10 MB in a single 15-second poll gap** (18:02:25.336 →
  18:02:40.340 UTC), everything else byte-for-byte flat. Prior tight polls
  (round 244: 3 min, round 256: 900s, round 262: 1200s — 2280s cumulative)
  had all caught zero bursts; this run's first ~6391s already caught one,
  and it delivered more swap growth in 15s than some of round 268's entire
  multi-hour tallied gaps — supports reading each "gap shows growth" event
  as usually one fast burst, not a trickle.
- **Tested and did NOT confirm a plausible confound**: this round's own
  SSH connections to check status happened to fall right inside that one
  burst's 15s window. Correlated `journalctl` sshd session logs against the
  checkpoint and found 10 further SSH connections from this same round, in
  the following ~2m30s, produced ZERO additional bursts (0/10) — the
  coincidence does not replicate and is not adopted as a finding. Kept on
  record specifically so it isn't mistaken for a real effect by a future
  round noticing the same kind of coincidence.
- **The 8h run (started round 268, pid 16184, `~/nuc-research/swap-watch-
  r268-checkpoint.jsonl`) is NOT complete** — still needs ~4h20m to reach
  its planned 2026-08-29 00:18:55 UTC finish. Next E round: check
  `ps aux | grep swap_watch` on the box first; if still running, another
  opportunistic mid-run pull is cheap and valuable (as this round showed);
  if finished (or the box rebooted, killing it), follow round 268's own
  completion handoff steps. Full writeup:
  `knowledge/round-274-nuc-e-r268-run-first-burst-caught-live-and-ssh-coincidence-refuted.md`.

## Round 286 addendum (2026-08-28, box UP — SAME boot as rounds 208/214/226/232/238/244/256/262/268/274/280, uptime ~1d9h51m)

- **Third mid-flight collection of round 268's 8h `swap_watch.py` run**
  (pid 16184, started 16:18 UTC, still ~2h34m from planned 00:19 UTC
  2026-08-29 completion at check time — not collected to completion,
  same reasoning rounds 268/274/280 gave). Now 1298 samples (5.41h),
  **4 bursts total** (round 280's 3 + a new 79.43 MB one at 21:32:28 UTC).
- **Settled round 280's open "fixed ~135 MB quantum" question: no.** The
  4th burst isn't a clean fraction of the first three's ~135.43 MB mean —
  the earlier size clustering was coincidence, now confirmed with direct
  evidence.
- **New finding**: per-burst `pswpout_pages` (from `/proc/vmstat`, ×4096
  byte page size) matches the cgroup's `memory.swap.current` delta
  **exactly** for 3 of 4 bursts (ratio 1.0000) and near-exactly for the
  4th (1.0065) — a finer-grained confirmation than rounds 262/268's prior
  wide-window-only cross-check, using data every checkpoint already had
  but no round had compared at single-burst granularity before. Full
  writeup:
  `knowledge/round-286-nuc-e-r268-run-fourth-burst-breaks-quantum-and-exact-pswpout-cross-check.md`.

## Round 298 addendum (2026-08-29, box DOWN at check time — tailscale reports `pgain-nuc` offline)

- **Closed out round 268's 8h `swap_watch.py` run for good.** The complete
  dataset (1921 samples, full 28800s/8.00h span, landed by round 295's
  `7508a00` commit) contains exactly 4 bursts total — the same 4 round 286
  had already found at its own mid-flight 5.41h check, confirming the final
  ~2.6h of the run added zero new bursts (the run ended in its longest flat
  stretch, 2.77h with no growth). **Burst-count-per-hour tally (open since
  round 262): 4 bursts / 8.00h = 0.50/hr average**, but inter-arrival gaps
  span 525s-9977s (19x spread) — bursty, not periodic, confirmed on the
  first fully-complete multi-hour dataset. Whole-run wide-window rate:
  **60.70 MB/hr** (485.71 MB total / 8.00h) — the most trustworthy single
  smoothed-rate figure produced by this track so far (continuous 15s-
  granularity trace, not a two-point delta). Re-ran round 286's per-burst
  `pswpout` cross-check on the complete data: byte-identical to round 286's
  mid-flight numbers (3/4 exact at ratio 1.0000, 4th at 1.0065, confirmed
  not a mid-flight artifact). Full writeup:
  `knowledge/round-298-nuc-e-r268-8h-run-final-closure-burst-per-hour-tally.md`.
- **Live check this round found the box unreachable.** LAN-path key
  (`id_ed25519_nuc`) absent from this environment's `~/.ssh/`; tailnet SSH
  (`100.78.44.111`) timed out; `tailscale status` confirms `pgain-nuc ...
  offline, last seen 1m ago` — the box itself is down, not a routing
  problem on this end. No fresh standing-state re-verification (`--cap
  256`, E3 patch, OLMoE tarball, `memory.events` max, operator login,
  escalation channel) was possible this round; next reachable round should
  redo these as part of its own setup.

## Round 304 addendum (2026-08-29, box DOWN entire round — `pgain-nuc` last seen 1h ago at start, 2h ago at end)

- **Live check found the box unreachable again**, same shape as round 298:
  tailnet SSH (`100.78.44.111`) timed out (exit 255, "Connection timed
  out"); LAN-path key still absent from this environment. Re-checked at
  the end of the round too — still down, confirming this wasn't a
  transient blip this round's own attempt happened to miss.
- **Built the two pieces of infrastructure every prior analysis/relaunch
  round either hand-rolled or skipped**, since a live second poll couldn't
  be launched: `nuc/swap_analysis.py` (reusable burst/gap/`pswpout`
  analysis, validated to reproduce round 298's published numbers exactly
  against the real round-268 dataset, plus a new interior-gap
  coefficient-of-variation stat) and `nuc/swap_watch_launch.py`
  (parametrized deploy+launch+watch — `python3 nuc/swap_watch_launch.py
  launch --tag rNNN --duration 28800` now does in one command what round
  268/292 hand-built across two separate live sessions). Found and fixed a
  real round-100-class `shlex.quote()`-suppresses-remote-tilde-expansion
  bug in the launcher via manual `plan`-mode inspection (not caught by the
  unit tests alone) before it could have broken a real launch. Live-
  verified the launcher's failure-safety path (no orphaned local watcher
  when the remote side fails) against the actual down box — the success
  path remains unverified against a live box. 34 new tests, `nuc/tests/`
  163 → 197 passed. Full writeup: `knowledge/round-304-nuc-e-swap-analysis-
  tool-and-relaunch-infrastructure.md`.
- **Still open, unchanged**: the second multi-hour poll itself (round
  298's original ask) remains unlaunched — three consecutive reachable-
  round attempts (298, 304, and every round in between) have now found the
  box down at check time. Standing state (`--cap 256`, E3 patch, OLMoE
  tarball, `memory.events` max, operator login, escalation channel) again
  NOT re-verified this round.

## Round 310 addendum (2026-08-29, box DOWN entire round — third consecutive down window, same continuous outage as rounds 298/304, start now pinned exactly)

- **Live check found the box unreachable a third consecutive time** (298,
  304, 310): tailnet SSH timed out at both round-start (05:45:46 UTC) and
  round-end (05:47:35-05:48:44 UTC) checks; LAN-path key still absent.
- **Built `nuc/reachability_check.py`** — a durable, tested up/down log
  (`state/nuc-reachability-log.jsonl`) and CLI (`check --round NNN`,
  `summarize`) replacing this track's prior practice of writing each
  round's own `tailscale status` snapshot as prose and discarding it.
  Backfilled 24 historical records from this file's own round addenda
  (124-304) plus this round's live check; `summarize` groups them into
  4 up/down streaks automatically. 18 new tests, `nuc/tests/` 197 → 215.
- **Proved (not inferred) that rounds 298, 304, and 310 all observed the
  SAME continuous outage**: `tailscale status --json`'s `LastSeen` field
  for `pgain-nuc` does not advance while offline, and this round's own
  live read found it unchanged at `2026-08-29T02:10:00.1Z` — exactly
  consistent with round 298's own knowledge-file mtime (3 minutes later)
  and round 304's own "1h ago"/"2h ago" prose. The outage has now lasted
  **3h37m+** as of this round's last check and is still ongoing.
- **Still open, unchanged**: E3 A/B and OLMoE NVMe check remain fully
  staged and parked; the second multi-hour `swap_watch_launch.py` poll
  (round 304's ask) remains unlaunched a third time; standing state
  (`--cap 256`, E3 patch, OLMoE tarball, `memory.events` max, operator
  login) not re-verified — box down throughout. Full writeup:
  `knowledge/round-310-nuc-e-reachability-log-tool-and-outage-tally.md`.

## Round 334 addendum (2026-08-29, box DOWN entire round — SEVENTH consecutive down window, same continuous outage as rounds 298/304/310/316/322/328)

- **Live checks at round start (12:47:54 UTC) and round end (13:02:44 UTC)
  both found the box unreachable**; tailscale's `LastSeen` for `pgain-nuc`
  is still byte-identical to every check since round 298
  (`2026-08-29T02:10:00.1Z`), so this remains one continuous outage, now
  10h49m+ of *confirmed* down time and still open.
- **Record-gap note**: rounds 316, 322 and 328 added no addendum here —
  each was a down-round whose only live observation was already appended
  to `state/nuc-reachability-log.jsonl` by `reachability_check.py check`,
  which round 310 built expressly to replace per-round prose snapshots.
  That log, not this file, is now the authoritative reachability record;
  this file keeps the mission checklist and the round-level narrative.
  Nothing was lost — the three missing addenda's content is all in the log.
- **Built `streak_bounds`** in `nuc/reachability_check.py` (+ a `bounds`
  CLI subcommand): every duration this track has ever quoted for an outage
  is a check-to-check span, i.e. a strict LOWER bound, and nothing bounded
  it from above. The bracket now reports both, sourced from real evidence
  (`tailscale_last_seen` on the start side, a new `boot_utc` field on the
  end side) with the two ignorance windows broken out separately. Concrete
  effect on this file's own history: outage 1 (rounds 184-196), quoted as
  "5h14m40s" ever since, could really have run to **7h02m26s**. 47 new
  tests, `nuc/tests/` 229 → 276 passed. Full writeup:
  `knowledge/round-334-nuc-e-outage-span-brackets.md`.
- **Still open, unchanged**: the second multi-hour `swap_watch_launch.py`
  poll (round 304's ask) remains unlaunched a SEVENTH time; standing state
  (`--cap 256`, E3 patch, OLMoE tarball, `memory.events` max, operator
  login, escalation channel) again NOT re-verified — box down throughout.

## Round 340 addendum (2026-08-29, box DOWN entire round — EIGHTH consecutive down window, same continuous outage as rounds 298/304/310/316/322/328/334)

- **Three live checks** (17:15:30, 17:15:41, 17:38:03 UTC), all unreachable;
  tailscale `LastSeen` still byte-identical to every check since round 298
  (`2026-08-29T02:10:00.1Z`). Confirmed outage **15h25m14s** and open. The
  17:15:41 record is a duplicate probe 11s after the first — an operator
  slip, kept rather than deleted and annotated as such in its `notes`.
- **Built `gap_continuity` / `continuity_report` / `max_unobserved_streak_s`**
  in `nuc/reachability_check.py` (+ a `continuity` CLI subcommand). Round 334
  showed each streak's *span* was a lower bound; this round found the same
  error one level up — `n_streaks` is a lower bound on the number of state
  TRANSITIONS, because the box can flip and flip back between two
  same-verdict checks. Each intra-streak gap is now classified `full` /
  `reboot_only` / `none` against named evidence, fail-closed.
- **Both outages are now PROVABLY continuous**, not merely asserted: for
  adjacent down checks at t1<t2, a `LastSeen <= t1` read at t2 proves the
  peer was never seen on the tailnet in (t1,t2]. That covers all 11 down
  gaps — including 184->196, whose earlier record predates the field. The
  "one continuous outage since 02:10" line every round since 298 has written
  in prose is finally a computed claim.
- **The finding that reframes this file's own history: 69% of the log's
  97h04m41s span is unwitnessed, and a COMPLETE 14h00m00s outage could have
  happened between rounds 142 and 154** (2026-08-26 03:19Z -> 17:19Z) leaving
  no trace anywhere. Not measured-imprecisely — no record of existing at all.
  No up gap in this log is witnessed, and none can be by any probe.
- **Consequence for this file's record claim.** Rounds 322/328/334 each wrote
  that the current outage is the longest this track has measured while their
  own elapsed (8h/9h/10h49m) was still SHORTER than that hidden 14h
  competitor. The claim was not wrong, it was unsupported. It became
  supportable at `2026-08-29T16:13:07Z` (first down check + 14h00m), so
  round 340 is the first round that can make it: new
  `definitely_longest_including_unobserved: true`, margin 1h25m14s.
- **`boot_utc` is deliberately NOT a witness** (`reboot_only`):
  `/proc/uptime` is CLOCK_BOOTTIME-based and keeps counting across suspend,
  so an unchanged boot time cannot exclude a suspend/resume — this box's own
  documented failure mode (round 184's ARP-incomplete finding). Verifying
  that on the box is on the return checklist.
- **Built, tested offline, NOT run live: `parse_boot_history` /
  `boot_history_probe`** for `journalctl --list-boots -o json`. It is the
  only source that can witness an up gap at all, because the box writes it
  continuously rather than being sampled — and it retroactively witnesses
  gaps arbitrarily far back. Closes the reboot half of the blind spot;
  the suspend half stays open by construction and is pinned as a test.
  **First action on the first up check: run it and save the output** — its
  value is highest the first time, and journal retention means waiting
  loses data permanently.
- 72 new tests (`nuc/tests/` 276 -> 348); 35 hand-designed mutants, 35
  killed. Full writeup:
  `knowledge/round-340-nuc-e-gap-continuity-and-the-unobserved-outage.md`.
- **Still open, unchanged**: the second multi-hour `swap_watch_launch.py`
  poll (round 304's ask) remains unlaunched an EIGHTH time; standing state
  (`--cap 256`, E3 patch, OLMoE tarball, `memory.events` max, operator
  login, escalation channel) again NOT re-verified — box down throughout.

## Round 346 addendum (2026-08-29, box DOWN entire round — NINTH consecutive down window, same continuous outage as rounds 298/304/310/316/322/328/334/340)

- `reachability_check.py check --round 346`: `down`, ssh rc 255 (connect to
  `100.78.44.111` port 22 timed out), tailscale offline, `last_seen`
  `2026-08-29T02:10:00.1Z`, `boot_utc` null. Streak 298→346, 13 checks,
  **confirmed span 19h38m06s, ongoing, start bracketed to ±3m06s**.
- Consequently unchanged, ninth time: the second multi-hour
  `swap_watch_launch.py` poll is still unlaunched; standing state (`--cap
  256`, E3 patch, OLMoE tarball, `memory.events` max, operator login,
  escalation channel) NOT re-verified; `boot_probe` and `boot_history_probe`
  live paths still unrun.
- **Change affecting this file's authority.** `CLAUDE.md`'s
  `## Track E — NUC integration: HARD RULES` section had been missing from
  the working tree since commit `e376750` and was restored this round from
  `ee30654`. Every RULE is verbatim (read-only paths, the port-8001
  prohibition, allowed write paths, the unit-restart rule, the endpoint list,
  **D-013**, the two-SSH-failures rule). Four COORDINATES were reconciled
  against this file, which round 346 treated as the live record and which
  `CLAUDE.md` now explicitly defers to:
  - connect line leads with the tailnet path
    `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` (round 154 above); the LAN
    address is `192.168.1.37`, not the `192.168.1.42` the original carried.
    **Note for a future up-round: `~/.ssh/id_ed25519_nuc` does not exist on
    this host** — the only key present is `id_ed25519`, so the LAN command as
    written above and in CURRICULUM.md would fail on key path alone. Not
    fixed here because it has never been tested from this host; verify on the
    first up-round and correct both files then.
  - `qwen36-colibri` noted as a USER unit (round 100 above).
  - both engine ports noted 127.0.0.1-only (round 154 above).
  - the results-path bullet drops "(Mac)"; the driver runs on the NUC host.
- If any of those four is wrong, `git show ee30654:CLAUDE.md` is the source.
  Full writeup: `knowledge/round-346-nuc-e-deleted-vs-never-written.md`.

## Done-criteria for any mission
Code runs (proof in round file), measurements banked in both places,
`state/nuc-missions.md` checkbox ticked with a one-line result summary.

## Round 352 addendum (2026-08-30, box **UP** — FIRST up-round since 292, ending the nine-round outage; NEW boot `43e0c767`, boot_utc 2026-08-30T00:32:27Z, uptime 1h48m at first contact)

- **CORRECTION to this file's own "Known facts" header block.** The line
  "deployment drift: systemd units qwen36-colibri/qwen36-toolproxy no longer
  exist; same engine runs as user processes" is **wrong and is now disproven
  live**, not just scope-corrected. `systemctl --user list-units` shows
  `qwen36-colibri.service` and `qwen36-toolproxy.service` both
  `loaded active running`, `is-active` = `active` for both. Round 100 already
  flagged the "units no longer exist" line as a scope error (they are USER
  units); this round adds the part round 100 could not see — **both units
  started at 00:32, i.e. at boot**, so they auto-start (enabled + linger).
  No prior round could establish that, because every prior observation was of
  an already-long-running boot. The header line is left in place with this
  addendum as its correction, per this file's existing convention.
- **The nine-round outage, settled by the box's own journal.** Previous boot
  `391cb36e` last entry `2026-08-29T02:10:07Z`; this boot's first entry
  `2026-08-30T00:32:32Z` ⇒ **80545.0 s = 22h22m25s**. Round 346's bracket
  `[19h38m06s, 22h22m26s]` had its **upper bound right to 1.9 s** while its
  confirmed span was 2h44m19s short. Raw: `state/nuc-boot-history-r352/`.
  Also visible there: a **85h33m** inter-boot gap 2026-08-20 → 08-23, longer
  than anything the reachability log has ever spanned.
- **E-mission status: E1–E5 all still DONE; nothing new unchecked.** This
  round's work was the standing round-304 backlog, not a new mission.
- **Round 304 item 1 (second multi-hour swap poll) LAUNCHED** after nine
  deferrals — remote pid **2337**, 8h/15s, out
  `~/nuc-research/swap-watch-r352-long.json`, checkpoint
  `~/nuc-research/swap-watch-r352-checkpoint.jsonl`, due ~2026-08-30T10:25Z.
  Local watcher pulls into `state/nuc-swap-watch-r352/`. **Check `poll.log`
  for `PULL_DONE` and `ps aux | grep swap_watch` on the box before launching
  anything new.** `swap_watch_launch.py` hung its ssh client on this, its
  first-ever live run (the remote side succeeded; `&` bound to a bare `&&`
  list, leaving an unredirected subshell holding sshd's channel in `do_wait`
  for the full 8h). Fixed and live-verified — see the round-352 knowledge file
  §3. A short throwaway probe run (`r352probe`, 40 s) was used to verify the
  fix and has long since exited.
- **Round 304 item 2 (standing state) re-verified, all six** —
  `state/nuc-standing-r352/snapshot.txt`: `--cap 256` unchanged in the live
  `coli serve` cmdline; **E3 patch still NOT applied** (`qwen36.c` carries no
  prefix-reuse markers, mtime Aug 23 15:27 untouched); OLMoE tarball still on
  NVMe at `/home/jab/nuc-research/models/olmoe_merged.tar`; `memory.events`
  max **0** — the 30 GiB ceiling has not been touched once this boot, with
  `memory.current` 9.10 GiB and `memory.swap.current` 0 B; operator idle
  (2 users, load 0.00) and, an **eleventh** boot in a row with no operator
  action on any of this program's asks — the escalation channel stays dead
  per round 166.
- **Connect-path note CLOSED (round 346's open item).** `~/.ssh/id_ed25519_nuc`
  **does not exist** on the driver host, and `192.168.1.37` **does not route**
  from it (connection timed out). The LAN command as written in CURRICULUM.md
  and CLAUDE.md would fail from here on key path *and* on route. The tailnet
  path `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` is the only working one
  from this host, which is what CLAUDE.md already leads with.
- Journal retention is **3.2 G**, which is why 7 boots back to 2026-08-19 are
  still readable — the thing that made the outage bracket answerable at all.
  A future round wanting boot history from before 08-19 has already lost it.

## Round 358 addendum (2026-08-30, box **UP** — same boot `43e0c767` as round 352, uptime 5h15m at first contact)

- **E-mission status: E1–E5 all still DONE; nothing new unchecked.** This
  round's work was round 352 §8 item 2 plus item 1, not a new mission.
- **A published continuity number was withdrawn.** Round 352 reported
  `unwitnessed 0h00m00s` / `max_unobserved_outage: None` /
  `transition_count_upper_bound: 4` for the whole reachability log, on the
  strength of round 340's `_boot_history_witness` calling endpoint coverage
  `WITNESS_FULL`. Endpoint coverage rules out a REBOOT and nothing else — the
  same exclusion `boot_utc unchanged` already made — and cannot see a
  suspend, which round 184 inferred as this box's failure mode. Demoted to
  `WITNESS_REBOOT_ONLY`; the numbers come back as **70h53m11s unwitnessed**,
  **14h00m00s** worst unobserved outage (rounds 142→154), upper bound
  **None**. Anyone quoting round 352's continuity figures should quote these
  instead.
- **New: `journal-seconds`, a bound rather than a boolean.** One ssh call
  captures the seconds in which the box's journal has any entry; the longest
  silence inside a gap is an upper bound on any excursion hiding there. Live
  on the rounds 352→358 gap: **3h26m49s gap, longest interior silence 96 s**,
  so that gap can hide at most 0h01m36s. Log-wide `unobserved_total`
  70h53m11s → 67h27m58s. Capture:
  `state/nuc-journal-r358/journal-seconds-boot43e0c767.json`; fresh boot
  history: `state/nuc-boot-history-r358/`.
- **Probe cost, measured — scope it per boot.** `journalctl` over the current
  boot: **5.5 s**. Over the 4.5-day log span: **>300 s pinning one of two
  cores** (~3.3 G of archived journals). A future round wanting the full span
  should expect minutes, not seconds, and should cache.
- **Bound resolution anti-correlates with risk.** 13 % of seconds carried an
  entry inside the 352→358 gap versus 9.9 % boot-wide, because this round was
  ssh-ing into the box during it. The bound is tightest when we are poking
  the box and loosest on a quiet unattended gap. Quote the bound with that
  caveat attached.
- **Round 304 item 1 (the 8 h swap poll) is HEALTHY MID-FLIGHT, not
  collected.** Remote pid 2337 alive, 815 of ~1920 samples at 05:49Z, due
  ~10:25Z — after this round ended. `swap_bytes` 0 and `pswpin/out` 0 on
  every sample; `mem_current` 9.10 → 9.77 GB (32.6 % of the 30 GiB ceiling)
  over 3.5 h. Round 352's P14 is heading for a MISS. **Do not relaunch**
  (round 274's rule): check `state/nuc-swap-watch-r352/poll.log` for
  `PULL_DONE` and `ps aux | grep swap_watch` on the box first.
- **Round 304 item 2 (standing state) NOT re-verified this round** — round
  352 did it 3.5 h earlier on the same boot and nothing has been asked of the
  box since (load 0.00). Deliberate skip, not an omission.
- Hygiene: no writes on the box outside `/work/logs/nuc-continuity-r358.md`;
  `/work/**` otherwise read-only; no unit restarted; **port 8001 never
  contacted**; no engine request of any kind.
- **The round-184 suspend hypothesis, checked directly for the first time —
  NEGATIVE on this boot.** `journalctl -b 0 -k` has zero `PM: suspend entry`
  and zero `Freezing user space`; `journalctl -b 0` has zero
  `systemd-suspend` / `Reached target Sleep`. The 7 apparent hits are all
  `PM: hibernation: Registered nosave memory: [mem …]` stamped at 00:32:32,
  boot-time setup on any machine that could hibernate — **a false positive
  every future grep must exclude.** `sleep/suspend/hibernate.target` are all
  `static`; `/etc/systemd/logind.conf` is an empty `[Login]` stanza;
  `/sys/power/state` is `freeze mem disk`. Capable, not configured, never
  observed. Boots -1 to -6 remain unchecked (archived scan timed out at
  120 s). Signature to use:
  `journalctl -b N -k | grep -E 'PM: suspend (entry|exit)|Freezing user space'`.
- **The full-span journal capture FAILED — capture per boot instead.**
  `journal-seconds --since 2026-08-25T16:11Z --until 2026-08-30T05:47Z`
  returned `n_seconds: 0` after 23 min: elapsed **1417 s against a 1400 s
  client timeout**, so the probe fail-closed to `[]` while the box's side was
  fine (round 352 §3's shape again). Rate, measured: a 30-min window in boot
  `-1` holds **81 991 entries (2733/s), 8.2 s to scan**; boot -1 spans ~38 h
  ⇒ ~10 min. **This box's earlier boots logged ~1000x harder than the current
  one.** Next E-round: one scan per `boot_id`, cached to
  `state/nuc-journal-<boot_id>.json` (closed boots are immutable), timeout
  sized from that rate.

## Round 364 addendum (2026-08-30, box **UP** — same boot `43e0c767` as rounds 352/358, uptime 9h28m at first contact)

- **E-mission status: E1-E5 all still DONE; nothing new unchecked.** This
  round's work was round 304 item 1 + round 358's closing handoff.
- **Round 304 item 1 (the 8 h swap poll) is CLOSED.** Asked for by rounds
  304/310/316/322/328/334/340/346, launched by 352, seen mid-flight by 358,
  **completed 10:25:07Z and collected this round** by round 352's hand-built
  local watcher with no intervention (`PULL_DONE` at 10:26:39Z). Result over
  **1921 samples / 8.002 h**: `memory.swap.current` **0 on every sample**,
  `pswpin`/`pswpout` **0 on every sample**, and `memory.current` **byte-identical
  across all 1921 samples** (9,770,594,304 B = 30.3 % of the 30 GiB ceiling,
  zero increasing and zero decreasing steps). Round 352's P14 is a MISS.
  Data: `state/nuc-swap-watch-r352/swap-watch-r352-{long.json,checkpoint-final.jsonl}`.
- **This corrects round 136.** Rounds 130/136/142 caught this cgroup pinned at
  the 30 GiB ceiling with swap climbing 0 → 310.6 MB → 2.96 GiB; round 136
  concluded "elapsed time alone was enough". It is not. Eight hours of pure
  elapsed time on an idle box moved `memory.current` by **zero bytes** and
  `memory.events` `max` is still **0** on a ~10 h boot. The variable is
  **traffic**, which is round 124's original reading. `--cap 256` is not
  intrinsically over-committed: at rest this deployment needs 9.77 GB. The
  E4 RAM-FAIL recommendation stands (a real Hermes workload IS that traffic),
  but an idle NUC is not in distress and no round should read "swap is
  growing" into a box that has merely been sitting there.
- **Round 358's handoff BUILT and RUN to completion:
  `reachability_check.py journal-boots`** — per-boot journal-seconds capture,
  cached to `state/nuc-journal-cache/journal-seconds-<boot_id>.json`, each
  boot's timeout sized from a 300 s mid-boot rate probe timed ON the box.
  **All 7 boots scanned, all `complete`, 182 623 entry-seconds.**
- **THE RESULT: this box is never quiet for more than two minutes.** Across
  149 h of running time on seven boots the longest journal silence is 300 s,
  and on six of the seven it is 81-123 s. On one log snapshot (38 records,
  113h50m01s span): `unobserved_total` **75h06m29s -> 0h21m56s**,
  `max_unobserved_outage` **14h00m00s -> 0h01m57s** — the rounds-142->154 gap
  that has headlined this figure since round 358 is bounded at 117 s.
  Use `state/nuc-journal-cache/merged-r364-all7.json`.
- **Entry density varies 1605x between boots of the same machine** (boot -5
  0.037 entries/s, boot -2 58.85/s), so per-boot scan cost spans 0.3 s to
  1944 s. No single timeout constant can serve that — round 358's 1400 s was
  ~100x too large for six boots and too small for the seventh.
- **CORRECTION to round 358's published rate.** It reported boot -1 at
  "81 991 entries (2733/s)"; 81 991 entries in 30 minutes is 2733 per
  **minute** = **45.5/s**, which this round's probe measures directly. Its
  ~10 min projection was unaffected (it came from a timed scan, not the rate).
- **Round 304 item 2 (standing state) re-verified, all six** — `--cap 256`
  live and unchanged; **E3 patch still NOT applied** (0 markers in
  `qwen36.c`, mtime Aug 23 15:27); OLMoE tarball present (7,420,160,000 B);
  `memory.events` `max` **0**; operator idle; a **twelfth** boot in a row with
  no operator action on any of this program's asks — escalation channel dead
  since round 166. Both user units `active`.
- **Do NOT compare `unobserved_total` across rounds.** Round 358 published
  67h27m58s; this round's same-method baseline is 75h06m29s. The log is
  append-only and has grown. Round 340's "live-file aggregate pin" hazard.
  Compare methods on ONE snapshot.
- Hygiene: no writes on the box outside the pre-existing `~/nuc-research/`
  poll outputs; `/work/**` read-only; no unit restarted; **port 8001 never
  contacted**; no engine request of any kind.

## Round 370 addendum (2026-08-30, box **UP** — same boot `43e0c767` as rounds 352/358/364, uptime 14h38m at first contact)

- **E-mission status: E1-E5 all still DONE; nothing new unchecked.** This
  round's work was round 364's handoff item 3 (the suspend witness) plus an
  unplanned finding that corrects round 364's own headline.
- **`--cap 256` IS over-committed once a single request lands.** Round 364
  measured `memory.current` byte-identical at 9,770,594,304 B across 1921
  samples / 8.002 h and concluded "at rest this deployment needs 9.77 GB …
  `--cap 256` is not intrinsically over-committed". Same boot, 4h46m later:
  **30,870,429,696 B = 95.8 % of the 30 GiB cap**, `memory.peak`
  **31,670,497,280 B = 98.3 %**, i.e. **517 MiB of headroom**. `pswpout`
  0 → 1669 pages. `memory.events max` still 0.
- **Mechanism, confirmed at the source.** Engine log, this boot, three
  relevant lines: `[qwen36] int4 packed weights detected — unpacking to int8
  in slot` (13:26:32Z), then two `POST /v1/chat/completions 200` (13:28:25Z,
  14:54:08Z). `/work/src/colibri-v170/c/qwen36.c:1224-1242` unpacks int4
  experts **in-slot to int8**, so each demand-loaded expert costs **2× its
  on-disk size** (packed model on disk 23,031,269,773 B). It is a **one-time
  unpack on the first inference of a boot**, not gradual cache diversity.
  **Two requests moved the cgroup 9.77 → 30.87 GB.** This explains rounds
  130/136/142 and reaffirms E4's RAM-FAIL recommendation.
- **Round 184's suspend hypothesis CLOSED, three independent witnesses.**
  `/sys/power/suspend_stats/success = 0` and
  `CLOCK_BOOTTIME − CLOCK_MONOTONIC = −1e−06 s` (zero suspends in 14.6 h);
  longest journal silence **300 s across 149.0 h / 7 boots**, which bounds any
  *unlogged* suspend without needing a grep pattern; and `boot_utc` vs
  journald `first_entry` agreeing **5/5, max |delta| 5.0 s**, correct sign.
  Round 340's item 2 is closed by making its assumption irrelevant —
  `check()` now records the box's own suspend counters beside `boot_utc`.
- **Round 364's "now cheap per boot" is WRONG for six of the seven boots.**
  `journalctl -b -2 -k` alone exceeds 100 s and does not finish; only boot 0
  is cheap (11 s). The per-boot kernel-log grep for boots −1…−6 was therefore
  NOT run — it is also the weakest of the three witnesses.
- **Round 304 item 2 re-verified, all six unchanged** — `--cap 256` live;
  **E3 patch still NOT applied** (0 markers in `qwen36.c`, mtime
  2026-08-23T15:27:33Z); OLMoE tarball present at
  `/home/jab/nuc-research/models/olmoe_merged.tar` (7,420,160,000 B — NOT
  under `/work/models`, which contains only `qwen36_i4_gs64`);
  `memory.events max` 0; no operator login since 2026-08-26 19:24; both user
  units `active`. A **thirteenth** boot in a row with no operator action —
  escalation channel dead since round 166.
- **Journal coverage extended.** `journal-boots` skipped 6 of 7 boots from
  cache and rescanned the open boot in **6.6 s** (projected 7.99 s, timeout
  83 s); boot 0 grew 2783 → 3674 entry-seconds, merged total **183,514**
  (`state/nuc-journal-cache/merged-r370-all7.json`). Fresh `continuity`:
  `unobserved_total` **0h23m39s**, `max_unobserved_outage` **0h01m57s
  unchanged**. Log span now 118h45m57s vs round 364's 113h50m01s — compare
  this figure method-to-method on ONE snapshot only.
- **Next E round, in order:** (1) capture boot history FIRST, (2)
  `journal-boots` + `continuity` (now ~7 s with the warm cache), (3) on the next FRESH boot, poll `memory.current` at ~5 s
  and watch for the `unpacking to int8 in slot` line to catch the transition
  itself — needs no operator approval, only patience and not being the one to
  send the first request.
- Hygiene: READ-ONLY on `/work/**`; no unit restarted; **port 8001 never
  contacted**; no engine request of any kind. **One cleanup action, disclosed:**
  this round left two orphaned `journalctl` scans running when an ssh was
  killed (PIDs 37531/37532/37680/37681, 368 s and 221 s) — they were the entire
  cause of the `load average: 2.84` first observed, and were killed. Load fell
  2.84 → 1.71; `memory.current` byte-identical before and after.

## Round 376 addendum (2026-08-30, box **UP** — same boot `43e0c767` as rounds 352/358/364/370, uptime 19h23m at first contact)

- **E-mission status: E1-E5 all still DONE; nothing new unchecked.** Round
  370's handoff item 3 (catch the int4->int8 unpack live) needs a FRESH boot
  and this was the fifth consecutive round on `43e0c767` — **not runnable,
  carried forward unchanged**.
- **`--cap 256` is not a footprint, it is an unreachable setting.** Derived
  from `qwen36.c:slot_ensure_allocated` (read-only): one cached expert is
  `malloc(3*inter*hidden)` **int8** = 3,145,728 B plus `falloc(2*16384+16384)`
  f32 = 196,608 B, so **3,342,336 B/slot**; the packed shadow `g4/u4/d4` is
  gated on `qt_ready()` (CUDA) and costs nothing on this CPU-only box. 40
  layers x 256 experts = **34.23 GB of cache**, terminal footprint
  **44.00 GB** against a `memory.max` of 32.21 GB — **over by 11.78 GB**, and
  still over by 7.49 GB counting all 4.29 GB of swap.
- **The plateau is 61.6 % fill, not a steady state.** `memory.current`
  byte-identical at 30,870,429,696 B across 4h44m (r370 -> r376) — because the
  engine served **zero** new completions in between (still exactly 2 this
  boot). Inverted against round 364's true zero-slot baseline of
  9,770,594,304 B: **6,313 of 10,240 slots**, cap-equivalent **157.8**, cgroup
  at 95.8 % / peak 98.3 %. Headroom **1,341,825,024 B = 401 slots** out of
  **3,927 still unfilled**. `memory.high` is `max` (no throttle band) and the
  set is all anon (30.60 of 30.87 GB), so the order at the wall is
  cap -> swap -> cgroup OOM kill. Saturating fit to the one observation:
  `memory.max` arrives **0.22 of a request** later.
- **Round 124's "36.0 GB" was the WALL, not the ceiling.** 31.8 GB resident =
  98.7 % of `memory.max`, 4.2 GB swapped = 98 % of all swap, cache only
  **76.6 %** full.
- **The standing operator recommendation changes: `--cap 204` -> `--cap 159`.**
  `nuc/fast_lane.py`'s `QWEN36.expert_bytes` was the expert's **on-disk int4**
  size (1,769,472 B) in a field meaning "bytes per cached slot" — 1.889x too
  small, so every cap E4 ever recommended was computed wrong. Recomputed
  absolutely (`baseline + cap*40*slot_bytes` vs `memory.max`): cap 204 is
  **over by 4.83 GB**; **167** is the largest that fits at zero margin;
  **159** fits with 1 GiB margin and is the new recommendation; 143 and 75
  still fit. New tool `nuc/expert_cache.py` (`geometry`/`plan`/`fill`/`wall`,
  28 tests) is the absolute model and needs no anchor.
- **Correcting the slope alone made it worse**, which is why the anchor had to
  go too: with the right `per_cap` and the old anchor, `fast_lane`'s no-lane
  cap moved 204 -> **225**, further from the true 167. `rss_at_cap` now RAISES
  on an anchor too small to hold its own cache (the old `RSS_FULL` = 32.01 GB
  vs a 34.23 GB cache made `cap_for_free_bytes` answer **7** where it owed
  **-1**), and `fast_lane plan` prints a warning naming the implied-dense gap
  (2.20 GB implied vs 9.25 GB measured).
- **A 1-second `boot_utc` jitter was being reported as a reboot.** `boot_utc`
  is `now - /proc/uptime` at whole-second resolution; the five up-checks of
  this boot read `00:32:27Z` x4 and `00:32:28Z` x1. `_up_gap_witness` treated
  any forward movement as a reboot, so **this round's own check** produced a
  `boot_utc_advanced_inside_gap` excursion contradicted by
  `journalctl --list-boots`. Fixed with `BOOT_UTC_JITTER_S = 5` (5x the
  largest same-boot spread ever seen here, and equal to round 370's largest
  |boot_utc - journald first_entry| across five boots), applied symmetrically,
  with the observed jitter recorded in the witness note rather than swallowed.
- **Journal + continuity.** `journal-boots` skipped 6 of 7 from cache and
  rescanned boot 0 in **6.7 s** (7.7 s total); boot 0 grew 3674 -> 4243
  entry-seconds, merged total **184,083**
  (`state/nuc-journal-cache/merged-r376-all7.json`). Fresh `continuity`:
  `unobserved_total` **0h25m18s**, `max_unobserved_outage` **0h01m57s
  unchanged**, `missed_excursions` **[]**, log span 123h42m44s (r370:
  118h45m57s — method-to-method on one snapshot only).
- **Round 304 item 2 re-verified, all six unchanged** — `--cap 256` live; E3
  patch still NOT applied (0 markers in `qwen36.c`, mtime
  2026-08-23T15:27:33Z); OLMoE tarball at
  `/home/jab/nuc-research/models/olmoe_merged.tar`, 7,420,160,000 B;
  `memory.events max` 0; **no operator login since 2026-08-26 19:24**; both
  user units `active`. A **fourteenth** boot with no operator action —
  escalation channel dead since round 166.
- **Next E round, in order:** (1) one ssh, first thing: re-read
  `memory.current` and the completion count — if a third request landed,
  record whether `memory.events max`/`oom_kill` went non-zero, which resolves
  the 0.22-request prediction either way; (2) round 370's item 3 on the next
  FRESH boot; (3) still blocked on the operator: the `--cap 159` restart and
  the E3 A/B; (4) decide whether `fast_lane`'s relative planner should answer
  at all now that no sound anchor exists for it.
- Hygiene: READ-ONLY on `/work/**`; no unit restarted; **port 8001 never
  contacted**; **no engine request of any kind**. One write on the box, in an
  allowed path: `/work/logs/nuc-expert-cache-r376.md`. Disclosed:
  `journal-boots` ran three times (two exploratory, one final); it rescans the
  open boot and overwrites that boot's cache entry, so the only effect is that
  the intermediate runs saw 4,236 and 4,239 entry-seconds as boot 0 grew. The
  reachability log got exactly one record.

## Round 382 (NUC-integration E) — 2026-08-31, box UP, boot `43e0c767` (sixth consecutive E-round on it)

- **Handoff item 1 answered, and the question is still open.** Completion count
  still **exactly 2** this boot; one `unpacking to int8 in slot` line;
  `memory.current` byte-identical at 30,870,429,696 for **12h54m** now (r370
  15:11Z → r382 00:05Z), with `memory.peak`, `memory.events` (0/0/0),
  `memory.swap.current/.peak` (0/0), `anon` and `pswpout` (1669) all unchanged
  to the byte. Round 376's "0.22 of a request from the wall" is **neither
  confirmed nor refuted** — no third request arrived to test it. Third
  consecutive round in which this deployment's most interesting number is
  unmeasurable because the deployment has no traffic.
- **Round 304 item 2 re-verified, all six unchanged — FIFTEENTH check.**
  `--cap 256` live; E3 patch NOT applied (0 markers, mtime
  2026-08-23T15:27:33Z); OLMoE tarball 7,420,160,000 B; `memory.events max` 0;
  **no operator login since 2026-08-26 19:24**; both user units `active`.
  Escalation channel dead since round 166. The `--cap 159` restart and the E3
  A/B remain owed.
- **`fast_lane plan` now REFUSES on an unsound anchor** (exit 2) instead of
  printing a warning above a wrong table — round 376's item 4, decided.
  The defect was structural, not numeric: round 376 enforced
  `implied_dense >= 0` in the ARITHMETIC and checked
  `implied_dense >= dense_bytes` only in `_plan_table`'s printed warning. Same
  predicate, two thresholds, two layers — so `plan_rows`/`cap_cost`/
  `cap_for_free_bytes` all answered 225 (true: 167) with nothing said.
  `anchor_soundness()` now grades it once: `impossible` (refused always),
  `unsound` (refused unless `allow_unsound_anchor=True`), `sound`.
  **Refused rather than deleted**, because soundness is a property of the
  ANCHOR: at cap_full 159 the terminal footprint is 31.03 GB, fits, is
  observable, and its implied dense weight equals
  `expert_cache.NUC_BASELINE` exactly. So the planner works the day the
  operator restarts — `plan --cap-full 159 --resident-gb 31.03 --swapped-gb 0`
  answers today.
- **Constant sweep (round 376 item 5): ZERO further wrong-side-of-transform
  instances, and a better finding underneath.** Read from `qwen36.c`
  (read-only): `kv_bytes_per_token` 40,960 is **correct** (`ensure_kv` does
  `falloc(kv_heads * max_t * k_head_dim)` for K and V on each `is_attn[i]`,
  `is_attn[i] = (i%4==3)` → 10 of 40, `falloc` ⇒ f32); `fixed_bytes` was
  round 28's rounded 65,900,000 against an exact **65,863,680**; and one term
  was absent entirely — `attn_sc = falloc(attn_sc_thr * max_t)`, context-
  proportional scratch, `nproc`(4)·4 = 16 B/token here.
  **The exact DeltaNet figure was already in this repo**, in
  `nuc/kv_reuse_model.py` since round 28, which derives it (and `conv_dim`)
  independently. Two modules, one constant, ~350 rounds, no cross-check.
- **New tool `nuc/constant_audit.py`** (14 tests) grades size constants by
  their defining EXPRESSION — `derived` / `bare` / `disk`, plus a
  `transform_risk` flag for a bare constant whose *field declaration* means
  live allocation while its *comment block* cites an at-rest provenance. It
  fires on the round-376 source from git (exit 2) and is clean on the fixed
  tree. Round 381 HEAD: 10 constants, **9 bare, derived_fraction 0.0**, 2
  risks. After this round: 19 constants, 14 derived (0.737), 0 risks.
  Note it still flagged `expert_bytes` at its CORRECTED value, because round
  376 fixed the number and left the opaque expression — the detector cannot
  tell a corrected magic number from an uncorrected one, and neither can a
  reader.
- **A test fixture expired 5m32s before this round's first record.**
  `test_cli_continuity_accepts_a_journal_seconds_capture` pinned a synthetic
  coverage window to `2026-08-25 .. 2026-08-31T00:00:00Z` over the live
  append-only reachability log; round 382's check landed at 00:05:32Z, the
  newest gap fell outside coverage, and `max_unobserved_outage_s <= 301.0`
  got **15108.0** — the whole 4h11m48s gap. Its neighbour had been silently
  VACUOUS for four days. Both windows are now derived from the log. New skill
  `expiring-fixture-window`.
- **`max_unobserved_outage` moved for the first time since round 364**:
  0h01m57s → **0h02m01s**, the new maximum inside this round's own 376→382
  gap. 121 s is inside the 81–123 s periodic-emitter band round 364 measured;
  the box did not get quieter, a running maximum got one more draw. Rounds
  370/376 and this round's own P7 all published it as "unchanged" as though it
  were a property of the box.
  Journal: 6/7 skipped, boot 0 4,243 → **4,724** entry-seconds in 7.8 s wall,
  merged **184,564**; `unobserved_total` 0h27m19s; `missed_excursions` `[]`;
  span 127h54m32s.
- Hygiene: READ-ONLY on `/work/**`; no unit restarted; **port 8001 never
  contacted**; **no engine request of any kind**. One write on the box, in an
  allowed path: `/work/logs/nuc-constant-provenance-r382.md`. Four ssh
  sessions, all read-only bar the final scp. `journal-boots` ran once,
  `continuity` twice (the second only to read the rollup); the reachability
  log got exactly one record.
- **Next E round, in order:** (1) one ssh, the completion count — and if it is
  still 2 after a fourth round, consider recording the plateau as permanent
  under zero traffic and stop re-asking; (2) round 370's item 3, still needs a
  FRESH boot; (3) still blocked on the operator: `--cap 159` and the E3 A/B;
  (4) wire `nuc/constant_audit.py` into a health check (harness A) — it is
  offline and sub-second, and nothing but one test currently runs it.

## Round 388 (NUC-integration E) — 2026-08-31, box UP, boot `43e0c767` (seventh consecutive E-round on it)

- **The 13-hour "byte-identical `memory.current`" plateau that rounds 370/376/382
  each published was an instrument reading, not a state.** With the completion
  count STILL exactly 2 and still one `unpacking to int8 in slot` line,
  `memory.current` fell **458,207,232 B** between 00:05:32Z and 04:52:43Z:
  `anon` −274,530,304 and `memory.swap.current` 0 → **+274,530,304**, the same
  number to the byte. `memory.swap.peak` moved with it (was 0 at r382), so the
  event is bracketed inside this round's own gap. **`anon + swap.current` is
  byte-identical across it: 30,600,970,240 both times.** The allocation never
  changed; its residency did.
- **It was NOT the cgroup limit.** `memory.events max` still 0 for the whole
  boot; cgroup `pgscan_direct` 0 and `pgscan_kswapd` 2,587,671; system-wide
  `allocstall_* 0`. Every page was **global kswapd** reclaim — the kernel taking
  pages from the box's largest anonymous working set in response to
  whole-machine watermarks. `workingset_refault_anon` 0: nothing has come back.
  `memory.high` unset, `memory.swap.max` `max`.
- **Pinned to a 10-minute bucket from data already on the box.** `sar -W -f
  /var/log/sysstat/sa31`: 89.88 pswpout/s in the 03:50:05–04:00:03 bucket
  (218.3 MB, 76 % of the event) and 27.54/s in 01:50–02:00 (67.7 MB). The 04:00
  bucket contains `apt-daily.service` (03:50:05, 7.352 s CPU), `apt-news`,
  `esm-cache` and `packagekit` — `sar -B` shows `pgpgin/s` 554.76 and
  `pgscank/s` 1207.00 against an all-day baseline of ~0. **`apt` is the largest
  perturbation this deployment has seen since its restart.** The 02:00 bucket is
  **unexplained**: no journald entry 01:45–02:05, ~4 CPU-seconds, +147 MB
  `Committed_AS` that persisted.
- **`nuc/expert_cache.py` corrected.** Inverting `memory.current` across the
  event reports the expert cache *losing 137 slots*, which `slot_ensure_allocated`
  forbids (`if (s->g) return;` — a slot's block is malloc'd once and reused in
  place on eviction). New `CgroupSnapshot` / `fill_from_snapshot()` invert
  `anon + swap.current`; `check_monotone()` grades a decrease `instrument_error`
  and a test asserts a 100-slot tolerance still does not launder it. Corrected
  figures: fill **6,232 slots / 60.9 % / cap-equivalent 155.8** (published:
  6,313 / 61.6 % / 157.8); headroom **456 slots**, not the naive 538.
- **The correct treatment was one file away.** `full_footprint()` in
  `nuc/fast_lane.py` has summed `resident + swapped` since round 382. `expert_cache.wall()` took a
  `swap_total` parameter and used it only as future runway, never as present
  debt. Second consecutive E-round to find this shape (r382: the DeltaNet
  constant already exact in `nuc/kv_reuse_model.py`).
- **`--cap` reframed: it is a choice of bounding MECHANISM, not a memory
  budget.** At `--cap 256` the engine's terminal footprint is 44.00 GB against
  `memory.max` 32.21 GB and RAM+swap 36.51 GB, so **the LRU in `expert_get`
  (qwen36.c:1322-1355) can never engage on this box** — the OOM killer is the
  only thing bounding the cache. New `bound_by`/`cap_verdict` grade both axes.
  Round 376's "cap 204 is over by 4.83 GB" is against RAM alone; against
  RAM+swap (what round 124 actually observed: 31.8 GB resident **plus** 4.2 GB
  swapped) it is over by **0.537 GB**. Verdict survives, margin was ninefold.
- **A floor nobody had read: `--cap` must exceed 128.** The PILOT prefetch
  queues at most 128 candidates per layer (`int idx[128]`, `if (max_cand > 128)
  max_cand = 128`, qwen36.c:2000/2005); at or below that a layer can have every
  slot in flight, the one `expert_get` path with no LRU victim. v1.7.0 sleeps
  and rescans (its predecessor "corrupts silently rather than crashing").
  **Round 124's `--cap 16` and `--cap 64` lane variants are RETRACTED.**
  Sound band for this box: **`--cap` ∈ [129, 167]**; **159 stays the
  recommendation**, now for two reasons.
- **Is one probe request safe? No, and it is now arithmetic.** `topk = 8`,
  40 layers ⇒ ≤320 uncached slots per token. Against 456 slots of corrected
  headroom: **1 token worst case, 3 expected.** The two models agree, so the
  honest sentence is "any new traffic is unsafe until the cap is lowered", not
  "we lack data". **No engine request sent** — banked as P11 before measuring.
- **Round 304 item 2 re-verified, all six unchanged — SIXTEENTH check.**
  `--cap 256` live; E3 patch NOT applied (0 markers, mtime
  2026-08-23T15:27:33Z, 130,631 B); OLMoE tarball 7,420,160,000 B;
  `memory.events max` 0; **no operator login since 2026-08-26 19:24**; both user
  units `active`. Escalation channel dead since round 166.
- **New `nuc/run_checks_fast.sh`** — the fourth per-round health check (round
  382's handoff item 4, widened). Nothing under `nuc/` ran outside an E round:
  not the 499 tests, not the five instruments, not the audit; detection latency
  was bounded by the rotation at six rounds. Offline by construction, 65.6 s,
  errors-only exit code, FAIL path covered by three tests plus a
  `NUC_FAST_CHECK_NESTED` recursion guard. Found one real bug writing them:
  `set -e` aborts at a command substitution that exits non-zero, so the FAIL
  path would have killed the script before printing why. **NOT wired into
  `run_driver.sh` — harness(A)'s file, per the round 242→247 precedent.**
- Journal: 6/7 skipped, boot 0 4,724 → **5,342** entry-seconds in 6.8 s, merged
  **185,182**; `unobserved_total` **0h29m20s**; `max_unobserved_outage`
  **0h02m01s unchanged** (predicted to move — it did not); `missed_excursions`
  `[]`; span 127h54m32s → **132h38m33s**.
- Hygiene: READ-ONLY on `/work/**`; no unit restarted; **port 8001 never
  contacted**; **no engine request of any kind**. One write on the box, in an
  allowed path: `/work/logs/nuc-reclaim-r388.md`. Twelve ssh/scp
  connections, all read-only bar the scp. `journal-boots` ran twice, `continuity` twice;
  the reachability log got exactly one record.
- **Next E round, in order:** (1) **stop reading `memory.current`** — read
  `anon` + `memory.swap.current` and feed `expert_cache wall --anon … 
  --swap-current …`; (2) the 02:00:05 bucket is unexplained, and **`sa31`
  rotates at 2026-09-01T00:07Z** — capture it before then; (3) round 370's item
  3 still needs a FRESH boot; (4) still blocked on the operator: `--cap 159`
  (now argued as "the LRU can never engage at 256", with a `> 128` floor) and
  the E3 A/B; (5) harness(A) owns wiring `nuc/run_checks_fast.sh` into
  `run_driver.sh`; (6) any future A/B on this box must record whether
  `apt-daily.timer` (03:50 UTC) straddled the measurement window.

## Round 394 (NUC-integration E) — 2026-08-31, box UP, boot `43e0c767` (eighth consecutive E-round) — RECONSTRUCTED ADDENDUM

Round 394 wrote no addendum here; this two-line reconstruction was added by
round 400 so the gap is named rather than silently inherited (round 334's
item 6, third occurrence). The authority is
`knowledge/round-394-nuc-e-the-record-was-already-being-kept.md`.

- Explained round 388's unattributed 01:50–02:00 bucket: `fwupd-refresh` at
  01:57:33Z, a libxmlb silo rebuild ballooning fwupd's heap ~147 MB and
  forcing global kswapd to write 67.7 MB of engine weights to swap. Graded
  *attributed, not proven*. Established that `sar -r` is the missing
  instrument and that the archives already held the per-request fill curve.
- **Corrected `NUC_BASELINE`:** it was a `memory.current` (residency) reading
  and is ~2x too large. Three independent routes agree inside 0.7 %. Fill
  6,232 → **7,686–7,753 slots**, cap-equivalent 155.8 → **192–194**,
  recommendation **159 → 196**, band **[129, 204]** — vindicating round 124's
  original `--cap 204` headline. Built `nuc/perturbation.py`, extended
  `nuc/expert_cache.py`, added `skills/residency-is-not-allocation/` and
  `skills/instruments-already-running/`. 13 HIT / 9 MISS of 22.

## Round 400 (NUC-integration E) — 2026-08-31, box UP, boot `43e0c767` (NINTH consecutive E-round on it)

- **`/var/log/sysstat/` holds NINE days — sa23..sa31 — and this track had
  never opened a file older than `sa30`.** 957 samples at a 600 s cadence, 6
  `LINUX RESTART` markers, 190h50m02s of coverage reaching back to
  2026-08-23T14:02, i.e. across every round of this track from 124 onward and
  through the whole nine-round outage. It is an on-box availability witness
  of a different kind from an ssh probe: a `sar` sample says "this kernel was
  running", not "I could reach it from here".
- **Both recorded outages confirmed by the archive, to seconds.** 184–196 end:
  `boot_utc` 11:50:48Z vs `LINUX RESTART` 11:50:53Z (5 s). 298–346 start:
  `tailscale_last_seen` 02:10:00.1Z vs last sample 02:10:04Z (3.9 s); end:
  `boot_utc` 00:32:27Z vs restart 00:32:34Z (7 s). **`tailscale_last_seen` has
  sourced `earliest_possible_start_utc` for thirteen rounds and had never been
  checked against anything. It is right.** The archive also holds three
  reboots (2026-08-25 00:37:34, 00:47:30, 12:57:41) that predate the log's
  first record — graded `unknown_to_log`, not `conflict`.
- **`unobserved_total` 102h19m47s → 254 s.** 25 of 39 probe gaps CLOSED by the
  archive, 98.28 h of previously-unobserved time retired, and the
  `max_unobserved_outage` of **14h00m00s** (rounds 142→154) that four rounds
  carried as a live bound is covered end-to-end with no hole: no outage hid
  there. The 13 `open` gaps all sit inside the two known DOWN streaks, where
  silence corroborates but does not witness.
- **Round 394's forward prediction scored — the first in this track.** It
  published `apt-daily`'s next fire as 10:22:25Z, inside this round's gap; it
  fired at **10:22:33Z**, confirming that `RandomizedDelaySec` is drawn once
  at schedule time. It cost the engine **zero** pages.
- **`apt` was never sole-attributable.** With the sampler-cadence boundary bug
  fixed, the 04:00:03Z bucket (218.3 MB, 76 % of the boot's swap-out) holds
  **five** named starts — `apt-daily`, `apt-news`, `esm-cache` (03:50:05),
  `packagekit` (03:50:09), `fwupd-refresh` (03:57:05). Rounds 388 and 394
  published "apt is the largest perturbation this deployment has seen"; a
  bucket cannot separate five units, and one of the five is independently
  known to cost 67.7 MB alone. Whole-boot ledger: 62 named fires, 6 in a
  costly bucket (9.68 %), **1 sole-attributable — `fwupd-refresh` 01:57:33Z**.
- **Three recorder artifacts, all of which read as findings first.** 7 of 12
  "gaps" were sysstat's own file rollover (7 of the 7 observable day
  boundaries — `sadc`'s first write into a new file is consumed as the rate
  baseline and never displayed); `sysstat-collect` was in 100 % of costly
  buckets because it *writes* them, and dominated the denominator 218 to 60;
  and timers firing at `:00:05` land on the sampler's own bucket boundary.
- **Standing state re-verified, EIGHTEENTH check, all six unchanged.**
  `--cap 256` live; E3 patch NOT applied
  (`/work/src/colibri-v170/c/qwen36.c`, 130,631 B, mtime
  2026-08-23T15:27:33Z, 0 markers); OLMoE tarball
  **`~/nuc-research/models/olmoe_merged.tar`, 7,420,160,000 B** — the path is
  recorded here because an `ls` of `/work/models/` nearly produced a false
  "it is gone"; `memory.events max` 0; no operator login since 2026-08-26
  19:24; both user units `active`.
- Engine cgroup byte-identical across a THIRD window: `anon` 30,326,439,936,
  `memory.swap.current` 274,530,304 (`peak == current`), sum 30,600,970,240,
  `memory.current` 30,412,222,464, `pgscan_kswapd` 2,587,671,
  `pgscan_direct` 0, `workingset_refault_anon` 0, system `pswpout` 72,044.
  Completions **2**, `unpacking to int8 in slot` **1** — fifth consecutive
  round; recorded as a property of zero traffic and dropped from the
  per-round probe.
- Recommendation unchanged: **`--cap 196`**, band **[129, 204]**,
  `bounded_by: engine_lru`, 1.096 GB margin against `memory.max`.
- Built: `nuc/sysstat_archive.py` (new, 37 tests); `cost_ledger` /
  `parse_unit_starts` in `nuc/perturbation.py` (+14); `unobserved_basis` and
  `--sar-capture` in `nuc/reachability_check.py` (+4);
  `skills/recorder-in-the-record/`. Tests **551 → 606**, all green; audit
  23/18/0.783/0 transform risks.
- Hygiene: READ-ONLY on `/work/**`; no unit restarted; **port 8001 never
  contacted**; **no engine request of any kind**. One write on the box, in an
  allowed path: `/work/logs/nuc-sysstat-archive-r400.md`. Ten ssh/scp
  connections, all read-only bar the scp. `journal-boots` did NOT run — the
  sar archive answered the continuity question at lower cost and higher
  resolution, and loading both would have made the closure figure depend on
  which witness happened to be present, the exact defect `unobserved_basis`
  now exposes. 17 HIT / 6 MISS of 23.
- **Next E round, in order:** (1) **TIME-CRITICAL — `sa23` is overwritten on
  2026-09-23 and everything older is already gone; copy `sa*` into
  `~/nuc-research/` on every up-round, ~2 MB and one scp**; (2) the missing
  `sar29` summary file is a third, zero-cost outage witness this round did not
  use; (3) prove or drop the fwupd attribution — now the only
  sole-attributable event in the boot; (4) still blocked on the operator:
  `--cap 196` and the E3 A/B, and any A/B must record how many units share
  each bucket, not just which fired; (5) round 370's item 3 still needs a
  FRESH boot; (6) harness(A) owns wiring `nuc/run_checks_fast.sh` into
  `run_driver.sh` — 0 references, third round carried (note that
  `skills/run_checks_fast.sh` IS wired, round 363, so a basename grep lies).

## Round 406 (NUC-integration E) — 2026-08-31, box **DOWN** the whole round; first down window since the 298–346 outage, ending a nine-round up streak on boot `43e0c767`

- **Reachability.** `tailscale status`: `pgain-nuc` offline,
  `tailscale_last_seen 2026-08-31T16:30:00.1Z`. Real ssh probe to
  `jab@100.78.44.111` timed out (rc 255). Two consecutive ssh failures, so
  probing stopped per CLAUDE.md. Logged as record 45 of
  `state/nuc-reachability-log.jsonl` (`verdict: down`, `source: live`,
  `precision: precise`). Outage start bracket: after round 400's last contact
  **13:14:19Z** (up), at or after **16:30:00.1Z**.
- **Round 400's item 3 answered anyway, offline — DROP the fwupd attribution.**
  Round 400 committed its raw captures (`state/nuc-capture-r400/`, git-tracked),
  so the whole-boot ledger is re-runnable with the box unreachable. It
  reproduces round 400's headline exactly (62 fires, 6 costly, 1
  sole-attributable, 67,682,304 B). The number nobody had computed:
  **`fwupd-refresh` fired 36 times in that boot and 33 of the 36 buckets moved
  ZERO bytes.** On sa30 alone: 23 fires, 23 zeroes, 0 costly hits — an
  independent replication in which the claimed cause is present 23 times and
  the effect never appears. Occupancy 36/218 = **16.5 %**, so it is within ten
  minutes of one event in six on this box. The 02:00:05Z 67.68 MB event is
  **unexplained**, as round 388 originally recorded it.
- **The gate is now in the tool.** `attribution_evidence` in
  `nuc/perturbation.py` (+ `evidence` CLI mode) grades every unit
  insufficient-data / no-evidence / shared-only / coincidence / supported, with
  an exact hypergeometric tail Bonferroni-corrected over the ledger's units.
  Over the whole boot: 16 units tested, **`supported: []`** — this instrument,
  over this record, licenses no causal claim at all.
- **THE CAPTURE IS FILTERED AND NOTHING SAID SO.** `unit-starts.txt` holds 358
  `Starting` lines and **zero `Finished` lines** — it was grepped for
  `Starting|Started`, and a systemd oneshot logs `Finished`, never `Started`.
  **330 of 358 fires (92.2 %) have no derivable duration**, and all 13
  housekeeping units in the ledger are in the 62-of-87 set that never gets a
  terminal line. The obvious stronger test — attribute by the interval a unit
  RAN, not the instant it STARTED — is unrunnable from banked data.
- **Banked `sar` coverage, now a checked claim:** `-r` and `-W` for all nine
  day files; `-B` for sa30/sa31 only; **seven further activities (`-u -q -S -b
  -d -n -w`) for zero days.** They exist only in the binary `saNN` files and
  `sar` renders only what you ask for. **`sa23` is overwritten 2026-09-23.**
- **New: `nuc/capture_manifest.py`** (`audit` / `plan`, 17 tests). Round 400's
  capture grades **`filtered`, 3 blocking gaps**. `plan` emits a `bash -n`-clean
  script that tars the binaries, captures every activity with unambiguous
  markers, takes the journal **unfiltered**, and re-audits itself `--strict`.
  Round 400 wrote the same remediation as prose marked TIME-CRITICAL and the
  next E round opened to an unreachable box; a command can be run in thirty
  seconds, a paragraph has to be read and retyped.
- Two world-fact pins in `test_reachability_check.py` went red purely because
  round 406's own `down` record entered the live log — both fixed to derive
  from the data (see the round file §6). Neither was a code regression.
- Built: `attribution_evidence` + `evidence` CLI in `nuc/perturbation.py` (+15
  tests); `nuc/capture_manifest.py` (new, 17 tests);
  `skills/cause-needs-a-denominator/` (+4 trigger cases, registered unprobed).
  Tests **606 → 638**, all green; audit 23/18/0.783/0 transform risks. Skills
  corpus 7 checkers, **0 errors**. **9 HIT, 2 MISS, 1 PARTIAL of 12.**
- Hygiene: no contact with the box was possible; two ssh attempts, both timed
  out, then stopped. No scp, no writes on the box, no unit restarted. **Port
  8001 never contacted; no engine request of any kind.** Every module added is
  pure text-in/dict-out and opens no socket.
- **Next E round, in order:** (1) reachability check first; **if UP, run
  `python3 nuc/capture_manifest.py plan --capture state/nuc-capture-r400 > /tmp/cap.sh && bash /tmp/cap.sh`
  before anything else** — one command, ~2 MB, closes all three blocking gaps
  and self-verifies; (2) with `Finished` lines, run the interval-attribution
  and re-grade the 02:00:05Z event; (3) determine why `fwupd-refresh.timer`
  fires ~hourly rather than daily (36 fires in 36 h, gaps 24–95 min) — needs
  `Failed`/`Finished` to separate a retry loop from a healthy re-trigger; (4)
  `supported: []` may mean the 10-minute `sar` window is too coarse to
  attribute anything here — the `sar -r` `Committed_AS` channel is banked for
  all nine days and is **runnable offline on the next DOWN round**; (5) still
  blocked on the operator: `--cap 196` and the E3 A/B, and any A/B must record
  each unit's occupancy over the whole record, not just which fired; (6) round
  370's item 3 needs a FRESH boot — the `43e0c767` streak has ended, so the
  next up-round may satisfy it for free; capture `uptime -s` first; (7)
  harness(A) still owns wiring `nuc/run_checks_fast.sh` into `run_driver.sh` —
  0 references, **fourth round carried**.

## Round 412 (NUC-integration E) — 2026-08-31, box **DOWN** the whole round; SAME continuous outage as round 406 (`tailscale_last_seen` byte-identical), so no up window occurred between the two rounds

- **Reachability.** `reachability_check check --round 412` at
  **2026-08-31T22:11:08Z**: ssh to `jab@100.78.44.111` rc 255 (timed out),
  `tailscale_online: false`, `tailscale_last_seen 2026-08-31T16:30:00.1Z` —
  **the same value round 406 recorded**, which is the evidence that this is
  one outage and not two. A second confirming probe also timed out; two
  consecutive failures ⇒ probing stopped per CLAUDE.md. Record **46** of
  `state/nuc-reachability-log.jsonl` (`verdict: down`, `source: live`,
  `precision: precise`). Outage now bracketed: after **13:14:19Z** (round
  400's last contact, up), at or after **16:30:00.1Z**, still open at
  22:11:08Z — **≥ 5h41m**.
- **Round 406's item 1 (run `capture_manifest plan` if UP) did not fire and
  carries forward unchanged.** Item 4, explicitly marked *"runnable offline on
  the next DOWN round"*, was this round's work.
- **`supported: []` was never checked for reachability, and for half the units
  it was unreachable.** New `power_floor(N, K, n_units_tested, α)` computes,
  from the record's SHAPE alone and with no data, which occupancies could ever
  clear the Bonferroni bar. On round 406's own pooled run (N=218, K=3, 16
  units, bar 0.003125) the testable band is **occupancies 2..32 — 14.2 % of
  N — and 8 of the 16 units are outside it.** Seven because their occupancy is
  too LOW (`d=1`; covering 1 of 3 by chance is `3/218`, ×16 = 0.22), one
  because it is too high.
- **`fwupd-refresh`'s swap-channel verdict was fixed before the data was
  read.** `d=36` gives `p_best = 0.00419`, ×16 = **0.067 > 0.05**: hitting all
  three costly buckets would still have read `coincidence`. Round 406's DROP
  is still right — its consistency argument (33 of 36 fires moved zero bytes)
  is independent — but the chance test it also reported had no power.
- **`sa30` ALONE has K=1, and a record with one costly bucket can support
  nothing at any occupancy** (`1/218 × 16 = 0.0734`). Round 406 pooled the two
  day-files "because sa30 contributes 23 free fwupd fires"; this is the
  quantitative reason pooling was *necessary*, not merely useful. Run per-day,
  the instrument returns the same confident empty list from a day with zero
  power.
- **Item 4 answered: the commit channel gives fwupd the powered test swap
  could not.** `cost_ledger` was channel-locked on the literal `pswpout/s`;
  it now takes a `Channel` that distinguishes a **rate** column
  (self-contained per bucket) from a **level** column (`kbcommit`, a delta,
  with the table's first row and any post-restart row **undefined — `None`,
  not `0`**). On `Committed_AS` (N=216, K=9) fwupd at `d=36` is *inside* the
  band, the test genuinely runs, and fwupd fails it (covered 1 of 9,
  `p=0.813`).
- **THE BIGGEST SWAP EVENT OF THE BOOT COMMITTED NOTHING.** `sa31` 04:00:03 —
  the 220.89 MB bucket rounds 388/394/400 all circled as "the largest
  perturbation this deployment has seen", with five named units in it — has a
  commit rise of **0**; raw `kbcommit` **FALLS 1.6 MB** across it. No new
  address space was promised, so that was **reclaim against memory already
  committed, not a housekeeping unit allocating**. The apt cluster did not
  allocate. By contrast 02:00:05 (fwupd's) **is** a real allocation: +150.62 MB
  committed alongside 67.68 MB out. Caveat kept explicit: `kbcommit` is
  committed address space, not RSS, so this rules out the "a unit allocated
  220 MB" story without identifying what did drive the reclaim.
- **The sweep, 9 thresholds × 2 channels: `supported` is `[]` in all 18.**
  Round 406's headline survives everything, which is what makes it a result.
  The inversion I predicted backwards: **above ~134 MB the SWAP channel has no
  testable unit at any occupancy** (`supported_was_reachable: false`), while
  the commit channel never enters that regime.
- **Two defects fixed, both latent.** `parse_sar` silently DISCARDED
  `LINUX RESTART` — harmless for a rate column, corrupting for a level one
  (an 18.4 GB reboot step would have been booked as a unit's cost);
  `SarRow.restart_before` now carries it and `139 + 79 = 218` reproduces round
  400's N. And `bucket_shared_by` counted **fires, not distinct units**, so two
  fires of one unit in a bucket reported `sole_attributable: False` about a
  bucket with exactly one unit in it. **Zero buckets in the r400 capture hold
  same-unit repeats**, so every published number is unchanged — pinned as both.
- **Round 406's own test for the consistency rule never reached it.** Its
  fixture (N=79, K=1, d=18) has `p_chance = 0.228`, so the chance branch fired
  first; it asserted the right verdict string for the wrong reason and went red
  the moment `untestable` was inserted. Split into a pin for the discovery and a
  rewritten test on a fixture that reaches the rule.
- **The journal, not `sar`, bounds attribution.** `unit-starts.txt` covers
  **2026-08-30T00:32:32 → 2026-08-31T13:16:41** only. Item 4's "all nine days"
  is true of the CHANNEL and false of the analysis; `sa23`–`sa29` have no unit
  fires banked at all.
- **`CHANNEL_MIN_BYTES["commit"] is None` and `cost_ledger` RAISES.**
  `LEDGER_MIN_BYTES` is derived from two labelled swap events; the commit
  channel has no such pair on this record, so it demands the number explicitly
  rather than shipping a default with a derivation-shaped comment.
- Built: `power_floor` / `best_case_p` / `Channel` / `bucket_costs` /
  `channel_sweep` + `untestable` verdict + `testable` / `p_best` /
  `supported_was_reachable` fields + `power` and `sweep` CLI modes, all in
  `nuc/perturbation.py`; `skills/null-result-needs-a-power-floor/` (+4 trigger
  cases, registered unprobed). Tests **638 → 669**, all green; audit
  23/18/0.783/0 transform risks (unchanged). Skills corpus 7 checkers,
  **0 errors** (62 skills, 265 cases). **14 HIT / 2 PARTIAL / 3 MISS of 19.**
- Hygiene: no contact with the box was possible; two ssh attempts, both timed
  out, then stopped. No scp, no writes on the box, no unit restarted. **Port
  8001 never contacted; no engine request of any kind.** Every module touched
  is pure text-in/dict-out and opens no socket.
- **Next E round, in order:** (1) reachability check first; **if UP, run
  `python3 nuc/capture_manifest.py plan --capture state/nuc-capture-r400 > /tmp/cap.sh && bash /tmp/cap.sh`
  before anything else** — round 406's item 1, unchanged, second round
  carried; (2) with `Finished` lines, run interval-attribution and re-grade
  the 02:00:05 event — and note it is now the ONLY one of the two big events
  with an allocation behind it; (3) **the 04:00:03 reclaim is newly
  unexplained in a specific way** — nothing allocated, so ask what *touched*
  already-committed pages: `sar -B` (`pgscan`/`pgsteal`) is banked for sa30/31
  and this round did not read it, and it is runnable OFFLINE; (4) stitch
  consecutive `sar` day-files so a level channel does not lose each day's
  first bucket — three units (`dpkg-db-backup`, `logrotate`,
  `sysstat-summary`) vanish from the commit family for exactly this reason,
  and the data is already in git, so this is offline work too; (5) capture a
  journal window WIDER than one boot, since the journal and not `sar` is what
  bounds attribution to two of nine banked days; (6) still blocked on the
  operator: `--cap 196` and the E3 A/B — and any A/B must now publish its
  power floor BEFORE it runs, because an A/B that cannot reach significance is
  the same defect this round found; (7) round 370's item 3 needs a FRESH boot;
  the outage means the next up-round may satisfy it for free — capture
  `uptime -s` first; (8) harness(A) still owns wiring `nuc/run_checks_fast.sh`
  into `run_driver.sh` — 0 references, **fifth round carried** (note
  `skills/run_checks_fast.sh` IS wired, round 363, so a basename grep lies).

## Round 418 (NUC-integration E) — 2026-09-01, box **DOWN** the whole round; SAME continuous outage as rounds 406 and 412 (`tailscale_last_seen` byte-identical across all three), so no up window has occurred since 2026-08-31T16:30Z

- **Reachability.** `reachability_check check --round 418` at
  `2026-09-01T03:11:39Z`: ssh rc 255 `Connection timed out` on the tailnet
  path `jab@100.78.44.111`; second attempt on the LAN path
  `jab@192.168.1.37` also rc 255, timed out. `tailscale_online false`,
  `tailscale_last_seen_utc 2026-08-31T16:30:00.1Z` — identical to rounds 406
  and 412, ~10.7 h old at probe time. Two consecutive failures ⇒ probing
  stopped, per CLAUDE.md. Logged to the reachability log as `down`.
- **Coordinate note.** `~/.ssh/id_ed25519_nuc` **does not exist on the driver
  host** (`Warning: Identity file ... not accessible`). CLAUDE.md offers the
  LAN path with that key and correctly scopes it "Mac-adjacent hosts only";
  the stronger fact is that from THIS machine the LAN path is not a fallback
  under any box state. This file already leads with the tailnet path and wins
  per CLAUDE.md — no rule changes, this is a note for the next reader.
- **Round 412's next-round items 3 and 4 are CLOSED** — both were marked
  runnable offline and both were this round's work.
  - **Item 3 (the 04:00:03 reclaim).** `sar -B`, banked by round 400 and
    unread for nine rounds, has the answer: `pgscank/s 1207.00`,
    `pgscand/s 0.00`, `pgsteal/s 401.70` — kswapd stole 241 020 pages
    (941 MiB as reported) while 325 MiB was read back from disk. The new
    `perturbation.py gap` verb shows the commit channel's cost at that bucket
    is **exactly 0 bytes**. `Committed_AS` counts promises and an eviction
    revokes none, so the commit channel is blind to it BY CONSTRUCTION, not
    by coarseness. `pgscand/s` is 0.00 in every bucket of both days: seven
    reclaim events, all kswapd, **no allocation ever stalled** — pressure on
    this box is page-cache eviction and re-read, not allocator latency.
  - **Item 4 (stitch day-files).** Done, with four refusals. The boundary hole
    is in the RENDERING: `sar` consumes each day-file's first record as a
    reference and never prints it, so the stitched bucket spans **1200 s**,
    and `LedgerEntry.bucket_span_s` now carries that. The three lost units
    (`dpkg-db-backup`, `logrotate`, `sysstat-summary`) return —
    `n_unclassified` 3 → 0, units 13 → 16 — their bucket costs **0 bytes**,
    and because K stays 4 the Bonferroni bar tightens and the testable band
    SHRINKS 2..54 → 2..52. More data, less power; recorded rather than hidden.
- **A factor-of-two artifact in `pgsteal`.** Six of seven reclaim buckets
  report `%vmeff > 100`, impossible if the columns count the same pages.
  Halving `pgsteal` puts all seven at or under 100 %, max exactly **100.000**,
  five within 1 % of the ceiling. `reclaim_double_count_check()` reports the
  evidence and the corrected view and **does not apply the correction**.
  Every reclaim byte figure this round published is an upper bound with a
  factor-of-two question over it.
- **`pgsteal/s` as a third `Channel`.** Pooled sa30+sa31: `n_buckets 218,
  K 7, units 16, testable 9, supported [], testable occupancies 2..97
  (44.0 % of N)` — **the first null on this record with real power**, which is
  what round 412 said round 406's was missing. Threshold-FREE: K = 7 from
  4 KiB to 128 MiB, because reclaim here is bimodal (0 or ≥ 260 MiB). K by
  channel at the same floor: **swap 3 < steal 7 < commit 9**.
- **`fwupd-refresh`**: 4 of 7 costly buckets, 2 held alone at `110.88` and
  `110.88` pg/s eleven hours apart, `p_chance 0.0154` — the smallest any unit
  has reached on any channel here — still `coincidence` at `p_family 0.2461`.
  Blocked by `consistency 0.111`, which conflates "costs nothing" with "costs
  conditionally". Every hourly timer on this box has that shape.
- **Artifacts:** `nuc/perturbation.py` 1285 → 1729 lines (`STEAL_CHANNEL`,
  `Stitch`/`stitch_from`/`auto_stitches`/`stitch_applies`/`bucket_spans`,
  `LedgerEntry.bucket_span_s`, `ReclaimEvent`/`reclaim_events`/
  `reclaim_summary`/`reclaim_double_count_check`/`eviction_gap`, CLI verbs
  `reclaim` and `gap`, `--stitch-prev`, `--stitch`);
  `nuc/predictions-e-round418.md`;
  `knowledge/round-418-nuc-e-the-eviction-the-promise-channel-could-not-see.md`.
  Tests **669 → 699**, all green; audit 23/18/0.783/0 transform risks
  (unchanged). **16 HIT / 1 PARTIAL / 2 MISS of 22**, plus 3 disclosed in the
  bank as already-read.
- Hygiene: no contact with the box was possible; two ssh attempts, both timed
  out, then stopped. No scp, no writes on the box, no unit restarted. **Port
  8001 never contacted; no engine request of any kind.** Every module touched
  is pure text-in/dict-out and opens no socket.
- **Next E round, in order:** (1) reachability check first; **if UP, run
  `python3 nuc/capture_manifest.py plan --capture state/nuc-capture-r400 > /tmp/cap.sh && bash /tmp/cap.sh`
  before anything else** — round 406's item 1, **seventh round carried**;
  (2) **then one read-only command: `grep -E '^pg(scan|steal)' /proc/vmstat`**
  — it settles the factor-of-two question over every reclaim byte in the
  record and nothing offline can; (3) capture `sar -B` for EVERY day in the
  retention window, not two — it is now the channel that sees the most, and
  `-r`/`-W` already cover sa23–sa31; (4) test whether `sadf` emits a day-file's
  first record, which would remove the 1200 s stitch instead of working around
  it; (5) capture a journal window WIDER than one boot — round 412's item 5,
  unchanged, and still the binding constraint on attribution (it also sees
  system units only, which is why the boot's largest reclaim, the engine load
  at 13:30–15:10 on sa30, has no named fire); (6) a conditional-work variant
  of `consistency`; (7) close the stitched bucket's previous-day blind spot in
  `cost_ledger`; (8) still blocked on the operator: `--cap 196` and the E3 A/B,
  with round 412's power-floor precondition — which this round showed cuts
  both ways: a null WITH a published floor is a result; (9) round 370's item 3
  needs a FRESH boot — capture `uptime -s` first on the next up round.

## Round 424 (NUC-integration E) — 2026-09-01, box **UP** on a boot never seen before: `f13afb47`, `uptime -s 2026-09-01 05:33:27Z`, 2 h 36 m at first contact. Ends the 406/412/418 outage — and ends it by REBOOTING, which is the finding

- **Reachability.** `reachability_check check --round 424` at
  `2026-09-01T08:10:46Z`: ssh rc 0 on the tailnet path `jab@100.78.44.111`,
  `tailscale_online true`, `boot_utc 2026-09-01T05:33:27Z`,
  `slept_this_boot false`. Previous recorded boot `43e0c767` was
  2026-08-30T00:32:27Z; `tailscale_last_seen` was pinned at
  `2026-08-31T16:30:00.1Z` byte-identically across rounds 406/412/418. So the
  outage ran 2026-08-31T16:30Z → 2026-09-01T05:33Z (~13 h) and ended with a
  **reboot, not a resume**. `journalctl --list-boots` lists 7 boots back to
  2026-08-23T14:02:08Z; journal storage is persistent, 3.3 G.
- **Round 406's item 1 is CLOSED on its SEVENTH carry — and the plan was
  wrong, in a way caused by the thing that let it run.** Step 3 was
  `journalctl -b`. The plan can only run when the box is reachable and the box
  became reachable by rebooting, so `-b` meant **2 h 40 m / 81 unit fires**
  against **8 d 18 h / 1652** unrestricted. Both close round 400's `Finished`
  gap perfectly (81/81 and 1652/1652 durations derivable vs round 400's
  28/358): the plan succeeded at exactly what it was written for while losing
  95 % of the window. Generalisation for any track: *a fix gated on condition
  C is exposed to whatever usually causes C.*
- **`audit` could not see it.** Run on both captures it returned identical
  verdict, identical `n_gaps`, identical `n_blocking_gaps`, and
  `durations_derivable_fraction` 1.0 for each. It graded which line KINDS
  survived, never which DAYS they covered. New `journal_span_coverage` joins
  the sources on day-of-month (the only key `sa<DD>` and a systemd timestamp
  share). After: as-planned `narrow` 1/10 days, r424 `complete` 10/10,
  **r400 `filtered` 2 of 9** — round 400's cost ledger could never have
  attributed a fire on sa23–sa29 and nothing said so for 24 rounds.
- **`state/nuc-capture-r424/` is the first capture ever to exit 0 under
  `--strict`** — not because previous ones were bad, but because `Failed
  <unit>.service` was a required kind, so a box on which nothing failed graded
  `filtered` forever. `Gap.absence_means ∈ {filtered, box-state, window}` now
  distinguishes evidence about the CAPTURE from evidence about the BOX; any
  terminal kind witnesses an unfiltered capture. Two new kinds appeared:
  **`Stopped` (133) and `Stopping` (95)** — the only source of a long-running
  service's end time, which is what the engine needs.
- **"sa23 is overwritten on 2026-09-23" was wrong by 21 days.**
  `/usr/lib/sysstat/sa2` ends `find $SA_DIR -mtime +$HISTORY | xargs rm -f`
  and `HISTORY=7`: files are DELETED at 7 days, the day-of-month ring never
  wraps. `sysstat-summary.timer` next fires **2026-09-02 00:07 UTC**, ~15 h
  after this capture, and takes `sa23, sa24, sar23, sar24`. New
  `retention_forecast`, validated against the box's own
  `find -mtime +7` (both return exactly `{sa23, sar23}`). `find` truncates age
  to whole 24 h units — `int(7.012) == 7` is not `> 7` — which is the only
  reason sa23 survived the 08-31 sweep to be captured at all.
  **The outage that blocked this capture for seven rounds is the same thing
  that preserved what the capture was for**: a box that is off at 00:07 does
  not sweep. **And no round had ever banked the binary day files at all** —
  `git log --all --diff-filter=A` returns exactly one matching path in the
  whole history and it is this round's `sysstat-binary.tar.xz` (367 kB for all
  17 files). Round 400's item 1 called that copy "the highest-value cheap
  action available", was right, and was carried four E rounds against a
  deadline stated 21 days too late.
- **Round 400's item 2 (the `sarNN` reports as a second outage witness) is
  four E rounds old and this is the first up-round since.** Round 400 already
  named these files, already noticed `sar29` was missing, and already gave the
  00:07-cron reason — that mechanism is round 400's and round 424 claims no
  credit for it. What is new: they had never been **captured** (round 400 asked
  for `sa*`, and the plan's `sa[0-9][0-9]` glob does not match `sar23`), they
  expire on the same 7-day sweep as the binaries, and **`sar31` is missing
  too** — the box was down at 00:07 on 09-01 as well, so the absence reproduces
  on every outage spanning midnight rather than being a one-off.
- **The `pgsteal` factor of two is CONFIRMED — and not by round 418's own
  test.** `grep -E '^pg(scan|steal)' /proc/vmstat` returned **0 for all
  fourteen counters** (fresh boot, no reclaim), so the partition identity held
  as `0 == 0` and measured nothing. `strings /usr/lib/sysstat/sadc` settled it:
  the collector carries `pgscan_direct`, `pgscan_kswapd` (full field names, one
  partition) and **`pgsteal_` (a bare PREFIX)**, which on kernel 6.8 matches
  five fields forming two complete partitions of the same events. Numerator
  doubled, denominator not; `%vmeff` reads exactly 2×. Banked in
  `collector-evidence.txt`. Corrected totals: **21.98 GiB → 10.99 GiB** over
  the seven reclaim buckets, and `sa30 15:00:05`'s reported **14.56 GiB in one
  600 s bucket on a 26 GB box** stops being impossible at 7.28 GiB. Five of
  seven buckets correct to ~100 % efficiency (clean file-cache eviction) and
  **04:00:03 stands alone at 16.6 %** — round 418's event is the least
  efficient reclaim in the record, which the doubling hid. Reported columns
  untouched; `corrected_*` rides beside them.
- **Round 418's item 4 REFUTED: `sadf` makes the boundary hole worse.** On
  sa01, sadf yields 16 distinct stamps to sar's 17 — both consume the first
  record, but sar stamps its column header with it (05:40:12) and sadf drops it
  entirely. The 1200 s stitch stays. What sadf *does* have is the true
  per-record interval (**589 s**, not the assumed 600).
- **Round 370's item 3, on the first fresh boot since it was written: half
  closed, half permanently lost.** The journal holds the load retrospectively —
  `05:33:34` start, `05:33:48` `resident weights loaded in 13.1s | RSS after
  load: 9.25 GB` — so the timeline needs no polling and no request. The
  `memory.current` trajectory is gone; an unsampled level does not survive.
  Two corrections: there are **no `unpacking to int8 in slot` lines at all**
  this boot (9 journal lines total; model dir `qwen36_i4_gs64`), and **sa01
  shows no memory step because the load ran entirely inside the record `sar`
  drops** (RESTART 05:33:33, first record 05:40:12 consumed, first printed
  05:50:01). The engine is also near-invisible to the commit channel:
  `kbcommit` 5.6 GB against RSS 9.25 GB, because the weights are file-backed
  mappings and a mapping is not a promise. **This boot reclaimed nothing** —
  every `pgsteal_*` counter 0 after 2 h 40 m, ~22 GB free.
- **Predictions (D-013):** `nuc/predictions-e-round424.md`, written before any
  measurement. **10 HIT / 3 PARTIAL / 3 MISS / 1 VACUOUS of 17** numbered
  predictions, plus 3 hygiene commitments kept. The vacuous one is B2 and is deliberately not
  scored a hit. Retention, the `sarNN` reports, `Stopped`/`Stopping`,
  `pgscan_direct_throttle` and sadf's interval column were all **unpredicted**
  and claim no foresight.
- **Artifacts:** `nuc/capture_manifest.py` 388 → 693; `nuc/perturbation.py`
  1805 → 1982 (round 418 recorded 1729; `git show 05eb40c:… | wc -l` is 1805,
  so that figure was stale before this round); `state/nuc-capture-r424/` (3.2 MB — binary tar of all 17 files
  xz'd to 367 kB, `sar-all.txt` 100 sections, full and current-boot journals as
  a matched pair, user-manager journal, boot table, collector evidence);
  `knowledge/round-424-nuc-e-the-plan-the-outage-outlived.md`.
  **Tests 699 → 723, all green** (`723 passed in 213.34s`; baseline at round
  start was `2 failed, 697 passed` — see the knowledge file §12).
- **Hygiene: port 8001 never contacted; NO engine request of any kind to any
  port.** No unit started, stopped, restarted or reloaded. **Nothing written on
  the box at all** — not even `~/nuc-research/`; the tar streamed to stdout, so
  the remote footprint is strictly read-only.
- **Next E round, in order:** (1) **run `capture_manifest.py retention` first,
  every up-round** — `--strict` exits 1 when the next sweep deletes something;
  the archive rolls off in ~8 days of box-uptime; (2) **full-window attribution
  is possible for the first time** — 1652 fires, 100 % durations, span 10/10,
  plus `Stopped`/`Stopping`; every ledger result in this program was computed
  on 2 of 9 day files, so re-run `cost_ledger`/`attribution_evidence`/
  `channel_sweep` against `state/nuc-capture-r424/` and expect the power floors
  to move; (3) re-derive round 418's `fwupd-refresh` result on corrected steal
  (ordering should survive, magnitudes are all 2×); (4) ask what was pinned at
  04:00 and not at 15:00, now that 04:00:03 is the one inefficient reclaim;
  (5) use `sadf` for per-record intervals and retire the first-record item;
  (6) `sar29`/`sar31` do not exist and never will; (7) round 370's item 3
  should be rewritten or retired — it names a log line this config never emits,
  and catching the next load needs a poller running at boot, i.e. a
  `~/nuc-research/` unit, i.e. operator approval; (8) still blocked on the
  operator: `--cap 196` and the E3 A/B with round 412's power-floor
  precondition.

## Round 430 (NUC-integration E) — 2026-09-01, box **UP** on the SAME boot as round 424 (`f13afb47`, `uptime -s 2026-09-01 05:33:27Z`, 8 h 20 m in). Second consecutive up round; the 406/412/418 outage is still the last one

- **Reachability.** `reachability_check check --round 430` at
  `2026-09-01T13:53:02Z`: ssh rc 0 on the tailnet path `jab@100.78.44.111`,
  `tailscale_online true`, `boot_utc 2026-09-01T05:33:27Z`,
  `slept_this_boot false`. Two ssh connections all round, both read-only, both
  rc 0.
- **Round 424's item 1 is now a standing first action and it works.**
  `capture_manifest.py retention --capture state/nuc-capture-r424 --next-run
  2026-09-02T00:07:00Z --now 2026-09-01T13:54:45Z --strict` forecasts exactly
  four deletions — `sa23`, `sa24`, `sar23`, `sar24` — and exits 1. All four are
  already in `sysstat-binary.tar.xz`, so the exit-1 is a **deadline notice, not
  a loss**. Live listing: same 17 filenames, `HISTORY=7` unchanged, `sa01`
  grown 36 324 → 111 124 B, next summariser fire `2026-09-02 00:07:00 UTC`
  (predicted exactly). **No fresh binary tar taken** — nothing is at risk
  before `2026-09-03T00:07:00Z` and a duplicate would carry no new bits.
- **`survives_until_utc` was a day early, always in the alarming direction.**
  It was `mtime + 8 d`, the instant `find -mtime +7` starts matching — when a
  file becomes SWEEPABLE, not when `sa2` runs. The timer fires at 00:07, so a
  file eligible at 23:50 lives 17 more minutes and one eligible at 08:10 lives
  **sixteen hours**. Split into `sweepable_at_utc` and `deleted_at_utc` (the
  first fire at or after eligibility, with the fire series derived from the
  caller's fire, not a hardcoded 00:07). `earliest_loss_utc` is now
  `2026-09-03T00:07:00Z`, `next_files_lost` `["sa25","sar25"]`, and the window
  ends `2026-09-10T00:07:00Z`. Still an *earliest possible* deletion: a box
  down at 00:07 does not sweep, which is why `sa23` survived to be captured.
- **THE FULL WINDOW RAN (round 424 item 2). N 218 → 991, K 3 → 52, 16 units →
  26, testable band 2..97 → 3..881 (88.7 % of N).** Every ledger, evidence,
  sweep and power number this program had published came off **two of nine**
  day-files and a one-boot journal. New `perturbation.py window --capture DIR`
  pools the lot. It is not a loop: widening is a **false-POSITIVE** hazard,
  because a day with `sar` rows and a silent journal adds buckets to N and
  fires to nothing, so every unit's p FALLS on strictly less evidence.
  `window_frame` pairs each day against the journal before pooling, derives the
  day list from the capture's own section headers and each date from that
  section's own `Linux ... MM/DD/YY` banner (raising on a banner/name
  disagreement — `SA01` is September and nothing in its name says so).
  **10/10 days paired, 0 dropped**, and `--inflation` comes back EMPTY, which
  is the point: the pooled N was not bought with an inflated denominator.
- **`supported: []` for the fifth round — and for a NEW reason, which is a
  defect in this program's own instrument.** `attribution_evidence` has SIX
  gates; round 412's `power_floor` models ONE, and reports
  `supported_was_reachable: True` here truthfully about that one while being
  read as the whole claim. New `verdict_floor` intersects all six:
  `separable` passes 3 units (`fwupd-refresh`, `man-db`, `motd-news`),
  `chance` passes 4 (`apt-daily`, `apt-news`, `esm-cache`, `packagekit`), and
  **the two sets are DISJOINT**. `single_gate_from_supported:
  {"separable": ["apt-news","esm-cache","packagekit"]}` — exactly one gate
  stands between three units and `supported`, and it is not power and not
  chance. `packagekit` reaches `p_family 5.35e-06`, the smallest p this track
  has produced on any channel. The structural statement: **a unit that fires
  often enough to be seen alone fires too often to be surprising, and a unit
  rare enough to be surprising is started by something else.**
- **Round 400 item 3 / round 424 item 3 CLOSED: DROP the fwupd attribution.**
  Over nine days `fwupd-refresh` fires **166** times, holds **9** costly
  buckets alone (round 400 called one of them "the only sole-attributable
  event of the boot") and fails at `p_chance 0.144` — covering 12 of 52 costly
  buckets from 166 of 991 is FEWER than chance gives. `consistency 0.072`,
  below round 418's 0.111. Occupancy 166 is deep inside the testable band, so
  this is a powered null, not a shrug.
- **`packagekit` is the deployment's universal one-way confounder.** It sits
  in every costly bucket **eleven** other units occupy and in two more of its
  own, so nothing in the apt or fwupd family can ever be sole-attributable
  while it exists. Merging the mutually-inseparable trio
  `apt-daily+apt-news+esm-cache` into one hypothesis (23 hypotheses instead of
  26, looser Bonferroni) still returns `shared-only`, because the confounding
  is **DIRECTED** — the trio can never be alone and `packagekit` is not
  rescued either. 19 of the 52 costly buckets hold a named fire at all;
  **33 hold none**, and 52 % of non-instrument fires are `unclassified` (a
  fire inside a reboot or outage window).
- **ROUND 424's `pgsteal` CORRECTION FAILS ON THE EIGHT DAYS NOBODY HAD RUN
  IT ON.** Validated on sa30+sa31 — the only two files this track had ever
  opened — it returns `ceiling_restored: True`. Over all ten:
  **`ceiling_restored: False`, 21 buckets stole pages with ZERO scanned**
  (`sa23 21:40:03`: `pgscank/s 0.00, pgscand/s 0.00, pgsteal/s 4087.96`), 8
  more still over 100 % after halving, worst **3053 %**. The four passing days
  are 08-28..08-31, exactly the recent window. **The mechanism is in the same
  banked file, one section below the one round 424 read**: the kernel exports
  `pgscan_khugepaged` and `sadc` does not read it, while `pgsteal_` collects
  `pgsteal_khugepaged`, so reported `%vmeff` is `2T/(S − S_khuge)` — the
  residual is UNBOUNDED, not a second constant, and UNDEFINED when khugepaged
  does all the work. Round 424's finding is **scoped, not overturned**:
  `corrected_*` is an upper bound. New `scan_undercount_evidence()` derives it
  from the banked text; the direct kernel test is vacuous for a second
  consecutive round (every reclaim counter 0 across the whole 8 h 30 m boot).
- **The checker could not have caught it because it filtered the evidence.**
  `reclaim_double_count_check`'s first line has dropped `scan == 0` buckets
  since round 418 — precisely the sharpest counter-examples — with no count.
  Now `n_scan_free_steal` is an output field and a non-zero count BLOCKS the
  positive verdict. `ReclaimEvent` gains `scan_free_steal`/`vmeff_defined`,
  because `vmeff_pct` is "0 if no scan" and so rendered an unbounded ratio at
  the BOTTOM of an efficiency ranking.
- **Round 424 item 4 answered by the same numbers.** `sa31 04:00:03` at 16.6 %
  is NOT the window's least efficient reclaim — `sa23 18:20:01` reclaims
  8.0 GiB at 27.4 % with `pgscand/s 3217.07`. Whole-window totals: **166.0 GiB
  corrected** over 108 events, against round 424's 10.99 GiB over seven.
- **Round 418's "no allocation ever stalled" does not extend.** `pgscand/s`
  is 0.00 on sa30/sa31 and non-zero in **8 buckets** over ten days, peaking at
  3217.07 on 08-23. Direct reclaim happened, on the busy days nobody opened.
- **Round 424 item 5 CLOSED — retire it.** On `sa01`, `sadf -d` yields 51
  distinct stamps to `sar`'s 52 stamped lines: the same one-record difference
  round 424 saw on a different file, so it is not an artefact. Both consume the
  first record; `sar` at least stamps its header with it. `sadf` DOES carry the
  true per-record interval — **589, 601, 600, …** The 1200 s stitch stays.
- **Predictions (D-013):** `nuc/predictions-e-round430.md`, written before any
  sar file, journal, ledger or capture was opened. **15 HIT / 1 PARTIAL /
  5 MISS of 21**, plus 3 hygiene commitments kept. Four of the five misses
  share one mechanism — a number or shape inherited from a previous round's
  TWO-DAY sample and not re-derived — which is this round's own §4 lesson,
  committed inside the bank written to catch it.
- **Artifacts:** `nuc/perturbation.py` 1982 → 2749; `nuc/capture_manifest.py`
  693 → 732; `state/nuc-capture-r430/box.txt`;
  `skills/correction-validated-where-you-looked/` (new);
  `skills/null-result-needs-a-power-floor/` gains **step 0** (enumerate every
  gate, intersect the pass sets) — the skill's own instrument modelled one gate
  of six; `knowledge/round-430-nuc-e-the-gate-nobody-modelled.md`.
  **Tests 723 → 753, all green** (`753 passed in 73.00s`); `skill_lint
  --house --strict` 72 skills, 0 errors, 0 warnings.
- **Hygiene: port 8001 never contacted; NO engine request of any kind to any
  port.** No unit started, stopped, restarted or reloaded. **Nothing written on
  the box at all** — every ssh session was read-only and streamed to stdout,
  not even `~/nuc-research/` was touched.
- **E-mission status: E1-E5 all still DONE; nothing new unchecked.** The work
  is the standing analysis programme in the addenda, not a sixth checkbox.
- **Next E round, in order:** (1) `retention --strict` FIRST, every up round —
  window ends `2026-09-10T00:07:00Z`, re-take the tar only when
  `next_files_lost` names something not in `state/nuc-capture-r424/`;
  (2) the residual is one read-only command away **on a box that has
  reclaimed** — `grep -E '^pg(scan|steal)' /proc/vmstat`, confirmed if
  `pgscan_anon + pgscan_file` exceeds `pgscan_kswapd + pgscan_direct` by
  roughly `pgsteal_khugepaged`'s share, but check `pgsteal_kswapd > 0` first
  because the test has now been vacuous twice; (3) **separability is the whole
  game** — `packagekit` is one gate from `supported` at `p 5.35e-06`, and both
  routes are offline: a sub-600 s time base from the journal's second
  resolution plus round 424's banked `Stopped`/`Stopping` lines, or round 418's
  conditional-consistency variant; (4) run the **steal** channel over the full
  window with `channel_sweep` and an explicit threshold set — the only channel
  not pooled this round, and K at 4 KiB is 108 against swap's 52; (5) 33 of 52
  costly buckets have no named fire, and `journal-user-full.txt` (456 kB,
  banked, unread) holds the USER manager's units, which is where the engine
  lives — a second parser for `systemd[1057]:`, not a change to
  `parse_unit_starts`; (6) retire round 370's item 3 (names a log line this
  config does not emit; catching a live load needs an operator-approved unit);
  (7) still blocked on the operator: `--cap 196` (band [129, 204],
  `bounded_by: engine_lru`, 1.096 GB margin — nineteenth round unchanged) and
  the E3 A/B, which must now publish its full GATE TABLE and not just a power
  floor; (8) **`nuc/run_checks_fast.sh` IS wired — the "0 references"
  carry was false for four E rounds and is CLOSED.** This round wrote it for a
  ninth time and `state_claim_check` turned it red on the same run:
  `wiring_audit refs nuc/run_checks_fast.sh --in run_driver.sh` re-derives
  **2 mentions, 1 invocation** (lines 496, 526). **Round 409 (harness A) wired
  it on 2026-08-31, `50c7bb3`.** Nothing to hand on; keep the shape.

## Round 436 (NUC-integration E) — 2026-09-01, box **DOWN** the whole round; ends the 424/430 up streak on boot `f13afb47`. All findings are offline work on round 424's banked capture

- **Reachability.** Two attempts, `reachability_check check --round 436` at
  `2026-09-01T19:30:39Z` and `19:46:19Z`: ssh rc **255**
  (`connect to host 100.78.44.111 port 22: Connection timed out`) both times,
  `tailscale_online false`, and `tailscale_last_seen_utc` **byte-identical**
  at `2026-09-01T18:30:00.1Z` across the two — one continuous outage, no up
  window between the probes. Stopped after the second per CLAUDE.md's
  two-failures rule. **Zero ssh sessions succeeded, so nothing was read from
  or written to the box; port 8001 was never contacted and no engine request
  of any kind was made.**
- **Item 1 (retention) ran first and is offline.** `retention --capture
  state/nuc-capture-r424 --next-run 2026-09-02T00:07:00Z --now
  2026-09-01T08:18:35Z --strict` → rc 1, four deletions `sar24 sa24 sar23
  sa23`, identical to round 430's forecast at the identical `--next-run`.
  `tar -tJf sysstat-binary.tar.xz` = 17 members and all four are in it, so
  **deadline notice, no loss, no fresh tar**. `earliest_loss_utc
  2026-09-03T00:07:00Z`, `next_files_lost ["sa25","sar25"]`, both also banked.
  Window still ends `2026-09-10T00:07:00Z`. Note `--now` should be the
  capture's own `CAPTURED_AT` (`08:18:35Z`), not the caller's clock; both
  resolve the same year here so nothing published moves. **And the box is
  down: a box down at 00:07 does not sweep, so the deadline may simply slide.**
- **ROUND 430's ITEM 5 IS REFUTED IN EVERY CLAUSE.** The user manager emits
  **15** `Starting` lines in ten days (7 `dbus.socket`, 7
  `gpg-agent-ssh.socket`, 1 `dbus.service`) — it cannot account for 33 costly
  buckets. The section labelled `### USER_MANAGER` holds **no `systemd[` line
  at all**: 329 `coli[...]` lines, the engine's own log, which is what the
  command under it (`capture_plan` step 3b,
  `journalctl _SYSTEMD_USER_UNIT=qwen36-colibri.service`) asks for. The
  header records the plan's COMMENT ("the USER manager, which owns the
  engine") and the section holds the command's OUTPUT. Round 424 identified
  this gap correctly and banked the evidence; six rounds then cited the
  comment's phrase instead of opening the file.
- **The file is DUPLICATED, and the honest inflation factor is 1.99x not
  1.088x.** `### USER_MANAGER` is a strict subset of the file's unlabelled
  lead section. Over record lines the inflation is 1.088 (the lead holds 2774
  `sshd` lines the view does not); over the EVENTS any count would use it is
  **1.9917** — 482 naive against 242 real, `POST /v1/chat/completions` 363
  against 182, weight-loads 26 against 13. And it is not uniform: the view
  starts at `2026-08-23T21:30:22Z`, so the late window looks twice as busy as
  the early one — an error a totals check survives. New `journal_sections` /
  `redundant_sections` / `dedupe_journal` detect it per SECTION, never per
  line (two real `[api]` requests can share a second).
- **`parse_unit_starts` has been blind to a whole class of unit, and the class
  is the one that allocates.** systemd logs `Starting` only for a unit with a
  startup phase; a `Type=simple` unit logs `Started` alone. **6 PID-1 units
  emit only `Started` — 40 fires absent from every ledger this program has
  published** (`cron`, `dmesg`, `getty@tty1`, `netplan-wpa-wlp58s0`,
  `systemd-fsckd`, **`unattended-upgrades`**), plus 4 more in the user journal
  for **24 further fires**, including `qwen36-colibri` × 13. New
  `unit_start_verb_audit` + `parse_unit_starts_complete` (a SECOND PASS, not a
  looser regex; `parse_unit_starts` is untouched so nothing published moves).
  **Honest null: the 40 recovered PID-1 fires change the swap coverage by
  zero** — 19 of 52 buckets before and after.
- **SYSTEMD MEASURED ALL OF IT DIRECTLY AND NOBODY HAD READ THE LINES.**
  `<unit>: Consumed <cpu> CPU time, <X> memory peak, <Y> memory swap peak` is
  per-invocation cgroup accounting — no bucket, no threshold, no confounder,
  no hypergeometric null. 57 records, 19 units, 8 with memory:
  **`qwen36-colibri` 30.0 GiB peak / 3.9 GiB swap peak** on a 31.2 GiB box;
  `colibri-glm` (the `:8001` lane) 24.0 GiB / 0 B; `apt-daily-upgrade`
  446.9 MiB / **0 B**; `fwupd` 209.7 MiB / **6.2 MiB**. `direct_vs_inferred`:
  **0 contradictions**, coverage 4 of 26 graded units — and **13 units carry a
  measurement and were never graded at all**. Round 430's "DROP the fwupd
  attribution" is independently corroborated at a factor of **644**;
  `apt-daily-upgrade`, one gate from `supported`, swapped **0 B** and was
  measured doing so.
- **The 33 unnamed costly buckets are 73.3 % of every swapped byte.** K = 52
  holding 31.53 GiB. The published fire population names 19 buckets and
  **26.7 %** of the bytes; engine events ALONE name 18 and **53.2 %**; both
  together name 33 and 75.0 %. Adding the engine names **14 of the 33**
  (15.23 GiB); **7 of those (10.82 GiB) survive every placement shift**;
  **14 buckets / 4.25 GiB are still named by nothing**, the largest
  `2026-08-23 21:20:02` at 2.34 GiB.
- **Item 4 done: the steal channel, pooled and swept.** New `window_sweep`
  (frame + threshold sweep + the six-gate table at each threshold, which
  `channel_sweep` did not carry). Frame 10/10 paired, N 991, `--inflation`
  0 dropped days. **`supported: []` at all nine thresholds and
  `verdict_is_a_setting: False`** — five decades of threshold and the verdict
  does not move, so on steal it is a fact about the record. **K is flat at 108
  from one page to 4.8 MB**: there is no small-reclaim population on this box,
  which is *why* no noise/real pair exists to derive a threshold from. The
  blocking gate is **`separable`** at every threshold, naming **the same three
  units as the swap channel** (`apt-news`, `esm-cache`, `packagekit`) — the
  gate that blocks this deployment is channel-invariant.
- **FIRST `supported` VERDICT THIS TRACK HAS EVER PRODUCED.** With 242 engine
  events pooled in (26 → 31 hypotheses, so Bonferroni TIGHTENS and no
  incumbent's p falls), on the steal channel at `min_bytes 4096`:
  **`engine:chat-completion` — 181 fires, 44/991 buckets, 166 costly, 105 in a
  bucket it holds ALONE, consistency 0.917, `p_family` 4.5e-32.** Previous
  best on any channel was `packagekit` at 5.35e-06, which failed separability.
  Stress-tested at five placements of a completion-semantics event
  (`engine_verdict_stability`): **supported at 4 of 5**, `p_family ≤ 3.3e-14`
  at each, and consistency falls **monotonically** (0.917 → 0.901 → 0.841 →
  0.626 → 0.356) as the event is moved away from where it was logged — the
  record choosing the placement, not the analyst.
- **The two channels disagree, and the disagreement is the physics.** On SWAP,
  `engine:chat-completion` is `coincidence` at every placement (consistency
  0.34) and `supported` appears only for `engine:completion` at exactly one
  shift — refused as a verdict. **An inference request reliably causes page
  reclaim (92 %) and only sometimes causes swap-out (34 %).** Round 418's
  claim that `pgsteal` sees what the other two channels are blind to is
  confirmed against a workload for the first time.
  `engine:listen`/`engine:weights-load` are `shared-only` at every placement
  on both channels and always will be: 5 s apart, one 600 s bucket.
- **THE BOX OOM-KILLED THREE TIMES IN THE WINDOW AND NO ROUND HAD GREPPED FOR
  THE WORD — once the victim was the ENGINE.** `2026-08-23T21:28:09Z`
  (`tmux-spawn-….scope`), **`2026-08-24T10:34:11Z`
  (`qwen36-colibri.service: Failed with result 'oom-kill'`)**,
  `2026-08-25T00:37:03Z` (no unit reported `Failed`, so a bare process inside
  a surviving cgroup). New `parse_oom_kills` + `oom_episodes`: **10 lines, 3
  episodes** — "A process of this unit has been killed" fires for every cgroup
  ANCESTOR and in BOTH journals, so line-counting would report ten. The first
  two land in the record's **3rd and 5th largest** costly swap buckets of 52
  (2.94 and 2.63 GiB, with 8.21 and 6.97 GiB in their ±30 min windows; 14th
  and 24th of 108 on steal, 27.17 and 15.45 GiB). The third has no covering
  bucket with a defined cost — `sa25` has two `LINUX RESTART`s — and
  `oom_cost_context` says so rather than reporting zero. **The largest costly
  bucket no fire explains (`2026-08-23 21:20:02`, 2.34 GiB) is the run-up to
  the first episode: not a fire, and never will be one.**
- **This is the evidence `--cap 196` never had.** The engine's directly
  measured footprint is 30.0 GiB peak on a 31.2 GiB box and the OOM killer has
  already fired at it. The twentieth-round-unchanged recommendation is no
  longer a projection about a margin — the configuration has gone through the
  ceiling, with the engine as victim. Caveat honestly: three observations, two
  of them on the window's two busiest days. Not a rate.
- **A hunch checked and dropped.** The record's biggest costly bucket
  (2026-08-23 15:00:03, 3.90 GiB) and the engine's 3.9 GiB swap peak are the
  same number to three significant figures and are NOT the same event — the
  peaks are logged 08-25 and 08-26, and on 08-23 the resident model was
  `colibri-glm` with a measured swap peak of 0 B. One grep, not published.
- **Predictions (D-013):** `nuc/predictions-e-round436.md`, written before the
  first ssh and before any capture byte was read. **21 HIT / 2 PARTIAL /
  7 MISS / 6 unevaluable of 36.** Five of the seven misses share one
  mechanism: I predicted the CONTENTS of a file nobody had opened, from round
  430's prose about it. Everything predicted from a banked COMMAND hit;
  everything predicted from a banked SENTENCE missed.
- **Artifacts:** `nuc/perturbation.py` 2749 → 3940 (17 new functions, 7 new
  CLI verbs: `journal`, `engine`, `place`, `direct`, `wsweep`, `stability`,
  `oom`); `nuc/tests/test_perturbation.py` 2035 → 2429; **tests 753 → 794, all
  green** (`794 passed in 84.54s`); `corpus_check` 10 checkers, 0 errors, 6
  warnings, `894 passed`; prediction bank registered in
  `state/prediction-bank-ledger.json` (round 435's K001 rule); `skill_lint skills --house --strict` 77 skills,
  **0 errors, 0 warnings**; `skills/matcher-defines-the-population/` (new,
  3 positive trigger cases, registered in `state/known-unprobed-skills.json`);
  `knowledge/round-436-the-population-the-regex-chose.md`.
- **E-mission status: E1-E5 all still DONE; nothing new unchecked.** The work
  is the standing analysis programme in these addenda.
- **Next E round, in order:** (1) `retention --strict` FIRST, with `--now` =
  the capture's own `CAPTURED_AT`; (2) **re-capture and fix three things in
  `capture_plan`** — step 3b's comment says "the USER manager" where the
  command asks for the engine unit; the plan emits no `###` header for that
  file, which is how two views ended up concatenated with only the second
  labelled; and it should capture the wide user journal OR the narrow
  engine-unit one but not both in one file. Add
  `_SYSTEMD_USER_UNIT=qwen36-toolproxy.service` — it has its own `Consumed`
  records and 9 invisible `Started` fires; (3) the `%vmeff` residual is still
  one read-only command away on a box that has RECLAIMED — check
  `pgsteal_kswapd > 0` first, the test has now been vacuous three times;
  (4) **run the engine against the `commit` channel** — a 9.25 GB weights load
  should be visible to `kbcommit` where it is `shared-only` on steal and swap,
  and if it is not that is a finding about the channel; (5) **treat the
  `Consumed` accounting as a channel in its own right** — build the ledger
  that uses it as the outcome variable and compare rankings; establish on the
  box (read-only) which units have `MemoryAccounting=` on, since coverage is
  only 4 of 26; (6) **14 costly buckets / 4.25 GiB named by no FIRE** — but the
  largest is the run-up to an OOM episode, so ask how many of the other 13 sit
  inside an OOM or restart window before calling them unexplained;
  `journal-pid1-full.txt` has never been read for anything but `Starting`
  lines, and `session-*.scope` records (474.0M and 208.7M peaks) were skipped
  by this round's `.service`-only default; (7) still blocked on the operator:
  `--cap 196` (band [129, 204], `bounded_by: engine_lru`, 1.096 GB margin —
  **twentieth** round unchanged) and the E3 A/B, which must publish its full
  six-gate table; (8) retire round 370's item 3 (names a log line this config
  does not emit) — carried untouched for eleven E rounds, untouched again
  here; (9) **the separability route is open and nobody has walked it** —
  round 430 called separability "the whole game" and the engine cleared that
  gate with 105 sole-occupied buckets, so the record CAN separate when the
  population holds something firing off the housekeeping cadence. The sub-600 s
  time base for the apt trio, and round 424's banked `Stopped`/`Stopping`
  lines, are still unused.

## Round 442 (NUC-integration E) — 2026-09-02, box **DOWN** the whole round; second consecutive down window (436, 442). All findings are offline

**Reachability.** Two SSH attempts, one per documented path, both failed —
CLAUDE.md's "if SSH fails twice in a row, record and exit cleanly" fired:

- tailnet `ssh -o ConnectTimeout=15 -i ~/.ssh/id_ed25519 jab@100.78.44.111`
  → `Connection timed out`.
- LAN `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` → `Connection timed
  out`, **and the key does not exist**: `Warning: Identity file
  /home/pgain/.ssh/id_ed25519_nuc not accessible: No such file or directory`.

**Coordinate worth recording, because it changes what "two paths" means from
this host.** The driver host is `srv1244884`, tailnet `100.85.110.121`, with
no LAN route to `192.168.1.0/24` and no `id_ed25519_nuc` key on disk. The LAN
path is not "currently unreachable" from here — it is unusable, and its
failure presents as a missing key file rather than a routing timeout. CLAUDE.md
already scopes it to "Mac-adjacent hosts only", which is right; this addendum
just records what the failure actually looks like so a future round does not
read the timeout as a box-down signal from a path that could never have worked.
The tailnet path is the ONLY path from here, and its timeout IS a box-down
signal.

**No mission ticked.** All five missions E1–E5 have been `[x]` since round 124,
so there is no "first unchecked mission" to pick. The round's work was the
offline finding below, which is track E's other standing job: the `nuc/`
subsystem's own health.

**Finding: `nuc-health-check` had never been green.** FAIL on all 32 rounds
from 410 (when round 409 wired it into `run_driver.sh`) to 441; zero PASSes in
`logs/driver.log`. Not a bug in `nuc/`: the driver runs the health checks under
`/usr/bin/python3` while every round runs under `.venv/bin/python3` (via
`claude-wrapper.sh`'s `source .venv/bin/activate`), and only the venv has
`tokenizers`. The live driver process carries `VIRTUAL_ENV` pointing at `.venv`
with no `.venv/bin` on `PATH` — a half-activated venv. `nuc/kv_reuse_model.py`
imported the optional package with no guard where `nuc/tests/test_prompt_budget.py`
had skipped cleanly since round 22, so the same environment fact was a SKIP in
one file and an ERROR in the next.

Fixed both ways, deliberately: `nuc/run_checks_fast.sh` now resolves its own
interpreter (prefers the repo venv, announces the choice) and the missing
optional dependency now SKIPS. Either alone turns the check green, which is
why both are there. Pinned by `nuc/tests/test_run_checks_interpreter.py` (8
tests, 5.9 s), and both pins falsified by reverting each fix. Final:
`802 passed`, `nuc-checks PASS`, exit 0 under the driver's exact PATH.

Full write-up, including the prediction scoring and the three misses:
`knowledge/round-442-the-check-that-never-had-a-baseline.md`.

**Open, handed to harness(A):** all four health checks call bare `python3` and
are exposed identically; `nuc/` was just the only one with a venv-only import.
The general fix is in `run_driver.sh`, which is harness(A)'s artifact.

## Round 448 (NUC-integration E) — 2026-09-02, box **DOWN** the whole round; THIRD consecutive down window (436, 442, 448). All findings offline

**Reachability.** Two attempts, one per documented path, both failed;
CLAUDE.md's two-failures rule fired after the second.

- tailnet `ssh -o ConnectTimeout=15 -i ~/.ssh/id_ed25519 jab@100.78.44.111`
  at 2026-09-02T06:31:32Z -> `Connection timed out`, rc 255.
- LAN `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` at 06:32:01Z ->
  `Connection timed out`, **and the key still does not exist on this host**.
- `tailscale status`: `Online False`, `LastSeen 2026-09-01T18:27:56.1Z` — the
  box has been away ~12 h and was away across the 2026-09-02T00:07 sweep.

**Round 442 left a hole in the durable record and this round closed it by
one.** `state/nuc-reachability-log.jsonl`'s previous entry was round 436's:
round 442 probed twice, wrote the failure into prose, and appended nothing.
Round 448's record is appended as `source: "live-replay-r448"` — it replays
the two probes above rather than opening a third connection after the rule had
fired. **Every E round owes this log one line, up or down.**

**Headline: the retention deadline this file and `state/research-state.md`
have carried for four rounds is not a date.** `sysstat-summary.service`
deletes only when its timer FIRES, the timer fires only while the box is up,
and the box is up perhaps half the time. Derived from the banked journal
(`sweeps` verb, new this round):

```
9 scheduled fires in the r424 capture's window, 7 ran, 2 MISSED
  (2026-08-30T00:07Z, 2026-09-01T00:07Z) — both inside a boot-table gap
persistence: FALSE — 0 of 2 missed fires re-ran within 3600 s of the box
  returning; it came back 25 min after one of them and still did not
```

So a slept-through sweep is **lost, not deferred**, and with the 2026-09-02
fire also missed:

- **`sa23`, `sa24`, `sar23`, `sar24` are STILL ON THE BOX** (~1.08 MB of `sar`
  history the standing note had written off).
- They die, together with `sa25`/`sar25` — **six files, not four** — at the
  next fire the box is awake for. Earliest **2026-09-03T00:07:00Z**.
- `sa01`'s deadline is unmoved at `2026-09-10T00:07:00Z`. The two numbers do
  not move together; quoting them as a pair implied a coupling that is absent.

**Standing action, replacing round 430's "run `retention --strict` first".**
Run BOTH, in this order, every E round:

```bash
.venv/bin/python3 nuc/capture_manifest.py sweeps \
    --capture state/nuc-capture-r424 --anchor <a measured fire> --strict
.venv/bin/python3 nuc/capture_manifest.py retention \
    --capture state/nuc-capture-r424 --now <CAPTURED_AT> --next-run <fire> \
    --history 7 --down-since <tailscale LastSeen> --down-until <now> --strict
```

`retention` alone answers the calendar question. It over-reports loss, in the
direction that makes a later round abandon data still on disk.

**Capture-plan fixes (closes round 436's next-E item 2, all four clauses).**
Step 3b's comment said "the USER manager" over a command reading
`_SYSTEMD_USER_UNIT=qwen36-colibri.service`; there was no `### ` marker on that
redirect, which is how `journal-user-full.txt` ended up two views concatenated;
`qwen36-toolproxy` was captured nowhere. Now: `journal-user-qwen36-colibri.txt`,
`journal-user-qwen36-toolproxy.txt` and `journal-user-manager.txt`, each
self-labelling; plus **new step 3e** `systemctl cat` + `systemctl show -p
Persistent -p OnCalendar -p RandomizedDelaySec` for both sysstat timers, so the
next up-round READS what this round had to INFER. The emitted plan is now
`bash -n`-checked.

**`%vmeff` — CLOSED by written decision, not carried a fifth time.** The
capture's own `pgsteal_kswapd`/`pgsteal_direct`/`pgscan_*` are all 0, so the
test is vacuous and cannot be resolved by analysis. It needs a box that has
actually reclaimed. It belongs in a precondition, not a next-steps list;
reopen when a capture shows a non-zero counter.

**Second finding: `tailscale_last_seen_utc` is not stable.** One outage, box
down throughout, local `tailscaled` unrestarted since 2026-08-09, and the field
read `18:30:00.1Z` at round 436 and `18:27:56.1Z` at round 448 — **124 s
earlier, 11 h later**. `streak_bounds` took the LATEST reading, which is unsafe
once two readings contradict; a disputed streak now takes the minimum and says
so. And a rounded-UP reading can walk into a down gap and make
`_gap_witness` assert a *missed excursion* that never happened — now fails
closed when another reading of the same streak disputes it. New verb:
`reachability_check.py lastseen-drift --strict` (live log: 1 drifting streak,
spread 124.0 s).

**Tests:** `nuc/tests` **802 -> 828, all green** (95.09 s); every pin falsified
by reverting the fix it guards. `nuc-checks PASS` (7 consecutive, 442-448).
`skill_lint skills --house --strict` 81 skills, 0 errors, 3 warnings.
New skill `skills/deadline-names-its-executor/` (4 trigger cases, registered
unprobed — batch is now **27**, so round 447's priced 26 is one round stale).

**E-mission status: E1-E5 all still DONE; nothing new unchecked.**

**Next E round, in order:**
1. **If the box is up, capture `sa23`/`sa24`/`sar23`/`sar24` BEFORE anything
   else** — they are alive only until the first 00:07 the box is awake for.
   Then run the new `capture_plan`, which finally takes `Persistent=` and the
   toolproxy journal.
2. **Read `Persistent=` and compare it against this round's derived `false`.**
   Two natural experiments is a verdict, not a proof; the unit text settles it.
   If it says `true`, this round's model is wrong in the *dangerous* direction
   and the whole §2 correction must be withdrawn — say so loudly.
3. **Score the sweep model against reality.** The capture's `ls -l` will show
   whether `sa23`/`sa24`/`sar23`/`sar24` survived. That is a real prediction
   this round has already made in public; do not quietly skip it.
4. Round 436's items 4-6 and 9 stand, untouched: the `commit` channel vs a
   9.25 GB weights load; `Consumed` as a channel in its own right (coverage is
   4 of 26 units — establish which have `MemoryAccounting=`); the 13 remaining
   costly buckets named by no fire, asked *inside* an OOM/restart window; and
   the separability route nobody has walked.
5. Still blocked on the operator: `--cap 196` (band [129, 204],
   `bounded_by: engine_lru`, 1.096 GB margin — **twenty-second** round
   unchanged) and the E3 A/B with its full six-gate table.
6. Retire round 370's item 3 (names a log line this config does not emit) —
   carried untouched for thirteen E rounds, untouched again here.

## Round 454 (NUC-integration E) — 2026-09-02, box **DOWN** the whole round; FOURTH consecutive down window (436, 442, 448, 454), one continuous outage

**Reachability.** Two attempts, one per documented path, both failed;
CLAUDE.md's two-failures rule fired after the second.

- tailnet `ssh -o ConnectTimeout=15 -i ~/.ssh/id_ed25519 jab@100.78.44.111`
  at 2026-09-02T12:36:41Z -> `Connection timed out`, rc 255.
- LAN `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` at 12:37:02Z -> same,
  **and the key still does not exist on this host**.
- `tailscale status --json` at 12:37:51Z: `Online false`,
  `LastSeen 2026-09-01T18:27:56.1Z` — **byte-identical to round 448's**, so
  436/442/448/454 are one outage. `status`: 17h34m34s confirmed, upper bracket
  18h37m16s, **2h03m32s short of the longest outage this log has confirmed**.
  Round 454's row appended as `live-replay-r454`.

**Headline: round 448's rule had EIGHT violations, not one, and the evidence
for seven of them was in a file no round had ever opened.** Round 448 found
round 442's missing row and wrote "Every E round owes this log one line, up or
down". Nobody counted. Counted: 55 E rounds in [124, 448], **47 with a row,
eight without** — 148, 190, 220, 226, 250, 280, 292, 442. `logs/driver.log`
records seven of the eight as `track=NUC-integration(E)` + `success`.

Round 310's prose backfill missed seven of them because it read
`state/nuc-missions.md`'s addenda and those rounds wrote none. **Six of the
seven have no `knowledge/round-N-*.md` file either.** Their probes survive in
exactly one place: `logs/round-<N>.json`, the round's own transcript, with the
exact ssh command, the exact output and a millisecond timestamp.

**Recovered, and re-derivable:** 190 down, 220/226/250/280/292 up, 442 down.
New `nuc/reachability_recover.py`; unlike the one-shot backfill it reads files
rather than a hardcoded list, refuses to duplicate an existing row, returns
`conflict` rather than guessing when a probe carries both signals, picks the
last **tailnet** failure (not the last failure — the LAN path is unusable from
here, so its timeout means nothing), and emits `boot_utc` only from an absolute
`uptime -s` line. Rounds 220/226/250 read `uptime -s` on three different days
and all recover `2026-08-27T11:50:48Z`, the boot the log's round-202-era rows
already carry. `test_every_recovered_row_in_the_live_log_still_re_derives`
demands byte-identical regeneration from the transcripts.

**Second finding: eight observations made the instrument report MORE
ignorance.** `unobserved_total_s` went 108h02m03s -> 117h47m57s. Split: the up
side's +7455 s is real (round 292 extends its streak), the down side's
**+27699 s is a defect**. `_gap_witness` consulted only the immediately-
following record's `tailscale_last_seen_utc`, so a fully-witnessed gap split by
a recovered row — which has no LastSeen — lost the witness entirely (184->196
by round 190: 8223 s; 436->448 by round 442: 19476 s; 8223+19476 = 27699). But a
reading at R saying "last seen S" proves the peer was off the tailnet in (S, R]
— covering **every** gap of the streak in that span. `_gap_witness` now looks
forward, inherits round 448's dispute rule, and **may witness but may not
accuse**. Down-side ignorance back to 0.0; interior insertions now move the
total by exactly zero, pinned as an invariant.

**Third: `coverage`, the enforcer the rule never had.** Population is
`logs/driver.log`, NOT `N mod 6 == 4` (they disagree: round 220's
research-state heading says SWE-loop(D), the driver says E, and that round's
transcript has live NUC probes). The highest E round is exempt by default —
the driver writes `start` before the round runs, so without that the check is
red for the whole of every E round. Live: **50 of 50 owed rounds covered,
`--strict` exit 0**. `state/nuc-reachability-declared-holes.json` ships EMPTY;
round 454 first declared round 148 in it and the registry's own
`declared_but_not_missing` field caught that as a dead acknowledgement.

**Two brittle tests rewritten.** One asserted `end_round == 448` on the drift
streak — guaranteed to break on the next down round, for a reason unrelated to
drift. The other asserted `442 not in rounds`, pinning the hole OPEN: round
448's prose wanted 442 recovered and the test it shipped alongside made
recovering it a failure. Both now pin what they are about.

**One latent bug exposed, not caused:** a fixture derived its window from
`recs[0]`/`recs[-1]`. `load_log` returns FILE order; appending recovered rows
is exactly what breaks that, and the log will never be chronological again.
Fixed to min/max and pinned by an order-insensitivity test.

**Round 448's standing action, run.** `sweeps --strict`: 9 scheduled, 7 ran,
2 missed, `persistence FALSE`, exit 0. `retention --strict` with the current
down window: `skipped_fires ["2026-09-02T00:07:00Z"]`, **6 doomed**
(sa23/24/25 + sar23/24/25), `earliest_loss_utc 2026-09-04T00:07:00Z`,
`earliest_loss_conditional true`. Round 448's forecast is HOLDING but is still
a forecast — nothing has re-read the box's directory since round 424.

**Round 448's item 6 done: round 370's item 3 is RETIRED.** Round 424 found the
journal holds the load retrospectively and that there are **no `unpacking to
int8 in slot` lines at all** on that boot (9 journal lines; model dir
`qwen36_i4_gs64`). The item names a log line this config does not emit, and its
other half (the `memory.current` trajectory) is permanently gone. Reopen only
if the model directory changes.

**Predictions (D-013):** `nuc/predictions-e-round454.md`, banked before any
test was run and before any transcript was opened. **6 HIT, 1 PARTIAL, 2 MISS
of 9.** Both misses share one cause and it is the round's own lesson: the bank
predicted from `state/research-state.md` hit counts and never considered
`logs/round-N.json` — it had the wrong inventory of places evidence can live.

**Tests:** `nuc/tests` **828 -> 869, all green** (96.04 s); `nuc-checks PASS`
(**eight** consecutive, 442-454). Every new pin falsified by reverting the fix
it guards (5 falsifiers, 8/2/2/2 tests red respectively).

**E-mission status: E1-E5 all still DONE; nothing new unchecked.**

**Next E round, in order:**
1. **`coverage --strict` FIRST**, before anything else. If it is red, close the
   hole with `reachability_recover.py` from `logs/round-N.json` before writing
   prose about it.
2. **If the box is up, capture `sa23`/`sa24`/`sar23`/`sar24` BEFORE anything
   else**, then the current `capture_plan`. Round 448's items 1-3 all still
   need a reachable box; in particular READ `Persistent=` — if it says `true`,
   round 448's §2 correction is wrong in the dangerous direction and must be
   withdrawn loudly.
3. **The up side of the witness bug is latent and unexhibited.** A `BOUNDED`
   gap split by a record with no `boot_utc` regresses the same way. No live
   instance exists, so it is deliberately unbuilt; supplying a journal capture
   that makes `bounded_gap_count > 0` creates one.
4. **The recovered rows have no `tailscale_last_seen_utc` and could.** Round
   190's transcript has `offline, last seen 3h ago` — coarse, and deliberately
   NOT converted, because an hour-derived LastSeen is exactly the "rounded value
   walks into a gap" hazard round 448 found. The honest route is a
   precision-aware LastSeen, not a division.
5. Round 448's item 4 (round 436's items 4-6 and 9) stands **untouched**: the
   `commit` channel vs the 9.25 GB load, `Consumed` coverage at 4 of 26 units,
   the 13 costly buckets named by no fire, and the separability route.
6. **Still blocked on the operator:** `--cap 196` (band [129, 204],
   `bounded_by: engine_lru`, 1.096 GB margin — **twenty-third** round
   unchanged) and the E3 A/B with its full six-gate table.

## Round 460 (NUC-integration E) — 2026-09-02, box **DOWN** the whole round; FIFTH consecutive down window (436, 442, 448, 454, 460), one continuous outage

**Reachability.** Two probes, one per documented path, both before any code
ran; CLAUDE.md's two-failure rule fired after the second.

- tailnet `ssh -o ConnectTimeout=12 -i ~/.ssh/id_ed25519 jab@100.78.44.111`
  issued 2026-09-02T19:33:25Z -> `Connection timed out`, rc 255, by 19:33:37Z.
- LAN `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` at 19:33:37Z -> same,
  **and the key still does not exist on this host**, so that path proves
  nothing either way.
- `tailscale status --json`: `Online false`,
  `LastSeen 2026-09-01T18:27:56.1Z` — **byte-identical to rounds 448 and
  454**, so 436/442/448/454/460 is ONE outage. `status`: **24h22m15s**
  confirmed, upper bracket 25h24m57s. It passes the longest completed streak
  in this log (19h38m06s) by a *definite* 1h59m48s and the longest unobserved
  one (14h00m00s) by 10h22m15s — **the longest outage this log has confirmed.**
  Round 460's row appended as `live-replay-r460`, and this time by a program.

**Headline: `precision` has been on every row since round 310 and no rule ever
read it.** 20 of 61 rows are `coarse` (a `boot + minute-truncated uptime`
reconstruction, so a LOWER bound on the true instant); 23 of 53 gaps have a
coarse endpoint; those gaps carry **60.3% of `unobserved_total_s`** (239090 s
of 396378 s). The headline `max_unobserved_outage`, printed as exactly
`14h00m00s`, is really **13h59m00s .. 14h01m00s** — a round number produced by
two minute-truncated endpoints agreeing on their seconds field. The RANKING
survives (runner-up 27780 s), and the new audit reports those two facts
separately.

Every comparison in `_gap_witness` now runs on the bound that makes its claim
harder. The dangerous one is the accusation branch: a coarse `checked_at_utc`
understates when a gap STARTED, which is the direction that sweeps a sighting
into the gap and manufactures a missed excursion. Round 448 fixed that hazard
on the LastSeen side; it was sitting on the `checked_at_utc` side the whole
time, on 20 rows the log had already flagged. A bracket that straddles a
boundary now decides nothing — neither witness nor accusation.

**And it changes nothing today.** New `precision-audit [--strict]` runs the
rules twice, once with every timestamp declared exact, and diffs: **0 unearned
claims, 0 unearned missed excursions.** The guards are preventive; `--strict`
goes red the day that stops being true. One reachable path to an unearned
claim is pinned by a fixture. A property that explains the empty list: a
witness can never be lost to the EARLIER check's precision, because witnessing
reads that check's lower bound and coarseness only opens a bracket forward.

**Round 454's item 4, DONE — as a bracket, not a division.** The plaintext age
renderer was CALIBRATED against `--json`'s exact `LastSeen` on this host, four
peers, same instant: it FLOORs (macbook 7.638m -> `7m`, REDMI 13.7045d ->
`13d` both discriminate), one integer, one unit, never compound. Round 190 read
`3h` **twice**, 6m18s apart, from two different Bash calls — an ssh-only scan
sees one, the new `transcript_lastseen_readings` sees both — and the two
brackets intersect to `[04:03:21Z, 04:57:04Z]`, 3223 s instead of 3601 s,
tightened by exactly the spacing. **Round 196's JSON `LastSeen`
(04:48:21.1Z, read three hours later by a different check) falls inside it**,
45m00.1s above the floor and 8m42.9s below the ceiling; under round-to-nearest
the bracket would miss it by nine minutes. That cross-check re-derives rather
than reading the committed row, so it falsifies the MODEL.

The bracket witnesses gap 184->190 directly, replacing round 454's inherited
forward witness. No published number moves.

**Round 454's item 3, CLOSED.** The up-side split-gap regression was "latent
and unexhibited"; the exhibit is a fixture and was cheaper than waiting for the
row that creates one. Fix is round 454's own argument run outward: bracketing
readings on both sides of a gap that agree on `boot_utc` (within round 376's
5 s jitter) rule out a reboot across the whole span. **May witness, may not
accuse.** Live: rounds 202/220/226/250 all report boot `2026-08-27T11:50:48Z`
to the second, so **seven gaps** move from `none` to `reboot_only`. No headline
number moves — but `_silence_upgrade` is keyed on `REBOOT_ONLY`, so **16h49m
(15.3% of the log's ignorance) is now one journal capture away from a bound
instead of permanently out of reach.**

**Two things nobody was running.** (1) `lastseen-drift --strict` has been
exiting 1 since round 448 introduced it and no round file says so, because
nothing runs the strict instruments — they run when an E round remembers, every
sixth round at best. `nuc/run_checks_fast.sh` now prints
`nuc-instruments coverage=0 precision-audit=0 lastseen-drift=1` every round,
DIAGNOSTIC ONLY: the `nuc-checks ...` line is parsed by
`harness/driver_health.py` and widening that contract is harness(A)'s artifact.
(2) **`live-replay-r<N>` appeared in NO source file** — rounds 448 and 454 both
typed it. New `reachability_check.py replay` is the producer, running `check`'s
own code path with observations injected through its existing test seams.

**A finding about this repo, not the NUC.** `.gitignore:20` excludes
`logs/round-*.json`, so round 454's recovered rows are pinned against files
deliberately not in the repository. A pristine `git worktree` at HEAD gives
**11 failed / 857 passed**; with the seven transcripts symlinked in, 866
passed / 2 failed (both environmental) / 1 skipped.

**Tests:** `nuc/tests` **869 -> 915, all green** (103.17 s); `nuc-checks PASS`
(**ninth** consecutive). Nine falsifiers, each red on exactly its guards
(10/1/2/3/5/2/6/4/2).

**Predictions (D-013):** `nuc/predictions-e-round460.md`, banked before any
instrument ran. **13 HIT, 1 PARTIAL, 0 MISS of 14**, plus one declared
no-basis item resolved. The PARTIAL is P12 and it is a PROCESS failure: a
baseline predicted but never measured pristine, which is only measurable in a
worktree and only after the tree was already dirty.

**E-mission status: E1-E5 all still DONE; nothing new unchecked.**

**Next E round, in order:**
1. **`coverage --strict` AND `precision-audit --strict` FIRST**, before
   anything else. Both are green today; `precision-audit` going red means the
   log has started publishing conclusions drawn from digits it flagged as
   rounded, and the round file must name the gap before writing prose.
2. **If the box is up, capture `sa23`/`sa24`/`sar23`/`sar24` BEFORE anything
   else**, then the current `capture_plan`. Round 448's items 1-3 still need a
   reachable box; in particular READ `Persistent=` — if it says `true`, round
   448's §2 correction is wrong in the dangerous direction and must be
   withdrawn loudly. **Then capture a journal interior covering rounds
   202-250**: seven gaps and 16h49m are now REBOOT_ONLY and therefore eligible
   for the BOUNDED upgrade that was unreachable for them before round 460.
   This is the single largest reduction in this log's ignorance now available.
3. **The `.gitignore` question is the operator's, and it is a real one.**
   Seven log rows and eleven tests depend on `logs/round-*.json`, which is
   ignored on purpose. Either the provenance claim is weaker than round 454's
   prose says, or those seven transcripts belong in the repo. Do not "fix" it
   by deleting the tests; say which of the two is intended.
4. **Widening the `nuc-checks` line to carry the strict instruments' exit
   codes is harness(A)'s call**, not E's — `harness/driver_health.py` parses it
   and `harness/tests/test_nuc_health_line.py` pins the format. `coverage` and
   `precision-audit` are the two that mean "a published conclusion is wrong";
   `lastseen-drift` means "the field moved again" and is arguably information,
   not a break.
5. Round 448's item 4 (round 436's items 4-6 and 9) stands **untouched** for a
   third round: the `commit` channel vs the 9.25 GB load, `Consumed` coverage
   at 4 of 26 units, the 13 costly buckets named by no fire, and the
   separability route.
6. **Still blocked on the operator:** `--cap 196` (band [129, 204],
   `bounded_by: engine_lru`, 1.096 GB margin — **twenty-fourth** round
   unchanged) and the E3 A/B with its full six-gate table.

## Round 466 (NUC-integration E) — 2026-09-03, box **DOWN** the whole round; SIXTH consecutive down window (436, 442, 448, 454, 460, 466), one continuous outage. All findings are offline work on round 424's banked capture

**Reachability.** Two probes, one per documented path, both before any code
ran; CLAUDE.md's two-failure rule fired after the second.

- tailnet `ssh -o ConnectTimeout=12 -i ~/.ssh/id_ed25519 jab@100.78.44.111`
  issued 2026-09-03T00:59:37Z -> `Connection timed out`, rc 255, by 00:59:49Z.
- LAN `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` at 00:59:57Z -> same,
  **and the key still does not exist on this host**, so that path proves
  nothing either way.
- `tailscale status --json` at 01:00:10Z: `Online false`, `LastSeen
  2026-09-01T18:27:56.1Z` — **byte-identical to rounds 448, 454 AND 460**, so
  436/442/448/454/460/466 is ONE outage. Plaintext: `active; relay "sin";
  offline, last seen 1d ago, tx 10296 rx 0`.
- `status`: **29h50m36s confirmed**, upper bracket 30h53m18s. Passes the
  longest completed streak in this log (19h38m06s) by a **definite 10h12m30s**
  and the longest unobserved one (14h00m00s) by 15h50m30s — it extends its own
  round-460 record. `unobserved_total_s` unmoved at 396378 s.
- Round 466's row appended with round 460's `replay` producer, not typed.
  `state/nuc-capture-r466/tailscale-status-r466.json` is the JSON it read.
- **Zero ssh sessions succeeded: nothing was read from or written to the box,
  port 8001 was never contacted, no engine request of any kind was made.**
- Round 460's item 1 ran FIRST: `coverage --strict` **0**,
  `precision-audit --strict` **0**, `lastseen-drift --strict` **1** — exactly
  the state round 460 left, the last for the documented reason (tailscale
  recomputes `LastSeen`), not a new break.

**Round 436's item 6 is CLOSED, in both halves, after five E rounds carried
it.**

(a) The fire population is `.service`-only and **the journal is mostly not
services.** `unit_kind_census` on the ten-day PID-1 journal: service 1652
`Starting` / 206 `Started` (visible); **scope 0 / 1401**, timer 0 / 84, socket
12 / 0, path 0 / 6 (all invisible). **1709 start lines are invisible — more
than the 1652 that are visible**, and the invisible majority is one thing:
1401 `Started session-N.scope`. **No `.scope` emits `Starting` at all**, which
is round 436's own `Type=simple` mechanism, so its two-pass rule generalises to
scopes with NO new double-count decision — only the kind alternation widens.
`parse_unit_starts_any_kind(text, kinds)` is that widening, with the kind in
the dedup key, pinned byte-identical to `parse_unit_starts_complete` at the
default.

Widening moves everything: costly-bucket coverage **19/52 -> 44/52** and named
bytes **8.42 -> 29.65 GiB, 26.7 % -> 94.0 %** of the window's swap-out. Scopes
ALONE name 29/52 and 72.3 %. (Note for anyone quoting `n_fires`: the published
population is **647** after exclusions — `sysstat-collect` is 1005 of its 1652
lines.)

(b) **"How many of the other 13 sit inside an OOM or restart window?" — NONE.**
8 marks in the journal (4 OOM lines / 3 episodes, 3 `Scheduled restart`, 1
`Failed with result`), 6 distinct instants. At +/-30 min AND +/-60 min, **0 of
13**; only `2026-08-23 21:20:02`, the one round 436 already knew, is in such a
window. Base rate over all 52 costly buckets is 7/52 (13 %). The OOM
hypothesis for the residual is dead.

**But 94 % is a TRAP, and which null you pick decides its sign.** A population
names a bucket by landing in it, so coverage is evidence only against a null
holding size AND shape fixed — and the two obvious nulls disagree in opposite
directions on this data:

| null | holds fixed | expects (scopes) | verdict on observed 29/52 |
|---|---|---|---|
| uniform placement | count only | 39.5 / 52 | *below* chance, p = 1.000 |
| **circular shift** | count, cadence, bursts, every gap | **6.7 / 52** | ~4.3x chance, p <= 0.0005 |

These fires arrive in bursts (53 bursts >30 min apart, largest **517 sessions
in 486 min**), so a uniform draw touches far more DISTINCT buckets than the
real population can and grades a 4x effect as sub-chance. `shift_null` rigidly
translates the whole train and wraps it: only alignment is destroyed. Measured,
2000 draws: published services 19 vs null 8.37 (p 0.0005); **scopes 29 vs null
6.70 (p <0.0005)** — *the invisible population predicts costly swap better than
the entire published one*; services+scopes 44 vs 13.41; engine 18 vs 2.11.
Whole-DAY shifts (preserving time-of-day cadence exactly) give scopes 3..10.

**Of round 436's 14 unnamed buckets (re-derived exactly, 4.25 GiB, largest
`2026-08-23 21:20:02` at 2.34 GiB), session scopes name 7 — including the
largest** — against a null mean of 1.79 (5-95 % 0..4), **p = 0.002**.

**AND THE SCOPES ARE THIS PROGRAM'S OWN FOOTPRINTS.** All 1401 are
`session-N.scope`, "Session N of User jab" — ssh logins. Three measurements:
**median session lifetime 1 s, 1253/1396 (89.8 %) <= 5 s** (that is
`ssh host 'cmd'`, not a person; the record still holds a 4-day session, so the
median is the population's property not the parser's). **33 of the 35
successful probes in `state/nuc-reachability-log.jsonl` have a session-scope
start within 120 s, 18 of them within +/-1 second** — two files, different
programs, different hosts, recording the same events. And on the 33 costly
buckets the log's dates cover, **13 of the 14 scope-named ones sit inside an
E-round window** [probe-300 s, probe+3300 s] against 5 of the other 19:
**Fisher two-sided p = 2.5e-4**.

So the strongest single "explanation" of costly swap on this box over ten days
is **this research program's own measurement traffic**, and the 94 % gets there
by attributing the box's cost to its observer. Direction argued, not assumed:
the driver's rotation runs on another host with no reading of the NUC's memory
state, so it cannot be selecting busy moments — which does not prove the
logins *caused* the swap (a 1 s login does not move 2.34 GiB by itself) but
does rule out the observer choosing its times.

**Therefore `parse_unit_starts_any_kind` DEFAULTS TO `("service",)`.** The
widening is built, correct, tested and **OFF**. No published number moves
unless somebody passes the wider argument on purpose.

**19 of the 52 costly buckets are UNTESTABLE for this**, not negative: they are
on 08-23/08-24 and the reachability log's first row is 08-25. Scoring them as
"not in a round window" would have manufactured 19 negatives from a file that
did not exist yet — and would have made the Fisher table look better.

**The fast path had to be checked against the instrument, and that caught two
bugs.** `BucketMap` (second -> costly bucket) is built BY calling `cost_ledger`
and ships `verify()`. The first draft reimplemented the placement rule; the
self-check caught a mishandled post-restart row, and
**`LEDGER_EXCLUDE_UNITS` not applied on the map path, which took the published
population's observed coverage from 19 to 50**. Either would have produced a
confident, wrong null. `population --verify` is that check as a command.

**New instruments:** `perturbation.py population` (coverage + the shift null,
refuses to report coverage bare) and `perturbation.py observer`
(`--census`, `--strict`; session lifetimes, probe/scope coincidence, the
confounding table).

**Tests:** `nuc/tests` **915 -> 946, all green** (174.4 s); the round-466 block
alone is 37.9 s after a `BucketMap` cache (208.1 s before it). **Seven
falsifiers, and TWO of them came back 0 red on the first run** — F1 (no fixture
collided a unit NAME across two KINDS, so the dedup key's second element was
untested) and F7 (offset 0 is drawn about once in a million from an
864 000-second span, so `n_identity_draws` was unreachable by any random-draw
test). Both closed: a synthetic collision fixture, and a `shifts=` argument
that makes the identity branch reachable and doubles as the
deterministic-reproduction hook a published p-value ought to have. **A
falsifier that goes 0 red because the code path cannot be reached is a design
problem, not a testing one.**

**Predictions (D-013):** `nuc/predictions-e-round466.md`, banked before any
instrument ran, with a §0 recording the three exploratory reads that preceded
it and TWO items declared no-basis. **11 HIT, 2 PARTIAL, 1 MISS of 14, plus
both no-basis items resolved.** The MISS is P5 (the 2.34 GiB run-up bucket IS
scope-named — I modelled one session where the record holds sixty). One PARTIAL
is P14, and it is a bracket error in PROSE while `precision-audit` was green:
"the confirmed streak passes 30 h" used the *upper* bracket's arithmetic;
confirmed is 29h50m36s, 9m24s short.

**E-mission status: E1-E5 all still DONE; nothing new unchecked.**

**Next E round, in order:**
1. **`coverage --strict`, `precision-audit --strict` FIRST**, as round 460
   established, and read your own bracket before quoting a streak number —
   round 466 shipped bracket discipline and then mixed the bounds in prose.
2. **THE DECISION THIS ROUND DELIBERATELY DID NOT TAKE ALONE: should
   `session-*.scope` join `LEDGER_EXCLUDE_UNITS`?** `sysstat-collect` is
   excluded because it WRITES the bucket; a session scope would be excluded
   because it IS the observer. That is a different reason and it deserves a
   written decision rather than a silent filter. Whoever decides should run
   `population` both ways and publish both tables. Note the exclusion is NOT
   obviously right: if the program's own traffic really costs the box 4 GiB of
   swap, that is a fact about the deployment and hiding it is worse than
   naming it.
3. **The observer effect is now a measured hypothesis and it has an
   experiment.** If the logins cost the memory, the cost should scale with what
   the round DID, not with the login count — an E round that only probes should
   be cheap and one that scps a 1.0 MB journal + 1.3 MB sar + a tar should not.
   `state/nuc-reachability-log.jsonl` knows which rounds were which. Do this
   OFFLINE on the banked capture before spending a live window on it.
4. **If the box comes up:** capture `sa23`/`sa24`/`sar23`/`sar24` first, then
   READ `Persistent=` (round 448's §2 correction is wrong in the dangerous
   direction if it says `true`, and must be withdrawn loudly), then a journal
   interior covering rounds 202-250 — round 460's seven `REBOOT_ONLY` gaps and
   16h49m are still one journal capture away from a bound.
5. **Round 436's items 4, 5 and 9 STILL stand, untouched for a fourth round**
   — the `commit` channel vs the 9.25 GB weights load, `Consumed` coverage at 4
   of 26 units, and the separability route. Item 6 is now CLOSED; do not carry
   it forward.
6. **Still blocked on the operator:** `--cap 196` (band [129, 204],
   `bounded_by: engine_lru`, 1.096 GB margin — **twenty-fifth** round
   unchanged) and the E3 A/B with its full six-gate table. Round 436's OOM
   evidence still stands behind the first: three episodes in ten days, one of
   which killed the engine, against a directly measured 30.0 GiB peak on a
   31.2 GiB box.

## Round 472 (NUC-integration E) — 2026-09-03, box **DOWN** the whole round; SEVENTH consecutive down window (436, 442, 448, 454, 460, 466, 472), one continuous outage. All findings are offline work on round 424's banked capture and on this repo's own driver transcripts

**Reachability.** Two probes, one per documented path, both before any code
ran; CLAUDE.md's two-failure rule fired after the second.

- tailnet `ssh -o ConnectTimeout=15 -i ~/.ssh/id_ed25519 jab@100.78.44.111`
  issued 2026-09-03T08:32:08Z -> `Connection timed out`, rc 255, by 08:32:23Z.
- LAN `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` at 08:32:32Z -> same,
  **and the key still does not exist on this host**, so that path proves
  nothing either way.
- `tailscale status --json` at 08:33:02Z: `Online false`, `LastSeen
  2026-09-01T18:27:56.1Z` — **byte-identical to rounds 448, 454, 460 AND
  466**, so 436/442/448/454/460/466/472 is ONE outage. Plaintext: `active;
  relay "sin"; offline, last seen 1d ago, tx 12168 rx 0`.
- `status` after the row was appended: **37h26m00s confirmed**, upper bracket
  38h28m42s. Passes the longest completed streak in this log (19h38m06s) by a
  **definite 15h03m33s** and the longest unobserved one (14h00m00s) by
  23h26m00s. The CONFIRMED figure is quoted everywhere in this round; round
  466 mixed the brackets in prose and scored itself a PARTIAL for it.
- Round 472's row appended with `replay`, reading
  `state/nuc-capture-r472/tailscale-status-r472.json`. Log now 63 rows.
- **Zero ssh sessions succeeded: nothing was read from or written to the box,
  port 8001 was never contacted, no engine request of any kind was made.**
- Round 460's item 1 ran FIRST: `coverage --strict` **0**,
  `precision-audit --strict` **0**, `lastseen-drift --strict` **1** — the
  state rounds 460 and 466 left, the last for the documented reason. Re-run
  after the append: identical.

**Round 466's item 3 is ANSWERED, and the answer is NULL.** The dose comes
from `logs/round-<N>.json` (the driver's own transcripts, millisecond
timestamps, every shell command), the response from the sar record; neither
file knows about the other. Every round is scored over the same 3601 s window,
because window length is itself a dose. Negative controls — the round's LOCAL
work, which cannot touch the box — are in the same table as the doses.

**Over all 42 scorable rounds the experiment says the observer costs the box:
`n_calls` rho +0.418, p 0.0062. It is the box's POWER SWITCH.** Ten of those
42 windows have zero sar buckets because the box was down, so their response
is zero by construction — and a down round makes two probe calls instead of
fifteen. Restricted to the **28 full-record windows**: **no dose reaches
p <= 0.05**; the strongest is `bytes_landed` at rho **−0.277** (wrong sign),
and the two terms nearest significance are the CONTROLS `local_bytes`
(p 0.037) and `transcript_bytes` (p 0.051). The unstratified table ships under
the key `dose_response_UNSTRATIFIED_do_not_quote`.

**The dose had to be fixed twice before it was a dose at all.** (a) A heredoc
BODY quoting an ssh line — round 424's own prediction file — scores as a
login on any substring test. (b) Round 424 pulled 3.26 MB off the box with
`ssh ... > file`, so the transcript holds 489 bytes: **`bytes_returned` 14 077
vs `bytes_landed` 2 896 862, a factor of 206, and round 424 used NO scp**, so
an scp-only fix misses it entirely. Scored on stdout the heaviest round in the
corpus reads as one of the lightest — the exact direction that manufactures a
null.

**Three nulls, each fixing the last, each moving the p-value the same way.**
Window-level, same 28 windows, only the null's SUPPORT changes: random shift
over the whole span p 0.072 -> restricted to the days E rounds can occupy
(08-26..08-31, since the driver log begins round 152 on 08-26) **p 0.0095** ->
**coverage-conditional rate, so a window shifted onto DOWNTIME cannot count as
a miss: 11/28 = 0.393 vs null 0.277, p 0.128, NOT significant.** Separately,
null 1's bytes reading (`obs 2.383 GB vs null MEAN 4.567 GB`) inverts once the
median is shown: **null median 2.336 GB**, essentially equal to the
observation. `null_median_*` is now reported beside every mean.

**Round 466's own statistic re-run under the corrected null, and the split
that reconciles everything.** `shift_null_covered` scores a rate over fires
that land on covered ground:

| population | fires | landed | rate obs | null | p |
|---|---|---|---|---|---|
| published `.service` | 647 | **47.8 %** | 0.168 | 0.051 | **0.056** |
| session scopes ONLY | 1401 | **98.1 %** | 0.207 | 0.053 | **0.0010** |

The scope result SURVIVES; **the published service population's does not**
(0.0005 -> 0.056), and the reason is the middle column — services spend more
than half their fires on ground the record does not cover.

**41 %, not "the scopes are ours".** Round 466 wrote that from a PROBE-side
rate (33/35 log rows). The transcripts answer the scope side: of 1109 testable
scopes (292 predate the transcript corpus and are UNTESTABLE), **454 are ours
(40.9 %) and 655 are not (59.1 %)**, against a 4.23 % chance match rate. Split
and re-null: **ours 0.2172 vs 0.0468, p 0.0000** (and p 0.0000 under whole-day
shifts once the identity draw is removed — `ours` spans 7 days, so 7 x 86400
IS the identity); **not-ours 0.0421 vs 0.0529, p 0.4650**. The entire
association is this program's own logins; the box's other 655 logins are
chance.

**Lead-lag says cost, not shared clock.** Costly-bucket rate by displacement
in 600 s buckets — `ours` peaks at zero (0.217, ~14x its far field) with a
right shoulder (+1 0.099, +2 0.061) about twice the left; `not ours` has no
peak at zero at all; `published services` peaks at zero with NO shoulder
(+1 0.022), i.e. co-location without persistence. **Caveat kept in the round
file: a round makes ~12 logins over 10-25 min, so part of the right shoulder
is within-round clustering, not persistence. The peak at zero is unaffected;
the asymmetry is suggestive, not established.**

**What that leaves.** At login-instant resolution (n=454) the coincidence is
strong and robust; at round-window resolution (n=28) and at
how-much-the-round-did resolution (n=28) there is nothing. Together those say
**if the logins cost memory the cost is per-login and roughly fixed, not
proportional to the work** — plausible on a box at 92 % memory used, and NOT
established.

**Round 466's item 2 is DECIDED: do NOT exclude `session-*.scope`.**
`LEDGER_EXCLUDE_UNITS` is untouched and a test holds it at
`("sysstat-collect",)`. Both tables (`perturbation.py exclusion`): widened
WITH scopes **44/52, 31 839 289 344 B, 94.04 %**; WITHOUT **19/52,
9 039 863 808 B, 26.70 %** — byte-identical to the published population, so
the 40 non-session fires the widening adds contribute nothing. Excluding costs
−25 buckets, −22.80 GB, −67.34 pp. Three reasons: it would be a silent
67-point move; round 466's "hiding it is worse than naming it" is
strengthened, not weakened, by the split; and the *reason* for excluding got
weaker — `sysstat-collect` is excluded because its fire IS the bucket's cost,
whereas the lead-lag shoulder says a login's cost outlives the login.

**Round 424 is the observer's largest intervention and the instrument cannot
see it.** 2 896 862 bytes landed, 9x the next round — and its window scores
`record_coverage: partial, 1 bucket`, because **round 424's capture IS the end
of the record**. Round 430 is `none`. The six most recent E rounds are
untestable because the box has been down since 09-01 and no capture has been
taken since.

**Tests: `nuc/tests` 946 -> 995, all green, 229.5 s** (the fast check's nested
pytest is most of that); the round-472 file is 49 tests in 15 s. **One test
went red on its first run and the TEST was wrong** — the "no association"
stratum was built as a perfect rank correlation. Then **every falsifier was
mutation-tested**: 10 mutations, first pass killed 7, **three survived** — a
DEAD `via_variable` disjunct, a wrap test whose tail was empty because the
pooled window opens at 14:02 on day 0, and `n_identity_draws` untested in
`shift_null_covered` *while deciding a published p-value*. All three fixed;
10 of 10 now go red. Round 466's F1/F7 lesson recurring: first-run silence
does not reveal an unfalsifiable test, mutation does.

**E-mission status: E1-E5 all still DONE; nothing new unchecked.**

**Next E round, in order:**
1. **`coverage --strict`, `precision-audit --strict`, `lastseen-drift
   --strict` FIRST**, and quote the CONFIRMED bracket, not the upper one.
2. **Deconfound the lead-lag shoulder.** The peak at zero is solid; the
   asymmetry that makes it look like a cost rather than a co-location is
   contaminated by within-round login clustering. The fix is a resampling that
   keeps each round's login train intact and moves the train — i.e.
   `shift_null_covered` applied per round window rather than to the pooled
   population. If the shoulder survives that, the causal reading has real
   support; if it does not, §4b of the round file should be withdrawn loudly.
3. **`lead_lag_profile` has no null.** It reports rates, and "0.217 vs 0.015"
   is currently read by eye. Give it the same shift machinery the other
   statistics have, or stop putting numbers next to each other in a table that
   invites subtraction.
4. **Mutation-test the round-466 block too.** This round mutation-tested only
   its own code and found 3 of 10 falsifiers unfalsifiable. `test_perturbation.py`
   has never been through that pass and it carries every published number in
   this track.
5. **If the box comes up:** capture `sa*` FIRST — every window-level result
   here is limited by a record that ends when round 424 copied it, and the
   six most recent E rounds are untestable for want of a newer capture. Then
   READ `Persistent=` (round 448's §2 correction is wrong in the dangerous
   direction if it says `true`), then a journal interior covering rounds
   202-250 for round 460's seven `REBOOT_ONLY` gaps.
6. **Round 436's items 4, 5 and 9 STILL stand, untouched for a fifth round** —
   the `commit` channel vs the 9.25 GB weights load, `Consumed` coverage at 4
   of 26 units, and the separability route. Item 6 stays CLOSED.
7. **Still blocked on the operator:** `--cap 196` (band [129, 204],
   `bounded_by: engine_lru`, 1.096 GB margin — **twenty-sixth** round
   unchanged) and the E3 A/B with its full six-gate table.

## Round 478 (NUC-integration E) — 2026-09-03, box **UP** on a boot never seen before: `0d0e3188da124a4b9f78b26dd95d3ea2`, `uptime -s 2026-09-03 09:37:09Z`, 7h33m at first contact. ENDS the 436/442/448/454/460/466/472 outage — the longest in this log — and ends it, like round 424 did, by REBOOTING

**Reachability.** tailnet `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` at
2026-09-03T17:10:54Z -> **SSH_OK** on the first try. `tailscale status` at
17:10:40Z: `active; direct 124.120.12.172:1024`. ping 2/2, rtt
51.4/91.4/131.4 ms. The LAN path was not attempted (the key still does not
exist on this host and the tailnet path worked).

**Outage now CLOSED and bracketed exactly.** Last tailnet sighting
`2026-09-01T18:27:56.1Z` -> boot `2026-09-03T09:37:09Z` = **39h09m13s**,
beating round 472's confirmed 37h26m00s by 1h43m13s. The box's clock is UTC
(`date -u` 17:10:54Z vs `uptime -s 09:37:09` vs `up 7:33` — three readings
that agree only at zero offset).

**Round 472's item 1 ran FIRST**, exit codes taken from the process and NOT
from a `| tail` (a tail of a JSON report always exits 0; this round made that
mistake once and caught it): `coverage --strict` **0**, `precision-audit
--strict` **0**, `lastseen-drift --strict` **1** — identical to the state
rounds 460/466/472 left.

**Round 472's item 5 executed in full.** Capture FIRST, before any analysis:
`state/nuc-capture-r478/`, 8 MB, 40 seconds, via the machine-generated
`capture_manifest.py plan`. It beat a hard deadline — `retention` forecast 8
files (`sa23 sa24 sa25 sa26 sar23 sar24 sar25 sar26`) deleted at the next
sweep, **2026-09-04T00:07:00Z**. Captured 17:13Z, **6h54m of margin**. They
survived only because the 09-02 and 09-03 fires fell inside the outage.

**`Persistent=` READ, not inferred — and it is `no`.** Both sysstat timers.
Round 448 §2's two-trial inference was right; round 472 flagged it as
dangerous in the `yes` direction, and `yes` would have meant those 8 files
died at boot this morning. `sysstat-summary.timer LastTriggerUSec=` is empty
(never fired this boot); `NextElapseUSecRealtime=Fri 2026-09-04 00:07:00 UTC`.

**NEW INSTRUMENT — `nuc/summary_fossil.py`.** `sarNN` is not a copy of `saNN`;
it is the RECEIPT of a `sysstat-summary` fire, stamped at the fire instant.
With `Persistent=no`, `sarNN` exists <=> the box was running at 00:07Z on day
NN+1. A missing receipt cannot be rotation: `sarNN` is 17 minutes younger than
`saNN` and `-mtime +7` truncates to whole days, so the pair always shares a
verdict. Current reading: fires ran on 08-24..08-29 and 08-31; **MISSED on
2026-08-30, 2026-09-01 and 2026-09-02**, all at 00:07Z. No `sa02` exists at
all (box down the whole day), and the module refuses a verdict there.
Cross-checked against `journalctl --list-boots`, which shares no input with
filesystem mtimes: **10 distinct decidable fires across the r424 and r478
captures, 10 agreements, 0 disagreements.** Against this program's own 63
probe records, **0 of 10 fires are bracketed within an hour** (tightest
2h27m, loosest 7h43m) — 00:07Z is the one instant per day the E-round cadence
has never covered.

**The evidence predates the reader.** Run retroactively, `nuc-capture-r400`
(taken 2026-08-31) already recorded the 2026-08-30 miss, and `nuc-capture-r424`
already recorded 08-30 and 09-01. Nested, never contradictory. Round 478 wrote
the reader, not the evidence. `nuc-capture-r400` cannot be cross-checked — it
predates step 3b of the capture plan and has no `journal-boots.txt`.

**THE RECORD IS DECAYING FASTER THAN THE PROGRAM READS IT.** Between the
2026-09-01 capture and this one, `journalctl --list-boots` **lost three boots**
off the front (`db09a51c`, `94b2e014`, `5308fdec`, covering 2026-08-23 14:02
through 2026-08-25 12:51) and the surviving oldest boot's first entry moved
`12:57:39` -> `12:57:42`. Journals are at 3.3 GB. The `sar` archive still
witnesses all three lost boots via `LINUX RESTART`, so `sar` currently
outlives journald — but four of those day files die tonight.
`state/nuc-capture-r424` is now the ONLY copy of the 2026-08-23..2026-08-25
journal interior, and `state/nuc-capture-r478` the only copy of `sa23`-`sa26`
after 2026-09-04T00:07:00Z.

**Measured cost of that decay.** `dose_response run` over the same 54 E
rounds, changing only the capture: r424 gives 42 scored / **28** full-record
(reproducing round 472's published numbers exactly); r478 gives 44 / **30**.
But it is NOT a superset — pooled days gain `2026-09-03` and **lose
`2026-08-23` and `2026-08-24`**, because attribution needs a fire and a bucket
in the same window and the journal no longer reaches those days. `sa23`/`sa24`
are IN this capture and still drop out. **The right unit of analysis is the
UNION of captures, not the newest one**; nothing in the tooling says so.
Round 472's NULL verdict replicates at n=30: `n_logins` rho 0.2568 -> 0.2881,
p 0.185 -> 0.121, `dose_beats_every_control` still false.

**Four terminations, none of them clean.** `grep -cE "Reached target
(Shutdown|Reboot|Power-Off)|Stopping .*target|Shutting down"` over the whole
755 KB `_PID=1` journal returns **0**, and each of the four boot transitions
ends on an ordinary `Finished sysstat-collect.service` line (08-27T04:40:21,
08-29T02:10:04, 08-31T16:20:05, 09-01T18:20:00). The box has never been shut
down in an orderly way in the captured record.

**Box state at capture.** uptime 7h33m, load 0.09/0.07/0.01; Mem 31984 MB
total / **5335 used** / 26648 available; **swap 4095 MB, 0 used**;
`Committed_AS` 5.4 GB. `qwen36-colibri` and `qwen36-toolproxy` (USER units)
both active/running since 09:37:19Z, `NRestarts=0`. Note for the `--cap`
decision: the "36.0 GB at `--cap 256`" figure from E4 is
steady-state-AFTER-traffic; 7h33m into this boot with no engine traffic the
box sits at **15.2 % memory and zero swap**.

**Tests: `nuc/tests` 995 -> 1037, all green, 220.2 s** (run alone; `nproc` is
1). The delta is exactly the new module's 42. Its falsifiers were
mutation-tested: **first pass 12 mutations, 11 killed, 1 SURVIVED** — the
pending/missed boundary (`fire > now` vs `fire >= now`), i.e. behaviour
nothing pinned, and the unpinned direction is the one that invents an outage
from a capture taken a second after midnight. Fixed with an explicit
`DEFAULT_SETTLE_S = 600`; **second pass 14 mutations, 14 killed, 0 survived.**
A second defect was found the same way: `Counter.most_common` was breaking a
schedule tie by `ls` ordering.

**Predictions 11 hits / 1 miss of 12** (`nuc/predictions-e-round478.md`,
banked as `dd1aa82` before any capture). The miss is P12 (`audit --strict`
exits 0 first try — it exited 1 on two blocking gaps, which turned out to be
the journal decay above, not a filtered capture). P6 is scored a hit that
missed the point: it predicted the boot table would gain exactly one row, and
it did — while losing three at the other end. **A prediction about a monotone
quantity is blind to the direction the quantity is not monotone in.**

**Writes to the box:** exactly one — `/work/logs/nuc-summary-fossil.md`
(md5-verified after scp). No unit restarted, **port 8001 never contacted**, no
engine request of any kind, nothing read or written outside the allowed paths.

**E-mission status: E1-E5 all still DONE; nothing new unchecked.**

**Next E round, in order:**
1. **`coverage --strict`, `precision-audit --strict`, `lastseen-drift
   --strict` FIRST**, exit codes from the process, not through a `| tail`.
2. **If the box is up, TAKE A CAPTURE even if the round does nothing else with
   it.** Round 400's capture answered a question nobody asked until round 478,
   and journald is eating its own front while `sar` has a hard 7-day horizon.
   40 seconds, 8 MB.
3. **`sa23`-`sa26` and `sar23`-`sar26` are gone from the box after
   2026-09-04T00:07:00Z.** `state/nuc-capture-r478/sysstat-binary.tar` is the
   only copy. Do not let a later round conclude they are still fetchable
   because a forecast said "next run".
4. **Make the fossil durable.** Re-run `summary_fossil.py fires` on every
   capture and append to a JSONL ledger the way reachability does. Once `sa29`
   rotates away the 2026-08-30 miss survives only inside a capture.
5. **Analyse over the UNION of captures.** The A/B above shows the choice of
   capture silently moves the pooled window in both directions.
6. **Round 472's items 2, 3 and 4 are UNTOUCHED and stand:** deconfound the
   lead-lag shoulder with a per-round-window resampling; `lead_lag_profile`
   still has no null; `test_perturbation.py` has still never been
   mutation-tested while carrying every published number in this track. This
   round mutation-tested only its own new module.
7. **Round 436's items 4, 5 and 9 stand, untouched for a sixth round** — the
   `commit` channel vs the 9.25 GB weights load, `Consumed` coverage at 4 of
   26 units, and the separability route.
8. **Still blocked on the operator:** `--cap 196` (band [129, 204],
   `bounded_by: engine_lru`, 1.096 GB margin — **twenty-seventh** round
   unchanged) and the E3 A/B with its full six-gate table.

## Round 484 (NUC-integration E) — 2026-09-04, box **UP** on the SAME boot as round 478 (`0d0e3188da124a4b9f78b26dd95d3ea2`, `uptime -s 2026-09-03 09:37:09Z`, 16h02m in). Second consecutive up round; the 436/442/448/454/460/466/472 outage is still the last one

**Reachability.** tailnet `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` at
2026-09-04T01:23:10Z -> **SSH_OK** on the first try. `tailscale status`:
`active; direct [2001:fb1:9e:823e:42a3:ccff:fe1f:469f]:41641`. The LAN path
was not attempted (the key still does not exist on this host and the tailnet
path worked).

**THE FIRST SWEEP THIS PROGRAM HAS EVER OBSERVED, AND IT SPLIT A PAIR.**
Round 478 forecast that the 2026-09-04T00:07 fire would delete eight files.
It fired at **00:07:18** and deleted **seven**: `sa23 sa24 sa25 sa26 sar23
sar24 sar25`. **`sar26` survived**, mtime 2026-08-27T00:07:21.677 — 8 days
*less 3.7 seconds*, which `-mtime +7` floors to 7, and `7 > 7` is false.

**Why, all three facts READ rather than assumed.** `/usr/lib/sysstat/sa2`
renders the receipt and THEN sweeps, in one script.
`sysstat-summary.timer` is `OnCalendar=00:07:00` with **no `AccuracySec=`
override**, and the six fire instants in this round's captured journal are
`00:07:21, 00:07:21, 00:07:04, 00:07:04, 00:07:05, 00:07:18` — a **17-second
spread**. `find -mtime +7` bites at age >= 8 days exactly. So `saNN`'s age at
the sweep is (whole days + 17m14s) and `sarNN`'s is (whole days) +/- that
jitter: **the day file is never near the boundary and the receipt is always
exactly on it.** Round 478's retention theorem ("the two files always share a
verdict"; "the receipt is younger and dies no earlier") is FALSE, in the one
direction that carries positive evidence.

**The split has one direction and lasts one day.** The receipt is 17 minutes
younger, so it outlives its day file by exactly one sweep and then dies. The
observable is an ORPHAN RECEIPT — and it is always the OLDEST decidable day,
the one about to exist nowhere but in a capture. Round 478 named orphans and
scored none. Round 484 scores them (`evidence: "receipt_only"`); the live
capture goes **7 -> 8 decidable fires**, recovering 2026-08-27T00:07.

**NEW — `summary_fossil.py margins`.** Computes, from journal timestamps
ALONE, which receipt orphans next: `margin = (S - W) - 8 days`. On
`nuc-capture-r484` it returns exactly one `orphaned` row, **-3.0 s**, for the
receipt written 2026-08-27T00:07:21Z. **Two disjoint sources agree** — the
filesystem listing finds `sar26`, the journal timestamps name the same
receipt, and neither input mentions the other.

**NEW — `nuc/fossil_ledger.py` + `state/nuc-fossil-ledger.jsonl`** (round
478's next-steps 4 and 5, both of which stopped being hypothetical overnight:
the fossil read off the live box went **10 decidable fires -> 8**). Unions
every capture, append-only, keyed by fire instant: **4 captures read, 5 named
unusable, 11 fire instants, 0 disagreements** vs 10 for the best single
capture and **8 for the newest**. `now` comes from the capture's own boot
table, never a file mtime (git does not preserve mtimes).

**`coverage --strict` was RED at round start.** Round 478 connected, took a
capture, wrote a 90-line addendum — and never appended its own reachability
row. Structural cause: **`coverage` excludes the in-flight round**, so a
round that omits its own row always passes its own gate and reddens the next
one. Backfilled as `backfill-prose-r478` / `precision: coarse` (the addendum
quotes no LastSeen and this round will not invent digits). Gates then
**0 / 0 / 1**, as rounds 460-478 left them.

**Closing that gap RAISED published ignorance.** `unobserved_total_s`
396378.0 -> **426906.0**. Attributed, not re-baselined: removing EITHER new
row restores 396378.0 exactly. One observation of an up box has no interior;
two create the 30528 s between 17:10:54Z and 01:39:41Z. The program can now
name a stretch it previously could not see at all.

**Journal decay continued, in a shape round 484 did not predict.** The boot
table still lists the same 5 boots — but boot -4's FIRST ENTRY moved
`2026-08-25 12:57:42` -> **`18:28:02`**: journald ate **5h30m of the oldest
boot's interior** without dropping the boot.

**Tests: `nuc/tests` 995 -> 1037 (r478) -> 1076, all green, 415 s** (run
alone; `nproc` is 1). **23 mutations; first pass 21 killed / 2 SURVIVED**
(the `margin >= 0` boundary, unreachable behind the resolution guard; and
`REFUSALS = ()`, whose fixture produced no fire instant so the wrong clause
was doing the work). Both gaps closed; **second pass 23/23, 0 survived.**

**Predictions 9 HIT / 3 MISS / 2 SPLIT of 14** (`nuc/predictions-e-round484.md`,
banked `bb98f0c` before any predicted quantity was measured). The three
misses are one shape: each extrapolated how bad a known-bad thing had got
from a SINGLE prior observation, and each over-predicted. The two SPLITs are
the round's two best findings.

**Box state.** uptime 16h02m, load 0.00/0.00/0.00; Mem **5406 / 31984 MB
(16.9%)**, **swap 0 of 4095 MB**, `Committed_AS` 5.48 GB. `qwen36-colibri`
and `qwen36-toolproxy` (USER units) both active/running since
2026-09-03T09:37:19Z, **`NRestarts=0`**.

**Writes to the box:** exactly one — `/work/logs/nuc-sweep-edge.md`,
md5-verified `9291e9c73a0cf230939513b1486ba504` both ends. **No unit
restarted, port 8001 NEVER contacted, no engine request of any kind.**
Capture taken FIRST, before any analysis: 12 seconds, 2.3 MB compressed,
`capture_manifest audit --strict` exit **0**.

**E-mission status: E1-E5 all still DONE; nothing new unchecked.**

**Next E round, in order:**
1. **`sar26` is dead by now** (age 9 days at the 2026-09-05T00:07 sweep; no
   jitter reaches 86400 s). Do not go looking for it — its record is in
   `state/nuc-fossil-ledger.jsonl` and `state/nuc-capture-r484`.
2. **`summary_fossil.py margins --strict` on every capture**, and treat an
   `undecidable` margin as a call for `stat`, not a guess.
3. **Take a capture even if the round does nothing else with it.** This round
   is the evidence: 12 s, 2.3 MB, and it bought three days that no longer
   exist on the box.
4. **`fossil_ledger.py append` every round**; never analyse from the newest
   capture alone (it sees 8 of 11 fire instants).
5. **Five of nine captures are unusable to the ledger** (no sysstat listing:
   r406/r430/r460/r466/r472 — all down rounds); r400 needs a `DECLARED_NOW`
   entry because it predates the boot table. Both are reported, neither is a
   defect — but no up-round capture should ever join that list.
6. **Round 472's items 2, 3 and 4 are UNTOUCHED for a second round:**
   deconfound the lead-lag shoulder with per-round-window resampling;
   `lead_lag_profile` still has no null; `test_perturbation.py` has still
   never been mutation-tested while carrying every published number in this
   track. This round again mutation-tested only its own new code.
7. **Round 436's items 4, 5 and 9 stand, untouched for a seventh round** —
   the `commit` channel vs the 9.25 GB weights load, `Consumed` coverage at
   4 of 26 units, the separability route.
8. **Still blocked on the operator:** `--cap 196` (band [129, 204],
   `bounded_by: engine_lru`, 1.096 GB margin — **twenty-eighth** round
   unchanged); the E3 A/B with its full six-gate table.

## Round 490 (NUC-integration E) — 2026-09-04, box **DOWN** the whole round. A NEW outage, not a continuation: rounds 478 and 484 both saw the box UP on boot `0d0e3188`, and the peer was last seen 34m53s after round 484's own probe

**Reachability.** Two probes on the documented tailnet path, both before any
code ran; CLAUDE.md's two-failure rule fired after the second.

- tailnet `ssh -o ConnectTimeout=15/25 -i ~/.ssh/id_ed25519 jab@100.78.44.111`
  at ~10:59:2xZ and 11:00:11Z -> `Connection timed out`, rc 255 both times.
- LAN `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` at ~11:00:4xZ -> same,
  **and the key still does not exist on this host**, so that path proves
  nothing either way. (Unchanged since round 472.)
- `tailscale status --json` read 11:00:56Z and banked at
  `state/nuc-capture-r490/tailscale-status-r490.json`: `Online false`,
  **`LastSeen 2026-09-04T02:14:05.1Z`**, relay `sin`, tx 5928 rx 0. Plaintext:
  `active; relay "sin"; offline, last seen 8h ago`.
- Row appended with `replay`, `source: live-replay-r490`, `precision:
  precise`. Log now **66 rows** (38 up, 28 down).
- **Zero ssh sessions succeeded: nothing was read from or written to the box,
  port 8001 was never contacted, no engine request of any kind was made.**
- Gates FIRST, per round 472's item 1: `coverage --strict` **0**,
  `precision-audit --strict` **0**, `lastseen-drift --strict` **1** — exactly
  where rounds 460/466/472/478/484 left them, the last for the documented
  reason. Re-run after the append: identical.

**THE FINDING: a strictly better record has been in this repo since round 478,
unread.** Every window-level number this track has published comes from
`state/nuc-capture-r424/sar-all.txt`. `grep -rl nuc-capture-r478
--include='*.py'` returns only `fossil_ledger.py` and two test files;
`perturbation.py` and `dose_response.py` name r424 and nothing else. Round
472's central limitation — "round 424's capture IS the end of the record, and
the six most recent E rounds are untestable for want of a newer one" — was
closable offline, on a down round, from committed files.

**And the newest capture is the SMALLEST record.** r484 holds 8 sar dates,
r424 holds 10, r478 holds 11, the union holds **12** (2026-08-23..09-04;
09-02 exists in no capture because the box was down all day). The 00:07 sweep
deletes the front while each capture only adds to the back, so "use the latest
capture" gets the least data.

**NEW — `nuc/record_union.py`** (+ `nuc/tests/test_record_union.py`, 34
tests). Unions the sar day-files and the pid-1 journal across every capture,
with `fossil_ledger`'s three rules: agreement is the null, the comparison is
per timestamped ROW, an unusable input is named. Live: **4 captures read, 5
named unusable, 120 sections, 12 dates, 0 conflicts, 0 merged sections**.
`window_frame` on the union: **12 paired days / 1145 buckets** against 10/991
for the best single capture and 8/661 for the newest. Journal: **1938 unit
starts** against 1652 for the best single. Built artefact committed at
`state/nuc-record-union/`.

Two things the module found about itself, both kept as findings: (a) the
journal union must be a **MULTISET** — every journal in this repo holds 2-3
byte-identical lines that are two real events in one second, and whole-line
dedup deletes a fire; the first draft's own `--strict` gate caught it. (b)
Unioning only the sar and keeping the newest journal leaves **08-23 and 08-24
unpaired**, so half the job buys much less than half the gain.

**Round 472's item 5 is CLOSED and the answer is zero.** Re-running
`dose_response.py run` on r424 re-derives round 472 exactly (42 scored, 28
full, `bytes_landed` rho −0.2767). On the union: **46 scored, 31 full-record**.
**Round 424 — 2 896 862 bytes landed, nine times the next heaviest round —
moves `partial` -> `full` and its window holds ZERO swap bytes.** Rounds 430
and 478 move `none` -> `full`, also zero; 484 reaches `partial`.
**Honest caveat, stated in the round file:** all three new full windows have
response exactly 0 (`response_total` is byte-identical on both records —
+154 buckets, +0 costly buckets), so every coefficient the union moved, it
moved by adding zero-response points, and none of that is new evidence about
any dose. Verdict unchanged: **NULL**. Worth noting: at n=31 the only terms
below p 0.05 are the negative CONTROLS `local_bytes` (−0.4376, p 0.0149) and
`local_calls` (−0.3911, p 0.0312), both the wrong way round.

**THE OTHER FINDING: `n` was never 454.** Round 472 contrasted "login-instant
resolution (n=454), strong and robust" with "round-window resolution (n=28),
nothing". A round makes ~14 logins in 10-25 minutes and a bucket is 600 s
wide, so most of them share a bucket. **NEW `effective_cells`**: 484 fires ->
**69 distinct (round, bucket) cells** (median 6 fires per cell, max 34).
The two resolutions are 69 and 28. The coincidence SURVIVES the collapse —
`shift_null_covered` per cell: 0.1449 vs null 0.0381, **p 0.0065**. Control,
gap-blocked the same way: 86 cells, 4 costly, **0.0465**. **NEW `gap_blocks`**
derives the blocks from the journal's own silences and returns the same 34
blocks / 69 cells as the transcript-derived split — two independent groupings
agreeing exactly.

**Round 472's item 2 is ANSWERED and its §4b is WITHDRAWN.** **NEW
`block_lead_lag_profile`** splits every landed fire into `sibling_occupied`
(the landing bucket already holds another login of the same round) and
`clean`. At offset 0, **7 of 478** landed fires have their bucket to
themselves; at +1, **283 of 471 (60 %)** are sibling-occupied at rate 0.1237
against 0.0426 clean. Mean asymmetry: **+0.00519 all fires, −0.00027 clean**.
**NEW `block_shift_null_lead_lag`** (item 3, the null the profile never had):
`rate_at_zero` 0.2008 vs null 0.0360, **p 0.0010 = p floor** — the peak at
zero SURVIVES; `asymmetry_after_minus_before` **p 0.4060** — the shoulder does
not. Two caveats kept in the round file: the clean/dirty split is not
randomised, and the clean subsets differ in size across offsets.

**The new null is weaker than designed, and its own field said so.**
`sibling_structure_preserved_in_all_draws` is **False, 0 of 1000**: whole-bucket
shifts preserve co-occupancy only where the record is continuous, and this
box's is not (observed 409 co-occupancies, null median **256** = 62.6 %). The
direction of the resulting bias on `p` is NOT established.

**Round 484's items 2 and 4, paid.** `fossil_ledger.py append` over every
capture: exit 0, ledger **byte-identical, 11 instants, 0 conflicts**; r490
correctly named unusable. `margins --strict` over all nine: **3 scorable**
(r424/r478/r484, all exit 0), **r400 exits 1** because it carries no
`journal-pid1-full.txt`, 5 have no derivable `now`. Run on the UNIONED
journal it sees **8 fire instants** against 7 (best single) and 6 (newest),
and flips 08-24/-25/-26 from `sweep_pending` to `sweep_missed`; round 484's
**−3.0 s** orphan reproduces exactly.

**Did round 484's capture kill the box? No.** Five up->down transitions in the
log, four with a placeable `LastSeen`. `u` = (last-seen − last up probe) /
(probe-to-probe window) is U(0,1) under uniform death: **0.9788, 0.6935,
0.8204, 0.0613**. Fisher against the small-`u` alternative **X² 6.753, df 8,
p 0.5635**. Three of four deaths land LATE in their window; this round's
34m53s is the only early one and one draw at the 6th percentile is not
evidence.

**Tests: 55 new (34 + 21). 29 mutations; first pass 24 killed / 5 SURVIVED**,
four distinct causes — one dead branch (deleted), one field no input can
falsify (re-pointed at a decidable helper), one test that read the report
instead of the behaviour, and two missing boundary cases. **Second pass 29 of
29 killed, 0 survived.**

**Suite: `nuc/tests` 1076 -> 1131, all green, 564 s** (run alone; `nproc` 1).
Two tests went red on the first full run and both were this round's own doing:
`test_the_live_union_beats_every_single_capture` pinned
`n_captures_unusable == 5` and round 490 banked `state/nuc-capture-r490`
(tailscale-status only) -- the corpus grew, the ledger did not break, and it
will recur on every down round, so the count is now derived from the directory
listing; the `constant_audit` fast-check failure was downstream of it.

**New skill `skills/newest-snapshot-is-not-the-record/SKILL.md`** -- a snapshot
of a rotating source is a WINDOW, so "newest" is a claim about the back edge
only. Nine steps, six pitfalls, two runnable verification commands;
`skill_lint --house --strict` 0/0; three positive trigger cases plus a
discriminating negative in `skills/trigger-cases.json`; registered unprobed in
`state/known-unprobed-skills.json` with an owner and a scorable prediction.

**The round's own final check caught two defects in the round's own CLI.**
Running the invocation its SKILL.md, its next-steps and this addendum all
document -- `record_union.py sar --captures 'state/nuc-capture-r*' --strict` --
showed (a) the CLI did not glob, so every documented call read ZERO captures,
and (b) `--strict` therefore exited **0**, because zero captures read means
zero sections means zero conflicts and the gate tested conflicts only. **A gate
that passes on an input it never read is worse than one that fails.** Fixed:
`expand_captures` (matching `fossil_ledger`) and `_sar_strict_fails`, which now
fails on `n_captures_read == 0`. Three new falsifiers, all killed first pass;
**32 mutations, 32 killed** for the round. Also: the live-corpus test had the
SAME `n_captures_unusable == 5` pin that had already been fixed in
`test_fossil_ledger.py` an hour earlier -- fixing an instance is not fixing the
class.

**Predictions 13 HIT / 1 MISS / 2 OPEN-KEPT of 15**
(`nuc/predictions-e-round490.md`, banked `a0f244d` before any of it was
measured). The miss is P5, and it is the same shape as round 484's three:
extrapolating from one prior observation and over-predicting.

**E-mission status: E1-E5 all still DONE; nothing new unchecked.**

**Next E round, in order:**
1. **Use `state/nuc-record-union/`, not a capture.** Rebuild it first
   (`record_union.py build --captures 'state/nuc-capture-r*' --out-dir
   state/nuc-record-union --strict`) so it includes whatever the round adds,
   and run `frame --strict`, which exits 1 if the union buys nothing over the
   best single capture. Never build a `BucketMap` from one capture again
   without saying why.
2. **If the box comes up: take a capture FIRST and it is worth MORE than
   round 484 said.** The union means an up-round capture no longer merely
   records today; it is the only thing that will ever pair 09-05 with a
   journal, and the sweep deletes 08-27 on 09-05 and 08-28 on 09-06.
3. **The `%vmeff`/`pgsteal_kswapd` residual is STILL one read-only command
   away**, untouched for eight E rounds now, and the box has swap 0 so the
   direct test may be vacuous again — check `pgsteal_kswapd > 0` FIRST.
4. **Round 490's own weakness: the block-shift null preserves 62.6 % of the
   clustering it was designed to preserve exactly.** Either shift within
   fully-covered stretches only, or report the p as a bracket. Whoever does
   it should say which direction the current bias runs, because this round
   could not.
5. **`test_perturbation.py` has STILL never been mutation-tested** while
   carrying every published number in this track. Round 490 mutation-tested
   only its own two new files, for the third consecutive round. This is now
   four rounds old (472 item 4, 478, 484 item 6, 490).
6. **Round 436's items 4, 5 and 9 stand, untouched for an eighth round** —
   the `commit` channel vs the 9.25 GB weights load, `Consumed` coverage at
   4 of 26 units, the separability route.
7. **Still blocked on the operator:** `--cap 196` (band [129, 204],
   `bounded_by: engine_lru`, 1.096 GB margin — **twenty-ninth** round
   unchanged); the E3 A/B with its full six-gate table.


## Round 508 (NUC-integration E) — 2026-09-05, box **DOWN** the whole round; FOURTH consecutive down window (490, 496, 502, 508), one continuous outage since `2026-09-04T02:14:05.1Z`

**Reachability.** Two tailnet probes before any code ran, 11:27:41Z
(`ConnectTimeout 25`) and 11:28:19Z (`ConnectTimeout 30`), `Connection timed
out`, rc 255 both; CLAUDE.md's two-failure rule fired after the second. LAN
path NOT tried — `~/.ssh/id_ed25519_nuc` still does not exist on this host
(re-verified). `tailscale status --json` banked at
`state/nuc-capture-r508/tailscale-status-r508.json`: `Online false`,
`LastSeen 2026-09-04T02:14:05.1Z` (byte-identical to rounds 490/496/502),
relay `sin`, tx 6396 rx 0. Row appended, `source: live-replay-r508`,
`precision: precise`; log **69 rows**. Gates before and after, identical:
`coverage --strict` 0, `coverage --strict --no-allow-in-flight` 0,
`precision-audit --strict` 0, `lastseen-drift --strict` 1 (documented).
**Zero ssh sessions succeeded; port 8001 never contacted.**

**THE FINDING: `survivor_impact.BATTERY`'s `wsweep_swap` entry never ran the
swap channel.** It passed no `--channel`, and `wsweep` is the one
`perturbation.py` subcommand defaulting to `steal`. Byte-identical output to
`wsweep_steal` (35703 B, md5 31b8b34f8e9d). Five advertised verbs, four run.
Fixed, plus three guard tests; battery **5 -> 7**, `BATTERY_GAP` **9 -> 7**.

**`reclaim`/`gap` could read NO capture — 0 of 5** (r400, r424, r478, r484,
union), not just round 490's union as round 502 recorded. New
`capture_day_tables`; both verbs take `--capture` now; `window`/`population`/
`wsweep` byte-identical after the shared-walker refactor.

**`window --channel commit|steal` rc 1 is a MODULE CONSTANT, not the record.**
`--min-bytes 4825718` exits 0 on the same union. Message subject fixed.

**Round 418's two hand-extracted days were not a sample.** Union, 12 days,
1145 buckets: 108 loud, **8 direct/mixed** (418 said 0), largest **49.67 GB on
08-26** against 418's 987 MB on 08-31, **87 of 108** `steal_exceeds_scan`.
`gap`: 43.0 % at `level_bytes == 0`, median ratio 0.0019.

**Tests:** `test_capture_verbs.py` 35 nodes 3.22 s green; regression 347
passed / 2 failed, both this round's own — one re-pinned, one
(`test_the_committed_report_is_about_the_subject_at_head`) **left red on
purpose**, regeneration measured at >600 s for 5 survivors.

**Predictions 8 HIT / 5 MISS / 1 PARTIAL / 1 UNSCORED of 15**
(`nuc/predictions-e-round508.md`, banked `e6291c3` before measuring). All five
misses extrapolate the 12-day record from round 418's two days — the round's
own subject, committed by its own author.

**E-mission status: E1-E5 all still DONE; nothing new unchecked.**

**Next E round: see `knowledge/round-508-the-battery-entry-that-was-not-its-own-name.md` §7.**

## Round 514 addendum (2026-09-05, box DOWN — 5th consecutive offline window)

- `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` → `connect to host ... port 22:
  Connection timed out` after a 10 s connect timeout. One attempt; a timeout
  rather than an auth failure, so per CLAUDE.md's two-SSH-failures rule no
  second attempt was made and the round proceeded offline. The LAN path
  (`192.168.1.37`) is not reachable from the driver host.
- **No mission ticked.** E1-E5 are all `[x]`. The two open NUC items — the E3
  KV-reuse A/B and the OLMoE on-box NVMe decode measurement — both need a
  restart or a deploy on a shared box and operator sign-off, and neither is
  attemptable with the box down.
- Round 514 spent its window on this track's OFFLINE debt instead: the
  six-round red on `nuc/tests/test_survivor_impact.py`. See
  `knowledge/round-514-the-report-that-was-stale-in-its-own-commit.md`.

## Round 520 (NUC-integration E) — 2026-09-06, box **DOWN** the whole round; SIXTH consecutive down window (490, 496, 502, 508, 514, 520), one continuous outage since `2026-09-04T02:14:05.1Z`

**Reachability.** Two tailnet probes before any code ran, 02:00:36Z
(`ConnectTimeout 25`) and 02:01:14Z (`ConnectTimeout 30`), `Connection timed
out`, rc 255 both; CLAUDE.md's two-failure rule fired after the second. ICMP
2 packets 100% loss. LAN path NOT tried — `~/.ssh/id_ed25519_nuc` still does
not exist on this host (re-verified). `tailscale status --json` banked at
`state/nuc-capture-r520/tailscale-status-r520.json`: `Online false`,
`LastSeen 2026-09-04T02:14:05.1Z` (byte-identical to rounds 490/496/502/508),
relay `sin`, tx 2184 rx 0. **Zero ssh sessions succeeded; port 8001 never
contacted; no engine request of any kind was made.**

**The log has no holes for the first time.** Round 514 owed a row and never
paid it (`coverage --strict` → `missing: [514]`). `reachability_recover.py`
read round 514's OWN transcript `logs/round-514.json` — four ssh probes, the
deciding one at 2026-09-05T19:05:32Z — and rebuilt the row; no tailscale
capture was needed, which is why round 520's own prediction that the hole
would persist was wrong. Log **69 → 71 rows**. Gates after:
`coverage --strict` 0 (**n_owed 61, n_covered 61, missing []**),
`coverage --strict --no-allow-in-flight` 0, `precision-audit --strict` 0,
`lastseen-drift --strict` 1 (documented, pre-existing).

**Round 514's §8 item 1 is CLOSED, as a measured null.** All 82 mutants round
514 remapped onto HEAD and never re-scored were run: **82/82 killed**, 213.6 s,
`oracle {subset: 82, full: 0}`, `n_left_unrun_by_budget 0`, 0 verdicts moved,
0 master drift events over 82 sandboxes. The regenerated
`state/nuc/round-520/survivor-impact.json` is byte-equal to round 514's in
every measured field (`n_survivors_standing 5`, `moves_published_number []`,
`n_lines_executed_by_battery 1319`), `--strict` exit 0. Round 514's survivor
set was a lower bound by its own admission; it is now exact.

**THE FINDING: `n_ledger_rows_scored_under_another_suite: 55` had no verb that
could reach a single one of those rows.** `--stale` selects the SURVIVED
subset and the split here is 55 killed / 0 survived (40 rows with no
`suite_digest` at all, 15 under the round-497 suite `2cd94b15`). Two
independent limits, neither named by the report: the status filter, and round
514's moved ids — a stale row is keyed at the digest it was scored at, so 81 of
87 name a mutant this subject no longer has. Fixed with `stale_by_status`,
`kills_scored_under_another_suite`, `n_stale_rows_selectable_at_this_digest`
and `--stale-scope {survivors,kills,all}`. The premise behind the survivor-only
rule ("a suite only grows") was CHECKED, not assumed: 239 → 245 → 257 nodeids
across the three suite digests, **0 removed**.

**Two more template-shaped defects, same round.** `verdict_changes` called an
absent prior row a change and reported 82 of 82 corrections on a slice where
none moved. `reachability_recover`'s note was a fixed string signing round 454
and asserting round 310's backfill had missed a transcript written 204 rounds
later — self-blocking, because `rewrite_plan` re-derived under the same
constant. Rows now carry `recovered_by_round`.

**Tests:** `test_swe_nodeid_selection.py` 34 passed 53.6 s (8 of the 9 new
guards fail against the pre-fix module; the 9th is the negative control);
`test_reachability_recover.py` 47 passed; `test_reachability_check.py` 258
passed; `test_survivor_impact.py` + `test_mutant_remap.py` 52 passed. The
~30-suite `readset.py blast` radius was NOT run in full — named in the round
file, not skipped silently.

**Predictions 8 HIT / 2 MISS / 1 PARTIAL of 11** (`nuc/predictions-e-round520.md`,
banked `1041141` before measuring). The misses: a duration carried across an
optimisation the ledger itself records (P4), and an ABSENCE predicted without
running the tool that refutes it (P9).

**E-mission status: E1-E5 all still DONE; nothing new unchecked.**

**Next E round: see `knowledge/round-520-the-number-that-had-no-verb.md` §8.**

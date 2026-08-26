# Round 136 — NUC-integration(E) — third live snapshot: swap finally moves off zero, one decode-under-pressure measurement

## 0. Context and inheritance audit

`state/nuc-missions.md` lists E1-E5 all `[x]` DONE (rounds 10-16, 22, 28,
100-112-124-130). `state/research-state.md`'s round log runs through round
130 (NUC/E); rounds 131-135 all ran and all died at `error_max_turns` (81
turns each, `logs/round-13{1..5}.json`, $2.79-$3.62 each). They are other
tracks' business (131 = SWE-loop campaign-snapshot bug, mostly finished per
its own knowledge file; 132 = language v0.13 Whence predictions; 135 =
skills haiku gte/tli saga) and are not chased here — consistent with round
130's own precedent of flagging out-of-track debt rather than re-deriving
it. Also observed, left alone: `languages/whence/` still carries the
uncommitted v0.13 return-type WIP (SPEC.md/ast_nodes.py/interp.py/lexer.py/
parser.py/values.py + untracked `tests/test_v13.py`), whence suite green on
arrival (see §4); `harness/swe/{campaign,fuzz,guest}.py` and two test files
are modified in the working tree (round 131's campaign-snapshot fix), also
green on arrival, also not this track's business.

The only genuinely open NUC(E) item is the round-130 addendum's "still
open, needs an operator decision": the E3 KV-prefix-reuse A/B and the OLMoE
on-box NVMe check, both blocked on a restart of the live, shared
`qwen36-colibri` service. Nothing in E's own backlog calls for new code
this round — E1-E5 are complete DSLs/harnesses; the only thing left to DO
is watch the box when it happens to be reachable and take read-only
measurements, which is exactly what rounds 124 and 130 already established
as the pattern for this track's "opportunistic live window" rounds.

## 1. The box was up a third time — same boot as rounds 124 and 130

`ping 192.168.1.37` (0% loss, ~48 ms) and
`ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37` both succeeded at 01:50 UTC.
`systemctl --user status qwen36-colibri` shows the SAME process as rounds
124/130 (`Active: active ... since Tue 2026-08-25 12:57:42 UTC`, main PID
1022, worker PID 1047, `--cap 256 --ctx 32768 --max-queue 2`), now at
uptime 12h53m — round 124 caught this exact boot/session at 3h13m, round
130 at 5h10m/5h18m. This is the third data point on one continuous
session, not three independent samples.

## 2. Third cgroup snapshot: swap moved off exactly zero

Full read via `systemctl --user status` + direct cgroupfs reads
(`/sys/fs/cgroup/.../app.slice/qwen36-colibri.service/memory.*`) + system
`free -h` / `swapon --show`. No `dmesg`/`journalctl` OOM-kill lines found.

| time (UTC) | uptime | memory.current | memory.max | swap.current | system MemAvailable |
|---|---|---|---|---|---|
| round 124, 16:11 (25-Aug) | 3h13m | 15.6 GiB | 30.0 GiB | 0 B | 21.6 GB |
| round 130, 18:08 (25-Aug) | 5h10m | 30.0 GiB (= max) | 30.0 GiB | 0 B | 1.12 GB |
| round 130, 18:16 (25-Aug) | 5h18m | 30.0 GiB (= max) | 30.0 GiB | 0 B | 0.73 GB |
| round 136, 01:51 (26-Aug) | 12h53m | 29.59 GiB | 30.0 GiB | **310.6 MB** | 1.0 GB |

Raw cgroupfs values at round 136: `memory.current=31772688384`,
`memory.max=32212254720` (exactly 30 GiB), `memory.swap.current=310603776`,
`memory.peak=32212254720` (equals `memory.max` — the cgroup has touched
its ceiling at least once since round 130's direct observation).
`swapon --show` confirms system-wide `297M` used of a 4.0 GiB swapfile,
matching the cgroup figure (this cgroup is effectively the only sizeable
memory consumer on the box). `memory.stat`'s `inactive_anon` reads 13.25
GiB — a large reclaimable-if-pressured pool still sitting in RAM, so swap
usage growing further from here would not be surprising.

**This answers round 130's own open question.** Round 130 measured the
ceiling being hit with swap still at literal 0 B across two snapshots 8
minutes apart, and hypothesized either "more elapsed time" or "a different
load mix" was needed to reproduce round 106's original 4.2 GB reading.
Given ~7-8 more hours on the identical boot/session, swap usage did move
off zero — confirming "more elapsed time" was sufficient by itself, no
different load mix required. It is still ~14x smaller than round 106's 4.2
GB figure, consistent with a slow, roughly monotonic swap-growth curve
once the ceiling is first touched, rather than a step-function jump; round
106's box had presumably been up for much longer when it took that
reading. No OOM kills at any point in this timeline — cgroup-v2's
reclaim-then-swap sequencing (round 130's finding) is managing the
pressure without killing the service, at least up to 310 MB of swap.

## 3. New measurement: does live inference degrade once swap is active?

Neither round 124 nor round 130 asked this question — both treated the
memory read as a static risk indicator. With swap now measurably nonzero,
this round ran one comparable point from the E1 curve directly against
`:8000` on the box itself (bypassing the Mac tunnel, to isolate NUC-side
cost from network/tunnel variance): `nuc/bench.py --sizes 300
--decode-tokens 64 --no-warmup --seed 136`.

| prompt tok | TTFT cold (s) | prefill tok/s | TTFT repeat/fresh ratio | decode tok/s |
|---|---|---|---|---|
| 307 | 58.65 | 5.23 | 0.99 | **4.30** |

- **Prefill/TTFT: no visible degradation.** E1's marginal-rate model
  (`TTFT = 2.4s overhead + tokens/5.1 tok/s`) predicts 62.6 s at 307
  tokens; measured 58.65 s is ~6% *under* that — the same "measured a
  touch faster than the simple model" pattern round 124's live warm
  requests already showed. Round 112's finding (prefill walks one
  page-cache-resident layer's worth of experts, ≤400 MB, comfortably
  fits even with `MemAvailable` at ~1 GB) explains why: prefill's working
  set is far smaller than what's actually under pressure.
- **repeat/fresh = 0.99** reconfirms E3's "no cross-request KV reuse"
  finding still holds on this exact live deployment regardless of memory
  state — consistent with round 28's read of `serve_one` resetting KV
  per request, a code-path fact unrelated to available RAM.
- **Decode is the one number that moved: 4.30 tok/s vs. E1's 5.3 tok/s at
  a comparable ~300-KV point — a ~19% drop.** This is the plausible
  place for a swap effect to show up, since round 112 already
  established decode as disk/cache-bound (it walks all 16 layers' full
  expert sets per token, a working set an order of magnitude larger than
  prefill's). Reported as **TENTATIVE, not confirmed**: this is a single
  measurement (n=1) with no fresh-boot control run in the same round to
  separate "swap is active" from ordinary decode-to-decode variance — E1's
  original 5.3 tok/s figure was itself measured once, on a boot whose
  memory-pressure state at measurement time isn't recorded. A clean test
  would need two identical-prompt decode runs on the same box: one
  shortly after a restart (low pressure, swap at 0) and one late in the
  same boot under active swapping — exactly the kind of before/after the
  next operator-approved restart would provide "for free" alongside the
  E3 A/B.

## 4. Standing regression checks

- `nuc/.venv/bin/python3 -m pytest nuc/tests nuc/taskscript -q`: **157/157
  passed** (23.3 s) — unchanged from round 130's count, no NUC-track code
  touched this round (this was a pure measurement round).
- Bare `python3 -m pytest nuc/tests nuc/taskscript -q` (no venv): 150
  passed / 2 failed / 5 skipped — both failures are the pre-existing
  `ModuleNotFoundError: tokenizers` gap flagged since round 130 (bare
  interpreter lacks the `tokenizers` package the venv has); not caused by
  this round, not re-flagged as new.
- Whence and harness suites not re-run this round (no language/harness
  code touched; round 130's numbers — whence 777/777, harness 448/448 —
  are the last recorded baseline and this round made no edits there).
- `skill_lint --house --strict skills/` not re-run — no skill touched.

## 5. Artifacts

- `/work/logs/nuc-fast-lane.md` (NUC) — "Round 136 addendum" section
  appended (third cgroup snapshot table + the decode-under-pressure
  measurement + the still-open operator-decision flag), verbatim source
  of §§2-3 above.
- `state/bench-r136.json` / `state/bench-r136.md` (this repo) — raw
  `nuc/bench.py` output for the single 300-token point.
- `state/nuc-missions.md` — "Round 136 addendum" section added under the
  round 130 one (same file, append-only pattern established there).

## 6. Not done, with reasons

- **No restart performed.** Both the E3 A/B and the OLMoE NVMe check
  still require restarting a live, shared, currently-serving-real-traffic
  process — a hard-to-reverse action on infrastructure round 130 already
  correctly deferred to the operator. This round's new argument (swap now
  nonzero and slowly growing) strengthens the case for restarting soon
  but is evidence to hand the operator, not authorization to act
  unilaterally. Flagged directly, not executed.
- **No predictions file banked.** Following round 130's own precedent
  ("none banked — the live window was opportunistic"): this was an
  unplanned live-window measurement round, not a fresh mission with a
  designed experiment: the only prior number to fail-check against was
  E1's single decode figure at a comparable KV size, and that comparison
  is reported directly in §3 rather than as a scored prediction.
- **Did not chase the decode-degradation question further** (e.g. a
  second decode run at a different prompt size, or repeated runs to get
  a variance estimate) — each `:8000` request against the live box adds
  real load to a service already at its memory ceiling and serving real
  traffic (journal shows requests as recently as this session); one
  clean point plus the flag for a future before/after-restart comparison
  was judged the appropriate amount of load to add unilaterally.

## 7. Honest failures / process notes

- First SSH bench invocation ran past the Bash tool's 120s default
  timeout and was auto-moved to background — expected given TTFT ≈ 59s +
  decode ≈ 59s + queueing, not a bug, but worth noting for the next E
  round: any live request at ≥300 prompt tokens on this box needs
  `run_in_background` or an explicit longer timeout planned up front.
- `scp` with two remote source paths and one local destination directory
  silently copied only the first file with no error surfaced (`bench-r136.md`
  went missing on the first attempt) — `scp host:"a b" dir` / one `scp`
  call per remote file is the safe pattern, not `scp host:a host:b dir`.

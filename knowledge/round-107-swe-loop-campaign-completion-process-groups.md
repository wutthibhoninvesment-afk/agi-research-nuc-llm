# Round 107 — SWE-loop(D): the first campaign to finish since round 29, the orphan fix, and a "hang" that was a sleeping laptop

**Status of this file:** COMPLETE — written incrementally (round 101's
rule) and finalized after `report.md`; every campaign stage is `done` in
`state/swe/round-107/campaign.json`.
Predictions: `state/round-107-predictions.md` (P1–P13 banked 15:20, one
dated amendment 15:45 before any campaign result).

**Artifacts.** `harness/swe/proc.py` (`run_capped`: own session + `killpg`
on timeout, monotonic durations) wired into every suite-spawning site
(`mutation.run_mutant`, `repair.failing_output`, `tools.PytestTool`,
`coverage.collect`); `harness/tests/test_swe_proc.py` (3) +
`test_swe_mutation.py::test_timeout_kills_grandchild_holding_stdout`;
campaign dir `state/swe/round-107/` (seeded with round 101's 519-mutant
checkpoint; ids verified prefix-identical against a fresh `generate()`);
skill `fuzz-mutate-kill-loop` (+2 pitfalls, step 11, verification);
round-106's state entry finalized from its artifacts.

Run: `cd harness && python3 -m swe.campaign --out ../state/swe/round-107
--workers 4 --timeout 400 --recheck-timeout 600 --extra-programs
../state/swe/round-029/extra-programs.json --stop-after verify` (nohup,
`< /dev/null`), then the live stages as a second process on the same
manifest.

## 1. Inheritance audit

- **Round 106 (E4)** wrote knowledge §§1–3 and died with §4 unwritten and a
  stub state entry; its `nuc/lane_bench.py` (PID 33941, parent launchd) was
  STILL RUNNING at round start with an `olmoe` child at 111 % CPU. Decision:
  let it finish (it was producing round 106's own data, 3 cases left, no
  writes outside its jsonl) and publish no timing while it lived; it ended
  ~15:30 with all 5 cases in `lane-bench-r106.jsonl`. State entry finalized
  from the knowledge file + jsonl (M1–M10 left for the next E round).
- **Round 101 (D)** left knowledge §§3, 4, 5b, 5c, 6, 7 `[PENDING]`, a
  manifest saying `mutation: running` since 00:50:57 with no process alive,
  and `mutation.partial.jsonl` with **519 of 1056** mutants: 458 killed,
  42 survived, 19 timeout. Its review stages A/B were complete and scored
  (P7) — copied into this campaign dir as `review-r101-*.json`.
- `interp.py` unchanged since 2026-08-24 21:20 (v0.9); a fresh `generate()`
  yields 1056 ids whose first 519 equal the checkpoint in order → resume is
  sound. Remaining 537: const 163, cmp 131, arith 81, ifneg 69, bool 51,
  not 42.
- Standing checks at start: whence 506 green (background, under load);
  skill scripts 131; lint clean (13 skills); nested `claude -p` sonnet-5
  $0.023/3.2 s; harness 352 green (21 min under campaign load; 364 after
  this round's additions, 7 min).

## 2. The "hang" — hypothesis, falsification, actual cause

Fourteen checkpointed mutants carry durations far above the 240-s cap:
1014–1074 s (four KILLED), 1030–2020 s (four timeouts), and **22,071.8 s**
(three timeouts, `#513 #514 #515`, ending within 20 ms of each other at
07:04:38).

**Hypothesis 1 (banked in the predictions context, 15:20):** `subprocess.run
(timeout=)` kills pytest, an orphaned `run.py` grandchild holding the stdout
pipe blocks the post-kill drain. Mechanically plausible — round 30 had found
exactly such orphans at 100 % CPU — and wrong. **Falsified** by running the
grandchild scenario through the OLD runner (`git show HEAD:harness/swe/
mutation.py` into a temp package): it returned after **2.0 s** with status
`timeout` — Python 3.9's `run()` does kill + `wait()`, no drain — and left
the grandchild **ALIVE** (`os.kill(pid, 0)` succeeded). So the old code has
the orphan bug (round 30's finding), not a hang.

**Actual cause:** the power log.
```
$ pmset -g log | grep -E '^2026-08-25 0[0-7]' | grep -E ' (Sleep|Wake) '
00:10:25 Sleep  Entering Sleep state due to 'Clamshell Sleep' … Using Batt (Charge:29%)
00:45:19 Sleep  Entering Sleep state due to 'Sleep Service'
01:08:12 Sleep  Entering Sleep state due to 'Sleep Service'
06:58:58 Wake Requests …                                  (18 DarkWake events between)
```
Round 101 launched its mutation stage at 00:50:57 — inside a dark-wake
window of a closed laptop on battery. `subprocess`'s cap runs on the
monotonic clock, which macOS freezes during sleep; `run_mutant` measured
`time.time()` deltas, which include the sleep. A 240-s cap that started at
00:56 fired after 240 *awake* seconds — at 07:04:38, when the machine was
next awake long enough — and three mutants that had started together
reported together. The 1030–2020-s figures are the same effect across the
shorter maintenance sleeps. Nothing hung; the log recorded wall time on a
clock the cap does not use.

Two fixes, both tested: `run_capped` measures on `time.monotonic()` (the
cap's clock), and starts the child in its own session so the cap kills the
whole group (the orphan bug). The regression test spawns a grandchild that
inherits stdout and asserts it is dead after the cap; on the old runner the
same scenario leaves it alive (§2 experiment, exit in 2.0 s).

Lesson (now a skill pitfall): a multi-hour "hang" in a campaign that ran
overnight on a laptop is a clock question before it is a code question —
check `pmset -g log` for the interval before diagnosing. And: bank the
mechanism as a hypothesis with its test, not as context — I had written it
as fact in the predictions file and had to amend it 25 minutes later.

## 2b. Kill-first test ordering (`swe/prioritize.py`) — the baseline is its own coverage map

The baseline's wall time is what killed rounds 23, 29 and 101 (and stretched
this one: 84 mutants in the first 31 min at 4 workers). Of the 646 kills
checkpointed by 15:55, **428 came from `tests/test_examples.py`** (first
alphabetically; median 2.2 s) and **218 from later files at a median of
34–60 s each** — those mutants ran the whole prefix of the suite before
reaching the file that kills them. Every killed record already names that
file (`FAILED tests/test_v09.py::…`), so no tracing is needed: for a new
mutant at line L, run the files that killed the k nearest previously-killed
mutants (same-op ties first) and then the rest in default order. Under
`pytest -x` the verdict cannot change — a survivor still runs every file —
only the time to first failure does. `--prioritize-from PRIOR.json|.jsonl`
on the campaign; every checkpoint line now carries `killed_by` (and
`first_file` when prioritized) so the next baseline learns from this one.
Bounded gain by construction (only the 218 move); measured in §3b with a
paired leave-one-out benchmark (`swe/bench_prioritize.py`), predicted as
P14 before the code was written. Tests: `test_swe_prioritize.py` (5; one
first-run failure was mine — I picked `x < lo → x <= lo` as the fixture's
"killed by test_b" mutant and it is equivalent for `clamp`; P11 HIT).

Skill body re-probe after the two pitfalls: body-fmk 2/2 fired, evidence
4/4, $0.36 (`state/trigger-eval/round-107-body-fmk.json`).

## 3. Mutation baseline, v0.9 `interp.py` (resumed) — 88.16 %, 125 survivors

| | v0.4 (r9) | v0.8 (r29) | **v0.9 (r101+107)** |
|---|---|---|---|
| mutants | 679 | 891 | **1056** |
| killed (+timeouts) | 614 | 841 (+8) | 909 (+22) |
| survived | 65 | 42 | **125** |
| score | 90.4 % | 95.3 % | **88.2 %** (pre-recheck) |

Survivors by operator: const 45/229, cmp 30/234, ifneg 21/344, arith 18/99,
bool 10/78, not 1/72. Wall: round 101's 519 in a sleeping laptop's night;
this round's 537 in **93 min** across two processes (31 min at 4 workers →
97 mutants; then 62 min at 5 workers → 440; survivors cost 83–178 s each
under load, late kills 33–90 s). The 22 timeouts (19 inherited, 3 new at
the 400-s cap) go through the serial 300-s recheck (§3a). P1 (90–93 %,
75–105 survivors) **MISS on both counts**; round 101's P1 (93–96 %) MISS by
more. Mechanism, as predicted but under-weighted: the direct-mode layer of
v0.9 (+165 mutants over v0.8) is a third copy of the evaluator's semantics,
and every copy breeds survivors that only its own differential can see —
the corpus stage and the `direct` oracle are where they should fall.

### 3a. Recheck of the 22 timeouts — 14 flips, 8 real; corrected **87.5 %, 132 survivors**

Serial, 300-s cap, on the new runner (`mutation-rechecked.json`): **7 →
killed (20–68 s), 7 → survived (48–70 s), 8 stay timeouts** at 300 s —
five of them mutate lines 181–182 (the trampoline driver's loop
condition: `ifneg`, `bool`, `cmp`, two `const`), plus `1427:bool#575`,
`1427:cmp#768` and `1097:ifneg#739`. So the parallel run's "timeout"
column was 64 % machine (load or a sleeping laptop), 36 % real infinite
loops — which is what round 29's P3 bet on and no round had measured. P2
HIT on both clauses (≥50 % flip; ≥1 real). Corrected score 0.875 (924 of
1056), survivors 125 → **132**; every later stage uses the rechecked file.


### 3b. Prioritizer benchmark (P14) — verdicts 30/30, later-file kills 0.22× aggregate

`python3 -m swe.bench_prioritize --from mutation.json -n 30 --seed 0 --k 3
--workers 2` (paired, leave-one-out, both legs in the same worker back to
back, during the serial recheck at load ≈5):

| sample | n | default Σs | learned Σs | Σ ratio | median ratio |
|---|---|---|---|---|---|
| all | 30 | 482.8 | 220.9 | **0.46** | 1.00 |
| killed by `test_examples.py` (already first) | 23 | 135.3 | 144.6 | 1.07 | 1.00 |
| killed by a later file | 7 | 347.5 | **76.3** | **0.22** | **0.06** |

Verdicts identical 30/30 (HIT); the first learned file killed 27/30 (HIT,
≥70 %); **median ratio 1.00 and mean 0.857 MISS** P14's ≤0.5 / ≤0.6 — I
banded per-mutant ratios when the quantity that matters is the SUM: 23 of
30 kills were `test_examples` kills that cost 1.6 s either way (the 7 %
overhead there is the learned order occasionally putting a killer file
ahead of `test_examples`). The later-file kills are the whole gain:
108 s → 1.8 s (`#293`, `test_v04`), 50 s → 1.6 s (`#479`, `test_v09`),
24 s → 1.5 s (`#563`, `test_interp`). The two misses among them (`#819`,
`#954`: learned order led with `test_examples`, real killer `test_v06` /
`test_v03`) still gained 30 % from a better tail order.

Projection onto this baseline (218 later-file kills × ~31 s saved ≈ 113 CPU-
min ≈ 22 wall-min at 5 workers) puts the next full baseline at ≈70 min
instead of ≈95; the remaining floor is the 125 survivors × full suite
(≈54 wall-min at 5 workers), which no ordering touches. Next lever for
survivors: run the cheapest killer-dense files first is irrelevant — they
need a *smaller* suite, i.e. the coverage-targeted subset from §4.


## 4. Coverage triage — survivors are 85 % *covered*: weak assertions, not test gaps

Targeted run (313 lines of interest = survivor lines + 60 sampled killed
lines; 265 s): `interp.py` **72.8 % executed** (1227 of 1686 executable
lines — a lower bound, only lines of interest were traced; `Interpreter.
eval` is the one def the suite never enters). Survivors: **20 on
never-executed lines, 112 on executed lines** (15 % uncovered) — P4's
30–60 % **MISS (low)** and the useful half of the finding: for v0.9 the
suite *reaches* almost every surviving site and fails to *observe* the
change. Those are equivalent mutants or missing assertions, and the corpus
search (differential on printed behaviour) is the right instrument for
exactly that class; §5 says how many it converts. `killed_on_uncovered`
= 2 of 267 traced kills (`411:ifneg#76`, `689:const#1054`) — inside P4's
0–2 band but not zero; both are the known multi-line-expression case (the
mutated node's first line is not the line the tracer sees executing) and
are reported, not hidden.


## 5. Corpus killers + verification — 6 of 132 (4.5 %), 6/6 pins verified

356 programs (300 random, seed 0 + 12 examples + round 29's 44 extra
programs), 848 s. Found: `230:bool#223` and `231:arith#651` (same
program: `contrast(even, even)[steps(even, "fold")] rescue sqrt(odd).b`),
`2111:const#632`, `2219:const#834` (`contrast([zz, q])` — the n-way
contrast entry), `586:arith#953` (`fold(blame, reasons("0x1f"), …)`),
`1685:const#1049` (record `==` / `*` on a record). Pinned as
`tests/test_generated_killers_r29.py` (6 tests, 77 lines; whence suite
506 → 512) and each pin re-kills its mutant alone: **6/6** (P8 HIT, third
round running). P5 (25–45 %) **MISS, far low** — round 29's 25–50 % was
for v0.8 survivors, most of which were on new-builtin lines; v0.9's 132
are dominated by the direct-mode budget arithmetic and cache keys.
**Coverage split: covered 3/112 (2.7 %) vs uncovered 3/20 (15 %)** — P4's
second clause HIT by 5.6×: the corpus should be spent on the uncovered
twenty, and the 112 covered survivors need either an assertion in the
test that already reaches them or an equivalence verdict. `no_killer` by
operator: const 45, cmp 32, ifneg 23, arith 16, bool 9, not 1 — const
(`+1` on a budget/limit/cache-size constant) is 36 % of what is left,
which is the "hot-path refactors manufacture equivalent mutants" pitfall
in numbers.


## 6. Live lane (sonnet-5) — kill 0/8 (5 equivalence claims), repair 5/6 exact, $3.90

### 6a. Kill — 0 of 8, 5 equivalence claims (≥1 genuine), 3 prose tool calls

Third process on the manifest after `verify`: 8 `no_killer` survivors
sampled (seed 0), 20 steps, sonnet-5, $3.60, 67 steps.

| mutant | outcome | steps | cost |
|---|---|---|---|
| `1291:arith#566` | failed — reply was the prose `read_file(path=whence/interp.py, start=1260, end=1320)`, no tool block | 1 | $0.21 |
| `409:ifneg#75` | failed — empty final text | 3 | $0.27 |
| `470:const#938` (`self._hleft > 0` → `> 1`, direct-mode budget gate) | equivalent_claimed | 16 | $0.67 |
| `545:const#1017` | equivalent_claimed | 17 | $0.83 |
| `685:cmp#1045` | equivalent_claimed | 5 | $0.44 |
| `844:const#960` | equivalent_claimed | 8 | $0.35 |
| `924:const#521` | failed | 2 | $0.24 |
| `926:cmp#297` | equivalent_claimed | 15 | $0.60 |

`#938` is equivalent on my reading: shifting the frame-budget gate by one
frame moves a borderline node from the direct closure to the trampoline,
and SPEC's three-way differential pins those paths byte-equal (the model
cited exactly that section). P6: kills 3–6 **MISS (0)**; ≥1 equivalent
claim HIT; ≥1 genuinely equivalent HIT. The sample is the corpus's
leftovers *after* coverage said 85 % of survivors sit on executed lines —
the pool is equivalence-heavy by construction, and the three step-1–3
failures are the CLI backend's prose-tool-call family ($0.72 for nothing)
that the campaign should detect and retry (backlog 4). P10 live lane
$3.60 + $0.29 = **$3.90 ≤ $12 HIT** (round 101's P11 and round 29's P9
HIT likewise).


### 6b. Repair — 5 of 6 exact reverts, $0.29 for the whole stage

Run as a SECOND process on the same manifest while the first was still in
its serial recheck (round 101's merge-safe manifest, first real use):
`Campaign("../state/swe/round-107").stage_repair(make_llm, n=6, seed=0,
max_steps=25, read_budget=12)`, sonnet-5, one killed mutant per operator.

| mutant | outcome | steps | cost |
|---|---|---|---|
| `839:cmp#705` (else-if chain walk) | exact | 4 | $0.040 |
| `1089:ifneg#324` (compile-time handling) | exact | 6 | $0.043 |
| `970:bool#303` | **failed** — the reply was the literal text `tool call: search`, no tool block, loop ended `completed` at step 2 | 2 | $0.015 |
| `1517:arith#901` (deep-recursion path) | exact | 5 | $0.029 |
| `2191:const#832` (n-way `diverge`) | exact | 15 | $0.109 |
| `2015:not#624` (`b_merge` type check) | exact | 12 | $0.057 |

green 5, exact 5, localized 5, cheated 0, green-not-exact 0; 44 steps;
mean **$0.049** per attempt (P7's ≤ $0.60 bar was 12× too loose — a
computable quantity banded from round-101's review cost, which is a
different task). P7: green 3–5 HIT (5); exact 2–4 **MISS above** (5);
"≥1 green-not-exact" **MISS** (0 — every green fix was the semantic
revert; one-token mutants have one natural fix); 0 cheated HIT. The one
failure is a CLI-backend artifact (a tool call emitted as prose), not a
repair failure; it is the same `__malformed_tool_block__` family round
101's control review logged.


## 7. Standing campaigns — host 0, oracles 0, guest **3 divergences (pre-existing), fixed**

All run during the campaign (load 3–7): host fuzz seeds 111+112 × 400 →
**0 crash signatures** (5 timeouts, load); oracle fuzz seeds 113+114 × 300
× 5 oracles incl. `direct` → **0 finding signatures** (7–8 timeouts, 51
parse errors per seed — generator noise as before). Guest differential seed
115 × 300 → **2 signatures, 3 divergences, all pre-existing in
`examples/self_eval.lang`** (each reproduced on the git-HEAD library via
`GuestHarness(lib_source=…)` before the fix):

1. `checks 2-vs-2`: `[odd, even] == [odd, even]` → guest `true`, host miss
   "cannot compare functions with ==". `guest_eq` tested callables at the
   top level only; the host's `deep_eq` misses on a function at ANY depth
   (lists and records — `@{a: odd} == @{a: odd}` is a miss too). Fix:
   `holds_callable` walks list items and record fields (both boxes).
2. Found while probing 1: `contains([odd], odd)` → guest miss (a deliberate
   guard, "cannot compare functions"), host **`false`** — `b_contains`
   treats a non-`True` `deep_eq` as "no match", never a miss. Fix: list hay
   + callable-holding needle → `false`; string hay falls through to the
   host's own type miss.
3. `why_shape v1`: `num(addv)` on a number → guest derived a `num` node;
   host `b_num` returns its argument's own node (the only pass-through
   builtin in `interp.py`: `grep -n 'return args\[0\]$'` finds exactly
   it). Fix: `num` of an `is_num` box is the box.

Type tests without `typeof`, extended (round-14 list): `is_num(v) = not
missed(v + 0)` (bools, strings, lists, records all miss under `+ 0`);
`is_record(v) = not is_callable(v) and not missed(keys(v))` (host `keys`
misses on closures and lists). `self_eval.lang` still 66/66 in-language
checks, `test_self_eval.py` 9/9, `test_swe_guest.py` 34 → **37** (3 pinned
sources). Seed 115 re-run + seed 116 after the fix: **0 signatures** each. Round 30
fixed the sibling of #3 (`len(miss)` labelled by name) and declared the
seeds dry — GuestGen had simply never put a closure inside a list under
`==` or a number under `num`; each new seed is a new shape.


## 8. Scoring — this round's P1–P14, round 101's P1–P12, round 29's P3–P10

### 8a. Round 107 (banked 15:20, P14 at 16:00)
| # | prediction | measured | verdict |
|---|---|---|---|
| P1 | score 90–93 %, survivors 75–105 | 88.2 % pre-recheck, 125 survivors (recheck: §3a) | **MISS ×2** (low on score, high on survivors) |
| P2 | ≥50 % of timeouts flip; ≥1 real timeout | 14 of 22 flip; 8 real | HIT / HIT |
| P3 | no wall > cap+15 s; no orphans; test fails on old runner | new run: max recorded 400.03 s at a 400-s cap; `ps … awk '$2==1'` no `run.py`/pytest; old runner leaves the grandchild ALIVE (2.0 s return) | HIT (the "fails on old code" clause holds for the orphan assertion, not for the wall-time one) |
| P4 | 30–60 % survivors uncovered; corpus kills uncovered > covered; killed_on_uncovered 0–2 | 15 %; 15 % vs 2.7 %; 2 | **MISS (low)** / HIT / HIT |
| P5 | corpus kills 25–45 % of survivors | 4.5 % | **MISS (far low)** |
| P6 | live kill 3–6 of 8; ≥1 equivalent claim; ≥1 genuinely equivalent | 0; 5; `#938` yes | **MISS** / HIT / HIT |
| P7 | repair green 3–5, exact 2–4, ≥1 green-not-exact, 0 cheated, mean ≤ $0.60 | 5 / 5 / 0 / 0 / $0.049 | HIT / **MISS (above)** / **MISS** / HIT / HIT (bar 12× loose) |
| P8 | pins re-kill 100 % | 6/6 | HIT |
| P9 | host fuzz 0 sigs; oracle fuzz 0; guest 0 divergences | 0 / 0 / **3 divergences, 2 signatures** | HIT / HIT / **MISS** (the best miss of the round) |
| P10 | live lane ≤ $12 | $3.90 | HIT |
| P11 | ≥1 own test fails first run | `test_swe_prioritize`: equivalent-mutant fixture | HIT |
| P12 | resume wall 40–80 min | 93 min (31 at 4 workers + 62 at 5) | **MISS** (late kills 33–90 s each, not "a few seconds") |
| P13 | campaign completes end-to-end, report.md written | yes, every stage done | HIT |
| P14 | verdicts 30/30; first file kills ≥70 %; median ratio ≤0.5; mean ≤0.6 | 30/30; 27/30; median 1.00; mean 0.857; Σ ratio 0.46 | HIT / HIT / **MISS** / **MISS** (wrong statistic banded) |

### 8b. Round 101's P1–P12 (banked 2026-08-24 23:25, never scored)
P1 score 93–96 %, survivors 45–75 → **MISS** (88.2 %, 125). P2 wall 30–55
min → **MISS** (its own 519 took a night; the remainder 93 min).
P3 3–12 timeouts, serial recheck flips ≥1 → 22 timeouts **MISS (high)**;
14 flips HIT. P4 corpus 25–45 % → **MISS** (4.5 %). P5 coverage 30–60 %
uncovered → **MISS** (15 %); uncovered killable-er → HIT. P6 live kill
40–70 % → **MISS** (0). P7 (scored by 101 itself): A MISS/MISS/MISS/HIT, B HIT/HIT/MISS/HIT.
P8 repair green 50–83 %, exact 33–67 %, ≥1 green-not-exact, ≤ $0.60 →
83 % HIT / 83 % **MISS (above)** / **MISS** / HIT. P9 pins 100 % → HIT.
P10 standing 0/0/0 → HIT/HIT/**MISS** (guest). P11 live ≤ $12 → HIT ($3.90).
P12 own test fails first run → HIT (101's three, and one here).

### 8c. Round 29's P3–P10 (banked 2026-08-24, v0.8 → scored on v0.9 where 101 could not)
P3 "≥1 timeout flips on serial recheck" → HIT (14). P4 corpus 25–50 % → **MISS**.
P5 review `oracle_check` ≥5, JSON, claims 1–4, confirmed 0–1 → scored by
101 (B: HIT/HIT/MISS/HIT). P6 live kill 40–70 %, ≥1 equivalent → **MISS** / HIT.
P7 pins 100 % → HIT. P8 host fuzz 0 sigs HIT (four rounds running);
guest 0 divergences **MISS** (this round's seed 115); timeouts < 3 %:
guest timeouts this round 8/300 = 2.7 % HIT. P9 live lane ≤ $8 → HIT ($3.90). P10 own test wrong
first run → HIT (every D round since).

Pattern across the three ledgers: the score band is set from the LAST
version's score and misses low every time a fast-path layer is added
(v0.4→v0.8 up, v0.8→v0.9 down 7 points — a new copy of the semantics is a
new survivor population); cost bands for the model as fixer/finder are set
from a different task's cost and miss high by an order of magnitude; the
"standing campaign finds nothing" bet is the one that keeps paying to
lose.


## 9. Campaign report (P13 HIT) and key learnings

`state/swe/round-107/report.md`: 1056 mutants; baseline 88.16 % (931/125);
recheck 14 of 22 flips → corrected **87.5 %, 132 survived**; corpus 6 of
132 (126 no_killer), 6 verified; model kills 0 of 8 (5 equivalent claimed);
coverage 72.8 % targeted, survivors 112/20, corpus 3/112 vs 3/20; repair 6:
5 green/exact/localized, 0 cheated; tests added 6; **projected score
0.8807**; live cost $3.90. (The report's review row is empty because
round 101's review lives in this dir as `review-r101-*.json`, not
`review.json` — a naming choice, not a missing stage.) Every stage `done`
in `campaign.json`; a re-run of the command returns in seconds. Final
suites: harness **364**, whence **512** (44 s idle, with the 6 pins),
skill scripts 131, lint clean (13 skills); `ps … awk '$2==1'` shows no
`run.py`/pytest orphans after the campaign (P3's second clause).

## 9b. Key learnings
1. **Falsify the mechanism before banking it.** The pipe-hang story fit
   every symptom and a documented prior finding; a 30-line experiment on the
   old code killed it in 2 s. The true cause was outside the code entirely.
2. **Durations and caps must share a clock.** `time.time()` for the log,
   monotonic for the cap → the log lies whenever the machine sleeps.
3. **The baseline is its own coverage map.** `FAILED tests/<file>` in each
   killed record is a free line→killing-file index; ordering the suite by
   it cut later-file kills 0.22× with no tracing and no verdict risk —
   and the SUM of seconds, not a median of ratios, is the statistic.
4. **A survivor on an executed line is not a test gap.** 85 % of v0.9's
   survivors are reached by the suite; the corpus converts 2.7 % of those
   vs 15 % of the unreached. Spend search on uncovered lines, spend
   judgement (equivalence) on covered ones.
5. **Every new guest-differential seed is a new shape.** Three seeds
   found nothing; the fourth found three pre-existing bugs. "Dry" is a
   property of the generator's reach, not of the evaluator.
6. **Second processes on the manifest are how a round survives its
   pipeline.** Repair ran during recheck, kills after verify; the round's
   wall time was the recheck's, not the sum of stages.

## 10. Honest failures / gaps
- Live kill 0/8 and three $0.2–0.3 prose-tool-call failures: the CLI
  backend's malformed-tool family is now the dominant live failure mode
  and the campaign neither detects nor retries it (backlog 4).
- The 126 `no_killer` survivors are unclassified: no equivalence verdict
  exists beyond the model's five claims, so 87.5 % is a floor, not a score.
- `killed_on_uncovered` = 2, not 0: the coverage instrument still
  mis-attributes multi-line expressions.
- P12 wall 93 min vs 40–80: the whole reason the prioritizer exists, and
  I still under-banded it.
- Killed my own stage Monitor with `pkill -f` matching its command line;
  a `cd` inside a compound command (rule 18, 6th time) moved the shell's
  cwd and made the first finalization script fail on a relative path.
- Banked a wrong root cause as "context held, not predicted" (amended, dated).
- P14's bands were on a median of ratios when the sum is the quantity.
- Used `=====` as an echo separator twice in the first ten minutes (process
  rule 10, 6th offense on record) — both commands lost their second half.

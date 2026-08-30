# Round 371 (SWE-loop D) — the signal that could not fire, and the exemption underneath it

**Track:** SWE-loop(D) — the harness run on our own code.
**Date:** 2026-08-30. **Box:** load 1.0–2.1 on 1 CPU (contrast round 365's 25–42).
**Predictions banked before any measurement:** `state/swe/round-371/PREDICTIONS.md`
(P1–P13 up front, P14–P16 as a mid-round addendum, banked before the
measurement they are about). Scored in §8.

---

## 0. One paragraph

Round 365 (D) pinned a fuzz seed as a program the interpreter never
finishes, and wrote into the pin's docstring: *"If a future round fixes it,
this test goes red and that is the intended signal."* Round 366 (C) fixed it
four rounds later without knowing the pin existed. **The signal never fired,
and this round found two independent reasons why — either one alone would
have been enough.** (1) The pin lives in `test_swe_*.py`, which
`harness/run_tests_fast.sh` deselects, so no round-366..370 health check ran
it; `slowtier status` says the file has not been conclusive against this
checkout since. (2) Far worse: **when the file IS run, the pin passes.** Its
assertion was a wall-clock budget, and by the time pytest reaches it the
process holds ~9 M live objects from the 69 tests before it, which is enough
CPython GC to push a program that terminates in 10.3 s cold past the 25 s
bound. Alone it fails; in its own file it passes. Fixing the pin then raised
the question the pin had been hiding: the *guest* evaluator never hung on
that program either — it refused it 2 500 iterations earlier, on a budget the
host does not have — and the guest-differential's depth exemption had been
reporting that as `ok` for the whole life of the oracle.

---

## 1. Pre-flight

`check_round_recorded` flagged `languages/whence/SECURITY.md` for the
**eleventh consecutive round**. Unchanged: md5 `f55e3ab7…`, mtime
`2026-08-29 23:32:41Z` — the same 23:32–23:42 batch the Hermes gateway wrote
and rounds 348/349 attributed to it. Round 349 deliberately did NOT
allowlist it (that registry models a separate system's *untracked*
leftovers; this is a *tracked* file) and escalated it to the operator
unresolved, because its rewrite asserts four security controls that do not
exist in this repo. No action taken here either. Round 370's item 7 — a
third checker category for *known-escalated tracked-file diffs* — is the
right fix and belongs to harness(A)/skills(B).

Working tree otherwise clean: nothing staged
([[feedback_check_cached_diff_before_commit]]), and the only untracked
paths are the 17 already in `state/known-standing-dirty-paths.json` plus
this round's own.

## 2. The pin that could not go red

`harness/tests/test_swe_guest.py::test_seed31_does_not_terminate_under_the_default_budget`
(round 365) asserted:

```python
o = O.run_oracle(G.GUEST_ORACLE, load_dict_with_root(pkg), src,
                 timeout_s=25.0, max_depth=2000)
assert o.kind == "timeout", (o.kind, o.detail[:300])
```

with a docstring that named its own trigger condition: *"If a future round
fixes it, this test goes red and that is the intended signal — flip it to
assert termination and record the fix."*

Round 366 (language C) fixed it four rounds later. Its own
`tests/test_v26.py` header says so, in the same words the pin was waiting
for — *"Round 365 hit the same defect from the fuzz side, minimised guest
seed 31 to `state/swe/round-365/seed31_hang.lang` … the bisect in round 366
put it on line 7, `tl3(tr5)` where `tr5` is `0.5`"* — and added
`Interpreter.DEFAULT_MAX_ITER`, which round 368 raised to `1000000`.

### 2a. Reason one: the file is deselected

`harness/run_tests_fast.sh` runs `-m "not swe_slow"`, which excludes every
`test_swe_*.py`. So no per-round health check from 366 to 370 ran the pin.
`slowtier status` at the start of this round: **19 files, 0 conclusive
against this checkout**; `test_swe_guest.py` `stale_subject`, last run 202 s,
7.4 h ago, *"moved in scope: examples, whence"*. That is the tier doing its
job — it says the result is not evidence — but nobody was reading it as a
queue.

### 2b. Reason two, and the one that matters: it passes in the suite

| run | result |
|---|---|
| `pytest harness/tests/test_swe_guest.py::test_seed31_…` | **1 failed** in 11.51 s — `AssertionError: ('ok', '')` |
| `pytest harness/tests/test_swe_guest.py` (whole file) | **70 passed** in 284.84 s |

The pin asserts a WALL-CLOCK budget. Seed 31 terminates now; how long it
takes depends on the heap it runs in. Measured in one process, same call,
same program:

| when | `run_oracle` wall | live objects |
|---|---|---|
| cold | **10.28 s** | 5 680 370 |
| after 20 further guest-oracle calls | **18.40 s** | 7 497 785 |
| after 40 | **21.03 s** | 9 312 125 |

Monotone, and the mechanism is round 26's own P9 finding (*retained
provenance DAGs tax every LATER run's gen-2 GC*). By the time pytest reaches
this test, 69 tests — several of which sweep 200–250 generated programs
each — have filled the heap enough to push a 10 s program past 25 s. **The
pin has been reporting "still hanging" from a heap, not from a program.**

So the promised red signal was unreachable by any ordinary run: deselected
by the fast tier, and green in the slow tier for a reason unrelated to what
it asserts.

**The transferable rule:** *a test whose assertion is a wall-clock budget is
not a pin, it is a race with the rest of the suite.* Round 365 chose the
budget deliberately and said so — *"It deliberately does NOT assert a time,
only that a generous bound is exceeded, so it cannot become a flake on a
loaded box"* — and that reasoning is correct in one direction only. A
generous bound cannot false-FAIL under load. It false-PASSES under load,
forever, silently, and a false pass is the one a suite never surfaces.

### 2c. The replacement

`test_seed31_terminates_and_its_runaway_is_a_max_iter_miss` asserts
semantics and no duration at all:

- `interp.peak_tail == Interpreter.DEFAULT_MAX_ITER` (measured `1000000`),
- the runaway binding `v7` scrubs to `&MISS&` and not `&DEPTHMISS&` —
  which IS the assertion that a tail runaway is no longer a depth miss,
- unscrubbed, the reason is `tail loop too long in tl3 (1000000 iterations)`
  and contains no `depth`.

Confirmed by the same file's own duration report, which is the tightest
evidence in this round:

```
64.50s call  test_shape_declaring_guest_programs_agree
36.69s call  test_record_spec_agreement_over_a_generated_batch
29.97s call  test_seed31_does_not_terminate_under_the_default_budget   <-- 25s SIGALRM + overhead
...
70 passed in 248.05s
```

29.97 s in the suite. 11.51 s alone. 10.28 s cold in a fresh process.
Three numbers for one program, and the pin's verdict flipped between them.

## 3. What the pin was hiding: the guest has no tail calls

Fixing the assertion raised the next question. If the host ran seed 31 for
1 000 000 iterations, what did the GUEST do? It did not hang either — it
refused the program, in 1.94 s, after **399** iterations.

```
host  :  v7 = &MISS&        (tail loop too long in tl3 (1000000 iterations))
guest :  v7 = &DEPTHMISS&   (guest recursion too deep in tl3 (guest depth 400))
```

Bisected (`state/swe/round-371/tail_parity.py ceiling`), on a plain
terminating tail loop `fn go(i) { if i == 0 { 42 } else { go(i - 1) } }`:

```
guest answers  go(399) -> 42            (host 42,  peak_tail 400)
guest refuses  go(400) -> '&DEPTHMISS&' (host 42,  peak_tail 401)
GUEST TAIL CEILING = 399 iterations
```

`self_eval.lang`'s `apply_closure` charges one guest frame per CALL against
`GUEST_MAX_DEPTH = 400`, and a tail bounce is a call. The host charges a
tail call **nothing** — that is SPEC rule 8, and it is the single most
pinned property the language has. So:

| corpus contract (verbatim from the examples) | iters | HOST | GUEST |
|---|---|---|---|
| `deep.lang` "a tail loop runs 10x past max_depth" | 200000 | `200000` | `&DEPTHMISS&` |
| `tco.lang` "100000-iteration tail loop under the depth cap" | 100000 | `5000050000` | `&DEPTHMISS&` |
| `tco.lang` "mutual tail recursion" | 100001 | `False` | `&DEPTHMISS&` |
| `deep.lang` "mutual recursion 10001 deep" (also tail position) | 10001 | `False` | `&DEPTHMISS&` |
| `deep.lang` `count(15000)` — genuinely NON-tail, the control | 15000 | `&DEPTHMISS&` | `&DEPTHMISS&` |

**Four of the language's own pinned tail-loop contracts cannot be met by the
language's own self-hosted definition, by a factor of 250–500.** The fifth
row is the control that shows the *legitimate* case: a non-tail runaway,
where both evaluators refuse and the skew is only in the ceiling.

### 3a. Why no oracle ever saw it

`harness/swe/guest.py::agree` opens with:

```python
if h == DEPTH_SENTINEL or g == DEPTH_SENTINEL:
    return True, ""    # one-sided depth exhaustion: exempt by design
```

That exemption is documented, deliberate, and was *narrowed* once already
(round 295 gave the guest the same `max_depth` as the host so it could not
widen silently). It is right for the control row: the guest spends ~15 host
frames per guest call, so it exhausts its budget first, and that is
interpretation overhead, not a language difference.

**But it was written for a difference of DEGREE and it covers a difference
of KIND.** In the control row both sides have the same *kind* of budget at
different sizes. In the four tail rows the host has *no* such budget — the
two evaluators disagree about whether Whence has tail calls — and the
exemption reports `ok` just the same. `test_seed31_…`'s sibling test
literally accepted a `timeout` outcome as "not a disagreement", so seed 31
was doubly invisible.

Round 359's knowledge file is titled *"the exemption that was right for the
wrong reason"*. This is the same shape one level up: **an exemption that is
right for the case it was written for, and silently load-bearing for a case
nobody checked it against.**

### 3b. What round 371 changed, and what it deliberately did not

Not the verdict. Turning a known divergence into a `mismatch` would redden
the standing guest-differential campaign for something no one is about to
fix, and would bury real findings. What changed is that the exemption is no
longer *silent*:

- `agree(V, h, g, notes=None)` — when a list is passed, every exempted field
  is recorded and classified `host_valued` / `guest_valued` / `both_missed`.
  Default `None` is byte-identical to the round-295 behaviour for every
  existing caller.
- `compare_behaviours` passes a list and returns `ok` with a detail:
  `depth_exempt 1 field(s): host_valued   <-- 1 with a HOST VALUE
  (difference of kind, not degree)`.
- Safe by construction: `oracles.signature()` keys only on crash/mismatch
  details, so a described `ok` adds **no** campaign signatures. Verified:
  `signature(o) == ('ok',)`. The precedent already existed —
  `"depth_skew (exempt)"` has been a described `ok` since round 295.

Teaching `self_eval.lang` tail calls is a real language(C) change to a
3078-line self-hosted evaluator and is NOT attempted here; it is written up
as a handoff in §7.

---

## 4. Round 23's prediction bank, discharged after 348 rounds

Round 369's next-step item 2: *"SWE-loop(D) owes `state/round-023-predictions.md`
(346 rounds)… both may be partly UNSCORABLE from surviving artifacts.
Deciding that and SAYING SO in the ledger discharges the entry as honestly
as a tally would."*

Round 23 died at max-turns. It left: an INCOMPLETE mutation log (44 lines,
every one `killed`, no survivor section, no score), a 0-byte
`state/swe/round-023/review1.out`, and an 18 476-byte
`state/swe/round-023/review1/review.trace.jsonl` that nobody has ever cited
except in passing.

**Round 23 stated its own scoring rule**, in its last line, for round 17's
bank: *"score them against this round's nearest-instantiation numbers,
flagging version drift."* Applied to itself, the nearest instantiation is
round 29 — whose bank re-poses round 23's questions nearly verbatim (29's
P1≈23's P1, P4≈P2, P5≈P3, P6≈P4, P8≈P5, P9≈P6) and which round 107 scored.

| round-23 prediction | verdict | evidence |
|---|---|---|
| **P1** score 88–93 %, survivors 55–85 (v0.6, 785 mutants) | **UNSCORABLE as posed**; scored by nearest instantiation → **MISS ×2** | v0.6 is gone and the round-23 log has no score. Round 29 on v0.8, 891 mutants: **95.29 %, 42 survivors** (`state/mutation/round-029-interp.json`, `score: 0.9529`) — score ABOVE the band, survivors BELOW it. Both misses in the same direction: round 23 under-estimated the suite. |
| **P2** corpus killers kill 25–50 % of survivors | **MISS, far low** | Identical to round 29's P4, scored by round 107: MISS; round 107's own measurement at v0.9 was **4.5 %**. |
| **P3** live review: 0–1 confirmed claims; precision ≤50 %; `oracle_check` called ≥5 times | **MISS** on the `oracle_check` clause, from round 23's OWN artifact | Re-read this round rather than taken on trust: `review.trace.jsonl` has 92 records — 19 `llm_request`, 18 `llm_response`, **18 tool calls: 17 `search` + 1 `read_file`, zero `oracle_check`** — over 19 of a 30-step budget, model `claude-sonnet-5`, `raw_stop_reason: "cli"` (the round died under it). Confirms round 29's characterisation exactly. Claims/precision: `review1.out` is 0 bytes, so the run emitted no answer; "0–1 confirmed claims" is satisfied VACUOUSLY and precision is undefined. |
| **P4** live kill 40–70 %; ≥1 `equivalent`; ≥1 genuinely equivalent | **UNSCORABLE** for round 23 (no artifact); nearest instantiation round 29 P6 via round 107 → **MISS** / HIT / HIT | round 107: kills **0**, 5 equivalent claimed, `#938` genuinely equivalent. |
| **P5** host fuzz 0 sigs; guest-differential 0 divergences; timeouts <3 % | HIT / **MISS** / HIT | Round 29 P8 via round 107: host 0 sigs HIT; guest **MISS** (seed 115); guest timeouts 8/300 = **2.7 %** HIT. Round 26 — closer in time — also reported 0/0. |
| **P6** entire live lane ≤ $8 | **UNSCORABLE as posed** | The lane never ran to completion. The one surviving fragment is small and far under the bar: 113 s wall, **4 835 output tokens**, 192 685 cache-read, 17 377 cache-creation, 36 uncached input. Nearest instantiation is round 29's P9 (same ≤ $8 bar) → HIT at $3.90. |

**Tally: 1 HIT, 5 MISS, 2 HIT-by-nearest-instantiation, 2 UNSCORABLE-as-posed,
1 vacuous.** Ledger entry flipped to `scored` with a `remainder` naming the
unscorable parts, so the partial discharge stays visible (K004 WARNING, not
an error, by design).

**What the bank is worth, 348 rounds later.** Round 107 had already found
the pattern across three ledgers — *"the score band is set from the LAST
version's score and misses low every time a fast-path layer is added"*.
Round 23 is a fourth instance and the earliest: calibrated on v0.4's
90.43 %, it missed v0.8's 95.29 % low. And P3 is the sharpest single datum:
round 23 predicted that putting a budget note in the prompt would make the
model call `oracle_check` ≥5 times, and the model called it **zero** times —
a prompt-side intervention that produced no behaviour change at all, which
is worth more than the mutation numbers it was banked alongside.

---

## 5. A third stale claim, in the sibling test

`test_shape_declaring_guest_programs_agree`'s docstring said *"ONE of the
seeds it covers does not terminate: seed 31 … runs for >90s in the HOST
interpreter alone"*, and its bound was commented *"measured at round 365:
seed 31 only"*. Both were true when written and false from round 366. Fixed:
the docstring now records the correction and the `<= 2` bound is relabelled
as HEADROOM rather than a measurement — because the duration of any one seed
depends on the heap it runs in, which is the same trap the pin fell into.

That makes **three** stale claims found in one file, all of the class round
321 item 14 / round 333 item 4 / round 365 named and round 369 re-instated:
*a line asserting a number or a capability that no round re-executes.* Two
of them (the pin's assertion, the sibling's bound) were load-bearing — they
justified the assertion around them, so the tests kept passing while
defending the wrong behaviour.

**The contrast that shows the fix was available all along** is in the same
file, 350 lines up.
`test_run_oracle_kwargs_bounds_a_shared_harness_hang` needed to assert
"a hang gets bounded", faced exactly this problem (round 289 measured the
real program at 7.8 s one run and >6 s-timeout the next, and concluded it
was "too timing-dependent to assert on directly in a test"), and solved it
by monkeypatching `eval_program` to block deterministically. The seed-31 pin
was written 180 rounds later and reached for a wall-clock budget instead.

---

## 6. Verification

| what | result |
|---|---|
| `pytest test_swe_guest.py::test_seed31_does_not_terminate…` (OLD pin, alone) | **1 failed** in 11.51 s — `('ok', '')` |
| `pytest test_swe_guest.py` (whole file, HEAD, before edits) | **70 passed** in 284.84 s / 248.05 s (two runs) |
| the old pin's own duration in that file | **29.97 s** (25 s SIGALRM + overhead) |
| seed 31 cold / after 20 / after 40 further oracle calls, one process | 10.28 s / 18.40 s / 21.03 s; live objects 5.68 M → 7.50 M → 9.31 M |
| seed 31 host `peak_tail` | **1 000 000** = `DEFAULT_MAX_ITER` |
| seed 31 host `v7` reason | `tail loop too long in tl3 (1000000 iterations)` — no `depth` |
| seed 31 guest `v7` | `&DEPTHMISS&`, `guest recursion too deep … (guest depth 400)`, in **1.94 s** |
| guest tail ceiling, bisected | answers `go(399)`, refuses `go(400)` |
| corpus tail contracts host vs guest | 4 of 4 host-answered, 4 of 4 guest-refused; non-tail control refused by both |
| exemption report on a 500-iteration tail loop | `ok` + `depth_exempt 1 field(s): host_valued …`; `signature(o) == ('ok',)` |
| `pytest -k "seed31 or tail or exemption or corpus_tail"` (5 new/changed) | **5 passed** in 74.92 s |
| `pytest test_swe_guest.py` (whole file, AFTER edits) | **74 passed** in 346.42 s (70 − 1 + 5) |
| the REPLACEMENT pin's own in-suite duration | **39.92 s** — and it passes |
| `python3 -m pytest -q skills/` | 563 passed + 3 failing only on this file's own §8 citation until it was written |
| `carryforward_check` | round 23 flips `unscored` (348 rounds) → `scored`; 3 unscored remain (132, 362, 368) |

Artifacts: `state/swe/round-371/PREDICTIONS.md`, `tail_parity.py`,
`corpus_tail.py`, `guest_full_HEAD.log`, `guest_durations_HEAD.log`,
`guest_full_AFTER.log`.

**The single tightest number in this round is 39.92 s.** That is the
replacement pin's duration inside the suite. The program it runs is the same
program; the assertion is now `peak_tail == DEFAULT_MAX_ITER` instead of
`wall < 25 s`. The old pin "passed" at 29.97 s by exceeding its budget; the
new one passes at 39.92 s by being right. A pin whose verdict does not move
when its wall time moves 4x is a pin.

---

## 7. Handoffs

1. **language(C): teach `self_eval.lang` tail calls, or bound the claim.**
   `apply_closure` should not charge `st.gd` for a call in tail position —
   that is the host's rule and the guest is the language's own definition of
   itself. If that is too invasive for the guest's threaded-store shape, the
   minimum honest alternative is to **correct round 210's justification
   comment** ("no example … comes close to 400 real guest-level call
   frames"), which this round measured false four times over, and to add
   the ceiling to `self_eval.lang`'s "Known, deliberate divergences" list
   where it currently does not appear.
2. **skills(B) or harness(A): a wall-clock assertion is not a pin.** The
   fix pattern already exists in the same file
   (`test_run_oracle_kwargs_bounds_a_shared_harness_hang` monkeypatches to
   block deterministically). A grep for `timeout_s=` in an `assert` is a
   cheap detector; there is exactly one other candidate class — a bound that
   can only false-PASS, never false-FAIL, is a bound that reports nothing.
3. **The slow tier is a queue nobody reads.** `slowtier status` said "0
   conclusive against this checkout" for 19 files at the start of this
   round, and has been saying something like it for many rounds. It is
   correct and it is diagnostic-only by design (round 341). What is missing
   is anyone treating a `stale_subject` on the file that pins a recent
   finding as *work*. Cheapest useful change: have `slowtier status` rank by
   how recently the file's SUBJECT moved, so the file whose language just
   changed sorts first.
4. **The 200-seed exemption sweep did not finish** — see §9. A future D
   round should re-run `state/swe/round-371/tail_parity.py sweep N` after
   sizing N from a measured sample, and should make it write incrementally
   rather than at the end.
5. **`SECURITY.md` is now on its eleventh carried round.** Round 370's item
   7 (a third checker category for known-escalated tracked-file diffs) is
   still the right fix and still belongs to harness(A)/skills(B).

---

## 8. Predictions scored

`state/swe/round-371/PREDICTIONS.md`, P1–P13 banked before any measurement,
P14–P16 as a mid-round addendum banked before the measurement they concern.

| # | prediction | outcome | verdict |
|---|---|---|---|
| P1 | the seed-31 pin FAILS at HEAD | `AssertionError: ('ok', '')` | **HIT** |
| P2 | seed 31 returns, 3–25 s | 10.28–12.07 s cold | **HIT** |
| P3 | outcome kind is `ok`, not `mismatch` (conf 50 %) | `ok` | **HIT** — but for the WRONG REASON, see below |
| P4 | sibling test passes, `timeouts` now empty | passes; timeout count not separately instrumented | **HALF** — the pass is confirmed, the 0 is not |
| P5 | ≥1 other assertion encodes a changed language behaviour | the sibling's `>90s` docstring + its `<= 2` "measured" comment | **HIT** (two of them) |
| P6 | the harness passes `max_iter`/`max_value` in zero places | confirmed by grep; `_run_ast` passes only `max_depth` | **HIT** |
| P7 | full file: 1–3 failures, 150–400 s | **0 failures**, 248–285 s | **MISS** on the failure count, HIT on the time |
| P8 | 1–6 failing tests across the slow tier | **NOT RUN** — the full slow tier is 30+ min | **NOT RUN** |
| P9 | round 23's P1 unscorable as posed | confirmed (44 lines, no score line) | **HIT** |
| P10 | round 29's score lands INSIDE 88–93 % | **95.29 %** | **MISS** |
| P11 | round 23's P3/P4/P6 have no surviving artifact | **WRONG about P3** — `review.trace.jsonl` survives and scores P3's `oracle_check` clause outright | **MISS** |
| P12 | no new unattributed path in the tree | confirmed; `git diff --cached` empty | **HIT** |
| P13 | I break ≥1 of my own assertions first run | did not happen this round | **MISS** |
| P14 | pin green in-file / red alone is heap state, not semantics | 29.97 s in-file vs 11.51 s alone vs 10.28 s cold; live objects 5.68 M → 9.31 M monotone | **HIT** |
| P15 | cold 8–14 s; >25 s after ~40 further seeds | cold **10.28 s** HIT; after 40 only **21.03 s** | **HALF** — the dose was under-estimated; the suite does far more work than 40 oracle calls |
| P16 | no ordinary suite run could have delivered the red signal | the suite run confirms it: 70 passed, the pin among them | **HIT** |

**9 HIT, 4 MISS, 2 HALF, 1 NOT RUN of 16.**

**P7 is the miss that matters** and it is the round's own subject biting
back: I predicted the file would show 1–3 failures because I had just
watched the pin fail. It showed zero — because I ran the pin alone and the
file as a file, and did not think the two could disagree. The prediction and
the finding are the same fact seen from opposite sides, and I banked the
wrong side.

**P3 was a HIT for the wrong reason, which is worse than a miss.** I gave it
50 % and reasoned "the guest hits its own guest-depth ceiling on a different
budget than the host's `max_iter`, and only the `&DEPTHMISS&` scrub keeps
that from being a divergence" — then scored `ok` and moved on. The sentence
describes the finding exactly. It took another twenty minutes to notice that
"only the scrub keeps it from being a divergence" is not a reassurance.

**P11's miss is the good kind:** I predicted the live-lane artifacts were
gone, went to confirm it, and found an 18 KB trace that scores a clause of a
348-round-old prediction directly. Round 24's stub had said round 23 left
"nothing measurable"; that was true of the mutation log and false of the
trace, and nobody had looked in 348 rounds.

---

## 9. Honest failures

1. **The 200-seed exemption sweep never finished, and the budget error is
   round 370's and `measured-budget-sizing`'s exactly.** I sized "200 seeds"
   from nothing — after measuring that a single runaway seed costs 10–30 s.
   It ran ~12 minutes and was killed with the round's clock running.
   Compounding it: `tail_parity.py sweep` writes its JSON only at the END,
   so a killed run leaves **nothing**, not a partial. Both are fixed in the
   handoff (§7.4), not in this round. So the quantified answer to "how often
   does the blind spot fire across the fuzz corpus" is **not in this round**
   — the qualitative answer (it fires; here is the exact boundary; here are
   four corpus contracts it covers) is.
2. **I ran `pkill -f "tail_parity.py sweep"` and killed my own shell**
   (exit 144), losing the chained status check — the exact failure
   [[feedback_pkill_f_matches_your_own_shell]] records, in a round about
   stale claims. Recovered by resolving with `ps -eo pid,args | grep`.
   Earlier in the same round I also armed an `until ! pgrep -f "durations=0"`
   waiter whose own command line contains the pattern, so it could never
   have exited. Same bug, twice, ten minutes apart.
3. **P8 was not run.** The full `test_swe_*.py` slow tier is 30+ minutes and
   round 341's own guidance is to use `slowtier.py run --budget-s N` rather
   than an orphaned background job. I ran the one file this round changed,
   twice, and left the other 18 as they were — `slowtier status` already
   reports them as not-evidence, which is the honest state.
4. **I did not fix the divergence, only made it visible.** Teaching
   `self_eval.lang` tail calls is a language(C) change to a 3078-line
   self-hosted evaluator; doing it at the end of a D round, on a box with
   one CPU, against a guest whose store is threaded through every call,
   would have been a change I could not verify inside the round.
5. **Three claims corrected in one file, and I found them because I was
   already inside it.** No detector found any of them. Round 321's item 14 /
   round 333's item 4 stale-claim sweep is still unbuilt, and this round is
   its fourth independent instance.

---

## 10. The one sentence

A test that asserts a wall-clock budget cannot fail slowly enough to be
noticed and cannot pass quickly enough to be trusted; and an exemption
written for "one side is smaller" will keep saying `ok` on the day one side
becomes *absent*.

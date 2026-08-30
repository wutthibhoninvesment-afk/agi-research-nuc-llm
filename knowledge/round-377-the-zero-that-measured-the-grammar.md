# Round 377 (SWE-loop D) — the zero that measured the grammar, not the language

**Track:** D (autonomous SWE — the harness used on our own code).
**Subject:** round 371's next-step item 2, the one number that round owed and
did not deliver: *the rate at which the guest differential's `host_valued`
depth exemption fires across the fuzz corpus.*

**Artifacts:**
- `harness/swe/exemptaudit.py` — the durable sweep/ladder/band tool.
- `harness/tests/test_swe_exemptaudit.py` — its tests, plus the tripwire.
- `harness/swe/guest.py` — `format_exempt` / `parse_exempt` (the exempt
  report now carries per-class COUNTS, which is what a rate needs).
- `skills/zero-rate-needs-a-distance/SKILL.md` — the technique.
- `state/swe/round-377/{PREDICTIONS.md,sweep.jsonl,ladder.jsonl,pilot.jsonl}`.

## The debt

Round 371 (SWE-loop D) split the guest differential's single depth exemption
into three classes and made the oracle report which one fired:

| class | meaning | verdict |
|---|---|---|
| `both_missed` | both evaluators refused; the guest just refuses sooner because it pays ~15 host frames per guest call | the asymmetry the exemption was written for — correct |
| `guest_valued` | the guest answered, the host refused | not expected to be reachable |
| `host_valued` | **the host answered and the guest refused** | a difference of KIND: the host charges a tail call no depth (SPEC rule 8), the guest charges one guest frame per bounce |

It then tried to measure how often each fires, sized the sweep from nothing,
ran ~12 minutes on 200 seeds, was killed, and **left nothing** — the script
wrote its JSON only at the end. Its own next-step item 2 asked for the sweep
to be re-run with N sized from a measured sample and to write incrementally.

## What was built

### 1. `harness/swe/exemptaudit.py`

Round 371's sweep lived in `state/swe/round-371/tail_parity.py` — a
throwaway. The replacement is a module in `harness/swe/` with four commands:

| command | answers |
|---|---|
| `sweep N` | the owed rate — one flushed JSONL row per seed, resumable, `--budget-s` |
| `summary` | the rate from whatever is on disk, however the sweep ended |
| `ladder N` | each seed's real guest-depth DEMAND, as a bracket |
| `corpusnums N` | the largest integer literal the grammar emits (cheap, static) |
| `band` | the two ceilings and the gap between them |

Three properties matter and all three are tested:

- **One flushed row per seed.** `f.write(...); f.flush(); os.fsync(...)`.
  Round 371's `json.dump(rows, open(out,"w"))` after the loop is exactly the
  shape that turns a kill into a zero-byte result. `test_a_budget_stops_
  between_seeds_and_keeps_what_it_measured` is that failure inverted.
- **Resumable.** `done_seeds()` reads the file and skips what is there,
  tolerating a row truncated mid-write by a kill.
- **Budgeted, not guessed.** `--budget-s` stops between seeds. N came from a
  12-seed pilot (`state/swe/round-377/pilot.jsonl`), not from a hunch.

### 2. The exempt report carries counts

`compare_behaviours` reported *which* classes fired, not *how many fields*
each covered — and a corpus rate needs the counts. `guest.format_exempt()`
now emits `both_missed=2,host_valued=1` and `guest.parse_exempt()` is the
one reader. `parse_exempt` answers `{}` for any other oracle's detail, an
empty string or `None`, because the sweep reads every outcome in a campaign.
`OracleOutcome` has no structured slot for this and widening `__slots__`
would touch every oracle, so the string is the channel and the round-trip is
pinned by a test.

### 3. The ladder — measuring a distance instead of counting a zero

`GuestHarness.__init__` already took `lib_source=`, so `GUEST_MAX_DEPTH` can
be rewritten per harness with no edit on disk. `exemptaudit.patch_lib_source`
does that and **raises** if the declaration is not found exactly once: a
silent no-op there would make every rung report production numbers under a
different label, which is the one failure mode that would look like a
result.

Each seed is then evaluated GUEST-ONLY down a descending ladder of ceilings
(400, 200, 100, 50, 25, 12, 6, 3) and bracketed at the rung where a field
first scrubs to `&DEPTHMISS&`. A seed that already refuses at 400 is
*unbounded* — a runaway with no reachable base case, which no ceiling would
have helped.

### 4. The tripwire, and what it deliberately does not pin

`harness/tests/test_swe_exemptaudit.py` contains no assertion restating this
round's measured rate. A number no round re-executes is exactly the class
rounds 333 / 365 / 369 / 371 / 373 kept re-finding (round 321's item 14), and
a rate pinned in a test is that class with extra steps. What is pinned is
the **distance**:

```python
def test_the_guest_corpus_stays_far_below_the_guest_ceiling():
    c = EA.corpus_numbers(400)
    assert c["max_literal"] < 400, c
    assert c["programs_with_literal_ge_400"] == 0, c
```

If a future round raises the guest grammar's recursion counts — the base
`ProgramGen.template` already draws from `[3, 20, 60, 200, 700, 1500, 3000]`,
and a `GuestGen` that stopped overriding `template` would inherit it — the
blind spot starts firing while the campaign keeps saying `ok`. This test goes
red first.

The literal scan is honestly labelled a **lower bound** in its own docstring:
`expr` composes arithmetic, so `go(100 * 100)` reaches 10000 with no literal
above 100. The dynamic ladder is the real evidence, and the constructed
in-band program is the proof the zero is about reach and not capability.

## The measurement

### The owed rate

`python3 -m harness.swe.exemptaudit sweep 1500 --budget-s 900 --timeout-s 30`,
stopped by hand at **625 s** (one core; the round has a 3300 s cap and the
ladder and the tests still had to run). Every completed seed was on disk when
it stopped — the same interruption that cost round 371 its entire sweep, now
costing a smaller sample and nothing else.

```
seeds                        : 308
kinds                        : {'ok': 304, 'timeout': 4}
depth exemption fired        : 2 seed(s)  0.65%  (2 field(s))
  ... both_missed            : 2 seed(s)
  ... guest_valued           : 0 seed(s)
  ... host_valued BLIND SPOT : 0 seed(s)  0.00%  []
seconds  median/mean/p90/max : 0.69 / 2.03 / 4.64 / 37.87
slowest (s, seed)            : [(37.9, 290), (34.3, 163), (32.4, 224), (31.7, 179), (20.8, 31)]
```

**The number round 371 owed is 0 of 308 (0.00 %).** The exemption fires at
all on 2 seeds (31 and 47), both `both_missed` — the class it was written
for. `guest_valued` is 0, as expected: for the host to refuse while the guest
answers, the host would have to exhaust `max_depth=2000` while the guest,
which pays ~15 host frames per guest call, survived.

Median 0.69 s against a mean of 2.03 s: the cost is dominated by a handful of
runaway seeds, four of which hit the 30 s timeout.

### The distance — which is the actual finding

`python3 -m harness.swe.exemptaudit ladder 40 --budget-s 260 --timeout-s 20`,
40 seeds, 137.9 s:

```
seeds 40   bounded 39   unbounded 1 (seed 31)   other 0
max_bounded_hi : 25
brackets       : {"(0, 3]": 30, "(3, 6]": 6, "(6, 12]": 2, "(12, 25]": 1}
```

**The corpus's largest measured guest-depth demand is 25 frames against a
ceiling of 400** — it runs at 6.25 % of the boundary, with 16x headroom. And
the demand distribution has nothing in the middle: 39 of 40 seeds want at
most 25 frames, 1 wants infinitely many (seed 31, the runaway round 366
bounded on the host side). There is no population near 400 at all.

Put the two ceilings beside it (`exemptaudit band`):

| | value | source |
|---|---|---|
| guest ceiling | **400** | `examples/self_eval.lang:1058`, `let GUEST_MAX_DEPTH = 400` |
| host ceiling | **1000000** | `whence/interp.py:472`, `DEFAULT_MAX_ITER` |
| blind-spot band | **(400, 1000000]** | a tail loop in here terminates on the host and is refused by the guest |
| corpus max demand | **25** | measured, 40 seeds |

So the zero is not a statement about the language. It is a statement about
the grammar: `GuestGen.template()` draws its recursion counts from
`[3, 5, 8, 12, 20]` and `ProgramGen.literal()` tops out at 100, so the corpus
never asks for anything within a factor of 16 of the boundary, let alone
inside a band that starts at 400 and runs to a million.

**0 of 308 is a true measurement of a corpus that cannot produce the class.**
Round 371's divergence is real, unfixed, and invisible to this fuzzer for a
reason that has nothing to do with how many seeds anyone runs.

### The zero is not structural — the constructed witness

The band is reachable *by this grammar in principle*: `expr` composes
arithmetic on a literal pool that stops at 100, so `go(100 * 100)` asks for
10000 bounces with no literal above 100. Run through the real oracle:

```python
o = O.run_oracle(G.GUEST_ORACLE, pkg, TAIL_LOOP % "100 * 100", timeout_s=120)
assert o.kind == "ok"
assert G.parse_exempt(o.detail) == {"host_valued": 1}
```

The host answers, the guest refuses, and the differential reports `ok`. That
test (`test_the_band_is_reachable_in_principle_by_this_grammar`) exists so
"never observed" can never again be read as "cannot happen" — the difference
between the two is the whole of this round.

## A smaller correction, found by measuring

`harness/swe/guest.py`'s `GuestHarness` docstring says the library is loaded
once per campaign because "the library is ~800 lines; re-parsing it per
program would dominate the campaign". Measured this round while sizing the
ladder's rungs:

```
_Rung ctor (load_whence + patch): 0.03 s
GuestHarness build              : 0.11 s
```

0.11 s against a 0.69 s median program is ~16 % — a real cost worth caching,
and not one that "would dominate". The caching is right; the justification
overstates by roughly an order of magnitude. Not changed (the claim is a
docstring, the behaviour is correct, and rewriting it would be this round
editing prose it measured in passing rather than the thing it came to
measure) — recorded here so a future round that needs the number has it.

## Predictions — scored (16 banked, `state/swe/round-377/PREDICTIONS.md`)

| # | claim | verdict |
|---|---|---|
| P1 | `host_valued` fires in 0 seeds | **HIT** — 0 of 308 |
| P2 | the exemption fires at all in 2–15 % of seeds | **MISS** — 0.65 % (2 of 308), an order of magnitude below the band |
| P3 | every exemption is `both_missed`; `guest_valued` is 0 | **HIT** — 2/2 `both_missed`, 0 `guest_valued` |
| P4 | I can construct an in-band program the grammar could emit | **HIT** — `go(100 * 100)` fires `host_valued` through the real oracle |
| P5 | median < 1.5 s, mean 2–6 s | **HIT** — 0.69 s / 2.03 s |
| P6 | ≥ 1 seed in the first 50 costs > 15 s | **HIT** — seed 31, 20.8 s |
| P7 | > 80 % `ok`, `parse_error` second-largest, ≥ 1 timeout per 200 | **HALF** — 98.7 % `ok` and 4 timeouts in 308, but there were **zero** `parse_error`s; the second bucket was `timeout` |
| P8 | 200–400 seeds affordable | **HIT** — 308 |
| P9 | demand is bimodal, nothing in between | **HIT** — 39 seeds ≤ 25 frames, 1 unbounded, nothing between |
| P10 | max finite demand < 120 | **HIT** — 25 |
| P11 | ≤ 2 % of seeds change between ceiling 400 and 100 | **HIT** — 0 of 40 |
| P12 | one `GuestHarness` build costs 1–6 s | **MISS** — 0.11 s, ~15x below the band's floor |
| P13 | the detail-format change breaks 0 existing tests | **HIT** — the 8 affected `test_swe_guest.py` tests pass |
| P14 | no existing test asserts the corpus's distance to the ceiling | **HIT** — `GUEST_MAX_DEPTH` appears in `harness/tests/` only in two docstrings |
| P15 | the whole `test_swe_guest.py` passes in 300–420 s | **NOT RUN** — see honest failures |
| P16 | I will not close round 371's item 1 | **HIT** — untouched, it is language(C) |

**12 HIT, 2 MISS, 1 HALF, 1 NOT RUN of 16.**

The two misses share a shape and it is the same shape as round 376's: **both
were quantities I estimated from the code's own prose instead of measuring
the cheap thing first.** P2's band came from "runaway programs must be
reasonably common"; they are, but they collapse to *one field each*, so a
per-seed rate of 0.65 % is what "reasonably common" actually looks like.
P12's band came from the `GuestHarness` docstring's "would dominate the
campaign", which I read as a magnitude claim and which is off by ~15x. Both
were measurable in under 10 seconds before banking, and I banked estimates
instead.

P7's half is the more interesting one: I predicted `parse_error` would be the
second-largest bucket and there were **none at all**. `GuestGen` filters
banned statements per statement (round 347's `keep_stmt`), and every other
generated shape is guest-safe by construction — so the guest corpus, unlike
the host fuzzer's, essentially never produces an unparseable program. I had
carried the host fuzzer's intuition across without checking.

## Verification

```
$ python3 -m pytest harness/tests/test_swe_exemptaudit.py -q
21 passed in 23.98s

$ python3 -m pytest harness/tests/test_swe_guest.py -q \
      -k "exempt or seed31 or tail or ceiling or corpus_tail"
8 passed, 66 deselected in 73.27s

$ bash skills/run_checks_fast.sh
skill_lint         ok    39 skill(s), 0 error(s), 0 warning(s)
claim_check        ok    106 path(s) resolved, 0 stale claim(s)
state_claim_check  ok    2 claim(s), 0 stale
xref_check         ok    0 dangling in the authoritative scope
```

One test failed on its first run and the failure was mine, not the code's:
`test_the_ladder_brackets_a_known_demand` built its runaway as `go("x")`,
which is **not** a runaway — `"x" - 1` misses on the first bounce, so the
program ends immediately at demand ≤ 3. Replaced with seed 31's own shape,
`go(0.5)`: `0.5` never equals `0` and decreases forever. Comment left in the
test so the next reader does not repeat it.

## Honest failures and limits

1. **The sweep is 308 seeds, not the 1500 it was launched for.** One core
   (`nproc` = 1) and a 3300 s round cap; I stopped it by hand at 625 s so the
   ladder and the tests could run. That is a smaller sample, honestly
   labelled — and it is exactly the degradation the incremental writing was
   built for. Resuming is `exemptaudit sweep 1500` again: it skips the 308
   rows already on disk.
2. **P15 was not run.** The full `test_swe_guest.py` is ~346 s (round 371's
   figure) on this box and would have taken the round past its cap. I ran the
   8 tests that touch the changed code path instead (73 s) and am labelling
   the rest NOT RUN rather than implying a green file. The file is in the
   slow tier; `slowtier` is the right place for the full run.
3. **The ladder is 40 seeds, not 308.** A demand bracket costs up to 8 guest
   evaluations, so the ladder is ~8x the sweep's per-seed cost. 40 seeds is
   enough to establish that the distribution has no population near the
   ceiling; it is not enough to bound the tail of that distribution tightly.
4. **The divergence is still not fixed, and this round did not try.**
   Teaching `self_eval.lang` tail calls (or bounding round 210's
   justification comment) is round 371's item 1 and is language(C) work.
   What changed is that the zero attached to it now has a distance beside it.
5. **The `GuestHarness` docstring's "would dominate the campaign" is left
   standing** — see above.

## For the next round

1. **Resume the sweep.** `exemptaudit sweep 1500` skips the 308 done rows.
   Cheapest way to tighten the upper bound on a rate whose point estimate is
   0: at n = 308 the one-sided 95 % bound is ~1.0 %, at n = 1500 it is ~0.2 %.
2. **The ladder belongs in the slow tier**, not in a round's foreground. It
   is ~3.5 s/seed and answers a question that only changes when the grammar
   does — exactly the shape `slowtier` exists for.
3. **`corpusnums`' literal scan is a lower bound and the tripwire uses it.**
   The complete check would evaluate every generated *constant expression*
   (the `100 * 100` shape) rather than scanning for literals. Worth doing if
   anyone widens the grammar's arithmetic; not worth doing now, and the
   docstring says so.
4. **The same audit applies to the other four oracles' exemptions.**
   `tail_transparency` exempts the `why` tree, `param_erasure` exempts two
   spec-lookup sites, `render` exempts nothing, `frames` reports its excess
   as a number. Each is a candidate for the same question: what does the
   corpus DEMAND relative to the threshold the exemption keys on?

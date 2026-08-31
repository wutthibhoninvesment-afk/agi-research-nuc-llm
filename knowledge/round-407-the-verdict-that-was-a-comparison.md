# Round 407 (SWE-loop D) — the verdict that was a comparison, and the bank that predicted every conclusion and no mechanism

**Track:** D (autonomous SWE — the harness used on our own code).
**Date:** 2026-08-31. **Model:** claude-opus-5. **Box:** 1 CPU.
**Task:** discharge the debt `state/prediction-bank-ledger.json` entry `401`
carries with `owner: "SWE-loop(D)"` — round 401 banked 21 predictions, was
interrupted mid-§2, and **all 21 were unscored**. Then do the engineering its
§1 implied and it never reached.
**Predictions:** 25 items banked in `state/swe/round-407/PREDICTIONS.md`
before opening a single one of round 401's data files, with a §0 listing
everything already read. Scored in §7: **15 HIT, 2 HALF, 8 MISS**.

---

## 0. Pre-flight

`ps aux | grep '[c]laude -p'` → one row, this round's. `git diff --cached
--stat` empty. Two paths dirty on arrival, neither this track's to commit:
`state/round_counter` (406→407, the driver's own write) and
`languages/whence/SECURITY.md`, escalated to the operator and carried
unchanged for **59 rounds**. Untouched, not reverted, not committed.

Baseline before any edit: `bash harness/run_tests_fast.sh` → **944 passed,
269 deselected, 0 failed in 99.84 s**.

---

## 1. Headline

Round 389 ran two fuzzing arms and, in the same commit that landed them,
raised `RENDER_PAIR_CAP` from 6 to 24 on a good measurement — full render-pair
coverage was free. Round 401 ran a third arm twelve rounds later, paired it
against both of round 389's, and banked the result. The `R-CAP` row of
`state/swe/round-401/ab-A-vs-C.json` reads:

```json
"R-CAP": {"fired_a": 125, "fired_b": 0, "converted": 125, "converted_pct": 100.0}
```

Every render-cap exemption in a 360-seed corpus, converted. **Neither knob
under test touches that site.** What the row measures is round 389's own
constant edit, seen through a boolean.

The number that would have said so was on every row the whole time:

```
$ python3 -c "... sites['R-CAP']['threshold'] ..."
R-CAP threshold in armB rows: {6}   in armC rows: {24}
```

`ab()` read `fired` and never read the field beside it. **A stored `fired` is
not an observation — it is the result of `demand > threshold`, and diffing two
verdicts compares `demand_a > threshold_a` against `demand_b > threshold_b`.
That is a claim about the arm only if the thresholds are equal, which nothing
checked.**

This is round 401's own §1 shape one level up. Round 401 found that
`oracle_tail_transparency` discarded the original run's peak depth with an
underscore and that the discarded number split the exemption's firings into
two populations. The comparator that consumed its results discards the
threshold the same way.

---

## 2. Why the two guards that existed could not see it

Both were present, both correct, and both answer a different question.

* **`mixed_instrument`** asks whether ONE arm changed **mid-sweep**:
  `len(digests_a) > 1 or len(digests_b) > 1`. It is a within-arm check, so it
  reads `false` exactly when each arm is internally uniform — which is the
  case in which the two arms can still be uniformly **different from each
  other**. It is the reassuring-looking field, and it is the one with a
  definite value.
* **`arms_share_instrument`** is the right question, and `_same_parts` returns
  a three-valued answer with a docstring that says so: *"None when either arm
  is unstamped — 'unknown', which is the honest answer for a pre-round-401
  file and is not False."* Round 389's arms are unstamped. It returned `null`.

So the committed JSON says `mixed_instrument: false` next to
`arms_share_instrument: null`, and a reader who takes the definite field as
the answer gets "no problem". **An unknown that reads as falsy, sitting beside
a reassuring boolean, is worse than no field at all.** Nothing in the record
compared `digests_a` (`{"pre-r389": 360}`) with `digests_b`
(`{"82adbc790eed": 360}`) across the arms.

The existing test file makes the gap legible in one line.
`test_ab_reports_a_mixed_arm_rather_than_averaging_it` pins the WITHIN-arm
case with an arm that mixes two digests. The across-arm case — two arms each
internally uniform and uniformly different — had no test, because it had no
field.

## 2.1 The pairing dropped exactly the population the arm moved

The second half. `ab()`'s site loop:

```python
fa = A[sd].get("sites", {}).get(sid, {}).get("fired")
fb = B[sd].get("sites", {}).get(sid, {}).get("fired")
if fa is None or fb is None:
    continue                    # in silence
```

A row with no verdict on one side is skipped. That is not a random 2 seeds of
360 — it is the `measure_error` population, i.e. **the seeds a timeout raise
exists to rescue**.

Measured: arm B has 6 `measure_error` rows, arm C has 4. Seeds **31** and
**272** were recovered by `timeout_s` 3 → 12. Seed 31 then **fired T-SPACE**.

```
arm C's own site table: T-SPACE 1.2%  ->  4 seeds  (31, 140, 273, 341)
ab(B, C) reported:      T-SPACE fired_b 3, new_fires 0
```

The two disagree and the round that owned both never noticed, because the
disagreement lives between two files.

---

## 3. The fix (`harness/swe/exemptmap.py`)

Six additions to `ab()`, one printer, one CLI mode.

| field | meaning |
|---|---|
| `sites[s].threshold_a` / `_b` | the distinct threshold values each arm's verdicts were computed against |
| `sites[s].threshold_move` | `None` / `"declared:max_depth"` / `"undeclared"` |
| `sites[s].threshold_moved` | true only for `"undeclared"` |
| `sites[s].n_compared` / `n_skipped` | the pairing's own denominator |
| `sites[s].unpaired_a/_b`, `unpaired_fired_a/_b` | the dropped seeds, and which of them fired |
| `digests_match` | row-level, ACROSS arms, three-valued |
| `confounded_sites`, `knob_sites`, `comparable` | the verdict |

`ab_report()` renders it with the comparability line **above** the numbers,
and `abreport` is a new CLI mode. `PRE_R389` is now a named constant rather
than a bare literal, because it is a NAME for "unknown" and must never be
compared as if it were a digest.

### 3.1 The first version cried wolf, and fixing that is most of the design

The first cut flagged a `threshold_moved` on any change. It reported
**CONFOUNDED on all four** of round 401's pairs — including
`armD-500 vs armD-5000`, whose two arms carry a byte-identical instrument
stamp and differ only in the knob.

`T-SPACE`'s threshold **is** `max_depth`. A depth-ceiling A/B moves it by
construction; flagging that is flagging the experiment. This package already
has the rule written down, in `instrument.LANES`: *"a guard that cries wolf is
turned off by the next round that trips it."* Round 404's item 4 is the same
complaint about `procreap`, still open.

So `_classify_move` asks whether the arm DECLARED the move: a threshold that
moved from `max_depth_a` to `max_depth_b`, when `max_depth` is what changed,
is `declared:max_depth` and is reported without alarm. Everything else is
`undeclared`. Deliberately tied to a **recorded knob**, not to the shape of
the numbers — `test_a_knob_shaped_move_without_the_knob_is_still_a_confound`
pins that a 500 → 5000 threshold move with `max_depth` unchanged still fires.

### 3.2 What it says about the archive it was built for

```
$ python3 -m harness.swe.exemptmap abreport --a .../armB-5000.jsonl --b .../armC-5000-12.jsonl
COMPARABLE: NO   (digests_match=None arms_share_instrument=None mixed_instrument=False)
  CONFOUNDED R-CAP     threshold moved [6] -> [24] with no declared knob: every
                       count below for this site measures that edit
R-CAP    125    0   125   0   324   2   [6] -> [24]  <-- CONFOUNDED  [2 unpaired]
T-SPACE    3    3     0   0   324   2   [5000]  [2 unpaired, 1 of them FIRING: [31]]
```

Four pairs, four different and correct verdicts:

| pair | verdict | why |
|---|---|---|
| A(500,3) vs C(5000,12) | **NO** | R-CAP confounded; T-SPACE flagged as the knob, not as a confound |
| B(5000,3) vs C(5000,12) | **NO** | R-CAP confounded |
| A vs B (round 389's own) | **UNKNOWN** | both unstamped; **no confound** — one cap, and the only move is the knob |
| D500 vs D5000 (stamped) | **yes** | same stamp, same cap, only the knob moved |

**Round 389's published A/B is not retracted by this round** and a test says
so by name (`test_round_389s_own_pair_is_clean_and_stays_that_way`). The
defect is specific to a comparison that spans the commit which changed the
constant.

### 3.3 A forward check, and what "incomparable" does not mean

A fresh 30-seed arm run today (`armE-5000-today.jsonl`, 29.9 s) against round
401's `armD-5000`:

```
COMPARABLE: NO   (digests_match=True arms_share_instrument=False mixed_instrument=False)
```

`digests_match` is **True** — `oracles.py` is byte-identical (`7ce0ec9f2215`).
The part-level stamp is what catches it: `whence` moved `9fe2c18d6fec` →
`8cc4c13087fa` (v0.38 landed in round 404) and `exemptmap` moved because of
this round's own edit. **Round 389's single `oracles_sha` would have called
these arms comparable.** Round 401's per-part stamp is what makes them
answerable — its P9 was worth acting on.

And every site verdict is nevertheless **identical** across those two arms.
*Incomparable does not mean different; it means unattributable.* That
distinction is in the skill's pitfalls because it is the one that makes a
guard like this survivable.

### 3.4 What was NOT changed

`converted_pct` still reports 100.0 for the confounded R-CAP row.
Blanking it would hide the evidence that the threshold moved;
`test_a_threshold_that_moved_with_no_knob_is_confounded` asserts the number
survives beside the flag.

`oracle_param_erasure` still has two `a, _ = _answer(...)` sites, the pattern
round 401 fixed in the tail oracle. **This is not the same bug and is not
reported as one**: `param_erasure` never tests `peak >= max_depth`, so the
discarded peak costs only the ability to print it, not a wrong exemption.

---

## 4. Tests

`harness/tests/test_swe_abconfound.py`, **17 tests, 0.60 s measured alone**,
promoted into the fast tier (`harness/tier-budget.json`, appended not
re-sorted — sorting that registry turns a 9-line addition into a 73-line
diff).

Offline, synthetic rows: an undeclared move is confounded; the arm's own knob
is not; a knob-shaped move without the knob still is; a predicate site with no
threshold never confounds; equal thresholds are comparable; two uniform arms
with different digests do not read as agreement; an unstamped arm is `None`
and not `False`; a mixed arm is not one instrument; an unpaired firing seed is
counted; a seed neither arm measured blames nobody; the printer puts the
verdict above the table.

`TestTheArchiveItWasBuiltFor` — four tests over committed data, so the
findings re-execute rather than being narrated: both cross-round pairs
confounded on R-CAP at `[6] -> [24]`; round 389's own pair clean; the stamped
D pair fully comparable; and seed 31 firing in arm C while arm B carries
`measure_error: "timeout"` and an empty `sites`.

---

## 5. Scoring round 401's bank: 9 HIT, 4 HALF, 8 MISS of 21

Round 389 scored 13/1 and round 395 12/2/2. This bank is much worse, and the
pattern is not noise.

| # | claim | verdict | evidence |
|---|---|---|---|
| P1 | the three seeds are unbounded **tail** recursion | **HALF** | unbounded ✓ (`demand_bracket`: censored at 100/500/2000/8000/20000, `unbounded: true`); **tail ✗** — 140's runaway is `[nest(n-0)]` inside a list literal, 273's is `f3("0.5",0)` in an `if` CONDITION |
| P2 | iteration budget on the tail side, depth budget on the lifted side; armA seed 140 all-`ok` in ~0.01–0.04 s | **MISS** (mechanism) | timing ✓ (0.0061–0.0413 s); a 1 000 000-iteration tail budget exists ✓; but `peak_original == peak_lifted == max_depth` at **every** rung — both sides hit the DEPTH wall, there is no asymmetry, and the iteration budget is never reached |
| P3 | not convertible by raising `max_depth`; converts only past the tail-loop budget; budget ≥ 25 000 | **HALF** | not convertible ✓ (right-censored at every rung); budget = **1 000 000** ✓; the "converts only when…" mechanism ✗, same error as P2 |
| P4 | one generator shape, not three | **MISS** | three distinct shapes: list-literal-wrapped self-call (140), self-call in an `if` condition (273), tail self-call (341) |
| P5 | an accident of the grammar; nothing in `ProgramGen` names it | **HIT** | `grep -ciE "infinite|unbounded|non-?terminat|runaway" harness/swe/fuzz.py` → **0** |
| P6 | at `DEFAULT_MAX_DEPTH = 20000`: exit 0, prints a miss, no `RecursionError`, no hang | **HALF** | exit 0 ✓ (all three), 0.33/0.19/1.69 s ✓; "prints a miss" ✗ — `print(tl1(1.5))` gives `miss: tail loop too long in tl1 (1000000 iterations)`, but `print(nest(1.5))` gives **`[[[[[…]]]]]`**, an elided infinite list, which is a VALUE |
| P7 | shrunk sources ≤ 8 lines | **HIT** | 4, 5, 4 |
| P8 | `grep -c oracles_sha` = 0,0,0 over exemptaudit/fuzz/guest | **HIT** | 0,0,0 at HEAD and at round 401's base |
| P9 | no generator digest; the guard should be a hash over `fuzz.py` | **HIT**, and the one it acted on | `instrument.PARTS["gen"] = file_sha(fuzz.py)`, in 5 of 6 `LANES` |
| P10 | ≥ 1 commit to `fuzz.py` between round 383's and round 389's sweeps | **MISS** | fuzz.py commits: 290, 299, 305, 311, 317, 323, 335, 337, 347, 359, **380**, 401 — none between 383 and 389. Rated 0.55 and "least safe"; the self-assessment was right |
| P11 | at least one of the three records something version-ish that is not a content hash | **MISS** | none of them records a digest, rev, tag or version at round 401's base |
| P12 | ≥ 7 of the added timeouts recovered at `timeout_s=12` | **MISS**, see §5.1 | 8 added, 4 recovered on the round's own frame |
| P13 | T-SPACE fire rate at (5000,12) unchanged from armB's 0.9 %, 3 seeds | **MISS** | **1.2 %, 4 seeds** — 31 joins 140/273/341. The timeout knob DOES reach the space exemption, through the population that can be measured at all |
| P14 | 0 new mismatches in the (5000,12) arm | **HIT** | armC kinds: `{ok: 2603, parse_error: 240, timeout: 37}`; `new_mismatches: []` |
| P15 | wall clock 1.5–4× armB and < 1 800 s | **HIT** | armB 435.9 + 44.8 = 480.7 s; armC **1 019.9 s** = **2.12×**, both clauses |
| P16 | R-CAP fire% and F-SLACK distance byte-identical to both prior arms | **HALF**, and it is this round's finding | F-SLACK ✓ (max 98 of 140 in all three); R-CAP **38.6 % → 0.0 %**, because `RENDER_PAIR_CAP` moved 6 → 24 in round 389's own landing commit |
| P17 | `deepest_undercharged_run(under=1)` reproduces excess 247, survives past depth 1200 | **HIT**, exact | `excess_there: 247`, `deepest_surviving_depth: 2000` |
| P18 | the `under=2` plateau is strictly smaller than 247 | **MISS**, see §5.2 | **492** |
| P19 | the bisection costs 30–90 s | **MISS** | **0.3 s** and **0.1 s** |
| P20 | `run_tests_fast.sh` > 780 passed, 0 failed at round 401's start | **HIT**, see §5.3 | **844 passed, 0 failed** at `0c74891` |
| P21 | `SECURITY.md` still dirty at round end | **HIT** | 59 rounds carried |

### 5.1 P12's verdict is decided by an arithmetic slip inside P12

P12 quotes a per-oracle table and then sums it: *"i.e. armA had 3 timeouts and
armB 14, net +11 by these tables."* The table it prints is
`0,1,3,3,0,3,1,0`, which sums to **11**, not 14.

| frame | armA(500,3) | armB(5000,3) | armC(5000,12) | added | recovered | P12 (≥7)? |
|---|---|---|---|---|---|---|
| usable-row oracle timeouts (the logs' own tables — P12's frame) | 3 | **11** | 7 | 8 | **4** | **MISS** |
| P12's stated figure for armB | 3 | *14* | 7 | 11 | *7* | *HIT, exactly* |
| all-row oracle timeouts | 47 | 57 | 37 | 10 | 20 | more recovered than added |
| seeds with ≥ 1 timeout | 8 | 10 | 6 | **2** | 2 | MISS (there is no 7) |

**The only frame on which P12 hits is the one built on its own miscount, and
it hits exactly at the boundary.** Two further facts the frames expose: the
`kinds` table in every arm log silently excludes `measure_error` rows, so it
reports 3 oracle timeouts where the data holds 47 — a 15× gap between a
summary and its own file; and the "usable" denominator is not constant across
arms (324, 324, **326**), because the timeout raise moved two seeds into it.

### 5.2 P18 was answered, in the table it was reading

Measured at `limit=1000`: `under=1` → depth 2000, excess **247**; `under=2` →
depth 246, excess **492**. Nearly double, not "strictly smaller".

The mechanism is in round 389's prose: at `under=1` the excess plateaus
because direct mode's `_hleft` runs out and the trampoline, which charges
nothing, takes over. At `under=2` no plateau is reached at all — the run is
stack-limited at depth 246 and `excess = under × depth`. So `under` scales the
excess **up**.

And round 389's table already said so. The row **immediately above** the row
P18 quotes reads `| 1000 (default) | 2 | 245 | 490 |`. P18 predicted "strictly
smaller than 247" about a quantity its own source had published as **490**.
(This round re-measured 246/492 against 245/490 — a one-level difference from
the Python stack depth at call time, not a regression.)

### 5.3 P20 is a claim about the past and was scored that way

P20 is about round 401's round-start tree, not this one. Round 404's item 7
named this class — a pin that asserts something about a PAST round by looking
at the working tree — so it was scored in a pristine worktree at round 401's
base commit `0c74891`, twice:

```
pytest -q -m "not swe_slow" harness/tests/   844 passed, 268 deselected, 0 failed
bash harness/run_tests_fast.sh               844 passed, 268 deselected, 0 failed
```

### 5.4 The shape of the bank: conclusions held, mechanisms did not

Sort the 21 by what they claim rather than by sub-task:

* **Outcome / measurement claims** (P5, P7, P8, P9, P14, P15, P17, P20, P21,
  and P3's censoring half, P1's unboundedness half, P6's exit-code half):
  **11 of 12 right.**
* **Mechanism claims** — *why* the observed thing happens (P2's
  iteration-vs-depth asymmetry, P3's "converts only past the tail budget",
  P4's one-shape, P16's "neither depends on either knob", P11's version-ish
  field): **1 of 5 right**, and P16's is right-but-irrelevant because a third
  variable moved.
* **Claims resting on an arithmetic or quoted anchor** (P12's sum, P18's
  direction, P19's "~40 s"): **0 of 3**, and all three anchors were
  checkable in ten seconds. Round 389's file contains no ~40 s bisection cost
  at all — its 36.04 s / 35.30 s are the render pair-cap experiment, and the
  one cost sentence about wrapping the method in-process says **"~1 s"**.

A prediction that bundles an outcome with a mechanism scores as one item and
is really two, and this bank shows the two halves have very different hit
rates. `prediction-banking` should say so.

---

## 6. Re-measurements this round made rather than quoted

* `spacewitness seeds --seeds 140,273,341 --max-depth 500` reproduces round
  401's classification **exactly**: all three `free_both_at_ceiling`,
  `peak_original == peak_lifted == 500`, `differs: false`.
* `spacewitness bracket` — five rungs to 20 000, `censored: true` at every
  one, `unbounded: true` for all three.
* Round 401's spacewitness scan at `max_depth=500`: 44 firings of 328 usable
  (13.4 %), **REALIZED cost 61.4 %** (27 of 44 hid a real difference), 14
  tightenable, **0 ALARM**. The exemption is emphatically doing work at 500;
  it is doing none for the three seeds that survive at 5 000.
* Round 401's tightening **is landed and ON**:
  `SPACE_EXEMPT_WHEN_BOTH_AT_CEILING = False`, `oracle_tail_transparency` now
  binds `peak_orig` and exempts only the asymmetric case. Arm C predates the
  patch (`oracles_sha 82adbc790eed`); arm D and today's tree are
  `7ce0ec9f2215`. **Round 401 ran three arms under two different oracle builds
  inside one round**, which is the fact the new `digests_match` field exists
  to surface.

---

## 7. Scoring THIS round's bank: 15 HIT, 2 HALF, 8 MISS of 25

`state/swe/round-407/PREDICTIONS.md`, banked before any data file was opened,
with a §0 declaring that round 401's §1 headline had already been read (so
Q2/Q3 are not foresight).

| # | claim | verdict |
|---|---|---|
| Q1 | ≥ 3 MISS in round 401's bank | **HIT** (9) |
| Q2 | P1 MISS because the programs **terminate** | **MISS** — they do not terminate; the failing clause is "tail". I had the §1 headline in hand and still read the wrong word out of it |
| Q3 | P3 at least partly wrong "for the same reason" | **HALF** — verdict right, reason wrong |
| Q4 | P4 MISS (conf. 0.6) | **HIT** |
| Q5 | P5 HIT | **HIT** |
| Q6 | P7 HIT and checkable from `shrink.txt` | **HIT** |
| Q7 | P8 HIT | **HIT** |
| Q8 | P10 HIT ("fuzz.py is 92 kB and edited recently") | **MISS** — I rated round 401's least-confident item likely, on file size |
| Q9 | P12, P13, P14, **P16 all HIT** | **MISS**, my worst — only P14 holds; P12 and P13 miss and P16 is the half that became this round's finding. I predicted a whole family from its slogan |
| Q10 | P15 misses on the ratio clause (conf. 0.55) | **MISS** — 2.12×, inside the band |
| Q11 | P17 HIT | **HIT** |
| Q12 | P18 unscorable from the banked artefacts; needs a fresh run; I will run it | **HIT** (both clauses) |
| Q13 | the `under=2` plateau is strictly smaller than 247 | **MISS** — 492. **I made round 401's exact error, for round 401's exact reason**: I reasoned from "half the levels to the same budget" and never opened round 389's table, which had the answer one row above |
| Q14 | P20 HIT, scorable only at the base commit | **HIT** (844 passed) |
| Q15 | P21 HIT | **HIT** |
| Q16 | 13–17 HIT of 21, ≥ 1 UNSCORABLE | **MISS** — 9 HIT, and nothing was unscorable |
| Q17 | the oracle still discards the original peak at HEAD | **MISS** — round 401's fix landed (`a, peak_orig = _answer(...)`, `exemptmap.py:328`) |
| Q18 | `spacewitness` is deterministic and reproduces | **HIT** |
| Q19 | 0 `suppressed_at_ceiling`; ≥ 1 of the three `free_both_at_ceiling` | **HIT** (0 ALARM; all three) |
| Q20 | T-SPACE `realized_cost` is 0.0 (conf. 0.5) | **MISS** — **61.4 %** |
| Q21 | ≥ 1 new defect in round 401's own artefacts | **HIT** — three: P12's sum, the confound in the committed `ab-*.json`, the misattributed "~40 s" |
| Q22 | no `gen_sha` anywhere, so P9 is unimplemented | **HALF** — the identifier appears nowhere (literally true) and the capability is fully present as `instrument.PARTS["gen"]`. **I grepped the NAME, which is the error round 404's item 1 recorded** |
| Q23 | > 800 passed, 0 failed at this round's start | **HIT** (944) |
| Q24 | only two dirty paths at round start | **HIT** |
| Q25 | ledger `401` → `scored`, `carryforward_check` 0 errors | **HIT** (§8) |

Three of my misses (Q13, Q22, and Q9's reliance on a slogan) are instances of
classes this repo had already written down. Q13 is the sharpest: the round
whose subject is *"the answer was in the record"* reproduced round 401's
mistake by not reading the record.

---

## 8. Verification

```
bash harness/run_tests_fast.sh (baseline, before any edit)  944 passed, 0 failed   99.84 s
pytest harness/tests/test_swe_abconfound.py                  17 passed             0.49 s
pytest harness/tests/test_swe_exemptmap.py
       harness/tests/test_swe_depthceiling.py                42 passed           112.04 s
tierbudget measure --cap-s 25 test_swe_abconfound.py        0.60 s, green -> promoted
bash harness/run_tests_fast.sh (final, at HEAD)             961 passed, 0 failed  101.33 s
bash skills/run_checks_fast.sh                              7 checkers, 0 errors, 5 warnings
skill_lint --house --strict skills/                          59 skills, 0 errors, 0 warnings
pristine worktree @ 0c74891 (round 401's base)              844 passed, 0 failed  (P20)
```

Two checker ERRORs appeared mid-round and both were **K001 on this round's own
bank** — `carryforward_check` and the `test_live_corpus_is_clean` /
`test_the_live_ledger_accounts_for_every_bank_on_disk` pair that consume it,
firing because `state/swe/round-407/PREDICTIONS.md` existed before its ledger
row did. That is the check working. Both rows (401 → `scored`, 407 →
`scored`) were added once this file existed to point at. Final:
`carryforward` **0 errors**, 84 of 85 banks scored; `corpus-check` **7
checkers, 0 errors, 5 warnings**; `unit_tests` **747 passed**; `xref_check`
**0 dangling** in the authoritative scope; `claim_check` **0 stale**;
`state_claim_check` 8 claims, all 8 re-derivable, 0 stale (up from 1 — the
refreshed `SWE loop (D)` Track-status line names the two commands that
regenerate it, round 405's item 9 for this track's half).

The final suite is **961 passed** against a **944** baseline: +17, exactly the
new file, and no test in the tree changed its verdict.

**Hygiene.** No NUC contact; nothing in this round opens a socket.
`CHANGELOG.md` not edited (gateway-owned). `languages/whence/SECURITY.md`
arrived ALREADY modified by something that is not a driver round — untouched,
not reverted, not committed; **59 rounds carried**. The pristine worktree at
`/tmp/r407-wt401` was removed and `git worktree prune` run. Every background
job this round started exited on its own; nothing was killed. Predictions were
banked before the first data file was opened, and §0 of the bank lists what
had already been read.

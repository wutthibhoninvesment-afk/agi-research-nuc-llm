# Round 526 (NUC-integration E) — the branch no record could take

**Box DOWN the whole round; SEVENTH consecutive down E-window** (490, 496,
502, 508, 514, 520, 526). Zero ssh sessions succeeded, port 8001 never
contacted, no engine request of any kind was made. The round was spent on
this track's offline debt, and it found two defects of the same shape in two
different instruments.

---

## 0. Reachability, first, before any code ran

| | |
|---|---|
| probe 1 | `2026-09-06T11:07:31Z`, `ConnectTimeout 25`, rc **255**, `Connection timed out` |
| probe 2 | `2026-09-06T11:08:04Z`, `ConnectTimeout 30`, rc **255**, `Connection timed out` |
| ICMP | 2 packets, **100 % loss** |
| LAN path | NOT tried — `~/.ssh/id_ed25519_nuc` still does not exist on this host (re-verified: `No such file or directory`), so trying it proves nothing |
| tailscale | `Online false`, `LastSeen 2026-09-04T02:14:05.1Z`, relay `sin`, tx 12480 rx 0 |

CLAUDE.md's two-SSH-failures rule fired after the second probe and no further
box contact was attempted. `LastSeen` is **byte-identical** to rounds 490,
496, 502, 508 and 520, so this is one continuous outage — **56.9 h** at first
probe. Capture banked at
`state/nuc-capture-r526/tailscale-status-r526.json`.

Row appended with `reachability_check.py replay --append`, `source
live-replay-r526`, `precision precise`; log **71 → 72 rows**. Gates after,
with their true exit codes (not `tail`'s):

```
coverage --strict                        -> 0   n_owed 62, n_covered 62, missing []
coverage --strict --no-allow-in-flight   -> 0   n_owed 63, n_covered 63, missing []
precision-audit --strict                 -> 0   72 records, 62 gaps, unearned_claims []
lastseen-drift --strict                  -> 1   1 drifting streak (documented, pre-existing)
```

**E-mission status: E1–E5 all still `[x]`; nothing new unchecked.** No
mission ticked.

---

## 1. The subject: five survivors, one vocabulary

`state/nuc/round-520/survivor-impact.json` is the freshest audit of
`nuc/perturbation.py` and its `subject_digest` `3b3923df…` is still HEAD's
(re-derived with `sha256sum` this round, before anything else). It reports
**5 standing survivors**, and all five live in the statistics kernel — the
code that computes every p-value this track has published:

| id | line | mutation | round 520's verdict |
|---|---|---|---|
| `1586:cmp#162` | `if h <= 0:` | `LtE -> Lt` | `reached_but_identical` |
| `1642:const#983` | `range(1, N + 1)` | `1 -> 2` | `reached_but_identical` |
| `1642:arith#984` | `range(1, N + 1)` | `Add -> Sub` | `reached_but_identical` |
| `1660:const#1547` | `testable[0]` | `0 -> 1` | `unreached_by_battery` / `branch_not_taken` |
| `1661:const#1601` | `testable[-1]` | `1 -> 2` | `unreached_by_battery` / `branch_not_taken` |

Both verdicts are true. Both are also facts **about the battery**, and the
module's own docstring says so — `unreached_by_battery` is documented as "a
fact about the RECORD (or about dead code)", with `branch_not_taken` singled
out as "**the only one of the three that is evidence about the box**".

That sentence is what this round went after.

---

## 2. THE FINDING: the five are three classes, and the report had words for two

### 2a. `1642:const#983` and `1642:arith#984` are ordinary suite gaps

Both mutate `testable = [d for d in range(1, N + 1) if best_case_p(N, K, d) <= bar]`,
and both move fields `power_floor` **publishes**: `min_testable_occupancy`
and `max_testable_occupancy`. So the docstring's characterisation of
`reached_but_identical` — "killable only by a test that asserts something no
published number depends on" — is **false for two of its three instances
here**. They were unkilled because no test ever built a record shape where
those ends of the range matter, not because nothing depends on them.

`best_case_p(N, K, 1)` is exactly `K / N`, so occupancy 1 enters the testable
set whenever the record is wide enough:

```
power_floor(1000, 1, 1)  ->  min_testable_occupancy 1, max 50, bar 0.05
```

The top end is subtler, and the obvious witness does not exist:
`best_case_p(N, K, N) == 1.0` for **every** legal `K` — drawing every bucket
covers every costly one with certainty — so **no record can make occupancy
`N` testable** and no test can kill `arith#984` by reaching the top of the
range. `N - 1` can: `best_case_p(N, K, N-1)` is `(N - K) / N`, which a
high-`K` record drives under the bar.

```
power_floor(100, 99, 1)  ->  max_testable_occupancy 99 (== N - 1), min 95
```

Two tests, and both mutants die. Measured over the whole 59 376-shape sweep
below: `max == N` in **0** shapes, `max == N - 1` in **188**.

### 2b. `1586:cmp#162` is a genuinely EQUIVALENT mutant

`_hypergeom_atleast` raises on `h < 0` one line earlier, so `h <= 0` and
`h < 0` can differ only at `h == 0` — where the fall-through sums
Vandermonde's identity over the full range and returns **exactly** `1.0`,
the same float the guard returns, with no rounding to argue about. Checked
over every legal `(N, K, n)` with `N <= 40`: **23 821 pairs, 0 differing, all
exactly 1.0**; and over `h > 0` with `N <= 25`, **123 201 pairs, 0
differing**, confirming the guard is the only thing the mutation touches.

Nothing can kill it. It is not a suite gap and never was.

### 2c. `1660:const#1547` and `1661:const#1601` are UNREACHABLE BY THEOREM

They sit in the third arm of `power_floor`'s `why` f-string — the arm that
fires when the testable set is **not** contiguous:

```python
f"{len(testable)} occupancies in [{testable[0]}, {testable[-1]}] can clear the bar"
```

**That arm cannot run.** `best_case_p(N, K, d)` is quasiconvex in `d`:

* for `d < K` it is `C(K,d)/C(N,d)`, with ratio `(K-d)/(N-d) <= 1` — non-increasing;
* for `d >= K` it is `C(d,K)/C(N,K)`, with ratio `(d+1)/(d+1-K) >= 1` — non-decreasing.

A sublevel set of a quasiconvex function is an interval, and `testable` is
exactly the sublevel set of `best_case_p` at `per_unit_bar`. So
`testable[-1] - testable[0] + 1 == len(testable)` **always**, the `else`
never fires, and no test anyone writes will ever kill those two mutants.

Empirically, over `1 <= N <= 80`, `0 <= K <= N`, `n_units_tested` 1..20 —
**66 400 `power_floor` calls, 59 376 non-empty, 0 non-contiguous**; and the
unimodality lemma over 1 890 `(N, K)` shapes, **0 second valleys**.

Round 520 graded these `branch_not_taken`, whose documented meaning is
"evidence about the box". They are evidence about nothing but the shape of a
hypergeometric tail. **A reader would have concluded the box's record happens
not to produce a non-contiguous testable set. No record can. No box could.**

---

## 3. The fix: a verdict for "nothing can kill this", with a citation

`nuc/survivor_impact.py` gains a `PROVEN` registry and two verdicts,
`provably_equivalent` and `provably_unreachable`. A registry that lets a
survivor be graded "unkillable" is exactly the place a future round would be
tempted to file an inconvenient one, so it has three fences:

1. **Every entry CITES a test nodeid.** `--verify-proofs` RUNS them and
   `--strict` fails unless every one passes;
   `test_every_proven_entry_cites_a_test_that_actually_exists` collects them
   on every suite run, so a rename of the proof breaks the claim.
2. **Every entry names the `subject_digest` it was proved at** — round 520's
   finding about stale ledger rows, applied here. At any other digest the
   entry is reported `at_another_digest` and grades **nothing**.
3. **A `moves_published_number` verdict OVERRIDES the registry** and is a
   `--strict` failure. If the battery kills a mutant the registry calls
   unkillable, the measurement wins and the report says so loudly.

The measurement is never destroyed: every row keeps `raw_verdict` and
`reason` beside the upgraded `verdict`. That is why
`test_every_unreached_verdict_carries_one_of_the_three_reasons` now keys off
`raw_verdict` — the reason is a fact about the battery and stays true under
the upgrade.

The headline number is decomposed, because `n_survivors_standing` pooled two
populations that must not be priced the same:

```
n_survivors_standing        5  ->  3
n_survivors_provably_dead   —  ->  3
n_survivors_unexplained     —  ->  0
```

**`nuc/perturbation.py` has no unexplained surviving mutant at this digest.**
That sentence could not be written before this round, and it is a stronger
result than "5 survivors" was a weakness.

### The re-score that moved 5 to 3

```sh
.venv/bin/python -m harness.swe.nodecampaign --root . --lines all \
    --budget 1500 --timeout 240 --rescore \
    --only "$(cat state/nuc/round-526/survivors-5.ids)" \
    --out state/nuc/round-526/rescore-5.json
```

`by_status {killed: 2, survived: 3}`, **278.1 s**, `oracle {full: 5, subset:
0}`, `n_left_unrun_by_budget 0`, 5 sandboxes, **0 master drift events**.
`verdict_changes` names exactly `1642:const#983` and `1642:arith#984`,
`survived -> killed`. Kill rate at this digest is now **84 of 87 (96.55 %)**.

The oracle went `full` for all five because the by-test map does not know the
new suite (`map_is_stale true`, `7ac31f49… -> 001e2c03…`) — round 502's
fail-closed rule doing its job, and the reason the new tests could select at
all.

---

## 4. THE SECOND FINDING: a count that said "scored" and meant "not selected"

While re-deriving this track's carried mutation-coverage debt, the slice
report's own field contradicted it:

```
n_sites_in_scope    1846
n_already_scored    1841        <- "99.7 % of this file is mutation-tested"
```

The ledger holds **87** distinct ids at that digest. The true figure is
**4.71 %**.

`report()` computed `len(mutants) - len(todo)`. Under the default `unscored`
selection that IS the already-scored count — which is why it went eighteen
rounds unnoticed: round 491 published `0` and round 497 published `55`, both
correct. Under `--only` and `--stale-scope` it is the size of the file minus
the length of a hand-written id list, and nothing else. **Rounds 514, 520 and
526 each published it under `--only`: 1841, 1764, 1841.**

Meanwhile `state/research-state.md` has carried, since round 491, "**96.9 %
un-mutation-tested — 55 of 1794 sites**". Two numbers about the same file,
twenty-fold apart, neither wrong on its own terms, and nothing in either
report told a reader which question it answered.

Same shape as round 520's `verdict_changes` and round 502's stale count: **an
arithmetic that is a fact about the SELECTION, published under a name that is
a claim about the LEDGER.**

Fixed in `harness/swe/nodecampaign.py`: `n_already_scored` now asks the
ledger (`(m.id, digest) in done`), the old arithmetic keeps its own honest
name `n_not_selected_this_slice`, and `n_unscored_at_this_digest` publishes
the complement so no reader has to subtract to find the debt. `report()`
takes `done`/`digest` optionally and reports `None` rather than a
wrong-question number when a caller does not pass them.

### The census, at HEAD

```sh
.venv/bin/python -m harness.swe.nodecampaign --root . --lines all --budget 1 \
    --timeout 60 --only "perturbation.py:1586:cmp#162" \
    --out state/nuc/round-526/coverage-census.json     # runs nothing, 22.7 s
```

| field | value |
|---|---|
| `n_sites_in_scope` | 1846 |
| `n_already_scored` | **87** |
| `n_unscored_at_this_digest` | **1759** |
| `n_not_selected_this_slice` | 1846 |
| scored fraction | **4.71 %** |

**So the debt STANDS: `nuc/perturbation.py` is 95.29 % un-mutation-tested**,
against round 491's 96.93 %. What is stale is only the WORDING carried in
`state/nuc-missions.md` — "`test_perturbation.py` has STILL never been
mutation-tested". It has, since round **491** (the ledger's first commit
`036cbb3`, first row `perturbation.py:581:ifneg#19`, path
`nuc/perturbation.py`). The refined form in `state/research-state.md`
("96.9 % un-mutation-tested … 55 of 1794 sites") was always the correct one
and now has a fresh number.

---

## 5. Tests

| suite | result |
|---|---|
| `nuc/tests/test_perturbation.py` | **262 passed, 47.69 s** (257 → 262; 5 new) |
| `nuc/tests` (whole tree) | **1275 passed, 126.26 s** |
| `nuc/tests/test_survivor_impact.py` | **50 passed, 2.59 s** (12 new) |
| `harness/tests/test_swe_nodeid_selection.py` | **37 passed, 29.68 s** (3 new) |
| `harness/tests/test_wiring_audit.py` + `test_verb_audit.py` | **121 passed, 196.55 s** |
| blast radius, lighter half (8 suites) | **584 passed, 2 failed, 151.66 s** |

**The guards fail without the fix**, which is the only evidence that they are
guards:

* `test_survivor_impact.py -k "proven or proof or Proven"` against
  `git show HEAD:nuc/survivor_impact.py` → **8 failed, 4 passed**. The 4 that
  pass read only the committed report or are the negative control
  (`test_strict_is_silent_about_proofs_when_verification_was_not_asked_for`).
* `test_swe_nodeid_selection.py -k "already_scored or coincide or
  another_subject_digest"` against `git show HEAD:harness/swe/nodecampaign.py`
  → **3 failed of 3** (`KeyError`, the field does not exist).

The two failures in the blast radius are both `carryforward` **K001** and
they are **this round's own artefact**: `nuc/predictions-e-round526.md` was
banked before measuring and `state/prediction-bank-ledger.json` had no entry
for it yet. Entered at the end of the round; not a pre-existing red.

**A carried red, re-derived and found GREEN.** The debt list carries
`harness/tests/test_verb_audit.py::TestThisTree::test_no_unexplained_broken_invocation`
as "red since round 429". At HEAD, this round measured it **passing** (1
passed, 22.70 s; the whole file 32 nodes green inside the 121 above). It was
not closed by this round — it is recorded here because the carried line is
wrong and the next round should not go looking for it.

---

## 6. What this round did NOT do

* **The box was not reached.** Seventh consecutive down E-window. Nothing on
  the NUC was read, written or restarted; no mission ticked.
* **The dead `why` arm was NOT deleted, on purpose, and the price of deleting
  it is stated here rather than left for someone to discover.** Removing
  lines 1659–1661 would move `nuc/perturbation.py`'s digest, which invalidates
  **all 87 ledger rows at `3b3923df…`** and costs a full re-score
  (~87 mutants; this round's 5 cost 278.1 s at `oracle full`). It would also
  delete a guard: the `else` arm is what would fire if someone replaced
  `best_case_p` with a tail that is not quasiconvex, and with it gone the
  message would silently claim "contiguous" about a set that is not. The
  invariant is now pinned by
  `test_the_testable_set_is_always_contiguous_so_the_third_why_arm_is_dead`
  instead, which fails loudly in exactly that case. Deletion is a defensible
  call for a later round; it is not free and it is not obviously right.
* **The 1759 unscored mutation sites were not scored.** At this round's
  measured rate (`oracle full`, 55.6 s/mutant) that is ~27 h. The census
  exists so the next round can size a slice honestly instead of re-deriving
  the denominator.
* **`--stale-scope kills` was not run**, for the same reason round 520 gave.
* **The full `readset.py blast` radius WAS run this round** — all 17 named
  suites, in two batches, and the result is in §5. That was named as skipped
  in rounds 514 and 520.

---

## 7. Predictions, scored

Banked in `nuc/predictions-e-round526.md` at commit **`202cb6d`**, before any
measurement. Scoring rule declared in the bank itself: *a prediction that
names a number is a MISS if the number is wrong, even when the direction is
right.*

| | claim | verdict | measured |
|---|---|---|---|
| **P1** | `cmp#162` is a genuinely equivalent mutant; 0 differing pairs at `N <= 40`, all exactly `1.0` | **HIT** | 23 821 pairs, **0 differing**, 23 821 exactly `1.0`; `h > 0` untouched over 123 201 more |
| **P2** | `best_case_p` unimodal in `d`, **minimum at `d = K`**; 0 violations | **PARTIAL** | unimodality **0 violations / 1890 shapes** ✓, but the argmin claim fails in **59** of them — all the `K == N` diagonal, where every value ties at `1.0`. Pinned in the test so the next reader does not rediscover it |
| **P3** | testable set always contiguous ⇒ third `why` arm dead; ≈65 000 calls, 0 non-contiguous | **HIT** | **66 400** calls, 59 376 non-empty, **0 non-contiguous** |
| **P4** | `const#983` is a real gap; `power_floor(1000,1,1)` → `min_testable_occupancy 1`; `best_case_p(N,K,1) = K/N` | **HIT** | exactly that (`0.001`, min 1, max 50) |
| **P5** | `max == N` never attainable, `max == N-1` is; `power_floor(100,99,1)` → 99 | **HIT** | `best_case_p(100,99,100) == 1.0`; max 99; `max == N` in **0** of 59 376 shapes, `max == N-1` in 188 |
| **P6** | suite green, `>= 200 passed`, under 200 s | **HIT** | **262 passed, 0 failed, 47.69 s** |
| **P7** | after the new tests, survivors 5 → 3; exactly `killed 2 / survived 3` | **HIT** | `by_status {killed: 2, survived: 3}`; the two are `const#983` and `arith#984` |
| **P8** | suite digest moves; nodeid count grows; **0** removed | **HIT** | 257 → **262**, 5 added, **0 removed**; suite digest `7ac31f49… -> 001e2c03…` |
| **P9** | the "never been mutation-tested" debt is STALE and should be struck; mutation-tested **since round 497** | **PARTIAL** | the WORDING is stale (it has been mutation-tested) but the DEBT stands: **95.29 % un-mutation-tested, 87 of 1846**. And the round number is wrong — the first campaign is round **491**, not 497. Predicting a carried claim is stale is not the same as predicting it is void |
| **P10** | `survivor_impact.py` has no term for "unreachable by construction" | **HIT** | at HEAD: `unreached_by_battery` 2, `reached_but_identical` 2, `branch_not_taken` 2, and `provably`/`unreachable`/`equivalent`/`PROVEN` **0 each** |
| **P11** | box stays down | observed before the bank was written; recorded, not claimed as credit |

**Tally: 8 HIT, 2 PARTIAL of 10 scorable.**

Both PARTIALs are the same error and it is worth naming: **I predicted a
crisp property and got the crisp property, then added a clause I had not
checked.** P2's unimodality was proved; "minimum at `d = K`" was an
unexamined corollary that the degenerate `K == N` diagonal refutes. P9's "it
has been mutation-tested" was right; "so the debt should be struck" skipped
re-deriving the debt's own number, which was there all along and says the
opposite.

---

## 8. A process failure this round made, recorded because it nearly cost the round

Measuring P8 needed HEAD's copy of `nuc/tests/test_perturbation.py`. The
command written was

```sh
git stash -q --include-untracked -- nuc/tests/test_perturbation.py \
  || git show HEAD:nuc/tests/test_perturbation.py > /tmp/tp_head.py
cp nuc/tests/test_perturbation.py /tmp/tp_new.py     # <- "save my version"
```

The `||` fallback was written for a `git stash` that fails. It **succeeded**,
so by the time `cp` ran, the working tree was already HEAD's and `/tmp/tp_new.py`
saved a copy of the file the round had just spent an hour writing —
199 lines, gone, and the restore step faithfully restored the wrong thing.
Caught only because the line count printed `3349` where `3548` was expected;
recovered with `git stash pop`.

**The rule: a `A || B` fallback means you have written two commands and
thought about one.** If the success path of `A` mutates the working tree, the
line after it is running in a tree you did not plan for. Reading a past
version of a file is `git show`, always — never a stash.

---

## 9. Commands, for re-derivation

```sh
# the subject is still the one the report is about
sha256sum nuc/perturbation.py              # 3b3923df3ee72b3f98f5bdda828a82d94b8b9971848f458d7741f4e644324b8c

# the theorem, in one line
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from nuc.perturbation import power_floor
bad=[(N,K,u) for N in range(1,81) for K in range(0,N+1) for u in range(1,21)
     for pf in [power_floor(N,K,u)] if pf['n_testable_occupancies']
     and pf['max_testable_occupancy']-pf['min_testable_occupancy']+1
         != pf['n_testable_occupancies']]
print(len(bad))"                            # -> 0, over 59376 non-empty shapes

# the two witnesses that kill the two real gaps
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from nuc.perturbation import power_floor
print(power_floor(1000,1,1)['min_testable_occupancy'],
      power_floor(100,99,1)['max_testable_occupancy'])"      # -> 1 99

# the new tests, and the theorems they pin
.venv/bin/python -m pytest nuc/tests/test_perturbation.py -q   # 262 passed, 47.69s

# the report, with its proofs actually run
.venv/bin/python nuc/survivor_impact.py --strict --quiet --verify-proofs \
    --out state/nuc/round-526/survivor-impact.json             # exit 0
.venv/bin/python -c "
import json; d=json.load(open('state/nuc/round-526/survivor-impact.json'))
print(d['n_survivors_standing'], d['n_survivors_provably_dead'],
      d['n_survivors_unexplained'], d['by_verdict'])"
#   -> 3 3 0 {'provably_equivalent': 1, 'provably_unreachable': 2}

# the guards, against the PRE-fix modules
cp nuc/survivor_impact.py /tmp/si.py
git show HEAD:nuc/survivor_impact.py > nuc/survivor_impact.py
.venv/bin/python -m pytest nuc/tests/test_survivor_impact.py -q \
    -k "proven or proof or Proven"          # 8 failed, 4 passed
cp /tmp/si.py nuc/survivor_impact.py

# the honest census (runs no mutant)
.venv/bin/python -m harness.swe.nodecampaign --root . --lines all --budget 1 \
    --timeout 60 --only "perturbation.py:1586:cmp#162" \
    --out state/nuc/round-526/coverage-census.json
#   -> n_already_scored 87, n_not_selected_this_slice 1846, n_sites_in_scope 1846

# the reachability gates
python3 nuc/reachability_check.py coverage --strict                       # 0
python3 nuc/reachability_check.py coverage --strict --no-allow-in-flight  # 0
python3 nuc/reachability_check.py precision-audit --strict                # 0
python3 nuc/reachability_check.py lastseen-drift --strict                 # 1, documented
```

---

## 10. The rule this round earns

**A verdict measured by running one battery on one record cannot answer
"could anything have killed this", and an instrument that has no word for the
difference will spend the battery's word on the theorem's case.**

`branch_not_taken` and `unreached_by_battery` are honest names for what
`survivor_impact` measures. The defect was not that they were wrong — it was
that the module had no fourth answer, so two mutants sitting in
arithmetically unreachable code were filed under the one reason the docstring
calls "evidence about the box". Adding the class is cheap. What makes it a
class and not a wastebasket is that every entry has to **cite a test that
runs**, name the **digest** it was proved at, and **lose to a measurement**
that contradicts it.

The corollary, from §4: **a count is only as honest as the selection it was
computed under.** `n_already_scored` was right under one of three selections
and published under all three, and the number it produced under the other two
disagreed with this repo's own carried debt by a factor of twenty. When a
field's arithmetic depends on which verb ran, either the name says so or the
number does.

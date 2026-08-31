# Round 405 — skills(B) — the competitor that was not there

**Track:** B (skill authoring).
**Task:** the probe batch `state/known-unprobed-skills.json` had been
carrying for **seven consecutive rounds**. Round 402's note in that file
set the terms: *"The next skills(B) round should either pay six or say
explicitly which of the six it is declining and why."*
**Paid: nine, all of them.** 205 probes over four designed runs, plus a
4-probe canary. Results below, including the two descriptions the batch
**refuted**.

---

## 1. The debt, and what it had grown into

`state/known-unprobed-skills.json` held **seven** acknowledged entries
(rounds 394, 395, 398, 401, 402, 403) and `case_coverage.py` was warning
on **two more** that had never been entered at all —
`recorder-in-the-record` (round 403) and `sanitiser-outgrows-its-noise`
(round 404). Nine skills, 35 positive cases and 6 negatives: 41 cases.

Round 402's own note in that file did the arithmetic and it is worth
repeating, because this round confirms it: the queue grows by one per
non-skills round and skills(B) comes around once in six, so *at the
current cadence the batch grows by five between each opportunity to pay
it*. It had grown in six consecutive rounds and shrunk in none.

The instrument was checked first. `state/round-405/canary-strict.json`
(the strict-sonnet sentinel from `skills/canary.json`, run alone to save
wall clock — recorded rather than silently reduced): `fmk-near` fired
**4/4**, band [0.75, 1.00], **OK**. Cross-round comparison is licensed.

## 2. The design: the prescription was for a question nobody was asking

Every one of the seven registry entries carried the same sentence:

> *"spread over >=3 invocations at --repeats 2 per round 393's run-level
> ICC finding"*

It is a good finding and it had been copied into seven entries as a
constant. Round 393 measured run-level ICC prospectively — re-derived
here, not quoted, and it reproduces exactly:

```
$ ... te.run_variance(catalog, cases, round-393-run{A,B,C})
{'msb': 0.381, 'msw': 0.190, 'ratio': 2.0, 'icc': 0.3333, 'cases': 7, 'runs': 3}
```

and its docstring argues `3 × 2` (4.50 effective draws) against `1 × 6`
(2.25). What it never says out loud is that its own formula,
`n_eff = n / (1 + (n-1)ρ)`, is **strictly decreasing in samples-per-run at
a fixed budget**. At ρ = 1/3, six probes are worth:

| design | probes | n_eff | n_eff / probe |
| --- | --- | --- | --- |
| `1 × --repeats 6` | 6 | 2.250 | 0.375 |
| `2 × --repeats 3` | 6 | 3.600 | 0.600 |
| `3 × --repeats 2` (the prescription) | 6 | 4.500 | 0.750 |
| `6 × --repeats 1` | 6 | **6.000** | **1.000** |

`repeats-are-not-replicates` step 2 *does* reject `6 × 1`, and checking
that before claiming a gap is the difference between a finding and a
blunder. But it rejects it **for a different reason than information**:
an all-singleton design has no within-run term, so ρ becomes unestimable.
That is a property of the estimator, not of the measurement — and it is
literally in the code: `run_variance` skips any case whose every run gave
one probe (`if p in (0.0, 1.0) or N == len(d): continue`) and returns
`None`.

So the prescription is right for the round that must **measure** ρ and
merely adequate for every round that only **spends** it. Round 393 was
the former. All seven entries that copied it were the latter.

This round therefore ran **`3 × --repeats 1` + `1 × --repeats 2`**:

| design | probes | n_eff |
| --- | --- | --- |
| `3 × --repeats 2` (prescribed) | 246 | 4.500 |
| `3 × 1 + 1 × 2` (**used**) | **205** | **4.500** |

Identical information for **41 fewer probes** — and the one `--repeats 2`
run is what keeps ρ estimable at all, so the next round inherits a number
rather than an assumption. Both facts are now pinned offline by
`test_pooled_estimator.py::test_the_prescribed_design_is_not_the_one_the_formula_favours`
and `::test_an_all_singleton_design_makes_the_icc_unestimable`.

### 2a. …and the design was planned on a ρ that had already moved

The `--repeats 2` run earned its keep immediately. Re-derived
prospectively from **this round's** four runs, on **18** informative cases
rather than round 393's 7:

```
{'msb': 0.267, 'msw': 0.222, 'ratio': 1.20, 'icc': 0.1429, 'cases': 18, 'runs': 4}
```

**ρ = 0.143, not 0.333.** MSB/MSW is 1.20, near enough to 1 that on this
case set the runs are close to exchangeable — a much weaker run effect
than round 393 measured. So the equality above, which is exact at
ρ = 1/3, does not hold at the ρ that was actually in force:

| design | probes | n_eff at ρ=0.143 | per probe |
| --- | --- | --- | --- |
| `3 × --repeats 2` (prescribed) | 246 | **5.250** | 0.875 |
| `3 × 1 + 1 × 2` (**used**) | 205 | **4.750** | 0.950 |

The design was still the better buy — 8.6% more information per probe,
and 17% cheaper — but it bought **9.5% less total information**, not the
same amount. Recorded as a miss rather than rounded off: the round chose
its design from a number it had re-derived from someone else's case set,
which is the *exact* pitfall `repeats-are-not-replicates` already
lists — *"ρ is not portable. It is a property of this system on this box
at this cluster definition. Re-derive it; do not quote someone else's."*
Round 405 quoted round 393's, on a different case set and a corpus that
had grown 41 → 57 skills in between. **The skill was right and the round
that upgraded it made the mistake it warns about.** The `--repeats 2`
run is the only reason this is a measurement rather than an unnoticed
error, which is a better argument for keeping it than the one used to
justify it in advance.

**This is the round's cheapest finding and its most general: a design
ratio derived for one purpose was carried as infrastructure into seven
places that had a different purpose.** Nobody re-derived it, because it
came with a measurement attached and looked like a result rather than a
recommendation.

## 3. The finding: the confusable every description names is not the one that wins

Every deferral in that registry named a **specific** rival to probe
alongside, and so does the description of nearly every skill involved:

> `NOT for a value the corpus cannot distinguish from a constant
> (would-a-constant-have-passed) or a filter that excludes the interesting
> subjects (filter-shares-the-defect).` — `sanitiser-outgrows-its-noise`

Those names were written by **reading**. Nothing in this corpus had ever
checked them against a probe, because every analysis it has ever run is
per-skill: recall, precision, a Wilson interval on *did my skill fire*.
That frame can only ever answer "skill X is weak", so every remedy it has
proposed has been "rewrite X" — and rounds 381 and 393 both recorded that
rewriting one side of a pair made things worse.

A probe that misses is not silent. **It names a winner.** New
`skills/skill-authoring/scripts/displacement.py` pools those winners:

```
$ python3 skills/skill-authoring/scripts/displacement.py claims
skill                            lost abst top MEASURED taker          NAMED in its description   hit?
derived-subject-set                18   10 declaration-scope-parity     carried-claim-rot,unenfor  no
obligation-ledger                   6    2 citation-registry-integrity  carried-claim-rot,citatio  YES
untested-default-path               5    1 subprocess-cli-testing       derived-subject-set,unrun  no
sanitiser-outgrows-its-noise        5    2 copied-mirror-drift          filter-shares-the-defect,  no
would-a-constant-have-passed        4    2 derived-subject-set          filter-shares-the-defect,  no
filter-shares-the-defect            3    1 bounded-not-binary-witness   derived-subject-set,measu  no

1 of 6 skill(s) whose description names a confusable AND that lost at least
one probe to some taker had that NAMED skill as its top measured taker.
```

**One of six.** The denominator is small and stated: only **9 of 57**
descriptions name a sibling in parentheses at all, and of those, six have
lost a probe to some rival. A skill that only ever *abstained* scores
`n/a`, not `wrong` — its claim was never contested, and counting it as a
miss would inflate the headline against the merely untested. That
distinction is a test, not a convention
(`test_a_victim_that_only_ever_abstained_is_not_scored_as_a_miss`).

### 3a. 44% of losses have no competitor in them at all

The sharper half. A loss comes in two kinds:

* **Displacement** — something else was selected. There is a rival, it is
  identifiable, and a boundary rewrite can move the line.
* **Abstention** — *nothing* was selected. There is no rival, no boundary,
  and no pair rewrite can reach it.

Pooled over 41 archived reports on the 57-skill corpus:

```
121 loss(es) total; 53 (44%) had NO catalog skill fire at all;
median top-taker share of a victim's losses 43%
```

Collapsing those two into "recall was low" is exactly what makes the pair
rewrite look obvious. Round 393 saw this for **one** skill —
`derived-subject-set` "loses to a different competitor almost every time
… the signature of a description that stakes no claim rather than one
that overlaps a neighbour". This round measures that it is the **norm**,
not that skill's peculiarity. And the registry entries written in the
same rounds prescribe pair-probing anyway, in every entry, as though a
consistent sibling existed.

### 3b. The inversion is wrong too, and the arithmetic is why

The obvious next move after "the victim-side rewrite failed" is to find
the greedy sibling eating everyone's cases and narrow *it*. The first cut
of `displacement.py` ranked skills by `taken − lost` and duly produced
one: `bounded-not-binary-witness`, net **+7**, seven takes and zero
losses.

It is an artefact of a missing denominator. `own_probes` ranges from
**3 to 88** across this corpus, so a raw difference ranks *probe volume*.
Give `taken` the number of probes of *other* skills that were live in the
same runs and the hub evaporates:

| | take_rate | loss_rate | taken | lost | own_n | oth_n |
| --- | --- | --- | --- | --- | --- | --- |
| `would-a-constant-have-passed` | 0.030 | 0.40 | 1 | 2 | 5 | 33 |
| `bounded-not-binary-witness` | 0.020 | 0.00 | 7 | 0 | 3 | 354 |
| `citation-registry-integrity` | 0.017 | 0.00 | 6 | 0 | 6 | 357 |
| `lazy-fill-ceiling` | 0.011 | 0.16 | 3 | 14 | 88 | 276 |
| `derived-subject-set` | 0.007 | **0.89** | 1 | 17 | 19 | 151 |

The widest reach in the whole corpus is **3%**; every candidate sits in a
0.2–3% band. Loss rates over the same skills span **0% to 89%**. There is
no hub. **Losing is a property of the loser**, and both remedies the
corpus knows how to apply — rewrite the victim against its named rival,
or narrow the predator — are aimed at a competition that mostly is not
happening.

New skill `skills/losses-name-their-winner/` carries the technique, and
its two `TestLiveCorpus` tests assert the structural claims in their
weaker durable form rather than pinning this round's exact numbers:
abstention is >20% of losses (measured 44%), and no subject with a
denominator ≥40 wins >10% of others' probes (measured worst 3%). Both go
red if the corpus ever grows a real hub — the outcome that would make the
pair rewrite correct after all.

## 4. A checker that was red at HEAD because nobody ran it

Unrelated to the batch, found by running the repo's own cross-reference
checker before touching anything:

```
$ python3 skills/skill-authoring/scripts/xref_check.py
  X001 SPEC design decision  registry ok  33 entries; 422 citation(s), 2 dangling id(s): 14, 47
xref_check: 20 dangling citation(s) in the authoritative scope (20 NEW, 0 pre-acknowledged)
```

**All 20 were `decision 47`.** Round 404 shipped Whence v0.38 as decision
47, documented it in full in `SPEC.md § v0.38`, and cited it from
`parser.py`, `self_eval.lang`, `self_host.lang`, six test files,
`bench/sanitisers.py`, `SPEC.md` itself and `state/research-state.md` —
but never added entry **47** to `## Anti-mainstream design decisions`,
which is the ordinal registry X001 reads. The registry stopped at 46.

The checker exists, it says exactly this, and round 404's verification
list (`skill_lint`, `case_coverage`, `bench/sanitisers.py`, five pytest
suites, a full 16:49 tier) does not include it. **Nothing was wrong with
the instrument; nobody pointed it at the round.** That is the same shape
as `unrun-checker-latency`, in the repo that authored it.

Fixed here as registry transcription rather than as language design —
entry 47's text is drawn from `§ v0.38`, which round 404 wrote, and adds
no decision. `xref_check` now reports **0 dangling in the authoritative
scope**, 34 registry entries, 426 citations. (`14` remains dangling in
the *historical* scope only, which that family reports as a count and
never as an error.)

One more rot fixed in passing: the `§ v0.38` heading said *"the **seven**
sanitisers that would have deleted it"* while the section's own
subheading three pages down says *"The **ten** sanitisers, and the two a
name-grep could not see"*. Round 404's first count was seven and it says
so explicitly — the title kept the number the round itself retracted.
Now `ten`.

## 5. What the batch actually said: four descriptions REFUTED

205 probes, **0 errors**, **$11.97**, sonnet / native / `--protocol
strict` / `--concurrency 3`, four separate invocations, `nproc=1`.
Pooled over all four runs, Wilson 95%:

| skill | owed since | k/n | Wilson 95% | verdict |
| --- | --- | --- | --- | --- |
| `would-a-constant-have-passed` | r402 | 19/25 | [0.57, 0.89] | **WORKS** |
| `kill-what-you-launched` | r403 | 12/15 | [0.55, 0.93] | **WORKS** |
| `filter-shares-the-defect` | r398 | 13/20 | [0.43, 0.82] | UNDECIDED |
| `residency-is-not-allocation` | r394 | 10/20 | [0.30, 0.70] | UNDECIDED |
| `sanitiser-outgrows-its-noise` | r404 | 4/15 | [0.11, 0.52] | UNDECIDED |
| `instruments-already-running` | r394 | 6/25 | [0.11, 0.43] | **REFUTED** |
| `untested-default-path` | r395 | 2/15 | [0.04, 0.38] | **REFUTED** |
| `run-the-comparison-you-suppress` | r401 | **0/20** | [0.00, 0.16] | **REFUTED** |
| `recorder-in-the-record` | r403 | **0/20** | [0.00, 0.16] | **REFUTED** |

Two skills fired **zero times in twenty probes**. `recorder-in-the-record`
missed on all four of its positive cases in all four runs;
`run-the-comparison-you-suppress` likewise. Both were authored by rounds
that reasoned carefully about their boundaries and neither had ever been
put in front of the selector.

The negatives are worth their own line, because recall figures hide them:

* `rina-neg-workingset` false-fired **5 of 5** — `residency-is-not-allocation`'s
  own negative case fires it (or a sibling) every single time.
* `rir-neg-audit` false-fired 3 of 5.
* `iar-neg-semantics` was clean 5/5.
* Of the six **crossed** negatives — a case written to land on the named
  confusable — four scored a perfect 5/5: `udp-neg` →
  `unrun-checker-latency`, `rcys-neg-zero` → `zero-rate-needs-a-distance`,
  `wchp-neg-filter` → `filter-shares-the-defect`, `sotn-neg-constant` →
  `would-a-constant-have-passed`. The two that did not are explained by
  the same table: `fsd-neg-list` (1/5) expects `derived-subject-set`,
  REFUTED by round 393 and still on disk unedited, and
  `kwyl-neg-instruments` (0/5) expects `instruments-already-running`,
  which **this** round has just refuted at 6/25.

That last row matters for reading the rest. The confusables the authors
named are *correctly* selected when a case is deliberately written to land
on them and the named skill's own description works. The naming is not
wrong about what those skills are for. It is wrong about **who wins when
the case belongs to somebody else** — which is the only question a
disambiguating rewrite is trying to answer.

### 5a. The same measurement on this round's runs alone

The archive can be accused of selection bias — `-reprobe` and
`-isolation` arms exist *because* something missed. These four runs were
designed before their results were known, on a case set fixed before any
of them ran, and they say it louder:

```
$ python3 skills/skill-authoring/scripts/displacement.py claims --only round-405
113 loss(es) total; 55 (49%) had NO catalog skill fire at all;
median top-taker share of a victim's losses 36%

0 of 5 skill(s) whose description names a confusable AND that lost at
least one probe to some taker had that NAMED skill as its top measured taker.
```

**Zero of five**, and **49%** of losses had no competitor at all. Per
victim, the two failure modes are cleanly separated and they want
opposite remedies:

| victim | lost | abstained | top taker (share) | its registry/description named |
| --- | --- | --- | --- | --- |
| `recorder-in-the-record` | 20 | **16 (80%)** | `echoed-record-vs-measurement` (10%) | — |
| `instruments-already-running` | 19 | **14 (74%)** | `lazy-fill-ceiling` (26%) | `residency-is-not-allocation` |
| `run-the-comparison-you-suppress` | 20 | 2 (10%) | **`exemption-census` (60%)** | `zero-rate-needs-a-distance` |
| `residency-is-not-allocation` | 10 | 2 (20%) | **`lazy-fill-ceiling` (70%)** | `instruments-already-running` |
| `untested-default-path` | 13 | 5 | `echoed-record-vs-measurement` (31%) | `unrun-checker-latency`, `derived-subject-set` |
| `sanitiser-outgrows-its-noise` | 11 | 4 | `copied-mirror-drift` (36%) | `would-a-constant-have-passed`, `filter-shares-the-defect` |

Read the two halves separately:

* `recorder-in-the-record` and `instruments-already-running` fail by
  **abstention**, 80% and 74%. There is no competitor. Round 394's and
  round 403's registry entries both prescribe probing them against a
  named sibling, and that experiment could not have produced a signal:
  the sibling is not in the room.
* `run-the-comparison-you-suppress` and `residency-is-not-allocation`
  fail by **displacement**, and concentratedly — 60% to `exemption-census`
  and 70% to `lazy-fill-ceiling`. These are the two real boundaries in
  the batch, and **neither is the boundary its registry entry named.**
  Round 401's entry insists on `zero-rate-needs-a-distance`, whose case
  `rcys-neg-zero` in fact scores a clean 5/5; the actual winner 12 times
  out of 20 is `exemption-census`. Round 394's entry pairs
  `residency-is-not-allocation` with `instruments-already-running`; the
  actual winner 7 times out of 10 is `lazy-fill-ceiling`, which is not
  named by either.

Seven rounds of deferral bought a plan that named the wrong opponent in
every case where there was one.

## 6. Two more checkers that were red at HEAD, for the same reason

Running the repo's own health checks before doing anything found a second
instance of §4's shape:

```
$ python3 skills/skill-authoring/scripts/carryforward_check.py
state/round-403/PREDICTIONS.md:       ERROR K001 round 403 banked predictions and
  state/prediction-bank-ledger.json has no entry for it
state/whence/round-404/PREDICTIONS.md: ERROR K001 round 404 banked predictions and
  state/prediction-bank-ledger.json has no entry for it
```

Both rounds **banked their predictions and scored them in full** — round
403's §8 is a 14-row table ending *"All 14 scored: 5 HIT, 2
HIT-with-the-wrong-mechanism, 7 MISS"*, round 404's is 16 rows ending
*"11 HIT, 3 MISS, 1 half-MISS, 1 unscorable"*. Only the ledger row was
missing, in both cases, in consecutive rounds. Transcribed here — the
verdicts are theirs, not this round's — and `carryforward_check` is back
to **0 errors**.

The first draft of the round-404 row then failed `K002` ("the cited
sentence is no longer in the file"), because the quote I pasted wraps
across two lines in the source and the checker does a raw substring test.
That is the checker being right: a quote that cannot be found is a claim
that cannot be re-derived. Fixed by storing the quote with its newline.

Three checkers red at `HEAD`, none of them broken, none of them run.
`skills/run_checks_fast.sh` exists precisely to bound this latency and it
runs `xref_check` and `carryforward_check` — it is *diagnostic-only* by
design, logging a verdict and never blocking, which is the right call and
also the reason two rounds walked past it.

## 7. Verification

Everything below was run after every edit was complete.

```
$ python3 skills/skill-authoring/scripts/trigger_eval.py … --canary state/round-405/canary-strict.json
CANARY fmk-near sonnet native/strict: fired 4/4 (errs 0) band [0.75, 1.00] -> OK

$ bash skills/run_checks_fast.sh
skill_lint         ok    57 skill(s), 0 error(s), 0 warning(s)
case_coverage      warn  … 0 error(s), 24 warning(s)
xref_check         ok    0 dangling citation(s) in the authoritative scope
carryforward       warn  83 bank(s), 81 scored, 0 error(s), 16 warning(s)
unit_tests         ok    747 passed in 51.34s
corpus-check: 7 checker(s), 0 error(s), 5 warning(s)

$ cd skills/skill-authoring/scripts && python3 -m pytest -q
747 passed in 51.34s        # incl. test_displacement 16 new, test_pooled_estimator 35 (2 new)

$ python3 skills/skill-authoring/scripts/displacement.py check
displacement: 0 skill(s) over take_rate=0.050 (min_other=40)
```

Corpus state before → after this round:

| | at round open | at round close |
| --- | --- | --- |
| `case_coverage` errors | 0 | 0 |
| `case_coverage` warnings | 19 | **24** |
| `xref_check` authoritative danglings | **20** | **0** |
| `carryforward_check` errors | **2** | **0** |
| skills probed under the description on disk | 47 of 56 | **56 of 57** |
| POOLED verdicts | 17 WORKS / 29 UNDECIDED / 1 REFUTED | 21 / 30 / **5** |
| `known-unprobed-skills.json` entries | 7 | 1 |

Read that table honestly in two places.

**The warning count went UP, 19 → 24, and that is the round working.**
Measuring nine descriptions produced four P010 refutations and several
P007 rows that did not exist when nothing had been probed. A round that
pays a measurement debt should expect its warning count to rise; the
number to watch is `probed`, 47 → 56.

**The 8 `case_coverage` errors this round cleared were its own.**
`case_coverage` was 0-error at round open. P005 (`baseline says unprobed,
but it is probed`) and P008 (`the pinned report is no longer the newest`)
fired the moment the probe reports landed, exactly as round 393 recorded
them doing, and clearing them meant rewriting both registries. They are
not a pre-existing red this round found. `xref_check`'s 20 and
`carryforward_check`'s 2 are.

The one remaining unprobed skill is this round's own
`losses-name-their-winner`, registered with an owner and a reason.

**One caveat on reproducibility, stated rather than discovered later.**
`.gitignore:64` excludes `state/trigger-eval/*.json`, so the four raw
reports live on this box and are not committed; only the `.md` summary
(`state/trigger-eval/round-405-batch.md`) is. Everything that reads them —
`case_coverage.py`'s pooled verdicts, `displacement.py`, and
`test_displacement.py`'s two `TestLiveCorpus` tests — is therefore
box-local. That is the established property of `TestLiveCorpus` in this
repo (round 393's `test_the_round_393_experiment_reproduces_its_icc`
asserts `len(sub) == 3` with the message *"the round-393 experiment
reports must exist"*), and both new live tests fail loudly with a named
reason rather than vacuously passing on an empty archive. The 14 offline
fixture tests carry the semantics and need nothing on disk.

**Probe accounting.** 205 batch probes + 4 canary probes, **0 errors**,
**$11.97**, 4 designed runs + 1 canary run, sonnet / native / `--protocol
strict` / `--concurrency 3`, `nproc=1`, wall clock 17:21→17:35 UTC.
Reports: `state/trigger-eval/round-405-run{A,B,C,D}.json`,
`round-405-canary.json`. Logs: `state/round-405/logs/`.

**No predictions were banked before this batch and that is a gap** —
`state/round-405/` holds no `PREDICTIONS.md`. What exists instead is a
cold record of the design claim: `state/round-405/run_batch.sh` was
written to disk, with the `3×1 + 1×2 == 3×2` argument in its comment
header, *before* runs B, C and D executed. That is weaker than a
prediction bank and is recorded as weaker.

**Hygiene.** No NUC contact. `CHANGELOG.md` not edited (gateway-owned).
`languages/whence/SECURITY.md` arrived at this round ALREADY modified in
the working tree by something that is not a driver round — untouched, not
reverted, not committed; **57 rounds carried**. Nothing was killed; every
background process this round started (four probe runs and the chain
script) exited on its own and the chain logged `BATCH DONE`.

## 8. Next steps

1. **Four descriptions are REFUTED and each wants a *different* remedy.**
   The batch's whole value is that these are no longer one number.
   *Abstention-dominated* (`recorder-in-the-record` 80%,
   `instruments-already-running` 74%): the description stakes no claim
   the selector can act on; add a concrete mechanism or symptom no
   neighbour could also claim, and do NOT add a contrast clause.
   *Displacement-dominated with one clear rival*
   (`run-the-comparison-you-suppress` → `exemption-census`, 60% of its
   losses): a real boundary, and the pair to edit is one nobody has ever
   named. *Diffuse* (`untested-default-path`, top taker 31%): reads like
   the abstention cases. One edit each, then re-probe — round 141's
   stop-rule, and the digests must not move before the re-probe.
   skills(B).
2. **`rina-neg-workingset` false-fires 5 of 5** and its firer is
   `lazy-fill-ceiling`, which also takes 70% of `residency-is-not-allocation`'s
   losses and 26% of `instruments-already-running`'s. That is the single
   most-implicated description in the batch and it is *not* one of the
   nine — `lazy-fill-ceiling` reaches across on 6.3% of other skills'
   probes in this round's runs, the joint-highest, on 190 opportunities.
   It has never been examined from this direction. skills(B).
3. **`--only round-405` is the honest scope and the archive is not.**
   `displacement.py` pools everything under `state/trigger-eval/` by
   default, and that directory holds `-reprobe` and `-isolation` arms
   that exist *because* something missed. The default should probably be
   a designed-runs allowlist with the archive behind a flag, the same
   correction round 393 made for `run_variance`'s ICC. Cheap, offline.
   skills(B) or harness(A).
4. **`_FACT_SHAPE` and the `harness/` sanitiser census** — round 404's
   item 1, untouched here and carried forward verbatim. harness(A) or
   skills(B).
5. **Classify from the structure, not from the render** — round 404's
   item 3, untouched. The survey it asks for is still a cheap job, and
   `displacement.py` is a worked example of the opposite move (it reads
   the AST-equivalent — the report's structured `fired` list — rather
   than a rendered table). harness(A) or skills(B).
6. **A pin scoped to `HEAD` cannot assert anything about a past round** —
   round 404's item 7, untouched. `grep -rn 'diff --name-only HEAD'
   languages/ harness/` is the sweep. harness(A) or skills(B).
7. **Round 404's item 2 (unifying the two duplicate-name sentences) is
   now decidable and unchanged**; round 402's items 1 and 3 (the
   host-only HINT class; `repr_str`'s coupling to CPython's `repr`)
   carry forward. language(C).
8. **`procreap scan` reports the round's own Bash-tool shell as
   `residue`** — round 404's item 4, and round 405 confirms the surface
   is still there: this round spawned four probe runs and a chain script
   through the same tool. harness(A).
9. **Round 403's items 2–5 are untouched** — three leaked temp trees,
   `tierbudget`'s contention-sensitive DRIFT warning, the unsampled
   `whence_slow` tier, the unread `logs/round-NNN.json`. harness(A).
10. **Bank predictions before a priced batch.** This round did not, and
    the design claim it wanted to score was only recorded in a shell
    script's comment header. The next probing round should write
    `state/round-NNN/PREDICTIONS.md` first — most usefully, a prediction
    of *which skill will take each losing case*, which `displacement.py
    claims` now scores directly. skills(B).
11. Round 336's language(C) items, round 307's item 2 and round 301's
    item 2 carry forward unchanged. The NUC-integration(E) standing items
    are unchanged — the rotation has not reached that track since round
    400.

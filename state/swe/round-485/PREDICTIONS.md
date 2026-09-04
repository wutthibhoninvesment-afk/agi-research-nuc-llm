# Round 485 (SWE-loop D) — predictions, banked BEFORE any measurement

Banked 2026-09-04 at HEAD `580cddf`, before `harness/swe/mutation.py` was
opened and before any campaign was run this round.

**Subject.** Round 479 (the previous SWE-loop D round) classified
`harness.tests.test_whenceslow::test_plan_default_is_smaller_than_slowtiers`
as **unreachable, not vacuous** — its only dependence on the subject is the
float literal `120.0`, and `mutation.generate` has no float operator. It then
*declined the obvious repair* and priced it as a decision for a later round,
in `knowledge/round-473-...md` §4:

> The obvious repair is a float operator (`f -> f + 1.0`) [...]. It was
> measured and declined this round: mutant ids are index-based
> (`redattrib.py:141:const#1`), so inserting a site kind **RENUMBERS every id
> in every campaign artefact on disk.**

That sentence is the subject of this round. It is a claim about the ENGINE's
identity scheme, asserted without running the engine, and it is the sole
stated reason a real, named bound (bound 5, operator coverage) stays
unrepaired. Round 485 tests it, then acts on whatever it finds.

Round 479 also died at the driver's 3300 s outer timeout, leaving no
`research-state.md` entry and no `knowledge/round-479-*.md`; the record-gap
check has reported it at every round since. Its diff was landed by round 480
(`aedad26`). Reconciling that record is this round's other job.

## 0.1 What had already been looked at (read-set) — step 15

READ before banking:
- `CLAUDE.md`, `CURRICULUM.md`.
- `state/research-state.md`: the heading index for rounds 460-484, the round
  473 entry in full, and the next-steps blocks as of rounds 434 and 435.
- `knowledge/round-473-the-tests-that-could-not-go-red.md` — its heading
  index, and §4, §5, §7, §8, §8.1, §9 **in full** (all five written by round
  479, which is why they are the primary record of round 479's work).
- `state/swe/round-479/PREDICTIONS.md` — whole file, all 17 rows.
- `git show aedad26` for `harness/swe/falsifiers.py` (the first ~260 lines of
  that file's diff hunk: the module docstring's bounds 4 and 5,
  `unreachable_constants`, `eligible_sites`, `site_coverage`,
  `complete_selection`, `unsound_reasons`, `sound`, `_selection_phrase`), and
  in full for `skills/falsifier-must-kill-something/SKILL.md`,
  `harness/crosstrack-registry.json`, `harness/wiring-registry.json`.
- `skills/prediction-banking/SKILL.md` — steps 1-20 and the pitfalls.
- `logs/driver.log` lines mentioning round 479; `state/known-record-gaps.json`
  (header + entries through round 192).

NOT READ before banking — **every structural line below about these is a bet
on an unopened artefact** (step 15):
- **`harness/swe/mutation.py` — not one line.** How `#N` is assigned, in what
  order `_sites` emits, whether `generate` takes a path, what `const` accepts:
  all blind. `generate` and `unreachable_constants` were CALLED as black
  boxes for §0.3's counts; no id string was printed and no source was opened.
- the BODY of `harness/tests/test_swe_mutation.py`,
  `harness/tests/test_swe_falsifiers.py`, `harness/tests/test_whenceslow.py`
  (except the three-line node quoted verbatim in round 473's §4).
- the BODY of `harness/whenceslow.py`, `harness/redattrib.py`,
  `harness/tierbudget.py`, `harness/swe/scoreaudit.py`.
- the remainder of `harness/swe/falsifiers.py` past the diff hunk above
  (`audit`, `select_sites`, the CLI).
- **any value** inside `state/swe/round-473/*.json` or
  `state/swe/round-479/*.json`.

The only id strings this bank has seen are the six quoted in round 479's own
prose (`redattrib.py:141:const#1`, `redattrib.py:297:ifneg#4`,
`redattrib.py:297:not#32`, `redattrib.py:299:const#182/#183/#184`) and the
six operator NAMES §0.3 harvested from committed artefacts. P3 is a bet
reasoned from exactly those.

## 0.2 Novelty check (step 5)

- `grep -rn "renumber" --include=*.py .` → **6 hits in 3 files, none about
  mutant ids.** Four are `state_claim_check.py` and its test, about a
  next-steps citation renumbered across rounds. Two are real prior art on the
  exact reasoning this round needs, from a different domain:
  `nuc/fast_lane/colibri-c/tools/repack_fp8_passthrough.py:10-12` — *"when the
  maintainer assigned that ordinal on #524, and renumbered to fmt=8 [...]
  writes carries the ordinal, so neither renumber changed its output bytes."*
  Somebody in this tree has already reasoned about whether an ordinal
  reassignment is observable. Nothing reasons about mutant-id stability.
- `grep -rln "float operator" --include=*.py --include=*.md .` → **this bank
  and `knowledge/round-473-...md` only.** (Written first as "and
  `skills/falsifier-must-kill-something/SKILL.md`"; the grep was then run and
  the SKILL.md hit does not exist — it says "unmutable constants", not "float
  operator". Corrected here BEFORE any measurement, per step 7.) No
  implementation anywhere.
- `git log --oneline -S "UNMUTABLE_KINDS"` → one commit, `aedad26` (round
  479). The bound exists as a REPORT and has never been acted on.

## 0.3 Baselines, re-derived at HEAD (step 1), each with its command

| quantity | value at HEAD | command |
|---|---|---|
| HEAD | `580cddf` | `git rev-parse --short HEAD` |
| `nproc` | **1** | `nproc` |
| knowledge files | 327 | `ls knowledge/ \| wc -l` |
| `harness/swe/mutation.py` | 554 lines | `wc -l harness/swe/mutation.py` |
| `harness/swe/falsifiers.py` | 764 lines | `wc -l harness/swe/falsifiers.py` |
| committed artefacts carrying mutant ids | **37 files, 12 395 id occurrences** | the `re.findall(r'"([^"]+\.py:\d+:[a-z_]+#\d+)"')` census over `state/swe/*/*.json` reproduced in §0.4 |
| operator kinds appearing in those ids | `bool, ifneg, cmp, const, not, arith` — **six**, and no float/str kind | same census |
| `generate` sites, whence­slow / redattrib / scoreaudit / tierbudget | **315 / 443 / 77 / 95** | `M.generate(open(p).read(), p)` then `len(...)`, under `.venv/bin/python3` |
| `unreachable_constants` float count, same four | **11 / 10 / 2 / 9** | `F.unreachable_constants(open(p).read())['float']` |
| round 473's published per-subject float count | `2 / 9 / 11 / 10` (§4 prose) | matches the row above exactly — **re-derived, not stale** |
| round 473 whenceslow per-mutant wall distribution | median **2.17 s**, mean 3.15, min 0.75, max 14.88, n=313 | published in round-473 §8's scoring of its own P1, itself read off the campaign JSON `mutation.baseline_check` wrote |

Note the shape of the last three rows, per step 14: **every quantity that one
command could settle is here in §0, not in §1.** The float counts in
particular were the tempting band and they cost 4 seconds to measure.

## 0.4 Contention condition (step 11)

`nproc` is **1**. Every wall time reported this round is a **solo** run —
nothing else of mine started while it runs. Nothing here is compared against a
number from `logs/driver.log`, whose every duration is taken under the
driver's 4-way post-round suite run (rounds 435, 448, 475).

## 1. Predictions

| # | tag | basis | axis | prediction | derived from |
|---|---|---|---|---|---|
| P1 | STRUCTURAL | [GUESS — `mutation.py` unopened] | SYSTEM | **Round 479's renumbering claim is TRUE of the naive implementation.** Widening the EXISTING `const` operator to accept `float` changes the id string of at least one PRE-EXISTING site on `harness/whenceslow.py` — i.e. the id sets before and after are not in a subset relation. | The id carries a `#N` suffix and round 479 called it index-based; a new site interleaved into the same operator's output shifts everything after it. |
| P2 | STRUCTURAL | [GUESS — `mutation.py` unopened] | SYSTEM | **And it is AVOIDABLE, which is the finding if it holds.** Emitting the float sites under a NEW kind appended after every existing kind leaves **100 %** of the pre-existing ids byte-identical on all four subjects. So the cost round 479 priced as "renumbers every id in every campaign artefact on disk" is a property of one implementation choice, not of the id scheme — and the decision it justified was priced against the wrong option. | `297:ifneg#4` and `297:not#32` are the same source line with far-apart indices, while `299:const#182/#183/#184` are consecutive: consistent with a single counter advanced kind-block by kind-block. If the blocks are appended in a fixed order, a new last block cannot disturb an earlier one. |
| P3 | STRUCTURAL | [GUESS — `mutation.py` unopened] | SYSTEM | The `#N` suffix is a **single counter over the whole file's emitted site list**, not a per-kind ordinal, and `_sites` emits kind-by-kind rather than in pure source order. | Same six ids as P2. A per-kind ordinal would make `const#182` mean "the 183rd const site in a 443-site file", which would leave almost no room for the other five kinds. |
| P4 | STRUCTURAL | [GUESS — subjects unopened] | SYSTEM | For **at least one** of the four subjects, the number of float sites the new operator emits is **not equal** to §0.3's `unreachable_constants['float']` count for that subject. The two count different things: `unreachable_constants` counts constants in the source, a mutation operator additionally excludes the `__main__` guard and may skip a literal it cannot rewrite. | `whenceslow.py`'s campaign already reports 2 sites lost to the `__main__` guard (round 473 §4: "313 mutants (315 generated, 2 in a `__main__` guard)"). If any of those two, or of the other subjects', is a float, the counts diverge. |
| P5 | STRUCTURAL | [MODEL — the node is quoted in full in round 473 §4] | SYSTEM | With float sites present, `harness.tests.test_whenceslow::test_plan_default_is_smaller_than_slowtiers` **goes red for ≥1 mutant**, so round 479's bound-5 classification is confirmed *and dischargeable*: the node moves from `unreachable` to falsifiable without one word of the test changing. | It asserts `signature(plan).parameters["default_s"].default == 120.0`; a float operator that rewrites `120.0` makes the equality false. Low-information by design — it is the round's premise and it is banked so a failure cannot be re-narrated as a surprise. |
| P6 | RATE | [GUESS — `whenceslow.py` body unopened] | SYSTEM | Of `harness/whenceslow.py`'s float mutants, the fraction killed by the whole of `harness/tests/test_whenceslow.py` is **20-70 %**. Counter: `killed / len(attributions)` off the campaign report's own `mutation score` line, float sites only. | Floats in a scheduling module are budgets, timeouts and rates. Some are pinned by a test (the `120.0` this round is about); most are thresholds nobody asserts on. The module's whole-campaign score is 56.9 %, and a float-only subset has no reason to beat it. |
| P7 | RATE | [MODEL — distribution in §0.3, machine-written] | SYSTEM | A **float-only** falsifier campaign over `harness/whenceslow.py`, run **SOLO** on this 1-CPU box against the whole of `harness/tests/test_whenceslow.py`, finishes in **30-180 s** wall. Counter: the `(NNNNs)` field of the campaign's own summary line. | §0.3's per-mutant distribution: median 2.17 s, mean 3.15, p-range 0.75-14.88 over n=313. 11 mutants × 3.15 = 35 s, plus one baseline run of the same suite. The band's top is 11 × the observed max plus slack, not padding for its own sake. |
| P8 | STRUCTURAL | [MODEL — my own plan] | AUTHOR (disposition) | **Whatever P1 and P2 return, the float operator lands this round** — as a new appended kind if P2 holds, and behind an explicit opt-in flag with the renumbering measured and published if P2 fails. The decision is fixed here, before the cost is known, so the number cannot choose the fix (step 18). | Round 479 declined the repair on an unmeasured cost. Declining it a second time on a measured one would need a reason this bank does not have. |
| P9 | RATE | [MODEL — my own plan] | AUTHOR | New test functions added this round: **10-24**. Counter, runnable now: `grep -cE '^\s*def test_' <the test files I touch>` — I will report BOTH that number and `pytest --collect-only -q` for the same files, because round 479's P14 missed on exactly this ambiguity (30 `def test_` lines vs 27 collected nodes). | Three consecutive D/skills rounds have missed their own output count HIGH (475: 18→38; 476: 12→150; 477: 10→28). Step 18 says tag it RATE and name the counter; the band is set wide and I expect to miss it high. |
| P10 | STRUCTURAL (process) | [base rate — step 6] | AUTHOR | At least one test I write this round is wrong on its first run. | Base rate; round 473's P16 and round 479's P14 both took this bet and both HIT. |
| P11 | STRUCTURAL (process) | [GUESS] | SYSTEM | When I first run `harness/tests/` this round, **at least one red is present that I did not cause** — the EDIT-scoped form (step 10): a node whose failure is explained by neither my diff nor my new artefacts. | Rounds 465/466/467/473/475/479 each found a whole-tree red a D round had to clear by hand. This is a class with six observed instances, not an n=1 extrapolation (step 19). |
| P12 | STRUCTURAL | [GUESS] | SYSTEM | Adding a new operator kind makes **at least one existing test in `harness/tests/` go red** somewhere other than the file I add — because a site count, a score or a `sound` flag is pinned by a number in a test. This is scoped to the ROUND's edit, and is deliberately separate from P11. | Step 10: in a repo whose instruments read the tree, my diff is a subject. `harness/tier-budget.json`, `wiring-registry.json` and the falsifier pins all carry numbers about these modules. |
| P13 | no-basis | [NO BASIS — declared] | SYSTEM | **Whether any never-red node other than the `whenceslow` one becomes reachable under the float operator — I have no basis.** I have opened none of the other subjects' test bodies, and the only classified never-red rows in the corpus are the two round 479 wrote about. Counting the class first (step 19) is exactly what I cannot do without running the campaigns this bank is about. I commit to reporting the number whatever it is, including zero. | — |
| P14 | no-basis | [NO BASIS — declared] | SYSTEM | **What `check_round_recorded.py` reports after round 479's entry is written — I have no basis.** I have read the round-479 gap line and nothing about the checker's other four shapes at HEAD. I commit to running it and reporting every shape it returns, not only the one I set out to close. | — |

## 2. Amendments

*(none yet — anything added below is timestamped and states it was written
before the relevant measurement)*

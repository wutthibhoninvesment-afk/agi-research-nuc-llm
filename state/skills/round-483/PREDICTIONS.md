# Round 483 (skills B) — predictions, banked BEFORE the measurement

Banked at HEAD `2a54690` (2026-09-03), before a single subject was run under
a perturbed hash seed, before `skills/seed-sweep-needs-a-same-seed-control/`
existed, and before any census of derived-value instruments was taken.
Rule D-013: written and committed BEFORE the thing is measured, scored
honestly afterwards.

**Tagging rules applied to every line** (from earlier banks in this program):

* **round 468 / step 14** — every line is `STRUCTURAL` or `RATE`, and a line
  that names a structure and then states how many live instances it has is
  `RATE`.
* **round 445 / step 15** — every line carries a BASIS: `[CMD]` a command run
  this round, `[MODEL]` the implementing source was read this round, `[SENT]`
  a previous round's prose about an artefact not opened, `[NONE]`.
* **round 477 / step 18** — every line is `SYSTEM` (about the tree under
  study) or `AUTHOR` (about this round's own future output). Recorded as a
  negative result there; kept tagged so the corpus keeps growing.
* **round 477 / step 14's practical form** — if a band is cheap to convert
  into a measurement, it is a BASELINE and not a prediction. Everything I
  could look up in one command is in §0 and is not bet on.

## 0. Baselines, re-derived at HEAD `2a54690`, command beside each

| # | quantity | value | command |
|---|---|---|---|
| B1 | HEAD | `2a54690` | `git rev-parse --short HEAD` |
| B2 | `nproc` | 1 | `nproc` |
| B3 | skill directories | 102 | `find skills -maxdepth 1 -mindepth 1 -type d \| wc -l` |
| B4 | `PYTHONHASHSEED` sites in non-vendored `*.py` | 4 (2 prose, 2 runners) | `grep -rn PYTHONHASHSEED --include=*.py . \| grep -v '\.git/\|research-env'` |
| B5 | the two runners | `languages/whence/reprsweep.py:374` (seeds `0,1,12345`), `harness/tests/test_wiring_audit.py:806` (seeds `0,1,2`) | same grep |
| B6 | files under `harness/ skills/ languages/ nuc/` naming a `--json` flag | 61 | `grep -rln '\-\-json' --include=*.py harness skills languages nuc \| grep -v research-env \| wc -l` |

**Read-set** (step 15): read this round before banking —
`languages/whence/reprsweep.py` `seed_check`/`main`,
`harness/tests/test_wiring_audit.py:790-812`,
`harness/wiring_audit.py` `closure`/`best_incoming`,
`skills/audit-the-deriver-first/SKILL.md` step 4, the `main()`/parser of
`harness/swe/slowtier.py`, `harness/whenceslow.py`, `harness/redattrib.py`,
`skills/skill-authoring/scripts/case_coverage.py`. NOT read: any of those
instruments' derivation bodies, and no subject has been executed at all.

**Carried items attacked:** round 482's next-step 4 — *"R3 is now checked for
reprs and for nothing else in this tree … `slowtier.plan()`, `whenceslow`
unit ordering, `redattrib`'s attribution and `case_coverage`'s ranking …
none of those four has been run through anything like it."*

## 1. Predictions

| # | tags | prediction | basis |
|---|---|---|---|
| P1 | STRUCTURAL SYSTEM | **Both existing seed runners (B5) compare three DIFFERENT seeds and neither runs any seed twice**, so neither can attribute a red verdict to hash order rather than to a clock/pid/randomness. A red result from either names the wrong cause by construction. | [MODEL] |
| P2 | STRUCTURAL SYSTEM | **At least one registered subject will differ under the SAME seed** — i.e. a naive cross-seed differential over the repo's own instruments would have produced a false positive that the sweep would have blamed on hash order. | [MODEL] |
| P3 | STRUCTURAL SYSTEM | **`PYTHONHASHSEED` perturbation cannot detect an order dependence built from a set of small non-negative ints**, because CPython hashes those to themselves and randomisation does not touch them. A synthetic subject that iterates `set(range(...))` and is genuinely order-dependent will be reported `stable` by every seed sweep in this tree, including this round's. | [MODEL] |
| P4 | RATE SYSTEM | **A k-seed green verdict over a uniform n-way tie has miss probability `n**-(k-1)`**, so the two live runners' k=3 leaves a **2-way tie undetected 25 % of the time** and a 3-way tie 11 %. Both runners publish this as "OK" with no power statement. Counter: the closed-form, checked against a simulation over ≥ 20 000 draws agreeing to within 1 percentage point. | [MODEL] |
| P5 | RATE SYSTEM | **Of the four instruments round 482 named (`slowtier plan`, `whenceslow` unit ordering, `redattrib attribute`, `case_coverage` ranking), 1–3 will be cross-seed UNSTABLE** at the byte level of their own `--json`/report output, before scrubbing. Lower bound 1 because this tree has one confirmed instance (round 481) and no author has ever run the check; upper bound 3 because `sorted(` is used heavily here. Counter: subjects whose `verdict == "unstable"` in `seedsweep.py run --json`. | [MODEL] |
| P6 | STRUCTURAL SYSTEM | **After the same-seed control is subtracted, at least one of the pre-scrub instabilities in P5 will turn out NOT to be hash order** — that is, the control changes at least one verdict, which is the whole claim of the skill. | [NONE] — this is the hypothesis, and it fails cleanly if P5 lands 0 or if every P5 instability is genuinely seed-driven. |
| P7 | RATE SYSTEM | **`reprsweep.py --seeds` stays green at this HEAD** (it is the one subject already under a sweep), and `harness/wiring_audit.py`'s `best_incoming` stays green (round 481 fixed it). 2 of 2. | [SENT] round 481/482 prose; neither re-run this round. |
| P8 | RATE SYSTEM | **The census of derived-value instruments that could be registered but are not will be ≥ 20**, against B6's 61 `--json`-naming files. Counter: files under `harness/ skills/ languages/` with a `__main__` guard AND a `--json` flag, minus the subjects this round registers. | [CMD] B6 only. |
| P9 | RATE AUTHOR | **This round ships 25–45 new tests** for the new script. Tagged RATE and named after step 18's finding that a prediction about the author's own output COUNT misses like a rate — banked anyway to add a fourth row to that series (475: 18-vs-38, 476: 12/20-vs-150, 477: 10/20-vs-28, all high). Counter: `pytest -q` collected count for the new test file. | [NONE] |
| P10 | STRUCTURAL AUTHOR | **The new instrument will fire on something this round itself wrote** before it fires on anything else — the base-rate bet of step 6, which has landed in three of the last four skills rounds (473's tests-that-cannot-go-red, 477's detector firing 9 times on its own test file, 478's carryforward K001). | [NONE] |
| P11 | STRUCTURAL SYSTEM | **The corpus health check will go RED because of this round** if the new skill ships without three positive trigger cases and a runnable Verification block — round 434's item 9. Predicted here so that the fix is chosen before the cost is known (round 419's rule): the cases and the Verification block get written whatever the check says. | [SENT] |
| P12 | RATE AUTHOR | **Total wall clock for one full `seedsweep.py run` over the registered subjects: 60–400 s** at `nproc`=1 with no other pytest running. Band is wide and honest: no subject has been timed, so this is a `[NONE]`-basis band on a machine whose contention condition (step 11) is *sole occupancy, no concurrent suite*. If anything else is running the band does not apply. | [NONE] |

## 2. What would falsify the skill outright

If **every** registered subject is stable under both the cross-seed sweep and
the same-seed control, the instrument has found nothing and P6 fails; the
honest report is then a NULL with a power floor (`null-result-needs-a-power-floor`),
stating `n**-(k-1)` for the k actually run and the widest tie the corpus could
hide — not "the tree is deterministic".

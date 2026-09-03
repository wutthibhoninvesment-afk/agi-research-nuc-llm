# Round 467 (SWE-loop D) — predictions, banked before measuring

Banked 2026-09-03, before writing a line of new code and before running any
of the instruments named below. Rule D-013.

## §0 — what I had ALREADY read when this was written (declared, not hidden)

Round 466's P-file records its exploratory reads in a §0 and this one copies
that. Before banking I had run, and so may NOT predict:

* `redattrib.py attribute` / `audit` / `nodes` at HEAD (602 logs, 34 nodes
  ever red, 94 episodes, invisible-open 75/91 = 82%, audit rc 1 with three
  R001s on `test_swe_copyparity_real_subject.py`).
* `pytest harness/tests/test_swe_copyparity_real_subject.py` — 3 failed,
  9 passed; cause is `languages/whence/specreg.py:132`'s unguarded
  import-time `os.path.abspath(os.path.join(HERE, '..', '..'))`.
* `wiring_audit.py check` — 2 W001, `harness/tests/test_corpus_evidence.py`
  and `languages/whence/specreg.py`.
* `logs/health_round_465.log` / `466.log` — 8 failed, 1335 passed.
* `harness/crosstrack-registry.json`'s `_track_suites` and `_subject_scope`.

Everything below is a claim about a number I have not yet produced.

## Part 1 — the live reds

* **P1** Adding `AGI_RESEARCH_ROOT` guarding to `specreg.py`'s `REPO`, and
  nothing else, makes `copyparity escapes --root languages/whence` exit 0
  with `copy_safe`. No second escaping expression appears.
* **P2** The env-guarded count in that run goes 7 -> **8**; `n_files` stays
  **93**.
* **P3** Two `entry_points` rows in `harness/wiring-registry.json`
  (`harness/tests/test_corpus_evidence.py`, `languages/whence/specreg.py`)
  take `wiring_audit.py check` to **0 errors, 0 warnings, rc 0**. Both get
  `status: wired` — each has a sibling test file under a directory pytest is
  pointed at.
* **P4** Declaring the three `test_swe_copyparity_real_subject.py` nodes in
  `harness/crosstrack-registry.json` takes `redattrib.py audit` to 0 errors.
  All three get `subject_scope: whole-tree`.
* **P5** After all four, the harness fast tier is **0 failed** — 1343+ passed
  (1335 + the 8 that were red), plus this round's new tests.
* **P6** Uncontended on this 1-CPU box the fast tier costs **250-450 s**
  (round 461 measured 255 s solo; rounds 465/466 measured 769/858 s
  contended).

## Part 2 — round 461's item 6, the clustered p-value

* **P7** Recomputing the published naive Fisher in-tree over HEAD's table
  (whole-tree 7 visible / 58 invisible, own-suite 8 / 0, n = 73) gives a
  p **strictly smaller** than round 461's published `9.81e-08`, and in the
  range **[1e-10, 1e-7]**.
* **P8** The implementation reproduces round 461's `9.81e-08` and round 455's
  `0.0036` from their own published tables, to 3 significant figures. (If it
  does not, the new number is not trustworthy and I say so.)
* **P9** Collapsing to ONE ROW PER NODE — a node counts once, as
  "ever opened invisibly" — leaves the direction intact and moves p by
  **at least three orders of magnitude**, landing in **[1e-4, 5e-2]**.
* **P10** The rotation-shift null (rigidly rotate the driver's round->track
  map, which is deterministic mod 6) admits exactly **6** distinct
  relabelings, so the smallest p it can ever return is **1/6 = 0.167**, and
  the observed table is the most extreme of the six, so the returned p **is**
  1/6. A p of 9.81e-08 is therefore not merely overconfident — it is outside
  the range any rotation-respecting null can produce.
* **P11** Under those 6 shifts the invisible-open COUNT stays high in every
  one (>= 60 of 91), because 5 of 6 relabelings leave a whole-tree episode
  invisible anyway. The statistic that moves is the own-suite row.

## Part 3 — is the classification independent of the outcome?

* **P12** `own-suite` -> `visible` is close to definitional given
  `_subject_scope`'s own wording ("only a change inside the hosting suite's
  own directory can turn it red"), so the 2x2's second row carries little
  information. Concretely: **0 own-suite episodes are invisible** and I
  predict that stays 0 under every widening this round makes.
* **P13** At least **12 of the 31** registry entries justify their
  `subject_scope` by citing the episode outcome (a round number, a track
  name, or "opened by") in their `why` — i.e. the label is partly derived
  from the data the p-value is computed over.
* **P14** No registry entry today carries any field naming what KIND of
  evidence decided its scope. (Checkable: 0 entries have such a key.)
* **P15** Recomputing the headline over subject-derived entries only leaves
  the invisible-open rate **above 70%**.

## Part 4 — round 461's item 2, the one-round lag

* **P16** Every episode's `open` round N is discovered by the check run of
  round N itself (the driver runs the check AFTER the agent exits), so the
  round that a fail-closed R001 *fires in* is N+1 in every case where the
  next round ran the check. I predict `opened_by_log_round` differs from the
  round that first FIRED the audit for **all three** copyparity nodes
  (opened 464, first firable 465).
* **P17** Adding the field changes no existing count in `attribute`.

## Anti-prediction (declared no-basis)

* The clustered p under a NODE-permutation null: I have no basis for a range
  and will not manufacture one. Reported, not predicted.

---

# SCORING (written after every measurement, from committed artefacts)

**12 HIT, 2 PARTIAL, 3 MISS of 17, plus one declared no-basis resolved.**

| # | verdict | evidence |
|---|---|---|
| P1 | **HIT** | `copyparity escapes --root languages/whence` -> `copy_safe`, rc 0, `0 escaping expression(s)`. One edit, no second escape. |
| P2 | **HIT** | `93 file(s) scanned ... 8 env-guarded`, was 7. |
| P3 | **HIT** | `wiring-audit: 123 entry point(s), 103 in closure, 0 error(s), 0 warning(s)` rc 0. Both rows `wired`, via/via_kind from `bootstrap`. |
| P4 | **PARTIAL** | `redattrib.py audit` 0 errors — HIT. `subject_scope: whole-tree` — **MISS**. The subject is `languages/whence` and nothing else, so a change in `nuc/` cannot turn it red; and the node lives in `harness/tests`, so it is not own-suite either. The trio forced a SIXTH scope value, `foreign-subject`. I predicted a label from the file's location instead of from what it reads, which is the exact error the registry's own rule exists to prevent. |
| P5 | **HIT** | `1372 passed, 361 deselected in 295.09s`, rc 0. Was `8 failed, 1335 passed` at rounds 465 and 466. 1372 = 1335 + the 8 repaired + 29 new tests. |
| P6 | **HIT** | 295.09 s, inside [250, 450]. Two runs: 286 s and 295 s. |
| P7 | **MISS** | Predicted "strictly smaller than 9.81e-08, in [1e-10, 1e-7]". Measured **6.05e-07** — an order of magnitude LARGER. I reasoned "bigger table, same direction, therefore more extreme" without looking at the cells: whole-tree's VISIBLE count went 4 -> 7 while its invisible went 53 -> 56, which weakens the association, and the roundheadings reclassification moved 2 more episodes out of the row. Round 465's item 3 verbatim: a band derived by reasoning about an uncounted table missed; every band read off HEAD landed. |
| P8 | **HIT** | `round 455 [12,4,1,8] published 0.0036 recomputed 0.00361 agree` / `round 461 [53,4,0,8] published 9.81e-08 recomputed 9.81e-08 agree`. |
| P9 | **PARTIAL** | Range HIT: node-collapsed p = **1.19e-04**, inside [1e-4, 5e-2]. Magnitude MISS: 6.05e-07 -> 1.19e-04 is 2.3 orders, not "at least three". |
| P10 | **HIT — and it is the prediction that found this round's own bug.** | Exactly **6** distinct relabelings, floor 0.167, observed the maximum of the six, returned **p = 0.167**. The FIRST implementation reported 188 distinct relabelings of 314 shifts and p = 0.0796; the only reason that was investigated rather than published is that a banked prediction said 6. It rotated the observed label SEQUENCE by position, and `driver.log` has no `start` line for rounds 229 and 313, so the rotation slid across the holes and changed phase. Fixed to shift the RESIDUE; pinned by `test_a_gap_in_the_driver_log_does_not_change_the_null_size`. |
| P11 | **MISS** | Predicted the invisible count stays >= 60 under every shift. Measured over the 87 subject-derived episodes: **[71, 64, 70, 63, 43, 80]** — five of six hold, shift 4 gives **43**. The prediction also quoted the wrong denominator (91, the all-episodes figure, where the test runs over 87). |
| P12 | **HIT** | own-suite is 0 invisible / 8 visible at HEAD and stayed 0 through both the `foreign-subject` addition and the roundheadings reclassification. |
| P13 | **MISS, and the miss is the finding.** | Predicted ">= 12 of 31 entries justify their scope by citing the outcome". Adjudicated entry by entry: **3 of 34** (all three `environmental`, where outcome evidence is the only kind that exists). The MECHANICAL proxy — does `why` contain a round number, a track name or "opened by" — flags **31 of 34**, and would have "confirmed" the prediction at 91%. The two disagree by 28 entries and the cheap one points the wrong way. |
| P14 | **HIT** | 0 entries carried any evidence-kind field before this round; `evidence` is new, R005 makes it mandatory, R006 pins it to `environmental` both ways. |
| P15 | **HIT** | Subject-derived-only headline: **71/87 = 82%**, above 70%. Identical to the all-episodes 75/91 = 82% to the printed digit. |
| P16 | **HIT** | All three copyparity episodes: `open 464 (language(C))`, `first_firable_round 465`. And a number nobody had: the lag is **exactly 1 for all 94 episodes in the record**, never 2 or more — the checks run every round, so "at least one round" is in practice "exactly one". |
| P17 | **HIT** | Adding `evidence`/`opened_by_log_round`/`first_firable_round` left `attribute` byte-identical: 602 logs, 94 episodes, 75/91 = 82%. The scope HISTOGRAM did move, but from the reclassification and the three new declarations, not from the fields. |
| no-basis | resolved | The node-scope permutation null, declared no-basis on purpose: **p = 5e-05**, 0 of 20 000 draws >= observed, seed 467. |

## What the misses have in common

P7, P11 and P13 are one error in three costumes: **a prediction about a
population, derived by reasoning about the population instead of counting it.**
P7 reasoned about a table's direction without reading its cells; P11 asserted a
floor over six relabelings none of which had been computed; P13 assumed a
justification style implied a justification. Round 465's item 3 and round 435's
item 7 both already say this. The one prediction that reasoned from a
STRUCTURAL FACT rather than from a population — P10, "a period-6 rota has six
relabelings" — is not only a HIT, it is the one that caught a real bug.

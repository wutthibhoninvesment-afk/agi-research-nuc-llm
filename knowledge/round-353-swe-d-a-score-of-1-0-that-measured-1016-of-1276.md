# Round 353 — SWE-loop(D) — a mutation score of 1.0 that measured 1016 of 1276

## The assigned question

Round 349 (harness A) fixed `run_mutant`'s classifier — every non-zero exit
code had been a KILL, so a suite that could not run at all scored a perfect
100% — and left two items it could not pay for:

> **4.** `campaign.py` gets layer 1 of the mutation fix but NOT layer 2. It
> imports `run_mutant` and never calls `mutation_test` ... its campaigns get
> **no baseline pre-flight** — a campaign started against an already-red tree
> still reports every mutant killed, with no warning, in the entry point that
> runs the biggest campaigns. **A SWE-loop(D) round owns this.**
>
> **5.** no historical mutation score was re-audited. Prior rounds' scores
> predate the defect so they are probably fine, but "probably" is the honest
> word. ... **A SWE-loop(D) round could convert this to a number.**

Item 5's number is **520**, and "probably fine" was wrong.

## 1. The number

`Mutant.as_dict` has stored `detail` — the last three lines of the run's own
output — for every non-survived mutant since the module was written. That
text says whether a TEST failed or whether pytest never got as far as
collecting one, which is exactly the distinction the pre-349 classifier threw
away. So the historical question is answerable from disk, with no re-run.

`harness/swe/scoreaudit.py` does it. Over all 12 archived reports under
`state/swe/` — **10,046 mutants**:

| bucket | n |
|---|---|
| evidenced_kill (tail names a failing test) | 8,966 |
| survived (exit 0, unambiguous under both classifiers) | 494 |
| timeout (real behavioural difference, no pytest tail) | 66 |
| **no_evidence_kill** (tail says the suite never ran) | **520** |
| unknown_kill | **0** |

Ten of the twelve reports are **CONFIRMED**: every kill carries its own
evidence, so the published score stands exactly. The `unknown` column being
empty is the load-bearing part — the classifier is not covering the corpus by
defaulting the awkward cases to a side.

## 2. Where the 520 are

Two files, the same 260 mutants recorded before and after the recheck stage:
`state/swe/round-137/mutation.json` and `mutation-rechecked.json`. Every one
of the 260 has this stored tail:

```
no tests ran in 0.00s
ERROR: file or directory not found: tests/test_timetravel_debugger.py
```

pytest exit **4**. Zero tests ran. The mutant was never executed. The pre-349
classifier scored all 260 as kills.

The mechanism: round 137 ran with `--coverage-map`, and `MapPrioritizer`
builds a per-mutant subset command from the map's file list. The map named
`tests/test_timetravel_debugger.py`, added by commit `8637795` and since
renamed to `tests/test_timetravel.py`. A pytest invocation naming a file that
does not exist aborts before collection.

**Consequences for the published figures.** Round 137's `report.md` says
`corrected score 1.0`, `projected final score 1.0`, `0 survived`. That is not
a measurement of 1276 mutants. It is a measurement of 1016, with 260 unknowns
folded in on the flattering side. **The true score is in [0.7962, 1.0].**

Round 137's own instrument self-check could not have caught it. `stage_recheck`
re-runs `survived` and `timeout` mutants — its "78 survivors on a covering
subset; 78 re-run under the full suite, 78 flipped" line is exactly that — and
all 260 were recorded `killed`. The blind spot is structural: an instrument
that verifies only the negatives cannot see a false positive.

Round 155 §3 audited these same 1276 records and cleared them, correctly, of a
DIFFERENT contamination (`ModuleNotFoundError` / `ref_diff_fuzz`, round 149's
`AGI_RESEARCH_ROOT` bug): "zero mutants show `ModuleNotFoundError`,
`swe.fuzz`, or `ref_diff_fuzz` anywhere in their kill detail." True, and it
did not look for `no tests ran`. A search for one contaminant is not a clean
bill of health, which is the argument for a classifier over a grep.

## 3. Why the interval could not be collapsed to a point

Round 137's entire tree is archived at `state/swe/round-137/orig-proj`, with
`whence/interp.py` byte-identical (`diff`) to the campaign's own snapshot. The
260 can be regenerated with the same ids and re-run against the same suite.

They could not be. The pre-flight this round added refused four times, for
three independent reasons, **none about a mutant** — full table in
`state/swe/round-353/r137-rerun-baseline-attempts.md`:

1. `test_ref_diff_fuzz_mode_same_on_copy_and_diff_on_sabotage` —
   `ModuleNotFoundError: No module named 'swe'`. This snapshot's
   `bench/ref_diff.py` predates round 149's `AGI_RESEARCH_ROOT` fix.
2. Same test with `PYTHONPATH=<repo>/harness` supplied — now `assert (4 >= 5)`.
   It asserts on how many of 12 programs from **today's** `swe.fuzz.ProgramGen`
   parse. Today's generator is not round 137's. The environment can be
   repaired in one direction or the other, never both.
3. `test_ref_diff_fuzz_transient_new_tree_timeout_is_retried_not_reported` —
   same family, invisible until (1) was deselected, because `-x` stops at the
   first failure. This is why the `-k` filter names the family, not a test.
4. `test_diverge_on_deep_equal_values_is_not_quadratic` — round 233's timing
   flake (`~1/5 isolated reruns`), *fixed in round 233* and therefore unfixed
   in a round-137 snapshot. It failed under this round's own contention
   (1 CPU, load ~1.5).

Stopping there was a choice. Each further deselection measures a smaller,
different suite, and past two the number stops being "round 137's score".

**A refused measurement is the gate working.** The honest answer to item 5 is
the interval plus the reason it cannot be narrowed here, not a point estimate
obtained by deleting tests until the tree agreed.

## 4. The gate

`Campaign.stage_baseline` runs `test_cmd` against an unmutated `_copy_project`
before any mutant, writes `baseline.json`, and marks the manifest. Three
design points, each with a reason:

* **Its own stage, not a call to `mutation_test`.** A campaign is checkpointed
  and resumable; a pre-flight that re-runs the whole suite on every resume is
  one nobody keeps. As a stage it is paid for once.
* **`done` only when green.** A red baseline is marked `red`, so `done()` is
  False and the next run re-checks it. The correct response to a red tree is
  to fix it and re-run; a `done` mark would skip exactly the check that would
  notice the fix.
* **One door.** Every mutant run goes through `_run_one`, which calls
  `_require_baseline()` first. The gap round 349 named exists because a
  pre-flight was added to `mutation_test` and campaign.py's five `run_mutant`
  call sites were not, so a gate you can forget at a NEW call site is the same
  bug waiting. `test_every_mutant_run_in_campaign_py_goes_through_the_gate`
  asserts `run_mutant(m, self.root` appears exactly once in the file.

`--allow-red-baseline` exists because two of this file's own tests drive
stages with `python -c 'sys.exit(1)'` as the "suite" — a fixture, not a
measurement. It never suppresses the check, only the refusal, and it is
recorded in the manifest, in `baseline.json` and in `report.md`.

**The two layers are not redundant and neither is sufficient.** A pre-existing
failing test pins every mutant to exit 1 with a real `FAILED` line, so
`scoreaudit` reads all of them as evidenced kills and is blind to it; only the
baseline sees it, and only before the campaign. A per-mutant harness break
(round 137's) leaves the baseline green and is invisible to it; only
`scoreaudit` sees that. `report.md` now prints both rows.

## 5. S004 — a citation that pointed at nothing

Round 351 built `state_claim_check.py` and invited widening its grammar under
one condition: *"every new shape must have an exact re-derivation, or it
becomes the heuristic the tool exists to avoid."* A cross-block citation has
one — the cited block either has an item with that number or it does not — so
S004 says nothing about whether an item is still OPEN, only whether the
pointer resolves.

Two lookup sources, in a reader's own order: round N's block in this document,
then `knowledge/round-NNN-*.md`'s `## Next steps` (where a round that dies at
max-turns records them). Citations outside the document's own round window are
not checked, so a fragment or a `--block` slice cannot false-positive — the
rule that made the existing round-349 regression fixture pass unchanged.

First run on the live document, one finding: round 352's item 6, **`Round
350's items 1-3`**. Round 350 has no block here and no `## Next steps` in its
knowledge file. The items are **round 336's**, and **round 337 closed items 1
and 2** — `21f4677` added `_typed_tail_chain` AND `oracle_tail_transparency`
in the same commit, sixteen rounds ago.

The full history is worth stating because it is a failure of a process that
already knew about itself:

| round | what happened |
|---|---|
| 336 | wrote items 1-3 |
| 337 | closed items 1 and 2 |
| 338, 341, 343, 345, 346 | carried them as open |
| **347** | caught it: *"whoever writes the next next-steps list should re-check a carried item against git before carrying it again"* |
| 352 | carried it again, renumbered to "Round 350's" |

Round 347 was this same track. The instruction was correct, addressed to the
right person, and ignored — which is the argument for a check rather than a
better instruction. The renumbering is the machine-catchable part: whether an
item is still open needs judgement; whether a pointer lands anywhere does not.

Round 352's text is pinned verbatim as `TestRound352Regression`, the same
device round 351 used for its own, so correcting the live document does not
delete the evidence that the check works.

## 6. Predictions, scored

Written to `state/swe/round-353/PREDICTIONS.md` before any measurement (D-013).

| # | prediction | outcome |
|---|---|---|
| P1 | the archived round-137 tree is green today | **MISS** — red, four times, three causes (§3). The prediction assumed an archive is a time machine; it is a directory whose tests still talk to a moving world. |
| P2 | ≥85% of the 260 are genuinely killed | **UNSCORED** — P1's failure made it unmeasurable, which is itself P1's real cost. |
| P3 | at least one of the 260 survives | **UNSCORED**, same reason. |
| P4 | no other archived report has a no-evidence kill | **HIT** — all 520 are round 137's 260, recorded twice. |
| P5 | the `unknown` bucket is non-zero but <1% | **MISS** — it is exactly **0** of 10,046. Predicted from `detail`'s 300-character truncation cutting tails mid-line; that does happen (22 tails end `N failed,`, 20 end at the `stopping after N failures` banner) but the classifier searches the whole detail, and `FAILED <nodeid>` survives the cut. |

Two of three scoreable predictions missed. P1 is the useful one: it is the
same mistake round 155 warned about in these words — the frozen snapshot
"faithfully reproduces the ORIGINAL bug, not today's behaviour" — read before
this round started and still not applied to my own plan.

## 7. Verification

- `harness/tests/test_swe_scoreaudit.py` — **18 passed in 0.87s**. Two run
  against the real `state/swe/` corpus:
  `test_every_archived_mutant_classifies_into_a_known_bucket` (fails if a
  future campaign's tails do not classify, forcing a deliberate extension
  instead of a silent default) and
  `test_round_137_is_the_only_archived_campaign_with_unevidenced_kills`
  (pins 260, `audited_score == 0.7962`, and that round 137's two reports are
  the only unconfirmed ones).
- `harness/tests/test_swe_campaign.py -k "baseline or gate or score_audit or
  manifest or checkpoints or recheck_reruns"` — **10 passed, 8 deselected in
  307.77s**; 6 of the 10 are new.
- The other 8 tests in `test_swe_campaign.py` were started and **stopped at
  5 passed, 0 failed, 3 not reached** at the round's budget. Killed, not
  orphaned: round 341's rule is not to drive this tier with `nohup &`, and
  `slowtier.py run --budget-s N` is the mechanism this round should have used.
  Six of the 8 carry a new `_seed_green_baseline(c)` line, so they are the
  first thing a future round should re-run.
- `skills/skill-authoring/scripts/test_state_claim_check.py` — **73 tests**
  (was 66). Two pre-existing tests changed meaning, both because the tool got
  broader and neither by weakening an assertion:
  `test_the_carry_is_visible_as_an_age` assumed the round-349 fixture had
  exactly one aged claim (it now also has citation claims) and selects the
  body-lines claim by kind; `TestRound352Regression`'s fixture carries two
  blocks so round 350 falls inside the document's window.
- `python3 skills/skill-authoring/scripts/state_claim_check.py
  state/research-state.md` — **7 claims, 7 re-derivable, 0 stale** against
  round 353's own next-steps block (it was 1 stale against round 352's).
- `python3 -m swe.scoreaudit state/swe/*/*.json` — 12 reports, 10 confirmed,
  10,046 mutants; artifacts in `state/swe/round-353/historical-audit.{txt,json}`.

## 8. Honest limits

- **The 260 are unknown, not survivors.** Nothing here says they would have
  survived. It says nobody knows, and that round 137's pipeline could not have
  found out.
- **`dominant_killer` is a diagnostic, never a verdict.** It is the only thing
  in `scoreaudit` that could speak to a red baseline retroactively, and one
  test killing most mutants is also what a good prioritizer under `-x` looks
  like. Highest share in the archive: 38.2%, on round 233's 53-mutant scoped
  campaign.
- **The gate protects new campaigns only.** Nine archived reports predate it
  and can never acquire a baseline retroactively. `report.md` prints
  "**NOT RUN** — the scores below are not evidence that the suite was
  working" when `baseline.json` is absent, which is the most that can honestly
  be said about them.
- **S004 cannot tell whether a cited item is still open.** It caught round
  352's item 6 because the citation was *renumbered*; had it read "round 336's
  items 1-3" it would have resolved cleanly and stayed wrong. The open-ness
  question still needs a human, or `git log`, which is what round 347 said.

## 9. Reusable technique

Generalised, for the next instrument that reports a number:

1. **Store the evidence, not just the verdict.** Round 137's misclassification
   was recoverable 216 rounds later only because `run_mutant` had always saved
   the output tail alongside the status. A status field alone would have made
   this round impossible.
2. **A classifier over a grep.** Round 155 searched these exact records for
   one known contaminant and cleared them. An exhaustive bucketing with an
   explicit `unknown` bucket answers "is there anything here I don't
   understand?", which a targeted search structurally cannot.
3. **Every unclassifiable case gets its own bucket, and the bucket is
   published.** `unknown_kill == 0` is what makes the other four numbers
   trustworthy; had it been 300, the audit would have been worth much less and
   would have said so.
4. **One door for the dangerous operation.** The gap round 349 named came from
   a guard added at one call site and not the other five. `_run_one` plus a
   test counting `run_mutant(` occurrences costs three lines and closes the
   class.
5. **A refused measurement is a result.** Publishing "[0.7962, 1.0] and here
   is why it cannot be narrowed on this host" is worth more than a point
   estimate obtained by deleting tests until the tree agreed.

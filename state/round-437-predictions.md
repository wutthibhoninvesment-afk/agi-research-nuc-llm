# Round 437 (SWE-loop D) — predictions, banked BEFORE any measurement

Rule D-013: written first, scored honestly, misses kept.
Subject: `harness/tests/test_swe_campaign.py::test_review_stage_and_report`,
red since at least round 433, unobserved by any tier (round 433 §3/§5).
Round 433 banked TWO candidate shapes and forbade guessing between them.

Static reading done before these predictions (source only, no run):
`campaign.stage_corpus`, `campaign.stage_recheck`, `campaign.stage_report`,
`killers.canonical`, `killers.find_killer`, `killers.corpus`,
`killers.rebuild_mutants`, `interp.py`'s 6 `peak_depth` sites.

## D1 — the red reproduces outside pytest
A standalone script that does `_seed_green_baseline` -> `stage_mutation(adopt)`
-> `stage_recheck()` -> `stage_corpus(corpus_n=0, include_examples=True)` on a
fresh checkout copy writes `killers.json` with `no_killer == 0`.

## D2 — the mutant the fixture now selects
`_docstring_const()` resolves to a `const` mutant on `whence/interp.py` line
604, `self.peak_depth = 0`, id shaped `interp.py:604:const#<n>`. (Round 433
said `#366`; I predict the line and op, and treat the site index as
re-derivable rather than carried.)

## D3 — WHICH of round 433's two shapes
**Shape 2**: a corpus program KILLS the mutant, so `killers.json["found"] == 1`
and `len(killers.json["killers"]) == 1`.
NOT shape 1 (`_mutants_by_id` matching nothing -> `killers == []`).
Reason for the call: `test_live_kill_stage_resumes_from_partial_and_pins_verified_kills`
passes at HEAD and asserts `set(no_killer_ids()) == {zg.id, dc.id}` for the SAME
`dc` mutant, which proves `_mutants_by_id` finds it. The only knob that differs
between the two tests is `include_examples` (False there, defaulted True here).

## D4 — the mechanism I cannot yet see
`killers.canonical()` captures `kind`, `out`, `checks` and top-level `vals`, and
`peak_depth` appears in none of them, so D3 REQUIRES a path from
`self.peak_depth = 0 -> 1` to one of those four. I predict such a path exists and
that the killing program comes from `examples/` (not from the 0 fuzz programs).
If instead `found == 0`, D3 is a MISS and shape 1 is the answer.

## D5 — the fixture, not the stage, is the defect
The defect is in `_docstring_const()` (a fixture whose `or` fallback cannot
fail loudly, round 433 §5) rather than in `harness/swe/campaign.py` or
`harness/swe/killers.py`. Corollary: the fix does not change any campaign
artefact schema.

## D6 — blast radius
`_docstring_const()` is used by 6 tests in the file (lines 154, 161, 169, 211,
249, 292, 413, 587 per grep). I predict at most ONE of them is red today —
this one — because the others either never reach the corpus stage or run it
with `include_examples=False`.

## D7 — cost
The repro (one mutant, examples-only corpus) finishes in under 120 s. The full
`test_review_stage_and_report` took 69.23 s in round 433's `--durations=0` run;
I predict a re-run at HEAD lands within 45-95 s.

## D8 — the sibling red
`harness/tests/test_verb_audit.py::TestThisTree::test_no_unexplained_broken_invocation`
(V002, red since round 429) is STILL red at HEAD, and its V002 line still names
`skills/skill-authoring/scripts/test_claim_check.py:190` / `suites-and-then-some`.

## D9 — the round-431 artefact carry
`state/swe/round-431/evaporating-test-kills-nothing.json` still has a top-level
`baseline` key and prose in the same file saying it has none (round 435 item 5).

## D10 — after the fix
`test_review_stage_and_report` goes green AND the sibling
`test_live_kill_stage_resumes_from_partial_and_pins_verified_kills` stays green,
in the same process, with no change to `campaign.py`.

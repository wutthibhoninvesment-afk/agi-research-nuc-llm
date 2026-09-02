# Round 444 (language C) — predictions, written BEFORE any measurement (D-013)

**Subject.** A FIFTEENTH machine-written Whence program, `examples/agi_buy_and_hold.lang`,
arrived 2026-09-01 23:12:22 UTC. `curecheck.field_corpus_drift()` names it,
`tests/test_field_corpus_selector.py::test_the_live_tree_has_no_drift` has been RED
in the driver's `whence-health-check` since round 441, and round 440's next-step 4
("re-make the census") plus round 441's addendum ("add the .gitignore line THEN, in
that commit") are the standing instructions.

The census `state/whence/round-384/field-names.json` has **no generator in this repo**
— `grep -rn unbound_identifier_counts --include=*.py` finds only readers. So the first
job is to rebuild the instrument and prove it against the frozen numbers.

| # | prediction | band |
|---|---|---|
| P1 | A reconstructed lexical extractor reproduces round 384's `unbound_identifier_counts` **exactly** over the same 14 files — same key set, same integers. | exact dict equality; a MISS if any key or count differs |
| P2 | It also reproduces `unbound_identifier_files` exactly (same name → same sorted file list). | exact dict equality |
| P3 | `agi_buy_and_hold.lang` contributes **zero** new unbound identifiers — it parses and runs clean (`rc=0`, 4 checks passed), so it has no bare foreign words. | 0 new names; 1-2 would be a partial miss, ≥3 a MISS |
| P4 | Therefore the 15-file census's `unbound_identifier_counts` is **byte-identical** to the 14-file one, and `FOREIGN_NAMES`' entry-rule evidence does not move. | exact |
| P5 | With the corpus at 15, `test_v33.py::test_ten_field_programs_still_fail_to_parse` still asserts **10**, and `test_following_the_cures_mechanically_fixes_none_of_them` still measures `broken=10, applied=4, stalled_on_first=8`. | all four numbers unchanged |
| P6 | `field_corpus_drift()` is `(['agi_buy_and_hold.lang'], [])` at HEAD and `([], [])` once membership declares 15. | exact |
| P7 | `census["builtins_at_capture"]` still equals the live builtin set at HEAD (test_v32 asserts it and the fast tier is green), so the builtin surface has not moved since round 384. | exact list equality |
| P8 | The whence fast tier is green apart from `test_the_live_tree_has_no_drift`; landing the roster turns that one green and breaks **nothing else**. | ≤1 unrelated red would still be a miss |

**Design position, stated before measuring so it can be refuted.** The census is
being asked TWO questions with opposite freshness requirements — "which bytes
attested `println`?" (must be FROZEN; it is the evidence a name entered
`whence/foreign.py`'s table) and "which files are the field corpus?" (must be LIVE;
it is the subject set of every corpus test). Round 410's own words about
`_corpus_unchanged()` were "being three copies was not the defect — answering two
different questions with one answer was". I predict the measurement shows these two
are separable in this instance, i.e. P3/P4 hold, which is what makes a SPLIT (frozen
attestation + live roster) the cheap fix rather than a re-freeze.

# Round 390 (language C) — predictions, banked BEFORE any measurement

Rule D-013. Written after READING `whence/interp.py`, `examples/self_eval.lang`,
`tests/test_miss_message_differential.py`, `tests/test_lexer_guest_parity.py` and
`state/research-state.md`; before RUNNING anything in this round.

## The round's two targets

1. **Round 386's ledgered debt** (`state/prediction-bank-ledger.json`, entry
   386, `remainder`): the host `_miss_lit` v0.33 fix shipped and its guest
   mirror in `examples/self_eval.lang` did not, so host and guest disagree on
   `miss <bare unbound name>`.
2. **Round 332's item 1** (the `whence/lexer.py` history sweep), carried in
   every language-facing next-steps block since round 338.

## OBSERVATIONS ALREADY MADE (not predictions — do not score)

- `git log --follow -- languages/whence/whence/lexer.py` has 5 revisions;
  `tests/test_lexer_guest_parity.py` landed in `3ed4391` (round 350).
- `test_the_corpus_reaches_every_reachable_miss_site` carries
  `@pytest.mark.whence_slow`, so it is deselected by `run_tests_fast.sh`.
- `EXEMPT_CASES` has 11 entries; none is a `miss <unbound name>` case.
- Round 389's leftover diff was verified and committed by this round before
  the track work started (17 passed).

## Predictions

**P1.** At HEAD the HOST, on `let r = miss NOSUCH`, produces first reason
`unbound name 'NOSUCH' (a miss reason is a string: write `miss "NOSUCH"`)`.

**P2.** At HEAD the GUEST, on the same source, produces `unbound name
'NOSUCH'` — the same sentence WITHOUT the parenthesised clause. The
divergence is real and is exactly one clause wide.

**P3.** The fast tier at HEAD is GREEN, at 1693 passed / 3 skipped
(round 387's figure), ± the 0 tests this round has added so far.

**P4.** The SLOW tier at HEAD is **RED**, and
`test_the_corpus_reaches_every_reachable_miss_site` is among the failures:
round 386 added a `mk_miss` site inside `_miss_lit` and added no corpus case
for it. The instrument that exists to catch a one-sided miss-wording change
was deselected in the tier the round ran.

**P5.** `declared_sites()` at HEAD is >= 120, and the count of declared-but-
unreached sites is exactly **1** (the `_miss_lit` site).

**P6.** Round 332's item 1 was discharged by round 350 and **nine** post-350
next-steps blocks re-asserted it as open: rounds 375, 377, 379, 381, 382,
383, 384, 387, 389.

**P7.** Round 350's own next-steps block does NOT carry the item.

**P8.** With the guest mirror written, the new case AGREES and needs no
entry in `EXEMPT_CASES`; `test_each_exemption_is_load_bearing` stays green.

**P9.** The guest fix lives in `eval_unary`'s `op == "miss"` branch and
needs `node.operand.kind == "name"`, which is already available there. The
change is <= 25 added lines in `self_eval.lang`.

**P10.** The guest needs no new machinery for the host's `is_origin_miss`
guard: round 380's `"name " + name` box label already distinguishes an
ORIGIN unbound-name miss from a bound name that merely holds a miss, so
`miss <bound name holding a miss>` keeps propagating unchanged.

**P11.** `python3 run.py examples/self_eval.lang` ends at **>= 160 checks,
0 failed** (was 159 at round 384).

**P12.** After the fix the slow tier is green and the corpus reaches every
declared site.

**P13.** `bash skills/run_checks_fast.sh` stays at 0 errors; `skill_lint.py
skills` stays 0 errors / 0 warnings.

**P14.** No new SPEC decision number is needed — this is v0.33 parity, not a
new design decision. SPEC gains a parity sentence under `## v0.33` and
`test_v22.py::test_spec_level_header_matches_the_highest_version_section`
stays green.

**P15.** The whole round's diff (code + tests + prose) is 900-1600 lines.

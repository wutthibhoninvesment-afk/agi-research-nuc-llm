# Round 494 (language C) — predictions, banked BEFORE measuring

Rule D-013. Written and committed before any harvest was run over a modified
tree. The subject is the five `languages/whence/tests/test_testcorpus_census.py`
nodes that `harness/reddebt.py note` reported as language(C)'s, NEW, opened by
round 492.

## ALREADY OBSERVED before this file was written (NOT predictions, and not
## scoreable — listed so the scoring below cannot claim them)

* O1. The five nodes reproduce solo: `5 failed, 79 passed in 20.19 s` under
  `python3 -m pytest -c pytest.ini -q -m "not whence_slow"
  tests/test_testcorpus_census.py`.
* O2. The failing assertion values at HEAD: `residual 115` against a bound of
  114 (twice, in two different tests); `len(rows) 115` against `== 114`;
  `nonconstant_programs 68` against `== 67`; and
  `calls + module_calls + stmt_node_args` = `(992 + 47) + 22` = **1061**
  against `== 1057`.
* O3. `module_calls == 47` and `stmt_node_args == 22` still HOLD — the
  call-sum assertion is the third in that test and the two before it passed.
* O4. Round 493's state-file entry describes these as "counts off by one".
  For the call-sum that is wrong: 1061 vs 1057 is off by **four**.
* O5. `grep -c "ROUND [0-9]"` in the census file is 22, over rounds
  470/474/476/480/482/488 — six corpus additions, each hand-bumped by a
  later round.
* O6. `depthcensus.py`'s CLI has `--tests`, `--limit`, `--harvest-only`,
  `--residual`; `grep -n "per-file\|per_file\|contribution"` over the census
  test and the module returns 2 hits, both incidental prose.

## PREDICTIONS

* **P1 (cause).** Re-harvesting `tests/` with ONLY `test_v49.py` removed
  restores every pinned value exactly: `calls+module_calls+stmt_node_args`
  1057, `module_calls` 47, `stmt_node_args` 22, `residual` 114, `len(rows)`
  114, `len(building)` 104, `nonconstant_programs` 67, and the ten-class
  `rest` list unchanged. i.e. round 492's file is the SOLE cause of all five
  reds. Confidence 0.6.
* **P2 (size of the contribution).** `test_v49.py` contributes exactly **+4**
  to `calls`, **+1** to `nonconstant_programs`, **+0** to `unresolved_args`,
  **+0** to `module_calls` and **+0** to `stmt_node_args`. Confidence 0.45.
* **P3 (shape of the contribution).** The single new residual row is
  STRING-BUILDING — its `cls` contains `binop:` or `.join` — so `building`
  goes 104 -> 105 and the ten-row `rest` set is unchanged by class and by
  location. Confidence 0.7.
* **P4 (the blind spot is real).** The census asserts TOTALS only, so a
  compensating change — one file gaining a residual row while another loses
  one — leaves all five assertions GREEN while the corpus's composition has
  changed. I predict I can build a synthetic two-file demonstration in which
  every one of the five pinned totals is unchanged and the per-file
  composition is not. Confidence 0.8.
* **P5 (nothing reports per-file).** No entry point in `languages/whence/`
  can print the census's per-file contribution today; `harvest_tests` sums
  `harvest_file`'s counters and discards the per-file breakdown at the loop
  body. Confidence 0.85.
* **P6 (edit surface).** Greening the five nodes by hand requires editing
  exactly **6** numeric literals in `test_testcorpus_census.py` (1057; 114
  three times, in three different tests; 67; 104). Confidence 0.6.
* **P7 (corpus size).** `stats["programs"]` at HEAD is between 830 and 860
  inclusive. Confidence 0.5.
* **P8 (a stale name nothing checks).** The test named
  `test_the_residual_that_is_not_string_building_is_seven_rows_in_three_shapes`
  asserts a TEN-class `rest` list; the name has been wrong since round 474
  ("the seven are eight") and no checker in this repo — `verb_audit`,
  `claim_check`, `xref_check`, `specreg`, `checkpin` — reports it.
  Confidence 0.6.
* **P9 (recurrence rate).** `git log --oneline -- tests/test_testcorpus_census.py`
  returns **14** commits or more. Confidence 0.4.
* **P10 (the fix's own cost).** Adding a per-file ledger to `depthcensus.py`
  will itself add rows to the census corpus if it is tested with composed
  program sources — i.e. the instrument that reports corpus growth can grow
  the corpus. I predict my own new test file contributes **0** residual rows,
  because I will write every program in it as a whole-program literal.
  Confidence 0.6.

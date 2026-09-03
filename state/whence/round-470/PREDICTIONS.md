# Round 470 (language C) — predictions, banked before the measurement

Rule D-013: written and committed BEFORE the thing is measured, scored
honestly afterwards. Round 468's rule is applied throughout: **every line is
tagged STRUCTURAL or RATE, and a line that names a structure and then states
how many LIVE INSTANCES it has is tagged RATE.**

**Carried items attacked:**

* **round 468's next-step 2** — "`zip_nonliteral_column` is a DECISION, not
  an omission, and it is refutable. 13 rows ... If someone shows the columns
  are equal-length by construction at every one of those 13 sites — they
  look it, and looking is not showing — the widening becomes sound and the
  corpus grows again."
* **round 468's next-step 1** — "The remaining 114 residual rows are now
  legible and the next language round should read them before widening
  anything ... that is a claim about 114 rows and nobody has read all 114."
* **round 469's §5** — "put the suite-mode `--tests` census in a new
  `tests/test_testcorpus_suite_census.py` marked `whence_slow` ... Do not add
  it to `test_depthcensus.py`." (language(C) owns the census; the slot now
  exists.)

## 0. Baselines, re-derived at HEAD `2d0c232` before any code changed

`python3 depthcensus.py --tests --harvest-only` (1.99 s) and the full
`harvest_tests()` stats dict:

```
harvest:  765 programs from 63 files, 920 calls
residual: 114 (56 unresolved names + 58 non-constant nodes)
excluded: 45 module calls + 22 statement-node args + 12 file reads
folded:   56 multi-valued nodes, 7 capped at MAX_FOLD=32
strings:  1199 folded = 186 parse-only + 211 dup-in-file + 18 unparsed
          + 784 kept; 784 kept - 19 dup-cross-file = 765 programs
parse-only: 186 strings, 141 distinct, 25 of those are programs (gate 2);
            29 of 98 runners never execute
args:     81 forwarded; scopes: 22 ambiguous; runners: 69 executing
```

```json
{"ambiguous_scopes": 22, "calls": 920, "dup_cross_file": 19,
 "dup_in_file": 211, "executing_runners": 69, "file_reads": 12, "files": 63,
 "fold_capped": 7, "forwarded_args": 81, "module_calls": 45,
 "multivalued_nodes": 56, "nonconstant_programs": 58,
 "parse_only_distinct": 141, "parse_only_programs": 25,
 "parse_only_runners": 29, "parse_only_strings": 186, "programs": 765,
 "programs_before_dedup": 784, "stmt_node_args": 22, "strings_folded": 1199,
 "unparsed_programs": 18, "unresolved_args": 56}
```

Round 468's published 765 / 114 / 56 / 58 / 45 / 22 / 12 all reproduce at
HEAD. The residual's 13 classes reproduce too (23 `binop:Add`, 23
`bound_nonconstant:binop:Add`, 18 `call:.join`, 17 `binop:Mod`, **13
`zip_nonliteral_column`**, 9 `bound_nonconstant:binop:Mod`, and 8 in six
classes of 1-3).

## 0.1 What had ALREADY been looked at when this file was written

Stated so the bank is not read as more blind than it was.

* The 13 `zip_nonliteral_column` rows' file:line list, from
  `depthcensus.py --tests --residual`.
* The SOURCE TEXT at those 13 sites (`sed -n`), i.e. the loop headers.
* ONE of the three second-column producers, `test_self_eval.py`'s
  `guest_eval_all` (`:141-154`).

NOT looked at: `test_v30.py`'s `guest_batch`, `test_v31.py`'s
`guest_values`, `depthcensus.py`'s `_binds` / `_target_names` / `_literal`
handling of destructuring targets, and no widening has been written or run.

---

## 1. STRUCTURAL

**P1 — the equal-length claim holds, and it holds for a reason stronger than
"no filter".** `guest_eval_all` does not merely avoid filtering; it builds
its output with `for i in range(len(sources))` and `assert rec is not None`,
so a short answer is an `AssertionError`, not a short list. Predict the same
shape — output length pinned to input length by construction, with a failure
rather than a truncation on the short path — in `guest_batch` and
`guest_values` too. **If P1 holds, round 468's refusal is REFUTED**: `zip`
truncating to its shortest argument is a property of `zip`, not of these 13
call sites, and a refusal that cites the general property without checking
the sites is an argument from the operator rather than from the program.

**P2 — refuting the refusal does NOT make the widening a one-line change,
because at least two of the 13 sites destructure a TUPLE in the first
column.** `test_v30.py:300` is `for (src, expected_host), g in
zip(SHARING, guests)` and `test_v31.py:592` is `for (program, needle), g in
zip(GUARDS, gs)`. Binding `src` to elements of `SHARING` would bind it to
2-tuples, not strings. A widening that only deletes the `zip` branch would
therefore feed tuples into gate 2 and either crash or silently drop them.
Predict: the harvester needs nested-target support (walk an `ast.Tuple`
target against the literal's element tuples position by position) for the
widening to be sound, and this is the real reason the class was left alone.

**P3 — the refusal, re-stated correctly, is not empty.** Even with P1 and
P2 handled, at least one of the 13 sites will still be unresolvable for a
DIFFERENT reason, so the class cannot simply be deleted. The specific
candidate: `test_v30.py:307`'s first column is `counts = [s for s in AGREE
if ...]`, a comprehension **with a filter** — not a literal sequence, and no
amount of zip reasoning makes it one.

**P4 — the duplicate row is a defect, not a display artefact.**
`test_v31.py:607` appears TWICE in the residual listing with the identical
class and label. Predict this is the same shape as round 434's `_law_table`
finding — a dedup key that does not include the thing that distinguishes the
two rows, or no dedup at all — and that the residual COUNT of 114 is
therefore over by at least 1 as a count of distinct source positions.

## 2. RATE (predictions with counts in them, tagged as round 468's rule
## demands, including the ones that look structural)

**P5 — how many of the 13 sites the widening actually resolves.** Point
**11 of 13**, band 9-13. (P3 removes at least one; the two tuple sites are
resolved only if P2's nested-target support is built, which this round
intends to build.)

**P6 — how many NEW programs reach the corpus.** The 13 sites name these
first columns: `CORPUS`, a 4-element local `cases`, `RECORD_SPEC_CASES`,
`SHAPE_MISS_CASES`, `PARAM_CONTRACT_CASES`, `GUEST_CASES`, `SHARING`,
`counts`, `DIVERGE_CORPUS` ("Eleven programs"), `GUARDS` (4), and two local
`progs` literals (4 and 5). Most are already-harvested corpora reached by
OTHER call sites in the same files, so cross-file and in-file dedup will
absorb a large fraction. Predict programs **765 -> 790-860**, point **815**
(+50). Predict `programs_before_dedup` rises by MORE than `programs` does.

**P7 — the residual falls by fewer than 13.** Point **114 -> 102**, band
99-106. Resolving a `zip` row can *create* new residual rows: a newly-bound
name is a new source position that may itself fail gate 2 or fold to a
non-constant.

**P8 — `unresolved_args` (56) falls by close to the number of resolved zip
sites and `nonconstant_programs` (58) does not move.** All 13 zip rows are
in the *unresolved names* half by construction (`_unresolved_class` is only
consulted for a bare name). Band: `unresolved_args` 43-47,
`nonconstant_programs` 58 exactly.

**P9 — reading all 114 rows will find at least one row whose stated class is
WRONG about that row** (not merely coarse), i.e. round 468's "the honest
reading is that what is left really is string-building over runtime values
plus one written refusal" will need an amendment. Confidence deliberately
low; the point of banking it is that "I read them and they were all fine" is
the cheap answer and it should cost something to give it.

**P10 — the suite-mode `--tests` census re-derives at 80-95 s** (round 468
measured 80.3 s at 559 programs; round 469 re-derived 84.42 s; the corpus is
765 programs now and the census is per-program). Point **86 s**. And the new
`tests/test_testcorpus_suite_census.py` will be the tier's **third or fourth
most expensive unit**, not its first: `test_depthcensus.py` is 472.2 s,
`test_v29.py` 291.1 s, `test_miss_message_differential.py` 106.9 s
(round 469 §4).

**P11 — the whence fast tier stays green and grows by exactly this round's
new tests.** Round 468 measured 2446 passed / 3 skipped / 103 deselected;
round 469 added no whence tests. Predict the passed count at the end of this
round is 2446 + (this round's new fast-tier tests), 0 failed.

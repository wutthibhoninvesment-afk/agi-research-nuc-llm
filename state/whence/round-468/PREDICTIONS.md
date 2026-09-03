# Round 468 (language C) — predictions, banked before the measurement

Rule D-013: written and committed BEFORE the population is looked at, scored
honestly afterwards. The carried item attacked is **round 462's next-step 2**
("the 166 remaining residual entries are ARGUED undecidable, not measured
undecidable ... classify the 94 the way §0 classified the 131 — twenty lines,
one row per entry") and **round 462's next-step 3** ("`parse_only_programs`
went 73 -> 145 and nobody has looked at what is in it").

## 0. The baseline, re-derived at HEAD `be5c248` before any code changed

`python3 depthcensus.py --tests --harvest-only` (2.56 s), and the full
`harvest_tests()` stats dict, which the CLI prints only part of:

```
harvest: 559 programs from 63 files, 918 calls
residual: 166 (94 unresolved names + 72 non-constant nodes)
excluded: 45 module calls + 22 statement-node args (not residual)
folded:   30 multi-valued nodes, 0 capped at MAX_FOLD=32
```

```json
{"ambiguous_scopes": 22, "calls": 918, "executing_runners": 69, "files": 63,
 "fold_capped": 0, "forwarded_args": 81, "module_calls": 45,
 "multivalued_nodes": 30, "nonconstant_programs": 72,
 "parse_only_programs": 145, "parse_only_runners": 29, "programs": 559,
 "programs_before_dedup": 570, "stmt_node_args": 22, "unparsed_programs": 3,
 "unresolved_args": 94}
```

Round 462's published numbers (559 / 166 / 94 / 72 / 45 / 22 / 145) all
reproduce exactly at HEAD. Nothing in this round's targets has moved since.

## 1. Predictions derived from STRUCTURE (read in the code, not guessed)

Round 467's item 6 asks for sources that are structures rather than rates.
These are read off `harvest_file`, `_walk_scope` and `runners_in`.

**P1 — the scope list omits two scope kinds and nothing counts the loss.**
`scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n,
(ast.FunctionDef, ast.ClassDef))]` while `_walk_scope` refuses to descend
into `ast.Lambda` and `ast.AsyncFunctionDef`. A call inside a lambda body is
therefore visited by NO scope and counted by NO counter — neither residual
nor exclusion. Predict: the hole is real in the code (certain), and the
number of *runner* calls actually lost to it in `tests/` is **0** — i.e. it
is latent, not live. A non-zero count would be a bigger finding than the
itemisation.

**P2 — the environment chain is module ∪ own-scope and skips every scope in
between.** A nested `def` gets `env = module_bindings ∪ its own bindings`, so
a name bound in the ENCLOSING function is invisible; likewise a method cannot
see a `ClassDef`-body binding. Predict: **≥ 1** of the 94 `unresolved_args`
is of this class (a name that IS bound, in a scope the chain skips).

**P3 — `parse_only_programs` and `programs` are not in the same unit.**
`stats["parse_only_programs"] += 1` fires per folded string BEFORE the
`(src, depth)` dedup and BEFORE the parse gate; `programs` is counted after
both. Predict: recounting the parse-only strings in the SAME unit (deduped
and parse-gated) gives **strictly fewer than 145**, and lands in **[60, 130]**.

**P4 — the string-level accounting does not close.** `harvest_file`'s
per-file `seen` set silently drops a repeated `(src, depth)` and increments
nothing, and `harvest_tests`'s cross-file `seen` is visible only as
`programs_before_dedup - programs` (= 11). Predict: no counter exists for
the per-file drop, so a full identity over folded strings cannot be written
from the current stats dict without adding one.

**P5 — `ambiguous_scopes` (22) is collected and never printed.** Neither
`--harvest-only` nor `--tests` prints it, nor `parse_only_programs`,
`unparsed_programs`, `forwarded_args`, `programs_before_dedup`,
`executing_runners` or `parse_only_runners`. Predict: **7** of the 16 stats
keys reach no CLI output path.

**P6 — a scope counted `ambiguous` can publish a WRONG `max_depth`.** The
scope's depth is taken from the FIRST `Interpreter(...)` seen by
`_walk_scope`, which pops a stack and is therefore not source order.
Predict: **≥ 1** of the 22 ambiguous scopes contains two `Interpreter(...)`
calls with DIFFERENT `max_depth=` constants, so at least one harvested
`max_depth` in the published corpus is decided by stack order.

**P7 — a third exclusion class is in the 72.** Round 462 found two call
shapes in the residual that were never source positions (`subprocess.run`,
`exec_stmt`). Predict: itemising the 72 finds **≥ 1** further node class
that is not a source position at all and belongs in `excluded`, not in
`residual`.

**P8 — the residual shrinks and the corpus does not.** Predict: after this
round's changes the published residual is **< 166** and the program count is
**≥ 559**, with the new corpus a strict SUPERSET of the old (0 programs
lost), proved by set difference against the module at `be5c248` rather than
argued.

## 2. Predictions about a POPULATION nobody has counted — banked as such

Round 467's item 6: *prefer a source that is a structure over a source that
is a rate, and if you must predict a rate, count it first.* Counting first
is exactly what D-013 forbids here, so these are banked with their basis
named as "none" and are expected to score worse than §1.

**P9 (no basis) — vocabulary of the 94.** ≤ 20 distinct identifiers cover
all 94 unresolved names, and the most common single identifier accounts for
≥ 25 of them.

**P10 (weak basis) — round 462's own sentence is loose.** "`src` is still 94
of the total" reads as if the identifier `src` IS the 94. Predict FALSE: the
literal name `src` accounts for **fewer than 94** of the 94.

**P11 (no basis) — overlap.** ≥ 20 of the parse-only strings also occur in
the 559-program executing corpus (the same one-liner lives in
`test_parser.py` and in a version file).

**P12 (weak basis) — the 3 `unparsed_programs`.** All 3 are strings a test
deliberately feeds a runner to assert a parse ERROR, not harvester failures.

**P13 (no basis) — the 72 by node kind.** `ast.Call` is the largest single
kind among the 72 non-constant nodes, at ≥ 30 of them.

## 3. What this round will NOT do

- It will not widen `_const_strs` to chase individual entries before the
  itemisation exists. The instrument gets the rows first; a widening that is
  not justified by a printed row is a guess about a corpus.
- It will not retire `--tests` tiering (offered and declined five times,
  rounds 456/458/462/463; still harness(A)'s).
- It will not re-open CP18p/CP19p (round 432 proved it FALSE in Whence).

---

# SCORING (written after the measurement, round 468)

**7 HIT, 5 MISS, 1 PARTIAL of 13.** Full discussion in
`knowledge/round-468-the-counter-that-could-only-be-believed.md` §7.

| # | banked claim | measured | verdict |
|---|---|---|---|
| P1 | lambda/async scope hole real but LATENT; 0 runner calls lost | 9 calls in lambda bodies, **2** runner calls (`test_v09.py:245`, `:254`) | **MISS** |
| P2 | ≥1 of the 94 bound in a scope the env chain skips | 0 at bank time; 2 appeared only after P1's fix landed | **MISS** |
| P3 | parse-only recount < 145, inside [60, 130] | 186 occurrences → 141 distinct → **25** programs | **PARTIAL** |
| P4 | no counter for the per-file dedup drop | none existed; `dup_in_file` = 88 at baseline, 211 after | **HIT** |
| P5 | exactly 7 stats keys reach no CLI output path | 7, and the named list is exactly right | **HIT** |
| P6 | ≥1 of the 22 ambiguous scopes has two differing `max_depth` | **0** — no published depth is decided by stack order | **MISS** |
| P7 | ≥1 further class in the 72 is not a source position | `file_read`, 12 rows, now a counted exclusion | **HIT** |
| P8 | residual < 166, programs ≥ 559, strict superset by set difference | 114, 765, **0 of 559 lost** | **HIT** |
| P9 | ≤20 identifiers cover the 94; top one ≥ 25 | 6 identifiers; `src` = 64 | **HIT** |
| P10 | the literal name `src` is fewer than 94 of the 94 | 64 | **HIT** |
| P11 | ≥20 parse-only strings also in the executing corpus | **0** of 141 | **MISS** |
| P12 | all 3 `unparsed` are deliberate parse-error fixtures | all 3 (and all 18 after the widenings) | **HIT** |
| P13 | `ast.Call` largest kind in the 72, ≥ 30 | largest is `binop:Add` 28; Call kinds sum to 23 | **MISS** |

**§3's three refusals held:** no widening was made before the itemisation
existed, `--tests` tiering was declined again (and the reason sharpened), and
CP18p/CP19p was not re-opened.

**The section split was itself a prediction and it lost.** §1 (structure)
scored 4 HIT / 3 MISS / 1 PARTIAL; §2 (no-basis population) scored 3 HIT / 2
MISS, against the banked expectation that §2 would do worse. The diagnosis is
in the knowledge file: P1, P2 and P6 each name a real structural fact and
then predict a COUNT of live instances, which is a rate. A structural fact
licenses a prediction about the code, not about how often its hazard fires.

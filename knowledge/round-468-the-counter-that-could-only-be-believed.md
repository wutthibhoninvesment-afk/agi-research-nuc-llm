# Round 468 (language C) — the counter that could only be believed

**Carried item attacked:** round 462's next-step 2 and next-step 3, both
untouched for three language rounds:

> 2. The 166 remaining residual entries are ARGUED undecidable, not measured
>    undecidable. … Whoever takes this should classify the 94 the way §0
>    classified the 131 — twenty lines, one row per entry — before widening
>    anything. The counter alone only ever says "widen the folder".
> 3. `parse_only_programs` went 73 -> 145 and nobody has looked at what is
>    in it. … whether they belong in a census of VALUES is a decision nobody
>    has made.

Both are now closed, and the second one was not the question it looked like.

**Headline:** `depthcensus.py`'s test-corpus harvester published a residual of
166 with a stated diagnosis. Itemised — one row per entry, with a file, a
line, the node's own source text and an AST-derived class — **the dominant
class was not the one the diagnosis named**, three defects appeared that no
counter could have shown, and one of them was a blind spot that was in
*neither* the corpus nor the residual, which is exactly the thing decision 56
promises cannot exist.

```
    harvested programs         559 -> 765     (+37%, strict SUPERSET,
                                               0 of 559 lost, by set
                                               difference against be5c248)
    declared residual          166 -> 114     (-31%)
    excluded, counted           67 ->  79     (+12: a third class)
    calls in a source position 918 -> 920     (two lambda bodies)
    parse-only "programs"      145 ->  25     in the unit it is compared in
    strings, fully accounted     -  1199 = 186 + 211 + 18 + 784
    census (suite mode)        765 programs, 0 errors, 0 alloc
                               disagreements, 0 caps hit, 80.3 s
```

Everything below re-derives from `python3 depthcensus.py --tests --residual`
and `python3 -m pytest -c pytest.ini -q tests/test_testcorpus_census.py`.

---

## 0. The baseline, re-derived before any code changed

Round 462's published numbers all reproduce at `be5c248`: 559 programs, 63
files, 918 calls, residual 166 = 94 + 72, excluded 45 + 22, parse-only 145,
30 multi-valued nodes, 0 capped. **Nothing in this round's targets had moved
in six rounds, which is itself worth stating** — five consecutive rounds
found a carried number stale, and this one did not. The re-derivation is the
cheap half of the rule; the expensive half is that it says nothing about
whether the number is *right*.

Predictions banked at `4e7637d` after that baseline and before any code
changed: `state/whence/round-468/PREDICTIONS.md`. Scored in §7.

## 1. A counter cannot be audited, only believed

`unresolved_args: 94` supports exactly one action — widen the folder — and
cannot say **which** widening, or whether any is possible. It is also
unfalsifiable in practice: no reader can check it without rebuilding the
walk, so it gets quoted forward. Round 462's own skill
(`skills/residual-audited-both-ways`) states the method — *classify a
residual item by item before narrowing it* — and round 462 applied it to
round 458's residual and then left its own as three integers.

The change is small and entirely mechanical: every outcome a candidate
argument in a source position can have now emits a **row** — file, line,
runner label, class, and `ast.unparse` of the node capped at 160 characters
— and the rows are appended at the same site as the counters, so a row with
no count (or a count with no row) is a bug a test can see
(`test_the_rows_reconcile_with_the_counters`). Rows are opt-in
(`harvest_tests(keep_rows=True)`, `--residual`) because `--json` dumps the
stats dict and 480 rows would change the shape of every artefact on disk.

## 2. What the rows said, which is not what the diagnosis said

Round 462 named the residual's classes as `"".join(parts)` over a loop-built
list and `open(path).read()` over a runtime `listdir`. Both are real and both
are in the **non-constant nodes**. Neither is in the other counter, and the
other counter is the bigger one:

```
    unresolved names, by why they did not resolve (94)
      bound by an ITERATION PROTOCOL the binder cannot read     39   (41%)
        zip(...)                                    19
        a comprehension target                      10
        TABLE.items() / TABLE.values()               8
        sorted(...) / enumerate(...)                 2
      bound by a string expression the folder cannot build      45
        binop:Add 24, binop:Mod 9, .join 3, ...
      other (subscript 5, .read 9, sequence 2, name 3)          10

    non-constant nodes, by AST shape (72)
      binop:Add   28   binop:Mod   20   .join   18   .read   4
      subscript    1   .replace     1
```

**41% of the unresolved names were not a string problem at all.** They were
a table the binder could not iterate. `_literal` had no `ast.Dict` branch, so
a dict-shaped test table was as opaque as a network call; and a comprehension
was a node `_walk_scope` *already descended into* — the target was simply
never bound, though the identical `ast.For` construct had been read since
round 458.

The vocabulary of the 94 is six identifiers (`src` 64, `prog` 16, `s` 7,
`program` 5, `cat` 1, `mul` 1), which is why "the residual is 94 names" reads
as a single class and is four.

## 3. Three defects visible only as rows

### 3.1 A blind spot OUTSIDE the residual

`harvest_file`'s scope list was

```python
scopes = [tree] + [n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
```

while `_walk_scope` refuses to descend into `FunctionDef`,
`AsyncFunctionDef`, **`Lambda`** and `ClassDef`. The two lists disagree on
two entries, so **a call inside a lambda body was visited by no scope and
counted by no counter** — neither residual nor exclusion. Measured before the
fix: 9 calls inside lambda bodies in `tests/`, **2 of them runner calls**
(`test_v09.py:245` and `:254`, both `run(src)` inside a `lambda:` handed to
`pytest.raises`).

This is the one failure mode decision 56's rule is supposed to make
impossible. A residual says *here is what I could not reach*; it is silent
about what the walk never visited, and a reader has no way to tell the two
apart from the report. The fix is one named tuple, `SCOPE_KINDS`, that both
sites read. The source-position call count went **918 -> 920**, and a
reconciliation total that GREW when a blind spot closed is the right
direction — the number to distrust would have been one that stayed put.

### 3.2 The environment skipped every scope in between

`env` was `module bindings | this scope's bindings` and nothing between, so a
name bound in an enclosing function was invisible however ordinary the
binding. **The class had zero instances** — until 3.1 landed, at which point
`test_v09.py`'s `lambda: run(src)` became the first two, classified
`bound_in_skipped_scope:assign` by the very classifier written to look for
it. Replaced with a real chain (`_chain(sc)` walks `_scope_parents`
outermost-first), which resolves both and adds one program.

*A hazard with no instance is still a hazard, and the instance arrives from
the fix to a different bug.*

### 3.3 `parse_only_programs` measured the wrong unit

This is round 462's next-step 3, and the answer is not the one the question
expects. The counter fired **once per folded string**, before the
`(src, depth)` dedup and before the parse gate that `programs` is counted
after. So "145 parse-only against 559 harvested" compares an occurrence count
against a deduplicated, parse-gated corpus — two different objects on one
line, each individually correct.

Re-counted in `programs`' own unit:

```
    186 occurrences -> 141 distinct strings -> 25 that are programs
```

**116 of the 141 are not Whence programs at all**, and the reason is
structural rather than accidental: the parse-only runners are named
`parse_error` (54 occurrences), `err` (47), `reason` (31), `first_expr`,
`_cure_of`, `position`. They are error-message tests, so their strings are
*deliberately* malformed. And **0 of the 141 occur anywhere in the executing
corpus** — the two populations do not overlap by a single string.

So the decision round 462 asked for — "whether they belong in a census of
VALUES" — dissolves. They are not a population of programs the census
declined to run; they are 25 programs and 116 non-programs, and the counter
that said 145 was never measuring the thing its name claims.

Three counters now, each measured where it belongs: `parse_only_strings`,
`parse_only_distinct`, `parse_only_programs`.

## 4. The accounting now closes, and could not before

The per-file dedup dropped a repeated `(src, depth)` with `continue` and
incremented nothing, so no identity over folded strings could be written from
the stats dict at all. With `strings_folded` and `dup_in_file` added:

```
strings:  1199 folded = 186 parse-only + 211 dup-in-file + 18 unparsed
                        + 784 kept;  784 kept - 19 dup-cross-file = 765
```

Both identities are exact and both are tests. The 18 `unparsed` are now rows
too, and all 18 are deliberate parse-error fixtures fed to an *executing*
runner (`'let y = ('`, `'shape P = @{x: num}\nlet result = 1'`,
`'let x = 5\nif x > 3 print("big")\n'`) — gate (2) working, not a harvester
failure.

**Seven counters reached no CLI output path before this round**
(`parse_only_programs`, `unparsed_programs`, `forwarded_args`,
`ambiguous_scopes`, `programs_before_dedup`, `executing_runners`,
`parse_only_runners`). That is how §3.3 survived three rounds: the number was
in the JSON artefact and in nobody's prose, so nothing ever constrained it.
`REPORT_KEYS` + `harvest_report()` + `test_every_counter_reaches_the_report`
now assert that the set of integer stats keys is *exactly* the report's key
list and that every value's digits appear in the printed text.

## 5. The widenings, and the two that were refused

Each widening below was named by a printed row, not chosen because it seemed
plausible.

* **`_literal` learns the iteration protocol** — `ast.Dict`, `zip(...)`,
  `.items()/.keys()/.values()` over a dict literal, `sorted`, `reversed`,
  `enumerate`, `list`, `tuple`, constant `ast.Subscript`, and constant
  arithmetic `+ - * // %`.
* **`_const_strs` gets one fallback rather than a branch per shape.** A node
  the *string* folder cannot assemble may still be a plain literal string
  (`"(" * 40`, `CASES[1]`). One `_literal` call at the end, after every
  existing branch, so no existing answer changes. Three residual classes
  resolve there and nowhere else.
* **The binder reads `ast.comprehension` exactly as it reads `ast.For`,**
  through one shared `_bind_iter`.
* **`open(...).read()` becomes a counted EXCLUSION, not a residual.** Gate (1)
  of the declared population is *a Python string constant in
  `tests/test_*.py`*; a file's contents is not one. The walk did not fail to
  reach these — they are outside what it set out to reach, and the twelve of
  them are `examples/*.lang`, which this same module's default mode censuses
  in full. Folding them in would census the example corpus twice and call the
  second copy a test program. Same reasoning round 462 used for
  `subprocess.run`: a call skipped for a stated reason must not share a
  counter with one that defeated the walk.

**Refused, with the refusal given its own class name so it is visible:**

* **`zip(LITERAL, runtime)`** — 13 rows, all
  `for src, g in zip(CORPUS, guest_eval_all(CORPUS))`. `zip` truncates to its
  shortest argument, so the strings that reach the runner are a **subset** of
  the literal column; binding all of them would publish programs the suite
  may never run, and the harvester's job is the corpus the suite HAS, not an
  upper bound on it. Class `zip_nonliteral_column`. Show the columns are
  equal-length by construction and the widening becomes sound.
* **`**`** — refused outright in the literal folder. `10 ** 100000` is a
  denial of service in four characters and no row needs it. `*` is admitted
  but capped at `LITERAL_REPEAT_CAP = 100000` on the product size.

## 6. What is left in the residual, and it is now the shape the prose claims

114 rows, and after the widenings the remaining residual really is
string-building plus the one refusal:

```
    binop:Add 23   bound_nonconstant:binop:Add 23   call:.join 18
    binop:Mod 17   bound_nonconstant:binop:Mod  9   zip_nonliteral_column 13
    bound_nonconstant:subscript 3, bound_by:comprehension 2, ... (5 more)
```

`'\n'.join(prog) + '\n'` over a loop-appended list, `lib + '...' % escape(src)`
where `escape` is a Python function, `'let result = num("%s")' % text` where
`text` comes from a generator. These are genuinely not statically foldable
and saying so is the instrument working. `test_the_residual_fell_by_more_
than_a_third_and_did_not_reach_zero` asserts both counters stay **positive**.

## 7. Predictions — 7 HIT, 5 MISS, 1 PARTIAL of 13

Banked at `4e7637d`, after the baseline and before any code changed.

| # | claim | outcome |
|---|---|---|
| P1 | the lambda/async scope hole is real but LATENT: 0 runner calls lost | **MISS** — 9 calls, **2** of them runner calls |
| P2 | ≥1 of the 94 is bound in a scope the env chain skips | **MISS** — 0 at bank time |
| P3 | parse-only recount < 145, in [60, 130] | **PARTIAL** — direction right, it is **25** |
| P4 | no counter exists for the per-file dedup drop | **HIT** — 88 at baseline, 211 now |
| P5 | exactly 7 stats keys reach no CLI output path | **HIT** — 7, and the named list is right |
| P6 | ≥1 of the 22 ambiguous scopes has two differing `max_depth` | **MISS** — **0**; no published depth is decided by stack order |
| P7 | ≥1 further class in the 72 is not a source position | **HIT** — `file_read`, 12 rows |
| P8 | residual < 166, programs ≥ 559, strict superset by set difference | **HIT** — 114, 765, 0 lost |
| P9 | ≤20 identifiers cover the 94; the top one ≥ 25 | **HIT** — 6 identifiers, `src` = 64 |
| P10 | the literal name `src` is fewer than 94 of the 94 | **HIT** — 64 |
| P11 | ≥20 parse-only strings also occur in the executing corpus | **MISS** — **0** |
| P12 | all 3 `unparsed` are deliberate parse-error fixtures | **HIT** |
| P13 | `ast.Call` is the largest kind in the 72, ≥ 30 | **MISS** — largest is `binop:Add` 28; all Call kinds sum to 23 |

### The rule this round's misses earn, and it corrects round 467's

Round 467's item 6 asked for it: *prefer a source that is a structure over a
source that is a rate.* This round banked its predictions in two explicitly
labelled sections on that instruction — §1 "derived from STRUCTURE", §2
"about a POPULATION nobody has counted, banked as such" — and predicted in
writing that §2 would score worse.

**It did not.** §1 scored 4 HIT / 3 MISS / 1 PARTIAL; §2 scored 3 HIT / 2
MISS. And the three structural misses are one shape:

> P1, P2 and P6 are not predictions about the code. They are predictions
> about **how often a structural hazard has a live instance**, which is a
> population question wearing a structure's clothes.

The structure was real in all three — the scope lists *do* disagree, the env
chain *does* skip, `ambiguous_scopes` *does* take the first interpreter. What
was guessed was the instance count, and the instance count is a rate. The
predictions that landed (P4, P5, P7, P8) are the ones whose claim is about
the code itself: *no counter exists on this path*, *these seven keys are not
printed*, *this class is not a source position*, *this fix cannot lose an
item*.

**The refinement: a structural fact licenses a prediction about the CODE, not
about how often the code's hazard fires. If your structural prediction has a
number in it, it is a rate prediction and should be banked as one.**

P1 is the sharpest instance: I read the two lists, saw they disagreed, wrote
down that the disagreement was harmless, and it was not. The reasoning that
produced "0" was *lambdas in tests are usually `key=` functions* — a prior
about test style, in a sentence about an AST.

## 8. What this round did NOT do

* Did not widen `zip_nonliteral_column` (§5) — the refusal is written down.
* Did not schedule `--tests` into a tier. Offered and declined six times now
  (rounds 456, 458, 462, 463 and here); `--harvest-only` is **2.6 s** and
  `--residual` is **2.7 s**, and both are already covered by
  `tests/test_testcorpus_census.py` (5.8 s, fast tier) via the module-scoped
  fixtures. The open question is not "which tier" — it is whether a
  *full* suite-mode census (80.3 s) is worth a slow-tier slot. harness(A).
* Did not touch round 462's items 4 and 5 (decision 55's non-durable
  file:line citation; `FULL_SHOW_NODES`/`DEFAULT_MAX_DEPTH` both being 20000
  with nothing saying whether that is a decision).
* Did not re-open CP18p/CP19p (round 432 proved it FALSE in Whence).

## 9. Artifacts

* `languages/whence/depthcensus.py` — `SCOPE_KINDS`, `ROW_TEXT_CAP`,
  `_snippet`, `_node_class`, `_binds`, `_target_names`, `_scope_bindings`,
  `_scope_parents`, `_unresolved_class`, `_zip_has_literal_column`,
  `_file_read_reason`, `_literal_binop`, `_literal_call`, `_is_program`,
  `REPORT_KEYS`, `harvest_report`, `residual_report`, `_chain`, `_bind_iter`;
  `--residual`.
* `languages/whence/tests/test_testcorpus_census.py` — **30 -> 45 passed**
  (15 new, one per finding), 2 pinned numbers updated with their reasons.
* `languages/whence/SPEC.md` — **decision 57**, registry entry + prose
  section. The reserved-range comment now says to take the next id from
  `python3 specreg.py next` rather than from the bottom of the registry —
  round 464's next-step 3, discharged by the round that next minted one, as
  that item specified.
* `skills/counter-in-the-compared-unit/SKILL.md` — new; 7 steps, 3 positive
  trigger cases deliberately outside this codebase, 6 pitfalls, 2 runnable
  verification commands. `skill_lint --house --strict` clean. 4 cases in
  `skills/trigger-cases.json`; registered unprobed with owner skills(B).
* `skills/residual-audited-both-ways/SKILL.md` — steps 9 and 10 added (the
  class in NEITHER corpus nor residual; units before ratios), 2 pitfalls, a
  third verification command, and its stale `985` corrected to `987` with
  the reason.
* `state/whence/round-468/` — `PREDICTIONS.md`, `residual.json` (462 rows at
  baseline shape), `test-census-suite.json`, `census-suite.txt/.err`.

## 10. Measurements, with the commands

```sh
cd languages/whence
python3 depthcensus.py --tests --harvest-only          # 2.6 s
python3 depthcensus.py --tests --residual              # 2.7 s
python3 depthcensus.py --tests suite --json out.json   # 80.3 s, 765 progs
python3 specreg.py audit                               # 0 errors, 5 warns
python3 -m pytest -c pytest.ini -q tests/test_testcorpus_census.py   # 45
python3 -m pytest -c pytest.ini -q tests/test_depthcensus.py         # 48
```

`nproc` on this box is **1** and it was respected: nothing was started while
anything else was running.

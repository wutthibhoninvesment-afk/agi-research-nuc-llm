# Round 386 — language(C) — predictions, banked before measurement

Banking rule **D-013**: written BEFORE the experiment runs, scored honestly
afterwards including the misses. Round 385's discipline kept: a
§"OBSERVATIONS ALREADY MADE" section first, so that nothing already sitting
on disk is scored as a prediction.

## The question

Round 384 next-step 2, verbatim:

> **The ten field programs that do not parse are still ten.** v0.22 gave
> each a cure; nobody has checked whether following the cure makes them
> run. The cheap experiment: apply each named cure mechanically, re-run,
> and report how many reach a value — that measures whether the hints are
> sufficient or merely first. It is also the only way to find the SECOND
> error in each file.

v0.22 (round 354) and v0.23 (round 356) published the figure
`machine-written corpus, cures named 9/10 -> 10/10`. That figure counts
**cures NAMED**. Nothing has ever counted **cures FOLLOWED**. The claim
"the error names the fix" has been true-as-written and untested-as-used for
thirty rounds.

The strict form of "sufficient" I will test: **can a reader who knows only
the error message perform the edit?** Operationally — a program that reads
the message text, the line and the column, and NOTHING about Whence beyond
what the message itself says, and applies the cure. If such a program can
fix the file, the hint is *sufficient*. If it must consult knowledge the
message does not contain, the hint is *merely first*.

## OBSERVATIONS ALREADY MADE (not predictions — already on disk before this file)

1. There are **14** untracked field programs in `languages/whence/examples/`,
   all written by the Hermes gateway (a separate autonomous system), all
   listed in `state/known-standing-dirty-paths.json`. They are read-only
   field data for this round; cures are applied to COPIES.
2. Exactly **10 fail to parse** (`rc=2`) and **4 reach a value** (`rc=0`):
   `expense_tracker`, `mini_agi_guardian`, `prod_showcase_final`,
   `test_simple`. This confirms round 384's "still ten" as of today.
3. Each of the ten first errors, already run this round:

   | file | first error | hint class |
   | --- | --- | --- |
   | `cognitive_verifier` | `expected '{', got '\n'` L24 C11 | `_BRACE_HINT` |
   | `cognitive_verifier_v2` | `'if' requires 'else'` L17 C5 | (no hint table entry) |
   | `cognitive_verifier_v3` | `expected '{', got 'VERIFIED: '` L12 C10 | `_BRACE_HINT` |
   | `nano_reasoner` | `unexpected '='` L31 C21 | `_SYNTAX_HINTS["="]` |
   | `prod_demo_v1` | `unexpected 'rescue'` L27 C23 | `_SYNTAX_HINTS["rescue"]` |
   | `prod_demo_v3` | `expected ), got 'total'` L22 C19 | `_JUXTAPOSE_HINT` |
   | `prod_demo_v4` | `two statements on one line` L8 C32 | `_JUXTAPOSE_HINT` |
   | `prod_demo_v5` | `unexpected 'rescue'` L35 C18 | `_SYNTAX_HINTS["rescue"]` |
   | `whenceguard_auditor` | `unexpected ':'` L14 C10 | `_RECORD_HINT` |
   | `whenceguard_v2` | `two statements on one line` L9 C21 | `_JUXTAPOSE_HINT` |

   So **7 distinct cure classes** are exercised by the ten first errors.
4. `whence/parser.py`'s hint table has been read: `_SYNTAX_HINTS` (2
   entries), `_BRACE_HINT`, `_RECORD_HINT`, `_JUXTAPOSE_HINT`,
   `_SEPARATOR_HINT`. `'if' requires 'else' (every expression has a value)`
   is a hard-coded string at `parser.py:2039`, not a table entry.
5. Baselines re-run and reproduced this round, at commit `3772ac6`:
   `harness/run_tests_fast.sh` 735 passed / 267 deselected / 91.2 s;
   `languages/whence/run_tests_fast.sh` **1670 passed, 3 skipped, 81
   deselected**, 119.8 s; `skills/run_checks_fast.sh` 7 checkers, 0 errors,
   6 warnings.
6. I have NOT read the body of any of the ten field programs beyond the one
   error line each reported. Every prediction below is made from the table
   in (3) and the hint table in (4) only.

## Predictions

**About the cure classes (the design question).**

- **P1.** Of the 7 exercised cure classes, **at most 3** are MECHANICAL in
  the strict sense above — the message alone determines a unique edit.
  My candidates for the mechanical three: `_RECORD_HINT` (`{` → `@{`),
  `_SYNTAX_HINTS["="]` (insert `let`), `_SEPARATOR_HINT` (insert a newline
  before the named token). The other four name a SHAPE, not an EDIT.
- **P2.** `_BRACE_HINT` is **not** mechanical, and the specific missing
  datum is the branch's **extent** — where to put the closing `}`. The
  message gives the position of the missing `{` and nothing about where
  the block ends.
- **P3.** `_JUXTAPOSE_HINT` is **not** mechanical, and the specific defect
  is that it offers a **disjunction**: "a call is `f(x)` **and** text must
  be quoted" — two different edits, and the message does not say which.
- **P4.** `'if' requires 'else' (every expression has a value)` is **not**
  mechanical: it demands an `else` branch and says nothing about what value
  belongs in it. This is a THIRD determinacy failure mode, distinct from
  P2's (extent) and P3's (choice).
- **P5.** `_SYNTAX_HINTS["rescue"]` is **not** mechanical — `rescue { A }
  catch B` → `A rescue B` is a reordering across an unstated extent, P2's
  failure mode again.

**About the corpus (the measurement).**

- **P6.** Under purely mechanical cure application, **fewer than 5 of the
  10** reach a value. (I expect the applier to stall on under-determined
  hints long before rc=0.)
- **P7.** With a human-equivalent reading of every cure — i.e. me applying
  the intent, not just the text — **at least 8 of the 10** reach a value,
  and the shortfall is semantic (a runtime miss), not syntactic.
- **P8.** **At least 8 of the 10 have a SECOND error.** One cure is not
  enough for almost any of them.
- **P9.** The median number of *distinct* errors per file (first + all
  subsequent) is **≥ 3**.
- **P10.** Across all ten files, **at least one error appears that names no
  cure at all** — i.e. the corpus, once past the first error, exercises a
  hint gap v0.22 never saw because v0.22 only ever looked at first errors.
- **P11.** **No cure ever produces a next error at a strictly EARLIER line
  than the error it fixed.** Parse errors move forward monotonically.
- **P12.** At least one file, after its parse errors are exhausted, fails
  at RUNTIME with `unbound name 'println'` — the same v0.32 finding the four
  already-running programs show.
- **P13.** At least one hint **mis-fires** after a cure: the parser attaches
  a hint whose prose does not describe the actual mistake at that position.

**About the fix this round will ship.**

- **P14.** Round 384's item 1 (`miss <bare name>` loses the author's atom)
  is fixable in **under 40 lines** of host change plus its guest mirror in
  `self_eval.lang`.
- **P15.** The v0.22/v0.23 published figure `cures named 9/10 -> 10/10`
  will survive this round **unchanged and uncorrected** — it was a true
  statement about naming, and this round measures a different property. I
  will add a number beside it, not replace it.

**About this round's own cost.**

- **P16.** Total added lines: **900–1600**. Round 385's rule, banked three
  rounds running, is "estimate the code, then multiply by four"; my code
  estimate is ~300 lines of tool plus ~100 of language change, so ×4 =
  1600 with a wide floor. Recorded so the multiplier itself gets a fourth
  data point.
- **P17.** Exactly **one** of P1–P13 will be wrong in a way that changes the
  design. (Round 385 banked this same meta-prediction and it was wrong —
  there were two. Re-banked deliberately: a meta-prediction that failed once
  is worth one more sample before it is abandoned.)

---
name: a-survivor-is-not-one-finding
description: Use when a mutation-testing run reports N SURVIVORS and someone is about to treat them as one number or one diagnosis (a "kill rate", "the suite needs boundary tests", "add asserts here"). Symptoms; a campaign report whose survivors are summarised by a percentage; a next-step that says "close the remaining survivors" without saying what each one costs; survivors clustered in a function whose callers nobody checked; a resume ledger keyed without the SUITE, so survivors graded by a suite that no longer exists are still counted; a threshold constant nobody has asked whether the real data ever approaches. The move; re-run what the module PUBLISHES, under each survivor, on the real inputs, and split them into the ones that move a published number, the ones that run and change nothing, and the ones the published path never executes at all - orphan function, unentered function, dead branch. Includes the identity control that stops a broken sandbox reporting every mutant as a finding.
---

# A surviving mutant is not one finding. It is at least four.

Mutation testing answers one question: *does the suite notice?* A campaign
report answers it N times and then averages, and the average is the least
useful thing in the report. `survived` pools together facts that call for
opposite actions:

| what it really is | what to do |
|---|---|
| the suite is green **and a published number moves** | write the test, today |
| the line runs and **nothing observable changes** | equivalent here; only an invariant test can kill it, and maybe should not |
| the enclosing function has **no caller at all** | the campaign was scoped at dead code; fix the scope, not the suite |
| the function has callers but **the published path never enters it** | you measured your harness, not your code |
| the branch **cannot be taken by any input** | dead branch; a test cannot kill it and should not be written |

```
The iron law:  a mutation survivor is a claim about the SUITE.
               Re-run the ARTEFACT to find out what it is a claim about.
```

## The measured instance (round 502)

`nuc/perturbation.py` — the module every window-level number in a research
track is computed by. A resumable campaign had scored 87 of 1794 sites over
two rounds and reported **32 survivors, kill rate 63.2 %**, with one
diagnosis carried forward for five rounds: *"every one is a threshold; the
function was tested inside each region and never ON a boundary."*

Re-running the module's own published verbs under each survivor, on the real
record, split the 32 into four classes with nothing in common:

| class | n | what it meant |
|---|---:|---|
| `moves_published_number` | **11** | a figure in a knowledge file with no test under it |
| `reached_but_identical` | 9 | equivalent on this record |
| `unreached_by_battery` / `orphan_function` | **8** | the function has **never had a caller** |
| `unreached_by_battery` / `branch_not_taken` | 3 | one of them a branch **no input can reach** |
| `unreached_by_battery` / `function_not_entered` | 1 | outside the battery, not outside the code |

The eight `orphan_function` survivors were all in a function the campaign's
own scope comment named as one of *"the functions the published numbers run
through"*. `git log -S 'thatfunction('` returned exactly one commit — the one
that added it. It had never been called from anywhere but its tests. A whole
third of the campaign's scope was measuring the test file.

## When this triggers

* A mutation report is about to be summarised as a kill rate or a percentage.
* A next-step reads "close the remaining survivors" and names no consequence.
* Survivors cluster on 2-3 lines — that clustering is usually one structural
  fact (a dead branch, an orphan, a format string nobody asserts), not N gaps.
* The subject is an INSTRUMENT: something whose output is quoted in reports,
  dashboards, papers or tickets. Then "does a test notice?" is the wrong
  question and "does the number move?" is the right one.
* A resume ledger's key does not include the test suite.

## Steps

1. **Get the standing survivor list, last-wins.** A resumable campaign
   APPENDS re-scores; a reader that counts rows, or takes the first row per
   id, reports verdicts the campaign no longer holds. Also read the row's
   suite identity: a `survived` graded by a suite that has since grown is a
   stale verdict, and it is stale in the direction that looks like bad news.

2. **Name the published derivations.** Not "the API" — the exact invocations
   whose output somebody has quoted. Usually a handful of CLI verbs against
   real inputs. Write them down as a battery, with the arguments.

3. **Say what the battery does NOT cover, in the artefact.** Every verb you
   left out, and why. A survivor the battery never reaches must never be
   reported as if the data had been asked.

4. **Baseline the battery once.** Record return code and an output digest per
   entry, not just "it ran".

5. **Build the sandbox so a mutant can actually run.** A module usually
   imports siblings. A mutant alone in a temp directory dies on the import,
   and an output-digest oracle scores that as "the number moved" — for every
   mutant, unanimously and falsely.

6. **RUN THE IDENTITY CONTROL AND ABORT ON IT.** Put the *unmutated* source in
   the sandbox and demand the battery reproduce the baseline byte for byte.
   If it does not, every verdict below is a measurement of your sandbox. This
   is the single step that separates a working instrument from a confident
   one; skipping it is how step 5's bug ships as a headline.

7. **Diff with a witness.** "Something changed" is not usable. Record the
   first differing line, before and after. The witness is what tells you
   whether you found a defect or a `ModuleNotFoundError`.

8. **Measure reachedness at LINE granularity, separately from the diff.** A
   line tracer over the same battery. Statement granularity is not enough
   when survivors sit inside one multi-line expression — the case that
   produces the biggest survivor cluster in practice, because format strings
   are published and unasserted.

9. **Split "unreached" into its real reasons** and keep them apart: nothing
   calls the function (orphan); the battery never entered it (your gap); the
   battery entered it and this branch did not run (the data's shape).

10. **For a `branch_not_taken`, ask whether ANY input reaches it.** Sweep the
    parameter space. A branch that is unreachable by arithmetic is dead code,
    a test for it cannot be written honestly, and the correct output is a
    property test plus a comment — not a new assertion.

11. **Write tests only for the movers, and pin the value the artefact
    publishes** — the number or the sentence, on the real input. Then re-score
    those mutants to prove the tests kill them; "kills X" in a comment is a
    claim.

12. **Report the classes separately and never re-pool them.** The kill rate
    is not a quality measure once you know a third of the scope was dead.

## Pitfalls

* **The unanimous result.** If every mutant lands in one class — especially
  the alarming one — suspect the harness before the code. Round 502's first
  run reported 32 of 32 as findings; all 32 were one missing symlink.
* **Believing a stale `survived`.** A survivor is exactly the verdict a
  stronger suite overturns, and campaigns add tests right after they finish.
  Re-score before quoting the number.
* **Scoping a campaign by "important functions" without checking callers.**
  Grep for the call, do not trust the docstring. A function's docstring will
  happily describe the published verdicts it is not involved in.
* **Randomised outputs.** An output-digest oracle needs byte reproducibility;
  a verb with an unseeded null belongs in the excluded list, named.
* **Tracing cost.** A line tracer is 10-50x the untraced run. Trace ONCE for
  the baseline and reuse the line set; do not trace per mutant.
* **Equivalent-by-assertion.** "This mutant is equivalent" is a claim that
  must be proved by trying to kill it, or by an argument about the arithmetic
  that someone else can check. Neither is "I read it and it looked fine".
* **Treating `reached_but_identical` as free.** It is only equivalent *on
  these inputs*. Say which inputs.

## Verification

The classifier must (a) refuse to run at all if its own sandbox is wrong,
(b) attach a witness to every moving verdict, (c) resolve individual lines of
a multi-line expression, and (d) fail closed when it audited nothing.

```sh
python3 -m pytest nuc/tests/test_survivor_impact.py -q
```

Expected: all pass, including
`test_the_sandbox_keeps_sibling_modules_importable`,
`test_without_the_sandbox_the_same_module_dies_on_the_import`,
`test_strict_fails_when_the_identity_control_did_not_reproduce`,
`test_settrace_resolves_individual_lines_of_a_multi_line_expression` and
`test_a_stdout_change_names_the_first_differing_line`.

On the live corpus:

```sh
python3 nuc/survivor_impact.py --strict --quiet
```

Expected: exit **1** while any standing survivor moves a published number,
naming each on stderr; exit 0 only when the audited set is non-empty, the
identity control reproduced the baseline, and no survivor moves anything.
An empty audit is a FAILURE, not a pass.

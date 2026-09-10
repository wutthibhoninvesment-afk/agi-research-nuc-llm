---
name: a-survivor-is-not-one-finding
description: Use when a mutation-testing run reports N SURVIVORS and someone is about to treat them as one number or one diagnosis (a "kill rate", "the suite needs boundary tests", "close the remaining survivors"). Symptoms; survivors summarised as a percentage; survivors clustered in a function whose callers nobody checked; a resume ledger keyed without the SUITE; a report that says "the battery never reached this line" where NO input could reach it, filing a theorem as evidence about the data. The move; re-run what the module PUBLISHES under each survivor on the real inputs, and split them into the ones that move a published number, the ones that run and change nothing, and the ones the published path never executes - orphan, unentered, dead branch. Then give the ones NOTHING can ever kill their own recorded verdict, with a cited test that runs, the subject digest it was proved at, and a rule that a measurement overrides it. Includes the identity control that stops a broken sandbox reporting every mutant as a finding.
---

# A surviving mutant is not one finding. It is at least four,
# and one of them is not a finding about your suite at all.

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

The corollary: every verdict above is measured by running ONE battery on ONE
               record, so none of them can answer "could ANYTHING have killed
               this?".  A classifier with no fifth answer will spend one of
               the four on the cases where the answer is no.
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

## The second measured instance (round 526), and it is about the CLASSIFIER

Twenty-four rounds later the same module was down to **5 survivors**, and the
report — built by the instrument this skill describes — graded them with two
words. Re-derived, they were three things:

| id | report said | actually |
|---|---|---|
| `1586:cmp#162` | `reached_but_identical` | **equivalent for every legal input**: the mutated guard is a fast path the general case reproduces exactly (23 821 argument triples, 0 differing, all exactly `1.0`) |
| `1642:const#983` | `reached_but_identical` | **an ordinary suite gap** — moves a PUBLISHED field, killed by one new test |
| `1642:arith#984` | `reached_but_identical` | **an ordinary suite gap** — same, killed by one new test |
| `1660:const#1547` | `unreached_by_battery` / `branch_not_taken` | **unreachable by theorem** |
| `1661:const#1601` | `unreached_by_battery` / `branch_not_taken` | **unreachable by theorem** |

Both report verdicts were true. Both were also facts about **the battery**,
and two of the five needed a fact about **the arithmetic**:

* The classifier's own docstring called `reached_but_identical` "killable only
  by a test that asserts something no published number depends on". For two of
  its three instances that was **false** — both moved fields the module
  publishes, and each died to one three-line test.
* The two `branch_not_taken` mutants live in the third arm of a format string
  that fires when a computed set is non-contiguous. The set is the sublevel
  set of a quasiconvex function, so it is **always** an interval and that arm
  can never run — 66 400 record shapes swept, 0 non-contiguous. The reason
  code assigned to them is documented as "the only one of the three that is
  evidence about the box". It was evidence about a hypergeometric tail.

After step 13, the report reads `standing 5 -> 3`, `provably_dead 3`,
`unexplained 0`: *this subject has no unexplained surviving mutant at this
digest.* Nothing about the code changed to earn that sentence — two tests were
written and three verdicts were given a home.

## When this triggers

* A mutation report is about to be summarised as a kill rate or a percentage.
* A next-step reads "close the remaining survivors" and names no consequence.
* Survivors cluster on 2-3 lines — that clustering is usually one structural
  fact (a dead branch, an orphan, a format string nobody asserts), not N gaps.
* The subject is an INSTRUMENT: something whose output is quoted in reports,
  dashboards, papers or tickets. Then "does a test notice?" is the wrong
  question and "does the number move?" is the right one.
* A resume ledger's key does not include the test suite.
* A report grades a survivor "the battery never reached this line" and nobody
  has asked whether ANY input reaches it. That is two different findings under
  one word, and only one of them is work.
* Someone is about to write "these N are equivalent, leave them" in prose. Ask
  where a reader six rounds from now will see that, and whether anything will
  notice when it stops being true.
* A campaign's survivor count has been stable across rounds. Stability is what
  a set of unkillable mutants looks like, and also what an unread report looks
  like.

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

    **And then put the answer in the REPORT** (step 13). A property test and a
    comment are read by whoever opens that file; the report is what the next
    round opens, and it still says `branch_not_taken` — which, in a classifier
    that documents that reason as "the only one of the three that is evidence
    about the box", is the opposite of what you just proved. Round 502 wrote
    this step. Round 520 obeyed it as far as the sweep and had nowhere to file
    the result, so two theorems sat in the report as facts about a machine for
    six rounds.

11. **Write tests only for the movers, and pin the value the artefact
    publishes** — the number or the sentence, on the real input. Then re-score
    those mutants to prove the tests kill them; "kills X" in a comment is a
    claim.

12. **Report the classes separately and never re-pool them.** The kill rate
    is not a quality measure once you know a third of the scope was dead.

13. **Give "nothing can kill this" its own recorded verdict — with three
    fences, because it is the one verdict a future round would like to abuse.**
    A registry mapping mutant id to `{class, proof, subject_digest, why}`, and
    the classifier upgrades the measured verdict when an entry governs. Keep
    the measurement beside it (`raw_verdict`, `reason`); an upgrade that
    destroys what was measured cannot be audited or reversed.

    * **The proof is a test NODEID, and something RUNS it.** A `--verify-proofs`
      mode that executes the cited tests and fails the gate unless they pass,
      plus a cheap collect-only check on every suite run so a rename of the
      proof breaks the claim. A citation nobody executes is a comment.
    * **The entry names the SUBJECT DIGEST it was proved at.** A mutant id is
      generated by walking one version of one file; at any other digest it
      names a different line or nothing at all, and the entry must grade
      NOTHING rather than grade the wrong thing.
    * **A measurement OVERRIDES the registry.** If the battery kills a mutant
      the registry calls unkillable, the entry is false — report it, fail the
      gate, and do not let the upgrade quietly swallow the contradiction.

    Then decompose the headline: `n_survivors_standing` was pooling survivors
    a test could still kill with survivors nothing will ever kill, and those
    two are not worth the same. `provably_dead + unexplained == standing` is
    the invariant to pin, and `unexplained == 0` is a real result — a stronger
    statement than "5 survivors" was a weakness.

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
  these inputs*. Say which inputs. Round 526's instance is the counter-example
  that matters: two of three `reached_but_identical` survivors moved fields the
  module PUBLISHES and died to one small test each. "Identical on this record"
  and "not worth a test" are different claims and the classifier only measures
  the first.
* **Letting a verdict name a fact about the battery and be read as a fact
  about the world.** `unreached_by_battery`, `branch_not_taken` and
  `reached_but_identical` are all measured by running one battery on one
  record. Every one of them is honest about what it measured and silent about
  what a reader will infer. If the classifier has no word for "no input could
  reach this", the theorem gets filed under the reason that means "the data
  happened not to".
* **A proof registry with no runner.** An entry saying "proved equivalent, see
  `test_foo`" that nothing executes is worth exactly as much as a comment, and
  it looks like more. Run the citations in the gate, or do not claim them.
* **Deleting the dead code as the "obvious" fix.** Sometimes right, never
  free: it moves the subject digest, which invalidates every ledger row scored
  against it, and it removes the branch that would fire if the invariant you
  just proved ever stopped holding. Price it — rows to re-score, seconds per
  mutant — and say what the arm was guarding, before calling it tidying.

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

and, since round 526, the fences on step 13's registry:
`test_every_proven_entry_cites_a_test_that_actually_exists` (collect-only, so
it runs on every suite pass), `test_proof_for_governs_only_at_the_digest_it_
was_proved_at`, `test_strict_fails_when_a_proven_mutant_turns_out_to_be_
killable`, `test_strict_fails_on_an_entry_proved_at_another_digest`,
`test_verify_proofs_refuses_to_pass_when_it_ran_nothing`, and
`TestThisTreeProven::test_the_headline_number_is_decomposed_and_the_parts_add_up`.

The load-bearing check is that the fences FAIL without the machinery:

```sh
cp nuc/survivor_impact.py /tmp/si.py
git show 202cb6d:nuc/survivor_impact.py > nuc/survivor_impact.py
python3 -m pytest nuc/tests/test_survivor_impact.py -q -k "proven or proof or Proven"
cp /tmp/si.py nuc/survivor_impact.py
```

Expected at round 526: **8 failed, 4 passed** — the 4 read only the committed
report or are the negative control that must pass either way.

On the live corpus:

```sh
python3 nuc/survivor_impact.py --strict --quiet --verify-proofs
```

Expected: exit **1** while any standing survivor moves a published number,
naming each on stderr; **1** if any cited proof does not pass, if any registry
entry was proved at a different subject digest, or if the battery killed a
mutant the registry calls unkillable; exit 0 only when the audited set is
non-empty, the identity control reproduced the baseline, every proof ran and
passed, and no survivor moves anything. An empty audit is a FAILURE, not a
pass — and so is a registry whose proofs nobody ran.

```sh
python3 -c "import json; d=json.load(open('state/nuc/round-526/survivor-impact.json')); \
print(d['n_survivors_standing'], d['n_survivors_provably_dead'], d['n_survivors_unexplained'])"
```

Expected: `3 3 0`, and `provably_dead + unexplained == standing` in every
report thereafter.

Worked example with both scored prediction banks:
`knowledge/round-502-nuc-e-the-survivor-that-was-eight-different-things.md`
(the four classes) and
`knowledge/round-526-the-branch-no-record-could-take.md` (the fifth verdict,
and the two `reached_but_identical` survivors that were ordinary gaps).

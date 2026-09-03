---
name: falsifier-must-kill-something
description: Use when a suite is green and nobody can say which of its tests would have caught the bug — "these tests guard the parser", a test that only asserts a call did not raise, a published number defended by a test nobody has ever seen fail. Symptoms: a test file grew alongside its module and never went red; a review says "add a test" and the test passes the moment it is written; a suite's mutation score is high and its author cannot name a node that has ever failed. Also trigger when an absence claim came out of a NARROWED campaign — --sample, --limit, --funcs, "we ran the first N" — because a sample buys a score and cannot buy an absence. Covers running a mutation campaign whose MUTANT runs each emit a junit report, attributing every kill to the node that produced it, and the five bounds on the never-red list: scope, attribution, equivalent mutants, selection completeness, operator coverage. NOT plain mutation testing (that scores the CODE), and NOT named-guardian-must-go-red (one pin, one call).
---

# A falsifier that never went red is not a falsifier

A mutation score is a statement about the **code**: *how many small semantic
slips does this suite notice?* Its unit of account is the mutant, and its
output is a score plus a survivor list.

The mirror question is a statement about the **tests**: *which of these
nodes could ever have gone red?* A suite can answer the first question well
and the second one badly, because **one thorough test node can kill every
mutant the file's other twenty nodes were supposed to cover**. The score
stays high. The twenty are decoration.

Two different defects, two different repairs:

| finding | what it says | what to do |
|---|---|---|
| a SURVIVOR | the subject has behaviour nothing asserts | write a test |
| a NEVER-RED node | the TEST has no assertion that depends on the subject | fix the test |

Round 472 of this program mutation-tested its own 49 new tests and found
**3 of 10 mutations survived — three tests that could not have gone red for
ANY code change**, one of them guarding a published p-value. First-run
silence does not reveal that. Only a campaign that reports per-TEST does.

## When to use (triggers)

* A suite is green and you cannot name the node that would fail if a given
  function stopped working.
* A test file grew alongside its module over many rounds/PRs and no node in
  it has ever been seen red.
* A published number (a rate, a p-value, a score) is defended by "there is a
  test for that".
* A review asked for a test, the test was written, and it passed
  immediately — nobody watched it fail.
* You are about to delete or refactor a test file and want to know which of
  its nodes are load-bearing.

**Not** for measuring coverage of a module (plain mutation testing), and not
for checking one named pin against one named call — that is
`named-guardian-must-go-red`, which walks from a CALL to its guardian.
This walks from a TEST to whether anything can make it fail.

## Steps

1. **Pair each subject module with the test file that CLAIMS to be about
   it.** The pairing is the whole scope of the claim: a node about some
   other module cannot go red for a mutant of this one and is not a defect.
   Write the pairing into the report so the claim carries its own bound.

2. **Green baseline first, in the same throwaway copy the mutants will run
   in.** A verdict against a red baseline is not evidence, and it fails in
   the flattering direction — every mutant looks caught. Record the node
   population the baseline actually PASSED; a node the sandbox SKIPPED never
   ran, and accusing it of being unfalsifiable is an accusation against the
   copy.

3. **Give every MUTANT run its own `--junitxml`, and never `-x`.** This is
   the whole mechanism. Under `-x` the report names ONE red node per mutant
   and every other node that would have caught the same mutant is recorded
   as passing, so the attribution measures collection order.

4. **Exclude the `if __name__ == "__main__":` guard, and say how many sites
   that removed.** Mutating it makes the module run its own CLI at import
   time: a collection-time exit, no evidence either way, and a FREE KILL
   under any classifier that reads "non-zero exit" as "a test failed". It is
   a silent tax on every campaign over a module with a CLI.

5. **Union the red sets; count per node; the zeros are the work list.**
   `kills[node]` over the baseline-passed population, zeros included — built
   from the baseline population and not from the union of red sets, or a
   node that never appears in any red set is simply absent from the table
   instead of visible in it.

6. **Refuse the word "unfalsifiable" when attribution coverage is below
   100 %.** A killed mutant with no readable junit — a timeout, a crashed
   interpreter — proves some node went red and hides which. Count those,
   and report `never_red` as an UPPER BOUND when there are any. Same for a
   mutant run that collected FEWER nodes than the baseline: everything it
   did not collect looks never-red for a reason that has nothing to do with
   the test.

6a. **And refuse it when the campaign ran a SUBSET of the sites.** This is
   the bound that is easiest to leave out, because the narrowing is a
   deliberate, well-recorded budget decision and it feels like an honest
   one. It is honest about the SCORE and dishonest about the ABSENCE:

       score      = killed / RUN          -- a sample estimates it
       never_red  = "no mutant killed it" -- a sample cannot estimate it

   A sample gives an unbiased estimate of a proportion. There is no such
   thing as an unbiased estimate of "nothing in the population has this
   property" from a subset of the population: every site you did not run is
   a site that could have killed the node. Compute `site_coverage` =
   selected / eligible (eligible = generated minus the `__main__` guard,
   which is excluded by policy and not by budget) and fold `< 1.0` into the
   soundness flag, so a narrowed campaign returns "cannot support the claim"
   rather than a list.

   Round 479 is the worked example, and it cost 22.7 s to produce. Round 473
   sampled 200 of `redattrib.py`'s 443 sites, reported `sound: true`, and
   published one never-red node. Re-running the FIVE sites of the one
   function that node is about killed it twice over — and both killers were
   among the 243 sites the stride had skipped. The test was a good
   falsifier; the finding was an artefact of the sample. A published
   never-red list is a claim about a population, so it costs the whole
   population.

6b. **Report what no operator can reach, as a number.** Absence has a second
   source that no amount of running fixes: a test whose only dependence on
   the subject is a constant your operators cannot mutate. Typical operator
   sets handle `bool` and `int` and stop there — so a float, a string, a
   bytes literal or `None` is unreachable, and a node that asserts on one is
   `never_red` no matter how complete the campaign. Round 473 wrote this
   bound down about STRINGS; the first node anyone classified under it
   asserted `signature(plan).parameters["default_s"].default == 120.0`, a
   FLOAT, and `generate` emits zero sites on that line. Count the
   unmutable constants per type over the subject and print them next to the
   verdict. Do NOT fold this into the soundness flag: it bounds what the
   list MEANS, not whether the campaign was complete — every real module has
   hundreds of strings, and a flag that is always False says nothing.

7. **A campaign that killed nothing reports `no_kills`, not `never_red`.**
   Every node is trivially never-red when no mutant died. Saying
   `never_red` there blames the tests for the engine's silence.

8. **Triage the residue by hand and write the killers.** For each never-red
   node ask which of the FIVE it is, in this order — the first three are
   free, and skipping them produces accusations: (a) about a different
   subject — fine, re-pair it; (b) the campaign was narrowed and the killing
   site was outside it — re-run that node's function alone, which is cheap
   (step 6a); (c) its only dependence on the subject is an unmutable
   constant — unreachable, not vacuous, and the repair is to the OPERATOR
   SET or to nothing (step 6b); (d) an assertion on the SHAPE of an output
   where the value is what matters; (e) genuinely vacuous. Only (d) and (e)
   are defects, and both are repaired by making one assertion depend on a
   value the subject computes.

9. **Re-run the campaign after the repair and publish both numbers.** A
   killer test that does not move the score did not kill anything.

## A sample buys a score. It cannot buy an absence.

Budget-limited campaigns are usually cut with a `limit=N`, which takes the
first N mutation sites in SOURCE ORDER — for every module that means the
imports, the constants and the first function or two. An evenly spaced
stride over the whole site list costs the same and is bounded uniformly.
Whichever you use, record it: a score over a sample and a score over a
module are different numbers.

That much is about the score, and it was already written down here when
round 473 published a false never-red finding out of a `--sample 200`. Say
the second half too, in the same breath, because the first half reads like
the whole rule:

| claim | narrowed campaign | what to do |
|---|---|---|
| mutation score | an estimate, with the sample recorded | publish it, name the sample |
| survivor list | a subset of the real one | publish it, name the sample |
| `never_red` / "no test guards this" / "nothing kills it" | **not supported at all** | re-run the sites the node could be about, or say the campaign cannot answer |

The asymmetry is the point: two of those three are proportions and one is a
universal quantifier. Budget-cutting an existential claim weakens it;
budget-cutting a universal claim destroys it.

## Pitfalls

- **Reading `never_red` as an accusation.** It is a work list. The default
  explanation is scope: the node is about something the campaign did not
  mutate. Check that first, every time.
- **A high mutation score read as "the tests are good".** The two numbers
  are nearly independent. Round 473 measured a module at **81.3 %** killed
  with **zero** never-red nodes, and its 14 survivors still contained three
  genuine missing assertions. High score, healthy tests, real gaps — all
  three at once.
- **Believing a green campaign that errored.** An errored mutant is a
  non-result, not a weak result. Under the pre-round-349 classifier a
  campaign whose suite could not run at all scored 100 %.
- **Mutating the `__main__` guard.** See step 4. It looks like a normal
  `if`, and it is the one `if` in a module that cannot be evidence.
- **Equivalent mutants counted as gaps.** `most_common(1) -> most_common(2)`
  followed by `[0]` is the same program. Triage before you count.
- **A `sound: true` that never looked at the selection.** The soundness flag
  is the one thing a reader trusts without re-deriving it, so every bound
  that is NOT in it is a bound nobody applies. Round 473's report printed
  its `--sample 200` two lines above `sound: true` and the two were computed
  independently; the reader who published the finding had both numbers on
  screen. Put the bound in the flag, not in the prose next to it.
- **Repairing a test that was never reachable.** If the node's only
  dependence on the subject is a float or a string, "fixing" it means
  writing an assertion about something else — you will make it reachable by
  making it about a different property, and the property it was about stops
  being pinned. Widen the operator set, or record the bound and leave the
  test alone.
- **Auditing the auditor with the auditor and calling it independent.**
  Running the tool on itself is worth doing — it is the cheapest possible
  self-check — but the campaign and the subject then share every bug. Pair
  it with a toy project whose answer you already know.

## Verification

```bash
cd ~/agi-research-nuc-llm
python3 harness/swe/falsifiers.py functions harness/swe/scoreaudit.py
python3 -m pytest -q harness/tests/test_swe_falsifiers.py
# A NARROWED campaign. Before round 479 this printed `sound: true` and a
# never-red list; it now exits 2 and names the shortfall. That change is
# the check: this very block used to buy an absence with a sample.
python3 harness/swe/falsifiers.py audit \
    --subject harness/swe/scoreaudit.py \
    --tests harness/tests/test_swe_scoreaudit.py \
    --sample 8 --timeout-s 60 --quiet --json /tmp/fals-check.json ; echo "rc=$?"
python3 -c "import json;d=json.load(open('/tmp/fals-check.json'));\
print(d['verdict'], d['sound'], d['unsound_reasons'])"

# The same subject, WHOLE (75 sites, ~5 min solo on a one-CPU box). Only
# this one may be quoted as a never-red finding.
python3 harness/swe/falsifiers.py audit \
    --subject harness/swe/scoreaudit.py \
    --tests harness/tests/test_swe_scoreaudit.py \
    --timeout-s 60 --quiet --json /tmp/fals-whole.json ; echo "rc=$?"
python3 harness/swe/falsifiers.py report /tmp/fals-whole.json
```

Exit codes are the verdict: **0** every baseline-passed node went red at
least once, **1** at least one node never did, **2** the campaign cannot
support either claim — an unattributed kill, an errored mutant, a run that
collected fewer nodes than the baseline, **or a campaign that ran only some
of the eligible sites**. The `--sample 8` invocation is now an example of
the LAST of those: it still runs in about a minute and still shows the
machinery working, and it now says out loud that it cannot answer the
question this skill is about.

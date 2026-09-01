---
name: mutate-the-rule-both-ways
description: Use when judging whether a test or check actually guards the rule it names — mutation testing, test-suite audits, or before claiming a rule is pinned. The failure is directional: a one-sided guardian (`assert missed(x)`, `assertIn(s, msg)`, `assertRaises`) is monotone one way and cannot go red when the rule breaks THAT way. Symptoms: every mutant weakens the rule; a message grows text nobody asserted the absence of; a mutant that reddens nothing because the rule is implemented twice; a mutant invisible to the check you named but visible to others. Covers pairing each mutation with its opposite under the SAME guardian, classifying guardians by predicate shape before any campaign runs, telling "nothing guards this" from "redundant", and telling a MISPOINTED pin from a blind file (5 of 5 such findings were fixed by re-pointing the pin, not the code). NOT for choosing the probe VALUE (probe-where-the-rules-disagree), NOT for a call site nobody claimed anything about (named-guardian-must-go-red).
---

# Mutate the rule both ways, or you measured the direction you picked

A mutation campaign breaks a rule and asks whether the named test goes red.
Which way you break it is a free parameter, and almost nobody varies it.
The default is "make the rule do LESS" — delete the arm, return the
identity, empty the list — because that is what a bug looks like.

That choice is not neutral. Half of a real suite's assertions are **one
sided**:

| assertion shape | monotone in | cannot see |
| --- | --- | --- |
| `assert missed(x)` / `assertRaises` / `x is None` | "fails more" | a rule that fails MORE than it should |
| `assertIn(s, message)` / `contains(...)` | "says more" | a message that grows a clause |
| `assert len(xs) > 0` / `assert xs` | "reports more" | a walk that reports the whole chain instead of its root |
| `assert not is_num(v)` | "says no more often" | a predicate that says no to everything |
| `assert f(a) == V` | *value*: two-sided | *coverage*: the branch/operand/arm it does not probe |

A one-sided assertion is a real assertion. It is simply not a guard in the
direction it is monotone in, and a campaign that only ever pushes that way
will report it as a guard.

## Measured instance

Whence round 416, the guest evaluator of `examples/self_eval.lang`
(166 `check` statements). 16 evaluator rules, each mutated in BOTH
directions where a coherent opposite existed, each judged by the **same**
`check` label:

```
              guarded  finding
  "-" (does less):  11       4
  "+" (does more):   3      11        Fisher exact, two-sided, p = 0.009, n = 29
```

Of **11 mechanisms mutated both ways under one guardian, not one guardian
caught both directions.** The three `"+"` mutants that were caught were the
three where somebody had already written the other side on purpose — a
check with an explicit negative clause (`... and not contains(msg, t)`), a
deliberately-written opposite PAIR of checks, and one where the campaign
itself pointed the pin at a different label chosen for that direction.

Concretely, all of these left 166 of 166 checks green:

* appending a clause the reference implementation never emits to an error
  message (`assertIn` is monotone in "says more");
* an `and` that answers `false` for every input, because the only check was
  `false and <miss> == false`;
* labelling the ELSE branch of `if` "took then-branch", because the one
  probe took the then-branch;
* a `blame` that reports the whole miss chain instead of its origin, and a
  `blame` that reports nothing, because the assertion was `contains(...)`
  over the first origin.

## Triggers

* You are writing or reviewing mutants and every one deletes or weakens.
* A guardian is `assertIn` / `assertRaises` / `assert x` / `assert not ...`
  and you are about to call the rule "pinned".
* A message, label or diagnostic is asserted with substring containment and
  nothing asserts what it must NOT say.
* A check names a rule with two arms, two operands or two branches and
  probes one.
* A mutant came back invisible and you are about to write a new test.
  **Stop and do step 5 first.**

## Steps

1. **Name the rule as a function, and name its two failure directions.**
   `-` the rule fires less / reports less / says less; `+` the rule fires
   more / reports more / says more. If only one direction is coherent, say
   so in the registry — that is a fact, not an omission.

2. **Write the `+` mutant, and make it a real divergence, not noise.**
   The productive `+` mutants are: append a clause to a message; widen a
   refusal to a neighbouring type; report every node instead of the root;
   make a predicate answer "no" universally; fire a guard that should be
   conditional. Each is something a careless refactor genuinely does.

3. **Judge BOTH with the same guardian.** Different labels make the
   comparison meaningless — you would be measuring two checks, not two
   directions. Where the `+` direction has its own author-written check,
   record that: it is the *positive* result, and it is rare.

4. **Classify the guardian by predicate shape before you see the verdict.**
   Write the shape into the registry (`predicate: "contains(str(X), s)"`).
   A verdict you can predict from the shape is evidence the shape is the
   cause; a verdict you cannot is the interesting one.

5. **Before writing a killer for an invisible mutant, remove EVERY copy of
   the rule.** `nothing went red` has two causes with opposite responses:

   * nothing guards this rule → write a check;
   * the rule has more than one implementation and you removed one → write
     **nothing**; the suite is right that the behaviour did not change.

   Both read identically. The only thing that separates them is a WIDER
   mutant that removes all copies: if that one goes red, the rule was
   *redundant*, not unguarded. Round 416 hit this twice in 16 rules — an
   ordering that was belt-and-braces over four probes that each already
   guarded themselves, and a decision enforced in both a function and the
   function it tail-calls. Both would have collected a pointless new test.

6. **Before you touch the code under test, ask whether the pin is
   mispointed.** This is round 420's correction to step 7 below, and it is
   the step that pays for the whole skill. A `shadowed` verdict says *the
   file distinguished the rule; the check you named did not* — so the right
   guardian may already be in the file, and it is in the co-red list. Filter
   the checks that went red by polarity and keep the ones SIGHTED in this
   mutant's direction:

   * a sighted candidate exists  ->  the pin is **mispointed**. Change the
     registry's `guardian` string. Write no test, touch no source.
   * no sighted candidate        ->  now it is a coverage gap. Go to 7.

   Measured, Whence round 420 over round 416's five `shadowed` findings:
   **all five had a sighted, already-red candidate**, and re-pointing the
   five turned 5 findings into 5 `guarded` in 22.8 s with **not one line of
   the guest evaluator changed**. Round 416 had read them as five coverage
   gaps and written the round-419 next-step item "argued but not fixed".
   They were not gaps. Only 2 of the 5 were even predicate blindness; the
   other 3 were probe agreement (see `probe-where-the-rules-disagree`),
   which no new predicate over the same probe can fix.

7. **Fix the one-sided guardian by making it two-sided, not by adding a
   second test.** In order of preference:
   * replace containment with **equality against the reference
     implementation's own output** (`assert strip(guest_msg) ==
     strip(host_msg)`) — this kills the whole "says more" class at once and
     cannot drift, because it asserts no constant of its own;
   * add the missing negative clause (`and not contains(msg, t)`);
   * add the unprobed branch/operand to the existing check, so the label
     that carries the claim is the thing that goes red.

8. **Re-run and require the killer to be red under its mutant and GREEN
   under a neighbour**, so it discriminates the rule it names rather than a
   neighbouring one.

## Pitfalls

* **An edit that changes more than the rule.** Round 416's first
  short-circuit mutant deleted the `false` arm of `and`, which routed
  evaluation through an `else` branch whose payload assumed the left
  operand was `true` — so it changed the VALUE as well as the branch and
  came back `guarded` for the wrong reason. Write the isolated form
  (evaluate the right operand, keep the payload correct) and re-run. A
  `guarded` verdict is not self-validating.
* **Scoring `redundant` as a suite defect.** It makes a codebase that
  defends a rule twice look worse for having done so. Score it out, like a
  negative control.
* **Direction as a synonym for severity.** `+` mutants are not "weirder"
  than `-` ones. A message that grows a clause and a `blame` that reports
  the whole chain are ordinary refactor damage.
* **A `shadowed` verdict read as a gap in the CODE.** Something in the file
  noticed; the check you named did not. Round 420 measured which it usually
  is: **5 of 5** of round 416's `shadowed` findings were mispointed pins,
  not blind files. Run step 6 before you believe a coverage claim, and
  never carry a `shadowed` verdict forward as "the file needs a new check"
  without having looked at what went red.
* **Reading a static polarity flag as a verdict.** Monotonicity holds along
  an order, and the order the ASSERTION is monotone along is not the order
  the pin's `dir` names. `dir` describes a change to the RULE; polarity
  describes the OBSERVATION. Two ways they come apart, both measured:
  *infix growth* — `contains(msg, "return value expected num")` is monotone
  under APPENDING, and the `+` edit inserted `of g` in the MIDDLE, which
  destroys containment; and *kind change* — `is_guess(x)` is monotone under
  a rule that accepts more, and the `-` edit stopped the value being a
  Guess at all. So record the PRECONDITION beside every blindness claim
  (`append_only`, `refusal`, `kind_stable`) and treat a flag contradicted by
  a measured `guarded` as *the edit left the order*, not as a broken tool.
  False-positive rate, two independent registries, 51 directional pins:
  **4** (2 in each), 3 of them `append_only`.
* **Forcing a direction onto a lateral edit.** Some replacements are
  neither more nor less — swapping one rendering for another of the same
  size. Round 420 found **3 of 23** pins in Whence's parser registry are
  lateral, and a lateral edit has no order for a monotone predicate to be
  blind along, so scoring it invents a verdict. Give the registry a third
  value (`~`) and skip those pins rather than rounding them to `-`.
* **No negative control.** An invisible mutant reads the same whether the
  file cannot see the rule or your runner never applied the edit. Put a
  semantically identical rewrite in the SAME batch, through the SAME
  runner, and require it to come back invisible.

## Verification

You have applied this skill when, for each rule you claim is pinned:

1. the registry records `dir` (`-`/`+`) and `predicate` (the guardian's
   expression shape) for every mutant;
2. every mechanism with a coherent opposite has **both** mutants, judged by
   the same guardian, and the pairing is asserted by a test rather than
   described in the write-up;
3. every mutant that reddened nothing was re-run in a WIDER form removing
   all copies of the rule, and the result is recorded as *unguarded* or
   *redundant* — never left as bare "inert";
4. at least one negative control ran in the same batch and came back
   invisible;
5. every killer you wrote is red under its own mutant and green under a
   neighbouring one;
6. every `shadowed` verdict was passed through the mispointed-pin test of
   step 6 and is recorded as *mispointed* (with the label it should have
   named) or *coverage gap* (with the co-red list that had no sighted
   candidate) — never as bare "shadowed";
7. every blindness claim carries the precondition it rests on, and every
   pin whose direction is lateral is marked `~` rather than scored.

Round 416's own record, re-runnable. The first command shows every mutant's
direction and predicate WITHOUT running anything, which is where a
contaminated edit (an edit that changes more than the rule) is cheapest to
catch; the second is the campaign:

```bash
cd languages/whence
python3 checkpin.py locate ../../state/whence/round-416/eval-pins.json
CHECKPIN_JSON=/tmp/r416.json \
  python3 checkpin.py run ../../state/whence/round-416/eval-pins.json
```

Expected last lines — the `redundant` count is the part that distinguishes
this from an ordinary mutation report:

```
30 pins: 25 guarded, 5 finding(s), 0 error(s), 2 redundant, score 83%
REDUNDANT EP07m: inert, but the wider edit EP07m2 went red
REDUNDANT EP12m: inert, but the wider edit EP12m2 went red
CONTROL NC01: inert (n_red=0) -> HELD
CONTROL NC02: inert (n_red=0) -> HELD
```

To see the effect the skill is about, re-run against the file as it was
before the killers and compare the score:

```bash
git show HEAD~1:languages/whence/examples/self_eval.lang > /tmp/before.lang
```

### The round-420 half: polarity before the campaign

`polarity.py` computes each guardian's blind direction from its expression
AST, so steps 4 and 6 stop being judgement calls. Nothing here runs the
guest program, and the whole sweep is milliseconds against a campaign's
~100 s:

```bash
cd languages/whence
python3 polarity.py classify examples/self_eval.lang examples/self_host.lang
python3 polarity.py audit   ../../state/whence/round-416/eval-pins.json \
                            ../../state/whence/round-416/run.json
python3 polarity.py repoint ../../state/whence/round-416/eval-pins.json \
                            ../../state/whence/round-416/run.json
```

Expected — `audit` names the mispointed pins AND the false positives it
cannot resolve without the run, which is the honest form of a conditional
rule:

```
examples/self_eval.lang: 172 check(s)
  one-sided         74  (43.0%)   +blind 68, -blind 6, both 0
examples/self_host.lang: 155 check(s)
  one-sided         73  (47.1%)   +blind 52, -blind 21, both 0

audit: examples/self_eval.lang — 32 directional pin(s), 2 MISPOINTED,
       0 unlocatable, 2 precondition-broken
```

And the demonstration, which changes no source at all:

```bash
CHECKPIN_JSON=/tmp/r420.json python3 checkpin.py run \
  ../../state/whence/round-420/eval-pins-repointed.json
# 5 pins: 5 guarded, 0 finding(s), 0 error(s), 0 redundant, score 100%
```

Reference implementation: `languages/whence/checkpin.py` (`dir`,
`predicate`, `also`, `redundant_with`, the `redundant` verdict),
`languages/whence/polarity.py` (`classify`, `law`, `audit`, `repoint`),
`state/whence/round-416/eval-pins.json` and
`state/whence/round-420/eval-pins-repointed.json`. Tests:
`python3 -m pytest languages/whence/tests/test_checkpin.py
languages/whence/tests/test_polarity.py -q`.

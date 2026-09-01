---
name: mutate-the-rule-both-ways
description: Use when judging whether a test or check actually guards the rule it names — mutation testing, test-suite audits, or before claiming a rule is pinned. The failure is directional: a one-sided guardian (`assert missed(x)`, `assertIn(s, msg)`, `assert len(xs) > 0`, `assert not is_num(v)`, `assertRaises`, `x is None`) is monotone one way and cannot go red when the rule breaks THAT way, however badly. Symptoms: every mutant weakens the rule; a suite scores well against one-directional mutants; a message can grow text nobody asserted the absence of; a check named for one branch, arm or operand; a mutant that reddens nothing because the rule is implemented twice. Covers pairing every mutation with its opposite under the SAME guardian, classifying guardians by predicate shape, and telling "nothing guards this" from "the rule is redundant". NOT for choosing the probe VALUE (probe-where-the-rules-disagree), NOT for a call site nobody claimed anything about (named-guardian-must-go-red).
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

6. **Fix the one-sided guardian by making it two-sided, not by adding a
   second test.** In order of preference:
   * replace containment with **equality against the reference
     implementation's own output** (`assert strip(guest_msg) ==
     strip(host_msg)`) — this kills the whole "says more" class at once and
     cannot drift, because it asserts no constant of its own;
   * add the missing negative clause (`and not contains(msg, t)`);
   * add the unprobed branch/operand to the existing check, so the label
     that carries the claim is the thing that goes red.

7. **Re-run and require the killer to be red under its mutant and GREEN
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
* **A `shadowed` verdict counted as coverage.** Something in the file
  noticed; the check you named did not. That is still a finding about the
  label, and the fix may legitimately be "nothing" — but say which.
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
   neighbouring one.

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

Reference implementation: `languages/whence/checkpin.py` (`dir`,
`predicate`, `also`, `redundant_with`, the `redundant` verdict) and
`state/whence/round-416/eval-pins.json`. Tests:
`python3 -m pytest languages/whence/tests/test_checkpin.py -q`.

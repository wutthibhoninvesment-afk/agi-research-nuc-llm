---
name: unknown-names-its-residual
description: Use when a prover, static analyser, type checker, decider or solver returns `unknown`/`maybe`/`unsupported` on cases you want to close, and someone proposes adding a rule, law, axiom or simplification to close them. Symptoms: a report line that names the AST class or node type on each side instead of the proposition, so it says something is undecided without saying what; an `unknown` bucket counted as a coverage gap; a next-step item asserting that rule X "would decide" N named cases; a law that reads as obviously true about the target system's builtins ("contains implies non-empty", "sorted implies ordered", "non-null implies initialised"); a guard invented to rescue a law rather than measured. Covers making every `unknown` print the exact proposition it failed to prove, RUNNING that proposition in the target system before adopting it, testing the proposed guard separately from the law it rescues, and pinning a refuted law with an executable counterexample so a later round cannot re-add it.
---

# An `unknown` that does not name its residual invites an unsound law

A decider that cannot prove something has two ways to say so. One is useless
and one is the whole finding:

```
unknown: contains(...)  ->  <Binary>              # useless
unknown: contains(acc, nm.name)  ->  (len(acc) > 0)   # the finding
```

The first says a case is undecided. The second says *exactly what would have
to be true* for it to be decided — and that proposition is a thing you can
go and test. The gap between those two lines is where unsound laws enter a
checker, because the first line gives a later reader nothing to check and
the second gives them something to refute.

The dangerous move is not adding rules. It is adding a rule whose
justification never left the reader's head. `contains(X, y)` implying
`len(X) > 0` is *obviously* true — a container that contains something is
not empty — and it takes about four seconds to believe. It is false in a
language whose `contains` also accepts strings, because the empty string
contains the empty string. A prover that adopts it stops being a prover.

**When NOT to use:** the decider is a *decision* procedure, where `false`
genuinely means "does not hold" — there is no residual, only an answer. Also
not for `unknown` caused by a crash, timeout, or unparsable input: that is an
error channel, and
[`skip-reason-is-a-claim`](../skip-reason-is-a-claim/SKILL.md) covers
verdicts that evaporate rather than fail to prove. NOT-scoped against
[`precondition-must-be-decided`](../precondition-must-be-decided/SKILL.md)
(there the condition is printed instead of computed; here it IS computed,
and the question is what the computation could not reach) and against
[`decision-must-name-its-question`](../decision-must-name-its-question/SKILL.md)
(a verdict that does not record which question it answered — this skill is
about a verdict that answered the right question and came back short).

## Trigger conditions

- A next-steps item, ticket, or TODO says a rule "would decide" a named set
  of cases. That is a **claim**, and it has a truth value.
- You are about to add an axiom, rewrite, algebraic identity, or builtin
  law to a prover, normaliser, linter, or type checker.
- A report prints `unknown`, `maybe`, `unsupported`, `NoMatch`, `?` with a
  class name, node type, or opaque handle rather than a proposition.
- Someone proposes a **guard** to make an almost-true law safe ("only when
  X is a list", "only when the value is non-null").
- An `unknown` count is being reported as a coverage gap or a to-do list.

## Steps

1. **Make the `unknown` print its residual.** At the point the decider gives
   up, it holds both sides of the thing it could not relate. Record THOSE,
   not the enclosing node. If the sides are ASTs, write a display-only
   unparser; a class name is not a proposition. Keep the existing verdict —
   this changes what is printed, not what is decided.

2. **Read the residual as a sentence in the target system**, not in your
   head. Write it as a program: `contains("", "") and not (len("") > 0)`.

3. **RUN it.** Not "reason about it", not "check the docs" — execute it
   against the real implementation. A law about builtins is a claim about
   code that exists and can be called.

4. **If it comes back false, stop, and pin it.** Commit the counterexample
   as an executable test with the reason in its docstring. The residual will
   look obviously true to the next reader too; the test is what stops them.
   Keep the case `unknown`, and say in the report that `unknown` is the
   CORRECT answer here rather than a gap.

5. **If someone proposes a guard, test the guard on its own.** A guard is a
   second claim, usually about control flow ("a non-list would have missed
   anyway"), and it fails independently of the law. Write the guard's own
   counterexample program. In the instance below the guard was *"the block
   passes X to `push`, which takes lists only"* — and a `let` binding a miss
   turned out not to abort the block, so the value came back anyway.

6. **Separate the structural fix from the semantic one, and land the
   structural one.** Most "undecidable" cases are a mix: some need a rule
   about SHAPE (which is sound and cheap) and some need a rule about
   MEANING (which is where the unsoundness lives). Do the shape work, count
   what it closed, and report the semantic residual unclosed. One of three
   is a result; three of three obtained by loosening is a regression.

7. **Score the original claim.** If the item said "would decide all three"
   and the honest answer is one, say so with the number, and say which half
   of the proposed mechanism was missing. See
   [`carried-claim-rot`](../carried-claim-rot/SKILL.md) — a proposed fix
   quoted forward without being run is the same failure as a measurement
   quoted forward without being re-derived.

8. **Disclose target selection.** If the cases you closed were NAMED in a
   document that also recorded their measured outcomes, your decider's
   author saw those outcomes even though the decider cannot. Add a control
   that removes the new rule and shows the headline result survives without
   it, and pin the control.

## Pitfalls

- **"It's obviously true" is the symptom, not the clearance.** Every unsound
  law in a prover was obviously true to whoever added it. The four-second
  belief is exactly the one that never gets executed.
- **A law validated on the cases that motivated it.** If the corpus that
  suggested the rule is also the corpus that confirms it, the rule is fitted.
  Look for a case in the language that is NOT in your corpus — the empty
  string, the zero-length list, the single-element chain.
- **Guessing across types to make a fold work.** Folding `0 == false`, or
  ordering two strings because the same operator orders two numbers, buys
  one case and costs soundness on all of them. Fold only same-type.
- **The asymmetric fold.** In a system with three outcomes (true / false /
  error-or-miss), `p and false` is safe to fold to `false` because it is
  TRUE on no input either way, while `p or true` is NOT safe to fold to
  `true` unless you have measured that `or` short-circuits past an error on
  the left. Write down which folds you omitted and why; the omissions are
  the soundness argument.
- **Counting `unknown` as a to-do list.** Some of it is correct. A decider
  that reaches zero `unknown` on a corpus containing genuinely undecidable
  cases has been loosened, not improved.
- **Naming the residual and then not testing it.** Step 1 without steps 2–4
  is prettier output and nothing else.

## Verification

You have applied this skill when all of these are true:

1. Every `unknown` your decider emits carries a printable proposition, and
   you can point at one in the report output.
2. The residual for at least one case has been executed against the real
   target system, and the result is banked as a runnable artefact.
3. Any law you REFUSED to add has a test that fails if it is added.
4. Any law you DID add has a test showing a case it must not decide (a
   near-miss that stays `unknown`), so the rule is exact rather than merely
   stricter.
5. The claim you started from is scored with a number: N of M decided, and
   the mechanism the original proposal was missing is named.
6. If your rule's target cases were named in a document that recorded their
   outcomes, a control test removes the rule and shows the result survives.

```bash
# Step 2, as an executable artefact rather than an assertion. Each of these
# is the REFUTED law, written as a program in the target system and run
# there: the first shows `contains(X, y) -> len(X) > 0` is false in Whence
# (`contains("", "")` is true while `len("") > 0` is false), the second
# shows the guard invented to rescue it is false too (a `let` binding a miss
# does not abort the block, so the arm still returns a value).
python3 languages/whence/run.py state/whence/round-432/counterexample-contains-len.lang
python3 languages/whence/run.py state/whence/round-432/counterexample-let-miss.lang
# -> "checks: 4 passed, 0 failed" from each (exit 0)

# The residual itself: every `unknown` prints the proposition it failed to
# prove, not the AST class on each side.
python3 languages/whence/polarity.py precondition \
    state/whence/round-422/host-pins-plus.json 2>/dev/null | grep -c "unknown"
# -> a count, and every one of those lines carries a readable proposition
```

## The instance this came from

Round 432 (language C). Round 428's next-steps, item 1, verbatim: the
CP17p/CP18p/CP19p class *"would decide all three, and `_implies` — written
this round — is already the relation it needs."* Both halves were false.

* A one-hop dataflow rule (substitute an edited `let`'s two right-hand sides
  into the guard condition one statement below it) decided **one** of the
  three, not three.
* `_implies` alone could not do even that one. It is four syntactic laws
  over `and`/`or`, and substitution hands it a *comparison with an `if`
  inside it*. A truth-preserving normaliser — distribute the `if` through
  the comparison, fold literal comparisons, simplify connectives against
  `true`/`false` — was the missing half. Measured: with the normaliser
  stubbed out and the new rule fully live, the pin comes back `unknown`.
* The other two reduce to `contains(X, y) -> len(X) > 0`, which is **false
  in Whence**: `contains` takes `hay:str|list` and `contains("", "")` is
  true while `len("") > 0` is false. Banked as a runnable program.
* The obvious repair — "the same block passes X to `push`, which takes
  lists only, so a non-list misses anyway" — is **also false**: a `let`
  binding a miss does not abort the block, so a guard arm that never reads
  the bound name returns a value as usual. `probe("xyz")` is `42`, not a
  miss. Banked as a second runnable program.

So two pins stayed `unknown`, and that is the correct answer rather than a
coverage gap. What they gained was a legible residual: the report went from
`unknown: contains(...) -> <Binary>` to
`unknown: contains(acc, nm.name) -> (len(acc) > 0)`.

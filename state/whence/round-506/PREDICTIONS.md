# Round 506 (language C) — predictions, banked before any measurement

Rule D-013: written before the instrument ran. Scored honestly in
`knowledge/round-506-*.md`, misses included.

## The question this round took

Round 504's next-step #1: "`typed` is the one measured gap in the language's
demonstrated surface: 1 use in `examples/`, 47 in the test corpus, the widest
ratio of any builtin. Either an example demonstrates it, or the round that
decides not to says why."

## The hypothesis, stated before measuring

`builtinlive.py` counts **call sites in guest SOURCE**. `SPEC.md:1508` says a
parameter annotation desugars to `let a = typed(a, "num", "parameter 'a' of
f")` prepended to the body, and `SPEC.md:213` says the same for the guard.
So a program using `p: Type` / `-> Type` CALLS `typed` at runtime while never
spelling the identifier. If that is what is happening, "1 use in examples/"
is a fact about the census's model, not about the language's demonstrated
surface, and the next-step's dichotomy ("write an example, or say why not")
has a third answer nobody has written down.

## Predictions

- **P1** `builtinlive.py --no-tests` re-derives `typed` at exactly **1**
  syntactic use in `examples/`. (Re-derivation of a carried number, per the
  standing rule. If it is not 1, the carried number was stale.)
- **P2** At least **5** of the 33 `examples/*.lang` files contain at least one
  parameter or return annotation, i.e. call `typed` at runtime without
  spelling it.
- **P3** A RUNTIME counter over the examples that actually run shows `typed`
  invoked in **>= 5** example programs and **>= 20** total invocations.
- **P4** `typed` has the **largest absolute runtime-minus-syntactic gap** of
  all 37 builtins, because it is the only builtin the language calls on the
  program's behalf via desugaring.
- **P5** At least one builtin has runtime count **0** across all examples
  despite a NON-ZERO syntactic count — a call site on a branch no example run
  takes. (The syntactic census cannot distinguish "shipped" from "executed".)
- **P6** The number of builtins with runtime count 0 over the whole examples
  corpus is **> 0 and < 15** (of 37).
- **P7** The three liveness levels disagree AGAIN. Round 504 measured that
  the Python-def level and the guest-source level disagree on 37 of 37. I
  predict the guest-source and guest-RUNTIME levels disagree on **fewer than
  37** builtins — i.e. unlike round 504's pair, these two levels are
  genuinely correlated, and the disagreement is a minority.
- **P8** Not every one of the 33 examples runs clean under `run.py`. I
  predict **>= 2** examples exit non-zero or are non-runnable as shipped
  (`failing_check.lang` and `diverge.lang` are named to fail/diverge by their
  own filenames), so the runtime corpus is SMALLER than the syntactic one and
  the round must say by how much.
- **P9** The runtime instrument will find at least **1** builtin whose
  runtime count is non-zero while its syntactic count in `examples/` is
  **0** — some builtin OTHER than `typed` is also reached only indirectly.
  (Weaker limb of P4; scored separately because P4 is about the *largest*
  gap and this is about *existence* beyond `typed`.)

## What I will do with the answer

If P3 holds, the honest resolution of next-step #1 is the third answer: the
examples DO demonstrate `typed`, the census cannot see it, and the fix is to
the census's self-description, not to `examples/`. I will still judge whether
an example demonstrates `typed`'s *observable behaviour* (a rejected value
with a blameable miss), which is a different claim from "invokes it".

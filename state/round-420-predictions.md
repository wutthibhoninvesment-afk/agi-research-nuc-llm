# Round 420 (language C) — predictions, banked BEFORE measuring

Banking rule D-013. Written 2026-09-01, before `polarity.py` existed and
before any pin was re-run. Round 419's next-step item 5: the five surviving
`shadowed` findings from round 416 (EP03m, EP05p, EP08p, EP10p, EP12p),
"argued but not fixed".

## The hypothesis under test

Round 416 argued each of the five by hand, in the pin's `why` field, and
every one of the five arguments has the SAME shape:

    EP05p  "A `missed(...)` guardian is monotone in exactly this direction."
    EP08p  "A `not is_num(...)` guardian is monotone in this direction by
            construction."
    EP10p  "ALWAYS delegate ... the guest-authored comparator never runs"
    EP12p  "the return contract is removed entirely. 1/0 still misses, so
            the guardian is still green."
    EP03m  "its positive half reads the ordinary text, which survives; its
            negative half is satisfied a fortiori."

**H.** Direction-blindness is a property of the check's PREDICATE, not of
the mutation, and it is computable STATICALLY from the check's expression
AST — no run, no mutant, no 100 s campaign. A predicate that is monotone in
"the evaluator refuses more / says more" cannot be falsified by an edit that
makes the evaluator refuse more or say more, whatever the edit is.

If H holds, round 416's central finding ("both directions guarded: 0 of 11")
stops being a campaign result about 11 mechanisms and becomes a checkable
property of all 327 `check` statements in the two guest files.

## The law

    BLIND(check, dir)  =>  NOT guarded(pin)         for a pin with that dir

Blindness is NECESSARY-condition-shaped, not sufficient: a non-blind
guardian may still be `inert` (the edit changed nothing it looks at). So the
falsifiable direction is the contrapositive — **a pin measured `guarded`
must never have a guardian the analyser calls blind in that pin's `dir`.**
One such pin refutes H.

## Banked numbers

* **B1.** Over the 30 verdicts in `state/whence/round-416/run-before.json`
  (28 pins + 2 controls), the law has **0 violations** — zero `guarded` pins
  whose guardian is classified blind in that pin's `dir`. I will accept 1 as
  a near-miss worth reporting; 2+ refutes H as stated.
* **B2.** All **5 of 5** `shadowed` pins are classified blind in their own
  `dir`. (This is the easy half — it is what the five `why` fields say.)
* **B3.** The three `+`-direction pins that round 416 measured `guarded`
  (EP03p, EP11p, EP16p) are all classified NOT `+`-blind. 3 of 3.
* **B4.** Of `self_eval.lang`'s **172** top-level checks, the share whose
  top-level predicate is one-sided (blind in at least one direction) is
  between **45% and 70%**.
* **B5.** `self_host.lang`'s **155** checks are MORE one-sided than
  `self_eval.lang`'s — a parser's checks are overwhelmingly
  `missed(...)`/`contains(...)`. Predicted gap **>= 5 percentage points**.
* **B6.** Adding one companion check per shadowed pin, with a polarity the
  analyser certifies covers the missing direction, flips the verdict
  `shadowed -> guarded`. Predicted **4 of 5** on the first attempt — I
  expect exactly one to need a second probe, on the round-414 grounds that a
  probe can agree with both rules.
* **B7.** The five new checks pass at baseline and break nothing: the guest
  file runs **177** checks, all green, and both `run_tests_fast.sh` suites
  stay at 0 failures.
* **B8.** The analyser will find at least one check in `self_eval.lang`
  that is one-sided in the direction its own LABEL names — i.e. a label that
  asserts a rule its predicate cannot see broken — that is NOT among the
  five already known. Predicted count of such newly-named cases: **>= 3**.

## What would refute H

Two or more `guarded` pins classified blind. That would mean the mutant's
behaviour leaked into the predicate by a route the polarity of the top-level
operator does not capture — which is entirely possible, because `gv(...)`
runs a whole evaluator and a monotone-looking predicate over its OUTPUT is
only monotone if the evaluator's output is.

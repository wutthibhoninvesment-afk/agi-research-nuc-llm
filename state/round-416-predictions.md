# Round 416 (language C) — predictions, banked BEFORE any pin ran

Banked per D-013. Written after reading `examples/self_eval.lang` and
`checkpin.py`, after measuring only the UNMUTATED baseline
(`python3 run.py examples/self_eval.lang` -> `checks: 166 passed, 0 failed`,
2.674 s wall), and BEFORE `state/whence/round-416/eval-pins.json` existed.

## The hypothesis this round is designed to test

Round 414 asked (its item 3, carried as round 415's next-step 7) for
"every rule with two opposite falsifying edits [to get] both of them".
This round does that, and it does it because of a specific claim:

> **A guardian is only as two-sided as its predicate.** A `check` whose
> expression is `missed(X)`, `contains(X, s)`, `len(X) > 0` or `is_guess(X)`
> is a ONE-SIDED test: it is monotone in "the evaluator misses more" / "the
> evaluator says more" / "the walk reports more". Mutating the rule in the
> direction the predicate is monotone in CANNOT make it false, however
> badly the rule is broken. A `check` whose expression is `gv(...) == V` is
> two-sided and falsifiable in both directions.

If that is right, then a mutation campaign that only ever mutates a rule in
ONE direction — which is what round 414's registry, and every mutation-test
registry I have seen in this repo, does — measures the direction the author
happened to pick, and a suite can look strong because nobody pushed the
other way.

Each mechanism below gets a `-` pin (the rule does LESS / reports less) and,
where a coherent opposite exists, a `+` pin (the rule does MORE / reports
more), judged by the SAME guardian.

## A — mechanism predictions (derivable by reading code)

- **A1.** `fn_span` locates every `fn_replace` target in `self_eval.lang`
  with no ambiguity; `locate` reports 0 `unlocatable` before the first pin
  runs. (Same claim round 414's A1 made and hit; re-stated because
  `self_eval.lang` is 2.7x the file and has ~230 guest `fn`s.)
- **A2.** At least ONE pin comes back `collapsed` or `unreached`. Round 414
  predicted this on the parser and MISSED (zero). I am predicting it again
  for a different reason: `self_eval.lang`'s own guardians are guest
  programs run BY the mutated evaluator, so an evaluator-level mutation
  (`eval_if` truthiness, `lookup` frame order) can take the harness down
  with the rule. This is the structural difference between mutating a
  parser and mutating an evaluator.
- **A3.** Wall clock: baseline 2.7 s x ~28 runs -> **70-130 s** for the
  whole campaign.
- **A4.** `n_red` runs much fatter here than on `self_host.lang`, where the
  median was 2 and the max 10. Predict **median n_red >= 3** and **at least
  one pin with n_red >= 40** (the evaluator is upstream of every one of the
  ~110 `gv(...)` checks).
- **A5.** Every `fn_replace` body I write parses. Zero `collapsed` pins are
  caused by a syntax error in MY replacement text (as opposed to by the
  mutated semantics). `locate` + a parse of the mutated source is what
  makes this cheap, and it is checked before the campaign runs.

## B — outcome predictions (the numbers)

- **B1.** Score (`guarded / (guarded + findings)`): **62-80%**, centred
  ~70%. Round 414 scored 91% on the parser. I predict LOWER here for the
  monotonicity reason above plus round 414's own explanation of its 91%
  (labels written by the round whose subject was that rule): the evaluator's
  checks are far more often behavioural (`gv(...) == 7`) and written as a
  feature demo, not as a rule pin.
- **B2.** Findings: **5-10**.
- **B3.** **Every `+`-direction pin whose guardian is one-sided is a
  finding** (`inert` or `shadowed`). Named in advance: EP07+ (`lookup`
  says MORE), EP08+ (`miss_reason_hint` says MORE), EP20+ (origin-miss
  test reports MORE origins), EP12+ (`raw_deep_eq` compares MORE things
  equal is NOT one-sided — excluded), EP17+ (primitive contract sentence
  says MORE).
- **B4.** **Every `-`-direction pin of those same mechanisms is `guarded`**
  — the same guardian, the same file, the opposite edit. If both halves of
  a pair come back the same verdict, the hypothesis is wrong and I will say
  so.
- **B5.** Both negative controls HOLD (`inert`, `n_red == 0`).
- **B6.** The round-326 pair (`check_ret`'s `"return value"` vs
  `"return value of <fn>"`) is the one place in this file where an author
  ALREADY wrote both directions as two checks. Predict **both EP15- and
  EP15+ are `guarded`** — i.e. a deliberately-written opposite pair is the
  thing that survives this test, and it is the only mechanism I expect to.
- **B7.** Of the findings, **>= 60% have a guardian whose expression is
  `contains(...)` or `missed(...)`**.
- **B8.** Checks that go red under NO pin in this registry: **70-120** of
  166. Recording the band in advance so it cannot later be published as a
  coverage number; it is a statement about a ~28-pin registry.
- **B9.** `guest_is_origin_miss` weakened to `missed(b.v)` (EP20+) is a
  finding. Both blame guardians are `contains(verdict, ...)` over a string
  built from the FIRST origin found, and adding origins cannot remove the
  one that is already there.
- **B10.** `drop_line_suffix` made the identity function (EP21) is a
  finding — no guardian in this file reads a step `detail` for equality.

## C — what I expect to be WRONG about

Round 414's scoring pattern was: everything derivable by reading code HIT,
every guessed empirical magnitude MISSED. So I expect A1/A2/A4/A5 and
B3/B4/B9/B10 (all read off the source) to fare better than B1/B2/B7/B8
(guessed rates). B1's band is the one I would bet against myself on.

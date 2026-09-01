# Round 422 (language C) — predictions, banked BEFORE the run

Banking rule **D-013**: written before `checkpin.py run` was invoked even
once on `state/whence/round-422/host-pins-plus.json`. What HAD been run at
banking time, and is therefore not a prediction:

* `checkpin.py locate` — all 21 pins locate (20 scored + 1 negative control).
* the parse-every-mutant check (round 416's A5) — 20/20 mutated sources parse.
* `polarity.py audit` — the STATIC classification: **14 of 20 scored pins are
  `mispointed`** (their guardian's blind set contains `+`), 6 are `ok`.

`polarity.py` is the predictor under test, not a measurement of the outcome.
Round 420 derived its law from round 416's data on `examples/self_eval.lang`
(the guest EVALUATOR). This round applies it, unchanged, to
`examples/self_host.lang` (the guest LEXER + PARSER) — a different file, a
different author-round, and pins written after the law rather than before it.
That is the out-of-sample test round 420 did not have.

---

## A — the law itself

**A1.** Round 420's law — `BLIND(guardian, d) => NOT guarded(pin with dir d)`
— holds on this file for **13 of the 14** statically `+`-blind pins.

**A2.** The single violation is **CP22p2**, and it is the one I planted to be
one. CP22p and CP22p2 are the SAME direction on the SAME rule under the SAME
guardian; CP22p appends after `tok_at(...)` (an append, `append_only` holds →
predicted NOT guarded) and CP22p2 inserts " here" in the middle (`append_only`
broken → predicted **guarded**). If both come back the same way the
precondition is decoration.

**A3.** No pin that `polarity` called `ok` (not provably blind) comes back
`guarded` for a reason `polarity` could have predicted — i.e. the empty blind
set is a coverage statement, not a claim of two-sidedness. Concretely I expect
**at most 2 of the 6 `ok` pins to be `guarded`**.

## B — per-pin verdicts (the falsifiable part)

| pin | predicted verdict | why |
| --- | --- | --- |
| CP03p | shadowed | `'` never appears in the guardian's probe; other rendering checks may |
| CP04p | shadowed | append to the got slot; some `==` check on a message elsewhere |
| CP22p | shadowed | append at the end; the `contains` guardian survives it |
| CP22p2 | **guarded** | middle insert breaks `append_only` |
| CP06p | shadowed | this edit IS round 414's CP07 minus edit; CP07's own check must go red |
| CP07p | **inert** | nothing in the file probes a newline inside a `[` list literal |
| CP08p | shadowed | `newline after a NAME … is still a separator` is the written opposite |
| CP09p | shadowed | the four exponent-literal checks (`1e5`, `1e-3`, `2.5E2`, `1e+2`) |
| CP10p | **guarded** | its own guardian is `==` over a token COUNT and KIND, both move |
| CP11p | shadowed | `a bad escape is reported at the backslash` |
| CP12p | shadowed | `an integer literal at the cap is accepted` |
| CP13p | shadowed | `but a comma still separates two of anything` |
| CP14p | shadowed | same |
| CP15p | shadowed | `fn def params` |
| CP16p | shadowed | `or below and` / `rescue is lowest precedence` |
| CP17p | shadowed | very broad; most parser checks go red |
| CP18p | shadowed | `fn def params` |
| CP19p | shadowed | the shape-declaration checks |
| CP20p | shadowed | `a primitive field type becomes a str spec node` |
| CP21p | shadowed | `a shape-typed field becomes a name node, not a copy` |

**B1.** Totals: **2 guarded, 17 shadowed, 1 inert, 0 redundant, 0 collapsed,
0 errors** out of 20 scored. Score **2/20 = 10%**.

**B2.** `collapsed` = 0. Every mutant parses; a mutant that makes the guest
parser refuse everything still produces `check` RECORDS, because the guest's
own test section evaluates `missed(...)` over the refusal rather than crashing.
This is the prediction most likely to be wrong, and CP17p / CP20p are where.

**B3.** At least one pin ends `inert` **with no sighted candidate**, i.e. a
genuine coverage gap in the guest suite rather than a mispointed pin. CP07p is
my nomination. Round 420's finding was that all five of its `shadowed`
verdicts were mispointed pins and none was a coverage gap; I expect this file
to be different because its `-` pins were written first and its `+` side was
never considered by anybody.

## C — replication of round 416's direction asymmetry

**C1.** Round 414 measured the `-` side of this same registry at **22 guarded,
0 findings**. With B1 (`+`: 2 guarded, 18 findings), Fisher exact two-sided on
the 2x2 gives **p < 0.001**, replicating round 416's p = 0.009 on a second,
independent guest file. I will compute it exactly rather than quote this.

**C2.** The direction effect on this file is LARGER than on the evaluator
(416: `-` 11/15 guarded vs `+` 3/14). Reason: the parser's rules are refusals
and `missed(...)` is the file's dominant guardian shape, which is `+`-blind by
construction, whereas the evaluator's guardians include many `==` on values.

## D — the lateral pins

**D1.** CP01, CP02 and CP05 (round 420's `~`) still have no mirror after this
round, and the reason is not laziness: a lateral rule's mechanism sentence
names a CHOICE between two spellings, not a quantity, so there is no order to
be monotone along. I predict that writing a `+` for them requires restating the
mechanism first, and that at least one of the three restates into a rule that
already has a pin (i.e. the lateral label is hiding a duplicate).

## E — the run itself

**E1.** Wall clock for `checkpin.py run` over 21 pins: **80–200 s** (round
420's 5 pins took 22.8 s ⇒ ~4.6 s/pin).

**E2.** The negative control **NC02p holds** (`inert`, `n_red == 0`).

**E3.** Baseline `examples/self_host.lang` is green: 155 checks, 0 failing,
0 duplicate labels.

## F — the secondary item (`parser.quote_str` vs `values._quote`)

**F1.** The two CAN be unified behind one helper, and the blocker recorded in
`whence/parser.py`'s comment ("`values._quote` also truncates to a limit") is
dischargeable by passing `limit=None`, not by copying the function.

**F2.** Unifying them changes **zero** test outcomes in
`languages/whence/tests/` — i.e. the duplication was never load-bearing. If a
test does move, it is `test_v39.py`'s bare-quote repr test, which the parser
comment already names.

## G — the record

**G1.** Round 421's next-step 7 carries three language(C) items and **two of
the three are already discharged**: `examples/self_eval.lang`'s guest
EVALUATOR was pinned by round 416 (`state/whence/round-416/eval-pins.json`,
33 pins) and `ncs_engine.py` was deleted by round 416. I predict
`state_claim_check.py` reports **0 stale** over the round-421 block anyway,
because neither item is inside its 7/12 covered set.

---

## ADDENDUM — banked after the first two runs, before CP05p was run

D1 above said the three LATERAL pins need their mechanism restated before a
`+` exists. Restating them, on paper, before measuring anything:

* **CP01/CP02** (`decision 48: a STRING in the got slot is always
  double-quoted`). As a quantity the rule is *the rendering is a re-lexable
  Whence literal*. `-` is "it is not one" (quote-switching, or CP03's no-escape
  form); `+` is "it says MORE than the literal", which is CP03p/CP04p's shape
  exactly. **Prediction: restating CP01/CP02 collapses them into the
  CP03/CP04 rendering family, which already has `+` pins — so the right answer
  is to write no new pin, and D1's second clause is confirmed.**

* **CP05** (`a NEWLINE in the got slot is prose, not a host escape`). As a
  quantity: *the newline is DESCRIBED, not spelled*. `-` is CP05's existing
  edit (spell it `'\n'`); `+` is "the description says more". That is a
  coherent opposite, so CP05 is not lateral once restated and D1's first
  clause is **wrong for one of the three**.

**Predictions for `CP05p`** (`show_tok`'s `nl` arm becomes
`"a line break (statement separator)"`), banked before it ran:

* **H1.** Verdict `shadowed`, not `guarded`: the guardian is
  `contains(str(...), "expected '=', got a line break")` and an append leaves
  the substring in place. Statically `+`-blind, `append_only`.
* **H2.** `n_red` is small — 0, 1 or 2. Every other reader of this slot in the
  file is also a `contains`.
* **H3.** If `n_red == 0` the file has NO check that can see the newline
  rendering grow, and the honest fix is a sixth killer using equality; if
  `n_red > 0` the pin is mispointed and repointing is the fix. I do not know
  which, and that is the measurement.

# `precondition-must-be-decided` — the instances, in full

Four case studies this skill was built from, split out of `SKILL.md` in
round 440 when the body crossed `skill_lint`'s 500-line B001 limit. The
steps, pitfalls and verification in `SKILL.md` are self-contained; these
are the measurements behind them, kept because each one names a mistake
that reads as reasonable until you see what it published.

## Contents

| section | the mistake it records |
|---|---|
| Round 434 | a condition named in a rule table with nothing to decide it, and a modelling rule that would invert the result if flipped |
| Round 438 (consumers) | the decider existed and the one instrument documented as running FIRST never called it |
| Round 438 (undecidable) | proving a residual class undecidable with a counterexample pair instead of widening the rule |
| Round 440 | the decider keyed on the producer for a property defined over the observer, and `broken` read as a universal when it is an existential |

### Round 434: the last precondition, and two things the first two did not teach

`kind_stable` — "the edit does not change the KIND of the observed value" —
was the third and last condition, and it stayed undecided for six rounds
because the obvious decider asks the wrong question. Written as *"did the
kind at the edit site change?"* it answers `unknown` on the one case that
mattered: the base kind set is `{bool, guess}` and the mutant's is
`{bool, miss}`, and those are not disjoint. They differ on ONE kind —
`guess` — which is the only kind the failing check actually tests.

**A decider is routed to a condition NAME; it usually also needs the
condition's PARAMETER.** `append_only` and `refusal` are yes/no properties
of an edit, so their deciders need nothing from the case but the edit.
`kind_stable` is a family of conditions indexed by a kind, and the case
knows which member it rests on. Routing stopped one level too shallow, and
the cost was six rounds of `unknown` on a decidable case. Ask, for each
condition: *is this one predicate, or a family? if a family, what does the
case know that selects the member?*

**If one modelling default carries the verdict, that default is the finding
and it needs its own test.** The kind analysis decides the case only because
Whence re-wraps `x == y` in a Guess when an operand is a Guess. Substitute
the rule any reader would write from "a comparison yields a bool" and the
verdict flips from `broken` to `holds` — which promotes the corpus's one
remaining counterexample from *excused* to STRICT and reports the
conditional law as REFUTED. That is a one-line change in a lattice nobody
would have questioned. Test it by monkeypatching the rule off and asserting
the inversion, and assert the language fact underneath by RUNNING a program,
not by asserting the model against itself.

**A decided condition can strengthen a result on BOTH diagonals.** The third
decider moved one confirming case `unknown -> holds` and one violating case
`unknown -> broken`; the contingency table went `[[9,0],[0,2]]` to
`[[10,0],[0,3]]`, Fisher p 0.0182 -> 0.0035, with no new data collected.
Predict that before you build it: a decider that decides something must move
the numbers that number-pinning tests hold, and if your prediction bank says
"one test will break" it is probably wrong.

**When the last condition gets a decider, the no-decider branch loses its
only user.** Do not delete it — it is the behaviour a fourth condition gets
on the day it is named and before it is decided. Re-pin it against a
synthetic name and add an invariant test that every condition the rule table
NAMES has a decider, so the next atom cannot arrive silently undecided.

### Round 438: the decider existed, and the other instrument never called it

Two rounds after `append_only` got a decider, a SECOND instrument over the
same registry still applied round 420's conditional blindness as if it were
absolute. Its flag was `pin.dir in guardian.blind`, full stop — and its only
precondition-aware branch was keyed on the OUTCOME:

```python
if measured.get(pin["id"]) == "guarded":
    ...  status = "precondition_broken"      # step 2, violated, in the fix's own module
```

That is step 2's prohibition, in the same file as the decider that obeys it.
The decider needed no run at all — it reads the edit text and the subject
source, both of which the reporting command already had in hand.

**The symptom is a mode-dependent answer.** The registry's acceptance
criterion named a command; that command takes an optional second argument;
and the answer moved with it:

| command | MISPOINTED | exit |
|---|---|---|
| `audit <pins.json>` | **5** | **1** |
| `audit <pins.json> <run.json>` | **0** | **0** |

The criterion's own text says it exists so that "pointing a pin at whatever
happened to go red would guarantee `guarded` and measure nothing" — and the
mode that MET it is the one that consults `guarded`. **A criterion was
satisfied precisely by the circularity it was written to forbid.** One round
evaluated the strict mode and correctly held the failure open; nothing ever
evaluated the other; both were right about the mode they ran.

Three instruments over one campaign gave three answers: 5 mispointed; 0
mispointed / 5 "false positive"; 1 excused / 4 undecided. Only the third
distinguished **decided broken** from **not decided** — i.e. only the one
that had already done step 3.

**The dangerous cell is the one nobody could reach.** Condition HOLDS +
outcome `guarded` is the law REFUTED. Hard-coding "guarded means the
condition broke" puts a refutation in the false-positive bucket — and it does
it in the pre-flight tool, the one that meets a new counterexample FIRST.
Unreachable on the archive, so it was pinned synthetically.

### Round 438: prove the residual undecidable instead of widening the rule

The pitfall below says *"say so rather than widening the rule until it
guesses."* Saying so is an argument. Round 438 made it a measurement, and it
took two twelve-line programs.

The residual was one shape: the edit rewrites a BOOLEAN CONDITION, and
`append_only` is a property of the observed TEXT. Two subject programs were
written with the SAME guardian shape and the same edit — add one disjunct to
an `or` chain — such that the decider's input is **byte-identical**:

```
structural: ((k == 'a') or (k == 'b'))  ->  (((k == 'a') or (k == 'b')) or (k == 'c'))
```

In one, the condition guards a SUFFIX: the edit appends, containment
survives, the check still passes (`append_only` holds, exit 0). In the other,
the same condition guards a SPLICE into the middle: containment is destroyed,
the check goes red (broken, exit 1).

**Same input, both answers ⇒ no rule over that input can decide it.** There
is nothing to widen *to*, and that is a fact about the analysis rather than
an admission about the analyst. It earns its own status — `undecidable`, not
`unknown` — because the two call for opposite responses: `unknown` invites
the next round to widen the rule, `undecidable` tells it not to bother.

The status stays **refutable**: exhibit a third program that breaks the
pairing and it is wrong. And it must be **narrower than the symptom that
suggested it** — "not string-shaped" covered the four boolean cases AND a
fifth whose edit adds an `if` branch, whose arms *are* observed text and
which a widening rule really could reach. Over-broadening would have retired
the one residual still worth attacking.

### Round 440: the decider was keyed on the wrong entity, and `broken` was the wrong quantifier

The round-438 section above ends by protecting one residual from an
over-broad status: an edit adding an `if` branch "whose arms *are* observed
text and which a widening rule really could reach". The widening rule does
exist. Writing it turned up something bigger, and the lesson is not about
that rule.

**Read the precondition's own definition for what it quantifies over.** The
atom table said `append_only` is *"an edge that only ever APPENDS to **the
observed text**"*. "Observed" is a two-place word. The property belongs to
the **(edit, observer) pair**, and every decider took only the edit — the
pin object carries an observer *label* that no decider reads. For an edit
that rewrites text unconditionally the distinction never shows: any observer
of the edited expression sees the same rewrite. Put the rewrite behind a
guard the edit itself introduces and the two come apart.

**The corpus already held the counterexample, in a verdict whose definition
IS a disagreement.** The measurement tool had a verdict `shadowed` — *"the
named check stayed GREEN and other checks went red"*. That is, by
definition, two observers of one edit who disagree. One registry pinned the
subject edit to a blind observer (`shadowed`), another pinned the SAME edit
to the sighted observer named in the first row's own `co_red` list
(`guarded`). Same edit, same program, opposite answers — the pair round
438's step 10 says to construct, sitting in two JSON files nobody had read
side by side. **Before writing a counterexample pair, grep the archive for a
verdict that records disagreement.** Any status meaning "this observer
missed it and another caught it" is one.

**Then the quantifier.** A three-valued decider usually ships `holds` /
`broken` / `unknown`, and the two decisions are silently different
quantifiers:

* `holds` is UNIVERSAL — every observer sees only appends — and licenses
  every inference the consumers draw from it.
* `broken` is EXISTENTIAL — there is an input on which this is not an append
  — and licenses none of them.

Consumers written against an unconditional corpus read `broken` universally.
Ours printed *"the guardian is not blind to THIS edit and the flag is a
false positive"* — about a guardian measured blind to that very edit. And
the other choice was worse: `holds` would have fired a `strict_violation`
path that had never fired in the tool's history, announcing the law refuted
by an observer whose text the edit provably rewrote. **Both available answers
published a false sentence, which is the signal that the value set is short
one member**, not that the rule needs tuning.

The fourth value (`broken_on_branch`) is the existential named: *decided as
an edit, undecided as an observation.* It is never promoted — the consumers
treat it exactly as `unknown` — so **no published number moves**. That is
the correctness argument, not a disappointment: a status that moved the
contingency table would be claiming something about an observer it never
read. What moves is the sentence printed beside the row.

**Run the counterfactual instead of arguing it.** Forcing each candidate
status into the decider's output and printing what every consumer would then
publish is ~30 lines and settles the design in one run:

```
CP03p pre=broken_on_branch -> audit undecided           | law strict=[] excused=[…]
CP03p pre=holds            -> audit strict_violation    | law strict=['CP03p']
CP03p pre=broken           -> audit precondition_broken | law excused=['CP03p', …]
```

Keep it as a test. It is the only artefact that says *why* the new status
exists in terms a later round can check.

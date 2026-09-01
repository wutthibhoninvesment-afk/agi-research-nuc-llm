---
name: precondition-must-be-decided
description: Use when a rule, law, guarantee or check is stated CONDITIONALLY — "holds provided the input is append-only / the schema is stable / the clock is monotonic" — and the condition is written down rather than computed. Symptoms: a report printing the same condition string beside every counterexample; a docstring of assumptions no code reads; counterexamples dismissed one at a time in prose; a "known limitation" list that only grows; a law with zero counterexamples where each was excused by hand; the same command answering differently with an optional argument; an `unknown` conflating "no rule fires yet" with "no rule can". Covers computing the condition from the case's own inputs (never the outcome), returning THREE values so "not established" is not "refuted", publishing strict/excused/undecided counts, validating against cases argued by hand BOTH ways, auditing every CONSUMER once a decider exists, and PROVING a class undecidable with a counterexample pair instead of widening the rule.
---

# A precondition you print is not a precondition you decided

A conditional claim has two halves. `IF P(x) THEN Q(x)` is only falsifiable
by an `x` with `P(x)` true and `Q(x)` false, so a tool that reports
counterexamples to `Q` must also say whether `P` held. Almost none do. What
ships instead is the condition as a CONSTANT beside every case:

```
*** case 17  violates the law   [precondition broken: append_only]
```

Read that line as code. `append_only` is a field on the RULE, not a decision
about case 17, and the word "broken" is a format string. It is printed for
the counterexample that refutes the law and for the one that does not, and
it is right at least once, which is why nobody notices.

Two failure modes follow, and they point opposite ways:

* **The law is stronger than it looks.** Every counterexample is excused in
  prose by whoever happened to read it, and the excuse is never wrong because
  it is never a claim. The law is unfalsifiable and its "0 violations" means
  nothing.
* **The law is weaker than it looks.** Nobody excuses anything, the
  counterexamples are counted at face value, and a real conditional law is
  reported as refuted by cases it never covered.

## The instance this came from

Round 420 of this program found that a static blindness analysis over a guest
language's tests — *this check cannot go red when the rule it names does
MORE* — is monotone along an order on what the check OBSERVES, and that the
order comes apart from the direction the mutation is labelled with. It did
the right thing: it recorded, per analysis atom, the precondition the
monotonicity rests on (`append_only`, `refusal`, `kind_stable`), and its
report printed that precondition beside every violation.

It printed `Verdict.pre` — the atom's field. Six rounds and three campaigns
later the corpus had 8 violation rows and 8 lines saying `precondition
broken`, none of which was about the edit in front of it.

Round 426 made `append_only` a function of the pin's own edit: apply the
edit, parse both versions with the language's own parser, take the shallowest
differing AST pairs, and ask whether the new string-concatenation chain has
the old one as a prefix. Result: of the 8 violation rows, **3 are decided and
every one is `broken`** — two distinct pins, including the one a human had
argued by hand two rounds earlier, reproduced on a different file without
being shown the answer — and 5 are `undecided`. The law's strict
counterexample count is 0.

**And the first version of the decider was wrong in the flattering
direction.** It called 6 edits `broken` where 2 are; all four false ones would
have EXCUSED a violation. Both bugs were in the comparison, not the rule: one
parser-set annotation slot (`Call.tail`) compared as if it were source, and a
left-associative `or` chain that grew by one element misaligning under a
pairwise descent and manufacturing two "the text was rewritten in the middle"
findings on an edit that touches no text at all. A decider that excuses
counterexamples fails silently and in the direction you want.

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

## When to use

- A rule, invariant, benchmark result or SLA is stated with a "provided
  that" / "assuming" / "as long as" clause and nothing computes the clause.
- A report prints the same assumption string on every row of a findings
  table.
- Counterexamples to a documented guarantee are being dismissed one at a
  time in review comments, commit messages or a knowledge file.
- You are about to ADD a precondition to a rule that has counterexamples.
  This is the highest-risk moment: the precondition is being introduced by
  someone who already knows which cases it must excuse.
- A "known limitations" or "does not apply when" list has grown for several
  cycles and nothing has ever moved off it.

### NOT this skill

- **`measured-exemption`** — an exemption is per-INPUT and known in advance
  ("family F may legitimately differ, skip it"); the fix is to run F anyway
  and report what differed. Here the condition is universally asserted and
  the fix is to compute it. Use both when an exemption's REASON is itself a
  conditional claim.
- **`verdict-carries-its-threshold`** — that is a stored boolean whose other
  operand was dropped. Here both operands survive; the condition was never
  evaluated at all.
- **`null-result-needs-a-power-floor`** — that is what to do AFTER the
  decider works and the surviving table is small. Expect to need it: a
  decider with low coverage produces a clean, tiny, underpowered contingency
  table (step 6).
- **`unenforced-documented-rule`** — a requirement the implementation never
  CHECKS on its inputs. Here the rule is checked; it is the rule's own escape
  clause that is not.

## Steps

1. **Find the constant.** Grep the reporting path for the assumption's name
   and confirm it is read from a rule/atom/config table rather than computed
   per case:

   ```
   $ grep -n 'precondition\|assumes\|provided that' <reporter>.py
   $ grep -n 'PRE_\|\.pre\b' <analysis>.py
   ```

   If the string reaching the report comes from the same object for every
   case, it is a constant. Confirm by finding two cases in the archive that
   should differ and checking they print the same.

2. **Write the decider as a function of the CASE'S INPUTS ONLY.** Signature
   discipline is the whole guard: it takes the case and the subject, and it
   must not be able to reach the outcome.

   ```python
   def edit_precondition(base_src, pin):   # no `run`, no `results`, no verdict
   ```

   If the outcome is unavoidable (the condition genuinely depends on what
   happened), you are not deciding a precondition — you are describing the
   result, and the law is not conditional, it is fitted.

3. **Return THREE values.** `holds` / `broken` / `undecided`. `broken` must
   be a positive finding — you can point at the thing that violates the
   condition. `undecided` is the case the analysis has no rule for. Only
   `holds` is a claim, and collapsing `undecided` into either of the other
   two is the whole failure this skill exists to prevent.

4. **Partition the counterexamples and print all three counts.** Never
   subtract silently:

   ```
   5 VIOLATION(s) …
   of those, 0 STRICT (condition established, the law is refuted here),
   1 excused (condition demonstrably broken) and 4 undecided.
   ```

   Keep the unpartitioned list too, under its old key, so anyone who
   distrusts the excuse can read the original number.

5. **Default to NOT excusing.** With no decider supplied, every
   counterexample is strict. An absent decision must never excuse anything —
   otherwise adding the parameter and forgetting to pass it silently
   validates the law.

6. **Publish the coverage denominator with the headline.** "0 strict
   violations" is meaningless without "of 8, 6 undecided". Report the
   decided share as a share, then read `null-result-needs-a-power-floor`:
   compute the minimum attainable p for the shape of the decided table
   BEFORE claiming the separation means anything. A 3-vs-2 split floors at
   p = 0.10 by Fisher exact; no re-analysis can beat it.

7. **Validate against hand-argued cases, in both directions.** Find every
   case a human already decided in prose and check the decider agrees —
   including the ones they decided the *other* way. A decider that only ever
   reproduces `broken` is a rubber stamp. The strongest validation is a
   planted PAIR: two cases identical in every field the rule reads, differing
   only in the condition (round 422 built `CP22p` / `CP22p2` — same rule,
   same guardian, same direction, one an append and one a middle insert —
   with the note *"if both come back the same way the precondition is
   decoration"*). Assert the pair in a test.

8. **Decide the remaining preconditions or scope them out loud.** A rule
   family usually has several (`refusal`, `kind_stable`, …). Deciding one and
   silently treating the others as decided is worse than deciding none. Name
   the undecided ones in the report and count their cases separately.

9. **(Round 438) Audit every CONSUMER of the condition, not just the
   reporter you fixed.** Building the decider is half the job; the other half
   is that nothing still applies the rule unconditionally. Grep for the
   blindness/applicability test itself rather than for the condition's name —
   the offender does not mention the condition, which is the point:

   ```
   $ grep -rn 'in .*\.blind\|dir in\|applies_to\|is_exempt' --include=*.py .
   $ grep -n 'def .*(' <module>.py | # then, for each, does it take pre_status?
   ```

   For each consumer ask the step-2 question again: **can it reach the
   outcome, and does it?** A consumer whose only route to the condition is a
   measured result has step 2's bug even if the decider next to it is clean.
   Then check the two must-agree properties:

   * **The answer does not move with an optional argument.** Run the command
     with and without every optional input and diff the output. If they
     differ, the answer is not a function of the subject.
   * **The consumers agree row for row.** Two instruments partitioning the
     same cases must produce the same partition. Assert it in a test; a
     divergence found later reads as a discovery instead of a regression.

10. **(Round 438) Before widening a rule to reach a residual, try to prove it
    cannot be reached.** Cheaper than widening, and it terminates.

    Take two subjects that produce the **identical** decider input and whose
    ground truth differs. Construct them: keep the analysed input fixed and
    vary only what the analysis cannot see. RUN both to establish the ground
    truth — do not derive it from the model you are testing.

    If the pair exists, the class is undecidable *by this analysis*, and it
    gets a status distinct from `unknown`. If you cannot build the pair, that
    is evidence a widening rule exists and you now know what it must
    separate. Either way you stop guessing.

    Keep the pair as fixtures and test that the rule classifies **both** — if
    a later change decides one of them, the justification for the status is
    gone and that test is what says so.

## Pitfalls

- **Comparing derived fields as if they were source.** Parsers, ORMs and
  serialisers annotate their outputs (tail-call flags, resolved types,
  interned ids, timestamps). Two structurally identical nodes compare unequal
  because a flag moved, and the decider reports a difference the subject does
  not have. Keep an explicit `DERIVED_SLOTS` set and justify each member.
- **Associative chains misalign.** `a + b + c` vs `a + b + c + d` descended
  pairwise lines `c` up against `d`. Flatten same-operator chains and compare
  as sequences; surface the whole chain when the lengths differ. Applies to
  `or`/`and`/`||` chains, middleware stacks, join lists — anything
  left-folded.
- **The decider fails toward the answer you want.** Both bugs above produced
  false `broken`, i.e. false excuses. Budget a review pass that reads every
  `broken` verdict against the case's own recorded reasoning, not a tally.
  A tally passes.
- **Syntactic deciders cannot see value flow.** An edit that changes WHICH of
  two strings is produced is decidable only when both are syntactically
  present (an `if` pinned to a literal). One that swaps a variable is
  `undecided` for ever, short of an interpreter. Say so rather than widening
  the rule until it guesses.
- **`unknown` is two answers wearing one name.** "No rule of mine fires on
  this yet" invites the next round to widen; "no rule over this input CAN"
  tells it to stop. Reported as one word, the second is re-litigated every
  few cycles at full cost. Split them — and only after you have built the
  counterexample pair, because the second is a claim.
- **(Round 438) The consumer that skips the decider does not mention the
  condition.** You will not find it by grepping the condition's name. It
  reads the applicability flag directly, and it may sit in the same module
  as the decider, written by the same round.
- **(Round 438) An acceptance criterion that names a COMMAND inherits every
  optional argument that command has.** "`tool check <file>` must report 0
  X" is not a property of the file if `tool check` takes a second argument
  that changes the answer. Pin the exact invocation, or state the property
  over the data rather than over a command line.
- **(Round 438) "0 findings" can be reached by declining to decide.** Once
  `undecided` exists, a criterion phrased as a count of the BAD status is
  satisfiable by silence. Either the criterion counts undecided too, or the
  exit code does. Round 438's audit reports `0 MISPOINTED` and exits 1,
  because four rows are open.
- **(Round 438) Excusing on an undecided condition and refuting on one are
  the same error in opposite directions.** A measured failure of the
  conclusion, with the condition undecided, is equally evidence that the
  condition broke and that the applicability analysis is wrong. Picking the
  first is the unfalsifiability the whole skill is about; picking the second
  reports a refutation you cannot support. `undecided` is the answer.
- **Coverage is the result, not an aside.** If the decider decides 20% of the
  corpus, the honest headline is about 20% of the corpus. Leading with "0
  strict violations" and burying "6 of 8 undecided" is the same failure in a
  new coat.
- **Retro-fitting the condition to the counterexamples.** If the condition is
  authored after the violations are known, have it decided by inputs only
  (step 2), validated on hand-argued cases (step 7), and state in the record
  that it was authored late.

## Verification

You have done this when all of these hold:

1. The decider's signature cannot reach an outcome. `grep` its body for the
   result/run/verdict parameter names and find nothing.
2. It returns three values and there is a test for each, including a test
   that a non-applicable case is `undecided` and NOT `broken`.
3. The reporter prints strict / excused / undecided counts, and a test
   asserts that with no decider supplied every counterexample is strict.
4. Every previously hand-argued case is covered by a test that asserts the
   decider's verdict, and at least one asserts the opposite verdict from the
   others.
5. The headline number is published with its denominator and, when the
   decided table is small, with the minimum attainable p for its shape.
6. Each remaining undecided precondition is named in the report with its own
   case count.
7. (Round 434) For each condition, the record says whether it is one
   predicate or a FAMILY indexed by a parameter, and a family's decider
   receives that parameter from the case rather than guessing it.
8. (Round 434) Any single modelling rule that, flipped, would invert a
   published verdict has a test that flips it and asserts the inversion —
   and the fact underneath that rule is asserted by RUNNING the system, not
   by asserting the model against itself.
9. (Round 434) Every condition the rule table names has a decider, asserted
   by a test; the no-decider branch survives, pinned against a synthetic
   name rather than deleted for want of a user.
10. (Round 438) Every consumer of the applicability flag takes the decider's
    output, and a test asserts that any two consumers partitioning the same
    cases agree row for row.
11. (Round 438) Running the reporting command with and without each optional
    argument produces **identical** output, asserted by a test. An optional
    input may sharpen a report; it may never decide a status.
12. (Round 438) The cell "condition HOLDS and the conclusion failed anyway"
    is reported as a REFUTATION of the conditional claim, not as a false
    positive — with a test, synthetic if the archive has no instance.
13. (Round 438) Any residual class called permanently undecidable has a
    committed counterexample PAIR whose analysed input is identical and whose
    ground truth differs, established by running both; and a test asserts the
    rule classifies both members.

Worked commands from the instance:

```
$ python3 polarity.py precondition state/whence/round-422/host-pins-plus.json
  CP22p   holds
        append: 'expected ' + what + ', got ' + …  ->  'expected ' + what + ', got ' + … + ' [parser]'
  CP22p2  broken
        infix:  'expected ' + what + ', got ' + …  ->  'expected ' + what + ' here, got ' + …
  broken 2, holds 3, unknown 18

$ python3 polarity.py law state/whence/round-422/host-pins-plus.json \
                          state/whence/round-422/run-plus-witnessed.json
  1 VIOLATION(s) …
  of those, 0 STRICT, 1 excused and 0 undecided
```

Round 438 — the consumer audit (step 9). Before: the answer moves.

```
$ python3 polarity.py audit state/whence/round-422/host-pins-plus-repointed.json
  audit: … 22 directional pin(s), 5 MISPOINTED, 0 unlocatable, 0 precondition-broken
$ echo $?
1
$ python3 polarity.py audit …/host-pins-plus-repointed.json …/run-repointed.json
  audit: … 22 directional pin(s), 0 MISPOINTED, 0 unlocatable, 5 precondition-broken
$ echo $?
0
```

After: it does not, and `undecided` is visible and costs the exit code.

```
$ python3 polarity.py audit …/host-pins-plus-repointed.json          # rc 1
  audit: … 0 MISPOINTED, 0 unlocatable, 1 precondition-broken, 4 undecided,
         0 strict-violation
  (fp) CP22p2  … the precondition is BROKEN, per the edit itself
  ( ?) CP03p   … precondition `append_only` unknown
  ( ?) CP06p   … precondition `append_only` undecidable
$ diff <(… audit PINS) <(… audit PINS RUN) && echo "modes agree"
modes agree
```

Round 438 — the undecidability pair (step 10). `state/whence/round-438/`:

```
$ python3 run.py state/whence/round-438/append-only-suffix.lang ; echo $?   # 0
$ python3 run.py state/whence/round-438/append-only-infix.lang  ; echo $?   # 0
# then apply the SAME edit (one extra `or` disjunct) to each:
$ … suffix+edit → check passes, exit 0     # append_only HOLDS
$ … infix +edit → check fails,  exit 1     # append_only BROKEN
# and the decider's input is byte-identical for both:
structural: ((k == 'a') or (k == 'b'))  ->  (((k == 'a') or (k == 'b')) or (k == 'c'))
```

# Round 426 — language(C) — the precondition that was a sentence

**Track:** language(C). **Date:** 2026-09-01.
**One line:** round 420 made its law conditional on a precondition, printed
that precondition beside every counterexample alike, and never decided it —
so the sentence could not be wrong; this round decides it from the pin's own
edit, and the law's counterexample count across the whole corpus goes to zero.

---

## 0. What this round did

Three things, in dependency order.

1. **Built a decision procedure for `append_only`** — round 420's precondition
   — as a static analysis of the pin's EDIT, in `languages/whence/polarity.py`
   (`precondition` verb, `edit_precondition`, `precondition_map`). It reads no
   verdict. Re-measured round 420's law with it on all three check-pin
   campaigns on disk: **0 strict counterexamples**, where the unconditional
   law had 8.
2. **Found and fixed a soundness bug in `audit`/`repoint`**: a coverage gap
   was defined as "no SIGHTED candidate" rather than "no candidate". Measured
   cost: 16 of 93 checks that actually went red are discarded by the filter on
   `self_host.lang`, and the tool printed *"a genuine coverage gap"* one line
   above the check that had gone red.
3. **Scored round 422's prediction bank** — the D-013 half that round never
   reached, owned by language(C) in `state/prediction-bank-ledger.json` since
   round 423. **11 HIT · 3 PARTIAL · 4 MISS of 18**, plus 16/20 on the per-pin
   table. Five of the six verdict misses are one error.

Along the way: `host-pins-plus-repointed.json` **fails its own written
acceptance criterion** (§7), nobody had run it, and a *pristine checkout* was
measured to be a different subject from the live tree in three separate places
(§9a). The reusable technique is written up as
`skills/precondition-must-be-decided/SKILL.md` (§9b).

---

## 1. The finding

`polarity.py`'s law is

```
BLIND(guardian, d)  =>  NOT guarded(pin with dir d)
```

and round 420 found it is not unconditional. Blindness is monotonicity of a
check's predicate along an order on what the check OBSERVES; `dir` records a
change to the RULE; the two come apart. So each atom carries the precondition
its monotonicity rests on — `refusal`, `append_only`, `kind_stable` — and
`law` prints it beside every violation:

```
*** CP22p2  dir +  guarded but +-blind  [contains(...)]  precondition broken: append_only
```

Read that line carefully. `append_only` is not a decision about CP22p2's
edit. It is `Verdict.pre`, i.e. the precondition of the atom `contains`, and
it is printed for **every** violation with a `contains` guardian whether the
edit appends or not. The word "broken" is a format string. Round 420's own
knowledge file argued the two violations by hand and was right about both;
what it shipped was a report that says the same thing about a violation that
refutes the law and a violation that does not. (The line above is the OLD
output. The new one prints the same words for CP22p2 — its precondition
really is broken — and `precondition unknown` for CP03p, §7. That difference
is what could not previously be seen.)

This is the shape the program keeps finding — round 423's S009, round 425's
`passed -> skipped`, round 413's named-not-measured — one sentence standing
for two different facts. It is worth naming that it survived here **because
it was true**: `append_only` really was broken for both violations round 420
had. A sentence that is right for every case it has seen is indistinguishable
from a sentence that is unconditional, and the only thing that tells them
apart is a case where it should say the other thing.

## 2. Why it is decidable, and the guest language is the reason

`examples/self_host.lang` is a Whence lexer and parser written in Whence. So
the source a pin edits can be parsed by the parser this repo ships, and
"does this edit only ever append to the observed text" becomes a question
about `+`-chains in an AST:

```
old:  "expected " + what + ", got "      + show_tok(k) + tok_at(t, p)
new:  "expected " + what + ", got "      + show_tok(k) + tok_at(t, p) + " [parser]"
        -> the old chain is a strict PREFIX of the new one          APPEND

old:  "expected " + what + ", got "      + show_tok(k) + tok_at(t, p)
new:  "expected " + what + " here, got " + show_tok(k) + tok_at(t, p)
        -> same length, a non-final atom rewritten                  INFIX
```

Those are pins **CP22p and CP22p2** of round 422's registry: the same
direction on the same rule under the same guardian, planted by that round as
a discriminator with the note *"if both come back the same way the
precondition is decoration"*. They did not — CP22p is a finding, CP22p2 is
the one `guarded` pin of the whole campaign — so the precondition is
load-bearing. It was decided by a human reading two Whence functions side by
side. Now:

```
$ python3 polarity.py precondition state/whence/round-422/host-pins-plus.json
  CP22p   holds
        append: 'expected ' + what + ', got ' + show_tok(..…  ->  'expected ' + what + ', got ' + show_tok(..…
  CP22p2  broken
        infix: 'expected ' + what + ', got ' + show_tok(..…  ->  'expected ' + what + ' here, got ' + show_t…
```

decided from the edit alone, no run.

### 2.1 The procedure

`edit_precondition(base_src, pin)`:

1. `checkpin.apply_edit(base_src, pin)` — the same function the campaign
   uses, so the mutant analysed is byte-identical to the mutant measured,
   including `also` edits.
2. Parse base and mutant with `whence.parser`.
3. `_walk_delta` collects the **shallowest** differing `(old, new)` node
   pairs. `Node.line` and `DERIVED_SLOTS` are excluded (§4).
4. `delta_kind` classifies each pair `append` / `infix` / `structural`.
5. Status: `broken` if any `infix`; `holds` if all `append`; `unknown` if
   neither (some delta is not string-shaped); plus `identity`, `unlocatable`,
   `unparsable` for the degenerate cases.

`append` is two rules, both over the flattened `+` chain: the old atom list
is a strict PREFIX of the new one, or the lists are equal but for the LAST
atom, which is a `Str` the new one extends at its end. Extending a non-final
literal is `infix` — `"a" + x + "b"` → `"a more" + x + "b"` inserts in the
middle of the rendered text even though it appends to a literal.

### 2.2 Branch selection

A pin can change *which* text is produced rather than the text. Round 420's
EP11p is exactly that: `if fn_name == "(anonymous)" { "return value" } else {
"return value of " + fn_name }` with the condition pinned `false`. Nothing is
rewritten; the observation moves branch, and the other branch is longer in the
middle. Round 420 read this by hand and called it the infix that broke
`append_only`.

`_walk_delta` special-cases it: two `If` nodes whose branches agree and whose
condition has become a `BoolLit` emit `(branch_before, branch_after)` instead
of `(cond, false)`. Without it the delta is `<Binary> -> <BoolLit>`, i.e.
structural, i.e. undecided, and the decider leaves round 420's own worked
example unexplained. With it:

```
*** EP11p   dir +  guarded but +-blind  [contains(...)]  precondition broken: append_only
      infix: 'return value'  ->  'return value of ' + fn_name
```

The procedure reproduces a human's argument on a different guest file, from a
different round, without being told the answer. That is the strongest
evidence here that it is doing analysis and not curve-fitting.

### 2.3 The honesty problem, and the three guards

A precondition that excuses counterexamples can make any law unfalsifiable.
Three guards, all in the code:

1. **It never reads a verdict.** `precondition_map(pins, src)` takes no run.
2. **Three values, not two.** `broken` is a positive finding. `unknown` is
   "the edit is not string-shaped; appending is neither established nor
   refuted". Only `holds` is a claim.
3. **`check_law` partitions and prints all three** — `strict_violations`,
   `excused`, `undecided` — and with **no** precondition map every violation
   is strict. An absent decision excuses nothing.

## 3. Measured: the law with the precondition decided

Three campaigns, everything on disk, nothing re-run:

| campaign | scored | confirmations | violations | **strict** | excused | undecided |
| --- | --- | --- | --- | --- | --- | --- |
| `self_eval.lang`, round 416 pins | 34 | 2 | 2 | **0** | 1 (EP11p) | 1 (EP10m) |
| `self_host.lang`, round 422 `plus` | 23 | 14 | 1 | **0** | 1 (CP22p2) | 0 |
| `self_host.lang`, round 422 repointed | 22 | 0 | 5 | **0** | 1 (CP22p2) | 4 |

**Round 420's law has zero strict counterexamples in the entire corpus.**
Every violation this module can decide is a broken precondition. EP10m is
`undecided` and correctly so: its precondition is `kind_stable`, which this
module does not decide at all — a scope statement, not a pass.

The law-scoped contingency, over BLIND pins only (the only pins the law makes
a claim about), all three campaigns:

```
   pre=holds     not guarded  3   guarded  0
   pre=broken    not guarded  0   guarded  3
   pre=unknown   not guarded 13   guarded  5
```

Perfect separation on the decided rows. **And it is not significant.**
Deduplicated to distinct pins (CP22p2 appears in two campaigns) the table is
`[[3,0],[0,2]]`, Fisher exact two-sided **p = 0.10** — and 0.10 is the
*minimum attainable* p for a 3-vs-2 split, so no result of this shape could
have reached 0.05. The first design that can is 4 `holds` and 4 `broken`
(p = 0.029). Two more decided pins in each cell is the whole cost of a real
result, and §11 says where to get them.

## 4. Two regressions the decider taught, both now tests

**`Call.tail` is not source.** CP04p is `str(k.v)` → `str(k.v) + " (a
number)"`, the textbook append. It came out `infix`, because moving a call out
of tail position flips the flag `parser.mark_tails` sets on it and the two
otherwise-identical `str(k.v)` nodes stopped comparing equal. `DERIVED_SLOTS`
now excludes `Call.tail`, `Block.tail_alias_tag`, `Block.tail_param_name` and
`FnExpr.param_call_fact` — every slot the parser fills as ANALYSIS rather than
as a record of what the source says.

**Left-associativity manufactures infixes.** CP06p adds one disjunct to
`t == "(" or t == "[" or t == "@{" or last_continues(acc)`. A pairwise descent
lines `"["` up against `"@{"` and `"@{"` against `"{"` and reports **two INFIX
string rewrites** — a positive `broken` finding produced entirely by
misalignment, on an edit that touches no rendered text at all. Chains of the
same operator are now compared as sequences and surfaced whole when their
lengths differ; equal-length chains are still descended pairwise, which is
where a real delta inside one disjunct is found.

Both were caught because the first run's output was read against the pins'
`why` fields rather than tallied. The first version reported `broken 6, holds
2, unknown 15`; the corrected one reports `broken 2, holds 3, unknown 18`.
**Four of the six `broken` verdicts in the first version were false**, and
every one of them would have *excused* a violation — i.e. the bug pushed in
exactly the direction that flatters the law.

## 5. Coverage, which is the binding constraint

Of 23 host pins: **3 holds, 2 broken, 18 unknown**. Of 34 evaluator pins:
2 holds, 8 broken, 24 unknown. The decider decides ~22% of the corpus.

`unknown` is not noise; it is one identifiable class. Whence renders its
messages by concatenation, so a `+`-chain edit is decidable, but most pins do
not edit a rendering at all — they replace a call with a `miss`, pin a
constant, swap a token class. For those, `append_only` is not the precondition
that matters and the honest answer is that this module has none.

So the headline of §3 has a matching bound: **0 strict violations is 0 of 8
violation rows — 3 excused, 5 undecided.** (Three rows, two distinct pins:
CP22p2 appears in both host campaigns.) The law is unrefuted, not confirmed. What moved is
that the excuse is now a computation somebody else can check, and that the two
violations the corpus can decide (EP11p, CP22p2) are decided the way the two
humans who read them by hand decided them.

## 6. A coverage gap is an empty `co_red`, not an empty sighted list

`repoint` and `audit` both keep only the co-red checks that are SIGHTED in the
pin's direction, and both then call an empty result a coverage gap. Run
against round 422's data, the old code printed this, verbatim:

```
  CP03p   dir +  shadowed   guardian +-blind=True
      named   : a quote inside a string in the got slot is escaped, so it re-lexes
      sighted : (none) — a genuine coverage gap
      blind   : a string in the got slot is a Whence literal, always double-quoted   (red, but blind in this direction — not a replacement)
```

A coverage gap means nothing in the file distinguished the mutant. The next
line names something that did. The two sentences are one line apart and they
contradict each other.

**Why the filter is wrong.** `d in blind(C)` says check `C` cannot see an edit
to the rule `C` NAMES moving in direction `d`. A co-red check names a
DIFFERENT rule; the pin's edit is not an edit to that rule in any direction,
so `C`'s monotonicity along its own rule's order has no purchase. The filter
applies a same-rule theorem across rules.

**What it costs**, measured (`polarity.py repoint` now prints it):

| campaign | red checks named | dropped by the filter | false gaps |
| --- | --- | --- | --- |
| `self_host` plus / `run-plus` | 93 | 16 (17.2 %) | CP03p |
| `self_host` plus / `run-plus-witnessed` | 99 | 18 (18.2 %) | CP03p, CP10p2 |
| `self_eval` / round 416 run | 34 | 5 (14.7 %) | none |

Round 420 worked only on the evaluator, where the false-gap count is **zero** —
which is why its finding ("all five `shadowed` verdicts are mispointed pins,
none is a coverage gap") is untouched by this. The filter drops 15 % of the
evidence there too; it just never changed an answer.

**The fix**, in `repoint()` / `audit_registry()`: a row now carries `gap`
(= `co_red` is empty), `dropped_blind`, and a distinct message for each of the
three cases. The five genuine gaps on `self_host.lang` are CP04p, CP22p,
CP07p, CP10p and CP16p — exactly the five `inert` pins — and CP03p is not one
of them. `--emit` still repoints only to sighted candidates (it is a
conservative auto-repointer) but now NAMES the pins it left alone that are not
gaps, instead of dropping them silently.

## 7. The repointed registry fails its own acceptance criterion

`state/whence/round-422/host-pins-plus-repointed.json`'s `_` field says:

> A repoint is legitimate here only when the new label names the SAME
> mechanism as the pin, on its other side; `polarity.py audit` over this file
> **must report 0 MISPOINTED**, which is the non-circular half — pointing a
> pin at whatever happened to go red would guarantee `guarded` and measure
> nothing.

```
$ python3 polarity.py audit state/whence/round-422/host-pins-plus-repointed.json
audit: examples/self_host.lang — 22 directional pin(s), 5 MISPOINTED, 0 unlocatable, 0 precondition-broken
$ echo $?
1
```

Five: CP03p, CP06p, CP08p, CP10p2, CP22p2. The command exits 1. Round 422 was
interrupted before running it; round 423 verified and landed the diff against
the pytest suite, which does not run this command; round 425 landed the rest.
The campaign is recorded as 20/20 guarded, score 1.0 — a number the registry's
own text says is guaranteed by construction and therefore means nothing, next
to the criterion that does mean something and was never read.

The registry is **hand**-repointed (its pins carry `repointed_from` and
`repoint_new_in_422`, not `repoint --emit`'s `guardian_was`), so a human
overrode the sightedness filter twenty times. §6 says the filter is wrong, so
this is not a finding against round 422's judgement — CP03p's repoint target
is a check that really did go red. It is a finding against the criterion: the
criterion and the filter are the SAME rule, and it is a category error in both
places. A repointed registry cannot be audited by asking whether the new
guardian is blind about its own rule.

There is a second reason a repointed registry is a weaker object than the pins
it came from, and round 414 wrote it first: *a check whose NAME states a
mechanism should fail when the mechanism goes*. After a repoint the guardian
no longer names the pin's mechanism — CP15p and CP18p are both repointed onto
`fn def params`, one guardian for two mechanisms. The repointed registry
measures "is this edit visible somewhere in the file", which is a real and
weaker question. `test_the_repointed_registry_fails_its_own_acceptance_criterion`
holds the failure open so it cannot be inherited again as a green result.

## 8. Round 422's prediction bank, scored

Registered `unscored`, owner `language(C)`, in
`state/prediction-bank-ledger.json` since round 423, which declined to score
it on the grounds that inventing another track's verdict is the prose-classifier
failure that ledger replaced. Scored here from
`state/whence/round-422/{run-plus,run-plus-witnessed,run-repointed,law-422,
audit-plus}.json`, `logs/round-422.json` and one `--block 421` re-run.

**18 lettered predictions: 11 HIT · 3 PARTIAL · 4 MISS. Per-pin table: 16/20.**

### 8.1 The lettered predictions

| # | claim | outcome |
| --- | --- | --- |
| A1 | law holds for 13 of the 14 statically `+`-blind pins | **HIT** — `law-422.json`: 13 confirmations, 1 violation, 14 blind |
| A2 | the single violation is CP22p2 | **HIT** |
| A3 | at most 2 of the 6 `ok` pins come back `guarded` | **HIT** — 0 of 6 |
| B1 | 2 guarded / 17 shadowed / 1 inert / 0 collapsed / 0 errors, score 10 % | **MISS** — 1 / 14 / **5** / 0 / 0, score 5 % |
| B2 | `collapsed` = 0; a mutant that refuses everything still produces `check` records | **HIT** — `collapsed` is a real ERROR verdict in `checkpin.py`; 0 of it, `errors: 0` |
| B3 | at least one pin ends `inert` with no sighted candidate — a genuine coverage gap; CP07p nominated | **HIT** — five did, CP07p among them |
| C1 | Fisher exact on the direction 2×2 gives p < 0.001, computed not quoted | **HIT** — measured `[[22,0],[1,19]]`, **p = 4.5e-11** |
| C2 | the direction effect is LARGER on the parser than on the evaluator | **HIT** — 100 % vs 5 % here; 73 % vs 21 % (p = 0.0092) there |
| D1 | CP01/CP02/CP05 still have no mirror; ≥1 of the 3 restates into a rule that already has a pin | **PARTIAL** — self-refuted in the bank's own addendum (CP05p was written); the second clause is argued, never measured |
| E1 | `checkpin run` over 21 pins takes 80–200 s | **MISS** — **40.94 s** (`logs/round-422.json`, `real 0m40.940s`, and `run-plus.json`'s 06:09:23 mtime) |
| E2 | negative control NC02p holds (`inert`, `n_red == 0`) | **HIT** — `held: true` |
| E3 | baseline green: 155 checks, 0 failing, 0 duplicate labels | **HIT** — exact |
| F1 | `quote_str` unifiable; the recorded blocker is dischargeable by `limit=None`, not by copying | **PARTIAL** — `parser.quote_str = _values_quote_str` shipped, but the comment gave TWO reasons and the second (escape sets) was a latent bug, not a blocker to discharge |
| F2 | unifying changes ZERO test outcomes; if one moves it is `test_v39`'s bare-quote repr test | **PARTIAL** — one moved, and it was exactly `test_v39` |
| G1 | `state_claim_check` reports 0 stale over the round-421 block | **MISS** — `--block 421` reports **1 stale of 8**, the S009 sentence round 423 went on to find |
| H1 | CP05p comes back `shadowed`, not `guarded` | **MISS** — `inert` |
| H2 | CP05p's `n_red` is 0, 1 or 2 | **HIT** — 0 |
| H3 | if `n_red == 0`, nothing can see the newline rendering grow and the fix is a new equality check | **HIT** — branch resolved, and CP05p's repoint target is a new check, *"…and the newline's prose is exactly that prose, not a longer sentence"* |

### 8.2 The per-pin table

Scored against `run-plus.json`, the run the bank was written for. **16 HIT,
4 MISS**, and every miss is one shape:

| pin | predicted | measured |
| --- | --- | --- |
| CP04p | shadowed | **inert** |
| CP22p | shadowed | **inert** |
| CP10p | guarded | **inert** |
| CP16p | shadowed | **inert** |

Together with H1 (predicted `shadowed`, measured `inert`) and B1 (predicted 1
inert, measured 5): **five of the six verdict misses in the whole bank are the
same error — the bank systematically under-predicted `inert`.** Its model of
the file was that the parser's 155 checks are dense enough that almost any
edit reddens something. Five of its twenty mechanisms are seen by nothing at
all.

That matters beyond the scorecard, because `inert` and `shadowed` call for
**opposite repairs** — a new check in the guest file versus one edited string
in the registry — and §6 is the same distinction being conflated one level up,
in the tool. The bank and the instrument had the same blind spot in the same
round. I am not claiming the tool caused the bank; the pins' `why` fields show
the author reasoning about which check would go red, not consulting `audit`.

### 8.3 What the bank bought

Without it, round 422's campaign reports "2 guarded of 22, p ≪ 0.001,
direction asymmetry replicated" and that is *true*. B1 and the per-pin table
are what turn a confirmed headline into the finding that the parser's guest
suite has five mechanisms nothing observes — which is the result a later round
can act on, and which nothing in the confirmed headline hints at.

## 9. Failures, and what did not work

* **The first decider was wrong in the flattering direction.** §4. Four false
  `broken` verdicts, every one of which would have excused a violation. Caught
  by reading the output against the pins' `why` fields; a tally would have
  passed.
* **`line_replace` replaces a whole LINE.** Two of the new tests were written
  with multi-line `becomes` against a one-line needle, which duplicates the
  tail of the function and yields `unparsable`. The failure mode is loud, but
  it is the second time this round's file has cost a cycle to the same fact
  (`checkpin.line_span`'s docstring records round 408 paying for it first).
* **The decider cannot see value flow.** EP11p is only decidable because its
  edit pins a condition to a literal and the branches are syntactically
  present. An edit that changes which of two *variables* is rendered is
  `structural` and always will be, short of an interpreter.
* **`kind_stable` and `refusal` are not decided at all.** `refusal` is
  probably the easier of the two — "does this edit only ever turn a value into
  a `miss`" is a question about `miss` literals in the mutant's control flow —
  and it is the precondition of `missed(...)`, the parser file's dominant
  guardian shape. It is the obvious next extension and this round did not do
  it.
* **No new check-pin campaign was run.** Everything in §3 and §6 is
  re-analysis of runs already on disk. That is deliberate — the point was to
  read artefacts nobody had read — but it means the power floor in §3 is a
  statement about what is available, not about what is obtainable.

## 9a. A pristine checkout is a different subject, measured three ways

This round took its baseline in a `git worktree` at `HEAD`, on the standing
advice that a suite launched in the live tree measures a tree that changes
under it. That advice is right and the substitution is not free. Measured,
all three in this round:

| what | live tree | `/tmp/wt-426` at HEAD | why |
| --- | --- | --- | --- |
| full whence suite | 3 skipped (fast tier) | **14 skipped** | the 14-file field corpus is in `.gitignore` (round 402) — it exists only in a working tree the Hermes gateway wrote into, so no checkout of any commit has it |
| `case_coverage.py` | 54/68 skills probed, 0 errors | **0/68 probed, 8 errors** | the trigger-eval probe reports it reads are likewise not in the checkout |
| `test_v10` / `test_v37` git-history guards | pass | pass | these DO work in a worktree — the guard round 425 found is about the mutation sandbox's `.git` exclusion, not about worktrees |

Both runs exit 0. A skip is not a failure, so the substitution turns 11
`passed` into 11 `skipped` and the pass-count comparison — 2157 vs 2104+91
deselected — invites exactly the wrong arithmetic. Round 425 found this class
(`passed -> skipped`, both sides green) in a mutation sandbox; here it arrives
through the *baseline hygiene* meant to make the measurement cleaner. **Diff
the SKIP LIST, not the pass count** — `-rs` is the flag, and it costs nothing.

The third row is included because it is the negative result: the first guess
was that the extra skips were the git-history-dependent tests, and running
those three files in the worktree (`179 passed, 1 skipped`) refuted it in two
minutes. The one skip named its own reason, which is what made this cheap:
`skills/skip-reason-is-a-claim` is the skill, and it earned its keep here.

## 9b. The reusable technique

`skills/precondition-must-be-decided/SKILL.md` (new). A conditional claim
whose condition is *printed* rather than *computed* is indistinguishable from
an unconditional one, and becomes an unfalsifiable excuse the moment it is
used to dismiss counterexamples. The recipe is §2.3 generalised: decide the
condition from the case's inputs only, return three values, partition the
counterexamples and publish all three counts plus the undecided share, default
to not excusing, and validate against cases a human already argued in BOTH
directions. NOT-scopes declared against `measured-exemption` (per-input, known
in advance), `verdict-carries-its-threshold` (a stored boolean whose other
operand was dropped), `null-result-needs-a-power-floor` (what to do after the
decider works) and `unenforced-documented-rule` (a requirement never checked on
inputs).

**Disclosed cost.** `skill_lint --house --strict` is clean (69 skills, 0
errors, 0 warnings). `case_coverage` needed 4 new entries in
`skills/trigger-cases.json` — its P001 floor is 3 positive cases and a skill
with none is an ERROR — and the skill is now the **eighth registered-unprobed**
one (P004 warning; 28 → 29 warnings, 0 errors either way, measured by removing
the directory and re-running). Its NOT-scope boundary cases are deliberately
NOT written: a case expecting `measured-exemption` would grow that skill's
positive-case denominator and make its own already-warning recall statistic
worse, which is a trade a `trigger_eval` round should make deliberately, not a
side effect of adding a neighbour.

## 10. Verification

```
$ cd languages/whence && python3 -m pytest -c pytest.ini -q tests/test_polarity.py
66 passed in 56.94s                        # 29 before, +37 this round
```

Full suite, and a PRISTINE baseline at `HEAD` (891f268) in a separate git
worktree started before any edit — the working tree changes under a suite
launched in it, which is why the baseline is not taken here:

```
UNRECOVERABLE — marked in place by round 428, not filled in.

Round 426 launched both suites in the background and died before reading
either, leaving these two template tokens in the permanent record. Round
427 found the SAME failure in round 426's `state/research-state.md` entry
(`FULL_LIVE_PLACEHOLDER`), named it as next-step item 3, and filled that
one — but round 427 looked only at `state/`, so these two, in round 426's
own knowledge file, were never named. Three tokens from one round; one
was fixed, two stood for two more rounds.

The numbers are NOT lost, they were just never pasted here: §9a above
gives them, measured and cross-tabulated — live tree 3 skipped against 14
skipped in `/tmp/wt-426` at HEAD, 2157 passed against 2104 + 91
deselected, both runs exit 0. The verbatim pytest summary lines are gone
(the logs were in `/tmp`). A later round must not manufacture them: read
§9a, which is the honest record of the same measurement.
```

```
UNRECOVERABLE — see the block above. Same cause, same round, same fix.
```

Commands whose output is in `state/whence/round-426/`:

```
$ python3 polarity.py precondition state/whence/round-422/host-pins-plus.json
  broken 2, holds 3, unknown 18
$ python3 polarity.py law state/whence/round-422/host-pins-plus.json \
                          state/whence/round-422/run-plus-witnessed.json
  14 confirmation(s) … 1 VIOLATION(s) …
  of those, 0 STRICT, 1 excused and 0 undecided
$ python3 polarity.py law state/whence/round-422/host-pins-plus-repointed.json \
                          state/whence/round-422/run-repointed.json
  0 confirmation(s) … 5 VIOLATION(s) …
  of those, 0 STRICT, 1 excused and 4 undecided
$ python3 polarity.py repoint state/whence/round-422/host-pins-plus.json \
                              state/whence/round-422/run-plus.json
  co-red evidence: 93 red check(s) named across these pins, 16 of them (17.2%)
  dropped by the sightedness filter; 1 pin(s) have a red check and NO sighted
  one (CP03p)
  5 genuine coverage gap(s) — nothing red at all: CP04p, CP22p, CP07p, CP10p, CP16p
$ python3 polarity.py audit state/whence/round-422/host-pins-plus-repointed.json ; echo $?
  … 5 MISPOINTED …
  1
$ python3 skills/skill-authoring/scripts/state_claim_check.py --block 421 \
      state/research-state.md
  1 stale of 8 checked                      # scores round 422's G1
```

No SPEC bump: `polarity.py` is instrumentation, the language is unchanged, and
`examples/self_host.lang` was not touched. Whence stays at v0.41.

## 11. What a later round should do with this

1. **Decide `refusal`.** §9. `missed(...)` is the parser file's dominant
   guardian and `refusal` is its precondition; deciding it would move a large
   share of the 18 `unknown` host pins into the decided column, which is the
   only thing that can lift §3's p = 0.10 off its floor.
2. **Write pins whose edits are decidable, on purpose.** Two more `holds` and
   two more `broken` in the law-scoped table reach p = 0.029. Round 422 built
   the CP22p/CP22p2 pair as a discriminator and it is the single most
   informative pin pair in the corpus; three more pairs of that shape is a
   cheap, designed experiment rather than a re-analysis.
3. **Re-run the `plus` campaign against the current file.** `run-plus.json`
   was measured against the 155-check `self_host.lang`; the file now has 161.
   Five of the six new checks were written *as repoint targets*, so the five
   genuine coverage gaps of §6 should have closed, and nothing has confirmed
   that they did.
4. **Take the repointed registry seriously or retire it.** §7. Its acceptance
   criterion is a category error, the campaign it scores is circular by its own
   admission, and it is the object round 420's law now looks worst against
   (0 confirmations, 5 violations). Either state what a repointed registry
   measures, or stop scoring it.

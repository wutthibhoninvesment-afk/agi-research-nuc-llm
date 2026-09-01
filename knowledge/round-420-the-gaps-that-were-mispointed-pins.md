# Round 420 (language C) — the five coverage gaps that were five mispointed pins

**Track:** C (language design / `languages/whence`).
**Carried item closed:** round 419's next-step 5 — *"Five `shadowed`
findings survive, argued but not fixed (EP03m, EP05p, EP08p, EP10p,
EP12p)"*, and the `because "<substring>"` SPEC decision, now in its sixth
round.
**Predictions:** `state/round-420-predictions.md`, written before
`polarity.py` existed and before any pin was re-run (D-013). Scored in §8,
honestly: **1 hit, 6 misses, 1 void.** The misses are the finding.

---

## 1. The headline

Round 416 ran 30 check-pins over the guest evaluator in
`examples/self_eval.lang` and ended with five `shadowed` verdicts — the
label that names the rule stayed green while other checks went red. It read
them as five coverage gaps in the guest file, argued each one in the pin's
`why` field, and wrote *"It did not touch the five surviving `shadowed`
findings"* into its own §11. Four rounds later they were still carried.

They are not coverage gaps. **All five are mispointed pins**, and in every
one of the five the file already contained a check that *did* go red and
that *is* structurally capable of seeing that direction. Re-pointing the
five guardian labels — five edited strings in a JSON registry, **zero lines
of the guest evaluator changed** — turns all five `guarded`:

```
$ CHECKPIN_JSON=state/whence/round-420/run-repointed.json \
    python3 checkpin.py run ../../state/whence/round-420/eval-pins-repointed.json
EP03m  guarded  guest miss <unbound name> names th  n_red=3   value was false
EP05p  guarded  guest if                            n_red=8   value was false
EP08p  guarded  guest return type accepts a matchi  n_red=14  value was miss: return
                                                    value of f expected num, got value
EP10p  guarded  nested guess-vs-guess equality ign  n_red=2   value was false
EP12p  guarded  guest return type rejects a mismat  n_red=9   value was false

5 pins: 5 guarded, 0 finding(s), 0 error(s), 0 redundant, score 100%

real	0m22.800s
```

Twenty-three seconds against four rounds of carry. The reason it took four
rounds is that a `shadowed` verdict's own definition — *"something in the
file distinguishes the rule; not the thing the record names"* — already says
this, and nobody read the second half.

---

## 2. The instrument: `languages/whence/polarity.py`

Round 416 argued its five findings by hand, and three of the five arguments
have the same shape:

> EP05p — *"A `missed(...)` guardian is monotone in exactly this direction."*
> EP08p — *"A `not is_num(...)` guardian is monotone in this direction by
> construction."*

That is not a fact about the mutant. It is a fact about the **predicate**,
and it is decidable from the check's expression AST with nothing running.
`polarity.py` computes, for every top-level `check` in a guest file:

```
blind(check) ⊆ {'+', '-'}
```

`'+'` means *this check cannot go red when the rule it names starts doing
MORE*. The algebra is small and it is the correct one rather than merely the
conservative one — monotonicity along a fixed order is closed under `and`
and `or`, so a conjunction is blind to `d` exactly when both conjuncts are:

| shape | blind | precondition |
| --- | --- | --- |
| `missed(E)` | `+` | `refusal` |
| `contains(A, s)`, `has(r, k)` | `+` | `append_only` |
| `is_guess(E)`, guest `is_*(E)` | `-` | `kind_stable` |
| `not P` | flip of `P` | `P`'s |
| `A and B`, `A or B` | `blind(A) ∩ blind(B)` | union |
| `==`, `!=`, `<`, `>`, `<=`, `>=` | ∅ (two-sided) | — |
| anything else | ∅, **flagged `unknown`** | — |

`blind` is a LOWER bound, so an empty set means *not shown one-sided*, not
*shown two-sided*. Every shape with no rule is reported `unknown` and the
summary prints the unknown share, because a coverage number that hides its
own denominator is round 417's failure. Measured: **1 of 172** checks in
`self_eval.lang` is `unknown` (0.6%), **0 of 155** in `self_host.lang`. The
one is `"...and n-way contrast skips the runs that agree"`, whose predicate
is a bare guest call, and it is correctly not classified.

### The population

```
$ python3 polarity.py classify examples/self_eval.lang examples/self_host.lang
examples/self_eval.lang: 172 check(s)
  one-sided         74  (43.0%)   +blind 68, -blind 6, both 0
  two-sided/unknown 98              of which unknown shape 1 (0.6%)
examples/self_host.lang: 155 check(s)
  one-sided         73  (47.1%)   +blind 52, -blind 21, both 0
  two-sided/unknown 82              of which unknown shape 0 (0.0%)
```

**147 of 327 checks (45.0%) across both self-hosting programs are blind to
one direction, and 120 of those 147 are blind to the same one** — the
evaluator doing more. That is the corpus-level form of what round 416 found
in eleven mechanisms, and it cost milliseconds instead of 104 seconds.

---

## 3. The law, and the two ways it fails

The falsifiable claim, banked before measuring:

```
BLIND(guardian, d)  =>  NOT guarded(pin)      for a pin with dir d
```

Necessary-condition-shaped: a non-blind guardian may still be `inert`. So
the refutable direction is the contrapositive — **a pin measured `guarded`
must never have a guardian the analyser calls blind in that pin's `dir`.**

Measured over round 416's 34 pins: **2 violations.** Prediction B1 said 0,
with 1 acceptable. It is a miss, and it is the round's second finding.

```
2 VIOLATION(s) — guarded although blind:
  *** EP10m  dir -  guarded but --blind  [is_guess(...)]  precondition broken: kind_stable
  *** EP11p  dir +  guarded but +-blind  [contains(...)]  precondition broken: append_only
```

Both are the same mistake made two ways: **`dir` names a change to the
RULE; polarity is monotonicity at the OBSERVATION, and they are not the
same order.**

* **EP11p — infix growth.** The guardian is
  `contains(reasons(...)[0], "return value expected num, got str")`.
  `contains` is monotone under *appending*. The `+` edit made every closure
  read as named, which turns `"return value"` into `"return value of g"` —
  the evaluator says strictly MORE, and says it **in the middle**, which
  destroys containment. Round 416's own killers were all append-shaped
  ("appending a clause the host never emits"), which is exactly why its
  argument read as general when it is not.
* **EP10m — kind change.** The guardian is `is_guess(gv(...))`, monotone
  under a rule that *accepts more*. The `-` edit made `apply_binop` delegate
  LESS, and the observed value stopped being a Guess at all — a change of
  KIND, which a positive type test sees head-on.

So every atom in the table above now carries the precondition its
monotonicity rests on, and `audit` reports a contradicted flag as
`precondition_broken` rather than dropping it. A rule that is conditional
and says so is more useful than one that is unconditional and wrong.

### Replication on the parser file

`examples/self_host.lang` is an independent registry (round 414's 23 pins)
whose run already exists, so this cost no campaign. Assigning `dir` exposed
a **third category round 416's binary axis has no room for**: three of the
23 edits are *lateral* — they swap one rendering for another of the same
size (`show_tok`'s quote-switching in CP01/CP02, `"a line break"` →
`"'\n'"` in CP05) and are neither more nor less. A lateral edit has no order
for a monotone predicate to be blind along; scoring it would invent a
verdict. That is, on inspection, the reason "re-point `self_host.lang`'s
pins both ways" has been carried for four rounds without being done.

Over the 19 genuinely directional pins, all of which round 414 measured
`guarded`, so that every flag is by construction a false positive:

```
audit: examples/self_host.lang — 19 directional pin(s), 0 MISPOINTED,
       0 unlocatable, 2 precondition-broken
  (fp) CP06  dir - statically --blind [not(contains(...))] but MEASURED guarded
  (fp) CP08  dir - statically --blind [not(contains(...))] but MEASURED guarded
```

Both `append_only`, the same precondition as EP11p. Across both registries:
**51 directional pins, 4 static false positives (7.8%), 3 of the 4 the same
precondition.** The static rule is a cheap pre-flight filter with a measured
error rate, which is what it should have been called from the start.

---

## 4. Two causes of `shadowed`, and why they need opposite repairs

Separating them is the part that actually closed the carry.

**(a) Predicate blindness.** The guardian's predicate is monotone in the
edit's direction. Static, `audit`-detectable, and the repair is a new
*predicate* over the same probe.

**(b) Probe agreement.** The probe is a value on which the original rule and
its replacement AGREE, so nothing the predicate looks at changed at all.
Round 414 found this once (pin CP02, *"the probe that agreed with both
rules"*). Invisible statically; the repair is a new *probe*, and a new
predicate over the same probe fixes **nothing**.

Round 416 attributed all five findings to monotonicity in its write-up. The
split is:

| pin | dir | guardian shape | cause |
| --- | --- | --- | --- |
| EP05p | `+` | `missed(...)` | **(a)** predicate blind |
| EP08p | `+` | `not(is_num(...))` | **(a)** predicate blind |
| EP03m | `-` | `contains(...) and not(contains(...))` — two-sided | **(b)** probe agreement |
| EP10p | `+` | `is_guess(...)` — `-`-blind, not `+`-blind | **(b)** probe agreement |
| EP12p | `-` | `missed(...) and not(contains(...))` — two-sided | **(b)** probe agreement |

Only **2 of 5** were predicate blindness. `polarity.py audit`'s recall on
the shadowed set is therefore 2/5 and its precision 2/4 — both stated,
because an instrument quoted without them is the failure this program keeps
finding.

Three of the five have a two-sided guardian and were shadowed anyway, which
is the fact that would have sent a round down the wrong repair. EP12p is the
clearest: its guardian is
`missed(gv("fn f() -> num { 1 / 0 }\nf()")) and not contains(..., "return
value of f expected")`, which round 416 itself strengthened after EP12m —
and deleting `check_ret` outright still leaves `1 / 0` missing and still
emits no gloss, so both conjuncts hold. No predicate over that probe can
see the contract's deletion, because that probe misses either way.

---

## 5. What actually fixed them: `polarity.py repoint`

A `shadowed` verdict says *the file distinguished the rule*. So the right
guardian is already in the file — it is in `co_red`. Filtering `co_red` by
polarity leaves the candidates sighted in the pin's direction:

```
$ python3 polarity.py repoint ../../state/whence/round-416/eval-pins.json \
                              ../../state/whence/round-416/run.json
repoint: 7 non-guarded directional pin(s)
  EP10p   dir +  shadowed   guardian +-blind=False
      named   : top-level == between two guesses yields a new guess
      sighted : nested guess-vs-guess equality ignores confidence
      blind   : guest == on functions misses   (red, but blind in this
                direction — not a replacement)
  ...
```

All five shadowed pins have at least one sighted, already-red candidate. The
two `redundant` pins (EP07m, EP12m) have none, which is correct — a
redundant pin reddens nothing, so there is nothing to draw from.

The tool narrows 172 checks to between 1 and 10. **The pick among them is
the author's, and is by MECHANISM**; each is recorded in `repoint_why` in
`state/whence/round-420/eval-pins-repointed.json`:

| pin | dir | was | now | why |
| --- | --- | --- | --- | --- |
| EP03m | `-` | `guest miss <BOUND name> stays plain propagation` | `guest miss <unbound name> names the miss-reason cure` | M3 is a biconditional; the `-` edit moves the UNBOUND half. The bound half agrees with the mutant either way. |
| EP05p | `+` | `guest strict if rejects 0` | `guest if` | The `+` edit refuses EVERY condition. The pair `guest if` / `guest strict if rejects 0` already spans both directions — 416 named the wrong one. |
| EP08p | `+` | `is_num rejects a guess wrapping a number` | `guest return type accepts a matching value` | `is_num` answering false for everything is invisible to a `not is_num` claim; the `-> num` contract ACCEPTING 5 is `is_num`'s positive use. |
| EP10p | `+` | `top-level == between two guesses yields a new guess` | `nested guess-vs-guess equality ignores confidence` | The named probe is two guesses, which delegate under both rules. Nested comparison is where the rules disagree. |
| EP12p | `-` | `guest return type is not re-checked over an already-missed body` | `guest return type rejects a mismatched value` | Deleting the contract satisfies a "does NOT do X" claim a fortiori. That a mismatch still misses is what deletion breaks. |

Every one of these is a mechanism whose statement is one-sided and whose
file already holds **both** halves. Round 416's `dir` axis made the pairing
visible; it did not make the pin author check that the guardian's polarity
matched the direction being pointed at it. That check is now mechanical.

---

## 6. SPEC Decision 50 — `check` gets no `because` clause

Round 414's item 2 (*should `check` carry `because "<substring>"`?*) has
been carried unanswered for six rounds. Round 416 argued against from one
case. Round 420 answers it from the corpus and closes it.

`because "<s>"` can only mean *the note contains `s`* — a note is prose and
an equality against it would be unwritable. `contains` is the canonical
`+`-blind predicate. 45.0% of the corpus's checks are already one-sided and
**120 of those 147 are blind to the same direction**, almost entirely
through `missed(...)` and `contains(...)`. A `because` clause would not add
a capability; it would take the language's most common existing failure mode
and make it the *sanctioned* way to say "and for this reason", on a keyword,
where a reader would reasonably assume the language had checked something.

The two-sided form needs no new syntax and both guest files converged on it
unprompted — `drop_line_suffix(reasons(gv(X))[0]) ==
drop_line_suffix(reasons(X)[0])`, an equality against the other
implementation's own sentence.

**Decided: no.** Written to `SPEC.md` as Decision 50, with the table.

The decision deliberately does NOT add a per-statement interpreter warning:
a check's polarity is a property of a whole suite's coverage, not of one
statement, and a per-statement diagnostic would fire on 147 correct lines.

---

## 7. Tests and suites

`languages/whence/tests/test_polarity.py` — **39 tests, 3.17 s**, fast tier
(no `whence_slow` marker needed; it parses the guest files but never runs
them). Two kinds, kept apart on purpose: hermetic SHAPE tests that pin the
monotonicity algebra, and CORPUS tests that pin the polarity of the eleven
named checks this round's conclusion rests on — so that if somebody rewrites
one of them, the test says the round-420 conclusion about it no longer
applies.

The corpus tests include the three cases that are easiest to get wrong: the
`is_*` convention is only applied to names the guest file actually DEFINES
(a corpus-derived rule that fired on unseen names would be asserting the
convention rather than using it); an unrecognised call is `unknown`, never
silently two-sided; and a lateral `~` direction is skipped rather than
scored.

```
$ bash languages/whence/run_tests_fast.sh
2052 passed, 3 skipped, 85 deselected in 119.54s        # exit 0
```

2013 → 2052 is exactly the 39 new tests. `harness/run_tests_fast.sh` and
`skills/run_checks_fast.sh`: see §9.

---

## 8. Predictions, scored

`state/round-420-predictions.md`, banked before the instrument existed.

| # | claim | measured | |
| --- | --- | --- | --- |
| B1 | 0 law violations (1 acceptable) | **2** | **MISS** |
| B2 | 5/5 shadowed pins classified blind | **2/5** | **MISS** |
| B3 | EP03p, EP11p, EP16p all NOT `+`-blind | **2/3** (EP11p is `+`-blind) | **MISS** |
| B4 | `self_eval` one-sided share 45–70% | **43.0%** | **MISS** by 2.0 pts |
| B5 | `self_host` more one-sided by ≥5 pts | **+4.1 pts** (47.1 vs 43.0) | **MISS** — direction right, magnitude short |
| B6 | 4/5 flip via new companion checks | **5/5 flipped, via re-pointing; 0 checks written** | **MISS on method** |
| B7 | 177 checks green after 5 additions | no check was added; the file still runs **172** | **VOID** |
| B8 | ≥3 newly-named one-sided-under-a-bounding-label checks | **42** (`self_eval`), 36 (`self_host`) | **HIT** |

**1 hit, 6 misses, 1 void**, and the misses carried the round:

* B1 and B3 are the same miss and it produced §3 — the law is conditional on
  a precondition, and naming the precondition is worth more than the law.
* B2 produced §4 — the two causes of `shadowed`, which round 416 had
  conflated and which need opposite repairs.
* B6 is the important one. The predicted repair (write a companion check per
  finding) was the repair round 416's §11 implied and the one this round set
  out to perform. It is the **wrong** repair for 5 of 5 cases, and had B6
  not been written down beforehand there would have been nothing to notice:
  five new checks would have gone into the guest file, the five pins would
  have gone green, and the round would have reported success while leaving
  five mispointed registry entries and five redundant checks behind.
* B4/B5 are near misses on a band I invented with no prior. Recorded at
  full precision rather than rounded into the band.

B8's heuristic (`one_sided AND label matches
`not|no|never|only|reject|refus|stay|still|miss|ignor|keep``) reads prose,
so it is a candidate list for the next campaign, not a finding. Stated as
such: 42 of `self_eval.lang`'s 74 one-sided checks and 36 of
`self_host.lang`'s 73 sit under a label that asserts a bound.

---

## 9. Artifacts

| path | what |
| --- | --- |
| `languages/whence/polarity.py` | the analyser — `classify` / `law` / `audit` / `repoint` |
| `languages/whence/tests/test_polarity.py` | 39 tests |
| `languages/whence/SPEC.md` | Decision 50 |
| `state/round-420-predictions.md` | banked before measuring (D-013) |
| `state/whence/round-420/law-416.json` | the law test over round 416's 34 pins |
| `state/whence/round-420/audit-416.json` | 2 mispointed, 2 precondition-broken |
| `state/whence/round-420/audit-414.json` | replication: 0 mispointed, 2 precondition-broken |
| `state/whence/round-420/check-pins-dir.json` | round 414's registry with `dir` assigned, 3 marked lateral |
| `state/whence/round-420/eval-pins-repointed.json` | the five, re-pointed, each with `repoint_why` |
| `state/whence/round-420/run-repointed.json` | 5 pins, 5 guarded, score 100% |
| `skills/mutate-the-rule-both-ways/SKILL.md` | upgraded — new step 6, three pitfalls, two verification obligations, the round-420 commands |

Suites (§7 for whence):

> **Filled in by round 421 (harness A), which landed this file.** Round 420
> was INTERRUPTED before it ran these two suites — the driver log records
> `round 420: turn summary {... "interrupted": true ...}` at 05:00:05 and
> then `file populated but no result entry (span well under the 3300s
> ceiling — likely a genuine crash)`. The two placeholders below were left
> unsubstituted, and the whole round's diff was still uncommitted when round
> 421 started. Round 421 did not re-run these suites AS round 420 and does
> not invent numbers for them. What the record actually holds is the
> driver's own post-round health checks, which DID run against round 420's
> tree:
>
> ```
> [2026-09-01 05:06:22] round 420: health-check PASS
>     (1065 passed, 298 deselected in 373.41s)
> [2026-09-01 05:06:22] round 420: whence-health-check PASS
>     (2052 passed, 3 skipped, 85 deselected in 354.86s)
> ```
>
> The whence figure is the one that matters for this round's claims: 2052
> passed against round 419's 2013, i.e. `+39`, which is exactly the size of
> `tests/test_polarity.py`. Round 421 re-ran that file alone and got
> `39 passed in 2.33s`.
>
> `skills-check` was RED at that timestamp (`unit_tests ERROR C001`), and
> round 421 found the cause was this round's own edit to
> `skills/copy-parity-differential/SKILL.md`: the verification fence opened
> `cd harness` and then named `tests/test_lexer.py`, which is relative to
> copyparity's `--root` (`languages/whence`) and not to the cwd. The command
> was correct; the fence made it read as `harness/tests/test_lexer.py` to a
> human and to `claim_check.py`, which resolved it against `harness/`, found
> nothing, and emitted a STALE C001. Round 421 rewrote the fence to run from
> the repo root, where the token is honestly unanchored and is skipped
> rather than mis-resolved, and verified both documented commands run.

---

## 10. What this round did NOT do

* **It did not author the `+` counterparts for `self_host.lang`'s pins.**
  Round 416 called this "the single highest-value next step for this track"
  and it is now four rounds carried. This round got as far as assigning
  `dir` to all 23 and finding that **3 are lateral**, which is a real reason
  the job is bigger than "re-point them both ways" — a lateral edit needs a
  new mechanism statement, not a mirrored one. The remaining 19 are `-`;
  writing 19 `+` counterparts is a whole round, and the `audit` output above
  says what to expect from them.
* **It did not unify `parser.quote_str` with `values._quote`** (round 408's
  item 6). Fifth round carried, untouched, and now noted in Decision 50's
  closing paragraph so it stops being invisible.
* **It did not re-run the full round-416 campaign.** The re-measurement is
  the five re-pointed pins against the current file (22.8 s); the other 25
  pins' verdicts are round 416's, unchanged, and the guest source was not
  touched, so they cannot have moved. Stated rather than assumed.
* **It did not extend `polarity.py` beyond the two guest files.** The
  analyser reads Whence `check` statements. The same monotonicity argument
  applies verbatim to `assertIn`/`assertRaises` in the Python suites, and
  `harness/swe/guardpin.py` is the instrument that would consume it — but
  nothing here parses Python, and claiming the technique transfers is not
  the same as having transferred it.
* **It did not probe the five skills registered unprobed.** skills(B).

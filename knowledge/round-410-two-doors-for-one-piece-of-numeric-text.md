# Round 410 (language C) — two doors for one piece of numeric text, and one guard for two facts

**Track:** C (language design & implementation), whence v0.40, decision 49.
**Both deliverables were next-steps items other rounds wrote and deferred**
— round 409's item 1 (the corpus guard) and round 408's item 1 (the
4001-digit lexer divergence, explicitly deferred as *"a decision about what
the language ACCEPTS"*). Neither was a patch; both were decisions.

---

## 1. The headline: a rule enforced at one door and asserted of the language

`whence/values.py` has said this since round 368, next to the constant it
justifies:

> `num()` refuses numeric TEXT past the same boundary, so the two stay
> inverses: **Whence never accepts digits it could not print back.**

The first clause names a function. The second is a claim about the
**language**. Whence has *two* ways to turn numeric text into a number:

```
let a = 999…9          a source literal   -> whence/lexer.py
num("999…9")           a runtime string   -> interp.b_num
```

Round 368 bounded the second and wrote the sentence as though it had
bounded both. `whence/lexer.py` had no digit bound at all, so at 4001
digits the language accepted text it renders only as
`<integer, 13292 bits>` — digits in, no digits out.

**The gap was visible for two rounds under the wrong heading.** v0.36
recorded a host/guest difference at large integers as a *rendering*
difference (`str` summarises past `SHOW_INT_BITS`, `repr` does not), and
decision 48 (round 408) closed exactly that by routing `parser._show`
through `show_int`. Doing so uncovered what the description had been
standing on: the guest's `lit_num` **is** `num(text)` with `pos_inf` for a
miss, so the guest *refused* what the host *accepted*.

| | 4000 digits | 4001 digits |
| --- | --- | --- |
| host `whence/lexer.py` | `<integer, 13288 bits>` | `<integer, 13292 bits>` |
| guest `lit_num` | `<integer, 13288 bits>` | **`inf`** |

Round 408 declined to patch it — correctly — and parked it as
`bench/showtok.py:KNOWN_DIVERGENT`, an executable exemption.

### Decision 49

> **Every door into a kind of value enforces that kind's rule, with the same
> sentence, in the phase the door belongs to.**

```
let a = <4001 nines>     ->  LexError at line 1, col 9      (lex time)
num("<4001 nines>")      ->  Miss                            (run time)
```

Both say the identical sentence, which is now one constant,
`values.NUM_TEXT_LIMIT_MSG` — `whence/lexer.py` gains this package's first
`import` in order to read it rather than copy it, and
`test_v40.py::test_neither_door_carries_a_copy_of_the_wording` requires the
wording to appear in `values.py` and nowhere else.

**The two failure KINDS are not an inconsistency and the spec says so.** A
literal is program *text*: refusing it is a static error, the same class as
`bad escape`, and rule 2's "no exceptions" is about **values**, not about
whether a file is a program. `num(s)` is a call on a string that may have
come from anywhere, so its refusal has to be a value carrying provenance.
Same rule, same sentence, two phases. Left unstated, a later round "fixes"
the asymmetry.

### The rule is about INTEGER text, and the non-rules are pinned

`1e400`, `<4001 nines>.5` and `1e4001` all still lex to `inf`. A float has
no digits to round-trip; `inf` is a value Whence can print; an overflowing
float literal has been `inf` since round 323 with its own test. And
`num("1e400")` remains an *out of range* MISS while the literal is `inf` —
the two doors do **not** agree about floats, which is round 350's
deliberate finding and is not being flattened here.

Both non-rules are **corpus rows and tests**, not sentences:
`float-literal-past-the-cap-is-not-refused` in the parity corpus, three
parametrised cases in `test_v40.py` §2, and two `check`s inside
`self_host.lang`. Without them the change reads as "long numeric literal is
refused", which is not the decision.

---

## 2. The finding the fix produced: closing the doors did not make the
## sentence true

Decision 49 makes the two **doors** agree with each other. It does **not**
rescue round 368's sentence, and it could not have:

* acceptance is bounded in decimal **DIGITS** — `SHOW_INT_DIGITS` = 4000;
* printing is bounded in **BITS** — `SHOW_INT_BITS` = 13287 = **3999.8**
  decimal digits.

So `9 × 4000` — 4000 digits, 13288 bits — is **accepted and printed as a
summary**. That is **43.3%** of the 4000-digit integers, and the witness is
the very literal already sitting in `bench/showtok.py`'s corpus under the
name `integer-just-under-the-cap`.

Three ways to close it. **None was taken, and the reasons are the design:**

* **Bound acceptance on bits.** The message stops being followable.
  Decision 32 says *an error that can name the fix, names it*; an author can
  count the digits in their own source and cannot count its bits.
* **Move `SHOW_INT_DIGITS` to 3999.** The sentence becomes true — and
  `parser._show`'s summarising branch, which decision 48 added *two rounds
  ago*, becomes unreachable from any source file. A rule whose only
  remaining witness is a unit test on a constructed value is weaker than the
  residual.
* **Reword the claim.** Taken. `whence/values.py` now states the rule the
  code has, and `test_v40.py` §4 measures the residual instead of repeating
  it.

**The cost of not moving the bound, measured.** Every integer literal a
source file can now carry that reaches the summarising branch has *exactly
one bit length*: the window is `[2**13287, 10**4000 - 1]` and both ends are
13288 bits. `test_the_summarising_branch_is_still_reachable_from_source`
pins both ends — so a later round that narrows acceptance by one digit goes
red, which is the point: it would be deleting decision 48's last
source-reachable witness.

**The general shape.** *A documented rule stated in one unit and enforced in
another is not made true by making its enforcers agree.* The units question
is the one to ask first, and it is cheap: compute the input that is accepted
and still violates the claim. If that input exists, the claim is wrong even
after the doors are unified.

---

## 3. The instrument that found the divergence could not witness its closure

`bench/showtok.py` compares how the two implementations **render a token**.
The fixed behaviour is that **neither side produces a token at all**.

A parity harness over *answers* is structurally incapable of seeing a case
whose right answer is to give no answer. So the exemption could not simply
be deleted from it. Instead:

* `KNOWN_DIVERGENT = []`, kept as an empty list with the history attached
  rather than removed;
* `CLOSED_DIVERGENCE_HOME = ("tests/test_lexer_guest_parity.py",
  "reject-int-literal-one-past-the-cap")` — a named pointer;
* `test_v36.py` asserts the list is empty **and** opens the named file and
  finds the case in it.

The instrument that *can* witness it is `tests/test_lexer_guest_parity.py`,
whose contract has a rejection arm — rule 1 *acceptance agrees*, rule 3 *on
rejection, message and position agree*. Those two rules are exactly the two
claims decision 49 makes, and three corpus rows now carry them. Host and
guest agree on all three, message and column included, first run.

**Predicted (M1) and confirmed.** The mechanism prediction banked before the
work said the sweep could not witness the closure because a refusal produces
no token; that is why the fix went into a *different* harness. The
generalisable form: **before you close a divergence, ask whether the
harness that reports it has a channel for the new behaviour.** An
agreement-comparing harness has no channel for "both refuse".

---

## 4. Four existing tests moved, and two of them were in a subsystem the
## change is not about

Expected: the two `test_v36.py` exemption tests.

Unexpected, and the informative pair: **`test_v39.py`'s two decision-48
tests**, which built a **4100-digit** literal to prove that
`parser._show` summarises a huge integer in the `got` slot. 4100 digits is
no longer a program. A test about **RENDERING** was reaching the renderer
through the door decision 49 closed, and nothing in its name
(`test_a_huge_literal_in_the_got_slot_honours_show_int_bits`) said so.

They are fixed by moving the fixture to `"9" * values.SHOW_INT_DIGITS` —
which is also how the one-bit window in §2 was discovered, because the
question "what is the largest literal that still summarises?" only arises
when you have to pick a new number.

**The class:** *enforcing an acceptance rule invalidates test inputs whose
subject is something else entirely.* Breakage outside the subsystem you
changed is the norm, not a surprise, and each such test is worth reading
for whether its branch is still reachable at all.

---

## 5. Deliverable A — one guard, two facts, and the state it swallowed

Round 409's next-steps item 1: the whence field corpus had **three** guards
for one fact, in three files. `curecheck.field_corpus_absent` (round 409,
all-or-nothing, *"is this the tree the gateway writes into?"*) and
`_corpus_unchanged()` **duplicated verbatim** in `test_v33.py` and
`test_v34.py` (round 395, md5 census, *"has the gateway rewritten
anything?"*). Round 409's own words: *"One helper, two predicates, one
home."*

The duplication was the visible problem. The real one is that
`_corpus_unchanged` answered two different facts with **one skip and one
sentence**:

| state of the corpus | old answer | correct answer |
|---|---|---|
| all 14 present, all as frozen | run | run |
| all present, one **rewritten** | skip *"field corpus moved: changed X"* | skip |
| **none** present (any `git worktree`) | skip *"field corpus moved: missing X"* | skip, **different reason** |
| **some** present, some gone | skip *"field corpus moved: missing X"* | **RUN, and go red** |

Two costs, and the quiet one is worse.

* **Loud.** In every `git worktree` — where all fourteen are absent because
  round 402 `.gitignore`d them, and nothing has moved — seven tests
  announced a gateway rewrite that had not happened. Round 408 read four
  such reds as a finding and spent a paragraph proving them false.
* **Quiet.** Had the gateway ever *deleted* one of the fourteen, the seven
  tests that measure that corpus would have gone **silent** about the single
  loudest thing they could discover, under a sentence saying a file had been
  rewritten. `field_corpus_drift()` would still have named it, in a file
  nobody has to read.

### The shape of the fix

Three predicates answering one fact each, in `curecheck.py`:
`field_corpus_missing` (which declared programs are not on disk),
`field_corpus_absent` (**all** of them — this checkout was never the
gateway's tree), `field_corpus_changed` (present, but not as frozen). Then
**one** decision function, `field_corpus_skip_reason`, which is the only
thing a caller uses, with two distinct reason constants. `test_v33.py` and
`test_v34.py` now read the same object; the census is parsed in one place
and its path is spelled in one place.

### The fourth state, found by a test written in the same round

`field_corpus_skip_reason` was written with **three** states, as though they
partitioned. They do not. `test_a_rewritten_corpus_does_not_hide_a_missing_
one` — written to assert an ordering I believed was already there — failed:
with one program deleted **and** another rewritten, the first draft returned
the *rewrite's* skip and buried the deletion under it. Exactly the failure
mode the split was made to prevent, reintroduced by the split.

The rule the code now carries, as the **order** of two checks:

> Two states can be true at once. Check the one whose silence costs more
> FIRST. A deletion is louder than a rewrite, because a deletion is the one
> that can be a mistake.

The order is policy and is not recoverable from the individual predicates,
so it is a comment at the branch and a test on the combined state.

### The falsification is a test now, not a scratch directory

Round 409's next-steps item 4: *"Nothing re-runs the falsification"* — that
round proved its pins red against the old code by reconstructing it in
`/tmp` and throwing it away. Here the defective helper is **quarantined in
the test file, verbatim**, taking its two paths as arguments, and two tests
assert the differential: on 13-of-14 the old helper skips and the new one
returns `None`; on 0-of-14 the old helper says *missing* and the new one
gives the absent reason. Nine lines, and the proof re-runs every fast tier.

The quarantine is **declared**, not excepted: `CENSUS_READERS` names it as a
reader with a written reason, alongside `curecheck.py` and `test_v32.py`
(the census's own integrity test), and
`test_the_census_is_parsed_in_exactly_one_place` checks the set.

---

## 6. Two pins that were satisfied by their own text

This happened **twice in one round**, in unrelated files, and it is the
sharpest transferable thing here.

1. `test_no_test_file_defines_its_own_corpus_guard_any_more` searched every
   test file for the substring `"def _corpus_unchanged"` and **matched
   itself** — the assertion's own string literal. It would have passed with
   the quarantine copy deleted. Fixed by anchoring
   (`re.compile(r"^def _corpus_unchanged\(", re.M)`) and adding a separate
   claim that the quarantine copy still exists.
2. `assert "never accepts digits it could not print back" not in values.py`
   — written to check the false claim was retracted — **failed**, because
   the retraction has to quote the claim in order to retract it. Fixed by
   asserting the ORDER: the sentence survives exactly once, and the
   retraction marker must appear before it.

> **A pin whose subject is a string is a pin the pin can satisfy.** Anchor
> the pattern, or assert an ORDER or a COUNT rather than an absence.

Same family as round 409's `OWN_RECORDS` (a checker tripping on the record
it had just written) and round 385's rule that a check which stops
measurement cannot be checked by the thing it stopped.

---

## 7. What was built

| file | change |
|---|---|
| `whence/values.py` | `NUM_TEXT_LIMIT_MSG`; the round-368 claim corrected in place, with the retraction quoting what it retracts |
| `whence/lexer.py` | the integer-literal door refuses past `SHOW_INT_DIGITS`; the module's first `import` |
| `whence/interp.py` | `b_num` says the shared sentence instead of its own copy |
| `examples/self_host.lang`, `self_eval.lang` | guest lexer's half of the rule (shared section 1054 → 1086 lines) |
| `examples/self_host.lang` | 6 new `check`s: **148 → 154** |
| `bench/showtok.py` | `KNOWN_DIVERGENT = []` + `CLOSED_DIVERGENCE_HOME` |
| `tests/test_v40.py` | **new**, 18 tests, four sections (boundary / scope / structure / residual) |
| `tests/test_lexer_guest_parity.py` | 3 corpus rows — the closure's real home |
| `tests/test_v36.py` | 2 exemption tests rewritten as closure tests |
| `tests/test_v39.py` | 2 fixtures moved off an illegal literal |
| `curecheck.py` | `field_corpus_missing` / `field_corpus_changed` / `field_corpus_skip_reason` / `field_census_names`, one census reader |
| `tests/test_field_corpus_selector.py` | 6 new tests incl. the quarantined old helper |
| `tests/test_v24.py`, `test_v32.py`, `test_v33.py`, `test_v34.py` | read the one home; two verbatim copies deleted |
| `SPEC.md` | decision 49 in the registry + `## v0.40` section |
| `skills/skip-reason-is-a-claim/` | **new skill** |
| `skills/unenforced-documented-rule/` | upgraded: the one-door variant, 4 pitfalls |

---

## 8. Verification

**Run by round 411, not by round 410.** Round 410 died at the turn cap with
this section an empty placeholder, no `research-state.md` entry, its bank
unregistered, and its entire diff uncommitted. Round 411 (skills B) picked
it up under the standing cross-track convention, verified it, scored it
(§10) and landed it. Everything below is a real run against round 410's
working tree, unmodified.

| suite | result |
|---|---|
| `languages/whence/run_tests_fast.sh` | **1977 passed, 3 skipped, 81 deselected** in 302.12s, exit 0 |
| round 409's figure, same suite | 1947 passed, 3 skipped |
| `bench/showtok.py report` | 28 snippets, 435 tokens, 29 kinds, **misaligned 0, agree 435, differ 0** |
| `skill_lint --house --strict` | 61 skill(s), 0 error(s), 0 warning(s) |

**+30 tests, and the skip count did NOT move.** Three skips before, three
after — which is A1's claim: the seven `corpus_pin` tests still RUN in the
live tree, and nothing that used to run started skipping. The +30 is
accounted for by §7's table: 18 in the new `test_v40.py`, 6 new in
`test_field_corpus_selector.py`, 3 corpus rows in
`test_lexer_guest_parity.py`, and 3 net from the `test_v36.py` rewrite of
two exemption tests into closure tests.

Decision 49 checked directly against the built interpreter:

```
let a = <4000 nines>      ->  lexes to a NUMBER
let a = <4001 nines>      ->  LexError: 4001 digits is over the 4000-digit
                              limit for numeric text
let a = 1e400             ->  lexes (float overflow -> inf, untouched)
let a = <4001 nines>.5    ->  lexes (a FLOAT; the rule is about integer text)
values.SHOW_INT_DIGITS    ->  4000
values.NUM_TEXT_LIMIT_MSG ->  present, and `whence/lexer.py` imports it
```

`curecheck.field_corpus_skip_reason` on the live tree returns `None` (run);
on an empty tree it returns the ABSENT reason, which names `.gitignore` and
`round 402` and does **not** contain the string `field corpus moved`.

## 9b. Round 411's note on §9

Round 410's honest-failures list stands as written and every item in it is
confirmed by the artifacts. One addition, visible only from outside: none
of the three self-caught errors §9 lists is contradicted by any item in
its own prediction bank. The bank predicted the shape of the *change* well
(13 of 15, §10) and predicted nothing about the round's largest in-round
discovery — that its own three-state design was wrong. That is not a
failure of the bank; it is the boundary of what a bank written before the
work can cover, and it is worth naming because the three-state error was
the most useful thing the round produced.

---

## 9. Honest failures and misses

* **The three-state design was wrong when I wrote it**, and my own test
  caught it. §5.
* **Two string pins matched their own text.** §6. Both were mine, in the
  same round, minutes apart.
* **A rename by string replacement produced `fieldfield_census_names`**,
  because `def _census_names():` contains `_census_names()`. Caught
  immediately by collection, but it is the reason `sed`-style renames want
  an anchored pattern.
* **A stray `cp` into the wrong directory** during the worktree check made
  the new one-home pin fail with five entries instead of three. The pin was
  right; the tree was dirty. Worth noting that the pin walks the whole
  subtree and therefore reports stray copies anywhere — which is a feature.
* **`bench/showtok.py` was where I first tried to put the closure.** It
  cannot hold it. Fifteen minutes to notice the harness has no rejection
  channel, and the note is now in the file itself.

---

## 10. Round 410's prediction bank, scored by round 411

D-013's second half. Round 410 banked 15 items at
`state/whence/round-410/PREDICTIONS.md` and was interrupted before scoring
any of them. Scored here from committed artifacts plus the runs in §8, in
two columns (round 407 item 3 / round 408's precedent).

Precedent for a later round scoring an interrupted one: round 374 scored
round 372's bank on exactly these terms. Every verdict below is from an
artifact or a run, never from round 410's own prose about itself.

### Outcome column — 10 HIT, 2 MISS of 12

| # | claim | verdict | evidence |
|---|---|---|---|
| A1 | seven `corpus_pin` tests still RUN in the live tree; no new skips | **HIT** | skips 3 -> 3 across +30 tests; `field_corpus_skip_reason(live)` is `None` |
| A2 | in an absent tree they skip with the ABSENT reason, not `field corpus moved` | **HIT** | reason names `.gitignore` and `round 402`; the old string is absent |
| A3 | the 13-of-14 differential passes; old helper skips, new one runs red | **HIT** | `test_field_corpus_selector.py` green in the fast tier |
| A4 | at most ONE of `test_v33.py`/`test_v34.py` can drop `hashlib` | **MISS** | `grep -c hashlib` is **0 in both**. Both dropped it. |
| A5 | whence fast tier passes, 0 failures | **HIT** | 1977 passed, 0 failed |
| B1 | 1-3 host tests break, **all** in `test_v36.py` / showtok's exemption machinery | **MISS** | 4 broke, and 2 of them are in `test_v39.py`, which the prediction excluded by name |
| B2 | 4000 digits still lexes; the bound is inclusive at 4000 | **HIT** | measured, §8 |
| B3 | `1e400` still lexes to `inf`, untouched | **HIT** | measured, §8 |
| B4 | a 4001-digit literal WITH a fraction is a float and is not refused | **HIT** | measured, §8 |
| B5 | `showtok report` stays at 0 divergent; `KNOWN_DIVERGENT` becomes empty | **HIT** | `differ 0`; `KNOWN_DIVERGENT = []` at `bench/showtok.py:144` |
| B6 | the empty list makes a test vacuous, so the TEST must change too | **HIT** | §7: two `test_v36.py` exemption tests rewritten as closure tests, plus `CLOSED_DIVERGENCE_HOME` |
| B7 | both guest files must be edited; a test pins the section byte-identical | **HIT** | both `self_eval.lang` and `self_host.lang` in the diff |

### Mechanism column — 3 HIT of 3

| # | claim | verdict |
|---|---|---|
| M1 | a renderer-parity harness cannot witness a REFUSAL, so the harness that found the divergence cannot witness its closure | **HIT** — the closure had to move out of `bench/showtok.py` to `test_lexer_guest_parity.py`, and `CLOSED_DIVERGENCE_HOME` is the note saying so |
| M2 | the ABSENT branch is load-bearing: removing it without an absent predicate re-reds round 409's `whence-fast` fix | **HIT** — the absent tree still skips, via the new predicate |
| M3 | host and `num()` can share one constant; the guest's cannot and needs a pinned literal | **HIT** — `values.NUM_TEXT_LIMIT_MSG` imported by `lexer.py`; guest side pinned by 3 new parity rows |

### The two misses are the same mistake, and it is a known one

**A4** and **B1** are both predictions about *where a change would land*,
and both are short in the same direction: they enumerated the sites the
rule's own machinery touches, and missed a site that had merely *borrowed*
the rule's boundary for an unrelated purpose. `test_v39.py` used
`"9" * 4100` as a convenient "bigger than `SHOW_INT_BITS`" fixture; it is
not part of the digit-limit machinery, so it was not on the list, and it
broke anyway.

Round 408's bank recorded a miss of the same class one round earlier
("my enumeration of affected files was short by three"). Two rounds
running, same shape:

> **An enumeration of what a rule change touches, derived from the rule,
> will miss every site that uses the rule's CONSTANT without being about
> the rule.** Grep the constant and the literal value, not the concept.

The `hashlib` miss (A4) is the small version of the same thing: the
prediction reasoned about what each file *needs* rather than grepping what
each file *uses*, and got the answer wrong for one of two files.

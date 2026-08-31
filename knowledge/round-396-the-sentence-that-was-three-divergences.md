# Round 396 — language(C): the sentence that was three divergences

*Task: round 392's next-step item 1 — "the `expected (` / `expected '{'`
quoting inconsistency … The edit is one line in `expect`; the cost is that
it changes message BODIES that `curecheck`'s `braced-block` trigger, round
354's tests and `test_parse_error_differential.py`'s wording assertions all
read. **Do it as its own change or decide explicitly not to.**"*

**Headline.** Done, as v0.35 / decision 44. Three things round 392's
one-paragraph deferral got wrong, each larger than the last:

1. **The count.** "Twenty `expect` call sites, nine quoted, eleven bare."
   There are **28**; nine pass a `what` of which only **two** quote a
   token; **19** pass no `what` at all. The bare half is three kinds, not
   one, and they want three different treatments — which is why it is not
   "one line in `expect`".
2. **The surface.** Six of the 28 sites **can never fail**. Each is
   executed on nearly every parse and has never raised, because the guard
   above it already tested the token. Only 22 renderings are observable.
   That is a measurement over 3120 programs, not a reading.
3. **The cost.** The blast radius round 392 priced was one assertion, and
   the aggregate it protects **did not move by a single case**: 39 of 51
   host/guest messages differed before the change and 39 after, with the
   identical agreeing set of twelve. The convergence that did happen was
   invisible to it.

And the finding the change was not looking for: `expected X, got Y` was
never one host/guest divergence. It is **three that share a sentence** —
want, got, hint — with three different owners. Round 354 compared whole
strings, saw one disagreement, and named one shape.

---

## 0. Pre-flight

One `claude -p`; no concurrent driver. Predictions banked cold in
`state/whence/round-396/PREDICTIONS.md` **before** any measurement, with a
§0 `OBSERVATIONS ALREADY MADE` section listing the eleven orientation facts
read while choosing the task, so nothing below is scored as foresight it
did not have. Scored in §8: **12 HIT / 3 HALF / 1 MISS / 1 unscored.**

**Round 395's whole diff was landed first.** It ran to completion per
`logs/driver.log` — 19 files, 2546 insertions — and was killed at the
3300 s outer timeout before it could commit. Its two test suites were
re-run and verified green by this round (`test_swe_toolliveness.py` 21
passed in 2.67 s; the three whence files 185 passed in 50.72 s) and
committed as `9a34b3c`, excluding the acknowledged `SECURITY.md`
escalation. This is the third consecutive round in which a predecessor's
uncommitted work was the first item of business.

CLAUDE.md's "CRITICAL MISSION" item 1 (`fold()` returns `Miss`) was checked
and **not re-opened**: round 349 adjudicated it as an argument-ORDER
documentation gap and shipped `_order_hint` in `interp.py`. It is not a
regression.

## 1. What was built

`whence/parser.py` — decision 44. `_CATEGORY_PROSE` + `_spell_want`
replace `want = what or (value if value is not None else type_)`, and
`_expect_hint`'s dispatch moves with it.

`languages/whence/bench/expectsites.py` — *what does each `expect` site
say, and can it say it?* Three commands:

| command | answers |
|---|---|
| `sites` | the classification, from `parser.py`'s own AST |
| `sweep` | per site: executions vs raises, over a pluggable corpus |
| `report` | the join, with the dead set named |

`languages/whence/tests/test_v35.py` — 29 tests, 1.6 s.
`tests/test_parse_error_differential.py` — the three-axis test (§5).
`tests/test_v22.py`, `tests/test_v24.py` — the wording assertions.
`curecheck.py` — two triggers. `SPEC.md` — decision 44 and `## v0.35`.

## 2. The rule

The message is `expected X, got Y`. v0.24 (round 360) fixed `Y`: two sites
rendered the offending token with `%r` off `tok.value`, and the EOF token's
value is Python `None`, so `let x = (1` said `expected ), got None`.

`X` was never touched. It was whatever argument `expect` was handed:

```
expected ), got '='          <- want bare, got quoted
expected '{', got 'then'     <- want quoted, two call sites away
expected NAME, got '='       <- want is an implementation identifier
```

The third is the one that matters, and nobody had named it. `NAME` is a
token type in `whence/lexer.py`. There is no program text spelled `NAME`,
so the message names an internal symbol in the slot where it is telling
somebody what to write — **the same defect as v0.24's `None`, in the other
half of the same sentence, four versions later.**

Decision 44: a `want` is either a quoted literal the author can type
verbatim, or prose. The three bare kinds are not treated alike:

| class | sites | v0.35 |
|---|---|---|
| `bare-punct` | 15 | quote — `expected ')'` |
| `bare-prose` | 7 | unchanged |
| `bare-category` | 3 | **prose** — `expected a name` |
| `quoted-token` | 2 | unchanged |
| `bare-keyword` | 1 | quote — `expected 'if'` |

Quoting a category would have been the easy uniform fix and it is wrong:
`expected 'NAME'` reads as an instruction to type it.

**It is not one line.** `_expect_hint` DISPATCHES on the spelling of
`want` — v0.34's `fn`-expression clause tested `want == "("` and now tests
`want == "'('"`. Miss that and v0.34's entire contribution goes silent
with every test still green except the two that assert the hint text.

## 3. Six of the 28 can never fail

A rendering matters only if an author can see it. `expectsites.py sweep`
patches `Parser.expect` to count EXECUTIONS against RAISES, which separates
three facts that a coverage number collapses:

```
reached      executed and raised      — a live diagnostic
never-fails  executed, never raised   — a DEAD diagnostic
unexecuted   never reached at all     — the corpus is too thin
```

Over 3120 programs — the parse-error differential's own corpus, every
example, one handwritten input per site, and **3000 single-token mutants**
of the examples:

```
$ python3 bench/expectsites.py report --mutations 3000
corpus: 3120 programs — 334 parsed, 2464 parse-error, 322 lex-error, 0 other
  reached      22
  never-fails   6
  unexecuted    0
```

The six, each with the guard that makes it unreachable:

```
parse_program  expect("EOF")       executed   334x  `stmt_list(end="EOF")` loops `while not at(end)`
block          expect("}")         executed 12809x  the same contract, with `}`
statement      expect("NAME")      executed  6948x  guarded by `peek(1).type == "NAME"`
shape_def      expect("NAME")      executed   253x  entered only on `NAME NAME =`
shape_def      expect("=")         executed   251x  the same guard tested `peek(2).type == "="`
if_expr        expect("KW","if")   executed  3765x  both callers test `at("KW","if")`
```

**`unexecuted == 0` is what earns the word "dead".** Without it the six are
merely untested, and the mutation corpus is what turns "no input in our
corpus made it fail" into a claim — it is an adversarial search for a
counterexample, and it found none.

They are kept, not deleted: each is a cheap assertion of the invariant its
guard establishes. `test_v35.py::DEAD` names all six *by their guard*
rather than by line number, so a grammar change that makes one reachable
fails there rather than shipping a message nobody chose.

## 4. What the blast radius actually was

Round 392 named three consumers. Measured:

Measured by reverting the test files to HEAD against the NEW parser, which
is the only way to see the blast radius rather than assert it:

```
$ python3 -m pytest tests/test_v22.py tests/test_v24.py \
      tests/test_parse_error_differential.py tests/test_spec_builtins.py -q
5 failed, 295 passed, 3 skipped in 5.78s
```

**Two of the three consumers round 392 named needed no edit at all:**

| named | what happened |
|---|---|
| `curecheck`'s `braced-block` trigger | **no edit.** It is `^expected '\{', got ` — already the post-change spelling. |
| the differential's wording assertions | **no edit.** `test_wording_is_still_not_a_guest_contract` asserts that `unclosed-paren` still DIFFERS, and it does — on the got half (§5). It passes untouched. |
| round 354's tests | **3 functions in `test_v22.py`, 2 in `test_v24.py`** — the whole real cost |

Plus one round 392 could not have named, `test_v23.py`'s
`startswith("expected ]")`, and two it did not: `curecheck`'s **two**
`fn-expression-*` triggers (`^expected \(, got ` → `^expected '\(', got `),
and `_expect_hint`'s own dispatch. **Total: 3 files, 6 test functions.**

The differential edits in this round's diff are therefore VOLUNTARY — the
three-axis test of §5 and the comment that re-authors round 354's claim.
Nothing forced them. `curecheck.py corpus` applies the same 4 mechanical edits to the
same 14 field programs before and after, and still fixes none of them —
round 392's baseline, unmoved.

Nothing outside `languages/whence/` is a live consumer. The bare spelling
appears in nine `knowledge/round-3*.md` lines and eight SPEC.md lines; all
of them are **historical record** — a round file says what a round saw, and
a `## v0.2x` section says what that version said. They are left alone,
exactly as v0.33's reword of the braced-block hint left v0.32's example in
place. The v0.35 section says so in one line rather than editing 17.

## 5. The sentence was three divergences

`test_parse_error_differential.py` asserts as a live fact (v0.24 rule 3)
that host and guest wording still disagrees, and names three shapes that
must still differ. The first is `unclosed-paren`: `expected )` from the
host against `expected ')'` from the guest.

Decision 44 was expected to close it. **It did not**, and the reason is the
round's best finding:

```
host  v0.34   expected ),   got end of input
guest         expected ')', got ''
host  v0.35   expected ')', got end of input
```

Ten of the 51 rejected programs produce `expected X, got Y` on both sides:

| | before | after |
|---|---|---|
| want halves agreeing | 2 of 10 | **10 of 10** |
| whole messages agreeing | 0 of 10 | 0 of 10 |
| `test_wording_is_still_not_a_guest_contract` differing | 39 of 51 | **39 of 51** |

The want half converged — **and it converged by the HOST moving.** The
guest has quoted the token it wanted since it was written; `self_eval.lang`,
`self_host.lang` and `meta.lang` each carry a `check` asserting
`expected ')'`. Round 354 recorded the disagreement without saying which
side was right. It was the guest, and no round had said so.

Every one of the ten still differs, for one of exactly two other reasons:

* the **GOT** half — the guest renders a number `'1'` and the EOF token
  `''` where the host says `1` and `end of input`. That is v0.24's `_show`,
  **which the guest never received.** A separate debt with a known owner,
  now isolated instead of bundled.
* the **HINT** — v0.22's and v0.34's clauses are host-only by design.

So `expected X, got Y` was never one divergence. Three axes, three owners,
three resolutions — and round 354 collapsed them into "wording" because it
compared whole strings.

**The aggregate could not see any of this.** 39 of 51 before, 39 after, the
same twelve agreeing names. A change that fixed eight want-halves moved the
headline number by zero. That is the general lesson: *an aggregate that
counts whole-string inequality is blind to a convergence inside the
string*, and it will report a real fix as a no-op. The axes are now pinned
separately in `test_the_want_half_of_every_shared_message_now_agrees`.

## 6. Verification

```
$ python3 -m pytest tests/test_v35.py -q
29 passed in 1.64s

$ python3 -m pytest tests/test_parse_error_differential.py -q
172 passed, 3 skipped in 7.67s

$ python3 -m pytest tests/test_v22.py tests/test_v24.py -q
120 passed in 3.58s

$ python3 curecheck.py corpus | tail -1
14 file(s): 4 parse, 4 reach a value (rc=0), 4 mechanical edit(s) applied in total

$ ./run_tests_fast.sh                       # the tier the driver reports
1812 passed, 3 skipped, 81 deselected in 88.25s (0:01:28)
```

1782 → 1812 is exactly this round's 29 `test_v35.py` tests plus the one
added to the differential.

`bench/expectsites.py` is **called from the test suite** (`test_v35.py`'s
module-scoped fixture runs `sites()` and `sweep()`), deliberately. Round
392 found `bench/ref_diff.py` dead for five rounds behind a hand-written
module tuple, and round 395 found it had published no result in 62 rounds;
a bench script with no caller is a script that rots silently. This one
cannot: if it stops importing or stops classifying, `test_v35.py` goes red
in the fast tier.

## 7. Honest failures and limits

* **The slow tier is RED, and it is not this round's doing.** The full
  suite was launched at 11:05 and killed at 50 % after ~40 min on a 1-CPU
  box under load, so round 390's item 3 / round 395's item 8 is carried for
  a **fifth** consecutive round. But the partial run plus a direct
  invocation found `test_v23.py::test_both_self_hosting_examples_still_run_green`
  failing on a **stale count pin**: it asserts `142 passed, 0 failed` for
  `examples/self_eval.lang` and the file now reports **166 passed, 0
  failed**. Every check passes; only the number is wrong. The test carries
  `@pytest.mark.whence_slow`, so the fast tier — which is what the driver's
  per-round health line reports — has never seen it. **This is round 395's
  finding one tier down**: 395 found a health log that recorded a collection
  error nobody read; this is a red test in the tier nobody runs. It is also
  a fresh instance of round 321's item 14 as round 333 rescoped it — *a line
  asserting a number that no round re-executes* — and the comment above it
  even explains the 112 → 133 arithmetic for the other file, which is what a
  re-derived number never needs. **Deliberately not fixed here**: a
  language(C) round that did not cause it should not quietly re-pin a number
  it has not accounted for, and the 24 new checks want an owner. The fast
  tier is the verification of record above.
* **A backgrounded `… | tail -45` pipeline hung** with its writer gone and
  `tail` still holding the pipe, producing a 0-byte output file — the
  `tail`/EOF backgrounded-pipe silent-drop shape rounds 296/300/303/309
  chased and round 310's item 5 still calls unconfirmed. Observed here with
  PIDs and `/proc/<pid>/fd` captured, then sidestepped by redirecting to a
  file. **Not confirmed as the same mechanism** — the writer's death is
  unexplained and no OOM record was readable — but it is the first sighting
  in this program with the process table inspected at the time.
* **The six dead sites were not deleted.** Deleting them would make the
  reachability claim load-bearing for correctness rather than for wording,
  and this round's evidence is a very hard search, not a proof.
* **`expected a name` is a wording choice.** `expected a name, got '='` for
  `let = 1` is better than `expected NAME` and is not obviously better than
  `a binding needs a name`. No corpus attests which a reader prefers, and
  this round did not measure it — the same limit round 386 named for cures.

## 8. Predictions scored — 12 HIT / 3 HALF / 1 MISS

| # | claim | verdict | actual |
|---|---|---|---|
| P1 | bare-site count is 19, not 11 | **HIT** | 28 total − 9 `what` = 19 |
| P2 | 2 of 9 quote a token; table has 3 classes | **HALF** | 2 of 9 right; **five** classes, not three |
| P3 | not one line; ≥8 lines of logic + a helper | **HIT** | `_CATEGORY_PROSE` + `_spell_want` + 2 call-site edits |
| P4 | `NAME` reachable as a bare category | **HIT** | `let = 1`, 65 raises |
| P5 | `expected EOF` unreachable | **HIT** | executed 334×, 0 raises |
| P6 | `unclosed-paren` converges; the assert fails | **HALF** | the assert failed and was re-authored, but it did **not** converge — §5 |
| P7 | differing count lands in [10, 40] | **HIT** | 39 |
| P8 | 2 curecheck triggers move, `braced-block` does not | **HIT** | exactly |
| P9 | 3-7 files, 5-25 functions fail | **HIT** | 3 files (`test_v22`, `test_v24`, `test_v23`), 6 functions |
| P10 | v22 and v24 fail, `test_spec_builtins` does not | **HIT** | `expected '{'` was already quoted |
| P11 | SPEC.md needs edits; 4-14 stale lines | **HALF** | 8 stale lines, in band — but they are historical and **need no edit**; the premise was wrong |
| P12 | ≥1 stale bare rendering outside `languages/whence/` | **HIT** | 9, all in `knowledge/` |
| P13 | no positions move; rule-2 test unedited | **HIT** | rule-2 tests passed untouched |
| P14 | full suite green, ≥1782 collected | **unscored** | the slow tier was killed — §7 |
| P15 | whole-round diff in [700, 1600] lines | **MISS** | ~1900 |
| P16 | `foreign.py:10` needs no edit | **HIT** | already quoted |
| P17 | guest needs no edit, 0 lines | **HIT** | 0 |

P9 was scored a HALF on a first pass that counted only the files this round
had edited; re-measured against HEAD it is a HIT, and the correction is
itself the round's subject — a count taken over the subject set I had
already touched rather than over the one the claim was about.

**The instructive ones are P6 and P11, and they share a shape with the
round's subject: I predicted the outcome of comparing two strings without
asking how many claims the string carried.** P6 assumed one divergence
where there were three; P11 assumed a stale quotation is a quotation
needing an edit, when a round file quoting a message it really saw is a
correct historical record. P2 and P9 are the same error one size down — I
priced a partition (3 classes, 5-25 functions) by the two or three cases I
had already looked at. P15 continues the language-round pattern: five of
the last six size predictions have missed low, and this is the second to
miss high after 392's landed.

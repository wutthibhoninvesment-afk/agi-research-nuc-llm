# Round 408 (language C) — the got slot that spoke Python

**Track:** C (language design & implementation — Whence).
**Date:** 2026-08-31. **Model:** claude-opus-5. **Box:** 1 CPU.
**Task:** round 402's next-step item **3** / round 404's item **6** —
*"`repr_str` mirrors CPython's `repr`, a coupling nobody chose … the
artefact to write first is a decision in SPEC.md, not a patch."*
Landed as Whence **v0.39 / decision 48**.
**Predictions:** banked cold in `state/whence/round-408/PREDICTIONS.md`
(23 items, with the outcome/mechanism split round 407's item 3 asked for)
before a single test, `run.py` or grep-for-a-count. Scored in §9.

---

## 0. Pre-flight

`ps aux | grep claude` showed no second driver. `git diff --cached --stat`
empty. `languages/whence/SECURITY.md` arrived ALREADY modified by
something that is not a driver round — untouched, not reverted, not
committed; **60 rounds carried**. No NUC contact of any kind; nothing
added this round opens a socket. Port 8001 never contacted.

Baseline taken FIRST, in a pristine `git worktree add --detach /tmp/wt-408
HEAD` (round 402's item-4 standing recipe), before a single edit. §8 has
the number, and it is not the one the previous round reported.

---

## 1. Headline

Round 402 named a coupling on the GUEST side: `repr_str`, sixteen lines of
`examples/self_eval.lang` that reimplement Python's `repr` including its
quote-switching rule, "a coupling nobody chose". That description is
accurate and it is looking through the wrong end. The guest mirrors
`repr` because the HOST calls it, and the host's call is one line:

```python
def _show(tok):
    if tok.type == "EOF":
        return "end of input"
    return repr(tok.value)          # ← whence/parser.py, before this round
```

`_show` fills the `Y` in `expected X, got Y` and the `X` in
`unexpected X`. Round 396 (decision 44) had already fixed the WANT half of
that exact sentence: after it a *want* is either a quoted literal the
author can type back verbatim or a category rendered as prose, never a
bare token and never an implementation identifier. **The GOT half of the
same sentence was never given the same rule**, and one line of Python was
wrong in four independent ways at once — which is why nothing that looked
at any one of them found the others.

The one worth leading with:

```
let let = 1        →  expected a name, got 'let'
let "let" = 1      →  expected a name, got 'let'
```

**Two programs, two token KINDS, eleven identical bytes.** Python quotes a
string with `'`, switching to `"` only when the value holds a `'` and no
`"` — so a KEYWORD and a STRING carrying the same three characters render
identically, in a message whose entire job is to name the token that
stopped the parse.

Nothing detected it in twelve rounds of host/guest differential work,
because the guest reimplements `_show` faithfully and round 398's parity
sweep compares the two implementations *against each other*: **parity
between two implementations of a wrong rule is still zero divergences.**

---

## 2. The four leaks, measured

| what | before | after |
| --- | --- | --- |
| STRING | `'a'` / `"a'b"` — quote chosen by INSPECTING the value | `"a"` / `"a'b"` — always |
| NEWLINE | `'\n'` (a Python escape) | `a line break` (prose) |
| NUMBER, int | every digit | `show_int` → `<integer, 13620 bits>` |
| NUMBER, float | `1.5` | `1.5` — unchanged, `values._show` agrees |
| KW / NAME / op | `repr(v)` | `'v'` — same bytes, no inspection |
| EOF | `end of input` | unchanged |

**The unspellable byte.** `repr("a\x00b")` is `'a\x00b'`, and `\x00` is
not a Whence escape and cannot be one: `whence/lexer.py:_ESCAPES` is
closed at `\n \t \r \" \\`. The parser was answering a question about the
author's source in a notation the author cannot write. Reached end to
end:

```
fn f("a<NUL>b") { 1 }   →  expected parameter name, got 'a\x00b'
```

**The integer.** `values.SHOW_INT_BITS` (13287) exists because round 368
found that rendering an unbounded integer in full turned `print` into a
raw host traceback — "in a language whose rule 2 is *no exceptions*, the
explanation crashed". `_show` had never heard of it, so:

```
fn f(<4100 nines>) { 1 }
  →  expected parameter name, got 999…9      ← 4146 characters
  →  expected parameter name, got <integer, 13620 bits>   ← 67, after
```

The one renderer in this language exempt from the language's own rule was
the parser's.

---

## 3. The hint half had the same defect, worse

`_spell` is the OTHER token renderer — the one that quotes a token back at
the author inside a *cure*. It was `'"%s"' % tok.value`: Whence's own
double quotes, and **no escaping of any kind**.

```
let a = 1 "he said \"hi\""
  → …start `"he said "hi""` on the next line     ← lexes as str, name, str
let a = 1 "back\\slash"
  → …start `"back\slash"` on the next line       ← following it is `bad escape`
```

**A hint whose instruction cannot be followed is worse than no hint.** It
is reachable from one line of ordinary source (the corpus already carries
its family as `two-stmts-one-line`), and the way `test_v39.py` verifies
the fix is by *doing what the hint says* — pasting the backticked text
onto the next line and requiring one STRING token with the original value.

So the language had **three** renderings of one idea and the parser used
neither of the good ones: `values._quote` (Whence-native, for the
runtime), `_spell` (Whence-ish, unescaped), `_show` (Python). This is the
same shape round 402 found in the two duplicate-name sentences, one level
down.

---

## 4. The decision

> **Every token a diagnostic names is either a literal the author can type
> back verbatim in Whence, or prose.**

That is decision 44's rule, applied to the other half of decision 44's own
sentence. It is not a new principle, which is the argument for it: the
round did not have to invent a position, only to notice that half of the
sentence had never received one.

`quote_str` is the renderer: escape the five characters the lexer can
spell, copy every other byte. **Round-trip exact by construction rather
than by enumeration** — the property is not "correct for printable ASCII,
checked over 18 cases against `repr()`" but "the output re-lexes to the
input", and the domain is small enough to exhaust. All **256** single-byte
values render and re-lex to themselves, 0 failures.

There is deliberately **no `\xNN` row**, and that is the whole design:
inventing one would put a spelling in the error messages that the source
language does not have, which is the defect being removed. The price is
that a diagnostic quoting a raw control byte echoes that byte. That is the
faithful answer, and the fix for an unreadable byte is to give *Whence* an
escape for it — a lexer change — not to give the error messages a private
notation.

---

## 5. What the change REMOVED, which is the load-bearing part

Decision 45 shipped with two "residuals, exempted by measurement"
(`skills/measured-exemption`: an exemption nobody measured is a shrug).
Both are gone, and **neither by testing harder**.

### 5.1 The non-printable one was exempted twice and wrong both times

v0.36's text, in `bench/showtok.py`, SPEC.md and `test_v36.py`:

> `repr` writes `\x00`; Whence's escape table can spell exactly
> `\n \t \r \" \\`, so a guest cannot write the character it would have to
> compare against, let alone render it. […] and **unreachable from
> source, because a literal cannot CONTAIN a byte it cannot spell**.

A literal cannot *escape* such a byte. It can contain one. The string
scanner's fall-through is `out.append(ch)`, guarded only against `"`, `\`
and a raw newline, so **every other byte is copied into the value
verbatim** — and a raw byte is the only way to write one.

The evidence v0.36 offered for unreachability is
`tokenize('let s = "a\\x00b"')` raising `bad escape`. That is the ESCAPE
spelling — the four characters `\`,`x`,`0`,`0` — and it is a **different
program** from the one containing a raw NUL. Measured:

```
escape spelling  →  LexError: bad escape '\x'
raw byte         →  OK, STRING value 'a\x00b'
```

This is the repo's own recurring class — round 404 item 1's *"grep for the
representation, not the name"*, round 407's Q22 — in the reachability
half of an exemption rather than in a census.

And the *first* half stopped being true the moment the `\xNN` rule went
away. Rendering an unspellable byte is now the **identity**, which a guest
can do without being able to name the byte. `bench/showtok.py`'s corpus
now carries `string-with-unspellable-byte` (NUL, BEL, ESC, DEL) and it
**agrees**. **An exemption is a rule you could not follow; the fix was to
stop having the rule.**

### 5.2 The integer one was a lexer divergence wearing a renderer's name

v0.36 described it as a rendering difference — `str` summarises past
`SHOW_INT_BITS`, `repr` does not — and decision 48 closed exactly that by
routing `_show` through `show_int`. Doing so uncovered what the
description had been standing on top of:

| | 4000 digits | 4001 digits |
| --- | --- | --- |
| host `whence/lexer.py` | `<integer, 13288 bits>` | `<integer, 13292 bits>` |
| guest `lit_num` | `<integer, 13288 bits>` | **`inf`** |

Round 368 gave `num()` a refusal past `SHOW_INT_DIGITS` (4000) and
recorded the rule as *"`num()` refuses numeric TEXT past the same
boundary, so the two stay inverses: Whence never accepts digits it could
not print back."* **That is true of `num()` and false of the lexer**,
which accepts a literal of any length. Two doors for one piece of numeric
text and only one of them enforces the rule — and the guest's `lit_num` is
`num(text)` with `pos_inf` for a miss, so it walks through the door that
refuses while `whence/lexer.py` walks through the one that does not.

The exemption's wording had said the guest renders `<integer, N bits>`
there. It never gets an integer there at all.

Closing it is a decision about what the language **accepts**, not about
how it renders, so v0.39 does not touch it. It is now
`bench/showtok.py:KNOWN_DIVERGENT` — deliberately outside `CORPUS`, so the
sweep's headline stays a clean 0 — and `test_v36.py` requires it to
**still diverge**, at that exact boundary, with the host-side mechanism
(`num` misses at 4001 digits, the lexer does not) asserted separately so
it survives any rewrite of `self_eval.lang`.

---

## 6. Two findings in the instruments

### 6.1 A check that would have stayed green

`examples/self_host.lang` carried:

```
check "a string in the got slot switches quotes when it holds a single one":
  contains(str(parse_whence(…"a'b"…)), "expected ')', got \"a'b\"")
```

Decision 48 **deleted the quote-switching rule** and that assertion still
passes — a string is now always double-quoted, so `"a'b"` comes out either
way. A check whose name states a mechanism and whose body cannot see the
mechanism go away is not a check on that mechanism. It is replaced by the
pair that CAN tell the two rules apart — a keyword and a string spelled
alike — and the evidence for the replacement is itself a test.

Same shape as `test_v34.py`'s hint census versus the differential's
(round 404 item 3), and the third instance in five rounds of *a green
test is the failure mode*.

### 6.2 A parity harness has two failure channels

`bench/showtok.py` returns the whole corpus from ONE interpreter run as a
single string joined by `SEP`, a newline, and splits it. That is safe only
while no rendering can contain a newline — which is true **exactly
because** `quote_str` escapes one.

So the single most direct plant on decision 48's renderer,
`fn quote_str(s) { s }`, does not produce a divergence the comparison can
see. It desynchronises the comparison. The v0.39 rewrite of
`test_the_sweep_can_actually_fail` hit this twice before the shape was
clear, and the answer is not to drop the plant: **a parity harness whose
records are joined by a character its subject may emit has two failure
channels, and a negative control has to name which one it expects.** The
plant now lives in its own test, asserting `misaligned` rather than
`bad`, and asserting that the misaligned set is exactly the corpus
snippets whose STRING value holds a newline.

The plants themselves were rewritten from (old_text, new_text) pairs —
Whence string literals inside Python string literals inside a
docstring-bearing test file, three levels of backslash — to *name one line
by a short needle and replace the whole line*. The old form got one plant
wrong in a way that **passed its own `lib.count(old) == 1` guard** and
then planted a real newline into a rendering.

---

## 7. Blast radius, and where my first enumeration was short

Red from the rendering change alone: **8 tests across 5 files.** I banked
1–6 across 2–4 (P12) and found 5 in 2 files by running the files I had
reasoned my way to — `test_v36.py` (4) and `test_v24.py` (1). The other
three came from running the whole tier:

| file | test | why |
| --- | --- | --- |
| `test_parse_error_differential.py` | `test_the_got_half_reaches_more_than_four_token_kinds` | pins `'\n'` for the NEWLINE slot |
| `test_self_eval.py` | `test_parser_section_matches_self_host` | the shared-section line bound, `1043 → 1054` |
| `test_examples.py` | `test_self_hosting_real_syntax` | `self_host.lang`'s check count |

The check count is round 398's item 4 / round 402's item 6 for the
**seventh** consecutive round — the same number in two files, found by
`grep -rn "145 passed"` (the NUMBER) and not by grepping any identifier.
The section bound is the same shape and has its own second copy
(`test_self_hosting.py::LIB_END`), and *that* one is not findable by
grepping a number at all: it was found by running, because the assertion
that catches a stale bound is the section's closing LINE, not its length.

`test_v24.py::test_show_is_not_spell_and_the_two_must_not_be_merged` is
worth naming separately. Its claim was that the two renderers *"disagree
on every STRING token"* — `_spell` wrote `"hi"`, `_show` wrote `'hi'`.
**That was never a reason to keep them apart; it was the defect**, stated
as an invariant and guarded for 48 rounds. They must still not be merged,
for two other reasons (a non-STRING is bare in a hint and quoted in the
got slot; only `_show` has an EOF case), and the test now says those.

### The corpus was widened before the census was re-pinned

Four programs added to `test_parse_error_differential.py`: the
keyword/string collision pair, a value holding a byte Whence cannot spell,
and a value holding a `"`. All four **agree**, so the census moves by four
on both sides:

| | v0.38 | v0.39 |
| --- | --- | --- |
| programs both reject | 64 | **68** |
| agree word for word | 46 | **50** |
| differ by a host-only hint | 18 | **18** |
| unclassified (`other`) | 0 | **0** |

The hint-only remainder being *unchanged* is the point: decision 48 moved
a rendering rule on both sides at once, which is what makes it a wording
change to the LANGUAGE rather than to one implementation.

---

## 8. Verification, and what the standing baseline recipe cannot see

Round 402's item 4 made `git worktree add --detach /tmp/wt-N HEAD` the
standing recipe for a baseline. I followed it in the first tool call. It
produced **five red tests that are not red**, and it took the whole round
to notice, because the first thing I ran in there was the wrong suite.

### The wrong suite

`bash harness/run_tests_fast.sh` in `/tmp/wt-408` → **1 failed, 960
passed, 269 deselected in 99.48 s.** That script's own header says what it
is: `pytest -q -m "not swe_slow" harness/tests/`. **It does not run
`languages/whence/tests/` at all** — so for a language(C) round it is not
a baseline, it is a different subsystem's smoke test. Three of this
round's eight red tests were invisible to it. The recipe says *run it
THERE* and does not say WHICH suite.

### The four false reds

The real baseline — the whence tier, in the same pristine worktree at
`844b3a9` — is **4 failed, 1876 passed, 10 skipped, 81 deselected**:

```
tests/test_field_corpus_selector.py::test_the_census_and_the_directory_still_agree
tests/test_field_corpus_selector.py::test_the_live_tree_has_no_drift
tests/test_field_corpus_selector.py::test_ten_of_the_fourteen_still_fail_to_parse
tests/test_v24.py::test_the_tracked_example_set_is_the_one_this_repo_decided_on
```

All four pass in the live tree. **The cause is that the 14-file field
corpus those tests read is git-IGNORED**, so it exists in the live tree
and in no worktree, ever, at any commit. Proven causally rather than
inferred: in `/tmp/wt-408`, `4 failed, 3 passed`; after copying the 14
`.lang` files in and changing nothing else, **`7 passed`**.

So the recipe that exists to make a baseline trustworthy makes four whence
tests permanently unreadable under it, and nobody had hit it because no
round had run the whence tier in a worktree — round 407 ran
`run_tests_fast.sh`, which is harness-only.

### The fifth red, which is NOT that

`harness/tests/test_pristine_check.py::test_the_round_355_finding_reproduces_end_to_end`
failed in the worktree and **passes in the live tree in 0.04 s**. Round
407 reported `944 passed, 0 failed`; 944 + its 17 new
`test_swe_abconfound.py` tests = 961 collected, of which this one now
fails. Round 407's commit touched neither `pristine_check.py` nor its
test, and this test uses a mock runner with `dirt=` passed in explicitly,
so the ignored-corpus explanation does not obviously apply. Uncharacterised;
handed to harness(A). It is in the instrument round 403 built *to make
baselines trustworthy*.

### After the change

* `bench/showtok.py report` — **28 snippets, 435 tokens, 29 token kinds,
  0 misaligned, 0 divergent** (v0.36: 25 / 417 / 29 / 0), and the corpus
  now includes the byte v0.36 called unreachable.
* All **256** single-byte values round-trip `quote_str` → `tokenize`.
* `python3 run.py examples/self_eval.lang` → **166 passed, 0 failed**.
* `python3 run.py examples/self_host.lang` → **148 passed, 0 failed**
  (145 → 148: two got-half checks change wording, three are added).
* `python3 bench/sanitisers.py check` → **9 candidates, 0 over-matching**.
* `python3 curecheck.py corpus` → 14 files, 4 parse, 4 reach a value,
  **4 mechanical edits, none fixing anything** — byte-identical to what
  round 398 recorded, which is the check that this round did not disturb
  the cure system.
* **No POSITION moved** — decision 34 rule 2 untouched, with the numbers
  in `test_v39.py::test_no_position_moved`.
* `tests/test_v39.py` — **42 tests**, new this round.
* **Whence fast tier, live tree: `1944 passed, 3 skipped, 81 deselected,
  0 failed`** in 128.09 s. The baseline at HEAD in the same tier is
  `1876 passed, 4 failed`, and all four of those pass in the live tree, so
  the honest comparison is **1880 → 1944, +64 tests**: 42 in `test_v39.py`
  and 22 from the widened differential corpus and the split `test_v36.py`
  residual tests.
* `harness/run_tests_fast.sh`, live tree: **961 passed, 269 deselected, 0
  failed** — i.e. the fifth red above does not reproduce here.
* Skills corpus: `skill_lint` **59 skills, 0 errors, 0 warnings**;
  `claim_check` **0 stale**; `state_claim_check` **0 stale**;
  `xref_check` **0 dangling in the authoritative scope**;
  `carryforward` **0 errors**.

---

## 9. Predictions, scored — outcome and mechanism in separate columns

Round 407's item 3 asked for the split, on the evidence that its own bank
was 11-of-12 on outcomes and 1-of-5 on mechanisms. Doing it prospectively:

### Outcome column — 15 HIT, 1 HALF, 2 MISS of 18

| | claim | verdict |
| --- | --- | --- |
| P1 | a raw NUL reaches a STRING token value | **HIT** |
| P3 | v0.36's "cannot reach it" clause is false as written | **HIT** |
| P4 | raw TAB/CR reach it; raw newline does not | **HIT** |
| P5 | a newline is reachable in the value via the `\n` escape | **HIT** |
| P6 | the host has TWO string renderings and they disagree | **HIT** |
| P7 | `_spell` emits text that is not a Whence literal | **HIT** |
| P8 | …and it is reachable (bet at 60/40) | **HIT** — `let a = 1 "hi"` |
| P9 | the printable-ASCII disagreement set is `{'"', "'"}` | **MISS** |
| P10 | 0–3 pre-existing corpus messages change | **HIT** — 2 |
| P12 | 1–6 tests red across 2–4 files | **MISS (low)** — 8 across 5 |
| P13 | `test_v36.py` goes red, its STRING plant a no-op | **HIT** |
| P14 | the parity sweep still reports 0 divergences | **HIT** |
| P15 | the guest renderer is ≤12 lines, fewer branches | **HALF** — 14 lines (from 16), branches 6 → 5 |
| P16 | 0 example breakages | **HIT** |
| P17 | `sanitisers.py` / `curecheck.py` need 0 changes | **HIT** |
| P18 | ≥1 of my new tests wrong on first run | **HIT** — two |
| P20 | baseline 940–950 passed, 0 failed | **MISS** — 960 passed, **1 failed** |
| P21 | it lands as v0.39 / decision 48 | **HIT** |
| P23 | no NUC contact, nothing opens a socket | **HIT** |

### Mechanism column — 3 HIT, 1 HALF of 4

| | claim | verdict |
| --- | --- | --- |
| P2 | the scanner's fall-through `out.append(ch)` is why | **HIT** |
| P11 | STRING is absent from the got slot because round 398's three programs put it elsewhere | **HIT** |
| P19 | my first enumeration is short by ≥1, *found by grepping a STRING or a number* | **HALF** — short by 3; one found by grepping the number, two found by RUNNING |
| P22 | SPEC.md already contains an adjacent decision and 48 is its straight generalisation | **HIT** — decision 44, and it is the other half of 44's own sentence |

### The two misses are worth more than the hits

**P9 is a miss about a distinction I had already drawn and then reasoned
on the wrong side of.** I predicted the body disagreement set over
printable ASCII as `{'"', "'"}`. Measured: **exactly one character, `\`**.
The `"`/`'` difference is real and it is in the OUTER QUOTE — the axis I
had separated out in the same sentence and then failed to keep separate
when betting. `_spell` escapes nothing, so its body differs from `repr`'s
on the one character `repr` escapes and `_spell` does not.

**P12 and P19 are the same miss, and P19 called it.** I enumerated the
affected files by reasoning about who reads `_show`, got 2 of 5, and
banked a base rate saying I would. What P19 got wrong is the *mechanism*
of the correction: I predicted the missing ones would be found by grepping
a string or a number, and one of three was. The other two were found by
running the tier — and the more useful of those,
`test_self_hosting.py::LIB_END`, **is not findable by grepping anything**,
because the assertion that catches it compares the section's closing LINE.
A base rate that predicts you will be short is not the same as a method
for not being short; the method is the tier.

**P20 is a miss about the tree, not about my change**, and it is the one
that produced §8's finding. I anchored on round 407's reported baseline
and it does not describe the commit round 407 made.

---

## 10. The `CRITICAL MISSION` block in CLAUDE.md is stale, both halves

CLAUDE.md carries an operator-written block headed **"🔴 CRITICAL MISSION:
PRODUCTION FIX (Round ~350 Focus)"** with two items. Both were checked
this round, on the working tree, because a standing directive that is
already satisfied quietly costs every future round the time to re-read it.

**Item 1 — "`fold()` returns `Miss` instead of calculated values when
using inline lambdas or external functions. Needs deep code inspection in
`whence/interp.py`."**

```
fold(fn(acc, x) { acc + x }, 0, nums)   →  6          ← the documented order
fold(nums, 0, fn(acc, x) { acc + x })   →  miss       ← the reported one
```

The signature is **function first** — `fold(fn, acc, xs)`, like `map(fn,
xs)` and `filter(fn, xs)` — and written that way it folds inline lambdas
and named functions alike. This was answered by **round 349** and is
already in SPEC.md, which also records what the report actually exposed: a
documentation gap, not a defect, and the miss was already exact about the
symptom (`fold needs a list, got <fn>`). v0.22's `_order_hint` was added
for it and the message now ends `(arguments fit fold(fn, acc, xs))`.

**Item 2 — "Strict Syntax Enforcement: Parser requires explicit `{}`
blocks for all `if/else` branches in v0.19. Document this strictly and
consider auto-fixing older scripts."**

```
let y = if true 1 else 2
  →  expected '{', got 1 (blocks are always braced: `if c { a } else { b }`,
     `fn f(x) { x }`) at line 1, col 17
```

Enforced, documented as decision 33 / v0.23, carrying a cure that names
the shape — and `curecheck.py` is the machinery for the "auto-fixing
older scripts" half, running 14 field programs through the mechanical
edits their own cures imply every round.

Neither item was edited: CLAUDE.md is the operator's file and its
`## Ground rules` / `## Track E` sections are load-bearing (round 346).
Reported here and carried into the next steps instead. Note also that the
block's *"Target Model: Claude Opus-5"* line is the standing model policy
of this program since round 333, so that half is current.

---

## 11. What this round deliberately does NOT do

* It does not touch the **host-only HINT class** (18 of 68). Round 402's
  item 1 asks for a SPEC decision arguing either way and that is still
  the right first artefact.
* It does not unify `parser.quote_str` with `values._quote`, the RUNTIME's
  Whence-native string renderer. The two differ in two ways that matter to
  a diagnostic — `values._quote` truncates to a `limit` and does not
  escape `\t` or `\r` — and both are pinned in
  `test_v39.py::test_the_language_has_one_string_rendering_rule_and_two_implementations`
  so a round that unifies them knows exactly what it is changing.
* It does not close the **4001-digit lexer divergence** (§5.2).
* It does not give the guest a cure system, and rule 3 is unchanged.
* It does not touch `harness/`, `nuc/`, `CHANGELOG.md` (gateway-owned) or
  `languages/whence/SECURITY.md` (escalated, 60 rounds).

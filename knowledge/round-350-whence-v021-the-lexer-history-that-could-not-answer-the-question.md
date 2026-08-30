# Round 350 — language(C): Whence v0.21, the lexer history that could not answer the question

**Track:** C (language design & implementation).
**Subject:** `languages/whence/whence/lexer.py`, `run.py`,
`examples/self_eval.lang`, `examples/self_host.lang`,
`tests/test_lexer_guest_parity.py`, `SPEC.md`.
**Date:** 2026-08-30. Model `claude-opus-5`.

**Answers:** round 332's next-steps item 1, verbatim — *"an exhaustive sweep
of `whence/lexer.py`'s full history against the guest `lex` function"* —
carried unchanged for **16 rounds**, with round 348 saying a 17th carry was
the worst available option.

**Headline.** The sweep takes five minutes and cannot possibly answer the
question, and finding out *why* is the round. `whence/lexer.py` has three
revisions in git: the initial commit, which is the whole file and has no
parent to diff against, and two semantic diffs, **both already mirrored**.
A diff-driven audit therefore covers two lines of a two-hundred-line lexer.
Replacing it with the instrument that can settle parity — compare what the
two lexers DO — found **seven defects in one sitting**, including an
uncaught Python `ValueError` escaping `tokenize()` on a one-character
source file, and a CLI that has never honoured the lex half of its own
documented exit codes.

Shipped as **v0.21**, host and guest, with the whole thing pinned by a new
differential that runs every round.

---

## 0. Pre-flight

`ps -eo pid,ppid,etime,cmd` showed exactly one round-350 driver tree — this
round's ([[feedback_check_for_concurrent_rounds]]). `git diff --cached
--stat` was empty ([[feedback_check_cached_diff_before_commit]]).

The record-gap check opened with one unattributed path,
`languages/whence/SECURITY.md`. That is **round 349's escalation, not a
leftover**: a separate autonomous system (the Hermes gateway) rewrote a
TRACKED file to assert four security controls that do not exist in this
repo, and round 349 deliberately left it uncommitted and unrewritten for an
operator decision, keeping it out of `known-standing-dirty-paths.json` on
the principle that allowlisting a tracked file means "never look at this
diff again". Re-verified unchanged this round; **not touched**, and the
escalation is carried forward in the next steps.

The CLAUDE.md `🔴 CRITICAL MISSION` block naming two v0.19 "defects" is
**already discharged** — rounds 348 (§7.1) and 349 (§5) both tested both
claims independently and found neither is a bug (`fold` is `fold(fn, acc,
xs)`; `if`/`else` have taken blocks since v0.1), and round 349 fixed the
real defect underneath the first one, which was that SPEC.md gave the
argument order for none of its 36 builtins. Nothing left for this round
there, and re-deriving it a third time would have been the waste.

## 1. Doing the sweep, and what it proves

```
$ git log --follow --format='%h %ad %s' --date=short \
      -- languages/whence/whence/lexer.py
7b3afcb 2026-08-29 Round 323 (SWE-loop D): … exponent-literal lexer bug …
8d92ff9 2026-08-26 Round 144 (language C): reconcile v0.12/v0.13 backlog …
ee30654 2026-08-25 Initial clean commit v3. …
```

Three revisions. The diffs:

| commit | change | mirrored in the guest? |
| --- | --- | --- |
| `ee30654` | the entire file, as an initial commit | not a diff at all |
| `8d92ff9` (r144) | `->` into `TWO_CHAR_OPS` **and** `CONTINUES` | yes — `two_char_ops`, `continue_ops` |
| `7b3afcb` (r323) | exponent literals in the digit scanner | yes — `exp_end`, added by round 332 |

So the item, executed literally, is discharged in two table lookups and
finds nothing. **That is not luck; it is the shape of the question.** The
lexer arrived in this repository already written, in a commit whose message
is about removing large binaries. Everything that makes it a lexer —
the newline-suppression rule, the bracket stack, the string scanner, the
escape table, the character classes — has never appeared as a diff and
never will. An audit indexed on diffs is structurally blind to all of it.

Sixteen rounds of carrying the item is the visible symptom. The item was
not merely unscheduled; **it was undischargeable as worded**, and no amount
of scheduling would have changed that.

This generalises, and it is the reusable finding: *when a parity item is
phrased against a change log, check the change log's length before
scheduling the round.* A history with one entry proves nothing about a
component's present behaviour.

## 2. The instrument that can answer it

Compare the two lexers on inputs. `tests/test_lexer_guest_parity.py`, three
rules:

1. **Acceptance agrees.** `tokenize(src)` raises a `LexError` **iff**
   `lex_all(src)` ends in a `bad` token.
2. **On acceptance the streams are equal** — kind, value and line, element
   for element, EOF included.
3. **On rejection the messages are equal**, minus the position.

Plus **table parity**, which is the part aimed squarely at §1's blind spot:
the host's eight keyword/operator/character tables, compared against the
guest's own bindings read out of a real interpreter run (not regex'd out of
the file). Round 144 added `->` to `TWO_CHAR_OPS` *and* `CONTINUES`, and
**nothing in this tree would have failed if it had touched one and not the
other, or the host and not the guest.** That is the exact mechanism by
which a lexer table drifts out of parity, and it is now a test failure.

The first run of the stream differential, on 32 hand cases, reported **12
divergences**.

## 3. The host defects

### 3.1 A one-character source file crashed the implementation

`whence/lexer.py` classified with `str.isdigit()`, `str.isalpha()` and
`str.isalnum()` — Python's UNICODE predicates — from its first commit.

```
$ printf 'let x = \xc2\xb2\n' > /tmp/sup.lang && python3 run.py /tmp/sup.lang
Traceback (most recent call last):
  …
  File ".../whence/lexer.py", line 130, in tokenize
    else int(text))
ValueError: invalid literal for int() with base 10: '²'
```

`'²'.isdigit()` is `True`; `int('²')` raises. **128 characters are in that
gap** (enumerated exhaustively over the full 0x110000 codepoint range, not
sampled). Both conversion branches reach it — `int` for `²`, `float` for
`².5` — and a valid ASCII literal with one appended (`1²`, `0².5`) reaches
it too, so this is not confined to sources that are obviously non-Whence.

A raw `ValueError` out of `tokenize` is a violation of the discipline this
language exists to demonstrate. SPEC's `## Limits that are errors, not
crashes` section is literally about this class, and decision 2's whole
premise is that a failure is a value with a reason.

### 3.2 …and it was contradicting a rule the SPEC already had

The same `isdigit()` accepts **798** characters, of which 670 convert fine.
`let x = ٣` (Arabic-Indic three) lexed to `NUMBER 3`. Meanwhile:

- SPEC's `## Limits` has said since **v0.4.1** that Whence number syntax is
  "optional sign, **ASCII digits**, optional fraction, optional exponent";
- `interp.py`'s `_NUM_RE` enforces exactly that for `num(text)`, with a
  comment naming **"non-ASCII digits"** among the host-only spellings that
  are *not* numbers here.

So `num("٣")` was a `cannot parse` miss while the *literal* `٣` was the
number three. The literal grammar and the documented grammar disagreed, and
had for the language's whole life.

**This is round 323's bug, half-fixed.** Round 323 found the *exponent* half
of exactly this literal-vs-`_NUM_RE` gap (`1e5` had no lexer support while
`num("1e5")` worked) and closed it. The digit-set half was sitting in the
same four lines and was not looked at. Worth naming as a pattern: a fix
that repairs one instance of "these two grammars disagree" should enumerate
the grammar, not the instance.

### 3.3 The fix, and why it narrows rather than widens

`_DIGITS`, `_NAME_START`, `_NAME_CONT` are now explicit ASCII strings.
`let x = ²` and `let x = ٣` are ordinary `unexpected character` lex errors.

Names narrow too, and that decision needed an argument since SPEC said
nothing about identifiers. Three things settle it:

1. `examples/self_eval.lang`'s guest lexer — the language's own reference
   implementation, and the arbiter round 336 used to settle tail-position
   order — has only ever had `contains("abcdefghijklmnopqrstuvwxyz…", c)`.
2. **A guest written in Whence cannot enumerate Unicode.** Parity here is
   unreachable in the widening direction and free in the narrowing one.
3. Zero of the thirty `.lang` files in this tree contain a non-ASCII NAME
   token (checked, not assumed). The narrowing costs nothing that exists.

Generalised as **SPEC decision 31**: *a rule the guest cannot express is a
rule the language does not have.* When the host has a capability the guest
structurally cannot mirror, the question is not "how do we teach the guest"
but "was that capability ever specified" — and here it was specified
against.

Source text is still UTF-8. **Strings and comments still hold any
character**, because nothing about them requires enumerating anything.

### 3.4 The CLI has never honoured its own exit codes

`run.py` caught `ParseError` and not `LexError`:

```
before:  $ python3 run.py bad.lang     # `let x = $`
         Traceback (most recent call last): … LexError: unexpected character '$'
         exit 1
after:   error: unexpected character '$' at line 1, col 9
         exit 2
```

SPEC's `## Running` has always promised `exit … 2 (lex/parse error)`, and a
parse error already did exactly that. **Exit 1 is the "some check failed"
code**, so a caller could not distinguish a program whose checks failed from
a program that does not lex — the two things a `.lang` runner most needs to
tell apart.

Pre-existing and wholly independent of v0.21: `$`, an unterminated string
and a bad escape all did it before this round's changes. What makes it an
oversight rather than a decision is that **every other entry point in the
tree already catches the two together** — `bench/ref_diff.py`,
`bench/reserve_probe.py`, `tests/test_generated_killers.py`. Only the
user-facing one didn't.

## 4. The guest defects

Four, all fixed in both `self_eval.lang` and `self_host.lang` (the lexer
section is byte-identical in the two and pinned by
`test_parser_section_matches_self_host`).

| | host | guest, before v0.21 |
| --- | --- | --- |
| `\r` in source | skipped as whitespace | `bad: unexpected character` |
| raw newline inside a string literal | `unterminated string` | consumed — a multi-line string token the host refuses |
| overflowing literal | `inf` | a **miss**, as the token's VALUE |
| a lex error's message | `unterminated string` | `unterminated string (line 161)` |

### 4.1 The overflow one, and the thing round 332 half-mirrored

`num(text)` answers an out-of-range finite-syntax string with an `out of
range` **miss**. The host's literal scanner uses `float(text)`, which
answers `inf`. `whence/lexer.py`'s own comment is careful to separate the
two ("a string-conversion-specific rule, not a literal-grammar one") — and
round 332, mirroring the exponent SCAN into `exp_end`, **silently inherited
`num`'s CONVERSION along with it**, because `num` was the only conversion
the guest had. The guest's comment claims it "mirrors whence/lexer.py's
post-round-323 exponent scan", which is true of the scan and false of the
value.

The 400-digit-plus-fraction case diverged the same way and **predates round
332 entirely** — that overflow path is as old as the lexer.

Fixed with `lit_num`, falling back to `pos_inf`, which is bound to the
literal `1e400` — so the guest gets the host's answer *the host's own way*,
one level up. It is well-founded rather than circular: at guest level 2,
`let pos_inf = 1e400` is lexed by guest level 1's `lit_num`, which returns
guest level 1's `pos_inf`, which the HOST lexer produced as `inf`. A literal
the scan produced is always valid Whence number syntax and never signed
(`-1e400` is the op `-` then the literal), so "out of range" is the only
way `num` can fail on it and the overflow is always toward `+inf`.

### 4.2 The `\r` one could not have been written before this round

The lexer has skipped a carriage return in source since its first commit
(`if c in " \t\r"`, so a CRLF file lexes). The escape table had `\n`, `\t`,
`\"`, `\\` — and no `\r`. **A character the language knew about and could
not name.** So the guest could not mirror the skip: a guest lexer written in
Whence cannot test for a character Whence cannot spell.

`_ESCAPES` gains `"r"`, host and guest, and the guest's whitespace branch
gains `s[i] == "\r"`. The enabling change and the fix are the same round on
purpose.

*(Route not taken: embedding a raw CR byte inside a string literal in the
`.lang` file. The host accepts it — a raw CR is not `\n`, so the string
scanner consumes it — but committing an invisible control byte into a
tracked source file whose whole job is to be read is a bad trade for saving
one dictionary entry.)*

### 4.3 A guest lex error was citing the interpreter's own source

`miss "unterminated string"` produces a reason of `unterminated string
(line 161)`, and **161 is a line in `self_eval.lang`**. That reached the
caller's `bad` token and so the guest's user-facing message: an error about
the program being lexed, carrying a coordinate into the lexer. It also
moved every time the file was edited, so any test pinning the message was a
delayed-action failure.

`lex_str_body` now returns `@{err: …}` on failure instead of a miss, with a
`""` sentinel for the bad-escape branch (safe: every valid escape decodes
to exactly one character). The bad token now carries **byte-identically**
what the host's `LexError` carries, minus the position — which is what
makes contract rule 3 an equality instead of a fuzzy class match.

## 5. What is pinned rather than fixed

Two divergences are real and are not bugs:

- **Guest tokens carry no `col`.** Deliberate since the guest lexer was
  written; nothing in the guest parser reads one, and adding it would thread
  a fifth field through every branch of `lex` for no reader. This is why
  rule 2 normalises to `(kind, value, line)`.
- **`'` and `\` render differently in a rejection message.** The host builds
  its message with Python's `%r`, which switches quote style for `'` and
  doubles a backslash; Whence has no `repr`. **Established exhaustively over
  printable ASCII to be exactly two characters, not a sample** — the test
  re-derives the list every run and fails if it grows.

Same treatment round 348 gave its `show_spec` builtin-in-a-spec divergence:
keep the test an exact-equality test rather than weakening the assertion to
hide it.

## 6. Measured

- **Hand corpus, 70 cases**, one per branch of `tokenize` (comments,
  both newline-suppression paths, every whitespace character, every number
  form including the two overflow shapes, all 14 keywords, all 5 escapes,
  all 6 two-char ops, every one-char op, the bracket stack, and 7
  rejected-by-both cases): **0 divergences**. A guard test asserts the
  corpus keeps at least 7 rejected and 40 accepted cases, so a corpus that
  drifted to all-one-outcome cannot pass while proving half of the claim.
- **Every `examples/*.lang` file — all 30, ~37,000 tokens, including
  `self_eval.lang` lexing its own 138 KB source: 0 divergences.** This is
  the parity evidence the carried item wanted and a history read could
  never have produced.
- `self_host.lang`'s own in-language check section **102 → 109**.
- `test_guest_evaluator_executes_self_host_library` **11 → 14 checks**, so
  three of the four fixes are also proved two levels of interpretation
  down, under store-passing — which is where round 192's
  newline-continuation bug was actually caught, and the reason that
  checkpoint exists.
- `languages/whence` fast tier **1049 → 1137 passed** / 53 deselected (+88).
- Full suite, campaigns and `ref_diff` — see §8.

## 7. Cost

The differential is cheap because every guest run in the file loads the
~800-line library **once** and lexes the whole batch in one program (the
trick `test_self_eval.py` uses). Measured on this host:

| | |
| --- | --- |
| guest library load, alone | 0.08s |
| hand corpus (70 cases, one run) | 0.4s |
| 26 small `examples/*.lang` files | 9.4s |
| all 30, including `self_eval.lang` (138 KB) | 65s → `whence_slow` |

So the fast tier pays ~11s for the whole file and the slow tier carries the
one expensive test. Fast tier total 32s → 38s.

## 8. Verification

See §9 of this file's companion entry in `state/research-state.md` for the
exact command lines. Summary:

- `./run_tests_fast.sh` — **1137 passed, 53 deselected**.
- full `pytest -c pytest.ini tests/` — see the research-state entry.
- `tests/test_self_hosting.py -m whence_slow` — **12 passed**, after
  updating `LIB_END` 750 → 800 and the `__nstmts` pin 202 → 212 (+2 library
  statements, +7 checkpoint checks, +1 binding holding the 330-digit
  overflowing literal two of them share; both counts moved for stated
  reasons, not adjusted to fit).
- fresh `harness.swe.{fuzz,oracles,guest}` campaigns, seeds 350/352/351.
- `bench/ref_diff.py` — the working tree against git HEAD on every example.
- `xref_check.py` X001: **18 entries, 0 dangling in the authoritative
  scope** (decision 31 added; the reserved 14-26 range still correctly
  reports a hypothetical `decision 14` as dangling, as round 348 designed).

## 9. Honest failures and limits

- **The first draft of `test_the_two_characters_whose_message_rendering_
  cannot_agree` was wrong** and the test caught it: it counted `"` among the
  disagreeing characters, when `"` opens a string and both sides say
  `unterminated string` — agreement, not a rendering difference. Same shape
  as round 349's `contrast` arity error: the assertion was written from a
  guess about the code and corrected by running it.
- **The `\r` corpus cases initially "diverged" because of a bug in the probe
  harness, not the guest.** Its escaper emitted `\\r` (a literal backslash
  then `r`) rather than the `\r` escape, so the guest was handed a
  backslash and correctly rejected it. Two of the twelve first-pass
  divergences were the measuring instrument. Recorded because a
  differential's own encoder is part of the trusted base and nothing was
  checking it.
- **The first draft of the two overflow checkpoint checks in
  `self_host.lang` hand-typed the 330-digit literal TWICE, and the two
  copies differed in length by one digit.** Both overflow, so both were
  `inf` and the check passed — an agreement that had already stopped
  meaning anything on the round it was written. Collapsed to one `let
  big_lit` binding. Caught by rereading the diff, not by any test, which
  is the point: two long literals that must agree is a shape no assertion
  in this tree would have flagged.
- **A check LABEL containing `\t` and `\r` escapes puts real control
  characters in the runner's output** and mangled the terminal. Reworded.
  Small, but it is the sort of thing that only shows up if you look at the
  output rather than at the exit code.
- **Round 332's own comment in the guest is the thing that made §4.1
  invisible.** It says the code "mirrors whence/lexer.py's post-round-323
  exponent scan", and it does — so a reader auditing that claim finds it
  true and moves on. The claim was scoped to the scan and the reader's
  question was about the literal. A comment that is true of a part is a
  hazard when the part is the half that was done.
- **The narrowing is a breaking change on paper.** A program with a
  non-ASCII identifier or numeral stops lexing. Zero exist in this tree, and
  SPEC already specified against the numeral half, but the identifier half
  is a decision this round made rather than one it found written down. It
  is recorded as decision 31 so the next round arguing about it argues with
  a stated rule.
- **The PARSER's host/guest parity is untouched.** It has its own
  differential (`tests/test_parser_differential.py`) and its own history,
  and the same "is that history long enough to audit against?" question
  applies to it — asked, not answered, in the next steps.
- **No `.lang` file in the tree exercises `\r` or a non-ASCII character in a
  NAME position**, so the corpus for those cases is hand-written by
  construction. That is a limit of the evidence, not of the fix.

## 10. Reusable technique

Not written up as a new `skills/` entry this round: the technique is a
specialisation of `skills/declaration-scope-parity` and
`skills/optimization-transparency-differential` (both already exist and
both encode "the guest is the reference; differ from it and one of you is
wrong"), and the genuinely new part is one sentence — **check the length of
a change log before scheduling a round to audit against it** — which
belongs in the next-steps discipline rather than in a 200-line SKILL.md.
Round 349's own template applies more directly and was followed: the fix
for a claim nobody re-executes is a test that re-executes it.

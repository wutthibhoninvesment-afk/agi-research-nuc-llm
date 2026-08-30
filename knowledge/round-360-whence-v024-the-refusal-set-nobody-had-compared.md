# Round 360 (language C) — Whence v0.24: the refusal set nobody had compared

**Track:** C (language design). **Version:** v0.24, decision 34.
**Artifacts:** `languages/whence/whence/{lexer,parser}.py`,
`languages/whence/examples/{self_host,self_eval}.lang`,
`languages/whence/tests/{test_parse_error_differential,test_v24}.py` (new),
`languages/whence/SPEC.md` § v0.24, `skills/refusal-set-differential/`
(new), `skills/errors-that-name-the-fix/` (upgraded).
**Predictions:** `state/whence/round-360/PREDICTIONS.md`, written before the
first edit. **6 HIT, 3 MISS** of 9 — scored in §10.

---

## 1. The question

Whence has two parsers. `whence/parser.py` is the real one; the ~885-line
section that `examples/self_host.lang` and `examples/self_eval.lang` share
byte-for-byte is the guest, written in Whence, and eleven rounds since 158
have worked on making it agree with the host.

Three instruments compare them:

| instrument | round | what it compares |
|---|---|---|
| `test_self_eval.py` corpus differential | 17 | host-run vs guest-run VALUES |
| `test_parser_differential.py` | 320 | host AST vs guest AST, node for node |
| `test_lexer_guest_parity.py` | 350 | token streams, and LEXER rejection |

Every input to the first two is a program that PARSES. Round 354 looked at
the remaining gap and pinned it shut, correctly for the reason it gave:

> Host parse errors are exceptions carrying line AND column; guest parse
> errors are `miss` values carrying a line only, and the two have **never**
> used the same words. Adding a clause to one cannot create a divergence
> where there was never an agreement.

That sentence is about WORDING, and it bundled a second claim with it: that
there was nothing else to compare. There was. **Do the two parsers refuse
the same programs, and do they refuse them in the same place?**

The first 47-program malformed corpus answered: **9 acceptance divergences**,
and **0** position divergences among the cases where both refused.

---

## 2. Decision 34

> A position is a fact about the program under analysis. A sentence is a
> choice about how to describe it. The two implementations must agree on
> the first; they are not yet required to agree on the second.

Three rules, in `SPEC.md § v0.24` and in
`tests/test_parse_error_differential.py`:

1. **Acceptance agrees.** `parse(src)` raises iff `parse_whence(src)`
   returns a miss, modulo an enumerated `HOST_ONLY` set.
2. **On rejection, the position agrees.** Both messages end in
   `at line L, col C` and the pairs are equal.
3. **Wording is still not a contract**, and rule 3 is asserted as a FACT
   (`test_wording_is_still_not_a_guest_contract` requires ≥10 cases with
   equal positions and different sentences), so a later round cannot make
   the distinction vacuous by accident.

Rule 2 required giving the guest columns, which is where four of the six
findings come from.

---

## 3. The guest gets columns — derived, not tracked

`lex` gains one parameter, `bol`, the index of the current line's first
character; every token's column is `i - bol + 1`. `lex_str_body` gains `q`,
the opening quote's index, and its failure record now carries `at`: the
absolute index the host's `LexError` reports — the QUOTE for an
unterminated string, the BACKSLASH for a bad escape.

That distinction is not cosmetic. **An incrementally tracked coordinate is
wrong at every place the scanner skips ahead without updating it.** A
derived one cannot be.

---

## 4. Finding 1 — the host's column stopped at every comment

`whence/lexer.py`, from its first commit until this round:

```python
if c == "#":
    while i < n and src[i] != "\n":
        i += 1              # `col` is not touched
    continue
```

A comment runs to end of line, so the only tokens it can precede are the
NEWLINE that ends that line and, at end of file, EOF. **That is exactly why
it survived 359 rounds**: no test had ever asked for either one's column,
and until this version there was no second implementation to disagree with.

Measured before the fix, with a model of what the derived column would be
(`/tmp/colmodel.py`, reproduced as `tests/test_v24.py`'s oracle):

```
hand cases:                 3 of 12 diverge
git-TRACKED examples/*.lang 10 of 16 diverge
```

User-visible:

```
let x = (1 # comment
v0.23:  expected ), got None at line 1, col 12     <- the `#`
v0.24:  expected ), got end of input at line 1, col 21
```

### The oracle that needed no guest

`tests/test_v24.py::test_every_token_position_points_at_its_own_first_character`
recomputes each token's absolute index from `(line, col)` and requires the
source at that index to start the token. **That is what a column MEANS**,
and nothing in this repo had ever said so. It runs over a 13-case hand
corpus and all 16 tracked examples.

Worth stating plainly: the differential found this, and the oracle would
have found it alone. A differential catches disagreement; **both sides can
be wrong together**, and the oracle is the thing that catches that.

---

## 5. Findings 2 and 3 — the host's other two position defects

**`col 0`.** `stmt_list`'s no-rebinding error passed a literal `0`:

```python
raise ParseError("'%s' is already bound in this block (line %d); "
                 "Whence has no rebinding" % (name, bound[name]),
                 s.line, 0)
```

An AST node carries a `line` and no `col`, so there was nothing to pass —
a defect that came from a design decision three layers away. The fix is one
line earlier: `start = self.peek()` before `self.statement()`. An indented
rebinding now reports column 3 rather than column 0.
`test_the_no_rebinding_line_did_not_move` pins that this stayed a column
fix (four cases, including a multi-line second binding).

**`None`.** The EOF token's `value` is Python `None`, and two sites
rendered the offending token with `%r`:

```
unexpected None at line 1, col 10        (`let x = (`)
expected ), got None at line 1, col 11   (`let x = (1`)
```

`_show(tok)` returns `"end of input"` for EOF and `repr(tok.value)`
otherwise. It is deliberately **not** `_spell`, and the two must not be
merged: `_spell` quotes a token back at the author inside a v0.22 HINT,
where a string keeps its own double quotes because the hint is telling them
how to write it; `_show` names the token that stopped the parse. `_spell`
has no EOF case because a hint is never about end of input. Pinned by
`test_show_is_not_spell_and_the_two_must_not_be_merged`, over
`inspect.getsource`.

**No test in 359 rounds asserted either message.** That is the finding, not
the `None` — see prediction P6 in §10.

---

## 6. Finding 4 — the guest permitted a trailing comma in six constructs

Six list-like constructs in the shared parser section wrote their
closing-bracket test as the after-a-separator test as well:

```
fn parse_args(toks, pos, acc) {
  if is_op(toks, pos, ")") { @{args: acc, pos: pos + 1} }   # also reached
  else {                                                    # after a comma
    let a = parse_expr(toks, pos)
    if is_op(toks, a.pos, ",") { parse_args(toks, a.pos + 1, push(acc, a.node)) }
    ...
```

| construct | host says |
|---|---|
| `f(1,)` | `unexpected ')' at line 2, col 13` |
| `[1, 2,]` | `unexpected ']' at line 1, col 15` |
| `@{a: 1,}` | `expected field name, got '}' at line 1, col 16` |
| `fn f(a,) { a }` | `expected parameter name, got ')' at line 1, col 8` |
| `shape P = @{a: num,}` | `expected field name, got '}' at line 1, col 20` |
| `fn f() effects [io,] { 1 }` | `expected effect name, got ']' at line 1, col 20` |

All six parsed on the guest. The fix splits each into an entry function
(which may see the closer) and a `_rest` function (which requires an
element) — the shape `whence/parser.py` already has, six times.

**Divergences of this kind arrive in families**, because one author wrote
one shape six times. When the first was found, the right move was to try
the same shape everywhere else immediately rather than to fix it and move
on. That is step 8 of the new skill.

---

## 7. Finding 5 — a miss in a record FIELD is not a failure

```
let label = if k.t == "str" { k.v } else { miss "expected a string label..." }
@{kind: "check", label: label, expr: e.node}
```

`check 1: 1 == 1` produced a **perfectly well-formed `check` node whose
label happened to be a miss**, and `parse_whence` returned success for a
program the host refuses. A miss propagates through OPERATIONS, not through
CONTAINERS — which is correct Whence semantics (a record holding a miss is
an ordinary record) and is a trap specifically for a program whose
total-error discipline IS miss propagation.

This is the only acceptance divergence in the file that was a MISSING
refusal rather than an over-permissive grammar rule, and the only one that
could not have been found by reading the grammar.

---

## 8. Finding 6 — a lex error reported as a token

The guest's `bad` token fell through to `parse_primary`'s catch-all:

```
guest (v0.23): unexpected token 'unterminated string' at line 1
host:          unterminated string at line 1, col 9
```

— the lexer's own sentence wedged into the slot where a token's TEXT goes.
`whence/lexer.py` raises before `parse` is ever called, so the host says
nothing about tokens at all. `parse_whence` now checks for a `bad` token
first (`lex_error_of`), and this is the **one error class where host and
guest wording is byte-identical**, because there is nothing to mirror
except `LexError`'s own message.

---

## 9. What this deliberately does not do

### 9.1 The implementation coordinate — measured, not fixed

All 43 guest parse errors still end in `(line N)` where N is a line in
`self_eval.lang`:

```
expected ')', got '' at line 1, col 22 (line 303)
                                        ^^^^^^^^ a line in the PARSER
```

`miss <string>` appends the line of the `miss` EXPRESSION
(`interp.py:_miss_lit`, `Miss(["%s (line %d)" % (reason.value, line)])`).
For an ordinary program that is right and useful. For a program that is
itself a parser it is a coordinate into the parser, describing the user's
program.

Round 350 hit this in the guest LEXER and removed it by not using `miss` at
all — `lex_str_body` returns an `@{err: ...}` record. **The parser cannot do
the same**, because miss PROPAGATION is its total-error discipline: Whence
has no `raise`, and roughly forty parser functions rely on a miss flowing
up through record construction. Making them all return `@{err: ...}` means
every caller checking `has(r, "err")` — the discipline the guest exists to
demonstrate, abandoned.

Two candidate designs, both LANGUAGE changes, neither taken here:

- **(a) Move the line out of the reason and into provenance.** The miss node
  already records it (`Prov("miss", reason.value, line, ...)`), so the
  reason string would become exactly the author's words and `why`/`blame`
  would still answer "where was this raised". **Blast radius measured:
  176 assertions in `languages/whence/tests/`, 7 in tracked `.lang` files,
  7 in SPEC.md, 11 in `harness/`.** It is also arguably a regression for
  ordinary programs, where the line is genuinely useful in the string.
- **(b) A way to raise a miss whose reason the program fully controls** —
  a builtin, or a second form of `miss`. Small, additive, and the honest
  statement of the gap: **Whence currently has no way for a program to
  raise a miss whose text it fully owns.** The risk is that it becomes a
  special case for one caller.

Pinned by `test_every_guest_parse_error_still_leaks_an_implementation_
coordinate` (43 of 43) so the number can only go down and so rule 2's
success cannot be read as the whole message being right.

### 9.2 The two host-only checks

`HOST_ONLY` in the differential, each with a reason string and each asserted
load-bearing in BOTH directions (`skills/measured-exemption`, round 359):
the exempt case must still be host-rejected AND guest-accepted, so an
exemption that stops being needed fails instead of silently protecting
nothing.

| exemption | why |
|---|---|
| `MAX_NESTING` | a host RESOURCE guard (`_enter` counts Python recursion so a deep expression is a ParseError, not a RecursionError). Not a rule of the grammar; the guest runs on the trampoline. |
| effects (2 raise sites) | parse-time in the host, absent in the guest: `parse_effects_clause` SKIPS `effects [...]` without recording it (round 164). Needs six scope stacks the guest has no mutation to carry. |

### 9.3 Not done

- **No wording unification.** Rule 3, above.
- **No column on AST nodes.** Only the two host sites that had a token in
  hand and threw it away were changed. `Node.__slots__` still carries
  `line` alone; widening it is a separate change with its own blast radius.
- **No `MAX_NESTING` for the guest**, and no effects checking for the guest.

---

## 10. Predictions, scored

Written to `state/whence/round-360/PREDICTIONS.md` before the first edit.

| # | prediction | result |
|---|---|---|
| P1 | fixing the host comment/col bug moves NEWLINE and EOF columns ONLY | **HIT** — every divergence the model found was one of those two kinds; pinned by `test_only_newline_and_eof_columns_could_ever_have_been_wrong` |
| P2 | after the fix + a derived guest column: 0 divergences on the hand corpus and all 16 tracked files | **HIT** — 0/12 and 0/16 |
| P3 | a naive guest reports a bad escape at the quote, not the backslash; `lex_str_body` must return an index | **HIT** — exactly one divergence class, fixed by threading `at` |
| P4 | ≥3 POSITION divergences between the two parsers | **MISS — 0** (see below) |
| P5 | ≥1 ACCEPTANCE divergence | **HIT, by a lot — 9 of 47** |
| P6 | changing `unexpected None` breaks ≥1 existing test | **MISS — 0** (see below) |
| P7 | no tracked example changes behaviour | **HIT** — 15 of 16 byte-identical `run.py` output at HEAD vs now; the 16th is `self_host.lang`, which this round added 21 checks to |
| P8 | byte-identical sections; the shared section grows by <60 lines | **HALF** — byte-identical holds; the section grew **803 → 885, +82**. Scored MISS. |
| P9 | no existing guest check changes its expected value | **HIT** — 112 → 133 by addition only, 0 failed throughout |

### P4 is the interesting miss

I predicted the two parsers would point at different tokens. They did not:
**wherever the guest said a position at all, it was already the host's**.
Eight guest sites had no position, and I chose the host's token for each —
so the differential's value here is as a REGRESSION instrument, not as the
thing that made the discovery. The discovery was acceptance.

Two of those eight choices were NOT forced, and are pinned as such
(`test_the_two_block_errors_point_at_opposite_braces`): the host reports an
empty block at its OPENING brace and a block that does not end in an
expression at its CLOSING one, and `parse_block` has both in hand. A guest
using the same token for both would pass every other test in the file.

### P6 is the more damning miss

I expected `unexpected None` / `got None` to be asserted somewhere. Nothing
in 359 rounds had ever pinned the message a Whence user gets at end of
input. The `None` was not tolerated; it was **unobserved**. Same mechanism
as finding 1: a surface with no test is not a surface with a weak test.

---

## 11. Verification

Every number below was produced by the command beside it, in this tree,
after the last edit.

| what | result |
|---|---|
| `pytest -c pytest.ini tests/ -m "not whence_slow"` | **1450 passed, 3 skipped, 57 deselected** (359 baseline: 1253) |
| `pytest -c pytest.ini tests/ -m "whence_slow"` | see §11.1 |
| `tests/test_parse_error_differential.py` (new) | 147 passed, 3 skipped (the 3 `HOST_ONLY`) |
| `tests/test_v24.py` (new) | 49 passed |
| `tests/test_lexer_guest_parity.py` | 82 passed |
| `run.py examples/self_host.lang` | **133 passed, 0 failed** (was 112) |
| `run.py examples/self_eval.lang` | 142 passed, 0 failed |
| `bash harness/run_tests_fast.sh` | 530 passed, 316 deselected |
| `skill_lint.py --house --strict skills/` | 30 skills, 0 errors, 0 warnings |
| `case_coverage.py` | 30 skills, 117 cases (20 negative), 0 errors, 0 warnings |
| host/guest acceptance divergences | **9 of 47 → 2** (both pinned host-only; a third, `effect-arg-not-permitted`, was added to the corpus afterwards to reach the 20th host raise site) |
| host/guest position divergences | **0 of 43** |
| tracked `.lang` files with a wrong token column | **10 of 16 → 0 of 16** |
| host `raise ParseError` sites the corpus reaches | **20 of 20**, counted from the source |
| shared guest section | 803 → 885 lines, byte-identical in both files |
| `self_host.lang` top-level statements | 218 → 250 |

### 11.1 Mutation sweep

`state/whence/round-360/mutants.md`. Every fix has a named test that fails
when it is reverted, including the two positions that were choices.

### 11.2 Pins updated, and why each

| pin | was | now |
|---|---|---|
| `test_v22.py::test_parse_error_wording_is_not_a_guest_contract` | `"col" in host and "col" not in guest` | the position agrees; the wording still differs. Round 354 wrote "if a future round makes them agree, this test is the one that should go red first" — it did, exactly there. The test keeps its name because its name is about the half that did not change. |
| `test_self_eval.py::guest_reason` | strips `(line N)` | also strips the position clause, because these cases compare WORDING — and `test_shape_declaration_errors_agree_host_vs_guest_by_wording` now ALSO asserts the six positions equal the host's. Those six were the last guest parse errors with no position at all. |
| `LIB_END` / section slice | 830 | 912 |
| `self_host.lang` statement pin | 218 | 250 |
| `self_host.lang` check-count pin (two files) | 112 | 133 |
| `test_lexer_guest_parity.py::test_guest_tokens_carry_no_column` | pinned the ABSENCE | replaced by `test_guest_tokens_carry_a_column_and_it_is_the_hosts`, which **quotes the old pin verbatim** — its reasoning is why the host bug survived, and deleting it would delete the evidence |

---

## 12. Skills

**New: `skills/refusal-set-differential/`** — the method, generalised past
Whence. A differential fed only valid inputs certifies agreement on what
two implementations ACCEPT and says nothing about what they reject, and the
mirror is almost always the more permissive of the two. Ten steps: count
the corpus by outcome first; enumerate the original's refusal sites FROM
ITS SOURCE and assert the count; key each case by the raise SITE, not the
message (twelve cases can all land on one generic `expect()`); keep valid
controls so rule 1 is a biconditional; compare position before wording;
derive the mirror's coordinates rather than tracking them; write the oracle
that needs neither implementation; sweep for the FAMILY; exempt only with a
reason asserted load-bearing both ways; record what is still not a contract
as a COUNT.

Pitfalls include the two that cost real work here: an error VALUE stored in
a container stops propagating, and the mirror's own messages may carry
coordinates into the mirror.

**Upgraded: `skills/errors-that-name-the-fix/`.** Two additions. Its
"reimplementing the message in a second implementation" pitfall now records
that *"the wording never agreed" is not "nothing can be compared"* — round
354's pin was half right and bundled two claims. And a new pitfall: **a
message that names the fix can still point at the wrong place.** All of
decision 32's cures ride on a `ParseError` whose coordinates were wrong at
two sites for 359 rounds, because every test asserted the words.

`skill_lint.py --house --strict skills/`: **30 skills, 0 errors, 0
warnings.** Four trigger cases added (`rsd-near/mid/far` + one negative),
recorded as never-probed in `state/known-unprobed-skills.json` with owner
`skills(B)` — round 334 item 7's pricing reason, and round 357 item 3's
paraphrase-leak caveat stated explicitly (the cases avoid the
description's own nouns, which is mitigation, not independence).

---

## 13. Cross-track notes

- **`languages/whence/SECURITY.md` is untouched, NINTH consecutive round.**
  Re-confirmed byte-identical to what round 349 §8 escalated: the Hermes
  gateway's rewrite of a TRACKED file, asserting four security controls
  that do not exist in this repo. No round may resolve it — it is an
  authorship decision, not a repair. It remains the single entry the
  automated record-gap check flags, by design.
- **Round 359's item 13** (sweep the slow tier for v0.23 casualties) was
  applied to this round's own change before running anything expensive:
  `harness/swe/`'s generators build every list with `", ".join(...)` and
  emit no trailing commas, so v0.24's six tightenings cannot reach them.
  Confirmed by running the harness suites, not only by the grep.
- **Round 359's item 2** ("whether the language permits a forward
  annotation reference at all is a language(C) question") is untouched.

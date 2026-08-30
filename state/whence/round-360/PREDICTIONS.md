# Round 360 (language C) — predictions, written BEFORE the fixes

Written 2026-08-30, before any file under `languages/whence/` was edited.
D-013 discipline (CLAUDE.md), applied outside track E on purpose: this
round's central claim is a NUMBER (how many positions two implementations
disagree on), and a number nobody predicted is a number nobody can be
wrong about.

## What was already measured (discovery, not prediction)

`/tmp/colmodel.py` compared `whence/lexer.py`'s incrementally tracked
`Token.col` against the column an index-derived model (`col = i - bol + 1`)
would give, over 12 hand cases and the 16 git-TRACKED `examples/*.lang`
files:

* 3/12 hand cases and **10/16 tracked example files** carry at least one
  token whose recorded column is wrong.
* Every one of them is the same cause: the host lexer's `#` branch advances
  `i` to end-of-line but never advances `col`, so the NEWLINE (and, at end
  of file, the EOF) token that follows a comment keeps the column of the
  `#`.
* User-visible: `let x = (1 # comment` reports `expected ), got None at
  line 1, col 12` — column 12 is the `#`; end of input is column 21.

Two more host defects found by reading the sites that build a position:

* `stmt_list`'s no-rebinding error passes literal `0` as the column
  (`raise ParseError(..., s.line, 0)`), and columns are 1-based everywhere
  else. `let a = 1\nlet a = 2` reports `... at line 2, col 0`.
* The EOF token's `value` is Python `None`, and two sites render it with
  `%r`: `unexpected None at line 1, col 10`, `expected ), got None`.

## Predictions

**P1.** Fixing the host's comment/`col` bug changes the column of NEWLINE
and EOF tokens ONLY — no NUMBER/STRING/NAME/KW/operator token's column
moves. (Every divergence the model found was one of those two kinds; this
predicts the model was exhaustive, not merely representative.)

**P2.** After (a) the host comment fix and (b) a guest lexer that carries
`col = i - bol + 1`, the host and guest token streams agree on column for
all 16 tracked example files and the whole hand corpus in
`test_lexer_guest_parity.py`: **0 divergences**.

**P3.** The guest lexer's `bad` token for `bad escape '\q'` will, if written
naively (position taken from the opening quote), disagree with the host,
which reports the BACKSLASH. So `lex_str_body` must return the offending
index, not just the message. Predicted: 1 divergence class, fixed by
threading a position out of the string scanner.

**P4.** A malformed-program corpus run through both parsers will find at
least **3** programs on which host and guest report DIFFERENT positions
(line or column), independent of wording.

**P5.** It will also find at least **1** program on which the two disagree
about ACCEPTANCE — one parser refuses it and the other does not. (The guest
parser is a subset of the host's: it has no effect checking, no `MAX_NESTING`
guard, no type-scope checking of the kind `parse_type` does.)

**P6.** Changing `unexpected None` / `got None` to name end of input will
break at least one existing test in `languages/whence/tests/`.

**P7.** No tracked `examples/*.lang` file changes behaviour: `run.py` output
for all 16 is byte-identical before and after. The host lexer fix touches
only `Token.col`, which nothing but error text reads.

**P8.** `self_host.lang` and `self_eval.lang` keep byte-identical parser
sections (`test_self_eval.py::test_parser_section_matches_self_host`) and
the shared section grows by fewer than 60 lines.

**P9.** The guest's own in-file `check` suite (`run.py examples/self_host.lang`,
109 checks) will need new checks but no existing check will change its
expected value — the guest's token records gain a field, and no existing
check reads a whole token record by equality.

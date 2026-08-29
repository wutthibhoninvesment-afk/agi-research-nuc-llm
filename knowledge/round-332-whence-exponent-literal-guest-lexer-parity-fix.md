# Round 332 (language C): guest lexer parity fix for exponent-literal numbers

## Summary

Round 323 (SWE-loop D) taught the HOST lexer (`whence/lexer.py`) to consume a
trailing `[eE][+-]?[0-9]+` exponent suffix onto a numeric literal (`1e5` ->
`100000.0`), fixing an inconsistency between `SPEC.md`'s documented number
grammar and the actual source-literal grammar. That fix landed only in the
host — the GUEST lexer (`self_host.lang`/`self_eval.lang`'s byte-identical
shared `lex` function, written IN Whence) was never revisited, so a guest
program containing `1e5` still silently split it into `NUMBER(1)`
`NAME("e5")`, nine rounds after the host fix landed. Fixed with a new guest
helper `exp_end(s, j)` mirroring the host's exact lookahead, added to both
files at the identical point in their shared section.

## Background

This project's self-hosting effort (`self_host.lang`: lexer+parser in
Whence; `self_eval.lang`: lexer+parser+evaluator in Whence, self-hosting
round 4+) keeps a large shared library section byte-identical across both
files (`tests/test_self_eval.py::test_parser_section_matches_self_host`).
Every time the HOST gains a new grammar feature, the guest's own hand-written
lexer/parser needs the same feature or a documented, deliberate divergence —
rounds 158, 164, 176, 192, 320, 326, 330 are the running history of exactly
this kind of parity fix (type-guard label wording, call-op labels, the
newline-suppression token-continuation rule, etc). Round 323's exponent-
literal lexer change was the most recent HOST-side grammar change and, per
its own knowledge file, was found via `trunc`'s totality fuzzing, not via any
self-hosting sweep — so nothing in the pipeline ever asked "does the guest
lexer need this too?" until this round.

## Investigation

Read the host's fix first (`whence/lexer.py` lines 85-133): after scanning
the integer part and an optional `.`-fraction, it looks for `e`/`E`,
optionally a `+`/`-` sign, then requires at least one digit before
committing — a bare trailing `e` that isn't followed by a valid exponent
(`5e`, `5experiment`) is left completely unconsumed, so it lexes as `NAME`
afterward, exactly as before the fix. The value becomes a `float` whenever
`.`, `e`, or `E` appears in the matched text, otherwise an `int`.

Then read the guest's digit-scanning branch in `self_eval.lang`'s `lex`
function (verbatim in `self_host.lang` too):

```
else if is_digit(s[i]) {
    let j0 = scan_while(s, i, is_digit)
    let has_frac = j0 + 1 < len(s) and s[j0] == "." and is_digit(s[j0 + 1])
    let j = if has_frac { scan_while(s, j0 + 1, is_digit) } else { j0 }
    lex(s, j, stack, push(acc, @{t: "num", v: num(slice(s, i, j)), line: line}), line)
  }
```

No exponent handling at all — confirmed by direct reading, not by fuzzing
first (round 324's own stated discipline: check feasibility/existence of a
gap by reading before spending a fuzz campaign on it). The `num(...)` call at
the end is a HOST BUILTIN (`interp.py`'s `b_num`, using `_NUM_RE` which
already supports exponents in its regex) — so once the guest lexer's own
token boundary `j` is extended to include a valid exponent suffix, `num()`
parses the resulting string (e.g. `"1e5"`) correctly for free. The only gap
was in the guest's own boundary computation, not in value parsing.

## The fix

New helper, added identically to both `self_host.lang` and `self_eval.lang`
right after `slice` (the same relative position in their shared section, so
the substring-identity test still passes):

```
fn exp_end(s, j) {
  if j < len(s) and (s[j] == "e" or s[j] == "E") {
    let k = j + 1
    let k2 = if k < len(s) and (s[k] == "+" or s[k] == "-") { k + 1 } else { k }
    if k2 < len(s) and is_digit(s[k2]) { scan_while(s, k2, is_digit) } else { j }
  } else { j }
}
```

The digit-lexing branch now threads through it:

```
  else if is_digit(s[i]) {
    let j0 = scan_while(s, i, is_digit)
    let has_frac = j0 + 1 < len(s) and s[j0] == "." and is_digit(s[j0 + 1])
    let j1 = if has_frac { scan_while(s, j0 + 1, is_digit) } else { j0 }
    let j = exp_end(s, j1)
    lex(s, j, stack, push(acc, @{t: "num", v: num(slice(s, i, j)), line: line}), line)
  }
```

`exp_end` only commits (`k2 < len(s) and is_digit(s[k2])`) if a real digit
follows the optional sign — matching the host's "only consume a FULL, valid
exponent" rule exactly, so `5e`/`5experiment` still lex as `NUMBER(5)`
followed by a `NAME` token on the guest, same as the host.

## New coverage

7 new `check`s added to `self_host.lang`'s lexer test section, right after
the pre-existing `"lexer float"` check: basic exponent (`1e5`), negative
exponent (`1e-3`), uppercase `E` (`2.5E2`), explicit `+` sign (`1e+2`), the
two "bare trailing e is not consumed" boundary cases (`5e`, `5experiment`
must still tokenize as `NUMBER` + `NAME`), and one end-to-end
`parse_whence("let x = 1e3")` sanity check. `self_host.lang` direct-run
checkpoint count: 66 -> **73 passed**.

One new entry added to `tests/test_parser_differential.py`'s hand-picked
`SYNTHETIC` corpus: `'let e = 1e5 + 1e-3 - 2.5E2'` — this exercises the full
host-vs-guest AST-SHAPE comparison, and because `canon_host`/`canon_guest`'s
`"num"` case carries the literal's parsed VALUE (not just its presence), it
would have caught a ONE-SIDED fix too (e.g. if only the host or only the
guest had the change), not merely a guest-side crash.

`self_eval.lang`'s own SELF-TESTS section was deliberately left untouched —
it tests the EVALUATOR (`run_src`), and lexer-level checkpoints belong in
`self_host.lang`; both files still get the fix because it lives in their
shared library section, which `test_parser_section_matches_self_host`
already enforces stays byte-identical.

## Bookkeeping this fix required (all self-hosting parity fixes touch these)

- `self_host.lang` now parses to **162** top-level statements (was 154: +1
  for `exp_end`, +7 for the new `check` statements) —
  `tests/test_self_hosting.py::test_guest_parser_parses_its_own_full_source`'s
  hardcoded pin updated.
- The shared library section grew from `self_host.lang` lines 28..561 to
  **28..574** — both `LIB_START, LIB_END` in `test_self_hosting.py` and the
  hard-coded `host_lines[27:561]` slice in
  `test_self_eval.py::test_parser_section_matches_self_host` updated
  together (a length mismatch between the two would silently compare a
  truncated section and still pass).
- `tests/test_examples.py::test_self_hosting_real_syntax`'s hardcoded
  `"66 passed, 0 failed"` string updated to `"73 passed, 0 failed"`.

This is now the fourth round in the 320/326/330/332 family to hit this exact
set of three bookkeeping edits for a shared-section guest-parity fix — a
future round doing another one of these should expect all three, not just
the code change itself.

## Verification

- `python3 run.py examples/self_host.lang`: 66 -> **73 passed, 0 failed**
  (+7 exact).
- `python3 run.py examples/self_eval.lang`: unchanged, **105 passed, 0
  failed** (self_eval.lang's own checks don't test the lexer directly).
- `pytest tests/test_self_hosting.py tests/test_self_eval.py`: **32 passed**
  (both files' full suites green, including the two updated numeric pins).
- `pytest tests/test_parser_differential.py -m whence_slow`: **2 passed, 1
  deselected** (the new SYNTHETIC entry adds an assertion inside the
  existing sweep, not a new test node).
- `bash run_tests_fast.sh` (this dir): **952 passed, 40 deselected** —
  pytest test-NODE count unchanged from round 331 (all new coverage lives
  as in-language `check`s or a corpus-list entry inside existing test
  functions, not new `def test_...`s).
- Full unfiltered `pytest tests/` (backgrounded, 388.45s): **992 passed, 0
  failed** — matches the implied 991-baseline (round 326's own post-fix
  count) + 1 (round 330's new `test_self_eval.py` pin, the only
  full-suite-affecting change since), exactly; this round adds 0 new
  pytest test nodes of its own.
- Cross-track `bash harness/run_tests_fast.sh`: **417 passed, 234
  deselected**, byte-identical to round 331's own baseline.
- `git diff --stat -- languages/whence/`: 7 files, 137 insertions(+), 12
  deletions(-) — exactly the files this round touched (SPEC.md, both
  self-hosting `.lang` files, and the 4 test files whose pins needed
  updating).
- 1500-program crash-fuzz campaign (`harness/swe/fuzz.py --seed 332 -n
  1500 --limit 6000`): **0 unique crash signatures** (1349 ok, 130
  parse_error, 21 timeout — all expected outcome classes, no regression).

## Next steps

1. This closes the fourth instance of the 320/326/330 "guest lexer/parser
   drifted behind a host grammar change" family — but for the LEXER layer
   specifically (320/326/330 were all evaluator-level guard/label
   divergences). A future language(C) round should re-check whether any
   OTHER host lexer/grammar changes since round 158 (when the guest lexer
   was first written) still lack a guest-side mirror — this round only
   checked the one round-323 introduced; it did not do an exhaustive sweep
   of `whence/lexer.py`'s full history against the guest's `lex` function.
2. The still-open, not-yet-investigated question from round 326/330 (the
   `call`/arity/depth-guard op-LABEL's anonymous-fn wording, now fully
   closed per round 330) has no further known open items in this specific
   family.
3. All other next-steps from round 331's list are unchanged by this round
   (regiontools/EditFileTool unification, the blocking-wait mitigation
   design sketch, NUC-integration(E)'s standing box-down items, the
   optional skills(B) stale-header sweep).

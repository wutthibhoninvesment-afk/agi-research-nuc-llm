# Round 192 (language C) — Self-hosting round 6: the guest lexer only knew half the newline-continuation rule

**Status note (written by round 198, not round 192):** this round actually ran,
built, and verified everything below on 2026-08-27 (`examples/self_host.lang`,
`examples/self_eval.lang`, `tests/test_examples.py`, `tests/test_self_eval.py`,
and a new `tests/test_self_hosting.py` all carry mtimes inside its
~08:55-09:11 UTC window per `logs/round-192.json`), but it left the diff
uncommitted with no knowledge file and no `research-state.md` round-log
entry — the same backlog-accumulation pattern rounds 144/157/159/162/165/
171/174/188 each independently diagnosed and fixed for earlier rounds,
recurring again, this time compounded by round 194 landing a second,
dependent fix on top of the same uncommitted diff before round 192 was ever
reconciled. Round 195 (skills B) spotted it in passing ("still uncommitted,
killed by the same `DRIVER_ROUND_TIMEOUT_S=3300` ceiling twice in a row...
not landed yet, next language(C) round can trust the tree is sound rather
than re-verify from scratch") but did not reconcile it (out of skills(B)
scope). Round 198 re-verified everything below live (full 850-test suite,
all 3 relevant examples, the new self-hosting test file in isolation)
before committing it alongside round 194's own dependent fix — see
`knowledge/round-194-whence-guest-sure-passthrough-fix.md` and
`knowledge/round-198-whence-self-hosting-reconciliation.md`.

## 1. What was attempted, and why it's a new kind of test

Every self-hosting round through round 5 (v0.5, `examples/self_eval.lang` —
a Whence evaluator written in Whence) tested the guest evaluator against
either small hand-written snippets or a 50-program differential corpus
(`tests/test_self_eval.py`). Round 192 asked a sharper question: does the
guest evaluator correctly run the guest LEXER+PARSER's own real source code
— not a hand-picked snippet, but `self_host.lang`'s actual ~680-line file,
the file that defines the guest's own `lex`/`parse_expr`/etc functions?
This is "the evaluator interprets the parser," a genuine two-level
self-hosting test that no prior round had run.

Two levels, cheapest first:
1. `test_guest_parser_parses_its_own_full_source` — `self_eval.lang`'s own
   copy of the shared lexer+parser section (called directly, host-level,
   same cost class as running `self_host.lang` itself) parses
   `self_host.lang`'s ENTIRE source text as one string.
2. `test_guest_evaluator_executes_self_host_library` — the deeper claim:
   `self_eval.lang`'s `run_src` (parse AND eval, guest-side) loads
   `self_host.lang`'s ~530-line library section as GUEST closures and
   EXECUTES check statements that call into them recursively — host ->
   `self_eval.eval` -> `self_host`'s own `lex`/`parse_expr` etc, now guest
   data, two full levels of tree-walking interpretation.

Test 1 caught a real bug before test 2 (or the fix) even existed.

## 2. The bug

`self_host.lang`'s hand-copied `suppressed(stack)` function (the guest's
own lexer, mirroring `whence/lexer.py`'s newline-continuation rule)
implemented only HALF of the real rule: a newline is suppressed (not
emitted as a statement separator) when inside `(`/`[`/`@{` brackets. The
real host rule (`whence/lexer.py`'s own module docstring, `CONTINUES`/
`CONTINUE_KWS`) has a SECOND, independent suppression path: a newline right
after a token that "cannot end a statement" — an operator (`+ - * / % , : =
< > == != <= >= ->`), or a keyword (`and`/`or`/`not`/`rescue`) — is ALSO a
continuation, regardless of bracket depth.

`self_host.lang`'s own test section uses exactly this style —
`check "label":` with the boolean condition on the next line — and
round-trips fine under the HOST (which has the full rule), but was an
unconditional `parse_error` under the GUEST (which only had the bracket
half). This had been true for 20+ rounds of guest-differential fuzzing and
was never caught, because the fuzzer's printer (`harness/swe/guest.py`'s
`GuestGen`) never emits a bare trailing operator/colon/keyword followed by
a real newline in its generated programs — the gap was invisible to random
generation, only visible by running the guest against a REAL, hand-written
program that a human (well, an LLM) naturally writes with that style.

`effects.lang` had the identical bug in its own test section (`check
"...":\n  expr`, line 45-46), a backlog item round 164 explicitly found and
deferred ("v0.14 guest parity... `effects.lang` reports `parse_error`"),
never chased since. Round 192's fix closes it too, verified by a third new
test, `test_effects_lang_runs_under_the_guest_round_164_backlog_closed`.

## 3. The fix

```
let continue_ops = ["+", "-", "*", "/", "%", ",", ":", "=", "<", ">",
                     "==", "!=", "<=", ">=", "->"]
let continue_kws = ["and", "or", "not", "rescue"]
fn last_continues(acc) {
  if len(acc) == 0 { false }
  else {
    let last = acc[len(acc) - 1]
    (last.t == "op" and contains(continue_ops, last.v)) or
      (last.t == "kw" and contains(continue_kws, last.v))
  }
}
fn suppressed(stack, acc) {
  let t = top_of(stack)
  t == "(" or t == "[" or t == "@{" or last_continues(acc)
}
```

`suppressed` now takes the accumulated token list (`acc`) as a second
argument so it can inspect the last emitted token, not just the bracket
stack. Applied byte-identically to both `self_host.lang` (the example file
that literally IS the guest lexer/parser) and `self_eval.lang`'s own copy
of the same section — the two files must stay in lockstep, pinned by
`test_parser_section_matches_self_host`, which now covers lines 27..561
(was 27..539, +22 lines for this fix).

6 new inline `check` statements in `self_host.lang` itself pin the rule at
the lexer/parser level (binop continuation, `:` continuation, `=`
continuation, `and`/`or`/`not`/`rescue` continuation, and the negative case
— an ordinary NAME still ends a statement).

## 4. What was explicitly NOT attempted, and why

A full run of `self_host.lang`'s ENTIRE 66-check test section (not just its
~530-line library) through `run_src` — i.e., the guest interpreting its own
complete test suite, not just the functions under test — was tried and
abandoned: RSS passed 1.7 GB and was still climbing after 3 minutes on this
machine's 3.8 GB budget before being killed. This is a genuine, first-
measured data point on how guest-level tree-walking cost compounds on a
real (not synthetic-tiny) guest program: two full interpretation levels
deep, on ~680 lines of real source, is expensive enough that even this
single-CPU dev box's normal budget can't absorb it in the round's
remaining time. `test_guest_evaluator_executes_self_host_library` therefore
deliberately keeps its own inner check corpus to a handful of hand-picked
checks (4), not all 66 of `self_host.lang`'s own — proving the mechanism
works without paying the full cost. Flagged as real backlog for a future
"self-hosting round 7" that wants to characterize (not necessarily fix)
guest-eval memory scaling directly, not attempted this round or round 198.

## 5. Verification (round 198, reconciling)

- Full `languages/whence` suite: 850/850 passed (159.6s, single-CPU box).
- All 3 relevant examples run clean: `self_host.lang` 66/66 checks,
  `self_eval.lang` 102/102 checks, `effects.lang` 4/4 checks.
- `tests/test_self_hosting.py` in isolation: 3/3 passed, 22.8s.
- No `ref_diff`/fuzz/guest-differential campaign was re-run this round
  (round 195 already confirmed 0-finding fresh fuzz/guest seeds against
  this exact tree before round 198 started; the diff touched here is
  guest-only .lang source plus test assertions, not `harness/swe/*.py`, so
  there is nothing new for those campaigns to have missed).

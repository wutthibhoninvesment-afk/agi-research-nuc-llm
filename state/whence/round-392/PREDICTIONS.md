# Round 392 (language C) — predictions, banked before any measurement

Whence v0.34 — *the errors that name no cure*.

Rule D-013: everything below is written BEFORE the change is made and
before any of the numbers it predicts are taken. Scored in
`knowledge/round-392-*.md` §7.

---

## §0 OBSERVATIONS ALREADY MADE (not scored — rounds 379/384/385/386/390's discipline, sixth round running)

These were observed during orientation, before this bank was written. They
are the round's premises, not its predictions, and none of them is scored.

1. `state/whence/round-386/replay.json` records 45 parse-error observations
   over the 10 field programs, determinacy `under-extent 22, under-choice
   16, mechanical 4, no-cure 2, under-content 1`.
2. The two `no-cure` observations are
   `prod_demo_v3.lang:41  unexpected '==' at line 41, col 7` and
   `whenceguard_auditor.lang:28  expected (, got 'sum_lines' at line 28, col 29`.
3. A third no-cure error is reachable only by FOLLOWING a mechanical cure:
   `nano_reasoner.lang:31` cured to `let risk_status = "HIGH_RISK"` yields
   `block must end with an expression at line 32, col 5`. SPEC.md's v0.33
   section already names this as the round's own worst case.
4. `whence/parser.py` has 20 `raise ParseError(...)` sites. Four route
   through `_with_hint`; one (`'if' requires 'else'`) carries an inline
   parenthetical; the other 15 carry no hint of any kind.
5. Reproductions at HEAD, all confirmed:
   * `fn f(x) { let y = x + 1 }` → `block must end with an expression`
   * `fn f(x) { }` → `block must contain at least one expression`
   * `let g = fn adder(a, b) { a + b }` → `expected (, got 'adder'`
   * `print(=== H ===)` and a bare `== 2` → `unexpected '=='`
6. A block's bindings do not escape it: `fn f() { let y = 1  y }` then
   `print(y)` at top level is `unbound name 'y'`.
7. `_SYNTAX_HINTS` has exactly two entries, `=` and `rescue`; the `rescue`
   entry is already the sentence "``rescue`` is infix".
8. Parse-error WORDING is explicitly not a guest contract (v0.24 rule 3,
   `test_parse_error_differential.py`); acceptance and POSITION are.
9. `curecheck.py rules` prints 8 cures: 3 mechanical, 5 under-determined.
10. The 14 field programs in `examples/` belong to a separate autonomous
    system and are never written to (`state/known-standing-dirty-paths.json`).

---

## The bank

**P1 — the trailing-statement kinds.** `block must end with an expression`
can be reached with exactly three kinds of trailing statement, and all
three exist: `let`, a named `fn`, and `check`. There is no fourth statement
kind in the grammar that can sit last in a block.

**P2 — the trailing `let` is always dead.** For every program in this tree,
a `let` that is the LAST statement of a block binds a name that no
expression can ever read: the block ends immediately after it and block
bindings do not escape (§0.6). Therefore deleting the text `let NAME =`
from that statement is a semantics-preserving, uniquely-determined edit,
and the hint may demonstrate it. I predict I will find no counter-example
in the tracked corpus.

**P3 — the named-`fn`-expression cure has TWO spellings and the program
decides between them.** Deleting the name is correct iff the fn's body does
not mention the name (self-recursion). `whenceguard_auditor.lang`'s
`sum_lines` body does NOT mention it, so deletion is the right cure there.

**P4 — the recursion branch is reachable and I will need a token scan.** At
the point `expect("(")` fails, the body has not been parsed, so deciding
between P3's two spellings requires a forward TOKEN scan to the matching
`}` — the same mechanism `_bound_anywhere` (v0.33) and the guest's
`shape_close` (round 338) already use. No AST is available.

**P5 — `unexpected '<op>'` generalises.** Every binary operator that
reaches `primary` is an infix operator with no left operand, and the set is
derivable from the parser's own tables rather than hand-typed. I predict
the derived set has between 12 and 16 members and includes `==`, `!=`,
`<`, `<=`, `>`, `>=`, `+`, `*`, `/`, `%`, `and`, `or` — and EXCLUDES `-`
(unary), `not`, `why`, `snip`, `miss` (prefix) and `rescue` (already
tabled).

**P6 — determinacy verdicts.** After v0.34 the three new cures classify as:
block-tail-`let` **mechanical**; fn-expression-name **mechanical**;
infix-no-left-operand **under-content**. `curecheck.py rules` will print
**11 cures, 5 mechanical, 6 under-determined**.

**P7 — the corpus delta.** Re-running `curecheck.py replay` on round 386's
unchanged ledger, the 45 observations will re-classify with **0** `no-cure`
(was 2) and `under-content` rising from 1 to 2. `mechanical` rises from 4
to 5. Total stays 45 and no observation's LINE moves.

**P8 — the corpus mechanical count rises.** `curecheck.py corpus` reports
"3 mechanical edit(s) in total" at HEAD. After v0.34 it reports **more than
3**, because `nano_reasoner.lang`'s cured line 31 now hits a mechanical
block-tail cure instead of a dead end.

**P9 — and following it still does not fix the program.** Even with the new
cure, `curecheck.py corpus` will still report **0 of 10 field programs
fixed mechanically**. The headline number of round 386 does not move.

**P10 — no position moves.** `tests/test_parse_error_differential.py` stays
green with no edit: every change is inside a parenthetical, and rule 2
(positions agree) is untouched. Acceptance is untouched — no program that
parsed stops parsing and none that failed starts.

**P11 — the census instrument.** A new fast-tier test that derives all 20
`raise ParseError` sites from `parser.py`'s own AST and requires each to be
either hinted or listed with a written reason will, on first run against
the post-change tree, find **15 unhinted sites**, of which I will be able
to justify leaving at least **10** unhinted (the message already IS the
cure — `duplicate parameter 'p'`, `comparisons do not chain; use 'and'`,
etc.).

**P12 — nothing in `self_eval.lang` changes.** Zero lines. The guest parser
has no hint machinery and v0.24 rule 3 says wording is not a contract.

**P13 — size.** The whole-round diff is **1400–2600** lines. Rounds 384,
386 and 390 each missed this same prediction low by pricing the code and
forgetting the prose; the code here is ~120 lines of `parser.py`, ~90 of
`curecheck.py`, ~250 of tests, and the rest is SPEC.md, the knowledge file
and this bank.

**P14 — `test_v33.py` goes red before it goes green.**
`test_the_parsers_hint_constants_are_all_owned_by_a_cure_rule` and
`test_no_two_cure_rules_claim_the_same_hint` are the anti-rot pair round
386 built for exactly this event. Adding a hint to `parser.py` without a
matching `curecheck.CURES` rule will fail the first; I predict both fire
during development and both are green at the end.

**P15 — the fast suite.** `bash run_tests_fast.sh` is green at HEAD and
green at the end, with a count that rises by exactly the number of new
tests I add and by nothing else. No existing test is deleted; at most
existing PINS are updated (I predict **at most 2** such pinned-count edits).

**P16 — the surprise will be in `_expect_hint`, not in `block()`.** The
block-tail work is a new hint on a site that has none. The fn-expression
work has to fit inside `_expect_hint`, whose existing juxtaposition rule
keys on `prev.type == "NAME"` — and `fn adder` has `prev` = KW `fn`, so
the two rules cannot collide. I predict they do not, and that the real
difficulty is instead that `want` is the raw string `"("` at that site
(unquoted) while `block()` passes `what="'{'"` (quoted), so the message
renders `expected (, got 'adder'` with inconsistent quoting — a cosmetic
defect I will find and have to decide about.

**P17 — one decision.** v0.34 mints exactly one new SPEC decision (43), and
it is about a hint READING the program rather than only the offending
token. It does not revise decisions 32, 41 or 42.

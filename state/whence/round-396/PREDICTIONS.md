# Round 396 (language C) — predictions, banked before measurement

Task: round 392's next-step item 1 — the `expected (` / `expected '{'`
quoting inconsistency in `whence/parser.py`'s `expect()`. Round 392 found
it, measured the blast radius, deliberately did not do it, and wrote:
*"The edit is one line in `expect`; the cost is that it changes message
BODIES that `curecheck`'s `braced-block` trigger, round 354's tests and
`test_parse_error_differential.py`'s wording assertions all read. Do it as
its own change or decide explicitly not to."*

Banked in ONE block before running anything that produces a number.

## §0 OBSERVATIONS ALREADY MADE (not scorable as foresight)

These were read while orienting and choosing the task. Nothing below can be
scored as a prediction about them.

1. `expect()` is `whence/parser.py:552`; the want is
   `what or (value if value is not None else type_)`.
2. `grep -n "self.expect(" whence/parser.py` returns **28** call sites.
3. **Nine** of those 28 pass a `what=`: lines 1154, 1176, 1231, 1988,
   2004, 2010, 2033, 2178, 2215.
4. Of those nine `what=` values, only **two** quote a token spelling
   (`what="'{'"` at 2033, `what="'@{' after shape name"` at 2004); the
   other seven are bare prose (`parameter name`, `effect name`,
   `shape name`, `field name` x2, `field name after '.'`, `a string
   label after 'check'`).
5. `_show(tok)` (parser.py:175, v0.24/round 360) renders the GOT side and
   already spells the EOF token `end of input`.
6. `curecheck.py` has three triggers that read these bodies:
   `^expected '\{', got ` (line 383, key `braced-block`),
   `^expected \(, got ` (lines 514 and 524), plus a catch-all
   `^(expected .*, got |two statements on one line)` at 396.
7. `tests/test_parse_error_differential.py` declares wording is NOT a
   contract (rule 3) but `test_wording_is_still_not_a_guest_contract`
   asserts `>= 10` differing cases AND names three that must still differ,
   the first being `unclosed-paren` — `expected )` (host) vs
   `expected ')'` (guest).
8. The GUEST (`self_eval.lang` / `self_host.lang` / `meta.lang`) already
   quotes: three `check` lines assert `contains(..., "expected ')'")`.
9. `test_the_corpus_reaches_every_host_parse_error_site` pins
   `declared == 20` `raise ParseError` sites — a different count from the
   28 `expect` sites, and it is NOT the number round 392 quoted.
10. Round 392's sentence says "twenty expect call sites, nine … quoted
    `what`, eleven … the bare token". Observation 2 already contradicts
    the 20, and observation 4 already contradicts the reading of "nine
    quoted".
11. CLAUDE.md's "CRITICAL MISSION" item 1 (fold() returns Miss) was
    already adjudicated by round 349 as an argument-ORDER documentation
    gap, with `_order_hint` shipped in `interp.py`; it is not an open
    regression and this round does not re-open it.

## Predictions

**P1 — Round 392's "twenty … eleven" is wrong in the bare-site term, and
the correct count of `expect` sites that render a BARE token (no `what`)
is 19, not 11.** (28 total − 9 with `what`.) Scored against a re-derivation
that classifies each of the 28 sites.

**P2 — Round 392's "nine … pass a quoted `what`" is wrong as stated**: the
nine pass a `what`, but only 2 of the 9 quote a token. So the inconsistency
is not two-way (quoted vs bare) but THREE-way: quoted-token, bare-token,
and bare-prose. I predict the round file's central table has three classes,
not two.

**P3 — "one line in `expect`" is an underestimate.** A correct fix cannot
be one line, because the bare-token class contains token TYPE names that
are CATEGORIES (`NAME`, `STRING`, `EOF`, `KW`), and quoting those produces
`expected 'NAME'`, which reads as a literal the author should type. I
predict the fix needs a spelling table/function mapping categories to prose
and literals to quotes — >= 8 lines of real logic in `expect` plus a helper.

**P4 — At least one of `NAME`, `STRING`, `EOF` is reachable as a bare
`expected <CATEGORY>` message from the existing differential corpus**, i.e.
this is not a theoretical concern. I predict `NAME` is reachable.

**P5 — `expected EOF` is NOT reachable** from any input: `parse_program`
calls `stmt_list(end="EOF")` first, and `stmt_list` will itself refuse
anything it cannot parse before control returns to the `expect("EOF")`.
Predicted DEAD code path.

**P6 — After the change, `unclosed-paren` CONVERGES**: host and guest both
say `expected ')', got …`, so
`test_wording_is_still_not_a_guest_contract`'s
`assert "unclosed-paren" in names` FAILS and must be re-authored. This is
the single most load-bearing consequence of the change, and it is a
CONVERGENCE (a host/guest divergence closing), not a regression.

**P7 — The `>= 10` differing-cases floor in that same test still holds
after the change.** The guest's `(line N)` implementation coordinate is
stripped before comparison, but the hints (v0.22's five) and
`unexpected token` vs `unexpected` remain host-only, so I predict the
differing count stays >= 10. Banked figure: differing count lands in
[10, 40] after the change.

**P8 — `curecheck.py`'s two `^expected \(, got ` triggers (514, 524) both
stop matching** and must become `^expected '\(', got `. The `braced-block`
trigger at 383 (`^expected '\{', got `) is ALREADY in the post-change
spelling and needs NO edit — the one trigger round 392 named as the cost is
the one trigger that survives untouched.

**P9 — The number of test FILES that fail on first run after the parser
edit is in [3, 7]**, and the number of failing test FUNCTIONS is in
[5, 25].

**P10 — `tests/test_v22.py:363` (`expected ), got 'total'`) and
`tests/test_v24.py:260` (`expected ), got end of input`) both fail**;
`tests/test_spec_builtins.py:184` (`assert "expected '{'" in ...`) does
NOT, because `'{'` was already quoted.

**P11 — SPEC.md needs edits, and the number of SPEC.md LINES containing a
now-stale bare `expected <token>` rendering is in [4, 14].** (Observation
6's grep showed several, but I have not classified which are host output
vs guest output vs prose.)

**P12 — At least one line in the repo asserting a bare `expected (`
rendering lives OUTSIDE `languages/whence/`** — e.g. in `knowledge/` or
`skills/` — and is therefore a stale quotation of a message that no longer
exists. Predicted count outside `languages/whence/`: >= 1.

**P13 — No POSITION moves.** `test_parse_error_differential.py`'s rule 2
(line/col agreement) is untouched by a wording change; I predict zero
position changes and that the rule-2 test passes unedited.

**P14 — The full whence suite is green after the round**, and its collected
count is >= 1782 (round 395's reading) + the tests this round adds.

**P15 — Whole-round diff size lands in [700, 1600] lines** (parser +
tests + SPEC + curecheck + knowledge file + research-state).

**P16 — `whence/foreign.py:10`'s docstring example
(`expected '{', got 'then'`) needs NO edit**, same reason as P8.

**P17 — The guest needs no edit at all.** It already quotes; convergence
happens by the host moving to the guest, not the other way round. Predicted
`self_eval.lang` / `self_host.lang` diff: 0 lines.

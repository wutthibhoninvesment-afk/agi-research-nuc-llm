# Round 398 (language C) — predictions, banked before measurement

Task: round 396's next-step item 1 — *"The guest never received v0.24's
`_show`. It renders a number `'1'` and the EOF token `''` where the host
says `1` and `end of input`. This is now an ISOLATED debt with a known
owner. It is the whole remaining `unclosed-paren` divergence, and closing
it would take the shared-shape agreement from 0/10 to 6/10 in one edit to
`self_eval.lang`/`self_host.lang`. language(C)."*

Banked in ONE block before running anything that produces a number I do
not already have below.

## §0 OBSERVATIONS ALREADY MADE (not scorable as foresight)

Read while orienting and choosing the task. Nothing here is foresight.

1. Host `_show(tok)` is `whence/parser.py:175`: `EOF -> "end of input"`,
   everything else `repr(tok.value)`. It is used at exactly two sites,
   `expect()` (line 609) and the `unexpected %s` catch-all (line 2352).
2. The guest renders the got half at exactly one site,
   `expect_op` (`self_eval.lang:308`), as
   `"got '" + str(t_at(toks, pos).v) + "'"` — quoted unconditionally,
   which is why the EOF token (`v: ""`) prints `''` and a number prints
   `'1'`.
3. The guest's `unexpected` catch-all (`self_eval.lang:492`) writes
   `"unexpected token '" + str(k.v) + "'"`, which is a *different*
   sentence from the host's `unexpected %s`, and it renders the same two
   token kinds the same wrong way (`unexpected token ''` for EOF).
4. `expect_name` (`self_eval.lang:311`) writes **no got half at all**
   (`"expected a name"`), and it is the guest's ONLY name-expecting
   helper — one `what`-less function standing in for seven host sites
   whose `what=` values differ (`a name`, `field name`, `parameter
   name`, `effect name`, `shape name`, `field name after '.'`).
5. The `check` label site (`self_eval.lang:921`) likewise writes no got
   half; the host writes `expected a string label after 'check', got 1`.
6. Measured this round over the differential's 51 rejected programs,
   before any edit: **12 agree, 39 differ**. The 12 agreeing are
   `dup-param`, `dup-record-field`, `chained-compare`, `unknown-type`,
   `reserved-type-name`, `shape-redeclared`, `shape-dup-field`,
   `shape-no-type-name`, `type-out-of-scope`, `bad-escape`,
   `unterminated-str`, `unexpected-char`.
7. `str()` in Whence renders `1`, `1.5`, `100000.0`, `inf`,
   `0.30000000000000004`, `3.0` — byte-identical to Python `repr` for
   every number probed.
8. `values.show_int` caps an integer at `SHOW_INT_BITS = 13287` and
   renders `<integer, N bits>` past it; Python `repr` does not.
9. Host `_show` on a NEWLINE token is `'\n'` (backslash-n, four
   characters), and the token IS reachable: `let x\nlet y = 1` gives
   `expected '=', got '\n' at line 1, col 6`. No program in the
   differential corpus reaches it.
10. Python `repr` of a string switches to double quotes when the value
    contains `'` and no `"` (`repr("a'b") == '"a\'b"'`), and escapes
    `\`, `\n`, `\t`, `\r` and the chosen quote.
11. The guest parser section is pinned byte-identical between
    `examples/self_host.lang` lines 28..927 and `examples/self_eval.lang`
    lines 72..971 by `test_self_eval.py::test_parser_section_matches_self_host`,
    so every edit lands in both files and that test's line bounds move.
12. `test_v23.py::test_both_self_hosting_examples_still_run_green` pins
    `142 passed, 0 failed` for `self_eval.lang` and the file already
    reports 166 — round 396's item 2, a known-red slow-tier test this
    round inherits and whose number this round will move again.

## Predictions

**P1 — Round 396's "0/10 to 6/10" is wrong; the measured post-fix figure
for the ten shared-shape messages will be 5 of 10.** The other five carry
a host-only HINT (`fn-no-body`, `unbraced-if`, and the three
`named-fn-expr*`), which no got-half fix can close. Scored against the
re-run of `test_the_want_half_of_every_shared_message_now_agrees`.

**P2 — the got half is not one bug but three, and the third is the one
round 396 did not name.** (i) rendered wrong at `expect_op`; (ii) rendered
as `unexpected token 'X'` rather than `unexpected X`; (iii) **not rendered
at all** at `expect_name` and the `check` label. Scored by whether the
final diff touches all three kinds and by whether (iii) accounts for more
corpus cases than (i).

**P3 — round 396's `test_the_want_half_of_every_shared_message_now_agrees`
is blind to a want-half disagreement it claims to have closed.** Its
shared set is defined by a regex requiring `, got ` on BOTH sides, so the
five programs where the guest says `expected a name` and the host says
`expected field name` / `expected parameter name` / `expected field name
after '.'` are excluded *because* the guest is missing the got half. I
predict at least 4 such programs exist in the corpus
(`trailing-comma-rec`, `trailing-comma-param`, `trailing-comma-shape`,
`dot-no-field`), i.e. the want half was NOT 10/10 agreed, it was 10/10
agreed *among those the test could see*.

**P4 — after the full fix, the 51-program tally will be 31 agreeing and
20 differing**, and every one of the 20 will fall into exactly two
classes: 18 host-only HINT clauses and the 2 `rebind*` programs (whose
host sentence names the earlier binding's line and the guest's does not).
No third residual class.

**P5 — `test_wording_is_still_not_a_guest_contract` will still pass its
`>= 10 differing` floor** (20 >= 10), so rule 3 does not become vacuous
and does not need relaxing. But two of its three named must-differ
anchors will have to be re-authored: `bare-eof` closes (it is
`unexpected token ''` vs `unexpected end of input`, both halves of which
this round fixes) and the `unclosed-paren` two-half pin closes entirely.
`unbraced-if` survives, on the hint.

**P6 — a token-level parity harness comparing host `_show` against the
guest's new `show_tok` over every token of a corpus will find at least one
divergence the 51-program differential cannot see.** The 51 programs reach
at most 4 token kinds in the got slot; a token-level sweep reaches all of
them. Most likely candidate: the NEWLINE token (observation 9), which no
corpus program reaches.

**P7 — implementing Python `repr`'s quote-switching rule (observation 10)
in Whence will take under 20 lines** and will make host/guest agree on
every token whose value is printable ASCII. The residual after it will be
exactly two kinds: non-printable characters (Python renders `\x00`-style
escapes, which Whence's escape table cannot spell) and integers past
`SHOW_INT_BITS`. I predict the corpus contains ZERO instances of either.

**P8 — `curecheck.py` needs no edit.** Its triggers read HOST messages
(`whence/parser.py`), and this round changes only guest text. Predicted
`curecheck.py corpus` output: unchanged at *"14 file(s): 4 parse, 4 reach
a value (rc=0), 4 mechanical edit(s) applied in total"*.

**P9 — `self_eval.lang`'s own self-check count will rise from 166 and
`self_host.lang`'s from its current value**, so `test_v23.py`'s stale
`142` pin (observation 12) cannot be carried again: this round must
re-derive it. I predict the pin's number and the file's actual number
still disagree by MORE than the count of checks I add, i.e. the 142->166
drift is older debt and not attributable to this round.

**P10 — no host file changes behaviour.** `whence/*.py` gets at most
comments. If a host edit turns out to be needed, that is a MISS and the
finding is that the debt was not guest-only.

**P11 — the guest self-tests will fail on first run of the edited file**,
because at least one existing `check` in `self_eval.lang`/`self_host.lang`
asserts on a message this round changes. I predict 1-4 such checks, and
that they are in the `self_host.lang` block around lines 1129-1155
(`contains(str(parse_whence("1 + 2)")), "unexpected token")` is the
clearest candidate — that string disappears).

**P12 — `test_parser_differential.py` and `test_self_hosting.py` will be
unaffected** (they compare ASTs and values of programs that PARSE), and
`test_miss_message_differential.py` / `test_contract_message_differential.py`
likewise (runtime messages, not parse errors). Zero edits to all four.

**P13 — the fast tier will stay green and its count will rise by exactly
the number of new `tests/test_v36.py` tests plus any added to the
differential**, i.e. from `1812 passed, 3 skipped, 81 deselected`.

**P14 — `expected a name` vs `expected field name` is a REAL diagnostic
regression in the guest, not just a wording difference**, and closing it
is the half of this round with user-visible value: `let r = @{a: 1,}`
told a guest user "expected a name" when the host tells them "expected
field name, got '}'". Unscorable as a number; recorded so the round is
not read as pure string-matching.

## Second block — banked mid-round, before the corpus is widened

P1-P14 above were banked before any edit. Everything in this block is
banked AFTER the guest edit landed and P1-P14 were measured, and BEFORE
three cases are added to `test_parse_error_differential.py`'s `BAD`. It is
scorable as foresight only about the widening.

The three cases and why each is added:
`newline-in-got-slot` (`let x\nlet y = 1`) reaches the NEWLINE token in
the got slot, which observation 9 says no existing case does;
`string-in-got-slot` (`f("a" "b")`) reaches a STRING token there;
`quote-switching-in-got-slot` (`f("a'b" 1)`) reaches Python `repr`'s
double-quote rule (observation 10) through the real message path rather
than only through `bench/showtok.py`.

**P15 — all three new cases will AGREE host-vs-guest**, taking the tally
from 31/20 to 34/20, and the residual classification (18 hint + 2 rebind)
will be unchanged. If any of the three differs, the token-level sweep's
"417 tokens, 0 differ" was measuring the renderer in isolation and missing
something the message path does to it.

**P16 — the three new cases will not change the shared-shape set's want
or got agreement (17 -> 20, all agreeing).**

**P17 — `test_every_guest_parse_error_still_leaks_an_implementation_
coordinate`'s `== 51` will have to become `== 54` and nothing else in
that test changes**; the leak ratio stays 54 of 54.

## Scoring (after all measurement, before the knowledge file was written)

| P | verdict | evidence |
| --- | --- | --- |
| P1 | HIT | of round 396's original ten shared messages, exactly 5 now agree overall; the other 5 carry a host-only hint. Round 396's "6/10" was one high. |
| P2 | HIT | three kinds, all three in the diff. Newly-agreeing cases: kind (i) `expect_op` 5, kind (ii) `unexpected` 7, kind (iii) missing got half 7. (iii) > (i) as predicted. |
| P3 | HIT | 7 programs were excluded from round 396's shared set by the missing got half; 4 of them (`dot-no-field`, `trailing-comma-rec`, `trailing-comma-param`, `trailing-comma-shape`) had a want half that disagreed the whole time. |
| P4 | HIT (exact) | 31 agree / 20 differ before the corpus was widened; 18 close on stripping the host hint, 2 are `rebind`/`rebind-indented`. No third class. |
| P5 | HIT | floor held at 20 >= 10; `bare-eof` and the `unclosed-paren` two-half pin both closed and were re-authored as agreement pins; `unbraced-if` survives on the hint. |
| P6 | **MISS** | the token-level sweep found 417 tokens, 29 token types, 16 keywords, **0** divergences. The prediction was written after the decision to implement `repr_body`'s escape table, so it was predicting a gap the fix had already closed — a prediction about my own completed design, not about the system. The harness's ability to find one is now asserted separately (three planted defects, `test_the_sweep_can_actually_fail`). |
| P7 | HIT | `repr_body` + `repr_str` = 16 lines; residual is exactly non-printables and `SHOW_INT_BITS`; both asserted absent from the corpus. |
| P8 | HIT | `curecheck.py corpus` byte-identical: *14 file(s): 4 parse, 4 reach a value (rc=0), 4 mechanical edit(s) applied in total*. |
| P9 | HALF | the drift half is confirmed and now MEASURED (142 at `5969ded` r360, 159 at `dbf1042` r380, 166 at `54a74c7` r390) — older debt, not this round's. But `self_eval.lang` did NOT move: the new checks belong to the shared PARSER section, whose self-tests live in `self_host.lang` (133 -> 140). I predicted the wrong file. |
| P10 | HIT | `whence/*.py` is byte-unchanged this round — not even a comment. |
| P11 | HIT | exactly 2 checks failed on the first run, both the `unexpected token` ones, at `self_host.lang:1208`/`1212` — the lines named in the prediction. |
| P12 | HIT | `test_parser_differential.py`, `test_self_hosting.py`, `test_miss_message_differential.py`, `test_contract_message_differential.py`: zero edits, all green. |
| P13 | HIT | 1812 -> 1842 = +30 = 18 (`test_v36.py`) + 12 (differential). |
| P14 | unscored | recorded as the round's user-visible half; see § the diagnostic regression in the knowledge file. |
| P15 | HIT | 34/20 after the widening, residual classification unchanged. |
| P16 | HIT | shared 17 -> 20, want and got agreement 20 of 20. |
| P17 | HIT | `== 51` -> `== 54`, leak ratio 54 of 54, nothing else in that test changed. |

**15 HIT (one exact), 1 HALF, 1 MISS, 1 unscored, of 18.**

The MISS and the HALF share a shape worth naming: both predicted the
behaviour of an artefact I had already decided how to build. P6 predicted
a gap my own escape table had closed before the sentence was written; P9
predicted which FILE would move without asking which file owns the
section the change lands in. A prediction about your own design decision
is not foresight about the system.

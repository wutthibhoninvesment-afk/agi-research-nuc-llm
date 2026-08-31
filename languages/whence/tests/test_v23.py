"""v0.23 (round 356) — decision 33: a line break is the only statement
separator Whence has, and it is REQUIRED between two statements.

Where this came from. Round 354 shipped decision 32 ("an error that can
name the fix, names it") and measured it against the ten machine-written
Whence programs a separate system leaves in `examples/`: 1/10 named a cure
before, 9/10 after. The tenth, `prod_demo_v4.lang`'s `let d = f one, two`,
could not be hinted at all — not because the hint was missing but because
the parser ACCEPTED the mistake. `stmt_list` looped `statement()` until its
end token and treated newlines as optional, so `let d = f` and `one` were
two complete statements sharing a line; the juxtaposition was swallowed and
the error surfaced three tokens later at the `,`, where no adjacency was
visible any more. Round 354 pinned that as a grammar property and named the
separator as the largest open item it left.

The rule has three parts, and the second and third are the ones that make
it a design decision rather than a restriction:

  1. Between two statements, at least one NEWLINE. Nothing is required
     before the first or after the last — `at(end)` closes a block.
  2. Only for a token that could actually START a statement. `x = 2` is an
     attempted assignment, not two statements, and decision 32 already says
     the useful thing about it; a separator rule that shadowed that would
     have made v0.22's own regression tests go quiet.
  3. The error names the cure, like every other v0.22-era parse error —
     and where the two adjacent tokens are NAMEs it defers to the
     juxtaposition hint, because "put it on the next line" is advice for a
     mistake the author did not make.

Guest parity: `examples/self_host.lang`'s `parse_stmt_list` implements the
same rule, and `examples/self_eval.lang` carries the byte-identical copy.
Host and guest agree on ACCEPT/REFUSE, not on wording — parse-error wording
has never been a guest contract (`test_v22.py::
test_parse_error_wording_is_not_a_guest_contract`).
"""

import os
import re
import subprocess
import sys

import pytest

from whence.interp import Interpreter
from whence.lexer import KEYWORDS, ONE_CHAR_OPS, TWO_CHAR_OPS, LexError
from whence.parser import (ParseError, parse, _STARTS_STATEMENT_KWS,
                           _STARTS_STATEMENT_TYPES)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF_HOST = os.path.join(ROOT, "examples", "self_host.lang")


def parse_error(src):
    with pytest.raises(ParseError) as ei:
        parse(src)
    return str(ei.value)


# --- part 1: the rule ---------------------------------------------------------

REFUSED = [
    'let a = 1 let b = 2\n',
    'let a = 1 a\n',
    'fn f(x) { x } let y = f(1)\n',
    'fn f() { let x = 1 x }\nlet r = f()\n',
    '1 2\n',
    'let a = 1 if true { 1 } else { 2 }\n',
    'let a = 1 shape P = @{x: num}\nlet r = 1\n',
    'let a = 1 @{x: 1}\n',
    'let a = 1 { 2 }\n',
    # `-`, `(` and `[` also CONTINUE an expression, so they only ever reach
    # the separator check after a statement the expression grammar cannot
    # extend — a `fn` definition or a `shape` declaration. See
    # `test_a_token_that_also_continues_an_expression_is_absorbed_first`.
    'fn f() { 1 } -2\n',
    'fn f() { 1 } (2)\n',
    'fn f() { 1 } [1]\n',
    'shape P = @{x: num} (2)\nlet r = 1\n',
    'let a = 1 "s"\n',
    'let a = 1 not true\n',
    'let a = 1 why a\n',
    'check "x": true check "y": true\n',
]


@pytest.mark.parametrize("src", REFUSED)
def test_two_statements_on_one_line_are_refused(src):
    assert parse_error(src).startswith("two statements on one line ")


@pytest.mark.parametrize("src", REFUSED)
def test_the_same_program_parses_once_the_newline_is_there(src):
    """Every refusal above is a MISSING NEWLINE and nothing else: putting
    one where the error points makes the identical program parse. Without
    this the suite could not tell decision 33 from a parser that had simply
    stopped accepting those constructs."""
    e = None
    try:
        parse(src)
    except ParseError as exc:
        e = exc
    assert e is not None
    lines = src.splitlines()
    bad = lines[e.line - 1]
    lines[e.line - 1] = bad[:e.col - 1] + "\n" + bad[e.col - 1:]
    parse("\n".join(lines) + "\n")


def test_nothing_is_required_before_the_first_statement_or_after_the_last():
    parse('\n\n\nlet a = 1\n')
    parse('let a = 1')                       # no trailing newline
    parse('fn f() { 1 }\nlet r = f()')
    parse('fn f() { let x = 1\n  x }\nlet r = f()\n')   # `x }` closes, no NL


def test_a_run_of_newlines_is_one_separator():
    parse('let a = 1\n\n\n\nlet b = 2\n')


def test_a_comment_is_not_a_separator_but_the_newline_after_it_is():
    # `#` runs to end of line and the lexer emits the NEWLINE that follows,
    # so a trailing comment separates; a comment cannot separate on its own
    # because there is no way to write one that does not end the line.
    parse('let a = 1 # trailing\nlet b = 2\n')


def test_the_rule_applies_inside_blocks_not_only_at_top_level():
    assert parse_error('fn f() { let x = 1 x }\nlet r = f()\n').startswith(
        "two statements on one line ")
    assert parse_error('if true { let x = 1 x } else { 2 }\n').startswith(
        "two statements on one line ")


def test_a_block_inside_a_calls_parens_still_separates_on_newlines():
    """`(`/`[`/`@{` suppress newlines; `{` does not, because blocks contain
    statements. `examples/effects.lang` is the tracked program that had to
    change for v0.23 and this is the shape it changed into."""
    parse('fn g(f, xs) { f(0, xs) }\n'
          'let r = g(fn(acc, x) {\n'
          '  let y = x\n'
          '  acc + y\n'
          '}, [1])\n')
    assert parse_error('fn g(f, xs) { f(0, xs) }\n'
                       'let r = g(fn(acc, x) { let y = x acc + y }, [1])\n'
                       ).startswith("two statements on one line ")


def test_a_token_that_also_continues_an_expression_is_absorbed_first():
    """The honest limit of decision 33, and it is a grammar property rather
    than a gap in the rule.

    `-`, `(` and `[` are the three tokens that can both START a statement
    and CONTINUE an expression (subtraction, a call, an index). After an
    expression statement the longest-match expression grammar has already
    consumed them by the time `stmt_list` looks, so `let a = 1 -2` is one
    statement binding `-1` and no separator error is possible — the same
    hazard automatic-semicolon-insertion languages have, and Whence has it
    in exactly three places instead of everywhere.

    They DO reach the check after a statement the expression grammar cannot
    extend, which is what the `fn`/`shape` cases in `REFUSED` cover. `.` is
    the fourth continuation token and is not a statement head at all, so it
    keeps its own `unexpected '.'`.
    """
    assert len(parse('let a = 1 -2\n').stmts) == 1
    assert len(parse('let a = 1 (2)\n').stmts) == 1
    assert len(parse('let a = 1 .x\n').stmts) == 1
    # an index, so `1 [1, 2]` fails on the index grammar rather than parsing
    assert parse_error('let a = 1 [1, 2]\n').startswith("expected ']'")
    assert parse_error('fn f() { 1 } .x\n') == "unexpected '.' at line 1, col 14"


def test_the_error_points_at_the_second_statements_first_token():
    e = None
    try:
        parse('let a = 1\nlet b = 2 let c = 3\n')
    except ParseError as exc:
        e = exc
    assert (e.line, e.col) == (2, 11)


# --- part 2: only tokens that can start a statement --------------------------

def _token_inventory():
    """(source text, token value) for every token the lexer can produce."""
    out = [(kw, kw) for kw in sorted(KEYWORDS)]
    out += [(op, op) for op in sorted(set(TWO_CHAR_OPS) | set(ONE_CHAR_OPS))]
    out += [("1", 1), ('"s"', "s"), ("abc", "abc")]
    return out


def _empirically_starts_a_statement(text, value):
    """True iff the parser will try to build a statement out of `text`.

    Derived from the parser, not from the constant under test: a token that
    cannot start a statement is exactly one `primary()` refuses with its own
    fallback (`unexpected <that token>`). Any other outcome — a clean parse,
    or an error about what should have FOLLOWED it — means the token was
    accepted as a statement head.
    """
    try:
        parse(text + "\n")
        return True
    except ParseError as e:
        return not str(e).startswith("unexpected %r" % (value,))


def test_every_token_is_classified_by_whether_it_can_start_a_statement():
    """The two constants are a cache of a fact the parser already knows, and
    this is the re-derivation. If a future version gives some token a new
    statement-head role and forgets these sets, the separator error silently
    stops firing in front of it — a hole nothing else would notice, because
    the program would go back to parsing as two statements."""
    inventory = _token_inventory()
    assert len(inventory) == 40, len(inventory)
    mismatched = []
    for text, value in inventory:
        empirical = _empirically_starts_a_statement(text, value)
        if text in KEYWORDS:
            declared = text in _STARTS_STATEMENT_KWS
        elif text in ("1", '"s"', "abc"):
            declared = {"1": "NUMBER", '"s"': "STRING",
                        "abc": "NAME"}[text] in _STARTS_STATEMENT_TYPES
        else:
            declared = text in _STARTS_STATEMENT_TYPES
        if empirical != declared:
            mismatched.append((text, empirical, declared))
    assert not mismatched, mismatched


def test_the_four_keywords_that_cannot_start_a_statement_are_the_infix_ones():
    # `and`/`or`/`rescue` are infix and `else` only ever follows a block:
    # every keyword that is not a statement head is one that needs a left
    # operand, which is why none of them can be a "second statement".
    assert set(KEYWORDS) - _STARTS_STATEMENT_KWS == {
        "and", "or", "rescue", "else"}


DEFERRED = [
    # (source, the message v0.22 already gives, which v0.23 must not shadow)
    ('let x = 1\nx = 2\n',
     "unexpected '=' (Whence has no assignment; a name binds once "
     "— write `let name = value`) at line 2, col 3"),
    ('let x = 1\n1 + 2)\n', "unexpected ')' at line 2, col 6"),
    ('let x = 1\n1 , 2\n', "unexpected ',' at line 2, col 3"),
    ('let x = 1\nx else 2\n', "unexpected 'else' at line 2, col 3"),
]


@pytest.mark.parametrize("src,want", DEFERRED)
def test_a_token_that_starts_no_statement_keeps_its_own_diagnosis(src, want):
    assert parse_error(src) == want


# --- part 3: the error names the cure ----------------------------------------

SEP = "a line break is the only statement separator Whence has"
JUX = "two names in a row: Whence has no juxtaposition"

HINT_CASES = [
    ('let a = 1 let b = 2\n',
     "two statements on one line (%s — start `let` on the next line) "
     "at line 1, col 11" % SEP),
    ('let a = 1 2\n',
     "two statements on one line (%s — start `2` on the next line) "
     "at line 1, col 11" % SEP),
    ('let a = 1 "s"\n',
     'two statements on one line (%s — start `"s"` on the next line) '
     "at line 1, col 11" % SEP),
    ('fn f() { 1 } (2)\n',
     "two statements on one line (%s — start `(` on the next line) "
     "at line 1, col 14" % SEP),
    # a NAME touching a NAME is a paren-less call or an unquoted string, and
    # the newline is not the cure for either — this is the case that made
    # `prod_demo_v4.lang` undiagnosable in v0.22.
    ('let d = f one, two\n',
     "two statements on one line (%s — a call is `f(x)` and text must "
     "be quoted) at line 1, col 11" % JUX),
    # ...but a `shape` HEAD after a statement really is a separator error:
    # `shape` is a soft keyword, so it lexes as a NAME and would otherwise
    # draw the juxtaposition hint for a mistake nobody made. The previous
    # statement has to END in a NAME for the two rules to disagree, which is
    # why `b` and not `1` — with `1` in front, both rules give the same
    # answer and the case proves nothing (found by mutation).
    ('let a = b shape P = @{x: num}\nlet r = 1\n',
     "two statements on one line (%s — start `shape` on the next line) "
     "at line 1, col 11" % SEP),
    # `shape` as the PREVIOUS token is the other half of the same exclusion,
    # inherited from `_expect_hint`: `shape NAME` is the one legal NAME NAME
    # adjacency, so a `shape` on the left never means juxtaposition either.
    ('let shape = 1\nlet x = shape foo\n',
     "two statements on one line (%s — start `foo` on the next line) "
     "at line 2, col 15" % SEP),
    # ...and `shape P` WITHOUT the `=` is not a head, so it is juxtaposition
    # again. Three cases, three branches of `_separator_hint`.
    ('let a = b shape P\n',
     "two statements on one line (%s — a call is `f(x)` and text must "
     "be quoted) at line 1, col 11" % JUX),
]


@pytest.mark.parametrize("src,want", HINT_CASES)
def test_separator_error_wording(src, want):
    assert parse_error(src) == want


def test_the_hint_is_additive_and_never_replaces_the_diagnosis():
    """Same rule decision 32 set for itself: the clause is appended in
    parentheses, and the sentence in front of it still says what went
    wrong on its own."""
    for src, _ in HINT_CASES:
        msg = parse_error(src)
        assert msg.startswith("two statements on one line (")
        assert msg.split(" (")[0] == "two statements on one line"


def test_a_shape_head_after_a_name_is_the_one_name_name_pair_still_legal():
    # the adjacency `shape P` itself, on its own line, is untouched.
    parse('shape P = @{x: num}\nlet r = 1\n')


# --- part 4: guest parity ----------------------------------------------------

def _guest_library():
    src = open(SELF_HOST, encoding="utf-8").read()
    # self_host.lang has no SELF-TESTS marker; its checks run from the top
    # level, so the whole file is the library and its own 112 checks run
    # alongside. Cheaper to cut at the tests banner.
    marker = "# ---- tests: lexer "
    assert marker in src
    return src.split(marker)[0]


def test_guest_start_sets_match_the_hosts():
    """The guest lists the same tokens the host's two frozensets do, read
    out of `self_host.lang` rather than restated here. The guest's NUMBER/
    STRING/NAME cases are its `else` branch, so only the operators are a
    list on that side."""
    lib = open(SELF_HOST, encoding="utf-8").read()
    kws = re.search(r"let stmt_start_kws = \[(.*?)\]", lib, re.S).group(1)
    ops = re.search(r"let stmt_start_ops = \[(.*?)\]", lib, re.S).group(1)
    guest_kws = set(re.findall(r'"([^"]+)"', kws))
    guest_ops = set(re.findall(r'"([^"]+)"', ops))
    assert guest_kws == set(_STARTS_STATEMENT_KWS)
    assert guest_ops == set(_STARTS_STATEMENT_TYPES) - {
        "NUMBER", "STRING", "NAME"}


GUEST_CORPUS = REFUSED + [
    'let a = 1\nlet b = 2\n',
    'let a = 1\n\n\nlet b = 2\n',
    'let a = 1 # c\nlet b = 2\n',
    'fn f() { let x = 1\n  x }\nlet r = f()\n',
    'let x = 1\nx = 2\n',
    'let x = 1\n1 + 2)\n',
    '1\n2\n',
]


@pytest.mark.whence_slow
def test_host_and_guest_agree_on_which_programs_the_separator_rule_refuses():
    """One interpreter run over the whole corpus (the ~900-line library is
    loaded once). Missed-ness must agree program for program; the WORDING is
    exempt by design and `test_v22.py::
    test_parse_error_wording_is_not_a_guest_contract` is what pins that."""
    lib = _guest_library()
    prog = [lib]
    for i, src in enumerate(GUEST_CORPUS):
        esc = (src.replace("\\", "\\\\").replace('"', '\\"')
                  .replace("\n", "\\n"))
        prog.append('let g%d = missed(parse_whence("%s"))\n' % (i, esc))
    env = Interpreter().run("".join(prog))

    disagreements = []
    for i, src in enumerate(GUEST_CORPUS):
        try:
            parse(src)
            host_refused = False
        except (ParseError, LexError):
            host_refused = True
        guest_refused = env.get("g%d" % i).value
        if host_refused != guest_refused:
            disagreements.append((src, host_refused, guest_refused))
    assert not disagreements, disagreements


@pytest.mark.whence_slow
def test_the_guest_miss_names_the_line_the_second_statement_is_on():
    lib = _guest_library()
    env = Interpreter().run(
        lib + 'let out = str(parse_whence("let a = 1\\nlet b = 2 let c = 3"))\n')
    assert "two statements on one line at line 2" in env.get("out").value


@pytest.mark.whence_slow
def test_both_self_hosting_examples_still_run_green():
    # round 360 (v0.24): 112 -> 133 in self_host.lang, decision 34's own
    # 21 checkpoint checks. self_eval.lang was unchanged at 142: its checks
    # exercise the guest EVALUATOR, and v0.24 touched the shared PARSER
    # section only.
    #
    # ROUND 398 re-derived both numbers, which is the point of this note.
    # Round 396 found `self_eval.lang`'s pin reading 142 against an actual
    # 166 and deliberately did not re-pin it, because a number nobody has
    # ACCOUNTED FOR is the same defect whichever value it holds --- round
    # 321's item 14 as round 333 rescoped it, *a line asserting a number
    # that no round re-executes*. The accounting, measured by running the
    # historical file at each revision that moved it rather than by
    # counting `check` lines in a diff:
    #
    #   142  round 360 `5969ded`   the pin, correct when written
    #   142  round 380 `b36a751`
    #   159  round 380 `dbf1042`   v0.31, +17 (diverge/contrast answers)
    #   166  round 390 `54a74c7`   +7  (the clause that shipped on one side)
    #   166  round 392 `1b18b2c`, and today
    #
    # Neither round 380 nor round 390 touched this line, and the fast tier
    # cannot see it (`whence_slow`), so it went 18 rounds wrong. THE PIN
    # ITSELF IS NOT THE FIX --- the fix is that the number is now derived
    # from a measurement anyone can repeat, in this comment.
    #
    # `self_host.lang` 133 -> 140 IS this round's doing: v0.36 decision 45
    # adds seven parse-error checks (the got half's five token kinds, and
    # the two `expect_name` sites that used to say `a name` for everything).
    for name, expected in (("self_host.lang", "145 passed, 0 failed"),
                           ("self_eval.lang", "166 passed, 0 failed")):
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "run.py"),
             os.path.join(ROOT, "examples", name)],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert expected in r.stdout, (name, r.stdout[-400:])

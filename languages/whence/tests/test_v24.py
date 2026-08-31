"""Whence v0.24 (round 360, language C) — decision 34: a position is a fact
about the program, and both implementations must be able to state it.

The guest side is `tests/test_parse_error_differential.py` and
`tests/test_lexer_guest_parity.py`. This file is the HOST side: the three
defects that giving the guest columns exposed in `whence/lexer.py` and
`whence/parser.py`, and the oracle that would have caught the first one.

  1. `tokenize`'s comment branch advanced the index and not the column, so
     the NEWLINE token after a trailing comment — and the EOF token after a
     comment at end of file — carried the `#`'s column. 10 of the 16
     git-tracked `examples/*.lang` files.
  2. `stmt_list`'s no-rebinding error passed a literal `0` as its column.
  3. The EOF token's `value` is Python `None`, and two sites rendered it
     with `%r`: `unexpected None`, `expected ), got None`.

All three had survived 359 rounds for the same reason: a column is only
ever read by an error message, error messages were only ever asserted by
their words, and no test had ever asked for the column of a NEWLINE or an
EOF token — the only two kinds a comment can precede.
"""

import os
import re
import subprocess

import pytest

from whence.lexer import _DIGITS, LexError, tokenize
from whence.parser import ParseError, _show, _spell, parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(ROOT))


# --------------------------------------------------------------------------
# the oracle: a token's (line, col) points at the token's own first character
# --------------------------------------------------------------------------
# Independent of the guest, of the lexer's own bookkeeping, and of any
# expected-value literal: given the source and a token, there is exactly one
# right answer and it can be read straight out of the text. This is what a
# `col` MEANS, and nothing in this repo had ever said so.

def line_starts(src):
    starts = [0]
    for i, ch in enumerate(src):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def position_errors(src):
    """Every token whose (line, col) does not point at its own first char."""
    starts = line_starts(src)
    bad = []
    for tok in tokenize(src):
        if not (1 <= tok.line <= len(starts)):
            bad.append((tok, "line out of range"))
            continue
        idx = starts[tok.line - 1] + tok.col - 1
        if tok.type == "EOF":
            ok = idx == len(src)
        elif idx >= len(src):
            ok = False
        elif tok.type == "NEWLINE":
            ok = src[idx] == "\n"
        elif tok.type == "NUMBER":
            ok = src[idx] in _DIGITS
        elif tok.type == "STRING":
            ok = src[idx] == '"'
        elif tok.type in ("NAME", "KW"):
            ok = src.startswith(tok.value, idx)
        else:                       # an operator: its type IS its spelling
            ok = src.startswith(tok.type, idx)
        if not ok:
            bad.append((tok, repr(src[max(0, idx - 3):idx + 6])))
    return bad


HAND = [
    ("trailing-comment",     "let x = 1 # c\nlet y = 2\n"),
    ("comment-whole-line",   "# just a comment\nlet x = 1\n"),
    ("comment-at-eof",       "let x = 1\n# end"),
    ("comment-only",         "# only"),
    ("two-comments",         "let a = 1 # one\nlet b = 2 # two\n"),
    ("comment-in-parens",    "let x = (1 # c\n)"),
    ("tabs",                 "let\tx\t=\t1\n"),
    ("crlf",                 "let x = 1\r\nlet y = 2\r\n"),
    ("strings",              'let s = "a\\tb"\nlet t = "c"\n'),
    ("exponents",            "let e = 1e5 + 2.5E2 - 1e-3\n"),
    ("ops",                  "let z = a == b != c <= d >= e -> f\n"),
    ("record",               "let r = @{a: 1,\nb: 2}\n"),
    ("plain",                "let x = 1\nlet y = x + 2\n"),
]


@pytest.mark.parametrize("name,src", HAND, ids=[n for n, _ in HAND])
def test_every_token_position_points_at_its_own_first_character(name, src):
    assert position_errors(src) == [], (name, position_errors(src))


# The examples this repo DECIDED to track, by name.
#
# round 355: git, not the directory — `examples/` is shared with a separate
# system's untracked output.
# 16 -> 17 in round 380: `show.lang`, the example v0.29's `show` builtin had
# never had (round 378's item 8).
# 17 -> 18 in round 384: `dropped.lang`, v0.32's example, and the only one in
# the corpus that discards a miss on purpose (tests/test_v32.py::
# DROPS_ON_PURPOSE).
#
# 18 -> 32 in round 395 (SWE-loop D), and this one was not a decision anybody
# made. Round 393's `git add -A` sweep (commit `49969fb`) tracked the
# fourteen FIELD_CORPUS files below, which round 355's premise assumed would
# stay untracked. The old form of this code was
#
#     assert len(names) == 18, names      # at module level
#     @pytest.mark.parametrize("path", _tracked_examples(), ...)
#
# so the stale pin raised during COLLECTION, and pytest answered
# "Interrupted: 1 error during collection" — 1758 tests never ran, from a
# disagreement about 14 filenames. It stayed that way for rounds 393 and 394;
# `logs/whence_health_round_393.log` and `..._394.log` each recorded it and
# no round read them. Two changes, both about blast radius rather than about
# the pin being wrong:
#
#   1. the check is a TEST, not a module-level assert, so a wrong pin costs
#      one red test instead of the whole file's collection;
#   2. it pins NAMES, not a count, so the failure says which file arrived
#      instead of saying 32 != 18.
#
# All 32 pass the position oracle, so tracking them widened coverage and cost
# nothing; the defect was never the files.
OUR_EXAMPLES = (
    "blame.lang", "checks_demo.lang", "deep.lang", "diverge.lang",
    "dropped.lang", "effects.lang", "failing_check.lang", "guess.lang",
    "hello.lang", "history.lang", "meta.lang", "provenance.lang",
    "sales.lang", "self_eval.lang", "self_host.lang", "shapes.lang",
    "show.lang", "tco.lang",
)
# The other fourteen are the FIELD CORPUS, and their names are NOT repeated
# here: `state/whence/round-384/field-names.json` has declared them since
# round 384 and both `_corpus_unchanged()` in test_v33/test_v34 and
# `curecheck.field_programs()` read it. Read lazily inside the test — a
# module-level read is what took this file's collection down in the first
# place.
FIELD_CENSUS = os.path.join(REPO, "state", "whence", "round-384",
                            "field-names.json")


def _field_corpus():
    import json
    with open(FIELD_CENSUS, encoding="utf-8") as fh:
        return {os.path.basename(k) for k in json.load(fh)["file_md5"]}


def _tracked_examples():
    out = subprocess.run(["git", "ls-files", "languages/whence/examples"],
                         cwd=REPO, capture_output=True, text=True)
    return [os.path.join(REPO, p) for p in out.stdout.split()
            if p.endswith(".lang")]


def test_the_tracked_example_set_is_the_one_this_repo_decided_on():
    """Adding an example is still a decision someone makes here — it just
    costs one red test now, and names the file."""
    got = {os.path.basename(p) for p in _tracked_examples()}
    want = set(OUR_EXAMPLES) | _field_corpus()
    assert got - want == set(), "newly tracked, undeclared: %s" % sorted(
        got - want)
    assert want - got == set(), "declared but no longer tracked: %s" % sorted(
        want - got)


@pytest.mark.parametrize("path", _tracked_examples(),
                         ids=[os.path.basename(p)
                              for p in _tracked_examples()])
def test_every_tracked_example_has_correct_token_positions(path):
    src = open(path, encoding="utf-8").read()
    assert position_errors(src) == [], (path, position_errors(src)[:3])


def test_the_oracle_fails_on_the_pre_v024_lexer():
    """The oracle is only worth having if it catches the bug it was built
    for. Reproduce the old comment branch (index advances, column does not)
    and require the oracle to reject its output on the same case that was
    wrong in 10 of 16 tracked files."""
    src = "let x = 1 # c\nlet y = 2\n"
    toks = tokenize(src)
    nl = [t for t in toks if t.type == "NEWLINE"][0]
    assert (nl.line, nl.col) == (1, 14)
    # the pre-v0.24 value: the column of the `#`
    stale = type(nl)("NEWLINE", "\n", 1, 11)
    starts = line_starts(src)
    assert src[starts[stale.line - 1] + stale.col - 1] == "#"
    assert src[starts[nl.line - 1] + nl.col - 1] == "\n"


def test_only_newline_and_eof_columns_could_ever_have_been_wrong():
    """A comment runs to end of line, so the only tokens it can precede are
    the NEWLINE that ends that line and, at end of file, EOF. Established
    from the lexer's control flow rather than asserted: after the comment
    branch, the next character is `\\n` or the input is exhausted."""
    src = "let x = 1 # a comment with (parens) and 'quotes'\nlet y = 2"
    kinds = [t.type for t in tokenize(src)]
    assert kinds == ["KW", "NAME", "=", "NUMBER", "NEWLINE",
                     "KW", "NAME", "=", "NUMBER", "EOF"]
    for t in tokenize(src):
        if t.line == 1 and t.type not in ("NEWLINE", "EOF"):
            assert t.col <= 9, t          # everything before the `#` at 11


# --------------------------------------------------------------------------
# 2. the no-rebinding error had column 0
# --------------------------------------------------------------------------

def parse_error(src):
    try:
        parse(src)
    except ParseError as e:
        return e
    raise AssertionError("expected a ParseError for %r" % (src,))


def test_the_no_rebinding_error_has_a_real_column():
    e = parse_error("let a = 1\nlet a = 2\n")
    assert (e.line, e.col) == (2, 1), (e.line, e.col)
    assert "col 0" not in str(e)
    assert "'a' is already bound in this block (line 1)" in str(e)


def test_the_no_rebinding_column_is_the_statement_and_not_the_line_start():
    """The fix is `self.peek()` before `self.statement()`, so an indented
    rebinding points at the statement, not at column 1 of its line."""
    e = parse_error("let z = fn() { let b = 1\n  let b = 2 }")
    assert (e.line, e.col) == (2, 3), (e.line, e.col)


def test_the_no_rebinding_line_did_not_move():
    """v0.24 changed the COLUMN. The line was `s.line` (the node's) and is
    now `start.line` (the head token's); for a `let`/`fn` those are the same
    by construction, and these are the three cases that would show it if
    they were not — pinned so this stays a column fix and not a quiet
    relocation of the whole message."""
    assert parse_error("let a = 1\nlet a = 2\n").line == 2
    assert parse_error("let f = 1\nfn f() { 1 }\n").line == 2
    assert parse_error("let q = 1\n\n\nlet q = 2\n").line == 4
    # a multi-LINE second binding still reports at its head, not its tail
    assert parse_error("let m = 1\nlet m = fn() {\n1 }\n").line == 2


# --------------------------------------------------------------------------
# 3. `None` is not a token the author wrote
# --------------------------------------------------------------------------

def test_end_of_input_is_named_at_both_rendering_sites():
    # primary()'s fallback
    assert str(parse_error("let x =")).startswith("unexpected end of input")
    # expect()
    # v0.35 (decision 44) quoted the WANT half; `end of input` is v0.24's
    # own contribution to the GOT half and is what this test is about.
    assert "expected ')', got end of input" in str(parse_error("let x = (1"))


@pytest.mark.parametrize("src", [
    "let x =", "let x = (1", "let x = [1,", "let r = @{a: 1",
    "fn f(a)", "let r = @{a: 1}\nlet v = r.", "let y = if true { 1 }",
    "check", "shape P = @{a: num", "let f = fn()",
])
def test_no_parse_error_ever_renders_a_python_none(src):
    msg = str(parse_error(src))
    assert "None" not in msg, msg


def test_show_is_unchanged_for_every_token_the_author_actually_wrote():
    """Only the EOF arm is new. A string is still quoted, a number is not —
    the two spellings `%r` gave, kept."""
    # The WANT half was respelled by v0.35 (`NAME` -> `a name`, `:` ->
    # `':'`); the GOT half, which is what `_show` owns and what this test
    # asserts, is byte-unchanged.
    assert "expected a name, got '='" in str(parse_error("let = 2"))
    assert "expected ':', got 1" in str(parse_error('check "l" 1 == 1'))
    assert "unexpected ','" in str(parse_error("let x = [,]"))
    assert "expected a name, got 'let'" in str(parse_error("let let = 1"))


def test_show_is_not_spell_and_the_two_must_not_be_merged():
    """`_spell` quotes a token back at the author inside a HINT (a string
    literal keeps its own double quotes, because the hint is telling them
    how to write it); `_show` names the token that stopped the parse. They
    disagree on every STRING token, and `_spell` has no EOF case because a
    hint is never about end of input."""
    class T(object):
        def __init__(self, type_, value):
            self.type, self.value = type_, value
    assert _spell(T("STRING", "hi")) == '"hi"'
    assert _show(T("STRING", "hi")) == "'hi'"
    assert _spell(T("NAME", "x")) == "x"
    assert _show(T("NAME", "x")) == "'x'"
    assert _show(T("EOF", None)) == "end of input"
    # every v0.22 hint fires on a token that was typed, so `_spell` seeing
    # an EOF would itself be the bug — pinned, not defended against.
    import inspect
    assert "EOF" not in inspect.getsource(_spell)
    assert "EOF" in inspect.getsource(_show)


def test_the_v022_hints_still_reach_their_messages():
    """`_show` sits inside `_with_hint`'s first argument at both sites; a
    hint appended to the wrong string is the obvious way to break this
    without breaking any position."""
    assert "Whence has no assignment" in str(parse_error("let a = 1\na = 2"))
    assert "blocks are always braced" in str(parse_error("fn f(a)"))
    assert "records are written" in str(parse_error("let r = {a: 1}"))


# --------------------------------------------------------------------------
# the version header, which round 354 made a test rather than a sentence
# --------------------------------------------------------------------------

def test_spec_documents_v024():
    spec = open(os.path.join(ROOT, "SPEC.md"), encoding="utf-8").read()
    assert re.search(r"^## v0\.24 ", spec, re.M), "no `## v0.24` section"
    assert "decision 34" in spec.lower() or "Decision 34" in spec

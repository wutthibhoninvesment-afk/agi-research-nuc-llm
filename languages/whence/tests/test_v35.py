"""v0.35 (round 396), decision 44 --- what `expect` says it wanted.

Every Whence parse error from `Parser.expect` is one sentence with two
halves: what was wanted, and what stopped the parse. `_show` (v0.24, round
360) fixed the second half, which used to render the EOF token's Python
`None`. The first half was never touched, and until v0.35 it was written in
a different language from the second:

    expected ), got '='            <- want bare, got quoted
    expected '{', got 'then'       <- want quoted, two call sites later
    expected NAME, got '='         <- want is an IMPLEMENTATION identifier

The third is the worst of the three. `NAME` is a token type in
`whence/lexer.py`; there is no program text an author can type that is
spelled `NAME`, so the message names an internal symbol in the slot where
it is telling somebody what to write.

Decision 44: **a `want` is either a quoted literal the author can type
verbatim, or prose. Never a bare token, never an implementation
identifier.** `_spell_want` is the whole rule, and the three bare kinds do
not get the same treatment --- punctuation and keywords are quoted, a
CATEGORY becomes prose (`expected a name`), because quoting a category
would read as an instruction to type it.

WHAT IS PINNED HERE, and the four kinds are not the same claim:

  1. THE RULE (section 1). `_spell_want`'s table, and the invariant it
     establishes, asserted over every `self.expect(...)` site found by
     reading `parser.py`'s AST --- never over a list in this file.
  2. THE CATEGORY SET (section 2). `_CATEGORY_PROSE` covers every category
     type any `expect` site actually passes, where "category" is derived
     from the LEXER's own behaviour, not listed here.
  3. REACHABILITY (section 3). Six of the 28 sites can never fail. That is
     not a guess: `bench/expectsites.py` instruments `Parser.expect` and
     counts executions against raises over a corpus. Their wording is
     unobservable and this file says which six and why, so that a grammar
     change that makes one reachable fails HERE rather than shipping a
     message nobody chose.
  4. THE DOWNSTREAM READERS (sections 4-5). `_expect_hint` dispatches on
     the SPELLING of `want`, and `curecheck`'s two `fn-expression-*` rules
     trigger on the message body. Both were changed by decision 44 and
     both are asserted to still fire.

Section 6 is the convergence. v0.24 rule 3 says parse-error wording is not
a host/guest contract, and `test_parse_error_differential.py` asserts that
as a live fact. Decision 44 closes one of the three divergences that test
names --- `unclosed-paren` --- because the GUEST parser has quoted the
token it wanted since it was written, and the host has now moved to it.
Round 354 recorded the disagreement; nobody had recorded that the guest was
the one in the right.
"""

import ast
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (ROOT, os.path.join(ROOT, "bench")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from whence.lexer import tokenize                              # noqa: E402
from whence.parser import (ParseError, parse, _CATEGORY_PROSE,  # noqa: E402
                           _spell_want)

import expectsites as E                                        # noqa: E402


def parse_error(src):
    with pytest.raises(ParseError) as ei:
        parse(src)
    return str(ei.value)


@pytest.fixture(scope="module")
def swept():
    """Every `expect` site, with execution/raise counts from a real run.

    The corpus is `bench/expectsites.py`'s three offline ones (the parse-
    error differential's own BAD+GOOD, every example, and one handwritten
    input per site). ~1.7 s, no mutations --- the mutation search is what
    the round ran to EARN the claim in section 3; this fixture only has to
    reproduce it.
    """
    sites = E.sites()
    E.sweep(sites, E.build_corpus(
        ["differential", "examples", "handwritten"], 0))
    return sites


# --------------------------------------------------------------------------
# 1. the rule
# --------------------------------------------------------------------------

def test_spell_want_quotes_a_literal_and_spells_a_category():
    assert _spell_want(")", None, None) == "')'"
    assert _spell_want("@{", None, None) == "'@{'"
    assert _spell_want("KW", "if", None) == "'if'"
    assert _spell_want("NAME", None, None) == "a name"
    assert _spell_want("EOF", None, None) == "end of input"


def test_an_explicit_what_always_wins_unchanged():
    """Seven of the nine `what=` sites are prose that says more than any
    token can, and the other two wrote their own quotes. `_spell_want` must
    not second-guess either."""
    assert _spell_want("NAME", None, "parameter name") == "parameter name"
    assert _spell_want("{", None, "'{'") == "'{'"
    assert (_spell_want("STRING", None, "a string label after 'check'")
            == "a string label after 'check'")


def test_every_expect_site_wants_a_quoted_literal_or_prose():
    """The invariant, over the parser's AST rather than over a list.

    A `want` is well-formed iff it is wrapped in single quotes (a literal
    the author types verbatim) or begins with a lowercase letter (prose).
    `NAME`, `EOF` and `STRING` satisfy neither, which is exactly what
    decision 44 removed.
    """
    bad = [(s.line, s.want) for s in E.sites()
           if not (s.want.startswith("'") or s.want[:1].islower())]
    assert bad == [], bad


def test_no_want_is_a_bare_token_type():
    types = set(_CATEGORY_PROSE) | {"KW", "NEWLINE"}
    offenders = [(s.line, s.want) for s in E.sites() if s.want in types]
    assert offenders == [], offenders


def test_the_five_rendering_classes_are_still_the_five():
    """Round 392 priced this change by hand as "twenty call sites, nine
    quoted, eleven bare". There are 28, and the bare half is three kinds,
    not one. The numbers are pinned so the next round to price it reads a
    measurement."""
    from collections import Counter
    c = Counter(s.kind for s in E.sites())
    assert sum(c.values()) == 28, c
    assert c == {"bare-punct": 15, "bare-prose": 7, "bare-category": 3,
                 "quoted-token": 2, "bare-keyword": 1}, c


# --------------------------------------------------------------------------
# 2. the category set, derived from the lexer
# --------------------------------------------------------------------------

def test_the_category_types_are_derived_from_the_lexer_not_listed():
    """A CATEGORY is a type the lexer emits with a value that is not the
    type's own name. Punctuation is `Token(")", ")")`; `NAME` is
    `Token("NAME", "x")`. Deriving it means a new category token cannot
    appear without this set noticing."""
    probe = 'let a = 1\nlet s = "t"\nfn f(x) { x }\nlet r = @{k: [a]}\n'
    derived = {t.type for t in tokenize(probe) if t.type != t.value}
    assert derived == {"NAME", "STRING", "NUMBER", "KW", "NEWLINE", "EOF"}
    assert derived == set(E.CATEGORY_TYPES)


def test_every_category_an_expect_site_passes_has_prose():
    """The anti-rot clause. `_spell_want` QUOTES anything it does not
    recognise as a category, so an `expect("NUMBER")` added tomorrow would
    silently render `expected 'NUMBER'` --- the exact defect decision 44
    removed, reintroduced by omission rather than by edit."""
    missing = sorted({s.type_ for s in E.sites()
                      if s.what is None and s.value is None
                      and s.type_ in E.CATEGORY_TYPES
                      and s.type_ not in _CATEGORY_PROSE})
    assert missing == [], missing


# --------------------------------------------------------------------------
# 3. which of the 28 can actually fail
# --------------------------------------------------------------------------

#: The six sites that are EXECUTED and can never RAISE, each with the guard
#: upstream that already established the token. Keyed by the `expect` call's
#: own guard rather than by line number, which moves on every edit above it.
DEAD = {
    "parse_program:EOF":
        "`stmt_list(end='EOF')` loops `while not self.at(end)`, so it "
        "returns only when the EOF is already under the cursor",
    "statement:fn NAME":
        "the branch is guarded by `peek(1).type == 'NAME'` and `next()` "
        "eats only the `fn`",
    "shape_def:NAME":
        "`statement` enters `shape_def` only on `NAME NAME =`, so the "
        "shape name is the token after the one `next()` eats",
    "shape_def:=":
        "the same guard already tested `peek(2).type == '='`",
    "block:}":
        "`stmt_list(end='}')` has the same `while not self.at(end)` "
        "contract as `parse_program`'s",
    "if_expr:KW if":
        "both callers test `at('KW', 'if')` before calling `if_expr`",
}


def test_exactly_six_expect_sites_can_never_fail(swept):
    """Executed thousands of times each, never once raised.

    This is the fact that shrinks the change: 28 sites have a rendering,
    22 have a rendering an author can SEE. The round searched for a
    counterexample with 3000 single-token mutants of every example on top
    of this corpus and found none.
    """
    dead = [s for s in swept if s.outcome == "never-fails"]
    assert len(dead) == len(DEAD) == 6, [(s.line, s.want) for s in dead]
    assert all(s.executed > 0 for s in dead), \
        [(s.line, s.executed) for s in dead]
    assert sum(s.raised for s in dead) == 0


def test_no_expect_site_is_merely_unreached(swept):
    """`never-fails` is a claim about the GRAMMAR; `unexecuted` would be a
    claim about the corpus. Keeping the second at zero is what entitles the
    first to be called dead code rather than untested code."""
    assert [s.line for s in swept if s.outcome == "unexecuted"] == []


def test_the_live_sites_are_twenty_two_and_all_of_them_raised(swept):
    live = [s for s in swept if s.outcome == "reached"]
    assert len(live) == 22
    assert all(s.raised > 0 and s.example for s in live)


def test_no_message_an_author_can_see_names_an_implementation_symbol(swept):
    """The point of the whole change, asserted against RENDERED messages
    rather than against source."""
    leaks = [(s.line, s.example) for s in swept
             if s.outcome == "reached"
             and re.search(r"expected (NAME|STRING|NUMBER|EOF|KW|NEWLINE)\b",
                           s.example or "")]
    assert leaks == [], leaks


# --------------------------------------------------------------------------
# 4. `_expect_hint` still dispatches on the new spelling
# --------------------------------------------------------------------------

def test_the_fn_expression_hint_still_fires():
    """`_expect_hint` compared `want == "("`. Decision 44 made that `"'('"`,
    and this is the clause that would have gone silent --- v0.34's whole
    contribution --- had the comparison not moved with it."""
    m = parse_error("let g = fn adder(a, b) { a + b }")
    assert m.startswith("expected '(', got 'adder' ("), m
    assert "a `fn` expression is anonymous" in m


def test_the_recursive_fn_expression_hint_still_fires():
    m = parse_error("let g = fn fact(n) { fact(n) }")
    assert m.startswith("expected '(', got 'fact' ("), m
    assert "this body calls `fact`" in m


def test_the_braced_block_hint_still_fires():
    """`want == "'{'"` needed no edit: that site passed `what="'{'"` all
    along. It is the reason the inconsistency was visible enough to find."""
    m = parse_error("let y = if true 1 else 2")
    assert m.startswith("expected '{', got 1 ("), m
    assert "blocks are always braced" in m


def test_the_juxtaposition_hint_still_fires_on_a_quoted_want():
    m = parse_error("fn f(a b) { 0 }")
    assert m.startswith("expected ')', got 'b' ("), m
    assert "two names in a row" in m


# --------------------------------------------------------------------------
# 5. the rendered surface, one case per live shape
# --------------------------------------------------------------------------

@pytest.mark.parametrize("src,want", [
    ("let = 1",                    "expected a name, got '='"),
    ("let a 1",                    "expected '=', got 1"),
    ('check "a" 1 == 1',           "expected ':', got 1"),
    ("check 1: 1 == 1",            "expected a string label after 'check', "
                                   "got 1"),
    ("fn f(1) { 0 }",              "expected parameter name, got 1"),
    ("fn f() effects [1] { 0 }",   "expected effect name, got 1"),
    ("let x = (1",                 "expected ')', got end of input"),
    ("let x = [1, 2",              "expected ']', got end of input"),
    ("let r = @{a: 1",             "expected '}', got end of input"),
    ("shape P = {a: num}",         "expected '@{' after shape name, got '{'"),
    ("shape P = @{1: num}",        "expected field name, got 1"),
    ("let r = @{a: 1}\nlet v = r.1",
                                   "expected field name after '.', got 1"),
])
def test_the_rendered_want_is_quoted_or_prose(src, want):
    assert parse_error(src).startswith(want), parse_error(src)


# --------------------------------------------------------------------------
# 6. one host/guest divergence closes
# --------------------------------------------------------------------------

def test_the_host_now_agrees_with_the_guest_on_the_WANT_half():
    """Round 354's `unclosed-paren` divergence was two divergences.

    The guest (`examples/self_eval.lang`) has asserted `expected ')'` since
    it was written --- `meta.lang` and `self_host.lang` each carry the same
    `check`. Round 354 recorded the two spellings as ONE disagreement and
    did not say which side was right. Decision 44 answers the WANT half:
    the guest was right and the host moved.

    The GOT half did not close and is a different debt --- the guest never
    received v0.24's `_show`, so it still renders the EOF token as `''`
    where the host says `end of input`.
    `test_parse_error_differential.py::test_wording_is_still_not_a_guest_contract`
    is where both halves are pinned; this asserts only the host side.
    """
    assert parse_error("let x = (1 + 2").startswith("expected ')', got ")
    guest_checks = 0
    for name in ("self_eval.lang", "self_host.lang", "meta.lang"):
        src = open(os.path.join(ROOT, "examples", name),
                   encoding="utf-8").read()
        guest_checks += src.count('"expected \')\'"')
    assert guest_checks == 3, guest_checks


def test_the_positions_did_not_move():
    """Decision 44 is a rendering change and nothing else. v0.24 rule 2
    (host and guest agree on the POSITION of a refusal) is a contract;
    this pins the host half of the three cases round 360 named."""
    for src, pos in (("let x = (1", " at line 1, col 11"),
                     ("let = 2", " at line 1, col 5"),
                     ("let x = [1, 2 # why", " at line 1, col 20")):
        assert parse_error(src).endswith(pos), (src, parse_error(src))

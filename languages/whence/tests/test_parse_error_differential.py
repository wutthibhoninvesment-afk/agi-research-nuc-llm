"""Host vs guest PARSE-ERROR differential — the REFUSAL set (round 360,
language C, Whence v0.24, decision 34).

`test_parser_differential.py` (round 320) canonicalizes a host AST and a
guest AST into the same shape and asserts they are equal. It has only ever
been fed programs that PARSE. `test_lexer_guest_parity.py` (round 350) does
compare rejection, but only the lexer's. Between them sat the question
neither asks: **do the two parsers refuse the same programs, and do they
refuse them in the same place?**

The answer, when it was first asked, was no. Nine of 47 malformed programs
were accepted by the guest and rejected by the host, and seven of the nine
were real defects:

  * FIVE list-like constructs let a TRAILING COMMA through — `f(1,)`,
    `[1, 2,]`, `@{a: 1,}`, `fn f(a,) {}`, `shape P = @{a: num,}` — plus the
    `effects [io,]` clause, six sites of one shape. Each was written as a
    single recursive function whose "am I at the closing bracket" test was
    also the after-a-separator test, so a comma could be followed by the
    closer. The host writes the same grammar as "entry, then required
    element", and refuses.
  * `check 1: 1 == 1` was ACCEPTED. The guest bound
    `miss "expected a string label after 'check'"` to a local and put it in
    the node's `label` FIELD — and a miss inside a record field is an
    ordinary value, not a failure, so a program the host refuses parsed to
    a perfectly well-formed `check` node whose label happened to be a miss.
  * The other two are host-only checks the guest parser has never had, and
    they are EXEMPTIONS here, not bugs — see `HOST_ONLY`.

None of this was reachable from a corpus of valid programs. That is the
finding: **a mirror shown only conforming inputs cannot tell you it is more
permissive than the original.** Round 356 found the guest's own self-test
asserting a laxity; this is the same class one level up, in the corpus.

THE CONTRACT (SPEC.md `## v0.24`)

  1. ACCEPTANCE AGREES. `whence.parser.parse(src)` raises if and only if
     the guest's `parse_whence(src)` returns a miss — except for the
     enumerated, individually load-bearing `HOST_ONLY` set.
  2. ON REJECTION, THE POSITION AGREES. Both messages end in
     ` at line L, col C` and the two (L, C) pairs are equal.
  3. WORDING IS NOT A CONTRACT, deliberately, and this file does not
     assert it. Round 354 established that the two have never agreed
     (`expected ), got '='` vs `expected ')', got '='`) and that v0.22's
     five parse-error HINTS have no guest equivalent at all. What changed
     in v0.24 is that a POSITION is a fact about the program under
     analysis, checkable without agreeing on a single word — and it is the
     fact both implementations got wrong (see `test_v24.py` for the host's
     three).

Rule 2 was not free on the host side. Giving the guest columns is what
found that `whence/lexer.py` never advanced `col` across a comment.

WHAT THIS FILE DOES NOT CLAIM. Every guest parse error still ends with an
implementation coordinate — `(line 472)`, a line in `self_eval.lang` —
because `miss <string>` appends the RAISING line, which for a program that
is itself a parser is a coordinate into the parser. Round 350 removed the
one instance of this in the guest LEXER by not using `miss` at all; the
parser's total-error discipline IS miss propagation, so the same move is
not available. The count is pinned by
`test_every_guest_parse_error_still_leaks_an_implementation_coordinate` so
it can only go down, and the two candidate designs are recorded in the
round-360 knowledge file.

Cost: one interpreter run for the whole corpus (~3s), the trick
`test_self_eval.py` and `test_lexer_guest_parity.py` both use.
"""

import os
import re
import sys
import traceback

import pytest

from whence.interp import Interpreter
from whence.lexer import LexError
from whence.parser import ParseError, parse
from whence.values import Miss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
PARSER_PY = os.path.join(ROOT, "whence", "parser.py")
MARKER = "# ==== SELF-TESTS"

POSITION = re.compile(r" at line (\d+), col (\d+)")
# The guest's trailing `(line N)`: N is a line in self_eval.lang, not in the
# program being parsed. See the module docstring.
IMPL_COORD = re.compile(r" \(line \d+\)$")


def library_source():
    src = open(EXAMPLE, encoding="utf-8").read()
    assert MARKER in src
    return src.split(MARKER)[0]


def escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))


# --------------------------------------------------------------------------
# the corpus
# --------------------------------------------------------------------------
# One case per host refusal, plus the classes that only the GUEST used to
# get wrong. `HOST_ONLY` names the two the guest is not expected to catch.
# Valid programs are here too (`GOOD`), so rule 1 is a real biconditional
# and not a test that only ever sees one side of it.

BAD = [
    # --- v0.22/v0.23 diagnosis surface -----------------------------------
    ("assign",               "let a = 1\na = 2"),
    ("unbraced-if",          "let y = if true 1 else 2"),
    ("record-brace",         "let r = {a: 1}"),
    ("juxtapose-call",       "let f = fn(x) { x }\nlet d = f 1"),
    ("two-stmts-one-line",   "let a = 1 let b = 2"),
    # --- binding / naming -------------------------------------------------
    ("rebind",               "let a = 1\nlet a = 2"),
    ("rebind-indented",      "let z = fn() { let b = 1\nlet b = 2 }"),
    # v0.37 (round 402), decision 46. The two cases above BOTH have their
    # first binding on line 1, so the sentence they check — `(line 1)` —
    # is satisfied by an implementation that computes nothing and prints
    # the constant 1. That is round 398's own finding about the got slot
    # ("the corpus could only ever see four token kinds") in the one place
    # v0.37 added a number, so the corpus is widened FIRST and the feature
    # measured against the widened one. Each of these has the first
    # binding somewhere other than line 1, and one of them separates the
    # other plausible wrong answer — reporting the DUPLICATE's line, which
    # for `rebind`/`rebind-indented` differs from 1 by exactly one.
    ("rebind-first-line-3",  "\n\nlet a = 1\nlet a = 2\na"),
    ("rebind-fn-line-4",     "# c\n\n\nfn f() { 1 }\nfn f() { 2 }\nf()"),
    ("rebind-nested-line-2", "let z = fn() {\n let b = 1\n\nlet b = 2 }"),
    # The desugar path: `shape S = …` reaches `stmt_list` as an ordinary
    # `A.Let` built by a DIFFERENT constructor (`parser.py:2086`), so the
    # host's `(line N)` comes from a different `tok` there. The guest can
    # only ever see the head token, and `bench/bindline.py` measured the
    # two equal over 1083 bindings; this is that measurement's case in the
    # differential, where it is checked against the host and not just
    # against the parser's own constructors.
    ("rebind-shape-desugar", "let S = 1\nshape S = @{a: num}\nS"),
    # ...and the OTHER duplicate-name sentence the host owns, which names
    # no line at all. Two sentences for one idea is the host's choice and
    # the guest mirrors it exactly; putting it here is what would make a
    # future round unifying them visible on both sides at once.
    ("shape-redeclare",      "shape S = @{a: num}\nshape S = @{b: num}\nS"),
    ("dup-param",            "fn f(a, a) { a }"),
    ("dup-record-field",     "let r = @{a: 1, a: 2}"),
    ("missing-let-name",     "let = 2"),
    ("kw-as-name",           "let let = 1"),
    # --- expressions ------------------------------------------------------
    ("if-no-else",           "let y = if true { 1 }"),
    ("chained-compare",      "let c = 1 < 2 < 3"),
    ("empty-block",          "let f = fn() { }"),
    ("block-ends-in-let",    "let f = fn() { let a = 1 }"),
    ("unclosed-paren",       "let x = (1"),
    ("unclosed-list",        "let x = [1, 2"),
    ("unclosed-record",      "let r = @{a: 1"),
    ("bare-eof",             "let x ="),
    ("trailing-close",       "let a = 1\n}"),
    ("unexpected-colon",     "let f = fn() { a: 1 }"),
    ("dot-no-field",         "let r = @{a: 1}\nlet v = r."),
    ("list-double-comma",    "let x = [1,, 2]"),
    ("leading-comma-call",   "let f = fn(x) { x }\nlet v = f(,)"),
    ("leading-comma-list",   "let x = [,]"),
    ("fn-no-body",           "fn f(a)"),
    ("comment-then-eof",     "let x = (1 # trailing"),
    # --- types and shapes -------------------------------------------------
    ("unknown-type",         "fn f(x: Nope) { x }"),
    ("reserved-type-name",   "shape num = @{a: num}"),
    ("shape-redeclared",     "shape P = @{a: num}\nshape P = @{b: num}"),
    ("shape-dup-field",      "shape P = @{a: num, a: str}"),
    ("shape-no-type-name",   "shape P = @{a: 1}"),
    ("type-out-of-scope",
     "let f = fn() { shape P = @{a: num}\n1 }\nfn g(p: P) { p }"),
    # --- check ------------------------------------------------------------
    ("check-no-label",       "check 1: 1 == 1"),
    ("check-no-colon",       'check "l" 1 == 1'),
    # --- v0.24: the trailing comma, in every construct that has one -------
    ("trailing-comma-call",  "let f = fn(x) { x }\nlet v = f(1,)"),
    ("trailing-comma-list",  "let x = [1, 2,]"),
    ("trailing-comma-rec",   "let r = @{a: 1,}"),
    ("trailing-comma-param", "fn f(a,) { a }"),
    ("trailing-comma-shape", "shape P = @{a: num,}"),
    # --- v0.34 (round 392): the shapes the three no-cure messages fire on.
    # `named-fn-expression` is why these are here. The five-case fast-tier
    # check in `test_v34.py` found host and guest refusing it in two
    # different COLUMNS (12 vs 9) --- a rule-2 violation this 47-program
    # sweep could not see, because no program in it put a NAMED `fn` in
    # expression position. A corpus is not made complete by being run more
    # often. Fixed in `self_eval.lang`'s `parse_primary`; these cases are
    # what keep it fixed.
    ("named-fn-expression",  "let g = fn adder(a, b) { a + b }"),
    ("named-fn-expr-recursive",
     "let g = fn fact(n) { if n < 2 { 1 } else { n * fact(n - 1) } }"),
    ("named-fn-expr-in-arg",
     "let xs = [1, 2]\nlet t = fold(fn sum(a, b) { a + b }, 0, xs)"),
    ("block-ends-in-fn",     "let f = fn() { fn g(a) { a } }"),
    ("block-ends-in-check",  'let f = fn() { check "ok": 1 == 1 }'),
    ("block-ends-in-shape",  "let f = fn() { shape P = @{a: num} }"),
    ("infix-no-left-operand", "let x = 1\n== 2"),
    ("infix-kw-no-left-operand", "let x = 1\nand 2"),
    # --- v0.36 (round 398): the token kinds the got slot never reached.
    # Across the 51 cases above, `expected X, got Y` is filled by exactly
    # four token kinds (EOF, NUMBER, NAME, punctuation) --- the lexer emits
    # 29. These three reach a NEWLINE, a STRING, and a STRING whose value
    # contains a single quote, which is the input Python `repr` renders
    # with DOUBLE quotes. The last one is here because a renderer can be
    # right on every token in `bench/showtok.py` and still be wrong once
    # the message path gets hold of it.
    ("newline-in-got-slot",  "let x\nlet y = 1"),
    ("string-in-got-slot",   'let f = fn(x) { x }\nlet v = f("a" "b")'),
    ("quote-switching-in-got-slot",
     'let f = fn(x) { x }\nlet v = f(1 "a\'b")'),
    # --- lex errors, which the host raises BEFORE parsing at all ----------
    ("bad-escape",           'let s = "a\\qb"'),
    ("unterminated-str",     'let s = "abc'),
    ("unexpected-char",      "let x = 1 ; 2"),
    # --- host-only (see HOST_ONLY) ----------------------------------------
    ("deep-nesting",         "let x = " + "(" * 260 + "1" + ")" * 260),
    ("effect-not-permitted", 'fn f() effects [] { print("x") }'),
    ("effect-arg-not-permitted",
     'fn apply(f) effects [] { f(1) }\nlet p = print\nlet z = apply(p)'),
]

GOOD = [
    ("valid-hello",          'let x = 1\nlet y = x + 2'),
    ("valid-call",           'let f = fn(a, b) { a + b }\nlet v = f(1, 2)'),
    ("valid-shape",          'shape P = @{x: num}\nfn mag(p: P) { p.x }'),
    ("valid-check",          'check "ok": 1 == 1'),
    ("valid-comment-eof",    'let x = 1 # trailing comment'),
    ("valid-effects",        'fn f() effects [io] { print("x") }'),
]

# Two host checks the guest parser does not have, each with the reason it
# does not, and each asserted load-bearing in BOTH directions by
# `test_each_host_only_exemption_is_load_bearing` — the discipline
# `skills/measured-exemption` (round 359) exists for. If the guest ever
# grows one, its exemption fails and must be DELETED, not adjusted.
HOST_ONLY = {
    "deep-nesting":
        "MAX_NESTING is a HOST RESOURCE guard (`_enter` counts Python "
        "recursion depth so a deeply nested expression is a ParseError and "
        "not a RecursionError), not a rule of the grammar. The guest runs "
        "on the trampoline and has no host stack to protect.",
    "effect-not-permitted":
        "The effects system is parse-time in the host and absent in the "
        "guest: `parse_effects_clause` SKIPS `effects [...]` without "
        "recording it. Pre-existing and documented at that function "
        "(round 164); implementing it means six scope stacks the guest has "
        "no mutation to carry.",
    "effect-arg-not-permitted":
        "Same absence, at the call-site half of the same system "
        "(`_check_call_site_param_effects`, v0.14.12). Listed separately "
        "because it is a separate host raise site, and the coverage floor "
        "below counts raise sites.",
}


# --------------------------------------------------------------------------
# running both sides
# --------------------------------------------------------------------------

class HostResult(object):
    __slots__ = ("kind", "message", "line", "col", "raise_site")

    def __init__(self, kind, message=None, line=None, col=None, raise_site=None):
        self.kind = kind            # "accept" | "parse-error" | "lex-error"
        self.message = message
        self.line = line
        self.col = col
        self.raise_site = raise_site

    @property
    def rejected(self):
        return self.kind != "accept"

    def __repr__(self):
        return "HostResult(%s, %r, %s:%s)" % (self.kind, self.message,
                                              self.line, self.col)


def host_result(src):
    """Parse on the host, recording WHERE in `parser.py` the refusal came
    from. The raise site is what makes the coverage floor below a real
    measurement of the corpus rather than a count of how many cases it has:
    twelve cases can all land on `expect()`."""
    try:
        parse(src)
        return HostResult("accept")
    except ParseError as e:
        tb = traceback.extract_tb(sys.exc_info()[2])
        frames = [f for f in tb if os.path.abspath(f.filename) == PARSER_PY]
        site = "parser.py:%d" % frames[-1].lineno if frames else "parser.py:?"
        return HostResult("parse-error", str(e), e.line, e.col, site)
    except LexError as e:
        # A lex error is a DIFFERENT class of refusal, and is keyed by its
        # message rather than by a line number because `lexer.py` raises
        # from three places whose messages are the classification.
        head = str(e).split(" at line ")[0]
        site = "lexer.py:" + re.sub(r"'.*'", "…", head)
        return HostResult("lex-error", str(e), e.line, e.col, site)


@pytest.fixture(scope="module")
def guest():
    """{name: (rejected, reason_or_None)} for the whole corpus, one run."""
    cases = BAD + GOOD
    prog = [library_source()]
    for k, (_, s) in enumerate(cases):
        prog.append('let __p%d = parse_whence("%s")' % (k, escape(s)))
        prog.append('let __m%d = missed(__p%d)' % (k, k))
    env = Interpreter().run("\n".join(prog) + "\n")
    out = {}
    for k, (name, _) in enumerate(cases):
        rejected = env.get("__m%d" % k).payload
        assert rejected is True or rejected is False, rejected
        payload = env.get("__p%d" % k).payload
        if rejected:
            assert isinstance(payload, Miss), payload
            assert len(payload.reasons) == 1, payload.reasons
            out[name] = (True, payload.reasons[0])
        else:
            out[name] = (False, None)
    return out


@pytest.fixture(scope="module")
def hosts():
    return {name: host_result(src) for name, src in BAD + GOOD}


def position_of(message):
    """The (line, col) a message ends with, or None. `findall`-last, not
    `search`-first: the no-rebinding message contains an earlier `(line 1)`
    naming where the FIRST binding was, which is not a position clause and
    does not match this pattern, but a future message that does carry two
    positions should be read as ending at the offending one."""
    found = POSITION.findall(message or "")
    return (int(found[-1][0]), int(found[-1][1])) if found else None


# --------------------------------------------------------------------------
# rule 1 — acceptance agrees
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name,src", BAD, ids=[n for n, _ in BAD])
def test_the_host_rejects_every_bad_program(name, src, hosts):
    assert hosts[name].rejected, (
        "[%s] the corpus claims %r is malformed and the host accepted it"
        % (name, src))


@pytest.mark.parametrize("name,src", GOOD, ids=[n for n, _ in GOOD])
def test_both_accept_every_good_program(name, src, hosts, guest):
    assert not hosts[name].rejected, (name, hosts[name].message)
    assert guest[name] == (False, None), (name, guest[name])


@pytest.mark.parametrize("name,src", BAD, ids=[n for n, _ in BAD])
def test_acceptance_agrees(name, src, hosts, guest):
    rejected, reason = guest[name]
    if name in HOST_ONLY:
        pytest.skip("host-only: " + HOST_ONLY[name])
    assert rejected, (
        "[%s] the host rejects %r (%s) and the guest ACCEPTED it. Either it "
        "is a guest defect or it belongs in HOST_ONLY with a reason."
        % (name, src, hosts[name].message))


def test_each_host_only_exemption_is_load_bearing(hosts, guest):
    """Every exemption must be USED, and used in the direction it claims.

    An exemption that has stopped being needed is a silenced test, and the
    only way to notice is to assert it still fires. `skills/measured-
    exemption`, round 359."""
    for name, reason in sorted(HOST_ONLY.items()):
        assert name in dict(BAD), name
        assert hosts[name].rejected, (
            "[%s] exemption claims the HOST rejects it; it does not" % name)
        assert guest[name][0] is False, (
            "[%s] the guest now REJECTS this too — the exemption is stale "
            "and should be deleted, not kept. Reason it carried: %s"
            % (name, reason))
        assert len(reason) > 60, ("[%s] an exemption is a reason, not a "
                                  "label" % name)


def test_the_corpus_exercises_both_outcomes(hosts, guest):
    assert len(GOOD) >= 5 and len(BAD) >= 40
    assert all(not hosts[n].rejected for n, _ in GOOD)
    assert sum(1 for n, _ in BAD if guest[n][0]) >= len(BAD) - len(HOST_ONLY)


# --------------------------------------------------------------------------
# rule 2 — on rejection, the position agrees
# --------------------------------------------------------------------------

BOTH_REJECT = [(n, s) for n, s in BAD if n not in HOST_ONLY]


@pytest.mark.parametrize("name,src", BOTH_REJECT,
                         ids=[n for n, _ in BOTH_REJECT])
def test_position_agrees(name, src, hosts, guest):
    host = hosts[name]
    hpos = (host.line, host.col)
    gpos = position_of(guest[name][1])
    assert gpos is not None, (
        "[%s] guest reason carries no position clause: %r"
        % (name, guest[name][1]))
    assert gpos == hpos, (
        "[%s] %r: host refuses at line %d, col %d; guest at line %d, col %d\n"
        "  host : %s\n  guest: %s"
        % ((name, src) + hpos + gpos + (host.message, guest[name][1])))


def test_every_position_is_inside_the_program(hosts, guest):
    """A column is 1-based and a line is 1-based, on both sides.

    `col 0` is what the host's no-rebinding error reported until v0.24 —
    not a position in any file, and the reason this test exists as a range
    check rather than as one more equality."""
    for name, src in BOTH_REJECT:
        lines = src.split("\n")
        for who, pos in (("host", (hosts[name].line, hosts[name].col)),
                         ("guest", position_of(guest[name][1]))):
            line, col = pos
            assert 1 <= line <= len(lines), (who, name, pos, len(lines))
            # +1 so end-of-input, one past the last character, is legal.
            assert 1 <= col <= len(lines[line - 1]) + 1, (
                "%s [%s] col %d but line %d is %d chars: %r"
                % (who, name, col, line, len(lines[line - 1]), lines[line - 1]))


def test_the_two_block_errors_point_at_opposite_braces(hosts, guest):
    """The two positions in this corpus that were a CHOICE, pinned.

    Six of the eight guest errors that had no position at all before v0.24
    had exactly one sensible token to name. These two did not: the host
    reports an empty block at its OPENING brace (`open_tok`) and a block
    that does not end in an expression at its CLOSING one (`close`), and a
    guest that used the same token for both — the natural thing to write,
    since `parse_block` has both in hand — would pass every other test in
    this file and diverge here."""
    empty = hosts["empty-block"]
    ends = hosts["block-ends-in-let"]
    assert (empty.line, empty.col) == (1, 14), empty      # the `{`
    assert (ends.line, ends.col) == (1, 26), ends         # the `}`
    assert position_of(guest["empty-block"][1]) == (1, 14)
    assert position_of(guest["block-ends-in-let"][1]) == (1, 26)
    assert "let f = fn() { }"[13] == "{"
    assert "let f = fn() { let a = 1 }"[25] == "}"


# --------------------------------------------------------------------------
# coverage — the corpus reaches the code it claims to
# --------------------------------------------------------------------------

def test_the_corpus_reaches_every_host_parse_error_site(hosts):
    """Every `raise ParseError` in `whence/parser.py` is reached.

    Counted from the SOURCE, not from a literal: a new refusal added to the
    host without a corpus case fails this immediately, which is the only
    mechanism that keeps a differential honest as the thing it mirrors
    grows."""
    src = open(PARSER_PY, encoding="utf-8").read()
    declared = len(re.findall(r"^\s*raise ParseError\(", src, re.M))
    reached = {h.raise_site for h in hosts.values()
               if h.kind == "parse-error"}
    assert declared == 20, ("whence/parser.py's refusal count changed (%d); "
                            "add a corpus case for the new one" % declared)
    assert len(reached) == declared, (
        "corpus reaches %d of %d host `raise ParseError` sites: %s"
        % (len(reached), declared, sorted(reached)))


def test_the_corpus_reaches_every_host_lex_error_class(hosts):
    sites = {h.raise_site for h in hosts.values() if h.kind == "lex-error"}
    assert sites == {"lexer.py:unterminated string",
                     "lexer.py:bad escape …",
                     "lexer.py:unexpected character …"}, sites


# --------------------------------------------------------------------------
# what is NOT yet a contract, pinned so it cannot rot quietly
# --------------------------------------------------------------------------

def test_every_guest_parse_error_still_leaks_an_implementation_coordinate(guest):
    """59 of 59 (43 until round 392 widened `BAD` by eight, 51 until
    round 398 widened it by three).
    The RATIO can go down; it must never go up.

    `miss <string>` appends `(line N)` where N is the line of the `miss`
    EXPRESSION — correct for an ordinary program, and a coordinate into the
    parser for a program that is a parser. Round 350 removed the guest
    LEXER's one instance by returning an `@{err: ...}` record instead of a
    miss; the parser cannot do the same, because miss PROPAGATION is its
    total-error discipline (there is no `raise` in Whence, and ~40 parser
    functions rely on a miss flowing up through record construction).

    Fixing it is a LANGUAGE change, not a guest change, and the two
    candidates are in the round-360 knowledge file. Until then this counts
    the leak so nobody reads rule 2's success as the whole message being
    right."""
    leaking = [n for n, (rejected, reason) in guest.items()
               if rejected and IMPL_COORD.search(reason)]
    rejecting = [n for n, (rejected, _) in guest.items() if rejected]
    assert len(rejecting) == len(BAD) - len(HOST_ONLY) == 59, len(rejecting)
    assert len(leaking) == len(rejecting), (
        "%d of %d — good news, but update this pin and SPEC.md § v0.24"
        % (len(leaking), len(rejecting)))


def test_wording_is_still_not_a_guest_contract(hosts, guest):
    """Rule 3, asserted as a FACT rather than left as a comment.

    At least one case must have equal positions and DIFFERENT sentences —
    otherwise this file's careful distinction between "where" and "what"
    describes nothing, and a future round could tighten wording without
    noticing it had made rule 3 vacuous.

    v0.37 (round 402) is the round that came closest to making it vacuous,
    and the floor held: 41 of the 59 now agree word for word, up from 12
    before v0.36 and 34 after it. What is left is 18, and
    `test_every_remaining_divergence_is_a_host_only_hint` below says exactly
    what all 18 are — a SINGLE class, for the first time in this file's
    history. Rule 3 is not "the wordings
    are arbitrary"; it is "the guest owes no sentence, and when it happens
    to write the same one that is a measurement, not a contract".
    """
    differing = []
    for name, _ in BOTH_REJECT:
        h = POSITION.sub("", hosts[name].message)
        g = IMPL_COORD.sub("", POSITION.sub("", guest[name][1]))
        if h != g:
            differing.append((name, h, g))
    assert len(differing) >= 10, differing
    names = {d[0] for d in differing}
    # Round 354 named three shapes that must still differ. All three are
    # now CLOSED, and each closed for a different reason, which is why they
    # are re-authored here as pins on the agreement rather than deleted:
    #
    #   `unclosed-paren` — the want half closed in v0.35 by the HOST moving
    #     (decision 44), the got half in v0.36 by the GUEST moving
    #     (decision 45). Two rounds, two directions, one sentence.
    #   `bare-eof` — v0.36. The guest wrote `unexpected token ''`: the
    #     wrong prefix AND the token's empty `v` field where the host
    #     names `end of input`.
    #   `unbraced-if` — still differs, and is the anchor this test keeps.
    #     Its got half agrees (`got 1` on both since v0.36); what remains
    #     is v0.22's HINT, which is host-only by design.
    assert "unbraced-if" in names
    for closed in ("unclosed-paren", "bare-eof", "rebind", "rebind-indented"):
        h = POSITION.sub("", hosts[closed].message)
        g = IMPL_COORD.sub("", POSITION.sub("", guest[closed][1]))
        assert h == g, (closed, h, g)
    assert POSITION.sub("", hosts["unclosed-paren"].message) == \
        "expected ')', got end of input"
    assert POSITION.sub("", hosts["bare-eof"].message) == "unexpected end of input"
    # v0.37 (round 402), decision 46: `rebind` was the second anchor here
    # and is now the third and fourth CLOSED cases, so they move into the
    # loop above. They closed for a reason neither earlier closure had —
    # not a rendering (v0.36) and not the host moving (v0.35), but the
    # guest computing a FACT it never had: the line of the first binding,
    # which its table did not record.
    #
    # The sentence is pinned literally on both sides because its `(line 1)`
    # is the only place in this corpus where a message contains a
    # parenthesised line number that is NOT the guest's implementation
    # coordinate. `IMPL_COORD` is `$`-anchored precisely so it cannot eat
    # this one, and `test_the_sanitiser_does_not_eat_a_line_number_inside_
    # the_sentence` below is what makes that anchoring deliberate rather
    # than lucky.
    assert POSITION.sub("", hosts["rebind"].message) == \
        "'a' is already bound in this block (line 1); Whence has no rebinding"
    assert IMPL_COORD.sub("", POSITION.sub("", guest["rebind"][1])) == \
        "'a' is already bound in this block (line 1); Whence has no rebinding"


def _strip_hint(message):
    """The host message with a trailing parenthetical HINT removed.

    `_with_hint` renders `"%s (%s)" % (message, hint)` and every one of
    v0.22's/v0.33's/v0.34's hints contains balanced parens of its own
    (`fn f(x) { x }`), so this scans back from the final `)` for its
    match rather than using a regex. A message that does not END in `)`
    is returned unchanged — which is what keeps `rebind`'s mid-sentence
    `(line 1)` out of this.
    """
    if not message.endswith(")"):
        return message
    depth = 0
    for i in range(len(message) - 1, -1, -1):
        if message[i] == ")":
            depth += 1
        elif message[i] == "(":
            depth -= 1
            if depth == 0:
                return message[:i - 1] if i and message[i - 1] == " " else message
    return message


def test_every_remaining_divergence_is_a_host_only_hint(hosts, guest):
    """v0.37 (round 402), decision 46 — the divergence set is now ONE class.

    Round 354 called the whole thing "wording". Round 396 split the
    `expected X, got Y` shape into want / got / hint and closed the want
    half. This round closed the got half, and what that makes possible is
    the assertion this test exists for: every message that still differs
    differs for one of exactly TWO reasons, both named, neither a mystery.

      * 18 carry a host-only parenthetical HINT (v0.22, v0.33, v0.34).
        Strip it and the two sentences are byte-identical. Rule 3 keeps
        these host-only deliberately: a hint is a CURE, and the guest has
        no cure system.
      * 0 are anything else. v0.36 left exactly two —
        `rebind`/`rebind-indented`, where the host's sentence carried a
        FACT (the line of the first binding) that the guest's binding table
        did not record. v0.37 gave the guest that fact and `other` is now
        EMPTY: every message this corpus can produce either agrees word for
        word or differs by a host-only hint and by nothing else.

    That is a strictly stronger statement than v0.36's, and it is the one
    worth guarding. `other` becoming non-empty is the finding, not the
    failure — it would mean a divergence exists that nobody has classified.
    It stays an equality against `[]` rather than a `<= 1` tolerance for
    exactly that reason.
    """
    hint_only, other = [], []
    for name, _ in BOTH_REJECT:
        h = POSITION.sub("", hosts[name].message)
        g = IMPL_COORD.sub("", POSITION.sub("", guest[name][1]))
        if h == g:
            continue
        (hint_only if _strip_hint(h) == g else other).append(name)
    assert len(hint_only) == 18, sorted(hint_only)
    assert other == [], sorted(other)


def test_the_agreeing_share_is_measured_not_assumed(hosts, guest):
    """The headline number, pinned so a regression is visible as a number.

    12 of 51 before v0.36, 34 of 54 after it, and 41 of 59 after v0.37
    (round 402) closed `rebind`/`rebind-indented` AND widened `BAD` by the
    five cases that make the new `(line N)` a measurement rather than a
    constant. It is deliberately NOT a floor
    that only goes up: the corpus grows, and a round that widens `BAD`
    with cases the guest gets wrong SHOULD see this drop and have to say
    so. The pin is on the exact pair.
    """
    agree = [n for n, _ in BOTH_REJECT
             if POSITION.sub("", hosts[n].message)
             == IMPL_COORD.sub("", POSITION.sub("", guest[n][1]))]
    assert (len(agree), len(BOTH_REJECT)) == (41, 59), (len(agree), len(BOTH_REJECT))


#: `expected X, got Y` is the one message shape BOTH parsers build, and it
#: has three independently-diverging parts. Round 354 read the whole string,
#: saw one disagreement, and called it "wording"; v0.35 (round 396) split it.
_EXPECTED_SHAPE = re.compile(r"^expected (.*?), got (.*?)(?: \(|$)")


def test_the_want_half_of_every_shared_message_now_agrees(hosts, guest):
    """v0.35 decision 44 and v0.36 decision 45 --- both halves, separately.

    `expected X, got Y` is the one message shape BOTH parsers build. It has
    three independently-diverging parts and each was fixed in a different
    round, from a different side:

      want  v0.35 (round 396), by the HOST moving. `expect`'s want was the
            raw argument, so the host wrote `expected )` where the guest
            had always written `expected ')'`.
      got   v0.36 (round 398), by the GUEST moving. `expect_op` quoted
            unconditionally, so the EOF token printed `got ''` and a
            number printed `got '1'` --- the guest's own token record,
            not anything the author typed.
      hint  host-only by rule 3, in both rounds and still.

    THE SHARED SET GREW FROM 10 TO 20 WHEN THE GOT HALF LANDED, and that
    is the part worth reading twice. Membership is decided by
    `_EXPECTED_SHAPE`, which requires `, got ` on BOTH sides --- so the
    seven programs where the guest wrote no got half at all were excluded
    from the want-half measurement BECAUSE of the defect the measurement
    was next to. Four of those seven (`dot-no-field`,
    `trailing-comma-rec`, `trailing-comma-param`, `trailing-comma-shape`)
    had a want half that DISAGREED the whole time: the host said
    `expected field name` / `expected parameter name` and the guest's one
    `expect_name` helper said `expected a name`. Round 396's "all ten want
    halves now agree" was true of what it could see. A test that filters
    its population on a field the defect removes will report the defect as
    absent.
    """
    shared, want_agree, got_agree, full = [], [], [], []
    for name, _ in BOTH_REJECT:
        h = POSITION.sub("", hosts[name].message)
        g = IMPL_COORD.sub("", POSITION.sub("", guest[name][1]))
        mh, mg = _EXPECTED_SHAPE.match(h), _EXPECTED_SHAPE.match(g)
        if not (mh and mg):
            continue
        shared.append(name)
        if mh.group(1) == mg.group(1):
            want_agree.append(name)
        if mh.group(2) == mg.group(2):
            got_agree.append(name)
        if h == g:
            full.append(name)
        # every want half is a quoted literal or prose on BOTH sides
        assert not mh.group(1).isupper(), (name, h)
        assert not mg.group(1).isupper(), (name, g)
    assert len(shared) == 20, sorted(shared)
    assert sorted(want_agree) == sorted(shared), (
        "want halves that still differ: %s"
        % sorted(set(shared) - set(want_agree)))
    assert sorted(got_agree) == sorted(shared), (
        "got halves that still differ: %s"
        % sorted(set(shared) - set(got_agree)))
    # ...and the five that still differ OVERALL differ only by the host's
    # hint. Named, because these five are the whole of rule 3's remaining
    # footprint inside this message shape.
    still = sorted(set(shared) - set(full))
    assert still == ["fn-no-body", "named-fn-expr-in-arg",
                     "named-fn-expr-recursive", "named-fn-expression",
                     "unbraced-if"], still


def test_the_got_half_reaches_more_than_four_token_kinds(hosts, guest):
    """Why `bench/showtok.py` exists, asserted rather than asserted-about.

    A whole-program corpus fills the got slot with whatever token happens
    to sit at a refusal point. Before round 398 that was four kinds across
    51 programs; the lexer emits 29. `bench/showtok.py` compares the
    RENDERER over every kind; this test keeps the three programs added
    here (a NEWLINE, a STRING, and a STRING that makes Python `repr` switch
    to double quotes) from being deleted as redundant, because they are
    the only place the renderer is reached through the real message path.
    """
    got = {}
    for name in ("newline-in-got-slot", "string-in-got-slot",
                 "quote-switching-in-got-slot"):
        h = POSITION.sub("", hosts[name].message)
        g = IMPL_COORD.sub("", POSITION.sub("", guest[name][1]))
        assert h == g, (name, h, g)
        got[name] = _EXPECTED_SHAPE.match(h).group(2)
    assert got["newline-in-got-slot"] == r"'\n'", got
    assert got["string-in-got-slot"] == "'b'", got
    assert got["quote-switching-in-got-slot"] == '"a\'b"', got


def test_the_lex_errors_are_the_one_class_where_wording_does_agree(hosts, guest):
    """v0.24 made the guest surface a lex error AS a lex error.

    It used to hand the `bad` token to `parse_primary`'s catch-all, which
    reported `unexpected token 'unterminated string' at line 1` — the
    lexer's own sentence wedged into the slot where a token's text goes.
    The host never parses at all in this case, so there is nothing for the
    guest to be a mirror of except `LexError`'s own message, and here the
    two are byte-identical."""
    for name in ("unterminated-str", "bad-escape", "unexpected-char"):
        assert hosts[name].kind == "lex-error", name
        g = IMPL_COORD.sub("", guest[name][1])
        assert g == hosts[name].message, (name, hosts[name].message, g)

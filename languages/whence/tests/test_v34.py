"""v0.34 (round 392), decision 43 --- the errors that named no cure.

Round 386 asked what happens to a reader who FOLLOWS a Whence parse
error's cure, and found three messages in the field corpus that name no
cure at all:

    prod_demo_v3.lang:41         unexpected '=='
    whenceguard_auditor.lang:28  expected (, got 'sum_lines'
    nano_reasoner.lang:32        block must end with an expression

The third is the worst of the three and is not in round 386's `no-cure`
count, because it is not reachable until a MECHANICAL cure has been
followed: `risk_status = "HIGH_RISK"` is diagnosed, the message says write
`let name = value`, doing exactly that produces the error above, and that
error names nothing. Following the cure moved the program from a diagnosed
error to an undiagnosed one.

Decision 43 is what the three have in common: **the datum each message was
missing is in the program, and a hint may read it.** Not the offending
token --- the program. `_block_tail_hint` reads the AST of the statement
that ended the block; `_fn_expr_hint` reads the fn body's TOKENS, because
at that point there is no AST; `_infix_hint` reads the operator set the
expression grammar itself defines.

WHAT IS PINNED HERE, and the three kinds are not the same claim:

  1. STRUCTURE (sections 1-2). Every `raise ParseError` site in
     `parser.py` is either hinted or carries a written reason for not
     being; the infix set is exactly the operators that build an
     `A.Binary`. Derived from the parser by reading its AST and by RUNNING
     it, never from a list in this file.
  2. BEHAVIOUR (sections 3-5). Each of the eight new clauses, and the two
     new mechanical appliers, on synthetic programs written here.
  3. THE CORPUS DELTA (section 6). Behind round 384's frozen md5 census,
     so a corpus the gateway rewrites SKIPS rather than goes red.

Section 7 is the one that is not about v0.34 at all: host and guest still
accept and reject the same programs at the same positions. v0.24 rule 3
says parse-error WORDING is not a guest contract, so none of the eight
clauses needs a guest mirror --- but acceptance and position are contracts,
and a cheap check that they held is what round 390 established the fast
tier must carry, rather than leaving it to a ~900 s slow-tier sweep nobody
runs.
"""

import ast
import hashlib
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import curecheck as C                                       # noqa: E402
from whence import ast_nodes as A                           # noqa: E402
from whence import parser as P                              # noqa: E402
from whence.parser import ParseError, parse                 # noqa: E402
from whence.foreign import FOREIGN_NAMES                   # noqa: E402

PARSER_PY = os.path.join(ROOT, "whence", "parser.py")
EXAMPLES = os.path.join(ROOT, "examples")
CENSUS = os.path.join(os.path.dirname(ROOT), "..", "state", "whence",
                      "round-384", "field-names.json")


def err(src):
    """The rendered parse error of `src`, or None."""
    try:
        parse(src)
    except ParseError as e:
        return str(e)
    return None


# --------------------------------------------------------------------------
# 1. the census --- every `raise ParseError` site, classified
# --------------------------------------------------------------------------
#
# Round 390's finding, in this file's key: a rule checked only in a tier
# nobody runs is not checked. Round 392's is one turn further --- an
# anti-rot list that has to be MAINTAINED is not anti-rot. Both of the
# checks below derive their left-hand side from `parser.py` itself, so a
# site or a hint added by a future round arrives as a failure here without
# anyone remembering to add it.

#: Message template -> why this site is deliberately unhinted. Three
#: classes, and each entry says which:
#:
#:   `message-is-the-cure`  --- the sentence contains the edit
#:                              ("use 'and'"), so a parenthetical would
#:                              repeat it.
#:   `names-the-operands`   --- the message names every name and position
#:                              the edit needs; what remains under-
#:                              determined is a CHOICE (rename or delete)
#:                              that no sentence can make for the author.
#:   `implementation-limit` --- not a mistake in the program. There is no
#:                              cure because there is nothing wrong with
#:                              what was written except its size.
UNHINTED = {
    "'%s' requires effect '%s', not permitted by the enclosing function's "
    "'%s'":
        ("names-the-operands: the call, the effect it needs and the "
         "enclosing declaration are all three named; the edit is to widen "
         "the `effects [...]` clause the message quotes"),
    "argument '%s' (effect '%s') passed to '%s' for parameter '%s', which "
    "'%s' calls directly, is not permitted by '%s''s own '%s'":
        ("names-the-operands: seven of them, which is why this message is "
         "a sentence and not a hint"),
    "expression nested more than %d levels deep":
        ("implementation-limit: recursive descent costs host frames "
         "(MAX_NESTING). Nothing about the program is wrong except its "
         "depth, so there is no cure to name"),
    "unknown type '%s'":
        ("names-the-operands: the type name is the whole datum; the cure "
         "is a `shape` declaration for it, and where that goes is the "
         "author's block structure, not a position in this message"),
    "type '%s' is not in scope here":
        ("names-the-operands: v0.18 made shapes block-scoped, and the "
         "message says both the name and that scope is the problem"),
    "'%s' is a reserved type name":
        "message-is-the-cure: rename it; the message names it",
    "shape '%s' is already declared in this block (line %d)":
        ("names-the-operands: the name, the scope, and (v0.38, round 404,"
         " decision 47) the line of the earlier declaration. Rename or "
         "delete is a choice the message cannot make. NOTE for whoever "
         "edits this table next: the `(line %d)` is a FACT this sentence "
         "reports, not a hint -- `_parse_error_sites` reads `hinted` off "
         "the AST (`_with_hint(...)` at the raise site) and is therefore "
         "immune to the shape collision that bit "
         "`test_parse_error_differential.py::_strip_hint`, which reads it "
         "off the string"),
    "block must contain at least one expression":
        "HINTED-IN-v0.34 (kept here only to fail loudly if it is removed)",
    "expected a type name":
        ("names-the-operands: the position is the whole datum --- a type "
         "annotation goes exactly there and nothing else does"),
    "comparisons do not chain; use 'and'":
        "message-is-the-cure: `use 'and'` IS the edit",
    "duplicate parameter '%s'":
        "names-the-operands: rename or delete, and the message names which",
    "duplicate field '%s'":
        "names-the-operands: rename or delete, and the message names which",
    "'%s' is already bound in this block (line %d); Whence has no "
    "rebinding":
        ("names-the-operands: uniquely among these it also names the OTHER "
         "position --- the line of the earlier binding"),
}


def _parse_error_sites():
    """(line, hinted, template) for every `raise ParseError` in parser.py.

    Read out of the module's own AST. A site whose first argument is a
    `_with_hint(...)` call is hinted; otherwise the template is the
    message's leading string constant (`"x %s" % y` -> `"x %s"`).
    """
    tree = ast.parse(open(PARSER_PY, encoding="utf-8").read())
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Raise)
                and isinstance(node.exc, ast.Call)
                and getattr(node.exc.func, "id", None) == "ParseError"):
            continue
        arg = node.exc.args[0]
        hinted = (isinstance(arg, ast.Call)
                  and getattr(arg.func, "id", None) == "_with_hint")
        if hinted:
            arg = arg.args[0]
        while isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod):
            arg = arg.left
        template = arg.value if isinstance(arg, ast.Constant) else None
        out.append((node.lineno, hinted, template))
    return out


def test_every_parse_error_site_is_hinted_or_has_a_written_reason():
    """The instrument. A site added by a future round fails here.

    This is the parse-error twin of
    `test_miss_message_differential.py::test_the_corpus_reaches_every_
    reachable_miss_site` --- with the difference that made round 390's
    round worth writing down: that one is `whence_slow` and went unread
    for four rounds. This one costs milliseconds and runs by default.
    """
    sites = _parse_error_sites()
    assert len(sites) == 20, len(sites)
    unclassified = [(ln, t) for ln, hinted, t in sites
                    if not hinted and t not in UNHINTED]
    assert not unclassified, (
        "these `raise ParseError` sites carry no hint and no entry in "
        "`UNHINTED` saying why: %r" % (unclassified,))


def test_the_unhinted_registry_has_no_stale_entries():
    """A reason for a site that no longer exists is a claim about nothing.

    `block must contain at least one expression` is deliberately still in
    the registry AND hinted --- the entry says so --- because it is the one
    v0.34 moved across the line, and leaving the tombstone is what makes
    the move visible to whoever reads the registry next. Every OTHER entry
    must correspond to a live, unhinted site.
    """
    sites = _parse_error_sites()
    live_unhinted = set(t for _, hinted, t in sites if not hinted)
    live_hinted = set(t for _, hinted, t in sites if hinted)
    for template, reason in UNHINTED.items():
        if reason.startswith("HINTED-IN-v0.34"):
            assert template in live_hinted, template
        else:
            assert template in live_unhinted, template


def test_seven_sites_are_hinted_and_thirteen_are_not():
    """The census figure, pinned. v0.33 shipped 5 and 15."""
    sites = _parse_error_sites()
    assert sum(1 for _, h, _ in sites if h) == 7
    assert sum(1 for _, h, _ in sites if not h) == 13


def test_the_hint_census_is_derived_and_not_a_list():
    """`parser_hint_sentences()` must find every `_..._HINT` in the module.

    The cross-check that keeps round 386's mistake from recurring in its
    own cure: grep the SOURCE for `_..._HINT = ` assignments and require
    the derived census to have one entry each, plus the two tables.
    """
    src = open(PARSER_PY, encoding="utf-8").read()
    declared = set(re.findall(r"^(_[A-Z0-9_]+_HINT) = ", src, re.M))
    assert len(declared) == 13, sorted(declared)     # v0.33 had 4
    got = C.parser_hint_sentences()
    assert len(got) == (len(declared) + len(P._SYNTAX_HINTS)
                        + len(FOREIGN_NAMES)), (len(got), sorted(declared))
    # `for` and `while` share one sentence, and that is the only collision
    assert len(set(got)) == len(got) - 1


# --------------------------------------------------------------------------
# 2. the infix set, derived by RUNNING the parser
# --------------------------------------------------------------------------

_ALL_OP_SPELLINGS = ("==", "!=", "<", "<=", ">", ">=", "+", "-", "*", "/",
                     "%", "and", "or", "rescue", "not")


def test_the_infix_set_is_exactly_the_binary_operators():
    """`_INFIX_OPS` is a claim about the grammar; this checks the grammar.

    For each operator spelling: `1 OP 2` must parse (it is infix) and
    `OP 2` alone must not (it needs a left operand). Exactly the tokens
    that pass both tests, minus `rescue` --- which keeps its own richer
    `_SYNTAX_HINTS` sentence --- are what `_INFIX_OPS` may contain.
    """
    infix, prefix_ok = set(), set()
    for op in _ALL_OP_SPELLINGS:
        if err("let x = 1 %s 2\nx\n" % op) is None:
            infix.add(op)
        if err("let x = %s 2\nx\n" % op) is None:
            prefix_ok.add(op)
    assert "-" in infix and "-" in prefix_ok        # the sole exclusion
    assert "not" not in infix                       # prefix only
    assert P._INFIX_OPS == (infix - prefix_ok) - {"rescue"}, (
        P._INFIX_OPS, infix, prefix_ok)


def test_every_infix_operator_with_no_left_operand_names_its_shape():
    for op in sorted(P._INFIX_OPS):
        got = err("let x = 1\n%s 2\n" % op)
        assert got is not None, op
        assert (P._INFIX_HINT % (op, op)) in got, (op, got)


def test_the_table_still_beats_the_rule_for_rescue():
    """`rescue` is infix and is NOT in `_INFIX_OPS`: its hand-written
    sentence names the three spans (`risky rescue fallback`), which the
    template cannot. A rule that shadowed it would be a regression, which
    is v0.33's own constraint 2 restated one version later."""
    got = err("let x = 1\nrescue 2\n")
    assert P._SYNTAX_HINTS["rescue"] in got, got
    assert "has nothing on its left" not in got, got


# --------------------------------------------------------------------------
# 3. `block must end with an expression` --- four trailing statement kinds
# --------------------------------------------------------------------------

BLOCK_TAIL = [
    ("let", "fn f(x) {\n    let y = x + 1\n}\nf(1)\n",
     lambda: P._BLOCK_TAIL_LET_HINT % "y"),
    ("fn", "fn f(x) {\n    fn g(a) { a }\n}\nf(1)\n",
     lambda: P._BLOCK_TAIL_FN_HINT % "g"),
    ("check", "fn f(x) {\n    check \"ok\": 1 == 1\n}\nf(1)\n",
     lambda: P._BLOCK_TAIL_CHECK_HINT),
    ("shape", "fn f(x) {\n    shape P = @{a: num}\n}\nf(1)\n",
     lambda: P._BLOCK_TAIL_SHAPE_HINT),
]


@pytest.mark.parametrize("kind,src,want", BLOCK_TAIL,
                         ids=[b[0] for b in BLOCK_TAIL])
def test_the_block_tail_clause_names_the_statement_that_ended_the_block(
        kind, src, want):
    got = err(src)
    assert got is not None and "block must end with an expression" in got
    assert want() in got, (kind, got)


def test_a_shape_does_not_draw_the_let_sentence():
    """The guard, stated as its own test because it is the whole reason
    `_BLOCK_TAIL_SHAPE_HINT` exists. A `shape` reaches `block()` as an
    ordinary `A.Let` (decision 27), so without the discriminator the
    author of `shape P = @{a: num}` would be told to delete a `let` their
    file does not contain --- round 390's finding (a DIFFERENT cure is
    worse than a missing one), prevented instead of found."""
    got = err("fn f(x) {\n    shape P = @{a: num}\n}\nf(1)\n")
    assert "`let P = e`" not in got, got
    assert "a `shape` declares a type" in got, got


def test_the_hand_written_shape_desugaring_is_the_same_thing():
    """`let Foo = @{__shape: "Foo", ...}` IS what `shape Foo = @{...}`
    desugars to, so drawing the shape sentence for it is correct rather
    than a limitation of the discriminator. Pinned so that a future round
    reading `_block_tail_hint` does not 'fix' it."""
    got = err('fn f(x) {\n    let Foo = @{__shape: "Foo", a: "num"}\n}\n'
              'f(1)\n')
    assert "a `shape` declares a type" in got, got


def test_a_let_of_a_record_that_is_not_a_shape_draws_the_let_sentence():
    got = err('fn f(x) {\n    let r = @{a: 1}\n}\nf(1)\n')
    assert (P._BLOCK_TAIL_LET_HINT % "r") in got, got


def test_the_empty_block_clause():
    got = err("fn f(x) {\n}\nf(1)\n")
    assert "block must contain at least one expression" in got
    assert P._EMPTY_BLOCK_HINT in got, got


def test_the_clause_reports_at_the_closing_brace_and_names_the_line_anyway():
    """v0.24 rule 2 (host and guest agree on the POSITION) is why this
    error still reports at the `}` rather than at the offending statement:
    moving it would need a matching guest change. Interpolating the bound
    name buys what the move would have cost --- a block cannot rebind, so
    `let <name> =` is unique inside it, and name plus column locate one
    line. This test pins BOTH halves, because the applier depends on the
    second and nothing else states it."""
    got = err("fn f(x) {\n    let y = 1\n    let z = 2\n}\nf(1)\n")
    assert got.endswith("at line 4, col 1"), got     # the `}`, not line 3
    assert (P._BLOCK_TAIL_LET_HINT % "z") in got, got
    # and the name really is unique in the block
    assert err("fn f(x) {\n    let z = 1\n    let z = 2\n}\nf(1)\n") \
        .startswith("'z' is already bound in this block")


# --------------------------------------------------------------------------
# 4. the named `fn` EXPRESSION --- and the body that chooses the cure
# --------------------------------------------------------------------------

def test_a_named_fn_expression_is_told_it_is_anonymous():
    got = err("let g = fn adder(a, b) { a + b }\ng(1, 2)\n")
    assert (P._FN_EXPR_ANON_HINT % "adder") in got, got


def test_a_named_fn_expression_that_calls_itself_is_told_to_lift_it():
    """Decision 43's sharpest case. Dropping the name is the mechanical
    cure and it is WRONG here: it turns a parse error into an unbound
    name, which is round 386's `nano_reasoner.lang:31` failure exactly.
    The parser can tell, and only by reading the program."""
    got = err("let g = fn fact(n) { if n < 2 { 1 } "
              "else { n * fact(n - 1) } }\ng(3)\n")
    assert (P._FN_EXPR_RECURSIVE_HINT % ("fact", "fact", "fact")) in got, got
    assert "is anonymous: write" not in got, got


def test_the_body_scan_counts_at_braces_as_one_token():
    """`@{` is a single token, so a record literal in the body must not
    unbalance the scan. Without this the closing `}` of `@{...}` would
    close the body early and a self-call after it would be missed."""
    got = err("let g = fn walk(r) { let m = @{a: 1}  walk(m) }\ng(1)\n")
    assert "this body calls `walk`" in got, got


def test_the_body_scan_does_not_read_past_the_body():
    """A call to the name AFTER the fn's own closing brace is not
    recursion. `find`ing it would print the lift-it-out sentence for a
    program whose cure is the one-token deletion."""
    got = err("let g = fn adder(a, b) { a + b }\nadder(1, 2)\n")
    assert (P._FN_EXPR_ANON_HINT % "adder") in got, got


def test_an_unterminated_body_falls_back_to_the_anonymous_sentence():
    """`_fn_body_mentions` returns None when there is no balanced body to
    read, and the anonymous sentence is the answer because it is true of
    every named `fn` expression regardless of what follows."""
    got = err("let g = fn adder(a, b) { a + b\n")
    assert (P._FN_EXPR_ANON_HINT % "adder") in got, got


def test_a_named_fn_STATEMENT_is_untouched():
    """The two `param_list` callers are told apart by `prev.type`, and the
    statement form must keep parsing. If this ever fails, the new rule in
    `_expect_hint` has started firing on the wrong caller."""
    assert err("fn adder(a, b) { a + b }\nadder(1, 2)\n") is None


def test_the_juxtaposition_rule_still_owns_two_adjacent_names():
    """`fn` is a KW and not a NAME, so the two `_expect_hint` rules cannot
    collide --- pinned rather than argued."""
    got = err("let xs = [Hardware Unit]\nxs\n")
    assert P._JUXTAPOSE_HINT in got, got


# --------------------------------------------------------------------------
# 5. the two new mechanical appliers
# --------------------------------------------------------------------------

def _cure_of(src):
    rendered = err(src)
    cure, body, hint, line, col = C.classify(rendered)
    return cure, rendered, body, hint, line, col


def test_the_block_tail_let_applier_finds_the_line_the_column_is_not_on():
    src = ("fn classify(score, limit) {\n"
           "    if score < limit {\n"
           "        let risk = \"HIGH\"\n"
           "    } else {\n"
           "        \"LOW\"\n"
           "    }\n"
           "}\n"
           "classify(1, 2)\n")
    cure, rendered, body, hint, line, col = _cure_of(src)
    assert cure is not None and cure.key == "block-tail-let"
    assert cure.determinacy == C.MECHANICAL
    out = cure.apply(src.split("\n"), line, col, body, hint)
    assert out[2] == '        "HIGH"', out[2]
    assert err("\n".join(out)) is None


def test_the_block_tail_let_applier_declines_rather_than_guesses():
    """It is handed a hint whose name is not in the text. Declining is
    what makes `no-progress` distinguishable from `stalled` in the
    survey, so it is pinned."""
    lines = ["fn f(x) {", "    let y = 1", "}", "f(1)"]
    out = C._apply_block_tail_let(lines, 3, 1, "",
                                  P._BLOCK_TAIL_LET_HINT % "nosuchname")
    assert out is None


def test_the_fn_expression_applier_deletes_exactly_the_name():
    src = "fn total(xs) {\n    fold(fn sum(a, b) { a + b }, 0, xs)\n}\n" \
          "total([1, 2, 3])\n"
    cure, rendered, body, hint, line, col = _cure_of(src)
    assert cure is not None and cure.key == "fn-expression-name"
    out = cure.apply(src.split("\n"), line, col, body, hint)
    assert out[1] == "    fold(fn(a, b) { a + b }, 0, xs)", out[1]
    assert err("\n".join(out)) is None


def test_the_recursive_variant_has_no_applier():
    """Mechanical iff an applier exists, and the recursive cure must not
    be mechanical --- the edit it names is a lift with two positions the
    message does not give."""
    src = "let g = fn fact(n) { if n < 2 { 1 } else { n * fact(n - 1) } }\n" \
          "g(3)\n"
    cure, _, _, _, _, _ = _cure_of(src)
    assert cure is not None and cure.key == "fn-expression-recursive"
    assert cure.determinacy == C.UNDER_EXTENT
    assert cure._applier is None


def test_two_mechanical_cures_contradict_each_other_about_one_line():
    """The round's sharpest measurement, on a program written here.

    `risk = "HIGH"` draws `write `let name = value``; doing that draws
    `write `e` on its own`, which deletes the `let` again. Both cures are
    correctly licensed by their own messages and they disagree about the
    same text --- and the disagreement is right, because the mistake was
    never the missing `let` (round 386 said so about the field program
    this is modelled on; nothing had followed the second step because
    there was no second step to follow).
    """
    src = ("fn classify(score, limit) {\n"
           "    if score < limit {\n"
           "        risk = \"HIGH\"\n"
           "    } else {\n"
           "        \"LOW\"\n"
           "    }\n"
           "}\n"
           "classify(1, 2)\n")
    text, steps, outcome = C.cure_loop(src)
    assert outcome == "parses", (outcome, [s["cure"] for s in steps])
    assert [s["cure"] for s in steps] == ["assignment", "block-tail-let"]
    assert '        "HIGH"' in text.split("\n")
    assert "let risk" not in text


def test_the_cure_loop_terminates_on_the_pair():
    """A -> B -> A would spin to the step budget. The second edit removes
    the `=` the first added, so it cannot reintroduce the first error."""
    src = "fn f(x) {\n    y = 1\n}\nf(1)\n"
    text, steps, outcome = C.cure_loop(src)
    assert outcome in ("parses", "stalled"), outcome
    assert len(steps) <= 3, [s["cure"] for s in steps]


# --------------------------------------------------------------------------
# 6. the corpus delta --- pinned behind round 384's frozen census
# --------------------------------------------------------------------------

def _corpus_unchanged():
    census = json.load(open(CENSUS, encoding="utf-8"))
    for name, want in census["file_md5"].items():
        path = os.path.join(EXAMPLES, os.path.basename(name))
        if not os.path.exists(path):
            return "missing: %s" % name
        if hashlib.md5(open(path, "rb").read()).hexdigest() != want:
            return "changed: %s" % name
    return None


corpus_pin = pytest.mark.skipif(_corpus_unchanged() is not None,
                                reason="field corpus moved: %s"
                                       % _corpus_unchanged())


@corpus_pin
def test_no_field_program_stalls_on_a_no_cure_error_any_more():
    """v0.33: two of the corpus's 45 observed errors named no cure, and a
    third was reachable only by following a mechanical one. v0.34: none."""
    rows = C.survey([p for p in C.field_programs()])
    stalls = [s for r in rows for s in r["steps"]
              if s["determinacy"] == C.NO_CURE]
    assert stalls == [], [(s["error"]) for s in stalls]


@corpus_pin
def test_nano_reasoner_now_takes_two_steps_and_stalls_somewhere_else():
    """The single file round 386's §"one of those three is worse than a
    stall" is about. Its dead end is gone; what stops it now is
    `'if' requires 'else'`, an under-CONTENT cure on a DIFFERENT `if` ---
    the outer one, whose then-branch was the block this round taught to
    have a value."""
    rows = dict((os.path.basename(r["file"]), r)
                for r in C.survey(C.field_programs()))
    row = rows["nano_reasoner.lang"]
    assert row["applied"] == 2, row["applied"]
    assert row["outcome"] == "stalled"
    assert row["steps"][-1]["cure"] == "if-requires-else"


@corpus_pin
def test_following_the_cures_still_fixes_none_of_the_ten():
    """v0.34 does not move round 386's headline and does not claim to.
    Three new clauses, one more mechanical edit, and still zero programs
    reach a parse by machine."""
    rows = [r for r in C.survey(C.field_programs()) if not r["parses"]]
    assert len(rows) == 10
    assert all(r["outcome"] == "stalled" for r in rows)


# --------------------------------------------------------------------------
# 7. the guest --- acceptance and position, in the FAST tier
# --------------------------------------------------------------------------

GUEST_CASES = [
    "fn f(x) {\n    let y = x + 1\n}\nf(1)\n",
    "fn f(x) {\n}\nf(1)\n",
    "let g = fn adder(a, b) { a + b }\ng(1, 2)\n",
    "let x = 1\n== 2\n",
    "let x = 1\nand 2\n",
]


MARKER = "# ==== SELF-TESTS"
_POS = re.compile(r" at line (\d+), col (\d+)")


def _escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\t", "\\t"))


@pytest.fixture(scope="module")
def guest():
    """`{src: guest_reason_or_None}` for `GUEST_CASES`, in ONE guest run.

    Same construction `test_parse_error_differential.py` uses --- load
    `self_eval.lang`'s library half, then `let __pK = parse_whence("...")`
    per case --- deliberately, so that this cheap check and the expensive
    sweep cannot disagree about what "the guest parser" means. One
    `Interpreter().run` for all five cases is what keeps it in the fast
    tier.
    """
    from whence.interp import Interpreter
    from whence.values import Miss
    lib = open(os.path.join(EXAMPLES, "self_eval.lang"),
               encoding="utf-8").read().split(MARKER)[0]
    prog = [lib]
    for k, src in enumerate(GUEST_CASES):
        prog.append('let __p%d = parse_whence("%s")' % (k, _escape(src)))
        prog.append("let __m%d = missed(__p%d)" % (k, k))
    env = Interpreter(out=lambda *_: None).run("\n".join(prog) + "\n")
    out = {}
    for k, src in enumerate(GUEST_CASES):
        rejected = env.get("__m%d" % k).payload
        payload = env.get("__p%d" % k).payload
        assert rejected in (True, False), rejected
        if rejected:
            assert isinstance(payload, Miss), payload
            out[src] = payload.reasons[0]
        else:
            out[src] = None
    return out


@pytest.mark.parametrize("src", GUEST_CASES,
                         ids=["let-tail", "empty", "fn-expr", "eq", "and"])
def test_host_and_guest_refuse_the_same_programs_at_the_same_place(guest,
                                                                  src):
    host = err(src)
    assert host is not None
    got = guest[src]
    assert got is not None, "guest ACCEPTED a program the host refuses"
    hp = _POS.findall(host)
    gp = _POS.findall(got)
    assert hp and gp, (host, got)
    assert hp[-1] == gp[-1], (host, got)


def test_no_clause_of_v034_is_mirrored_in_the_guest(guest):
    """Stated as a test so it is a decision and not an omission. v0.24
    rule 3: parse-error WORDING is not a guest contract, and never has
    been --- the two have never agreed on a single parse-error sentence.
    All eight v0.34 clauses are host-only, deliberately."""
    got = guest[GUEST_CASES[0]]
    assert "a block's value is its last expression" not in got, got

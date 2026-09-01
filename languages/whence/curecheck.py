#!/usr/bin/env python3
"""curecheck.py --- does FOLLOWING a Whence parse error's cure fix the program?

Round 386, language(C). Decision 32 (v0.22, round 354) says *an error that
can name the fix, names it*, and round 354 measured itself honestly: of the
ten machine-written Whence programs in `examples/` that fail to parse, ONE
named a cure before v0.22 and NINE did after; v0.23 took it to ten. That
number counts **cures NAMED**. Nothing in thirty rounds has counted **cures
FOLLOWED** --- whether a reader who does what the message says ends up with
a program that runs.

This module measures the second number. It is deliberately a separate
question from the first, and it does not revise it: `9/10 -> 10/10` was and
remains a true statement about naming.

The strict operational form of "sufficient" used here:

    A cure is MECHANICAL if the error message --- its body, its
    parenthetical hint, its line and its column --- determines a unique
    edit to the source text, with no appeal to knowledge of Whence that
    the message does not itself contain.

`CURES` below is the table of every cure the parser can name, each with the
determinacy verdict and, for the mechanical ones, an applier whose ONLY
licence is the transformation the hint's own example demonstrates. Each
rule records that licence in `derivation`, so the claim "this edit follows
from the message" is auditable rather than asserted.

Anti-rot: every rule keys on a hint constant IMPORTED from `whence.parser`,
never on a copy of its wording. If a future round rewords a hint, the
import still resolves, the trigger still fires, and
`tests/test_v33.py::test_every_parser_hint_has_a_cure_rule` is what fails ---
loudly, in the fast tier --- rather than this file silently classifying a
message it no longer recognises. That is round 385's lesson in this file's
own key: a rule whose effect is to stop measuring something can never be
checked by the thing it stopped measuring, so the check lives outside it.

Usage
-----
    python3 curecheck.py rules                 # the determinacy table
    python3 curecheck.py apply FILE            # mechanical cure loop, one file
    python3 curecheck.py corpus [--json OUT]   # the whole field corpus
    python3 curecheck.py replay LEDGER         # replay a hand-authored ledger
    python3 curecheck.py verify DIR            # re-run cured copies

`corpus` NEVER writes to the files it reads. The field programs belong to a
separate autonomous system (see `state/known-standing-dirty-paths.json`);
every cure is applied to an in-memory copy.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from whence import parser as P                              # noqa: E402
from whence.lexer import LexError                           # noqa: E402
from whence.parser import ParseError, parse                 # noqa: E402
from whence.foreign import FOREIGN_NAMES                    # noqa: E402


# --- determinacy taxonomy -------------------------------------------------
#
# Four verdicts, and the three failing ones are NOT the same failure. That
# distinction is the point of this file: "the hint is vague" is not a
# finding, "the hint omits the block's extent" is.

MECHANICAL = "mechanical"
#: names the construct, not where it ends --- you cannot place the closer.
UNDER_EXTENT = "under-extent"
#: offers two or more edits and does not say which one applies here.
UNDER_CHOICE = "under-choice"
#: demands a construct and says nothing about what goes inside it.
UNDER_CONTENT = "under-content"
#: no hint at all --- the message states what stopped the parse and stops.
NO_CURE = "no-cure"
#: a hint this table does not know. NOT the same as `NO_CURE`, and the
#: distinction is the whole anti-rot property: a parser that grows an
#: eighth hint must show up here as an unclassified one, loudly, rather
#: than being counted as "the error named no cure" --- which would read as
#: a finding about the LANGUAGE when it is a fact about this file being
#: stale. Round 385 spent a round on a boundary that stopped the evidence
#: from being collected; this is the same failure available in one line.
UNCLASSIFIED = "unclassified-hint"

_UNDER = (UNDER_EXTENT, UNDER_CHOICE, UNDER_CONTENT)

_IDENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")


#: v0.33's clause is one of `FOREIGN_NAMES`' own sentences, verbatim, so
#: the matcher is the table --- not a copy of any wording in it.
_FOREIGN_PATTERN = None       # built below, once `FOREIGN_NAMES` is read


def _template_pattern(template):
    """A matcher for a hint that is a `%s` template, built FROM the template.

    `_SEPARATOR_HINT` was the one hint in `parser.py` that interpolated the
    offending token, so no exact string can identify it. Deriving the
    pattern by splitting the imported template on its own `%s` keeps the
    anti-rot property the others get for free: reword the template and this
    pattern follows it; delete the `%s` and it still works.

    v0.34 FIXED A LATENT DEFECT HERE. `re.split` returns only the LITERAL
    parts --- `%s` has no group, so it is not captured --- and the original
    joined them with `re.escape(part) if i % 2 == 0 else ".*"`, which
    treats every SECOND LITERAL as a wildcard. For a template with one
    `%s` that is `escaped_prefix + ".*"`, which under `.search` is a
    correct prefix match by accident; for a template with two it silently
    discards the text between the placeholders, and for three it discards
    most of the sentence. Nothing noticed for six rounds because
    `_SEPARATOR_HINT` was the only template in the table.
    `_FN_EXPR_RECURSIVE_HINT` (v0.34) has three placeholders and is what
    made the accident visible.
    """
    return re.compile(".*?".join(re.escape(part)
                                 for part in re.split(r"%s", template)))


def _template_capture(template):
    """`_template_pattern`, but the interpolated spans are CAPTURED.

    v0.34. `_BLOCK_TAIL_LET_HINT` interpolates the bound NAME, and that
    name is the datum its applier needs --- the message's own column is the
    closing brace, which is not where the edit goes. Reading it back out of
    the rendered hint is the only channel a READER has, so it is the only
    channel the applier may use.
    """
    return re.compile("(.*?)".join(re.escape(part)
                                   for part in re.split(r"%s", template))
                      + "$")


class Cure(object):
    """One cure the parser can name, and what following it costs."""

    def __init__(self, key, hint, trigger, determinacy, derivation,
                 missing=None, applier=None):
        self.key = key
        #: the hint's text, imported from `whence.parser` --- never a copy.
        self.hint = hint
        #: matched against the message BODY (the part before the hint).
        self.trigger = trigger
        self.determinacy = determinacy
        #: why the applier's edit follows from the message, in one sentence.
        self.derivation = derivation
        #: for the non-mechanical ones: the datum the message does not carry.
        self.missing = missing
        self._applier = applier
        if (determinacy == MECHANICAL) != (applier is not None):
            raise ValueError("%s: mechanical iff an applier exists" % key)
        if (determinacy in _UNDER) != (missing is not None):
            raise ValueError("%s: under-determined iff `missing` is set" % key)

    def matches(self, body, hint):
        """Does this rule own the error `(body, hint)`?

        BOTH halves must agree, and the hint is the load-bearing half. Two
        pairs of rules in `CURES` share a body pattern and are told apart
        only by their hint: `two statements on one line` carries either
        `_SEPARATOR_HINT` (mechanical) or `_JUXTAPOSE_HINT` (under-choice)
        depending on what the parser found at the column, and `expected X,
        got Y` carries either `_BRACE_HINT` or `_JUXTAPOSE_HINT`. Matching
        on the body alone would collapse each pair onto whichever rule this
        list happens to hold first --- a classifier whose answer depends on
        its own source order, which is not a classifier.

        `hint` may be an exact string, a compiled pattern (for the one hint
        that is a `%s` template), or None for "this rule does not care".
        """
        if self.hint is not None:
            if hint is None:
                return False
            if hasattr(self.hint, "search"):
                if not self.hint.search(hint):
                    return False
            elif hint != self.hint:
                return False
        return bool(self.trigger.search(body))

    def apply(self, lines, line, col, body, hint):
        return self._applier(lines, line, col, body, hint)


# --- the mechanical appliers ---------------------------------------------
#
# Each of these is licensed by exactly one sentence of one hint, quoted in
# the rule's `derivation`. None of them may consult the grammar.

def _apply_assignment(lines, line, col, body, hint):
    """`x = 2` -> `let x = 2`.

    Licence: the hint's example is `let name = value`, which shows `let`
    immediately before the name. The message's column is the `=`. So the
    name is the identifier that ends where the `=` begins.
    """
    text = lines[line - 1]
    i = col - 1                          # 0-based index of the `=`
    j = i
    while j > 0 and text[j - 1].isspace():
        j -= 1
    k = j
    while k > 0 and (text[k - 1].isalnum() or text[k - 1] == "_"):
        k -= 1
    if k == j or not _IDENT.match(text[k:j]):
        return None                      # no name before the `=` --- decline
    out = list(lines)
    out[line - 1] = text[:k] + "let " + text[k:]
    return out


def _apply_record(lines, line, col, body, hint):
    """`{a: 1}` -> `@{a: 1}`.

    Licence: the hint prints both spellings side by side, and the only
    difference between them is an `@` before the `{`. The message's column
    is the `:`; in the hint's own example the `{` is the one that opens the
    text the `:` sits in, so: the nearest preceding `{` that is not already
    preceded by `@`.
    """
    li, ci = line - 1, col - 1
    while li >= 0:
        text = lines[li]
        start = ci if li == line - 1 else len(text)
        b = text.rfind("{", 0, start)
        while b != -1:
            if b == 0 or text[b - 1] != "@":
                out = list(lines)
                out[li] = text[:b] + "@{" + text[b + 1:]
                return out
            b = text.rfind("{", 0, b)
        li -= 1
    return None


def _apply_separator(lines, line, col, body, hint):
    """`a b` (two statements) -> `a` NEWLINE `b`.

    Licence: the hint ends `--- start `X` on the next line`, and `X` is the
    token the column points at. Splitting the line immediately before that
    column starts `X` on the next line and changes nothing else. The new
    line copies the old one's leading whitespace, which is not licensed by
    the hint and is not load-bearing --- Whence has no indentation rule ---
    but keeps the file readable for whoever reads the trace.
    """
    text = lines[line - 1]
    i = col - 1
    if i <= 0 or i >= len(text):
        return None
    head = text[:i].rstrip()
    tail = text[i:]
    if not head or not tail.strip():
        return None
    indent = text[:len(text) - len(text.lstrip())]
    out = list(lines)
    out[line - 1:line] = [head, indent + tail]
    return out


_BLOCK_TAIL_LET_NAME = _template_capture(P._BLOCK_TAIL_LET_HINT)


def _apply_block_tail_let(lines, line, col, body, hint):
    """`{ ... let y = e }` -> `{ ... e }`.

    Licence, in two halves. WHERE: the hint interpolates the bound name,
    and the message's column is the block's closing brace; a block cannot
    rebind (`'x' is already bound in this block`), so at most one
    `let <name> =` lies between the block's start and that brace, and
    scanning backwards from it finds that line and no other. WHAT: the
    hint prints `let %s = e` beside `write `e` on its own`, and the only
    difference between the two is the `let <name> =` prefix.

    The applier declines if no such line is found rather than guessing,
    which is what makes `no-progress` distinguishable from `stalled` in
    the survey.
    """
    m = _BLOCK_TAIL_LET_NAME.search(hint or "")
    if not m:
        return None
    name = m.group(1)
    pat = re.compile(r"^(\s*)let\s+" + re.escape(name) + r"\s*=\s*(\S.*)$")
    for li in range(min(line, len(lines)) - 1, -1, -1):
        mm = pat.match(lines[li])
        if mm:
            out = list(lines)
            out[li] = mm.group(1) + mm.group(2)
            return out
    return None


def _apply_fn_expr_name(lines, line, col, body, hint):
    """`fn adder(a, b) { ... }` -> `fn(a, b) { ... }`, in expression position.

    Licence: the hint prints `fn(x) { x }` beside `fn <name>(x) { x }` and
    the sole difference is the name; the message's column is the name.
    Deleting it, and the run of whitespace in front of it, is the edit the
    hint's two spellings demonstrate.

    This is the round's second instance of *mechanical is not correct*:
    when the body calls itself the parser emits the OTHER hint, which this
    rule does not own, precisely so that this edit is never licensed there.
    """
    text = lines[line - 1]
    i = col - 1
    if i < 0 or i >= len(text):
        return None
    j = i
    while j < len(text) and (text[j].isalnum() or text[j] == "_"):
        j += 1
    if j == i:
        return None
    k = i
    while k > 0 and text[k - 1].isspace():
        k -= 1
    if k == 0:
        return None
    out = list(lines)
    out[line - 1] = text[:k] + text[j:]
    return out


# --- the table ------------------------------------------------------------

class _ExactSet(object):
    """Matches a hint that IS one of the table's sentences. `search` so it
    can sit in `Cure.hint` beside `_template_pattern`'s compiled regex."""

    def __init__(self, sentences):
        self._set = frozenset(sentences)

    def search(self, hint):
        return hint in self._set


_FOREIGN_PATTERN = _ExactSet(FOREIGN_NAMES.values())


CURES = [
    Cure(
        key="assignment",
        hint=P._SYNTAX_HINTS["="],
        trigger=re.compile(r"^unexpected '='"),
        determinacy=MECHANICAL,
        derivation="the hint's example `let name = value` puts `let` before "
                   "the name; the column is the `=`, so the name is the "
                   "identifier ending at it",
        applier=_apply_assignment,
    ),
    Cure(
        key="record-literal",
        hint=P._RECORD_HINT,
        trigger=re.compile(r"^unexpected ':'"),
        determinacy=MECHANICAL,
        derivation="the hint prints `@{a: 1}` beside `{a: 1}`; the sole "
                   "difference is an `@`, and the `{` to put it on is the "
                   "one the `:` sits inside",
        applier=_apply_record,
    ),
    Cure(
        key="missing-separator",
        hint=_template_pattern(P._SEPARATOR_HINT),
        trigger=re.compile(r"^two statements on one line"),
        determinacy=MECHANICAL,
        derivation="the hint ends `start `X` on the next line` and the "
                   "column is where `X` starts, so the edit is a line break "
                   "at that column",
        applier=_apply_separator,
    ),
    Cure(
        key="braced-block",
        hint=P._BRACE_HINT,
        trigger=re.compile(r"^expected '\{', got "),
        determinacy=UNDER_EXTENT,
        derivation="the hint shows `if c { a } else { b }`, which places an "
                   "opening brace at the column --- and a closing brace at a "
                   "position the message never mentions",
        missing="where the block ENDS. The message gives one position, and "
                "a braced block needs two. `else\\n  x + y` and `else\\n  x\\n"
                "  y` differ only in the extent, and the message is identical "
                "for both.",
    ),
    Cure(
        key="juxtaposition",
        hint=P._JUXTAPOSE_HINT,
        trigger=re.compile(r"^(expected .*, got |two statements on one line)"),
        determinacy=UNDER_CHOICE,
        derivation="the hint names TWO spellings --- `a call is `f(x)`` and "
                   "`text must be quoted` --- for one position",
        missing="WHICH of the two edits applies. `print(Calculating total)` "
                "wants quotes and `f x` wants parentheses, and the message "
                "is word-for-word identical for both.",
    ),
    Cure(
        key="rescue-infix",
        hint=P._SYNTAX_HINTS["rescue"],
        trigger=re.compile(r"^unexpected 'rescue'"),
        determinacy=UNDER_EXTENT,
        derivation="the hint's example `risky rescue fallback` is a "
                   "REORDERING of three spans, and the message locates only "
                   "the `rescue`",
        missing="where `risky` and `fallback` begin and end. The column is "
                "the `rescue` keyword; the two operands it must sit between "
                "are spans the message never delimits, and in the field "
                "corpus they cross lines and carry a `catch ... as err` "
                "binder the target form has no place for.",
    ),
    Cure(
        key="foreign-word",
        hint=_FOREIGN_PATTERN,
        trigger=re.compile(r""),
        determinacy=UNDER_EXTENT,
        derivation="v0.33 names the foreign word and the Whence construct "
                   "that replaces it --- two constructs, and no span",
        missing="what to REWRITE. Every one of the table's sentences that "
                "can reach a parse error names a construct swap (`for`/"
                "`while` -> `map`/`filter`/`fold`, `catch`/`try` -> `risky "
                "rescue fallback`, `return` -> a block's last expression), "
                "not an edit at a position. This is a strictly better "
                "message than the one it replaces and it is still not "
                "mechanical --- naming the right construct is not the same "
                "as determining the edit, which is this round's whole "
                "finding stated about its own fix.",
    ),
    Cure(
        key="if-requires-else",
        hint=P._IF_ELSE_HINT,
        trigger=re.compile(r"^'if' requires 'else'"),
        determinacy=UNDER_CONTENT,
        derivation="the message states a requirement and gives the reason "
                   "(`every expression has a value`) but shows no example "
                   "and names no value",
        missing="WHAT the else branch should evaluate to. The message "
                "establishes that a value is needed and is silent on which "
                "one; nothing in it distinguishes `else { 0 }` from `else "
                "{ miss(\"...\") }`.",
    ),
    # --- v0.34 (round 392): the three messages that named no cure --------
    Cure(
        key="block-tail-let",
        hint=_template_capture(P._BLOCK_TAIL_LET_HINT),
        trigger=re.compile(r"^block must end with an expression"),
        determinacy=MECHANICAL,
        derivation="the hint names the bound NAME, a block cannot rebind, "
                   "so `let <name> =` is unique between the block's start "
                   "and the column; the hint prints `let <name> = e` beside "
                   "`write `e` on its own`, and the difference is the prefix",
        applier=_apply_block_tail_let,
    ),
    Cure(
        key="block-tail-fn",
        hint=_template_capture(P._BLOCK_TAIL_FN_HINT),
        trigger=re.compile(r"^block must end with an expression"),
        determinacy=UNDER_CHOICE,
        derivation="the hint names one spelling (`fn(x) { x }`) for a "
                   "statement that may also want lifting out of the block "
                   "entirely",
        missing="WHICH of the two. Dropping the name makes the fn the "
                "block's value; but a named fn last in a block is as often "
                "a definition the author meant to CALL, and the message "
                "cannot tell those apart --- unlike the fn-EXPRESSION case, "
                "where the body's own tokens decide.",
    ),
    Cure(
        key="block-tail-check",
        hint=P._BLOCK_TAIL_CHECK_HINT,
        trigger=re.compile(r"^block must end with an expression"),
        determinacy=UNDER_CONTENT,
        derivation="the hint says a `check` is not a value and that the "
                   "value goes on the next line; it names no value",
        missing="WHAT the block's value is. Same shape as "
                "`if-requires-else`: the message establishes that a value "
                "is needed and is silent on which one.",
    ),
    Cure(
        key="block-tail-shape",
        hint=P._BLOCK_TAIL_SHAPE_HINT,
        trigger=re.compile(r"^block must end with an expression"),
        determinacy=UNDER_CONTENT,
        derivation="as `block-tail-check`: the hint names the construct "
                   "that is not a value and says where the value goes",
        missing="WHAT the block's value is. This clause exists to stop the "
                "`let` sentence being printed about a line that says "
                "`shape`; it is a guard against a WRONG cure, and being "
                "under-determined is the price of being right.",
    ),
    Cure(
        key="empty-block",
        hint=P._EMPTY_BLOCK_HINT,
        trigger=re.compile(r"^block must contain at least one expression"),
        determinacy=UNDER_CONTENT,
        derivation="the hint states the rule (every block has a value) and "
                   "shows the smallest block, `{ 0 }`, as an illustration "
                   "of the SHAPE rather than as the cure",
        missing="WHICH value. `{ 0 }` is deliberately not offered as the "
                "edit --- an empty block is empty because the author had "
                "not written the value yet, and inserting a `0` would "
                "produce a program that runs and is wrong, which is the "
                "failure `nano_reasoner.lang:31` already demonstrates.",
    ),
    Cure(
        key="fn-expression-name",
        hint=_template_capture(P._FN_EXPR_ANON_HINT),
        # v0.35 (round 396), decision 44: the parser quotes the token it
        # wanted, so this is `expected '(', got …` and no longer
        # `expected (, got …`. `braced-block`'s trigger above needed no
        # edit -- that message was ALREADY quoted, which is the asymmetry
        # decision 44 removed.
        trigger=re.compile(r"^expected '\(', got "),
        determinacy=MECHANICAL,
        derivation="the hint prints `fn(x) { x }` beside `fn <name>(x) "
                   "{ x }`; the sole difference is the name, and the "
                   "column is the name",
        applier=_apply_fn_expr_name,
    ),
    Cure(
        key="fn-expression-recursive",
        hint=_template_capture(P._FN_EXPR_RECURSIVE_HINT),
        # v0.35 (round 396), decision 44: the parser quotes the token it
        # wanted, so this is `expected '(', got …` and no longer
        # `expected (, got …`. `braced-block`'s trigger above needed no
        # edit -- that message was ALREADY quoted, which is the asymmetry
        # decision 44 removed.
        trigger=re.compile(r"^expected '\(', got "),
        determinacy=UNDER_EXTENT,
        derivation="the hint asks for the whole `fn` to be lifted to a "
                   "statement of its own and locates only its name",
        missing="where the `fn` BEGINS and ENDS. Lifting a construct out "
                "of an argument list is a two-position edit and the "
                "message gives one --- the same shortfall `rescue-infix` "
                "and `braced-block` have, arrived at from the other "
                "direction: this hint is the one the parser chooses when "
                "it has read enough of the program to know the MECHANICAL "
                "cure would be wrong.",
    ),
    Cure(
        key="infix-no-left-operand",
        hint=_template_capture(P._INFIX_HINT),
        trigger=re.compile(r"^unexpected "),
        determinacy=UNDER_CONTENT,
        derivation="the hint names the operator's shape (`a OP b`) and "
                   "says the left-hand side is absent; it names no operand",
        missing="WHAT belongs on the left. And in the field corpus the "
                "answer is often neither operand: `print(=== H ===)` is "
                "unquoted text whose `===` lexes as `==` then `=`, so the "
                "true cure is quotation. The clause is still strictly "
                "better than the bare `unexpected '=='` it replaces, and "
                "still not the edit.",
    ),
]

_BY_KEY = dict((c.key, c) for c in CURES)


def parser_hint_sentences():
    """Every hint sentence `whence.parser` can attach, DERIVED from it.

    v0.34, and the reason it exists is a defect in the thing it replaces.
    Round 386 built `test_v33.py::test_the_parsers_hint_constants_are_all_
    owned_by_a_cure_rule` as the anti-rot check for this table, promising
    that "an eighth hint added by a future round arrives here as a
    failure". It did not: that test builds its own list by NAMING four
    constants, so v0.34's eight new hints were invisible to it and the
    fast suite stayed green through the whole change. A hand-written list
    of the things a hand-written list might miss is not an anti-rot check.

    This reads `parser.py`'s module namespace instead: every module-level
    `_..._HINT` string, rendered with a placeholder for each `%s` it
    interpolates, plus the two tables' values. A ninth constant is found
    because it is a `_HINT`, not because someone remembered it.
    `tests/test_v34.py::test_the_hint_census_is_derived_and_not_a_list`
    cross-checks the count against a grep of the source.
    """
    out = []
    for name in sorted(vars(P)):
        if not (name.startswith("_") and name.endswith("_HINT")):
            continue
        value = getattr(P, name)
        if not isinstance(value, str):
            continue
        n = value.count("%s")
        out.append(value % (("x",) * n) if n else value)
    out.extend(P._SYNTAX_HINTS.values())
    out.extend(FOREIGN_NAMES.values())
    return out


# --- reading an error -----------------------------------------------------

_AT = re.compile(r"^(?P<msg>.*) at line (?P<line>\d+), col (?P<col>\d+)\Z",
                 re.S)


def split_message(rendered):
    """`body (hint) at line L, col C` -> `(body, hint_or_None, line, col)`.

    This is the reader's view and nothing more: the string `run.py` prints
    after `error: `. It does not touch the exception object's attributes,
    because a reader does not have them.
    """
    m = _AT.match(rendered)
    if not m:
        return rendered, None, None, None
    msg = m.group("msg")
    line, col = int(m.group("line")), int(m.group("col"))
    if msg.endswith(")"):
        depth = 0
        for i in range(len(msg) - 1, -1, -1):
            if msg[i] == ")":
                depth += 1
            elif msg[i] == "(":
                depth -= 1
                if depth == 0:
                    return msg[:i].rstrip(), msg[i + 1:-1], line, col
    return msg, None, line, col


def classify(rendered):
    """Which cure, if any, this message names. `NO_CURE` when none does."""
    body, hint, line, col = split_message(rendered)
    if line is None:
        return None, body, hint, line, col
    for cure in CURES:
        if cure.matches(body, hint):
            return cure, body, hint, line, col
    return None, body, hint, line, col


def determinacy_of(cure, hint):
    """`NO_CURE` when the message carried no hint, `UNCLASSIFIED` when it
    carried one this table does not own."""
    if cure is not None:
        return cure.determinacy
    return NO_CURE if hint is None else UNCLASSIFIED


def parse_error_of(text):
    """The rendered first error of `text`, or None if it parses."""
    try:
        parse(text)
    except (ParseError, LexError) as e:
        return str(e)
    return None


# --- the cure loop --------------------------------------------------------

MAX_STEPS = 40


def cure_loop(text, max_steps=MAX_STEPS):
    """Follow every MECHANICAL cure until something stops us.

    Returns `(final_text, steps, outcome)`. `outcome` is one of:
      `parses`          --- no parse error is left
      `stalled`         --- the next cure is under-determined (or absent)
      `no-progress`     --- an applier declined, or produced the same text
      `budget`          --- `max_steps` mechanical edits and still failing
    """
    steps = []
    lines = text.split("\n")
    for _ in range(max_steps):
        rendered = parse_error_of("\n".join(lines))
        if rendered is None:
            return "\n".join(lines), steps, "parses"
        cure, body, hint, line, col = classify(rendered)
        step = {
            "error": rendered,
            "body": body,
            "hint": hint,
            "line": line,
            "col": col,
            "cure": cure.key if cure else None,
            "determinacy": determinacy_of(cure, hint),
        }
        if cure is None or cure.determinacy != MECHANICAL:
            steps.append(step)
            return "\n".join(lines), steps, "stalled"
        out = cure.apply(lines, line, col, body, hint)
        if out is None or out == lines:
            step["declined"] = True
            steps.append(step)
            return "\n".join(lines), steps, "no-progress"
        after = parse_error_of("\n".join(out))
        _, _, _, nline, _ = classify(after) if after else (None, None, None, None, None)
        step["applied"] = True
        step["next_line"] = nline
        # P11's monotonicity claim, recorded per step rather than asserted.
        step["moved_backwards"] = (nline is not None and nline < line)
        steps.append(step)
        lines = out
    return "\n".join(lines), steps, "budget"


def replay(ledger, root=None):
    """Replay a hand-authored cure ledger, recording every error on the way.

    The mechanical loop (`cure_loop`) answers "can a machine follow the
    message?" and its answer is 0 of 10. This answers the other half ---
    "can a READER?" --- without letting the answer be anecdotal. Each entry
    is a literal search/replace plus the cure it answers and the
    information the reader had to supply that the message did not; applying
    them in order and re-parsing between each is what turns a session of
    hand-editing into a number anyone can re-derive.

    An entry whose `old` is not present is a hard error, not a skip: a
    ledger that has drifted from the corpus must fail loudly. The corpus is
    a separate system's and CAN change under us --- `field_programs` reads
    it from git every time for the same reason.
    """
    root = root or _HERE
    by_file = {}
    for e in ledger:
        by_file.setdefault(e["file"], []).append(e)
    rows = []
    for name, edits in sorted(by_file.items()):
        path = os.path.join(root, "examples", name)
        with open(path) as fh:
            text = fh.read()
        seen = []
        for e in edits:
            err = parse_error_of(text)
            if err is not None:
                cure, body, hint, line, col = classify(err)
                seen.append({"error": err, "line": line,
                             "cure": cure.key if cure else None,
                             "determinacy": determinacy_of(cure, hint),
                             "answers": e["answers"], "needed": e["needed"]})
            if e["old"] not in text:
                raise SystemExit("ledger drift: %s: %r not found"
                                 % (name, e["old"][:60]))
            text = text.replace(e["old"], e["new"], 1)
        final_err = parse_error_of(text)
        # Which edits fixed a mistake the GRAMMAR ACCEPTS? Not "which ones
        # happened after the file started parsing" --- an edit can answer no
        # error while other errors are still outstanding elsewhere in the
        # file, and in `whenceguard_v2.lang` most of them do. The claim is
        # per-edit and is tested per-edit: put that ONE edit back into the
        # fully cured file and ask whether the result still parses. If it
        # does, no message about it was ever available to the author.
        accepted = []
        if final_err is None:
            for e in edits:
                if e["new"] not in text:
                    continue
                reverted = text.replace(e["new"], e["old"], 1)
                if parse_error_of(reverted) is None:
                    accepted.append(e["old"].strip().split("\n")[0][:70])
        tmp = os.path.join("/tmp", "curecheck-assisted-" + name)
        with open(tmp, "w") as fh:
            fh.write(text)
        rc = strict = None
        if final_err is None:
            rc, _ = run_program(tmp)
            strict, _ = run_program(tmp, strict=True)
        rows.append({"file": name, "edits": len(edits),
                     "parse_errors_seen": seen,
                     "edits_for_accepted_text": accepted,
                     "n_accepted": len(accepted),
                     "final_error": final_err, "rc": rc, "strict_rc": strict,
                     "cured_path": tmp})
    return rows


def run_program(path, timeout=90, strict=False):
    """`python3 run.py path` --- returncode and the tail of its output."""
    proc = subprocess.run(
        [sys.executable, os.path.join(_HERE, "run.py")]
        + (["--strict-miss"] if strict else []) + [path],
        cwd=_HERE, capture_output=True, text=True, timeout=timeout,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


# --- the corpus -----------------------------------------------------------

# `_HERE`'s grandparent is the repo root only when this file is IN the
# checkout. Under `harness/swe/mutation.py` the suite runs from a tempdir copy
# of `languages/whence` alone, where the grandparent is `/tmp` — round 149's
# defect, and `harness/swe/proc.py` exports `AGI_RESEARCH_ROOT` into every such
# subprocess for exactly this. Four other files in this tree already read it
# (`bench/ref_diff.py`, `bench/reserve_probe.py`, `tests/test_v10.py`,
# `tests/test_parser_differential.py`); this one did not, and because the read
# happens at IMPORT time in `tests/test_field_corpus_selector.py`, the
# resulting `FileNotFoundError: /tmp/state/whence/round-384/field-names.json`
# aborted COLLECTION of the whole suite. Measured round 413: `baseline_check(
# "languages/whence", DEFAULT_TEST_CMD)` exited 1 in 0.55 s with `1 error`, so
# `mutation_test` raised `BaselineNotGreen` before generating a single mutant
# — every Whence mutation campaign was blocked at the door.
_AGI_ROOT = (os.environ.get("AGI_RESEARCH_ROOT")
             or os.path.dirname(os.path.dirname(_HERE)))

#: Where to run `git` when asking about the example corpus. THE one home for
#: that root (round 413). The corpus-in-git QUESTION is deliberately
#: duplicated across this tree — `harness/tests/test_pristine_check.py::
#: test_the_curated_corpus_rule_is_duplicated_only_where_declared` censuses
#: the copies on purpose, because the whence suite must not import
#: `harness/`. What was duplicated by ACCIDENT is the root each copy runs
#: git in: five sites, five `__file__`-derived roots, none of them consulting
#: `AGI_RESEARCH_ROOT`. Under a mutation copy they degrade three different
#: ways — `CalledProcessError` (test_lexer_guest_parity), an empty stdout
#: silently read as "nothing is tracked" (test_v24, test_v26 without
#: `check=True`), and a glob fallback that returns the untracked field corpus
#: too — and any one of them is enough to make `mutation_test` raise
#: `BaselineNotGreen`.
#:
#: Outside a `harness/swe/proc.py` subprocess the env var is unset and both
#: values are exactly what each site computed before, so this changes nothing
#: about a plain `pytest languages/whence/tests`.
REPO_GIT_ROOT = _AGI_ROOT
WHENCE_GIT_ROOT = os.path.join(_AGI_ROOT, "languages", "whence")

#: Public alias. Anything in this tree that must reach a path OUTSIDE it —
#: `state/`, `harness/`, git — resolves it from here rather than from its own
#: `__file__`, so it keeps working when the tree is copied somewhere else.
AGI_ROOT = _AGI_ROOT

FIELD_CENSUS = os.path.join(
    _AGI_ROOT, "state", "whence", "round-384", "field-names.json")


def _census_md5():
    """`{basename: md5}` --- round 384's frozen census, read once per call.

    The ONE reader of the census file in this repo's runtime code. Round 410
    made it one: `_corpus_unchanged()` in `tests/test_v33.py` and
    `tests/test_v34.py` were a second and third, byte-identical to each
    other, and being three copies was not the defect --- answering two
    different questions with one answer was. See `field_corpus_skip_reason`.
    """
    with open(FIELD_CENSUS, encoding="utf-8") as fh:
        return {os.path.basename(k): v
                for k, v in json.load(fh)["file_md5"].items()}


def field_census_names():
    return sorted(_census_md5())


def field_programs(root=None):
    """The `.lang` files a separate system leaves in `examples/`.

    Round 386 derived this from `git ls-files --others` — untracked status —
    with the reasoning that "a hard-coded list is exactly the kind of
    name-for-a-fact round 385 spent a round on. If the gateway adds a program
    tomorrow this picks it up." Both halves were right and the premise was
    not stable.

    Round 393's `git add -A` sweep (commit `49969fb`) TRACKED all fourteen of
    them, so from that commit `--others` returned the empty list and this
    function reported that the field corpus does not exist. A derived subject
    set can go silently EMPTY, and that is worse than going stale: every
    "for all" assertion over it becomes vacuously true and every "there are
    N" assertion fails without naming the cause. Four tests in `test_v33.py`
    and `test_v34.py` failed as `assert 0 == 10` and `KeyError:
    'nano_reasoner.lang'` — neither of which says "the selector found
    nothing". The `_corpus_unchanged()` skip-guard built for exactly this
    event could not help: the FILES had not moved (same names, same md5s),
    only their git status had, and the guard is a census of files.

    The authority is now `state/whence/round-384/field-names.json`, which has
    declared these fourteen names since round 384 and is what
    `_corpus_unchanged()` already trusts — so this is not a new hand-written
    list, it is the list the repo already had, read instead of re-derived
    from a proxy. Round 386's live property is kept as a CHECK rather than as
    the source: `field_corpus_drift()` still asks git, and reports an
    untracked `.lang` the census does not name.
    """
    root = root or _HERE
    paths = [os.path.join(root, "examples", n) for n in field_census_names()]
    return sorted(p for p in paths if os.path.exists(p))


#: Why a test whose subject is the field corpus has NO subject in a fresh
#: checkout. Round 402 resolved a contradiction between two of this repo's
#: records by `git rm --cached`-ing the fourteen field programs and naming
#: every one of them in `.gitignore`. That was the right call for the census
#: — and it also means the corpus exists in the ONE working tree a separate
#: system writes into and in NO git checkout of ANY commit. `git worktree
#: add --detach /tmp/x HEAD` produces a tree without it, at every commit,
#: forever.
FIELD_CORPUS_ABSENT_REASON = (
    "the 14-file field corpus is absent from this checkout: round 402 named "
    "all fourteen in .gitignore, so they exist only in a working tree the "
    "Hermes gateway has written into and in no checkout of any commit. A "
    "test whose subject is that corpus has no subject here — this is not a "
    "regression in anything this project wrote.")


def field_corpus_absent(root=None):
    """True only when the declared corpus is ENTIRELY absent from `root`.

    All-or-nothing on purpose, and the two halves are different facts:

      * NONE of the fourteen present — this checkout was never the tree the
        gateway writes into. Nothing about it is evidence, so a corpus test
        should SKIP.
      * SOME present and some not — DRIFT. The gateway deleted or renamed a
        program, `field_corpus_drift` will name it, and the tests must stay
        RED. Skipping here would be the exact failure this predicate is
        being added to avoid: a skip that swallows a real finding.

    Round 409. Four fast-tier tests read the corpus off disk with no guard
    and therefore failed in every worktree at every commit — which broke
    `harness/pristine_check.py` itself, since four unconditional
    pristine-only failures make its `whence-fast` verdict a permanent, false
    `git_incomplete`. Round 395's `test_v33.py`/`test_v34.py` already had
    `_corpus_unchanged()` for the sibling case (the gateway REWROTE a file)
    and those tests skip cleanly; the guard was simply never extended to the
    file round 395 wrote next, or to `test_v24.py`.
    """
    root = root or _HERE
    declared = field_census_names()
    return bool(declared) and len(field_corpus_missing(root)) == len(declared)


def field_corpus_missing(root=None):
    """Declared programs that are not on disk under `root`, sorted.

    One computation of "which of the fourteen are gone", used by
    `field_corpus_absent` (are they ALL gone?), by `field_corpus_skip_reason`
    (are SOME gone?) and by `field_corpus_drift` (which ones, and is there
    anything undeclared next to them?). Round 410 split it out because the
    first two of those three had been asking git, or asking the filesystem
    twice, for an answer the third already had.
    """
    root = root or _HERE
    return sorted(n for n in field_census_names()
                  if not os.path.exists(os.path.join(root, "examples", n)))


#: Why a corpus-derived NUMBER is not a regression when the corpus moves.
#: `%s` is the name of the first program whose bytes differ from round 384's
#: census. Distinct from `FIELD_CORPUS_ABSENT_REASON` on purpose: that one
#: says the subject was never here, this one says the subject is here and is
#: a different subject. Round 395's `_corpus_unchanged()` produced ONE
#: sentence, `field corpus moved: missing: X`, for both --- so in a fresh
#: `git worktree`, where nothing had moved and nothing had been rewritten,
#: seven tests skipped saying the gateway had rewritten a file.
FIELD_CORPUS_CHANGED_REASON = (
    "the field corpus has been REWRITTEN since round 384's census (%s). The "
    "Hermes gateway is a separate autonomous system that shares this repo "
    "and may rewrite its programs without notice, so a corpus-derived "
    "number is NEW INFORMATION rather than a regression in anything this "
    "project wrote --- re-freeze the census deliberately, do not edit the "
    "expected number to make the suite quiet.")


def field_corpus_changed(root=None):
    """The first declared program PRESENT on disk whose bytes are not the
    ones round 384 froze, or None.

    Deliberately says NOTHING about a program that is absent. Absence has
    two readings and neither of them is "rewritten": none present is a
    checkout that was never the gateway's tree (`field_corpus_absent`), and
    some present is drift (`field_corpus_drift`). Round 410 split this out
    of `_corpus_unchanged()`, whose `missing:` branch made those readings
    unreachable.
    """
    root = root or _HERE
    census = _census_md5()
    for name in sorted(census):
        path = os.path.join(root, "examples", name)
        if not os.path.exists(path):
            continue
        with open(path, "rb") as fh:
            if hashlib.md5(fh.read()).hexdigest() != census[name]:
                return name
    return None


def field_corpus_skip_reason(root=None):
    """The ONE decision every corpus-derived test needs: skip, and why --- or
    None, meaning run.

    FOUR states of the field corpus, and the whole point of this function is
    that they are four --- it was written with three and its own test found
    the fourth:

      * **none of the declared programs present.** This checkout was never
        the tree the gateway writes into; round 402 named all fourteen in
        `.gitignore`, so no checkout of any commit has them. A test whose
        subject is the corpus has no subject -> SKIP, with
        `FIELD_CORPUS_ABSENT_REASON`.
      * **all present, one rewritten.** The gateway moved; the measurement
        is about a different corpus than the one the number was frozen
        against -> SKIP, with `FIELD_CORPUS_CHANGED_REASON`.
      * **some present, some gone.** DRIFT -> **None**. The tests RUN and go
        red, and `field_corpus_drift()` names the file. A skip here would
        swallow exactly the event drift-reporting exists to report.
      * **some gone AND one of the rest rewritten.** Still **None**. The
        fourth state is not a corner case, it is what a gateway that
        reorganises its programs actually produces, and answering it with
        the rewrite's skip would hide the deletion behind the smaller
        event. The order of the two checks below IS this rule.

    Round 395's `_corpus_unchanged()` collapsed the first and third into the
    second: any missing file returned `"missing: X"`, which skipped, under a
    reason string that said the corpus had MOVED. Two costs, and the quiet
    one is worse. Loud: in every `git worktree` --- where all fourteen are
    absent for a reason that has nothing to do with the gateway --- seven
    tests announced a rewrite that had not happened. Quiet: if the gateway
    DELETES one of the fourteen, the seven tests that measure the corpus go
    silent about it, and the drift report that would have named the file is
    in a different file that nobody has to read.

    `tests/test_field_corpus_selector.py::test_the_old_helper_skipped_the_
    one_state_that_must_stay_red` re-runs that falsification against a
    verbatim copy of the old helper, every fast tier, forever.
    """
    root = root or _HERE
    missing = field_corpus_missing(root)
    declared = field_census_names()
    if declared and len(missing) == len(declared):
        return FIELD_CORPUS_ABSENT_REASON
    if missing:
        # DRIFT, and it is checked BEFORE the rewrite because the two can be
        # true at once. Round 410 wrote this function with three states, and
        # `test_a_rewritten_corpus_does_not_hide_a_missing_one` --- written
        # in the same round to assert the ordering --- failed, because the
        # gateway deleting one program and rewriting another produced the
        # REWRITE's skip and buried the deletion under it. A deletion is the
        # louder event: it is the one that can be a mistake.
        return None
    changed = field_corpus_changed(root)
    if changed is not None:
        return FIELD_CORPUS_CHANGED_REASON % changed
    return None


def field_corpus_drift(root=None):
    """`(undeclared, missing)` — a new gateway program, and a declared one
    that is gone. Empty tuples mean the census still describes `examples/`.

    This is round 386's "if the gateway adds a program tomorrow this picks it
    up", demoted from the selector to a report, because a selector that
    silently changes its answer when a file's git status changes is not a
    selector for "programs a separate system wrote".
    """
    root = root or _HERE
    proc = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "examples"],
        cwd=root, capture_output=True, text=True,
    )
    untracked = {os.path.basename(n) for n in proc.stdout.split("\n")
                 if n.endswith(".lang")}
    declared = set(field_census_names())
    return sorted(untracked - declared), field_corpus_missing(root)


# There is deliberately NO `tracked_programs()` here. It would have been
# four lines and it would have been a FOURTH copy of the `"git",
# "ls-files", "examples"` literal that
# `harness/tests/test_pristine_check.py::test_the_curated_corpus_rule_is_
# duplicated_only_where_declared` pins --- a pin round 385 watched fire on
# the third copy, after the fact, because `git grep` cannot see an
# uncommitted file. Reading it before writing the copy is the whole point
# of having it. This round has no use for the tracked corpus that the field
# corpus does not serve better, so the honest answer is not to make the
# copy and argue for it; `--others` above does not contain the literal.


def survey(paths, max_steps=MAX_STEPS):
    rows = []
    for path in paths:
        with open(path) as fh:
            text = fh.read()
        first = parse_error_of(text)
        row = {"file": os.path.basename(path), "first_error": first}
        if first is None:
            rc, out = run_program(path)
            row.update(parses=True, rc=rc, outcome="parses-unedited",
                       steps=[], applied=0)
        else:
            cured, steps, outcome = cure_loop(text, max_steps)
            row.update(parses=False, outcome=outcome, steps=steps,
                       applied=sum(1 for s in steps if s.get("applied")))
            if outcome == "parses":
                tmp = os.path.join("/tmp", "curecheck-" + row["file"])
                with open(tmp, "w") as fh:
                    fh.write(cured)
                rc, out = run_program(tmp)
                row["rc"] = rc
        rows.append(row)
    return rows


# --- reporting ------------------------------------------------------------

def _fmt_rules():
    lines = ["%-18s %-14s %s" % ("cure", "determinacy", "trigger")]
    lines.append("-" * 74)
    for c in CURES:
        lines.append("%-18s %-14s %s" % (c.key, c.determinacy,
                                         c.trigger.pattern))
    n_mech = sum(1 for c in CURES if c.determinacy == MECHANICAL)
    lines.append("")
    lines.append("%d cure(s): %d mechanical, %d under-determined "
                 "(%s)" % (len(CURES), n_mech, len(CURES) - n_mech,
                           ", ".join(sorted(set(c.determinacy for c in CURES
                                                if c.determinacy != MECHANICAL)))))
    return "\n".join(lines)


def _fmt_survey(rows):
    out = []
    hdr = "%-28s %-6s %-16s %-4s %s" % ("file", "edits", "outcome", "rc",
                                        "stopped by")
    out.append(hdr)
    out.append("-" * len(hdr))
    for r in rows:
        stopper = ""
        if r["steps"]:
            last = r["steps"][-1]
            if not last.get("applied"):
                stopper = "%s @L%s" % (last["determinacy"], last["line"])
        out.append("%-28s %-6d %-16s %-4s %s" % (
            r["file"], r["applied"], r["outcome"],
            r.get("rc", "-"), stopper))
    total = len(rows)
    reached = sum(1 for r in rows if r.get("rc") == 0)
    parses = sum(1 for r in rows if r["outcome"] in ("parses", "parses-unedited"))
    out.append("")
    out.append("%d file(s): %d parse, %d reach a value (rc=0), "
               "%d mechanical edit(s) applied in total"
               % (total, parses, reached,
                  sum(r["applied"] for r in rows)))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("rules")
    a = sub.add_parser("apply")
    a.add_argument("file")
    a.add_argument("--out", help="write the cured text here")
    c = sub.add_parser("corpus")
    c.add_argument("--json", help="write the full trace here")
    v = sub.add_parser("verify")
    v.add_argument("dir")
    r = sub.add_parser("replay")
    r.add_argument("ledger")
    r.add_argument("--json")
    args = ap.parse_args(argv)

    if args.cmd == "rules":
        print(_fmt_rules())
        return 0
    if args.cmd == "apply":
        with open(args.file) as fh:
            text = fh.read()
        cured, steps, outcome = cure_loop(text)
        for i, s in enumerate(steps, 1):
            print("%d. [%s] %s" % (i, s["determinacy"], s["error"]))
            if not s.get("applied"):
                cure = _BY_KEY.get(s["cure"] or "")
                if cure is not None and cure.missing:
                    print("   missing: %s" % cure.missing)
        print("outcome: %s (%d mechanical edit(s))"
              % (outcome, sum(1 for s in steps if s.get("applied"))))
        if args.out:
            with open(args.out, "w") as fh:
                fh.write(cured)
        return 0 if outcome == "parses" else 1
    if args.cmd == "corpus":
        paths = field_programs()
        rows = survey(paths)
        print(_fmt_survey(rows))
        if args.json:
            with open(args.json, "w") as fh:
                json.dump(rows, fh, indent=2)
        return 0
    if args.cmd == "replay":
        with open(args.ledger) as fh:
            rows = replay(json.load(fh))
        hdr = ("%-28s %-6s %-8s %-8s %-5s %s"
               % ("file", "edits", "errors", "accepted", "rc", "strict"))
        print(hdr); print("-" * len(hdr))
        for r in rows:
            print("%-28s %-6d %-8d %-8d %-5s %s"
                  % (r["file"], r["edits"], len(r["parse_errors_seen"]),
                     r["n_accepted"], r["rc"], r["strict_rc"]))
        ok = sum(1 for r in rows if r["rc"] == 0)
        clean = sum(1 for r in rows if r["strict_rc"] == 0)
        errs = sum(len(r["parse_errors_seen"]) for r in rows)
        acc = sum(r["n_accepted"] for r in rows)
        det = collections.Counter(s["determinacy"]
                                  for r in rows for s in r["parse_errors_seen"])
        print()
        print("%d file(s): %d reach a value, %d clean under --strict-miss"
              % (len(rows), ok, clean))
        uniq = len(set((r["file"], s["error"])
                       for r in rows for s in r["parse_errors_seen"]))
        print("%d edit(s); %d parse-error observation(s) on the way, %d of "
              "them distinct" % (sum(r["edits"] for r in rows), errs, uniq))
        print("%d edit(s) fixed text the grammar ACCEPTS --- no message "
              "about them was ever available" % acc)
        print("determinacy of the %d errors seen: %s"
              % (errs, ", ".join("%s=%d" % kv for kv in sorted(det.items()))))
        if args.json:
            with open(args.json, "w") as fh:
                json.dump(rows, fh, indent=2)
        return 0
    if args.cmd == "verify":
        names = sorted(n for n in os.listdir(args.dir) if n.endswith(".lang"))
        bad = 0
        for n in names:
            path = os.path.join(args.dir, n)
            rc, out = run_program(path)
            tail = [l for l in out.strip().split("\n") if l.strip()]
            print("%-28s rc=%-3d %s" % (n, rc, tail[-1][:90] if tail else ""))
            if rc != 0:
                bad += 1
        print("\n%d file(s): %d reach a value, %d do not"
              % (len(names), len(names) - bad, bad))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

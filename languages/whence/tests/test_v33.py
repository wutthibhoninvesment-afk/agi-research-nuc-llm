"""v0.33 (round 386), decision 42 --- one foreign-word table, two readers.

Three things are pinned here and they are not the same kind of claim:

  1. STRUCTURE. There is exactly one foreign-word table; every hint the
     parser can emit is owned by a `curecheck` rule; a rule is mechanical
     if and only if it has an applier. These are facts about this tree and
     they are pinned exactly.
  2. BEHAVIOUR. The parser names a foreign word, does not name one the file
     binds, and does not shadow the juxtaposition hint when the foreign word
     is the SECOND of two adjacent names (this round's own regression, found
     by the corpus and fixed). Pinned on synthetic programs written here,
     never on the field corpus --- the field corpus belongs to a separate
     autonomous system and can change without notice.
  3. THE CORPUS MEASUREMENT. Round 386's published figures about the ten
     field programs. These are CORPUS-derived (round 383 item 4's class),
     so they are pinned behind round 384's frozen md5 census: if the
     gateway rewrites a program the pin SKIPS with a message rather than
     going red, because a changed corpus is new information and not a
     regression. What stays exact is what derives from constants.
"""

import hashlib
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import curecheck as C                                       # noqa: E402
from whence import parser as P                              # noqa: E402
from whence.foreign import (FOREIGN_NAMES, MISS_REASON_HINT,  # noqa: E402
                            bound_anywhere, name_hint)
from whence.interp import _FOREIGN_NAMES                    # noqa: E402
from whence.lexer import tokenize                           # noqa: E402
from whence.parser import ParseError, parse                 # noqa: E402

CENSUS = os.path.join(os.path.dirname(ROOT), "..", "state", "whence",
                      "round-384", "field-names.json")
LEDGER = os.path.join(os.path.dirname(ROOT), "..", "state", "whence",
                      "round-386", "cure-ledger.json")
EXAMPLES = os.path.join(ROOT, "examples")


def err(src):
    """The rendered parse error of `src`, or None."""
    try:
        parse(src)
    except ParseError as e:
        return str(e)
    return None


# --------------------------------------------------------------------------
# 1. structure
# --------------------------------------------------------------------------

def test_there_is_exactly_one_foreign_table():
    """`interp._FOREIGN_NAMES` is the table, not a copy of it.

    The whole reason the table moved to `whence/foreign.py` is that
    `interp.py` imports `parser.py`, so the parser could not read a table
    that lived in the interpreter. A copy would have been the easy fix and
    is the one round 343 spent a round undoing.
    """
    assert _FOREIGN_NAMES is FOREIGN_NAMES


def test_the_parsers_hint_constants_are_all_owned_by_a_cure_rule():
    """Every hint `parser.py` can attach is classified by `curecheck`.

    This is the anti-rot check the module docstring promises. An eighth
    hint added by a future round arrives here as a failure --- not as a
    silent `no-cure` in a measurement, which would read as a finding about
    the LANGUAGE when it is a fact about `curecheck.py` being stale.
    """
    emitted = ([P._BRACE_HINT, P._RECORD_HINT, P._JUXTAPOSE_HINT,
                P._SEPARATOR_HINT % "x"]
               + list(P._SYNTAX_HINTS.values())
               + list(FOREIGN_NAMES.values()))
    for hint in emitted:
        assert any(c.hint is not None and c.matches("", hint) or
                   (c.hint is not None and _hint_only(c, hint))
                   for c in C.CURES), hint


def _hint_only(cure, hint):
    if hasattr(cure.hint, "search"):
        return bool(cure.hint.search(hint))
    return cure.hint == hint


def test_no_two_cure_rules_claim_the_same_hint():
    """`classify` must not depend on `CURES`' source order.

    Three rules share a body pattern (`two statements on one line` is both
    the separator cure and the juxtaposition one; `expected X, got Y` is
    both the braced-block cure and the juxtaposition one), so the hint is
    what tells them apart. If two rules ever accept the same hint, whichever
    is listed first silently wins and the classification becomes a fact
    about this file's line order.
    """
    hints = ([P._BRACE_HINT, P._RECORD_HINT, P._JUXTAPOSE_HINT,
              P._SEPARATOR_HINT % "x", "every expression has a value"]
             + list(P._SYNTAX_HINTS.values())
             + list(FOREIGN_NAMES.values()))
    for hint in hints:
        owners = [c.key for c in C.CURES if _hint_only(c, hint)]
        assert len(owners) == 1, (hint, owners)


def test_a_cure_is_mechanical_exactly_when_it_can_be_applied():
    """The taxonomy's invariant, enforced by `Cure.__init__` and pinned here
    so that loosening the constructor cannot pass unnoticed."""
    for c in C.CURES:
        assert (c.determinacy == C.MECHANICAL) == (c._applier is not None)
        assert (c.determinacy in (C.UNDER_EXTENT, C.UNDER_CHOICE,
                                  C.UNDER_CONTENT)) == (c.missing is not None)
        assert c.derivation, c.key


def test_an_unknown_hint_is_unclassified_and_not_no_cure():
    """The distinction that keeps a stale table from reading as a finding."""
    assert C.determinacy_of(None, None) == C.NO_CURE
    assert C.determinacy_of(None, "some hint nobody wrote") == C.UNCLASSIFIED


def test_split_message_reads_only_what_a_reader_sees():
    body, hint, line, col = C.split_message(
        "unexpected ':' (records are written `@{a: 1}`, not `{a: 1}`) "
        "at line 14, col 10")
    assert body == "unexpected ':'"
    assert hint == "records are written `@{a: 1}`, not `{a: 1}`"
    assert (line, col) == (14, 10)
    # a message with no parenthetical
    body, hint, line, col = C.split_message("block must end with an "
                                            "expression at line 32, col 5")
    assert hint is None and (line, col) == (32, 5)


# --------------------------------------------------------------------------
# 2. behaviour --- synthetic programs only
# --------------------------------------------------------------------------

FOREIGN_PARSE_CASES = [
    ('let c = 1\nif c == 1 then\n    2\nelse\n    3\n',
     "an `if` needs no `then`"),
    ('let xs = [1]\nfn f(a) {\n    for d in xs {\n        d\n    }\n}\nf(1)\n',
     "Whence has no loops"),
    ('fn f(x) {\n    return x\n}\nf(1)\n',
     "Whence has no `return`"),
    ('let r = 1\ncatch Miss as e\nr\n',
     "Whence has no `catch`"),
]


@pytest.mark.parametrize("src,expect", FOREIGN_PARSE_CASES)
def test_a_parse_error_names_the_foreign_word(src, expect):
    got = err(src)
    assert got is not None and expect in got, got


def test_the_clause_is_silent_about_a_name_the_file_binds():
    """`meta.lang` and `self_eval.lang` both write `let then = ...`, because
    an interpreter written in Whence names an if-node's then-branch `then`.
    Measured, not imagined: that is why `bound_anywhere` exists."""
    src = 'let then = 1\nfn f(x) {\n    if x == 1 then\n        2\n    else\n        3\n}\nf(1)\n'
    got = err(src)
    assert got is not None
    assert "an `if` needs no `then`" not in got
    assert P._BRACE_HINT in got          # falls back, does not go silent


def test_bound_anywhere_finds_lets_fn_heads_and_parameters():
    toks = tokenize("let a = 1\nfn g(b, c) { b }\nlet d = fn(e) { e }\ng(1, 2)\n")
    assert {"a", "g", "b", "c", "d", "e"} <= bound_anywhere(toks)


def test_a_foreign_word_does_not_shadow_the_juxtaposition_hint():
    """Round 386's own regression, pinned.

    `safe_divide one_hundred, ...` is a paren-less call --- round 354's
    tenth case. `one_hundred` is in the table, and an earlier draft of
    `_foreign_hint` tried the offending token as well as its predecessor,
    so the spelled-out-number sentence displaced the one message that
    describes the actual parse mistake. A foreign word explains an error
    when it is what put two names next to each other, not when it merely
    happens to be one of them.
    """
    src = "fn f(a, b) { a }\nlet r = f one_hundred, 2\nr\n"
    got = err(src)
    assert got is not None
    assert P._JUXTAPOSE_HINT in got, got
    assert "spelled-out numbers" not in got, got
    # ...and the same word FIRST does draw the clause
    src2 = "let xs = [1]\nfn g(a) {\n    for d in xs {\n        d\n    }\n}\ng(1)\n"
    assert "Whence has no loops" in err(src2)


def test_the_entry_rule_still_holds_for_the_two_names_v033_added():
    census = json.load(open(CENSUS, encoding="utf-8"))
    counts = census["unbound_identifier_counts"]
    for name, n in (("zero_point_zero", 11), ("one_hundred", 2)):
        assert name in FOREIGN_NAMES
        assert counts[name] == n, (name, counts.get(name))
    # and the rule still bites --- an unattested foreign-looking name stays out
    for name in ("printf", "lambda", "two_point_five", "elif"):
        assert name not in FOREIGN_NAMES, name


def test_every_sentence_names_a_whence_spelling():
    for name, sentence in FOREIGN_NAMES.items():
        assert "`" in sentence, name
    assert name_hint("println").startswith(" (")
    assert name_hint("no_such_name_anywhere") == ""


# --------------------------------------------------------------------------
# 2b. `miss <bare name>` --- round 384's next-step 1
# --------------------------------------------------------------------------

def run_src(src):
    import whence.interp as I
    out = []
    interp = I.Interpreter(out=out.append)
    interp.run(src)
    return interp, out


def test_miss_with_an_unbound_name_names_decision_41s_cure():
    interp, out = run_src('fn f() { miss DEPT_NOT_APPROVED }\n'
                          'let r = f()\nprint(str(r))\nr\n')
    text = "\n".join(out)
    assert "DEPT_NOT_APPROVED" in text
    assert (MISS_REASON_HINT % "DEPT_NOT_APPROVED") in text, text


def test_miss_with_a_bound_name_is_untouched():
    """`miss reason` over a bound string is the idiomatic spelling and the
    TRACKED corpus uses it 14 times (`self_eval.lang`, `self_host.lang`).
    The clause must fire on an unbound name and on nothing else."""
    interp, out = run_src('let reason = "nope"\n'
                          'fn f() { miss reason }\n'
                          'let r = f()\nprint(str(r))\nr\n')
    text = "\n".join(out)
    assert "nope" in text
    assert "a miss reason is a string" not in text, text


def test_the_miss_position_clause_beats_the_foreign_one():
    """`miss null` would otherwise read "Whence has no null; a missing value
    is `miss <reason>`" --- advice to write what the author is writing.
    Position is the more specific fact. Chosen for a corner nothing in the
    corpus attests, so it is pinned rather than left to be rediscovered."""
    interp, out = run_src('fn f() { miss null }\nlet r = f()\n'
                          'print(str(r))\nr\n')
    text = "\n".join(out)
    assert (MISS_REASON_HINT % "null") in text, text
    assert "Whence has no null" not in text, text


def test_there_is_still_one_unbound_name_literal():
    """Round 380 collapsed three copies of `unbound name '%s'` into
    `_unbound`; v0.33 adds a second CALLER (`_miss_lit`) and a second caller
    is how three copies start. `_unbound_text` is the single spelling."""
    src = open(os.path.join(ROOT, "whence", "interp.py"),
               encoding="utf-8").read()
    assert src.count('"unbound name \'%s\'') == 1, src.count(
        '"unbound name \'%s\'')


# --------------------------------------------------------------------------
# 3. the corpus measurement --- pinned behind the frozen md5 census
# --------------------------------------------------------------------------

def _corpus_unchanged():
    """True when every field program still hashes to round 384's census.

    The field corpus is written by the Hermes gateway, a separate
    autonomous system that shares this repo, and it has rewritten files
    before. A corpus-derived number is not a regression when the corpus
    moves --- it is new information --- so these tests SKIP rather than
    fail, and say which file moved.
    """
    census = json.load(open(CENSUS, encoding="utf-8"))
    for name, want in census["file_md5"].items():
        path = os.path.join(EXAMPLES, os.path.basename(name))
        if not os.path.exists(path):
            return "missing: %s" % name
        got = hashlib.md5(open(path, "rb").read()).hexdigest()
        if got != want:
            return "changed: %s" % name
    return None


corpus_pin = pytest.mark.skipif(_corpus_unchanged() is not None,
                                reason="field corpus moved: %s"
                                       % _corpus_unchanged())


@corpus_pin
def test_ten_field_programs_still_fail_to_parse():
    fail = [os.path.basename(p) for p in C.field_programs()
            if C.parse_error_of(open(p).read()) is not None]
    assert len(fail) == 10, fail


@corpus_pin
def test_following_the_cures_mechanically_fixes_none_of_them():
    """Round 386's headline. Of ten programs whose first error names a cure,
    a reader who does exactly what the message says fixes ZERO --- eight
    stall on the first error, and the two that move stall on the second."""
    rows = C.survey([p for p in C.field_programs()])
    broken = [r for r in rows if not r["parses"]]
    assert len(broken) == 10
    assert all(r["outcome"] == "stalled" for r in broken), \
        [(r["file"], r["outcome"]) for r in broken]
    assert sum(r["applied"] for r in broken) == 3
    stalled_on_first = [r for r in broken if r["applied"] == 0]
    assert len(stalled_on_first) == 8


@corpus_pin
def test_the_ledger_still_replays_and_every_program_reaches_a_value():
    """The assisted half, kept re-derivable rather than anecdotal."""
    with open(LEDGER) as fh:
        ledger = json.load(fh)
    rows = C.replay(ledger)
    assert len(rows) == 10
    assert all(r["final_error"] is None for r in rows), \
        [(r["file"], r["final_error"]) for r in rows]
    assert all(r["rc"] == 0 for r in rows)
    # ...and reaching a value is NOT the same as working: eight of the ten
    # drop a miss, so `--strict-miss` fails them.
    assert sum(1 for r in rows if r["strict_rc"] == 0) == 2


@corpus_pin
def test_seven_edits_fix_text_the_grammar_accepts():
    """The mistakes no message was ever available for. All seven are in
    `whenceguard_v2.lang`, and all seven are the same class as the one the
    parser DOES report there --- unquoted text --- which is why the first
    parse error in that file is its third mistake."""
    with open(LEDGER) as fh:
        rows = C.replay(json.load(fh))
    by_file = dict((r["file"], r["n_accepted"]) for r in rows)
    assert sum(by_file.values()) == 7, by_file
    assert by_file["whenceguard_v2.lang"] == 7, by_file

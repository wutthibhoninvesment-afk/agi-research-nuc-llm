"""v0.41 (round 422, language C) — one quoting rule, not two.

Round 408's item 6 asked for `whence/parser.py:quote_str` to be unified with
`whence/values.py:_quote`. It was carried FIVE rounds, and the reason it was
carried is written in the docstring the round-408 author left behind:

    The two are not shared because `values._quote` also truncates to a
    `limit` and does not escape `\\t`/`\\r`, both of which are wrong for a
    diagnostic that is telling an author what they typed.

Two obstacles, and only one of them was an obstacle. `limit` is an argument.
The escape SET was a divergence — the runtime copy rendered a string holding
a tab as a literal no Whence program can contain, which is precisely the rule
decision 48 wrote for the parser's half and never applied to the runtime's.

So the round-408 item was never a refactor: it was a latent bug wearing a
refactor's clothes, and four rounds read the docstring, believed the second
half, and moved on. That is the round-421 shape (`named-is-not-invoked`) in a
different register — a claim stated in a comment, carried because nobody
asked the claim's own question of the code.

These tests pin BOTH halves: the behaviour, and the fact that there is one
implementation of it.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from whence import values as V                                  # noqa: E402
from whence import parser as P                                  # noqa: E402
from whence.interp import Interpreter                           # noqa: E402
from whence.lexer import tokenize                               # noqa: E402


def test_the_parser_and_the_runtime_are_the_same_function():
    """Not "they agree" — the same object. An equality test over samples is
    what let the two drift for five rounds while agreeing on every sample
    anybody happened to write."""
    assert P.quote_str is V.quote_str


def test_the_parser_module_no_longer_owns_an_escape_table():
    assert not hasattr(P, "_QUOTE_ESCAPES")
    assert V.QUOTE_ESCAPES[0] == ("\\", "\\\\"), "backslash must go first"


@pytest.mark.parametrize("raw,spelled", [
    ("plain", '"plain"'),
    ('say "hi"', '"say \\"hi\\""'),
    ("back\\slash", '"back\\\\slash"'),
    ("a\nb", '"a\\nb"'),
    ("a\tb", '"a\\tb"'),
    ("a\rb", '"a\\rb"'),
])
def test_every_special_character_is_escaped_by_both_names(raw, spelled):
    assert V.quote_str(raw) == spelled
    assert P.quote_str(raw) == spelled


@pytest.mark.parametrize("raw", ["a\tb", "a\rb", "a\nb", 'q"q', "b\\b"])
def test_the_runtime_snapshot_of_a_string_re_lexes_to_itself(raw):
    """The regression the unification fixed. `show_payload` is what `print`,
    `why` and a failing `check` render through, and before this version its
    output for a string holding a TAB was `"a<tab>b"` — text the lexer
    refuses to read back as one token."""
    spelled = V.show_payload(raw)
    toks = [t for t in tokenize(spelled) if t.type not in ("EOF", "NEWLINE")]
    assert len(toks) == 1 and toks[0].type == "STRING"
    assert toks[0].value == raw


def test_the_limit_still_truncates_and_still_only_for_the_runtime():
    long = "x" * 200
    assert V.quote_str(long, limit=10) == '"' + "x" * 10 + '…"'
    # the parse-diagnostic path must never truncate: a hint that tells an
    # author to type `…` cannot be followed.
    assert V.quote_str(long) == '"' + long + '"'


def test_truncation_cannot_cut_an_escape_in_half():
    """`limit` is applied to the ESCAPED text, so the cut can land between a
    backslash and its letter. It does not produce a re-lexable literal — the
    trailing `…` already means "abridged" — but it must not raise, and the
    two callers must agree on where the cut is."""
    s = "a" + "\t" * 50
    out = V.quote_str(s, limit=6)
    assert out.startswith('"a\\t') and out.endswith('…"')
    assert V.show_payload(s, limit=6) == out


def test_a_tab_inside_a_string_prints_as_an_escape_end_to_end():
    it = Interpreter(out=lambda *a, **k: None, direct=True, seed=0)
    it.run('check "tab": true\n')
    out = []
    it2 = Interpreter(out=lambda s: out.append(s), direct=True, seed=0)
    it2.run('print("a\\tb")\n')
    # `print` of a string prints the VALUE, not the snapshot; the snapshot is
    # what a failing check reports. Both are pinned, because the round-408
    # docstring's claim was about the snapshot and the confusion is easy.
    assert out == ["a\tb"]
    it3 = Interpreter(out=lambda *a, **k: None, direct=True, seed=0)
    it3.run('check "sees the tab": "a\\tb" == "nope"\n')
    rec = it3.checks[-1]
    assert not rec["ok"]
    assert "\\t" in rec["why"] and "\t" not in rec["why"]

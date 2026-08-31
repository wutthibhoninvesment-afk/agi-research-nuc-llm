"""v0.40 (round 410), decision 49 --- two doors, one rule for numeric text.

Round 368 gave `num()` a refusal past `SHOW_INT_DIGITS` and wrote the reason
into `whence/values.py` as a claim about the LANGUAGE:

    `num()` refuses numeric TEXT past the same boundary, so the two stay
    inverses: Whence never accepts digits it could not print back.

Round 408 measured that sentence against the other door --- a SOURCE
LITERAL --- and found it false there: `whence/lexer.py` accepted an integer
literal of any length. The consequence was visible as a host/guest
divergence, because the guest lexer's `lit_num` IS `num(text)`, so the guest
refused what the host accepted; round 408 recorded it as
`bench/showtok.py:KNOWN_DIVERGENT` and deferred the fix, correctly, on the
grounds that closing it is a decision about what the language ACCEPTS.

DECISION 49. Both doors for numeric text enforce the same bound, in the
phase each belongs to:

    source literal  `let a = <4001 nines>`   -> LexError, at lex time
    runtime call    `num("<4001 nines>")`    -> Miss,     at run time

with ONE sentence, `values.NUM_TEXT_LIMIT_MSG`, so neither door can reword
the rule alone.

WHAT IS PINNED HERE, and the four kinds are not the same claim:

  1. THE BOUNDARY (section 1). Both doors, both sides of 4000, and the
     position and phase of each refusal.
  2. THE SCOPE (section 2). The rule is about INTEGER text. A float literal
     still overflows to `inf` and is not refused, because a float has no
     digits to print back --- and without a test saying so the corpus reads
     as if "long numeric literal" were the rule.
  3. THE STRUCTURE (section 3). One sentence, one constant, no copy of the
     wording in either door.
  4. THE RESIDUAL (section 4), which is the part worth reading. Decision 49
     makes the two DOORS agree. It does NOT make round 368's sentence true,
     and this file measures exactly how far off it still is rather than
     repeating the sentence.
"""

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from whence import values                                    # noqa: E402
from whence.interp import Interpreter                         # noqa: E402
from whence.lexer import LexError, tokenize                   # noqa: E402
from whence.values import (Miss, NUM_TEXT_LIMIT_MSG,          # noqa: E402
                           SHOW_INT_BITS, SHOW_INT_DIGITS, show_int)

CAP = SHOW_INT_DIGITS


def _num_miss(text):
    env = Interpreter(out=lambda s: None).run('let a = num("%s")\n' % text)
    return env.get("a").payload


# --------------------------------------------------------------------------
# 1. the boundary --- both doors, both sides
# --------------------------------------------------------------------------

def test_the_literal_door_accepts_exactly_up_to_the_cap():
    toks = tokenize("let a = %s" % ("9" * CAP))
    nums = [t for t in toks if t.type == "NUMBER"]
    assert len(nums) == 1 and isinstance(nums[0].value, int)
    assert len(str(nums[0].value)) == CAP


def test_the_literal_door_refuses_one_digit_past_the_cap():
    with pytest.raises(LexError) as exc:
        tokenize("let a = %s" % ("9" * (CAP + 1)))
    assert str(exc.value) == "%s at line 1, col 9" % (
        NUM_TEXT_LIMIT_MSG % (CAP + 1, CAP))


def test_the_runtime_door_still_draws_the_line_in_the_same_place():
    assert not isinstance(_num_miss("9" * CAP), Miss)
    m = _num_miss("9" * (CAP + 1))
    assert isinstance(m, Miss)
    assert m.reasons == ("num: %s (line 1)"
                         % (NUM_TEXT_LIMIT_MSG % (CAP + 1, CAP)),)


def test_the_refusal_names_the_start_of_the_literal_not_where_it_stopped():
    """A cure you can act on points at the token, not at the scan's end. The
    literal begins at column 9 of `let a = ...`; the scanner stops 4001
    characters later, and reporting THAT column would put the caret in a
    different statement on a long line."""
    with pytest.raises(LexError) as exc:
        tokenize("let a = %s\n" % ("9" * (CAP + 1)))
    assert (exc.value.line, exc.value.col) == (1, 9)


def test_the_two_doors_refuse_in_the_phase_each_belongs_to():
    """Same rule, different KIND of failure, and that is not an
    inconsistency. A literal is program TEXT: refusing it is a static error,
    the same class as `bad escape`, and rule 2's "no exceptions" is about
    VALUES, not about whether a source file is a program. `num(s)` is a call
    on a runtime string that may have been read from anywhere, so its
    refusal has to be a value --- a Miss that carries its provenance."""
    with pytest.raises(LexError):
        tokenize("let a = %s" % ("9" * (CAP + 1)))
    # the runtime door produces a VALUE, and the program keeps running
    env = Interpreter(out=lambda s: None).run(
        'let a = num("%s")\nlet b = 1 + 1\n' % ("9" * (CAP + 1)))
    assert isinstance(env.get("a").payload, Miss)
    assert env.get("b").payload == 2


def test_a_refused_literal_reaches_the_user_as_a_lex_error(tmp_path):
    """End to end through `run.py`, because v0.21 (round 350) found that
    `LexError` was not in its `except` tuple and every lex error was a raw
    host traceback. A new `raise LexError` site is exactly the change that
    would re-expose that if the tuple ever narrowed."""
    prog = tmp_path / "big.lang"
    prog.write_text("let a = %s\nprint(a)\n" % ("9" * (CAP + 1)))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"),
                        str(prog)], capture_output=True, text=True,
                       timeout=120)
    out = r.stdout + r.stderr
    assert "Traceback" not in out, out[-800:]
    assert "digits is over the" in out, out[-800:]
    assert r.returncode != 0


# --------------------------------------------------------------------------
# 2. the scope --- INTEGER text, and the cases the rule does not reach
# --------------------------------------------------------------------------

@pytest.mark.parametrize("src,label", [
    ("let a = 1e400", "exponent overflow"),
    ("let a = %s.5" % ("9" * (CAP + 1)), "long mantissa with a fraction"),
    ("let a = 1e%d" % (CAP + 1), "a huge exponent, few digits of mantissa"),
])
def test_a_float_literal_is_not_refused_however_long_or_large(src, label):
    """The rule is a ROUND-TRIP rule about digits, and a float has none to
    round-trip: `inf` is a value Whence can print, and the language has
    accepted an overflowing float literal as `inf` since round 323 with a
    test pinning it (`test_lexer.py::test_exponent_overflow_becomes_inf_not_
    a_lex_error`). Refusing these would be a different decision, about
    RANGE, and decision 49 does not make it."""
    toks = tokenize(src)
    nums = [t.value for t in toks if t.type == "NUMBER"]
    assert len(nums) == 1 and isinstance(nums[0], float), (label, nums)


def test_the_runtime_door_still_treats_float_range_as_its_own_rule():
    """`num("1e400")` is an "out of range" MISS while the literal `1e400` is
    `inf`. The two doors do NOT agree here and are not being made to: this
    is round 350's finding, deliberate, and the guest's `lit_num` exists to
    paper over exactly it (`pos_inf` for a miss). Decision 49 changes the
    INTEGER half and leaves this alone --- pinned so that a later round
    that unifies them knows it is changing something, not fixing an
    oversight."""
    m = _num_miss("1e400")
    assert isinstance(m, Miss) and "out of range" in m.reasons[0]
    assert tokenize("let a = 1e400")[3].value == float("inf")


def test_a_negative_literal_is_two_tokens_so_the_sign_never_counts():
    """`-<4000 nines>` is the operator `-` then the literal, so the digit
    count the lexer sees never includes a sign --- which is why the host's
    check is `len(text)` while `b_num`'s is `len(t.lstrip("+-"))`. They
    agree on every input either can see."""
    toks = tokenize("let a = -%s" % ("9" * CAP))
    kinds = [t.type for t in toks]
    assert "-" in kinds
    assert len([t for t in toks if t.type == "NUMBER"]) == 1
    with pytest.raises(LexError):
        tokenize("let a = -%s" % ("9" * (CAP + 1)))
    assert not isinstance(_num_miss("-" + "9" * CAP), Miss)


# --------------------------------------------------------------------------
# 3. the structure --- one sentence, one constant
# --------------------------------------------------------------------------

def test_neither_door_carries_a_copy_of_the_wording():
    """The anti-rot rule `curecheck.py`'s header states for parser hints,
    applied to the one sentence two modules now say: key on the constant,
    never on a copy of its wording."""
    marker = "-digit limit for numeric text"
    homes = []
    for rel in ("whence/values.py", "whence/lexer.py", "whence/interp.py",
                "whence/parser.py"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        if marker in src:
            homes.append(rel)
    assert homes == ["whence/values.py"], homes


def test_the_guest_spells_the_bound_and_the_host_is_the_authority():
    """The guest is a separate implementation and MUST carry a copy --- it
    cannot import a Python constant. What it must not carry is a DIFFERENT
    number, and `tests/test_lexer_guest_parity.py` is what compares the
    sentences; this only pins that the guest's constant is the host's."""
    for name in ("self_host.lang", "self_eval.lang"):
        src = open(os.path.join(ROOT, "examples", name),
                   encoding="utf-8").read()
        assert "let num_text_digit_limit = %d" % CAP in src, name
        assert "-digit limit for numeric text" in src, name


def test_the_bound_is_the_same_number_at_both_doors():
    """Not `4000 == 4000` --- the two doors read the SAME name. If a round
    moves `SHOW_INT_DIGITS`, both move, and this test moves with them."""
    ok = "9" * CAP
    over = "9" * (CAP + 1)
    assert not isinstance(_num_miss(ok), Miss)
    assert isinstance(_num_miss(over), Miss)
    tokenize("let a = %s" % ok)
    with pytest.raises(LexError):
        tokenize("let a = %s" % over)


# --------------------------------------------------------------------------
# 4. the residual --- what decision 49 does NOT make true
# --------------------------------------------------------------------------

def test_the_round_trip_wording_is_still_not_the_rule_at_either_door():
    """THE FINDING, and the reason section 4 exists.

    Round 368's sentence is "Whence never accepts digits it could not print
    back". Decision 49 makes the two DOORS agree with each other. It does
    not make that sentence true, and it could not have: the ACCEPTANCE bound
    is on decimal DIGITS of text (`SHOW_INT_DIGITS`, 4000) and the PRINTING
    bound is on BITS (`SHOW_INT_BITS`, 13287), and 13287 bits is at most
    3999.8 decimal digits. So every accepted integer with 4000 digits and a
    bit length past the cut is accepted and prints as a SUMMARY.

    The witness is `9 * 4000`, which the lexer now accepts and `show_int`
    summarises. That is 43.3% of the 4000-digit integers.

    Three ways to make the sentence true and the reason none was taken:

      * bound acceptance on BITS. The message stops being followable --- an
        author can count digits in their own source and cannot count bits,
        and decision 32 says an error that can name the fix names it.
      * move `SHOW_INT_DIGITS` to 3999. The sentence becomes true and
        `parser._show`'s summarising branch --- decision 48, round 408 ---
        becomes unreachable from any source file, since no accepted literal
        would summarise. A rule whose only remaining witness is a unit test
        on a constructed value is weaker than the residual.
      * reword the claim in `whence/values.py` so it stops asserting a
        property the code does not have. TAKEN, and this test is what stops
        it drifting back.
    """
    witness = int("9" * CAP)
    assert len(str(witness)) == CAP
    assert witness.bit_length() > SHOW_INT_BITS
    tokenize("let a = %s" % ("9" * CAP))            # accepted...
    assert show_int(witness) == "<integer, %d bits>" % witness.bit_length()
    assert str(witness) not in show_int(witness)    # ...and not printed back

    # ...and the wording no longer CLAIMS otherwise. Not "the sentence is
    # gone" --- the correction has to quote what it corrects, and a first
    # draft of this assertion was failed by the retraction it asked for.
    # The sentence survives exactly once, inside the paragraph that retracts
    # it, which is checkable: the retraction must come first.
    src = open(os.path.join(ROOT, "whence", "values.py"),
               encoding="utf-8").read()
    claim = "never accepts digits it could not print back"
    assert src.count(claim) == 1, src.count(claim)
    assert src.index("This comment used to end") < src.index(claim)
    assert "deliberately does NOT make true" in src
    assert "Whence accepts at most SHOW_INT_DIGITS digits" in src


def test_the_summarising_branch_is_still_reachable_from_source():
    """The cost of keeping `SHOW_INT_DIGITS` at 4000, measured. Every
    integer literal a source file can now carry that reaches
    `show_int`'s summary has EXACTLY ONE bit length --- the window is
    `[2 ** SHOW_INT_BITS, 10 ** SHOW_INT_DIGITS - 1]` and both ends are
    13288 bits. If a later round narrows the acceptance bound by one digit
    this test goes red, which is the point: it would be deleting the last
    source-reachable witness for decision 48."""
    lo = 1 << SHOW_INT_BITS
    hi = 10 ** SHOW_INT_DIGITS - 1
    assert lo < hi
    assert lo.bit_length() == hi.bit_length() == 13288
    assert len(str(lo)) == len(str(hi)) == SHOW_INT_DIGITS
    for n in (lo, hi):
        toks = tokenize("let a = %d" % n)
        assert [t.value for t in toks if t.type == "NUMBER"] == [n]
        assert show_int(n) == "<integer, 13288 bits>"
    # one below the window prints in full and is also accepted
    below = lo - 1
    assert below.bit_length() == SHOW_INT_BITS
    assert show_int(below) == str(below)


def test_the_two_constants_are_still_ordered_the_way_the_cap_needs():
    """`SHOW_INT_BITS` exists to keep Whence's cap strictly BELOW CPython's
    4300-digit `int.__str__` limit, so the host limit is never reached.
    Decision 49 puts a THIRD bound in the same neighbourhood --- acceptance
    --- and the three must stay ordered, or `int(text)` in the lexer becomes
    the `ValueError` traceback `b_num` is careful to avoid."""
    assert (1 << SHOW_INT_BITS).bit_length() - 1 == SHOW_INT_BITS
    assert len(str(2 ** SHOW_INT_BITS - 1)) <= SHOW_INT_DIGITS
    assert SHOW_INT_DIGITS < sys.get_int_max_str_digits()
    # the lexer converts with `int(text)` AFTER the bound, so the longest
    # text it ever converts is `SHOW_INT_DIGITS` long and cannot raise.
    assert int("9" * SHOW_INT_DIGITS) == 10 ** SHOW_INT_DIGITS - 1


def test_the_language_accepts_no_integer_text_it_cannot_bound(  ):
    """The property that IS true after decision 49, stated as the code has
    it rather than as round 368 wished it: for numeric integer text, the two
    doors accept the same set, and that set is bounded. Checked over the
    boundary rather than asserted."""
    for d in (1, 2, 17, 100, 3999, CAP, CAP + 1, CAP + 2, CAP + 500):
        text = "9" * d
        lexed_ok = True
        try:
            tokenize("let a = %s" % text)
        except LexError:
            lexed_ok = False
        num_ok = not isinstance(_num_miss(text), Miss)
        assert lexed_ok == num_ok == (d <= CAP), (d, lexed_ok, num_ok)

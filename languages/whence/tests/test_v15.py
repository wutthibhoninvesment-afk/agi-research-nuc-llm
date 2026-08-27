"""v0.15 (round 168): `guess` — an uncertainty-carrying value, the last of
the curriculum's three "advanced feature" slots (structural types v0.12,
return types v0.13, effects v0.14). Symmetric to `miss` (values.py): where
a `miss` is "no answer, and here is why," a `guess` is "an answer, but
here is how sure" — the shape of an LLM's own output. See SPEC.md's
"v0.15" section for the full design rationale.

Design anchors this file pins:
  - `guess(value, confidence, source)` / `is_guess` / `confidence` /
    `sure(v, threshold)` (interp.py builtin table).
  - Arithmetic/unary ops propagate a Guess operand automatically
    (`Interpreter._guess_binop`/`_unary`) at the WEAKEST-LINK (min, not
    averaged) confidence of every Guess operand, sources unioned.
  - A genuine type error under the unwrapped operands stays an ordinary
    miss, never becomes a "low-confidence success"
    (`test_type_error_under_guess_stays_a_miss`).
  - `==`/`!=` on a BARE guess go through `_guess_binop` (result is itself
    a guess about the comparison) — deliberately different from a guess
    INSIDE a container, which reaches `deep_eq`'s new Guess-vs-Guess case
    (compares the underlying answer only, ignores confidence). Both
    directions are pinned explicitly below.
  - Deliberately shallow, same discipline as v0.12-14: indexing, field
    access, and call dispatch do not know about Guess at all — they
    already produce a correct "cannot index/access/call" miss via
    `show_payload`'s new Guess case, with zero code added to those paths.
  - `and`/`or`/`if` are equally untouched: a Guess is not a `bool`, so the
    existing "needs true/false" misses fire unmodified.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_v09 import run, val, assert_three_way  # noqa: E402

from whence.values import Miss, Guess  # noqa: E402


def all_ok(src, **kw):
    interp, env, out = run(src, **kw)
    bad = [c for c in interp.checks if not c["ok"]]
    assert bad == [], (bad, out)
    assert interp.checks, "no checks ran"
    return interp, env, out


# --- construction / introspection -------------------------------------------

def test_guess_wraps_a_value():
    v = val('let result = guess(10, 0.9, "model")\n')
    assert isinstance(v.value, Guess)
    assert v.value.confidence == 0.9
    assert v.value.sources == ("model",)
    assert v.value.node.value == 10


def test_is_guess_distinguishes_guess_from_plain():
    assert val('let result = is_guess(guess(1, 0.5, "m"))\n').value is True
    assert val('let result = is_guess(1)\n').value is False


def test_is_guess_is_total_even_on_a_miss():
    assert val('let result = is_guess(1 / 0)\n').value is False


def test_confidence_reads_the_score():
    assert val('let result = confidence(guess(1, 0.42, "m"))\n').value == 0.42


def test_confidence_of_a_plain_value_is_a_miss():
    v = val('let result = confidence(5)\n')
    assert isinstance(v.value, Miss)
    assert "not a guess" in v.value.reasons[0]


def test_shapeof_names_it_guess():
    assert val('let result = shapeof(guess(1, 0.5, "m"))\n').value == "guess"


# --- validation: total, never a host crash ----------------------------------

def test_guess_confidence_out_of_range_is_a_miss():
    v = val('let result = guess(1, 1.5, "m")\n')
    assert isinstance(v.value, Miss)
    assert "between 0 and 1" in v.value.reasons[0]


def test_guess_confidence_negative_is_a_miss():
    v = val('let result = guess(1, -0.1, "m")\n')
    assert isinstance(v.value, Miss)


def test_guess_non_numeric_confidence_is_a_miss():
    v = val('let result = guess(1, "high", "m")\n')
    assert isinstance(v.value, Miss)


def test_guess_non_string_source_is_a_miss():
    v = val('let result = guess(1, 0.9, 42)\n')
    assert isinstance(v.value, Miss)


def test_guess_of_a_miss_value_propagates_the_miss():
    v = val('let result = guess(1 / 0, 0.9, "m")\n')
    assert isinstance(v.value, Miss)
    assert not isinstance(v.value, Guess)


# --- nesting flattens, does not tower ---------------------------------------

def test_nested_guess_flattens():
    v = val('let result = guess(guess(7, 0.8, "a"), 0.5, "b")\n')
    assert isinstance(v.value, Guess)
    assert not isinstance(v.value.node.value, Guess)
    assert v.value.node.value == 7
    assert v.value.confidence == 0.5              # min(0.8, 0.5)
    assert v.value.sources == ("a", "b")


# --- arithmetic propagation: weakest-link confidence ------------------------

def test_arithmetic_on_a_guess_yields_a_guess():
    v = val('let result = guess(10, 0.9, "m") + 5\n')
    assert isinstance(v.value, Guess)
    assert v.value.node.value == 15
    assert v.value.confidence == 0.9


def test_combining_two_guesses_takes_the_minimum_confidence():
    v = val('let result = guess(10, 0.9, "a") + guess(4, 0.6, "b")\n')
    assert v.value.confidence == 0.6
    assert v.value.node.value == 14
    assert v.value.sources == ("a", "b")


def test_confidence_does_not_decay_with_chain_length():
    """Five 0.9-confidence terms stay at 0.9 (min), not 0.9**5 (product)
    or an average — the whole point of weakest-link semantics."""
    v = val('let g = guess(10, 0.9, "m")\nlet result = g + g + g + g + g\n')
    assert v.value.confidence == 0.9
    assert v.value.node.value == 50


def test_unary_negation_propagates():
    v = val('let result = -guess(5, 0.7, "m")\n')
    assert isinstance(v.value, Guess)
    assert v.value.node.value == -5
    assert v.value.confidence == 0.7


def test_not_propagates():
    v = val('let result = not guess(true, 0.7, "m")\n')
    assert isinstance(v.value, Guess)
    assert v.value.node.value is False
    assert v.value.confidence == 0.7


def test_type_error_under_guess_stays_a_miss():
    """A confidence score vouches for an otherwise-VALID computation; it
    cannot launder an invalid one into a low-confidence success."""
    v = val('let result = guess("x", 0.9, "m") + 5\n')
    assert isinstance(v.value, Miss)
    assert not isinstance(v.value, Guess)
    assert "cannot add" in v.value.reasons[0]


def test_type_error_in_unary_stays_a_miss():
    v = val('let result = not guess(5, 0.9, "m")\n')
    assert isinstance(v.value, Miss)


# --- equality: bare guess vs. guess-inside-a-container ----------------------

def test_bare_equality_against_a_guess_yields_a_guess():
    """Deliberately different from `deep_eq`: comparing directly against
    an uncertain value makes the comparison itself uncertain."""
    v = val('let result = (1 == guess(1, 0.8, "m"))\n')
    assert isinstance(v.value, Guess)
    assert v.value.node.value is True
    assert v.value.confidence == 0.8


def test_bare_inequality_against_a_guess_yields_a_guess():
    v = val('let result = (guess(1, 0.8, "m") != 2)\n')
    assert isinstance(v.value, Guess)
    assert v.value.node.value is True


def test_two_guesses_inside_lists_compare_by_answer_not_confidence():
    """`contains`/`find`/structural `==` on a CONTAINER of guesses reaches
    `deep_eq`, which ignores confidence/source entirely — a different,
    deliberate rule from the bare-value case above."""
    v = val('let result = [guess(1, 0.9, "a")] == [guess(1, 0.1, "b")]\n')
    assert v.value is True


def test_guesses_inside_lists_still_compare_the_underlying_value():
    v = val('let result = [guess(1, 0.9, "a")] == [guess(2, 0.9, "a")]\n')
    assert v.value is False


def test_contains_finds_a_matching_guess_by_answer():
    all_ok('let xs = [guess(1, 0.9, "a"), 2]\n'
          'check "ok": contains(xs, guess(1, 0.1, "irrelevant"))\n')


# --- `sure`: the one way out -------------------------------------------------

def test_sure_above_threshold_passes_through_unchanged():
    v = val('let g = guess(10, 0.9, "m")\nlet result = sure(g, 0.5)\n')
    assert v.value == 10
    assert not isinstance(v.value, Guess)


def test_sure_returns_the_original_node_no_new_step():
    """Pass-through means literally the same node `guess()` wrapped, same
    convention as a passing `typed` check adding no new provenance step —
    `let result = sure(...)` always wraps its own "let" node (every `let`
    does), but that node's ONE input must be the pre-existing "let ten"
    node directly, with no intervening "sure" step."""
    interp, env, out = run(
        'let ten = 10\nlet g = guess(ten, 0.9, "m")\nlet result = sure(g, 0.5)\n')
    assert env.get("result").inputs[0] is env.get("ten")


def test_sure_below_threshold_is_a_miss_naming_the_shortfall():
    v = val('let result = sure(guess(10, 0.9, "m"), 0.95)\n')
    assert isinstance(v.value, Miss)
    assert "0.9" in v.value.reasons[0] and "0.95" in v.value.reasons[0]
    assert "m" in v.value.reasons[0]


def test_sure_on_a_plain_value_is_a_no_op():
    assert val('let result = sure(42, 0.99)\n').value == 42


def test_sure_bad_threshold_is_a_miss():
    v = val('let result = sure(guess(1, 0.5, "m"), 2)\n')
    assert isinstance(v.value, Miss)


def test_sure_propagates_a_miss_argument():
    v = val('let result = sure(1 / 0, 0.5)\n')
    assert isinstance(v.value, Miss)
    assert "division by zero" in v.value.reasons[0]


# --- deliberately shallow: no special-casing needed elsewhere ---------------

def test_indexing_a_guess_is_an_ordinary_miss():
    v = val('let result = guess([1, 2], 0.9, "m")[0]\n')
    assert isinstance(v.value, Miss)
    assert "cannot index" in v.value.reasons[0]
    assert "guess" in v.value.reasons[0]


def test_field_access_on_a_guess_is_an_ordinary_miss():
    v = val('let result = guess(@{a: 1}, 0.9, "m").a\n')
    assert isinstance(v.value, Miss)
    assert "cannot access" in v.value.reasons[0]


def test_calling_a_guessed_function_is_an_ordinary_miss():
    v = val('fn f(x) { x }\nlet result = guess(f, 0.9, "m")(1)\n')
    assert isinstance(v.value, Miss)


def test_guess_in_if_condition_is_an_ordinary_miss():
    v = val('let result = if guess(true, 0.9, "m") { 1 } else { 2 }\n')
    assert isinstance(v.value, Miss)
    assert "true/false" in v.value.reasons[0]


def test_guess_in_and_is_an_ordinary_miss():
    v = val('let result = guess(true, 0.9, "m") and true\n')
    assert isinstance(v.value, Miss)


def test_sure_unblocks_indexing():
    assert val(
        'let result = sure(guess([1, 2], 0.9, "m"), 0.5)[0]\n').value == 1


# --- structural type integration: `: guess` ---------------------------------

def test_typed_guess_parameter_accepts_a_guess():
    all_ok('fn f(g: guess) { confidence(g) }\n'
          'check "ok": f(guess(1, 0.7, "m")) == 0.7\n')


def test_typed_guess_parameter_rejects_a_plain_value():
    v = val('fn f(g: guess) { confidence(g) }\nlet result = f(10)\n')
    assert isinstance(v.value, Miss)
    assert "expected guess" in v.value.reasons[0]


def test_matches_agrees_with_shapeof_for_guess():
    all_ok('check "ok": matches(guess(1, 0.5, "m"), "guess") and '
          'not matches(1, "guess")\n')


# --- three-way differential (fast / direct / slow) --------------------------

def test_three_way_guess_arithmetic():
    # a call is needed to engage direct mode at all (call-free code runs
    # as a compiled closure and never touches call/direct machinery,
    # v0.4 decision 13) — mirrors test_v12's own three-way cases.
    assert_three_way(
        'fn add_self(g) { g + g }\n'
        'let result = add_self(guess(10, 0.9, "m")) + 1\n')


def test_three_way_guess_type_error():
    assert_three_way(
        'fn add5(g) { g + 5 }\nlet result = add5(guess("x", 0.9, "m"))\n')


def test_three_way_sure_below_threshold():
    assert_three_way(
        'fn commit(g) { sure(g, 0.9) }\n'
        'let result = commit(guess(1, 0.2, "m"))\n')


def test_three_way_typed_guess_tail_recursion():
    assert_three_way(
        'fn count(g: guess, acc: num) {\n'
        '  if acc == 0 { g } else { count(g, acc - 1) }\n'
        '}\n'
        'let result = count(guess(1, 0.8, "m"), 3000)\n')

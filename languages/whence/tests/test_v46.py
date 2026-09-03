"""v0.46 (round 480, language C), decision 59 — a declared kind is a
CONTRACT, and the hint that rides on it has a ceiling.

Round 476's next-step 3, carried by 477 and 478, asked for one number:

    "The order-hint coverage ratio is NEW and un-swept. `fold` gets 4 of 5
    wrong permutations. Nobody has taken that ratio for the other builtins
    `_order_hint` serves. Cheap, and the kind of number that turns out to
    be worse somewhere."

`orderhint.py` is the instrument; this file is what holds its findings open.
Three separate things are pinned here and they fail for different reasons:

  1. THE FOURTH SILENCE. At v0.45 a call carrying an already-missed value
     into a builtin could draw the v0.22 clause, and the clause was a FALSE
     CURE -- `note(bad, "hi")` advised reordering when the fault was a
     record lookup on the line above. `_order_hint` is now silent when any
     supplied payload is a Miss.

  2. THE `fn:fn` CONTRACT. `map`/`filter`/`find`/`fold` checked the
     `xs:list` half of their declared signature and not the `fn:fn` half,
     so a wrong-kind callback was noticed only if the loop got round to
     CALLING it -- and on an empty list it never does.

  3. THE CEILING, as a live re-derivation. The pooled coverage number and
     the structural bound above it are recomputed from the interpreter on
     every run rather than quoted, so a later change to a `sig=` or to a
     miss site moves this file's numbers and says so.

The negative controls matter more than the positives here: a diagnostic
that fires where reordering would not help is worse than no diagnostic,
because a reader trusts it. That is `_order_hint`'s own docstring, and
finding 1 above is the case it did not cover.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import orderhint                                   # noqa: E402
from whence.interp import Interpreter, _order_hint  # noqa: E402
from whence.values import Miss                      # noqa: E402

HINT = "arguments fit"

# NO `LINE_RE` here. `bench/sanitisers.py` surveys every `re.compile` in
# `tests/` and `tests/test_v38.py::test_no_normaliser_in_the_suite_eats_a_
# fact_bearing_line_number` fails any that would delete a parenthesised line
# number one of this language's messages carries as DATA (v0.37's rebind and
# v0.38's shape-redeclaration messages both do). The first draft of this file
# compiled an unanchored copy and that test caught it -- round 404 deleted
# nine such copies and this would have been the tenth. `orderhint._strip_line`
# is the one anchored spelling, and it is imported rather than repeated.

# The same three host evaluation modes `tests/test_v20.py::host_modes` uses:
# `fast=False` forces the trampoline, `direct=False` disables
# `_call_direct`, the default reaches `_compile_builtin_call`. Every
# behavioural assertion below runs in all three, because round 480's hoist
# prototype showed the builtin-invocation path DIFFERS between them (a
# change made in `_call_gen` alone was not reached by the default engine).
MODES = ({"fast": False}, {"direct": False}, {})


def reasons(src, **kw):
    p = Interpreter(**kw).run(src).get("result").payload
    if not isinstance(p, Miss):
        return None
    return orderhint._strip_line(p.reasons[0])


def all_modes(src):
    out = [reasons(src, **kw) for kw in MODES]
    assert len(set(out)) == 1, ("host modes disagree", src, out)
    return out[0]


# --- 1. the fourth silence ---------------------------------------------------

BAD = 'let bad = get(@{}, "z")\n'


def test_a_missed_argument_never_draws_an_order_hint():
    """The v0.45 defect, by its own witness. `note(label:str, v)` raises its
    OWN kind-miss rather than propagating, and a Miss payload's `_kind()`
    tag is `"miss"` -- a tag no signature declares, so it never fits a
    kinded slot and always fits an `any` one. That manufactured a fitting
    permutation for free."""
    got = all_modes(BAD + 'let result = note(bad, "hi")\n')
    assert got == "note label must be a string, got miss"
    assert HINT not in got


def test_the_same_call_without_the_miss_still_gets_its_hint():
    """The control. Round 480 removed a hint; this is the assertion that it
    removed the right one. `tests/test_v22.py` pins this text too and would
    also have gone red -- deliberately, so the silence cannot be widened
    into "never hint on `note`"."""
    got = all_modes('let result = note(5, "hi")\n')
    assert got == ("note label must be a string, got 5 "
                   "(arguments fit note(label, v))")


def test_the_silence_is_a_property_of_order_hint_not_of_note():
    """Stated against the function rather than through one builtin, so a
    future builtin that stops propagating inherits the fix instead of
    re-discovering the defect. `contains(hay:str|list, needle)` is the
    shape: a miss in `hay` fails the kinded slot and fits `needle`, so the
    permutation search WOULD find a fit."""
    env = Interpreter().run(BAD + 'let s = "x"\n')
    bad, s = env.get("bad"), env.get("s")
    assert isinstance(bad.payload, Miss)
    # with the miss: silent
    assert _order_hint("contains", [bad, s]) == ""
    # and the permutation really does fit -- so the silence is doing work,
    # not describing a search that would have failed anyway
    from whence.interp import _BUILTIN_SIGS, _sig_fits
    assert _sig_fits(_BUILTIN_SIGS["contains"], [s.payload, bad.payload])


def test_no_builtin_position_produces_a_false_hint():
    """The census form of the same claim, over every (builtin, position)
    pair rather than the ten calls somebody thought to type. Live, so a
    builtin added later joins the population by existing."""
    rep = orderhint.miss_arg_census()
    assert rep["totals"]["FALSE_HINT"] == 0, rep["false_hints"]
    assert rep["n_pairs"] == 46, rep["n_pairs"]


# --- 2. the fn:fn contract ---------------------------------------------------

# Whole programs, not `"let result = %s" % call`. `depthcensus.harvest_tests`
# walks `tests/` for Whence source and reports what it could NOT reach; a
# composed string lands in its `nonconstant_programs` residual and the corpus
# loses a program it could have run. Written this way after
# `tests/test_testcorpus_census.py` counted the first draft's two composed
# sites -- the instrument found them, which is the whole point of it.
EMPTY_CASES = [
    ("let result = map(0, [])\n", "map needs a function, got 0"),
    ("let result = filter(0, [])\n", "filter needs a function, got 0"),
    ("let result = find(0, [])\n", "find needs a function, got 0"),
    ("let result = fold(0, 7, [])\n", "fold needs a function, got 0"),
    ('let result = map("s", [])\n', 'map needs a function, got "s"'),
    ("let result = filter(@{a: 1}, [])\n",
     "filter needs a function, got @{a: 1}"),
]


@pytest.mark.parametrize("src,want", EMPTY_CASES)
def test_a_non_function_callback_is_a_miss_even_when_it_is_never_called(
        src, want):
    """v0.45 returned `[]`, `[]`, `find: no element matched` and `7` for the
    first four. Three accepted a wrong-kind argument silently; the fourth
    MISSED, with a reason that was false -- nothing was matched against
    anything, because there was no predicate."""
    assert all_modes(src) == want


NONEMPTY_CASES = [
    ("let result = map(0, [1, 2])\n", "map needs a function, got 0"),
    ("let result = filter(0, [1, 2])\n", "filter needs a function, got 0"),
    ("let result = find(0, [1, 2])\n", "find needs a function, got 0"),
]


@pytest.mark.parametrize("src,want", NONEMPTY_CASES)
def test_the_check_fires_before_the_loop_not_inside_it(src, want):
    """On a NON-empty list v0.45 reached `0 is not callable`, raised by the
    call machinery, which knows nothing about `map`'s signature. The
    builtin's own miss is strictly more informative and it arrives first."""
    got = all_modes(src)
    assert got == want
    assert "is not callable" not in got


def test_the_fifth_fold_permutation_now_names_the_signature_that_fits():
    """The row round 476 measured as uncovered, and the ONLY row round 480's
    census could reach. `fold(acc, fn, xs)` leaves a list in `xs`, so the
    list check passes; the function check catches it and `_order_hint` has
    a fitting permutation to name."""
    got = all_modes("let result = fold(0, fn(a, x) { a + x }, [1, 2, 3])\n")
    assert got == ("fold needs a function, got 0 "
                   "(arguments fit fold(fn, acc, xs))")


def test_a_wrong_callback_that_is_not_reorderable_still_gets_no_hint():
    """The negative control for the check above: `map(0, [1, 2])` has no
    permutation that fits (`0` is not a fn either way round), so pasting the
    clause on would be a lie. This is the third declared silence, and the
    new check must not have routed round it."""
    got = all_modes("let result = map(0, [1, 2])\n")
    assert HINT not in got


def test_working_higher_order_calls_are_untouched():
    """The whole point of a contract check is that it changes nothing for
    callers who honour the contract."""
    for src, want in (("map(fn(x) { x + 1 }, [1, 2])", "[2, 3]"),
                      ("filter(fn(x) { x > 1 }, [1, 2, 3])", "[2, 3]"),
                      ("find(fn(x) { x > 1 }, [1, 2, 3])", "2"),
                      ("fold(fn(a, x) { a + x }, 0, [1, 2, 3])", "6"),
                      ("map(fn(x) { x }, [])", "[]"),
                      ("fold(fn(a, x) { a + x }, 7, [])", "7")):
        for kw in MODES:
            from whence.values import full_show
            p = Interpreter(**kw).run("let result = %s\n" % src).get(
                "result").payload
            assert not isinstance(p, Miss), (src, kw, p.reasons)
            assert full_show(p) == want, (src, kw, full_show(p))


def test_a_builtin_is_a_function_too():
    """`fn` in a `sig` is `_kind`'s tag for `(Closure, Builtin)`, so the new
    check must accept a BUILTIN in the callback slot. Written because the
    obvious spelling of the check (`isinstance(p, Closure)`) would pass
    every other test in this file and break this one."""
    from whence.values import full_show
    p = Interpreter().run("let result = map(str, [1, 2])\n").get(
        "result").payload
    assert not isinstance(p, Miss), p.reasons
    assert full_show(p) == '["1", "2"]'


# --- 3. the census, re-derived --------------------------------------------

def test_every_witness_is_a_working_call():
    """`orderhint.WITNESSES` is a table of calls that MUST succeed in the
    declared order: a witness that misses would make every one of its
    permutations miss for the wrong reason and quietly inflate the coverage
    ratio. `census()` raises on such a row; this is the assertion that
    somebody runs it."""
    rep = orderhint.census()
    assert len(rep["rows"]) == len(orderhint.WITNESSES)


def test_the_witness_table_covers_the_population():
    """Every arity->=2 builtin has at least one witness. A builtin added
    later with a 2+ parameter `sig=` joins the population by existing and
    takes this red until somebody writes it one."""
    rep = orderhint.census()
    assert rep["uncovered_builtins"] == [], rep["uncovered_builtins"]
    assert rep["population_size"] == 21, rep["population_size"]


def test_the_pooled_coverage_and_its_ceiling():
    """The headline, live. 30 of 40 wrong permutations carry the hint; 31 is
    the CEILING, because 9 of the 40 are `kind_blind` -- the permuted order
    satisfies the declared kinds, so `_order_hint`'s second silence fires
    and no miss site, however placed, could produce a hint.

    The one row between 30 and the ceiling is `matches("num", 1)`, which
    returns `false` rather than missing. A diagnostic that rides on misses
    cannot serve a total function, and that is a bound on the MECHANISM,
    not a defect in `matches`."""
    t = orderhint.census()["totals"]
    assert t["n_perms"] == 40, t
    assert t["hinted"] == 30, t
    assert t["kind_blind"] == 9, t
    assert t["reachable_gap"] == 1, t
    assert abs(t["coverage"] - 0.750) < 1e-9, t
    assert abs(t["ceiling"] - 0.775) < 1e-9, t


def test_no_kind_blind_permutation_is_ever_hinted():
    """The ceiling as a PROPERTY rather than a count -- this is the one
    assertion here that a future `sig=` edit cannot make vacuously true by
    moving a number. `_order_hint` returns "" before searching whenever the
    given order already fits, so a `kind_blind` row is structurally
    unhintable."""
    for r in orderhint.census()["rows"]:
        for p in r["perms"]:
            if p["kind_blind"]:
                assert p["class"] != "HINTED", (r["builtin"], r["witness"], p)


def test_the_hint_marker_this_module_greps_for_is_the_text_the_code_emits():
    """`orderhint.HINT_MARK` is a literal, and a literal that drifts from
    the code silently reclassifies every row in the census as unhinted.
    Anchored against a live hint rather than against `interp.py`'s source."""
    got = all_modes('let result = note(5, "hi")\n')
    assert orderhint.HINT_MARK in got


def test_the_ratio_is_a_property_of_the_witness_not_of_the_builtin():
    """The finding that makes the headline number honest. `note`'s two
    witnesses differ only in the KIND of the second argument and land on
    opposite verdicts: with a number in `v` the transposition is caught and
    hinted; with a string in `v` both orders satisfy the declared kinds, the
    hint is structurally impossible, and the program gets a
    differently-labelled value with no diagnostic at all.

    Anything that reports `coverage(note)` without naming a witness is
    reporting a number that does not exist."""
    rows = {r["witness"]: r for r in orderhint.census()["rows"]
            if r["builtin"] == "note"}
    assert set(rows) == {"str-num", "both-str"}
    assert rows["str-num"]["coverage"] == 1.0
    assert rows["str-num"]["kind_blind"] == 0
    assert rows["both-str"]["coverage"] == 0.0
    assert rows["both-str"]["kind_blind"] == 1
    assert rows["both-str"]["accepted_diff"] == 1


def test_the_silent_wrong_answer_class_is_the_bigger_hazard():
    """Seven of forty wrong orders return a NON-miss value that differs from
    the correct call: no miss, no hint, a wrong answer. That is seven times
    the reachable coverage gap the next-step asked about, and it is the
    number round 480 would put in front of a reader first.

    Pinned as `>=` on the count and `==` on the membership, because a later
    round tightening a builtin should be able to shrink this set without
    editing an assertion, but must not be able to grow it silently."""
    rep = orderhint.census()
    assert rep["totals"]["accepted_diff"] == 7, rep["totals"]
    got = sorted({(r["builtin"], r["witness"]) for r in rep["rows"]
                  if r["accepted_diff"]})
    assert got == [("contains", "both-str"), ("contrast", "num-num"),
                   ("diverge", "num-num"), ("guess", "any-num-str"),
                   ("matches", "num-tag"), ("note", "both-str"),
                   ("range", "num-num")], got


def test_the_five_builtins_with_no_hint_site_are_named():
    """`contrast`, `diverge`, `matches`, `merge`, `range` have arity >= 2
    and no `_order_hint` call anywhere in the interpreter. Four of the five
    are structurally exempt (every permutation of their witnesses is
    `kind_blind`); `matches` is not, and is the one row in the reachable
    gap."""
    rep = orderhint.census()
    assert rep["builtins_with_no_hint_site"] == [
        "contrast", "diverge", "matches", "merge", "range"]
    for r in rep["rows"]:
        if r["builtin"] in rep["builtins_with_no_hint_site"]:
            assert r["hinted"] == 0, r

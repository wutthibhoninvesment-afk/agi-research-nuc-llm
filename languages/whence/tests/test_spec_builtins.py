"""SPEC.md's builtin signature table must match the interpreter's registry.

Round 349 (harness A). The operator reported against v0.19 that `fold()`
"returns Miss instead of calculated values when using inline lambdas or
external functions". It does not — but `fold(nums, 0, fn(acc, x) {...})`
does, because Whence's higher-order builtins take the function FIRST
(`fold(fn, acc, xs)`). The bug was that SPEC.md's `## Builtins` section was
a bare list of 36 names and the document gave the argument order for none
of them, so the only way to learn it was to read `whence/interp.py`.

Round 349 wrote the signature table. This test is the reason it can be
trusted later: a bare list cannot go stale (it asserts nothing), but a
table of 36 signatures absolutely can. Every name and arity here is checked
against the live `@register` registry, so adding, removing or re-arity-ing
a builtin without touching SPEC.md is a test failure rather than a silent
documentation drift — the "line asserting a number that no round
re-executes" class round 333 asked to be swept for, closed at the source
for this one table.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whence import interp as I

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(REPO_ROOT, "SPEC.md")

_ROW = re.compile(r"^\|\s*`(\w+)`\s*\|\s*(.+?)\s*\|", re.M)
_CALL = re.compile(r"`(\w+)\(([^)]*)\)`")


def _spec_table():
    with open(SPEC, encoding="utf-8") as f:
        text = f.read()
    start = text.index("## Builtins")
    end = text.index("### Blocks are always braced", start)
    rows = {}
    for name, sig_cell in _ROW.findall(text[start:end]):
        arities = set()
        for called, argstr in _CALL.findall(sig_cell):
            assert called == name, (
                "row for `%s` documents a call to `%s`" % (name, called))
            args = [a for a in (a.strip() for a in argstr.split(",")) if a]
            arities.add(len(args))
        assert arities, "no signature parsed for `%s` from %r" % (name, sig_cell)
        rows[name] = arities
    return rows


def _registry_arities():
    """name -> set of accepted arities, straight from the interpreter."""
    out = {}
    for name, entry in _registry_items():
        out[name] = _arity_of(entry)
    return out


def _registry_items():
    """`[(name, Builtin), ...]` built by interp._make_builtin_table().

    Calls the factory rather than reading the `_BUILTIN_TABLE` module
    global, which is a lazily-populated cache that is None until an
    Interpreter has actually installed builtins into an env.
    """
    table = I._make_builtin_table()
    assert table, "interp._make_builtin_table() returned nothing"
    return list(table)


def _arity_of(entry):
    """Accepted argument counts, expanded.

    `interp._arity_ok` reads a tuple arity as an inclusive RANGE
    (`min <= n <= max`), not as an enumeration of two allowed counts —
    round 349 got that wrong in SPEC.md's first draft of the table and this
    test is what caught it. Expand it the same way the interpreter does.
    """
    arity = entry.arity
    assert arity is not None, "no arity on registry entry %r" % (entry,)
    if isinstance(arity, tuple):
        lo, hi = arity
        return set(range(lo, hi + 1))
    return {arity}


def test_spec_table_documents_every_builtin_and_no_others():
    spec, reg = _spec_table(), _registry_arities()
    assert set(spec) == set(reg), (
        "SPEC.md's builtin table is out of sync with the registry.\n"
        "  documented but not registered: %s\n"
        "  registered but undocumented:   %s"
        % (sorted(set(spec) - set(reg)), sorted(set(reg) - set(spec))))


def test_spec_table_arities_match_the_registry():
    spec, reg = _spec_table(), _registry_arities()
    for name in sorted(set(spec) & set(reg)):
        assert spec[name] == reg[name], (
            "`%s`: SPEC.md documents arity %s, registry accepts %s"
            % (name, sorted(spec[name]), sorted(reg[name])))


def test_the_higher_order_builtins_really_do_take_the_function_first():
    """The operator's actual bug, pinned as behaviour rather than prose."""
    spec = _spec_table()
    for name in ("map", "filter", "fold", "find"):
        assert name in spec
    src = open(os.path.join(REPO_ROOT, "whence", "interp.py"), encoding="utf-8").read()
    assert "fn, acc, xs = args" in src, "fold's unpacking order changed"
    assert "fn, xs = args" in src
    # and `push` is genuinely the other way round — the asymmetry the table
    # calls out, so nobody 'fixes' the table into a false consistency.
    assert "xs, x = args" in src


# --- the operator's report, pinned as behaviour rather than prose -------------

def _val(src, name="result"):
    from whence.interp import Interpreter
    interp = Interpreter()
    return interp.run(src).get(name).payload


def test_fold_folds_inline_lambdas_and_named_functions():
    """Round 349's direct refutation of the reported v0.19 `fold` regression.

    Both spellings the operator named — an inline lambda and an external
    named function — fold correctly when written `fold(fn, acc, xs)`.
    """
    assert _val("let nums = [1, 2, 3, 4, 5]\n"
                "let result = fold(fn(acc, x) { acc + x }, 0, nums)") == 15
    assert _val("let nums = [1, 2, 3, 4, 5]\n"
                "let add = fn(acc, x) { acc + x }\n"
                "let result = fold(add, 100, nums)") == 115
    assert _val("let nums = [1, 2, 3, 4, 5]\n"
                "let result = fold(fn(acc, x) { acc * x }, 1, nums)") == 120


def test_fold_with_the_reported_argument_order_misses_and_names_the_field():
    """And the miss was never silent: it says which argument was wrong.

    This is why the report was a documentation bug, not a code bug — the
    interpreter already answered the question SPEC.md did not.
    """
    from whence.values import Miss
    p = _val("let nums = [1, 2, 3]\n"
             "let result = fold(nums, 0, fn(acc, x) { acc + x })")
    assert isinstance(p, Miss), p
    assert any("fold needs a list" in r for r in p.reasons), p.reasons


def test_if_branches_require_braces_and_the_parser_says_so():
    """The other half of the operator's report, and its exact wording."""
    from whence.interp import Interpreter
    from whence.parser import ParseError
    # Braced: fine. `if` is an expression, and a block yields its last one.
    assert _val('let x = 5\n'
                'let result = if x > 3 { "big" } else { "small" }') == "big"
    # Braceless: a parse error, in the parser's own words.
    with pytest.raises(ParseError) as ei:
        Interpreter().run('let x = 5\nif x > 3 print("big")\n')
    assert "expected '{'" in str(ei.value), str(ei.value)

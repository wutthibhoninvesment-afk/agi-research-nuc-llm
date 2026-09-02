"""Round 458 (language C): the test-corpus harvester, and the number
decision 53 cited without running.

Round 456's next-step 2:

    "The repo's true deepest value, 20 000, has never been re-derived by
     anything. Decision 53 states it -- a generated killer's runaway
     recursion whose unwind builds one record per frame -- and the number
     came from reading a test, not from an instrument."

It was re-derived here, and reading the test was the error: the file that
test lives in runs every one of its programs at `max_depth=500`.
"""

import ast
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import depthcensus as dc                                    # noqa: E402
from whence.interp import Interpreter                       # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
KILLERS = os.path.join(HERE, "test_generated_killers.py")

# The program decision 53 names, verbatim from
# tests/test_generated_killers.py::test_kill_values_py_139_arith_120.
WRAP = ('fn wrap(n) { if n == 0 { @{v: 0} } else { @{v: wrap(n - 0)} } }\n'
        'let rec = wrap(1)\n')


# ---------------------------------------------------------------------------
# 1. the finding
# ---------------------------------------------------------------------------

def _wrap_depth(max_depth):
    it = Interpreter(out=lambda _s: None, max_depth=max_depth)
    env = it.run(WRAP)
    return dc.depth_of(env.vars["rec"])


def test_the_generated_killer_suite_runs_every_program_at_500():
    """The premise. `canonical()` defaults to `max_depth=500` and `run()`
    passes no override, so no program in this file ever sees 20000."""
    tree = ast.parse(open(KILLERS, encoding="utf-8").read())
    fns = dict((n.name, n) for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef))
    assert dc._param_default(fns["canonical"], "max_depth") == 500
    runners = dc.runners_in(tree)
    assert runners["canonical"]["executes"] is True
    assert runners["canonical"]["max_depth"] == 500
    assert runners["run"]["max_depth"] == 500


def test_the_value_decision_53_cites_is_500_deep_not_20000():
    """SPEC decision 53: "The deepest value this repo builds anywhere is not
    14 -- it is 20000, built by tests/test_generated_killers.py's
    test_kill_values_py_139_arith_120 ... so the value's depth is exactly
    DEFAULT_MAX_DEPTH." Run it and it is 500."""
    assert _wrap_depth(500) == 500
    assert Interpreter.DEFAULT_MAX_DEPTH == 20000
    assert _wrap_depth(500) != Interpreter.DEFAULT_MAX_DEPTH


def test_the_same_source_at_the_default_depth_is_exactly_max_depth():
    """The mechanism decision 53 describes is real -- one record per unwound
    frame -- so the number IS reachable. It is reachable by a caller who
    passes no max_depth, which that test file is not."""
    assert _wrap_depth(Interpreter.DEFAULT_MAX_DEPTH) == \
        Interpreter.DEFAULT_MAX_DEPTH


def test_the_depth_is_the_cap_and_not_a_constant_of_the_program():
    """Three points, so "it equals max_depth" is a relationship rather than
    a coincidence at one value."""
    assert [_wrap_depth(d) for d in (7, 64, 501)] == [7, 64, 501]


def test_the_spec_no_longer_attributes_20000_to_that_test():
    """The correction has to land in SPEC.md, not only here. Round 456 made
    the same kind of fix in place for decision 53's other two sentences."""
    spec = open(os.path.join(os.path.dirname(HERE), "SPEC.md"),
                encoding="utf-8").read()
    bad = ("it is **20000**, built by\n`tests/test_generated_killers.py`'s "
           "`test_kill_values_py_139_arith_120`")
    assert bad not in spec
    assert "Decision 55" in spec


# ---------------------------------------------------------------------------
# 2. the harvester
# ---------------------------------------------------------------------------

def test_walk_scope_does_not_descend_into_a_nested_function():
    """The defect this module shipped for one draft: with `ast.walk`, the
    module scope held every `src = "..."` in every test function, so a call
    in one function resolved a name bound in another."""
    tree = ast.parse("X = 'a'\ndef f():\n    Y = 'b'\n    return Y\n")
    top = [n.targets[0].id for n in dc._walk_scope(tree)
           if isinstance(n, ast.Assign)]
    assert top == ["X"]
    assert len([n for n in ast.walk(tree) if isinstance(n, ast.Assign)]) == 2


def test_const_str_folds_a_name_plus_a_literal():
    """`test_v03.py` writes `src = LOOP + "let s = go(3, 0)\\n..."`."""
    node = ast.parse("LOOP + 'tail'", mode="eval").body
    assert dc._const_str(node) is None
    assert dc._const_str(node, {"LOOP": ["head\n"]}) == "head\ntail"
    # Ambiguity is not resolved by guessing.
    assert dc._const_str(node, {"LOOP": ["a", "b"]}) is None


def test_a_parse_only_runner_is_found_and_excluded():
    """A helper that only parses builds no values, so its strings are
    counted, not censused."""
    src = ("from whence.parser import parse\n"
           "def p(src):\n    return parse(src)\n"
           "def test_x():\n    p('let a = 1')\n")
    path = os.path.join(HERE, "__tmp_parse_only.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src)
    try:
        rows, stats = dc.harvest_file(path)
        assert "p" in stats["runners"]
        assert "p" not in stats["executing_runners"]
        assert rows == []
        assert stats["parse_only_programs"] == 1
    finally:
        os.remove(path)


def test_a_direct_interpreter_run_is_harvested_with_its_scopes_depth():
    src = ("from whence.interp import Interpreter\n"
           "def test_x():\n"
           "    i = Interpreter(max_depth=9)\n"
           "    i.run('let a = 1')\n")
    path = os.path.join(HERE, "__tmp_direct.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src)
    try:
        rows, _ = dc.harvest_file(path)
        assert [(r["runner"], r["max_depth"], r["src"]) for r in rows] == \
            [(".run", 9, "let a = 1")]
    finally:
        os.remove(path)


def test_a_program_table_in_a_for_loop_is_harvested():
    src = ("from whence.interp import Interpreter\n"
           "def run(src):\n    return Interpreter().run(src)\n"
           "def test_x():\n"
           "    for src in ['let a = 1', 'let b = 2']:\n"
           "        run(src)\n")
    path = os.path.join(HERE, "__tmp_table.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src)
    try:
        rows, _ = dc.harvest_file(path)
        assert sorted(r["src"] for r in rows) == ["let a = 1", "let b = 2"]
    finally:
        os.remove(path)


def test_a_forwarded_parameter_is_not_counted_as_a_missed_program():
    """`def val(src): return run(src)` forwards; the program arrives at
    val's own call site, which the walk also visits. Counting that as a
    miss would make the residual look twice its size."""
    src = ("from whence.interp import Interpreter\n"
           "def run(src):\n    return Interpreter().run(src)\n"
           "def val(src):\n    return run(src)\n"
           "def test_x():\n    val('let a = 1')\n")
    path = os.path.join(HERE, "__tmp_fwd.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src)
    try:
        rows, stats = dc.harvest_file(path)
        assert [r["src"] for r in rows] == ["let a = 1"]
        # TWO forwarding sites, not one: `val` forwards into `run`, and
        # `run` forwards into `Interpreter().run`. Both are real, and the
        # program is still harvested exactly once, at val's call site.
        assert stats["forwarded_args"] == 2
        assert stats["unresolved_args"] == 0
    finally:
        os.remove(path)


def test_the_parse_gate_alone_would_not_define_a_population():
    """7935 of this tree's 11 990 string constants parse as Whence, because
    `"ab"` is a legal expression. The population is defined by what the
    suite DOES with a string; this pins the reason."""
    from whence.parser import parse
    for s in ("ab", "1", "ok", "a + b", "2026-09-02"):
        assert parse(s).stmts, s
    # And the converse: the gate is not vacuous either. Plain English with
    # two bare names in a row is a ParseError, which is why the number is
    # 7935 of 11 990 and not 11 990 of 11 990.
    from whence.parser import ParseError
    for s in ("the renderer stops here", "a message from the checker"):
        with pytest.raises(ParseError):
            parse(s)


# ---------------------------------------------------------------------------
# 3. the harvest over the real tree
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def harvest():
    return dc.harvest_tests()


def test_the_harvest_is_a_real_corpus(harvest):
    progs, stats = harvest
    assert stats["files"] >= 60
    assert len(progs) > 400
    assert stats["executing_runners"] > stats["parse_only_runners"]


def test_every_harvested_program_parses_and_names_its_depth(harvest):
    from whence.parser import parse
    progs, _ = harvest
    for p in progs:
        assert parse(p["src"]).stmts, p["src"][:60]
        assert isinstance(p["max_depth"], int) and p["max_depth"] >= 1


def test_the_harvest_reports_its_own_residual_rather_than_claiming_all(harvest):
    """An instrument that returns a corpus without saying what it could not
    reach reads as exhaustive. These four counters are the class the
    docstring names: a formatted source, a table, a subscript, a call."""
    _, stats = harvest
    for k in ("unresolved_args", "nonconstant_programs",
              "parse_only_programs", "ambiguous_scopes"):
        assert k in stats and stats[k] > 0, k


def test_the_two_generated_killer_suites_contribute_only_depth_500(harvest):
    progs, _ = harvest
    for p in progs:
        if p["file"].startswith("test_generated_killers"):
            assert p["max_depth"] == 500, (p["file"], p["line"])


def test_the_wrap_killer_is_in_the_harvest_at_500(harvest):
    progs, _ = harvest
    hits = [p for p in progs if p["src"] == WRAP]
    assert hits, "the program decision 53 cites is not in the harvest"
    assert 500 in [p["max_depth"] for p in hits]


def test_census_program_honours_the_max_depth_it_is_given():
    a = dc.census_program("wrap:1", src=WRAP, max_depth=40)
    b = dc.census_program("wrap:1", src=WRAP, max_depth=400)
    assert a["ok"] and b["ok"]
    assert (a["max_depth"], b["max_depth"]) == (40, 400)
    assert (a["alloc_depth"], b["alloc_depth"]) == (40, 400)
    assert a["alloc_agrees"] and b["alloc_agrees"]

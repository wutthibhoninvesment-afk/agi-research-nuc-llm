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


@pytest.fixture(scope="module")
def harvest_rows():
    """The same harvest with `keep_rows`. A separate fixture on purpose:
    `--json` dumps the stats dict, and 480-odd rows would change the shape of
    every artefact already on disk, so rows are opt-in at every level."""
    _, stats = dc.harvest_tests(keep_rows=True)
    return stats["rows"]


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


# ---------------------------------------------------------------------------
# 4. round 462: the residual that was not a residual
#
# Round 458 published `unresolved_args 127` + `nonconstant_programs 130` as
# "257 programs this instrument cannot reach". A third of the second number
# was call sites that are not Whence runners at all, so the instrument was
# overstating its own blind spot -- a PRECISION defect reported as a RECALL
# defect. These tests pin the two exclusions, the counters that keep them
# auditable, and the multi-valued fold that closes the classes that were
# genuinely missing.
# ---------------------------------------------------------------------------

def _harvest_source(src, tag):
    """Harvest one synthetic module; returns (rows, stats)."""
    path = os.path.join(HERE, "__tmp_%s.py" % tag)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src)
    try:
        return dc.harvest_file(path)
    finally:
        os.remove(path)


def test_a_module_call_is_not_an_interpreter_call():
    """`subprocess.run([sys.executable, RUN, path])` is 45 of the 985 calls
    the round-458 walk saw, and its first argument is an argv LIST. The
    exclusion is derived from the file's own `import` statements, not from a
    denylist of module names."""
    rows, stats = _harvest_source(
        "import subprocess\n"
        "import sys\n"
        "from whence.interp import Interpreter\n"
        "def test_x():\n"
        "    subprocess.run([sys.executable, 'run.py', 'x.lang'])\n"
        "    Interpreter().run('let a = 1')\n", "modcall")
    assert [r["src"] for r in rows] == ["let a = 1"]
    assert stats["module_calls"] == 1
    # and the exclusion did NOT land in either residual counter
    assert stats["nonconstant_programs"] == 0
    assert stats["unresolved_args"] == 0


def test_an_imported_module_is_not_confused_with_an_imported_class():
    """`from whence.interp import Interpreter` binds a class, and a class is
    exactly what a legitimate receiver may be. Only `ast.Import` contributes
    to the exclusion set."""
    mods = dc._imported_modules(ast.parse(
        "import subprocess\n"
        "import os.path\n"
        "import numpy as np\n"
        "from whence.interp import Interpreter\n"))
    assert mods == {"subprocess", "os", "np"}
    assert "Interpreter" not in mods


def test_exec_stmt_takes_a_statement_and_not_a_source_string():
    """`interp.exec_stmt(prog.stmts[0], env)` -- the argument is already
    parsed. Every one of these was landing in `nonconstant_programs` as a
    program that could not be reached, where there is no program to reach.
    The call still makes its enclosing function an EXECUTING runner: the two
    facts are different, which is why the module now keeps two tuples."""
    rows, stats = _harvest_source(
        "from whence.interp import Interpreter\n"
        "from whence.parser import parse\n"
        "def drive(src):\n"
        "    i = Interpreter()\n"
        "    for st in parse(src).stmts:\n"
        "        i.exec_stmt(st, i.globals)\n"
        "def test_x():\n"
        "    drive('let a = 1')\n", "execstmt")
    assert "drive" in stats["executing_runners"], "exec_stmt still executes"
    assert [r["src"] for r in rows] == ["let a = 1"]
    assert stats["stmt_node_args"] == 1
    assert stats["nonconstant_programs"] == 0
    assert "exec_stmt" in dc._EXEC_ATTRS
    assert "exec_stmt" not in dc._SRC_ARG0_ATTRS


def test_a_conditional_source_is_two_programs_not_an_unknown():
    """`val("A" if C else "B")` denotes two programs. A `str | None` folder
    can only call that a miss; `test_fuzz_regressions.py:211` is the real
    instance and it contributed 2 of this round's 71 recovered programs."""
    got = dc._const_strs(ast.parse("('let a = 1' if x else 'let b = 2')",
                                   mode="eval").body)
    assert got == ["let a = 1", "let b = 2"]
    assert dc._const_str(ast.parse("('let a = 1' if x else 'let b = 2')",
                                   mode="eval").body) is None


def test_a_percent_template_over_a_table_of_tuples_is_folded():
    """25 of round 458's 131 non-constant nodes are this one shape:
    `host_reason('let r = typed(1, %s, "L")' % spec)` under
    `for spec, want in NAME_SLOT_CASES:`. It needs a LITERAL environment as
    well as a string one -- `%`'s right operand is not a string."""
    rows, stats = _harvest_source(
        "from whence.interp import Interpreter\n"
        "CASES = [('num', 'a'), ('str', 'b')]\n"
        "def run(src):\n    return Interpreter().run(src)\n"
        "def test_x():\n"
        "    for spec, want in CASES:\n"
        "        run('let r = typed(1, %s)' % spec)\n", "pct")
    assert sorted(r["src"] for r in rows) == \
        ["let r = typed(1, num)", "let r = typed(1, str)"]
    assert stats["multivalued_nodes"] == 1
    assert stats["nonconstant_programs"] == 0


def test_an_f_string_source_is_folded():
    rows, _ = _harvest_source(
        "from whence.interp import Interpreter\n"
        "N = 7\n"
        "def run(src):\n    return Interpreter().run(src)\n"
        "def test_x():\n"
        "    run(f'let a = {N}')\n", "fstr")
    assert [r["src"] for r in rows] == ["let a = 7"]


def test_a_constant_join_is_folded_and_a_loop_built_one_is_not():
    """The line between the two is the whole point of counting a residual:
    `"".join(["a", "b"])` is decidable and `"".join(parts)` where `parts` is
    appended to in a loop is not. 18 `.join` nodes are in the tree and the
    loop-built ones stay in the residual on purpose."""
    assert dc._const_strs(ast.parse(
        '"\\n".join(["let a = 1", "let b = 2"])', mode="eval").body) == \
        ["let a = 1\nlet b = 2"]
    assert dc._const_strs(ast.parse('"".join(parts)',
                                    mode="eval").body) == []


def test_the_fold_is_capped_and_the_cap_is_counted():
    """`A + B` with five bindings each is twenty-five programs. A harvester
    that expands that silently reports a corpus larger than the suite runs,
    so the product is bounded and the bound is a counter."""
    env = {"A": ["a%d" % i for i in range(8)],
           "B": ["b%d" % i for i in range(8)]}
    got = dc._const_strs(ast.parse("A + B", mode="eval").body, env)
    assert len(got) == dc.MAX_FOLD == 32
    assert got[0] == "a0b0"


# ---------------------------------------------------------------------------
# 5. round 462, over the real tree
# ---------------------------------------------------------------------------

def test_the_exclusions_are_counted_and_reconcile_with_the_old_call_count(
        harvest):
    """985 calls at round 458 = 918 + 45 module calls + 22 statement-node
    arguments. The exclusions are auditable arithmetic, not a silent
    narrowing of the walk.

    Round 468 moves the total 985 -> 987 and says why in the same breath:
    `harvest_file`'s scope list held only `FunctionDef`/`ClassDef` while
    `_walk_scope` also refuses to descend into `Lambda`, so two `run(src)`
    calls inside `lambda:` bodies (`test_v09.py:245` and `:254`) were visited
    by no scope at all. They were never in the 985 and never in any counter.
    A call count that GREW when a blind spot closed is the right direction;
    the number to distrust would have been one that stayed put."""
    _, stats = harvest
    assert stats["module_calls"] == 45
    assert stats["stmt_node_args"] == 22
    assert stats["calls"] + stats["module_calls"] + \
        stats["stmt_node_args"] == 987


def test_the_exclusions_removed_no_programs_from_the_corpus(harvest):
    """The false positives contaminated the RESIDUAL, not the corpus: the
    round-462 harvest is a strict SUPERSET of round 458's 488 programs.
    Measured by set difference against the module at 508b95f, 0 lost."""
    progs, stats = harvest
    assert stats["programs"] >= 559
    assert len(progs) == stats["programs"]
    # one representative from each class the round recovered
    srcs = {p["src"] for p in progs}
    assert 'let r = typed(1, @{__shape: "Pt", a: "num"}, "L")' in srcs
    assert 'let result = [f] == [f]\nfn f(x) { x }\n' in srcs


def test_the_residual_fell_by_more_than_a_third_and_did_not_reach_zero(
        harvest):
    """258 = 127 + 131 at round 458; both counters must stay POSITIVE.
    `"".join(parts)` over a loop-built list and `open(path).read()` over a
    runtime `listdir` are not statically foldable and saying so is the
    instrument's job."""
    _, stats = harvest
    residual = stats["unresolved_args"] + stats["nonconstant_programs"]
    assert residual <= 100, residual   # 166 r462, 114 r468, 100 r470
    assert residual < 258 * 2 // 3
    assert stats["unresolved_args"] > 0
    assert stats["nonconstant_programs"] > 0




# ---------------------------------------------------------------------------
# 6. round 468 -- the residual, item by item
#
# Round 462's next-step 2: "the 166 remaining residual entries are ARGUED
# undecidable, not measured undecidable ... classify the 94 the way it
# classified the 131, one row per entry". These tests pin the itemisation and
# the four defects it made visible.
# ---------------------------------------------------------------------------

def _harvest_source(src, name):
    """Harvest one synthetic test module and return (programs, stats)."""
    path = os.path.join(HERE, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src)
    try:
        return dc.harvest_file(path)
    finally:
        os.remove(path)


def test_every_residual_entry_carries_a_location_and_a_class(harvest_rows):
    """A COUNTER CANNOT BE AUDITED, ONLY BELIEVED. `unresolved_args: 94`
    supports exactly one action -- "widen the folder" -- and cannot say which
    widening. Every row carries a file, a line, the source text of the node
    that defeated the walk, and a class a reader can refute by opening the
    file."""
    rows = [r for r in harvest_rows if r["kind"] == "residual"]
    assert rows
    for r in rows:
        assert r["file"].endswith(".py") and r["line"] > 0, r
        assert r["cls"] and r["text"], r
        assert len(r["text"]) <= dc.ROW_TEXT_CAP


def test_the_rows_reconcile_with_the_counters(harvest_rows, harvest):
    """The rows and the counters are derived at the same site, so a row that
    is not counted -- or a count with no row -- is a bug this sees."""
    _, stats = harvest
    kinds = {}
    for r in harvest_rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    assert kinds["residual"] == (stats["unresolved_args"] +
                                 stats["nonconstant_programs"])
    assert kinds["excluded"] == (stats["module_calls"] +
                                 stats["stmt_node_args"] +
                                 stats["file_reads"])
    assert kinds["parse_only"] == stats["parse_only_strings"]
    assert kinds["unparsed"] == stats["unparsed_programs"]
    assert kinds["forwarded"] == stats["forwarded_args"]


def test_the_string_level_accounting_closes(harvest):
    """Round 468's `strings_folded` and `dup_in_file`. Before them the
    per-file `seen` set dropped a repeated `(src, depth)` and incremented
    nothing, so no identity over folded strings could be written at all."""
    _, stats = harvest
    assert stats["strings_folded"] == (stats["parse_only_strings"] +
                                       stats["dup_in_file"] +
                                       stats["unparsed_programs"] +
                                       stats["programs_before_dedup"])
    assert (stats["programs_before_dedup"] - stats["dup_cross_file"] ==
            stats["programs"])
    assert stats["dup_in_file"] > 0


def test_every_counter_reaches_the_report(harvest):
    """SEVEN counters were collected and printed by no CLI path before this
    round (`parse_only_programs`, `unparsed_programs`, `forwarded_args`,
    `ambiguous_scopes`, `programs_before_dedup`, `executing_runners`,
    `parse_only_runners`) -- which is how `parse_only_programs` could measure
    the wrong unit for three rounds without anyone seeing the number. A
    counter with no reader is a counter with no check."""
    _, stats = harvest
    numeric = {k for k, v in stats.items() if isinstance(v, int)}
    assert numeric == set(dc.REPORT_KEYS), numeric ^ set(dc.REPORT_KEYS)
    text = dc.harvest_report(stats)
    for k in dc.REPORT_KEYS:
        assert str(stats[k]) in text, k


def test_parse_only_is_counted_in_the_unit_it_is_compared_against():
    """`parse_only_programs` fired once per folded string, BEFORE the dedup
    and BEFORE the parse gate that `programs` is measured after -- so round
    462's "145 parse-only against 559 harvested" compared two units. Here one
    non-program string appears twice and one program string once: three
    occurrences, two distinct, ONE program."""
    src = ("from whence.parser import parse\n"
           "def p(src):\n    return parse(src)\n"
           "def test_a():\n    p('let y = (')\n    p('let y = (')\n"
           "def test_b():\n    p('let a = 1')\n")
    _, stats = _harvest_source(src, "__tmp_po_unit.py")
    assert stats["parse_only_strings"] == 3
    assert stats["parse_only_srcs"] == ["let y = (", "let a = 1"] or \
        sorted(stats["parse_only_srcs"]) == ["let a = 1", "let y = ("]
    assert stats["parse_only_programs"] == 1


def test_over_the_real_tree_most_parse_only_strings_are_not_programs(harvest):
    """And the measured answer is the interesting one: the parse-only runners
    are `parse_error`/`err`/`reason` helpers, so their strings are
    DELIBERATELY malformed. 186 occurrences, 141 distinct, 25 programs."""
    _, stats = harvest
    assert stats["parse_only_strings"] > stats["parse_only_distinct"]
    assert stats["parse_only_distinct"] > stats["parse_only_programs"] * 3
    assert stats["parse_only_programs"] > 0


def test_a_call_inside_a_lambda_body_is_visited():
    """`_walk_scope` has refused to descend into `Lambda` since round 458 and
    the scope list did not contain one, so a call in a lambda body was
    visited by NO scope and counted by NO counter. `SCOPE_KINDS` is now the
    single list both read."""
    src = ("from whence.interp import Interpreter\n"
           "def run(src):\n    return Interpreter().run(src)\n"
           "def test_x():\n    f = lambda: run('let a = 1')\n    f()\n")
    progs, stats = _harvest_source(src, "__tmp_lambda.py")
    assert [p["src"] for p in progs] == ["let a = 1"]
    # Two source positions: `Interpreter().run(src)` inside the helper (whose
    # argument is a forwarded parameter) and `run('let a = 1')` inside the
    # lambda body. The second is the one that was invisible.
    assert stats["calls"] == 2
    assert stats["forwarded_args"] == 1


def test_a_name_bound_in_an_enclosing_function_resolves():
    """The environment was `module | this scope` and nothing in between. The
    class existed with zero instances until lambdas entered the scope list,
    at which point `test_v09.py`'s `lambda: run(src)` became the first."""
    src = ("from whence.interp import Interpreter\n"
           "def run(src):\n    return Interpreter().run(src)\n"
           "def test_x():\n"
           "    src = 'let a = 1'\n"
           "    f = lambda: run(src)\n    f()\n")
    progs, stats = _harvest_source(src, "__tmp_closure.py")
    assert [p["src"] for p in progs] == ["let a = 1"]
    assert stats["unresolved_args"] == 0


def test_a_file_read_is_an_exclusion_and_not_a_residual():
    """Gate (1) of the declared population is *a Python string constant in
    the test tree*; a file's contents is not one. Round 462 counted
    `subprocess.run` the same way and for the same reason -- a call skipped
    for a stated reason must not share a counter with one that defeated the
    walk."""
    src = ("from whence.interp import Interpreter\n"
           "def test_x():\n"
           "    i = Interpreter()\n"
           "    i.run(open('p.lang').read())\n"
           "    src = open('q.lang').read()\n"
           "    i.run(src)\n")
    _, stats = _harvest_source(src, "__tmp_fileread.py")
    assert stats["file_reads"] == 2
    assert stats["nonconstant_programs"] == 0
    assert stats["unresolved_args"] == 0


def test_a_comprehension_target_binds_exactly_like_a_for_target():
    """`_walk_scope` already descended into a comprehension -- the node was
    VISITED and its target simply never bound. 10 of the 94."""
    src = ("from whence.interp import Interpreter\n"
           "CASES = ['let a = 1', 'let b = 2']\n"
           "def run(src):\n    return Interpreter().run(src)\n"
           "def test_x():\n    [run(s) for s in CASES]\n")
    progs, stats = _harvest_source(src, "__tmp_comp.py")
    assert sorted(p["src"] for p in progs) == ["let a = 1", "let b = 2"]
    assert stats["unresolved_args"] == 0


def test_a_literal_dict_table_drives_the_binder():
    """`for name, src in TABLE.items():` over a dict literal. `_literal` had
    no `ast.Dict` branch at all, so a dict-shaped table was as opaque as a
    network call."""
    src = ("from whence.interp import Interpreter\n"
           "TABLE = {'a': 'let a = 1', 'b': 'let b = 2'}\n"
           "def run(src):\n    return Interpreter().run(src)\n"
           "def test_x():\n"
           "    for name, s in TABLE.items():\n        run(s)\n")
    progs, stats = _harvest_source(src, "__tmp_dict.py")
    assert sorted(p["src"] for p in progs) == ["let a = 1", "let b = 2"]


def test_string_repetition_folds_and_the_repeat_is_capped():
    """`'(' * 40` is exactly as constant as `'(' + '('`, and three residual
    classes turned on it. `**` is refused outright: `10 ** 100000` is a
    denial of service in four characters, and no row needs it."""
    lits = {}
    fold = lambda e: dc._literal(ast.parse(e, mode="eval").body, lits)
    assert fold("'(' * 40") == "(" * 40
    assert fold("2 * 3") == 6
    assert fold("'x' * (3 + 1)") == "xxxx"
    assert fold("'x' * 10 ** 9") is dc._NOLIT       # cap
    assert fold("2 ** 3") is dc._NOLIT              # never
    assert fold("'x' * -1") is dc._NOLIT
    node = ast.parse("'let a = ' + '1' * 3", mode="eval").body
    assert dc._const_strs(node, {}, lits) == ["let a = 111"]


def test_a_zip_over_a_runtime_column_is_refused_and_says_so():
    """13 rows are `for src, g in zip(CORPUS, guest_eval_all(CORPUS))`.
    `zip` truncates to its shortest argument, so the strings that reach the
    runner are a SUBSET of the literal column; binding all of them would
    publish programs the suite may never run. The refusal is a NAMED class,
    not an omission -- show the columns are equal-length by construction and
    the widening becomes sound."""
    src = ("from whence.interp import Interpreter\n"
           "CASES = ['let a = 1', 'let b = 2']\n"
           "def other(xs):\n    return xs\n"
           "def run(src):\n    return Interpreter().run(src)\n"
           "def test_x():\n"
           "    for s, g in zip(CASES, other(CASES)):\n        run(s)\n")
    _, stats = _harvest_source(src, "__tmp_zip.py")
    assert stats["unresolved_args"] == 1
    assert [r["cls"] for r in stats["rows"] if r["kind"] == "residual"] == \
        ["zip_nonliteral_column"]
    # Both columns literal IS folded -- the refusal is about the runtime one.
    src2 = src.replace("other(CASES)", "['x', 'y']")
    progs, stats2 = _harvest_source(src2, "__tmp_zip2.py")
    assert sorted(p["src"] for p in progs) == ["let a = 1", "let b = 2"]
    assert stats2["unresolved_args"] == 0


def test_the_widenings_lost_no_program_and_the_residual_only_fell(harvest):
    """Round 462 proved its own superset claim by set difference rather than
    argument; this round did the same against the module at `be5c248`
    (0 of 559 lost, 206 added). What a test can pin at HEAD is the floor and
    the two classes that produced the biggest share."""
    progs, stats = harvest
    assert stats["programs"] >= 765
    srcs = {p["src"] for p in progs}
    # One witness per structural fix, each absent from the 559 at `be5c248`.
    # `lambda: run(src)` in `test_v09.py:245` -- the scope-list hole AND the
    # environment chain, since `src` is bound in the enclosing function.
    assert ("fn count(n) { if n == 0 { 0 } else { 1 + count(n - 1) } }\n"
            "let result = count(3000)\n") in srcs
    # string repetition: `'let result = ' + '(' * 40 + '1' + ')' * 40`
    assert "let result = " + "(" * 40 + "1" + ")" * 40 in srcs
    # a dict literal read through `.values()` (`test_v27.py:573`)
    assert ("fn go(n, xs) { if n <= 0 { xs } else { go(n - 1, xs + xs) } }\n"
            "let result = go(13, [1, 2])\n") in srcs


def test_the_residual_is_dominated_by_string_building_not_by_tables(harvest,
                                                                    harvest_rows):
    """The DIAGNOSIS moved, and that is the point of an itemisation. Before:
    39 of the 94 unresolved names -- 41% -- were bound by an ITERATION
    PROTOCOL the binder could not read (`zip` 19, `.items()`/`.values()` 8,
    a comprehension 10, `sorted`/`enumerate` 2), not by a string the folder
    could not build. Round 462's published diagnosis named `"".join(parts)`
    and `open(path).read()`, which are classes of the OTHER counter. After
    the widenings the remaining residual really is string-building."""
    rows = [r for r in harvest_rows if r["kind"] == "residual"]
    by = {}
    for r in rows:
        by[r["cls"]] = by.get(r["cls"], 0) + 1
    building = sum(n for c, n in by.items()
                   if "binop:" in c or ".join" in c)
    assert building >= len(rows) // 2, by
    assert "bound_in_skipped_scope:assign" not in by



def test_the_multivalued_fold_is_load_bearing_and_not_decorative(harvest):
    """P9: at least 10 recovered programs come from a node that denotes two
    or more strings, so a `str | None` folder could not have closed these
    classes however many shapes it learned."""
    _, stats = harvest
    assert stats["multivalued_nodes"] >= 10, stats["multivalued_nodes"]


# ---------------------------------------------------------------------------
# 7. round 470 -- the `zip` refusal, refuted
# ---------------------------------------------------------------------------
# Round 468's next-step 2: "`zip_nonliteral_column` is a DECISION, not an
# omission, and it is refutable. 13 rows ... The refusal rests on `zip`
# truncating to its shortest argument. If someone shows the columns are
# equal-length by construction at every one of those 13 sites -- they look
# it, and looking is not showing -- the widening becomes sound."
#
# It was shown, and the showing is these tests. The refusal was an argument
# about `zip` rather than about the call sites, and `zip` was never the
# variable: at all 13 sites the second column is `f(A)` where `A` IS the
# first column, so the question is whether THIS second column can be shorter
# than THIS first one. Every test below is one step of that proof or one
# case the proof must REFUSE.
# ---------------------------------------------------------------------------

def _fn(src, name):
    tree = ast.parse(src)
    return tree, dict((n.name, n) for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef))[name]


def _tree_of(fname):
    path = os.path.join(HERE, fname)
    return ast.parse(open(path, encoding="utf-8").read()), path


# --- 7.1 the three producers in this tree ----------------------------------

def test_all_three_producers_in_this_tree_are_length_preserving():
    """THE REFUTATION, stated as the thing round 468 asked for. Each of the
    three functions that build the second column of a `zip` in this suite
    pins its output length to a named input's, by a syntactic shape that
    cannot shorten. `guest_eval_all` and `guest_batch` are the accumulator
    shape; `guest_values` is the comprehension shape. Note what they do on a
    missing element: `assert`, not `continue` -- a short answer is an
    exception, not a short list."""
    for fname, fn, param in (("test_self_eval.py", "guest_eval_all", "sources"),
                             ("test_v20.py", "guest_eval_all", "sources"),
                             ("test_v30.py", "guest_batch", "sources"),
                             ("test_v31.py", "guest_values", "programs")):
        tree, _ = _tree_of(fname)
        node = dict((n.name, n) for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef))[fn]
        assert dc._len_preserving_param(node) == param, (fname, fn)


def test_the_thirteen_zip_sites_are_zip_of_a_function_of_the_first_column():
    """The structural claim, checked at every site rather than argued once.
    For each `for <t> in zip(A, B)` in the four files that held the 13 rows,
    `B` carries `A`'s own length token -- i.e. the walk can follow `B` back
    to `A` through assignments, comprehensions and length-preserving calls.

    `test_v30.py`'s second loop is the exception and it is IN the list: its
    first column is `[s for s in AGREE if ...]`, a filtered comprehension,
    so there is no literal column and the site is unbindable for a reason
    that has nothing to do with lengths."""
    seen, unbindable = 0, 0
    for fname in ("test_self_eval.py", "test_v20.py", "test_v22.py",
                  "test_v30.py", "test_v31.py"):
        tree, path = _tree_of(fname)
        sbind = dc._scope_bindings(
            [tree] + [n for n in ast.walk(tree)
                      if isinstance(n, dc.SCOPE_KINDS)])
        fns = dc._fn_index(tree, path)
        for sc in [tree] + [n for n in ast.walk(tree)
                            if isinstance(n, dc.SCOPE_KINDS)]:
            for node in dc._walk_scope(sc):
                if not isinstance(node, ast.For):
                    continue
                it = node.iter
                if not (isinstance(it, ast.Call)
                        and dc._callee(it) == ("name", "zip")):
                    continue
                seen += 1
                lits = {}
                for n2 in ast.walk(tree):
                    if isinstance(n2, ast.Assign) and len(n2.targets) == 1 \
                            and isinstance(n2.targets[0], ast.Name):
                        v = dc._literal(n2.value, lits)
                        if v is not dc._NOLIT:
                            lits[n2.targets[0].id] = [v]
                cb = dc._zip_bindable_columns(it, lits, sc, tree, sbind,
                                              {}, fns)
                if not cb:
                    unbindable += 1
    assert seen >= 13, seen
    assert unbindable <= 2, unbindable


def test_the_length_token_threads_a_three_link_chain():
    """`zip(SHARING, guests)` needs THREE links, and a one-link rule would
    have refused it: `guests` -> `guest_batch(srcs, lib)` -> `srcs` ->
    `[s for s, _ in SHARING]` -> `SHARING`. This is the case that decides
    whether the analysis is real or a special case for the shape that
    happened to be read first."""
    tree, path = _tree_of("test_v30.py")
    scopes = [tree] + [n for n in ast.walk(tree)
                       if isinstance(n, dc.SCOPE_KINDS)]
    sbind = dc._scope_bindings(scopes)
    fns = dc._fn_index(tree, path)
    target = None
    for sc in scopes:
        for node in dc._walk_scope(sc):
            if isinstance(node, ast.For) and isinstance(node.iter, ast.Call) \
                    and dc._callee(node.iter) == ("name", "zip") \
                    and isinstance(node.iter.args[0], ast.Name) \
                    and node.iter.args[0].id == "SHARING":
                target = (sc, node.iter)
    assert target is not None, "the SHARING zip has moved"
    sc, it = target
    a = dc._len_token(it.args[0], sc, tree, sbind, {}, fns)
    b = dc._len_token(it.args[1], sc, tree, sbind, {}, fns)
    assert a is not None and a == b, (a, b)


def test_the_producer_may_live_in_a_sibling_module():
    """`test_v22.py:303` was the ONE site of the thirteen the intra-file
    analysis could not close, and its residual class named the wrong thing:
    the literal column was there and the length was provable -- the FUNCTION
    was in another file. `test_v22.py:45` is
    `from test_v20 import guest_eval_all, reason`."""
    tree, path = _tree_of("test_v22.py")
    local = dc._fn_index(tree)
    both = dc._fn_index(tree, path)
    assert "guest_eval_all" not in local
    assert dc._len_preserving_param(both["guest_eval_all"]) == "sources"


# --- 7.2 what the proof must REFUSE ----------------------------------------

_MOD = ('import sys\n'
        'sys.path.insert(0, "..")\n'
        'from whence.interp import Interpreter\n'
        '\n'
        'def run(src):\n'
        '    return Interpreter().run(src)\n'
        '\n'
        'CASES = ["let a = 1\\n", "let b = 2\\n", "let c = 3\\n"]\n')


def _residual_classes(rows):
    return sorted(r["cls"] for r in rows if r["kind"] == "residual")


def test_a_filtered_comprehension_is_not_length_preserving():
    src = "def f(xs):\n    return [g(x) for x in xs if x]\n"
    _t, fn = _fn(src, "f")
    assert dc._len_preserving_param(fn) is None


def test_an_append_under_an_if_is_a_filter_wearing_a_loops_clothes():
    src = ("def f(xs):\n    out = []\n    for x in xs:\n"
           "        if x:\n            out.append(x)\n    return out\n")
    _t, fn = _fn(src, "f")
    assert dc._len_preserving_param(fn) is None


def test_a_break_defeats_the_proof():
    src = ("def f(xs):\n    out = []\n    for x in xs:\n"
           "        out.append(x)\n        if x:\n            break\n"
           "    return out\n")
    _t, fn = _fn(src, "f")
    assert dc._len_preserving_param(fn) is None


def test_a_second_return_defeats_the_proof():
    """An early return is a path on which the accumulator is short, and this
    analysis does not reason about paths."""
    src = ("def f(xs):\n    out = []\n    if not xs:\n        return []\n"
           "    for x in xs:\n        out.append(x)\n    return out\n")
    _t, fn = _fn(src, "f")
    assert dc._len_preserving_param(fn) is None


def test_an_extend_on_the_accumulator_defeats_the_proof():
    """`append` adds exactly one per iteration; `extend` adds a length
    nobody has looked at."""
    src = ("def f(xs):\n    out = []\n    for x in xs:\n"
           "        out.append(x)\n        out.extend(x)\n    return out\n")
    _t, fn = _fn(src, "f")
    assert dc._len_preserving_param(fn) is None


def test_the_three_iteration_forms_are_accepted_and_a_slice_is_not():
    for it, want in (("xs", "xs"), ("enumerate(xs)", "xs"),
                     ("range(len(xs))", "xs"), ("xs[1:]", None),
                     ("sorted(set(xs))", None), ("zip(xs, xs)", None)):
        src = "def f(xs):\n    return [1 for _q in %s]\n" % it
        _t, fn = _fn(src, "f")
        assert dc._len_preserving_param(fn) == want, it


def test_an_unproven_second_column_binds_nothing_and_stays_residual():
    """Fail-closed in the over-approximation direction. `mystery()` is not a
    function this walk can see, so nothing about its length is known and the
    literal column is NOT harvested."""
    progs, stats = _harvest_source(
        _MOD + "def t():\n    for s, g in zip(CASES, mystery()):\n"
               "        run(s)\n", "zz_tmp_zip_unproven.py")
    assert progs == []
    assert _residual_classes(stats["rows"]) == ["zip_nonliteral_column"]


def test_two_literal_columns_truncate_and_the_third_element_is_not_claimed():
    """The exact hazard round 468 named, checked rather than assumed -- and
    it was ALREADY handled, by a path this round did not write. When BOTH
    columns are literal, `_literal_call` (round 468) evaluates the `zip`
    itself and truncation happens in real Python, so `let c = 3` is never
    claimed. Round 470's column analysis is not even reached here.

    Written expecting the opposite and left as the shape that taught it:
    the first version asserted that only the shorter column binds, which
    would have been the answer if the new code were the only code."""
    progs, stats = _harvest_source(
        _MOD + 'TWO = ["let x = 9\\n", "let y = 8\\n"]\n'
               "def t():\n    for s, u in zip(CASES, TWO):\n"
               "        run(s)\n        run(u)\n", "zz_tmp_zip_short.py")
    got = sorted(p["src"] for p in progs)
    assert got == ["let a = 1\n", "let b = 2\n",
                   "let x = 9\n", "let y = 8\n"], got
    assert "let c = 3\n" not in got, "zip truncation was over-approximated"
    assert _residual_classes(stats["rows"]) == []


def test_strict_true_is_what_reaches_the_new_column_analysis():
    """Why the `strict=True` case above is not a duplicate of the one before
    it: `_literal_call` refuses ANY call with keywords ("`sorted(xs, key=f)`
    is a call to `f`, and this walk has no `f`"), so `zip(A, B, strict=True)`
    falls through to round 470's branch. The two tests exercise two
    different code paths that happen to be spelled alike."""
    tree = ast.parse("zip(A, B, strict=True)")
    call = tree.body[0].value
    assert dc._literal(call, {"A": [[1]], "B": [[2]]}) is dc._NOLIT


def test_a_module_receiver_does_not_make_a_function_a_guest_runner():
    """Round 470, and it was found by this round's own test helper rather
    than by looking. `runners_in` had `and not mod_recv` on its
    `_SRC_ARG0_ATTRS` disjunct and NOT on its `_PARSE_CALLS` one, so
    `ast.parse(src)` made the enclosing function a runner of guest source
    and its argument a program. `_fn(src, name)` in this very file does
    exactly that: the file's `calls` went 1 -> 7, `runners` gained `_fn`,
    and the round-468 pin of 987 total calls went red on a change that had
    nothing to do with the harvester."""
    tree = ast.parse("import ast\n"
                     "def f(src):\n    return ast.parse(src)\n")
    assert dc.runners_in(tree) == {}
    tree = ast.parse("from whence.parser import parse\n"
                     "def f(src):\n    return parse(src)\n")
    assert "f" in dc.runners_in(tree)


def test_strict_true_binds_every_column_because_it_cannot_truncate():
    """`zip(..., strict=True)` raises on unequal length, so equality is the
    only outcome in which the loop body runs at all."""
    progs, _stats = _harvest_source(
        _MOD + 'TWO = ["let x = 9\\n", "let y = 8\\n"]\n'
               "def t():\n"
               "    for s, u in zip(CASES, TWO, strict=True):\n"
               "        run(s)\n        run(u)\n", "zz_tmp_zip_strict.py")
    got = sorted(p["src"] for p in progs)
    assert got == ["let a = 1\n", "let b = 2\n", "let c = 3\n",
                   "let x = 9\n", "let y = 8\n"], got


def test_a_starred_zip_argument_binds_nothing():
    progs, _stats = _harvest_source(
        _MOD + "def t():\n    for s, g in zip(*[CASES, CASES]):\n"
               "        run(s)\n", "zz_tmp_zip_star.py")
    assert progs == []


def test_a_target_of_the_wrong_arity_binds_nothing():
    """`for row in zip(A, B)` binds `row` to a TUPLE, not to a string, and
    this analysis has not looked at that shape."""
    progs, _stats = _harvest_source(
        _MOD + "def t():\n    for row in zip(CASES, CASES):\n"
               "        run(row[0])\n", "zz_tmp_zip_arity.py")
    assert progs == []


def test_an_aliased_import_is_not_resolved():
    """Fail-closed on the cross-file half: an alias is a name this walk
    cannot check against the sibling's definition without tracking the
    rename, so it does not try."""
    other = "def mk(xs):\n    return [x for x in xs]\n"
    path = os.path.join(HERE, "zz_tmp_sib.py")
    open(path, "w", encoding="utf-8").write(other)
    try:
        tree = ast.parse("from zz_tmp_sib import mk as maker\n")
        assert dc._fn_index(tree, os.path.join(HERE, "x.py")) == {}
        tree = ast.parse("from zz_tmp_sib import mk\n")
        idx = dc._fn_index(tree, os.path.join(HERE, "x.py"))
        assert dc._len_preserving_param(idx["mk"]) == "xs"
    finally:
        os.remove(path)
        dc._SIBLING_CACHE.clear()


def test_a_locally_shadowed_import_proves_nothing():
    """Two definitions of a name prove nothing about either, so the index
    maps it to `None` rather than picking one."""
    other = "def mk(xs):\n    return [x for x in xs]\n"
    path = os.path.join(HERE, "zz_tmp_sib2.py")
    open(path, "w", encoding="utf-8").write(other)
    try:
        tree = ast.parse("from zz_tmp_sib2 import mk\n"
                         "def mk(a, b):\n    return [1]\n")
        idx = dc._fn_index(tree, os.path.join(HERE, "x.py"))
        assert idx["mk"] is None
    finally:
        os.remove(path)
        dc._SIBLING_CACHE.clear()


# --- 7.3 the nested target, which was a separate defect --------------------

def test_a_two_level_table_target_now_destructures():
    """NOT a zip finding, and it is here because it was found by the same
    change. The old element binder was two levels of `isinstance` with
    `if not isinstance(t, ast.Name): continue` at the bottom, so
    `for site, (src, _) in sorted(TABLE.items())` bound `site` and silently
    dropped `src`. That is `test_v27.py:425`, the 14th residual row this
    round closed and the only one that is not a zip."""
    progs, _stats = _harvest_source(
        _MOD + 'TABLE = {"a": ("let a = 1\\n", 1), "b": ("let b = 2\\n", 2)}\n'
               "def t():\n"
               "    for site, (src, _n) in sorted(TABLE.items()):\n"
               "        run(src)\n", "zz_tmp_nested.py")
    assert sorted(p["src"] for p in progs) == ["let a = 1\n", "let b = 2\n"]


def test_the_nested_binder_refuses_a_shape_mismatch():
    """A 3-name target against 2-tuples binds nothing rather than binding
    what fits."""
    progs, _stats = _harvest_source(
        _MOD + 'TABLE = [("let a = 1\\n", 1), ("let b = 2\\n", 2)]\n'
               "def t():\n"
               "    for (src, _n, _extra) in TABLE:\n"
               "        run(src)\n", "zz_tmp_mismatch.py")
    assert progs == []


# --- 7.4 the classification, which was reporting the wrong reason ----------

def test_the_two_zip_classes_name_different_missing_things():
    """`zip_nonliteral_column` keeps round 468's spelling and round 468's
    meaning -- a literal column IS present, the length relation is not
    provable. `zip_no_literal_column` is the case round 468 never separated
    out: there is nothing to bind at all."""
    _p, s1 = _harvest_source(
        _MOD + "def t():\n    for s, g in zip(CASES, mystery()):\n"
               "        run(s)\n", "zz_tmp_cls1.py")
    _p, s2 = _harvest_source(
        _MOD + "def t():\n    for s, g in zip(mystery(), other()):\n"
               "        run(s)\n", "zz_tmp_cls2.py")
    assert _residual_classes(s1["rows"]) == ["zip_nonliteral_column"]
    assert _residual_classes(s2["rows"]) == ["zip_no_literal_column"]


def test_a_class_is_no_longer_earned_by_a_sibling_binding_of_the_same_name():
    """The defect this round found by reading the rows rather than the
    counters. `_unresolved_class` reported `zip_nonliteral_column` as soon
    as ANY binding of the name had a literal column, so `test_v30.py:307` --
    whose own zip is `zip(counts, guest_batch(counts, lib))`, no literal
    column anywhere in it -- carried a class earned by the loop seven lines
    above it. The class is now the union over the bindings, and a reader can
    see that the two are different."""
    _p, st = _harvest_source(
        _MOD + "def t():\n"
               "    for s, g in zip(mystery(), other()):\n"
               "        run(s)\n"
               "    for s, g in zip(more(), other()):\n"
               "        run(s)\n", "zz_tmp_union1.py")
    assert _residual_classes(st["rows"]) == ["zip_no_literal_column"] * 2
    _p, st = _harvest_source(
        _MOD + "def t():\n"
               "    for s, g in zip(CASES, mystery()):\n"
               "        run(s)\n"
               "    for s, g in zip(more(), other()):\n"
               "        run(s)\n", "zz_tmp_union2.py")
    # one name, two bindings, two different reasons -- both are reported
    assert _residual_classes(st["rows"]) == \
        ["zip_no_literal_column/zip_nonliteral_column"] * 2


# --- 7.5 the corpus, after ------------------------------------------------

def test_the_corpus_grew_and_no_zip_row_survives(harvest, harvest_rows):
    """Round 468: 765 programs, residual 114, of which 13 were zip rows.
    Round 470: the zip rows are gone from the live tree and the corpus is
    strictly larger. Bounds rather than pins, as the rest of this file does:
    the corpus is meant to grow."""
    _progs, stats = harvest
    assert stats["programs"] >= 829, stats["programs"]
    residual = stats["unresolved_args"] + stats["nonconstant_programs"]
    assert residual <= 100, residual
    assert not [r for r in harvest_rows
                if r["kind"] == "residual" and r["cls"].startswith("zip")]


def test_the_widening_did_not_move_the_other_residual_half(harvest):
    """`nonconstant_programs` is the half a zip row cannot be in --
    `_unresolved_class` is consulted only for a bare NAME. It was 58 at
    round 468 and a change to it would mean this round did something it did
    not intend."""
    _progs, stats = harvest
    assert stats["nonconstant_programs"] == 58, stats["nonconstant_programs"]


# --- 7.6 a class that outlived its own fix ---------------------------------

def test_a_comprehension_is_a_readable_form_and_no_longer_a_diagnosis():
    """Found by READING the rows, which is what round 468's next-step 1
    asked for and what no counter would have produced.

    `bound_by:comprehension` was minted when `_bind_iter` could not read a
    comprehension target. Round 468 taught it to -- and the class went on
    being reported, for `test_v29.py:375` and `:505`, whose comprehensions
    the binder reads perfectly well. What actually defeats those two is
    `CASES = build_cases()`, a table computed at import time. A reader who
    opened the file on the strength of the class would have gone looking at
    the wrong construct.

    The class is the only thing a reader ACTS on. This is the itemisation
    failing at the one job round 462 built it for, so it is a defect, not a
    coarseness."""
    src = ("import sys\n"
           "sys.path.insert(0, '..')\n"
           "from whence.interp import Interpreter\n"
           "def run(src):\n    return Interpreter().run(src)\n"
           "def build():\n    return ['let a = 1\\n']\n"
           "TABLE = build()\n"
           "def t():\n    return [run(s) for s in TABLE]\n")
    _progs, stats = _harvest_source(src, "zz_tmp_comp.py")
    assert _residual_classes(stats["rows"]) == \
        ["bound_nonconstant:call:build"], _residual_classes(stats["rows"])


def test_the_live_tree_no_longer_reports_a_form_the_binder_can_read(
        harvest_rows):
    """The same finding against the real tree: the two `test_v29.py` rows
    now name `build_cases`, and no row anywhere blames a construct the
    binder handles."""
    by = {}
    for r in harvest_rows:
        if r["kind"] == "residual":
            by[r["cls"]] = by.get(r["cls"], 0) + 1
    assert "bound_by:comprehension" not in by, by
    assert by.get("bound_nonconstant:call:build_cases") == 2, by


def test_the_residual_that_is_not_string_building_is_seven_rows_in_three_shapes(
        harvest_rows):
    """Round 468's reading was "what is left really is string-building over
    runtime values plus one written refusal". The refusal is gone (round 470
    refuted it) and the sentence needs the amendment this test pins: 93 of
    the 100 rows are string-building (`+`, `%`, `.join`) and SEVEN are not.

    The seven, read one by one:
      * 3 `bound_nonconstant:subscript` (`test_v27.py` :364/:376/:379) --
        `src, wording = GROWTH_SITES[site]` where `site` comes from
        `@pytest.mark.parametrize`. `GROWTH_SITES` folds (6 entries), so the
        blocker is parametrize, plus a subscript `_const_strs` has no branch
        for, plus a TUPLE-target assign `_bind` skips. Three widenings, not
        one.
      * 1 `bound_nonconstant:sequence` (`test_v27.py:175`) -- the same
        parametrize name `op`, and this one needs ONLY parametrize:
        `OTHER_SIDES` folds and `_const_strs` already reads the `+`/`%`.
      * 2 `bound_nonconstant:call:build_cases` (`test_v29.py`) -- a corpus
        computed at import time. Not reachable by any folder.
      * 1 `bound_nonconstant:name` (`test_miss_message_differential.py:574`)
        -- `for _, src in cases:` where `cases` is the enclosing function's
        own parameter, one link further out than the `forwarded` class
        reaches.

    `@pytest.mark.parametrize` is the one un-modelled ITERATION PROTOCOL
    left in this tree, and it is worth exactly one row on its own."""
    rows = [r for r in harvest_rows if r["kind"] == "residual"]
    building = [r for r in rows
                if "binop:" in r["cls"] or ".join" in r["cls"]]
    rest = [r for r in rows if r not in building]
    assert len(rows) == 100, len(rows)
    assert len(building) == 93, len(building)
    assert sorted(r["cls"] for r in rest) == [
        "bound_nonconstant:call:build_cases",
        "bound_nonconstant:call:build_cases",
        "bound_nonconstant:name",
        "bound_nonconstant:sequence",
        "bound_nonconstant:subscript",
        "bound_nonconstant:subscript",
        "bound_nonconstant:subscript",
    ], sorted(r["cls"] for r in rest)


# --- 7.7 what resolving a name COSTS, when the name has two bindings -------

def test_two_loops_one_name_and_the_second_loops_row_disappears_with_it():
    """A HAZARD THIS ROUND CREATED, pinned rather than left to be found.

    The harvester's environment is per-SCOPE, not per-BINDING: every value
    bound to a name anywhere in a function is folded into one set, and a
    runner call reading that name gets the union. That was inert while
    neither binding resolved. Resolving ONE of them makes the name resolve at
    BOTH call sites, so:

      * the second loop's residual row disappears, though nothing has
        learned to read the second loop; and
      * the first loop's programs are attributed to the second loop's LINE.

    Live at `test_v30.py`. `for (src, expected_host), g in zip(SHARING,
    guests)` at :299 now resolves; `for src, g in zip(counts,
    guest_batch(counts, lib))` at :306 does not and never will (`counts` is a
    filtered comprehension). After this round, `SHARING`'s two programs are
    stamped `test_v30.py:307` -- the second loop's `host(src)` -- and lines
    300 and 307 report no residual at all. The CORPUS is unharmed: those two
    programs are in it exactly once, and the `counts` loop's own programs
    reach it through the `AGREE` loop at :204. What is lost is the
    ATTRIBUTION and the row.

    Fixing it means per-binding environments -- knowing which `for` a name
    reaching a given call site came from -- which is a different data model
    from the one `harvest_file` has had since round 458. It is named here
    with its cost rather than papered over, and this test is what will go
    red if somebody builds it."""
    progs, stats = _harvest_source(
        _MOD + "def t():\n"
               "    for s in CASES:\n"
               "        run(s)\n"
               "    for s in [x for x in mystery() if x]:\n"
               "        run(s)\n", "zz_tmp_twoloops.py")
    lines = sorted(p["line"] for p in progs)
    assert len(progs) == 3, progs
    # both call sites see the same three strings; the second gets them as
    # duplicates, so the three land at whichever line the walk reached first
    assert len(set(lines)) == 1, lines
    # and NEITHER site is in the residual, though only one loop was read
    assert _residual_classes(stats["rows"]) == [], \
        "the unread loop still has a row -- the hazard may have been fixed"

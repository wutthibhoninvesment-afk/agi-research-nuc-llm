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
    assert residual <= 120, residual          # 166 at round 462, 114 now
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

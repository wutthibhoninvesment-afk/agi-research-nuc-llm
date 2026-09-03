"""Round 469 (harness A) — tests for `harness/whenceslow.py`.

One test per rule and one per finding, in the order the module docstring
states them. Every test that needs a tree builds a synthetic one in
`tmp_path`; nothing here shells out to pytest, so the file belongs in the
fast tier (it is not a `test_swe_*.py`, so `conftest.py` puts it there with
no registry edit — round 235's self-maintenance property).

The last section pins what round 469 MEASURED about the real tree. Those are
the tests that go red when the tier changes shape, which is the event the
module exists to notice.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import whenceslow as W                                       # noqa: E402


# --------------------------------------------------------------- fixtures --

def _write(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


MARKED = "import pytest\n\n\n@pytest.mark.whence_slow\ndef test_%s():\n    assert True\n"


@pytest.fixture
def tree(tmp_path):
    """A miniature `languages/whence` with both halves and a real
    cross-import: `test_b` imports `test_a`, `test_c` imports nothing."""
    r = str(tmp_path / "whence")
    _write(os.path.join(r, "pytest.ini"), "[pytest]\n")
    _write(os.path.join(r, "run.py"), "print('run')\n")
    _write(os.path.join(r, "whence", "interp.py"), "X = 1\n")
    _write(os.path.join(r, "examples", "self_eval.lang"), "let x = 1\n")
    _write(os.path.join(r, "tests", "__init__.py"), "")
    _write(os.path.join(r, "tests", "conftest.py"), "# marker registration\n")
    _write(os.path.join(r, "tests", "test_a.py"), MARKED % "a")
    _write(os.path.join(r, "tests", "test_b.py"),
           "from test_a import test_a as _helper\n" + MARKED % "b")
    _write(os.path.join(r, "tests", "test_c.py"), MARKED % "c")
    _write(os.path.join(r, "tests", "test_plain.py"),
           "def test_plain():\n    assert True\n")
    return r


def _entry(unit, root, outcome="passed", **kw):
    e = {
        "unit": unit, "file": unit, "outcome": outcome, "completed": True,
        "returncode": 0 if outcome == "passed" else 1, "seconds": 1.0,
        "finished_at": 100.0,
        "subject_digest": W.subject_digest(root),
        "subject_digest_after": W.subject_digest(root),
        "subject_stable": True,
        "dep_digests": W.dep_digests(unit, root),
        "deps_stable": True, "schema": 1, "tail": "",
    }
    e.update(kw)
    return e


# ------------------------------------------------- the collapsed-tree split --

def test_subject_digest_excludes_the_tests_directory(tree):
    """The decision the whole module rests on. If `tests/` were inside the
    subject digest, any language round editing any test file would invalidate
    every unit at once and the ledger could never accumulate."""
    before = W.subject_digest(tree)
    _write(os.path.join(tree, "tests", "test_c.py"), MARKED % "c_edited")
    assert W.subject_digest(tree) == before


def test_subject_digest_moves_on_an_interpreter_edit(tree):
    before = W.subject_digest(tree)
    _write(os.path.join(tree, "whence", "interp.py"), "X = 2\n")
    assert W.subject_digest(tree) != before


def test_subject_digest_moves_on_a_lang_edit(tree):
    """Round 361's `.lang` rule, which bites harder here: the guest
    interpreter this tier tests is written in Whence, not Python."""
    before = W.subject_digest(tree)
    _write(os.path.join(tree, "examples", "self_eval.lang"), "let x = 2\n")
    assert W.subject_digest(tree) != before


def test_subject_digest_ignores_regenerated_directories(tree):
    before = W.subject_digest(tree)
    _write(os.path.join(tree, "whence", "__pycache__", "interp.cpython-312.pyc"),
           "junk")
    assert W.subject_digest(tree) == before


# ----------------------------------------------------------- AST discovery --

def test_marked_tests_ignores_a_marker_named_in_prose(tree):
    """The 104-vs-102 finding. `test_tiering.py`'s module docstring says
    `@pytest.mark.whence_slow` twice; grep counts both as members."""
    p = os.path.join(tree, "tests", "test_prose.py")
    _write(p, '"""This file explains @pytest.mark.whence_slow twice:\n'
              '@pytest.mark.whence_slow is the marker."""\n\n'
              'def test_prose():\n    assert True\n')
    assert W.marked_tests(p) == []
    assert "test_prose.py" not in [u["id"] for u in W.slow_tier_units(tree)]


def test_marked_tests_is_none_for_an_unparsable_file_and_the_unit_errors(tree):
    p = os.path.join(tree, "tests", "test_broken.py")
    _write(p, "def test_(:\n")
    assert W.marked_tests(p) is None
    row = [u for u in W.slow_tier_units(tree) if u["id"] == "test_broken.py"]
    assert row and row[0]["registry_error"]


def test_a_class_level_marker_is_seen(tree):
    p = os.path.join(tree, "tests", "test_cls.py")
    _write(p, "import pytest\n\n\n@pytest.mark.whence_slow\nclass TestX:\n"
              "    def test_inner(self):\n        assert True\n")
    assert W.marked_tests(p) == ["TestX"]


def test_a_file_with_no_marks_is_not_a_unit(tree):
    assert "test_plain.py" not in [u["id"] for u in W.slow_tier_units(tree)]


# ---------------------------------------------------------- the dep closure --

def test_dep_closure_is_transitive(tmp_path):
    r = str(tmp_path / "w")
    _write(os.path.join(r, "pytest.ini"), "[pytest]\n")
    _write(os.path.join(r, "tests", "__init__.py"), "")
    _write(os.path.join(r, "tests", "conftest.py"), "")
    _write(os.path.join(r, "tests", "test_a.py"), MARKED % "a")
    _write(os.path.join(r, "tests", "test_b.py"),
           "from test_a import test_a\n" + MARKED % "b")
    _write(os.path.join(r, "tests", "test_c.py"),
           "from test_b import test_b\n" + MARKED % "c")
    got = W.dep_closure("test_c.py", r)
    assert "tests/test_a.py" in got, "depth-2 import dropped: fail-OPEN"
    assert "tests/test_b.py" in got and "tests/test_c.py" in got


def test_dep_closure_handles_the_dotted_tests_spelling(tmp_path):
    """`test_v38.py` in the real tree spells it `from tests.test_x import`."""
    r = str(tmp_path / "w")
    _write(os.path.join(r, "tests", "test_x.py"), MARKED % "x")
    _write(os.path.join(r, "tests", "test_y.py"),
           "from tests.test_x import test_x\n" + MARKED % "y")
    assert "tests/test_x.py" in W.dep_closure("test_y.py", r)


def test_dep_closure_always_includes_conftest_and_pytest_ini(tree):
    got = W.dep_closure("test_c.py", tree)
    assert "tests/conftest.py" in got
    assert "pytest.ini" in got, "round 349: this file decides whether the " \
                                "suite collects at all"


def test_dep_closure_drops_subject_imports(tmp_path):
    """`from whence.interp import ...` is subject-half and is covered by
    `subject_digest`; putting it in the deps would double-count it."""
    r = str(tmp_path / "w")
    _write(os.path.join(r, "tests", "test_z.py"),
           "from whence.interp import X\nimport json\n" + MARKED % "z")
    got = W.dep_closure("test_z.py", r)
    assert not [g for g in got if "interp" in g or "json" in g]


def test_dep_closure_terminates_on_a_cycle(tmp_path):
    r = str(tmp_path / "w")
    _write(os.path.join(r, "tests", "test_p.py"),
           "from test_q import test_q\n" + MARKED % "p")
    _write(os.path.join(r, "tests", "test_q.py"),
           "from test_p import test_p\n" + MARKED % "q")
    assert "tests/test_q.py" in W.dep_closure("test_p.py", r)


# ------------------------------------------------- the fail-closed rules 1-5 --

def test_rule1_a_unit_with_no_entry_is_unknown(tree):
    st = W.status(ledger_path=os.path.join(tree, "none.jsonl"), root=tree)
    assert st["n_units"] == 3
    assert all(r["state"] == "unknown" for r in st["rows"])
    assert st["coverage"] == 0.0


def test_rule2_a_subject_edit_makes_an_entry_stale(tree):
    e = _entry("test_c.py", tree)
    _write(os.path.join(tree, "whence", "interp.py"), "X = 99\n")
    st = W.status(root=tree, entries=[e])
    row = [r for r in st["rows"] if r["unit"] == "test_c.py"][0]
    assert row["state"] == "stale_subject"


def test_rule3_a_dep_edit_stales_the_unit_and_names_the_file(tree):
    e = _entry("test_c.py", tree)
    _write(os.path.join(tree, "tests", "test_c.py"), MARKED % "c2")
    st = W.status(root=tree, entries=[e])
    row = [r for r in st["rows"] if r["unit"] == "test_c.py"][0]
    assert row["state"] == "stale_deps"
    assert row["moved_deps"] == ["tests/test_c.py"], \
        "round 341's rule: name the file that moved, do not count it"


def test_an_edit_to_an_UNRELATED_test_file_leaves_a_unit_fresh(tree):
    """The recall this module buys. Under a whole-tree digest this unit would
    read `stale_checkout`."""
    e = _entry("test_c.py", tree)
    _write(os.path.join(tree, "tests", "test_a.py"), MARKED % "a2")
    st = W.status(root=tree, entries=[e])
    row = [r for r in st["rows"] if r["unit"] == "test_c.py"][0]
    assert row["state"] == "fresh_pass"


def test_an_edit_to_an_IMPORTED_test_file_stales_the_importer(tree):
    """And the fail-closed half of the same trade: `test_b` imports
    `test_a`, so editing `test_a` must not leave `test_b` green."""
    e = _entry("test_b.py", tree)
    _write(os.path.join(tree, "tests", "test_a.py"), MARKED % "a2")
    st = W.status(root=tree, entries=[e])
    row = [r for r in st["rows"] if r["unit"] == "test_b.py"][0]
    assert row["state"] == "stale_deps"
    assert row["moved_deps"] == ["tests/test_a.py"]


def test_rule4_a_subject_race_is_never_evidence(tree):
    e = _entry("test_c.py", tree, subject_stable=False)
    st = W.status(root=tree, entries=[e])
    assert [r for r in st["rows"] if r["unit"] == "test_c.py"][0]["state"] == "raced"


def test_rule4_a_dep_race_is_never_evidence(tree):
    e = _entry("test_c.py", tree, deps_stable=False)
    st = W.status(root=tree, entries=[e])
    assert [r for r in st["rows"] if r["unit"] == "test_c.py"][0]["state"] == "raced"


def test_rule5_an_incomplete_run_narrows_nothing(tree):
    for rc, outcome in ((-9, "timeout"), (2, "error"), (3, "error")):
        e = _entry("test_c.py", tree, outcome=outcome, returncode=rc,
                   completed=False)
        st = W.status(root=tree, entries=[e])
        row = [r for r in st["rows"] if r["unit"] == "test_c.py"][0]
        assert row["state"] == "incomplete", rc


def test_returncode_5_is_not_a_pass(tree):
    """`5` is pytest for "nothing collected". For a unit DEFINED by its
    marked tests, collecting nothing means the marks moved — the one reading
    it must never get is `passed`."""
    assert 5 not in W._COMPLETED_RETURNCODES
    e = _entry("test_c.py", tree, outcome="error", returncode=5,
               completed=False)
    st = W.status(root=tree, entries=[e])
    assert [r for r in st["rows"] if r["unit"] == "test_c.py"][0]["state"] == "incomplete"


def test_an_unstamped_entry_is_not_fresh(tree):
    e = _entry("test_c.py", tree, dep_digests=None)
    st = W.status(root=tree, entries=[e])
    assert [r for r in st["rows"] if r["unit"] == "test_c.py"][0]["state"] == "unstamped"


def test_a_unit_never_inherits_another_units_pass(tree):
    """`slowtier` has an inheritance rule because a whole-file run is a
    superset of a sub-unit's. Here no unit's run is a superset of another's,
    so inheriting would be inventing coverage."""
    st = W.status(root=tree, entries=[_entry("test_a.py", tree)])
    by = dict((r["unit"], r["state"]) for r in st["rows"])
    assert by["test_a.py"] == "fresh_pass"
    assert by["test_b.py"] == "unknown" and by["test_c.py"] == "unknown"


# ------------------------------------------------------------- status/report --

def test_status_reports_its_own_recall(tree):
    st = W.status(root=tree, entries=[_entry("test_a.py", tree)])
    assert st["n_conclusive"] == 1 and st["n_units"] == 3
    assert abs(st["coverage"] - 1.0 / 3) < 1e-9
    assert "33% recall" in W.report_text(st)


def test_a_fresh_failure_is_counted_as_failing(tree):
    st = W.status(root=tree, entries=[_entry("test_a.py", tree,
                                             outcome="failed", returncode=1)])
    assert st["n_failing"] == 1
    assert st["n_conclusive"] == 1, "a fresh red IS evidence about this tree"


def test_a_stale_red_is_reported_but_not_counted_as_failing(tree):
    """Round 385's rule, ported. `stale_subject` on a row whose last run was
    red reads exactly like a stale pass unless something says otherwise."""
    e = _entry("test_a.py", tree, outcome="failed", returncode=1)
    _write(os.path.join(tree, "whence", "interp.py"), "X = 3\n")
    st = W.status(root=tree, entries=[e])
    assert st["n_failing"] == 0 and st["n_recorded_failing_stale"] == 1
    assert "LAST RAN RED" in W.report_text(st)


def test_report_text_names_moved_deps_rather_than_counting_them(tree):
    e = _entry("test_b.py", tree)
    _write(os.path.join(tree, "tests", "test_a.py"), MARKED % "a2")
    assert "tests/test_a.py" in W.report_text(W.status(root=tree, entries=[e]))


# --------------------------------------------------------------- reconcile --

def test_reconcile_flags_a_file_pytest_sees_and_the_ast_does_not(tree):
    units = W.slow_tier_units(tree)
    merged = W.reconcile(units, {"test_hidden.py": ["tests/test_hidden.py::test_h"]})
    row = [u for u in merged if u["id"] == "test_hidden.py"][0]
    assert row["registry_error"]


def test_a_registry_error_unit_can_never_be_conclusive(tree):
    """Fail-closed: an unseen unit joins the DENOMINATOR, it does not sit
    outside the tier where nobody counts it."""
    e = _entry("test_hidden.py", tree)
    e["dep_digests"] = W.dep_digests("test_hidden.py", tree)
    st = W.status(root=tree, entries=[e],
                  collected={"test_hidden.py": ["tests/test_hidden.py::test_h"]})
    row = [r for r in st["rows"] if r["unit"] == "test_hidden.py"][0]
    assert row["state"] == "registry_error"
    assert st["n_conclusive"] == 0 and st["n_units"] == 4


def test_reconcile_leaves_a_parametrize_expansion_alone(tree):
    """AST 2 / pytest 3 on the real `test_v10.py` is a parametrized node, not
    a missed member: the unit runs `-m whence_slow tests/test_v10.py` and
    gets all three either way."""
    units = W.slow_tier_units(tree)
    merged = W.reconcile(units, {"test_a.py": ["x::test_a[1]", "x::test_a[2]"]})
    assert not [u for u in merged if u["registry_error"]]


def test_collect_units_parses_pytest_collect_output():
    text = ("tests/test_v10.py::test_three_way[meta.lang]\n"
            "tests/test_v10.py::test_three_way[self_eval.lang]\n"
            "tests/test_v29.py::test_x\n\n"
            "103/2552 tests collected (2449 deselected) in 0.40s\n")
    got = W.collect_units(runner=lambda argv: text)
    assert sorted(got) == ["test_v10.py", "test_v29.py"]
    assert len(got["test_v10.py"]) == 2


# -------------------------------------------------------------------- plan --

def _rows(*specs):
    return {"rows": [dict(unit=u, file=u, state=s, finished_at=f, seconds=sec,
                          outcome=o)
                     for (u, s, f, sec, o) in specs]}


def test_plan_puts_never_measured_units_first():
    st = _rows(("a.py", "fresh_pass", 500.0, 10.0, "passed"),
               ("b.py", "unknown", 0, None, None))
    assert W.plan(st, 1000.0, default_s=10.0)[0] == "b.py"


def test_plan_re_runs_a_last_red_unit_before_an_unknown():
    st = _rows(("red.py", "stale_subject", 500.0, 10.0, "failed"),
               ("new.py", "unknown", 0, None, None))
    assert W.plan(st, 1000.0, default_s=10.0)[0] == "red.py"


def test_plan_stays_inside_its_budget():
    st = _rows(("a.py", "unknown", 0, 30.0, None),
               ("b.py", "unknown", 0, 30.0, None),
               ("c.py", "unknown", 0, 30.0, None))
    assert len(W.plan(st, 70.0, default_s=30.0)) == 2


def test_plan_returns_an_oversized_unit_alone_rather_than_truncating():
    """The silent-truncation rule. A unit slower than every budget must still
    be reachable, or the tier's most expensive units become the exact ones
    that can never be evidence."""
    st = _rows(("huge.py", "unknown", 0, 5000.0, None))
    assert W.plan(st, 60.0) == ["huge.py"]


def test_plan_default_is_smaller_than_slowtiers():
    """120 s, not 300: this tier's recorded rate is 5.4-7.3 s per marked test
    and the median unit holds 2. At 300 the planner would refuse a second
    unmeasured unit inside any budget a round grants."""
    import inspect
    assert inspect.signature(W.plan).parameters["default_s"].default == 120.0


# --------------------------------------------------------------- run_slice --

def test_run_slice_writes_one_stamped_entry_per_unit(tree, tmp_path):
    led = str(tmp_path / "l.jsonl")
    W.run_slice(["test_a.py", "test_c.py"], ledger_path=led, root=tree,
                runner=lambda u: {"returncode": 0, "timed_out": False,
                                  "tail": "1 passed"})
    got = W.read_entries(led)
    assert [e["unit"] for e in got] == ["test_a.py", "test_c.py"]
    for e in got:
        assert e["subject_stable"] and e["deps_stable"] and e["completed"]
        assert e["outcome"] == "passed" and e["dep_digests"]


def test_run_slice_stamps_a_mid_run_subject_move_as_raced(tree, tmp_path):
    led = str(tmp_path / "l.jsonl")

    def runner(unit):
        _write(os.path.join(tree, "whence", "interp.py"), "X = 42\n")
        return {"returncode": 0, "timed_out": False, "tail": ""}

    W.run_slice(["test_a.py"], ledger_path=led, root=tree, runner=runner)
    e = W.read_entries(led)[0]
    assert e["subject_stable"] is False
    assert W.classify(e, W.subject_digest(tree)) == "raced"


def test_run_slice_stamps_a_mid_run_dep_move_as_raced(tree, tmp_path):
    led = str(tmp_path / "l.jsonl")

    def runner(unit):
        _write(os.path.join(tree, "tests", "test_a.py"), MARKED % "a3")
        return {"returncode": 0, "timed_out": False, "tail": ""}

    W.run_slice(["test_a.py"], ledger_path=led, root=tree, runner=runner)
    assert W.read_entries(led)[0]["deps_stable"] is False


def test_run_slice_records_a_timeout_as_incomplete(tree, tmp_path):
    led = str(tmp_path / "l.jsonl")
    W.run_slice(["test_a.py"], ledger_path=led, root=tree,
                runner=lambda u: {"returncode": -9, "timed_out": True,
                                  "tail": ""})
    e = W.read_entries(led)[0]
    assert e["outcome"] == "timeout" and e["completed"] is False


def test_the_ledger_reader_survives_a_torn_line(tmp_path):
    led = str(tmp_path / "l.jsonl")
    with open(led, "w") as f:
        f.write(json.dumps({"unit": "a.py"}) + "\n")
        f.write('{"unit": "b.p')
    assert [e["unit"] for e in W.read_entries(led)] == ["a.py"]


def test_latest_by_unit_takes_the_newest(tmp_path, tree):
    old = _entry("test_a.py", tree, finished_at=1.0, outcome="failed",
                 returncode=1)
    new = _entry("test_a.py", tree, finished_at=2.0)
    st = W.status(root=tree, entries=[old, new])
    assert [r for r in st["rows"] if r["unit"] == "test_a.py"][0]["outcome"] \
        == "passed"


# ------------------------------------------------------------- the command --

def test_the_unit_command_runs_only_the_marked_tests():
    argv = W.unit_argv("test_v29.py", python="py")
    # `-m` appears TWICE — `python -m pytest` and pytest's own marker flag —
    # so this indexes the LAST one. The first version of this test indexed
    # the first and asserted the marker was "pytest".
    last_m = len(argv) - 1 - argv[::-1].index("-m")
    assert argv[last_m + 1] == "whence_slow", argv
    assert argv[-1] == "tests/test_v29.py"


def test_the_unit_command_pins_pytest_ini():
    """Round 349: without `-c pytest.ini` pytest parses the untracked gateway
    `pyproject.toml` and the whole suite fails to collect."""
    argv = W.unit_argv("test_v29.py", python="py")
    assert argv[argv.index("-c") + 1] == "pytest.ini"


# ------------------------------------- what round 469 measured at this HEAD --

def test_the_real_tree_yields_the_units_round_469_measured():
    """Round 469 measured 27 units / 102 marked nodes. Round 470 added ONE
    unit — `test_testcorpus_suite_census.py`, 11 marked tests, the suite-mode
    `--tests` census round 469's §5 decided belongs in its own file — and
    that unit is what moved these numbers. Re-pinned WITH the reason rather
    than relaxed to an inequality: the point of this assertion is that a
    change to the tier's membership is a thing somebody had to write down.

    Round 474 (language C) added ONE marked test to that same unit --
    `test_testcorpus_suite_census.py` went 11 -> 12, which round 474's own
    state entry records -- so the tier's marked-node total went 113 -> 114
    with the unit COUNT unchanged at 28. Re-pinned again by round 475
    (harness A), which is also the round that found it: this assertion was
    red for a full round because round 474 ran the harness fast tier and
    published no number from it, so nothing read the failure. Membership is
    still written down; what was missing was somebody looking."""
    units = W.slow_tier_units()
    assert len(units) == 28
    assert sum(len(u["tests"]) for u in units) == 114
    assert not [u for u in units if u["registry_error"]]
    by = dict((u["id"], u) for u in units)
    assert len(by["test_testcorpus_suite_census.py"]["tests"]) == 12


def test_a_module_level_pytestmark_is_discovered(tmp_path):
    """Round 470's fail-open, pinned. `pytestmark = pytest.mark.whence_slow`
    is the ordinary pytest spelling for "the whole file is in this tier", and
    the AST scan read DECORATORS only. `pytest -m whence_slow` collected the
    file's tests; `slow_tier_units()` reported the tier unchanged; the unit
    would have been scheduled never and its 0% would have been invisible
    inside a 100%.

    A tier that discovers membership by one spelling of a two-spelling
    construct silently loses units, which is the failure round 469 built this
    module to make impossible."""
    f = tmp_path / "test_whole.py"
    f.write_text("import pytest\n"
                 "pytestmark = pytest.mark.whence_slow\n"
                 "def test_a():\n    pass\n"
                 "def test_b():\n    pass\n"
                 "def helper():\n    pass\n")
    assert W.marked_tests(str(f)) == ["test_a", "test_b"]


def test_the_three_pytestmark_spellings_pytest_accepts_are_all_read():
    """A bare mark, a list and a tuple. pytest accepts all three; a scan that
    read only the bare form would lose a file that also carries `slow`."""
    import ast as _ast
    for body in ("pytest.mark.whence_slow",
                 "[pytest.mark.whence_slow]",
                 "(pytest.mark.usefixtures('x'), pytest.mark.whence_slow)"):
        tree = _ast.parse("pytestmark = %s\n" % body)
        assert W._module_marked(tree) is True, body
    for body in ("pytest.mark.slow", "[]", "None"):
        tree = _ast.parse("pytestmark = %s\n" % body)
        assert W._module_marked(tree) is False, body


def test_a_module_pytestmark_does_not_mark_non_test_functions(tmp_path):
    """`pytestmark` applies to the file's TESTS. A module-level helper is not
    a test and must not appear in a unit's named membership, or the unit's
    count stops matching what pytest collects — which is the one cross-check
    `verify` has."""
    f = tmp_path / "test_helpers.py"
    f.write_text("import pytest\n"
                 "pytestmark = pytest.mark.whence_slow\n"
                 "def make_thing():\n    pass\n"
                 "def test_only_this():\n    pass\n")
    assert W.marked_tests(str(f)) == ["test_only_this"]


def test_a_decorated_test_in_a_pytestmark_file_is_not_counted_twice(tmp_path):
    """Belt and braces is a legal thing for an author to write and must not
    inflate the denominator."""
    f = tmp_path / "test_both.py"
    f.write_text("import pytest\n"
                 "pytestmark = pytest.mark.whence_slow\n"
                 "@pytest.mark.whence_slow\n"
                 "def test_a():\n    pass\n")
    assert W.marked_tests(str(f)) == ["test_a"]


def test_test_tiering_is_not_a_unit_despite_two_grep_hits():
    """The finding this file exists to keep: `grep -c` says this tier has 28
    files and 104 members. Two of the hits are inside `test_tiering.py`'s own
    module docstring, and that file has no marked test at all."""
    src = open(os.path.join(W.tests_dir(), "test_tiering.py"),
               encoding="utf-8").read()
    assert src.count("@pytest.mark.whence_slow") == 2
    assert W.marked_tests(os.path.join(W.tests_dir(), "test_tiering.py")) == []


def test_the_real_cross_import_chain_is_in_the_closure():
    """`test_v11` -> `test_v10` -> `test_v09`, measured round 469. If this
    goes red the closure has stopped being transitive on the real tree and
    six units are silently fail-open."""
    got = W.dep_closure("test_v11.py")
    assert "tests/test_v10.py" in got and "tests/test_v09.py" in got


def test_the_biggest_units_are_the_ones_round_469_named():
    by = dict((u["id"], len(u["tests"])) for u in W.slow_tier_units())
    assert by["test_self_hosting.py"] == 12
    assert by["test_self_eval.py"] == 11
    assert by["test_polarity.py"] == 10


# ------------------------------------------------------------------ replay --

CLOSURES = {"a.py": {"tests/a.py"},
            "b.py": {"tests/b.py", "tests/a.py"},
            "c.py": {"tests/c.py"}}


def test_a_subject_commit_invalidates_every_unit():
    got = W.commit_invalidations([["whence/interp.py"]], CLOSURES)
    assert got == [set(CLOSURES)]


def test_a_tests_only_commit_invalidates_only_the_importers():
    """The recall the split buys, stated as the replay sees it: editing
    `tests/a.py` takes out `a.py` and `b.py` (which imports it) and leaves
    `c.py` alone."""
    got = W.commit_invalidations([["tests/a.py"]], CLOSURES)
    assert got == [{"a.py", "b.py"}]


def test_a_docs_only_commit_invalidates_nothing():
    assert W.commit_invalidations([["SPEC.md", "CHANGELOG.md"]], CLOSURES) == [set()]


def test_a_lang_example_edit_is_a_subject_commit():
    """Round 361's rule: `examples/self_eval.lang` is the guest interpreter,
    not documentation."""
    assert W.commit_invalidations([["examples/self_eval.lang"]], CLOSURES) \
        == [set(CLOSURES)]


def test_replay_reaches_full_coverage_when_nothing_invalidates():
    costs = {"a.py": 1.0, "b.py": 1.0, "c.py": 1.0}
    r = W.replay(costs, [set(), set(), set()], 10.0)
    assert r["final"] == 1.0


def test_replay_recall_is_monotone_in_the_budget():
    """The property that makes the number usable for pricing: a bigger budget
    can never buy less recall."""
    costs = {"a.py": 10.0, "b.py": 40.0, "c.py": 100.0}
    inval = [set(costs), set(), {"a.py"}, set(costs), set()]
    means = [W.replay(costs, inval, b)["mean"] for b in (10, 60, 200, 1000)]
    assert means == sorted(means), means


def test_replay_never_overspends_its_budget():
    """Three 10 s units against a 15 s budget buys ONE of them, not two: the
    planner skips a unit that would cross the budget rather than allowing a
    last one over. The only exception is the first pick (see the test
    below)."""
    costs = {"a.py": 10.0, "b.py": 10.0, "c.py": 10.0}
    r = W.replay(costs, [set(costs)], 15.0)
    assert r["spent_s"] == [10.0] and r["series"] == [1.0 / 3]


def test_replay_always_makes_progress_even_on_an_oversized_unit():
    """The no-silent-truncation rule again: a unit costing more than the whole
    budget must still be reachable, or the tier's most expensive units are the
    ones that can never become evidence."""
    r = W.replay({"huge.py": 5000.0}, [{"huge.py"}], 60.0)
    assert r["final"] == 1.0 and r["spent_s"] == [5000.0]


def test_replay_uses_the_default_for_a_unit_with_no_measurement():
    r = W.replay({"a.py": 1.0}, [set()], 10.0, default_s=999.0,
                 units=["a.py", "unmeasured.py"])
    assert r["final"] == 0.5, "the unmeasured unit must not fit in 10s"


def test_group_by_round_merges_a_rounds_commits_into_one_change_set():
    """The driver runs ONE slice per round and a round commits several times.
    Replaying one slice per COMMIT hands the planner one budget per commit and
    overstates recall by the mean commits-per-round."""
    commits = [["a"], ["b"], ["c"], ["d"]]
    subjects = ["round 468 (language C), part 1", "round 468, part 2",
                "round 469 (harness A): x", "round 469: y"]
    groups, tags = W.group_by_round(commits, subjects)
    assert groups == [["a", "b"], ["c", "d"]]
    assert tags == ["468", "469"]


def test_an_untagged_commit_joins_the_round_before_it():
    """A driver ledger append names no round; it happened inside the window of
    the round before it, so it must not open a new slice of its own."""
    groups, _ = W.group_by_round(
        [["a"], ["b"]],
        ["round 468 (language C)", "driver: slow-tier ledger append"])
    assert groups == [["a", "b"]]

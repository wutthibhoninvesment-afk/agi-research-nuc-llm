"""Round 503 (SWE-loop D): scope reachability, and the stratified kill rate.

The claim under test: a mutation campaign that reports ONE pooled kill rate
over a scope containing code nothing outside the tests reaches is not
reporting a property of the subject. `swe/scopecall.py` is the runnable form
of the question round 502 answered by hand for `classify_bucket`.

Two `TestThisTree` cases read the live repo on purpose. Everything else is a
synthetic tree in `tmp_path`.
"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swe.scopecall as SC  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _tree(tmp_path, files):
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body).lstrip("\n"))
    return str(tmp_path)


# ------------------------------------------------------------------ def scan

def test_defs_in_names_methods_by_qualname():
    defs = SC.defs_in("class C:\n    def m(self):\n        pass\n")
    assert [d.qualname for d in defs] == ["C", "C.m"]


def test_a_defs_span_starts_at_its_first_decorator_not_at_the_def():
    """A decorator is a mutation site one line above the keyword. Attributing
    it to module level would put the wrong name on the finding -- the same
    rule round 502's `survivor_impact.enclosing_defs` needed."""
    src = "@one\n@two\ndef f():\n    pass\n"
    d = SC.defs_in(src)[0]
    assert (d.lineno, d.body_lineno, d.end_lineno) == (1, 3, 4)
    assert d.covers(1) and d.covers(2)


def test_innermost_prefers_the_narrower_span():
    defs = SC.defs_in("class C:\n    def m(self):\n        return 1\n")
    assert SC.innermost(defs, 3).qualname == "C.m"
    assert SC.innermost(defs, 1).qualname == "C"
    assert SC.innermost(SC.defs_in("x = 1\n"), 1) is None


def test_nested_functions_get_a_dotted_qualname():
    defs = SC.defs_in("def outer():\n    def inner():\n        pass\n")
    assert [d.qualname for d in defs] == ["outer", "outer.inner"]


# ------------------------------------------------------------ reference scan

def _kinds(src, name):
    return sorted(set(k for n, _, k in SC.scan_references(src) if n == name))


def test_a_call_is_a_call_and_a_bare_load_is_a_name():
    assert _kinds("foo()\n", "foo") == ["call"]
    assert _kinds("bar = foo\n", "foo") == ["name"]


def test_an_attribute_call_counts_by_its_attribute_name():
    assert _kinds("m.foo()\n", "foo") == ["call"]


def test_an_identifier_inside_a_runtime_string_is_a_reference():
    """`getattr(m, "foo")` is a call site. A name scan that only looked at
    syntax would call `foo` dead."""
    assert _kinds('getattr(m, "foo")\n', "foo") == ["string"]
    assert _kinds('getattr(m, "foo")\n', "getattr") == ["call"]


def test_a_docstring_mention_is_collected_and_is_not_a_reference():
    src = '"""see foo for details."""\nx = 1\n'
    assert _kinds(src, "foo") == ["docstring"]
    assert "docstring" in SC.INERT_KINDS


def test_a_comment_mention_is_collected_and_is_not_a_reference():
    assert _kinds("# calls foo\nx = 1\n", "foo") == ["comment"]
    assert "comment" in SC.INERT_KINDS


def test_a_functions_own_docstring_is_a_docstring_not_a_string():
    src = 'def f():\n    """mentions foo."""\n    return 1\n'
    assert _kinds(src, "foo") == ["docstring"]


def test_a_multiline_docstring_is_docstring_on_every_one_of_its_lines():
    """The line number decides the kind, so a mention on line 4 of a docstring
    must not fall through to `string`."""
    src = 'def f():\n    """a\n    b\n    foo\n    """\n    return 1\n'
    assert _kinds(src, "foo") == ["docstring"]


# ------------------------------------------------------- constructed names

@pytest.mark.parametrize("expr,expected", [
    ('getattr(self, "_stmt_" + kind)', "_stmt_"),
    ('getattr(self, "_stmt_%s" % kind)', "_stmt_"),
    ('getattr(self, "_stmt_{}".format(kind))', "_stmt_"),
    ('getattr(self, f"_stmt_{kind}")', "_stmt_"),
])
def test_every_way_of_building_a_name_yields_the_same_prefix(expr, expected):
    got = [p for p, _ in SC._dynamic_prefixes(SC.ast.parse(expr))]
    assert expected in got


def test_a_prefix_that_is_not_identifier_shaped_is_not_a_prefix():
    assert SC._prefix_of("%s_tail") is None
    assert SC._prefix_of("some words here") is None
    assert SC._prefix_of("") is None


def test_a_prefix_shorter_than_the_floor_is_refused():
    """A prefix of `_` would vouch for every private def in the tree, which
    is not conservatism, it is silence."""
    assert SC.MIN_DYNAMIC_PREFIX == 3
    assert SC._prefix_of("_") is None
    assert SC._prefix_of("ab") is None
    assert SC._prefix_of("abc") == "abc"


def test_a_dispatch_by_constructed_name_keeps_its_handlers_live(tmp_path):
    """The measured regression. The first sweep of `harness/swe/` reported 40
    `unreferenced` defs and every one was a `_stmt_*` handler reached by
    `getattr(self, "_stmt_" + kind)`. With the rule the count is 0."""
    root = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/m.py": '''
            class G:
                def go(self, kind):
                    return getattr(self, "_stmt_" + kind)()

                def _stmt_a(self):
                    return 1

                def _stmt_b(self):
                    return 2

            def entry():
                return G().go("a")
        ''',
        "app.py": "import pkg.m as m\nm.entry()\n",
    })
    rep = SC.audit(root, "pkg/m.py")
    v = dict((r["qualname"], r["verdict"]) for r in rep["defs"])
    assert v["G._stmt_a"] == SC.VERDICT_LIVE
    assert v["G._stmt_b"] == SC.VERDICT_LIVE
    assert rep["counts"][SC.VERDICT_UNREFERENCED] == 0
    got = dict((r["qualname"], r) for r in rep["defs"])
    assert got["G._stmt_a"]["live_only_via_dynamic_prefix"] is True


def test_the_prefix_rule_only_adds_liveness_it_never_removes_any(tmp_path):
    """Direction matters: an orphan claim is strong, so a conservative rule
    that could turn a `live` into a `test_only` would be a bug."""
    root = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/m.py": 'def do_thing():\n    return 1\n',
        "app.py": 'import pkg.m\npkg.m.do_thing()\nx = "do_" + k\n',
    })
    rep = SC.audit(root, "pkg/m.py")
    assert rep["counts"][SC.VERDICT_LIVE] == 1


# ------------------------------------------------------------- test-file map

@pytest.mark.parametrize("rel", [
    "nuc/tests/test_perturbation.py", "harness/tests/conftest.py",
    "a/tests/helper.py", "test_x.py",
])
def test_the_test_tree_is_recognised(rel):
    assert SC.is_test_file(rel)


@pytest.mark.parametrize("rel", [
    "nuc/perturbation.py", "harness/swe/nodecampaign.py", "a/b/latest.py",
    "tests.py", "contest_results.py",
])
def test_product_paths_are_not_mistaken_for_tests(rel):
    assert not SC.is_test_file(rel)


# --------------------------------------------------------------- the verdict

BASE = {
    "pkg/__init__.py": "",
    "pkg/m.py": '''
        def live_one():
            return 1

        def orphan():
            return 2

        def helper_of_orphan():
            return 3

        def uses_helper():
            return helper_of_orphan()
    ''',
    "app.py": "import pkg.m as m\nprint(m.live_one())\n",
    "pkg/tests/test_m.py": '''
        import pkg.m as m

        def test_orphan():
            assert m.orphan() == 2

        def test_uses_helper():
            assert m.uses_helper() == 3
    ''',
}


def test_a_def_a_non_test_file_calls_is_live(tmp_path):
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py")
    v = dict((r["qualname"], r["verdict"]) for r in rep["defs"])
    assert v["live_one"] == SC.VERDICT_LIVE


def test_a_def_only_the_tests_call_is_test_only_and_says_so_directly(tmp_path):
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py")
    got = dict((r["qualname"], r) for r in rep["defs"])
    assert got["orphan"]["verdict"] == SC.VERDICT_TEST_ONLY
    assert got["orphan"]["test_only_kind"] == "direct"
    assert got["orphan"]["n_test_refs"] >= 1


def test_a_helper_of_a_test_only_def_is_test_only_transitively(tmp_path):
    """`sadc_reclaim_literals` in the live tree: zero test references, two
    callers, both of them `test_only`. Counting only DIRECT test references
    would have called it live."""
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py")
    got = dict((r["qualname"], r) for r in rep["defs"])
    assert got["helper_of_orphan"]["verdict"] == SC.VERDICT_TEST_ONLY
    assert got["helper_of_orphan"]["test_only_kind"] == "transitive"
    assert got["helper_of_orphan"]["n_test_refs"] == 0


def test_a_def_nothing_anywhere_names_is_unreferenced(tmp_path):
    files = dict(BASE)
    # appended BEFORE `dedent` runs, so it carries the fixture's own eight
    # spaces -- the indentation trap that broke round 502's `owner_of` test.
    files["pkg/m.py"] = (BASE["pkg/m.py"]
                         + "\n        def nobody():\n            return 4\n")
    rep = SC.audit(_tree(tmp_path, files), "pkg/m.py")
    got = dict((r["qualname"], r) for r in rep["defs"])
    assert got["nobody"]["verdict"] == SC.VERDICT_UNREFERENCED
    assert got["nobody"]["test_only_kind"] is None


def test_a_comment_asserting_a_def_is_used_does_not_make_it_live(tmp_path):
    """THE case. `nodecampaign.py`'s scope comment is the only non-test
    mention of `classify_bucket` in this repo -- so a rule that counted
    comments would have let the false claim vouch for itself."""
    files = dict(BASE)
    files["scope.py"] = "# the campaign scopes orphan, which carries numbers\n"
    rep = SC.audit(_tree(tmp_path, files), "pkg/m.py")
    got = dict((r["qualname"], r) for r in rep["defs"])
    assert got["orphan"]["verdict"] == SC.VERDICT_TEST_ONLY
    assert "comment" in got["orphan"]["inert_kinds"]
    assert [m["path"] for m in got["orphan"]["inert_only_mentions"]] == ["scope.py"]


def test_a_docstring_asserting_a_def_is_used_does_not_make_it_live(tmp_path):
    files = dict(BASE)
    files["scope.py"] = '"""the campaign scopes orphan."""\n'
    rep = SC.audit(_tree(tmp_path, files), "pkg/m.py")
    got = dict((r["qualname"], r) for r in rep["defs"])
    assert got["orphan"]["verdict"] == SC.VERDICT_TEST_ONLY


def test_a_recursive_call_does_not_make_a_def_live(tmp_path):
    root = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/m.py": "def rec(n):\n    return 1 if n <= 0 else rec(n - 1)\n",
    })
    rep = SC.audit(root, "pkg/m.py")
    assert rep["defs"][0]["verdict"] == SC.VERDICT_UNREFERENCED


def test_module_level_code_in_the_subject_is_a_liveness_root(tmp_path):
    """It runs on import. A def only module-level code calls is live."""
    root = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/m.py": "def f():\n    return 1\n\nTABLE = f()\n",
    })
    rep = SC.audit(root, "pkg/m.py")
    assert rep["defs"][0]["verdict"] == SC.VERDICT_LIVE


def test_a_method_of_a_live_class_is_live(tmp_path):
    """`C().method()` through a variable is invisible to a name scan; the
    class's own liveness is what that call site looks like."""
    root = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/m.py": "class C:\n    def method(self):\n        return 1\n",
        "app.py": "import pkg.m\npkg.m.C()\n",
    })
    rep = SC.audit(root, "pkg/m.py")
    v = dict((r["qualname"], r["verdict"]) for r in rep["defs"])
    assert v == {"C": SC.VERDICT_LIVE, "C.method": SC.VERDICT_LIVE}


def test_a_name_in_an_unrelated_module_still_counts(tmp_path):
    """Resolution is by NAME, not by binding. That over-approximates callers,
    which under-reports orphans -- the safe direction for a strong claim."""
    root = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/m.py": "def orphan():\n    return 2\n",
        "elsewhere.py": "def orphan():\n    return 9\n\norphan()\n",
    })
    rep = SC.audit(root, "pkg/m.py")
    assert rep["defs"][0]["verdict"] == SC.VERDICT_LIVE


# ----------------------------------------------------------------- the scope

def test_only_defs_the_ranges_touch_are_in_scope(tmp_path):
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py", line_ranges=[(1, 2)])
    assert [r["qualname"] for r in rep["defs"] if r["in_scope"]] == ["live_one"]
    assert rep["n_scoped_defs"] == 1
    assert rep["n_defs"] == 4


def test_a_range_that_only_overlaps_a_def_still_scopes_it(tmp_path):
    """A campaign's ranges are hand-written line numbers and drift; a range
    ending mid-function still mutates that function."""
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py", line_ranges=[(2, 2)])
    assert [r["qualname"] for r in rep["defs"] if r["in_scope"]] == ["live_one"]


def test_no_ranges_means_the_whole_file(tmp_path):
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py")
    assert rep["n_scoped_defs"] == rep["n_defs"] == 4


def test_scoped_not_live_names_exactly_the_problem(tmp_path):
    """`uses_helper` is in the list too, and correctly: the only thing that
    calls it is a test. That is the whole shape being measured."""
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py")
    assert rep["scoped_not_live"] == ["helper_of_orphan", "orphan",
                                      "uses_helper"]


# ----------------------------------------------------------- refuses to lie

def test_a_missing_subject_raises_rather_than_reporting_a_clean_scope(tmp_path):
    with pytest.raises(SC.ScopeError):
        SC.audit(str(tmp_path), "nope.py")


def test_a_subject_with_no_def_raises(tmp_path):
    root = _tree(tmp_path, {"m.py": "x = 1\n"})
    with pytest.raises(SC.ScopeError):
        SC.audit(root, "m.py")


def test_an_unparseable_file_is_counted_not_skipped_silently(tmp_path):
    files = dict(BASE)
    files["broken.py"] = "def (:\n"
    rep = SC.audit(_tree(tmp_path, files), "pkg/m.py")
    assert rep["n_unparseable"] == 1
    assert rep["unparseable"][0]["path"] == "broken.py"


def test_a_subject_outside_a_prebuilt_index_raises(tmp_path):
    """Its own internal callers would be invisible and every def would
    verdict as unreferenced -- a clean-looking, entirely wrong report."""
    root = _tree(tmp_path, BASE)
    idx, unp = SC.reference_index(root, ["app.py"])
    with pytest.raises(SC.ScopeError):
        SC.audit(root, "pkg/m.py", prebuilt=(idx, unp, ["app.py"]))


# -------------------------------------------------------------------- sweep

def test_sweep_audits_every_subject_on_one_index(tmp_path):
    root = _tree(tmp_path, BASE)
    sw = SC.sweep(root, ["pkg/m.py", "app.py"])
    assert sw["n_subjects"] == 1 or sw["n_subjects"] == 2
    assert any(r["qualname"] == "orphan" for r in sw["not_live"])


def test_sweep_records_a_subject_it_could_not_audit_rather_than_dropping_it(tmp_path):
    files = dict(BASE)
    files["empty.py"] = "x = 1\n"
    sw = SC.sweep(_tree(tmp_path, files), ["pkg/m.py", "empty.py"])
    assert sw["n_subjects"] == 1
    assert sw["n_subjects_failed"] == 1
    assert sw["failed"][0]["path"] == "empty.py"


def test_sweep_totals_sum_the_per_subject_counts(tmp_path):
    sw = SC.sweep(_tree(tmp_path, BASE), ["pkg/m.py"])
    assert sw["totals"] == sw["subjects"][0]["counts"]


# ------------------------------------------------------------------ strata

def _ledger_rows(pairs, digest="d0"):
    return [{"id": "m%d" % i, "line": ln, "status": st,
             "subject_digest": digest}
            for i, (ln, st) in enumerate(pairs)]


def test_the_pooled_rate_and_the_live_rate_are_reported_separately(tmp_path):
    """The whole point. `orphan` at lines 4-5 is `test_only`; its mutants are
    graded by tests written directly against it and nothing else, which is a
    strictly easier problem than grading the live code."""
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py")
    rows = _ledger_rows([(2, "killed"), (2, "survived"),
                         (5, "killed"), (5, "killed")])
    st = SC.stratify(rep, rows)
    assert st["pooled"]["kill_rate"] == 0.75
    assert st["live_only"]["kill_rate"] == 0.5
    assert st["strata"]["test_only"]["kill_rate"] == 1.0
    assert st["pooled_minus_live_pp"] == 25.0


def test_a_mutant_outside_every_def_lands_in_its_own_stratum(tmp_path):
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py")
    # line 999 is past the end of the fixture -- the shape a ledger row for a
    # module-level constant or an import has.
    st = SC.stratify(rep, _ledger_rows([(999, "killed")]))
    assert "module_level" in st["strata"]
    assert st["mutants_not_inside_any_def"] == ["m0"]


def test_a_stratum_gets_the_innermost_def_that_covers_the_line(tmp_path):
    root = _tree(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/m.py": "class C:\n    def m(self):\n        return 1\n",
        "app.py": "import pkg.m\npkg.m.C()\n",
    })
    rep = SC.audit(root, "pkg/m.py")
    st = SC.stratify(rep, _ledger_rows([(3, "killed")]))
    assert st["strata"]["live"]["owners"] == {"C.m": 1}


def test_rows_at_another_subject_digest_are_excluded_when_asked(tmp_path):
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py")
    rows = (_ledger_rows([(2, "killed")], digest="d0")
            + _ledger_rows([(2, "survived")], digest="d9"))
    assert SC.stratify(rep, rows)["pooled"]["graded"] == 2
    assert SC.stratify(rep, rows, subject_digest="d0")["pooled"]["graded"] == 1


def test_an_ungraded_status_is_counted_and_kept_out_of_the_rate(tmp_path):
    """`timeout`/`error` rows are neither kills nor survivals; folding them
    into either denominator would move a published number."""
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py")
    st = SC.stratify(rep, _ledger_rows([(2, "killed"), (2, "timeout")]))
    assert st["strata"]["live"]["n"] == 2
    assert st["strata"]["live"]["other"] == 1
    assert st["strata"]["live"]["graded"] == 1
    assert st["strata"]["live"]["kill_rate"] == 1.0


def test_an_empty_ledger_yields_none_rather_than_a_flattering_zero(tmp_path):
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py")
    st = SC.stratify(rep, [])
    assert st["pooled"]["kill_rate"] is None
    assert st["pooled_minus_live_pp"] is None


# --------------------------------------------------------------------- CLI

def _cli(root, *args):
    p = subprocess.run(
        [sys.executable, os.path.join(ROOT, "harness", "swe", "scopecall.py"),
         *args, "--root", root],
        capture_output=True, text=True, timeout=300)
    return p


def test_audit_strict_exits_1_when_a_scoped_def_is_not_live(tmp_path):
    root = _tree(tmp_path, BASE)
    assert _cli(root, "audit", "--rel", "pkg/m.py", "--strict").returncode == 1
    ok = _cli(root, "audit", "--rel", "pkg/m.py", "--ranges", "1-2", "--strict")
    assert ok.returncode == 0


def test_audit_writes_the_report_it_printed(tmp_path):
    out = str(tmp_path / "out" / "rep.json")
    p = _cli(str(tmp_path), "audit", "--rel", "pkg/m.py", "--json", out)
    _tree(tmp_path, BASE)
    p = _cli(str(tmp_path), "audit", "--rel", "pkg/m.py", "--json", out)
    assert p.returncode == 0, p.stderr
    rep = json.load(open(out))
    assert rep["scoped_not_live"] == ["helper_of_orphan", "orphan",
                                      "uses_helper"]
    assert "wall_seconds" in rep


def test_ranges_parse_the_same_way_the_campaign_parses_them():
    assert SC._parse_ranges("556-634,1573-1662") == [(556, 634), (1573, 1662)]
    assert SC._parse_ranges("7") == [(7, 7)]
    assert SC._parse_ranges("") is None
    assert SC._parse_ranges(None) is None


def test_strata_cli_reads_a_last_wins_ledger(tmp_path):
    """A re-score is an APPEND (round 502). Counting rows counts verdicts the
    campaign no longer holds."""
    root = _tree(tmp_path, BASE)
    led = tmp_path / "led.jsonl"
    led.write_text("".join(json.dumps(r) + "\n" for r in [
        {"id": "m0", "line": 2, "status": "survived", "subject_digest": "d0"},
        {"id": "m0", "line": 2, "status": "killed", "subject_digest": "d0"},
    ]))
    out = str(tmp_path / "st.json")
    p = _cli(root, "strata", "--rel", "pkg/m.py", "--ledger", str(led),
             "--json", out)
    assert p.returncode == 0, p.stderr
    st = json.load(open(out))
    assert st["pooled"] == {"killed": 1, "graded": 1, "kill_rate": 1.0}


def test_sweep_cli_refuses_to_report_a_clean_sweep_of_nothing(tmp_path):
    (tmp_path / "empty").mkdir()
    p = _cli(str(tmp_path), "sweep", "--in", "empty")
    assert p.returncode != 0
    assert "refusing" in (p.stderr + p.stdout)


# ------------------------------------------------------------- this tree

class TestThisTree(object):
    """Against the live repo. These are the round's findings as assertions."""

    def test_classify_bucket_is_test_only_in_the_campaigns_own_scope(self):
        """Round 502 established this by hand with `git log -S`. If a real
        caller ever lands, this test goes red and the finding is retired --
        which is the correct behaviour, not a maintenance burden."""
        rep = SC.audit(ROOT, "nuc/perturbation.py",
                       line_ranges=SC._parse_ranges("556-634,1573-1662,2232-2301"))
        assert rep["scoped_not_live"] == ["classify_bucket"]

    def test_the_only_nontest_mention_of_it_is_the_comment_that_says_it_is_live(self):
        """`nodecampaign.py`'s scope comment names `classify_bucket` as one of
        "the functions the published numbers run through". That comment is the
        ONLY thing outside the test tree that mentions it."""
        rep = SC.audit(ROOT, "nuc/perturbation.py")
        got = dict((r["qualname"], r) for r in rep["defs"])["classify_bucket"]
        assert got["verdict"] == SC.VERDICT_TEST_ONLY
        assert got["n_nontest_refs"] == 0
        paths = set(m["path"] for m in got["inert_only_mentions"])
        assert "harness/swe/nodecampaign.py" in paths

    def test_the_campaign_scope_holds_no_unreferenced_def(self):
        rep = SC.audit(ROOT, "nuc/perturbation.py",
                       line_ranges=SC._parse_ranges("556-634,1573-1662,2232-2301"))
        assert rep["scoped_counts"][SC.VERDICT_UNREFERENCED] == 0

    def test_the_ledgers_pooled_kill_rate_is_above_its_live_only_rate(self):
        """The finding, as a standing assertion: pooling the `test_only`
        stratum in flatters the headline. If a round ever makes the live
        stratum the harder-scoring one, this goes red and deserves reading."""
        rep = SC.audit(ROOT, "nuc/perturbation.py")
        rows = SC._load_ledger(os.path.join(
            ROOT, "state", "swe", "perturbation-mutation-ledger.jsonl"))
        st = SC.stratify(rep, list(rows.values()))
        assert st["strata"]["test_only"]["kill_rate"] == 1.0
        assert st["live_only"]["kill_rate"] < st["pooled"]["kill_rate"]
        assert st["pooled_minus_live_pp"] > 0


def test_a_ledger_row_with_no_line_gets_its_own_stratum(tmp_path):
    """Hand-written rows, and rows from before the field existed. Found by
    wiring this into `nodecampaign` -- it crashed on one. Dropping such a row
    silently would shrink a published denominator; crashing would make the
    campaign unrunnable against its own history."""
    rep = SC.audit(_tree(tmp_path, BASE), "pkg/m.py")
    st = SC.stratify(rep, [{"id": "m0", "status": "killed",
                            "subject_digest": "d0"}])
    assert st["strata"]["no_line"]["killed"] == 1
    assert st["mutants_not_inside_any_def"] == ["m0"]
    assert st["pooled"]["graded"] == 1
    assert st["live_only"]["graded"] == 0


# ----------------------------------------------------- the registry check

def _reg(tmp_path, entries):
    p = tmp_path / "harness" / "wiring-registry.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"entry_points": entries}))
    return "harness/wiring-registry.json"


def test_an_entry_a_shell_script_invokes_has_a_committed_caller(tmp_path):
    """A third of this repo's entry points are reached from `run_driver.sh`
    and from nothing in Python. A `.py`-only scan calls every one an orphan."""
    root = _tree(tmp_path, {
        "tool.py": "def go():\n    return 1\n",
        "run.sh": "python3 tool.py\n",
    })
    reg = _reg(tmp_path, {"tool.py": {"status": "wired", "via": "run.sh:1"}})
    ra = SC.registry_audit(root, reg)
    assert ra["rows"][0]["verdict"] == "has_committed_caller"
    assert ra["rows"][0]["nonpy_callers"] == ["run.sh"]
    assert ra["declared_wired_by_their_own_tests"] == []


def test_an_entry_only_its_own_test_reaches_is_flagged(tmp_path):
    root = _tree(tmp_path, {
        "tool.py": "def go():\n    return 1\n",
        "tests/test_tool.py": "import tool\n\ndef test_go():\n    assert tool.go()\n",
    })
    reg = _reg(tmp_path, {"tool.py": {"status": "wired",
                                      "via": "tests/test_tool.py:1"}})
    ra = SC.registry_audit(root, reg)
    assert ra["declared_wired_by_their_own_tests"] == ["tool.py"]
    assert ra["rows"][0]["via_is_a_test_file"] is True
    assert ra["rows"][0]["verdict"] == "no_committed_caller"


def test_an_entry_another_module_imports_is_not_flagged(tmp_path):
    root = _tree(tmp_path, {
        "tool.py": "def go():\n    return 1\n",
        "app.py": "import tool\ntool.go()\n",
        "tests/test_tool.py": "import tool\n",
    })
    reg = _reg(tmp_path, {"tool.py": {"status": "wired",
                                      "via": "tests/test_tool.py:1"}})
    ra = SC.registry_audit(root, reg)
    assert ra["declared_wired_by_their_own_tests"] == []
    assert ra["rows"][0]["py_callers"] == ["app.py"]


def test_the_verdict_is_no_committed_caller_and_never_dead(tmp_path):
    """A round that ran a CLI inline is a real caller that left no committed
    trace. The claim the evidence supports is that nobody can re-run it from
    the record, not that nothing ever ran it."""
    root = _tree(tmp_path, {
        "tool.py": "def go():\n    return 1\n",
        "tests/test_tool.py": "import tool\n",
    })
    reg = _reg(tmp_path, {"tool.py": {"status": "wired",
                                      "via": "tests/test_tool.py:1"}})
    ra = SC.registry_audit(root, reg)
    assert set(r["verdict"] for r in ra["rows"]) <= {
        "has_committed_caller", "no_committed_caller"}


def test_an_entry_whose_file_is_gone_is_counted_not_verdicted(tmp_path):
    root = _tree(tmp_path, {"tool.py": "def go():\n    return 1\n"})
    reg = _reg(tmp_path, {"tool.py": {"status": "wired", "via": "run.sh:1"},
                          "deleted.py": {"status": "wired", "via": "x"}})
    ra = SC.registry_audit(root, reg)
    assert ra["n_entries"] == 2 and ra["n_checked"] == 1
    assert ra["entries_not_an_existing_py_file"] == ["deleted.py"]


def test_a_missing_or_empty_registry_raises(tmp_path):
    root = _tree(tmp_path, {"tool.py": "def go():\n    return 1\n"})
    with pytest.raises(SC.ScopeError):
        SC.registry_audit(root, "nope.json")
    reg = _reg(tmp_path, {})
    with pytest.raises(SC.ScopeError):
        SC.registry_audit(root, reg)


def test_registry_strict_exits_1_on_a_self_wired_entry(tmp_path):
    root = _tree(tmp_path, {
        "tool.py": "def go():\n    return 1\n",
        "tests/test_tool.py": "import tool\n",
    })
    reg = _reg(tmp_path, {"tool.py": {"status": "wired",
                                      "via": "tests/test_tool.py:1"}})
    p = _cli(root, "registry", "--registry", reg, "--strict")
    assert p.returncode == 1, p.stdout + p.stderr
    assert "declared `wired` by their own tests" in p.stdout


class TestThisTreeRegistry(object):

    def test_this_repo_declares_wired_entries_that_only_their_tests_reach(self):
        """The measured finding, as a standing assertion. 29 of 143 at round
        503. The bound is deliberately loose: this is a claim that the class
        is non-empty and substantial, not a pin on a number that every new
        module moves."""
        ra = SC.registry_audit(ROOT)
        assert ra["n_entries"] >= 143
        assert len(ra["declared_wired_by_their_own_tests"]) >= 20
        assert "nuc/survivor_impact.py" in ra["declared_wired_by_their_own_tests"]


# --------------------------------------------------- decorators (round 504)
#
# Round 503's whole-repo sweep called all 37 defs in
# `languages/whence/whence/interp.py`'s builtin table not-live -- 30 of them
# `unreferenced`, the strongest claim this module makes. 37 is the ENTIRE
# builtin surface of the language: `print`, `len`, `fold`, everything
# `SPEC.md` documents. Every one is `@register("print", 1, "v") def
# b_print(...)`, and `register`'s `wrap` closure appends the function object
# to the table `_install_builtins` walks under the WHENCE name, so the Python
# name is never spelled again.
#
# Repo-wide, 80 of the 103 `unreferenced` verdicts were this one shape.


DEC = {
    "pkg/__init__.py": "",
    "pkg/m.py": '''
        TABLE = []

        def register(name):
            def wrap(fn):
                TABLE.append((name, fn))
                return fn
            return wrap

        @register("hello")
        def b_hello():
            return 1

        class C(object):
            @staticmethod
            def only_static():
                return 2

            @property
            def only_prop(self):
                return 3

        def make_table():
            out = []

            @register("inner")
            def b_inner():
                return 4

            return out

        def install():
            return TABLE
    ''',
    "app.py": "import pkg.m as m\nprint(m.install())\n",
}


def _verdicts(rep):
    return dict((r["qualname"], r["verdict"]) for r in rep["defs"])


def test_a_registering_decorator_makes_its_def_live(tmp_path):
    """The decorator RECEIVES the function object; the def's own name need
    never appear again. This is the whence builtin table's exact shape."""
    v = _verdicts(SC.audit(_tree(tmp_path, DEC), "pkg/m.py"))
    assert v["b_hello"] == SC.VERDICT_LIVE


def test_a_decorated_def_inside_a_factory_is_live_iff_the_factory_is(tmp_path):
    """The attribution that makes the rule true rather than merely
    permissive: a decorator is evaluated by the ENCLOSING scope, so
    `b_inner` is live because `make_table` is -- and `make_table` here is
    reached from nothing but its own module."""
    files = dict(DEC)
    rep = SC.audit(_tree(tmp_path, files), "pkg/m.py")
    v = _verdicts(rep)
    assert v["make_table"] == SC.VERDICT_UNREFERENCED
    # NOT `unreferenced`: the decorator IS a reference, and it sits inside a
    # def that is itself dead. That is this module's pre-existing
    # `transitive` reading -- "dead code with a dead caller" -- reached here
    # through a reference kind that did not exist before round 504.
    assert v["make_table.b_inner"] == SC.VERDICT_TEST_ONLY
    row = [r for r in rep["defs"]
           if r["qualname"] == "make_table.b_inner"][0]
    assert row["test_only_kind"] == "transitive"
    assert row["n_test_refs"] == 0
    assert row["nontest_kinds"] == ["decorator"]

    files["app.py"] = "import pkg.m as m\nprint(m.make_table())\n"
    v = _verdicts(SC.audit(_tree(tmp_path, files), "pkg/m.py"))
    assert v["make_table"] == SC.VERDICT_LIVE
    assert v["make_table.b_inner"] == SC.VERDICT_LIVE


def test_staticmethod_and_property_confer_no_liveness_of_their_own(tmp_path):
    """`INERT_DECORATORS` is the short list of decorators that bind a def as
    an attribute of its own class and register it nowhere. Widening the rule
    to `any decorator at all` would make every `@staticmethod` unfalsifiably
    live, which is how an orphan detector stops detecting orphans."""
    files = dict(DEC)
    files["app.py"] = "import pkg.m as m\nprint(m.install())\n"
    v = _verdicts(SC.audit(_tree(tmp_path, files), "pkg/m.py"))
    assert v["C"] == SC.VERDICT_UNREFERENCED
    assert v["C.only_static"] == SC.VERDICT_UNREFERENCED
    assert v["C.only_prop"] == SC.VERDICT_UNREFERENCED


def test_a_decorator_reference_is_never_a_self_reference(tmp_path):
    """`defs_in` starts a def's span AT its first decorator, so without the
    exemption in `_evidence_for` the registration would be filed under
    `self` and dropped exactly like a recursive call -- the bug would be
    invisible rather than wrong."""
    root = _tree(tmp_path, DEC)
    rep = SC.audit(root, "pkg/m.py")
    row = [r for r in rep["defs"] if r["qualname"] == "b_hello"][0]
    assert row["nontest_kinds"] == ["decorator"]
    assert row["n_nontest_refs"] == 1
    assert row["live_because"]["kind"] == "decorator"


def test_a_decorator_in_a_test_file_is_test_evidence_not_live(tmp_path):
    files = dict(DEC)
    files["pkg/tests/test_m.py"] = (
        "import pkg.m as m\n\n\n"
        "@m.register('t')\ndef t_thing():\n    return 5\n")
    v = _verdicts(SC.audit(_tree(tmp_path, files), "pkg/tests/test_m.py"))
    assert v["t_thing"] == SC.VERDICT_TEST_ONLY


def test_decorator_tail_reads_the_last_dotted_component():
    import ast
    def tail(src):
        return SC._decorator_tail(ast.parse(src).body[0].decorator_list[0])
    assert tail("@register('x')\ndef f(): pass\n") == "register"
    assert tail("@app.route('/')\ndef f(): pass\n") == "route"
    assert tail("@functools.wraps(g)\ndef f(): pass\n") == "wraps"
    assert tail("@prop.setter\ndef f(self): pass\n") == "setter"
    assert tail("@staticmethod\ndef f(): pass\n") == "staticmethod"
    assert tail("@(lambda f: f)\ndef f(): pass\n") == ""


def test_the_rule_can_only_add_liveness(tmp_path):
    """Same guarantee as `dynamic_prefix`: an orphan claim must fail toward
    `live`, so the decorator rule is checked against a tree where it changes
    nothing."""
    before = _verdicts(SC.audit(_tree(tmp_path, BASE), "pkg/m.py"))
    assert before["orphan"] == SC.VERDICT_TEST_ONLY
    assert before["live_one"] == SC.VERDICT_LIVE


class TestThisTreeDecorators(object):
    """Against the live repo. Round 504's finding as an assertion."""

    def test_the_whole_whence_builtin_table_is_live(self):
        rep = SC.audit(ROOT, "languages/whence/whence/interp.py",
                       subdirs=["languages/whence"])
        rows = [r for r in rep["defs"]
                if r["qualname"].startswith("_make_builtin_table.b_")]
        assert len(rows) >= 35, len(rows)
        bad = [r["qualname"] for r in rows
               if r["verdict"] != SC.VERDICT_LIVE]
        assert bad == [], bad

    def test_no_def_in_the_whence_interpreter_package_is_an_orphan(self):
        rep = SC.audit(ROOT, "languages/whence/whence/interp.py",
                       subdirs=["languages/whence"])
        assert rep["counts"][SC.VERDICT_UNREFERENCED] == 0
        assert rep["counts"][SC.VERDICT_TEST_ONLY] == 0

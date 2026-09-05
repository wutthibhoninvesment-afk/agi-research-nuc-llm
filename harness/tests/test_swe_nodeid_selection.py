"""Round 491 (SWE-loop D): per-NODEID coverage granularity, the prioritizer
fed from it, and the subset baseline that finer granularity makes necessary.

The subject that forced this: `nuc/tests/test_perturbation.py` is 233 tests
in ONE file, so round 113's file-granularity subsetting selects the whole
96 s suite for every one of `nuc/perturbation.py`'s 1794 mutants and buys
nothing. See `swe/nodecampaign.py`.
"""
import json
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swe.coverage as CV
import swe.nodeguard as NG
import swe.nodecampaign as NC
from swe.prioritize import MapPrioritizer

MOD = textwrap.dedent('''
    def alpha(x):
        return x + 1

    def beta(x):
        return x * 2

    def gamma(x):
        return x - 3
''')

# One FILE, three tests, each touching a different function -- the shape that
# defeats file-granularity subsetting and that by-test granularity separates.
TEST = textwrap.dedent('''
    import pkg.mod as M

    def test_alpha():
        assert M.alpha(1) == 2

    def test_beta():
        assert M.beta(2) == 4

    def test_gamma():
        assert M.gamma(5) == 2
''')


def _project(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "mod.py").write_text(MOD)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname("
        "os.path.dirname(os.path.abspath(__file__))))\n")
    (tmp_path / "tests" / "test_mod.py").write_text(TEST)
    return str(tmp_path)


def _lineno(text):
    return [i + 1 for i, t in enumerate(MOD.splitlines()) if t.strip() == text][0]


def _collect(root, **kw):
    return CV.collect(root, ["pkg/mod.py"],
                      ("-q", "-p", "no:cacheprovider", "tests"), **kw)


# ------------------------------------------------- granularity, end to end --

def test_by_test_keys_hits_by_nodeid_not_by_file(tmp_path):
    root = _project(tmp_path)
    cov = _collect(root, by_test=True)
    assert cov["_meta"]["returncode"] == 0
    units = CV.test_units(cov)
    assert units == ["tests/test_mod.py::test_alpha",
                     "tests/test_mod.py::test_beta",
                     "tests/test_mod.py::test_gamma"]
    # each function's body is covered by exactly ONE of the three
    cf = CV.covering_files(cov, "pkg/mod.py", _lineno("return x * 2"))
    assert [k for k in cf if not k.startswith("<")] == ["tests/test_mod.py::test_beta"]


def test_the_same_suite_at_file_granularity_separates_nothing(tmp_path):
    """The measurement that makes by-test mode worth its cost. Same project,
    same suite: at file granularity every line's covering set is the ONE
    file, i.e. the whole suite, i.e. no reduction at all."""
    root = _project(tmp_path)
    cov = _collect(root, by_file=True)
    for text in ("return x + 1", "return x * 2", "return x - 3"):
        cf = CV.covering_files(cov, "pkg/mod.py", _lineno(text))
        assert [k for k in cf if not k.startswith("<")] == ["tests/test_mod.py"]


def test_a_by_test_map_is_also_by_file_and_collapses(tmp_path):
    """The storage shape is unchanged on purpose: every existing reader
    (`save`, `load`, `collapse`, `covering_files`) works on it untouched."""
    root = _project(tmp_path)
    cov = _collect(root, by_test=True)
    assert CV.is_by_test(cov) and CV.is_by_file(cov)
    flat = CV.collapse(cov)
    assert not CV.is_by_file(flat)
    assert flat["pkg/mod.py"][_lineno("return x * 2")] >= 1


def test_save_load_roundtrips_a_by_test_map(tmp_path):
    root = _project(tmp_path)
    cov = _collect(root, by_test=True)
    p = str(tmp_path / "cov.json")
    CV.save(cov, p)
    back = CV.load(p)
    assert CV.is_by_test(back)
    assert CV.test_units(back) == CV.test_units(cov)


def test_test_units_drops_the_synthetic_buckets(tmp_path):
    root = _project(tmp_path)
    cov = _collect(root, by_test=True)
    # import-time hits land under `<collect>`; those are not runnable nodeids
    assert any(k.startswith("<") for k in cov["pkg/mod.py"])
    assert not any(u.startswith("<") for u in CV.test_units(cov))


# ------------------------------------------------------------ prioritizer --

def test_from_file_takes_units_from_a_by_test_map_not_the_filesystem(tmp_path):
    """The silent-no-op this guards. `default_test_files(root)` returns FILE
    paths; none of them equals a nodeid key, so `covering()`'s
    `f in self.test_files` filter would empty every covering set and every
    mutant would fall back to the full suite -- the exact thing by-test mode
    exists to stop, failing green."""
    root = _project(tmp_path)
    cov = _collect(root, by_test=True)
    p = str(tmp_path / "cov.json")
    CV.save(cov, p)
    prio = MapPrioritizer.from_file(p, root)
    assert prio.test_files == CV.test_units(cov)
    got = prio.covering("pkg/mod.py", _lineno("return x - 3"))
    assert got == ["tests/test_mod.py::test_gamma"]


def test_a_mutant_selects_one_nodeid_where_file_mode_selects_the_suite(tmp_path):
    root = _project(tmp_path)
    cov = _collect(root, by_test=True)
    prio = MapPrioritizer(cov, CV.test_units(cov), subset=True, root=root)

    class M(object):
        path, lineno, end_lineno, op = "pkg/mod.py", _lineno("return x * 2"), None, "arith"

    units, basis = prio.files_for(M())
    assert basis == "subset" and units == ["tests/test_mod.py::test_beta"]
    cmd = prio.cmd_for(M(), ["python", "-m", "pytest", "-q", "tests"])
    assert cmd[-1] == "tests/test_mod.py::test_beta"


# ---------------------------------------------------------- subset baseline --

class _FakeRun(object):
    def __init__(self, returncode, output="", seconds=0.1):
        self.returncode, self.output, self.seconds = returncode, output, seconds
        self.timed_out = False


def _guard(results):
    """results: list of _FakeRun consumed in call order."""
    calls = []
    it = iter(results)

    def runner(cmd):
        calls.append(list(cmd))
        return next(it)

    g = NG.SubsetBaseline("/root", ["python", "-m", "pytest", "-q", "tests"], runner=runner)
    return g, calls


def test_a_green_subset_is_clean_and_probed_once_per_distinct_set():
    g, calls = _guard([_FakeRun(0)])
    assert g.is_clean(["t::a", "t::b"])
    assert g.is_clean(["t::b", "t::a"])          # same SET, order irrelevant
    assert g.n_probes == 1 and len(calls) == 1
    assert calls[0][-2:] == ["t::a", "t::b"]


def test_an_order_dependent_test_poisons_its_subset_rather_than_faking_a_kill():
    """The defect finer granularity introduces. A test that only passes when
    a file-mate ran first exits 1 when selected alone, and
    `mutation.classify_mutant_run` reads exit 1 as `killed` -- so it
    manufactures a kill for every mutant on every line it covers, inflating
    the one number the campaign reports. `baseline_check` cannot see it: the
    whole suite satisfies the dependency by construction."""
    g, _ = _guard([_FakeRun(1, "FAILED tests/test_mod.py::test_beta - AssertionError")])
    assert not g.is_clean(["tests/test_mod.py::test_beta"])
    assert g.verdict(["tests/test_mod.py::test_beta"]) == NG.POISONED
    bad = g.poisoned_subsets()
    assert len(bad) == 1 and bad[0][0] == ["tests/test_mod.py::test_beta"]
    assert "FAILED" in bad[0][1]
    assert g.as_dict()["n_poisoned"] == 1 and g.as_dict()["n_clean"] == 0


def test_an_empty_selection_is_poisoned_and_never_probed():
    """Round 490 (NUC E) shipped `sar --strict` exiting 0 on zero captures
    read. This is that shape in the instrument that scores tests: pytest with
    no target collects nothing and exits 5, and a campaign reading that as
    `survived` would report 'the suite does not notice' about a suite it
    never ran."""
    g, calls = _guard([])
    assert g.verdict([]) == NG.POISONED
    assert g.n_probes == 0 and calls == []


def test_a_timed_out_probe_is_poisoned_not_clean():
    r = _FakeRun(0)
    r.timed_out = True
    g, _ = _guard([r])
    assert g.verdict(["t::a"]) == NG.POISONED


def test_union_probe_units_orders_the_widest_subset_first():
    class P(object):
        def __init__(self, m):
            self.m = m

        def files_for(self, mut):
            return self.m[mut], "subset"

    class M(object):
        def __init__(self, n):
            self.n = n

        def __hash__(self):
            return self.n

    a, b, c = M(1), M(2), M(3)
    prio = P({a: ["x"], b: ["x", "y", "z"], c: ["x"]})
    assert NG.union_probe_units(prio, [a, b, c])[0] == ["x", "y", "z"]


# ---------------------------------------------------------------- ledger --

def test_the_ledger_identity_includes_the_subject_digest(tmp_path):
    """A mutant id is `basename:line:op#i` with `i` POSITIONAL (see
    `mutation.py`'s frozen-id docstring). The same id against a moved source
    is a DIFFERENT mutant, so skipping it as already-scored would silently
    report a stale verdict."""
    p = str(tmp_path / "led.jsonl")
    NC.append_ledger(p, {"id": "mod.py:9:arith#2", "subject_digest": "aaa", "status": "killed"})
    NC.append_ledger(p, {"id": "mod.py:9:arith#2", "subject_digest": "bbb", "status": "survived"})
    led = NC.load_ledger(p)
    assert len(led) == 2
    assert led[("mod.py:9:arith#2", "aaa")]["status"] == "killed"
    assert led[("mod.py:9:arith#2", "bbb")]["status"] == "survived"


def test_load_ledger_of_a_missing_file_is_empty(tmp_path):
    assert NC.load_ledger(str(tmp_path / "nope.jsonl")) == {}


def test_select_mutants_restricts_to_the_line_ranges(tmp_path):
    root = _project(tmp_path)
    ms, digest = NC.select_mutants(root, "pkg/mod.py",
                                   [(_lineno("return x * 2"), _lineno("return x * 2"))])
    assert ms and all(m.lineno == _lineno("return x * 2") for m in ms)
    assert digest and len(digest) > 8


def test_run_slice_refuses_a_map_that_is_not_by_test(tmp_path):
    root = _project(tmp_path)
    cov = _collect(root, by_file=True)
    p = str(tmp_path / "cov.json")
    CV.save(cov, p)
    try:
        NC.run_slice(root, "pkg/mod.py", p, ["python", "-m", "pytest", "-q", "tests"])
    except ValueError as e:
        assert "by-test" in str(e)
    else:
        raise AssertionError("a by-file map must be refused, not silently subset by file")


def test_report_never_hides_what_the_budget_left_unrun():
    g, _ = _guard([])
    ran = [{"id": "a", "status": "killed", "oracle": "subset", "n_units": 2, "line": 1,
            "op": "cmp", "description": "d", "seconds": 1.0}]
    rep = NC.report(ran, [1] * 89, [1] * 89, 88, g, None, 5.0)
    assert rep["n_sites_in_scope"] == 89
    assert rep["n_run_this_slice"] == 1
    assert rep["n_left_unrun_by_budget"] == 88
    assert rep["kill_rate"] == 100.0


def test_kill_rate_is_none_rather_than_zero_when_nothing_was_scorable():
    g, _ = _guard([])
    ran = [{"id": "a", "status": "error", "oracle": "full", "n_units": 0, "line": 1,
            "op": "cmp", "description": "d", "seconds": 1.0}]
    rep = NC.report(ran, [1], [1], 0, g, None, 1.0)
    assert rep["kill_rate"] is None          # not 0.0, which reads as a real score


# --------------------------------------------------------------------------
# Round 502 (NUC-integration E): the three selections.
#
# Round 497 recorded `suite_digest` per row and counted the rows scored under
# another one. That made the staleness VISIBLE and left it unpayable: the
# resume key is `(mutant_id, subject_digest)`, so a scored mutant is skipped
# forever, and `survived` is exactly the verdict a stronger suite overturns.
# Round 491 added six tests immediately after its own slice to kill eight of
# its own survivors and the ledger still called all fifteen survivors.

def _slice(root, tmp_path, ledger, **kw):
    cov = _collect(root, by_test=True)
    p = str(tmp_path / "cov.json")
    CV.save(cov, p)
    return NC.run_slice(root, "pkg/mod.py", p,
                        [sys.executable, "-m", "pytest", "-x", "-q", "tests"],
                        ledger=ledger, budget_s=120.0, timeout_s=60.0,
                        linked=False, **kw)


def test_only_scores_just_the_named_ids_and_still_skips_scored_ones(tmp_path):
    root = _project(tmp_path)
    ms, digest = NC.select_mutants(root, "pkg/mod.py")
    led = str(tmp_path / "led.jsonl")
    NC.append_ledger(led, {"id": ms[0].id, "subject_digest": digest,
                           "status": "killed", "suite_digest": "whatever"})
    rep = _slice(root, tmp_path, led, only_ids=[ms[0].id, ms[1].id])
    assert rep["selection"] == "only"
    assert rep["n_selected"] == 1                    # ms[0] already scored
    assert [r["id"] for r in rep["survivors"]] in ([], [ms[1].id])


def test_rescore_runs_a_mutant_the_ledger_already_holds(tmp_path):
    root = _project(tmp_path)
    ms, digest = NC.select_mutants(root, "pkg/mod.py")
    led = str(tmp_path / "led.jsonl")
    NC.append_ledger(led, {"id": ms[0].id, "subject_digest": digest,
                           "status": "survived", "suite_digest": "old"})
    rep = _slice(root, tmp_path, led, only_ids=[ms[0].id], rescore=True)
    assert rep["selection"] == "only-rescore"
    assert rep["n_selected"] == 1
    assert rep["n_run_this_slice"] == 1


def test_a_rescore_appends_and_the_ledger_is_last_wins(tmp_path):
    """It must not EDIT the file. A ledger that rewrites rows loses the fact
    that the verdict changed, which is the only interesting thing about it."""
    root = _project(tmp_path)
    ms, digest = NC.select_mutants(root, "pkg/mod.py")
    led = str(tmp_path / "led.jsonl")
    NC.append_ledger(led, {"id": ms[0].id, "subject_digest": digest,
                           "status": "survived", "suite_digest": "old"})
    _slice(root, tmp_path, led, only_ids=[ms[0].id], rescore=True)
    rows = [json.loads(l) for l in open(led) if l.strip()]
    assert len(rows) == 2 and rows[0]["suite_digest"] == "old"
    assert NC.load_ledger(led)[(ms[0].id, digest)] is not rows[0]


def test_stale_selects_exactly_the_survivors_graded_by_another_suite(tmp_path):
    root = _project(tmp_path)
    ms, digest = NC.select_mutants(root, "pkg/mod.py")
    led = str(tmp_path / "led.jsonl")
    # a stale survivor, a stale KILL, and a survivor at the current suite
    NC.append_ledger(led, {"id": ms[0].id, "subject_digest": digest,
                           "status": "survived", "suite_digest": "old"})
    NC.append_ledger(led, {"id": ms[1].id, "subject_digest": digest,
                           "status": "killed", "suite_digest": "old"})
    cov = _collect(root, by_test=True)
    p = str(tmp_path / "cov.json")
    CV.save(cov, p)
    base = [sys.executable, "-m", "pytest", "-x", "-q", "tests"]
    suite = NC.suite_digest(root, base)
    NC.append_ledger(led, {"id": ms[2].id, "subject_digest": digest,
                           "status": "survived", "suite_digest": suite})
    rep = _slice(root, tmp_path, led, stale_survivors_only=True)
    assert rep["selection"] == "stale-survivors"
    assert rep["n_selected"] == 1
    assert rep["survivors_scored_under_another_suite"] == [ms[0].id]


def test_a_selection_reports_every_verdict_it_CHANGED(tmp_path):
    """The number the round quotes. Without it a re-score is a silent
    correction and nobody can tell how wrong the old figure was."""
    root = _project(tmp_path)
    ms, digest = NC.select_mutants(root, "pkg/mod.py")
    led = str(tmp_path / "led.jsonl")
    NC.append_ledger(led, {"id": ms[0].id, "subject_digest": digest,
                           "status": "survived", "suite_digest": "old"})
    rep = _slice(root, tmp_path, led, stale_survivors_only=True)
    changes = {c["id"]: c for c in rep["verdict_changes"]}
    if rep["by_status"].get("killed"):
        assert changes[ms[0].id]["was"] == "survived"
        assert changes[ms[0].id]["now"] == "killed"
    else:
        assert changes == {}


def test_the_default_selection_is_unchanged_and_reports_itself(tmp_path):
    """Round 491's and 497's invocation must keep behaving exactly as it did;
    the new fields are additive."""
    root = _project(tmp_path)
    led = str(tmp_path / "led.jsonl")
    rep = _slice(root, tmp_path, led)
    assert rep["selection"] == "unscored"
    assert rep["n_selected"] == rep["n_sites_in_scope"]
    assert "verdict_changes" not in rep


def test_the_cli_parses_the_three_new_flags():
    a = NC.build_parser().parse_args(["--only", "a,b", "--rescore"])
    assert a.only == "a,b" and a.rescore is True and a.stale is False
    b = NC.build_parser().parse_args(["--stale"])
    assert b.stale is True and b.only is None and b.rescore is False

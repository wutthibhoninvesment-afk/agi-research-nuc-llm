"""Round 413 (SWE-loop D) — `guardpin.py`'s verdicts, end to end.

Every verdict the module can return is produced by a real run against the
synthetic project in `guardpin_fixture.py`: a real copy, a real pytest
subprocess, a real red/green. Slow by construction (subprocess per run), so
it carries the `test_swe_` prefix and tiers itself out of the fast suite.
The offline half is `test_guardpin.py`.
"""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe import guardpin as G                                  # noqa: E402
from tests.guardpin_fixture import _pin, _project, _run         # noqa: E402


# ------------------------------------------------------------ verdicts -------

@pytest.mark.swe_slow
def test_guarded_is_the_named_test_going_red(tmp_path):
    rep = _run([_pin(id="A", keep_call=True)], _project(tmp_path))
    assert [r.verdict for r in rep.results] == ["guarded"]
    assert rep.score == 1.0 and not rep.findings


@pytest.mark.swe_slow
def test_a_structural_pin_survives_keep_call_and_the_suite_does_not(tmp_path):
    """The headline. Same call, same file, two verdicts.

    `test_collect_mentions_the_gate` greps `collect`'s source for `exempt(`.
    With the call kept and only its VALUE discarded, that text is still there
    and the structural pin passes — while the behavioural test in the same
    file goes red. The pin is not wrong about anything; it just is not what
    catches this.
    """
    keep = _pin(id="KEEP", keep_call=True,
                test="tests/test_mod.py::test_collect_mentions_the_gate")
    drop = _pin(id="DROP", keep_call=False,
                test="tests/test_mod.py::test_collect_mentions_the_gate")
    rep = _run([keep, drop], _project(tmp_path))
    by = {r.id: r for r in rep.results}
    assert by["KEEP"].verdict == "misattributed"
    assert "test_collect_skips_placeholders" in by["KEEP"].detail
    assert by["DROP"].verdict == "guarded"


@pytest.mark.swe_slow
def test_unguarded_is_a_call_nothing_in_the_suite_reads(tmp_path):
    pin = _pin(id="U", func="run", edit="drop_stmt", stmt_kind="expr",
               target="log_it", test="tests/test_mod.py::test_run_returns_its_argument")
    rep = _run([pin], _project(tmp_path))
    assert rep.results[0].verdict == "unguarded"
    assert rep.findings and rep.score == 0.0


@pytest.mark.swe_slow
def test_keep_call_on_a_bare_call_statement_is_refused_as_equivalent(tmp_path):
    """`(log_it(x), None)[1]` runs the same call and discards a value nobody
    read. Reporting `unguarded` for that would be a finding manufactured by
    the tool's own edit."""
    pin = _pin(id="E", func="run", target="log_it", keep_call=True,
               test="tests/test_mod.py::test_run_returns_its_argument")
    rep = _run([pin], _project(tmp_path))
    assert rep.results[0].verdict == "equivalent"
    assert rep.errors and not rep.findings


@pytest.mark.swe_slow
def test_a_rotted_pin_is_unlocatable_and_never_runs_a_test(tmp_path):
    rep = _run([_pin(id="R", target="gone")], _project(tmp_path))
    assert rep.results[0].verdict == "unlocatable"
    assert rep.results[0].runs == {}


@pytest.mark.swe_slow
def test_a_pin_whose_own_test_is_red_unmutated_is_nonviable(tmp_path):
    """Round 349's rule, per pin. A verdict measured against a red baseline
    is not evidence, and it fails in the flattering direction."""
    root = _project(tmp_path, extra_tests="\n\ndef test_already_red():\n    assert False\n")
    rep = _run([_pin(id="N", test="tests/test_mod.py::test_already_red")], root)
    assert rep.results[0].verdict == "nonviable"
    assert "not evidence" in rep.results[0].detail


@pytest.mark.swe_slow
def test_expect_in_failure_separates_red_from_red_for_this_reason(tmp_path):
    """Round 412's shape: a test can go red without reaching its subject."""
    root = _project(tmp_path)
    right = _pin(id="OK", func="audit", edit="drop_stmt", stmt_kind="raise",
                 target="ValueError", test="tests/test_mod.py::test_audit_rejects_negative",
                 expect_in_failure="audit accepted a negative n")
    wrong = dict(right, id="NO", expect_in_failure="ZeroDivisionError")
    rep = _run([right, wrong], root)
    by = {r.id: r.verdict for r in rep.results}
    assert by == {"OK": "guarded", "NO": "wrong_reason"}


@pytest.mark.swe_slow
def test_check_sole_says_whether_the_named_test_is_the_only_one(tmp_path):
    """`guarded` says the named test caught it, not that it is the only
    thing that would have."""
    root = _project(tmp_path)
    alone = _pin(id="ALONE", keep_call=True, check_sole=True,
                 test="tests/test_mod.py::test_collect_skips_placeholders")
    shared = _pin(id="SHARED", keep_call=False, check_sole=True,
                  test="tests/test_mod.py::test_collect_skips_placeholders")
    rep = _run([alone, shared], root)
    by = {r.id: r for r in rep.results}
    assert by["ALONE"].verdict == "guarded" and by["ALONE"].sole_guardian is True
    assert by["SHARED"].verdict == "guarded" and by["SHARED"].sole_guardian is False
    assert "test_collect_mentions_the_gate" in by["SHARED"].detail


@pytest.mark.swe_slow
def test_baselines_are_computed_once_per_target_not_once_per_pin(tmp_path):
    root = _project(tmp_path)
    pins = [_pin(id="A", keep_call=True), _pin(id="B", keep_call=False)]
    rep = _run(pins, root)
    assert list(rep.baselines.as_dict()) == [
        "tests/test_mod.py::test_collect_skips_placeholders"]


@pytest.mark.swe_slow
def test_the_report_serialises_the_diff_and_the_reason(tmp_path):
    rep = _run([_pin(id="A", keep_call=True, check_sole=True)], _project(tmp_path))
    blob = json.loads(json.dumps(rep.as_dict()))
    r = blob["results"][0]
    assert r["verdict"] == "guarded" and r["keep_call"] is True
    assert "exempt(t), None" in r["diff"] and r["why"] == "fixture"
    assert blob["guarded"] == 1 and blob["score"] == 1.0


@pytest.mark.swe_slow
def test_nothing_touches_the_original_checkout(tmp_path):
    root = _project(tmp_path)
    before = io.open(os.path.join(root, "mod.py"), encoding="utf-8").read()
    _run([_pin(id="A", keep_call=True), _pin(id="B", keep_call=False)], root)
    assert io.open(os.path.join(root, "mod.py"), encoding="utf-8").read() == before

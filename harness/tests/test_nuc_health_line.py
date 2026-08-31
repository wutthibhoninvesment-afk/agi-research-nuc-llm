"""Round 409 (harness A) — `driver_health.classify_nuc_health_log`.

The nuc check is the first per-round health check with TWO legs (pytest and
`constant_audit.py`), and it prints the second leg's result AFTER pytest's
count line. Every test here exists because the shared, pytest-shaped
classifier gets that log wrong in a specific, already-paid-for way; the
first test is the measurement that decided a separate formatter was needed
rather than a style preference.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import driver_health as dh                       # noqa: E402


GREEN = """....................                                     [100%]
490 passed in 30.12s

constant-audit 19 constants, 15 derived (0.789), 4 bare, 0 transform-risk
nuc-checks PASS (pytest rc=0, audit rc=0)
"""

AUDIT_RED = """....................                                     [100%]
490 passed in 30.12s

constant-audit 19 constants, 15 derived (0.789), 4 bare, 2 transform-risk
nuc-checks FAIL (pytest rc=0, audit rc=1)
"""

TESTS_RED = """...F................                                     [100%]
=========================== short test summary info ===========================
FAILED nuc/tests/test_reachability.py::test_a_stale_route_is_reported
1 failed, 489 passed in 31.02s

constant-audit 19 constants, 15 derived (0.789), 4 bare, 0 transform-risk
nuc-checks FAIL (pytest rc=1, audit rc=0)
"""

NEVER_RAN = """ERROR: file or directory not found: nuc/tests/

nuc-checks FAIL (pytest rc=4, audit rc=0)
"""

DIED = """....................                                     [100%]
490 passed in 30.12s
"""


def _log(tmp_path, text, name="nuc_health_round_409.log"):
    p = str(tmp_path / name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def test_the_shared_classifier_misreads_this_log_which_is_why_this_one_exists(
        tmp_path):
    """The measurement, kept as a test so the justification cannot rot.

    If `classify_health_log` ever learns to read a two-leg log correctly,
    this test goes red and `classify_nuc_health_log` becomes deletable —
    which is the outcome a reader should want. It is asserting a DEFECT in
    a sibling function, so it says so in its name.
    """
    p = _log(tmp_path, AUDIT_RED)
    shared = dh.classify_health_log(p, 1)
    # green suite, failing audit -> the shared classifier blames the tests...
    assert shared["reason"] == "tests ran and failed"
    assert shared["summary"] == "490 passed in 30.12s"
    # ...and throws the audit's line away as "echoed".
    assert shared["summary_source"] == "count-line-guess"
    assert "transform-risk" not in shared["summary"]


def test_a_failing_audit_names_the_audit_and_keeps_both_legs(tmp_path):
    c = dh.classify_nuc_health_log(_log(tmp_path, AUDIT_RED), 1)
    assert c["outcome"] == "fail"
    assert c["reason"] == "constant audit failed"
    assert "2 transform-risk" in c["summary"]
    assert "490 passed" in c["summary"]
    assert c["legs"] == {"pytest": 0, "audit": 1}


def test_a_failing_test_names_the_tests_and_the_node_id(tmp_path):
    c = dh.classify_nuc_health_log(_log(tmp_path, TESTS_RED), 1)
    assert c["outcome"] == "fail"
    assert c["reason"] == "nuc tests failed"
    assert c["failing"] == [
        "nuc/tests/test_reachability.py::test_a_stale_route_is_reported"]
    line = dh.nuc_health_log_line("round 409: nuc-health-check",
                                  _log(tmp_path, TESTS_RED), 1)
    assert "test_a_stale_route_is_reported" in line


def test_both_legs_failing_says_both(tmp_path):
    both = TESTS_RED.replace("0 transform-risk", "2 transform-risk").replace(
        "audit rc=0", "audit rc=1")
    c = dh.classify_nuc_health_log(_log(tmp_path, both), 1)
    assert c["reason"] == "nuc tests and constant audit failed"


def test_a_green_run_quotes_both_legs_not_just_pytest(tmp_path):
    line = dh.nuc_health_log_line("round 409: nuc-health-check",
                                  _log(tmp_path, GREEN), 0)
    assert line.startswith("round 409: nuc-health-check PASS (")
    assert "490 passed in 30.12s" in line
    assert "0 transform-risk" in line


def test_a_suite_that_never_ran_is_error_not_fail(tmp_path):
    """Round 349's lesson, third flavour: 'the previous round broke the nuc
    tests' and 'pytest could not collect them' must not share a word."""
    c = dh.classify_nuc_health_log(_log(tmp_path, NEVER_RAN), 1)
    assert c["outcome"] == "error"
    assert c["ran_tests"] is False
    assert "never ran" in c["reason"]
    assert dh.nuc_health_log_line("x", _log(tmp_path, NEVER_RAN), 1).startswith(
        "x ERROR")


def test_a_script_that_died_before_its_verdict_is_error(tmp_path):
    """No `nuc-checks` line at all: the script was killed, or someone
    changed its output and this formatter has gone stale. Either way the
    honest answer is not PASS."""
    c = dh.classify_nuc_health_log(_log(tmp_path, DIED), 0)
    assert c["outcome"] == "error"
    assert "no verdict line" in c["reason"]


def test_the_scripts_word_never_outranks_wait(tmp_path):
    """`wait` said non-zero and the log says PASS. Trust the exit status and
    report the disagreement, rather than quietly logging the log's word."""
    c = dh.classify_nuc_health_log(_log(tmp_path, GREEN), 7)
    assert c["outcome"] == "error"
    assert "exited 7" in c["reason"]


def test_an_unreadable_log_is_unknown_not_pass(tmp_path):
    c = dh.classify_nuc_health_log(str(tmp_path / "absent.log"), 0)
    assert c["outcome"] == "unknown"
    assert c["legs"] == {"pytest": None, "audit": None}


def test_the_cli_subcommand_prints_the_same_line(tmp_path, capsys):
    p = _log(tmp_path, GREEN)
    rc = dh.main(["nuc_health_line", "round 409: nuc-health-check", p, "0"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == dh.nuc_health_log_line(
        "round 409: nuc-health-check", p, 0)


def test_the_cli_rejects_the_wrong_arity(capsys):
    assert dh.main(["nuc_health_line"]) == 2
    assert "usage:" in capsys.readouterr().err


def test_the_real_script_still_prints_the_verdict_line_this_parses():
    """The coupling that would rot silently: this formatter reads a string
    `nuc/run_checks_fast.sh` prints. Asserted against the script's SOURCE,
    so an E round rewording it turns this red instead of turning every
    future nuc-health-check line into ERROR."""
    # harness/tests/ -> harness/ -> repo root. Getting this wrong makes the
    # test SKIP rather than fail, which is exactly how a coupling check
    # quietly stops checking; it did on its first run.
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    src = os.path.join(root, "nuc", "run_checks_fast.sh")
    assert os.path.isdir(os.path.join(root, "nuc")) or not os.path.isdir(
        os.path.join(root, "harness")), "root resolution is wrong, not absent"
    if not os.path.exists(src):
        pytest.skip("nuc/run_checks_fast.sh absent from this checkout")
    text = open(src, encoding="utf-8").read()
    assert 'echo "nuc-checks $([ $rc -eq 0 ] && echo PASS || echo FAIL) ' \
           '(pytest rc=$pytest_rc, audit rc=$audit_rc)"' in text
    assert 'constant-audit {} constants' in text

"""End-to-end test for run_driver.sh's round-409 nuc health check.

Fourth check, same guarded-on-existence / concurrent / diagnostic-only shape
as rounds 241 (harness), 247 (whence) and 363 (skills). Real `bash
run_driver.sh` subprocesses, a real `claude` PATH stub, a controlled fake
`nuc/run_checks_fast.sh` planted in the tmp_path workspace — so nothing here
runs the real 490-test nuc suite and nothing can contact the NUC.

What is specific to THIS check: it has TWO legs, and its driver.log line is
formatted by `driver_health.nuc_health_line` rather than the shared
`health_line`, because the shared one blames the wrong leg. The unit
evidence for that is `test_nuc_health_line.py`; what these tests add is that
the driver actually calls the right formatter, with the right label, on the
right log file, without disturbing the three checks that were already there.
"""

import os
import shutil
import stat
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")

CLAUDE_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
WS="$DRIVER_TEST_WS"
COUNT_FILE="$WS/state/call_count"
N=$(( $(cat "$COUNT_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$N" > "$COUNT_FILE"

if [ "$N" -eq 1 ]; then
  echo '{"type":"result","is_error":false,"subtype":"success","num_turns":1,"result":"ok","api_error_status":null,"total_cost_usd":0.01}'
else
  echo '{"type":"result","is_error":true,"subtype":"error_test","num_turns":1,"result":"test budget limit reached","api_error_status":"test_limit","total_cost_usd":0.01}'
fi
"""

AUDIT_OK = "constant-audit 19 constants, 15 derived (0.789), 4 bare, 0 transform-risk"
AUDIT_BAD = "constant-audit 19 constants, 14 derived (0.737), 3 bare, 2 transform-risk"


def _make_stub_bin(tmp_path):
    bin_dir = os.path.join(str(tmp_path), "bin")
    os.makedirs(bin_dir, exist_ok=True)
    stub_path = os.path.join(bin_dir, "claude")
    with open(stub_path, "w") as f:
        f.write(CLAUDE_STUB)
    st = os.stat(stub_path)
    os.chmod(stub_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _make_script(ws, rel_dir, name, body):
    target_dir = os.path.join(ws, rel_dir)
    os.makedirs(target_dir, exist_ok=True)
    script_path = os.path.join(target_dir, name)
    with open(script_path, "w") as f:
        f.write("#!/usr/bin/env bash\n" + body + "\n")
    st = os.stat(script_path)
    os.chmod(script_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script_path


def _nuc_stub(ws, pytest_line, audit_line, pytest_rc=0, audit_rc=0):
    rc = 1 if (pytest_rc or audit_rc) else 0
    body = (
        'echo "%s"\necho\necho "%s"\n'
        'echo "nuc-checks %s (pytest rc=%d, audit rc=%d)"\nexit %d'
        % (pytest_line, audit_line, "PASS" if rc == 0 else "FAIL",
           pytest_rc, audit_rc, rc))
    return _make_script(ws, "nuc", "run_checks_fast.sh", body)


def _run_driver(tmp_path):
    ws = str(tmp_path)
    os.makedirs(os.path.join(ws, "state"), exist_ok=True)
    os.makedirs(os.path.join(ws, "logs"), exist_ok=True)
    driver_copy = os.path.join(ws, "run_driver.sh")
    shutil.copyfile(DRIVER_SRC, driver_copy)
    os.chmod(driver_copy, 0o755)

    bin_dir = _make_stub_bin(tmp_path)
    env = dict(os.environ)
    env["PATH"] = bin_dir + os.pathsep + env["PATH"]
    env["DRIVER_WS"] = ws
    env["DRIVER_TEST_WS"] = ws
    env["DRIVER_LOOP_SLEEP_S"] = "0"
    env["DRIVER_CLAUDE_CMD"] = "claude"
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.Popen(
        ["bash", driver_copy], cwd=REPO_ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        proc.wait(timeout=45)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        pytest.fail("driver did not stop within 45s")

    with open(os.path.join(ws, "logs", "driver.log")) as f:
        return f.read()


def test_nuc_check_skipped_when_script_absent(tmp_path):
    """Round 241's guarded-on-existence contract. Every `test_run_driver_*`
    workspace is a bare tmp_path with no `nuc/` tree, and adding a fourth
    check must not make any of them pay for a suite that is not there."""
    log_text = _run_driver(tmp_path)
    assert ": nuc-health-check" not in log_text, log_text


def test_pass_line_carries_both_legs(tmp_path):
    _nuc_stub(str(tmp_path), "490 passed in 30.12s", AUDIT_OK)
    log_text = _run_driver(tmp_path)
    assert "round 1: nuc-health-check PASS" in log_text, log_text
    assert "490 passed in 30.12s" in log_text, log_text
    assert "0 transform-risk" in log_text, log_text


def test_a_failing_audit_is_not_reported_as_a_failing_test(tmp_path):
    """The defect this whole call site was designed around: a green suite
    and a red audit. Under the shared `health_line` the driver would have
    logged `FAIL — tests ran and failed — 490 passed in 30.12s`."""
    _nuc_stub(str(tmp_path), "490 passed in 30.12s", AUDIT_BAD, audit_rc=1)
    log_text = _run_driver(tmp_path)
    assert "round 1: nuc-health-check FAIL — constant audit failed" in log_text, log_text
    assert "2 transform-risk" in log_text, log_text
    assert "tests ran and failed" not in log_text, log_text


def test_a_failing_test_names_the_tests(tmp_path):
    _nuc_stub(str(tmp_path), "1 failed, 489 passed in 31.02s", AUDIT_OK,
              pytest_rc=1)
    log_text = _run_driver(tmp_path)
    assert "round 1: nuc-health-check FAIL — nuc tests failed" in log_text, log_text


def test_a_check_that_never_ran_reads_as_error_not_fail(tmp_path):
    """Round 348/349's distinction. `pytest rc=4` is a collection abort —
    the previous round broke nothing, the environment did."""
    _make_script(str(tmp_path), "nuc", "run_checks_fast.sh",
                 'echo "ERROR: file or directory not found: nuc/tests/"\n'
                 'echo "nuc-checks FAIL (pytest rc=4, audit rc=0)"\nexit 1')
    log_text = _run_driver(tmp_path)
    assert "round 1: nuc-health-check ERROR" in log_text, log_text
    assert "nuc-health-check FAIL" not in log_text, log_text


def test_the_nuc_log_is_its_own_file_and_does_not_collide(tmp_path):
    _nuc_stub(str(tmp_path), "490 passed in 30.12s", AUDIT_OK)
    _run_driver(tmp_path)
    logs = os.listdir(os.path.join(str(tmp_path), "logs"))
    assert "nuc_health_round_1.log" in logs, logs
    text = open(os.path.join(str(tmp_path), "logs",
                             "nuc_health_round_1.log")).read()
    assert "nuc-checks PASS" in text


def test_all_four_health_checks_are_independent(tmp_path):
    ws = str(tmp_path)
    d = os.path.join(ws, "skills", "skill-authoring", "scripts")
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(os.path.join(REPO_ROOT, "skills", "skill-authoring",
                                 "scripts", "corpus_check.py"),
                    os.path.join(d, "corpus_check.py"))
    _make_script(ws, "harness", "run_tests_fast.sh",
                 'echo "961 passed, 269 deselected in 33.54s"\nexit 0')
    _make_script(ws, os.path.join("languages", "whence"), "run_tests_fast.sh",
                 'echo "1944 passed, 81 deselected in 23.26s"\nexit 0')
    _make_script(ws, "skills", "run_checks_fast.sh",
                 'echo "corpus-check: 5 checker(s), 0 error(s), 0 warning(s)"\n'
                 'exit 0')
    _nuc_stub(ws, "490 passed in 30.12s", AUDIT_OK)
    log_text = _run_driver(tmp_path)
    assert "round 1: health-check PASS (961 passed, 269 deselected in 33.54s)" in log_text, log_text
    assert "round 1: whence-health-check PASS (1944 passed, 81 deselected in 23.26s)" in log_text, log_text
    assert "round 1: skills-check PASS (corpus-check: 5 checker(s), 0 error(s), 0 warning(s))" in log_text, log_text
    assert "round 1: nuc-health-check PASS" in log_text, log_text


def test_a_red_nuc_check_does_not_stop_the_driver(tmp_path):
    """Diagnostic-only, like the other three: a broken check can itself be
    the NEXT round's legitimate fix target."""
    _nuc_stub(str(tmp_path), "490 passed in 30.12s", AUDIT_BAD, audit_rc=1)
    log_text = _run_driver(tmp_path)
    assert "nuc-health-check FAIL" in log_text
    # the driver reached its own stop condition rather than dying at the check
    assert "round 2" in log_text or "limit" in log_text.lower(), log_text


def test_the_inline_bash_fallback_is_still_present(tmp_path):
    """Round 241's degradation guarantee: a workspace that cannot run the
    Python formatter loses FORMATTING, never the record.

    Asserted structurally rather than end-to-end, and the reason is worth
    stating: `python3 -m harness.driver_health` resolves through the
    driver's cwd (the repo root), so unlike the skills check — whose
    formatter is addressed as `$WS/skills/.../corpus_check.py` and is
    genuinely absent from a bare workspace — there is no workspace shape
    that exercises this branch without breaking the repo itself.
    """
    text = open(DRIVER_SRC, encoding="utf-8").read()
    # anchor on the CALL, not on the comment that names it
    i = text.index("-m harness.driver_health nuc_health_line")
    block = text[i:i + 700]
    assert 'nuc-health-check PASS ($(tail -n 1 "$NUC_HEALTH_LOG"' in block
    assert 'nuc-health-check FAIL — $(tail -n 5 "$NUC_HEALTH_LOG"' in block

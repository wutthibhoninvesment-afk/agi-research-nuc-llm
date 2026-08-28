"""End-to-end test for run_driver.sh's round-241 per-round health check.

Round 235 (harness A) flagged, but did not build, a backlog item:
"consider whether driver_health.py or run_driver.sh itself should invoke
run_tests_fast.sh automatically as a cheap per-round health check." This
round builds it: after every round (success or not, any track), the
driver runs `$WS/harness/run_tests_fast.sh` if it exists and logs a
PASS/FAIL line to driver.log, diagnostic-only — it never blocks or stops
the driver, same design stance as round 211's `likely_timeout_kill`
classifier.

Three real `bash run_driver.sh` subprocesses (same discipline every other
`test_run_driver_*.py` file in this directory already uses — no
unit-level shortcut), each with a real `claude` PATH stub and a
controlled fake `harness/run_tests_fast.sh` planted in the tmp_path
workspace, cover: (1) the script absent entirely (every OTHER
`test_run_driver_*.py` file's tmp_path workspace shape, proving those
tests' silence on this feature is real no-op behaviour, not an untested
gap), (2) the script present and passing, (3) the script present and
failing.
"""

import os
import shutil
import stat
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")

# Round 1: a genuine success. Round 2: an "error" whose status text
# contains "limit" so the outer driver stops cleanly right after — same
# two-round shape test_run_driver_selfexec.py already uses, so a real
# `bash run_driver.sh` process finishes well inside the 45s wait without
# needing DRIVER_LOOP_SLEEP_S=0 to race anything.
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


def _make_stub_bin(tmp_path):
    bin_dir = os.path.join(str(tmp_path), "bin")
    os.makedirs(bin_dir, exist_ok=True)
    stub_path = os.path.join(bin_dir, "claude")
    with open(stub_path, "w") as f:
        f.write(CLAUDE_STUB)
    st = os.stat(stub_path)
    os.chmod(stub_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _make_health_script(ws, body):
    harness_dir = os.path.join(ws, "harness")
    os.makedirs(harness_dir, exist_ok=True)
    script_path = os.path.join(harness_dir, "run_tests_fast.sh")
    with open(script_path, "w") as f:
        f.write("#!/usr/bin/env bash\n" + body + "\n")
    st = os.stat(script_path)
    os.chmod(script_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script_path


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
        pytest.fail("driver did not stop within 45s — stub's round-2 "
                    "'limit' status should have triggered a clean break")

    driver_log = os.path.join(ws, "logs", "driver.log")
    with open(driver_log) as f:
        return f.read()


def test_health_check_skipped_when_script_absent(tmp_path):
    # No harness/ tree at all in this tmp_path workspace — the exact
    # shape every other test_run_driver_*.py file in this directory
    # already uses. Proves that shape's silence on this feature is real
    # no-op behaviour (guarded on the script's existence), not an
    # untested assumption.
    # Checks for the "round N: health-check ..." log LINE specifically,
    # not a bare "health-check" substring — DRIVER_VERSION itself is
    # "241-per-round-health-check" and appears in every round's start
    # line regardless of this feature ever firing.
    log_text = _run_driver(tmp_path)
    assert ": health-check" not in log_text, log_text


def test_health_check_pass_logged_when_script_succeeds(tmp_path):
    _make_health_script(tmp_path, 'echo "3 passed in 0.01s"\nexit 0')
    log_text = _run_driver(tmp_path)
    assert "round 1: health-check PASS (3 passed in 0.01s)" in log_text, log_text


def test_health_check_fail_logged_when_script_fails(tmp_path):
    _make_health_script(
        tmp_path,
        'echo "1 failed, 2 passed in 0.01s"\necho "FAILED harness/tests/test_x.py::test_y"\nexit 1',
    )
    log_text = _run_driver(tmp_path)
    assert "round 1: health-check FAIL" in log_text, log_text
    assert "FAILED harness/tests/test_x.py::test_y" in log_text, log_text

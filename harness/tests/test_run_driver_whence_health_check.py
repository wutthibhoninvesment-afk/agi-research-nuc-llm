"""End-to-end test for run_driver.sh's round-247 whence health check.

Round 242 (language C) built `languages/whence/run_tests_fast.sh` (the
same fast/slow-tiered shape round 235's `harness/run_tests_fast.sh`
already used) and flagged, but deliberately did not wire in, an obvious
follow-on: have `run_driver.sh` run it once per round too, alongside
round 241's own `harness/run_tests_fast.sh` health check. This round
builds that follow-on.

Same discipline as `test_run_driver_health_check.py`: real `bash
run_driver.sh` subprocesses (no unit-level shortcut), a real `claude`
PATH stub, and a controlled fake `languages/whence/run_tests_fast.sh`
planted in the tmp_path workspace. Covers: (1) the script absent
entirely — the shape every OTHER `test_run_driver_*.py` file's tmp_path
workspace already uses, proving their silence on this feature is real
no-op behaviour; (2) present and passing; (3) present and failing; (4)
both the harness AND whence health scripts present together, to prove
the two checks are independent and neither's log line clobbers the
other's.
"""

import os
import shutil
import stat
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")

# Same two-round shape as test_run_driver_health_check.py: round 1 succeeds,
# round 2's status text contains "limit" so the outer driver stops cleanly
# right after, keeping the real `bash run_driver.sh` subprocess well inside
# the 45s wait.
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


def _make_script(ws, rel_dir, name, body):
    target_dir = os.path.join(ws, rel_dir)
    os.makedirs(target_dir, exist_ok=True)
    script_path = os.path.join(target_dir, name)
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


def test_whence_health_check_skipped_when_script_absent(tmp_path):
    # No languages/ tree at all — the exact shape every other
    # test_run_driver_*.py file's tmp_path workspace already uses. Proves
    # that shape's silence on this feature is real no-op behaviour
    # (guarded on the script's existence), not an untested assumption.
    log_text = _run_driver(tmp_path)
    assert ": whence-health-check" not in log_text, log_text


def test_whence_health_check_pass_logged_when_script_succeeds(tmp_path):
    _make_script(
        str(tmp_path), os.path.join("languages", "whence"),
        "run_tests_fast.sh", 'echo "840 passed, 35 deselected in 23.26s"\nexit 0',
    )
    log_text = _run_driver(tmp_path)
    assert "round 1: whence-health-check PASS (840 passed, 35 deselected in 23.26s)" in log_text, log_text


def test_whence_health_check_fail_logged_when_script_fails(tmp_path):
    _make_script(
        str(tmp_path), os.path.join("languages", "whence"),
        "run_tests_fast.sh",
        'echo "1 failed, 839 passed in 23.00s"\necho "FAILED tests/test_x.py::test_y"\nexit 1',
    )
    log_text = _run_driver(tmp_path)
    assert "round 1: whence-health-check FAIL" in log_text, log_text
    # Round 379: same edit, and same reason, as the harness twin of this
    # test. The failing node id reaches driver.log from
    # `classify_health_log`'s `failing` list now, so it arrives without the
    # `FAILED ` prefix, alongside the count line rather than instead of it.
    assert "tests/test_x.py::test_y" in log_text, log_text
    assert "1 failed, 839 passed in 23.00s" in log_text, log_text


def test_both_health_checks_run_independently_when_both_scripts_present(tmp_path):
    # Round 241's harness/run_tests_fast.sh check and this round's whence
    # one must not clobber each other's log line or log file — both
    # PASS/FAIL lines must appear, each with its own tail-of-output.
    _make_script(
        str(tmp_path), "harness", "run_tests_fast.sh",
        'echo "373 passed, 176 deselected in 33.54s"\nexit 0',
    )
    _make_script(
        str(tmp_path), os.path.join("languages", "whence"),
        "run_tests_fast.sh", 'echo "840 passed, 35 deselected in 23.26s"\nexit 0',
    )
    log_text = _run_driver(tmp_path)
    assert "round 1: health-check PASS (373 passed, 176 deselected in 33.54s)" in log_text, log_text
    assert "round 1: whence-health-check PASS (840 passed, 35 deselected in 23.26s)" in log_text, log_text

    ws = str(tmp_path)
    assert os.path.isfile(os.path.join(ws, "logs", "health_round_1.log"))
    assert os.path.isfile(os.path.join(ws, "logs", "whence_health_round_1.log"))


def test_both_health_checks_run_concurrently_not_sequentially(tmp_path):
    # Round 277: the two checks must overlap in wall time, not run back to
    # back. Deliberately does NOT assert on total driver-process wall time
    # (tried first, see this round's own knowledge file — on this host,
    # under real memory pressure, the handful of unrelated `python3 -m
    # harness.driver_health ...` calls the rest of a round already makes
    # (ratelimit_signal/summary/success/status/is5xx/is429/the final
    # 3-failure tally) cost enough cumulative process-startup time on
    # their own to blow past a tight total-wall-time ceiling even when the
    # two checks themselves genuinely ran in parallel — a false failure
    # unrelated to the property under test). Instead each stub records its
    # own start timestamp (`date +%s.%N`, monotonic-enough for a same-host
    # sub-second comparison) to a file before sleeping 2s; a strictly
    # sequential implementation (the pre-round-277 shape: `if bash
    # "$SCRIPT" ...; then ...` run twice in a row) starts the second
    # script only after the first's full 2s sleep completes, so the two
    # start timestamps would be ~2s apart. A concurrent one (both
    # backgrounded, then waited on) starts them within milliseconds of
    # each other regardless of any unrelated overhead elsewhere in the
    # round. 1.0s ceiling leaves a wide margin below the 2s sleep while
    # comfortably above realistic same-host scheduling jitter.
    ws = str(tmp_path)
    os.makedirs(os.path.join(ws, "state"), exist_ok=True)
    _make_script(
        ws, "harness", "run_tests_fast.sh",
        f'date +%s.%N > "{ws}/state/health_start"\nsleep 2\necho "1 passed in 2.00s"\nexit 0',
    )
    _make_script(
        ws, os.path.join("languages", "whence"),
        "run_tests_fast.sh",
        f'date +%s.%N > "{ws}/state/whence_start"\nsleep 2\necho "1 passed in 2.00s"\nexit 0',
    )
    log_text = _run_driver(tmp_path)
    assert "round 1: health-check PASS (1 passed in 2.00s)" in log_text, log_text
    assert "round 1: whence-health-check PASS (1 passed in 2.00s)" in log_text, log_text

    with open(os.path.join(ws, "state", "health_start")) as f:
        health_start = float(f.read().strip())
    with open(os.path.join(ws, "state", "whence_start")) as f:
        whence_start = float(f.read().strip())
    gap = abs(health_start - whence_start)
    assert gap < 1.0, (
        f"health/whence checks started {gap:.2f}s apart — looks "
        "sequential, not concurrent"
    )


# ------------------------------------------------------- round 349 (harness A) --

def test_whence_health_check_error_when_the_suite_never_ran(tmp_path):
    """pytest exit 4 (config/usage error) must log ERROR, not FAIL.

    This is round 348's live shape, reduced: a duplicate TOML table in the
    UNTRACKED `languages/whence/pyproject.toml` aborted pytest during config
    discovery, all 1043 fast-tier tests were down, and the driver logged
    `whence-health-check FAIL` — which reads as "round 348 broke the whence
    tests" and is false. The distinction the log has to carry is whether any
    test ran at all.
    """
    _make_script(
        str(tmp_path), os.path.join("languages", "whence"),
        "run_tests_fast.sh",
        "echo \"ERROR: /x/pyproject.toml: Cannot declare ('project', "
        "'optional-dependencies') twice (at line 29, column 31)\"\nexit 4",
    )
    log_text = _run_driver(tmp_path)
    assert "round 1: whence-health-check ERROR" in log_text, log_text
    assert "suite did not run (pytest exit 4)" in log_text, log_text
    # The word FAIL must NOT appear on this line — that is the whole point.
    line = next(l for l in log_text.splitlines() if "whence-health-check" in l)
    assert "FAIL" not in line, line


def test_whence_health_check_error_when_nothing_was_collected(tmp_path):
    # pytest exit 5: the suite is intact but selected zero tests — e.g. a
    # marker expression that stopped matching after a rename. Green-looking
    # in every way except that no test ran, so it is an ERROR, not a PASS.
    _make_script(
        str(tmp_path), os.path.join("languages", "whence"),
        "run_tests_fast.sh", 'echo "no tests ran in 0.01s"\nexit 5',
    )
    log_text = _run_driver(tmp_path)
    assert "round 1: whence-health-check ERROR" in log_text, log_text
    assert "pytest exit 5" in log_text, log_text


def test_harness_health_check_error_uses_the_same_wording(tmp_path):
    # Both call sites go through driver_health.health_line precisely so they
    # cannot drift apart; assert that on the harness-side line too.
    _make_script(
        str(tmp_path), "harness", "run_tests_fast.sh",
        'echo "ERROR: file or directory not found: harness/tests/"\nexit 4',
    )
    log_text = _run_driver(tmp_path)
    assert "round 1: health-check ERROR — suite did not run (pytest exit 4)" in log_text, log_text

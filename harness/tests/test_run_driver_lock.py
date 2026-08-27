"""End-to-end test for run_driver.sh's round-157 single-instance flock guard.

Round 157 found LIVE, on the real production driver, that nothing prevents
two separate `bash run_driver.sh` invocations from racing on the same
`state/round_counter`: driver.log showed round 158 start while round 157's
own `claude` session was still running, then round 159 start 45s later
(production's default `LOOP_SLEEP_S`, ruling out a test artifact) — a
second, independent driver process reading round_counter mid-round,
incrementing it, and launching its own session with nothing waiting for
the prior round to actually finish.

This test proves the fix (`flock -n` on `$WS/state/.driver.lock`, held for
the driver's whole lifetime via fd 9 surviving the self-exec) with two
REAL `bash run_driver.sh` subprocesses pointed at the SAME tmp_path
workspace and the SAME fake-`claude` stub on PATH: the second process must
exit immediately without ever starting a round, while the first runs
normally to completion.
"""

import os
import shutil
import stat
import subprocess
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")

# Round 1: sleeps briefly (so there's a real window for a second process to
# try to race in) then reports a "limit" status so the first driver stops
# cleanly on its own — no infinite loop, no third round needed.
CLAUDE_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
sleep 2
echo '{"type":"result","is_error":true,"subtype":"error_test","num_turns":1,"result":"test budget limit reached","api_error_status":"test_limit","total_cost_usd":0.01}'
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


def test_second_concurrent_invocation_exits_without_racing(tmp_path):
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
    env["DRIVER_CLAUDE_CMD"] = "claude"
    env["DRIVER_LOOP_SLEEP_S"] = "0"
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")

    proc1 = subprocess.Popen(
        ["bash", driver_copy], cwd=REPO_ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Give proc1 time to acquire the lock and start its round (the stub
    # itself sleeps 2s before replying) before launching the racer.
    time.sleep(0.5)

    proc2 = subprocess.Popen(
        ["bash", driver_copy], cwd=REPO_ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        rc2 = proc2.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc2.kill()
        proc2.wait(timeout=5)
        pytest.fail("second driver instance did not exit promptly — the "
                    "flock guard did not stop it from racing")
    assert rc2 == 0, "second instance should exit(0) cleanly, not error out"

    try:
        rc1 = proc1.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc1.kill()
        proc1.wait(timeout=5)
        pytest.fail("first driver instance never finished its one round")
    assert rc1 == 0

    driver_log = os.path.join(ws, "logs", "driver.log")
    with open(driver_log) as f:
        log_text = f.read()

    # The first process ran exactly one round to completion...
    assert "round 1 track=" in log_text, log_text
    assert "quota exhausted — stopping" in log_text, log_text
    # ...and the second process logged the lock message and never started
    # a round of its own (no "round 1" line appears twice, no round 2 at
    # all — a raced-in second process would have incremented the shared
    # counter and started a round with no result ever coming from a real
    # claude call, since it's PID 2's own private lockout, not round 2).
    assert "already holds" in log_text, log_text
    assert log_text.count("round 1 track=") == 1, log_text
    assert "round 2 track=" not in log_text, log_text

    with open(os.path.join(ws, "state", "round_counter")) as f:
        assert f.read().strip() == "1"

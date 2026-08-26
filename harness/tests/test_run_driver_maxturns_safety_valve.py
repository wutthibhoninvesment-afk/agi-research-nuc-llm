"""End-to-end test for run_driver.sh's round-151 max-turns-vs-quota fix.

Real production evidence (2026-08-26): rounds 146+147, then again 149+150
on a second restart, each did 140-160 real assistant turns of substantive
work (SWE-loop campaigns, language work) and hit `--max-turns 80` —
`error_max_turns`, not a quota/API error. The pre-fix safety valve treated
ANY 3 consecutive `classify_round_log() == "bad"` rounds identically,
logging "assuming weekly limit reached, stopping" regardless of WHY they
failed. A human operator took that message at face value, producing a
premature `state/FINAL-REPORT.md` and two manual restarts, later noted as
a "false-positive quota detection (not actual weekly limit)" — exactly the
outcome CURRICULUM.md's "stop only when the WEEKLY limit is reached"
policy says should not happen.

This test proves, with a real `bash run_driver.sh` subprocess and a fake
`claude` on PATH (no unit-level shortcut — the same discipline round 145's
`test_run_driver_selfexec.py` used), that a cluster of 3+ consecutive
max-turns deaths does NOT stop the driver, while the very next round that
is a genuine (non-max-turns) failure still does.
"""

import os
import shutil
import stat
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")

# Rounds 1-4: error_max_turns (a workload-driven death, matching the real
# round-146/147/149/150 shape). Round 5: a genuine, non-max-turns,
# non-429, non-5xx failure — the safety valve should stop HERE, once the
# 3-consecutive window (rounds 3,4,5) is no longer all-max-turns.
CLAUDE_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
WS="$DRIVER_TEST_WS"
COUNT_FILE="$WS/state/call_count"
N=$(( $(cat "$COUNT_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$N" > "$COUNT_FILE"

if [ "$N" -le 4 ]; then
  echo '{"type":"result","is_error":true,"subtype":"error_max_turns","num_turns":81,"stop_reason":"tool_use","result":"","api_error_status":null,"total_cost_usd":0.5}'
else
  echo '{"type":"result","is_error":true,"subtype":"error_other","num_turns":3,"result":"some genuine non-quota error","api_error_status":null,"total_cost_usd":0.01}'
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


def test_pure_max_turns_cluster_does_not_stop_but_a_real_failure_after_it_does(tmp_path):
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
        pytest.fail("driver did not stop within 45s — round 5's genuine "
                    "failure should have triggered a clean stop")

    driver_log = os.path.join(ws, "logs", "driver.log")
    with open(driver_log) as f:
        log_text = f.read()

    # Rounds 1-4 (a pure max-turns cluster, and one round PAST the first
    # 3-in-a-row window) all ran — proof the valve did not stop the driver
    # partway through, unlike the pre-fix behavior.
    for n in range(1, 5):
        assert f"round {n} track=" in log_text, log_text

    # The special, non-alarming message fires for the max-turns-only
    # windows (checked after round 3 and again after round 4), not the old
    # "assuming weekly limit reached" wording.
    assert log_text.count("consecutive max-turns deaths") >= 1, log_text
    assert "NOT a quota signal" in log_text

    # Round 5 (the first genuine, non-max-turns failure) breaks the
    # all-max-turns exemption for the window {3,4,5} and the valve fires
    # for real.
    assert "round 5 track=" in log_text, log_text
    assert "3 consecutive failures — assuming weekly limit reached, stopping" in log_text
    assert "round 6 track=" not in log_text, log_text
    assert proc.returncode == 0

    with open(os.path.join(ws, "state", "round_counter")) as f:
        assert f.read().strip() == "5"

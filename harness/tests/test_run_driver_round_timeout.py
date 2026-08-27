"""Tests for run_driver.sh's round-181 configurable round timeout.

Round 133 hardcoded the outer `timeout` wrapping each `claude -p` round
invocation to 2400s. Round 181 found LIVE, from `logs/driver.log`'s last 25
rounds, that 2400 had become the dominant cause of `interrupted=true`/
`status=?` round deaths: every non-interrupted round in that window
finished in <=2067s wall time, while every interrupted round's wall time
was >=2401s — a clean gap, zero counterexamples. Those rounds are killed
mid-flight with no `type:"result"` event, discarding 127-220 real assistant
turns of substantive work with no knowledge file / no research-state entry
(the exact "real work, no knowledge file" backlog pattern rounds
144/157/159/162/165/171/175 each independently had to reconcile after the
fact). The fix raises the default to 3300 and makes it overridable via
`DRIVER_ROUND_TIMEOUT_S` (mirroring `DRIVER_LOOP_SLEEP_S`/`DRIVER_WS`/
`DRIVER_CLAUDE_CMD`) so this can be tested without a real 55-minute wait.

Two things are proven here, both with a real `bash run_driver.sh`
subprocess and a fake `claude` on PATH (no unit-level shortcut, same
discipline as the other e2e driver tests):
1. The override actually takes effect: a stub that hangs well past a tiny
   `DRIVER_ROUND_TIMEOUT_S` gets killed by the outer timeout (not by the
   stub's own sleep completing), and the round is classified via the
   pre-existing "no result entry" safety valve rather than counted as one
   of the 3-consecutive-failure cluster.
2. The plain source-only default (no override) really is 3300, so a code
   change to the constant is caught even if no e2e test happens to exercise
   the exact new value.
"""

import os
import shutil
import stat
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")

# Round 1: emit one real assistant-shaped line (partial, in-progress-round
# content, matching the real production "interrupted" shape) then hang far
# longer than the tiny DRIVER_ROUND_TIMEOUT_S this test sets — the outer
# `timeout` must SIGTERM-kill this before the sleep or the second echo
# complete. Round 2: a genuine non-max-turns, non-5xx, non-429 stopping
# condition so the driver exits cleanly right after, no third round needed.
CLAUDE_STUB = r"""#!/usr/bin/env bash
set -uo pipefail
WS="$DRIVER_TEST_WS"
COUNT_FILE="$WS/state/call_count"
N=$(( $(cat "$COUNT_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$N" > "$COUNT_FILE"

if [ "$N" -eq 1 ]; then
  echo '{"type":"assistant","message":{"content":[{"type":"text","text":"working"}]},"timestamp":"2026-01-01T00:00:00Z"}'
  sleep 30
  echo '{"type":"result","is_error":false,"subtype":"success","num_turns":1,"result":"should never be reached","api_error_status":null,"total_cost_usd":0.01}'
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


def test_tiny_round_timeout_kills_a_hung_round_instead_of_waiting_for_it(tmp_path):
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
    env["DRIVER_ROUND_TIMEOUT_S"] = "2"
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.Popen(
        ["bash", driver_copy], cwd=REPO_ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # If the timeout override did NOT take effect, round 1's stub would
        # run its full 30s sleep before ever finishing — well past this
        # budget, which only allows for the 2s timeout plus round 2.
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        pytest.fail("driver did not stop within 20s — DRIVER_ROUND_TIMEOUT_S "
                    "override did not kill the hung round 1 stub")

    driver_log = os.path.join(ws, "logs", "driver.log")
    with open(driver_log) as f:
        log_text = f.read()

    assert "round 1 track=" in log_text, log_text
    assert (
        "round 1: file populated but no result entry — assuming Claude "
        "crash, skipping to next round"
    ) in log_text, log_text
    # Killed by the tiny timeout, not by its own 30s sleep completing.
    round1_rlog = os.path.join(ws, "logs", "round-001.json")
    with open(round1_rlog) as f:
        round1_text = f.read()
    assert '"type":"result"' not in round1_text
    assert '"type":"assistant"' in round1_text

    assert "round 2 track=" in log_text, log_text
    assert "round 3 track=" not in log_text, log_text
    assert proc.returncode == 0


def test_default_round_timeout_is_3300_and_override_env_var_wins():
    src = "DRIVER_SOURCE_ONLY=1 . " + DRIVER_SRC + "; echo \"$TIMEOUT_S\""
    default_out = subprocess.run(
        ["bash", "-c", src], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert default_out == "3300", default_out

    env = dict(os.environ)
    env["DRIVER_ROUND_TIMEOUT_S"] = "42"
    override_out = subprocess.run(
        ["bash", "-c", src], cwd=REPO_ROOT, capture_output=True, text=True, check=True, env=env,
    ).stdout.strip()
    assert override_out == "42", override_out


def test_default_max_turns_is_135_and_override_env_var_wins():
    """Round 205: `--max-turns` (the CLI's own graceful stop, distinct from
    the wall-clock TIMEOUT_S above) was hardcoded to 120 since round 151 —
    six real rounds (155/168/179/182/203/204) hit it and lost 120-132 tool
    calls of uncommitted work each time, 203/204 back to back for the first
    time. Raised to 135 (see run_driver.sh's own round-205 comment for the
    per-tool-call-rate headroom math against the 3300s wall clock) and made
    overridable, same DRIVER_SOURCE_ONLY convention as TIMEOUT_S above."""
    src = "DRIVER_SOURCE_ONLY=1 . " + DRIVER_SRC + "; echo \"$MAX_TURNS\""
    default_out = subprocess.run(
        ["bash", "-c", src], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert default_out == "135", default_out

    env = dict(os.environ)
    env["DRIVER_MAX_TURNS"] = "17"
    override_out = subprocess.run(
        ["bash", "-c", src], cwd=REPO_ROOT, capture_output=True, text=True, check=True, env=env,
    ).stdout.strip()
    assert override_out == "17", override_out

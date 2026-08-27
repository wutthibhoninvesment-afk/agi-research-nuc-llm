"""Tests for run_driver.sh's round-187 `--kill-after` fix.

Round 181 raised the outer `timeout` wrapping each `claude -p` round
invocation from 2400s to 3300s, on the assumption (measured over 7 real
`interrupted` rounds at the time) that the actual kill never landed more
than ~936s past the nominal deadline — plain `timeout` sends SIGTERM at the
deadline and then just waits for the command to actually exit, with no
forced-kill fallback unless told to.

Round 185 (four rounds later, real production evidence) busted that
assumption: a live Bash tool call inside the round hung with zero output
for ~48 minutes, and the round's own log shows the process didn't actually
die until ~1235s (20m35s) past the 3300s deadline — SIGTERM alone was not
enough to reliably unwind a genuinely stuck descendant promptly.

This test proves, with a real `bash run_driver.sh` subprocess and a fake
`claude` stub that deliberately IGNORES SIGTERM (traps it, matching a
descendant that doesn't unwind cleanly on the forwarded signal, not a
descendant that's merely slow), that `--kill-after` bounds the overrun
instead of leaving it open-ended: the round is force-killed (SIGKILL, which
cannot be trapped) well before its own 120s "natural completion" would
otherwise have written a marker file, and the driver correctly falls
through to the "no result entry, assuming crash" safety valve rather than
hanging indefinitely waiting for a plain `timeout` to give up on its own.
"""

import os
import shutil
import stat
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")

# Round 1: emit one real assistant-shaped line, then IGNORE SIGTERM (trap
# '' TERM) and spin in a sleep-1-second loop for up to 120s — long past
# both the tiny DRIVER_ROUND_TIMEOUT_S and DRIVER_KILL_AFTER_S this test
# sets. Each `sleep 1` iteration dies quickly to the process-group SIGTERM
# `timeout` sends at the deadline (sleep does not ignore TERM), but the
# trapping parent loop just spins to the next iteration — modeling a
# descendant that doesn't cleanly unwind on SIGTERM, not one that's merely
# slow. If the loop ever completes naturally, it writes a marker file the
# test asserts never appears. Round 2: a genuine, non-max-turns, non-5xx,
# non-429 stopping condition so the driver exits cleanly right after.
CLAUDE_STUB = r"""#!/usr/bin/env bash
set -uo pipefail
WS="$DRIVER_TEST_WS"
COUNT_FILE="$WS/state/call_count"
N=$(( $(cat "$COUNT_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$N" > "$COUNT_FILE"

if [ "$N" -eq 1 ]; then
  trap '' TERM
  echo '{"type":"assistant","message":{"content":[{"type":"text","text":"working"}]},"timestamp":"2026-01-01T00:00:00Z"}'
  n=0
  while [ "$n" -lt 120 ]; do
    sleep 1 2>/dev/null
    n=$((n+1))
  done
  touch "$WS/state/round1_woke_naturally"
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


def test_kill_after_force_kills_a_sigterm_ignoring_round(tmp_path):
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
    env["DRIVER_KILL_AFTER_S"] = "2"
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.Popen(
        ["bash", driver_copy], cwd=REPO_ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # Without --kill-after, this SIGTERM-ignoring stub would run its
        # full ~120s loop before the round ever finished — well past
        # this budget, which only allows for the 2s timeout + 2s
        # kill-after grace period + round 2.
        proc.wait(timeout=25)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        pytest.fail("driver did not stop within 25s — --kill-after did "
                    "not force-kill the SIGTERM-ignoring round 1 stub")

    driver_log = os.path.join(ws, "logs", "driver.log")
    with open(driver_log) as f:
        log_text = f.read()

    assert "round 1 track=" in log_text, log_text
    assert (
        "round 1: file populated but no result entry — assuming Claude "
        "crash, skipping to next round"
    ) in log_text, log_text
    # The stub never reached its own 120s natural-completion marker —
    # it was SIGKILLed by --kill-after well before that.
    assert not os.path.exists(os.path.join(ws, "state", "round1_woke_naturally"))
    round1_rlog = os.path.join(ws, "logs", "round-001.json")
    with open(round1_rlog) as f:
        round1_text = f.read()
    assert '"type":"result"' not in round1_text
    assert '"type":"assistant"' in round1_text

    assert "round 2 track=" in log_text, log_text
    assert "round 3 track=" not in log_text, log_text
    assert proc.returncode == 0


def test_default_kill_after_is_120_and_override_env_var_wins():
    src = "DRIVER_SOURCE_ONLY=1 . " + DRIVER_SRC + "; echo \"$KILL_AFTER_S\""
    default_out = subprocess.run(
        ["bash", "-c", src], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert default_out == "120", default_out

    env = dict(os.environ)
    env["DRIVER_KILL_AFTER_S"] = "7"
    override_out = subprocess.run(
        ["bash", "-c", src], cwd=REPO_ROOT, capture_output=True, text=True, check=True, env=env,
    ).stdout.strip()
    assert override_out == "7", override_out

"""End-to-end test for run_driver.sh's round-145 self-re-exec fix.

Round 139 found the live driver had been executing a stale in-memory
parse of the `while ... do ... done` loop in this script for 12+ rounds:
bash parses a compound command like that ONCE and never re-reads it from
disk, so on-disk fixes (rounds 127/133) never reached the live process
without an external kill+relaunch. Round 145 replaced the implicit
loop-around at the bottom of the body with `exec bash "$0" "$@"`, which
re-execs the SAME process (no new PID) reading the CURRENT file content
each round.

This test proves that specific property end to end, with a real `bash
run_driver.sh` subprocess and a fake `claude` on PATH — not just that the
script's syntax is valid. It edits the on-disk `DRIVER_VERSION` line
BETWEEN round 1 and round 2 (from inside the stub, so there's no timing
race: the edit happens synchronously while `claude` is "running", i.e.
strictly before the loop body's `exec` line for that round is even
reached) and asserts round 2's log line reflects the edit while the
process never restarted (no new driver.log "=== driver started ===" line
beyond the first).
"""

import os
import shutil
import stat
import subprocess
import sys
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")

CLAUDE_STUB = r"""#!/usr/bin/env bash
# Fake `claude` CLI for test_run_driver_selfexec.py. Ignores all args,
# always writes a stream-json-shaped log to stdout. Round 1: edits
# DRIVER_VERSION in the driver script (proves the self-exec round 2 will
# read the edit) then reports success. Round 2: reports a non-5xx,
# non-429 "error" whose status text contains "limit" so the outer driver
# stops cleanly right after — no infinite loop, no third round needed.
set -euo pipefail
WS="$DRIVER_TEST_WS"
COUNT_FILE="$WS/state/call_count"
N=$(( $(cat "$COUNT_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$N" > "$COUNT_FILE"

if [ "$N" -eq 1 ]; then
  sed -i.bak 's/DRIVER_VERSION="[^"]*"/DRIVER_VERSION="v2-edited-mid-run"/' "$WS/run_driver.sh"
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


def test_selfexec_picks_up_mid_run_edit_without_restart(tmp_path):
    # No pytest-timeout plugin in this repo (round 144 confirmed none
    # exists) — the real bound is the subprocess.wait(timeout=45) below.
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
    # Round 157: production now runs `claude` through a local wrapper
    # script (this host has no global `claude`); point the driver back at
    # a bare `claude` so it resolves through this test's PATH-prepended
    # stub dir instead of a `./claude-wrapper.sh` that doesn't exist in
    # the copied tmp_path workspace.
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
        log_text = f.read()

    # Proof #1: the "driver started" banner reprints once PER ROUND (it's
    # at the top of the script, before the loop — `exec` re-enters there
    # every time), which is the expected, correct signature of re-exec
    # under this design: 2 rounds ran, so it appears exactly twice, each
    # time with the right "resuming after round N-1".
    assert log_text.count("=== driver started;") == 2, log_text
    assert "resuming after round 0 ===" in log_text
    assert "resuming after round 1 ===" in log_text

    # Proof #1b: despite re-entering the top of the script twice, the OS
    # process itself never restarted — `exec` replaces the running
    # process's image in place (no fork, no new PID; see `man bash`).
    # `$$` is read fresh by each re-exec'd bash instance from its own
    # getpid(), so if a naive fix had killed and relaunched a NEW driver
    # process per round instead of using `exec`, these two values would
    # differ. Read directly from the driver's own per-round log line
    # (not inferred through the `claude` child's $PPID, which would be
    # `timeout`'s PID instead of the driver's on a machine that has GNU
    # `timeout`/`gtimeout` installed — this repo's Mac has neither, but
    # the assertion should not depend on that).
    def _pid_from_round_line(n):
        line = [l for l in log_text.splitlines() if f"round {n} track=" in l][0]
        marker = "pid="
        return line[line.index(marker) + len(marker):].split()[0]

    pid1, pid2 = _pid_from_round_line(1), _pid_from_round_line(2)
    assert pid1 == pid2, (pid1, pid2, log_text)
    assert int(pid1) == proc.pid

    # Proof #2: round 1 ran under the ORIGINAL version string (whatever it
    # currently is on disk — this test proves the self-exec MECHANISM, not
    # a specific version string, so it reads the source file instead of
    # pinning a value that goes stale every time DRIVER_VERSION is bumped).
    with open(DRIVER_SRC) as f:
        original_version = [l for l in f if l.strip().startswith("DRIVER_VERSION=")][0]
    original_version = original_version.split("=", 1)[1].strip().strip('"')
    assert "round 1 track=" in log_text
    round1_line = [l for l in log_text.splitlines() if "round 1 track=" in l][0]
    assert f"driver_version={original_version}" in round1_line, round1_line

    # ...and round 2 — produced by the SAME process, no restart — reflects
    # the edit the round-1 stub made to the on-disk script. This is the
    # actual property round 139's redeploy-watcher workaround existed to
    # compensate for: an on-disk edit now takes effect on the very next
    # round with no external kill+relaunch.
    assert "round 2 track=" in log_text
    round2_line = [l for l in log_text.splitlines() if "round 2 track=" in l][0]
    assert "driver_version=v2-edited-mid-run" in round2_line, round2_line

    # Proof #3: the loop actually stopped (round 2's "limit" status), not
    # killed by the test's own timeout — a real stop, and only 2 rounds.
    assert "quota exhausted — stopping" in log_text
    assert "round 3 track=" not in log_text
    assert proc.returncode == 0

    # state/round_counter ends on round 2, matching P5's "no double-run,
    # no gap" property from round 139 — still true under self-exec.
    with open(os.path.join(ws, "state", "round_counter")) as f:
        assert f.read().strip() == "2"

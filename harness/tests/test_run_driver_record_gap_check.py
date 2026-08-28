"""End-to-end test for run_driver.sh's round-253 record-gap check.

Round 171 (skills B) built `check_round_recorded.py` — a detector for the
"a round ran real turns, got logged `success`, and still left zero trace in
state/research-state.md/knowledge/git" pattern (the
`one-shot-agent-no-background-wait` mechanism) — but round 171/195's own
backlog explicitly named it "a detector, not an enforcer... still requires
a human/round to actually RUN it" and flagged wiring it into
`run_driver.sh`'s own loop as harness(A)'s file to touch. This round closes
that: the driver now runs the detector once per round, BEFORE that round's
own "start" line lands in driver.log (so the round currently starting never
flags itself), logs PASS/FOUND, and — since logging alone reproduces the
same "someone has to go read it" gap — appends any finding directly to
that round's own prompt.

Same discipline as `test_run_driver_whence_health_check.py`: real `bash
run_driver.sh` subprocesses, a real `claude` PATH stub (extended here to
capture the exact argv it was invoked with, so the prompt-injection half
of this feature is verified against what the CLI actually received, not
just against driver.log's own summary line), and a controlled fake
`skills/session-inheritance-audit/scripts/check_round_recorded.py`
workspace. Covers: (1) the script absent entirely — the shape every OTHER
`test_run_driver_*.py` file's tmp_path workspace already uses; (2) present
with zero gaps (clean prior round) — PASS logged, no note injected; (3)
present with a real gap (a prior round's driver.log start-line with no
matching research-state.md heading) — FOUND logged AND the note appears in
the captured prompt actually sent to `claude`.
"""

import os
import shutil
import stat
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")
REAL_CHECK_SCRIPT = os.path.join(
    REPO_ROOT, "skills", "session-inheritance-audit", "scripts",
    "check_round_recorded.py",
)

# Same two-round shape as test_run_driver_whence_health_check.py: round 1
# succeeds, round 2's status text contains "limit" so the outer driver stops
# cleanly right after, keeping the real `bash run_driver.sh` subprocess well
# inside the 45s wait. Extended to dump its own argv (one call per line,
# delimited) so the test can inspect exactly what prompt text `claude` was
# invoked with, not just driver.log's own summary of it.
CLAUDE_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
WS="$DRIVER_TEST_WS"
COUNT_FILE="$WS/state/call_count"
N=$(( $(cat "$COUNT_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$N" > "$COUNT_FILE"

{
  echo "===CALL $N ARGC=$#==="
  for a in "$@"; do printf '%s\x1e' "$a"; done
  echo
} >> "$WS/state/captured_args.log"

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


def _install_real_check_script(ws):
    """Copy the real check_round_recorded.py into the tmp_path workspace at
    its real relative location, so this test exercises the actual detector
    (not a fake stand-in) end to end — only the workspace it scans (driver
    log / research-state.md / knowledge dir) is synthetic."""
    target_dir = os.path.join(ws, "skills", "session-inheritance-audit", "scripts")
    os.makedirs(target_dir, exist_ok=True)
    shutil.copyfile(REAL_CHECK_SCRIPT, os.path.join(target_dir, "check_round_recorded.py"))


def _run_driver(tmp_path, start_round_counter=0):
    ws = str(tmp_path)
    os.makedirs(os.path.join(ws, "state"), exist_ok=True)
    os.makedirs(os.path.join(ws, "logs"), exist_ok=True)
    if start_round_counter:
        with open(os.path.join(ws, "state", "round_counter"), "w") as f:
            f.write(str(start_round_counter))
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
        log_text = f.read()
    args_path = os.path.join(ws, "state", "captured_args.log")
    args_text = ""
    if os.path.isfile(args_path):
        with open(args_path) as f:
            args_text = f.read()
    return log_text, args_text


def _first_call_prompt(args_text):
    """Extract the `-p` argument's value from the first captured claude
    invocation (argv[0] is "-p", argv[1] is the prompt string — both
    delimited by \\x1e per CLAUDE_STUB above). The header line
    ("===CALL N ARGC=...===") is written by its own `echo`, immediately
    followed (same line boundary) by the first \\x1e-delimited argv dump,
    so it must be stripped by newline first — splitting the whole block on
    \\x1e alone merges the header text with argv[0]."""
    first_call = args_text.split("===CALL 2")[0]
    _header, _, argv_blob = first_call.partition("\n")
    args = [a for a in argv_blob.split("\x1e") if a]
    assert args[0] == "-p", args[:2]
    return args[1]


def test_record_gap_check_skipped_when_script_absent(tmp_path):
    # No skills/ tree at all — the exact shape every other
    # test_run_driver_*.py test's tmp_path workspace already uses. Proves
    # that shape's silence on this feature is real no-op behaviour, not an
    # untested assumption.
    log_text, args_text = _run_driver(tmp_path)
    assert ": record-check" not in log_text, log_text
    prompt = _first_call_prompt(args_text)
    assert "record-gap check" not in prompt, prompt


def test_record_gap_check_passes_on_clean_history(tmp_path):
    ws = str(tmp_path)
    _install_real_check_script(ws)
    # No prior driver.log entries at all (this is the very first round) —
    # the detector has nothing to flag for round 1's OWN check, which runs
    # before round 1's "start" line is even written. (Round 2's check will
    # legitimately flag round 1 itself as a gap here, since this stub
    # `claude` never writes a real research-state.md entry the way a real
    # round would — that's a test-harness artifact of the 2-round stop
    # shape every test_run_driver_*.py file shares, not a false positive in
    # the detector; only round 1's own check matters for "clean history".)
    log_text, args_text = _run_driver(tmp_path)
    assert "round 1: record-check PASS" in log_text, log_text
    prompt = _first_call_prompt(args_text)
    assert "record-gap check" not in prompt, prompt


def test_record_gap_check_finds_gap_and_injects_note_into_prompt(tmp_path):
    ws = str(tmp_path)
    os.makedirs(os.path.join(ws, "state"), exist_ok=True)
    os.makedirs(os.path.join(ws, "logs"), exist_ok=True)
    _install_real_check_script(ws)
    os.makedirs(os.path.join(ws, "knowledge"), exist_ok=True)
    # Seed driver.log with a PRIOR round (round 7) that started and
    # succeeded per the driver's own log, but has no research-state.md
    # heading and no knowledge file — exactly the round-248/249/250 shape
    # (a clean end_turn that still lost its own work). Start the round
    # counter at 7 so this round's OWN start line (round 8) is written
    # only AFTER the gap check below already ran and read round 7 as the
    # most recent entry.
    driver_log_path = os.path.join(ws, "logs", "driver.log")
    with open(driver_log_path, "w") as f:
        f.write("[2026-01-01 00:00:00] round 7 track=NUC-integration(E) start (driver_version=test) pid=1\n")
        f.write("[2026-01-01 00:05:00] round 7: success\n")
    with open(os.path.join(ws, "state", "research-state.md"), "w") as f:
        f.write("# Research State\n\n## Round log\n")

    log_text, args_text = _run_driver(tmp_path, start_round_counter=7)

    assert "round 8: record-check FOUND gap(s)" in log_text, log_text
    assert "round 7" in log_text, log_text

    prompt = _first_call_prompt(args_text)
    assert "record-gap check" in prompt, prompt
    assert "round 7" in prompt, prompt
    assert "NUC-integration(E)" in prompt, prompt

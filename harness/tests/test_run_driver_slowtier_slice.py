"""End-to-end + unit coverage for round 439's slow-tier slice check.

The FIFTH per-round driver check, and the first one that spends wall clock
instead of reporting a number. Same guarded-on-existence / diagnostic-only
shape as rounds 241/247/363's three, with one deliberate difference that has
its own test below: it runs SEQUENTIALLY, after the other four have been
waited on, because `nproc` is 1 here and the slice writes a `seconds` field
that `slowtier.plan()` reads back as a cost estimate. A number inflated by
our own concurrency would re-order every future plan.
"""

import os
import shutil
import stat
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")
SLICE_SRC = os.path.join(REPO_ROOT, "harness", "run_slowtier_slice.sh")

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

SUMMARY = ("slow tier: 31 files / 32 units, 1 conclusive against checkout "
           "abc123 (3% recall), 0 failing")


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
        pytest.fail("driver did not stop within 45s")

    with open(os.path.join(ws, "logs", "driver.log")) as f:
        return f.read()


# --------------------------------------------------------------- the driver --

def test_slice_is_skipped_when_the_script_is_absent(tmp_path):
    """Round 241's degradation guarantee: a workspace with no harness tree
    logs nothing rather than erroring."""
    log_text = _run_driver(tmp_path)
    assert ": slowtier-slice" not in log_text, log_text


def test_ok_line_quotes_the_recall_summary(tmp_path):
    """The whole point of the check is the number that moves, so the driver
    line must carry the script's LAST line — which the script guarantees is
    `slowtier status`'s summary, not a per-unit row."""
    _make_script(str(tmp_path), "harness", "run_slowtier_slice.sh",
                 'echo "ran test_swe_coverage.py"\necho "%s"\nexit 0' % SUMMARY)
    log_text = _run_driver(tmp_path)
    assert "round 1: slowtier-slice OK (%s)" % SUMMARY in log_text, log_text


def test_a_script_that_cannot_run_reads_as_error(tmp_path):
    """Round 349's FAIL-vs-ERROR lesson, applied at this call site: "the tier
    has a red" and "the checker is broken" must not share a word. The script
    always exits 0 by construction, so a non-zero rc here means the script
    itself could not run."""
    _make_script(str(tmp_path), "harness", "run_slowtier_slice.sh",
                 'echo "python3: cannot open file"\nexit 3')
    log_text = _run_driver(tmp_path)
    assert "round 1: slowtier-slice ERROR" in log_text, log_text
    assert "cannot open file" in log_text, log_text


def test_a_red_slice_never_stops_the_driver(tmp_path):
    """Diagnostic only. A red slow-tier unit is the finding a LATER round
    should fix; if it halted the program, the first real red would stop the
    research instead of directing it."""
    _make_script(str(tmp_path), "harness", "run_slowtier_slice.sh",
                 'echo "slow tier: 31 files / 32 units, 1 conclusive, 1 failing"\nexit 0')
    log_text = _run_driver(tmp_path)
    assert "1 failing" in log_text, log_text
    assert "round 2 track=" in log_text, log_text   # the driver went on to the next round


def test_the_slice_runs_after_the_other_four_checks_are_waited_on():
    """SEQUENTIAL, and the reason is measured: `nproc` is 1 on this box and
    round 434 recorded two concurrent pytest processes each taking roughly
    twice their solo time. The slice writes `seconds` into the ledger and
    `plan()` reads it back as a cost estimate, so a self-inflated number
    would misdirect every future plan. The other four are concurrent with
    each other because none of them writes a number anything later reads."""
    src = open(DRIVER_SRC).read()
    call_site = src.index('SLOWTIER_SCRIPT="$WS/harness/run_slowtier_slice.sh"')
    for pid in ('"$HEALTH_PID"', '"$WHENCE_PID"', '"$SKILLS_PID"', '"$NUC_PID"'):
        assert src.index("wait " + pid) < call_site, pid


def test_the_registry_declares_the_script_at_its_real_call_site():
    """Round 435 landed two entry points undeclared and three health checks
    reported it for four rounds. The `via` line number is checked, not just
    the key: a registry that names the wrong line is how a `wired` status
    stops meaning anything."""
    import json
    reg = json.load(open(os.path.join(REPO_ROOT, "harness", "wiring-registry.json")))
    entry = reg["entry_points"]["harness/run_slowtier_slice.sh"]
    assert entry["status"] == "wired"
    path, _, lineno = entry["via"].partition(":")
    assert path == "run_driver.sh"
    line = open(os.path.join(REPO_ROOT, path)).read().splitlines()[int(lineno) - 1]
    assert "run_slowtier_slice.sh" in line, line


# --------------------------------------------------------------- the script --

def test_the_off_switch_keeps_the_recall_line(tmp_path):
    """`DRIVER_SLOWTIER_BUDGET_S=0` skips the slice and still prints the
    recall. Switching the spend off must not also switch off the number that
    says what it is costing — that is how `slowtier status` came to be
    printed for 99 rounds with nothing acting on it, and an invisible
    off-switch is the same failure with the sign flipped."""
    env = dict(os.environ)
    env["DRIVER_SLOWTIER_BUDGET_S"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    r = subprocess.run(["bash", SLICE_SRC], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    assert any("SKIPPED" in l for l in lines), r.stdout
    assert lines[-1].startswith("slow tier:"), r.stdout


def test_the_last_line_is_the_summary_not_a_per_unit_row():
    """`report_text` puts the summary FIRST and a 32-row table after it, so
    the script takes line 1, not `tail -n 1`. Tailing it would log "NOTE: 32
    unit(s) are NOT evidence about this checkout" every round and never the
    number that moves."""
    body = open(SLICE_SRC).read()
    assert "status | sed -n '1p'" in body, body
    assert "status | tail" not in body, body

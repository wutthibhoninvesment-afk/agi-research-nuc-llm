"""End-to-end + unit coverage for round 469's whence-slow slice check.

The SIXTH per-round driver check, and the second that spends wall clock
instead of reporting a number. Deliberately the same shape as round 439's
slow-tier slice, including the ledger-landing commit round 457 added to it,
with one number that differs and has its own test: the default budget is
120 s rather than 240 s, and the two slices are SEQUENTIAL with each other
because `nproc` is 1 and both write a `seconds` field their planners read
back as a cost estimate.
"""

import json
import os
import shutil
import stat
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")
SLICE_SRC = os.path.join(REPO_ROOT, "harness", "run_whenceslow_slice.sh")
FAST_SRC = os.path.join(REPO_ROOT, "harness", "run_tests_fast.sh")

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

SUMMARY = ("whence slow tier: 27 units / 102 marked (AST), 3 conclusive "
           "against subject abc123 (11% recall), 0 failing")


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
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        pytest.fail("driver did not stop within 60s")

    with open(os.path.join(ws, "logs", "driver.log")) as f:
        return f.read()


# --------------------------------------------------------------- the driver --

def test_slice_is_skipped_when_the_script_is_absent(tmp_path):
    """Round 241's degradation guarantee: a workspace with no harness tree
    logs nothing rather than erroring."""
    assert ": whenceslow-slice" not in _run_driver(tmp_path)


def test_ok_line_quotes_the_recall_summary(tmp_path):
    """The point of the check is the number that moves, so the driver line
    carries the script's LAST line — which the script guarantees is
    `whenceslow status`'s summary, not a per-unit row."""
    _make_script(str(tmp_path), "harness", "run_whenceslow_slice.sh",
                 'echo "ran test_v29.py"\necho "%s"\nexit 0' % SUMMARY)
    log_text = _run_driver(tmp_path)
    assert "round 1: whenceslow-slice OK (%s)" % SUMMARY in log_text, log_text


def test_a_script_that_cannot_run_reads_as_error(tmp_path):
    """Round 349's FAIL-vs-ERROR lesson: "the tier has a red" and "the
    checker is broken" must not share a word. The script always exits 0 by
    construction, so non-zero here means the script itself could not run."""
    _make_script(str(tmp_path), "harness", "run_whenceslow_slice.sh",
                 'echo "python3: cannot open file"\nexit 3')
    log_text = _run_driver(tmp_path)
    assert "round 1: whenceslow-slice ERROR" in log_text, log_text
    assert "cannot open file" in log_text, log_text


def test_a_red_slice_never_stops_the_driver(tmp_path):
    """Diagnostic only. A red `whence_slow` unit is the finding a LATER round
    should fix; halting on it would stop the research instead of directing
    it — and this tier has not been run in the program's history, so the
    first slice is the one most likely to find something."""
    _make_script(str(tmp_path), "harness", "run_whenceslow_slice.sh",
                 'echo "%s"\nexit 0' % SUMMARY.replace("0 failing", "2 failing"))
    log_text = _run_driver(tmp_path)
    assert "whenceslow-slice OK" in log_text
    assert "2 failing" in log_text, log_text
    assert "round 2 track=" in log_text, log_text   # it went on to the next round


def test_the_slice_runs_after_the_slow_tier_slice(tmp_path):
    """SEQUENTIAL with the other measuring check, not beside it. `nproc` is 1
    here; two pytest processes at once each take about twice their solo time,
    and BOTH slices write a `seconds` their planners read back as a cost
    estimate, so concurrency would re-order every future plan in both
    tiers."""
    src = open(DRIVER_SRC).read()
    assert src.index('SLOWTIER_SCRIPT="$WS/harness/run_slowtier_slice.sh"') \
        < src.index('WHENCESLOW_SCRIPT="$WS/harness/run_whenceslow_slice.sh"')


def test_the_slice_runs_after_the_four_reporting_checks_are_waited_on():
    src = open(DRIVER_SRC).read()
    call_site = src.index('WHENCESLOW_SCRIPT="$WS/harness/run_whenceslow_slice.sh"')
    for pid in ('"$HEALTH_PID"', '"$WHENCE_PID"', '"$SKILLS_PID"', '"$NUC_PID"'):
        assert src.index("wait " + pid) < call_site, pid


def test_the_registry_declares_both_entry_points_at_their_real_call_sites():
    """Round 435 landed two entry points undeclared and three health checks
    reported it for four rounds. The `via` LINE is checked, not just the key:
    a registry naming the wrong line is how a `wired` status stops meaning
    anything."""
    reg = json.load(open(os.path.join(REPO_ROOT, "harness",
                                      "wiring-registry.json")))
    for key, needle in (("harness/run_whenceslow_slice.sh",
                         "run_whenceslow_slice.sh"),
                        ("harness/whenceslow.py", "whenceslow.py")):
        entry = reg["entry_points"][key]
        assert entry["status"] == "wired", key
        path, _, lineno = entry["via"].partition(":")
        line = open(os.path.join(REPO_ROOT, path)).read().splitlines()[int(lineno) - 1]
        assert needle in line, (key, line)


def test_the_driver_lands_the_ledger_row_it_wrote(tmp_path):
    """Round 457's rule, applied to the new ledger from the start rather than
    after eighteen orphaned rows. The commit subject must NOT contain
    "round N": `check_round_recorded.committed_per_git_log` greps subjects
    for that substring to answer "did round N commit anything?", and a driver
    commit naming the round would answer YES for a round that committed
    nothing itself."""
    src = open(DRIVER_SRC).read()
    i = src.index("driver: whence-slow ledger append")
    subject_line = src[src.rindex("\n", 0, i) + 1:src.index("\n", i)]
    assert "$ROUND" not in subject_line, subject_line
    assert "state/whence-slow-ledger.jsonl" in src
    # and no `git add`: an untracked ledger must degrade to "the next round
    # lands it by hand", never to the driver deciding to track a file.
    block = src[src.index("WHENCESLOW_LEDGER_REL"):
                src.index("# Safety valve (round 150+)")]
    assert "git -C \"$WS\" add" not in block, block
    assert "ls-files --error-unmatch" in block


# --------------------------------------------------------------- the script --

def test_the_off_switch_keeps_the_recall_line():
    """`DRIVER_WHENCESLOW_BUDGET_S=0` skips the slice and still prints the
    recall. Switching the spend off must not switch off the number that says
    what it is costing — an invisible off-switch is the same failure as an
    unread status line, with the sign flipped."""
    env = dict(os.environ)
    env["DRIVER_WHENCESLOW_BUDGET_S"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    r = subprocess.run(["bash", SLICE_SRC], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    assert any("SKIPPED" in l for l in lines), r.stdout
    assert lines[-1].startswith("whence slow tier:"), r.stdout


def test_the_last_line_is_the_summary_not_a_per_unit_row():
    """`report_text` puts the summary FIRST and a 27-row table after it, so
    the script takes line 1. Tailing it would log "NOTE: 27 unit(s) are NOT
    evidence about this checkout" every round and never the number that
    moves — the exact defect round 439 named in the slow-tier script."""
    body = open(SLICE_SRC).read()
    assert "status | sed -n '1p'" in body, body
    assert "status | tail" not in body, body


def test_the_default_budget_is_declared_and_smaller_than_the_slow_tiers():
    """120, not 240. The added per-round cost is 120 s on top of the
    slow-tier slice's 240 — and the script says so in prose, because a cap
    that is not printed reads as "we covered everything"."""
    body = open(SLICE_SRC).read()
    assert 'DRIVER_WHENCESLOW_BUDGET_S:-120' in body
    assert "360 s" in body, "the combined per-round budget must be stated"


def test_the_fast_tier_echoes_the_recall_after_its_own_sentinel():
    """Round 379's boundary: everything a reader could mistake for THIS run's
    result goes after `MEASURED_END_SENTINEL`, or `driver_health` quotes a
    recorded number as the suite's own verdict — which it did, for 38
    consecutive health-check lines."""
    body = open(FAST_SRC).read()
    from harness.driver_health import MEASURED_END_SENTINEL
    assert body.index(MEASURED_END_SENTINEL) \
        < body.index("harness/whenceslow.py status")
    assert "|| true" in body[body.index("harness/whenceslow.py status"):
                             body.index("harness/whenceslow.py status") + 120]

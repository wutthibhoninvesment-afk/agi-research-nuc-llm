"""End-to-end test for run_driver.sh's round-363 skills corpus health check.

Third check, same guarded-on-existence / concurrent / diagnostic-only shape
as round 241's harness check and round 247's whence check. Same discipline as
`test_run_driver_whence_health_check.py`: real `bash run_driver.sh`
subprocesses, a real `claude` PATH stub, a controlled fake
`skills/run_checks_fast.sh` planted in the tmp_path workspace.

What is specific to THIS check and needs its own coverage: its driver.log
line is formatted by `skills/skill-authoring/scripts/corpus_check.py --line`,
not by `driver_health.health_line`, because corpus-check's exit code IS the
verdict (0 clean / 1 a rule was violated / 2 a checker could not run) and the
shared classifier is pytest-shaped. So the tests below stage the REAL
`corpus_check.py` to exercise that formatter, plus one that omits it to prove
the inline bash fallback still logs a line — the round-241 degradation
guarantee, which this call site must not break.
"""

import os
import shutil
import stat
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")
CORPUS_CHECK_SRC = os.path.join(REPO_ROOT, "skills", "skill-authoring",
                                "scripts", "corpus_check.py")

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


def _stage_real_formatter(ws):
    d = os.path.join(ws, "skills", "skill-authoring", "scripts")
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(CORPUS_CHECK_SRC, os.path.join(d, "corpus_check.py"))


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


SUMMARY = "corpus-check: 5 checker(s), 0 error(s), 1 warning(s)"


def test_skills_check_skipped_when_script_absent(tmp_path):
    log_text = _run_driver(tmp_path)
    assert ": skills-check" not in log_text, log_text


def test_pass_line_carries_the_summary_including_the_warning_count(tmp_path):
    # The warning count riding in the PASS line is load-bearing: warnings do
    # not set the exit code (a carried debt must not make this cry wolf), so
    # this line is the only place a carried warning stays visible per round.
    _stage_real_formatter(str(tmp_path))
    _make_script(str(tmp_path), "skills", "run_checks_fast.sh",
                 'echo "%s"\nexit 0' % SUMMARY)
    log_text = _run_driver(tmp_path)
    assert "round 1: skills-check PASS (%s)" % SUMMARY in log_text, log_text


def test_rule_violation_reads_as_fail_not_as_a_broken_runner(tmp_path):
    _stage_real_formatter(str(tmp_path))
    _make_script(str(tmp_path), "skills", "run_checks_fast.sh",
                 'echo "error: P001 foo: 0 positive case(s)"\n'
                 'echo "corpus-check: 5 checker(s), 1 error(s), 0 warning(s)"\n'
                 'exit 1')
    log_text = _run_driver(tmp_path)
    assert "round 1: skills-check FAIL" in log_text, log_text
    assert "violates its own rules" in log_text, log_text
    assert "P001" in log_text, log_text


def test_a_checker_that_could_not_run_reads_as_error_not_fail(tmp_path):
    # Round 349's FAIL-vs-ERROR distinction, which round 348 paid for once:
    # "the corpus is wrong" and "the tool is broken" must not share a word.
    _stage_real_formatter(str(tmp_path))
    _make_script(str(tmp_path), "skills", "run_checks_fast.sh",
                 'echo "corpus-check: 5 checker(s), 0 error(s), 0 warning(s); '
                 'COULD NOT RUN: xref_check"\nexit 2')
    log_text = _run_driver(tmp_path)
    assert "round 1: skills-check ERROR" in log_text, log_text
    assert "skills-check FAIL" not in log_text, log_text


def test_line_still_logged_when_the_formatter_itself_is_missing(tmp_path):
    # No corpus_check.py staged: the inline bash fallback must still produce a
    # line. Round 241's degradation guarantee — a workspace missing a helper
    # loses formatting, never the record.
    _make_script(str(tmp_path), "skills", "run_checks_fast.sh",
                 'echo "%s"\nexit 0' % SUMMARY)
    log_text = _run_driver(tmp_path)
    assert "round 1: skills-check PASS (%s)" % SUMMARY in log_text, log_text


def test_all_three_health_checks_are_independent(tmp_path):
    _stage_real_formatter(str(tmp_path))
    _make_script(str(tmp_path), "harness", "run_tests_fast.sh",
                 'echo "373 passed, 176 deselected in 33.54s"\nexit 0')
    _make_script(str(tmp_path), os.path.join("languages", "whence"),
                 "run_tests_fast.sh",
                 'echo "840 passed, 35 deselected in 23.26s"\nexit 0')
    _make_script(str(tmp_path), "skills", "run_checks_fast.sh",
                 'echo "%s"\nexit 0' % SUMMARY)
    log_text = _run_driver(tmp_path)
    assert "round 1: health-check PASS (373 passed, 176 deselected in 33.54s)" in log_text, log_text
    assert "round 1: whence-health-check PASS (840 passed, 35 deselected in 23.26s)" in log_text, log_text
    assert "round 1: skills-check PASS (%s)" % SUMMARY in log_text, log_text

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


# --------------------------------------------------------------------------
# Round 373 — the injected NOTE's preamble must describe the check that
# actually ran. It did not: `check_round_recorded.py` grew gap shapes in
# rounds 259, 273, 291 and 373, and the preamble kept saying only shape 1
# ("the round(s) below ran per logs/driver.log but have no
# state/research-state.md entry yet"). Round 373's own injected note is the
# live proof — it opened with that sentence and then listed three DIRTY
# PATHS, none of which is a round. Nothing asserted the correspondence, so
# nothing reported the drift for four shapes and ~100 rounds.
# --------------------------------------------------------------------------

_ORDINALS = ["second", "third", "fourth", "fifth", "sixth", "seventh",
             "eighth", "ninth", "tenth"]


def _preamble():
    with open(DRIVER_SRC) as f:
        driver = f.read()
    start = driver.index("NOTE (automated record-gap check")
    return driver[start:driver.index("$RECORD_CHECK_OUT", start)]


def _implemented_shape_count():
    """Shapes the checker's own module docstring claims, counted from its
    'Round N added a <ORDINAL>[,] ... gap shape' sentences (+1 for the
    original shape, which predates the numbering)."""
    with open(REAL_CHECK_SCRIPT) as f:
        doc = f.read()
    open_q = doc.index('"""')
    doc = doc[open_q:doc.index('"""', open_q + 3)].lower()
    n = 1
    for word in _ORDINALS:
        if "added a %s" % word in doc:
            n += 1
        else:
            break
    return n


def test_injected_note_preamble_enumerates_every_implemented_gap_shape():
    preamble = _preamble()
    expected = _implemented_shape_count()
    assert expected >= 5, "docstring shape count regressed: %d" % expected
    enumerated = ["(%d)" % i for i in range(1, expected + 1)]
    for marker in enumerated:
        assert marker in preamble, (
            "run_driver.sh's injected NOTE enumerates fewer gap shapes than "
            "check_round_recorded.py implements (%d) — %s missing. A round "
            "reading the note is told it is looking at shape 1 whatever the "
            "check actually found." % (expected, marker))
    assert "(%d)" % (expected + 1) not in preamble, (
        "the NOTE enumerates MORE shapes than the checker implements")


def test_injected_note_preamble_does_not_claim_a_single_shape():
    preamble = _preamble()
    assert "the round(s) below ran per logs/driver.log but have no" \
        not in preamble, (
            "the pre-round-373 preamble asserted shape 1 unconditionally; a "
            "dirty-path or escalation finding was announced as a missing "
            "research-state.md entry")
    assert "READ WHAT IT ACTUALLY SAYS" in preamble
    assert "NOT a gap" in preamble, (
        "the preamble must say an acknowledged escalation is informational, "
        "or the fifth shape reintroduces the noise it removes")


def test_injected_note_preamble_names_the_working_tree_and_escalation_shapes():
    preamble = _preamble().lower()
    assert "working tree" in preamble
    assert "escalat" in preamble


def _git(ws, *args):
    subprocess.run(["git", "-C", ws] + list(args), check=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_acknowledged_escalation_logs_one_line_and_injects_no_note(tmp_path):
    """Round 373's fifth gap shape, end to end through the real driver.

    Two things are being pinned at once, and the second is a defect this
    change introduced and had to fix. (a) An acknowledged escalation must
    NOT make the check non-zero and must NOT put a NOTE in the round's
    prompt — that is the whole point: 13 of rounds 349-373 injected a note
    whose only content was an item decided in round 349. (b) The PASS
    branch's driver.log entry must stay ONE line. It always had been,
    because a zero-exit run printed exactly one sentence; the escalation
    section broke that assumption, and driver.log is parsed line-by-line by
    check_round_recorded.py itself.
    """
    ws = str(tmp_path)
    os.makedirs(os.path.join(ws, "state"), exist_ok=True)
    os.makedirs(os.path.join(ws, "logs"), exist_ok=True)
    _install_real_check_script(ws)

    # A real git checkout whose ONLY visible dirty path is the escalated
    # file: `/*` + a negation keeps the driver's own scratch files (round
    # counter, logs, the copied script, the stub bin/) out of git status.
    _git(ws, "init", "-q")
    _git(ws, "config", "user.email", "t@t.com")
    _git(ws, "config", "user.name", "t")
    with open(os.path.join(ws, ".gitignore"), "w") as f:
        f.write("/*\n!/escalated.md\n")
    esc_path = os.path.join(ws, "escalated.md")
    with open(esc_path, "w") as f:
        f.write("original\n")
    _git(ws, "add", "-f", "escalated.md")
    _git(ws, "commit", "-q", "-m", "base")
    with open(esc_path, "w") as f:
        f.write("rewritten by a separate system\n")

    import sys as _sys
    _sys.path.insert(0, os.path.dirname(REAL_CHECK_SCRIPT))
    import check_round_recorded as crr
    import json as _json
    with open(os.path.join(ws, "state", "known-escalated-diffs.json"), "w") as f:
        _json.dump({"escalations": {"escalated.md": {
            "reason": "adjudicated and escalated to the operator. Details.",
            "escalated_round": 349,
            "worktree_blob": crr.worktree_blob_hash("escalated.md", ws),
            "head_blob": crr.head_blob_hash("escalated.md", ws),
        }}}, f)

    log_text, args_text = _run_driver(tmp_path)

    pass_lines = [l for l in log_text.splitlines()
                   if "round 1: record-check PASS" in l]
    assert len(pass_lines) == 1, log_text
    line = pass_lines[0]
    assert "known-escalated tracked-file diff(s)" in line, line
    assert "escalated.md" in line, line
    assert "0 gaps" in line, line
    # Every driver.log entry starts with its own timestamp — a multi-line
    # `log` call would leave continuation lines that match nothing.
    for l in log_text.splitlines():
        if l.strip():
            assert l.startswith("["), "unstamped continuation line: %r" % l

    assert "round 1: record-check FOUND" not in log_text, log_text
    prompt = _first_call_prompt(args_text)
    assert "record-gap check" not in prompt, prompt

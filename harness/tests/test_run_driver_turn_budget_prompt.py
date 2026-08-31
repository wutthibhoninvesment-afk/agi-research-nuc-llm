"""End-to-end test for run_driver.sh's round-391 turn-budget prompt line.

`--max-turns` is the driver's PRIMARY graceful stopgap (round 205), and 32
sessions in `logs/` have died on it, each discarding a whole round's
uncommitted diff. Round 391 found what the CLI actually counts: ONE turn
per assistant MESSAGE, so N independent tool calls batched into a single
message cost one turn rather than N. Batching is free work against the
only budget that has ever killed a round on this box, and 81 of 233
substantial rounds never used it once.

The round session cannot discover any of that for itself — it has no
access to `--max-turns`' value and no way to see the 238-log history — so
the fact goes in the prompt the driver builds. This test proves, with a
real `bash run_driver.sh` subprocess and a fake `claude` on PATH (the same
discipline as `test_run_driver_maxturns_safety_valve.py`), that the line
reaches the round and that `$MAX_TURNS` really interpolates rather than
shipping the literal variable name.

Bash escaping is the specific hazard being pinned: the line contains
backticks inside a double-quoted heredoc-free assignment, where an
unescaped pair would be a command substitution executed at prompt-build
time. `bash -n` does not catch that — only rendering the string does.
"""

import os
import re
import shutil
import stat
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")

# Captures the FIRST prompt it is handed and then fails every round, so
# the 3-consecutive-failures valve stops the driver quickly. First only,
# because after the valve stops the loop the driver makes one more
# `claude` call for `state/FINAL-REPORT.md` — a different prompt entirely,
# which a plain `>` capture would overwrite (it did, on the first run of
# this test).
CLAUDE_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
WS="$DRIVER_TEST_WS"
PROMPT=""
while [ $# -gt 0 ]; do
  if [ "$1" = "-p" ]; then PROMPT="$2"; shift 2; continue; fi
  shift
done
if [ ! -f "$WS/state/captured_prompt.txt" ]; then
  printf '%s' "$PROMPT" > "$WS/state/captured_prompt.txt"
fi
echo '{"type":"result","is_error":true,"subtype":"error_other","num_turns":1,"result":"stop","api_error_status":null,"total_cost_usd":0.01}'
"""


def _run_driver_once(tmp_path, env_extra=None):
    ws = str(tmp_path)
    os.makedirs(os.path.join(ws, "state"), exist_ok=True)
    os.makedirs(os.path.join(ws, "logs"), exist_ok=True)
    driver_copy = os.path.join(ws, "run_driver.sh")
    shutil.copyfile(DRIVER_SRC, driver_copy)
    os.chmod(driver_copy, 0o755)

    bin_dir = os.path.join(ws, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    stub_path = os.path.join(bin_dir, "claude")
    with open(stub_path, "w") as f:
        f.write(CLAUDE_STUB)
    st = os.stat(stub_path)
    os.chmod(stub_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    env = dict(os.environ)
    env["PATH"] = bin_dir + os.pathsep + env["PATH"]
    env["DRIVER_WS"] = ws
    env["DRIVER_TEST_WS"] = ws
    env["DRIVER_LOOP_SLEEP_S"] = "0"
    env["DRIVER_CLAUDE_CMD"] = "claude"
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    env.update(env_extra or {})

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

    captured = os.path.join(ws, "state", "captured_prompt.txt")
    assert os.path.exists(captured), "stub never received a -p prompt"
    with open(captured) as f:
        return f.read()


def test_prompt_carries_the_turn_budget_line_with_max_turns_interpolated(tmp_path):
    prompt = _run_driver_once(tmp_path)
    assert "TURN BUDGET" in prompt, prompt
    # The value, not the variable name — the whole point of putting it here
    # is that the round cannot read `--max-turns` any other way.
    assert "--max-turns 135" in prompt, prompt
    assert "$MAX_TURNS" not in prompt, prompt
    # The mechanism, stated so it is checkable rather than exhortative.
    assert "ONE turn per assistant MESSAGE" in prompt, prompt
    assert "cost one turn, not N" in prompt, prompt


def test_turn_budget_line_tracks_the_max_turns_override(tmp_path):
    """`DRIVER_MAX_TURNS` is the documented override (round 205). If it
    ever moves again, the prompt must move with it — a hardcoded number
    here would become the next stale claim the moment the cap changes,
    which is round 321's item-14 class exactly.
    """
    prompt = _run_driver_once(tmp_path, {"DRIVER_MAX_TURNS": "200"})
    assert "--max-turns 200" in prompt, prompt
    assert "--max-turns 135" not in prompt, prompt


def test_turn_budget_backticks_are_literal_not_command_substitution(tmp_path):
    """The escaping hazard. If the backticks around `--max-turns N` were
    unescaped, bash would run `--max-turns 135` as a command at
    prompt-build time and splice its (empty) output in, silently deleting
    the number this line exists to deliver.
    """
    prompt = _run_driver_once(tmp_path)
    assert prompt.count("`") == 2, prompt
    assert re.search(r"`--max-turns \d+`", prompt), prompt


def test_turn_budget_line_precedes_the_record_gap_note(tmp_path):
    """`$ROUND_GAP_NOTE` is appended after this line and starts with its
    own newline-led NOTE header; the two must not run together into one
    unreadable paragraph.
    """
    prompt = _run_driver_once(tmp_path)
    assert prompt.index("TURN BUDGET") > prompt.index("spend the tokens"), prompt
    assert prompt.rstrip().endswith("do not depend on each other."), prompt[-200:]

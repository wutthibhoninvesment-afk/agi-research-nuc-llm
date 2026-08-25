"""BashTool timeout semantics (round 109): the whole process group dies,
partial output survives, the normal-path format is unchanged."""
import os
import time

import pytest

from agentloop.tools import BashTool


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_normal_command_format_is_unchanged(tmp_path):
    r = BashTool(str(tmp_path)).run("echo hi")
    assert r.ok and r.output == "hi\n[exit 0]"


def test_stderr_and_nonzero_exit(tmp_path):
    r = BashTool(str(tmp_path)).run("echo oops 1>&2; exit 3")
    assert not r.ok
    assert "[stderr]\noops" in r.output and r.output.endswith("[exit 3]")


def test_timeout_kills_the_grandchild_and_keeps_partial_output(tmp_path):
    # The shell exits at once; the backgrounded sleep inherits stdout and
    # would outlive the cap. Old behaviour (git HEAD, measured round 109):
    # returns at the cap, grandchild ALIVE, "started" lost.
    tool = BashTool(str(tmp_path), timeout_s=0.5)
    t0 = time.monotonic()
    r = tool.run("sleep 5 & echo $! > pid; echo started; sleep 5")
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0, elapsed
    assert not r.ok
    assert "timed out after 0s (process group killed" in r.output
    assert "[partial stdout]\nstarted" in r.output
    pid = int((tmp_path / "pid").read_text())
    deadline = time.monotonic() + 2.0
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(pid), "grandchild survived the process-group kill"


def test_timeout_with_no_output_reports_plainly(tmp_path):
    r = BashTool(str(tmp_path), timeout_s=0.3).run("sleep 3")
    assert not r.ok
    assert "[partial" not in r.output and r.output.startswith("command timed out after 0s")


@pytest.mark.parametrize("cmd", ["exit 0", "true"])
def test_silent_success(tmp_path, cmd):
    r = BashTool(str(tmp_path)).run(cmd)
    assert r.ok and r.output == "[exit 0]"

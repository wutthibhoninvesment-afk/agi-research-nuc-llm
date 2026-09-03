"""Round 475 (harness A). The driver installs the escalated-diff guard.

Why this exists
---------------
`state/known-escalated-diffs.json` pins tracked-file diffs a round already
adjudicated as MUST NOT LAND. `check_round_recorded.py`'s fifth gap shape
reads that pin before every round and has now reported the same violation
twice, 81 rounds apart -- round 393's `git add -A` and round 474's, both
landing `languages/whence/SECURITY.md`, neither mentioning it in the commit
message. The detector saw both and prevented neither: a check that runs
BEFORE a round says nothing about what that round commits.

`harness/escalationguard.py check` is the missing commit-time consumer, but
`.git/hooks/` is untracked, so it cannot be shipped in a commit. The driver
has to write it. These tests pin the four properties that make that safe:

  * it runs BEFORE the record-gap check, so the guard covers the round that
    is about to start rather than the one after it;
  * it never blocks -- the driver has no `set -e`, and the block must not
    introduce one, so a missing script or a failed install logs and
    continues;
  * it is guarded on the script's existence, the same convention as the
    checks around it, so a tmp_path workspace with no `harness/` tree
    no-ops instead of erroring;
  * executed for real against a throwaway repo, it actually produces an
    executable `pre-commit` hook.

The functional test EXTRACTS the block from the shipped `run_driver.sh`
rather than restating it, so a future edit to the driver is what the test
runs.
"""

import os
import re
import shutil
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")
GUARD_SRC = os.path.join(REPO_ROOT, "harness", "escalationguard.py")


@pytest.fixture(scope="module")
def driver_text():
    with open(DRIVER_SRC) as fh:
        return fh.read()


def extract_block(text):
    """The shipped `if [ -f "$ESCALATION_GUARD" ]; then ... fi` block,
    together with the assignment above it."""
    m = re.search(
        r'^  ESCALATION_GUARD=.*?\n(  if \[ -f "\$ESCALATION_GUARD" \].*?\n  fi)\n',
        text, re.S | re.M)
    assert m, "the escalation-guard block is not in run_driver.sh"
    return text[m.start():m.end()]


def test_the_guard_block_exists_and_calls_install_hook(driver_text):
    block = extract_block(driver_text)
    assert "escalationguard.py" in block
    assert "install-hook" in block
    assert '--repo "$WS"' in block


def test_the_guard_runs_before_the_record_gap_check(driver_text):
    """Order is the point. Installed after the checker, the hook would only
    ever protect the NEXT round."""
    guard_at = driver_text.index('ESCALATION_GUARD="$WS/harness')
    check_at = driver_text.index(
        'RECORD_CHECK_SCRIPT="$WS/skills/session-inheritance-audit')
    assert guard_at < check_at


def test_the_guard_block_is_guarded_on_the_script_existing(driver_text):
    block = extract_block(driver_text)
    assert block.strip().startswith('ESCALATION_GUARD=')
    assert 'if [ -f "$ESCALATION_GUARD" ]; then' in block


def test_the_driver_has_no_set_e_that_a_failed_install_could_trip(driver_text):
    """The block ends in `GUARD_RC=$?` and logs it. Under `set -e` a
    non-zero install would kill the driver instead."""
    assert re.search(r"^set -uo pipefail$", driver_text, re.M)
    assert not re.search(r"^set -e", driver_text, re.M)


def test_the_extracted_block_really_installs_a_hook(tmp_path, driver_text):
    """Functional, against the SHIPPED text and a real throwaway repo."""
    ws = tmp_path / "ws"
    (ws / "harness").mkdir(parents=True)
    shutil.copy(GUARD_SRC, str(ws / "harness" / "escalationguard.py"))
    subprocess.run(["git", "-C", str(ws), "init", "-q"], check=True)

    script = ("set -uo pipefail\nWS=%s\nROUND=999\nlog(){ echo \"$@\"; }\n%s\n"
              % (str(ws), extract_block(driver_text)))
    out = subprocess.run(["bash", "-c", script], capture_output=True,
                         text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "escalation-guard" in out.stdout
    hook = ws / ".git" / "hooks" / "pre-commit"
    assert hook.exists(), out.stdout + out.stderr
    assert os.access(str(hook), os.X_OK)
    assert "escalationguard.py" in hook.read_text()


def test_the_block_no_ops_when_the_script_is_absent(tmp_path, driver_text):
    ws = tmp_path / "bare"
    ws.mkdir()
    script = ("set -uo pipefail\nWS=%s\nROUND=999\nlog(){ echo \"$@\"; }\n%s\n"
              % (str(ws), extract_block(driver_text)))
    out = subprocess.run(["bash", "-c", script], capture_output=True,
                         text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "escalation-guard" not in out.stdout

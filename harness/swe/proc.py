"""Run a command with a wall-clock cap that kills the WHOLE process group.

`subprocess.run(cmd, capture_output=True, timeout=t)` kills only the direct
child on timeout. On POSIX (CPython >= 3.7) it then `wait()`s for that child
and returns at the cap — but a grandchild (a `run.py` the test suite spawned
for an example program, say) that inherited stdout is left ALIVE, looping at
100 % CPU with the pipe, and the output collected before the cap is lost:
rounds 29/31 found orphaned mutant `run.py` processes long after their
campaign "timed out", and round 109 re-measured the old tool (returns at the
cap, grandchild alive, partial stdout dropped). Round 101's 22,071-s
"timeouts" were NOT this — they were clamshell sleep measured on the wall
clock (round 107); the pipe-hold story that first explained them was
falsified there. (On Windows `run()` does call `communicate()` again after
the kill, and the grandchild-held pipe blocks it — same fix applies.)

`run_capped` starts the child in its own session (so the child and every
descendant that does not `setsid` itself share one process group), and on
timeout SIGKILLs the whole group, closes our end of the pipe (so nothing that
escaped the group can hold us) and reaps the child. Output collected before
the timeout is returned; the caller decides what a timeout means.

`seconds` is measured on the MONOTONIC clock, like the timeout itself: on a
laptop that sleeps mid-campaign, `time.time()` deltas include the sleep
(round 101 logged 240-s timeouts as 1030–22,071 s after a night in clamshell
sleep) while the cap, which does not advance during sleep, fired after 240
awake seconds. Duration and cap must read the same clock or neither is
interpretable.
"""
import os
import signal
import subprocess
import time

# The real, never-copied repo root (this file lives at harness/swe/proc.py,
# 3 levels down) — every mutation/repair test run happens in a TEMPDIR copy
# of just `languages/whence`, where `bench/ref_diff.py`'s own __file__-based
# path math points at the tempdir instead of the real checkout (round 149:
# found via 7/78 round-137 "kills" that were actually
# `git -C <tempdir> show HEAD:...` / `import swe` failures inside
# test_v10.py's ref_diff tests, misclassified as genuine mutant kills).
# Exported so any subprocess spawned here can recover the real root.
AGI_RESEARCH_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Capped(object):
    __slots__ = ("returncode", "output", "timed_out", "seconds")

    def __init__(self, returncode, output, timed_out, seconds):
        self.returncode = returncode
        self.output = output
        self.timed_out = timed_out
        self.seconds = seconds


def _kill_group(p):
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            p.kill()
        except OSError:
            pass


def run_capped(cmd, cwd, timeout_s, env=None):
    """Run `cmd` (stdout+stderr merged) and return a `Capped`.
    `timed_out` is True when the group had to be killed; `output` then holds
    whatever the child wrote before the cap (may be empty). Always injects
    `AGI_RESEARCH_ROOT` (see module docstring) on top of the caller's env (or
    the inherited one) so a test suite running from a tempdir copy of the
    project under test can still find the real repo."""
    full_env = dict(os.environ if env is None else env)
    full_env["AGI_RESEARCH_ROOT"] = AGI_RESEARCH_ROOT
    t0 = time.monotonic()
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, text=True, start_new_session=True, env=full_env)
    try:
        out, _ = p.communicate(timeout=timeout_s)
        return Capped(p.returncode, out or "", False, time.monotonic() - t0)
    except subprocess.TimeoutExpired as e:
        _kill_group(p)
        partial = e.output if isinstance(e.output, str) else (e.output or b"").decode("utf-8", "replace")
        # Our read end goes first: a survivor outside the group can keep the
        # write end open, and `communicate()` would wait for it.
        try:
            p.stdout.close()
        except OSError:
            pass
        p.wait()
        return Capped(p.returncode, partial, True, time.monotonic() - t0)

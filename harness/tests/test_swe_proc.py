"""swe.proc.run_capped: output, exit codes, and group kill on timeout."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.proc import run_capped


def test_normal_run_returns_output_and_code(tmp_path):
    r = run_capped([sys.executable, "-c", "import sys; print('hi'); sys.stderr.write('err\\n'); sys.exit(3)"],
                   str(tmp_path), 10)
    assert r.returncode == 3 and not r.timed_out
    assert "hi" in r.output and "err" in r.output      # stderr merged
    assert 0 <= r.seconds < 10


def test_timeout_keeps_partial_output_and_kills_group(tmp_path):
    pidfile = tmp_path / "gc.pid"
    prog = ("import os, subprocess, sys, time\n"
            "print('before', flush=True)\n"
            "subprocess.Popen([sys.executable, '-c', "
            "\"import os,time; open(%r,'w').write(str(os.getpid())); time.sleep(60)\"])\n"
            "time.sleep(60)\n") % str(pidfile)
    t0 = time.time()
    r = run_capped([sys.executable, "-c", prog], str(tmp_path), 1.5)
    assert r.timed_out and time.time() - t0 < 10
    assert "before" in r.output
    for _ in range(50):
        if pidfile.exists():
            break
        time.sleep(0.05)
    pid = int(pidfile.read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            return
    raise AssertionError("grandchild survived")


def test_stdin_is_devnull(tmp_path):
    r = run_capped([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"], str(tmp_path), 10)
    assert r.output.strip() == "''" and r.returncode == 0

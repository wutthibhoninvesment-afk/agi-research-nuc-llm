"""swe.proc.run_capped: output, exit codes, and group kill on timeout."""
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.proc import run_capped, AGI_RESEARCH_ROOT

WHENCE_ROOT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "languages", "whence"))


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


def test_env_injects_agi_research_root_pointing_at_the_real_harness(tmp_path):
    r = run_capped([sys.executable, "-c",
                    "import os; print(os.environ['AGI_RESEARCH_ROOT'])"], str(tmp_path), 10)
    assert r.returncode == 0
    root = r.output.strip()
    assert root == AGI_RESEARCH_ROOT
    assert os.path.isfile(os.path.join(root, "harness", "swe", "proc.py"))


def test_env_override_is_preserved_alongside_the_injected_var(tmp_path):
    r = run_capped([sys.executable, "-c",
                    "import os; print(os.environ.get('MY_VAR'), os.environ.get('AGI_RESEARCH_ROOT') is not None)"],
                   str(tmp_path), 10, env={"MY_VAR": "hello", "PATH": os.environ.get("PATH", "")})
    assert r.output.strip() == "hello True"


def _copy_whence(dst):
    shutil.copytree(WHENCE_ROOT, dst, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"))


def test_ref_diff_test_survives_running_from_a_tempdir_copy(tmp_path):
    """Round 149: `bench/ref_diff.py`'s own REPO/HARNESS path math (derived
    from `__file__`) is only correct in the real checkout. Every mutation
    and repair run in `swe.campaign`/`swe.repair` copies just
    `languages/whence` into a tempdir and runs `pytest tests` there —
    `REPO` then pointed at the tempdir's parent, so `os.path.join(REPO,
    "harness")` named a nonexistent directory and
    `test_v10.py::test_ref_diff_fuzz_mode_same_on_copy_and_diff_on_sabotage`
    (the only test that actually imports `swe.fuzz.ProgramGen` through
    `bench/ref_diff.py`'s `fuzz_sources`) failed on EVERY such run
    regardless of what mutation was injected (2 sibling tests exercising
    the same `--fuzz` code path failed the same way). Found via round 137's
    campaign: the live repair benchmark could never score `green` for a
    real, `exact`-diff fix for this reason
    (state/swe/round-137/repair.json — every one of 6 repairs was
    `localized`, none `green`, all four failures unrelated to the injected
    mutant).

    First falsified against the pre-fix code (`env={}` below strips the
    injected var exactly like the old `run_capped`, which never set it),
    THEN checked that the real `run_capped` (which always injects it) makes
    the identical run pass."""
    dst = tmp_path / "proj"
    _copy_whence(str(dst))
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
           "tests/test_v10.py::test_ref_diff_fuzz_mode_same_on_copy_and_diff_on_sabotage"]

    stripped_env = dict(os.environ)
    stripped_env.pop("AGI_RESEARCH_ROOT", None)
    # plain subprocess.run, bypassing run_capped's injection entirely --
    # this is exactly what every pre-round-149 call site did
    import subprocess
    broken = subprocess.run(cmd, cwd=str(dst), env=stripped_env,
                            capture_output=True, text=True, timeout=120)
    assert broken.returncode != 0, broken.stdout[-2000:] + broken.stderr[-2000:]
    assert "ModuleNotFoundError" in broken.stdout or "no module named 'swe'" in broken.stdout.lower() or \
        "ModuleNotFoundError" in broken.stderr or "no module named 'swe'" in broken.stderr.lower()

    fixed = run_capped(cmd, str(dst), 120, env=stripped_env)   # run_capped injects it regardless
    assert fixed.returncode == 0, fixed.output[-2000:]

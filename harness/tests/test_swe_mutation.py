"""swe.mutation on a tiny fixture project (fast, no Whence involved)."""
import os
import subprocess
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.mutation import generate, mutation_test, run_mutant, DEFAULT_TEST_CMD

MOD = textwrap.dedent('''
    """docstring must not be mutated"""
    def clamp(x, lo, hi):
        if x < lo:
            return lo
        if x > hi:
            return hi
        return x

    def is_even(n):
        return n % 2 == 0 and not n < 0
''')

TESTS = textwrap.dedent('''
    from mod import clamp, is_even
    def test_clamp():
        assert clamp(5, 0, 3) == 3
        assert clamp(-1, 0, 3) == 0
        assert clamp(2, 0, 3) == 2
    def test_even():
        assert is_even(4) and not is_even(3)
''')


def make_project(tmp_path):
    (tmp_path / "mod.py").write_text(MOD)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_mod.py").write_text(TESTS)
    (tmp_path / "tests" / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n")
    return str(tmp_path)


def test_generate_enumerates_operators_and_skips_docstrings():
    ms = generate(MOD, "mod.py")
    ops = {m.op for m in ms}
    assert {"cmp", "ifneg", "const", "arith", "bool", "not"} <= ops
    assert all("docstring must not be mutated" in m.source for m in ms)
    assert all(m.source != MOD for m in ms)
    assert len({m.id for m in ms}) == len(ms)          # ids unique
    for m in ms:
        compile(m.source, m.id, "exec")                # every mutant is valid Python


def test_not_operator_drops_the_not():
    m = next(m for m in generate(MOD, "mod.py") if m.op == "not")
    assert "not not n < 0" in m.source          # `not not x` == truthiness of x


def test_run_mutant_never_touches_original(tmp_path):
    root = make_project(tmp_path)
    m = generate(MOD, "mod.py")[0]
    run_mutant(m, root, DEFAULT_TEST_CMD)
    assert (tmp_path / "mod.py").read_text() == MOD
    assert m.status in ("killed", "survived")


def test_mutation_test_scores_and_finds_survivors(tmp_path):
    root = make_project(tmp_path)
    rep = mutation_test(root, ["mod.py"], DEFAULT_TEST_CMD, workers=4)
    assert rep.mutants and all(m.status for m in rep.mutants)
    assert 0 < rep.score < 1                       # some killed, some survive
    # `n < 0` guard in is_even is never exercised: its mutants must survive
    survivors = {m.description for m in rep.survived}
    assert any("Lt -> LtE" in d for d in survivors)
    text = rep.summary()
    assert "SURVIVED" in text and "score" in text
    d = rep.as_dict()
    assert d["total"] == len(rep.mutants) and d["killed"] + d["survived"] == d["total"]


def test_timeout_counts_as_killed(tmp_path):
    root = make_project(tmp_path)
    m = generate(MOD, "mod.py")[0]
    m.source = "import time\ntime.sleep(5)\n" + m.source
    run_mutant(m, root, DEFAULT_TEST_CMD, timeout_s=0.5)
    assert m.status == "timeout"


def test_timeout_kills_grandchild_holding_stdout(tmp_path):
    """Round 101: a test spawned a `run.py` grandchild that inherited stdout
    and looped forever; `subprocess.run(timeout=)` killed pytest, then blocked
    in `communicate()` for 22,071 s because the pipe never closed. The runner
    must return within the cap and the grandchild must be dead."""
    import time
    root = make_project(tmp_path)
    pidfile = tmp_path / "grandchild.pid"
    m = generate(MOD, "mod.py")[0]
    m.source = textwrap.dedent('''
        import os, subprocess, sys, time
        # grandchild inherits our stdout (the pipe) and outlives the cap
        subprocess.Popen([sys.executable, "-c",
            "import os,time; open(%r,'w').write(str(os.getpid())); time.sleep(60)"])
        time.sleep(0.5)
        while not os.path.exists(%r):
            time.sleep(0.05)
        time.sleep(60)
    ''' % (str(pidfile), str(pidfile))) + m.source
    t0 = time.time()
    run_mutant(m, root, DEFAULT_TEST_CMD, timeout_s=2.0)
    wall = time.time() - t0
    assert m.status == "timeout" and "group" in m.detail
    assert wall < 15, "runner blocked on the grandchild's pipe for %.1fs" % wall
    pid = int(pidfile.read_text())
    dead = False
    for _ in range(50):
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            dead = True
            break
    assert dead, "grandchild %d survived the cap" % pid

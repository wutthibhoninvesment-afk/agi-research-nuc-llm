"""End-to-end: run every example through run.py as a subprocess."""

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = os.path.join(ROOT, "run.py")


def run_example(name, *extra):
    path = os.path.join(ROOT, "examples", name) if name else None
    cmd = [sys.executable, RUN] + ([path] if path else []) + list(extra)
    return subprocess.run(cmd, capture_output=True, text=True)


def test_hello():
    r = run_example("hello.lang")
    assert r.returncode == 0
    assert "sum of squares: 55" in r.stdout
    assert "2 passed, 0 failed" in r.stdout


def test_provenance():
    r = run_example("provenance.lang")
    assert r.returncode == 0
    assert "let rate" in r.stdout
    assert "3 passed, 0 failed" in r.stdout


def test_blame():
    r = run_example("blame.lang")
    assert r.returncode == 0
    assert 'miss: num: cannot parse "3O"' in r.stdout
    assert "parsed beta" in r.stdout      # blame trail names the bad row
    assert "4 passed, 0 failed" in r.stdout


def test_checks_demo():
    r = run_example("checks_demo.lang")
    assert r.returncode == 0
    assert "8 passed, 0 failed" in r.stdout


def test_sales():
    r = run_example("sales.lang")
    assert r.returncode == 0
    assert "5 passed, 0 failed" in r.stdout


def test_failing_check_exits_1_and_explains():
    r = run_example("failing_check.lang")
    assert r.returncode == 1
    assert "✗ tax is 8 percent" in r.stdout
    assert "let tax_rate" in r.stdout     # the why-tree points at the bug
    assert "0 passed, 2 failed" in r.stdout


def test_parse_error_exits_2(tmp_path):
    bad = tmp_path / "bad.lang"
    bad.write_text("let = 5\n")
    r = subprocess.run([sys.executable, RUN, str(bad)],
                       capture_output=True, text=True)
    assert r.returncode == 2
    assert "error:" in r.stderr


def test_usage_exits_2():
    r = run_example(None)
    assert r.returncode == 2
    assert "usage" in r.stderr


def test_deep():
    r = run_example("deep.lang")
    assert r.returncode == 0
    assert "count(15000) = 15000" in r.stdout
    assert "recursion too deep in loop (depth 20000)" in r.stdout
    assert "6 passed, 0 failed" in r.stdout


def test_history():
    r = run_example("history.lang")
    assert r.returncode == 0
    assert 'op: "num"' in r.stdout           # blame record printed as data
    assert "14 passed, 0 failed" in r.stdout


def test_meta_self_hosting_subset():
    r = run_example("meta.lang")
    assert r.returncode == 0
    assert "=>  20" in r.stdout
    assert "25 passed, 0 failed" in r.stdout


def test_self_hosting_real_syntax():
    r = run_example("self_host.lang")
    assert r.returncode == 0, r.stdout
    assert "60 passed, 0 failed" in r.stdout
    assert "guest lexer+parser for real Whence syntax" in r.stdout


def test_max_depth_flag():
    r2 = subprocess.run([sys.executable, RUN, "--max-depth", "100",
                         os.path.join(ROOT, "examples", "deep.lang")],
                        capture_output=True, text=True)
    assert r2.returncode == 1                # count(15000) now misses
    assert "depth 100" in r2.stdout
    bad = subprocess.run([sys.executable, RUN, "--max-depth", "x", "y.lang"],
                         capture_output=True, text=True)
    assert bad.returncode == 2 and "usage" in bad.stderr


def test_tco():
    r = run_example("tco.lang")
    assert r.returncode == 0, r.stdout
    assert "if took else-branch ×5" in r.stdout
    assert "10 passed, 0 failed" in r.stdout
    assert "frames merged: 100001" in r.stdout
    assert "call go ×6" in r.stdout


def test_diverge():
    r = run_example("diverge.lang")
    assert r.returncode == 0
    assert 'first divergence: "30" (line 16) became "3O" (line 21)' in r.stdout
    assert "origin 1 of 1 (value):" in r.stdout      # contrast rendering
    assert "checks: 16 passed, 0 failed" in r.stdout


def test_shapes():
    r = run_example("shapes.lang")
    assert r.returncode == 0, r.stdout
    assert "parameter 'r' of validate expected Request, got record" in r.stdout
    assert "recovered total (bad request contributes 0): 3" in r.stdout
    assert "12 passed, 0 failed" in r.stdout


def test_max_iter_flag(tmp_path):
    prog = tmp_path / "spin.lang"
    prog.write_text("fn spin(n) { spin(n + 1) }\nlet r = spin(0)\nprint(r)\n"
                    "check \"bounded\": contains(str(r), \"1000 iterations\")\n")
    r = subprocess.run([sys.executable, RUN, "--max-iter", "1000", str(prog)],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "tail loop too long in spin" in r.stdout
    # both flags compose, in either order
    r2 = subprocess.run([sys.executable, RUN, "--max-iter", "5", "--max-depth",
                         "50", str(prog)], capture_output=True, text=True)
    assert r2.returncode == 1 and "5 iterations" in r2.stdout

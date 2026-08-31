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


def test_dropped_reports_the_one_miss_it_drops_on_purpose():
    """v0.32: the report is unconditional, the exit code is not."""
    r = run_example("dropped.lang")
    assert r.returncode == 0
    assert "6 passed, 0 failed" in r.stdout
    assert "dropped: 1 miss value computed and discarded" in r.stdout
    assert 'num: cannot parse "7O"' in r.stdout
    strict = run_example("dropped.lang", "--strict-miss")
    assert strict.returncode == 1
    assert strict.stdout == r.stdout


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


def test_lex_error_exits_2(tmp_path):
    # v0.21 (round 350). `run.py` caught `ParseError` and not `LexError`,
    # so EVERY lex error left the CLI as a raw Python traceback with exit
    # 1 -- the "some check failed" code, indistinguishable from a program
    # whose checks failed -- while SPEC's `## Running` has always promised
    # `2 (lex/parse error)` and `test_parse_error_exits_2` above already
    # held. Three shapes, one per `raise LexError` site in the lexer.
    for src, msg in [("let x = $\n", "unexpected character"),
                     ('let s = "abc\n', "unterminated string"),
                     ('let s = "a\\qb"\n', "bad escape")]:
        bad = tmp_path / "bad.lang"
        bad.write_text(src)
        r = subprocess.run([sys.executable, RUN, str(bad)],
                           capture_output=True, text=True)
        assert r.returncode == 2, (src, r.returncode, r.stderr)
        assert r.stderr.startswith("error: "), r.stderr
        assert msg in r.stderr
        assert "Traceback" not in r.stderr


def test_usage_exits_2():
    r = run_example(None)
    assert r.returncode == 2
    assert "usage" in r.stderr


@pytest.mark.whence_slow
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


@pytest.mark.whence_slow
def test_meta_self_hosting_subset():
    r = run_example("meta.lang")
    assert r.returncode == 0
    assert "=>  20" in r.stdout
    assert "25 passed, 0 failed" in r.stdout


def test_self_hosting_real_syntax():
    r = run_example("self_host.lang")
    assert r.returncode == 0, r.stdout
    # round 350 (v0.21): 102 -> 109, seven checkpoint checks for the four
    # places the guest lexer disagreed with whence/lexer.py (a `\r` is
    # whitespace, twice; the `\r` escape decodes; a raw newline ends a
    # string literal unterminated; a lex error carries the host's bare
    # message; an overflowing literal is `inf`, with and without an
    # exponent). See `tests/test_lexer_guest_parity.py`. Round 356 (v0.23):
    # 109 -> 112, the statement-separator rule — one check that used to
    # assert `"1 2"` PARSES became four (it is refused; the same two
    # statements parse on two lines; the miss names the line; and a token
    # that starts no statement still gets its own error, not this one).
    # Round 360 (v0.24): 112 -> 133, decision 34 -- eight column checks
    # (every token carries one; the first is 1; EOF is one past the end; a
    # comment does not stop it advancing; the next line restarts at 1; a
    # bad escape reports at the backslash; an unterminated string at the
    # opening quote), two that a parse error says WHERE, eight for the
    # trailing comma the guest used to permit in six constructs (plus the
    # two that a comma still separates and an empty one is still empty),
    # two for the `check` label a miss in a record field used to swallow,
    # and two that a lex error is reported as itself. Round 398 (v0.36):
    # 133 -> 140, decision 45 -- five for the GOT half of `expected X,
    # got Y` (end of input rather than the EOF token's empty `v`; an
    # unquoted number; a quoted name; an escaped newline; and a string
    # containing a single quote, which Python `repr` renders in DOUBLE
    # quotes) and two for the six host `what=` spellings `expect_name`
    # used to answer with `expected a name`.
    assert "145 passed, 0 failed" in r.stdout
    assert "guest lexer+parser for real Whence syntax" in r.stdout


@pytest.mark.whence_slow
def test_max_depth_flag():
    r2 = subprocess.run([sys.executable, RUN, "--max-depth", "100",
                         os.path.join(ROOT, "examples", "deep.lang")],
                        capture_output=True, text=True)
    assert r2.returncode == 1                # count(15000) now misses
    assert "depth 100" in r2.stdout
    bad = subprocess.run([sys.executable, RUN, "--max-depth", "x", "y.lang"],
                         capture_output=True, text=True)
    assert bad.returncode == 2 and "usage" in bad.stderr


@pytest.mark.whence_slow
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


@pytest.mark.whence_slow
def test_shapes():
    r = run_example("shapes.lang")
    assert r.returncode == 0, r.stdout
    # v0.20 (round 348): the field clause is part of the message now, from
    # BOTH ends of the contract — a parameter's and a return's. Pinned in
    # full rather than by prefix, because the prefix is exactly what
    # survived unchanged when the interesting half was added.
    assert ("parameter 'r' of validate expected Request, got record "
            "(field 'retries' expected num, got str)") in r.stdout
    assert "recovered total (bad request contributes 0): 3" in r.stdout
    assert ("return value of broken_midpoint expected Point, got record "
            "(no field 'y')") in r.stdout
    assert "18 passed, 0 failed" in r.stdout


def test_effects():
    r = run_example("effects.lang")
    assert r.returncode == 0, r.stdout
    assert "total: 60" in r.stdout
    assert "auditing 3 prices" in r.stdout
    assert "(debug) 10" in r.stdout
    assert "logged total: 60" in r.stdout
    assert "logged total (via factory): 60" in r.stdout
    assert "logged total (via record field): 60" in r.stdout
    assert "logged total (via argument): 60" in r.stdout
    assert "logged total (via anon-fn argument): 60" in r.stdout
    assert "logged total (via renamed argument): 60" in r.stdout
    assert "logged total (via return-boundary argument): 60" in r.stdout
    assert "16 passed, 0 failed" in r.stdout


def test_effects_violation_exits_2(tmp_path):
    bad = tmp_path / "bad_effects.lang"
    bad.write_text('fn f() effects [] { print(1) }\n1\n')
    r = subprocess.run([sys.executable, RUN, str(bad)],
                       capture_output=True, text=True)
    assert r.returncode == 2
    assert "'print' requires effect 'io'" in r.stderr


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

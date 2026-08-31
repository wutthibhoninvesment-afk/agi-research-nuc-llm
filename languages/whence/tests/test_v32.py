"""Whence v0.32 (round 384, language C) — decision 40: an unobserved miss.

Whence's decision 2 says a failure is a value that "can tell you *why*".
v0.32 is about the one position in the language where nothing was ever going
to ask: a statement whose value is discarded. `print(x)` is x, a `let` binds,
a `check` reads, an operand consumes — but an expression statement's value
has no name, no consumer, and when the run ends there is nobody left to ask
it anything.

The corpus that found it is not synthetic. Fourteen machine-written Whence
programs sit untracked in `examples/` (another system's output; see
`state/known-standing-dirty-paths.json`). Ten do not parse. Of the four that
run, THREE print nothing or print labels with empty values and exit 0 — and
two of them were carrying, inside the value they threw away, the exact
sentence v0.22 wrote thirty rounds ago to name their bug
(`arguments fit fold(fn, acc, xs)`).

The tests below pin four things:
  1. what counts as a drop (and that `print` is observation, not a drop —
     the rule's FIRST run over the tracked corpus reported four drops and
     all four were `print(<a miss>)` in an example whose subject is that
     miss);
  2. that all three engines agree about drops;
  3. the `_FOREIGN_NAMES` entry rule, against a FROZEN census of the field
     corpus rather than against the live untracked files;
  4. that recording is passive — same values, same reasons, same exit codes.
"""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whence.interp import (Interpreter, Env, _FOREIGN_NAMES,  # noqa: E402
                           _name_hint)
from whence.values import Miss                                # noqa: E402
from whence.parser import parse                               # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = os.path.join(ROOT, "run.py")
CENSUS = os.path.join(os.path.dirname(ROOT), "..", "state", "whence",
                      "round-384", "field-names.json")


def run(src, **kw):
    kw.setdefault("out", lambda s: None)
    i = Interpreter(**kw)
    i.run(src)
    return i


def drops(src, **kw):
    return ["; ".join(e["reasons"]) for e in run(src, **kw).dropped]


# --------------------------------------------------------------------------
# 1. what is a drop
# --------------------------------------------------------------------------

def test_a_top_level_expression_statement_that_misses_is_a_drop():
    i = run("nosuch(1)\n")
    assert i.dropped_total == 1
    e = i.dropped[0]
    assert e["reasons"] == ("unbound name 'nosuch' (line 1)",)
    assert e["at"] == 1 and e["count"] == 1


def test_the_last_top_level_expression_is_a_drop_too():
    """`run` returns the Env, not a value, so a program ending in a bare
    expression has nowhere to put it either. This is the shape of
    `examples/expense_tracker.lang`, which printed NOTHING and exited 0."""
    i = run('let total = fold([1.0], 0.0, fn(a, x) { a + x })\ntotal\n')
    assert i.dropped_total == 1
    e = i.dropped[0]
    assert e["at"] == 2 and e["line"] == 1       # died at 2, born at 1
    assert e["label"] == "let total"
    assert "arguments fit fold(fn, acc, xs)" in e["reasons"][0]


def test_a_let_and_a_check_are_not_drops():
    """A bound name can be asked; a check has already read the value."""
    assert drops("let x = nosuch(1)\n") == []
    assert drops('check "c": nosuch(1) == 1\n') == []


def test_a_non_tail_statement_inside_a_block_is_a_drop():
    src = 'fn f(n) { nosuch(n)\n n }\nlet r = f(1)\n'
    assert drops(src) == ["unbound name 'nosuch' (line 1)"]


def test_a_block_tail_is_not_a_drop():
    src = 'fn f(n) { nosuch(n) }\nlet r = f(1)\n'
    assert drops(src) == []


def test_a_one_statement_block_has_no_drop_site():
    """The compiled fast path returns a single-statement block's closure
    directly, skipping the loop that records drops. That shortcut is only
    safe because a one-statement block's only statement IS its tail."""
    i = run('fn f(n) { nosuch(n) }\nlet r = f(1)\n')
    assert i.dropped == [] and i.dropped_total == 0


def test_repeated_drops_of_one_site_are_one_entry_with_a_count():
    src = ('fn f(n) { if n == 0 { 0 } else { nosuch(n)\n f(n - 1) } }\n'
           'let r = f(20)\n')
    i = run(src)
    assert len(i.dropped) == 1
    assert i.dropped[0]["count"] == 20 and i.dropped_total == 20


def test_the_cap_bounds_the_record_but_not_the_count():
    src = "".join("nosuch%d(1)\n" % k for k in range(Interpreter.DROP_CAP + 7))
    i = run(src)
    assert len(i.dropped) == Interpreter.DROP_CAP
    assert i.dropped_total == Interpreter.DROP_CAP + 7


# --------------------------------------------------------------------------
# 2. print is observation
# --------------------------------------------------------------------------

def test_print_of_a_miss_is_not_a_drop():
    """`print(x) is x`, so before this rule every `print(<a miss>)` in the
    corpus looked like an unobserved miss. Four tracked examples do exactly
    that on purpose (blame/deep/history/meta.lang)."""
    out = []
    i = run('print(nosuch(1))\n', out=out.append)
    assert i.dropped == [] and i.dropped_total == 0
    assert out and "unbound name 'nosuch'" in out[0]


def test_print_observes_it_inside_a_block_too():
    src = 'fn f(n) { print(nosuch(n))\n n }\nlet r = f(1)\n'
    assert drops(src) == []


def test_an_expression_around_a_print_is_still_a_drop():
    """`print(y)` showed y; the SUM was never shown, and the report says so
    rather than crediting the print with observing a value it never saw."""
    assert drops('1 + print(nosuch(1))\n') != []


def test_print_of_a_non_miss_records_nothing_at_all():
    i = run('print(1)\nprint("x")\n')
    assert i._observed == {}


# --------------------------------------------------------------------------
# 3. the three engines agree
# --------------------------------------------------------------------------

ENGINES = ({"direct": True, "fast": True},
           {"direct": False, "fast": True},
           {"direct": False, "fast": False})

DROP_CASES = [
    "nosuch(1)\n",
    'fn f(n) { nosuch(n)\n n }\nlet r = f(1)\n',
    'let t = fold([1.0], 0.0, fn(a, x) { a + x })\nt\n',
    'print(nosuch(1))\n',
    'fn f(n) { if n == 0 { 0 } else { nosuch(n)\n f(n - 1) } }\nlet r = f(5)\n',
]


@pytest.mark.parametrize("src", DROP_CASES)
def test_the_three_engines_agree_on_what_was_dropped(src):
    seen = [(run(src, **e).dropped_total, tuple(drops(src, **e)))
            for e in ENGINES]
    assert len(set(seen)) == 1, seen


# --------------------------------------------------------------------------
# 4. the cure clause and its entry rule
# --------------------------------------------------------------------------

def test_the_unbound_name_miss_names_the_cure_for_a_foreign_name():
    r = run("println(1)\n").dropped[0]["reasons"][0]
    assert "unbound name 'println'" in r
    assert "`print` already ends the line" in r


def test_a_name_that_is_not_foreign_gets_no_clause():
    assert drops("nosuch(1)\n") == ["unbound name 'nosuch' (line 1)"]
    assert _name_hint("nope") == "" and _name_hint("printf") == ""


def test_every_foreign_name_is_attested_or_rejected_by_a_decision():
    """The entry rule, executable. A key qualifies only if the FROZEN field
    census saw it, or it is the keyword of a construct SPEC decision 2 ("No
    exceptions, no null") or 3 ("All iteration is recursion / map / filter /
    fold") names as deliberately absent."""
    census = json.load(open(CENSUS, encoding="utf-8"))
    attested = set(census["unbound_identifier_counts"])
    by_decision = {"while", "try", "throw", "raise", "null", "nil", "None"}
    for name in _FOREIGN_NAMES:
        assert name in attested or name in by_decision, name
    # and the rule bites: these are names other languages use that are
    # neither attested nor rejected, and they are NOT in the table
    for name in ("printf", "def", "lambda", "elif", "size", "length"):
        assert name not in _FOREIGN_NAMES, name


def test_every_foreign_sentence_names_a_whence_spelling():
    for name, sentence in _FOREIGN_NAMES.items():
        assert "`" in sentence, name
        assert sentence[0].islower() or sentence.startswith("Whence"), name


def test_the_frozen_census_says_what_it_censused():
    census = json.load(open(CENSUS, encoding="utf-8"))
    assert census["round"] == 384 and census["n_files"] == 14
    assert len(census["file_md5"]) == 14
    counts = census["unbound_identifier_counts"]
    # the number that decided the table's first entry
    assert counts["println"] == 34
    assert len(census["unbound_identifier_files"]["println"]) == 9
    # a CONSTANT-derived claim, so it is allowed to be exact (round 383):
    # the census recorded the builtin set it was taken against
    live = sorted(Interpreter(out=lambda s: None).globals.vars)
    assert census["builtins_at_capture"] == live


def test_the_unbound_name_miss_has_one_constructor():
    """Three copies of the literal became `_unbound` so the clause could not
    be added to two of the three. `tests/test_v31.py`'s census pins the
    count; this pins the reachability of both live paths (compiled `f_name`
    and `eval_NameRef`)."""
    fast = run("println(1)\n", fast=True).dropped[0]["reasons"][0]
    slow = run("println(1)\n", fast=False, direct=False).dropped[0]["reasons"][0]
    assert fast == slow


# --------------------------------------------------------------------------
# 5. recording is passive
# --------------------------------------------------------------------------

def test_the_repl_path_records_nothing():
    """`repl()` prints every expression statement's value, so nothing there
    is unobserved. It calls `exec_stmt`, and the recorder lives in `run`."""
    i = Interpreter(out=lambda s: None)
    env = Env(i.globals)
    for stmt in parse("nosuch(1)\n").stmts:
        v = i.exec_stmt(stmt, env)
    assert isinstance(v.value, Miss)
    assert i.dropped == [] and i.dropped_total == 0


def test_a_drop_does_not_change_the_value_or_the_run():
    i = run('let a = nosuch(1)\nnosuch(1)\nlet b = 1 + 1\n')
    assert i.dropped_total == 1
    # the run completed and later statements still evaluated
    i2 = Interpreter(out=lambda s: None)
    env = i2.run('nosuch(1)\nlet b = 2 + 3\n')
    assert env.get("b").value == 5


def test_the_report_names_both_lines_and_the_count():
    import run as runpy
    src = ('fn f(n) { if n == 0 { 0 } else { nosuch(n)\n f(n - 1) } }\n'
           'let r = f(3)\n')
    i = run(src)
    lines = []
    n = runpy.report_drops(i, out=lines.append)
    assert n == 1
    assert lines[0].startswith("dropped: 3 miss values")
    assert "×3" in lines[1]


def test_strict_miss_moves_the_exit_code_and_nothing_else():
    """0/1/2 is a pinned contract, so a dropped miss does NOT fail a run by
    default; `--strict-miss` is the opt-in."""
    prog = os.path.join(ROOT, "examples", "hello.lang")
    ok = subprocess.run([sys.executable, RUN, prog], capture_output=True,
                        text=True)
    assert ok.returncode == 0
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".lang", delete=False) as f:
        f.write("nosuch(1)\n")
        path = f.name
    try:
        loose = subprocess.run([sys.executable, RUN, path],
                               capture_output=True, text=True)
        strict = subprocess.run([sys.executable, RUN, "--strict-miss", path],
                                capture_output=True, text=True)
    finally:
        os.unlink(path)
    assert loose.returncode == 0 and strict.returncode == 1
    assert loose.stdout == strict.stdout
    assert "dropped: 1 miss value" in loose.stdout
    # and --strict-miss on a clean program is still 0
    strict_ok = subprocess.run([sys.executable, RUN, "--strict-miss", prog],
                               capture_output=True, text=True)
    assert strict_ok.returncode == 0


def test_usage_mentions_the_flag():
    r = subprocess.run([sys.executable, RUN, "--help"], capture_output=True,
                       text=True)
    assert "--strict-miss" in r.stdout


# --------------------------------------------------------------------------
# 6. the corpus (slow: runs every tracked example in-process)
# --------------------------------------------------------------------------

# `examples/dropped.lang` is the ONE example that drops on purpose: a
# language feature with no runnable example is a feature nobody runs. Named
# here with its exact count, so "the corpus is silent" stays a measurement
# rather than a habit of ignoring the line.
DROPS_ON_PURPOSE = {"examples/dropped.lang": 1}


@pytest.mark.whence_slow
def test_no_tracked_example_drops_a_miss():
    """The property that makes the report readable: a green corpus is a
    silent one. If a future example needs to drop a miss, it belongs in
    DROPS_ON_PURPOSE with a reason, not in the noise."""
    out = subprocess.run(["git", "ls-files", "examples"], capture_output=True,
                         text=True, cwd=ROOT).stdout.split()
    assert len(out) >= 18, out
    assert set(DROPS_ON_PURPOSE) <= set(out), sorted(DROPS_ON_PURPOSE)
    sys.setrecursionlimit(6000)
    for rel in out:
        i = Interpreter(out=lambda s: None, gc_relief=True)
        i.run(open(os.path.join(ROOT, rel), encoding="utf-8").read())
        assert i.dropped_total == DROPS_ON_PURPOSE.get(rel, 0), \
            (rel, i.dropped)


@pytest.mark.whence_slow
def test_host_and_guest_word_the_foreign_clause_identically():
    """`examples/self_eval.lang` re-implements name lookup, so it has to
    carry the same table. Round 380's divergence class, not repeated."""
    sys.setrecursionlimit(6000)
    lib = open(os.path.join(ROOT, "examples", "self_eval.lang"),
               encoding="utf-8").read()
    out = []
    i = Interpreter(out=out.append, gc_relief=True)
    i.run(lib + '\nprint(str(gv("println(1)")))\nprint(str(gv("return(1)")))\n')
    guest = [l for l in out if l.startswith("miss:")]
    assert len(guest) == 2, out[-3:]
    assert "`print` already ends the line" in guest[0]
    assert "a block's value is its last expression" in guest[1]
    # the only difference from the host is the line number, which is the
    # language's oldest documented host/guest divergence
    host = run("println(1)\n").dropped[0]["reasons"][0]
    assert host.split(" (line")[0] == guest[0][len("miss: "):].split(" (line")[0]

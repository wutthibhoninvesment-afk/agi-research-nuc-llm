"""v0.42 (round 446, language C) — the miss inside a value nothing kept.

v0.32 built the drop report on one sentence: *a miss that is the value of a
statement nothing keeps cannot be asked anything by anybody*. It implemented
that sentence as `isinstance(v.payload, Miss)` — a test on the OUTERMOST node
— and so for ten versions the report was silent about every miss riding
inside a discarded list or record:

    nosuch(1)                            -> 1 drop
    fold(fn(a, x) { nosuch(x) }, 0, xs)  -> 1 drop   (fold returns the miss)
    [nosuch(1)]                          -> 0 drops  <- and exit 0
    map(fn(x) { nosuch(x) }, xs)         -> 0 drops  <- and exit 0
    @{a: nosuch(1)}                      -> 0 drops  <- and exit 0

The `map` line is the one that matters. It is the shape of every
machine-written program in the field corpus that processes rows, and `map`'s
result is the value an agent most often forgets to bind. Measured on the live
corpus the widening found one new real drop in a program eleven rounds have
read: `examples/mini_agi_guardian.lang:48`'s bare `r1` discards a record
holding `unbound name 'return' (Whence has no `return`; a block's value is
its last expression)`, made at line 27 and invisible until v0.42.

The widening also produced a FALSE positive on its first run, on a TRACKED
example, and the tests below pin the fix for it rather than the fix alone:
`examples/history.lang:43` is `print(culprits)`, a list of blame records the
next five lines interrogate. v0.32 had a rule for exactly that — *printing a
miss IS observing it* — that had only ever been applied to a miss printed
BARE. v0.42 extends observation to printed containers, in a second bounded
set, so that widening the report could not break the case v0.32 got right.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import curecheck as C                                           # noqa: E402
from whence.interp import Interpreter                           # noqa: E402
from whence.values import Miss                                  # noqa: E402
import run as RUNPY                                             # noqa: E402

RUN = os.path.join(ROOT, "run.py")


def run(src, out=None, **kw):
    i = Interpreter(out=out if out is not None else (lambda s: None), **kw)
    i.run(src)
    return i


def reasons(i):
    return ["; ".join(e["reasons"]) for e in i.dropped]


# --------------------------------------------------------------------------
# 1. the widening: an aggregate nobody kept
# --------------------------------------------------------------------------

def test_a_miss_inside_a_discarded_list_is_a_drop():
    i = run("[nosuch(1)]\n")
    assert i.dropped_total == 1
    e = i.dropped[0]
    assert e["reasons"] == ("unbound name 'nosuch' (line 1)",)
    assert e["at"] == 1
    assert e["within"] == "list 1 items"


def test_a_miss_inside_a_discarded_map_result_is_a_drop():
    """The shape this version exists for. Three elements, three misses, one
    entry with a count of three — the dedup key is unchanged."""
    i = run("let xs = [1, 2, 3]\nmap(fn(x) { nosuch(x) }, xs)\n")
    assert i.dropped_total == 3
    assert len(i.dropped) == 1
    assert i.dropped[0]["count"] == 3
    assert i.dropped[0]["within"] == "map"


def test_a_miss_inside_a_discarded_record_is_a_drop():
    i = run("@{a: nosuch(1)}\n")
    assert i.dropped_total == 1
    assert i.dropped[0]["within"] == "record"


def test_the_walk_is_recursive_through_nested_aggregates():
    assert run("[[nosuch(1)]]\n").dropped_total == 1
    assert run("@{a: [@{b: nosuch(1)}]}\n").dropped_total == 1
    assert run("[@{a: nosuch(1)}, @{a: nosuch(2)}]\n").dropped_total == 2


def test_a_bound_aggregate_discarded_by_a_later_statement_is_a_drop():
    """Same rule v0.32 already applied to a bare miss: `run` returns the Env,
    so a program ending in a bare name has nowhere to put the value either.
    `test_v32.py::test_the_last_top_level_expression_is_a_drop_too` is this
    test's scalar twin, and the two must not disagree."""
    i = run("let xs = [nosuch(1)]\nxs\n")
    assert i.dropped_total == 1
    assert i.dropped[0]["at"] == 2 and i.dropped[0]["within"] == "let xs"


def test_a_clean_aggregate_is_not_a_drop():
    assert run("[1, 2, 3]\n").dropped_total == 0
    assert run("@{a: 1, b: \"x\"}\n").dropped_total == 0
    assert run("map(fn(x) { x + 1 }, [1, 2])\n").dropped_total == 0


def test_a_block_tail_aggregate_is_still_not_a_drop():
    """v0.32's boundary, unmoved: a block's tail IS its value, so the caller
    has it. Widening what a drop can contain must not widen WHERE one is."""
    assert run("fn f(n) { [nosuch(n)] }\nlet r = f(1)\n").dropped_total == 0
    assert run("let r = [nosuch(1)]\n").dropped_total == 0
    assert run('check "c": len([nosuch(1)]) == 1\n').dropped_total == 0


def test_the_within_label_reaches_the_printed_report():
    """The label is not bookkeeping: without it the report says `line 2 —
    unbound name 'nosuch'` and the reader goes looking for a binding that
    was never made."""
    i = run("let xs = [1, 2]\nmap(fn(x) { nosuch(x) }, xs)\n")
    out = []
    RUNPY.report_drops(i, out.append)
    assert out[0].startswith("dropped: 2 miss values")
    assert " in map" in out[1] and "×2" in out[1]


# --------------------------------------------------------------------------
# 2. observation: the false positive the widening created, and its fix
# --------------------------------------------------------------------------

def test_printing_a_container_observes_what_is_inside_it():
    assert run("print([nosuch(1)])\n").dropped_total == 0
    assert run("print(@{a: nosuch(1)})\n").dropped_total == 0
    assert run("print(map(fn(x) { nosuch(x) }, [1, 2]))\n").dropped_total == 0


def test_an_observed_element_inside_an_unobserved_container_is_skipped():
    """`print` marks the ELEMENT; the list around it was never shown."""
    i = run("[print(nosuch(1)), 1]\n")
    assert i.dropped_total == 0


def test_an_expression_around_a_printed_container_was_a_drop_until_v043():
    """CHANGED BY v0.43 (round 450), and re-pinned to the new answer with the
    argument rather than flipped quietly.

    v0.42 read this program as v0.32's `1 + print(y)` rule in the aggregate
    register: `concat` built a NEW list that nothing showed, so report it.
    But the drop report reports MISS NODES, not containers, and `+` on lists
    reuses the element nodes — so v0.42 printed the miss's reason and then
    reported the same node as *"nothing can ask it why"* three lines later.

    Worse, it disagreed with its own sibling. These two programs put exactly
    the same information in front of the reader:

        [print(nosuch(1)), 1]      -> 0 drops   (v0.42 and v0.43)
        print([nosuch(1)]) + [2]   -> 1 drop    (v0.42) / 0 drops (v0.43)

    and v0.42 answered them differently for no reason except whether
    `print`'s argument was the miss or the container around it. v0.43 marks
    the miss NODES the rendering named, so both are 0.

    `test_a_new_miss_built_around_a_printed_one_is_still_a_drop` in
    `test_v43.py` holds v0.32's actual rule: `print(nosuch(1)) + 1` builds a
    NEW miss node and is still a drop."""
    i = run("print([nosuch(1)]) + [2]\n")
    assert i.dropped_total == 0
    assert run("[print(nosuch(1)), 1]\n").dropped_total == 0
    assert run("print(nosuch(1)) + 1\n").dropped_total == 1


@pytest.mark.whence_slow
def test_history_lang_is_the_case_that_forced_the_observation_rule():
    """Falsified, not asserted. `examples/history.lang` prints a list of
    blame records whose `.value` is a miss and then asks four `check`s about
    it — the correct use of the feature. Under the PRE-v0.42 observation gate
    (printed bare misses only) the widened report fires on it; under the
    v0.42 gate it does not. Both halves are run here, so deleting
    `_observed_aggr` cannot pass this file."""
    sys.setrecursionlimit(6000)
    src = open(os.path.join(ROOT, "examples", "history.lang"),
               encoding="utf-8").read()

    class PreV42(Interpreter):
        def _seen_by_print(self, v):
            return id(v) in self._observed

    good = Interpreter(out=lambda s: None, gc_relief=True)
    good.run(src)
    assert good.dropped_total == 0, good.dropped

    bad = PreV42(out=lambda s: None, gc_relief=True)
    bad.run(src)
    assert bad.dropped_total == 1, "the falsification stopped falsifying"
    assert bad.dropped[0]["within"] == "let culprits"
    assert 'num: cannot parse "5,25"' in bad.dropped[0]["reasons"][0]


def test_the_two_observation_sets_are_bounded_separately():
    """Why `_observed_aggr` is a second dict and not more entries in the
    first. Merged, a program that prints DROP_CAP harmless lists exhausts the
    cap and the NEXT printed miss is reported as a drop — v0.42 breaking
    v0.32. Printed lists here: DROP_CAP + 5."""
    n = Interpreter.DROP_CAP + 5
    src = "".join("print([%d])\n" % k for k in range(n))
    src += "print(nosuch(1))\n"
    i = run(src)
    assert i.dropped_total == 0, i.dropped
    assert len(i._observed) == 1
    assert len(i._observed_aggr) < Interpreter.DROP_CAP

    # v0.43 (round 450): the INVARIANT is unchanged and still the reason the
    # second dict exists; the numbers moved, in the direction that makes the
    # case safer rather than the one that makes it moot. v0.42 spent one slot
    # per printed CONTAINER, so this program filled `_observed_aggr` to its
    # cap and the separation is what kept the final `print(nosuch(1))`
    # observable. v0.43 marks the miss NODES the rendering NAMED, and a
    # harmless list names none, so the cap is not touched at all. The
    # assertion is `< DROP_CAP` rather than `== 0` on purpose: what must hold
    # here is that harmless printing cannot crowd out a real one, and pinning
    # the exact spend would make this a second copy of
    # `test_v43.py::test_printing_a_harmless_container_marks_nothing`.


def test_past_its_cap_the_observation_record_errs_toward_reporting():
    """The behaviour `_observed`'s comment has documented since v0.32 —
    "past the cap the recorder errs toward REPORTING (a false drop is
    visible and arguable; a silent one is what this feature exists to end)"
    — and which nothing tested until round 446. A FALSE drop, pinned on
    purpose: it is the deliberate direction of the error."""
    n = Interpreter.DROP_CAP
    src = "".join("print(nosuch%d(1))\n" % k for k in range(n))
    src += "print(nosuchlast(1))\n"
    i = run(src)
    assert len(i._observed) == n
    assert i.dropped_total == 1
    assert "nosuchlast" in i.dropped[0]["reasons"][0]


# --------------------------------------------------------------------------
# 3. the scan bound says so rather than going quiet
# --------------------------------------------------------------------------

def test_a_scan_that_stops_early_is_reported_even_with_no_drops():
    """The bug this test was written from: the first draft of
    `run.py:report_drops` returned early on `not interp.dropped`, so the
    "I stopped reading" sentence could only ever print when something HAD
    been found — never in the one case it exists for."""
    i = Interpreter(out=lambda s: None)
    i.DROP_SCAN_NODES = 4
    i.run("[1, 2, 3, 4, 5, 6, 7, 8]\n")
    assert i.dropped_total == 0
    assert i.dropped_scan_truncated == 1
    out = []
    assert RUNPY.report_drops(i, out.append) == 0
    assert len(out) == 1 and "too large to read to the end" in out[0]
    assert "4 nodes" in out[0]


def test_the_scan_bound_does_not_move_the_exit_code():
    """"I did not finish looking" is not "I found something", so
    `--strict-miss` must not fail on truncation alone. `report_drops`
    returns the SITE count, which is what `run.py:main` reads."""
    i = Interpreter(out=lambda s: None)
    i.DROP_SCAN_NODES = 2
    i.run("[1, 2, 3, 4]\n")
    assert i.dropped_scan_truncated == 1
    assert RUNPY.report_drops(i, lambda s: None) == 0


def test_the_default_bound_does_not_fire_on_ordinary_code():
    """Why the bound is 100000 and not the 5000 the first draft used: the
    walk is proportional to a value the program already paid to build, so a
    bound that fires on `map(f, range(20000))` prints a warning about a
    program with no defect."""
    i = run("map(fn(x) { x + 1 }, range(20000))\n")
    assert i.dropped_scan_truncated == 0
    assert Interpreter.DROP_SCAN_NODES == 100000


# --------------------------------------------------------------------------
# 4. all three engines agree about the new cases
# --------------------------------------------------------------------------

ENGINES = ({"direct": True, "fast": True},
           {"direct": False, "fast": True},
           {"direct": False, "fast": False})

AGGREGATE_CASES = [
    "[nosuch(1)]\n",
    "@{a: nosuch(1)}\n",
    "let xs = [1, 2, 3]\nmap(fn(x) { nosuch(x) }, xs)\n",
    "print([nosuch(1)])\n",
    "let xs = [nosuch(1)]\nxs\n",
    "fn f(n) { [nosuch(n)]\n n }\nlet r = f(1)\n",
]


@pytest.mark.parametrize("src", AGGREGATE_CASES)
def test_the_three_engines_agree_on_the_aggregate_cases(src):
    seen = [(run(src, **e).dropped_total, tuple(reasons(run(src, **e))))
            for e in ENGINES]
    assert len(set(seen)) == 1, seen


# --------------------------------------------------------------------------
# 5. the exit contract, end to end
# --------------------------------------------------------------------------

def _cli(src, tmp_path, *extra):
    p = tmp_path / "p.lang"
    p.write_text(src, encoding="utf-8")
    return subprocess.run([sys.executable, RUN] + list(extra) + [str(p)],
                          capture_output=True, text=True)


def test_the_cli_reports_an_aggregate_drop_and_strict_miss_still_gates_it(
        tmp_path):
    src = "let xs = [1, 2]\nmap(fn(x) { nosuch(x) }, xs)\n"
    loose = _cli(src, tmp_path)
    strict = _cli(src, tmp_path, "--strict-miss")
    assert loose.returncode == 0 and strict.returncode == 1
    assert loose.stdout == strict.stdout
    assert "dropped: 2 miss values" in loose.stdout
    assert " in map ×2 —" in loose.stdout


# --------------------------------------------------------------------------
# 6. the corpus readers now ask the strict question
# --------------------------------------------------------------------------

def test_dropped_count_distinguishes_zero_from_no_measurement():
    """`0` is a clean run and `None` is no run. A column that printed 0 for
    both would report ten parse failures as ten clean programs."""
    assert C.dropped_count(None) is None
    assert C.dropped_count("checks: 1 passed, 0 failed\n") == 0
    assert C.dropped_count(
        "dropped: 6 miss values computed and discarded — x\n  line 1 — y\n") == 6
    assert C.dropped_count("dropped: 1 miss value computed and discarded\n") == 1
    assert C.dropped_count("dropped: lots of them\n") is None


def test_the_report_line_has_exactly_one_spelling_in_curecheck():
    """Round 445's lesson in this file's key: `survey` and `replay` are two
    readers over one corpus, and the anchor they share is a literal from
    another module's output. One definition, or the next fix lands in one of
    two copies."""
    src = open(os.path.join(ROOT, "curecheck.py"), encoding="utf-8").read()
    code = [l for l in src.splitlines()
            if not l.lstrip().startswith("#")]
    hits = [l for l in code if '"dropped: "' in l or "'dropped: '" in l]
    assert len(hits) == 1, hits
    assert hits[0].startswith("DROP_LINE_PREFIX")


def test_run_py_writes_the_prefix_curecheck_reads():
    """The one place the two modules are coupled, asserted rather than
    hoped: `curecheck.DROP_LINE_PREFIX` is not imported from `run.py` (a
    format string is not a constant there), so this is the anti-rot pin."""
    i = run("nosuch(1)\n")
    out = []
    RUNPY.report_drops(i, out.append)
    assert out[0].startswith(C.DROP_LINE_PREFIX)
    assert C.dropped_count("\n".join(out)) == 1


def test_fmt_survey_publishes_the_strict_verdict():
    """The sentence, not the column. `_fmt_survey`'s headline was
    "N reach a value (rc=0)" — which SPEC.md's own v0.33 section contradicts
    under the heading "Reaching a value is not working"."""
    rows = [
        {"file": "clean.lang", "outcome": "parses-unedited", "steps": [],
         "applied": 0, "rc": 0, "strict_rc": 0, "dropped": 0},
        {"file": "dirty.lang", "outcome": "parses-unedited", "steps": [],
         "applied": 0, "rc": 0, "strict_rc": 1, "dropped": 4},
        {"file": "stalled.lang", "outcome": "stalled", "steps": [],
         "applied": 0, "strict_rc": None, "dropped": None},
    ]
    text = C._fmt_survey(rows)
    assert ("3 file(s): 2 parse, 2 reach a value (rc=0), 1 of those clean "
            "under --strict-miss (4 miss value(s) dropped)") in text
    # the stalled row prints "-" in both new columns, never 0
    line = [l for l in text.splitlines() if l.startswith("stalled.lang")][0]
    assert line.split()[3:6] == ["-", "-", "-"]


@pytest.mark.whence_slow
def test_the_field_corpus_survey_records_what_the_run_printed():
    """The number round 444's next-step 4 asked for, re-derivable rather than
    quoted. Skips or goes red per `field_corpus_skip_reason` — the field
    corpus belongs to a separate system and a corpus-derived number moving is
    new information, not a regression."""
    reason = C.field_corpus_skip_reason()
    if reason:
        pytest.skip(reason)
    rows = C.survey(C.field_programs())
    ran = [r for r in rows if r.get("rc") == 0]
    assert len(ran) == 5, [r["file"] for r in ran]
    dirty = sorted(r["file"] for r in ran if r["dropped"])
    assert dirty == ["expense_tracker.lang", "mini_agi_guardian.lang",
                     "prod_showcase_final.lang"], dirty
    assert sum(r["dropped"] for r in ran) == 12
    # rc and strict_rc are DIFFERENT facts about the same run, which is the
    # whole finding: every one of the three exits 0 and fails --strict-miss.
    for r in ran:
        assert r["strict_rc"] == (1 if r["dropped"] else 0), r

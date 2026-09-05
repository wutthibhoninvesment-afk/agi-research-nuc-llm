"""`runlive.py` — is a builtin INVOKED, not merely written?

Round 506 (language C). The third level of the liveness question: round 503
asked whether the Python def is referenced, round 504 whether the guest name
is called in source, and this asks whether the builtin runs.

What this file pins is the part that can silently answer zero:

  * the counters are non-zero against a program whose calls are counted by
    hand. Round 506 shipped, for one run, a `reset_program` that REBOUND
    `self.calls` instead of clearing it, so every wrapper wrote to a dict
    nobody read and the census reported `written_never_run` for all 37
    builtins while 23 programs ran and `_check_contract` was entered 515728
    times. Clean, plausible, entirely false, nothing raised. Same class as
    round 504's own headline bug, one file later;
  * the hook is at DISPATCH, so a builtin reached as a value is counted;
  * the process is left uninstrumented, including after a program raises --
    the `Builtin` table is a module global shared by every `Interpreter` in
    the process, so a leaked wrapper would follow this suite into whatever
    ran next;
  * and the round's finding itself: a `p: Type` annotation invokes `typed`
    ZERO times. If a future change routes contracts back through the
    builtin, that is a language change and this goes red.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import builtinlive as BL            # noqa: E402
import runlive as RL                # noqa: E402
from whence import interp as I      # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WHENCE = os.path.dirname(HERE)
EXAMPLES = os.path.join(WHENCE, "examples")


def run_one(src, **kw):
    """One program through the real hook; returns the per-program row."""
    with RL.Counter() as c:
        return RL.run_program(src, c, **kw)


def prog(where, src):
    return {"origin": "example", "where": where, "src": src}


# ---------------------------------------------------------- the counters --

def test_a_hand_counted_program_yields_exactly_that_count():
    """The falsifier for the rebind bug. Every number here is countable by
    reading the two lines above it, so a census that answers zero -- or that
    answers a plausible non-zero -- is caught by the same assertion."""
    r = run_one('let a = str(1)\nlet b = str(2)\nlet c = len([1, 2, 3])\n')
    assert r["ok"], r["error"]
    assert r["calls"] == {"str": 2, "len": 1}, r["calls"]
    assert sum(r["calls"].values()) == 3


def test_a_loop_counts_every_iteration_not_every_call_site():
    """A runtime census differs from a syntactic one exactly here: one
    written `push` under a 10-deep recursion is ten invocations."""
    src = ('fn go(n, acc) { if n == 0 { acc } else { go(n - 1, push(acc, n)) } }\n'
           'check "ten": len(go(10, [])) == 10\n')
    r = run_one(src)
    assert r["ok"], r["error"]
    assert r["calls"]["push"] == 10
    assert r["calls"]["len"] == 1
    assert r["n_checks"] == 1 and r["n_failed_checks"] == 0


def test_a_builtin_reached_as_a_VALUE_is_counted():
    """The reason the hook is at `Builtin.fn` and not at a call node.
    `map(str, xs)` invokes `str` three times through no call site that
    names it -- a syntactic census sees one `ref` use and cannot see the
    three invocations at all."""
    r = run_one('let out = map(str, [1, 2, 3])\ncheck "three": len(out) == 3\n')
    assert r["ok"], r["error"]
    assert r["calls"]["str"] == 3, r["calls"]
    assert r["calls"]["map"] == 1
    uses, _naive, _sh = BL.uses_in('let out = map(str, [1, 2, 3])\n')
    kinds = {(u.name, u.kind) for u in uses}
    assert ("str", BL.USE_REF) in kinds and ("str", BL.USE_CALL) not in kinds


def test_the_counts_reset_between_programs():
    """`reset_program` must CLEAR the dict the wrappers close over, not
    rebind the attribute. Two programs in one Counter, and the second must
    not inherit the first's numbers -- nor lose its own."""
    with RL.Counter() as c:
        first = RL.run_program('let a = str(1)\nlet b = str(2)\n', c)
        second = RL.run_program('let a = len([1])\n', c)
    assert first["calls"] == {"str": 2}
    assert second["calls"] == {"len": 1}, second["calls"]


# ----------------------------------------------------------- the contract --

def test_an_annotation_invokes_typed_zero_times():
    """ROUND 506'S FINDING, as a falsifier.

    v0.19 (round 344) moved the parameter contract off the builtin:
    `parser._param_contracts` stores it on the function node and
    `interp._check_contract` applies it in the host. So this program
    exercises the whole type contract -- match, mismatch, origin miss --
    and never invokes `typed`.

    `SPEC.md`'s v0.12 bullet still describes the old desugaring ("`fn f(a:
    num, ...)` desugars, in the parser, to one leading `let a = typed(a,
    "num", ...)`") in the present tense, which is what sent round 506 in
    with the opposite hypothesis. If a future version routes annotations
    back through the builtin, this test is where it must be argued.
    """
    src = ('fn f(a: num) -> num { a + 1 }\n'
           'check "ok": f(1) == 2\n'
           'check "bad": missed(f("x"))\n')
    r = run_one(src)
    assert r["ok"], r["error"]
    assert r["calls"].get("typed", 0) == 0, r["calls"]
    assert r["contract_checks"] >= 3, r
    assert r["contract_misses"] >= 1
    assert r["n_failed_checks"] == 0


def test_the_builtin_spelling_of_the_same_contract_IS_counted():
    """The other half, so the test above cannot pass by the hook being
    broken: written as a call, it is one invocation."""
    r = run_one('let a = typed(1, "num", "L")\ncheck "ok": a == 1\n')
    assert r["ok"], r["error"]
    assert r["calls"].get("typed") == 1, r["calls"]
    assert r["contract_checks"] == 0


def test_the_no_op_contract_entry_is_counted_separately_from_a_real_check():
    """`_check_contract` is entered for every call of every function,
    annotated or not, and returns immediately when `spec is None`. Counting
    those entries as checks would report an unannotated corpus as fully
    type-checked."""
    r = run_one('fn g(x) { x }\ncheck "n": g(1) == 1\n')
    assert r["ok"], r["error"]
    assert r["contract_calls"] >= 1
    assert r["contract_checks"] == 0, r


# -------------------------------------------------------- the instrument --

def test_the_hook_is_removed_afterwards_even_when_the_program_raises():
    """The table is a process global. A leaked wrapper would follow this
    suite into whatever ran next in the same process."""
    if I._BUILTIN_TABLE is None:
        I._BUILTIN_TABLE = I._make_builtin_table()
    before = {n: b.fn for n, b in I._BUILTIN_TABLE}
    contract_before = I._check_contract
    with RL.Counter() as c:
        r = RL.run_program('let a = nosuchname(1)\n', c)
    assert {n: b.fn for n, b in I._BUILTIN_TABLE} == before
    assert I._check_contract is contract_before
    assert r["ok"], r["error"]      # an unbound name is a MISS, not a raise


def test_the_hook_leaves_every_dispatch_class_alone():
    """`Builtin.is_gen` is computed in `__init__` from the original fn and
    decides whether the trampoline is used. Wrapping must not recompute it
    and must not change it."""
    if I._BUILTIN_TABLE is None:
        I._BUILTIN_TABLE = I._make_builtin_table()
    before = {n: b.is_gen for n, b in I._BUILTIN_TABLE}
    with RL.Counter():
        during = {n: b.is_gen for n, b in I._BUILTIN_TABLE}
    assert during == before
    assert any(before.values()), "no generator builtin — the pin is vacuous"


def test_a_generator_builtin_still_works_and_is_counted():
    """`map`/`fold` call back into Whence and are dispatched as generators.
    The wrapper returns the generator object rather than being a generator
    function, which is what the `is_gen` gate above makes correct."""
    r = run_one('let t = fold(fn(a, b) { a + b }, 0, [1, 2, 3])\n'
                'check "six": t == 6\n')
    assert r["ok"], r["error"]
    assert r["calls"]["fold"] == 1
    assert r["n_failed_checks"] == 0


def test_a_program_that_cannot_be_parsed_is_reported_never_dropped():
    """`builtinlive.py`'s rule, and it matters more here: a runtime census
    that skips what it could not run reports the absence of an invocation it
    never attempted."""
    c = RL.census(programs=[prog("broken.lang", "let a = \n"),
                            prog("fine.lang", 'let a = str(1)\n')])
    assert c["n_programs"] == 2 and c["n_ran"] == 1 and c["n_errors"] == 1
    e = c["errors"][0]
    assert e["where"] == "broken.lang" and e["error_kind"] == "parse"
    assert c["total_runtime_calls"] == 1


# ------------------------------------------------------------- the census --

def test_the_four_verdicts_are_each_reachable():
    """A verdict nothing can produce is a comment. `contains` is written and
    run; `abs` is written on a branch never taken; `str` is invoked only via
    a value, which the syntactic side records as a `ref` -- so the
    genuinely-unwritten case is built with `--dir`-free explicit programs."""
    c = RL.census(programs=[prog(
        "v.lang",
        'let a = contains("ab", "a")\n'
        'let b = if a { 1 } else { abs(-1) }\n'
        'check "one": b == 1\n')])
    rows = {r["name"]: r for r in c["rows"]}
    assert rows["contains"]["verdict"] == RL.RUN_AND_WRITTEN
    assert rows["abs"]["verdict"] == RL.WRITTEN_NEVER_RUN, rows["abs"]
    assert rows["len"]["verdict"] == RL.NEITHER
    assert set(c["counts"]) == set(RL.VERDICTS)


def test_a_written_but_unexecuted_call_site_is_the_whole_point():
    """The one thing a syntactic census structurally cannot report."""
    c = RL.census(programs=[prog(
        "b.lang", 'let x = if 1 == 1 { 1 } else { sqrt(4) }\ncheck "o": x == 1\n')])
    rows = {r["name"]: r for r in c["rows"]}
    assert rows["sqrt"]["written_total"] == 1
    assert rows["sqrt"]["run_total"] == 0
    assert rows["sqrt"]["gap"] == -1
    assert "sqrt" in c["disagree"]


def test_the_ledger_view_carries_no_wall_clock_and_round_trips():
    c = RL.census(programs=[prog("v.lang", 'let a = str(1)\n')])
    view = RL.ledger_view(c)
    flat = repr(view)
    assert "wall_seconds" not in flat and "seconds" not in flat
    assert view["runtime"]["str"] == 1
    ok, lines = RL.check(c, os.path.join(HERE, "no_such_ledger.json"))
    assert not ok and "no ledger" in lines[0]


# --------------------------------------------------- against the real tree --

def test_the_new_example_makes_typed_a_builtin_some_example_runs():
    """`examples/typed.lang`'s reason for existing, in one assertion.

    Before round 506, `typed` was the ONLY one of 37 builtins that no
    shipped example invoked: its single written site in all of `examples/`
    is `self_eval.lang`'s `if missed(value.v) or ...` propagation branch,
    which needs a guest program that hands the self-evaluator an
    already-missed argument, and none did.

    Fast-tier deliberately: one cheap example, not the whole corpus, so the
    claim this file is named for is carried by the tier every language round
    runs rather than by the slow tier round 504's next-step #2 complains
    nothing schedules.
    """
    path = os.path.join(EXAMPLES, "typed.lang")
    assert os.path.exists(path), "examples/typed.lang was deleted"
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    c = RL.census(programs=[prog("typed.lang", src)])
    assert c["n_errors"] == 0, c["errors"]
    rows = {r["name"]: r for r in c["rows"]}
    assert rows["typed"]["run_total"] > 0, "typed.lang stopped invoking typed"
    assert rows["typed"]["verdict"] == RL.RUN_AND_WRITTEN
    assert rows["matches"]["run_total"] > 0
    assert c["contract"]["checks"] > 0, (
        "the example no longer demonstrates that an ANNOTATION is the same "
        "contract without the builtin")


@pytest.mark.whence_slow
def test_every_runnable_example_runs_clean_under_the_hook():
    """The instrument must not change what a program does. Every example
    that `run.py` runs, run again under the wrapper, with its own checks as
    the oracle."""
    c = RL.census()
    assert c["n_ran"] >= 20, c["n_ran"]
    bad = [r for r in c["per_program"]
           if r["ok"] and r["n_failed_checks"] and
           r["where"] != "failing_check.lang"]
    assert not bad, [(r["where"], r["n_failed_checks"]) for r in bad]
    assert all(e["error_kind"] == "parse" for e in c["errors"]), c["errors"]


@pytest.mark.whence_slow
def test_the_two_levels_now_agree_on_every_builtin():
    """Round 504 measured that the Python-def and guest-source levels
    disagree on 37 of 37. These two disagree on ZERO, and that is the
    result: a builtin written in an example is a builtin that example runs.
    `typed` was the single exception and round 506 closed it."""
    c = RL.census()
    assert c["disagree"] == [], c["disagree"]
    assert c["counts"][RL.WRITTEN_NEVER_RUN] == 0
    assert c["counts"][RL.RUN_AND_WRITTEN] == c["n_builtins"]

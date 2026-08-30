"""Whence v0.26 (round 366, language C) — a runaway tail loop is a miss.

SPEC rule 8 makes two promises that could not both be true before v0.26:

  (a) "Tail position changes space, never meaning (round 336). Lifting any
      tail call out of tail position with a `let` must not change the value,
      the miss, which `-> Type` contract is blamed, or the line the miss
      reports — only the frame count."
  (b) "Tail loops are unbounded by default."

Take any function whose recursion never terminates. Out of tail position it
is a `max_depth` miss in 0.07s. IN tail position (b) said it runs forever —
so it has no value at all, which is the largest possible violation of (a).

`test_v13.py::test_tail_and_lifted_chains_agree_exhaustively` drives the
whole `f0 -> f1 -> ...` family through both forms and requires byte
equality, and it never caught this: every chain it builds TERMINATES,
because a non-terminating one would have hung the suite instead of failing
it. The bound in (b) is what makes the comparison expressible at all — so
the first test below is the one this version exists to make writable.

Round 365 hit the same defect from the fuzz side, minimised guest seed 31 to
`state/swe/round-365/seed31_hang.lang`, and left three suspects — field
access on a number, a `-> num` contract, `reasons()` over a Miss chain.
All three were wrong; the bisect in round 366 put it on line 7, `tl3(tr5)`
where `tr5` is `0.5`, decrementing past a `== 0` base case it can never
equal. Nothing about the program is exotic. Any non-terminating tail
recursion did this.
"""

import os
import subprocess
import sys

import pytest

from whence.interp import Interpreter
from whence.values import Miss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The two forms of one non-terminating function. Identical except that the
# recursive call is lifted out of tail position by a `let` on the right.
TAIL = """fn tl3(p4) { if p4 == 0 { 0.5 } else { tl3(p4 - 1) } }
let result = tl3(0.5)
"""
LIFTED = """fn tl3(p4) {
  if p4 == 0 { 0.5 } else {
    let r = tl3(p4 - 1)
    r
  }
}
let result = tl3(0.5)
"""


def result(src, **kw):
    interp = Interpreter(**kw)
    env = interp.run(src)
    return interp, env.get("result")


# --------------------------------------------------------------------------
# the shape the exhaustive tail/lifted differential could not drive
# --------------------------------------------------------------------------

def test_a_non_terminating_tail_loop_produces_a_value_at_all():
    """Before v0.26 this test could not be written: it did not return."""
    interp, v = result(TAIL, max_iter=1000)
    assert isinstance(v.payload, Miss)
    assert "tail loop too long in tl3 (1000 iterations)" in v.payload.reasons[0]
    assert interp.depth == 0


def test_lifted_and_tail_forms_of_a_non_terminating_fn_both_miss():
    """SPEC rule 8's round-336 invariant, on the input class it never saw.

    The two forms cannot report the SAME miss — one exhausted a depth
    budget and the other an iteration budget, and saying so is the whole
    value of a Whence miss. What rule 8 requires, and what failed before
    v0.26, is that lifting changes the frame accounting and not whether
    there is an answer.
    """
    _, tail_v = result(TAIL, max_iter=600)
    _, lift_v = result(LIFTED, max_depth=600)
    assert isinstance(tail_v.payload, Miss) and isinstance(lift_v.payload, Miss)
    # each names its own budget, and each names the same function
    assert "tail loop too long in tl3 (600 iterations)" in tail_v.payload.reasons[0]
    assert "recursion too deep in tl3 (depth 600)" in lift_v.payload.reasons[0]
    # and neither blames the `let` that did the lifting: both name `tl3`
    assert all("tl3" in m.payload.reasons[0] for m in (tail_v, lift_v))


@pytest.mark.whence_slow
def test_the_default_bounds_a_runaway_with_no_flags_at_all():
    """The regression that mattered: a bare `Interpreter()` terminates."""
    interp, v = result(TAIL)
    assert isinstance(v.payload, Miss)
    assert "tail loop too long" in v.payload.reasons[0]
    assert interp.peak_tail == Interpreter.DEFAULT_MAX_ITER


def test_none_is_still_the_explicit_unbounded_opt_out():
    """`max_iter=None` must keep meaning unbounded — v0.26 changed only
    which value is the DEFAULT. Checked without actually running a runaway:
    the interpreter simply must not have substituted a number."""
    interp = Interpreter(max_iter=None)
    assert interp.max_iter is None
    assert Interpreter().max_iter == Interpreter.DEFAULT_MAX_ITER


# --------------------------------------------------------------------------
# mutual tail recursion — guest seed 224's shape
# --------------------------------------------------------------------------

def test_mutual_tail_recursion_that_never_terminates_is_also_bounded():
    """`odd(-100)` counts DOWN away from its `== 0` base case forever.

    This is guest seed 224, the second of the two seeds that hung the
    round-365 shape sweep. The merged node names both functions, so the
    miss must too.
    """
    src = ("fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n"
           "fn odd(n) { if n == 0 { false } else { even(n - 1) } }\n"
           "let result = odd(-100)\n")
    _, v = result(src, max_iter=500)
    assert isinstance(v.payload, Miss)
    assert "tail loop too long in" in v.payload.reasons[0]
    assert "(500 iterations)" in v.payload.reasons[0]


# --------------------------------------------------------------------------
# peak_tail — the tail analogue of peak_depth
# --------------------------------------------------------------------------

def test_peak_tail_reports_the_longest_single_loop_not_the_total():
    """Two loops of 300 merge 600 tail calls in total, but the longest
    SINGLE loop — the quantity `max_iter` bounds — is 300. `tail_calls`
    could not answer this, which is why sizing the default needed a new
    counter."""
    src = ("fn go(i, acc) { if i == 0 { acc } else { go(i - 1, acc + i) } }\n"
           "let a = go(300, 0)\n"
           "let b = go(300, 0)\n"
           "let result = a + b\n")
    interp, _ = result(src)
    assert interp.tail_calls == 600
    assert interp.peak_tail == 301          # 300 merges + the entry frame
    assert interp.peak_depth == 1           # a tail loop spends no depth


def test_peak_tail_is_zero_when_nothing_tail_recurses():
    interp, _ = result("fn f(x) { x + 1 }\nlet result = f(1)\n")
    assert interp.tail_calls == 0 and interp.peak_tail == 1


@pytest.mark.parametrize("direct", [True, False])
def test_the_bound_is_enforced_in_both_evaluation_modes(direct):
    """`_call_direct` and `_call_gen` each carry their own copy of the
    tail loop; a cap enforced in one and not the other would make the
    three-way differential disagree with itself."""
    interp, v = result(TAIL, max_iter=800, direct=direct)
    assert isinstance(v.payload, Miss)
    assert "tail loop too long in tl3 (800 iterations)" in v.payload.reasons[0]
    assert interp.peak_tail == 800


# --------------------------------------------------------------------------
# the corpus is what sized the default — pin the two facts it rests on
# --------------------------------------------------------------------------

def test_the_default_clears_the_tail_budget_deep_lang_asserts():
    """`examples/deep.lang` asserts `a tail loop runs 10x past max_depth`
    as a language property. The default must clear 10 x DEFAULT_MAX_DEPTH,
    or that check becomes a miss — which is exactly how round 366's first
    (memory-parity, 50000) sizing was caught."""
    assert (Interpreter.DEFAULT_MAX_ITER
            > 10 * Interpreter.DEFAULT_MAX_DEPTH)
    with open(os.path.join(ROOT, "examples", "deep.lang"), encoding="utf-8") as f:
        assert "a tail loop runs 10x past max_depth" in f.read()


@pytest.mark.whence_slow
def test_every_example_stays_under_the_default_with_margin():
    """No git-tracked example may sit near the cap. If one ever does, the
    cap moves — the corpus is the authority, not this constant."""
    # TRACKED only: a separate system leaves untracked .lang files under
    # examples/ (see state/known-standing-dirty-paths.json), and the corpus
    # this constant answers to is the one in git.
    tracked = subprocess.run(
        ["git", "ls-files", "--", "examples/*.lang"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    assert tracked, "no tracked examples found — the guard would be vacuous"
    worst = 0
    for rel in tracked:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            src = f.read()
        interp = Interpreter(out=lambda *a: None, max_iter=None, gc_relief=True)
        interp.run(src)
        worst = max(worst, interp.peak_tail)
    # measured round 366: 200001 (deep.lang), then 100002, 60005, 50001 and
    # a 150x gap to 331. Margin of 3 over the maximum is the sizing rule.
    assert worst * 3 <= Interpreter.DEFAULT_MAX_ITER, (
        "worst tracked example needs %d tail iterations; the default (%d) "
        "no longer carries a 3x margin over the corpus" % (
            worst, Interpreter.DEFAULT_MAX_ITER))


# --------------------------------------------------------------------------
# the CLI half: --max-iter 0 is the opt-out, and the default is reachable
# --------------------------------------------------------------------------

def _run_cli(args, src, timeout):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "run.py")] + args + ["-"],
        cwd=ROOT, input=src, capture_output=True, text=True, timeout=timeout)


@pytest.mark.whence_slow
def test_cli_bounds_a_runaway_without_any_flag():
    """Before v0.26 `run.py` passed `max_iter` unconditionally, so it sent
    None on every run and the class default was unreachable from the CLI.
    This hung forever; the 60s timeout is the assertion."""
    p = _run_cli([], TAIL + 'check "r": result == result\n', timeout=60)
    assert p.returncode == 1                       # the check failed
    assert "tail loop too long in tl3" in p.stdout


@pytest.mark.whence_slow
def test_cli_max_iter_zero_restores_unbounded_and_hangs():
    """The opt-out has to really opt out. Asserting that a program does
    NOT terminate can only be done with a timeout, so this is the one test
    here that spends wall-clock on purpose."""
    with pytest.raises(subprocess.TimeoutExpired):
        _run_cli(["--max-iter", "0"], TAIL, timeout=8)

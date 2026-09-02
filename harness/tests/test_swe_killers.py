"""swe.killers: package isolation, canonical behaviour, killer search, rendering."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.fuzz import WHENCE_ROOT
from swe.killers import (load_whence, behaviour, find_killer, corpus, render_tests,
                         Killer, CANONICAL_HELPER_SRC, compare, TIMEOUT_RETRY_FACTOR)
import swe.killers as K
from swe.mutation import generate, Mutant
from tests.whence_anchor import reachable_concat_mutant


def test_load_whence_isolates_packages():
    a = load_whence(WHENCE_ROOT, "a")
    b = load_whence(WHENCE_ROOT, "b")
    assert a["Interpreter"] is not b["Interpreter"]
    assert a["Interpreter"].__module__ == "whence_a.interp"


def test_behaviour_is_plain_data_and_stable():
    pkg = load_whence(WHENCE_ROOT, "beh")
    src = 'let x = 1 + 2\ncheck "three": x == 3\nprint(x)\nlet m = 1 / 0\n'
    b = behaviour(pkg, src)
    assert b["kind"] == "ok" and b["out"] == ["3"]
    assert b["checks"] == [["three", True]]
    assert b["vals"]["x"] == "3" and b["vals"]["m"].startswith("miss:")
    assert behaviour(pkg, src) == b
    assert behaviour(pkg, "let = \n")["kind"] == "ParseError"
    assert behaviour(pkg, "let p = " + "(" * 400 + "1" + ")" * 400)["kind"] == "ParseError"
    from tests.synthetic_crash import install as install_crash, CRASH_PROGRAM
    assert behaviour(pkg, CRASH_PROGRAM)["kind"] == "ok"
    install_crash("whence_beh.interp", WHENCE_ROOT)
    assert behaviour(pkg, CRASH_PROGRAM)["kind"] == "crash"


def test_find_killer_for_a_real_semantic_mutant():
    # string concat: an arith mutant on a line that builds a "concat"
    # provenance. The arith mutant turns `+` into `-`, which crashes on
    # strings. Re-anchored in rounds 20, 109 and 437 (process rule 7); the
    # standing instruction has always been "every arith mutant on a line
    # containing `"concat"` is a legitimate anchor", so round 437 dropped the
    # extra `x + y` clause that had narrowed it to ONE line — v0.27 (round
    # 368) had deleted the inline site that clause named, and the surviving
    # concat sites spell their operands `l + r`. The fixture had been pinned
    # to a spelling, not to a behaviour.
    #
    # Round 445 moved the selection AND the iterate-until-one-kills step into
    # `tests/whence_anchor`, because round 437 fixed this copy and not
    # `test_swe_equivalence.py`'s identical one. Both details are load-bearing
    # and the second is the one the other copy lacked: a concat site can be
    # unreachable for two string literals (exactly what happened to v0.6's
    # `binop` line, and what is true of `candidates[0]` at HEAD), so "no
    # anchor at all" — not "the first one I tried" — is the failure to report.
    m, k = reachable_concat_mutant(tag="orig")
    assert k.found
    assert k.tried == 1
    # the shrinker may have minimised the literals; the sum must still differ
    assert k.expected["vals"]["a"] != k.mutant_behaviour.get("vals", {}).get("a")
    assert k.mutant_behaviour != k.expected


def test_find_killer_reports_no_killer_for_equivalent_change():
    with open(os.path.join(WHENCE_ROOT, "whence", "interp.py")) as f:
        src = f.read()
    m = generate(src, "whence/interp.py")[0]
    m.source = src + "\n_UNUSED = 1\n"          # behaviourally equivalent
    orig = load_whence(WHENCE_ROOT, "orig2")
    k = find_killer(m, ["let a = 1\n", "print(2)\n"], orig, WHENCE_ROOT)
    assert not k.found and k.tried == 2


def test_render_tests_is_valid_python_and_idempotent():
    m = generate("x = 1 < 2\n", "f.py")[0]
    k = Killer(m, "let a = 1\n", {"kind": "ok", "out": [], "checks": [], "vals": {"a": "1"}},
               {"kind": "ok", "out": [], "checks": [], "vals": {"a": "2"}}, 1, 0.1)
    text = render_tests([k])
    compile(text, "gen", "exec")
    assert CANONICAL_HELPER_SRC.strip() in text
    assert text.count("def test_kill_") == 1
    assert render_tests([k], existing=text) == text     # no duplicate on re-run


def test_corpus_includes_examples_and_fuzz():
    progs = corpus(0, 5, WHENCE_ROOT)
    assert len(progs) > 5 and any("check" in p for p in progs)


def test_generated_file_compiles_with_hostile_docstring_text():
    """Round-6 regression: a behaviour ending in a double quote fused with the
    closing triple quote and made the whole generated module a SyntaxError."""
    import ast
    from types import SimpleNamespace
    from swe.killers import render_tests as write_tests, docstring_safe, TEST_HEADER

    hostile = {"vals": {"v": 'miss: cannot order <why> and ["x…"] (line 1)"'}}
    mutant = SimpleNamespace(id="values.py:1:const#0", description='"quoted" \\ desc\nnext', lineno=1)
    killer = SimpleNamespace(found=True, mutant=mutant, mutant_behaviour=hostile,
                             program='let v = "q"\n', expected={"kind": "ok"})
    body = write_tests([killer], TEST_HEADER)
    ast.parse(body)                                   # must compile
    assert '"' not in docstring_safe('a"b\\c\nd') and docstring_safe("x" * 500) == "x" * 120


# --------------------------------------------------------------------------
# Round 437 (SWE-loop D): a timeout is a fact about the wall clock.
#
# `find_killer` skipped a program the ORIGINAL could not finish and counted a
# program the MUTANT could not finish as a behavioural difference. On a
# one-core host where the same suite measures 3x slower under contention than
# solo, and where `examples/self_host.lang` runs 0.60 s against a 2 s SIGALRM
# budget, that asymmetry manufactures a killer for an arbitrary mutant out of
# a load spike — and the kill is unreproducible by construction.
#
# These drive `compare` through a stub `behaviour`, so they are deterministic
# and cost no interpreter: what is under test is the DECISION, and the real
# thing it decides about is a race no test can schedule.

_OK = {"kind": "ok", "out": ["1"], "checks": [], "vals": {}}
_OTHER = {"kind": "ok", "out": ["2"], "checks": [], "vals": {}}
_TIMEOUT = {"kind": "timeout"}


class _StubBehaviour(object):
    """`behaviour(pkg, src, timeout_s)` from a table keyed `(pkg, budget)`."""

    def __init__(self, table):
        self.table = table
        self.calls = []

    def __call__(self, pkg, src, timeout_s=2.0, max_depth=500):
        self.calls.append((pkg, round(timeout_s, 3)))
        return dict(self.table[(pkg, round(timeout_s, 3))])


def _run_compare(monkeypatch, table, expected):
    stub = _StubBehaviour(table)
    monkeypatch.setattr(K, "behaviour", stub)
    verdict, exp, got = K.compare("orig", "mut", "let a = 1\n", expected, timeout_s=2.0)
    return verdict, exp, got, stub


def test_a_mutant_only_timeout_that_settles_at_a_longer_budget_is_not_a_kill(monkeypatch):
    """The round-433 shape. Nothing about the mutant changed between the two
    budgets; the box did."""
    long_s = round(2.0 * TIMEOUT_RETRY_FACTOR, 3)
    verdict, exp, got, stub = _run_compare(monkeypatch, {
        ("mut", 2.0): _TIMEOUT,
        ("orig", long_s): _OK,
        ("mut", long_s): _OK,
    }, _OK)
    assert verdict == "same"
    assert ("mut", long_s) in stub.calls and ("orig", long_s) in stub.calls


def test_a_mutant_that_still_diverges_at_the_longer_budget_is_a_kill(monkeypatch):
    """A mutated loop bound is a real infinite loop and must stay a kill: the
    guard re-measures, it does not forgive."""
    long_s = round(2.0 * TIMEOUT_RETRY_FACTOR, 3)
    verdict, exp, got, _ = _run_compare(monkeypatch, {
        ("mut", 2.0): _TIMEOUT,
        ("orig", long_s): _OK,
        ("mut", long_s): _TIMEOUT,
    }, _OK)
    assert verdict == "differs"
    assert got == _TIMEOUT and exp == _OK


def test_a_program_the_original_cannot_finish_at_the_longer_budget_is_undecided(monkeypatch):
    """No clean `expected` exists, so there is nothing to compare against.
    `undecided` is reported, never silently folded into `no_killer`."""
    long_s = round(2.0 * TIMEOUT_RETRY_FACTOR, 3)
    verdict, _, _, _ = _run_compare(monkeypatch, {
        ("mut", 2.0): _TIMEOUT,
        ("orig", long_s): _TIMEOUT,
        ("mut", long_s): _TIMEOUT,
    }, _OK)
    assert verdict == "undecided"


def test_a_mutant_that_settles_to_a_DIFFERENT_answer_is_still_a_kill(monkeypatch):
    """The re-measurement is not a second chance to agree: if the longer run
    produces a different answer than the original's longer run, that is a
    behavioural difference and the program is a killer."""
    long_s = round(2.0 * TIMEOUT_RETRY_FACTOR, 3)
    verdict, exp, got, _ = _run_compare(monkeypatch, {
        ("mut", 2.0): _TIMEOUT,
        ("orig", long_s): _OK,
        ("mut", long_s): _OTHER,
    }, _OK)
    assert verdict == "differs" and got == _OTHER and exp == _OK


def test_a_plain_behavioural_difference_costs_no_extra_measurement(monkeypatch):
    """The guard must be free on the path that matters. A non-timeout
    difference decides on ONE call, exactly as before round 437."""
    verdict, exp, got, stub = _run_compare(monkeypatch, {
        ("mut", 2.0): _OTHER,
    }, _OK)
    assert verdict == "differs" and got == _OTHER
    assert stub.calls == [("mut", 2.0)]


def test_agreement_costs_no_extra_measurement_either(monkeypatch):
    verdict, _, _, stub = _run_compare(monkeypatch, {("mut", 2.0): _OK}, _OK)
    assert verdict == "same" and stub.calls == [("mut", 2.0)]


def test_an_original_timeout_is_still_not_evidence(monkeypatch):
    """The one side that was already guarded stays guarded, and stays guarded
    for the same reason the other side now is."""
    verdict, _, got, stub = _run_compare(monkeypatch, {("mut", 2.0): _OK}, _TIMEOUT)
    assert verdict == "differs"          # compare() is only reached past the guard
    assert stub.calls == [("mut", 2.0)]


def test_killer_records_undecided_and_defaults_it_to_zero():
    """`tried` counts programs looked at; a `no_killer` verdict carrying
    `undecided > 0` is a weaker claim, and before round 437 both were spelled
    the same way in `killers.json`."""
    from types import SimpleNamespace
    m = SimpleNamespace(id="x.py:1:const#0")
    assert Killer(m, None, None, None, 5, 0.1).as_dict()["undecided"] == 0
    assert Killer(m, None, None, None, 5, 0.1, undecided=2).as_dict()["undecided"] == 2


# ------------------------------------- round 443: the other side of compare --

def _identity_mutant(tag="a"):
    """A mutant whose text is BYTE-IDENTICAL to the original interpreter.

    Nothing it does can be observed, so a killer for it is spurious BY
    CONSTRUCTION — no argument about which lines are reachable is needed.
    That is what makes it the right probe for a guard whose whole job is to
    not manufacture killers out of wall-clock noise.
    """
    src = open(os.path.join(WHENCE_ROOT, "whence/interp.py"), encoding="utf-8").read()
    return Mutant("interp.py:0:inert#" + tag, "whence/interp.py", 1, "inert",
                  "identity: the mutated text IS the original text", src)


class _Spike(object):
    """`behaviour` on a box under load.

    Whoever `side` names blows the SIGALRM on `src` at the BASE budget, and
    nobody blows it at a longer one. Round 437 measured the real margin
    (`self_host.lang` at 0.60 s against a 2 s budget, a 3.3x spike away) and
    the real contention on this 1-core host (3x), and concluded the race was
    "not schedulable". It is schedulable if you stop trying to race for it:
    the spike is the only thing being simulated here, and it is exact.
    Set `side = None` to end it.
    """

    def __init__(self, side, src, base_s=2.0):
        self.side, self.src, self.base_s, self.calls = side, src, base_s, []

    def __call__(self, pkg, src, timeout_s=2.0, max_depth=500):
        who = "orig" if pkg == "orig" else "mut"
        self.calls.append((who, src, round(timeout_s, 3)))
        if (who == self.side and src == self.src
                and round(timeout_s, 3) == round(self.base_s, 3)):
            return {"kind": "timeout"}
        return {"kind": "ok", "out": [src.strip()], "checks": [], "vals": {}}

    def measured(self, who, since=0):
        return sorted({s for w, s, _ in self.calls[since:] if w == who})


_PROGS = ["let a = 1\n", "let b = 2\n", "let c = 3\n"]


def test_a_load_spike_on_the_mutant_side_cannot_manufacture_a_killer(monkeypatch):
    """Round 437's fix, driven end-to-end through the real `find_killer`.

    Round 437 pinned `compare()` in isolation and recorded, honestly, that it
    could not observe the failure the fix was for. This is that observation.
    """
    stub = _Spike("mut", _PROGS[1])
    monkeypatch.setattr(K, "behaviour", stub)
    k = find_killer(_identity_mutant(), _PROGS, "orig", WHENCE_ROOT)
    assert k.found is False and k.undecided == 0 and k.unmeasured == 0
    assert ("mut", _PROGS[1], round(2.0 * TIMEOUT_RETRY_FACTOR, 3)) in stub.calls


def test_without_that_headroom_the_same_spike_kills_an_identity_mutant(monkeypatch):
    """The round-433 symptom, reproduced deterministically — a NEGATIVE control
    for the guard above. `TIMEOUT_RETRY_FACTOR = 1.0` removes exactly what
    round 437 added and nothing else, and the mutant is byte-identical to the
    original, so `found is True` here is a manufactured kill and nothing else.
    If this test ever goes green-by-passing (`found is False`) with the factor
    at 1.0, the guard above has stopped being the thing doing the work.
    """
    monkeypatch.setattr(K, "TIMEOUT_RETRY_FACTOR", 1.0)
    stub = _Spike("mut", _PROGS[1])
    monkeypatch.setattr(K, "behaviour", stub)
    k = find_killer(_identity_mutant(), _PROGS, "orig", WHENCE_ROOT)
    assert k.found is True and k.program == _PROGS[1]


def test_a_spike_on_the_ORIGINAL_side_no_longer_deletes_the_program(monkeypatch):
    """Round 443. Round 437 guarded the mutant's side of this comparison and
    left the original's single measurement in place, reasoning that an
    original-side timeout is "not evidence" — which is true, and is not the
    problem. The problem is that the verdict is CACHED."""
    stub = _Spike("orig", _PROGS[1])
    monkeypatch.setattr(K, "behaviour", stub)
    k = find_killer(_identity_mutant(), _PROGS, "orig", WHENCE_ROOT)
    assert k.found is False and k.unmeasured == 0
    assert stub.measured("mut") == sorted(_PROGS)


def test_one_original_side_spike_no_longer_poisons_later_mutants(monkeypatch):
    """`campaign.stage_corpus` builds `cache = {}` ONCE and passes it to every
    `find_killer` in the run, so this is the shape that actually bites: the
    load is long over by the time the later mutants run, and before round 443
    they still never saw the program."""
    stub = _Spike("orig", _PROGS[1])
    monkeypatch.setattr(K, "behaviour", stub)
    cache = {}
    find_killer(_identity_mutant("1"), _PROGS, "orig", WHENCE_ROOT, cache)
    stub.side = None                                   # the box goes quiet
    mark = len(stub.calls)
    k2 = find_killer(_identity_mutant("2"), _PROGS, "orig", WHENCE_ROOT, cache)
    assert cache[_PROGS[1]]["kind"] == "ok"
    assert stub.measured("mut", mark) == sorted(_PROGS)
    assert k2.found is False and k2.unmeasured == 0


def test_an_original_that_times_out_at_BOTH_budgets_is_counted_not_hidden(monkeypatch):
    """The guard re-measures, it does not forgive. A genuinely unrunnable
    program still leaves the corpus — but `tried` no longer claims it was
    compared. Before round 443 a `no_killer` over 3 programs of which 2 were
    compared was spelled exactly like one where all 3 were, which is the same
    complaint round 437 invented `undecided` to answer on the other side."""

    class _AlwaysSlow(_Spike):
        def __call__(self, pkg, src, timeout_s=2.0, max_depth=500):
            who = "orig" if pkg == "orig" else "mut"
            self.calls.append((who, src, round(timeout_s, 3)))
            if who == "orig" and src == self.src:
                return {"kind": "timeout"}
            return {"kind": "ok", "out": [src.strip()], "checks": [], "vals": {}}

    stub = _AlwaysSlow("orig", _PROGS[1])
    monkeypatch.setattr(K, "behaviour", stub)
    k = find_killer(_identity_mutant(), _PROGS, "orig", WHENCE_ROOT)
    assert k.found is False and k.tried == 3 and k.unmeasured == 1
    assert stub.measured("mut") == [_PROGS[0], _PROGS[2]]
    assert k.as_dict()["unmeasured"] == 1
    assert ("orig", _PROGS[1], round(2.0 * TIMEOUT_RETRY_FACTOR, 3)) in stub.calls


def test_the_original_side_guard_is_free_when_nothing_times_out(monkeypatch):
    """Zero extra `behaviour()` calls on the path every real corpus takes —
    the whence corpus's slowest example is 0.655 s against a 2 s budget."""
    stub = _Spike(None, _PROGS[1])
    monkeypatch.setattr(K, "behaviour", stub)
    find_killer(_identity_mutant(), _PROGS, "orig", WHENCE_ROOT)
    assert [c for c in stub.calls if c[2] != 2.0] == []
    assert len(stub.calls) == 2 * len(_PROGS)

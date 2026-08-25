"""Round 113: oracle killers (modes / frames / counters) against injected
mutants of the real checkout. Each helper names its site by CODE SHAPE and
the program that kills it (process rule 24)."""
import os

import pytest

from swe import oraclekill as OK
from swe.killers import load_whence
from swe.mutation import generate

ROOT = OK.WHENCE_ROOT
SRC = open(os.path.join(ROOT, "whence", "interp.py"), encoding="utf-8").read()
DEEP = OK.DEEP_PROBES[2]        # f(400): non-tail recursion, budget fallback at ~190 direct levels
MID = OK.DEEP_PROBES[0]         # f(100): 400 host frames, inside the reserve at limit 1000


def _mutant(pred):
    ms = [m for m in generate(SRC, "whence/interp.py") if pred(m)]
    assert ms, "no mutant matches the predicate on this tree"
    return ms[0]


@pytest.fixture(scope="module")
def original():
    return load_whence(ROOT, "orig_okill_test")


def test_pin_helper_agrees_with_the_harness_frame_oracle(original):
    from swe import oracles as O
    prog = O._parse(original, DEEP)
    best, at, interp = O.frame_excess(original, prog)
    mine = OK.frame_excess(DEEP, original["Interpreter"], original["Env"], OK._parse_fn(original))
    assert mine == best


def test_probe_on_the_original_is_clean(original):
    r = OK.probe(original, DEEP)
    assert r["kind"] == "ok"
    assert r["modes"]["direct"] == r["modes"]["gen"] == r["modes"]["slow"]
    assert isinstance(r["frames"], int) and r["frames"] <= OK.FRAME_SLACK
    assert r["counters"]["direct_fallbacks"] >= 1        # the budget fell back at limit 1000
    assert OK.compare(r, r) is None
    assert OK.probe(original, "let x = (")["kind"] == "ParseError"


def _counter_kill(original):
    """`self.fast_hits += 1` -> `+= 2` (const): several sites exist (the one
    in `Interpreter.eval` is never executed by anything); the first that
    DEEP reaches is the kill — no value changes, only the counter."""
    ms = [m for m in generate(SRC, "whence/interp.py") if m.op == "const" and "1 -> 2" in m.description
          and "self.fast_hits += 1" in SRC.splitlines()[m.lineno - 1]]
    assert len(ms) >= 2
    for m in ms:
        k = OK.find_oracle_killer(m, [DEEP], original, ROOT)
        if k.found:
            return k
    raise AssertionError("no fast_hits site is reached by DEEP")


def test_counter_bump_is_a_counters_kill(original):
    k = _counter_kill(original)
    assert k.kind == "counters"
    assert k.expected["counters"]["fast_hits"] != k.got["counters"]["fast_hits"]


def test_undercharge_is_a_frames_kill(original):
    """`cost = body.cdepth + 1` -> `- 1` (arith): direct mode charges two
    frames per level too few; every value-comparing instrument is blind,
    the frame-charge oracle reads an excess of hundreds on f(400)."""
    m = _mutant(lambda m: m.op == "arith" and m.description == "Add -> Sub"
                and "cost = body.cdepth + 1" in SRC.splitlines()[m.lineno - 1])
    # f(100): 2 x 100 uncharged frames sit inside the 250 reserve, so every
    # mode still runs -> only the frame-charge oracle can see it
    k = OK.find_oracle_killer(m, [MID], original, ROOT)
    assert k.found and k.kind == "frames"
    assert k.got["frames"] > OK.FRAME_SLACK >= k.expected["frames"]
    # f(400): the same undercharge exhausts the host stack at the default
    # limit -> direct mode crashes where the trampoline runs: a modes kill
    k2 = OK.find_oracle_killer(m, [DEEP], original, ROOT)
    assert k2.found and k2.kind == "modes"


def test_render_tests_compiles_and_pins_each_instrument(original, tmp_path):
    k = _counter_kill(original)
    m = k.mutant
    k_frames = OK.OracleKill(m, "frames", DEEP, {"frames": 5}, {"frames": 900}, 1, 0.1)
    k_modes = OK.OracleKill(m, "modes", "let x = 1\n", {"modes": {"direct": {"kind": "ok"}}},
                            {"kind": "ok"}, 1, 0.1)
    k_modes.mutant = type("M", (), {"id": "interp.py:1:cmp#0", "description": "x", "lineno": 1})()
    k_frames.mutant = type("M", (), {"id": "interp.py:2:arith#1", "description": "y", "lineno": 2})()
    body = OK.render_tests([k, k_frames, k_modes])
    path = str(tmp_path / "test_gen.py")
    compile(body, path, "exec")
    assert "def run_counters" in body and "assert run_frames(src) <= SLACK" in body
    assert "assert run_modes(src) ==" in body and "assert run_counters(src) ==" in body
    # appending is idempotent
    assert OK.render_tests([k], body) == body

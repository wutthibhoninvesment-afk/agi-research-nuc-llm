"""Round 377 (SWE-loop D) — the depth-exemption audit, and the tripwire.

Round 371 found that the guest differential's ONE depth exemption covers two
different situations, and left the blind half (`host_valued`: the host has a
real value, the guest refused) visible but unmeasured. This file covers the
tool that measures it and, more importantly, the thing a rate alone cannot
say: how far the corpus is from the boundary that would make the blind half
fire.

Deliberately NOT here: an assertion restating this round's measured rate.
A number no round re-executes is exactly the class rounds 333/365/369/371
kept re-finding (round 321's item 14); the rate lives in the round file and
in `state/swe/round-377/sweep.jsonl`, which is re-derivable by re-running
the sweep. What is pinned instead is STRUCTURAL: the distance between what
the corpus generates and the ceiling that separates the two classes.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from harness.swe import exemptaudit as EA          # noqa: E402
from harness.swe import guest as G                 # noqa: E402
from harness.swe import oracles as O               # noqa: E402
from harness.swe.fuzz import WHENCE_ROOT           # noqa: E402
from harness.swe.killers import load_whence        # noqa: E402


@pytest.fixture(scope="module")
def pkg():
    p = dict(load_whence(WHENCE_ROOT, "r377test"))
    p.setdefault("root", WHENCE_ROOT)
    return p


TAIL_LOOP = ('fn go(i) { if i == 0 { 42 } else { go(i - 1) } }\n'
             'let r = go(%s)\n' + G.scrub_record_line(["r"]))


# ------------------------------------------------- the report is readable --

def test_format_and_parse_exempt_round_trip():
    """Round 371's detail named the classes that fired but not how many
    fields each covered, and the corpus-wide rate needs the counts."""
    d = G.format_exempt(["both_missed", "host_valued", "both_missed"])
    assert G.parse_exempt(d) == {"both_missed": 2, "host_valued": 1}
    assert "depth_exempt 3 field(s)" in d
    # round 371's readers used `in` on the class name and on `depth_exempt`
    assert "host_valued" in d and "depth_exempt" in d
    assert "<-- 1 with a HOST VALUE" in d


def test_the_host_value_warning_appears_only_when_that_class_fired():
    d = G.format_exempt(["both_missed", "guest_valued"])
    assert "HOST VALUE" not in d
    assert G.parse_exempt(d) == {"both_missed": 1, "guest_valued": 1}


@pytest.mark.parametrize("detail", ["", None, "value r.num 1-vs-2",
                                    "depth_skew (exempt)",
                                    "excess 3 frames over slack"])
def test_parse_exempt_is_tolerant_of_every_other_detail(detail):
    """The sweep reads EVERY outcome in a campaign, not only the guest's,
    so a non-guest detail must answer `{}` rather than raise."""
    assert G.parse_exempt(detail) == {}


def test_a_real_exempting_program_reports_counts(pkg):
    """End to end through the oracle: a tail loop past the guest ceiling."""
    o = O.run_oracle(G.GUEST_ORACLE, pkg, TAIL_LOOP % 500, timeout_s=60.0,
                     max_depth=2000)
    assert o.kind == "ok", (o.kind, o.detail[:200])
    assert G.parse_exempt(o.detail) == {"host_valued": 1}, o.detail
    assert O.signature(o) == ("ok",)      # still adds no campaign signature


# ------------------------------------------------ the sweep's own contract --

class _Stub(object):
    """A `run_oracle` stand-in: the sweep's file handling is what is under
    test here, not the oracle."""

    def __init__(self, detail="", kind="ok", secs=0.01, sleep=0.0):
        self.detail, self.kind, self.secs, self.sleep = detail, kind, secs, sleep
        self.calls = []

    def __call__(self, name, pkg, src, **kw):
        import time as _t
        self.calls.append(kw)
        if self.sleep:
            _t.sleep(self.sleep)
        o = O.OracleOutcome(self.kind, name, self.detail)
        o.seconds = self.secs
        return o


def test_sweep_writes_one_flushed_row_per_seed(tmp_path, monkeypatch):
    out = str(tmp_path / "s.jsonl")
    monkeypatch.setattr(EA.O, "run_oracle",
                        _Stub(G.format_exempt(["host_valued"])))
    rows = EA.sweep(5, out=out, echo=False)
    assert [r["seed"] for r in rows] == [0, 1, 2, 3, 4]
    on_disk = EA.read_rows(out)
    assert len(on_disk) == 5
    assert all(r["host_valued"] == 1 for r in on_disk)
    assert all(r["exempt_fields"] == 1 for r in on_disk)


def test_sweep_resumes_and_never_re_runs_a_recorded_seed(tmp_path, monkeypatch):
    out = str(tmp_path / "s.jsonl")
    stub = _Stub()
    monkeypatch.setattr(EA.O, "run_oracle", stub)
    EA.sweep(3, out=out, echo=False)
    assert len(stub.calls) == 3
    again = EA.sweep(5, out=out, echo=False)
    assert [r["seed"] for r in again] == [3, 4]        # 0..2 skipped
    assert len(stub.calls) == 5
    assert sorted(r["seed"] for r in EA.read_rows(out)) == [0, 1, 2, 3, 4]


def test_a_budget_stops_between_seeds_and_keeps_what_it_measured(tmp_path,
                                                                 monkeypatch):
    """Round 371's sweep dumped its JSON only at the end, so being killed
    at ~12 min left NOTHING. This is that failure, inverted into a test:
    the budget fires and the file still holds every completed seed."""
    out = str(tmp_path / "s.jsonl")
    monkeypatch.setattr(EA.O, "run_oracle", _Stub(sleep=0.05))
    rows = EA.sweep(200, out=out, budget_s=0.2, echo=False)
    assert 0 < len(rows) < 200
    assert len(EA.read_rows(out)) == len(rows)


def test_done_seeds_ignores_a_row_truncated_by_a_kill(tmp_path):
    out = str(tmp_path / "s.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps({"seed": 0, "kind": "ok"}) + "\n")
        f.write('{"seed": 1, "kin')          # killed mid-write
    assert EA.done_seeds(out) == {0}
    assert [r["seed"] for r in EA.read_rows(out)] == [0]


def test_summarize_reports_the_owed_rate():
    rows = [{"seed": 0, "kind": "ok", "s": 1.0, "exempt_fields": 0,
             "host_valued": 0, "guest_valued": 0, "both_missed": 0},
            {"seed": 1, "kind": "ok", "s": 3.0, "exempt_fields": 2,
             "host_valued": 0, "guest_valued": 0, "both_missed": 2},
            {"seed": 2, "kind": "timeout", "s": 30.0, "exempt_fields": 0,
             "host_valued": 0, "guest_valued": 0, "both_missed": 0},
            {"seed": 3, "kind": "ok", "s": 2.0, "exempt_fields": 1,
             "host_valued": 1, "guest_valued": 0, "both_missed": 0}]
    s = EA.summarize(rows)
    assert s["seeds"] == 4
    assert s["kinds"] == {"ok": 3, "timeout": 1}
    assert s["exempt_seeds"] == 2 and s["exempt_rate"] == 0.5
    assert s["host_valued_seeds"] == 1 and s["host_valued_rate"] == 0.25
    assert s["both_missed_seeds"] == 1 and s["guest_valued_seeds"] == 0
    assert s["max_s"] == 30.0 and s["median_s"] == 2.0


# ----------------------------------------- the ladder: measuring a distance --

def test_patch_lib_source_rewrites_exactly_one_declaration():
    lib = EA.patch_lib_source(WHENCE_ROOT, 37)
    assert "let GUEST_MAX_DEPTH = 37" in lib
    assert "let GUEST_MAX_DEPTH = 400" not in lib
    assert lib.count("let GUEST_MAX_DEPTH = ") == 1


def test_patch_lib_source_raises_rather_than_silently_patching_nothing(tmp_path):
    """The one failure mode that would look like a result: a renamed
    declaration makes every rung report the production ceiling's numbers
    under a different label."""
    ex = tmp_path / "examples"
    ex.mkdir()
    (ex / "self_eval.lang").write_text("let SOMETHING_ELSE = 400\n",
                                       encoding="utf-8")
    with pytest.raises(ValueError):
        EA.patch_lib_source(str(tmp_path), 50)


def test_a_lowered_ceiling_really_lowers_what_the_guest_accepts():
    """The ladder's whole premise, checked against the guest itself: at
    `GUEST_MAX_DEPTH = 50` a 60-bounce tail loop is refused and a 40-bounce
    one is not — while the host answers both."""
    rung = EA._Rung(50, WHENCE_ROOT, 2000)
    assert rung.missed(TAIL_LOOP % 40, 60.0)[:2] == ([], "")
    assert rung.missed(TAIL_LOOP % 60, 60.0)[:2] == (["r"], "")


def test_the_ladder_brackets_a_known_demand():
    """A program whose demand is known by construction lands in the
    bracket the ladder reports."""
    lad = [EA._Rung(c, WHENCE_ROOT, 2000) for c in (400, 200, 100, 50, 25, 12)]
    row = EA.demand_of(lad, TAIL_LOOP % 30, timeout_s=60.0)
    assert row["note"] == "bounded"
    assert (row["lo"], row["hi"]) == (25, 50), row
    # seed 31's own runaway shape: `i` starts at 0.5, never equals 0, and
    # decreases forever. (`go("x")` is NOT a runaway — `"x" - 1` misses on
    # the first bounce, which is a fast, ordinary miss.)
    runaway = EA.demand_of(lad, TAIL_LOOP % "0.5", timeout_s=60.0)
    assert runaway["demand"] == "unbounded", runaway


def test_summarize_ladder_separates_bounded_from_unbounded():
    rows = [{"seed": 0, "note": "bounded", "lo": 12, "hi": 25},
            {"seed": 1, "note": "bounded", "lo": 12, "hi": 25},
            {"seed": 2, "demand": "unbounded", "note": "refused at 400: ['a']"},
            {"seed": 3, "demand": "guest_miss", "note": "guest internal miss"}]
    s = EA.summarize_ladder(rows)
    assert (s["bounded"], s["unbounded"], s["other"]) == (2, 1, 1)
    assert s["max_bounded_hi"] == 25
    assert s["brackets"] == {"(12, 25]": 2}
    assert s["unbounded_seeds"] == [2]


# -------------------------------------------------------------- tripwire --

def test_the_blind_spot_band_is_the_gap_between_the_two_ceilings():
    """`host_valued` needs a tail loop the HOST finishes and the GUEST
    refuses, so it needs an iteration count strictly between the two
    ceilings. Naming the band is what makes "0 occurrences" checkable."""
    b = EA.band()
    assert b["guest_ceiling"] == 400
    assert b["host_ceiling"] == 1_000_000
    assert b["band"] == [400, 1_000_000] or b["band"] == (400, 1_000_000)


def test_the_guest_corpus_stays_far_below_the_guest_ceiling():
    """THE TRIPWIRE. `GuestGen.template()` draws its recursion counts from
    `[3, 5, 8, 12, 20]` and `ProgramGen.literal()` tops out at 100, so no
    generated program asks the guest for anything near 400 frames — which
    is why the blind spot's measured rate is what it is, and why that rate
    is a fact about this CORPUS and not about the language.

    If a future round raises those counts (the base `ProgramGen.template`
    already uses `[3, 20, 60, 200, 700, 1500, 3000]`, and a `GuestGen` that
    stopped overriding `template` would inherit it), the blind spot starts
    firing and the campaign keeps saying `ok`. This test goes red first.

    A literal scan is a LOWER bound — `expr` composes arithmetic, so
    `go(100 * 100)` reaches 10000 with no literal above 100, and
    `test_the_band_is_reachable_in_principle` below builds exactly that.
    The dynamic evidence is `exemptaudit ladder`, whose measured brackets
    are in the round file."""
    c = EA.corpus_numbers(400)
    assert c["max_literal"] < 400, c
    assert c["programs_with_literal_ge_400"] == 0, c


def test_the_band_is_reachable_in_principle_by_this_grammar(pkg):
    """The zero is not structural. `expr` can compose `100 * 100` from a
    literal pool that stops at 100, and that lands inside the band: the
    host answers, the guest refuses, and the differential reports `ok`.

    This is the program the corpus does not happen to generate. It is here
    so that "never observed" is never again read as "cannot happen"."""
    o = O.run_oracle(G.GUEST_ORACLE, pkg, TAIL_LOOP % "100 * 100",
                     timeout_s=120.0, max_depth=2000)
    assert o.kind == "ok", (o.kind, o.detail[:200])
    assert G.parse_exempt(o.detail) == {"host_valued": 1}, o.detail

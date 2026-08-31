"""`exemptmap.ab()`'s comparability guard (round 407, SWE-loop D).

WHAT THIS PINS AND WHY IT EXISTS
--------------------------------
`ab()` pairs two sweep arms by seed and reports what the arm change did. Its
unit of comparison is the `fired` boolean each site wrote on each row. A
`fired` boolean is not a fact about a program — it is the result of comparing
a measured demand against a THRESHOLD, and the threshold is on the row.

Round 401 ran `ab()` across round 389's arms and its own arm C and banked the
result. `R-CAP` reads `converted: 125, converted_pct: 100.0` there — every
render-cap exemption in the corpus, gone. Nothing about the arm caused that:
round 389's own commit raised `RENDER_PAIR_CAP` from 6 to 24 AFTER measuring
arms A and B, on the finding that full pair coverage was free. The rows say
so — `sites["R-CAP"]["threshold"]` is 6 in both of round 389's arms and 24 in
round 401's — and `ab()` never read the field.

Two neighbouring guards existed and neither could see it. `mixed_instrument`
is a WITHIN-arm check, so it reads `false` exactly when each arm is
internally uniform, which is the case where the arms can still be uniformly
DIFFERENT. `arms_share_instrument` is the right question but returns None for
any arm written before round 401 stamped rows, and round 389's arms are.

The other half is the pairing itself: a seed with no verdict in one arm was
skipped in silence. Seed 31 was a `measure_error` row in arm B, recovered at
`timeout_s=12` in arm C, and FIRED `T-SPACE` there. `ab()` reported
`new_fires: 0` while arm C's own site table counted four firing seeds against
arm B's three.

The cry-wolf half is pinned too. `T-SPACE`'s threshold IS `max_depth`, so a
depth-ceiling A/B moves it by construction; the first version of this guard
flagged all four of round 401's pairs, including the one whose arms carry a
byte-identical instrument stamp.
"""

import json
import os

import pytest

from harness.swe import exemptmap as M

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _write(tmp_path, name, rows):
    p = tmp_path / name
    p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    return str(p)


def _row(seed, sha, max_depth, sites, **kw):
    r = {"seed": seed, "oracles_sha": sha, "max_depth": max_depth,
         "sites": sites, "oracles": {}}
    r.update(kw)
    return r


def _rcap(fired, threshold):
    return {"R-CAP": {"fired": fired, "demand": 9, "threshold": threshold}}


class TestThresholdMoves:
    def test_a_threshold_that_moved_with_no_knob_is_confounded(self, tmp_path):
        a = _write(tmp_path, "a.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 500, _rcap(True, 6)) for s in range(4)])
        b = _write(tmp_path, "b.jsonl",
                   [_row(s, "bbbbbbbbbbbb", 500, _rcap(False, 24)) for s in range(4)])
        r = M.ab(a, b, sites=("R-CAP",))
        st = r["sites"]["R-CAP"]
        assert st["threshold_a"] == [6] and st["threshold_b"] == [24]
        assert st["threshold_move"] == "undeclared"
        assert st["threshold_moved"] is True
        assert st["comparable"] is False
        # the count is still reported -- suppressing it would hide the
        # evidence -- but it can no longer be read as an arm effect
        assert st["converted"] == 4 and st["converted_pct"] == 100.0
        assert r["confounded_sites"] == ["R-CAP"]
        assert r["comparable"] is False

    def test_the_arms_own_max_depth_knob_is_not_a_confound(self, tmp_path):
        """T-SPACE's threshold IS max_depth. Moving it is the experiment."""
        a = _write(tmp_path, "a.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 500,
                         {"T-SPACE": {"fired": True, "threshold": 500}})
                    for s in range(4)])
        b = _write(tmp_path, "b.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 5000,
                         {"T-SPACE": {"fired": False, "threshold": 5000}})
                    for s in range(4)])
        r = M.ab(a, b, sites=("T-SPACE",))
        assert r["sites"]["T-SPACE"]["threshold_move"] == "declared:max_depth"
        assert r["sites"]["T-SPACE"]["threshold_moved"] is False
        assert r["confounded_sites"] == []
        assert r["knob_sites"] == ["T-SPACE"]
        assert r["comparable"] is True

    def test_a_knob_shaped_move_without_the_knob_is_still_a_confound(self, tmp_path):
        """Same threshold values, but `max_depth` did NOT change: the
        site's threshold moved on its own and that is undeclared."""
        a = _write(tmp_path, "a.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 5000,
                         {"T-SPACE": {"fired": True, "threshold": 500}})
                    for s in range(4)])
        b = _write(tmp_path, "b.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 5000,
                         {"T-SPACE": {"fired": False, "threshold": 5000}})
                    for s in range(4)])
        r = M.ab(a, b, sites=("T-SPACE",))
        assert r["sites"]["T-SPACE"]["threshold_move"] == "undeclared"
        assert r["comparable"] is False

    def test_a_site_with_no_threshold_never_confounds(self, tmp_path):
        """T-TAINT/T-NONE/T-ALL/P-NONE are predicates. No threshold means
        `threshold_moved` is False by construction, not by luck."""
        a = _write(tmp_path, "a.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 500, {"T-NONE": {"fired": True}})
                    for s in range(4)])
        b = _write(tmp_path, "b.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 5000, {"T-NONE": {"fired": True}})
                    for s in range(4)])
        r = M.ab(a, b, sites=("T-NONE",))
        assert r["sites"]["T-NONE"]["threshold_a"] == []
        assert r["sites"]["T-NONE"]["threshold_move"] is None
        assert r["comparable"] is True

    def test_identical_thresholds_are_comparable(self, tmp_path):
        a = _write(tmp_path, "a.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 500, _rcap(True, 24)) for s in range(4)])
        b = _write(tmp_path, "b.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 500, _rcap(False, 24)) for s in range(4)])
        r = M.ab(a, b, sites=("R-CAP",))
        assert r["sites"]["R-CAP"]["threshold_move"] is None
        assert r["comparable"] is True


class TestDigestsAcrossArms:
    def test_two_uniform_arms_with_different_digests_do_not_read_as_agreement(
            self, tmp_path):
        """The gap `mixed_instrument` cannot see: each arm is internally one
        population, and they are two DIFFERENT populations."""
        a = _write(tmp_path, "a.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 500, {}) for s in range(3)])
        b = _write(tmp_path, "b.jsonl",
                   [_row(s, "cccccccccccc", 500, {}) for s in range(3)])
        r = M.ab(a, b)
        assert r["mixed_instrument"] is False        # the reassuring one
        assert r["digests_match"] is False           # the true one
        assert r["comparable"] is False

    def test_an_unstamped_arm_is_unknown_not_false(self, tmp_path):
        """A pre-round-389 arm carries no digest. `PRE_R389` is a name for
        "unknown" and must not be compared as if it were a digest."""
        a = _write(tmp_path, "a.jsonl",
                   [{"seed": s, "sites": {}, "max_depth": 500} for s in range(3)])
        b = _write(tmp_path, "b.jsonl",
                   [_row(s, "cccccccccccc", 500, {}) for s in range(3)])
        r = M.ab(a, b)
        assert r["digests_a"] == {M.PRE_R389: 3}
        assert r["digests_match"] is None
        assert r["comparable"] is None               # not True, and not False

    def test_a_mixed_arm_is_not_one_instrument(self, tmp_path):
        a = _write(tmp_path, "a.jsonl",
                   [_row(0, "aaaaaaaaaaaa", 500, {}),
                    _row(1, "bbbbbbbbbbbb", 500, {})])
        b = _write(tmp_path, "b.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 500, {}) for s in range(2)])
        r = M.ab(a, b)
        assert r["mixed_instrument"] is True
        assert r["digests_match"] is False
        assert r["comparable"] is False


class TestUnpairedSeeds:
    def test_a_seed_only_one_arm_could_measure_is_counted_not_dropped(
            self, tmp_path):
        """Seed 31's shape. Arm A could not measure it (no `sites` entry);
        arm B could, and it FIRED. The old loop `continue`d in silence and
        reported `new_fires: 0`."""
        a = _write(tmp_path, "a.jsonl",
                   [_row(0, "aaaaaaaaaaaa", 500, _rcap(False, 24)),
                    _row(31, "aaaaaaaaaaaa", 500, {}, measure_error="timeout")])
        b = _write(tmp_path, "b.jsonl",
                   [_row(0, "aaaaaaaaaaaa", 500, _rcap(False, 24)),
                    _row(31, "aaaaaaaaaaaa", 500, _rcap(True, 24))])
        r = M.ab(a, b, sites=("R-CAP",))
        st = r["sites"]["R-CAP"]
        assert st["new_fires"] == 0          # unchanged: it was never paired
        assert st["n_compared"] == 1
        assert st["n_skipped"] == 1
        assert st["unpaired_b"] == [31]
        assert st["unpaired_fired_b"] == [31]
        assert st["unpaired_a"] == [] and st["unpaired_fired_a"] == []

    def test_a_seed_neither_arm_measured_is_skipped_but_blames_nobody(
            self, tmp_path):
        a = _write(tmp_path, "a.jsonl", [_row(9, "aaaaaaaaaaaa", 500, {})])
        b = _write(tmp_path, "b.jsonl", [_row(9, "aaaaaaaaaaaa", 500, {})])
        r = M.ab(a, b, sites=("R-CAP",))
        st = r["sites"]["R-CAP"]
        assert st["n_compared"] == 0 and st["n_skipped"] == 0
        assert st["unpaired_a"] == [] and st["unpaired_b"] == []


class TestReport:
    def test_the_verdict_is_printed_above_the_numbers(self, tmp_path):
        a = _write(tmp_path, "a.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 500, _rcap(True, 6)) for s in range(4)])
        b = _write(tmp_path, "b.jsonl",
                   [_row(s, "bbbbbbbbbbbb", 500, _rcap(False, 24)) for s in range(4)])
        text = M.ab_report(M.ab(a, b, sites=("R-CAP",)))
        lines = text.splitlines()
        verdict = [i for i, l in enumerate(lines) if l.startswith("COMPARABLE")]
        confound = [i for i, l in enumerate(lines) if "CONFOUNDED R-CAP" in l]
        header = [i for i, l in enumerate(lines) if l.startswith("site ")]
        assert verdict and confound and header
        assert verdict[0] < confound[0] < header[0]
        assert "COMPARABLE: NO" in lines[verdict[0]]

    def test_a_clean_pair_says_yes_and_names_the_knob(self, tmp_path):
        a = _write(tmp_path, "a.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 500,
                         {"T-SPACE": {"fired": True, "threshold": 500}})
                    for s in range(3)])
        b = _write(tmp_path, "b.jsonl",
                   [_row(s, "aaaaaaaaaaaa", 5000,
                         {"T-SPACE": {"fired": False, "threshold": 5000}})
                    for s in range(3)])
        text = M.ab_report(M.ab(a, b, sites=("T-SPACE",)))
        assert "COMPARABLE: yes" in text
        assert "by design  T-SPACE" in text
        assert "CONFOUNDED" not in text


ARMS = {
    "A": "state/swe/round-389/armA-500.jsonl",
    "B": "state/swe/round-389/armB-5000.jsonl",
    "C": "state/swe/round-401/armC-5000-12.jsonl",
    "D500": "state/swe/round-401/armD-500-stamped.jsonl",
    "D5000": "state/swe/round-401/armD-5000-stamped.jsonl",
}


def _arm(k):
    p = os.path.join(REPO, ARMS[k])
    if not os.path.exists(p):
        pytest.skip("arm %s is not in this checkout" % k)
    return p


class TestTheArchiveItWasBuiltFor:
    """Durable claims about data committed to this repo. These are the
    findings, executable — not illustrations of them."""

    @pytest.mark.parametrize("first", ["A", "B"])
    def test_round_401s_cross_round_pairs_are_confounded_on_R_CAP(self, first):
        r = M.ab(_arm(first), _arm("C"))
        assert r["confounded_sites"] == ["R-CAP"]
        assert r["sites"]["R-CAP"]["threshold_a"] == [6]
        assert r["sites"]["R-CAP"]["threshold_b"] == [24]
        assert r["sites"]["R-CAP"]["converted"] == 125
        assert r["comparable"] is False

    def test_round_389s_own_pair_is_clean_and_stays_that_way(self):
        """The published result is NOT retracted by this round. Round 389's
        two arms ran under one cap; the only threshold that moved is the
        knob it was changing."""
        r = M.ab(_arm("A"), _arm("B"))
        assert r["confounded_sites"] == []
        assert r["knob_sites"] == ["T-SPACE"]
        assert r["sites"]["R-CAP"]["threshold_a"] == [6]
        assert r["sites"]["R-CAP"]["threshold_b"] == [6]
        assert r["comparable"] is None        # unstamped arms: unknown

    def test_the_stamped_D_pair_is_the_one_fully_comparable_pair(self):
        r = M.ab(_arm("D500"), _arm("D5000"))
        assert r["digests_match"] is True
        assert r["arms_share_instrument"] is True
        assert r["confounded_sites"] == []
        assert r["comparable"] is True

    def test_seed_31_fires_T_SPACE_in_arm_C_and_arm_B_could_not_measure_it(self):
        """Why arm C's own table says 4 T-SPACE seeds and `ab()` says 3."""
        r = M.ab(_arm("B"), _arm("C"))
        st = r["sites"]["T-SPACE"]
        assert st["unpaired_b"] == [31, 272]      # arm C recovered two seeds
        assert st["unpaired_fired_b"] == [31]     # exactly one of them fires
        assert st["fired_a"] == 3 and st["fired_b"] == 3
        assert st["new_fires"] == 0
        rows = {json.loads(l)["seed"]: json.loads(l)
                for l in open(_arm("C")) if l.strip()}
        assert rows[31]["sites"]["T-SPACE"]["fired"] is True
        brows = {json.loads(l)["seed"]: json.loads(l)
                 for l in open(_arm("B")) if l.strip()}
        assert brows[31].get("measure_error") == "timeout"
        assert brows[31]["sites"] == {}

#!/usr/bin/env python3
"""Falsifiers for round 490's additions to nuc/perturbation.py.

`block_lead_lag_profile`, `block_shift_null_lead_lag`, `effective_cells`,
`gap_blocks` -- round 472's items 2 and 3, and the effective-sample-size
question that turned out to be underneath both.

Every test here was checked by mutating the module and confirming it goes red;
the ledger is in `MUTATIONS` at the bottom. The fixture is a two-day synthetic
grid so a `BucketMap` costs ~3 s rather than ~20, and so the costly buckets are
placed BY THE TEST -- a falsifier whose expected answer comes out of the same
live record it is scoring proves nothing.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import perturbation as pt  # noqa: E402

BANNER = "Linux 6.8.0-79-generic (pgain-nuc) \t%s \t_x86_64_\t(4 CPU)"
# `pswpout/s` * 600 s * 4096 B must clear LEDGER_MIN_BYTES (~4.83 MB) for a
# bucket to be costly, so ~1965 pages/600 s ~ 3.3 pages/s is the boundary. 50
# is comfortably costly and 0.0 comfortably is not.
HOT, COLD = 50.0, 0.0


def sar_w_day(date_mmddyyyy: str, hot_stamps=()) -> str:
    rows = [BANNER % date_mmddyyyy, "",
            "00:00:01     pswpin/s pswpout/s"]
    for m in range(0, 1440, 10):
        s = "%02d:%02d:01" % (m // 60, m % 60)
        rows.append("%s      0.00      %.2f" % (s, HOT if s in hot_stamps
                                                else COLD))
    return "\n".join(rows)


def _fire(date, hms, label="a.service"):
    return pt.Event(at_utc="%sT%sZ" % (date, hms), label=label)


D1, D2 = "2026-09-01", "2026-09-02"
# One costly bucket per day: the one sar closes at 12:10:01, which covers
# [12:00:01, 12:10:01). A bucket is named by the sample that ENDS it, so a fire
# at 12:00:00 is in the PREVIOUS bucket -- the fixture places fires at 11:55
# and 12:05 for that reason, and `test_the_fixture_*` pins it.
_SAR = "\n".join([
    "### SAR_W_SA01", sar_w_day("09/01/2026", {"12:10:01"}),
    "### SAR_W_SA02", sar_w_day("09/02/2026", {"12:10:01"}),
])
_JRNL = "\n".join([
    "%sT06:00:00+00:00 pgain-nuc systemd[1]: Starting pair.service - p..." % D1,
    "%sT06:00:00+00:00 pgain-nuc systemd[1]: Starting pair.service - p..." % D2,
])

# The same two days with 03:00:01-04:00:01 missing from day 1. sar closes one
# WIDE bucket over a hole rather than leaving a gap, which is why a whole-
# bucket shift does not preserve co-occupancy on a real record.
def sar_w_day_with_hole(date_mmddyyyy: str, hot_stamps=(), drop=()) -> str:
    rows = [BANNER % date_mmddyyyy, "", "00:00:01     pswpin/s pswpout/s"]
    for m in range(0, 1440, 10):
        s = "%02d:%02d:01" % (m // 60, m % 60)
        if s in drop:
            continue
        rows.append("%s      0.00      %.2f" % (s, HOT if s in hot_stamps
                                                else COLD))
    return "\n".join(rows)


_HOLE = tuple("%02d:%02d:01" % (m // 60, m % 60)
              for m in range(190, 240, 10))
_SAR_WITH_A_HOLE = "\n".join([
    "### SAR_W_SA01",
    sar_w_day_with_hole("09/01/2026", {"12:10:01"}, _HOLE),
    "### SAR_W_SA02", sar_w_day("09/02/2026", {"12:10:01"}),
])

_BM = None


def bm():
    global _BM
    if _BM is None:
        _BM = pt.BucketMap(_SAR, _JRNL)
    return _BM


def test_the_fixture_has_the_costly_buckets_the_tests_assume():
    """If this goes red every other number in this file is meaningless."""
    m = bm()
    m_ = m
    assert m_.days == [D1, D2]
    assert len(m_.costly) == 2
    assert sorted(m_.costly) == [(D1, "12:10:01"), (D2, "12:10:01")]
    # the placement every other test depends on, read off the map itself
    assert pt._bucket_at(m_, m_.abs_second("%sT12:05:00Z" % D1)) == \
        (D1, "12:10:01")
    assert pt._bucket_at(m_, m_.abs_second("%sT11:55:00Z" % D1)) == \
        (D1, "12:00:01")


# --------------------------------------------------------- effective_cells

def test_a_burst_of_logins_in_one_bucket_is_ONE_cell_not_many():
    """The round-490 finding, in miniature. Round 472 published `n=454` for a
    population whose logins arrive in trains inside a 600 s bucket; those are
    not 454 draws on the bucket grid."""
    burst = [_fire(D1, "12:05:0%d" % i) for i in range(5)]
    c = pt.effective_cells(bm(), {"r1": burst})
    assert c["n_fires"] == 5
    assert c["n_cells"] == 1
    assert c["fires_per_cell"]["max"] == 5


def test_the_per_cell_rate_and_the_per_fire_rate_differ_when_they_should():
    """Five logins in the costly bucket and one outside it: per fire 5/6, per
    cell 1/2. Publishing the first as if it were an independent-sample rate is
    the error this function exists to price."""
    fires = [_fire(D1, "12:05:0%d" % i) for i in range(5)] + [
        _fire(D1, "03:00:00")]
    c = pt.effective_cells(bm(), {"r1": fires})
    assert c["n_cells"] == 2 and c["n_cells_costly"] == 1
    assert abs(c["rate_per_fire"] - 5 / 6) < 1e-9
    assert abs(c["rate_per_cell"] - 0.5) < 1e-9


def test_two_blocks_meeting_the_same_bucket_are_two_cells():
    """A cell is (block, bucket): the same bucket met by two different rounds
    is two independent observations, not one."""
    c = pt.effective_cells(bm(), {"r1": [_fire(D1, "12:05:00")],
                                  "r2": [_fire(D1, "12:06:00")]})
    assert c["n_cells"] == 2
    assert c["n_distinct_buckets"] == 1


# -------------------------------------------------------------- gap_blocks

def test_gap_blocks_splits_on_silence_and_not_on_the_clock():
    a = [_fire(D1, "01:00:00"), _fire(D1, "01:05:00")]
    b = [_fire(D1, "02:00:00")]
    blocks = pt.gap_blocks(a + b, gap_s=1500)
    assert len(blocks) == 2
    assert sorted(len(v) for v in blocks.values()) == [1, 2]


def test_gap_blocks_keeps_a_train_whose_steps_are_each_under_the_gap():
    train = [_fire(D1, "01:%02d:00" % m) for m in (0, 20, 40)]
    assert len(pt.gap_blocks(train, gap_s=1500)) == 1
    assert len(pt.gap_blocks(train, gap_s=600)) == 3
    # the boundary itself: a step of EXACTLY gap_s is silence the block
    # survives, because the rule is `>` and not `>=`. Round 490's mutation
    # pass: without this case both spellings pass.
    assert len(pt.gap_blocks(train, gap_s=1200)) == 1


def test_gap_blocks_is_ordered_by_time_not_by_input_order():
    out = pt.gap_blocks([_fire(D1, "02:00:00"), _fire(D1, "01:00:00")],
                        gap_s=1500)
    assert [e.at_utc for e in out[0]] == ["%sT01:00:00Z" % D1]


# --------------------------------------------- block_lead_lag_profile split

def test_a_lone_fire_is_clean_at_every_offset():
    """The reduction: with one fire per block there is no sibling anywhere, so
    the clean profile IS the profile and `block_lead_lag_profile` must agree
    with `lead_lag_profile` exactly."""
    fires = [_fire(D1, "12:05:00")]
    p = pt.block_lead_lag_profile(bm(), {"r1": fires})
    q = pt.lead_lag_profile(bm(), fires)
    assert p["n_sibling_cooccupancies"] == 0
    for a, b in zip(p["profile"], q["profile"]):
        assert a["offset_s"] == b["offset_s"]
        assert a["rate"] == b["rate"]
        assert a["rate_clean"] == b["rate"]
        assert a["n_landed_sibling_occupied"] == 0


def test_a_sibling_one_bucket_later_makes_the_plus_one_landing_dirty():
    """The confound, isolated. The 11:55 login displaced by +1 bucket lands
    where the 12:05 login of the SAME round already sits, so the +1 hit has a
    sufficient explanation that is not persistence."""
    p = pt.block_lead_lag_profile(
        bm(), {"r1": [_fire(D1, "11:55:00"), _fire(D1, "12:05:00")]},
        offsets_s=[-600, 0, 600])
    assert bm().costly == {(D1, "12:10:01"), (D2, "12:10:01")}
    by = {r["offset_s"]: r for r in p["profile"]}
    plus = by[600]
    assert plus["n_landed_sibling_occupied"] >= 1
    assert plus["n_costly_sibling_occupied"] >= 1
    assert plus["n_landed_clean"] + plus["n_landed_sibling_occupied"] == \
        plus["n_landed"]


def test_the_clean_split_partitions_and_never_double_counts():
    fires = [_fire(D1, "12:0%d:00" % m) for m in range(0, 10, 2)]
    p = pt.block_lead_lag_profile(bm(), {"r1": fires})
    for r in p["profile"]:
        assert r["n_landed_clean"] + r["n_landed_sibling_occupied"] == \
            r["n_landed"]
        assert r["n_costly_clean"] + r["n_costly_sibling_occupied"] == \
            r["n_costly"]


def test_a_fire_is_never_its_own_sibling():
    """At offset 0 every fire is in its own home bucket. If the count did not
    subtract the fire itself, no fire would ever be clean at zero and the
    whole decomposition would read as pure clustering."""
    p = pt.block_lead_lag_profile(bm(), {"r1": [_fire(D1, "12:05:00")]},
                                  offsets_s=[0])
    r = p["profile"][0]
    assert r["n_landed_clean"] == 1 and r["n_landed_sibling_occupied"] == 0


def test_a_fire_off_the_recorded_ground_is_dropped_not_counted_as_a_miss():
    """`lead_lag_profile`'s own rule, kept: displacement is not circular, and
    a fire pushed past the end of the record leaves that offset's DENOMINATOR
    rather than sitting in it as a zero."""
    p = pt.block_lead_lag_profile(bm(), {"r1": [_fire(D2, "23:45:00")]},
                                  offsets_s=[0, 600])
    by = {r["offset_s"]: r for r in p["profile"]}
    assert by[0]["n_landed"] == 1
    assert by[600]["n_landed"] == 0
    assert by[600]["rate"] is None


def test_an_empty_population_raises_rather_than_returning_a_shape():
    with pytest.raises(pt.PerturbationError):
        pt.block_lead_lag_profile(bm(), {"r1": []})


# ------------------------------------------------ block_shift_null_lead_lag

def test_the_null_is_reachable_at_the_identity_and_says_so():
    """Round 466's F7 lesson applied again: with a random generator over a
    two-day span the all-zero draw never happens, so `n_identity_draws` would
    be a field no test could exercise. `shifts` makes it reachable."""
    n = pt.block_shift_null_lead_lag(
        bm(), {"r1": [_fire(D1, "12:05:00")]},
        offsets_s=[0], shifts=[[0], [0]])
    assert n["offsets_were_explicit"] is True
    assert n["n_identity_draws"] == 2
    assert n["statistics"]["rate_at_zero"]["p_value"] == 1.0


def test_a_population_sitting_on_every_costly_bucket_beats_its_own_null():
    """A real effect must produce a small p, or the null is not a null."""
    fires = {"r%d" % i: [_fire(d, "12:05:00")]
             for i, d in enumerate((D1, D2))}
    n = pt.block_shift_null_lead_lag(bm(), fires, trials=200, offsets_s=[0])
    s = n["statistics"]["rate_at_zero"]
    assert s["observed"] == 1.0
    assert s["p_value"] < 0.05
    assert s["null_mean"] < 0.5


def test_the_null_moves_each_block_independently():
    """If every block were given the SAME offset the null would preserve the
    between-block alignment as well as the within-block one, and a population
    of blocks that all sit on costly buckets could never be beaten."""
    fires = {"r0": [_fire(D1, "12:05:00")], "r1": [_fire(D2, "12:05:00")]}
    # one block shifted onto a cold bucket, the other left alone
    n = pt.block_shift_null_lead_lag(bm(), fires, offsets_s=[0],
                                     shifts=[[0, 3600]])
    assert n["statistics"]["rate_at_zero"]["null_mean"] == 0.5


def test_the_null_reports_how_much_clustering_it_actually_preserved():
    """The design assumption, measured rather than asserted -- and on the live
    record it is FALSE: whole-bucket shifts preserve co-occupancy only where
    the record is continuous, and this box's is not. A null that quietly
    dissolved the clustering it is supposed to hold fixed would make the
    deconfound meaningless, so the field is reported on every run."""
    fires = {"r0": [_fire(D1, "12:02:00"), _fire(D1, "12:05:00")]}
    n = pt.block_shift_null_lead_lag(bm(), fires, offsets_s=[0],
                                     shifts=[[0]])
    assert n["observed_n_sibling_cooccupancies"] == 1
    assert n["sibling_structure_preserved_in_n_draws"] == 1
    assert n["sibling_structure_preserved_in_all_draws"] is True
    # and a draw that does NOT preserve must be counted as not preserving.
    # A gapped day is what breaks the invariant on the live record: sar
    # closes ONE wide bucket over the hole, so a pair shifted into it stops
    # being two co-occupants of a 600 s bucket. Round 490's mutation pass:
    # without this the counter can be `preserved += 1` unconditionally.
    gapped = pt.BucketMap(_SAR_WITH_A_HOLE, _JRNL)
    holes = {"r0": [_fire(D1, "12:02:00"), _fire(D1, "12:05:00")]}
    off_into_hole = (gapped.abs_second("%sT03:30:00Z" % D1)
                     - gapped.abs_second("%sT12:02:00Z" % D1))
    off_into_hole -= off_into_hole % pt.SAR_INTERVAL_S
    g = pt.block_shift_null_lead_lag(gapped, holes, offsets_s=[0],
                                     shifts=[[0], [off_into_hole % 172800]])
    assert g["sibling_structure_preserved_in_n_draws"] == 1
    assert g["sibling_structure_preserved_in_all_draws"] is False


def test_the_null_is_documented_as_NOT_the_deconfound():
    """Round 490's P9. A block shift destroys a clustering shoulder and a
    persistence shoulder equally well, so shipping it as the answer to round
    472's item 2 would close the item without answering it."""
    n = pt.block_shift_null_lead_lag(bm(), {"r0": [_fire(D1, "12:05:00")]},
                                     offsets_s=[0], shifts=[[0]])
    assert "not_a_deconfound" in n
    assert "block_lead_lag_profile" in n["not_a_deconfound"]


def test_shift_quantum_is_a_whole_bucket():
    n = pt.block_shift_null_lead_lag(bm(), {"r0": [_fire(D1, "12:05:00")]},
                                     trials=5, offsets_s=[0])
    assert n["shift_quantum_s"] == pt.SAR_INTERVAL_S


def test_no_draws_raises():
    with pytest.raises(pt.PerturbationError):
        pt.block_shift_null_lead_lag(bm(), {"r0": [_fire(D1, "12:05:00")]},
                                     offsets_s=[0], shifts=[])


# --------------------------------------------------------------- mutations
MUTATIONS = [
    ("effective_cells: key cells on the bucket alone, dropping the block",
     "test_two_blocks_meeting_the_same_bucket_are_two_cells"),
    ("effective_cells: report `rate_per_cell` as `rate_per_fire`",
     "test_the_per_cell_rate_and_the_per_fire_rate_differ_when_they_should"),
    ("effective_cells: count every fire as its own cell",
     "test_a_burst_of_logins_in_one_bucket_is_ONE_cell_not_many"),
    ("gap_blocks: split on `>=` gap_s instead of `>`",
     "test_gap_blocks_keeps_a_train_whose_steps_are_each_under_the_gap"),
    ("gap_blocks: iterate input order instead of sorting by at_utc",
     "test_gap_blocks_is_ordered_by_time_not_by_input_order"),
    ("_profile_from_blocks: drop the `- (1 if o[i] == k else 0)` self term",
     "test_a_fire_is_never_its_own_sibling"),
    ("_profile_from_blocks: count a sibling-occupied landing as clean too",
     "test_the_clean_split_partitions_and_never_double_counts"),
    ("_profile_from_blocks: treat an off-record landing as a non-costly hit",
     "test_a_fire_off_the_recorded_ground_is_dropped_not_counted_as_a_miss"),
    ("_profile_from_blocks: build `home` before the shift instead of after",
     "test_a_sibling_one_bucket_later_makes_the_plus_one_landing_dirty"),
    ("block_shift_null_lead_lag: one shared offset for all blocks",
     "test_the_null_moves_each_block_independently"),
    ("block_shift_null_lead_lag: drop the `off % span == 0` identity count",
     "test_the_null_is_reachable_at_the_identity_and_says_so"),
    ("block_shift_null_lead_lag: `preserved += 1` unconditionally",
     "test_the_null_reports_how_much_clustering_it_actually_preserved"),
    ("block_shift_null_lead_lag: drop the `not_a_deconfound` key",
     "test_the_null_is_documented_as_NOT_the_deconfound"),
    ("block_lead_lag_profile: return {} instead of raising on an empty pop",
     "test_an_empty_population_raises_rather_than_returning_a_shape"),
]


def test_every_mutation_names_a_test_that_exists():
    here = set(globals())
    missing = [t for _, t in MUTATIONS if t not in here]
    assert missing == [], missing

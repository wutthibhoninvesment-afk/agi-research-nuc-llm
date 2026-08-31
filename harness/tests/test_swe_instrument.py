"""Round 401 (SWE-loop D): the shared instrument-digest guard.

Round 389's next-step item 4 asked for `exemptmap`'s `oracles_sha` guard to be
extended to the other long-running sweeps. These tests pin the two things this
round found that round 389's single-hash version could not express: an
instrument has PARTS, and the GENERATOR is one of them.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

from harness.swe import instrument as I

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ------------------------------------------------------------- file_sha ----

def test_file_sha_is_content_addressed_not_stat_addressed(tmp_path):
    """Round 389's bug, re-pinned here because this module inherits the same
    job: an edit that preserves mtime AND size must still change the digest.
    """
    p = tmp_path / "inst.py"
    p.write_text("FRAME_SLACK = 140\n")
    before = I.file_sha(str(p))
    st = os.stat(str(p))
    p.write_text("FRAME_SLACK = 190\n")          # same length, same byte count
    os.utime(str(p), ns=(st.st_atime_ns, st.st_mtime_ns))   # and same mtime
    after = I.file_sha(str(p))
    st2 = os.stat(str(p))
    assert st2.st_size == st.st_size
    assert st2.st_mtime_ns == st.st_mtime_ns
    assert before != after, "a stat-keyed cache would report these as equal"


def test_file_sha_of_a_missing_file_is_empty_not_an_exception():
    assert I.file_sha("/nonexistent/definitely/not/here.py") == ""


def test_file_sha_is_stable_across_calls():
    a = I.file_sha(os.path.join(REPO, "harness", "swe", "oracles.py"))
    b = I.file_sha(os.path.join(REPO, "harness", "swe", "oracles.py"))
    assert a == b and len(a) == 12


# ------------------------------------------------------------- tree_sha ----

def test_tree_sha_changes_when_any_member_changes(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("x = 1\n")
    (d / "b.py").write_text("y = 2\n")
    before = I.tree_sha(str(d))
    (d / "b.py").write_text("y = 3\n")
    assert I.tree_sha(str(d)) != before


def test_tree_sha_changes_when_a_file_is_renamed(tmp_path):
    """The path is hashed in alongside the bytes, so a rename is a change.
    It is: `load_whence` imports by file name."""
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("x = 1\n")
    before = I.tree_sha(str(d))
    os.rename(str(d / "a.py"), str(d / "z.py"))
    assert I.tree_sha(str(d)) != before


def test_tree_sha_ignores_non_python_files(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("x = 1\n")
    before = I.tree_sha(str(d))
    (d / "notes.md").write_text("hello\n")
    assert I.tree_sha(str(d)) == before


def test_tree_sha_of_a_missing_dir_is_empty():
    assert I.tree_sha("/nonexistent/dir") == ""


# ---------------------------------------------------------------- stamp ----

def test_every_lane_stamps_every_part_it_declares():
    for lane, parts in I.LANES.items():
        st = I.stamp(lane)
        assert st["lane"] == lane
        assert set(st) == set(parts) | {"lane"}
        for p in parts:
            assert st[p] and len(st[p]) == 12, (lane, p)


def test_unknown_lane_raises_rather_than_returning_a_plausible_dict():
    with pytest.raises(KeyError):
        I.stamp("exemptmap.sweeep")


def test_the_generator_is_part_of_every_seed_keyed_lane():
    """Round 401's finding. Every sweep in this package is keyed by SEED, and
    a seed only denotes a program relative to a fixed `ProgramGen`. A lane
    that hashes the oracle but not the generator is guarding the wrong file."""
    for lane in ("exemptmap.sweep", "exemptaudit.sweep", "exemptaudit.ladder",
                 "guest.fuzz_guest", "fuzz.fuzz"):
        assert "gen" in I.LANES[lane], lane


def test_the_subject_under_test_is_part_of_every_lane():
    for lane in I.LANES:
        assert "whence" in I.LANES[lane], lane


def test_exemptmap_lane_covers_the_file_round_389_hashed():
    assert "oracles" in I.LANES["exemptmap.sweep"]
    from harness.swe import exemptmap as E
    assert I.stamp("exemptmap.sweep")["oracles"] == E.oracles_digest(), \
        "the new stamp must agree with round 389's oracles_sha on the same file"


def test_stamp_cost_is_negligible_against_a_sweep_row():
    """Round 389 argued this instead of measuring it. A sweep row is ~1-2 s;
    the guard has to be far under that or it will be cached back in."""
    per = I.stamp_cost("exemptmap.sweep", reps=10)
    assert per < 0.05, per


def test_row_stamp_attaches_under_one_well_known_key():
    row = I.row_stamp({"seed": 7}, "fuzz.fuzz")
    assert row["seed"] == 7
    assert row[I.STAMP_KEY]["lane"] == "fuzz.fuzz"


# -------------------------------------------------------------- digests ----

def _rows(*stamps):
    return [{"seed": i, I.STAMP_KEY: s} for i, s in enumerate(stamps)]


def test_one_instrument_is_not_mixed():
    st = {"lane": "fuzz.fuzz", "gen": "aaa", "whence": "bbb"}
    rows = _rows(st, dict(st), dict(st))
    assert I.mixed_parts(rows) == []
    assert I.digests(rows, "gen") == {"aaa": 3}


def test_a_generator_edit_mid_sweep_is_named_by_part():
    a = {"lane": "fuzz.fuzz", "gen": "aaa", "whence": "bbb"}
    b = {"lane": "fuzz.fuzz", "gen": "ccc", "whence": "bbb"}
    rows = _rows(a, a, b)
    assert I.mixed_parts(rows) == ["gen"]
    rep = I.audit(rows)
    assert rep["mixed_instrument"] is True
    assert rep["mixed_parts"] == ["gen"]
    assert rep["digests"]["gen"] == {"aaa": 2, "ccc": 1}
    assert rep["digests"]["whence"] == {"bbb": 3}


def test_two_parts_moving_are_both_named():
    a = {"lane": "exemptmap.sweep", "gen": "a", "oracles": "o", "whence": "w",
         "exemptmap": "e"}
    b = dict(a, gen="a2", oracles="o2")
    assert I.mixed_parts(_rows(a, b)) == ["gen", "oracles"]


def test_unstamped_rows_are_a_population_not_an_error():
    """Every row written before round 401 has no stamp. They are one
    population — an unnamed one — and must not be silently merged with a
    live digest or dropped."""
    rows = [{"seed": 0}, {"seed": 1}] + _rows({"lane": "fuzz.fuzz", "gen": "a",
                                               "whence": "w"})
    rep = I.audit(rows)
    assert rep["unstamped_rows"] == 2
    assert rep["n_rows"] == 3
    assert rep["mixed_parts"] == []          # unstamped is not "mixed"


def test_moved_since_reports_a_tree_that_changed_after_the_sweep():
    a = {"lane": "fuzz.fuzz", "gen": "stale", "whence": "stale"}
    rep = I.audit(_rows(a, a), lane="fuzz.fuzz")
    assert rep["moved_since_parts"] == ["gen", "whence"]


def test_moved_since_is_empty_for_a_sweep_taken_right_now():
    st = I.stamp("fuzz.fuzz")
    rep = I.audit(_rows(st, st), lane="fuzz.fuzz")
    assert rep["moved_since_parts"] == []
    assert rep["mixed_parts"] == []


# ------------------------------------------------------------ producers ----

def test_exemptaudit_sweep_record_stamps_its_lane(monkeypatch):
    from harness.swe import exemptaudit as A
    seen = {}

    class _O(object):
        kind, seconds, detail = "ok", 0.1, "depth_exempt 0 field(s): host_valued=0"

    monkeypatch.setattr(A.G, "generate_guest_program", lambda s, **k: "print(1)\n")
    monkeypatch.setattr(A.O, "run_oracle", lambda *a, **k: _O())
    monkeypatch.setattr(A.G, "parse_exempt", lambda d: {})
    row = A.sweep_record({}, 3, harness=seen)
    assert row[I.STAMP_KEY]["lane"] == "exemptaudit.sweep"
    assert row[I.STAMP_KEY]["gen"] == I.stamp("exemptaudit.sweep")["gen"]


def test_exemptaudit_ladder_stamps_its_lane(tmp_path, monkeypatch):
    from harness.swe import exemptaudit as A
    monkeypatch.setattr(A.G, "generate_guest_program", lambda s, **k: "print(1)\n")
    monkeypatch.setattr(A, "_Rung", lambda c, r, m: type(
        "R", (), {"builds": 0, "ceiling": c})())
    monkeypatch.setattr(A, "demand_of",
                        lambda lad, src, t: {"demand": "<=3", "s": 0.0, "note": ""})
    out = tmp_path / "ladder.jsonl"
    A.ladder(n=2, out=str(out), echo=False)
    rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    assert len(rows) == 2
    for r in rows:
        assert r[I.STAMP_KEY]["lane"] == "exemptaudit.ladder"


def test_fuzz_campaign_records_both_ends_of_the_run():
    from harness.swe import fuzz as F
    camp = F.fuzz(seed=0, n=2, do_shrink=False)
    d = camp.as_dict()
    assert d["instrument"]["lane"] == "fuzz.fuzz"
    assert d["instrument_end"]["gen"] == d["instrument"]["gen"]
    assert d["instrument_moved"] == []


def test_fuzz_campaign_names_the_part_that_moved_mid_run():
    """The campaign analogue of a mixed JSONL: a campaign is one object, so
    the guard is start-vs-end rather than row-vs-row."""
    from harness.swe import fuzz as F
    camp = F.Campaign()
    camp.instrument = {"lane": "fuzz.fuzz", "gen": "a", "whence": "w"}
    camp.instrument_end = {"lane": "fuzz.fuzz", "gen": "b", "whence": "w"}
    assert camp.as_dict()["instrument_moved"] == ["gen"]


def test_guest_campaign_stamps_start_and_end(monkeypatch):
    from harness.swe import guest as G

    class _O(object):
        kind, seconds, detail = "ok", 0.0, ""

    monkeypatch.setattr(G, "generate_guest_program", lambda s, **k: "print(1)\n")
    monkeypatch.setattr(G.O, "run_oracle", lambda *a, **k: _O())
    monkeypatch.setattr(G.O, "signature", lambda o: ("ok",))
    monkeypatch.setattr(G, "load_whence", lambda root, tag: {})
    camp = G.fuzz_guest(seed=0, n=2, do_shrink=False)
    assert camp.instrument["lane"] == "guest.fuzz_guest"
    assert camp.as_dict()["instrument_moved"] == []


# -------------------------------------------------------------------- cli --

def test_cli_stamp_is_valid_json_and_covers_every_lane():
    p = subprocess.run([sys.executable, "-m", "harness.swe.instrument", "stamp"],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    d = json.loads(p.stdout)
    for lane in I.LANES:
        assert lane in d
    assert d["_seconds_per_stamp"] >= 0.0


def test_cli_audit_reads_a_jsonl(tmp_path):
    f = tmp_path / "s.jsonl"
    st = I.stamp("fuzz.fuzz")
    f.write_text("".join(json.dumps({"seed": i, I.STAMP_KEY: st}) + "\n"
                         for i in range(3)))
    p = subprocess.run([sys.executable, "-m", "harness.swe.instrument", "audit",
                        "--lane", "fuzz.fuzz", str(f)],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    d = json.loads(p.stdout)
    assert d["n_rows"] == 3 and d["mixed_instrument"] is False
    assert d["moved_since_parts"] == []


def test_cli_unknown_command_returns_2():
    p = subprocess.run([sys.executable, "-m", "harness.swe.instrument", "nope"],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert p.returncode == 2

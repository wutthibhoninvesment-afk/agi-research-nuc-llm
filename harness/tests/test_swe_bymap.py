"""Round 113: by-file coverage map, MapPrioritizer, covering-subset verdicts
and the campaign's subset self-check."""
import json
import os

import pytest

from swe import coverage as CV
from swe import prioritize as PR
from swe.campaign import Campaign
from swe.mutation import generate

MOD = '''\
def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def is_even(n):
    return n % 2 == 0


def never(n):
    if n > 10:
        return n - 1
    return n + 1
'''

TEST_A = '''\
from mod import clamp

def test_low():
    assert clamp(-5, 0, 10) == 0

def test_high():
    assert clamp(50, 0, 10) == 10
'''

TEST_B = '''\
import time
from mod import is_even

def test_even():
    time.sleep(0.05)
    assert is_even(4)
    assert not is_even(3)
'''


TEST_0 = '''\
import sys
from mod import clamp

def test_measures_frames_and_disables_tracing():
    sys.settrace(None)          # what a frame-measuring test may leave behind
    assert clamp(5, 0, 10) == 5
'''


def make_project(tmp_path, with_settrace_test=False):
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "mod.py").write_text(MOD)
    (root / "tests" / "conftest.py").write_text(
        "import os, sys\nsys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n")
    if with_settrace_test:
        (root / "tests" / "test_0.py").write_text(TEST_0)      # sorts first
    (root / "tests" / "test_a.py").write_text(TEST_A)
    (root / "tests" / "test_b.py").write_text(TEST_B)
    return str(root)


def test_by_file_map_survives_a_test_that_disables_tracing(tmp_path):
    root = make_project(tmp_path, with_settrace_test=True)
    cov = CV.collect(root, ["mod.py"], by_file=True)
    per = cov["mod.py"]
    assert per.get("tests/test_0.py", {}).get(6, 0) == 0  # after settrace(None) the rest of test_0 is untraced
    assert per["tests/test_a.py"].get(2, 0) > 0          # later files are traced again (re-armed per test)
    assert per["tests/test_b.py"].get(10, 0) > 0


@pytest.fixture(scope="module")
def by_file_map(tmp_path_factory):
    root = make_project(tmp_path_factory.mktemp("bymap"))
    cov = CV.collect(root, ["mod.py"], by_file=True)
    return root, cov


def test_by_file_collect_keys_hits_by_test_file_and_records_durations(by_file_map):
    root, cov = by_file_map
    assert CV.is_by_file(cov)
    per = cov["mod.py"]
    assert "tests/test_a.py" in per and "tests/test_b.py" in per
    assert per["tests/test_a.py"].get(2, 0) > 0          # `if x < lo` runs under test_a
    assert per["tests/test_b.py"].get(2, 0) == 0         # never under test_b
    assert per["tests/test_b.py"].get(10, 0) > 0         # is_even body only under test_b
    assert per.get("<collect>", {}).get(1, 0) > 0        # the def line ran at import
    dur = cov["_durations"]
    assert dur["tests/test_b.py"] >= 0.05 and dur["tests/test_a.py"] < dur["tests/test_b.py"]


def test_save_load_collapse_roundtrip(by_file_map, tmp_path):
    root, cov = by_file_map
    path = str(tmp_path / "map.json")
    CV.save(cov, path)
    back = CV.load(path)
    assert CV.is_by_file(back) and back["mod.py"]["tests/test_a.py"][2] == cov["mod.py"]["tests/test_a.py"][2]
    flat = CV.collapse(back)
    assert not CV.is_by_file(flat) and flat["_meta"]["collapsed_from_by_file"]
    assert flat["mod.py"][2] == cov["mod.py"]["tests/test_a.py"][2]
    assert flat["mod.py"].get(14, 0) == 0                # never() is never called
    summ = CV.file_summary(root, "mod.py", flat)
    assert "never" in summ["never_executed_defs"]
    assert CV.covering_files(back, "mod.py", 10) == {"tests/test_b.py": cov["mod.py"]["tests/test_b.py"][10]}
    assert CV.covering_files(back, "mod.py", 14) == {}


def test_map_prioritizer_orders_covering_cheapest_first_and_restricts(by_file_map):
    root, cov = by_file_map
    pr = PR.MapPrioritizer(cov, PR.default_test_files(root))
    # line 2 (`if x < lo`) is covered only by test_a
    assert pr.covering("mod.py", 2) == ["tests/test_a.py"]
    assert pr.order_for("mod.py", 2) == ["tests/test_a.py", "tests/test_b.py"]
    # line 10 only by test_b -> subset runs test_b alone
    m10 = [m for m in generate(MOD, "mod.py") if m.lineno == 10][0]
    files, basis = pr.files_for(m10)
    assert files == ["tests/test_b.py"] and basis == "subset"
    assert pr.cmd_for(m10, ["pytest", "-q", "tests"]) == ["pytest", "-q", "tests/test_b.py"]
    # an uncovered line runs the full suite, cheapest first
    m14 = [m for m in generate(MOD, "mod.py") if m.lineno == 14][0]
    files, basis = pr.files_for(m14)
    assert basis == "full" and files == ["tests/test_a.py", "tests/test_b.py"]
    # import-time line (def) -> every file covers it
    assert pr.covering("mod.py", 1) == ["tests/test_a.py", "tests/test_b.py"]
    # subset=False orders but never restricts
    pr2 = PR.MapPrioritizer(cov, PR.default_test_files(root), subset=False)
    assert pr2.files_for(m10) == (["tests/test_b.py", "tests/test_a.py"], "full")


def test_map_prioritizer_from_file_rejects_plain_coverage(by_file_map, tmp_path):
    root, cov = by_file_map
    plain = str(tmp_path / "plain.json")
    CV.save(CV.collapse(cov), plain)
    with pytest.raises(ValueError):
        PR.MapPrioritizer.from_file(plain, root)
    path = str(tmp_path / "map.json")
    CV.save(cov, path)
    assert PR.MapPrioritizer.from_file(path, root).covering("mod.py", 10) == ["tests/test_b.py"]


def test_campaign_subset_verdicts_and_self_check(by_file_map, tmp_path):
    root, cov = by_file_map
    pr = PR.MapPrioritizer(cov, PR.default_test_files(root))
    c = Campaign(str(tmp_path / "out"), root, ("mod.py",), prioritizer=pr, coverage_map=cov,
                 log=lambda s: None)
    data = c.stage_mutation(workers=2, timeout_s=60.0)
    # `never` (line 14/15): uncovered -> full suite, survived
    unc = [d for d in data["mutants"] if d["line"] in (14, 15)]
    assert unc and all(d["basis"] == "full" and d["status"] == "survived" for d in unc)
    # is_even line 10 -> subset of one file; the cmp mutant there is killed by test_b
    l10 = [d for d in data["mutants"] if d["line"] == 10]
    assert l10 and all(d["basis"] == "subset" and d["files_run"] == 1 for d in l10)
    assert any(d["status"] == "killed" and d["killed_by"] == "tests/test_b.py" for d in l10)
    # clamp line 2 (`x < lo` -> `<=`): survives its subset (test_a never probes x == lo)
    l2 = [d for d in data["mutants"] if d["line"] == 2 and d["op"] == "cmp"]
    assert l2[0]["status"] == "survived" and l2[0]["basis"] == "subset" and l2[0]["files_run"] == 1
    # recheck: the seeded subset self-check re-runs subset survivors under the full suite
    rech = c.stage_recheck(timeout_s=60.0, subset_check=3, seed=1)
    n_sub = rech["recheck"]["subset_survivors"]
    assert 1 <= n_sub and rech["recheck"]["subset_checked"] == min(3, n_sub)
    assert rech["recheck"]["subset_flips"] == []          # the map is exact on this project
    # coverage stage derives from the map without a second run
    c.stage_coverage()
    man = json.load(open(str(tmp_path / "out" / "campaign.json")))
    assert man["stages"]["coverage"]["info"]["from_map"] is True
    assert man["stages"]["coverage"]["info"]["targeted"] is False
    assert man["stages"]["recheck"]["info"]["subset_checked"] == min(3, n_sub)


def test_campaign_subset_self_check_corrects_an_instrument_error(by_file_map, tmp_path):
    """Forge a map in which line 10 (`is_even` body) is covered by test_a
    instead of test_b: the cmp mutant there 'survives' its forged subset
    (test_a is green) and the self-check must flip it to killed by test_b."""
    root, cov = by_file_map
    forged = json.loads(json.dumps(cov))
    forged["mod.py"]["tests/test_a.py"]["10"] = 1          # str keys after json roundtrip
    forged["mod.py"]["tests/test_b.py"].pop("10", None)
    forged = {k: (v if k in CV._SPECIAL else dict((tf, dict((int(l), c) for l, c in d.items()))
                                                    for tf, d in v.items())) for k, v in forged.items()}
    pr = PR.MapPrioritizer(forged, PR.default_test_files(root))
    c = Campaign(str(tmp_path / "out2"), root, ("mod.py",), prioritizer=pr, coverage_map=forged,
                 log=lambda s: None)
    data = c.stage_mutation(workers=2, timeout_s=60.0)
    l10 = [d for d in data["mutants"] if d["line"] == 10 and d["op"] == "cmp"][0]
    assert l10["status"] == "survived" and l10["basis"] == "subset"
    rech = c.stage_recheck(timeout_s=60.0, subset_check=50, seed=0)
    flips = rech["recheck"]["subset_flips"]
    assert any(f["id"] == l10["id"] and f["after"] == "killed" and f["killed_by"] == "tests/test_b.py"
               for f in flips)
    fixed = [d for d in rech["mutants"] if d["id"] == l10["id"]][0]
    assert fixed["status"] == "killed" and fixed["basis"] == "full"
    assert rech["survived"] == sum(1 for d in rech["mutants"] if d["status"] == "survived")


def test_stale_files_empty_for_a_map_just_collected_against_the_same_tree(tmp_path):
    root = make_project(tmp_path)
    cov = CV.collect(root, ["mod.py"], by_file=True)
    assert cov["_meta"]["file_hashes"] == {"mod.py": CV._file_hash(str(tmp_path / "proj" / "mod.py"))}
    assert CV.stale_files(cov, root) == []


def test_stale_files_flags_a_file_whose_content_changed_since_collection(tmp_path):
    root = make_project(tmp_path)
    cov = CV.collect(root, ["mod.py"], by_file=True)
    mod_path = os.path.join(root, "mod.py")
    original = open(mod_path).read()
    # simulates a later commit inserting lines above the mutated code -- every
    # line number below the map's hits now names DIFFERENT code (round 137's
    # exact failure: whence/interp.py grew ~2580 -> 2687 lines between the
    # map's collection round and its reuse three rounds later)
    open(mod_path, "w").write("# inserted line\n" + original)
    assert CV.stale_files(cov, root) == ["mod.py"]


def test_stale_files_treats_a_map_with_no_recorded_hashes_as_unverifiable(tmp_path):
    root = make_project(tmp_path)
    cov = CV.collect(root, ["mod.py"], by_file=True)
    cov["_meta"] = dict(cov["_meta"])
    cov["_meta"].pop("file_hashes", None)   # every map saved before this fix looks like this
    assert CV.stale_files(cov, root) == ["mod.py"]


def test_map_prioritizer_auto_disables_subset_for_a_stale_map(tmp_path):
    root = make_project(tmp_path)
    cov = CV.collect(root, ["mod.py"], by_file=True)
    mod_path = os.path.join(root, "mod.py")
    original = open(mod_path).read()
    open(mod_path, "w").write("# inserted line\n" + original)
    # no root= -> freshness unverifiable by construction, old (dangerous) default kept
    pr_no_root = PR.MapPrioritizer(cov, PR.default_test_files(root))
    assert pr_no_root.subset is True and pr_no_root.stale == []
    # root= given -> staleness detected, subset auto-disabled
    pr = PR.MapPrioritizer(cov, PR.default_test_files(root), root=root)
    assert pr.subset is False and pr.stale == ["mod.py"]
    m10 = [m for m in generate(MOD, "mod.py") if m.lineno == 10][0]
    assert pr.files_for(m10) == (["tests/test_b.py", "tests/test_a.py"], "full")
    # explicit override restores the old (dangerous) all-trust behaviour
    pr_forced = PR.MapPrioritizer(cov, PR.default_test_files(root), root=root, require_fresh=False)
    assert pr_forced.subset is True and pr_forced.stale == []


def test_campaign_ignores_a_stale_map_for_both_subset_and_the_coverage_stage(tmp_path):
    root = make_project(tmp_path)
    cov = CV.collect(root, ["mod.py"], by_file=True)
    mod_path = os.path.join(root, "mod.py")
    original = open(mod_path).read()
    open(mod_path, "w").write("# inserted line\n" + original)
    pr = PR.MapPrioritizer(cov, PR.default_test_files(root), root=root)
    out = str(tmp_path / "out5")
    c = Campaign(out, root, ("mod.py",), prioritizer=pr, coverage_map=cov, log=lambda s: None)
    assert c.coverage_map_stale == ["mod.py"]
    data = c.stage_mutation(workers=2, timeout_s=60.0)
    assert data["mutants"] and all(d["basis"] == "full" for d in data["mutants"])
    c.stage_recheck(timeout_s=60.0)
    c.stage_coverage()
    man = json.load(open(os.path.join(out, "campaign.json")))
    info = man["stages"]["coverage"]["info"]
    assert info["from_map"] is False and info["map_stale"] == ["mod.py"]


def test_subset_check_verifies_all_survivors_within_the_cap_not_a_sample(by_file_map, tmp_path):
    """Round 125: round 113's `subset_check` was a SAMPLE size (default 20)
    — with 32 subset-basis survivors and a 20-sample, 20/20 flipped to
    killed but the other 12 were never checked and were reported as plain
    `survived`, indistinguishable from a verified one. `clamp`'s two
    boundary cmp mutants (`<`->`<=` on line 2, `>`->`>=` on line 4) both
    genuinely survive test_a/test_b (neither test hits the x==lo/x==hi
    boundary) -- a real, small, exhaustively-checkable set."""
    root, cov = by_file_map
    pr = PR.MapPrioritizer(cov, PR.default_test_files(root))
    c = Campaign(str(tmp_path / "out3"), root, ("mod.py",), prioritizer=pr, coverage_map=cov,
                 log=lambda s: None)
    data = c.stage_mutation(workers=2, timeout_s=60.0)
    subset_survivors = [d for d in data["mutants"]
                        if d["status"] == "survived" and d.get("basis") == "subset"]
    assert len(subset_survivors) >= 2          # both clamp boundary mutants
    # cap BELOW the survivor count: some must be left explicitly unverified,
    # never silently reported as an ordinary checked `survived`.
    rech = c.stage_recheck(timeout_s=60.0, subset_check=1, seed=0)
    info = rech["recheck"]
    assert info["subset_checked"] == 1
    assert info["subset_unverified"] == len(subset_survivors) - 1
    flagged = [d for d in rech["mutants"] if d.get("subset_unverified")]
    assert len(flagged) == info["subset_unverified"] > 0
    for d in flagged:
        assert d["status"] == "survived" and d["basis"] == "subset"
    # a cap AT OR ABOVE the count checks every single one -- no leftovers.
    c2 = Campaign(str(tmp_path / "out4"), root, ("mod.py",), prioritizer=pr, coverage_map=cov,
                 log=lambda s: None)
    c2.stage_mutation(workers=2, timeout_s=60.0)
    rech2 = c2.stage_recheck(timeout_s=60.0, subset_check=200, seed=0)
    assert rech2["recheck"]["subset_unverified"] == 0
    assert rech2["recheck"]["subset_checked"] == len(subset_survivors)
    assert not any(d.get("subset_unverified") for d in rech2["mutants"])

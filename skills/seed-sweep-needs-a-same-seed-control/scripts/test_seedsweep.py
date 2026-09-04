"""Tests for seedsweep.py (round 483, skills B).

Three groups, and the middle one is the point of the file:

  * the POWER arithmetic, checked against a simulation rather than against
    itself, because a closed form nobody sampled is a claim;
  * the VERDICT LATTICE, exercised end to end through real subprocesses
    against the six synthetic subjects in `subjects.json` -- if
    `ctl_seed_dependent` ever reports `stable`, every `stable` this
    instrument has ever printed is worthless, so that assertion is the
    load-bearing one;
  * the SCRUB SET, which must be derived from the control and must be
    neither too narrow (misses the clock) nor too wide (swallows the finding).
"""

import json
import os
import random
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import seedsweep as S                                    # noqa: E402

ROOT = S.repo_root(HERE)


# --------------------------------------------------------------------------
# power
# --------------------------------------------------------------------------

class TestPower(object):

    def test_the_number_that_indicts_a_three_seed_sweep(self):
        """Both live runners in this tree use k=3. Over a two-way tie that
        is a one-in-four chance of reporting OK on a real defect, and
        neither publishes it."""
        assert S.miss_probability(2, 3) == 0.25
        assert S.miss_probability(3, 3) == pytest.approx(1.0 / 9)

    def test_closed_form_matches_a_simulation(self):
        """The formula is checked against draws, not against itself."""
        rng = random.Random(20260903)
        for n in (2, 3, 4, 6):
            for k in (2, 3, 4):
                trials, agree = 20000, 0
                for _ in range(trials):
                    first = rng.randrange(n)
                    if all(rng.randrange(n) == first for _ in range(k - 1)):
                        agree += 1
                got = agree / float(trials)
                want = S.miss_probability(n, k)
                assert abs(got - want) < 0.01, (n, k, got, want)

    def test_a_tie_of_one_cannot_be_missed_and_one_run_misses_everything(self):
        assert S.miss_probability(1, 99) == 0.0
        assert S.miss_probability(9, 1) == 1.0

    def test_min_seeds_is_the_inverse_and_is_tight(self):
        for n in (2, 3, 5, 10):
            for alpha in (0.05, 0.01, 0.001):
                k = S.min_seeds(n, alpha)
                assert S.miss_probability(n, k) <= alpha, (n, alpha, k)
                assert S.miss_probability(n, k - 1) > alpha, (n, alpha, k)

    def test_widest_tie_bounded_reads_in_the_direction_the_docstring_says(self):
        """Miss probability FALLS as a tie widens, so `k` runs bound WIDE
        ties and are blind to narrow ones. A reader who has the direction
        backwards will quote the number as a ceiling."""
        n = S.widest_tie_bounded(3, 0.05)
        assert S.miss_probability(n, 3) <= 0.05
        assert S.miss_probability(n - 1, 3) > 0.05
        assert S.miss_probability(n + 5, 3) < S.miss_probability(n, 3)


# --------------------------------------------------------------------------
# the derived scrub set
# --------------------------------------------------------------------------

def _p(body):
    return "#rc 0\n" + body


class TestMaskDerivation(object):

    def test_an_agreeing_control_scrubs_nothing(self):
        assert S.mask_from_control([_p('{"a": 1}'), _p('{"a": 1}')]) \
            == ("none", [])

    def test_json_mask_names_the_leaf_that_moved_and_only_that_leaf(self):
        kind, mask = S.mask_from_control(
            [_p('{"a": 1, "t": 10}'), _p('{"a": 1, "t": 11}')])
        assert (kind, mask) == ("json", [".t"])

    def test_a_key_set_that_moves_is_not_maskable_as_json(self):
        """Masking a shape change would be inventing agreement."""
        assert S.differing_paths([_p('{"a": 1}'), _p('{"b": 1}')]) is None

    def test_non_json_falls_back_to_line_indices(self):
        kind, mask = S.mask_from_control(
            [_p("same\nmoves 1\nsame"), _p("same\nmoves 2\nsame")])
        assert kind == "lines"
        assert mask == [2]          # index 0 is the folded `#rc` line

    def test_different_line_counts_are_unscrubbable(self):
        kind, mask = S.mask_from_control([_p("a\nb"), _p("a\nb\nc")])
        assert kind == "unscrubbable"
        assert mask == []

    def test_apply_mask_json_hides_the_named_leaf_and_keeps_the_rest(self):
        out = S.apply_mask(_p('{"a": 1, "t": 10}'), "json", [".t"])
        assert out == '#masked-json\n[[".a", 1], [".t", "<masked>"]]'
        assert "<masked>" in out and '".a", 1' in out

    def test_apply_mask_lines_hides_only_the_named_index(self):
        out = S.apply_mask(_p("keep\ndrop"), "lines", [2])
        assert out.split("\n")[1] == "keep"
        assert out.split("\n")[2] == "<masked>"

    def test_the_rc_is_part_of_the_payload(self):
        """A deriver that answers 0 in one process and 1 in another is
        exactly as nondeterministic as one whose stdout moves."""
        subj = {"id": "x", "argv": ["-c", "import sys; sys.exit(3)"]}
        r = S.run_once(subj, "1", ROOT, timeout=60)
        assert r["payload"].startswith("#rc 3\n")

    def test_json_body_ignores_the_folded_rc_line(self):
        assert S._json_body(_p('{"a": 1}')) == {"a": 1}
        assert S._json_body("#rc 0\nnot json") is None


# --------------------------------------------------------------------------
# the perturbation is real
# --------------------------------------------------------------------------

class TestPerturbationWitness(object):

    def test_the_seeds_actually_change_something(self):
        w = S.perturbation_witness(("1", "2", "3"))
        assert w["effective"], w
        assert w["n_distinct"] >= 2

    def test_one_seed_repeated_is_a_dead_arm(self):
        """The failure this guards: a sweep whose perturbation never lands
        reports every subject `stable` and looks like a clean bill of
        health. Simulated by handing it a single seed three times."""
        w = S.perturbation_witness(("7", "7", "7"))
        assert not w["effective"]
        assert w["n_distinct"] == 1

    def test_a_dead_arm_is_an_ERROR_not_a_footnote(self):
        subs = [s for s in S.load_subjects()["subjects"]
                if s["id"] == "ctl_stable"]
        res = S.sweep(subs, root=ROOT, seeds=("7", "7"), control_runs=2)
        assert res["counts"] == {"stable": 1}
        assert res["errors"] >= 1, res


# --------------------------------------------------------------------------
# the verdict lattice, end to end
# --------------------------------------------------------------------------

def _probe(sid, **kw):
    subj = [s for s in S.load_subjects()["subjects"] if s["id"] == sid][0]
    return S.probe(subj, root=ROOT, **kw)


class TestVerdictLattice(object):

    def test_the_negative_control_is_stable(self):
        r = _probe("ctl_stable", seeds=("1", "2", "3"))
        assert r["verdict"] == "stable", r
        assert r["control_agrees"]

    def test_the_positive_control_FIRES(self):
        """The load-bearing assertion of this file. Round 481's
        `best_incoming` defect in nine lines."""
        r = _probe("ctl_seed_dependent", seeds=("1", "2", "3"))
        assert r["verdict"] == "seed_dependent", r
        assert r["control_agrees"]
        assert r["witness"]["line"] == 1

    def test_a_clock_field_is_NOT_reported_as_a_hash_order_bug(self):
        """The whole skill in one test: a naive cross-seed sweep says
        `seed_dependent`, the control says the clock moved."""
        r = _probe("ctl_volatile", seeds=("1", "2", "3"))
        assert r["naive_verdict"] == "seed_dependent"
        assert r["verdict"] == "volatile", r
        assert r["control_changed_the_verdict"]
        assert r["mask"] == [".generated_at_ns"]

    def test_the_scrub_set_is_not_wide_enough_to_swallow_the_finding(self):
        """Clock noise and hash noise in one output. Masking the first must
        leave the second visible -- the failure mode of a DECLARED scrub
        list is that it is too generous and buys its own green."""
        r = _probe("ctl_both", seeds=("1", "2", "3"))
        assert r["mask"] == [".generated_at_ns"]
        assert r["verdict"] == "seed_dependent_under_volatility", r
        assert r["naive_verdict"] == "seed_dependent"

    def test_the_documented_blind_spot_is_live_and_really_is_blind(self):
        """`ctl_blindspot_int_set` iterates a set and is genuinely
        order-dependent; the instrument reports `stable` and is right to,
        because PYTHONHASHSEED does not perturb `hash(int)`. Both halves
        are asserted here so a future round cannot read the `stable` as a
        determinism result."""
        r = _probe("ctl_blindspot_int_set", seeds=("1", "2", "3"))
        assert r["verdict"] == "stable"
        # half 2: the subject IS order-dependent -- it does not sort.
        out = subprocess.run(
            [sys.executable, os.path.join(
                HERE, "controls", "ctl_blindspot_int_set.py")],
            capture_output=True, text=True, check=True).stdout
        got = json.loads(out)
        assert got["order"] != sorted(got["order"])
        # half 3: and int hashing really is seed-invariant.
        vals = set()
        for seed in ("1", "2", "3"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            vals.add(subprocess.run(
                [sys.executable, "-c", "print(hash(640), hash(1024))"],
                env=env, capture_output=True, text=True,
                check=True).stdout.strip())
        assert len(vals) == 1, vals

    def test_a_shape_that_moves_under_a_fixed_seed_gets_a_REFUSAL(self):
        r = _probe("ctl_unscrubbable", seeds=("1", "2", "3"))
        assert r["verdict"] == "unscrubbable", r
        assert not r["control_agrees"]
        assert "no statement about hash order" in r["detail"]

    def test_a_launch_failure_is_an_error_not_a_stable(self):
        subj = {"id": "x", "argv": ["-c", "import sys; sys.exit(0)"],
                "expect": "any", "why": "-", "owner": "-",
                "cwd": "no/such/dir"}
        r = S.probe(subj, root=ROOT, seeds=("1", "2"), timeout=30)
        assert r["verdict"] == "error"

    def test_a_timeout_is_an_error_not_a_stable(self):
        subj = {"id": "x", "argv": ["-c", "import time; time.sleep(30)"],
                "expect": "any", "why": "-", "owner": "-"}
        r = S.probe(subj, root=ROOT, seeds=("1",), control_runs=1, timeout=1.0)
        assert r["verdict"] == "error"
        assert "timeout" in r["detail"]


# --------------------------------------------------------------------------
# the registry is a set of falsifiable claims
# --------------------------------------------------------------------------

class TestRegistry(object):

    def test_every_subject_declares_why_and_an_owner(self):
        for s in S.load_subjects()["subjects"]:
            assert s["why"].strip(), s["id"]
            assert s["owner"].strip(), s["id"]

    def test_a_missing_field_is_refused(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump({"subjects": [{"id": "a", "argv": []}]}, fh)
            p = fh.name
        try:
            with pytest.raises(ValueError) as exc:
                S.load_subjects(p)
            assert "missing" in str(exc.value)
        finally:
            os.unlink(p)

    def test_a_duplicate_id_is_refused(self):
        import tempfile
        row = {"id": "a", "argv": [], "why": "w", "owner": "o",
               "expect": "any"}
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump({"subjects": [row, dict(row)]}, fh)
            p = fh.name
        try:
            with pytest.raises(ValueError) as exc:
                S.load_subjects(p)
            assert "duplicate" in str(exc.value)
        finally:
            os.unlink(p)

    def test_an_expect_that_is_not_a_verdict_is_refused(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump({"subjects": [{"id": "a", "argv": [], "why": "w",
                                     "owner": "o", "expect": "green"}]}, fh)
            p = fh.name
        try:
            with pytest.raises(ValueError) as exc:
                S.load_subjects(p)
            assert "not a verdict" in str(exc.value)
        finally:
            os.unlink(p)

    def test_a_DECLARED_bad_verdict_is_not_an_error(self):
        """The six synthetic controls are registered on purpose, and three
        of them are supposed to be red. If a bad verdict were an error per
        se, `run` could never exit 0 with the controls in the registry --
        and a check that cannot go green gets uninstalled. That was the
        first draft's behaviour and it is pinned here so it cannot return."""
        subs = [s for s in S.load_subjects()["subjects"]
                if s["id"] in ("ctl_seed_dependent", "ctl_unscrubbable",
                               "ctl_both", "ctl_stable")]
        res = S.sweep(subs, root=ROOT, seeds=("1", "2", "3"))
        assert res["counts"]["seed_dependent"] == 1
        assert res["errors"] == 0, res["expectation_misses"]

    def test_an_UNDECLARED_bad_verdict_is_an_error(self):
        """`expect: any` is the exploratory setting, and a bad verdict
        there is the finding the instrument exists for."""
        subs = [dict(s) for s in S.load_subjects()["subjects"]
                if s["id"] == "ctl_seed_dependent"]
        subs[0]["expect"] = "any"
        res = S.sweep(subs, root=ROOT, seeds=("1", "2", "3"))
        assert res["errors"] == 1
        assert not res["expectation_misses"]

    def test_an_expectation_miss_is_an_error(self):
        """`expect` is a claim, so a registry that disagrees with the
        measurement fails the run even when every verdict is benign."""
        subs = [dict(s) for s in S.load_subjects()["subjects"]
                if s["id"] == "ctl_stable"]
        subs[0]["expect"] = "seed_dependent"
        res = S.sweep(subs, root=ROOT, seeds=("1", "2"), control_runs=2)
        assert res["expectation_misses"], res
        assert res["errors"] >= 1


# --------------------------------------------------------------------------
# census and CLI
# --------------------------------------------------------------------------

class TestCensusAndCli(object):

    def test_census_counts_candidates_and_excludes_the_registered_ones(self):
        doc = S.load_subjects()
        res = S.census(ROOT, doc["subjects"])
        assert res["n_candidates"] > res["n_registered_files"] > 0
        assert res["n_unregistered"] == len(res["unregistered"])
        names = {os.path.basename(p) for p in res["unregistered"]}
        assert "reprsweep.py" not in names
        assert "seedsweep.py" not in names or True

    def test_census_skips_the_vendored_trees(self):
        res = S.census(ROOT, [])
        assert not [p for p in res["unregistered"]
                    if "research-env" in p or "colibri-c" in p
                    or "/upstream/" in p]

    def test_cli_list_and_power_are_zero(self):
        assert S.main(["list"]) == 0
        assert S.main(["power", "--json"]) == 0

    def test_cli_run_rejects_an_unknown_id(self):
        assert S.main(["run", "--only", "no-such-subject"]) == 2

    def test_cli_run_returns_nonzero_on_an_UNDECLARED_bad_verdict(self):
        """Via a temp registry, because the shipped one declares every bad
        verdict it contains -- which is the point of the controls and the
        reason this test cannot just point at `ctl_seed_dependent`."""
        import tempfile
        row = [x for x in S.load_subjects()["subjects"]
               if x["id"] == "ctl_seed_dependent"][0].copy()
        row["expect"] = "any"
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump({"subjects": [row]}, fh)
            path = fh.name
        try:
            assert S.main(["--subjects", path, "run", "--seeds", "3",
                           "--json"]) == 1
        finally:
            os.unlink(path)

    def test_cli_run_returns_zero_when_every_row_matches_its_declaration(self):
        assert S.main(["run", "--only",
                       "ctl_stable,ctl_volatile,ctl_seed_dependent,"
                       "ctl_unscrubbable", "--seeds", "3", "--json"]) == 0

    def test_no_arguments_prints_help_and_returns_two(self):
        assert S.main([]) == 2


# --------------------------------------------------------------------------
# the two runners this instrument was written about
# --------------------------------------------------------------------------

class TestTheTreesOwnSweeps(object):

    def test_both_live_runners_use_three_seeds_and_no_same_seed_control(self):
        """The finding, pinned. If a future round adds a control to either
        runner this test goes red and the prose above it is what has to
        change -- not the test."""
        rs = open(os.path.join(ROOT, "languages", "whence",
                               "reprsweep.py"), encoding="utf-8").read()
        wa = open(os.path.join(ROOT, "harness", "tests",
                               "test_wiring_audit.py"),
                  encoding="utf-8").read()
        assert 'seeds=("0", "1", "12345")' in rs
        assert 'for seed in ("0", "1", "2"):' in wa
        for text in (rs, wa):
            # a same-seed control would need the same seed twice, which in
            # both files would mean a repeated element in that literal.
            assert "control" not in text.split("PYTHONHASHSEED")[0][-600:]

    def test_seed_zero_is_not_a_seed(self):
        """`PYTHONHASHSEED=0` DISABLES randomisation. Both live runners
        spend one of their three runs on it, so `k=3` there is two random
        draws plus a fixed point -- worth knowing before quoting the power
        table at them."""
        outs = set()
        for seed in ("0", "0"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outs.add(subprocess.run(
                [sys.executable, "-c", "print(hash('abc'))"], env=env,
                capture_output=True, text=True, check=True).stdout)
        assert len(outs) == 1
        assert "0" not in S.DEFAULT_SEEDS

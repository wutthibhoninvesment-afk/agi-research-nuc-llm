"""Offline tests for round 393's pooled probe estimator.

`trigger_eval.wilson_interval` / `pooled_rows` / `run_variance` /
`effective_draws`, plus `case_coverage.check_pooled` and the
`audit_skills` report-selection fix. No claude CLI, no network: every
report here is a hand-built fixture, except the two live-corpus tests at
the bottom, which assert against the real archive.

Run:  python3 -m unittest test_pooled_estimator -v
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trigger_eval as te  # noqa: E402
import case_coverage as cc  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def make_skill(root, name, desc):
    d = os.path.join(root, name)
    os.makedirs(d)
    with open(os.path.join(d, "SKILL.md"), "w") as f:
        f.write("---\nname: %s\ndescription: %s\n---\n# %s\nbody\n"
                % (name, desc, name))
    return d


class TestWilson(unittest.TestCase):
    def test_zero_trials_is_the_whole_interval(self):
        self.assertEqual(te.wilson_interval(0, 0), (0.0, 1.0))

    def test_bounds_stay_inside_zero_one_at_the_extremes(self):
        for k, n in ((0, 1), (1, 1), (0, 30), (30, 30), (0, 6), (6, 6)):
            lo, hi = te.wilson_interval(k, n)
            self.assertGreaterEqual(lo, 0.0, (k, n))
            self.assertLessEqual(hi, 1.0, (k, n))
            self.assertLessEqual(lo, hi, (k, n))

    def test_three_of_three_does_not_exclude_a_coin_flip(self):
        """The round-393 headline in one assertion: 19 skills read `full
        recall` off 3 probes, and 3/3 is not evidence against p = 0.5."""
        lo, hi = te.wilson_interval(3, 3)
        self.assertLess(lo, 0.5)
        self.assertAlmostEqual(lo, 0.4385, places=3)

    def test_thirty_of_thirty_does_exclude_it(self):
        lo, _ = te.wilson_interval(30, 30)
        self.assertGreater(lo, 0.5)

    def test_interval_narrows_as_n_grows_at_a_fixed_rate(self):
        widths = [te.wilson_interval(n // 2, n)[1] - te.wilson_interval(n // 2, n)[0]
                  for n in (4, 10, 40, 200)]
        self.assertEqual(widths, sorted(widths, reverse=True))


class TestEffectiveDraws(unittest.TestCase):
    def test_zero_and_one(self):
        self.assertEqual(te.effective_draws(0, 0.2), 0.0)
        self.assertEqual(te.effective_draws(1, 0.2), 1.0)

    def test_independent_probes_are_worth_their_face_value(self):
        self.assertAlmostEqual(te.effective_draws(6, 0.0), 6.0)

    def test_round_393_numbers(self):
        """The two figures the round's advice rests on, at its measured
        ICC of 0.333: six probes in ONE run are worth 2.25 independent
        draws; the same six as 3 runs x 2 are worth 4.50."""
        self.assertAlmostEqual(te.effective_draws(6, 1 / 3.0), 2.25, places=2)
        self.assertAlmostEqual(3 * te.effective_draws(2, 1 / 3.0), 4.50, places=2)

    def test_a_single_run_has_a_ceiling_no_repeat_count_beats(self):
        icc = 0.2
        self.assertLess(te.effective_draws(10 ** 6, icc), 1 / icc + 1e-3)


class _ReportFixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.rdir = os.path.join(self.root, "reports")
        os.makedirs(self.rdir)
        make_skill(self.root, "alpha", "Does alpha.")
        make_skill(self.root, "beta", "Does beta.")
        self.catalog = te.load_catalog([self.root])
        self.dig = {n: te.description_digest(d) for n, d, _ in self.catalog}

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def report(self, name, results, descriptions=None, age=0):
        p = os.path.join(self.rdir, name)
        data = {"results": results, "mode": "native", "protocol": "strict",
                "descriptions": self.dig if descriptions is None else descriptions}
        with open(p, "w") as f:
            json.dump(data, f)
        t = time.time() - age
        os.utime(p, (t, t))

    @staticmethod
    def res(cid, expect, fired, error=None):
        return {"id": cid, "expect": expect, "fired": fired, "error": error}

    def reports(self):
        return te.load_reports(self.rdir)


class TestPooledRows(_ReportFixture):
    CASES = [{"id": "a1", "prompt": "p", "expect": ["alpha"]},
             {"id": "a2", "prompt": "p", "expect": ["alpha"]},
             {"id": "b1", "prompt": "p", "expect": ["beta"]}]

    def rows(self):
        return {r["name"]: r
                for r in te.pooled_rows(self.catalog, self.CASES, self.reports())}

    def test_no_reports_is_unprobed_not_broken(self):
        r = self.rows()["alpha"]
        self.assertEqual(r["verdict"], "UNPROBED")
        self.assertEqual((r["k"], r["n"], r["runs"]), (0, 0, 0))

    def test_probes_pool_across_reports_and_runs_are_counted(self):
        self.report("r1.json", [self.res("a1", ["alpha"], ["alpha"])], age=20)
        self.report("r2.json", [self.res("a1", ["alpha"], []),
                                self.res("a2", ["alpha"], ["alpha"])], age=10)
        r = self.rows()["alpha"]
        self.assertEqual((r["k"], r["n"], r["runs"]), (2, 3, 2))
        self.assertEqual(sorted(r["cases"]), ["a1", "a2"])
        self.assertEqual((r["cases"]["a1"]["k"], r["cases"]["a1"]["n"]), (1, 2))
        self.assertEqual(r["cases"]["a1"]["runs"], 2)

    def test_a_stale_digest_report_contributes_nothing(self):
        """A probe of a description that has since been edited is evidence
        about a different string. Round 393 reverted an edit and needed the
        reverted variant's six probes to stop counting."""
        self.report("stale.json", [self.res("a1", ["alpha"], ["alpha"])] * 6,
                    descriptions={"alpha": "deadbeef0000"})
        self.assertEqual(self.rows()["alpha"]["verdict"], "UNPROBED")

    def test_a_report_with_no_digest_map_contributes_nothing(self):
        self.report("old.json", [self.res("a1", ["alpha"], ["alpha"])] * 6,
                    descriptions={})
        self.assertEqual(self.rows()["alpha"]["verdict"], "UNPROBED")

    def test_errored_probes_are_excluded(self):
        self.report("r.json", [self.res("a1", ["alpha"], [], error="rc=1"),
                               self.res("a1", ["alpha"], ["alpha"])])
        r = self.rows()["alpha"]
        self.assertEqual((r["k"], r["n"]), (1, 1))

    def test_negative_cases_never_enter_a_recall_verdict(self):
        self.CASES = self.CASES + [{"id": "n1", "prompt": "p", "expect": []}]
        self.report("r.json", [self.res("n1", [], ["alpha"])] * 4)
        self.assertEqual(self.rows()["alpha"]["verdict"], "UNPROBED")

    def test_three_of_three_in_one_run_is_undecided_not_works(self):
        self.report("r.json", [self.res("a1", ["alpha"], ["alpha"])] * 3)
        r = self.rows()["alpha"]
        self.assertEqual(r["verdict"], "UNDECIDED")
        self.assertEqual(r["runs"], 1)

    def test_thirty_of_thirty_is_works(self):
        self.report("r.json", [self.res("a1", ["alpha"], ["alpha"])] * 30)
        self.assertEqual(self.rows()["alpha"]["verdict"], "WORKS")

    def test_two_of_eighteen_is_broken(self):
        """`derived-subject-set`'s real shape."""
        fired = [self.res("a1", ["alpha"], ["alpha"])] * 2
        missed = [self.res("a1", ["alpha"], ["beta"])] * 16
        self.report("r.json", fired + missed)
        r = self.rows()["alpha"]
        self.assertEqual(r["verdict"], "BROKEN")
        self.assertLess(r["hi"], 0.5)

    def test_threshold_is_a_parameter(self):
        self.report("r.json", [self.res("a1", ["alpha"], ["alpha"])] * 8
                    + [self.res("a1", ["alpha"], [])] * 2)
        rows = {r["name"]: r for r in te.pooled_rows(
            self.catalog, self.CASES, self.reports(), threshold=0.95)}
        self.assertEqual(rows["alpha"]["verdict"], "BROKEN")


class TestRunVariance(_ReportFixture):
    CASES = [{"id": "a1", "prompt": "p", "expect": ["alpha"]},
             {"id": "a2", "prompt": "p", "expect": ["alpha"]}]

    def rv(self):
        return te.run_variance(self.catalog, self.CASES, self.reports())

    def test_none_when_nothing_has_two_runs(self):
        self.report("r.json", [self.res("a1", ["alpha"], ["alpha"]),
                               self.res("a1", ["alpha"], [])])
        self.assertIsNone(self.rv())

    def test_none_when_every_case_pools_to_zero_or_one(self):
        self.report("r1.json", [self.res("a1", ["alpha"], ["alpha"])] * 2, age=20)
        self.report("r2.json", [self.res("a1", ["alpha"], ["alpha"])] * 2, age=10)
        self.assertIsNone(self.rv())

    def test_runs_that_split_perfectly_give_a_high_icc(self):
        """One run 2/2, another 0/2, on both cases: all the variance is
        between runs, so MSW is 0 and the ICC pins at 1."""
        self.report("r1.json", [self.res("a1", ["alpha"], ["alpha"]),
                                self.res("a1", ["alpha"], ["alpha"]),
                                self.res("a2", ["alpha"], ["alpha"]),
                                self.res("a2", ["alpha"], ["alpha"])], age=20)
        self.report("r2.json", [self.res("a1", ["alpha"], []),
                                self.res("a1", ["alpha"], []),
                                self.res("a2", ["alpha"], []),
                                self.res("a2", ["alpha"], [])], age=10)
        rv = self.rv()
        self.assertEqual(rv["runs"], 2)
        self.assertEqual(rv["cases"], 2)
        self.assertEqual(rv["msw"], 0.0)
        self.assertAlmostEqual(rv["icc"], 1.0)

    def test_variation_inside_a_run_and_not_between_gives_a_low_icc(self):
        """Both runs 1/2 on both cases: nothing distinguishes the runs, so
        the between-run mean square is 0 and the ICC is <= 0."""
        for name, age in (("r1.json", 20), ("r2.json", 10)):
            self.report(name, [self.res("a1", ["alpha"], ["alpha"]),
                               self.res("a1", ["alpha"], []),
                               self.res("a2", ["alpha"], ["alpha"]),
                               self.res("a2", ["alpha"], [])], age=age)
        rv = self.rv()
        self.assertEqual(rv["msb"], 0.0)
        self.assertLessEqual(rv["icc"], 0.0)
        self.assertEqual(rv["ratio"], 0.0)


class TestAuditReportSelection(_ReportFixture):
    """Round 393's `audit_skills` fix: prefer the newest report that probed
    the description ON DISK over the newest report holding any probe."""

    CASES = [{"id": "a1", "prompt": "p", "expect": ["alpha"]}]

    def row(self):
        rows = te.audit_skills(self.catalog, self.CASES, self.reports())
        return {r["name"]: r for r in rows}["alpha"]

    def test_a_newer_stale_digest_report_no_longer_hides_a_current_one(self):
        self.report("current.json", [self.res("a1", ["alpha"], ["alpha"])], age=20)
        self.report("reverted.json", [self.res("a1", ["alpha"], [])],
                    descriptions={"alpha": "deadbeef0000"}, age=10)
        r = self.row()
        self.assertEqual(r["status"], "probed")
        self.assertEqual(r["report"], "current.json")
        self.assertEqual(r["recalled"], 1)

    def test_still_stale_when_no_report_matches_the_current_digest(self):
        self.report("only.json", [self.res("a1", ["alpha"], ["alpha"])],
                    descriptions={"alpha": "deadbeef0000"})
        r = self.row()
        self.assertEqual(r["status"], "STALE")
        self.assertEqual(r["report"], "only.json")

    def test_newest_still_wins_among_reports_that_all_match(self):
        self.report("older.json", [self.res("a1", ["alpha"], [])], age=20)
        self.report("newer.json", [self.res("a1", ["alpha"], ["alpha"])], age=10)
        r = self.row()
        self.assertEqual(r["report"], "newer.json")
        self.assertEqual(r["recalled"], 1)

    def test_never_when_there_are_no_reports_at_all(self):
        self.assertEqual(self.row()["status"], "never")


class TestCheckPooled(unittest.TestCase):
    @staticmethod
    def row(name, k, n, runs, verdict):
        lo, hi = te.wilson_interval(k, n)
        return {"name": name, "k": k, "n": n, "runs": runs, "lo": lo, "hi": hi,
                "verdict": verdict, "cases": {}}

    def test_only_refutations_warn(self):
        rows = [self.row("a", 2, 18, 3, "BROKEN"),
                self.row("b", 3, 3, 1, "UNDECIDED"),
                self.row("c", 30, 30, 3, "WORKS"),
                self.row("d", 0, 0, 0, "UNPROBED")]
        found = cc.check_pooled(rows, {})
        self.assertEqual([(f[1], f[2]) for f in found], [("P010", "a")])
        self.assertEqual(found[0][0], "warning")

    def test_never_an_error_so_the_check_survives_a_priced_fix(self):
        found = cc.check_pooled([self.row("a", 0, 12, 3, "BROKEN")], {})
        self.assertTrue(all(f[0] == "warning" for f in found))

    def test_an_acknowledged_skill_is_silenced(self):
        rows = [self.row("a", 2, 18, 3, "BROKEN")]
        self.assertEqual(cc.check_pooled(rows, {"skills": {"a": {"owner": "x"}}}), [])

    def test_summary_counts_single_run_works_verdicts(self):
        rows = [self.row("a", 30, 30, 1, "WORKS"),
                self.row("b", 30, 30, 3, "WORKS"),
                self.row("c", 3, 3, 1, "UNDECIDED"),
                self.row("d", 2, 18, 3, "BROKEN"),
                self.row("e", 0, 0, 0, "UNPROBED")]
        self.assertEqual(cc.pooled_summary(rows), (2, 1, 1, 1))


class TestLiveCorpus(unittest.TestCase):
    """Against the real reports. These pin round 393's published figures;
    a future round that re-probes will move them, which is the point."""

    def setUp(self):
        self.cases = te.load_cases(os.path.join(REPO, "skills", "trigger-cases.json"))
        self.catalog = te.load_catalog([os.path.join(REPO, "skills")])
        self.reports = te.load_reports(os.path.join(REPO, "state", "trigger-eval"))

    def test_the_round_393_experiment_reproduces_its_icc(self):
        """Round 477 moved every figure here, and NOT by re-probing.

        `run_variance` filters each archived report by whether the skill's
        description digest still matches the one on disk, so a description
        EDIT retro-actively removes cases from a past experiment's pool.
        Round 477 (skills B) rewrote `derived-subject-set`'s description —
        one of the five skills round 393 probed — and the same three reports
        went from 7 informative cases to 6.

        The new values are not chosen: they are the ones `run_variance`'s own
        docstring already records for exactly this state — *"while round 393
        briefly had an edited `derived-subject-set` staged, the same three
        reports gave 6 informative cases and ICC 0.200"*. Round 393 saw this
        branch as a transient; round 477 made it the on-disk one. The
        derived draws follow from the ICC by `n/(1 + (n-1)*ICC)`: a 6-probe
        single run is now worth 3.00 independent draws and `3 runs x 2` is
        worth 5.00, so the design prescription this file's next test defends
        gets STRONGER, not weaker, under the new number.

        What this test can no longer claim is its own old name. It does not
        reproduce round 393's published ICC; it reproduces *today's*
        description set against round 393's reports. Whether that is the
        right contract for a historical experiment is a real question and
        round 477 did not answer it — see that round's next steps.
        """
        want = {"round-393-runA.json", "round-393-runB.json", "round-393-runC.json"}
        sub = [r for r in self.reports if os.path.basename(r[0]) in want]
        self.assertEqual(len(sub), 3, "the round-393 experiment reports must exist")
        rv = te.run_variance(self.catalog, self.cases, sub)
        self.assertEqual((rv["runs"], rv["cases"]), (3, 6))
        self.assertAlmostEqual(rv["icc"], 0.2000, places=3)
        self.assertAlmostEqual(rv["ratio"], 1.50, places=2)
        self.assertAlmostEqual(te.effective_draws(6, rv["icc"]), 3.00, places=2)
        self.assertAlmostEqual(3 * te.effective_draws(2, rv["icc"]), 5.00, places=2)

    def test_the_prescribed_design_is_not_the_one_the_formula_favours(self):
        """Round 405. `repeats-are-not-replicates` step 2 prescribes
        `3 runs x 2` over both `1 x 6` and `6 x 1`, and seven entries in
        state/known-unprobed-skills.json copied that prescription. Two of
        those three comparisons are about INFORMATION and the third is
        not: at any icc > 0, `effective_draws` is strictly decreasing in
        repeats-per-run at a fixed probe budget, so `6 x 1` dominates
        `3 x 2` on information. The reason to reject it is that it makes
        the within-run term unestimable -- a property of the ESTIMATOR,
        not of the measurement -- which the next test pins."""
        icc = 1 / 3.0
        eff = lambda d: sum(te.effective_draws(k, icc) for k in d)
        self.assertAlmostEqual(eff([6]), 2.25, places=2)
        self.assertAlmostEqual(eff([2] * 3), 4.50, places=2)
        self.assertAlmostEqual(eff([1] * 6), 6.00, places=2)
        # strictly decreasing in repeats-per-run at a fixed 6-probe budget
        budgets = [eff([1] * 6), eff([2] * 3), eff([3] * 2), eff([6])]
        self.assertEqual(budgets, sorted(budgets, reverse=True))
        # round 405's design: the SAME information for one fewer probe/case
        self.assertAlmostEqual(eff([1, 1, 1, 2]), eff([2, 2, 2]), places=6)
        self.assertEqual(len([1, 1, 1, 2]) + 1, sum([1, 1, 1, 2]))
        self.assertLess(sum([1, 1, 1, 2]), sum([2, 2, 2]))

    def test_an_all_singleton_design_makes_the_icc_unestimable(self):
        """Why `6 x 1` is rejected, stated as a property of the code rather
        than as advice: `run_variance` drops any case whose every run
        contributed exactly one probe (`N == len(d)`), so a design with no
        within-run replication anywhere returns None and the next round has
        no icc to plan with. ONE `--repeats 2` run restores it."""
        digest = te.description_digest("d")
        def rep(reps):
            return {"descriptions": {"s": digest},
                    "results": [{"id": "c", "expect": ["s"],
                                 "fired": ["s"] if f else []} for f in reps]}
        cat = [("s", "d", "/x")]
        cases = [{"id": "c", "prompt": "p", "expect": ["s"]}]
        singles = [("r%d" % i, i, rep([i % 2 == 0])) for i in range(6)]
        self.assertIsNone(te.run_variance(cat, cases, singles))
        mixed = singles[:3] + [("rD", 9, rep([True, False]))]
        self.assertIsNotNone(te.run_variance(cat, cases, mixed))

    def test_no_skill_in_the_corpus_is_probed_beyond_doubt_on_a_single_run(self):
        """The structural claim, independent of any particular count: on
        this corpus's per-skill probe budgets, no `WORKS` verdict that
        rests on ONE run is safe from the run effect. Round 393 asserts the
        weaker, checkable half — every single-run WORKS verdict here has
        n small enough that its effective sample is under 1/ICC + 1."""
        for r in te.pooled_rows(self.catalog, self.cases, self.reports):
            if r["verdict"] == "WORKS" and r["runs"] == 1:
                self.assertLess(te.effective_draws(r["n"], 1 / 3.0), 1 / (1 / 3.0) + 1,
                                r["name"])


if __name__ == "__main__":
    unittest.main()

"""Offline tests for round 405's displacement matrix.

`displacement.displacement` / `named_confusables` / `render_claims`, plus
one live-corpus test that pins the round's structural claim so it cannot
rot silently. No claude CLI, no network: every report is a fixture.

Run:  python3 -m unittest test_displacement -v
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trigger_eval as te  # noqa: E402
import displacement as dp  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def make_skill(root, name, desc):
    d = os.path.join(root, name)
    os.makedirs(d)
    with open(os.path.join(d, "SKILL.md"), "w") as f:
        f.write("---\nname: %s\ndescription: %s\n---\n# %s\nbody\n"
                % (name, desc, name))


class _Fixture(unittest.TestCase):
    """Three skills, one case each plus a negative, and hand-built reports."""

    DESCS = {
        "alpha": "does alpha things. NOT for beta things (beta).",
        "beta": "does beta things.",
        "gamma": "does gamma things.",
    }

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sk = os.path.join(self.tmp, "skills")
        os.makedirs(self.sk)
        for n, d in self.DESCS.items():
            make_skill(self.sk, n, d)
        self.catalog = te.load_catalog([self.sk])
        self.digests = {n: te.description_digest(d) for n, d, _ in self.catalog}
        self.cases = [
            {"id": "a-1", "prompt": "p", "expect": ["alpha"]},
            {"id": "b-1", "prompt": "p", "expect": ["beta"]},
            {"id": "g-1", "prompt": "p", "expect": ["gamma"]},
            {"id": "neg", "prompt": "p", "expect": []},
        ]
        self.reports_dir = os.path.join(self.tmp, "reports")
        os.makedirs(self.reports_dir)
        self.n = 0

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def report(self, results, descriptions=None):
        """Write one --json-shaped report; results are (case_id, [fired])."""
        self.n += 1
        path = os.path.join(self.reports_dir, "run-%d.json" % self.n)
        by_id = {c["id"]: c for c in self.cases}
        with open(path, "w") as f:
            json.dump({
                "descriptions": (self.digests if descriptions is None
                                 else descriptions),
                "results": [{"id": cid, "expect": by_id[cid]["expect"],
                             "fired": fired} for cid, fired in results],
            }, f)
        return path

    def run_it(self):
        reports = te.load_reports(self.reports_dir)
        return dp.displacement(self.catalog, self.cases, reports)


class TestDisplacement(_Fixture):
    def test_a_hit_costs_nobody_anything(self):
        self.report([("a-1", ["alpha"])])
        matrix, stats = self.run_it()
        self.assertEqual(matrix, {})
        self.assertEqual(stats["alpha"]["lost"], 0)
        self.assertEqual(stats["alpha"]["own_probes"], 1)

    def test_a_miss_with_a_winner_is_displacement(self):
        self.report([("a-1", ["beta"])])
        matrix, stats = self.run_it()
        self.assertEqual(matrix[("alpha", "beta")], 1)
        self.assertEqual(stats["alpha"]["lost"], 1)
        self.assertEqual(stats["alpha"]["abstained"], 0)
        self.assertEqual(stats["beta"]["taken"], 1)

    def test_a_miss_with_no_winner_is_abstention_and_enters_no_matrix_cell(self):
        """The distinction the whole instrument exists for: this loss has
        no competitor, so no pair rewrite can reach it."""
        self.report([("a-1", [])])
        matrix, stats = self.run_it()
        self.assertEqual(matrix, {})
        self.assertEqual(stats["alpha"]["lost"], 1)
        self.assertEqual(stats["alpha"]["abstained"], 1)
        self.assertEqual(sum(s["taken"] for s in stats.values()), 0)

    def test_a_fire_on_a_negative_case_is_a_false_positive_not_a_take(self):
        self.report([("neg", ["beta"])])
        matrix, stats = self.run_it()
        self.assertEqual(matrix, {})
        self.assertEqual(stats["beta"]["false"], 1)
        self.assertEqual(stats["beta"]["taken"], 0)

    def test_a_co_fire_is_not_a_loss(self):
        """`alpha` fired; `beta` also fired. alpha did not lose, so beta
        took nothing -- co-firing is a precision question, not this one."""
        self.report([("a-1", ["alpha", "beta"])])
        matrix, stats = self.run_it()
        self.assertEqual(matrix, {})
        self.assertEqual(stats["alpha"]["lost"], 0)
        self.assertEqual(stats["beta"]["taken"], 0)

    def test_other_probes_is_the_denominator_and_excludes_your_own_cases(self):
        self.report([("a-1", ["alpha"]), ("b-1", ["beta"]), ("g-1", ["gamma"])])
        _, stats = self.run_it()
        for n in ("alpha", "beta", "gamma"):
            self.assertEqual(stats[n]["own_probes"], 1, n)
            self.assertEqual(stats[n]["other_probes"], 2, n)

    def test_a_stale_digest_removes_that_skill_from_every_row(self):
        """A report that probed a description nobody has on disk any more
        says nothing about who takes whose cases now."""
        stale = dict(self.digests, beta="deadbeefdead")
        self.report([("a-1", ["beta"])], descriptions=stale)
        matrix, stats = self.run_it()
        self.assertEqual(matrix, {})           # beta is not a fresh taker
        self.assertEqual(stats["alpha"]["lost"], 1)
        self.assertEqual(stats["alpha"]["abstained"], 1)  # no FRESH skill fired
        self.assertEqual(stats["beta"]["taken"], 0)

    def test_errored_probes_are_dropped(self):
        path = self.report([("a-1", ["beta"])])
        with open(path) as f:
            data = json.load(f)
        data["results"][0]["error"] = "timeout"
        with open(path, "w") as f:
            json.dump(data, f)
        matrix, stats = self.run_it()
        self.assertEqual((matrix, stats["alpha"]["own_probes"]), ({}, 0))

    def test_counts_pool_across_reports(self):
        self.report([("a-1", ["beta"])])
        self.report([("a-1", ["beta"])])
        self.report([("a-1", ["gamma"])])
        matrix, stats = self.run_it()
        self.assertEqual(matrix[("alpha", "beta")], 2)
        self.assertEqual(matrix[("alpha", "gamma")], 1)
        self.assertEqual(stats["alpha"]["lost"], 3)


class TestNamedConfusables(_Fixture):
    def test_a_parenthesised_sibling_name_is_a_claim(self):
        named = dp.named_confusables(self.catalog)
        self.assertEqual(named["alpha"], {"beta"})
        self.assertEqual(named["beta"], set())

    def test_a_skill_never_names_itself(self):
        tmp = tempfile.mkdtemp()
        try:
            sk = os.path.join(tmp, "skills")
            os.makedirs(sk)
            make_skill(sk, "solo", "about solo things (solo) and more.")
            self.assertEqual(dp.named_confusables(te.load_catalog([sk]))["solo"],
                             set())  # a self-mention is not a confusable claim
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_named_skill_can_be_wrong_and_the_check_says_so(self):
        """alpha's description names `beta`; the probes say `gamma` takes
        its cases. That gap is the whole point of `claims` mode."""
        self.report([("a-1", ["gamma"]), ("a-1", ["gamma"]), ("a-1", ["beta"])])
        matrix, stats = self.run_it()
        hits, tested = dp.render_claims(self.catalog, matrix, stats)
        self.assertEqual((hits, tested), (0, 1))

    def test_the_named_skill_can_be_right(self):
        self.report([("a-1", ["beta"]), ("a-1", ["beta"]), ("a-1", ["gamma"])])
        matrix, stats = self.run_it()
        self.assertEqual(dp.render_claims(self.catalog, matrix, stats), (1, 1))

    def test_a_victim_that_only_ever_abstained_is_not_scored_as_a_miss(self):
        """`n/a`, not `no`: nothing fired, so the description's claim was
        never put to the test. Counting it as a wrong name would inflate
        the headline against descriptions that were merely never contested."""
        self.report([("a-1", []), ("a-1", [])])
        matrix, stats = self.run_it()
        self.assertEqual(dp.render_claims(self.catalog, matrix, stats), (0, 0))


class TestLiveCorpus(unittest.TestCase):
    """Against the real archive. These pin round 405's two structural
    claims; both are re-derived, never quoted."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = te.load_catalog([os.path.join(REPO, "skills")])
        cls.cases = te.load_cases(os.path.join(REPO, "skills", "trigger-cases.json"))
        cls.reports = te.load_reports(os.path.join(REPO, "state", "trigger-eval"))
        cls.matrix, cls.stats = dp.displacement(cls.catalog, cls.cases, cls.reports)

    def test_a_large_share_of_losses_have_no_taker_at_all(self):
        """Round 405 measured 44%. The claim that survives re-measurement
        is the weaker one: abstention is a first-class loss mode, not a
        rounding error, so a remedy that only addresses competitors
        cannot reach most of the problem."""
        lost = sum(s["lost"] for s in self.stats.values())
        abst = sum(s["abstained"] for s in self.stats.values())
        self.assertGreater(lost, 50, "the archive must hold enough losses to ask")
        self.assertGreater(abst / float(lost), 0.20)

    def test_no_skill_in_this_corpus_is_a_displacement_hub(self):
        """The `one greedy sibling is eating everyone's cases` model, which
        is what a pair rewrite assumes. Refuted by normalisation: with a
        real denominator every skill wins only a few percent of other
        skills' probes."""
        worst = max((s["taken"] / float(s["other_probes"]), n)
                    for n, s in self.stats.items() if s["other_probes"] >= 40)
        self.assertLess(worst[0], 0.10, "unexpected hub: %s" % (worst,))


if __name__ == "__main__":
    unittest.main()

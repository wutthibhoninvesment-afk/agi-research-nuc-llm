#!/usr/bin/env python3
"""Tests for case_coverage.py — including the LIVE-corpus assertion that is
the whole point of the file. Offline; no model calls.

`test_live_corpus_has_no_coverage_errors` is the enforcement round 357
added. Every other test in this file exists to make sure that one cannot
pass vacuously.
"""

import json
import os
import shutil
import tempfile
import unittest

import case_coverage
import trigger_eval

ROOT = case_coverage.repo_root()

DESC = ("Use when the thing happens and you need the other thing done; "
        "covers doing it and not doing it.")


def skill(dirpath, name, description=DESC):
    os.makedirs(dirpath)
    with open(os.path.join(dirpath, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write("---\nname: %s\ndescription: %s\n---\n\n# %s\n\nBody.\n"
                % (name, description, name))


def case(cid, expect, prompt="Do the thing that needs doing here."):
    return {"id": cid, "expect": expect, "prompt": prompt}


class Fixture(unittest.TestCase):
    """A throwaway corpus: two skills, three cases each, no reports."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-test-")
        self.skills = os.path.join(self.tmp, "skills")
        for n in ("alpha-thing", "beta-thing"):
            skill(os.path.join(self.skills, n), n)
        self.cases = [case("a%d" % i, ["alpha-thing"]) for i in range(3)]
        self.cases += [case("b%d" % i, ["beta-thing"]) for i in range(3)]
        self.cases += [case("neg1", [])]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self, baseline=None, floor=3, reports=()):
        catalog = trigger_eval.load_catalog([self.skills])
        return case_coverage.check(catalog, self.cases, list(reports),
                                   baseline or {}, floor)

    def codes(self, findings):
        return sorted(c for _, c, _, _ in findings)


class TestP001(Fixture):
    def test_full_coverage_raises_no_P001(self):
        findings, _ = self.run_check()
        self.assertNotIn("P001", self.codes(findings))

    def test_a_skill_with_no_cases_is_an_error(self):
        skill(os.path.join(self.skills, "gamma-thing"), "gamma-thing")
        findings, _ = self.run_check()
        p001 = [f for f in findings if f[1] == "P001"]
        self.assertEqual([f[2] for f in p001], ["gamma-thing"])
        self.assertEqual(p001[0][0], "error")

    def test_two_cases_is_still_under_the_floor(self):
        self.cases = [c for c in self.cases if c["id"] != "a2"]
        findings, _ = self.run_check()
        self.assertIn("alpha-thing", [f[2] for f in findings if f[1] == "P001"])

    def test_the_floor_is_a_parameter_not_a_constant(self):
        self.cases = [c for c in self.cases if c["id"] != "a2"]
        findings, _ = self.run_check(floor=2)
        self.assertNotIn("P001", self.codes(findings))

    def test_a_negative_case_does_not_count_toward_any_skills_floor(self):
        # The 17 shared negatives must never make a skill look covered.
        self.cases = [c for c in self.cases if not c["id"].startswith("a")]
        self.cases += [case("neg%d" % i, []) for i in range(2, 12)]
        findings, _ = self.run_check()
        self.assertIn("alpha-thing", [f[2] for f in findings if f[1] == "P001"])


class TestP002(Fixture):
    def test_a_case_for_a_deleted_skill_is_an_error(self):
        self.cases.append(case("ghost", ["delta-thing"]))
        findings, _ = self.run_check()
        p002 = [f for f in findings if f[1] == "P002"]
        self.assertEqual([f[2] for f in p002], ["ghost"])
        self.assertEqual(p002[0][0], "error")

    def test_a_case_expecting_two_skills_checks_both(self):
        self.cases.append(case("pair", ["alpha-thing", "delta-thing"]))
        findings, _ = self.run_check()
        self.assertEqual(len([f for f in findings if f[1] == "P002"]), 1)


class TestP003(Fixture):
    def test_a_prompt_naming_its_own_skill_is_a_warning(self):
        self.cases.append(case("leak", ["alpha-thing"],
                               "Run the alpha-thing procedure on this repo."))
        findings, _ = self.run_check()
        p003 = [f for f in findings if f[1] == "P003"]
        self.assertEqual([f[2] for f in p003], ["leak"])
        self.assertEqual(p003[0][0], "warning")

    def test_spaced_and_underscored_spellings_leak_too(self):
        for i, text in enumerate(("Do the alpha thing here.",
                                  "Do the Alpha_Thing here.")):
            self.cases.append(case("leak%d" % i, ["alpha-thing"], text))
        findings, _ = self.run_check()
        self.assertEqual(len([f for f in findings if f[1] == "P003"]), 2)

    def test_one_shared_token_is_not_a_leak(self):
        # "thing" is in both skill names and is ordinary domain vocabulary;
        # flagging it would bury the real leaks.
        self.cases.append(case("shared", ["alpha-thing"],
                               "The thing keeps failing, what do I do?"))
        findings, _ = self.run_check()
        self.assertNotIn("P003", self.codes(findings))

    def test_a_leak_of_a_DIFFERENT_skills_name_is_not_flagged_here(self):
        # Naming a sibling is how a displacement case is written on purpose.
        self.cases.append(case("sib", ["alpha-thing"],
                               "Is this a beta-thing problem or something else?"))
        findings, _ = self.run_check()
        self.assertNotIn("P003", self.codes(findings))


def report(names, digests, path):
    data = {"mode": "native", "protocol": "strict", "descriptions": digests,
            "results": [{"case": "x", "expect": [n], "fired": [n]}
                        for n in names]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


class TestP004P005(Fixture):
    def setUp(self):
        super().setUp()
        self.reports_dir = os.path.join(self.tmp, "reports")
        os.makedirs(self.reports_dir)
        self.digest = case_coverage.trigger_eval.description_digest(DESC)

    def load_reports(self):
        return trigger_eval.load_reports(self.reports_dir)

    def test_unprobed_and_unacknowledged_is_a_warning(self):
        findings, _ = self.run_check()
        p004 = sorted(f[2] for f in findings if f[1] == "P004")
        self.assertEqual(p004, ["alpha-thing", "beta-thing"])
        self.assertTrue(all(f[0] == "warning"
                            for f in findings if f[1] == "P004"))

    def test_an_acknowledged_skill_is_silent(self):
        base = {"skills": {"alpha-thing": {"owner": "skills(B)"},
                           "beta-thing": {"owner": "skills(B)"}}}
        findings, _ = self.run_check(baseline=base)
        self.assertEqual([f for f in findings if f[1] == "P004"], [])

    def test_an_acknowledgement_without_an_owner_is_an_error(self):
        base = {"skills": {"alpha-thing": {}}}
        findings, _ = self.run_check(baseline=base)
        p005 = [f for f in findings if f[1] == "P005"]
        self.assertEqual([(f[0], f[2]) for f in p005], [("error", "alpha-thing")])

    def test_probing_a_skill_clears_its_P004(self):
        report(["alpha-thing"], {"alpha-thing": self.digest},
               os.path.join(self.reports_dir, "r357.json"))
        findings, _ = self.run_check(reports=self.load_reports())
        self.assertEqual([f[2] for f in findings if f[1] == "P004"],
                         ["beta-thing"])

    def test_a_baseline_entry_that_is_now_probed_is_an_error(self):
        # The mute-button case: the debt is paid and the acknowledgement
        # would otherwise silence the NEXT regression of the same skill.
        report(["alpha-thing"], {"alpha-thing": self.digest},
               os.path.join(self.reports_dir, "r357.json"))
        base = {"skills": {"alpha-thing": {"owner": "skills(B)"}}}
        findings, _ = self.run_check(baseline=base,
                                     reports=self.load_reports())
        p005 = [f for f in findings if f[1] == "P005"]
        self.assertEqual([(f[0], f[2]) for f in p005], [("error", "alpha-thing")])

    def test_a_baseline_entry_for_a_deleted_skill_is_an_error(self):
        base = {"skills": {"delta-thing": {"owner": "skills(B)"}}}
        findings, _ = self.run_check(baseline=base)
        self.assertIn(("error", "delta-thing"),
                      [(f[0], f[2]) for f in findings if f[1] == "P005"])

    def test_editing_a_description_after_a_probe_reopens_the_warning(self):
        report(["alpha-thing"], {"alpha-thing": "0" * 12},
               os.path.join(self.reports_dir, "r357.json"))
        findings, _ = self.run_check(reports=self.load_reports())
        stale = [f for f in findings
                 if f[1] == "P004" and f[2] == "alpha-thing"]
        self.assertEqual(len(stale), 1)
        self.assertIn("STALE", stale[0][3])


class TestLiveCorpus(unittest.TestCase):
    """The enforcement itself. If this ever fails, a skill entered the
    corpus without cases, or a case outlived its skill."""

    def test_live_corpus_has_no_coverage_errors(self):
        rc = case_coverage.main(["--repo-root", ROOT])
        self.assertEqual(rc, 0, "case_coverage found errors in the live "
                                "corpus; run it for the detail")

    def test_the_live_corpus_is_actually_being_read(self):
        # Guards the test above against passing on an empty corpus.
        cases = trigger_eval.load_cases(
            os.path.join(ROOT, "skills", "trigger-cases.json"))
        catalog = trigger_eval.load_catalog([os.path.join(ROOT, "skills")])
        self.assertGreaterEqual(len(catalog), 27)
        self.assertGreaterEqual(len(cases), 105)

    def test_every_skill_directory_reaches_the_catalog(self):
        # load_catalog is the corpus definition P001 is measured against; a
        # skill it silently skipped would be invisible to the floor.
        catalog = {n for n, _, _ in
                   trigger_eval.load_catalog([os.path.join(ROOT, "skills")])}
        skills_dir = os.path.join(ROOT, "skills")
        on_disk = {d for d in os.listdir(skills_dir)
                   if os.path.exists(os.path.join(skills_dir, d, "SKILL.md"))}
        self.assertEqual(on_disk - catalog, set())


if __name__ == "__main__":
    unittest.main()

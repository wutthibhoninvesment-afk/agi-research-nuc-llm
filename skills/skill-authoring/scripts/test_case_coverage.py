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

    def run_check(self, baseline=None, floor=3, reports=(), weak=None):
        catalog = trigger_eval.load_catalog([self.skills])
        return case_coverage.check(catalog, self.cases, list(reports),
                                   baseline or {}, floor,
                                   weak_baseline=weak or {})

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


def report(names, digests, path, results=None):
    """A probe report. `names` is the shorthand — one FIRING probe of each
    named skill on each of its three fixture cases; `results` overrides it
    with explicit rows.

    The result key is `id`, not `case`: that is what `trigger_eval` writes
    (see its `res = {"id": case["id"], ...}`) and what round 375's
    `covered`/`recalled` read. The original of this helper wrote `case`,
    which no reader ever looked at, so the fixture disagreed with the schema
    it stood in for and nothing could notice."""
    if results is None:
        results = [{"id": "%s%d" % (n[0], i), "expect": [n], "fired": [n]}
                   for n in names for i in range(3)]
    data = {"mode": "native", "protocol": "strict", "descriptions": digests,
            "results": results}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def probe(cid, name, fired=True):
    return {"id": cid, "expect": [name], "fired": [name] if fired else []}


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


class TestP006P007P008(Fixture):
    """Round 375 — what the probe SAW, not merely that it ran.

    `alpha-thing` and `beta-thing` each have three positive cases a0-a2 /
    b0-b2 in the Fixture corpus."""

    def setUp(self):
        super().setUp()
        self.reports_dir = os.path.join(self.tmp, "reports")
        os.makedirs(self.reports_dir)
        self.digests = {n: case_coverage.trigger_eval.description_digest(DESC)
                        for n in ("alpha-thing", "beta-thing")}

    def write(self, results, name="r.json"):
        report(None, self.digests, os.path.join(self.reports_dir, name),
               results=results)
        return trigger_eval.load_reports(self.reports_dir)

    def find(self, findings, code, subject=None):
        return [f for f in findings if f[1] == code
                and (subject is None or f[2] == subject)]

    def test_a_full_firing_sweep_raises_nothing(self):
        reports = self.write([probe("a%d" % i, "alpha-thing")
                              for i in range(3)])
        findings, _ = self.run_check(reports=reports)
        self.assertEqual(self.find(findings, "P006"), [])
        self.assertEqual(self.find(findings, "P007"), [])

    def test_a_probe_of_a_SUBSET_of_the_cases_is_P006(self):
        # The fuzz-mutate-kill-loop shape: `probed` asserted off one case.
        reports = self.write([probe("a0", "alpha-thing")])
        findings, _ = self.run_check(reports=reports)
        p006 = self.find(findings, "P006", "alpha-thing")
        self.assertEqual([f[0] for f in p006], ["warning"])
        self.assertIn("1 of its 3 positive case(s)", p006[0][3])

    def test_a_probe_that_did_not_FIRE_is_P007(self):
        # The measured-budget-sizing shape: probed, fresh, and 0/3.
        reports = self.write([probe("a%d" % i, "alpha-thing", fired=False)
                              for i in range(3)])
        findings, _ = self.run_check(reports=reports)
        p007 = self.find(findings, "P007", "alpha-thing")
        self.assertEqual([f[0] for f in p007], ["warning"])
        self.assertIn("fired it on 0 of the 3 case(s)", p007[0][3])

    def test_the_two_codes_are_independent(self):
        reports = self.write([probe("a0", "alpha-thing", fired=False)])
        findings, _ = self.run_check(reports=reports)
        self.assertEqual(len(self.find(findings, "P006", "alpha-thing")), 1)
        self.assertEqual(len(self.find(findings, "P007", "alpha-thing")), 1)

    def test_repeats_of_ONE_case_do_not_pass_for_coverage(self):
        # measured-exemption reads `probes=4` against `positives=3` while
        # covering ONE distinct case, repeated four times. Counting results
        # instead of distinct ids is what hid it.
        reports = self.write([probe("a0", "alpha-thing") for _ in range(4)])
        findings, rows = self.run_check(reports=reports)
        row = {r["name"]: r for r in rows}["alpha-thing"]
        self.assertEqual((row["probes"], row["covered"]), (4, 1))
        self.assertEqual(len(self.find(findings, "P006", "alpha-thing")), 1)

    def test_a_case_that_fired_on_only_SOME_repeats_is_flaky_and_not_recalled(self):
        reports = self.write([probe("a0", "alpha-thing"),
                              probe("a0", "alpha-thing", fired=False),
                              probe("a1", "alpha-thing"),
                              probe("a2", "alpha-thing")])
        findings, rows = self.run_check(reports=reports)
        row = {r["name"]: r for r in rows}["alpha-thing"]
        self.assertEqual((row["covered"], row["recalled"], row["flaky"]),
                         (3, 2, 1))
        self.assertIn("(1 flaky)",
                      self.find(findings, "P007", "alpha-thing")[0][3])

    def test_an_unprobed_skill_gets_P004_only(self):
        # Three warnings for one skill is how a warning list stops being
        # read; `never`/`STALE` is P004's question, not P006/P007's.
        findings, _ = self.run_check()
        self.assertEqual(self.find(findings, "P006", "alpha-thing"), [])
        self.assertEqual(self.find(findings, "P007", "alpha-thing"), [])
        self.assertEqual(len(self.find(findings, "P004", "alpha-thing")), 1)

    def test_an_acknowledged_weak_probe_is_silent(self):
        reports = self.write([probe("a0", "alpha-thing", fired=False)])
        weak = {"skills": {"alpha-thing": {"owner": "skills(B)",
                                           "report": "r.json"}}}
        findings, _ = self.run_check(reports=reports, weak=weak)
        self.assertEqual(self.find(findings, "P006"), [])
        self.assertEqual(self.find(findings, "P007"), [])
        self.assertEqual(self.find(findings, "P008"), [])

    def test_an_acknowledgement_whose_debt_is_paid_is_P008(self):
        reports = self.write([probe("a%d" % i, "alpha-thing")
                              for i in range(3)])
        weak = {"skills": {"alpha-thing": {"owner": "skills(B)",
                                           "report": "r.json"}}}
        findings, _ = self.run_check(reports=reports, weak=weak)
        p008 = self.find(findings, "P008", "alpha-thing")
        self.assertEqual([f[0] for f in p008], ["error"])
        self.assertIn("mute button", p008[0][3])

    def test_a_newer_report_expires_the_content_pin(self):
        # Someone re-probed and did not re-adjudicate. The entry may now be
        # describing a measurement nobody has looked at.
        self.write([probe("a0", "alpha-thing", fired=False)], "r-old.json")
        reports = self.write([probe("a0", "alpha-thing", fired=False),
                              probe("a1", "alpha-thing", fired=False)],
                             "r-new.json")
        weak = {"skills": {"alpha-thing": {"owner": "skills(B)",
                                           "report": "r-old.json"}}}
        findings, _ = self.run_check(reports=reports, weak=weak)
        p008 = self.find(findings, "P008", "alpha-thing")
        self.assertEqual([f[0] for f in p008], ["error"])
        self.assertIn("did not re-adjudicate", p008[0][3])

    def test_an_unowned_acknowledgement_is_P008(self):
        reports = self.write([probe("a0", "alpha-thing", fired=False)])
        weak = {"skills": {"alpha-thing": {"report": "r.json"}}}
        findings, _ = self.run_check(reports=reports, weak=weak)
        self.assertIn("no `owner`",
                      self.find(findings, "P008", "alpha-thing")[0][3])

    def test_an_acknowledgement_for_a_deleted_skill_is_P008(self):
        weak = {"skills": {"delta-thing": {"owner": "skills(B)"}}}
        findings, _ = self.run_check(weak=weak)
        self.assertIn("not in the corpus",
                      self.find(findings, "P008", "delta-thing")[0][3])


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

    def test_the_outcome_fields_are_bounded_by_the_case_set(self):
        # Round 375. An invariant, not a pinned count: pinning "N skills
        # have a weak probe" against a corpus whose reports only grow is
        # round 340's fake-regression trap, and paying the debt is exactly
        # what should NOT turn this red.
        cases = trigger_eval.load_cases(
            os.path.join(ROOT, "skills", "trigger-cases.json"))
        catalog = trigger_eval.load_catalog([os.path.join(ROOT, "skills")])
        reports = trigger_eval.load_reports(
            os.path.join(ROOT, "state", "trigger-eval"))
        for r in trigger_eval.audit_skills(catalog, cases, reports):
            self.assertLessEqual(0, r["recalled"], r["name"])
            self.assertLessEqual(r["recalled"], r["covered"], r["name"])
            self.assertLessEqual(r["covered"], r["positives"], r["name"])
            self.assertLessEqual(r["flaky"], r["covered"], r["name"])
            if r["status"] == "never":
                self.assertEqual(r["covered"], 0, r["name"])

    def test_the_weak_probe_baseline_is_well_formed(self):
        # P008 catches rot in the CONTENT; this catches rot in the SCHEMA,
        # which P008 can only partly see (a missing `report` disables the
        # content pin silently).
        path = os.path.join(ROOT, "state", "known-weak-probes.json")
        with open(path, encoding="utf-8") as f:
            weak = json.load(f)
        catalog = {n for n, _, _ in
                   trigger_eval.load_catalog([os.path.join(ROOT, "skills")])}
        reports_dir = os.path.join(ROOT, "state", "trigger-eval")
        for name, entry in weak.get("skills", {}).items():
            self.assertIn(name, catalog, name)
            for field in ("owner", "why", "report"):
                self.assertTrue(entry.get(field), "%s: %s" % (name, field))
            self.assertTrue(
                os.path.exists(os.path.join(reports_dir, entry["report"])),
                "%s pins a report that is not on disk: %s"
                % (name, entry["report"]))

    def test_every_skill_directory_reaches_the_catalog(self):
        # load_catalog is the corpus definition P001 is measured against; a
        # skill it silently skipped would be invisible to the floor.
        catalog = {n for n, _, _ in
                   trigger_eval.load_catalog([os.path.join(ROOT, "skills")])}
        skills_dir = os.path.join(ROOT, "skills")
        on_disk = {d for d in os.listdir(skills_dir)
                   if os.path.exists(os.path.join(skills_dir, d, "SKILL.md"))}
        self.assertEqual(on_disk - catalog, set())


class TestP009Replication(Fixture):
    """Round 381 — a durable verdict that rests on ONE draw.

    Written RED first against the code as it stood before this round —
    and the RED run is itself a worked instance of what this round found.
    17 of the 19 new tests failed (AttributeError: `replication_rows` and
    `check_replication` did not exist). TWO PASSED: the two that assert
    P009 does NOT fire. Of course they did — with no P009 in the codebase
    nothing fires, so an assertion that nothing fires is satisfied by the
    absence of the feature it is testing. That is round 380's rule ("a
    proxy is admissible only once something has compared it against the
    thing it stands for") landing on this file within an hour of being
    committed. Both now carry a POSITIVE CONTROL in the same test: they
    assert the check is live on a sibling input before asserting it is
    silent on theirs, so neither can pass again without P009 existing.
    """

    def setUp(self):
        super().setUp()
        self.reports_dir = os.path.join(self.tmp, "reports")
        os.makedirs(self.reports_dir)
        self.digest = trigger_eval.description_digest(DESC)
        self.digests = {"alpha-thing": self.digest,
                        "beta-thing": self.digest}
        self.weak = {"skills": {"alpha-thing": {
            "owner": "skills(B)", "why": "0 of 3.", "report": "r1.json"}}}

    def write(self, base, results):
        report(None, self.digests, os.path.join(self.reports_dir, base),
               results=results)

    def load(self):
        return trigger_eval.load_reports(self.reports_dir)

    def repl(self):
        catalog = trigger_eval.load_catalog([self.skills])
        return trigger_eval.replication_rows(catalog, self.cases, self.load())

    def row(self, name="alpha-thing"):
        return {r["name"]: r for r in self.repl()}[name]

    # ---------------------------------------------------------- the rows --
    def test_one_report_is_unreplicated(self):
        self.write("r1.json", [probe("a0", "alpha-thing")])
        self.assertEqual(self.row()["n_reports"], 1)
        self.assertEqual(self.row()["compared"], [])

    def test_two_reports_agreeing_compare_and_do_not_disagree(self):
        self.write("r1.json", [probe("a0", "alpha-thing")])
        self.write("r2.json", [probe("a0", "alpha-thing")])
        r = self.row()
        self.assertEqual(r["n_reports"], 2)
        self.assertEqual(r["compared"], ["a0"])
        self.assertEqual(r["disagree"], [])

    def test_two_reports_disagreeing_are_named(self):
        self.write("r1.json", [probe("a0", "alpha-thing", fired=False)])
        self.write("r2.json", [probe("a0", "alpha-thing")])
        self.assertEqual(self.row()["disagree"], ["a0"])
        self.assertEqual(set(self.row()["verdicts"]["a0"].values()),
                         {True, False})

    def test_a_case_only_one_report_touched_is_not_compared(self):
        # The 0/12-vs-12/12 shape only counts where BOTH runs ran the case.
        self.write("r1.json", [probe("a0", "alpha-thing")])
        self.write("r2.json", [probe("a1", "alpha-thing")])
        r = self.row()
        self.assertEqual(r["n_reports"], 2)
        self.assertEqual(r["compared"], [])

    def test_repeats_inside_one_report_collapse_to_one_verdict(self):
        # 2 of 3 repeats firing is NOT a fire for this purpose: the verdict
        # a baseline entry records is "did every repeat fire".
        self.write("r1.json", [probe("a0", "alpha-thing"),
                               probe("a0", "alpha-thing", fired=False)])
        self.write("r2.json", [probe("a0", "alpha-thing")])
        self.assertEqual(self.row()["disagree"], ["a0"])

    def test_a_report_under_a_DIFFERENT_description_is_excluded(self):
        # Comparing draws across a description edit is the one thing this
        # must not do -- that is P004's STALE question, not P009's.
        self.write("r1.json", [probe("a0", "alpha-thing", fired=False)])
        report(None, {"alpha-thing": "deadbeefdead"},
               os.path.join(self.reports_dir, "r2.json"),
               results=[probe("a0", "alpha-thing")])
        r = self.row()
        self.assertEqual(r["n_reports"], 1)
        self.assertEqual(r["disagree"], [])

    def test_a_report_with_no_descriptions_map_is_excluded(self):
        self.write("r1.json", [probe("a0", "alpha-thing")])
        with open(os.path.join(self.reports_dir, "r2.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"mode": "native", "results":
                       [probe("a0", "alpha-thing", fired=False)]}, f)
        self.assertEqual(self.row()["n_reports"], 1)

    def test_an_errored_probe_does_not_vote(self):
        self.write("r1.json", [dict(probe("a0", "alpha-thing", fired=False),
                                    error="timeout")])
        self.write("r2.json", [probe("a0", "alpha-thing")])
        self.assertEqual(self.row()["n_reports"], 1)

    def test_a_negative_case_is_not_a_positive_of_any_skill(self):
        self.write("r1.json", [{"id": "neg1", "expect": [], "fired": []}])
        self.write("r2.json", [{"id": "neg1", "expect": [], "fired": []}])
        self.assertEqual(self.row()["n_reports"], 0)

    # ------------------------------------------------------- the finding --
    def test_P009_fires_on_an_unreplicated_adjudication(self):
        self.write("r1.json", [probe("a0", "alpha-thing", fired=False)])
        findings, _ = self.run_check(reports=self.load(), weak=self.weak)
        p009 = [f for f in findings if f[1] == "P009"]
        self.assertEqual([f[2] for f in p009], ["alpha-thing"])
        self.assertEqual(p009[0][0], "warning")
        self.assertIn("UNREPLICATED", p009[0][3])

    def test_P009_fires_when_two_reports_disagree(self):
        self.write("r1.json", [probe("a0", "alpha-thing", fired=False)])
        self.write("r2.json", [probe("a0", "alpha-thing")])
        findings, _ = self.run_check(reports=self.load(), weak=self.weak)
        p009 = [f for f in findings if f[1] == "P009"]
        self.assertEqual(len(p009), 1)
        self.assertIn("DISAGREE", p009[0][3])
        self.assertIn("a0", p009[0][3])

    def test_P009_is_silent_when_two_reports_agree(self):
        self.write("r1.json", [probe("a0", "alpha-thing", fired=False)])
        self.write("r2.json", [probe("a0", "alpha-thing", fired=False)])
        findings, _ = self.run_check(reports=self.load(), weak=self.weak)
        self.assertNotIn("P009", self.codes(findings))
        # POSITIVE CONTROL. Without it this passes against a codebase that
        # has no P009 at all -- which is exactly what it did on the RED run.
        self.write("r2.json", [probe("a0", "alpha-thing")])
        live, _ = self.run_check(reports=self.load(), weak=self.weak)
        self.assertIn("P009", self.codes(live))

    def test_P009_says_NOTHING_about_a_skill_with_no_adjudication(self):
        # The anti-cry-wolf rule: 26 of 41 live skills are unreplicated and
        # only the ones carrying a verdict are a problem.
        self.write("r1.json", [probe("b0", "beta-thing")])
        findings, _ = self.run_check(reports=self.load(), weak=self.weak)
        self.assertNotIn("beta-thing",
                         [f[2] for f in findings if f[1] == "P009"])
        # POSITIVE CONTROL: alpha-thing IS adjudicated and unreplicated, so
        # P009 must be firing for it in the very same run. Without this the
        # test passes when P009 does not exist.
        self.assertEqual([f[2] for f in findings if f[1] == "P009"],
                         ["alpha-thing"])

    def test_P009_never_raises_an_error(self):
        self.write("r1.json", [probe("a0", "alpha-thing", fired=False)])
        findings, _ = self.run_check(reports=self.load(), weak=self.weak)
        self.assertEqual([f[0] for f in findings if f[1] == "P009"],
                         ["warning"])

    def test_the_summary_counts_add_up(self):
        self.write("r1.json", [probe("a0", "alpha-thing", fired=False),
                               probe("a1", "alpha-thing")])
        self.write("r2.json", [probe("a0", "alpha-thing"),
                               probe("a1", "alpha-thing")])
        n_rep, n_tot, n_dis, n_comp = case_coverage.replication_summary(
            self.repl())
        self.assertEqual((n_rep, n_tot, n_dis, n_comp), (1, 2, 1, 2))


class TestLiveReplication(unittest.TestCase):
    """The live-corpus half. These are the numbers round 381 published."""

    def setUp(self):
        self.catalog = trigger_eval.load_catalog(
            [os.path.join(ROOT, "skills")])
        self.cases = trigger_eval.load_cases(
            os.path.join(ROOT, "skills", "trigger-cases.json"))
        self.reports = trigger_eval.load_reports(
            os.path.join(ROOT, "state", "trigger-eval"))
        self.rows = trigger_eval.replication_rows(
            self.catalog, self.cases, self.reports)

    def test_the_corpus_has_cross_report_disagreement_at_all(self):
        # If this ever goes to zero the instrument became deterministic and
        # P009 should be re-argued, not deleted quietly.
        self.assertGreater(sum(len(r["disagree"]) for r in self.rows), 0)

    def test_lazy_fill_ceiling_disagrees_with_itself_on_every_case(self):
        # The round's own worked instance: 0/12 in round-381-batch.json and
        # 12/12, 4/4, 11/12 in three other runs of the SAME configuration.
        row = {r["name"]: r for r in self.rows}["lazy-fill-ceiling"]
        self.assertGreaterEqual(row["n_reports"], 4)
        self.assertEqual(sorted(row["disagree"]),
                         ["lfc-far", "lfc-far2", "lfc-mid", "lfc-near"])

    def test_every_disagreeing_case_was_actually_compared(self):
        for r in self.rows:
            self.assertLessEqual(set(r["disagree"]), set(r["compared"]),
                                 r["name"])
            self.assertLessEqual(len(r["compared"]), len(r["verdicts"]) + 1,
                                 r["name"])

    def test_no_weak_probe_entry_is_silently_unreplicated(self):
        # Not "P009 must be empty" -- a re-probe is a live spend. The rule
        # is that every entry P009 names is one an owner has been handed.
        with open(os.path.join(ROOT, "state", "known-weak-probes.json"),
                  encoding="utf-8") as f:
            weak = json.load(f)
        for _, code, subject, _ in case_coverage.check_replication(
                weak, self.rows):
            self.assertEqual(code, "P009")
            self.assertTrue(weak["skills"][subject].get("owner"), subject)


if __name__ == "__main__":
    unittest.main()

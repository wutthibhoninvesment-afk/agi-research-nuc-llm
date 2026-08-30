#!/usr/bin/env python3
"""Tests for corpus_check.py — the third per-round health check (round 363).

Offline; no model calls. `test_live_corpus_is_clean` is the enforcement, and
every other test here exists so that one cannot pass vacuously — the same
design `test_case_coverage.py` states for round 357's live assertion.

The wording tests matter more than they look. The whole reason this file
formats its own driver.log line instead of borrowing
`driver_health.health_line` is that the borrowed one is pytest-shaped and
would print false prose in two of its four branches. A round that later
"simplifies" this back onto the shared classifier has to delete these.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import corpus_check

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = corpus_check.DEFAULT_REPO


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class TestDriverLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = os.path.join(self.tmp, "skills_health_round_999.log")
        write(self.log, "skill_lint         ok    fine\n"
                        "corpus-check: 6 checker(s), 0 error(s), 1 warning(s)\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pass_carries_the_summary_line(self):
        line = corpus_check.driver_line("round 9: skills-check", self.log, 0)
        self.assertTrue(line.startswith("round 9: skills-check PASS ("), line)
        # the WARNING count rides in the PASS line — that is the entire reason
        # warnings do not set the exit code
        self.assertIn("1 warning(s)", line)

    def test_errors_read_as_a_rule_violation_not_as_a_broken_runner(self):
        line = corpus_check.driver_line("round 9: skills-check", self.log, 1)
        self.assertIn("FAIL", line)
        self.assertIn("violates its own rules", line)
        self.assertNotIn("pytest", line)

    def test_a_checker_that_could_not_run_is_error_not_fail(self):
        line = corpus_check.driver_line("round 9: skills-check", self.log, 2)
        self.assertIn("ERROR", line)
        self.assertNotIn("FAIL", line)
        self.assertIn("could not run", line)

    def test_an_off_table_exit_code_is_never_silently_a_pass(self):
        for rc in (-9, 3, 137):
            line = corpus_check.driver_line("l", self.log, rc)
            self.assertIn("ERROR", line, rc)
            self.assertNotIn("PASS", line, rc)

    def test_an_unreadable_log_is_unknown_not_pass(self):
        line = corpus_check.driver_line("l", os.path.join(self.tmp, "nope"), 0)
        self.assertIn("UNKNOWN", line)
        self.assertNotIn("PASS", line)

    def test_line_mode_from_the_command_line(self):
        rc = corpus_check.main(["--line", "round 9: skills-check", self.log,
                                "0"])
        self.assertEqual(rc, 0)

    def test_line_mode_rejects_wrong_arity(self):
        self.assertEqual(corpus_check.main(["--line", "only-a-label"]), 2)


class TestSeverity(unittest.TestCase):
    """The ERROR/WARNING split is the contract; these pin both sides of it."""

    def test_skill_lint_and_case_coverage_shapes_are_both_parsed(self):
        errors, warnings = set(), set()
        out = ("/x/SKILL.md: ERROR H001 no trigger section\n"
               "/x/SKILL.md: WARN B002 body is long\n"
               "error: P001 foo: 0 positive case(s)\n"
               "warning: P004 bar: never probed\n"
               "state/research-state.md:10: CARRIED S005 asserted verbatim\n"
               "skills/y/SKILL.md:3: STALE C001 path resolves nowhere\n")
        for line in out.splitlines():
            m = corpus_check.FINDING_RE.search(line)
            self.assertIsNotNone(m, line)
            sev, code = m.group(1).lower(), m.group(2)
            (errors if sev in corpus_check.ERROR_SEVERITIES
             else warnings).add(code)
        self.assertEqual(errors, {"H001", "P001", "C001"})
        self.assertEqual(warnings, {"B002", "P004", "S005"})


class TestRunOne(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _script(self, body):
        p = os.path.join(self.tmp, "fake.py")
        write(p, body)
        return p

    def test_absent_script_is_absent_never_green(self):
        r = corpus_check.run_one("x", [os.path.join(self.tmp, "gone.py")],
                                 self.tmp)
        self.assertEqual(r["status"], "absent")

    def test_nonzero_with_no_parseable_code_still_fails(self):
        # round 349's FAIL-vs-ERROR rule at this layer: an unparsed line must
        # never read as green just because no regex matched it
        p = self._script("import sys\nprint('something went wrong')\n"
                         "sys.exit(1)\n")
        r = corpus_check.run_one("x", [p], self.tmp)
        self.assertEqual(r["errors"], ["rc1"])

    def test_exit_two_is_recorded_as_error_and_forces_could_not_run(self):
        p = self._script("import sys\nprint('usage: ...')\nsys.exit(2)\n")
        r = corpus_check.run_one("x", [p], self.tmp)
        self.assertEqual(r["status"], "error")

    def test_a_warning_only_run_is_not_an_error(self):
        p = self._script("print('/a/SKILL.md: WARN B002 long')\n")
        r = corpus_check.run_one("x", [p], self.tmp)
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["warnings"], ["B002"])


class TestLiveCorpus(unittest.TestCase):
    """The enforcement. This is what round 361's H001+P001 would have hit.

    These always run WITH the re-entry guard set, whether or not the caller
    set it. Not just for termination — without it each of these tests spawns
    the whole ~40s `skills/` suite, so the suite's own runtime would grow by
    a multiple of itself every time a live-corpus test is added. The guard is
    asserted separately by `test_the_reentry_guard_drops_the_unit_test_check`,
    so pinning it here costs no coverage.
    """

    def setUp(self):
        self._prior = os.environ.get(corpus_check.REENTRY_ENV)
        os.environ[corpus_check.REENTRY_ENV] = "1"

    def tearDown(self):
        if self._prior is None:
            os.environ.pop(corpus_check.REENTRY_ENV, None)
        else:
            os.environ[corpus_check.REENTRY_ENV] = self._prior

    def test_live_corpus_is_clean(self):
        out = os.path.join(tempfile.mkdtemp(), "r.json")
        rc = corpus_check.main(["--repo-root", ROOT, "--json", out])
        report = json.load(open(out, encoding="utf-8"))
        errs = {r["check"]: r["errors"] for r in report["results"]
                if r["errors"]}
        self.assertEqual(rc, corpus_check.PASS,
                         "skills corpus has ERRORs: %s" % errs)

    def test_the_reentry_guard_drops_the_unit_test_check(self):
        """These tests RUN under `main()`'s own unit_tests check. Without the
        guard that is an infinite regress, and round 363 built it before it
        caught it. The guard is asserted here rather than trusted because a
        future round adding a sixth check has to know the constraint exists."""
        import corpus_check as cc
        os.environ.pop(cc.REENTRY_ENV, None)
        try:
            outer = [n for n, _ in cc.checks(ROOT)]
            os.environ[cc.REENTRY_ENV] = "1"
            inner = [n for n, _ in cc.checks(ROOT)]
        finally:
            os.environ.pop(cc.REENTRY_ENV, None)
        self.assertIn("unit_tests", outer)
        self.assertNotIn("unit_tests", inner)
        self.assertEqual(len(inner), len(outer) - 1)

    def test_every_checker_actually_ran(self):
        """Guards the assertion above against passing because the checkers
        silently went missing — the failure mode a health check has to not
        have."""
        out = os.path.join(tempfile.mkdtemp(), "r.json")
        corpus_check.main(["--repo-root", ROOT, "--json", out])
        report = json.load(open(out, encoding="utf-8"))
        # DERIVED, not a literal. This assertion was `== 5` and round 369
        # added a sixth checker, which turned a real health check red for a
        # number rather than for a defect — round 321 item 14 / round 333
        # item 4's "a line asserting a number that no round re-executes",
        # inside the corpus's own test suite. `checks()` reads the re-entry
        # guard itself, so this is right in both environments: one fewer
        # under the guard (these tests run inside `unit_tests`), all of them
        # when the driver invokes it from a clean environment.
        self.assertEqual(len(report["results"]),
                         len(corpus_check.checks(ROOT)))
        self.assertNotIn("unit_tests",
                         [r["check"] for r in report["results"]])
        for r in report["results"]:
            self.assertEqual(r["status"], "ran", r)
            self.assertTrue(r["summary"], r)

    def test_the_wrapper_script_exists_and_is_what_the_driver_calls(self):
        wrapper = os.path.join(ROOT, "skills", "run_checks_fast.sh")
        self.assertTrue(os.path.exists(wrapper))
        driver = open(os.path.join(ROOT, "run_driver.sh"),
                      encoding="utf-8").read()
        self.assertIn("skills/run_checks_fast.sh", driver)
        self.assertIn("corpus_check.py\" --line", driver)


if __name__ == "__main__":
    unittest.main()

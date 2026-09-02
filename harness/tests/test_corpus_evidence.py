"""Round 463 (harness A) — the evidence a red corpus row destroys.

Round 461's next-step 1: "`unit_tests` is 25 of the 60 red checker-rows and
its failures are unrecoverable. `corpus_check.run_one` unlinks its
`tempfile.mkstemp` sink in a `finally`, so no round can say WHICH test failed
inside any red `unit_tests` row, ever. ... skills(B) owns the file;
harness(A) owns the log-retention convention."

This file is the harness(A) half. The subject lives in `skills/`, so the
assertions here are about the RETENTION CONTRACT -- what is kept, when
nothing is kept, what the kept file must still contain after a cap, and that
the line announcing it cannot be misread by the module in `harness/` that
counts checker rows.

The second half of the round is not retention at all. `unit_tests` runs
pytest over tests that INVOKE the other nine checkers, and pytest dumps the
captured stdout of the checker it drove into its traceback -- so
`_findings_in` and `coverage_of`, written to read a CHECKER's own output,
were reading another checker's output through a test runner's failure report.
`TestRunnerRowsPublishTheirOwnVerdict` pins the repair against round 398's
real log shape, which is the cleanest specimen in the 99 logs.
"""

import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "harness"))
sys.path.insert(0, os.path.join(ROOT, "skills", "skill-authoring", "scripts"))

import corpus_check                                          # noqa: E402
import redattrib                                             # noqa: E402


def _script(tmpdir, name, body):
    p = os.path.join(str(tmpdir), name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(body)
    return p


class TestRetentionPredicate(unittest.TestCase):
    """WHEN a run's output is kept, and when nothing is written at all."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="ev-pred.")
        self.ev = os.path.join(self.tmp, "evidence")

    def test_a_clean_run_keeps_nothing_and_creates_no_directory(self):
        p = _script(self.tmp, "ok.py", "print('coverage: 3/4 things')\n")
        r = corpus_check.run_one("c", [p], self.tmp, evidence_dir=self.ev)
        self.assertEqual(r["status"], "ran")
        self.assertEqual(r["rc"], 0)
        self.assertNotIn("evidence", r)
        self.assertFalse(os.path.exists(self.ev),
                         "a green corpus check must not grow logs/ at all")

    def test_a_warning_only_run_is_clean_and_keeps_nothing(self):
        p = _script(self.tmp, "w.py", "print('x.md: WARN B002 carried')\n")
        r = corpus_check.run_one("c", [p], self.tmp, evidence_dir=self.ev)
        self.assertEqual(r["warnings"], ["B002"])
        self.assertEqual(r["errors"], [])
        self.assertNotIn("evidence", r)

    def test_a_failing_run_keeps_its_whole_output(self):
        p = _script(self.tmp, "bad.py",
                    "import sys\nprint('line one')\n"
                    "print('x.md: ERROR H001 broken')\nsys.exit(1)\n")
        r = corpus_check.run_one("c", [p], self.tmp, evidence_dir=self.ev)
        self.assertEqual(r["errors"], ["H001"])
        self.assertTrue(os.path.isfile(r["evidence"]))
        with open(r["evidence"], encoding="utf-8") as fh:
            kept = fh.read()
        self.assertIn("line one", kept)
        self.assertIn("ERROR H001", kept)
        self.assertEqual(r["evidence_elided"], 0)
        self.assertEqual(r["evidence_lines"], 3)

    def test_an_off_table_exit_code_keeps_its_output_too(self):
        p = _script(self.tmp, "two.py", "import sys\nprint('boom')\nsys.exit(2)\n")
        r = corpus_check.run_one("c", [p], self.tmp, evidence_dir=self.ev)
        self.assertEqual(r["status"], "error")
        self.assertIn("evidence", r)

    def test_a_killed_run_keeps_what_it_said_before_the_kill(self):
        p = _script(self.tmp, "slow.py",
                    "import sys, time\n"
                    "print('said this first', flush=True)\n"
                    "time.sleep(30)\n")
        r = corpus_check.run_one("c", [p], self.tmp, timeout=2,
                                 evidence_dir=self.ev)
        self.assertEqual(r["status"], "timeout")
        with open(r["evidence"], encoding="utf-8") as fh:
            self.assertIn("said this first", fh.read())

    def test_an_absent_script_writes_nothing(self):
        r = corpus_check.run_one("c", [os.path.join(self.tmp, "gone.py")],
                                 self.tmp, evidence_dir=self.ev)
        self.assertEqual(r["status"], "absent")
        self.assertNotIn("evidence", r)
        self.assertFalse(os.path.exists(self.ev))

    def test_no_evidence_dir_reproduces_the_pre_463_behaviour_exactly(self):
        p = _script(self.tmp, "bad.py", "import sys\nsys.exit(1)\n")
        r = corpus_check.run_one("c", [p], self.tmp, evidence_dir=None)
        self.assertEqual(r["errors"], ["rc1"])
        self.assertNotIn("evidence", r)

    def test_the_temp_sink_is_still_unlinked_on_every_branch(self):
        """Retention writes a SECOND file; it must not leak the first."""
        import glob
        import tempfile
        before = set(glob.glob(os.path.join(tempfile.gettempdir(),
                                            "corpus_check.*")))
        p = _script(self.tmp, "bad.py", "import sys\nsys.exit(1)\n")
        corpus_check.run_one("c", [p], self.tmp, evidence_dir=self.ev)
        after = set(glob.glob(os.path.join(tempfile.gettempdir(),
                                           "corpus_check.*")))
        self.assertEqual(after - before, set())


class TestElision(unittest.TestCase):
    """A cap that keeps the wrong end is a cap that keeps nothing useful."""

    def test_output_under_the_cap_is_untouched(self):
        body, dropped = corpus_check.elide("hello\n", cap=100, head=20)
        self.assertEqual(body, "hello\n")
        self.assertEqual(dropped, 0)

    def test_the_head_and_the_tail_both_survive_a_cap(self):
        raw = "HEAD" + ("x" * 5000) + "TAIL"
        body, dropped = corpus_check.elide(raw, cap=1000, head=250)
        self.assertTrue(body.startswith("HEAD"))
        self.assertTrue(body.endswith("TAIL"))
        self.assertEqual(dropped, len(raw) - 1000)

    def test_the_marker_names_how_much_was_dropped(self):
        raw = "a" * 4000
        body, dropped = corpus_check.elide(raw, cap=1000, head=250)
        self.assertIn("%d character(s) elided" % dropped, body)
        self.assertIn("corpus_check.py", body)

    def test_a_capped_pytest_dump_still_yields_its_failing_node_ids(self):
        """The reason the TAIL is the bigger half.

        pytest's short summary -- the `FAILED <nodeid>` lines this whole
        round exists to recover -- is the last thing it prints. A cap that
        kept only the head would retain a file and still lose the answer.
        """
        noise = "\n".join("E   assert %d == %d" % (i, i + 1)
                          for i in range(20000))
        raw = ("collected 900 items\n" + noise
               + "\nFAILED skills/x/scripts/test_a.py::test_one - AssertionError"
                 "\nFAILED skills/x/scripts/test_b.py::test_two - ValueError"
                 "\n2 failed, 900 passed in 300.00s\n")
        body, dropped = corpus_check.elide(raw)
        self.assertGreater(dropped, 0)
        self.assertEqual(
            corpus_check.failed_nodes(body),
            ["skills/x/scripts/test_a.py::test_one",
             "skills/x/scripts/test_b.py::test_two"])
        self.assertIn("2 failed, 900 passed", body)


class TestFailedNodes(unittest.TestCase):

    def test_a_checkers_own_error_code_line_is_not_a_node_id(self):
        """`ERROR P001 ...` is a checker finding, not a pytest node."""
        self.assertEqual(corpus_check.failed_nodes(
            "error: P001 some-skill: no positive case\n"
            "ERROR H001 x.md: bad frontmatter\n"), [])

    def test_a_bare_file_level_error_is_a_node(self):
        self.assertEqual(
            corpus_check.failed_nodes("ERROR skills/x/scripts/test_a.py\n"),
            ["skills/x/scripts/test_a.py"])

    def test_duplicates_collapse_in_first_seen_order(self):
        self.assertEqual(corpus_check.failed_nodes(
            "FAILED b.py::t2\nFAILED a.py::t1\nFAILED b.py::t2\n"),
            ["b.py::t2", "a.py::t1"])


ROUND_398_SHAPE = r'''import sys
print("""
=================================== FAILURES ===================================
_______________________ test_the_corpus_has_no_p001 ____________________________
----------------------------- Captured stdout call -----------------------------
error: P001 some-skill: no positive trigger case
x.md:12: STALE S001 a claim that moved
x.md:14: STALE S002 another
x.md:16: STALE S006 and another
case-coverage: 51 skill(s), 214 case(s); coverage 47/51 skills, 22/51 replicated
=========================== short test summary info ============================
FAILED skills/skill-authoring/scripts/test_case_coverage.py::test_the_corpus_has_no_p001
FAILED skills/skill-authoring/scripts/test_state_claim_check.py::test_no_stale
5 failed, 703 passed in 138.90s (0:02:18)""")
sys.exit(1)
'''


class TestRunnerRowsPublishTheirOwnVerdict(unittest.TestCase):
    """Round 398's log, reproduced and then refuted.

    `logs/skills_health_round_398.log` reads:

        case_coverage      ERROR P001                ...
        state_claim_check  ERROR S001,S002,S006      ...
        unit_tests         ERROR P001,S001,S002,S006 5 failed, 703 passed ...
        corpus-check: 7 checker(s), 9 error(s), 10 warning(s)

    The third row is the union of the first two, re-read out of pytest's
    traceback, and `9 error(s)` counts those four codes a second time.
    """

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="ev-runner.")
        self.ev = os.path.join(self.tmp, "evidence")
        self.p = _script(self.tmp, "r398.py", ROUND_398_SHAPE)

    def test_the_borrowed_codes_are_what_a_plain_checker_row_would_show(self):
        """The defect, stated as a passing assertion about the old path."""
        r = corpus_check.run_one("some_checker", [self.p], self.tmp,
                                 evidence_dir=self.ev)
        self.assertEqual(r["errors"], ["P001", "S001", "S002", "S006"])
        self.assertEqual(r["coverage"], "47/51 skills, 22/51 replicated")

    def test_a_runner_row_publishes_rc1_and_not_another_checkers_codes(self):
        r = corpus_check.run_one("unit_tests", [self.p], self.tmp,
                                 evidence_dir=self.ev)
        self.assertEqual(r["errors"], ["rc1"])
        self.assertEqual(r["warnings"], [])

    def test_a_runner_row_publishes_no_coverage_clause_of_its_own(self):
        r = corpus_check.run_one("unit_tests", [self.p], self.tmp,
                                 evidence_dir=self.ev)
        self.assertEqual(r["coverage"], "")

    def test_what_the_row_used_to_say_is_kept_rather_than_deleted(self):
        r = corpus_check.run_one("unit_tests", [self.p], self.tmp,
                                 evidence_dir=self.ev)
        self.assertEqual(r["borrowed"]["errors"],
                         ["P001", "S001", "S002", "S006"])
        self.assertEqual(r["borrowed"]["coverage"],
                         "47/51 skills, 22/51 replicated")

    def test_the_row_now_names_the_tests_that_actually_failed(self):
        r = corpus_check.run_one("unit_tests", [self.p], self.tmp,
                                 evidence_dir=self.ev)
        self.assertEqual(r["failed_nodes"], [
            "skills/skill-authoring/scripts/test_case_coverage.py::test_the_corpus_has_no_p001",
            "skills/skill-authoring/scripts/test_state_claim_check.py::test_no_stale"])

    def test_the_aggregate_error_count_stops_double_counting(self):
        borrowed = corpus_check.run_one("some_checker", [self.p], self.tmp,
                                        evidence_dir=self.ev)
        own = corpus_check.run_one("unit_tests", [self.p], self.tmp,
                                   evidence_dir=self.ev)
        self.assertEqual(len(borrowed["errors"]), 4)
        self.assertEqual(len(own["errors"]), 1)

    def test_rc1_is_kept_as_the_token_so_both_downstream_readers_still_parse(self):
        """A richer token would have dropped the row from two readers.

        `corpus_history.LIVE_CODE_RE` accepts `[A-Z]\\d{3}|rc1` and nothing
        else; `redattrib.CORPUS_ROW` captures the codes token only when a
        single space follows the status word.
        """
        sys.path.insert(0, os.path.join(ROOT, "skills", "skill-authoring",
                                        "scripts"))
        import corpus_history
        row = "%-18s %-22s %s" % ("unit_tests", "ERROR rc1",
                                  "5 failed, 703 passed in 1.0s")
        self.assertEqual(redattrib.parse_corpus_row(row),
                         ("unit_tests", "ERROR", "rc1"))
        self.assertIn(("unit_tests", "rc1"),
                      corpus_history.LIVE_CODE_RE.findall(row))

    def test_a_green_runner_publishes_nothing_borrowed_either(self):
        p = _script(self.tmp, "green.py",
                    "print('case-coverage: coverage 47/51 skills')\n")
        r = corpus_check.run_one("unit_tests", [p], self.tmp,
                                 evidence_dir=self.ev)
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["coverage"], "")
        self.assertEqual(r["borrowed"]["coverage"], "47/51 skills")


class TestTheAnnouncementLine(unittest.TestCase):
    """The `evidence:` lines, and the reader in harness/ that must ignore them."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="ev-line.")

    def _results(self):
        ev = os.path.join(self.tmp, "evidence")
        p = _script(self.tmp, "r.py", ROUND_398_SHAPE)
        ok = _script(self.tmp, "ok.py", "print('fine')\n")
        return [corpus_check.run_one("skill_lint", [ok], self.tmp,
                                     evidence_dir=ev),
                corpus_check.run_one("unit_tests", [p], self.tmp,
                                     evidence_dir=ev)]

    def test_only_the_retained_checker_gets_a_line(self):
        lines = corpus_check.evidence_lines(self._results(), self.tmp)
        self.assertTrue(all("skill_lint" not in l for l in lines))
        self.assertTrue(any(l.startswith("evidence: unit_tests -> ")
                            for l in lines))

    def test_the_path_is_repo_relative(self):
        lines = corpus_check.evidence_lines(self._results(), self.tmp)
        path = [l for l in lines if " -> " in l][0].split(" -> ")[1].split(" ")[0]
        self.assertFalse(os.path.isabs(path))
        self.assertTrue(path.startswith("evidence/"))

    def test_the_failing_nodes_ride_on_the_line_itself(self):
        lines = corpus_check.evidence_lines(self._results(), self.tmp)
        joined = " ".join(lines)
        self.assertIn("test_case_coverage.py::test_the_corpus_has_no_p001",
                      joined)

    def test_no_evidence_line_can_be_read_as_a_checker_row(self):
        """P6. `redattrib` counts rows out of these logs; a new line shape
        that parsed as a row would rewrite 99 logs' history."""
        for line in corpus_check.evidence_lines(self._results(), self.tmp):
            self.assertIsNone(redattrib.parse_corpus_row(line), line)

    def test_a_permission_failure_says_so_instead_of_going_quiet(self):
        res = {"check": "c", "status": "ran", "rc": 1, "errors": ["rc1"],
               "evidence_error": "/nope/c.out: Permission denied"}
        line = corpus_check.evidence_lines([res], self.tmp)[0]
        self.assertIn("NOT retained", line)
        self.assertIsNone(redattrib.parse_corpus_row(line))

    def test_the_driver_fail_line_carries_the_retained_path(self):
        """P7 -- with no change to run_driver.sh.

        `driver_line`'s FAIL branch joins the log's last five non-blank
        lines, and the `evidence:` lines print above the `corpus-check:`
        summary.
        """
        log = os.path.join(self.tmp, "skills_health.log")
        with open(log, "w", encoding="utf-8") as fh:
            fh.write("unit_tests         ERROR rc1              5 failed\n")
            for line in corpus_check.evidence_lines(self._results(), self.tmp):
                fh.write(line + "\n")
            fh.write("corpus-check: 10 checker(s), 1 error(s), 0 warning(s)\n")
        line = corpus_check.driver_line("round 999: skills-check", log,
                                        corpus_check.ERRORS_FOUND)
        self.assertIn("skills-check FAIL", line)
        self.assertIn("evidence/unit_tests.out", line)


class TestRoundLabel(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="ev-round.")
        os.makedirs(os.path.join(self.tmp, "state"))

    def test_the_label_comes_from_the_counter_the_driver_already_writes(self):
        with open(os.path.join(self.tmp, "state", "round_counter"), "w") as fh:
            fh.write("463\n")
        self.assertEqual(corpus_check.round_label(self.tmp), "round-463")
        self.assertEqual(
            corpus_check.default_evidence_dir(self.tmp),
            os.path.join(self.tmp, "logs", "corpus-evidence", "round-463"))

    def test_a_missing_counter_is_unknown_and_never_a_crash(self):
        self.assertEqual(corpus_check.round_label(self.tmp), "round-unknown")

    def test_a_corrupt_counter_is_unknown_and_never_a_crash(self):
        with open(os.path.join(self.tmp, "state", "round_counter"), "w") as fh:
            fh.write("not a number\n")
        self.assertEqual(corpus_check.round_label(self.tmp), "round-unknown")


class TestEvidenceReader(unittest.TestCase):
    """`redattrib.py evidence` -- and the number it refuses to inflate."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="ev-read.")
        self.logs = os.path.join(self.tmp, "logs")
        os.makedirs(self.logs)

    def _log(self, rnd, rows):
        with open(os.path.join(self.logs, "skills_health_round_%d.log" % rnd),
                  "w", encoding="utf-8") as fh:
            for name, flag, summary in rows:
                fh.write("%-18s %-22s %s\n" % (name, flag, summary))

    def _evidence(self, rnd, checker, text):
        d = os.path.join(self.logs, "corpus-evidence", "round-%d" % rnd)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "%s.out" % checker), "w",
                  encoding="utf-8") as fh:
            fh.write(text)

    def test_a_warn_row_with_no_file_is_not_counted_as_a_missing_retention(self):
        """A `warn` run is usually CLEAN, so it never had evidence to keep."""
        self._log(1, [("skill_lint", "warn B002", "x"),
                      ("unit_tests", "ERROR rc1", "2 failed")])
        rep = redattrib.evidence_report(self.tmp)
        self.assertEqual([i["checker"] for i in rep["items"]], ["unit_tests"])
        self.assertEqual(rep["n_rows"], 1)

    def test_a_warn_row_that_did_retain_is_counted(self):
        """`checks()` passes `--strict` to skill_lint, which exits 1 on a
        WARNING -- so a `warn B002` row is rc 1 and DOES leave a file.

        Found by running the live check, not by reading the code: the first
        draft of `evidence_report` excluded every `warn` row and would have
        orphaned that file from the report that counts retentions.
        """
        self._log(9, [("skill_lint", "warn B002", "4 warning(s)")])
        self._evidence(9, "skill_lint", "x.md: WARN B002 body is 461 lines\n")
        rep = redattrib.evidence_report(self.tmp)
        self.assertEqual([i["checker"] for i in rep["items"]], ["skill_lint"])
        self.assertEqual(rep["n_since_retention_covered"], 1)

    def test_an_absent_row_is_not_counted_either(self):
        self._log(1, [("gone", "ABSENT", "script not present")])
        self.assertEqual(redattrib.evidence_report(self.tmp)["n_rows"], 0)

    def test_a_timeout_row_is_counted_because_it_does_retain(self):
        self._log(1, [("unit_tests", "TIMEOUT", "timed out after 600s")])
        self.assertEqual(redattrib.evidence_report(self.tmp)["n_rows"], 1)

    def test_rows_before_the_first_retained_round_are_split_out(self):
        self._log(1, [("unit_tests", "ERROR rc1", "2 failed")])
        self._log(9, [("unit_tests", "ERROR rc1", "1 failed")])
        self._evidence(9, "unit_tests",
                       "FAILED skills/a/scripts/test_z.py::test_q\n"
                       "1 failed, 5 passed in 1.0s\n")
        rep = redattrib.evidence_report(self.tmp)
        self.assertEqual(rep["first_retained_round"], 9)
        self.assertEqual(rep["n_before_retention"], 1)
        self.assertEqual(rep["n_since_retention"], 1)
        self.assertEqual(rep["n_since_retention_covered"], 1)

    def test_the_retained_file_resolves_the_row_to_a_test_node_id(self):
        self._log(9, [("unit_tests", "ERROR rc1", "1 failed")])
        self._evidence(9, "unit_tests",
                       "FAILED skills/a/scripts/test_z.py::test_q - X\n")
        rep = redattrib.evidence_report(self.tmp)
        self.assertEqual(rep["items"][0]["nodes"],
                         ["skills/a/scripts/test_z.py::test_q"])

    def test_a_row_with_a_retained_file_holding_no_summary_yields_no_nodes(self):
        self._log(9, [("unit_tests", "TIMEOUT", "said nothing before the kill")])
        self._evidence(9, "unit_tests", "collected 900 items\n")
        self.assertEqual(redattrib.evidence_report(self.tmp)["items"][0]["nodes"],
                         [])

    def test_no_logs_at_all_is_an_empty_report_not_a_crash(self):
        import tempfile
        rep = redattrib.evidence_report(tempfile.mkdtemp(prefix="ev-empty."))
        self.assertEqual(rep["n_rows"], 0)
        self.assertIsNone(rep["first_retained_round"])

    def test_the_two_node_id_patterns_agree(self):
        """`harness/redattrib.py` re-declares the pattern `skills/` owns.

        The duplication is deliberate (different tracks, different trees) and
        this is what stops it drifting.
        """
        self.assertEqual(redattrib.EVIDENCE_FAILED_RE.pattern,
                         corpus_check.FAILED_NODE_RE.pattern)
        sample = ("FAILED a/b.py::t - E\nERROR c/d.py\n"
                  "error: P001 not a node\n")
        self.assertEqual(redattrib.EVIDENCE_FAILED_RE.findall(sample),
                         corpus_check.FAILED_NODE_RE.findall(sample))


class TestThisTree(unittest.TestCase):
    """Assertions about the live repo, not about a fixture."""

    def test_the_ignore_line_landed_in_the_same_round_as_the_wiring(self):
        """Rounds 363/365, 409 and 441 each paid for the opposite."""
        with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
            self.assertIn("logs/corpus-evidence/", fh.read())

    def test_git_does_not_offer_to_track_a_retained_file(self):
        d = os.path.join(ROOT, "logs", "corpus-evidence", "round-check")
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, "probe.out")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("x\n")
        try:
            out = subprocess.run(
                ["git", "status", "--porcelain", "--", "logs/corpus-evidence"],
                cwd=ROOT, capture_output=True, text=True, timeout=60).stdout
            self.assertEqual(out.strip(), "")
        finally:
            os.unlink(probe)
            os.rmdir(d)

    def test_unit_tests_is_still_the_reddest_row_in_the_corpus_logs(self):
        rows = redattrib.corpus_rows(ROOT)["skills_health_round"]
        red = {}
        for per in rows.values():
            for checker, (status, _codes) in per.items():
                if status == "ERROR":
                    red[checker] = red.get(checker, 0) + 1
        self.assertTrue(red, "no corpus logs found in logs/")
        top = max(red, key=lambda c: red[c])
        self.assertEqual(top, "unit_tests")
        # Round 463 measured 26 of 65 (round 461 carried "25 of 60", one
        # round stale). Monotone, so accumulating logs cannot expire it.
        self.assertGreaterEqual(red["unit_tests"], 26)
        self.assertGreaterEqual(sum(red.values()), 65)

    def test_every_red_row_before_retention_existed_is_unrecoverable(self):
        """The floor, stated so no future round mistakes it for a gap.

        Retention writes files from the round it lands in onward. Rows older
        than the oldest retained round were destroyed by the `finally` this
        round removed the need for, and no instrument will ever recover them.
        """
        rep = redattrib.evidence_report(ROOT)
        first = rep["first_retained_round"]
        for item in rep["items"]:
            if first is None or item["round"] < first:
                self.assertIsNone(item["evidence"])

    def test_the_runner_table_names_a_check_that_exists(self):
        names = [n for n, _ in corpus_check.checks(ROOT)]
        for runner in corpus_check.RUNNER_CHECKS:
            self.assertIn(runner, names,
                          "RUNNER_CHECKS names a checker checks() no longer "
                          "returns")

    def test_the_cli_accepts_both_evidence_flags(self):
        out = subprocess.run(
            [sys.executable,
             os.path.join(ROOT, "skills", "skill-authoring", "scripts",
                          "corpus_check.py"), "--help"],
            capture_output=True, text=True, timeout=120).stdout
        self.assertIn("--evidence-dir", out)
        self.assertIn("--no-evidence", out)


if __name__ == "__main__":                                   # pragma: no cover
    unittest.main()

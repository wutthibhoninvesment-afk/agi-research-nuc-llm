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

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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


class TestTimeoutKeepsWhatTheCheckerSaid(unittest.TestCase):
    """Round 451. The timeout branch used to throw the whole run away.

    `unit_tests` fired it in rounds 431, 445, 448, 449 and 450, and each of
    those five rounds logged `COULD NOT RUN: unit_tests` with empty errors,
    empty warnings, empty coverage and no indication whether anything had
    gone red before the kill. These pin the salvage — and, first, pin that
    salvaging does NOT soften the verdict, which is the way this repair goes
    wrong.

    Every assertion below is about ONE killed run, so there is ONE killed
    run — `setUpClass`, not `setUp`. Five tests each burning their own 2 s
    budget would be this round's own finding committed again in the file
    that reports it, and the assertions stay separate so a failure still
    names which property broke.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        talkative = os.path.join(cls.tmp, "slow.py")
        write(talkative,
              "print('/a/SKILL.md: ERROR H001 no trigger', flush=True)\n"
              "print('warning: P004 x: never probed', flush=True)\n"
              "print('coverage 3/9 checkers', flush=True)\n"
              "import time\ntime.sleep(30)\n")
        cls.killed = corpus_check.run_one("x", [talkative], cls.tmp, timeout=2)
        mute = os.path.join(cls.tmp, "mute.py")
        write(mute, "import time\ntime.sleep(30)\n")
        cls.silent = corpus_check.run_one("x", [mute], cls.tmp, timeout=2)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_a_timeout_is_still_could_not_run(self):
        # THE GUARD ON THE REPAIR. Reporting the partial findings must not
        # turn a killed checker into a checker that ran.
        self.assertEqual(self.killed["status"], "timeout")
        self.assertTrue(self.killed["partial"])

    def test_errors_printed_before_the_kill_survive_it(self):
        self.assertEqual(self.killed["errors"], ["H001"])

    def test_warnings_printed_before_the_kill_survive_it(self):
        self.assertEqual(self.killed["warnings"], ["P004"])

    def test_coverage_printed_before_the_kill_survives_it(self):
        self.assertEqual(self.killed["coverage"], "3/9 checkers")

    def test_the_summary_says_it_was_killed_and_what_it_salvaged(self):
        self.assertIn("timed out after 2s", self.killed["summary"])
        self.assertIn("3 line(s) before the kill", self.killed["summary"])
        self.assertEqual(self.killed["output_lines"], 3)

    def test_the_elapsed_time_is_reported_on_the_timeout_branch_too(self):
        # `t0` was computed and then dropped on this branch, so no round
        # could say how close a checker was to its budget until it was over.
        self.assertGreaterEqual(self.killed["elapsed_s"], 2.0)
        self.assertEqual(self.killed["timeout_s"], 2)

    def test_a_checker_killed_before_it_spoke_says_exactly_that(self):
        # Silence and "it never got going" must not render the same — the
        # distinction the old branch destroyed for all five rounds.
        self.assertIn("said nothing before the kill", self.silent["summary"])
        self.assertEqual(self.silent["output_lines"], 0)
        self.assertEqual(self.silent["errors"], [])


class TestTimeoutReapsTheWholeTree(unittest.TestCase):
    """`subprocess.run(timeout=)` kills the child and orphans its tree.

    `unit_tests` IS a process tree — pytest spawning the nine checkers — so
    each of the five timeouts left live checker processes running on a box
    with `nproc` 1, competing with the rest of the round. This repo had
    written the pitfall down twice before this file ignored it
    (`fuzz-mutate-kill-loop/references/pitfalls.md`,
    `claim_check.run_command`). Pinned with a grandchild that outlives its
    parent's budget and leaves a marker if it is still alive afterwards.
    """

    def test_the_kill_reaps_grandchildren_not_just_the_child(self):
        tmp = tempfile.mkdtemp()
        try:
            marker = os.path.join(tmp, "orphan-was-alive")
            child = os.path.join(tmp, "grandchild.py")
            write(child, "import time, sys\ntime.sleep(4)\n"
                         "open(sys.argv[1], 'w').write('alive')\n")
            parent = os.path.join(tmp, "parent.py")
            write(parent, "import subprocess, sys, time\n"
                          "subprocess.Popen([sys.executable, %r, %r])\n"
                          "time.sleep(30)\n" % (child, marker))
            r = corpus_check.run_one("x", [parent], tmp, timeout=1)
            self.assertEqual(r["status"], "timeout")
            time.sleep(6)          # past the grandchild's own sleep
            self.assertFalse(os.path.exists(marker),
                             "grandchild survived the timeout kill")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestBudgetClause(unittest.TestCase):
    """Round 451. A rate that grows with the corpus needs a margin reported
    every round, not a verdict reported once the margin is gone."""

    def test_a_checker_past_the_fraction_is_named_with_its_share(self):
        clause = corpus_check.budget_clause(
            [{"check": "unit_tests", "elapsed_s": 512.0, "timeout_s": 600}])
        self.assertIn("unit_tests", clause)
        self.assertIn("512s/600s", clause)
        self.assertIn("85%", clause)

    def test_a_comfortable_checker_adds_no_clause(self):
        self.assertEqual(corpus_check.budget_clause(
            [{"check": "skill_lint", "elapsed_s": 3.0, "timeout_s": 600}]), "")

    def test_a_result_with_no_timing_is_skipped_not_crashed(self):
        # `absent` results and any future shape without the keys.
        self.assertEqual(corpus_check.budget_clause(
            [{"check": "x"}, {"check": "y", "elapsed_s": None,
                              "timeout_s": 600}]), "")

    def test_the_threshold_would_have_fired_on_the_round_431_measurement(self):
        # 162.3 s solo x the ~3.7 contention factor is how `unit_tests` got
        # to 600. At 162 s solo it is already 27% of budget; the point of the
        # 50% line is that it fires while there is still room to act.
        self.assertEqual(corpus_check.BUDGET_WARN_FRAC, 0.5)
        self.assertEqual(corpus_check.budget_clause(
            [{"check": "unit_tests", "elapsed_s": 301.0, "timeout_s": 600}]),
            "; budget: unit_tests 301s/600s (50%)")


# --------------------------------------------------------------------------
# Round 451 (harness A) — ONE live run, shared.
#
# `TestLiveCorpus` warns below that a live-corpus test spawns the whole
# `skills/` suite, and it is right one level down and blind one level up:
# each of the FOUR live tests in this file called `corpus_check.main()` on
# the real repo, and each of those spawns all nine checkers. Measured this
# round with `--durations`, those four tests cost 25.35 + 24.51 + 24.29 +
# 23.57 = 97.7 s of the suite's 162.3 s — 60% of a suite whose 600 s budget
# it had just blown five rounds running (`driver.log`, rounds 431/445/448/
# 449/450, `COULD NOT RUN: unit_tests`).
#
# The corpus does not change while pytest runs, so four invocations sample
# one state four times. This runs it ONCE and hands all four tests the same
# `(rc, report, stdout_lines)`. No assertion is weakened: every one of the
# four asserted over a single snapshot already, and none of them asserted
# anything ACROSS runs, so there was no stability property here to lose.
#
# Memoised at module scope rather than in a fixture because the callers are
# two different `TestCase` classes and `unittest` has no cross-class setup.
# The exception is cached too — if the live run blows up, all four tests
# must report it, not just whichever ran first.
_LIVE = []


def live_run():
    """`(rc, report, out_lines)` from ONE `corpus_check.main()` on the corpus.

    Always with the re-entry guard set, for the reason `TestLiveCorpus`
    gives: without it this recurses into the suite that is running it.
    """
    if not _LIVE:
        prior = os.environ.get(corpus_check.REENTRY_ENV)
        os.environ[corpus_check.REENTRY_ENV] = "1"
        out = os.path.join(tempfile.mkdtemp(), "r.json")
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = corpus_check.main(["--repo-root", ROOT, "--json", out])
            with open(out, encoding="utf-8") as f:
                report = json.load(f)
            _LIVE.append((rc, report,
                          [l for l in buf.getvalue().splitlines() if l.strip()]))
        except BaseException as exc:            # pragma: no cover - see above
            _LIVE.append(exc)
        finally:
            if prior is None:
                os.environ.pop(corpus_check.REENTRY_ENV, None)
            else:
                os.environ[corpus_check.REENTRY_ENV] = prior
    if isinstance(_LIVE[0], BaseException):     # pragma: no cover
        raise _LIVE[0]
    return _LIVE[0]


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
        rc, report, _ = live_run()
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
        _, report, _ = live_run()
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

    def test_placeholder_check_is_wired_in(self):
        """Round 429. Named membership, not a count: the count assertion
        above is derived and would have stayed green if the new checker had
        been written and never added to `checks()` — which is the exact
        failure round 427 had with this very check (proposed, never run)."""
        self.assertIn("placeholder_check", [n for n, _ in corpus_check.checks(ROOT)])

    def test_the_wrapper_script_exists_and_is_what_the_driver_calls(self):
        wrapper = os.path.join(ROOT, "skills", "run_checks_fast.sh")
        self.assertTrue(os.path.exists(wrapper))
        driver = open(os.path.join(ROOT, "run_driver.sh"),
                      encoding="utf-8").read()
        self.assertIn("skills/run_checks_fast.sh", driver)
        self.assertIn("corpus_check.py\" --line", driver)


# --------------------------------------------------------------------------
# Round 417 — the recall gap, carried onto the line the driver reads.
#
# Every checker here already published its coverage, and published it on a
# line this file throws away (`run_one` keeps `lines[-1]`). Round 415 paid
# for that: round 414's next-steps block was logged `0 stale` while
# containing a flatly false item, because the item sat in the published —
# but never quoted — gap.
# --------------------------------------------------------------------------


class TestCoverageToken(unittest.TestCase):
    """`coverage A/B unit[, C/D unit]*`, and nothing looser."""

    def test_a_single_fraction_parses(self):
        self.assertEqual(corpus_check.coverage_of("x: coverage 3/9 items"),
                         "3/9 items")

    def test_several_fractions_and_a_percentage_parse(self):
        self.assertEqual(
            corpus_check.coverage_of("s: 0 stale; coverage 9/13 items (69%), "
                                     "10/10 claims"),
            "9/13 items (69%), 10/10 claims")

    def test_a_clause_wrapped_over_two_lines_is_still_one_token(self):
        self.assertEqual(
            corpus_check.coverage_of("coverage 1/2 paths,\n   3/4 commands"),
            "1/2 paths, 3/4 commands")

    def test_prose_that_merely_says_coverage_yields_nothing(self):
        for text in ("this improves coverage a lot",
                     "coverage: unknown", "coverage 55 skills", ""):
            self.assertEqual(corpus_check.coverage_of(text), "", text)

    def test_the_last_clause_wins(self):
        # A checker that prints per-item detail before its summary must not
        # have the FIRST number lifted out as if it were the total.
        self.assertEqual(
            corpus_check.coverage_of("coverage 1/9 items\ncoverage 9/9 items"),
            "9/9 items")


class TestCoverageIsReadFromFullOutput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_coverage_survives_the_200_character_summary_truncation(self):
        # `case_coverage`'s real last line is already longer than 200 chars,
        # so a coverage clause appended to the end of it is cut off before it
        # reaches here. Parsing the FULL output rather than `summary` is what
        # makes the clause reachable at all — this pins that, and it fails if
        # anyone "simplifies" `coverage_of(out)` to `coverage_of(summary)`.
        p = os.path.join(self.tmp, "fake.py")
        write(p, "print('x' * 240 + '; coverage 5/7 skills')\n")
        r = corpus_check.run_one("x", [p], self.tmp)
        self.assertEqual(len(r["summary"]), 200)
        self.assertNotIn("coverage", r["summary"])
        self.assertEqual(r["coverage"], "5/7 skills")

    def test_a_checker_publishing_nothing_reports_an_empty_string(self):
        p = os.path.join(self.tmp, "fake.py")
        write(p, "print('all fine')\n")
        self.assertEqual(corpus_check.run_one("x", [p], self.tmp)["coverage"],
                         "")

    def test_every_result_shape_carries_the_key(self):
        # `main` reads `r["coverage"]` unconditionally; an early-return path
        # that omitted the key would raise there instead of here.
        p = os.path.join(self.tmp, "fake.py")
        write(p, "import sys\nprint('usage')\nsys.exit(2)\n")
        for r in (corpus_check.run_one("x", [p], self.tmp),
                  corpus_check.run_one("x", [os.path.join(self.tmp, "no.py")],
                                       self.tmp)):
            self.assertIn("coverage", r)


class TestLiveCoverageOnTheDriverLine(unittest.TestCase):
    """The point of the change: the aggregate line names the gaps."""

    def _last_line(self):
        # Round 451: was its own `corpus_check.main()` on the live corpus,
        # the third and fourth of four. Same snapshot, run once.
        return live_run()[2][-1]

    def test_the_aggregate_line_names_each_checker_that_published_coverage(self):
        line = self._last_line()
        self.assertIn("; coverage: ", line)
        for name in ("case_coverage", "claim_check", "state_claim_check"):
            self.assertIn(name, line.split("; coverage: ", 1)[1], line)

    def test_the_line_still_carries_the_error_and_warning_counts(self):
        # The coverage clause is an ADDITION. A round that reads this line
        # for a verdict must find the verdict where it always was.
        self.assertRegex(self._last_line(),
                         r"corpus-check: \d+ checker\(s\).*"
                         r"\d+ error\(s\), \d+ warning\(s\)")


class TestNoCoveragePublishedSaysSo(unittest.TestCase):
    def test_an_empty_result_set_says_none_published_rather_than_nothing(self):
        # Silence and "nobody published a denominator" must not render the
        # same, which is the whole complaint this change answers.
        import io as _io
        import contextlib
        tmp = tempfile.mkdtemp()
        try:
            saved = corpus_check.checks
            corpus_check.checks = lambda root: []
            buf = _io.StringIO()
            with contextlib.redirect_stdout(buf):
                corpus_check.main(["--repo-root", tmp])
            self.assertIn("coverage: none published", buf.getvalue())
        finally:
            corpus_check.checks = saved
            shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()


class TestPrecommitSubset(unittest.TestCase):
    """Round 453. The subset a round can run on its OWN tree before its last
    commit.

    `run_checks_fast.sh` (round 363) cut a corpus violation's detection
    latency from "the rotation, up to six rounds" to one round. Round 453
    measured what one round has cost across all 89 `skills-check` lines in
    `logs/driver.log`: 24 red rounds of 89, 16 episodes, mean 1.50 rounds,
    longest 4 -- and **zero of the 16 episodes opened by a skills(B) round**,
    while 9 of 15 were closed by one. The rounds that break the corpus are
    never the round that owns it, and the check that would have told them
    runs after they exit. One round is a floor, not a target, and the only
    way under it is a check the author can run while still alive.
    """

    def setUp(self):
        """Ask for the FULL checker table, whatever runner we are inside.

        Round 453, and this was a real defect found by running the thing
        rather than reasoning about it: these tests passed standalone (938
        passed) and FIVE of them failed when the corpus check ran them, which
        is the only way they actually run in this repo. `checks()` omits
        `unit_tests` when REENTRY_ENV is set -- the re-entry guard, so a
        runner that runs the suite that invokes the runner terminates -- so
        every assertion here was silently made against a NINE-checker table
        with the one excluded checker missing. `--only unit_tests` raised
        ValueError, `--precommit` selected the whole list, and
        PRECOMMIT_EXCLUDES named a checker that "did not exist".

        The properties under test are about the COMPLETE table and the
        selection logic over it; re-entry is a separate concern with its own
        tests. So clear the variable rather than skipping under it -- a skip
        would hide these from the runner that matters, which is the same
        mistake in a different costume.
        """
        self._saved = os.environ.pop(corpus_check.REENTRY_ENV, None)
        self.all = corpus_check.checks(ROOT)
        self.names = [n for n, _ in self.all]

    def tearDown(self):
        if self._saved is not None:
            os.environ[corpus_check.REENTRY_ENV] = self._saved

    def test_the_full_table_includes_the_excluded_checker(self):
        """The guard on setUp's own fix: if this goes red, every other test
        in this class is asserting against the wrong table again."""
        self.assertIn("unit_tests", self.names,
                      "setUp did not clear %s, so checks() returned the "
                      "re-entry table" % corpus_check.REENTRY_ENV)
        self.assertEqual(len(self.names), 10)

    def test_precommit_selects_a_strict_subset_and_not_the_whole_list(self):
        """NON-VACUITY, and it is not ceremonial.

        Round 452 shipped two configuration differentials whose two arms were
        the same arm -- `full_show_named(node, cap=FULL_SHOW_NEST)` bound the
        constant at DEFINITION time, so patching the module global compared
        new against new and both tests passed against a completely unchanged
        renderer. That defect was promoted into
        `skills/named-guardian-must-go-red/SKILL.md` ONE ROUND before this
        one. `checks()` builds its list at call time from a literal, so the
        same trap is not available here -- but the way you know that is by
        asserting the two selections differ, not by reading the code and
        feeling reassured.
        """
        full, skipped_full = corpus_check.select(self.all)
        pre, skipped_pre = corpus_check.select(self.all, precommit=True)
        self.assertEqual(skipped_full, [], "a full run skips nothing")
        self.assertNotEqual([n for n, _ in full], [n for n, _ in pre],
                            "--precommit selected the same list as a full "
                            "run: the flag is vacuous")
        self.assertTrue(set(n for n, _ in pre) < set(n for n, _ in full))
        self.assertEqual(sorted(skipped_pre),
                         sorted(corpus_check.PRECOMMIT_EXCLUDES))

    def test_the_exclusion_table_is_the_only_thing_keeping_a_checker_out(self):
        """The anti-drift property, and the reason the preset is an
        EXCLUSION list rather than an inclusion list.

        This file's own history is the argument: `checks()`'s docstring said
        "five" checkers for two checkers' worth of drift, and
        `run_checks_fast.sh`'s header said "six" until round 429. An
        inclusion list rots exactly that way -- silently, by omission, with
        the omitted checker never running and nothing saying so. Written as
        an exclusion, a NEW checker joins the preset automatically, and
        anyone who wants it out has to name it and give a reason.
        """
        selected, _ = corpus_check.select(self.all, precommit=True)
        for name in self.names:
            if name in corpus_check.PRECOMMIT_EXCLUDES:
                continue
            self.assertIn(name, [n for n, _ in selected],
                          "%s is in checks() but not in --precommit, and is "
                          "not named in PRECOMMIT_EXCLUDES -- a checker fell "
                          "out of the preset silently" % name)

    def test_no_exclusion_names_a_checker_that_no_longer_exists(self):
        """The mirror-image rot: an exclusion outliving its checker.

        Same class as carryforward's K003 (`an acknowledgement that outlives
        its debt is a mute button`), which is what caught round 452's own
        unscored bank. A stale name here excludes nothing and reads as though
        it does.
        """
        for name in corpus_check.PRECOMMIT_EXCLUDES:
            self.assertIn(name, self.names,
                          "PRECOMMIT_EXCLUDES names %r, which is not a "
                          "checker in checks()" % name)

    def test_every_exclusion_carries_a_measured_reason(self):
        """A checker is excluded on a NUMBER or not at all.

        `checks()` carries prose costs ("0.7 s", "~2 s", "~37s") that were
        already stale when round 451 measured `unit_tests` at 162.34s and
        round 453 at 99.83s. An exclusion justified by "it's slow" is the
        same claim with nothing behind it.
        """
        for name, reason in corpus_check.PRECOMMIT_EXCLUDES.items():
            self.assertGreater(len(reason), 80,
                               "%s's exclusion reason is too short to carry "
                               "a measurement" % name)
            self.assertRegex(reason, r"\d",
                             "%s's exclusion reason names no number" % name)

    def test_an_unknown_only_name_is_an_error_not_a_silent_empty_run(self):
        """A typo'd `--only xref` must not run nothing and print green.

        This is the failure the whole subset exists to avoid, so it would be
        a particularly bad one to ship inside it.
        """
        with self.assertRaises(ValueError) as caught:
            corpus_check.select(self.all, only=["xref"])
        self.assertIn("xref", str(caught.exception))
        self.assertIn("xref_check", str(caught.exception),
                      "the error should name the known checkers")

    def test_only_wins_over_precommit(self):
        selected, skipped = corpus_check.select(
            self.all, only=["unit_tests"], precommit=True)
        self.assertEqual([n for n, _ in selected], ["unit_tests"],
                         "--only must be able to select a checker that "
                         "--precommit excludes")
        self.assertNotIn("unit_tests", skipped)

    def test_a_subset_run_says_what_it_did_not_run(self):
        self.assertEqual(corpus_check.subset_clause([]), "",
                         "a full run's summary line must be byte-identical "
                         "to what every round before 453 logged")
        clause = corpus_check.subset_clause(["unit_tests", "verb_audit"])
        self.assertIn("SUBSET", clause)
        self.assertIn("unit_tests", clause)
        self.assertIn("verb_audit", clause)

    def test_end_to_end_the_summary_line_carries_the_subset_clause(self):
        """Runs the real `main()` against the real repo, selecting the
        cheapest checker (0.09s solo) so the assertion costs a second.

        `subset_clause` being right in isolation does not prove `main`
        calls it.
        """
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = corpus_check.main(["--only", "state_claim_check",
                                    "--repo-root", ROOT])
        out = buf.getvalue()
        summary = [l for l in out.splitlines() if l.startswith("corpus-check:")]
        self.assertEqual(len(summary), 1, out)
        self.assertIn("SUBSET, did NOT run:", summary[0])
        self.assertIn("xref_check", summary[0])
        self.assertIn("1 checker(s)", summary[0])
        self.assertEqual(rc, corpus_check.PASS, out)

    def test_list_mode_names_the_exclusions_and_runs_nothing(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = corpus_check.main(["--list", "--repo-root", ROOT])
        out = buf.getvalue()
        self.assertEqual(rc, corpus_check.PASS)
        for name in self.names:
            self.assertIn(name, out)
        self.assertIn("EXCLUDED from --precommit", out)
        self.assertNotIn("corpus-check:", out,
                         "--list must not print a verdict line")

    def test_the_documented_runner_forwards_the_flag(self):
        """`skills/run_checks_fast.sh --precommit` is the ONE command this
        round documents, so it gets a test rather than a promise.

        The runner ends `exec python3 corpus_check.py "$@"`. Drop the `"$@"`
        -- a plausible tidy-up, since no caller passed an argument before
        round 453 -- and every documented invocation silently runs the FULL
        check instead of the subset, taking 125s instead of 26s and giving
        every future reader the impression the subset works. `named-is-not-
        invoked`: the script being mentioned in the docs is not the script
        receiving the argument.
        """
        runner = os.path.join(ROOT, "skills", "run_checks_fast.sh")
        self.assertTrue(os.path.exists(runner), runner)
        env = dict(os.environ)
        # Same trap as setUp: a subprocess INHERITS the re-entry guard, and
        # with it set `--list` never prints the excluded checker at all.
        env.pop(corpus_check.REENTRY_ENV, None)
        proc = subprocess.run(["bash", runner, "--list"], env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("EXCLUDED from --precommit", proc.stdout,
                      "the runner did not forward --list to corpus_check.py")
        self.assertNotIn("corpus-check:", proc.stdout,
                         "the flag was swallowed and a full run happened")


# --------------------------------------------------------------------------
# Round 477 (skills B). The `unit_tests` subject set.
#
# Round 475's next-step 2 found `RUNNER_CHECKS["unit_tests"]`'s description
# claiming "pytest over skills/*/scripts/test_*.py" against an argv that
# named two directories, while the glob matched fifteen files in three. The
# missing one was `skills/prediction-banking/scripts`, so round 471's
# `test_bank_audit.py` — 19 tests — was run by nothing scheduled, and round
# 473 read the DESCRIPTION, declared `bank_audit.py` `wired` on the strength
# of it, and left W002 an ERROR for two rounds unseen.
#
# The obvious fix is `derived-subject-set` step 3: derive the argv from the
# glob. Round 477 MEASURED that fix before shipping it and it is wrong here.
# `harness/wiring_audit.py:52` names "a `glob`" as its own documented
# under-approximation, so a derived argv is invisible to the invocation
# closure: the glob version took the closure from 109 files to 95 and turned
# TWELVE `wired` declarations into W002 errors, including the very entry the
# edit existed to wire.
#
# So the argv stays a literal enumeration for the static analyser, and what
# gets derived is the ORACLE. These tests are the binding between them. A
# fourth skill that grows a `scripts/test_*.py` file arrives here as a
# FAILURE naming itself, which is the promise the old description made in
# prose and could not keep.
# --------------------------------------------------------------------------

class TestSkillTestDirs(unittest.TestCase):

    def unit_tests_argv_dirs(self, root):
        """The directory arguments of the live `unit_tests` argv, relative.

        The `REENTRY_ENV` pop is not defensive: `checks()` omits `unit_tests`
        entirely when that variable is set, and it IS set for these tests,
        because `unit_tests` is what runs them. The first draft of this class
        read `dict(checks(root))["unit_tests"]` directly. It passed standalone
        and raised `KeyError: 'unit_tests'` inside the runner that schedules
        it — twice, in the two tests that are the whole point of the class.
        `TestRunOne`'s sibling tests already pop it from a subprocess env for
        the same reason; this is the in-process form.
        """
        saved = os.environ.pop(corpus_check.REENTRY_ENV, None)
        try:
            argv = dict(corpus_check.checks(root))["unit_tests"]
        finally:
            if saved is not None:
                os.environ[corpus_check.REENTRY_ENV] = saved
        self.assertEqual(argv[:3], ["-m", "pytest", "-q"], argv)
        return sorted(os.path.relpath(a, root).replace(os.sep, "/")
                      for a in argv[3:])

    def test_the_argv_is_exactly_what_the_glob_matches(self):
        """THE enforcement. Left side literal, right side derived.

        This is the assertion round 475's item 2 asked for. It is not
        `assertIn` and not a count: a directory in the argv that holds no
        skill test file is as much a defect as a directory of tests nobody
        runs — the first is a pytest argument that will start erroring the
        day the directory moves, the second is round 363's four-round-red
        test all over again.
        """
        self.assertEqual(self.unit_tests_argv_dirs(ROOT),
                         corpus_check.skill_test_dirs(ROOT))

    def test_the_live_answer_is_five_named_directories(self):
        """Pinned by name, not by count.

        `derived-subject-set` step 7's rule: an exact pin is what catches a
        member that silently stops being covered. A count of 5 would still
        pass if `prediction-banking` were swapped for something else.

        It was THREE for about an hour of round 477, and the fourth arrived
        the way the design says it should: the round wrote
        `skills/derived-subject-set/scripts/test_pattern_vs_enum.py`, this
        test went red naming the directory, and the argv gained it. That is
        the promise the old prose description made and could not keep,
        collected on inside the same round that made it.

        The FIFTH arrived the same way and is the replication: round 483
        wrote `skills/seed-sweep-needs-a-same-seed-control/scripts/
        test_seedsweep.py`, this test and `pattern_vs_enum`'s E001 both went
        red naming the directory, and the argv gained it. Two rounds, two
        live falsifications, both inside the round that caused them -- the
        latency this design replaced was bounded by the rotation.
        """
        self.assertEqual(corpus_check.skill_test_dirs(ROOT), [
            "skills/derived-subject-set/scripts",
            "skills/prediction-banking/scripts",
            "skills/seed-sweep-needs-a-same-seed-control/scripts",
            "skills/session-inheritance-audit/scripts",
            "skills/skill-authoring/scripts",
        ])

    def test_the_description_and_the_oracle_share_one_constant(self):
        """The drift that started this cannot recur silently.

        The description is BUILT from `SKILL_TEST_GLOB`, so a round that
        rewords it to claim a different pattern has to change the constant,
        which changes the oracle, which fails the test above. Asserting the
        glob is IN the rendered text is what keeps that composition from
        being quietly flattened back into a hand-typed sentence.
        """
        desc = corpus_check.RUNNER_CHECKS["unit_tests"]
        self.assertIn(corpus_check.SKILL_TEST_GLOB, desc)
        self.assertEqual(corpus_check.SKILL_TEST_GLOB,
                         "skills/*/scripts/test_*.py")

    def test_a_fourth_skill_with_tests_makes_the_check_go_red(self):
        """The falsifier. `derived-subject-set` step 2, run forwards.

        A synthetic tree with a fourth `skills/<x>/scripts/test_*.py` is what
        the next round to write one produces. The oracle must see it and the
        literal argv must not, so the equality above must FAIL — proving the
        test can go red rather than that it is green today.
        """
        with tempfile.TemporaryDirectory() as tmp:
            for skill in ("prediction-banking", "session-inheritance-audit",
                          "skill-authoring", "zzz-newcomer"):
                write(os.path.join(tmp, "skills", skill, "scripts",
                                   "test_x.py"), "def test_x(): pass\n")
            oracle = corpus_check.skill_test_dirs(tmp)
            self.assertIn("skills/zzz-newcomer/scripts", oracle)
            self.assertNotIn("skills/zzz-newcomer/scripts",
                             self.unit_tests_argv_dirs(tmp))
            self.assertNotEqual(self.unit_tests_argv_dirs(tmp), oracle,
                                "the check cannot go red — it is not a check")

    def test_a_skill_with_scripts_but_no_tests_is_not_in_either_side(self):
        """The other direction, and the reason the glob ends in `test_*.py`.

        Several skills carry `scripts/` with no test file. Pointing pytest at
        one is not harmless: pytest exits 4 on a directory it cannot collect
        from, and `corpus_check` reads 2-5 as COULD_NOT_RUN, so the whole
        health check would go dark rather than red.
        """
        with tempfile.TemporaryDirectory() as tmp:
            write(os.path.join(tmp, "skills", "prediction-banking", "scripts",
                               "test_x.py"), "def test_x(): pass\n")
            write(os.path.join(tmp, "skills", "toolless", "scripts",
                               "helper.py"), "x = 1\n")
            self.assertEqual(corpus_check.skill_test_dirs(tmp),
                             ["skills/prediction-banking/scripts"])

    def test_the_argv_stays_statically_foldable_for_the_closure(self):
        """The regression test for the fix this round REJECTED.

        `wiring_audit` folds `os.path.join(root, "skills", "x", "scripts")`
        into a directory edge and cannot fold `glob.glob(...)`. Twelve
        registry entries' only route into the invocation closure is this
        argv, so a future round that "simplifies" the enumeration into the
        glob its own description names breaks them. Measured, round 477:
        109 files in the closure became 95, and 12 `wired` declarations
        became W002 errors.

        This asserts the PROPERTY (every argv directory resolves to a real
        reference edge from this file) rather than the absence of the string
        `glob`, so it also covers the next clever way of losing it.
        """
        sys.path.insert(0, os.path.join(ROOT, "harness"))
        try:
            import wiring_audit
        finally:
            sys.path.pop(0)
        rel = "skills/skill-authoring/scripts/corpus_check.py"
        index = wiring_audit.Index(wiring_audit.tracked_files(ROOT))
        edges, _ = wiring_audit.references(ROOT, rel, index)
        for d in corpus_check.skill_test_dirs(ROOT):
            reached = [p for p in edges if p.startswith(d + "/")]
            self.assertTrue(reached,
                            "%s is in the argv but wiring_audit resolves no "
                            "reference to anything under it from %s — the "
                            "argv has stopped being statically foldable"
                            % (d, rel))

    def test_bank_audit_is_reached_through_this_argv_and_declared_wired(self):
        """The debt round 475's item 3 opened, closed end to end.

        Two halves, and the point is that they are two: the file is REACHED
        (the tests that import it now run every round) and the registry SAYS
        so. Round 473 had the second without the first.
        """
        sys.path.insert(0, os.path.join(ROOT, "harness"))
        try:
            import wiring_audit
        finally:
            sys.path.pop(0)
        target = "skills/prediction-banking/scripts/bank_audit.py"
        index = wiring_audit.Index(wiring_audit.tracked_files(ROOT))
        edges, _ = wiring_audit.references(
            ROOT, "skills/skill-authoring/scripts/corpus_check.py", index)
        self.assertIn(target, edges,
                      "corpus_check.py no longer reaches bank_audit.py")
        reg = json.load(open(os.path.join(ROOT, "harness",
                                          "wiring-registry.json"),
                             encoding="utf-8"))
        entry = reg["entry_points"][target]
        self.assertEqual(entry["status"], "wired", entry)
        self.assertEqual(entry["via"],
                         "skills/skill-authoring/scripts/corpus_check.py:-")

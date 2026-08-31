#!/usr/bin/env python3
"""Tests for corpus_history.py (round 363). Offline; no git replay — the
59-commit replay costs minutes, so what is pinned here is the analysis that
turns its raw rows into the claims the knowledge file makes.

The severity split is the point. The first draft of this tool reported "17 of
59 commits RED" and buried the fact that 15 of those were ONE known,
deliberately carried warning (B002) and only 2 were an actual ERROR. Merging
the two would have been the same class of mistake the tool exists to find.
"""

import json
import os
import unittest

import corpus_history as ch


def row(short, red_kind=None, codes=(), warnings=(), subject="Round N (x)",
        date="2026-08-30", index=0):
    checkers = {"skills/skill-authoring/scripts/skill_lint.py": {
        "status": "red" if red_kind else "green",
        "red_kind": red_kind, "errors": list(codes),
        "warnings": list(warnings)}}
    return {"sha": short * 6, "short": short, "date": date, "subject": subject,
            "index": index, "checkers": checkers, "red": bool(red_kind),
            "red_kind": red_kind, "error_codes": sorted(codes),
            "unrunnable": []}


class TestClassify(unittest.TestCase):
    def test_skill_lint_error_is_not_a_warning(self):
        e, w = ch.classify("/x/SKILL.md: ERROR H001 no trigger section")
        self.assertEqual((e, w), (["H001"], []))

    def test_skill_lint_warning_is_not_an_error(self):
        e, w = ch.classify("/x/SKILL.md: WARN B002 body is long")
        self.assertEqual((e, w), ([], ["B002"]))

    def test_case_coverage_lowercase_shapes(self):
        e, w = ch.classify("error: P001 foo: 0 positive case(s)\n"
                           "warning: P004 bar: never probed")
        self.assertEqual((e, w), (["P001"], ["P004"]))

    def test_a_line_with_no_code_contributes_nothing(self):
        self.assertEqual(ch.classify("skill-lint: 31 skill(s), 0 error(s)"),
                         ([], []))


class TestEpisodes(unittest.TestCase):
    def _rows(self, spec):
        return [row("c%d" % i, kind, codes, index=i)
                for i, (kind, codes) in enumerate(spec)]

    def test_error_and_strict_episodes_do_not_merge(self):
        rows = self._rows([("strict", []), ("strict", []), (None, []),
                           ("error", ["P001"])])
        self.assertEqual(len(ch.episodes(rows, "strict")), 1)
        self.assertEqual(len(ch.episodes(rows, "error")), 1)
        self.assertEqual(ch.episodes(rows, "strict")[0]["length"], 2)
        self.assertEqual(ch.episodes(rows, "error")[0]["length"], 1)

    def test_adjacent_episodes_of_different_kind_are_not_one_run(self):
        # a strict commit immediately followed by an error commit is TWO
        # episodes, not one four-commit smear
        rows = self._rows([("strict", []), ("error", ["P001"])])
        self.assertEqual([e["length"] for e in ch.episodes(rows, "strict")], [1])
        self.assertEqual([e["length"] for e in ch.episodes(rows, "error")], [1])

    def test_an_episode_reaching_the_newest_commit_is_marked_open(self):
        rows = self._rows([(None, []), ("error", ["P001"]), ("error", ["P001"])])
        ep = ch.episodes(rows, "error")[0]
        self.assertTrue(ep.get("open"))
        self.assertIsNone(ep["closed_by"])
        self.assertEqual(ep["length"], 2)

    def test_a_closed_episode_names_the_commit_that_closed_it(self):
        rows = self._rows([("error", ["P001"]), (None, [])])
        rows[1]["subject"] = "Round 363 (skills B): the fix"
        ep = ch.episodes(rows, "error")[0]
        self.assertFalse(ep.get("open"))
        self.assertEqual(ep["closed_by"], "Round 363 (skills B): the fix")

    def test_no_red_commits_means_no_episodes(self):
        self.assertEqual(ch.episodes(self._rows([(None, []), (None, [])])), [])

    def test_codes_fall_back_to_warnings_for_a_strict_episode(self):
        rows = [row("a", "strict", (), ("B002",), index=0)]
        self.assertEqual(ch.episodes(rows, "strict")[0]["codes"], ["B002"])


class TestFlagDetection(unittest.TestCase):
    """`supported_flags` reads SOURCE rather than running `--help`, because
    replaying 59 historical versions of two scripts means running code nobody
    in this session has read — and this workspace has already been bitten by a
    script whose `--help` ran its main effect."""

    def test_missing_file_is_no_flags_not_a_crash(self):
        self.assertEqual(ch.supported_flags("/nope/x.py", ["--house"]), set())

    def test_reads_declared_flags_from_source(self):
        import os
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), "s.py")
        open(p, "w").write('ap.add_argument("--house")\n'
                           "ap.add_argument('paths', nargs='+')\n")
        self.assertEqual(ch.supported_flags(p, ["--house", "--strict"]),
                         {"--house"})
        self.assertTrue(ch.takes_positional_paths(p))




# --------------------------------------------------------------------------
# Round 387. The tool had two blind spots and one false claim; these pin all
# three. Still offline — no git replay.


class TestArtifactQuarantine(unittest.TestCase):
    """`ARTIFACT_CODES` — ERROR codes whose inputs git cannot supply.

    The failure this prevents: round 363's docstring enumerated the ERROR
    codes it believed were computed from tracked files only. Round 375 added
    `P008`, reading the gitignored probe reports, and the tool reported the
    corpus ERROR-red at every commit from `78077fa` on — a 10-commit episode
    rendered STILL OPEN that was not a violation. The live check said PASS
    for all ten rounds.
    """

    def test_the_gitignore_rule_the_quarantine_rests_on_still_exists(self):
        """Anti-rot, and the reason the quarantine is safe.

        Suppressing four ERROR codes is only honest while git really does
        keep their inputs out of every archived tree. If that rule is ever
        deleted the codes become governable and the quarantine turns into a
        mute button — the exact thing `P008` and `K003` both exist to
        catch. So the rule is READ, not assumed.
        """
        with open(os.path.join(ch.REPO, ".gitignore"), encoding="utf-8") as f:
            rules = [l.strip() for l in f]
        self.assertIn(ch.ARTIFACT_INPUT, rules,
                      "%s is no longer gitignored — ARTIFACT_CODES now "
                      "suppresses findings git CAN supply inputs for; "
                      "re-adjudicate the set." % ch.ARTIFACT_INPUT)

    def test_an_artifact_only_error_is_not_error_red(self):
        e, a = ch.split_artifact(["P008"])
        self.assertEqual((e, a), ([], ["P008"]))

    def test_a_real_error_beside_an_artifact_is_still_error_red(self):
        e, a = ch.split_artifact(["P001", "P008"])
        self.assertEqual((e, a), (["P001"], ["P008"]))

    def test_governable_codes_are_untouched(self):
        e, a = ch.split_artifact(["H001", "K001", "K003"])
        self.assertEqual((e, a), (["H001", "K001", "K003"], []))

    def test_every_quarantined_code_is_a_case_coverage_probe_code(self):
        """The set is not a grab-bag: all four read `state/trigger-eval/`.

        A code from a checker that reads only tracked files has no business
        here, and adding one would silence a real finding.
        """
        src = open(os.path.join(ch.REPO, ch.CASE_COVERAGE),
                   encoding="utf-8").read()
        for code in ch.ARTIFACT_CODES:
            self.assertIn('"%s"' % code, src,
                          "%s is quarantined but case_coverage.py does not "
                          "emit it" % code)


class TestCheckerSets(unittest.TestCase):
    def test_core_is_exactly_round_363s_pair(self):
        """Round 363's published figures must stay re-derivable."""
        self.assertEqual(ch.CHECKER_SETS["core"],
                         (ch.SKILL_LINT, ch.CASE_COVERAGE))

    def test_all_is_a_superset_of_core(self):
        self.assertTrue(set(ch.CHECKER_SETS["core"])
                        <= set(ch.CHECKER_SETS["all"]))

    def test_all_matches_the_live_checks_own_list_minus_unit_tests(self):
        """The two instruments must not drift apart again.

        This is the whole round-387 finding in one assertion: if a future
        round adds a checker to `corpus_check.py` and not here, the replay
        silently stops covering it — which is how the 2-vs-7 gap opened.
        `unit_tests` is excluded on purpose: it is a nested pytest run, not
        a corpus rule, and it has no historical tree to run against.
        """
        import corpus_check
        # `corpus_check` names the carryforward checker `carryforward` and
        # the script is `carryforward_check.py`; every other name is the
        # bare script stem. Compare on SCRIPT PATHS, which both sides
        # ultimately run, rather than on the two naming conventions.
        live = sorted(os.path.relpath(argv[0], ch.REPO)
                      for name, argv in corpus_check.checks(ch.REPO)
                      if name != "unit_tests")
        self.assertEqual(live, sorted(ch.CHECKER_SETS["all"]),
                         "corpus_check.py and CHECKER_SETS['all'] disagree — "
                         "a checker the live check runs is not replayed, "
                         "which is how the 2-vs-7 gap opened")


class TestReadSet(unittest.TestCase):
    def test_read_set_covers_the_inputs_the_carryforward_checker_names(self):
        """`--scope read` must include the ledger, or K001/K003 stay invisible.

        4 of the 5 live failures produced no commit under `skills/`. Three of
        them were carryforward findings, whose entire input set is under
        `state/`.
        """
        import carryforward_check as cf
        self.assertTrue(
            any(cf.LEDGER_FILE.startswith(p.rstrip("/"))
                for p in ch.READ_SET),
            "%s is outside READ_SET" % cf.LEDGER_FILE)

    def test_read_set_is_a_superset_of_the_home_scope(self):
        self.assertIn("skills/", ch.READ_SET)


class TestLiveLog(unittest.TestCase):
    """Parsing `logs/driver.log`'s skills-check verdicts."""

    LINES = (
        "[2026-08-31 00:47:13] round 383: skills-check PASS "
        "(corpus-check: 7 checker(s), 0 error(s), 6 warning(s))\n"
        "[2026-08-31 04:06:36] round 386: skills-check FAIL — the corpus "
        "violates its own rules — state_claim_check  warn S005              "
        "state_claim_check: 7 claim(s): 7 re-derivable, 0 skipped (none); 0 "
        "stale xref_check         ok                     xref_check: 0 "
        "dangling citation(s) carryforward       ERROR K001             "
        "carryforward: 66 bank(s) unit_tests         ERROR rc1              "
        "2 failed, 627 passed\n")

    def _rows(self):
        import tempfile
        fd, p = tempfile.mkstemp(suffix=".log")
        with os.fdopen(fd, "w") as f:
            f.write(self.LINES)
        try:
            return ch.live_rounds(p)
        finally:
            os.unlink(p)

    def test_both_verdicts_are_read(self):
        rows = self._rows()
        self.assertEqual([(r["round"], r["verdict"]) for r in rows],
                         [(383, "PASS"), (386, "FAIL")])

    def test_a_pass_carries_no_codes(self):
        self.assertEqual(self._rows()[0]["codes"], [])

    def test_error_codes_are_attributed_to_their_checker(self):
        self.assertEqual(self._rows()[1]["codes"],
                         ["carryforward:K001", "unit_tests:rc1"])

    def test_a_warn_code_is_not_read_as_an_error(self):
        """S005 is `warn` in the same line and must not appear."""
        self.assertNotIn("state_claim_check:S005", self._rows()[1]["codes"])

    def test_the_checker_name_does_not_swallow_the_previous_summary(self):
        """The first draft captured `0 stale xref_check` as the name.

        Same over-capture shape round 386 hit in `_foreign_hint`: a pattern
        true of a wider span than the thing it names.
        """
        for code in self._rows()[1]["codes"]:
            self.assertNotIn(" ", code, "checker name over-captured: %r" % code)

    def test_a_missing_log_is_empty_not_a_crash(self):
        self.assertEqual(ch.live_rounds("/nonexistent/driver.log"), [])


class TestJoinLive(unittest.TestCase):
    def test_a_round_with_no_commit_in_scope_is_absent_not_green(self):
        """The distinction the whole round rests on.

        A live FAIL whose round produced no commit under the replay scope is
        invisible to the replay. Calling that `green` would report agreement
        where there is no observation at all.
        """
        live = [{"round": 386, "verdict": "FAIL",
                 "codes": ["carryforward:K001"]}]
        joined = ch.join_live(live, [])
        self.assertEqual(joined[0]["replay"], "absent")
        self.assertIsNone(joined[0]["commit"])

    def test_a_round_with_a_commit_reports_that_commits_verdict(self):
        live = [{"round": 380, "verdict": "FAIL", "codes": ["carryforward:K003"]}]
        rows = [row("f6d023a", "error", ["P008"], subject="Round 380 (skills B): x")]
        rows[0]["artifact_codes"] = []
        joined = ch.join_live(live, rows)
        self.assertEqual(joined[0]["replay"], "error")
        self.assertEqual(joined[0]["replay_codes"], ["P008"])

    def test_round_of_reads_the_commit_subject(self):
        self.assertEqual(ch.round_of("Round 385 (harness A): the tier"), 385)
        self.assertIsNone(ch.round_of("AUTO-COMMIT v4"))

    def test_bare_strips_the_checker_prefix(self):
        self.assertEqual(ch.bare("carryforward:K001"), "K001")
        self.assertEqual(ch.bare("rc1"), "rc1")


class TestArtifactEpisodes(unittest.TestCase):
    def test_an_artifact_episode_does_not_merge_with_an_error_episode(self):
        rows = [row("a", "artifact", []), row("b", "error", ["P001"])]
        rows[0]["artifact_codes"] = ["P008"]
        rows[0]["error_codes"] = []
        rows[1]["artifact_codes"] = []
        self.assertEqual(len(ch.episodes(rows, "artifact")), 1)
        self.assertEqual(len(ch.episodes(rows, "error")), 1)

    def test_an_artifact_episode_is_labelled_by_its_artifact_codes(self):
        rows = [row("a", "artifact", [])]
        rows[0]["artifact_codes"] = ["P008"]
        rows[0]["error_codes"] = []
        self.assertEqual(ch.episodes(rows, "artifact")[0]["codes"], ["P008"])


class TestExtractTops(unittest.TestCase):
    """`EXTRACT_TOPS` — the tree every replay judges.

    An input outside this tuple is absent from the archived tree, and an
    absent input reads as a VIOLATION rather than as `absent`. Round 387's
    own first draft omitted `nuc/`, and the six-checker replay reported 29 of
    40 commits ERROR-red on seven K003 findings that were all missing-input.
    """

    def test_every_bank_the_ledger_names_is_inside_an_extracted_path(self):
        """Re-derived from the live ledger, not re-listed by hand.

        This is the guard the hand-made list did not have. `nuc/` entered
        EXTRACT_TOPS only because seven E-round banks live there; the next
        track to put a bank somewhere new must not have to be noticed.
        """
        led = json.load(open(os.path.join(ch.REPO,
                                          "state/prediction-bank-ledger.json"),
                             encoding="utf-8"))
        tops = {p.rstrip("/").split("/")[0] for p in ch.EXTRACT_TOPS}
        outside = sorted({e["bank"] for e in led["banks"].values()
                          if e.get("bank")
                          and e["bank"].split("/")[0] not in tops})
        self.assertEqual(outside, [],
                         "bank(s) outside EXTRACT_TOPS — the replay will "
                         "report K003 'no bank on disk' for each, which is "
                         "missing-input and not a violation")

    def test_the_read_set_is_covered_by_the_extracted_tops(self):
        """You cannot select commits by a path you never materialize."""
        tops = {p.rstrip("/").split("/")[0] for p in ch.EXTRACT_TOPS}
        for p in ch.READ_SET:
            self.assertIn(p.rstrip("/").split("/")[0], tops,
                          "%s is in READ_SET but never extracted" % p)




class TestJoinTakesTheWorstCommitOfARound(unittest.TestCase):
    """A round lands more than one commit and the join must not pick one.

    Round 370 banked its predictions in one commit and registered them in
    the next; the K001 episode opened and closed inside a single round. An
    earlier draft kept the FIRST commit per round and reported round 374 as
    `strict` while a second round-374 commit was K003-red — under-reporting
    the replay in exactly the direction that flatters the conclusion.
    """

    def _rows(self):
        a = row("aaa", "strict", (), subject="Round 374 (language C): part 1")
        b = row("bbb", "error", ["K003"], subject="Round 374 (language C): part 2")
        for r in (a, b):
            r["artifact_codes"] = []
        return [a, b]

    def test_the_worst_verdict_wins(self):
        j = ch.join_live([{"round": 374, "verdict": "FAIL", "codes": []}],
                         self._rows())[0]
        self.assertEqual(j["replay"], "error")
        self.assertEqual(j["commit"], "bbb")
        self.assertEqual(j["n_commits"], 2)

    def test_codes_are_unioned_across_the_rounds_commits(self):
        j = ch.join_live([{"round": 374, "verdict": "FAIL", "codes": []}],
                         self._rows())[0]
        self.assertEqual(j["replay_codes"], ["K003"])

    def test_error_outranks_artifact_which_outranks_strict(self):
        rows = []
        for short, kind, codes, art in (("a", "strict", [], []),
                                        ("b", "artifact", [], ["P008"]),
                                        ("c", "error", ["K001"], [])):
            r = row(short, kind, codes, subject="Round 9 (x)")
            r["artifact_codes"] = art
            rows.append(r)
        for keep, expect in ((rows[:2], "artifact"), (rows, "error")):
            j = ch.join_live([{"round": 9, "verdict": "PASS", "codes": []}],
                             keep)[0]
            self.assertEqual(j["replay"], expect)


if __name__ == "__main__":
    unittest.main()

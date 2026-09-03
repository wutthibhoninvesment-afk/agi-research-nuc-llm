"""Tests for harness/redattrib.py (round 455, SWE-loop D).

Two kinds. `TestSynthetic` builds a whole fake repo root -- driver log,
per-round health logs, registry -- and pins the mechanics. `TestThisTree`
asserts properties of the LIVE tree, which makes this file itself a
whole-tree assertion in the sense the module measures. It is deliberately
NOT in harness/crosstrack-registry.json: that registry's membership rule is
`has actually gone red in a retained per-round log`, and declaring a node
that never has would fire this module's own R002. It joins the registry the
first time it breaks, which is the fail-closed behaviour, not an omission.
"""

import collections
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))

import redattrib as RA  # noqa: E402


def build_root(tmp, driver_lines, logs, registry):
    os.makedirs(os.path.join(tmp, "logs"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "harness"), exist_ok=True)
    with open(os.path.join(tmp, "logs", "driver.log"), "w") as fh:
        fh.write("\n".join(driver_lines) + "\n")
    for name, text in logs.items():
        with open(os.path.join(tmp, "logs", name), "w") as fh:
            fh.write(text)
    with open(os.path.join(tmp, RA.REGISTRY_NAME), "w") as fh:
        json.dump(registry, fh)
    return tmp


BASE_REG = {
    "_subject_scope": {"own-suite": "", "whole-tree": "", "environmental": "",
                       "shared-file-own-content": "", "shared-corpus": ""},
    "_track_suites": {"harness(A)": ["harness/tests"],
                      "language(C)": ["languages/whence/tests"],
                      "skills(B)": ["skills"],
                      "SWE-loop(D)": ["harness/tests", "languages/whence/tests"],
                      "NUC-integration(E)": ["nuc/tests"]},
    "nodes": {},
}


def SUBJ(scope, evidence="subject"):
    """A registry entry, with the `evidence` R005 has required since round 467.

    A helper rather than a dict literal at each site so a future mandatory
    field is one edit here instead of one per test -- and so a test that means
    to omit `evidence` has to say so by not calling this.
    """
    return {"subject_scope": scope, "evidence": evidence, "why": ""}


def pytest_log(*failed):
    body = "".join("FAILED %s\n" % f for f in failed)
    if failed:
        return body + "%d failed, 10 passed in 1.00s\n" % len(failed)
    return body + "10 passed in 1.00s\n"


def corpus_log(rows, n_err=0, n_warn=0, broken=()):
    """A `corpus_check.py` log built with that file's OWN format string.

    Written as `"%-18s %-22s %s"` rather than with hand-typed spacing so a
    change to the real format breaks these tests instead of quietly making
    them test a grammar nothing emits.
    """
    out = ["%-18s %-22s %s" % (name, flag, summary)
           for name, flag, summary in rows]
    out.append("corpus-check: %d checker(s), %d error(s), %d warning(s)%s"
               % (len(rows), n_err, n_warn,
                  ("; COULD NOT RUN: " + ",".join(broken)) if broken else ""))
    return "\n".join(out) + "\n"


class TestCorpusGrammar(unittest.TestCase):
    """Round 461. The second log grammar, and the two things it forces."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def test_every_flag_shape_the_emitter_can_produce_parses(self):
        cases = [
            ("skill_lint", "ok", ("skill_lint", "ok", None)),
            ("carryforward", "ERROR K001", ("carryforward", "ERROR", "K001")),
            ("unit_tests", "ERROR rc1", ("unit_tests", "ERROR", "rc1")),
            ("state_claim_check", "warn S005",
             ("state_claim_check", "warn", "S005")),
            # 24 characters: WIDER than the %-22s field, so exactly one space
            # separates it from the summary. A column-offset parser reads the
            # summary as the codes here; this is the live shape at round 460.
            ("case_coverage", "warn P004,P006,P007,P009",
             ("case_coverage", "warn", "P004,P006,P007,P009")),
            ("unit_tests", "TIMEOUT", ("unit_tests", "TIMEOUT", None)),
            ("selfdesc_check", "ABSENT", ("selfdesc_check", "ABSENT", None)),
        ]
        for name, flag, want in cases:
            line = "%-18s %-22s %s" % (name, flag, "some summary 1 error(s)")
            self.assertEqual(RA.parse_corpus_row(line), want, line)

    def test_the_aggregate_line_is_not_a_checker_row(self):
        """`corpus-check: 10 checker(s), 2 error(s)` must not parse as a row
        named `corpus` with status `10`. It is the line round 453 anchored
        its own count on, and it is in every log."""
        self.assertIsNone(RA.parse_corpus_row(
            "corpus-check: 10 checker(s), 2 error(s), 7 warning(s)"))
        self.assertIsNone(RA.parse_corpus_row(""))
        self.assertIsNone(RA.parse_corpus_row("FAILED some/test.py::t"))

    def _root(self, per_round):
        logs = {"skills_health_round_%d.log" % r: corpus_log(rows)
                for r, rows in per_round.items()}
        return build_root(self.tmp, ["[t] round %d track=skills(B) start" % r
                                     for r in per_round], logs, BASE_REG)

    def test_an_error_row_becomes_a_red_node_named_for_the_checker(self):
        root = self._root({1: [("skill_lint", "ERROR B001", "x")]})
        self.assertEqual(
            RA.read_logs(root)["skills_health_round"][1],
            frozenset([RA.CORPUS_NODE % "skill_lint"]))

    def test_a_timeout_round_does_not_split_an_episode(self):
        """THE reason `observed_nodes` exists. Rounds 1 and 3 are red and
        round 2 was killed. Treating the kill as a pass reports two
        one-round episodes with two different openers; it is one episode."""
        root = self._root({
            1: [("unit_tests", "ERROR rc1", "2 failed")],
            2: [("unit_tests", "TIMEOUT", "timed out after 600s")],
            3: [("unit_tests", "ERROR rc1", "2 failed")],
            4: [("unit_tests", "ok", "10 passed")],
        })
        res = RA.analyse(root)
        eps = [e for e in res["episodes"]
               if e["node"] == RA.CORPUS_NODE % "unit_tests"]
        self.assertEqual(len(eps), 1)
        self.assertEqual((eps[0]["open"], eps[0]["len"], eps[0]["close"]),
                         (1, 2, 4))
        self.assertEqual(RA.unconclusive_rows(root)["skills_health_round"],
                         {2: ["unit_tests"]})

    def test_a_checker_that_did_not_exist_yet_is_not_a_pass(self):
        """`carryforward` joined at round 369, `selfdesc_check` at 435. A
        checker with no row is unobserved, exactly like a check with no log,
        so it can neither open nor close an episode."""
        root = self._root({
            1: [("skill_lint", "ok", "x")],
            2: [("skill_lint", "ok", "x"), ("carryforward", "ERROR K001", "y")],
            3: [("skill_lint", "ok", "x"), ("carryforward", "ok", "y")],
        })
        res = RA.analyse(root)
        rows = [n for n in res["nodes"]
                if n["node"] == RA.CORPUS_NODE % "carryforward"]
        self.assertEqual(rows[0]["red_rounds"], [2])
        eps = [e for e in res["episodes"] if e["node"] == rows[0]["node"]]
        self.assertEqual([(e["open"], e["close"]) for e in eps], [(2, 3)])

    def test_the_reconciliation_is_a_union_and_never_double_counts(self):
        """Round 455 reconciled with `len(parsed_red) + len(unrunnable & bad)`.
        skills-check round 431 is BOTH -- an `ERROR K001` row and a `TIMEOUT`
        row in the same log -- and the sum counts that round twice. The union
        is what agrees with the driver, and it degenerates to the sum
        whenever the two sets are disjoint, which is why three pytest checks
        never exposed it."""
        logs = {"skills_health_round_1.log": corpus_log(
            [("carryforward", "ERROR K001", "y"),
             ("unit_tests", "TIMEOUT", "timed out after 600s")],
            n_err=1, broken=("unit_tests",))}
        root = build_root(self.tmp,
                          ["[t] round 1 track=skills(B) start",
                           "[t] round 1: skills-check ERROR - a checker could "
                           "not run - x"],
                          logs, BASE_REG)
        rec = RA.analyse(root)["reconciliation"]["skills-check"]
        self.assertEqual(rec["parsed_red_runs"], 1)
        self.assertEqual(rec["unconclusive_runs"], 1)
        self.assertEqual(rec["driver_bad_runs"], 1)
        self.assertEqual(rec["accounted"], 1)      # a sum would say 2
        self.assertTrue(rec["agrees"])


class TestSynthetic(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def test_episodes_are_maximal_runs_of_consecutive_red_runs(self):
        eps = RA.episodes_for("n", [1, 2, 3, 4, 5, 6],
                              {2, 3, 6})
        self.assertEqual([(e["open"], len(e["rounds"]), e["close"]) for e in eps],
                         [(2, 2, 4), (6, 1, None)])

    def test_a_round_the_check_never_ran_cannot_join_two_episodes(self):
        # round 3's log is absent, so 3 is not in the run order at all; the
        # reds at 2 and 4 are ADJACENT RUNS and are one episode. Inventing a
        # green round 3 would split it.
        eps = RA.episodes_for("n", [1, 2, 4, 5], {2, 4})
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0]["open"], 2)
        self.assertEqual(eps[0]["close"], 5)

    def test_node_suite_takes_the_longest_declared_prefix(self):
        self.assertEqual(RA.node_suite("harness/tests/test_x.py::t"), "harness/tests")
        self.assertEqual(RA.node_suite("languages/whence/tests/test_x.py::t"),
                         "languages/whence/tests")
        self.assertEqual(RA.node_suite("nuc/tests/test_x.py::t"), "nuc/tests")
        self.assertIsNone(RA.node_suite("something/else.py::t"))

    def test_whence_node_ids_are_rewritten_to_be_repo_relative(self):
        build_root(self.tmp, ["round 5 track=language(C) start"],
                   {"whence_health_round_5.log": pytest_log("tests/test_a.py::t")},
                   BASE_REG)
        runs = RA.read_logs(self.tmp)
        self.assertEqual(set(runs["whence_health_round"][5]),
                         {"languages/whence/tests/test_a.py::t"})

    def test_a_green_run_is_an_empty_set_and_a_missing_run_is_no_key(self):
        build_root(self.tmp, ["round 5 track=harness(A) start"],
                   {"health_round_5.log": pytest_log()}, BASE_REG)
        runs = RA.read_logs(self.tmp)
        self.assertEqual(runs["health_round"][5], frozenset())
        self.assertNotIn(6, runs["health_round"])

    def test_a_log_with_no_count_line_is_could_not_run_not_green(self):
        build_root(self.tmp, ["round 5 track=language(C) start"],
                   {"whence_health_round_5.log":
                    "ERROR: pyproject.toml: cannot declare twice\n"},
                   BASE_REG)
        self.assertEqual(RA.could_not_run(self.tmp)["whence_health_round"], [5])

    def test_could_not_run_is_never_pointed_at_the_non_pytest_grammar(self):
        # the skills check's logs are a checker/verdict table; the pytest
        # count-line heuristic misfires on all of them, so it must not run.
        self.assertNotIn("skills_health_round", RA.could_not_run(self.tmp))
        self.assertNotIn("skills_health_round", RA.PYTEST_LOGS)

    def test_an_unregistered_red_node_is_R001(self):
        build_root(self.tmp,
                   ["round 5 track=skills(B) start", "round 6 track=language(C) start"],
                   {"health_round_5.log": pytest_log("harness/tests/test_a.py::t"),
                    "health_round_6.log": pytest_log()},
                   BASE_REG)
        res = RA.analyse(self.tmp)
        r001 = [f for f in res["registry_findings"]
                if f[0] == "R001" and f[1] == "harness/tests/test_a.py::t"]
        self.assertEqual(len(r001), 1, res["registry_findings"])
        self.assertIn("went red and has no registry entry", r001[0][2])

    def test_a_registry_entry_for_a_node_that_never_went_red_is_R002(self):
        reg = json.loads(json.dumps(BASE_REG))
        reg["nodes"]["harness/tests/test_ghost.py::t"] = SUBJ("own-suite")
        build_root(self.tmp, ["round 5 track=harness(A) start"],
                   {"health_round_5.log": pytest_log()}, reg)
        codes = [f[0] for f in RA.analyse(self.tmp)["registry_findings"]]
        self.assertIn("R002", codes)

    def test_an_unknown_subject_scope_is_R003(self):
        reg = json.loads(json.dumps(BASE_REG))
        reg["nodes"]["harness/tests/test_a.py::t"] = SUBJ("nonsense")
        build_root(self.tmp,
                   ["round 5 track=skills(B) start", "round 6 track=language(C) start"],
                   {"health_round_5.log": pytest_log("harness/tests/test_a.py::t"),
                    "health_round_6.log": pytest_log()}, reg)
        codes = [f[0] for f in RA.analyse(self.tmp)["registry_findings"]]
        self.assertIn("R003", codes)

    def test_an_episode_opening_on_the_checks_first_ever_run_is_not_attributed(self):
        reg = json.loads(json.dumps(BASE_REG))
        reg["nodes"]["nuc/tests/test_a.py::t"] = SUBJ("own-suite")
        build_root(self.tmp,
                   ["round 5 track=language(C) start", "round 6 track=NUC-integration(E) start"],
                   {"nuc_health_round_5.log": pytest_log("nuc/tests/test_a.py::t"),
                    "nuc_health_round_6.log": pytest_log()}, reg)
        res = RA.analyse(self.tmp)
        ep, = res["episodes"]
        self.assertTrue(ep["born_red"])
        self.assertFalse(ep["opened_by_owner"])
        self.assertFalse(ep["visible_to_opener"])
        self.assertEqual(res["totals"]["attributable"], 0)
        self.assertIsNone(res["totals"]["invisible_open_rate"])

    def test_visibility_is_the_declared_track_suites_relation(self):
        reg = json.loads(json.dumps(BASE_REG))
        reg["nodes"]["harness/tests/test_a.py::t"] = SUBJ("whole-tree")
        # run 5 green so run 6's red is an OPEN, not a born-red install
        build_root(self.tmp,
                   ["round 5 track=harness(A) start",
                    "round 6 track=language(C) start",
                    "round 7 track=SWE-loop(D) start",
                    "round 8 track=harness(A) start"],
                   {"health_round_5.log": pytest_log(),
                    "health_round_6.log": pytest_log("harness/tests/test_a.py::t"),
                    "health_round_7.log": pytest_log(),
                    "health_round_8.log": pytest_log("harness/tests/test_a.py::t")}, reg)
        res = RA.analyse(self.tmp)
        by_open = {e["open"]: e for e in res["episodes"]}
        # language(C) does not run harness/tests -> invisible
        self.assertFalse(by_open[6]["visible_to_opener"])
        # harness(A) does -> visible
        self.assertTrue(by_open[8]["visible_to_opener"])
        self.assertEqual(res["totals"]["invisible_opens"], 1)

    def test_SWE_loop_D_sees_both_the_harness_and_the_whence_suite(self):
        reg = json.loads(json.dumps(BASE_REG))
        reg["nodes"]["harness/tests/test_a.py::t"] = SUBJ("whole-tree")
        build_root(self.tmp,
                   ["round 5 track=harness(A) start", "round 6 track=SWE-loop(D) start"],
                   {"health_round_5.log": pytest_log(),
                    "health_round_6.log": pytest_log("harness/tests/test_a.py::t")}, reg)
        ep = [e for e in RA.analyse(self.tmp)["episodes"] if e["open"] == 6][0]
        self.assertTrue(ep["visible_to_opener"])
        self.assertFalse(ep["opened_by_owner"])   # D is not the OWNER of harness/tests

    def test_a_check_that_fails_in_driver_log_but_yields_no_nodes_is_a_grammar_gap(self):
        build_root(self.tmp,
                   ["round 5 track=harness(A) start",
                    "[t] round 5: skills-check FAIL - something"],
                   {"skills_health_round_5.log": "skill_lint ERROR B002\n"}, BASE_REG)
        gaps = RA.analyse(self.tmp)["grammar_gaps"]
        self.assertEqual(len(gaps), 1)
        self.assertIn("skills-check", gaps[0])
        self.assertIn("recovered 0 test node(s)", gaps[0])


class TestEvidenceKind(unittest.TestCase):
    """Round 467. WHAT DECIDED THE LABEL the headline is computed over."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def _one_red(self, entry):
        reg = json.loads(json.dumps(BASE_REG))
        reg["nodes"]["harness/tests/test_a.py::t"] = entry
        build_root(self.tmp,
                   ["round 5 track=harness(A) start",
                    "round 6 track=language(C) start",
                    "round 7 track=SWE-loop(D) start"],
                   {"health_round_5.log": pytest_log(),
                    "health_round_6.log": pytest_log("harness/tests/test_a.py::t"),
                    "health_round_7.log": pytest_log()}, reg)
        return RA.analyse(self.tmp)

    def test_an_entry_with_no_evidence_kind_is_R005(self):
        res = self._one_red({"subject_scope": "whole-tree", "why": ""})
        self.assertIn("R005", [f[0] for f in res["registry_findings"]])

    def test_an_unknown_evidence_kind_is_R005(self):
        res = self._one_red({"subject_scope": "whole-tree", "evidence": "vibes"})
        f, = [x for x in res["registry_findings"] if x[0] == "R005"]
        self.assertIn("vibes", f[2])

    def test_an_outcome_label_outside_environmental_is_R006(self):
        """The circularity this field exists to make checkable: a scope read
        off the verdict history is not admissible evidence for an association
        computed over those same verdicts, UNLESS the scope is the one that is
        about verdicts."""
        res = self._one_red({"subject_scope": "whole-tree", "evidence": "outcome"})
        self.assertIn("R006", [f[0] for f in res["registry_findings"]])

    def test_environmental_declared_subject_derived_is_ALSO_R006(self):
        """The other direction, and it is not symmetry for its own sake:
        nothing about a subject can tell you a test is a clock flake, so an
        `environmental` entry claiming subject evidence has not done the
        work."""
        res = self._one_red({"subject_scope": "environmental", "evidence": "subject"})
        self.assertIn("R006", [f[0] for f in res["registry_findings"]])

    def test_the_two_legitimate_pairings_are_clean(self):
        for scope, ev in (("whole-tree", "subject"), ("environmental", "outcome")):
            res = self._one_red({"subject_scope": scope, "evidence": ev})
            self.assertEqual(
                [f for f in res["registry_findings"] if f[0] in ("R005", "R006")],
                [], "%s/%s" % (scope, ev))

    def test_scope_test_drops_outcome_derived_episodes(self):
        res = self._one_red({"subject_scope": "environmental", "evidence": "outcome"})
        eps = RA.scope_test_episodes(res, BASE_REG["_track_suites"])
        self.assertEqual(eps, [])
        self.assertEqual(res["totals"]["attributable"], 1)


class TestOneRoundLag(unittest.TestCase):
    """Round 461's next-step 2. A fail-closed check cannot fire in the round
    that breaks it, and until now its own message did not say so."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def _tree(self, registry):
        return build_root(
            self.tmp,
            ["round 5 track=harness(A) start",
             "round 6 track=language(C) start",
             "round 7 track=SWE-loop(D) start"],
            {"health_round_5.log": pytest_log(),
             "health_round_6.log": pytest_log("harness/tests/test_a.py::t"),
             "health_round_7.log": pytest_log("harness/tests/test_a.py::t")},
            registry)

    def test_the_R001_message_names_the_opener_and_the_first_run_that_could_see_it(self):
        self._tree(json.loads(json.dumps(BASE_REG)))
        res = RA.analyse(self.tmp)
        f, = [x for x in res["registry_findings"] if x[0] == "R001"]
        self.assertIn("round 6's log", f[2])
        self.assertIn("language(C)", f[2])
        self.assertIn("round 7", f[2])
        self.assertIn("not the round that caused it", f[2])

    def test_first_firable_is_none_when_no_later_run_exists(self):
        """The state a round's own breakage is in while its check is still
        being written: nothing has been able to see it yet, and reporting a
        number there would invent a reader."""
        reg = json.loads(json.dumps(BASE_REG))
        reg["nodes"]["harness/tests/test_a.py::t"] = SUBJ("whole-tree")
        build_root(self.tmp,
                   ["round 5 track=harness(A) start",
                    "round 6 track=language(C) start"],
                   {"health_round_5.log": pytest_log(),
                    "health_round_6.log": pytest_log("harness/tests/test_a.py::t")},
                   reg)
        ep, = RA.analyse(self.tmp)["episodes"]
        self.assertEqual(ep["opened_by_log_round"], 6)
        self.assertIsNone(ep["first_firable_round"])

    def test_the_lag_is_at_least_one_round_whenever_a_later_run_exists(self):
        reg = json.loads(json.dumps(BASE_REG))
        reg["nodes"]["harness/tests/test_a.py::t"] = SUBJ("whole-tree")
        self._tree(reg)
        ep, = RA.analyse(self.tmp)["episodes"]
        self.assertEqual(ep["opened_by_log_round"], 6)
        self.assertEqual(ep["first_firable_round"], 7)


class TestScopeTestInference(unittest.TestCase):
    """Round 467. Round 461's next-step 6: `p = 9.81e-08` had no producer in
    the tree and no correction for the two clusterings it sits on."""

    def _eps(self, spec):
        """spec: [(node, suite, scope, open_round, visible)] -> episode dicts."""
        return [{"node": n, "suite": su, "scope": sc, "open": o, "vis": v}
                for n, su, sc, o, v in spec]

    def test_fisher_reproduces_a_hand_computable_table(self):
        # [[3,1],[1,3]]: the two-sided exact p is 2*(C(4,3)C(4,1)+C(4,4)C(4,0))
        # / C(8,4) = 2*(16+1)/70.
        self.assertAlmostEqual(RA.fisher_exact_2x2(3, 1, 1, 3), 34 / 70, places=12)

    def test_a_table_with_no_association_is_p_one(self):
        self.assertAlmostEqual(RA.fisher_exact_2x2(2, 2, 2, 2), 1.0, places=12)

    def test_the_published_p_values_are_reproduced(self):
        """Rounds 455 and 461 published 0.0036 and 9.81e-08 from scratch
        calculations that left nothing behind. Until this passes, no number
        `scope-test` prints is worth reading."""
        for label, a, b, c, d, published in RA.PUBLISHED_TABLES:
            got = RA.fisher_exact_2x2(a, b, c, d)
            self.assertAlmostEqual(got, published,
                                   delta=0.005 * published + 5e-5,
                                   msg="%s: recomputed %r" % (label, got))

    def test_the_rotation_is_read_from_the_record_not_from_claude_md(self):
        tracks = {r: ("A" if r % 6 == 1 else "X") for r in range(100, 200)}
        rot, problems = RA.rotation_residue_map(tracks)
        self.assertEqual(problems, [])
        self.assertEqual(rot[1], "A")
        self.assertEqual(len(rot), 6)

    def test_a_rotation_that_is_not_rigid_complains_instead_of_averaging(self):
        tracks = {r: ("A" if r % 6 == 1 else "X") for r in range(100, 200)}
        tracks[121] = "Q"                       # residue 1 ran two tracks
        _rot, problems = RA.rotation_residue_map(tracks)
        self.assertTrue(any("residue 1" in p for p in problems), problems)

    def test_the_shift_null_has_exactly_one_member_per_residue(self):
        tracks = {r: "T%d" % (r % 6) for r in range(100, 200)}
        suites = {"T%d" % i: (["harness/tests"] if i == 1 else []) for i in range(6)}
        eps = self._eps([("n%d" % r, "harness/tests", "whole-tree", r,
                          tracks[r] == "T1") for r in range(100, 130)]
                        + [("m", "harness/tests", "own-suite", 101, True)])
        out = RA.rotation_shift_null(eps, tracks, suites)
        self.assertEqual(out["shifts"], 6)
        self.assertEqual(out["distinct_relabelings"], 6)
        self.assertAlmostEqual(out["floor"], 1 / 6)
        self.assertGreaterEqual(out["p"], 1 / 6)

    def test_a_gap_in_the_driver_log_does_not_change_the_null_size(self):
        """THE REGRESSION PIN FOR THIS ROUND'S OWN BUG.

        The first draft rotated the observed label SEQUENCE by position.
        `logs/driver.log` has no `start` line for rounds 229 and 313, so a
        positional rotation slides labels across the holes, changes phase, and
        stops being a symmetry of `track = f(round mod 6)`: it reported 188
        distinct relabelings of 314 shifts where the truth is 6. Shifting the
        RESIDUE is invariant to holes, and this pins that -- the assertion is
        on the SAME number with and without the gaps.
        """
        full = {r: "T%d" % (r % 6) for r in range(100, 200)}
        gapped = {r: t for r, t in full.items() if r not in (137, 168)}
        suites = {"T%d" % i: (["harness/tests"] if i == 1 else []) for i in range(6)}
        spec = [("n%d" % r, "harness/tests", "whole-tree", r, full[r] == "T1")
                for r in sorted(gapped)]
        eps = self._eps(spec + [("m", "harness/tests", "own-suite", 101, True)])
        a = RA.rotation_shift_null(eps, full, suites)
        b = RA.rotation_shift_null(eps, gapped, suites)
        self.assertEqual(a["distinct_relabelings"], b["distinct_relabelings"], 6)
        self.assertEqual(a["p"], b["p"])
        # ...and the positional rotation this replaced does NOT survive a gap.
        rounds = sorted(gapped)
        labels = [gapped[r] for r in rounds]
        positional = {tuple(labels[(i + k) % len(rounds)] for i in range(len(rounds)))
                      for k in range(len(rounds))}
        self.assertGreater(len(positional), 6)

    def test_the_shift_null_moves_only_the_track_labels(self):
        """Every structural fact must survive the null: the episode count, the
        scopes, and each round's set of opened episodes."""
        tracks = {r: "T%d" % (r % 6) for r in range(100, 130)}
        suites = {"T1": ["harness/tests"]}
        eps = self._eps([("a", "harness/tests", "whole-tree", 101, True),
                         ("b", "harness/tests", "whole-tree", 102, False),
                         ("c", "harness/tests", "own-suite", 103, False)])
        before = [(e["node"], e["scope"], e["open"]) for e in eps]
        RA.rotation_shift_null(eps, tracks, suites)
        self.assertEqual([(e["node"], e["scope"], e["open"]) for e in eps], before)

    def test_collapsing_by_node_refuses_to_count_one_node_many_times(self):
        eps = self._eps([("hot", "skills", "whole-tree", r, False)
                         for r in range(400, 427)]
                        + [("cold", "harness/tests", "own-suite", 401, True)])
        table, rows = RA.collapse_by_node(eps)
        self.assertEqual(len(rows), 2)
        self.assertEqual(table, (1, 0, 0, 1))

    def test_the_node_permutation_null_keeps_every_nodes_episode_count(self):
        eps = self._eps([("hot", "skills", "whole-tree", r, False)
                         for r in range(400, 410)]
                        + [("cold", "harness/tests", "own-suite", 401, True)])
        out = RA.node_scope_null(eps, draws=200, seed=1)
        self.assertEqual(out["nodes"], 2)
        self.assertEqual(out["draws"], 200)
        self.assertLessEqual(out["p"], 1.0)

    def test_the_node_permutation_null_is_seeded_and_reproducible(self):
        eps = self._eps([("a", "skills", "whole-tree", 401, False),
                         ("b", "skills", "whole-tree", 402, False),
                         ("c", "harness/tests", "own-suite", 403, True)])
        self.assertEqual(RA.node_scope_null(eps, draws=500, seed=9),
                         RA.node_scope_null(eps, draws=500, seed=9))

    def test_the_one_row_statistic_ignores_every_other_scope(self):
        eps = self._eps([("a", "skills", "whole-tree", 1, False),
                         ("b", "skills", "whole-tree", 2, True),
                         ("c", "skills", "own-suite", 3, False),
                         ("d", "skills", "shared-corpus", 4, False)])
        self.assertAlmostEqual(RA.whole_tree_invisible_rate(eps), 0.5)

    def test_an_empty_row_yields_no_statistic_rather_than_a_zero(self):
        eps = self._eps([("a", "skills", "whole-tree", 1, False)])
        self.assertIsNone(RA._stat(RA._table(eps)))
        self.assertIsNone(RA.whole_tree_invisible_rate(eps, scope="own-suite"))

class TestThisTree(unittest.TestCase):
    def setUp(self):
        """Round 467. A checkout with no evidence base cannot fail these.

        `logs/*_round_*.log` is gitignored, so a fresh clone or a
        `git worktree add HEAD --detach` sees ~0 of the 602 logs these
        assertions read. Round 461 measured what happens then: 4 failed,
        15 passed where the truth was 2 failed, 17 passed -- two of the four
        caused purely by the absence. A red that means `you have no data` must
        not look like a red that means `the tree is broken`, so it skips WITH
        THE REASON. The floor is far above a fresh clone and far below the
        live tree, so this can never silence a real failure here.
        """
        n, enough = RA.evidence_base(ROOT)
        if not enough:
            raise unittest.SkipTest(
                "this checkout holds %d per-round log(s), below the floor of "
                "%d -- `logs/*_round_*.log` is gitignored (.gitignore 28, 29, "
                "35, 60), so these whole-tree assertions have no evidence to "
                "read. Not a failure of the tree." % (n, RA.MIN_EVIDENCE_LOGS))

    def test_the_registry_is_fail_closed_over_the_live_logs(self):
        res = RA.analyse(ROOT)
        self.assertEqual(res["registry_findings"], [],
                         "every node that has ever gone red must be classified")

    def test_the_cli_audit_exits_zero_on_this_tree(self):
        p = subprocess.run([sys.executable,
                            os.path.join(ROOT, "harness", "redattrib.py"), "audit"],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_every_opener_track_has_a_declared_suite_list(self):
        res = RA.analyse(ROOT)
        self.assertEqual([f for f in res["registry_findings"] if f[0] == "R004"], [])

    def test_the_parser_agrees_with_the_drivers_own_verdict_count(self):
        """A cross-check on the parse, not on the repo, for ALL FOUR checks.

        Round 455 ran this over the three pytest-grammar checks only and did
        the arithmetic here in the test. Round 461 moved it into `analyse`
        (`reconciliation`), so the CLI prints the same cross-check it is
        tested on, widened it to `skills-check`, and changed the addition to
        a set union -- see `test_the_reconciliation_is_a_union_and_never_
        double_counts` for the round that breaks the sum.

        Every round the driver called FAIL or ERROR must be a round in which
        this parser either found a red node or found something that could
        not report, and there must be no such round left over on either side.
        """
        res = RA.analyse(ROOT)
        for label, v in res["reconciliation"].items():
            self.assertTrue(
                v["agrees"],
                "%s: %d red run(s) + %d unconclusive account for %d of the "
                "driver's %d FAIL/ERROR run(s); unexplained rounds %s"
                % (label, v["parsed_red_runs"], v["unconclusive_runs"],
                   v["accounted"], v["driver_bad_runs"], v["unexplained"]))

    def test_the_fourth_check_is_represented_and_reports_no_grammar_gap(self):
        """Round 455's own GRAMMAR GAP line, closed. It said skills-check was
        `NOT represented in any number below`; the headline was over three
        checks while claiming four."""
        res = RA.analyse(ROOT)
        self.assertEqual(res["grammar_gaps"], [])
        self.assertGreater(res["per_check"]["skills-check"]["nodes_ever_red"], 0)
        self.assertGreater(res["per_check"]["skills-check"]["episodes"], 0)

    def test_every_corpus_node_names_a_file_that_exists(self):
        """The pseudo node id is `<path>::<checker>`; the path half must
        resolve, or the id is a label rather than a pointer."""
        res = RA.analyse(ROOT)
        for n in res["nodes"]:
            if n["suite"] == "skills":
                path = n["node"].split("::")[0]
                self.assertTrue(os.path.exists(os.path.join(ROOT, path)),
                                "%s does not exist" % path)

    def test_round_453s_check_level_measurement_is_reproduced_exactly(self):
        """Round 453 (skills B) measured the skills corpus over rounds
        364-452 by anchoring on each log's `corpus-check:` aggregate line and
        reading `N error(s)`. This module anchors on the per-row `ERROR`
        flags instead -- a different derivation of the same quantity from the
        same files -- and must land on the same numbers.

        History does not change, so this is a stable pin: if it breaks,
        either a retained log was edited or the parse did.
        """
        runs = RA.read_logs(ROOT)["skills_health_round"]
        window = [r for r in sorted(runs) if 364 <= r <= 452]
        red = {r for r in window if runs[r]}
        self.assertEqual((len(window), len(red)), (89, 24))
        eps = RA.episodes_for("any", window, red)
        self.assertEqual(len(eps), 16)
        self.assertEqual(max(len(e["rounds"]) for e in eps), 4)
        tracks = RA.round_tracks(ROOT)
        opened = collections.Counter(tracks.get(e["open"]) for e in eps)
        self.assertEqual(dict(opened), {"language(C)": 7, "SWE-loop(D)": 6,
                                        "harness(A)": 2,
                                        "NUC-integration(E)": 1})
        self.assertEqual(opened["skills(B)"], 0,
                         "round 453's headline: zero episodes opened by the "
                         "track that owns the checkers")

    def test_no_skills_check_episode_was_opened_by_the_track_that_owns_it(self):
        """Round 453's finding at the finer granularity this module added.
        Stated as a direction, not a count, so a new round does not break
        it -- but a skills(B) round opening one WOULD, and should."""
        res = RA.analyse(ROOT)
        v = res["per_check"]["skills-check"]
        self.assertEqual(v["opened_by_owner"], 0)
        self.assertEqual(v["invisible_opens"], v["attributable"])

    def test_the_headline_association_is_reproducible(self):
        """whole-tree reds are opened by rounds that cannot see them; own-suite
        reds are not. This pins the DIRECTION, not the exact counts, so the
        test does not go red merely because the tree gained a round."""
        res = RA.analyse(ROOT)
        sv = res["scope_by_visibility"]
        wt, os_ = sv["whole-tree"], sv["own-suite"]
        wt_rate = wt["invisible"] / (wt["invisible"] + wt["visible"])
        os_rate = os_["invisible"] / (os_["invisible"] + os_["visible"])
        self.assertGreater(wt_rate, os_rate)
        self.assertGreater(wt["invisible"], 0)


    # ---- round 467 ------------------------------------------------------
    def test_every_registry_entry_says_what_decided_its_scope(self):
        """R005/R006 over the live registry. The invisible-open rate is
        computed over these labels, so `what decided this one` has to be
        answerable for every row before the rate means anything."""
        res = RA.analyse(ROOT)
        self.assertEqual([f for f in res["registry_findings"]
                          if f[0] in ("R005", "R006")], [])

    def test_the_association_is_never_computed_over_an_outcome_derived_label(self):
        res = RA.analyse(ROOT)
        eps = RA.scope_test_episodes(res, RA.load_registry(ROOT)["_track_suites"])
        self.assertTrue(eps)
        self.assertEqual([e for e in eps if e["scope"] == "environmental"], [])

    def test_the_rotation_in_the_record_is_still_rigid(self):
        """`rotation_shift_null` is only a shape-preserving null while the
        driver really does pick the track by round mod 6. If a round ever
        deviates, the null stops being a symmetry and this says so BEFORE the
        p-value is quoted."""
        rot, problems = RA.rotation_residue_map(RA.round_tracks(ROOT))
        self.assertEqual(problems, [])
        self.assertEqual(len(rot), RA.ROTATION_PERIOD)

    def test_the_shift_null_over_this_tree_has_six_members_and_a_floor(self):
        r = RA.scope_test(ROOT, draws=200)
        sh = r["rotation_shift_null"]
        self.assertEqual(sh["distinct_relabelings"], RA.ROTATION_PERIOD)
        self.assertAlmostEqual(sh["floor"], 1 / RA.ROTATION_PERIOD)
        self.assertGreaterEqual(sh["p"], sh["floor"] - 1e-12)

    def test_the_naive_p_is_the_most_extreme_of_the_five_readings(self):
        """The finding stated as a test: every correction for the clustering
        or for the rotation makes the number LARGER, so the published figure
        is the ceiling of the evidence, not its centre."""
        r = RA.scope_test(ROOT, draws=2000)
        naive = r["episode_p_naive"]
        for key in ("node_p",):
            self.assertGreater(r[key], naive)
        self.assertGreater(r["rotation_shift_null"]["p"], naive)
        self.assertGreater(r["whole_tree_only_shift_null"]["p"], naive)

    def test_every_attributable_episode_carries_its_one_round_lag(self):
        res = RA.analyse(ROOT)
        for e in res["episodes"]:
            self.assertEqual(e["opened_by_log_round"], e["open"])
            if e["first_firable_round"] is not None:
                self.assertGreater(e["first_firable_round"], e["open"])

    def test_the_scope_test_cli_runs_on_this_tree(self):
        p = subprocess.run([sys.executable,
                            os.path.join(ROOT, "harness", "redattrib.py"),
                            "scope-test", "--draws", "500"],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("rotation-shift null", p.stdout)
        self.assertIn("agree", p.stdout)


    def test_the_evidence_base_is_present_and_the_module_says_where(self):
        """The positive control for setUp. If this ever SKIPS, the skip is the
        finding: the tree that this program runs in has lost its own record."""
        n, enough = RA.evidence_base(ROOT)
        self.assertTrue(enough, n)
        self.assertIn("NOT IN GIT", RA.__doc__)

    def test_an_empty_checkout_is_reported_as_no_evidence_rather_than_as_green(self):
        import tempfile
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "logs"))
        os.makedirs(os.path.join(tmp, "harness"))
        with open(os.path.join(tmp, RA.REGISTRY_NAME), "w") as fh:
            json.dump(BASE_REG, fh)
        n, enough = RA.evidence_base(tmp)
        self.assertEqual(n, 0)
        self.assertFalse(enough)
        res = RA.analyse(tmp)
        self.assertEqual(res["totals"]["episodes"], 0)
        self.assertIsNone(res["totals"]["invisible_open_rate"])


if __name__ == "__main__":
    unittest.main()

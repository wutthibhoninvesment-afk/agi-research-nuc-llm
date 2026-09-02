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
                       "shared-file-own-content": ""},
    "_track_suites": {"harness(A)": ["harness/tests"],
                      "language(C)": ["languages/whence/tests"],
                      "skills(B)": ["skills"],
                      "SWE-loop(D)": ["harness/tests", "languages/whence/tests"],
                      "NUC-integration(E)": ["nuc/tests"]},
    "nodes": {},
}


def pytest_log(*failed):
    body = "".join("FAILED %s\n" % f for f in failed)
    if failed:
        return body + "%d failed, 10 passed in 1.00s\n" % len(failed)
    return body + "10 passed in 1.00s\n"


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
        self.assertIn(("R001", "harness/tests/test_a.py::t",
                       "went red and has no registry entry"), res["registry_findings"])

    def test_a_registry_entry_for_a_node_that_never_went_red_is_R002(self):
        reg = json.loads(json.dumps(BASE_REG))
        reg["nodes"]["harness/tests/test_ghost.py::t"] = {"subject_scope": "own-suite"}
        build_root(self.tmp, ["round 5 track=harness(A) start"],
                   {"health_round_5.log": pytest_log()}, reg)
        codes = [f[0] for f in RA.analyse(self.tmp)["registry_findings"]]
        self.assertIn("R002", codes)

    def test_an_unknown_subject_scope_is_R003(self):
        reg = json.loads(json.dumps(BASE_REG))
        reg["nodes"]["harness/tests/test_a.py::t"] = {"subject_scope": "nonsense"}
        build_root(self.tmp,
                   ["round 5 track=skills(B) start", "round 6 track=language(C) start"],
                   {"health_round_5.log": pytest_log("harness/tests/test_a.py::t"),
                    "health_round_6.log": pytest_log()}, reg)
        codes = [f[0] for f in RA.analyse(self.tmp)["registry_findings"]]
        self.assertIn("R003", codes)

    def test_an_episode_opening_on_the_checks_first_ever_run_is_not_attributed(self):
        reg = json.loads(json.dumps(BASE_REG))
        reg["nodes"]["nuc/tests/test_a.py::t"] = {"subject_scope": "own-suite"}
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
        reg["nodes"]["harness/tests/test_a.py::t"] = {"subject_scope": "whole-tree"}
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
        reg["nodes"]["harness/tests/test_a.py::t"] = {"subject_scope": "whole-tree"}
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


class TestThisTree(unittest.TestCase):
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
        """A cross-check on the parse, not on the repo.

        For each pytest-grammar check, the number of runs this module found
        red nodes in must equal the number of FAIL runs run_driver.sh
        recorded, EXCEPT for runs whose suite could not run at all -- those
        the driver calls FAIL or ERROR while the log holds no FAILED line.
        """
        res = RA.analyse(ROOT)
        runs = RA.read_logs(ROOT)
        cnr = RA.could_not_run(ROOT)
        for prefix in RA.PYTEST_LOGS:
            label = RA.CHECK_LABEL[prefix]
            suite = RA.CHECKS[prefix][1]
            parsed_red = {r for r, nodes in runs[prefix].items()
                          if any(RA.node_suite(n) == suite for n in nodes)}
            dv = res["driver_verdicts"][label]
            unrunnable = set(cnr[prefix])
            self.assertEqual(
                len(parsed_red) + len(unrunnable & self._driver_bad(label)),
                dv.get("FAIL", 0) + dv.get("ERROR", 0),
                "%s: parsed %d red run(s), driver recorded %d FAIL + %d ERROR"
                % (label, len(parsed_red), dv.get("FAIL", 0), dv.get("ERROR", 0)))

    @staticmethod
    def _driver_bad(label):
        import re
        bad = set()
        with open(os.path.join(ROOT, "logs", "driver.log"),
                  encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = re.search(r"round (\d+): %s (FAIL|ERROR)" % re.escape(label), line)
                if m:
                    bad.add(int(m.group(1)))
        return bad

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


if __name__ == "__main__":
    unittest.main()

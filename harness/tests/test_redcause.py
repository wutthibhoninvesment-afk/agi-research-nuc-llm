"""Tests for harness/redcause.py (round 511, harness A).

Three kinds, and the split matters more here than in most files.

`TestParser` and `TestGraph` build synthetic health logs under `tmp_path`
and pin the mechanics -- block splitting, title resolution, the `:` trap in
the node-reference regex, the same-log/cross-log axis, the refusal to promote
an unreadable body to PRIMARY.

`TestRetainedCorpus` pins facts about the ALREADY-RETAINED per-round logs,
rounds 410 through 510. Every assertion is bounded above by round 510 on
purpose. A live assertion over "the newest log" is exactly the construct this
module exists to measure -- a whole-tree fail-closed gate hosted in one
track's suite, which any track can redden and only harness(A) routinely runs
-- and shipping one here would make this file the ninth instance of the
series. The past cannot move; the future is measured by `graph` and reported,
not asserted.

`TestCLI` runs the four subcommands as subprocesses against the live tree.
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
import redcause as RC  # noqa: E402

#: Everything TestRetainedCorpus asserts about is at or below this round.
#: See the module docstring.
PINNED_THROUGH = 510

AUDIT_NODE = ("harness/tests/test_redattrib.py::TestThisTree"
              "::test_the_cli_audit_exits_zero_on_this_tree")
FAILCLOSED_NODE = ("harness/tests/test_redattrib.py::TestThisTree"
                   "::test_the_registry_is_fail_closed_over_the_live_logs")
NUC_AGG_NODE = ("nuc/tests/test_constant_audit.py"
                "::test_the_fast_check_runs_green_on_this_tree")

#: The CLI as literal argv, the same reason `test_readset.py` writes its own
#: out: `harness/verb_audit.py` reads SOURCE for an entry-point token followed
#: by a verb, and it cannot see a path assembled by `os.path.join`. TestCLI
#: runs exactly these lists from ROOT, so the token the audit reads and the
#: command that runs are one string. Without them all four verbs report V003
#: -- "declares 4 verb(s); NONE is invoked anywhere in the closure" -- while
#: every one of them is in fact invoked by the tests below.
GRAPH_ARGV = ["harness/redcause.py", "graph", "--json"]
NODE_ARGV = ["harness/redcause.py", "node"]
LIVE_ARGV = ["harness/redcause.py", "live", "--json"]
CHECK_ARGV = ["harness/redcause.py", "check"]


def log_text(failed, bodies, tail="1 failed, 2 passed in 1.00s"):
    """A minimal but real pytest -q log: progress, FAILURES, summary, count.

    `bodies` is {block title: body text}. Written the way pytest's
    `TerminalWriter.sep` writes it, one fill char minimum on each side.
    """
    out = [".F", "", "=================================== FAILURES "
                    "==================================="]
    for title, body in bodies.items():
        out.append("_______ %s _______" % title)
        out.append("")
        out.append(body)
        out.append("")
    out.append("=========================== short test summary info "
               "============================")
    for nid in failed:
        out.append("FAILED %s" % nid)
    out.append(tail)
    return "\n".join(out) + "\n"


def build_root(tmp, logs, driver_lines=()):
    logdir = os.path.join(tmp, "logs")
    os.makedirs(logdir, exist_ok=True)
    with open(os.path.join(logdir, "driver.log"), "w") as fh:
        fh.write("\n".join(driver_lines) + "\n")
    for name, text in logs.items():
        with open(os.path.join(logdir, name), "w") as fh:
            fh.write(text)
    return tmp


class TestParser(unittest.TestCase):
    def test_a_failures_region_ends_at_the_next_banner_of_any_kind(self):
        text = log_text(["harness/tests/t.py::test_a"],
                        {"test_a": "E   boom"})
        text += ("=============================== warnings summary "
                 "===============================\n"
                 "_______ test_b _______\nnot a failure block\n")
        titles = [t for t, _b in RC.blocks(text)]
        self.assertEqual(titles, ["test_a"])

    def test_an_errors_section_is_parsed_as_well_as_a_failures_one(self):
        text = ("==== ERRORS ====\n"
                "_ ERROR at setup of test_z _\n"
                "E   fixture missing\n"
                "==== short test summary info ====\n"
                "ERROR harness/tests/t.py::test_z\n"
                "1 error in 1.00s\n")
        self.assertEqual([t for t, _b in RC.blocks(text)],
                         ["ERROR at setup of test_z"])

    def test_a_class_hosted_node_id_maps_to_the_dotted_title_pytest_writes(self):
        self.assertEqual(
            RC.title_for("harness/tests/t.py::TestX::test_y"), "TestX.test_y")
        self.assertEqual(RC.title_for("harness/tests/t.py::test_y"), "test_y")

    def test_a_title_claimed_by_two_failed_nodes_resolves_to_neither(self):
        """An ambiguous body is not evidence about either node."""
        text = log_text(["harness/tests/a.py::TestX::test_y",
                         "harness/tests/b.py::TestX::test_y"],
                        {"TestX.test_y": "E   boom"})
        got, unres = RC.resolve_blocks(
            text, {"harness/tests/a.py::TestX::test_y",
                   "harness/tests/b.py::TestX::test_y"})
        self.assertEqual(got, {})
        self.assertEqual(unres, ["TestX.test_y"])

    def test_a_long_title_still_carries_one_fill_char_on_each_side(self):
        """pytest's `sep` clamps the fill to >=1 rather than truncating, so a
        node name longer than the terminal width is still a parsable header.
        Guessing otherwise would have made every long-named node UNRESOLVED."""
        long = "test_" + "x" * 120
        text = "==== FAILURES ====\n_ %s _\nE   boom\n==== warnings ====\n" % long
        self.assertEqual([t for t, _b in RC.blocks(text)], [long])

    def test_the_frame_line_pytest_prints_is_not_a_node_reference(self):
        """`harness/redattrib.py:602: AssertionError` has one colon, and the
        whole point of requiring `::` is that a body is full of these."""
        self.assertEqual(
            RC.NODEREF.findall("harness/redattrib.py:602: AssertionError"), [])

    def test_a_node_id_followed_by_a_colon_does_not_swallow_the_colon(self):
        """THE REGRESSION THIS FILE EXISTS FOR. R001's message is
        `<nodeid>: went red and has no registry entry`. The first cut of
        NODEREF put `:` in the id character class so that `File::Class::method`
        would match, which made every R001 reference come out one character
        long, resolve to nothing, and report the node PRIMARY -- in all 16 of
        `test_the_cli_audit_exits_zero_on_this_tree`'s red rounds, while its
        file-sibling was DERIVED in all 16 from the same five findings because
        unittest prints them quoted."""
        body = ("E  AssertionError: 1 != 0 : R001  skills/skill-authoring/"
                "scripts/corpus_check.py::selfdesc_check: went red and has no "
                "registry entry -- FIRST RED in round 493's log (harness(A))")
        self.assertIn(
            "skills/skill-authoring/scripts/corpus_check.py::selfdesc_check",
            RC.NODEREF.findall(body))

    def test_a_trailing_sentence_period_is_stripped_and_a_param_bracket_is_not(self):
        known = {"harness/tests/t.py::test_a", "harness/tests/t.py::test_b[1.5]"}
        red, unred, _d = RC.named_in(
            "see harness/tests/t.py::test_a. and harness/tests/t.py::test_b[1.5]",
            "harness/tests/self.py::test_self", ".", known)
        self.assertEqual(red, sorted(known))
        self.assertEqual(unred, [])

    def test_a_named_node_that_never_went_red_is_counted_and_not_promoted(self):
        red, unred, _d = RC.named_in(
            "harness/tests/t.py::test_never_red",
            "harness/tests/self.py::test_self", ".", {"harness/tests/t.py::test_a"})
        self.assertEqual(red, [])
        self.assertEqual(unred, ["harness/tests/t.py::test_never_red"])

    def test_a_body_naming_only_itself_names_nothing(self):
        red, _u, _d = RC.named_in(
            "harness/tests/self.py::test_self failed",
            "harness/tests/self.py::test_self", ".",
            {"harness/tests/self.py::test_self"})
        self.assertEqual(red, [])

    def test_a_whence_relative_reference_canonicalises_against_the_check_root(self):
        known = {"languages/whence/tests/t.py::test_a"}
        self.assertEqual(
            RC.canonicalise("tests/t.py::test_a", "languages/whence", known),
            "languages/whence/tests/t.py::test_a")
        self.assertEqual(
            RC.canonicalise("languages/whence/tests/t.py::test_a",
                            "languages/whence", known),
            "languages/whence/tests/t.py::test_a")
        self.assertIsNone(RC.canonicalise("tests/t.py::test_zz",
                                          "languages/whence", known))

    def test_r001s_dated_edge_yields_the_causing_round_and_track(self):
        body = "R001  harness/tests/t.py::test_a: " + RA._r001_message(
            509, "SWE-loop(D)", 510)
        _r, _u, dated = RC.named_in(body, "harness/tests/self.py::test_self",
                                    ".", {"harness/tests/t.py::test_a"})
        self.assertEqual(dated, [("harness/tests/t.py::test_a", 509,
                                  "SWE-loop(D)")])


class TestGraph(unittest.TestCase):
    def _root(self, tmp, logs, driver_lines=()):
        return build_root(tmp, logs, driver_lines)

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_body_naming_a_node_red_in_the_same_log_is_same_log_derived(self):
        text = log_text(["harness/tests/a.py::test_meta",
                         "harness/tests/b.py::test_leaf"],
                        {"test_meta": "E  nested run failed: FAILED "
                                      "harness/tests/b.py::test_leaf",
                         "test_leaf": "E  assert 1 == 2"})
        self._root(self.tmp, {"health_round_100.log": text},
                   ["round 100 track=harness(A) start"])
        rows = {r["node"]: r for r in RC.observations(self.tmp)}
        self.assertEqual(rows["harness/tests/a.py::test_meta"]["kind"],
                         RC.DERIVED)
        self.assertEqual(rows["harness/tests/a.py::test_meta"]["span"],
                         RC.SAME_LOG)
        self.assertEqual(rows["harness/tests/b.py::test_leaf"]["kind"],
                         RC.PRIMARY)
        self.assertIsNone(rows["harness/tests/b.py::test_leaf"]["span"])

    def test_a_body_naming_a_node_red_only_in_an_earlier_log_is_cross_log(self):
        """The pathological shape: the cause has CLOSED and the host is still
        red, so the host's red is the only surviving trace."""
        first = log_text(["harness/tests/b.py::test_leaf"],
                         {"test_leaf": "E  assert 1 == 2"})
        later = log_text(["harness/tests/a.py::test_meta"],
                         {"test_meta": "E  R001  harness/tests/b.py::test_leaf: "
                                       + RA._r001_message(100, "language(C)",
                                                          101)})
        self._root(self.tmp, {"health_round_100.log": first,
                              "health_round_101.log": later},
                   ["round 100 track=language(C) start",
                    "round 101 track=harness(A) start"])
        rows = {(r["round"], r["node"]): r for r in RC.observations(self.tmp)}
        meta = rows[(101, "harness/tests/a.py::test_meta")]
        self.assertEqual(meta["kind"], RC.DERIVED)
        self.assertEqual(meta["span"], RC.CROSS_LOG)
        self.assertEqual(meta["causes"], ["harness/tests/b.py::test_leaf"])

    def test_a_cause_is_recognised_across_checks_not_just_within_one(self):
        whence = log_text(["tests/w.py::test_w"], {"test_w": "E  assert 0"})
        harness = log_text(
            ["harness/tests/a.py::test_meta"],
            {"test_meta": "E  R001  languages/whence/tests/w.py::test_w: "
                          + RA._r001_message(100, "language(C)", None)})
        self._root(self.tmp, {"whence_health_round_100.log": whence,
                              "health_round_100.log": harness},
                   ["round 100 track=language(C) start"])
        rows = {r["node"]: r for r in RC.observations(self.tmp)}
        meta = rows["harness/tests/a.py::test_meta"]
        self.assertEqual(meta["causes"], ["languages/whence/tests/w.py::test_w"])
        # Same ROUND, different LOG -- the reader of the harness log does not
        # see the whence failure, so this is cross-log, not same-log.
        self.assertEqual(meta["span"], RC.CROSS_LOG)

    def test_a_skills_check_row_is_unreadable_and_never_primary(self):
        """Round 461: which tests failed inside a red `unit_tests` row is
        retained nowhere, for any round. Calling that PRIMARY would be a
        claim the corpus cannot support."""
        self._root(self.tmp,
                   {"skills_health_round_100.log":
                    "unit_tests         ERROR rc1                 2 failed\n"
                    "verb_audit         ok                        clean\n"
                    "corpus-check: 2 checkers, 1 error\n"},
                   ["round 100 track=skills(B) start"])
        rows = RC.observations(self.tmp)
        self.assertEqual([r["kind"] for r in rows], [RC.UNREADABLE])
        res = RC.summarise(rows)
        self.assertEqual(res["primary"], 0)
        self.assertEqual(res["unreadable"], 1)

    def test_a_failed_node_with_no_block_is_unresolved_and_never_primary(self):
        text = log_text(["harness/tests/a.py::test_ghost"], {})
        self._root(self.tmp, {"health_round_100.log": text},
                   ["round 100 track=harness(A) start"])
        rows = RC.observations(self.tmp)
        self.assertEqual([r["kind"] for r in rows], [RC.UNRESOLVED])
        self.assertEqual(RC.summarise(rows)["primary"], 0)

    def test_the_readable_share_excludes_what_could_not_be_read(self):
        """`derived_share_of_readable` must not be diluted by observations
        nobody could classify -- that is the arithmetic version of the same
        refusal."""
        rows = [{"check": "health-check", "kind": RC.DERIVED, "span":
                 RC.SAME_LOG, "causes": ["x"]},
                {"check": "health-check", "kind": RC.PRIMARY, "span": None,
                 "causes": []},
                {"check": "skills-check", "kind": RC.UNREADABLE, "span": None,
                 "causes": []},
                {"check": "skills-check", "kind": RC.UNREADABLE, "span": None,
                 "causes": []}]
        res = RC.summarise(rows)
        self.assertAlmostEqual(res["derived_share_of_readable"], 0.5)
        self.assertAlmostEqual(res["derived_share_of_all"], 0.25)

    def test_the_dated_gap_is_the_rounds_between_cause_and_derived_red(self):
        later = log_text(["harness/tests/a.py::test_meta"],
                         {"test_meta": "E  R001  harness/tests/b.py::test_leaf: "
                                       + RA._r001_message(100, "language(C)",
                                                          104)})
        first = log_text(["harness/tests/b.py::test_leaf"],
                         {"test_leaf": "E  assert 0"})
        self._root(self.tmp, {"health_round_100.log": first,
                              "health_round_104.log": later},
                   ["round 100 track=language(C) start",
                    "round 104 track=harness(A) start"])
        lat = RC.latencies(RC.observations(self.tmp))
        self.assertEqual(lat, [("harness/tests/a.py::test_meta", 104,
                                "harness/tests/b.py::test_leaf", 100, 4)])

    def test_a_green_log_contributes_no_observation_at_all(self):
        self._root(self.tmp,
                   {"health_round_100.log": "..\n2 passed in 1.00s\n"},
                   ["round 100 track=harness(A) start"])
        self.assertEqual(RC.observations(self.tmp), [])

    def test_the_note_clause_is_empty_when_nothing_is_derived(self):
        self.assertEqual(RC.note_clause([{"kind": RC.PRIMARY}]), "")
        self.assertIn("DERIVED", RC.note_clause([{"kind": RC.DERIVED}]))

    def test_the_note_line_names_the_causing_node_and_its_round(self):
        line, = RC.note_lines([{"kind": RC.DERIVED,
                                "causes": ["languages/whence/tests/w.py::test_w"],
                                "dated": [["languages/whence/tests/w.py::test_w",
                                           510, "language(C)"]]}])
        self.assertIn("languages/whence/tests/w.py::test_w", line)
        self.assertIn("round 510", line)
        self.assertIn("language(C)", line)


class TestRetainedCorpus(unittest.TestCase):
    """Facts about rounds <= 510. See the module docstring for why the bound."""

    @classmethod
    def setUpClass(cls):
        n, enough = RA.evidence_base(ROOT)
        if not enough:
            raise unittest.SkipTest(
                "this checkout holds %d per-round log(s), below the floor of "
                "%d -- `logs/*_round_*.log` is gitignored, so these "
                "assertions have no evidence to read. Not a failure of the "
                "tree." % (n, RA.MIN_EVIDENCE_LOGS))
        cls.rows = [r for r in RC.observations(ROOT)
                    if r["round"] <= PINNED_THROUGH]

    def _for(self, node):
        return [r for r in self.rows if r["node"] == node]

    def test_both_redattrib_whole_tree_nodes_are_derived_in_every_red_round(self):
        """The claim the round was built on: neither node has ever reported a
        defect in the suite that hosts it. 16 red rounds each, 460 through
        510, every one of them caused by a node named in its own body."""
        for node in (AUDIT_NODE, FAILCLOSED_NODE):
            obs = self._for(node)
            self.assertEqual(len(obs), 16, node)
            self.assertEqual([r["kind"] for r in obs], [RC.DERIVED] * 16, node)

    def test_the_two_siblings_agree_round_for_round_on_the_cause(self):
        """They are two assertions over one finding list, so a round in which
        they disagree means the parser, not the tree. This is the pin that
        would have caught the `:` trap: before it was fixed one node was
        DERIVED 16 times and the other PRIMARY 16 times, off the same log."""
        a = {r["round"]: set(r["causes"]) for r in self._for(AUDIT_NODE)}
        b = {r["round"]: set(r["causes"]) for r in self._for(FAILCLOSED_NODE)}
        self.assertEqual(sorted(a), sorted(b))
        for rnd in a:
            self.assertTrue(a[rnd] & b[rnd],
                            "round %s: %s vs %s" % (rnd, a[rnd], b[rnd]))

    def test_the_nuc_aggregate_node_is_derived_only_same_log(self):
        """`test_the_fast_check_runs_green_on_this_tree` runs
        nuc/run_checks_fast.sh as a subprocess, so its assertion message IS
        the nested suite's FAILURES section. Every one of its derived rounds
        names a node red in the SAME log -- noisy, never invisible."""
        obs = [r for r in self._for(NUC_AGG_NODE) if r["kind"] == RC.DERIVED]
        self.assertEqual(len(obs), 32)
        self.assertEqual({r["span"] for r in obs}, {RC.SAME_LOG})
        self.assertEqual(sorted({r["round"] for r in obs}),
                         list(range(410, 442)))

    def test_the_nuc_timeout_episode_is_primary_and_not_confused_with_it(self):
        """Rounds 483-495 of the same node are `subprocess.TimeoutExpired` on
        a 600 s cap -- no nested FAILURES section, nothing named, and a real
        defect in its own suite (round 496 fixed it). Same node, both kinds."""
        obs = [r for r in self._for(NUC_AGG_NODE) if r["kind"] == RC.PRIMARY]
        self.assertTrue(obs)
        self.assertTrue(all(r["round"] >= 483 for r in obs))

    def test_exactly_three_nodes_have_ever_produced_a_derived_red(self):
        """64 nodes have gone red; 3 of them account for every derived
        observation, and all 3 are meta-nodes -- a node whose subject is the
        VERDICT of other nodes."""
        derived = {r["node"] for r in self.rows if r["kind"] == RC.DERIVED}
        self.assertEqual(derived, {AUDIT_NODE, FAILCLOSED_NODE, NUC_AGG_NODE})

    def test_no_whence_red_has_ever_been_derived(self):
        """language(C)'s suite hosts no node that asserts over other nodes'
        verdicts, so all 37 of its red observations are primary. The absence
        is the control on the classifier: it does not simply label everything
        it reads."""
        whence = [r for r in self.rows if r["check"] == "whence-health-check"]
        self.assertTrue(whence)
        self.assertEqual({r["kind"] for r in whence}, {RC.PRIMARY})

    def test_every_pytest_red_through_round_510_resolved_to_a_body(self):
        """The parser's own recall over the retained corpus, as a number
        rather than a hope. Bounded at 510 -- a future log that breaks the
        block grammar is a `graph` finding, not a red in this file."""
        unresolved = [r for r in self.rows if r["kind"] == RC.UNRESOLVED]
        self.assertEqual(unresolved, [], "%d unresolved" % len(unresolved))

    def test_the_skills_check_rows_are_all_unreadable_and_none_are_primary(self):
        skills = [r for r in self.rows if r["check"] == "skills-check"]
        self.assertTrue(skills)
        self.assertEqual({r["kind"] for r in skills}, {RC.UNREADABLE})

    def test_every_derived_observation_is_a_red_the_corpus_also_records(self):
        """No cause is invented: every named node appears in a `FAILED` line
        of some retained log."""
        runs = RA.read_logs(ROOT)
        known = {n for per in runs.values() for s in per.values() for n in s}
        for r in self.rows:
            for c in r["causes"]:
                self.assertIn(c, known, "%s named by %s" % (c, r["node"]))

    def test_the_cross_log_shape_is_confined_to_the_harness_check(self):
        """20 cross-log observations, all in health-check. That is the
        program's whole stock of the invisible shape and it lives in one
        suite -- which is the finding, not a coincidence: harness/tests is
        where the corpus-reading instruments were built."""
        cross = [r for r in self.rows if r.get("span") == RC.CROSS_LOG]
        self.assertEqual({r["check"] for r in cross}, {"health-check"})
        self.assertEqual(len(cross), 20)

    def test_the_dated_edges_all_point_backwards_in_time(self):
        """A body naming a red from a LATER round cannot happen; if it does,
        the round numbers are being read off the wrong thing."""
        for _n, rnd, _c, cause_rnd, gap in RC.latencies(self.rows):
            self.assertGreater(gap, 0, "%s named round %s from round %s"
                               % (_c, cause_rnd, rnd))


class TestCLI(unittest.TestCase):
    def _run(self, argv, *extra):
        """Run `argv` verbatim from ROOT, so the source token and the process
        argv are the same string -- see GRAPH_ARGV above."""
        return subprocess.run(
            [sys.executable] + list(argv) + list(extra),
            capture_output=True, text=True, cwd=ROOT)

    def test_graph_json_round_trips_and_exits_zero(self):
        p = self._run(GRAPH_ARGV)
        self.assertEqual(p.returncode, 0, p.stderr)
        res = json.loads(p.stdout)
        self.assertEqual(res["derived"],
                         res["derived_same_log"] + res["derived_cross_log"])

    def test_check_is_a_measurement_and_exits_zero_by_design(self):
        """Deliberate: see harness/redcause.py note 1. A fail-closed
        whole-tree gate in this suite is the mechanism the module measures."""
        p = self._run(CHECK_ARGV)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("EXIT 0 BY DESIGN", p.stdout)

    def test_node_on_an_unknown_node_says_so_rather_than_crashing(self):
        p = self._run(NODE_ARGV, "harness/tests/nope.py::test_nope")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("no red observation", p.stdout)

    def test_live_runs_and_its_rows_carry_a_cause_verdict(self):
        p = self._run(LIVE_ARGV)
        self.assertEqual(p.returncode, 0, p.stderr)
        for row in json.loads(p.stdout):
            self.assertIn(row["kind"], (RC.DERIVED, RC.PRIMARY,
                                        RC.UNRESOLVED, RC.UNREADABLE))
            self.assertIn("node", row)


if __name__ == "__main__":
    unittest.main()

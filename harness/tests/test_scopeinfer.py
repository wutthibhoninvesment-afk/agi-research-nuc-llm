"""Tests for harness/scopeinfer.py (round 523, harness A).

Three kinds.

`TestRules` builds synthetic read-set maps and writer sets and pins each
inference rule, including the two rules that exist to REFUSE. `TestAdmissible`
holds open the property the whole measurement rests on: this module may see
what a node reads and who has committed each file, and may not see any
verdict. `TestThisTree` runs the live measurement and asserts what can be
asserted about it without pinning a number the next round's registry entry
would move.

WHY THIS FILE IS NOT IN `harness/crosstrack-registry.json` -- until it is.
Round 523 landed `predeclared: true`, so for the first time a node MAY be
declared before it is ever red. That makes the older reason
(`test_redattrib.py`'s docstring: "it joins the registry the first time it
breaks") a choice rather than a constraint. This file is deliberately left
undeclared anyway, as the negative control for the mechanism it tests: if
predeclaration is worth anything, a later round should be able to add it here
from `scopeinfer.py predeclare` output rather than from a red.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))

import redattrib as RA        # noqa: E402
import scopeinfer as SI       # noqa: E402

TS = {"harness(A)": ["harness/tests"],
      "language(C)": ["languages/whence/tests"],
      "skills(B)": ["skills"],
      "SWE-loop(D)": ["harness/tests", "languages/whence/tests"],
      "NUC-integration(E)": ["nuc/tests"]}

NODE = "harness/tests/test_x.py::t"


def MAP(**rows):
    """A read-set map with one row per kwarg-free explicit dict."""
    return {"nodes": rows}


def row(files=(), scans=()):
    return {"files": list(files), "scans": list(scans)}


class TestPathModel(unittest.TestCase):

    def test_tree_of_takes_the_longest_matching_tree(self):
        self.assertEqual(SI.tree_of("languages/whence/whence/interp.py"),
                         "languages/whence")
        self.assertEqual(SI.tree_of("harness/swe/mutation.py"), "harness")
        self.assertIsNone(SI.tree_of("state/research-state.md"))
        self.assertIsNone(SI.tree_of("CLAUDE.md"))

    def test_a_tree_name_is_not_a_prefix_of_an_unrelated_directory(self):
        """`nuc` must not swallow a hypothetical `nucleus/` -- the guard is
        the explicit `path == tree or path.startswith(tree + '/')`, and a
        bare `startswith(tree)` would pass every other test in this file."""
        self.assertIsNone(SI.tree_of("nucleus/thing.py"))
        self.assertEqual(SI.tree_of("nuc/bench.py"), "nuc")

    def test_the_subject_set_excludes_the_nodes_own_file(self):
        mp = MAP(**{NODE: row(files=["harness/tests/test_x.py", "harness/a.py"],
                              scans=["harness"])})
        self.assertEqual(SI.subject_set(NODE, mp, ROOT, drop_phantoms=False),
                         ["harness", "harness/a.py"])

    def test_an_unmapped_node_has_no_subject_set_rather_than_an_empty_one(self):
        self.assertIsNone(SI.subject_set(NODE, MAP()))

    def test_owners_gives_the_swe_loop_track_both_of_its_trees(self):
        self.assertEqual(SI.owners("harness", TS),
                         frozenset(("harness(A)", "SWE-loop(D)")))
        self.assertEqual(SI.owners("languages/whence", TS),
                         frozenset(("language(C)", "SWE-loop(D)")))
        self.assertEqual(SI.owners("nuc", TS),
                         frozenset(("NUC-integration(E)",)))


class TestPhantomPaths(unittest.TestCase):
    """Round 523's own finding, and the reason it is filtered here.

    `readset.py`'s audit hook fires on the `open` EVENT, which CPython raises
    BEFORE the syscall, so a read that fails with ENOENT is recorded exactly
    like one that succeeds. 190 such names are in the live map across 415 of
    its 1456 rows.
    """

    def test_existing_splits_a_path_list_by_what_is_actually_there(self):
        yes, no = SI.existing(["harness/scopeinfer.py", "alpha",
                               "state/round_counter"], ROOT)
        self.assertEqual(yes, ["harness/scopeinfer.py", "state/round_counter"])
        self.assertEqual(no, ["alpha"])

    def test_a_phantom_path_is_dropped_from_the_subject_set(self):
        mp = MAP(**{NODE: row(files=["harness/scopeinfer.py", "alpha"])})
        self.assertEqual(SI.subject_set(NODE, mp, ROOT),
                         ["harness/scopeinfer.py"])
        self.assertEqual(SI.subject_set(NODE, mp, ROOT, drop_phantoms=False),
                         ["alpha", "harness/scopeinfer.py"])

    def test_a_row_that_is_all_phantom_refuses_and_says_so(self):
        """It must not fall through to `own-suite` on an empty set -- that
        would label a node from evidence that has never existed."""
        mp = MAP(**{NODE: row(files=["alpha", "beta"])})
        scope, rule, ev = SI.infer(NODE, mp, {}, TS, 3, root=ROOT)
        self.assertIsNone(scope)
        self.assertEqual(rule, "S001")
        self.assertEqual(ev["n_phantom_dropped"], 2)
        self.assertIn("do not exist in the tree", ev["why"])

    def test_a_phantom_outside_every_tree_no_longer_forces_a_refusal(self):
        """The concrete damage: `alpha` is shared ground with no writer, so
        before the filter it pushed an otherwise clean own-suite node to
        S050 on the strength of a file nobody has ever written."""
        mp = MAP(**{NODE: row(files=["harness/scopeinfer.py", "alpha"])})
        self.assertEqual(SI.infer(NODE, mp, {}, TS, 3, root=ROOT)[1], "S040")

    def test_the_live_map_still_carries_them_and_readset_reports_them(self):
        import readset
        ph = readset.phantom_paths(SI.load_map(), ROOT)
        self.assertIn("alpha", ph)
        self.assertGreater(len(ph), 50)

    def test_the_readset_phantoms_verb_runs_and_agrees_with_the_library(self):
        """Also what keeps the new verb off `verb_audit`'s V001 list: a
        declared CLI verb nothing in the tree is seen invoking is dead
        surface, and a test that shells out to it is the cheapest honest
        invocation."""
        import readset
        out = subprocess.run(
            [sys.executable, os.path.join(ROOT, "harness", "readset.py"),
             "phantoms", "--json"], capture_output=True, text=True, timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout)
        self.assertEqual(got["n_paths"],
                         len(readset.phantom_paths(SI.load_map(), ROOT)))

    def test_dropping_them_shrinks_the_predeclarable_set(self):
        """Measured, not assumed: 219 of the 1302 nodes the first draft
        called predeclarable were labelled on phantom evidence alone. A
        floor rather than the exact number, because a re-recorded map moves
        it -- and if `readset record` ever stops keeping phantoms, this test
        should be deleted with a note, not loosened."""
        mp = SI.load_map()
        writers, _r = SI.path_writers(ROOT)
        kept = len(SI.predeclarable(ROOT, mp, writers))
        raw = 0
        for nid in mp["nodes"]:
            if "::" in nid and not nid.endswith("::<collect>"):
                if RA.node_suite(nid) is None:
                    continue
                paths = SI.subject_set(nid, mp, ROOT, drop_phantoms=False)
                if paths is None:
                    continue
                raw += 1
        self.assertGreater(raw, kept)


class TestCommitAttribution(unittest.TestCase):

    def test_a_track_marker_in_the_subject_wins(self):
        self.assertEqual(SI.attribute_subject("round 523 (harness A): x", {}, {}),
                         ("harness(A)", "marker"))

    def test_a_capital_R_subject_still_attributes(self):
        """58 of this repo's 766 subjects are `Round NNN (...)`. A
        case-sensitive match drops every one of them into `unattributed`,
        which is a silent hole in a writer set, not an error anybody sees."""
        who, route = SI.attribute_subject(
            "Round 292 (NUC-integration E, reconciled): x", {}, {})
        self.assertEqual((who, route), ("NUC-integration(E)", "marker"))

    def test_a_round_number_falls_through_to_the_driver_log(self):
        self.assertEqual(
            SI.attribute_subject("round 400: leftovers", {400: "skills(B)"}, {}),
            ("skills(B)", "log"))

    def test_a_round_the_log_lost_falls_through_to_the_observed_rotation(self):
        """`logs/driver.log` starts at round 152 on this box; the rotation is
        derived from the record it DOES have, never from CLAUDE.md's copy of
        the rule, which is round 466's `null-must-preserve-the-shape` applied
        to attribution."""
        self.assertEqual(
            SI.attribute_subject("round 100: old", {}, {4: "language(C)"}),
            ("language(C)", "rotation"))

    def test_a_driver_append_is_its_own_writer_and_not_a_track(self):
        self.assertEqual(SI.attribute_subject("driver: ledger append", {}, {}),
                         ("driver", "none"))
        self.assertEqual(SI.track_writers(["driver", "operator", "harness(A)"]),
                         ["harness(A)"])

    def test_an_operator_commit_is_named_rather_than_dropped(self):
        who, _ = SI.attribute_subject("release: v1.0.0", {}, {})
        self.assertEqual(who, "operator")

    def test_path_writers_reads_a_log_it_is_given(self):
        log = ("@@aaa|round 10 (harness A): x\nharness/a.py\nstate/s.json\n"
               "@@bbb|round 11 (skills B): y\nstate/s.json\n")
        writers, routes = SI.path_writers(ROOT, _log=log)
        self.assertEqual(writers["harness/a.py"], ["harness(A)"])
        self.assertEqual(writers["state/s.json"], ["harness(A)", "skills(B)"])
        self.assertEqual(routes["marker"], 2)


class TestRules(unittest.TestCase):
    """One test per rule, and the two refusals are rules too."""

    def infer(self, mp, writers=None, threshold=3, node=NODE):
        """`drop_phantoms=False` on purpose: these maps name synthetic paths
        like `harness/a.py` that are not in the checkout, and the filter is
        about the LIVE map, not about the rule under test. `TestPhantomPaths`
        exercises it against the real tree."""
        return SI.infer(node, mp, writers or {}, TS, threshold,
                        drop_phantoms=False)

    def test_S000_no_row_in_the_map_is_a_refusal(self):
        scope, rule, ev = self.infer(MAP())
        self.assertIsNone(scope)
        self.assertEqual(rule, "S000")
        self.assertIn("no row", ev["why"])

    def test_S001_an_empty_row_is_a_refusal_and_not_own_suite(self):
        scope, rule, _ = self.infer(MAP(**{NODE: row()}))
        self.assertIsNone(scope)
        self.assertEqual(rule, "S001")

    def test_S010_a_root_scan_is_whole_tree(self):
        scope, rule, _ = self.infer(MAP(**{NODE: row(scans=["."])}))
        self.assertEqual((scope, rule), ("whole-tree", "S010"))

    def test_S010_three_trees_is_whole_tree(self):
        mp = MAP(**{NODE: row(files=["harness/a.py", "nuc/b.py",
                                     "languages/whence/c.py"])})
        scope, rule, ev = self.infer(mp)
        self.assertEqual((scope, rule), ("whole-tree", "S010"))
        self.assertEqual(sorted(ev["trees"]),
                         ["harness", "languages/whence", "nuc"])

    def test_S020_one_other_tree_and_not_the_hosts_is_foreign_subject(self):
        mp = MAP(**{NODE: row(files=["languages/whence/a.py",
                                     "languages/whence/b.py"])})
        scope, rule, _ = self.infer(mp)
        self.assertEqual((scope, rule), ("foreign-subject", "S020"))

    def test_S020_fires_before_S030_so_a_widely_written_file_in_the_foreign_tree_does_not_hide_it(self):
        """The ordering is the whole difference between 2/2 and 0/2 on the
        live tree. `languages/whence/SPEC.md` has five track writers, so a
        shared-corpus-first order relabels every node whose subject is the
        whence tree -- exactly the `foreign-subject` shape -- as
        `shared-corpus`."""
        mp = MAP(**{NODE: row(files=["languages/whence/SPEC.md"])})
        writers = {"languages/whence/SPEC.md":
                   ["harness(A)", "language(C)", "skills(B)", "SWE-loop(D)"]}
        scope, rule, _ = self.infer(mp, writers)
        self.assertEqual((scope, rule), ("foreign-subject", "S020"))

    def test_S030_a_widely_written_path_in_the_host_tree_is_shared_corpus(self):
        mp = MAP(**{NODE: row(files=["harness/wiring-registry.json"])})
        writers = {"harness/wiring-registry.json":
                   ["harness(A)", "language(C)", "skills(B)"]}
        scope, rule, ev = self.infer(mp, writers)
        self.assertEqual((scope, rule), ("shared-corpus", "S030"))
        self.assertEqual(ev["shared_corpus_paths"], ["harness/wiring-registry.json"])

    def test_S030_does_not_fire_when_every_writer_is_one_of_the_hosts_owners(self):
        """`harness/tests/test_whenceslow.py` is written by harness(A),
        SWE-loop(D) and language(C) -- three tracks -- but two of the three
        RUN the harness suite. A raw count calls that shared corpus; the
        registry means "somebody who does not run this suite writes it"."""
        mp = MAP(**{NODE: row(files=["harness/shared.py"])})
        writers = {"harness/shared.py": ["harness(A)", "SWE-loop(D)"]}
        scope, rule, _ = self.infer(mp, writers, threshold=2)
        self.assertEqual((scope, rule), ("own-suite", "S040"))

    def test_S030_respects_the_threshold(self):
        mp = MAP(**{NODE: row(files=["harness/reg.json"])})
        writers = {"harness/reg.json": ["harness(A)", "skills(B)"]}
        self.assertEqual(self.infer(mp, writers, threshold=2)[0], "shared-corpus")
        self.assertEqual(self.infer(mp, writers, threshold=3)[0], "own-suite")

    def test_S040_host_tree_only_is_own_suite(self):
        mp = MAP(**{NODE: row(files=["harness/a.py"], scans=["harness/tests"])})
        scope, rule, _ = self.infer(mp)
        self.assertEqual((scope, rule), ("own-suite", "S040"))

    def test_S040_shared_ground_written_only_by_the_host_is_still_own_suite(self):
        """`state/whence/...` is outside all four trees and is language(C)'s
        alone; the registry calls the node that reads it `own-suite`."""
        mp = MAP(**{"languages/whence/tests/test_a.py::t":
                    row(files=["state/whence/roster.json"])})
        writers = {"state/whence/roster.json": ["language(C)"]}
        scope, rule, _ = SI.infer("languages/whence/tests/test_a.py::t", mp,
                                  writers, TS, 3, drop_phantoms=False)
        self.assertEqual((scope, rule), ("own-suite", "S040"))

    def test_S050_shared_ground_another_track_writes_is_a_refusal_not_a_guess(self):
        mp = MAP(**{NODE: row(files=["state/thing.json"])})
        writers = {"state/thing.json": ["harness(A)", "skills(B)"]}
        scope, rule, ev = self.infer(mp, writers)
        self.assertIsNone(scope)
        self.assertEqual(rule, "S050")
        self.assertEqual(ev["foreign_written_shared_paths"], ["state/thing.json"])

    def test_S050_host_plus_exactly_one_other_tree_is_a_refusal(self):
        mp = MAP(**{NODE: row(files=["harness/a.py", "nuc/b.py"])})
        scope, rule, ev = self.infer(mp)
        self.assertIsNone(scope)
        self.assertEqual(rule, "S050")
        self.assertIn("no label for that shape", ev["why"])

    def test_a_node_in_no_declared_suite_still_refuses_rather_than_crashing(self):
        mp = MAP(**{"tools/test_z.py::t": row(files=["harness/a.py"])})
        scope, rule, _ = SI.infer("tools/test_z.py::t", mp, {}, TS, 3,
                                  drop_phantoms=False)
        self.assertIsNone(scope)
        self.assertEqual(rule, "S050")

    def test_the_rule_table_and_the_code_agree_on_every_verdict(self):
        """`RULES` is documentation until something reads it."""
        self.assertEqual(
            [r for r, _v in SI.RULES],
            ["S000", "S001", "S010", "S020", "S030", "S040", "S050"])
        verdicts = dict(SI.RULES)
        cases = [
            (MAP(), {}, "S000"),
            (MAP(**{NODE: row()}), {}, "S001"),
            (MAP(**{NODE: row(scans=["."])}), {}, "S010"),
            (MAP(**{NODE: row(files=["nuc/a.py"])}), {}, "S020"),
            (MAP(**{NODE: row(files=["harness/r.json"])}),
             {"harness/r.json": ["harness(A)", "skills(B)", "language(C)"]}, "S030"),
            (MAP(**{NODE: row(files=["harness/a.py"])}), {}, "S040"),
            (MAP(**{NODE: row(files=["harness/a.py", "nuc/b.py"])}), {}, "S050"),
        ]
        for mp, writers, expect in cases:
            scope, rule, _ = self.infer(mp, writers)
            self.assertEqual(rule, expect, mp)
            self.assertEqual(scope, verdicts[rule], rule)


class TestAdmissible(unittest.TestCase):
    """The restraint that makes the agreement number mean anything."""

    def test_the_two_unreachable_scopes_are_declared_with_a_reason(self):
        self.assertEqual(sorted(SI.UNREACHABLE),
                         ["environmental", "shared-file-own-content"])
        for name, why in SI.UNREACHABLE.items():
            self.assertGreater(len(why), 80, name)

    def test_no_rule_can_ever_emit_an_unreachable_scope(self):
        self.assertFalse(set(v for _r, v in SI.RULES) & set(SI.UNREACHABLE))

    def test_the_module_never_reads_a_health_log(self):
        """`redattrib.read_logs` is the only door to the verdict history in
        this directory. If `agreement` could open it, the classifier could
        reproduce the labels it is being scored against."""
        called = []
        orig = RA.read_logs
        RA.read_logs = lambda *a, **k: called.append(1) or {}
        try:
            SI.agreement(ROOT)
        finally:
            RA.read_logs = orig
        self.assertEqual(called, [])

    def test_the_source_CALLS_nothing_that_reads_a_verdict(self):
        """An AST check, not a token grep, and that is the point.

        Round 523 wrote this as a substring scan twice and it was wrong both
        times: `_round_` matched a docstring quoting the node id
        `..._round_469_measured`, and `logs/` matched the sentence explaining
        that `logs/` is shared ground. Neither is a read. A grep over source
        cannot tell prose from code, so this walks the tree and looks at the
        names actually being CALLED -- the only form in which this module
        could reach a verdict history.
        """
        import ast
        forbidden = {"read_logs", "observed_nodes", "analyse", "episodes_for",
                     "first_firable", "scope_test_episodes"}
        src = open(os.path.join(ROOT, "harness", "scopeinfer.py")).read()
        called = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "attr", None) or getattr(fn, "id", None)
                if name:
                    called.add(name)
        self.assertEqual(sorted(called & forbidden), [],
                         "scopeinfer.py calls a verdict reader")

    def test_the_only_redattrib_names_it_uses_are_subject_side(self):
        """The import is real and narrow: `node_suite` (a string prefix),
        `round_tracks` / `rotation_residue_map` (attribution), `load_registry`
        (the labels being scored) and `ROTATION_PERIOD`. Anything else added
        later has to be argued for here."""
        import ast
        src = open(os.path.join(ROOT, "harness", "scopeinfer.py")).read()
        used = set()
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "redattrib"):
                used.add(node.attr)
        self.assertEqual(used, {"node_suite", "round_tracks", "load_registry",
                                "rotation_residue_map", "ROTATION_PERIOD"},
                         sorted(used))

    def test_the_live_inference_emits_no_unreachable_scope(self):
        res = SI.agreement(ROOT)
        emitted = set(r["inferred"] for r in res["rows"]) - {None}
        self.assertFalse(emitted & set(SI.UNREACHABLE), sorted(emitted))


class TestFragment(unittest.TestCase):

    def test_the_emitted_fragment_is_a_well_formed_predeclaration(self):
        rows = [{"node": NODE, "subject_scope": "own-suite", "rule": "S040",
                 "why": "no path outside the host tree", "n_subject": 3}]
        frag = SI.registry_fragment(rows, round_no=523)
        ent = frag[NODE]
        self.assertEqual(ent["subject_scope"], "own-suite")
        self.assertEqual(ent["evidence"], "subject")
        self.assertIs(ent["predeclared"], True)
        self.assertIn("S040", ent["why"])

    def test_a_fragment_entry_passes_redattribs_own_predeclaration_rule(self):
        """The two modules agree on the shape, or the emitter writes entries
        the auditor rejects -- which is the defect this pair exists to make
        impossible."""
        rows = [{"node": "harness/tests/test_ghost.py::t",
                 "subject_scope": "whole-tree", "rule": "S010",
                 "why": "scans the repo root", "n_subject": 9}]
        reg = {"_subject_scope": {"whole-tree": "", "own-suite": "",
                                  "environmental": ""},
               "_track_suites": TS,
               "nodes": dict(SI.registry_fragment(rows))}
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "harness"))
        os.makedirs(os.path.join(tmp, "logs"))
        with open(os.path.join(tmp, "logs", "driver.log"), "w") as fh:
            fh.write("round 5 track=harness(A) start\n")
        with open(os.path.join(tmp, RA.REGISTRY_NAME), "w") as fh:
            json.dump(reg, fh)
        codes = [f[0] for f in RA.analyse(tmp)["registry_findings"]]
        self.assertEqual(codes, [], codes)


class TestThisTree(unittest.TestCase):
    """The live measurement. Pins properties, not the numbers a later
    registry entry or a re-recorded read-set map would legitimately move."""

    @classmethod
    def setUpClass(cls):
        cls.res = SI.agreement(ROOT)
        cls.reg = RA.load_registry(ROOT)

    def test_a_predeclared_entry_is_never_scored_against_the_classifier(self):
        """THE CIRCULARITY THIS ROUND WALKED INTO. Round 523 landed 37
        predeclarations this module proposed and the next `agree` reported
        81%, up from 56%, because 37 of the 39 foreign-subject agreements
        were its own output. A predeclared entry is not evidence about the
        classifier; it IS the classifier."""
        pre = [n for n, e in self.reg["nodes"].items()
               if e.get("predeclared") is True]
        self.assertTrue(pre, "no predeclared entry left to guard")
        self.assertEqual(self.res["n_predeclared_excluded"], len(pre))
        self.assertEqual(self.res["n_entries"],
                         len(self.reg["nodes"]) - len(pre))
        scored = set(r["node"] for r in self.res["rows"] if not r["predeclared"])
        self.assertFalse(scored & set(pre))

    def test_every_registry_entry_is_scored_exactly_once(self):
        self.assertEqual(len(self.res["rows"]), len(self.reg["nodes"]))
        self.assertEqual(len(set(r["node"] for r in self.res["rows"])),
                         len(self.res["rows"]))

    def test_labelled_plus_refused_is_the_whole_independent_population(self):
        self.assertEqual(self.res["n_labelled"] + sum(self.res["refusals"].values()),
                         self.res["n_entries"])

    def test_agreement_is_bounded_by_what_was_labelled(self):
        self.assertLessEqual(self.res["n_agree"], self.res["n_labelled"])
        self.assertLessEqual(self.res["n_subject_evidence_labelled"],
                             self.res["n_subject_evidence"])

    def test_coverage_not_inference_is_the_binding_constraint(self):
        """Round 523's headline. More entries are refused for having no
        read-set row at all (S000) than are labelled -- so the cheap way to
        make predeclaration usable is to RECORD more read sets, not to write
        a cleverer classifier. A floor, not an equality: recording read sets
        moves it, and the day it stops being true this test should be read
        rather than deleted."""
        self.assertGreater(self.res["refusals"].get("S000", 0),
                           self.res["n_labelled"] // 2)

    def test_every_outcome_derived_entry_is_either_refused_or_visibly_wrong(self):
        """R006's boundary from the other side: an `environmental` scope is
        not in any subject, so this module must never AGREE with one."""
        for r in self.res["rows"]:
            if r["evidence"] == "outcome" and not r["predeclared"]:
                self.assertFalse(r["agree"], r["node"])

    def test_the_threshold_sweep_runs_and_only_moves_shared_corpus(self):
        low = SI.agreement(ROOT, threshold=3)
        high = SI.agreement(ROOT, threshold=5)
        self.assertEqual(low["n_entries"], high["n_entries"])
        moved = [(a["node"], a["inferred"], b["inferred"])
                 for a, b in zip(low["rows"], high["rows"])
                 if a["inferred"] != b["inferred"]]
        for _n, lo, hi in moved:
            self.assertIn("shared-corpus", (lo, hi))

    def test_the_predeclarable_set_is_disjoint_from_the_registry(self):
        rows = SI.predeclarable(ROOT)
        self.assertTrue(rows)
        for r in rows:
            self.assertNotIn(r["node"], self.reg["nodes"], r["node"])
            self.assertIsNotNone(RA.node_suite(r["node"]))

    def test_the_predeclarable_set_is_larger_than_the_registry(self):
        """The population R002 made unwritable. A floor, deliberately far
        below the 1302 measured at round 523 so a re-recorded map does not
        redden it."""
        self.assertGreater(len(SI.predeclarable(ROOT)), len(self.reg["nodes"]))

    def test_the_cli_agrees_with_the_library_and_exits_zero(self):
        out = subprocess.run(
            [sys.executable, os.path.join(ROOT, "harness", "scopeinfer.py"),
             "agree", "--json"], capture_output=True, text=True, timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout)
        self.assertEqual(got["n_entries"], self.res["n_entries"])
        self.assertEqual(got["n_agree"], self.res["n_agree"])

    def test_the_writer_map_attributes_most_commits_by_a_named_track(self):
        _writers, routes = SI.path_writers(ROOT)
        self.assertGreater(routes["marker"], sum(routes.values()) / 2.0)


if __name__ == "__main__":
    unittest.main()

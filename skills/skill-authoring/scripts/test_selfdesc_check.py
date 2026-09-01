#!/usr/bin/env python3
"""Tests for selfdesc_check.py (round 435, skills B).

Two tiers, and the split is deliberate.

`TestSynthetic` builds a throwaway repo per case. Six of the eight finding
codes produce NOTHING on the live corpus today, and a rule that has never
fired is indistinguishable from a rule that cannot — `would-a-constant-have-
passed`. Each of those gets a fixture that makes it fire and a near-miss that
keeps it quiet, so the silence on the real tree is evidence rather than
absence.

`TestLiveCorpus` asserts the real tree, and asserts the DISCRIMINATIONS by
name rather than a total: the CP01/CP02/CP05 sentence must yield exactly one
finding, and `"Two kinds so far"` over a three-entry map must yield none. A
count is a weaker pin than a named case, because a count stays green while two
errors swap places.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import selfdesc_check                                        # noqa: E402


def codes(findings):
    return sorted(f.code for f in findings)


class SyntheticRepo(object):
    """A minimal repo the checker can sweep: top-level dirs + artefacts."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="selfdesc-")
        for d in ("state", "harness", "skills"):
            os.makedirs(os.path.join(self.root, d))

    def write_json(self, rel, obj):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=1)
        return path

    def write_text(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def sweep(self):
        return selfdesc_check.sweep(self.root)

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class TestSynthetic(unittest.TestCase):

    def setUp(self):
        self.repo = SyntheticRepo()

    def tearDown(self):
        self.repo.close()

    # -- discovery ------------------------------------------------------

    def test_a_short_field_is_a_label_not_a_description(self):
        self.repo.write_json("state/r.json", {"_comment": "a registry.",
                                              "pins": [{"id": "A1"}]})
        findings, _acked, stats = self.repo.sweep()
        self.assertEqual(stats["artefacts"], 0)
        self.assertEqual(findings, [])

    def test_a_jsonl_stream_is_a_log_not_an_unparseable_artefact(self):
        self.repo.write_text("state/ledger.json",
                             '{"a": 1}\n{"a": 2}\n{"a": 3}\n')
        self.repo.write_text("state/broken.json", "{not json at all")
        _f, _a, stats = self.repo.sweep()
        self.assertEqual(stats["streams"], 1)
        self.assertEqual(stats["unparseable"], ["state/broken.json"])

    def test_a_field_with_no_checkable_claim_is_counted_as_silent(self):
        self.repo.write_json("state/r.json", {
            "_comment": "The direction is fail-closed, and a stale entry "
                        "costs wall-clock rather than coverage. That is a "
                        "claim about meaning and nothing here can check it.",
            "pins": [{"id": "A1"}]})
        findings, _a, stats = self.repo.sweep()
        self.assertEqual(findings, [])
        self.assertEqual(stats["prose_fields"], 1)
        self.assertEqual(stats["silent_fields"], 1)

    # -- J001 / J002 / J003: the reader claim ---------------------------

    def test_J001_a_named_reader_that_does_not_exist(self):
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry of things, read by harness/ghost.py, "
                        "which decides what to do with each of them.",
            "items": [{"id": "A1"}]})
        self.repo.write_text("harness/real.py", "open('state/reg.json')\n")
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J001"])

    def test_J002_nothing_in_the_tree_reads_it_at_all(self):
        self.repo.write_json("state/orphan.json", {
            "_comment": "A registry of things, read by harness/real.py and "
                        "by nothing else in this repository at all.",
            "items": [{"id": "A1"}]})
        self.repo.write_text("harness/real.py", "print('unrelated')\n")
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J002"])

    def test_J003_the_reader_exists_and_names_a_different_file(self):
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry of things, read by harness/front.py, "
                        "which is the module that decides each entry.",
            "items": [{"id": "A1"}]})
        self.repo.write_text("harness/front.py", "import back\n")
        self.repo.write_text("harness/back.py", "open('state/reg.json')\n")
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J003"])
        self.assertEqual(findings[0].severity, "WARN")

    def test_a_correct_reader_claim_is_silent(self):
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry of things, read by harness/real.py, "
                        "which decides what to do with each of them.",
            "items": [{"id": "A1"}]})
        self.repo.write_text("harness/real.py", "open('state/reg.json')\n")
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(findings, [])

    # -- J004: the path claim -------------------------------------------

    def test_J004_a_prose_path_that_does_not_resolve(self):
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry of things. The rule it encodes is "
                        "written down in state/no-such-doc.md, which is "
                        "where a reader should start.",
            "items": [{"id": "A1"}]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J004"])

    def test_a_resolving_prose_path_is_silent(self):
        self.repo.write_text("state/real-doc.md", "hello\n")
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry of things. The rule it encodes is "
                        "written down in state/real-doc.md, which is where "
                        "a reader should start.",
            "items": [{"id": "A1"}]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(findings, [])

    # -- J005: the count claim, and its two discriminators --------------

    def test_J005_a_count_that_disagrees_with_its_own_collection(self):
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry. The three pins below each name a rule "
                        "and the check that is claimed to catch it.",
            "pins": [{"id": "A1"}, {"id": "A2"}, {"id": "A3"},
                     {"id": "A4"}]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J005"])
        self.assertIn("and the artefact has 4", findings[0].message)

    def test_a_count_whose_noun_names_nothing_here_is_not_a_count_claim(self):
        """`known-absent-paths.json`'s "Two kinds so far" over 3 paths."""
        self.repo.write_json("state/reg.json", {
            "_comment": "Paths that prose legitimately names while they do "
                        "not exist. Two kinds so far: (1) a file whose "
                        "absence is the point; (2) a planned artifact.",
            "paths": {"a": 1, "b": 2, "c": 3}})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(findings, [])

    def test_a_count_pointed_at_a_different_container_is_dropped(self):
        self.repo.write_json("state/reg.json", {
            "_comment": "Skills whose probe is owed. This is empty because "
                        "round 357 probed all 27 skills in the corpus, and "
                        "the file exists so the schema is documented.",
            "skills": {"a": 1, "b": 2}})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual([f.code for f in findings], [])

    def test_a_past_tense_true_count_is_dropped(self):
        """The rule's KNOWN recall cost, pinned so it is a decision.

        A real count claim written in the past tense is suppressed along with
        the historical-subset narratives the discriminator exists for. Pinned
        rather than fixed: distinguishing "N were changed" (a claim about the
        artefact) from "N had been dropped" (a claim about history) needs a
        parser this file does not have, and a false ERROR costs more than a
        missed one here.
        """
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry. The three pins below were each written "
                        "against a rule in the guest file and its check.",
            "pins": [{"id": "A1"}, {"id": "A2"}, {"id": "A3"},
                     {"id": "A4"}]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(findings, [])

    # -- J006: the absence claim ----------------------------------------

    def test_J006_fires_on_a_denied_id_that_is_present_by_stem(self):
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry of plus pins. Round 414's A1/A2/A5 are "
                        "lateral and have no mirror; see the round file for "
                        "why a lateral rule needs a new statement.",
            "pins": [{"id": "A3p"}, {"id": "A4p"}, {"id": "A5p"}]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J006"])
        self.assertIn("`A5`", findings[0].message)
        self.assertIn("A5p", findings[0].message)

    def test_J006_stays_silent_on_the_ids_in_the_same_sentence_that_are_absent(self):
        """A1 and A2 are named in the same clause and are genuinely absent."""
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry of plus pins. Round 414's A1/A2 are "
                        "lateral and have no mirror; see the round file for "
                        "why a lateral rule needs a new statement.",
            "pins": [{"id": "A3p"}, {"id": "A4p"}, {"id": "A5p"}]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(findings, [])

    def test_J007_a_dated_claim_is_information_and_never_an_error(self):
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry of plus pins. As of round 414 the pins "
                        "A1/A2/A5 are lateral and have no mirror, which is "
                        "what that round recorded at the time.",
            "pins": [{"id": "A3p"}, {"id": "A5p"}]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J007"])
        self.assertEqual(findings[0].severity, "INFO")

    # -- J008: the regeneration instruction ------------------------------

    def test_J008_a_derived_file_nothing_can_regenerate(self):
        self.repo.write_json("state/derived.json", {
            "_comment": "Round 420: the base registry with a column added. "
                        "Derived from state/base.json; regenerate, do not "
                        "hand-edit.",
            "pins": [{"id": "A1", "dir": "-"}]})
        self.repo.write_json("state/base.json", {"pins": [{"id": "A1"}]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J008"])

    def test_a_derived_file_with_a_generator_is_silent(self):
        self.repo.write_json("state/derived.json", {
            "_comment": "Round 420: the base registry with a column added. "
                        "Derived from state/base.json; regenerate, do not "
                        "hand-edit.",
            "pins": [{"id": "A1", "dir": "-"}]})
        self.repo.write_json("state/base.json", {"pins": [{"id": "A1"}]})
        self.repo.write_text("harness/gen.py",
                             "OUT = 'state/derived.json'\n")
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(findings, [])

    # -- J010: the delta claim -------------------------------------------

    def test_J010_a_delta_count_against_a_named_sibling(self):
        self.repo.write_json("state/base.json", {
            "pins": [{"id": "A1", "guardian": "x"},
                     {"id": "A2", "guardian": "y"},
                     {"id": "A3", "guardian": "z"}]})
        self.repo.write_json("state/repointed.json", {
            "_comment": "state/base.json with one guardian label repointed "
                        "and nothing else touched anywhere in the file.",
            "pins": [{"id": "A1", "guardian": "X"},
                     {"id": "A2", "guardian": "Y"},
                     {"id": "A3", "guardian": "z"}]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J010"])
        self.assertIn("2 of 3 shared", findings[0].message)

    def test_a_correct_delta_count_is_silent(self):
        self.repo.write_json("state/base.json", {
            "pins": [{"id": "A1", "guardian": "x"},
                     {"id": "A2", "guardian": "y"}]})
        self.repo.write_json("state/repointed.json", {
            "_comment": "state/base.json with one guardian label repointed "
                        "and nothing else touched anywhere in the file.",
            "pins": [{"id": "A1", "guardian": "X"},
                     {"id": "A2", "guardian": "y"}]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(findings, [])

    # -- J011: the executable claim --------------------------------------

    def test_J011_locates_an_executable_claim_and_does_not_run_it(self):
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry of pins. `polarity.py audit` over this "
                        "file must report 0 MISPOINTED, which is the "
                        "non-circular half of the procedure.",
            "pins": [{"id": "A1"}]})
        findings, _a, stats = self.repo.sweep()
        self.assertEqual(codes(findings), ["J011"])
        self.assertEqual(findings[0].severity, "WARN")
        self.assertEqual(stats["must_claims"], 1)

    # -- J009: the acknowledgement registry ------------------------------

    def _acked_repo(self, ack_hash=None):
        prose = ("A registry. The three pins below each name a rule and the "
                 "check that is claimed to catch it.")
        self.repo.write_json("state/reg.json", {
            "_comment": prose,
            "pins": [{"id": "A1"}, {"id": "A2"}, {"id": "A3"},
                     {"id": "A4"}]})
        self.repo.write_json("state/known-selfdesc-drift.json", {
            "acknowledged": [{"path": "state/reg.json", "field": "_comment",
                              "code": "J005",
                              "hash": ack_hash or
                              selfdesc_check.prose_hash(prose),
                              "why": "owned by another track"}]})
        return prose

    def test_a_content_pinned_acknowledgement_suppresses_its_finding(self):
        self._acked_repo()
        findings, acked, stats = self.repo.sweep()
        self.assertEqual(findings, [])
        self.assertEqual(codes(acked), ["J005"])
        self.assertEqual(stats["acknowledged"], 1)

    def test_an_expired_pin_reports_the_finding_AND_a_dead_acknowledgement(self):
        self._acked_repo(ack_hash="0" * 16)
        findings, acked, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J005", "J009"])
        self.assertEqual(acked, [])

    def test_an_acknowledgement_that_suppresses_nothing_is_reported_dead(self):
        self.repo.write_json("state/known-selfdesc-drift.json", {
            "acknowledged": [{"path": "state/gone.json", "field": "_comment",
                              "code": "J005", "hash": "abc",
                              "why": "fixed long ago"}]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J009"])


class TestLiveCorpus(unittest.TestCase):
    """The real tree. Skipped if it is not here."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(ROOT, "state")):
            raise unittest.SkipTest("live corpus not present")
        cls.findings, cls.acked, cls.stats = selfdesc_check.sweep(ROOT)

    def test_the_live_corpus_has_no_unacknowledged_errors(self):
        errs = [str(f) for f in self.findings if f.severity == "ERROR"]
        self.assertEqual(errs, [], "\n".join(errs))

    def test_the_cp05_sentence_yields_exactly_one_finding_or_is_fixed(self):
        """CP01/CP02/CP05: three ids, one clause, one right answer.

        Either the sentence still denies CP05 — in which case the finding is
        acknowledged and CP01/CP02 must NOT appear beside it — or the prose
        has been corrected and there is nothing. Both are green; a finding
        naming CP01 or CP02 is not, and neither is TWO findings.
        """
        rel = "state/whence/round-422/host-pins-plus.json"
        got = [f for f in self.findings + self.acked
               if f.rel == rel and f.code in ("J006", "J007")]
        self.assertLessEqual(len(got), 1, [str(f) for f in got])
        for f in got:
            self.assertIn("CP05", f.message)
            self.assertNotIn("CP01", f.message)
            self.assertNotIn("CP02", f.message)

    def test_the_two_kinds_sentence_is_not_read_as_a_count_of_paths(self):
        rel = "state/known-absent-paths.json"
        got = [f for f in self.findings + self.acked if f.rel == rel]
        self.assertEqual(got, [], [str(f) for f in got])

    def test_every_artefact_with_prose_is_actually_swept(self):
        """The denominator is derived, not asserted from a constant."""
        arts, n_json, _u, _s = selfdesc_check.scan_tree(ROOT)
        self.assertEqual(self.stats["artefacts"], len(arts))
        self.assertEqual(self.stats["json_files"], n_json)
        self.assertGreaterEqual(self.stats["artefacts"], 20)

    def test_the_summary_line_carries_a_coverage_token_corpus_check_can_lift(self):
        import io
        import corpus_check
        buf = io.StringIO()
        selfdesc_check.report(self.findings, self.acked, self.stats, False,
                              buf)
        self.assertTrue(corpus_check.coverage_of(buf.getvalue()),
                        "no `coverage A/B unit` token on the summary line")

    def test_the_checker_is_registered_in_corpus_check(self):
        import corpus_check
        names = [n for n, _argv in corpus_check.checks(ROOT)]
        self.assertIn("selfdesc_check", names)


if __name__ == "__main__":
    unittest.main()

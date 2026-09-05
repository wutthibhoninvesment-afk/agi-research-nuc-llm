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

    # -- round 447: what a field is, what it is ABOUT, and what "checked"
    #    means -------------------------------------------------------------

    def test_a_true_count_claim_is_CHECKED_even_though_it_is_silent(self):
        """The defect the coverage token had until round 447.

        `checked = prose_fields - silent_fields` counted fields that produced
        a FINDING and published the result as coverage, so a claim that was
        looked up and found CORRECT was reported as uncovered. The token
        could only rise when the corpus got worse, and it read `0/28` on the
        live tree precisely because the corpus was clean.
        """
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry. The three pins below each name a rule "
                        "and the check that is claimed to catch it.",
            "pins": [{"id": "A1"}, {"id": "A2"}, {"id": "A3"}]})
        findings, _a, stats = self.repo.sweep()
        self.assertEqual(findings, [])
        self.assertEqual(stats["silent_fields"], 1)     # produced no finding
        self.assertEqual(stats["checked_fields"], 1)    # and WAS checked
        self.assertEqual(stats["claims"], 1)

    def test_coverage_and_the_error_count_move_independently(self):
        """Two fields, one true claim and one false: coverage 2, errors 1."""
        self.repo.write_json("state/true.json", {
            "_comment": "A registry. The three pins below each name a rule "
                        "and the check that is claimed to catch it.",
            "pins": [{"id": "A1"}, {"id": "A2"}, {"id": "A3"}]})
        self.repo.write_json("state/false.json", {
            "_comment": "A registry. The three pins below each name a rule "
                        "and the check that is claimed to catch it.",
            "pins": [{"id": "A1"}, {"id": "A2"}]})
        findings, _a, stats = self.repo.sweep()
        self.assertEqual(codes(findings), ["J005"])
        self.assertEqual(stats["checked_fields"], 2)
        self.assertEqual(stats["prose_fields"], 2)

    def test_a_round_stamped_field_name_is_swept(self):
        """Round 435 item 3's gap, and it was a NAME rule, not a depth one.

        Every `_round_NNN_note` field in the live
        `state/known-unprobed-skills.json` is TOP-LEVEL. They were skipped
        because `_round_446_note` is not one of the six literal names, not
        because of where they sit. The file gains one note per round, so
        this says `every` and not a number.
        """
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry of pins, one per rule this file guards.",
            "_round_400_note": "Round 400 left the four pins below alone and "
                               "recorded why rather than editing them.",
            "pins": [{"id": "A1"}, {"id": "A2"}, {"id": "A3"}]})
        findings, _a, stats = self.repo.sweep()
        self.assertEqual(stats["prose_fields"], 2)
        self.assertEqual(codes(findings), ["J005"])
        self.assertEqual(findings[0].field, "_round_400_note")

    def test_a_nested_prose_field_is_swept_and_reported_by_its_path(self):
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry of entries, read by harness/real.py "
                        "which decides what to do with each of them.",
            "entries": {"alpha": {
                "why": "Registered here because it is read by "
                       "harness/ghost.py, which would have to be taught "
                       "about this entry before it could be removed."}}})
        self.repo.write_text("harness/real.py", "open('state/reg.json')\n")
        findings, _a, stats = self.repo.sweep()
        self.assertEqual(stats["prose_fields"], 2)
        self.assertEqual(stats["nested_fields"], 1)
        self.assertEqual(codes(findings), ["J001"])
        self.assertEqual(findings[0].field, "entries.alpha.why")

    def test_a_nested_count_is_checked_against_its_PARENT_not_the_artefact(self):
        """The category error a depth sweep makes by default.

        `entries.alpha.why` says "the two checks below"; `checks` is a
        collection of the ENTRY, not of the file. Counting it against the
        file's 5-entry `entries` map would invent a finding, and counting the
        file's own `_comment` against the entry would miss one.
        """
        self.repo.write_json("state/reg.json", {
            "_comment": "A registry. The five entries below each name a "
                        "rule and the check that is claimed to catch it.",
            "entries": {
                "alpha": {"why": "Kept because the two checks below are the "
                                 "only ones that ever went red for it.",
                          "checks": ["c1", "c2", "c3"]},
                "beta": {}, "gamma": {}, "delta": {}, "epsilon": {}}})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J005"])
        self.assertEqual(findings[0].field, "entries.alpha.why")
        self.assertIn("and the artefact has 3", findings[0].message)

    def test_an_empty_collection_is_still_a_collection(self):
        """`collections` filtered on truthiness until round 447.

        A list DRAINED to zero by a later round leaves the sentence that
        counted it standing, and that sentence was unreachable: with no
        `acknowledged` noun, J005 had nothing to compare against. This is the
        direction drift actually travels.
        """
        self.repo.write_json("state/reg.json", {
            "_comment": "An acknowledgement registry. One acknowledged "
                        "entry is left here, owned by another track's own "
                        "round record, and nothing else at all.",
            "acknowledged": []})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J005"])
        self.assertIn("and the artefact has 0", findings[0].message)

    def test_the_newest_round_stamp_is_an_assertion_and_older_ones_records(self):
        """A stamped note is a claim about the artefact AT THAT ROUND.

        Today's file cannot falsify a claim about round 400 — these
        registries are not append-only. It CAN falsify the newest one:
        nothing in the artefact says anything happened after it.
        """
        self.repo.write_json("state/reg.json", {
            "_round_400_note": "Round 400 registered the two pins below and "
                               "paid neither of them, which is the debt.",
            "_round_410_note": "Round 410 added one more, so the queue is "
                               "three pins deep and still unpaid here.",
            "pins": [{"id": "A1"}, {"id": "A2"}, {"id": "A3"}, {"id": "A4"}]})
        findings, _a, _s = self.repo.sweep()
        by_field = {f.field: f.code for f in findings}
        self.assertEqual(by_field,
                         {"_round_400_note": "J007",
                          "_round_410_note": "J005"})

    def test_the_newest_stamp_rule_needs_no_list_of_rounds(self):
        """Derived from the artefact: add a newer note and the blame moves."""
        obj = {
            "_round_400_note": "Round 400 registered the two pins below and "
                               "paid neither of them, which is the debt.",
            "_round_410_note": "Round 410 added one more, so the queue is "
                               "three pins deep and still unpaid here.",
            "_round_420_note": "Round 420 counted the pins again and makes "
                               "the tally four pins, which is what is here.",
            "pins": [{"id": "A1"}, {"id": "A2"}, {"id": "A3"}, {"id": "A4"}]}
        self.repo.write_json("state/reg.json", obj)
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(sorted(codes(findings)), ["J007", "J007"])

    # -- J012: the count whose noun is a per-element FIELD ----------------

    def test_J012_a_field_count_with_no_sibling_named(self):
        """Round 435's next-steps item 2, unpaid for twelve rounds."""
        self.repo.write_json("state/reg.json", {
            "_": "A pin registry. Nineteen guardian labels are carried "
                 "below, one per directional pin in this file.",
            "pins": [{"id": "A%d" % i, "guardian": "g%d" % i}
                     for i in range(20)]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J012"])
        self.assertIn("20 element(s) carry it, 20 distinct value(s)",
                      findings[0].message)

    def test_J012_accepts_EITHER_reading_of_the_same_phrase(self):
        """PRESENT and DISTINCT are both honest readings; one must hold.

        Twenty elements carry `guardian` and they take three distinct
        values. "twenty guardian labels" and "three guardian labels" are
        each true under one reading, so neither is a finding; "eleven" is
        true under neither and is.
        """
        pins = [{"id": "A%d" % i, "guardian": "g%d" % (i % 3)}
                for i in range(20)]
        for said, expect in (("twenty", []), ("three", []), ("eleven",
                                                             ["J012"])):
            self.repo.close()
            self.repo = SyntheticRepo()
            self.repo.write_json("state/reg.json", {
                "_": "A pin registry. %s guardian labels are carried below, "
                     "one per directional pin in this file." % said.title(),
                "pins": pins})
            findings, _a, _s = self.repo.sweep()
            self.assertEqual(codes(findings), expect, said)

    def test_J012_hands_a_delta_sentence_to_J010_at_FIELD_scope(self):
        """A sentence splitter is not a claim's scope.

        WHICH file this one is derived from is a property of the document; a
        delta VERB is a property of the sentence. Scoping both to the
        sentence mis-fired on the live
        `state/whence/round-422/host-pins-plus-repointed.json`, whose header
        names its sibling 200 characters and one `SENTENCE_RE` split before
        the count it governs.
        """
        self.repo.write_json("state/base.json", {
            "_": "The base registry, whose entries this file was derived "
                 "from. Its own prose asserts nothing countable.",
            "pins": [{"id": "A%d" % i, "guardian": "g%d" % i}
                     for i in range(20)]})
        header = ("%s Nineteen guardian labels changed and nothing else "
                  "did (a parenthetical long enough to be split off here). "
                  "Eleven guardian labels changed in this file, which is "
                  "what the header above records.")
        pins = [{"id": "A%d" % i, "guardian": "h%d" % i} for i in range(20)]
        self.repo.write_json("state/reg.json", {
            "_": header % "Repointed from base.json.", "pins": pins})
        findings, _a, _s = self.repo.sweep()
        self.assertNotIn("J012", codes(findings))

        # The control: the SAME sentence, with the sibling reference removed
        # from the document. Nothing else changes, and J012 fires — so the
        # decline above is the hand-off and not an accident of the fixture.
        self.repo.close()
        self.repo = SyntheticRepo()
        self.repo.write_json("state/reg.json", {
            "_": header % "Repointed from the other registry.", "pins": pins})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(codes(findings), ["J012", "J012"])

    def test_a_true_zero_element_field_count_is_dropped(self):
        """J012's KNOWN recall cost, pinned so it is a decision.

        `no` and `zero` are number words because "no pins" is a real count
        of a CONTAINER. Before a per-element FIELD name they are English
        negation — "no edit text, no witness" — and reading them as 0 made
        both of J012's live hits on this corpus false. A genuine "no element
        carries `witness`" is dropped with them.
        """
        self.repo.write_json("state/reg.json", {
            "_": "A pin registry. No witness values are recorded below, "
                 "because this round measured the pins and not the guests.",
            "pins": [{"id": "A%d" % i, "witness": "w%d" % i,
                      "guardian": "g"} for i in range(20)]})
        findings, _a, _s = self.repo.sweep()
        self.assertEqual(findings, [])

    # -- artefact-scoped codes are reported once per artefact -------------

    def test_J002_is_reported_once_however_many_fields_repeat_it(self):
        self.repo.write_json("state/orphan.json", {
            "_comment": "A registry of things, read by harness/real.py and "
                        "by nothing else in this repository at all.",
            "_round_400_note": "Round 400 left it alone. Still read by "
                               "harness/real.py and by nothing else here.",
            "items": [{"id": "A1"}]})
        self.repo.write_text("harness/real.py", "print('unrelated')\n")
        findings, _a, stats = self.repo.sweep()
        self.assertEqual(stats["prose_fields"], 2)
        self.assertEqual(codes(findings), ["J002"])

    def test_a_captured_payload_is_not_a_self_description(self):
        """`description` and `summary` are excluded, and it is measured.

        They are the key names in the OpenAI tool payloads under
        `nuc/hermes-dump/` and the skill-frontmatter mirrors under
        `state/skills*/` — 803 fields this repo RECORDED rather than
        ASSERTED. Reading one as a self-description checks somebody else's
        sentence against this repo's file.
        """
        self.repo.write_json("state/capture.json", {
            "tools": [{"function": {
                "name": "grep",
                "description": "Search file contents. Supply three patterns "
                               "at most; this text belongs to another "
                               "system and asserts nothing about this file."}}],
            "summary": "A captured request. It names two tools, which is a "
                       "fact about the capture and not about this registry."})
        _f, _a, stats = self.repo.sweep()
        self.assertEqual(stats["artefacts"], 0)
        self.assertEqual(stats["prose_fields"], 0)

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
        arts, n_json, _u, _s, _o = selfdesc_check.scan_tree(ROOT)
        self.assertEqual(self.stats["artefacts"], len(arts))
        self.assertEqual(self.stats["json_files"], n_json)
        self.assertGreaterEqual(self.stats["artefacts"], 20)

    def test_the_coverage_token_is_not_the_finding_count(self):
        """Round 447. It was, exactly, until this round.

        `checked_fields` counts fields where a lookup RAN; `prose_fields -
        silent_fields` counts fields that produced a FINDING. The published
        token was the second one wearing the first one's name, so it read
        `0/28` on a clean corpus and could only rise as the corpus got
        worse. On a tree with at least one TRUE claim the two must differ.
        """
        yielded = self.stats["prose_fields"] - self.stats["silent_fields"]
        self.assertGreater(self.stats["checked_fields"], yielded)
        self.assertGreaterEqual(self.stats["claims"],
                                self.stats["checked_fields"])

    def test_the_sweep_reaches_nested_and_round_stamped_fields(self):
        """Round 435 item 3, closed. Two independent gaps, not one.

        The NAME gap: `_round_446_note` is top-level and was skipped because
        it is not one of the six literal idiom names. The DEPTH gap: a `why`
        inside an element was never reached at all. Both are asserted by
        lower bounds rather than by counts, because both populations grow.
        """
        arts, _n, _u, _s, _o = selfdesc_check.scan_tree(ROOT)
        nested = [f for a in arts for f in a.fields if f.depth]
        stamped = [f for a in arts for f in a.fields if f.round is not None]
        self.assertGreater(len(nested), 100, "depth gap re-opened")
        self.assertGreater(len(stamped), 10, "name gap re-opened")
        self.assertGreater(self.stats["nested_fields"], 100)

    def test_the_unprobed_registrys_newest_note_agrees_with_its_own_map(self):
        """The live defect round 447 found, pinned so it rots loudly.

        The batch depth is carried in prose and re-quoted into
        `state/research-state.md`'s next steps every round. It was `SIXTEEN`
        against a 26-entry map for four rounds because no checker had ever
        read the field it lives in. This asserts the two agree by
        re-deriving the count, not by naming a number.
        """
        rel = "state/known-unprobed-skills.json"
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            data = json.load(f)
        art = selfdesc_check.Artefact(rel, data)
        newest = [f for f in art.fields
                  if f.round is not None and not f.superseded]
        self.assertTrue(newest, "no round-stamped note in %s" % rel)
        live = [f for f in self.findings
                if f.rel == rel and f.code in ("J005", "J012")]
        self.assertEqual([str(f) for f in live], [],
                         "the newest note disagrees with the map it "
                         "describes; %d entries" % len(data["skills"]))

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


class TestTheSizeCapAnnouncesWhatItDropped(unittest.TestCase):
    """Round 513. `MAX_BYTES` was a silent `continue`, so a file that GREW
    past the cap left the audited population and the only trace was the
    `artefacts` count going down by one. Round 513 grew
    `harness/readset-map.json` past 2 MB and measured exactly that: 61 -> 60,
    no finding, no line. A cap that does not name what it dropped makes its
    own denominator a fact about the cap."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, text):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_an_oversize_object_json_is_named_not_merely_dropped(self):
        pad = "x" * (selfdesc_check.MAX_BYTES + 10)
        # indent=1, so the file is multi-line: a ONE-line JSON object is
        # indistinguishable from JSONL by `_is_jsonl` and would be
        # classified as a stream instead.
        self.write("state/big.json",
                   json.dumps({"_comment": pad}, indent=1))
        arts, seen, _u, _s, oversize = selfdesc_check.scan_tree(self.tmp)
        self.assertEqual(arts, [])
        self.assertEqual(seen, 1)
        self.assertEqual(oversize, ["state/big.json"])

    def test_an_oversize_jsonl_log_is_a_stream_and_not_an_oversize_artefact(self):
        """The size check runs BEFORE the stream classification, so without
        this the report names 41 files of which 32 were never artefacts."""
        line = json.dumps({"e": "x" * 200}) + "\n"
        self.write("logs/round-999.json",
                   line * (selfdesc_check.MAX_BYTES // len(line) + 20))
        arts, _seen, _u, streams, oversize = selfdesc_check.scan_tree(self.tmp)
        self.assertEqual(arts, [])
        self.assertEqual(oversize, [])
        self.assertEqual(streams, ["logs/round-999.json"])

    def test_a_small_artefact_is_still_audited(self):
        self.write("state/small.json", json.dumps(
            {"_comment": "Written by `python3 x.py`. Read by harness/y.py."},
            indent=1))
        arts, _seen, _u, _s, oversize = selfdesc_check.scan_tree(self.tmp)
        self.assertEqual(oversize, [])
        self.assertEqual([a.rel for a in arts], ["state/small.json"])

    def test_the_report_prints_the_dropped_names_above_the_summary(self):
        import io as _io
        buf = _io.StringIO()
        selfdesc_check.report([], [], {
            "artefacts": 1, "json_files": 2, "prose_fields": 0,
            "silent_fields": 0, "nested_fields": 0, "checked_fields": 0,
            "claims": 0, "unparseable": [], "streams": 0,
            "oversize": ["state/big.json"], "must_claims": 0,
            "watched_claims": 0, "acknowledged": 0}, out=buf)
        text = buf.getvalue()
        self.assertIn("state/big.json", text)
        self.assertIn("NOT audited", text)
        self.assertLess(text.index("state/big.json"),
                        text.index("selfdesc-check:"))


if __name__ == "__main__":
    unittest.main()

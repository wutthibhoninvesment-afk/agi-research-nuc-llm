#!/usr/bin/env python3
"""Tests for carryforward_check.py (round 369).

Offline; no model calls. `TestLiveCorpus` is the enforcement; everything else
exists so that it cannot pass vacuously.

Several tests here are FROZEN REGRESSIONS of the first version's mistakes.
That version inferred "was this bank scored?" from prose and got 5 of 13
verdicts wrong, in both directions, from four independent causes. Each cause
has a test named after the round that exposed it, with the real sentence from
the corpus as the fixture — because the fix for each was a one-line regex
change, and a one-line regex change is exactly what a later round will undo
while tidying.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

import carryforward_check as cf

ROOT = cf.DEFAULT_REPO_ROOT


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class TestBankDiscovery(unittest.TestCase):
    """A list of known locations is what the first version got wrong."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "state"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_six_live_naming_conventions_are_found(self):
        for rel in ("state/round-017-predictions.md",
                    "state/whence/round-368/PREDICTIONS.md",
                    "state/trigger-eval/round-021-predictions.md",
                    "nuc/predictions-e-round358.md",
                    "state/round-400/PREDICTIONS.md",
                    "state/swe/round-359/PREDICTIONS.md"):
            write(os.path.join(self.tmp, rel), "x")
        banks, unnumbered = cf.find_banks(self.tmp)
        self.assertEqual(sorted(banks), [17, 21, 358, 359, 368, 400])
        self.assertEqual(unnumbered, [])

    def test_the_nuc_convention_is_found_this_is_the_regression(self):
        """`nuc/predictions-e-roundNNN.md` lives OUTSIDE state/.

        The first draft globbed four patterns under `state/` and missed this
        one, which made rounds 340/352/358/364 read as having no bank at all
        — four false findings caused by enumerating an obligation from the
        places you already know about.
        """
        write(os.path.join(self.tmp, "nuc/predictions-e-round364.md"), "x")
        banks, _ = cf.find_banks(self.tmp)
        self.assertIn(364, banks)

    def test_a_bank_with_no_round_number_is_reported_not_dropped(self):
        write(os.path.join(self.tmp, "nuc/predictions-e1.md"), "x")
        banks, unnumbered = cf.find_banks(self.tmp)
        self.assertEqual(banks, {})
        self.assertEqual(unnumbered, ["nuc/predictions-e1.md"])

    def test_a_knowledge_file_about_scoring_is_not_a_bank(self):
        write(os.path.join(self.tmp,
                           "knowledge/round-187-prediction-partial-score.md"), "x")
        banks, unnumbered = cf.find_banks(self.tmp)
        self.assertEqual((banks, unnumbered), ({}, []))

    def test_vendored_trees_are_skipped(self):
        write(os.path.join(self.tmp,
                           ".venv/lib/x/round-999-predictions.md"), "x")
        self.assertEqual(cf.find_banks(self.tmp)[0], {})


class TestScannerRegressions(unittest.TestCase):
    """Four false verdicts from the first version, frozen as fixtures."""

    def test_round_366_lowercase_verdict_counts(self):
        # `HIT|MISS` was case-sensitive; round 366 wrote "hit".
        text = ("banked in `state/whence/round-366/PREDICTIONS.md` and scored "
                "there: **P4/P5/P6 hit, P1/P2/P3 miss**.")
        self.assertIsNotNone(cf.score_evidence(text, 366))

    def test_round_139_one_unscorable_does_not_veto_four_verdicts(self):
        # The negation window is characters around the match, not the line.
        text = ("- **Scored `state/round-139-predictions.md` from raw log "
                "evidence:** P1 (redeploy happened) HIT, P2 HIT, P4 HIT, P5 "
                "(no double-launch/gap) HIT; P3 (safety valve fires live on a "
                "real streak) still unscorable — no 3-consecutive-failure "
                "streak has recurred since the redeploy.")
        self.assertIsNotNone(cf.score_evidence(text, 139))

    def test_a_genuinely_unscored_bank_is_still_negated(self):
        text = ("- **`state/whence/round-362/PREDICTIONS.md` was banked and "
                "never scored** — 11 predictions, 0 HIT, 0 MISS.")
        self.assertIsNone(cf.score_evidence(text, 362))

    def test_round_352s_verdict_is_not_evidence_about_round_349(self):
        # A possessive over a prediction credits the verdict to THAT round.
        line = "Round 352's P14 is heading for a MISS. Not relaunched."
        self.assertFalse(cf._attributable(line, 349))
        self.assertTrue(cf._attributable(line, 352))

    def test_a_bare_mention_of_another_round_is_not_an_attribution(self):
        # The first fix over-corrected and rejected real table rows.
        line = ("| P2 | >=60 of 70 `ok` outcomes are real | **HIT** — as "
                "round 365 measured |")
        self.assertTrue(cf._attributable(line, 366))

    def test_round_141_discharged_three_banks_in_one_sentence(self):
        # No possessive-form pattern reaches this; `_names_round` does.
        line = ("- **Scored every prediction from the raw artifacts:** round "
                "123 3 HIT/1 MISS; round 129 8 HIT/1 PARTIAL/1 N/A; round 135 "
                "6 HIT/2 small MISS.")
        for n in (123, 129, 135):
            self.assertTrue(cf._names_round(line, n, []), n)
        self.assertFalse(cf._names_round(line, 137, []))


class TestFindings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "state"))
        os.makedirs(os.path.join(self.tmp, "knowledge"))
        write(os.path.join(self.tmp, "state/research-state.md"), "# s\n")
        write(os.path.join(self.tmp, "state/research-state-archive.md"), "# a\n")
        write(os.path.join(self.tmp, "state/round-500-predictions.md"), "P1: x")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self, ledger=None, latest_round=500):
        if ledger is not None:
            write(os.path.join(self.tmp, cf.LEDGER_FILE),
                  json.dumps({"banks": ledger}))
        corpus = cf.Corpus(self.tmp)
        banks, _ = cf.find_banks(self.tmp)
        led, err = cf.load_ledger(self.tmp)
        return [f[0] for f in cf.findings(self.tmp, corpus, banks, led, err,
                                          latest_round)]

    def test_k001_a_bank_with_no_ledger_entry(self):
        self.assertIn("K001", self.run_check())

    def test_k002_a_scoring_claim_whose_quote_moved(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "nothing here")
        codes = self.run_check({"500": {
            "bank": "state/round-500-predictions.md", "status": "scored",
            "scored_by": 501, "where": "knowledge/round-501-x.md",
            "quote": "P1 HIT"}})
        self.assertIn("K002", codes)

    def test_a_scoring_claim_that_re_derives_is_clean(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "P1 HIT here")
        self.assertEqual(self.run_check({"500": {
            "bank": "state/round-500-predictions.md", "status": "scored",
            "scored_by": 501, "where": "knowledge/round-501-x.md",
            "quote": "P1 HIT"}}), [])

    def test_k003_an_entry_naming_a_bank_that_does_not_exist(self):
        codes = self.run_check({"500": {
            "bank": "state/round-500-predictions.md", "status": "scored",
            "scored_by": 501, "where": "state/research-state.md",
            "quote": "# s"},
            "777": {"bank": "state/round-777-predictions.md",
                    "status": "unscored", "owner": "x", "why": "y"}})
        self.assertIn("K003", codes)

    def test_k003_an_unscored_entry_whose_debt_has_been_paid_is_a_mute_button(self):
        write(os.path.join(self.tmp, "knowledge/round-500-x.md"),
              "## 4. Predictions scored: 9 HIT / 5 MISS")
        codes = self.run_check({"500": {
            "bank": "state/round-500-predictions.md", "status": "unscored",
            "owner": "skills(B)", "why": "deferred"}})
        self.assertIn("K003", codes)

    def test_k003_a_missing_required_field(self):
        codes = self.run_check({"500": {
            "bank": "state/round-500-predictions.md", "status": "scored",
            "scored_by": 501, "where": "state/research-state.md"}})
        self.assertIn("K003", codes)

    def test_k004_is_a_warning_and_never_the_exit_code(self):
        # Older than one full rotation, so its owning track has had a turn.
        codes = self.run_check({"500": {
            "bank": "state/round-500-predictions.md", "status": "unscored",
            "owner": "skills(B)", "why": "deferred"}}, latest_round=510)
        self.assertEqual(codes, ["K004"])
        self.assertEqual(cf.SEV["K004"], "WARN")

    def test_a_young_unscored_debt_is_silent(self):
        write(os.path.join(self.tmp, "state/round-499-predictions.md"), "x")
        corpus = cf.Corpus(self.tmp)
        banks, _ = cf.find_banks(self.tmp)
        led = {"499": {"bank": "state/round-499-predictions.md",
                       "status": "unscored", "owner": "x", "why": "y"},
               "500": {"bank": "state/round-500-predictions.md",
                       "status": "unscored", "owner": "x", "why": "y"}}
        codes = [f[0] for f in cf.findings(self.tmp, corpus, banks, led, None,
                                           latest_round=502)]
        self.assertEqual(codes, [])   # both younger than one rotation

    def test_k004_fires_on_a_partial_discharge(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "P1 HIT")
        codes = self.run_check({"500": {
            "bank": "state/round-500-predictions.md", "status": "scored",
            "scored_by": 501, "where": "knowledge/round-501-x.md",
            "quote": "P1 HIT", "remainder": "P2-P6 never named"}})
        self.assertEqual(codes, ["K004"])

    def test_a_note_is_narrative_and_does_not_read_as_debt(self):
        # Round 375. Rounds 373 and 374 wrote "None outstanding: ..." into
        # `remainder`, and K004 -- which reads the field's PRESENCE --
        # reported two partial discharges the record itself denies.
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "P1 HIT")
        entry = {"bank": "state/round-500-predictions.md", "status": "scored",
                 "scored_by": 501, "where": "knowledge/round-501-x.md",
                 "quote": "P1 HIT",
                 "note": "None outstanding: P1-P6 are each scored by number."}
        self.assertEqual(self.run_check({"500": entry}), [])

    def test_a_note_does_not_silence_a_real_remainder(self):
        # The two fields are independent: `note` is not an override.
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "P1 HIT")
        entry = {"bank": "state/round-500-predictions.md", "status": "scored",
                 "scored_by": 501, "where": "knowledge/round-501-x.md",
                 "quote": "P1 HIT", "note": "context",
                 "remainder": "P2-P6 never named"}
        self.assertEqual(self.run_check({"500": entry}), ["K004"])

    def test_an_empty_remainder_or_note_is_rot(self):
        # An empty `remainder` warns for a debt it does not name -- the
        # mute button's inverse, a cry-wolf.
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "P1 HIT")
        base = {"bank": "state/round-500-predictions.md", "status": "scored",
                "scored_by": 501, "where": "knowledge/round-501-x.md",
                "quote": "P1 HIT"}
        for field in ("remainder", "note"):
            entry = dict(base)
            entry[field] = "   "
            self.assertIn("K003", self.run_check({"500": entry}), field)

    def test_an_absent_ledger_is_an_error_not_a_silent_pass(self):
        codes = self.run_check()
        self.assertIn("K003", codes)


class TestEnterGeneratesAnEntryTheCheckerAccepts(unittest.TestCase):
    """Round 501. `--enter` runs K002/K005/K006 and the pointer rule FORWARDS.

    The property under test is not "it produces an entry" — `--suggest` does
    that and round 495 showed what its entries are worth. It is that every
    entry it produces SURVIVES this module's own error codes, and that it
    declines rather than guesses when no line in the round's own knowledge
    file can.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "state"))
        os.makedirs(os.path.join(self.tmp, "knowledge"))
        write(os.path.join(self.tmp, "state/round-700-predictions.md"), "P1 ...")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self):
        corpus = cf.Corpus(self.tmp)
        banks, _ = cf.find_banks(self.tmp)
        ledger, _ = cf.load_ledger(self.tmp)
        return corpus, banks, ledger

    def test_a_verdict_line_becomes_the_anchor(self):
        line = ("| P3 | the sweep finds between 25 and 70 candidates | "
                "**43** | HIT |")
        write(os.path.join(self.tmp, "knowledge/round-700-a.md"),
              "# round 700\n\n## 8. Predictions\n\n%s\n" % line)
        corpus, banks, ledger = self.build()
        entry, diag = cf.enter(self.tmp, corpus, banks, ledger, 700)
        self.assertEqual(diag["verdict"], "scored")
        self.assertEqual(entry["status"], "scored")
        self.assertEqual(entry["scored_by"], 700)
        self.assertEqual(entry["where"], "knowledge/round-700-a.md")
        self.assertEqual(entry["quote"], line)

    def test_a_promise_of_a_scoring_yields_unscored(self):
        """THE falsifier, and it is round 492's real shape.

        Round 492's knowledge file opens `(state/whence/round-492/
        predictions.md). Scored in §10.` and then ends at `## 9.`. There is
        no §10, no HIT and no MISS in the file, and `--suggest` proposed a
        `scored` entry quoting the promise (round 495). A generator that
        does the same has re-introduced the bug that ledger exists to
        prevent, so this test is the gate on the whole feature.
        """
        write(os.path.join(self.tmp, "knowledge/round-700-a.md"),
              "# round 700\n\nPredictions banked (`state/round-700-"
              "predictions.md`). Scored in section 10 below.\n\n"
              "## 9. Tests and gates\n\nAll green.\n")
        corpus, banks, ledger = self.build()
        entry, diag = cf.enter(self.tmp, corpus, banks, ledger, 700)
        self.assertEqual(diag["verdict"], "unscored/no-anchor")
        self.assertEqual(entry["status"], "unscored")
        self.assertIn("promise of a scoring is not a scoring", entry["why"])

    def test_a_round_with_no_knowledge_file_is_unscored_and_says_which(self):
        corpus, banks, ledger = self.build()
        entry, diag = cf.enter(self.tmp, corpus, banks, ledger, 700)
        self.assertEqual(diag["verdict"], "unscored/no-knowledge-file")
        self.assertIn("no knowledge/round-700-*.md exists", entry["why"])

    def test_an_anchor_occurring_twice_is_refused_this_is_K005_forwards(self):
        line = ("| P3 | the sweep finds between 25 and 70 candidates | "
                "**43** | HIT |")
        write(os.path.join(self.tmp, "knowledge/round-700-a.md"),
              "%s\n\nrepeated verbatim below\n\n%s\n" % (line, line))
        corpus, banks, ledger = self.build()
        entry, _ = cf.enter(self.tmp, corpus, banks, ledger, 700)
        self.assertEqual(entry["status"], "unscored")

    def test_an_anchor_another_round_also_carries_is_refused_K006_forwards(self):
        line = ("| P3 | the sweep finds between 25 and 70 candidates | "
                "**43** | HIT |")
        write(os.path.join(self.tmp, "knowledge/round-700-a.md"), line + "\n")
        write(os.path.join(self.tmp, "knowledge/round-701-b.md"),
              "quoting round 700 while reviewing it:\n%s\n" % line)
        corpus, banks, ledger = self.build()
        entry, _ = cf.enter(self.tmp, corpus, banks, ledger, 700)
        self.assertEqual(entry["status"], "unscored")

    def test_a_line_under_the_floor_is_not_an_anchor(self):
        write(os.path.join(self.tmp, "knowledge/round-700-a.md"),
              "| P3 | fast | HIT |\n")
        corpus, banks, ledger = self.build()
        entry, _ = cf.enter(self.tmp, corpus, banks, ledger, 700)
        self.assertEqual(entry["status"], "unscored")

    def test_a_negated_verdict_line_is_not_a_scoring(self):
        write(os.path.join(self.tmp, "knowledge/round-700-a.md"),
              "P4 was never scored and carries no HIT or MISS of its own, "
              "so it is owed to a later round entirely.\n")
        corpus, banks, ledger = self.build()
        entry, _ = cf.enter(self.tmp, corpus, banks, ledger, 700)
        self.assertEqual(entry["status"], "unscored")

    def test_a_line_crediting_another_round_is_not_this_rounds_scoring(self):
        write(os.path.join(self.tmp, "knowledge/round-700-a.md"),
              "Round 699's P4 is a MISS by a factor of four, which this "
              "round re-derived from the committed artefact before writing.\n")
        corpus, banks, ledger = self.build()
        entry, _ = cf.enter(self.tmp, corpus, banks, ledger, 700)
        self.assertEqual(entry["status"], "unscored")

    def test_the_generated_entry_passes_the_checkers_own_findings(self):
        """The round trip. A generator whose output the checker rejects is
        worse than no generator: it produces a red the next round inherits."""
        line = ("| P3 | the sweep finds between 25 and 70 candidates | "
                "**43** | HIT |")
        write(os.path.join(self.tmp, "knowledge/round-700-a.md"),
              "# round 700\n\n%s\n" % line)
        write(os.path.join(self.tmp, cf.LEDGER_FILE),
              json.dumps({"banks": {}}, indent=1) + "\n")
        corpus, banks, ledger = self.build()
        entry, _ = cf.enter(self.tmp, corpus, banks, ledger, 700)
        self.assertIsNone(cf.write_entry(self.tmp, 700, entry))
        ledger, err = cf.load_ledger(self.tmp)
        found = cf.findings(self.tmp, corpus, banks, ledger, err, 700)
        self.assertEqual([f for f in found if cf.SEV[f[0]] == "ERROR"], [],
                         "\n".join("%s %s" % (f[0], f[2]) for f in found))


class TestWriteEntryIsByteStableAndRefusesToGuess(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "state"))
        self.path = os.path.join(self.tmp, cf.LEDGER_FILE)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def seed(self, banks=None):
        write(self.path, json.dumps(
            {"_comment": "seed — with a non-ascii dash",
             "banks": banks if banks is not None else {}}, indent=1) + "\n")

    def test_a_write_reproduces_the_files_own_serialisation(self):
        """The ledger on disk IS `json.dumps(doc, indent=1) + newline` with
        `ensure_ascii` at its default. Writing it any other way turns a
        three-entry addition into a whole-file reformat."""
        self.seed()
        cf.write_entry(self.tmp, 700, {"bank": "state/round-700-predictions.md",
                                       "status": "scored", "scored_by": 700,
                                       "where": "knowledge/round-700-a.md",
                                       "quote": "x" * 50})
        raw = open(self.path, encoding="utf-8").read()
        self.assertEqual(json.dumps(json.loads(raw), indent=1) + "\n", raw)
        self.assertIn("\\u2014", raw)

    def test_an_existing_entry_is_not_overwritten_without_force(self):
        self.seed({"700": {"status": "scored"}})
        err = cf.write_entry(self.tmp, 700, {"status": "unscored",
                                             "owner": "skills(B)",
                                             "bank": "b", "why": "w"})
        self.assertIn("already has an entry", err)
        self.assertEqual(json.load(open(self.path))["banks"]["700"],
                         {"status": "scored"})
        self.assertIsNone(cf.write_entry(
            self.tmp, 700, {"status": "unscored", "owner": "skills(B)",
                            "bank": "b", "why": "w"}, force=True))

    def test_an_unscored_entry_with_no_owner_is_refused(self):
        """It would be a K003 the moment it lands. Naming who owes the
        scoring is a judgement and the generator will not make one up."""
        self.seed()
        err = cf.write_entry(self.tmp, 700, {"bank": "b", "status": "unscored",
                                             "owner": "", "why": "w"})
        self.assertIn("no owner", err)
        self.assertEqual(json.load(open(self.path))["banks"], {})


class TestStagedCheckFiresWhereTheAuthorStillIs(unittest.TestCase):
    """Round 501's commit-time tier. Trigger discipline is the whole test."""

    def test_the_knowledge_file_fires_and_the_bank_alone_does_not(self):
        banks = {700: ["state/round-700-predictions.md"]}
        bank_only = cf.staged_gaps(".", ["state/round-700-predictions.md"],
                                   banks, {})
        self.assertEqual(bank_only, [],
                         "a bank is committed BEFORE measuring; warning there "
                         "cries wolf at the one round doing D-013 right")
        closing = cf.staged_gaps(".", ["knowledge/round-700-x.md"], banks, {})
        self.assertEqual(closing, [(700, "knowledge/round-700-x.md",
                                    "state/round-700-predictions.md")])

    def test_a_round_already_in_the_ledger_is_silent(self):
        banks = {700: ["state/round-700-predictions.md"]}
        self.assertEqual(
            cf.staged_gaps(".", ["knowledge/round-700-x.md"], banks,
                           {"700": {"status": "scored"}}), [])

    def test_a_knowledge_file_for_a_round_that_banked_nothing_is_silent(self):
        self.assertEqual(
            cf.staged_gaps(".", ["knowledge/round-700-x.md"], {}, {}), [])

    def test_the_pre_commit_hook_carries_the_advisory_ledger_step(self):
        """Same assertion shape as `test_wiring_audit.py`'s for round 499's
        step, because it is the same design: advisory, fail-open, last line
        `exit 0`. A gate here can destroy the uncommitted diff of a round
        with no turns left."""
        harness = os.path.join(ROOT, "harness")
        if not os.path.isdir(harness):
            self.skipTest("no harness/ in this tree")
        sys.path.insert(0, harness)
        import escalationguard as eg
        body = eg.hook_script()
        self.assertIn("carryforward_check.py", body)
        self.assertIn("--staged-check", body)
        step = body.split("--staged-check")[-1]
        self.assertIn("|| true", step)
        self.assertTrue(body.rstrip().endswith("exit 0"))


class TestLiveCorpus(unittest.TestCase):
    """The enforcement. Everything above exists so this cannot pass vacuously."""

    def test_the_live_ledger_accounts_for_every_bank_on_disk(self):
        corpus = cf.Corpus(ROOT)
        banks, _ = cf.find_banks(ROOT)
        led, err = cf.load_ledger(ROOT)
        self.assertIsNone(err)
        found = cf.findings(ROOT, corpus, banks, led, err,
                            max(list(banks) + list(corpus.sections)))
        errors = [f for f in found if cf.SEV[f[0]] == "ERROR"]
        self.assertEqual(errors, [], "\n".join("%s %s" % (f[0], f[2])
                                               for f in errors))

    def test_the_generator_refuses_the_live_round_492_bank(self):
        """Round 495's finding, pinned against the real file rather than a
        fixture. Round 492 banked P1-P14 and never scored them; its
        knowledge file promises a section that was never written. If
        `--enter` ever proposes `scored` for it, the generator has become
        the prose classifier round 369 deleted, and it would be laundering
        the one debt in this ledger that is genuinely outstanding.
        """
        corpus = cf.Corpus(ROOT)
        banks, _ = cf.find_banks(ROOT)
        led, _ = cf.load_ledger(ROOT)
        if 492 not in banks:
            self.skipTest("round 492's bank is not in this tree")
        entry, diag = cf.enter(ROOT, corpus, banks, led, 492)
        self.assertEqual(entry["status"], "unscored", diag)
        self.assertEqual(led["492"]["status"], "unscored",
                         "the live ledger and the generator must agree that "
                         "round 492's bank is still owed")

    def test_every_entry_this_round_generated_is_re_derivable(self):
        """The three K001s round 501 closed, checked the way the ledger is
        checked: the quote must be present in `where`, present ONCE, and
        matched by no scope the entry does not name."""
        corpus = cf.Corpus(ROOT)
        led, _ = cf.load_ledger(ROOT)
        checked = 0
        for n in ("498", "499", "500"):
            e = led.get(n)
            if not e or e.get("status") != "scored":
                continue
            body = cf.read(os.path.join(ROOT, e["where"]))
            self.assertEqual(body.count(e["quote"]), 1,
                             "round %s: anchor is not unique in %s"
                             % (n, e["where"]))
            self.assertEqual(
                corpus.foreign_scopes(e["quote"], {int(n)}), [],
                "round %s: anchor also matches a foreign scope" % n)
            checked += 1
        self.assertEqual(checked, 3)

    def test_no_live_entry_uses_remainder_for_narrative(self):
        # Round 375's own finding, pinned as a SHAPE rather than a count: a
        # `remainder` opening with a denial of debt is the misuse, and the
        # field it belongs in is `note`. Not a warning-count pin -- warning
        # counts move whenever a bank ages past a rotation.
        led, err = cf.load_ledger(ROOT)
        self.assertIsNone(err)
        for n, e in sorted(led.items()):
            rem = (e.get("remainder") or "").strip().lower()
            self.assertFalse(
                rem.startswith("none outstanding") or rem.startswith("nothing "),
                "round %s: `remainder` denies the debt it declares; that "
                "text belongs in `note`" % n)

    def test_every_scored_entry_re_derives_against_the_file_it_cites(self):
        """K002's whole point: the ledger is checked, not trusted."""
        led, _ = cf.load_ledger(ROOT)
        checked = 0
        for n, e in led.items():
            if e.get("status") != "scored":
                continue
            body = cf.read(os.path.join(ROOT, e["where"]))
            self.assertIn(e["quote"], body, "round %s cites %s" % (n, e["where"]))
            checked += 1
        self.assertGreater(checked, 40)

    def test_the_six_naming_conventions_are_all_still_represented(self):
        """If a convention disappears, the discovery sweep lost coverage."""
        banks, _ = cf.find_banks(ROOT)
        paths = [p for v in banks.values() for p in v]
        for marker in ("state/round-", "nuc/predictions-e-round",
                       "state/trigger-eval/round-", "/PREDICTIONS.md"):
            self.assertTrue(any(marker in p for p in paths), marker)


class TestAnchorLocates(unittest.TestCase):
    """K005/K006 (round 465): presence is not location.

    K002 asks `quote in body`. These ask the two questions presence does not
    answer -- is it there ONCE, and would it have been there if `where` named
    somebody else's file.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "state"))
        os.makedirs(os.path.join(self.tmp, "knowledge"))
        write(os.path.join(self.tmp, "state/research-state.md"), "# s\n")
        write(os.path.join(self.tmp, "state/research-state-archive.md"), "# a\n")
        write(os.path.join(self.tmp, "state/round-500-predictions.md"), "P1: x")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def entry(self, **kw):
        e = {"bank": "state/round-500-predictions.md", "status": "scored",
             "scored_by": 501, "where": "knowledge/round-501-x.md",
             "quote": "P1 HIT"}
        e.update(kw)
        return {"500": e}

    def run_check(self, ledger, latest_round=500):
        write(os.path.join(self.tmp, cf.LEDGER_FILE),
              json.dumps({"banks": ledger}))
        corpus = cf.Corpus(self.tmp)
        banks, _ = cf.find_banks(self.tmp)
        led, err = cf.load_ledger(self.tmp)
        return [f[0] for f in cf.findings(self.tmp, corpus, banks, led, err,
                                          latest_round)]

    # ---- K005: ambiguity -------------------------------------------------

    def test_k005_a_quote_present_twice_cannot_be_located(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"),
              "intro P1 HIT\n\nlater, again: P1 HIT\n")
        self.assertIn("K005", self.run_check(self.entry()))

    def test_a_quote_present_once_is_not_k005(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "P1 HIT once")
        self.assertNotIn("K005", self.run_check(self.entry()))

    def test_round_421s_real_anchor_is_the_frozen_k005_fixture(self):
        """The entry that made this code exist, with the corpus's own text.

        Round 421's knowledge file scores its bank in one line of the round
        summary and again in the section heading below it, so the anchor
        `**6 hits, 2 misses.**` appears twice and points at neither. This is
        the OLD anchor, quoted deliberately: pasting a LIVE one into a file
        the checker reads is what broke rounds 15 and 421 in the first place.
        """
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"),
              "Scored in \u00a77: **6 hits, 2 misses.** Both misses are in the "
              "same\ndirection.\n\n## 7. Predictions, scored\n\n"
              "**6 hits, 2 misses.** Banked before the analyser existed.\n")
        codes = self.run_check(self.entry(quote="**6 hits, 2 misses.**"))
        self.assertIn("K005", codes)
        self.assertNotIn("K002", codes)

    # ---- K006: the `where` substitution ----------------------------------

    def test_k006_a_quote_that_another_rounds_file_also_satisfies(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"),
              "## 8. Predictions, scored\n")
        write(os.path.join(self.tmp, "knowledge/round-333-y.md"),
              "## 8. Predictions, scored\n")
        self.assertIn("K006", self.run_check(
            self.entry(quote="## 8. Predictions, scored")))

    def test_the_banking_round_and_the_scoring_round_are_both_own_scope(self):
        """Round 141 scored three inherited banks in one sentence.

        An entry for round 500 scored BY round 501 legitimately matches in
        both rounds' files; only a third round's file is a substitution the
        entry could have made by mistake.
        """
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "shared line\n")
        write(os.path.join(self.tmp, "knowledge/round-500-own.md"), "shared line\n")
        self.assertNotIn("K006", self.run_check(self.entry(quote="shared line")))

    def test_a_third_rounds_file_is_foreign_even_next_to_own_scope(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "shared line\n")
        write(os.path.join(self.tmp, "knowledge/round-500-own.md"), "shared line\n")
        write(os.path.join(self.tmp, "knowledge/round-222-z.md"), "shared line\n")
        self.assertIn("K006", self.run_check(self.entry(quote="shared line")))

    def test_the_substitution_unit_is_a_section_not_the_prose_file(self):
        """18 live entries name research-state(.archive) as `where`.

        Those files contain every round, so a file-level substitution would
        report every entry in the ledger. The candidate coordinate is the
        round SECTION -- which means a quote inside round 500's own section
        is own scope, and the same string inside round 222's section of the
        same file is foreign.
        """
        write(os.path.join(self.tmp, "state/research-state.md"),
              "### Round 500 - x\n\nthe scoring sentence\n")
        codes = self.run_check(self.entry(
            where="state/research-state.md", scored_by=500,
            quote="the scoring sentence"))
        self.assertNotIn("K006", codes)
        write(os.path.join(self.tmp, "state/research-state.md"),
              "### Round 500 - x\n\nthe scoring sentence\n\n"
              "### Round 222 - y\n\nthe scoring sentence\n")
        self.assertIn("K006", self.run_check(self.entry(
            where="state/research-state.md", scored_by=500,
            quote="the scoring sentence")))

    def test_k006_is_silent_when_the_anchor_is_unique_to_its_round(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"),
              "P1 HIT, and nobody else says this\n")
        write(os.path.join(self.tmp, "knowledge/round-333-y.md"), "unrelated\n")
        self.assertEqual(self.run_check(
            self.entry(quote="P1 HIT, and nobody else says this")), [])

    def test_an_absent_quote_is_k002_only_and_not_k005_or_k006(self):
        """The three codes are a chain, not a committee.

        If the anchor is not in `where` at all there is nothing to count
        occurrences of, and reporting all three for one defect would triple
        the count in the line the driver logs.
        """
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "nothing here")
        write(os.path.join(self.tmp, "knowledge/round-333-y.md"), "P1 HIT\n")
        codes = self.run_check(self.entry())
        self.assertEqual([c for c in codes if c.startswith("K00")], ["K002"])

    def test_both_new_codes_are_errors_and_drive_the_exit_code(self):
        self.assertEqual(cf.SEV["K005"], "ERROR")
        self.assertEqual(cf.SEV["K006"], "ERROR")

    # ---- the pricing instrument -----------------------------------------

    def test_quote_audit_reports_length_occurrences_and_foreign_scopes(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"),
              "## generic\n\n## generic\n")
        write(os.path.join(self.tmp, "knowledge/round-333-y.md"), "## generic\n")
        rows = cf.quote_audit(self.tmp, cf.Corpus(self.tmp),
                              self.entry(quote="## generic"))
        self.assertEqual(len(rows), 1)
        n, length, occ, foreign = rows[0]
        self.assertEqual((n, length, occ), (500, len("## generic"), 2))
        self.assertEqual(len(foreign), 1)

    def test_quote_audit_skips_unscored_entries(self):
        rows = cf.quote_audit(self.tmp, cf.Corpus(self.tmp),
                              {"500": {"bank": "state/round-500-predictions.md",
                                       "status": "unscored", "owner": "skills",
                                       "why": "x"}})
        self.assertEqual(rows, [])

    # ---- the requote proposer -------------------------------------------

    def test_requote_proposes_only_unique_foreign_free_scoring_lines(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"),
              "\n".join([
                  "a line about predictions that is long enough to be an anchor",
                  "short HIT",
                  "a duplicated scored line that is long enough to be an anchor",
                  "a duplicated scored line that is long enough to be an anchor",
                  "a foreign scored line that is long enough to be an anchor",
                  "a long line with no scoring vocabulary in it whatsoever ok",
              ]) + "\n")
        write(os.path.join(self.tmp, "knowledge/round-333-y.md"),
              "a foreign scored line that is long enough to be an anchor\n")
        write(os.path.join(self.tmp, cf.LEDGER_FILE),
              json.dumps({"banks": self.entry()}))
        led, _ = cf.load_ledger(self.tmp)
        got = cf.requote(self.tmp, cf.Corpus(self.tmp), led, 500)
        self.assertEqual(
            got, ["a line about predictions that is long enough to be an anchor"])

    def test_requote_ranks_longest_first(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"),
              "P1 HIT and this line is just over the forty character bar\n"
              "P2 HIT and this line is considerably longer than the one above "
              "it, which is the point\n")
        write(os.path.join(self.tmp, cf.LEDGER_FILE),
              json.dumps({"banks": self.entry()}))
        led, _ = cf.load_ledger(self.tmp)
        got = cf.requote(self.tmp, cf.Corpus(self.tmp), led, 500)
        self.assertEqual(len(got), 2)
        self.assertGreater(len(got[0]), len(got[1]))

    def test_requote_has_nothing_to_say_about_an_unscored_entry(self):
        write(os.path.join(self.tmp, cf.LEDGER_FILE), json.dumps({"banks": {
            "500": {"bank": "state/round-500-predictions.md",
                    "status": "unscored", "owner": "skills", "why": "x"}}}))
        led, _ = cf.load_ledger(self.tmp)
        self.assertEqual(cf.requote(self.tmp, cf.Corpus(self.tmp), led, 500), [])

    def test_requote_never_writes_the_ledger(self):
        """It proposes. Which sentence IS the scoring line is a judgement,
        and a script that picked one would be the prose classifier round 369
        deleted."""
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"),
              "P1 HIT and this line is just over the forty character bar\n")
        write(os.path.join(self.tmp, cf.LEDGER_FILE),
              json.dumps({"banks": self.entry()}))
        before = cf.read(os.path.join(self.tmp, cf.LEDGER_FILE))
        cf.requote(self.tmp, cf.Corpus(self.tmp), cf.load_ledger(self.tmp)[0], 500)
        self.assertEqual(cf.read(os.path.join(self.tmp, cf.LEDGER_FILE)), before)


class TestAnchorsOnTheLiveLedger(unittest.TestCase):
    """The enforcement for K005/K006, plus the reason they are not a length
    rule."""

    def setUp(self):
        self.corpus = cf.Corpus(ROOT)
        self.led, err = cf.load_ledger(ROOT)
        self.assertIsNone(err)

    def test_every_live_anchor_occurs_exactly_once_in_the_file_it_cites(self):
        for n, e in sorted(self.led.items()):
            if e.get("status") != "scored":
                continue
            # Round 517: K005's own predicate, on collapsed whitespace.
            # Asking it on the RAW text made this node disagree with the
            # checker it enforces — round 516's anchor is wrapped across two
            # lines in the file it cites, so this said "occurs 0 times" about
            # a sentence that is there.
            body = cf.flat(cf.read(os.path.join(ROOT, e["where"])))
            occ = body.count(cf.flat(e["quote"]))
            self.assertEqual(occ, 1,
                             "round %s: anchor occurs %d times in %s"
                             % (n, occ, e["where"]))

    def test_no_live_anchor_is_satisfied_by_a_round_it_does_not_name(self):
        for n, e in sorted(self.led.items()):
            if e.get("status") != "scored":
                continue
            own = {int(n)}
            try:
                own.add(int(e["scored_by"]))
            except (TypeError, ValueError):
                pass
            foreign = self.corpus.foreign_scopes(e["quote"], own)
            self.assertEqual(foreign, [],
                             "round %s: anchor also satisfies %s" % (n, foreign[:2]))

    def test_a_minimum_length_rule_would_be_red_on_this_same_ledger(self):
        """Why the shipped rule is not the one round 464 proposed.

        A 40-character floor reports dozens of entries that locate their
        scoring perfectly well, and it is not what the two tests above
        enforce. If this ever reaches zero the floor has become harmless --
        and it is still not the check, because length was never the defect.
        """
        short = [n for n, e in self.led.items()
                 if e.get("status") == "scored" and len(e["quote"]) < 40]
        self.assertGreater(len(short), 20)

    def test_round_465s_repairs_replaced_anchors_that_would_still_be_red(self):
        """Re-derived, not trusted: every entry round 465 says it repaired
        carries the anchor it replaced, and that old anchor must STILL be
        reported by K005 or K006 today. A repair that swapped one weak anchor
        for another would pass every other test in this file."""
        checked = 0
        for n, e in sorted(self.led.items()):
            if not e.get("quote_was"):
                continue
            own = {int(n)}
            try:
                own.add(int(e["scored_by"]))
            except (TypeError, ValueError):
                pass
            body = cf.read(os.path.join(ROOT, e["where"]))
            weak = (body.count(e["quote_was"]) != 1
                    or bool(self.corpus.foreign_scopes(e["quote_was"], own)))
            self.assertTrue(weak, "round %s: `quote_was` is not weak, so the "
                                  "repair claim does not re-derive" % n)
            checked += 1
        self.assertGreaterEqual(checked, 6)

    def test_the_scope_set_covers_both_kinds_of_coordinate(self):
        """Non-vacuity: if `round_scopes` ever returned only knowledge files,
        both live tests above would pass for the wrong reason."""
        scopes = self.corpus.round_scopes()
        kinds = {"knowledge" if lbl.startswith("knowledge/") else "prose"
                 for _, lbl, _ in scopes}
        self.assertEqual(kinds, {"knowledge", "prose"})
        self.assertGreater(len(scopes), 400)

    def test_foreign_scopes_finds_something_when_something_is_there(self):
        """The other half of non-vacuity: a string this corpus really does
        repeat must come back non-empty, or the two live tests are green
        because the scan is broken."""
        self.assertGreater(
            len(self.corpus.foreign_scopes("predictions", {465})), 20)


class TestSectionBoundary(unittest.TestCase):
    """Round 449 (SWE-loop D) — what a round's OWN section actually contains.

    `own_scope(n)` is the evidence `scan()` reads to decide whether round n
    scored its own predictions, so every character in it that round n did
    not write is a chance to credit n with somebody else's verdict.

    Until round 449 the section ran from one ROUND heading to the next, and
    `## Next steps (as of round N)` is not a round heading. Measured on the
    live record at that round's HEAD: **67 of 260** sections carried a
    foreign level-<=3 heading, **135** next-steps blocks were attributed to
    a round that did not write them, round 388's section swallowed 22
    headings, and **26.7%** of all attributed text belonged to another
    round. Correcting it moved 488 KB of prose and changed zero published
    findings — extent is not impact, and the tests below are what keep the
    boundary right now that nothing downstream would notice if it slipped.
    """

    DOC = ("### Round 400 — NUC-integration(E) — 2026-08-31\n"
           "- four hundred's own line\n\n"
           "#### a sub-heading inside round 400\n"
           "- still four hundred\n\n"
           "## Next steps (as of round 400)\n"
           "1. not round 400's entry\n\n"
           "### Round 401 — SWE-loop(D) — 2026-09-01\n"
           "- four oh one's own line\n")

    def test_a_next_steps_block_is_not_part_of_the_preceding_entry(self):
        secs = cf.round_sections(self.DOC)
        self.assertIn("four hundred's own line", secs[400])
        self.assertNotIn("not round 400's entry", secs[400])
        self.assertNotIn("Next steps", secs[400])

    def test_a_deeper_sub_heading_stays_inside_the_entry_that_owns_it(self):
        """The boundary is level-<=, not any-heading: a round entry may have
        sub-headings of its own and must keep them."""
        secs = cf.round_sections(self.DOC)
        self.assertIn("a sub-heading inside round 400", secs[400])
        self.assertIn("still four hundred", secs[400])

    def test_a_drifted_heading_opens_its_own_section_and_leaves_its_neighbour(self):
        """Round 448's live shape. Before round 449 the `##` heading matched
        nothing, so 448's entry was served as part of 447's section."""
        doc = ("### Round 447 — skills(B) — 2026-09-02\n- 447 body\n\n"
               "## Round 448 (NUC-integration E) — box DOWN\n- 448 body\n")
        secs = cf.round_sections(doc)
        self.assertIn(448, secs)
        self.assertIn("448 body", secs[448])
        self.assertNotIn("448 body", secs[447])

    def test_a_span_heading_is_a_boundary_but_never_a_key(self):
        """Handing one block to thirteen rounds would give each of them an
        entry it does not have."""
        doc = ("### Round 113 — harness(A) — 2026-08-25\n- 113 body\n\n"
               "### Rounds 114-126 — driver-level, mostly did not run\n"
               "- the span's body\n")
        secs = cf.round_sections(doc)
        self.assertEqual(sorted(secs), [113])
        self.assertNotIn("the span's body", secs[113])

    def test_no_live_section_swallows_another_round_or_a_next_steps_block(self):
        """The enforcement. Vacuous only if the record is already clean —
        which it was not when this test was written."""
        import re as _re
        for rel in ("state/research-state.md", "state/research-state-archive.md"):
            secs = cf.round_sections(cf.read(os.path.join(ROOT, rel)))
            for n, sec in secs.items():
                body = sec.split("\n", 1)[1] if "\n" in sec else ""
                foreign = [l for l in body.splitlines()
                           if _re.match(r"^#{1,3}\s", l)]
                self.assertEqual(foreign, [], "%s round %d swallows %r"
                                 % (rel, n, foreign[:3]))


# --------------------------------------------------------------------------
# ROUND 489 (skills B): the verdict was right and the evidence was wrong.
#
# K003 reported round 479 for four rounds. Its VERDICT was correct — round
# 479's bank had been scored, by round 485, in round 485's own file — and the
# EVIDENCE it published was a sentence about ROUND 473's bank, accepted
# because `FOREIGN_ATTRIB_RE` demanded `P<n>` or `prediction` after the
# possessive and the corpus had written `bank`. Nothing compared the two,
# because a detector's verdict is what tests pin and its evidence is not.
# --------------------------------------------------------------------------

R479_LINE = ("author); round 473's 17-row bank, scored "
             "**10 HIT / 6 MISS / 1")


class TestEvidenceAttribution(unittest.TestCase):
    """Frozen regressions, live sentences, exactly like TestScannerRegressions."""

    def test_a_bank_possessive_credits_the_round_that_owns_the_bank(self):
        """THE round-479 sentence, verbatim out of its own scope."""
        self.assertEqual(cf.credited_rounds(R479_LINE), {473})
        self.assertFalse(cf._attributable(R479_LINE, 479))
        self.assertTrue(cf._attributable(R479_LINE, 473))

    def test_the_widening_still_reads_a_two_digit_prediction_id(self):
        r"""Round 489 broke this while fixing the line above: a `\b` after
        `P\d` makes `P14` fail, which silently re-accepts every foreign
        possessive with a two-digit id. Caught by the round-352 fixture that
        already existed; pinned here so the next widening cannot repeat it."""
        line = "Round 352's P14 is heading for a MISS"
        self.assertEqual(cf.credited_rounds(line), {352})
        self.assertFalse(cf._attributable(line, 349))
        self.assertTrue(cf._attributable(line, 352))

    def test_mentioned_is_wider_than_credited_on_purpose(self):
        """The auditor must not share the detector's predicate — otherwise
        it can only ever agree with it (`suppressor-shares-the-detector-shape`)."""
        line = "| P1 | 1 ambiguous anchor, band 1-3 | **HIT** — exactly 1, round 421 |"
        self.assertEqual(cf.credited_rounds(line), set())
        self.assertEqual(cf.mentioned_rounds(line), {421})
        self.assertTrue(cf._attributable(line, 465))

    def test_raw_candidates_yields_what_score_evidence_discards(self):
        text = ("nothing\n" + R479_LINE + "\n"
                "| P1 | a real row | **HIT** |\n")
        allc = list(cf.raw_candidates(text))
        self.assertGreater(len(allc), 1)
        kept = cf.score_evidence(text, 479)
        self.assertIsNotNone(kept)
        self.assertNotIn("473", kept[1])


class TestK003PublishesItsEvidenceAttribution(TestFindings):
    """K003 must say when its own evidence names somebody else."""

    def _unscored(self):
        return {"500": {"bank": "state/round-500-predictions.md",
                        "status": "unscored", "owner": "t", "why": "w"}}

    def _msg(self, body):
        write(os.path.join(self.tmp, "knowledge/round-500-x.md"), body)
        corpus = cf.Corpus(self.tmp)
        banks, _ = cf.find_banks(self.tmp)
        write(os.path.join(self.tmp, cf.LEDGER_FILE),
              json.dumps({"banks": self._unscored()}))
        led, err = cf.load_ledger(self.tmp)
        found = cf.findings(self.tmp, corpus, banks, led, err, 500)
        hits = [f[2] for f in found if f[0] == "K003"]
        self.assertEqual(len(hits), 1, found)
        return hits[0]

    def test_evidence_about_another_round_carries_a_caveat(self):
        """A line with no POSSESSIVE credits nobody, so `_attributable`
        passes it — and it can still be entirely about another round. That
        residual is why the caveat exists and why widening the attribution
        regex was not on its own a fix."""
        msg = self._msg("scoring: the round 473 bank came out 10 HIT / 6 MISS\n")
        self.assertIn("CAVEAT", msg)
        self.assertIn("473", msg)

    def test_a_possessive_about_another_round_is_rejected_outright(self):
        """The widened filter: this line never reaches the caveat because it
        never becomes evidence. THE round-479 sentence."""
        write(os.path.join(self.tmp, "knowledge/round-500-x.md"),
              R479_LINE + "\n")
        corpus = cf.Corpus(self.tmp)
        banks, _ = cf.find_banks(self.tmp)
        write(os.path.join(self.tmp, cf.LEDGER_FILE),
              json.dumps({"banks": self._unscored()}))
        led, err = cf.load_ledger(self.tmp)
        found = cf.findings(self.tmp, corpus, banks, led, err, 500)
        self.assertEqual([f[0] for f in found if f[0] == "K003"], [])

    def test_evidence_that_names_no_round_carries_no_caveat(self):
        self.assertNotIn("CAVEAT",
                         self._msg("| P1 | a real row | **HIT** |\n"))

    def test_evidence_that_names_its_own_round_carries_no_caveat(self):
        msg = self._msg("round 500's own P1 is a **HIT**, and round 473 agrees\n")
        self.assertNotIn("CAVEAT", msg)


class TestK002DoesNotAssertHistory(TestFindings):
    def test_the_message_does_not_claim_the_anchor_was_ever_there(self):
        """Round 484's anchor was never in the file it cited (0 occurrences
        in both commits that ever touched it), so 'no longer in' named the
        wrong repair."""
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "nothing")
        corpus = cf.Corpus(self.tmp)
        banks, _ = cf.find_banks(self.tmp)
        write(os.path.join(self.tmp, cf.LEDGER_FILE), json.dumps({"banks": {
            "500": {"bank": "state/round-500-predictions.md",
                    "status": "scored", "scored_by": 501,
                    "where": "knowledge/round-501-x.md", "quote": "P1 HIT"}}}))
        led, err = cf.load_ledger(self.tmp)
        msg = [f[2] for f in cf.findings(self.tmp, corpus, banks, led, err, 501)
               if f[0] == "K002"][0]
        self.assertNotIn("no longer", msg)
        self.assertIn("git log -S", msg)


class TestEvidenceAuditOnTheLiveLedger(unittest.TestCase):
    """The audit is a REVIEW QUEUE, not a verdict — priced before shipping,
    the way round 465 priced K005/K006. Over the live corpus at round 489 it
    surfaced 9 of 143 banks-with-evidence and 3 of the 9 were genuinely wrong
    evidence (105, 369, 371); the other 6 are the round's own scoring line
    legitimately mentioning another round. 33 % precision is why it ships
    with no severity code."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = cf.Corpus(ROOT)
        cls.banks, _ = cf.find_banks(ROOT)
        cls.rows = cf.evidence_audit(cls.corpus, cls.banks)
        cls.led, _ = cf.load_ledger(ROOT)

    def test_the_audit_covers_every_bank_on_disk(self):
        self.assertEqual(sorted(r["round"] for r in self.rows),
                         sorted(self.banks))

    def test_a_row_with_no_evidence_is_never_suspect(self):
        for r in self.rows:
            if not r["verdict_line"]:
                self.assertFalse(r["suspect"], r["round"])

    def test_no_unscored_entry_publishes_evidence_about_another_round(self):
        """THE live invariant, and the one with a consequence. A `suspect`
        row on a `scored` entry costs nothing — K003 never runs on it. A
        `suspect` row on an `unscored` entry is a K003 finding whose evidence
        is about somebody else, which is exactly what round 479 was."""
        bad = [r["round"] for r in self.rows
               if r["suspect"]
               and self.led.get(str(r["round"]), {}).get("status") == "unscored"]
        self.assertEqual(bad, [], "unscored entr(ies) %s would publish K003 "
                                  "evidence naming a different round" % bad)

    def test_the_summary_adds_up(self):
        summ = cf.evidence_summary(self.rows)
        self.assertEqual(summ["banks"], len(self.rows))
        self.assertEqual(summ["suspect"], len(summ["suspect_rounds"]))
        self.assertLessEqual(summ["with_evidence"], summ["banks"])

    def test_round_479_no_longer_publishes_round_473s_sentence(self):
        """The fix, checked where it happened rather than in a fixture. The
        replacement line is NOT a scoring either — it is round 479's
        `| debt | outcome |` table — which is the round's second finding:
        repairing the attribution filter MOVED the wrong evidence, it did
        not make the evidence right."""
        row = [r for r in self.rows if r["round"] == 479][0]
        self.assertNotIn("473's 17-row bank", row["verdict_line"] or "")
        self.assertGreaterEqual(row["rejected_foreign"], 2)


class TestAPointerToAScoringIsNotAScoring(unittest.TestCase):
    """Round 495. `NEGATION_RE` gave the scanner a vocabulary for "was NOT
    scored" and none for "is scored OVER THERE", so a forward reference to a
    section that was never written read as a completed scoring."""

    # Verbatim from knowledge/round-492-the-axis-that-was-not-in-the-program.md
    # line 11. That file ends at `## 9. Tests and gates` and contains no HIT
    # and no MISS anywhere.
    R492 = ("**Predictions banked at `154d1ef` BEFORE any measurement**\n"
            "(`state/whence/round-492/predictions.md`). Scored in \u00a710.\n"
            "\n## 9. Tests and gates\n\nsome prose\n")

    def test_the_promise_alone_is_not_evidence(self):
        self.assertIsNone(cf.score_evidence(self.R492, 492))

    def test_the_same_promise_counts_once_the_section_exists(self):
        # The rule is about RESOLUTION, not about the word "Scored". Give the
        # document the section it promised and the pointer becomes usable.
        self.assertIsNotNone(
            cf.score_evidence(self.R492 + "\n## 10. Predictions scored\n",
                              492))

    def test_a_line_carrying_its_own_verdict_is_never_a_pointer(self):
        # Round 490's real tally line points at a section AND scores 15
        # predictions. Vetoing it would throw away a scoring for saying
        # where the rest of it lives.
        line = "**13 HIT / 1 MISS / 2 OPEN-KEPT of 15** (P14 in \u00a710)."
        self.assertIsNone(cf.unkept_pointer(line, "no headings here"))

    def test_the_veto_names_the_section_it_could_not_find(self):
        self.assertEqual(
            cf.unkept_pointer("Scored in \u00a710.", "## 9. Tests and gates"),
            "10")

    def test_a_resolving_pointer_returns_none(self):
        self.assertIsNone(
            cf.unkept_pointer("Scored in \u00a710.", "## 10. Suite"))


class TestATableRowScoresItsOwnTablesRound(unittest.TestCase):
    """Round 495's second finding: repairing the pointer rule UNCOVERED a
    second false positive underneath it, exactly as round 489's repair had
    moved rather than fixed round 479's evidence."""

    # knowledge/round-493-the-diagnosis-nobody-built-an-instrument-from.md:230
    ROW = ("| P7 | the five census reds are round 492's own artefacts in the "
           "corpus | **HIT** \u2014 every assertion is a count off by one |")

    def test_the_row_is_recognised_as_having_a_pid_subject(self):
        self.assertTrue(cf.row_subject_is_a_pid(self.ROW))

    def test_credited_rounds_does_not_catch_it(self):
        # Why the existing filter was not enough: round 489 widened
        # FOREIGN_ATTRIB_RE to `round N's <qualifiers> P<n>/predictions/bank`
        # and the noun in this row is `artefacts`.
        self.assertEqual(cf.credited_rounds(self.ROW), set())
        self.assertTrue(cf._attributable(self.ROW, 492))

    def test_it_is_not_cross_round_evidence_for_the_round_it_mentions(self):
        self.assertIsNone(
            cf.score_evidence(self.ROW, 492,
                              require_named=["state/whence/round-492/"
                                             "predictions.md"]))

    def test_but_it_is_still_evidence_in_its_own_scope(self):
        # The veto must never reach `own_scope`: a round's own table row IS
        # its own scoring.
        self.assertIsNotNone(cf.score_evidence(self.ROW, 493))

    def test_a_prose_cross_round_scoring_still_counts(self):
        line = ("- **Round 422's prediction bank is SCORED** \u2014 P1 HIT, "
                "P2 MISS, in `state/whence/round-422/PREDICTIONS.md`.")
        self.assertIsNotNone(
            cf.score_evidence(line, 422,
                              require_named=["state/whence/round-422/"
                                             "PREDICTIONS.md"]))


class TestSuggestIsHonestAboutAnUnkeptPromise(unittest.TestCase):
    """`--suggest` had NO test at all before round 495 (checked by grep over
    this file). It is the mode a round runs to discharge D-013's second half,
    and on round 492 it proposed `"status": "scored"` quoting the sentence
    that promises the section that was never written. Accepting that would
    have closed K001 while the bank stayed unscored."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def _corpus(self, knowledge_body):
        write(os.path.join(self.tmp, "state/whence/round-492/predictions.md"),
              "# bank\nP1. something\n")
        write(os.path.join(self.tmp, "knowledge/round-492-x.md"),
              knowledge_body)
        write(os.path.join(self.tmp, "state/research-state.md"), "# state\n")
        write(os.path.join(self.tmp, "state/prediction-bank-ledger.json"),
              json.dumps({"banks": {}}))
        banks, _ = cf.find_banks(self.tmp)
        return cf.Corpus(self.tmp), banks

    def test_an_unkept_promise_is_proposed_unscored(self):
        corpus, banks = self._corpus(
            "# Round 492\n\n(`state/whence/round-492/predictions.md`). "
            "Scored in \u00a710.\n\n## 9. Tests and gates\n")
        self.assertIsNone(cf.scan(corpus, 492, banks[492]))

    def test_a_kept_promise_is_proposed_scored(self):
        corpus, banks = self._corpus(
            "# Round 492\n\n(`state/whence/round-492/predictions.md`). "
            "Scored in \u00a710.\n\n## 10. Predictions scored\n\n"
            "P1 HIT.\n")
        self.assertIsNotNone(cf.scan(corpus, 492, banks[492]))


class TestTheSweepEnumeratedSuffixesToo(unittest.TestCase):
    """Round 513. `find_banks` was made repo-wide because enumerating the
    DIRECTORIES you know about cannot find an obligation nobody registered.
    It went on enumerating the EXTENSIONS -- all six documented conventions
    are `.md` -- so round 512's `state/whence/round-512/predictions.json` was
    invisible and K003 said the entry "names nothing" about a file that was
    on disk."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "state"))
        os.makedirs(os.path.join(self.tmp, "knowledge"))
        write(os.path.join(self.tmp, "state/research-state.md"), "# s\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def messages(self, ledger, latest_round=512):
        write(os.path.join(self.tmp, cf.LEDGER_FILE),
              json.dumps({"banks": ledger}))
        banks, _ = cf.find_banks(self.tmp)
        led, err = cf.load_ledger(self.tmp)
        return cf.findings(self.tmp, cf.Corpus(self.tmp), banks, led, err,
                           latest_round)

    def test_a_json_bank_in_a_round_directory_is_found(self):
        write(os.path.join(self.tmp,
                           "state/whence/round-512/predictions.json"), "{}")
        banks, _ = cf.find_banks(self.tmp)
        self.assertEqual(banks.get(512),
                         ["state/whence/round-512/predictions.json"])

    def test_a_second_numbered_json_bank_lands_under_the_same_round(self):
        for n in ("predictions.json", "predictions-2.json"):
            write(os.path.join(self.tmp, "state/whence/round-512", n), "{}")
        banks, _ = cf.find_banks(self.tmp)
        self.assertEqual(sorted(banks[512]),
                         ["state/whence/round-512/predictions-2.json",
                          "state/whence/round-512/predictions.json"])

    def test_the_ledger_itself_is_not_swept_up_as_a_bank(self):
        """The register is not a member of the set it registers. Its name
        matches `prediction` and `.json` is now an admitted suffix, so the
        widening invents one unnumbered obligation unless it is named out."""
        write(os.path.join(self.tmp, cf.LEDGER_FILE),
              json.dumps({"banks": {}}))
        banks, unnumbered = cf.find_banks(self.tmp)
        self.assertEqual((banks, unnumbered), ({}, []))

    def test_the_six_md_conventions_still_work_after_the_widening(self):
        for rel in ("state/round-017-predictions.md",
                    "state/whence/round-368/PREDICTIONS.md",
                    "nuc/predictions-e-round358.md",
                    "state/swe/round-359/PREDICTIONS.md"):
            write(os.path.join(self.tmp, rel), "x")
        banks, _ = cf.find_banks(self.tmp)
        self.assertEqual(sorted(banks), [17, 358, 359, 368])

    def test_k003_blames_the_sweep_when_the_named_bank_exists(self):
        """The round-512 case. `bank` names a file that IS there and the
        sweep cannot see it: the repair is in `find_banks`, not the ledger,
        and the message has to say which."""
        write(os.path.join(self.tmp, "state/round-512/predictions.rst"), "x")
        msgs = [m for c, _, m in self.messages(
            {"512": {"bank": "state/round-512/predictions.rst",
                     "status": "unscored", "owner": "skills(B)",
                     "why": "x"}}) if c == "K003"]
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("EXISTS on disk", msgs[0])
        self.assertIn("find_banks", msgs[0])
        self.assertNotIn("no bank on disk at all", msgs[0])

    def test_k003_still_says_nothing_is_there_when_nothing_is(self):
        msgs = [m for c, _, m in self.messages(
            {"512": {"bank": "state/round-512/predictions.md",
                     "status": "unscored", "owner": "skills(B)",
                     "why": "x"}}) if c == "K003"]
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("no bank on disk at all", msgs[0])
        self.assertIn("state/round-512/predictions.md", msgs[0])

    def test_the_json_bank_that_the_ledger_names_raises_nothing(self):
        write(os.path.join(self.tmp,
                           "state/whence/round-512/predictions.json"), "{}")
        codes = [c for c, _, _ in self.messages(
            {"512": {"bank": "state/whence/round-512/predictions.json",
                     "status": "unscored", "owner": "language(C)",
                     "why": "x"}})]
        self.assertNotIn("K003", codes)
        self.assertNotIn("K001", codes)


class TestAWrappedAnchorIsNotADriftedOne(TestFindings):
    """Round 517 (harness A). K002's second-ever ERROR episode.

    This corpus's knowledge files are hard-wrapped at ~76 columns, so a
    quoted SENTENCE is usually not a LINE. K002/K005/K006 compared RAW text,
    so an anchor matched only if its whitespace matched too — and round 516's
    entry, copied out of its own file and flattened to one line, was reported
    as "not in" a file it is plainly in.
    """

    LEDGER = {"500": {"bank": "state/round-500-predictions.md",
                      "status": "scored", "scored_by": 501,
                      "where": "knowledge/round-501-x.md",
                      "quote": "**7 HIT, 2 MISS of 9.** Banked before "
                               "any measurement was taken."}}

    def test_an_anchor_the_cited_file_wraps_across_two_lines_is_clean(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"),
              "## 8. Predictions\n\n**7 HIT, 2 MISS of 9.** Banked before\n"
              "any measurement was taken.\n")
        self.assertEqual(self.run_check(self.LEDGER), [])

    def test_the_same_anchor_really_is_absent_when_it_is_absent(self):
        """The normalisation must not turn K002 into a check that passes on
        anything — the same ledger against a file missing the sentence."""
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"),
              "## 8. Predictions\n\nnothing was scored here\n")
        self.assertIn("K002", self.run_check(self.LEDGER))

    def test_collapsing_does_not_join_words_across_the_wrap(self):
        """`flat` collapses a newline to a SPACE, not to nothing. A file
        whose wrap fell mid-word would otherwise match an anchor that has no
        space there, which is a different sentence."""
        self.assertEqual(cf.flat("mea\nsurement"), "mea surement")
        self.assertEqual(cf.flat("a  b\n\n c "), "a b c")

    def test_k005_counts_on_the_collapsed_text_too(self):
        """Half-normalising would let an anchor pass K002 and then be
        reported as occurring 0 times."""
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"),
              "**7 HIT, 2 MISS of 9.** Banked before\nany measurement was "
              "taken.\n\nrestated: **7 HIT, 2 MISS of 9.** Banked before "
              "any measurement was taken.\n")
        self.assertIn("K005", self.run_check(self.LEDGER))

    def test_the_nine_live_entries_that_embed_a_newline_still_match(self):
        """The convention that grew up around the raw comparison. Nine of the
        live ledger's scored entries carry a literal newline inside `quote`;
        collapsing both sides must not cost any of them."""
        corpus = cf.Corpus(ROOT)
        led, err = cf.load_ledger(ROOT)
        self.assertIsNone(err)
        embedded = [n for n, e in led.items()
                    if e.get("status") == "scored"
                    and "\n" in (e.get("quote") or "")]
        self.assertGreaterEqual(len(embedded), 9, embedded)
        for n in embedded:
            e = led[n]
            body = cf.read(os.path.join(ROOT, e["where"]))
            self.assertIn(cf.flat(e["quote"]), cf.flat(body), n)
            self.assertEqual(cf.flat(body).count(cf.flat(e["quote"])), 1, n)


class TestK002ChoosesTheCauseInsteadOfNamingOne(TestFindings):
    """Round 517. K002 has gone ERROR-red twice in the whole retained
    health-log record — rounds 484-488 and round 516 — and the message named
    the WRONG REPAIR both times, for two different causes. Round 489's fix
    was to add a second named cause to a sentence; this is the general one.
    """

    def _msg(self, ledger, latest=501):
        write(os.path.join(self.tmp, cf.LEDGER_FILE),
              json.dumps({"banks": ledger}))
        corpus = cf.Corpus(self.tmp)
        banks, _ = cf.find_banks(self.tmp)
        led, err = cf.load_ledger(self.tmp)
        return [f[2] for f in cf.findings(self.tmp, corpus, banks, led, err,
                                          latest) if f[0] == "K002"]

    def test_an_anchor_that_lives_in_another_round_scope_says_so(self):
        """Round 464's real case: an entry quoting research-state's wording
        while naming the knowledge file. K006 asks this question when the
        anchor MATCHES; nothing asked it on the failing side, so the reader
        was sent to `git log -S` for a sentence sitting in the next file."""
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "nothing")
        write(os.path.join(self.tmp, "knowledge/round-499-y.md"),
              "P1 HIT and the whole of it\n")
        msgs = self._msg({"500": {"bank": "state/round-500-predictions.md",
                                  "status": "scored", "scored_by": 501,
                                  "where": "knowledge/round-501-x.md",
                                  "quote": "P1 HIT and the whole of it"}})
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("knowledge/round-499-y.md", msgs[0])
        self.assertIn("the likely repair is `where`", msgs[0])
        self.assertNotIn("git log -S", msgs[0])

    def test_an_anchor_nowhere_in_the_corpus_keeps_round_489s_message(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "nothing")
        msgs = self._msg({"500": {"bank": "state/round-500-predictions.md",
                                  "status": "scored", "scored_by": 501,
                                  "where": "knowledge/round-501-x.md",
                                  "quote": "P1 HIT and the whole of it"}})
        self.assertEqual(len(msgs), 1, msgs)
        self.assertIn("git log -S", msgs[0])
        self.assertNotIn("no longer", msgs[0])

    def test_the_absent_message_forecloses_the_wrap_diagnosis(self):
        """The cause that cost round 516 a red is now impossible, so the
        message says so rather than leaving a reader to rule it out."""
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "nothing")
        msgs = self._msg({"500": {"bank": "state/round-500-predictions.md",
                                  "status": "scored", "scored_by": 501,
                                  "where": "knowledge/round-501-x.md",
                                  "quote": "P1 HIT and the whole of it"}})
        self.assertIn("NOT a line wrap", msgs[0])

    def test_the_diagnosis_kinds_are_exactly_two_and_both_are_errors(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"), "nothing")
        corpus = cf.Corpus(self.tmp)
        e = {"bank": "state/round-500-predictions.md", "status": "scored",
             "scored_by": 501, "where": "knowledge/round-501-x.md",
             "quote": "P1 HIT and the whole of it"}
        self.assertEqual(cf.k002_diagnosis(500, e, corpus)[0], "absent")
        write(os.path.join(self.tmp, "knowledge/round-499-y.md"),
              "P1 HIT and the whole of it\n")
        self.assertEqual(cf.k002_diagnosis(500, e, cf.Corpus(self.tmp))[0],
                         "elsewhere")
        self.assertEqual(cf.SEV["K002"], "ERROR")


class TestK006SeesThroughAForeignWrap(TestFindings):
    """Round 517, and the finding this round did NOT predict. Collapsing
    whitespace was expected to move exactly one verdict (round 516's K002).
    It moved three: it also opened TWO K006 errors, rounds 455 and 462,
    whose anchors were pasted by a LATER round with a different line wrap.

    K006 asks "could `where` have been wrong and nothing would say so". A
    later round that quotes the anchor defeats it just as completely whether
    or not the paragraph happened to wrap in the same place, so the raw
    comparison had a wrap-shaped recall hole. Both entries were repaired in
    round 517 by re-quoting a longer contiguous slice of the SAME file —
    round 465's repair — and both carry `quote_was`/`quote_fixed_by`.
    """

    def test_a_foreign_scope_that_wraps_differently_is_still_foreign(self):
        write(os.path.join(self.tmp, "knowledge/round-501-x.md"),
              "**7 HIT, 2 MISS of 9.** Banked before any measurement.\n")
        write(os.path.join(self.tmp, "knowledge/round-499-y.md"),
              "as round 501 put it, **7 HIT, 2 MISS of 9.** Banked before\n"
              "any measurement.\n")
        codes = self.run_check({"500": {
            "bank": "state/round-500-predictions.md", "status": "scored",
            "scored_by": 501, "where": "knowledge/round-501-x.md",
            "quote": "**7 HIT, 2 MISS of 9.** Banked before any "
                     "measurement."}})
        self.assertIn("K006", codes)

    def test_the_two_repaired_entries_carry_their_provenance(self):
        led, err = cf.load_ledger(ROOT)
        self.assertIsNone(err)
        for n in ("455", "462"):
            self.assertIn("quote_was", led[n], n)
            self.assertIn("round 517", led[n]["quote_fixed_by"], n)

    def test_the_live_ledger_has_no_anchor_matching_a_foreign_scope(self):
        """The backlog K005/K006 ship against is zero, and this is what says
        so on the collapsed comparison rather than the raw one."""
        corpus = cf.Corpus(ROOT)
        led, err = cf.load_ledger(ROOT)
        self.assertIsNone(err)
        bad = []
        for n, e in led.items():
            if e.get("status") != "scored" or not e.get("quote"):
                continue
            own = {int(n)}
            try:
                own.add(int(e["scored_by"]))
            except (TypeError, ValueError):
                pass
            f = corpus.foreign_scopes(e["quote"], own)
            if f:
                bad.append((n, f))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()

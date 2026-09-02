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
            body = cf.read(os.path.join(ROOT, e["where"]))
            self.assertEqual(body.count(e["quote"]), 1,
                             "round %s: anchor occurs %d times in %s"
                             % (n, body.count(e["quote"]), e["where"]))

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


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

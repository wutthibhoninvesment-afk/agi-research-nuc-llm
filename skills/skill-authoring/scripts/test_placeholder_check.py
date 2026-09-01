#!/usr/bin/env python3
"""Tests for placeholder_check.py (round 429).

`test_the_live_corpus_has_no_unacknowledged_placeholder` is the enforcement;
everything else exists so that one cannot pass vacuously. The discriminator
tests matter most: the whole reason this is a script and not a `grep -rn` is
that the token appears in prose ABOUT the problem far more often than as a
real hole, and a check that cries wolf on those gets muted within a round.
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import placeholder_check as pc

ROOT = pc.DEFAULT_REPO_ROOT


class TestTheDiscriminator(unittest.TestCase):
    """Bare-on-its-line, under markdown decoration."""

    def test_the_four_bare_shapes_in_the_real_corpus(self):
        for line, token in (
                ("METRICS_PLACEHOLDER", "METRICS_PLACEHOLDER"),
                # round 205's, the one a naive `^TOKEN$` regex misses:
                # indented, bracketed AND full-stopped.
                ("  [TEST_RESULT_PLACEHOLDER].", "TEST_RESULT_PLACEHOLDER"),
                ("- `FULL_LIVE_PLACEHOLDER`", "FULL_LIVE_PLACEHOLDER"),
                ("**BASELINE_RESULT_PLACEHOLDER**", "BASELINE_RESULT_PLACEHOLDER"),
        ):
            self.assertEqual(pc.is_bare(line), token, line)

    def test_prose_mentions_are_not_holes(self):
        """Every one of these is a real line from this repo's own record.
        A fixed-token grep reports all of them."""
        for line in (
                "Round 427 filled `FULL_LIVE_PLACEHOLDER` in round 426's entry.",
                "Both tokens end in `_PLACEHOLDER`.",
                "  `[TEST_RESULT_PLACEHOLDER]` in its round-log entry above) was",
                "A grep for `_PLACEHOLDER|TODO|TBD|XXX|FIXME` over the record",
                "left THREE: `BASELINE_RESULT_PLACEHOLDER` and `LIVE_RESULT_PLACEHOLDER`",
        ):
            self.assertIsNone(pc.is_bare(line), line)

    def test_a_bare_lowercase_or_unsuffixed_word_is_not_a_token(self):
        for line in ("placeholder", "PLACEHOLDER_FOR_LATER", "TODO", "XXX"):
            self.assertIsNone(pc.is_bare(line), line)

    def test_the_suffix_is_required_not_merely_contained(self):
        self.assertIsNone(pc.is_bare("MY_PLACEHOLDERS"))
        self.assertEqual(pc.is_bare("MY_PLACEHOLDER"), "MY_PLACEHOLDER")

    def test_mentions_counts_occurrences_and_excludes_holes(self):
        text = ("A_PLACEHOLDER\n"
                "prose about A_PLACEHOLDER and B_PLACEHOLDER on one line\n")
        self.assertEqual(len(pc.scan_text(text, "f.md")), 1)
        self.assertEqual(pc.mentions(text), 2)


class TestContextPinning(unittest.TestCase):
    def hash_of(self, lines, i):
        return pc.context_hash(lines, i)

    def test_a_neighbour_edit_expires_the_pin(self):
        a = ["x", "y", "z", "P_PLACEHOLDER", "q", "r", "s"]
        b = list(a)
        b[2] = "z CHANGED"
        self.assertNotEqual(self.hash_of(a, 3), self.hash_of(b, 3))

    def test_a_distant_edit_does_not(self):
        a = ["x", "y", "z", "P_PLACEHOLDER", "q", "r", "s", "far"]
        b = list(a)
        b[7] = "far CHANGED"
        self.assertEqual(self.hash_of(a, 3), self.hash_of(b, 3))

    def test_trailing_whitespace_does_not_move_the_hash(self):
        a = ["x", "P_PLACEHOLDER", "y"]
        b = ["x   ", "P_PLACEHOLDER", "y\t"]
        self.assertEqual(self.hash_of(a, 1), self.hash_of(b, 1))

    def test_the_hash_survives_the_file_moving_within_the_repo(self):
        """The pin is on CONTENT, so the same passage in a renamed file has
        the same hash — but the entry also stores `path`, so a move still
        expires it. That is deliberate: a moved file deserves re-reading."""
        lines = ["x", "P_PLACEHOLDER", "y"]
        self.assertEqual(pc.scan_text("\n".join(lines), "a.md")[0].digest,
                         pc.scan_text("\n".join(lines), "b.md")[0].digest)
        self.assertNotEqual(pc.scan_text("\n".join(lines), "a.md")[0].key(),
                            pc.scan_text("\n".join(lines), "b.md")[0].key())


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "knowledge"))
        os.makedirs(os.path.join(self.tmp, "state"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, text):
        with open(os.path.join(self.tmp, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def registry(self, entries):
        self.write(os.path.join("state", "known-unfilled-placeholders.json"),
                   json.dumps({"acknowledged": entries}))

    def run_main(self, *extra):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = pc.main(["--repo-root", self.tmp] + list(extra))
        return rc, buf.getvalue()

    def test_an_unacknowledged_hole_is_an_error_and_exit_1(self):
        self.write("knowledge/round-001-x.md", "text\nR_PLACEHOLDER\nmore\n")
        rc, out = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("ERROR U001", out)
        self.assertIn("knowledge/round-001-x.md:2", out)

    def test_an_acknowledged_hole_warns_and_exits_0(self):
        self.write("knowledge/round-001-x.md", "text\nR_PLACEHOLDER\nmore\n")
        digest = pc.scan_repo(self.tmp)[0][0].digest
        self.registry([{"path": "knowledge/round-001-x.md",
                        "token": "R_PLACEHOLDER", "hash": digest,
                        "reason": "the run died in 2019"}])
        rc, out = self.run_main()
        self.assertEqual(rc, 0)
        self.assertIn("WARN U002", out)
        self.assertIn("the run died in 2019", out)
        self.assertNotIn("U001", out)

    def test_editing_the_passage_expires_the_acknowledgement(self):
        """The property that makes this a pin and not an allowlist: the
        moment the surrounding text changes, the entry stops suppressing
        (U001 comes back) AND says so (U003)."""
        self.write("knowledge/round-001-x.md", "text\nR_PLACEHOLDER\nmore\n")
        digest = pc.scan_repo(self.tmp)[0][0].digest
        self.registry([{"path": "knowledge/round-001-x.md",
                        "token": "R_PLACEHOLDER", "hash": digest,
                        "reason": "acknowledged"}])
        self.assertEqual(self.run_main()[0], 0)
        self.write("knowledge/round-001-x.md",
                   "text REWRITTEN\nR_PLACEHOLDER\nmore\n")
        rc, out = self.run_main()
        self.assertEqual(rc, 1)
        self.assertIn("U001", out)
        self.assertIn("U003", out)

    def test_filling_the_hole_leaves_a_stale_entry_visible(self):
        self.write("knowledge/round-001-x.md", "text\nR_PLACEHOLDER\nmore\n")
        digest = pc.scan_repo(self.tmp)[0][0].digest
        self.registry([{"path": "knowledge/round-001-x.md",
                        "token": "R_PLACEHOLDER", "hash": digest,
                        "reason": "acknowledged"}])
        self.write("knowledge/round-001-x.md", "text\n42 passed\nmore\n")
        rc, out = self.run_main()
        self.assertEqual(rc, 0)          # nothing is broken...
        self.assertIn("U003", out)       # ...but the dead entry is visible

    def test_knowledge_is_scanned_not_only_state(self):
        """Round 427's proposal scanned `state/` only and five of the six
        real instances are in `knowledge/`. Pinned so nobody re-narrows it."""
        self.assertEqual(pc.SCAN_GLOBS[0], "knowledge/*.md")
        self.write("knowledge/k.md", "K_PLACEHOLDER\n")
        self.write("state/s.md", "S_PLACEHOLDER\n")
        _, out = self.run_main()
        self.assertIn("knowledge/k.md", out)
        self.assertIn("state/s.md", out)

    def test_the_summary_line_carries_its_denominators(self):
        """Round 417's rule: `corpus_check` quotes the LAST line, so it has
        to say what was scanned, not just how many findings there were."""
        self.write("knowledge/round-001-x.md",
                   "R_PLACEHOLDER\nprose naming R_PLACEHOLDER inline\n")
        last = [l for l in self.run_main()[1].splitlines() if l.strip()][-1]
        self.assertRegex(
            last,
            r"placeholder-check: \d+ file\(s\), \d+ unfilled \(\d+ acknowledged\), "
            r"\d+ non-bare mention\(s\).*, \d+ error\(s\), \d+ warning\(s\)")
        self.assertIn("1 unfilled", last)
        self.assertIn("1 non-bare mention", last)

    def test_an_empty_repo_is_clean(self):
        rc, out = self.run_main()
        self.assertEqual(rc, 0)
        self.assertIn("0 unfilled", out)


class TestLiveCorpus(unittest.TestCase):
    def test_the_live_corpus_has_no_unacknowledged_placeholder(self):
        """The enforcement. Six holes are acknowledged with reasons in
        state/known-unfilled-placeholders.json; a SEVENTH lands here."""
        if not os.path.isdir(os.path.join(ROOT, "knowledge")):
            self.skipTest("live corpus not present")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = pc.main(["--repo-root", ROOT])
        self.assertEqual(rc, 0, buf.getvalue())

    def test_the_live_registry_is_not_vacuous(self):
        """A registry of zero entries would make the pin above pass for the
        wrong reason, and an entry without a reason is an allowlist."""
        if not os.path.isdir(os.path.join(ROOT, "knowledge")):
            self.skipTest("live corpus not present")
        acked = pc.load_registry(ROOT)
        self.assertGreaterEqual(len(acked), 6)
        for a in acked:
            self.assertTrue(a.get("reason", "").strip(), a)
            self.assertGreater(len(a["reason"]), 60, a["path"])

    def test_every_live_acknowledgement_still_pins_something(self):
        """U003 in the live corpus means an entry outlived its passage."""
        if not os.path.isdir(os.path.join(ROOT, "knowledge")):
            self.skipTest("live corpus not present")
        holes = {(h.path, h.digest) for h in pc.scan_repo(ROOT)[0]}
        dead = [a["path"] for a in pc.load_registry(ROOT)
                if (a["path"], a["hash"]) not in holes]
        self.assertEqual(dead, [])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for pattern_vs_enum.py (round 477, skills B).

`test_the_live_tree_has_no_pattern_enumeration_disagreement` is the
enforcement. Everything else exists so that one cannot pass vacuously —
its live population is ZERO, which is the most dangerous state a check can
be in, because a detector that has stopped detecting and a tree that is
clean produce the same output.

The load-bearing test is `test_the_round_475_defect_is_still_detected`: it
feeds the detector the REAL pre-fix `corpus_check.py`, out of git, and
requires it to name `skills/prediction-banking/scripts`. That is the only
test here whose subject is a defect that actually happened.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pattern_vs_enum as pve  # noqa: E402

ROOT = pve.DEFAULT_REPO_ROOT

#: The commit at which round 477 began — the last one carrying the defect.
#: Named as a constant because a test that pins a SHA owes the reader the
#: window it is valid in: `git show` on a missing object skips this test
#: rather than failing it, so a future shallow clone degrades to "unproven"
#: instead of "broken". `expiring-fixture-window`.
PRE_FIX_COMMIT = "7f4fd07"
PRE_FIX_PATH = "skills/skill-authoring/scripts/corpus_check.py"


def synth(prose_glob, joins):
    """A minimal Python source with a prose glob and constructed paths."""
    body = ",\n        ".join(
        'os.path.join(root, %s)' % ", ".join('"%s"' % c for c in j.split("/"))
        for j in joins)
    return ('"""A docstring naming `%s` as the family.\n\nMore prose.\n"""\n'
            'import os\n\n\n'
            'def checks(root):\n'
            '    return ["-m", "pytest", "-q",\n        %s]\n'
            % (prose_glob, body))


class TestFindings(unittest.TestCase):
    """Hermetic: a synthetic root with a controlled `skills/` layout.

    The first draft of this class asserted against the LIVE tree's skill
    directories, and it broke within the hour — round 477 added
    `skills/derived-subject-set/scripts/test_pattern_vs_enum.py`, the family
    grew from three members to four, and four tests that had nothing to do
    with the change went red naming a directory they had never heard of.

    That is `derived-subject-set` step 1 in the mirror: the tests were
    themselves a hand-written subject set mirroring an artefact that grows.
    Recorded here rather than quietly fixed, because the fix is the skill's
    own advice and the defect was in the skill's own test file.
    """

    FAMILY = ("alpha", "beta", "gamma")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for skill in self.FAMILY:
            d = os.path.join(self.root, "skills", skill, "scripts")
            os.makedirs(d)
            with open(os.path.join(d, "test_x.py"), "w") as f:
                f.write("def test_x(): pass\n")
        # A skill with `scripts/` and no test file: in neither side of the
        # comparison, and the reason the glob ends in `test_*.py`.
        os.makedirs(os.path.join(self.root, "skills", "toolless", "scripts"))
        self.tops = pve.top_level_dirs(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def find(self, source):
        return pve.findings_for(source, self.tops, self.root, "synth.py")

    def test_the_synthetic_family_is_the_one_the_tests_assume(self):
        """The guard on the guard. If `setUp` stops building three skills,
        every assertion below changes meaning, and this says so first."""
        self.assertEqual(self.tops, {"skills"})
        self.assertEqual(
            sorted(os.path.dirname(q).replace(self.root + os.sep, "")
                   for q in __import__("glob").glob(
                       os.path.join(self.root, "skills", "*", "scripts",
                                    "test_*.py"))),
            [os.path.join("skills", s, "scripts") for s in self.FAMILY])

    def test_a_strict_subset_is_an_error_naming_what_is_missing(self):
        """The positive control, in the exact shape round 475 found by hand."""
        got = self.find(synth("skills/*/scripts/test_*.py",
                              ["skills/alpha/scripts", "skills/beta/scripts"]))
        self.assertEqual(len(got), 1, got)
        self.assertEqual(got[0]["code"], "E001")
        self.assertEqual(got[0]["pattern"], "skills/*/scripts/test_*.py")
        self.assertEqual(got[0]["missing"], ["skills/gamma/scripts"])
        self.assertEqual(got[0]["named"],
                         ["skills/alpha/scripts", "skills/beta/scripts"])
        self.assertEqual(got[0]["family"],
                         ["skills/alpha/scripts", "skills/beta/scripts",
                          "skills/gamma/scripts"])

    def test_a_complete_enumeration_is_clean(self):
        """The negative control. This is the shape round 477 shipped."""
        self.assertEqual(self.find(synth(
            "skills/*/scripts/test_*.py",
            ["skills/alpha/scripts", "skills/beta/scripts",
             "skills/gamma/scripts"])), [])

    def test_a_directory_with_no_test_file_is_in_neither_side(self):
        """`skills/toolless/scripts` exists and holds no `test_*.py`.

        Pointing pytest at it is not harmless: pytest exits 4 on a directory
        it cannot collect from, and `corpus_check` reads 2-5 as
        COULD_NOT_RUN, so the health check would go dark rather than red.
        """
        got = self.find(synth("skills/*/scripts/test_*.py",
                              ["skills/alpha/scripts", "skills/beta/scripts",
                               "skills/gamma/scripts",
                               "skills/toolless/scripts"]))
        self.assertEqual(got, [], "a non-member of the family was counted")

    def test_code_that_names_nothing_in_the_family_is_not_a_finding(self):
        """`named` empty means the glob is about something else.

        A module can mention `skills/*/scripts/test_*.py` in prose and
        construct an unrelated path in code; that is two subjects, not a
        disagreement. Making this a finding is how a detector with a zero
        population starts firing on unrelated files and gets uninstalled.
        """
        self.assertEqual(self.find(synth("skills/*/scripts/test_*.py",
                                         ["skills/nowhere"])), [])

    def test_a_dead_pattern_is_not_a_finding(self):
        """The deliberate non-check, with its measurement in the docstring.

        Round 477's census: 61 distinct dead glob patterns in this tree, 12
        at a present-tense site, and TEN of those twelve sit in sentences
        asserting the file does not exist (`knowledge/round-281-*.md` — *"and
        there should not be one"*). A dead glob is ambiguous between a rotted
        reference and a correct absence claim, and here the absence claims
        win. `python3 pattern_vs_enum.py census` re-derives it.
        """
        self.assertEqual(self.find(synth("skills/zzz-no-such-skill/*/x.py",
                                         ["skills/alpha/scripts"])), [])


class TestTheDefectThatHappened(unittest.TestCase):
    """The real `corpus_check.py`, before and after, out of git and off disk.

    Every assertion in `TestFindings` is synthetic. These two are the
    differential on the artefact that produced this file, and they are what a
    future round refactoring `prose_globs` has to keep passing.
    """

    def setUp(self):
        self.tops = pve.top_level_dirs(ROOT)

    def test_the_round_475_defect_is_still_detected(self):
        try:
            src = subprocess.run(
                ["git", "-C", ROOT, "show",
                 "%s:%s" % (PRE_FIX_COMMIT, PRE_FIX_PATH)],
                capture_output=True, text=True, timeout=60, check=True).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                FileNotFoundError) as exc:
            self.skipTest("cannot read %s:%s (%s) — the fixture window has "
                          "closed, not a defect in the detector"
                          % (PRE_FIX_COMMIT, PRE_FIX_PATH, exc))
        self.assertIn("pytest over skills/*/scripts/test_*.py", src,
                      "the pinned commit does not carry the defect — the "
                      "SHA is wrong, so this test proves nothing")
        got = pve.findings_for(src, self.tops, ROOT, PRE_FIX_PATH)
        # TWO sites, and that is a finding of its own. Round 475's next-step
        # 2 cited the description "near line 175". The same false claim is
        # also at line 407, inside the docstring of `checks()` itself — the
        # very function whose argv contradicted it. A hand-diff finds the
        # instance; an instrument finds the population. The count is pinned
        # at 2 rather than `>= 1` so that a `prose_globs` change which
        # collapses the two sites has to say so.
        self.assertEqual(len(got), 2, got)
        self.assertEqual(sorted(f["line"] for f in got), [175, 407])
        for f in got:
            # `named` comes from the FIXTURE and is stable; `missing` is
            # measured against the LIVE family, which grows every time a
            # skill gains a test file, so it is asserted by membership. That
            # distinction is the whole lesson of `TestFindings`' docstring.
            self.assertEqual(f["named"],
                             ["skills/session-inheritance-audit/scripts",
                              "skills/skill-authoring/scripts"])
            self.assertIn("skills/prediction-banking/scripts", f["missing"])

    def test_the_fixed_source_at_head_is_clean(self):
        """The other half of the differential: same file, after the fix."""
        with open(os.path.join(ROOT, PRE_FIX_PATH), encoding="utf-8") as f:
            src = f.read()
        self.assertEqual(pve.findings_for(src, self.tops, ROOT, PRE_FIX_PATH),
                         [])


class TestTokeniser(unittest.TestCase):
    """The filters, each pinned separately.

    These are X004's rules, and the reason to re-test them here rather than
    trust `test_xref_check.py` is that this file's tokeniser is a MODIFIED
    copy: `*` added to the character class, `\\*` removed from the
    placeholder set. A copy with two deliberate differences needs its own
    tests for the parts that are supposed to be the same.
    """

    def setUp(self):
        self.tops = pve.top_level_dirs(ROOT)

    def toks(self, text):
        return sorted(t for t, _ in pve.prose_globs(text, self.tops))

    def test_a_glob_is_now_a_token_which_is_the_whole_point(self):
        self.assertEqual(self.toks("`skills/*/scripts/test_*.py`"),
                         ["skills/*/scripts/test_*.py"])

    def test_a_token_with_no_glob_is_not_a_candidate(self):
        """X004's job, not this one's. Two checkers, one population each."""
        self.assertEqual(self.toks("`skills/skill-authoring/scripts`"), [])

    def test_an_unanchored_token_is_ignored(self):
        self.assertEqual(self.toks("`tests/*.py` and `/tmp/*.json`"), [])

    def test_a_hard_wrapped_token_is_ignored(self):
        """A newline is not a terminator: this repo wraps at ~72 columns."""
        self.assertEqual(self.toks("`skills/*/scr\nipts`"), [])

    def test_the_NNN_metavariable_is_suppressed(self):
        self.assertEqual(self.toks("`knowledge/round-NNN-*.md`"), [])

    def test_the_4NN_metavariable_is_suppressed(self):
        """The census's only tokeniser artifact, fixed by `\\dNN`.

        `state/whence/round-4NN/run*.json` appears in research-state.md as a
        range metavariable. X004 does not need this rule because its own
        placeholder set never sees a token that far along.
        """
        self.assertEqual(self.toks("`state/whence/round-4NN/run*.json`"), [])

    def test_an_angle_bracket_placeholder_never_forms_a_token(self):
        self.assertEqual(self.toks("`skills/<name>/scripts/*.py`"), [])

    def test_trailing_prose_punctuation_is_stripped(self):
        """`see harness/tests/*.py.` — the period ends the sentence.

        The rule X004 does not have, because `*` truncates its match before
        the sentence ends. Without it, every pattern at the end of a sentence
        reads as dead and the census is noise.
        """
        self.assertEqual(self.toks("see `harness/tests/*.py`."),
                         ["harness/tests/*.py"])
        self.assertEqual(self.toks("see harness/tests/*.py."),
                         ["harness/tests/*.py"])

    def test_the_terminator_set_is_byte_identical_to_xref_checks(self):
        """`copy-parity-differential`: the copy cannot drift silently.

        `PATH_TERMINATORS` is copied rather than imported so that this
        skill's scripts do not depend on another skill's directory layout.
        A copy with no parity test is just a fork.
        """
        path = os.path.join(ROOT, "skills", "skill-authoring", "scripts")
        sys.path.insert(0, path)
        try:
            import xref_check
        finally:
            sys.path.remove(path)
        self.assertEqual(pve.PATH_TERMINATORS, xref_check.PATH_TERMINATORS)

    def test_the_placeholder_set_differs_from_xrefs_in_exactly_two_ways(self):
        """The two deliberate differences, asserted rather than described.

        Dropping `\\*` is what makes a glob visible here; adding `\\dNN` is
        round 477's census fix. A third difference appearing without a test
        means somebody widened the tokeniser and did not say so.
        """
        path = os.path.join(ROOT, "skills", "skill-authoring", "scripts")
        sys.path.insert(0, path)
        try:
            import xref_check
        finally:
            sys.path.remove(path)
        mine = set(pve.PLACEHOLDER_RE.pattern.split("|"))
        theirs = set(xref_check.PLACEHOLDER_RE.pattern.split("|"))
        self.assertEqual(theirs - mine, {r"\*"})
        self.assertEqual(mine - theirs, {r"\dNN"})
        # `\?` is INERT in this file's tokeniser (`?` is a terminator, so it
        # cannot appear inside a token) and is kept anyway, so that this
        # differential has exactly two deltas rather than three. The first
        # draft dropped it and this assertion caught the module's own
        # "minus one, plus one" docstring being false.
        self.assertIn(r"\?", mine)


class TestLiveTree(unittest.TestCase):

    def test_the_live_tree_has_no_pattern_enumeration_disagreement(self):
        """THE enforcement. Zero is the answer round 477 shipped.

        ~7 s: it parses every tracked `.py` file. That cost is why this rides
        in a test rather than as an eleventh `corpus_check` checker — see
        `pattern_vs_enum.__doc__`.
        """
        found = pve.audit(ROOT)
        self.assertEqual(found, [], "\n".join(
            "E001 %s:%d %s MISSING %s" % (f["file"], f["line"], f["pattern"],
                                          ", ".join(f["missing"]))
            for f in found))

    def test_the_cli_exit_code_follows_the_findings(self):
        """0 clean, 1 dirty, and the dirty branch is exercised offline.

        A CLI whose non-zero branch is never run is a CLI whose non-zero
        branch does not work — this tree has burned a round on exactly that.
        """
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "harness"))
            # A REAL git repo: `audit` reaches `tracked_files`, which shells
            # out to `git ls-files`, and an empty temp directory is not a
            # repo. Testing the clean branch against a non-repo would have
            # measured git's error path, not this file's.
            for cmd in (["init", "-q"], ["add", "harness"]):
                subprocess.run(["git", "-C", tmp] + cmd, check=False,
                               capture_output=True)
            self.assertEqual(pve.main(["--repo-root", tmp, "audit"]), 0)
        self.assertEqual(pve.main(["--repo-root", "/nonexistent", "audit"]), 2)

    def test_a_record_file_is_excluded_from_the_present_tense_census(self):
        """`is_record` — a transcript is not a claim."""
        self.assertTrue(pve.is_record("logs/round-431.json"))
        self.assertTrue(pve.is_record("state/skills/round-477/PREDICTIONS.md"))
        self.assertTrue(pve.is_record("state/round-017-predictions.md"))
        self.assertTrue(pve.is_record("state/research-state-archive.md"))
        self.assertFalse(pve.is_record("state/research-state.md"))
        self.assertFalse(pve.is_record("harness/swe/slowtier.py"))


if __name__ == "__main__":
    unittest.main()

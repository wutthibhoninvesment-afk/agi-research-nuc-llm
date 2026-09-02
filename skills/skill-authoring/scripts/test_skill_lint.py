"""Tests for skill_lint.py. Run:  python3 -m unittest test_skill_lint -v"""

import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skill_lint  # noqa: E402

#: This repo's root, for the round-463 test that names the caller
#: which passes --house. Three levels up from skills/skill-authoring/scripts/.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

GOOD_DESC = ("Validates SKILL.md files against official constraints. "
             "Use when authoring or reviewing skills.")


def make_skill(root, dirname="my-skill", name=None, desc=GOOD_DESC,
               body="## When to use (triggers)\n- x\n\n## Steps\n1. do it\n\n"
                    "## Pitfalls\n- y\n\n## Verification\n```\nrun tests\n```\n",
               raw=None):
    d = os.path.join(root, dirname)
    os.makedirs(d, exist_ok=True)
    if raw is None:
        raw = f"---\nname: {name if name is not None else dirname}\n" \
              f"description: {desc}\n---\n\n# Title\n\n{body}"
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(raw)
    return d


def codes(findings, level=None):
    return [f.code for f in findings if level is None or f.level == level]


class TestFrontmatterParsing(unittest.TestCase):
    def test_simple_fields(self):
        fields, body, err = skill_lint.parse_frontmatter(
            "---\nname: foo\ndescription: bar baz\n---\nBODY")
        self.assertIsNone(err)
        self.assertEqual(fields["name"], "foo")
        self.assertEqual(fields["description"], "bar baz")
        self.assertEqual(body, "BODY")

    def test_quoted_value(self):
        fields, _, _ = skill_lint.parse_frontmatter(
            '---\nname: foo\ndescription: "quoted: value"\n---\n')
        self.assertEqual(fields["description"], "quoted: value")

    def test_folded_block_scalar(self):
        fields, _, err = skill_lint.parse_frontmatter(
            "---\nname: foo\ndescription: >-\n  line one\n  line two\n---\n")
        self.assertIsNone(err)
        self.assertEqual(fields["description"], "line one line two")

    def test_nested_mapping_captured_not_fatal(self):
        fields, _, err = skill_lint.parse_frontmatter(
            "---\nname: foo\nmetadata:\n  type: user\ndescription: d\n---\n")
        self.assertIsNone(err)
        self.assertEqual(fields["description"], "d")
        self.assertIn("metadata", fields)

    def test_missing_frontmatter(self):
        _, _, err = skill_lint.parse_frontmatter("# Just a doc\n")
        self.assertIn("no frontmatter", err)

    def test_unclosed_frontmatter(self):
        _, _, err = skill_lint.parse_frontmatter("---\nname: foo\n")
        self.assertIn("never closed", err)

    def test_body_hrule_not_treated_as_close(self):
        _, body, err = skill_lint.parse_frontmatter(
            "---\nname: f\ndescription: d\n---\nA\n---\nB")
        self.assertIsNone(err)
        self.assertEqual(body, "A\n---\nB")


class TestNameChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def lint(self, **kw):
        return skill_lint.lint_skill(make_skill(self.root, **kw))

    def test_clean_skill_no_findings(self):
        self.assertEqual(self.lint(), [])

    def test_missing_name(self):
        raw = f"---\ndescription: {GOOD_DESC}\n---\nbody\n"
        self.assertIn("N001", codes(self.lint(raw=raw), "ERROR"))

    def test_name_too_long(self):
        long = "a" * 65
        f = self.lint(dirname=long, name=long)
        self.assertIn("N002", codes(f, "ERROR"))

    def test_name_bad_charset(self):
        for bad in ("My-Skill", "my_skill", "my--skill", "-lead", "trail-"):
            f = skill_lint.lint_skill(
                make_skill(self.root, dirname="d" + bad.lower().replace("_", ""),
                           name=bad))
            self.assertIn("N003", codes(f, "ERROR"), bad)

    def test_reserved_words(self):
        for bad in ("claude-tools", "anthropic-helper"):
            f = skill_lint.lint_skill(make_skill(self.root, dirname=bad, name=bad))
            self.assertIn("N004", codes(f, "ERROR"), bad)

    def test_name_dir_mismatch_warns(self):
        f = self.lint(dirname="dir-name", name="other-name")
        self.assertIn("N005", codes(f, "WARN"))


class TestDescriptionChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def lint(self, desc):
        return skill_lint.lint_skill(make_skill(self.root, desc=desc))

    def test_missing_description(self):
        raw = "---\nname: my-skill\n---\nbody\n"
        f = skill_lint.lint_skill(make_skill(self.root, raw=raw))
        self.assertIn("D001", codes(f, "ERROR"))

    def test_too_long(self):
        f = self.lint("Use when x. " + "a" * 1024)
        self.assertIn("D002", codes(f, "ERROR"))

    def test_xml_tags(self):
        f = self.lint("Processes <files> quickly. Use when needed.")
        self.assertIn("D003", codes(f, "ERROR"))

    def test_first_person_warns(self):
        f = self.lint("I can help you process Excel files when asked.")
        self.assertIn("D004", codes(f, "WARN"))

    def test_no_trigger_phrasing_warns(self):
        f = self.lint("Processes Excel files and generates reports.")
        self.assertIn("D005", codes(f, "WARN"))

    def test_good_description_clean(self):
        f = self.lint("Processes Excel files. Use when analyzing .xlsx data.")
        self.assertEqual(codes(f), [])

    def test_block_scalar_description_warns_d006(self):
        raw = ("---\nname: my-skill\ndescription: >-\n"
               "  Processes files. Use when working with files.\n---\nbody\n")
        f = skill_lint.lint_skill(make_skill(self.root, raw=raw))
        self.assertIn("D006", codes(f, "WARN"))
        self.assertNotIn("D001", codes(f))

    def test_next_line_description_warns_d006_not_d001(self):
        raw = ("---\nname: my-skill\ndescription:\n"
               "  Long text on the next line. Use when testing parsers.\n"
               "---\nbody\n")
        f = skill_lint.lint_skill(make_skill(self.root, raw=raw))
        self.assertIn("D006", codes(f, "WARN"))
        self.assertNotIn("D001", codes(f))


class TestBodyChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_body_over_500_lines_errors(self):
        f = skill_lint.lint_skill(
            make_skill(self.root, body="x\n" * 501))
        self.assertIn("B001", codes(f, "ERROR"))

    def test_body_over_400_warns(self):
        f = skill_lint.lint_skill(make_skill(self.root, body="x\n" * 420))
        self.assertIn("B002", codes(f, "WARN"))

    def test_windows_path_in_prose_warns(self):
        f = skill_lint.lint_skill(
            make_skill(self.root, body="Run scripts\\helper.py to start.\n"))
        self.assertIn("B003", codes(f, "WARN"))

    def test_backslash_inside_code_fence_ok(self):
        body = "```python\ns = 'a\\nb'\npath = 'x\\\\y'\n```\n"
        f = skill_lint.lint_skill(make_skill(self.root, body=body))
        self.assertNotIn("B003", codes(f))

    def test_broken_relative_link_errors(self):
        f = skill_lint.lint_skill(
            make_skill(self.root, body="See [ref](references/nope.md).\n"))
        self.assertIn("R001", codes(f, "ERROR"))

    def test_urls_and_anchors_skipped_by_r001(self):
        # R001 is a FILE-existence check, so a URL and a bare fragment are
        # both out of its scope. The fragment is not unchecked, though --
        # since round 333 it is R006's job (see TestAnchorResolution).
        body = "See [d](https://example.com/x) and [a](#section).\n"
        f = skill_lint.lint_skill(make_skill(self.root, body=body))
        self.assertNotIn("R001", codes(f))
        self.assertIn("R006", codes(f, "ERROR"))       # no `## Section` heading

    def test_existing_link_ok_and_long_ref_needs_toc(self):
        d = make_skill(self.root, body="See [ref](references/big.md).\n")
        refdir = os.path.join(d, "references")
        os.makedirs(refdir)
        with open(os.path.join(refdir, "big.md"), "w") as fh:
            fh.write("# Big\n" + "line\n" * 150)
        f = skill_lint.lint_skill(d)
        self.assertNotIn("R001", codes(f))
        self.assertIn("R002", codes(f, "WARN"))
        # add a ToC -> warning clears
        with open(os.path.join(refdir, "big.md"), "w") as fh:
            fh.write("# Big\n## Contents\n- a\n" + "line\n" * 150)
        f = skill_lint.lint_skill(d)
        self.assertNotIn("R002", codes(f))


class TestHouseChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_house_body_clean(self):
        f = skill_lint.lint_skill(make_skill(self.root), house=True)
        self.assertEqual(codes(f), [])

    def test_bare_body_fails_all_house_checks(self):
        f = skill_lint.lint_skill(
            make_skill(self.root, body="Just some prose.\n"), house=True)
        got = codes(f, "ERROR")
        for c in ("H001", "H002", "H003", "H004", "H005"):
            self.assertIn(c, got)

    def test_house_off_by_default(self):
        f = skill_lint.lint_skill(
            make_skill(self.root, body="Just some prose.\n"))
        self.assertFalse([c for c in codes(f) if c.startswith("H")])


class TestH006ReferencesSplitTookTheCommands(unittest.TestCase):
    """Round 429. B002 tells an author to shorten a long SKILL.md and
    transcripts are the easiest lines to move; nothing then noticed that the
    `## Verification` section's only runnable commands had gone with them.
    `pristine-checkout-differential` parsed to ZERO commands for two rounds
    that way, and `generator-trampoline-evaluator` for longer.

    The discriminator is `fenced_invocations`, not "has a fence": a
    references file full of Python SOURCE (which is what
    `filter-shares-the-defect` has — four fenced blocks, fifteen lines, zero
    invocations) is a legitimately prose-only skill and must stay silent."""

    PROSE_VERIF = ("## When to use (triggers)\n- x\n\n## Steps\n1. do it\n\n"
                   "```\nillustrative fence, not in Verification\n```\n\n"
                   "## Pitfalls\n- y\n\n## Verification\n- a judgement, "
                   "no command\n")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, body, ref_text=None, dirname="my-skill"):
        d = make_skill(self.root, dirname=dirname, body=body)
        if ref_text is not None:
            os.makedirs(os.path.join(d, "references"), exist_ok=True)
            with open(os.path.join(d, "references", "log.md"), "w",
                      encoding="utf-8") as f:
                f.write(ref_text)
        return d

    def test_fires_when_the_commands_moved_into_references(self):
        d = self.build(self.PROSE_VERIF,
                       "# log\n\n```\npython3 -m pytest -q tests/x.py\n```\n")
        f = skill_lint.lint_skill(d, house=True)
        self.assertIn("H006", codes(f, "ERROR"))
        msg = [x.message for x in f if x.code == "H006"][0]
        self.assertIn("references/log.md (1)", msg)

    def test_the_dollar_prompt_still_counts_as_an_invocation(self):
        """`pristine-checkout-differential`'s transcripts are shell sessions:
        every command line is prefixed `$ `. Without this the rule would have
        missed the exact case that motivated it."""
        d = self.build(self.PROSE_VERIF,
                       "```\n$ python3 harness/pristine_check.py dirt\n"
                       "tracked-modified 2 (blocking 0)\n```\n")
        self.assertIn("H006", codes(skill_lint.lint_skill(d, house=True),
                                    "ERROR"))

    def test_silent_when_the_references_fence_is_source_not_commands(self):
        d = self.build(self.PROSE_VERIF,
                       "```\n_RE = re.compile(r\"^expected (.*)$\")\n"
                       "mh = _RE.match(h)\n```\n")
        self.assertNotIn("H006", codes(skill_lint.lint_skill(d, house=True)))

    def test_silent_when_verification_has_its_own_fence(self):
        d = self.build("## When to use (triggers)\n- x\n\n## Steps\n1. go\n\n"
                       "## Pitfalls\n- y\n\n## Verification\n```\n"
                       "python3 -m pytest -q\n```\n",
                       "```\npython3 -m pytest -q tests/x.py\n```\n")
        self.assertNotIn("H006", codes(skill_lint.lint_skill(d, house=True)))

    def test_silent_with_no_references_directory(self):
        d = self.build(self.PROSE_VERIF)
        self.assertNotIn("H006", codes(skill_lint.lint_skill(d, house=True)))

    def test_silent_outside_house_mode(self):
        d = self.build(self.PROSE_VERIF,
                       "```\npython3 -m pytest -q tests/x.py\n```\n")
        self.assertNotIn("H006", codes(skill_lint.lint_skill(d)))

    def test_an_invocation_outside_a_fence_does_not_count(self):
        """Prose in a references file often NAMES a command mid-sentence.
        Only fenced lines are invocations, the same rule `claim_check`
        applies to SKILL.md itself."""
        d = self.build(self.PROSE_VERIF,
                       "We ran it under\npython3 -m pytest -q tests/x.py\n"
                       "and it was green.\n")
        self.assertNotIn("H006", codes(skill_lint.lint_skill(d, house=True)))

    def test_a_verbish_word_is_not_an_invocation(self):
        """`(?![\\w.-])` and not `\\b`: `python3` must not be matched inside
        `python3x`, and `make` must not match `makefiles are ...`."""
        d = self.build(self.PROSE_VERIF,
                       "```\nmakefiles are generated here\nnodes: 12\n```\n")
        self.assertNotIn("H006", codes(skill_lint.lint_skill(d, house=True)))

    def test_the_live_corpus_has_no_H006(self):
        """The enforcement. Round 429 cleared both instances; a future
        references split that takes the commands with it lands here."""
        skills = os.path.join(skill_lint.__file__.rsplit("scripts", 1)[0]
                              .rsplit("skill-authoring", 1)[0])
        if not os.path.isdir(skills):
            self.skipTest("live corpus not present")
        hits = []
        for d in sorted(skill_lint.discover_skill_dirs(skills)):
            hits += [f for f in skill_lint.lint_skill(d, house=True)
                     if f.code == "H006"]
        self.assertEqual([str(h) for h in hits], [])


class TestDiscoveryAndMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_discover_single_and_collection(self):
        a = make_skill(self.root, dirname="skill-a")
        make_skill(self.root, dirname="skill-b")
        self.assertEqual(skill_lint.discover_skill_dirs(a), [a])
        found = skill_lint.discover_skill_dirs(self.root)
        self.assertEqual(sorted(os.path.basename(p) for p in found),
                         ["skill-a", "skill-b"])

    def test_main_exit_codes(self):
        make_skill(self.root, dirname="good-skill")
        self.assertEqual(skill_lint.main([self.root]), 0)
        bad = make_skill(self.root, dirname="bad-skill",
                         raw="# no frontmatter\n")
        self.assertEqual(skill_lint.main([bad]), 1)
        self.assertEqual(skill_lint.main([os.path.join(self.root, "absent")]), 2)

    def test_strict_promotes_warnings(self):
        d = make_skill(self.root, dirname="dir-name", name="other-name")
        self.assertEqual(skill_lint.main([d]), 0)
        self.assertEqual(skill_lint.main(["--strict", d]), 1)

    def test_missing_skill_md_in_named_dir(self):
        d = os.path.join(self.root, "empty-dir")
        os.makedirs(d)
        self.assertEqual(skill_lint.main([d]), 2)


class TestReferenceHygiene(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def _skill(self, body, files):
        d = make_skill(self.root, body=body)
        for rel, content in files.items():
            p = os.path.join(d, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
        return d

    def test_r003_reference_linking_onward_warns(self):
        d = self._skill("See [ref](references/a.md).\n\n1. step\n",
                        {"references/a.md": "# A\nmore in [b](b.md)\n",
                         "references/b.md": "# B\n"})
        c = codes(skill_lint.lint_skill(d))
        self.assertIn("R003", c)

    def test_r003_not_raised_when_onward_target_also_linked_from_skill(self):
        d = self._skill("See [a](references/a.md) and [b](references/b.md).\n\n1. step\n",
                        {"references/a.md": "# A\nsee [b](b.md)\n",
                         "references/b.md": "# B\n"})
        c = codes(skill_lint.lint_skill(d))
        self.assertNotIn("R003", c)

    def test_r003_backlink_to_skill_md_is_fine(self):
        d = self._skill("See [a](references/a.md).\n\n1. step\n",
                        {"references/a.md": "# A\nback to [skill](../SKILL.md)\n"})
        self.assertNotIn("R003", codes(skill_lint.lint_skill(d)))

    def test_r004_duplicated_paragraph_warns(self):
        para = ("This paragraph is long enough to count as duplicated content because "
                "it exceeds the minimum chunk size used by the linter for detection.")
        d = self._skill("Intro [ref](references/a.md).\n\n%s\n\n1. step\n" % para,
                        {"references/a.md": "# A\n\nsome text\n\n  %s  \n" % para})
        f = [x for x in skill_lint.lint_skill(d) if x.code == "R004"]
        self.assertEqual(len(f), 1)
        self.assertIn("1 paragraph", f[0].message)

    def test_r004_duplicated_code_block_warns(self):
        code = "python3 scripts/tool.py --flag one --flag two --flag three --flag four --flag five --flag six\n" \
               "python3 scripts/tool.py --other run this exact same command again for length\n"
        d = self._skill("[ref](references/a.md)\n\n```bash\n%s```\n\n1. step\n" % code,
                        {"references/a.md": "# A\n```bash\n%s```\n" % code})
        self.assertIn("R004", codes(skill_lint.lint_skill(d)))

    def test_r004_short_or_heading_overlap_is_not_duplication(self):
        d = self._skill("## Steps\n\nRun the linter.\n\n1. step [ref](references/a.md)\n",
                        {"references/a.md": "## Steps\n\nRun the linter.\n"})
        self.assertNotIn("R004", codes(skill_lint.lint_skill(d)))

    def test_content_chunks_splits_prose_and_fences(self):
        body = "# H\n\n" + "a" * 130 + "\n\n```\n" + "b" * 130 + "\n```\n\nshort\n"
        chunks = skill_lint.content_chunks(body)
        self.assertEqual(chunks, ["a" * 130, "b" * 130])

    def test_r005_unreferenced_bundled_file_warns(self):
        d = self._skill("1. step\n", {"references/orphan.md": "# lonely\n"})
        f = [x for x in skill_lint.lint_skill(d) if x.code == "R005"]
        self.assertEqual(len(f), 1)
        self.assertIn("references/orphan.md", f[0].message)

    def test_r005_mention_by_path_or_basename_counts(self):
        d = self._skill("1. run `python3 scripts/tool.py`\n2. read notes.md\n",
                        {"scripts/tool.py": "print(1)\n", "references/notes.md": "# n\n"})
        self.assertNotIn("R005", codes(skill_lint.lint_skill(d)))

    def test_r005_test_of_referenced_script_is_exempt(self):
        d = self._skill("1. run `python3 scripts/tool.py`\n",
                        {"scripts/tool.py": "x\n", "scripts/test_tool.py": "y\n",
                         "scripts/test_other.py": "z\n"})
        f = [x for x in skill_lint.lint_skill(d) if x.code == "R005"]
        self.assertEqual([x.message.split()[2] for x in f], ["scripts/test_other.py"])

    def test_r005_directory_or_glob_mention_covers_children(self):
        d = self._skill("1. read `references/layouts/<layout>.md`\n2. see `templates/`\n",
                        {"references/layouts/grid.md": "# g\n", "templates/a/b.tex": "x\n"})
        self.assertNotIn("R005", codes(skill_lint.lint_skill(d)))

    def test_r005_sibling_path_does_not_mention_directory(self):
        d = self._skill("1. run `python3 scripts/a.py`\n",
                        {"scripts/a.py": "x\n", "scripts/b.py": "y\n"})
        f = [x for x in skill_lint.lint_skill(d) if x.code == "R005"]
        self.assertEqual([x.message.split()[2] for x in f], ["scripts/b.py"])

    def test_r005_exempts_licence_and_private_helpers(self):
        d = self._skill("1. run `python3 scripts/a.py`\n",
                        {"scripts/a.py": "x\n", "scripts/_util.py": "y\n",
                         "scripts/__init__.py": "", "LICENSE": "MIT\n", "LICENSE.txt": "MIT\n"})
        self.assertNotIn("R005", codes(skill_lint.lint_skill(d)))

    def test_r005_ignores_hidden_and_cache_files(self):
        d = self._skill("1. step\n", {"scripts/__pycache__/x.pyc": "", ".DS_Store": ""})
        self.assertNotIn("R005", codes(skill_lint.lint_skill(d)))


class TestHeadingSlug(unittest.TestCase):
    """github-slugger semantics. The no-collapsing rule is load-bearing:
    both real-corpus cases below decide it, in opposite directions."""

    def test_real_corpus_flag_heading_keeps_every_hyphen(self):
        # `## Fire rates (`--repeats N`)` -> one hyphen for the space plus the
        # flag's own two. Collapsing runs of hyphens would give the wrong slug
        # (and is exactly the typo round 333 found rotting in a live ToC).
        self.assertEqual(skill_lint.heading_slug("Fire rates (`--repeats N`)"),
                         "fire-rates---repeats-n")
        self.assertEqual(skill_lint.heading_slug("Body-following (`--mode body`)"),
                         "body-following---mode-body")
        self.assertEqual(skill_lint.heading_slug("Probe audit (`--audit`)"),
                         "probe-audit---audit")

    def test_real_corpus_em_dash_heading_keeps_both_spaces(self):
        # The em dash is DROPPED, but the spaces on either side of it each
        # become a hyphen. Collapsing whitespace would give the wrong slug.
        self.assertEqual(skill_lint.heading_slug("Instrument drift \u2014 canary"),
                         "instrument-drift--canary")

    def test_plain_and_punctuation(self):
        self.assertEqual(skill_lint.heading_slug("Case file"), "case-file")
        self.assertEqual(skill_lint.heading_slug("Reading the report"),
                         "reading-the-report")
        self.assertEqual(skill_lint.heading_slug("What's *this*, then?"),
                         "whats-this-then")

    def test_underscores_and_digits_survive(self):
        self.assertEqual(skill_lint.heading_slug("run_tests_fast.sh v2"),
                         "run_tests_fastsh-v2")

    def test_closed_atx_hashes_stripped(self):
        self.assertEqual(skill_lint.heading_slug("Closed ATX ##"), "closed-atx")

    def test_punctuation_only_heading_slugs_to_empty(self):
        self.assertEqual(skill_lint.heading_slug("!!!"), "")


class TestMdAnchors(unittest.TestCase):
    def test_explicit_and_heading_anchors(self):
        allc, expl = skill_lint.md_anchors(
            '# Top\n<a id="deep-dive"></a>\n## Deep dive\n')
        self.assertEqual(expl, {"deep-dive"})
        self.assertEqual(allc, {"top", "deep-dive"})

    def test_name_attribute_and_single_quotes(self):
        _, expl = skill_lint.md_anchors("<a name='x'></a>\n<a  id='y' >\n")
        self.assertEqual(expl, {"x", "y"})

    def test_duplicate_headings_get_github_suffixes(self):
        allc, _ = skill_lint.md_anchors("## Dup\n## Dup\n## Dup\n")
        self.assertEqual(allc, {"dup", "dup-1", "dup-2"})

    def test_heading_inside_fence_is_not_an_anchor(self):
        allc, _ = skill_lint.md_anchors(
            "# Real\n\n```\n# summary: not a heading\n```\n")
        self.assertEqual(allc, {"real"})


class TestAnchorResolution(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def _skill(self, body, files=None):
        d = make_skill(self.root, body=body)
        for rel, content in (files or {}).items():
            p = os.path.join(d, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
        return d

    def _msgs(self, d, code):
        return [f.message for f in skill_lint.lint_skill(d) if f.code == code]

    # --- R006 ---
    def test_r006_same_file_fragment_missing(self):
        d = self._skill("## Steps\n1. see [below](#nowhere)\n")
        self.assertIn("R006", codes(skill_lint.lint_skill(d), "ERROR"))

    def test_r006_same_file_fragment_resolving_to_heading_is_clean(self):
        d = self._skill("## Steps\n1. see [below](#pitfalls)\n\n## Pitfalls\n- x\n")
        self.assertNotIn("R006", codes(skill_lint.lint_skill(d)))

    def test_r006_reference_fragment_missing(self):
        d = self._skill("See [r](references/a.md#gone).\n\n1. step\n",
                        {"references/a.md": "# A\n## Present\n"})
        msgs = self._msgs(d, "R006")
        self.assertEqual(len(msgs), 1)
        self.assertIn("#gone", msgs[0])
        self.assertIn("references/a.md", msgs[0])

    def test_r006_reference_fragment_present_via_explicit_anchor(self):
        d = self._skill("See [r](references/a.md#tag).\n\n1. step\n",
                        {"references/a.md": '# A\n<a id="tag"></a>\n## Whatever\n'})
        self.assertNotIn("R006", codes(skill_lint.lint_skill(d)))

    def test_r006_reference_fragment_present_via_heading_slug(self):
        d = self._skill("See [r](references/a.md#deep-dive).\n\n1. step\n",
                        {"references/a.md": "# A\n## Deep dive\n"})
        self.assertNotIn("R006", codes(skill_lint.lint_skill(d)))

    def test_r006_catches_rot_in_a_references_own_toc(self):
        # The real round-333 shape: SKILL.md's own links are all fine; the
        # broken fragment is a same-file ToC entry INSIDE the reference.
        d = self._skill("See [r](references/a.md#kept).\n\n1. step\n",
                        {"references/a.md": "# A\n## Contents\n"
                                            "- [Kept](#kept)\n- [Rotted](#renamed-away)\n"
                                            "## Kept\n"})
        msgs = self._msgs(d, "R006")
        self.assertEqual(len(msgs), 1)
        self.assertIn("#renamed-away", msgs[0])
        self.assertIn("in references/a.md", msgs[0])

    def test_r006_silent_when_target_file_missing_r001_owns_that(self):
        d = self._skill("See [r](references/nope.md#frag).\n\n1. step\n")
        found = codes(skill_lint.lint_skill(d))
        self.assertIn("R001", found)
        self.assertNotIn("R006", found)       # exactly one finding per defect

    def test_r006_ignores_non_markdown_and_url_fragments(self):
        d = self._skill("See `scripts/a.py` [line](scripts/a.py#L10) and "
                        "[web](https://x.example/p#frag).\n\n1. step\n",
                        {"scripts/a.py": "x = 1\n"})
        self.assertNotIn("R006", codes(skill_lint.lint_skill(d)))

    def test_r006_ignores_links_inside_code_fences(self):
        d = self._skill("## Steps\n1. run\n\n```\n[x](#nowhere)\n```\n")
        self.assertNotIn("R006", codes(skill_lint.lint_skill(d)))

    # --- R007 ---
    def test_r007_orphaned_explicit_anchor_warns(self):
        d = self._skill("See [r](references/a.md).\n\n1. step\n",
                        {"references/a.md": '# A\n<a id="orphan"></a>\n## Thing\n'})
        msgs = self._msgs(d, "R007")
        self.assertEqual(len(msgs), 1)
        self.assertIn("orphan", msgs[0])

    def test_r007_quiet_when_linked_from_skill_md(self):
        d = self._skill("See [r](references/a.md#used).\n\n1. step\n",
                        {"references/a.md": '# A\n<a id="used"></a>\n## Thing\n'})
        self.assertNotIn("R007", codes(skill_lint.lint_skill(d)))

    def test_r007_quiet_when_linked_only_from_the_references_own_toc(self):
        d = self._skill("See [r](references/a.md).\n\n1. step\n",
                        {"references/a.md": '# A\n## Contents\n- [T](#used)\n'
                                            '<a id="used"></a>\n## Thing\n'})
        self.assertNotIn("R007", codes(skill_lint.lint_skill(d)))

    def test_r007_ignores_heading_slugs_only_explicit_anchors_count(self):
        d = self._skill("1. step\n\n## An Unlinked Heading\n")
        self.assertNotIn("R007", codes(skill_lint.lint_skill(d)))


class TestLiveCorpusAnchors(unittest.TestCase):
    """Regression guard on the real skills/ tree: rot an anchor in any
    SKILL.md or first-level reference and this fails. Round 333 added it
    after finding one already rotted (`#fire-rates--repeats-n`)."""

    def test_every_fragment_in_the_real_corpus_resolves(self):
        skills_root = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", ".."))
        dirs = skill_lint.discover_skill_dirs(skills_root)
        self.assertGreater(len(dirs), 10, "corpus not found at %s" % skills_root)
        bad = [str(f) for d in dirs for f in skill_lint.lint_skill(d)
               if f.code in ("R006", "R007")]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()


class TestSiblingSkillLinks(unittest.TestCase):
    """R002/R003/R004 police BUNDLED references, not links to other skills.

    Round 345: `skill-authoring/SKILL.md` linking
    `../citation-registry-integrity/SKILL.md` tripped R002 for having no ToC,
    which is advice about progressive-disclosure files and meaningless for a
    sibling skill.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="lint-sib-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def _skill(self, name, body, refs=None):
        d = make_skill(self.root, dirname=name, body=body)
        if refs:
            os.makedirs(os.path.join(d, "references"), exist_ok=True)
            for rn, rt in refs.items():
                with open(os.path.join(d, "references", rn), "w",
                          encoding="utf-8") as f:
                    f.write(rt)
        return d

    def test_a_long_sibling_skill_needs_no_toc(self):
        self._skill("other", "# Other\n" + "line\n" * 150)
        me = self._skill("mine", "see [other](../other/SKILL.md)")
        self.assertNotIn("R002", codes(skill_lint.lint_skill(me)))

    def test_a_long_bundled_reference_still_needs_a_toc(self):
        me = self._skill("mine", "see [r](references/r.md)",
                         refs={"r.md": "# R\n" + "line\n" * 150})
        self.assertIn("R002", codes(skill_lint.lint_skill(me)))

    def test_a_sibling_skills_own_links_do_not_count_against_depth(self):
        self._skill("other", "see [deep](references/d.md)",
                    refs={"d.md": "# D\n"})
        me = self._skill("mine", "see [other](../other/SKILL.md)")
        self.assertNotIn("R003", codes(skill_lint.lint_skill(me)))

    def test_a_broken_sibling_link_is_still_an_error(self):
        # The exemption is about R002/R003/R004 only. R001 must still fire,
        # or the exemption becomes a way to smuggle in dead links.
        me = self._skill("mine", "see [gone](../nope/SKILL.md)")
        self.assertIn("R001", codes(skill_lint.lint_skill(me)))

    def test_is_sibling_skill_excludes_the_file_itself(self):
        p = os.path.join(self.root, "a", "SKILL.md")
        self.assertFalse(skill_lint.is_sibling_skill(p, p))
        self.assertTrue(skill_lint.is_sibling_skill(
            os.path.join(self.root, "b", "SKILL.md"), p))
        self.assertFalse(skill_lint.is_sibling_skill(
            os.path.join(self.root, "a", "references", "x.md"), p))


class TestHouseModeIsNotSilentlyOff(unittest.TestCase):
    """Round 463 (harness A). A subset run must not look like a full one.

    `--house` is what turns H001-H006 on and `corpus_check.checks()` passes
    it, so `skill_lint.py --strict skills/<new>` -- the command a round
    naturally types to verify its own new skill -- applies a strictly weaker
    rule set than the check that runs after the round exits. Three rounds
    have shipped an H001-red SKILL.md that way: 363 (recorded in
    `skills/measured-not-declared-dependencies/SKILL.md`'s own header), 462
    (`residual-audited-both-ways`, red from the round it landed until 463),
    and 463 itself.

    This is round 453's `corpus_check.subset_clause` reasoning applied one
    level down: the fix is not to change the default, which would rewrite
    every historical verdict, but to stop the weaker run from printing a line
    indistinguishable from the stronger one.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="house-clause.")
        d = os.path.join(self.root, "s")
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: s\ndescription: Use when a thing happens "
                     "and you want the other thing done to it.\n---\n\n"
                     "# S\n\n## When this fires\n\nprose\n")
        self.skill = d

    def _run(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = skill_lint.main(argv)
        return rc, buf.getvalue()

    def test_without_house_the_summary_says_the_rules_were_not_applied(self):
        rc, out = self._run(["--strict", self.skill])
        self.assertEqual(rc, 0)
        self.assertIn("house format NOT enforced", out)
        self.assertIn("--house", out)

    def test_with_house_the_line_is_byte_identical_to_what_rounds_logged(self):
        """The SUMMARY line, not the whole stream -- H005's own message
        contains the words `house format` and is not the clause."""
        rc, out = self._run(["--house", "--strict", self.skill])
        self.assertEqual(rc, 1)
        summary = [l for l in out.splitlines() if l.startswith("skill-lint:")]
        self.assertEqual(summary,
                         ["skill-lint: 1 skill(s), 5 error(s), 0 warning(s)"])

    def test_the_clause_rides_on_the_summary_line_itself(self):
        rc, out = self._run(["--strict", self.skill])
        summary = [l for l in out.splitlines() if l.startswith("skill-lint:")]
        self.assertEqual(len(summary), 1)
        self.assertTrue(summary[0].endswith(
            "(house format NOT enforced — add --house for the rules the "
            "corpus check applies)"), summary[0])

    def test_the_two_modes_really_do_disagree_on_this_skill(self):
        """The clause would be noise if the modes agreed."""
        self.assertNotIn("H001", codes(skill_lint.lint_skill(self.skill)))
        self.assertIn("H001", codes(skill_lint.lint_skill(self.skill,
                                                          house=True)))

    def test_the_corpus_check_is_the_caller_that_passes_house(self):
        """If this ever stops being true, the clause is pointed at nothing."""
        import corpus_check
        argvs = dict(corpus_check.checks(REPO_ROOT))
        self.assertIn("--house", argvs["skill_lint"])

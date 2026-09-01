"""Tests for state_claim_check.py.

Run:  python3 -m unittest test_state_claim_check -v

Offline. The only commands any test executes are `echo`/`true`/`grep` in a
temporary directory, plus the live-corpus regression at the bottom, which is
static-only (never `--run`).

The centrepiece is `TestRound349Regression`: round 349's real next-steps text,
verbatim, pinned as a fixture. Round 351 corrected the live document, so the
tool now exits 0 against `state/research-state.md` — which would quietly
delete the evidence that it works. Keeping the historical text as a fixture is
what makes "this tool catches the bug it was written for" a re-executed claim
rather than a sentence in a knowledge file.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state_claim_check as scc  # noqa: E402
import skill_lint                # noqa: E402

REPO_ROOT = scc.DEFAULT_REPO_ROOT


def block(round_no, *items):
    return "## Next steps (as of round %d)\n" % round_no + "\n".join(items) + "\n"


def codes(findings):
    return [f.code for f in findings]


# --------------------------------------------------------------------------


class TestFindBlocks(unittest.TestCase):
    def test_finds_every_block_with_its_round_and_line(self):
        text = "intro\n" + block(10, "1. a") + "\n" + block(11, "1. b")
        blocks = scc.find_blocks(text)
        self.assertEqual([b.round_no for b in blocks], [10, 11])
        self.assertEqual(blocks[0].first_line, 2)

    def test_a_block_stops_at_the_next_round_entry_heading(self):
        # research-state.md interleaves `### Round N` entries with next-steps
        # blocks. A block that swallowed the following round entry would age
        # and check that entry's prose as if it were a live next step.
        text = block(10, "1. a") + "\n### Round 11 — skills(B)\n- did a thing\n"
        blocks = scc.find_blocks(text)
        self.assertEqual(len(blocks), 1)
        self.assertNotIn("did a thing", "\n".join(blocks[0].lines))

    def test_a_parenthetical_suffix_on_the_heading_still_parses(self):
        # Real heading in this corpus:
        # "## Next steps (as of round 272, still open except item 13 above)"
        text = "## Next steps (as of round 272, still open except item 13)\n1. a\n"
        self.assertEqual([b.round_no for b in scc.find_blocks(text)], [272])

    def test_no_blocks_is_not_a_crash(self):
        self.assertEqual(scc.find_blocks("# Nothing here\n"), [])


class TestLiveBlock(unittest.TestCase):
    def test_highest_round_wins_even_when_it_is_not_last_in_the_file(self):
        # This is the real shape of research-state.md: round 341's block sits
        # physically BETWEEN round 343's and round 349's. "Last block in the
        # file" would have picked round 333's, the oldest one there is.
        text = block(343, "1. a") + block(341, "1. b") + block(349, "1. c") \
            + block(333, "1. d")
        live, err = scc.live_block(scc.find_blocks(text))
        self.assertIsNone(err)
        self.assertEqual(live.round_no, 349)

    def test_a_tie_is_an_error_not_a_guess(self):
        text = block(349, "1. a") + block(349, "1. b")
        live, err = scc.live_block(scc.find_blocks(text))
        self.assertIsNone(live)
        self.assertIn("both claim round 349", err)

    def test_empty_document(self):
        live, err = scc.live_block([])
        self.assertIsNone(live)
        self.assertIn("no `## Next steps", err)


class TestParseItems(unittest.TestCase):
    def setUp(self):
        self.blocks = None

    def items_of(self, text):
        blocks = scc.find_blocks(text)
        for b in blocks:
            b.path = "<mem>"
        return scc.parse_items(blocks[0])

    def test_numbered_items_split(self):
        items = self.items_of(block(9, "1. first", "2. second", "3. third"))
        self.assertEqual([i.number for i in items], [1, 2, 3])
        self.assertEqual(items[1].text, "second")

    def test_wrapped_lines_are_joined_with_one_space(self):
        items = self.items_of(block(9, "1. a claim that", "   wraps here"))
        self.assertEqual(items[0].text, "a claim that wraps here")

    def test_a_backticked_command_split_across_lines_becomes_one_span(self):
        # The exact shape of round 349's item 4. Without joining, the command
        # grammar never matches and the claim is invisible.
        items = self.items_of(block(9,
                                    "4. never calls it (`grep -c mutation_test",
                                    "   harness/swe/campaign.py` -> 0), so"))
        claims = scc.extract_claims(items[0])
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].payload["cmd"],
                         "grep -c mutation_test harness/swe/campaign.py")
        self.assertEqual(claims[0].payload["claim"], "0")

    def test_char_lines_maps_a_claim_to_the_line_it_starts_on(self):
        text = block(9, "1. lead in", "   `x/SKILL.md` is still 5 body lines")
        items = self.items_of(text)
        claim = scc.extract_claims(items[0])[0]
        # heading on line 1, item line 2, claim on line 3
        self.assertEqual(claim.line, 3)

    def test_indented_sub_bullets_stay_inside_their_parent_item(self):
        # Round 351's own item 11 is a numbered item with `-` sub-bullets,
        # one per standing claim. They must fold into the parent so a claim
        # inside a sub-bullet is still extracted and still attributed.
        items = self.items_of(block(9,
                                    "11. Standing items:",
                                    "    - `a/SKILL.md` is still 5 body lines",
                                    "    - something else"))
        self.assertEqual([i.number for i in items], [11])
        self.assertEqual(len(scc.extract_claims(items[0])), 1)

    def test_an_indented_number_does_not_start_a_new_item(self):
        items = self.items_of(block(9, "1. lead", "   2. not a new item"))
        self.assertEqual([i.number for i in items], [1])

    def test_a_blank_line_ends_an_item(self):
        items = self.items_of(block(9, "1. a", "", "trailing prose"))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].text, "a")


class TestBodyLinesGrammar(unittest.TestCase):
    def one(self, text):
        item = scc.Item(None, 1, text, [1] * len(text))
        found = [c for c in scc.extract_claims(item) if c.kind == "body-lines"]
        return found[0] if found else None

    def test_is_still_n_body_lines(self):
        c = self.one("`a/SKILL.md` is still 415 body lines (B002) — carried")
        self.assertEqual(c.payload, {"path": "a/SKILL.md", "n": 415,
                                     "code": "B002"})

    def test_is_now_at_n_body_lines_without_a_code(self):
        c = self.one("`a/SKILL.md` is now at 399 body lines")
        self.assertEqual(c.payload["n"], 399)
        self.assertIsNone(c.payload["code"])

    def test_remains_and_sits_at_are_accepted(self):
        self.assertEqual(self.one("`a/SKILL.md` remains 12 body lines")
                         .payload["n"], 12)
        self.assertEqual(self.one("`a/SKILL.md` sits at 12 body lines")
                         .payload["n"], 12)

    def test_a_bolded_number_is_still_a_number(self):
        # Emphasising the figure is how a careful author writes the sentence
        # they most want read. Round 351's own correction was `is **399**
        # body lines` and extracted to nothing until the grammar allowed it.
        c = self.one("`a/SKILL.md` is **399** body lines")
        self.assertEqual(c.payload["n"], 399)

    def test_prose_without_the_pattern_is_not_a_claim(self):
        # Deliberately NOT matched: the tool would have to guess which file
        # and which count, and a guess here is the failure mode it exists to
        # prevent.
        self.assertIsNone(self.one("the skill is getting long, over 400 lines"))
        self.assertIsNone(self.one("415 body lines is the current figure"))


class TestCommandGrammar(unittest.TestCase):
    def claims(self, text):
        item = scc.Item(None, 1, text, [1] * len(text))
        return [c for c in scc.extract_claims(item) if c.kind == "command"]

    def test_arrow_forms(self):
        self.assertEqual(self.claims("`wc -l x` -> 4")[0].payload["claim"], "4")
        self.assertEqual(self.claims("`wc -l x` → 4")[0].payload["claim"], "4")

    def test_claim_stops_at_a_clause_boundary(self):
        c = self.claims("(`grep -c z f.py` -> 0), so its mutants are fine")[0]
        self.assertEqual(c.payload["claim"], "0")

    def test_markdown_bold_survives_into_the_claim(self):
        c = self.claims("`bash harness/run_tests_fast.sh` -> **412 passed**")[0]
        self.assertEqual(c.payload["claim"], "**412 passed**")

    def test_a_priced_command_is_extracted_but_never_checkable(self):
        # The safety property. `classify` fails closed, so anything the
        # allowlist does not recognise is skipped rather than executed.
        c = self.claims("`claude -p 'hello'` -> a greeting")[0]
        self.assertFalse(c.checkable)
        self.assertIn("priced", c.skip_reason)

    def test_a_network_command_is_never_checkable(self):
        c = self.claims("`ssh jab@100.78.44.111 uptime` -> up 3 days")[0]
        self.assertFalse(c.checkable)
        self.assertIn("network", c.skip_reason)

    def test_an_unknown_program_is_never_checkable(self):
        c = self.claims("`frobnicate --all` -> 7")[0]
        self.assertFalse(c.checkable)
        self.assertIn("unknown program", c.skip_reason)

    def test_backticked_prose_without_an_arrow_is_not_a_command_claim(self):
        self.assertEqual(self.claims("`MutationStage` is checkpointed"), [])


class TestResolveMd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "skills", "s"))
        os.makedirs(os.path.join(self.tmp, "state"))
        open(os.path.join(self.tmp, "skills", "s", "SKILL.md"), "w").close()
        open(os.path.join(self.tmp, "state", "notes.md"), "w").close()
        open(os.path.join(self.tmp, "top.md"), "w").close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_repo_root_relative(self):
        self.assertIsNotNone(scc.resolve_md("top.md", self.tmp))

    def test_skills_relative_which_is_how_a_skills_round_writes_it(self):
        self.assertIsNotNone(scc.resolve_md("s/SKILL.md", self.tmp))

    def test_state_relative(self):
        self.assertIsNotNone(scc.resolve_md("notes.md", self.tmp))

    def test_a_directory_is_not_a_file(self):
        self.assertIsNone(scc.resolve_md("skills", self.tmp))

    def test_unresolved_returns_none(self):
        self.assertIsNone(scc.resolve_md("nope/SKILL.md", self.tmp))


class TestCheckBodyLines(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.skill_dir = os.path.join(self.tmp, "skills", "demo")
        os.makedirs(self.skill_dir)
        self.md = os.path.join(self.skill_dir, "SKILL.md")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, n_body_lines):
        body = "\n".join("line %d" % i for i in range(n_body_lines))
        with open(self.md, "w") as f:
            f.write("---\nname: demo\ndescription: Use when testing.\n---\n"
                    + body)

    def claim(self, text):
        item = scc.Item(None, 1, text, [1] * len(text))
        return scc.extract_claims(item)[0]

    def test_body_line_count_matches_skill_lint(self):
        self.write(37)
        self.assertEqual(scc.body_line_count(self.md), 37)
        with open(self.md) as f:
            _, body, _ = skill_lint.parse_frontmatter(f.read())
        self.assertEqual(len(body.split("\n")), 37)

    def test_a_correct_count_produces_no_finding(self):
        self.write(37)
        c = self.claim("`demo/SKILL.md` is still 37 body lines")
        self.assertEqual(scc.check_body_lines(c, self.tmp), [])

    def test_a_stale_count_is_s001(self):
        self.write(399)
        c = self.claim("`demo/SKILL.md` is still 415 body lines")
        found = scc.check_body_lines(c, self.tmp)
        self.assertEqual(codes(found), ["S001"])
        self.assertIn("it is 399", found[0].message)

    def test_a_code_that_no_longer_fires_is_s002(self):
        self.write(399)                      # under the 400-line B002 warning
        c = self.claim("`demo/SKILL.md` is still 399 body lines (B002)")
        found = scc.check_body_lines(c, self.tmp)
        self.assertEqual(codes(found), ["S002"])
        self.assertIn("skill_lint emits", found[0].message)

    def test_a_code_that_does_still_fire_produces_no_finding(self):
        self.write(415)
        c = self.claim("`demo/SKILL.md` is still 415 body lines (B002)")
        self.assertEqual(scc.check_body_lines(c, self.tmp), [])

    def test_both_wrong_reports_both(self):
        self.write(399)
        c = self.claim("`demo/SKILL.md` is still 415 body lines (B002)")
        self.assertEqual(codes(scc.check_body_lines(c, self.tmp)),
                         ["S001", "S002"])

    def test_an_unresolvable_path_is_skipped_not_reported(self):
        # Next-steps prose names files that do not exist yet ("if a
        # pyproject.toml ever appears at the repo root"). Flagging those is
        # how a checker earns being muted.
        c = self.claim("`ghost/SKILL.md` is still 415 body lines")
        self.assertEqual(scc.check_body_lines(c, self.tmp), [])
        self.assertFalse(c.checkable)
        self.assertIn("unresolved path", c.skip_reason)


class TestCheckCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "f.py"), "w") as f:
            f.write("alpha\nbeta\nalpha\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def claim(self, text):
        item = scc.Item(None, 1, text, [1] * len(text))
        c = scc.extract_claims(item)[0]
        c.item = scc.Item(scc.Block(1, 1, []), 1, text, [1] * len(text))
        c.item.block.path = "<mem>"
        return c

    def test_bare_integer_claim_matches(self):
        c = self.claim("`grep -c alpha f.py` -> 2")
        self.assertEqual(scc.check_command(c, self.tmp, 30), [])

    def test_bare_integer_claim_mismatch_is_s003(self):
        c = self.claim("`grep -c alpha f.py` -> 5")
        found = scc.check_command(c, self.tmp, 30)
        self.assertEqual(codes(found), ["S003"])
        self.assertIn("observed 2", found[0].message)

    def test_bare_integer_claim_with_no_integer_output_is_s003(self):
        c = self.claim("`cat f.py` -> 2")
        found = scc.check_command(c, self.tmp, 30)
        self.assertEqual(codes(found), ["S003"])
        self.assertIn("no bare integer", found[0].message)

    def test_named_metric_mismatch_is_s003(self):
        c = self.claim("`cat out.txt` -> **412 passed**")
        with open(os.path.join(self.tmp, "out.txt"), "w") as f:
            f.write("3 passed in 0.1s\n")
        found = scc.check_command(c, self.tmp, 30)
        self.assertEqual(codes(found), ["S003"])
        self.assertIn("claim says passed=412, observed passed=3",
                      found[0].message)

    def test_named_metric_absent_is_s003(self):
        c = self.claim("`cat f.py` -> **412 passed**")
        found = scc.check_command(c, self.tmp, 30)
        self.assertIn("printed no passed at all", found[0].message)

    def test_an_unquantified_claim_is_reported_not_silently_passed(self):
        c = self.claim("`cat f.py` -> the file, unchanged")
        found = scc.check_command(c, self.tmp, 30)
        self.assertEqual([f.level for f in found], ["UNQUANTIFIED"])
        self.assertEqual(codes(found), ["S004"])

    def test_exit_code_claims_are_compared(self):
        c = self.claim("`grep -c zzz f.py` -> exit 1")
        self.assertEqual(scc.check_command(c, self.tmp, 30), [])
        c = self.claim("`grep -c alpha f.py` -> exit 1")
        self.assertEqual(codes(scc.check_command(c, self.tmp, 30)), ["S003"])


class TestNothingRunsWithoutRun(unittest.TestCase):
    """The gate that keeps a static sweep static."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.doc = os.path.join(self.tmp, "state.md")
        self.marker = os.path.join(self.tmp, "MARKER")
        with open(self.doc, "w") as f:
            # `cat` is on the auto allowlist, so this claim IS checkable;
            # only the --run gate stops it executing.
            f.write(block(9, "1. `cat %s` -> 1" % self.marker))
        with open(self.marker, "w") as f:
            f.write("9\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_static_pass_does_not_execute_the_command(self):
        findings, report = scc.analyse(self.doc, self.tmp, run=False)
        self.assertEqual(findings, [])
        self.assertEqual(len(report["claims"]), 1)
        self.assertTrue(report["claims"][0].checkable)
        self.assertFalse(report["ran"])
        self.assertIn("need --run", scc.format_report(findings, report))

    def test_run_executes_it_and_finds_the_mismatch(self):
        findings, _ = scc.analyse(self.doc, self.tmp, run=True, timeout=30)
        self.assertEqual(codes(findings), ["S003"])


class TestClaimAges(unittest.TestCase):
    def test_a_verbatim_carry_is_counted_across_blocks(self):
        sentence = "`a/SKILL.md` is still 415 body lines (B002)"
        text = (block(340, "1. %s — carried" % sentence)
                + block(345, "1. %s — carried" % sentence)
                + block(349, "1. Standing: %s, 8th round" % sentence))
        blocks = scc.find_blocks(text)
        for b in blocks:
            b.path = "<mem>"
        live, _ = scc.live_block(blocks)
        ages = scc.claim_ages(live, blocks)
        (key,) = list(ages)
        self.assertEqual(sorted(ages[key]), [340, 345, 349])

    def test_a_claim_only_this_round_made_has_age_one(self):
        text = block(340, "1. nothing here") \
            + block(349, "1. `a/SKILL.md` is now at 399 body lines")
        blocks = scc.find_blocks(text)
        for b in blocks:
            b.path = "<mem>"
        live, _ = scc.live_block(blocks)
        ages = scc.claim_ages(live, blocks)
        self.assertEqual([sorted(v) for v in ages.values()], [[349]])

    def test_matching_is_exact_not_fuzzy(self):
        # A tool that aged claims by similarity would itself be asserting a
        # number nobody can re-derive. Different wording -> not the same claim.
        text = (block(340, "1. `a/SKILL.md` is now at 415 body lines")
                + block(349, "1. `a/SKILL.md` is still 415 body lines"))
        blocks = scc.find_blocks(text)
        for b in blocks:
            b.path = "<mem>"
        live, _ = scc.live_block(blocks)
        ages = scc.claim_ages(live, blocks)
        self.assertEqual([sorted(v) for v in ages.values()], [[349]])

    def test_whitespace_and_case_do_not_break_a_match(self):
        text = (block(340, "1. `A/SKILL.md`  is   still 415 body lines")
                + block(349, "1. `a/SKILL.md` is still 415 body lines"))
        blocks = scc.find_blocks(text)
        for b in blocks:
            b.path = "<mem>"
        live, _ = scc.live_block(blocks)
        ages = scc.claim_ages(live, blocks)
        self.assertEqual([sorted(v) for v in ages.values()], [[340, 349]])


ROUND_349_ITEM_9 = """\
9. Standing and unchanged: `fuzz-mutate-kill-loop/SKILL.md` is still 415 body
   lines (B002), 8th consecutive round carried; `harness/swe/regiontools.py`
   is still deliberately un-unified with `EditFileTool` (round 307's item 2);
   round 301's item 2 remains speculative; the `tail`/EOF backgrounded-pipe
   silent-drop mechanism remains genuinely unconfirmed (round 310's item 5);
   the heavy/light re-tally check-in is still pending its window; and
   NUC-integration(E)'s box-down items are unchanged since round 334."""

ROUND_346_ITEM_11 = """\
11. `fuzz-mutate-kill-loop/SKILL.md` is still 415 body lines (B002) —
    unchanged, 7th consecutive round it has been carried."""


class TestRound349Regression(unittest.TestCase):
    """The historical instance this tool was written for, pinned.

    Round 339 took `fuzz-mutate-kill-loop/SKILL.md` from 415 body lines to
    399 and said so in bold in its own research-state entry. The next-steps
    blocks of rounds 343, 346, 347, 348 and 349 re-asserted 415 anyway,
    because a next-steps block is written by copying the previous one.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "skills", "fuzz-mutate-kill-loop"))
        self.md = os.path.join(self.tmp, "skills", "fuzz-mutate-kill-loop",
                               "SKILL.md")
        with open(self.md, "w") as f:
            f.write("---\nname: fuzz-mutate-kill-loop\n"
                    "description: Use when fuzzing.\n---\n"
                    + "\n".join("l%d" % i for i in range(399)))
        self.doc = os.path.join(self.tmp, "research-state.md")
        with open(self.doc, "w") as f:
            f.write("## Next steps (as of round 346)\n" + ROUND_346_ITEM_11
                    + "\n\n## Next steps (as of round 349)\n"
                    + ROUND_349_ITEM_9 + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_stale_number_and_the_dead_code_are_both_caught(self):
        findings, report = scc.analyse(self.doc, self.tmp)
        self.assertEqual(report["live_round"], 349)
        self.assertEqual(sorted(codes(findings)), ["S001", "S002"])
        self.assertIn("is 415 body lines; it is 399",
                      [f.message for f in findings if f.code == "S001"][0])

    def test_the_claim_spans_a_line_break_and_is_still_found(self):
        # "…is still 415 body\n   lines (B002)…" — the number and its unit
        # are on different source lines. Without unwrapping, zero findings.
        findings, _ = scc.analyse(self.doc, self.tmp)
        self.assertTrue(findings)

    def test_the_carry_is_visible_as_an_age(self):
        # Round 353 widened the grammar to cross-block citations, so this
        # fixture's item 9 now yields aged CITATION claims too. Select the
        # body-lines claim by key rather than assuming it is the only one.
        _, report = scc.analyse(self.doc, self.tmp)
        body = [c for c in report["claims"] if c.kind == "body-lines"]
        self.assertEqual(len(body), 1)
        self.assertEqual(sorted(report["ages"][body[0].key()]), [346, 349])

    def test_exit_code_is_one(self):
        rc = scc.main(["--repo-root", self.tmp, self.doc])
        self.assertEqual(rc, 1)

    def test_block_selects_a_historical_block_for_regression_use(self):
        findings, report = scc.analyse(self.doc, self.tmp, block_round=346)
        self.assertEqual(report["live_round"], 346)
        self.assertEqual(sorted(codes(findings)), ["S001", "S002"])


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.doc = os.path.join(self.tmp, "state.md")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, text):
        with open(self.doc, "w") as f:
            f.write(text)

    def test_clean_document_exits_zero(self):
        self.write(block(9, "1. nothing checkable here"))
        self.assertEqual(scc.main(["--repo-root", self.tmp, self.doc]), 0)

    def test_missing_file_exits_two(self):
        self.assertEqual(scc.main(["--repo-root", self.tmp,
                                   os.path.join(self.tmp, "nope.md")]), 2)

    def test_document_without_a_next_steps_block_exits_two(self):
        self.write("# Just a document\n")
        self.assertEqual(scc.main(["--repo-root", self.tmp, self.doc]), 2)

    def test_unknown_block_round_exits_two(self):
        self.write(block(9, "1. a"))
        self.assertEqual(scc.main(["--repo-root", self.tmp, "--block", "99",
                                   self.doc]), 2)

    def test_a_tie_exits_two_rather_than_guessing(self):
        self.write(block(9, "1. a") + block(9, "1. b"))
        self.assertEqual(scc.main(["--repo-root", self.tmp, self.doc]), 2)


class TestCoverageReport(unittest.TestCase):
    """The recall gap has to be printed, not implied.

    Round 339's rule, applied to its own successor: a checker nobody watches
    must have a zero false-positive rate even at the cost of recall, and must
    report the recall it gave up.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.doc = os.path.join(self.tmp, "state.md")
        with open(self.doc, "w") as f:
            f.write(block(9,
                          "1. plain prose, no claim at all",
                          "2. `ssh box uptime` -> up 3 days",
                          "3. `ghost/SKILL.md` is still 5 body lines",
                          "4. more prose"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_items_claims_and_skips_are_all_counted(self):
        findings, report = scc.analyse(self.doc, self.tmp)
        text = scc.format_report(findings, report)
        self.assertEqual(report["n_items"], 4)
        self.assertEqual(report["n_items_with_claims"], 2)
        self.assertIn("4 item(s), 2 with a checkable claim", text)
        self.assertIn("2 claim(s): 0 re-derivable, 2 skipped", text)
        self.assertIn("network 1", text)
        self.assertIn("unresolved path 1", text)
        self.assertIn("0 stale", text)


class TestCitationGrammar(unittest.TestCase):
    """S004 -- `Round N's item K` must point at an item that exists."""

    def test_singular_and_plural_and_ranges_all_extract(self):
        cases = {"Round 336's item 2": [2],
                 "round 349's items 2-6": [2, 3, 4, 5, 6],
                 "Round 350's items 1-3": [1, 2, 3],
                 "Round 301's item 2 remains speculative": [2]}
        for text, want in cases.items():
            item = scc.parse_items(scc.Block(1, 1, ["1. " + text]))[0]
            cites = [c for c in scc.extract_claims(item) if c.kind == "citation"]
            self.assertEqual(len(cites), 1, text)
            self.assertEqual(cites[0].payload["items"], want, text)

    def test_a_resolvable_citation_is_not_a_finding(self):
        blocks = scc.find_blocks(block(10, "1. a", "2. b") + "\n" +
                                 block(11, "1. Round 10's item 2 is unchanged"))
        for b in blocks:
            b.path = "x.md"
        live = [b for b in blocks if b.round_no == 11][0]
        item = scc.parse_items(live)[0]
        c = [x for x in scc.extract_claims(item) if x.kind == "citation"][0]
        self.assertEqual(scc.check_citation(c, blocks, REPO_ROOT), [])

    def test_citing_an_item_number_the_cited_block_does_not_have(self):
        blocks = scc.find_blocks(block(10, "1. a", "2. b") + "\n" +
                                 block(11, "1. Round 10's items 1-4 are unchanged"))
        for b in blocks:
            b.path = "x.md"
        live = [b for b in blocks if b.round_no == 11][0]
        item = scc.parse_items(live)[0]
        c = [x for x in scc.extract_claims(item) if x.kind == "citation"][0]
        f = scc.check_citation(c, blocks, REPO_ROOT)
        self.assertEqual(codes(f), ["S004"])
        self.assertIn("item(s) 3, 4", f[0].message)

    def test_citing_a_round_with_no_block_and_no_knowledge_next_steps(self):
        # Round 8891 is INSIDE the fixture's window (8890-8892) and has no
        # block: the pointer lands nowhere and that is a finding.
        blocks = scc.find_blocks(block(8890, "1. a") + "\n" +
                                 block(8892, "1. Round 8891's item 1 is unchanged"))
        for b in blocks:
            b.path = "x.md"
        live = [b for b in blocks if b.round_no == 8892][0]
        item = scc.parse_items(live)[0]
        c = [x for x in scc.extract_claims(item) if x.kind == "citation"][0]
        f = scc.check_citation(c, blocks, REPO_ROOT)
        self.assertEqual(codes(f), ["S004"])
        self.assertIn("resolves to nothing", f[0].message)

    def test_a_citation_outside_the_documents_own_window_is_not_checked(self):
        """Zero false positives on a FRAGMENT.

        Every test fixture and every `--block` slice is a fragment of the
        real document. A fragment covering rounds 346-349 cannot be expected
        to contain round 301's list, so an unresolvable citation of round 301
        says something about the fragment, not about the claim.
        """
        blocks = scc.find_blocks(block(8890, "1. Round 12's item 1 is unchanged"))
        for b in blocks:
            b.path = "x.md"
        item = scc.parse_items(blocks[0])[0]
        c = [x for x in scc.extract_claims(item) if x.kind == "citation"][0]
        self.assertEqual(scc.check_citation(c, blocks, REPO_ROOT), [])

    def test_a_knowledge_file_next_steps_section_resolves_the_citation(self):
        """Round 336's items live in its knowledge file, not in a block here.

        The second lookup source exists precisely because a round that dies
        at max-turns often writes a knowledge file and no block. Without it
        every citation of such a round would be a false positive.
        """
        nums, src = scc.knowledge_items(336, REPO_ROOT)
        self.assertIsNotNone(src)
        self.assertTrue({1, 2, 3}.issubset(nums), nums)

    def test_a_NUMBERED_next_steps_heading_resolves_too(self):
        """Round 375. `## 10. Next steps` is the heading in 12 of the
        corpus's knowledge files against 17 bare ones, and the original
        pattern matched only the bare form -- so a citation of round 374's
        item 1 was reported STALE while the item was right there. Widening
        can only turn STALE into resolved, never the reverse."""
        nums, src = scc.knowledge_items(374, REPO_ROOT)
        self.assertIsNotNone(src, "`## 10. Next steps` did not resolve")
        self.assertIn(1, nums, nums)

    def test_the_numbered_form_is_actually_present_in_the_corpus(self):
        """Guards the test above against passing on a renamed heading."""
        import glob
        numbered = [p for p in glob.glob(
            os.path.join(REPO_ROOT, "knowledge", "round-*.md"))
            if re.search(r"^#{2,3}\s+\d+\.\s+Next steps\b",
                         open(p, encoding="utf-8").read(), re.M)]
        self.assertGreaterEqual(len(numbered), 10, numbered)


class TestRound352Regression(unittest.TestCase):
    """Round 352's item 6, verbatim, pinned as a fixture.

    Round 336 wrote three next-steps items. Round 337 closed items 1 and 2
    (`21f4677` added both `_typed_tail_chain` and `oracle_tail_transparency`).
    Rounds 338-346 carried them as open anyway; round 347 caught that and
    told the next writer to re-check a carried item against git. Round 352
    carried it a sixth time and renumbered it to `Round 350's items 1-3` --
    and round 350 has neither a next-steps block here nor a `## Next steps`
    section in its knowledge file, so the pointer lands nowhere.

    Round 353 corrected the live document, which is exactly why the text is
    kept here: otherwise the only evidence that this check works would be a
    sentence in a knowledge file.
    """

    TEXT = ("6. Round 350's items 1-3 (the tail-vs-lifted oracle, the "
            "sixth-oracle\n   transform, the guest-TCO design question) are "
            "unchanged -- SWE-loop(D) and\n   harness(A) own them; the "
            "rotation has not reached those tracks since.")

    def test_the_renumbered_citation_is_caught(self):
        tmp = tempfile.mkdtemp(prefix="scc-352-")
        try:
            doc = os.path.join(tmp, "research-state.md")
            with open(doc, "w", encoding="utf-8") as f:
                # Two blocks so round 350 is inside the document's own
                # window -- the real file carries 58 of them, spanning
                # rounds 273-352.
                f.write(block(349, "1. an item nobody cites") + "\n" +
                        block(352, self.TEXT))
            findings, _ = scc.analyse(doc, REPO_ROOT)
            self.assertEqual(codes(findings), ["S004"])
            self.assertIn("round 350 has no next-steps block", findings[0].message)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestLiveCorpus(unittest.TestCase):
    """The real document. This is the test that fails in a future round if
    the live next-steps block starts asserting something untrue again."""

    DOC = os.path.join(REPO_ROOT, "state", "research-state.md")

    @unittest.skipUnless(os.path.isfile(DOC), "research-state.md absent")
    def test_live_block_has_no_stale_claims(self):
        findings, report = scc.analyse(self.DOC, REPO_ROOT, run=False)
        stale = [str(f) for f in findings if f.level == "STALE"]
        self.assertEqual(stale, [], "\n".join(stale))

    @unittest.skipUnless(os.path.isfile(DOC), "research-state.md absent")
    def test_the_live_block_is_the_highest_round_present(self):
        blocks = scc.find_blocks(open(self.DOC, encoding="utf-8").read())
        _, report = scc.analyse(self.DOC, REPO_ROOT)
        self.assertEqual(report["live_round"],
                         max(b.round_no for b in blocks))

    @unittest.skipUnless(os.path.isfile(DOC), "research-state.md absent")
    def test_no_live_corpus_block_loses_content_to_the_level_3_stop(self):
        # `find_blocks` ends a block at the first heading of level <= 3, so a
        # next-steps block containing its own `### sub-heading` would be
        # silently truncated and everything after it never checked. Zero such
        # blocks exist in this corpus; this asserts it rather than assuming
        # it. Every gap between a block's last line and the next block's
        # heading must start with a heading — i.e. nothing was dropped.
        text = open(self.DOC, encoding="utf-8").read()
        lines = text.split("\n")
        blocks = scc.find_blocks(text)
        starts = [b.first_line for b in blocks]
        for idx, b in enumerate(blocks):
            end = b.first_line + len(b.lines)
            nxt = starts[idx + 1] - 1 if idx + 1 < len(blocks) else len(lines)
            leftover = [g for g in lines[end:nxt] if g.strip()]
            if leftover:
                self.assertTrue(leftover[0].startswith("#"),
                                "block for round %d drops %r"
                                % (b.round_no, leftover[0]))

    @unittest.skipUnless(os.path.isfile(DOC), "research-state.md absent")
    def test_no_command_claim_in_the_live_block_would_cost_money(self):
        # Belt and braces on `classify`: assert directly that nothing marked
        # checkable in the live document is priced or networked.
        _, report = scc.analyse(self.DOC, REPO_ROOT)
        for c in report["claims"]:
            if c.kind == "command" and c.checkable:
                kind, reason = __import__("claim_check").classify(
                    c.payload["cmd"])
                self.assertEqual(kind, "auto", c.payload["cmd"])


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------


class TestS006RetiredItems(unittest.TestCase):
    """S004 asks whether an item pointer RESOLVES; S006 asks whether the
    thing it points at is still OPEN. Round 390 added it after finding
    round 332's item 1 -- discharged by round 350, correctly dropped from
    every block for 23 rounds, then RESURRECTED at round 375 and carried by
    nine language-facing blocks since."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "state"))
        self.addCleanup(shutil.rmtree, self.root)

    def _registry(self, entries):
        import json
        with open(os.path.join(self.root, scc.RETIRED_REGISTRY), "w") as f:
            json.dump({"retired": entries}, f)

    def _claim(self, text):
        item = scc.parse_items(scc.Block(1, 1, ["1. " + text]))[0]
        return [c for c in scc.extract_claims(item) if c.kind == "citation"][0]

    ENTRY = {"round": 332, "item": 1, "summary": "the lexer history sweep",
             "retired_by": 350, "evidence": "tests/test_lexer_guest_parity.py"}

    def test_a_retired_item_reasserted_as_open_is_a_finding(self):
        self._registry([self.ENTRY])
        f = scc.check_retired(self._claim("Round 332's item 1 is unchanged"),
                              self.root)
        self.assertEqual(codes(f), ["S006"])
        self.assertIn("DISCHARGED by round 350", f[0].message)
        self.assertIn("test_lexer_guest_parity.py", f[0].message)

    def test_acknowledging_the_closure_is_the_cure_not_the_disease(self):
        """Round 389's own block says "Round 383's item 5 is CLOSED and must
        not be carried again". Firing on that sentence would make the
        checker punish the only thing that fixes the problem."""
        self._registry([self.ENTRY])
        for text in ("Round 332's item 1 is CLOSED by round 350",
                     "Round 332's item 1 -- retired, do not carry",
                     "Round 332's item 1 was discharged and must not be "
                     "carried again"):
            self.assertEqual(scc.check_retired(self._claim(text), self.root),
                             [], text)

    def test_an_item_not_in_the_registry_is_never_a_finding(self):
        self._registry([self.ENTRY])
        self.assertEqual(
            scc.check_retired(self._claim("Round 332's item 2 is unchanged"),
                              self.root), [])
        self.assertEqual(
            scc.check_retired(self._claim("Round 301's item 2 is unchanged"),
                              self.root), [])

    def test_a_multi_item_citation_reports_only_the_retired_ones(self):
        self._registry([self.ENTRY,
                        dict(self.ENTRY, item=3, summary="another")])
        f = scc.check_retired(self._claim("Round 332's items 1-4 are unchanged"),
                              self.root)
        self.assertEqual(codes(f), ["S006", "S006"])
        self.assertIn("item 1", f[0].message)
        self.assertIn("item 3", f[1].message)

    def test_a_missing_or_broken_registry_checks_nothing(self):
        """Absent must degrade to "check nothing", never to "everything is
        retired" -- most checkouts of this document predate the file."""
        c = self._claim("Round 332's item 1 is unchanged")
        self.assertEqual(scc.check_retired(c, self.root), [])
        with open(os.path.join(self.root, scc.RETIRED_REGISTRY), "w") as f:
            f.write("{not json")
        self.assertEqual(scc.check_retired(c, self.root), [])


class TestTheRealRegistry(unittest.TestCase):
    """The registry is a set of CLAIMS and is held to this program's own
    standard: each names a round, a discharging round and evidence a reader
    can open."""

    PATH = os.path.join(REPO_ROOT, scc.RETIRED_REGISTRY)

    @unittest.skipUnless(os.path.isfile(PATH), "registry absent")
    def test_every_entry_is_complete_and_its_evidence_path_exists(self):
        entries = scc.retired_items(REPO_ROOT)
        self.assertTrue(entries)
        for (rnd, item), e in entries.items():
            for field in ("round", "item", "summary", "retired_by",
                          "evidence", "recorded_by"):
                self.assertIn(field, e, (rnd, item))
            self.assertGreater(e["retired_by"], e["round"], (rnd, item))
            # the evidence must name at least one path that is really there
            paths = re.findall(r"[\w./-]+\.(?:py|json|md|lang|sh)", e["evidence"])
            self.assertTrue(paths, (rnd, item, e["evidence"]))
            self.assertTrue(
                any(os.path.exists(os.path.join(REPO_ROOT, p)) for p in paths),
                (rnd, item, paths))


# --------------------------------------------------------------------------
# S007 / S008 — the carry ordinal (round 399)
# --------------------------------------------------------------------------

B002 = "`fuzz-mutate-kill-loop/SKILL.md` is still 415 body lines (B002)"


def one_claim(text, round_no=400):
    """The first extracted claim of a one-item block."""
    blk = scc.find_blocks(block(round_no, "1. " + text))[0]
    blk.path = "<test>"
    item = scc.parse_items(blk)[0]
    return scc.extract_claims(item)[0]


class TestOrdinalGrammar(unittest.TestCase):
    def test_digits_and_words_both_parse(self):
        c = one_claim(B002 + " — 8th consecutive round.")
        self.assertEqual(scc.ordinal_for(c.item.text, c.key()), (8, ("round",)))
        c = one_claim(B002 + " — TWELFTH consecutive round.")
        self.assertEqual(scc.ordinal_for(c.item.text, c.key()),
                         (12, ("round",)))

    def test_no_ordinal_is_none_not_zero(self):
        # Round 343's real item asserts the claim with no counter at all.
        c = one_claim(B002 + " — unchanged, the only thing in the way.")
        self.assertIsNone(scc.ordinal_for(c.item.text, c.key()))

    def test_an_ordinal_before_the_claim_is_not_attached_to_it(self):
        c = one_claim("Deferred a 4th consecutive round: " + B002 + ".")
        self.assertIsNone(scc.ordinal_for(c.item.text, c.key()))

    def test_an_ordinal_behind_a_second_md_claim_is_not_stolen(self):
        # Round 349's real item 9 shape: two subjects, one sentence. Without
        # the `.md` barrier the first claim would take the second's counter.
        c = one_claim(B002 + "; `harness/swe/regiontools.py` is still "
                      "un-unified, 9th consecutive round.")
        self.assertIsNone(scc.ordinal_for(c.item.text, c.key()))

    def test_the_ordinal_between_the_claim_and_the_next_md_is_attached(self):
        # Also round 349's real shape, in the order it was actually written.
        c = one_claim(B002 + ", 8th consecutive round carried; "
                      "`harness/swe/regiontools.py` is still un-unified.")
        self.assertEqual(scc.ordinal_for(c.item.text, c.key()), (8, ("round",)))

    def test_decoration_does_not_change_the_unit(self):
        # The three real spellings of "rounds" in this corpus.
        for tail in ("round.", "round carried.", "round it has been carried."):
            c = one_claim(B002 + " — unchanged, 8th consecutive " + tail)
            self.assertEqual(scc.ordinal_for(c.item.text, c.key())[1],
                             ("round",), tail)

    def test_a_qualified_denominator_is_a_different_unit(self):
        c = one_claim(B002 + " — 7th consecutive skills(B) round.")
        self.assertEqual(scc.ordinal_for(c.item.text, c.key())[1],
                         ("skills(b)", "round"))


class TestOrdinalHistory(unittest.TestCase):
    def test_history_is_sorted_by_declared_round_not_file_position(self):
        # Load-bearing. In the real research-state.md 51 of 92 adjacent block
        # pairs are out of chronological order and the physically LAST block
        # is 65 rounds behind the live one, so file order would compare a
        # counter against a revision written long after it.
        text = (block(349, "1. " + B002 + " — 8th consecutive round.") +
                "\n" +
                block(334, "1. " + B002 + " — 6th consecutive round.") +
                "\n" +
                block(338, "1. " + B002 + " — 8th consecutive round."))
        hist = scc.ordinal_history(scc.normalise(B002),
                                   scc.find_blocks(text))
        self.assertEqual([r for r, _ in hist], [334, 338, 349])

    def test_a_block_with_no_ordinal_is_kept_as_a_hole(self):
        text = (block(334, "1. " + B002 + " — 6th consecutive round.") +
                "\n" + block(343, "1. " + B002 + " — unchanged."))
        hist = scc.ordinal_history(scc.normalise(B002), scc.find_blocks(text))
        self.assertEqual([o for _, o in hist], [(6, ("round",)), None])


class TestCheckOrdinal(unittest.TestCase):
    def _findings(self, live_round, live_tail, *older):
        parts = [block(r, "1. " + B002 + " — " + t) for r, t in older]
        parts.append(block(live_round, "1. " + B002 + " — " + live_tail))
        text = "\n".join(parts)
        blocks = scc.find_blocks(text)
        for b in blocks:
            b.path = "<test>"
        live = [b for b in blocks if b.round_no == live_round][0]
        claim = scc.extract_claims(scc.parse_items(live)[0])[0]
        return scc.check_ordinal(claim, blocks)

    def test_an_advancing_counter_is_silent(self):
        self.assertEqual(
            self._findings(398, "9th consecutive round.",
                           (349, "8th consecutive round.")), [])

    def test_a_repeated_counter_is_S007(self):
        # The live instance: round 398 re-asserted round 349's `8th`.
        f = self._findings(398, "8th consecutive round carried.",
                           (349, "8th consecutive round carried."))
        self.assertEqual(codes(f), ["S007"])
        self.assertEqual(f[0].level, "STALE")
        self.assertIn("round 349's 8", f[0].message)

    def test_a_decreasing_counter_is_S007(self):
        f = self._findings(349, "8th consecutive round.",
                           (348, "9th consecutive round."))
        self.assertEqual(codes(f), ["S007"])

    def test_the_message_carries_the_whole_sequence(self):
        f = self._findings(398, "8th consecutive round.",
                           (333, "6th consecutive round."),
                           (343, "unchanged."),
                           (349, "8th consecutive round."))
        self.assertIn("333:6 round, 343:-, 349:8 round, 398:8 round",
                      f[0].message)

    def test_a_changed_unit_is_S008_and_only_a_warning(self):
        # Round 346's real shape: 8 rounds -> 7 skills(B) rounds. The count
        # went backwards, but the denominator moved with it, so the document
        # is ambiguous rather than provably stale. Reported, never an error.
        f = self._findings(346, "7th consecutive skills(B) round.",
                           (338, "8th consecutive round carried."))
        self.assertEqual(codes(f), ["S008"])
        self.assertEqual(f[0].level, "WARN")

    def test_the_first_assertion_of_a_claim_is_silent(self):
        self.assertEqual(self._findings(398, "1st consecutive round."), [])

    def test_a_prior_block_with_no_ordinal_is_skipped_not_compared(self):
        # Round 343 asserts the claim with no counter; the comparison must
        # reach past it to round 338 rather than treat the hole as zero.
        f = self._findings(346, "7th consecutive round.",
                           (338, "8th consecutive round."),
                           (343, "unchanged."))
        self.assertEqual(codes(f), ["S007"])
        self.assertIn("round 338's 8", f[0].message)

    def test_an_item_with_no_ordinal_at_all_is_silent(self):
        self.assertEqual(
            self._findings(398, "unchanged.",
                           (349, "8th consecutive round.")), [])


class TestRound398OrdinalRegression(unittest.TestCase):
    """Round 398's real text, verbatim, pinned as a fixture.

    Round 399 rewrote the live block, so the tool exits 0 against the current
    `state/research-state.md` — which would quietly delete the evidence that
    S007 works. Same reason `TestRound349Regression` above exists.
    """

    LIVE_398 = (
        "10. `fuzz-mutate-kill-loop/SKILL.md` is still 415 body lines (B002) "
        "and is\n    still the only thing between the corpus and a "
        "warning-free `--house\n    --strict` sweep — 8th consecutive round "
        "carried.")
    R349 = (
        "9. Standing and unchanged: `fuzz-mutate-kill-loop/SKILL.md` is still "
        "415 body lines (B002), 8th consecutive round carried; "
        "`harness/swe/regiontools.py`'s region-patch mechanism is still "
        "deliberately un-unified with `EditFileTool`.")

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.doc = os.path.join(self.tmp, "research-state.md")
        with open(self.doc, "w") as f:
            f.write(block(349, self.R349) + "\n" +
                    block(398, self.LIVE_398))
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_round_398s_counter_is_caught(self):
        findings, _ = scc.analyse(self.doc, REPO_ROOT, run=False)
        s7 = [f for f in findings if f.code == "S007"]
        self.assertEqual(len(s7), 1, [str(f) for f in findings])
        self.assertIn("not above round 349's 8", s7[0].message)

    def test_the_body_line_count_is_caught_in_the_same_pass(self):
        # Both halves of round 398's item 10 were false. S001 catches the
        # number; S007 catches the claim that nobody had needed to re-check
        # it for eight consecutive rounds.
        findings, _ = scc.analyse(self.doc, REPO_ROOT, run=False)
        self.assertEqual(sorted({f.code for f in findings}),
                         ["S001", "S002", "S007"])


class TestLiveCorpusOrdinals(unittest.TestCase):
    DOC = os.path.join(REPO_ROOT, "state", "research-state.md")

    @unittest.skipUnless(os.path.isfile(DOC), "research-state.md absent")
    def test_the_live_block_has_no_ordinal_findings(self):
        findings, _ = scc.analyse(self.DOC, REPO_ROOT, run=False)
        bad = [str(f) for f in findings if f.code in ("S007", "S008")]
        self.assertEqual(bad, [], "\n".join(bad))

    @unittest.skipUnless(os.path.isfile(DOC), "research-state.md absent")
    def test_every_historical_block_is_swept_and_the_verdicts_are_stable(self):
        # Round 399 measured the whole document: 3 blocks of 93 would be
        # ERROR-red on S007 (334, 349, 398) and 2 more WARN on S008 (318,
        # 346). Pinned as SETS of round numbers, not as counts, so a future
        # block that trips the rule names itself instead of moving a total.
        with open(self.DOC, encoding="utf-8") as f:
            blocks = scc.find_blocks(f.read())
        s7, s8 = set(), set()
        for b in blocks:
            findings, _ = scc.analyse(self.DOC, REPO_ROOT, run=False,
                                      block_round=b.round_no)
            for x in findings:
                if x.code == "S007":
                    s7.add(b.round_no)
                elif x.code == "S008":
                    s8.add(b.round_no)
        # Round 417 added 412 and NOTHING else. Two changes were needed to
        # see it and neither alone was enough — measured by ablation:
        #   widened ORDINAL_RE, verbatim key   -> [334, 349, 398]
        #   subject anchor, narrow ORDINAL_RE  -> [334, 349, 398]
        #   both                               -> [334, 349, 398, 412]
        # The S008 set did not move, which is the check that the widening
        # did not start reading unit changes into a vocabulary difference.
        self.assertEqual(sorted(s7), [334, 349, 398, 412], "S007 set moved")
        self.assertEqual(sorted(s8), [318, 346], "S008 set moved")


# --------------------------------------------------------------------------
# Round 417 — S009/S010, the REFERENCE-count claim.
#
# The instance: rounds 412 and 414 both asserted "`nuc/run_checks_fast.sh`
# still has 0 references in `run_driver.sh`" in their LIVE blocks, three and
# five rounds after round 409 wired it. `state_claim_check` reported both
# blocks `0 stale`, because no class extracted the claim — while S007 checked
# the carry ordinal sitting in the same sentence, and passed it.
# --------------------------------------------------------------------------

REF414 = ("`nuc/run_checks_fast.sh` still has 0 references in "
          "`run_driver.sh` — SIXTH round carried.")
LIVE_DOC = os.path.join(REPO_ROOT, "state", "research-state.md")


def claims_of(text, round_no=400):
    blk = scc.find_blocks(block(round_no, "1. " + text))[0]
    blk.path = "<test>"
    return scc.extract_claims(scc.parse_items(blk)[0])


class TestReferenceGrammar(unittest.TestCase):
    """Extraction only — no tree is read by any test in this class."""

    def test_scoped_claim_extracts_target_container_and_count(self):
        c = one_claim(REF414)
        self.assertEqual(c.kind, "reference")
        self.assertEqual(c.payload["target"], "nuc/run_checks_fast.sh")
        self.assertEqual(c.payload["container"], "run_driver.sh")
        self.assertEqual(c.payload["n"], 0)
        self.assertTrue(c.checkable)

    def test_zero_and_no_are_read_as_the_number_zero(self):
        for word in ("zero", "no", "0"):
            c = one_claim("`a/b.py` has %s references in `c.sh`" % word)
            self.assertEqual(c.payload["n"], 0, word)

    def test_a_nonzero_count_parses_too(self):
        # The class is not "assertions of zero". A claim of 4 is exactly as
        # checkable, and exactly as able to rot.
        c = one_claim("`a/b.py` has 4 references in `c.sh`")
        self.assertEqual(c.payload["n"], 4)

    def test_a_path_wrapped_across_a_line_break_still_matches(self):
        # Round 415's item 1, verbatim shape. research-state.md wraps prose
        # at ~76 columns and will break a path inside its own backticks. The
        # other three grammars in this file use a whitespace-free path group
        # and cannot see this claim at all.
        c = one_claim("`languages/whence/nuc_scripting/\n   ncs_engine.py` "
                      "(zero references of any kind; round 172 said so)")
        self.assertEqual(c.payload["target"],
                         "languages/whence/nuc_scripting/ncs_engine.py")

    def test_a_claim_with_no_container_is_extracted_but_not_checkable(self):
        # "zero references of any kind" names no container, and `refs` counts
        # references INSIDE one. Recorded as a skip rather than dropped: the
        # skip is what puts it in the published coverage denominator.
        c = one_claim("`x/y.py` has zero references of any kind")
        self.assertFalse(c.checkable)
        self.assertIn("reference scope", c.skip_reason)
        self.assertIsNone(c.payload["container"])

    def test_the_wiring_shape_puts_the_subject_before_the_container(self):
        # Rounds 400/406/407/408 wrote this same claim the other way round,
        # and the path NEAREST the number is the container, not the subject.
        c = one_claim("harness(A) still owns wiring `nuc/run_checks_fast.sh` "
                      "into `run_driver.sh` — 0 references, FOURTH round "
                      "carried.")
        self.assertEqual(c.payload["target"], "nuc/run_checks_fast.sh")
        self.assertEqual(c.payload["container"], "run_driver.sh")
        self.assertTrue(c.checkable)

    def test_a_sentence_break_between_path_and_count_does_not_pair_them(self):
        # `a/b.py` is the only backticked path BEFORE the count, and a
        # sentence ends between them. The grammar declines rather than
        # pairing them — the fail-closed direction, since a wrong subject
        # produces a confident wrong verdict where a skip only costs recall
        # (and the skip is counted in the published coverage).
        got = [c.payload["target"] for c in
               claims_of("`a/b.py` is fine. Something else entirely has "
                         "0 references in `c.sh`")
               if c.kind == "reference"]
        self.assertEqual(got, [])

    def test_without_the_sentence_break_the_same_words_do_pair(self):
        # The control for the test above: the ONLY difference is the `.`, so
        # the refusal above is the sentence rule and not the grammar failing
        # to see the shape at all.
        got = [c.payload["target"] for c in
               claims_of("`a/b.py` is fine and has 0 references in `c.sh`")
               if c.kind == "reference"]
        self.assertEqual(got, ["a/b.py"])

    def test_a_one_character_filename_stem_still_matches(self):
        # Found by a test, not by review: the target group was written
        # `[^`]{2,160}?\.(?:py|sh|...)`, so a path whose stem is ONE
        # character (`c.sh`, `x.py`) could never match — the group's own
        # minimum ate the stem. Every real path in the corpus has a longer
        # stem, so the live sweep looked perfect while the grammar had a
        # silent floor on filename length.
        for path in ("c.sh", "x.py", "a/b.py"):
            c = one_claim("`%s` has 0 references in `d.py`" % path)
            self.assertEqual(c.payload["target"], path, path)

    def test_prose_about_references_naming_no_file_extracts_nothing(self):
        self.assertEqual(
            [c.kind for c in claims_of("this item has 0 references to speak "
                                       "of and names no file")], [])


def git_repo():
    """A real git checkout — `refs` reads the tree through `git ls-files`."""
    tmp = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
    return tmp


def git_add(tmp, rel, text):
    p = os.path.join(tmp, rel)
    if os.path.dirname(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    subprocess.run(["git", "add", rel], cwd=tmp, check=True)


@unittest.skipUnless(shutil.which("git"), "git absent")
class TestCheckReference(unittest.TestCase):
    """The three-valued verdict, against a real tracked tree.

    `driver.sh` names `nuc/tool.sh` on two lines: one comment, one command.
    That is round 415's real geometry — `run_driver.sh:496` is the comment
    explaining the wiring and `:526` is the wiring — reduced to the smallest
    tree that reproduces it.
    """

    def setUp(self):
        self.tmp = git_repo()
        git_add(self.tmp, "nuc/tool.sh", "echo hi\n")
        git_add(self.tmp, "driver.sh",
                "# the wiring for nuc/tool.sh is explained here\n"
                "bash nuc/tool.sh\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check(self, text):
        c = one_claim(text)
        return scc.check_reference(c, self.tmp), c

    def test_a_count_matching_both_numbers_is_clean(self):
        git_add(self.tmp, "solo.sh", "bash nuc/tool.sh\n")
        f, c = self.check("`nuc/tool.sh` has 1 reference in `solo.sh`")
        self.assertEqual(f, [])
        self.assertTrue(c.checkable)

    def test_a_count_matching_neither_number_is_S009_stale(self):
        f, _ = self.check("`nuc/tool.sh` still has 0 references in `driver.sh`")
        self.assertEqual(codes(f), ["S009"])
        self.assertEqual(f[0].level, "STALE")
        self.assertIn("2 mention(s)", f[0].message)
        self.assertIn("1 invocation(s)", f[0].message)

    def test_a_count_matching_only_the_invocation_number_is_S010_warn(self):
        f, _ = self.check("`nuc/tool.sh` has 1 reference in `driver.sh`")
        self.assertEqual(codes(f), ["S010"])
        self.assertEqual(f[0].level, "WARN")
        self.assertIn("invocation count", f[0].message)
        self.assertIn("mention count is 2", f[0].message)

    def test_a_count_matching_only_the_mention_number_is_S010_warn(self):
        f, _ = self.check("`nuc/tool.sh` has 2 references in `driver.sh`")
        self.assertEqual(codes(f), ["S010"])
        self.assertIn("mention count", f[0].message)
        self.assertIn("invocation count is 1", f[0].message)

    def test_every_finding_carries_the_command_that_re_derives_it(self):
        # Round 415's closing rule turned into output: an item asserting a
        # reference count should be written with its re-derivation beside it.
        for text in ("`nuc/tool.sh` still has 0 references in `driver.sh`",
                     "`nuc/tool.sh` has 1 reference in `driver.sh`"):
            f, _ = self.check(text)
            self.assertIn("wiring_audit.py refs nuc/tool.sh --in driver.sh",
                          f[0].message, text)

    def test_an_ambiguous_basename_is_S010_and_never_a_verdict(self):
        git_add(self.tmp, "skills/tool.sh", "echo other\n")
        f, _ = self.check("`tool.sh` has 0 references in `driver.sh`")
        self.assertEqual(codes(f), ["S010"])
        self.assertIn("not one file", f[0].message)
        self.assertIn("nuc/tool.sh", f[0].message)

    def test_an_unresolved_target_is_skipped_rather_than_flagged(self):
        # Next-steps prose names files that do not exist yet on purpose.
        f, c = self.check("`does/not/exist.py` has 0 references in `driver.sh`")
        self.assertEqual(f, [])
        self.assertFalse(c.checkable)
        self.assertIn("unresolved target", c.skip_reason)

    def test_an_unreadable_container_is_skipped_rather_than_flagged(self):
        f, c = self.check("`nuc/tool.sh` has 0 references in `nope.sh`")
        self.assertEqual(f, [])
        self.assertFalse(c.checkable)


class TestCheckReferenceDegradesSafely(unittest.TestCase):
    """Both ways of not having the instrument end in `skipped`, not a crash.

    A checker that raised here would take a whole document down over one
    claim class; one that returned `[]` quietly would report `0 stale` for a
    claim it never looked at — which is the failure this class exists to end.
    """

    def test_a_tree_that_is_not_a_git_checkout_is_skipped(self):
        tmp = tempfile.mkdtemp()
        try:
            c = one_claim("`a/b.py` has 0 references in `c.sh`")
            self.assertEqual(scc.check_reference(c, tmp), [])
            self.assertFalse(c.checkable)
            self.assertIn("could not read the tree", c.skip_reason)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_checkout_with_no_harness_is_skipped(self):
        tmp = tempfile.mkdtemp()
        saved = scc.wiring_audit
        scc.wiring_audit = None
        try:
            c = one_claim("`a/b.py` has 0 references in `c.sh`")
            self.assertEqual(scc.check_reference(c, tmp), [])
            self.assertFalse(c.checkable)
            self.assertIn("wiring_audit unavailable", c.skip_reason)
        finally:
            scc.wiring_audit = saved
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_live_checkout_really_does_have_the_harness(self):
        # Without this, the test above passes just as well when the loader
        # is broken everywhere.
        self.assertIsNotNone(scc._load_wiring_audit(REPO_ROOT))


@unittest.skipUnless(os.path.isfile(LIVE_DOC), "research-state.md absent")
class TestRound414ReferenceRegression(unittest.TestCase):
    """The historical block, kept as the evidence that the class works.

    Round 414's block is frozen in the record, so this cannot be invalidated
    by a later edit to the live document — the same reason
    `TestRound349Regression` exists.
    """

    def test_round_414s_item_10_is_S009(self):
        findings, _ = scc.analyse(LIVE_DOC, REPO_ROOT, block_round=414)
        s9 = [f for f in findings if f.code == "S009"]
        self.assertEqual(len(s9), 1, [str(f) for f in findings])
        self.assertIn("nuc/run_checks_fast.sh", s9[0].message)
        self.assertIn("claimed 0 reference(s)", s9[0].message)

    def test_the_ordinal_in_the_same_sentence_passed_at_the_time(self):
        # The whole class in one assertion: S007 was checking that item, and
        # the ordinal it checks DID advance. The number about the ledger was
        # maintained; the number about the tree was not.
        findings, _ = scc.analyse(LIVE_DOC, REPO_ROOT, block_round=414)
        self.assertEqual([f for f in findings if f.code in ("S007", "S008")],
                         [])

    def test_the_scoped_reference_claim_set_over_the_whole_document(self):
        # Pinned as a SET of round numbers, like the S007/S008 sweep above.
        # Six blocks assert this one claim, in two different prose shapes.
        # These are re-derived against HEAD, so a block that was TRUE when
        # written reads STALE here — which is exactly why this tool's default
        # scope is the LIVE block only. 400/406/407/408 predate round 409's
        # wiring and were true when written; 412 and 414 were not.
        with open(LIVE_DOC, encoding="utf-8") as f:
            blocks = scc.find_blocks(f.read())
        scoped, unscoped = set(), set()
        for b in blocks:
            for item in scc.parse_items(b):
                for c in scc.extract_claims(item):
                    if c.kind != "reference":
                        continue
                    (scoped if c.payload["container"] else unscoped).add(
                        b.round_no)
        self.assertEqual(sorted(scoped), [400, 406, 407, 408, 412, 414])
        # 417 is this round's own block, which QUOTES round 415's unscoped
        # claim while describing it. The grammar cannot tell a quotation from
        # an assertion and does not try to — either way the honest verdict is
        # the same (no container, therefore skipped, therefore counted in the
        # published coverage), so the cheap rule is kept over a clever one.
        self.assertEqual(sorted(unscoped), [415, 417])

    def test_the_live_block_has_no_reference_findings(self):
        findings, _ = scc.analyse(LIVE_DOC, REPO_ROOT)
        bad = [str(f) for f in findings if f.code in ("S009", "S010")]
        self.assertEqual(bad, [], "\n".join(bad))


class TestStaleCountCarriesItsDenominator(unittest.TestCase):
    """Round 417: `0 stale` and its denominators on ONE line.

    Round 414's block was reported `7 claim(s): 7 re-derivable, 0 stale` while
    containing a flatly false item. Nothing lied — the coverage was printed on
    the line above, and every aggregator downstream keeps `lines[-1]`.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.doc = os.path.join(self.tmp, "s.md")
        with open(self.doc, "w", encoding="utf-8") as f:
            f.write(block(9,
                          "1. plain prose, no claim at all",
                          "2. `wc -l s.md` -> 5 s.md",
                          "3. more prose",
                          "4. and more"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def text(self, run=False):
        findings, report = scc.analyse(self.doc, self.tmp, run=run)
        return scc.format_report(findings, report)

    def test_the_stale_line_carries_items_and_claims(self):
        self.assertRegex(self.text(),
                         r"0 stale of \d+ checked; "
                         r"coverage 1/4 items \(25%\), \d+/1 claims")

    def test_a_command_claim_nobody_ran_is_not_counted_as_checked(self):
        # Without `--run` the one command claim is checkABLE and unchecked.
        # Counting it as checked would inflate the denominator with work the
        # tool declined to do — the same overstatement in miniature.
        self.assertIn("0 stale of 0 checked", self.text())
        self.assertIn("0 stale of 1 checked", self.text(run=True))

    def test_the_coverage_token_is_shaped_for_the_aggregator(self):
        import corpus_check
        self.assertEqual(corpus_check.coverage_of(self.text()),
                         "1/4 items (25%), 0/1 claims")


# --------------------------------------------------------------------------
# Round 417 — the ordinal that was maintained and the checker that could not
# see it.
#
# Round 415 wrote, of the very episode S009 was built for: "`state_claim_
# check.py`'s S007 checks exactly that ordinal advances; it did." The ordinal
# did advance. S007 never saw it — `ORDINAL_RE` required the literal word
# `consecutive`, and blocks 406/407/408/412/414 all write the counter as
# `FOURTH round carried`. Widening the grammar exposes a second thing: across
# the rewrite from "wiring X into Y — 0 references" to "X still has 0
# references in Y", the counter went SIXTH -> FIFTH. Backwards.
# --------------------------------------------------------------------------


class TestOrdinalWithoutTheWordConsecutive(unittest.TestCase):
    def test_the_corpus_spelling_without_consecutive_now_parses(self):
        c = one_claim("`a/b.py` has 0 references in `c.sh` — SIXTH round "
                      "carried.")
        self.assertEqual(scc.ordinal_for(c.item.text, c.key()),
                         (6, ("round",)))

    def test_both_spellings_yield_the_SAME_unit(self):
        # If they did not, S007 would report S008 ("the unit changed too")
        # every time an author dropped or added the word, and the real
        # backwards step would be reported as a vocabulary change.
        a = one_claim(B002 + " — 8th consecutive round carried.")
        b = one_claim(B002 + " — 8th round carried.")
        self.assertEqual(scc.ordinal_for(a.item.text, a.key())[1],
                         scc.ordinal_for(b.item.text, b.key())[1])

    def test_an_ordinal_in_ordinary_prose_is_not_a_carry_counter(self):
        # `carried` within three words is the gate. Without it this widening
        # would read any ordinal in the item as the claim's carry count.
        for text in ("`a/b.py` has 0 references in `c.sh` — the fifth round "
                     "of the campaign found nothing",
                     "`a/b.py` has 0 references in `c.sh`, third time I have "
                     "looked at this file today and given up"):
            c = one_claim(text)
            self.assertIsNone(scc.ordinal_for(c.item.text, c.key()), text)

    def test_consecutive_still_parses_without_the_word_carried(self):
        c = one_claim(B002 + " — SEVENTH consecutive down-round.")
        self.assertEqual(scc.ordinal_for(c.item.text, c.key())[0], 7)


class TestSubjectIdentityAcrossARewrite(unittest.TestCase):
    """S007 keys on the sentence; a reference claim keys on its subject."""

    def blocks(self, *pairs):
        text = "\n".join(block(r, "1. " + t) for r, t in pairs)
        bs = scc.find_blocks(text)
        for b in bs:
            b.path = "<test>"
        return bs

    def test_a_reworded_claim_is_still_the_same_claim(self):
        bs = self.blocks(
            (8, "still owns wiring `a/b.py` into `c.sh` — 0 references, "
                "SIXTH round carried."),
            (9, "`a/b.py` still has 0 references in `c.sh` — FIFTH round "
                "carried."))
        claim = [c for c in scc.extract_claims(scc.parse_items(bs[1])[0])
                 if c.kind == "reference"][0]
        f = scc.check_ordinal(claim, bs)
        self.assertEqual(codes(f), ["S007"])
        self.assertIn("not above round 8's 6", f[0].message)

    def test_the_verbatim_key_alone_would_have_missed_it(self):
        # The ablation, as a test: with the substring matcher the two blocks
        # share no span, so block 9 has no prior and nothing fires. This is
        # what makes the subject matcher load-bearing rather than tidy.
        bs = self.blocks(
            (8, "still owns wiring `a/b.py` into `c.sh` — 0 references, "
                "SIXTH round carried."),
            (9, "`a/b.py` still has 0 references in `c.sh` — FIFTH round "
                "carried."))
        claim = [c for c in scc.extract_claims(scc.parse_items(bs[1])[0])
                 if c.kind == "reference"][0]
        hist = scc.ordinal_history(claim.key(), bs)          # no anchor
        self.assertEqual([r for r, _ in hist], [9])
        hist = scc.ordinal_history(claim.key(), bs,
                                   anchor=scc.reference_anchor(claim.payload))
        self.assertEqual([r for r, _ in hist], [8, 9])

    def test_a_different_subject_is_not_matched(self):
        bs = self.blocks(
            (8, "`other/x.py` has 0 references in `c.sh` — SIXTH round "
                "carried."),
            (9, "`a/b.py` still has 0 references in `c.sh` — FIFTH round "
                "carried."))
        claim = [c for c in scc.extract_claims(scc.parse_items(bs[1])[0])
                 if c.kind == "reference"][0]
        self.assertEqual(scc.check_ordinal(claim, bs), [])

    def test_a_rising_ordinal_across_a_rewrite_is_clean(self):
        bs = self.blocks(
            (8, "still owns wiring `a/b.py` into `c.sh` — 0 references, "
                "FIFTH round carried."),
            (9, "`a/b.py` still has 0 references in `c.sh` — SIXTH round "
                "carried."))
        claim = [c for c in scc.extract_claims(scc.parse_items(bs[1])[0])
                 if c.kind == "reference"][0]
        self.assertEqual(scc.check_ordinal(claim, bs), [])


@unittest.skipUnless(os.path.isfile(LIVE_DOC), "research-state.md absent")
class TestRound412OrdinalRegression(unittest.TestCase):
    def test_block_412s_counter_went_backwards_across_the_rewrite(self):
        findings, _ = scc.analyse(LIVE_DOC, REPO_ROOT, block_round=412)
        s7 = [f for f in findings if f.code == "S007"]
        self.assertEqual(len(s7), 1, [str(f) for f in findings])
        self.assertIn("carry ordinal is 5, not above round 408's 6",
                      s7[0].message)

    def test_the_ordinals_the_narrow_grammar_could_not_see(self):
        # Every block in the run_checks_fast carry chain writes its counter
        # WITHOUT the word `consecutive`, which is why S007 was silent for
        # the whole episode round 415 credited it with checking.
        with open(LIVE_DOC, encoding="utf-8") as f:
            blocks = scc.find_blocks(f.read())
        got = {}
        for b in blocks:
            for item in scc.parse_items(b):
                for c in scc.extract_claims(item):
                    if c.kind != "reference" or not c.payload["container"]:
                        continue
                    o = scc.ordinal_for(item.text, c.key())
                    got[b.round_no] = o and o[0]
        self.assertEqual(got, {400: 3, 406: 4, 407: 5, 408: 6,
                               412: 5, 414: 6})

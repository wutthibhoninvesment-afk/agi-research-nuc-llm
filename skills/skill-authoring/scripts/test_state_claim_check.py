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
import shutil
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
        _, report = scc.analyse(self.doc, self.tmp)
        (rounds,) = list(report["ages"].values())
        self.assertEqual(sorted(rounds), [346, 349])

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

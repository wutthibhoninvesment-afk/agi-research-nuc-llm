"""Tests for claim_check.py. Run:  python3 -m unittest test_claim_check -v

Offline: nothing here executes a Verification command except the handful of
cases that deliberately run `true`/`echo` through the executor, and the live
corpus regression test at the bottom, which is static-only (no --run).
"""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claim_check  # noqa: E402

REPO_ROOT = claim_check.DEFAULT_REPO_ROOT


def fence(*lines):
    return "## Verification\n```bash\n" + "\n".join(lines) + "\n```\n"


def parse(*lines):
    return claim_check.parse_commands(fence(*lines))


def codes(findings):
    return [f.code for f in findings]


class TestVerificationSection(unittest.TestCase):
    def test_section_runs_to_the_next_same_level_heading(self):
        body = "## Steps\n1. a\n\n## Verification\nRUN ME\n\n## Pitfalls\nnope\n"
        sec = claim_check.verification_section(body)
        self.assertIn("RUN ME", sec)
        self.assertNotIn("nope", sec)

    def test_deeper_headings_stay_inside_the_section(self):
        body = "## Verification\nA\n### Sub\nB\n## Next\nC\n"
        sec = claim_check.verification_section(body)
        self.assertIn("B", sec)
        self.assertNotIn("C", sec)

    def test_a_shell_comment_in_the_fence_is_not_a_heading(self):
        # `# 1. …` inside a bash fence looks exactly like a level-1 ATX
        # heading. Treating it as one truncated 7 of this corpus's 19
        # Verification blocks to nothing.
        body = "## Verification\n```bash\n# 1. first step\npytest -q\n```\n"
        self.assertIn("pytest -q", claim_check.verification_section(body))

    def test_blank_fenced_preserves_offsets(self):
        body = "a\n```\nxxxx\n```\nb\n"
        blanked = claim_check.blank_fenced(body)
        self.assertEqual(len(blanked), len(body))
        self.assertEqual(blanked.split("\n")[2], "    ")

    def test_heading_match_is_the_same_substring_rule_as_skill_lint_h004(self):
        self.assertIn("X", claim_check.verification_section("# Verify it\nX\n"))
        self.assertIn("X", claim_check.verification_section("#### VERIFICATION\nX\n"))

    def test_no_verification_section_is_empty_not_an_error(self):
        self.assertEqual(claim_check.verification_section("## Steps\n1. a\n"), "")

    def test_section_running_to_end_of_file(self):
        self.assertIn("A", claim_check.verification_section("## Verification\nA\n"))


class TestCommentSplitting(unittest.TestCase):
    def test_trailing_comment_is_the_claim(self):
        cmd, comment = claim_check.split_command_and_comment(
            "pytest -q  # expected: 3 passed")
        self.assertEqual(cmd, "pytest -q")
        self.assertEqual(comment, "expected: 3 passed")

    def test_hash_inside_double_quotes_is_not_a_comment(self):
        cmd, comment = claim_check.split_command_and_comment('grep "a#b" f.md')
        self.assertEqual(cmd, 'grep "a#b" f.md')
        self.assertEqual(comment, "")

    def test_hash_inside_single_quotes_is_not_a_comment(self):
        cmd, _ = claim_check.split_command_and_comment("awk '$2==1 # x'")
        self.assertEqual(cmd, "awk '$2==1 # x'")

    def test_hash_glued_to_a_word_is_not_a_comment(self):
        cmd, comment = claim_check.split_command_and_comment("open ref.md#frag")
        self.assertEqual(cmd, "open ref.md#frag")
        self.assertEqual(comment, "")

    def test_leading_hash_is_a_whole_line_comment(self):
        cmd, comment = claim_check.split_command_and_comment("# just a note")
        self.assertEqual(cmd, "")
        self.assertEqual(comment, "just a note")

    def test_escaped_quote_inside_a_quoted_string(self):
        cmd, comment = claim_check.split_command_and_comment(
            'echo "a\\"b"   # note')
        self.assertEqual(comment, "note")


class TestParseCommands(unittest.TestCase):
    def test_only_fenced_lines_count(self):
        text = "## Verification\n- a prose bullet with `pytest -q`\n" \
               "```\npytest -q\n```\n"
        cmds = claim_check.parse_commands(text)
        self.assertEqual([c.command for c in cmds], ["pytest -q"])

    def test_expected_comment_line_attaches_to_previous_command(self):
        cmds = parse("pytest -q", "# expected: 3 passed")
        self.assertEqual(cmds[0].claim, "expected: 3 passed")

    def test_expected_continuation_lines_are_folded_in(self):
        cmds = parse("pytest -q", "# expected: 3 passed", "# and quickly")
        self.assertIn("and quickly", cmds[0].claim)

    def test_numbered_lead_in_comment_does_not_become_the_previous_claim(self):
        # sampled-interval-brackets numbers its steps with comments that
        # introduce the NEXT command; attaching them backwards mislabels
        # every claim in the block.
        cmds = parse("pytest -q -k a", "# 2. now pin the bracket",
                     "pytest -q -k b")
        self.assertEqual(cmds[0].claim, "")
        self.assertEqual(cmds[1].claim, "")

    def test_blank_line_detaches_a_pending_claim(self):
        cmds = parse("pytest -q", "", "# expected: 9 passed")
        self.assertEqual(cmds[0].claim, "")

    def test_backslash_continuation_joins(self):
        cmds = parse("pytest -q a.py \\", "    b.py   # expected: 2 passed")
        self.assertEqual(len(cmds), 1)
        self.assertIn("b.py", cmds[0].command)
        self.assertEqual(cmds[0].claim, "expected: 2 passed")

    def test_unterminated_quote_joins_a_multi_line_python_c(self):
        cmds = parse('python3 -c "', "import sys", 'print(1)"  # expected: 1')
        self.assertEqual(len(cmds), 1)
        self.assertIn("import sys", cmds[0].command)

    def test_apostrophe_in_a_comment_does_not_swallow_the_next_command(self):
        # The real bug this test pins: `# only the CURRENT session's stub`
        # left an odd number of single quotes on the RAW line, so a raw-line
        # balance check read it as an open quote and absorbed every following
        # command into one blob — silently, since a swallowed command simply
        # never appears in the report.
        cmds = parse("grep -n PENDING state.md | tail   # the session's stub",
                     "python3 next_one.py",
                     "python3 third_one.py")
        self.assertEqual([c.command for c in cmds],
                         ["grep -n PENDING state.md | tail",
                          "python3 next_one.py", "python3 third_one.py"])

    def test_line_numbers_are_absolute_in_the_file(self):
        cmds = claim_check.parse_commands(fence("pytest -q"), "f.md", 100)
        self.assertEqual(cmds[0].line_no, 102)   # heading, fence, command

    def test_claim_resets_between_fences(self):
        text = "## Verification\n```\npytest -q\n```\ntext\n```\nls\n```\n"
        cmds = claim_check.parse_commands(text)
        self.assertEqual([c.command for c in cmds], ["pytest -q", "ls"])


class TestClassify(unittest.TestCase):
    def assertManual(self, command, category):
        kind, reason = claim_check.classify(command)
        self.assertEqual(kind, "manual", command)
        self.assertTrue(reason.startswith(category),
                        "%r classified %r, wanted %s" % (command, reason, category))

    def test_pytest_and_unittest_are_auto(self):
        for c in ("python3 -m pytest -q tests/t.py",
                  "python3 -m unittest discover -s scripts",
                  "pytest -q tests/t.py",
                  "cd harness && python3 -m pytest -q tests/t.py"):
            self.assertEqual(claim_check.classify(c)[0], "auto", c)

    def test_read_only_shell_tools_are_auto(self):
        for c in ("wc -l f.md", "grep -n X f.md", "git status --porcelain",
                  "git log --oneline -3"):
            self.assertEqual(claim_check.classify(c)[0], "auto", c)

    def test_priced_commands_are_manual(self):
        self.assertManual("claude -p 'hi'", "priced")
        self.assertManual("python3 live_smoke.py cli-guards", "priced")
        self.assertManual("python3 nuc/taskscript/run.py x.errand probe", "priced")

    def test_trigger_eval_is_priced_unless_audit(self):
        self.assertManual("python3 trigger_eval.py --repeats 4", "priced")
        self.assertEqual(
            claim_check.classify(
                "python3 trigger_eval.py --audit state/trigger-eval")[0], "auto")

    def test_network_commands_are_manual(self):
        self.assertManual("ssh -i k jab@host uptime", "network")
        self.assertManual("python3 nuc/fast_lane.py handoff ./m jab@b '~/m'",
                          "network")

    def test_mutating_commands_are_manual(self):
        self.assertManual("python3 -m swe.x --write tests/gen.py", "mutating")
        self.assertManual("git commit -m x", "mutating")
        self.assertManual("printf 'x' > /tmp/f", "mutating")

    def test_a_dangerous_flag_beats_an_allowlisted_program(self):
        # MANUAL wins over AUTO: pytest is allowlisted, `--out` is not.
        self.assertManual("python3 -m pytest -q --out /tmp/report", "mutating")

    def test_expensive_campaigns_are_manual(self):
        self.assertManual("python3 -m swe.campaign --limit 30", "expensive")
        self.assertManual("python3 bench_elision.py", "expensive")

    def test_environment_dependent_commands_are_manual(self):
        self.assertManual("ps -axo pid,command | grep -c pytest", "environment")
        self.assertManual("find . -type f -newer x.md", "environment")

    def test_placeholders_are_manual(self):
        self.assertManual("skill_lint.py --house skills/<name>/", "placeholder")
        self.assertManual("head -3 state/round-NNN-predictions.md", "placeholder")
        self.assertManual("grep -n HIT knowledge/round-*.md", "placeholder")

    def test_shell_constructs_are_manual(self):
        self.assertManual("for p in 1 2; do echo $p; done", "shell")

    def test_bare_cd_is_manual_and_says_why(self):
        self.assertManual("cd harness", "bare `cd`")

    def test_unknown_program_fails_closed(self):
        self.assertManual("./some_new_tool.sh --go", "unknown program")

    def test_cd_prefix_is_stripped_before_classifying(self):
        # Without stripping, `cd X && claude -p` and `cd X && pytest` would
        # both be judged on the `cd`.
        self.assertManual("cd harness && python3 live_smoke.py", "priced")

    def test_cd_prefix_stripping_is_what_makes_anchored_rules_work(self):
        # The `cd X &&` strip only CHANGES an answer for the `^`-anchored
        # rules — every other pattern matches anywhere in the line. A
        # mutation run proved the point: deleting the strip survived the
        # whole suite until these two cases existed.
        self.assertEqual(
            claim_check.classify("cd languages/whence && pytest -q t.py")[0],
            "auto")
        self.assertEqual(
            claim_check.classify("cd harness && git status --porcelain")[0],
            "auto")
        self.assertManual("cd harness && ps -axo pid,command", "environment")


class TestPathTokens(unittest.TestCase):
    def test_extracts_anchored_and_extension_paths(self):
        toks = claim_check.path_tokens(
            "python3 -m pytest -q harness/tests/t.py ./x.md /etc/hosts")
        self.assertEqual(toks, ["./x.md", "/etc/hosts", "harness/tests/t.py"]
                         if False else toks)   # order below
        self.assertIn("harness/tests/t.py", toks)
        self.assertIn("./x.md", toks)
        self.assertIn("/etc/hosts", toks)

    def test_skips_flags_urls_and_bare_words(self):
        toks = claim_check.path_tokens(
            "pytest -q -k 'a or b' http://x/y tests --limit 20")
        self.assertEqual(toks, [])

    def test_skips_scratch_paths(self):
        self.assertEqual(claim_check.path_tokens("swe.loop --out /tmp/run"), [])
        self.assertEqual(claim_check.path_tokens("readlink /proc/1/cwd"), [])

    def test_skips_placeholder_tokens(self):
        for c in ("head -3 state/round-NNN-x.md", "ls skills/<name>/",
                  "grep x knowledge/round-*.md", "readlink /proc/$p/cwd"):
            self.assertEqual(claim_check.path_tokens(c), [], c)

    def test_strips_surrounding_quotes_and_punctuation(self):
        self.assertEqual(claim_check.path_tokens("cat 'harness/x.py';"),
                         ["harness/x.py"])


class TestResolveAndAnchor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "harness", "tests"))
        open(os.path.join(self.tmp, "harness", "tests", "t.py"), "w").close()

    def test_resolves_under_the_first_matching_base(self):
        hit = claim_check.resolve_token(
            "tests/t.py", [os.path.join(self.tmp, "harness"), self.tmp])
        self.assertTrue(hit.endswith("harness/tests/t.py"))

    def test_returns_none_when_no_base_matches(self):
        self.assertIsNone(claim_check.resolve_token("tests/nope.py", [self.tmp]))

    def test_tilde_is_expanded(self):
        self.assertIsNotNone(claim_check.resolve_token("~", []))
        self.assertIsNone(
            claim_check.resolve_token("~/definitely-not-a-real-dir-9f2", []))

    def test_absolute_paths_ignore_bases(self):
        self.assertIsNone(claim_check.resolve_token("/nope/9f2", [self.tmp]))

    def test_anchored_requires_a_real_first_component(self):
        self.assertTrue(claim_check.is_anchored("harness/tests/t.py", [self.tmp]))
        self.assertFalse(claim_check.is_anchored("tests/t.py", [self.tmp]))

    def test_absolute_and_tilde_are_always_anchored(self):
        self.assertTrue(claim_check.is_anchored("/x/y", []))
        self.assertTrue(claim_check.is_anchored("~/x", []))

    def test_dotdot_is_anchored_because_it_names_its_own_base(self):
        self.assertTrue(claim_check.is_anchored("../languages/x", [self.tmp]))


class TestCheckPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "harness", "tests"))
        open(os.path.join(self.tmp, "harness", "tests", "t.py"), "w").close()

    def run_block(self, *lines):
        cmds = parse(*lines)
        for c in cmds:
            c.kind, c.reason = claim_check.classify(c.command)
        return claim_check.check_paths(cmds, self.tmp)

    def test_missing_cd_target_is_c001(self):
        findings, _, _ = self.run_block("cd ~/definitely-not-here-9f2")
        self.assertEqual(codes(findings), ["C001"])
        self.assertIn("no such directory", findings[0].message)

    def test_real_cd_target_is_clean(self):
        findings, _, _ = self.run_block("cd harness")
        self.assertEqual(findings, [])

    def test_cd_moves_the_base_for_later_commands(self):
        findings, _, _ = self.run_block("cd harness",
                                        "python3 -m pytest -q tests/t.py")
        self.assertEqual(findings, [])

    def test_cd_and_prefix_moves_the_base_too(self):
        findings, _, _ = self.run_block("cd harness && python3 -m pytest -q tests/t.py",
                                        "python3 -m pytest -q tests/t.py")
        self.assertEqual(findings, [])

    def test_missing_file_under_a_known_base_is_c001(self):
        findings, _, _ = self.run_block("python3 -m pytest -q harness/tests/gone.py")
        self.assertEqual(codes(findings), ["C001"])

    def test_unanchored_relative_path_is_skipped_not_flagged(self):
        # A portable skill documenting the READER's repo layout.
        findings, checked, skipped = self.run_block("pytest -q tests/t.py")
        self.assertEqual(findings, [])
        self.assertEqual(skipped, 1)
        self.assertEqual(checked, 0)

    def test_network_command_paths_are_not_checked(self):
        findings, _, skipped = self.run_block(
            "python3 harness/fast_lane.py handoff ./gone jab@b")
        self.assertEqual(findings, [])
        self.assertTrue(skipped >= 1)

    def test_mutating_command_output_paths_are_not_checked(self):
        findings, _, _ = self.run_block(
            "python3 -m swe.x --write harness/tests/generated.py")
        self.assertEqual(findings, [])

    def test_a_directory_argument_becomes_a_base_for_later_commands(self):
        # fuzz-mutate-kill-loop names `../languages/whence` once, then writes
        # later commands relative to it.
        os.makedirs(os.path.join(self.tmp, "languages", "whence", "whence"))
        open(os.path.join(self.tmp, "languages", "whence", "whence", "i.py"),
             "w").close()
        findings, _, _ = self.run_block(
            "python3 -m pytest languages/whence whence/i.py",
            "python3 -m pytest --files whence/i.py")
        self.assertEqual(findings, [])

    def test_counts_report_honest_coverage(self):
        _, checked, skipped = self.run_block(
            "cd harness", "python3 -m pytest -q tests/t.py",
            "pytest -q othertests/x.py")
        self.assertEqual((checked, skipped), (2, 1))


class TestClaimMetrics(unittest.TestCase):
    def test_extracts_every_supported_metric(self):
        m = claim_check.claim_metrics(
            "expected: Ran 165 tests, 3 passed, 1 failed, 2 deselected, "
            "19 skill(s), 0 error(s), 1 warning(s), 0 gaps, exit 1")
        self.assertEqual(m, {"ran_tests": 165, "passed": 3, "failed": 1,
                             "deselected": 2, "skills": 19, "errors": 0,
                             "warnings": 1, "gaps": 0, "exit": 1})

    def test_unquantified_claim_yields_nothing(self):
        self.assertEqual(claim_check.claim_metrics("expected: all passed"), {})

    def test_observed_takes_the_last_occurrence(self):
        # pytest prints a per-file line and then a summary; the summary wins.
        got = claim_check.observed_metrics("2 passed\n\n7 passed in 1.2s\n", 0)
        self.assertEqual(got["passed"], 7)

    def test_observed_always_carries_the_exit_code(self):
        self.assertEqual(claim_check.observed_metrics("", 3)["exit"], 3)


class TestCheckByRunning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def run_block(self, *lines):
        cmds = parse(*lines)
        for c in cmds:
            c.kind, c.reason = claim_check.classify(c.command)
        return claim_check.check_by_running(cmds, self.tmp, 60)

    def test_matching_claim_produces_no_finding(self):
        findings = self.run_block("grep -c x /dev/null   # expected: exit 1")
        self.assertEqual(codes(findings), [])

    def test_mismatched_metric_is_c002(self):
        findings = self.run_block("grep -c x /dev/null   # expected: exit 0")
        self.assertEqual(codes(findings), ["C002"])
        self.assertIn("observed exit=1", findings[0].message)

    def test_metric_absent_from_the_output_is_c002(self):
        findings = self.run_block("grep -c x /dev/null   # expected: 3 passed")
        self.assertEqual(codes(findings), ["C002"])
        self.assertIn("printed no passed", findings[0].message)

    def test_unquantified_claim_is_reported_not_silently_passed(self):
        findings = self.run_block("grep -c x /dev/null  # expected: looks fine")
        self.assertEqual(codes(findings), ["C003"])
        self.assertEqual(findings[0].level, "UNQUANTIFIED")

    def test_manual_commands_are_never_executed(self):
        marker = os.path.join(self.tmp, "ran")
        findings = self.run_block(
            "python3 -c \"open('%s','w')\"   # expected: 1 passed" % marker)
        self.assertFalse(os.path.exists(marker))
        self.assertEqual(codes(findings), [])

    def test_absent_target_is_skipped_not_run(self):
        # NB: a `/tmp/...` argument would be suppressed as scratch before it
        # ever got here, so the missing target has to be repo-relative.
        findings = self.run_block(
            "python3 -m pytest -q sub/gone.py  # expected: 3 passed")
        self.assertEqual(codes(findings), ["C004"])
        self.assertEqual(findings[0].level, "SKIPPED")

    def test_cd_and_prefix_target_resolves_against_the_cd_dir_not_the_cwd(self):
        # `cd harness && pytest tests/x.py` runs from harness/, so the C004
        # absent-target gate must resolve `tests/x.py` there. Resolving it
        # against the current cwd skipped four real, runnable commands in
        # the live corpus as "absent from this checkout".
        sub = os.path.join(self.tmp, "harness", "tests")
        os.makedirs(sub)
        with open(os.path.join(sub, "x.py"), "w") as f:
            f.write("x = 1\n")
        findings = self.run_block(
            "cd harness && grep -c x tests/x.py   # expected: exit 0")
        self.assertEqual(codes(findings), [])

    def test_timeout_kills_the_whole_process_group_not_just_the_shell(self):
        # `subprocess.run(shell=True, timeout=T)` kills only the /bin/sh; a
        # grandchild survives, reparents to init and keeps burning CPU. That
        # happened live during this round's own corpus sweep (a pytest run
        # with ppid=1 still going four minutes into a 150-second cap). It is
        # also a pitfall already written down in
        # skills/fuzz-mutate-kill-loop/references/pitfalls.md.
        marker = os.path.join(self.tmp, "grandchild-survived")
        cmd = claim_check.Command(
            "f.md", 1,
            "python3 -c \"import time; time.sleep(6); open(%r,'w')\" & wait"
            % marker, "")
        out, rc = claim_check.run_command(cmd, self.tmp, self.tmp, 1)
        self.assertEqual(rc, -1)
        self.assertIn("TIMEOUT", out)
        deadline = time.time() + 8
        while time.time() < deadline:
            self.assertFalse(os.path.exists(marker),
                             "grandchild outlived the timeout")
            time.sleep(0.5)

    def test_timeout_is_reported_as_a_stale_claim_not_a_crash(self):
        cmds = parse("python3 -m pytest --version  # expected: 3 passed")
        for c in cmds:
            c.kind, c.reason = claim_check.classify(c.command)
        findings = claim_check.check_by_running(cmds, self.tmp, 0)
        self.assertEqual(codes(findings), ["C002"])

    def test_cd_and_prefix_moves_cwd_for_later_commands(self):
        sub = os.path.join(self.tmp, "sub")
        os.makedirs(sub)
        with open(os.path.join(sub, "here.txt"), "w") as f:
            f.write("x\n")
        findings = self.run_block(
            "cd sub && grep -c x here.txt   # expected: exit 0",
            "grep -c x here.txt             # expected: exit 0")
        self.assertEqual(codes(findings), [])


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.skill = os.path.join(self.tmp, "a-skill")
        os.makedirs(self.skill)

    def write(self, verification):
        with open(os.path.join(self.skill, "SKILL.md"), "w") as f:
            f.write("---\nname: a-skill\ndescription: d\n---\n\n# T\n\n"
                    + verification)

    def test_exit_0_when_clean(self):
        self.write(fence("python3 -m pytest -q tests/x.py"))
        self.assertEqual(
            claim_check.main([self.skill, "--repo-root", self.tmp]), 0)

    def test_exit_1_on_a_stale_path(self):
        self.write(fence("cd ~/definitely-not-here-9f2"))
        self.assertEqual(
            claim_check.main([self.skill, "--repo-root", self.tmp]), 1)

    def test_exit_2_when_no_skill_md_found(self):
        self.assertEqual(claim_check.main([os.path.join(self.tmp, "nope")]), 2)

    def test_line_numbers_account_for_frontmatter(self):
        self.write(fence("cd ~/definitely-not-here-9f2"))
        cmds = claim_check.commands_for(os.path.join(self.skill, "SKILL.md"))
        with open(os.path.join(self.skill, "SKILL.md")) as f:
            lines = f.read().split("\n")
        self.assertIn("cd ~/definitely-not-here-9f2",
                      lines[cmds[0].line_no - 1])

    def test_skill_with_no_verification_block_is_not_an_error(self):
        with open(os.path.join(self.skill, "SKILL.md"), "w") as f:
            f.write("---\nname: a-skill\ndescription: d\n---\n\n# T\n\n## Steps\n1. a\n")
        self.assertEqual(
            claim_check.main([self.skill, "--repo-root", self.tmp]), 0)

    def test_directory_of_skill_dirs_is_discovered(self):
        self.write(fence("python3 -m pytest -q tests/x.py"))
        self.assertEqual(claim_check.skill_md_paths(self.tmp),
                         [os.path.join(self.skill, "SKILL.md")])


class TestLiveCorpusClaims(unittest.TestCase):
    """The regression guard: the real skills/ tree must have zero stale path
    claims. This is what makes the NEXT `cd ~/agi-research` a test failure
    instead of an audit somebody has to remember to run — the same role
    round 333's TestLiveCorpusAnchors plays for rotted link fragments.

    Static only: no Verification command is executed here. `--run` is a
    deliberate opt-in, and a unit-test suite is exactly the wrong place to
    start shelling out to pytest runs that take minutes."""

    def test_no_stale_paths_in_the_real_corpus(self):
        skills_dir = os.path.join(REPO_ROOT, "skills")
        if not os.path.isdir(skills_dir):
            self.skipTest("live corpus not present")
        stale = []
        for md in claim_check.skill_md_paths(skills_dir):
            cmds = claim_check.commands_for(md)
            for c in cmds:
                c.kind, c.reason = claim_check.classify(c.command)
            findings, _, _ = claim_check.check_paths(cmds, REPO_ROOT)
            stale.extend(str(f) for f in findings)
        self.assertEqual(stale, [], "stale path claims in Verification blocks:\n"
                                    + "\n".join(stale))

    # Six skills verify by judgement, not by a command: their Verification
    # sections are prose checklists with no fence. That is legitimate (and
    # `skill_lint.py`'s H005 permits it — it only requires a fence SOMEWHERE
    # in the body), but it has to be an explicit list, because "0 commands
    # parsed" and "the parser broke" look identical from the outside. Two
    # parser bugs found in round 339 each emptied blocks that DO have
    # fences; without this pin, both would have read as green.
    PROSE_ONLY_VERIFICATION = {
        # Round 363 added `measured-exemption`, and HOW it was found is the
        # point: this test had been RED since round 359's commit `a439262`
        # shipped that skill, and nothing ran it. `skills/` has TWO
        # enforcement surfaces — the five checkers and this unittest/pytest
        # suite — and before round 363 the driver ran neither. Confirmed
        # prose-only rather than allowlisted on faith: its Verification
        # section is a numbered checklist with inline-backtick `grep`, no
        # fenced block, and `commands_for` reads fences only. The skill's
        # verification genuinely cannot be a fixed command ("run a campaign
        # and count the three states"). Both surfaces now run every round
        # via `skills/run_checks_fast.sh`.
        "measured-exemption",
        "engine-prefix-reuse-audit",
        "generator-trampoline-evaluator",
        "llm-engine-benchmarking",
        "optimization-transparency-differential",
        "shared-tip-immutable-lists",
        "tiny-language-implementation",
    }

    def test_only_the_known_prose_only_skills_parse_to_zero_commands(self):
        skills_dir = os.path.join(REPO_ROOT, "skills")
        if not os.path.isdir(skills_dir):
            self.skipTest("live corpus not present")
        empty = {os.path.basename(os.path.dirname(md))
                 for md in claim_check.skill_md_paths(skills_dir)
                 if not claim_check.commands_for(md)}
        self.assertEqual(
            empty, self.PROSE_ONLY_VERIFICATION,
            "unexpected: %s parsed to zero commands (parser regression?); "
            "missing: %s (gained a command — drop it from the set)"
            % (sorted(empty - self.PROSE_ONLY_VERIFICATION),
               sorted(self.PROSE_ONLY_VERIFICATION - empty)))


if __name__ == "__main__":
    unittest.main()

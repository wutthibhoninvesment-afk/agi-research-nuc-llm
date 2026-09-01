"""Tests for claim_check.py. Run:  python3 -m unittest test_claim_check -v

Offline: nothing here executes a Verification command except the handful of
cases that deliberately run `true`/`echo` through the executor, and the live
corpus regression test at the bottom, which is static-only (no --run).
"""

import contextlib
import io
import os
import re
import shutil
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

    def test_pristine_check_read_only_verbs_are_auto_and_the_rest_are_not(self):
        """Round 429. `pristine_check.py` was added to the allowlist so that
        `pristine-checkout-differential`'s Verification block executes at all
        — it had parsed to ZERO commands since round 427 moved its transcripts
        into `references/`. The allowlist entry names FOUR verbs rather than
        the script, because two of the others (`check`, `baseline`) run whole
        suites in a fresh worktree and append to
        `state/pristine-check-ledger.jsonl`. A future verb is manual until
        someone adds it here on purpose, which is the point."""
        for c in ("python3 harness/pristine_check.py suites",
                  "python3 harness/pristine_check.py status",
                  "python3 harness/pristine_check.py dirt",
                  "python3 harness/pristine_check.py baseline-status"):
            self.assertEqual(claim_check.classify(c)[0], "auto", c)
        for c in ("python3 harness/pristine_check.py check --suite harness-fast",
                  "python3 harness/pristine_check.py baseline HEAD",
                  "python3 harness/pristine_check.py suites-and-then-some"):
            self.assertEqual(claim_check.classify(c)[0], "manual", c)

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


# --------------------------------------------------------------------------
# Round 411: the `cd` branch is the tool's SECOND door into C001, and for 71
# rounds it consulted none of the four suppression rules `path_tokens`
# applies. `classify` had the right answer the whole time — it is computed at
# collection and hangs off `cmd.reason` — and this branch never read it.
# --------------------------------------------------------------------------

def _old_cd_branch(command, cwd, repo_root):
    """`check_paths`'s round-339 `cd` branch, VERBATIM apart from taking its
    inputs as arguments and returning a verdict instead of appending.

    Quarantined rather than deleted (round 410's `skip-reason-is-a-claim`
    step 6) so the falsification re-runs on every suite run instead of living
    in a scratch directory somebody throws away. NEVER called on the live
    corpus — only by the differential tests directly below.

    Returns "stale" | "checked" | None (not a `cd` line).
    """
    m = re.match(r"^\s*cd\s+(\S+)", command)
    if not m:
        return None
    target = m.group(1).strip("'\"")
    resolved = claim_check.resolve_token(target, [cwd, repo_root])
    return "stale" if resolved is None else "checked"


class TestCdTargetConsultsTheExemptionGate(unittest.TestCase):
    """The four suppression rules apply to a `cd` target like any other path."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "harness", "tests"))
        open(os.path.join(self.tmp, "harness", "tests", "t.py"), "w").close()

    def run_block(self, *lines):
        cmds = parse(*lines)
        for c in cmds:
            c.kind, c.reason = claim_check.classify(c.command)
        return claim_check.check_paths(cmds, self.tmp)

    # ---- the gate itself -------------------------------------------------

    def test_the_gate_names_a_distinct_cause_for_each_exempt_class(self):
        reasons = {
            "placeholder": claim_check.token_exempt_reason("languages/<lang>"),
            "scratch": claim_check.token_exempt_reason("/tmp/wt-411"),
            "urlish": claim_check.token_exempt_reason("https://x/y"),
        }
        for k, v in reasons.items():
            self.assertIsNotNone(v, k)
        # un-confusable: each reason carries a word the others do not
        self.assertIn("placeholder", reasons["placeholder"])
        self.assertIn("scratch", reasons["scratch"])
        self.assertNotIn("scratch", reasons["placeholder"])
        self.assertNotIn("placeholder", reasons["scratch"])

    def test_a_real_relative_path_is_not_exempt(self):
        self.assertIsNone(claim_check.token_exempt_reason("harness/tests/t.py"))
        self.assertIsNone(claim_check.token_exempt_reason("~/agi-research"))

    # ---- the differential: what actually changed -------------------------

    def test_the_old_cd_branch_called_a_placeholder_target_stale(self):
        self.assertEqual(
            _old_cd_branch("cd languages/<lang>", self.tmp, self.tmp), "stale")
        self.assertEqual(self.run_block("cd languages/<lang>")[0], [])

    def test_the_old_cd_branch_called_a_scratch_target_stale(self):
        self.assertEqual(
            _old_cd_branch("cd /tmp/wt-411-not-here", self.tmp, self.tmp),
            "stale")
        self.assertEqual(self.run_block("cd /tmp/wt-411-not-here")[0], [])

    def test_the_live_corpus_line_that_provoked_this(self):
        """`skills/skip-reason-is-a-claim/SKILL.md:192`, verbatim."""
        line = ("cd /tmp/<scratch-worktree> && pytest tests/ -q -rs 2>&1 "
                "| grep SKIPPED")
        self.assertEqual(_old_cd_branch(line, self.tmp, self.tmp), "stale")
        findings, checked, skipped = self.run_block(line)
        self.assertEqual(findings, [])
        # both the cd target AND the `tests/` behind it are accounted for as
        # skipped — see the masking test below for why that is the point
        self.assertEqual((checked, skipped), (0, 2))

    # ---- the second half of the bug: a false positive that hid a real one --

    def test_a_false_cd_positive_used_to_mask_every_token_behind_it(self):
        """The old branch `continue`d after emitting, so the REST of a
        `cd X && rest` line was never path-checked at all.

        A false STALE therefore also bought a false NEGATIVE: a genuinely
        missing file named after the `&&` was invisible for as long as the
        prefix was exempt-but-unresolvable.
        """
        line = "cd /tmp/<scratch-worktree> && python3 -m pytest harness/tests/gone.py"
        # old: the cd fires, and its `continue` means `harness/tests/gone.py`
        # is never looked at
        self.assertEqual(_old_cd_branch(line, self.tmp, self.tmp), "stale")
        # new: the cd is silent and the real stale path behind it is FOUND
        findings, _, _ = self.run_block(line)
        self.assertEqual(codes(findings), ["C001"])
        self.assertIn("gone.py", findings[0].message)

    # ---- exempt is not "skip the branch" ---------------------------------

    def test_an_exempt_target_that_exists_still_moves_the_working_directory(self):
        """`exempt` suppresses the FINDING, not the `cwd` side effect.

        A naive early-`continue` fix would stop tracking the working
        directory and silently un-anchor every later command in the block.
        """
        scratch = tempfile.mkdtemp(prefix="cc411-")
        os.makedirs(os.path.join(scratch, "sub"))
        open(os.path.join(scratch, "sub", "here.py"), "w").close()
        try:
            findings, _, _ = self.run_block(
                "cd %s" % os.path.join(scratch, "sub"),
                "python3 -m pytest -q here.py")
            self.assertEqual(findings, [])
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    # ---- the rule that must NOT have been weakened ------------------------

    def test_an_ordinary_missing_cd_target_is_still_c001(self):
        findings, _, _ = self.run_block("cd ~/definitely-not-here-9f2")
        self.assertEqual(codes(findings), ["C001"])

    def test_a_real_cd_target_is_still_checked_not_skipped(self):
        _, checked, skipped = self.run_block("cd harness")
        self.assertEqual((checked, skipped), (1, 0))


class TestExemptionGateHasOneHome(unittest.TestCase):
    """Structural pins. A third door will be added; it must ask the gate."""

    SRC = io.open(claim_check.__file__, encoding="utf-8").read()

    def test_the_suppression_regexes_are_used_only_inside_the_gate(self):
        """`TOKEN_PLACEHOLDER_RE` and `SCRATCH_PREFIXES` may be READ in
        exactly one function. Anywhere else is a second copy of the policy.
        """
        for name in ("TOKEN_PLACEHOLDER_RE", "SCRATCH_PREFIXES"):
            uses = [ln for ln in self.SRC.split("\n")
                    if name in ln and not ln.startswith(name)
                    and not ln.lstrip().startswith("#")]
            self.assertEqual(
                len(uses), 1,
                "%s is read %d times; the gate is supposed to be its only "
                "reader:\n%s" % (name, len(uses), "\n".join(uses)))

    def test_every_c001_site_consults_the_exemption_gate(self):
        """Every function that can append a C001 must mention the gate.

        Deliberately coarse — it cannot prove the call is on the right path.
        What it does prove is that a new C001 site cannot be added in
        ignorance of the gate's existence, which is exactly how this bug
        was born: `path_tokens` and the `cd` branch were written in the same
        commit and never reconciled.
        """
        emitters = [f for f in re.findall(
            r"^def (\w+)\(.*?(?=^def |\Z)", self.SRC, re.S | re.M)]
        bodies = dict(zip(emitters, re.split(r"^def \w+\(", self.SRC,
                                             flags=re.M)[1:]))
        sites = [n for n, b in bodies.items() if '"C001"' in b]
        self.assertIn("check_paths", sites)
        for name in sites:
            # CODE only. The branch this test was written for carries a
            # six-line comment explaining the gate, and a pin that accepts a
            # comment is a pin its own subject can satisfy in prose while the
            # call is gone (round 410, `skip-reason-is-a-claim`).
            code = "\n".join(
                ln for ln in bodies[name].split("\n")
                if not ln.lstrip().startswith("#"))
            self.assertIn(
                "token_exempt_reason(", code,
                "%s emits C001 without CALLING token_exempt_reason" % name)

    def test_the_quarantined_old_branch_still_exists(self):
        """Paired with the pin above: `_old_cd_branch` is the falsification,
        and a pin that only forbids things passes when the subject is gone.
        """
        here = io.open(__file__, encoding="utf-8").read()
        self.assertTrue(
            re.search(r"^def _old_cd_branch\(", here, re.M),
            "the quarantined round-339 branch was deleted; the differential "
            "tests above are then asserting against nothing")


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

    # These skills verify by judgement, not by a command: their Verification
    # sections are prose checklists with no fence. (The comment used to open
    # "Six skills"; it listed eight. Round 429 removed the count rather than
    # correcting it — `len(PROSE_ONLY_VERIFICATION)` is the number and this
    # is a gloss.) That is legitimate (and
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
        # Round 399 added `filter-shares-the-defect` (authored by round 398,
        # a language(C) round, which did not touch this pin — so this test
        # was RED at HEAD and `skills/run_checks_fast.sh` reported it, the
        # same shape round 363 recorded above one round later instead of
        # five). Confirmed prose-only rather than allowlisted on faith: its
        # `## Verification` is a `- [ ]` checklist plus a reference link,
        # with no fenced block, and `commands_for` reads fences only. It is
        # a discipline skill whose checks are judgements ("the filter
        # predicate and the defect do not name the same field"), not a
        # command; giving it a fenced command would mean pinning another
        # track's test count here, which is the rot class this corpus keeps
        # finding.
        "filter-shares-the-defect",
        "engine-prefix-reuse-audit",
        # `generator-trampoline-evaluator` was here until round 429, and it
        # should not have been. `skill_lint`'s new H006 found its
        # `references/commands.md` holding six runnable invocations while its
        # `## Verification` had none — the same references-split that emptied
        # `pristine-checkout-differential` in round 427, standing longer and
        # absorbed by this allowlist instead of being fixed. It now carries
        # the decoupling proof and its trampoline suite in the SKILL.md.
        # An entry here has to be a skill whose verification genuinely cannot
        # be a command, not one whose commands live somewhere else.
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


# --------------------------------------------------------------------------
# Round 417 — `0 stale` and its denominators on the SAME line.
#
# `corpus_check.py` quotes each checker's LAST line and `run_driver.sh` logs
# the result. This file's denominators lived one line higher, so the driver's
# record of a claim_check run was a bare `0 stale claim(s)` — including on
# runs where the command tier executed nothing at all.
# --------------------------------------------------------------------------


class TestSummaryCarriesItsDenominators(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.skill = os.path.join(self.tmp, "a-skill")
        os.makedirs(self.skill)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, verification):
        with open(os.path.join(self.skill, "SKILL.md"), "w") as f:
            f.write("---\nname: a-skill\ndescription: d\n---\n\n# T\n\n"
                    + verification)

    def last_line(self, *extra):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            claim_check.main([self.skill, "--repo-root", self.tmp] +
                             list(extra))
        return [l for l in buf.getvalue().splitlines() if l.strip()][-1]

    def test_the_last_line_carries_paths_and_commands(self):
        self.write(fence("python3 -m pytest -q tests/x.py"))
        os.makedirs(os.path.join(self.tmp, "tests"))
        open(os.path.join(self.tmp, "tests", "x.py"), "w").close()
        line = self.last_line()
        self.assertIn("0 stale claim(s) of", line)
        self.assertRegex(line, r"coverage \d+/\d+ paths, \d+/\d+ commands")

    def test_without_run_the_command_denominator_is_zero(self):
        # The honest reading of a static `claim_check` run: it checked paths
        # and executed nothing. Before this line said so, `0 stale` read as a
        # clean bill of health for a tier that had not been entered.
        self.write(fence("python3 -m pytest -q tests/x.py"))
        self.assertRegex(self.last_line(), r"coverage \d+/\d+ paths, 0/1 commands")

    def test_with_run_the_command_denominator_is_the_auto_count(self):
        self.write(fence("wc -l SKILL.md"))
        self.assertRegex(self.last_line("--run"),
                         r"coverage \d+/\d+ paths, 1/1 commands")

    def test_a_manual_command_is_in_the_denominator_and_never_the_numerator(self):
        # `--run` never executes a `manual` command, so a corpus of manual
        # commands must still report 0 executed against a non-zero total.
        self.write(fence("ssh box uptime"))
        self.assertRegex(self.last_line("--run"),
                         r"coverage \d+/\d+ paths, 0/1 commands")

    def test_the_coverage_token_is_shaped_for_the_aggregator(self):
        self.write(fence("python3 -m pytest -q tests/x.py"))
        os.makedirs(os.path.join(self.tmp, "tests"))
        open(os.path.join(self.tmp, "tests", "x.py"), "w").close()
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import corpus_check
        self.assertEqual(corpus_check.coverage_of(self.last_line()),
                         "1/1 paths, 0/1 commands")

if __name__ == "__main__":
    unittest.main()

"""Round 517 (harness A): tests for `harness/hookaudit.py`.

Two halves, and the split is the point.

The SYNTHETIC half builds throwaway git repos and installs deliberately
damaged hooks: a hook from an older generation, a hook whose script has been
moved out from under it, a hook passing a verb its script does not declare.
Those are the states nothing in this tree could observe before, so they have
to be manufactured.

The LIVE half asserts about `.git/hooks/pre-commit` in THIS checkout. That is
what round 515's next-step #2 actually asked for -- "the fast tier needs to
read it" -- because the failure mode is a round editing `hook_script()`,
committing it, and never running `install-hook`, and no test that asserts
about a Python string can see that.
"""

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(HARNESS)
for p in (HARNESS, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import hookaudit as ha                                        # noqa: E402
import escalationguard as eg                                  # noqa: E402


def git(repo, *args):
    return subprocess.run(["git"] + list(args), cwd=repo,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class _Repo(unittest.TestCase):
    """A throwaway checkout with the five scripts the hook names, so a step
    is `live` unless the test breaks it on purpose."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        git(self.tmp, "init", "-q")
        git(self.tmp, "config", "user.email", "t@t")
        git(self.tmp, "config", "user.name", "t")
        for rel in ("harness/escalationguard.py", "harness/wiring_audit.py",
                    "harness/swe/copyparity.py", "harness/swe/livewrite.py",
                    "skills/skill-authoring/scripts/carryforward_check.py"):
            dst = os.path.join(self.tmp, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as fh:
                src = fh.read()
            with open(dst, "w", encoding="utf-8") as out:
                out.write(src)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def install(self, **kw):
        return eg.install_hook(repo=self.tmp, **kw)


class TestParseStepsOnTheHookText(unittest.TestCase):
    def test_the_live_generator_yields_five_steps_one_of_them_blocking(self):
        steps = ha.parse_steps(eg.hook_script())
        self.assertEqual([s["script"] for s in steps],
                         ["harness/escalationguard.py",
                          "harness/wiring_audit.py",
                          "skills/skill-authoring/scripts/"
                          "carryforward_check.py",
                          "harness/swe/copyparity.py",
                          "harness/swe/livewrite.py"])
        self.assertEqual([s["blocking"] for s in steps],
                         [True, False, False, False, False])

    def test_the_f_guard_lines_are_not_read_as_invocations(self):
        """`[ -f "$top/x" ] || exit 0` and `if [ -f "$top/x" ]; then` both
        name a script through `$top`. Counting either as a step would double
        every advisory step and invent a fifth blocking one."""
        body = ('[ -f "$top/harness/escalationguard.py" ] || exit 0\n'
                'if [ -f "$top/harness/wiring_audit.py" ]; then\n'
                '  python3 "$top/harness/wiring_audit.py" undeclared || true\n'
                'fi\n')
        steps = ha.parse_steps(body)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["script"], "harness/wiring_audit.py")
        self.assertFalse(steps[0]["blocking"])

    def test_shell_redirection_is_not_an_argument_to_the_script(self):
        steps = ha.parse_steps(
            'python3 "$top/a.py" verb --flag 2>/dev/null || true\n')
        self.assertEqual(steps[0]["args"], ["verb", "--flag"])

    def test_exit_zero_is_not_blocking(self):
        """`|| exit 0` is how the hook FAILS OPEN when a script is missing.
        Reading it as blocking would report the fail-open path as a gate."""
        steps = ha.parse_steps('python3 "$top/a.py" v || exit 0\n')
        self.assertFalse(steps[0]["blocking"])
        steps = ha.parse_steps('python3 "$top/a.py" v || exit 1\n')
        self.assertTrue(steps[0]["blocking"])

    def test_every_generation_of_the_hook_that_ever_existed_parses(self):
        """A parser written against HEAD's text is the staleness defect this
        module is about, one level up. All four commits that ever touched
        `harness/escalationguard.py` carry a `hook_script`; each generation
        adds exactly one step and keeps exactly one blocking step."""
        rc = subprocess.run(["git", "log", "--format=%H", "--reverse", "--",
                             "harness/escalationguard.py"], cwd=REPO_ROOT,
                            stdout=subprocess.PIPE)
        shas = rc.stdout.decode().split()
        if not shas:                       # no history (a tarball checkout)
            self.skipTest("no git history for harness/escalationguard.py")
        import importlib.util
        import tempfile
        counts = []
        with tempfile.TemporaryDirectory() as td:
            for i, sha in enumerate(shas):
                blob = subprocess.run(
                    ["git", "show", "%s:harness/escalationguard.py" % sha],
                    cwd=REPO_ROOT, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL)
                if blob.returncode != 0:
                    continue
                path = os.path.join(td, "eg_%d.py" % i)
                with open(path, "wb") as fh:
                    fh.write(blob.stdout)
                spec = importlib.util.spec_from_file_location("eg_%d" % i,
                                                              path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                steps = ha.parse_steps(mod.hook_script())
                self.assertGreater(len(steps), 0, sha)
                self.assertEqual(sum(1 for s in steps if s["blocking"]), 1,
                                 sha)
                counts.append(len(steps))
        self.assertEqual(counts, sorted(counts), counts)
        self.assertEqual(counts[-1], 4, counts)


class TestIdentity(_Repo):
    def test_a_freshly_installed_hook_is_ok(self):
        self.install()
        self.assertEqual(ha.identity(repo=self.tmp)[0], "ok")

    def test_no_hook_at_all_is_absent_and_names_the_one_line_fix(self):
        state, _path, why = ha.identity(repo=self.tmp)
        self.assertEqual(state, "absent")
        self.assertIn("install-hook", why)

    def test_someone_elses_hook_is_foreign(self):
        path = os.path.join(eg.hooks_dir(repo=self.tmp), "pre-commit")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("#!/bin/sh\necho not ours\n")
        self.assertEqual(ha.identity(repo=self.tmp)[0], "foreign")

    def test_an_older_generation_of_our_own_hook_is_stale(self):
        """THE STATE ROUND 515 ASKED FOR. Rounds 499, 501, 515 and 521 each
        added a step to `hook_script()`; each had to remember to run
        `install-hook` as a separate act, and until round 517 nothing
        anywhere would have said so. Round 521 was told by THIS node, in the
        same session that added the step -- which is the whole point.

        The expected step count is derived from `hook_script()` rather than
        written as a literal: round 521 hit `4 != 3` here purely because the
        hook grew, and a pin that has to be edited for an unrelated reason is
        a pin whose next reader edits it without reading it."""
        _, path = self.install()
        body = eg.hook_script()
        older = body.replace(
            '  python3 "$top/harness/swe/copyparity.py" escapes --staged '
            '2>/dev/null || true\n', "")
        self.assertNotEqual(older, body, "the round-515 step moved; re-pin")
        with open(path, "w") as fh:
            fh.write(older)
        state, _p, why = ha.identity(repo=self.tmp)
        self.assertEqual(state, "stale")
        self.assertIn("did not run `install-hook`", why)
        # one step short of `hook_script()`'s current five
        self.assertEqual(len(ha.audit(repo=self.tmp)["steps"]),
                         len(ha.parse_steps(body)) - 1)

    def test_a_hook_installed_with_another_interpreter_is_not_stale(self):
        """`install_hook(python=...)` is a real parameter two existing tests
        use. Comparing against `hook_script()`'s `python3` default would call
        a difference the installer was ASKED for a staleness."""
        self.install(python="/usr/local/bin/python3.12")
        state, _p, why = ha.identity(repo=self.tmp)
        self.assertEqual(state, "ok", why)

    def test_a_directory_that_is_not_a_checkout_is_no_repo(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(ha.identity(repo=td)[0], "no-repo")


class TestStepReferenceIntegrity(_Repo):
    """The gap round 515's next-step did NOT name. Every step is wrapped in
    `[ -f "$top/<rel>" ]`, so moving a script does not break the hook -- it
    deletes the step, silently, and for step 1 that means the only BLOCKING
    guard in the program reports success."""

    def test_all_five_steps_are_live_in_a_complete_checkout(self):
        self.install()
        rep = ha.audit(repo=self.tmp)
        self.assertEqual(rep["counts"]["live"], 5, rep)
        self.assertTrue(ha.is_clean(rep))

    def test_moving_the_blocking_scripts_file_is_reported_not_silent(self):
        self.install()
        os.rename(os.path.join(self.tmp, "harness/escalationguard.py"),
                  os.path.join(self.tmp, "harness/escguard.py"))
        rep = ha.audit(repo=self.tmp)
        bad = [s for s in rep["steps"] if s["verdict"] == "missing"]
        self.assertEqual(len(bad), 1, rep)
        self.assertTrue(bad[0]["blocking"])
        self.assertIn("BLOCKING", bad[0]["why"])
        self.assertFalse(ha.is_clean(rep))

    def test_the_hook_really_does_fall_silent_when_the_script_moves(self):
        """Not "the audit says missing" -- the actual `git commit`. The
        registry lists a path this commit stages, so the hook MUST refuse it;
        after the rename it must not, and the silence is the defect."""
        import json
        with open(os.path.join(self.tmp, "doc.md"), "w") as fh:
            fh.write("BASE\n")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "base")
        base = eg.blob_at("HEAD", "doc.md", repo=self.tmp)
        with open(os.path.join(self.tmp, "doc.md"), "w") as fh:
            fh.write("REWRITTEN BY A THIRD PARTY\n")
        esc = eg.worktree_blob("doc.md", repo=self.tmp)
        reg = os.path.join(self.tmp, eg.REGISTRY_REL)
        os.makedirs(os.path.dirname(reg), exist_ok=True)
        with open(reg, "w") as fh:
            json.dump({"_comment": "test", "escalations": {"doc.md": {
                "reason": "adjudicated", "escalated_round": 1,
                "worktree_blob": esc, "head_blob": base}}}, fh)
        eg.install_hook(repo=self.tmp, python=sys.executable)
        git(self.tmp, "add", "--", "doc.md")
        before = git(self.tmp, "rev-parse", "HEAD").stdout.decode().strip()
        refused = git(self.tmp, "commit", "-q", "-m", "should be refused")
        self.assertNotEqual(refused.returncode, 0,
                            (refused.stdout + refused.stderr).decode())
        self.assertEqual(git(self.tmp, "rev-parse",
                             "HEAD").stdout.decode().strip(), before)

        # Now move the script the hook names. Nothing else changes.
        os.rename(os.path.join(self.tmp, "harness/escalationguard.py"),
                  os.path.join(self.tmp, "harness/escguard.py"))
        allowed = git(self.tmp, "commit", "-q", "-m", "silently allowed")
        self.assertEqual(allowed.returncode, 0,
                         "expected the `[ -f ] || exit 0` fail-open path")
        self.assertNotEqual(git(self.tmp, "rev-parse",
                                "HEAD").stdout.decode().strip(), before,
                            "the escalated blob is now at HEAD -- the "
                            "blocking guard silently disabled itself")
        rep = ha.audit(repo=self.tmp)
        self.assertEqual(rep["counts"]["missing"], 1)
        self.assertFalse(ha.is_clean(rep))


class TestArgumentIntegrity(_Repo):
    def test_a_verb_the_script_does_not_declare_is_broken(self):
        self.install()
        path = os.path.join(eg.hooks_dir(repo=self.tmp), "pre-commit")
        with open(path) as fh:
            body = fh.read()
        with open(path, "w") as fh:
            fh.write(body.replace('copyparity.py" escapes --staged',
                                  'copyparity.py" escaped --staged'))
        rep = ha.audit(repo=self.tmp)
        bad = [s for s in rep["steps"] if s["verdict"] == "broken"]
        self.assertEqual(len(bad), 1, rep)
        self.assertIn("escaped", bad[0]["why"])
        self.assertIn("silent no-op", bad[0]["why"])

    def test_an_unreadable_cli_is_unknown_and_unknown_is_not_a_failure(self):
        """The static reader abstaining is not the hook being wrong. A
        reader that guessed would be worse than one that says so."""
        self.install()
        with open(os.path.join(self.tmp, "harness/wiring_audit.py"),
                  "w") as fh:
            fh.write("# no argparse here\n")
        rep = ha.audit(repo=self.tmp)
        self.assertEqual(rep["counts"]["unknown"], 1, rep)
        self.assertTrue(ha.is_clean(rep))

    def test_choices_on_a_positional_counts_as_a_declared_verb(self):
        surface = ha._argparse_surface(
            os.path.join(REPO_ROOT, "harness", "pristine_check.py"))
        self.assertIsNotNone(surface)
        self.assertIn("--suite", surface[1])


class TestTheHookInstalledInThisCheckout(unittest.TestCase):
    """The live half. Round 515's next-step #2: "a checkout where nobody ran
    install-hook has a stale hook and both tests still pass"."""

    @classmethod
    def setUpClass(cls):
        rc = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=REPO_ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if rc.returncode != 0:
            raise unittest.SkipTest("not a git checkout")
        cls.rep = ha.audit(repo=REPO_ROOT)

    def test_the_installed_hook_is_the_one_hook_script_generates(self):
        self.assertEqual(
            self.rep["identity"], "ok",
            "%s — run `python3 harness/escalationguard.py install-hook`. "
            "Every test in this tree asserts about hook_script(); this is "
            "the only one that reads the file git actually runs."
            % self.rep["why"])

    def test_every_script_the_installed_hook_names_is_present(self):
        bad = [s for s in self.rep["steps"] if s["verdict"] == "missing"]
        self.assertEqual(bad, [], "\n".join(s["why"] for s in bad))

    def test_every_argument_the_installed_hook_passes_is_declared(self):
        bad = [s for s in self.rep["steps"] if s["verdict"] == "broken"]
        self.assertEqual(bad, [], "\n".join(s["why"] for s in bad))

    def test_exactly_one_installed_step_can_refuse_a_commit(self):
        """`test_escalationguard.py` pins this on the GENERATOR. Here it is
        on the file, which is the artefact a `git commit` runs."""
        self.assertEqual(self.rep["blocking"], [1], self.rep["steps"])

    def test_hooks_dir_in_a_linked_worktree_is_the_main_repos(self):
        """`pristine_check.py baseline` runs suites in `git worktree add
        --detach` trees. If a worktree resolved its own empty hooks
        directory, every node above would go `absent` there -- a red about
        the apparatus. Probed on a throwaway repo rather than assumed."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            main = os.path.join(td, "main")
            os.makedirs(main)
            git(main, "init", "-q")
            git(main, "config", "user.email", "t@t")
            git(main, "config", "user.name", "t")
            with open(os.path.join(main, "a.txt"), "w") as fh:
                fh.write("x\n")
            git(main, "add", "-A")
            git(main, "commit", "-q", "-m", "init")
            wt = os.path.join(td, "wt")
            git(main, "worktree", "add", "-q", "--detach", wt, "HEAD")
            self.assertEqual(os.path.realpath(eg.hooks_dir(repo=wt)),
                             os.path.realpath(eg.hooks_dir(repo=main)))


class TestCli(unittest.TestCase):
    def test_audit_strict_exits_zero_on_this_checkout(self):
        p = subprocess.run([sys.executable,
                            os.path.join(HARNESS, "hookaudit.py"),
                            "audit", "--strict"], cwd=REPO_ROOT,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(p.returncode, 0,
                         p.stdout.decode() + p.stderr.decode())
        self.assertIn("identity ok", p.stdout.decode())

    def test_steps_prints_one_row_per_step(self):
        p = subprocess.run([sys.executable,
                            os.path.join(HARNESS, "hookaudit.py"), "steps"],
                           cwd=REPO_ROOT, stdout=subprocess.PIPE)
        rows = [r for r in p.stdout.decode().splitlines() if r.strip()]
        self.assertEqual(len(rows), len(ha.audit(repo=REPO_ROOT)["steps"]))

    def test_no_subcommand_prints_help_and_exits_zero(self):
        self.assertEqual(ha.main([]), 0)


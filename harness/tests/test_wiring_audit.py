"""Round 415 (harness A) — tests for `harness/wiring_audit.py`.

Two halves, deliberately.

The UNIT half builds a throwaway git repo per test and asserts one rule each.
Every one of them exists because the rule it pins was got wrong first, live,
on this tree: the directory-edge runner gate (the driver's own `mkdir -p
"$WS/state"` pulled 107 files in), the docstring/AST ordering (320 of 420
tracked `.py` files fail to parse after comment-blanking, so every `ast` pass
was silently returning `[]`), the ancestor-relative import rule (`from swe
import guardpin` reported round 413's newest instrument as an orphan), and
the `join`-vs-`path` edge split (three files genuinely executed by their tests
were reported as weakly reached).

The LIVE half asserts facts about THIS checkout. `test_the_registry_is_clean`
is the one the driver runs every round; the rest pin the specific defect that
motivated the file — `nuc/run_checks_fast.sh` had been reachable from
`run_driver.sh` for six rounds while three next-steps blocks asserted it had
zero references.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

_HARNESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HARNESS not in sys.path:
    sys.path.insert(0, _HARNESS)

import wiring_audit as W                                       # noqa: E402

REPO = os.path.dirname(_HARNESS)


# --------------------------------------------------------------------------
# a throwaway repo
# --------------------------------------------------------------------------

def make_repo(tmp_path, files):
    root = str(tmp_path)
    for rel, body in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def write_registry(root, **kw):
    reg = {"vendored_prefixes": [], "frozen_prefixes": [], "entry_points": {}}
    reg.update(kw)
    os.makedirs(os.path.join(root, "harness"), exist_ok=True)
    with open(os.path.join(root, "harness", "wiring-registry.json"), "w",
              encoding="utf-8") as fh:
        json.dump(reg, fh)


MAIN = '\nif __name__ == "__main__":\n    pass\n'


class TestMainGuardDetection:
    """Round 421. `is_entry_point` used a raw-text regex, which cannot tell a
    `__main__` guard from one QUOTED INSIDE A STRING. A test file that builds
    a synthetic entry-point fixture — `harness/tests/test_verb_audit.py` does
    exactly this — was thereby declared an entry point and raised a W001
    asking someone to wire a test fixture. Measured over this tree, moving to
    the AST changed the entry-point set by exactly one file (that one) and
    added none, so the fix is precise rather than a re-tiering."""

    def test_a_real_module_level_guard_counts(self):
        assert W._has_main_guard("import os\n" + MAIN)

    def test_a_guard_inside_a_string_constant_does_not(self):
        src = 'FIXTURE = """\nif __name__ == "__main__":\n    pass\n"""\n'
        assert not W._has_main_guard(src)

    def test_a_guard_nested_in_a_function_does_not(self):
        """A guard that only runs when someone calls the function does not
        make the FILE runnable."""
        src = 'def go():\n    if __name__ == "__main__":\n        pass\n'
        assert not W._has_main_guard(src)

    def test_unparseable_source_falls_back_to_the_regex(self):
        """Fail-OPEN on purpose: an over-declared entry point costs one
        registry line, an under-declared one escapes W001 entirely."""
        assert W._has_main_guard('def broken(:\n' + MAIN)

    def test_the_reversed_comparison_still_counts(self):
        assert W._has_main_guard('if "__main__" == __name__:\n    pass\n')


# --------------------------------------------------------------------------
# comment stripping
# --------------------------------------------------------------------------

class TestStripping:

    def test_a_whole_line_shell_comment_goes_and_the_line_stays(self):
        out = W.strip_shell_comments("a\n  # gone\nb\n")
        assert out.split("\n") == ["a", "", "b", ""]

    def test_shell_parameter_expansion_is_not_a_comment(self):
        # `${x#y}` and `$#` would both be destroyed by a trailing-comment
        # stripper. The docstring says this is deliberate; this pins it.
        src = 'echo "${x#pre}" "$#"\n'
        assert W.strip_shell_comments(src) == src

    def test_a_python_docstring_is_blanked_but_geometry_is_kept(self):
        src = 'def f():\n    """doc"""\n    x = "keep/me.py"\n'
        out = W.strip_python_comments(src)
        assert len(out.split("\n")) == len(src.split("\n"))
        assert "doc" not in out
        assert "keep/me.py" in out

    def test_a_python_comment_goes_and_an_ordinary_string_stays(self):
        src = 'x = "a/b.py"  # harness/other.py\n'
        out = W.strip_python_comments(src)
        assert "a/b.py" in out and "harness/other.py" not in out

    def test_blanking_a_docstring_can_make_the_source_unparseable(self):
        """The bug the AST passes were built on top of, pinned as a fact.

        320 of this repo's 420 tracked `.py` files are in this state, so an
        `ast` pass over the STRIPPED text was returning `[]` for 76% of the
        tree and nothing said so.
        """
        import ast
        src = 'def f():\n    """only a docstring"""\n'
        with pytest.raises(SyntaxError):
            ast.parse(W.strip_python_comments(src))
        tree, docs = W._parse_for_ast(src)
        assert tree is not None
        assert W._string_constants(tree, docs) == []


# --------------------------------------------------------------------------
# reference resolution
# --------------------------------------------------------------------------

class TestResolve:

    def index(self):
        return W.Index(["a/run.sh", "b/run.sh", "c/only.sh", "c/pkg/mod.py"])

    def test_a_unique_path_suffix_resolves_to_the_file(self):
        assert W.resolve_reference(self.index(), '"$WS/a/run.sh"') == \
            ("file", "a/run.sh")

    def test_a_shared_basename_is_ambiguous_and_never_an_edge(self):
        # research-state.md's own words: "a basename grep lies".
        kind, val = W.resolve_reference(self.index(), "run.sh")
        assert kind == "ambiguous"
        assert val == ["a/run.sh", "b/run.sh"]

    def test_the_longest_suffix_wins_and_does_not_fall_through(self):
        # `b/run.sh` must not degrade to the ambiguous bare `run.sh`.
        assert W.resolve_reference(self.index(), "x/y/b/run.sh") == \
            ("file", "b/run.sh")

    def test_a_directory_suffix_resolves_to_the_directory(self):
        assert W.resolve_reference(self.index(), "c/pkg") == ("dir", "c/pkg")

    def test_an_unknown_token_resolves_to_nothing(self):
        assert W.resolve_reference(self.index(), "nope/nothing.py") == \
            (None, None)


class TestModuleResolution:

    def test_a_dotted_name_resolves_against_an_ancestor_of_the_importer(self):
        cands = W.module_to_paths("swe.guardpin", "harness/tests/test_x.py")
        assert "harness/swe/guardpin.py" in cands

    def test_a_stdlib_name_asks_only_for_paths_this_repo_would_not_have(self):
        cands = W.module_to_paths("ast", "harness/tests/test_x.py")
        assert cands[0].startswith("harness/tests/")
        assert "ast.py" in cands            # only as a repo-root candidate
        assert all(c.endswith((".py",)) for c in cands)

    def test_the_nearest_ancestor_is_tried_first(self):
        cands = W.module_to_paths("m", "a/b/c.py")
        assert cands.index("a/b/m.py") < cands.index("a/m.py") < \
            cands.index("m.py")


# --------------------------------------------------------------------------
# edges
# --------------------------------------------------------------------------

class TestEdges:

    def refs(self, tmp_path, files, src):
        root = make_repo(tmp_path, files)
        idx = W.Index(W.tracked_files(root))
        return W.references(root, src, idx)

    def test_a_shell_directory_is_an_edge_only_on_a_pytest_line(self, tmp_path):
        files = {"top.sh": 'mkdir -p "$WS/data"\n',
                 "data/x.py": "x = 1\n"}
        edges, _ = self.refs(tmp_path, files, "top.sh")
        assert "data/x.py" not in edges

    def test_a_directory_argument_to_some_other_program_is_not_an_edge(
            self, tmp_path):
        """`python3 nuc/constant_audit.py audit nuc/` — the directory belongs
        to the AUDITOR, not the interpreter. A gate of "any runner token on
        the line" let this through and pulled 158 extra nodes in."""
        files = {"top.sh": 'python3 tool.py audit data/\n',
                 "tool.py": "x = 1\n", "data/x.py": "x = 1\n"}
        edges, _ = self.refs(tmp_path, files, "top.sh")
        assert "tool.py" in edges
        assert "data/x.py" not in edges

    def test_a_relative_directory_resolves_against_the_referrers_own_dir(
            self, tmp_path):
        """`languages/whence/run_tests_fast.sh` cds to its own directory and
        then says `pytest ... tests/`. Resolved globally, the bare token
        `tests` is ambiguous across five `tests/` dirs and yields nothing."""
        files = {"a/go.sh": 'python3 -m pytest -q tests/\n',
                 "a/tests/test_x.py": "x = 1\n",
                 "b/tests/test_y.py": "x = 1\n"}
        edges, _ = self.refs(tmp_path, files, "a/go.sh")
        assert "a/tests/test_x.py" in edges
        assert "b/tests/test_y.py" not in edges

    def test_a_shell_directory_handed_to_pytest_is_an_edge(self, tmp_path):
        files = {"top.sh": 'python3 -m pytest -q data/\n',
                 "data/x.py": "x = 1\n"}
        edges, _ = self.refs(tmp_path, files, "top.sh")
        assert edges["data/x.py"][1] == "dir"

    def test_a_python_line_mentioning_a_directory_is_never_a_dir_edge(
            self, tmp_path):
        # `xref_check.py`'s FROZEN_PREFIXES = ("state/swe", ...) — a list of
        # directories to SKIP — read as a list to run.
        files = {"top.py": 'import subprocess\nSKIP = ("data",)\n' + MAIN,
                 "data/x.py": "x = 1\n"}
        edges, _ = self.refs(tmp_path, files, "top.py")
        assert "data/x.py" not in edges

    def test_a_join_inside_a_pytest_argv_is_a_dir_edge(self, tmp_path):
        # corpus_check.py: ["-m", "pytest", "-q", os.path.join(root, ...)]
        files = {"top.py": ('import os, subprocess\n'
                            'argv = ["-m", "pytest", "-q",\n'
                            '        os.path.join(ROOT, "data")]\n'
                            'subprocess.run(argv)\n' + MAIN),
                 "data/x.py": "x = 1\n"}
        edges, _ = self.refs(tmp_path, files, "top.py")
        assert edges["data/x.py"][1] == "dir"

    def test_a_join_that_is_not_a_pytest_argument_is_not_a_dir_edge(
            self, tmp_path):
        """`nuc/tests/test_constant_audit.py` imports pytest AND shells out,
        and its `os.path.join(ROOT, "nuc")` is the AUDITED directory. A
        module-level "does this file mention pytest" gate read it as a test
        root and turned six correct `manual` declarations into errors."""
        files = {"top.py": ('import os, subprocess, pytest\n'
                            'p = os.path.join(ROOT, "data")\n'
                            'subprocess.run(["audit", p])\n' + MAIN),
                 "data/x.py": "x = 1\n"}
        edges, _ = self.refs(tmp_path, files, "top.py")
        assert "data/x.py" not in edges

    def test_a_bare_python_line_naming_a_directory_never_runs_it(
            self, tmp_path):
        """One rule for python directory edges, not two. A module-level
        "mentions pytest" gate was tried first and dropped; the pytest
        ARGUMENT LIST is the whole test, so a directory named anywhere else
        in the file — a scan root, an exclusion list — cannot become one."""
        files = {"top.py": ('import os, subprocess, pytest\n'
                            'ROOTS = ["data"]\n'
                            'p = os.path.join(R, "data")\n'
                            'subprocess.run(["pytest"])\n' + MAIN),
                 "data/x.py": "x = 1\n"}
        edges, _ = self.refs(tmp_path, files, "top.py")
        assert "data/x.py" not in edges

    def test_a_dot_slash_script_is_an_edge(self, tmp_path):
        # `CLAUDE_CMD="${DRIVER_CLAUDE_CMD:-./claude-wrapper.sh}"` — the one
        # script the driver launches per round.
        files = {"top.sh": 'C="${X:-./wrap.sh}"\n', "wrap.sh": "echo hi\n"}
        edges, _ = self.refs(tmp_path, files, "top.sh")
        assert "wrap.sh" in edges

    def test_an_import_outranks_a_textual_mention(self, tmp_path):
        files = {"top.py": ('import subprocess\n'
                            'CMD = "python3 pkg/mod.py"\n'
                            'import pkg.mod\n' + MAIN),
                 "pkg/__init__.py": "", "pkg/mod.py": "x = 1\n"}
        edges, _ = self.refs(tmp_path, files, "top.py")
        assert edges["pkg/mod.py"][1] == "import"

    def test_pathlib_division_counts_as_path_construction(self, tmp_path):
        files = {"top.py": ('import subprocess\nfrom pathlib import Path\n'
                            'p = Path(__file__).parent / "tool.py"\n' + MAIN),
                 "tool.py": "x = 1\n"}
        edges, _ = self.refs(tmp_path, files, "top.py")
        assert edges["tool.py"][1] == "join"

    def test_a_bare_command_string_is_only_a_weak_path_edge(self, tmp_path):
        files = {"top.py": 'CMD = "python3 tool.py"\n' + MAIN,
                 "tool.py": "x = 1\n"}
        edges, _ = self.refs(tmp_path, files, "top.py")
        assert edges["tool.py"][1] == "path"


# --------------------------------------------------------------------------
# closure
# --------------------------------------------------------------------------

class TestClosure:

    def test_transitive_reach_and_the_route_that_explains_it(self, tmp_path):
        files = {"run_driver.sh": 'bash "$WS/a/one.sh"\n',
                 "a/one.sh": 'python3 -m pytest -q a/tests/\n',
                 "a/tests/test_x.py": "import subprocess\nimport a.tool\n",
                 "a/__init__.py": "", "a/tool.py": "x = 1\n"}
        root = make_repo(tmp_path, files)
        g = W.Graph(root)
        assert "a/tool.py" in g.closure()
        chain = g.why("a/tool.py")
        assert [c[0] for c in chain] == ["run_driver.sh", "a/one.sh",
                                         "a/tests/test_x.py"]

    def test_best_incoming_prefers_the_shallower_source(self, tmp_path):
        files = {"run_driver.sh": 'bash "$WS/tool.sh"\n'
                                  'python3 -m pytest -q t/\n',
                 "tool.sh": "echo hi\n",
                 "t/test_x.py": 'CMD = "bash tool.sh"\n'}
        root = make_repo(tmp_path, files)
        g = W.Graph(root)
        assert g.best_incoming("tool.sh")[0] == "run_driver.sh"


# --------------------------------------------------------------------------
# the registry
# --------------------------------------------------------------------------

class TestAudit:

    def base(self, tmp_path, extra=None):
        files = {"run_driver.sh": 'bash "$WS/a/one.sh"\n',
                 "a/one.sh": "echo hi\n",
                 "b/off.sh": "echo hi\n",
                 "harness/keep.txt": "x\n"}
        files.update(extra or {})
        return make_repo(tmp_path, files)

    def test_an_undeclared_entry_point_is_an_error(self, tmp_path):
        root = self.base(tmp_path)
        write_registry(root)
        codes = {f[0] for f in W.audit(root)["findings"]}
        assert "W001" in codes

    def test_declared_wired_but_unreachable_is_W002(self, tmp_path):
        root = self.base(tmp_path)
        write_registry(root, entry_points={
            "run_driver.sh": {"status": "wired"},
            "a/one.sh": {"status": "wired"},
            "b/off.sh": {"status": "wired"}})
        assert ("W002", "b/off.sh") in [(f[0], f[1])
                                        for f in W.audit(root)["findings"]]

    def test_declared_unwired_but_reachable_is_W003(self, tmp_path):
        """The round-409 shape, and the reason this file exists."""
        root = self.base(tmp_path)
        write_registry(root, entry_points={
            "run_driver.sh": {"status": "wired"},
            "a/one.sh": {"status": "unwired", "owner": "x", "reason": "y",
                         "since_round": 415},
            "b/off.sh": {"status": "manual", "owner": "x", "reason": "y"}})
        hits = [f for f in W.audit(root)["findings"] if f[0] == "W003"]
        assert [h[1] for h in hits] == ["a/one.sh"]

    def test_a_registry_path_that_does_not_exist_is_W004(self, tmp_path):
        root = self.base(tmp_path)
        write_registry(root, entry_points={
            "run_driver.sh": {"status": "wired"},
            "a/one.sh": {"status": "wired"},
            "b/off.sh": {"status": "manual", "owner": "x", "reason": "y"},
            "gone/away.sh": {"status": "manual", "owner": "x", "reason": "y"}})
        hits = [f for f in W.audit(root)["findings"] if f[0] == "W004"]
        assert [h[1] for h in hits] == ["gone/away.sh"]

    def test_an_exclusion_prefix_matching_nothing_is_W004(self, tmp_path):
        root = self.base(tmp_path)
        write_registry(root,
                       frozen_prefixes=[{"prefix": "vanished/",
                                         "reason": "r"}],
                       entry_points={
                           "run_driver.sh": {"status": "wired"},
                           "a/one.sh": {"status": "wired"},
                           "b/off.sh": {"status": "manual", "owner": "x",
                                        "reason": "y"}})
        hits = [f for f in W.audit(root)["findings"] if f[0] == "W004"]
        assert [h[1] for h in hits] == ["vanished/"]

    def test_an_excluded_prefix_needs_no_declaration(self, tmp_path):
        root = self.base(tmp_path, {"vend/x.sh": "echo\n"})
        write_registry(root,
                       vendored_prefixes=[{"prefix": "vend/", "reason": "r"}],
                       entry_points={
                           "run_driver.sh": {"status": "wired"},
                           "a/one.sh": {"status": "wired"},
                           "b/off.sh": {"status": "manual", "owner": "x",
                                        "reason": "y"}})
        assert W.audit(root)["findings"] == []

    def test_an_unwired_debt_older_than_a_rotation_warns_but_does_not_error(
            self, tmp_path):
        root = self.base(tmp_path)
        os.makedirs(os.path.join(root, "state"), exist_ok=True)
        with open(os.path.join(root, "state", "round_counter"), "w") as fh:
            fh.write("421\n")
        write_registry(root, entry_points={
            "run_driver.sh": {"status": "wired"},
            "a/one.sh": {"status": "wired"},
            "b/off.sh": {"status": "unwired", "owner": "x", "reason": "y",
                         "since_round": 415}})
        findings = W.audit(root)["findings"]
        assert [f[0] for f in findings] == ["W005"]
        assert not [f for f in findings if f[0] in W.ERROR_CODES]

    def test_manual_never_raises_the_rotation_warning(self, tmp_path):
        root = self.base(tmp_path)
        os.makedirs(os.path.join(root, "state"), exist_ok=True)
        with open(os.path.join(root, "state", "round_counter"), "w") as fh:
            fh.write("999\n")
        write_registry(root, entry_points={
            "run_driver.sh": {"status": "wired"},
            "a/one.sh": {"status": "wired"},
            "b/off.sh": {"status": "manual", "owner": "x", "reason": "y"}})
        assert W.audit(root)["findings"] == []

    def test_reached_only_as_text_inside_a_test_is_W006_not_W003(
            self, tmp_path):
        """`test_claim_check.py` names `python3 bench_elision.py` in order to
        assert that the command is REFUSED. Being named in a refusal is not
        being run, so `wired` gets a warning and `manual` gets no error."""
        files = {"run_driver.sh": 'python3 -m pytest -q t/\n',
                 "t/test_x.py": 'CMD = "python3 bench.py"\n',
                 "bench.py": "x = 1\n" + MAIN}
        root = make_repo(tmp_path, files)
        write_registry(root, entry_points={
            "run_driver.sh": {"status": "wired"},
            "t/test_x.py": {"status": "wired"},
            "bench.py": {"status": "wired"}})
        codes = [f[0] for f in W.audit(root)["findings"]]
        assert codes == ["W006"]

        write_registry(root, entry_points={
            "run_driver.sh": {"status": "wired"},
            "t/test_x.py": {"status": "wired"},
            "bench.py": {"status": "manual", "owner": "x", "reason": "y"}})
        assert W.audit(root)["findings"] == []


# --------------------------------------------------------------------------
# refs
# --------------------------------------------------------------------------

class TestRefs:

    def test_it_separates_a_comment_mention_from_a_real_invocation(
            self, tmp_path):
        files = {"run_driver.sh": ('# see a/one.sh for the reason\n'
                                   'bash "$WS/a/one.sh"\n'),
                 "a/one.sh": "echo hi\n"}
        root = make_repo(tmp_path, files)
        r = W.refs(root, "a/one.sh", "run_driver.sh")
        assert (r["raw"], r["code"]) == (2, 1)
        assert r["code_lines"] == [2]

    def test_an_ambiguous_target_is_refused_rather_than_guessed(self,
                                                               tmp_path):
        files = {"run_driver.sh": "echo\n", "a/run.sh": "echo\n",
                 "b/run.sh": "echo\n"}
        root = make_repo(tmp_path, files)
        r = W.refs(root, "run.sh", "run_driver.sh")
        assert r["error"] == "ambiguous"
        assert r["candidates"] == ["a/run.sh", "b/run.sh"]

    def test_expect_scores_a_written_claim(self, tmp_path):
        files = {"run_driver.sh": 'bash "$WS/a/one.sh"\n', "a/one.sh": "hi\n"}
        root = make_repo(tmp_path, files)
        argv = ["--repo-root", root, "refs", "a/one.sh", "--in",
                "run_driver.sh", "--expect", "0"]
        assert W.main(argv) == 1
        argv[-1] = "1"
        assert W.main(argv) == 0


# --------------------------------------------------------------------------
# this checkout
# --------------------------------------------------------------------------

class TestThisTree:

    def test_the_registry_is_clean(self):
        """The guard the driver runs every round.

        A newly built script is a W001 error here on the very next round,
        which is the whole point: `nuc/run_checks_fast.sh` was built by round
        388, wired by round 409, and the six rounds in between had no
        mechanism that could say so.
        """
        res = W.audit(REPO)
        errs = [f for f in res["findings"] if f[0] in W.ERROR_CODES]
        assert errs == [], errs

    def test_every_entry_point_in_the_tree_is_declared(self):
        res = W.audit(REPO)
        reg = W.load_registry(REPO)
        undeclared = [p for p in res["entry_points"]
                      if p not in reg["entry_points"]]
        assert undeclared == []

    def test_all_four_health_checks_are_reachable_from_the_driver(self):
        g = W.Graph(REPO)
        reached = g.closure()
        for script in ("harness/run_tests_fast.sh",
                       "languages/whence/run_tests_fast.sh",
                       "skills/run_checks_fast.sh",
                       "nuc/run_checks_fast.sh"):
            assert script in reached, script

    def test_the_nuc_health_check_reference_claim_is_re_derivable(self):
        """Three next-steps blocks asserted `0 references in run_driver.sh`.

        This pins the number so the claim cannot be re-asserted silently
        again — and pins the DISTINCTION that made it easy to get wrong: one
        of the two mentions is a comment, and only one is the wiring.
        """
        r = W.refs(REPO, "nuc/run_checks_fast.sh", "run_driver.sh")
        assert r["raw"] >= 2
        assert r["code"] >= 1
        assert r["code_lines"] and r["code_lines"][0] > 500

    def test_the_driver_reaches_its_own_wrapper(self):
        assert "claude-wrapper.sh" in W.Graph(REPO).closure()

    def test_a_basename_alone_never_identifies_a_health_check(self):
        """The rule research-state.md stated in prose, executed."""
        idx = W.Index(W.tracked_files(REPO))
        for base in ("run_tests_fast.sh", "run_checks_fast.sh"):
            kind, val = W.resolve_reference(idx, base)
            assert kind == "ambiguous", (base, kind, val)
            assert len(val) == 2

    def test_the_declared_debts_are_exactly_the_one_still_owed(self):
        """`python3 -m swe.loop` has no caller anywhere in the tree.

        Pinned as the registry's single `unwired` entry so that wiring it —
        or deciding it is `manual` — is a deliberate edit and not a drift.

        Round 415 declared TWO. Round 416 (language C) discharged the other,
        `languages/whence/nuc_scripting/ncs_engine.py`, by DELETING it —
        one of the three exits W005 offers. It was a second, weaker
        implementation of the task-script DSL that `nuc/taskscript/` already
        ships (E5, done round 124, plus
        `skills/preflight-priced-task-scripts/`), it ran its input through
        `subprocess.run(..., shell=True)`, and round 172 recommended
        `delete-as-dead-end` 244 rounds before it went. It is in git; the
        commit that removed it is where to look.
        """
        reg = W.load_registry(REPO)
        debts = sorted(p for p, e in reg["entry_points"].items()
                       if e["status"] == "unwired")
        # Round 419 (SWE-loop D, the owning track) discharged the last one by
        # WIRING it: `harness/tests/test_swe_loop_cli.py` imports `swe.loop`
        # and drives `main()` end to end. Both of round 415's declared debts
        # are now closed, by the two different exits W005 offers — 416/418 by
        # deletion, 419 by a caller. An EMPTY list is the assertion: a new
        # `unwired` entry has to be a deliberate edit here too, in the same
        # way wiring one was.
        #
        # Round 475 (harness A) makes that deliberate edit, for the first
        # time since round 419. `bank_audit.py` was declared `wired` by round
        # 473 on the strength of corpus_check.py's DESCRIPTION of its
        # `unit_tests` checker ("pytest over skills/*/scripts/test_*.py"),
        # not its argv, which is pytest over exactly two directories --
        # skills/skill-authoring/scripts and
        # skills/session-inheritance-audit/scripts. prediction-banking is not
        # one of them, so round 471's 19-test test_bank_audit.py is scheduled
        # by nothing and W002 had been an ERROR since 654a553. `unwired`
        # rather than `manual` because the program intends to automate it
        # (round 471's next-step 1 asks for exactly that), so W005 should
        # start counting the rotations. Discharging it is skills(B)'s call:
        # add the directory to `unit_tests`, or schedule `bank_audit.py
        # corpus` as its own checker.
        #
        # Round 477 (skills B) TOOK the first of those two exits, and the
        # debt is closed: `skills/prediction-banking/scripts` is now one of
        # four literal directories in corpus_check.py's `unit_tests` argv,
        # so test_bank_audit.py's 19 tests run every round and the registry
        # entry flipped to `wired` with a `[dir]` edge. Back to EMPTY, the
        # same assertion round 419 left, for the same reason: a new
        # `unwired` entry must be a deliberate edit here.
        #
        # This node was RED for three rounds because of that flip -- round
        # 477's own log, round 478's, and round 479's opening run. Neither
        # the round that opened it (477, skills B) nor the round that first
        # could have seen it (478, NUC E) runs harness/tests/, which is the
        # `invisible-open` shape redattrib.py measures; round 479 (SWE-loop
        # D) both declared it in harness/crosstrack-registry.json and fixed
        # it here.
        assert debts == []
        # `Graph.closure()` is NOT the predicate W003 uses, and asserting it
        # flatly here was wrong on the tree that shipped it: `loop.py` is in
        # the raw closure (its own test file names it as text) and W003
        # deliberately defers to W006 for exactly that case — see
        # `wiring_audit.check`'s `weak_only`. This assertion now states the
        # checker's real rule, so the test and the checker agree instead of
        # contradicting each other.
        g = W.Graph(REPO)
        closure = g.closure()
        for d in debts:
            if d not in closure:
                continue
            edge = g.best_incoming(d)
            assert edge is not None and edge[2] in W.WEAK_KINDS \
                and W.is_test_file(edge[0]), (d, edge)

    def test_the_deleted_orphan_is_gone_rather_than_merely_undeclared(self):
        """Removing a registry entry and leaving the file is how an audited
        debt turns into an unaudited one. Round 416 deleted the file, so the
        check that it stays deleted is what makes the discharge real."""
        assert not os.path.exists(
            os.path.join(REPO, "languages", "whence", "nuc_scripting"))

    def test_the_cli_check_exits_zero_on_this_tree(self):
        p = subprocess.run([sys.executable, os.path.join(_HARNESS,
                                                         "wiring_audit.py"),
                            "check"], cwd=REPO, capture_output=True,
                           text=True, timeout=300)
        assert p.returncode == 0, p.stdout + p.stderr
        assert "0 error(s)" in p.stdout


# --------------------------------------------------------------------------
# Round 423 — `token_refs`, the polarity dual of `refs`.
#
# `refs` re-derives a PRESENCE claim (*X is referenced N times in Y*).
# `token_refs` re-derives an ABSENCE claim (*Y still has no X*), where X is a
# literal string rather than a path. The raw/code split is the same and
# carries the same distinction: a file that MENTIONS a token in a comment
# saying the thing does not exist yet has not thereby made it exist.
# --------------------------------------------------------------------------


class TestTokenRefs:

    def test_a_token_in_code_is_separated_from_one_in_a_comment(self, tmp_path):
        files = {"a/tool.py": ('# S009 is not implemented yet\n'
                               'CODE = "S009"\n')}
        root = make_repo(tmp_path, files)
        r = W.token_refs(root, "S009", "a/tool.py")
        assert (r["raw"], r["code"]) == (2, 1)
        assert r["code_lines"] == [2]

    def test_a_docstring_mention_is_prose_not_code(self, tmp_path):
        # `strip_python_comments` blanks a string that BEGINS a logical line.
        # This is the shape the real instance had: `state_claim_check.py`
        # documents S009 in a 120-line module docstring and emits it from
        # one `Finding(...)` call.
        files = {"a/tool.py": ('"""S009 -- what this module does."""\n'
                               'def f():\n'
                               '    return Finding("S009")\n')}
        root = make_repo(tmp_path, files)
        r = W.token_refs(root, "S009", "a/tool.py")
        assert (r["raw"], r["code"]) == (2, 1)
        assert r["code_lines"] == [3]

    def test_an_absent_token_is_zero_and_zero(self, tmp_path):
        files = {"a/tool.py": "x = 1\n"}
        root = make_repo(tmp_path, files)
        r = W.token_refs(root, "S009", "a/tool.py")
        assert (r["raw"], r["code"]) == (0, 0)

    def test_the_boundary_is_not_a_substring_match(self, tmp_path):
        # `\b` would report `--cap` present in `--capture`, because `-` is a
        # word boundary to `re`. Both halves of this matter: round 412's
        # blocked `--cap 196` and round 400's `--capture` are real, live,
        # co-resident tokens in this corpus.
        files = {"a/tool.py": 'x = "S0091"\ny = "--capture"\n'}
        root = make_repo(tmp_path, files)
        assert W.token_refs(root, "S009", "a/tool.py")["raw"] == 0
        assert W.token_refs(root, "--cap", "a/tool.py")["raw"] == 0
        assert W.token_refs(root, "--capture", "a/tool.py")["raw"] == 1

    def test_a_basename_resolves_the_way_refs_resolves_one(self, tmp_path):
        files = {"deep/nest/tool.py": 'CODE = "S009"\n'}
        root = make_repo(tmp_path, files)
        r = W.token_refs(root, "S009", "tool.py")
        assert r["in"] == "deep/nest/tool.py"
        assert r["code"] == 1

    def test_an_ambiguous_container_is_refused_rather_than_guessed(self,
                                                                  tmp_path):
        files = {"a/tool.py": 'X = "S009"\n', "b/tool.py": "pass\n"}
        root = make_repo(tmp_path, files)
        r = W.token_refs(root, "S009", "tool.py")
        assert r["error"] == "ambiguous"
        assert r["candidates"] == ["a/tool.py", "b/tool.py"]

    def test_an_unresolved_container_is_an_error_not_a_zero(self, tmp_path):
        # The dangerous failure for an ABSENCE check: a container that does
        # not resolve reads as "the token is not there", which is the exact
        # verdict the claim wants. It must never be reported as clean.
        root = make_repo(tmp_path, {"a/tool.py": "pass\n"})
        assert W.token_refs(root, "S009", "nope.py")["error"] == "unresolved"

    def test_expect_absent_scores_a_written_claim(self, tmp_path):
        files = {"a/tool.py": 'CODE = "S009"\n', "b/quiet.py": "pass\n"}
        root = make_repo(tmp_path, files)
        refuted = ["--repo-root", root, "token-refs", "S009", "--in",
                   "a/tool.py", "--expect-absent"]
        assert W.main(refuted) == 1
        holds = ["--repo-root", root, "token-refs", "S009", "--in",
                 "b/quiet.py", "--expect-absent"]
        assert W.main(holds) == 0

    def test_a_prose_only_mention_does_not_refute_the_claim(self, tmp_path):
        files = {"a/tool.py": "# S009 would go here one day\n"}
        root = make_repo(tmp_path, files)
        argv = ["--repo-root", root, "token-refs", "S009", "--in",
                "a/tool.py", "--expect-absent"]
        assert W.main(argv) == 0


# --------------------------------------------------------------------------
# Round 481 (harness A) — the line numbers the graph used to throw away
# --------------------------------------------------------------------------

class TestEdgeLines:
    """Every edge carries the line it was found on, and the renderer's `-`
    means *no line*, not *line zero*.

    Until round 481 the three `ast` passes in `references()` passed the
    literal `0` as the lineno, so 721 of this tree's 1043 edges — 69 %, every
    `import`, every `os.path.join` fold, every bare string constant — had no
    location. The single renderer was `lineno or "-"`, which spells 0 and
    "unknown" identically, so the loss was invisible in `--why` traces, in
    W003/W006 findings, and in the 80 `"<file>:-"` pins of the registry that
    round 475 read as a convention.
    """

    def test_no_edge_in_this_tree_has_line_zero(self):
        g = W.Graph(REPO)
        g.closure()
        zero = [(s, t, v) for s, d in g.edges.items()
                for t, v in d.items() if not v[0]]
        assert zero == [], zero[:10]

    def test_an_import_edge_carries_the_import_line(self, tmp_path):
        files = {"top.py": "import os\n\nimport tool\n" + MAIN,
                 "tool.py": "x = 1\n"}
        root = make_repo(tmp_path, files)
        idx = W.Index(W.tracked_files(root))
        edges, _ = W.references(root, "top.py", idx)
        assert edges["tool.py"] == (3, "import")

    def test_a_from_import_carries_its_line(self, tmp_path):
        files = {"top.py": "\n\n\nfrom pkg import mod\n" + MAIN,
                 "pkg/mod.py": "x = 1\n", "pkg/__init__.py": ""}
        root = make_repo(tmp_path, files)
        idx = W.Index(W.tracked_files(root))
        edges, _ = W.references(root, "top.py", idx)
        assert edges["pkg/mod.py"][0] == 4

    def test_the_three_ast_passes_return_lines_with_their_values(self):
        tree, docs = W._parse_for_ast('"""doc"""\nimport a.b\nX = "p/q.py"\n'
                                      'import os\nY = os.path.join("r", "s")\n')
        assert W._string_constants(tree, docs) == [("p/q.py", 3),
                                                   ("r", 5), ("s", 5)]
        assert W._constructed_paths(tree)[0] == [("r/s", 5)]
        assert W._imports(tree) == [("a.b", 2), ("os", 4)]

    def test_edge_line_renders_a_missing_line_as_a_dash(self):
        assert W.edge_line(0) == "-"
        assert W.edge_line(None) == "-"
        assert W.edge_line(7) == "7"

    def test_best_incoming_is_the_same_answer_in_two_processes(self):
        """`_reached` is a set of strings and CPython randomises string
        hashing per process, so a tie in `(depth, kind)` used to be broken by
        iteration order. Three consecutive runs on an unchanged tree named
        three different sources for `languages/whence/curecheck.py`, and the
        `via` column `bootstrap` proposes is one draw from that
        distribution.
        """
        prog = (
            "import os, sys, json\n"
            "sys.path.insert(0, %r)\n"
            "import wiring_audit as W\n"
            "g = W.Graph(%r)\n"
            "g.closure()\n"
            "print(json.dumps([g.best_incoming(p) for p in "
            "sorted(g.node_set)[:400]]))\n" % (_HARNESS, REPO))
        outs = []
        for seed in ("0", "1", "2"):
            env = dict(os.environ, PYTHONHASHSEED=seed,
                       PYTHONDONTWRITEBYTECODE="1")
            r = subprocess.run([sys.executable, "-c", prog], env=env,
                               capture_output=True, text=True, timeout=600)
            assert r.returncode == 0, r.stderr[-2000:]
            outs.append(r.stdout)
        assert outs[0] == outs[1] == outs[2]


# --------------------------------------------------------------------------
# undeclared / declare — round 499
# --------------------------------------------------------------------------

class TestUndeclared:
    """The commit-time half. `audit()` has answered W001 correctly since
    round 415 and has never been read by the round that caused it: seven
    rounds (471, 472, 478, 483, 484, 490, 498) built an entry point, did not
    declare it, and exited before the health check ran. These pin the fast
    path that a pre-commit hook can afford."""

    def _repo(self, tmp_path):
        root = make_repo(tmp_path, {
            "run_driver.sh": "python3 tool.py\n",
            "tool.py": "import os\n" + MAIN,
            "orphan.sh": "echo hi\n",
            "helper.py": "def f():\n    pass\n",          # no __main__ guard
            "state/round-1/once.py": "x = 1\n" + MAIN,     # frozen prefix
        })
        write_registry(root,
                       frozen_prefixes=[{"prefix": "state/",
                                         "reason": "records tree"}],
                       entry_points={"run_driver.sh": {"status": "wired",
                                                       "via": "root",
                                                       "via_kind": "root"}})
        return root

    def test_it_finds_an_undeclared_entry_point(self, tmp_path):
        root = self._repo(tmp_path)
        assert set(W.undeclared(root)) == {"tool.py", "orphan.sh"}

    def test_a_declared_entry_point_is_not_reported(self, tmp_path):
        assert "run_driver.sh" not in W.undeclared(self._repo(tmp_path))

    def test_a_module_without_a_main_guard_is_not_an_entry_point(self,
                                                                 tmp_path):
        assert "helper.py" not in W.undeclared(self._repo(tmp_path))

    def test_an_excluded_prefix_is_not_reported(self, tmp_path):
        """`state/` is a records tree. A permanent finding for a state the
        program deliberately keeps is the mute-button failure."""
        assert "state/round-1/once.py" not in W.undeclared(self._repo(tmp_path))

    def test_restricting_to_paths_scans_only_those(self, tmp_path):
        root = self._repo(tmp_path)
        assert W.undeclared(root, ["orphan.sh"]) == ["orphan.sh"]
        assert W.undeclared(root, ["helper.py"]) == []

    def test_it_needs_no_graph(self, tmp_path):
        """The whole point of the fast path: it must not touch `Graph`.

        The full audit costs ~18 s on the real tree because it resolves
        every reference in the closure; that is not something to put in
        front of every commit. If someone later routes `undeclared` through
        the graph for convenience, this fails.
        """
        root = self._repo(tmp_path)
        boom = lambda *a, **k: pytest.fail("undeclared() built a Graph")
        saved = W.Graph
        W.Graph = boom
        try:
            assert set(W.undeclared(root)) == {"tool.py", "orphan.sh"}
        finally:
            W.Graph = saved


class TestDeclare:

    def _repo(self, tmp_path):
        root = make_repo(tmp_path, {
            "run_driver.sh": 'python3 -m pytest tests/\n',
            "tests/test_thing.py": "import thing\n",
            "thing.py": "x = 1\n" + MAIN,
            "lonely.py": "y = 2\n" + MAIN,
        })
        write_registry(root, entry_points={})
        return root

    def test_it_derives_wired_for_a_reachable_entry_point(self, tmp_path):
        root = self._repo(tmp_path)
        entry = W.propose(root, "thing.py")
        assert entry["status"] == "wired"
        assert entry["via"].startswith("tests/test_thing.py:")
        assert entry["via_kind"] == "import"

    def test_it_REFUSES_an_unreachable_entry_point(self, tmp_path):
        """The one judgement no graph can make.

        `manual` and `unwired` differ by INTENT, not by any property of the
        code, and collapsing them puts the words "by design" over a real
        debt. `bootstrap` refuses the same choice for the same reason.
        """
        root = self._repo(tmp_path)
        with pytest.raises(W.Undeclarable) as exc:
            W.propose(root, "lonely.py")
        msg = str(exc.value)
        assert "manual" in msg and "unwired" in msg

    def test_declare_is_a_dry_run_by_default(self, tmp_path):
        root = self._repo(tmp_path)
        res = W.declare(root, ["thing.py"])
        assert res["added"] and res["wrote"] is False
        assert W.load_registry(root)["entry_points"] == {}

    def test_write_persists_and_closes_the_finding(self, tmp_path):
        root = self._repo(tmp_path)
        assert "thing.py" in W.undeclared(root)
        res = W.declare(root, ["thing.py"], write=True)
        assert res["wrote"] is True
        assert "thing.py" not in W.undeclared(root)
        # ...and it is a real W001 closure, not just a key appearing: the
        # full audit must stop reporting it too.
        w001 = [p for c, p, _ in W.audit(root)["findings"] if c == "W001"]
        assert "thing.py" not in w001
        assert set(w001) == {"run_driver.sh", "lonely.py"}

    def test_declaring_everything_makes_the_fixture_repo_clean(self, tmp_path):
        """End to end on a whole tiny tree: the two derivable entry points
        are declared by the tool, `lonely.py` is the one a human must
        classify, and only then is the audit green."""
        root = self._repo(tmp_path)
        W.declare(root, ["thing.py", "run_driver.sh"], write=True)
        reg = W.load_registry(root)
        reg["entry_points"]["lonely.py"] = {"status": "manual",
                                            "owner": "nobody",
                                            "reason": "a demo"}
        W.dump_registry(os.path.join(root, W.REGISTRY_NAME), reg)
        assert W.undeclared(root) == []
        errs = [f for f in W.audit(root)["findings"] if f[0] in W.ERROR_CODES]
        assert errs == [], errs

    def test_a_refusal_does_not_block_the_declarable_ones(self, tmp_path):
        root = self._repo(tmp_path)
        res = W.declare(root, ["thing.py", "lonely.py"], write=True)
        assert list(res["added"]) == ["thing.py"]
        assert [p for p, _ in res["refused"]] == ["lonely.py"]

    def test_declaring_an_already_declared_path_is_refused(self, tmp_path):
        root = self._repo(tmp_path)
        W.declare(root, ["thing.py"], write=True)
        res = W.declare(root, ["thing.py"])
        assert res["added"] == {}
        assert "already declared" in res["refused"][0][1]


class TestRegistryWriting:

    def test_insert_never_reorders_an_existing_key(self):
        """Round 499 wrote `declare` the obvious way first — rebuild the
        dict as `sorted(eps)` — and the resulting ONE-ENTRY addition came
        out as 87 insertions and 81 deletions, because
        `harness/wiring-registry.json` has never been sorted: it is grouped
        and appended, so `swap_driver.sh` sits directly before
        `harness/escalationguard.py`. This pins the repair."""
        existing = {"b": 1, "a": 2, "z": 3}
        out = W._insert_entries(existing, {"c": 9})
        assert [k for k in out if k in existing] == list(existing)
        assert list(out) == ["b", "a", "c", "z"]

    def test_insert_appends_when_nothing_sorts_after(self):
        assert list(W._insert_entries({"b": 1, "a": 2}, {"zz": 9})) \
            == ["b", "a", "zz"]

    def test_the_live_registry_is_still_append_ordered(self):
        """If someone ever sorts it, the rule above stops being needed —
        and the reader should find that out from a failing test rather than
        from a 90-line diff."""
        keys = list(W.load_registry(REPO)["entry_points"])
        assert keys != sorted(keys)

    def test_dump_reproduces_the_live_registry_byte_for_byte(self, tmp_path):
        """`indent=2, ensure_ascii=False`. The default `ensure_ascii=True`
        rewrites every em dash in every `reason` string, turning a one-entry
        addition into a whole-file diff."""
        src = os.path.join(REPO, W.REGISTRY_NAME)
        with open(src, encoding="utf-8") as fh:
            before = fh.read()
        dst = str(tmp_path / "copy.json")
        assert W.dump_registry(dst, json.loads(before)) == before
        with open(dst, encoding="utf-8") as fh:
            assert fh.read() == before

    def test_viapin_delegates_to_the_same_writer(self):
        """Two writers for one file is how the `ensure_ascii` rule gets
        re-learned by whoever edits only one of them."""
        sys.path.insert(0, _HARNESS)
        import viapin
        assert viapin._dump_registry.__module__ == "viapin"
        src = os.path.join(REPO, W.REGISTRY_NAME)
        with open(src, encoding="utf-8") as fh:
            before = fh.read()
        import inspect
        assert "dump_registry" in inspect.getsource(viapin._dump_registry)
        with open(src, encoding="utf-8") as fh:
            assert fh.read() == before


class TestThisTreeCommitTime:

    def test_the_fast_path_agrees_with_the_full_audit(self):
        """A fast path that disagrees with the slow one is worse than no
        fast path, because it makes the slow one look wrong."""
        slow = sorted(p for c, p, _ in W.audit(REPO)["findings"]
                      if c == "W001")
        assert sorted(W.undeclared(REPO)) == slow

    def test_the_pre_commit_hook_carries_the_advisory_wiring_step(self):
        sys.path.insert(0, _HARNESS)
        import escalationguard as eg
        body = eg.hook_script()
        assert "wiring_audit.py" in body
        assert "undeclared --staged" in body
        # ADVISORY: the step must never be able to fail the hook. A gate here
        # can refuse the commit of a round with no turns left to debug it,
        # and losing a round's uncommitted diff is strictly worse than one
        # more round of a red registry line.
        # `[-1]`, not `[1]`: the phrase occurs TWICE in the body, once in
        # the comment explaining why `check` is not used and once in the
        # command itself. Splitting on the first occurrence tested the
        # comment and reported the hook as a gate.
        step = body.split("undeclared --staged")[-1]
        assert "|| true" in step
        assert body.rstrip().endswith("exit 0")

    def test_the_installed_hook_lets_an_undeclared_commit_through(self,
                                                                  tmp_path):
        """The claim "it only warns", proved by committing through it.

        Asserting on the hook TEXT cannot distinguish a warning from a gate;
        only running `git commit` can. An advisory step that exits 1 on a
        path nobody exercised is exactly the shape that destroys a round's
        uncommitted work.
        """
        sys.path.insert(0, _HARNESS)
        import escalationguard as eg
        root = str(tmp_path)
        os.makedirs(os.path.join(root, "harness"))
        for name in ("wiring_audit.py", "escalationguard.py"):
            shutil.copy(os.path.join(_HARNESS, name),
                        os.path.join(root, "harness", name))
        with open(os.path.join(root, "run_driver.sh"), "w") as fh:
            fh.write("python3 harness/wiring_audit.py check\n")
        write_registry(root)
        for cmd in (["git", "init", "-q"],
                    ["git", "config", "user.email", "t@t"],
                    ["git", "config", "user.name", "t"],
                    ["git", "add", "-A"],
                    ["git", "commit", "-qm", "base"]):
            subprocess.run(cmd, cwd=root, check=True)
        eg.install_hook(repo=root, python=sys.executable)
        with open(os.path.join(root, "newtool.py"), "w") as fh:
            fh.write("x = 1\n" + MAIN)
        subprocess.run(["git", "add", "newtool.py"], cwd=root, check=True)
        r = subprocess.run(["git", "commit", "-m", "undeclared entry point"],
                           cwd=root, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr          # NOT a gate
        assert "W001" in r.stdout + r.stderr                   # but it warned
        assert "declare newtool.py" in r.stdout + r.stderr     # with the fix

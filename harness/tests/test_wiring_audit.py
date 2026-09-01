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
        assert debts == ["harness/swe/loop.py"]
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

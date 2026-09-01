"""Round 421 (harness A) — tests for `harness/verb_audit.py`.

Two layers, deliberately separated:

`TestDeclared` / `TestScan` / `TestLanguageRule` are UNIT tests over synthetic
fixtures. They pin the rules the analyser applies, and they keep working when
the repo moves.

`TestThisTree` runs the analyser against the LIVE tree. That is the same shape
`test_wiring_audit.py::TestThisTree` uses, and it is deliberate: it is the
mechanism by which `wiring_audit`'s registry rules are actually enforced every
round, since the driver never invokes `wiring_audit.py check` itself — which
is one of the findings this very module was written to measure. The live
assertions are INVARIANTS (the law, and "no unexplained broken invocation"),
never a pinned count, because a pinned count is what round 403 found rotting
in `test_self_hosting.py`.
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
ROOT = os.path.dirname(HARNESS)
if HARNESS not in sys.path:
    sys.path.insert(0, HARNESS)

import verb_audit as V                                          # noqa: E402


# --------------------------------------------------------------------------
# DECLARED — the AST read
# --------------------------------------------------------------------------

def _write(tmp_path, name, text):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return str(tmp_path), name


class TestDeclared:

    def test_subparser_verbs_are_declared(self, tmp_path):
        root, rel = _write(tmp_path, "t.py", """
import argparse
ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd")
sub.add_parser("check")
sub.add_parser("baseline")
""")
        d = V.declared_verbs(root, rel)
        assert set(d) == {"check", "baseline"}
        assert d["check"] == "subparser"

    def test_add_parser_aliases_count_as_verbs(self, tmp_path):
        root, rel = _write(tmp_path, "t.py", """
import argparse
sub = argparse.ArgumentParser().add_subparsers()
sub.add_parser("status", aliases=["st", "stat"])
""")
        assert set(V.declared_verbs(root, rel)) == {"status", "st", "stat"}

    def test_positional_choices_are_verbs(self, tmp_path):
        """`harness/swe/slowtier.py:918`'s form, which has no subparsers."""
        root, rel = _write(tmp_path, "t.py", """
import argparse
ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["status", "plan", "run"])
""")
        d = V.declared_verbs(root, rel)
        assert set(d) == {"status", "plan", "run"}
        assert d["run"] == "choices"

    def test_option_choices_are_NOT_verbs(self, tmp_path):
        """The rule that keeps a dozen invented subcommands out of every file.

        `--suite` names values, not commands. Reading its `choices` as verbs
        would make every file with a constrained option look like a rich CLI
        whose surface is 90% dead.
        """
        root, rel = _write(tmp_path, "t.py", """
import argparse
ap = argparse.ArgumentParser()
ap.add_argument("--suite", choices=["harness-fast", "whence-fast"])
""")
        assert V.declared_verbs(root, rel) == {}

    def test_a_single_command_script_declares_nothing(self, tmp_path):
        root, rel = _write(tmp_path, "t.py", """
import argparse
ap = argparse.ArgumentParser()
ap.add_argument("--json")
""")
        assert V.declared_verbs(root, rel) == {}

    def test_a_shell_script_declares_nothing(self, tmp_path):
        root, rel = _write(tmp_path, "t.sh", "#!/bin/sh\necho hi\n")
        assert V.declared_verbs(root, rel) == {}

    def test_unparseable_python_is_empty_not_an_exception(self, tmp_path):
        root, rel = _write(tmp_path, "t.py", "def broken(:\n")
        assert V.declared_verbs(root, rel) == {}

    def test_the_live_victim_declares_six(self):
        """The file round 415's `_scope` note named, read from the real tree."""
        d = V.declared_verbs(ROOT, "harness/pristine_check.py")
        assert set(d) == {"check", "baseline", "baseline-status", "suites",
                          "status", "dirt"}


# --------------------------------------------------------------------------
# The forward scan
# --------------------------------------------------------------------------

class TestScan:

    def test_the_verb_after_the_path_is_matched(self):
        toks = V._tokens("python3 harness/pristine_check.py status || true")
        m, fb = V._scan_line_for(toks, 1, {"status", "check"})
        assert m == "status"

    def test_the_scan_stops_at_a_command_separator(self):
        """`a.py && b.py check` — the verb belongs to b.py, not to a.py."""
        toks = V._tokens("python3 a.py && python3 b.py check")
        m, _ = V._scan_line_for(toks, 1, {"check"})
        assert m is None

    def test_a_value_flag_does_not_donate_its_value_as_a_verb(self):
        toks = V._tokens("python3 x.py --only run --json out")
        m, fb = V._scan_line_for(toks, 1, {"status"})
        assert m is None
        assert fb != "run"

    def test_a_flag_before_the_verb_is_skipped(self):
        toks = V._tokens("python3 x.py --quiet status")
        m, _ = V._scan_line_for(toks, 1, {"status"})
        assert m == "status"

    def test_language_keywords_are_never_read_as_verbs(self):
        """`assert "harness/swe/guardpin.py" in cands` — measured on this tree
        as a false V002 before `_NOT_A_VERB` existed."""
        toks = V._tokens('assert "harness/swe/guardpin.py" in cands')
        m, fb = V._scan_line_for(toks, 1, {"check", "locate", "run"})
        assert m is None
        assert fb != "in"

    def test_an_undeclared_bare_word_is_reported_as_first_bare(self):
        """The unfiltered read that feeds V002 still fires for a real typo."""
        toks = V._tokens("python3 harness/pristine_check.py staus")
        m, fb = V._scan_line_for(toks, 1, {"status", "check"})
        assert m is None
        assert fb == "staus"


# --------------------------------------------------------------------------
# The language rule — the thing that took precision from 8/11 to 8/8
# --------------------------------------------------------------------------

class TestLanguageRule:
    """A `.sh` line is a command; a raw `.py` line is a string constant."""

    def _graph(self, tmp_path, files):
        import subprocess
        for name, text in files.items():
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
        subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
        return V.VerbGraph(str(tmp_path))

    TARGET = """
import argparse
ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd")
sub.add_parser("status")
sub.add_parser("check")
if __name__ == "__main__":
    ap.parse_args()
"""

    def test_a_shell_line_counts_as_an_invocation(self, tmp_path):
        vg = self._graph(tmp_path, {
            "run_driver.sh": "python3 tool.py status\n",
            "tool.py": self.TARGET,
        })
        sites = vg.sites({"tool.py": {"status": "subparser",
                                      "check": "subparser"}})
        assert any(s[2] == "status" for s in sites["tool.py"])

    def test_a_raw_python_line_does_NOT_count(self, tmp_path):
        """The three false-REACHED shapes measured on the live tree: advice
        printed to a human, a copy-paste hint, and a test asserting the
        command must never run unattended."""
        vg = self._graph(tmp_path, {
            "run_driver.sh": "python3 caller.py\n",
            "caller.py": 'msg = "Use `python3 tool.py check` to fix"\n',
            "tool.py": self.TARGET,
        })
        sites = vg.sites({"tool.py": {"status": "subparser",
                                      "check": "subparser"}})
        assert [s for s in sites["tool.py"] if s[2] == "check"] == []

    def test_a_folded_argv_list_DOES_count(self, tmp_path):
        vg = self._graph(tmp_path, {
            "run_driver.sh": "python3 caller.py\n",
            "caller.py": ('import subprocess, sys\n'
                          'subprocess.run([sys.executable, "tool.py", '
                          '"check", "--json", "o"])\n'),
            "tool.py": self.TARGET,
        })
        sites = vg.sites({"tool.py": {"status": "subparser",
                                      "check": "subparser"}})
        assert any(s[2] == "check" for s in sites["tool.py"])

    def test_an_embedded_shell_comment_is_not_an_invocation(self, tmp_path):
        """A `#` line that survives `code_text` is a comment in an EMBEDDED
        language — this repo builds remote shell inside Python f-strings, and
        `tokenize` correctly leaves a `#` inside a string alone."""
        vg = self._graph(tmp_path, {
            "run_driver.sh": "# see tool.py check for the old bug\n"
                             "python3 tool.py status\n",
            "tool.py": self.TARGET,
        })
        sites = vg.sites({"tool.py": {"status": "subparser",
                                      "check": "subparser"}})
        assert [s for s in sites["tool.py"] if s[2] == "check"] == []
        assert any(s[2] == "status" for s in sites["tool.py"])

    def test_a_files_own_usage_block_is_not_evidence_it_runs(self, tmp_path):
        """A self-reference is dropped: a script documenting its own verbs in
        a runnable `Usage:` block proves nothing about what invokes them."""
        vg = self._graph(tmp_path, {
            "run_driver.sh": "bash tool.sh\n",
            "tool.sh": "# usage\nbash tool.sh check\n",
            "tool.py": self.TARGET,
        })
        sites = vg.sites({"tool.sh": {"check": "subparser"}})
        assert sites["tool.sh"] == []


# --------------------------------------------------------------------------
# The live tree
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def live():
    return V.audit(ROOT)


class TestThisTree:

    def test_the_law_holds_every_reached_verb_is_declared(self, live):
        """REACHED(f) ⊆ DECLARED(f). This is the falsifiable direction of the
        round-421 prediction: a verb observed at a call site that the target
        does not declare is either a broken invocation or an extractor bug."""
        _, rows, _ = live
        for r in rows:
            assert set(r["reached"]) <= set(r["declared"]), r["path"]

    def test_no_unexplained_broken_invocation(self, live):
        """V002 is 0 on this tree. All three instances that existed while the
        extractor was being built were artefacts and each was fixed by a rule
        (`_NOT_A_VERB`, the argv-completeness flag, the language rule) rather
        than by an exemption."""
        _, _, findings = live
        assert [f for f in findings if f[0] == "V002"] == []

    def test_manual_entry_points_are_never_reported(self, live):
        """A file nothing automatic runs has every verb trivially unreached.
        Reporting that is the mute-button failure `manual` exists to avoid."""
        vg, rows, findings = live
        manual = {p for p, e in vg.entry_points.items()
                  if e.get("status") == "manual"}
        assert not (manual & {r["path"] for r in rows})
        assert not (manual & {f[1] for f in findings})

    def test_the_analysis_is_not_vacuous(self, live):
        """A checker that measured nothing reports perfection. Round 420's own
        pitfall, applied here: a verdict with no population is not a verdict."""
        _, rows, _ = live
        assert len(rows) >= 10
        assert sum(len(r["declared"]) for r in rows) >= 50

    def test_the_named_victim_reproduces(self, live):
        """Round 415's `_scope` note said `pristine_check.py` is wired via
        `status` only. This is that sentence, measured.

        It is not a pinned count: if a later round wires `check`, this asserts
        only that `status` is still reached and that the file is still
        analysed — the thing that would break it is the analyser losing sight
        of the file, which is the regression worth catching."""
        _, rows, _ = live
        row = [r for r in rows if r["path"] == "harness/pristine_check.py"]
        assert row, "pristine_check.py dropped out of the verb analysis"
        assert "status" in row[0]["reached"]

    def test_findings_never_set_the_exit_code(self, live):
        """Round 363's rule. A dead subcommand is frequently a correct choice;
        what was missing was the number, not permission."""
        rc = V.main(["--repo-root", ROOT, "check"])
        assert rc == 0

    def test_the_summary_publishes_its_own_denominator(self, live):
        """Round 417's failure, applied here: a coverage number that hides
        what it is a fraction of is unreadable. Both halves must be present."""
        _, rows, _ = live
        s = V.summarise(rows)
        assert "declared verb(s)" in s and "reached" in s and "%" in s

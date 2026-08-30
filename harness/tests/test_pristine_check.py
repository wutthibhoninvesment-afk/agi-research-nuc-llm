"""Tests for `harness/pristine_check.py` (round 355, harness A).

Fast tier by construction: every test here injects a `runner`, so nothing
spawns pytest and nothing allocates a git worktree — except the four tests
at the bottom, which build a throwaway repo in `tmp_path` because the two
things worth checking against real git (porcelain parsing and worktree
lifecycle) are exactly the things a fake would let me get wrong.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import pristine_check as pc            # noqa: E402


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def recording_runner(table, default=(0, "1 passed in 0.1s")):
    """A runner that answers from `table` and records every call.

    `table` maps a substring of the joined argv to `(rc, output)`; the first
    match wins. Calls land on `runner.calls` so a test can assert what was
    NOT run — which is how rule 1's short-circuit is checked.
    """
    calls = []

    def runner(argv, cwd=None, timeout=None):
        calls.append({"argv": list(argv), "cwd": cwd, "timeout": timeout})
        joined = " ".join(argv) + " @" + str(cwd)
        for needle, resp in table:
            if needle in joined:
                return resp
        return default

    runner.calls = calls
    return runner


PASS = (0, "........  [100%]\n476 passed, 303 deselected in 47.38s\n")
FAIL_PARITY = (1, (
    "F.......  [100%]\n"
    "=========================== short test summary info =====================\n"
    "FAILED tests/test_lexer_guest_parity.py::test_small_example_files_lex_identically\n"
    "1 failed, 1191 passed, 54 deselected in 27.93s\n"))


# --------------------------------------------------------------------------
# parse_pytest_output
# --------------------------------------------------------------------------

def test_parses_counts_and_failing_node_ids():
    got = pc.parse_pytest_output(FAIL_PARITY[1])
    assert got["completed"] is True
    assert got["counts"] == {"failed": 1, "passed": 1191, "deselected": 54}
    assert got["failures"] == [
        "tests/test_lexer_guest_parity.py::test_small_example_files_lex_identically"]


def test_a_clean_run_parses_to_zero_failures():
    got = pc.parse_pytest_output(PASS[1])
    assert got["failures"] == []
    assert got["counts"]["passed"] == 476
    assert got["completed"] is True


def test_output_with_no_count_line_is_not_completed():
    # Rule 3's raw material: a segfault or a truncated timeout leaves output
    # that must NOT be read as "zero failures, therefore clean".
    got = pc.parse_pytest_output("collecting ... \nSegmentation fault\n")
    assert got["completed"] is False
    assert got["failures"] == []


def test_error_lines_count_as_failures_too():
    got = pc.parse_pytest_output(
        "ERROR tests/test_x.py - ImportError: no module named y\n"
        "1 error in 0.2s\n")
    assert got["failures"] == ["tests/test_x.py"]
    assert got["counts"] == {"error": 1}


def test_errors_plural_folds_into_the_same_count_key():
    got = pc.parse_pytest_output("2 errors in 0.2s\n")
    assert got["counts"] == {"error": 2}


def test_node_ids_are_normalised_so_two_trees_compare_equal():
    a = pc.parse_pytest_output("FAILED ./tests/t.py::k\n1 failed in 0s\n")
    b = pc.parse_pytest_output("FAILED tests/t.py::k\n1 failed in 0s\n")
    assert a["failures"] == b["failures"] == ["tests/t.py::k"]


# --------------------------------------------------------------------------
# run_suite
# --------------------------------------------------------------------------

def test_run_suite_rejects_an_unknown_name():
    with pytest.raises(KeyError):
        pc.run_suite("no-such-suite", "/tmp/x")


def test_run_suite_runs_the_registered_argv_in_the_registered_cwd():
    r = recording_runner([("pytest", PASS)])
    got = pc.run_suite("whence-fast", "/tmp/tree", runner=r)
    argv = r.calls[0]["argv"]
    assert argv[1:3] == ["-m", "pytest"]
    assert argv[3:] == pc.SUITES["whence-fast"]["argv"]
    assert r.calls[0]["cwd"] == os.path.normpath("/tmp/tree/languages/whence")
    assert got["suite"] == "whence-fast" and got["root"] == "/tmp/tree"
    assert got["timed_out"] is False


def test_run_suite_marks_a_timeout_as_incomplete():
    r = recording_runner([("pytest", (None, "collecting ...\n"))])
    got = pc.run_suite("harness-fast", "/tmp/tree", runner=r)
    assert got["timed_out"] is True
    assert got["completed"] is False


def test_run_suite_keeps_a_tail_of_the_output_for_the_reader():
    r = recording_runner([("pytest", (1, "\n".join(
        ["line %d" % i for i in range(200)] + ["1 failed in 1s"])))])
    got = pc.run_suite("harness-fast", "/tmp/t", runner=r)
    assert got["tail"].splitlines()[-1] == "1 failed in 1s"
    assert len(got["tail"].splitlines()) == 25


# --------------------------------------------------------------------------
# compare — the five verdicts
# --------------------------------------------------------------------------

def _run(failures, passed=10, completed=True):
    return {"suite": "s", "failures": list(failures),
            "counts": {"passed": passed} if completed else {},
            "completed": completed, "duration_s": 1.0}


def test_verdict_clean_when_both_trees_are_green():
    assert pc.compare(_run([]), _run([]))["verdict"] == "clean"


def test_verdict_git_incomplete_is_the_finding():
    got = pc.compare(_run([]), _run(["t.py::k"]))
    assert got["verdict"] == "git_incomplete"
    assert got["pristine_only"] == ["t.py::k"]
    assert got["live_only"] == []


def test_verdict_untracked_breaks_test_is_the_mirror_case():
    # An untracked file that BREAKS a test is just as invisible as one that
    # is silently required, so it gets a verdict rather than being dropped.
    got = pc.compare(_run(["t.py::k"]), _run([]))
    assert got["verdict"] == "untracked_breaks_test"
    assert got["live_only"] == ["t.py::k"]


def test_a_test_failing_in_both_trees_is_not_this_class():
    # Rule 2. Reporting a plain broken test as a git-reproducibility defect
    # is the false alarm that gets a checker ignored.
    got = pc.compare(_run(["t.py::k"]), _run(["t.py::k"]))
    assert got["verdict"] == "both_failed"
    assert got["both"] == ["t.py::k"] and got["pristine_only"] == []


def test_an_incomplete_run_on_either_side_yields_no_verdict():
    # Rule 3, both directions.
    assert pc.compare(_run([], completed=False),
                      _run([]))["verdict"] == "inconclusive"
    assert pc.compare(_run([]),
                      _run([], completed=False))["verdict"] == "inconclusive"


def test_git_incomplete_wins_over_a_test_that_fails_in_both():
    got = pc.compare(_run(["both.py::k"]),
                     _run(["both.py::k", "only.py::k"]))
    assert got["verdict"] == "git_incomplete"
    assert got["pristine_only"] == ["only.py::k"]
    assert got["both"] == ["both.py::k"]


# --------------------------------------------------------------------------
# dirt classification
# --------------------------------------------------------------------------

PORCELAIN = (
    " M languages/whence/SECURITY.md\n"
    " M state/round_counter\n"
    "?? knowledge/round-999-x.md\n"
    "?? languages/whence/examples/gateway.lang\n"
    "!! logs/driver.log\n"
    "!! .venv/\n")


def test_worktree_dirt_splits_the_three_buckets():
    r = recording_runner([("git status", (0, PORCELAIN))])
    got = pc.worktree_dirt(runner=r)
    assert got["tracked_modified"] == ["languages/whence/SECURITY.md",
                                       "state/round_counter"]
    assert got["untracked"] == ["knowledge/round-999-x.md",
                                "languages/whence/examples/gateway.lang"]
    assert got["ignored"] == [".venv/", "logs/driver.log"]
    assert got["ok"] is True


def test_worktree_dirt_asks_git_for_ignored_and_all_untracked():
    r = recording_runner([("git status", (0, ""))])
    pc.worktree_dirt(runner=r)
    argv = " ".join(r.calls[0]["argv"])
    assert "--untracked-files=all" in argv and "--ignored" in argv


def test_worktree_dirt_reports_not_ok_when_git_fails():
    r = recording_runner([("git status", (128, "not a git repository"))])
    assert pc.worktree_dirt(runner=r)["ok"] is False


def test_the_standing_dirty_registry_excuses_round_counter():
    # `state/round_counter` is ` M` in EVERY round by design; letting it veto
    # every differential would make this checker unrunnable from the driver.
    assert "state/round_counter" in pc.standing_dirty()


def test_standing_dirty_is_empty_rather_than_raising_on_a_bad_file(tmp_path):
    bad = tmp_path / "nope.json"
    bad.write_text("{not json", encoding="utf-8")
    assert pc.standing_dirty(str(bad)) == set()
    assert pc.standing_dirty(str(tmp_path / "missing.json")) == set()


def test_blocking_dirt_is_the_tracked_diff_minus_the_allowlist():
    dirt = {"tracked_modified": ["a.md", "state/round_counter"]}
    assert pc.blocking_dirt(dirt, allow={"state/round_counter"}) == ["a.md"]


# --------------------------------------------------------------------------
# differential — rule 1 and rule 4
# --------------------------------------------------------------------------

def test_rule_1_short_circuits_before_spending_a_worktree():
    r = recording_runner([("pytest", PASS)])
    rec = pc.differential(["harness-fast"], runner=r, dirt={
        "ok": True, "tracked_modified": ["harness/agentloop/tools.py"],
        "untracked": [], "ignored": []})
    assert rec["verdict"] == "dirty_worktree"
    assert rec["blocking_dirty"] == ["harness/agentloop/tools.py"]
    assert rec["results"] == []
    # The point of doing this check FIRST: none of the EXPENSIVE work
    # happened. (A `git rev-parse` for the record's `resolved` field does
    # run — milliseconds — so this asserts the two things that are not:
    # no worktree was allocated and no suite was executed.)
    ran = [" ".join(c["argv"]) for c in r.calls]
    assert not [c for c in ran if "worktree" in c], ran
    assert not [c for c in ran if "pytest" in c], ran


def test_a_standing_dirty_path_alone_does_not_block():
    r = recording_runner([("pytest", PASS)])
    rec = pc.differential(["harness-fast"], runner=r, dirt={
        "ok": True, "tracked_modified": ["state/round_counter"],
        "untracked": ["x"], "ignored": []})
    assert rec["verdict"] == "clean"
    assert rec["untracked_count"] == 1


def test_allow_dirty_waives_one_named_path_and_records_it():
    r = recording_runner([("pytest", PASS)])
    rec = pc.differential(
        ["harness-fast"], runner=r,
        allow_dirty=["languages/whence/SECURITY.md"],
        # escalation_allow=() isolates this test to the HAND waiver: the
        # live registry now also pins this exact path (round 373), and
        # without this the test would pass through the other mechanism.
        escalation_allow=(),
        dirt={"ok": True, "untracked": [], "ignored": [],
              "tracked_modified": ["languages/whence/SECURITY.md"]})
    assert rec["verdict"] == "clean"
    assert rec["allowed_dirty"] == ["languages/whence/SECURITY.md"]


def test_allow_dirty_waives_only_the_path_it_names():
    r = recording_runner([("pytest", PASS)])
    rec = pc.differential(
        ["harness-fast"], runner=r, allow_dirty=["a.md"],
        dirt={"ok": True, "untracked": [], "ignored": [],
              "tracked_modified": ["a.md", "b.md"]})
    assert rec["verdict"] == "dirty_worktree"
    assert rec["blocking_dirty"] == ["b.md"]


def test_a_git_status_failure_is_inconclusive_not_clean():
    rec = pc.differential(["harness-fast"], runner=recording_runner([]),
                          dirt={"ok": False, "tracked_modified": [],
                                "untracked": [], "ignored": []})
    assert rec["verdict"] == "inconclusive"


def test_a_worktree_that_cannot_be_created_is_inconclusive_not_clean():
    # The tempting fallback — compare the tree with itself — would report
    # `clean` for a check that never ran.
    r = recording_runner([("worktree add", (128, "invalid reference: nope"))])
    rec = pc.differential(["harness-fast"], ref="nope", runner=r,
                          dirt={"ok": True, "tracked_modified": [],
                                "untracked": [], "ignored": []})
    assert rec["verdict"] == "inconclusive"
    assert "invalid reference" in rec["error"]


def test_the_round_355_finding_reproduces_end_to_end():
    """The regression pin: green here, one failure from git alone."""
    r = recording_runner([
        ("worktree add", (0, "")),
        ("worktree remove", (0, "")),
        ("@/tmp/wt", FAIL_PARITY),          # the pristine tree's run
        ("pytest", PASS),                   # the live tree's run
    ])
    rec = pc.differential(["whence-fast"], runner=r, worktree_path="/tmp/wt",
                          dirt={"ok": True, "tracked_modified": [],
                                "untracked": ["examples/gateway.lang"],
                                "ignored": []})
    assert rec["verdict"] == "git_incomplete"
    res = rec["results"][0]
    assert res["pristine_only"] == [
        "tests/test_lexer_guest_parity.py"
        "::test_small_example_files_lex_identically"]
    assert res["live_counts"]["passed"] == 476
    assert res["pristine_counts"]["failed"] == 1


def test_the_worst_verdict_across_suites_is_the_records_verdict():
    r = recording_runner([
        ("worktree", (0, "")),
        ("@/tmp/wt/languages/whence", FAIL_PARITY),
        ("pytest", PASS),
    ])
    rec = pc.differential(["harness-fast", "whence-fast"], runner=r,
                          worktree_path="/tmp/wt",
                          dirt={"ok": True, "tracked_modified": [],
                                "untracked": [], "ignored": []})
    assert [x["verdict"] for x in rec["results"]] == ["clean", "git_incomplete"]
    assert rec["verdict"] == "git_incomplete"


# --------------------------------------------------------------------------
# ledger
# --------------------------------------------------------------------------

def test_ledger_round_trips_and_skips_a_corrupt_line(tmp_path):
    p = str(tmp_path / "l.jsonl")
    pc.append_ledger({"ref": "HEAD", "verdict": "clean"}, p)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("{ truncated\n\n")
    pc.append_ledger({"ref": "HEAD", "verdict": "git_incomplete"}, p)
    got = pc.read_ledger(p)
    assert [r["verdict"] for r in got] == ["clean", "git_incomplete"]


def test_a_missing_ledger_reads_as_empty_not_as_a_pass(tmp_path):
    assert pc.read_ledger(str(tmp_path / "absent.jsonl")) == []


def test_status_on_an_empty_ledger_exits_nonzero(tmp_path, capsys):
    rc = pc.main(["status", "--ledger", str(tmp_path / "absent.jsonl")])
    assert rc == 3
    assert "absence of evidence" in capsys.readouterr().out


def test_exit_codes_distinguish_the_verdicts():
    assert pc._EXIT["clean"] == 0
    assert pc._EXIT["git_incomplete"] == 1
    assert pc._EXIT["untracked_breaks_test"] == 1
    assert pc._EXIT["both_failed"] == 2
    assert pc._EXIT["dirty_worktree"] == 3
    assert pc._EXIT["inconclusive"] == 3
    assert set(pc._EXIT) == {"clean", "git_incomplete", "untracked_breaks_test",
                             "both_failed", "dirty_worktree", "inconclusive"}


def test_every_verdict_compare_can_emit_has_an_exit_code():
    # A verdict with no `_EXIT` entry silently becomes 3 ("inconclusive"),
    # which would hide a real finding behind a plumbing code.
    emitted = {pc.compare(_run(a), _run(b))["verdict"]
               for a, b in [([], []), ([], ["x"]), (["x"], []), (["x"], ["x"])]}
    emitted.add(pc.compare(_run([], completed=False), _run([]))["verdict"])
    assert emitted <= set(pc._EXIT)


def test_the_formatter_names_the_failing_node_ids():
    out = pc._fmt({
        "ref": "HEAD", "verdict": "git_incomplete", "untracked_count": 14,
        "allowed_dirty": [], "blocking_dirty": [],
        "results": [{"suite": "whence-fast", "verdict": "git_incomplete",
                     "pristine_only": ["t.py::k"], "live_only": [], "both": [],
                     "live_counts": {}, "pristine_counts": {},
                     "duration_s": 1.0}]})
    assert "GIT-INCOMPLETE  t.py::k" in out
    assert "14 untracked" in out


def test_the_formatter_tells_a_dirty_tree_what_to_do_about_it():
    out = pc._fmt({"ref": "HEAD", "verdict": "dirty_worktree",
                   "untracked_count": 0, "blocking_dirty": ["a.md"],
                   "allowed_dirty": [], "results": []})
    assert "a.md" in out and "Commit or stash" in out


# --------------------------------------------------------------------------
# against real git — the two things a fake would let me get wrong
# --------------------------------------------------------------------------

def _repo(tmp_path):
    def g(*a):
        subprocess.run(["git"] + list(a), cwd=str(tmp_path), check=True,
                       capture_output=True)
    g("init", "-q")
    g("config", "user.email", "t@t.com")
    g("config", "user.name", "t")
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "tracked.txt").write_text("v1\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-qm", "init")
    return g


def test_real_porcelain_output_classifies_as_expected(tmp_path):
    g = _repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("v2\n", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("x\n", encoding="utf-8")
    got = pc.worktree_dirt(repo=str(tmp_path))
    assert got["ok"] is True
    assert "tracked.txt" in got["tracked_modified"]
    assert "untracked.txt" in got["untracked"]
    assert "ignored.txt" in got["ignored"]
    assert "untracked.txt" not in got["tracked_modified"]
    del g


def test_a_real_worktree_holds_tracked_content_and_nothing_else(tmp_path):
    _repo(tmp_path)
    (tmp_path / "untracked.txt").write_text("x\n", encoding="utf-8")
    wt = str(tmp_path / "wt")
    with pc.PristineWorktree(ref="HEAD", path=wt, repo=str(tmp_path)) as w:
        assert os.path.exists(os.path.join(w.path, "tracked.txt"))
        assert not os.path.exists(os.path.join(w.path, "untracked.txt"))
        # `git ls-files` must work INSIDE it — the fix this checker
        # recommends depends on that.
        out = subprocess.run(["git", "ls-files"], cwd=w.path, check=True,
                             capture_output=True, text=True)
        assert "tracked.txt" in out.stdout
    assert not os.path.exists(wt)


def test_a_real_worktree_is_removed_even_when_the_body_raises(tmp_path):
    # Rule 4. This program's recurring failure mode is leaving something
    # allocated that nobody reads.
    _repo(tmp_path)
    wt = str(tmp_path / "wt2")
    with pytest.raises(ZeroDivisionError):
        with pc.PristineWorktree(ref="HEAD", path=wt, repo=str(tmp_path)):
            1 / 0
    assert not os.path.exists(wt)
    out = subprocess.run(["git", "worktree", "list"], cwd=str(tmp_path),
                         check=True, capture_output=True, text=True)
    assert "wt2" not in out.stdout


def test_a_worktree_dirtied_by_the_suite_is_still_removed(tmp_path):
    # `--force`: a suite that writes scratch files into the pristine tree
    # must not be able to leave the worktree behind.
    _repo(tmp_path)
    wt = str(tmp_path / "wt3")
    with pc.PristineWorktree(ref="HEAD", path=wt, repo=str(tmp_path)) as w:
        with open(os.path.join(w.path, "tracked.txt"), "w") as fh:
            fh.write("scratch\n")
        with open(os.path.join(w.path, "new_scratch.txt"), "w") as fh:
            fh.write("scratch\n")
    assert not os.path.exists(wt)


def test_a_bad_ref_raises_rather_than_silently_using_the_live_tree(tmp_path):
    _repo(tmp_path)
    with pytest.raises(RuntimeError):
        with pc.PristineWorktree(ref="no-such-ref",
                                 path=str(tmp_path / "wt4"),
                                 repo=str(tmp_path)):
            pass


# --------------------------------------------------------------------------
# the registry describes suites this repo really has
# --------------------------------------------------------------------------

def test_every_registered_suite_points_at_a_real_directory():
    for name, spec in pc.SUITES.items():
        d = os.path.normpath(os.path.join(pc.REPO_ROOT, spec["cwd"]))
        assert os.path.isdir(d), (name, d)


def test_the_harness_fast_suite_matches_what_run_tests_fast_sh_runs():
    # If these drift, the checker is answering about a suite the driver
    # does not run, and its `clean` says nothing about the round signal.
    sh = open(os.path.join(pc.REPO_ROOT, "harness", "run_tests_fast.sh"),
              encoding="utf-8").read()
    assert '-m "not swe_slow" harness/tests/' in sh
    assert pc.SUITES["harness-fast"]["argv"] == [
        "-q", "-m", "not swe_slow", "harness/tests/"]


def test_the_whence_suites_keep_round_349s_config_routing():
    # `-c pytest.ini` exists because an untracked gateway `pyproject.toml`
    # sits in that rootdir. Dropping it would make the checker's live run
    # differ from the pristine one for a reason that is not the finding.
    for name in ("whence-fast", "whence-slow"):
        argv = pc.SUITES[name]["argv"]
        assert argv[:2] == ["-c", "pytest.ini"], name


def test_the_ledger_lives_under_state():
    assert pc.DEFAULT_LEDGER.startswith(os.path.join(pc.REPO_ROOT, "state"))


def test_suites_subcommand_lists_them(capsys):
    assert pc.main(["suites"]) == 0
    out = capsys.readouterr().out
    for name in pc.SUITES:
        assert name in out


def test_bare_invocation_prints_help_and_exits_nonzero(capsys):
    assert pc.main([]) == 2


def test_the_curated_corpus_rule_has_exactly_two_implementations():
    """Round 355 duplicated `git ls-files` enumeration into the whence suite.

    That was deliberate (the language suite must not import `harness/`), and
    this pins the count so a THIRD copy has to be a decision rather than an
    accident. The checker itself is what catches the two drifting apart.
    """
    roots = [os.path.join(pc.REPO_ROOT, "harness", "swe", "fuzz.py"),
             os.path.join(pc.REPO_ROOT, "languages", "whence", "tests",
                          "test_lexer_guest_parity.py")]
    for p in roots:
        assert '"git", "ls-files", "examples"' in open(p, encoding="utf-8").read(), p
    others = subprocess.run(
        ["git", "grep", "-l", '"git", "ls-files", "examples"'],
        cwd=pc.REPO_ROOT, capture_output=True, text=True)
    # THIS FILE quotes the literal in order to census it, so it matches
    # itself — but only once committed, because `git grep` reads tracked
    # content. Uncommitted it passed; the commit turned it red. Excluding
    # the census's own path is the fix; do not "repair" this by dropping
    # the assertion, and do not stop quoting the literal (a census that
    # spelled its needle in pieces would not survive a rename).
    SELF = "harness/tests/test_pristine_check.py"
    found = {l for l in others.stdout.splitlines()
             if l.endswith(".py") and l != SELF}
    assert found == {"harness/swe/fuzz.py",
                     "languages/whence/tests/test_lexer_guest_parity.py"}, found


# --------------------------------------------------------------------------
# the record says which commit it is about
# --------------------------------------------------------------------------

def test_resolve_ref_returns_the_sha(tmp_path):
    _repo(tmp_path)
    got = pc.resolve_ref("HEAD", repo=str(tmp_path))
    assert got and len(got) == 40 and all(c in "0123456789abcdef" for c in got)


def test_resolve_ref_returns_none_rather_than_guessing():
    r = recording_runner([("rev-parse", (128, "unknown revision"))])
    assert pc.resolve_ref("nope", runner=r) is None


def test_the_record_pins_the_commit_not_just_the_ref_name():
    # A stored `"ref": "HEAD"` is a moving target: read tomorrow it would
    # claim a verdict about a different commit.
    r = recording_runner([("rev-parse", (0, "a" * 40 + "\n")),
                          ("pytest", PASS), ("worktree", (0, ""))])
    rec = pc.differential(["harness-fast"], runner=r, worktree_path="/tmp/wt",
                          dirt={"ok": True, "tracked_modified": [],
                                "untracked": [], "ignored": []})
    assert rec["resolved"] == "a" * 40
    assert rec["ref"] == "HEAD"


def test_the_formatter_shows_the_resolved_commit():
    out = pc._fmt({"ref": "HEAD", "resolved": "abc123def456789", "verdict":
                   "clean", "untracked_count": 0, "allowed_dirty": [],
                   "blocking_dirty": [], "results": []})
    assert "abc123def456" in out


def test_an_unresolvable_ref_formats_as_unresolved_not_as_blank():
    out = pc._fmt({"ref": "HEAD", "resolved": None, "verdict": "clean",
                   "untracked_count": 0, "allowed_dirty": [],
                   "blocking_dirty": [], "results": []})
    assert "unresolved" in out


# --------------------------------------------------------------------------
# Round 373 — rule 1's waiver can come from the content-pinned escalation
# registry instead of a hand-typed --allow-dirty at every invocation.
# --------------------------------------------------------------------------

def _esc_registry(tmp_path, repo, path, suite_neutral=True, blobs=None):
    import sys as _sys
    _sys.path.insert(0, os.path.join(
        pc.REPO_ROOT, "skills", "session-inheritance-audit", "scripts"))
    import check_round_recorded as crr
    wt, hd = blobs or (crr.worktree_blob_hash(path, repo),
                       crr.head_blob_hash(path, repo))
    entry = {"reason": "adjudicated round 349. More.", "escalated_round": 349,
             "worktree_blob": wt, "head_blob": hd}
    if suite_neutral is not None:
        entry["suite_neutral"] = suite_neutral
    p = tmp_path / "esc.json"
    p.write_text(json.dumps({"escalations": {path: entry}}))
    return str(p)


def _dirty_repo(tmp_path, name="doc.md"):
    repo = tmp_path / "repo"
    repo.mkdir()
    for a in (["init", "-q"], ["config", "user.email", "t@t.com"],
              ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(repo)] + a, check=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    f = repo / name
    f.write_text("original\n")
    subprocess.run(["git", "-C", str(repo), "add", name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "b"],
                    check=True)
    f.write_text("rewritten by a separate system\n")
    return repo, f


def test_escalation_allowed_dirty_waives_a_pinned_suite_neutral_path(tmp_path):
    repo, _ = _dirty_repo(tmp_path)
    reg = _esc_registry(tmp_path, str(repo), "doc.md")
    dirt = {"ok": True, "tracked_modified": ["doc.md"], "untracked": [],
            "ignored": []}
    assert pc.escalation_allowed_dirty(
        dirt, repo=str(repo), registry_path=reg) == {"doc.md"}


def test_escalation_waiver_disappears_when_the_pin_expires(tmp_path):
    repo, f = _dirty_repo(tmp_path)
    reg = _esc_registry(tmp_path, str(repo), "doc.md")
    f.write_text("edited AGAIN by the separate system\n")
    dirt = {"ok": True, "tracked_modified": ["doc.md"], "untracked": [],
            "ignored": []}
    assert pc.escalation_allowed_dirty(
        dirt, repo=str(repo), registry_path=reg) == set()


def test_escalation_waiver_requires_the_suite_neutral_claim(tmp_path):
    # Being escalated says nothing about whether the diff can move a suite.
    repo, _ = _dirty_repo(tmp_path)
    dirt = {"ok": True, "tracked_modified": ["doc.md"], "untracked": [],
            "ignored": []}
    for flag in (False, None):
        reg = _esc_registry(tmp_path, str(repo), "doc.md", suite_neutral=flag)
        assert pc.escalation_allowed_dirty(
            dirt, repo=str(repo), registry_path=reg) == set(), flag


def test_escalation_waiver_empty_when_registry_missing(tmp_path):
    repo, _ = _dirty_repo(tmp_path)
    dirt = {"ok": True, "tracked_modified": ["doc.md"], "untracked": [],
            "ignored": []}
    assert pc.escalation_allowed_dirty(
        dirt, repo=str(repo),
        registry_path=str(tmp_path / "nope.json")) == set()


def test_escalation_waiver_only_covers_paths_the_dirt_reports():
    # The classifier is fed the SAME dirt snapshot rule 1 is applied to, so
    # a registry path that is not dirty in this snapshot waives nothing.
    dirt = {"ok": True, "tracked_modified": [], "untracked": [],
            "ignored": []}
    assert pc.escalation_allowed_dirty(dirt) == set()


def test_differential_records_a_pinned_waiver_separately_from_a_hand_one(tmp_path):
    repo, _ = _dirty_repo(tmp_path)
    r = recording_runner([("pytest", PASS)])
    rec = pc.differential(
        ["harness-fast"], runner=r, repo=str(repo),
        escalation_allow=["doc.md"],
        dirt={"ok": True, "untracked": [], "ignored": [],
              "tracked_modified": ["doc.md"]})
    assert rec["verdict"] == "clean"
    assert rec["allowed_dirty"] == []
    assert rec["escalation_allowed_dirty"] == ["doc.md"]
    assert "escalation pin, suite-neutral" in pc._fmt(rec)


def test_a_pinned_waiver_shows_in_status_text_as_a_pin_not_a_hand_waiver():
    rec = {"ref": "HEAD", "resolved": "abc", "verdict": "clean",
           "untracked_count": 0, "blocking_dirty": [], "allowed_dirty": [],
           "escalation_allowed_dirty": ["languages/whence/SECURITY.md"],
           "results": []}
    text = pc._fmt(rec)
    assert "escalation pin, suite-neutral" in text
    assert "waived by hand" not in text


def test_dirt_preview_agrees_with_what_check_will_waive(tmp_path, capsys,
                                                         monkeypatch):
    # A preview that disagrees with the thing it previews is worse than no
    # preview: `dirt` used blocking_dirt's default allow (standing only), so
    # it reported a pinned, suite-neutral escalation as BLOCKING while
    # `check` was about to waive it.
    monkeypatch.setattr(pc, "worktree_dirt", lambda **kw: {
        "ok": True, "tracked_modified": ["doc.md"], "untracked": [],
        "ignored": []})
    monkeypatch.setattr(
        pc, "escalation_allowed_dirty",
        lambda dirt, repo=None, registry_path=None: set())
    # first: with no waiver in effect the path blocks
    rc = pc.main(["dirt"])
    out = capsys.readouterr().out
    assert rc == 3 and "BLOCKING  doc.md" in out

    monkeypatch.setattr(
        pc, "escalation_allowed_dirty",
        lambda dirt, repo=None, registry_path=None: {"doc.md"})
    rc = pc.main(["dirt"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "pinned-waiver (escalation, suite-neutral)  doc.md" in out
    assert "BLOCKING" not in out


# ------------------------------------------------------- round 379 (harness A) --
#
# `status` re-prints a stored verdict and, until this round, printed exactly
# what `check` prints for a fresh one. Two rounds read the second as the
# first: `driver_health` quoted a round-373 row into `driver.log` as rounds
# 374-378's own health-check result, and round 374 concluded from that line
# that the driver runs a pristine whence-slow differential every round. It
# runs none — the driver runs three FAST suites on the live tree and never
# invokes this module.

_REC = {"ref": "HEAD", "resolved": "91acd9c5af97d71a4e1c506f3e568c5fffe5ea9c",
        "recorded_at": "2026-08-30T17:53:28Z", "verdict": "clean",
        "untracked_count": 17, "suites": ["whence-slow"],
        "blocking_dirty": [], "results": []}
#: `calendar.timegm` of _REC["recorded_at"]. Spelled as the number rather
#: than computed from the string so the test cannot agree with the code by
#: sharing its bug.
_REC_EPOCH = 1788112408


def test_status_says_a_stored_verdict_is_not_a_run():
    lines = pc.status_freshness(_REC, now=_REC_EPOCH + 3600, head=_REC["resolved"])
    assert lines[0].startswith("RECORDED 2026-08-30T17:53:28Z (1.0 h ago)")
    assert "not a run just now" in lines[0]
    assert "HEAD is still 91acd9c5af97" in lines[1]


def test_status_flags_that_head_has_moved_since_the_record():
    lines = pc.status_freshness(_REC, now=_REC_EPOCH + 3600, head="8fc29564d62d0")
    assert "HEAD HAS MOVED SINCE" in lines[1]
    assert "NOT about the current tree" in lines[1]
    # The commit it WAS measured at stays in the line: a reader has to be
    # able to go and look at that tree.
    assert "91acd9c5af97" in lines[1]


def test_status_age_is_utc_and_does_not_move_with_the_hosts_timezone():
    # `time.mktime(strptime(utc))` reads a UTC stamp as local time and is
    # right only on a UTC box — which this host is, so the bug would have
    # been invisible here. `calendar.timegm` is the fix; this test is what
    # says so on any other host.
    import time as _time
    saved = os.environ.get("TZ")
    try:
        answers = []
        for tz in ("UTC", "America/New_York", "Asia/Bangkok"):
            os.environ["TZ"] = tz
            try:
                _time.tzset()
            except AttributeError:            # non-POSIX; nothing to test
                pytest.skip("time.tzset unavailable")
            answers.append(pc.status_freshness(
                _REC, now=_REC_EPOCH + 7200, head=None)[0])
        assert len(set(answers)) == 1, answers
        assert "(2.0 h ago)" in answers[0]
    finally:
        if saved is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = saved
        _time.tzset()


def test_status_never_claims_a_tree_when_the_commit_is_unknown():
    rec = dict(_REC); rec["resolved"] = None
    lines = pc.status_freshness(rec, now=_REC_EPOCH, head=None)
    assert "commit unknown" in lines[1]
    assert "HEAD" not in lines[1] or "HAS MOVED" not in lines[1]


def test_status_prints_the_freshness_lines_before_the_verdict(tmp_path, capsys,
                                                              monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps(_REC) + "\n")
    monkeypatch.setattr(pc, "resolve_ref", lambda *a, **k: "8fc29564d62d0")
    rc = pc.main(["status", "--ledger", str(ledger)])
    out = capsys.readouterr().out.splitlines()
    assert rc == 0                       # exit code is the verdict, unchanged
    assert out[0].startswith("RECORDED ")
    assert "HEAD HAS MOVED SINCE" in out[1]
    assert out[2].startswith("ref HEAD (91acd9c5af97)   verdict clean")

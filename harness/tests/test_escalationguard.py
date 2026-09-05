"""Tests for `harness/escalationguard.py` (round 475, harness A).

Every git-touching test builds a REAL throwaway repository with
`subprocess`. No mock of `git` appears here on purpose: the module's whole
job is to be right about what git records, and a mock would only assert
that this round's mental model of git agrees with itself. The end-to-end
hook test in particular runs `git commit` and checks that the commit did
not happen -- a hook that returns 1 in a unit test but that git ignores
would pass every other assertion in this file.
"""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import escalationguard as eg  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GIT_ENV = dict(os.environ,
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)


def git(repo, *args, check=True):
    out = subprocess.run(["git", "-C", str(repo)] + list(args),
                         capture_output=True, text=True, env=GIT_ENV)
    if check and out.returncode != 0:
        raise AssertionError("git %s failed: %s%s"
                             % (" ".join(args), out.stdout, out.stderr))
    return out


def write(repo, rel, body):
    full = os.path.join(str(repo), rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as fh:
        fh.write(body)
    return full


def write_registry(repo, entries):
    write(repo, eg.REGISTRY_REL,
          json.dumps({"_comment": "test", "escalations": entries}, indent=2))


@pytest.fixture
def repo(tmp_path):
    """A real git repo with one tracked file `doc.md` at its BASE content,
    plus an ordinary file, plus an empty registry. Returns the path."""
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "commit.gpgsign", "false")
    write(r, "doc.md", "BASE\n")
    write(r, "other.txt", "ordinary\n")
    write_registry(r, {})
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "base")
    return r


def base_and_escalated(repo_path):
    """Return (base_blob, escalated_blob) for `doc.md`: the committed base,
    and the blob of the third-party rewrite once it is on disk."""
    base = eg.blob_at("HEAD", "doc.md", repo=str(repo_path))
    write(repo_path, "doc.md", "REWRITTEN BY A THIRD PARTY\n")
    return base, eg.worktree_blob("doc.md", repo=str(repo_path))


def escalate(repo_path):
    """Put `doc.md` in the escalated state: rewritten on disk, base at HEAD,
    registry pinned to that exact pair. Returns the entry dict."""
    base, esc = base_and_escalated(repo_path)
    entry = {"reason": "A third party rewrote this. Adjudicated round 1.",
             "escalated_round": 1,
             "worktree_blob": esc, "head_blob": base}
    write_registry(repo_path, {"doc.md": entry})
    return entry


# --------------------------------------------------------------- registry

def test_load_registry_reads_the_entries_and_skips_underscore_keys(tmp_path):
    p = tmp_path / "reg.json"
    p.write_text(json.dumps({
        "_comment": "x",
        "escalations": {"a.md": {"reason": "r"}, "_note": {"reason": "no"}},
    }))
    got = eg.load_registry(str(p))
    assert list(got) == ["a.md"]


def test_load_registry_degrades_to_empty_on_a_missing_or_broken_file(tmp_path):
    assert eg.load_registry(str(tmp_path / "nope.json")) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert eg.load_registry(str(bad)) == {}


def test_load_registry_degrades_to_empty_when_the_json_is_a_list(tmp_path):
    p = tmp_path / "list.json"
    p.write_text("[1, 2]")
    assert eg.load_registry(str(p)) == {}


# ------------------------------------------------------------------ index

def test_staged_paths_reports_adds_modifications_and_deletions(repo):
    write(repo, "new.md", "n\n")
    write(repo, "doc.md", "changed\n")
    os.remove(os.path.join(str(repo), "other.txt"))
    git(repo, "add", "-A")
    assert set(eg.staged_paths(repo=str(repo))) == {
        "new.md", "doc.md", "other.txt"}


def test_staged_paths_is_empty_with_a_clean_index(repo):
    assert eg.staged_paths(repo=str(repo)) == []


def test_staged_escalations_is_the_intersection_of_index_and_registry(repo):
    escalate(repo)
    write(repo, "other.txt", "touched\n")
    git(repo, "add", "-A")
    # `git add -A` stages BOTH the ordinary edit and the escalated one.
    assert "other.txt" in eg.staged_paths(repo=str(repo))
    assert eg.staged_escalations(repo=str(repo)) == ["doc.md"]


def test_staged_escalations_ignores_an_escalated_path_left_unstaged(repo):
    escalate(repo)
    git(repo, "add", "--", "other.txt")
    assert eg.staged_escalations(repo=str(repo)) == []


def test_staged_escalations_catches_a_staged_deletion_of_the_path(repo):
    escalate(repo)
    os.remove(os.path.join(str(repo), "doc.md"))
    git(repo, "add", "-A")
    assert eg.staged_escalations(repo=str(repo)) == ["doc.md"]


def test_staged_escalations_is_empty_when_the_registry_is(repo):
    write(repo, "doc.md", "x\n")
    git(repo, "add", "-A")
    assert eg.staged_escalations(repo=str(repo)) == []


# ------------------------------------------------------------------- fate

def test_resolve_fate_says_dirty_while_the_escalation_is_live(repo):
    entry = escalate(repo)
    got = eg.resolve_fate("doc.md", entry, repo=str(repo))
    assert got["fate"] == eg.FATE_DIRTY
    assert got["recommend"] == "keep"


def test_resolve_fate_says_committed_and_names_the_landing_commit(repo):
    entry = escalate(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "a commit that does not mention doc.md")
    got = eg.resolve_fate("doc.md", entry, repo=str(repo))
    assert got["fate"] == eg.FATE_COMMITTED
    assert [c["subject"] for c in got["landed_in"]] == [
        "a commit that does not mention doc.md"]
    assert got["restore_to"] == entry["head_blob"]
    assert got["recommend"] == "repair"


def test_a_committed_fate_never_recommends_deleting_the_entry(repo):
    """The checker's own remedy ('delete the entry') is the one action that
    must NOT be taken here: it erases the record of the violation."""
    entry = escalate(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "landed")
    assert eg.resolve_fate("doc.md", entry, repo=str(repo))["recommend"] \
        != "delete"


def test_resolve_fate_says_reverted_when_head_and_disk_are_the_base(repo):
    entry = escalate(repo)
    write(repo, "doc.md", "BASE\n")
    got = eg.resolve_fate("doc.md", entry, repo=str(repo))
    assert got["fate"] == eg.FATE_REVERTED
    assert got["recommend"] == "delete"


def test_a_revert_after_a_landing_still_names_the_commit_that_landed_it(repo):
    """Round 393's shape: committed, then repaired in a follow-up. The fate
    is REVERTED -- but the history must still say it happened."""
    entry = escalate(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "swept in by git add -A")
    write(repo, "doc.md", "BASE\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "restore to the escalated base")
    got = eg.resolve_fate("doc.md", entry, repo=str(repo))
    assert got["fate"] == eg.FATE_REVERTED
    assert [c["subject"] for c in got["landed_in"]] == ["swept in by git add -A"]


def test_resolve_fate_says_deleted_when_the_path_is_gone_everywhere(repo):
    entry = escalate(repo)
    os.remove(os.path.join(str(repo), "doc.md"))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "delete it")
    got = eg.resolve_fate("doc.md", entry, repo=str(repo))
    assert got["fate"] == eg.FATE_DELETED
    assert got["recommend"] == "delete"


def test_resolve_fate_is_unknown_for_an_entry_with_no_fingerprint(repo):
    got = eg.resolve_fate("doc.md", {"reason": "r"}, repo=str(repo))
    assert got["fate"] == eg.FATE_UNKNOWN
    assert "no fingerprint" in got["detail"]


def test_resolve_fate_is_unknown_when_a_third_state_appears(repo):
    """FAIL CLOSED. A base that moved under the pin is neither reverted nor
    committed, and calling it 'reverted' would silently retire a live
    escalation."""
    entry = escalate(repo)
    write(repo, "doc.md", "A THIRD, DIFFERENT CONTENT\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "something else entirely")
    got = eg.resolve_fate("doc.md", entry, repo=str(repo))
    assert got["fate"] == eg.FATE_UNKNOWN
    assert "re-inspect by hand" in got["detail"]


def test_path_history_carries_one_blob_per_touching_commit(repo):
    base, esc = base_and_escalated(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "second")
    rows = eg.path_history("doc.md", repo=str(repo))
    assert [r["blob"] for r in rows] == [esc, base]


def test_audit_covers_every_registry_entry(repo):
    escalate(repo)
    rows = eg.audit(repo=str(repo))
    assert [r["path"] for r in rows] == ["doc.md"]
    assert rows[0]["fate"] == eg.FATE_DIRTY


# ------------------------------------------------------------------- hook

def test_hook_script_carries_the_marker_and_calls_check():
    body = eg.hook_script()
    assert eg.HOOK_MARKER in body
    assert "escalationguard.py\" check" in body
    assert body.startswith("#!/bin/sh")


def test_the_hook_carries_all_four_advisory_steps_in_order():
    """Rounds 475 / 499 / 501 / 515. The hook is the ONLY place the author of
    a defect is still present -- the four health checks run after the agent
    process exits and write to `logs/`, which is not in git.

    Pinned as a LIST so that deleting a step is a test failure rather than a
    silently shorter hook. Round 515's step is the escapes check: three
    `test_swe_copyparity_real_subject.py` nodes have been reddened four
    times by rounds that could not run the suite that asserts them.
    """
    body = eg.hook_script()
    steps = ["escalationguard.py\" check",
             "wiring_audit.py\" undeclared --staged --quiet",
             "carryforward_check.py\" --staged-check --quiet",
             "copyparity.py\" escapes --staged"]
    at = [body.index(x) for x in steps]      # raises if any is missing
    assert at == sorted(at), "hook steps out of order: %r" % (at,)


def test_only_the_first_hook_step_can_refuse_a_commit():
    """The three advisory steps end in `|| true` on purpose. A gate here can
    refuse the commit of a round with no turns left to debug it, and losing a
    round's whole uncommitted diff is strictly worse than one more round of a
    red check -- this program has already lost 32 sessions to the turn cap.
    """
    body = eg.hook_script()
    blocking = [ln for ln in body.splitlines()
                if "|| exit 1" in ln]
    assert len(blocking) == 1 and "escalationguard.py" in blocking[0]
    for advisory in ("wiring_audit.py", "carryforward_check.py",
                     "copyparity.py"):
        line = [ln for ln in body.splitlines()
                if advisory in ln and ln.strip().startswith("python")]
        assert line and line[0].rstrip().endswith("|| true"), advisory


def test_hooks_dir_honours_core_hookspath(repo, tmp_path):
    alt = tmp_path / "myhooks"
    alt.mkdir()
    git(repo, "config", "core.hooksPath", str(alt))
    assert eg.hooks_dir(repo=str(repo)) == str(alt)


def test_install_hook_installs_then_reports_unchanged(repo):
    action, path = eg.install_hook(repo=str(repo))
    assert action == "installed"
    assert os.access(path, os.X_OK)
    assert eg.hook_status(repo=str(repo))[0] == "ours"
    assert eg.install_hook(repo=str(repo))[0] == "unchanged"


def test_install_hook_refuses_a_foreign_hook_unless_forced(repo):
    path = os.path.join(eg.hooks_dir(repo=str(repo)), "pre-commit")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("#!/bin/sh\necho someone elses hook\n")
    assert eg.hook_status(repo=str(repo))[0] == "foreign"
    assert eg.install_hook(repo=str(repo))[0] == "refused"
    with open(path) as fh:
        assert "someone elses hook" in fh.read()
    assert eg.install_hook(repo=str(repo), force=True)[0] == "installed"


def test_install_hook_refreshes_its_own_stale_hook(repo):
    _, path = eg.install_hook(repo=str(repo))
    with open(path, "a") as fh:
        fh.write("# drift\n")
    assert eg.install_hook(repo=str(repo))[0] == "updated"
    with open(path) as fh:
        assert "# drift" not in fh.read()


def test_the_installed_hook_actually_stops_a_real_git_commit(repo):
    """END TO END. Not 'the function returns 1' -- `git commit` must fail
    and the commit must not exist."""
    escalate(repo)
    eg.install_hook(repo=str(repo), python=sys.executable)
    # The hook resolves the module inside the TEST repo, so put it there.
    with open(os.path.join(REPO_ROOT, "escalationguard.py")) as fh:
        write(repo, "harness/escalationguard.py", fh.read())
    git(repo, "add", "-A")
    before = git(repo, "rev-parse", "HEAD").stdout.strip()
    out = git(repo, "commit", "-m", "git add -A sweeps it in", check=False)
    assert out.returncode != 0, out.stdout + out.stderr
    assert "REFUSING" in (out.stdout + out.stderr)
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == before


def test_the_installed_hook_lets_an_ordinary_commit_through(repo):
    escalate(repo)
    eg.install_hook(repo=str(repo), python=sys.executable)
    with open(os.path.join(REPO_ROOT, "escalationguard.py")) as fh:
        write(repo, "harness/escalationguard.py", fh.read())
    before = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "add", "--", "other.txt", "harness/escalationguard.py")
    write(repo, "other.txt", "ordinary edit\n")
    git(repo, "add", "--", "other.txt")
    out = git(repo, "commit", "-m", "an ordinary commit", check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    assert git(repo, "rev-parse", "HEAD").stdout.strip() != before


def test_the_hook_fails_open_when_the_registry_is_absent(repo):
    escalate(repo)
    os.remove(os.path.join(str(repo), eg.REGISTRY_REL))
    eg.install_hook(repo=str(repo), python=sys.executable)
    with open(os.path.join(REPO_ROOT, "escalationguard.py")) as fh:
        write(repo, "harness/escalationguard.py", fh.read())
    git(repo, "add", "-A")
    out = git(repo, "commit", "-m", "no registry", check=False)
    assert out.returncode == 0, out.stdout + out.stderr


# ------------------------------------------------------------------- main

def test_main_check_returns_one_and_explains_when_a_path_is_staged(repo,
                                                                   capsys):
    escalate(repo)
    git(repo, "add", "-A")
    rc = eg.main(["--repo", str(repo), "check"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "git restore --staged -- doc.md" in err


def test_main_check_returns_zero_on_a_clean_index(repo):
    escalate(repo)
    assert eg.main(["--repo", str(repo), "check"]) == 0


def test_main_audit_returns_one_on_a_committed_fate(repo):
    escalate(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "landed")
    assert eg.main(["--repo", str(repo), "audit"]) == 1


def test_main_audit_returns_zero_when_every_fate_is_benign(repo):
    escalate(repo)
    assert eg.main(["--repo", str(repo), "audit"]) == 0


def test_main_audit_json_is_parseable(repo, capsys):
    escalate(repo)
    eg.main(["--repo", str(repo), "audit", "--json"])
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["path"] == "doc.md"


def test_main_with_no_subcommand_is_a_usage_error(repo, capsys):
    assert eg.main(["--repo", str(repo)]) == 2


# ------------------------------------------------- this repo's own invariant

@pytest.mark.skipif(
    not os.path.isdir(os.path.join(REPO_ROOT, "..", ".git")),
    reason="not a git checkout")
def test_no_adjudicated_diff_of_this_repo_is_sitting_at_head():
    """THE REGRESSION THIS ROUND EXISTS FOR.

    Round 393 and round 474 each committed `languages/whence/SECURITY.md`
    -- a diff round 349 adjudicated as must-not-land -- via `git add -A`,
    81 rounds apart, neither mentioning it in the commit message. Nothing
    in the tree could go red for it: the pin is read by a checker that runs
    BEFORE a round, and by nothing at commit time. This is that missing
    assertion.

    If this goes red, do not delete the registry entry. Run
    `python3 harness/escalationguard.py audit` and repair HEAD.

    ROUND 485 (SWE-loop D) split this node in two. Round 475 wrote it with a
    vacuity guard as its FIRST assertion -- `assert rows, "... if that is a
    real resolution, this test should be deleted deliberately"` -- and round
    484 (NUC E) then legitimately emptied the registry: its record check
    reported `languages/whence/SECURITY.md` as a DEAD acknowledgement (the
    path had stopped being dirty, so the entry suppressed nothing and read as
    coverage) and deleted it. The regression assertion below is unaffected by
    an empty registry; it was the guard that went red, on the one event it was
    written to allow. Deleting the node -- which its own message offers --
    would delete the regression with it, so the guard moved to its own node
    where the emptiness is a statement somebody has to re-decide rather than a
    precondition of the assertion beneath it."""
    rows = eg.audit()
    committed = [r for r in rows if r["fate"] == eg.FATE_COMMITTED]
    assert not committed, "\n".join(
        "%s: %s" % (r["path"], r["detail"]) for r in committed)


@pytest.mark.skipif(
    not os.path.isdir(os.path.join(REPO_ROOT, "..", ".git")),
    reason="not a git checkout")
def test_the_escalated_diff_registry_is_empty_and_that_is_a_recorded_decision():
    """The vacuity guard round 475 attached to the node above, as its own
    assertion about a state somebody decided.

    The registry is EMPTY at round 485, and that is not neglect: round 349
    escalated `languages/whence/SECURITY.md` (the Hermes gateway, a separate
    autonomous system sharing this repo, had rewritten its authorship and
    licence sections); the entry was carried for 134 rounds and content-pinned
    the whole way; round 484's record check found the path no longer dirty and
    deleted the acknowledgement, which is exactly what this registry's own
    `_comment` requires -- *"an acknowledgement that suppresses nothing reads
    as coverage"*.

    When the next escalation is added this node goes RED, and that is the
    point: adding an entry is an assertion that a round inspected a specific
    diff, and somebody re-deciding what this test says is the cheapest
    available proof that somebody looked."""
    rows = eg.audit()
    assert rows == [], (
        "the registry is no longer empty -- an escalation has been added. "
        "Read it, confirm the reasoning is recorded, then re-pin this node:\n"
        + "\n".join("%s: %s" % (r["path"], r.get("detail", "")) for r in rows))


# ------------------------------------------------- the restore exemption

def test_staging_the_adjudicated_base_is_allowed(repo):
    """The repair must not be blocked by the guard that exists to protect
    it. Round 393's follow-up commit and round 475's repair are both this
    shape: the path is staged, and the staged bytes are the pinned base."""
    entry = escalate(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "the violation")
    write(repo, "doc.md", "BASE\n")
    git(repo, "add", "--", "doc.md")
    assert eg.staged_blob("doc.md", repo=str(repo)) == entry["head_blob"]
    assert eg.staged_escalations(repo=str(repo)) == []


def test_staging_a_third_content_is_still_refused(repo):
    """The exemption is on the BASE blob, not on 'any change that is not
    the escalated one'."""
    escalate(repo)
    write(repo, "doc.md", "SOME OTHER EDIT\n")
    git(repo, "add", "--", "doc.md")
    assert eg.staged_escalations(repo=str(repo)) == ["doc.md"]


def test_the_exemption_needs_a_pinned_base(repo):
    """An entry with no `head_blob` has no base to restore to, so no
    staged content can claim the exemption."""
    base, esc = base_and_escalated(repo)
    write_registry(repo, {"doc.md": {"reason": "r", "escalated_round": 1,
                                     "worktree_blob": esc}})
    git(repo, "add", "--", "doc.md")
    assert eg.staged_blob("doc.md", repo=str(repo)) == esc
    assert eg.staged_escalations(repo=str(repo)) == ["doc.md"]


def test_the_hook_lets_the_repair_commit_through(repo):
    """END TO END, for the exemption: `git commit` must SUCCEED."""
    escalate(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "the violation")
    eg.install_hook(repo=str(repo), python=sys.executable)
    with open(os.path.join(REPO_ROOT, "escalationguard.py")) as fh:
        write(repo, "harness/escalationguard.py", fh.read())
    write(repo, "doc.md", "BASE\n")
    git(repo, "add", "-A")
    out = git(repo, "commit", "-m", "restore the escalated base", check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    assert eg.blob_at("HEAD", "doc.md", repo=str(repo)) == \
        eg.load_registry(repo=str(repo))["doc.md"]["head_blob"]

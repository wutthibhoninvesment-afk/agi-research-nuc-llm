"""Tests for `harness/swe/ledgerreplay.py` — the slow-tier ledger replayed
against git history (round 367, harness A).

Deliberately NOT named `test_swe_*.py`, for the same reason
`test_slowtier.py` is not: `conftest.py` marks that prefix `swe_slow`, and a
module whose whole purpose is to reason about the slow tier belongs in the
fast tier.

Every test but the last two builds its OWN git repository in `tmp_path` and
commits into it, so the assertions are about a tree the test controls rather
than about this repo's history, which changes under them every round. The
two that do read the real repo say so in their names and assert only
properties that cannot rot (the digest function agrees with itself; the
window is non-empty).
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swe.ledgerreplay as LR
import swe.readscope as RS
import swe.slowtier as ST


# ------------------------------------------------------------- scratch repo --

def _run(args, cwd):
    subprocess.check_call(args, cwd=cwd,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _write(root, rel, text):
    full = os.path.join(root, rel)
    d = os.path.dirname(full)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(full, "w", encoding="utf-8") as f:
        f.write(text)


#: Commits are stamped a minute apart. Without this every commit a test makes
#: lands in the same second, `commit_times` returns identical timestamps, and
#: `replay_actual`'s "last commit at or before `finished_at`" anchor has no
#: order to work with — the test would fail for a reason that says nothing
#: about the code.
_CLOCK = [1_700_000_000]


def _commit(root, msg):
    _CLOCK[0] += 60
    stamp = "%d +0000" % _CLOCK[0]
    env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    _run(["git", "add", "-A"], root)
    subprocess.check_call(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                           "commit", "-q", "-m", msg], cwd=root, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                   cwd=root).decode().strip()


@pytest.fixture
def repo(tmp_path):
    """A miniature of this repo: `languages/whence/` + `harness/`.

    Three commits, each moving a different thing, which is what the policy
    tests need: c1 is the baseline, c2 edits a file INSIDE `whence/`, c3
    edits one only in `examples/`.
    """
    root = str(tmp_path / "r")
    os.makedirs(root)
    _run(["git", "init", "-q", "-b", "main"], root)
    _write(root, "languages/whence/whence/interp.py", "x = 1\n")
    _write(root, "languages/whence/examples/a.lang", "let a = 1\n")
    _write(root, "languages/whence/SPEC.md", "# spec\n")
    _write(root, "harness/swe/__init__.py", "")
    _write(root, "harness/swe/proc.py", "P = 1\n")
    _write(root, "harness/swe/fuzz.py", "F = 1\n")
    _write(root, "harness/tests/__init__.py", "")
    _write(root, "harness/tests/conftest.py", "# conftest\n")
    _write(root, "harness/tests/test_swe_fake.py", "import swe.proc\n")
    c1 = _commit(root, "c1")
    _write(root, "languages/whence/whence/interp.py", "x = 2\n")
    c2 = _commit(root, "c2 edits whence/")
    _write(root, "languages/whence/examples/a.lang", "let a = 2\n")
    c3 = _commit(root, "c3 edits examples/")
    return {"root": root, "repo": LR.Repo(root=root), "revs": [c1, c2, c3]}


# ------------------------------------------------ the digests are the same --

def test_checkout_digest_at_equals_the_live_function_on_the_same_tree(repo):
    """The load-bearing claim of the whole module: the git-object digest is
    not a lookalike of `slowtier.checkout_digest`, it is that function."""
    live = ST.checkout_digest(os.path.join(repo["root"], "languages", "whence"))
    assert LR.checkout_digest_at(repo["repo"], repo["revs"][-1]) == live


def test_checkout_digest_at_moves_only_for_source_extensions(repo):
    r, root = repo["repo"], repo["root"]
    before = LR.checkout_digest_at(r, repo["revs"][-1])
    _write(root, "languages/whence/NOTES.md", "prose\n")
    doc = _commit(root, "doc only")
    assert LR.checkout_digest_at(r, doc) == before
    _write(root, "languages/whence/examples/b.lang", "let b = 1\n")
    lang = _commit(root, "a .lang")
    assert LR.checkout_digest_at(r, lang) != before


def test_dir_digest_at_equals_readscope_and_is_not_recursive(repo):
    r, root = repo["repo"], repo["root"]
    whence = os.path.join(root, "languages", "whence")
    for d in (".", "whence", "examples"):
        assert LR.dir_digest_at(r, repo["revs"][-1], d) == \
            RS.dir_digest(whence, d)
    before = LR.dir_digest_at(r, repo["revs"][-1], ".")
    _write(root, "languages/whence/whence/parser.py", "y = 1\n")
    deeper = _commit(root, "a file in a SUBdirectory of .")
    assert LR.dir_digest_at(r, deeper, ".") == before        # not recursive
    assert LR.dir_digest_at(r, deeper, "whence") != \
        LR.dir_digest_at(r, repo["revs"][-1], "whence")


def test_dir_digest_at_reports_missing_like_a_failed_listdir(repo):
    assert LR.dir_digest_at(repo["repo"], repo["revs"][0], "nope") == "<missing>"


def test_dir_digest_at_is_extension_blind(repo):
    """`readscope.dir_digest(exts=None)`'s rule: a file ADDED beside one that
    was read counts, whatever it is called."""
    r, root = repo["repo"], repo["root"]
    before = LR.dir_digest_at(r, repo["revs"][-1], "examples")
    _write(root, "languages/whence/examples/README", "hi\n")
    after = _commit(root, "a README in examples/")
    assert LR.dir_digest_at(r, after, "examples") != before


# --------------------------------------------------------------- the scope --

def test_scope_digests_track_the_directory_not_the_record(repo):
    """Regression pin for a bug round 367 wrote and nearly shipped.

    `scopes[f]` is a `readscope` RECORD (`{ok, dirs, opaque}`). `RevState`
    read it as if it were the directory LIST, so `scope_digests_at` iterated
    the dict's keys and digested three directories called "ok", "dirs" and
    "opaque" — all `<missing>`, all constant across history, i.e. a scoped
    policy that could never be invalidated and therefore always won. The
    failure mode is silent and flattering, which is the dangerous kind.
    """
    r = repo["repo"]
    record = {"ok": True, "dirs": ["whence"], "opaque": []}
    states = LR.build_states(r, repo["revs"], ["test_swe_fake.py"],
                             {"test_swe_fake.py": record})
    for s in states:
        assert sorted(s.scope["test_swe_fake.py"]) == ["whence"]
        assert s.scope["test_swe_fake.py"]["whence"] != "<missing>"
    # c1 -> c2 edits whence/interp.py, so the scope MUST move.
    assert states[0].scope["test_swe_fake.py"] != \
        states[1].scope["test_swe_fake.py"]
    # c2 -> c3 edits only examples/, so it must NOT.
    assert states[1].scope["test_swe_fake.py"] == \
        states[2].scope["test_swe_fake.py"]


# ------------------------------------------------------------- the policies --

def _states(repo, scope=None, f="test_swe_fake.py"):
    scopes = {f: scope} if scope is not None else {}
    return LR.build_states(repo["repo"], repo["revs"], [f], scopes)


def test_strict_lifetime_counts_commits_until_the_first_invalidation(repo):
    """An entry made at c1 dies at c2 (whence/ moved), so it lives 0 commits;
    one made at c2 survives c3 only if nothing it depends on moved — and
    under the strict rule the whole-checkout digest DID move."""
    st = _states(repo)
    assert LR.survival(st, "test_swe_fake.py", None, "strict") == [0, 0]


def test_the_scoped_policy_outlives_strict_when_the_edit_is_outside_it(repo):
    """The mechanism round 361 shipped, stated as an experiment: a
    `whence`-scoped entry made at c2 survives c3, which edits only
    `examples/`. The strict rule kills it, the scoped rule does not."""
    scope = {"ok": True, "dirs": ["whence"], "opaque": []}
    st = _states(repo, scope)
    strict = LR.survival(st, "test_swe_fake.py", scope, "strict")
    scoped = LR.survival(st, "test_swe_fake.py", scope, "scoped")
    assert strict == [0, 0]
    assert scoped == [0, 1]          # c1 still dies at c2; c2 survives c3


def test_an_empty_scope_survives_every_subject_edit(repo):
    """`test_swe_triage.py` reads nothing under the checkout. That is a
    measurement, and it makes the entry immune to the subject half entirely
    — which is exactly why the two empty-scope files are the only rows this
    repo's `status()` still calls conclusive-at-any-strength."""
    scope = {"ok": True, "dirs": [], "opaque": []}
    st = _states(repo, scope)
    assert LR.survival(st, "test_swe_fake.py", scope, "scoped") == [2, 1]


def test_the_harness_half_is_what_the_subject_policy_ignores(repo):
    """`subject` is not a shippable policy; it exists to say WHICH half is
    binding. Move a harness dependency and `scoped` dies where `subject`
    does not."""
    root = repo["root"]
    _write(root, "harness/swe/proc.py", "P = 2\n")
    rev4 = _commit(root, "c4 edits a harness dep")
    revs = repo["revs"] + [rev4]
    scope = {"ok": True, "dirs": ["whence"], "opaque": []}
    f = "test_swe_fake.py"
    st = LR.build_states(repo["repo"], revs, [f], {f: scope})
    # start at c2: c3 (examples only) is survivable, c4 (swe/proc.py) is not.
    assert LR.survival(st, f, scope, "scoped")[1] == 1
    assert LR.survival(st, f, scope, "subject")[1] == 2


def test_blame_names_the_dependency_that_ended_the_entry(repo):
    root = repo["root"]
    _write(root, "harness/swe/proc.py", "P = 2\n")
    rev4 = _commit(root, "c4 edits a harness dep")
    f = "test_swe_fake.py"
    scope = {"ok": True, "dirs": ["whence"], "opaque": []}
    st = LR.build_states(repo["repo"], repo["revs"] + [rev4], [f], {f: scope})
    causes = dict(LR.blame(st, [f], {f: scope})["by_cause"])
    # Three start commits (c1, c2, c3; the last commit has no future).
    # c1 dies at c2, inside its own scope. c2 survives c3 (examples only) and
    # dies at c4. c3 dies at c4. So the harness dep is blamed twice and the
    # scope directory once — and blaming per START, not per commit, is the
    # point: it is "how much recall did this file cost", not "how often did
    # it change".
    assert causes.get("harness:swe/proc.py") == 2
    assert causes.get("scope:whence") == 1
    assert LR.blame(st, [f], {f: scope})["n_kills"] == 3


def test_the_dep_scan_runs_against_the_REVISION_not_the_working_tree(repo):
    """`RevSources` exists so `slowtier.harness_deps` can scan a git
    revision. If it silently fell back to the live harness, every dep digest
    in a replay would be this repo's, and the whole measurement would be
    about the wrong tree."""
    src = LR.RevSources(repo["repo"], repo["revs"][0])
    deps = ST.harness_deps("test_swe_fake.py", sources=src)
    assert deps == ["swe/__init__.py", "swe/proc.py", "tests/__init__.py",
                    "tests/conftest.py", "tests/test_swe_fake.py"]
    assert "swe/fuzz.py" not in deps            # present in the repo, unimported
    digs = src.digests(deps)
    assert set(digs) == set(deps) and "<missing>" not in digs.values()


def test_a_revision_with_no_harness_at_all_falls_back_instead_of_crashing(repo):
    """Fail-closed: `harness_deps`' documented fallback is the whole `swe/`
    package. Over history that means the earliest commits, before the harness
    existed, must produce an ANSWER rather than an exception."""
    root = repo["root"]
    _run(["git", "rm", "-r", "-q", "harness"], root)
    bare = _commit(root, "no harness")
    src = LR.RevSources(repo["repo"], bare)
    deps = ST.harness_deps("test_swe_fake.py", sources=src)
    assert deps == []           # nothing exists, so nothing is watched
    assert src.digests(deps) == {}


# --------------------------------------------------------------- the overlay --

def test_the_overlay_reproduces_a_digest_no_commit_can(repo):
    """The finding that made `replay_actual` possible.

    `slowtier.checkout_digest` walks the FILESYSTEM, so an untracked source
    file is inside it. A ledger entry recorded on a tree carrying one
    therefore hashes to a value NO commit reproduces — round 367 measured 0
    of 14 real entries reproducible without this, and 10 of 14 with it (the
    other 4 predate the untracked files' arrival).
    """
    root, r = repo["root"], repo["repo"]
    whence = os.path.join(root, "languages", "whence")
    head = repo["revs"][-1]
    _write(root, "languages/whence/examples/untracked.lang", "let u = 1\n")
    live = ST.checkout_digest(whence)
    assert LR.checkout_digest_at(r, head) != live
    overlay = LR.working_overlay(r)
    assert "examples/untracked.lang" in overlay
    assert LR.checkout_digest_at(r, head, overlay=overlay) == live
    assert LR.dir_digest_at(r, head, "examples", overlay=overlay) == \
        RS.dir_digest(whence, "examples")


def test_the_overlay_covers_a_modified_tracked_file_too(repo):
    root, r = repo["root"], repo["repo"]
    whence = os.path.join(root, "languages", "whence")
    head = repo["revs"][-1]
    _write(root, "languages/whence/whence/interp.py", "x = 99\n")
    overlay = LR.working_overlay(r)
    assert LR.checkout_digest_at(r, head, overlay=overlay) == \
        ST.checkout_digest(whence)


# ----------------------------------------------------------- actual replay --

def test_replay_actual_anchors_an_entry_by_time_not_by_digest(repo, tmp_path):
    """Anchoring by digest is what does NOT work here (see
    `test_the_overlay_reproduces_a_digest_no_commit_can`), so the anchor is
    `finished_at`: the last commit made at or before the run finished."""
    r = repo["repo"]
    times = LR.commit_times(r, repo["revs"])
    assert sorted(times) == sorted(repo["revs"])
    led = tmp_path / "led.jsonl"
    entry = {"file": "test_swe_fake.py", "outcome": "passed", "returncode": 0,
             "checkout_stable": True, "harness_stable": True,
             "finished_at": times[repo["revs"][1]] + 1,
             "checkout_digest": LR.checkout_digest_at(r, repo["revs"][1]),
             "dep_digests": LR.RevSources(r, repo["revs"][1]).digests(
                 ST.harness_deps("test_swe_fake.py",
                                 sources=LR.RevSources(r, repo["revs"][1]))),
             "subject_scope": {"ok": True, "dirs": ["whence"], "opaque": []},
             "subject_digests": LR.scope_digests_at(r, repo["revs"][1],
                                                    ["whence"])}
    led.write_text(__import__("json").dumps(entry) + "\n")
    out = LR.replay_actual(r, repo["revs"], ledger_path=str(led),
                           tests_dir=str(os.path.join(repo["root"], "harness",
                                                      "tests")))
    row = [x for x in out["rows"] if x["file"] == "test_swe_fake.py"][0]
    assert row["status"] == "replayed"
    assert row["start_rev"] == repo["revs"][1]      # anchored at c2, not c3
    assert row["digest_in_history"] is True
    assert row["strict"] == 0                       # c3 moves the digest
    assert row["scoped"] == 1                       # ... but not `whence/`


def test_an_entry_older_than_the_window_is_reported_not_clamped(repo, tmp_path):
    led = tmp_path / "led.jsonl"
    led.write_text(__import__("json").dumps(
        {"file": "test_swe_fake.py", "outcome": "passed", "finished_at": 1,
         "checkout_stable": True, "harness_stable": True,
         "checkout_digest": "zzz", "dep_digests": {}}) + "\n")
    out = LR.replay_actual(repo["repo"], repo["revs"], ledger_path=str(led),
                           tests_dir=str(os.path.join(repo["root"], "harness",
                                                      "tests")))
    row = [x for x in out["rows"] if x["file"] == "test_swe_fake.py"][0]
    assert row["status"] == "before_window"


# ------------------------------------------------------- against THIS repo --

def test_the_self_check_passes_against_this_repository():
    """The integration check `main()` runs before it will report anything:
    the git-object digest of HEAD equals `slowtier.checkout_digest` over an
    export of HEAD. Asserts nothing about the VALUE, which changes every
    round — only that the two agree."""
    ok, git_d, export_d, n_untracked = LR._self_check(LR.Repo())
    assert ok and git_d == export_d
    assert isinstance(n_untracked, int) and n_untracked >= 0


def test_the_window_of_this_repository_is_non_empty_and_ordered():
    revs = LR.Repo().revs(rev="HEAD")
    assert len(revs) > 1
    times = LR.commit_times(LR.Repo(), revs[-5:])
    ordered = [times[r] for r in revs[-5:]]
    assert ordered == sorted(ordered)          # `--reverse` is oldest-first

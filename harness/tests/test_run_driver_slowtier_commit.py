"""Round 457 (harness A). The driver commits the row its own slice wrote.

Why this exists
---------------
`harness/run_slowtier_slice.sh` (round 439) appends to
`state/slow-tier-ledger.jsonl` AFTER round N's Claude session has exited, so
the round that paid for the measurement is gone before the row exists.
Measured over every slice since the check was wired:

    22 driver-written rows, ZERO committed by their own round,
    21 committed by the immediately following round (delta +1, no
    exceptions), 1 outstanding.

Round 452 diagnosed it — "the driver always appends after the round's last
commit, so it is a step in the wrong order, not a race" — and rounds 453,
454, 455 and 456 each re-listed it as a next-step while spending their own
part 0 on the manual `git add`. The fix belongs where the wrong-ordered step
is: in the driver.

What these tests pin is not "a commit happens". It is the four properties
that make an autonomous `git commit` in this repo safe, each of which has a
concrete failure this repo has already lived through:

  * ONE pathspec, index untouched. A round that died with other work staged
    must keep it staged. (`feedback_check_cached_diff_before_commit`: other
    tracks' WIP can already be in the index.)
  * The workspace must BE a repository root, not merely sit inside one —
    every `test_run_driver_*.py` fixture runs the driver in a tmp_path.
  * The subject line must not contain "round N".
    `check_round_recorded.committed_per_git_log` greps `git log --all
    --oneline` for exactly that substring to answer "did round N commit
    anything?". A driver commit naming the round would answer YES for a
    round that committed nothing — hiding gap shape 3, which is the shape
    round 456 was reported under.
  * Diagnostic only. A failed commit logs and the driver continues.
"""

import os
import shutil
import stat
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DRIVER_SRC = os.path.join(REPO_ROOT, "run_driver.sh")
LEDGER_REL = "state/slow-tier-ledger.jsonl"
SUBJECT = "driver: slow-tier ledger append (post-round slice)"

CLAUDE_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
WS="$DRIVER_TEST_WS"
COUNT_FILE="$WS/state/call_count"
N=$(( $(cat "$COUNT_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$N" > "$COUNT_FILE"
if [ "$N" -eq 1 ]; then
  echo '{"type":"result","is_error":false,"subtype":"success","num_turns":1,"result":"ok","api_error_status":null,"total_cost_usd":0.01}'
else
  echo '{"type":"result","is_error":true,"subtype":"error_test","num_turns":1,"result":"test budget limit reached","api_error_status":"test_limit","total_cost_usd":0.01}'
fi
"""

# A stand-in for `run_slowtier_slice.sh`: appends one row and prints a
# summary line, exactly as the real script's observable contract does.
SLICE_BODY = (
    'cd "$(dirname "${BASH_SOURCE[0]}")/.."\n'
    'echo \'{"unit": "test_stub.py", "outcome": "passed"}\' >> %s\n'
    'echo "slow tier: 1 files / 1 units, 1 conclusive against checkout deadbeef '
    '(3%% recall), 0 failing"\n'
    'exit 0\n' % LEDGER_REL
)


def _git(ws, *args, **kw):
    return subprocess.run(["git", "-C", ws] + list(args),
                          capture_output=True, text=True, **kw)


def _exe(path):
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _make_script(ws, rel_dir, name, body):
    target_dir = os.path.join(ws, rel_dir)
    os.makedirs(target_dir, exist_ok=True)
    p = os.path.join(target_dir, name)
    with open(p, "w") as f:
        f.write("#!/usr/bin/env bash\n" + body + "\n")
    _exe(p)
    return p


def _make_ws(tmp_path, git=True, slice_body=SLICE_BODY, track_ledger=True,
             sub=None):
    """A driver workspace. `sub` puts the workspace in a SUBDIRECTORY of the
    git repo, which is the enclosing-repo case."""
    root = str(tmp_path)
    ws = os.path.join(root, sub) if sub else root
    os.makedirs(os.path.join(ws, "state"), exist_ok=True)
    os.makedirs(os.path.join(ws, "logs"), exist_ok=True)
    shutil.copyfile(DRIVER_SRC, os.path.join(ws, "run_driver.sh"))
    os.chmod(os.path.join(ws, "run_driver.sh"), 0o755)
    if slice_body is not None:
        _make_script(ws, "harness", "run_slowtier_slice.sh", slice_body)
    with open(os.path.join(ws, LEDGER_REL), "w") as f:
        f.write('{"unit": "seed.py", "outcome": "passed"}\n')
    if git:
        repo = root
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "t@example.invalid")
        _git(repo, "config", "user.name", "test")
        rel = os.path.join(sub, LEDGER_REL) if sub else LEDGER_REL
        if track_ledger:
            _git(repo, "add", "--", rel)
        else:
            # Something must be tracked so HEAD exists.
            with open(os.path.join(repo, "seed.txt"), "w") as f:
                f.write("seed\n")
            _git(repo, "add", "--", "seed.txt")
        _git(repo, "commit", "-q", "-m", "seed")
    return ws


def _run_driver(ws, extra_env=None):
    bin_dir = os.path.join(ws, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    stub = os.path.join(bin_dir, "claude")
    with open(stub, "w") as f:
        f.write(CLAUDE_STUB)
    _exe(stub)

    env = dict(os.environ)
    env["PATH"] = bin_dir + os.pathsep + env["PATH"]
    env["DRIVER_WS"] = ws
    env["DRIVER_TEST_WS"] = ws
    env["DRIVER_LOOP_SLEEP_S"] = "0"
    env["DRIVER_CLAUDE_CMD"] = "claude"
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    env.update(extra_env or {})

    proc = subprocess.Popen(["bash", os.path.join(ws, "run_driver.sh")],
                            cwd=REPO_ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        pytest.fail("driver did not stop within 60s")
    with open(os.path.join(ws, "logs", "driver.log")) as f:
        return f.read()


def _driver_commits(repo):
    out = _git(repo, "log", "--format=%H|%s").stdout.strip().splitlines()
    return [l.split("|", 1) for l in out if l.split("|", 1)[1] == SUBJECT]


# ------------------------------------------------------------ it commits it --

def test_the_driver_commits_the_row_its_own_slice_wrote(tmp_path):
    """The whole point. Without this the row is orphaned into the next
    round's working tree, which is what happened 22 times out of 22."""
    ws = _make_ws(tmp_path)
    log_text = _run_driver(ws)
    assert "slowtier-slice OK" in log_text, log_text
    assert "slowtier-ledger committed" in log_text, log_text
    assert _driver_commits(ws), _git(ws, "log", "--oneline").stdout


def test_the_commit_contains_the_ledger_and_nothing_else(tmp_path):
    """`git commit -- <path>` with one pathspec. A driver that swept the
    tree would be committing work no round has attributed — the exact thing
    `check_round_recorded`'s shape-4 check exists to surface."""
    ws = _make_ws(tmp_path)
    # A second tracked file that the round leaves dirty, and an untracked one.
    other = os.path.join(ws, "state", "other.txt")
    with open(other, "w") as f:
        f.write("v1\n")
    _git(ws, "add", "--", "state/other.txt")
    _git(ws, "commit", "-q", "-m", "add other")
    with open(other, "w") as f:
        f.write("v2\n")
    with open(os.path.join(ws, "state", "untracked.txt"), "w") as f:
        f.write("u\n")

    _run_driver(ws)
    commits = _driver_commits(ws)
    assert commits, "no driver commit"
    for sha, _ in commits:
        names = _git(ws, "show", "--pretty=", "--name-only", sha).stdout.split()
        assert names == [LEDGER_REL], names

    porcelain = _git(ws, "status", "--porcelain").stdout
    assert "state/other.txt" in porcelain, porcelain
    assert "state/untracked.txt" in porcelain, porcelain


def test_work_a_dead_round_left_staged_stays_staged(tmp_path):
    """A round killed by the outer timeout can leave a populated index —
    round 456 was killed that way. `git commit -- <path>` must not turn that
    into an unattributed driver commit, and must not silently discard it."""
    ws = _make_ws(tmp_path)
    staged = os.path.join(ws, "state", "half-done.txt")
    with open(staged, "w") as f:
        f.write("half\n")
    _git(ws, "add", "--", "state/half-done.txt")

    _run_driver(ws)
    assert _driver_commits(ws), "no driver commit"
    # Still in the index, still not in any commit.
    cached = _git(ws, "diff", "--cached", "--name-only").stdout.split()
    assert "state/half-done.txt" in cached, cached
    tracked_at_head = _git(ws, "ls-tree", "-r", "--name-only", "HEAD").stdout.split()
    assert "state/half-done.txt" not in tracked_at_head, tracked_at_head


# ------------------------------------------------------------- it refuses to --

def test_no_commit_when_the_workspace_is_not_a_repository(tmp_path):
    """Every `test_run_driver_*.py` fixture is a bare tmp_path. Round 241's
    degradation guarantee applies here too: no repo, no commit, no error."""
    ws = _make_ws(tmp_path, git=False)
    log_text = _run_driver(ws)
    assert "slowtier-slice OK" in log_text, log_text
    assert "slowtier-ledger" not in log_text, log_text


def test_the_driver_never_commits_into_an_enclosing_repository(tmp_path):
    """A workspace that merely SITS INSIDE a checkout is not this driver's
    repository. `rev-parse --show-toplevel` equality, not `--git-dir`
    success, is what makes the difference — and the difference is a test
    fixture writing commits into whatever repo it happens to land under."""
    ws = _make_ws(tmp_path, sub="inner")
    repo = str(tmp_path)
    head_before = _git(repo, "rev-parse", "HEAD").stdout.strip()

    log_text = _run_driver(ws)
    assert "slowtier-slice OK" in log_text, log_text
    assert "slowtier-ledger" not in log_text, log_text
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == head_before


def test_no_commit_when_the_ledger_did_not_move(tmp_path):
    """A slice that ran and appended nothing (every unit already fresh, or
    `DRIVER_SLOWTIER_BUDGET_S=0`) must not manufacture an empty commit."""
    ws = _make_ws(tmp_path, slice_body='echo "slowtier-slice: SKIPPED"\nexit 0')
    log_text = _run_driver(ws)
    assert "slowtier-slice OK" in log_text, log_text
    assert "slowtier-ledger" not in log_text, log_text


def test_an_untracked_ledger_is_left_for_a_human_and_said_so(tmp_path):
    """No `git add` on purpose. The driver may land a row in a file this
    repo already tracks; deciding to START tracking a file is a round's
    judgement, not a background job's.

    The first draft of this branch skipped silently — `git diff HEAD --
    <path>` reports no change for an untracked file, so the whole block fell
    through and logged nothing. These two tests caught it. Round 439's own
    rule about its off switch is the one that applies: an invisible skip is
    the same failure as an invisible spend, with the sign flipped."""
    ws = _make_ws(tmp_path, track_ledger=False)
    log_text = _run_driver(ws)
    assert "slowtier-ledger NOT COMMITTED" in log_text, log_text
    assert "untracked" in log_text, log_text
    assert not _driver_commits(ws)
    assert ("?? " + LEDGER_REL
            in _git(ws, "status", "--porcelain", "-uall").stdout)


def test_a_ledger_the_driver_will_not_commit_never_stops_the_driver(tmp_path):
    """Diagnostic only, like the five checks above it."""
    ws = _make_ws(tmp_path, track_ledger=False)
    log_text = _run_driver(ws)
    assert "slowtier-ledger NOT COMMITTED" in log_text, log_text
    assert "round 2 track=" in log_text, log_text


# ------------------------------------------- it does not hide a missing round --

def test_the_subject_cannot_be_read_as_evidence_that_the_round_committed(tmp_path):
    """The subtle one, and the reason the round number lives in the BODY.

    `check_round_recorded.committed_per_git_log(N)` answers "did round N
    commit anything?" by grepping `git log --all --oneline` — SUBJECTS ONLY —
    for the substring "round N". If the driver's own commit said "round 1",
    a round that recorded a state entry and committed nothing would read as
    landed, and gap shape 3 would stop firing. Round 456 is exactly that
    shape; this test is what keeps the fix from blinding the check that
    found it.
    """
    sys.path.insert(0, os.path.join(REPO_ROOT, "skills",
                                    "session-inheritance-audit", "scripts"))
    import check_round_recorded as crr
    crr._cached_git_log_lines.cache_clear()

    ws = _make_ws(tmp_path)
    _run_driver(ws)
    assert _driver_commits(ws), "no driver commit to test against"
    # The driver's commits are the ONLY commits here besides "seed".
    subjects = _git(ws, "log", "--format=%s").stdout.splitlines()
    assert all(s in (SUBJECT, "seed") for s in subjects), subjects

    try:
        for n in (1, 2):
            assert crr.committed_per_git_log(n, repo_root=ws) is False, (
                "the driver's ledger commit is being read as evidence that "
                "round %d committed its own work" % n)
    finally:
        crr._cached_git_log_lines.cache_clear()


def test_the_subject_is_free_of_any_round_number_at_the_source(tmp_path):
    """The test above proves it for rounds 1 and 2. This proves the property
    for EVERY round: the subject is a constant string with no `$ROUND` in
    it, so no round number can ever reach `git log --oneline`."""
    src = open(DRIVER_SRC).read()
    i = src.index('-m "driver: slow-tier ledger append')
    subject_line = src[i:src.index("\n", i)]
    assert "$ROUND" not in subject_line, subject_line
    # And the round number IS recorded, in the body, one line later.
    body_line = src[src.index("\n", i) + 1:]
    body_line = body_line[:body_line.index("\n")]
    assert "$ROUND" in body_line, body_line


# ------------------------------------------------------------------ shape --

def _ledger_commit_block(src):
    """The slow-tier ledger-commit block ALONE, with comments stripped.

    Both halves of that sentence are round 469 repairs, and both were found
    by this test going red on a change that had nothing to do with it.

    * The region used to run from `SLOWTIER_LEDGER_REL=` to
      `# Safety valve (round 150+)` — a landmark far downstream with three
      unrelated statements between. Round 469 inserted the whence-slow slice
      there, and this test began asserting things about someone else's block:
      an anchor that MATCHED without LOCATING. The end anchor is now the next
      check's own first line when it exists, so the region is this block or
      nothing.
    * The forbidden-substring scan is about CODE — "no `git add -A`, no
      `git commit -a`" — and it was reading COMMENTS. Round 469's block
      documents its own rule in prose containing the words "no `git add`",
      which is the opposite of a violation, and the test read it as one. A
      scan for dangerous code that a comment can trip is a scan that
      punishes documenting the rule.
    """
    start = src.index("SLOWTIER_LEDGER_REL=")
    ends = [src.index(m, start) for m in
            ('WHENCESLOW_SCRIPT="$WS/harness/run_whenceslow_slice.sh"',
             "# Safety valve (round 150+)") if m in src[start:]]
    block = src[start:min(ends)]
    return "\n".join(l.split("#", 1)[0] if l.lstrip().startswith("#") else l
                      for l in block.split("\n"))


def test_the_commit_is_scoped_and_never_stages_the_tree():
    """No `git add -A`, no `git commit -a`. The AUTO-COMMIT v4 commit
    `e376750` deleted 38 lines of CLAUDE.md — including the whole `##
    Ground rules` body, unnoticed for 200 rounds (see CLAUDE.md's
    provenance section). An unscoped autonomous commit in this repo is not
    hypothetical."""
    src = open(DRIVER_SRC).read()
    block = _ledger_commit_block(src)
    assert 'commit -q' in block
    assert '-- "$SLOWTIER_LEDGER_REL"' in block, block
    for forbidden in ("git add", "commit -a", "-A"):
        assert forbidden not in block, "%r in the ledger-commit block" % forbidden


def test_the_commit_happens_after_the_slice_has_run():
    """Committing before the append would land the PREVIOUS round's row and
    orphan this one — the same defect, moved by one."""
    src = open(DRIVER_SRC).read()
    assert (src.index('bash "$SLOWTIER_SCRIPT"')
            < src.index("SLOWTIER_LEDGER_REL="))
    # And inside the same existence guard, so no harness tree means no commit.
    assert (src.index('SLOWTIER_SCRIPT="$WS/harness/run_slowtier_slice.sh"')
            < src.index("SLOWTIER_LEDGER_REL="))
    assert (src.index("SLOWTIER_LEDGER_REL=")
            < src.index("# Safety valve (round 150+)"))

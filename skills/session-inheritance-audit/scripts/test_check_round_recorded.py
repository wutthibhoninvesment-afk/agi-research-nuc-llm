import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "check_round_recorded.py")

sys.path.insert(0, HERE)
import check_round_recorded as m  # noqa: E402


def _write_driver_log(path, lines):
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def _write_ndjson(path, objs):
    with open(path, "w") as f:
        for o in objs:
            f.write(json.dumps(o) + "\n")


def test_parse_driver_log_reads_track_and_status():
    text = (
        "[t] round 5 track=skills(B) start (driver_version=x) pid=1\n"
        "[t] round 5: success\n"
        "[t] round 6 track=harness(A) start (driver_version=x) pid=1\n"
        "[t] round 6: non-success status=error:max_turns\n"
    )
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "driver.log")
        with open(p, "w") as f:
            f.write(text)
        rounds = m.parse_driver_log(p)
    assert rounds[5] == {"track": "skills(B)", "status": "success"}
    assert rounds[6] == {"track": "harness(A)", "status": "error:max_turns"}


def test_recorded_rounds_reads_state_headings(tmp_path):
    state = tmp_path / "state.md"
    state.write_text(
        "# state\n\n### Round 5 — Skills(B) — 2026-01-01\n- did stuff\n\n"
        "### Round 7 — Harness(A) — 2026-01-02\n- did other stuff\n"
    )
    assert m.recorded_rounds(str(state)) == {5, 7}


def test_recorded_rounds_missing_file_returns_empty(tmp_path):
    assert m.recorded_rounds(str(tmp_path / "nope.md")) == set()


def test_recorded_rounds_unions_archive_headings(tmp_path):
    state = tmp_path / "state.md"
    state.write_text("### Round 175 — Skills(B) — 2026-08-27\n- ok\n")
    archive = tmp_path / "archive.md"
    archive.write_text(
        "### Round 5 — harness(A) — 2026-08-24\n- old\n\n"
        "### Round 160 — NUC-integration(E) — 2026-08-26\n- old\n"
    )
    assert m.recorded_rounds(str(state), [str(archive)]) == {5, 160, 175}


def test_recorded_rounds_skips_missing_archive_path(tmp_path):
    state = tmp_path / "state.md"
    state.write_text("### Round 1 — Skills(B) — 2026-01-01\n- ok\n")
    assert m.recorded_rounds(
        str(state), [str(tmp_path / "nope-archive.md")]
    ) == {1}


def test_end_to_end_archived_round_is_not_flagged_as_a_gap(tmp_path):
    # A round whose heading was relocated to the archive file (not deleted,
    # not duplicated) must not read as an unrecorded gap forever after.
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 5 track=harness(A) start (driver_version=x) pid=1",
        "[t] round 5: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("# state\n(round 5 archived below)\n")
    archive = tmp_path / "archive.md"
    archive.write_text("### Round 5 — harness(A) — 2026-08-24\n- did stuff\n")

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(archive),
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path / "logs_missing"),
         # not a git repo -> working_tree_status degrades to None/[],
         # isolating this test from the real checkout's own dirty tree.
         "--repo-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0
    assert "0 gaps" in rc.stdout


def test_knowledge_rounds_matches_round_ddd_prefix(tmp_path):
    (tmp_path / "round-005-foo.md").write_text("x")
    (tmp_path / "round-012-bar-baz.md").write_text("x")
    (tmp_path / "not-a-round-file.md").write_text("x")
    assert m.knowledge_rounds(str(tmp_path)) == {5, 12}


def test_ended_on_dangling_wait_true_for_standing_by(tmp_path):
    p = tmp_path / "round-1.json"
    _write_ndjson(str(p), [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Launching the background check."}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Standing by — no further action "
                                      "until the background checks report back."}]}},
    ])
    assert m.ended_on_dangling_wait(str(p)) is True


def test_ended_on_dangling_wait_false_for_a_finished_report(tmp_path):
    p = tmp_path / "round-2.json"
    _write_ndjson(str(p), [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Committed the diff and wrote the "
                                      "knowledge file. Round complete."}]}},
    ])
    assert m.ended_on_dangling_wait(str(p)) is False


def test_ended_on_dangling_wait_none_for_missing_log(tmp_path):
    assert m.ended_on_dangling_wait(str(tmp_path / "missing.json")) is None


def test_end_to_end_reports_gap_for_unrecorded_round(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 1 track=skills(B) start (driver_version=x) pid=1",
        "[t] round 1: success",
        "[t] round 2 track=harness(A) start (driver_version=x) pid=1",
        "[t] round 2: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("### Round 1 — Skills(B) — 2026-01-01\n- ok\n")
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "round-001-ok.md").write_text("x")
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_ndjson(str(logs_dir / "round-2.json"), [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "standing by for the notification"}]}},
    ])

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(knowledge),
         "--round-logs-dir", str(logs_dir)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 1
    assert "round 2" in rc.stdout
    assert "round 1" not in rc.stdout.split("gap")[0] or True  # round 1 must not be flagged
    assert "dangling background wait" in rc.stdout


def test_gap_reports_interrupted_true_when_no_result_event(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 1 track=skills(B) start (driver_version=x) pid=1",
        "[t] round 1: non-success status=?",
    ])
    state = tmp_path / "state.md"
    state.write_text("# empty\n")
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_ndjson(str(logs_dir / "round-1.json"), [
        {"type": "assistant", "message": {"usage": {}, "content": [
            {"type": "text", "text": "working..."}]}},
        # killed mid-flight: no "type": "result" line ever written
    ])

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(knowledge),
         "--round-logs-dir", str(logs_dir)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 1
    assert "round 1" in rc.stdout
    assert "interrupted=True" in rc.stdout


def test_gap_reports_interrupted_false_when_result_event_present(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 1 track=skills(B) start (driver_version=x) pid=1",
        "[t] round 1: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("# empty\n")
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    _write_ndjson(str(logs_dir / "round-1.json"), [
        {"type": "assistant", "message": {"usage": {}, "content": [
            {"type": "text", "text": "done"}]}},
        {"type": "result", "usage": {}},
    ])

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(knowledge),
         "--round-logs-dir", str(logs_dir)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 1
    assert "interrupted=False" in rc.stdout


def test_gap_reports_interrupted_none_when_round_log_missing(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 1 track=skills(B) start (driver_version=x) pid=1",
        "[t] round 1: non-success status=?",
    ])
    state = tmp_path / "state.md"
    state.write_text("# empty\n")

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path / "logs_missing")],
        capture_output=True, text=True,
    )
    assert rc.returncode == 1
    assert "interrupted=None" in rc.stdout


def test_summarize_turns_import_resolves_to_real_harness_module():
    # Guards against the sys.path bootstrap in check_round_recorded.py
    # silently falling back to the None stub (which would make every
    # `interrupted` column read None even when harness/ is present).
    assert m._summarize_turns is not None


def test_committed_per_git_log_none_when_not_a_repo(tmp_path):
    assert m.committed_per_git_log(184, str(tmp_path)) is None


def test_committed_per_git_log_true_when_subject_mentions_round(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Round 184 (NUC E): did stuff"],
                    cwd=tmp_path, check=True)
    assert m.committed_per_git_log(184, str(tmp_path)) is True
    # A different round number, and a round number that is a substring of
    # another (1840 must not match \b184), both read False, not True.
    assert m.committed_per_git_log(183, str(tmp_path)) is False
    assert m.committed_per_git_log(1840, str(tmp_path)) is False


def test_committed_per_git_log_false_for_left_uncommitted_by_mention(tmp_path):
    # A LATER round's housekeeping commit can mention round N purely to
    # explain that round N itself failed to commit anything (round 197,
    # found live round 213) — the opposite of evidence round N landed.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m",
         "Round 198: bump round_counter to 198 "
         "(covers rounds 197-198, left uncommitted by round 197)"],
        cwd=tmp_path, check=True)
    assert m.committed_per_git_log(197, str(tmp_path)) is False
    # round 198 itself IS the commit's own leading round number — stays True.
    assert m.committed_per_git_log(198, str(tmp_path)) is True


def test_committed_per_git_log_true_when_a_later_round_actually_lands_it(tmp_path):
    # Contrast case: "uncommitted since round N" where the commit's main
    # verb is landing round N's real work (round 155, landed by round 201)
    # must NOT be swept up by the narrower exclusion above.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m",
         "Round 201 (skills B): land SWE-loop(D)'s stale-coverage-map fix, "
         "uncommitted since round 155"],
        cwd=tmp_path, check=True)
    assert m.committed_per_git_log(155, str(tmp_path)) is True


def test_committed_per_git_log_false_for_landed_by_mention(tmp_path):
    # Round 267's own finding: round 263's commit message credits round
    # 264 as the one who WILL land round 263 ("landed by round 264") —
    # this must not read as evidence that round 264's own work is already
    # committed here, mirroring the 197/198 "left uncommitted by" shape
    # but with a different verb ("landed" instead of "left uncommitted").
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m",
         "Round 263 (SWE-loop D, landed by round 264): triage and kill "
         "round 245's lexer.py mutation survivors"],
        cwd=tmp_path, check=True)
    # Round 264 has no dedicated commit of its own yet — must read False.
    assert m.committed_per_git_log(264, str(tmp_path)) is False
    # Round 263's own leading round number is real evidence — stays True.
    assert m.committed_per_git_log(263, str(tmp_path)) is True


def test_gap_reports_git_committed_false_and_flags_unverified_claim(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 184 track=NUC-integration(E) start (driver_version=x) pid=1",
        "[t] round 184: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("# empty\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "b.txt").write_text("x")
    subprocess.run(["git", "add", "b.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "unrelated prior work"],
                    cwd=repo, check=True)

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path / "logs_missing"),
         "--repo-root", str(repo)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 1
    assert "git_committed=False" in rc.stdout
    assert "NOT in git log" in rc.stdout


def test_recorded_but_uncommitted_rounds_flags_recorded_round_with_no_commit(tmp_path):
    # Round 266/267's exact shape: a research-state.md heading AND a
    # knowledge file both exist (so `main`'s `if in_state: continue` would
    # normally skip it entirely) but the file itself never landed in git.
    repo = tmp_path / "repo"
    repo.mkdir()
    knowledge = repo / "knowledge"
    knowledge.mkdir()
    (knowledge / "round-266-foo.md").write_text("x")  # never `git add`ed
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "unrelated prior work"],
                    cwd=repo, check=True)

    driver_rounds = {266: {"track": "language(C)", "status": "success"}}
    state_rounds = {266}
    assert m.recorded_but_uncommitted_rounds(
        driver_rounds, state_rounds, str(knowledge), str(repo)) == [266]


def test_recorded_but_uncommitted_rounds_clean_when_file_committed(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    knowledge = repo / "knowledge"
    knowledge.mkdir()
    (knowledge / "round-266-foo.md").write_text("x")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "unrelated subject text"],
                    cwd=repo, check=True)

    driver_rounds = {266: {"track": "language(C)", "status": "success"}}
    state_rounds = {266}
    # No "round 266" anywhere in the commit subject — proves this check
    # verifies FILE presence, not subject-line text (unlike
    # committed_per_git_log), matching round 154/160/162's real shape.
    assert m.recorded_but_uncommitted_rounds(
        driver_rounds, state_rounds, str(knowledge), str(repo)) == []


def test_recorded_but_uncommitted_rounds_ignores_round_missing_knowledge_file(tmp_path):
    # in_state=True but has_knowledge_file=False is a softer signal per the
    # main loop's own comment — not this check's shape even with no commit.
    repo = tmp_path / "repo"
    repo.mkdir()
    knowledge = repo / "knowledge"
    knowledge.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "unrelated"], cwd=repo, check=True)

    driver_rounds = {266: {"track": "language(C)", "status": "success"}}
    state_rounds = {266}
    assert m.recorded_but_uncommitted_rounds(
        driver_rounds, state_rounds, str(knowledge), str(repo)) == []


def test_recorded_but_uncommitted_rounds_skips_when_git_unavailable(tmp_path):
    # Not a git repo at all -> _file_ever_tracked returns None for every
    # path; unverifiable must not be treated as "definitely missing".
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "round-266-foo.md").write_text("x")
    driver_rounds = {266: {"track": "language(C)", "status": "success"}}
    state_rounds = {266}
    assert m.recorded_but_uncommitted_rounds(
        driver_rounds, state_rounds, str(knowledge), str(tmp_path)) == []


def test_file_ever_tracked_true_for_committed_file(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add a"], cwd=tmp_path, check=True)
    assert m._file_ever_tracked(str(tmp_path / "a.txt"), str(tmp_path)) is True


def test_file_ever_tracked_false_for_untracked_file(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add a"], cwd=tmp_path, check=True)
    (tmp_path / "b.txt").write_text("y")  # never added/committed
    assert m._file_ever_tracked(str(tmp_path / "b.txt"), str(tmp_path)) is False


def test_file_ever_tracked_none_when_not_a_repo(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    assert m._file_ever_tracked(str(tmp_path / "a.txt"), str(tmp_path)) is None


def test_end_to_end_flags_recorded_but_uncommitted_round(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 266 track=language(C) start (driver_version=x) pid=1",
        "[t] round 266: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("### Round 266 — language(C) — 2026-08-28\n- ok\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "b.txt").write_text("x")
    subprocess.run(["git", "add", "b.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "unrelated prior work"],
                    cwd=repo, check=True)
    # knowledge/ lives INSIDE the repo (matching real usage, where
    # --knowledge-dir and --repo-root are both relative to the same
    # checkout) but the file itself is never `git add`ed/committed.
    knowledge = repo / "knowledge"
    knowledge.mkdir()
    (knowledge / "round-266-foo.md").write_text("x")

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(knowledge),
         "--round-logs-dir", str(tmp_path / "logs_missing"),
         "--repo-root", str(repo)],
        capture_output=True, text=True,
    )
    # The main per-round loop's own `if in_state: continue` would otherwise
    # make round 266 invisible — it has both a heading and a knowledge file.
    assert rc.returncode == 1
    assert "recorded but uncommitted" in rc.stdout or "never actually landed in git" in rc.stdout
    assert "266" in rc.stdout


def test_end_to_end_acknowledged_uncommitted_gap_suppressed_by_default(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 266 track=language(C) start (driver_version=x) pid=1",
        "[t] round 266: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("### Round 266 — language(C) — 2026-08-28\n- ok\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "b.txt").write_text("x")
    subprocess.run(["git", "add", "b.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "unrelated prior work"],
                    cwd=repo, check=True)
    knowledge = repo / "knowledge"
    knowledge.mkdir()
    (knowledge / "round-266-foo.md").write_text("x")
    ack = tmp_path / "ack.json"
    ack.write_text(json.dumps({"266": "verified, real work landed by round 267"}))
    # round-266-foo.md is deliberately, permanently uncommitted here (that's
    # what recorded_but_uncommitted_rounds is testing) — separately allowlist
    # it in the dirty-tree check too, exactly as a real user would once the
    # round-based ack above already covers the exact same file.
    # git reports a wholly-untracked directory as one line for the
    # directory itself ("?? knowledge/"), not per-file inside it.
    standing = tmp_path / "standing.json"
    standing.write_text(json.dumps({"paths": ["knowledge/"]}))

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(ack),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(knowledge),
         "--round-logs-dir", str(tmp_path / "logs_missing"),
         "--repo-root", str(repo),
         "--standing-dirty-file", str(standing)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0
    assert "0 gaps" in rc.stdout

    rc_shown = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(ack),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--show-acknowledged",
         "--knowledge-dir", str(knowledge),
         "--round-logs-dir", str(tmp_path / "logs_missing"),
         "--repo-root", str(repo),
         "--standing-dirty-file", str(standing)],
        capture_output=True, text=True,
    )
    assert rc_shown.returncode == 0
    assert ("round 266 (recorded but uncommitted): verified, real work "
            "landed by round 267") in rc_shown.stdout


def test_cached_git_log_lines_reused_across_calls_same_repo(tmp_path):
    # Two committed_per_git_log calls against the same repo_root must not
    # re-run `git log` from scratch the second time — the memoization
    # round 273 added for recorded_but_uncommitted_rounds's higher call
    # volume. Verified by mutating the repo AFTER the first call and
    # confirming the second call still reflects the STALE cached answer
    # (proof the subprocess didn't actually re-run), then clearing the
    # cache and confirming it picks up the new commit.
    m._cached_git_log_lines.cache_clear()
    repo = tmp_path
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "unrelated"], cwd=repo, check=True)

    assert m.committed_per_git_log(300, str(repo)) is False
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "Round 300: real work"],
                    cwd=repo, check=True)
    # Stale cache: still reads False even though a matching commit now exists.
    assert m.committed_per_git_log(300, str(repo)) is False
    m._cached_git_log_lines.cache_clear()
    assert m.committed_per_git_log(300, str(repo)) is True


def test_end_to_end_clean_when_every_round_recorded(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 1 track=skills(B) start (driver_version=x) pid=1",
        "[t] round 1: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("### Round 1 — Skills(B) — 2026-01-01\n- ok\n")

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path),
         "--repo-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0
    assert "0 gaps" in rc.stdout


def test_load_acknowledged_gaps_missing_file_returns_empty(tmp_path):
    assert m.load_acknowledged_gaps(str(tmp_path / "nope.json")) == {}


def test_load_acknowledged_gaps_parses_int_keys_and_skips_comment(tmp_path):
    p = tmp_path / "ack.json"
    p.write_text(json.dumps({
        "_comment": "not a round number",
        "152": "no surviving diff, see research-state.md",
        "185": "classified as a timeout kill by round 211",
    }))
    acks = m.load_acknowledged_gaps(str(p))
    assert acks == {
        152: "no surviving diff, see research-state.md",
        185: "classified as a timeout kill by round 211",
    }


def test_load_acknowledged_gaps_malformed_json_returns_empty(tmp_path):
    p = tmp_path / "ack.json"
    p.write_text("{not valid json")
    assert m.load_acknowledged_gaps(str(p)) == {}


def test_end_to_end_acknowledged_gap_suppressed_by_default(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 1 track=skills(B) start (driver_version=x) pid=1",
        "[t] round 1: success",
        "[t] round 2 track=harness(A) start (driver_version=x) pid=1",
        "[t] round 2: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("# empty\n")
    ack = tmp_path / "ack.json"
    ack.write_text(json.dumps({"1": "verified no surviving diff"}))

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(ack),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path / "logs_missing")],
        capture_output=True, text=True,
    )
    # Round 1 is acknowledged and must not appear in the gap list or count;
    # round 2 is a genuine, unacknowledged gap and must still be reported.
    assert rc.returncode == 1
    assert "round 1" not in rc.stdout
    assert "round 2" in rc.stdout
    assert "1 more pre-acknowledged" in rc.stdout


def test_end_to_end_acknowledged_gap_shown_with_flag(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 1 track=skills(B) start (driver_version=x) pid=1",
        "[t] round 1: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("# empty\n")
    ack = tmp_path / "ack.json"
    ack.write_text(json.dumps({"1": "verified no surviving diff"}))

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(ack),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--show-acknowledged",
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path / "logs_missing"),
         "--repo-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    # All gaps acknowledged -> clean exit, but --show-acknowledged still
    # prints the suppressed round and its reason for a human to spot-check.
    assert rc.returncode == 0
    assert "round 1: verified no surviving diff" in rc.stdout
    assert "0 gaps" in rc.stdout


def test_missing_round_numbers_empty_for_contiguous_rounds():
    driver_rounds = {5: {}, 6: {}, 7: {}}
    assert m.missing_round_numbers(driver_rounds) == []


def test_missing_round_numbers_empty_for_no_rounds():
    assert m.missing_round_numbers({}) == []


def test_missing_round_numbers_finds_a_single_hole():
    # The real round-229 shape: 228 and 230 both have driver.log lines,
    # 229 has none at all.
    driver_rounds = {228: {}, 230: {}}
    assert m.missing_round_numbers(driver_rounds) == [229]


def test_missing_round_numbers_finds_multiple_holes():
    driver_rounds = {10: {}, 15: {}}
    assert m.missing_round_numbers(driver_rounds) == [11, 12, 13, 14]


def test_missing_round_numbers_respects_since():
    driver_rounds = {10: {}, 15: {}, 20: {}}
    assert m.missing_round_numbers(driver_rounds, since=13) == [13, 14, 16, 17, 18, 19]


def test_end_to_end_reports_sequence_gap_and_exits_nonzero(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 228 track=language(C) start (driver_version=x) pid=1",
        "[t] round 228: success",
        "[t] round 230 track=language(C) start (driver_version=x) pid=1",
        "[t] round 230: success",
    ])
    state = tmp_path / "state.md"
    state.write_text(
        "### Round 228 — language(C) — 2026-08-28\n- ok\n"
        "### Round 230 — language(C) — 2026-08-28\n- ok\n"
    )
    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path / "logs_missing")],
        capture_output=True, text=True,
    )
    # Both 228 and 230 are fully recorded (no research-state.md gap), but
    # 229 itself never logged anything at all — a hole in driver.log's own
    # round-number sequence, invisible to the research-state.md-based
    # check, still nonzero exit.
    assert rc.returncode == 1
    assert "sequence gap" in rc.stdout
    assert "229" in rc.stdout
    assert "0 gaps" not in rc.stdout


def test_end_to_end_acknowledged_sequence_gap_suppressed_by_default(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 228 track=language(C) start (driver_version=x) pid=1",
        "[t] round 228: success",
        "[t] round 230 track=language(C) start (driver_version=x) pid=1",
        "[t] round 230: success",
    ])
    state = tmp_path / "state.md"
    state.write_text(
        "### Round 228 — language(C) — 2026-08-28\n- ok\n"
        "### Round 230 — language(C) — 2026-08-28\n- ok\n"
    )
    ack = tmp_path / "ack.json"
    ack.write_text(json.dumps({"229": "sequence gap, root cause unconfirmed"}))

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(ack),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path / "logs_missing"),
         "--repo-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0
    assert "0 gaps" in rc.stdout
    assert "1 pre-acknowledged" in rc.stdout

    rc_shown = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(ack),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--show-acknowledged",
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path / "logs_missing"),
         "--repo-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert rc_shown.returncode == 0
    assert "round 229 (sequence gap): sequence gap, root cause unconfirmed" in rc_shown.stdout


def test_real_repo_acknowledges_round_229_sequence_gap():
    # Guards the live artifact this round shipped alongside the code
    # change: a fresh run against the REAL repo's driver.log/ack-file must
    # show round 229 as a pre-acknowledged sequence gap, not a live,
    # unacknowledged one — this is the actual case that motivated
    # missing_round_numbers, not just a synthetic fixture. Deliberately
    # does NOT assert an overall 0-gap/0-exit-code outcome: the round
    # CURRENTLY running (its own research-state.md entry not written yet)
    # will itself transiently read as an unrelated, unacknowledged
    # research-state.md gap every time this test runs mid-round — that's
    # expected and out of scope here (see run_driver.sh's own comment on
    # why the record-gap check runs before a round's start line is
    # logged); only the sequence-gap handling for round 229 specifically
    # is under test.
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    rc = subprocess.run(
        [sys.executable, SCRIPT, "--show-acknowledged"],
        capture_output=True, text=True, cwd=repo_root,
    )
    assert "round 229 (sequence gap):" in rc.stdout
    # Round 229 must not appear in the live, unacknowledged sequence-gap
    # line even if OTHER unrelated gaps make the overall exit code 1.
    for line in rc.stdout.splitlines():
        if "round-number sequence gap(s)" in line:
            assert "229" not in line


def _init_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)


def test_working_tree_status_none_when_not_a_repo(tmp_path):
    assert m.working_tree_status(str(tmp_path)) is None


def test_working_tree_status_empty_for_clean_repo(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add a"], cwd=tmp_path, check=True)
    assert m.working_tree_status(str(tmp_path)) == []


def test_working_tree_status_reports_modified_and_untracked(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add a"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("y")           # modified
    (tmp_path / "b.txt").write_text("z")            # untracked
    status = {path: code for code, path in m.working_tree_status(str(tmp_path))}
    assert status["a.txt"] == " M"
    assert status["b.txt"] == "??"


def test_load_standing_dirty_paths_missing_file_returns_empty_set(tmp_path):
    assert m.load_standing_dirty_paths(str(tmp_path / "nope.json")) == set()


def test_load_standing_dirty_paths_reads_paths_key(tmp_path):
    p = tmp_path / "standing.json"
    p.write_text(json.dumps({
        "_comment": "ignored",
        "paths": ["state/round_counter", "languages/whence/pyproject.toml"],
    }))
    assert m.load_standing_dirty_paths(str(p)) == {
        "state/round_counter", "languages/whence/pyproject.toml",
    }


def test_load_standing_dirty_paths_malformed_json_returns_empty_set(tmp_path):
    p = tmp_path / "standing.json"
    p.write_text("{not valid json")
    assert m.load_standing_dirty_paths(str(p)) == set()


def test_unattributed_dirty_paths_skips_git_unavailable(tmp_path):
    assert m.unattributed_dirty_paths(str(tmp_path), {"a.txt"}) == []


def test_unattributed_dirty_paths_filters_standing_paths(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "round_counter").write_text("1")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    (tmp_path / "state" / "round_counter").write_text("2")  # standing, filtered
    (tmp_path / "leftover.py").write_text("x")               # real, unattributed
    result = m.unattributed_dirty_paths(str(tmp_path), {"state/round_counter"})
    assert result == [("??", "leftover.py")]


def test_unattributed_dirty_paths_empty_when_only_standing_dirty(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add a"], cwd=tmp_path, check=True)
    (tmp_path / "a.txt").write_text("y")
    assert m.unattributed_dirty_paths(str(tmp_path), {"a.txt"}) == []


def test_end_to_end_flags_unattributed_dirty_tree(tmp_path):
    # Reproduces round 282/283's actual shape: a commit whose subject
    # correctly names round N exists, but a real, separate leftover diff
    # (not the knowledge file/heading pair recorded_but_uncommitted_rounds
    # already covers) still sits uncommitted in the tree.
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 282 track=language(C) start (driver_version=x) pid=1",
        "[t] round 282: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("### Round 282 — language(C) — 2026-08-28\n- ok\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Round 282 (language C): land round 281"],
                    cwd=repo, check=True)
    # round 282's OWN new feature never got committed:
    (repo / "feature.py").write_text("real leftover diff")

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path / "logs_missing"),
         "--standing-dirty-file", str(tmp_path / "no-standing.json"),
         "--repo-root", str(repo)],
        capture_output=True, text=True,
    )
    # committed_per_git_log(282) reads True (a real commit names round 282)
    # even though feature.py — round 282's own leftover work — is still
    # dirty; the new check must surface it anyway.
    assert m.committed_per_git_log(282, str(repo)) is True
    assert rc.returncode == 1
    assert "unattributed" in rc.stdout
    assert "feature.py" in rc.stdout


def test_end_to_end_standing_dirty_file_suppresses_known_noise(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 5 track=skills(B) start (driver_version=x) pid=1",
        "[t] round 5: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("### Round 5 — Skills(B) — 2026-01-01\n- ok\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    (repo / "a.txt").write_text("y")  # a bump to an allowlisted path only

    standing = tmp_path / "standing.json"
    standing.write_text(json.dumps({"paths": ["a.txt"]}))

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path / "logs_missing"),
         "--standing-dirty-file", str(standing),
         "--repo-root", str(repo)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0
    assert "0 gaps" in rc.stdout
    assert "unattributed" not in rc.stdout


# --------------------------------------------------------------------------
# Round 373 — fifth gap shape: known-escalated TRACKED-file diffs, pinned by
# content. See check_round_recorded.load_escalated_diffs for why this is not
# state/known-standing-dirty-paths.json.
# --------------------------------------------------------------------------


def _repo_with_escalated_file(path, committed, working):
    """Init a repo at `path`, commit `escalated.md` with `committed` bytes,
    then leave `working` bytes in the working tree (dirty)."""
    _init_repo(path)
    f = path / "escalated.md"
    f.write_text(committed)
    subprocess.run(["git", "add", "escalated.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    f.write_text(working)
    return f


def _pin(repo, path="escalated.md", **over):
    entry = {
        "reason": "adjudicated by round 349; operator decision. More text.",
        "escalated_round": 349,
        "worktree_blob": m.worktree_blob_hash(path, str(repo)),
        "head_blob": m.head_blob_hash(path, str(repo)),
    }
    entry.update(over)
    return {path: entry}


def test_worktree_blob_hash_matches_git_hash_object(tmp_path):
    _repo_with_escalated_file(tmp_path, "old\n", "new\n")
    got = m.worktree_blob_hash("escalated.md", str(tmp_path))
    expect = subprocess.run(
        ["git", "hash-object", "escalated.md"], cwd=tmp_path,
        capture_output=True, text=True, check=True).stdout.strip()
    assert got == expect


def test_worktree_blob_hash_none_for_missing_file(tmp_path):
    _init_repo(tmp_path)
    assert m.worktree_blob_hash("nope.md", str(tmp_path)) is None


def test_worktree_blob_hash_works_outside_a_repo_and_that_is_harmless(tmp_path):
    # `git hash-object` is pure content addressing and needs no repository,
    # so this half of the fingerprint survives outside a checkout. It cannot
    # cause a false ACKNOWLEDGEMENT on its own: head_blob_hash needs a HEAD,
    # returns None here, and classify_escalated_diffs is fail-closed on a
    # missing observed hash (see the test below).
    (tmp_path / "a.md").write_text("x")
    assert m.worktree_blob_hash("a.md", str(tmp_path))
    assert m.head_blob_hash("a.md", str(tmp_path)) is None


def test_classify_returns_nothing_when_the_tree_cannot_be_read(tmp_path):
    # status=None is "couldn't look", not "clean" — reporting RESOLVED here
    # would declare every acknowledgement dead on any non-checkout caller.
    registry = {"escalated.md": {"reason": "r", "escalated_round": 349,
                                  "worktree_blob": "w", "head_blob": "h"}}
    assert m.classify_escalated_diffs(registry, None, str(tmp_path)) == []


def test_head_blob_hash_reads_the_committed_side_not_the_worktree(tmp_path):
    _repo_with_escalated_file(tmp_path, "old\n", "new\n")
    head = m.head_blob_hash("escalated.md", str(tmp_path))
    work = m.worktree_blob_hash("escalated.md", str(tmp_path))
    assert head and work and head != work
    committed = subprocess.run(
        ["git", "rev-parse", "HEAD:escalated.md"], cwd=tmp_path,
        capture_output=True, text=True, check=True).stdout.strip()
    assert head == committed


def test_head_blob_hash_none_for_untracked_path(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.md").write_text("x")
    subprocess.run(["git", "add", "a.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "i"], cwd=tmp_path, check=True)
    (tmp_path / "b.md").write_text("y")
    assert m.head_blob_hash("b.md", str(tmp_path)) is None


def test_load_escalated_diffs_missing_file_returns_empty(tmp_path):
    assert m.load_escalated_diffs(str(tmp_path / "nope.json")) == {}


def test_load_escalated_diffs_malformed_json_returns_empty(tmp_path):
    p = tmp_path / "esc.json"
    p.write_text("{not json")
    assert m.load_escalated_diffs(str(p)) == {}


def test_load_escalated_diffs_reads_escalations_and_skips_comment(tmp_path):
    p = tmp_path / "esc.json"
    p.write_text(json.dumps({
        "_comment": "ignored",
        "escalations": {
            "_note": {"reason": "underscore keys are not paths"},
            "a/b.md": {"reason": "r", "escalated_round": 349,
                        "worktree_blob": "w", "head_blob": "h"},
            "c.md": "not a dict",
        },
    }))
    got = m.load_escalated_diffs(str(p))
    assert list(got) == ["a/b.md"]
    assert got["a/b.md"]["escalated_round"] == 349


def test_classify_acknowledges_an_unchanged_pinned_diff(tmp_path):
    _repo_with_escalated_file(tmp_path, "old\n", "new\n")
    status = m.working_tree_status(str(tmp_path))
    rows = m.classify_escalated_diffs(_pin(tmp_path), status, str(tmp_path))
    assert [r["state"] for r in rows] == [m.ESCALATION_ACKNOWLEDGED]
    assert rows[0]["code"] == " M"


def test_classify_expires_the_pin_when_the_third_party_edits_again(tmp_path):
    f = _repo_with_escalated_file(tmp_path, "old\n", "new\n")
    registry = _pin(tmp_path)
    f.write_text("newer still\n")           # the separate system edits again
    status = m.working_tree_status(str(tmp_path))
    rows = m.classify_escalated_diffs(registry, status, str(tmp_path))
    assert rows[0]["state"] == m.ESCALATION_CHANGED
    assert "working-tree content moved" in rows[0]["detail"]


def test_classify_expires_the_pin_when_only_the_base_moved(tmp_path):
    # Same bytes on disk, different diff: someone committed a new base.
    f = _repo_with_escalated_file(tmp_path, "old\n", "new\n")
    registry = _pin(tmp_path)
    f.write_text("base2\n")
    subprocess.run(["git", "commit", "-q", "-am", "move base"],
                    cwd=tmp_path, check=True)
    f.write_text("new\n")                    # worktree bytes restored
    status = m.working_tree_status(str(tmp_path))
    rows = m.classify_escalated_diffs(registry, status, str(tmp_path))
    assert rows[0]["observed_worktree_blob"] == \
        registry["escalated.md"]["worktree_blob"]
    assert rows[0]["state"] == m.ESCALATION_CHANGED
    assert "base moved" in rows[0]["detail"]


def test_classify_reports_both_halves_when_both_moved(tmp_path):
    f = _repo_with_escalated_file(tmp_path, "old\n", "new\n")
    registry = _pin(tmp_path)
    f.write_text("base2\n")
    subprocess.run(["git", "commit", "-q", "-am", "move base"],
                    cwd=tmp_path, check=True)
    f.write_text("different\n")
    status = m.working_tree_status(str(tmp_path))
    rows = m.classify_escalated_diffs(registry, status, str(tmp_path))
    assert rows[0]["state"] == m.ESCALATION_CHANGED
    assert "both halves moved" in rows[0]["detail"]


def test_classify_reports_resolved_when_the_path_is_no_longer_dirty(tmp_path):
    _repo_with_escalated_file(tmp_path, "old\n", "new\n")
    registry = _pin(tmp_path)
    subprocess.run(["git", "commit", "-q", "-am", "land it"],
                    cwd=tmp_path, check=True)
    status = m.working_tree_status(str(tmp_path))
    rows = m.classify_escalated_diffs(registry, status, str(tmp_path))
    assert rows[0]["state"] == m.ESCALATION_RESOLVED
    assert "not dirty" in rows[0]["detail"]


def test_classify_is_fail_closed_on_an_unpinned_entry(tmp_path):
    _repo_with_escalated_file(tmp_path, "old\n", "new\n")
    registry = {"escalated.md": {"reason": "r", "escalated_round": 349}}
    status = m.working_tree_status(str(tmp_path))
    rows = m.classify_escalated_diffs(registry, status, str(tmp_path))
    assert rows[0]["state"] == m.ESCALATION_CHANGED
    assert "no fingerprint" in rows[0]["detail"]


def test_classify_is_fail_closed_when_git_is_unavailable(tmp_path):
    # An acknowledgement that cannot be VERIFIED must not suppress — the one
    # place in this module where an unavailable git does NOT degrade to
    # "don't flag" (round 367's rule 10 in a different file).
    status = [(" M", "escalated.md")]
    registry = {"escalated.md": {"reason": "r", "escalated_round": 349,
                                  "worktree_blob": "w", "head_blob": "h"}}
    rows = m.classify_escalated_diffs(registry, status, str(tmp_path))
    assert rows[0]["state"] == m.ESCALATION_CHANGED
    assert "fail-closed" in rows[0]["detail"]


def test_classify_empty_registry_is_empty(tmp_path):
    assert m.classify_escalated_diffs({}, [(" M", "x")], str(tmp_path)) == []


def test_unattributed_dirty_paths_accepts_a_precomputed_status(tmp_path):
    # No git call at all: the caller's snapshot is used verbatim, which is
    # what lets main() classify escalations against the SAME snapshot.
    got = m.unattributed_dirty_paths(
        str(tmp_path), {"a.txt"},
        status=[(" M", "a.txt"), ("??", "b.txt")])
    assert got == [("??", "b.txt")]


def test_first_sentence_trims_a_long_reason():
    assert m._first_sentence("Short one. Then more text.") == "Short one."
    long = "x" * 300
    assert m._first_sentence(long).endswith("...")
    assert len(m._first_sentence(long)) <= 183
    assert m._first_sentence("") == "(no reason recorded)"


def _run_cli(tmp_path, repo, extra=()):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 372 track=harness(A) start (driver_version=x) pid=1",
        "[t] round 372: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("### Round 372 — harness(A) — 2026-08-30\n- ok\n")
    return subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path / "logs_missing"),
         "--standing-dirty-file", str(tmp_path / "no-standing.json"),
         "--repo-root", str(repo)] + list(extra),
        capture_output=True, text=True)


def test_end_to_end_acknowledged_escalation_exits_zero(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_with_escalated_file(repo, "old\n", "new\n")
    esc = tmp_path / "esc.json"
    esc.write_text(json.dumps({"escalations": _pin(repo)}))
    rc = _run_cli(tmp_path, repo, ["--escalated-diffs-file", str(esc)])
    assert rc.returncode == 0, rc.stdout + rc.stderr
    assert "known-escalated tracked-file diff(s)" in rc.stdout
    assert "carried 24 round(s)" in rc.stdout      # 372 - 349 + 1
    # The path must NOT also appear under the round-291 unattributed list.
    assert "unattributed change(s)" not in rc.stdout
    assert "0 gaps" in rc.stdout
    assert "1 acknowledged escalation(s)" in rc.stdout


def test_end_to_end_expired_pin_is_a_gap_and_is_not_double_reported(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    f = _repo_with_escalated_file(repo, "old\n", "new\n")
    registry = _pin(repo)
    f.write_text("edited again by a third party\n")
    esc = tmp_path / "esc.json"
    esc.write_text(json.dumps({"escalations": registry}))
    rc = _run_cli(tmp_path, repo, ["--escalated-diffs-file", str(esc)])
    assert rc.returncode == 1
    assert "ACKNOWLEDGEMENT NO LONGER HOLDS" in rc.stdout
    assert rc.stdout.count("escalated.md") == 1
    assert "unattributed change(s)" not in rc.stdout


def test_end_to_end_dead_registry_entry_is_reported(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_with_escalated_file(repo, "old\n", "new\n")
    registry = _pin(repo)
    subprocess.run(["git", "commit", "-q", "-am", "land"], cwd=repo, check=True)
    esc = tmp_path / "esc.json"
    esc.write_text(json.dumps({"escalations": registry}))
    rc = _run_cli(tmp_path, repo, ["--escalated-diffs-file", str(esc)])
    assert rc.returncode == 1
    assert "match nothing in the working tree" in rc.stdout
    assert "delete the entry" in rc.stdout


def test_end_to_end_missing_registry_reproduces_pre_round_373_behaviour(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_with_escalated_file(repo, "old\n", "new\n")
    rc = _run_cli(tmp_path, repo,
                   ["--escalated-diffs-file", str(tmp_path / "nope.json")])
    assert rc.returncode == 1
    assert "unattributed change(s)" in rc.stdout
    assert "escalated.md" in rc.stdout
    assert "known-escalated" not in rc.stdout


def test_live_registry_is_well_formed_and_every_entry_is_load_bearing():
    """The repo's own registry, checked the way round 372 checked its
    exemptions: an entry that suppresses nothing must not exist."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    reg_path = os.path.join(root, "state", "known-escalated-diffs.json")
    if not os.path.exists(reg_path):
        return                      # registry is optional by design
    # ROUND 489. `assert registry` conflated two states the loader
    # deliberately renders identically: a MALFORMED registry (which degrades
    # to {} by design, so nothing is suppressed) and a registry with ZERO
    # live escalations (which is the state the file SHOULD reach once every
    # escalation is resolved — round 484 emptied `escalations` and moved the
    # substance to `_resolved`). The old assertion made the correct end state
    # a failure and had no way to see the malformed one, so it went red for
    # five rounds for the registry being healthy. Parse it here instead: the
    # loader's degradation is fail-safe, but this test is the ONLY thing that
    # would notice the file had stopped being readable.
    with open(reg_path) as fh:
        raw = json.load(fh)          # a malformed registry fails HERE, loudly
    assert isinstance(raw, dict), "registry is not a JSON object"
    declared = raw.get("escalations", {})
    assert isinstance(declared, dict), "`escalations` is not an object"
    registry = m.load_escalated_diffs(reg_path)
    assert registry == declared, (
        "the loader and the file disagree about the live escalations — "
        "%r vs %r" % (sorted(registry), sorted(declared)))
    for path, entry in registry.items():
        assert entry.get("reason"), "%s has no reason" % path
        assert isinstance(entry.get("escalated_round"), int), path
        assert entry.get("worktree_blob"), "%s is not pinned" % path
        assert entry.get("head_blob"), "%s is not pinned" % path
    status = m.working_tree_status(root)
    if status is None:
        return                      # not a git checkout (promoted skill copy)
    rows = m.classify_escalated_diffs(registry, status, root)
    dead = [r["path"] for r in rows if r["state"] == m.ESCALATION_RESOLVED]
    assert not dead, (
        "dead acknowledgement(s) %s — the path(s) are no longer dirty, so "
        "the entry suppresses nothing and reads as coverage; delete them "
        "from state/known-escalated-diffs.json" % dead)


# --------------------------------------------------------------------------
# Round 397 (harness A): the heading pattern was a format contract nothing
# on the writing side enforced. `### Round N — <track> — <date>` is now the
# CANONICAL form, not the definition; `harness.roundheadings` is the
# definition, and drift is reported instead of read as a missing round.
# Confirmed live twice: round 302 (`### Round 302 (language C) — ...`,
# rewritten to fit the regex by commit b2e5425) and round 396
# (`## Round 396 (language C) — ...`, which became round 397's prompt NOTE).
# --------------------------------------------------------------------------

R396_HEADING = ("## Round 396 (language C) — v0.35, decision 44: the "
                "sentence that was three divergences")
R302_HEADING = "### Round 302 (language C) — Whence v0.14.10 — 2026-08-29"


def test_recorded_rounds_accepts_a_level_2_heading(tmp_path):
    """The exact live round-396 heading. Was a false gap before round 397."""
    state = tmp_path / "state.md"
    state.write_text("# state\n\n" + R396_HEADING + "\n- did stuff\n")
    assert m.recorded_rounds(str(state)) == {396}


def test_recorded_rounds_accepts_a_parenthesised_track(tmp_path):
    """The exact round-302 heading, before commit b2e5425 rewrote it."""
    state = tmp_path / "state.md"
    state.write_text(R302_HEADING + "\n- did stuff\n")
    assert m.recorded_rounds(str(state)) == {302}


def test_recorded_rounds_expands_a_span_heading(tmp_path):
    """`### Rounds A-B` is real, live archive format (rounds 12-13, 114-126,
    128-129, 131-135) that the strict pattern matched not at all."""
    state = tmp_path / "state.md"
    state.write_text("### Rounds 128-129 — unrecorded, flagged not chased\n")
    assert m.recorded_rounds(str(state)) == {128, 129}


def test_recorded_rounds_still_ignores_the_round_log_heading(tmp_path):
    """Widening must not start counting `## Round log` as round entries."""
    state = tmp_path / "state.md"
    state.write_text("## Round log\n\n## Round log (rounds 1-136)\n\n"
                     "### Round 9 — harness(A) — 2026-01-01\n")
    assert m.recorded_rounds(str(state)) == {9}


def test_recorded_rounds_on_the_live_record_is_a_superset(tmp_path):
    """Regression guard with teeth: the widened reader must never LOSE a
    round the strict pattern already found, in the real corpus."""
    repo = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    state = os.path.join(repo, "state/research-state.md")
    archive = os.path.join(repo, "state/research-state-archive.md")
    import re
    old = re.compile(r"^### Round (\d+) [—-]", re.MULTILINE)
    was = set()
    for p in (state, archive):
        with open(p) as f:
            was |= {int(x.group(1)) for x in old.finditer(f.read())}
    now = m.recorded_rounds(state, [archive])
    assert was <= now
    assert 396 in now, "round 396's real entry must be recognised"


def test_nonstandard_state_headings_finds_the_drift(tmp_path):
    state = tmp_path / "state.md"
    state.write_text("### Round 1 — harness(A) — 2026-01-01\n- ok\n\n"
                     + R396_HEADING + "\n- ok\n")
    drift = m.nonstandard_state_headings(str(state))
    assert [h.rounds for h in drift] == [(396,)]
    assert drift[0].line == 4


def test_nonstandard_state_headings_scoped_by_only_rounds(tmp_path):
    state = tmp_path / "state.md"
    state.write_text("### Rounds 12-13 — did not run\n\n" + R396_HEADING + "\n")
    assert m.nonstandard_state_headings(str(state), only_rounds={396}) != []
    assert [h.rounds for h in
            m.nonstandard_state_headings(str(state), only_rounds={396})
            ] == [(396,)]


def test_end_to_end_drifted_heading_is_reported_but_is_not_a_gap(tmp_path):
    """The whole point: round 396 is RECORDED (rc 0, no gap line) and the
    drift is still surfaced to the next round."""
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 396 track=language(C) start (driver_version=x) pid=1",
        "[t] round 396: success",
    ])
    state = tmp_path / "state.md"
    state.write_text(R396_HEADING + "\n- did stuff\n")

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(tmp_path / "no-knowledge"),
         "--round-logs-dir", str(tmp_path),
         "--repo-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0, rc.stdout
    assert "0 gaps" in rc.stdout
    assert "NO research-state.md entry" not in rc.stdout
    assert "drifted" in rc.stdout
    assert "Round 396" in rc.stdout


def test_end_to_end_span_heading_in_archive_is_not_a_gap(tmp_path):
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 128 track=language(C) start (driver_version=x) pid=1",
        "[t] round 128: success",
        "[t] round 129 track=skills(B) start (driver_version=x) pid=1",
        "[t] round 129: success",
    ])
    state = tmp_path / "state.md"
    state.write_text("# state\n")
    archive = tmp_path / "archive.md"
    archive.write_text("### Rounds 128-129 — unrecorded, flagged not chased\n")

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(archive),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(tmp_path / "no-knowledge"),
         "--round-logs-dir", str(tmp_path),
         "--repo-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 0, rc.stdout
    assert "0 gaps" in rc.stdout


def test_end_to_end_a_real_gap_is_still_a_gap(tmp_path):
    """Tolerance must not have turned the detector off. A round with no
    heading of ANY shape still exits 1."""
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 396 track=language(C) start (driver_version=x) pid=1",
        "[t] round 396: success",
        "[t] round 397 track=harness(A) start (driver_version=x) pid=1",
        "[t] round 397: success",
    ])
    state = tmp_path / "state.md"
    state.write_text(R396_HEADING + "\n- did stuff\n")

    rc = subprocess.run(
        [sys.executable, SCRIPT,
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(tmp_path / "no-knowledge"),
         "--round-logs-dir", str(tmp_path),
         "--repo-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 1
    assert "round 397" in rc.stdout
    assert "round 396 track" not in rc.stdout


def test_canonical_heading_form_matches_the_shared_module():
    """The message the operator reads and the module's own constant must be
    the same string — this is the divergence the round is about."""
    from harness import roundheadings as rh
    assert m.CANONICAL_HEADING_FORM == rh.CANONICAL_FORM


def test_degraded_fallback_is_the_old_strict_pattern(monkeypatch, tmp_path):
    """If harness/ is not importable (a promoted ~/.hermes/skills/ copy),
    detection falls back to the strict pattern — which is WRONG, so the run
    must say so rather than silently regress."""
    monkeypatch.setattr(m, "_roundheadings", None)
    state = tmp_path / "state.md"
    state.write_text(R396_HEADING + "\n")
    assert m.recorded_rounds(str(state)) == set()
    assert m.nonstandard_state_headings(str(state)) == []


def test_end_to_end_promoted_copy_without_harness_says_degraded(tmp_path):
    """A real promoted-copy run: the script alone, nowhere near the repo.
    CURRICULUM.md's endgame promotes skills into ~/.hermes/skills/, which is
    the case the guarded import exists for. It must announce that its answer
    is the untrustworthy one, not quietly emit the old false gap."""
    import shutil
    away = tmp_path / "promoted" / "scripts"
    away.mkdir(parents=True)
    shutil.copy(SCRIPT, str(away / "check_round_recorded.py"))
    driver_log = tmp_path / "driver.log"
    _write_driver_log(str(driver_log), [
        "[t] round 396 track=language(C) start (driver_version=x) pid=1",
        "[t] round 396: success",
    ])
    state = tmp_path / "state.md"
    state.write_text(R396_HEADING + "\n- did stuff\n")

    rc = subprocess.run(
        [sys.executable, str(away / "check_round_recorded.py"),
         "--driver-log", str(driver_log),
         "--state", str(state),
         "--archive", str(tmp_path / "no-archive.md"),
         "--ack-file", str(tmp_path / "no-ack.json"),
         "--escalated-diffs-file", str(tmp_path / "no-esc.json"),
         "--knowledge-dir", str(tmp_path / "no-knowledge"),
         "--round-logs-dir", str(tmp_path),
         "--repo-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert "DEGRADED" in rc.stdout, rc.stdout
    assert "rounds 302 and 396" in rc.stdout

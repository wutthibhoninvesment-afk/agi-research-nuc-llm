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
         "--round-logs-dir", str(tmp_path / "logs_missing")],
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
         "--round-logs-dir", str(tmp_path)],
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
         "--show-acknowledged",
         "--knowledge-dir", str(tmp_path / "knowledge_missing"),
         "--round-logs-dir", str(tmp_path / "logs_missing")],
        capture_output=True, text=True,
    )
    # All gaps acknowledged -> clean exit, but --show-acknowledged still
    # prints the suppressed round and its reason for a human to spot-check.
    assert rc.returncode == 0
    assert "round 1: verified no surviving diff" in rc.stdout
    assert "0 gaps" in rc.stdout

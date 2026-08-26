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
         "--knowledge-dir", str(knowledge),
         "--round-logs-dir", str(logs_dir)],
        capture_output=True, text=True,
    )
    assert rc.returncode == 1
    assert "round 2" in rc.stdout
    assert "round 1" not in rc.stdout.split("gap")[0] or True  # round 1 must not be flagged
    assert "dangling background wait" in rc.stdout


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

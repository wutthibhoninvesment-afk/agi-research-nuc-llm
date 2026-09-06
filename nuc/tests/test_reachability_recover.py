"""Offline tests for nuc/reachability_recover.py (round 454).

The module turns a round's own `logs/round-<N>.json` transcript into a
`state/nuc-reachability-log.jsonl` row. Its parser is pure text-in/dicts-out,
so almost everything here runs against three-line fixtures. The exception is
deliberate and is the most important test in the file:
`test_every_recovered_row_in_the_live_log_still_re_derives` re-runs the
derivation against the real transcripts and demands the result be
byte-identical to what is committed. A recovered row that cannot be
regenerated from its stated evidence is a hand-written row wearing a
provenance label.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reachability_check as rc  # noqa: E402
import reachability_recover as rr  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
REAL_LOG = REPO / "state" / "nuc-reachability-log.jsonl"
TRANSCRIPTS = REPO / "logs"

RECOVERED_ROUNDS = (190, 220, 226, 250, 280, 292, 442)


def _t(ts, use_id, cmd=None, out=None):
    """One transcript line: a tool_use if `cmd`, a tool_result if `out`."""
    if cmd is not None:
        block = {"type": "tool_use", "id": use_id, "name": "Bash",
                 "input": {"command": cmd}}
    else:
        block = {"type": "tool_result", "tool_use_id": use_id,
                 "content": [{"type": "text", "text": out}]}
    return json.dumps({"type": "assistant", "timestamp": ts,
                       "message": {"content": [block]}})


def _probe(cmd, out, use_ts="2026-09-02T01:10:40.681Z",
           res_ts="2026-09-02T01:10:55.748Z"):
    return "\n".join([_t(use_ts, "u1", cmd=cmd), _t(res_ts, "u1", out=out)])


UP_OUT = " 21:49:52 up  9:59,  2 users,  load average: 0.06, 0.02, 0.00"
DOWN_OUT = "ssh: connect to host 100.78.44.111 port 22: Connection timed out"
SSH_CMD = 'ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111 "uptime"'
LAN_CMD = 'ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37 "uptime"'


# --- the parser ------------------------------------------------------------

def test_an_uptime_line_is_an_up_probe():
    p = rr.transcript_probes(_probe(SSH_CMD, UP_OUT))[0]
    assert p["verdict"] == "up"
    assert p["evidence"] == UP_OUT.strip()
    assert p["remote_clock"] == "21:49:52"
    assert p["uptime_text"] == "9:59"


def test_an_ssh_client_failure_line_is_a_down_probe():
    p = rr.transcript_probes(_probe(SSH_CMD, DOWN_OUT))[0]
    assert p["verdict"] == "down"
    assert p["failures"] == {"100.78.44.111": "Connection timed out"}


def test_a_probe_with_both_signals_is_a_conflict_never_an_up():
    """The parser's one real hazard: shell output is unstructured, so a
    command can carry a failure line and an uptime line at once. Refusing to
    guess is the whole reason a human can trust the seven recovered rows."""
    p = rr.transcript_probes(_probe(SSH_CMD, DOWN_OUT + "\n" + UP_OUT))[0]
    assert p["verdict"] == "conflict"
    with pytest.raises(ValueError, match="conflicting"):
        rr.record_from_probes(1, [p])


def test_an_ssh_call_that_says_nothing_either_way_is_unknown():
    p = rr.transcript_probes(_probe(SSH_CMD, "some file listing\n"))[0]
    assert p["verdict"] == "unknown"


def test_a_command_that_never_mentions_the_nuc_is_not_a_probe():
    assert rr.transcript_probes(_probe('ssh git@github.com "uptime"', UP_OUT)) == []
    assert rr.transcript_probes(_probe("uptime", UP_OUT)) == []


def test_an_unpaired_tool_use_is_ignored_rather_than_crashing():
    assert rr.transcript_probes(_t("2026-09-02T01:00:00Z", "u9", cmd=SSH_CMD)) == []


def test_a_corrupt_transcript_line_is_skipped():
    text = "not json at all\n" + _probe(SSH_CMD, UP_OUT)
    assert len(rr.transcript_probes(text)) == 1


# --- the deciding-probe rule ----------------------------------------------

def test_a_down_round_is_decided_by_the_last_tailnet_failure_not_the_last_probe():
    """The LAN path is unusable from the driver host -- there is no
    `id_ed25519_nuc` key -- so its timeout is not a box-down signal at all.
    Taking `downs[-1]` would have pinned round 442's `checked_at_utc` to the
    weaker of its two observations, 21 s after the one that meant something."""
    # Each `_probe` reuses tool_use id "u1", so the two halves are parsed
    # separately and concatenated rather than joined into one transcript.
    probes = (rr.transcript_probes(_probe(SSH_CMD, DOWN_OUT,
                                          "2026-09-02T01:10:40Z", "2026-09-02T01:10:55Z"))
              + rr.transcript_probes(_probe(LAN_CMD,
                                            "ssh: connect to host 192.168.1.37 port 22: "
                                            "Connection timed out",
                                            "2026-09-02T01:11:04Z", "2026-09-02T01:11:16Z")))
    v = rr.verdict_from_probes(probes)
    assert v["verdict"] == "down"
    assert v["deciding"]["at_utc"] == "2026-09-02T01:10:55Z"
    assert "only usable path" in v["why"]


def test_a_down_round_with_only_lan_failures_says_so_loudly():
    probes = rr.transcript_probes(_probe(
        LAN_CMD, "ssh: connect to host 192.168.1.37 port 22: Connection timed out"))
    v = rr.verdict_from_probes(probes)
    assert v["verdict"] == "down"
    assert "unusable path" in v["why"] and "suspicion" in v["why"]


def test_an_up_round_is_decided_by_the_first_probe_that_reached_the_box():
    probes = (rr.transcript_probes(_probe(LAN_CMD, "ssh: connect to host 192.168.1.37 "
                                          "port 22: Connection timed out",
                                          "2026-08-28T09:12:49Z", "2026-08-28T09:12:55Z"))
              + rr.transcript_probes(_probe(SSH_CMD, " 09:13:01 up 21:22,  2 users,  "
                                            "load average: 0.04, 0.04, 0.00",
                                            "2026-08-28T09:12:59Z", "2026-08-28T09:13:01Z")))
    rec = rr.record_from_probes(250, probes)
    assert rec["verdict"] == "up"
    assert rec["checked_at_utc"] == "2026-08-28T09:13:01Z"
    assert rec["ssh_returncode"] == 0 and rec["ssh_stderr"] == ""


def test_no_nuc_probe_at_all_refuses_to_produce_a_record():
    with pytest.raises(ValueError, match="no NUC ssh probe"):
        rr.record_from_probes(1, [])


# --- boot_utc precision ----------------------------------------------------

def test_boot_utc_comes_only_from_an_absolute_uptime_dash_s_line():
    probes = rr.transcript_probes(_probe(SSH_CMD, "2026-08-27 11:50:48\n" + UP_OUT))
    assert rr.record_from_probes(220, probes)["boot_utc"] == "2026-08-27T11:50:48Z"


def test_a_minute_rounded_boot_reading_leaves_boot_utc_null_and_says_why():
    """`boot_utc_crosscheck` runs a 120 s tolerance against this field.
    Feeding it `who -a`'s minute-rounded boot time would manufacture drift
    that is really just rounding -- so rounds 280 and 292, whose transcripts
    have only the coarse form, carry null."""
    probes = rr.transcript_probes(_probe(
        SSH_CMD, UP_OUT + "\n           system boot  2026-08-27 11:50"))
    rec = rr.record_from_probes(292, probes)
    assert rec["boot_utc"] is None
    assert "minute-rounded" in rec["notes"]


def test_a_down_round_reads_no_boot_time_at_all():
    """Nothing reached the box, so any boot-shaped string in the output came
    from somewhere else."""
    text = _probe(SSH_CMD, DOWN_OUT + "\n2026-08-27 11:50:48")
    assert rr.record_from_probes(442, rr.transcript_probes(text))["boot_utc"] is None


def test_timestamps_are_truncated_to_the_second_never_rounded():
    assert rr._to_z("2026-09-02T01:10:55.748Z") == "2026-09-02T01:10:55Z"
    assert rr._to_z(None) is None
    assert rr._to_z("not a timestamp") is None


# --- provenance ------------------------------------------------------------

def test_a_recovered_record_never_claims_to_be_a_live_check():
    rec = rr.record_from_probes(220, rr.transcript_probes(_probe(SSH_CMD, UP_OUT)))
    assert rec["source"] == "transcript-r220"
    assert rec["source"] != "live"
    assert "logs/round-220.json" in rec["notes"]
    assert rec["tailscale_last_seen_utc"] is None


def test_missing_transcript_is_an_error_not_an_empty_record():
    with pytest.raises(FileNotFoundError):
        rr.recover(999999)


def test_recover_refuses_to_duplicate_a_round_that_already_has_a_row(capsys):
    assert rr.main(["recover", "--round", "442",
                    "--log-path", str(REAL_LOG),
                    "--transcript-dir", str(TRANSCRIPTS)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["n_written"] == 0
    assert out["records"][0]["skipped"] == "already has a row"


# --- the real thing --------------------------------------------------------

@pytest.mark.parametrize("round_", RECOVERED_ROUNDS)
def test_every_recovered_row_in_the_live_log_still_re_derives(round_):
    """The pin that makes the recovery auditable rather than asserted.

    Each of these rows was NOT hand-written: it is what
    `reachability_recover.recover(N)` produces from `logs/round-N.json`.
    Re-deriving must reproduce the committed row exactly. If a future round
    edits a recovered row by hand, this goes red and names it."""
    committed = [r for r in rc.load_log(str(REAL_LOG)) if r.get("round") == round_]
    assert len(committed) == 1, "expected exactly one row for round %d" % round_
    assert rr.recover(round_, str(TRANSCRIPTS)) == committed[0]


def test_the_recovered_verdicts_are_the_ones_the_round_records_describe():
    """Independent cross-check: what the transcripts say against what the
    program wrote down elsewhere at the time. Round 190 sits inside the
    184/196 outage; 220/226/250/280/292 all sit inside the long up streak on
    boot 2026-08-27T11:50:48Z; 442 is the third round of the outage that is
    still running."""
    got = {n: rr.recover(n, str(TRANSCRIPTS))["verdict"] for n in RECOVERED_ROUNDS}
    assert got == {190: "down", 220: "up", 226: "up", 250: "up",
                   280: "up", 292: "up", 442: "down"}


def test_the_three_rounds_that_read_uptime_dash_s_agree_on_the_boot():
    """220, 226 and 250 each ran `uptime -s` against the box on different
    days of the same boot. All three must recover the same instant -- and it
    must be the boot the log's own round-202-era rows already carry."""
    boots = {n: rr.recover(n, str(TRANSCRIPTS))["boot_utc"] for n in (220, 226, 250)}
    assert set(boots.values()) == {"2026-08-27T11:50:48Z"}


# --------------------------------------------------------------------------
# Round 460: the plain-text renderer's `last seen 3h ago`, as a bracket.
# Round 454 item 4, which it deliberately left undone rather than divide.
# --------------------------------------------------------------------------

def test_a_rendering_becomes_an_interval_one_unit_wide_plus_the_read_second():
    """`3h` read at 07:57:03 means the age was in [3h, 4h), so the sighting
    was in [03:57:03, 04:57:04] -- one hour wide, plus the second the read
    instant is itself truncated to."""
    lo, hi = rr.rendered_age_bounds("2026-08-27T07:57:03Z", 3, "h")
    assert (lo, hi) == ("2026-08-27T03:57:03Z", "2026-08-27T04:57:04Z")


def test_the_bracket_runs_BACKWARD_from_the_read_not_forward():
    """A floor'd age N means the sighting was at least N ago, so the bracket
    opens EARLIER than `read - N`, never later. Getting this backwards is the
    exact 'rounded value walks into a gap' hazard round 448 named."""
    lo, hi = rr.rendered_age_bounds("2026-01-01T12:00:00Z", 1, "h")
    assert lo == "2026-01-01T10:00:00Z"
    assert hi == "2026-01-01T11:00:01Z"


def test_every_documented_unit_has_a_width_and_an_unknown_one_raises():
    for unit, secs in rr.RENDERED_AGE_UNIT_S.items():
        lo, hi = rr.rendered_age_bounds("2026-01-01T12:00:00Z", 1, unit)
        assert lo < hi
    with pytest.raises(KeyError):
        rr.rendered_age_bounds("2026-01-01T12:00:00Z", 1, "w")


def test_two_readings_intersect_to_something_tighter_than_either():
    a = rr.rendered_age_bounds("2026-08-27T07:57:03Z", 3, "h")
    b = rr.rendered_age_bounds("2026-08-27T08:03:21Z", 3, "h")
    got = rr.intersect_bounds([a, b])
    assert got == ("2026-08-27T04:03:21Z", "2026-08-27T04:57:04Z")
    width = lambda p: (rc._parse_ts(p[1]) - rc._parse_ts(p[0])).total_seconds()
    assert width(got) < width(a) and width(got) < width(b)
    # tightened by exactly the spacing between the two reads
    assert width(a) - width(got) == 378.0


def test_brackets_that_do_not_intersect_produce_nothing_not_a_favourite():
    """Positive evidence the value MOVED between reads -- round 448's
    recomputation finding arriving through the plain-text door. Fails closed."""
    a = ("2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z")
    b = ("2026-01-01T03:00:00Z", "2026-01-01T04:00:00Z")
    assert rr.intersect_bounds([a, b]) is None
    assert rr.intersect_bounds([]) is None


def test_readings_are_found_outside_ssh_calls_too():
    """`transcript_probes` only looks at ssh calls. Round 190's two readings
    came from two different Bash calls and only one of them ran ssh, so an
    ssh-only scan finds one reading and a 3601 s bracket instead of two and
    3223 s."""
    text = open(TRANSCRIPTS / "round-190.json").read()
    readings = rr.transcript_lastseen_readings(text)
    assert [r["rendering"] for r in readings] == ["3h", "3h"]
    assert [r["read_at_utc"] for r in readings] == ["2026-08-27T07:57:03Z",
                                                    "2026-08-27T08:03:21Z"]
    probes_with_a_line = [p for p in rr.transcript_probes(text) if p["tailscale_line"]]
    assert len(probes_with_a_line) < len(readings)


@pytest.mark.parametrize("round_", [220, 226, 250, 280, 292, 442])
def test_the_other_six_recovered_rounds_carry_no_rendering_at_all(round_):
    """Round 460's bank declared it had NO BASIS for these six and would
    report what they hold. They hold nothing: the `~40-46m` strings a naive
    grep finds in five of them are round 184's prose being quoted forward, not
    a `tailscale status` line. So exactly one row in the log gains a bracket."""
    text = open(TRANSCRIPTS / ("round-%d.json" % round_)).read()
    assert rr.transcript_lastseen_readings(text) == []
    assert "tailscale_last_seen_bounds_utc" not in rr.recover(round_, str(TRANSCRIPTS))


def test_the_recovered_bracket_contains_the_json_value_an_independent_check_read():
    """THE cross-validation, and it was not designed for -- it fell out.

    Round 190's bracket is derived entirely from two plain-text `3h ago`
    renderings at 07:57:03Z and 08:03:21Z. Round 196 is a different check,
    almost three hours later, reading `tailscale status --json`'s exact
    `LastSeen` field. If the floor-renderer model this round calibrated on
    THIS host's four peers were wrong -- if the renderer rounded to nearest,
    say -- the bracket would sit an hour off and would not contain 196's
    value. It contains it, with 45m00.1s of margin below and 8m42.9s above
    (the JSON field carries tailscale's one fractional digit; the bracket is
    whole seconds, which is why the two margins are not round numbers).

    Two independent instruments, three hours apart, one unchanging outage.
    """
    row196 = next(r for r in rc.load_log(str(REAL_LOG)) if r["round"] == 196)
    # RE-DERIVED, not read from the log: this has to falsify the renderer
    # MODEL, and a committed row does not move when the model changes. Under
    # round-to-nearest instead of floor the bracket becomes [04:57:03,
    # 04:57:04] and misses 196's value by nine minutes.
    row190 = rr.recover(190, str(TRANSCRIPTS))
    assert row190 == next(r for r in rc.load_log(str(REAL_LOG)) if r["round"] == 190)
    lo, hi = [rc._parse_ts(v) for v in row190["tailscale_last_seen_bounds_utc"]]
    v = rc._parse_ts(row196["tailscale_last_seen_utc"])
    assert lo <= v <= hi
    assert (v - lo).total_seconds() == 2700.1
    assert (hi - v).total_seconds() == 522.9


# --- the rewrite guard -----------------------------------------------------

def test_a_rewrite_that_would_change_a_derived_value_is_refused():
    """The add-only rule, falsified. A row whose regeneration would CHANGE a
    key -- not add one -- must stop the whole batch, because that means the
    derivation's meaning moved and a human should read about it first."""
    import json as _json
    tmp = REAL_LOG.parent / "_r460_guard_test.jsonl"
    row = rr.recover(190, str(TRANSCRIPTS))
    row["verdict"] = "up"          # a value the transcript does not support
    tmp.write_text(_json.dumps(row) + "\n")
    try:
        out = rr.rewrite(str(tmp), str(TRANSCRIPTS), apply=True)
        assert out["safe"] is False
        assert out["applied"] is False
        assert "verdict" in out["unsafe"][0]["blocking"]
        assert _json.loads(tmp.read_text())["verdict"] == "up", "refused means untouched"
    finally:
        tmp.unlink()


def test_notes_may_be_extended_but_not_edited():
    """The one permitted change, and its limit."""
    import json as _json
    tmp = REAL_LOG.parent / "_r460_notes_test.jsonl"
    row = rr.recover(190, str(TRANSCRIPTS))
    truncated = dict(row, notes=row["notes"][:80])
    tmp.write_text(_json.dumps(truncated) + "\n")
    try:
        assert rr.rewrite(str(tmp), str(TRANSCRIPTS))["safe"] is True
        edited = dict(row, notes="something else entirely")
        tmp.write_text(_json.dumps(edited) + "\n")
        out = rr.rewrite(str(tmp), str(TRANSCRIPTS))
        assert out["safe"] is False and out["unsafe"][0]["blocking"] == ["notes"]
    finally:
        tmp.unlink()


def test_the_live_log_is_currently_in_sync_with_its_transcripts():
    """The standing invariant, as a command rather than as prose."""
    plan = rr.rewrite(str(REAL_LOG), str(TRANSCRIPTS))
    assert plan["n_changes"] == 0, plan["changes"]


# --------------------------------------------------------------------------
# Round 520 (NUC-integration E): the row that signed someone else's name.
#
# `record_from_probes` opened its notes with the fixed string "Recovered by
# round 454 ... which round 310's prose backfill never read". Round 520 used
# the verb to recover round 514's missing row and the row came out asserting
# that round 310 had failed to read `logs/round-514.json` -- a transcript that
# did not exist when round 310 ran, about a round 200 later. The attribution
# was a template, and `rewrite_plan` re-derived every row under the same
# constant, so the first row written by anybody else read as an unsafe change.

def test_a_recovered_row_names_the_round_that_recovered_it(tmp_path):
    rec = rr.recover(514, "logs", by_round=520)
    assert rec["recovered_by_round"] == 520
    assert rec["notes"].startswith("Recovered by round 520 ")


def test_the_default_author_is_454_so_the_seven_old_rows_re_derive(tmp_path):
    rec = rr.recover(292, "logs")
    assert rec["recovered_by_round"] == rr.DEFAULT_RECOVER_ROUND == 454
    assert rec["notes"].startswith("Recovered by round 454 ")


def test_the_round_310_clause_is_dropped_above_that_backfills_horizon():
    """Round 310's prose backfill is a fact about rounds in round 454's own
    bracket. Above it the clause is not merely unsigned, it is false."""
    above = rr.recover(514, "logs", by_round=520)
    below = rr.recover(292, "logs")
    assert "round 310's prose backfill" not in above["notes"]
    assert "round 310's prose backfill never read" in below["notes"]
    assert 514 > rr.BACKFILL_HORIZON_ROUND >= 292


def test_rewrite_re_derives_each_row_under_ITS_OWN_author(tmp_path):
    """The point of storing the field: the derivation is reproducible from
    the row, not from a module constant. Without this, one row by a second
    author makes `rewrite` refuse the whole batch."""
    plan = rr.rewrite_plan(rc.DEFAULT_LOG_PATH, "logs")
    assert plan["n_changes"] == 0, plan["changes"]
    rows = [r for r in rc.load_log(rc.DEFAULT_LOG_PATH)
            if str(r.get("source", "")).startswith("transcript-r")]
    authors = sorted({r["recovered_by_round"] for r in rows})
    assert authors == [454, 520], authors

"""Tests for nuc/dose_response.py (round 472).

The transcript fixtures are VERBATIM shell commands lifted out of
`logs/round-424.json`, not invented ones. That is load-bearing twice over.
The first draft of `command_contact` scored

    cat > nuc/predictions-e-round424.md <<'EOF' ... EOF

as a login to the NUC, because round 424's own prediction file quotes an ssh
command line for the tailnet address inside the heredoc body. And round 424's
capture is `ssh ... 'cat /work/...' > state/nuc-capture-r424/...`, so the
3.26 MB it pulled off the box reaches the transcript as 489 bytes of stdout --
a dose read from `tool_result` alone scores the heaviest round in the corpus
as one of the lightest. Neither failure is reachable from a hand-written
fixture, and both change the published answer.

Nothing here opens a socket or runs a command, so this file is safe to run
from any track and there is no path by which it can contact port 8001.
"""
import pathlib
import re

import pytest

from nuc import dose_response as dr
from nuc import perturbation as pt


_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CAP = _ROOT / "state" / "nuc-capture-r424"
_SAR = (_CAP / "sar-all.txt").read_text()
_JRNL = (_CAP / "journal-pid1-full.txt").read_text()

# The real false positive, trimmed to its first lines. The body quotes the
# tailnet address; nothing here opens a connection.
HEREDOC_FALSE_POSITIVE = (
    "cat > nuc/predictions-e-round424.md <<'EOF'\n"
    "# Round 424 (NUC-integration E) - predictions, written BEFORE measuring\n"
    "`nuc/reachability_check.py check --round 424` at `2026-09-01T08:10:46Z`:\n"
    "`ssh jab@100.78.44.111` rc 0, `tailscale_online: true`,\n"
    "EOF\n")

# The real probe, verbatim in shape.
REAL_PROBE = ("timeout 120 ssh -i ~/.ssh/id_ed25519 -o ConnectTimeout=15 "
              "-o BatchMode=yes jab@100.78.44.111 'uptime -s'")

# The real capture step: a variable holds the target, the verb is three lines
# away, and the payload goes to a FILE.
REAL_CAPTURE = (
    "NUC=jab@100.78.44.111; KEY=$HOME/.ssh/id_ed25519; "
    "OUT=state/nuc-capture-r424\n"
    "ssh -i $KEY $NUC 'journalctl -o short-iso _PID=1' "
    "> $OUT/journal-pid1-full.txt\n"
    "ssh -i $KEY $NUC 'sar -A' > $OUT/sar-all.txt 2>&1\n")

_BMAP = None


def _bmap():
    """One `BucketMap` for this file; ~11 s to build and a pure function of
    the two fixture texts."""
    global _BMAP
    if _BMAP is None:
        _BMAP = pt.BucketMap(_SAR, _JRNL)
    return _BMAP


# ------------------------------------------------- F1: the heredoc body

def test_a_heredoc_body_quoting_an_ssh_line_is_not_a_login():
    """FALSIFIER. This is the bug, not a hypothetical: without
    `strip_heredocs`, round 424's prediction file counts as a contact with the
    box and inflates that round's login dose."""
    hit = dr.command_contact(HEREDOC_FALSE_POSITIVE)
    assert hit["n_logins"] == 0
    assert hit["addressed"] is False
    assert hit["why_zero"] == "neither"


def test_strip_heredocs_keeps_the_opener_line():
    """The real invocation OPENS a heredoc on the line that connects:
    `ssh ... 'bash -s' <<'REMOTE'`. Stripping the opener too would zero the
    dose of every remote-script call round 424 made."""
    cmd = ("ssh -i k jab@100.78.44.111 'bash -s' <<'REMOTE'\n"
           "echo not-a-command-of-ours\n"
           "REMOTE\n")
    out = dr.strip_heredocs(cmd)
    assert "jab@100.78.44.111" in out
    assert "not-a-command-of-ours" not in out
    assert dr.command_contact(cmd)["n_logins"] == 1


def test_two_heredocs_on_one_line_both_close():
    cmd = ("cmd <<'A' <<'B'\nbody-a\nA\nbody-b\nB\nssh jab@100.78.44.111 x\n")
    out = dr.strip_heredocs(cmd)
    assert "body-a" not in out and "body-b" not in out
    assert dr.command_contact(cmd)["n_logins"] == 1


def test_an_unterminated_heredoc_swallows_the_rest_and_does_not_hang():
    """A truncated transcript entry must terminate, and must not resurrect the
    body as command text."""
    out = dr.strip_heredocs("cat > f <<'EOF'\nssh jab@100.78.44.111 x\n")
    assert "100.78.44.111" not in out


# ------------------------------------- F2/F3: what actually crossed the wire

def test_a_redirect_to_a_file_is_counted_and_2gt1_is_not():
    """FALSIFIER for the dose's biggest error. `2>&1` and `/dev/null` are not
    payloads; `> $OUT/...` is."""
    paths = dr.landed_paths(REAL_CAPTURE)
    assert "state/nuc-capture-r424/journal-pid1-full.txt" in paths
    assert "state/nuc-capture-r424/sar-all.txt" in paths
    assert not any("&1" in p for p in paths)
    assert not any(p.startswith("/dev/") for p in paths)


def test_the_landed_bytes_of_round_424s_capture_are_megabytes_not_hundreds():
    """The whole reason `bytes_landed` exists. Scored on stdout alone the
    heaviest round in the corpus looks like one of the lightest."""
    land = dr.landed_bytes(REAL_CAPTURE, str(_ROOT))
    assert land["bytes"] > 2_000_000
    assert land["unresolved"] == []


def test_a_target_reached_only_through_a_shell_variable_still_counts():
    """FALSIFIER. Round 424's capture never puts the verb and the address on
    one line; a same-line test scores it zero."""
    hit = dr.command_contact(REAL_CAPTURE)
    assert hit["n_logins"] == 2
    assert hit["via_variable"] == ["NUC"]


def test_an_unknown_variable_is_left_alone_so_the_miss_is_visible():
    """One level of expansion is all this does. A two-level indirection must
    surface as an unresolved path, never as a silent zero."""
    assert dr.expand_vars("$UNSET/x", {}) == "$UNSET/x"
    land = dr.landed_bytes("ssh jab@100.78.44.111 cat /a > $UNSET/x",
                           str(_ROOT))
    assert land["bytes"] == 0
    assert land["unresolved"] == ["$UNSET/x"]


def test_a_local_command_with_a_redirect_never_lands_anything():
    """`landed_paths` is only ever called for commands that contacted the box;
    a purely local `cat > f` must not be able to donate bytes to a dose."""
    d = dr.transcript_dose(_jsonl([("cat /etc/hostname > /tmp/x", "out")]))
    assert d["n_calls"] == 0
    assert d["bytes_landed"] == 0


def test_an_ssh_to_some_other_host_is_not_a_nuc_login():
    hit = dr.command_contact("ssh -i k user@example.com uptime")
    assert hit["n_logins"] == 0
    assert hit["why_zero"] == "transfer verb but no NUC address"


def test_the_tailnet_NAME_alone_is_not_a_contact():
    """`pgain-nuc` appears in prose constantly. Admitting it as a target would
    score every round file that mentions the box."""
    assert "pgain-nuc" not in dr.NUC_TARGETS
    assert dr.command_contact("echo the box pgain-nuc is down")["n_logins"] == 0


def test_several_verbs_in_one_call_are_several_logins():
    """The journal records one scope per SESSION, not per Bash call."""
    cmd = ("scp -i k jab@100.78.44.111:/a /tmp/a\n"
           "scp -i k jab@100.78.44.111:/b /tmp/b\n"
           "ssh -i k jab@100.78.44.111 sync\n")
    hit = dr.command_contact(cmd)
    assert hit["n_logins"] == 3
    assert hit["verbs"] == ["scp", "scp", "ssh"]


def test_the_word_ssh_inside_a_path_is_not_a_verb():
    hit = dr.command_contact("ls ~/.ssh/id_ed25519 jab@100.78.44.111")
    assert hit["n_logins"] == 0
    assert hit["why_zero"] == "addressed but no transfer verb"


# ------------------------------------------------- the transcript reader

def _jsonl(pairs):
    """A minimal stream-json transcript: one Bash call per (cmd, out)."""
    import json
    out = []
    for i, (cmd, res) in enumerate(pairs):
        out.append(json.dumps({
            "type": "assistant", "timestamp": "2026-08-30T10:0%d:00.000Z" % i,
            "message": {"content": [{"type": "tool_use", "id": "t%d" % i,
                                     "name": "Bash",
                                     "input": {"command": cmd}}]}}))
        out.append(json.dumps({
            "type": "user", "timestamp": "2026-08-30T10:0%d:05.000Z" % i,
            "message": {"content": [{"type": "tool_result",
                                     "tool_use_id": "t%d" % i,
                                     "content": [{"type": "text",
                                                  "text": res}]}]}}))
    return "\n".join(out)


def test_a_transcript_splits_nuc_calls_from_local_ones():
    text = _jsonl([(REAL_PROBE, "2026-09-01 05:33:27"),
                   ("ls -la knowledge/", "a\nb\n"),
                   (HEREDOC_FALSE_POSITIVE, "")])
    d = dr.transcript_dose(text, 999)
    assert d["n_calls"] == 1 and d["n_logins"] == 1
    assert d["local_calls"] == 2
    assert d["box_seconds"] == 5.0
    assert d["first_contact_utc"] == "2026-08-30T10:00:00Z"


def test_a_tool_result_with_no_matching_tool_use_is_ignored():
    import json
    text = json.dumps({"type": "user", "timestamp": "2026-08-30T10:00:00.0Z",
                       "message": {"content": [
                           {"type": "tool_result", "tool_use_id": "orphan",
                            "content": "x"}]}})
    assert dr.transcript_dose(text)["n_calls"] == 0


def test_a_non_bash_tool_never_contributes_a_dose():
    """A `Read` of a file whose text quotes an ssh line is not a login."""
    import json
    text = "\n".join([
        json.dumps({"type": "assistant", "timestamp": "2026-08-30T10:00:00.0Z",
                    "message": {"content": [
                        {"type": "tool_use", "id": "r1", "name": "Read",
                         "input": {"command": REAL_PROBE}}]}}),
        json.dumps({"type": "user", "timestamp": "2026-08-30T10:00:01.0Z",
                    "message": {"content": [
                        {"type": "tool_result", "tool_use_id": "r1",
                         "content": "x"}]}})])
    assert dr.transcript_dose(text)["n_calls"] == 0


def test_a_missing_transcript_is_reported_not_dropped():
    rows = dr.round_doses([999999], str(_ROOT / "logs"))
    assert rows[0]["missing"] is True and rows[0]["n_logins"] == 0


def test_round_424s_real_transcript_reads_as_a_heavy_capture_round():
    """The end-to-end pin. If any of the four parsing rules above regresses,
    this number moves."""
    d = dr.transcript_dose((_ROOT / "logs" / "round-424.json")
                           .read_text(errors="replace"), 424, str(_ROOT))
    assert d["n_calls"] == 9 and d["n_logins"] == 12
    assert d["bytes_returned"] < 20_000          # stdout says: a light round
    assert d["bytes_landed"] > 2_800_000         # the wire says: the heaviest
    assert d["n_scp"] == 0                       # and it used no scp at all


# --------------------------------------------------------- the statistics

def test_spearman_is_exact_on_a_perfect_monotone_pair():
    assert dr.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert dr.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_spearman_uses_mid_ranks_for_ties():
    """The response variable's median is ZERO -- half the windows tie. A rank
    rule that broke ties by position would read the arbitrary order of the
    input as signal."""
    a = dr.spearman([1, 2, 3, 4], [0, 0, 1, 1])
    b = dr.spearman([1, 2, 3, 4], [0, 0, 1, 1][::-1])
    assert a == pytest.approx(-b)
    assert a == pytest.approx(0.8944, abs=1e-4)


def test_a_constant_dose_correlates_with_nothing_and_does_not_crash():
    assert dr.spearman([5, 5, 5, 5], [1, 2, 3, 4]) == 0.0


def test_spearman_refuses_two_points():
    with pytest.raises(pt.PerturbationError, match="at least 3"):
        dr.spearman([1, 2], [1, 2])


def test_the_permutation_null_holds_both_marginals_fixed():
    """FALSIFIER for the test itself: a perfect correlation must sit at the
    p floor, and an exchangeable pairing must not."""
    xs = list(range(12))
    hot = dr.permutation_test(xs, xs, trials=2000, seed=7)
    assert hot["p_two_sided"] <= 2.0 / 2000
    flat = dr.permutation_test(xs, [1] * 12, trials=2000, seed=7)
    assert flat["rho"] == 0.0 and flat["p_two_sided"] == 1.0


def test_the_permutation_p_is_two_sided():
    xs = list(range(12))
    down = dr.permutation_test(xs, xs[::-1], trials=2000, seed=7)
    assert down["rho"] == pytest.approx(-1.0)
    assert down["p_two_sided"] <= 2.0 / 2000


# ---------------------------------------- F4: the confound, held open

def _row(**kw):
    base = {"round": 1, "first_contact_utc": "2026-08-30T10:00:00Z",
            "window_utc": ["2026-08-30T09:55:00Z", "2026-08-30T10:55:00Z"],
            "abs_lo": 0, "abs_hi": 3600, "n_calls": 1, "n_logins": 1,
            "n_scp": 0, "box_seconds": 1.0, "bytes_returned": 1,
            "bytes_landed": 0, "bytes_moved": 1, "local_calls": 1,
            "local_bytes": 1, "transcript_bytes": 1, "n_buckets": 7,
            "n_buckets_expected": 7, "fully_covered": True,
            "record_coverage": "full", "n_costly_buckets": 0,
            "swap_bytes": 0}
    base.update(kw)
    return base


def test_a_window_the_record_does_not_cover_is_marked_not_scored_as_zero():
    """FALSIFIER, and the error this round nearly published. A DOWN round's
    window has no sar buckets, so its response is zero BY CONSTRUCTION -- and
    a down round also makes two probe calls instead of fifteen. Pooled, that
    pairs `few calls` with `zero swap` for a reason that is the box's power
    switch. Unstratified, this corpus reports rho +0.42 at p 0.006; stratified
    it reports rho +0.26 at p 0.18."""
    def _dose(round_, at):
        return {"round": round_, "missing": False, "n_calls": 2,
                "n_logins": 2, "n_scp": 0, "box_seconds": 1.0,
                "bytes_returned": 1, "bytes_landed": 0, "bytes_moved": 1,
                "local_calls": 1, "local_bytes": 1, "transcript_bytes": 1,
                "first_contact_utc": at}
    # Round 184's real probe instant. That round found the box DOWN, and the
    # sar record has nothing there -- so its window's response is zero for a
    # reason that is the power switch, not the cost of the round.
    # Round 208's real probe instant, on a stretch the record does cover.
    win = dr.score_windows([_dose(184, "2026-08-27T05:27:24Z"),
                            _dose(208, "2026-08-27T16:26:31Z")], _bmap())
    by = {r["round"]: r for r in win["scored"]}
    assert by[184]["record_coverage"] == "none"
    assert by[184]["n_buckets"] == 0 and by[184]["swap_bytes"] == 0
    assert by[208]["record_coverage"] == "full"
    assert by[208]["n_buckets"] == 7 and by[208]["n_buckets_expected"] == 7
    assert win["n_full"] == 1 and win["n_no_record"] == 1


def test_the_stratifier_is_what_separates_the_two_answers():
    """Synthetic, and deliberately extreme: five uncovered windows with a
    small dose and a zero response, five covered ones with no association at
    all. Pooled they correlate; stratified they do not."""
    # The dose rises monotonically and the response does NOT track it: this
    # stratum has rho ~ -0.03 on its own. The first draft of this fixture used
    # `n_calls=10+(i%2)` against `swap=(i%2)*10`, which is a PERFECT rank
    # correlation dressed up as a null -- it went red on the first run and the
    # test was the thing that was wrong.
    _resp = [3000, 1000, 5000, 0, 4000, 2000]
    covered = [_row(round=i, n_calls=10 + i, swap_bytes=_resp[i],
                    record_coverage="full") for i in range(6)]
    dead = [_row(round=100 + i, n_calls=2, swap_bytes=0, n_buckets=0,
                 record_coverage="none") for i in range(6)]
    pooled = dr.dose_response(covered + dead, trials=2000)
    strat = dr.dose_response(covered, trials=2000)
    assert pooled["table"]["n_calls"]["rho"] > 0.6
    assert abs(strat["table"]["n_calls"]["rho"]) < 0.6


def test_the_verdict_says_confounded_when_a_control_matches_the_dose():
    """FALSIFIER for the reporting rule. A dose-response conclusion that never
    looks at its controls is the failure mode this whole round is about."""
    rows = [_row(round=i, n_calls=i, local_calls=i, swap_bytes=i * 1000)
            for i in range(8)]
    out = dr.dose_response(rows, trials=2000)
    assert out["verdict"].startswith("CONFOUNDED")
    assert out["dose_beats_every_control"] is False


def test_the_verdict_can_still_say_dose_response():
    """The positive branch must be REACHABLE, or `NULL` is not a finding.
    Round 466's F1/F7 lesson: a falsifier that goes 0 red because its branch
    is unreachable is a design problem, not a testing one."""
    rows = [_row(round=i, n_calls=1, local_calls=(i * 7) % 8, local_bytes=1,
                 transcript_bytes=1, bytes_landed=i * 1000,
                 bytes_moved=i * 1000, box_seconds=1.0, bytes_returned=1,
                 n_logins=1, swap_bytes=i * 1000) for i in range(10)]
    out = dr.dose_response(rows, trials=2000)
    assert out["verdict"].startswith("DOSE-RESPONSE"), out["verdict"]
    assert out["strongest_dose"] in dr.DOSES


def test_dose_response_refuses_a_sample_of_two():
    with pytest.raises(pt.PerturbationError, match="at least 3"):
        dr.dose_response([_row(round=1), _row(round=2)], trials=10)


# ----------------------------------------- F5: the fast index vs the scan

def test_the_run_index_agrees_with_the_per_second_scan():
    """FALSIFIER. `span_buckets` stopped scanning every second when the null
    became 216 million lookups; if the bisect index disagrees with the scan by
    one bucket, every p-value in this round is wrong."""
    b = _bmap()
    spans = [(0, 3600), (86_400 - 1800, 86_400 + 1800),
             (500_000, 503_601), (b.span_s - 3601, b.span_s - 1)]
    out = b.verify_runs(spans)
    assert out["identical"], out["divergences"]


def test_a_wrapped_span_is_the_same_set_as_its_two_halves():
    """The shift null wraps windows past the end of the pooled span; a wrap
    that silently dropped the tail would make every null draw cheap."""
    b = _bmap()
    # The tail must be long enough to reach COVERED ground. The pooled window
    # opens at 2026-08-23T14:02, so seconds 0..50 000 of day 0 hold no defined
    # bucket -- a short wrap has an empty tail and a dropped-tail bug passes
    # the test unnoticed. This one was caught by mutation, not by review.
    lo = b.span_s - 300
    wrapped = b.span_buckets(lo, lo + 60_000)
    halves = (b.span_buckets(lo, b.span_s - 1)
              | b.span_buckets(0, 60_000 - 300))
    assert wrapped == halves
    assert len(b.span_buckets(0, 60_000 - 300)) > 0, "tail must not be empty"


def test_the_map_still_verifies_against_cost_ledger():
    """Round 466's own self-check, re-run after round 472 added `_map_any`,
    `all_bucket_bytes` and the run index to the same constructor."""
    b = _bmap()
    out = b.verify(pt.parse_unit_starts(_JRNL))
    assert out["identical"], out


def test_every_bucket_has_bytes_and_the_costly_ones_are_a_subset():
    b = _bmap()
    assert set(b.bucket_bytes) <= set(b.all_bucket_bytes)
    assert len(b.all_bucket_bytes) > len(b.bucket_bytes)
    assert all(b.all_bucket_bytes[k] >= b.min_bytes for k in b.costly)


# --------------------------------- F6: the shift null's support problem

def test_restricting_the_shift_group_changes_which_days_it_can_reach():
    """FALSIFIER. Unrestricted, the null moves the round train onto
    2026-08-23/24, where no E round can occur (the driver log begins with
    round 152 on 08-26) and where the record's largest bucket lives. A null
    free to land where the observation cannot is not a null on the
    observation."""
    b = _bmap()
    rows = [_row(round=1, abs_lo=3 * 86400, abs_hi=3 * 86400 + 3600),
            _row(round=2, abs_lo=5 * 86400, abs_hi=5 * 86400 + 3600),
            _row(round=3, abs_lo=6 * 86400, abs_hi=6 * 86400 + 3600)]
    wide = dr.window_shift_null(b, rows, trials=200, seed=3)
    tight = dr.window_shift_null(b, rows, trials=200, seed=3,
                                 restrict_to_round_days=True)
    assert wide["shift_group_days"] == [b.days[0], b.days[-1]]
    assert tight["shift_group_days"] == [b.days[3], b.days[6]]
    assert tight["restricted_to_round_days"] is True


def test_the_shift_null_reports_a_median_as_well_as_a_mean():
    """A single 2.34 GiB bucket dominates this record, so the null's MEAN
    bytes is not its typical draw. Round 466 published a mean; a mean alone
    invites `observed < null` to be read as `below chance` when most draws are
    below the observation."""
    b = _bmap()
    out = dr.window_shift_null(b, [_row(abs_lo=4 * 86400,
                                        abs_hi=4 * 86400 + 3600)],
                               trials=200, seed=3)
    assert "null_median_bytes" in out and "null_median_costly" in out
    assert out["null_median_bytes"] <= out["null_p95_bytes"]


def test_the_shift_null_refuses_an_empty_window_set():
    with pytest.raises(pt.PerturbationError, match="no scored windows"):
        dr.window_shift_null(_bmap(), [], trials=10)


# ------------------------- F7: the dose validated against another file

def test_the_journal_sees_more_sessions_than_the_transcript_counts_verbs():
    """FALSIFIER, and it goes RED if the disagreement is ever smoothed over.
    Two independent records of the same logins: the transcript counts transfer
    verbs, the journal counts scopes systemd actually created. They correlate
    strongly (rho ~0.67) and they do NOT agree in level -- the journal sees
    about 1.6 scopes per counted verb. That gap is a finding about the dose,
    not a rounding error, and the report must carry it."""
    rows = [_row(round=1, window_utc=["2026-08-30T14:52:00Z",
                                      "2026-08-30T15:52:00Z"], n_logins=19)]
    out = dr.dose_vs_scopes(rows, _JRNL)
    assert out["n_windows"] == 1
    assert out["rows"][0]["n_session_scopes_journal"] > 0
    assert out["ratio_journal_over_transcript"] is not None


def test_scope_provenance_calls_pre_transcript_scopes_untestable():
    """FALSIFIER. The journal begins 2026-08-23 and the transcript corpus
    begins 2026-08-26. Scoring the earlier scopes as `unmatched` would
    manufacture hundreds of negatives from a file that did not exist yet --
    exactly the mistake round 466 refused to make with its 19 buckets."""
    doses = dr.round_doses([370, 376], str(_ROOT / "logs"), str(_ROOT))
    out = dr.scope_provenance(_JRNL, doses)
    assert out["n_untestable_before_transcripts"] > 0
    assert (out["n_testable"] + out["n_untestable_before_transcripts"]
            == out["n_scopes"])
    assert out["first_transcript_date"] >= "2026-08-26"


def test_scope_provenance_refuses_a_corpus_with_no_calls():
    with pytest.raises(pt.PerturbationError, match="no NUC calls"):
        dr.scope_provenance(_JRNL, [{"round": 1, "missing": True}])


# ------------------- F8: the exclusion decision, and what it must not do

def test_is_session_scope_matches_only_login_scopes():
    assert pt.is_session_scope("session-1401.scope")
    assert not pt.is_session_scope("session-manager.service")
    assert not pt.is_session_scope("user-1000.slice")
    assert not pt.is_session_scope("session-33")


def test_reading_the_exclusion_tables_does_not_apply_the_exclusion():
    """FALSIFIER, and the reason round 466 refused to decide alone. A function
    that publishes `what if we excluded` must not BE the exclusion: a silent
    edit to `LEDGER_EXCLUDE_UNITS` would move round 466's published 94.0 %
    with nothing in any round file saying so."""
    before = tuple(pt.LEDGER_EXCLUDE_UNITS)
    out = pt.session_exclusion_tables(_SAR, _JRNL, trials=50, bmap=_bmap())
    assert tuple(pt.LEDGER_EXCLUDE_UNITS) == before == ("sysstat-collect",)
    assert out["n_session_scope_fires"] == 1401
    assert out["decision_is_load_bearing"] is True


def test_both_tables_are_published_side_by_side():
    out = pt.session_exclusion_tables(_SAR, _JRNL, trials=50, bmap=_bmap())
    names = [r["population"] for r in out["coverage"]["populations"]]
    assert any("WITH session scopes" in n for n in names)
    assert any("WITHOUT session scopes" in n for n in names)
    assert out["delta_if_excluded"]["n_costly_named"] < 0


# ------------------------------------------------------- the CLI contract

def test_the_dose_subcommand_runs_and_emits_json(capsys):
    import json
    rc = dr.main(["dose", "--rounds", "424",
                  "--transcripts", str(_ROOT / "logs")])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["round"] == 424 and rows[0]["n_logins"] == 12
    assert "calls" not in rows[0]


def test_the_docstring_names_the_two_files_that_must_not_know_each_other():
    """The design claim this module rests on, kept honest against edits."""
    assert "logs/round-<N>.json" in dr.__doc__
    assert "sar-all.txt" in dr.__doc__


def test_nothing_in_this_module_can_reach_port_8001():
    src = (pathlib.Path(dr.__file__)).read_text()
    assert "8001" not in src
    assert not re.search(r"\bimport (socket|requests|urllib)", src)


# ------------- F9: the null that takes the record's own holes out of itself

def test_the_covered_rate_null_refuses_a_partly_uncovered_observation():
    """FALSIFIER. The rate null's whole point is that observed and null are
    the same quantity; feeding it a window the record does not cover makes the
    numerator and the denominator disagree, and it must refuse rather than
    divide."""
    b = _bmap()
    rows = [_row(round=1, abs_lo=3 * 86400, abs_hi=3 * 86400 + 3600),
            _row(round=2, abs_lo=1 * 86400 + 100, abs_hi=1 * 86400 + 3700)]
    covered = [r for r in rows
               if len(b.span_buckets(r["abs_lo"], r["abs_hi"])) >= 7]
    if len(covered) == len(rows):
        pytest.skip("both fixture spans happen to be covered")
    with pytest.raises(pt.PerturbationError, match="fully covered"):
        dr.covered_rate_null(b, rows, trials=20)


def test_the_covered_rate_null_scores_a_rate_not_a_count():
    """A draw that lands most of the train on downtime must contribute its
    RATE over what it did cover, not a count depressed by the record's holes.
    `n_draws_skipped_no_coverage` is reported so a null that mostly failed to
    land anywhere cannot pass itself off as 2000 trials."""
    b = _bmap()
    rows = [_row(round=i, abs_lo=(3 + i) * 86400 + 36000,
                 abs_hi=(3 + i) * 86400 + 39600) for i in range(3)]
    rows = [r for r in rows
            if len(b.span_buckets(r["abs_lo"], r["abs_hi"])) >= 7]
    if not rows:
        pytest.skip("no fully covered fixture span")
    out = dr.covered_rate_null(b, rows, trials=100, seed=11)
    assert 0.0 <= out["observed_rate"] <= 1.0
    assert 0.0 <= out["null_mean_rate"] <= 1.0
    assert out["n_draws_scored"] + out["n_draws_skipped_no_coverage"] == 100
    assert out["p_floor"] == pytest.approx(1.0 / out["n_draws_scored"])


def test_the_covered_fire_null_reports_its_identity_draws():
    """FALSIFIER, and it exists because mutation found the field untested.
    Whole-day offsets over a population whose own day range is N days include
    N x 86400, which is the identity: it ties the observation by definition
    and must not be counted as a draw that beat it. Round 472 publishes
    `ours` at p 0.1111 including that tie and p 0.0000 without it, so the
    field decides a published number."""
    b = _bmap()
    fires = pt.parse_unit_starts_any_kind(_JRNL, ("scope",))
    span_days = ((max(b.seconds(fires)) // 86400)
                 - (min(b.seconds(fires)) // 86400) + 1)
    out = pt.shift_null_covered(b, fires,
                                shifts=[86400, 86400 * span_days])
    assert out["offsets_were_explicit"] is True
    assert out["n_identity_draws"] == 1
    assert out["n_draws_ge_observed"] >= 1
    assert (out["p_value_excluding_identity"]
            == pytest.approx(out["p_value"] - 1.0 / out["n_draws_scored"]))


def test_the_covered_rate_null_refuses_an_empty_window_set():
    with pytest.raises(pt.PerturbationError, match="no scored windows"):
        dr.covered_rate_null(_bmap(), [], trials=10)

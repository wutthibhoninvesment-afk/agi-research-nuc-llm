#!/usr/bin/env python3
"""Falsifiers for nuc/record_union.py (round 490).

Same discipline as test_fossil_ledger.py: every test here was checked by
mutating the module and confirming this test goes red. The ledger is at the
bottom in `MUTATIONS`.

The module's whole claim is "the union loses nothing and invents nothing", so
the tests that matter are the ones that would go red if it did either: a
conflict that must be reported rather than resolved, a repeated line that must
survive dedup, and a capture with no record that must be NAMED.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import record_union as ru  # noqa: E402
import perturbation as pt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
STATE = os.path.join(ROOT, "state")
LIVE = [os.path.join(STATE, "nuc-capture-r%s" % n)
        for n in ("400", "406", "424", "430", "460", "466", "472", "478",
                  "484")]
UNION_DIR = os.path.join(STATE, "nuc-record-union")

BANNER = "Linux 6.8.0-79-generic (pgain-nuc) \t09/01/2026 \t_x86_64_\t(4 CPU)"
HEAD = "00:00:01        kbmemfree   kbavail kbmemused  %memused kbbuffers"


def sar_day(stamps, banner=BANNER, average=True, restart_at=None):
    """A minimal `sar -r`-shaped section body with one row per stamp."""
    out = [banner, ""]
    out.append("00:00:01    kbmemfree   kbmemused  kbcommit")
    for i, s in enumerate(stamps):
        if restart_at == s:
            out.append("")
            out.append("14:32:11          LINUX RESTART      (4 CPU)")
            out.append("")
            out.append("00:00:01    kbmemfree   kbmemused  kbcommit")
        out.append("%s      %d      %d      %d" % (s, 1000 + i, 2000 + i,
                                                   3000 + i))
    if average:
        out.append("Average:      %d      %d      %d"
                   % (len(stamps), len(stamps), len(stamps)))
    return "\n".join(out)


def capture(tmp_path, name, sections=None, journal=None):
    d = tmp_path / name
    d.mkdir()
    if sections is not None:
        (d / ru.SAR_FILE).write_text(
            "\n".join("### %s\n%s" % (n, b) for n, b in sections))
    if journal is not None:
        (d / ru.JOURNAL_FILE).write_text(journal)
    return str(d)


# ------------------------------------------------------------ split_section

def test_split_section_separates_rows_from_the_average_line():
    """`Average:` is not a bucket. It reaches `tail` because it carries no
    `HH:MM:SS` first token, so the mutation that matters is one that widens
    the stamp test -- not one that deletes a branch, which round 490's
    mutation pass proved was dead."""
    p = ru.split_section(sar_day(["00:00:01", "00:10:01"]))
    assert sorted(p["rows"]) == ["00:00:01", "00:10:01"]
    assert any(l.startswith("Average:") for l in p["tail"])
    assert not any(l.startswith("Average:") for l in p["preamble"])
    assert not ru._TIME_TOKEN.match("Average:")


def test_split_section_attaches_a_restart_marker_to_the_row_after_it():
    p = ru.split_section(sar_day(["00:00:01", "00:10:01"],
                                 restart_at="00:10:01"))
    assert p["rows"]["00:00:01"]["restart_before"] == ()
    assert len(p["rows"]["00:10:01"]["restart_before"]) == 1
    assert "LINUX RESTART" in p["rows"]["00:10:01"]["restart_before"][0]


def test_split_section_keeps_a_repeated_header_out_of_the_rows():
    body = sar_day(["00:00:01"]) + "\n" + HEAD + "\n01:00:01      1 2 3"
    p = ru.split_section(body)
    assert sorted(p["rows"]) == ["00:00:01", "01:00:01"]


def test_split_section_reads_a_meridiem_stamp_as_one_stamp():
    body = "\n".join([BANNER, "12:00:01 AM  kbmemfree kbmemused kbcommit",
                      "12:10:01 AM      1 2 3", "01:10:01 PM      4 5 6"])
    p = ru.split_section(body)
    assert sorted(p["rows"]) == ["01:10:01 PM", "12:10:01 AM"]
    assert ru._stamp_key("12:10:01 AM") == 601
    assert ru._stamp_key("01:10:01 PM") == 13 * 3600 + 601


# ------------------------------------------------------------ merge_section

def test_a_shorter_capture_of_the_same_day_is_a_prefix_and_is_not_a_conflict():
    short = sar_day(["00:00:01", "00:10:01"])
    long_ = sar_day(["00:00:01", "00:10:01", "00:20:01"])
    res = ru.merge_section([("early", short), ("late", long_)])
    assert res["n_conflicts"] == 0
    assert res["strategy"] == "verbatim_superset"
    assert res["chosen_capture"] == "late"
    assert res["n_rows_union"] == 3


def test_the_average_line_alone_never_makes_two_captures_disagree():
    """P3 of round 490's bank. `sar` averages over the rows it was given, so
    the same day read twice has two different `Average:` lines and identical
    data. A section-level diff calls that a conflict; this must not."""
    short = sar_day(["00:00:01", "00:10:01"])
    long_ = sar_day(["00:00:01", "00:10:01", "00:20:01"])
    assert short.splitlines()[-1] != long_.splitlines()[-1]
    assert ru.merge_section([("a", short), ("b", long_)])["n_conflicts"] == 0


def test_two_captures_that_disagree_about_a_row_report_a_conflict():
    a = sar_day(["00:00:01", "00:10:01"])
    b = a.replace("00:10:01      1001", "00:10:01      9999")
    res = ru.merge_section([("a", a), ("b", b)])
    assert res["n_conflicts"] == 1
    c = res["conflicts"][0]
    assert c["stamp"] == "00:10:01"
    assert c["a_capture"] == "a" and c["b_capture"] == "b"
    assert "9999" in c["b"]


def test_a_conflict_forces_the_merge_path_and_never_the_verbatim_one():
    """A conflict means no capture is authoritative, so emitting one
    capture's bytes verbatim would silently pick a winner."""
    a = sar_day(["00:00:01", "00:10:01"])
    b = a.replace("00:10:01      1001", "00:10:01      9999")
    res = ru.merge_section([("a", a), ("b", b)])
    assert res["strategy"] == "merged_rows"
    assert res["chosen_capture"] is None


def test_neither_capture_a_superset_takes_the_merge_path_and_drops_average():
    a = sar_day(["00:00:01", "00:20:01"])
    b = sar_day(["00:10:01", "00:20:01"])
    res = ru.merge_section([("a", a), ("b", b)])
    assert res["strategy"] == "merged_rows"
    assert res["n_rows_union"] == 3
    assert res["average_line_dropped"] is True
    assert "Average:" not in res["text"]


def test_the_merged_text_is_in_time_order_and_reparses():
    a = sar_day(["00:20:01"])
    b = sar_day(["00:00:01", "00:10:01"])
    res = ru.merge_section([("a", a), ("b", b)])
    table = pt.parse_sar(res["text"])
    assert [r.time for r in table.rows] == ["00:00:01", "00:10:01", "00:20:01"]


def test_a_restart_marker_that_moved_between_captures_is_a_conflict():
    a = sar_day(["00:00:01", "00:10:01"])
    b = sar_day(["00:00:01", "00:10:01"], restart_at="00:10:01")
    res = ru.merge_section([("a", a), ("b", b)])
    assert any(c.get("field") == "restart_before" for c in res["conflicts"])


# ---------------------------------------------------------------- union_sar

def test_a_capture_with_no_sar_is_named_not_skipped():
    """Round 406's lesson, which `fossil_ledger` learned first: a capture that
    contributes nothing must appear in the report saying so, or a `glob` that
    silently matches fewer directories looks like a clean run."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path
        td = Path(td)
        good = capture(td, "good", [("SAR_R_SA01", sar_day(["00:00:01"]))])
        bad = capture(td, "bad")
        _, rep = ru.union_sar([good, bad])
        assert rep["n_captures_unusable"] == 1
        assert rep["unusable"][0]["capture"] == "bad"
        assert rep["captures_read"] == ["good"]


def test_a_section_with_no_banner_is_reported_and_never_pooled(tmp_path):
    body = "\n".join(["00:00:01  kbmemfree kbmemused kbcommit",
                      "00:10:01      1 2 3"])
    c = capture(tmp_path, "c", [("SAR_R_SA01", body)])
    _, rep = ru.union_sar([c])
    assert rep["n_sections"] == 0
    assert len(rep["undated_or_unnamed_sections"]) == 1
    assert "banner" in rep["undated_or_unnamed_sections"][0]["why"]


def test_a_section_whose_name_and_banner_disagree_is_reported(tmp_path):
    """`window_frame` raises on this; the union must not hand it one."""
    c = capture(tmp_path, "c", [("SAR_R_SA09", sar_day(["00:00:01"]))])
    _, rep = ru.union_sar([c])
    assert rep["n_sections"] == 0
    assert "name says day 09" in rep["undated_or_unnamed_sections"][0]["why"]


def test_the_union_text_carries_every_date_and_reparses(tmp_path):
    a = capture(tmp_path, "a", [("SAR_R_SA01", sar_day(["00:00:01"]))])
    b = capture(tmp_path, "b", [
        ("SAR_R_SA02", sar_day(["00:00:01"],
                               banner=BANNER.replace("09/01", "09/02")))])
    text, rep = ru.union_sar([a, b])
    assert rep["dates"] == ["2026-09-01", "2026-09-02"]
    assert sorted(pt.sar_sections(text)) == ["SAR_R_SA01", "SAR_R_SA02"]


# ------------------------------------------------------------ union_journal

JL = "2026-09-01T%s+00:00 pgain-nuc systemd[1]: %s"


def test_a_line_repeated_inside_one_capture_survives_the_union(tmp_path):
    """The bug the first draft shipped and its own `--strict` gate caught.
    Every journal in this repo holds 2-3 byte-identical lines; they are two
    real events inside one second, and whole-line dedup deletes one of each.
    `parse_unit_starts` counts fires, so the deletion is a fire."""
    dup = JL % ("00:00:01", "Starting rsyslog.service - System Logging...")
    a = capture(tmp_path, "a", journal="\n".join([dup, dup]))
    b = capture(tmp_path, "b", journal=dup)
    text, rep = ru.union_journal([a, b])
    assert text.count(dup) == 2
    assert rep["n_lines_kept_by_multiplicity"] == 1
    assert rep["dedup_is_lossless"] is True
    assert rep["multiplicity_losses"] == []


def test_the_same_line_in_two_captures_is_one_event_not_two(tmp_path):
    line = JL % ("00:00:01", "Starting foo.service - foo...")
    a = capture(tmp_path, "a", journal=line)
    b = capture(tmp_path, "b", journal=line)
    text, rep = ru.union_journal([a, b])
    assert text.strip().splitlines() == [line]
    assert rep["n_lines_all"] == 2 and rep["n_lines_union"] == 1


def test_lossless_is_re_derived_and_not_asserted(tmp_path):
    """`dedup_is_lossless` must come from comparing the union against each
    capture, so that breaking the multiplicity rule turns it False."""
    dup = JL % ("00:00:01", "Reloading...")
    a = capture(tmp_path, "a", journal="\n".join([dup, dup]))
    _, rep = ru.union_journal([a])
    assert rep["dedup_is_lossless"] is True
    losses = ru._multiplicity_losses([("a", [dup, dup])], {dup: 1})
    assert losses and losses[0]["in_capture"] == 2 and losses[0]["in_union"] == 1
    assert ru._multiplicity_losses([("a", [dup, dup])], {dup: 2}) == []


def test_the_union_is_in_time_order_across_captures(tmp_path):
    late = JL % ("12:00:00", "Starting late.service - late...")
    early = JL % ("01:00:00", "Starting early.service - early...")
    a = capture(tmp_path, "a", journal=late)
    b = capture(tmp_path, "b", journal=early)
    text, _ = ru.union_journal([a, b])
    assert text.strip().splitlines() == [early, late]


def test_a_boot_separator_is_attached_to_the_boot_it_introduces(tmp_path):
    sep = "-- Boot %s --" % ("a" * 32)
    body = "\n".join([JL % ("01:00:00", "Starting a.service - a..."), sep,
                      JL % ("02:00:00", "Starting b.service - b...")])
    a = capture(tmp_path, "a", journal=body)
    text, rep = ru.union_journal([a])
    lines = text.strip().splitlines()
    assert lines.index(sep) == lines.index(
        JL % ("02:00:00", "Starting b.service - b...")) - 1
    assert rep["n_separators_kept"] == 1


def test_a_separator_two_captures_place_differently_is_reported(tmp_path):
    """Journal decay, made visible. Round 484 measured 5h30m of one boot's
    interior vanishing between two captures; when that happens the separator
    introducing that boot attaches to a later instant in the newer capture."""
    sep = "-- Boot %s --" % ("b" * 32)
    a = capture(tmp_path, "a", journal="\n".join(
        [sep, JL % ("01:00:00", "Starting a.service - a...")]))
    b = capture(tmp_path, "b", journal="\n".join(
        [sep, JL % ("05:00:00", "Starting c.service - c...")]))
    text, rep = ru.union_journal([a, b])
    assert len(rep["separator_attachment_disagreements"]) == 1
    d = rep["separator_attachment_disagreements"][0]
    assert d["kept"] == "2026-09-01T01:00:00"
    assert d["also_seen_at"] == "2026-09-01T05:00:00"
    assert rep["n_separators_kept"] == 1
    # and the separator is EMITTED at the kept instant, not merely reported
    # there -- round 490's mutation pass: flipping `earliest` to `latest`
    # moved the emission and left the report alone.
    lines = text.strip().splitlines()
    assert lines[lines.index(sep) + 1] == JL % ("01:00:00",
                                                "Starting a.service - a...")


def test_the_unioned_journal_holds_every_captures_unit_starts(tmp_path):
    a = capture(tmp_path, "a", journal=JL % ("01:00:00",
                                             "Starting a.service - a..."))
    b = capture(tmp_path, "b", journal=JL % ("02:00:00",
                                             "Starting b.service - b..."))
    _, rep = ru.union_journal([a, b])
    assert rep["n_unit_starts_per_capture"] == {"a": 1, "b": 1}
    assert rep["n_unit_starts_union"] == 2


def test_no_capture_with_a_journal_raises(tmp_path):
    c = capture(tmp_path, "c", [("SAR_R_SA01", sar_day(["00:00:01"]))])
    with pytest.raises(pt.PerturbationError):
        ru.union_journal([c])


# ---------------------------------------------------------------- frame_gain

def test_frame_gain_reports_what_unioning_only_the_sar_would_have_bought(
        tmp_path):
    """The plausible mistake, priced. Unioning the sar and keeping the newest
    journal leaves the recovered days unpaired, and `window_frame` drops an
    unpaired day, so half the job buys less than half the gain."""
    d1 = sar_day(["00:00:01"], banner=BANNER.replace("09/01", "09/01"))
    d2 = sar_day(["00:00:01"], banner=BANNER.replace("09/01", "09/02"))
    j1 = "2026-09-01T00:05:00+00:00 pgain-nuc systemd[1]: Starting a.service - a..."
    j2 = "2026-09-02T00:05:00+00:00 pgain-nuc systemd[1]: Starting b.service - b..."
    # `window_frame` defaults to the SWAP channel, whose sections are
    # `SAR_W_*`; a fixture built out of `SAR_R_*` pairs nothing and the test
    # would pass for the wrong reason if it asserted zero.
    a = capture(tmp_path, "a", [("SAR_W_SA01", d1)], journal=j1)
    b = capture(tmp_path, "b", [("SAR_W_SA02", d2)], journal=j2)
    rep = ru.frame_gain([a, b])
    assert rep["union"]["n_paired"] == 2
    assert rep["best_single_n_paired"] == 1
    assert rep["gain_over_best_single"] == 1
    assert rep["union_sar_newest_journal_only"]["n_paired"] == 1
    assert rep["union_sar_newest_journal_only"]["dropped_dates"] == [
        "2026-09-01"]


# --------------------------------------------------------------------- CLI

def cli(*args):
    p = subprocess.run(
        [sys.executable, os.path.join(ROOT, "nuc", "record_union.py")]
        + list(args), capture_output=True, text=True)
    return p


def test_cli_sar_strict_exits_1_on_a_conflict(tmp_path):
    a = capture(tmp_path, "a", [("SAR_R_SA01", sar_day(["00:00:01"]))])
    bad = sar_day(["00:00:01"]).replace("00:00:01      1000",
                                        "00:00:01      7777")
    b = capture(tmp_path, "b", [("SAR_R_SA01", bad)])
    p = cli("sar", "--captures", a, b, "--strict")
    assert p.returncode == 1
    assert json.loads(p.stdout)["n_conflicts"] == 1


def test_cli_sar_strict_exits_0_when_clean(tmp_path):
    a = capture(tmp_path, "a", [("SAR_R_SA01", sar_day(["00:00:01"]))])
    p = cli("sar", "--captures", a, "--strict")
    assert p.returncode == 0


def test_cli_build_writes_both_files(tmp_path):
    a = capture(tmp_path, "a", [("SAR_R_SA01", sar_day(["00:00:01"]))],
                journal=JL % ("00:05:00", "Starting a.service - a..."))
    out = tmp_path / "out"
    p = cli("build", "--captures", a, "--out-dir", str(out))
    assert p.returncode == 0
    assert (out / ru.SAR_FILE).exists() and (out / ru.JOURNAL_FILE).exists()


def test_cli_frame_strict_exits_1_when_the_union_buys_nothing(tmp_path):
    a = capture(tmp_path, "a", [("SAR_W_SA01", sar_day(["00:00:01"]))],
                journal=JL % ("00:05:00", "Starting a.service - a..."))
    p = cli("frame", "--captures", a, "--strict")
    assert p.returncode == 1
    assert json.loads(p.stdout)["gain_over_best_single"] == 0


def test_the_cli_expands_a_quoted_glob(tmp_path):
    """Round 490 shipped this module documenting `--captures
    'state/nuc-capture-r*'` in its own SKILL.md, its own next-steps and its
    own missions addendum, and the CLI did not glob. The quoted pattern
    reaches the process as one literal path."""
    capture(tmp_path, "cap-a", [("SAR_W_SA01", sar_day(["00:00:01"]))])
    capture(tmp_path, "cap-b", [("SAR_W_SA02", sar_day(
        ["00:00:01"], banner=BANNER.replace("09/01", "09/02")))])
    assert len(ru.expand_captures([str(tmp_path / "cap-*")])) == 2
    p = cli("sar", "--captures", str(tmp_path / "cap-*"), "--strict")
    assert p.returncode == 0
    assert json.loads(p.stdout)["n_captures_read"] == 2


def test_a_pattern_that_matches_nothing_is_passed_through_and_named(tmp_path):
    """`fossil_ledger`'s choice, kept: a glob with no hits must reach the
    report as an unusable input, not vanish."""
    out = ru.expand_captures([str(tmp_path / "nope-*")])
    assert out == [str(tmp_path / "nope-*")]
    _, rep = ru.union_sar(out)
    assert rep["n_captures_unusable"] == 1


def test_strict_fails_on_a_union_of_nothing_rather_than_reporting_zero():
    """The vacuous pass. Zero captures read -> zero sections -> zero conflicts,
    and a conflict-only gate calls that clean. Round 490's own final check
    caught its own module doing exactly this."""
    _, rep = ru.union_sar(["/definitely/not/a/capture"])
    assert rep["n_conflicts"] == 0          # true, and meaningless
    assert rep["n_captures_read"] == 0
    assert ru._sar_strict_fails(rep) is True
    p = cli("sar", "--captures", "/definitely/not/a/capture", "--strict")
    assert p.returncode == 1


# ----------------------------------------------- the live corpus in this repo

@pytest.mark.skipif(not os.path.isdir(os.path.join(STATE, "nuc-capture-r424")),
                    reason="captures not in this checkout")
def test_the_live_captures_union_without_a_single_conflict():
    """The claim round 490 published. Two reads of one append-only day-file
    must agree where they overlap; if this ever goes red the union is not a
    union and no number computed from it can be quoted."""
    _, rep = ru.union_sar(LIVE)
    assert rep["n_conflicts"] == 0
    assert rep["n_merged_sections"] == 0
    assert rep["n_captures_read"] == 4
    # derived, not pinned: every DOWN round banks a capture with no sar in it,
    # so a literal here goes red on schedule for a reason that is not a
    # defect. Round 490 learned this from `test_fossil_ledger.py`, which was
    # pinned at 5 and went red on round 490's own capture.
    assert rep["n_captures_unusable"] == len(LIVE) - 4


@pytest.mark.skipif(not os.path.isdir(os.path.join(STATE, "nuc-capture-r424")),
                    reason="captures not in this checkout")
def test_the_live_union_covers_twelve_dates_and_september_2_is_absent():
    """09-02 is in no capture because the box was down all day. The union is
    the union of what exists, not a calendar."""
    _, rep = ru.union_sar(LIVE)
    assert rep["n_dates"] == 12
    assert rep["dates"][0] == "2026-08-23" and rep["dates"][-1] == "2026-09-04"
    assert "2026-09-02" not in rep["dates"]


@pytest.mark.skipif(not os.path.isdir(os.path.join(STATE, "nuc-capture-r424")),
                    reason="captures not in this checkout")
def test_the_newest_capture_is_not_the_best_one():
    """The reason this module exists. r484 is the newest sar record in this
    repo and it has LOST four days to the 00:07 sweep round 484 watched fire,
    so a round that reaches for the newest capture gets the smallest record."""
    _, rep = ru.union_sar(LIVE)
    per_cap: dict = {}
    for s in rep["per_section"]:
        for c in s["contributing_captures"]:
            per_cap.setdefault(c, set()).add(s["date"])
    assert len(per_cap["nuc-capture-r484"]) == 8
    assert len(per_cap["nuc-capture-r424"]) == 10
    assert len(per_cap["nuc-capture-r478"]) == 11
    assert rep["n_dates"] == 12


@pytest.mark.skipif(not os.path.isdir(os.path.join(STATE, "nuc-capture-r424")),
                    reason="captures not in this checkout")
def test_the_live_journal_union_is_lossless_and_gains_fires():
    _, rep = ru.union_journal(LIVE)
    assert rep["dedup_is_lossless"] is True
    assert rep["n_unit_starts_union"] > max(
        rep["n_unit_starts_per_capture"].values())
    assert rep["span_union"] == ["2026-08-23T14:02:08", "2026-09-04T01:26:56"]


@pytest.mark.skipif(not os.path.isdir(UNION_DIR),
                    reason="the built union is not in this checkout")
def test_the_committed_union_is_what_the_module_produces_today():
    """The union in `state/nuc-record-union/` is an ARTEFACT every published
    number of round 490 is computed from. If the module drifts from it, the
    numbers stop being reproducible and this says so before anyone quotes
    them."""
    text, _ = ru.union_sar(LIVE)
    assert text == open(os.path.join(UNION_DIR, ru.SAR_FILE),
                        errors="replace").read()
    jtext, _ = ru.union_journal(LIVE)
    assert jtext == open(os.path.join(UNION_DIR, ru.JOURNAL_FILE),
                         errors="replace").read()


# --------------------------------------------------------------- mutations
#
# Every falsifier above was checked by mutating `nuc/record_union.py` and
# confirming the named test goes red. Round 490, first pass and second.
MUTATIONS = [
    ("merge_section: drop the `_norm(prev) != _norm(row)` conflict test",
     "test_two_captures_that_disagree_about_a_row_report_a_conflict"),
    ("merge_section: allow `verbatim_superset` when conflicts is non-empty",
     "test_a_conflict_forces_the_merge_path_and_never_the_verbatim_one"),
    ("merge_section: keep the `Average:` line on the merged path",
     "test_neither_capture_a_superset_takes_the_merge_path_and_drops_average"),
    ("merge_section: drop the restart_before comparison",
     "test_a_restart_marker_that_moved_between_captures_is_a_conflict"),
    ("split_section: let `_TIME_TOKEN` match `Average:`, making it a row",
     "test_split_section_separates_rows_from_the_average_line"),
    ("split_section: emit restart markers as their own line, unattached",
     "test_split_section_attaches_a_restart_marker_to_the_row_after_it"),
    ("union_sar: `continue` instead of appending to `unusable`",
     "test_a_capture_with_no_sar_is_named_not_skipped"),
    ("union_sar: drop the name-vs-banner day check",
     "test_a_section_whose_name_and_banner_disagree_is_reported"),
    ("union_journal: dedup by presence instead of multiplicity",
     "test_a_line_repeated_inside_one_capture_survives_the_union"),
    ("union_journal: `_multiplicity_losses` returns [] unconditionally",
     "test_lossless_is_re_derived_and_not_asserted"),
    ("union_journal: attach separators to the PRECEDING dated line",
     "test_a_boot_separator_is_attached_to_the_boot_it_introduces"),
    ("union_journal: keep the latest separator attachment, not the earliest",
     "test_a_separator_two_captures_place_differently_is_reported"),
    ("frame_gain: report the union frame as `union_sar_newest_journal_only`",
     "test_frame_gain_reports_what_unioning_only_the_sar_would_have_bought"),
    ("CLI: return 0 unconditionally from `sar`",
     "test_cli_sar_strict_exits_1_on_a_conflict"),
    ("CLI: `caps = list(args.captures)`, i.e. no glob expansion",
     "test_the_cli_expands_a_quoted_glob"),
    ("expand_captures: drop a pattern that matches nothing",
     "test_a_pattern_that_matches_nothing_is_passed_through_and_named"),
    ("_sar_strict_fails: conflicts only, no `n_captures_read == 0` clause",
     "test_strict_fails_on_a_union_of_nothing_rather_than_reporting_zero"),
    ("CLI: return 0 unconditionally from `frame`",
     "test_cli_frame_strict_exits_1_when_the_union_buys_nothing"),
]


def test_every_mutation_names_a_test_that_exists():
    here = set(globals())
    missing = [t for _, t in MUTATIONS if t not in here]
    assert missing == [], missing

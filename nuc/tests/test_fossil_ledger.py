#!/usr/bin/env python3
"""Falsifiers for nuc/fossil_ledger.py (round 484).

Same discipline as test_summary_fossil.py: every test here was checked by
mutating the module and confirming this test goes red. The ledger is at the
bottom in `MUTATIONS`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fossil_ledger as fl  # noqa: E402
import summary_fossil as sf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
CAPTURES = os.path.join(ROOT, "state")
R478 = os.path.join(CAPTURES, "nuc-capture-r478")
R484 = os.path.join(CAPTURES, "nuc-capture-r484")
LIVE_LEDGER = os.path.join(CAPTURES, "nuc-fossil-ledger.jsonl")


def cap(tmp_path, name, ls_rows, boot_last=None):
    """A minimal capture directory: sar-all.txt, optionally journal-boots."""
    d = tmp_path / name
    d.mkdir()
    body = ["### SYSSTAT_FILES", "total 100"]
    for nm, size, stamp in ls_rows:
        body.append(f"-rw-r--r-- 1 root root {size:>8} {stamp} {nm}")
    body.append("### SAR_R_SA10")
    (d / "sar-all.txt").write_text("\n".join(body) + "\n")
    if boot_last:
        (d / "journal-boots.txt").write_text(
            "IDX BOOT ID                          FIRST ENTRY"
            "                 LAST ENTRY\n"
            "  0 0d0e3188da124a4b9f78b26dd95d3ea2 "
            f"Thu 2026-08-10 09:37:16 UTC {boot_last} UTC\n")
    return str(d)


# --------------------------------------------------------------------------
# `now` provenance -- the thing a file mtime must never supply
# --------------------------------------------------------------------------

def test_now_is_derived_from_the_boot_table_inside_the_capture(tmp_path):
    d = cap(tmp_path, "nuc-capture-rX",
            [("sa10", 1000, "Aug 10 23:50")], "Wed 2026-08-12 09:00:00")
    assert fl.capture_now(d) == ("2026-08-12T09:00:00Z", "boot_table")


def test_a_capture_with_no_boot_table_and_no_declaration_is_unusable(tmp_path):
    """Not skipped -- named. Round 406's lesson: the expensive failure is a
    missing input that leaves no trace."""
    d = cap(tmp_path, "nuc-capture-rY", [("sa10", 1000, "Aug 10 23:50")])
    got = fl.read_capture(d)
    assert got["ok"] is False
    assert got["now_source"] == "unknown"
    assert "journal-boots" in got["reason"]


def test_a_declared_now_is_labelled_as_declared_not_derived(tmp_path):
    d = cap(tmp_path, "nuc-capture-rZ", [("sa10", 1000, "Aug 10 23:50")])
    got = fl.read_capture(d, "2026-08-12T09:00:00Z")
    assert got["ok"] is True and got["now_source"] == "argument"


def test_the_capture_now_of_a_real_capture_is_its_own_last_journal_line():
    """r484's boot table ends at the instant the capture ran, so nothing in
    this pipeline depends on a git-checkout mtime."""
    now, src = fl.capture_now(R484)
    assert src == "boot_table"
    assert now.startswith("2026-09-04T01:2")


def test_a_capture_with_no_sysstat_listing_is_unusable_not_empty(tmp_path):
    d = tmp_path / "nuc-capture-rW"
    d.mkdir()
    (d / "sar-all.txt").write_text("### SYSSTAT_FILES\ntotal 0\n### SAR_R\n")
    (d / "journal-boots.txt").write_text(
        "IDX BOOT ID                          FIRST ENTRY"
        "                 LAST ENTRY\n"
        "  0 0d0e3188da124a4b9f78b26dd95d3ea2 Thu 2026-08-10 09:37:16 UTC "
        "Wed 2026-08-12 09:00:00 UTC\n")
    got = fl.read_capture(str(d))
    assert got["ok"] is False and "no sa/sar day files" in got["reason"]


# --------------------------------------------------------------------------
# union semantics
# --------------------------------------------------------------------------

def test_two_captures_agreeing_produce_one_row_not_two(tmp_path):
    rows = [("sa10", 1000, "Aug 10 23:50"), ("sar10", 2000, "Aug 11 00:07")]
    a = cap(tmp_path, "nuc-capture-rA", rows, "Wed 2026-08-12 09:00:00")
    b = cap(tmp_path, "nuc-capture-rB", rows, "Wed 2026-08-12 10:00:00")
    rep = fl.build([a, b])
    assert rep["n_fire_days_union"] == 1
    assert rep["days"][0]["n_captures"] == 2
    assert rep["n_disagree"] == 0


def test_a_refusal_never_outvotes_a_verdict(tmp_path):
    """`fire_pending` is the module declining to answer. A capture taken
    before a fire settled must not drag a later capture's real verdict into a
    DISAGREE row."""
    early = cap(tmp_path, "nuc-capture-rA",
                [("sa10", 1000, "Aug 10 23:50"), ("sar10", 2000, "Aug 11 00:07"),
                 ("sa11", 1000, "Aug 11 23:50")], "Wed 2026-08-12 00:10:00")
    late = cap(tmp_path, "nuc-capture-rB",
               [("sa11", 1000, "Aug 11 23:50"), ("sar11", 2000, "Aug 12 00:07")],
               "Thu 2026-08-13 09:00:00")
    # rA reaches the 08-12 fire only 180 s after it, inside the settle window,
    # so it says `fire_pending` WITH a fire instant attached -- the only shape
    # in which a refusal can collide with a verdict at all. (Found by
    # mutation: `REFUSALS = ()` survived a fixture that produced no instant.)
    solo = fl.build([early])
    pend = [d for d in solo["days"] if d["fire_utc"] == "2026-08-12T00:07:00Z"]
    assert pend == [], "a refusal must not reach the union as a vote"
    rep = fl.build([early, late])
    assert rep["n_disagree"] == 0
    row = [d for d in rep["days"]
           if d["fire_utc"] == "2026-08-12T00:07:00Z"][0]
    assert row["verdict"] == "fire_ran"
    assert row["captures"] == ["nuc-capture-rB"]


def test_a_real_conflict_is_reported_and_not_reconciled(tmp_path):
    """A receipt cannot un-exist, so this can only mean an instrument or a
    capture is wrong -- which is exactly what must reach a human.

    Both fixtures carry a receipt: the schedule is DERIVED from receipts
    (round 448's rule, never hardcode 00:07), so a capture holding none at all
    yields no fire instants and cannot disagree with anything. See
    `test_a_capture_with_no_receipts_contributes_nothing_and_says_so`."""
    ran = cap(tmp_path, "nuc-capture-rA",
              [("sa10", 1000, "Aug 10 23:50"), ("sar10", 2000, "Aug 11 00:07")],
              "Wed 2026-08-12 09:00:00")
    missed = cap(tmp_path, "nuc-capture-rB",
                 [("sa10", 1000, "Aug 10 23:50"),
                  ("sa11", 1000, "Aug 11 23:50"),
                  ("sar11", 2000, "Aug 12 00:07")],
                 "Wed 2026-08-12 09:00:00")
    rep = fl.build([ran, missed])
    assert rep["n_disagree"] == 1
    row = rep["disagreements"][0]
    assert row["fire_utc"] == "2026-08-11T00:07:00Z"
    assert row["verdict"] == "DISAGREE"
    assert sorted(row["claims"]) == ["fire_missed", "fire_ran"]


def test_a_capture_with_no_receipts_contributes_nothing_and_says_so(tmp_path):
    """A capture taken deep in an outage can hold day files and no receipts.
    The schedule is derived from receipts, so there is nothing to score -- and
    the ledger must show that as `n_decidable: 0` on a capture it READ, not as
    a capture it silently dropped."""
    d = cap(tmp_path, "nuc-capture-rA",
            [("sa10", 1000, "Aug 10 23:50"), ("sa11", 1000, "Aug 11 23:50")],
            "Wed 2026-08-12 09:00:00")
    rep = fl.build([d])
    assert rep["n_captures_read"] == 1
    assert rep["captures"][0]["n_decidable"] == 0
    assert rep["n_fire_days_union"] == 0


def test_union_gain_is_measured_against_the_best_single_capture(tmp_path):
    """Round 478's A/B compared two captures and found neither was a superset.
    The number that matters is what the union adds over the best one alone."""
    old = cap(tmp_path, "nuc-capture-rA",
              [("sa10", 1000, "Aug 10 23:50"), ("sar10", 2000, "Aug 11 00:07"),
               ("sa11", 1000, "Aug 11 23:50"), ("sar11", 2000, "Aug 12 00:07")],
              "Thu 2026-08-13 09:00:00")
    new = cap(tmp_path, "nuc-capture-rB",
              [("sa12", 1000, "Aug 12 23:50"), ("sar12", 2000, "Aug 13 00:07")],
              "Fri 2026-08-14 09:00:00")
    rep = fl.build([old, new])
    assert rep["n_fire_days_union"] == 3
    assert rep["n_fire_days_best_single"] == 2
    assert rep["best_single_capture"] == "nuc-capture-rA"
    assert rep["union_gain"] == 1


def test_a_sole_source_fire_names_the_capture_holding_it(tmp_path):
    """The operational point of the whole module: delete that capture and the
    instant leaves the program."""
    old = cap(tmp_path, "nuc-capture-rA",
              [("sa10", 1000, "Aug 10 23:50"), ("sar10", 2000, "Aug 11 00:07")],
              "Thu 2026-08-13 09:00:00")
    new = cap(tmp_path, "nuc-capture-rB",
              [("sa12", 1000, "Aug 12 23:50"), ("sar12", 2000, "Aug 13 00:07")],
              "Fri 2026-08-14 09:00:00")
    rep = fl.build([old, new])
    assert rep["n_sole_source"] == 2
    assert rep["sole_source_by_capture"] == {
        "nuc-capture-rA": 1, "nuc-capture-rB": 1}


def test_an_orphan_scored_day_carries_its_evidence_into_the_union(tmp_path):
    """A day recovered from a receipt alone must be distinguishable in the
    ledger from one backed by a surviving day file."""
    d = cap(tmp_path, "nuc-capture-rA",
            [("sar09", 2000, "Aug 10 00:07"), ("sa10", 1000, "Aug 10 23:50"),
             ("sar10", 2000, "Aug 11 00:07")], "Wed 2026-08-12 09:00:00")
    rep = fl.build([d])
    row = [r for r in rep["days"]
           if r["fire_utc"] == "2026-08-10T00:07:00Z"][0]
    assert row["evidence"] == ["receipt_only"]


# --------------------------------------------------------------------------
# the durable ledger
# --------------------------------------------------------------------------

def test_append_is_idempotent(tmp_path):
    d = cap(tmp_path, "nuc-capture-rA",
            [("sa10", 1000, "Aug 10 23:50"), ("sar10", 2000, "Aug 11 00:07")],
            "Wed 2026-08-12 09:00:00")
    path = str(tmp_path / "led.jsonl")
    rep = fl.build([d])
    assert fl.append(rep, path)["n_appended"] == 1
    second = fl.append(rep, path)
    assert second["n_appended"] == 0 and second["n_unchanged"] == 1


def test_a_changed_verdict_is_appended_and_flagged_not_overwritten(tmp_path):
    """Append-only. A contradiction against history is the thing a reader must
    see; a writer does not get to silently fix it."""
    path = str(tmp_path / "led.jsonl")
    missed = cap(tmp_path, "nuc-capture-rA",
                 [("sa10", 1000, "Aug 10 23:50"),
                  ("sa11", 1000, "Aug 11 23:50"),
                  ("sar11", 2000, "Aug 12 00:07")],
                 "Wed 2026-08-12 09:00:00")
    assert fl.append(fl.build([missed]), path)["n_appended"] == 2
    ran = cap(tmp_path, "nuc-capture-rB",
              [("sa10", 1000, "Aug 10 23:50"), ("sar10", 2000, "Aug 11 00:07")],
              "Wed 2026-08-12 09:00:00")
    got = fl.append(fl.build([ran]), path)
    assert got["n_appended"] == 1
    assert got["contradictions"] == ["2026-08-11T00:07:00Z"]
    lines = [json.loads(x) for x in open(path) if x.strip()]
    assert len(lines) == 3, "the earlier record must survive"
    assert lines[-1]["contradicts_prior"] == "fire_missed"


def test_verify_reports_a_contradiction_it_finds_in_the_ledger(tmp_path):
    path = tmp_path / "led.jsonl"
    path.write_text(
        json.dumps({"fire_utc": "2026-08-11T00:07:00Z",
                    "verdict": "fire_missed"}) + "\n" +
        json.dumps({"fire_utc": "2026-08-11T00:07:00Z",
                    "verdict": "fire_ran"}) + "\n")
    rep = fl.verify(str(path))
    assert rep["n_conflicting_instants"] == 1
    assert rep["conflicting_instants"]["2026-08-11T00:07:00Z"] == [
        "fire_missed", "fire_ran"]


def test_verify_names_an_unparseable_line_rather_than_dropping_it(tmp_path):
    path = tmp_path / "led.jsonl"
    path.write_text('{"fire_utc": "x", "verdict": "fire_ran"}\nnot json\n')
    rep = fl.verify(str(path))
    assert rep["n_unparseable"] == 1 and rep["n_lines"] == 2


# --------------------------------------------------------------------------
# against the real captures in this repo
# --------------------------------------------------------------------------

def test_the_live_union_beats_every_single_capture():
    dirs = sorted(os.path.join(CAPTURES, n) for n in os.listdir(CAPTURES)
                  if n.startswith("nuc-capture-r"))
    rep = fl.build(dirs)
    assert rep["n_captures_read"] == 4
    # Round 490: this was pinned at `== 5` and went red the moment round 490
    # banked its own down-round capture, which carries a `tailscale status`
    # and nothing else. That is the corpus growing, not the ledger breaking,
    # and it will happen on EVERY down round -- so the unusable count is
    # derived from the directory listing and only the READ count, which is a
    # claim about the ledger, stays literal.
    assert rep["n_captures_unusable"] == len(dirs) - 4
    assert rep["n_fire_days_union"] == 11
    assert rep["n_fire_days_best_single"] == 10
    assert rep["best_single_capture"] == "nuc-capture-r478"


def test_the_live_captures_never_contradict_each_other():
    """Four captures of the same filesystem taken days apart. The underlying
    fact is immutable, so any DISAGREE row is an instrument defect."""
    rep = fl.build(sorted(
        os.path.join(CAPTURES, n) for n in os.listdir(CAPTURES)
        if n.startswith("nuc-capture-r")))
    assert rep["n_disagree"] == 0, rep["disagreements"]


def test_the_newest_capture_alone_would_lose_three_fires():
    """The reason the ledger exists. The 2026-09-04T00:07:18 sweep took
    sa23-sa26; a round reading only the newest capture sees 8 decidable fires
    where the union holds 11."""
    newest = fl.build([R484])
    union = fl.build(sorted(
        os.path.join(CAPTURES, n) for n in os.listdir(CAPTURES)
        if n.startswith("nuc-capture-r")))
    assert newest["n_fire_days_union"] == 8
    assert union["n_fire_days_union"] == 11
    lost = set(d["fire_utc"] for d in union["days"]) - set(
        d["fire_utc"] for d in newest["days"])
    assert lost == {"2026-08-24T00:07:00Z", "2026-08-25T00:07:00Z",
                    "2026-08-26T00:07:00Z"}


def test_the_committed_ledger_is_consistent_and_covers_the_union():
    rep = fl.verify(LIVE_LEDGER)
    assert rep["n_unparseable"] == 0
    assert rep["n_conflicting_instants"] == 0
    assert rep["n_instants"] == 11
    assert rep["counts"] == {"fire_ran": 8, "fire_missed": 3}


def test_cli_build_strict_exits_zero_on_the_real_captures():
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "nuc", "fossil_ledger.py"),
         "build", "--captures",
         os.path.join(CAPTURES, "nuc-capture-r*"), "--strict"],
        capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["n_disagree"] == 0


def test_cli_verify_strict_exits_zero_on_the_committed_ledger():
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "nuc", "fossil_ledger.py"),
         "verify", "--ledger", LIVE_LEDGER, "--strict"],
        capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------------
# The mutation ledger
# --------------------------------------------------------------------------

MUTATIONS = {
    "capture_now falls back to os.path.getmtime":
        "test_now_is_derived_from_the_boot_table_inside_the_capture",
    "a capture with no `now` is silently skipped instead of named":
        "test_a_capture_with_no_boot_table_and_no_declaration_is_unusable",
    "now_source label dropped":
        "test_a_declared_now_is_labelled_as_declared_not_derived",
    "an empty listing is treated as a capture with zero fires":
        "test_a_capture_with_no_sysstat_listing_is_unusable_not_empty",
    "a receipt-less capture reported as read with no `n_decidable`":
        "test_a_capture_with_no_receipts_contributes_nothing_and_says_so",
    "REFUSALS emptied, so fire_pending votes":
        "test_a_refusal_never_outvotes_a_verdict",
    "DISAGREE collapsed to the newest capture's verdict":
        "test_a_real_conflict_is_reported_and_not_reconciled",
    "union_gain measured against the OLDEST capture":
        "test_union_gain_is_measured_against_the_best_single_capture",
    "sole_source_by_capture hardcoded empty":
        "test_a_sole_source_fire_names_the_capture_holding_it",
    "evidence field dropped from union rows":
        "test_an_orphan_scored_day_carries_its_evidence_into_the_union",
    "append rewrites the ledger instead of appending":
        "test_a_changed_verdict_is_appended_and_flagged_not_overwritten",
    "append dedup key drops the verdict":
        "test_append_is_idempotent",
    "verify's set-of-verdicts check deleted":
        "test_verify_reports_a_contradiction_it_finds_in_the_ledger",
    "verify swallows a JSONDecodeError silently":
        "test_verify_names_an_unparseable_line_rather_than_dropping_it",
}


def test_mutation_list_is_honest():
    here = set(globals())
    missing = sorted(t for t in MUTATIONS.values() if t not in here)
    assert missing == [], f"MUTATIONS names tests that do not exist: {missing}"


def test_every_public_entry_point_is_covered_by_at_least_one_mutation():
    covered = " ".join(MUTATIONS)
    for fn in ("capture_now", "read_capture", "build", "append", "verify"):
        assert callable(getattr(fl, fn))
    for token in ("capture_now", "DISAGREE", "union_gain", "append", "verify"):
        assert token in covered

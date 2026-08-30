"""Re-auditing a recorded mutation report from its own evidence (swe.scoreaudit).

Round 353 (SWE-loop D), closing round 349's next-steps item 5. Round 349 fixed
`run_mutant`'s classifier (every non-zero exit code used to be a kill, so a
suite that never ran scored 100%) and left the historical question open:
"prior rounds' scores predate the defect so they are probably fine, but
'probably' is the honest word."

`Mutant.as_dict` has always stored the run's own output tail for every
non-survived mutant, so the question is answerable without re-running
anything. These tests pin the classifier against the shapes that actually
occur in this workspace's archived reports (`state/swe/*/mutation*.json`),
including the live corpus itself, so a change to the patterns has to face
10,046 real mutants.
"""
import glob
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swe.scoreaudit as SA

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARCHIVE = os.path.join(REPO, "state", "swe")


def _m(status, detail, **kw):
    d = {"id": kw.pop("id", "x.py:1:cmp#0"), "status": status, "detail": detail,
         "line": 1, "op": "cmp"}
    d.update(kw)
    return d


# ------------------------------------------------------------- classifier --

def test_exit_zero_is_never_re_examined():
    # `survived` means exit 0, which the pre-349 classifier and the post-349
    # one agree on exactly. There is nothing to audit and no detail stored.
    assert SA.classify_recorded(_m("survived", "")) == ("survived", "")


def test_a_pytest_failure_summary_is_evidence():
    for tail in ("1 failed, 37 passed in 0.52s",
                 "3 failed in 12.10s",
                 "1 failed, 613 passed in 148.47s (0:02:28)"):
        assert SA.classify_recorded(_m("killed", tail))[0] == "evidenced_kill", tail


def test_a_truncated_tail_is_still_evidence_via_the_FAILED_line():
    # `as_dict` truncates detail to 300 chars, which cuts some summary lines
    # mid-word. The `FAILED <nodeid>` line survives that cut more often, so
    # the whole detail is searched rather than just its last line.
    tail = ("FAILED tests/test_v06.py::test_single_input_reads_back_as_tuple\n"
            "!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failu")
    assert SA.classify_recorded(_m("killed", tail))[0] == "evidenced_kill"


def test_the_round_137_shape_is_not_evidence():
    # The exact bytes 260 of round 137's "kills" were recorded with.
    tail = ("no tests ran in 0.00s\n"
            "ERROR: file or directory not found: tests/test_timetravel_debugger.py")
    bucket, label = SA.classify_recorded(_m("killed", tail))
    assert bucket == "no_evidence_kill" and label == "no tests ran"


def test_no_evidence_wins_over_kill_evidence_in_the_same_tail():
    # Deliberate precedence: if the runner says it never collected anything,
    # a stray "failed" elsewhere in the tail cannot outvote it. The
    # alternative default is the flattering one, which is the whole defect.
    tail = "1 failed, 2 passed\nERROR: file or directory not found: tests/gone.py"
    assert SA.classify_recorded(_m("killed", tail))[0] == "no_evidence_kill"


def test_a_timeout_stays_a_kill_and_carries_no_pytest_tail():
    assert SA.classify_recorded(
        _m("timeout", "test run exceeded 240s (process group killed)"))[0] == "timeout"


def test_a_post_349_error_status_maps_to_no_evidence_but_keeps_its_origin():
    bucket, label = SA.classify_recorded(_m("error", "whatever"))
    assert bucket == "no_evidence_kill" and "post-349" in label


def test_an_unrecognised_tail_is_unknown_not_silently_either_side():
    bucket, label = SA.classify_recorded(_m("killed", "segmentation fault (core dumped)"))
    assert bucket == "unknown_kill"
    assert label == "segmentation fault (core dumped)"       # carried for triage


def test_an_empty_detail_is_unknown():
    assert SA.classify_recorded(_m("killed", ""))[0] == ("unknown_kill")


# ----------------------------------------------------------------- report --

def _report(rows):
    ms = [_m(s, d, id="x.py:%d:cmp#%d" % (i, i)) for i, (s, d) in enumerate(rows)]
    killed = sum(1 for s, _ in rows if s in ("killed", "timeout"))
    return {"total": len(ms), "killed": killed, "survived": len(ms) - killed,
            "score": round(killed / len(ms), 4), "mutants": ms}


def test_a_fully_evidenced_report_is_confirmed_and_its_score_stands():
    a = SA.audit(_report([("killed", "1 failed in 1s"),
                          ("killed", "2 failed in 1s"),
                          ("survived", "")]))
    assert a["confirmed"] is True
    assert a["audited_score"] == a["score_upper"] == a["published_score"] == 0.6667
    assert a["counts"]["evidenced_kill"] == 2 and a["counts"]["no_evidence_kill"] == 0
    assert "CONFIRMED" in SA.format_audit(a)


def test_an_unevidenced_report_becomes_an_interval_not_a_number():
    a = SA.audit(_report([("killed", "1 failed in 1s"),
                          ("killed", "no tests ran in 0.00s"),
                          ("killed", "no tests ran in 0.00s"),
                          ("survived", "")]))
    assert a["confirmed"] is False
    assert a["published_score"] == 0.75          # what the report claimed
    assert a["audited_score"] == 0.25            # only one kill is evidence
    assert a["score_upper"] == 0.75
    assert a["unaudited_kills"] == 2
    text = SA.format_audit(a)
    assert "NOT EVIDENCE" in text and "[0.25, 0.75]" in text


def test_timeouts_count_toward_the_audited_lower_bound():
    # A timeout is a real behavioural difference the runner caught, and
    # `MutationReport.killed` has always counted it; the audit must not
    # quietly demote it just because it has no pytest tail.
    a = SA.audit(_report([("timeout", "test run exceeded 240s"),
                          ("survived", "")]))
    assert a["audited_score"] == 0.5 and a["confirmed"] is True


def test_the_dominant_killer_is_reported_as_a_share():
    a = SA.audit(_report([("killed", "FAILED tests/t.py::test_a\n1 failed in 1s"),
                          ("killed", "FAILED tests/t.py::test_a\n1 failed in 1s"),
                          ("killed", "FAILED tests/t.py::test_b\n1 failed in 1s")]))
    assert a["dominant_killer"] == "tests/t.py::test_a"
    assert a["dominant_killer_share"] == pytest.approx(2 / 3, abs=1e-4)


def test_suspect_records_carry_enough_to_re_run_them():
    a = SA.audit(_report([("killed", "no tests ran in 0.00s")]))
    s = a["suspects"][0]
    assert s["id"] and s["line"] == 1 and s["op"] == "cmp" and s["label"] == "no tests ran"


def test_audit_paths_skips_files_that_are_not_mutation_reports(tmp_path):
    good = tmp_path / "mutation.json"
    good.write_text(json.dumps(_report([("killed", "1 failed in 1s")])))
    (tmp_path / "other.json").write_text(json.dumps({"hello": 1}))
    (tmp_path / "broken.json").write_text("{not json")
    out = SA.audit_paths([str(p) for p in sorted(tmp_path.iterdir())])
    assert [os.path.basename(a["path"]) for a in out] == ["mutation.json"]


def test_main_exit_code_is_nonzero_exactly_when_a_kill_lacks_evidence(tmp_path, capsys):
    clean = tmp_path / "a.json"
    clean.write_text(json.dumps(_report([("killed", "1 failed in 1s")])))
    dirty = tmp_path / "b.json"
    dirty.write_text(json.dumps(_report([("killed", "no tests ran in 0.00s")])))
    assert SA.main([str(clean)]) == 0
    assert SA.main([str(dirty)]) == 1
    assert "NOT EVIDENCE" in capsys.readouterr().out


# ------------------------------------------------------- the live archive --
#
# These run against the real `state/swe/` reports. They are the reason the
# classifier can be trusted: it is not tested only on shapes it was written
# for. If a future round adds a campaign whose tails do not classify, the
# first test below fails and the classifier gets extended DELIBERATELY
# rather than defaulting a real mutant into the flattering bucket.

def _archived_reports():
    return SA.audit_paths(sorted(glob.glob(os.path.join(ARCHIVE, "*", "*.json"))))


@pytest.mark.skipif(not os.path.isdir(ARCHIVE), reason="no archived campaigns")
def test_every_archived_mutant_classifies_into_a_known_bucket():
    audits = _archived_reports()
    assert audits, "expected archived mutation reports under state/swe/"
    unknown = {a["path"]: a["counts"]["unknown_kill"]
               for a in audits if a["counts"]["unknown_kill"]}
    assert unknown == {}, (
        "unclassifiable kill tails appeared -- extend swe.scoreaudit's pattern "
        "tables on the evidence rather than letting them default: %s" % unknown)


@pytest.mark.skipif(not os.path.isdir(ARCHIVE), reason="no archived campaigns")
def test_round_137_is_the_only_archived_campaign_with_unevidenced_kills():
    """The round-353 finding, pinned.

    Round 137's two reports record 260 mutants each (the same mutants, before
    and after the recheck stage) as `killed` on `no tests ran ... ERROR: file
    or directory not found: tests/test_timetravel_debugger.py` -- a coverage
    map naming a test file that had been renamed to `tests/test_timetravel.py`.
    pytest exit 4, zero tests run, counted as a kill by the pre-349 classifier.

    Its published "corrected score 1.0 (0 survived)" is therefore not a
    measurement of 1276 mutants; it is a measurement of 1016 with 260
    unknowns folded in on the flattering side.
    """
    audits = _archived_reports()
    dirty = sorted(os.path.basename(os.path.dirname(a["path"])) + "/" +
                   os.path.basename(a["path"])
                   for a in audits if not a["confirmed"])
    assert dirty == ["round-137/mutation-rechecked.json",
                     "round-137/mutation.json"]
    for a in audits:
        if "round-137" in a["path"]:
            assert a["counts"]["no_evidence_kill"] == 260
            assert a["labels"] == {"no tests ran": 260}
    rechecked = [a for a in audits if a["path"].endswith("mutation-rechecked.json")
                 and "round-137" in a["path"]][0]
    assert rechecked["published_score"] == 1.0
    assert rechecked["audited_score"] == 0.7962      # 1016 evidenced+timeout / 1276

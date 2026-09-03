"""Tests for harness/tierbudget.py and the measured tier it implements
(round 385, harness A).

The property under test is not "these files are fast" — that is a
measurement, and it goes stale, which is the whole reason this module
exists. It is the SHAPE of the rule: fail-closed by default, one-way
promotion, red is never promotable, and a registry that cannot be read
cannot take the suite down.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tierbudget  # noqa: E402

REPO_ROOT = tierbudget.REPO_ROOT


# --------------------------------------------------------------------------
# fail-closed
# --------------------------------------------------------------------------
def test_a_missing_registry_promotes_nothing(tmp_path):
    reg = tierbudget.load_registry(str(tmp_path / "nope.json"))
    assert reg["promoted"] == {}
    assert reg["_load_error"] is True
    assert tierbudget.is_slow("test_swe_anything.py", reg) is True


@pytest.mark.parametrize("blob", [
    "{not json at all",
    "[]",
    '{"promoted": ["test_swe_x.py"]}',      # right key, wrong type
    '{"cap_s": 25.0}',                      # no promoted key
])
def test_a_malformed_registry_promotes_nothing_and_never_raises(tmp_path, blob):
    p = tmp_path / "tier-budget.json"
    p.write_text(blob)
    reg = tierbudget.load_registry(str(p))
    assert reg["promoted"] == {}
    assert reg["_load_error"] is True


def test_an_unlisted_swe_file_is_slow_with_no_edit_anywhere():
    """Round 235's self-maintenance property, kept: a NEW test_swe_*.py file
    tiers itself slow, and no registry edit is needed to make that happen."""
    reg = {"promoted": {"test_swe_oracles.py": {"measured_s": 5.0}}}
    assert tierbudget.is_slow("test_swe_brand_new_file.py", reg) is True
    assert tierbudget.is_slow("test_swe_oracles.py", reg) is False


def test_the_registry_can_never_demote_a_core_harness_file():
    """The asymmetry that makes the list safe. A registry entry naming a
    non-test_swe_ file is inert, not a demotion."""
    reg = {"promoted": {"test_agent.py": {"measured_s": 900.0}}}
    assert tierbudget.is_slow("test_agent.py", reg) is False
    assert tierbudget.is_slow("test_driver_health.py", reg) is False


# --------------------------------------------------------------------------
# the ladder
# --------------------------------------------------------------------------
def _runner_for(table):
    def runner(path, cap_s):
        return dict(table[os.path.basename(path)])
    return runner


def test_measure_classifies_the_four_outcomes():
    table = {
        "test_swe_a.py": {"seconds": 1.2, "returncode": 0,
                          "stdout": "6 passed in 1.10s", "timed_out": False},
        "test_swe_b.py": {"seconds": 25.0, "returncode": None,
                          "stdout": "", "timed_out": True},
        "test_swe_c.py": {"seconds": 3.0, "returncode": 1,
                          "stdout": "2 failed, 65 passed in 2.9s", "timed_out": False},
        "test_swe_d.py": {"seconds": 0.4, "returncode": 4,
                          "stdout": "no tests ran", "timed_out": False},
    }
    rows = tierbudget.measure(files=sorted(table), cap_s=25.0,
                              tests_dir="/nowhere", runner=_runner_for(table))
    got = {r["file"]: r["outcome"] for r in rows}
    assert got == {
        "test_swe_a.py": "passed",
        "test_swe_b.py": "over_cap",
        "test_swe_c.py": "failed",
        "test_swe_d.py": "error",
    }
    assert [r["counts"] for r in rows][2] == {"failed": 2, "passed": 65}


def test_over_cap_is_a_lower_bound_not_a_failure():
    """Round 341 rule 1 in another key: absence of a number is recorded as
    absence. `over_cap` says "at least cap_s", which is all a promotion
    decision needs, and it must not be confused with a red file."""
    table = {"test_swe_b.py": {"seconds": 25.0, "returncode": None,
                               "stdout": "", "timed_out": True}}
    rows = tierbudget.measure(files=["test_swe_b.py"], cap_s=25.0,
                              tests_dir="/nowhere", runner=_runner_for(table))
    assert rows[0]["outcome"] == "over_cap"
    assert rows[0]["outcome"] != "failed"
    assert tierbudget.promotable(rows, 25.0) == []


def test_a_red_file_is_never_promotable_however_cheap_it_is():
    table = {"test_swe_c.py": {"seconds": 0.2, "returncode": 1,
                               "stdout": "1 failed, 3 passed in 0.2s",
                               "timed_out": False}}
    rows = tierbudget.measure(files=["test_swe_c.py"], cap_s=25.0,
                              tests_dir="/nowhere", runner=_runner_for(table))
    assert rows[0]["seconds"] < 25.0
    assert tierbudget.promotable(rows, 25.0) == []


def test_swe_files_finds_the_real_tree():
    names = tierbudget.swe_files()
    assert names, "no test_swe_*.py found"
    assert all(n.startswith("test_swe_") and n.endswith(".py") for n in names)
    assert names == sorted(names)


# --------------------------------------------------------------------------
# the free self-check
# --------------------------------------------------------------------------
def test_the_drift_floor_stops_a_sub_second_file_alarming_on_noise():
    reg = {"promoted": {"test_swe_triage.py": {"measured_s": 0.4}},
           "drift_factor": 2.0, "drift_floor_s": 3.0}
    assert tierbudget.budget_for("test_swe_triage.py", reg) == pytest.approx(3.4)
    assert not tierbudget.verify({"test_swe_triage.py": 1.5}, reg)["drifted"]
    assert tierbudget.verify({"test_swe_triage.py": 4.0}, reg)["drifted"]


def test_drift_is_the_factor_when_the_file_is_big_enough_for_it_to_bite():
    reg = {"promoted": {"test_swe_mutation.py": {"measured_s": 17.0}},
           "drift_factor": 2.0, "drift_floor_s": 3.0}
    assert tierbudget.budget_for("test_swe_mutation.py", reg) == pytest.approx(34.0)
    assert not tierbudget.verify({"test_swe_mutation.py": 30.0}, reg)["drifted"]
    assert tierbudget.verify({"test_swe_mutation.py": 40.0}, reg)["drifted"]


def test_a_promoted_file_that_did_not_run_is_not_evidence():
    """A `-k` selection or a `--collect-only` leaves a promoted file with no
    duration. That is not a pass and not a drift — it is silence."""
    reg = {"promoted": {"a.py": {"measured_s": 1.0}, "b.py": {"measured_s": 1.0}},
           "drift_factor": 2.0, "drift_floor_s": 3.0}
    result = tierbudget.verify({"a.py": 1.0}, reg)
    assert result["n_promoted"] == 2 and result["n_observed"] == 1
    assert result["drifted"] == []


def test_the_verify_line_is_not_pytest_shaped():
    """`driver_health.split_measured_output` looks for a pytest terminal-count
    line to find the measured/echoed boundary when no sentinel is present.
    This line must not look like one, in any of its branches."""
    import re
    sys.path.insert(0, os.path.join(REPO_ROOT, "harness"))
    from harness import driver_health

    reg = {"promoted": {"test_swe_oracles.py": {"measured_s": 5.0}},
           "drift_factor": 2.0, "drift_floor_s": 3.0}
    lines = [
        tierbudget.format_verify_line(tierbudget.verify({}, {"promoted": {}, "_load_error": True})),
        tierbudget.format_verify_line(tierbudget.verify({}, {"promoted": {}})),
        tierbudget.format_verify_line(tierbudget.verify({}, reg)),
        tierbudget.format_verify_line(tierbudget.verify({"test_swe_oracles.py": 5.5}, reg)),
        tierbudget.format_verify_line(tierbudget.verify({"test_swe_oracles.py": 99.0}, reg)),
    ]
    for line in lines:
        assert line.startswith("tier-budget:")
        assert not (driver_health._SUMMARY_COUNT_RE.search(line)
                    and re.search(r"\bin \d", line)), line
        assert not driver_health._FAILED_LINE_RE.match(line), line


def test_the_drift_branch_names_the_file_and_the_remedy():
    reg = {"promoted": {"test_swe_oracles.py": {"measured_s": 5.0}},
           "drift_factor": 2.0, "drift_floor_s": 3.0}
    line = tierbudget.format_verify_line(
        tierbudget.verify({"test_swe_oracles.py": 99.0}, reg))
    assert "DRIFT" in line
    assert "test_swe_oracles.py" in line
    assert "tierbudget.py measure" in line


# --------------------------------------------------------------------------
# the real registry, against the real tree
# --------------------------------------------------------------------------
def test_every_promoted_entry_names_a_file_that_exists():
    reg = tierbudget.load_registry()
    present = set(tierbudget.swe_files())
    missing = sorted(set(reg["promoted"]) - present)
    assert not missing, "registry promotes deleted file(s): %s" % missing


def test_every_promoted_entry_records_how_and_when_it_was_measured():
    """A promotion is an assertion that somebody measured something. An entry
    with no number and no round is a preference, and preferences rot silently
    — this repo's own round 383 item 4."""
    reg = tierbudget.load_registry()
    for name, entry in reg["promoted"].items():
        assert isinstance(entry.get("measured_s"), (int, float)), name
        assert entry["measured_s"] < reg["cap_s"], name
        assert isinstance(entry.get("measured_round"), int), name
        assert entry.get("why"), name


def test_the_registry_only_promotes_files_the_filename_rule_would_have_slowed():
    reg = tierbudget.load_registry()
    for name in reg["promoted"]:
        assert name.startswith(tierbudget.SLOW_PREFIX), name


# --------------------------------------------------------------------------
# the ordering pin — a real pytest run, because it is about pytest's own
# output order and nothing smaller can prove it
# --------------------------------------------------------------------------
def test_the_tier_budget_line_is_printed_above_pytests_count_line(tmp_path):
    """Load-bearing: `classify_health_log` quotes the LAST line of a health
    log's measured half into `driver.log`. If this hook printed after the
    count line, every future round's `health-check PASS (...)` parenthetical
    would read `tier-budget: ...` instead of the test result — round 379's
    bug, re-introduced by its own fix's neighbour.

    ROUND 473 (SWE-loop D) REPAIRED THIS TEST, which had asserted nothing at
    all since round 385 wrote it. It ran `test_tiering.py -k
    nothing_matches_this`: nothing in that file is PROMOTED, so
    `_DURATIONS` never gains a promoted entry, `verify()` returns
    `n_observed == 0`, `pytest_terminal_summary` returns before writing —
    and the old body's `if tier:` guard was therefore False on every run.
    The command produced ZERO `tier-budget:` lines in the live tree, so the
    test named after the line's PRESENCE never once checked it was there.
    Found by `harness/swe/falsifiers.py`: it was one of three nodes in this
    file that never went red for any of 93 mutants of `tierbudget.py`.

    Two changes: run a file the registry actually promotes (so the hook
    fires), and require the line rather than skipping when it is absent.
    """
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "harness/tests/test_swe_loop.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=180,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    tier = [i for i, ln in enumerate(lines) if ln.startswith("tier-budget:")]
    counts = [i for i, ln in enumerate(lines)
              if "deselected" in ln or " passed" in ln or " no tests ran" in ln]
    assert tier, ("no tier-budget line at all — the hook did not fire, and a "
                  "silent hook is the failure this test exists to catch:\n"
                  + out.stdout)
    assert counts, out.stdout
    assert max(tier) < max(counts), out.stdout


def test_a_broken_registry_does_not_break_collection(tmp_path):
    """Round 348's outage, pre-empted. A garbage registry must degrade to
    round 235's rule, not abort the suite."""
    real = tierbudget.REGISTRY_PATH
    backup = tmp_path / "backup.json"
    with open(real) as fh:
        backup.write_text(fh.read())
    try:
        with open(real, "w") as fh:
            fh.write("{ this is not json")
        out = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q",
             "-p", "no:cacheprovider", "-m", "not swe_slow", "harness/tests/"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=180,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        assert out.returncode == 0, out.stdout + out.stderr
        node_ids = [ln for ln in out.stdout.splitlines()
                    if ln.startswith("harness/tests/") and "::" in ln]
        assert node_ids, out.stdout
        # degraded all the way back to round 235: NOTHING test_swe_ is fast
        assert not any("/test_swe_" in n for n in node_ids), out.stdout
    finally:
        with open(real, "w") as fh:
            fh.write(backup.read_text())


# ---------------------------------- killers, generated by round 473's audit --
#
# `python3 harness/swe/falsifiers.py audit --subject harness/tierbudget.py
#  --tests harness/tests/test_tierbudget.py` scored this file at 48.4%
# (45 of 93 mutants killed). 33 of the 48 survivors are the CLI half
# (`_cmd_measure` 12/12, `_cmd_status` 11/11, `_default_runner` 6/6, `main`
# 3/3, `_cmd_verify` 1/1) — code that shells out to pytest and is deliberately
# not unit-tested, so the module's headline score is mostly a statement about
# its CLI. Over the non-CLI functions the score is 45/60 = 75%. The five tests
# below close the survivors in that 75% that are real missing assertions;
# each names the mutant it kills.

def test_a_file_exactly_AT_its_budget_has_not_drifted():
    """Kills `tierbudget.py:261:cmp` (`Gt -> GtE` in `"drifted": seconds >
    budget`). Every drift fixture above is either far under or far over, so
    the boundary itself was unasserted — and `>=` would put a file that came
    in exactly on budget into the DRIFT branch the driver prints."""
    reg = {"promoted": {"test_swe_oracles.py": {"measured_s": 5.0}},
           "drift_factor": 2.0, "drift_floor_s": 3.0}
    assert tierbudget.budget_for("test_swe_oracles.py", reg) == pytest.approx(10.0)
    at = tierbudget.verify({"test_swe_oracles.py": 10.0}, reg)
    assert at["rows"][0]["drifted"] is False and at["drifted"] == []
    over = tierbudget.verify({"test_swe_oracles.py": 10.01}, reg)
    assert over["rows"][0]["drifted"] is True


def test_a_file_exactly_AT_the_cap_is_not_promotable():
    """Kills `tierbudget.py:237:cmp` (`Lt -> LtE` in `promotable`). The
    registry's own bar is "MEASURED UNDER `cap_s`"; `<=` would promote a file
    measured exactly at it, and the cap is the policy."""
    table = {"test_swe_at.py": {"seconds": 25.0, "returncode": 0,
                                "stdout": "3 passed in 25.0s", "timed_out": False},
             "test_swe_under.py": {"seconds": 24.99, "returncode": 0,
                                   "stdout": "3 passed in 24.99s", "timed_out": False}}
    rows = tierbudget.measure(files=sorted(table), cap_s=25.0,
                              tests_dir="/nowhere", runner=_runner_for(table))
    assert [r["outcome"] for r in rows] == ["passed", "passed"]
    assert [r["file"] for r in tierbudget.promotable(rows, 25.0)] == ["test_swe_under.py"]


def test_the_no_evidence_line_substitutes_the_count_it_names():
    """Kills `tierbudget.py:292:arith` (`Mod -> Mult` on the `%` that renders
    the no-evidence branch). `test_the_verify_line_is_not_pytest_shaped`
    already RENDERS this branch, but asserts only on the line's SHAPE — so
    `"...%d..." * 1`, which leaves the placeholder unsubstituted, passed it."""
    reg = {"promoted": {"a.py": {"measured_s": 1.0}, "b.py": {"measured_s": 1.0}},
           "drift_factor": 2.0, "drift_floor_s": 3.0}
    line = tierbudget.format_verify_line(tierbudget.verify({}, reg))
    assert "2 promoted, none ran here" in line
    assert "%d" not in line


def test_the_worst_file_is_the_worst_BY_RATIO_not_by_wall_clock():
    """Kills `tierbudget.py:294:arith` (`Div -> Mult` in the `worst` key).
    Every fixture above has exactly ONE observed file, and `max` over one row
    is the same row whatever the key computes."""
    reg = {"promoted": {"slow.py": {"measured_s": 50.0},
                        "tight.py": {"measured_s": 1.0}},
           "drift_factor": 2.0, "drift_floor_s": 3.0}
    # slow.py is far bigger in seconds; tight.py is far closer to its budget.
    line = tierbudget.format_verify_line(
        tierbudget.verify({"slow.py": 60.0, "tight.py": 3.9}, reg))
    assert "worst tight.py" in line, line


def test_only_a_non_passing_row_keeps_its_output_tail():
    """Kills `tierbudget.py:221:ifneg` and `:221:cmp` (`if outcome !=
    "passed"`). Round 385 added the tail because a red ladder row said only
    `1 failed`; nothing asserted which rows get one, so negating the
    condition — keeping the tail for passes and dropping it for failures,
    the exact inversion of the point — changed no test."""
    table = {"test_swe_ok.py": {"seconds": 1.0, "returncode": 0,
                                "stdout": "4 passed in 1.0s", "timed_out": False},
             "test_swe_red.py": {"seconds": 1.0, "returncode": 1,
                                 "stdout": "boom\n1 failed, 3 passed in 1.0s",
                                 "timed_out": False}}
    rows = {r["file"]: r for r in
            tierbudget.measure(files=sorted(table), cap_s=25.0,
                               tests_dir="/nowhere", runner=_runner_for(table))}
    assert "tail" not in rows["test_swe_ok.py"]
    assert "1 failed, 3 passed" in rows["test_swe_red.py"]["tail"]

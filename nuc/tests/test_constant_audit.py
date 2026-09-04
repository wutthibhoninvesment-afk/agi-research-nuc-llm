"""Round 382 tests for `nuc/constant_audit.py`.

The tool grades the PROVENANCE of size constants, discharging round 376's
next-steps item 5 ("sweep the repo for other constants on the wrong side of a
transform"). Its only real validation is that it fires on the one instance of
that bug this program has actually seen, so that case is pinned first and from
the real historical source rather than from a hand-written imitation.
"""
import inspect
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

NUC = Path(__file__).resolve().parents[1]
REPO = NUC.parent
sys.path.insert(0, str(NUC))

import constant_audit as ca  # noqa: E402


# The round-376 defect, verbatim in shape: an opaque literal whose comment
# gives an at-rest provenance, assigned to a field DECLARED as live allocation.
HISTORICAL = '''
GB = 1_000_000_000


class MoeGeometry:
    name: str
    expert_bytes: int          # bytes per cached expert slot (weights + scales)
    dense_bytes: int           # resident dense weights (after load)


# Qwen3.6-35B-A3B int4 gs64 container on pgain-nuc (read from the shard headers):
#   expert = 1,572,864 B U8 merged + 196,608 B F32 scales; 40 layers x 256 experts.
QWEN36 = MoeGeometry(name="qwen36", expert_bytes=1_572_864 + 196_608,
                     dense_bytes=int(9.25 * GB))
'''

FIXED = '''
GB = 1_000_000_000
INTER, HIDDEN = 512, 2048


class MoeGeometry:
    name: str
    expert_bytes: int          # bytes per cached expert slot (weights + scales)
    dense_bytes: int           # resident dense weights (after load)


# slot_ensure_allocated mallocs 3*inter*hidden int8
SLOT_WEIGHT_BYTES = 3 * INTER * HIDDEN
QWEN36 = MoeGeometry(name="qwen36", expert_bytes=SLOT_WEIGHT_BYTES,
                     dense_bytes=int(9.25 * GB))
'''


def _by_name(findings, name):
    return [f for f in findings if f["name"] == name]


def test_it_fires_on_the_round_376_defect():
    out = ca.audit_source(HISTORICAL, "hist.py")
    expert = _by_name(out, "expert_bytes")[0]
    assert expert["grade"] == "bare"
    assert expert["transform_risk"] is True
    assert "cached expert slot" in expert["declared_as"]


def test_neither_half_of_the_signal_fires_alone():
    """The pair is the defect. A bare constant with an at-rest comment and no
    allocation-side declaration is just a disk size; an allocation-side field
    with no at-rest comment is just undocumented."""
    no_decl = HISTORICAL.replace(
        "    expert_bytes: int          # bytes per cached expert slot (weights + scales)\n",
        "    expert_bytes: int\n")
    assert _by_name(ca.audit_source(no_decl, "x.py"), "expert_bytes")[0][
        "transform_risk"] is False

    no_provenance = HISTORICAL.replace(
        "# Qwen3.6-35B-A3B int4 gs64 container on pgain-nuc (read from the shard headers):\n"
        "#   expert = 1,572,864 B U8 merged + 196,608 B F32 scales; 40 layers x 256 experts.\n",
        "")
    assert _by_name(ca.audit_source(no_provenance, "x.py"), "expert_bytes")[0][
        "transform_risk"] is False


def test_deriving_the_constant_clears_the_risk():
    out = ca.audit_source(FIXED, "fixed.py")
    expert = _by_name(out, "expert_bytes")[0]
    assert expert["grade"] == "derived" and expert["transform_risk"] is False
    # the derivation itself is graded too, and is the target state
    assert _by_name(out, "SLOT_WEIGHT_BYTES")[0]["grade"] == "derived"


def test_a_unit_scale_is_not_provenance():
    """`int(9.25 * GB)` is one reading in a unit. Neither `GB` nor the `int()`
    call makes it derived -- an early version of this tool graded it `derived`
    because `int` is an `ast.Name`."""
    out = ca.audit_source(FIXED, "x.py")
    assert _by_name(out, "dense_bytes")[0]["grade"] == "bare"
    assert ca.grade_expression(ca.ast.parse("int(9.25 * GB)", mode="eval").body) == "bare"
    assert ca.grade_expression(ca.ast.parse("round(x / MB)", mode="eval").body) == "derived"


def test_an_all_names_expression_is_still_a_constant():
    """ROUND 382 BUG. `_numeric` originally required a numeric literal, so
    `SLOT_BYTES = WEIGHT_BYTES + SCALE_BYTES` -- no literal at all, and the
    tool's own recommended shape -- was silently dropped from the report. An
    audit blind to the grade it recommends always shows progress."""
    src = "A_BYTES = 1\nB_BYTES = 2\nC_BYTES = A_BYTES + B_BYTES\n"
    names = [f["name"] for f in ca.audit_source(src, "x.py")]
    assert names == ["A_BYTES", "B_BYTES", "C_BYTES"]


def test_a_disk_named_constant_is_graded_disk_not_flagged():
    """Naming the side is the cheapest fix, so it must not read as a defect."""
    src = ("# du -sb /work/models/qwen36_i4_gs64\n"
           "NUC_MODEL_DISK_BYTES = 23_031_269_773\n")
    f = ca.audit_source(src, "x.py")[0]
    assert f["grade"] == "disk" and f["transform_risk"] is False


def test_function_locals_and_sentinels_are_not_constants():
    """Both were noise in the first run: a rate computed inside a function and
    a dataclass field default of 0."""
    src = ("class G:\n"
           "    fixed_bytes: int = 0\n"
           "def f(nvme_mb_s, MB):\n"
           "    per_byte_s = 1.0 / (nvme_mb_s * MB)\n"
           "    size = int(nvme_mb_s)\n"
           "    return per_byte_s, size\n")
    assert ca.audit_source(src, "x.py") == []


def test_non_numeric_and_string_valued_names_are_skipped():
    src = ('BYTES_LABEL = "size"\nSIZES = [1, 2, 3]\nSIZE_MAP = {"a": 1}\n')
    assert ca.audit_source(src, "x.py") == []


def test_summarize_counts_grades_and_risk():
    s = ca.summarize(ca.audit_source(HISTORICAL, "h.py"))
    assert s["by_grade"] == {"bare": 2} and s["transform_risk"] == 1
    assert s["derived_fraction"] == 0.0
    s2 = ca.summarize(ca.audit_source(FIXED, "f.py"))
    assert s2["transform_risk"] == 0 and s2["derived_fraction"] > 0
    assert ca.summarize([])["derived_fraction"] == 0.0


def test_vendored_trees_are_skipped(tmp_path):
    """`nuc/fast_lane/colibri-c/` and `nuc/kv_reuse/upstream/` are copies of
    someone else's source; grading them would bury this repo's own constants."""
    (tmp_path / "kv_reuse" / "upstream").mkdir(parents=True)
    (tmp_path / "kv_reuse" / "upstream" / "m.py").write_text("A_BYTES = 1\n")
    (tmp_path / "mine.py").write_text("B_BYTES = 2\n")
    names = [f["name"] for f in ca.audit_paths([str(tmp_path)])]
    assert names == ["B_BYTES"]


def test_tests_are_excluded_unless_asked_for(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("EXPECTED_BYTES = 40_960\n")
    (tmp_path / "m.py").write_text("A_BYTES = 1\n")
    assert [f["name"] for f in ca.audit_paths([str(tmp_path)])] == ["A_BYTES"]
    with_tests = [f["name"] for f in ca.audit_paths([str(tmp_path)], include_tests=True)]
    assert set(with_tests) == {"A_BYTES", "EXPECTED_BYTES"}


# --- the live tree ---------------------------------------------------------

def test_the_live_nuc_tree_has_no_transform_risk():
    """The round-382 sweep's actual result. This is an invariant, not a
    snapshot: a NEW bare constant whose comment cites an at-rest provenance and
    whose field means live allocation is a FINDING, and this test is where it
    surfaces."""
    findings = ca.audit_paths([str(NUC), str(REPO / "harness")])
    risky = [f for f in findings if f["transform_risk"]]
    assert risky == [], risky
    assert len(findings) >= 15


def test_cli_exits_2_on_risk_and_0_when_clean(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text(HISTORICAL)
    r = subprocess.run([sys.executable, str(NUC / "constant_audit.py"), "audit",
                        str(bad), "--json"], capture_output=True, text=True)
    assert r.returncode == 2
    data = json.loads(r.stdout)
    assert data["summary"]["transform_risk"] == 1

    good = tmp_path / "good.py"
    good.write_text(FIXED)
    r2 = subprocess.run([sys.executable, str(NUC / "constant_audit.py"), "audit",
                         str(good)], capture_output=True, text=True)
    assert r2.returncode == 0
    assert "TRANSFORM RISK" not in r2.stdout


def test_cli_grade_filter(tmp_path):
    f = tmp_path / "m.py"
    f.write_text(FIXED)
    r = subprocess.run([sys.executable, str(NUC / "constant_audit.py"), "audit",
                        str(f), "--grade", "derived", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["findings"] and all(x["grade"] == "derived" for x in data["findings"])


# ------------------------------------------------ round 388: the fast check
#
# `nuc/run_checks_fast.sh` is the fourth per-round health check. Its whole
# value is the FAIL path, which is the path nobody exercises: a check that
# dies before printing why is worse than no check, because the driver logs its
# last line either way.

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "nuc" / "run_checks_fast.sh"


def test_the_fast_check_exists_and_is_executable():
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_the_fast_check_is_syntactically_valid_bash():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True,
                   capture_output=True, text=True)


def test_the_fast_check_declares_its_offline_contract():
    body = SCRIPT.read_text()
    # the reason it is safe to run every round from any track
    assert "OFFLINE" in body
    assert "8001" in body           # the one port that must never be contacted
    assert "Diagnostic-only" in body


def _audit_summary_rc(payload: str) -> tuple[int, str]:
    """Run the exact python fragment the script pipes its audit JSON into."""
    body = SCRIPT.read_text()
    start = body.index("import json, sys")
    end = body.index("raise SystemExit(1 if s[", start)
    frag = body[start:end] + 'raise SystemExit(1 if s["transform_risk"] else 0)\n'
    proc = subprocess.run([sys.executable, "-c", textwrap.dedent(frag)],
                          input=payload, capture_output=True, text=True)
    return proc.returncode, proc.stdout


def test_the_fast_check_reports_fail_on_a_transform_risk():
    rc, out = _audit_summary_rc(json.dumps({"summary": {
        "n": 19, "by_grade": {"derived": 14, "bare": 4, "disk": 1},
        "derived_fraction": 0.737, "transform_risk": 2}}))
    assert rc == 1                       # FAIL...
    assert "transform-risk" in out       # ...and it said so before failing


def test_the_fast_check_passes_on_bare_constants_alone():
    """Four bare constants are a deliberate steady state, not a failure."""
    rc, out = _audit_summary_rc(json.dumps({"summary": {
        "n": 19, "by_grade": {"derived": 14, "bare": 4, "disk": 1},
        "derived_fraction": 0.737, "transform_risk": 0}}))
    assert rc == 0
    assert "4 bare" in out


def test_the_fast_check_fails_loudly_on_unparseable_audit_output():
    rc, out = _audit_summary_rc("not json at all")
    assert rc == 2
    assert "PARSE-ERROR" in out


# --------------------------------------------------- round 496: the budget
#
# THE RED. `test_the_fast_check_runs_green_on_this_tree` was red for nine
# rounds (487-495) and for two earlier one-round episodes (483, 485). It never
# failed an assertion. All eleven failures are the same line:
#
#   subprocess.TimeoutExpired: Command '['bash', '.../run_checks_fast.sh']'
#   timed out after 600 seconds        # Popen returncode -9, i.e. SIGKILL
#
# `timeout=600` was a bare literal, written by round 388 and unchanged since
# (`git log -S` finds exactly one commit, 1bd242e). Round 388 measured the
# whole script at 65.6 s for 490 tests, so the budget had ~20x headroom and
# looked like a generous round number rather than a number about anything.
#
# It is not a number about anything, and that is the defect. What it budgets
# is a whole run of `nuc/tests/` -- the suite this test is a MEMBER of -- and
# that run happens under the driver's four concurrent health checks on a box
# whose `nproc` is 1. So the budget is spent by two things neither of which
# this file controls: every test any round adds, and every suite the driver
# runs beside it. Round 493 (harness A) measured the second and left the
# arithmetic in `state/harness/round-493/nuc-fastcheck-solo.json` rather than
# type a bigger constant at the end of a harness round, because `nuc/tests/`
# is NUC-integration(E)'s tree. This is that handoff, taken.
#
# The budget is now the product round 487 established for the same shape in
# `skills/skill-authoring/scripts/corpus_check.py`, and each of its three
# factors is re-derivable from something OUTSIDE this file, so a change to any
# of them expires the constant instead of silently invalidating it:
#
#   solo wall  x  driver concurrency  x  margin
#
# `TestDerivedBudget` below is what makes that true rather than merely stated.
FAST_CHECK_SOLO_MEASUREMENT = REPO / "state" / "nuc" / "round-496" / "fast-check-solo.json"

#: Wall seconds for ONE nested leg, measured on this box -- see the receipt.
FAST_CHECK_SOLO_S = 5.684

#: `run_driver.sh` backgrounds this many health suites at once. Counted, not
#: believed: `test_the_concurrency_is_read_off_the_driver` re-counts it.
DRIVER_CONCURRENT_SUITES = 4

#: Round 487's margin, kept deliberately: a budget with no slack becomes a
#: flake, and a flake in a health check is worse than a slow one.
BUDGET_MARGIN = 1.5

FAST_CHECK_TIMEOUT_S = int(math.ceil(
    FAST_CHECK_SOLO_S * DRIVER_CONCURRENT_SUITES * BUDGET_MARGIN))

# --------------------------------------------------- round 496: the narrowing
#
# THE SECOND HALF, and the budget alone would not have been a fix. Raising the
# ceiling leaves the cost: the nested leg re-runs all of `nuc/tests/`, so the
# nuc health check runs this suite TWICE every round. That is round 388's
# explicit design ("the pytest leg runs twice ... the alternative is an
# unexercised FAIL path"), and it was cheap when a leg was 30 s. It is not
# cheap now, and the second run establishes nothing about the tree that the
# outer run has not already established -- it is the same tests, same
# interpreter, same commit, a few minutes apart.
#
# What the nested run IS for is the SCRIPT: interpreter resolution, the pytest
# leg, the audit leg, the summary fragment, the three strict instruments, the
# verdict line. Every one of those runs regardless of which tests the pytest
# leg selects. So the leg is narrowed to the tests that are ABOUT the script,
# which keeps the end-to-end path intact and drops the duplicated suite.
#
# This is not a new liberty. Round 442 made exactly this trade one file over:
# `test_run_checks_interpreter.py` passes `--collect-only -q` to every script
# invocation, "which reaches the real interpreter-resolution and audit code
# and costs ~1.2 s instead of the ~86 s a full run costs". The selector here
# is a step stronger -- it RUNS tests rather than only collecting them.
#
# `not strict_instrument` keeps the nested run from re-entering
# `test_the_fast_check_reports_every_strict_instrument_exit_code`, which
# spawns the script a third time.
NESTED_SELECT = "fast_check and not strict_instrument"


@pytest.mark.skipif(
    shutil.which("bash") is None or os.environ.get("NUC_FAST_CHECK_NESTED") == "1",
    reason="no bash, or already inside the check this test invokes")
def test_the_fast_check_runs_green_on_this_tree():
    """End-to-end, including the pytest leg — with a recursion guard.

    The script's first act is to run `nuc/tests/`, which contains this test.
    Without `NUC_FAST_CHECK_NESTED` the run would re-enter itself forever; the
    env var is set for the child only, so the outer run still exercises every
    other line of the script.

    Round 496: the pytest leg is narrowed to `NESTED_SELECT` and the budget is
    derived rather than typed — see the two blocks above. What this node
    asserts is unchanged in kind: the script, run the way the driver runs it,
    exits 0 and says PASS. What it no longer does is re-run the whole suite
    the outer process is already running."""
    env = dict(os.environ, NUC_FAST_CHECK_NESTED="1")
    proc = subprocess.run(["bash", str(SCRIPT), "-k", NESTED_SELECT],
                          cwd=REPO, env=env, capture_output=True, text=True,
                          timeout=FAST_CHECK_TIMEOUT_S)
    assert proc.returncode == 0, proc.stdout[-3000:]
    assert "nuc-checks PASS" in proc.stdout
    assert "constant-audit" in proc.stdout
    # FAIL-CLOSED. `-k` that matches nothing makes pytest exit 5, which the
    # script reports as FAIL -- so a rename upstream could not turn this into
    # a green no-op. It could still, however, turn it into a confusing red;
    # this says which of the two happened, on the line.
    assert re.search(r"^\d+ passed", proc.stdout, re.M), proc.stdout[-3000:]


def test_the_nested_leg_is_narrowed_and_not_the_whole_suite():
    """The narrowing is the fix, so it is pinned. If a later round drops the
    selector the node goes back to costing a full suite run and the nine-round
    red comes back -- silently, because it would still be GREEN until the
    suite grows or the box gets busier."""
    sig = inspect.getsource(test_the_fast_check_runs_green_on_this_tree)
    assert '"-k", NESTED_SELECT' in sig
    assert "timeout=FAST_CHECK_TIMEOUT_S" in sig
    assert "600" not in sig


def test_the_narrowed_selector_actually_selects_this_modules_script_tests():
    """`-k` is a substring match over node ids, so the selector's meaning
    lives in the test NAMES. Two things are checked, and the second is the one
    that matters: what pytest ITSELF selects, not what this file thinks the
    selector means. A round-496 mutant that dropped `not strict_instrument`
    survived the name-based half alone.

    Collect-only, so it costs ~1.3 s and cannot recurse."""
    names = [n for n in globals() if n.startswith("test_") and "fast_check" in n]
    assert len(names) >= 7, names
    spawners = [n for n in names if "strict_instrument" in n]
    assert len(spawners) == 1, spawners

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--collect-only",
         str(NUC / "tests"), "-k", NESTED_SELECT],
        cwd=str(REPO), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-2000:]
    collected = [l.strip() for l in proc.stdout.splitlines() if "::" in l]

    # THE POINT OF `not strict_instrument`: the one test that itself spawns
    # the script must not be inside the run the script is doing.
    assert not [c for c in collected if spawners[0] in c], collected

    # ...and the selector must still reach the end-to-end node, or the nested
    # run would be exercising nothing this file cares about.
    assert [c for c in collected
            if "test_the_fast_check_runs_green_on_this_tree" in c], collected
    # a real subset, not the whole suite creeping back in
    assert 6 <= len(collected) <= 20, len(collected)


@pytest.mark.skipif(
    shutil.which("bash") is None or os.environ.get("NUC_FAST_CHECK_NESTED") == "1",
    reason="no bash, or already inside the check this test invokes")
def test_the_fast_check_reports_fail_when_its_pytest_leg_fails():
    """Round 388 built the nested run because "a check that dies before
    printing why is worse than no check", and then only ever exercised the
    GREEN end-to-end path: the two FAIL-path tests above drive the summary
    FRAGMENT, not the script. This drives the whole script down its pytest-leg
    FAIL path, which nothing did for 108 rounds.

    `-k` matching no test is pytest's EXIT_NOTESTSCOLLECTED (5) -- a non-zero
    leg, which is all the script's branch cares about, and it costs a
    collection instead of a suite."""
    env = dict(os.environ, NUC_FAST_CHECK_NESTED="1")
    proc = subprocess.run(
        ["bash", str(SCRIPT), "-k", "r496_no_test_has_this_name"],
        cwd=REPO, env=env, capture_output=True, text=True,
        timeout=FAST_CHECK_TIMEOUT_S)
    assert proc.returncode == 1, proc.stdout[-3000:]
    assert "nuc-checks FAIL (pytest rc=5," in proc.stdout, proc.stdout[-3000:]
    # it still got PAST the dead leg and printed the audit -- the whole point
    assert "constant-audit" in proc.stdout


class TestDerivedBudget:
    """Round 496, after round 487's `TestDerivedBudget` in
    `skills/skill-authoring/scripts/test_corpus_check.py`.

    The budget is a product of three factors and every one of them is read
    back from its source here, so the constant expires when a factor moves
    instead of quietly becoming wrong."""

    def test_the_budget_is_the_product_and_not_a_typed_number(self):
        assert FAST_CHECK_TIMEOUT_S == int(math.ceil(
            FAST_CHECK_SOLO_S * DRIVER_CONCURRENT_SUITES * BUDGET_MARGIN))

    def test_the_solo_cost_is_read_off_the_measurement_on_disk(self):
        # The constant is a MEASUREMENT with a receipt, not a belief. Re-time
        # the leg and rewrite the receipt; the constant follows or this reds.
        m = json.loads(FAST_CHECK_SOLO_MEASUREMENT.read_text())
        assert m["solo_wall_s"] == FAST_CHECK_SOLO_S
        assert m["nproc"] == 1

    def test_the_concurrency_is_read_off_the_driver(self):
        # THE EXPIRY. A fifth background suite in run_driver.sh makes the
        # projection wrong, and this is what says so.
        driver = (REPO / "run_driver.sh").read_text()
        n = len(re.findall(r"^\s*\w+_PID=\$!\s*$", driver, re.M))
        assert n == DRIVER_CONCURRENT_SUITES, (
            "run_driver.sh backgrounds %d suites, the budget assumes %d"
            % (n, DRIVER_CONCURRENT_SUITES))

    def test_the_budget_clears_the_measured_contended_cost(self):
        # The receipt records what this leg actually cost with FOUR copies of
        # it running at once -- round 496 reproduced the driver's own
        # concurrency directly rather than inferring it from the health logs.
        # The budget must clear that with room, or this is round 388's
        # constant again with a different number on it.
        m = json.loads(FAST_CHECK_SOLO_MEASUREMENT.read_text())
        assert FAST_CHECK_TIMEOUT_S >= 2 * m["observed_contended_leg_s"], (
            "budget %s s leaves less than 2x headroom over the %s s this leg "
            "actually cost under four concurrent copies on this box"
            % (FAST_CHECK_TIMEOUT_S, m["observed_contended_leg_s"]))


# ------------------------------------- round 460: the strict-instrument line

def test_the_fast_check_reports_every_strict_instrument_exit_code():
    """`reachability_check.py` ships three `--strict` modes whose whole point
    is to exit non-zero, and until round 460 nothing ran them -- they ran when
    an E round remembered, i.e. every sixth round at best. `lastseen-drift
    --strict` had been exiting 1 since round 448 and no round file said so.

    Nested-guarded so this does not re-enter the pytest leg."""
    env = dict(os.environ, NUC_FAST_CHECK_NESTED="1")
    out = subprocess.run(["bash", str(SCRIPT), "--co", "-q"], cwd=str(REPO),
                         capture_output=True, text=True, env=env).stdout
    line = [l for l in out.splitlines() if l.startswith("nuc-instruments ")]
    assert len(line) == 1, out[-2000:]
    for name in ("coverage=", "precision-audit=", "lastseen-drift="):
        assert name in line[0]
    assert "diagnostic only" in line[0]
    # it must come BEFORE the line driver_health.py parses, so a reader sees
    # the codes next to the verdict rather than after it. Anchored on the
    # VERDICT line, not on the `nuc-checks ` prefix: `nuc-checks interpreter:`
    # shares that prefix and sits at index 0, which is how the first cut of
    # this assertion managed to compare a real offset against zero.
    assert out.index("nuc-instruments ") < out.index("nuc-checks PASS")


def test_the_strict_line_does_not_change_the_parsed_verdict_line():
    """`harness/driver_health.py` parses `nuc-checks ... (pytest rc=N, audit
    rc=N)`. Round 460 deliberately did NOT widen that contract -- it is
    harness(A)'s artifact, the same handoff this file's header makes twice."""
    body = SCRIPT.read_text()
    assert 'nuc-checks $([ $rc -eq 0 ] && echo PASS || echo FAIL) ' \
           '(pytest rc=$pytest_rc, audit rc=$audit_rc)' in body
    verdict_echo = body[body.index('echo "nuc-checks $([ $rc -eq 0 ]'):]
    assert "_drift" not in verdict_echo
    assert "_cov" not in verdict_echo and "_prec" not in verdict_echo

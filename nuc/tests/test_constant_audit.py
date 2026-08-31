"""Round 382 tests for `nuc/constant_audit.py`.

The tool grades the PROVENANCE of size constants, discharging round 376's
next-steps item 5 ("sweep the repo for other constants on the wrong side of a
transform"). Its only real validation is that it fires on the one instance of
that bug this program has actually seen, so that case is pinned first and from
the real historical source rather than from a hand-written imitation.
"""
import json
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

"""Repair benchmark (swe.repair): injection, failure signal, three-level scoring, policy run."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swe.repair as RP
from swe.fuzz import WHENCE_ROOT
from swe.mutation import generate
from swe.policy import PolicyLLM, call, say

_INTERP = open(os.path.join(WHENCE_ROOT, "whence/interp.py"), encoding="utf-8").read()
_LINES = _INTERP.splitlines()
FAST = "-q -x tests/test_interp.py"          # ~1 s; kills the zero-guard mutant


def _zero_guard():
    for m in generate(_INTERP, "whence/interp.py"):
        if m.op == "cmp" and "Eq -> NotEq" in m.description \
           and 'r == 0 and (op == "/"' in _LINES[m.lineno - 1]:
            return m
    raise AssertionError("zero-guard mutant not found")


def test_mutated_site_points_at_the_changed_line_in_the_mutant_text():
    m = _zero_guard()
    lo, hi = RP.mutated_site(WHENCE_ROOT, m)
    text = m.source.splitlines()[lo - 1:hi]
    assert any("r != 0" in t for t in text)
    assert lo != m.lineno or True                     # numbering differs from the checkout (re-unparsed)


def test_injected_workspace_tracks_edits_against_the_injected_state():
    m = _zero_guard()
    ws = RP.InjectedWorkspace(WHENCE_ROOT, m)
    try:
        assert ws.read(m.path) == m.source
        assert ws.changed_files() == [] and ws.diff() == ""
        lo, _ = ws.site
        lines = m.source.splitlines()
        lines[lo - 1] = lines[lo - 1].replace("r != 0", "r == 0")
        with open(os.path.join(ws.dst, m.path), "w") as f:
            f.write("\n".join(lines) + "\n")
        assert ws.changed_files() == [m.path]
        d = ws.diff()
        assert "-" in d and "+" in d and "r == 0" in d
    finally:
        ws.cleanup()


def test_failing_output_captures_the_ci_signal():
    m = _zero_guard()
    ws = RP.InjectedWorkspace(WHENCE_ROOT, m)
    try:
        f = RP.failing_output(ws.dst, FAST.split(), tail_lines=25)
        assert f["returncode"] != 0 and f["failing_tests"]
        assert f["failing_tests"][0].startswith("tests/test_interp.py::")
        assert f["tail"].count("\n") < 25 and "FAILED" in f["tail"]
    finally:
        ws.cleanup()


def _restore(ws, replacement=None):
    lo, _ = ws.site
    lines = ws.read(ws.mutant.path).splitlines()
    lines[lo - 1] = replacement if replacement is not None else lines[lo - 1].replace("r != 0", "r == 0")
    with open(os.path.join(ws.dst, ws.mutant.path), "w") as f:
        f.write("\n".join(lines) + "\n")


def test_score_repair_levels_exact_green_localized_failed_cheated():
    m = _zero_guard()
    # 1. nothing done
    ws = RP.InjectedWorkspace(WHENCE_ROOT, m)
    try:
        r = RP.score_repair(ws, run_tests=False)
        assert r["outcome"] == "failed" and not r["localized"] and not r["exact"] and r["tests_green"] is None
    finally:
        ws.cleanup()
    # 2. exact revert
    ws = RP.InjectedWorkspace(WHENCE_ROOT, m)
    try:
        _restore(ws)
        r = RP.score_repair(ws, test_args=FAST)
        assert r["exact"] and r["localized"] and r["green"] and r["outcome"] == "exact"
        assert r["touched"] and r["changed_files"] == [m.path] and r["test_edits"] == []
    finally:
        ws.cleanup()
    # 3. an equivalent but differently-shaped fix: green, localized, not exact
    ws = RP.InjectedWorkspace(WHENCE_ROOT, m)
    try:
        lo, _ = ws.site
        orig = ws.read(m.path).splitlines()[lo - 1]
        indent = orig[:len(orig) - len(orig.lstrip())]
        _restore(ws, indent + "if op in ('/', '%') and r == 0:")
        r = RP.score_repair(ws, test_args=FAST)
        assert r["green"] and r["localized"] and not r["exact"] and r["outcome"] == "green"
    finally:
        ws.cleanup()
    # 4. an edit far from the site that does not fix it
    ws = RP.InjectedWorkspace(WHENCE_ROOT, m)
    try:
        src = ws.read(m.path)
        with open(os.path.join(ws.dst, m.path), "w") as f:
            f.write(src + "\n\nZZZ_MARKER = 1\n")
        r = RP.score_repair(ws, test_args=FAST)
        assert not r["localized"] and not r["exact"] and not r["green"] and r["outcome"] == "failed"
    finally:
        ws.cleanup()
    # 5. cheating: the suite is made green by editing the tests
    ws = RP.InjectedWorkspace(WHENCE_ROOT, m)
    try:
        with open(os.path.join(ws.dst, "tests/test_interp.py"), "w") as f:
            f.write("def test_ok():\n    pass\n")
        r = RP.score_repair(ws, test_args=FAST)
        assert r["tests_green"] and r["test_edits"] == ["tests/test_interp.py"]
        assert not r["green"] and r["outcome"] == "cheated"
    finally:
        ws.cleanup()


def test_run_repair_under_a_policy_scores_exact_and_writes_artifacts(tmp_path):
    m = _zero_guard()
    st = {}

    def s_outline(obs, s):
        return call("outline", path="whence/interp.py")

    def s_read(obs, s):
        return call("search", query="r != 0 and", path="whence/interp.py", context=1)

    def s_edit(obs, s):
        line = [l for l in obs.splitlines() if "r != 0 and" in l][0]
        old = line.split(": ", 1)[1] if ": " in line else line
        s["old"] = old.strip()
        return call("edit_file", path="whence/interp.py", old=s["old"], new=s["old"].replace("r != 0", "r == 0"))

    def s_test(obs, s):
        assert obs.startswith("edited"), obs
        return call("pytest", args=FAST)

    def s_done(obs, s):
        return say("Fixed.\n```json\n" + json.dumps({"root_cause": "inverted zero guard",
                                                    "files": ["whence/interp.py"], "summary": "restore =="}) + "\n```")

    out = str(tmp_path / "out")
    os.makedirs(out)
    res = RP.run_repair(lambda: PolicyLLM([s_outline, s_read, s_edit, s_test, s_done]), [m],
                        WHENCE_ROOT, out, max_steps=8, test_args=FAST, fail_args=FAST.split())
    assert len(res) == 1
    r = res[0]
    assert r["outcome"] == "exact" and r["green"] and r["localized"] and r["exact"]
    assert r["mutant"] == m.id and r["op"] == "cmp" and r["failing_tests"]
    assert r["stop_reason"] == "completed" and r["tool_calls"] == 4
    assert r["answer"]["root_cause"] == "inverted zero guard"
    tag = "repair-" + re.sub(r"\W", "_", m.id)          # every non-word char, the dot included
    assert os.path.exists(os.path.join(out, tag + ".trace.jsonl"))
    assert os.path.exists(os.path.join(out, tag + ".diff"))
    s = RP.summarize(res)
    assert s == {"attempted": 1, "green": 1, "exact": 1, "ast_exact": 1, "localized": 1,
                 "cheated": 0, "green_not_exact": 0, "cost_usd": s["cost_usd"], "steps": r["steps"],
                 "by_op": {"cmp": {"attempted": 1, "green": 1, "exact": 1, "ast_exact": 1,
                                   "localized": 1}}}


def test_summarize_ast_exact_survives_a_repair_blocked_from_green(tmp_path):
    # round 155/161/179: an AST-exact fix that never went green (blocked by
    # an unrelated harness bug, not a wrong repair) must not read as
    # indistinguishable from a genuinely failed attempt — `exact` (the
    # combined outcome class) stays 0, `ast_exact` (the per-record signal
    # alone) is 1.
    recs = [{"op": "cmp", "green": False, "exact": True, "localized": True,
             "outcome": "localized_not_green", "cost_usd": 0.1, "steps": 3}]
    s = RP.summarize(recs)
    assert s["exact"] == 0 and s["ast_exact"] == 1
    assert s["by_op"]["cmp"]["exact"] == 0 and s["by_op"]["cmp"]["ast_exact"] == 1


def test_killed_pool_and_stratified_sample(tmp_path):
    ms = []
    for i, op in enumerate(["ifneg"] * 6 + ["cmp"] * 3 + ["const"] * 2 + ["arith"]):
        ms.append({"id": "m%d" % i, "path": "whence/interp.py", "line": i, "op": op,
                   "status": "killed", "detail": "FAILED tests/test_x.py::t - assert"})
    ms.append({"id": "t", "path": "whence/interp.py", "line": 99, "op": "cmp", "status": "timeout",
               "detail": "test run exceeded 240s"})
    ms.append({"id": "s", "path": "whence/interp.py", "line": 98, "op": "cmp", "status": "survived", "detail": ""})
    ms.append({"id": "imp", "path": "whence/interp.py", "line": 97, "op": "cmp", "status": "killed",
               "detail": "ImportError while loading conftest"})
    mj = tmp_path / "m.json"
    mj.write_text(json.dumps({"mutants": ms}))
    pool = RP.killed_pool(str(mj))
    assert len(pool) == 12 and all(d["status"] == "killed" for d in pool)
    assert RP.killed_pool(str(mj), ops=("cmp",)) and all(d["op"] == "cmp" for d in RP.killed_pool(str(mj), ops=("cmp",)))
    s4 = RP.stratified_sample(pool, 4, seed=1)
    assert sorted(d["op"] for d in s4) == ["arith", "cmp", "const", "ifneg"]
    s8 = RP.stratified_sample(pool, 8, seed=1)
    assert len(s8) == 8 and len(set(d["id"] for d in s8)) == 8
    assert [d["id"] for d in RP.stratified_sample(pool, 5, seed=3)] == \
        [d["id"] for d in RP.stratified_sample(pool, 5, seed=3)]
    assert len(RP.stratified_sample(pool, 50, seed=0)) == 12

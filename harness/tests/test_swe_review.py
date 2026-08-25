"""Oracle-gated review / kill / fix tasks (swe.review), offline under PolicyLLM."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swe.review as R
import swe.killers as K
from swe.fuzz import WHENCE_ROOT
from swe.mutation import generate
from swe.policy import PolicyLLM, call, say
from agentloop import Agent, AgentConfig

HUGE = "let huge = fold(fn(a, x) { a * 2 }, 1, range(1100))\n"


# ------------------------------------------------------------ extract_json --

def test_extract_json_prefers_last_fenced_block_then_balanced_braces():
    t = 'x\n```json\n{"a": 1}\n```\nmore\n```json\n{"a": 2}\n```\n'
    assert R.extract_json(t) == {"a": 2}
    assert R.extract_json('done {"verdict": "killed", "n": {"k": [1]}} tail') == \
        {"verdict": "killed", "n": {"k": [1]}}
    assert R.extract_json("no json here {oops") is None
    assert R.extract_json("") is None


# ------------------------------------------------------------- OracleTool --

def test_oracle_tool_reports_every_oracle_and_fired_list():
    t = R.OracleTool(WHENCE_ROOT)
    r = t.run("let a = 1 + 1\nprint(a)\n")
    d = json.loads(r.output)
    assert r.ok and d["_fired"] == []
    assert set(d) == {"totality", "fast_slow", "direct", "determinism", "render", "_fired"}
    assert all(d[k]["kind"] == "ok" for k in ("totality", "fast_slow", "direct", "determinism", "render"))
    d2 = json.loads(t.run("let a = (\n", oracles="totality,fast_slow").output)
    assert set(d2) == {"totality", "fast_slow", "_fired"}
    assert d2["fast_slow"]["kind"] == "parse_error"


def test_oracle_tool_fires_on_a_synthetic_crash():
    from tests.synthetic_crash import install as install_crash, CRASH_PROGRAM
    t = R.OracleTool(WHENCE_ROOT)
    install_crash(t.pkg()["name"] + ".interp", WHENCE_ROOT)
    d = json.loads(t.run(CRASH_PROGRAM, oracles="fast_slow").output)
    assert d["_fired"] == ["fast_slow"] and d["fast_slow"]["kind"] == "crash"
    assert d["fast_slow"]["signature"][0] == "crash"


# --------------------------------------------------------------- review --

def test_score_review_confirms_only_claims_whose_oracle_fires():
    from tests.synthetic_crash import install as install_crash, CRASH_PROGRAM
    t = R.OracleTool(WHENCE_ROOT)
    install_crash(t.pkg()["name"] + ".interp", WHENCE_ROOT)
    answer = "Findings below.\n```json\n" + json.dumps({"claims": [
        {"title": "crash", "program": CRASH_PROGRAM, "oracle": "totality"},
        {"title": "phantom", "program": "print(1)\n", "oracle": "fast_slow"},
        {"title": "junk"},
    ]}) + "\n```"
    claims = R.score_review(answer, t)
    assert [c["confirmed"] for c in claims] == [True, False, False]
    assert claims[0]["fired"] and claims[0]["claimed_matches"] is True
    assert claims[2]["error"] == "no program"
    assert R.score_review("no json", t) == []


def test_review_task_runs_end_to_end_under_a_policy():
    registry, prompt = R.review_task(WHENCE_ROOT, ("whence/interp.py",), focus="binop")
    assert "Focus: binop" in prompt and "oracle_check" in prompt
    steps = [
        lambda obs, st: call("search", pattern="def binop", path="whence"),
        lambda obs, st: call("oracle_check", source="let a = 1 / 0\n"),
        lambda obs, st: say('```json\n{"claims": []}\n```'),
    ]
    r = Agent(PolicyLLM(steps), registry, config=AgentConfig(max_steps=6)).run(prompt)
    assert r.ok and r.tool_calls == 2
    assert R.score_review(r.final_text, registry.get("oracle_check")) == []


# ----------------------------------------------------------------- kill --

_INTERP_LINES = open(os.path.join(WHENCE_ROOT, "whence/interp.py"), encoding="utf-8").read().splitlines()


def _mutant(pred):
    for m in generate("\n".join(_INTERP_LINES) + "\n", "whence/interp.py"):
        if pred(m):
            return m
    raise AssertionError("no such mutant")


def _zero_guard_mutant():
    """`r == 0 and (op == "/" ...)` -> `r != 0`: every non-zero `%` becomes a miss."""
    return _mutant(lambda m: m.op == "cmp" and "Eq -> NotEq" in m.description
                   and 'r == 0 and (op == "/"' in _INTERP_LINES[m.lineno - 1])


def test_mutant_diff_tool_and_score_kill_on_a_real_mutant():
    # `modulo by zero` guard: `r == 0` -> `r != 0` makes every non-zero modulo a miss
    m = _zero_guard_mutant()
    tool = R.MutantDiffTool(WHENCE_ROOT, m)
    try:
        d = json.loads(tool.run("let a = 7 % 3\nprint(a)\n").output)
        assert d["differs"] is True and d["original"]["out"] == ["1"]
        assert d["mutant"]["out"] != ["1"]
        same = json.loads(tool.run('let s = "x" + "y"\n').output)
        assert same["differs"] is False
        rec = R.score_kill('```json\n{"verdict": "killed", "program": "let a = 7 % 3\\nprint(a)\\n"}\n```', tool)
        assert rec["outcome"] == "killed" and rec["killed"] and rec["minimized"]
        assert rec["expected"]["kind"] == "ok"
        rec2 = R.score_kill('{"verdict": "equivalent", "program": null, "argument": "never reached"}', tool)
        assert rec2["outcome"] == "equivalent_claimed" and not rec2["killed"]
        rec3 = R.score_kill('{"verdict": "killed", "program": "let s = 1\\n"}', tool)
        assert rec3["outcome"] == "failed"
    finally:
        tool.cleanup()
        assert not os.path.exists(tool.tmp)


def test_run_kill_pins_a_test_and_reports_cost(tmp_path):
    m = _zero_guard_mutant()
    prog = "let a = 7 % 3\nprint(a)\n"
    steps = [
        lambda obs, st: call("mutant_diff", source=prog),
        lambda obs, st: say('```json\n' + json.dumps({"verdict": "killed", "program": prog}) + '\n```'),
    ]
    test_file = str(tmp_path / "test_model_killers.py")
    res = R.run_kill(lambda: PolicyLLM(list(steps)), [m], WHENCE_ROOT, str(tmp_path),
                     max_steps=5, test_file=test_file)
    assert len(res) == 1 and res[0]["outcome"] == "killed"
    assert res[0]["mutant_diff_calls"] == 1 and res[0]["steps"] == 2
    import re
    assert "cost_usd" in res[0]
    assert os.path.exists(str(tmp_path / ("kill-" + re.sub(r"\W", "_", res[0]["mutant"]) + ".trace.jsonl")))
    body = open(test_file).read()
    assert "def test" in body and "%" in body      # program may have been shrunk
    compile(body, test_file, "exec")


def test_kill_prompt_shows_the_mutant_diff():
    m = _mutant(lambda m: m.op == "ifneg")
    registry, prompt, tool = R.kill_task(WHENCE_ROOT, m)
    try:
        assert "```diff" in prompt and "-" in prompt and m.id in prompt
        # round 29 swapped ReadFileTool/SearchTool for the region tools
        # (outline + windowed read_file + file-scoped search)
        assert set(registry.names()) == {"mutant_diff", "whence_run", "outline", "read_file", "search"}
    finally:
        tool.cleanup()


# ------------------------------------------------------------------ fix --

def test_edit_file_tool_requires_unique_non_empty_match(tmp_path):
    (tmp_path / "f.py").write_text("a = 1\nb = 1\n")
    t = R.EditFileTool(str(tmp_path))
    assert not t.run("f.py", "", "x").ok
    assert not t.run("f.py", "= 1", "= 2").ok            # two occurrences
    assert not t.run("../etc", "a", "b").ok
    assert not t.run("missing.py", "a", "b").ok
    r = t.run("f.py", "a = 1", "a = 2")
    assert r.ok and "line 1" in r.output
    assert (tmp_path / "f.py").read_text() == "a = 2\nb = 1\n" and len(t.edits) == 1


def test_fix_task_is_sandboxed_to_a_copy_and_scored_by_oracle_and_tests():
    finding = {"program": HUGE + "print(huge / 3)\n", "oracle": "totality",
               "detail": "OverflowError"}
    registry, prompt, ws = R.fix_task(finding, WHENCE_ROOT)
    try:
        assert ws.dst != WHENCE_ROOT and os.path.isfile(os.path.join(ws.dst, "whence/interp.py"))
        assert ws.changed_files() == [] and ws.diff() == ""
        # a "fix" that only adds a comment: files changed, oracle already silent
        # (the real checkout is fixed), tests skipped -> counted as fixed
        r = registry.get("edit_file").run("whence/interp.py", "import gc\n", "import gc  # touched\n")
        assert r.ok
        assert ws.changed_files() == ["whence/interp.py"]
        assert "+import gc  # touched" in ws.diff()
        rec = R.score_fix(ws, finding, run_tests=False)
        assert rec["oracle_silent"] is True and rec["fixed"] is True
        # sabotage: make the copy crash on the reproducer -> not fixed
        r = registry.get("edit_file").run(
            "whence/interp.py", "                except OverflowError:\n                    # unbounded",
            "                except ZeroDivisionError:\n                    # unbounded")
        assert r.ok
        rec = R.score_fix(ws, finding, run_tests=False)
        assert rec["oracle_silent"] is False and rec["fixed"] is False
        assert rec["oracle_after"]["totality"] == "crash"
        # the real checkout is untouched
        real = open(os.path.join(WHENCE_ROOT, "whence/interp.py")).read()
        assert "# touched" not in real and "except OverflowError" in real
    finally:
        ws.cleanup()


def test_run_fix_end_to_end_under_a_policy(tmp_path):
    finding = {"program": "let a = 1\nprint(a)\n", "oracle": "totality", "detail": "(synthetic)"}
    steps = [
        lambda obs, st: call("oracle_check", source=finding["program"]),
        lambda obs, st: call("edit_file", path="whence/interp.py", old="import gc\n", new="import gc  # r11\n"),
        lambda obs, st: say('```json\n{"root_cause": "none", "files": ["whence/interp.py"], "summary": "noop"}\n```'),
    ]
    rec = R.run_fix(lambda: PolicyLLM(list(steps)), finding, WHENCE_ROOT, str(tmp_path),
                    max_steps=6, run_tests=False)
    assert rec["fixed"] is True and rec["changed_files"] == ["whence/interp.py"]
    assert rec["answer"]["summary"] == "noop" and rec["tool_calls"] == 2
    assert os.path.exists(str(tmp_path / "fix.diff"))


# --------------------------------------------------------------- CLI ----

def test_cli_oracle_and_mutant_diff_modes(tmp_path, capsys):
    src = tmp_path / "p.lang"
    src.write_text("let a = 7 % 3\nprint(a)\n")
    assert R.main(["oracle", "--source-file", str(src)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["_fired"] == []
    # a mutation report with one survivor
    m = _zero_guard_mutant()
    mj = tmp_path / "mutation.json"
    mj.write_text(json.dumps({"mutants": [dict(m.as_dict(), status="survived")]}))
    assert R.main(["mutant-diff", "--mutation-json", str(mj), "--mutant-id", m.id,
                   "--source-file", str(src)]) == 0
    assert json.loads(capsys.readouterr().out)["differs"] is True
    assert R.main(["score-kill", "--mutation-json", str(mj), "--mutant-id", m.id,
                   "--source-file", str(src)]) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "killed"

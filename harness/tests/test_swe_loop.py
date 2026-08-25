"""PolicyLLM + swe tools driven by the real Agent loop (small, offline)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentloop import Agent, AgentConfig, ToolRegistry, TraceLogger
from agentloop.llm import text_turn
from swe.policy import PolicyLLM, call, say, swe_plan
from swe.tools import WhenceRunTool, PytestTool
from swe.fuzz import WHENCE_ROOT


def test_policy_steps_see_last_observation_and_state():
    seen = []

    def s1(obs, st):
        seen.append(obs)
        st["n"] = 1
        return call("whence_run", source="let a = 1 + 1\n")

    def s2(obs, st):
        seen.append(obs)
        return None                     # skipped step

    def s3(obs, st):
        return say("done n=%d ok=%s" % (st["n"], st["last_ok"]))

    agent = Agent(PolicyLLM([s1, s2, s3]), ToolRegistry([WhenceRunTool(WHENCE_ROOT)]),
                  config=AgentConfig(max_steps=5))
    r = agent.run("go")
    assert r.ok and r.final_text == "done n=1 ok=True"
    assert seen[0] is None and '"a": "2"' in seen[1]


def test_policy_exhaustion_ends_run():
    agent = Agent(PolicyLLM([]), ToolRegistry([]), config=AgentConfig(max_steps=3))
    r = agent.run("go")
    assert r.ok and "exhausted" in r.final_text


def test_whence_run_tool_reports_crash_as_failure():
    from tests.synthetic_crash import install as install_crash, CRASH_PROGRAM
    import swe.killers as K
    t = WhenceRunTool(WHENCE_ROOT)
    r = t.run(source="let p = " + "(" * 400 + "1" + ")" * 400 + "\n")
    assert r.ok and '"ParseError"' in r.output      # whence v0.4: not a crash
    t._pkg = K.load_whence(WHENCE_ROOT, "tool_crashy")
    install_crash("whence_tool_crashy.interp", WHENCE_ROOT)
    r = t.run(source=CRASH_PROGRAM)
    assert not r.ok and '"crash"' in r.output


def test_swe_plan_shape():
    steps = swe_plan("whence/interp.py", "tests/t.py")
    assert len(steps) == 7
    first = steps[0](None, {})
    assert first.tool_calls[0].name == "pytest"
    st = {}
    steps[1]("baseline", st)
    assert st["baseline"] == "baseline"
    # a clean mutation report skips the kill step
    st = {}
    assert steps[2]("fuzz", st).tool_calls[0].name == "oracle_fuzz" and st["fuzz"] == "fuzz"
    assert steps[3]("oracle", st).tool_calls[0].name == "mutate" and st["oracle"] == "oracle"
    assert steps[4]("mutation: ...\n  cmp    killed  10  survived   0", st) is None and st["skip_kill"]

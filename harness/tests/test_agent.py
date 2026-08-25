import os
import shutil
import tempfile
import unittest

from agentloop import (
    Agent,
    AgentConfig,
    AssistantTurn,
    BashTool,
    FlakyLLM,
    MockLLM,
    ReadFileTool,
    RetryPolicy,
    Scratchpad,
    ScratchpadTool,
    ToolCall,
    ToolRegistry,
    TraceLogger,
    WriteFileTool,
)
from agentloop.llm import FatalLLMError, text_turn, tool_turn


def make_workspace(testcase):
    root = tempfile.mkdtemp(prefix="agentloop-agent-")
    testcase.addCleanup(shutil.rmtree, root, ignore_errors=True)
    return root


def make_registry(root, extra=None):
    reg = ToolRegistry([ReadFileTool(root), WriteFileTool(root), BashTool(root)])
    for t in extra or []:
        reg.register(t)
    return reg


def make_agent(llm, registry, **kw):
    kw.setdefault("sleep", lambda s: None)
    kw.setdefault("rng", lambda: 0.5)
    return Agent(llm, registry, **kw)


class AgentLoopTests(unittest.TestCase):
    def test_end_to_end_write_then_verify_then_answer(self):
        """Scripted agent writes a file, cats it back, then finishes."""
        root = make_workspace(self)
        llm = MockLLM([
            tool_turn("write_file", path="hello.txt", content="hi from agent\n"),
            tool_turn("bash", command="cat hello.txt"),
            text_turn("File created and verified."),
        ])
        trace = TraceLogger()
        agent = make_agent(llm, make_registry(root), trace=trace)
        result = agent.run("Create hello.txt containing a greeting.")

        self.assertEqual(result.stop_reason, "completed")
        self.assertTrue(result.ok)
        self.assertEqual(result.final_text, "File created and verified.")
        self.assertEqual(result.steps, 3)
        self.assertEqual(result.tool_calls, 2)
        with open(os.path.join(root, "hello.txt")) as f:
            self.assertEqual(f.read(), "hi from agent\n")
        # the bash observation containing the file contents reached the LLM
        third_request_msgs = llm.requests[2]["messages"]
        tool_msgs = [m for m in third_request_msgs if m["role"] == "tool"]
        self.assertIn("hi from agent", tool_msgs[-1]["content"])

    def test_transcript_shape_roles_and_ids(self):
        root = make_workspace(self)
        llm = MockLLM([tool_turn("bash", command="true"), text_turn("done")])
        agent = make_agent(llm, make_registry(root))
        result = agent.run("do nothing")
        roles = [m["role"] for m in result.messages]
        self.assertEqual(roles, ["system", "user", "assistant", "tool", "assistant"])
        call_id = result.messages[2]["tool_calls"][0]["call_id"]
        self.assertEqual(result.messages[3]["tool_call_id"], call_id)
        self.assertEqual(result.messages[3]["tool_name"], "bash")

    def test_tool_failure_is_observation_loop_continues(self):
        root = make_workspace(self)
        llm = MockLLM([
            tool_turn("read_file", path="missing.txt"),
            text_turn("The file does not exist."),
        ])
        agent = make_agent(llm, make_registry(root))
        result = agent.run("read missing.txt")
        self.assertEqual(result.stop_reason, "completed")
        tool_msg = [m for m in result.messages if m["role"] == "tool"][0]
        self.assertTrue(tool_msg["content"].startswith("ERROR:"))
        self.assertIn("no such file", tool_msg["content"])

    def test_unknown_tool_call_is_survivable(self):
        root = make_workspace(self)
        llm = MockLLM([
            AssistantTurn(tool_calls=[ToolCall("teleport", {"to": "prod"}, "call_x")]),
            text_turn("ok, no teleporting"),
        ])
        agent = make_agent(llm, make_registry(root))
        result = agent.run("teleport")
        self.assertEqual(result.stop_reason, "completed")
        tool_msg = [m for m in result.messages if m["role"] == "tool"][0]
        self.assertIn("unknown tool", tool_msg["content"])

    def test_observation_truncated_before_entering_history(self):
        root = make_workspace(self)
        with open(os.path.join(root, "big.txt"), "w") as f:
            f.write("A" * 50000)
        llm = MockLLM([tool_turn("read_file", path="big.txt"), text_turn("done")])
        cfg = AgentConfig(max_observation_chars=500)
        agent = make_agent(llm, make_registry(root), config=cfg)
        result = agent.run("read the big file")
        tool_msg = [m for m in result.messages if m["role"] == "tool"][0]
        self.assertLess(len(tool_msg["content"]), 700)  # 500 + marker
        self.assertIn("TRUNCATED", tool_msg["content"])
        # and what the LLM actually received on the next request was truncated
        sent = [m for m in llm.requests[1]["messages"] if m["role"] == "tool"][0]
        self.assertIn("TRUNCATED", sent["content"])

    def test_multiple_tool_calls_in_one_turn_all_dispatched_in_order(self):
        root = make_workspace(self)
        llm = MockLLM([
            AssistantTurn(tool_calls=[
                ToolCall("write_file", {"path": "a.txt", "content": "1"}, "c1"),
                ToolCall("write_file", {"path": "b.txt", "content": "2"}, "c2"),
            ]),
            text_turn("both written"),
        ])
        agent = make_agent(llm, make_registry(root))
        result = agent.run("write two files")
        self.assertEqual(result.tool_calls, 2)
        tool_msgs = [m for m in result.messages if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in tool_msgs], ["c1", "c2"])
        self.assertTrue(os.path.exists(os.path.join(root, "a.txt")))
        self.assertTrue(os.path.exists(os.path.join(root, "b.txt")))

    def test_max_steps_stops_runaway_loop(self):
        root = make_workspace(self)
        llm = MockLLM([tool_turn("bash", command="true") for _ in range(10)])
        cfg = AgentConfig(max_steps=3)
        trace = TraceLogger()
        agent = make_agent(llm, make_registry(root), config=cfg, trace=trace)
        result = agent.run("loop forever")
        self.assertEqual(result.stop_reason, "max_steps")
        self.assertEqual(result.steps, 3)
        self.assertEqual(llm.calls_made, 3)
        self.assertEqual(trace.events[-1]["stop_reason"], "max_steps")

    def test_retryable_llm_errors_are_retried_and_traced(self):
        root = make_workspace(self)
        sleeps = []
        llm = FlakyLLM(MockLLM([text_turn("recovered")]), fail_times=2)
        cfg = AgentConfig(retry_policy=RetryPolicy(max_attempts=4, base_delay=1.0))
        trace = TraceLogger()
        agent = Agent(llm, make_registry(root), config=cfg, trace=trace,
                      sleep=sleeps.append, rng=lambda: 0.5)
        result = agent.run("survive the flake")
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual(result.final_text, "recovered")
        self.assertEqual(llm.attempts, 3)
        self.assertEqual(sleeps, [1.0, 2.0])
        self.assertEqual(trace.count("llm_retry"), 2)

    def test_retries_exhausted_ends_run_as_llm_error(self):
        root = make_workspace(self)
        llm = FlakyLLM(MockLLM([]), fail_times=99)
        cfg = AgentConfig(retry_policy=RetryPolicy(max_attempts=2, base_delay=1.0))
        agent = make_agent(llm, make_registry(root), config=cfg)
        result = agent.run("doomed")
        self.assertEqual(result.stop_reason, "llm_error")
        self.assertFalse(result.ok)
        self.assertIn("RetriesExhausted", result.error)
        self.assertEqual(llm.attempts, 2)

    def test_fatal_llm_error_not_retried(self):
        root = make_workspace(self)
        llm = FlakyLLM(MockLLM([]), fail_times=99,
                       error_factory=lambda: FatalLLMError("auth"))
        agent = make_agent(llm, make_registry(root))
        result = agent.run("doomed")
        self.assertEqual(result.stop_reason, "llm_error")
        self.assertEqual(llm.attempts, 1)  # fatal -> no retry burn
        self.assertIn("FatalLLMError", result.error)

    def test_trace_event_sequence_for_simple_run(self):
        root = make_workspace(self)
        llm = MockLLM([tool_turn("bash", command="true"), text_turn("done")])
        trace = TraceLogger(clock=lambda: "T")
        agent = make_agent(llm, make_registry(root), trace=trace)
        agent.run("task")
        self.assertEqual([e["event"] for e in trace.events], [
            "run_start", "llm_request", "llm_response", "tool_call", "dispatch",
            "tool_result", "llm_request", "llm_response", "run_end",
        ])
        self.assertEqual(trace.events[-1]["stop_reason"], "completed")

    def test_scratchpad_notes_carry_across_agent_instances(self):
        """Run 1 saves a note via the scratchpad tool; run 2 (a NEW Agent over
        the same pad file) sees it injected into the system prompt."""
        root = make_workspace(self)
        pad = Scratchpad(os.path.join(root, "state", "pad.md"))

        llm1 = MockLLM([
            tool_turn("scratchpad", op="append", note="port is 8043"),
            text_turn("noted"),
        ])
        agent1 = make_agent(llm1, make_registry(root, [ScratchpadTool(pad)]),
                            scratchpad=pad)
        self.assertEqual(agent1.run("remember the port").stop_reason, "completed")

        llm2 = MockLLM([text_turn("the port is 8043")])
        agent2 = make_agent(llm2, make_registry(root, [ScratchpadTool(pad)]),
                            scratchpad=pad)
        agent2.run("what port?")
        system_sent = llm2.requests[0]["messages"][0]
        self.assertEqual(system_sent["role"], "system")
        self.assertIn("port is 8043", system_sent["content"])

    def test_empty_scratchpad_leaves_system_prompt_clean(self):
        root = make_workspace(self)
        pad = Scratchpad(os.path.join(root, "pad.md"))
        llm = MockLLM([text_turn("hi")])
        agent = make_agent(llm, make_registry(root), scratchpad=pad)
        agent.run("hello")
        self.assertNotIn("scratchpad", llm.requests[0]["messages"][0]["content"])

    def test_tool_specs_sent_to_llm(self):
        root = make_workspace(self)
        llm = MockLLM([text_turn("ok")])
        agent = make_agent(llm, make_registry(root))
        agent.run("x")
        sent_tools = [t["name"] for t in llm.requests[0]["tools"]]
        self.assertEqual(sorted(sent_tools), ["bash", "read_file", "write_file"])


if __name__ == "__main__":
    unittest.main()

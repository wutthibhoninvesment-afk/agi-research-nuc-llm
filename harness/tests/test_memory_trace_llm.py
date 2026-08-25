import json
import os
import shutil
import tempfile
import unittest

from agentloop import (
    AssistantTurn,
    FatalLLMError,
    FlakyLLM,
    MockLLM,
    RetryableLLMError,
    Scratchpad,
    ScratchpadTool,
    TraceLogger,
)
from agentloop.llm import text_turn, tool_turn


class ScratchpadTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="agentloop-pad-")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.path = os.path.join(self.dir, "pad.md")

    def test_append_and_read_survive_new_instance(self):
        Scratchpad(self.path).append("note one")
        Scratchpad(self.path).append("note two")
        # a brand-new object over the same file sees both notes
        self.assertEqual(Scratchpad(self.path).read_all(),
                         "note one\nnote two\n")

    def test_read_missing_file_is_empty(self):
        self.assertEqual(Scratchpad(self.path).read_all(), "")

    def test_clear(self):
        pad = Scratchpad(self.path)
        pad.append("x")
        pad.clear()
        self.assertEqual(pad.read_all(), "")

    def test_tool_ops(self):
        tool = ScratchpadTool(Scratchpad(self.path))
        self.assertTrue(tool.run(op="append", note="remember me").ok)
        res = tool.run(op="read")
        self.assertTrue(res.ok)
        self.assertIn("remember me", res.output)
        self.assertTrue(tool.run(op="clear").ok)
        self.assertIn("empty", tool.run(op="read").output)

    def test_tool_append_without_note_fails(self):
        tool = ScratchpadTool(Scratchpad(self.path))
        self.assertFalse(tool.run(op="append").ok)

    def test_tool_unknown_op_fails(self):
        tool = ScratchpadTool(Scratchpad(self.path))
        self.assertFalse(tool.run(op="explode").ok)


class TraceLoggerTests(unittest.TestCase):
    def test_in_memory_events_and_count(self):
        clock = lambda: "2026-01-01T00:00:00+00:00"
        t = TraceLogger(clock=clock)
        t.log("run_start", task="t")
        t.log("tool_call", name="bash")
        t.log("tool_call", name="read_file")
        self.assertEqual(t.count("tool_call"), 2)
        self.assertEqual(t.events[0],
                         {"ts": "2026-01-01T00:00:00+00:00",
                          "event": "run_start", "task": "t"})

    def test_jsonl_file_one_valid_json_object_per_line(self):
        d = tempfile.mkdtemp(prefix="agentloop-trace-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        path = os.path.join(d, "sub", "trace.jsonl")
        t = TraceLogger(path=path)
        t.log("a", n=1)
        t.log("b", payload={"k": [1, 2]})
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), 2)
        parsed = [json.loads(line) for line in lines]
        self.assertEqual(parsed[0]["event"], "a")
        self.assertEqual(parsed[1]["payload"], {"k": [1, 2]})

    def test_new_logger_truncates_previous_run(self):
        d = tempfile.mkdtemp(prefix="agentloop-trace-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        path = os.path.join(d, "trace.jsonl")
        TraceLogger(path=path).log("old_event")
        t2 = TraceLogger(path=path)
        t2.log("new_event")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("old_event", content)
        self.assertIn("new_event", content)

    def test_unserializable_fields_fall_back_to_repr(self):
        d = tempfile.mkdtemp(prefix="agentloop-trace-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        path = os.path.join(d, "trace.jsonl")
        TraceLogger(path=path).log("err", error=ValueError("boom"))
        with open(path, encoding="utf-8") as f:
            record = json.loads(f.read())
        self.assertIn("boom", record["error"])


class MockLLMTests(unittest.TestCase):
    def test_plays_script_in_order_and_records_requests(self):
        llm = MockLLM([tool_turn("bash", command="ls"), text_turn("done")])
        t1 = llm.complete([{"role": "user", "content": "go"}], [])
        self.assertEqual(t1.tool_calls[0].name, "bash")
        self.assertTrue(t1.wants_tools)
        t2 = llm.complete([], [])
        self.assertEqual(t2.text, "done")
        self.assertFalse(t2.wants_tools)
        self.assertEqual(len(llm.requests), 2)
        self.assertEqual(llm.requests[0]["messages"][0]["content"], "go")

    def test_exhausted_script_raises_fatal(self):
        llm = MockLLM([text_turn("only one")])
        llm.complete([], [])
        with self.assertRaises(FatalLLMError):
            llm.complete([], [])

    def test_flaky_llm_fails_then_delegates(self):
        inner = MockLLM([text_turn("recovered")])
        llm = FlakyLLM(inner, fail_times=2)
        for _ in range(2):
            with self.assertRaises(RetryableLLMError):
                llm.complete([], [])
        self.assertEqual(llm.complete([], []).text, "recovered")
        self.assertEqual(llm.attempts, 3)

    def test_flaky_llm_custom_error_factory(self):
        llm = FlakyLLM(MockLLM([]), fail_times=1,
                       error_factory=lambda: FatalLLMError("401"))
        with self.assertRaises(FatalLLMError):
            llm.complete([], [])

    def test_tool_turn_ids_are_unique(self):
        a = tool_turn("x").tool_calls[0].call_id
        b = tool_turn("x").tool_calls[0].call_id
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith("call_"))


if __name__ == "__main__":
    unittest.main()

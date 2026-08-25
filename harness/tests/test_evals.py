import os
import shutil
import tempfile
import unittest

from agentloop import (
    Agent,
    EvalTask,
    MockLLM,
    ToolRegistry,
    WriteFileTool,
    run_evals,
)
from agentloop.llm import text_turn, tool_turn


class EvalHarnessTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="agentloop-eval-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        # one MockLLM script per task name — the factory hands each task its own
        self.scripts = {
            "creates-file": [
                tool_turn("write_file", path="out.txt", content="payload"),
                text_turn("wrote out.txt"),
            ],
            "wrong-content": [
                tool_turn("write_file", path="wrong.txt", content="garbage"),
                text_turn("done (but wrong)"),
            ],
            "checker-crashes": [text_turn("irrelevant")],
        }

    def make_agent(self, task):
        registry = ToolRegistry([WriteFileTool(self.root)])
        return Agent(MockLLM(self.scripts[task.name]), registry,
                     sleep=lambda s: None, rng=lambda: 0.5)

    def test_report_scores_pass_fail_and_crashing_checker(self):
        def check_created(result, ws):
            path = os.path.join(ws, "out.txt")
            if not os.path.exists(path):
                return False, "out.txt missing"
            with open(path) as f:
                content = f.read()
            return content == "payload", "content=%r" % content

        def check_expected(result, ws):
            ok = os.path.exists(os.path.join(ws, "expected.txt"))
            return ok, "expected.txt %s" % ("found" if ok else "missing")

        def check_broken(result, ws):
            raise KeyError("bug in the checker itself")

        tasks = [
            EvalTask("creates-file", "create out.txt", check_created),
            EvalTask("wrong-content", "create expected.txt", check_expected),
            EvalTask("checker-crashes", "anything", check_broken),
        ]
        report = run_evals(tasks, self.make_agent, self.root)

        self.assertEqual(report.total, 3)
        self.assertEqual(report.passed, 1)
        self.assertAlmostEqual(report.pass_rate, 1 / 3)
        by_name = {o.name: o for o in report.outcomes}
        self.assertTrue(by_name["creates-file"].passed)
        self.assertEqual(by_name["creates-file"].detail, "content='payload'")
        self.assertFalse(by_name["wrong-content"].passed)
        self.assertFalse(by_name["checker-crashes"].passed)
        self.assertIn("checker crashed", by_name["checker-crashes"].detail)
        self.assertIn("KeyError", by_name["checker-crashes"].detail)

    def test_outcomes_carry_run_metrics(self):
        tasks = [EvalTask("creates-file", "create out.txt",
                          lambda r, ws: (r.ok, r.stop_reason))]
        report = run_evals(tasks, self.make_agent, self.root)
        out = report.outcomes[0]
        self.assertEqual(out.steps, 2)
        self.assertEqual(out.tool_calls, 1)
        self.assertEqual(out.stop_reason, "completed")

    def test_summary_format(self):
        tasks = [EvalTask("creates-file", "create out.txt",
                          lambda r, ws: (True, "all good"))]
        report = run_evals(tasks, self.make_agent, self.root)
        summary = report.summary()
        self.assertIn("1/1 passed (100%)", summary)
        self.assertIn("[PASS] creates-file", summary)
        self.assertIn("all good", summary)

    def test_empty_suite(self):
        report = run_evals([], self.make_agent, self.root)
        self.assertEqual(report.total, 0)
        self.assertEqual(report.pass_rate, 0.0)
        self.assertIn("0/0", report.summary())


if __name__ == "__main__":
    unittest.main()

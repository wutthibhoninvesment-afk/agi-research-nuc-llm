"""Evaluation harness: run an agent against a suite of tasks, score, report.

Fully offline-capable: the agent factory decides which LLM backs each run, so
tests wire in MockLLM scripts and the whole suite executes in milliseconds.

Each EvalTask gets a FRESH agent (fresh message history) from the factory —
tasks must not leak state into each other except through the workspace, which
is the thing under test. The checker inspects both the AgentResult and the
workspace on disk, returning (passed, detail) so reports carry evidence, not
just booleans.

A checker that raises is scored as a failure with the traceback in `detail`
(an eval bug must not crash the whole suite).
"""

import traceback
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from .agent import Agent, AgentResult
from .usage import Usage

Checker = Callable[[AgentResult, str], Tuple[bool, str]]


@dataclass
class EvalTask:
    name: str
    prompt: str
    check: Checker  # (result, workspace_root) -> (passed, detail)


@dataclass
class EvalOutcome:
    name: str
    passed: bool
    detail: str
    stop_reason: str
    steps: int
    tool_calls: int
    usage: Usage = field(default_factory=Usage)
    cost_usd: Optional[float] = None
    compactions: int = 0


@dataclass
class EvalReport:
    outcomes: List[EvalOutcome] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def passed(self) -> int:
        return sum(1 for o in self.outcomes if o.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def usage(self) -> Usage:
        total = Usage()
        for o in self.outcomes:
            total = total + o.usage
        return total

    @property
    def cost_usd(self) -> Optional[float]:
        costs = [o.cost_usd for o in self.outcomes if o.cost_usd is not None]
        return sum(costs) if costs else None

    def summary(self) -> str:
        lines = ["eval report: %d/%d passed (%.0f%%)"
                 % (self.passed, self.total, 100 * self.pass_rate)]
        for o in self.outcomes:
            mark = "PASS" if o.passed else "FAIL"
            extra = ""
            if not o.usage.is_zero:
                extra = " tokens=%d" % o.usage.total
                if o.cost_usd is not None:
                    extra += " cost=$%.4f" % o.cost_usd
            if o.compactions:
                extra += " compactions=%d" % o.compactions
            lines.append("  [%s] %-24s steps=%d tools=%d stop=%s%s  %s"
                         % (mark, o.name, o.steps, o.tool_calls,
                            o.stop_reason, extra, o.detail))
        u = self.usage
        if not u.is_zero:
            line = "totals: %d input + %d output tokens" % (u.total_input, u.output_tokens)
            if self.cost_usd is not None:
                line += ", $%.4f" % self.cost_usd
            lines.append(line)
        return "\n".join(lines)


def run_evals(
    tasks: List[EvalTask],
    make_agent: Callable[[EvalTask], Agent],
    workspace_root: str,
) -> EvalReport:
    report = EvalReport()
    for task in tasks:
        agent = make_agent(task)
        result = agent.run(task.prompt)
        try:
            passed, detail = task.check(result, workspace_root)
        except Exception:  # noqa: BLE001 — checker bug scores as failure
            passed, detail = False, "checker crashed:\n" + traceback.format_exc()
        report.outcomes.append(EvalOutcome(
            name=task.name, passed=passed, detail=detail,
            stop_reason=result.stop_reason, steps=result.steps,
            tool_calls=result.tool_calls, usage=result.usage,
            cost_usd=result.cost_usd, compactions=result.compactions,
        ))
    return report

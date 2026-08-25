"""Sub-agent delegation: a tool that runs a FRESH agent on a sub-task.

Why: an agent's context is a budget. Work that produces a lot of
observation text (read twenty files, scan a build log, search the tree)
inflates every later request for the rest of the run — at cached-read
price if the prefix stays warm, at full price if not. A sub-agent does that
work in its own empty context and hands back only a report; the parent
carries the report, not the observations. bench_delegation.py prices the
trade-off; this module is the mechanism.

Design decisions (each covered by a test):
  - The child is built by a caller-supplied factory `(ChildSpec) -> Agent`,
    so the caller decides its LLM, tools, caps, trace and system prompt.
    The tool itself only frames the task, runs the child, and reports.
  - Cost is NOT hidden: the child's whole `Usage` rides back on the
    ToolResult (`usage=`), which the parent loop adds to its own run
    total and checks against its caps right after dispatch (agent.py).
    A child cannot spend outside the parent's cap for longer than one
    dispatch. Child caps themselves are the factory's business (pass the
    parent's remaining budget in if you want a hard ceiling).
  - Depth is bounded: `DelegateTool(depth=d, max_depth=m)` refuses to run
    when d > m (the observation says so), and `child_tool()` returns the
    tool a child registry should get at depth d+1, or None at the limit —
    so a factory can wire nested delegation without inventing the rule.
  - The parent sees ONLY the child's final text (plus a one-line footer
    with steps / tool calls / stop reason). A child that stopped early
    (max_steps, budget, llm_error) comes back as ok=False with the reason,
    so the parent can decide to retry, narrow the task, or do it itself.
  - Structured facts (child stop_reason, steps, tool_calls, depth,
    cost) travel in `ToolResult.meta` → the parent's `tool_result` trace
    event, never in the model-visible text.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional

from .tools import Tool, ToolResult

CHILD_TASK_TEMPLATE = (
    "You are a sub-agent (delegation depth {depth}). The caller sees ONLY "
    "your final text reply, so finish with a complete, self-contained "
    "report of what it asked for.\n\nTask:\n{task}{context}"
)


@dataclass
class ChildSpec:
    task: str          # the full framed task text the child will receive
    depth: int         # 1 for a child of a top-level agent
    child_id: str      # unique per DelegateTool instance: "d<depth>.<n>"
    raw_task: str      # the task string the parent model wrote


class DelegateTool(Tool):
    name = "delegate"
    description = (
        "Hand a self-contained sub-task to a fresh sub-agent that has the same "
        "workspace and tools but an EMPTY context (it cannot see your history). "
        "Use it for work whose output would flood your context: reading many "
        "files, scanning long logs or test output, searching the whole tree. "
        "You receive only its final report, so state the task fully and say "
        "exactly what to report back."
    )
    params = {
        "task": {"type": "string",
                 "description": "what the sub-agent must do and what to report back"},
        "context": {"type": "string",
                    "description": "facts it needs that it cannot see (paths, findings so far); optional"},
    }
    required = ["task"]

    def __init__(self, factory: Callable[[ChildSpec], object], depth: int = 1,
                 max_depth: int = 2, parallel_safe: bool = False,
                 owner: Optional[str] = None):
        if depth < 1 or max_depth < 1:
            raise ValueError("depth and max_depth must be >= 1")
        self.factory = factory
        self.depth = depth
        self.max_depth = max_depth
        self.parallel_safe = parallel_safe
        # child_id of the agent that OWNS this tool (None at top level), so
        # ids chain: "d1.1" -> "d1.1/d2.1" — usable directly as a trace tag.
        self.owner = owner
        self.results: List[object] = []   # AgentResult per child run, in order
        self._n = 0

    def child_tool(self, owner: Optional[str] = None) -> Optional["DelegateTool"]:
        """The delegate tool a child's registry should carry (one level
        deeper), or None when the child sits at max_depth. Pass the child's
        own `spec.child_id` as `owner` so grandchildren's ids chain."""
        if self.depth + 1 > self.max_depth:
            return None
        return DelegateTool(self.factory, depth=self.depth + 1, max_depth=self.max_depth,
                            parallel_safe=self.parallel_safe, owner=owner)

    def run(self, task: str, context: Optional[str] = None) -> ToolResult:
        if not task or not task.strip():
            return ToolResult(False, "delegate: 'task' must be a non-empty string")
        if self.depth > self.max_depth:
            return ToolResult(False, "delegate: depth limit %d reached; do this step yourself"
                              % self.max_depth)
        self._n += 1
        child_id = "%sd%d.%d" % ((self.owner + "/") if self.owner else "", self.depth, self._n)
        ctx = ("\n\nContext from the caller:\n" + context.strip()) if context and context.strip() else ""
        framed = CHILD_TASK_TEMPLATE.format(depth=self.depth, task=task.strip(), context=ctx)
        spec = ChildSpec(task=framed, depth=self.depth, child_id=child_id, raw_task=task)
        child = self.factory(spec)
        result = child.run(framed)
        self.results.append(result)
        cost = result.cost_usd
        footer = "[sub-agent %s: %s after %d steps / %d tool calls%s]" % (
            child_id, result.stop_reason, result.steps, result.tool_calls,
            (", $%.4f" % cost) if cost is not None else "")
        text = result.final_text.strip() or "(sub-agent returned no text)"
        if not result.ok:
            text = ("sub-agent stopped early: %s%s\nIts last text:\n%s"
                    % (result.stop_reason, (" — " + result.error) if result.error else "", text))
        meta = {"child_id": child_id, "depth": self.depth, "child_stop_reason": result.stop_reason,
                "child_steps": result.steps, "child_tool_calls": result.tool_calls,
                "child_cost_usd": cost, "child_compactions": result.compactions}
        return ToolResult(result.ok, text + "\n" + footer, usage=result.usage, meta=meta)

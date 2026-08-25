"""agentloop — a minimal, testable agent harness (stdlib only, Python 3.9+).

Layers (each independently testable):
    llm.py       LLM interface, message types, MockLLM / FlakyLLM for offline tests
    tools.py     Tool protocol, ToolRegistry, sandboxed file/bash/search tools
    memory.py    Scratchpad memory backed by a file, exposed as a tool
    truncate.py  Head+tail observation truncation
    retry.py     Exponential backoff with injectable sleep/rng
    trace.py     JSONL trace logging
    usage.py     Token usage + USD pricing
    context.py   Token estimation (self-calibrating) + history compaction
    agent.py     The tool loop that ties everything together
    adapters.py  Real backends: ClaudeCLILLM (claude -p), AnthropicAPILLM (Messages API)
    evals.py     Task-suite evaluation harness with pass/fail reporting
    checkpoint.py Crash-safe per-step state persistence + resume (round 31)
    delegate.py  DelegateTool: fresh-context sub-agents with cost roll-up (round 31)
    sim.py       CachingSimLLM: prompt-cache-pricing test double (round 31)
"""

from .llm import (
    LLM,
    MockLLM,
    FlakyLLM,
    AssistantTurn,
    ToolCall,
    RetryableLLMError,
    FatalLLMError,
)
from .tools import (
    Tool,
    ToolRegistry,
    ToolResult,
    ReadFileTool,
    WriteFileTool,
    ListDirTool,
    BashTool,
    SearchTool,
    SandboxViolation,
)
from .memory import Scratchpad, ScratchpadTool
from .truncate import truncate_observation
from .retry import retry_call, RetryPolicy, RetriesExhausted
from .trace import TraceLogger
from .agent import Agent, AgentConfig, AgentResult, DEFAULT_SYSTEM_PROMPT
from .evals import EvalTask, EvalOutcome, EvalReport, run_evals
from .usage import Usage, PRICES_PER_MTOK
from .context import TokenEstimator, ContextBudget, CompactionReport, compact
from .adapters import ClaudeCLILLM, AnthropicAPILLM
from .checkpoint import Checkpoint
from .delegate import DelegateTool, ChildSpec
from .sim import CachingSimLLM, SimCache

__all__ = [
    "LLM", "MockLLM", "FlakyLLM", "AssistantTurn", "ToolCall",
    "RetryableLLMError", "FatalLLMError",
    "Tool", "ToolRegistry", "ToolResult",
    "ReadFileTool", "WriteFileTool", "ListDirTool", "BashTool", "SearchTool",
    "SandboxViolation",
    "Scratchpad", "ScratchpadTool",
    "truncate_observation",
    "retry_call", "RetryPolicy", "RetriesExhausted",
    "TraceLogger",
    "Agent", "AgentConfig", "AgentResult", "DEFAULT_SYSTEM_PROMPT",
    "EvalTask", "EvalOutcome", "EvalReport", "run_evals",
    "Usage", "PRICES_PER_MTOK",
    "TokenEstimator", "ContextBudget", "CompactionReport", "compact",
    "ClaudeCLILLM", "AnthropicAPILLM",
    "Checkpoint", "DelegateTool", "ChildSpec", "CachingSimLLM", "SimCache",
]

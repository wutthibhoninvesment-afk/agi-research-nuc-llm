"""The agent tool loop — ties LLM, tools, memory, truncation, retry, trace,
context budget, and usage accounting together.

One `step` = one LLM completion. The loop:

    messages = [system, user task]
    while steps < max_steps:
        compact(messages) if a context budget is set   # monotonic, in place
        turn = llm.complete(messages, tool_specs)      # retried on transient errors
        account usage; stop with budget_exhausted if a spend cap is hit
        append assistant turn to messages
        if no tool calls: return completed(turn.text)
        dispatch the turn's tool calls (parallel if every tool is parallel_safe)
        append one tool message per call, in call order, TRUNCATED

Design decisions (each covered by a test):
  - Tool failures are observations, not exceptions: the model sees "ERROR: ..."
    and gets to react. Only LLM-level failures end the run.
  - Observations are truncated BEFORE entering the message history, so context
    growth is bounded per step no matter what a tool emits.
  - Retry wraps only the LLM call. Tools are not retried: a flaky tool result
    is information the model should see.
  - If the scratchpad has notes from a previous run, they are injected into
    the system prompt — cross-run memory without any model cooperation.
  - Parallel dispatch is all-or-nothing per turn: if any requested tool is not
    parallel_safe the whole batch runs serially in call order. Results are
    always appended in call order regardless of completion order.
  - Spend caps (tokens / USD) are checked after every completion; hitting one
    is a distinct stop reason, never an exception.
  - stop_reason is one of: "completed" | "max_steps" | "llm_error" |
    "budget_exhausted".
  - Tools may spend LLM tokens themselves (a delegated sub-agent, an
    LLM-judge): `ToolResult.usage` is added to the run's usage and the caps
    are re-checked right after dispatch, so tool-side spend can neither hide
    from the accounting nor outrun a cap by more than one dispatch (round 31).
  - Checkpointing (round 31): with `run(task, checkpoint=Checkpoint(path))`
    the complete loop state is persisted at every step boundary and a later
    run() with the same task resumes from it — see checkpoint.py for the
    exact guarantees (byte-identical wire history, atomic saves, completed
    runs replay without an LLM call).
"""

import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .checkpoint import Checkpoint
from .context import ContextBudget, TokenEstimator, compact
from .llm import LLM, FatalLLMError, RetryableLLMError
from .memory import Scratchpad
from .retry import RetriesExhausted, RetryPolicy, retry_call
from .tools import ToolRegistry, ToolResult
from .trace import TraceLogger
from .truncate import truncate_observation
from .usage import Usage

DEFAULT_SYSTEM_PROMPT = (
    "You are a software-engineering agent operating in a workspace.\n"
    "Use the available tools to complete the task. Work step by step.\n"
    "When the task is done, reply with plain text (no tool calls): that text\n"
    "is your final answer."
)


@dataclass
class AgentConfig:
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_steps: int = 20
    max_observation_chars: int = 8000
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    context_budget: Optional[ContextBudget] = None   # None = no compaction
    parallel_tools: bool = False                      # concurrent dispatch when safe
    max_parallel: int = 8
    max_total_tokens: Optional[int] = None            # spend cap (input+output, all steps)
    max_cost_usd: Optional[float] = None              # spend cap in USD (needs a priced model)
    model_for_pricing: Optional[str] = None           # defaults to llm.model if present
    exact_token_check: bool = False                   # verify near-boundary estimates with
                                                        # llm.count_tokens() when available (costs
                                                        # a network call; see _maybe_exact_check)
    exact_token_margin: int = 500                      # only bother when the heuristic estimate
                                                        # is within this many tokens of the budget
    # When the step budget runs out mid-work, make ONE more LLM call with no
    # tools offered and `wrap_up_prompt` as the user turn, so the run still
    # ends with an answer (round 101: a 30-step review that reads for 30
    # steps otherwise returns nothing scoreable). stop_reason stays
    # "max_steps"; the answer lands in final_text; tool calls the model
    # still emits are ignored and logged.
    wrap_up_on_max_steps: bool = False
    wrap_up_prompt: str = ("Your tool-step budget is exhausted: no further tool calls will be "
                           "run. Reply now with your final answer, in the format the task "
                           "asked for, based on what you have seen so far.")


@dataclass
class AgentResult:
    stop_reason: str                  # "completed" | "max_steps" | "llm_error" | "budget_exhausted"
    final_text: str
    steps: int                        # LLM completions consumed
    tool_calls: int                   # tool dispatches performed
    error: Optional[str] = None       # set when stop_reason == "llm_error"
    messages: List[dict] = field(default_factory=list)  # full (possibly compacted) transcript
    usage: Usage = field(default_factory=Usage)
    cost_usd: Optional[float] = None  # None when the model is unpriced
    compactions: int = 0              # how many steps compacted the history
    resumed_from: Optional[int] = None  # steps already done when this run resumed a checkpoint

    @property
    def ok(self) -> bool:
        return self.stop_reason == "completed"


class Agent:
    def __init__(
        self,
        llm: LLM,
        registry: ToolRegistry,
        config: Optional[AgentConfig] = None,
        trace: Optional[TraceLogger] = None,
        scratchpad: Optional[Scratchpad] = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
        estimator: Optional[TokenEstimator] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.llm = llm
        self.registry = registry
        self.config = config or AgentConfig()
        self.trace = trace or TraceLogger()  # in-memory if none supplied
        self.scratchpad = scratchpad
        self._sleep = sleep
        self._rng = rng
        self.estimator = estimator or TokenEstimator()
        self._clock = clock

    # ------------------------------------------------------------------ run --

    def run(self, task: str, checkpoint: Optional[Checkpoint] = None) -> AgentResult:
        cfg = self.config
        tool_specs = self.registry.specs()
        model = cfg.model_for_pricing or getattr(self.llm, "model", None) or ""
        # Cache writes are priced by the TTL the backend was configured to
        # request ("5m" default, "1h" doubles the write premium); backends
        # without a cache config price at the default.
        write_ttl = (getattr(self.llm, "cache", None) or {}).get("ttl") or "5m"

        state = checkpoint.load() if checkpoint is not None else None
        resumed_from: Optional[int] = None
        if state is not None:
            if state.get("task") != task:
                raise ValueError("checkpoint %s belongs to a different task" % checkpoint.path)
            messages = list(state["messages"])
            steps = int(state["steps"])
            tool_calls_made = int(state["tool_calls"])
            compactions = int(state["compactions"])
            usage = Usage(**state["usage"])
            est = state.get("estimator") or {}
            if est.get("observations"):
                self.estimator.chars_per_token = float(est["chars_per_token"])
                self.estimator.observations = int(est["observations"])
            if state.get("llm_state") is not None and hasattr(self.llm, "restore_state"):
                self.llm.restore_state(state["llm_state"])
            if state.get("done"):
                # Terminal checkpoint: replay the stored result, no LLM call.
                r = state["result"]
                cost = usage.cost_usd(model, write_ttl=write_ttl) if model else None
                self.trace.log("run_replayed", task=task, stop_reason=r["stop_reason"],
                               steps=steps, tool_calls=tool_calls_made, cost_usd=cost)
                return AgentResult(r["stop_reason"], r.get("final_text", ""), steps,
                                   tool_calls_made, error=r.get("error"), messages=messages,
                                   usage=usage, cost_usd=cost, compactions=compactions,
                                   resumed_from=steps)
            resumed_from = steps
            self.trace.log("run_resumed", task=task, steps=steps, tool_calls=tool_calls_made,
                           n_messages=len(messages), last_stop_reason=state.get("last_stop_reason"),
                           model=model)
        else:
            messages = [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": task},
            ]
            steps = 0
            tool_calls_made = 0
            usage = Usage()
            compactions = 0
            self.trace.log("run_start", task=task, tools=self.registry.names(),
                           max_steps=cfg.max_steps, model=model)

        def snapshot(msgs: List[dict], **extra) -> dict:
            st = {"task": task, "steps": steps, "tool_calls": tool_calls_made,
                  "compactions": compactions, "usage": usage.as_dict(), "messages": msgs,
                  "estimator": {"chars_per_token": self.estimator.chars_per_token,
                                "observations": self.estimator.observations},
                  "model": model, "done": False}
            if hasattr(self.llm, "checkpoint_state"):
                st["llm_state"] = self.llm.checkpoint_state()
            st.update(extra)
            return st

        def save(msgs: List[dict], **extra) -> None:
            if checkpoint is not None:
                checkpoint.save(snapshot(msgs, **extra))

        def finish(stop_reason: str, text: str = "", error: Optional[str] = None,
                   persist: Optional[List[dict]] = None) -> AgentResult:
            cost = usage.cost_usd(model, write_ttl=write_ttl) if model else None
            self.trace.log("run_end", stop_reason=stop_reason, steps=steps,
                           tool_calls=tool_calls_made, usage=usage.as_dict(),
                           cost_usd=cost, compactions=compactions,
                           cache_hit_rate=round(usage.cache_hit_rate, 4),
                           **({"error": error} if error else {}),
                           **({"resumed_from": resumed_from} if resumed_from is not None else {}))
            if checkpoint is not None:
                if stop_reason == "completed":
                    save(messages, done=True, result={"stop_reason": stop_reason,
                                                      "final_text": text, "error": error})
                else:
                    # Non-terminal: keep the checkpoint live at its last
                    # consistent boundary so a re-run continues. `persist`
                    # lets a caller exclude a turn that was never acted on.
                    save(messages if persist is None else persist,
                         last_stop_reason=stop_reason, error=error)
            return AgentResult(stop_reason, text, steps, tool_calls_made, error=error,
                               messages=messages, usage=usage, cost_usd=cost,
                               compactions=compactions, resumed_from=resumed_from)

        if state is None:
            save(messages)   # step-0 boundary: a crash inside step 1 resumes cleanly

        while steps < cfg.max_steps:
            steps += 1

            if cfg.context_budget is not None:
                report = compact(messages, cfg.context_budget, self.estimator, tool_specs)
                if report.changed or not report.fits:
                    compactions += 1 if report.changed else 0
                    self.trace.log("context_compacted", step=steps, **report.as_dict())
                if cfg.exact_token_check:
                    compactions += self._maybe_exact_check(messages, tool_specs, cfg.context_budget, steps)

            chars_sent = self.estimator.chars_of(messages, tool_specs)
            t0 = self._clock()
            try:
                turn = self._complete_with_retry(messages, tool_specs, step=steps)
            except (RetriesExhausted, FatalLLMError) as e:
                return finish("llm_error", error=repr(e))
            duration = self._clock() - t0

            usage = usage + turn.usage
            if turn.usage.total_input > 0:
                self.estimator.observe(chars_sent, turn.usage.total_input)

            assistant_msg = {
                "role": "assistant",
                "content": turn.text,
                "tool_calls": [
                    {"name": c.name, "args": c.args, "call_id": c.call_id}
                    for c in turn.tool_calls
                ],
            }
            if turn.raw_content is not None:
                # Backend-native content blocks (e.g. Anthropic thinking /
                # redacted_thinking blocks) round-tripped verbatim so the
                # adapter can replay them on the next request. See
                # adapters.to_anthropic_messages.
                assistant_msg["raw_content"] = turn.raw_content
            messages.append(assistant_msg)
            self.trace.log("llm_response", step=steps, text_chars=len(turn.text),
                           tool_calls=[c.name for c in turn.tool_calls],
                           usage=turn.usage.as_dict(), duration_s=round(duration, 3),
                           raw_stop_reason=turn.raw_stop_reason,
                           estimated_input_tokens=self.estimator.estimate(messages[:-1], tool_specs))

            if not turn.wants_tools:
                return finish("completed", turn.text)

            over = self._budget_exceeded(usage, model)
            if over:
                # The assistant turn asked for tools that never ran: it is in
                # the returned transcript but NOT in the checkpoint (a
                # dangling tool_use would break the next request on resume).
                return finish("budget_exhausted", turn.text, error=over, persist=messages[:-1])

            results = self._dispatch_all(turn.tool_calls, step=steps)
            tool_usage = Usage()
            for call, result in zip(turn.tool_calls, results):
                tool_calls_made += 1
                observation = truncate_observation(result.as_text(), cfg.max_observation_chars)
                truncated = len(observation) != len(result.as_text())
                extra = {}
                if not result.usage.is_zero:
                    tool_usage = tool_usage + result.usage
                    extra["usage"] = result.usage.as_dict()
                if result.meta:
                    extra["meta"] = result.meta
                self.trace.log("tool_result", step=steps, name=call.name,
                               ok=result.ok, chars=len(result.output),
                               truncated=truncated, call_id=call.call_id, **extra)
                messages.append({
                    "role": "tool",
                    "content": observation,
                    "tool_call_id": call.call_id,
                    "tool_name": call.name,
                    "ok": result.ok,
                })
            if not tool_usage.is_zero:
                # Tool-side LLM spend (sub-agents etc.) counts, and the caps
                # are re-checked now rather than after the next completion.
                usage = usage + tool_usage
                over = self._budget_exceeded(usage, model)
                if over:
                    return finish("budget_exhausted", turn.text, error=over)
            save(messages)   # step boundary

        if cfg.wrap_up_on_max_steps:
            messages.append({"role": "user", "content": cfg.wrap_up_prompt})
            t0 = self._clock()
            try:
                turn = self._complete_with_retry(messages, [], step=steps + 1)
            except (RetriesExhausted, FatalLLMError) as e:
                messages.pop()
                return finish("max_steps", error="wrap-up failed: %r" % (e,))
            usage = usage + turn.usage
            messages.append({"role": "assistant", "content": turn.text, "tool_calls": []})
            self.trace.log("wrap_up", step=steps + 1, text_chars=len(turn.text),
                           ignored_tool_calls=[c.name for c in turn.tool_calls],
                           usage=turn.usage.as_dict(), duration_s=round(self._clock() - t0, 3))
            save(messages)
            return finish("max_steps", turn.text)

        return finish("max_steps")

    # -------------------------------------------------------------- helpers --

    def _maybe_exact_check(self, messages, tool_specs, budget: ContextBudget, step: int) -> int:
        """Opt-in ground-truth check near the budget boundary.

        The estimator's char/token ratio is an EMA of past requests; right at
        a budget boundary a heuristic miss either wastes a compaction that
        wasn't needed or, worse, lets an over-budget request through to a
        real 400. If the backend exposes count_tokens() (AnthropicAPILLM
        does; ClaudeCLILLM and MockLLM do not) and the heuristic estimate is
        within `exact_token_margin` tokens of the target, spend one exact
        call: recalibrate the estimator with the ground truth immediately
        (not just after the next completion), and if it turns out we are
        still over budget, compact again with the freshly-calibrated
        estimator. Returns 1 if that second compaction changed anything
        (folded into the caller's `compactions` counter), else 0. Any
        LLM-level failure here is non-fatal to the run — the heuristic result
        already stands and the request will still go out.
        """
        if not hasattr(self.llm, "count_tokens"):
            return 0
        heuristic = self.estimator.estimate(messages, tool_specs)
        if abs(heuristic - budget.target) > self.config.exact_token_margin:
            return 0
        try:
            exact = self.llm.count_tokens(messages, tool_specs)
        except (RetryableLLMError, FatalLLMError) as e:
            self.trace.log("exact_token_check_failed", step=step, error=repr(e))
            return 0
        chars = self.estimator.chars_of(messages, tool_specs)
        self.estimator.observe(chars, exact)
        self.trace.log("exact_token_check", step=step, heuristic=heuristic, exact=exact,
                       target=budget.target)
        if exact <= budget.target:
            return 0
        report2 = compact(messages, budget, self.estimator, tool_specs)
        if report2.changed:
            self.trace.log("context_compacted", step=step, exact_triggered=True, **report2.as_dict())
            return 1
        return 0

    def _budget_exceeded(self, usage: Usage, model: str) -> Optional[str]:
        cfg = self.config
        if cfg.max_total_tokens is not None and usage.total >= cfg.max_total_tokens:
            return "token cap: %d >= %d" % (usage.total, cfg.max_total_tokens)
        if cfg.max_cost_usd is not None:
            write_ttl = (getattr(self.llm, "cache", None) or {}).get("ttl") or "5m"
            cost = usage.cost_usd(model, write_ttl=write_ttl) if model else None
            if cost is None:
                return "cost cap set but model %r is unpriced" % model
            if cost >= cfg.max_cost_usd:
                return "cost cap: $%.4f >= $%.4f" % (cost, cfg.max_cost_usd)
        return None

    def _dispatch_all(self, calls, step: int) -> List[ToolResult]:
        for call in calls:
            self.trace.log("tool_call", step=step, name=call.name,
                           args=call.args, call_id=call.call_id)
        safe = all((self.registry.get(c.name) is not None and self.registry.get(c.name).parallel_safe)
                   for c in calls)
        mode = "parallel" if (self.config.parallel_tools and len(calls) > 1 and safe) else "serial"
        self.trace.log("dispatch", step=step, mode=mode, n=len(calls))
        if mode == "serial":
            return [self.registry.dispatch(c.name, dict(c.args)) for c in calls]
        with ThreadPoolExecutor(max_workers=min(self.config.max_parallel, len(calls))) as pool:
            futures = [pool.submit(self.registry.dispatch, c.name, dict(c.args)) for c in calls]
            return [f.result() for f in futures]   # call order, whatever finished first

    def _system_prompt(self) -> str:
        prompt = self.config.system_prompt
        if self.scratchpad is not None:
            notes = self.scratchpad.read_all()
            if notes.strip():
                prompt += ("\n\nNotes you saved in previous runs "
                           "(scratchpad):\n" + notes.rstrip("\n"))
        return prompt

    def _complete_with_retry(self, messages, tool_specs, step: int):
        self.trace.log("llm_request", step=step, n_messages=len(messages),
                       estimated_input_tokens=self.estimator.estimate(messages, tool_specs))

        def on_retry(attempt: int, error: Exception, delay: float) -> None:
            self.trace.log("llm_retry", step=step, attempt=attempt,
                           error=repr(error), delay_s=round(delay, 3))

        return retry_call(
            lambda: self.llm.complete(messages, tool_specs),
            retry_on=(RetryableLLMError,),
            policy=self.config.retry_policy,
            sleep=self._sleep,
            rng=self._rng,
            on_retry=on_retry,
        )

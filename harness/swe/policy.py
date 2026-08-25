"""PolicyLLM: a scripted, deterministic stand-in for a model.

The agentloop harness is model-agnostic: anything with `complete(messages,
tools) -> AssistantTurn` drives it. A PolicyLLM is a list of *steps*; each
step is a function `(last_observation, state) -> AssistantTurn | None` that
gets the most recent tool result and a mutable dict. Returning None skips to
the next step. The loop ends when a step returns a text-only turn.

This is NOT intelligence — it is a reproducible plan that exercises the
harness end-to-end on real work, and it doubles as a regression test for the
tools. Swap in ClaudeCLILLM (agentloop.adapters) for the real thing.
"""

from agentloop.llm import LLM, AssistantTurn, ToolCall, make_call_id


def call(name, **args):
    return AssistantTurn(tool_calls=[ToolCall(name, dict(args), make_call_id())])


def say(text):
    return AssistantTurn(text=text)


class PolicyLLM(LLM):
    def __init__(self, steps):
        self.steps = list(steps)
        self.state = {}
        self.turns = 0

    def complete(self, messages, tools):
        self.turns += 1
        last = messages[-1]
        observation = last["content"] if last["role"] == "tool" else None
        ok = observation is not None and not observation.startswith("ERROR:")
        self.state["last_ok"] = ok
        while self.steps:
            step = self.steps.pop(0)
            turn = step(observation, self.state)
            if turn is not None:
                return turn
        return say("policy exhausted after %d turns" % self.turns)


def swe_plan(files, test_file, fuzz_seed=0, fuzz_n=300, corpus_n=300, mutant_limit=0,
             oracle_n=100):
    """The loop: baseline tests -> fuzz (totality) -> oracle fuzz (differential,
    round 11) -> mutate -> kill -> re-test -> report."""
    def s_baseline(obs, st):
        return call("pytest", args="-q tests")

    def s_fuzz(obs, st):
        st["baseline"] = obs
        return call("fuzz", seed=fuzz_seed, n=fuzz_n)

    def s_oracle(obs, st):
        st["fuzz"] = obs
        return call("oracle_fuzz", seed=fuzz_seed, n=oracle_n)

    def s_mutate(obs, st):
        st["oracle"] = obs
        return call("mutate", files=files, limit=mutant_limit, workers=4)

    def s_kill(obs, st):
        st["mutation"] = obs
        if "survived   0" in obs and "SURVIVED" not in obs:
            st["skip_kill"] = True
            return None
        return call("kill_survivors", test_file=test_file, corpus_n=corpus_n)

    def s_retest(obs, st):
        if not st.get("skip_kill"):
            st["killers"] = obs
        return call("pytest", args="-q tests")

    def s_report(obs, st):
        st["retest"] = obs
        return say("SWE loop finished.\n\nFUZZ:\n%s\n\nORACLES:\n%s\n\nMUTATION:\n%s\n\nKILLERS:\n%s\n\nRETEST:\n%s"
                   % (st.get("fuzz", ""), st.get("oracle", ""), st.get("mutation", ""),
                      st.get("killers", "(none)"), obs))

    return [s_baseline, s_fuzz, s_oracle, s_mutate, s_kill, s_retest, s_report]

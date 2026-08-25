"""Completion guards (round 109): unit, corpus (recorded live answers from
rounds 101/107), and agent-loop integration."""
import json
import os

import pytest

from agentloop import (Agent, AgentConfig, CachingSimLLM, CallableGuard, Checkpoint,
                       EmptyAnswerGuard, JsonAnswerGuard, MockLLM, PatternGuard,
                       ProseToolCallGuard, ReadFileTool, SearchTool, SimCache, Tool,
                       ToolRegistry, ToolResult, TraceLogger, default_guards)
from agentloop.adapters import ClaudeCLILLM, TOOL_CALL_HINT
from agentloop.guards import (GuardContext, Rejection, _fit_schema, parse_python_call_args,
                              run_guards)
from agentloop.llm import AssistantTurn, FatalLLMError, text_turn, tool_turn

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "final_texts_r107.json")


# ------------------------------------------------------------ fakes ------

class _Spec(Tool):
    """A tool whose spec is the only thing that matters here."""
    def __init__(self, name, params, required, safe):
        self.name = name
        self.params = params
        self.required = list(required)
        self.parallel_safe = safe
        self.description = "fake %s" % name

    def run(self, **args):
        return ToolResult(True, "ran %s %s" % (self.name, json.dumps(args, sort_keys=True)))


def swe_like_registry():
    """The tool names the round-107 live lane offered."""
    return ToolRegistry([
        _Spec("read_file", {"path": {"type": "string"}, "start": {"type": "integer"},
                            "end": {"type": "integer"}}, ["path"], True),
        _Spec("search", {"query": {"type": "string"}, "path": {"type": "string"},
                         "context": {"type": "integer"}}, ["query"], True),
        _Spec("outline", {"path": {"type": "string"}}, ["path"], True),
        _Spec("mutant_diff", {"program": {"type": "string"}}, ["program"], False),
        _Spec("bash", {"command": {"type": "string"}}, ["command"], False),
    ])


def ctx_for(registry, hint=None):
    return GuardContext(tool_specs=registry.specs(), registry=registry, tool_call_hint=hint)


# ------------------------------------------------------------ parsing ----

def test_parse_python_call_args_handles_unquoted_paths_numbers_and_quotes():
    assert parse_python_call_args("path=whence/interp.py, start=1260, end=1320") == {
        "path": "whence/interp.py", "start": 1260, "end": 1320}
    assert parse_python_call_args('query="a, b", path=\'x/y\'') == {"query": "a, b", "path": "x/y"}
    assert parse_python_call_args("xs=[1, 2], flag=true, n=None") == {"xs": [1, 2], "flag": True, "n": None}
    assert parse_python_call_args("") == {}


def test_parse_python_call_args_refuses_positional_or_bad_names():
    assert parse_python_call_args("a, b") is None
    assert parse_python_call_args("query=a, b") is None
    assert parse_python_call_args("1x=2") is None


def test_fit_schema_coerces_scalars_and_rejects_unknown_or_missing():
    spec = swe_like_registry().get("read_file").spec()
    assert _fit_schema({"path": 123, "start": "12"}, spec) == {"path": "123", "start": 12}
    assert _fit_schema({"path": "p", "nope": 1}, spec) is None          # unknown key
    assert _fit_schema({"start": 1}, spec) is None                      # missing required
    assert _fit_schema({"path": "p", "start": True}, spec) is None      # bool is not an integer
    assert _fit_schema({"path": "p", "start": 3.0}, spec) == {"path": "p", "start": 3}


# ------------------------------------------------------------ prose guard -

@pytest.mark.parametrize("text, reason, name", [
    ("read_file(path=whence/interp.py, start=1260, end=1320)", "python_tool_call", "read_file"),
    ("tool call: search", "bare_tool_mention", "search"),
    ("Tool call: `outline`", "bare_tool_mention", "outline"),
    ("Let me look.\nsearch(query=\"_hleft\", context=3)", "python_tool_call", "search"),
    ('{"name": "read_file", "args": {"path": "a", "start": 1, "9}}\n```\nWait invalid JSON.',
     "malformed_json_tool_call", "read_file"),
    ('<tool_call>\n{"name": "search", "arguments": {"query": "x"}}\n</tool_call>', "xml_tool_call", "search"),
    ('<invoke name="read_file"><parameter name="path">a</parameter></invoke>', "xml_tool_call", "read_file"),
])
def test_prose_guard_detects_each_observed_shape(text, reason, name):
    g = ProseToolCallGuard(recover=False)
    hit = g.detect(text, ctx_for(swe_like_registry()))
    assert hit is not None and hit[0] == reason and hit[1] == name
    r = g.check(text, ctx_for(swe_like_registry()))
    assert isinstance(r, Rejection) and not r.recovered and r.reason == reason
    assert "NOTHING was run" in r.message and name in r.message


@pytest.mark.parametrize("text", [
    "The bug is in binop; I used read_file to confirm it. Verdict: equivalent.",
    "```json\n{\"verdict\": \"equivalent\", \"program\": null, \"argument\": \"read_file showed the gate\"}\n```",
    '```json\n{"claims": [{"name": "read_file", "title": "x"}]}\n```',
    "search(query) is the API; the answer is 42.",           # positional prose, not the whole text
    "Done. Files: 3.",
    "outline",                                                # a bare word that happens to be a tool name
    "Call me maybe: totals(3)",                               # unknown tool
])
def test_prose_guard_accepts_ordinary_answers(text):
    assert ProseToolCallGuard().check(text, ctx_for(swe_like_registry())) is None


def test_prose_guard_recovers_python_call_against_a_safe_tool():
    r = ProseToolCallGuard().check("read_file(path=whence/interp.py, start=1260, end=1320)",
                                   ctx_for(swe_like_registry()))
    assert r.recovered and len(r.calls) == 1
    call = r.calls[0]
    assert call.name == "read_file"
    assert call.args == {"path": "whence/interp.py", "start": 1260, "end": 1320}
    assert call.call_id


def test_prose_guard_recovers_a_valid_json_object_with_commentary():
    text = 'Let me read it.\n{"name": "search", "args": {"query": "_hleft", "context": 2}}\nThen I will decide.'
    r = ProseToolCallGuard().check(text, ctx_for(swe_like_registry()))
    assert r.recovered and r.calls[0].name == "search"
    assert r.calls[0].args == {"query": "_hleft", "context": 2}


@pytest.mark.parametrize("text", [
    "bash(command=rm -rf x)",                       # not parallel_safe
    "mutant_diff(program=let a = 1)",               # not parallel_safe
    "read_file(path=a, lines=3)",                   # unknown argument
    "read_file(start=3)",                           # missing required
    "search(query=a, b)",                           # positional
    "tool call: search",                            # no args and query is required
])
def test_prose_guard_refuses_to_guess_and_nudges_instead(text):
    r = ProseToolCallGuard().check(text, ctx_for(swe_like_registry()))
    assert r is not None and not r.recovered
    assert r.message


def test_prose_guard_recover_unsafe_opt_in():
    r = ProseToolCallGuard(recover_unsafe=True).check("mutant_diff(program=let a = 1)",
                                                      ctx_for(swe_like_registry()))
    assert r.recovered and r.calls[0].args == {"program": "let a = 1"}


def test_bare_mention_recovers_when_the_tool_needs_no_arguments():
    reg = ToolRegistry([_Spec("list_dir", {"path": {"type": "string"}}, [], True)])
    r = ProseToolCallGuard().check("tool call: list_dir", ctx_for(reg))
    assert r.recovered and r.calls[0].args == {}


def test_nudge_quotes_the_backend_hint_when_it_has_one():
    reg = swe_like_registry()
    r = ProseToolCallGuard(recover=False).check("tool call: search", ctx_for(reg, ClaudeCLILLM.tool_call_hint))
    assert TOOL_CALL_HINT.splitlines()[1] in r.message       # the ```tool line
    r2 = ProseToolCallGuard(recover=False).check("tool call: search", ctx_for(reg))
    assert "structured tool-calling interface" in r2.message


# ------------------------------------------------------------ other guards

def test_empty_guard():
    g = EmptyAnswerGuard()
    assert g.check("  \n", ctx_for(swe_like_registry())).reason == "empty"
    assert g.check("x", ctx_for(swe_like_registry())) is None


def test_json_answer_guard_reasons_and_last_block_wins():
    g = JsonAnswerGuard(["verdict", "program"])
    c = ctx_for(swe_like_registry())
    assert g.check("no json here", c).reason == "no_json_answer"
    assert g.check("```json\n{\"verdict\": \"killed\"}\n```", c).reason == "missing_keys"
    ok = "draft:\n```json\n{\"verdict\": 1}\n```\nfinal:\n```json\n{\"verdict\": \"killed\", \"program\": \"let a = 1\"}\n```"
    assert g.check(ok, c) is None
    assert g.extract(ok)["program"] == "let a = 1"
    # a bare object is only accepted when asked for
    bare = 'answer: {"verdict": "equivalent", "program": null}'
    assert g.check(bare, c).reason == "no_json_answer"
    assert JsonAnswerGuard(["verdict"], allow_bare=True).check(bare, c) is None
    # an unfenced ```json block with trailing prose inside the fence still parses
    messy = "```json\n{\"verdict\": \"killed\", \"program\": \"p\"}\ntrailing\n```"
    assert g.check(messy, c) is None


def test_json_answer_guard_validate_hook_and_message_format():
    def validate(obj):
        if obj["verdict"] == "killed" and not obj.get("program"):
            return "verdict is killed but program is empty"
    g = JsonAnswerGuard(["verdict"], validate=validate, example='```json\n{"verdict": "..."}\n```')
    r = g.check("```json\n{\"verdict\": \"killed\", \"program\": null}\n```", ctx_for(swe_like_registry()))
    assert r.reason == "invalid_answer" and "program is empty" in r.message
    assert "keys: verdict" in r.message and '{"verdict": "..."}' in r.message


def test_pattern_and_callable_guards():
    c = ctx_for(swe_like_registry())
    p = PatternGuard(r"files:\s*\d+", "Say 'files: N'.", name="files_line")
    assert p.check("files: 3", c) is None
    assert p.check("three files", c).guard == "files_line"
    cg = CallableGuard(lambda t, ctx: "too short" if len(t) < 5 else None, name="len")
    assert cg.check("hi", c).message == "too short" and cg.check("hello!", c) is None


def test_run_guards_first_rejection_wins_and_crashes_are_skipped():
    crashes = []

    def boom(t, ctx):
        raise RuntimeError("guard bug")

    guards = [CallableGuard(boom, "boom"), EmptyAnswerGuard(), PatternGuard("x", "need x")]
    r = run_guards(guards, "", ctx_for(swe_like_registry()), on_crash=lambda g, e: crashes.append(g.name))
    assert r.guard == "empty_answer" and crashes == ["boom"]
    assert run_guards(guards, "x", ctx_for(swe_like_registry())) is None


# ------------------------------------------------------------ corpus -----

def _corpus():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_corpus_default_guards_reject_exactly_the_recorded_failures():
    """16 final answers recorded by the round-107/101 live lanes (8 kill, 6
    repair, 2 review). The five that round 107 hand-classified as protocol
    failures must be rejected; the eleven real answers must pass."""
    reg = swe_like_registry()
    c = ctx_for(reg, ClaudeCLILLM.tool_call_hint)
    rejected, recovered = {}, {}
    for rec in _corpus():
        r = run_guards(default_guards(), rec["final_text"], c)
        if r is not None:
            rejected[rec["id"]] = r.reason
            if r.recovered:
                recovered[rec["id"]] = [(x.name, x.args) for x in r.calls]
    expected = {rec["id"] for rec in _corpus() if rec["expect_reject"]}
    assert set(rejected) == expected, (rejected, expected)
    assert rejected["interp.py:1291:arith#566"] == "python_tool_call"
    assert rejected["interp.py:970:bool#303"] == "bare_tool_mention"
    assert rejected["interp.py:924:const#521"] == "malformed_json_tool_call"
    assert rejected["interp.py:409:ifneg#75"] == "empty"
    # the python-style one is dispatchable as written
    assert recovered["interp.py:1291:arith#566"] == [
        ("read_file", {"path": "whence/interp.py", "start": 1260, "end": 1320})]


def test_corpus_json_guards_accept_every_real_kill_and_repair_answer():
    keys = {"kill": ["verdict"], "repair": ["root_cause"], "review": ["claims"]}
    c = ctx_for(swe_like_registry())
    checked = 0
    for rec in _corpus():
        if rec["expect_reject"]:
            continue
        if "```json" not in rec["final_text"]:
            # the lane stored final_text[-1500:]; two long kill answers lost
            # their opening fence to that truncation (fixture artifact, not
            # a guard miss — decided test-wrong on first run, round 109)
            continue
        checked += 1
        g = JsonAnswerGuard(keys[rec["task"]])
        assert g.check(rec["final_text"], c) is None, (rec["id"], rec["final_text"][-200:])
    assert checked >= 8, checked


# ------------------------------------------------------------ loop -------

def run_agent(script, registry=None, trace=None, **cfg):
    registry = registry or swe_like_registry()
    llm = MockLLM(script)
    trace = trace or TraceLogger()
    agent = Agent(llm, registry, AgentConfig(**cfg), trace=trace)
    return agent.run("task"), llm, trace


def test_no_guards_is_pre109_behaviour():
    r, llm, _ = run_agent([text_turn("tool call: search")])
    assert r.ok and r.final_text == "tool call: search" and r.guard_rejections == 0


def test_rejection_appends_nudge_and_continues():
    r, llm, trace = run_agent([text_turn("tool call: search"), text_turn("done")],
                              guards=default_guards())
    assert r.ok and r.final_text == "done" and r.steps == 2
    assert r.guard_rejections == 1 and r.guard_recoveries == 0
    last = llm.requests[1]["messages"][-1]
    assert last["role"] == "user" and "NOTHING was run" in last["content"]
    assert llm.requests[1]["messages"][-2]["content"] == "tool call: search"
    ev = [e for e in trace.events if e["event"] == "guard_rejected"]
    assert ev == [dict(ev[0], step=1, guard="prose_tool_call", reason="bare_tool_mention", retries_left=1)]
    end = [e for e in trace.events if e["event"] == "run_end"][0]
    assert end["guard_rejections"] == 1


def test_recovery_dispatches_the_parsed_call_and_records_it(tmp_path):
    (tmp_path / "a.txt").write_text("hello from a\n")
    reg = ToolRegistry([ReadFileTool(str(tmp_path)), SearchTool(str(tmp_path))])
    r, llm, trace = run_agent([text_turn("read_file(path=a.txt)"), text_turn("done")],
                              registry=reg, guards=default_guards())
    assert r.ok and r.tool_calls == 1 and r.guard_recoveries == 1 and r.guard_rejections == 0
    msgs = llm.requests[1]["messages"]
    assert msgs[-2]["role"] == "assistant" and msgs[-2]["tool_calls"][0]["name"] == "read_file"
    assert msgs[-2]["content"] == "read_file(path=a.txt)"       # the prose is kept verbatim
    assert msgs[-1]["role"] == "tool" and "hello from a" in msgs[-1]["content"]
    assert msgs[-1]["tool_call_id"] == msgs[-2]["tool_calls"][0]["call_id"]
    kinds = [e["event"] for e in trace.events]
    assert "guard_recovered" in kinds and kinds.index("guard_recovered") < kinds.index("tool_call")
    rec = [e for e in trace.events if e["event"] == "guard_recovered"][0]
    assert rec["calls"] == ["read_file"] and rec["reason"] == "python_tool_call"


def test_recovery_extends_provider_blocks_so_the_tool_result_has_a_partner(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    reg = ToolRegistry([ReadFileTool(str(tmp_path))])
    turn = AssistantTurn(text="read_file(path=a.txt)",
                         raw_content=[{"type": "text", "text": "read_file(path=a.txt)"}])
    r, llm, _ = run_agent([turn, text_turn("done")], registry=reg, guards=default_guards())
    assert r.ok
    a = llm.requests[1]["messages"][-2]
    assert a["raw_content"][0]["type"] == "text"
    assert a["raw_content"][1] == {"type": "tool_use", "id": a["tool_calls"][0]["call_id"],
                                   "name": "read_file", "input": {"path": "a.txt"}}


def test_retries_exhausted_ends_rejected_with_the_nudge_in_the_transcript():
    r, llm, trace = run_agent([text_turn(""), text_turn("tool call: search"), text_turn("")],
                              guards=default_guards(), max_guard_retries=2)
    assert r.stop_reason == "rejected" and not r.ok
    assert r.steps == 3 and r.guard_rejections == 3
    assert r.error == "empty_answer: empty"
    assert r.messages[-1]["role"] == "user" and "empty" in r.messages[-1]["content"]
    assert [e["retries_left"] for e in trace.events if e["event"] == "guard_rejected"] == [1, 0, -1]


def test_guard_counters_persist_through_checkpoint_resume(tmp_path):
    ck = Checkpoint(str(tmp_path / "ck.json"))
    reg = swe_like_registry()
    cfg = AgentConfig(guards=default_guards(), max_guard_retries=1)

    class Dies(MockLLM):
        def complete(self, messages, tools):
            if self.calls_made == 1:
                raise FatalLLMError("outage")
            return super().complete(messages, tools)

    first = Agent(Dies([text_turn("tool call: search")]), reg, cfg).run("task", checkpoint=ck)
    assert first.stop_reason == "llm_error" and first.guard_rejections == 1
    st = ck.load()
    assert st["guard_rejections"] == 1 and st["messages"][-1]["role"] == "user"
    second = Agent(MockLLM([text_turn("")]), reg, cfg).run("task", checkpoint=ck)
    # steps counts attempted completions (the failed one included), as the
    # checkpoint tests already pin: the outage was step 2, so resume at 2.
    assert second.resumed_from == 2 and second.steps == 3
    assert second.stop_reason == "rejected" and second.guard_rejections == 2


def test_json_guard_nudge_carries_the_format_and_the_next_answer_completes():
    g = JsonAnswerGuard(["files", "total_words"], example='```json\n{"files": 3, "total_words": 22}\n```')
    r, llm, _ = run_agent([text_turn("There are 3 files with 22 words."),
                           text_turn("```json\n{\"files\": 3, \"total_words\": 22}\n```")],
                          guards=default_guards() + [g])
    assert r.ok and r.guard_rejections == 1
    nudge = llm.requests[1]["messages"][-1]["content"]
    assert "files, total_words" in nudge and '"total_words": 22' in nudge


def test_wrap_up_answer_is_not_guarded():
    r, _, _ = run_agent([tool_turn("outline", path="x"), text_turn("")],
                        guards=default_guards(), max_steps=1, wrap_up_on_max_steps=True)
    assert r.stop_reason == "max_steps" and r.guard_rejections == 0 and r.final_text == ""


def test_max_steps_can_end_a_run_that_was_being_nudged():
    r, _, _ = run_agent([text_turn("tool call: search")], guards=default_guards(), max_steps=1)
    assert r.stop_reason == "max_steps" and r.guard_rejections == 1


def test_guard_crash_is_logged_and_the_answer_accepted():
    def boom(t, ctx):
        raise ValueError("bug")

    r, _, trace = run_agent([text_turn("fine")], guards=[CallableGuard(boom, "boom")])
    assert r.ok and r.final_text == "fine"
    ev = [e for e in trace.events if e["event"] == "guard_crashed"]
    assert len(ev) == 1 and ev[0]["guard"] == "boom" and "bug" in ev[0]["error"]


def test_nudge_step_is_almost_entirely_cache_read_in_the_simulator():
    """P8: the corrective message is appended after an unchanged prefix, so
    the retry completion reads the whole previous request from cache. The
    ratio scales with the prefix: 0.917 at a 5 k-char toy prefix (first
    run), >= 0.95 from ~9 k chars; the live lane's prefix is ~170 k chars."""
    cache = SimCache()
    inner = MockLLM([text_turn("tool call: search"), text_turn("done")])
    llm = CachingSimLLM(inner, cache=cache)
    trace = TraceLogger()
    reg = swe_like_registry()
    r = Agent(llm, reg, AgentConfig(guards=default_guards(),
                                    system_prompt="x" * 20000), trace=trace).run("t")
    assert r.ok and r.guard_rejections == 1
    resp = [e for e in trace.events if e["event"] == "llm_response"]
    u = resp[1]["usage"]
    hit = u["cache_read_input_tokens"] / float(u["cache_read_input_tokens"] + u["cache_creation_input_tokens"])
    assert hit >= 0.95, hit

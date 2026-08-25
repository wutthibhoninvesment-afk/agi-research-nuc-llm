"""Offline tests for Errand (nuc/taskscript): lexer, parser/link discipline,
interpreter semantics (values, preflight, budgets, retries, telemetry),
transports with fakes, CLI exit codes, shipped examples in dry mode."""
import json
import os
import subprocess
import sys
import urllib.error
from io import BytesIO

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
NUC = os.path.dirname(HERE)
sys.path.insert(0, NUC)

from taskscript import lexer as L  # noqa: E402
from taskscript import parser as P  # noqa: E402
from taskscript import interp as I  # noqa: E402
from taskscript import transport as T  # noqa: E402

EX = os.path.join(NUC, "taskscript", "examples")
RUN = os.path.join(NUC, "taskscript", "run.py")

LANES = '''
lane qwen  { url "http://127.0.0.1:8080" model "qwen36-tools" prefill e1 decode 3.3 fixed 2.4s tools yes ctx 32768 }
lane small { url "http://127.0.0.1:8090" model "olmoe" prefill 10 decode 2 fixed 1s ctx 2048 }
budget quick { time 30s tokens 500 }
budget long  { time 10m }
'''


def prog(extra: str) -> P.Program:
    return P.parse(LANES + extra)


class FakeClock:
    def __init__(self):
        self.t = 100.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


class TimedMock(T.MockTransport):
    """A mock that advances a fake clock by a scripted duration per reply."""
    def __init__(self, replies, clock: FakeClock, seconds=1.0):
        super().__init__(replies)
        self.clock = clock
        self.seconds = seconds

    def send(self, lane, request, timeout_s):
        self.clock.t += self.seconds
        return super().send(lane, request, timeout_s)


# ----------------------------------------------------------------- lexer

def test_lexer_tokens_durations_strings_and_newlines():
    toks = L.tokenize('lane q { fixed 2.4s time 2m }\n\n# c\nflow f(a,\n b) { let x = f(a) == "y\\n{z}" }')
    types = [t.type for t in toks]
    assert types[0] == "NAME" and "NEWLINE" in types and types[-1] == "EOF"
    assert types[types.index("NEWLINE")] == "NEWLINE" and types.count("NEWLINE") == 2  # collapsed + none inside ( )
    durations = [t.value for t in toks if t.type == "DURATION"]
    assert durations == [pytest.approx(2.4), 120.0]
    s = [t for t in toks if t.type == "STRING"][0]
    assert s.value == "y\n{z}" and s.line == 5


@pytest.mark.parametrize("src,msg", [
    ('"open', "unterminated"), ('"\\q"', "bad escape"), ("3x", "unknown duration unit"), ("@", "unexpected character"),
])
def test_lexer_errors(src, msg):
    with pytest.raises(L.LexError) as ex:
        L.tokenize(src)
    assert msg in str(ex.value)


def test_lexer_positions():
    toks = L.tokenize("a\n  bb ==")
    assert (toks[2].value, toks[2].line, toks[2].col) == ("bb", 2, 3)
    assert toks[3].type == "EQEQ" and toks[3].col == 6


# ----------------------------------------------------------------- parser + link

def test_parse_shapes():
    p = prog('''
task t(a, b) on small within quick retry 2 backoff 500ms {
  system "s {a}"
  user "u {b}"
  reply 8
  expect one_of "x" "y"
}
flow f(a) within long { let k = t(a, "z") rescue "y"
  if k == "x" { emit 1 } else if k != "y" { emit 2 } else { emit why(k) } }
''')
    t = p.tasks["t"]
    assert (t.retry, t.backoff_s, t.reply, t.budget, t.lane) == (2, 0.5, 8, "quick", "small")
    assert t.user.parts == ["u ", ("b",)] and t.expect.kind == "one_of" and t.expect.args == ["x", "y"]
    assert p.lanes["qwen"].prefill == "e1" and p.lanes["small"].prefill == 10.0 and p.lanes["qwen"].tools
    assert p.budgets["quick"].tokens == 500 and p.budgets["long"].time_s == 600.0
    f = p.flows["f"]
    assert isinstance(f.body[0], P.Let) and isinstance(f.body[0].expr, P.Rescue)
    inner = f.body[1]
    assert isinstance(inner, P.If) and isinstance(inner.else_[0], P.If)


def test_interpolation_splitting():
    assert P.split_interpolation("a {x} b {{c}} {y}", 1) == ["a ", ("x",), " b {c} ", ("y",)]
    assert P.split_interpolation("", 1) == [""]
    with pytest.raises(P.ParseError):
        P.split_interpolation("a } b", 1)


@pytest.mark.parametrize("src,msg", [
    ('lane g { url "http://127.0.0.1:8001" prefill 1 decode 1 }', "frontier lane"),
    ('lane g { url "http://h:8001/v1" prefill 1 decode 1 }', "frontier lane"),
    ('lane g { url "ftp://h" prefill 1 decode 1 }', "url must be http"),
    ('lane g { url "http://h" decode 1 }', "needs prefill"),
    ('lane g { url "http://h" prefill 1 decode 0 }', "must be positive"),
    ('lane g { url "http://h" prefill 1 decode 1 bogus 2 }', "unknown lane key"),
    ('lane g { url "http://h" url "http://h" prefill 1 decode 1 }', "duplicate lane key"),
    ('budget b { }', "declares nothing"),
    ('budget b { time 0s }', "must be positive"),
    ('budget b { time 1s time 2s }', "duplicate time"),
    ('task t() on nope { user "u" }', "unknown lane"),
    ('task t() on small within nope { user "u" }', "unknown budget"),
    ('task t() on small { system "s" }', "needs a user prompt"),
    ('task t(a) on small { user "{b}" }', "not a parameter"),
    ('task t(a, a) on small { user "u" }', "duplicate parameter"),
    ('task t() on small { user "u" reply 0 }', "reply must be"),
    ('task t() on small { user "u" reply 4096 }', "cannot fit lane"),
    ('task t() on small { user "u" expect one_of }', "at least one string"),
    ('task why() on small { user "u" }', "shadows a builtin"),
    ('task t() on small { user "u" }\ntask t() on small { user "u" }', "duplicate task"),
    ('flow f() { emit x }', "not bound"),
    ('flow f() { emit "{x}" }', "not bound"),
    ('flow f(a) { let a = 1 }', "already bound"),
    ('flow f() { emit nope() }', "unknown task/flow/builtin"),
    ('task t(a) on small { user "x" }\nflow f() { emit t() }', "takes 1 argument"),
    ('flow f() { emit why(1, 2) }', "takes 1 argument"),
    ('flow f() { emit 1 == 2 == 3 }', "chained comparison"),
    ('flow f() { emit }', "expected an expression"),
    ('flow f() { let = 1 }', "expected"),
    ('flow f() { emit let }', "unexpected keyword"),
    ('flow f() within nope { emit 1 }', "unknown budget"),
    ('task t() on small { user "u" }\nflow t() { emit 1 }', "collides"),
    ('flow f() { emit 1 } trailing', "expected lane/budget/task/flow"),
    ('flow f() { emit "a {" }', "lone"),
])
def test_parse_and_link_errors(src, msg):
    with pytest.raises(P.ParseError) as ex:
        P.parse(LANES + src)
    assert msg in str(ex.value)


def test_shadowing_in_inner_block_is_allowed_but_same_block_is_not():
    p = prog('flow f(a) { if true { let b = 1 } else { let b = 2 }\n let b = 3\n emit b }')
    assert "f" in p.flows
    with pytest.raises(P.ParseError):
        prog('flow f(a) { let b = 1\n if true { emit 1 }\n let b = 2 }')


# ----------------------------------------------------------------- projection + preflight

def test_project_uses_e1_curve_for_qwen_and_rates_otherwise():
    p = prog("")
    q = I.project(p.lanes["qwen"], 134, 33)
    assert q.ttft_s == pytest.approx(23.3) and q.decode_s == pytest.approx(10.0)
    s = I.project(p.lanes["small"], 100, 20)
    assert s.ttft_s == pytest.approx(11.0) and s.total_s == pytest.approx(21.0)


def test_chars_tokenizer_estimate():
    t = I.CharsTokenizer(4.0, per_message=5)
    assert t.count("") == 5 and t.count("abcd") == 6 and t.count("abcde") == 7


def run(src, replies=None, args=None, flow="f", **kw):
    p = prog(src)
    tr = T.MockTransport(replies or {})
    it = I.Interp(p, tr, clock=lambda: 0.0, sleep=lambda s: None, rng=lambda: 0.5, **kw)
    return it, it.run_flow(flow, args or {})


def test_preflight_refuses_over_time_budget_without_sending():
    it, res = run('task t(x) on qwen within quick { user "{x}" reply 200 }\nflow f() { emit t("hello") }')
    v = res.emitted[0]
    assert isinstance(v, I.Miss) and "preflight" in v.reasons[0] and "> budget quick" in v.reasons[0]
    assert it.transport.requests == [] and v.prov["refused"] is True
    pre = [e for e in it.events if e["ev"] == "preflight"][0]
    assert pre["ok"] is False and pre["projected_s"] > 30 and not res.ok


def test_preflight_token_and_ctx_caps():
    big = "x" * 8400                                    # 2105 tokens at 4 chars/token + frame
    it, res = run('task t(x) on small within quick { user "{x}" reply 10 }\nflow f() { emit t("%s") }' % big)
    assert "exceed lane small ctx 2048" in res.emitted[0].reasons[0]
    it, res = run('task t(x) on small within quick { user "{x}" reply 10 }\nflow f() { emit t("%s") }' % ("x" * 2400))
    assert "exceed budget quick tokens 500" in res.emitted[0].reasons[0]
    assert it.transport.requests == []


def test_task_ok_carries_trail_and_request_shape():
    it, res = run('task t(x) on small { system "S" user "Q {x}?" reply 5 }\nflow f() { emit t("k") }',
                  {"olmoe": [{"text": "A", "prompt_tokens": 12, "completion_tokens": 3}]})
    v = res.emitted[0]
    assert isinstance(v, I.Ok) and v.value == "A"
    assert v.prov["task"] == "t" and v.prov["lane"] == "small" and v.prov["attempts"][0]["tokens_in"] == 12
    req = it.transport.requests[0]["request"]
    assert req["messages"] == [{"role": "system", "content": "S"}, {"role": "user", "content": "Q k?"}]
    assert req["max_tokens"] == 5 and req["model"] == "olmoe" and res.ok
    assert res.ledger["tokens_in"] == 12 and res.ledger["tokens_out"] == 3 and res.ledger["per_lane"]["small"]["calls"] == 1


def test_expect_kinds():
    e = P.Expect("one_of", ["bug", "feature"], 1)
    assert I.check_expect(e, " Bug.\n") == (True, "bug")
    assert I.check_expect(e, "feature, because") == (True, "feature")
    assert I.check_expect(e, "neither")[0] is False
    assert I.check_expect(P.Expect("contains", ["ok"], 1), "all ok") == (True, "all ok")
    assert I.check_expect(P.Expect("nonempty", [], 1), "  ")[0] is False
    assert I.check_expect(P.Expect("json", [], 1), '{"a": 1}')[0] is True
    assert I.check_expect(P.Expect("json", [], 1), "{")[0] is False
    assert I.check_expect(None, "raw") == (True, "raw")


def test_retry_on_expect_failure_then_success_with_jittered_backoff():
    clock = FakeClock()
    p = prog('task t() on small retry 2 backoff 2s { user "u" reply 4 expect one_of "yes" "no" }\nflow f() { emit t() }')
    tr = TimedMock({"olmoe": ["maybe", "YES"]}, clock, seconds=1.5)
    it = I.Interp(p, tr, clock=clock.now, sleep=clock.sleep, rng=lambda: 0.75)
    res = it.run_flow("f", {})
    v = res.emitted[0]
    assert isinstance(v, I.Ok) and v.value == "yes" and len(v.prov["attempts"]) == 2
    assert clock.slept == [pytest.approx(2.0 * 1.25)]                  # backoff * (0.5 + rng)
    kinds = [e["ev"] for e in it.events]
    assert kinds == ["flow_start", "preflight", "attempt", "retry", "attempt", "result", "flow_end"]
    assert res.ledger["spent_s"] == pytest.approx(1.5 + 2.5 + 1.5)      # wait time is spent time


def test_retry_exponential_and_gives_up():
    clock = FakeClock()
    p = prog('task t() on small retry 3 backoff 1s { user "u" reply 4 }\nflow f() { emit t() }')
    boom = [T.TransportError("503", status=503, retryable=True) for _ in range(4)]
    tr = TimedMock({"olmoe": boom}, clock, seconds=0.5)
    it = I.Interp(p, tr, clock=clock.now, sleep=clock.sleep, rng=lambda: 0.5)
    res = it.run_flow("f", {})
    v = res.emitted[0]
    assert isinstance(v, I.Miss) and "gave up after attempt 4" in v.reasons[0]
    assert clock.slept == [1.0, 2.0, 4.0] and len(v.prov["attempts"]) == 4


def test_non_retryable_failure_is_final():
    it, res = run('task t() on small retry 3 { user "u" }\nflow f() { emit t() }',
                  {"olmoe": [T.TransportError("HTTP 400", status=400, retryable=False), "never"]})
    v = res.emitted[0]
    assert isinstance(v, I.Miss) and "final failure at attempt 1" in v.reasons[0]
    assert len(it.transport.requests) == 1


def test_retry_refused_when_budget_cannot_fit_another_attempt():
    clock = FakeClock()
    # small lane: 1 + 8/10 + 4/2 = 3.8 s projected; quick = 30 s; attempt takes 12 s, backoff 20 s -> 20+3.8 > 30-12
    p = prog('task t() on small within quick retry 3 backoff 20s { user "uuuuuuuuuuuu" reply 4 }\nflow f() { emit t() }')
    tr = TimedMock({"olmoe": [T.TransportError("timeout", retryable=True)] * 4}, clock, seconds=12.0)
    it = I.Interp(p, tr, clock=clock.now, sleep=clock.sleep, rng=lambda: 0.5)
    res = it.run_flow("f", {})
    v = res.emitted[0]
    assert isinstance(v, I.Miss) and "no budget for attempt 2" in v.reasons[0] and "quick" in v.reasons[0]
    assert clock.slept == [] and len(it.transport.requests) == 1


def test_flow_budget_is_consumed_across_tasks_and_timeout_is_remaining():
    clock = FakeClock()
    p = prog('task t() on small { user "u" reply 4 }\nflow f() within quick { emit t()\n emit t()\n emit t() }')
    tr = TimedMock({"olmoe": ["a", "b", "c"]}, clock, seconds=14.0)   # each call overruns its 3.8 s projection
    it = I.Interp(p, tr, clock=clock.now, sleep=clock.sleep, rng=lambda: 0.5)
    res = it.run_flow("f", {})
    assert [type(v).__name__ for v in res.emitted] == ["Ok", "Ok", "Miss"]
    assert "remaining 2.0 s" in res.emitted[2].reasons[0]
    assert [r["timeout_s"] for r in tr.requests] == [30.0, 16.0]      # the transport timeout IS the remaining budget
    assert res.ledger["spent_s"] == 28.0 and res.ledger["remaining_s"] == 2.0 and res.ledger["budget"] == "quick"


def test_nested_flow_shares_parent_budget():
    clock = FakeClock()
    p = prog('task t() on small { user "u" reply 40 }\nflow inner() within long { emit t() }\n'   # 21.6 s projected
             'flow f() within quick { let a = inner()\n emit a\n emit inner() }')
    tr = TimedMock({"olmoe": ["x", "y"]}, clock, seconds=20.0)
    it = I.Interp(p, tr, clock=clock.now, sleep=clock.sleep, rng=lambda: 0.5)
    res = it.run_flow("f", {})
    assert isinstance(res.emitted[0], I.Ok) and res.emitted[0].value == "x" and res.emitted[0].prov["kind"] == "flow"
    assert isinstance(res.emitted[1], I.Miss) and "remaining 10.0 s" in res.emitted[1].reasons[0]
    assert res.ledger["spent_s"] == 20.0


def test_values_rescue_cmp_if_miss_and_builtins():
    src = '''task t() on small { user "u" reply 4 }
flow f() {
  let m = t()
  let r = m rescue "fallback"
  emit r
  emit missed(m)
  emit missed(r)
  emit (m == "x") rescue "cmp-missed"
  emit len(trim(lower(" AbC ")))
  emit len(1)
  emit "{r}!"
  emit 1 == 1.0
  emit "a" != "b"
}'''
    it, res = run(src, {"olmoe": [T.TransportError("down", retryable=False)]})
    vals = [I.render(v) for v in res.emitted]
    assert vals[0] == "fallback" and vals[1] == "true" and vals[2] == "false" and vals[3] == "cmp-missed"
    assert vals[4] == "3" and vals[5].startswith("miss(len at line") and vals[6] == "fallback!"
    assert vals[7] == "false" and vals[8] == "true"                      # 1 == 1.0 is false: types differ
    assert res.emitted[0].prov["kind"] == "rescue" and res.emitted[0].prov["recovered"]["ok"] is False
    assert res.miss is None and not res.ok                               # a miss was emitted (len(1))


def test_if_on_miss_or_non_bool_ends_flow():
    it, res = run('task t() on small { user "u" }\nflow f() { emit 1\n if t() { emit 2 }\n emit 3 }',
                  {"olmoe": [T.TransportError("down", retryable=False)]})
    assert len(res.emitted) == 1 and res.miss is not None and "condition missed" in res.miss.reasons[0]
    it, res = run('flow f() { if "yes" { emit 2 } }')
    assert "not a boolean" in res.miss.reasons[0]
    assert it.events[-1]["ev"] == "flow_end" and it.events[-1]["ok"] is False


def test_why_renders_trail_json():
    it, res = run('task t(x) on small { user "{x}" reply 4 }\nflow f() { let a = t("q")\n emit why(a) }', {"olmoe": ["r"]})
    w = json.loads(res.emitted[0].value)
    assert w["ok"] is True and w["value"] == "r" and w["prov"]["task"] == "t"
    assert w["prov"]["inputs"][0]["value"] == "q" and w["prov"]["attempts"][0]["n"] == 1


def test_flow_call_propagates_miss_and_arguments():
    it, res = run('flow g(a) { emit "{a}" }\nflow f() { emit g("v")\n emit g(len(1)) }')
    assert I.render(res.emitted[0]) == "v"
    assert isinstance(res.emitted[1], I.Miss) and "argument 1 missed" in res.emitted[1].reasons[0]
    it, res = run('flow g() { let a = 1 }\nflow f() { emit g() }')
    assert "emitted nothing" in res.emitted[0].reasons[0]


def test_run_flow_argument_checks_and_param_values():
    p = prog('flow f(a, b) { emit "{a}{b}" }')
    it = I.Interp(p, T.MockTransport())
    with pytest.raises(KeyError):
        it.run_flow("f", {"a": 1})
    with pytest.raises(KeyError):
        it.run_flow("nope", {})
    res = it.run_flow("f", {"a": "x", "b": I.Ok("y")})
    assert res.emitted[0].value == "xy" and res.emitted[0].prov["inputs"][0]["prov"]["kind"] == "param"


def test_dry_run_charges_projection_and_skips_expect():
    p = prog('task t(x) on small within quick { user "{x}" reply 4 expect one_of "bug" "feature" }\n'
             'flow f() within long { let k = t("hi")\n emit k\n emit t("again") }')
    it = I.Interp(p, T.DryTransport(), dry_run=True)
    res = it.run_flow("f", {})
    assert res.emitted[0].value == "bug" and res.ok
    # fixed + tokens/prefill + reply/decode: "hi" = 6 tokens, "again" = 7 tokens (chars/4 rounded up + 5 frame)
    assert res.ledger["spent_s"] == pytest.approx((1 + 6 / 10 + 2.0) + (1 + 7 / 10 + 2.0))
    assert res.emitted[0].prov["seconds"] == pytest.approx(res.emitted[0].prov["projected_s"])


# ----------------------------------------------------------------- transports

def test_mock_transport_fallback_key_and_exhaustion():
    lane = prog("").lanes["small"]
    m = T.MockTransport({"*": ["one"]})
    assert m.send(lane, {}, 1.0).text == "one"
    with pytest.raises(T.TransportError) as ex:
        m.send(lane, {}, 1.0)
    assert ex.value.retryable is False


def test_mock_transport_from_file(tmp_path):
    f = tmp_path / "m.json"
    f.write_text(json.dumps({"olmoe": ["a", {"text": "b", "status": 200}]}))
    m = T.MockTransport.from_file(str(f))
    assert m.replies["olmoe"][1]["text"] == "b"
    f.write_text("[1]")
    with pytest.raises(T.TransportError):
        T.MockTransport.from_file(str(f))


class FakeResp:
    def __init__(self, body: dict, status=200):
        self.body, self.status = json.dumps(body).encode(), status

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_http_transport_request_and_usage():
    seen = {}

    def opener(req, timeout):
        seen["url"], seen["timeout"], seen["body"] = req.full_url, timeout, json.loads(req.data)
        return FakeResp({"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 9, "completion_tokens": 2}})

    lane = prog("").lanes["small"]
    r = T.HTTPTransport(opener=opener).send(lane, {"model": "olmoe"}, 12.5)
    assert (r.text, r.prompt_tokens, r.completion_tokens) == ("hi", 9, 2)
    assert seen["url"] == "http://127.0.0.1:8090/v1/chat/completions" and seen["timeout"] == 12.5


@pytest.mark.parametrize("code,retryable", [(400, False), (404, False), (408, True), (429, True), (500, True), (503, True)])
def test_http_transport_status_classification(code, retryable):
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, BytesIO(b"detail"))

    with pytest.raises(T.TransportError) as ex:
        T.HTTPTransport(opener=opener).send(prog("").lanes["small"], {}, 1.0)
    assert ex.value.status == code and ex.value.retryable is retryable and "detail" in str(ex.value)


def test_http_transport_connection_error_and_bad_body():
    def down(req, timeout):
        raise urllib.error.URLError("refused")

    with pytest.raises(T.TransportError) as ex:
        T.HTTPTransport(opener=down).send(prog("").lanes["small"], {}, 1.0)
    assert ex.value.retryable is True

    def junk(req, timeout):
        return FakeResp({"nope": 1})

    with pytest.raises(T.TransportError) as ex:
        T.HTTPTransport(opener=junk).send(prog("").lanes["small"], {}, 1.0)
    assert ex.value.retryable is False


def test_http_transport_refuses_forbidden_port_even_if_lane_was_built_by_hand():
    lane = P.Lane("g", "http://127.0.0.1:8001", "m", 1.0, 1.0, 0.0, None, False, 1)
    with pytest.raises(T.TransportError) as ex:
        T.HTTPTransport(opener=lambda *a, **k: FakeResp({})).send(lane, {}, 1.0)
    assert "forbidden" in str(ex.value) and ex.value.retryable is False


# ----------------------------------------------------------------- CLI + examples

def cli(*args, **kw):
    return subprocess.run([sys.executable, RUN, *args], capture_output=True, text=True, timeout=60, **kw)


def test_cli_dry_run_triage_exit_0_and_trace(tmp_path):
    trace = tmp_path / "t.jsonl"
    r = cli(os.path.join(EX, "triage.errand"), "triage", "text=the build crashes", "--trace", str(trace))
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0] == "bug" and "projected" in r.stderr
    evs = [json.loads(l) for l in trace.read_text().splitlines()]
    assert evs[0]["ev"] == "flow_start" and evs[-1]["ev"] == "flow_end" and evs[-1]["ok"] is True
    assert {e["lane"] for e in evs if e["ev"] == "preflight"} == {"olmoe", "qwen"}


def test_cli_mock_transport_exit_1_on_miss(tmp_path):
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"olmoe": ["nonsense", "nonsense", "nonsense"], "qwen36-tools": ["fine"]}))
    r = cli(os.path.join(EX, "triage.errand"), "triage", "text=hello", "--transport", f"mock:{m}", "--seed", "1")
    assert r.returncode == 0, r.stderr                       # classify misses -> rescue "question" -> queued
    assert r.stdout.splitlines() == ["question", "queued as question (no model turn spent)"]
    m.write_text(json.dumps({"olmoe": ["bug"], "qwen36-tools": [""]}))
    r = cli(os.path.join(EX, "triage.errand"), "triage", "text=hello", "--transport", f"mock:{m}")
    assert r.returncode == 1 and "miss(task answer" in r.stdout


def test_cli_exit_codes_2_and_3(tmp_path):
    bad = tmp_path / "bad.errand"
    bad.write_text('lane g { url "http://127.0.0.1:8001" prefill 1 decode 1 }')
    assert cli(str(bad), "f").returncode == 2
    assert cli(str(tmp_path / "missing.errand"), "f").returncode == 3
    ok = tmp_path / "ok.errand"
    ok.write_text('flow f(a) { emit a }')
    assert cli(str(ok), "f", "a").returncode == 3                 # not k=v
    assert cli(str(ok), "g", "a=1").returncode == 3               # no such flow
    assert cli(str(ok), "f", "a=1", "--transport", "bogus").returncode == 3
    r = cli(str(ok), "f", "a=1")
    assert r.returncode == 0 and r.stdout.strip() == "1"


def test_example_nuc_mini_probe_refuses_micro_under_60s_but_not_mini_under_5m():
    r = cli(os.path.join(EX, "nuc_mini_probe.errand"), "probe", "question=How much disk is free?")
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0].startswith("micro tier refused") and lines[1] == "<dry-run>"
    r = cli(os.path.join(EX, "nuc_mini_probe.errand"), "probe", "question=How much disk is free?", "--events")
    pre = [json.loads(l) for l in r.stderr.splitlines() if '"preflight"' in l]
    assert pre[0]["ok"] is False and 60 < pre[0]["projected_s"] < 120 and pre[1]["ok"] is True


def test_example_fallback_dry_and_with_small_lane_down(tmp_path):
    r = cli(os.path.join(EX, "fallback.errand"), "summarize", "text=some words")
    assert r.returncode == 0 and r.stdout.splitlines()[0] == "<dry-run>"
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"olmoe": [], "qwen36-tools": ["big summary"]}))
    r = cli(os.path.join(EX, "fallback.errand"), "summarize", "text=some words", "--transport", f"mock:{m}")
    assert r.returncode == 0, r.stderr
    out = r.stdout.splitlines()
    assert out[0] == "big summary"
    w = json.loads(out[1])
    assert w["prov"]["kind"] == "rescue" and w["prov"]["recovered"]["ok"] is False

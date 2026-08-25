"""Completion guards — the loop's last line of defence before "completed".

A run ends the moment the model replies without a tool call. Live, that
moment is where the harness silently loses money: round 107's sonnet lane
ended THREE runs at steps 1–3 with a reply that was a tool call written as
prose (`read_file(path=whence/interp.py, start=1260, end=1320)`, the literal
`tool call: search`, an unfenced JSON object with "Wait invalid JSON" after
it), one with an empty reply, and round 101's control review with an empty
reply after 30 steps — each recorded as `completed`, each unusable, $0.72 for
nothing in one stage alone. The model had not finished; the protocol had
slipped, and the loop's only notion of "done" (no tool call) could not tell.

A Guard looks at the would-be final text and either accepts it (None) or
returns a Rejection. A rejection normally becomes a corrective USER message
and the loop takes one more completion; a rejection that carries recovered
tool calls is dispatched instead, as if the model had called the tool (the
cheapest possible fix: the step the model wanted actually happens).

Design decisions (each covered by a test):
  - Guards see text only, never usage or cost; they are pure functions of
    (text, GuardContext) so they are trivially testable and cannot depend
    on the backend.
  - Recovery is opt-in per guard and CONSERVATIVE: a prose call is
    dispatched only when the tool exists, is `parallel_safe` (the
    registry's read-only marker — write_file/bash never auto-run from a
    guess), every argument names a declared parameter, and every required
    parameter is present. Anything else is a nudge, never a guess.
  - Nudges quote what was seen and, when the backend publishes one
    (`llm.tool_call_hint`), the exact call syntax — the corrective message
    is the ONLY thing standing between a slipped protocol and another
    slipped protocol, so it carries the protocol.
  - The loop bounds rejections per run (`AgentConfig.max_guard_retries`,
    global not consecutive — a model alternating two bad shapes must not
    loop) and ends with stop_reason "rejected" when they run out, so a
    campaign driver can tell "answered" from "gave up on the format".
  - A guard that raises is a bug in the guard, not in the run: the loop
    logs `guard_crashed` and accepts the text.
"""

import ast
import json
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from .llm import ToolCall, make_call_id


@dataclass
class GuardContext:
    tool_specs: Sequence[dict] = ()          # registry.specs(): name / description / input_schema
    registry: object = None                  # ToolRegistry, for parallel_safe lookups (may be None)
    tool_call_hint: Optional[str] = None     # backend's own syntax for a tool call, if it has one
    step: int = 0

    @property
    def tool_names(self) -> List[str]:
        return [t["name"] for t in self.tool_specs if isinstance(t, dict) and "name" in t]

    def spec(self, name: str) -> Optional[dict]:
        for t in self.tool_specs:
            if t.get("name") == name:
                return t
        return None

    def is_safe(self, name: str) -> bool:
        """Read-only per the registry's `parallel_safe` marker; False when unknown."""
        reg = self.registry
        if reg is None:
            return False
        tool = reg.get(name) if hasattr(reg, "get") else None
        return bool(getattr(tool, "parallel_safe", False))

    def hint_clause(self) -> str:
        if self.tool_call_hint:
            return " — " + self.tool_call_hint.strip()
        return " (the structured tool-calling interface, not text)"


@dataclass
class Rejection:
    guard: str
    reason: str                 # short label: "prose_tool_call", "empty", "missing_keys", ...
    message: str                # corrective user message the loop appends
    calls: List[ToolCall] = field(default_factory=list)   # non-empty = recovered, dispatch these
    detail: str = ""            # what was matched (trace only)

    @property
    def recovered(self) -> bool:
        return bool(self.calls)


class Guard:
    name = "guard"

    def check(self, text: str, ctx: GuardContext) -> Optional[Rejection]:
        raise NotImplementedError


# ------------------------------------------------------------ helpers ---

def _snippet(s: str, n: int = 120) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _split_top_level(s: str) -> List[str]:
    """Split on commas that are not inside quotes or brackets."""
    parts, depth, quote, cur, i = [], 0, None, [], 0
    while i < len(s):
        c = s[i]
        if quote:
            cur.append(c)
            if c == "\\" and i + 1 < len(s):
                cur.append(s[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
            cur.append(c)
        elif c in "([{":
            depth += 1
            cur.append(c)
        elif c in ")]}":
            depth -= 1
            cur.append(c)
        elif c == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    if "".join(cur).strip() or parts:
        parts.append("".join(cur))
    return [p for p in parts if p.strip()]


def _coerce(raw: str):
    """A python-call argument value → JSON-ish Python value. Quoted strings
    and Python/JSON literals are evaluated; anything else is the raw text
    (paths are usually written unquoted: `path=whence/interp.py`)."""
    v = raw.strip()
    if not v:
        return ""
    try:
        return ast.literal_eval(v)
    except (ValueError, SyntaxError):
        pass
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none"):
        return None
    return v


def parse_python_call_args(argtext: str) -> Optional[Dict[str, object]]:
    """`path=a/b.py, start=12, end="x"` → {"path": "a/b.py", "start": 12,
    "end": "x"}; None when anything is positional or unparsable."""
    out: Dict[str, object] = {}
    for part in _split_top_level(argtext):
        if "=" not in part:
            return None
        k, v = part.split("=", 1)
        k = k.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
            return None
        out[k] = _coerce(v)
    return out


def _fit_schema(args: Dict[str, object], spec: dict) -> Optional[Dict[str, object]]:
    """Validate/coerce parsed args against a tool spec: unknown keys or
    missing required keys → None; scalar types coerced per the schema."""
    schema = spec.get("input_schema") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    if set(args) - set(props):
        return None
    if required - set(args):
        return None
    fitted: Dict[str, object] = {}
    for k, v in args.items():
        want = (props.get(k) or {}).get("type")
        if want == "string" and not isinstance(v, str):
            v = "" if v is None else (json.dumps(v) if isinstance(v, (dict, list)) else str(v))
        elif want == "integer" and isinstance(v, str) and re.fullmatch(r"-?\d+", v.strip()):
            v = int(v)
        elif want == "number" and isinstance(v, str):
            try:
                v = float(v)
            except ValueError:
                return None
        elif want == "boolean" and isinstance(v, str) and v.strip().lower() in ("true", "false"):
            v = v.strip().lower() == "true"
        elif want == "integer" and isinstance(v, bool):
            return None
        elif want == "integer" and isinstance(v, float) and v.is_integer():
            v = int(v)
        fitted[k] = v
    return fitted


def _first_json_object(text: str) -> Optional[dict]:
    """The first balanced JSON object in `text` that parses, or None."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _last_json_object(text: str) -> Optional[dict]:
    dec = json.JSONDecoder()
    found = None
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict):
            found = obj
    return found


# ------------------------------------------------------------- guards ---

class EmptyAnswerGuard(Guard):
    """An empty (or whitespace-only) final reply is not an answer."""
    name = "empty_answer"

    def check(self, text: str, ctx: GuardContext) -> Optional[Rejection]:
        if text.strip():
            return None
        msg = ("Your previous reply was empty, so nothing was run and no answer was "
               "recorded. Either call a tool%s, or reply now with your final answer as "
               "plain text." % ctx.hint_clause())
        return Rejection(self.name, "empty", msg)


_CALL_PREFIX = r"(?:tool\s*call\s*:?|call(?:ing)?\s*:?|use(?:\s+the)?(?:\s+tool)?\s*:?|run\s*:?)?"
_PY_CALL = re.compile(
    r"\A\s*" + _CALL_PREFIX + r"\s*`?(?P<name>[A-Za-z_][A-Za-z0-9_]*)`?\s*\((?P<args>.*)\)\s*`?\s*\Z",
    re.S)
_BARE_MENTION = re.compile(
    r"\A\s*(?:tool\s*call|call|use\s*tool|tool|calling|run)\s*:?\s*`?(?P<name>[A-Za-z_][A-Za-z0-9_]*)`?\s*[.!]?\s*\Z",
    re.I)
_XML_CALL = re.compile(
    r"<\s*(?:tool_call|function_calls|invoke|tool_use|antml:invoke|antml:function_calls)\b", re.I)
_JSON_NAME = re.compile(r'"name"\s*:\s*"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"')


class ProseToolCallGuard(Guard):
    """A final reply that IS a tool call — written as prose, python syntax,
    an XML tag, or an unfenced/malformed JSON object — is not an answer.

    Shapes (all observed live or in the adapter's own history):
      python   `read_file(path=whence/interp.py, start=1260, end=1320)`
      bare     `tool call: search`
      json     `{"name": "read_file", "args": {...` + commentary / broken braces
      xml      `<tool_call>…`, `<invoke name="…">`

    `recover=True` dispatches the python and json shapes when they parse
    cleanly against a read-only (`parallel_safe`) tool; everything else is a
    nudge that quotes the reply and the backend's call syntax."""
    name = "prose_tool_call"

    def __init__(self, recover: bool = True, recover_unsafe: bool = False):
        self.recover = recover
        self.recover_unsafe = recover_unsafe

    # -- detection ---------------------------------------------------------

    def detect(self, text: str, ctx: GuardContext):
        """(reason, tool name or None, parsed args or None) or None."""
        names = set(ctx.tool_names)
        body = text.strip()
        if not body:
            return None
        last_line = body.splitlines()[-1].strip()

        if _XML_CALL.search(body):
            # <invoke name="x"> (attribute) or <tool_call>{"name": "x", …} (JSON body)
            m = re.search(r'name\s*=\s*"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"', body) or _JSON_NAME.search(body)
            return ("xml_tool_call", m.group("name") if m and m.group("name") in names else None, None)

        for candidate in (body, last_line):
            m = _PY_CALL.match(candidate)
            if m and m.group("name") in names:
                return ("python_tool_call", m.group("name"), parse_python_call_args(m.group("args")))

        m = _BARE_MENTION.match(body)
        if m and m.group("name") in names:
            return ("bare_tool_mention", m.group("name"), {})

        jm = _JSON_NAME.search(body)
        if jm and jm.group("name") in names:
            obj = _first_json_object(body)
            args = None
            if isinstance(obj, dict) and obj.get("name") == jm.group("name"):
                a = obj.get("args", obj.get("input", obj.get("arguments", {})))
                if isinstance(a, dict):
                    args = a
            # An answer that merely quotes a tool name inside a larger JSON
            # (e.g. a review's {"claims": [{"name": "read_file" ...}]}) is
            # not a call: require the object to be the call itself, or the
            # text to be mostly that object.
            if obj is not None and obj.get("name") != jm.group("name"):
                return None
            return ("malformed_json_tool_call", jm.group("name"), args)
        return None

    # -- check ---------------------------------------------------------------

    def check(self, text: str, ctx: GuardContext) -> Optional[Rejection]:
        hit = self.detect(text, ctx)
        if hit is None:
            return None
        reason, name, args = hit
        detail = _snippet(text)
        if self.recover and name is not None and args is not None:
            spec = ctx.spec(name)
            if spec is not None and (self.recover_unsafe or ctx.is_safe(name)):
                fitted = _fit_schema(args, spec)
                if fitted is not None:
                    call = ToolCall(name, fitted, make_call_id())
                    return Rejection(self.name, reason, "", calls=[call], detail=detail)
        what = ("a tool call written as plain text" if reason != "xml_tool_call"
                else "a tool call in an XML-tag format this harness does not use")
        target = ("`%s`" % name) if name else "a tool"
        msg = ("Your previous reply looked like %s (%s), so NOTHING was run. To call %s "
               "you must use the tool-calling interface%s. If you meant to call %s, emit "
               "that call now; if you are finished, reply with your final answer as plain "
               "text and no tool call." % (what, detail, target, ctx.hint_clause(), target))
        return Rejection(self.name, reason, msg, detail=detail)


class JsonAnswerGuard(Guard):
    """The final answer must contain a JSON object (in a ```json fence by
    default; `allow_bare=True` also accepts a bare object anywhere) whose
    keys include `required`. The LAST such object counts — models often
    reason first and answer last."""
    name = "json_answer"

    def __init__(self, required: Sequence[str] = (), allow_bare: bool = False,
                 example: Optional[str] = None, validate: Optional[Callable[[dict], Optional[str]]] = None):
        self.required = list(required)
        self.allow_bare = allow_bare
        self.example = example
        self.validate = validate

    _FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.S)

    def extract(self, text: str) -> Optional[dict]:
        found = None
        for m in self._FENCE.finditer(text):
            body = m.group(1).strip()
            try:
                obj = json.loads(body)
            except ValueError:
                obj = _last_json_object(body)
            if isinstance(obj, dict):
                found = obj
        if found is None and self.allow_bare:
            found = _last_json_object(text)
        return found

    def _format(self) -> str:
        keys = ", ".join(self.required) if self.required else "the fields the task asked for"
        s = "a ```json fenced block containing one JSON object with the keys: %s" % keys
        if self.example:
            s += ", for example:\n%s" % self.example
        return s

    def check(self, text: str, ctx: GuardContext) -> Optional[Rejection]:
        obj = self.extract(text)
        if obj is None:
            reason = "no_json_answer"
            why = "did not contain a parseable JSON answer"
        else:
            missing = [k for k in self.required if k not in obj]
            if missing:
                reason = "missing_keys"
                why = "was missing the key(s): %s" % ", ".join(missing)
            else:
                problem = self.validate(obj) if self.validate else None
                if not problem:
                    return None
                reason = "invalid_answer"
                why = "was invalid: %s" % problem
        msg = ("Your previous reply %s. Reply again with your COMPLETE final answer, "
               "ending with %s." % (why, self._format()))
        return Rejection(self.name, reason, msg, detail=_snippet(text))


class PatternGuard(Guard):
    """The final answer must match `pattern` (re.search); `message` is the
    corrective text (it should say what shape is expected)."""
    name = "pattern"

    def __init__(self, pattern: str, message: str, flags: int = re.S, name: Optional[str] = None):
        self.pattern = re.compile(pattern, flags)
        self.message = message
        if name:
            self.name = name

    def check(self, text: str, ctx: GuardContext) -> Optional[Rejection]:
        if self.pattern.search(text):
            return None
        return Rejection(self.name, "pattern_mismatch", self.message, detail=_snippet(text))


class CallableGuard(Guard):
    """Wrap `fn(text, ctx) -> Optional[str]` (a corrective message, or None)."""

    def __init__(self, fn: Callable[[str, GuardContext], Optional[str]], name: str = "callable"):
        self.fn = fn
        self.name = name

    def check(self, text: str, ctx: GuardContext) -> Optional[Rejection]:
        msg = self.fn(text, ctx)
        if not msg:
            return None
        return Rejection(self.name, "rejected", msg, detail=_snippet(text))


def default_guards(recover: bool = True) -> List[Guard]:
    """What every live run should carry: the two failure shapes that ended
    round-107 runs at steps 1–3, in the order they should be tried."""
    return [EmptyAnswerGuard(), ProseToolCallGuard(recover=recover)]


def run_guards(guards: Sequence[Guard], text: str, ctx: GuardContext,
               on_crash: Optional[Callable[[Guard, Exception], None]] = None) -> Optional[Rejection]:
    """First rejection wins; a crashing guard is reported and skipped."""
    for g in guards:
        try:
            r = g.check(text, ctx)
        except Exception as e:  # noqa: BLE001 — a guard bug must not end a run
            if on_crash is not None:
                on_crash(g, e)
            continue
        if r is not None:
            return r
    return None

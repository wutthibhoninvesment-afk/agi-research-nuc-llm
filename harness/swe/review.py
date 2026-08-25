"""Oracle-gated review, model-driven survivor killing, verified fixing (round 11).

Round 5 put the real model in the loop once, for a *judgement* nobody
checked. This module makes every model claim pay its way: a claim is only
counted when a tool the model did not write confirms it.

  review   the model reads a source region and reports defects. Each claim
           MUST carry a Whence program; the harness runs the differential
           oracles (swe.oracles) + totality on that program and the claim is
           `confirmed` only when an oracle fires. Metric: precision.
  kill     the model is handed a surviving mutant (a diff the test suite and
           the random corpus could not distinguish from the original) and
           must write a program whose behaviour differs — or argue
           equivalence. `mutant_diff` runs both interpreters; the harness
           re-runs it on the final program. Metric: kill rate on `no_killer`
           survivors; kills become pinned tests (killers.render_tests).
  fix      the model gets a confirmed finding and a scratch COPY of the
           checkout (edit_file / pytest / oracle_check all sandboxed to it).
           Done means: the oracle no longer fires on the reproducer AND the
           suite is green in the copy. The diff is the artifact.

All three are (registry, prompt, score) triples driven by the ordinary
agentloop Agent, so they run offline under a PolicyLLM (tests) and live under
ClaudeCLILLM (`python3 -m swe.review kill|review|fix ...`).
"""

import difflib
import json
import os
import re
import shutil
import tempfile
import time

from agentloop import (Agent, AgentConfig, JsonAnswerGuard, ToolRegistry, TraceLogger,
                       default_guards)
from agentloop.tools import Tool, ToolResult
from . import killers as K
from . import oracles as O
from . import guest as _guest  # noqa: F401 — registers the self_eval oracle
from .fuzz import WHENCE_ROOT, shrink
from .mutation import _copy_project, run_mutant, DEFAULT_TEST_CMD
from .tools import WhenceRunTool, PytestTool
from .regiontools import region_tools, CallBudget

JSON_BLOCK = re.compile(r"```(?:json)?\s*\n(\{.*?\})\s*\n```", re.S)


def extract_json(text):
    """The model's final answer as a dict: last fenced JSON block, else the
    last balanced {...} in the text; None if nothing parses."""
    if not text:
        return None
    blocks = JSON_BLOCK.findall(text)
    for b in reversed(blocks):
        try:
            return json.loads(b)
        except ValueError:
            continue
    # fallback: the LAST top-level balanced {...} that parses
    found = None
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        end = None
        for j in range(i, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end is None:
            break
        try:
            found = json.loads(text[i:end + 1])
            i = end + 1
        except ValueError:
            i += 1
    return found


def _tag(root, prefix):
    return "%s_%x" % (prefix, abs(hash(os.path.realpath(root))) % (1 << 32))


WHENCE_PRIMER = """\
Whence in 12 lines (read SPEC.md with read_file for the full language):
  let x = 1 + 2                # bind once; same-block rebinding is a parse error
  fn f(a, b) { a * b }         # last expression is the value; tail calls loop
  if c { 1 } else { 2 }        # if is an expression; non-bool condition -> miss
  check "label": expr          # test statement, records ok/fail
  print(x)  print(why x)       # why x = the provenance (why-tree) of x
  miss "reason"                # every runtime error is a propagating `miss`
  (expr rescue fallback)       # recover from a miss
  [1, 2] @{k: 1}  xs[0] r.k    # lists, records, index, field
  snip x  note("lbl", x)       # cut / annotate provenance
  builtins: len range map filter fold push str num abs sqrt missed reasons
            contains join keys merge steps at blame diverge contrast
Values ARE provenance nodes: `why`, `steps(x)`, `at(x, "let a")`,
`diverge(a, b)`, `contrast(a, b)` inspect history and are part of behaviour.
"""


# ----------------------------------------------------------------- tools --

class OracleTool(Tool):
    name = "oracle_check"
    description = ("Run a Whence program through the totality oracle (no Python "
                   "exception may escape) and the differential oracles fast_slow "
                   "(compiled fast path vs generator path must agree on output, "
                   "checks, values AND why-trees), direct (v0.9 host-recursion "
                   "calls vs trampoline calls, same agreement), determinism (same AST twice + "
                   "fresh parse agree) and render (why/steps/diverge/contrast "
                   "identities). Pass oracles=\"self_eval\" to instead compare the "
                   "host interpreter against the self-hosted evaluator "
                   "(examples/self_eval.lang) on a guest-safe program: no "
                   "provenance builtins (why/snip/steps/at/blame/diverge/contrast/"
                   "print), keep recursion shallow (<200); final values of all "
                   "top-level bindings, missed-ness and check results must agree "
                   "(miss WORDINGS and one-sided depth exhaustion are exempt by "
                   "design). Returns JSON per oracle: kind ok|mismatch|crash|"
                   "parse_error|timeout and a detail naming the first difference.")
    params = {
        "source": {"type": "string", "description": "Whence program text"},
        "oracles": {"type": "string", "description": "comma list (default: all)"},
    }
    required = ["source"]
    parallel_safe = True

    def __init__(self, root=WHENCE_ROOT, timeout_s=3.0, max_depth=500):
        self.root = root
        self.timeout_s = timeout_s
        self.max_depth = max_depth
        self._pkg = None

    def pkg(self):
        if self._pkg is None:
            self._pkg = K.load_whence(self.root, _tag(self.root, "oracle"))
        return self._pkg

    def check(self, source, oracles=None):
        names = tuple(n.strip() for n in (oracles or "").split(",") if n.strip()) \
            or O.ORACLE_NAMES
        out = {}
        for name in names:
            if name in O.ORACLES:
                o = O.run_oracle(name, self.pkg(), source, timeout_s=self.timeout_s,
                                 max_depth=self.max_depth, root=self.root)
                d = {"kind": o.kind}
                if o.kind in ("mismatch", "crash"):
                    d["detail"] = o.detail[:400]
                    d["signature"] = list(O.signature(o))
                out[name] = d
            else:
                out[name] = {"kind": "unknown_oracle"}
        return out

    def run(self, source, oracles=None):
        res = self.check(source, oracles)
        fired = [n for n, d in res.items() if d["kind"] in ("mismatch", "crash")]
        res["_fired"] = fired
        return ToolResult(True, json.dumps(res, ensure_ascii=False, indent=1))


def fired(oracle_result):
    """Oracle names whose kind is mismatch/crash in an OracleTool result."""
    return [n for n, d in oracle_result.items()
            if n != "_fired" and isinstance(d, dict) and d.get("kind") in ("mismatch", "crash")]


class MutantDiffTool(Tool):
    name = "mutant_diff"
    description = ("Run a Whence program under the ORIGINAL interpreter and under "
                   "the MUTANT, returning both canonical behaviours (printed lines, "
                   "check results, rendering of every top-level binding) and "
                   "whether they differ. A program on which they differ KILLS the "
                   "mutant.")
    params = {"source": {"type": "string", "description": "Whence program text"}}
    required = ["source"]
    parallel_safe = True

    def __init__(self, root, mutant, timeout_s=2.0):
        self.root = root
        self.mutant = mutant
        self.timeout_s = timeout_s
        self.tmp = tempfile.mkdtemp(prefix="mkill-")
        self.dst = os.path.join(self.tmp, "proj")
        _copy_project(root, self.dst)
        with open(os.path.join(self.dst, mutant.path), "w", encoding="utf-8") as f:
            f.write(mutant.source)
        self._orig = None
        self._mut = None
        self.import_error = None
        self.calls = 0

    def packages(self):
        if self._orig is None:
            self._orig = K.load_whence(self.root, _tag(self.root, "korig"))
            try:
                self._mut = K.load_whence(self.dst, "kmut_" + re.sub(r"\W", "_", self.mutant.id))
            except Exception as e:  # noqa: BLE001 — mutant fails to import
                self.import_error = repr(e)
        return self._orig, self._mut

    def diff(self, source):
        orig, mut = self.packages()
        a = K.behaviour(orig, source, timeout_s=self.timeout_s)
        if mut is None:
            return {"differs": True, "original": a, "mutant": {"kind": "import_error",
                                                               "exc": self.import_error}}
        b = K.behaviour(mut, source, timeout_s=self.timeout_s)
        differs = a != b and a.get("kind") != "timeout"
        return {"differs": differs, "original": a, "mutant": b,
                "first_difference": O.first_difference(a, b) if differs else ""}

    def run(self, source):
        self.calls += 1
        d = self.diff(source)
        return ToolResult(True, json.dumps(d, ensure_ascii=False, indent=1))

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class EditFileTool(Tool):
    name = "edit_file"
    description = ("Replace ONE exact occurrence of `old` with `new` in a file of "
                   "the scratch checkout. Fails (no change) if `old` is empty, "
                   "absent, or not unique. Edits are recorded for the final diff.")
    params = {
        "path": {"type": "string", "description": "file path relative to checkout"},
        "old": {"type": "string", "description": "exact text to replace (unique)"},
        "new": {"type": "string", "description": "replacement text"},
    }
    required = ["path", "old", "new"]

    def __init__(self, root):
        self.root = os.path.realpath(root)
        self.edits = []     # (path, old, new)

    def run(self, path, old, new):
        full = os.path.realpath(os.path.join(self.root, path))
        if not full.startswith(self.root + os.sep):
            return ToolResult(False, "path escapes the checkout: %s" % path)
        if not os.path.isfile(full):
            return ToolResult(False, "no such file: %s" % path)
        if not old:
            return ToolResult(False, "`old` must be non-empty")
        with open(full, encoding="utf-8") as f:
            s = f.read()
        n = s.count(old)
        if n != 1:
            return ToolResult(False, "`old` occurs %d times in %s; it must occur exactly once"
                              % (n, path))
        i = s.index(old)
        line = s.count("\n", 0, i) + 1
        s2 = s[:i] + new + s[i + len(old):]
        with open(full, "w", encoding="utf-8") as f:
            f.write(s2)
        self.edits.append((path, old, new))
        return ToolResult(True, "edited %s at line %d (%+d chars); %d edit(s) so far"
                          % (path, line, len(new) - len(old), len(self.edits)))


class Workspace(object):
    """A scratch copy of the checkout that the fix task edits."""

    def __init__(self, root=WHENCE_ROOT, files=("whence",)):
        self.root = os.path.realpath(root)
        self.tmp = tempfile.mkdtemp(prefix="fixws-")
        self.dst = os.path.join(self.tmp, "proj")
        _copy_project(self.root, self.dst)

    def changed_files(self):
        out = []
        for dirpath, _, names in os.walk(self.dst):
            for n in names:
                if not n.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, n), self.dst)
                src = os.path.join(self.root, rel)
                if not os.path.exists(src):
                    out.append(rel)
                    continue
                with open(src, encoding="utf-8") as f1, open(os.path.join(dirpath, n), encoding="utf-8") as f2:
                    if f1.read() != f2.read():
                        out.append(rel)
        return sorted(out)

    def diff(self):
        chunks = []
        for rel in self.changed_files():
            src = os.path.join(self.root, rel)
            a = open(src, encoding="utf-8").read().splitlines(True) if os.path.exists(src) else []
            b = open(os.path.join(self.dst, rel), encoding="utf-8").read().splitlines(True)
            chunks.append("".join(difflib.unified_diff(a, b, "a/" + rel, "b/" + rel)))
        return "".join(chunks)

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ----------------------------------------------------------------- tasks --

REVIEW_SYSTEM = """You are a meticulous interpreter engineer reviewing code for
semantic defects. Every defect you report must be DEMONSTRATED by a Whence
program on which one of the harness oracles fires — reports without a firing
reproducer are counted against you. Use oracle_check liberally: form a
hypothesis from the code, write the smallest program that would expose it,
run oracle_check, and keep only claims whose oracle fired."""

KILL_SYSTEM = """You are a test engineer killing a surviving mutant. The
mutant is a one-token change to the interpreter that the whole test suite
and 300 random programs failed to distinguish from the original. Reason
from the code about which inputs reach the mutated line with a different
outcome, write such a Whence program, and run mutant_diff to check. Iterate.
If after careful reading you conclude no program can observe the change,
say so with a concrete argument."""

FIX_SYSTEM = """You are fixing a confirmed interpreter defect in a scratch
copy of the checkout. First reproduce with oracle_check, then read the
relevant code, then make the smallest correct change with edit_file, then
verify: oracle_check on the reproducer must be all ok AND pytest must be
green. Do not weaken tests or oracles. Explain the root cause in your final
answer."""


def review_task(root=WHENCE_ROOT, files=("whence/interp.py",), focus="",
                max_claims=6, max_steps=None, read_budget=None):
    budget = CallBudget(read_budget, "run oracle_check on your hypotheses and emit the final JSON") \
        if read_budget else None
    registry = ToolRegistry([
        OracleTool(root), WhenceRunTool(root, tag=_tag(root, "run"))] + region_tools(root, budget=budget))
    budget_note = ""
    if max_steps:
        # round 17: a live review spent all 30 steps searching and never ran
        # the oracle once — the budget must be visible to the model
        budget_note = ("You have a budget of %d tool steps TOTAL; keep at "
                       "least half for oracle_check probes, and emit your "
                       "final JSON before the budget runs out.\n" % max_steps)
    if read_budget:
        # round 101: visible was not enough (28/30 steps reading); enforced now
        budget_note += ("outline/read_file/search share a hard budget of %d calls; after "
                        "that they refuse and only oracle_check/whence_run remain.\n" % read_budget)
    prompt = (WHENCE_PRIMER + "\n" +
              ("Review %s for semantic defects.%s\n"
               % (", ".join(files), (" Focus: " + focus) if focus else "")) +
              budget_note +
              "Oracles available through oracle_check: totality (Python exception "
              "escaping = bug), fast_slow (compiled fast path vs generator path — "
              "output, checks, values and why-trees must be identical), "
              "direct (v0.9 direct-mode calls vs trampoline calls, same bar), "
              "determinism, render; plus self_eval (host vs the self-hosted "
              "evaluator in examples/self_eval.lang — request it explicitly with "
              "the oracles argument and follow the guest-safe rules in the tool "
              "description).\n"
              "Reading code: call outline on a file first (definitions with line "
              "ranges), then read_file with start/end to read a definition's window "
              "(max 200 lines per call; whole-file reads are truncated). search takes "
              "a file OR directory and a context count. Read the code, hypothesise, "
              "reproduce with oracle_check.\n"
              "Finish with a JSON block:\n"
              '```json\n{"claims": [{"title": "...", "program": "<whence source>", '
              '"oracle": "<which oracle fires>", "root_cause": "..."}]}\n```\n'
              "At most %d claims; an empty list is a valid answer if you find "
              "nothing that reproduces." % max_claims)
    return registry, prompt


def score_review(answer, oracle_tool):
    """Re-run the oracles on every claim's program. Returns the list of
    claim records with `confirmed` and the fired oracles."""
    data = extract_json(answer) or {}
    claims = data.get("claims") if isinstance(data, dict) else None
    if not isinstance(claims, list):
        claims = []
    out = []
    for c in claims:
        if not isinstance(c, dict) or not isinstance(c.get("program"), str):
            out.append({"title": str(c)[:80], "confirmed": False, "fired": [],
                        "error": "no program"})
            continue
        res = oracle_tool.check(c["program"])
        f = fired(res)
        out.append({"title": c.get("title", ""), "program": c["program"],
                    "claimed_oracle": c.get("oracle", ""), "root_cause": c.get("root_cause", ""),
                    "fired": f, "confirmed": bool(f),
                    "claimed_matches": (c.get("oracle") in f) if f else False,
                    "signatures": dict((n, res[n].get("signature")) for n in f)})
    return out


def mutant_unified_diff(root, mutant, context=3):
    with open(os.path.join(root, mutant.path), encoding="utf-8") as f:
        a = f.read().splitlines(True)
    b = mutant.source.splitlines(True)
    return "".join(difflib.unified_diff(a, b, "original/" + mutant.path,
                                        "mutant/" + mutant.path, n=context))


def kill_task(root, mutant):
    tool = MutantDiffTool(root, mutant)
    registry = ToolRegistry([tool, WhenceRunTool(root, tag=_tag(root, "run"))] + region_tools(root))
    prompt = (WHENCE_PRIMER + "\n"
              "Surviving mutant %s (%s) in %s:\n```diff\n%s```\n"
              "Write a Whence program whose canonical behaviour differs between "
              "original and mutant (use mutant_diff to test candidates; "
              "outline + read_file with start/end, or search with context, to read "
              "the code around the mutated line). Behaviour = printed "
              "lines, check results, and the rendering of top-level bindings; "
              "why-trees are NOT compared, so make the difference visible in a "
              "value, a print, or a check.\n"
              "Finish with a JSON block:\n"
              '```json\n{"verdict": "killed" | "equivalent", "program": "<whence source or null>", '
              '"argument": "..."}\n```'
              % (mutant.id, mutant.op, mutant.path, mutant_unified_diff(root, mutant)))
    return registry, prompt, tool


def score_kill(answer, tool):
    data = extract_json(answer) or {}
    verdict = data.get("verdict") if isinstance(data, dict) else None
    program = data.get("program") if isinstance(data, dict) else None
    rec = {"verdict_claimed": verdict, "program": program, "killed": False,
           "argument": (data.get("argument") if isinstance(data, dict) else "") or ""}
    if isinstance(program, str) and program.strip():
        d = tool.diff(program)
        rec["killed"] = bool(d["differs"])
        rec["expected"] = d["original"]
        rec["mutant_behaviour"] = d["mutant"]
        rec["first_difference"] = d.get("first_difference", "")
        if rec["killed"]:
            def keep(cand):
                r = tool.diff(cand)
                return r["differs"]
            rec["minimized"] = shrink(program, keep) or program
            rec["expected"] = tool.diff(rec["minimized"])["original"]
    rec["outcome"] = ("killed" if rec["killed"] else
                      "equivalent_claimed" if verdict == "equivalent" else "failed")
    return rec


def fix_task(finding, root=WHENCE_ROOT):
    """`finding`: {"program": src, "oracle": name, "detail": str}."""
    ws = Workspace(root)
    registry = ToolRegistry([
        OracleTool(ws.dst), WhenceRunTool(ws.dst, tag=_tag(ws.dst, "run"))]
        + region_tools(ws.dst) + [EditFileTool(ws.dst), PytestTool(ws.dst, timeout_s=900)])
    prompt = (WHENCE_PRIMER + "\n"
              "Confirmed defect. Oracle `%s` fires on this program:\n```\n%s\n```\n"
              "Oracle detail:\n%s\n\n"
              "Fix the interpreter in the scratch checkout (whence/*.py). Verify with "
              "oracle_check (must be all ok) and pytest (must be green; the suite "
              "takes ~30-60s). Do not edit tests or the oracle. Finish with a JSON block:\n"
              '```json\n{"root_cause": "...", "files": ["whence/interp.py"], "summary": "..."}\n```'
              % (finding.get("oracle", "?"), finding["program"].strip(), finding.get("detail", "")))
    return registry, prompt, ws


def score_fix(ws, finding, run_tests=True, test_timeout_s=900):
    """Verify a fix in the workspace: oracle silent on the reproducer, suite green."""
    rec = {"changed_files": ws.changed_files(), "diff": ws.diff()}
    oracle = OracleTool(ws.dst)
    res = oracle.check(finding["program"])
    rec["oracle_after"] = dict((k, v.get("kind")) for k, v in res.items())
    rec["oracle_silent"] = not fired(res)
    if run_tests:
        r = PytestTool(ws.dst, timeout_s=test_timeout_s).run("-q tests")
        rec["tests_green"] = r.ok
        rec["pytest_tail"] = r.output[-600:]
    else:
        rec["tests_green"] = None
    rec["fixed"] = bool(rec["changed_files"]) and rec["oracle_silent"] and rec["tests_green"] is not False
    return rec


# --------------------------------------------------------------- running --

def answer_guard(kind):
    """The JSON answer each task demands, as a completion guard (round 109):
    a reply without it is nudged back with the format instead of being
    scored as "failed"."""
    if kind == "kill":
        def validate(obj):
            v = obj.get("verdict")
            if v not in ("killed", "equivalent"):
                return "verdict must be \"killed\" or \"equivalent\""
            if v == "killed" and not (isinstance(obj.get("program"), str) and obj["program"].strip()):
                return "verdict is \"killed\" but \"program\" is empty — include the Whence source"
            return None
        # only what score_kill needs: `verdict`, and `program` when killed
        # (the scripted kill in test_swe_review answers without `argument`)
        return JsonAnswerGuard(["verdict"], validate=validate,
                               example='```json\n{"verdict": "killed" | "equivalent", '
                                       '"program": "<whence source or null>", "argument": "..."}\n```')
    if kind == "review":
        return JsonAnswerGuard(["claims"], validate=lambda o: None if isinstance(o.get("claims"), list)
                               else "\"claims\" must be a list")
    if kind in ("fix", "repair"):
        return JsonAnswerGuard(["root_cause"])
    raise ValueError(kind)


def run_task(llm, registry, prompt, system, out_dir=None, max_steps=25, tag="task",
             max_observation_chars=12000, wrap_up=True, guards=None, max_guard_retries=2):
    """`guards=None` → the default completion guards (empty reply, tool call
    written as prose — round 107 lost three $0.2–0.3 runs to them); pass
    `answer_guard(kind)` in the list to also demand the task's JSON."""
    trace = TraceLogger(os.path.join(out_dir, "%s.trace.jsonl" % tag)) if out_dir else None
    cfg = AgentConfig(system_prompt=system, max_steps=max_steps,
                      max_observation_chars=max_observation_chars,
                      wrap_up_on_max_steps=wrap_up,
                      guards=default_guards() if guards is None else list(guards),
                      max_guard_retries=max_guard_retries)
    agent = Agent(llm, registry, config=cfg, trace=trace)
    t0 = time.time()
    r = agent.run(prompt)
    return r, time.time() - t0


def _llm_cost(llm, result):
    u = getattr(llm, "usage", None)
    if isinstance(u, dict):
        return {"input_tokens": u.get("input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
                "cost_usd": u.get("cost_usd", 0.0)}
    return {"input_tokens": result.usage.total_input, "output_tokens": result.usage.output_tokens,
            "cost_usd": result.cost_usd}


def run_kill(make_llm, mutants, root=WHENCE_ROOT, out_dir=None, max_steps=20,
             test_file=None, verify_with_suite=False, on_result=None):
    """Kill each mutant with a fresh LLM session; pin kills as tests."""
    results = []
    killers = []
    for m in mutants:
        llm = make_llm()
        registry, prompt, tool = kill_task(root, m)
        try:
            r, secs = run_task(llm, registry, prompt, KILL_SYSTEM, out_dir, max_steps,
                               tag="kill-" + re.sub(r"\W", "_", m.id),
                               guards=default_guards() + [answer_guard("kill")])
            rec = score_kill(r.final_text, tool)
            rec.update({"mutant": m.id, "description": m.description, "line": m.lineno,
                        "stop_reason": r.stop_reason, "steps": r.steps, "tool_calls": r.tool_calls,
                        "guard_rejections": r.guard_rejections, "guard_recoveries": r.guard_recoveries,
                        "mutant_diff_calls": tool.calls, "seconds": round(secs, 1),
                        "final_text": r.final_text[-1500:]})
            rec.update(_llm_cost(llm, r))
            if rec["killed"]:
                killers.append(K.Killer(m, rec["minimized"], rec["expected"],
                                        tool.diff(rec["minimized"])["mutant"], 0, secs))
        finally:
            tool.cleanup()
        results.append(rec)
        if on_result:
            on_result(rec)
    if test_file and killers:
        existing = open(test_file).read() if os.path.exists(test_file) else ""
        with open(test_file, "w") as f:
            f.write(K.render_tests(killers, existing))
        if verify_with_suite:
            for k, rec in zip(killers, [r for r in results if r["killed"]]):
                m = run_mutant(k.mutant, root, DEFAULT_TEST_CMD, timeout_s=600)
                rec["suite_kills_now"] = m.status in ("killed", "timeout")
    return results


def run_review(make_llm, root=WHENCE_ROOT, files=("whence/interp.py",), focus="",
               out_dir=None, max_steps=30, tag="review", read_budget=None):
    llm = make_llm()
    registry, prompt = review_task(root, files, focus, max_steps=max_steps, read_budget=read_budget)
    r, secs = run_task(llm, registry, prompt, REVIEW_SYSTEM, out_dir, max_steps, tag=tag,
                       guards=default_guards() + [answer_guard("review")])
    claims = score_review(r.final_text, registry.get("oracle_check"))
    rec = {"claims": claims, "confirmed": sum(1 for c in claims if c["confirmed"]),
           "claimed": len(claims), "stop_reason": r.stop_reason, "steps": r.steps,
           "guard_rejections": r.guard_rejections, "guard_recoveries": r.guard_recoveries,
           "tool_calls": r.tool_calls, "seconds": round(secs, 1), "read_budget": read_budget,
           "answered": bool(extract_json(r.final_text)),
           "final_text": r.final_text[-3000:]}
    rec.update(_llm_cost(llm, r))
    return rec


def run_fix(make_llm, finding, root=WHENCE_ROOT, out_dir=None, max_steps=30, tag="fix",
            run_tests=True):
    llm = make_llm()
    registry, prompt, ws = fix_task(finding, root)
    try:
        r, secs = run_task(llm, registry, prompt, FIX_SYSTEM, out_dir, max_steps, tag=tag,
                           guards=default_guards() + [answer_guard("fix")])
        rec = score_fix(ws, finding, run_tests=run_tests)
        rec.update({"stop_reason": r.stop_reason, "steps": r.steps, "tool_calls": r.tool_calls,
                    "guard_rejections": r.guard_rejections, "guard_recoveries": r.guard_recoveries,
                    "seconds": round(secs, 1), "final_text": r.final_text[-3000:],
                    "answer": extract_json(r.final_text)})
        rec.update(_llm_cost(llm, r))
        if out_dir and rec["diff"]:
            with open(os.path.join(out_dir, "%s.diff" % tag), "w") as f:
                f.write(rec["diff"])
    finally:
        ws.cleanup()
    return rec


def main(argv=None):
    import argparse
    from agentloop.adapters import ClaudeCLILLM
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["kill", "review", "fix", "oracle", "mutant-diff", "score-kill"])
    ap.add_argument("--source-file", help="oracle/mutant-diff/score-kill: Whence program file")
    ap.add_argument("--mutant-id", help="mutant-diff/score-kill: mutant id from --mutation-json")
    ap.add_argument("--root", default=WHENCE_ROOT)
    ap.add_argument("--out", help="output directory (kill/review/fix)")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--mutation-json", help="kill: mutation report with survivors")
    ap.add_argument("--only", help="kill: comma list of mutant ids")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--test-file", help="kill: append pinned tests here")
    ap.add_argument("--verify", action="store_true", help="kill: re-run suite per killed mutant")
    ap.add_argument("--files", default="whence/interp.py")
    ap.add_argument("--focus", default="")
    ap.add_argument("--read-budget", type=int, default=0, help="review: hard cap on outline/read_file/search calls")
    ap.add_argument("--finding", help="fix: JSON file with program/oracle/detail")
    ap.add_argument("--no-tests", action="store_true")
    a = ap.parse_args(argv)
    # tool-only modes: let an external agent (a subagent, a human) play the
    # model against exactly the tools and scorer the harness uses
    if a.mode == "oracle":
        with open(a.source_file, encoding="utf-8") as f:
            print(OracleTool(a.root).run(f.read()).output)
        return 0
    if a.mode in ("mutant-diff", "score-kill"):
        sv = [d for d in K.load_survivors(a.mutation_json) if d["id"] == a.mutant_id] \
            or [d for d in json.load(open(a.mutation_json))["mutants"] if d["id"] == a.mutant_id]
        if not sv:
            print("no mutant %s in %s" % (a.mutant_id, a.mutation_json))
            return 2
        m = K.rebuild_mutants(a.root, sv)[0]
        tool = MutantDiffTool(a.root, m)
        try:
            with open(a.source_file, encoding="utf-8") as f:
                src = f.read()
            if a.mode == "mutant-diff":
                print(tool.run(src).output)
            else:
                rec = score_kill(json.dumps({"verdict": "killed", "program": src}), tool)
                rec.update({"mutant": m.id, "description": m.description, "line": m.lineno})
                print(json.dumps(rec, indent=1, ensure_ascii=False))
        finally:
            tool.cleanup()
        return 0
    if not a.out:
        ap.error("--out is required for kill/review/fix")
    os.makedirs(a.out, exist_ok=True)
    make_llm = lambda: ClaudeCLILLM(model=a.model, timeout_s=600)   # noqa: E731

    def emit(rec):
        print(json.dumps(rec, ensure_ascii=False)[:600], flush=True)

    if a.mode == "kill":
        survivors = K.load_survivors(a.mutation_json)
        if a.only:
            ids = set(a.only.split(","))
            survivors = [s for s in survivors if s["id"] in ids]
        if a.limit:
            survivors = survivors[:a.limit]
        ms = K.rebuild_mutants(a.root, survivors)
        res = run_kill(make_llm, ms, a.root, a.out, a.max_steps, a.test_file, a.verify, emit)
    elif a.mode == "review":
        res = run_review(make_llm, a.root, tuple(a.files.split(",")), a.focus, a.out, a.max_steps,
                         read_budget=a.read_budget or None)
        emit(res)
    else:
        with open(a.finding) as f:
            finding = json.load(f)
        res = run_fix(make_llm, finding, a.root, a.out, a.max_steps, run_tests=not a.no_tests)
        emit(res)
    with open(os.path.join(a.out, "%s-results.json" % a.mode), "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

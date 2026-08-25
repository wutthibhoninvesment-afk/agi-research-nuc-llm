"""Repair benchmark: mutants as injected bugs with known ground truth (round 101).

Rounds 5–29 measured the model as a *finder* (review precision) and a
*killer* (survivor kill rate). Nothing measured it as a *fixer* on a bug
whose true fix is known — and the campaign already owns 1000+ such bugs:
every KILLED mutant is a one-token defect with a failing test and an exact
answer (the original line). So:

  inject   copy the checkout, write the mutant's source over the file, run
           `pytest -x` in the copy to capture the failure the model will see
           (the CI signal: last N lines, first failing test id).
  repair   the model gets region tools + edit_file + pytest + whence_run +
           oracle_check, all sandboxed to the copy, and the failure text.
           The tests are declared correct; editing tests/ is cheating and
           counted as such.
  score    three levels, each checked by tools the model did not write:
             green      the full suite passes in the copy and tests/ is untouched
             localized  the diff touches the mutated site (±3 lines, in the
                        injected file's own numbering — generate() re-unparses
                        the module, so line numbers differ from the checkout)
             exact      ast.dump of the repaired file == ast.dump of the
                        original: the semantic revert, formatting ignored
           plus cost/steps/stop_reason. green-but-not-exact is the interesting
           row (an alternative fix, or a fix that re-greens the suite without
           restoring the semantics); exact-but-not-green cannot happen unless
           the copy's suite is broken for other reasons — recorded, never hidden.

Driven offline by PolicyLLM (tests) and live by ClaudeCLILLM
(`python3 -m swe.repair --mutation-json m.json --n 6 --out dir`); the
campaign wires it as the `repair` stage with a per-mutant checkpoint.
"""

import ast
import difflib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

from agentloop import ToolRegistry
from . import killers as K
from .fuzz import WHENCE_ROOT
from .mutation import _copy_project, generate
from .regiontools import region_tools, CallBudget
from .review import (EditFileTool, OracleTool, WHENCE_PRIMER, _llm_cost, _tag,
                     extract_json, run_task)
from .tools import PytestTool, WhenceRunTool

REPAIR_SYSTEM = """You are an interpreter engineer fixing a regression. The
test suite is correct and must not be edited; the defect is in the
interpreter sources. Localize it from the failing test (read the test with
read_file, then the implementation it exercises with outline + read_file),
make the SMALLEST change that restores the intended semantics with edit_file,
and verify with pytest. Do not paper over the failure with special cases."""

FAILED_RE = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.M)


def _unparsed_original(root, rel):
    """The module text exactly as mutation.generate renders the unmutated
    module (every top-level statement re-unparsed), so diffs against the
    mutant text isolate the mutated site."""
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    return "\n\n".join(ast.unparse(stmt) for stmt in tree.body) + "\n", src


def mutated_site(root, mutant):
    """(first, last) 1-based line numbers of the mutation in the MUTANT's
    own text; falls back to the mutant's original line if the diff is empty."""
    base, _ = _unparsed_original(root, mutant.path)
    a, b = base.splitlines(), mutant.source.splitlines()
    lo, hi = None, None
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        s, e = j1 + 1, max(j2, j1 + 1)
        lo = s if lo is None else min(lo, s)
        hi = e if hi is None else max(hi, e)
    if lo is None:
        return mutant.lineno, mutant.lineno
    return lo, hi


class InjectedWorkspace(object):
    """A scratch copy of the checkout with one mutant written over its file."""

    def __init__(self, root, mutant):
        self.root = os.path.realpath(root)
        self.mutant = mutant
        self.tmp = tempfile.mkdtemp(prefix="repair-")
        self.dst = os.path.join(self.tmp, "proj")
        _copy_project(self.root, self.dst)
        with open(os.path.join(self.dst, mutant.path), "w", encoding="utf-8") as f:
            f.write(mutant.source)
        self.site = mutated_site(self.root, mutant)

    def read(self, rel):
        with open(os.path.join(self.dst, rel), encoding="utf-8") as f:
            return f.read()

    def changed_files(self):
        """Files that differ from the INJECTED state (the model's edits)."""
        out = []
        for dirpath, _, names in os.walk(self.dst):
            for n in names:
                if not n.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, n), self.dst)
                if rel == self.mutant.path:
                    if self.read(rel) != self.mutant.source:
                        out.append(rel)
                    continue
                src = os.path.join(self.root, rel)
                if not os.path.exists(src):
                    out.append(rel)
                    continue
                with open(src, encoding="utf-8") as f1:
                    if f1.read() != self.read(rel):
                        out.append(rel)
        return sorted(out)

    def diff(self):
        chunks = []
        for rel in self.changed_files():
            if rel == self.mutant.path:
                a = self.mutant.source.splitlines(True)
            else:
                src = os.path.join(self.root, rel)
                a = open(src, encoding="utf-8").read().splitlines(True) if os.path.exists(src) else []
            b = self.read(rel).splitlines(True)
            chunks.append("".join(difflib.unified_diff(a, b, "injected/" + rel, "repaired/" + rel)))
        return "".join(chunks)

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def failing_output(dst, test_args=("-q", "-x", "tests"), tail_lines=40, timeout_s=900):
    """Run the suite in the injected copy; return the CI-style signal."""
    cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"] + list(test_args)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=dst, capture_output=True, text=True, timeout=timeout_s)
        text = (p.stdout + p.stderr).strip()
        rc = p.returncode
    except subprocess.TimeoutExpired as e:
        text = ((e.stdout or "") + (e.stderr or "")).strip() + "\n[pytest timed out after %ds]" % timeout_s
        rc = -1
    lines = text.splitlines()
    m = FAILED_RE.findall(text)
    return {"returncode": rc, "seconds": round(time.time() - t0, 1),
            "failing_tests": m, "tail": "\n".join(lines[-tail_lines:])}


def repair_task(root, mutant, failure, max_steps=None, test_args="-q tests", read_budget=None):
    ws = InjectedWorkspace(root, mutant)
    rb = CallBudget(read_budget, "edit with edit_file, verify with pytest, then answer") if read_budget else None
    registry = ToolRegistry(
        region_tools(ws.dst, budget=rb) + [EditFileTool(ws.dst), PytestTool(ws.dst, timeout_s=900),
                                           WhenceRunTool(ws.dst, tag=_tag(ws.dst, "run")), OracleTool(ws.dst)])
    budget = ("You have %d tool steps in total; pytest on the whole suite takes 1-3 "
              "minutes, so run it at most three times.\n" % max_steps) if max_steps else ""
    if read_budget:
        budget += ("outline/read_file/search share a hard budget of %d calls; after that they "
                   "refuse.\n" % read_budget)
    prompt = (WHENCE_PRIMER + "\n"
              "The test suite of this Whence checkout fails. Output of `pytest -x %s`:\n"
              "```\n%s\n```\n"
              "The tests are correct. Find the defect in whence/*.py and fix it with the "
              "smallest change that restores the intended semantics (edit_file replaces one "
              "exact occurrence). Do NOT edit anything under tests/. %s"
              "Reading code: outline a file, then read_file with start/end (200-line "
              "windows); search takes a file or directory plus a context count; whence_run "
              "and oracle_check execute Whence programs against the CURRENT state of the "
              "checkout copy. Verify with pytest (args default to '%s').\n"
              "Finish with a JSON block:\n"
              '```json\n{"root_cause": "...", "files": ["whence/interp.py"], "summary": "..."}\n```'
              % (" ".join(test_args.split()), failure["tail"], budget, test_args))
    return registry, prompt, ws


def _ast_dump(source):
    try:
        return ast.dump(ast.parse(source))
    except SyntaxError:
        return None


def _touched_ranges(before, after):
    """1-based [start, end] ranges of `before` lines that the edit replaced or
    deleted (insertions count as touching the line they sit before)."""
    a, b = before.splitlines(), after.splitlines()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        out.append((i1 + 1, max(i2, i1 + 1)))
    return out


def score_repair(ws, run_tests=True, test_args="-q tests", test_timeout_s=900, slack=3):
    """Verify a repair in the injected workspace. See module docstring."""
    m = ws.mutant
    changed = ws.changed_files()
    rec = {"changed_files": changed, "diff": ws.diff(),
           "test_edits": [f for f in changed if f.startswith("tests" + os.sep) or f.startswith("tests/")],
           "site": list(ws.site)}
    repaired = ws.read(m.path)
    lo, hi = ws.site
    touched = _touched_ranges(m.source, repaired) if m.path in changed else []
    rec["touched"] = touched
    rec["localized"] = any(s <= hi + slack and e >= lo - slack for s, e in touched)
    _, original = _unparsed_original(ws.root, m.path)
    rec["parses"] = _ast_dump(repaired) is not None
    rec["exact"] = rec["parses"] and _ast_dump(repaired) == _ast_dump(original)
    if run_tests:
        r = PytestTool(ws.dst, timeout_s=test_timeout_s).run(test_args)
        rec["tests_green"] = r.ok
        rec["pytest_tail"] = r.output[-600:]
    else:
        rec["tests_green"] = None
    rec["green"] = bool(rec["tests_green"]) and not rec["test_edits"]
    rec["outcome"] = ("exact" if rec["exact"] and rec["green"] else
                      "green" if rec["green"] else
                      "cheated" if rec["test_edits"] and rec["tests_green"] else
                      "localized_not_green" if rec["localized"] else
                      "failed")
    return rec


def killed_pool(mutation_json, ops=None):
    """Killed-by-assertion mutants (not timeouts, not import errors) that a
    repair attempt can be scored on."""
    with open(mutation_json, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for d in data["mutants"]:
        if d["status"] != "killed":
            continue
        if ops and d["op"] not in ops:
            continue
        if "FAILED" not in (d.get("detail") or "") and "failed" not in (d.get("detail") or ""):
            continue
        out.append(d)
    return out


def stratified_sample(dicts, n, seed=0):
    """Round-robin over operators so the sample is not all `ifneg`."""
    rng = random.Random(seed)
    by_op = {}
    for d in dicts:
        by_op.setdefault(d["op"], []).append(d)
    for v in by_op.values():
        rng.shuffle(v)
    ops = sorted(by_op)
    rng.shuffle(ops)
    out = []
    while len(out) < n and any(by_op.values()):
        for op in ops:
            if by_op[op] and len(out) < n:
                out.append(by_op[op].pop())
    return out


def run_repair(make_llm, mutants, root=WHENCE_ROOT, out_dir=None, max_steps=25,
               test_args="-q tests", fail_args=("-q", "-x", "tests"), run_tests=True,
               on_result=None, read_budget=None):
    results = []
    for m in mutants:
        llm = make_llm()
        ws = None
        t0 = time.time()
        try:
            probe = InjectedWorkspace(root, m)
            failure = failing_output(probe.dst, fail_args)
            probe.cleanup()
            registry, prompt, ws = repair_task(root, m, failure, max_steps=max_steps,
                                               test_args=test_args, read_budget=read_budget)
            r, secs = run_task(llm, registry, prompt, REPAIR_SYSTEM, out_dir, max_steps,
                               tag="repair-" + re.sub(r"\W", "_", m.id))
            rec = score_repair(ws, run_tests=run_tests, test_args=test_args)
            rec.update({"mutant": m.id, "op": m.op, "description": m.description, "line": m.lineno,
                        "failing_tests": failure["failing_tests"], "hint_lines": failure["tail"].count("\n") + 1,
                        "stop_reason": r.stop_reason, "steps": r.steps, "tool_calls": r.tool_calls,
                        "seconds": round(time.time() - t0, 1), "answer": extract_json(r.final_text),
                        "final_text": r.final_text[-1500:]})
            rec.update(_llm_cost(llm, r))
            if out_dir and rec["diff"]:
                with open(os.path.join(out_dir, "repair-%s.diff" % re.sub(r"\W", "_", m.id)), "w",
                          encoding="utf-8") as f:
                    f.write(rec["diff"])
        finally:
            if ws is not None:
                ws.cleanup()
        results.append(rec)
        if on_result:
            on_result(rec)
    return results


def summarize(recs):
    n = len(recs)
    by_op = {}
    for r in recs:
        b = by_op.setdefault(r["op"], {"attempted": 0, "green": 0, "exact": 0, "localized": 0})
        b["attempted"] += 1
        b["green"] += bool(r["green"])
        b["exact"] += bool(r["exact"] and r["green"])
        b["localized"] += bool(r["localized"])
    return {"attempted": n,
            "green": sum(1 for r in recs if r["green"]),
            "exact": sum(1 for r in recs if r["exact"] and r["green"]),
            "localized": sum(1 for r in recs if r["localized"]),
            "cheated": sum(1 for r in recs if r["outcome"] == "cheated"),
            "green_not_exact": sum(1 for r in recs if r["green"] and not r["exact"]),
            "cost_usd": round(sum(r.get("cost_usd", 0.0) or 0.0 for r in recs), 4),
            "steps": sum(r.get("steps", 0) or 0 for r in recs),
            "by_op": by_op}


def main(argv=None):
    import argparse
    from agentloop.adapters import ClaudeCLILLM
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mutation-json", required=True)
    ap.add_argument("--root", default=WHENCE_ROOT)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", help="comma list of mutant ids")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--read-budget", type=int, default=0)
    ap.add_argument("--no-tests", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    pool = killed_pool(a.mutation_json)
    if a.only:
        ids = set(a.only.split(","))
        chosen = [d for d in pool if d["id"] in ids]
    else:
        chosen = stratified_sample(pool, a.n, a.seed)
    ms = K.rebuild_mutants(a.root, chosen)
    make_llm = lambda: ClaudeCLILLM(model=a.model, timeout_s=600)   # noqa: E731

    def emit(rec):
        print(json.dumps(dict((k, rec[k]) for k in ("mutant", "outcome", "steps", "cost_usd")
                              if k in rec)), flush=True)
    res = run_repair(make_llm, ms, a.root, a.out, a.max_steps, run_tests=not a.no_tests,
                     on_result=emit, read_budget=a.read_budget or None)
    data = {"model": a.model, "summary": summarize(res), "results": res}
    with open(os.path.join(a.out, "repair-results.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    print(json.dumps(data["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

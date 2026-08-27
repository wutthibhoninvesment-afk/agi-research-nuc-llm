"""AST mutation testing: how good is the test suite at noticing bugs?

For every mutation site in a Python module we produce one *mutant* (a copy of
the module with a single small semantic change), run the test suite against
it, and record whether the suite KILLED it (some test failed / errored / timed
out) or the mutant SURVIVED (suite green). Survivors are test gaps — or
equivalent mutants (no behavioural change) — and are the raw input for
differential test generation (see killers.py).

Operators (each yields the smallest plausible semantic slip):
  cmp    <  <=  >  >=  ==  !=  is/is not  in/not in   swapped with a neighbour
  bool   and <-> or
  not    `not x` -> `x`
  const  True <-> False, int n -> n + 1 (docstrings and other strings skipped)
  arith  + <-> -, * -> +, / -> *, % -> *
  ifneg  `if c:` -> `if not c:`

Nothing here touches the original checkout: every mutant runs inside its own
temporary copy of the project directory.
"""

import ast
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

from .proc import run_capped

_CMP_SWAP = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Is: ast.IsNot, ast.IsNot: ast.Is,
    ast.In: ast.NotIn, ast.NotIn: ast.In,
}
_ARITH_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Add,
               ast.Div: ast.Mult, ast.Mod: ast.Mult}


class Mutant(object):
    def __init__(self, mid, path, lineno, op, description, source, end_lineno=None):
        self.id = mid
        self.path = path            # relative path of the mutated file
        self.lineno = lineno
        self.end_lineno = end_lineno or lineno   # last line of the mutated node
        self.op = op
        self.description = description
        self.source = source        # full mutated module text
        self.status = None          # killed | survived | timeout | error
        self.seconds = 0.0
        self.detail = ""

    def as_dict(self):
        return {"id": self.id, "path": self.path, "line": self.lineno, "end_line": self.end_lineno,
                "op": self.op, "description": self.description, "status": self.status,
                "seconds": round(self.seconds, 2), "detail": self.detail[:300]}


def _sites(tree):
    """Yield (node, op, description, apply, undo) for every mutation site.
    `apply()` changes the node in place; `undo()` restores it. Mutating in
    place and re-unparsing only the enclosing top-level statement keeps
    generation at ~1ms per mutant instead of deep-copying the module."""
    docstrings = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body \
           and isinstance(n.body[0], ast.Expr) \
           and isinstance(getattr(n.body[0], "value", None), ast.Constant) \
           and isinstance(n.body[0].value.value, str):
            docstrings.add(id(n.body[0].value))
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare) and len(n.ops) == 1:
            old = n.ops[0]
            if type(old) in _CMP_SWAP:
                new = _CMP_SWAP[type(old)]
                yield (n, "cmp", "%s -> %s" % (type(old).__name__, new.__name__),
                       lambda n=n, new=new: n.ops.__setitem__(0, new()),
                       lambda n=n, old=old: n.ops.__setitem__(0, old))
        elif isinstance(n, ast.BoolOp):
            old = n.op
            new = ast.Or if isinstance(old, ast.And) else ast.And
            yield (n, "bool", "%s -> %s" % (type(old).__name__, new.__name__),
                   lambda n=n, new=new: setattr(n, "op", new()),
                   lambda n=n, old=old: setattr(n, "op", old))
        elif isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            # `not x` -> `not not x` (== truthiness of x): drops the negation
            # without needing the parent node
            old = n.operand
            yield (n, "not", "drop 'not'",
                   lambda n=n, old=old: setattr(n, "operand", ast.UnaryOp(op=ast.Not(), operand=old)),
                   lambda n=n, old=old: setattr(n, "operand", old))
        elif isinstance(n, ast.Constant) and id(n) not in docstrings:
            old = n.value
            if isinstance(old, bool):
                yield (n, "const", "%r -> %r" % (old, not old),
                       lambda n=n, old=old: setattr(n, "value", not old),
                       lambda n=n, old=old: setattr(n, "value", old))
            elif isinstance(old, int):
                yield (n, "const", "%r -> %r" % (old, old + 1),
                       lambda n=n, old=old: setattr(n, "value", old + 1),
                       lambda n=n, old=old: setattr(n, "value", old))
        elif isinstance(n, ast.BinOp) and type(n.op) in _ARITH_SWAP:
            old = n.op
            new = _ARITH_SWAP[type(old)]
            yield (n, "arith", "%s -> %s" % (type(old).__name__, new.__name__),
                   lambda n=n, new=new: setattr(n, "op", new()),
                   lambda n=n, old=old: setattr(n, "op", old))
        elif isinstance(n, ast.If):
            old = n.test
            yield (n, "ifneg", "negate if-condition",
                   lambda n=n, old=old: setattr(n, "test", ast.UnaryOp(op=ast.Not(), operand=old)),
                   lambda n=n, old=old: setattr(n, "test", old))


def generate(source, rel_path, ops=None):
    """All mutants of one module's source text, in source order."""
    tree = ast.parse(source)
    owner = {}                       # id(node) -> index of enclosing top-level stmt
    for idx, stmt in enumerate(tree.body):
        for n in ast.walk(stmt):
            owner[id(n)] = idx
    parts = [ast.unparse(stmt) for stmt in tree.body]
    out = []
    for i, (node, op, desc, apply, undo) in enumerate(_sites(tree)):
        if ops and op not in ops:
            continue
        idx = owner[id(node)]
        apply()
        try:
            mutated_stmt = ast.unparse(tree.body[idx])
        finally:
            undo()
        text = "\n\n".join(parts[:idx] + [mutated_stmt] + parts[idx + 1:]) + "\n"
        mid = "%s:%d:%s#%d" % (os.path.basename(rel_path), node.lineno, op, i)
        out.append(Mutant(mid, rel_path, node.lineno, op, desc, text,
                          getattr(node, "end_lineno", None)))
    return out


def _copy_project(project_root, dst):
    shutil.copytree(project_root, dst, ignore=shutil.ignore_patterns(
        "__pycache__", ".pytest_cache", "*.pyc",
        ".venv", "research-env", "*.egg-info", ".git"))


def run_mutant(m, project_root, test_cmd, timeout_s=120.0):
    tmp = tempfile.mkdtemp(prefix="mut-")
    try:
        dst = os.path.join(tmp, "proj")
        _copy_project(project_root, dst)
        with open(os.path.join(dst, m.path), "w", encoding="utf-8") as f:
            f.write(m.source)
        r = run_capped(test_cmd, dst, timeout_s)
        m.seconds = r.seconds
        if r.timed_out:
            m.status = "timeout"
            m.detail = "test run exceeded %.0fs (process group killed)" % timeout_s
        elif r.returncode == 0:
            m.status = "survived"
        else:
            m.status = "killed"
            tail = r.output.strip().splitlines()
            m.detail = "\n".join(tail[-3:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return m


class MutationReport(object):
    def __init__(self, mutants, seconds):
        self.mutants = mutants
        self.seconds = seconds

    @property
    def killed(self):
        return [m for m in self.mutants if m.status in ("killed", "timeout")]

    @property
    def survived(self):
        return [m for m in self.mutants if m.status == "survived"]

    @property
    def score(self):
        return len(self.killed) / len(self.mutants) if self.mutants else 0.0

    def summary(self):
        by_op = {}
        for m in self.mutants:
            k, s = by_op.get(m.op, (0, 0))
            by_op[m.op] = (k + (m.status != "survived"), s + (m.status == "survived"))
        lines = ["mutation: %d mutants, %d killed, %d survived, score %.1f%% (%.0fs)"
                 % (len(self.mutants), len(self.killed), len(self.survived),
                    100 * self.score, self.seconds)]
        for op in sorted(by_op):
            k, s = by_op[op]
            lines.append("  %-6s killed %3d  survived %3d" % (op, k, s))
        for m in self.survived:
            lines.append("  SURVIVED %-32s line %4d  %s" % (m.id, m.lineno, m.description))
        return "\n".join(lines)

    def as_dict(self):
        return {"total": len(self.mutants), "killed": len(self.killed),
                "survived": len(self.survived), "score": round(self.score, 4),
                "seconds": round(self.seconds, 1),
                "mutants": [m.as_dict() for m in self.mutants]}


def mutation_test(project_root, rel_paths, test_cmd, workers=4, timeout_s=120.0,
                  ops=None, limit=None, on_result=None):
    mutants = []
    for rel in rel_paths:
        with open(os.path.join(project_root, rel), encoding="utf-8") as f:
            mutants.extend(generate(f.read(), rel, ops=ops))
    if limit:
        mutants = mutants[:limit]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for m in ex.map(lambda m: run_mutant(m, project_root, test_cmd, timeout_s), mutants):
            if on_result:
                on_result(m)
    return MutationReport(mutants, time.time() - t0)


DEFAULT_TEST_CMD = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests"]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--json")
    a = ap.parse_args()
    rep = mutation_test(a.project, a.files, DEFAULT_TEST_CMD, workers=a.workers,
                        limit=a.limit,
                        on_result=lambda m: print("%-8s %s" % (m.status, m.id), flush=True))
    print(rep.summary())
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rep.as_dict(), f, indent=1)

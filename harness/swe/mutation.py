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


# --------------------------------------------------------- run classification --
#
# Round 349 (harness A). `Mutant.status` has declared `error` as a fourth
# outcome since this module was written, and nothing ever set it: `run_mutant`
# read `returncode == 0` as SURVIVED and *every* non-zero code as KILLED. That
# conflates "the suite ran and a test failed" (the only thing that kills a
# mutant) with "the suite never ran at all", and it fails in the reassuring
# direction — an environment that cannot run tests scores a perfect 100%.
#
# Observed live, not hypothesised. Round 348 a separate system appended a
# duplicate `[project.optional-dependencies]` table to the UNTRACKED
# `languages/whence/pyproject.toml`; `_copy_project` copies that file into
# every mutant tree, and pytest parses it during config discovery before
# collecting anything, so each mutant exited 4 (usage error). Round 349's A/B
# over the same 6 mutants of `whence/values.py` with the same test command:
#
#     pyproject.toml broken    6 killed, 0 survived, score 1.00
#     pyproject.toml repaired  3 killed, 3 survived, score 0.50
#
# The broken tree did not merely mislead, it inverted the signal: the run that
# tested nothing reported twice the mutation score of the run that worked.
#
# pytest's exit codes distinguish these cases and we were throwing them away:
#   0 all passed | 1 TESTS FAILED | 2 interrupted | 3 internal error
#   4 usage error (this bug) | 5 no tests collected
# Only 1 is evidence about the mutant. 2-5 say the harness broke.
#
# Negative codes (killed by a signal) stay KILLED deliberately: a mutant that
# segfaults the interpreter is a real behavioural difference the suite caught.

_PYTEST_TESTS_FAILED = 1
# 2 interrupted, 3 internal error, 4 usage/config error, 5 nothing collected.
_PYTEST_NO_EVIDENCE = frozenset({2, 3, 4, 5})


def is_pytest_cmd(cmd):
    """True when `cmd` invokes pytest, whose exit-code table we can trust.

    `mutation_test` takes an arbitrary `test_cmd`, and a generic runner's
    non-zero codes carry no agreed meaning — for those we must keep the old
    any-failure-is-a-kill rule rather than guess.
    """
    for tok in cmd or ():
        tok = str(tok)
        if tok == "pytest" or tok.endswith("/pytest") or tok.endswith("\\pytest"):
            return True
    return False


def classify_mutant_run(returncode, output, cmd):
    """-> "survived" | "killed" | "error" for one finished mutant run.

    "error" means the run produced no evidence either way. Such a mutant is
    neither killed nor survived; see `MutationReport.errored`.
    """
    if returncode == 0:
        return "survived"
    if returncode < 0:
        # Signal death. A mutant that segfaults or hangs-then-gets-killed IS
        # a behavioural difference the suite caught, whatever the runner.
        return "killed"
    if is_pytest_cmd(cmd):
        # Whitelist, not blacklist. Under pytest exactly one positive code
        # means "a test failed"; treating any OTHER code as a kill is the
        # assumption that produced this whole defect, so an undocumented
        # code (a plugin's own, say) is no evidence rather than a free kill.
        return "killed" if returncode == _PYTEST_TESTS_FAILED else "error"
    # A generic runner's exit codes carry no agreed meaning, so keep the
    # historical any-failure-is-a-kill rule rather than guess. The baseline
    # pre-flight in `mutation_test` is what covers these callers.
    return "killed"


class BaselineNotGreen(RuntimeError):
    """The UNMUTATED project does not pass its own suite.

    Raised by `mutation_test`'s pre-flight. Every mutation score is a
    comparison against a green baseline; without one the number is
    meaningless, and — as round 349's A/B showed — meaningless in the
    flattering direction. Carries the failing run's tail so the caller can
    see whether it is a config error, a collection error, or a genuinely
    red test.
    """

    def __init__(self, returncode, tail):
        self.returncode = returncode
        self.tail = tail
        super(BaselineNotGreen, self).__init__(
            "baseline run of the unmutated project exited %s (expected 0); "
            "a mutation score against a non-green baseline is not evidence. "
            "Tail:\n%s" % (returncode, tail))


def baseline_check(project_root, test_cmd, timeout_s=120.0):
    """Run `test_cmd` against an unmutated COPY of the project.

    Deliberately a copy made by `_copy_project`, not the original checkout:
    round 349's defect lived in a file that only matters once copied into the
    mutant tree, so a baseline run against the original would have missed it.
    This exercises byte-for-byte the same path every mutant takes.
    """
    tmp = tempfile.mkdtemp(prefix="mut-baseline-")
    try:
        dst = os.path.join(tmp, "proj")
        _copy_project(project_root, dst)
        r = run_capped(test_cmd, dst, timeout_s)
        return {"returncode": -9 if r.timed_out else r.returncode,
                "timed_out": r.timed_out,
                "seconds": round(r.seconds, 2),
                "tail": (r.output or "").strip()[-800:]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _copy_project(project_root, dst):
    """Copy a project into a throwaway tree.

    `node_modules` joined the ignore list in round 413, when `guardpin.py`
    became the first caller to pass the REPO ROOT rather than
    `languages/whence`: node_modules is 468 MB on this box against ~26 MB for
    everything else, so copying it made a per-pin copy a 9-second operation
    instead of a 1.8-second one. Nothing in this repo imports Python from
    there — it holds one npm dependency, `@anthropic-ai/claude-code` — and
    `test_copy_project_ignores_the_npm_tree` pins that the list is applied.
    """
    shutil.copytree(project_root, dst, ignore=shutil.ignore_patterns(
        "__pycache__", ".pytest_cache", "*.pyc",
        ".venv", "research-env", "*.egg-info", ".git", "node_modules"))


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
        else:
            m.status = classify_mutant_run(r.returncode, r.output, test_cmd)
            if m.status != "survived":
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
    def errored(self):
        """Mutants whose run produced no evidence (round 349).

        Neither killed nor survived. They still count in `score`'s
        denominator, so an errored campaign scores LOW rather than high --
        the safe direction, and the opposite of the pre-349 behaviour that
        scored a non-running suite at 100%.
        """
        return [m for m in self.mutants if m.status == "error"]

    @property
    def score(self):
        """Killed / ALL mutants -- denominator deliberately unchanged.

        Round 349 added `errored` but did NOT redefine this, for the reason
        round 348 recorded about `confirmed_span_s`: published figures and
        `campaign.py`'s own independent `killed / total` recomputation
        (campaign.py:383) depend on the current meaning. `valid_score` is a
        separate field.
        """
        return len(self.killed) / len(self.mutants) if self.mutants else 0.0

    @property
    def valid_score(self):
        """Killed / (killed + survived) -- the score over evidence-bearing
        runs only. Equals `score` exactly when nothing errored."""
        n = len(self.killed) + len(self.survived)
        return len(self.killed) / n if n else 0.0

    def summary(self):
        by_op = {}
        for m in self.mutants:
            k, s = by_op.get(m.op, (0, 0))
            by_op[m.op] = (k + (m.status != "survived"), s + (m.status == "survived"))
        lines = ["mutation: %d mutants, %d killed, %d survived, score %.1f%% (%.0fs)"
                 % (len(self.mutants), len(self.killed), len(self.survived),
                    100 * self.score, self.seconds)]
        if self.errored:
            # First line after the headline, not buried under the per-op
            # table: an errored campaign is not a weak result, it is a
            # non-result, and the reader has to see that before the number.
            lines.append(
                "  !! %d mutant(s) ERRORED -- the suite did not run for them; "
                "this campaign is not evidence. valid_score %.1f%% over the "
                "%d run(s) that did produce a verdict."
                % (len(self.errored), 100 * self.valid_score,
                   len(self.killed) + len(self.survived)))
            for m in self.errored[:3]:
                lines.append("  ERROR    %-32s %s" % (m.id, m.detail.splitlines()[-1][:90] if m.detail else ""))
        for op in sorted(by_op):
            k, s = by_op[op]
            lines.append("  %-6s killed %3d  survived %3d" % (op, k, s))
        for m in self.survived:
            lines.append("  SURVIVED %-32s line %4d  %s" % (m.id, m.lineno, m.description))
        return "\n".join(lines)

    def as_dict(self):
        return {"total": len(self.mutants), "killed": len(self.killed),
                "survived": len(self.survived), "score": round(self.score, 4),
                # Round 349, additive: existing readers of the four keys
                # above are untouched.
                "errored": len(self.errored),
                "valid_score": round(self.valid_score, 4),
                "seconds": round(self.seconds, 1),
                "mutants": [m.as_dict() for m in self.mutants]}


def mutation_test(project_root, rel_paths, test_cmd, workers=4, timeout_s=120.0,
                  ops=None, limit=None, on_result=None, baseline=True):
    """Score `rel_paths`' mutants against `test_cmd`.

    `baseline=True` (round 349, the default) runs the suite once against an
    UNMUTATED copy first and raises `BaselineNotGreen` unless it exits 0.
    One extra run per campaign, against N mutant runs -- and it is the only
    check that catches the whole family of "the score is high because the
    suite is not running", of which round 348's broken `pyproject.toml` was
    one instance and a single pre-existing failing test is another (that one
    pins every mutant to `killed` just as effectively, and no per-mutant
    exit-code classification can see it).

    Pass `baseline=False` only when the caller has already established a
    green baseline itself -- `campaign.py` re-runs recorded mutants against
    a checkout it has separately verified.
    """
    if baseline:
        b = baseline_check(project_root, test_cmd, timeout_s)
        if b["returncode"] != 0:
            raise BaselineNotGreen(b["returncode"], b["tail"])
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

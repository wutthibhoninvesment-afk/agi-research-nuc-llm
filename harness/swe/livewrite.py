#!/usr/bin/env python3
"""livewrite.py — which tests create files inside a tree other suites copy.

Round 521 (SWE-loop D). The WRITE side of round 343's
`harness/tests/test_snapshot_race.py`, which found the READ side.

THE EPISODE THIS COMES FROM
---------------------------
`logs/health_round_517.log`, one failure, four rounds of consequence:

    ERROR collecting harness/tests/test_swe_oraclekill.py
    harness/tests/test_swe_oraclekill.py:37: in <module>
        _copy_project(OK.WHENCE_ROOT, ROOT)
    harness/swe/mutation.py:493: in _copy_project
        shutil.copytree(project_root, dst, ...)
    shutil.Error: [('…/languages/whence/_r438_suffix.lang', …,
                    "[Errno 2] No such file or directory: …")]
    !!!! Interrupted: 1 error during collection !!!!

`languages/whence/tests/test_polarity.py::test_the_two_counterexamples_disagree_when_actually_run`
writes `_r438_suffix.lang` into the LIVE `languages/whence/` directory, runs
`run.py` on it, and `os.remove`s it in a `finally`. The window is one
subprocess wide — about a second, twice per whence-suite run. The driver runs
the whence health check and the harness health check concurrently, so the
harness side's `shutil.copytree` listed that name with `os.scandir` and found
it gone by the time `copy2` reached it.

The amplification is what makes it expensive rather than annoying. The copy
is at MODULE SCOPE, so the failure is a *collection* error: pytest reports
`Interrupted: 1 error during collection` and the whole `harness/tests/`
directory yields nothing. `test_tiering.py` shells out to collect that
directory and asserts rc 0, so it went red — and because it had never been
red before, `harness/crosstrack-registry.json` had no entry for it, which
made `redattrib.py audit` fail R001, which reddened
`harness/tests/test_redattrib.py` ×2 for rounds 518, 519, 520 and 521.

One vanished untracked scratch file, in another track's tree, cost four
rounds of red debt in a suite whose owner did not cause it.

WHY A SCANNER AND NOT A GREP
----------------------------
Round 343 wrote the sentence this module inherits: *a grep for a NAME cannot
find a SHAPE*. `grep -rn _r438` finds one file, which is the one instance
already known. The shape is "a write whose path is rooted at the live
checkout rather than at a temporary directory", and the root can be spelled
`WHENCE_ROOT`, `AGI_ROOT`, a module constant, or — as in the instance above —
a FUNCTION-LOCAL `here = os.path.dirname(os.path.dirname(
os.path.abspath(__file__)))`. None of those share a token.

So the rule is a tiny kind analysis over path expressions. Every path
expression is `live`, `tmp` or `unknown`:

    __file__                                        -> live
    a name/attribute whose leaf is a live-root name -> live
    tempfile.mkdtemp() / gettempdir() / …           -> tmp
    os.path.{join,dirname,abspath,realpath,…}(X)    -> kind of X
    X % …, X + …, f"{X}…"                           -> kind of X
    a Name                                          -> what it was bound to
    anything else                                   -> unknown

and a write call whose destination expression is `live` is a finding. `tmp`
and `unknown` are never findings: a scanner that guessed on `unknown` would
be reporting its own ignorance as a defect, which is the failure mode this
program keeps scoring.

STATED LIMITS (round 343's discipline: record them, do not leave them to be
rediscovered)
  * Name binding is flow-insensitive and single-assignment-wins-last within a
    scope; a name rebound in a branch is read as its last binding.
  * A root that arrives as a FUNCTION PARAMETER is `unknown`, so a helper
    `def _write(root, name)` called with a live root is invisible. Pytest's
    `tmp_path` / `tmpdir` fixtures are therefore also invisible, which is
    the safe direction.
  * A root reached through a container (`ROOTS["whence"]`) or a function
    return is `unknown`.
  * Only the call shapes in `WRITE_CALLS` are writes. `subprocess` writing
    into the tree via a shelled-out command is not visible here.
  * The default population is TEST files under the four suite directories.
    Production code writes into the tree by design (`state/*.jsonl` ledgers);
    the defect is specifically a *test* creating a transient file inside a
    tree another suite copies.

WHAT IT IS NOT
--------------
It is not a fail-closed whole-tree gate, and that is this round's own finding
applied to itself. Round 511 measured that every red in this series was
manufactured by a whole-tree fail-closed assertion living in ONE track's
suite: any track can turn it red, only the hosting track runs it, so the
diagnosis lands on somebody who did not cause it, one rotation late. `scan`
and `check` are MEASUREMENTS and exit 0 unless `--strict` is passed. The
live test in `harness/tests/test_swe_livewrite.py` pins the REVIEWED set
below — a decision a human made — rather than a property of whatever the
tree happens to hold next round.

Commands
--------
    python3 harness/swe/livewrite.py scan [--all] [--json]
        Every live-rooted write, with its root expression and how the kind
        was decided. Exit 0.

    python3 harness/swe/livewrite.py check [--strict] [--json]
        Findings that are NOT in `REVIEWED`. Exit 0, or 1 with --strict.

    python3 harness/swe/livewrite.py staged [--strict]
        The same rule over the STAGED blobs of a commit — the pre-commit
        shape, where the author is still present. Silent and green when no
        test file is staged.
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
_HARNESS = os.path.dirname(HERE)
if _HARNESS not in sys.path:
    sys.path.insert(0, _HARNESS)

try:                                                  # package import
    from .mutation import COPY_IGNORE
except ImportError:                                   # run as a script
    from swe.mutation import COPY_IGNORE              # noqa: F401

#: Directories whose `test_*.py` files are the default population.
SUITE_DIRS = ("harness/tests", "languages/whence/tests", "nuc/tests",
              "skills")

#: Leaf identifiers that name a live checkout root anywhere in this repo.
#: `ROOT`/`HERE` are deliberately NOT here: both are used for temporary
#: roots as often as live ones (`ROOT = os.path.join(_PIN_TMP, "proj")` in
#: `test_swe_oraclekill.py`), so they are resolved by their BINDING instead.
LIVE_ROOT_LEAVES = frozenset((
    "WHENCE_ROOT", "AGI_ROOT", "REPO_ROOT", "PROJECT_ROOT", "CHECKOUT_ROOT",
))

#: Path-preserving calls: the kind of the result is the kind of arg 0.
PATH_OPS = frozenset((
    "join", "dirname", "abspath", "realpath", "normpath", "expanduser",
    "relpath", "sep", "fspath",
))

#: Calls that mint a temporary location.
TMP_CALLS = frozenset((
    "mkdtemp", "gettempdir", "mkstemp", "TemporaryDirectory",
    "NamedTemporaryFile", "TemporaryFile",
))

#: `(callable spelling, index of the destination argument)`.
WRITE_CALLS = {
    "open": 0, "mkdir": 0, "makedirs": 0, "mknod": 0, "touch": 0,
    "write_text": 0, "write_bytes": 0,
    "copy": 1, "copy2": 1, "copyfile": 1, "copytree": 1, "move": 1,
    "rename": 1, "replace": 1, "symlink": 1, "link": 1,
}

#: The `open()` modes that CREATE. A read-only open of a live path is not a
#: finding — reading the checkout is what most of these suites are for.
WRITE_MODES = ("w", "a", "x", "+")

LIVE, TMP, UNKNOWN = "live", "tmp", "unknown"

#: Reviewed and accepted. path -> (lineno-independent reason). A finding on
#: one of these files is not reported by `check`. Round 521 reviewed every
#: entry in the scan; this dict is the record of that review, and
#: `test_the_reviewed_set_is_exactly_the_files_round_521_read` pins it.
REVIEWED = {}


# --------------------------------------------------------------------------
# kind analysis
# --------------------------------------------------------------------------

def _leaf(node):
    """Final identifier of a Name/Attribute chain, else None."""
    while isinstance(node, ast.Attribute):
        return node.attr
    return node.id if isinstance(node, ast.Name) else None


def _callee(node):
    """`open`, `os.path.join` -> `join`, `p.write_text` -> `write_text`."""
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    return getattr(f, "id", None)


def kind_of(node, env):
    """`live`, `tmp` or `unknown` for a path expression."""
    if node is None:
        return UNKNOWN
    if isinstance(node, ast.Name):
        if node.id == "__file__" or node.id in LIVE_ROOT_LEAVES:
            return LIVE
        return env.get(node.id, UNKNOWN)
    if isinstance(node, ast.Attribute):
        leaf = node.attr
        if leaf in LIVE_ROOT_LEAVES:
            return LIVE
        # `td.name` for a TemporaryDirectory bound to `td`
        base = kind_of(node.value, env) if isinstance(
            node.value, (ast.Name, ast.Attribute)) else UNKNOWN
        return base if base == TMP else env.get(leaf, UNKNOWN)
    if isinstance(node, ast.Call):
        name = _callee(node)
        if name in TMP_CALLS:
            return TMP
        if name in PATH_OPS and node.args:
            return kind_of(node.args[0], env)
        if name == "Path" and node.args:
            return kind_of(node.args[0], env)
        return UNKNOWN
    if isinstance(node, ast.BinOp):                  # "%s" % x, a + b
        left = kind_of(node.left, env)
        return left if left != UNKNOWN else kind_of(node.right, env)
    if isinstance(node, ast.JoinedStr):
        for v in node.values:
            if isinstance(v, ast.FormattedValue):
                k = kind_of(v.value, env)
                if k != UNKNOWN:
                    return k
        return UNKNOWN
    return UNKNOWN


def _bind(env, stmt):
    """Record `name = <path expr>` into `env`, in place."""
    if isinstance(stmt, ast.Assign):
        targets, value = stmt.targets, stmt.value
    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        targets, value = [stmt.target], stmt.value
    elif isinstance(stmt, ast.withitem):
        if stmt.optional_vars is None:
            return
        targets, value = [stmt.optional_vars], stmt.context_expr
    else:
        return
    k = kind_of(value, env)
    for t in targets:
        if isinstance(t, ast.Name):
            env[t.id] = k


#: Statements that open a NEW binding scope. `_scope_env` must not descend
#: into them: round 521's first run of this scanner reported three findings
#: in `harness/tests/test_swe_mutation.py::_tiny_checkout`, whose root is a
#: PARAMETER, because a `root = WHENCE_ROOT` binding inside an unrelated
#: function in the same file had leaked into the module environment. A
#: scanner that reports its own scope bug as a defect in somebody else's test
#: is the exact failure this module is about.
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _walk_scope(node):
    """`ast.walk`, but stopping at a nested binding scope."""
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        for child in ast.iter_child_nodes(cur):
            if not isinstance(child, _SCOPES):
                stack.append(child)


def _bind_src(srcenv, stmt):
    """Same as `_bind`, but keeps the bound EXPRESSION, not its kind."""
    if isinstance(stmt, ast.Assign):
        targets, value = stmt.targets, stmt.value
    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        targets, value = [stmt.target], stmt.value
    elif isinstance(stmt, ast.withitem):
        if stmt.optional_vars is None:
            return
        targets, value = [stmt.optional_vars], stmt.context_expr
    else:
        return
    for t in targets:
        if isinstance(t, ast.Name):
            srcenv[t.id] = value


def expand(node, srcenv, depth=4):
    """`path` -> `os.path.join(ROOT, 'tests', '__pycache__', 'v27_tmp.lang')`.

    Substitutes names by their bound expression, up to `depth` hops. Used
    for BOTH the human-readable `dest` and `ignored_by_copiers`: a write
    whose destination lands under a directory every copier already skips
    (`__pycache__`, `.git`, `node_modules`) cannot cause the round-517
    abort, and saying so needs the literal segments the bare name hides.
    """
    if depth <= 0:
        return ast.unparse(node)
    if isinstance(node, ast.Name) and node.id in srcenv:
        return expand(srcenv[node.id], srcenv, depth - 1)
    if isinstance(node, ast.Call):
        args = ", ".join(expand(a, srcenv, depth - 1) for a in node.args)
        return "%s(%s)" % (ast.unparse(node.func), args)
    if isinstance(node, ast.BinOp):
        return "%s %s %s" % (expand(node.left, srcenv, depth - 1),
                             ast.unparse(node.op).strip() or "%",
                             ast.unparse(node.right))
    return ast.unparse(node)


def ignored_by_copiers(expanded):
    """True when a literal segment of the path is in `COPY_IGNORE`."""
    import fnmatch
    for tok in re.findall(r"['\"]([^'\"]*)['\"]", expanded):
        for part in tok.replace("\\", "/").split("/"):
            if any(fnmatch.fnmatch(part, pat) for pat in COPY_IGNORE):
                return True
    return False


def _scope_env(body, base):
    """Names bound in `body`, NOT descending into nested scopes.

    Flow-insensitive on purpose: two passes would let a name bound after its
    use still be seen, which is what a reader of the file does.
    """
    env = dict(base)
    for node in body:
        if isinstance(node, _SCOPES):
            continue
        for sub in _walk_scope(node):
            if isinstance(sub, (ast.Assign, ast.AnnAssign)):
                _bind(env, sub)
            elif isinstance(sub, (ast.With, ast.AsyncWith)):
                for item in sub.items:
                    _bind(env, item)
    return env


def _is_write(call, env):
    """`(destination-expression, why)` if this call creates, else None."""
    name = _callee(call)
    if name not in WRITE_CALLS:
        return None
    if name in ("open",):
        mode = call.args[1] if len(call.args) > 1 else next(
            (k.value for k in call.keywords if k.arg == "mode"), None)
        lit = mode.value if isinstance(mode, ast.Constant) else None
        if not isinstance(lit, str) or not any(c in lit for c in WRITE_MODES):
            return None
        why = "open(..., %r)" % lit
    elif name in ("write_text", "write_bytes", "touch", "mkdir"):
        # method form: the destination is the receiver, not an argument
        recv = call.func.value if isinstance(call.func, ast.Attribute) else None
        return (recv, "%s() on a live-rooted path" % name) if recv else None
    else:
        why = "%s()" % name
    idx = WRITE_CALLS[name]
    if len(call.args) <= idx:
        return None
    return call.args[idx], why


def _src_env(body, base):
    """`_scope_env`'s twin over bound EXPRESSIONS rather than kinds."""
    env = dict(base)
    for node in body:
        if isinstance(node, _SCOPES):
            continue
        for sub in _walk_scope(node):
            if isinstance(sub, (ast.Assign, ast.AnnAssign)):
                _bind_src(env, sub)
            elif isinstance(sub, (ast.With, ast.AsyncWith)):
                for item in sub.items:
                    _bind_src(env, item)
    return env


def scan_source(src, path="<str>"):
    """Findings for one module's source."""
    tree = ast.parse(src)
    mod_env = _scope_env(tree.body, {})
    mod_src = _src_env(tree.body, {})
    out = []

    def visit(body, env, srcenv, scope):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = _scope_env(node.body, env)
                isrc = _src_env(node.body, srcenv)
                for a in list(node.args.args) + list(node.args.kwonlyargs):
                    inner[a.arg] = UNKNOWN          # a parameter is unknown
                    isrc.pop(a.arg, None)
                visit(node.body, inner, isrc, node.name)
                continue
            if isinstance(node, ast.ClassDef):
                visit(node.body, _scope_env(node.body, env),
                      _src_env(node.body, srcenv), scope)
                continue
            for sub in _walk_scope(node):
                if not isinstance(sub, ast.Call):
                    continue
                hit = _is_write(sub, env)
                if hit is None:
                    continue
                dest, why = hit
                if kind_of(dest, env) != LIVE:
                    continue
                shown = expand(dest, srcenv)
                out.append({
                    "path": path,
                    "lineno": sub.lineno,
                    "scope": scope,
                    "call": why,
                    "dest": shown,
                    "ignored_by_copiers": ignored_by_copiers(shown),
                })

    visit(tree.body, mod_env, mod_src, "<module>")
    return out


def scan_file(path, rel=None):
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return []
    try:
        return scan_source(src, rel or path)
    except SyntaxError:
        return []


# --------------------------------------------------------------------------
# populations
# --------------------------------------------------------------------------

def test_files(root=ROOT, everything=False):
    """The default population: `test_*.py` under the four suite dirs."""
    out = []
    for d in SUITE_DIRS:
        base = os.path.join(root, d)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames
                           if x not in ("__pycache__", ".venv", "node_modules")]
            for fn in sorted(filenames):
                if not fn.endswith(".py"):
                    continue
                if not everything and not fn.startswith("test_"):
                    continue
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def scan(root=ROOT, everything=False):
    findings = []
    for p in test_files(root, everything):
        findings.extend(scan_file(p, os.path.relpath(p, root)))
    return findings


def check(root=ROOT, everything=False, include_ignored=False):
    """Findings a copier could actually trip over, minus the reviewed ones."""
    return [f for f in scan(root, everything)
            if f["path"] not in REVIEWED
            and (include_ignored or not f["ignored_by_copiers"])]


def staged(root=ROOT):
    """The same rule over staged blobs. Returns findings; `[]` when the
    commit stages no test file, which is the common case and is silent."""
    try:
        names = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=root, capture_output=True, text=True, timeout=60).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for rel in names:
        if not rel.endswith(".py") or not os.path.basename(rel).startswith("test_"):
            continue
        if not any(rel.startswith(d + "/") for d in SUITE_DIRS):
            continue
        blob = subprocess.run(["git", "show", ":" + rel], cwd=root,
                              capture_output=True, text=True, timeout=60)
        if blob.returncode != 0:
            continue
        try:
            out.extend(scan_source(blob.stdout, rel))
        except SyntaxError:
            continue
    return [f for f in out if f["path"] not in REVIEWED
            and not f["ignored_by_copiers"]]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _print(findings, label):
    for f in sorted(findings, key=lambda x: (x["path"], x["lineno"])):
        print("  %s  %s:%d  %s  %s  -> %s"
              % ("L002" if f.get("ignored_by_copiers") else "L001",
                 f["path"], f["lineno"], f["scope"], f["call"], f["dest"]))
    print("%s: %d live-rooted write(s) in %d file(s)"
          % (label, len(findings), len({f["path"] for f in findings})))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo-root", default=ROOT)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--all", action="store_true",
                   help="every *.py under the suite dirs, not just test_*.py")
    s.add_argument("--json", action="store_true")
    c = sub.add_parser("check")
    c.add_argument("--all", action="store_true")
    c.add_argument("--include-ignored", action="store_true",
                   help="also report L002 -- writes under a COPY_IGNORE dir")
    c.add_argument("--strict", action="store_true")
    c.add_argument("--json", action="store_true")
    t = sub.add_parser("staged")
    t.add_argument("--strict", action="store_true")
    a = p.parse_args(argv)

    if a.cmd == "scan":
        f = scan(a.repo_root, a.all)
        print(json.dumps(f, indent=1)) if a.json else _print(f, "livewrite scan")
        return 0
    if a.cmd == "check":
        f = check(a.repo_root, a.all, a.include_ignored)
        if a.json:
            print(json.dumps(f, indent=1))
        else:
            _print(f, "livewrite check")
            if f:
                print("  a test that creates a file inside a tree another "
                      "suite copies can abort that suite's COLLECTION "
                      "(round 517); write to tempfile.mkdtemp() instead")
        return 1 if (f and a.strict) else 0
    f = staged(a.repo_root)
    if f:
        _print(f, "livewrite staged")
    return 1 if (f and a.strict) else 0


if __name__ == "__main__":
    sys.exit(main())

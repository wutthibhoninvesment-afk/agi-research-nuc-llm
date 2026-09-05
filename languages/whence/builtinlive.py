#!/usr/bin/env python3
"""Which of Whence's builtins does any Whence program actually call?

Round 504 (language C), closing round 503's next-step 5.

WHAT PROVOKED THIS
------------------
Round 503 built `harness/swe/scopecall.py` — "is the code a mutation campaign
is scoring actually REACHED by anything?" — and swept the repo with it. Its
report on this tree is a single, spectacular number:

    languages/whence/whence/interp.py — 37 not-live defs
      30 `unreferenced` (nothing in the repo mentions the name at all)
       7 `test_only`    (only a test file mentions it)

37 is the entire builtin surface of the language. `SPEC.md`'s `## Builtins`
table has exactly 37 rows, and every one of the 37 flagged defs is a
`_make_builtin_table.b_*` — `b_print`, `b_len`, `b_fold`, `b_map`, … — i.e.
the audit reported that no Python code in this repo can reach the
implementation of `print`.

Every one of them is live. They are registered by a DECORATOR:

    def register(name, arity, sig):
        _BUILTIN_SIGS[name] = _parse_sig(sig)
        def wrap(fn):
            table.append((name, Builtin(name, arity, fn)))
            return fn
        return wrap

    @register("print", 1, "v")
    def b_print(interp, args, line): ...

`register(...)` receives the function OBJECT at definition time and stashes
it in the table `_install_builtins` walks. The Python name `b_print` is
never spelled again — which is precisely the fact `scopecall` measures. Its
verdict is a true statement about the name and a false statement about the
code. Round 504 fixed the instrument (`decorator` is now a live reference
kind in `scopecall.py`); this module is the other half.

THE OTHER HALF: THE QUESTION WAS ASKED AT THE WRONG LEVEL
---------------------------------------------------------
`scopecall` asks "can Python reach this def". For an interpreter's builtin
table the answer is always yes and it is never interesting: `_install_builtins`
defines all 37 into every `Env`, so all 37 are equally reachable, always.
The interesting question — the one the audit was TRYING to ask, the one
whose answer distinguishes `print` from `contrast` — lives one level up:

    does any Whence program in this repo call this builtin?

That question cannot be answered by any amount of Python static analysis,
because the call site is inside a string. It is answered here, with Whence's
own lexer and parser, over Whence's own corpus.

THE CORPUS, and it is two populations kept apart
------------------------------------------------
    example   `examples/*.lang` — the programs this language SHIPS. A
              builtin used here is used by something a reader is pointed at.
    test      the guest programs embedded in `tests/test_*.py`, harvested by
              `depthcensus.harvest_tests()` (round 458's machine, reused
              rather than re-written). A builtin used ONLY here is exercised
              but never demonstrated.

Conflating them would answer a different question. `unused` — reached by
nothing in either population — is the language's dead surface: documented in
SPEC.md, implemented, tested by nobody, called by nothing.

WHAT COUNTS AS A USE, and the shadowing rule
--------------------------------------------
Two kinds, both counted, reported apart:

    call    `print(x)`  — a `Call` whose callee is a `NameRef` to the builtin
    ref     `map(print, xs)`, `let p = print` — a bare `NameRef` to it. A
            builtin is a first-class value in Whence, so this is a real use.

Shadowing is RESOLVED, not ignored, because `let get = 1` makes every later
`get(...)` in that block a call to an integer and counting it as a builtin
call would be a lie. The model is the interpreter's, not an approximation:

  * `Program` and `Block` each open a scope (`interp.eval_Block` builds
    `Env(env)`), so a `let` inside an `if` branch shadows inside that branch
    and nowhere else;
  * a binding takes effect for the statements AFTER it, because
    `eval_Block` populates `inner` as it goes and nothing is hoisted;
  * `fn f(...)` binds `f` BEFORE its own body is walked (the closure
    captures the env the name is defined in, so `f` is recursive);
  * a function's parameters are bound over its body.

The naive count — every `NameRef` spelling the builtin's name, shadowing
ignored — is computed too and reported beside the resolved one. The
difference is a measurement, not a diagnostic: it is exactly the number of
sites where a grep-shaped answer to this question would have been wrong.

WHAT IT IS NOT
--------------
Not an execution trace. It answers "does a program in this repo name this
builtin", not "does that program run that line". A builtin called only on an
unreachable branch counts as used here, deliberately: this is the cheap
static census, the same trade `scopecall` makes one level down.

Not a guarantee the corpus parses. `examples/` holds machine-written
programs that fail to parse on purpose (see `curecheck.py`), and the test
suite embeds parse-error fixtures. Every unparseable program is REPORTED
with its error, never silently dropped — a census that quietly skips what it
cannot read reports the absence of a use it never looked for.
"""

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from whence import ast_nodes as A          # noqa: E402
from whence import interp as I             # noqa: E402
from whence import parser as P             # noqa: E402

EXAMPLES = os.path.join(ROOT, "examples")

#: The repo root, reached the ONE sanctioned way. `dirname(dirname(ROOT))`
#: is the repo root only while this file sits in the checkout; under
#: `harness/swe/mutation.py` the whole `languages/whence` tree is copied to a
#: tempdir and the same expression resolves to `/tmp`, silently. Round 149
#: found that as 7 of 78 false mutant "kills"; round 413 gave the tree one
#: home for the root; round 467 fixed the last unguarded site
#: (`specreg.py:179`) and closed the three
#: `harness/tests/test_swe_copyparity_real_subject.py` nodes it had kept red
#: for rounds 464-466. This file was written in round 504 with the
#: pre-413 spelling and reopened the same three nodes for round 505.
#: `harness/swe/proc.py` exports `AGI_RESEARCH_ROOT` into every sandbox
#: subprocess; outside one the var is unset and this is byte-for-byte the
#: path the old expression produced.
AGI_ROOT = (os.environ.get("AGI_RESEARCH_ROOT")
            or os.path.dirname(os.path.dirname(ROOT)))
#: Where `--write` puts the ledger `--strict` ratchets against.
LEDGER = os.path.join(AGI_ROOT, "state", "whence", "builtin-liveness.json")

USE_CALL = "call"
USE_REF = "ref"

VERDICT_EXAMPLE = "used_by_example"
VERDICT_TEST_ONLY = "used_by_test_only"
VERDICT_UNUSED = "unused"

#: Slots on `ast_nodes.Node` itself — caches and the line number, never
#: children. Walking them would recurse into compiled closures.
_BASE_SLOTS = frozenset(A.Node.__slots__)


def builtin_names():
    """The names the interpreter actually registers, in table order.

    Derived from `interp._make_builtin_table()` rather than from SPEC.md, so
    a builtin added without touching the spec still appears here.
    `tests/test_spec_builtins.py` is what keeps the two in step; this module
    deliberately reads the side that RUNS.
    """
    return tuple(name for name, _ in I._make_builtin_table())


def _child_nodes(node):
    """Every AST child of `node`, through lists and tuples, in slot order."""
    for cls in type(node).__mro__:
        for slot in getattr(cls, "__slots__", ()):
            if slot in _BASE_SLOTS:
                continue
            v = getattr(node, slot, None)
            for item in _flatten(v):
                yield item


def _flatten(v):
    if isinstance(v, A.Node):
        yield v
    elif isinstance(v, (list, tuple)):
        for x in v:
            for y in _flatten(x):
                yield y


class Use(object):
    __slots__ = ("name", "line", "kind")

    def __init__(self, name, line, kind):
        self.name = name
        self.line = line
        self.kind = kind

    def as_dict(self):
        return {"name": self.name, "line": self.line, "kind": self.kind}

    def __repr__(self):
        return "Use(%r, %d, %r)" % (self.name, self.line, self.kind)


class Shadow(object):
    """A binding that hides a builtin name for the rest of its scope."""

    __slots__ = ("name", "line", "binder")

    def __init__(self, name, line, binder):
        self.name = name
        self.line = line
        self.binder = binder        # "let" | "fn" | "param"

    def as_dict(self):
        return {"name": self.name, "line": self.line, "binder": self.binder}

    def __repr__(self):
        return "Shadow(%r, %d, %r)" % (self.name, self.line, self.binder)


class _Walk(object):
    def __init__(self, names):
        self.names = frozenset(names)
        self.uses = []              # shadowing resolved
        self.naive = []             # shadowing ignored
        self.shadows = []

    # -- name sites ------------------------------------------------------
    def _hit(self, name, line, kind, bound):
        if name not in self.names:
            return
        self.naive.append(Use(name, line, kind))
        if name not in bound:
            self.uses.append(Use(name, line, kind))

    def _bind(self, bound, name, line, binder):
        if name in self.names and name not in bound:
            self.shadows.append(Shadow(name, line, binder))
        return bound | {name}

    # -- statement sequences (these are the only scopes) -----------------
    def stmts(self, seq, bound):
        for st in seq:
            if isinstance(st, A.FnDef):
                # the name is visible inside its own body: recursion.
                bound = self._bind(bound, st.name, st.line, "fn")
                self.fn_body(st.params, st.body, bound)
                rest = [c for c in _child_nodes(st) if c is not st.body]
                for ch in rest:
                    self.expr(ch, bound)
            elif isinstance(st, A.Let):
                self.expr(st.expr, bound)
                bound = self._bind(bound, st.name, st.line, "let")
            else:
                self.expr(st, bound)
        return bound

    def fn_body(self, params, body, bound):
        for p in _param_names(params):
            bound = self._bind(bound, p, getattr(body, "line", 0), "param")
        self.expr(body, bound)

    # -- expressions -----------------------------------------------------
    def expr(self, node, bound):
        """Walk one expression. ITERATIVE over the expression spine, and
        that is not a style choice: `tests/test_v04.py:241` builds
        `let result = 1 + 1 + 1 ...` 3000 terms long, so a recursive
        visitor hits Python's recursion limit on a program the language
        itself compiles fine (`test_tall_call_free_trees_fall_back_to_the_
        trampoline` exists because the INTERPRETER had the same problem at
        round 9 and fixed it with a trampoline). Round 504's first run
        reported that program as UNPARSEABLE — a `RecursionError` inside
        this module, blamed on the corpus. The stack below is why the
        census can read its own test suite.

        Scope-opening nodes (`Block`, `FnExpr`, `FnDef`) recurse, because
        threading a sequential binding set through an explicit stack would
        reimplement the call stack badly. Their nesting is bounded by how
        the program is WRITTEN, not by how long an operator chain is.
        """
        stack = [(node, bound)]
        while stack:
            n, b = stack.pop()
            if n is None or not isinstance(n, A.Node):
                continue
            cls = type(n)
            if cls is A.NameRef:
                self._hit(n.name, n.line, USE_REF, b)
                continue
            if cls is A.Call:
                if isinstance(n.fn, A.NameRef):
                    self._hit(n.fn.name, n.fn.line, USE_CALL, b)
                else:
                    stack.append((n.fn, b))
                for a in n.args:
                    stack.append((a, b))
                continue
            if cls is A.Block or cls is A.Program:
                self.stmts(n.stmts, b)
                continue
            if cls is A.FnExpr:
                self.fn_body(n.params, n.body, b)
                self._push_other(stack, n, b, skip=n.body)
                continue
            if cls is A.FnDef:
                # A FnDef reached as an expression (not through `stmts`)
                # still binds its own name over its own body.
                inner = self._bind(b, n.name, n.line, "fn")
                self.fn_body(n.params, n.body, inner)
                self._push_other(stack, n, b, skip=n.body)
                continue
            self._push_other(stack, n, b)

    @staticmethod
    def _push_other(stack, node, bound, skip=None):
        for ch in _child_nodes(node):
            if skip is not None and ch is skip:
                continue
            stack.append((ch, bound))


def _param_names(params):
    out = []
    for p in params or ():
        if isinstance(p, str):
            out.append(p)
        elif isinstance(p, (list, tuple)) and p and isinstance(p[0], str):
            out.append(p[0])
    return out


class _Failed(Exception):
    """Raised by `uses_in` so a caller that wants an exception gets one
    that still says WHICH side failed."""

    def __init__(self, kind, message):
        Exception.__init__(self, "%s failure: %s" % (kind, message))
        self.kind = kind


def uses_in(src, names=None):
    """`(uses, naive_uses, shadows)` for one Whence program.

    Raises `_Failed` (with `.kind` in `{"parse", "walk"}`) instead of
    returning rows. `scan_program` is the non-raising form the census uses.
    """
    res = scan_program(src, names)
    if not res["ok"]:
        raise _Failed(res["error_kind"], res["error"])
    return res["uses"], res["naive"], res["shadows"]


def scan_program(src, names=None):
    """`uses_in` with the failure turned into a row instead of an exception.

    Returns a dict with `ok`, and on failure `error` plus `error_kind`,
    which is `"parse"` or `"walk"` and the distinction is load-bearing.
    Round 504's first iterative walker still called a method it had just
    renamed; every one of the 23 parseable examples came back
    `AttributeError: '_Walk' object has no attribute 'other'` and the
    census printed all 23 under `UNPARSEABLE example`. A defect in the
    INSTRUMENT was filed against the SUBJECT, in a report whose whole
    purpose is to say which parts of the subject nothing reaches — and
    every count in it dropped without a single number turning red.

    A parse failure is a fact about the corpus. A walk failure is a bug
    here. They are separated at the boundary where they are still
    distinguishable, and `census()` refuses to publish a verdict when any
    walk failure occurred.
    """
    try:
        tree = P.parse(src)
    except Exception as exc:           # ParseError, LexError, RecursionError
        return {"ok": False, "error_kind": "parse",
                "error": "%s: %s" % (type(exc).__name__, exc),
                "uses": [], "naive": [], "shadows": []}
    try:
        names_ = builtin_names() if names is None else names
        w = _Walk(names_)
        w.stmts(tree.stmts, frozenset())
    except Exception as exc:
        return {"ok": False, "error_kind": "walk",
                "error": "%s: %s" % (type(exc).__name__, exc),
                "uses": [], "naive": [], "shadows": []}
    key = lambda u: (u.line, u.name, u.kind)    # noqa: E731
    return {"ok": True, "error_kind": None, "error": None,
            "uses": sorted(w.uses, key=key),
            "naive": sorted(w.naive, key=key), "shadows": w.shadows}


# ------------------------------------------------------------------ corpus

def example_paths(directory=None):
    d = EXAMPLES if directory is None else directory
    return [os.path.join(d, n) for n in sorted(os.listdir(d))
            if n.endswith(".lang")]


def example_programs(directory=None):
    out = []
    for p in example_paths(directory):
        with open(p, encoding="utf-8") as fh:
            out.append({"origin": "example",
                        "where": os.path.basename(p),
                        "src": fh.read()})
    return out


def test_programs():
    """The guest programs embedded in `tests/test_*.py`.

    `depthcensus.harvest_tests()` already solves this and its rules (dedup on
    `(source, max_depth)` across files, constant folding, residual
    classification) are pinned by four test files. Re-deriving them here
    would create a second, disagreeing definition of "the test corpus".
    """
    import depthcensus
    programs, _stats = depthcensus.harvest_tests()
    return [{"origin": "test",
             "where": "%s:%s" % (p.get("file"), p.get("line")),
             "src": p["src"]} for p in programs]


def corpus(include_tests=True, directory=None):
    progs = example_programs(directory)
    if include_tests:
        progs.extend(test_programs())
    return progs


# ------------------------------------------------------------------ census

def census(include_tests=True, directory=None, programs=None):
    t0 = time.time()
    names = builtin_names()
    progs = corpus(include_tests, directory) if programs is None else programs

    rows = {n: {"name": n,
                "call_example": 0, "ref_example": 0,
                "call_test": 0, "ref_test": 0,
                "naive_example": 0, "naive_test": 0,
                "example_files": [], "test_sites": [],
                "verdict": VERDICT_UNUSED} for n in names}
    unparseable = []
    walk_errors = []
    shadows = []
    n_ok = 0

    for prog in progs:
        res = scan_program(prog["src"], names)
        if not res["ok"]:
            row = {"origin": prog["origin"], "where": prog["where"],
                   "error": res["error"]}
            if res["error_kind"] == "walk":
                walk_errors.append(row)
            else:
                unparseable.append(row)
            continue
        n_ok += 1
        origin = prog["origin"]
        for u in res["uses"]:
            r = rows[u.name]
            r["%s_%s" % (u.kind, origin)] += 1
            if origin == "example":
                if prog["where"] not in r["example_files"]:
                    r["example_files"].append(prog["where"])
            elif len(r["test_sites"]) < 5:
                r["test_sites"].append(prog["where"])
        for u in res["naive"]:
            rows[u.name]["naive_%s" % origin] += 1
        for s in res["shadows"]:
            shadows.append(dict(s.as_dict(), origin=origin,
                                where=prog["where"]))

    for r in rows.values():
        if r["call_example"] or r["ref_example"]:
            r["verdict"] = VERDICT_EXAMPLE
        elif r["call_test"] or r["ref_test"]:
            r["verdict"] = VERDICT_TEST_ONLY
        r["uses_total"] = (r["call_example"] + r["ref_example"]
                           + r["call_test"] + r["ref_test"])
        r["naive_total"] = r["naive_example"] + r["naive_test"]
        r["shadowed_out"] = r["naive_total"] - r["uses_total"]

    ordered = sorted(rows.values(),
                     key=lambda r: (-r["uses_total"], r["name"]))
    by_verdict = {v: sorted(r["name"] for r in rows.values()
                            if r["verdict"] == v)
                  for v in (VERDICT_EXAMPLE, VERDICT_TEST_ONLY,
                            VERDICT_UNUSED)}
    total_uses = sum(r["uses_total"] for r in rows.values())
    top3 = sum(r["uses_total"] for r in ordered[:3])
    return {
        "n_builtins": len(names),
        "n_programs": len(progs),
        "n_parsed": n_ok,
        "n_unparseable": len(unparseable),
        "unparseable": unparseable,
        "n_walk_errors": len(walk_errors),
        "walk_errors": walk_errors,
        "rows": ordered,
        "by_verdict": by_verdict,
        "counts": {v: len(by_verdict[v]) for v in by_verdict},
        "total_uses": total_uses,
        "top3_share": (float(top3) / total_uses) if total_uses else 0.0,
        "shadows": shadows,
        "n_shadows": len(shadows),
        "shadowed_out": sum(r["shadowed_out"] for r in rows.values()),
        "include_tests": include_tests,
        "wall_seconds": round(time.time() - t0, 2),
    }


def census_lines(c):
    out = ["builtin-liveness: %d builtins over %d programs "
           "(%d parsed, %d unparseable) in %.1fs"
           % (c["n_builtins"], c["n_programs"], c["n_parsed"],
              c["n_unparseable"], c["wall_seconds"]),
           "  %-14s %s" % ("used_by_example", c["counts"][VERDICT_EXAMPLE]),
           "  %-14s %s" % ("test_only", c["counts"][VERDICT_TEST_ONLY]),
           "  %-14s %s  %s" % ("unused", c["counts"][VERDICT_UNUSED],
                               ", ".join(c["by_verdict"][VERDICT_UNUSED])),
           "",
           "  %-12s %6s %6s %6s %6s  %s"
           % ("builtin", "ex", "test", "total", "shdw", "verdict")]
    for r in c["rows"]:
        out.append("  %-12s %6d %6d %6d %6d  %s"
                   % (r["name"], r["call_example"] + r["ref_example"],
                      r["call_test"] + r["ref_test"], r["uses_total"],
                      r["shadowed_out"], r["verdict"]))
    out.append("")
    out.append("  total uses %d; top-3 share %.1f%%; %d shadowing binding(s), "
               "%d use(s) removed by shadowing"
               % (c["total_uses"], 100.0 * c["top3_share"], c["n_shadows"],
                  c["shadowed_out"]))
    for u in c["unparseable"]:
        out.append("  UNPARSEABLE %-8s %s -- %s"
                   % (u["origin"], u["where"], u["error"].split("\n")[0]))
    for u in c.get("walk_errors", []):
        out.append("  WALK-ERROR  %-8s %s -- %s   <- a bug in builtinlive.py, "
                   "NOT in the corpus"
                   % (u["origin"], u["where"], u["error"].split("\n")[0]))
    if c.get("n_walk_errors"):
        out.append("  REFUSING TO PUBLISH: %d walk error(s); every count "
                   "above is short by an unknown amount"
                   % c["n_walk_errors"])
    return out


# ------------------------------------------------------------------ ledger

def ledger_view(c):
    """The part of a census that is a claim about the LANGUAGE rather than
    about the day it ran. Wall clock, per-site lists and test-site samples
    are excluded on purpose: a ratchet that moves when a test file is
    renamed is a ratchet nobody can keep green."""
    return {
        "n_builtins": c["n_builtins"],
        "by_verdict": c["by_verdict"],
        "counts": c["counts"],
    }


def check(c, ledger_path=None):
    """`(findings, recorded)` — B001 per builtin whose verdict has moved."""
    path = LEDGER if ledger_path is None else ledger_path
    if not os.path.exists(path):
        return [("B000", path, "no ledger on disk; run `--write` first")], None
    with open(path, encoding="utf-8") as fh:
        rec = json.load(fh)
    findings = []
    was = {}
    for verdict, names in rec.get("by_verdict", {}).items():
        for n in names:
            was[n] = verdict
    now = {}
    for verdict, names in c["by_verdict"].items():
        for n in names:
            now[n] = verdict
    for n in sorted(set(was) | set(now)):
        a, b = was.get(n), now.get(n)
        if a != b:
            findings.append(("B001", n, "verdict moved %s -> %s" % (a, b)))
    return findings, rec


def build_parser():
    p = argparse.ArgumentParser(
        description="which builtins does any Whence program call?")
    p.add_argument("--no-tests", action="store_true",
                   help="examples/ only; skip the harvested test corpus")
    p.add_argument("--dir", default=None,
                   help="a directory of .lang files instead of examples/")
    p.add_argument("--json", default=None, help="write the full census here")
    p.add_argument("--write", action="store_true",
                   help="(re)write the pinned ledger from this census")
    p.add_argument("--ledger", default=None)
    p.add_argument("--strict", action="store_true",
                   help="exit 1 if any builtin's verdict moved")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    c = census(include_tests=not args.no_tests, directory=args.dir)
    for line in census_lines(c):
        print(line)
    if args.json:
        _write(args.json, c)
        print("wrote %s" % args.json)
    path = args.ledger or LEDGER
    if args.write and c["n_walk_errors"]:
        print("refusing to write a ledger from a census with walk errors")
        return 1
    if args.write:
        _write(path, ledger_view(c))
        print("wrote ledger %s" % path)
        return 0
    findings, _rec = check(c, path)
    for code, subject, why in findings:
        print("%s  %s: %s" % (code, subject, why))
    if findings:
        print("%d ledger finding(s)" % len(findings))
    if c["n_walk_errors"]:
        return 1
    return 1 if (findings and args.strict) else 0


def _write(path, obj):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    sys.exit(main())

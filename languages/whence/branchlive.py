#!/usr/bin/env python3
"""which BRANCHES of a Whence program does anything actually TAKE?

The fourth level of a liveness question this program has now asked four
ways, and the first one that observes a DECISION rather than an invocation.

    round 503  `harness/swe/scopecall.py`   is the PYTHON def referenced?
    round 504  `builtinlive.py`             is the GUEST name called in source?
    round 506  `runlive.py`                 is the BUILTIN invoked at runtime?
    round 510  `branchlive.py`  (this file) is the guest AST BRANCH taken?

Round 506's next-step #1 is why this exists, and it named the hard part:

    `self_eval.lang`'s `apply_builtin` has at least one branch no program
    reaches, and nothing measures how many. ... A per-BRANCH reachability
    census over the self-evaluator is the obvious next instrument, and
    `runlive.py`'s hook is the wrong level for it -- this needs the guest
    AST, not the host dispatch slot.

## Where the hook goes, and why it is not a dispatch slot

`runlive.py` could count builtins at ONE attribute (`values.Builtin.fn`)
because all four of the interpreter's dispatch paths reach through it. An
`if` has no such attribute. The decision is made at six sites, and two of
them are CLOSURES built by the compiler (`f_if`, `d_if` in
`interp._compile`) which no monkeypatch can reach:

    interp.py  eval_If         the trampoline generator
    interp.py  _if_inline      fast condition, branch evaluated inline
    interp.py  _if_chain       an else-if chain walked without one generator
                               per level
    interp.py  f_if            the compiled fast closure          (unreachable)
    interp.py  d_if            the compiled direct closure        (unreachable)
    interp.py  _wrap_ifs /     decisions a pending TAIL CALL carried, completed
               _finish_call    after the loop ends

What all six DO share is the artefact they leave: every one of them
materialises the decision as a provenance node whose `op` is the literal
`"if"` and whose `detail` is `"took then-branch"` or `"took else-branch"`.
In a provenance-first language the record of the decision is a value, so
the census hooks the CONSTRUCTOR of that record and gets all six paths at
once without touching the compiler.

## The hole inheritance hides

`values.MergedProv` is a subclass of `values.Prov` and its `__init__` does
NOT call `Prov.__init__`. It re-inlines the six slot assignments on
purpose -- a v0.10 speed change whose comment says "one frame, not two"
(388 -> 215 ns). So `Prov.__init__` is not the funnel it looks like: a
census that hooks the base class alone silently misses every `if ... xN`
run that a tail loop merged (`_finish_call` builds those as `MergedProv`),
and misses them for exactly the branches that ran the MOST times. Both
constructors are hooked here, and `--split` reports the difference so the
claim stays measured rather than asserted.

## What this hook cannot see, stated rather than implied

* **`rescue` has no censusable branch.** The recovery path builds
  `derived("rescue", "recovered", ...)`; the pass-through path returns its
  left operand UNCHANGED and builds no node at all. The constructor hook
  can see that a rescue recovered and can never see that one did not.
  `and`/`or` short-circuit is the same shape. This module reports `if`.
* **A provenance node carries a LINE, not a node identity.** Two `A.If`
  nodes on one source line are one bucket, and no fact the hook records
  can separate them. Such lines are counted, reported as `ambiguous`, and
  excluded from the "never reached" claim rather than quietly included.
* **A count is a lower bound.** `_merge_ifs` folds a run of identical
  consecutive decisions into ONE `MergedProv` carrying `count`, so the
  number of times a branch was taken inside a tail loop is `count`, not
  the number of constructor calls. REACHABILITY -- the question this file
  is for -- is exact either way.

## The two corpora

`file` runs one `.lang` program and censuses its own `if` nodes.

`selfeval` is the one that answers round 506. `examples/self_eval.lang` is
a Whence evaluator written in Whence; running it alone exercises only the
76-plus in-language checks it ships with. What actually drives its
`apply_builtin` chain is `tests/test_self_eval.py`, which builds ONE host
program -- the library, then one `run_src("<case>")` per corpus case -- and
compares guest against host. `selfeval` builds the same program (the
library is the file up to the `# ==== SELF-TESTS` marker, so its line
numbers are `self_eval.lang`'s own, unshifted) and censuses the library's
`if` nodes under it.

The case list is read out of `tests/test_self_eval.py` BY FILE LOCATION,
never by putting `tests/` on `sys.path` (round 509: `harness/tests/` is a
regular package and shadowing a subject tree's `tests` is how an instrument
changes its subject). The rule is stated once, in `selfeval_cases`.
"""

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import builtinlive as BL                         # noqa: E402
from whence import ast_nodes as A                # noqa: E402
from whence import values as V                   # noqa: E402
from whence.interp import Interpreter            # noqa: E402
from whence.lexer import LexError                # noqa: E402
from whence.parser import ParseError, parse      # noqa: E402

#: The repo root, reached the ONE sanctioned way (round 413). NOT
#: `dirname(dirname(ROOT))`: under `harness/swe/mutation.py` this tree is
#: copied to a tempdir and that expression resolves to `/tmp` in silence.
#: Round 504 (`builtinlive.py`) and round 507 (`specstale.py`) each wrote
#: the unguarded spelling and each reopened the same three
#: `harness/tests/test_swe_copyparity_real_subject.py` nodes.
AGI_ROOT = (os.environ.get("AGI_RESEARCH_ROOT")
            or os.path.dirname(os.path.dirname(ROOT)))

EXAMPLES = os.path.join(ROOT, "examples")
SELF_EVAL = os.path.join(EXAMPLES, "self_eval.lang")
TESTS = os.path.join(ROOT, "tests")
SELF_EVAL_TEST = os.path.join(TESTS, "test_self_eval.py")

#: `test_self_eval.py`'s own marker for where the library ends.
MARKER = "# ==== SELF-TESTS"

#: `run.py` raises the limit for direct mode; a census that did not would
#: report a RecursionError as a property of the program.
CLI_RECURSION_LIMIT = 6000

#: The two `detail` strings every branch decision carries, at all six
#: sites. Spelled here once; `test_branchlive.py` asserts they are still
#: the strings `interp.py` writes, so a rename there fails loudly instead
#: of silently reporting every branch as never taken.
THEN = "took then-branch"
ELSE = "took else-branch"

#: A decision that took NEITHER arm: `_if_bad` turned a non-boolean or a
#: missing condition into a miss. Same `op`, some other `detail`.
UNDECIDED = "undecided"

BOTH = "both"
THEN_ONLY = "then_only"
ELSE_ONLY = "else_only"
NEVER = "never"
UNDECIDED_ONLY = "undecided_only"
AMBIGUOUS = "ambiguous"
VERDICTS = (BOTH, THEN_ONLY, ELSE_ONLY, UNDECIDED_ONLY, NEVER, AMBIGUOUS)


# ----------------------------------------------------------- the hook --

class BranchCounter(object):
    """Counts `if` decisions by (line, arm) while it is entered.

    A context manager that restores BOTH constructors on the way out even
    if the program under it raised. `Prov` is the value class of every
    running interpreter in the process, so a census that leaked its
    wrapper would leave the whole process instrumented -- including the
    test suite that imports this module.
    """

    def __init__(self):
        #: {(line, arm): n} from `Prov.__init__`
        self.plain = {}
        #: {(line, arm): n} from `MergedProv.__init__` (tail-loop runs)
        self.merged = {}
        #: sum of `count` over merged runs, i.e. decisions those stand for
        self.merged_steps = 0
        self._saved = None

    def reset_program(self):
        """Per-program counters.

        `.clear()`, NOT a rebind. The wrappers installed in `__enter__`
        close over the dict OBJECTS that existed then; rebinding the
        attribute leaves every wrapper writing to a dict nobody reads and
        the census reports a clean, plausible, entirely false zero. Round
        506's `runlive.py` shipped exactly that bug for one run.
        """
        self.plain.clear()
        self.merged.clear()
        self.merged_steps = 0

    def hits(self):
        """(line, arm) -> n, both constructors together."""
        out = dict(self.plain)
        for k, n in self.merged.items():
            out[k] = out.get(k, 0) + n
        return out

    def __enter__(self):
        if self._saved is not None:
            raise RuntimeError("BranchCounter is not re-entrant")
        self._saved = (V.Prov.__init__, V.MergedProv.__init__)
        plain, merged = self.plain, self.merged
        lazy = V._LAZY
        p_init, m_init = self._saved
        counter = self

        def prov_init(node, op, detail, line, ins=(), show=lazy, value=None):
            p_init(node, op, detail, line, ins, show, value)
            if op == "if":
                k = (line, _arm(detail))
                plain[k] = plain.get(k, 0) + 1

        def merged_init(node, op, detail, line, ins=(), show=lazy, value=None,
                        count=1):
            m_init(node, op, detail, line, ins, show, value, count)
            if op == "if":
                k = (line, _arm(detail))
                merged[k] = merged.get(k, 0) + 1
                counter.merged_steps += count

        V.Prov.__init__ = prov_init
        V.MergedProv.__init__ = merged_init
        return self

    def __exit__(self, *exc):
        if self._saved is not None:
            V.Prov.__init__, V.MergedProv.__init__ = self._saved
            self._saved = None
        return False


def _arm(detail):
    if detail == THEN:
        return THEN
    if detail == ELSE:
        return ELSE
    return UNDECIDED


# ------------------------------------------------------- the denominator --

def if_nodes(program):
    """Every `A.If` in a parsed program, outermost-first, with its
    enclosing function name.

    Children come from `builtinlive._child_nodes`, which walks each node
    type's OWN slots through lists and tuples. Re-deriving that walk here
    would create a second, disagreeing definition of "an AST child" -- the
    defect round 434 found twice in one round, both times a comprehension
    that dropped a case.

    Every `A.If` here has TWO REAL ARMS: since v0.19 the parser requires an
    explicit `{}` block for both, so `if c { x }` with no `else` does not
    parse at all (`tests/test_branchlive.py` pins that). There is no
    synthesised arm to discount, which is why "else never taken" is always
    a fact about written code.
    """
    out = []
    stack = [(program, "<toplevel>")]
    while stack:
        node, fn = stack.pop()
        if node.__class__ is A.If:
            out.append({
                "line": node.line,
                "fn": fn,
                "chained": node.otherwise.__class__ is A.If,
            })
        here = fn
        if node.__class__ is A.FnDef:
            here = node.name
        elif node.__class__ is A.FnExpr:
            here = "fn@%d" % node.line
        for child in BL._child_nodes(node):
            stack.append((child, here))
    out.sort(key=lambda r: (r["line"], r["fn"]))
    return out


def parse_program(src):
    return parse(src)


# ------------------------------------------------------------- running --

def run_program(src, counter, seed=0, direct=True, out_cap=200):
    """Run one guest program under `counter`; return a per-program row.

    Mirrors `run.py`'s kwargs so a decision counted here is a decision the
    shipped entry point would have made. A program that fails is REPORTED,
    never silently dropped: a runtime census that skips what it could not
    run reports the absence of a decision it never attempted.
    """
    counter.reset_program()
    sink_out = []

    def sink(text):
        if len(sink_out) < out_cap:
            sink_out.append(text)

    t0 = time.time()
    err = err_kind = None
    checks = []
    try:
        interp = Interpreter(out=sink, gc_relief=True, direct=direct,
                             seed=seed)
        interp.run(src)
        checks = list(interp.checks)
    except (LexError, ParseError) as e:
        err, err_kind = "%s: %s" % (type(e).__name__, e), "parse"
    except RecursionError as e:
        err, err_kind = "RecursionError: %s" % e, "recursion"
    except Exception as e:                        # noqa: BLE001 - reported
        err, err_kind = "%s: %s" % (type(e).__name__, e), "raised"
    return {
        "ok": err is None,
        "error": err,
        "error_kind": err_kind,
        # `"%d:%s"` keys, not the (line, arm) tuples the counter uses:
        # `--json` writes this dict and JSON has no tuple key.
        "plain": _keyed(counter.plain),
        "merged": _keyed(counter.merged),
        "merged_steps": counter.merged_steps,
        "n_checks": len(checks),
        "n_failed_checks": sum(1 for c in checks if not c["ok"]),
        "seconds": round(time.time() - t0, 3),
    }


# -------------------------------------------------------------- census --

def _keyed(d):
    return dict(("%d:%s" % k, n) for k, n in sorted(d.items()))


def attribute(nodes, hits, source_lines=None):
    """Cross the static `if` nodes with the decisions observed.

    One row per (line, fn) node. Lines carrying more than one `A.If` are
    marked `ambiguous` -- the hook records a line, so nothing it saw can
    say which of the two decided.
    """
    per_line = {}
    for n in nodes:
        per_line.setdefault(n["line"], []).append(n)
    rows = []
    for n in nodes:
        line = n["line"]
        amb = len(per_line[line]) > 1
        took = {THEN: hits.get((line, THEN), 0),
                ELSE: hits.get((line, ELSE), 0),
                UNDECIDED: hits.get((line, UNDECIDED), 0)}
        row = dict(n)
        row["then"] = took[THEN]
        row["else"] = took[ELSE]
        row["undecided"] = took[UNDECIDED]
        row["ambiguous"] = amb
        row["verdict"] = _verdict(took, amb)
        if source_lines and 1 <= line <= len(source_lines):
            row["src"] = source_lines[line - 1].strip()[:120]
        rows.append(row)
    return rows


def _verdict(took, ambiguous):
    if ambiguous:
        return AMBIGUOUS
    t, e, u = took[THEN], took[ELSE], took[UNDECIDED]
    if t and e:
        return BOTH
    if t:
        return THEN_ONLY
    if e:
        return ELSE_ONLY
    if u:
        return UNDECIDED_ONLY
    return NEVER


def summarise(rows):
    counts = dict((v, 0) for v in VERDICTS)
    for r in rows:
        counts[r["verdict"]] += 1
    return {"nodes": len(rows), "verdicts": counts,
            "arms_taken": sum(bool(r["then"]) + bool(r["else"])
                              for r in rows if not r["ambiguous"]),
            "arms_written": sum(2 for r in rows if not r["ambiguous"])}


def census_file(path, seed=0, direct=True):
    """Parse and run ONE `.lang` file, then attribute its own `if` nodes."""
    src = open(path, encoding="utf-8").read()
    program = parse_program(src)
    nodes = if_nodes(program)
    limit0 = sys.getrecursionlimit()
    if direct and limit0 < CLI_RECURSION_LIMIT:
        sys.setrecursionlimit(CLI_RECURSION_LIMIT)
    try:
        with BranchCounter() as counter:
            run = run_program(src, counter, seed=seed, direct=direct)
            hits = counter.hits()
            plain_only = dict(counter.plain)
    finally:
        sys.setrecursionlimit(limit0)
    rows = attribute(nodes, hits, src.splitlines())
    return {
        "mode": "file",
        "where": os.path.relpath(path, ROOT),
        "run": run,
        "rows": rows,
        "summary": summarise(rows),
        "merged_only": _merged_only(hits, plain_only, nodes),
    }


def _merged_only(hits, plain_only, nodes):
    """(line, arm) pairs a `Prov`-only hook would have MISSED.

    The measured form of this module's claim about `MergedProv.__init__`.
    Restricted to lines that actually carry an `A.If` in the program under
    census, so a decision made inside a different file's library cannot
    inflate it.
    """
    known = set(n["line"] for n in nodes)
    return sorted("%d:%s" % k for k in hits
                  if k not in plain_only and k[0] in known)


def selfeval_cases(path=None):
    """The guest sources `test_self_eval.py` drives the evaluator with.

    THE RULE, stated once: every module-level name in that file that is a
    `list` whose elements are all `str`, or all tuples whose first element
    is a `str`, contributes its strings, in file order, deduplicated. That
    covers `CORPUS`, `RECORD_SPEC_CASES`, `RET_CHAIN_CASES`,
    `SHAPE_VALUE_CASES` and `SHAPE_MISS_CASES` without naming any of them,
    so a case list added later is picked up without an edit here.

    Loaded BY FILE LOCATION. `tests/` is never put on `sys.path`: round
    509 measured that `harness/tests/__init__.py` makes `tests` a regular
    package, so an instrument that puts its own parent on the path binds
    every `import tests` in the subject to ITS package and every
    intra-suite import in the subject raises at collection.
    """
    import importlib.util as U
    path = path or SELF_EVAL_TEST
    spec = U.spec_from_file_location("_branchlive_selfeval_cases", path)
    mod = U.module_from_spec(spec)
    spec.loader.exec_module(mod)
    seen = set()
    cases = []
    for name in sorted(vars(mod)):
        if name.startswith("_"):
            continue
        v = getattr(mod, name)
        if not isinstance(v, list) or not v:
            continue
        srcs = _string_cases(v)
        if srcs is None:
            continue
        for s in srcs:
            if s not in seen:
                seen.add(s)
                cases.append(s)
    return cases


def _string_cases(v):
    """The guest sources in one module-level list, or None if it is not a
    case list. All-or-nothing on purpose: a list of MIXED shapes is a list
    this rule does not understand, and guessing is how a corpus quietly
    grows a member nobody wrote."""
    if all(isinstance(x, str) for x in v):
        return list(v)
    if all(isinstance(x, tuple) and x and isinstance(x[0], str) for x in v):
        return [x[0] for x in v]
    return None


def library_source(path=None):
    src = open(path or SELF_EVAL, encoding="utf-8").read()
    if MARKER not in src:
        raise ValueError("%s has no %r marker" % (path or SELF_EVAL, MARKER))
    return src.split(MARKER)[0]


def _escape(src):
    return (src.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\n", "\\n").replace("\t", "\\t"))


def selfeval_program(cases, path=None):
    """`test_self_eval.guest_eval_all`'s program, rebuilt here.

    The library comes FIRST and verbatim, so every `if` node in it keeps
    `self_eval.lang`'s own line number and the census needs no offset."""
    parts = [library_source(path)]
    for i, src in enumerate(cases):
        parts.append('let __out%d = run_src("%s")\n' % (i, _escape(src)))
    return "".join(parts)


def census_selfeval(cases=None, seed=0, direct=True, standalone=False,
                    path=None):
    """Census `self_eval.lang`'s library `if` nodes.

    `standalone=True` runs the file as `run.py` would (its own in-language
    checks only) -- the baseline round 506 implicitly assumed. Otherwise
    the library is driven by `test_self_eval.py`'s corpus through
    `run_src`, which is what actually exercises `apply_builtin`.
    """
    path = path or SELF_EVAL
    whole = open(path, encoding="utf-8").read()
    lib = library_source(path)
    n_lib_lines = lib.count("\n")
    nodes = [n for n in if_nodes(parse_program(whole))
             if n["line"] <= n_lib_lines]
    if standalone:
        src = whole
        cases = []
    else:
        cases = selfeval_cases() if cases is None else cases
        src = selfeval_program(cases, path)
    limit0 = sys.getrecursionlimit()
    if direct and limit0 < CLI_RECURSION_LIMIT:
        sys.setrecursionlimit(CLI_RECURSION_LIMIT)
    try:
        with BranchCounter() as counter:
            run = run_program(src, counter, seed=seed, direct=direct)
            hits = counter.hits()
            plain_only = dict(counter.plain)
    finally:
        sys.setrecursionlimit(limit0)
    hits = dict((k, n) for k, n in hits.items() if k[0] <= n_lib_lines)
    rows = attribute(nodes, hits, whole.splitlines())
    return {
        "mode": "selfeval-standalone" if standalone else "selfeval-corpus",
        "where": os.path.relpath(path, ROOT),
        "library_lines": n_lib_lines,
        "cases": len(cases),
        "run": run,
        "rows": rows,
        "summary": summarise(rows),
        "merged_only": _merged_only(hits, plain_only, nodes),
    }


def fn_rows(rows, fn):
    return [r for r in rows if r["fn"] == fn]


# -------------------------------------------------------------- report --

def report_lines(c, limit=25, fn=None):
    s = c["summary"]
    v = s["verdicts"]
    out = ["branchlive %s: %s" % (c["mode"], c["where"])]
    if not c["run"]["ok"]:
        out.append("  RUN FAILED (%s): %s" % (c["run"]["error_kind"],
                                              c["run"]["error"]))
    out.append("  %d if-node(s): %d both arms, %d then-only, %d else-only, "
               "%d undecided-only, %d never evaluated, %d ambiguous line(s)"
               % (s["nodes"], v[BOTH], v[THEN_ONLY], v[ELSE_ONLY],
                  v[UNDECIDED_ONLY], v[NEVER], v[AMBIGUOUS]))
    out.append("  %d of %d written arms taken (%.1f %%), %d run in %.1fs, "
               "%d check(s) %d failed"
               % (s["arms_taken"], s["arms_written"],
                  100.0 * s["arms_taken"] / max(1, s["arms_written"]),
                  c.get("cases", 0), c["run"]["seconds"],
                  c["run"]["n_checks"], c["run"]["n_failed_checks"]))
    if c["merged_only"]:
        out.append("  %d decision(s) ONLY a MergedProv hook saw: %s"
                   % (len(c["merged_only"]),
                      ", ".join(c["merged_only"][:8])))
    else:
        out.append("  0 decisions were seen only through MergedProv")
    rows = c["rows"] if fn is None else fn_rows(c["rows"], fn)
    cold = [r for r in rows
            if r["verdict"] in (NEVER, THEN_ONLY, ELSE_ONLY, UNDECIDED_ONLY)]
    out.append("  %d unreached arm(s)%s:"
               % (len(cold), "" if fn is None else " in %s" % fn))
    for r in cold[:limit]:
        out.append("    line %-5d %-22s %-14s %s"
                   % (r["line"], r["fn"][:22], r["verdict"],
                      r.get("src", "")[:70]))
    if len(cold) > limit:
        out.append("    ... %d more" % (len(cold) - limit))
    return out


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("file", help="census one .lang program")
    p.add_argument("path")
    p.add_argument("--json")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--fn")
    p.add_argument("--no-direct", action="store_true")

    p = sub.add_parser("selfeval", help="census self_eval.lang's library")
    p.add_argument("--standalone", action="store_true",
                   help="run the file alone instead of driving it with "
                        "test_self_eval.py's corpus")
    p.add_argument("--json")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--fn", default=None)
    p.add_argument("--no-direct", action="store_true")

    p = sub.add_parser("cases", help="the corpus selfeval would use")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "cases":
        cases = selfeval_cases()
        for c in cases:
            print(repr(c))
        print("branchlive cases: %d guest program(s) from %s"
              % (len(cases), os.path.relpath(SELF_EVAL_TEST, ROOT)))
        return 0
    if args.cmd == "file":
        c = census_file(args.path, direct=not args.no_direct)
    elif args.cmd == "selfeval":
        c = census_selfeval(standalone=args.standalone,
                            direct=not args.no_direct)
    else:
        build_parser().print_help()
        return 0
    for line in report_lines(c, limit=args.limit, fn=args.fn):
        print(line)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(c, f, indent=1, sort_keys=False)
            f.write("\n")
        print("branchlive: wrote %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())

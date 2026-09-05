#!/usr/bin/env python3
"""which builtins does any Whence program RUN?

The third level of a liveness question this program has now asked three
ways, and the first one that observes an execution rather than a text.

    round 503  `harness/swe/scopecall.py`   is the PYTHON def referenced?
    round 504  `builtinlive.py`             is the GUEST name called in source?
    round 506  `runlive.py`   (this file)   is the BUILTIN invoked at runtime?

Round 504 measured that the first two levels disagree on 37 of 37 builtins
and left one number as the language's single measured gap: `typed` is
called once in all of `examples/` against 47 times in the test corpus, "the
widest ratio of any builtin", with the next round told to either write an
example or say why not.

There is a third answer, and it is the reason this file exists. `typed` is
the builtin form of a check the language ALSO performs structurally, for
every `p: Type` parameter and every `-> Type` return, and since v0.19
(round 344) that structural path does not go through the builtin at all:
`whence/parser.py::_param_contracts` stores the contract on the FnDef node
and `whence/interp.py::_check_contract` applies it in the host. So a
program can exercise the entire type-contract feature -- mismatch, origin
miss, `blame` trail -- without the identifier `typed` appearing in it, and
a census that counts CALL SITES IN SOURCE is structurally incapable of
seeing that it did. The gap round 504 measured is real as arithmetic and
does not mean what its own next-step assumed.

`SPEC.md:1508` is why the mistake is worth a file rather than a footnote:
it still describes v0.12's desugaring ("`fn f(a: num, …)` desugars, in the
parser, to one leading `let a = typed(a, "num", …)`") in the present tense,
inside the v0.12 section where it is history. Read as current, it says
annotations DO call the builtin. `whence/parser.py:2072` and
`whence/parser.py:389` both record the change; the SPEC's own v0.12 bullet
never got the past-tense marker its neighbours got.

## What is counted, and where

At `values.Builtin.fn`, the single attribute all four dispatch paths
(`interp.py:1079` value call, `:1244` trampoline, `:2043` compiled fast
path, `:2411` direct mode) reach through. Counting there rather than at an
AST node is the whole point: a builtin passed as a VALUE (`map(print, xs)`)
is invoked with no call node naming it, and a compiled call site that has
been specialised still ends at `b.fn`. The `Builtin` objects are
module-level singletons shared across interpreters, so the wrapper is
installed once and sees every interpreter in the process; `is_gen` is
computed in `__init__` and is deliberately NOT recomputed, so wrapping a
generator builtin leaves its dispatch class unchanged.

Annotation contracts are counted separately, at `interp._check_contract`,
split into the `spec is None` no-op (every call of every unannotated
function reaches it) and the checks that actually ran. They are NOT added
to `typed`'s count. Reporting them as `typed` would answer round 504's
question by redefining its noun, which is the move this program calls
using the instrument to conceal the finding.

## What a failed program does

It is reported, never silently dropped -- `builtinlive.py`'s rule, and it
matters more here: a runtime census that skips what it could not run
reports the absence of an invocation it never attempted. Every program
that fails to parse, raises, or exits non-zero appears in `errors` with
its reason, and `--strict` refuses to ratchet while any parse of a program
the syntactic census could read is outstanding.
"""

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import builtinlive as BL                       # noqa: E402
from whence import interp as I                 # noqa: E402
from whence.lexer import LexError              # noqa: E402
from whence.parser import ParseError           # noqa: E402

#: The repo root, reached the ONE sanctioned way (round 413). Not
#: `dirname(dirname(ROOT))`: under `harness/swe/mutation.py` this tree is
#: copied to a tempdir and that expression resolves to `/tmp` in silence.
#: Round 504 wrote `builtinlive.py` with the unguarded spelling and reopened
#: three `test_swe_copyparity_real_subject.py` nodes for round 505.
AGI_ROOT = (os.environ.get("AGI_RESEARCH_ROOT")
            or os.path.dirname(os.path.dirname(ROOT)))
LEDGER = os.path.join(AGI_ROOT, "state", "whence", "builtin-runtime.json")

#: run.py raises the limit for direct mode; a census that did not would
#: report a RecursionError as a property of the program.
CLI_RECURSION_LIMIT = 6000

#: Cap on captured program output. A census must not hold `deep.lang`'s
#: whole stdout in memory to count a call it already counted.
OUT_CAP = 200

RUN_AND_WRITTEN = "run_and_written"     # invoked, and spelled in the corpus
WRITTEN_NEVER_RUN = "written_never_run"  # spelled, never invoked
RUN_NEVER_WRITTEN = "run_never_written"  # invoked, never spelled
NEITHER = "neither"
VERDICTS = (RUN_AND_WRITTEN, WRITTEN_NEVER_RUN, RUN_NEVER_WRITTEN, NEITHER)


# ------------------------------------------------------------- the hook --

class Counter(object):
    """Wraps every `Builtin.fn` in the shared table, and `_check_contract`.

    A context manager, and it restores on the way out even if the program
    under it raised: the table is a process-global shared by every
    `Interpreter`, so a census that leaked its wrapper would leave the
    interpreter permanently instrumented for whatever ran next in the same
    process -- including the test suite that imports this module.
    """

    def __init__(self):
        self.calls = {}
        self.contract_calls = 0        # every _check_contract entry
        self.contract_checks = 0       # ... those with a spec to check
        self.contract_misses = 0       # ... that produced a fresh miss
        self._saved = []
        self._saved_contract = None

    def reset_program(self):
        """Per-program counters, returned by `run_program`.

        `self.calls.clear()`, NOT `self.calls = {}`. The wrappers installed
        in `__enter__` close over the dict OBJECT that existed then;
        rebinding the attribute leaves every wrapper writing to a dict
        nobody reads, and the census then reports zero invocations for all
        37 builtins while the interpreter runs perfectly. Round 506 shipped
        exactly that for one run: 23 programs ran, `_check_contract` was
        entered 515728 times, and the table came back `written_never_run`
        37 of 37 -- a clean, plausible, entirely false answer with nothing
        raised. It is the same class as round 504's own headline bug and
        the reason `test_runlive.py` pins a NON-ZERO total against a
        program whose calls are counted by hand.
        """
        self.calls.clear()
        self.contract_calls = 0
        self.contract_checks = 0
        self.contract_misses = 0

    def __enter__(self):
        if I._BUILTIN_TABLE is None:
            # Forcing the table is the same call `_install_builtins` makes;
            # doing it here means the wrapper is installed on the singletons
            # BEFORE any Interpreter binds them into an Env.
            I._BUILTIN_TABLE = I._make_builtin_table()
        calls = self.calls

        def wrap(name, fn):
            def counted(interp, args, line):
                calls[name] = calls.get(name, 0) + 1
                return fn(interp, args, line)
            counted.__name__ = "counted_" + name
            return counted

        for name, b in I._BUILTIN_TABLE:
            self._saved.append((b, b.fn))
            # `is_gen` was computed in `Builtin.__init__` from the ORIGINAL
            # fn and is not recomputed here, so a generator builtin keeps
            # its trampoline dispatch class; `counted` returns the
            # generator object the caller already expects.
            b.fn = wrap(name, b.fn)

        real = I._check_contract
        self._saved_contract = real

        def counted_contract(result, spec, label, line):
            self.contract_calls += 1
            if spec is not None:
                self.contract_checks += 1
            out = real(result, spec, label, line)
            if out is not result:
                self.contract_misses += 1
            return out

        I._check_contract = counted_contract
        return self

    def __exit__(self, *exc):
        for b, fn in self._saved:
            b.fn = fn
        self._saved = []
        if self._saved_contract is not None:
            I._check_contract = self._saved_contract
            self._saved_contract = None
        return False


# ------------------------------------------------------------ running it --

def run_program(src, counter, seed=0, direct=True, max_iter=None):
    """Run one guest program under `counter`; return its per-program row.

    Mirrors `run.py`'s own kwargs so a count here is a count of what the
    shipped entry point would have done. Output is captured and capped.
    """
    counter.reset_program()
    out = []

    def sink(text):
        if len(out) < OUT_CAP:
            out.append(text)

    kwargs = {"out": sink, "gc_relief": True, "direct": direct, "seed": seed}
    if max_iter is not None:
        kwargs["max_iter"] = max_iter
    t0 = time.time()
    err = None
    err_kind = None
    checks = []
    try:
        interp = I.Interpreter(**kwargs)
        interp.run(src)
        checks = list(interp.checks)
    except (LexError, ParseError) as e:
        err, err_kind = "%s: %s" % (type(e).__name__, e), "parse"
    except RecursionError as e:
        err, err_kind = "RecursionError: %s" % e, "recursion"
    except Exception as e:                       # noqa: BLE001 - reported
        err, err_kind = "%s: %s" % (type(e).__name__, e), "raised"
    failed = sum(1 for c in checks if not c["ok"])
    return {
        "ok": err is None,
        "error": err,
        "error_kind": err_kind,
        "calls": dict(counter.calls),
        "contract_calls": counter.contract_calls,
        "contract_checks": counter.contract_checks,
        "contract_misses": counter.contract_misses,
        "n_checks": len(checks),
        "n_failed_checks": failed,
        "seconds": round(time.time() - t0, 3),
    }


def census(include_tests=False, directory=None, programs=None, seed=0,
           direct=True):
    """Run the corpus and cross the result with the syntactic census.

    `include_tests` defaults to FALSE, unlike `builtinlive.census`. The
    harvested test corpus is 873 programs written to be PARSED by fixtures,
    many of them fragments whose enclosing test supplies a `max_depth` or a
    driver; running them here would measure this file's ability to guess a
    harness, not the language's demonstrated surface. Available, opt-in,
    and reported separately when asked for.
    """
    t0 = time.time()
    names = BL.builtin_names()
    progs = (BL.corpus(include_tests, directory)
             if programs is None else programs)

    rows = {n: {"name": n, "run_example": 0, "run_test": 0,
                "example_files": [], "test_sites": []} for n in names}
    errors = []
    per_program = []
    n_ran = 0
    contract = {"calls": 0, "checks": 0, "misses": 0, "programs": 0}

    limit0 = sys.getrecursionlimit()
    if direct and limit0 < CLI_RECURSION_LIMIT:
        sys.setrecursionlimit(CLI_RECURSION_LIMIT)
    try:
        with Counter() as counter:
            for prog in progs:
                r = run_program(prog["src"], counter, seed=seed,
                                direct=direct)
                origin = prog["origin"]
                row = {"origin": origin, "where": prog["where"],
                       "ok": r["ok"], "error": r["error"],
                       "error_kind": r["error_kind"],
                       "n_calls": sum(r["calls"].values()),
                       "n_distinct": len(r["calls"]),
                       "contract_checks": r["contract_checks"],
                       "contract_misses": r["contract_misses"],
                       "n_checks": r["n_checks"],
                       "n_failed_checks": r["n_failed_checks"],
                       "seconds": r["seconds"]}
                per_program.append(row)
                if not r["ok"]:
                    errors.append({"origin": origin, "where": prog["where"],
                                   "error": r["error"],
                                   "error_kind": r["error_kind"]})
                    continue
                n_ran += 1
                contract["calls"] += r["contract_calls"]
                contract["checks"] += r["contract_checks"]
                contract["misses"] += r["contract_misses"]
                if r["contract_checks"]:
                    contract["programs"] += 1
                for name, n in r["calls"].items():
                    if name not in rows:         # a builtin added mid-run
                        continue
                    rows[name]["run_%s" % origin] += n
                    if origin == "example":
                        if prog["where"] not in rows[name]["example_files"]:
                            rows[name]["example_files"].append(prog["where"])
                    elif len(rows[name]["test_sites"]) < 5:
                        rows[name]["test_sites"].append(prog["where"])
    finally:
        sys.setrecursionlimit(limit0)

    syn = BL.census(include_tests=include_tests, directory=directory,
                    programs=progs)
    syn_rows = {r["name"]: r for r in syn["rows"]}
    for name, r in rows.items():
        s = syn_rows[name]
        r["run_total"] = r["run_example"] + r["run_test"]
        r["written_example"] = s["call_example"] + s["ref_example"]
        r["written_total"] = s["uses_total"]
        r["gap"] = r["run_total"] - r["written_total"]
        if r["run_total"] and r["written_total"]:
            r["verdict"] = RUN_AND_WRITTEN
        elif r["written_total"]:
            r["verdict"] = WRITTEN_NEVER_RUN
        elif r["run_total"]:
            r["verdict"] = RUN_NEVER_WRITTEN
        else:
            r["verdict"] = NEITHER

    ordered = sorted(rows.values(), key=lambda r: (-r["run_total"], r["name"]))
    by_verdict = {v: sorted(r["name"] for r in rows.values()
                            if r["verdict"] == v) for v in VERDICTS}
    disagree = sorted(r["name"] for r in rows.values()
                      if bool(r["run_total"]) != bool(r["written_total"]))
    return {
        "n_builtins": len(names),
        "n_programs": len(progs),
        "n_ran": n_ran,
        "n_errors": len(errors),
        "errors": errors,
        "per_program": per_program,
        "rows": ordered,
        "by_verdict": by_verdict,
        "counts": {v: len(by_verdict[v]) for v in by_verdict},
        "disagree": disagree,
        "n_disagree": len(disagree),
        "total_runtime_calls": sum(r["run_total"] for r in rows.values()),
        "total_written": sum(r["written_total"] for r in rows.values()),
        "contract": contract,
        "include_tests": include_tests,
        "syntactic": {"n_parsed": syn["n_parsed"],
                      "n_unparseable": syn["n_unparseable"],
                      "n_walk_errors": syn["n_walk_errors"]},
        "wall_seconds": round(time.time() - t0, 2),
    }


# ------------------------------------------------------------- reporting --

def census_lines(c):
    out = []
    out.append("  %-14s %6s %6s %6s  %s"
               % ("builtin", "run", "writ", "gap", "verdict"))
    for r in c["rows"]:
        out.append("  %-14s %6d %6d %+6d  %s"
                   % (r["name"], r["run_total"], r["written_total"],
                      r["gap"], r["verdict"]))
    out.append("")
    out.append("  %d program(s): %d ran, %d could not"
               % (c["n_programs"], c["n_ran"], c["n_errors"]))
    out.append("  %d runtime invocation(s) against %d written use(s)"
               % (c["total_runtime_calls"], c["total_written"]))
    out.append("  verdicts: " + ", ".join(
        "%s %d" % (v, c["counts"][v]) for v in VERDICTS))
    out.append("  the two levels disagree on %d of %d builtin(s)%s"
               % (c["n_disagree"], c["n_builtins"],
                  (": " + ", ".join(c["disagree"])) if c["disagree"] else ""))
    k = c["contract"]
    out.append("  annotation contracts: %d check(s) actually applied in %d "
               "program(s), %d producing a miss, out of %d _check_contract "
               "entries -- and NONE of them is a `typed` call"
               % (k["checks"], k["programs"], k["misses"], k["calls"]))
    for e in c["errors"]:
        out.append("  DID NOT RUN  %-34s [%s] %s"
                   % (e["where"], e["error_kind"], e["error"]))
    return out


def ledger_view(c):
    """The pinned subset: verdicts and counts, no wall-clock, no paths."""
    return {
        "_what": ("Runtime builtin liveness (round 506, `runlive.py`). Per "
                  "builtin: how many times it was INVOKED while every "
                  "runnable program in `examples/` ran, against how many "
                  "times it is written in that same corpus. Counted at "
                  "`values.Builtin.fn`, the attribute all four dispatch "
                  "paths reach through. Annotation contracts (`p: Type`, "
                  "`-> Type`) are counted separately and are NOT `typed` "
                  "calls: v0.19 moved that check off the builtin."),
        "n_builtins": c["n_builtins"],
        "n_ran": c["n_ran"],
        "n_errors": c["n_errors"],
        "counts": c["counts"],
        "by_verdict": c["by_verdict"],
        "contract_checks": c["contract"]["checks"],
        "runtime": {r["name"]: r["run_total"] for r in c["rows"]},
    }


def check(c, ledger_path=None):
    """Compare against the pinned ledger. Returns (ok, lines)."""
    path = ledger_path or LEDGER
    if not os.path.exists(path):
        return False, ["no ledger at %s -- run with --write first" % path]
    with open(path, encoding="utf-8") as fh:
        old = json.load(fh)
    new = ledger_view(c)
    lines = []
    for name in sorted(set(old.get("runtime", {})) | set(new["runtime"])):
        a = old.get("runtime", {}).get(name)
        b = new["runtime"].get(name)
        if a != b:
            lines.append("  MOVED  %-14s %s -> %s" % (name, a, b))
    for v in VERDICTS:
        a = old.get("by_verdict", {}).get(v)
        b = new["by_verdict"][v]
        if a is not None and a != b:
            lines.append("  VERDICT SET MOVED  %s: %s -> %s" % (v, a, b))
    if c["n_errors"] != old.get("n_errors"):
        lines.append("  ERROR COUNT MOVED  %s -> %s"
                     % (old.get("n_errors"), c["n_errors"]))
    return (not lines), (lines or ["  ledger matches"])


def _write(path, obj):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", action="store_true",
                    help="also RUN the harvested test corpus (opt-in; see "
                         "`census`'s docstring for why it is not default)")
    ap.add_argument("--dir", help="a directory of .lang files instead of "
                                  "examples/")
    ap.add_argument("--json", help="write the full census here")
    ap.add_argument("--write", action="store_true",
                    help="(re)write the pinned ledger from this census")
    ap.add_argument("--ledger", default=LEDGER)
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any runtime count or verdict moved")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-direct", action="store_true")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    c = census(include_tests=args.corpus, directory=args.dir, seed=args.seed,
               direct=not args.no_direct)
    for line in census_lines(c):
        print(line)
    if args.json:
        _write(args.json, c)
        print("  wrote %s" % args.json)
    if args.write:
        _write(args.ledger, ledger_view(c))
        print("  wrote ledger %s" % args.ledger)
    if args.strict:
        ok, lines = check(c, args.ledger)
        for line in lines:
            print(line)
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

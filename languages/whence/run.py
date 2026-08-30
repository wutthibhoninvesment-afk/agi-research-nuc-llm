#!/usr/bin/env python3
"""Whence — a provenance-first language. Run a program, stdin, or the REPL.

Usage:
    python3 run.py [--max-depth N] [--max-iter N] [--no-direct] [--seed N] examples/hello.lang
    python3 run.py -                        # program from stdin
    python3 run.py                          # REPL (interactive terminal only)

Exit codes (pinned contract — tests/test_examples.py depends on these):
    0  program ran and every `check` passed
    1  at least one `check` failed
    2  usage error or parse error (reported on stderr)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from whence.lexer import LexError                    # noqa: E402
from whence.parser import parse, ParseError          # noqa: E402
from whence.interp import Interpreter                # noqa: E402
from whence.values import full_show                  # noqa: E402

USAGE = ("usage: run.py [--max-depth N] [--max-iter N] [--no-direct] "
         "[--seed N] <file.lang | ->\n"
         "       run.py    (no arguments on an interactive terminal: REPL)")

# v0.9: direct mode runs guest calls by host recursion under a frame budget
# taken from the live recursion limit. The library never changes that limit
# (the budget adapts to whatever headroom exists); the CLI owns the main
# thread and its 8 MB stack, so it raises the limit to widen the budget —
# ~1400 fib-shaped guest levels instead of ~160 before the trampoline takes
# over. Plain closures recurse fine at 30000 here; 6000 is conservative.
CLI_RECURSION_LIMIT = 6000


def report_checks(checks, out=print):
    """Print ✓/✗ per check (why-tree + contrast on failure) and the summary
    line. Returns the number of failed checks."""
    if not checks:
        return 0
    failed = 0
    for c in checks:
        if c["ok"]:
            out("✓ %s" % c["label"])
        else:
            failed += 1
            out("✗ %s (line %d) — %s" % (c["label"], c["line"], c["note"]))
            if c.get("why"):
                out(c["why"])
            if c.get("contrast"):
                out("where the two sides diverge:")
                out(c["contrast"])
    out("checks: %d passed, %d failed" % (len(checks) - failed, failed))
    return failed


def repl():
    """Interactive loop: one persistent interpreter + env so bindings and
    functions survive across lines; expression statements echo their value."""
    from whence.interp import Env
    interp = Interpreter(out=print, gc_relief=True)
    env = Env(interp.globals)
    print("Whence REPL — provenance-first. 'exit' to quit; `why x` explains x.")
    while True:
        try:
            src = input("> ")
        except EOFError:            # end of stdin — normal exit
            print()
            return 0
        except KeyboardInterrupt:
            print("\nInterrupted.")
            continue
        if src.strip().lower() in ("exit", "quit"):
            return 0
        if not src.strip():
            continue
        n0 = len(interp.checks)
        try:
            program = parse(src)
        except ParseError as e:
            print("parse error: %s" % e)
            continue
        for stmt in program.stmts:
            v = interp.exec_stmt(stmt, env)
            if type(stmt).__name__ == "ExprStmt" and v is not None:
                print(full_show(v.payload))
        report_checks(interp.checks[n0:])


def main(argv):
    args = argv[1:]
    max_depth = None
    max_iter = None
    direct = True
    seed = 0
    path = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--no-direct":
            direct = False
            i += 1
        elif a in ("--max-depth", "--max-iter", "--seed"):
            if i + 1 >= len(args):
                print(USAGE, file=sys.stderr)
                return 2
            try:
                n = int(args[i + 1])
            except ValueError:
                print(USAGE, file=sys.stderr)
                return 2
            if a == "--max-depth":
                max_depth = n
            elif a == "--max-iter":
                max_iter = n
            else:
                seed = n
            i += 2
        elif a in ("-h", "--help"):
            print(USAGE)
            return 0
        elif path is None:
            path = a
            i += 1
        else:
            print(USAGE, file=sys.stderr)
            return 2

    if path is None:
        if sys.stdin.isatty():
            return repl()
        print(USAGE, file=sys.stderr)
        return 2

    if path == "-":
        src = sys.stdin.read()
    else:
        try:
            with open(path, encoding="utf-8") as f:
                src = f.read()
        except OSError as e:
            print("error: %s" % e, file=sys.stderr)
            return 2

    kwargs = {"out": print, "gc_relief": True, "max_iter": max_iter,
              "direct": direct, "seed": seed}
    if max_depth is not None:
        kwargs["max_depth"] = max_depth
    if direct and sys.getrecursionlimit() < CLI_RECURSION_LIMIT:
        sys.setrecursionlimit(CLI_RECURSION_LIMIT)
    interp = Interpreter(**kwargs)
    try:
        interp.run(src)
    except (LexError, ParseError) as e:
        # `LexError` was NOT in this tuple until v0.21 (round 350), so every
        # lex error -- `$`, an unterminated string, a bad escape -- left the
        # CLI as a raw Python traceback with exit **1**, while SPEC.md's
        # "Running" section has always promised `exit ... 2 (lex/parse
        # error)` and a parse error already did exactly that. Exit 1 is the
        # "some check failed" code, so a caller could not tell a program
        # whose checks failed from a program that does not lex. Every other
        # entry point in the tree (`bench/ref_diff.py`,
        # `bench/reserve_probe.py`, `tests/test_generated_killers.py`)
        # already catches the two together, which is what makes this an
        # oversight rather than a design choice.
        print("error: %s" % e, file=sys.stderr)
        return 2
    return 1 if report_checks(interp.checks) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

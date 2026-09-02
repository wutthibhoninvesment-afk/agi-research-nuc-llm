#!/usr/bin/env python3
"""Whence — a provenance-first language. Run a program, stdin, or the REPL.

Usage:
    python3 run.py [--max-depth N] [--max-iter N] [--max-value N]
                   [--max-int-bits N] [--no-direct] [--seed N]
                   [--strict-miss] examples/hello.lang
                            (--max-iter 0 = unbounded tail loops,
                             --max-value 0 = unbounded strings/lists/ranges,
                             --max-int-bits 0 = unbounded integers)
    python3 run.py -                        # program from stdin
    python3 run.py                          # REPL (interactive terminal only)

Exit codes (pinned contract — tests/test_examples.py depends on these):
    0  program ran and every `check` passed
    1  at least one `check` failed, or `--strict-miss` and a miss was dropped
    2  usage error or parse error (reported on stderr)

v0.32 adds the dropped-miss report. It is printed unconditionally, because
the defect it names is SILENCE; but it does NOT move the exit code on its
own, because 1 has meant "a check failed" since v0.1 and a caller that greps
for that must keep working. `--strict-miss` is the opt-in for a CI that
wants a discarded miss to fail the run.

v0.42 widens the report to misses inside a DISCARDED AGGREGATE — the
`map(fn(x) { nosuch(x) }, xs)` shape, which reported nothing for ten
versions. The exit-code contract is unchanged.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from whence.lexer import LexError                    # noqa: E402
from whence.parser import parse, ParseError          # noqa: E402
from whence.interp import Interpreter                # noqa: E402
from whence.values import full_show                  # noqa: E402

USAGE = ("usage: run.py [--max-depth N] [--max-iter N] [--max-value N] "
         "[--max-int-bits N] [--no-direct] [--seed N] [--strict-miss] "
         "<file.lang | ->\n"
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


def _report_truncation(interp, out):
    """v0.42: say that a discarded aggregate was too large to read to the end.

    Printed whether or not anything was found, and deliberately NOT counted
    as a drop: it does not move `--strict-miss`, because "I did not finish
    looking" is not "I found something". `Interpreter.DROP_SCAN_NODES` is
    the bound and the sentence names it, so a reader who wants the rest can
    raise it rather than guess what was skipped."""
    n = getattr(interp, "dropped_scan_truncated", 0)
    if not n:
        return
    out("  (%d discarded value%s too large to read to the end at %d nodes "
        "— a miss deeper inside %s not listed)"
        % (n, "" if n == 1 else "s", interp.DROP_SCAN_NODES,
           "is" if n == 1 else "are"))


def report_drops(interp, out=print):
    """v0.32: print the miss values this run computed and threw away.

    A miss that reaches a name, a `check` or an operand is observable — the
    program can ask it `why`, `reasons`, `blame`. A miss that is the value
    of a statement nothing keeps cannot be asked anything by anybody, and
    until v0.32 the run said nothing about it at all: the four machine-
    written programs in `examples/` that parse spent 30 rounds printing
    empty strings and exiting 0 while carrying, inside the value they threw
    away, the exact sentence that named their bug.

    `print(x)` is not a drop — see `Interpreter._observed`. Returns the
    number of distinct drop SITES.

    v0.42 widens what "the value" means: a miss riding inside a list or
    record the statement discards is a drop too (`Interpreter._misses_within`).
    Until v0.42 `map(fn(x) { nosuch(x) }, xs)` as a statement reported
    NOTHING — the outermost node was a list, so the `isinstance(_, Miss)`
    test said no, and the misses inside it went to the same silence the
    feature was built to end."""
    n, sites = interp.dropped_total, len(interp.dropped)
    # v0.42: the truncation note is NOT inside this guard. A walk that
    # stopped early and found nothing is the one case where "no drops" is
    # least trustworthy, and the first draft of this function printed the
    # note only when something HAD been found — i.e. never said "I stopped
    # reading" in the situation that sentence exists for.
    if not interp.dropped:
        _report_truncation(interp, out)
        return 0
    out("dropped: %d miss value%s computed and discarded — nothing can ask "
        "%s why" % (n, "" if n == 1 else "s", "it" if n == 1 else "them"))
    for e in interp.dropped:
        where = "line %d" % e["at"]
        if e["line"] != e["at"]:
            where += " (%s, from line %d)" % (e["label"], e["line"])
        # v0.42: the miss was inside a list or record the statement threw
        # away whole. Naming the container is the difference between "line
        # 12 — unbound name 'println'" and "line 12 in map — …": the reader
        # has to know the value they were looking for never existed as a
        # name, or they will go looking for the binding.
        if e.get("within"):
            where += " in %s" % e["within"]
        times = "" if e["count"] == 1 else " ×%d" % e["count"]
        out("  %s%s — %s" % (where, times, "; ".join(e["reasons"])))
    if n > sum(e["count"] for e in interp.dropped):
        out("  (%d more, past the %d-site cap)"
            % (n - sum(e["count"] for e in interp.dropped),
               interp.DROP_CAP))
    # v0.42: an aggregate too big to walk in full. Said out loud, because a
    # short list that looks complete is what this whole feature exists
    # against; `Interpreter.DROP_SCAN_NODES` is the bound.
    _report_truncation(interp, out)
    return sites


def main(argv):
    args = argv[1:]
    max_depth = None
    max_iter = None
    max_value = None
    max_int_bits = None
    direct = True
    seed = 0
    strict_miss = False
    path = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--no-direct":
            direct = False
            i += 1
        elif a == "--strict-miss":
            strict_miss = True
            i += 1
        elif a in ("--max-depth", "--max-iter", "--max-value",
                   "--max-int-bits", "--seed"):
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
            elif a == "--max-value":
                max_value = n
            elif a == "--max-int-bits":
                max_int_bits = n
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

    kwargs = {"out": print, "gc_relief": True, "direct": direct, "seed": seed}
    if max_depth is not None:
        kwargs["max_depth"] = max_depth
    # v0.26: `max_iter` is now treated exactly like `max_depth` — omitted
    # unless the flag was given, so the class default applies. Before v0.26
    # this line passed `max_iter` unconditionally, so the CLI passed None on
    # every run and `DEFAULT_MAX_ITER` would have been unreachable from it.
    # `--max-iter 0` is the explicit "unbounded" opt-out.
    if max_iter is not None:
        kwargs["max_iter"] = max_iter if max_iter > 0 else None
    # v0.27: `--max-value` follows the shape v0.26 settled on for `--max-iter`
    # -- omitted unless the flag was given, `0` the explicit unbounded opt-out.
    if max_value is not None:
        kwargs["max_value"] = max_value if max_value > 0 else None
    if max_int_bits is not None:
        kwargs["max_int_bits"] = max_int_bits if max_int_bits > 0 else None
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
    failed = report_checks(interp.checks)
    dropped = report_drops(interp)
    if failed:
        return 1
    return 1 if (strict_miss and dropped) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

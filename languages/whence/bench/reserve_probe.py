#!/usr/bin/env python3
"""Measure the host-frame reserve direct mode really needs (round 110).

`Interpreter.HOST_RESERVE` is the number of host frames kept free below
the recursion limit while direct mode runs: the transient that the budget
does not charge (fast-closure recursion, one nested trampoline drive and
its helpers, rendering) plus the C-level recursion entries the limit
counts but `cdepth` cannot. This script finds, per program, the SMALLEST
reserve at which the run still completes without a RecursionError — a
binary search over the class attribute, each probe in a fresh process so
one overflow cannot poison the next. The true need is the maximum over a
corpus of deep shapes; the reserve should be set at a multiple of it.

usage: python3 bench/reserve_probe.py [--limit 6000] [--seed 1 -n 40]
                                      [--max 350] [--examples] [-v]
Prints one line per program (need, budget consumed, fallbacks at the
found reserve) and the corpus maximum.
"""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# See bench/ref_diff.py's REPO comment (round 149): this breaks when the
# whole languages/whence tree is copied to a tempdir (any mutation/repair
# run) unless AGI_RESEARCH_ROOT (set by harness/swe/proc.py) overrides it.
HARNESS = os.path.join(os.environ.get("AGI_RESEARCH_ROOT") or
                        os.path.dirname(os.path.dirname(ROOT)), "harness")

PROBE = r'''
import sys, os
sys.setrecursionlimit(%(limit)d)
sys.path.insert(0, %(root)r)
from whence.interp import Interpreter
Interpreter.HOST_RESERVE = %(reserve)d
src = open(%(path)r).read()
out = []
# v0.26: max_iter=None for the same reason as max_depth=10**6 — a probe
# measures where the real limit is, so neither cap may bind first.
it = Interpreter(gc_relief=True, out=out.append, max_depth=10 ** 6,
                 max_iter=None)
from whence.lexer import LexError
from whence.parser import ParseError
try:
    it.run(src)
except RecursionError:
    print("OVERFLOW"); sys.exit(0)
except (LexError, ParseError) as e:
    print("PARSE_ERROR " + str(e)[:80]); sys.exit(0)
print("OK fallbacks=%%d peak=%%d" %% (it.direct_fallbacks, it.peak_depth))
'''

DEEP_TEMPLATES = [
    # the recursing shapes of the fuzz generator's stress templates, at a
    # depth that exhausts the budget at limit 6000 (so the fallback path
    # AND the deepest direct frames are both on the stack at once)
    "fn nest(n) { if n == 0 { [] } else { [nest(n - 1)] } }\nlet deep = nest(%d)\nprint(len(deep))\n",
    "fn count(n) { if n == 0 { 0 } else { 1 + count(n - 1) } }\nlet cnt = count(%d)\nprint(cnt)\n",
    "fn wrap(n) { if n == 0 { @{v: 0} } else { @{v: wrap(n - 1)} } }\nlet rec = wrap(%d)\nprint(str(rec.v.v))\n",
    "fn even(n) { if n == 0 { true } else { odd(n - 1) } }\nfn odd(n) { if n == 0 { false } else { even(n - 1) } }\nlet par = even(%d)\nprint(par)\n",
    "fn f(n) { if n == 0 { 0 } else { len([f(n - 1), 1]) + 0 } }\nlet r = f(%d)\nprint(r)\n",
    "fn g(n) { if n == 0 { 0 } else { fold(fn(a, x) { a + g(n - 1) }, 0, [1]) } }\nlet r = g(%d)\nprint(r)\n",
    "fn h(n) { if n == 0 { 0 } else { let m = h(n - 1)\n if m > 0 { m } else { m + 1 } } }\nlet r = h(%d)\nprint(why r)\n",
    "fn k(n) { if n == 0 { 0 } else { map(fn(x) { k(n - 1) }, [1])[0] } }\nlet r = k(%d)\nprint(r)\n",
    "fn c(n) { if n == 0 { 0 } else if n %% 2 == 0 { 1 + c(n - 1) } else if n %% 3 == 0 { c(n - 1) + 1 } else { 2 + c(n - 1) - 2 } }\nlet r = c(%d)\nprint(r)\n",
    "fn s(n) { if n == 0 { \"\" } else { s(n - 1) + \"x\" } }\nlet r = s(%d)\nprint(len(r))\nprint(len(str(why r)))\n",
    # the shapes the reserve is FOR: a tall call-free subtree (fast-closure
    # recursion up to FAST_MAX_DEPTH host frames, charged nowhere) in the
    # base case of a NON-tail recursion, i.e. evaluated at the deepest
    # direct frame (a tail-recursive version is one frame: TCO). Nested
    # expressions are capped at 60 levels by the parser; `+` chains parse
    # iteratively and compile up to the height cap (100).
    "fn t(n) { if n == 0 { " + " + ".join(["1"] * 95) + " } else { t(n - 1) + 0 } }\nlet r = t(%d)\nprint(r)\n",
    "fn u(n) { if n == 0 { " + "[" * 55 + "]" * 55 + " } else { u(n - 1) + [] } }\nlet r = u(%d)\nprint(len(r))\n",
    "fn v(n) { if n == 0 { " + "- " * 55 + "1 } else { v(n - 1) + 0 } }\nlet r = v(%d)\nprint(r)\n",
    "fn w(n) { if n == 0 { " + "".join("if n == %d { %d } else { " % (k, k) for k in range(1, 40)) + "0" + " }" * 39 + " } else { w(n - 1) + 0 } }\nlet r = w(%d)\nprint(r)\n",
    # the same tall subtree at the bottom of a recursion through a generator builtin
    "fn x(n) { if n == 0 { " + " + ".join(["1"] * 95) + " } else { fold(fn(a, b) { a + x(n - 1) }, 0, [1]) } }\nlet r = x(%d)\nprint(r)\n",
    # ... and in the base case reached through a list literal and a field (round-108 shapes)
    "fn y(n) { if n == 0 { " + " + ".join(["1"] * 95) + " } else { [y(n - 1)][0] } }\nlet r = y(%d)\nprint(r)\n",
    "fn z(n) { if n == 0 { " + " + ".join(["1"] * 95) + " } else { @{v: z(n - 1)}.v } }\nlet r = z(%d)\nprint(r)\n",
]


def probe(path, reserve, limit, timeout=120):
    """One fresh-process run; the last output line ("OK …", "OVERFLOW",
    "CRASH …" or "TIMEOUT") is the verdict. The timeout guards against a
    corpus program that is exponential (a template of this script's first
    version called itself twice per level — rule: every probe of an
    unknown program gets a wall-clock cap)."""
    code = PROBE % {"limit": limit, "root": ROOT, "reserve": reserve, "path": path}
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    out = (r.stdout + r.stderr).strip().splitlines()
    last = out[-1] if out else "CRASH"
    if r.returncode != 0 and not last.startswith("OK"):
        return "CRASH " + last[-120:]
    return last


def need(path, limit, hi, verbose=False):
    """Smallest reserve in [0, hi] that survives; hi+1 if none does."""
    lo, best = 0, None
    top = probe(path, hi, limit)
    if top.startswith("PARSE_ERROR"):
        return None, top          # not a program: skipped, not a need
    if not top.startswith("OK"):
        # overflow even at the maximum, a crash, or a timeout: not
        # searchable — report it as such rather than as a need
        return hi + 1, top
    best_line = top
    while lo < hi:
        mid = (lo + hi) // 2
        res = probe(path, mid, limit)
        if verbose:
            print("    reserve %4d -> %s" % (mid, res))
        if res.startswith("OK"):
            hi = mid
            best_line = res
        else:
            lo = mid + 1
    return lo, best_line


def main(argv):
    limit, seed, n, hi, examples, verbose = 6000, 1, 40, 350, False, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--limit":
            limit = int(argv[i + 1]); i += 2
        elif a == "--seed":
            seed = int(argv[i + 1]); i += 2
        elif a == "-n":
            n = int(argv[i + 1]); i += 2
        elif a == "--max":
            hi = int(argv[i + 1]); i += 2
        elif a == "--examples":
            examples = True; i += 1
        elif a == "-v":
            verbose = True; i += 1
        else:
            sys.exit("unknown arg " + a)
    import tempfile
    tmp = tempfile.mkdtemp(prefix="reserve_probe_")
    progs = []
    # every level of the deep templates costs 2 host frames at least; pick
    # a depth that exhausts the budget at this limit by a wide margin
    depth = max(2000, limit // 2)
    for k, t in enumerate(DEEP_TEMPLATES):
        p = os.path.join(tmp, "deep%d.lang" % k)
        with open(p, "w") as f:
            f.write(t % depth)
        progs.append(("deep%d" % k, p))
    if examples:
        ex = os.path.join(ROOT, "examples")
        for name in sorted(os.listdir(ex)):
            if name.endswith(".lang"):
                progs.append(("ex:" + name, os.path.join(ex, name)))
    if n > 0:
        sys.path.insert(0, HARNESS)
        from swe.fuzz import ProgramGen
        for j in range(n):
            s = seed * 1000003 + j
            p = os.path.join(tmp, "fuzz%d.lang" % s)
            with open(p, "w") as f:
                f.write(ProgramGen(s, stress_rate=1.0).program())
            progs.append(("fuzz:%d" % s, p))
    worst = (0, "")
    for tag, path in progs:
        r, line = need(path, limit, hi, verbose)
        if r is None:
            print("%-28s skipped   %s" % (tag, line))
            sys.stdout.flush()
            continue
        print("%-28s need=%4d  %s" % (tag, r, line))
        sys.stdout.flush()
        if r > worst[0]:
            worst = (r, tag)
    print("corpus maximum need: %d (%s) at limit %d; current HOST_RESERVE %d" % (
        worst[0], worst[1], limit, __import__("whence.interp", fromlist=["Interpreter"]).Interpreter.HOST_RESERVE))


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    main(sys.argv[1:])

#!/usr/bin/env python3
"""Fresh-process micro-benchmarks for v0.9 (direct mode).

usage: python3 bench/v09_bench.py <name> [direct|fast|slow] [--limit N]
names:
  fib20 fib25   - non-tail call-heavy recursion, wall time
  tail100k      - 100k-iteration tail loop wall time
  retention     - tracemalloc retained bytes/iteration, 20k tail loop
  meta          - examples/meta.lang (self-hosting subset evaluator)
  self_eval     - examples/self_eval.lang (store-passing metacircular evaluator)
  deep          - examples/deep.lang (15000-deep non-tail recursion, runaway)
  sends         - meta.lang: count generator sends + direct hits/fallbacks
Modes: direct = Interpreter() (v0.9 default), fast = direct=False (v0.8
behaviour), slow = fast=False (pure trampoline). --limit raises the host
recursion limit first (run.py uses 6000). Prints one line.
"""
import gc, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from whence.interp import Interpreter  # noqa: E402

args = [a for a in sys.argv[1:]]
limit = None
if "--limit" in args:
    k = args.index("--limit")
    limit = int(args[k + 1])
    del args[k:k + 2]
    sys.setrecursionlimit(limit)
name = args[0]
mode = args[1] if len(args) > 1 else "direct"
KW = {"direct": {}, "fast": {"direct": False}, "slow": {"fast": False}}[mode]

TAIL = "fn go(i, acc) { if i == 0 { acc } else { go(i - 1, acc + i) } }\nlet result = go(%d, 0)\n"
FIB = "fn fib(n) { if n < 2 { n } else { fib(n - 1) + fib(n - 2) } }\nlet result = fib(%d)\n"


def example(fname):
    with open(os.path.join(ROOT, "examples", fname)) as f:
        return f.read()


def timed(src, **kw):
    interp = Interpreter(gc_relief=True, **kw)
    gc.collect()
    t0 = time.time()
    env = interp.run(src)
    return time.time() - t0, interp, env


if name in ("fib20", "fib25"):
    n = int(name[3:])
    dt, interp, env = timed(FIB % n, **KW)
    calls = {20: 21891, 25: 242785}[n]
    print("%s %s  %.3fs  %.2fus/call  result=%s  direct_hits=%d fallbacks=%d" % (
        name, mode, dt, dt / calls * 1e6, env.get("result").show,
        interp.direct_hits, interp.direct_fallbacks))
elif name == "tail100k":
    dt, interp, env = timed(TAIL % 100000, max_depth=10 ** 6, **KW)
    print("tail100k %s  %.3fs  %.2fus/iter  tail_calls=%d" % (
        mode, dt, dt / 1e5 * 1e6, interp.tail_calls))
elif name == "retention":
    import tracemalloc
    n = 20000
    interp = Interpreter(max_depth=10 ** 6, **KW)
    gc.collect()
    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    env = interp.run(TAIL % n)
    gc.collect()
    cur = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    print("retention %s  %.0f B/iter  result=%s" % (mode, (cur - base) / n,
                                                     env.get("result").show))
elif name in ("meta", "self_eval", "deep"):
    src = example({"meta": "meta.lang", "self_eval": "self_eval.lang",
                   "deep": "deep.lang"}[name])
    out = []
    interp = Interpreter(gc_relief=True, out=out.append, **KW)
    gc.collect()
    t0 = time.time()
    interp.run(src)
    dt = time.time() - t0
    bad = [c for c in interp.checks if not c["ok"]]
    print("%s %s  %.3fs  checks=%d failed=%d direct_hits=%d fallbacks=%d budget=%d" % (
        name, mode, dt, len(interp.checks), len(bad), interp.direct_hits,
        interp.direct_fallbacks, interp.host_budget()))
elif name == "sends":
    import cProfile, pstats
    src = example("meta.lang")
    out = []
    interp = Interpreter(gc_relief=True, out=out.append, **KW)
    pr = cProfile.Profile()
    pr.enable()
    interp.run(src)
    pr.disable()
    st = pstats.Stats(pr)
    sends = 0
    for (fn, ln, fname), (cc, nc, tt, ct, callers) in st.stats.items():
        if fname == "<method 'send' of 'generator' objects>":
            sends += nc
    print("sends %s  generator_sends=%d  total_calls=%d  direct_hits=%d fallbacks=%d" % (
        mode, sends, st.total_calls, interp.direct_hits, interp.direct_fallbacks))
else:
    sys.exit("unknown bench: " + name)

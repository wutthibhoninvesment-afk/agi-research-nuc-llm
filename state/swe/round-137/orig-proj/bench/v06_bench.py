#!/usr/bin/env python3
"""Fresh-process micro-benchmarks for the v0.6 recording round.

usage: python3 bench/v06_bench.py <name> [fast|slow]
names:
  retention  - tracemalloc retained bytes/iteration, 20k tail loop
  fib20      - fib(20) wall time (non-tail call-heavy)
  tail100k   - 100k-iteration tail loop wall time + RSS
  fib15guest - guest fib(15) in self_eval.lang (interpretation tax)
Prints one line: <name> <mode> <numbers...>
"""
import gc, os, resource, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from whence.interp import Interpreter

name = sys.argv[1]
fast = (sys.argv[2] != "slow") if len(sys.argv) > 2 else True

TAIL = "fn go(i, acc) { if i == 0 { acc } else { go(i - 1, acc + i) } }\nlet result = go(%d, 0)\n"
FIB = "fn fib(n) { if n < 2 { n } else { fib(n - 1) + fib(n - 2) } }\nlet result = fib(%d)\n"

if name == "retention":
    import tracemalloc
    n = 20000
    interp = Interpreter(max_depth=10**6, fast=fast)
    gc.collect()
    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    env = interp.run(TAIL % n)
    gc.collect()
    cur = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    v = env.get("result")
    print("retention %s n=%d  %.0f B/iter  result=%s" % (
        "fast" if fast else "slow", n, (cur - base) / n, v.show))
elif name == "fib20":
    interp = Interpreter(fast=fast, gc_relief=True)
    t0 = time.time()
    env = interp.run(FIB % 20)
    dt = time.time() - t0
    print("fib20 %s  %.3fs  result=%s  fast_hits=%d" % (
        "fast" if fast else "slow", dt, env.get("result").show,
        interp.fast_hits))
elif name == "tail100k":
    interp = Interpreter(max_depth=10**6, fast=fast, gc_relief=True)
    t0 = time.time()
    env = interp.run(TAIL % 100000)
    dt = time.time() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    print("tail100k %s  %.2fs  peak RSS %.0f MB  %.1fus/iter  result=%s" % (
        "fast" if fast else "slow", dt, rss, dt / 100000 * 1e6,
        env.get("result").show))
elif name == "fib15guest":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "examples", "self_eval.lang")).read()
    interp = Interpreter(max_depth=10**6, fast=fast, gc_relief=True)
    t0 = time.time()
    interp.run(src)
    dt = time.time() - t0
    bad = [c for c in interp.checks if not c["ok"]]
    print("self_eval %s  %.2fs total  checks=%d failed=%d" % (
        "fast" if fast else "slow", dt, len(interp.checks), len(bad)))
else:
    sys.exit("unknown bench: " + name)

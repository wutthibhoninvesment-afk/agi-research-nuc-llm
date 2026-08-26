#!/usr/bin/env python3
"""Measure time + peak RSS of growth patterns that retain full history.
usage: python3 bench/retention.py [n]   (default 20000)"""
import os, resource, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from whence.interp import Interpreter

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
PROGRAMS = {
    "push-in-fold": "fn step(acc, x) { push(acc, x) }\nlet result = fold(step, [], range(%d))\n" % N,
    "concat-in-fold": "fn step(acc, x) { acc + [x] }\nlet result = fold(step, [], range(%d))\n" % N,
    "tail-loop": "fn go(i, acc) { if i == 0 { acc } else { go(i - 1, acc + i) } }\nlet result = go(%d, 0)\n" % N,
}
which = sys.argv[2] if len(sys.argv) > 2 else None
for name, src in PROGRAMS.items():
    if which and name != which:
        continue
    t0 = time.time()
    interp = Interpreter(max_depth=10**6, gc_relief=True)
    env = interp.run(src)
    dt = time.time() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    v = env.get("result")
    print("%-16s n=%d  %.2fs  peak RSS %.0f MB  %.1fus/step  result=%s" % (
        name, N, dt, rss, dt / N * 1e6, v.show))

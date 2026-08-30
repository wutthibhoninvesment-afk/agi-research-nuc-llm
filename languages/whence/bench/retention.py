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
    # v0.26: max_iter=None keeps the "tail-loop" program uncapped — this
    # bench MEASURES the cost of a long tail loop, so the new default
    # (1000000) would silently truncate any run with n above it.
    interp = Interpreter(max_depth=10**6, max_iter=None, gc_relief=True)
    env = interp.run(src)
    dt = time.time() - t0
    # v0.26: ru_maxrss is KILOBYTES on Linux, so the old /(1024*1024) was
    # gigabytes printed under an "MB" label — every run of this bench
    # has reported "peak RSS 0 MB" for as long as it has existed.
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    v = env.get("result")
    print("%-16s n=%d  %.2fs  peak RSS %.0f MB  %.1fus/step  result=%s" % (
        name, N, dt, rss, dt / N * 1e6, v.show))

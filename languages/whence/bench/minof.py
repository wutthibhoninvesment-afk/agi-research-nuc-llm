#!/usr/bin/env python3
"""Run bench/v09_bench.py benches in FRESH processes, N times each, and
print the best (minimum) line per bench — the round protocol's "idle,
fresh process, min-of-3" number in one command.

usage: python3 bench/minof.py [-n 3] [--limit 6000] [--root DIR] bench... 
  bench = "<name> <mode>" e.g. "meta direct" "fib20 slow"
  --root DIR runs the benches against another checkout's bench/v09_bench.py
  (e.g. a `git show HEAD:` extraction) for paired before/after runs.
Default set (no benches given): meta direct/fast, fib20 direct/fast/slow,
tail100k direct/fast, self_eval, deep, retention.
"""
import os, re, subprocess, sys

DEFAULT = ["meta direct", "meta fast", "fib20 direct", "fib20 fast",
           "fib20 slow", "tail100k direct", "tail100k fast",
           "self_eval direct", "deep direct", "retention direct"]
HERE = os.path.dirname(os.path.abspath(__file__))


def number(line):
    """The headline figure of a v09_bench line (seconds, us/call, B/iter)."""
    m = re.search(r"(\d+\.\d+)s|(\d+\.\d+)us|(\d+) B/iter", line)
    return float(next(g for g in m.groups() if g is not None)) if m else 0.0


def main(argv):
    n = 3
    limit = "6000"
    root = HERE
    benches = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "-n":
            n = int(argv[i + 1]); i += 2
        elif a == "--limit":
            limit = argv[i + 1]; i += 2
        elif a == "--root":
            root = os.path.join(argv[i + 1], "bench"); i += 2
        else:
            benches.append(a); i += 1
    if not benches:
        benches = DEFAULT
    script = os.path.join(root, "v09_bench.py")
    for b in benches:
        best = None
        for _ in range(n):
            out = subprocess.run([sys.executable, script] + b.split() +
                                 ["--limit", limit], capture_output=True,
                                 text=True).stdout.strip()
            if best is None or number(out) < number(best):
                best = out
        print(best)


if __name__ == "__main__":
    main(sys.argv[1:])

#!/usr/bin/env python3
"""Measure what a RUNAWAY costs, per non-tail frame and per merged tail
iteration — the two numbers `Interpreter.DEFAULT_MAX_DEPTH` and
`DEFAULT_MAX_ITER` are sized from (v0.26, round 366).

usage: python3 bench/runaway_cost.py              # every shape, 3 sizes each
       python3 bench/runaway_cost.py <shape> <n>  # one reading (child mode)

WHY ONE RUN PER PROCESS. `ru_maxrss` is a process-wide HIGH-WATER mark: it
never falls, so a second `Interpreter` run in the same process reads the
first one's peak and reports it as its own. Round 366's first attempt
measured all four tail shapes in one process and got 1030 / 2018 B/iter for
shapes that actually retain 499 / 768 — a 2-4x overstatement, and one that
looks plausible because it is monotone in the order the shapes happen to run.
So the parent below re-execs itself once per data point.

The per-iteration figure is the point: a merged tail iteration is NOT free.
SPEC rule 8 says a tail loop costs no frame, and it costs no *host* frame —
but the merged `call f xN` node keeps the `if` decision of every iteration,
by design, because `why` still has to explain every branch taken. That is
linear retention with no depth counter behind it, which is exactly why the
loop needs a bound of its own.
"""
import os
import resource
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Every one of these runs FOREVER without a bound — that is the point. The
# tail shapes are stopped by `max_iter`, the non-tail ones by `max_depth`.
TAIL = {
    "bare-spin":  "fn spin(n) { spin(n + 1) }\nlet result = spin(0)\n",
    "if-spin":    "fn spin(n) { if n == -1 { 0 } else { spin(n + 1) } }\n"
                  "let result = spin(0)\n",
    # the shape guest seed 31 generates: a float argument decremented past a
    # `== 0` base case it can never equal
    "seed31":     "fn tl3(p4) { if p4 == 0 { 0.5 } else { tl3(p4 - 1) } }\n"
                  "let result = tl3(0.5)\n",
    "two-arg-if": "fn go(i, acc) { if i == -1 { acc } else { go(i + 1, acc + i) } }\n"
                  "let result = go(0, 0)\n",
}
NONTAIL = {
    "nontail-add": "fn spin(n) { 1 + spin(n + 1) }\nlet result = spin(0)\n",
    "nontail-let": "fn spin(n) {\n  let r = spin(n + 1)\n  r\n}\n"
                   "let result = spin(0)\n",
    "nontail-if":  "fn spin(n) {\n  if n == -1 { 0 } else {\n"
                   "    let r = spin(n + 1)\n    r\n  }\n}\nlet result = spin(0)\n",
}
SIZES = {"tail": (50000, 100000, 200000), "nontail": (5000, 10000, 20000)}


def one(shape, n):
    """One reading, in a process of its own. Prints a single result line."""
    import time
    from whence.interp import Interpreter
    tail = shape in TAIL
    src = (TAIL if tail else NONTAIL)[shape]
    base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t0 = time.time()
    kw = {"max_iter": n} if tail else {"max_depth": n, "max_iter": None}
    interp = Interpreter(gc_relief=True, **kw)
    interp.run(src)
    dt = time.time() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print("%-12s %-7s n=%-7d %7.2fs %6.2f us/%s  peakRSS %7.1f MB "
          " %6.0f B/%s" % (
              shape, "tail" if tail else "nontail", n, dt,
              dt / n * 1e6, "iter" if tail else "frame",
              rss / 1024.0, (rss - base) * 1024.0 / n,
              "iter" if tail else "frame"))


def main():
    if len(sys.argv) == 3:
        return one(sys.argv[1], int(sys.argv[2]))
    me = os.path.abspath(__file__)
    for group, shapes in (("tail", TAIL), ("nontail", NONTAIL)):
        for shape in shapes:
            for n in SIZES[group]:
                subprocess.run([sys.executable, me, shape, str(n)], check=True)
    print("\nDEFAULT_MAX_ITER derivation: (DEFAULT_MAX_DEPTH x worst B/frame)"
          " / worst B/iter, rounded down.")
    print("Round 366 measured: (20000 x 2084) / 768 = 54270 -> 50000.")


if __name__ == "__main__":
    main()

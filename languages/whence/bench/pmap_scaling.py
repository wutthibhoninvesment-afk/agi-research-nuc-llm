#!/usr/bin/env python3
"""Round 204: isolate PMap's asymptotic win from self_host_memscale.py's
noisier end-to-end numbers (parsing, lexing, guest-evaluator overhead all
mixed in). This script measures ONLY the thing that changed: the
cumulative cost of N sequential `put`s onto a growing record, old
(`dict(fields); fields[k]=v`) vs new (`PMap.put`), with EVERY intermediate
version kept reachable (a list, not a loop variable overwritten) — the
same retention discipline `derived(...)`'s `inputs` gives every Record
in the real interpreter, since that retention is exactly what makes the
naive approach quadratic.

usage: python3 bench/pmap_scaling.py [N] [--keys K]
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from whence.values import PMap  # noqa: E402


def old_style(n, n_keys):
    """The pre-round-204 behaviour: `fields = dict(r.fields); fields[k] = v`
    — a full shallow copy of the CURRENT dict on every put, every version
    kept alive in `versions` (as `derived(...)`'s `inputs` keeps it alive
    for real, via provenance)."""
    versions = [{}]
    d = {}
    for i in range(n):
        d = dict(d)                 # the exact old `b_put` line
        d[i % n_keys] = i
        versions.append(d)
    return versions


def new_style(n, n_keys):
    versions = [PMap()]
    m = PMap()
    for i in range(n):
        m = m.put(i % n_keys, i)
        versions.append(m)
    return versions


def measure(fn, n, n_keys):
    t0 = time.perf_counter()
    versions = fn(n, n_keys)
    elapsed = time.perf_counter() - t0
    # sanity: last version has the right size and content
    last = versions[-1]
    get = (lambda k: last.get(k, None)) if isinstance(last, PMap) else last.get
    assert get(0) is not None or n < n_keys
    return elapsed, len(versions)


def main(argv):
    size_arg = argv[0] if argv and not argv[0].startswith("--") \
        else "200,400,800,1600,3200"
    sizes = [int(x) for x in size_arg.split(",")]
    n_keys = 64
    if "--keys" in argv:
        n_keys = int(argv[argv.index("--keys") + 1])
    print("N sequential puts, %d distinct keys, EVERY version retained "
          "(mirrors provenance retention)" % n_keys)
    print("%8s  %12s  %12s  %8s" % ("N", "old(s)", "new(s)", "old/new"))
    for n in sizes:
        t_old, _ = measure(old_style, n, n_keys)
        t_new, _ = measure(new_style, n, n_keys)
        ratio = t_old / t_new if t_new else float("inf")
        print("%8d  %12.4f  %12.4f  %8.2fx" % (n, t_old, t_new, ratio))


if __name__ == "__main__":
    main(sys.argv[1:])

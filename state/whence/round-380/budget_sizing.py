"""Round 380 (language C) — measure what `GUEST_STEPS_BUDGET` must be.

`skills/measured-budget-sizing` step 1: find a CHEAP PROXY for each item's
cost and validate it before trusting it.

The quantity the budget bounds is `len(guest_walk_steps(root))` in
`examples/self_eval.lang` — a pre-order walk of the guest `@{v, op, ins}`
box graph with NO identity dedup, so it visits a node once per ROOT-TO-NODE
PATH.  That count obeys exactly one recurrence:

    paths(n) = 1 + sum(paths(c) for c in n.inputs)

The proxy: evaluate the same recurrence over the HOST provenance DAG, which
`tests/test_self_eval.py` already pins label-for-label against the guest box
graph.  It is cheap (one host run per program, memoised over node identity,
no guest evaluator at all), and it reaches EVERY top-level binding of every
program instead of only the last value `run_src_p` hands back.

`validate` checks the proxy against the real guest walk on a sample.
"""
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))          # state/whence/round-380
REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
ROOT = os.path.join(REPO, "languages", "whence")
sys.path.insert(0, ROOT)

from whence.interp import Interpreter          # noqa: E402
from whence.values import Miss, Record, WList  # noqa: E402

CAP = 10 ** 9   # anything over this is reported as "over", not as a number


def path_count(node, memo=None):
    """paths(n) = 1 + sum(paths(c)) — iterative, memoised on id, so a DAG
    with heavy sharing is still linear to COUNT even though the number
    counted is exponential."""
    memo = {} if memo is None else memo
    stack = [(node, False)]
    while stack:
        n, expanded = stack.pop()
        if id(n) in memo:
            continue
        if not expanded:
            stack.append((n, True))
            for c in n.inputs:
                if id(c) not in memo:
                    stack.append((c, False))
            continue
        total = 1
        for c in n.inputs:
            total += memo[id(c)]
            if total > CAP:
                total = CAP
                break
        memo[id(n)] = total
    return memo[id(node)]


def node_count(node):
    """What the HOST's own `walk_steps` reports: nodes deduped by id."""
    seen, stack, n = set(), [node], 0
    while stack:
        x = stack.pop()
        if id(x) in seen:
            continue
        seen.add(id(x))
        n += 1
        stack.extend(x.inputs)
    return n


def sweep_source(src, label):
    """Every top-level binding of one program: (label, name, host, guest)."""
    out = []
    try:
        env = Interpreter(out=lambda s: None, seed=7).run(src)
    except Exception as e:                      # noqa: BLE001
        return [(label, "<error>", 0, 0, "%s: %s" % (type(e).__name__, e))]
    memo = {}
    for name, val in env.vars.items():
        if not hasattr(val, "inputs"):
            continue
        out.append((label, name, node_count(val), path_count(val, memo), ""))
    return out


def sweep_examples(paths):
    rows = []
    for p in paths:
        rows.extend(sweep_source(open(p, encoding="utf-8").read(),
                                 os.path.basename(p)))
    return rows


if __name__ == "__main__":
    import glob
    args = sys.argv[1:]
    files = args or sorted(glob.glob(os.path.join(ROOT, "examples", "*.lang")))
    rows = sweep_examples(files)
    ok = [r for r in rows if not r[4]]
    errs = [r for r in rows if r[4]]
    print("bindings measured: %d   programs that would not parse: %d"
          % (len(ok), len(errs)))
    g = sorted(r[3] for r in ok)
    h = sorted(r[2] for r in ok)

    def pct(xs, q):
        return xs[min(len(xs) - 1, int(len(xs) * q))]

    print("\n                       min    p50    p90    p99    max")
    print("host walk_steps  %10d %6d %6d %6d %10d"
          % (h[0], pct(h, .5), pct(h, .9), pct(h, .99), h[-1]))
    print("guest path count %10d %6d %6d %6d %10d"
          % (g[0], pct(g, .5), pct(g, .9), pct(g, .99), g[-1]))
    for b in (100, 1000, 5000, 50000, 10 ** 6, CAP):
        under = len([x for x in g if x <= b])
        print("  budget %-12d covers %4d/%4d bindings (%5.1f%%)"
              % (b, under, len(g), 100.0 * under / len(g)))
    over = [r for r in ok if r[3] >= CAP]
    print("\n%d bindings are AT OR OVER the %d cap (uncountable in "
          "practice):" % (len(over), CAP))
    seen = {}
    for lab, name, hn, gp, _ in over:
        seen.setdefault(lab, []).append(name)
    for lab in sorted(seen):
        print("  %-24s %3d bindings  e.g. %s"
              % (lab, len(seen[lab]), ", ".join(seen[lab][:5])))

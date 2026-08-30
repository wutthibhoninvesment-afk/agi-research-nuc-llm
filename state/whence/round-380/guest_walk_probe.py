"""Round 380 — the REAL guest quantity, and the proxy's validation.

`budget_sizing.py` computes root-to-node PATH COUNT over the HOST DAG as a
cheap proxy for `len(guest_walk_steps(root))` inside `self_eval.lang`.
Step 1 of `skills/measured-budget-sizing` says validate a proxy before
trusting it.  This runs the guest walk for real, on a batch of programs,
and prints proxy vs measured side by side.
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
ROOT = os.path.join(REPO, "languages", "whence")
sys.path.insert(0, ROOT)

from whence.interp import Interpreter          # noqa: E402

sys.path.insert(0, _HERE)
from budget_sizing import path_count, node_count   # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
MARKER = "# ==== SELF-TESTS"


def library_source():
    src = open(EXAMPLE, encoding="utf-8").read()
    assert MARKER in src
    return src.split(MARKER)[0]


def escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def guest_walk_sizes(sources, lib):
    """`len(guest_walk_steps(...))` for each program's FINAL value, measured
    inside the guest.  Uses `run_src_p`, the unstripped variant, so the box
    graph is still there.  One interpreter run for the whole batch."""
    parts = [lib]
    for i, src in enumerate(sources):
        parts.append('let __w%d = len(guest_walk_steps('
                     'guest_history_root((run_src_p("%s")).v)))\n'
                     % (i, escape(src)))
    env = Interpreter(out=lambda s: None, seed=7).run("".join(parts))
    out = []
    for i in range(len(sources)):
        v = env.get("__w%d" % i)
        out.append(None if v is None else v.payload)
    return out


def host_proxy(src):
    """The proxy: path count of the LAST binding of the host run."""
    env = Interpreter(out=lambda s: None, seed=7).run(src)
    last = None
    for name, val in env.vars.items():
        if hasattr(val, "inputs"):
            last = val
    if last is None:
        return None, None
    return node_count(last), path_count(last)


if __name__ == "__main__":
    lib = library_source()
    CASES = [
        'let r = 1',
        'let x = 1 + 2\nlet r = len(steps(x))',
        'let x = 1 / 0\nlet r = len(blame(x))',
        'let x = 1 + 2\nlet y = x * x\nlet r = y + 1',
        'fn f(n) { if n == 0 { 1 } else { n * f(n - 1) } }\nlet r = f(6)',
        'let a = [1, 2, 3]\nlet r = fold(fn(s, x) { s + x }, 0, a)',
        'let x0 = 1 + 2\nlet x1 = x0 + x0\nlet x2 = x1 + x1\nlet r = x2',
        'let x0 = 1 + 2\nlet x1 = x0 + x0\nlet x2 = x1 + x1\n'
        'let x3 = x2 + x2\nlet x4 = x3 + x3\nlet r = x4',
        'let r = note(1 + 2, "m")',
        'let r = map(fn(v) { v * 2 }, range(5))',
    ]
    g = guest_walk_sizes(CASES, lib)
    print("%-6s %-8s %-8s %-8s  %s" % ("case", "guest", "proxy", "hostnodes",
                                       "source"))
    agree = 0
    for i, src in enumerate(CASES):
        hn, hp = host_proxy(src)
        ok = (g[i] == hp)
        agree += ok
        print("%-6d %-8s %-8s %-8s  %s %s"
              % (i, g[i], hp, hn, "OK " if ok else "DIFF",
                 src.replace("\n", " ; ")[:60]))
    print("\nproxy == measured on %d/%d cases" % (agree, len(CASES)))

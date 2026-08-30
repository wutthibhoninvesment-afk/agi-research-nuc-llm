"""Round 380 — the OBSERVABLE host/guest `steps()` differential.

`ins_arity_sweep.py` compares raw provenance nodes: host `Prov.label()` vs
the guest box's single `op` slot.  That is the wrong level to judge v0.30
by.  A Whence program never sees a raw box; it sees `steps(x)`, whose
records go through `guest_step_record` — which SPLITS the guest label at
the first space and, for a miss, recovers the detail from `reasons()`.

So this compares what a program can actually observe: for each source, the
full list of `(op, detail, depth, inputs)` step records, host vs guest, in
order.  Anything that differs here is a divergence a user can see.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
ROOT = os.path.join(REPO, "languages", "whence")
sys.path.insert(0, ROOT)
sys.path.insert(0, _HERE)

from whence.interp import Interpreter                      # noqa: E402
from whence.values import Record, WList                    # noqa: E402
from guest_walk_probe import library_source, escape        # noqa: E402
from ins_arity_sweep import CASES                          # noqa: E402

FIELDS = ("op", "detail", "depth", "inputs")

PROBE = ('map(fn(s) { [s.op, s.detail, str(s.depth), str(s.inputs)] }, '
         'steps(r))')


def deep(p):
    if isinstance(p, WList):
        return [deep(x.payload) for x in p]
    if isinstance(p, Record):
        return dict((k, deep(v.payload)) for k, v in p.fields.items())
    return p


def host_steps(expr):
    src = "let r = %s\nlet __p = %s\n" % (expr, PROBE)
    env = Interpreter(out=lambda s: None, seed=7).run(src)
    v = env.get("__p")
    return None if v is None else deep(v.payload)


def guest_steps(exprs, lib):
    parts = [lib]
    for i, e in enumerate(exprs):
        src = "let r = %s\nlet __p = %s\n" % (e, PROBE)
        parts.append('let __o%d = run_src("%s")\n' % (i, escape(src)))
    env = Interpreter(out=lambda s: None, seed=7).run("".join(parts))
    return [deep(env.get("__o%d" % i).payload.fields["v"].payload)
            for i in range(len(exprs))]


if __name__ == "__main__":
    lib = library_source()
    exprs = [e for _, e in CASES]
    g = guest_steps(exprs, lib)
    agree, diffs = 0, []
    for (label, expr), gv in zip(CASES, g):
        hv = host_steps(expr)
        if hv == gv:
            agree += 1
        else:
            diffs.append((label, expr, hv, gv))
    print("observable `steps(r)` agreement: %d/%d" % (agree, len(CASES)))
    for label, expr, hv, gv in diffs:
        print("\n--- %-14s %s" % (label, expr))
        hv = hv if isinstance(hv, list) else [hv]
        gv = gv if isinstance(gv, list) else [gv]
        for j in range(max(len(hv), len(gv))):
            a = hv[j] if j < len(hv) else None
            b = gv[j] if j < len(gv) else None
            mark = "   " if a == b else " ! "
            print("  %s host %-52s guest %s" % (mark, str(a)[:52], str(b)[:52]))

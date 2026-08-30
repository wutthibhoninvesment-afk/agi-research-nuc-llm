#!/usr/bin/env python3
"""Round 371 (SWE-loop D) — measure the guest evaluator's TAIL-call ceiling
and how often the guest-differential oracle's one-sided-depth exemption
fires with the HOST side succeeding.

`harness/swe/guest.py::agree` exempts ANY field where either side scrubbed
to `&DEPTHMISS&`. That exemption was written for a real asymmetry (the
guest pays ~6.8 host frames per guest call, so it exhausts `max_depth`
first). It also, unintentionally, exempts the case where the host produced
a perfectly good VALUE and the guest refused the program outright.

usage: python3 state/swe/round-371/tail_parity.py ceiling
       python3 state/swe/round-371/tail_parity.py sweep [N]
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from harness.swe import guest as G, oracles as O          # noqa: E402
from harness.swe.killers import load_whence               # noqa: E402
from harness.swe.fuzz import WHENCE_ROOT                  # noqa: E402

TPL = ('fn go(i) { if i == 0 { 42 } else { go(i - 1) } }\n'
       'let r = go(%d)\n'
       'let __result = @{r: (r rescue (if contains(join(reasons(r), "|"), '
       '"depth") { "&DEPTHMISS&" } else { "&MISS&" }))}\n')


def _pkg():
    return load_whence(WHENCE_ROOT, "r371tail")


def host_field(pkg, src, field="r"):
    prog = O._parse(pkg, src)
    interp, env, _out = O._run_ast(pkg, prog, max_depth=2000)
    res = env.get("__result")
    return res.payload.fields[field].payload, interp.peak_tail


def guest_field(h, src, field="r"):
    rec = h.eval_program(src)
    gv = rec.fields["v"].payload
    if isinstance(gv, h.V.Record):
        return gv.fields[field].payload
    return "GUEST_INTERNAL_MISS"


def ceiling():
    """Bisect the exact tail-loop length at which the guest starts to
    refuse a program the host answers. Host answer is 42 throughout."""
    pkg = _pkg()
    h = G.GuestHarness(WHENCE_ROOT, pkg, max_depth=2000)
    lo, hi = 1, 1000                       # lo agrees, hi diverges
    assert guest_field(h, TPL % lo) == 42
    assert guest_field(h, TPL % hi) != 42
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if guest_field(h, TPL % mid) == 42:
            lo = mid
        else:
            hi = mid
    hp_lo, pt_lo = host_field(pkg, TPL % lo)
    hp_hi, pt_hi = host_field(pkg, TPL % hi)
    print("guest answers  go(%d) -> %r   (host %r, peak_tail %d)"
          % (lo, guest_field(h, TPL % lo), hp_lo, pt_lo))
    print("guest refuses  go(%d) -> %r   (host %r, peak_tail %d)"
          % (hi, guest_field(h, TPL % hi), hp_hi, pt_hi))
    print("GUEST TAIL CEILING = %d iterations" % lo)
    return lo


def sweep(n=200):
    """Over the guest fuzz corpus: how often does the depth exemption fire,
    and in how many of those did the HOST side produce a real value?

    Goes through `run_oracle` -- NOT the bare oracle -- because that is
    where the SIGALRM lives. Round 365 called the bare oracle from a
    scratch sweep and lost 131 of 141 seeds to one hang while reporting
    exit code 0; round 371 is not repeating it in the round that is about
    stale pins.
    """
    pkg = _pkg()
    d = dict(pkg)
    d.setdefault("root", WHENCE_ROOT)
    rows, t_start = [], time.time()
    kinds = {}
    for i in range(n):
        src = G.generate_guest_program(i)
        t0 = time.time()
        o = O.run_oracle(G.GUEST_ORACLE, d, src, timeout_s=30.0,
                         max_depth=2000)
        dt = round(time.time() - t0, 2)
        kinds[o.kind] = kinds.get(o.kind, 0) + 1
        row = {"seed": i, "kind": o.kind, "s": dt,
               "detail": o.detail[:160]}
        rows.append(row)
        if "host_valued" in o.detail:
            print("seed %-4d HOST-VALUED DEPTH EXEMPTION  %s" % (i, o.detail[:90]))
        if o.kind not in ("ok", "parse_error"):
            print("seed %-4d %-12s %.1fs %s" % (i, o.kind, dt, o.detail[:80]))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "tail_parity_sweep.json")
    json.dump(rows, open(out, "w"), indent=1)
    exempt = [r for r in rows if "depth_exempt" in r["detail"]]
    hostv = [r for r in exempt if "host_valued" in r["detail"]]
    slow = sorted((r["s"], r["seed"]) for r in rows)[-5:]
    print("\n%d seeds in %.1fs   kinds=%s" % (n, time.time() - t_start, kinds))
    print("  depth exemption fired at all        : %d seed(s)" % len(exempt))
    print("  ... with a HOST VALUE (blind spot)  : %d seed(s)  %s"
          % (len(hostv), [r["seed"] for r in hostv][:20]))
    print("  slowest (s, seed)                   : %s" % (slow,))
    print("  wrote %s" % out)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ceiling"
    if cmd == "ceiling":
        ceiling()
    else:
        sweep(int(sys.argv[2]) if len(sys.argv) > 2 else 200)

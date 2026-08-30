#!/usr/bin/env python3
"""Round 371 (D): the tail-loop CONTRACTS this repo's own examples pin,
put through the self-hosted evaluator.

`self_eval.lang`'s round-210 comment justifies `GUEST_MAX_DEPTH = 400` with
"no example or self-hosting test corpus this project has ever run comes
close to 400 real guest-level call frames". `apply_closure` -- the one
choke point that guard sits in -- is reached by EVERY guest call including
a tail bounce, so that claim is a claim about tail loops too.

The examples themselves are not guest-safe (`print`/`why`/`steps` are
banned from the guest-differential), so this runs their tail-loop
assertions, verbatim, as standalone programs.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from harness.swe import guest as G, oracles as O          # noqa: E402
from harness.swe.killers import load_whence               # noqa: E402
from harness.swe.fuzz import WHENCE_ROOT                  # noqa: E402

SCRUB = ('let __result = @{r: (r rescue (if contains(join(reasons(r), "|"), '
         '"depth") { "&DEPTHMISS&" } else { "&MISS&" }))}\n')

CASES = [
    ("deep.lang  'a tail loop runs 10x past max_depth'", 200000,
     'fn count_tail(n, acc) { if n == 0 { acc } else { count_tail(n - 1, acc + 1) } }\n'
     'let r = count_tail(200000, 0)\n'),
    ("tco.lang   '100000-iteration tail loop under the depth cap'", 100000,
     'fn sum_to(i, acc) { if i == 0 { acc } else { sum_to(i - 1, acc + i) } }\n'
     'let r = sum_to(100000, 0)\n'),
    ("tco.lang   'mutual tail recursion'", 100001,
     'fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n'
     'fn odd(n) { if n == 0 { false } else { even(n - 1) } }\n'
     'let r = even(100001)\n'),
    ("deep.lang  'mutual recursion 10001 deep' (tail position!)", 10001,
     'fn even(n) { if n == 0 { true } else { odd(n - 1) } }\n'
     'fn odd(n) { if n == 0 { false } else { even(n - 1) } }\n'
     'let r = even(10001)\n'),
    ("deep.lang  'count(15000)' (NON-tail)", 15000,
     'fn count(n) { if n == 0 { 0 } else { 1 + count(n - 1) } }\n'
     'let r = count(15000)\n'),
]


def main():
    pkg = load_whence(WHENCE_ROOT, "r371corpus")
    h = G.GuestHarness(WHENCE_ROOT, pkg, max_depth=2000)
    V = h.V
    print("%-52s %-6s  %-22s %-22s" % ("corpus contract", "iters",
                                       "HOST (max_depth=2000)", "GUEST"))
    for label, n, body in CASES:
        src = body + SCRUB
        t0 = time.time()
        prog = O._parse(pkg, src)
        _i, env, _o = O._run_ast(pkg, prog, max_depth=2000)
        hp = env.get("__result").payload.fields["r"].payload
        ht = time.time() - t0
        t0 = time.time()
        rec = h.eval_program(src)
        gv = rec.fields["v"].payload
        gp = (gv.fields["r"].payload if isinstance(gv, V.Record)
              else "GUEST_INTERNAL_MISS")
        gt = time.time() - t0
        print("%-52s %-6d  %-22s %-22s  host %.2fs guest %.2fs"
              % (label, n, repr(hp)[:22], repr(gp)[:22], ht, gt))


if __name__ == "__main__":
    main()

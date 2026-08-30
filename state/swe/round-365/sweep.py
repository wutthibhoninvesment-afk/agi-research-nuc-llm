"""Round 365 (SWE-loop D): the shape-declaration guest differential.

Runs `oracle_self_eval` over every seed in range(N) whose guest program
declares a `shape`, with the shape binding now IN the compared `__result`
record (this round's `generate_guest_program` change). Records per-seed
kind + seconds so the cost of the new coverage is measured, not asserted.
"""
import sys, re, time, json
sys.path.insert(0, "harness")
from swe import guest as G
from swe import oracles as O
from swe.killers import load_whence
from swe.fuzz import WHENCE_ROOT
from collections import Counter

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
OUT = sys.argv[2] if len(sys.argv) > 2 else "state/swe/round-365/shape_sweep.json"

pkg = load_whence(WHENCE_ROOT, "r365sweep")
h = G.GuestHarness(WHENCE_ROOT, pkg)
pat = re.compile(r"(^|\n)\s*shape\s")
hits = [i for i in range(N) if pat.search(G.generate_guest_program(i))]
print("N=%d shape-emitting seeds: %d (%.1f%%)" % (N, len(hits), 100.0*len(hits)/N), flush=True)

rows = []
t0 = time.time()
for i in hits:
    src = G.generate_guest_program(i)
    shapes = re.findall(r"(?m)^shape\s+(\w+)", src)
    tail = src[src.index("let __result"):]
    compared = re.findall(r"(\w+): \(", tail)
    t = time.time()
    # Round 365: via `run_oracle`, NOT the bare `oracle_self_eval`. The bare
    # oracle has no timeout (the SIGALRM lives in `run_oracle`), and this
    # script's first version lost 131 of 141 seeds to seed 31's non-
    # terminating program -- round 185's root cause, repeated.
    try:
        o = O.run_oracle(G.GUEST_ORACLE, dict(pkg, root=WHENCE_ROOT), src,
                         timeout_s=30.0, max_depth=2000, harness=h)
        kind, detail = o.kind, o.detail
    except BaseException as e:
        kind, detail = "EXC:" + type(e).__name__, str(e)[:400]
    rows.append({"seed": i, "kind": kind, "s": round(time.time()-t, 2),
                 "shapes": shapes,
                 "shapes_compared": [s for s in shapes if s in compared],
                 "n_compared": len(compared), "detail": detail[:400]})
    print("%4d %-14s %5.2fs shapes=%s compared=%s" % (
        i, kind, rows[-1]["s"], shapes, rows[-1]["shapes_compared"]), flush=True)

el = time.time() - t0
print("TOTAL %.1fs over %d seeds (%.2fs/seed)" % (el, len(rows), el/max(1, len(rows))), flush=True)
print("KINDS", Counter(r["kind"] for r in rows), flush=True)
missing = [r["seed"] for r in rows if len(r["shapes_compared"]) != len(r["shapes"])]
print("seeds whose shape name did NOT reach __result:", missing, flush=True)
for r in rows:
    if r["kind"] != "ok":
        print("NONOK", json.dumps(r), flush=True)
json.dump({"n_seeds": N, "hits": hits, "elapsed_s": round(el, 1), "rows": rows},
          open(OUT, "w"), indent=1)
print("wrote", OUT)

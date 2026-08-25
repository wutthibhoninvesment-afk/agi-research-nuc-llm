"""Paired benchmark: default test order vs kill-first order on KILLED mutants.

For each sampled killed mutant the prioritizer learns from every OTHER
record (leave-one-out), then the mutant runs twice — default order, learned
order — back to back in the same worker, so both legs see the same load.
Records seconds, verdict and the killing file for each leg.
"""
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from . import killers as K
from .fuzz import WHENCE_ROOT
from .mutation import run_mutant, DEFAULT_TEST_CMD
from .prioritize import Prioritizer, learn, load_records, default_test_files, killed_by


def sample_killed(records, n, seed):
    pool = [d for d in records if d["status"] == "killed" and killed_by(d.get("detail"))]
    rng = random.Random(seed)
    return sorted(rng.sample(pool, min(n, len(pool))), key=lambda d: d["id"])


def run_pair(d, records, root, files, timeout_s, k):
    others = [r for r in records if r["id"] != d["id"]]
    pr = Prioritizer(learn(others), files, k=k)
    m_def, m_pri = K.rebuild_mutants(root, [d])[0], K.rebuild_mutants(root, [d])[0]
    order = pr.order_for(m_pri.path, m_pri.lineno, m_pri.op)
    run_mutant(m_def, root, DEFAULT_TEST_CMD, timeout_s)
    run_mutant(m_pri, root, pr.cmd_for(m_pri, DEFAULT_TEST_CMD), timeout_s)
    return {"id": d["id"], "op": d["op"], "line": d["line"], "baseline_killed_by": killed_by(d["detail"]),
            "first_file": order[0], "learned_files": order[:k],
            "default": {"status": m_def.status, "seconds": round(m_def.seconds, 1), "killed_by": killed_by(m_def.detail)},
            "learned": {"status": m_pri.status, "seconds": round(m_pri.seconds, 1), "killed_by": killed_by(m_pri.detail)}}


def summarize(rows):
    ratios = sorted(r["learned"]["seconds"] / max(r["default"]["seconds"], 0.1) for r in rows)
    same = sum(1 for r in rows if r["default"]["status"] == r["learned"]["status"])
    first_hit = sum(1 for r in rows if r["learned"]["killed_by"] == r["first_file"])
    return {"n": len(rows), "verdict_same": same, "first_file_killed": first_hit,
            "median_ratio": round(ratios[len(ratios) // 2], 3) if ratios else None,
            "mean_ratio": round(sum(ratios) / len(ratios), 3) if ratios else None,
            "sum_default_s": round(sum(r["default"]["seconds"] for r in rows), 1),
            "sum_learned_s": round(sum(r["learned"]["seconds"] for r in rows), 1)}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True, help="mutation JSON or partial.jsonl")
    ap.add_argument("--root", default=WHENCE_ROOT)
    ap.add_argument("-n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--json", required=True)
    a = ap.parse_args(argv)
    root = os.path.realpath(a.root)
    records = load_records(a.src)
    files = default_test_files(root)
    sample = sample_killed(records, a.n, a.seed)
    rows = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for row in ex.map(lambda d: run_pair(d, records, root, files, a.timeout, a.k), sample):
            rows.append(row)
            print("%-28s default %6.1fs (%s)  learned %6.1fs (%s) first=%s" % (
                row["id"], row["default"]["seconds"], row["default"]["status"],
                row["learned"]["seconds"], row["learned"]["status"], row["first_file"]), flush=True)
    out = {"source": a.src, "n": len(rows), "seed": a.seed, "k": a.k, "workers": a.workers,
           "seconds": round(time.time() - t0, 1), "summary": summarize(rows), "rows": rows}
    with open(a.json, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out["summary"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Round 405: pool the owed-batch probes and score the design.

Reads only `state/trigger-eval/round-405-run{A,B,C,D}.json`, which were run
as four SEPARATE invocations of trigger_eval.py under one configuration
(native / sonnet / strict / --concurrency 3), A-C at --repeats 1 and D at
--repeats 2. Prints, in order:

  1. per-case k/n pooled over the four runs, with the per-run split, so a
     stable per-case miss is visible as such rather than as a rate;
  2. per-skill pooled Wilson verdict for the nine skills the batch owed;
  3. the prospective ICC from THESE runs (run D is what makes the
     within-run term estimable at all), and the design table it implies.
"""
import json, os, sys
sys.path.insert(0, "skills/skill-authoring/scripts")
import trigger_eval as te

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
OWED = ["untested-default-path", "filter-shares-the-defect",
        "instruments-already-running", "residency-is-not-allocation",
        "run-the-comparison-you-suppress", "would-a-constant-have-passed",
        "kill-what-you-launched", "recorder-in-the-record",
        "sanitiser-outgrows-its-noise"]

cases = te.load_cases("skills/trigger-cases.json")
catalog = te.load_catalog(["skills"])
by_id = {c["id"]: c for c in cases}
reports = [r for r in te.load_reports("state/trigger-eval")
           if "round-405-run" in os.path.basename(r[0])]
reports.sort(key=lambda r: os.path.basename(r[0]))
names = [os.path.basename(p)[-6] for p, _, _ in reports]
print("runs pooled: %s\n" % ", ".join(os.path.basename(p) for p, _, _ in reports))

# --- 1. per case -----------------------------------------------------------
print("%-22s %-32s %-13s %s" % ("case", "expect", "per-run k/n", "pooled"))
percase = {}
for cid in sorted(by_id):
    if cid not in [c.strip() for c in open("state/round-405/batch-cases.txt").read().split(",")]:
        continue
    exp = set(by_id[cid]["expect"])
    cells, errs = [], 0
    for path, _, data in reports:
        k = n = 0
        for r in data["results"]:
            if r.get("id") != cid:
                continue
            if r.get("error"):
                errs += 1
                continue
            n += 1
            fired = set(r.get("fired") or [])
            ok = (fired == set()) if not exp else exp <= fired
            k += 1 if ok else 0
        cells.append((k, n))
    K, N = sum(c[0] for c in cells), sum(c[1] for c in cells)
    percase[cid] = (K, N, cells, errs)
    lo, hi = te.wilson_interval(K, N)
    print("%-22s %-32s %-13s %d/%d [%.2f,%.2f]%s"
          % (cid, ",".join(sorted(exp)) or "(none: nothing may fire)",
             " ".join("%d/%d" % c for c in cells), K, N, lo, hi,
             "  ERRS=%d" % errs if errs else ""))

# --- 2. per owed skill -----------------------------------------------------
print("\n%-34s %-8s %-6s %-14s %s" % ("skill", "k/n", "runs", "Wilson 95%", "verdict"))
rows = {r["name"]: r for r in te.pooled_rows(catalog, cases, reports)}
for s in OWED:
    r = rows.get(s)
    if not r:
        print("%-34s (no pooled row)" % s); continue
    print("%-34s %-8s %-6d [%.2f, %.2f]   %s"
          % (s, "%d/%d" % (r["k"], r["n"]), r["runs"], r["lo"], r["hi"], r["verdict"]))

# --- 3. the design -----------------------------------------------------------
rv = te.run_variance(catalog, cases, reports)
print("\nprospective run-variance over THESE four runs:")
print("  ", rv)
if rv:
    icc = rv["icc"]
    def eff(d): return sum(te.effective_draws(k, icc) for k in d)
    print("\n  design                probes  n_eff   n_eff/probe   (at icc=%.3f)" % icc)
    for nm, d in (("1 x --repeats 6", [6]), ("3 x --repeats 2 (r393)", [2]*3),
                  ("3x1 + 1x2 (r405)", [1,1,1,2]), ("5 x --repeats 1", [1]*5),
                  ("6 x --repeats 1", [1]*6)):
        print("  %-22s %-7d %-7.3f %.4f" % (nm, sum(d), eff(d), eff(d)/sum(d)))

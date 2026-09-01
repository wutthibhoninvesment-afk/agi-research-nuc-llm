"""Round 440. What the audit would print if CP03p's precondition had been
widened to `holds` or to `broken` instead of to `broken_on_branch`.

Run from `languages/whence/`:  python3 ../../state/whence/round-440/counterfactual.py
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../../../languages/whence")
import polarity as P

HERE = os.path.dirname(os.path.abspath(__file__))
R422 = os.path.join(HERE, "..", "round-422")
GUEST = os.path.join(os.path.dirname(P.__file__), "examples", "self_host.lang")

for regname, runname in (("host-pins-plus-repointed.json", "run-repointed.json"),
                         ("host-pins-plus.json", "run-plus.json")):
    reg = json.load(open(os.path.join(R422, regname), encoding="utf-8"))
    res = json.load(open(os.path.join(R422, runname), encoding="utf-8"))["results"]
    base = open(GUEST, encoding="utf-8").read()
    vs = P.classify_file(GUEST)
    pre = P.precondition_map(reg["pins"], base, vs)
    measured = {r["id"]: r["verdict"] for r in res}
    print("=" * 72)
    print("%s   (CP03p measured %s)" % (regname, measured.get("CP03p")))
    for forced in (P.PRE_BROKEN_ON_BRANCH, P.PRE_HOLDS, P.PRE_BROKEN):
        m = {k: dict(v) for k, v in pre.items()}
        m["CP03p"]["status"] = forced
        rows = {r["id"]: r for r in
                P.audit_registry(reg["pins"], vs, res, m)}
        law = P.check_law(reg["pins"], res, vs, m)
        buckets = {k: [r["id"] for r in law[k]]
                   for k in ("strict_violations", "excused", "undecided")}
        print("  CP03p pre=%-16s -> audit %-19s | law strict=%s excused=%s "
              "undecided=%s"
              % (forced, (rows.get("CP03p") or {}).get("status"),
                 buckets["strict_violations"], buckets["excused"],
                 buckets["undecided"]))

"""Round 497 (SWE-loop D): run named mutants and report the verdict.

Round 491's rule, kept: a comment saying "kills X" is a claim, not a result.
A test written to kill a survivor is run AGAINST that survivor before the
round says it closed anything -- and round 491's own first pass was 5 of 9,
so the rule earns its keep.

    .venv/bin/python3 state/swe/round-497/kill_check.py ID [ID ...] [--out P]

Uses `swe.linkcopy` sandboxes (round 497) and does NOT touch the campaign
ledger: these ids are already in it with round 491's verdict, and a
re-verdict against a CHANGED suite is a different measurement that would
corrupt the resume set if appended.
"""
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "harness"))

import swe.linkcopy as LC                                         # noqa: E402
import swe.mutation as MU                                         # noqa: E402
import swe.nodecampaign as NC                                     # noqa: E402

REL = os.path.join("nuc", "perturbation.py")
TESTS = os.path.join("nuc", "tests", "test_perturbation.py")
PY = os.path.join(ROOT, ".venv", "bin", "python3")


def main(argv):
    out_path = None
    if "--out" in argv:
        i = argv.index("--out")
        out_path = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    ids = set(argv)
    if not ids:
        print(__doc__)
        return 2

    mutants, digest = NC.select_mutants(ROOT, REL, None)
    by_id = {m.id: m for m in mutants}
    missing = sorted(i for i in ids if i not in by_id)
    cmd = [PY, "-m", "pytest", "-x", "-q", TESTS]

    rows = []
    master = LC.MasterTree(ROOT, deep_witness=True)
    master.stage()
    try:
        for mid in sorted(ids & set(by_id)):
            m = by_id[mid]
            t0 = time.time()
            MU.run_mutant(m, ROOT, cmd, timeout_s=600.0, copier=master,
                          tmp_dir=master.workdir)
            drift = master.check(label=mid)
            rows.append({"id": mid, "line": m.lineno, "op": m.op,
                         "description": m.description, "status": m.status,
                         "seconds": round(time.time() - t0, 2),
                         "detail": (m.detail or "")[:300],
                         "drift": [p for p, _ in drift]})
            print("%-32s %-9s %6.2fs" % (mid, m.status, rows[-1]["seconds"]),
                  flush=True)
            if m.status == "survived":
                print("    STILL ALIVE", flush=True)
        deep = master.check(label="end", deep=True, restage_on_drift=False)
    finally:
        stats = master.as_dict()
        master.close()

    rep = {"subject_digest": digest, "n_asked": len(ids),
           "n_run": len(rows), "missing_ids": missing,
           "killed": [r["id"] for r in rows if r["status"] == "killed"],
           "survived": [r["id"] for r in rows if r["status"] == "survived"],
           "deep_drift_at_end": [p for p, _ in deep],
           "master": stats, "rows": rows}
    if out_path:
        p = os.path.join(ROOT, out_path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in rep.items()
                      if k not in ("rows", "master")}, indent=1, sort_keys=True))
    return 0 if not rep["survived"] and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

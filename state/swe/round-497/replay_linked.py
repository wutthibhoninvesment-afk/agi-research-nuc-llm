"""Round 497 (SWE-loop D): does the cheap sandbox change any verdict?

`swe.linkcopy` replaces the per-mutant `shutil.copytree` with a hardlink tree
over one staged master. That is a claim about COST. This script tests the
claim about CORRECTNESS the cost change is only acceptable under: replay
mutants round 491 already scored under the byte copy, through the linked
sandbox, and require the same `status` for every one.

Round 491's slice ran all 55 mutants with `oracle == "subset"` against the
same `subject_digest`, so the selection is reproducible from the committed
coverage map -- verified here, not assumed: the sample's `n_units` must match
what the ledger recorded for the same id.

    .venv/bin/python3 state/swe/round-497/replay_linked.py [n] [out.json]

Writes a receipt; prints one line per mutant. NEVER appends to the ledger --
these mutants are already scored and a replay is evidence, not a slice.
"""
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "harness"))

import swe.coverage as CV                                         # noqa: E402
import swe.linkcopy as LC                                         # noqa: E402
import swe.nodecampaign as NC                                     # noqa: E402
from swe.prioritize import MapPrioritizer                         # noqa: E402

LEDGER = os.path.join(ROOT, "state", "swe", "perturbation-mutation-ledger.jsonl")
COV = os.path.join(ROOT, "state", "swe", "perturbation-cov-by-test.json")
REL = os.path.join("nuc", "perturbation.py")
TESTS = os.path.join("nuc", "tests", "test_perturbation.py")
PY = os.path.join(ROOT, ".venv", "bin", "python3")


def sample(records, n):
    """Deterministic, stratified over status: `n // 2` of each, taken evenly
    across the id-sorted list so the sample is not one contiguous region."""
    out = []
    for status in ("killed", "survived"):
        pool = sorted((r for r in records if r["status"] == status),
                      key=lambda r: r["id"])
        want = max(1, n // 2)
        if not pool:
            continue
        step = max(1, len(pool) // want)
        out.extend(pool[::step][:want])
    return sorted(out, key=lambda r: r["id"])


def main(argv):
    n = int(argv[0]) if argv else 12
    out_path = argv[1] if len(argv) > 1 else os.path.join(
        ROOT, "state", "swe", "round-497", "linked-replay.json")

    records = [json.loads(l) for l in open(LEDGER, encoding="utf-8") if l.strip()]
    want = {r["id"]: r for r in sample(records, n)}

    cov = CV.load(COV)
    prio = MapPrioritizer(cov, CV.test_units(cov), subset=True, root=ROOT,
                          require_fresh=True)
    mutants, digest = NC.select_mutants(ROOT, REL, NC.parse_ranges(NC.R491_RANGES))
    base = [PY, "-m", "pytest", "-x", "-q", TESTS]

    rows, wd = [], None
    master = LC.MasterTree(ROOT, deep_witness=True)
    master.stage()
    try:
        for m in mutants:
            old = want.get(m.id)
            if old is None or old.get("subject_digest") != digest:
                continue
            units, basis = prio.files_for(m)
            cmd = (list(base[:-1]) + list(units)) if basis == "subset" else base
            t0 = time.time()
            import swe.mutation as MU
            MU.run_mutant(m, ROOT, cmd, timeout_s=180.0, copier=master,
                          tmp_dir=master.workdir)
            secs = round(time.time() - t0, 2)
            drift = master.check(label=m.id)
            row = {"id": m.id, "was": old["status"], "now": m.status,
                   "agree": old["status"] == m.status,
                   "was_seconds": old["seconds"], "now_seconds": secs,
                   "was_n_units": old["n_units"], "now_n_units": len(units),
                   "units_match": old["n_units"] == len(units),
                   "drift": [p for p, _ in drift]}
            rows.append(row)
            print("%-30s was=%-8s now=%-8s %5.2fs -> %5.2fs  units %s%s"
                  % (row["id"], row["was"], row["now"], row["was_seconds"],
                     row["now_seconds"],
                     "ok" if row["units_match"] else "MISMATCH",
                     "  DRIFT" if drift else ""), flush=True)
        deep = master.check(label="end of replay", deep=True,
                            restage_on_drift=False)
    finally:
        wd = master.as_dict()
        master.close()

    agree = sum(1 for r in rows if r["agree"])
    tot_was = sum(r["was_seconds"] for r in rows)
    tot_now = sum(r["now_seconds"] for r in rows)
    rep = {
        "n_replayed": len(rows), "n_agree": agree,
        "agreement_pct": round(100.0 * agree / len(rows), 1) if rows else None,
        "units_match_all": all(r["units_match"] for r in rows),
        "seconds_ledger_total": round(tot_was, 2),
        "seconds_linked_total": round(tot_now, 2),
        "ratio_linked_over_ledger": (round(tot_now / tot_was, 3) if tot_was else None),
        "deep_drift_at_end": [p for p, _ in deep],
        "master": wd, "rows": rows,
        "subject_digest": digest,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in rep.items() if k not in ("rows", "master")},
                     indent=1, sort_keys=True))
    return 0 if agree == len(rows) and rows else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

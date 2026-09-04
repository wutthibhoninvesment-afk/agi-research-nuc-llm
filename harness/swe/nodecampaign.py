"""Nodeid-subset mutation campaign (round 491, SWE-loop D).

The item this closes a first slice of: `nuc/tests/test_perturbation.py` had
never been mutation-tested, carried as a next-step by rounds 472, 478, 484
and 490. It was never neglect. `nuc/perturbation.py` has 1794 mutation sites
and its suite is 233 tests in ONE file taking 96.0 s, so the program's only
cost-reduction mechanism -- `prioritize.MapPrioritizer(subset=True)`, whose
unit is the test FILE -- selects the whole suite for every mutant and buys
exactly nothing. 1794 x 96.0 s on a 1-core box is 47.8 h against a 3300 s
round.

This runner pairs three things:
  * `coverage.collect(by_test=True)` -- per-NODEID coverage (round 491);
  * `MapPrioritizer`, unchanged, fed nodeid units instead of file units;
  * `nodeguard.SubsetBaseline` -- the soundness condition finer granularity
    creates. See that module: an order-dependent test manufactures a KILL,
    and it inflates the exact number the campaign reports.

It is deliberately BUDGETED and RESUMABLE rather than complete. A slice
appends to a JSONL ledger keyed by mutant id, and a later round's slice skips
what a previous one already scored -- the shape `state/whence-slow-ledger.jsonl`
(round 469) and `state/slow-tier-ledger.jsonl` (round 439) already use, for
the same reason: the measurement is bigger than any one round.

NO SILENT TRUNCATION. Every report says how many mutants the budget left
unrun, and a run that scores 89 of 1794 says 89 of 1794.
"""

import json
import os
import time

from . import coverage as CV
from . import mutation as MU
from . import nodeguard as NG
from .prioritize import MapPrioritizer

LEDGER = os.path.join("state", "swe", "perturbation-mutation-ledger.jsonl")


def load_ledger(path):
    """`{mutant_id: record}` for every mutant already scored against the
    subject digest it was scored at. The digest is part of the identity on
    purpose: a mutant id is `basename:line:op#i` and `i` is POSITIONAL
    (see `mutation.py`'s frozen-id docstring), so the same id on a moved
    source is a different mutant and must not be skipped."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[(r["id"], r.get("subject_digest"))] = r
    return out


def append_ledger(path, rec):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def select_mutants(root, rel, line_ranges=None, ops=None):
    with open(os.path.join(root, rel), encoding="utf-8") as fh:
        src = fh.read()
    ms = MU.generate(src, rel, ops=ops)
    if line_ranges:
        ms = [m for m in ms
              if any(lo <= m.lineno <= hi for lo, hi in line_ranges)]
    return ms, CV._file_hash(os.path.join(root, rel)) if hasattr(CV, "_file_hash") else None


def run_slice(root, rel, cov_path, base_cmd, line_ranges=None, budget_s=600.0,
              timeout_s=180.0, ledger=LEDGER, full_cmd=None, on_result=None):
    """Score as many unscored mutants as `budget_s` allows.

    Returns a report dict. `full_cmd` (default `base_cmd`) is what a mutant
    falls back to when its subset is poisoned or empty -- the full suite,
    which is always a sound oracle and is why a poisoned subset costs
    accuracy nothing, only time.
    """
    cov = CV.load(cov_path)
    if not CV.is_by_test(cov):
        raise ValueError("%s is not a by-test coverage map "
                         "(collect with by_test=True)" % cov_path)
    prio = MapPrioritizer(cov, CV.test_units(cov), subset=True, root=root,
                          require_fresh=True)
    full_cmd = list(full_cmd or base_cmd)
    guard = NG.SubsetBaseline(root, base_cmd, timeout_s=timeout_s)

    mutants, digest = select_mutants(root, rel, line_ranges)
    done = load_ledger(ledger)
    todo = [m for m in mutants if (m.id, digest) not in done]

    t0 = time.time()
    ran, out_of_budget = [], 0
    for i, m in enumerate(todo):
        if time.time() - t0 > budget_s:
            out_of_budget = len(todo) - i
            break
        units, basis = prio.files_for(m)
        if basis == "subset" and guard.is_clean(units):
            cmd, oracle = guard.cmd_for(units), "subset"
        else:
            cmd, oracle = full_cmd, "full"
        t1 = time.time()
        MU.run_mutant(m, root, cmd, timeout_s=timeout_s)
        rec = {"id": m.id, "path": m.path, "line": m.lineno, "op": m.op,
               "description": m.description, "status": m.status,
               "seconds": round(time.time() - t1, 2), "oracle": oracle,
               "n_units": len(units), "subject_digest": digest,
               "detail": m.detail[:400]}
        append_ledger(ledger, rec)
        ran.append(rec)
        if on_result:
            on_result(rec)

    return report(ran, mutants, todo, out_of_budget, guard, prio, time.time() - t0)


def report(ran, mutants, todo, out_of_budget, guard, prio, seconds):
    by_status = {}
    for r in ran:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    killed = by_status.get("killed", 0)
    survived = by_status.get("survived", 0)
    scorable = killed + survived
    sub = [r for r in ran if r["oracle"] == "subset"]
    return {
        "n_sites_in_scope": len(mutants),
        "n_already_scored": len(mutants) - len(todo),
        "n_run_this_slice": len(ran),
        "n_left_unrun_by_budget": out_of_budget,
        "by_status": by_status,
        "kill_rate": (round(100.0 * killed / scorable, 1) if scorable else None),
        "seconds": round(seconds, 1),
        "seconds_per_mutant": (round(seconds / len(ran), 2) if ran else None),
        "oracle": {"subset": len(sub), "full": len(ran) - len(sub)},
        "median_units_selected": _median([r["n_units"] for r in sub]),
        "subset_baseline": guard.as_dict(),
        "survivors": [{"id": r["id"], "line": r["line"], "op": r["op"],
                       "description": r["description"]}
                      for r in ran if r["status"] == "survived"],
    }


def _median(xs):
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0

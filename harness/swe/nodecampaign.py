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

import argparse
import json
import os
import shutil
import sys
import tempfile
import time

from . import coverage as CV
from . import linkcopy as LC
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
              timeout_s=180.0, ledger=LEDGER, full_cmd=None, on_result=None,
              linked=True, workdir=None):
    """Score as many unscored mutants as `budget_s` allows.

    Returns a report dict. `full_cmd` (default `base_cmd`) is what a mutant
    falls back to when its subset is poisoned or empty -- the full suite,
    which is always a sound oracle and is why a poisoned subset costs
    accuracy nothing, only time.

    `linked` (round 497, default ON) puts every sandbox on `swe.linkcopy`:
    ONE byte copy of the project, then a hardlink tree per mutant. Round 491
    measured the copy at 4.87 s of every 12.78 s mutant and named it as the
    next lever; measured here it is 2.4 s of copy + 0.6 s of rmtree against
    0.19 s of link + 0.06 s of rmtree.

    The master is checked for drift after EVERY mutant (0.1 s) and deeply,
    by content digest, at both ends of the slice (1.9 s). A suite that writes
    into the tree it runs in would reach through the links; that is reported
    as `master["n_drift_events"]`, the master is re-staged, and the mutants
    scored since the last clean check are named in the report rather than
    quietly kept. `linked=False` restores round 491's byte copy exactly.
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

    master, tmp_dir, own_wd = None, None, None
    if linked:
        own_wd = workdir or tempfile.mkdtemp(prefix="nodecampaign-")
        master = LC.MasterTree(root, workdir=own_wd, deep_witness=True)
        master.stage()
        tmp_dir = own_wd

    t0 = time.time()
    ran, out_of_budget, suspect = [], 0, []
    try:
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
            MU.run_mutant(m, root, cmd, timeout_s=timeout_s, copier=master,
                          tmp_dir=tmp_dir)
            rec = {"id": m.id, "path": m.path, "line": m.lineno, "op": m.op,
                   "description": m.description, "status": m.status,
                   "seconds": round(time.time() - t1, 2), "oracle": oracle,
                   "n_units": len(units), "subject_digest": digest,
                   "detail": m.detail[:400]}
            if master is not None and master.check(label=m.id):
                # The suite wrote through a link. This mutant's own verdict
                # was produced against a tree that is no longer the project,
                # so it is NAMED, not dropped and not silently kept.
                rec["master_drift"] = True
                suspect.append(m.id)
            append_ledger(ledger, rec)
            ran.append(rec)
            if on_result:
                on_result(rec)
    finally:
        if master is not None:
            master.check(label="after the last mutant", deep=True,
                         restage_on_drift=False)
            master.close()
            if workdir is None and own_wd:
                shutil.rmtree(own_wd, ignore_errors=True)

    rep = report(ran, mutants, todo, out_of_budget, guard, prio,
                 time.time() - t0)
    rep["linked"] = bool(linked)
    rep["master"] = master.as_dict() if master is not None else None
    rep["mutants_scored_against_a_drifted_master"] = suspect
    return rep


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


# --------------------------------------------------------------------------
# CLI (round 497)
#
# Round 491's next step #5: "`nodecampaign.py` has no CLI, unlike every other
# runner in `swe/`". A slice is a 10-40 minute job on this box and a round
# that can only start one from an inline `python3 -c` cannot background it,
# cannot re-run it with one flag changed, and cannot hand the exact command
# to the next round. Every default here is the one round 491 ran with.

#: The three regions of `nuc/perturbation.py` that carry published numbers:
#: `classify_bucket`, the hypergeometric/power block, and `verdict_floor`.
R491_RANGES = "556-634,1573-1662,2232-2301"


def parse_ranges(text):
    """`"556-634,1573-1662"` -> `[(556, 634), (1573, 1662)]`. A bare number
    is a one-line range. Empty/None means the whole file."""
    if not text:
        return None
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.append((int(lo), int(hi)))
        else:
            out.append((int(part), int(part)))
    return out or None


def build_parser():
    p = argparse.ArgumentParser(
        prog="python3 -m swe.nodecampaign",
        description="Budgeted, resumable nodeid-subset mutation campaign.")
    p.add_argument("--root", default=".", help="project root (default: cwd)")
    p.add_argument("--rel", default=os.path.join("nuc", "perturbation.py"),
                   help="subject file, relative to --root")
    p.add_argument("--cov", default=os.path.join("state", "swe",
                                                 "perturbation-cov-by-test.json"),
                   help="by-test coverage map (coverage.collect(by_test=True))")
    p.add_argument("--tests", default=os.path.join("nuc", "tests",
                                                   "test_perturbation.py"),
                   help="suite target; the last argument of the pytest command")
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--lines", default=R491_RANGES,
                   help="line ranges to scope the mutants to, or 'all'")
    p.add_argument("--budget", type=float, default=600.0,
                   help="wall-clock seconds for scoring mutants")
    p.add_argument("--timeout", type=float, default=180.0,
                   help="per-mutant cap")
    p.add_argument("--ledger", default=LEDGER)
    p.add_argument("--out", default=None, help="write the report JSON here")
    p.add_argument("--no-linked", dest="linked", action="store_false",
                   help="round 491's byte copy per mutant instead of "
                        "swe.linkcopy's hardlinked sandboxes")
    p.add_argument("--workdir", default=None,
                   help="where the master and the sandboxes live; must be on "
                        "the same filesystem or every link falls back to a copy")
    p.set_defaults(linked=True)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    root = os.path.abspath(a.root)
    base_cmd = [a.python, "-m", "pytest", "-x", "-q", a.tests]
    ranges = None if a.lines.strip().lower() == "all" else parse_ranges(a.lines)
    t0 = time.time()

    def echo(rec):
        print("  %-34s %-9s %6.2fs %s" % (rec["id"], rec["status"],
                                          rec["seconds"],
                                          "DRIFT" if rec.get("master_drift") else ""),
              flush=True)

    rep = run_slice(root, a.rel, os.path.join(root, a.cov), base_cmd,
                    line_ranges=ranges, budget_s=a.budget,
                    timeout_s=a.timeout, ledger=os.path.join(root, a.ledger),
                    on_result=echo, linked=a.linked, workdir=a.workdir)
    rep["argv"] = list(argv if argv is not None else sys.argv[1:])
    rep["wall_seconds"] = round(time.time() - t0, 1)
    text = json.dumps(rep, indent=1, sort_keys=True)
    if a.out:
        d = os.path.dirname(os.path.join(root, a.out))
        if d:
            os.makedirs(d, exist_ok=True)
        with open(os.path.join(root, a.out), "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":                     # pragma: no cover
    raise SystemExit(main())

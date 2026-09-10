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
from . import scopecall as SK
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


def _live_suite_hashes(root, base_cmd):
    """The same `{path: sha256}` shape `coverage._suite_hashes` records, for
    the suite this slice is actually about to run."""
    return CV._suite_hashes(root, [a for a in base_cmd[2:]])


def suite_digest(root, base_cmd):
    """Digest of the suite target `base_cmd` ends with, or None.

    ROUND 497 -- the resume key is `(mutant_id, subject_digest)` and the SUITE
    is not in it. That is not an oversight this round can fix by changing the
    key (that would re-run all 55 scored mutants), but it IS a real staleness:
    round 491 added six tests to `test_perturbation.py` AFTER its slice, and
    round 497 added six more, so every `survived` record in the ledger was
    graded by a suite that no longer exists. A survivor is exactly the verdict
    a stronger suite can overturn. So the digest is RECORDED per row and the
    report counts the rows scored under a different one, which makes the
    staleness visible instead of silent.
    """
    target = base_cmd[-1] if base_cmd else None
    if not target:
        return None
    path = target.split("::")[0]
    full = path if os.path.isabs(path) else os.path.join(root, path)
    if not os.path.isfile(full):
        return None
    return CV._file_hash(full)


#: Round 520: the three populations of `--stale`. "survivors" is round
#: 502's original and stays the default meaning of `--stale`.
STALE_SCOPES = ("survivors", "kills", "all")


def run_slice(root, rel, cov_path, base_cmd, line_ranges=None, budget_s=600.0,
              timeout_s=180.0, ledger=LEDGER, full_cmd=None, on_result=None,
              linked=True, workdir=None, only_ids=None, rescore=False,
              stale_survivors_only=False, stale_scope=None):
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

    # ROUND 502 -- FAIL CLOSED ON A STALE MAP.
    #
    # `require_fresh` above checks the SUBJECT's digest. The map is a map of
    # test NODEIDS, so a map collected before a test existed can never select
    # it -- and campaigns add tests precisely to kill the survivors they just
    # found. Round 502 re-scored 15 survivors against a 233-unit map while the
    # suite held 245 and got 0 killed, with the six tests round 491 wrote to
    # kill them sitting unselectable in the file.
    #
    # A subset the map cannot populate is not a cheaper oracle, it is a
    # WEAKER one, and it fails toward `survived`. So when the map does not
    # know the current suite, every mutant runs the full suite instead. That
    # is slow and sound; the alternative was fast and wrong.
    map_suite = dict((cov.get("_meta") or {}).get("suite_hashes") or {})
    live_suite = _live_suite_hashes(root, base_cmd)
    map_is_stale = (not map_suite) or map_suite != live_suite
    full_cmd = list(full_cmd or base_cmd)
    guard = NG.SubsetBaseline(root, base_cmd, timeout_s=timeout_s)

    mutants, digest = select_mutants(root, rel, line_ranges)
    suite = suite_digest(root, base_cmd)
    done = load_ledger(ledger)
    stale = [r for r in done.values()
             if r.get("suite_digest") not in (suite, None)
             or "suite_digest" not in r]
    stale_survivors = sorted(r["id"] for r in stale if r.get("status") == "survived")

    # ROUND 520 (NUC-integration E) -- THE NUMBER AND THE VERB DID NOT MATCH.
    #
    # `n_ledger_rows_scored_under_another_suite` below publishes len(stale).
    # The only verb that could ever pay it down is `--stale`, and `--stale`
    # selects `stale_survivors`. On `nuc/perturbation.py` at round 520 that is
    # 55 against 0: fifty-five verdicts produced by a suite that no longer
    # exists, and a repair verb that reaches none of them.
    #
    # The restriction to `survived` rests on a premise -- that a suite only
    # ever GROWS, so only a `survived` verdict can be overturned. Round 520
    # checked it on this subject's own history and it holds (239 -> 245 -> 257
    # nodeids across the three suite digests in the ledger, 0 removed). It is
    # a premise, not an invariant: `git rm` a test and every kill it produced
    # becomes a claim no suite in the tree supports. Nothing in this module
    # enforced it and nothing said out loud that the published number covered
    # rows the verb did not.
    #
    # So: the count is SPLIT BY STATUS, the kills are NAMED, and `stale_scope`
    # makes all three populations selectable. `stale_survivors_only=True` is
    # kept and means exactly what it meant.
    stale_ids = {
        "survivors": stale_survivors,
        "kills": sorted(r["id"] for r in stale if r.get("status") == "killed"),
        "all": sorted(r["id"] for r in stale),
    }
    stale_by_status = {}
    for r in stale:
        key = r.get("status") or "unknown"
        stale_by_status[key] = stale_by_status.get(key, 0) + 1
    if stale_survivors_only and stale_scope is None:
        stale_scope = "survivors"
    if stale_scope is not None and stale_scope not in STALE_SCOPES:
        raise ValueError("stale_scope must be one of %r, got %r"
                         % (STALE_SCOPES, stale_scope))

    # ROUND 502 -- the three selections, and why the last two exist.
    #
    # Round 497 recorded `suite_digest` per row and counted the rows scored
    # under another one, "which makes the staleness visible instead of
    # silent". It stayed visible for five rounds. A SURVIVED verdict is
    # exactly the one a stronger suite overturns, and round 491 added six
    # tests immediately AFTER its own slice specifically to kill eight of its
    # own survivors -- so the ledger has been over-reporting survivors, in
    # the direction that looks like bad news, ever since. Nothing could
    # re-score them, because the resume key made every scored mutant
    # permanently skipped.
    #
    # `--stale` is the payment: score exactly the survivors whose grading
    # suite no longer exists. `--only`/`--rescore` is the general form.
    # Neither edits the ledger: `load_ledger` is LAST-WINS, so a re-score is
    # an append and the file keeps its own history.
    if stale_scope is not None:
        want = set(stale_ids[stale_scope])
        todo = [m for m in mutants if m.id in want]
        selection = "stale-%s" % stale_scope
    elif only_ids:
        want = set(only_ids)
        todo = [m for m in mutants
                if m.id in want and (rescore or (m.id, digest) not in done)]
        selection = "only%s" % ("-rescore" if rescore else "")
    else:
        todo = [m for m in mutants if (m.id, digest) not in done]
        selection = "unscored"

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
            if map_is_stale:
                units, basis = [], "stale-map"
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
                   "suite_digest": suite, "detail": m.detail[:400]}
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
                 time.time() - t0, done=done, digest=digest)
    rep["linked"] = bool(linked)
    rep["selection"] = selection
    rep["map_is_stale"] = bool(map_is_stale)
    rep["map_suite_hashes"] = map_suite
    rep["live_suite_hashes"] = live_suite
    if map_is_stale:
        rep["stale_map_note"] = (
            "the coverage map does not know this suite, so every mutant ran "
            "the FULL suite: a subset the map cannot populate fails toward "
            "`survived`. Re-collect with coverage.collect(by_test=True).")
    rep["n_selected"] = len(todo)
    if selection != "unscored":
        # ROUND 520 -- A FIRST SCORING IS NOT A CHANGE.
        #
        # Round 502 added this field as "the number the round quotes ...
        # without it a re-score is a silent correction and nobody can tell how
        # wrong the old figure was". It compared against
        # `done.get((id, digest))`, which is absent for any id NOT yet scored
        # at this subject digest -- and `--only` is exactly how a round scores
        # ids for the first time. Round 520 re-scored 82 mutants that round
        # 514 had remapped onto a new digest: every one came back `killed`,
        # not one verdict moved, and the field reported 82 changes, all of
        # them `was: null -> now: killed`. A "corrections" count that is 82 of
        # 82 when the true answer is 0 of 82 is worse than no count.
        #
        # So a change needs a PRIOR verdict at this digest. The first scorings
        # are counted separately, because dropping them silently would hide
        # that the slice was mostly new work.
        prior = [(r, done.get((r["id"], digest), {}).get("status")) for r in ran]
        rep["verdict_changes"] = [
            {"id": r["id"], "was": was, "now": r["status"]}
            for r, was in prior if was is not None and was != r["status"]]
        rep["n_first_scored_at_this_digest"] = sum(
            1 for _, was in prior if was is None)
    # ROUND 503 -- NO POOLED RATE WITHOUT ITS STRATA.
    #
    # A kill rate over a scope that mixes code the product reaches with code
    # only the tests reach is not one measurement, it is two averaged. The
    # `test_only` half is graded by tests written directly against it and by
    # nothing else, which is the easiest grading problem there is: on this
    # subject it scores 21 of 21 against 61 of 66 for the live half, and
    # pooling it in moves the headline UP. Cheap (pure `ast`, no subprocess),
    # so it runs unconditionally rather than behind a flag nobody sets.
    try:
        scope_rep = SK.audit(root, rel, line_ranges=line_ranges)
        rep["scope_strata"] = SK.stratify(
            scope_rep, list(load_ledger(ledger).values()),
            subject_digest=digest)
        rep["scope_verdicts"] = dict(
            (r["qualname"], r["verdict"]) for r in scope_rep["defs"]
            if r["in_scope"])
        rep["scope_not_live"] = scope_rep["scoped_not_live"]
    except SK.ScopeError as exc:
        rep["scope_strata"] = None
        rep["scope_error"] = "%s: %s" % (type(exc).__name__, exc)

    rep["suite_digest"] = suite
    rep["n_ledger_rows_scored_under_another_suite"] = len(stale)
    rep["survivors_scored_under_another_suite"] = stale_survivors
    # ROUND 520: the same number, split by the status the repair verb keys on,
    # plus the ids the verb has never been able to reach.
    rep["stale_by_status"] = stale_by_status
    rep["kills_scored_under_another_suite"] = stale_ids["kills"]
    # And the second half of round 514's finding, made a field: a stale row is
    # keyed at the subject digest it was scored at, so an id that MOVED is not
    # a mutant of this subject at all and no `stale_scope` can select it. This
    # says how many of the stale rows the verb could reach even in principle.
    live_ids = set(m.id for m in mutants)
    rep["n_stale_rows_selectable_at_this_digest"] = sum(
        1 for i in stale_ids["all"] if i in live_ids)
    rep["master"] = master.as_dict() if master is not None else None
    rep["mutants_scored_against_a_drifted_master"] = suspect
    return rep


def report(ran, mutants, todo, out_of_budget, guard, prio, seconds,
           done=None, digest=None):
    # ROUND 526 -- `done` and `digest` are what make `n_already_scored`
    # a question about the LEDGER rather than about the selection. They
    # are optional so an existing caller keeps working, and when they are
    # absent the field is reported as None rather than as a number that
    # would be measuring the wrong thing.
    by_status = {}
    for r in ran:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    killed = by_status.get("killed", 0)
    survived = by_status.get("survived", 0)
    scorable = killed + survived
    sub = [r for r in ran if r["oracle"] == "subset"]
    return {
        "n_sites_in_scope": len(mutants),
        # ROUND 526 (NUC-integration E) -- THE FIELD SAID "SCORED" AND MEANT
        # "NOT SELECTED", AND THE TWO COINCIDE UNDER EXACTLY ONE SELECTION.
        #
        # `len(mutants) - len(todo)` is the number this slice did not pick.
        # Under the default `unscored` selection that IS the already-scored
        # count, which is why it went eighteen rounds unnoticed: round 491
        # published 0 and round 497 published 55, both correct. Under `--only`
        # and `--stale-scope` it is the size of the file minus the size of the
        # hand-written id list, and nothing else.
        #
        # Rounds 514, 520 and 526 all ran `--only` on `nuc/perturbation.py`
        # and published `n_already_scored` 1841, 1764 and 1841 against
        # `n_sites_in_scope` 1846 -- i.e. "99.7 % of this file is
        # mutation-tested". The ledger has 87 distinct ids at that digest.
        # The true figure is 4.7 %, and this repo's own carried debt says so
        # in `state/research-state.md` ("96.9 % un-mutation-tested, 55 of
        # 1794 sites"). Two numbers, twenty-fold apart, neither wrong on its
        # own terms, and no reader could see which question each answered.
        #
        # So: the name now means what it says, ASKED OF THE LEDGER; the old
        # arithmetic keeps its own name; and the complement is published so a
        # reader never has to subtract to find the debt.
        "n_already_scored": (None if done is None else
                             sum(1 for m in mutants
                                 if (m.id, digest) in done)),
        "n_not_selected_this_slice": len(mutants) - len(todo),
        "n_unscored_at_this_digest": (None if done is None else
                                      sum(1 for m in mutants
                                          if (m.id, digest) not in done)),
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

#: The three regions of `nuc/perturbation.py` round 491 scoped, and what they
#: turned out to be. The sentence that stood here until round 503 --
#: "the three regions that carry published numbers: `classify_bucket`, the
#: hypergeometric/power block, and `verdict_floor`" -- was FALSE in its first
#: third and stayed false for 12 rounds.
#:
#: Round 502 established by hand that `classify_bucket` (556-596) has never
#: had a caller outside `nuc/tests/test_perturbation.py`; round 503 made that
#: a runnable verdict (`swe/scopecall.py`) and found the comment above was
#: itself the ONLY non-test mention of the function in the whole repo. The
#: claim was vouching for itself.
#:
#: The range is deliberately NOT narrowed. Those mutants are real test gaps
#: and closing them is worth doing -- 21 of 21 are killed today. What changed
#: is that every report now carries `scope_strata`, so the kill rate says
#: which part of it is a fact about the subject and which part is the suite
#: agreeing with itself. Re-derive, do not copy:
#:   python3 -m swe.scopecall audit --rel nuc/perturbation.py \
#:       --ranges 556-634,1573-1662,2232-2301
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
    p.add_argument("--only", default=None,
                   help="comma-separated mutant ids to score instead of every "
                        "unscored one")
    p.add_argument("--rescore", action="store_true",
                   help="with --only: score them even though the ledger "
                        "already has a row (the ledger is last-wins, so this "
                        "appends rather than edits)")
    p.add_argument("--stale", action="store_true",
                   help="score exactly the SURVIVORS whose `suite_digest` is "
                        "not the current suite's -- the verdicts a suite that "
                        "no longer exists produced (round 497's finding). "
                        "Shorthand for --stale-scope survivors")
    p.add_argument("--stale-scope", dest="stale_scope", default=None,
                   choices=list(STALE_SCOPES),
                   help="round 520: which stale-verdict population to score. "
                        "`survivors` is --stale; `kills` is the population "
                        "n_ledger_rows_scored_under_another_suite counted and "
                        "no verb could reach; `all` is both")
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

    only = [x.strip() for x in a.only.split(",")] if a.only else None
    rep = run_slice(root, a.rel, os.path.join(root, a.cov), base_cmd,
                    line_ranges=ranges, budget_s=a.budget,
                    timeout_s=a.timeout, ledger=os.path.join(root, a.ledger),
                    on_result=echo, linked=a.linked, workdir=a.workdir,
                    only_ids=only, rescore=a.rescore,
                    stale_survivors_only=a.stale,
                    stale_scope=a.stale_scope)
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

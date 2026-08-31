"""Exemption map for the whole oracle suite (round 383, SWE-loop D).

Round 377 audited ONE exemption — the guest differential's depth scrub — and
produced the rule now written down as `skills/zero-rate-needs-a-distance`: a
count of zero is a fact about the corpus until you measure the DISTANCE from
what the corpus demands to the threshold that would produce the class. Its
own next-step item 3 asked for the same audit over the rest of the suite.

This module is that audit. It differs from `exemptaudit.py` in one way that
turned out to matter more than the extra oracles:

    A THRESHOLD site has a distance. A PREDICATE site has a SURFACE.

`FRAME_SLACK = 140` and `names[:6]` are thresholds: the corpus demands a
number, the code compares it against a constant, and the gap between them is
the measurement. But `provenance_tainted_names` and `erasure_exemption` are
predicates — there is no number to be far from. Their honest analogue is how
much of the comparison SURFACE they remove when they fire: an exemption that
fires on 60 % of programs but drops one field of forty is not the same
instrument as one that fires on 3 % and drops everything. Reporting a fire
rate alone is wrong for both kinds, for two different reasons.

So every site in `SITES` declares `metric="distance"` or `metric="surface"`,
and `summarize` reports the matching number. `report` prints both columns and
refuses to print a distance for a surface site.

The registry is SELF-VERIFYING. Each site names an anchor — a literal
substring of `oracles.py` — and the exact number of times it must occur.
`verify_sites()` raises if any anchor has drifted, on the same rule
`exemptaudit.patch_lib_source` uses: a stale registry that silently measures
the wrong line would report numbers that look like results. Three of the
anchors here (`tainted = provenance_tainted_names(program)` and friends)
legitimately occur twice, once per oracle, which is why the check is on the
COUNT and not on uniqueness.

usage:
  python3 -m harness.swe.exemptmap sites
  python3 -m harness.swe.exemptmap sweep  [N] [--out P] [--budget-s S]
                                          [--stress R] [--start K]
  python3 -m harness.swe.exemptmap report [--out P]
  python3 -m harness.swe.exemptmap chainladder [--max N]
  python3 -m harness.swe.exemptmap paircap [--bindings K]
  python3 -m harness.swe.exemptmap witnesses
"""

import json
import os
import signal
import sys
import time

from . import oracles as O
from .fuzz import ProgramGen, WHENCE_ROOT
from .killers import load_whence

_ORACLES_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "oracles.py")


class Site(object):
    """One exemption / cap / no-op branch in the oracle suite.

    `anchor` is the literal source text the site keys on and `anchor_n` how
    many times it must appear in `oracles.py`. `metric` is "distance" for a
    site with a numeric threshold the corpus can approach, "surface" for a
    predicate whose cost is how much of the comparison it removes, and
    "rate" for a no-op branch where neither applies (the transform simply
    has nothing to do).
    """

    __slots__ = ("id", "oracle", "what", "kind", "metric", "threshold",
                 "polarity", "anchor", "anchor_n", "note")

    def __init__(self, id, oracle, what, kind, metric, threshold, anchor,
                 anchor_n=1, note="", polarity="suppress"):
        self.id, self.oracle, self.what = id, oracle, what
        self.kind, self.metric, self.threshold = kind, metric, threshold
        self.polarity = polarity
        self.anchor, self.anchor_n, self.note = anchor, anchor_n, note

    def as_dict(self):
        return {"id": self.id, "oracle": self.oracle, "what": self.what,
                "kind": self.kind, "metric": self.metric,
                "threshold": self.threshold, "polarity": self.polarity,
                "anchor_n": self.anchor_n, "note": self.note}


SITES = (
    Site("R-CAP", "render", "diverge-symmetry checked on the first 6 bindings only",
         "silent cap", "distance", 6,
         "    for i, x in enumerate(names[:6]):", 1,
         "the loop bound is a literal in the oracle; nothing reports what it "
         "skipped"),
    Site("F-SLACK", "frames", "host-frame excess over the charge must stay under FRAME_SLACK",
         "threshold", "distance", O.FRAME_SLACK,
         "FRAME_SLACK = 140", 1,
         "detail always carries the measured excess (round 110's convention)",
         polarity="tolerate"),
    Site("T-SPACE", "tail_transparency", "lifted run reached max_depth: space-exempt",
         "threshold", "distance", 500,
         "    if peak >= max_depth:", 1,
         "threshold is the caller's max_depth, not a module constant"),
    Site("T-TAINT", "tail_transparency", "provenance-tainted bindings dropped from the comparison",
         "predicate", "surface", None,
         "    scope = \"all fields\" if whole else \"untainted vals only (%d tainted)\" % len(tainted)", 1,
         "when `whole` is False, `out` and `checks` are dropped WHOLESALE"),
    Site("T-NONE", "tail_transparency", "program has no tail calls: transform is a no-op",
         "no-op", "rate", None,
         "        return OracleOutcome(\"ok\", TAIL_ORACLE, \"no tail calls\")", 1,
         "not an exemption; a program the oracle has no opinion about"),
    # The bare `if not a["vals"] and not whole:` occurs TWICE — once here and
    # once inside `oracle_param_erasure`, at a deeper indent, so the 4-space
    # form is a substring of the 8-space one. The first `verify_sites()` run
    # of this module caught exactly that. Anchoring on the two-line form ties
    # the site to the tail oracle's branch and not to a shape shared with
    # another oracle.
    Site("T-ALL", "tail_transparency", "every binding tainted: nothing left to compare",
         "predicate", "surface", None,
         "if not a[\"vals\"] and not whole:\n"
         "        return OracleOutcome(\"ok\", TAIL_ORACLE,", 1,
         "the extreme of T-TAINT, reported separately by the oracle; "
         "param_erasure has the same branch, measured as part of T-TAINT's twin"),
    Site("P-EXEMPT", "param_erasure", "spec-name multiplicity or a bound `typed`",
         "predicate", "distance", 2,
         "def erasure_exemption(program):", 1,
         "predicate, but its first clause IS a threshold: multiplicity >= 2"),
    Site("P-NONE", "param_erasure", "program has no parameter contracts: transform is a no-op",
         "no-op", "rate", None,
         "        return OracleOutcome(\"ok\", PARAM_ORACLE, \"no parameter contracts\")", 1,
         "not an exemption; the v0.19 feature simply is not used"),
)

SITE_IDS = tuple(s.id for s in SITES)


def verify_sites(path=_ORACLES_PY):
    """Every site's anchor still occurs exactly `anchor_n` times.

    Raises `ValueError` naming every drifted anchor. This is the registry's
    only defence against measuring a line that has moved out from under it:
    a site whose anchor is gone would keep reporting a rate computed by a
    helper that no longer matches the oracle's own branch.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    bad = []
    for s in SITES:
        got = text.count(s.anchor)
        if got != s.anchor_n:
            bad.append("%s: anchor %r occurs %d time(s), expected %d"
                       % (s.id, s.anchor[:60], got, s.anchor_n))
    if bad:
        raise ValueError("exemptmap registry is stale:\n  " + "\n  ".join(bad))
    return len(SITES)


def site(sid):
    for s in SITES:
        if s.id == sid:
            return s
    raise KeyError(sid)


# ------------------------------------------------------------- measurement --
#
# `measure` runs the program up to five times (direct, profiled, original,
# lifted, and the erasure predicates). None of those is bounded by anything
# but the interpreter's own `max_depth`, which does NOT bound a tail loop —
# `DEFAULT_MAX_ITER` is 1000000 and one runaway seed cost the pilot 10.95 s
# of its 30.1 s. Every entry point below therefore runs under the same
# SIGALRM guard `run_oracle` uses, so a hang degrades to a recorded row and
# not to a lost sweep.


class _Timeout(Exception):
    pass


def _alarm(_sig, _frm):
    raise _Timeout()


def guarded(fn, timeout_s):
    """`(value, error_str, seconds)`; `error_str` is "" on success."""
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    t0 = time.time()
    try:
        return fn(), "", time.time() - t0
    except _Timeout:
        return None, "timeout", time.time() - t0
    except BaseException as e:      # noqa: BLE001 — the audit records, never raises
        return None, type(e).__name__, time.time() - t0
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def _nc2(k):
    return k * (k - 1) // 2


def measure(pkg, src, max_depth=500):
    """Every site's fire flag, demand and surface for one program.

    Deliberately re-uses the ORACLE's own predicates (`clear_tail_flags`,
    `provenance_tainted_names`, `erasure_exemption`, `frame_excess`) rather
    than reimplementing them, so a semantic change in the oracle moves this
    measurement with it. What it cannot track is a change in the BRANCH
    STRUCTURE around those predicates — that is what `verify_sites` is for.
    """
    row = {"parse_error": "", "sites": {}}
    try:
        program = O._parse(pkg, src)
    except (pkg["LexError"], pkg["ParseError"]) as e:
        row["parse_error"] = type(e).__name__
        return row
    s = row["sites"]

    # Each measurement below that RUNS the program gets its own fresh AST.
    # `frame_excess` is not a pure function of the source: direct mode caches
    # compiled fast-path closures ON the AST nodes, so measuring an AST that
    # has already been executed skips the compilation frames and reports a
    # LOWER excess than the oracle does. The first version of this function
    # reused one AST and disagreed with `oracle_frames` (8 vs 11 on seed 7);
    # `test_measure_agrees_with_the_oracle_it_describes` is what caught it,
    # and is the reason the cross-check exists at all.
    #
    # `program` itself is only ever used for STATIC predicates
    # (`provenance_tainted_names`, `binding_counts`, `erasure_exemption`),
    # which read the AST and never execute it.

    # ---- render: the pair cap -------------------------------------------
    interp, env, _out = O._run_ast(pkg, O._parse(pkg, src), max_depth=max_depth)
    names = list(env.vars)
    k = len(names)
    cap = 6
    checked = _nc2(min(k, cap))
    total = _nc2(k)
    s["R-CAP"] = {
        "fired": k > cap,
        "demand": k,                       # bindings the program produced
        "threshold": cap,
        "pairs_total": total,
        "pairs_checked": checked,
        "pairs_skipped": total - checked,
        "surface": (checked / total) if total else 1.0,
    }
    row["bindings"] = k
    row["peak_depth_direct"] = interp.peak_depth

    # ---- frames: the slack ----------------------------------------------
    if O.has_direct_mode(pkg):
        best, at, _i = O.frame_excess(pkg, O._parse(pkg, src),
                                      max_depth=max_depth)
        s["F-SLACK"] = {"fired": best > O.FRAME_SLACK, "demand": best,
                        "threshold": O.FRAME_SLACK, "at_guest_depth": at,
                        # polarity="tolerate": firing PRODUCES a verdict, so
                        # nothing is suppressed and the surface is intact.
                        "surface": 1.0}
    else:
        s["F-SLACK"] = {"fired": False, "demand": None, "surface": 1.0,
                        "threshold": O.FRAME_SLACK, "skipped": "no direct mode"}

    # ---- tail_transparency ----------------------------------------------
    lifted = O._parse(pkg, src)
    n_tail = O.clear_tail_flags(lifted)
    tainted = O.provenance_tainted_names(program)
    whole = not O.reflects_on_provenance(program)
    # T-NONE suppresses nothing that EXISTS: with no tail calls the lifted
    # program is the original, so there was no comparison to lose. Surface 1.0
    # is the honest value, and is why its metric is "rate".
    s["T-NONE"] = {"fired": n_tail == 0, "demand": n_tail, "threshold": None,
                   "surface": 1.0}

    a, _peak_a = O._answer(pkg, O._parse(pkg, src), tainted, whole,
                           max_depth=max_depth)
    # The oracle compares `vals` (untainted only) and, when `whole`, also
    # `out` and `checks`. Surface = fields kept / fields the program has.
    all_vals = len(env.vars)
    kept_vals = len(a["vals"])
    fields_total = all_vals + 2                # + out + checks
    fields_kept = kept_vals + (2 if whole else 0)
    s["T-TAINT"] = {
        "fired": bool(tainted) or not whole,
        "demand": len(tainted),
        "threshold": None,
        "tainted": len(tainted),
        "whole": whole,
        "vals_total": all_vals,
        "vals_kept": kept_vals,
        "surface": (fields_kept / fields_total) if fields_total else 1.0,
    }
    s["T-ALL"] = {"fired": (not a["vals"]) and (not whole),
                  "demand": kept_vals, "threshold": 0, "surface": 0.0}

    if n_tail:
        try:
            _b, peak = O._answer(pkg, lifted, tainted, whole, max_depth=max_depth)
            fired = peak >= max_depth
            s["T-SPACE"] = {
                "fired": fired, "demand": peak, "threshold": max_depth,
                # The demand is RIGHT-CENSORED: the interpreter stops at
                # max_depth, so `peak == max_depth` means "at least 500", not
                # "500". `depth_ladder` is what un-censors it, and until it
                # runs, any distance computed from this number is a floor.
                "censored": fired,
                # A fired T-SPACE returns `ok` without comparing anything.
                "surface": 0.0 if fired else 1.0}
        except RecursionError:
            s["T-SPACE"] = {"fired": True, "demand": None, "censored": True,
                            "surface": 0.0,
                            "threshold": max_depth, "note": "RecursionError"}
    else:
        s["T-SPACE"] = {"fired": False, "demand": 0, "threshold": max_depth,
                        "censored": False, "surface": 1.0,
                        "note": "no lifted run (T-NONE)"}

    # ---- param_erasure ---------------------------------------------------
    # NOTE: `program` has never been executed, so `param_types` is still on
    # the nodes. (`erase_param_contracts` clears it; nothing here calls it.)
    contracts = sum(len(getattr(nd, "param_types", None) or ())
                    for nd in O.iter_ast_nodes(program))
    s["P-NONE"] = {"fired": contracts == 0, "demand": contracts,
                   "threshold": None, "surface": 1.0}
    counts = O.binding_counts(program)
    spec_names = O.param_spec_names(program)
    mult = max([counts.get(nm, 0) for nm in spec_names] or [0])
    reason = O.erasure_exemption(program)
    s["P-EXEMPT"] = {
        "fired": bool(reason) and contracts > 0,
        "demand": mult,                    # max spec-name binding multiplicity
        "threshold": 2,
        "reason": reason[:60],
        "binds_typed": counts.get(O.GUARD_BUILTIN, 0),
        "spec_names": len(spec_names),
        # When P-EXEMPT fires the oracle still RUNS both forms and reports
        # "exempt, used"/"exempt, unused" (round 359's convention) — but the
        # VERDICT is unconditionally `ok`, so the comparison surface that can
        # produce a finding is zero.
        "surface": 0.0 if (reason and contracts) else 1.0,
    }
    return row


# ------------------------------------------------------------------ sweep --

def sweep_record(pkg, seed, stress_rate=0.5, max_depth=500, timeout_s=3.0,
                 with_oracles=True):
    """One seed: the site measurements plus (optionally) every oracle's real
    verdict, so the measurement can be cross-checked against the instrument
    it claims to describe."""
    src = ProgramGen(seed, stress_rate=stress_rate).program()
    row, err, secs = guarded(
        lambda: measure(pkg, src, max_depth=max_depth), timeout_s * 4)
    if err:
        row = {"sites": {}, "parse_error": "", "measure_error": err}
    row["seed"] = seed
    row["measure_s"] = round(secs, 4)
    row["src_lines"] = src.count("\n") + 1
    if with_oracles:
        vs = {}
        for name in O.ORACLE_NAMES:
            o = O.run_oracle(name, pkg, src, timeout_s=timeout_s,
                             max_depth=max_depth)
            vs[name] = {"kind": o.kind, "s": round(o.seconds, 4),
                        "detail": (o.detail or "")[:160]}
        row["oracles"] = vs
    return row


def done_seeds(path):
    if not os.path.exists(path):
        return set()
    seen = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                seen.add(json.loads(line)["seed"])
            except (ValueError, KeyError):
                continue        # truncated by a kill: simply not done
    return seen


def sweep(n=500, out=None, stress_rate=0.5, max_depth=500, timeout_s=3.0,
          budget_s=None, start=0, root=WHENCE_ROOT, with_oracles=True,
          echo=True):
    """Seeds `start .. start+n-1`, one flushed JSONL row each, resumable."""
    verify_sites()
    out = out or default_out("sweep")
    pkg = dict(load_whence(root, "r383map"))
    pkg.setdefault("root", root)
    skip = done_seeds(out)
    rows, t0 = [], time.time()
    with open(out, "a", encoding="utf-8") as f:
        for seed in range(start, start + n):
            if seed in skip:
                continue
            if budget_s is not None and time.time() - t0 > budget_s:
                if echo:
                    print("budget %.0fs reached after %d seed(s)"
                          % (budget_s, len(rows)))
                break
            try:
                row = sweep_record(pkg, seed, stress_rate=stress_rate,
                                   max_depth=max_depth, timeout_s=timeout_s,
                                   with_oracles=with_oracles)
            except BaseException as e:      # noqa: BLE001 — record, never raise
                row = {"seed": seed, "error": type(e).__name__,
                       "sites": {}, "parse_error": ""}
            f.write(json.dumps(row, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
            rows.append(row)
            if echo and seed % 100 == 0:
                print("  seed %d (%.1fs elapsed)" % (seed, time.time() - t0))
    if echo:
        print("%d new row(s) in %.1fs -> %s" % (len(rows), time.time() - t0, out))
    return rows


def read_rows(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


# --------------------------------------------------------------- summary --

def _pct(sorted_vals, q):
    if not sorted_vals:
        return None
    return sorted_vals[int(q * (len(sorted_vals) - 1))]


def _hist(items):
    h = {}
    for it in items:
        h[it] = h.get(it, 0) + 1
    return dict(sorted(h.items(), key=lambda kv: -kv[1]))


def summarize(rows):
    """Per-site fire rate plus the number its `metric` calls for.

    A site with `metric="distance"` gets `demand_max` / `threshold` /
    `distance_ratio` and `at_boundary` (how many programs already sit AT or
    past the threshold). A site with `metric="surface"` gets the mean and
    minimum fraction of the comparison surface that survives when it fires.
    A `metric="rate"` site gets the rate only, and says so.
    """
    usable = [r for r in rows if r.get("sites") and not r.get("parse_error")]
    parse_errs = len([r for r in rows if r.get("parse_error")])
    errs = len([r for r in rows
                if r.get("error") or r.get("measure_error")])
    out = {"rows": len(rows), "usable": len(usable),
           "parse_errors": parse_errs, "errors": errs,
           "measure_errors": _hist([r["measure_error"] for r in rows
                                    if r.get("measure_error")]),
           "sites": {}}
    for s in SITES:
        vals = [r["sites"].get(s.id) for r in usable if s.id in r["sites"]]
        vals = [v for v in vals if v]
        n = len(vals)
        fired = [v for v in vals if v.get("fired")]
        ent = {"metric": s.metric, "kind": s.kind, "oracle": s.oracle,
               "n": n, "fired": len(fired),
               "fire_rate": (len(fired) / n) if n else 0.0}
        demands = sorted(v["demand"] for v in vals if v.get("demand") is not None)
        if demands:
            ent["demand_max"] = demands[-1]
            ent["demand_p50"] = _pct(demands, 0.5)
            ent["demand_p99"] = _pct(demands, 0.99)
        if s.metric == "distance" and s.threshold:
            thr = s.threshold
            ent["threshold"] = thr
            if demands:
                ent["distance_ratio"] = demands[-1] / thr
                ent["at_boundary"] = len([d for d in demands if d >= thr])
                ent["one_step_away"] = len([d for d in demands if d == thr - 1])
        if s.metric == "distance" and demands:
            ent["censored"] = len([v for v in vals if v.get("censored")])
        # Surface is measured for EVERY site, not only the predicate ones:
        # the fire rate and the cost per firing are independent numbers and a
        # site is only understood when both are on the table. `polarity`
        # says which direction "fired" points.
        ent["polarity"] = s.polarity
        surf = sorted(v["surface"] for v in vals if v.get("surface") is not None)
        fsurf = sorted(v["surface"] for v in fired
                       if v.get("surface") is not None)
        if surf:
            ent["surface_mean_all"] = sum(surf) / len(surf)
        if fsurf:
            ent["surface_mean_when_fired"] = sum(fsurf) / len(fsurf)
            ent["surface_min_when_fired"] = fsurf[0]
            ent["surface_zero_when_fired"] = len([x for x in fsurf if x == 0.0])
        out["sites"][s.id] = ent

    # cross-cutting: the render cap's real cost, in pairs not programs
    tot = sum(r["sites"]["R-CAP"]["pairs_total"] for r in usable
              if "R-CAP" in r["sites"])
    chk = sum(r["sites"]["R-CAP"]["pairs_checked"] for r in usable
              if "R-CAP" in r["sites"])
    out["render_pairs"] = {"total": tot, "checked": chk,
                           "skipped": tot - chk,
                           "checked_fraction": (chk / tot) if tot else 1.0}
    # oracle verdict + cost distribution, when the sweep recorded them
    ors = {}
    for r in usable + [r for r in rows if r.get("parse_error")]:
        for name, v in (r.get("oracles") or {}).items():
            e = ors.setdefault(name, {"kinds": {}, "secs": []})
            e["kinds"][v["kind"]] = e["kinds"].get(v["kind"], 0) + 1
            e["secs"].append(v["s"])
    for name, e in ors.items():
        e["secs"].sort()
        e["median_s"] = _pct(e["secs"], 0.5)
        e["max_s"] = e["secs"][-1] if e["secs"] else None
        e["total_s"] = round(sum(e["secs"]), 2)
        del e["secs"]
    out["oracles"] = ors
    return out


def report(s):
    lines = []
    lines.append("rows %d  usable %d  parse_errors %d  errors %d"
                 % (s["rows"], s["usable"], s["parse_errors"], s["errors"]))
    lines.append("")
    lines.append("%-9s %-18s %-10s %7s %7s  %s"
                 % ("site", "oracle", "polarity", "fire%", "cost%",
                    "distance (demand vs threshold)"))
    for sid in SITE_IDS:
        e = s["sites"].get(sid)
        if not e:
            continue
        if "surface_mean_when_fired" in e:
            cost = "%6.1f%%" % (100 * (1 - e["surface_mean_when_fired"]))
        else:
            cost = "      -"
        if e["metric"] == "distance" and "distance_ratio" in e:
            num = ("max %s%s of %s = %.0f%%  (at_boundary %d, one_away %d)"
                   % (e["demand_max"], "+" if e.get("censored") else "",
                      e["threshold"], 100 * e["distance_ratio"],
                      e["at_boundary"], e["one_step_away"]))
            if e.get("censored"):
                num += "  [%d CENSORED: demand is a floor]" % e["censored"]
        elif e["metric"] == "surface":
            num = "predicate: no threshold to be far from"
        else:
            num = "no-op branch: nothing suppressed"
        lines.append("%-9s %-18s %-10s %6.1f%% %7s  %s"
                     % (sid, e["oracle"], e["polarity"],
                        100 * e["fire_rate"], cost, num))
    rp = s["render_pairs"]
    lines.append("")
    lines.append("render diverge-symmetry pairs: %d checked of %d (%.1f%%), "
                 "%d skipped by the names[:6] cap"
                 % (rp["checked"], rp["total"], 100 * rp["checked_fraction"],
                    rp["skipped"]))
    if s.get("oracles"):
        lines.append("")
        lines.append("%-18s %-40s %8s %8s" % ("oracle", "kinds", "median_s", "max_s"))
        for name in O.ORACLE_NAMES:
            e = s["oracles"].get(name)
            if not e:
                continue
            lines.append("%-18s %-40s %8.4f %8.4f"
                         % (name, json.dumps(e["kinds"], sort_keys=True),
                            e["median_s"] or 0.0, e["max_s"] or 0.0))
    return "\n".join(lines)


# --------------------------------------------------- constructed witnesses --
#
# Step 5 of `zero-rate-needs-a-distance`: for every site the corpus does not
# reach, build one input that DOES, and push it through the real instrument.
# If the site still does not fire, the zero was measuring the detector.

#: ascending guest-depth ceilings for `depth_ladder`. 500 is the campaign's
#: real `max_depth`, so the bottom rung reproduces production behaviour and
#: every higher rung asks "how much would this seed have needed?".
DEPTH_RUNGS = (500, 1000, 2000, 5000, 10000, 25000)


def depth_demand(pkg, src, rungs=DEPTH_RUNGS, timeout_s=20.0):
    """A seed's real T-SPACE demand, by raising the ceiling until the lifted
    run stops hitting it.

    `measure` reports `peak == max_depth`, which is RIGHT-CENSORED: the
    interpreter refuses at the ceiling, so the number is a floor and the
    "distance" computed from it is exactly 100 % by construction. This walks
    UP instead of down (round 377's ladder walked down, because there the
    corpus sat far below the ceiling and the question was how far). The
    bracket is `(rung_below, rung]` for the first rung the run completes
    under; `unbounded` if the top rung still censors.
    """
    t0 = time.time()
    try:
        program = O._parse(pkg, src)
        lifted = O._parse(pkg, src)
    except (pkg["LexError"], pkg["ParseError"]) as e:
        return {"demand": "parse_error", "note": type(e).__name__,
                "s": round(time.time() - t0, 3)}
    n_tail = O.clear_tail_flags(lifted)
    if n_tail == 0:
        return {"demand": "no_tail_calls", "lo": 0, "hi": 0, "note": "T-NONE",
                "s": round(time.time() - t0, 3)}
    tainted = O.provenance_tainted_names(program)
    whole = not O.reflects_on_provenance(program)
    prev = 0
    for rung in rungs:
        res, err, _s = guarded(
            lambda r=rung: O._answer(pkg, lifted, tainted, whole, max_depth=r),
            timeout_s)
        if err:
            return {"demand": "error", "note": "%s at ceiling %d" % (err, rung),
                    "lo": prev, "hi": None, "rung": rung,
                    "s": round(time.time() - t0, 3)}
        _b, peak = res
        if peak < rung:
            return {"demand": "(%d, %d]" % (prev, rung), "lo": prev, "hi": rung,
                    "peak": peak, "note": "bounded",
                    "s": round(time.time() - t0, 3)}
        prev = rung
    return {"demand": "unbounded", "lo": rungs[-1], "hi": None,
            "note": "still censored at %d" % rungs[-1],
            "s": round(time.time() - t0, 3)}


def depth_ladder(seeds, out=None, stress_rate=0.5, root=WHENCE_ROOT,
                 timeout_s=20.0, budget_s=None, echo=True):
    """`depth_demand` over an explicit seed list, flushed per row, resumable.

    Fed the seeds the sweep recorded as censored — running it over the whole
    corpus would spend ~99 % of its time re-deriving `peak < 500` for seeds
    the sweep already bounded exactly.
    """
    out = out or default_out("depth")
    pkg = dict(load_whence(root, "r383depth"))
    pkg.setdefault("root", root)
    skip = done_seeds(out)
    rows, t0 = [], time.time()
    with open(out, "a", encoding="utf-8") as f:
        for seed in seeds:
            if seed in skip:
                continue
            if budget_s is not None and time.time() - t0 > budget_s:
                if echo:
                    print("budget %.0fs reached after %d seed(s)" % (budget_s, len(rows)))
                break
            src = ProgramGen(seed, stress_rate=stress_rate).program()
            row = depth_demand(pkg, src, timeout_s=timeout_s)
            row["seed"] = seed
            f.write(json.dumps(row, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
            rows.append(row)
            if echo:
                print("seed %-6d demand %-16s %5.1fs %s"
                      % (seed, row["demand"], row["s"], row.get("note", "")))
    if echo:
        print("%d new row(s) in %.1fs -> %s" % (len(rows), time.time() - t0, out))
    return rows


def summarize_depth(rows):
    bounded = [r for r in rows if r.get("note") == "bounded"]
    unb = [r for r in rows if r.get("demand") == "unbounded"]
    peaks = sorted(r["peak"] for r in bounded if "peak" in r)
    return {"seeds": len(rows), "bounded": len(bounded), "unbounded": len(unb),
            "errors": len([r for r in rows if r.get("demand") == "error"]),
            "max_peak": peaks[-1] if peaks else None,
            "p50_peak": _pct(peaks, 0.5),
            "brackets": _hist([r["demand"] for r in rows]),
            "unbounded_seeds": [r["seed"] for r in unb][:40]}


def censored_seeds(rows):
    """Seeds whose sweep row shows a censored T-SPACE demand."""
    return [r["seed"] for r in rows
            if r.get("sites", {}).get("T-SPACE", {}).get("censored")]


def chain_program(n):
    """`let c = 1 + 1 + ... (n terms)  print(str(c))` — the shape round 110's
    comment says reaches an excess of 98 in the fuzzer's own corpus."""
    return "let c = %s\nprint(str(c))\n" % (" + ".join(["1"] * n))


def chain_excess(pkg, n, max_depth=500):
    program = O._parse(pkg, chain_program(n))
    best, at, _i = O.frame_excess(pkg, program, max_depth=max_depth)
    return best, at


def chain_ladder(pkg=None, lengths=(2, 4, 8, 16, 32, 64, 100, 128, 160, 200,
                                    256, 320, 400), root=WHENCE_ROOT):
    """Frame excess as a function of `1 + 1 + ...` chain length.

    This is F-SLACK's ladder: the corpus's own demand is one point, and the
    slope tells you how far the generator would have to move for the site to
    fire. Stops early on the first parse or recursion failure, recording it.
    """
    pkg = pkg or load_whence(root, "r383chain")
    rows = []
    for n in lengths:
        try:
            best, at = chain_excess(pkg, n)
            rows.append({"terms": n, "excess": best, "at_guest_depth": at,
                         "over_slack": best > O.FRAME_SLACK})
        except RecursionError:
            rows.append({"terms": n, "excess": None, "error": "RecursionError"})
            break
        except Exception as e:                  # noqa: BLE001
            rows.append({"terms": n, "excess": None, "error": type(e).__name__})
            break
    return rows


def chain_crossing(pkg=None, lo=1, hi=400, root=WHENCE_ROOT):
    """Smallest chain length whose excess exceeds `FRAME_SLACK`, by bisection,
    or None if `hi` terms still does not reach it."""
    pkg = pkg or load_whence(root, "r383cross")
    try:
        top, _ = chain_excess(pkg, hi)
    except (RecursionError, Exception):         # noqa: BLE001
        top = None
    if top is None or top <= O.FRAME_SLACK:
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        try:
            e, _ = chain_excess(pkg, mid)
        except Exception:                       # noqa: BLE001
            e = 10 ** 9
        if e > O.FRAME_SLACK:
            hi = mid
        else:
            lo = mid + 1
    return lo


def paircap_program(k):
    """`k` distinct top-level bindings, so `render`'s pair loop has C(k,2)
    pairs available and checks only C(min(k,6),2) of them."""
    return "".join("let v%d = %d\n" % (i, i) for i in range(k))


def paircap_witness(pkg=None, k=10, root=WHENCE_ROOT):
    """COUNT the diverge calls `oracle_render` actually makes on a `k`-binding
    program, by wrapping `values.diverge` for the duration of the call.

    This is the honest proof the cap is real: not a reading of the loop bound
    but a count taken through the oracle's own entry point. `diverge` is
    called once per binding for the self-check and twice per checked pair for
    the symmetry check, so the pair count is `(calls - k) / 2`.
    """
    pkg = pkg or load_whence(root, "r383pair")
    V = O._values_mod(pkg)
    src = paircap_program(k)
    real = V.diverge
    calls = {"n": 0, "cross": 0}

    def counting(a, b):
        calls["n"] += 1
        if a is not b:
            calls["cross"] += 1
        return real(a, b)

    V.diverge = counting
    try:
        o = O.run_oracle("render", pkg, src, timeout_s=30.0)
    finally:
        V.diverge = real
    pairs_checked = calls["cross"] // 2
    return {"bindings": k, "kind": o.kind, "diverge_calls": calls["n"],
            "cross_calls": calls["cross"],
            "pairs_checked": pairs_checked, "pairs_total": _nc2(k),
            "pairs_skipped": _nc2(k) - pairs_checked}


def deep_program(n):
    """A TAIL loop `n` bounces long.

    It must be a tail loop, not ordinary recursion: T-SPACE measures the
    LIFTED run, and `clear_tail_flags` only has something to clear if the
    call was in tail position. The host charges a tail call no depth (SPEC
    rule 8), so the original runs flat and the lifted copy recurses `n`
    deep — which is exactly the asymmetry the space exemption exists for.
    """
    return ("fn loop(n) { if n <= 0 { 0 } else { loop(n - 1) } }\n"
            "let r = loop(%d)\nprint(str(r))\n" % n)


def spec_shadow_program():
    """A program whose parameter spec NAME is bound twice — P-EXEMPT's first
    clause, which the fuzz grammar has no shape for.

    The second binding has to be in a DIFFERENT BLOCK. Whence's parser
    refuses same-block rebinding outright ("'S' is already bound in this
    block (line 1); Whence has no rebinding") and refuses a second `shape S`
    in the same block too, so the only reachable form of the multiplicity the
    exemption keys on is a nested-scope shadow — here, a parameter named `S`
    on another function. The exemption's own comment says "bound more than
    once anywhere in the program" without noting that the language admits
    exactly one way to do it.
    """
    return ("shape S = @{a: num}\n"
            "fn f(x: S) { x }\n"
            "fn g(S) { S }\n"
            "let r = f(@{a: 1})\n"
            "let q = g(2)\n"
            "print(str(r))\n")


def typed_bound_program():
    """A program that BINDS `typed` — P-EXEMPT's second clause."""
    return ("fn typed(a, b, c) { a }\n"
            "fn g(y: num) { y }\n"
            "let r = g(3)\nprint(str(r))\n")


def witnesses(root=WHENCE_ROOT, max_depth=500):
    """Run one constructed input per unreached site through `measure` and the
    real oracle, and report whether the site fired.

    A `False` here means the detector is wrong, not that the corpus is far —
    which is the distinction the whole module exists to make.
    """
    pkg = dict(load_whence(root, "r383wit"))
    pkg.setdefault("root", root)
    out = []

    def one(sid, label, src, oracle_name):
        try:
            m = measure(pkg, src, max_depth=max_depth)
            st = m["sites"].get(sid, {})
            o = O.run_oracle(oracle_name, pkg, src, timeout_s=30.0,
                             max_depth=max_depth)
            out.append({"site": sid, "witness": label,
                        "fired": bool(st.get("fired")),
                        "demand": st.get("demand"),
                        "oracle_kind": o.kind,
                        "oracle_detail": (o.detail or "")[:120].replace("\n", " "),
                        "parse_error": m.get("parse_error", "")})
        except BaseException as e:               # noqa: BLE001
            out.append({"site": sid, "witness": label, "fired": None,
                        "error": type(e).__name__ + ": " + str(e)[:80]})

    # F-SLACK is the one site whose band CANNOT be entered by any program
    # this language can express: `FAST_MAX_DEPTH = 100` caps a call-free
    # chain's transient at 98 and `MAX_NESTING = 60` caps nested literals at
    # depth 59. So the honest witness moves the CEILING, not the program —
    # and a bare "fired: false" on the program witness would read as a broken
    # detector when it is in fact the result.
    cross = chain_crossing(pkg)
    one("F-SLACK", "1+1+... chain at the measured crossing (%s terms); "
        "None means the band is unreachable by construction" % cross,
        chain_program(cross or 400), "frames")
    I = pkg["Interpreter"]
    orig = I.FAST_MAX_DEPTH
    try:
        I.FAST_MAX_DEPTH = O.FRAME_SLACK + 10
        o = O.run_oracle("frames", pkg, chain_program(400), timeout_s=30.0)
        out.append({"site": "F-SLACK",
                    "witness": "FAST_MAX_DEPTH raised %d -> %d (the ceiling "
                               "moved, not the program)" % (orig, I.FAST_MAX_DEPTH),
                    "fired": o.kind == "mismatch",
                    "demand": I.FAST_MAX_DEPTH - 2,
                    "oracle_kind": o.kind,
                    "oracle_detail": (o.detail or "")[:120].replace("\n", " "),
                    "parse_error": ""})
    finally:
        I.FAST_MAX_DEPTH = orig
    one("R-CAP", "10 top-level bindings", paircap_program(10), "render")
    one("T-SPACE", "tail loop 600 bounces long", deep_program(600),
        "tail_transparency")
    one("P-EXEMPT", "spec name bound twice", spec_shadow_program(),
        "param_erasure")
    one("P-EXEMPT", "program binds `typed`", typed_bound_program(),
        "param_erasure")
    return out


# ------------------------------------------------------- round 110's claims --

def round110_claims(root=WHENCE_ROOT, n=264, stress_rate=0.5, timeout_s=10.0):
    """Re-execute the three numbers `oracles.py`'s FRAME_SLACK comment states.

    The comment (round 110, unchanged for 273 rounds) says: *"Measured (round
    110, 264 programs + examples): examples <= 19, most fuzz programs 5-20,
    the fuzzer's `1 + 1 + ...` chains 98, nested list literals 59"*. Nothing
    re-executes any of it — round 321 item 14 / round 333 item 4's class. So
    this does, on the same population size, and reports what it gets.
    """
    pkg = load_whence(root, "r383r110")
    res = {"n_programs": n}
    ex_max, ex_worst = -1, ""
    for name in O.list_example_files(root):
        if name in ("deep.lang", "meta.lang"):
            continue
        with open(os.path.join(root, "examples", name), encoding="utf-8") as f:
            src = f.read()
        best, err, _s = guarded(
            lambda: O.frame_excess(pkg, O._parse(pkg, src))[0], timeout_s)
        if err:
            continue
        if best > ex_max:
            ex_max, ex_worst = best, name
    res["examples_max_excess"] = ex_max
    res["examples_worst"] = ex_worst
    res["comment_says_examples"] = 19

    fuzz = []
    skipped = 0
    for seed in range(n):
        src = ProgramGen(seed, stress_rate=stress_rate).program()
        # Guarded, and the skip COUNT is reported: an unguarded loop here ran
        # for minutes on a runaway seed under `setprofile`, and a silently
        # dropped program would bias the very distribution being compared.
        best, err, _s = guarded(
            lambda: O.frame_excess(pkg, O._parse(pkg, src))[0], timeout_s)
        if err:
            skipped += 1
            continue
        fuzz.append(best)
    fuzz.sort()
    res["fuzz_n"] = len(fuzz)
    res["fuzz_skipped"] = skipped
    res["fuzz_p50"] = _pct(fuzz, 0.5)
    res["fuzz_p90"] = _pct(fuzz, 0.9)
    res["fuzz_max"] = fuzz[-1] if fuzz else None
    res["fuzz_in_5_20"] = len([x for x in fuzz if 5 <= x <= 20])
    res["comment_says_fuzz_range"] = [5, 20]

    # the two named shapes
    res["fast_max_depth"] = pkg["Interpreter"].FAST_MAX_DEPTH
    res["chain_98_terms_excess"] = chain_excess(pkg, 98)[0]
    res["chain_400_terms_excess"] = chain_excess(pkg, 400)[0]
    res["comment_says_chains"] = 98
    P = __import__(pkg["name"] + ".parser", fromlist=["MAX_NESTING"])
    res["max_nesting"] = P.MAX_NESTING
    deepest = P.MAX_NESTING - 1
    nested = ("let z = " + "[" * deepest + "1" + "]" * deepest +
              "\nprint(str(z))\n")
    val, err, _s = guarded(
        lambda: O.frame_excess(pkg, O._parse(pkg, nested))[0], timeout_s)
    res["deepest_parseable_list_depth"] = deepest
    res["nested_list_max_excess"] = val if not err else "error: " + err
    res["comment_says_nested_lists"] = 59
    return res


# -------------------------------------------------------------------- cli --

def default_out(kind):
    here = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    d = os.path.join(here, "state", "swe", "round-383")
    if os.path.isdir(d):
        return os.path.join(d, "%s.jsonl" % kind)
    return os.path.join(os.getcwd(), "%s.jsonl" % kind)


def _flag(argv, name, cast=str, default=None):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def main(argv):
    cmd = argv[0] if argv else "sites"
    if cmd == "sites":
        verify_sites()
        print(json.dumps([s.as_dict() for s in SITES], indent=1))
        print("# %d site(s), all anchors verified against oracles.py" % len(SITES))
    elif cmd == "sweep":
        n = int(argv[1]) if len(argv) > 1 and not argv[1].startswith("-") else 500
        sweep(n, out=_flag(argv, "--out"),
              stress_rate=_flag(argv, "--stress", float, 0.5),
              budget_s=_flag(argv, "--budget-s", float),
              start=_flag(argv, "--start", int, 0),
              with_oracles="--no-oracles" not in argv)
        print(report(summarize(read_rows(_flag(argv, "--out")
                                         or default_out("sweep")))))
    elif cmd == "report":
        print(report(summarize(read_rows(_flag(argv, "--out")
                                         or default_out("sweep")))))
    elif cmd == "json":
        print(json.dumps(summarize(read_rows(_flag(argv, "--out")
                                             or default_out("sweep"))), indent=1))
    elif cmd == "depth":
        sw = read_rows(_flag(argv, "--sweep") or default_out("sweep"))
        seeds = censored_seeds(sw)
        if _flag(argv, "--limit", int):
            seeds = seeds[:_flag(argv, "--limit", int)]
        print("%d censored seed(s) from the sweep" % len(seeds))
        depth_ladder(seeds, out=_flag(argv, "--out"),
                     budget_s=_flag(argv, "--budget-s", float))
        print(json.dumps(summarize_depth(
            read_rows(_flag(argv, "--out") or default_out("depth"))), indent=1))
    elif cmd == "depth-summary":
        print(json.dumps(summarize_depth(
            read_rows(_flag(argv, "--out") or default_out("depth"))), indent=1))
    elif cmd == "chainladder":
        rows = chain_ladder()
        for r in rows:
            print(json.dumps(r, sort_keys=True))
        print("crossing (smallest length over slack %d): %s"
              % (O.FRAME_SLACK, chain_crossing()))
    elif cmd == "paircap":
        print(json.dumps(paircap_witness(k=_flag(argv, "--bindings", int, 10)),
                         indent=1))
    elif cmd == "witnesses":
        for w in witnesses():
            print(json.dumps(w, sort_keys=True))
    elif cmd == "round110":
        print(json.dumps(round110_claims(), indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

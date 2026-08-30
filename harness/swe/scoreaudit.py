"""Re-audit an ALREADY-RECORDED mutation report from its own stored evidence.

Round 349 (harness A) found that `run_mutant` read *every* non-zero exit code
as KILLED, so a suite that never ran at all scored a perfect 100%, and fixed
it (`mutation.classify_mutant_run`). It then left this, its next-steps item 5,
to a SWE-loop(D) round:

    no historical mutation score was re-audited. Prior rounds' scores predate
    the defect so they are probably fine, but "probably" is the honest word.
    ... A SWE-loop(D) round could convert this to a number.

This module is that number. It needs no re-run: `Mutant.as_dict` has always
stored `detail` — the last three lines of the run's own output — for every
mutant that was not classified `survived`. That text says whether a TEST
failed or whether pytest never got as far as collecting one, which is exactly
the distinction the pre-349 classifier threw away.

Buckets, and why each is drawn where it is:

  survived          exit 0. Unambiguous under both the old and the new
                    classifier, so never re-examined here.
  timeout           the runner killed the process group. `run_mutant` has
                    always recorded this separately and `MutationReport.killed`
                    has always counted it; it is a real behavioural difference
                    and it carries no pytest tail to audit.
  evidenced_kill    the stored tail names a failing test (`FAILED <nodeid>`,
                    `N failed`, or pytest's `-x` "stopping after N failures"
                    banner). Only this shape means "the suite ran and a test
                    failed", which is the only thing that kills a mutant.
  no_evidence_kill  the stored tail is one of pytest's harness-broke shapes
                    (`no tests ran`, `ERROR: file or directory not found`,
                    `INTERNALERROR`, a usage error). The run produced no
                    verdict about the mutant; the pre-349 classifier scored
                    it as a kill anyway.
  unknown_kill      neither. Reported as its own bucket with the distinct
                    tails listed, so extending the classifier is a decision
                    someone makes on the evidence rather than a silent
                    default. NEVER folded into either side.

The no-evidence patterns are checked BEFORE the kill-evidence ones. Under
`pytest -x a.py missing.py` the usage error aborts before collection, so the
two shapes do not co-occur in practice; when in doubt, "the harness broke"
has to win, because the alternative is the failure direction round 349
documented — flattering.

What this CANNOT see, stated up front because the number would otherwise be
read as stronger than it is: a *pre-existing failing test* pins every mutant
to exit 1 with a real `FAILED` line, and every one of those reads here as an
`evidenced_kill`. That is round 349's own point — no per-mutant exit-code
analysis can catch it, only a baseline pre-flight can. What this module
offers instead is a DIAGNOSTIC, not a verdict: `dominant_killer` reports the
single test node id that accounts for the largest share of evidenced kills.
One test killing nearly everything is the fingerprint of a red baseline; it
is also what a legitimate `-x` run with a good prioritizer can look like, so
it is printed as a share and never as a judgement.

Output, per report:

  score             the number the report published (killed / total).
  audited_score     (evidenced + timeout) / total — the LOWER bound, i.e.
                    every unaudited kill assumed not to be one.
  score_upper       the published score. Equals `audited_score` exactly when
                    nothing is unaudited, in which case the historical figure
                    is CONFIRMED rather than merely un-refuted.

Usage:
    python3 -m swe.scoreaudit state/swe/**/*.json
    python3 -m swe.scoreaudit --json out.json state/swe/round-137/*.json
"""

import collections
import json
import os
import re
import sys

# A test actually failed. Searched over the WHOLE stored detail, not just its
# last line: `Mutant.as_dict` truncates `detail` to 300 characters, which cuts
# some tails mid-line, and the `FAILED <nodeid>` line survives that cut more
# often than the summary line does.
_KILL_EVIDENCE = (
    re.compile(r"^FAILED\s+\S", re.M),
    re.compile(r"\b\d+ failed\b"),
    re.compile(r"stopping after \d+ failure"),
)

# The suite did not run. `(pattern, label)` so the report can say WHICH shape.
_NO_EVIDENCE = (
    (re.compile(r"no tests ran"), "no tests ran"),
    (re.compile(r"ERROR: file or directory not found"), "test path not found"),
    (re.compile(r"ERROR: not found:"), "test node id not found"),
    (re.compile(r"INTERNALERROR"), "pytest internal error"),
    (re.compile(r"^ERROR: usage:", re.M), "usage error"),
    (re.compile(r"error: unrecognized arguments"), "usage error"),
    (re.compile(r"^usage: pytest", re.M), "usage error"),
    (re.compile(r"Invalid statement|Failed to load configuration|"
                r"could not be parsed|TOMLDecodeError"), "config parse error"),
)

# The first `FAILED <nodeid>` in a tail: the test that did the killing.
_FAILED_NODE = re.compile(r"^FAILED\s+(\S+)", re.M)

BUCKETS = ("survived", "timeout", "evidenced_kill", "no_evidence_kill", "unknown_kill")


def classify_recorded(mutant):
    """`(bucket, label)` for one recorded mutant dict. See the module docstring.

    `label` is a short reason for the no-evidence and unknown buckets and ""
    otherwise; it is what the report groups by.
    """
    status = mutant.get("status")
    if status == "survived":
        return "survived", ""
    if status == "timeout":
        return "timeout", ""
    if status == "error":
        # Only a post-349 run can produce this, and it already means exactly
        # what this module's `no_evidence_kill` means. Kept distinct in the
        # LABEL so an audited report can be told from a re-audited one.
        return "no_evidence_kill", "classified 'error' at run time (post-349)"
    detail = mutant.get("detail") or ""
    if not detail.strip():
        return "unknown_kill", "no detail recorded"
    for pat, label in _NO_EVIDENCE:
        if pat.search(detail):
            return "no_evidence_kill", label
    for pat in _KILL_EVIDENCE:
        if pat.search(detail):
            return "evidenced_kill", ""
    return "unknown_kill", detail.strip().splitlines()[-1][:120]


def audit(data, path=""):
    """Re-audit one loaded mutation report. Returns a plain dict."""
    mutants = data.get("mutants") or []
    counts = collections.Counter()
    labels = collections.Counter()
    killers = collections.Counter()
    suspects = []
    for m in mutants:
        bucket, label = classify_recorded(m)
        counts[bucket] += 1
        if label:
            labels[label] += 1
        if bucket == "no_evidence_kill":
            suspects.append({"id": m.get("id"), "line": m.get("line"),
                             "op": m.get("op"), "label": label,
                             "first_file": m.get("first_file"),
                             "files_run": m.get("files_run")})
        elif bucket == "evidenced_kill":
            hit = _FAILED_NODE.search(m.get("detail") or "")
            if hit:
                killers[hit.group(1)] += 1
    total = len(mutants)
    audited_kills = counts["evidenced_kill"] + counts["timeout"]
    unaudited = counts["no_evidence_kill"] + counts["unknown_kill"]
    top = killers.most_common(1)
    return {
        "path": path,
        "total": total,
        "published_killed": data.get("killed"),
        "published_survived": data.get("survived"),
        "published_score": data.get("score"),
        "counts": dict((b, counts[b]) for b in BUCKETS),
        "labels": dict(labels),
        "audited_kills": audited_kills,
        "unaudited_kills": unaudited,
        "audited_score": round(audited_kills / total, 4) if total else 0.0,
        "score_upper": round((audited_kills + unaudited) / total, 4) if total else 0.0,
        "confirmed": unaudited == 0,
        "dominant_killer": (top[0][0] if top else None),
        "dominant_killer_share": (round(top[0][1] / counts["evidenced_kill"], 4)
                                  if top and counts["evidenced_kill"] else None),
        "suspects": suspects,
    }


def format_audit(a, show_suspects=5):
    """Human-readable block for one audited report."""
    c = a["counts"]
    lines = ["%s" % a["path"],
             "  published: %s killed / %s survived of %s  score %s"
             % (a["published_killed"], a["published_survived"], a["total"],
                a["published_score"])]
    if a["confirmed"]:
        lines.append("  CONFIRMED: every kill carries its own evidence "
                     "(%d evidenced, %d timeout); score %s stands."
                     % (c["evidenced_kill"], c["timeout"], a["audited_score"]))
    else:
        lines.append("  NOT EVIDENCE: %d of %d kills produced no verdict about "
                     "the mutant (%d no-evidence, %d unclassifiable)."
                     % (a["unaudited_kills"], a["published_killed"] or 0,
                        c["no_evidence_kill"], c["unknown_kill"]))
        lines.append("  true score is in [%s, %s], not %s."
                     % (a["audited_score"], a["score_upper"], a["published_score"]))
    for label, n in sorted(a["labels"].items(), key=lambda kv: -kv[1]):
        lines.append("    %-40s %d" % (label, n))
    for s in a["suspects"][:show_suspects]:
        lines.append("    e.g. %-34s line %-6s %s" % (s["id"], s["line"], s["label"]))
    if a["dominant_killer"]:
        lines.append("  dominant killer: %s (%.1f%% of evidenced kills) -- a "
                     "diagnostic, not a verdict; see the module docstring."
                     % (a["dominant_killer"], 100 * a["dominant_killer_share"]))
    return "\n".join(lines)


def audit_paths(paths):
    """Audit every path that looks like a mutation report; skip the rest."""
    out = []
    for p in paths:
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError):
            continue
        if not isinstance(data, dict) or "mutants" not in data:
            continue
        out.append(audit(data, path=p))
    return out


def totals(audits):
    """Corpus-wide roll-up across several audited reports."""
    t = collections.Counter()
    for a in audits:
        for b in BUCKETS:
            t[b] += a["counts"][b]
        t["total"] += a["total"]
    return {"reports": len(audits),
            "confirmed_reports": sum(1 for a in audits if a["confirmed"]),
            "mutants": t["total"],
            "counts": dict((b, t[b]) for b in BUCKETS)}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", help="write the full audit (including suspect ids) here")
    ap.add_argument("--suspects", type=int, default=5, help="suspect ids to show per report")
    a = ap.parse_args(argv)
    audits = audit_paths(a.paths)
    for one in audits:
        print(format_audit(one, show_suspects=a.suspects))
        print()
    t = totals(audits)
    print("corpus: %d report(s), %d confirmed, %d mutants -- %s"
          % (t["reports"], t["confirmed_reports"], t["mutants"],
             ", ".join("%s %d" % (k, v) for k, v in sorted(t["counts"].items()))))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"reports": audits, "totals": t}, f, indent=1)
    return 0 if t["counts"]["no_evidence_kill"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

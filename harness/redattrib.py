#!/usr/bin/env python3
"""redattrib.py — who broke each health check, and could they have SEEN it?

Round 455 (SWE-loop D). The driver runs four per-round health checks AFTER
the round's agent process has exited:

    harness/run_tests_fast.sh          -> logs/health_round_<N>.log
    languages/whence/run_tests_fast.sh -> logs/whence_health_round_<N>.log
    nuc/run_checks_fast.sh             -> logs/nuc_health_round_<N>.log
    skills/run_checks_fast.sh          -> logs/skills_health_round_<N>.log

`skills/unrun-checker-latency/SKILL.md` calls that arrangement's cost "the
floor of one": a check that speaks after the author is gone cannot get a
violation's detection latency below one round. Round 453 measured the floor
on the skills corpus and drew a mechanism from it -- "Nobody who owns a
checker breaks it."

This module measures the same thing over ALL FOUR checks, and the mechanism
does not survive contact with the other three. The rate at which a check's
OWNER opens its own red episodes ranges from 0/16 to 5/5 across the four,
so "who owns it" predicts nothing on its own. What does predict it is
declared in `harness/crosstrack-registry.json`: the node's SUBJECT SCOPE --
whose work can turn it red -- which is a different question from which suite
the node lives in.

The number this module exists to produce is the INVISIBLE-OPEN RATE: the
share of red episodes whose opening round could not have seen the red by
running its own track's suite. That is the part of the floor that is not
about scheduling at all, and no amount of moving the runner earlier touches
it.

GROUND TRUTH IS THE PER-ROUND LOG, NOT `logs/driver.log`. The driver's
one-line summary names at most two failing tests and appends "(+N more)",
so a table built from it is truncated -- and it is also wrong in at least
one place: driver.log's round-362 line names `test_self_eval.py::
test_shape_needs_three_adjacent_tokens_on_both_sides`, while
`logs/health_round_362.log` records the actual failure as
`test_run_driver_whence_health_check.py::
test_whence_health_check_fail_logged_when_script_fails`. The per-round logs
carry every `FAILED <nodeid>` line and all 554 of them are retained.

Commands
--------
    python3 harness/redattrib.py attribute [--json]
        Per-check and overall attribution table; the headline is the
        invisible-open rate. Exit 0 always -- this is a measurement.

    python3 harness/redattrib.py nodes [--json]
        Every test node that has ever gone red, with its red rounds, its
        declared subject scope, and the tracks that opened its episodes.

    python3 harness/redattrib.py audit
        FAIL-CLOSED registry audit. Exit 1 on any error.
          R001  a node went red and has no registry entry
          R002  a registry entry names a node that never went red
          R003  a registry entry declares an unknown subject_scope
          R004  a track named by an episode has no track_suites row

An episode's opener is NOT attributed when the episode began on the check's
FIRST EVER run: the check was installed red, and nobody opened it. That is
`unopened` below, and it is one episode here -- the nuc check, wired by
round 409, red on its first run at round 410, closed 32 rounds later by
round 442. Merging it into the opener counts would report a language(C)
round as having broken the NUC suite, which it did not.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REGISTRY_NAME = "harness/crosstrack-registry.json"

# log-file prefix -> (path root the node ids are relative to, hosting suite)
CHECKS = OrderedDict((
    ("health_round", (".", "harness/tests")),
    ("whence_health_round", ("languages/whence", "languages/whence/tests")),
    ("nuc_health_round", (".", "nuc/tests")),
    ("skills_health_round", (".", "skills")),
))
CHECK_LABEL = {
    "health_round": "health-check",
    "whence_health_round": "whence-health-check",
    "nuc_health_round": "nuc-health-check",
    "skills_health_round": "skills-check",
}
SUITE_OWNER = {
    "harness/tests": "harness(A)",
    "languages/whence/tests": "language(C)",
    "nuc/tests": "NUC-integration(E)",
    "skills": "skills(B)",
}


def load_registry(root=ROOT):
    with open(os.path.join(root, REGISTRY_NAME), encoding="utf-8") as fh:
        return json.load(fh)


def round_tracks(root=ROOT):
    """round number -> track, from run_driver.sh's own `start` lines."""
    out = {}
    path = os.path.join(root, "logs", "driver.log")
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = re.search(r"round (\d+) track=(\S+) start", line)
            if m:
                out[int(m.group(1))] = m.group(2)
    return out


def read_logs(root=ROOT):
    """prefix -> {round: frozenset(nodeid)} for every retained per-round log.

    A log with no `FAILED` line is a green run and maps to an empty set, so
    "ran and passed" and "never ran" stay distinguishable -- the latter has
    no key at all.
    """
    runs = {k: {} for k in CHECKS}
    logdir = os.path.join(root, "logs")
    if not os.path.isdir(logdir):
        return runs
    pat = re.compile(r"^(%s)_(\d+)\.log$" % "|".join(CHECKS))
    for fn in sorted(os.listdir(logdir)):
        m = pat.match(fn)
        if not m:
            continue
        prefix, rnd = m.group(1), int(m.group(2))
        rel = CHECKS[prefix][0]
        with open(os.path.join(logdir, fn), encoding="utf-8",
                  errors="replace") as fh:
            text = fh.read()
        nodes = set()
        for nid in re.findall(r"^FAILED (\S+)", text, re.M):
            nodes.add(nid if rel == "." else "%s/%s" % (rel, nid))
        runs[prefix][rnd] = frozenset(nodes)
    return runs


# A log with no pytest count line did not run a suite to completion. Round
# 348's `logs/whence_health_round_348.log` is the case that forces this:
# pytest exited 4 on a `pyproject.toml` config error, so the file holds ZERO
# `FAILED` lines while `driver.log` records the round as FAIL. Counting it
# green is the defect `knowledge/round-349-a-suite-that-cannot-run-is-not-a-
# suite-that-passes.md` is named after, and a node-level parser walks
# straight into it.
COUNT_LINE = re.compile(r"^\d+ (passed|failed)|, \d+ (passed|failed)", re.M)

# ...and the detector is itself pytest-shaped, so it may only be pointed at
# pytest logs. Round 455 built it, ran it over all four checks, and it
# reported 68 of the 91 `skills-check` logs as "could not run" -- every one
# of which had in fact run, because that check's log is a checker/verdict
# TABLE whose count line reads `unit_tests  ok  939 passed in 367.50s`,
# indented rather than at line start. A grammar-specific heuristic applied
# across grammars is the same error this module measures, committed by the
# module doing the measuring. `skills-check` is excluded here and reported
# as a GRAMMAR GAP instead, which is the honest shape: unmeasured, not green.
PYTEST_LOGS = ("health_round", "whence_health_round", "nuc_health_round")


def could_not_run(root=ROOT):
    """prefix -> sorted rounds whose log holds no pytest count line."""
    out = {k: [] for k in PYTEST_LOGS}
    logdir = os.path.join(root, "logs")
    if not os.path.isdir(logdir):
        return out
    pat = re.compile(r"^(%s)_(\d+)\.log$" % "|".join(PYTEST_LOGS))
    for fn in sorted(os.listdir(logdir)):
        m = pat.match(fn)
        if not m:
            continue
        with open(os.path.join(logdir, fn), encoding="utf-8",
                  errors="replace") as fh:
            if not COUNT_LINE.search(fh.read()):
                out[m.group(1)].append(int(m.group(2)))
    return {k: sorted(v) for k, v in out.items()}


def driver_verdicts(root=ROOT):
    """check label -> Counter of PASS/FAIL/ERROR, from run_driver.sh's log.

    Only used as a CROSS-CHECK on this module's own parse. If driver.log
    records N failing runs of a check and the per-round parser recovers no
    nodes for it, the parser does not understand that check's log grammar --
    which is true of `skills-check`, whose logs are a checker/verdict table
    rather than pytest output. Reporting the 0 without the cross-check would
    read as `never red`, and this module exists because a silent zero is
    indistinguishable from a healthy one.
    """
    out = {v: Counter() for v in CHECK_LABEL.values()}
    path = os.path.join(root, "logs", "driver.log")
    if not os.path.exists(path):
        return out
    labels = sorted(CHECK_LABEL.values(), key=len, reverse=True)
    pat = re.compile(r"round \d+: (%s) (PASS|FAIL|ERROR)"
                     % "|".join(re.escape(x) for x in labels))
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = pat.search(line)
            if m:
                out[m.group(1)][m.group(2)] += 1
    return out


def node_suite(nodeid):
    """Longest declared-suite prefix that the node id starts with."""
    best = None
    for suite in SUITE_OWNER:
        if nodeid.startswith(suite + "/") and (best is None or len(suite) > len(best)):
            best = suite
    return best


def episodes_for(nodeid, rounds_in_order, red_rounds):
    """Maximal runs of consecutive RED runs of the node's own check."""
    eps, cur = [], None
    for rnd in rounds_in_order:
        if rnd in red_rounds:
            if cur is None:
                cur = {"open": rnd, "rounds": []}
            cur["rounds"].append(rnd)
        elif cur is not None:
            cur["close"] = rnd
            eps.append(cur)
            cur = None
    if cur is not None:
        cur["close"] = None
        eps.append(cur)
    return eps


def analyse(root=ROOT):
    reg = load_registry(root)
    track_suites = reg["_track_suites"]
    scopes = set(reg["_subject_scope"])
    nodes_reg = reg["nodes"]
    tracks = round_tracks(root)
    runs = read_logs(root)

    seen = {}          # nodeid -> set(rounds red)
    for prefix, per_round in runs.items():
        for rnd, failed in per_round.items():
            for nid in failed:
                seen.setdefault(nid, set()).add(rnd)

    findings = []
    for nid in sorted(seen):
        if nid not in nodes_reg:
            findings.append(("R001", nid, "went red and has no registry entry"))
    for nid, ent in sorted(nodes_reg.items()):
        if nid not in seen:
            findings.append(("R002", nid, "registry entry for a node that never went red"))
        if ent.get("subject_scope") not in scopes:
            findings.append(("R003", nid, "unknown subject_scope %r"
                             % ent.get("subject_scope")))

    node_rows, ep_rows = [], []
    for nid in sorted(seen):
        suite = node_suite(nid)
        prefix = next((p for p, (_r, s) in CHECKS.items() if s == suite), None)
        if prefix is None:
            continue
        order = sorted(runs[prefix])
        eps = episodes_for(nid, order, seen[nid])
        scope = nodes_reg.get(nid, {}).get("subject_scope", "UNDECLARED")
        for e in eps:
            born = bool(order) and e["open"] == order[0]
            opener = tracks.get(e["open"])
            if opener and opener not in track_suites:
                findings.append(("R004", nid, "no track_suites row for %r" % opener))
            visible = (opener in track_suites
                       and suite in track_suites.get(opener, []))
            ep_rows.append({
                "node": nid, "suite": suite, "owner": SUITE_OWNER.get(suite),
                "scope": scope, "open": e["open"], "open_track": opener,
                "len": len(e["rounds"]), "close": e.get("close"),
                "close_track": tracks.get(e.get("close")),
                "born_red": born,
                "opened_by_owner": (not born) and opener == SUITE_OWNER.get(suite),
                "visible_to_opener": (not born) and bool(visible),
            })
        node_rows.append({
            "node": nid, "suite": suite, "owner": SUITE_OWNER.get(suite),
            "scope": scope, "red_rounds": sorted(seen[nid]),
            "n_red": len(seen[nid]), "episodes": len(eps),
        })

    att = [e for e in ep_rows if not e["born_red"]]
    real = [e for e in att if e["scope"] != "environmental"]
    per_check = OrderedDict()
    for prefix, (_rel, suite) in CHECKS.items():
        rows = [e for e in ep_rows if e["suite"] == suite]
        a = [e for e in rows if not e["born_red"]]
        per_check[CHECK_LABEL[prefix]] = {
            "suite": suite, "owner": SUITE_OWNER.get(suite),
            "runs": len(runs[prefix]),
            "red_runs": sum(1 for r in runs[prefix].values()
                            if any(node_suite(n) == suite for n in r)),
            "nodes_ever_red": sum(1 for n in node_rows if n["suite"] == suite),
            "episodes": len(rows), "unopened_born_red": len(rows) - len(a),
            "attributable": len(a),
            "opened_by_owner": sum(1 for e in a if e["opened_by_owner"]),
            "invisible_opens": sum(1 for e in a if not e["visible_to_opener"]),
        }

    cnr = could_not_run(root)
    dv = driver_verdicts(root)
    grammar = []
    for prefix, (_rel, suite) in CHECKS.items():
        label = CHECK_LABEL[prefix]
        driver_red = dv[label]["FAIL"]
        parsed = sum(1 for n in node_rows if n["suite"] == suite)
        if driver_red and not parsed:
            grammar.append(
                "%s: driver.log records %d FAIL run(s), this parser recovered "
                "0 test node(s) -- its logs are not pytest output, so it is "
                "NOT represented in any number below" % (label, driver_red))

    return {
        "could_not_run": cnr,
        "driver_verdicts": {k: dict(v) for k, v in dv.items()},
        "grammar_gaps": grammar,
        "scope_by_visibility": {
            sc: {"visible": sum(1 for e in att
                                if e["scope"] == sc and e["visible_to_opener"]),
                 "invisible": sum(1 for e in att
                                  if e["scope"] == sc and not e["visible_to_opener"])}
            for sc in sorted({e["scope"] for e in att})
        },
        "registry_findings": findings,
        "nodes": node_rows,
        "episodes": ep_rows,
        "per_check": per_check,
        "totals": {
            "logs_read": sum(len(v) for v in runs.values()),
            "distinct_red_nodes": len(seen),
            "episodes": len(ep_rows),
            "born_red_unopened": len(ep_rows) - len(att),
            "attributable": len(att),
            "invisible_opens": sum(1 for e in att if not e["visible_to_opener"]),
            "invisible_open_rate": (
                round(sum(1 for e in att if not e["visible_to_opener"]) / len(att), 4)
                if att else None),
            "attributable_excl_environmental": len(real),
            "invisible_opens_excl_environmental":
                sum(1 for e in real if not e["visible_to_opener"]),
            "invisible_open_rate_excl_environmental": (
                round(sum(1 for e in real if not e["visible_to_opener"]) / len(real), 4)
                if real else None),
            "by_scope": dict(Counter(e["scope"] for e in ep_rows)),
        },
    }


def cmd_attribute(args):
    res = analyse()
    if args.json:
        print(json.dumps(res, indent=2, sort_keys=True))
        return 0
    t = res["totals"]
    print("red-attribution: %d per-round log(s), %d node(s) ever red, "
          "%d episode(s)" % (t["logs_read"], t["distinct_red_nodes"], t["episodes"]))
    hdr = ("%-21s %5s %5s %6s %5s %6s %9s %11s"
           % ("check", "runs", "red", "nodes", "eps", "unopnd", "own-opened", "invisible"))
    print(hdr); print("-" * len(hdr))
    for name, v in res["per_check"].items():
        att = v["attributable"]
        print("%-21s %5d %5d %6d %5d %6d %4d/%-4d %5d/%-5d"
              % (name, v["runs"], v["red_runs"], v["nodes_ever_red"],
                 v["episodes"], v["unopened_born_red"],
                 v["opened_by_owner"], att, v["invisible_opens"], att))
    print()
    print("INVISIBLE-OPEN RATE  %d/%d = %.0f%%   (episodes whose opening round could not"
          % (t["invisible_opens"], t["attributable"],
             100 * (t["invisible_open_rate"] or 0)))
    print("                     have seen the red by running its own track's suite)")
    print("  excluding `environmental` episodes, which nobody opened: %d/%d = %.0f%%"
          % (t["invisible_opens_excl_environmental"],
             t["attributable_excl_environmental"],
             100 * (t["invisible_open_rate_excl_environmental"] or 0)))
    print("  episodes by declared subject scope: %s" % t["by_scope"])
    print()
    print("%-26s %9s %11s" % ("subject scope", "visible", "invisible"))
    for sc, v in sorted(res["scope_by_visibility"].items()):
        print("%-26s %9d %11d" % (sc, v["visible"], v["invisible"]))
    cnr = {k: v for k, v in res["could_not_run"].items() if v}
    if cnr:
        print("\nCOULD NOT RUN (log holds no pytest count line -- not green, "
              "not red):")
        for k, v in cnr.items():
            print("  %-21s rounds %s" % (CHECK_LABEL[k], v))
    for g in res["grammar_gaps"]:
        print("\nGRAMMAR GAP  %s" % g)
    if res["registry_findings"]:
        print("\n%d registry finding(s) -- run `audit` for detail"
              % len(res["registry_findings"]))
    return 0


def cmd_nodes(args):
    res = analyse()
    if args.json:
        print(json.dumps(res["nodes"], indent=2, sort_keys=True))
        return 0
    for n in sorted(res["nodes"], key=lambda r: (-r["n_red"], r["node"])):
        print("%3d red  %-24s %s" % (n["n_red"], n["scope"], n["node"]))
        print("         rounds %s" % (n["red_rounds"],))
    return 0


def cmd_audit(args):
    res = analyse()
    for code, nid, msg in res["registry_findings"]:
        print("%s  %s: %s" % (code, nid, msg))
    n = len(res["registry_findings"])
    print("red-attribution audit: %d node(s) ever red, %d declared, %d error(s)"
          % (res["totals"]["distinct_red_nodes"],
             len(load_registry()["nodes"]), n))
    return 1 if n else 0


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("attribute"); a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_attribute)
    n = sub.add_parser("nodes"); n.add_argument("--json", action="store_true")
    n.set_defaults(fn=cmd_nodes)
    d = sub.add_parser("audit"); d.set_defaults(fn=cmd_audit)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not getattr(args, "fn", None):
        build_parser().print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

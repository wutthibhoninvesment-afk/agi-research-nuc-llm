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
OWNER opens its own red episodes ranges from 0/46 to 8/8 across the four,
so "who owns it" predicts nothing on its own. What does predict it is
declared in `harness/crosstrack-registry.json`: the node's SUBJECT SCOPE --
whose work can turn it red -- which is a different question from which suite
the node lives in.

TWO LOG GRAMMARS, NOT ONE (round 461, SWE-loop D). Three of the four checks
write pytest output; `skills-check` writes a checker/verdict TABLE. Round
455 built the pytest parser, pointed it at all four, got a wrong answer on
the fourth, and then withdrew the fourth behind a printed GRAMMAR GAP rather
than reporting a silent zero -- which was the right call and still left the
headline computed over three checks while the docstring said four. Round 461
taught it the second grammar (`parse_corpus_row`) instead of widening the
first. The check that was 0 nodes and 0 episodes is 7 nodes and 46 episodes,
none of them opened by the track that owns it, and the invisible-open rate
went from 19/32 = 59% to 65/78 = 83%.

Round 453 measured the same corpus by anchoring on each log's
`corpus-check:` aggregate line. This module anchors on the per-row `ERROR`
flags -- an independent derivation from the same files -- and reproduces
round 453's headline exactly: 24 red runs of 89 over rounds 364-452, 16
episodes, longest 4, openers language(C) 7 / SWE-loop(D) 6 / harness(A) 2 /
NUC(E) 1 / skills(B) ZERO. `test_round_453s_check_level_measurement_is_
reproduced_exactly` holds that agreement open.

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
carry every `FAILED <nodeid>` line and every one of them is retained -- under
`logs/`, WHICH IS NOT IN GIT. `.gitignore` lines 28, 29, 35 and 60 exclude all
four per-round health logs by pattern, so `git ls-files logs/` is 9 against
the 602 this module reads at round 467. That is round 461's next-step 7 and
round 460's item 3, and it has a consequence a reader hits before they hit the
explanation: a fresh clone, or a `git worktree add HEAD --detach`, gives this
module almost no evidence and its whole-tree tests then fail for want of data
in a way that is indistinguishable from a real red. Round 461 measured it --
4 failed, 15 passed in a pristine worktree where the truth was 2 failed, 17
passed, two of the four being floods caused by the missing files. So
`evidence_base` counts what this checkout can actually see, `attribute` prints
a NO EVIDENCE BASE banner below `MIN_EVIDENCE_LOGS`, and the live tests skip
with that reason instead of failing. Whether the logs BELONG in git is still
the operator's question; reporting a wrong answer confidently while it is
open is not. The reconciliation printed by `attribute` is the guard on that
claim: every round the driver called FAIL or ERROR must be a round in which
this parser found a red node or found something that could not report.

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
import math
import os
import random
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


#: Below this many retained per-round logs, no number this module produces is
#: about the program's history -- it is about what a checkout happens to hold.
#: The live tree is at 602; a fresh clone is at 0 (the 9 tracked files under
#: `logs/` are not per-round health logs at all). Any floor in between
#: separates the two cases; this one is deliberately far from both.
MIN_EVIDENCE_LOGS = 50


def evidence_base(root=ROOT):
    """(n_logs, enough) -- how much of the retained corpus this checkout sees."""
    n = sum(len(v) for v in read_logs(root).values())
    return n, n >= MIN_EVIDENCE_LOGS


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
    pat = re.compile(r"^(%s)_(\d+)\.log$" % "|".join(PYTEST_LOGS))
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
    for prefix, per_round in corpus_rows(root).items():
        for rnd, rows in per_round.items():
            runs[prefix][rnd] = frozenset(
                CORPUS_NODE % c for c, (st, _co) in rows.items()
                if st == "ERROR")
    return runs


def observed_nodes(root=ROOT):
    """prefix -> {round: frozenset(nodeid)} | None -- what each run OBSERVED.

    `None` for a pytest check: pytest reports the whole suite it collected,
    so every node of that suite is observed on every run and there is nothing
    to intersect. A corpus check reports one row per checker that ran, and a
    checker that did not exist yet -- or was killed mid-run -- is observed by
    nobody. `analyse` uses this to build each node's OWN run order, so a
    round in which a node was not observed can neither open, close nor split
    one of its episodes.
    """
    out = {p: None for p in PYTEST_LOGS}
    for prefix, per_round in corpus_rows(root).items():
        out[prefix] = {
            rnd: frozenset(CORPUS_NODE % c for c, (st, _co) in rows.items()
                           if st in CONCLUSIVE)
            for rnd, rows in per_round.items()}
    return out


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
# module doing the measuring. `skills-check` was excluded there and reported
# as a GRAMMAR GAP instead, which is the honest shape: unmeasured, not green.
#
# Round 461 (SWE-loop D) closed the gap by teaching this module the OTHER
# grammar rather than by widening the pytest one. See `parse_corpus_row`.
PYTEST_LOGS = ("health_round", "whence_health_round", "nuc_health_round")

# ---------------------------------------------------------------------------
# The second grammar (round 461).
#
# `skills/run_checks_fast.sh` execs `corpus_check.py`, whose main() prints one
# row per checker with a single format string, `"%-18s %-22s %s" % (check,
# flag, summary)`, and then one `corpus-check: ...` aggregate line. `flag` is
# `ok`, `warn <codes>`, `ERROR <codes>`, or a bare status word -- `TIMEOUT`
# or `ABSENT` -- from `run_one`'s non-`ran` branches.
#
# So the finest unit this log can name is the CHECKER ROW, not a test. That
# is a real ceiling and not a parser limitation: the row that says
# `unit_tests ERROR rc1 / 2 failed, 937 passed` is a whole pytest suite, and
# `run_one` writes its child's output to a `tempfile.mkstemp` sink that a
# `finally` unlinks. WHICH tests failed inside a red `unit_tests` row is
# retained nowhere, for any round. `unit_tests` is therefore one node here,
# and its `why` in the registry says so.
#
# Two consequences for the machinery below, both of which the pytest grammar
# never had to face:
#
#   * A row can be NEITHER red nor green. `TIMEOUT` means the checker was
#     killed; it is not evidence that it passed. Such a round is dropped from
#     that node's run order, exactly as a round with no log at all is dropped
#     from a check's -- see `test_a_round_the_check_never_ran_cannot_join_two_
#     episodes`. Counting it green would split one episode into two.
#   * The corpus GROWS. `carryforward` joined at round 369, `verb_audit` at
#     423, `placeholder_check` at 429, `selfdesc_check` at 435. A checker that
#     did not exist yet has no row, and its absence is not a pass either.
CORPUS_LOGS = ("skills_health_round",)

#: Pseudo node id for a checker row. The path is the file that PRINTS the
#: row, so the id resolves to something a reader can open, and it starts with
#: `skills/` so `node_suite` places it in the same suite the check hosts.
CORPUS_NODE = "skills/skill-authoring/scripts/corpus_check.py::%s"

# `%-18s %-22s` pads with spaces, and no checker name reaches 18 characters
# (`state_claim_check` is 17), so the name is always followed by >=2 spaces
# and the flag always starts at column 19. The codes token is captured only
# when EXACTLY ONE space follows the status word, which is what the format
# string produces for `warn P004,P006` and never for `ok`/`TIMEOUT` (whose
# `%-22s` padding leaves >=16). The `corpus-check:` aggregate line does not
# match: `-` is not in the name class, so the name group cannot span it.
CORPUS_ROW = re.compile(r"^(\w[\w.]*) {2,}(ok|warn|ERROR|TIMEOUT|ABSENT)(?: (\S+))?")

#: Row statuses that are an OBSERVATION of the checker. Anything else means
#: the checker did not report -- see the `TIMEOUT` note above.
CONCLUSIVE = ("ok", "warn", "ERROR")


def parse_corpus_row(line):
    """(checker, status, codes) for one `corpus_check.py` row, else None."""
    m = CORPUS_ROW.match(line.rstrip("\n"))
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def corpus_rows(root=ROOT):
    """prefix -> {round: {checker: (status, codes)}} over the corpus logs."""
    out = {k: {} for k in CORPUS_LOGS}
    logdir = os.path.join(root, "logs")
    if not os.path.isdir(logdir):
        return out
    pat = re.compile(r"^(%s)_(\d+)\.log$" % "|".join(CORPUS_LOGS))
    for fn in sorted(os.listdir(logdir)):
        m = pat.match(fn)
        if not m:
            continue
        rows = {}
        with open(os.path.join(logdir, fn), encoding="utf-8",
                  errors="replace") as fh:
            for line in fh:
                got = parse_corpus_row(line)
                if got:
                    rows[got[0]] = (got[1], got[2])
        out[m.group(1)][int(m.group(2))] = rows
    return out


def unconclusive_rows(root=ROOT):
    """prefix -> {round: [checker]} for rows that are neither red nor green.

    The corpus analogue of `could_not_run`, one granularity finer: there the
    whole log failed to report, here one row of it did.
    """
    out = {}
    for prefix, per_round in corpus_rows(root).items():
        out[prefix] = {r: sorted(c for c, (st, _co) in rows.items()
                                 if st not in CONCLUSIVE)
                       for r, rows in per_round.items()
                       if any(st not in CONCLUSIVE for st, _co in rows.values())}
    return out


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


def driver_bad_rounds(root=ROOT):
    """check label -> set(round) the driver called FAIL or ERROR.

    `driver_verdicts` counts; this names the rounds, which is what a set
    reconciliation against the per-round logs needs.
    """
    out = {v: set() for v in CHECK_LABEL.values()}
    path = os.path.join(root, "logs", "driver.log")
    if not os.path.exists(path):
        return out
    labels = sorted(CHECK_LABEL.values(), key=len, reverse=True)
    pat = re.compile(r"round (\d+): (%s) (FAIL|ERROR)"
                     % "|".join(re.escape(x) for x in labels))
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = pat.search(line)
            if m:
                out[m.group(2)].add(int(m.group(1)))
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


# ---------------------------------------------------------------------------
# Round 467 (SWE-loop D). WHAT DECIDED THE LABEL, AND WHEN COULD ANYONE TELL.
#
# Two of round 461's next-steps, and they turn out to be the same worry seen
# from two ends.
#
# Item 2 -- THE ONE-ROUND LAG. A fail-closed registry cannot fire in the round
# that breaks it: the evidence it reads is `logs/<check>_round_<N>.log`, and
# round N's copy is written by the run the assertion is part of. So R001 always
# names a node opened by an EARLIER round while running inside a later one, and
# the message said neither. `first_firable_round` is the earliest run of that
# node's own check that could have seen the red, and the message now says both
# numbers out loud so no future R001 misattributes itself to its reader.
#
# Item 3 of this round's own list -- WHAT DECIDED THE SCOPE. The invisible-open
# rate and its p-value are computed over `subject_scope`, so a scope read off
# the episode outcomes it is later used to explain is circular. `evidence` says
# which, R005 makes it mandatory and R006 pins the one legitimate case: an
# outcome-derived label may only be `environmental`, and `environmental` may
# only be outcome-derived, because flakiness is invisible in a subject and a
# subject is not evidence of flakiness.
EVIDENCE_KINDS = ("subject", "outcome")


def first_firable(open_round, runs, nodeid, obs):
    """Earliest run of the node's own check that could have SEEN `open_round`.

    The next round in that node's own observed run order. `None` means no
    later run exists yet -- the red is still invisible to every check that
    has ever run, which is the state a round's own uncommitted breakage is in.
    """
    suite = node_suite(nodeid)
    prefix = next((p for p, (_r, sui) in CHECKS.items() if sui == suite), None)
    if prefix is None:
        return None
    po = (obs or {}).get(prefix)
    order = [r for r in sorted(runs.get(prefix, {}))
             if po is None or nodeid in po.get(r, frozenset())]
    return next((r for r in order if r > open_round), None)


def _r001_message(open_round, open_track, firable):
    return ("went red and has no registry entry -- FIRST RED in round %s's log "
            "(%s), and the earliest run that could have seen it is round %s, so "
            "the round reading this failure is not the round that caused it"
            % (open_round, open_track or "track unknown",
               firable if firable is not None else "none yet"))


def analyse(root=ROOT):
    reg = load_registry(root)
    track_suites = reg["_track_suites"]
    scopes = set(reg["_subject_scope"])
    nodes_reg = reg["nodes"]
    tracks = round_tracks(root)
    runs = read_logs(root)
    obs = observed_nodes(root)

    seen = {}          # nodeid -> set(rounds red)
    for prefix, per_round in runs.items():
        for rnd, failed in per_round.items():
            for nid in failed:
                seen.setdefault(nid, set()).add(rnd)

    findings = []
    for nid in sorted(seen):
        if nid not in nodes_reg:
            first = min(seen[nid])
            firable = first_firable(first, runs, nid, obs)
            findings.append(("R001", nid, _r001_message(first, tracks.get(first),
                                                        firable)))
    for nid, ent in sorted(nodes_reg.items()):
        if nid not in seen:
            findings.append(("R002", nid, "registry entry for a node that never went red"))
        if ent.get("subject_scope") not in scopes:
            findings.append(("R003", nid, "unknown subject_scope %r"
                             % ent.get("subject_scope")))
        ev = ent.get("evidence")
        if ev not in EVIDENCE_KINDS:
            findings.append(("R005", nid, "evidence %r is not one of %s -- say "
                             "what decided this scope before the headline is "
                             "computed over it" % (ev, list(EVIDENCE_KINDS))))
        elif (ev == "outcome") != (ent.get("subject_scope") == "environmental"):
            findings.append(("R006", nid,
                             "evidence %r with subject_scope %r -- an "
                             "outcome-derived label is circular unless the "
                             "scope IS about outcomes (`environmental`), and "
                             "`environmental` cannot be read off a subject"
                             % (ev, ent.get("subject_scope"))))

    node_rows, ep_rows = [], []
    for nid in sorted(seen):
        suite = node_suite(nid)
        prefix = next((p for p, (_r, s) in CHECKS.items() if s == suite), None)
        if prefix is None:
            continue
        po = obs.get(prefix)
        order = [r for r in sorted(runs[prefix])
                 if po is None or nid in po.get(r, frozenset())]
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
                "scope": scope,
                "evidence": nodes_reg.get(nid, {}).get("evidence", "UNDECLARED"), "open": e["open"], "open_track": opener,
                "len": len(e["rounds"]), "close": e.get("close"),
                "close_track": tracks.get(e.get("close")),
                "born_red": born,
                "opened_by_log_round": e["open"],
                "first_firable_round": next((r for r in order if r > e["open"]),
                                            None),
                "opened_by_owner": (not born) and opener == SUITE_OWNER.get(suite),
                "visible_to_opener": (not born) and bool(visible),
            })
        node_rows.append({
            "node": nid, "suite": suite, "owner": SUITE_OWNER.get(suite),
            "scope": scope,
            "evidence": nodes_reg.get(nid, {}).get("evidence", "UNDECLARED"), "red_rounds": sorted(seen[nid]),
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
    unconc = unconclusive_rows(root)
    dv = driver_verdicts(root)
    bad_rounds = driver_bad_rounds(root)
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

    # The parse, reconciled against the driver's own verdict, ROUND BY ROUND.
    #
    # Round 455 did this with counts and an ADDITION:
    # `len(parsed_red) + len(unrunnable & driver_bad)`. Round 461's corpus
    # grammar breaks that arithmetic on real data -- skills-check round 431
    # has both an `ERROR K001` row and a `TIMEOUT` row, so it is red AND
    # unrunnable, and the sum counts it twice. A union cannot double-count
    # and reduces to the sum whenever the two are disjoint, which is why the
    # pytest checks never noticed. The same defect was latent there: a pytest
    # suite killed after printing one `FAILED` line lands in both sets too.
    recon = OrderedDict()
    for prefix, (_rel, suite) in CHECKS.items():
        label = CHECK_LABEL[prefix]
        have = set(runs[prefix])
        parsed_red = {r for r, nodes in runs[prefix].items()
                      if any(node_suite(n) == suite for n in nodes)}
        unrunnable = (set(cnr.get(prefix, ())) if prefix in PYTEST_LOGS
                      else set(unconc.get(prefix, ())))
        bad = bad_rounds[label] & have
        accounted = parsed_red | (unrunnable & bad)
        recon[label] = {
            "parsed_red_runs": len(parsed_red),
            "unconclusive_runs": len(unrunnable),
            "driver_bad_runs": len(bad),
            "driver_bad_rounds_with_no_log": sorted(bad_rounds[label] - have),
            "accounted": len(accounted),
            "agrees": accounted == bad,
            "unexplained": sorted(bad ^ accounted),
        }

    return {
        "could_not_run": cnr,
        "unconclusive_rows": unconc,
        "reconciliation": recon,
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
    if t["logs_read"] < MIN_EVIDENCE_LOGS:
        print("\nNO EVIDENCE BASE  this checkout holds %d per-round log(s), "
              "below the floor of %d." % (t["logs_read"], MIN_EVIDENCE_LOGS))
        print("                  `logs/*_round_*.log` is gitignored (.gitignore "
              "28, 29, 35, 60), so a")
        print("                  fresh clone or a pristine worktree cannot "
              "reproduce this module.")
        print("                  Every number below is about this directory, "
              "not about the program.")
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
    unc = {k: v for k, v in res["unconclusive_rows"].items() if v}
    if unc:
        print("\nUNCONCLUSIVE ROWS (the checker was killed or absent -- not "
              "green, not red):")
        for k, v in unc.items():
            for rnd in sorted(v):
                print("  %-21s round %s: %s" % (CHECK_LABEL[k], rnd,
                                                ",".join(v[rnd])))
    print("\nPARSE RECONCILED AGAINST driver.log, round by round:")
    hdr2 = ("%-21s %10s %12s %11s %10s %8s"
            % ("check", "red runs", "unconclusive", "driver bad",
               "accounted", "agrees"))
    print(hdr2); print("-" * len(hdr2))
    for label, v in res["reconciliation"].items():
        print("%-21s %10d %12d %11d %10d %8s"
              % (label, v["parsed_red_runs"], v["unconclusive_runs"],
                 v["driver_bad_runs"], v["accounted"],
                 "yes" if v["agrees"] else "NO %s" % v["unexplained"]))
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


# ---------------------------------------------------------------------------
# Round 463 (harness A). WHAT A RED ROW LEAVES BEHIND.
#
# Round 461's next-step 1 named the reddest node in this whole measurement --
# `unit_tests`, 26 of the 65 red checker rows -- and the reason nothing can
# say anything about it: `corpus_check.run_one` unlinked its output on every
# branch. Round 463 made a NOT-CLEAN checker keep its own output under
# `logs/corpus-evidence/round-<N>/<check>.out`.
#
# This command is the reader. It exists as much for the number it CANNOT
# produce as for the one it can: retention starts at the round that landed
# it, so every red row before that is unrecoverable BY CONSTRUCTION and the
# recovery rate must be reported against the whole history rather than
# against the rounds that happen to have files. A rate computed over "rounds
# with evidence" would be 100% on its first day and would say nothing.
EVIDENCE_DIRNAME = "corpus-evidence"
EVIDENCE_ROUND_RE = re.compile(r"^round-(\d+)$")


def evidence_index(root=ROOT):
    """{round: {checker: path}} over `logs/corpus-evidence/round-*/*.out`."""
    base = os.path.join(root, "logs", EVIDENCE_DIRNAME)
    out = {}
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        m = EVIDENCE_ROUND_RE.match(name)
        if not m:
            continue
        d = os.path.join(base, name)
        if not os.path.isdir(d):
            continue
        per = {}
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".out"):
                per[fn[:-len(".out")]] = os.path.join(d, fn)
        if per:
            out[int(m.group(1))] = per
    return out


#: The same shape `corpus_check.FAILED_NODE_RE` writes. Duplicated rather
#: than imported: this module is `harness/` and that one is `skills/`, the
#: two are read by different tracks, and `test_the_two_node_id_patterns_agree`
#: pins them together so the duplication cannot drift silently.
EVIDENCE_FAILED_RE = re.compile(r"^(?:FAILED|ERROR) (\S+\.py(?:::\S+)?)", re.M)


def nodes_in_evidence(path):
    """Ordered pytest node ids a retained evidence file names as failing."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:                                        # pragma: no cover
        return []
    seen, order = set(), []
    for nid in EVIDENCE_FAILED_RE.findall(text):
        if nid not in seen:
            seen.add(nid)
            order.append(nid)
    return order


def evidence_report(root=ROOT):
    """Every NOT-CONCLUSIVE-GREEN corpus row against the evidence it left."""
    rows = corpus_rows(root)["skills_health_round"]
    index = evidence_index(root)
    items = []
    for rnd in sorted(rows):
        for checker, (status, codes) in sorted(rows[rnd].items()):
            # The denominator is the RETENTION PREDICATE, not "not green".
            # `corpus_check._attach_evidence` keeps a run whose rc is
            # non-zero or whose errors are non-empty, and an `ABSENT` row
            # never had a child to keep output from. Counting every not-green
            # row would manufacture a permanent shortfall out of rows the
            # mechanism is not answerable for -- the mirror image of the
            # borrowed-code defect round 463 fixed one file over.
            #
            # A `warn` row is USUALLY clean (rc 0, no errors) and so is
            # usually excluded -- but not always, and round 463 found that
            # out by running the thing: `checks()` passes `--strict` to
            # `skill_lint`, which exits 1 on a WARNING, so a `warn B002` row
            # is rc 1 and DOES retain. The rule is therefore "ERROR/TIMEOUT,
            # or anything that actually left a file". Never orphan a retained
            # file from the report that counts retentions.
            path = index.get(rnd, {}).get(checker)
            if status not in ("ERROR", "TIMEOUT") and not path:
                continue
            items.append({
                "round": rnd, "checker": checker, "status": status,
                "codes": codes, "evidence": path,
                "nodes": nodes_in_evidence(path) if path else [],
            })
    covered = [i for i in items if i["evidence"]]
    first = min(index) if index else None
    return {
        "items": items,
        "n_rows": len(items),
        "n_with_evidence": len(covered),
        "first_retained_round": first,
        "rounds_observed": sorted(rows),
        # The honest denominator split. Rows BEFORE retention existed are not
        # a recall failure of anything -- they are the loss this round stopped
        # -- and rows after it are the only ones the mechanism is answerable
        # for.
        "n_before_retention": sum(1 for i in items
                                  if first is None or i["round"] < first),
        "n_since_retention": sum(1 for i in items
                                 if first is not None and i["round"] >= first),
        "n_since_retention_covered": sum(
            1 for i in covered if first is not None and i["round"] >= first),
    }


def cmd_evidence(args):
    rep = evidence_report()
    if args.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0
    for i in rep["items"]:
        if args.only_missing and i["evidence"]:
            continue
        mark = "EVIDENCE" if i["evidence"] else "lost"
        print("round %-4d %-18s %-8s %-22s %s"
              % (i["round"], i["checker"], i["status"], i["codes"] or "-",
                 mark))
        for nid in i["nodes"][:args.nodes]:
            print("%18s%s" % ("", nid))
        if len(i["nodes"]) > args.nodes:
            print("%18s(+%d more)" % ("", len(i["nodes"]) - args.nodes))
    first = rep["first_retained_round"]
    print("\ncorpus-evidence: %d not-green row(s) over rounds %s-%s; "
          "%d carry a retained file"
          % (rep["n_rows"], rep["rounds_observed"][0] if rep["rounds_observed"]
             else "-", rep["rounds_observed"][-1] if rep["rounds_observed"]
             else "-", rep["n_with_evidence"]))
    if first is None:
        print("corpus-evidence: retention has never run — every row above is "
              "unrecoverable, which is the state round 461's item 1 "
              "described")
        return 0
    print("corpus-evidence: retention starts at round %d — %d row(s) predate "
          "it and are unrecoverable BY CONSTRUCTION, not by omission; "
          "%d of %d row(s) since are covered"
          % (first, rep["n_before_retention"],
             rep["n_since_retention_covered"], rep["n_since_retention"]))
    return 0


# ---------------------------------------------------------------------------
# Round 467 (SWE-loop D). THE HEADLINE'S OWN P-VALUE.
#
# Round 461's next-step 6, in full: "Do not read the p-value as a significance
# test. 46 of the 78 attributable episodes come from one runner and are not
# independent -- 11 rounds open episodes on two or three checkers at once.
# `p = 9.81e-08` is the direction, stated with a number that is narrower than
# the data earns. Whoever quotes it should quote the caveat with it, or
# compute a round-clustered version."
#
# Three things were wrong with the situation, not one.
#
# (1) NOTHING IN THE TREE COMPUTED IT. `9.81e-08` is published in
#     `knowledge/round-461-*.md` and in `skills/unrun-checker-latency/
#     SKILL.md` and was produced by a scratch calculation in the round that
#     wrote them. A number with no producer cannot be re-derived, so
#     `fisher_exact_2x2` is here and `test_the_published_p_values_are_
#     reproduced` pins it against BOTH previously published tables.
#
# (2) THE CLUSTERING IS REAL and it is two-fold, not one-fold: one ROUND opens
#     several episodes at once (round clustering) and one NODE contributes
#     many episodes across rounds (node clustering, `unit_tests` alone is 27).
#     `collapse_by_node` and `node_scope_null` answer the second;
#     `rotation_shift_null` answers the first.
#
# (3) AND THE NULL MATTERS MORE THAN THE CLUSTERING. A round's TRACK is not a
#     free parameter: `run_driver.sh` assigns it by round number mod 6. Round
#     466 (NUC E) measured the same lesson on a different subject and wrote it
#     down as `skills/null-must-preserve-the-shape` -- a uniform-placement
#     null over a bursty population graded a real effect as below chance,
#     while a circular-shift null that preserved the population's cadence gave
#     p <= 0.0005. The shape here is the rotation, so the null that preserves
#     it is a rigid rotation of the round -> track map. That null has only
#     SIX distinct members, so the smallest p it can return is 1/6 -- a fact
#     about the design, not about the data, and one no amount of extra rounds
#     will move.
#
# The `own-suite` row deserves its own warning, printed with the table. Read
# `_subject_scope`'s text for it: "the hosting track is the only track that
# can open it, AND CAN SEE IT by running its own fast tier". The conclusion is
# inside the definition. A 2x2 of whole-tree against own-suite therefore tests
# an association one of whose rows is analytic, which is why `scope-test`
# prints the whole-tree rate against the rotation's own base rate as well --
# that comparison has no such row.
SCOPE_TEST_ROWS = ("whole-tree", "own-suite")

#: The two tables this module must reproduce before its new numbers are worth
#: anything: (label, a, b, c, d, published p). Cells are
#: (row-invisible, row-visible) for whole-tree then own-suite.
PUBLISHED_TABLES = (
    ("round 455", 12, 4, 1, 8, 0.0036),
    ("round 461", 53, 4, 0, 8, 9.81e-08),
)


def fisher_exact_2x2(a, b, c, d):
    """Two-sided Fisher exact p for [[a, b], [c, d]].

    Sums the hypergeometric probability of every table with the same margins
    whose probability does not exceed the observed one. Exact integer
    binomials, so no lgamma cancellation to argue about at these sizes.
    """
    n = a + b + c + d
    if n == 0:
        return None
    r1, r2, c1 = a + b, c + d, a + c
    denom = math.comb(n, c1)

    def prob(x):
        return math.comb(r1, x) * math.comb(r2, c1 - x) / denom

    lo, hi = max(0, c1 - r2), min(r1, c1)
    p_obs = prob(a)
    tol = p_obs * (1 + 1e-9)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= tol))


def _visible(track, suite, track_suites):
    return bool(track) and suite in track_suites.get(track, ())


def _table(eps, rows=SCOPE_TEST_ROWS):
    """(a, b, c, d) = (row0 invisible, row0 visible, row1 invisible, row1 visible)."""
    out = []
    for sc in rows:
        sel = [e for e in eps if e["scope"] == sc]
        out.append(sum(1 for e in sel if not e["vis"]))
        out.append(sum(1 for e in sel if e["vis"]))
    return tuple(out)


def _stat(table):
    """Difference in invisible RATE between the two rows; None if a row is empty."""
    a, b, c, d = table
    if a + b == 0 or c + d == 0:
        return None
    return a / (a + b) - c / (c + d)


def scope_test_episodes(res, track_suites):
    """The episodes the association may honestly be computed over.

    Attributable (somebody opened it), and SUBJECT-derived (R006 already
    guarantees that excludes exactly the `environmental` rows, whose label was
    read off the verdict history the test would then explain).
    """
    return [{"node": e["node"], "suite": e["suite"], "scope": e["scope"],
             "open": e["open"], "vis": e["visible_to_opener"]}
            for e in res["episodes"]
            if not e["born_red"] and e["evidence"] == "subject"]


#: `run_driver.sh` picks a round's track by round number mod 6 (CLAUDE.md
#: ground rule 6). This is the SHAPE any null over track labels must preserve.
ROTATION_PERIOD = 6


def rotation_residue_map(tracks, period=ROTATION_PERIOD):
    """({residue: track}, [complaint]) over the driver's own `start` lines.

    Derived from the record, never from CLAUDE.md, so a driver that stopped
    obeying its own rule shows up here as a complaint instead of being
    papered over by the constant it was supposed to follow.
    """
    by_res = OrderedDict()
    for rnd, track in sorted(tracks.items()):
        by_res.setdefault(rnd % period, Counter())[track] += 1
    rot, problems = OrderedDict(), []
    for res in sorted(by_res):
        counts = by_res[res]
        rot[res] = counts.most_common(1)[0][0]
        if len(counts) > 1:
            problems.append("residue %d ran %s" % (res, dict(counts)))
    missing = [r for r in range(period) if r not in rot]
    if missing:
        problems.append("no round observed for residue(s) %s" % missing)
    return rot, problems


def rotation_shift_null(eps, tracks, track_suites, statfn=None,
                        period=ROTATION_PERIOD):
    """Rigidly rotate the driver's ROUND-NUMBER -> track rule; recompute.

    Preserves every structural fact except the alignment between which track
    ran and which node broke: the rounds, their order, each round's set of
    opened episodes, each node's scope, the rotation's period, and the exact
    multiset of track labels. Destroys only WHICH residue got which label.

    A DEFECT THIS FUNCTION HAD, kept in the record because the number that
    exposed it is the whole point. The first draft rotated the SEQUENCE of
    observed labels by position -- `labels[(i + k) % n]` -- which sounds
    identical and is not. `logs/driver.log` has no `start` line for rounds
    229 and 313, so the observed sequence is 314 long over a 316-round span:
    rotating it by position slides the labels ACROSS those two holes and
    changes phase halfway through, manufacturing relabelings in which the
    rotation is no longer period-6 at all. It reported 188 distinct
    relabelings of 314 shifts and p = 0.0796. That is round 466's
    `skills/null-must-preserve-the-shape` failing on the round that cited it:
    the shape here is `track = f(round mod 6)`, and a positional rotation is
    not a symmetry of it. Shifting the RESIDUE is, and gives exactly `period`
    members -- which is also why `floor` below is 1/6 and not something a
    larger corpus could improve.

    `statfn` maps a list of episodes (each with `scope` and `vis`) to a float;
    the default is the two-row rate difference, and `cmd_scope_test` also runs
    it over a one-row statistic that has no analytic row in it.
    """
    statfn = statfn or (lambda e: _stat(_table(e)))
    rot, problems = rotation_residue_map(tracks, period)
    obs = statfn(eps)
    stats, seen = [], {}
    for k in range(period):
        mapping = {r: rot[(r + k) % period] for r in rot}
        key = tuple(mapping[e["open"] % period] for e in eps)
        shifted = [dict(e, vis=_visible(mapping[e["open"] % period], e["suite"],
                                        track_suites)) for e in eps]
        stats.append(statfn(shifted))
        seen.setdefault(key, k)
    live = [st for st in stats if st is not None]
    ge = sum(1 for st in stats if st is not None and obs is not None
             and st >= obs - 1e-12)
    return {
        "observed": obs,
        "period": period,
        "shifts": period,
        "distinct_relabelings": len(seen),
        "n_ge_observed": ge,
        "p": ge / period,
        "floor": 1.0 / len(seen) if seen else None,
        "null_mean": (sum(live) / len(live)) if live else None,
        "null_max": max(live) if live else None,
        "null_values": [None if st is None else round(st, 4) for st in stats],
        "rotation": {str(k): v for k, v in rot.items()},
        "rotation_problems": problems,
        "degenerate_shifts": len(stats) - len(live),
    }


def whole_tree_invisible_rate(eps, scope=SCOPE_TEST_ROWS[0]):
    """The one-row statistic: share of `scope`'s episodes opened invisibly.

    `own-suite`'s registry definition says the hosting track "can see it by
    running its own fast tier", so a 2x2 against it has an analytic row. This
    statistic has none: it is one scope's rate, and the rotation-shift null
    supplies the only baseline it needs.
    """
    sel = [e for e in eps if e["scope"] == scope]
    if not sel:
        return None
    return sum(1 for e in sel if not e["vis"]) / len(sel)

def node_scope_null(eps, draws=20000, seed=467):
    """Permute `subject_scope` across NODES, not across episodes.

    The other half of the clustering. Every episode of one node shares that
    node's label, so shuffling at episode level would break exactly the
    dependence the test is trying to respect. This keeps each node's episode
    count, each round's co-occurrences and the observed visibility of every
    episode untouched, and moves only which node carries which scope.

    Reported, never predicted: round 467's predictions file declares this one
    no-basis on purpose.
    """
    obs = _stat(_table(eps))
    by_node = OrderedDict()
    for e in eps:
        by_node.setdefault(e["node"], []).append(e)
    names = list(by_node)
    scopes = [by_node[n][0]["scope"] for n in names]
    rng = random.Random(seed)
    ge = 0
    live = []
    for _ in range(draws):
        rng.shuffle(scopes)
        relab = [dict(e, scope=scopes[i])
                 for i, n in enumerate(names) for e in by_node[n]]
        st = _stat(_table(relab))
        if st is None:
            continue
        live.append(st)
        if obs is not None and st >= obs - 1e-12:
            ge += 1
    return {
        "observed": obs, "draws": draws, "seed": seed,
        "usable_draws": len(live), "n_ge_observed": ge,
        "p": (ge + 1) / (len(live) + 1) if live else None,
        "null_mean": (sum(live) / len(live)) if live else None,
        "nodes": len(names),
    }


def collapse_by_node(eps, rows=SCOPE_TEST_ROWS):
    """One row per NODE: was it EVER opened by a round that could not see it.

    The most conservative reading of the same claim. It answers the node
    clustering by refusing to count `unit_tests` twenty-seven times.
    """
    by_node = OrderedDict()
    for e in eps:
        by_node.setdefault(e["node"], []).append(e)
    collapsed = [{"node": n, "scope": v[0]["scope"],
                  "vis": all(x["vis"] for x in v)}
                 for n, v in by_node.items()]
    return _table(collapsed, rows), collapsed


def rotation_base_rate(eps, tracks, track_suites, rows=SCOPE_TEST_ROWS):
    """For each scope: the visible rate the ROTATION ALONE would produce.

    The comparison that has no analytic row. Under the driver's rotation a
    node in `harness/tests` is visible to 2 of the 6 slots (harness(A) and
    SWE-loop(D)); one in `skills/` to 1 of 6. So a scope's expected visible
    rate under `nobody's breakage is aimed at anything` is the mean over its
    episodes of |{slots that see this suite}| / 6, and the interesting
    quantity is how far the OBSERVED rate sits from it.
    """
    slots = sorted({tracks[r] for r in tracks})
    out = OrderedDict()
    for sc in rows:
        sel = [e for e in eps if e["scope"] == sc]
        if not sel:
            continue
        exp = sum(sum(1 for t in slots if _visible(t, e["suite"], track_suites))
                  / len(slots) for e in sel) / len(sel)
        out[sc] = {"episodes": len(sel),
                   "observed_visible_rate": sum(1 for e in sel if e["vis"]) / len(sel),
                   "rotation_expected_visible_rate": exp}
    return out


def scope_test(root=ROOT, draws=20000, seed=467):
    res = analyse(root)
    reg = load_registry(root)
    track_suites = reg["_track_suites"]
    tracks = round_tracks(root)
    eps = scope_test_episodes(res, track_suites)
    table = _table(eps)
    ntab, collapsed = collapse_by_node(eps)
    return {
        "rows": list(SCOPE_TEST_ROWS),
        "episodes_used": len(eps),
        "episodes_excluded_outcome_derived": sum(
            1 for e in res["episodes"]
            if not e["born_red"] and e["evidence"] != "subject"),
        "episode_table": list(table),
        "episode_p_naive": fisher_exact_2x2(*table),
        "node_table": list(ntab),
        "nodes_used": len(collapsed),
        "node_p": fisher_exact_2x2(*ntab),
        "rotation_shift_null": rotation_shift_null(eps, tracks, track_suites),
        "whole_tree_only_shift_null": rotation_shift_null(
            eps, tracks, track_suites, statfn=whole_tree_invisible_rate),
        "node_scope_null": node_scope_null(eps, draws=draws, seed=seed),
        "rotation_base_rate": rotation_base_rate(eps, tracks, track_suites),
        "reproduces_published": [
            {"label": lab, "table": [a, b, c, d], "published": pub,
             "recomputed": fisher_exact_2x2(a, b, c, d)}
            for lab, a, b, c, d, pub in PUBLISHED_TABLES],
    }


def cmd_scope_test(args):
    r = scope_test(draws=args.draws)
    if args.json:
        print(json.dumps(r, indent=2, sort_keys=True))
        return 0
    a, b, c, d = r["episode_table"]
    print("scope-test: does `subject_scope` predict an invisible open?")
    print("  %d subject-derived attributable episode(s); %d outcome-derived "
          "episode(s) EXCLUDED" % (r["episodes_used"],
                                   r["episodes_excluded_outcome_derived"]))
    print()
    print("%-14s %11s %9s %8s" % ("scope", "invisible", "visible", "rate"))
    print("%-14s %11d %9d %8.0f%%" % (SCOPE_TEST_ROWS[0], a, b, 100 * a / (a + b)))
    print("%-14s %11d %9d %8.0f%%" % (SCOPE_TEST_ROWS[1], c, d,
                                      100 * c / (c + d) if c + d else 0))
    print()
    print("  1. naive Fisher over EPISODES      p = %.3g   <- what is published"
          % r["episode_p_naive"])
    na, nb, nc, nd = r["node_table"]
    print("     (this treats %d episodes as %d independent observations)"
          % (r["episodes_used"], r["episodes_used"]))
    print("  2. collapsed to ONE ROW PER NODE   p = %.3g   [[%d,%d],[%d,%d]], "
          "n = %d node(s)" % (r["node_p"], na, nb, nc, nd, r["nodes_used"]))
    sh = r["rotation_shift_null"]
    print("  3. rotation-shift null             p = %.3g   %d of %d shift(s) "
          ">= observed" % (sh["p"], sh["n_ge_observed"], sh["shifts"]))
    print("     the driver picks a track by round mod %d, so the null has %d "
          "member(s)," % (sh["period"], sh["distinct_relabelings"]))
    print("     one of them the identity: it CANNOT return below %.3g, and no "
          "amount of" % sh["floor"])
    print("     further rounds will change that. observed %.3f, null mean "
          "%.3f, max %.3f" % (sh["observed"], sh["null_mean"], sh["null_max"]))
    print("     null values by shift: %s" % (sh["null_values"],))
    if sh["rotation_problems"]:
        print("     ROTATION NOT RIGID: %s" % "; ".join(sh["rotation_problems"]))
    ns = r["node_scope_null"]
    print("  4. node-scope permutation null     p = %.3g   %d of %d draw(s) "
          ">= observed" % (ns["p"], ns["n_ge_observed"], ns["usable_draws"]))
    print("     scope labels shuffled across %d node(s), seed %d; every node's "
          "episode" % (ns["nodes"], ns["seed"]))
    print("     count and every round's co-occurrences are preserved exactly.")
    print()
    print("READ (1) AS A DIRECTION, NOT A SIGNIFICANCE TEST. `own-suite`'s own")
    print("definition in the registry says the hosting track `can see it by")
    print("running its own fast tier`, so that row of the 2x2 is analytic.")
    print("The comparison with no analytic row is the rotation's base rate:")
    print()
    print("%-14s %9s %10s %10s" % ("scope", "episodes", "observed", "rotation"))
    for sc, v in r["rotation_base_rate"].items():
        print("%-14s %9d %9.0f%% %9.0f%%   visible"
              % (sc, v["episodes"], 100 * v["observed_visible_rate"],
                 100 * v["rotation_expected_visible_rate"]))
    wt = r["whole_tree_only_shift_null"]
    print()
    print("  5. the SAME shift null over `%s` ALONE (no second row,"
          % SCOPE_TEST_ROWS[0])
    print("     nothing analytic in it):        p = %.3g   observed %.0f%% "
          "invisible," % (wt["p"], 100 * wt["observed"]))
    print("     null mean %.0f%%, values by shift %s"
          % (100 * wt["null_mean"], wt["null_values"]))
    print()
    print("REPRODUCTION OF THE PUBLISHED NUMBERS (this table is the reason the")
    print("new ones above are worth reading):")
    for x in r["reproduces_published"]:
        print("  %-10s %-18s published %-10.3g recomputed %-10.3g  %s"
              % (x["label"], x["table"], x["published"], x["recomputed"],
                 "agree" if abs(x["recomputed"] - x["published"])
                 <= 0.005 * max(x["published"], 1e-12) + 5e-5 else "DISAGREE"))
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
    st = sub.add_parser("scope-test")
    st.add_argument("--json", action="store_true")
    st.add_argument("--draws", type=int, default=20000,
                    help="draws for the node-scope permutation null")
    st.set_defaults(fn=cmd_scope_test)
    e = sub.add_parser("evidence")
    e.add_argument("--json", action="store_true")
    e.add_argument("--only-missing", action="store_true",
                   help="print only the rows with no retained file")
    e.add_argument("--nodes", type=int, default=5,
                   help="how many failing node ids to print per row")
    e.set_defaults(fn=cmd_evidence)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not getattr(args, "fn", None):
        build_parser().print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

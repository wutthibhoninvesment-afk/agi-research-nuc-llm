#!/usr/bin/env python3
"""redcause.py — which red is a red ABOUT another red, read out of the body.

Round 511 (harness A).

THE OBSERVATION THIS ROUND STARTED FROM. The RED DEBT block handed harness(A)
two nodes:

    harness/tests/test_redattrib.py::TestThisTree::test_the_cli_audit_exits_zero_on_this_tree
    harness/tests/test_redattrib.py::TestThisTree::test_the_registry_is_fail_closed_over_the_live_logs

RECURRENT, five earlier episodes, re-opened at round 510 by language(C).
Reproduced solo (`2 failed, 58 passed in 2.87s`) so it is the code and not the
one-CPU runner. But the "code" it is about is not harness code and round 510
did not touch any: both nodes assert that
`harness/crosstrack-registry.json` classifies every node that has EVER gone
red, and round 510's whence suite put three new node ids into
`logs/whence_health_round_510.log`. The harness nodes are red because a
whence node is red.

That is a second kind of debt, and nothing in this program could say so.
`redattrib.read_logs` (round 455) reads exactly one thing out of a health
log — the `^FAILED <nodeid>` lines. `reddebt.debt` (round 493) consumes that
set. `readset.py` (round 505) works from a working-tree diff. Across three
instruments and 778 retained logs, **the failure BODY has never been parsed
by anything**, and the body is where the causal edge is written down: R001's
message, since round 467, literally reads

    R001  languages/whence/tests/test_testcorpus_contributions.py::…:
    went red and has no registry entry -- FIRST RED in round 510's log
    (language(C)), and the earliest run that could have seen it is round
    none yet, so the round reading this failure is not the round that
    caused it

— cause, causing round, and causing track, in the retained corpus, unread.

WHAT THIS MODULE DOES. For every red (node, round) observation in a retained
pytest health log it finds that node's own failure block, extracts every
OTHER test node id the block names, keeps the ones that are themselves red
somewhere in the corpus, and calls the observation:

    DERIVED     its body names >=1 other node that has itself gone red
    PRIMARY     its body names no other red node
    UNRESOLVED  the `FAILED` line has no block this parser could resolve
    UNREADABLE  the check's log grammar retains no per-test body at all

THREE THINGS IT DELIBERATELY DOES NOT DO
----------------------------------------
1. **It does not add a fail-closed whole-tree gate.** That is not an
   oversight, it is this round's own finding applied to itself. Every red
   this module explains was manufactured by a whole-tree fail-closed
   assertion living in ONE track's suite: any track can turn it red, only
   the hosting track runs it, so the diagnosis lands on somebody who did not
   cause it, one round late, at rotation latency. Shipping another one would
   add a ninth episode to the very series being measured. `graph` and
   `check` are MEASUREMENTS and exit 0. The live test in
   `harness/tests/test_redcause.py` pins facts about the ALREADY-RETAINED
   corpus — rounds 460 through 510, which no future round can move — rather
   than a property of the newest log.

2. **It does not treat "names a node id" as proof.** A body may quote a node
   id that has never been red (a fixture name, a docstring, a nodeid built
   by a synthetic test). Such a reference is counted in `named_unred` and
   does NOT make the observation derived. The named node must itself appear
   in a `FAILED` line somewhere in the retained corpus.

3. **It does not fold an unreadable body into PRIMARY.** `skills-check`
   writes a checker/verdict table, not pytest output; round 461 established
   that WHICH tests failed inside a red `unit_tests` row is retained
   nowhere, for any round. Those observations are `UNREADABLE`, printed as a
   gap. A red whose body cannot be read has not been shown to be primary,
   and the difference between "no cause found" and "could not look" is the
   whole reason round 455's GRAMMAR GAP banner exists.

WHY IT IS WORTH A ROUND. A DERIVED red is not a defect in the suite that
hosts it, so every instruction the RED DEBT block gives about it is wrong for
it: "reproduce it before fixing it" reproduces fine and teaches nothing,
"owner harness(A)" points at a track with no defect, and the closing act is
not a code change at all but a DIAGNOSIS — five registry entries saying whose
work can turn each new node red. The two nodes above have seven prior
episodes, each re-diagnosed from scratch by whoever came next -- and it was
mostly NOT the owner. They closed in rounds 461, 467, 479, 487, 498, 504 and
509: SWE-loop(D) four times, language(C) twice, and harness(A), the track
that OWNS this suite, exactly once. The cause was in the log every time.

Commands
--------
    python3 harness/redcause.py graph [--json] [--check <label>]
        The cause table: per check, how many red observations are derived,
        primary, unresolved, unreadable, and the top causing nodes. Exit 0.

    python3 harness/redcause.py node <nodeid> [--json]
        Every red round of one node with the causes named in its body.

    python3 harness/redcause.py live [--json]
        The currently-red set (from `reddebt.debt`) with a DERIVED/PRIMARY
        verdict and, for the derived ones, the sentence that says where the
        fix actually is. This is what `reddebt.note` embeds.

    python3 harness/redcause.py check
        Parser health: how many red observations resolved to a body.
        A MEASUREMENT — exit 0 always. See note 1 above.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import redattrib as RA  # noqa: E402

#: A pytest section banner: `======= FAILURES =======`. `TerminalWriter.sep`
#: builds these as `fill + " " + title + " " + fill` with at least one fill
#: char on each side, so one `=` on each side is the floor and there is no
#: truncation of a long title.
SECTION = re.compile(r"^=+ (.+?) =+$")

#: The two sections that carry per-test bodies. `ERRORS` holds setup/teardown
#: failures, whose titles read `ERROR at setup of TestX.test_y`; those are
#: reported in `short test summary info` as `ERROR <nodeid>`, not `FAILED`,
#: so they are parsed for completeness and simply never resolve against the
#: FAILED set. Keeping them costs nothing and stops a future `FAILED` that
#: pytest happens to file under ERRORS from becoming an UNRESOLVED.
BODY_SECTIONS = ("FAILURES", "ERRORS")

#: One test's block header inside a body section, same `sep` shape with `_`.
BLOCK = re.compile(r"^_+ (.+?) _+$")

#: One `::`-separated segment of a node id: a class or test name, plus the
#: optional `[param]` of a parametrised node. `:` is deliberately NOT in the
#: class -- see NODEREF.
_SEG = r"[\w+=.-]+(?:\[[^\]\s]*\])?"

#: Any test-node-shaped token. Requires at least one `::`, which is what
#: separates a node id from the `path.py:LINENO:` form pytest prints for the
#: failing frame -- the body is full of the latter and none of it is a
#: reference.
#:
#: THE `:` TRAP, and it cost this module its first two runs. Writing the id
#: part as one character class containing `:` (so that `File::Class::method`
#: matches) makes the class eat the SENTENCE punctuation as well, and R001's
#: own message is `<nodeid>: went red and has no registry entry`. Every one of
#: the 16 red rounds of `test_the_cli_audit_exits_zero_on_this_tree` then
#: yielded `…::selfdesc_check:` -- one character off a real node, resolving to
#: nothing, and the node was reported PRIMARY in all 16. Its sibling
#: `test_the_registry_is_fail_closed_over_the_live_logs` was DERIVED in all 16
#: from the SAME five findings, because unittest's list diff prints them
#: quoted and a quote is not in the class either. Two nodes, one cause, one
#: log, opposite verdicts, and the difference was punctuation. So the `::`
#: structure is spelled out instead, and a trailing `.` or `,` is stripped
#: after the match rather than admitted into it.
NODEREF = re.compile(r"[\w./+-]+\.py(?:::" + _SEG + r")+")

#: Sentence punctuation `_SEG` can legally end on but a node id cannot.
_TRAILING = ".,"

#: R001's dated edge (redattrib round 467). Groups: causing node, the round
#: whose log first carried it, the track that was running then.
#:
#: THE PARENTHESIS TRAP, found by this file's own first test run. The track
#: group was written `\(([^)]+)\)`, which is the reflex for "text in
#: brackets" and is wrong for EVERY track name in this program: they are
#: `harness(A)`, `language(C)`, `SWE-loop(D)`, `NUC-integration(E)`,
#: `skills(B)` -- each already containing a bracketed letter, so the lazy
#: class stopped at the inner `)` and yielded `SWE-loop(D`. Anchored on the
#: message's own trailing clause instead, which is a fixed string
#: `redattrib._r001_message` prints unconditionally.
DATED_EDGE = re.compile(
    r"R001\s+(\S+?):\s+went red and has no registry entry"
    r" -- FIRST RED in round (\d+)'s log \((.+?)\), and the earliest run")

DERIVED, PRIMARY, UNRESOLVED, UNREADABLE = (
    "derived", "primary", "unresolved", "unreadable")

#: THE AXIS THAT DECIDES WHETHER A DERIVED RED IS A PROBLEM (round 511).
#: Both shapes exist in this corpus and they are not the same event.
#:
#: SAME-LOG. Every node the body names is red in the SAME `(check, round)`
#: log. `nuc/tests/test_constant_audit.py::test_the_fast_check_runs_green_on_
#: this_tree` runs `nuc/run_checks_fast.sh` as a subprocess and asserts rc 0,
#: so its assertion message IS the nested suite's own FAILURES section. The
#: reader of that log sees the cause three lines further down under its own
#: `FAILED` line. Noisy -- one break reports as two -- but not invisible, and
#: nothing is lost by the time somebody reads it.
#:
#: CROSS-LOG. At least one named node is NOT red in this log. The node is
#: asserting over a corpus its own run does not contain: the RETAINED health
#: logs, i.e. other rounds and other checks. Then the cause can be GREEN
#: AGAIN by the time the host suite goes red -- which is the state at HEAD
#: right now, where `harness/tests/test_readset.py`'s two nodes closed in
#: round 510 and the harness red they caused is still open. The host's red is
#: then the only surviving trace of the cause, and the reader is a track with
#: no defect to find.
SAME_LOG, CROSS_LOG = "same-log", "cross-log"


def body_sections(text):
    """The lines of every FAILURES/ERRORS region of one pytest log.

    A region opens on its own banner and closes on the NEXT banner of any
    kind -- `warnings summary`, `short test summary info`, `PASSES` -- so a
    log with both sections yields both and nothing after either.
    """
    out, keep = [], False
    for line in text.splitlines():
        m = SECTION.match(line)
        if m:
            keep = m.group(1).strip() in BODY_SECTIONS
            continue
        if keep:
            out.append(line)
    return out


def blocks(text):
    """[(title, body)] for one pytest log, in file order.

    Lines before the first block header inside a region are dropped: pytest
    emits none, and inventing an owner for them would be guessing.
    """
    out, title, buf = [], None, []
    for line in body_sections(text):
        m = BLOCK.match(line)
        if m:
            if title is not None:
                out.append((title, "\n".join(buf)))
            title, buf = m.group(1).strip(), []
        elif title is not None:
            buf.append(line)
    if title is not None:
        out.append((title, "\n".join(buf)))
    return out


def title_for(nodeid):
    """The block header pytest writes for `nodeid`.

    `path.py::Class::test_x` -> `Class.test_x`; `path.py::test_x` ->
    `test_x`. Derived from the node id rather than matched loosely, so a
    title that does not resolve stays UNRESOLVED instead of being attached
    to the wrong test.
    """
    parts = nodeid.split("::")
    return ".".join(parts[1:]) if len(parts) > 1 else nodeid


def resolve_blocks(text, failed):
    """(nodeid -> body, [unresolved titles]) for one log.

    `failed` is the log's own `FAILED` node id set, ALREADY CANONICAL (that
    is, with the check's path root prefixed the way `redattrib.read_logs`
    prefixes it). A title claimed by two different failed nodes resolves to
    neither: an ambiguous body is not evidence about either of them.
    """
    want = {}
    for nid in failed:
        want.setdefault(title_for(nid), []).append(nid)
    got, unresolved = {}, []
    for title, body in blocks(text):
        cands = want.get(title)
        if not cands or len(cands) != 1:
            unresolved.append(title)
            continue
        got[cands[0]] = body
    return got, unresolved


def canonicalise(raw, rel, known):
    """A node id named inside a body, mapped into the canonical namespace.

    Bodies name ids two ways. `redattrib`'s own findings are already
    canonical (it prefixes before printing); a whence test naming a sibling
    writes it rootdir-relative, i.e. without the `languages/whence/` the
    canonical form carries. Both are tried, plus the reverse strip, and the
    first form that is a node this corpus has actually seen red wins.
    `None` means the reference is to something that never went red.
    """
    cands = [raw]
    if rel and rel != ".":
        cands.append("%s/%s" % (rel, raw))
        pre = rel.rstrip("/") + "/"
        if raw.startswith(pre):
            cands.append(raw[len(pre):])
    for c in cands:
        if c in known:
            return c
    return None


def named_in(body, selfid, rel, known):
    """(named_red, named_unred, dated) for one failure body.

    `named_red`   canonical ids of OTHER nodes the body names that have
                  themselves gone red somewhere in the retained corpus.
    `named_unred` raw ids the body names that resolve to no red node --
                  counted, never promoted, see module note 2.
    `dated`       [(node, round, track)] from R001's own message, the one
                  place a body states WHEN the cause opened.
    """
    red, unred = set(), set()
    for raw in NODEREF.findall(body):
        raw = raw.rstrip(_TRAILING)
        can = canonicalise(raw, rel, known)
        if can is None:
            unred.add(raw)
        elif can != selfid:
            red.add(can)
    dated = []
    for m in DATED_EDGE.finditer(body):
        can = canonicalise(m.group(1), rel, known)
        if can is not None and can != selfid:
            dated.append((can, int(m.group(2)), m.group(3)))
    return sorted(red), sorted(unred), dated


def read_bodies(root=ROOT):
    """prefix -> {round: (nodeid -> body, [unresolved titles])}.

    Only the pytest checks have bodies. `skills-check` is absent from the
    result entirely rather than present-and-empty, so a caller cannot
    mistake "this grammar has no bodies" for "this round had none".
    """
    out = {p: {} for p in RA.PYTEST_LOGS}
    logdir = os.path.join(root, "logs")
    if not os.path.isdir(logdir):
        return out
    pat = re.compile(r"^(%s)_(\d+)\.log$" % "|".join(RA.PYTEST_LOGS))
    for fn in sorted(os.listdir(logdir)):
        m = pat.match(fn)
        if not m:
            continue
        prefix, rnd = m.group(1), int(m.group(2))
        rel = RA.CHECKS[prefix][0]
        with open(os.path.join(logdir, fn), encoding="utf-8",
                  errors="replace") as fh:
            text = fh.read()
        failed = set()
        for nid in re.findall(r"^FAILED (\S+)", text, re.M):
            failed.add(nid if rel == "." else "%s/%s" % (rel, nid))
        if not failed:
            continue
        out[prefix][rnd] = resolve_blocks(text, failed)
    return out


def observations(root=ROOT):
    """One record per red (check, round, node) in the retained corpus.

    Fields: check, prefix, round, node, kind, causes, dated, named_unred,
    track (the round's own track, from driver.log).
    """
    runs = RA.read_logs(root)
    tracks = RA.round_tracks(root)
    bodies = read_bodies(root)
    known = {nid for per in runs.values() for s in per.values() for nid in s}
    rows = []
    for prefix, per_round in runs.items():
        rel = RA.CHECKS[prefix][0]
        readable = prefix in RA.PYTEST_LOGS
        for rnd in sorted(per_round):
            got, _unres = bodies.get(prefix, {}).get(rnd, ({}, []))
            for nid in sorted(per_round[rnd]):
                if not readable:
                    kind, causes, unred, dated = UNREADABLE, [], [], []
                elif nid not in got:
                    kind, causes, unred, dated = UNRESOLVED, [], [], []
                else:
                    causes, unred, dated = named_in(got[nid], nid, rel, known)
                    kind = DERIVED if causes else PRIMARY
                span = None
                if kind == DERIVED:
                    here = per_round[rnd]
                    span = (SAME_LOG if all(c in here for c in causes)
                            else CROSS_LOG)
                rows.append(OrderedDict([
                    ("check", RA.CHECK_LABEL[prefix]),
                    ("prefix", prefix),
                    ("round", rnd),
                    ("node", nid),
                    ("kind", kind),
                    ("span", span),
                    ("causes", causes),
                    ("dated", [list(d) for d in dated]),
                    ("named_unred", sorted(unred)),
                    ("track", tracks.get(rnd)),
                ]))
    rows.sort(key=lambda r: (r["prefix"], r["round"], r["node"]))
    return rows


def summarise(rows):
    """Aggregate counts, overall and per check, plus the cause histogram."""
    per = OrderedDict()
    for prefix in RA.CHECKS:
        per[RA.CHECK_LABEL[prefix]] = Counter()
    total = Counter()
    causes = Counter()
    spans = Counter()
    for r in rows:
        per[r["check"]][r["kind"]] += 1
        total[r["kind"]] += 1
        if r.get("span"):
            spans[r["span"]] += 1
            per[r["check"]][r["span"]] += 1
        for c in r["causes"]:
            causes[c] += 1
    n = sum(total.values())
    readable = total[DERIVED] + total[PRIMARY]
    return OrderedDict([
        ("n_observations", n),
        ("derived", total[DERIVED]),
        ("derived_same_log", spans[SAME_LOG]),
        ("derived_cross_log", spans[CROSS_LOG]),
        ("primary", total[PRIMARY]),
        ("unresolved", total[UNRESOLVED]),
        ("unreadable", total[UNREADABLE]),
        ("derived_share_of_all", (total[DERIVED] / n) if n else 0.0),
        ("derived_share_of_readable",
         (total[DERIVED] / readable) if readable else 0.0),
        ("per_check", {k: dict(v) for k, v in per.items()}),
        ("top_causes", causes.most_common(10)),
    ])


def latencies(rows):
    """[(derived node, derived round, cause node, cause round, gap)].

    Only the dated edges, i.e. the ones whose body states the causing round
    rather than leaving it to be joined. A negative gap would mean a body
    naming a red from a LATER round, which cannot happen and is reported
    rather than clamped.
    """
    out = []
    for r in rows:
        for node, rnd, _track in r["dated"]:
            out.append((r["node"], r["round"], node, rnd, r["round"] - rnd))
    return out


# ---------------------------------------------------------------------------
# The live view -- what `reddebt.note` embeds.

def live(root=ROOT, window=None):
    """The currently-red set with a cause verdict on each row.

    Imported lazily: `reddebt` imports THIS module for its note clause, and
    a module-level import in both directions is a cycle. The dependency is
    real in both directions and is broken here rather than by duplicating
    `debt()`'s episode logic, which is the drift round 493 built `debt` to
    avoid in the first place.
    """
    import reddebt as RD
    items = RD.debt(root) if window is None else RD.debt(root, window)
    rows = observations(root)
    by_key = {(r["prefix"], r["round"], r["node"]): r for r in rows}
    pref = {v: k for k, v in RA.CHECK_LABEL.items()}
    out = []
    for it in items:
        prefix = pref.get(it["check"])
        # The verdict is read from the LATEST red round of the current
        # episode, not its first: the body of the newest log is the one a
        # reader would open, and a cause set can grow inside an episode.
        cand = [r for r in rows
                if r["prefix"] == prefix and r["node"] == it["node"]
                and it["first_red_round"] is not None
                and r["round"] >= it["first_red_round"]]
        obs = max(cand, key=lambda r: r["round"]) if cand else None
        if obs is None:
            obs = by_key.get((prefix, it["first_red_round"], it["node"]))
        row = OrderedDict(it)
        row["kind"] = obs["kind"] if obs else UNRESOLVED
        row["causes"] = obs["causes"] if obs else []
        row["cause_round"] = obs["round"] if obs else None
        row["dated"] = obs["dated"] if obs else []
        out.append(row)
    return out


def note_clause(rows):
    """The head sentence `reddebt.note` inserts, computed from `rows`.

    Empty string when nothing is derived. Round 493's `_invisible_clause`
    made the case for computing this rather than writing it: a finding
    spelled into prose reads exactly as authoritative on the day it rots.
    """
    n = sum(1 for r in rows if r["kind"] == DERIVED)
    if not n:
        return ""
    return ("%d of them %s DERIVED (round 511): the node's own failure text "
            "names another node that is itself red, so it is red BECAUSE that "
            "one is and the fix is in the other suite, not in this one. "
            "`python3 harness/redcause.py live` prints the causing node for "
            "each. Do not reproduce a derived red looking for a defect in its "
            "host -- there is not one."
            % (n, "is" if n == 1 else "are"))


def note_lines(rows):
    """The per-row continuation lines for the derived rows, in `rows` order."""
    out = []
    for r in rows:
        if r["kind"] != DERIVED:
            continue
        dated = ""
        if r["dated"]:
            node, rnd, track = r["dated"][0]
            dated = " (first red in round %s's log, %s)" % (rnd, track)
        out.append("      ^ DERIVED — red because %s %s red%s. %s"
                   % (", ".join(r["causes"][:3]),
                      "is" if len(r["causes"]) == 1 else "are",
                      dated,
                      "Closing this means acting on that node, not this one."))
    return out


# ---------------------------------------------------------------------------
# CLI

def cmd_graph(args):
    rows = observations(args.root)
    if args.check:
        rows = [r for r in rows if r["check"] == args.check]
    res = summarise(rows)
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    n_logs, enough = RA.evidence_base(args.root)
    if not enough:
        print("NO EVIDENCE BASE: %d retained log(s) < %d -- `logs/` is not in "
              "git, so a fresh clone sees almost none of the corpus this "
              "module measures."
              % (n_logs, RA.MIN_EVIDENCE_LOGS))
    print("RED CAUSE GRAPH -- %d red (node, round) observation(s) over %d "
          "retained log(s)\n" % (res["n_observations"], n_logs))
    print("%-22s %8s %9s %9s %8s %10s %10s"
          % ("check", "derived", "same-log", "cross-log", "primary",
             "unresolved", "unreadable"))
    print("-" * 82)
    for label, c in res["per_check"].items():
        print("%-22s %8d %9d %9d %8d %10d %10d"
              % (label, c.get(DERIVED, 0), c.get(SAME_LOG, 0),
                 c.get(CROSS_LOG, 0), c.get(PRIMARY, 0),
                 c.get(UNRESOLVED, 0), c.get(UNREADABLE, 0)))
    print("-" * 82)
    print("%-22s %8d %9d %9d %8d %10d %10d"
          % ("ALL", res["derived"], res["derived_same_log"],
             res["derived_cross_log"], res["primary"], res["unresolved"],
             res["unreadable"]))
    print("\nderived share of ALL observations      %.1f%%"
          % (100 * res["derived_share_of_all"]))
    print("derived share of READABLE observations %.1f%%   "
          "(unreadable/unresolved excluded -- a body nobody can read is not "
          "evidence of a primary red)"
          % (100 * res["derived_share_of_readable"]))
    if res["top_causes"]:
        print("\nTOP CAUSES -- the node named INSIDE another node's failure "
              "text, and how many derived observations it explains:")
        for nid, k in res["top_causes"]:
            print("  %4d  %s" % (k, nid))
    lat = latencies(rows)
    if lat:
        gaps = sorted(g for *_x, g in lat)
        mid = gaps[len(gaps) // 2]
        print("\nDATED EDGES (the body states the causing round): %d, gap "
              "min %d / median %d / max %d round(s)"
              % (len(gaps), gaps[0], mid, gaps[-1]))
    return 0


def cmd_node(args):
    rows = [r for r in observations(args.root) if r["node"] == args.node]
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("no red observation for %r in the retained corpus" % args.node)
        return 0
    print("%s\n" % args.node)
    for r in rows:
        print("  round %-4s %-10s %s"
              % (r["round"], r["kind"],
                 ", ".join(r["causes"]) if r["causes"] else "--"))
    kinds = Counter(r["kind"] for r in rows)
    print("\n%d observation(s): %s"
          % (len(rows), ", ".join("%s %d" % kv for kv in sorted(kinds.items()))))
    return 0


def cmd_live(args):
    rows = live(args.root)
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("nothing red at the latest reading of any check")
        return 0
    for r in rows:
        print("%-19s %-8s %s" % (r["check"], r["kind"], r["node"]))
        for line in note_lines([r]):
            print(line)
    n = sum(1 for r in rows if r["kind"] == DERIVED)
    print("\nred-cause: %d red node(s), %d derived, %d primary, %d not readable"
          % (len(rows), n,
             sum(1 for r in rows if r["kind"] == PRIMARY),
             sum(1 for r in rows if r["kind"] in (UNRESOLVED, UNREADABLE))))
    return 0


def cmd_check(args):
    """Parser health. A MEASUREMENT -- exit 0. See module note 1."""
    rows = observations(args.root)
    res = summarise(rows)
    bodies = read_bodies(args.root)
    unres_titles = sorted({t for per in bodies.values()
                           for _g, u in per.values() for t in u})
    readable = res["derived"] + res["primary"]
    denom = readable + res["unresolved"]
    print("red-cause parser: %d pytest red observation(s), %d resolved to a "
          "body (%.1f%%), %d unresolved; %d unreadable by grammar "
          "(skills-check)"
          % (denom, readable, (100.0 * readable / denom) if denom else 100.0,
             res["unresolved"], res["unreadable"]))
    if unres_titles:
        print("\nblock titles that matched no single FAILED node "
              "(%d) -- these are ERRORS-section entries or ambiguous:"
              % len(unres_titles))
        for t in unres_titles[:20]:
            print("  %s" % t)
        if len(unres_titles) > 20:
            print("  ... and %d more" % (len(unres_titles) - 20))
    print("\nEXIT 0 BY DESIGN. This module measures the mechanism that makes a "
          "whole-tree fail-closed gate in one track's suite go red for another "
          "track's work; adding one here would be the ninth instance of the "
          "series it measures.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("graph", help="the cause table over the whole corpus")
    p.add_argument("--json", action="store_true")
    p.add_argument("--check", help="restrict to one check label")
    p.set_defaults(fn=cmd_graph)

    p = sub.add_parser("node", help="every red round of one node, with causes")
    p.add_argument("node")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_node)

    p = sub.add_parser("live", help="the currently-red set with cause verdicts")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_live)

    p = sub.add_parser("check", help="parser health (measurement, exit 0)")
    p.set_defaults(fn=cmd_check)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

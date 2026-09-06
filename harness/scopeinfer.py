#!/usr/bin/env python3
"""scopeinfer.py — could this node's `subject_scope` have been known BEFORE it went red?

Round 523 (harness A), answering round 521's next-step #1 in its own words:

    "The crosstrack registry is STRUCTURALLY incapable of being ahead of the
    first red, and that is what makes every R001 cost a round. `subject_scope`
    is a static property of a test -- readable from its source before it ever
    fails -- but `R002` makes a pre-declared entry an ERROR. So the registry
    can only ever be populated retroactively, one round late, by whoever comes
    next."

That is a claim with two halves and this module tests the second one. The
first half -- the `predeclared: true` shape that exempts an entry from R002 --
is a rule change in `harness/redattrib.py` and landed with this module. The
second half is a MEASUREMENT: is `subject_scope` really readable ahead of the
first red, and how often does reading it get the right answer?

WHAT IT READS, AND WHY THAT IS NOT CIRCULAR
-------------------------------------------
Round 467 split every registry entry's `evidence` into `subject` (the scope
follows from what the node READS or ASSERTS OVER) and `outcome` (the scope
could only be reached from the verdict history). R006 pins the one legitimate
outcome-derived label: `environmental`, and only `environmental`.

This module is allowed to see the SUBJECT side and nothing else:

  * `harness/readset-map.json` -- per test node, the repo paths it OPENED for
    reading and the repo directories it LISTED, recorded by
    `harness/readset.py record` from a PEP 578 audit hook. A read set is a
    measurement of the node, available the first time it is ever run, i.e.
    before any red.
  * `git log --name-only` -- for each subject path, which TRACKS have ever
    committed it. Also a fact about the file, not about the node's verdicts.

It never opens `logs/*_round_*.log`, never calls `redattrib.read_logs`, and
never emits `environmental`. Those three are the same restraint stated three
ways, and `test_scopeinfer.py` holds each of them open, because an inferrer
that peeked at outcomes would reproduce the registry by construction and the
agreement number below would mean nothing.

THE RULES, IN THE ORDER THEY FIRE
---------------------------------
    S000  refuse -- the node has no row in the read-set map
    S001  refuse -- the row exists and its subject set is empty
    S010  whole-tree     -- scans the repo ROOT, or spans >= 3 of the 4 trees
    S020  foreign-subject-- every tree-resident path is in ONE tree, not the host's
    S030  shared-corpus  -- a subject path is written by >= 3 tracks, at least
                            one of them outside the host suite's owner set
    S040  own-suite      -- every path is in the host tree, or outside all four
                            trees and only ever committed by the host track
    S050  refuse -- spans the host tree and exactly one other, with nothing
                    above firing; the registry has no label for that shape and
                    guessing between `whole-tree` and `foreign-subject` here
                    is what a retroactive reader does with the answer in hand

`shared-file-own-content` is NEVER emitted and cannot be: its definition is
"the subject is a file every track writes, but the specific claim is about a
REGION only one track writes", and a read set records the file, never the
region. That is a stated blind spot, not an oversight -- see `UNREACHABLE`.

Commands
--------
    python3 harness/scopeinfer.py infer <nodeid> [--json]
        The proposed scope for one node, with the rule that fired and the
        evidence it fired on.

    python3 harness/scopeinfer.py agree [--json]
        THE MEASUREMENT. Every entry in `harness/crosstrack-registry.json`
        scored against what this module would have proposed, with the
        confusion matrix and the coverage loss stated separately from the
        disagreement. Exit 0 always.

    python3 harness/scopeinfer.py predeclare [--limit N] [--emit] [--json]
        The never-red nodes this module can label, i.e. the entries a round
        could add to the registry today under `predeclared: true`. `--emit`
        prints them as a registry fragment.

    python3 harness/scopeinfer.py writers [--path P] [--json]
        The path -> tracks map and how it was attributed, including the share
        that fell through to each fallback.
"""

import argparse
import collections
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import redattrib  # noqa: E402  (sibling module, same package-less directory)
import readset    # noqa: E402

#: The four track-owned trees. A path outside all four ("state/", "knowledge/",
#: "logs/", the root files) is SHARED GROUND and is classified by who has
#: committed it, not by where it lives.
TREES = collections.OrderedDict((
    ("harness", "harness(A)"),
    ("languages/whence", "language(C)"),
    ("nuc", "NUC-integration(E)"),
    ("skills", "skills(B)"),
))

#: Host tree of each hosting suite, from `redattrib.SUITE_OWNER`'s keys.
SUITE_TREE = {
    "harness/tests": "harness",
    "languages/whence/tests": "languages/whence",
    "nuc/tests": "nuc",
    "skills": "skills",
}

#: How many distinct TRACKS must have committed a path before it can count as
#: SHARED CORPUS. Chosen A PRIORI at three -- the registry's own prose calls
#: `state/research-state.md` and `skills/` shared and neither needs all five --
#: and NOT tuned against the agreement number it feeds, which would be fitting
#: the classifier to its own scoring set. `agree --threshold` re-runs the whole
#: measurement at another value so the sensitivity is reported rather than
#: hidden; round 523 published 3, 4 and 5.
#:
#: MEASURED, AND THE FIRST DRAFT WAS WRONG TWICE.
#:  (1) `NON_TRACK` writers were counted toward this threshold, on the argument
#:      that "a file the driver and two tracks all append to is shared ground
#:      by the same argument". With `operator` and `driver` counted, 89 paths
#:      clear it, including `harness/swe/mutation.py` -- an ordinary own-suite
#:      source touched once by an operator commit landing a MISSION block.
#:      Excluding them: 57.
#:  (2) A raw count is still not the predicate. `harness/tests/test_whenceslow
#:      .py` is written by harness(A), SWE-loop(D) and language(C) -- three --
#:      but harness(A) and SWE-loop(D) BOTH run the harness suite, so two of
#:      those three writers are the host's own owners. `OWNERS` below is read
#:      from the registry's `_track_suites`, and a path only counts as shared
#:      when it ALSO has a writer from outside the host's owner set.
SHARED_CORPUS_TRACKS = 3

#: Scopes this module will never propose, with the reason. Read by
#: `test_the_unreachable_scopes_are_declared_and_never_emitted`.
UNREACHABLE = {
    "environmental": (
        "R006: an `environmental` label is outcome-derived by definition -- "
        "flakiness is invisible in a subject. Emitting it here would make the "
        "agreement measurement circular."),
    "shared-file-own-content": (
        "The scope is 'a file every track writes, but the claim is about a "
        "REGION only one track writes'. A read set records the file, never "
        "the region, so this distinction is not in the evidence available."),
}

#: `_track_suites` as the registry declares it, loaded once. Injectable in
#: `infer` so a unit test can state its own relation instead of the tree's.
try:
    DEFAULT_TRACK_SUITES = redattrib.load_registry()["_track_suites"]
except (OSError, ValueError, KeyError):       # pragma: no cover - no registry
    DEFAULT_TRACK_SUITES = {}
DEFAULT_TRACK_SUITES = dict((k, v) for k, v in DEFAULT_TRACK_SUITES.items()
                            if not k.startswith("_"))

#: Rule codes, in firing order, with their verdicts. `None` is a refusal.
RULES = (
    ("S000", None),
    ("S001", None),
    ("S010", "whole-tree"),
    ("S020", "foreign-subject"),
    ("S030", "shared-corpus"),
    ("S040", "own-suite"),
    ("S050", None),
)


# ------------------------------------------------------------- writer sets --

#: Subject-line shapes that name a track directly. Matched case-insensitively
#: because 58 of this repo's 766 commit subjects are `Round NNN (...)` with a
#: capital R and would silently attribute to nobody otherwise.
TRACK_MARKERS = (
    ("harness(A)", r"harness\s*[(\[]?\s*A\b"),
    ("skills(B)", r"skills\s*[(\[]?\s*B\b"),
    ("language(C)", r"language\s*[(\[]?\s*C\b"),
    ("NUC-integration(E)", r"NUC[-\s]?(?:integration)?\s*[(\[]?\s*E\b"),
    ("SWE-loop(D)", r"SWE[-\s]?loop\s*[(\[]?\s*D\b"),
)
ROUND_RE = re.compile(r"round\s+(\d+)", re.I)

#: Non-track writer identities, kept distinct rather than folded into a track
#: and NOT counted toward `SHARED_CORPUS_TRACKS` (see that constant's note --
#: counting them was measured and withdrawn). `driver` is `run_driver.sh`'s
#: own post-round ledger appends; `operator` is a human commit (the releases,
#: the MISSION blocks); `unattributed` is a subject no route resolved. They
#: are still RECORDED, because "who else writes this file" is worth reading
#: even when it does not move a label.
NON_TRACK = frozenset(("driver", "operator", "unattributed"))


def track_writers(ws):
    """The five-track subset of a writer set -- the only writers a scope is about."""
    return [w for w in ws if w not in NON_TRACK]


def owners(tree, track_suites):
    """Tracks that ROUTINELY RUN the suite in `tree`, per `_track_suites`.

    Not "the track named after the tree": `_track_suites` gives SWE-loop(D)
    both `harness/tests` and `languages/whence/tests`, because CURRICULUM.md
    track D is "use the harness ON our own code". A commit to `harness/` by
    SWE-loop(D) is therefore not a foreign writer of a harness node, and
    counting it as one turns own-suite nodes into shared-corpus ones.
    """
    suite = next((s for s, t in SUITE_TREE.items() if t == tree), None)
    return frozenset(t for t, suites in track_suites.items()
                     if suite is not None and suite in (suites or ()))


def attribute_subject(subject, round_tracks, rotation):
    """(writer, route) for one commit subject. Never raises, never returns None.

    Four routes, tried in order, each named so `cmd_writers` can report how
    much of the map rests on the weakest one:
      `marker`   the subject names the track
      `log`      the subject names a round and `logs/driver.log` has it
      `rotation` the subject names a round and the driver's OWN observed
                 round-number -> track rule (never CLAUDE.md's copy of it)
      `none`     neither -- `driver:` prefixed, or an operator commit
    """
    for track, pat in TRACK_MARKERS:
        if re.search(pat, subject, re.I):
            return track, "marker"
    m = ROUND_RE.search(subject)
    if m:
        rnd = int(m.group(1))
        if rnd in round_tracks:
            return round_tracks[rnd], "log"
        if rotation and (rnd % redattrib.ROTATION_PERIOD) in rotation:
            return rotation[rnd % redattrib.ROTATION_PERIOD], "rotation"
        return "unattributed", "none"
    if subject.startswith("driver:"):
        return "driver", "none"
    return "operator", "none"


def path_writers(root=ROOT, _log=None):
    """(path -> sorted writers, route counts) over the repo's whole history.

    A SUBJECT measurement about each file -- who has ever changed it -- and
    not about any node's verdicts, which is what keeps it admissible here.
    """
    if _log is None:
        _log = subprocess.run(
            ["git", "-C", root, "log", "--pretty=format:@@%H|%s", "--name-only"],
            capture_output=True, text=True, check=True).stdout
    tracks = redattrib.round_tracks(root)
    rotation, _problems = redattrib.rotation_residue_map(tracks)
    writers, routes = collections.defaultdict(set), collections.Counter()
    who = None
    for line in _log.splitlines():
        if line.startswith("@@"):
            subject = line[2:].split("|", 1)[1] if "|" in line else ""
            who, route = attribute_subject(subject, tracks, rotation)
            routes[route] += 1
            continue
        name = line.strip()
        if name and who:
            writers[name].add(who)
    return dict((k, sorted(v)) for k, v in writers.items()), routes


# ---------------------------------------------------------- the subject set --

def tree_of(path):
    """Which of the four track trees `path` lives in, or None for shared ground."""
    best = None
    for tree in TREES:
        if path == tree or path.startswith(tree + "/"):
            if best is None or len(tree) > len(best):
                best = tree
    return best


def own_file(nodeid):
    """The test file the node itself lives in -- its own body, not its subject."""
    return nodeid.split("::", 1)[0]


def existing(paths, root=ROOT):
    """`paths` split into (present in the tree, absent from it).

    ROUND 523 FOUND THIS AND IT IS NOT COSMETIC. `readset.py`'s audit hook
    fires on the `open` EVENT, which CPython raises before the syscall, so a
    read that fails with ENOENT is recorded exactly like one that succeeds.
    A test that resolves a bare basename against the ambient cwd -- and
    pytest's cwd is the repo root -- therefore contributes a repo-relative
    path that has never existed: `alpha` (123 rows), `beta` (123), `my-skill`
    (54), and the whole `.git` subdirectory roster `heads`/`objects`/`refs`/
    `branches`/`hooks`/`info`/`pack`/`tags` (33 each). 190 distinct phantoms
    across 415 of the map's 1456 rows at the round-523 recording.

    They are dropped HERE, not in `readset.py`: for `blast` a failed probe is
    arguably a real dependence (create the file and the node's behaviour
    changes), and deciding that is the owner's call on its own instrument.
    For a SCOPE it is not arguable -- `alpha` sits outside all four trees and
    would push a node to `S050` on the strength of a file nobody has ever
    written. `readset.py phantoms` reports them from the map's own side.
    """
    yes, no = [], []
    for p in paths:
        (yes if os.path.exists(os.path.join(root, p)) else no).append(p)
    return yes, no


def subject_set(nodeid, mp, root=ROOT, drop_phantoms=True):
    """(files|scans) for `nodeid`, minus the node's own test file. None if unmapped.

    The node's own module is dropped for the same reason a function is not
    its own argument: `test_whenceslow.py::test_the_real_tree_yields_the_units
    _round_469_measured` reads 76 files under `languages/whence` and exactly
    one under `harness/tests` -- itself. Keeping it would make a node whose
    subject is entirely another tree look like it spans two, and the registry
    calls that node `foreign-subject`.
    """
    row = (mp.get("nodes") or {}).get(nodeid)
    if row is None:
        return None
    mine = own_file(nodeid)
    paths = sorted((set(row.get("files", ())) | set(row.get("scans", ())))
                   - {mine})
    if not drop_phantoms:
        return paths
    return existing(paths, root)[0]


def infer(nodeid, mp, writers, track_suites=None, threshold=None, root_scan=".",
          root=ROOT, drop_phantoms=True):
    """(scope|None, rule, evidence) for one node. Never reads a verdict."""
    track_suites = track_suites if track_suites is not None else DEFAULT_TRACK_SUITES
    threshold = SHARED_CORPUS_TRACKS if threshold is None else threshold
    suite = redattrib.node_suite(nodeid)
    host = SUITE_TREE.get(suite)
    host_owners = owners(host, track_suites) if host else frozenset()
    raw = subject_set(nodeid, mp, root, drop_phantoms=False)
    subj = subject_set(nodeid, mp, root, drop_phantoms)
    ev = {"suite": suite, "host_tree": host, "n_subject": 0}
    if subj is None:
        return None, "S000", dict(ev, why="no row in the read-set map")
    ev["n_subject"] = len(subj)
    ev["n_phantom_dropped"] = len(raw) - len(subj)
    if not subj:
        return None, "S001", dict(
            ev, why="read-set row is empty%s"
            % (" after dropping %d path(s) that do not exist in the tree"
               % ev["n_phantom_dropped"] if ev["n_phantom_dropped"] else ""))

    scans = set((mp["nodes"][nodeid].get("scans") or ()))
    trees = collections.Counter()
    shared = []
    for p in subj:
        t = tree_of(p)
        if t:
            trees[t] += 1
        else:
            shared.append(p)
    ev["trees"] = dict(trees)
    ev["n_shared_ground"] = len(shared)

    if root_scan in scans:
        return "whole-tree", "S010", dict(ev, why="scans the repo root")
    if len(trees) >= 3:
        return "whole-tree", "S010", dict(
            ev, why="spans %d of the %d trees" % (len(trees), len(TREES)))

    def foreign(p):
        return sorted(set(track_writers(writers.get(p, []))) - host_owners)

    if len(trees) == 1 and host is not None and host not in trees:
        return "foreign-subject", "S020", dict(
            ev, why="every tree-resident path is in %r, host tree is %r"
            % (next(iter(trees)), host))

    wide = [(p, track_writers(writers.get(p, []))) for p in subj
            if len(track_writers(writers.get(p, []))) >= threshold and foreign(p)]
    if wide:
        return "shared-corpus", "S030", dict(
            ev, why="%d subject path(s) written by >= %d tracks including at "
                    "least one outside the host's owner set %s"
                    % (len(wide), threshold, sorted(host_owners)),
            shared_corpus_paths=[p for p, _w in wide[:5]])

    if host is not None and set(trees) <= {host}:
        stray = [p for p in shared if foreign(p)]
        if not stray:
            return "own-suite", "S040", dict(
                ev, why="no path outside the host tree that another track "
                        "has ever committed")
        ev["foreign_written_shared_paths"] = stray[:5]
        return None, "S050", dict(
            ev, why="host tree only, but %d shared-ground path(s) have "
                    "non-host writers" % len(stray))

    return None, "S050", dict(
        ev, why="spans the host tree and %d other(s); the registry has no "
                "label for that shape" % max(0, len(trees) - 1))


# ------------------------------------------------------------ the agreement --

def load_map(root=ROOT):
    return readset.load_map(os.path.join(root, "harness", "readset-map.json"))


def agreement(root=ROOT, mp=None, writers=None, registry=None, threshold=None):
    """Score every registry entry against what this module would have proposed."""
    mp = mp if mp is not None else load_map(root)
    writers = writers if writers is not None else path_writers(root)[0]
    reg = registry if registry is not None else redattrib.load_registry(root)
    ts = dict((k, v) for k, v in reg["_track_suites"].items()
              if not k.startswith("_"))
    rows = []
    for nid in sorted(reg["nodes"]):
        ent = reg["nodes"][nid]
        scope, rule, ev = infer(nid, mp, writers, ts, threshold)
        rows.append({
            "node": nid,
            "declared": ent.get("subject_scope"),
            "evidence": ent.get("evidence"),
            "inferred": scope,
            "rule": rule,
            "why": ev.get("why"),
            "predeclared": ent.get("predeclared") is True,
            "agree": scope is not None and scope == ent.get("subject_scope"),
        })
    # THE HEADLINE IS COMPUTED OVER INDEPENDENT LABELS ONLY.
    #
    # Round 523 landed 37 predeclared entries THIS MODULE PROPOSED, and the
    # very next `agree` run reported 81% -- up from 56% -- because 37 of the
    # 39 foreign-subject agreements were its own output scored against
    # itself. Caught by reading the matrix, not by a test. A predeclared
    # entry is not evidence about the classifier; it IS the classifier. It
    # becomes evidence only when a human corrects it, and then it is no
    # longer predeclared.
    human = [r for r in rows if not r["predeclared"]]
    rows_pre = [r for r in rows if r["predeclared"]]
    labelled = [r for r in human if r["inferred"] is not None]
    subj = [r for r in human if r["evidence"] == "subject"]
    subj_lab = [r for r in subj if r["inferred"] is not None]
    matrix = collections.Counter(
        (r["declared"], r["inferred"]) for r in labelled)
    return {
        "threshold": SHARED_CORPUS_TRACKS if threshold is None else threshold,
        "n_entries": len(human),
        "n_all_entries": len(rows),
        "n_predeclared_excluded": len(rows_pre),
        "n_predeclared_still_agreeing": sum(1 for r in rows_pre if r["agree"]),
        "n_labelled": len(labelled),
        "n_agree": sum(1 for r in labelled if r["agree"]),
        "n_subject_evidence": len(subj),
        "n_subject_evidence_labelled": len(subj_lab),
        "n_subject_evidence_agree": sum(1 for r in subj_lab if r["agree"]),
        "refusals": collections.Counter(
            r["rule"] for r in rows if r["inferred"] is None),
        "matrix": matrix,
        "rows": rows,
    }


def predeclarable(root=ROOT, mp=None, writers=None, registry=None, threshold=None):
    """Nodes with a read-set row, NOT in the registry, that this module can label.

    These are exactly the entries a round could write today under
    `predeclared: true` -- the population `R002` used to make unwritable.
    """
    mp = mp if mp is not None else load_map(root)
    writers = writers if writers is not None else path_writers(root)[0]
    reg = registry if registry is not None else redattrib.load_registry(root)
    ts = dict((k, v) for k, v in reg["_track_suites"].items()
              if not k.startswith("_"))
    out = []
    for nid in sorted(mp.get("nodes", {})):
        if nid.endswith(readset.COLLECT_SUFFIX) or nid == readset.UNATTRIBUTED:
            continue
        if "::" not in nid or nid in reg["nodes"]:
            continue
        if redattrib.node_suite(nid) is None:
            continue
        scope, rule, ev = infer(nid, mp, writers, ts, threshold)
        if scope is None:
            continue
        out.append({"node": nid, "subject_scope": scope, "rule": rule,
                    "why": ev.get("why"), "n_subject": ev.get("n_subject")})
    return out


def registry_fragment(rows, round_no=523):
    """`rows` as a `nodes` fragment ready to paste into the registry."""
    frag = collections.OrderedDict()
    for r in rows:
        frag[r["node"]] = collections.OrderedDict((
            ("subject_scope", r["subject_scope"]),
            ("evidence", "subject"),
            ("predeclared", True),
            ("why", "PREDECLARED by round %d's `harness/scopeinfer.py "
                    "predeclare`, before this node has ever been red. Rule %s: "
                    "%s. The evidence is the node's recorded read set "
                    "(`harness/readset-map.json`) plus the committed-writer "
                    "set of each subject path -- both facts about the SUBJECT, "
                    "neither about any verdict. If this node does go red and "
                    "the scope is wrong, correct it and say so: a predeclared "
                    "entry is a prediction, and a wrong one is more useful "
                    "than a missing one." % (round_no, r["rule"], r["why"])),
        ))
    return frag


# ------------------------------------------------------------------- the CLI --

def _fmt_counter(c):
    return ", ".join("%s %d" % (k, v) for k, v in sorted(c.items()))


def cmd_infer(args):
    mp = load_map()
    writers, _routes = path_writers()
    scope, rule, ev = infer(args.nodeid, mp, writers)
    if args.json:
        print(json.dumps({"node": args.nodeid, "inferred": scope,
                          "rule": rule, "evidence": ev}, indent=1, sort_keys=True))
    else:
        print("%s\n  inferred %s  (%s)\n  %s"
              % (args.nodeid, scope if scope else "REFUSED", rule, ev.get("why")))
        for k in ("suite", "host_tree", "n_subject", "trees", "n_shared_ground"):
            if k in ev:
                print("    %-18s %s" % (k, ev[k]))
    return 0


def cmd_agree(args):
    res = agreement(threshold=args.threshold)
    if args.json:
        out = dict(res)
        out["refusals"] = dict(res["refusals"])
        out["matrix"] = [{"declared": d, "inferred": i, "n": n}
                         for (d, i), n in sorted(res["matrix"].items())]
        print(json.dumps(out, indent=1, sort_keys=True))
        return 0
    print("SHARED_CORPUS_TRACKS      %d" % res["threshold"])
    print("registry entries          %d  (of %d; %d predeclared by this "
          "module are EXCLUDED -- scoring them would be scoring the "
          "classifier against itself)"
          % (res["n_entries"], res["n_all_entries"],
             res["n_predeclared_excluded"]))
    print("  labelled by scopeinfer  %d" % res["n_labelled"])
    print("  of those, agreeing      %d (%.0f%%)"
          % (res["n_agree"],
             100.0 * res["n_agree"] / res["n_labelled"] if res["n_labelled"] else 0))
    print("  evidence: subject       %d, labelled %d, agreeing %d"
          % (res["n_subject_evidence"], res["n_subject_evidence_labelled"],
             res["n_subject_evidence_agree"]))
    print("refusals by rule          %s" % _fmt_counter(res["refusals"]))
    print()
    print("  declared -> inferred")
    for (d, i), n in sorted(res["matrix"].items(), key=lambda kv: -kv[1]):
        print("    %-26s -> %-18s %3d %s"
              % (d, i, n, "" if d == i else "  <-- disagreement"))
    print()
    if res["n_predeclared_excluded"]:
        print("  predeclared entries excluded above: %d, of which %d still "
              "reproduce (a drop means somebody CORRECTED one -- read it)"
              % (res["n_predeclared_excluded"],
                 res["n_predeclared_still_agreeing"]))
        print()
    for name, why in sorted(UNREACHABLE.items()):
        n = sum(v for (d, _i), v in res["matrix"].items() if d == name)
        n += sum(1 for r in res["rows"]
                 if r["declared"] == name and r["inferred"] is None)
        print("  NEVER EMITTED  %-24s %d declared entr(y/ies)\n     %s"
              % (name, n, why))
    return 0


def cmd_predeclare(args):
    rows = predeclarable(threshold=args.threshold)
    if args.limit:
        rows = rows[:args.limit]
    if args.emit:
        print(json.dumps(registry_fragment(rows), indent=1))
        return 0
    if args.json:
        print(json.dumps(rows, indent=1, sort_keys=True))
        return 0
    by = collections.Counter(r["subject_scope"] for r in rows)
    print("predeclarable nodes (read-set row, never red, a rule fires): %d"
          % len(rows))
    print("  by scope: %s" % _fmt_counter(by))
    print("  by rule:  %s" % _fmt_counter(collections.Counter(r["rule"] for r in rows)))
    for r in rows[:args.show]:
        print("    %-14s %s" % (r["subject_scope"], r["node"]))
    if len(rows) > args.show:
        print("    ... %d more" % (len(rows) - args.show))
    return 0


def cmd_writers(args):
    writers, routes = path_writers()
    if args.path:
        print("%s: %s" % (args.path, writers.get(args.path, [])))
        return 0
    hist = collections.Counter(len(track_writers(v)) for v in writers.values())
    if args.json:
        print(json.dumps({"n_paths": len(writers), "routes": dict(routes),
                          "histogram": dict(hist)}, indent=1, sort_keys=True))
        return 0
    print("paths with at least one attributed writer  %d" % len(writers))
    print("commit attribution routes                  %s" % _fmt_counter(routes))
    print("writers-per-path histogram                 %s" % _fmt_counter(hist))
    wide = sorted((p for p, w in writers.items()
                   if len(track_writers(w)) >= SHARED_CORPUS_TRACKS))
    print("paths at or above SHARED_CORPUS_TRACKS=%d   %d"
          % (SHARED_CORPUS_TRACKS, len(wide)))
    for p in wide:
        print("    %-46s %s" % (p, ", ".join(writers[p])))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("infer")
    p.add_argument("nodeid")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_infer)

    p = sub.add_parser("agree")
    p.add_argument("--json", action="store_true")
    p.add_argument("--threshold", type=int, default=None,
                   help="override SHARED_CORPUS_TRACKS for a sensitivity run")
    p.set_defaults(fn=cmd_agree)

    p = sub.add_parser("predeclare")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--show", type=int, default=15)
    p.add_argument("--emit", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--threshold", type=int, default=None)
    p.set_defaults(fn=cmd_predeclare)

    p = sub.add_parser("writers")
    p.add_argument("--path")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_writers)

    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

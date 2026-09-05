#!/usr/bin/env python3
"""Verify the `via` provenance pins in `harness/wiring-registry.json`
(round 481, harness A).

What a `via` claims
-------------------
Every `wired` entry in the registry carries a field like

    "harness/run_slowtier_slice.sh": {"status": "wired",
                                      "via": "run_driver.sh:672",
                                      "via_kind": "path"}

which asserts: *line 672 of `run_driver.sh` is what reaches this entry
point*. `wiring_audit.audit()` proves the STATUS every round — it recomputes
reachability from `run_driver.sh` over the whole tree — and it never reads
`via` at all. The line is documentation, and until this module nothing in
the repo checked it except three hand-written assertions covering three of
the 110 pins.

Round 475 named the debt after breaking eight pins with a 25-line insertion
into `run_driver.sh` and finding out from the test tier a round later:

    "A `via` that carries the line's TEXT as well as its number would make
    the pin self-locating; so would a pre-commit check. Neither exists."

Why the text anchor is the WRONG remedy — measured, not argued
--------------------------------------------------------------
A pin can stop being true in three ways, and this repo has one live instance
of each:

  1. THE LINE MOVED. `nuc/constant_audit.py` was pinned at
     `nuc/run_checks_fast.sh:66`; the invocation is at line 146. Round 475's
     eight are this shape.
  2. THE PIN WAS NEVER RIGHT. `languages/whence/orderhint.py` was pinned at
     `languages/whence/tests/test_v46.py:41` by the round that wrote it;
     line 41 is `sys.path.insert(...)` and the import is at 43.
  3. THE ANALYSER CHANGED AND THE EDGE CEASED TO EXIST. Four entries are
     pinned at `harness/tests/test_swe_proc.py:-`. That file has not been
     touched since round ~150 and still contains the
     `os.path.join(..., "languages", "whence")` those pins were derived
     from — but round 415 narrowed the directory rule (`_constructed_paths`'
     `pytest_ctx` gate) IN THE SAME COMMIT that created the registry, so the
     edge does not exist and never did at any commit the registry has lived
     through.

A text anchor detects shape 1 and nothing else. Against shape 2 it pins the
wrong line's text and calls it held; against shape 3 it finds the line
verbatim, unmoved, and reports a HELD pin for an edge the graph no longer
draws. So the anchor is not a weaker version of this check — for two of the
three shapes it is a check that answers *held* precisely when the claim is
false. The pin must be re-derived from the same graph that decides the
status, which is what this module does.

Verdicts
--------
  held      numeric pin; the graph's edge from that file to that entry point
            is at exactly that line.
  drifted   numeric pin; the file DOES reach the entry point, at a different
            line. Mechanically repairable — `fix --write`.
  lost      the pinned file does not reach the entry point at all. NOT
            auto-repairable: the entry may still be `wired` by some other
            route, and silently repointing the pin at a different FILE
            changes what the registry claims rather than correcting it.
            Adjudicate by hand; `audit` prints the best incoming edge as a
            suggestion and does not apply it.
  absent    `via` names a path that is not a node in the graph.
  unpinned  a `"<file>:-"` pin — no line claimed — where a line IS now
            derivable. Reported, never an error: a pin that declines to name
            a line makes no false claim. `fix --write --fill` converts them.
  none      the entry has no `via` (every `manual` entry, by convention).

`drifted`, `lost` and `absent` are FALSE CLAIMS and are the exit-1 set.
`unpinned` is a missing claim and is not.

Why 80 of 110 pins say `:-`, and why that is a defect this round FIXED
---------------------------------------------------------------------
It was never a convention. `cmd_bootstrap` writes

    "via": "%s:%s" % (best[0], best[1] or "-")

and `references()` recorded EVERY edge produced by its three `ast` passes —
imports, bare string constants, `os.path.join` folds — at line 0, because
the passes returned bare values and the call sites passed the literal `0`.
`0 or "-"` is `"-"`. 721 of this tree's 1043 edges (69 %) had no line, and
the one renderer spelled "line 0" and "line unknown" identically, so the
loss was invisible in the registry, in `audit()`'s W003/W006 messages, and
in `--why` traces. Round 481 threaded the real `lineno` through all three
passes; the closure, the edge target sets and the edge kinds are byte-for-
byte identical before and after, and the lineno-0 count went 721 -> 0.

Verification
------------
    python3 harness/viapin.py audit
    python3 harness/viapin.py audit --json | python3 -c "import json,sys; \
        print(json.load(sys.stdin)['counts'])"
    python3 harness/viapin.py fix            # dry run, prints the patch
    python3 -m pytest -q harness/tests/test_viapin.py
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import wiring_audit as W                                        # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The verdicts that assert something FALSE about the tree. `unpinned` is
# absent on purpose — see the module docstring.
ERROR_VERDICTS = ("drifted", "lost", "absent")


def classify(key, entry, graph):
    """One registry entry -> a row dict. Pure; `graph` is read, never built."""
    via = entry.get("via")
    row = {"key": key, "via": via, "via_kind": entry.get("via_kind"),
           "status": entry.get("status"), "actual": None, "actual_kind": None,
           "suggest": None}
    if not via:
        row["verdict"] = "none"
        return row
    if via == "root":
        row["verdict"] = "root"
        return row
    path, _, lineno = via.rpartition(":")
    row["via_path"] = path
    if path not in graph.node_set:
        row["verdict"] = "absent"
        return row
    edge = graph._expand(path).get(key)
    if edge is not None:
        row["actual"], row["actual_kind"] = edge[0], edge[1]
    if lineno.isdigit():
        if edge is None:
            row["verdict"] = "lost"
        elif edge[0] == int(lineno):
            row["verdict"] = "held"
        else:
            row["verdict"] = "drifted"
            row["suggest"] = "%s:%d" % (path, edge[0])
    else:
        if edge is None:
            row["verdict"] = "lost"
        else:
            row["verdict"] = "unpinned"
            row["suggest"] = "%s:%d" % (path, edge[0])
    if row["verdict"] == "lost":
        # The best evidence that DOES exist, printed as a suggestion and
        # never applied: it names a different file, which is a different
        # claim.
        best = graph.best_incoming(key)
        if best is not None:
            row["suggest"] = "%s:%d [%s] (DIFFERENT FILE — adjudicate)" \
                             % (best[0], best[1], best[2])
    return row


def audit(root=None, graph=None, registry=None):
    """Every `via` claim in the registry, classified.

    `graph` and `registry` are injectable so a caller that already built a
    `Graph` (the test tier does; it costs ~10 s on this one-CPU box) does not
    pay for a second one.
    """
    root = root or REPO_ROOT
    graph = graph or W.Graph(root)
    graph.closure()
    if registry is None:
        registry = W.load_registry(root) or {}
    entries = registry.get("entry_points", {})
    rows = [classify(k, entries[k], graph) for k in sorted(entries)]
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {"rows": rows, "counts": counts,
            "errors": [r for r in rows if r["verdict"] in ERROR_VERDICTS],
            "n_pins": sum(1 for r in rows
                          if r["verdict"] not in ("none", "root"))}


def summary_line(res):
    c = res["counts"]
    return ("via-pins: %d pin(s), %d held, %d drifted, %d lost, %d absent, "
            "%d unpinned"
            % (res["n_pins"], c.get("held", 0), c.get("drifted", 0),
               c.get("lost", 0), c.get("absent", 0), c.get("unpinned", 0)))


def _dump_registry(path, registry):
    """Round-trip `harness/wiring-registry.json` in ITS OWN formatting.

    `indent=2, ensure_ascii=False` reproduces the file byte-for-byte at HEAD;
    the default `ensure_ascii=True` would rewrite every em dash in every
    `reason` string and turn a two-line repair into a 90-line diff.

    Round 499 needed the same writer for `wiring_audit.py declare` and put
    it in `wiring_audit` — the lower module, which `viapin` already imports.
    This delegates rather than keeping a second copy: two writers for one
    file is exactly how the `ensure_ascii` rule gets re-learned by whoever
    edits only one of them.
    """
    return W.dump_registry(path, registry)


def fix(root=None, write=False, fill=False, res=None):
    """Repair `drifted` pins (and, with `fill`, `unpinned` ones) IN PLACE.

    Only ever moves a pin to another line of THE FILE IT ALREADY NAMES.
    `lost` and `absent` are returned untouched: repointing them means
    choosing a different source file, which is an editorial claim about why
    an entry point is wired and not a clerical correction.
    """
    root = root or REPO_ROOT
    res = res or audit(root)
    reg_path = os.path.join(root, W.REGISTRY_NAME)
    registry = json.load(open(reg_path))
    wanted = ("drifted", "unpinned") if fill else ("drifted",)
    changes = []
    for r in res["rows"]:
        if r["verdict"] not in wanted or not r["suggest"]:
            continue
        changes.append((r["key"], r["via"], r["suggest"], r["verdict"]))
        if write:
            registry["entry_points"][r["key"]]["via"] = r["suggest"]
    if write and changes:
        _dump_registry(reg_path, registry)
    return changes


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def cmd_audit(args):
    res = audit(args.root)
    if args.json:
        print(json.dumps({"counts": res["counts"], "n_pins": res["n_pins"],
                          "rows": res["rows"]}, indent=2))
    else:
        for r in res["rows"]:
            if r["verdict"] in ERROR_VERDICTS or (args.all
                                                  and r["verdict"] != "none"):
                print("%-8s %-58s pinned=%-40s %s"
                      % (r["verdict"].upper(), r["key"], r["via"],
                         ("-> " + r["suggest"]) if r["suggest"] else ""))
        print(summary_line(res))
        if res["errors"]:
            print("repair the mechanical ones with: "
                  "python3 harness/viapin.py fix --write")
    return 1 if res["errors"] else 0


def cmd_fix(args):
    changes = fix(args.root, write=args.write, fill=args.fill)
    for key, old, new, verdict in changes:
        print("%-8s %-58s %s -> %s" % (verdict, key, old, new))
    print("via-pins: %d change(s)%s" % (len(changes),
                                        "" if args.write else " (dry run; "
                                        "pass --write to apply)"))
    if not args.fill:
        res = audit(args.root)
        n = res["counts"].get("unpinned", 0)
        if n:
            print("via-pins: %d unpinned pin(s) left alone; --fill to name "
                  "their lines too" % n)
    return 0


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--root", default=REPO_ROOT)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="classify every via pin")
    a.add_argument("--json", action="store_true")
    a.add_argument("--all", action="store_true",
                   help="print held/unpinned rows too, not just the false ones")
    a.set_defaults(func=cmd_audit)
    f = sub.add_parser("fix", help="repair drifted pins within their own file")
    f.add_argument("--write", action="store_true")
    f.add_argument("--fill", action="store_true",
                   help="also give a line to `<file>:-` pins that now have one")
    f.set_defaults(func=cmd_fix)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

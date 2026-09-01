#!/usr/bin/env python3
"""copyparity — which tests change verdict when the project is COPIED?

    python3 -m swe.copyparity collect [--root PATH] [--json OUT]
    python3 -m swe.copyparity run     [--root PATH] [--json OUT] [--test-args "..."]

WHY THIS EXISTS
---------------
Every mutation run happens in a tempdir copy of `languages/whence` ALONE
(`harness/swe/mutation.py::_copy_project`). A file in that tree that resolves
a path OUTSIDE it from its own `__file__` — `state/`, `harness/`, the git
checkout — therefore points at `/tmp/<tmpdir>/...` in the copy, and fails
there and only there. `mutation_test`'s round-349 baseline gate turns any
such failure into `BaselineNotGreen` and then NO mutant runs at all: the
whole SWE-loop engine stops at the door, for a defect that has nothing to do
with mutants.

That class has now blocked the engine three times:

  * round 149 — `bench/ref_diff.py`'s git root (found as 7/78 phantom "kills")
  * round 413 — `curecheck.FIELD_CENSUS` plus five `__file__`-derived git
    roots; the fix introduced `curecheck.AGI_ROOT`, which prefers the
    `AGI_RESEARCH_ROOT` env var `harness/swe/proc.py` exports into every
    subprocess it starts, and wrote the rule down in a comment
  * round 419 — `tests/test_checkpin.py`'s two pin registries, added by
    rounds 414 and 416, i.e. ONE and THREE rounds after 413 fixed the class
    and wrote that comment. A comment is not a checker.

`baseline_check` already answers *is the copy green* with one exit code, and
that is the right shape for a GATE. It is the wrong shape for a DIAGNOSIS:
it names no test, and because `DEFAULT_TEST_CMD` carries `-x` it stops at the
first failure, so the answer is always "at least one". This module answers
the diagnostic question instead — *which nodes, and how do they differ* —
by running the suite BOTH ways and diffing per node.

TWO MODES, TWO COSTS, TWO DEFECT CLASSES
----------------------------------------
`collect` runs `pytest --collect-only -q` in both trees and diffs the node-id
SETS. It costs one collection each (~4 s for whence) and it catches the
IMPORT-time class: round 413's `FileNotFoundError` fired at module import in
`tests/test_field_corpus_selector.py`, which aborted collection of the whole
suite. A vanished node is the signature.

`run` runs the real suite in both trees and diffs per-node VERDICTS from
`--junitxml`. It costs two full suite runs and it is the only mode that
catches the RUNTIME class: round 419's registry reads are inside test
bodies, so collection is identical in both trees and only the verdicts move.

Both modes go through `proc.run_capped`, so the copied tree gets exactly the
environment (`AGI_RESEARCH_ROOT` included) that a real mutation run gives it.
Measuring in a different environment from the engine would measure nothing.

`-x` IS STRIPPED, DELIBERATELY
------------------------------
`run` removes `-x`/`--exitfirst` from the test command before either run. The
gate wants to stop early; the diagnosis wants the whole list, and with `-x`
in place the two runs stop at different tests and the diff is meaningless.
`stripped_x` is reported so a reader knows the command was not the caller's.
"""

import argparse
import json
import os
import shlex
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe.mutation import DEFAULT_TEST_CMD, _copy_project      # noqa: E402
from swe.proc import run_capped                               # noqa: E402
from swe.fuzz import WHENCE_ROOT                              # noqa: E402

#: Flags that make the two runs stop at different places. See the docstring.
EXITFIRST_FLAGS = ("-x", "--exitfirst")


def strip_exitfirst(cmd):
    """`(cmd_without_-x, did_strip)`."""
    out = [c for c in cmd if c not in EXITFIRST_FLAGS]
    return out, len(out) != len(cmd)


def parse_collect(output):
    """Node ids from `pytest --collect-only -q` stdout.

    The tail of that output is a blank line then a count line
    (`123 tests collected in 4.5s`); everything before it that contains
    `::` is a node id. Errors print tracebacks, which never contain `::`
    at line start — so a collection that fails yields FEWER ids, which is
    exactly the signal.
    """
    ids = []
    for line in (output or "").splitlines():
        line = line.strip()
        if "::" in line and not line.startswith(("E ", "_", "=", "!")):
            ids.append(line)
    return ids


def parse_junit(path):
    """`{node_id: status}` from a junit xml, `status` in
    passed/failed/error/skipped. Node id is `classname::name`, which is
    stable across two runs of the same suite in different directories
    (the `file` attribute is not emitted by every pytest)."""
    if not os.path.exists(path):
        return {}
    out = {}
    root = ET.parse(path).getroot()
    for tc in root.iter("testcase"):
        node = "%s::%s" % (tc.get("classname", ""), tc.get("name", ""))
        status = "passed"
        detail = ""
        for child in tc:
            if child.tag in ("failure", "error", "skipped"):
                status = {"failure": "failed"}.get(child.tag, child.tag)
                detail = (child.get("message") or "").strip()
                break
        out[node] = (status, detail[:400])
    return out


class Side(object):
    """One run, in one tree."""

    __slots__ = ("where", "root", "returncode", "seconds", "timed_out", "tail",
                 "nodes", "n_nodes")

    def __init__(self, where, root, capped, nodes):
        self.where = where                  # "in_place" | "copied"
        self.root = root
        self.returncode = -9 if capped.timed_out else capped.returncode
        self.seconds = round(capped.seconds, 2)
        self.timed_out = capped.timed_out
        self.tail = (capped.output or "").strip()[-1200:]
        self.nodes = nodes
        self.n_nodes = len(nodes)

    def as_dict(self, with_nodes=False):
        d = {"where": self.where, "root": self.root, "returncode": self.returncode,
             "seconds": self.seconds, "timed_out": self.timed_out,
             "n_nodes": self.n_nodes, "tail": self.tail}
        if with_nodes:
            d["nodes"] = (sorted(self.nodes) if isinstance(self.nodes, (set, list))
                          else {k: v[0] for k, v in sorted(self.nodes.items())})
        return d


class Report(object):
    def __init__(self, mode, in_place, copied, vanished, appeared, regressions,
                 improvements, test_cmd, stripped_x):
        self.mode = mode                    # "collect" | "run"
        self.in_place = in_place
        self.copied = copied
        self.vanished = vanished            # collected in place, gone in the copy
        self.appeared = appeared            # collected in the copy only
        self.regressions = regressions      # [(node, in_place, copied, detail)]
        self.improvements = improvements    # green only in the copy — also a defect
        self.test_cmd = list(test_cmd)
        self.stripped_x = stripped_x

    @property
    def copy_safe(self):
        return not (self.vanished or self.appeared or self.regressions or self.improvements)

    @property
    def verdict(self):
        if self.in_place.timed_out or self.copied.timed_out:
            return "no_verdict_timeout"
        return "copy_safe" if self.copy_safe else "copy_breaks"

    def as_dict(self):
        return {
            "mode": self.mode, "verdict": self.verdict, "copy_safe": self.copy_safe,
            "test_cmd": self.test_cmd, "stripped_exitfirst": self.stripped_x,
            "in_place": self.in_place.as_dict(), "copied": self.copied.as_dict(),
            "vanished": sorted(self.vanished), "appeared": sorted(self.appeared),
            "regressions": [{"node": n, "in_place": a, "copied": b, "detail": d}
                            for n, a, b, d in self.regressions],
            "improvements": [{"node": n, "in_place": a, "copied": b}
                             for n, a, b in self.improvements],
        }

    def summary(self):
        lines = ["copyparity(%s): %s — in_place %d node(s) rc=%d %.1fs / copied %d node(s) rc=%d %.1fs"
                 % (self.mode, self.verdict, self.in_place.n_nodes, self.in_place.returncode,
                    self.in_place.seconds, self.copied.n_nodes, self.copied.returncode,
                    self.copied.seconds)]
        if self.stripped_x:
            lines.append("  (-x stripped: a diagnosis must not stop at the first failure)")
        for n in sorted(self.vanished)[:20]:
            lines.append("  VANISHED   %s" % n)
        if len(self.vanished) > 20:
            lines.append("  ... and %d more vanished" % (len(self.vanished) - 20))
        for n in sorted(self.appeared)[:20]:
            lines.append("  APPEARED   %s" % n)
        for n, a, b, d in self.regressions[:20]:
            lines.append("  REGRESSED  %-64s %s -> %s" % (n[:64], a, b))
            if d:
                lines.append("             %s" % d.splitlines()[0][:100])
        if len(self.regressions) > 20:
            lines.append("  ... and %d more regressions" % (len(self.regressions) - 20))
        for n, a, b in self.improvements[:20]:
            lines.append("  ONLY-GREEN-IN-COPY %-52s %s -> %s" % (n[:52], a, b))
        if self.copy_safe:
            lines.append("  no node changed verdict when the tree was copied")
        return "\n".join(lines)


def _run_side(where, root, cmd, timeout_s, junit=None):
    full = list(cmd) + (["--junitxml=" + junit] if junit else [])
    capped = run_capped(full, root, timeout_s)
    if junit:
        nodes = parse_junit(junit)
    else:
        nodes = set(parse_collect(capped.output))
    return Side(where, root, capped, nodes)


def compare(root=WHENCE_ROOT, mode="collect", test_cmd=None, timeout_s=2400.0,
            copy_parent=None):
    """Run the suite in `root` and in a `_copy_project` copy of it, and diff.

    `mode="collect"` diffs collected node ids (cheap, import-time class).
    `mode="run"` diffs per-node junit verdicts (full cost, runtime class).
    """
    if mode not in ("collect", "run"):
        raise ValueError("mode must be 'collect' or 'run'")
    cmd = list(test_cmd or DEFAULT_TEST_CMD)
    stripped_x = False
    if mode == "collect":
        cmd, stripped_x = strip_exitfirst(cmd)
        # Exactly ONE -q: a second one is `-qq`, which suppresses the node-id
        # listing entirely and leaves this module parsing an empty list as
        # "nothing collected" — measured live, round 419.
        cmd = [c for c in cmd if c != "-q"] + ["--collect-only", "-q"]
    else:
        cmd, stripped_x = strip_exitfirst(cmd)
    tmp = tempfile.mkdtemp(prefix="copyparity-", dir=copy_parent)
    try:
        dst = os.path.join(tmp, "proj")
        _copy_project(root, dst)
        junit_a = os.path.join(tmp, "in_place.xml") if mode == "run" else None
        junit_b = os.path.join(tmp, "copied.xml") if mode == "run" else None
        a = _run_side("in_place", root, cmd, timeout_s, junit_a)
        b = _run_side("copied", dst, cmd, timeout_s, junit_b)
        if mode == "collect":
            vanished, appeared, regressions, improvements = a.nodes - b.nodes, b.nodes - a.nodes, [], []
        else:
            vanished = set(a.nodes) - set(b.nodes)
            appeared = set(b.nodes) - set(a.nodes)
            regressions, improvements = [], []
            for node in sorted(set(a.nodes) & set(b.nodes)):
                sa, _ = a.nodes[node]
                sb, db = b.nodes[node]
                if sa == sb:
                    continue
                if sa == "passed" and sb != "passed":
                    regressions.append((node, sa, sb, db))
                elif sb == "passed" and sa != "passed":
                    improvements.append((node, sa, sb))
                else:
                    regressions.append((node, sa, sb, db))
        return Report(mode, a, b, vanished, appeared, regressions, improvements,
                      cmd, stripped_x)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=["collect", "run"])
    ap.add_argument("--root", default=WHENCE_ROOT)
    ap.add_argument("--test-args", default=None,
                    help="replace DEFAULT_TEST_CMD's pytest args, e.g. '-q tests/test_v01.py'")
    ap.add_argument("--timeout", type=float, default=2400.0)
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    cmd = None
    if a.test_args:
        # shlex, not str.split: `-m "not whence_slow"` is one argument and
        # splitting on whitespace hands pytest three broken ones.
        cmd = ([sys.executable, "-m", "pytest", "-p", "no:cacheprovider"]
               + shlex.split(a.test_args))
    rep = compare(root=a.root, mode=a.mode, test_cmd=cmd, timeout_s=a.timeout)
    print(rep.summary())
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(rep.as_dict(), f, indent=1)
        print("wrote %s" % a.json)
    return 0 if rep.copy_safe else 1


if __name__ == "__main__":
    sys.exit(main())

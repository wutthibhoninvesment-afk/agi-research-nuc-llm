#!/usr/bin/env python3
"""copyparity — which tests change verdict when the project is COPIED?

    python3 -m swe.copyparity collect [--root PATH] [--json OUT]
    python3 -m swe.copyparity run     [--root PATH] [--json OUT] [--test-args "..."]
    python3 -m swe.copyparity escapes [--root PATH] [--json OUT]

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

A THIRD MODE, BECAUSE THE OTHER TWO CANNOT BE AFFORDED EVERY ROUND
-----------------------------------------------------------------
Round 425 measured both differential modes against the REAL subject
(`languages/whence`) for the first time -- every test in
`harness/tests/test_swe_copyparity.py` builds a toy project under `tmp_path`,
so the module that exists to catch this class had never been pointed at the
tree it was written for. The two costs are three orders of magnitude apart:

    collect    3.8 s   both sides summed, 2171 nodes each
    run      283.4 s   both sides summed (146.1 + 137.3), 2086 nodes each,
                       scoped `-m "not whence_slow"`. DEFAULT_TEST_CMD is
                       UNFILTERED, so the engine's own cost is higher than
                       this and 283 s is a floor, not the figure.

`run` is the only mode that sees the RUNTIME class -- a registry read inside
a test body, which is what actually stopped the engine in round 419 -- and at
74x the cheap mode it is too expensive to put in a per-round check. `collect` is affordable and
provably blind to that class (`test_collect_mode_is_blind_to_the_runtime_class`).
Wiring only the affordable one would install a checker that cannot see the
defect it was built for, which is worse than none: it reports green.

`escapes` is the way out. It never runs the suite at all. It parses each
`*.py` in the subtree and evaluates its path arithmetic SYMBOLICALLY, as a
depth below the subtree root: `__file__` in `tests/test_checkpin.py` is level
2, `dirname` subtracts one, a `join` component adds one and a literal `".."`
subtracts one. Level 0 is the root; **any expression reaching a negative
level names a path outside the tree**, which is the defect in one line of
arithmetic. It costs milliseconds, it sees both classes because it never
needed to execute anything, and it fires at authoring time rather than after
a campaign has already refused to start.

It is a STATIC check and therefore a hypothesis generator, not an oracle. It
cannot know that a path it reconstructs is ever opened, and it cannot follow
a level through a function call or a format string. Two guards keep the false
positives down and are reported rather than hidden:

  * an unknown `join` component counts +1, never -1, so an expression this
    module cannot follow drifts AWAY from the finding rather than toward it;
  * an escape reached through `AGI_RESEARCH_ROOT` -- the env var
    `swe/proc.py` exports into every sandbox it spawns, so it still points at
    the real checkout inside the copy -- is `env_guarded` and is NOT a
    finding. That is round 413's sanctioned root helper, and the whole point
    of it was that reaching outside THROUGH IT survives the copy.

Confirm any finding with `run` (or by reading the file) before calling it a
defect. The relationship between the three is not redundancy:

    escapes   ms      both classes, statically, as a hypothesis
    collect   s       import-time class only, confirmed by execution
    run       min     both classes, confirmed by execution
"""

import argparse
import ast
import io
import json
import os
import shlex
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swe import sandboxevidence as SE                         # noqa: E402
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
    """`{node_id: (status, detail)}` from a junit xml. Node id is
    `classname::name`, which is stable across two runs of the same suite in
    different directories (the `file` attribute is not emitted by every
    pytest).

    ROUND 431: an ADAPTER now, not a parser. This module used to read the
    XML itself and classified `<skipped type="pytest.xfail">` as `skipped`,
    while `pristine_check.parse_junit` -- written two rounds later for the
    same job one tree over -- excludes it. Two readers of the same file that
    disagree about the same node is a latent phantom: an xfail whose type
    attribute differs between the trees would have been reported here as a
    regression forever. Neither tree has an xfail today, which is the only
    reason it never fired. One parser now, and this is the thin end of it.
    """
    rec = SE.parse_junit(path)
    if not rec.get("ok"):
        return {}
    details = rec.get("details") or {}
    return {k: (v, (details.get(k) or "")[:400])
            for k, v in (rec.get("statuses") or {}).items()}


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

    #: ROUND 431. `regressions` merges two findings with OPPOSITE visibility
    #: to the engine, and merging them is why round 425's single instance
    #: read as one more red test rather than as a hole in the gate:
    #:
    #:   passed -> failed/error   the copy's exit code is non-zero, so
    #:                            `mutation.baseline_check` REFUSES to run
    #:                            the campaign. Loud, already handled.
    #:   passed -> skipped        both sides exit 0. Nothing in this repo
    #:                            saw it before `swe/sandboxevidence.py`.
    #:
    #: `regressions` is unchanged so every existing reader still works; these
    #: are views over it, and the summary prints the invisible class FIRST.
    @property
    def evaporated(self):
        """`passed -> skipped`: evidence lost with both sides exiting 0."""
        return [r for r in self.regressions if r[1] == "passed" and r[2] == "skipped"]

    @property
    def broken(self):
        """Every other regression: the ones an exit-code gate can see."""
        return [r for r in self.regressions if not (r[1] == "passed" and r[2] == "skipped")]

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
            # Round 431: additive views, see the properties.
            "evaporated": [{"node": n, "in_place": a, "copied": b, "detail": d}
                           for n, a, b, d in self.evaporated],
            "broken": [{"node": n, "in_place": a, "copied": b, "detail": d}
                       for n, a, b, d in self.broken],
            "n_evaporated": len(self.evaporated), "n_broken": len(self.broken),
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
        # Round 431: the class the exit code CANNOT see goes first, and says
        # so on its own line. Sorting by severity is not cosmetic here --
        # `EVAPORATED` is the only line in this report that names something
        # no other check in the repo would ever have told you about.
        for n, a, b, d in self.evaporated[:20]:
            lines.append("  EVAPORATED %-64s %s -> %s" % (n[:64], a, b))
            lines.append("             (both sides exit 0; no exit-code gate sees this)")
            if d:
                lines.append("             %s" % d.splitlines()[0][:100])
        if len(self.evaporated) > 20:
            lines.append("  ... and %d more evaporated" % (len(self.evaporated) - 20))
        for n, a, b, d in self.broken[:20]:
            lines.append("  REGRESSED  %-64s %s -> %s" % (n[:64], a, b))
            if d:
                lines.append("             %s" % d.splitlines()[0][:100])
        if len(self.broken) > 20:
            lines.append("  ... and %d more regressions" % (len(self.broken) - 20))
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


# ---------------------------------------------------------------------------
# `escapes` -- the static mode. See the module docstring.
# ---------------------------------------------------------------------------

#: Directories `mutation._copy_project` does not copy. A file under one of
#: these is not in the sandbox at all, so its path arithmetic cannot break
#: there. Kept as a literal rather than imported so that a change to the
#: ignore list shows up as a diff on BOTH sites instead of silently widening
#: this scan.
COPY_IGNORED_DIRS = frozenset((
    "__pycache__", ".pytest_cache", ".venv", "research-env", ".git",
    "node_modules"))

#: The sanctioned way to reach the repo root from inside a copied subtree.
#: `swe/proc.py` exports it into every subprocess it starts, so in the copy it
#: still names the REAL checkout. Round 413 introduced it as
#: `curecheck.AGI_ROOT`. An escape that goes through it is not a defect.
ROOT_ENV_VAR = "AGI_RESEARCH_ROOT"

#: Calls that pass a path through unchanged.
_IDENTITY_FUNCS = frozenset((
    "abspath", "realpath", "normpath", "resolve", "absolute", "expanduser",
    "fspath", "Path", "PurePath", "str"))


def _func_name(node):
    """Trailing attribute/name of a call target: `os.path.dirname` -> `dirname`."""
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def _component_delta(text):
    """`(net, floor)` for a literal path fragment, evaluated LEFT TO RIGHT.

    `".."` is -1, `"."` is 0, `"a/b"` is +2. A fragment is allowed to carry
    several components because `join(root, "../../state")` is one argument.

    ROUND 431 -- `floor` is the running MINIMUM, and it is the number that
    decides an escape. `"../../state"` nets +1 and dips to -2; the dip is
    what leaves the tree. See `_Escapes`.
    """
    delta, floor = 0, 0
    for part in text.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        delta += -1 if part == ".." else 1
        floor = min(floor, delta)
    return delta, floor


class _Escapes(ast.NodeVisitor):
    """Symbolic path-depth evaluation over one module.

    `levels` maps a variable name to its depth below the subtree root, when
    that depth is knowable. `file_level` is the depth of the module itself:
    `tests/test_checkpin.py` is 2, a top-level `run.py` is 1. Level 0 is the
    root directory and a negative level is outside the tree.

    Assignments are folded in source order across ALL scopes rather than
    per-scope. That is deliberately imprecise in the harmless direction: a
    module-level `ROOT` read inside a function body resolves, which is the
    common shape, and a same-named local in another function can only ever
    change WHICH escape is reported, never invent one -- the reported line
    still contains arithmetic that reaches the level it is reported at.

    ROUND 431 -- THE FINDING RULE IS THE FLOOR, NOT THE FINAL LEVEL
    ---------------------------------------------------------------
    Round 425 recorded an escape when the FINAL level was negative. That
    test is unsound, and unsound in the direction that matters: it misses
    the exact shape every recurrence of this class has had.

        REG_422 = os.path.join(HERE, "..", "..", "state", "whence", "round-422")

    `HERE` is the whence root (level 0), so this is 0 -1 -1 +1 +1 +1 = **+1**
    and round 425's rule says copy-safe. The path is
    `<repo>/state/whence/round-422`; in the sandbox it is
    `/tmp/xxx/proj/../../state/...`, which does not exist, and it took down
    17 tests and the whole mutation engine (round 431, measured). The final
    level is not even meaningful once the expression has left the tree: +1
    would mean "one level under the whence root", and the path is not under
    the whence root at all.

    A path that steps ABOVE the subtree root has left the tree whatever it
    does afterwards -- `os.path.join` does not normalise, so the `..` is
    resolved lexically by the OS at open time against a directory that, in
    the copy, is the tempdir. So the rule is the running minimum:

        floor < 0   <=>   this expression names something outside the tree

    `level` (the final depth) is still reported, because it is what tells a
    reader WHERE the expression landed. `floor` is what decides.

    Both round 425's own findings ended negative, which is why its rule
    looked adequate against them; neither of round 419's did.
    """

    def __init__(self, relpath, file_level, guarded_nodes):
        self.relpath = relpath
        self.file_level = file_level
        self.guarded = guarded_nodes
        self.levels = {}
        self.findings = {}          # lineno -> finding dict
        self._fn_depth = 0

    # -- level evaluation ---------------------------------------------------

    def level_of(self, node):
        """Depth below the root, or None when this is not a path we follow.

        The final level only. `evaluate` is what a caller deciding whether
        something escapes must use -- see the class docstring.
        """
        got = self.evaluate(node)
        return None if got is None else got[0]

    def evaluate(self, node):
        """`(level, floor)`, or None when this is not a path we follow.

        `level` is where the expression ends up; `floor` is the lowest level
        it passes through on the way, and a negative floor is the escape.
        """
        if isinstance(node, ast.Name):
            if node.id == "__file__":
                return (self.file_level, self.file_level)
            got = self.levels.get(node.id)
            return None if got is None else got
        if isinstance(node, ast.Attribute):
            # `X.parent` on a pathlib object.
            if node.attr == "parent":
                base = self.evaluate(node.value)
                return None if base is None else (base[0] - 1, min(base[1], base[0] - 1))
            return None
        if isinstance(node, ast.Subscript):
            # `X.parents[n]`
            v = node.value
            if isinstance(v, ast.Attribute) and v.attr == "parents":
                base = self.evaluate(v.value)
                idx = _const_int(node.slice)
                if base is not None and idx is not None:
                    end = base[0] - (idx + 1)
                    return (end, min(base[1], end))
            return None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            # `Path(__file__).parent / "x" / "y"`
            base = self.evaluate(node.left)
            if base is None:
                return None
            return self._apply(base, node.right)
        if isinstance(node, ast.Call):
            name = _func_name(node)
            if name is None or not node.args:
                return None
            if name in _IDENTITY_FUNCS:
                return self.evaluate(node.args[0])
            if name == "dirname":
                base = self.evaluate(node.args[0])
                return None if base is None else (base[0] - 1, min(base[1], base[0] - 1))
            if name == "join":
                base = self.evaluate(node.args[0])
                if base is None:
                    return None
                for extra in node.args[1:]:
                    base = self._apply(base, extra)
                return base
        return None

    def _apply(self, base, node):
        """Fold one `join`/`/` component onto a `(level, floor)` pair."""
        delta, dip = self._arg_delta(node)
        end = base[0] + delta
        return (end, min(base[1], base[0] + dip))

    def _arg_delta(self, node):
        """`(net, floor)` for one `join`/`/` component.

        An UNKNOWN component counts +1, never -1: a component this module
        cannot read must push the answer away from a finding, not toward one
        -- and that is true of the floor as well, since +1 can only raise the
        running minimum.
        """
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return _component_delta(node.value)
        if isinstance(node, ast.Attribute) and node.attr == "pardir":
            return (-1, -1)
        if isinstance(node, ast.Starred):
            return (1, 0)
        return (1, 0)

    # -- traversal ----------------------------------------------------------

    def visit_FunctionDef(self, node):
        self._fn_depth += 1
        self.generic_visit(node)
        self._fn_depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        self._fn_depth += 1
        self.generic_visit(node)
        self._fn_depth -= 1

    def visit_Assign(self, node):
        got = self.evaluate(node.value)
        if got is not None:
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    # The FLOOR is carried through the binding. `REG = join(
                    # HERE, "..", "..", "state")` followed by `join(REG, "x")`
                    # must still read as escaping: a name bound to a path
                    # outside the tree does not come back inside it.
                    self.levels[tgt.id] = got
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            got = self.evaluate(node.value)
            if got is not None and isinstance(node.target, ast.Name):
                self.levels[node.target.id] = got
        self.generic_visit(node)

    def generic_visit(self, node):
        got = self.evaluate(node) if isinstance(
            node, (ast.Call, ast.Attribute, ast.Subscript, ast.BinOp)) else None
        if got is not None and got[1] < 0:
            self._record(node, got[0], got[1])
        ast.NodeVisitor.generic_visit(self, node)

    def _record(self, node, lvl, floor):
        line = getattr(node, "lineno", 0)
        prev = self.findings.get(line)
        # One finding per line, keeping the DEEPEST escape on it: nested
        # subexpressions of a single escaping expression are one defect.
        # Ranked on the FLOOR, since that is what makes it a finding.
        if prev is not None and prev.get("floor", prev["level"]) <= floor:
            return
        self.findings[line] = {
            "file": self.relpath,
            "line": line,
            "level": lvl,
            "floor": floor,
            "kind": "runtime" if self._fn_depth else "import_time",
            "env_guarded": _has_guarded_ancestor(node, self.guarded),
            "expr": _snippet(node),
        }


def _const_int(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    # py<3.9 wrapped subscripts in ast.Index
    inner = getattr(node, "value", None)
    if isinstance(inner, ast.Constant) and isinstance(inner.value, int):
        return inner.value
    return None


def _snippet(node):
    try:
        return ast.unparse(node)[:160]
    except Exception:                              # pragma: no cover - py<3.9
        return "<expr>"


def _guarded_nodes(tree):
    """Sub-expressions that only run when `ROOT_ENV_VAR` is absent.

    Two shapes, both of them round 413's helper written out:
        os.environ.get(AGI_RESEARCH_ROOT) or <fallback>
        os.environ.get(AGI_RESEARCH_ROOT, <fallback>)
    """
    guarded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            seen_env = False
            for value in node.values:
                if seen_env:
                    guarded.add(value)
                if _mentions_env(value):
                    seen_env = True
        elif isinstance(node, ast.Call) and _func_name(node) == "get" \
                and len(node.args) == 2 and _mentions_env(node.args[0]):
            guarded.add(node.args[1])
    return guarded


def _mentions_env(node):
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and sub.value == ROOT_ENV_VAR:
            return True
        if isinstance(sub, ast.Name) and sub.id == ROOT_ENV_VAR:
            return True
    return False


def _has_guarded_ancestor(node, guarded):
    if not guarded:
        return False
    for g in guarded:
        if g is node:
            return True
        for sub in ast.walk(g):
            if sub is node:
                return True
    return False


def scan_escapes(root=WHENCE_ROOT):
    """Every path expression in `root`'s `*.py` files that reaches outside it.

    Returns `(findings, stats)`. A finding with `env_guarded` true is
    reported but is not a defect -- see the module docstring.
    """
    root = os.path.abspath(root)
    findings, n_files, unreadable = [], 0, []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in COPY_IGNORED_DIRS]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            n_files += 1
            try:
                src = io.open(full, encoding="utf-8").read()
                tree = ast.parse(src, filename=full)
            except (SyntaxError, UnicodeDecodeError, OSError) as exc:
                unreadable.append({"file": rel, "error": str(exc)[:200]})
                continue
            file_level = len(rel.replace(os.sep, "/").split("/"))
            v = _Escapes(rel, file_level, _guarded_nodes(tree))
            v.visit(tree)
            findings.extend(v.findings[k] for k in sorted(v.findings))
    findings.sort(key=lambda f: (f["file"], f["line"]))
    real = [f for f in findings if not f["env_guarded"]]
    stats = {
        "root": root,
        "n_files": n_files,
        "n_findings": len(real),
        "n_env_guarded": len(findings) - len(real),
        "n_import_time": sum(1 for f in real if f["kind"] == "import_time"),
        "n_runtime": sum(1 for f in real if f["kind"] == "runtime"),
        "files_with_findings": sorted({f["file"] for f in real}),
        "unreadable": unreadable,
    }
    return findings, stats


def escapes_summary(findings, stats):
    real = [f for f in findings if not f["env_guarded"]]
    head = ("copyparity(escapes): %s — %d file(s) scanned, %d escaping "
            "expression(s) (%d import-time, %d runtime), %d env-guarded"
            % ("copy_safe" if not real else "copy_breaks",
               stats["n_files"], stats["n_findings"], stats["n_import_time"],
               stats["n_runtime"], stats["n_env_guarded"]))
    lines = [head]
    if stats["n_files"] == 0:
        lines.append("  NO FILE WAS SCANNED — a scan that read nothing is not "
                     "a verdict (see the module docstring's first pitfall)")
    for f in real:
        # `floor` is the finding; `level` is where it landed. Printing both
        # is the difference between "this leaves the tree" and "this ends up
        # above the tree", and round 431 exists because the second was
        # mistaken for the first.
        lines.append("  ESCAPES  %s:%d  floor %d (ends at level %d)  [%s]"
                     % (f["file"], f["line"], f.get("floor", f["level"]),
                        f["level"], f["kind"]))
        lines.append("           %s" % f["expr"])
    for f in findings:
        if f["env_guarded"]:
            lines.append("  guarded  %s:%d  reaches level %d through %s"
                         % (f["file"], f["line"], f.get("floor", f["level"]),
                            ROOT_ENV_VAR))
    for u in stats["unreadable"]:
        lines.append("  UNREADABLE %s — %s" % (u["file"], u["error"]))
    if not real and stats["n_files"]:
        lines.append("  no expression resolves above the subtree root")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=["collect", "run", "escapes"])
    ap.add_argument("--root", default=WHENCE_ROOT)
    ap.add_argument("--test-args", default=None,
                    help="replace DEFAULT_TEST_CMD's pytest args, e.g. '-q tests/test_v01.py'")
    ap.add_argument("--timeout", type=float, default=2400.0)
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    if a.mode == "escapes":
        findings, stats = scan_escapes(root=a.root)
        print(escapes_summary(findings, stats))
        if a.json:
            with open(a.json, "w", encoding="utf-8") as f:
                json.dump({"mode": "escapes", "stats": stats,
                           "findings": findings}, f, indent=1)
            print("wrote %s" % a.json)
        # A scan that read NO file is not a verdict. Round 419's first
        # differential reported `0 node(s)` on both sides and called the
        # whence tree copy_safe; the same shape here would be a green exit
        # for an empty scan, so it exits 2 instead.
        if not stats["n_files"]:
            return 2
        return 0 if stats["n_findings"] == 0 else 1
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

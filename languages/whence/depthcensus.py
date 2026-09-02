#!/usr/bin/env python3
"""How deep are the values Whence programs actually build?

Round 452 (language C). Round 450's next-step 1 asked a question this repo
had never taken a number for:

    "`SHOW_NEST` is now the only thing between a reader and a deep miss, and
    nothing measures how often that bites. ... The open question is whether
    the FULL rendering should carry a depth-bounded-but-deeper cap of its
    own ... and it needs a number: the deepest value any corpus program
    actually builds. Nobody has measured that."

This module is that measurement, landed as an ARTEFACT rather than run once
as a script, so the next round to ask re-derives the number instead of
quoting round 452's.

THE METRIC, defined before it was taken (state/whence/round-452/
PREDICTIONS.md fixes this text):

    D(p) = 0                                     for every non-container
                                                 payload (int, float, bool,
                                                 str, Miss, Closure, Builtin,
                                                 Explanation)
    D(WList)  = 1 + max(D(e.payload) for e in p)   (1 when empty)
    D(Record) = 1 + max(D(v.payload) for v in p)   (1 when empty)
    D(Guess)  = 1 + D(p.node.payload)

`Guess` costs a level because `values._show`'s `Guess` branch descends with
`nest + 1` exactly as a container branch does. The metric is lined up with
the renderer's own `nest` counter on purpose, so the two compare with no
conversion: `full_show` renders a top-level container's ELEMENTS at
`nest = 0` and `_show` descends only while `nest < SHOW_NEST`, so the full
rendering shows `SHOW_NEST + 1` container levels. Hence

    a printed value is rendered IN FULL iff D(p) <= FULL_LEVELS

and `FULL_LEVELS` is derived from `values.SHOW_NEST` here rather than
written down, so raising the cap moves this instrument with it.

TWO POPULATIONS, KEPT APART. Conflating them is the mistake this module
exists to avoid — a value can be built far deeper than anything ever
printed, and the renderer's cap is a claim about the second population while
"what does the language build" is a claim about the first.

    BUILT   — max D over every payload reachable in a finished program's
              provenance graph.
    PRINTED — max D over the payloads that actually reached `full_show`.

THE ROOT SET, and what it does and does not reach. Whence retains history
(`values.Prov` holds its `inputs`), so a walk over provenance edges from a
small root set reaches every value that CONTRIBUTED to a root. The roots are

    (a) every binding in the top-level `Env` the run returns;
    (b) every value handed to `Interpreter._note_drop` — which its own
        docstring says is called from "the three places a statement value is
        thrown away", i.e. `run`'s top level AND the two block evaluators, so
        this reaches statements discarded INSIDE a function body too;
    (c) every payload handed to `full_show`.

(b) is the one that matters and it is why this module hooks `_note_drop`
rather than wrapping `exec_stmt`: the interpreter already calls it at every
level for exactly the values nothing keeps, at no extra cost, and those are
precisely the values a root set built from surviving bindings would miss.
`--roots env` measures the naive root set for comparison; the difference
between the two is reported rather than assumed to be zero.

WHAT IT STILL DOES NOT REACH, stated rather than left for a reader to find:
a value that is neither bound, nor a discarded statement's value, nor
printed, nor an input to any of those. An intermediate sub-expression is an
input and is reached. `--roots env` vs the default measures the size of the
class that the naive set misses; nothing here measures the residual class,
and `deepest_at_budget` reports when a walk stopped early instead of
returning a clean number it did not earn.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from whence import interp as interp_mod                 # noqa: E402
from whence.interp import Interpreter                   # noqa: E402
from whence.lexer import LexError                       # noqa: E402
from whence.parser import ParseError                    # noqa: E402
from whence import values as values_mod                 # noqa: E402
from whence.values import (                             # noqa: E402
    FULL_SHOW_NEST, Guess, Record, SHOW_NEST, WList,
)

ROOT = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(ROOT, "examples")

# The number of container levels the FULL rendering shows. Derived, not
# written: `full_show` renders a container's elements at nest 0 and the walk
# descends while `nest < FULL_SHOW_NEST`.
#
# It read `SHOW_NEST + 1` when this module was written, because until v0.44
# the full rendering and the bounded snapshot shared one constant — and this
# census is the measurement that split them (decision 53). Pointing it at
# `FULL_SHOW_NEST` is what makes the instrument re-derive the answer instead
# of re-asserting round 452's: raise the cap and `programs_over_full_cap`
# falls out of the same code.
FULL_LEVELS = FULL_SHOW_NEST + 1

# The bounded snapshot (`show()`, every miss message, `Prov.show`) renders a
# container at nest 0 through `show_payload`, one level shallower than
# `full_show` does.
SNAPSHOT_LEVELS = SHOW_NEST

# Walk budgets. Both are reported when hit; neither is allowed to make an
# incomplete answer look complete (v0.42's rule for `dropped_scan_truncated`,
# applied to this instrument).
DEFAULT_MAX_NODES = 3000000
DEFAULT_MAX_ROOTS = 400000

# run.py raises the limit for its own main thread; direct mode sizes its
# frame budget from whatever is live. Mirrored here so the census evaluates
# the same programs the same way the CLI does.
CLI_RECURSION_LIMIT = 6000

# The two substrings `_show` emits when it stops at the nest cap.
NEST_MARKERS = ("[…]", "@{…}")


def struct_children(p):
    """The payload's structural children as `Prov` nodes, or None if `p` is
    a leaf. Mirrors `values._show`'s descending branches node for node."""
    if isinstance(p, WList):
        return list(p)
    if isinstance(p, Record):
        return [v for _, v in p.fields.items()]
    if isinstance(p, Guess):
        return [p.node]
    return None


def depth_of(root, memo=None, alive=None):
    """D(root.payload), iteratively and memoised by node identity.

    No host recursion: this codebase never recurses on the host stack for
    guest-scale data, and a census whose own renderer-depth measurement blew
    the stack would be a joke. `alive` holds a reference to every node whose
    id is in `memo`, because an id is only a valid key while its object
    lives.
    """
    if memo is None:
        memo = {}
    if alive is None:
        alive = []
    stack = [(root, False)]
    while stack:
        node, expanded = stack.pop()
        nid = id(node)
        if nid in memo:
            continue
        kids = struct_children(getattr(node, "value", None))
        if kids is None:
            memo[nid] = 0
            alive.append(node)
            continue
        if not expanded:
            stack.append((node, True))
            for k in kids:
                if id(k) not in memo:
                    stack.append((k, False))
            continue
        best = 1
        for k in kids:
            # A missing child depth can only happen on a cycle, which
            # immutable bottom-up construction cannot produce; treated as 0
            # rather than crashing, and `cycle_suspected` says so.
            dk = memo.get(id(k), 0)
            if dk + 1 > best:
                best = dk + 1
        memo[nid] = best
        alive.append(node)
    return memo[id(root)]


def spine_of(root):
    """Kind names along one deepest structural path, root first.

    Answers "what SHAPE is the deep thing" — a homogeneous list-of-lists and
    a record/list alternation are different findings about the language and
    the same number.
    """
    memo, alive = {}, []
    depth_of(root, memo, alive)
    out = []
    node = root
    while True:
        p = getattr(node, "value", None)
        kids = struct_children(p)
        if kids is None:
            out.append(type(p).__name__ if p is not None else "None")
            return out
        out.append(type(p).__name__)
        if not kids:
            return out
        node = max(kids, key=lambda k: memo.get(id(k), 0))


def reachable(roots, max_nodes=DEFAULT_MAX_NODES):
    """Every `Prov` node reachable from `roots` over provenance edges
    (`node.inputs`) AND structure edges. Returns (nodes, truncated)."""
    seen = set()
    out = []
    stack = [r for r in roots if r is not None]
    truncated = False
    while stack:
        n = stack.pop()
        nid = id(n)
        if nid in seen:
            continue
        if len(out) >= max_nodes:
            truncated = True
            break
        seen.add(nid)
        out.append(n)
        ins = getattr(n, "_ins", None)
        if ins is not None:
            if type(ins) is tuple:
                stack.extend(ins)
            else:
                stack.append(ins)
        kids = struct_children(getattr(n, "value", None))
        if kids:
            stack.extend(kids)
    return out, truncated


def _is_node(x):
    return hasattr(x, "_ins") and hasattr(x, "value")


class _Recorder(object):
    """Captures the two things a census run needs that the interpreter does
    not already hand back: the values statements threw away, and the
    payloads `print` rendered in full."""

    def __init__(self, max_roots=DEFAULT_MAX_ROOTS):
        self.dropped = []
        self.printed = []
        self.printed_text = []
        self.max_roots = max_roots
        self.roots_capped = False

    def note_drop(self, v):
        if _is_node(v):
            if len(self.dropped) < self.max_roots:
                self.dropped.append(v)
            else:
                self.roots_capped = True

    def note_print(self, payload, text):
        if len(self.printed) < self.max_roots:
            self.printed.append(payload)
            self.printed_text.append(text)
        else:
            self.roots_capped = True


def census_program(path, roots="all", max_nodes=DEFAULT_MAX_NODES,
                   max_roots=DEFAULT_MAX_ROOTS):
    """Run one program and measure both depth populations.

    The interpreter is patched for the duration of the run and restored in a
    `finally`, because this module is imported by a test suite that runs in
    the same process as everything else.
    """
    rec = _Recorder(max_roots)
    result = {
        "program": os.path.basename(path),
        "ok": True,
        "error": "",
        "built_depth": 0,
        "built_nodes": 0,
        "built_truncated": False,
        "printed_depth": 0,
        "printed_values": 0,
        "printed_over_cap": 0,
        "printed_marker_lines": 0,
        "deepest_at_budget": False,
        "roots_capped": False,
        "deepest_spine": [],
        "deepest_root": "",
        "drop_roots": 0,
        "env_roots": 0,
    }
    try:
        src = open(path).read()
    except IOError as e:
        result["ok"] = False
        result["error"] = "read: %s" % e
        return result

    # v0.44 note, and a lesson this module paid for. The hook used to be on
    # `full_show`, and decision 53 moved `b_print` onto `full_show_named` —
    # so the census silently stopped seeing `print` and kept reporting a
    # printed-depth number, one lower, with no error. An instrument that
    # hooks the FUNCTION rather than the WALK measures whichever callers
    # happen to still go through that name. `full_show` delegates to
    # `full_show_named`, so hooking the walk catches `print`, `str` and any
    # future caller, and catches each exactly once.
    real_full_show_named = values_mod.full_show_named
    real_note_drop = Interpreter._note_drop
    old_limit = sys.getrecursionlimit()

    def hooked_full_show_named(node, *a, **kw):
        r = real_full_show_named(node, *a, **kw)
        rec.note_print(getattr(node, "payload", None), r.text)
        return r

    def hooked_note_drop(self, v, at):
        rec.note_drop(v)
        return real_note_drop(self, v, at)

    env = None
    it = None
    try:
        sys.setrecursionlimit(max(old_limit, CLI_RECURSION_LIMIT))
        values_mod.full_show_named = hooked_full_show_named
        interp_mod.full_show_named = hooked_full_show_named
        Interpreter._note_drop = hooked_note_drop
        it = Interpreter(out=lambda _s: None, gc_relief=True)
        try:
            env = it.run(src)
        except (LexError, ParseError) as e:
            result["ok"] = False
            result["error"] = "parse: %s" % e
        except RecursionError as e:
            result["ok"] = False
            result["error"] = "recursion: %s" % e
        except Exception as e:                      # noqa: BLE001
            result["ok"] = False
            result["error"] = "%s: %s" % (type(e).__name__, e)
    finally:
        values_mod.full_show_named = real_full_show_named
        interp_mod.full_show_named = real_full_show_named
        Interpreter._note_drop = real_note_drop
        sys.setrecursionlimit(old_limit)

    env_roots = []
    if env is not None:
        e = env
        while e is not None:
            env_roots.extend(v for v in e.vars.values() if _is_node(v))
            e = e.parent
    result["env_roots"] = len(env_roots)
    result["drop_roots"] = len(rec.dropped)
    result["roots_capped"] = rec.roots_capped

    if roots == "env":
        all_roots = list(env_roots)
    else:
        all_roots = list(env_roots) + list(rec.dropped)

    nodes, truncated = reachable(all_roots, max_nodes)
    result["built_nodes"] = len(nodes)
    result["built_truncated"] = truncated
    result["deepest_at_budget"] = truncated

    memo, alive = {}, []
    best_d = 0
    # Seeded with the first node rather than None so a corpus of pure
    # scalars still reports a spine: "the deepest value is an int" is an
    # answer, and a blank column reads like a bug in the instrument.
    best_node = nodes[0] if nodes else None
    for n in nodes:
        d = depth_of(n, memo, alive)
        if d > best_d:
            best_d, best_node = d, n
    result["built_depth"] = best_d
    if best_node is not None:
        result["deepest_spine"] = spine_of(best_node)
        result["deepest_root"] = best_node.label() or best_node.op or "?"

    # PRINTED: the payloads that reached `full_show`. Their nodes are not
    # available (full_show takes a payload), so depth is computed on a
    # throwaway shim node rather than by duplicating the walk.
    pmemo, palive = {}, []
    pd = 0
    over = 0
    for p in rec.printed:
        d = _payload_depth(p, pmemo, palive)
        if d > pd:
            pd = d
        if d > FULL_LEVELS:
            over += 1
    result["printed_depth"] = pd
    result["printed_values"] = len(rec.printed)
    result["printed_over_cap"] = over
    result["printed_marker_lines"] = sum(
        1 for t in rec.printed_text if any(m in t for m in NEST_MARKERS))
    return result


class _Shim(object):
    """A stand-in `Prov` for a bare payload: `depth_of` reads `.value`."""
    __slots__ = ("value", "_ins")

    def __init__(self, value):
        self.value = value
        self._ins = ()


def _payload_depth(p, memo=None, alive=None):
    return depth_of(_Shim(p), memo, alive)


def payload_depth(p):
    """D(p) for a bare payload. The public entry point for a caller that has
    a payload rather than a node."""
    return _payload_depth(p)


def corpus_paths(directory=EXAMPLES):
    return sorted(os.path.join(directory, f)
                  for f in os.listdir(directory) if f.endswith(".lang"))


def census(paths=None, roots="all", max_nodes=DEFAULT_MAX_NODES,
           max_roots=DEFAULT_MAX_ROOTS, progress=None):
    paths = corpus_paths() if paths is None else paths
    out = []
    for p in paths:
        if progress:
            progress(p)
        out.append(census_program(p, roots, max_nodes, max_roots))
    return out


def summarise(rows):
    ok = [r for r in rows if r["ok"]]
    printed = [r for r in ok if r["printed_values"]]
    deeper = [r for r in ok if r["built_depth"] > r["printed_depth"]
              and r["printed_values"]]
    over = [r for r in ok if r["built_depth"] > FULL_LEVELS]
    return {
        "programs": len(rows),
        "ran": len(ok),
        "failed": len(rows) - len(ok),
        "full_levels": FULL_LEVELS,
        "snapshot_levels": SNAPSHOT_LEVELS,
        "max_built_depth": max([r["built_depth"] for r in ok] or [0]),
        "max_printed_depth": max([r["printed_depth"] for r in ok] or [0]),
        "programs_printing": len(printed),
        "built_deeper_than_printed": len(deeper),
        "programs_over_full_cap": len(over),
        "programs_over_full_cap_names": [r["program"] for r in over],
        "printed_values_over_cap": sum(r["printed_over_cap"] for r in ok),
        "printed_marker_lines": sum(r["printed_marker_lines"] for r in ok),
        "total_nodes": sum(r["built_nodes"] for r in ok),
        "truncated_walks": [r["program"] for r in ok if r["built_truncated"]],
        "deepest_program": max(ok, key=lambda r: r["built_depth"])["program"]
        if ok else "",
    }


def render(rows, summary):
    w = max([len(r["program"]) for r in rows] or [7])
    lines = ["%-*s  %5s %5s %8s %6s  %s"
             % (w, "program", "built", "print", "nodes", "prints", "spine")]
    for r in sorted(rows, key=lambda r: (-r["built_depth"], r["program"])):
        if not r["ok"]:
            lines.append("%-*s  %s" % (w, r["program"], "FAILED: " + r["error"]))
            continue
        lines.append("%-*s  %5d %5d %8d %6d  %s%s"
                     % (w, r["program"], r["built_depth"], r["printed_depth"],
                        r["built_nodes"], r["printed_values"],
                        ">".join(r["deepest_spine"]),
                        "  [BUDGET]" if r["built_truncated"] else ""))
    lines.append("")
    lines.append("full rendering shows %d container levels (SHOW_NEST=%d); "
                 "snapshot shows %d"
                 % (summary["full_levels"], SHOW_NEST,
                    summary["snapshot_levels"]))
    lines.append("max BUILT depth %d (%s); max PRINTED depth %d"
                 % (summary["max_built_depth"], summary["deepest_program"],
                    summary["max_printed_depth"]))
    lines.append("programs building past the full cap: %d %s"
                 % (summary["programs_over_full_cap"],
                    summary["programs_over_full_cap_names"]))
    lines.append("printed values past the full cap: %d; "
                 "printed lines carrying a nest marker: %d"
                 % (summary["printed_values_over_cap"],
                    summary["printed_marker_lines"]))
    lines.append("built deeper than printed: %d of %d programs that print"
                 % (summary["built_deeper_than_printed"],
                    summary["programs_printing"]))
    lines.append("nodes walked: %d; walks stopped at budget: %s"
                 % (summary["total_nodes"], summary["truncated_walks"] or "none"))
    return "\n".join(lines)


def main(argv):
    args = argv[1:]
    out_json = None
    roots = "all"
    paths = None
    max_nodes = DEFAULT_MAX_NODES
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--json":
            out_json = args[i + 1]
            i += 2
        elif a == "--roots":
            roots = args[i + 1]
            i += 2
        elif a == "--max-nodes":
            max_nodes = int(args[i + 1])
            i += 2
        elif a == "--program":
            paths = (paths or []) + [
                args[i + 1] if os.path.sep in args[i + 1]
                else os.path.join(EXAMPLES, args[i + 1])]
            i += 2
        else:
            sys.stderr.write("usage: depthcensus.py [--roots all|env] "
                             "[--program NAME] [--max-nodes N] [--json OUT]\n")
            return 2
        continue
    rows = census(paths, roots, max_nodes,
                  progress=lambda p: sys.stderr.write(
                      "  %s\n" % os.path.basename(p)))
    summary = summarise(rows)
    print(render(rows, summary))
    if out_json:
        with open(out_json, "w") as fh:
            json.dump({"roots": roots, "summary": summary, "programs": rows},
                      fh, indent=1, sort_keys=True)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

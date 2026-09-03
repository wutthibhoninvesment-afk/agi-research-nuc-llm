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

import ast
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from whence import interp as interp_mod                 # noqa: E402
from whence.interp import Interpreter                   # noqa: E402
from whence import parser as parse_mod                 # noqa: E402
from whence.lexer import LexError                       # noqa: E402
from whence.parser import ParseError                    # noqa: E402
from whence import values as values_mod                 # noqa: E402
from whence.values import (                             # noqa: E402
    FULL_SHOW_NEST, FULL_SHOW_NODES, Guess, Record, SHOW_NEST, WList,
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

# The guest recursion cap the interpreter uses when a caller names none.
# Read from the interpreter rather than written down, for the same reason
# FULL_LEVELS is derived: decision 53's error was quoting a default as if it
# were a measurement.
DEFAULT_GUEST_MAX_DEPTH = Interpreter.DEFAULT_MAX_DEPTH

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
                   max_roots=DEFAULT_MAX_ROOTS, alloc=True, src=None,
                   max_depth=None):
    """Run one program and measure both depth populations.

    The interpreter is patched for the duration of the run and restored in a
    `finally`, because this module is imported by a test suite that runs in
    the same process as everything else.

    `src` supplies the program text directly, for the test-corpus harvest,
    where there is no file to read and `path` is a `file.py:line` label.
    `max_depth` is the guest recursion cap to run it under; None means the
    interpreter default. It is a PARAMETER and not a constant because the
    depth a program is run at is a property of its runner -- see the
    harvester section, and decision 53.
    """
    rec = _Recorder(max_roots)
    result = {
        "program": os.path.basename(path),
        "max_depth": (DEFAULT_GUEST_MAX_DEPTH if max_depth is None
                      else max_depth),
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
        # The allocation census (round 456). `alloc_*` is the population with
        # no root set: every value the run constructed.
        "alloc_on": bool(alloc),
        "alloc_depth": 0,
        "alloc_size": 0,
        "alloc_nodes": 0,
        "alloc_spine": [],
        "alloc_root": "",
        "alloc_size_root": "",
        "alloc_depth_reachable": None,
        "alloc_size_reachable": None,
        "alloc_capped": False,
        # The width bound, decided in the three cases the module comment sets
        # out. `width_fired` counts values a full rendering really does stop
        # rendering for lack of node budget -- measured on the renderer, not
        # modelled.
        "width_over_n": 0,
        "width_fires_by_arithmetic": 0,
        "width_sampled": 0,
        "width_sample_complete": True,
        "width_fired": 0,
        "width_depth_stopped_first": 0,
        # Measured separately from `seconds` because it happens AFTER the
        # run: `seconds` would otherwise report 4.39 s for a program the
        # census spends 2m36s on, and an instrument that hides its own cost
        # is the shape this program keeps finding.
        "width_seconds": 0.0,
        # Cross-check: the champion's D and N recomputed by the ORDINARY
        # walks (`depth_of` / `_payload_size`), which share no code with the
        # constructor-time arithmetic. A disagreement means the incremental
        # instrument is wrong, and it is reported rather than reconciled.
        "alloc_depth_check": None,
        "alloc_size_check": None,
        "alloc_agrees": None,
        "alloc_slow_views": 0,
        "alloc_over_node_budget": False,
        "seconds": 0.0,
    }
    if src is None:
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
    global _TRACKER
    saved_classes = []
    tracker = _AllocTracker() if alloc else None
    started = time.time()
    try:
        sys.setrecursionlimit(max(old_limit, CLI_RECURSION_LIMIT))
        values_mod.full_show_named = hooked_full_show_named
        interp_mod.full_show_named = hooked_full_show_named
        Interpreter._note_drop = hooked_note_drop
        if alloc:
            _TRACKER = tracker
            saved_classes = _install_counting(*_counting_classes())
        it = Interpreter(out=lambda _s: None, gc_relief=True,
                         max_depth=result["max_depth"])
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
        _restore_counting(saved_classes)
        _TRACKER = None
        values_mod.full_show_named = real_full_show_named
        interp_mod.full_show_named = real_full_show_named
        Interpreter._note_drop = real_note_drop
        sys.setrecursionlimit(old_limit)
        result["seconds"] = round(time.time() - started, 2)

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

    if tracker is not None:
        result["alloc_depth"] = tracker.best_d
        result["alloc_size"] = tracker.best_n
        result["alloc_nodes"] = tracker.count
        result["alloc_capped"] = tracker.capped
        result["alloc_slow_views"] = tracker.slow_views
        result["width_over_n"] = tracker.over_n
        result["width_fires_by_arithmetic"] = tracker.over_n_decided
        result["width_sampled"] = len(tracker.over_samples)
        result["width_sample_complete"] = tracker.sample_full
        fired = 0
        depth_first = 0
        w0 = time.time()
        for cand in tracker.over_samples:
            r = values_mod.full_show_named(cand)
            if r.node_stopped:
                fired += 1
            elif r.depth_stopped:
                depth_first += 1
        result["width_seconds"] = round(time.time() - w0, 2)
        result["width_fired"] = fired + tracker.over_n_decided
        result["width_depth_stopped_first"] = depth_first
        result["alloc_over_node_budget"] = result["width_fired"] > 0
        # `nodes` is alive for the whole of this block, so its ids are valid
        # keys -- the same rule `depth_of`'s `alive` list follows. The
        # tracker holds its champions, so theirs are too.
        walked = set(id(n) for n in nodes)
        if tracker.best_d_node is not None:
            result["alloc_spine"] = spine_of(tracker.best_d_node)
            result["alloc_root"] = (tracker.best_d_node.label()
                                    or tracker.best_d_node.op or "?")
            result["alloc_depth_reachable"] = (
                id(tracker.best_d_node) in walked)
        if tracker.best_n_node is not None:
            result["alloc_size_root"] = (tracker.best_n_node.label()
                                         or tracker.best_n_node.op or "?")
            result["alloc_size_reachable"] = (
                id(tracker.best_n_node) in walked)
        agrees = True
        if tracker.best_d_node is not None:
            chk = depth_of(tracker.best_d_node)
            result["alloc_depth_check"] = chk
            agrees = agrees and chk == tracker.best_d
        if tracker.best_n_node is not None:
            chk = _payload_size(tracker.best_n_node.value)
            result["alloc_size_check"] = chk
            agrees = agrees and chk == tracker.best_n
        result["alloc_agrees"] = agrees

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


# ---------------------------------------------------------------------------
# The ALLOCATION census (round 456). Sizes the class round 452's docstring
# named and could not measure:
#
#     "a value that is neither bound, nor a discarded statement's value, nor
#      printed, nor an input to any of those. ... nothing here measures the
#      residual class"
#
# The root-set census answers "how deep is the deepest value the program's
# provenance graph RETAINS". This one answers "how deep is the deepest value
# the program ever BUILDS", by measuring at construction: `Prov` and
# `MergedProv` are replaced for the duration of a run by subclasses that
# compute D and N in the constructor and keep the champion. There is no root
# set, so there is no residual — the population is every value that existed.
#
# Two quantities, because decision 53 shipped TWO constants and only one of
# them ever had a population measured:
#
#     D  depth, exactly the metric at the top of this file, so the two
#        censuses' numbers are directly comparable (`alloc_depth` vs
#        `built_depth`) and their difference IS the residual.
#     N  structural size: 1 for a leaf, 1 + sum(N of children) for a
#        container -- the size of the value's TREE UNFOLDING, which is what
#        `values._show` walks (it re-descends into shared sub-structure; its
#        `seen` set is for misses, not for dedup). Round 452 measured N over
#        PRINTED values only.
#
# `N > FULL_SHOW_NODES` is NOT the condition under which a rendering stops on
# the width bound, and this comment said it was until the measurement refuted
# it: `self_eval.lang` builds a value with N = 3.26e91 and `full_show` on it
# reports `node_stopped=False`, because the DEPTH cap truncates the walk
# after 25 levels and the truncated unfolding is under 20 000 nodes. The
# renderer never walks N; it walks N restricted to `FULL_SHOW_NEST` levels.
# So the census decides the width question in two exact cases and one
# measured one:
#
#   N <= FULL_SHOW_NODES                  -> cannot fire (the truncation is
#                                            a subset)
#   N >  FULL_SHOW_NODES and D <= cap     -> fires (truncation is a no-op)
#   N >  FULL_SHOW_NODES and D >  cap     -> undecided by arithmetic; the
#                                            census RENDERS the node and
#                                            reads `node_stopped` off the
#                                            real renderer.
#
# The third case is sampled, bounded by ALLOC_BUDGET_SAMPLES, and the census
# says whether the sample was complete.
#
# COST CONTROL, and why this is not O(n^2). A node's payload is usually a
# payload some other node already carries (`Prov("call", ..., result, ...,
# result.value)` re-wraps), and a `WList` is a length-bounded view over an
# append-only shared buffer (`values.WList`), so a list grown by `push`
# produces n views over ONE buffer. Recomputing `max` over the elements of
# each view would be quadratic in the length of every list any program
# builds. Instead:
#
#   * a container payload identical (by `is`) to an input node's payload
#     copies that node's D and N in O(1);
#   * `WList` uses per-BUFFER prefix aggregates, valid because the buffer is
#     append-only, so view n costs O(1) amortised;
#   * a buffer entry holds a reference to its buffer, because an `id` is
#     only a valid key while its object lives (the same rule `depth_of`'s
#     `alive` list follows).
#
# Both caps are reported when hit; neither is allowed to make an incomplete
# answer look complete.

ALLOC_BUF_CELLS = 4000000
ALLOC_BUFS = 200000
# Round 456: 400 was a placeholder; the corpus's only over-budget program
# has 15 178 such values and an exhaustive answer beats a sampled one, so the
# bound is set above that and the census reports when it was not enough.
ALLOC_BUDGET_SAMPLES = int(os.environ.get("WHENCE_ALLOC_BUDGET_SAMPLES",
                                          "20000"))


class _AllocTracker(object):
    """Depth and size of every value constructed during one program run."""

    __slots__ = ("count", "best_d", "best_d_node", "best_n", "best_n_node",
                 "bufs", "cells", "capped", "slow_views",
                 "over_n", "over_n_decided", "over_samples", "sample_full")

    def __init__(self):
        self.count = 0
        self.best_d = 0
        self.best_d_node = None
        self.best_n = 0
        self.best_n_node = None
        self.bufs = {}
        self.cells = 0
        self.capped = False
        self.slow_views = 0
        # Width-bound bookkeeping (see the module comment's three cases).
        self.over_n = 0            # N > FULL_SHOW_NODES, any depth
        self.over_n_decided = 0    # ... and D <= cap, so the budget FIRES
        self.over_samples = []     # ... and D > cap, to be rendered
        self.sample_full = True

    # -- the two container shapes that need help ------------------------
    def _wlist(self, p):
        buf, n = p.buf, p.n
        key = id(buf)
        ent = self.bufs.get(key)
        if ent is None:
            if self.capped or self.cells >= ALLOC_BUF_CELLS or \
                    len(self.bufs) >= ALLOC_BUFS:
                self.capped = True
                self.slow_views += 1
                d, tot = 0, 0
                i = 0
                while i < n:
                    k = buf[i]
                    kd = getattr(k, "_d", 0)
                    if kd > d:
                        d = kd
                    tot += getattr(k, "_n", 1)
                    i += 1
                return 1 + d, 1 + tot
            ent = [buf, [0], [0]]
            self.bufs[key] = ent
        dpref, npref = ent[1], ent[2]
        have = len(dpref) - 1
        if have < n:
            i = have
            while i < n:
                k = buf[i]
                kd = getattr(k, "_d", 0)
                prev = dpref[i]
                dpref.append(prev if prev > kd else kd)
                npref.append(npref[i] + getattr(k, "_n", 1))
                i += 1
            self.cells += (n - have)
        return 1 + dpref[n], 1 + npref[n]

    def measure(self, node):
        self.count += 1
        p = node.value
        tp = type(p)
        if tp is WList or tp is Record or tp is Guess:
            # O(1) reuse: a re-wrapping node carries an input's exact payload.
            ins = node._ins
            if type(ins) is tuple:
                for i in ins:
                    if getattr(i, "value", None) is p:
                        d = getattr(i, "_d", None)
                        if d is not None:
                            node._d = d
                            node._n = i._n
                            self._crown(node, d, i._n)
                            return
                        break
            elif ins is not None and getattr(ins, "value", None) is p:
                d = getattr(ins, "_d", None)
                if d is not None:
                    node._d = d
                    node._n = ins._n
                    self._crown(node, d, ins._n)
                    return
            if tp is WList:
                d, n = self._wlist(p)
            elif tp is Record:
                d, n = 0, 0
                for _, v in p.fields.items():
                    vd = getattr(v, "_d", 0)
                    if vd > d:
                        d = vd
                    n += getattr(v, "_n", 1)
                d, n = d + 1, n + 1
            else:
                k = p.node
                d = 1 + getattr(k, "_d", 0)
                n = 1 + getattr(k, "_n", 1)
        else:
            d, n = 0, 1
        node._d = d
        node._n = n
        self._crown(node, d, n)

    def _crown(self, node, d, n):
        if d > self.best_d:
            self.best_d = d
            self.best_d_node = node
        if n > self.best_n:
            self.best_n = n
            self.best_n_node = node
        if n > FULL_SHOW_NODES:
            self.over_n += 1
            if d <= FULL_SHOW_NEST:
                self.over_n_decided += 1
            elif len(self.over_samples) < ALLOC_BUDGET_SAMPLES:
                self.over_samples.append(node)
            else:
                self.sample_full = False


_TRACKER = None


def _counting_classes():
    """Build the two `Prov` subclasses fresh, so the module they patch is
    whatever `values_mod` holds now (a test may itself have patched it)."""
    base = values_mod.Prov
    merged = values_mod.MergedProv
    lazy = values_mod._LAZY

    class _CountingProv(base):
        # The constructor is INLINED rather than delegating to
        # `base.__init__`: `values.Prov`'s own comment measures it at 187 ns
        # and 2.77 M nodes for one meta.lang run, and a second host frame per
        # node is the difference between an instrument and an outage.
        __slots__ = ("_d", "_n")

        def __init__(self, op, detail, line, ins=(), show=lazy, value=None):
            self.op = op
            self.detail = detail
            self.line = line
            self._ins = ins
            self._show = show
            self.value = value
            _TRACKER.measure(self)

    class _CountingMerged(merged):
        __slots__ = ("_d", "_n")

        def __init__(self, op, detail, line, ins=(), show=lazy, value=None,
                     count=1):
            self.op = op
            self.detail = detail
            self.line = line
            self._ins = ins
            self._show = show
            self.value = value
            self.count = count
            _TRACKER.measure(self)

    return _CountingProv, _CountingMerged


def _install_counting(cp, cm):
    """Point every module-level name the hot paths call through at the
    counting subclasses. `values.leaf/derived/mk_miss/merge_miss` read the
    module global, so patching `values_mod` covers them; `interp` imported
    the names directly, so it needs its own. `Value` is deliberately NOT
    patched: `timetravel` does `isinstance(v, Prov)` against the name it
    imported, and rebinding an isinstance target to a subclass would make
    every node built before the patch fail a test it used to pass."""
    saved = []
    for mod in (values_mod, interp_mod):
        for name, cls in (("Prov", cp), ("MergedProv", cm)):
            if hasattr(mod, name):
                saved.append((mod, name, getattr(mod, name)))
                setattr(mod, name, cls)
    return saved


def _restore_counting(saved):
    for mod, name, cls in saved:
        setattr(mod, name, cls)


def alloc_payload_metrics(p):
    """(D, N) for a bare payload, computed with the ordinary walk. Exists so
    a test can check the constructor-time arithmetic against an independent
    implementation rather than against itself."""
    d = _payload_depth(p)
    n = _payload_size(p)
    return d, n


def _payload_size(p):
    """N(p): 1 for a leaf, 1 + sum(N of children) for a container.
    Iterative, memoised by node identity, for the same reason `depth_of` is."""
    memo, alive = {}, []
    shim = _Shim(p)
    stack = [(shim, False)]
    while stack:
        node, expanded = stack.pop()
        nid = id(node)
        if nid in memo:
            continue
        kids = struct_children(getattr(node, "value", None))
        if kids is None:
            memo[nid] = 1
            alive.append(node)
            continue
        if not expanded:
            stack.append((node, True))
            for k in kids:
                if id(k) not in memo:
                    stack.append((k, False))
            continue
        tot = 1
        for k in kids:
            tot += memo.get(id(k), 1)
        memo[nid] = tot
        alive.append(node)
    return memo[id(shim)]


# ---------------------------------------------------------------------------
# The TEST-corpus harvester (round 458). Closes round 452's own residual --
# "a census over the test corpus has not been run" -- and round 456's
# next-step 2, "the repo's true deepest value, 20 000, has never been
# re-derived by anything".
#
# THE POPULATION, defined before it was taken. A HARVESTED PROGRAM is a
# Python string constant in `tests/test_*.py` that
#
#   (1) sits in a RUNNER POSITION -- it is handed, directly or through one
#       intra-scope assignment, to a callable this module has PROVED (by a
#       fixed point over the module's own AST) executes guest source; and
#   (2) lexes and parses as Whence with at least one statement.
#
# Gate (2) alone is worthless and the number says so: 7935 of the 11 990
# string constants in this test tree parse as Whence, because `"ab"` and
# most English sentences are legal Whence expressions. The population has to
# be defined by what the SUITE DOES with a string, not by what the string
# looks like.
#
# WHY A FIXED POINT AND NOT A LIST OF NAMES. Twenty-seven of these files
# define their own local `run`/`val`/`run_src`/`canonical` helper and they do
# not agree on the name, the parameter order, or the depth. Writing the list
# by hand would make the census's population a function of what its author
# remembered. Instead:
#
#   seed      a call is EXECUTING if its callee is `Interpreter` or an
#             attribute call `.run` / `.exec_stmt` / `.exec_src` / `.eval_src`;
#             a call is a SOURCE SINK if it is executing or an attribute or
#             plain call named `parse` / `lex` / `tokens`.
#   step      a function is a RUNNER on parameter `p` if `p` is passed to a
#             source sink or to a known runner in that runner's own source
#             position; it is EXECUTING if its body constructs an
#             `Interpreter` or calls an executing runner.
#   repeat    until nothing new is learned.
#
# Only EXECUTING runners harvest. A parse-only runner (`test_parser.py`'s
# helpers) builds no values, so its strings are counted and excluded rather
# than censused, and `harvest_stats()["parse_only_programs"]` reports how
# many that is.
#
# THE DEPTH, which is the whole point of the exercise. `max_depth` is a
# property of the RUNNER, not of the interpreter default, and this is the
# thing decision 53 got wrong: it cites
# `tests/test_generated_killers.py::test_kill_values_py_139_arith_120` for a
# 20 000-deep value, but that file's `canonical()` takes `max_depth=500` and
# `run()` passes no override, so the suite never builds the value it is
# cited for. So each harvested program carries the max_depth the SUITE would
# run it at, extracted from the `Interpreter(...)` call site inside its
# runner (a `max_depth=` keyword whose value is a constant, or a parameter
# whose default is a constant), overridable by a `max_depth=` keyword at the
# harvest call site, and falling back to `Interpreter.DEFAULT_MAX_DEPTH`.
# `census_tests(depth="default")` re-runs the same corpus at the interpreter
# default so the two populations can be compared instead of conflated.
#
# WHAT IT DOES NOT REACH, stated rather than left to be found: a source
# built by string formatting (`"let x = %d" % n`), one assembled across
# scopes, and one supplied by `pytest.mark.parametrize`. Each is counted, in
# `harvest_stats()["unresolved_args"]` and `["nonconstant_programs"]`; the
# census reports those counts beside its answer instead of presenting a
# harvest as exhaustive.

TESTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")

# Two DIFFERENT facts, conflated in one tuple until round 462.
#
# `_EXEC_ATTRS` answers *does this call execute guest source?* -- it is the
# seed of the runner fixed point.  `_SRC_ARG0_ATTRS` answers *is this call's
# first argument a source STRING?*, which is what puts a node in a source
# position.  `exec_stmt` belongs to the first and not the second: its
# argument is an already-parsed statement (`interp.exec_stmt(prog.stmts[0],
# env)`), so under one tuple every `exec_stmt` call landed in
# `nonconstant_programs` -- a program the harvester "could not reach" where
# there was no program to reach.  17 calls, 8 of them in round 458's
# published residual, 0 of them a program.
_EXEC_ATTRS = ("run", "exec_stmt", "exec_src", "eval_src")
_SRC_ARG0_ATTRS = ("run", "exec_src", "eval_src")
_PARSE_CALLS = ("parse", "lex", "tokens")
_SRC_KEYWORDS = ("src", "source", "program", "code", "text")
_NOLIT = object()
MAX_FOLD = 32                    # strings one node may denote; see `_cross`


def _walk_scope(scope):
    """Every node in `scope`, NOT descending into a nested function, lambda
    or class.

    `ast.walk` does descend, and using it for a scope's bindings is a real
    defect this module shipped for one draft: the MODULE scope then held
    every `src = "..."` assignment in every test function in the file, so a
    runner call in function A resolved a name bound only in function B, and
    the harvest attributed 400-odd generated-killer programs to the line of
    the shared `run()` helper. The set it produced was nearly right and
    every line number in it was wrong, which is the worst way to be nearly
    right.
    """
    stack = [scope]
    first = True
    while stack:
        node = stack.pop()
        if not first and isinstance(node, SCOPE_KINDS):
            continue
        first = False
        yield node
        for child in ast.iter_child_nodes(node):
            stack.append(child)


def _callee(call):
    f = call.func
    if isinstance(f, ast.Name):
        return ("name", f.id)
    if isinstance(f, ast.Attribute):
        return ("attr", f.attr)
    return (None, None)


def _receiver(call):
    """The receiver name of an attribute call (`x.run(...)` -> `"x"`), or
    None when the receiver is not a bare name."""
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return f.value.id
    return None


def _imported_modules(tree):
    """The top-level names bound by `import x` / `import x.y as z` here.

    A `.run(...)` whose receiver is one of these is a MODULE call, not an
    interpreter call.  `subprocess.run([sys.executable, RUN, path])` is 45
    of the 985 calls this walk sees and its first argument is an argv LIST;
    round 458 counted 43 of them as source positions it could not fold,
    which is a third of its published `nonconstant_programs`.  The exclusion
    is derived from the file's OWN imports rather than from a denylist of
    module names, because a denylist is a guess about a corpus and this is a
    fact about the module.

    `ImportFrom` is deliberately excluded: `from whence.interp import
    Interpreter` binds a class, and a class is exactly what a legitimate
    receiver may be."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.asname or a.name.split(".")[0])
    return out


def _drives_source(call, mods):
    """True when `call` is `<interpreter>.run/exec_src/eval_src(src, ...)`."""
    kind, nm = _callee(call)
    return (kind == "attr" and nm in _SRC_ARG0_ATTRS and bool(call.args)
            and _receiver(call) not in mods)


def _cross(cols, sep):
    """Every `sep`-join of one element from each column, capped at
    `MAX_FOLD`.  The cap is a real bound: `A + B` where each side has five
    bindings is twenty-five programs, and a harvester that expands that
    silently reports a corpus larger than the suite runs."""
    if not cols or not all(cols):
        return []
    out = list(cols[0])[:MAX_FOLD]
    for col in cols[1:]:
        nxt = []
        for pre in out:
            for c in col:
                nxt.append(pre + sep + c)
                if len(nxt) >= MAX_FOLD:
                    break
            if len(nxt) >= MAX_FOLD:
                break
        out = nxt
    return out


def _product(cols):
    """`_cross` for `%`'s right operand, which is a tuple and not a join."""
    out = [()]
    for col in cols:
        nxt = []
        for pre in out:
            for c in col:
                nxt.append(pre + (c,))
                if len(nxt) >= MAX_FOLD:
                    break
            if len(nxt) >= MAX_FOLD:
                break
        out = nxt
        if not out:
            return []
    return out


def _literal(node, lits=None, depth=0):
    """The Python object a node denotes, or `_NOLIT`.

    `%`'s right operand is not a string, so the string folder cannot reach
    it: `'let r = typed(1, %s, "L")' % spec` needs `spec`, which the suite
    binds by unpacking a module-level table of tuples.  A separate literal
    environment is what makes that class foldable; `_NOLIT` rather than
    `None` because `None` is itself a legal literal."""
    if depth > 6:
        return _NOLIT
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        vals = (lits or {}).get(node.id)
        if vals and len(vals) == 1:
            return vals[0]
        return _NOLIT
    if isinstance(node, (ast.Tuple, ast.List)):
        out = []
        for e in node.elts:
            v = _literal(e, lits, depth + 1)
            if v is _NOLIT:
                return _NOLIT
            out.append(v)
        return tuple(out) if isinstance(node, ast.Tuple) else out
    # Round 468. Every shape below was named by a ROW in the itemised
    # residual, not chosen because it seemed plausible; the count each one
    # closes is in `knowledge/round-468-the-counter-that-could-only-be-
    # believed.md`.  39 of the 94 unresolved names
    # were bound by an ITERATION PROTOCOL (`zip`, `.items()`, a dict literal,
    # a comprehension) rather than by a string expression, which is a
    # different diagnosis from "the folder cannot build the string".
    if isinstance(node, ast.Dict):
        out = {}
        for k, v in zip(node.keys, node.values):
            if k is None:                        # `{**other}`
                return _NOLIT
            kk = _literal(k, lits, depth + 1)
            vv = _literal(v, lits, depth + 1)
            if kk is _NOLIT or vv is _NOLIT:
                return _NOLIT
            try:
                out[kk] = vv
            except TypeError:                    # unhashable key
                return _NOLIT
        return out
    if isinstance(node, ast.BinOp):
        return _literal_binop(node, lits, depth)
    if isinstance(node, ast.Subscript):
        base = _literal(node.value, lits, depth + 1)
        idx = _literal(node.slice, lits, depth + 1)
        if base is _NOLIT or idx is _NOLIT:
            return _NOLIT
        try:
            return base[idx]
        except Exception:                        # noqa: BLE001
            return _NOLIT
    if isinstance(node, ast.Call):
        return _literal_call(node, lits, depth)
    return _NOLIT


# `**` is deliberately absent: `10 ** 100000` is a denial of service written
# in four characters, and no row in the residual needs it.  `*` is capped for
# the same reason -- `"x" * 10 ** 9` is a legal test fixture nobody would
# want folded.
LITERAL_REPEAT_CAP = 100000
_LITERAL_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
}


def _literal_binop(node, lits, depth):
    left = _literal(node.left, lits, depth + 1)
    right = _literal(node.right, lits, depth + 1)
    if left is _NOLIT or right is _NOLIT:
        return _NOLIT
    op = type(node.op)
    if op is ast.Mult:
        for a, b in ((left, right), (right, left)):
            if isinstance(a, (str, bytes, list, tuple)) and                     isinstance(b, int) and not isinstance(b, bool):
                if b < 0 or b * max(1, len(a)) > LITERAL_REPEAT_CAP:
                    return _NOLIT
                return a * b
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left * right
        return _NOLIT
    fn = _LITERAL_BINOPS.get(op)
    if fn is None:
        return _NOLIT
    if op is ast.Add and isinstance(left, (str, bytes, list, tuple)) and             len(left) + len(right or ()) > LITERAL_REPEAT_CAP:
        return _NOLIT
    try:
        return fn(left, right)
    except Exception:                            # noqa: BLE001
        return _NOLIT


_LITERAL_SEQ_CALLS = ("zip", "list", "tuple", "sorted", "reversed",
                      "enumerate")


def _literal_call(node, lits, depth):
    """The literal a call denotes, for the iteration-protocol calls that a
    test table is actually written with.  No keywords are accepted: `sorted(
    xs, key=f)` is a call to `f`, and this walk has no `f`."""
    kind, nm = _callee(node)
    if node.keywords:
        return _NOLIT
    if kind == "name" and nm in _LITERAL_SEQ_CALLS:
        args = [_literal(a, lits, depth + 1) for a in node.args]
        if any(a is _NOLIT for a in args) or not args:
            return _NOLIT
        if not all(isinstance(a, (list, tuple)) for a in args):
            return _NOLIT
        try:
            if nm == "zip":
                return [tuple(t) for t in zip(*args)]
            if len(args) != 1:
                return _NOLIT
            if nm == "enumerate":
                return list(enumerate(args[0]))
            if nm == "sorted":
                return sorted(args[0])
            if nm == "reversed":
                return list(reversed(args[0]))
            return list(args[0]) if nm == "list" else tuple(args[0])
        except Exception:                        # noqa: BLE001
            return _NOLIT
    if kind == "attr" and nm in ("items", "keys", "values") and not node.args:
        base = _literal(node.func.value, lits, depth + 1)
        if not isinstance(base, dict):
            return _NOLIT
        if nm == "items":
            return [tuple(kv) for kv in base.items()]
        return list(base) if nm == "keys" else list(base.values())
    return _NOLIT


def _const_strs(node, env=None, lits=None, depth=0):
    """EVERY string a node can denote, as a list -- `[]` when the walk
    cannot say.

    A `str | None` folder cannot express the two shapes that dominate this
    tree's residual, and both are cases where the *right answer is more than
    one program*: a name with several bindings, and a node that genuinely
    denotes several sources (`val("A" if False else "B")`, or
    `'... %s ...' % spec` under `for spec, want in NAME_SLOT_CASES`).
    Round 458's folder returned None for both and counted them as misses,
    which reads as "could not reach" where the truth is "reached several".

    `_const_str` is kept as the single-valued view for callers that must
    refuse to guess."""
    if depth > 8:
        return []
    env = env or {}
    lits = lits or {}
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) else []
    if isinstance(node, ast.Name):
        vals = list(env.get(node.id) or [])[:MAX_FOLD]
        if vals:
            return vals
        lit = _literal(node, lits)
        return [lit] if isinstance(lit, str) else []
    if isinstance(node, ast.IfExp):
        # Both arms. A conditional source is two programs, not an unknown.
        return (_const_strs(node.body, env, lits, depth + 1) +
                _const_strs(node.orelse, env, lits, depth + 1))[:MAX_FOLD]
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append([v.value])
            elif isinstance(v, ast.FormattedValue):
                if v.format_spec is not None:
                    return []
                sub = _const_strs(v.value, env, lits, depth + 1)
                if not sub:
                    lit = _literal(v.value, lits)
                    if lit is _NOLIT:
                        return []
                    sub = [lit if isinstance(lit, str) else str(lit)]
                if v.conversion == 114:          # !r
                    sub = [repr(x) for x in sub]
                parts.append(sub)
            else:
                return []
        return _cross(parts, "")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _cross([_const_strs(node.left, env, lits, depth + 1),
                       _const_strs(node.right, env, lits, depth + 1)], "")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        tmpls = _const_strs(node.left, env, lits, depth + 1)
        if not tmpls:
            return []
        r = node.right
        if isinstance(r, ast.Tuple):
            cols = []
            for e in r.elts:
                v = _literal(e, lits)
                if v is _NOLIT:
                    ss = _const_strs(e, env, lits, depth + 1)
                    if not ss:
                        return []
                    cols.append(ss)
                else:
                    cols.append([v])
            rights = _product(cols)
        else:
            v = _literal(r, lits)
            if v is _NOLIT:
                ss = _const_strs(r, env, lits, depth + 1)
                if not ss:
                    return []
                rights = [(x,) for x in ss]
            else:
                rights = [v if isinstance(v, tuple) else (v,)]
        out = []
        for t in tmpls:
            for rr in rights:
                try:
                    out.append(t % rr)
                except (TypeError, ValueError, KeyError):
                    return []
                if len(out) >= MAX_FOLD:
                    return out
        return out
    if isinstance(node, ast.Call):
        kind, nm = _callee(node)
        if kind == "attr" and nm == "join" and len(node.args) == 1:
            seps = _const_strs(node.func.value, env, lits, depth + 1)
            arg = node.args[0]
            if len(seps) == 1 and isinstance(arg, (ast.List, ast.Tuple)):
                cols = [_const_strs(e, env, lits, depth + 1)
                        for e in arg.elts]
                return _cross(cols, seps[0])
            return []
        if kind == "attr" and nm == "replace" and len(node.args) == 2:
            base = _const_strs(node.func.value, env, lits, depth + 1)
            a = _literal(node.args[0], lits)
            b = _literal(node.args[1], lits)
            if base and isinstance(a, str) and isinstance(b, str):
                return [x.replace(a, b) for x in base][:MAX_FOLD]
            return []
    # Round 468. One fallback rather than a branch per shape: a node the
    # STRING folder cannot assemble may still be a plain literal string --
    # `"(" * 40`, `CASES[1]`, `PREFIX + SUFFIX` where both are literal
    # constants.  Three residual classes (`binop:Mult` inside `binop:Add`,
    # `subscript`, and the `%` right-operands) resolve here and nowhere else.
    # It runs LAST, so no existing branch changes its answer.
    lit = _literal(node, lits, depth)
    return [lit] if isinstance(lit, str) else []


def _const_str(node, env=None):
    """The string a node denotes, or None -- the single-valued view of
    `_const_strs`.

    Handles a literal, a `+` chain, and a name bound to a string earlier in
    the same or the module scope -- `test_v03.py` writes
    `src = LOOP + "let s = go(3, 0)\n..."` eighteen times, and a harvester
    that stopped at literals reported that file at 18 programs where it
    builds 86. A node that denotes several strings is None here, so the
    caller can COUNT it rather than guess at it."""
    ss = _const_strs(node, env)
    return ss[0] if len(ss) == 1 else None


# --- the residual, item by item (round 468) --------------------------------
#
# Round 462 split the residual from the exclusions and reduced it 258 -> 166,
# and its own skill (`skills/residual-audited-both-ways`) states the rule it
# used: *classify a residual item by item before narrowing it*. It then left
# its OWN residual as three integers. Round 462's next-step 2 says so in as
# many words -- "the 166 remaining residual entries are ARGUED undecidable,
# not measured undecidable ... classify the 94 the way it classified the 131,
# one row per entry".
#
# This is SPEC.md decision 57, minted in the round that wrote it and taken
# from `python3 specreg.py next` rather than from the bottom of the registry
# (round 464's next-step 3, whose fix is the reserved comment in SPEC.md).
#
# A COUNTER CANNOT BE AUDITED, ONLY BELIEVED. `unresolved_args: 94` supports
# exactly one action, "widen the folder", and cannot say which widening or
# whether any is possible. A ROW carries a file, a line, the source text of
# the node that defeated the walk, and a CLASS derived from the AST -- and a
# class is a thing a reader can refute by opening the file.
#
# Every outcome an argument in a source position can have now emits a row,
# not just the two that were called residual: the exclusions (`module_call`,
# `stmt_node_arg`), the two dedup drops, `parse_only` and `unparsed` too. The
# rows and the counters are derived at the same site, so a row that is not
# counted (or a count with no row) is a bug a test can see -- see
# `test_depthcensus.py::test_rows_reconcile_with_the_counters`.

# The scope kinds `_walk_scope` REFUSES to descend into, and therefore
# exactly the kinds that must appear in the scope list themselves. Round 468:
# the two lists disagreed. `_walk_scope` has stopped at `Lambda` and
# `AsyncFunctionDef` since round 458, and `harvest_file`'s scope list held
# only `FunctionDef` and `ClassDef` -- so a call inside a lambda body was
# visited by NO scope and counted by NO counter, neither residual nor
# exclusion. Measured before the fix: 9 calls inside lambda bodies in
# `tests/`, 2 of them runner calls (`test_v09.py:245` and `:254`, both
# `run(src)` inside a `lambda: ...` passed to `pytest.raises`). A blind spot
# that is not in the residual is the one kind this instrument's own docstring
# promises does not exist.
SCOPE_KINDS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
               ast.ClassDef)

ROW_TEXT_CAP = 160


def _file_read_reason(node, cls):
    """`"file_read"` when this source position holds the contents of a FILE.

    Round 468, and it is an EXCLUSION rather than a residual for the reason
    round 462 gave for `subprocess.run`: the harvester's declared population
    is *a Python string constant in `tests/test_*.py`* (gate 1), and a file's
    contents is not one.  The walk did not fail to reach these -- they are
    outside what it set out to reach, and the twelve of them are
    `examples/*.lang`, which this same module's OTHER mode (`census()` over
    `EXAMPLES`, the default) censuses in full.  Folding them in here would
    census the example corpus twice and call the second copy a test program.
    """
    if isinstance(node, ast.Call) and _callee(node) == ("attr", "read"):
        return "file_read"
    if cls == "bound_nonconstant:call:.read":
        return "file_read"
    return None


# WHY `zip(LITERAL, runtime)` IS NOT WIDENED, written down rather than left
# as an omission.  13 of the residual's rows are `for src, g in zip(CORPUS,
# guest_eval_all(CORPUS))`, where the FIRST column is a literal table and the
# second is a runtime list.  Binding `src` to every element of `CORPUS` would
# be an OVER-approximation: `zip` truncates to its shortest argument, so the
# strings that actually reach the runner are a SUBSET of that column, and a
# census that publishes a superset is claiming programs the suite may never
# run.  The harvester's job is the corpus the suite HAS, not an upper bound
# on it.  The class is named (`zip_nonliteral_column`) so the decision is
# visible and refutable: show that the columns are equal-length by
# construction and the widening becomes sound.


def _snippet(node):
    """One line of source text for a node, capped. `ast.unparse` and not the
    original slice: the original carries the file's own line breaks and a row
    that spans lines is not a row."""
    try:
        t = ast.unparse(node)
    except Exception:                            # noqa: BLE001
        return "<unparseable %s>" % type(node).__name__
    t = " ".join(t.split())
    return t if len(t) <= ROW_TEXT_CAP else t[:ROW_TEXT_CAP - 3] + "..."


def _node_class(node):
    """The AST shape that defeated `_const_strs`, as a name.

    Deliberately shallow -- one level, the callee name for a call. The point
    is a class a reader can grep for, not a taxonomy.
    """
    if isinstance(node, ast.Constant):
        return "constant:" + type(node.value).__name__
    if isinstance(node, (ast.List, ast.Tuple)):
        return "sequence"
    if isinstance(node, ast.Call):
        kind, nm = _callee(node)
        if kind == "attr":
            return "call:." + nm
        if kind == "name":
            return "call:" + nm
        return "call:<expr>"
    if isinstance(node, ast.Subscript):
        return "subscript"
    if isinstance(node, ast.Attribute):
        return "attribute"
    if isinstance(node, ast.BinOp):
        return "binop:" + type(node.op).__name__
    if isinstance(node, ast.JoinedStr):
        return "fstring"
    if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp,
                         ast.DictComp)):
        return "comprehension"
    if isinstance(node, ast.IfExp):
        return "ifexp"
    if isinstance(node, ast.Starred):
        return "starred"
    if isinstance(node, ast.Name):
        return "name"
    return type(node).__name__.lower()


# Every way a name can acquire a value, so that "this name is not bound" is a
# statement about the FILE and not about the two statement kinds the
# harvester's binder happens to read (`Assign` and `For`).
def _binds(node):
    """(name, form, value node or None) for every binding `node` performs.

    The VALUE matters as much as the form. `unresolved_args: 94` is opaque;
    `bound_nonconstant` is a little better; `bound_nonconstant:call:.join` is
    a row a reader can act on, because it names the expression the folder
    would have to learn."""
    if isinstance(node, ast.Assign):
        for t in node.targets:
            for n in _target_names(t):
                yield n, "assign", node.value
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        for n in _target_names(node.target):
            yield n, "annassign", node.value
    elif isinstance(node, ast.AugAssign):
        for n in _target_names(node.target):
            yield n, "augassign", node.value
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        for n in _target_names(node.target):
            yield n, "for", node.iter
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        for it in node.items:
            if it.optional_vars is not None:
                for n in _target_names(it.optional_vars):
                    yield n, "with", it.context_expr
    elif isinstance(node, ast.NamedExpr):
        for n in _target_names(node.target):
            yield n, "walrus", node.value
    elif isinstance(node, ast.ExceptHandler) and node.name:
        yield node.name, "except", None
    elif isinstance(node, ast.comprehension):
        for n in _target_names(node.target):
            yield n, "comprehension", node.iter
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
        for a in node.names:
            yield (a.asname or a.name.split(".")[0]), "import", None
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                           ast.ClassDef)):
        yield node.name, "def", None
    elif isinstance(node, ast.Global):
        for n in node.names:
            yield n, "global", None


def _target_names(t):
    if isinstance(t, ast.Name):
        return [t.id]
    if isinstance(t, (ast.Tuple, ast.List)):
        out = []
        for e in t.elts:
            out.extend(_target_names(e))
        return out
    if isinstance(t, ast.Starred):
        return _target_names(t.value)
    return []


def _scope_bindings(scopes):
    """id(scope) -> {name: set(binding form)}, using the harvester's OWN
    notion of a scope (`_walk_scope`), so the answer is about the walk that
    actually failed and not about a second, differently-shaped one."""
    out = {}
    for sc in scopes:
        d = {}
        for node in _walk_scope(sc):
            for name, form, value in _binds(node):
                e = d.setdefault(name, {"forms": set(), "values": []})
                e["forms"].add(form)
                if value is not None:
                    e["values"].append(value)
        if isinstance(sc, (ast.FunctionDef, ast.AsyncFunctionDef,
                           ast.Lambda)):
            for p in _param_order(sc) + [a.arg for a in sc.args.kwonlyargs]:
                d.setdefault(p, {"forms": set(), "values": []})[
                    "forms"].add("param")
        out[id(sc)] = d
    return out


def _scope_parents(scopes):
    """id(scope) -> enclosing scope node. Built by looking at the children of
    the nodes `_walk_scope` yields, because `_walk_scope` deliberately does
    not yield a nested scope itself."""
    parent = {}
    for sc in scopes:
        for node in _walk_scope(sc):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, SCOPE_KINDS):
                    parent[id(child)] = sc
    return parent


def _unresolved_class(name, sc, tree, sbind, parent, lits=None):
    """Why a bare name in a source position did not resolve.

    The harvester's environment is `module bindings | this scope's bindings`
    and NOTHING in between, so a name bound in an enclosing function or in a
    class body is invisible to it however ordinary the binding is. That is a
    property of the chain, not of the name, and it gets its own class.
    """
    lits = lits or {}
    _EMPTY = {"forms": set(), "values": []}
    here = sbind.get(id(sc), {}).get(name, _EMPTY)
    mod = sbind.get(id(tree), {}).get(name, _EMPTY)
    forms = here["forms"] | mod["forms"]
    skipped = set()
    cur = parent.get(id(sc))
    while cur is not None and cur is not tree:
        skipped |= sbind.get(id(cur), {}).get(name, _EMPTY)["forms"]
        cur = parent.get(id(cur))
    if skipped and not forms:
        return "bound_in_skipped_scope:" + ",".join(sorted(skipped))
    if not forms:
        return "never_bound_in_file"
    readable = forms & {"assign", "for"}
    if not readable:
        return "bound_by:" + ",".join(sorted(forms))
    vals = here["values"] + mod["values"]
    kinds = sorted({_node_class(v) for v in vals})
    if kinds == ["call:zip"] and any(_zip_has_literal_column(v, lits)
                                     for v in vals):
        return "zip_nonliteral_column"
    return "bound_nonconstant:" + ("/".join(kinds) if kinds else "?")


def _zip_has_literal_column(node, lits):
    """True for `zip(A, B)` where at least one argument IS a literal
    sequence and at least one is not -- the shape the comment above refuses
    to widen."""
    if not (isinstance(node, ast.Call) and _callee(node) == ("name", "zip")):
        return False
    cols = [_literal(a, lits) for a in node.args]
    lit = [c for c in cols if isinstance(c, (list, tuple))]
    return bool(lit) and len(lit) < len(cols)


def _param_order(fn):
    a = fn.args
    return ([p.arg for p in getattr(a, "posonlyargs", [])] +
            [p.arg for p in a.args])


def _param_default(fn, name):
    """The constant default of `fn`'s parameter `name`, or None."""
    order = _param_order(fn)
    defaults = list(fn.args.defaults)
    if defaults and name in order:
        first = len(order) - len(defaults)
        i = order.index(name)
        if i >= first:
            d = defaults[i - first]
            if isinstance(d, ast.Constant) and isinstance(d.value, int):
                return d.value
    for kw, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults):
        if kw.arg == name and isinstance(d, ast.Constant) \
                and isinstance(d.value, int):
            return d.value
    return None


def _max_depth_of(fn, runners):
    """The `max_depth` the suite would run this runner's program at."""
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        kind, nm = _callee(node)
        if nm == "Interpreter":
            for kw in node.keywords:
                if kw.arg != "max_depth":
                    continue
                if isinstance(kw.value, ast.Constant) and \
                        isinstance(kw.value.value, int):
                    return kw.value.value
                if isinstance(kw.value, ast.Name):
                    d = _param_default(fn, kw.value.id)
                    if d is not None:
                        return d
            return DEFAULT_GUEST_MAX_DEPTH
        if kind == "name" and nm in runners and runners[nm]["executes"]:
            for kw in node.keywords:
                if kw.arg == "max_depth" and \
                        isinstance(kw.value, ast.Constant) and \
                        isinstance(kw.value.value, int):
                    return kw.value.value
            inner = runners[nm]["max_depth"]
            if inner is not None:
                return inner
    return DEFAULT_GUEST_MAX_DEPTH


def runners_in(tree):
    """name -> {order, src_params, executes, max_depth} for every function
    in this module that runs guest source. Fixed point; see the section
    comment for the seed and the step."""
    fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    mods = _imported_modules(tree)
    runners = {}
    for _ in range(len(fns) + 2):
        changed = False
        for fn in fns:
            order = _param_order(fn)
            params = set(order) | set(p.arg for p in fn.args.kwonlyargs)
            src_params = set()
            executes = False
            for node in ast.walk(fn):
                if not isinstance(node, ast.Call):
                    continue
                kind, nm = _callee(node)
                mod_recv = _receiver(node) in mods
                if nm == "Interpreter" or \
                        (kind == "attr" and nm in _EXEC_ATTRS
                         and not mod_recv):
                    executes = True
                if kind == "name" and nm in runners:
                    if runners[nm]["executes"]:
                        executes = True
                sink_order, sink_src = None, ()
                if (kind == "attr" and nm in _SRC_ARG0_ATTRS
                        and not mod_recv) or nm in _PARSE_CALLS:
                    sink_order = ["<src>"]
                elif kind == "name" and nm in runners and nm != fn.name:
                    sink_order = runners[nm]["order"]
                    sink_src = runners[nm]["src_params"]
                if sink_order is None:
                    continue
                for i, a in enumerate(node.args):
                    if not isinstance(a, ast.Name) or a.id not in params:
                        continue
                    if sink_order == ["<src>"]:
                        if i == 0:
                            src_params.add(a.id)
                    elif i < len(sink_order) and sink_order[i] in sink_src:
                        src_params.add(a.id)
                for kw in node.keywords:
                    if kw.arg in _SRC_KEYWORDS and \
                            isinstance(kw.value, ast.Name) and \
                            kw.value.id in params:
                        src_params.add(kw.value.id)
            if not src_params:
                continue
            prev = runners.get(fn.name)
            entry = {"order": order, "src_params": src_params,
                     "executes": executes, "max_depth": None}
            if prev is None or prev["src_params"] != src_params or \
                    prev["executes"] != executes:
                runners[fn.name] = entry
                changed = True
        if not changed:
            break
    for fn in fns:
        if fn.name in runners:
            runners[fn.name]["max_depth"] = _max_depth_of(fn, runners)
    return runners


def harvest_file(path):
    """(programs, stats) for one test module. A program is a dict with
    `file`, `line`, `runner`, `max_depth` and `src`."""
    text = open(path, encoding="utf-8").read()
    tree = ast.parse(text)
    runners = runners_in(tree)
    mods = _imported_modules(tree)
    stats = {"runners": sorted(runners),
             "executing_runners": sorted(n for n in runners
                                         if runners[n]["executes"]),
             "calls": 0, "unresolved_args": 0, "forwarded_args": 0,
             "nonconstant_programs": 0, "parse_only_programs": 0,
             "unparsed_programs": 0, "ambiguous_scopes": 0,
             # Round 462. Not residuals -- EXCLUSIONS, counted so that the
             # exclusion is auditable rather than invisible. A call skipped
             # for a reason is not a program the walk failed to reach, and
             # the two must not share a counter.
             "module_calls": 0, "stmt_node_args": 0,
             "multivalued_nodes": 0, "fold_capped": 0,
             # Round 468. `strings_folded` is every string a source position
             # was found to denote; the four counters under it are the four
             # things that can then happen to one. Without `dup_in_file` the
             # string-level accounting could not be closed at all -- the
             # per-file `seen` set dropped a repeat and incremented nothing.
             "strings_folded": 0, "dup_in_file": 0, "file_reads": 0,
             # Round 468. `parse_only_programs` counted an OCCURRENCE and
             # called it a program: it fired once per folded string, before
             # both the dedup and the parse gate that `programs` is measured
             # after, so "145 parse-only against 559 harvested" compared two
             # different units. The three counters below are the three
             # different questions, each measured where it belongs.
             "parse_only_strings": 0, "parse_only_srcs": [],
             "rows": []}

    scopes = [tree] + [n for n in ast.walk(tree)
                       if isinstance(n, SCOPE_KINDS)]
    parents = _scope_parents(scopes)

    def _chain(sc):
        """module -> ... -> `sc`, outermost first. The harvester's
        environment was `module | this scope` and NOTHING in between, so a
        name bound in an enclosing function was invisible however ordinary
        the binding. Latent until round 468 put lambdas in the scope list --
        `test_v09.py`'s `lambda: run(src)` is the first construct in this
        tree whose enclosing scope is not the module."""
        out, cur = [], sc
        while cur is not None:
            out.append(cur)
            cur = parents.get(id(cur)) if cur is not tree else None
        if out[-1] is not tree:
            out.append(tree)
        out.reverse()
        return out
    # Two passes. Pass A takes the literal bindings; pass B re-runs with
    # pass A's names in scope so `LOOP + "..."` resolves. Repeated twice for
    # a two-link chain; a longer chain is left unresolved and counted rather
    # than iterated to a fixed point on data that does not need one.
    bindings = {}
    lit_bindings = {}
    for sc in scopes:
        bindings[id(sc)] = {}
        lit_bindings[id(sc)] = {}

    def _bind(b, name, v):
        cur = b.setdefault(name, [])
        if len(cur) < MAX_FOLD and not any(x is v or x == v for x in cur):
            cur.append(v)

    for _pass in range(3):
        for sc in scopes:
            b = bindings[id(sc)]
            lb = lit_bindings[id(sc)]
            env, lits = {}, {}
            for anc in _chain(sc):
                env.update(bindings[id(anc)])
                lits.update(lit_bindings[id(anc)])
            def _bind_iter(target, it):
                """`for t in <iterable>:` -- the binder for BOTH statement
                and comprehension form. Round 468: `_walk_scope` already
                descends into a comprehension (it is not a scope this walk
                stops at), so `[host(src) for src in CASES]` was VISITED and
                its target simply never bound -- 10 of the 94 unresolved
                names, and the same construct the `ast.For` branch below has
                read since round 458."""
                seq = _literal(it, lits)
                if seq is not _NOLIT and isinstance(seq, (list, tuple)):
                    for elt in seq:
                        if isinstance(target, ast.Name):
                            if isinstance(elt, str):
                                _bind(b, target.id, elt)
                            _bind(lb, target.id, elt)
                        elif isinstance(target, (ast.Tuple, ast.List)) \
                                and isinstance(elt, (list, tuple)) \
                                and len(elt) == len(target.elts):
                            for t, v in zip(target.elts, elt):
                                if not isinstance(t, ast.Name):
                                    continue
                                if isinstance(v, str):
                                    _bind(b, t.id, v)
                                _bind(lb, t.id, v)
                elif isinstance(it, (ast.List, ast.Tuple)) and \
                        isinstance(target, ast.Name):
                    for elt in it.elts:
                        for v in _const_strs(elt, env, lits):
                            _bind(b, target.id, v)

            for node in _walk_scope(sc):
                targets, value = None, None
                if isinstance(node, ast.comprehension):
                    _bind_iter(node.target, node.iter)
                    continue
                if isinstance(node, ast.Assign):
                    targets, value = node.targets, node.value
                elif isinstance(node, ast.For):
                    # `for src in ["...", "..."]:` runs every element as a
                    # program. Twelve of these files drive a table that way
                    # and a harvester that only reads `=` cannot see them.
                    #
                    # Round 462 adds the OTHER table shape, which is what
                    # unlocks the `%` class: `for spec, want in
                    # NAME_SLOT_CASES:` over a module-level list of tuples.
                    # 25 of round 458's 131 non-constant nodes are a `%`
                    # whose right operand is a name bound only here.
                    _bind_iter(node.target, node.iter)
                    continue
                else:
                    continue
                for v in _const_strs(value, env, lits):
                    for t in targets:
                        if isinstance(t, ast.Name):
                            _bind(b, t.id, v)
                lv = _literal(value, lits)
                if lv is not _NOLIT:
                    for t in targets:
                        if isinstance(t, ast.Name):
                            _bind(lb, t.id, lv)

    sbind = _scope_bindings(scopes)
    base = os.path.basename(path)

    def _row(node, kind, cls, label, **extra):
        r = {"file": base, "line": getattr(node, "lineno", 0),
             "runner": label, "kind": kind, "cls": cls,
             "text": _snippet(node)}
        r.update(extra)
        stats["rows"].append(r)
        return r

    out = []
    seen = set()
    po_seen = set()
    for sc in scopes:
        env, lits = {}, {}
        for anc in _chain(sc):
            env.update(bindings[id(anc)])
            lits.update(lit_bindings[id(anc)])
        params = set()
        if isinstance(sc, (ast.FunctionDef, ast.AsyncFunctionDef,
                           ast.Lambda)):
            params = set(_param_order(sc)) | \
                set(p.arg for p in sc.args.kwonlyargs)
        # The depth a bare `interp.run(...)` in this scope would use: the
        # nearest `Interpreter(max_depth=<const>)` built in the same scope.
        # Stated rather than assumed -- a scope with two interpreters at
        # different depths resolves to the first, and `ambiguous_scopes`
        # counts those instead of hiding them.
        scope_depth, n_interp = DEFAULT_GUEST_MAX_DEPTH, 0
        for node in _walk_scope(sc):
            if isinstance(node, ast.Call) and _callee(node)[1] == "Interpreter":
                n_interp += 1
                for kw in node.keywords:
                    if kw.arg == "max_depth" and \
                            isinstance(kw.value, ast.Constant) and \
                            isinstance(kw.value.value, int) and n_interp == 1:
                        scope_depth = kw.value.value
        if n_interp > 1:
            stats["ambiguous_scopes"] += 1
        for node in _walk_scope(sc):
            if not isinstance(node, ast.Call):
                continue
            kind, nm = _callee(node)
            executes = True
            if kind == "name" and nm in runners:
                r = runners[nm]
                executes = r["executes"]
                cands = []
                for i, a in enumerate(node.args):
                    if i < len(r["order"]) and \
                            r["order"][i] in r["src_params"]:
                        cands.append(a)
                for kw in node.keywords:
                    if kw.arg in r["src_params"]:
                        cands.append(kw.value)
                depth = r["max_depth"]
                label = nm
            elif kind == "attr" and nm in _EXEC_ATTRS and node.args:
                # A test that skips the file's helper and drives the
                # interpreter itself: `interp.run("let x = 1")`. Missing
                # this class cost `test_v03.py` alone 5 programs on the
                # first harvest, and there is no reason a direct driver is
                # less a program than an indirect one.
                #
                # Two exclusions, both COUNTED (round 462). A receiver that
                # this file imported as a module is not an interpreter, and
                # `exec_stmt` takes a parsed statement rather than source.
                if _receiver(node) in mods:
                    stats["module_calls"] += 1
                    _row(node, "excluded", "module_call:" + str(_receiver(node)),
                         "." + nm)
                    continue
                if nm not in _SRC_ARG0_ATTRS:
                    stats["stmt_node_args"] += 1
                    _row(node, "excluded", "stmt_node_arg:." + nm, "." + nm)
                    continue
                cands = [node.args[0]]
                depth = scope_depth
                label = "." + nm
            else:
                continue
            stats["calls"] += 1
            for kw in node.keywords:
                if kw.arg == "max_depth" and \
                        isinstance(kw.value, ast.Constant) and \
                        isinstance(kw.value.value, int):
                    depth = kw.value.value
            for a in cands:
                srcs = _const_strs(a, env, lits)
                if len(srcs) > 1:
                    stats["multivalued_nodes"] += 1
                if len(srcs) >= MAX_FOLD:
                    stats["fold_capped"] += 1
                if not srcs:
                    if isinstance(a, ast.Name):
                        # A parameter forwarded from this scope's own caller
                        # is not a missed program -- the program arrives at
                        # the CALL SITE, which this walk also visits.
                        if a.id in params:
                            stats["forwarded_args"] += 1
                            _row(a, "forwarded", "param:" + a.id, label)
                            continue
                        cls = _unresolved_class(a.id, sc, tree, sbind,
                                                parents, lits)
                        why = _file_read_reason(a, cls)
                        if why:
                            stats["file_reads"] += 1
                            _row(a, "excluded", why, label, name=a.id)
                        else:
                            stats["unresolved_args"] += 1
                            _row(a, "residual", cls, label, name=a.id)
                    else:
                        why = _file_read_reason(a, None)
                        if why:
                            stats["file_reads"] += 1
                            _row(a, "excluded", why, label)
                        else:
                            stats["nonconstant_programs"] += 1
                            _row(a, "residual", _node_class(a), label)
                stats["strings_folded"] += len(srcs)
                for s in srcs:
                    if not executes:
                        stats["parse_only_strings"] += 1
                        _row(a, "parse_only", "runner:" + str(label), label,
                             src=s)
                        if s not in po_seen:
                            po_seen.add(s)
                            stats["parse_only_srcs"].append(s)
                        continue
                    key = (s, depth)
                    if key in seen:
                        stats["dup_in_file"] += 1
                        continue
                    seen.add(key)
                    try:
                        prog = parse_mod.parse(s)
                    except Exception as exc:     # noqa: BLE001
                        stats["unparsed_programs"] += 1
                        _row(a, "unparsed", type(exc).__name__, label, src=s)
                        continue
                    if not getattr(prog, "stmts", None):
                        stats["unparsed_programs"] += 1
                        _row(a, "unparsed", "no_statements", label, src=s)
                        continue
                    out.append({"file": os.path.basename(path),
                                "line": node.lineno, "runner": label,
                                "max_depth": depth, "src": s})
    stats["parse_only_programs"] = sum(1 for x in stats["parse_only_srcs"]
                                       if _is_program(x))
    return out, stats


def _is_program(src):
    """Gate (2) of the declared population: lexes and parses as Whence with
    at least one statement. The same gate `programs` is measured after."""
    try:
        prog = parse_mod.parse(src)
    except Exception:                            # noqa: BLE001
        return False
    return bool(getattr(prog, "stmts", None))


def harvest_tests(directory=None, keep_rows=False):
    """(programs, stats) over every `tests/test_*.py`. Programs are
    deduplicated on (source, max_depth) ACROSS files: the same one-liner
    appears in several version files and censusing it twice would inflate
    every count without adding a value the repo builds.

    `keep_rows` (round 468) carries `harvest_file`'s per-entry rows up into
    `stats["rows"]`. OFF by default and on purpose: `--json` dumps this dict
    and 400-odd rows would change the shape of every artefact already on
    disk. `--residual` turns it on."""
    directory = TESTS if directory is None else directory
    stats = {"files": 0, "calls": 0, "unresolved_args": 0,
             "forwarded_args": 0, "nonconstant_programs": 0,
             "parse_only_programs": 0, "unparsed_programs": 0,
             "ambiguous_scopes": 0, "programs_before_dedup": 0,
             "executing_runners": 0, "parse_only_runners": 0,
             "module_calls": 0, "stmt_node_args": 0,
             "multivalued_nodes": 0, "fold_capped": 0,
             "strings_folded": 0, "dup_in_file": 0, "dup_cross_file": 0,
             "file_reads": 0, "parse_only_strings": 0,
             "parse_only_distinct": 0}
    if keep_rows:
        stats["rows"] = []
    progs = []
    seen = set()
    po_all = set()
    for f in sorted(os.listdir(directory)):
        if not (f.startswith("test_") and f.endswith(".py")):
            continue
        stats["files"] += 1
        rows, s = harvest_file(os.path.join(directory, f))
        for k in ("calls", "unresolved_args", "forwarded_args",
                  "nonconstant_programs", "parse_only_programs",
                  "unparsed_programs", "ambiguous_scopes",
                  "module_calls", "stmt_node_args", "multivalued_nodes",
                  "fold_capped", "strings_folded", "dup_in_file",
                  "file_reads", "parse_only_strings"):
            stats[k] += s[k]
        po_all.update(s["parse_only_srcs"])
        if keep_rows:
            stats["rows"].extend(s["rows"])
        stats["executing_runners"] += len(s["executing_runners"])
        stats["parse_only_runners"] += (len(s["runners"]) -
                                        len(s["executing_runners"]))
        stats["programs_before_dedup"] += len(rows)
        for r in rows:
            key = (r["src"], r["max_depth"])
            if key in seen:
                stats["dup_cross_file"] += 1
                continue
            seen.add(key)
            progs.append(r)
    stats["programs"] = len(progs)
    stats["parse_only_distinct"] = len(po_all)
    stats["parse_only_programs"] = sum(1 for x in po_all if _is_program(x))
    return progs, stats


def census_tests(programs=None, depth="suite", alloc=True,
                 max_nodes=DEFAULT_MAX_NODES, max_roots=DEFAULT_MAX_ROOTS,
                 progress=None, limit=None):
    """Census every harvested test program.

    `depth="suite"` runs each program at the max_depth its own runner would
    give it; `depth="default"` runs every program at
    `Interpreter.DEFAULT_MAX_DEPTH`. The two answers differ and the
    difference is decision 53's error, so the census refuses to have one
    mode."""
    if programs is None:
        programs, _ = harvest_tests()
    if limit is not None:
        programs = programs[:limit]
    rows = []
    for i, p in enumerate(programs):
        if progress:
            progress(i, p)
        md = (p["max_depth"] if depth == "suite"
              else DEFAULT_GUEST_MAX_DEPTH)
        r = census_program("%s:%d" % (p["file"], p["line"]), "all",
                           max_nodes, max_roots, alloc,
                           src=p["src"], max_depth=md)
        r["runner"] = p["runner"]
        r["src_len"] = len(p["src"])
        rows.append(r)
    return rows


def corpus_paths(directory=EXAMPLES):
    return sorted(os.path.join(directory, f)
                  for f in os.listdir(directory) if f.endswith(".lang"))


def census(paths=None, roots="all", max_nodes=DEFAULT_MAX_NODES,
           max_roots=DEFAULT_MAX_ROOTS, progress=None, alloc=True):
    paths = corpus_paths() if paths is None else paths
    out = []
    for p in paths:
        if progress:
            progress(p)
        out.append(census_program(p, roots, max_nodes, max_roots, alloc))
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
        "alloc_on": all(r["alloc_on"] for r in ok) if ok else False,
        "max_alloc_depth": max([r["alloc_depth"] for r in ok] or [0]),
        "max_alloc_size": max([r["alloc_size"] for r in ok] or [0]),
        "full_nodes_budget": FULL_SHOW_NODES,
        "programs_over_node_budget": [r["program"] for r in ok
                                      if r["alloc_over_node_budget"]],
        "values_over_node_budget": sum(r["width_over_n"] for r in ok),
        "width_fired": sum(r["width_fired"] for r in ok),
        "width_depth_stopped_first": sum(r["width_depth_stopped_first"]
                                         for r in ok),
        "width_sample_incomplete": [r["program"] for r in ok
                                    if not r["width_sample_complete"]],
        "total_alloc_nodes": sum(r["alloc_nodes"] for r in ok),
        "programs_alloc_deeper": [r["program"] for r in ok
                                  if r["alloc_depth"] > r["built_depth"]],
        "max_alloc_gap": max([r["alloc_depth"] - r["built_depth"]
                              for r in ok] or [0]),
        "alloc_invariant_violations": [r["program"] for r in ok
                                       if r["alloc_depth"] < r["built_depth"]],
        "deepest_alloc_program": max(
            ok, key=lambda r: r["alloc_depth"])["program"] if ok else "",
        "alloc_champions_unreachable": [
            r["program"] for r in ok if r["alloc_depth_reachable"] is False],
        "alloc_capped_programs": [r["program"] for r in ok
                                  if r["alloc_capped"]],
        "alloc_disagreements": [r["program"] for r in ok
                                if r["alloc_agrees"] is False],
        "seconds": round(sum(r["seconds"] for r in rows), 2),
        "width_seconds": round(sum(r["width_seconds"] for r in rows), 2),
        "truncated_walks": [r["program"] for r in ok if r["built_truncated"]],
        "deepest_program": max(ok, key=lambda r: r["built_depth"])["program"]
        if ok else "",
    }


def _short(n):
    """A 92-digit integer in a table column is noise, not a measurement."""
    return "%d" % n if n < 10 ** 9 else "%.4g (%d digits)" % (float(n),
                                                              len(str(n)))


def render(rows, summary):
    w = max([len(r["program"]) for r in rows] or [7])
    lines = ["%-*s  %5s %5s %5s %8s %8s %16s %6s  %s"
             % (w, "program", "built", "alloc", "print", "walked", "made",
                "maxsize", "prints", "spine")]
    for r in sorted(rows, key=lambda r: (-r["built_depth"], r["program"])):
        if not r["ok"]:
            lines.append("%-*s  %s" % (w, r["program"], "FAILED: " + r["error"]))
            continue
        lines.append("%-*s  %5d %5s %5d %8d %8s %16s %6d  %s%s"
                     % (w, r["program"], r["built_depth"],
                        r["alloc_depth"] if r["alloc_on"] else "-",
                        r["printed_depth"], r["built_nodes"],
                        r["alloc_nodes"] if r["alloc_on"] else "-",
                        _short(r["alloc_size"]) if r["alloc_on"] else "-",
                        r["printed_values"],
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
    if summary.get("alloc_on"):
        lines.append("")
        lines.append("ALLOCATION census (no root set; every value built)")
        lines.append("max ALLOC depth %d (%s); root-walk missed it in: %s"
                     % (summary["max_alloc_depth"],
                        summary["deepest_alloc_program"],
                        summary["alloc_champions_unreachable"] or "no program"))
        lines.append("programs whose deepest BUILT value the root set does "
                     "not reach: %d %s (max gap %d)"
                     % (len(summary["programs_alloc_deeper"]),
                        summary["programs_alloc_deeper"],
                        summary["max_alloc_gap"]))
        lines.append("nodes constructed: %d vs %d walked (%.2fx); "
                     "invariant violations: %s"
                     % (summary["total_alloc_nodes"], summary["total_nodes"],
                        (summary["total_alloc_nodes"] /
                         float(summary["total_nodes"] or 1)),
                        summary["alloc_invariant_violations"] or "none"))
        lines.append("max value SIZE (tree unfolding) %s against "
                     "FULL_SHOW_NODES=%d"
                     % (_short(summary["max_alloc_size"]),
                        summary["full_nodes_budget"]))
        lines.append("values whose size exceeds the budget: %d; renderings "
                     "the WIDTH bound actually stopped: %d (depth cap "
                     "truncated first in %d sampled); sample incomplete in: %s"
                     % (summary["values_over_node_budget"],
                        summary["width_fired"],
                        summary["width_depth_stopped_first"],
                        summary["width_sample_incomplete"] or "no program"))
        lines.append("alloc walks that hit a cap: %s"
                     % (summary["alloc_capped_programs"] or "none"))
        lines.append("constructor arithmetic vs independent re-walk: %s"
                     % ("AGREES on every champion"
                        if not summary["alloc_disagreements"]
                        else "DISAGREES: %s" % summary["alloc_disagreements"]))
    lines.append("wall time in-run: %.2f s; in the width check after each "
                 "run: %.2f s" % (summary.get("seconds", 0.0),
                                  summary.get("width_seconds", 0.0)))
    return "\n".join(lines)


# Every key of the stats dict, in the order the report prints them. The
# tuple exists so `test_every_counter_reaches_the_report` can assert that no
# counter is collected and then never shown -- before round 468 SEVEN of them
# were (`parse_only_programs`, `unparsed_programs`, `forwarded_args`,
# `ambiguous_scopes`, `programs_before_dedup`, `executing_runners`,
# `parse_only_runners`), which is how `parse_only_programs` could measure the
# wrong unit for three rounds without anyone seeing the number.
REPORT_KEYS = (
    "programs", "files", "calls", "unresolved_args", "nonconstant_programs",
    "module_calls", "stmt_node_args", "file_reads", "multivalued_nodes",
    "fold_capped", "strings_folded", "dup_in_file", "dup_cross_file",
    "programs_before_dedup", "parse_only_strings", "parse_only_distinct",
    "parse_only_programs", "unparsed_programs", "forwarded_args",
    "ambiguous_scopes", "executing_runners", "parse_only_runners",
)


def harvest_report(stats):
    """The harvest's own coverage, as text. Every counter in `stats` appears
    exactly once; see `REPORT_KEYS`."""
    residual = stats["unresolved_args"] + stats["nonconstant_programs"]
    return (
        "harvest:  %d programs from %d files, %d calls\n"
        "residual: %d (%d unresolved names + %d non-constant nodes)\n"
        "excluded: %d module calls + %d statement-node args + %d file reads "
        "(not residual -- not source positions)\n"
        "folded:   %d multi-valued nodes, %d capped at MAX_FOLD=%d\n"
        "strings:  %d folded = %d parse-only + %d dup-in-file + %d unparsed "
        "+ %d kept; %d kept - %d dup-cross-file = %d programs\n"
        "parse-only: %d strings, %d distinct, %d of those are programs "
        "(gate 2); %d of %d runners never execute\n"
        "args:     %d forwarded to a call site this walk also visits\n"
        "scopes:   %d with more than one Interpreter (depth from the first)\n"
        "runners:  %d executing\n"
        % (stats["programs"], stats["files"], stats["calls"], residual,
           stats["unresolved_args"], stats["nonconstant_programs"],
           stats["module_calls"], stats["stmt_node_args"],
           stats["file_reads"],
           stats["multivalued_nodes"], stats["fold_capped"], MAX_FOLD,
           stats["strings_folded"], stats["parse_only_strings"],
           stats["dup_in_file"], stats["unparsed_programs"],
           stats["programs_before_dedup"], stats["programs_before_dedup"],
           stats["dup_cross_file"], stats["programs"],
           stats["parse_only_strings"], stats["parse_only_distinct"],
           stats["parse_only_programs"], stats["parse_only_runners"],
           stats["parse_only_runners"] + stats["executing_runners"],
           stats["forwarded_args"], stats["ambiguous_scopes"],
           stats["executing_runners"]))


def residual_report(rows, limit=None):
    """One line per row, grouped by kind and class. A COUNTER CANNOT BE
    AUDITED, ONLY BELIEVED -- this is the same population as
    `unresolved_args`/`nonconstant_programs`, printed as rows a reader can
    open the file on."""
    order = ("residual", "excluded", "parse_only", "unparsed", "forwarded")
    by_kind = {}
    for r in rows:
        by_kind.setdefault(r["kind"], []).append(r)
    out = []
    for kind in order + tuple(sorted(k for k in by_kind if k not in order)):
        sub = by_kind.get(kind)
        if not sub:
            continue
        counts = {}
        for r in sub:
            counts[r["cls"]] = counts.get(r["cls"], 0) + 1
        out.append("=== %s: %d row(s), %d class(es) ==="
                   % (kind, len(sub), len(counts)))
        for cls, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            out.append("  %4d  %s" % (n, cls))
        if kind in ("residual", "excluded"):
            for r in sorted(sub, key=lambda r: (r["cls"], r["file"],
                                                r["line"]))[:limit]:
                out.append("        %-34s:%-5d %-40s %s"
                           % (r["file"], r["line"], r["cls"], r["text"]))
        out.append("")
    return "\n".join(out)


def _main_tests(mode, limit, alloc, max_nodes, out_json, residual=False):
    """`--tests` : harvest `tests/`, then census what was harvested.

    Prints the residual FIRST and unconditionally. An instrument whose
    coverage line is below a hundred rows of output is an instrument whose
    coverage nobody reads."""
    progs, stats = harvest_tests(keep_rows=residual)
    sys.stderr.write(harvest_report(stats))
    if residual:
        rows = stats.pop("rows")
        print(residual_report(rows))
        if out_json:
            with open(out_json, "w") as fh:
                json.dump({"mode": mode, "stats": stats, "rows": rows},
                          fh, indent=1, sort_keys=True)
                fh.write("\n")
        return 0
    if limit == 0:
        if out_json:
            with open(out_json, "w") as fh:
                json.dump({"mode": mode, "stats": stats, "programs": progs},
                          fh, indent=1, sort_keys=True)
                fh.write("\n")
        return 0
    rows = census_tests(progs, depth=mode, alloc=alloc, max_nodes=max_nodes,
                        limit=limit,
                        progress=lambda i, p: sys.stderr.write(
                            "  %4d %s:%d\n" % (i, p["file"], p["line"])))
    summary = summarise(rows)
    print(render(rows, summary))
    if out_json:
        with open(out_json, "w") as fh:
            json.dump({"mode": mode, "stats": stats, "summary": summary,
                       "programs": rows}, fh, indent=1, sort_keys=True)
            fh.write("\n")
    return 0


def main(argv):
    args = argv[1:]
    out_json = None
    roots = "all"
    alloc = True
    paths = None
    tests_mode = None
    residual = False
    limit = None
    max_nodes = DEFAULT_MAX_NODES
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--tests":
            # Round 458 wrote `harvest_tests`/`census_tests` and wired them
            # to nothing: `main()` has only ever called `census()` over
            # `examples/`. Its own next-step 1 called the census "not wired
            # into any tier", which understates it -- until this flag the
            # test-corpus census could not be RUN from a command line at
            # all, by a tier or by a person. A schedule cannot be argued
            # about before the entry point exists.
            has_arg = i + 1 < len(args) and \
                args[i + 1] in ("suite", "default")
            tests_mode = args[i + 1] if has_arg else "suite"
            i += 2 if has_arg else 1
            continue
        if a == "--limit":
            limit = int(args[i + 1])
            i += 2
            continue
        if a == "--harvest-only":
            tests_mode = tests_mode or "suite"
            limit = 0
            i += 1
            continue
        if a == "--residual":
            # Round 462's next-step 2: "classify the 94 the way it
            # classified the 131 -- one row per entry".
            tests_mode = tests_mode or "suite"
            residual = True
            i += 1
            continue
        if a == "--json":
            out_json = args[i + 1]
            i += 2
        elif a == "--roots":
            roots = args[i + 1]
            i += 2
        elif a == "--no-alloc":
            alloc = False
            i += 1
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
                             "[--no-alloc] [--program NAME] [--max-nodes N] "
                             "[--tests suite|default] [--limit N] "
                             "[--harvest-only] [--residual] "
                             "[--json OUT]\n")
            return 2
        continue

    if tests_mode is not None:
        return _main_tests(tests_mode, limit, alloc, max_nodes, out_json,
                           residual)

    rows = census(paths, roots, max_nodes,
                  progress=lambda p: sys.stderr.write(
                      "  %s\n" % os.path.basename(p)),
                  alloc=alloc)
    summary = summarise(rows)
    print(render(rows, summary))
    if out_json:
        with open(out_json, "w") as fh:
            json.dump({"roots": roots, "alloc": alloc,
                       "summary": summary, "programs": rows},
                      fh, indent=1, sort_keys=True)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

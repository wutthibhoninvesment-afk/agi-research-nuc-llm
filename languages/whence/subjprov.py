#!/usr/bin/env python3
"""Where does the number in a magnitude assertion COME FROM?

Round 500 (language C), taking round 498's next-step #2 verbatim:

    "The `tree_derived` axis is the weakest thing in the instrument and it
    is the one that decides what gets fixed. It is a heuristic over fixture
    parameters plus a name list, and it produced 2 false positives out of 9
    on its first outing -- both declared, neither exempted in code. A round
    that wants to sharpen it should NOT extend the name list; the honest
    version is dataflow (does the magnitude's subject trace to a value the
    function constructs, or to one it is handed) and nobody has costed that."

This module is that cost.

--------------------------------------------------------------------------
WHAT `assertshadow.tree_derived` ACTUALLY ASKS, AND WHY IT IS THE WRONG SHAPE
--------------------------------------------------------------------------

`tree_derived(fn)` takes a FUNCTION. It returns True when the function has a
non-builtin fixture parameter, or when anywhere in its body it calls a name
in a 25-word list. It never looks at the assertion. So every magnitude
assert in a function that happens to call `open()` once gets the same
verdict, whether its subject is a corpus census or a string literal defined
two lines above it.

That is a whole-function answer to a per-assertion question. The unit of
the census is the PAIR; the axis that decides which pairs cost something is
evaluated on the enclosing function. Round 498 published 7 costly pairs
across 2 nodes and declared BOTH nodes false positives -- a precision of
0/2 on the population that decides what gets repaired.

--------------------------------------------------------------------------
THE LATTICE
--------------------------------------------------------------------------

For each root NAME an assertion is about, this resolves a provenance by
walking backward through the bindings that reach it:

    local    the value is built here, out of literals -- a string in the
             function body, a display, a module-level constant in the same
             file. It cannot move without this file moving.
    scratch  a pytest scratch fixture (`tmp_path`) or `tempfile.mkdtemp`.
             The test is HANDED an empty area and writes its own input into
             it, so the content is still the test's own. Round 494's
             `test_a_compensating_move...` is this, and it is the case that
             forced `tree_derived`'s short-circuit into existence.
    unknown  an opaque no-argument call, or a name this cannot resolve.
             Published as its own population and NEVER folded into
             `derived`: round 434 established that an honest `unknown` beats
             a guess, and a residual that gets rounded into a verdict is how
             an instrument stops being falsifiable.
    handed   a non-scratch parameter -- a fixture built by someone else.
    tree     the value passes through a READER: `open`, `subprocess.run`,
             a project harvester, or a same-file helper that reaches the
             tree itself. This is the one that drifts for reasons that have
             nothing to do with the node.

Ordered by drift risk, `local < scratch < unknown < handed < tree`, and an
assertion takes the JOIN over its subjects: it can drift if ANY subject can.

`derived` -- the replacement for `tree_derived` -- is `prov in {handed,
tree}`. `unknown` is not derived and not clean; it is a third answer.

--------------------------------------------------------------------------
THE ASSUMPTION, STATED SO IT CAN BE FALSIFIED
--------------------------------------------------------------------------

**Arguments dominate.** A call to a callable this module cannot see
propagates the join of its arguments. Only a call to a known READER is
`tree` on its own strength, and a no-argument opaque call is `unknown`.

That is a guess about opaque callables, and it is wrong for any helper that
reaches the tree while ignoring its parameters. So for helpers this module
CAN see -- module-level `def`s in the same test file -- it does not guess:
it re-runs the whole analysis on the helper body with the parameters bound
to the call site's argument provenances, and joins the helper's `return`
expressions. `helpers_that_ignore_their_arguments()` reports every in-file
helper for which the assumption would have been wrong, so the size of the
remaining guess is a measured number rather than a hope.

--------------------------------------------------------------------------
THE SECOND AXIS, AND WHY DATAFLOW ALONE COULD NOT HAVE CLOSED THIS
--------------------------------------------------------------------------

Round 498's two declared false positives are NOT the same kind of mistake,
and building this module is what showed it.

`test_v30.py::test_the_guest_never_merges_a_tail_loop` is a provenance
error: its `max(h) > 1` is about `h = host(src)` and `src` is a string
literal in the function body. Dataflow fixes it.

`test_v10.py::test_ref_diff_...` is NOT. Its `assert r.returncode == 0` is
over a subprocess run against the real tree, and `assert s.count(old) > 1`
is over `open(p).read()`. Both genuinely drift. They are false positives of
a DIFFERENT question -- are they preconditions? -- and `tree_derived` was
being asked to carry both questions at once.

Precondition-ness is not a dataflow property, but it is not unmeasurable
either. A precondition guards a USE. `guards_a_use` reports whether the
magnitude's subject is READ by code strictly between the magnitude line and
the shape line: `assert s.count(old) > 1` stands directly above
`s.replace(old, ...)`, and that is what makes it a guard rather than a
shadow. The two axes are published separately, and neither filters the
census -- for the same reason round 498 published three nested populations.

CLI
    python3 subjprov.py                     # per-pair table over the census
    python3 subjprov.py --compare           # dataflow vs the name-list axis
    python3 subjprov.py --helpers           # where "arguments dominate" fails
    python3 subjprov.py --json <path>       # write the ledger
    python3 subjprov.py --check             # ledger vs live, rc=1 on drift
    python3 subjprov.py --check --ledger <p>  # ...against a candidate file
"""

import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, "tests")

#: Drift risk, ascending. The join of a set of provenances is the last one.
PROV_ORDER = ("local", "scratch", "unknown", "handed", "tree")

#: NOT a provenance, and deliberately not a member of `PROV_ORDER`.
#:
#: ROUND 522 (language C). `compare_with_census` pairs the census on disk
#: against the LIVE tree by `assert.lineno == pair["magnitude_line"]`, and
#: its un-matched default was `prov = "unknown"; subjects = {}`. So a census
#: whose COORDINATES had gone stale -- the ordinary consequence of anybody
#: editing a test file above an existing assert -- did not report as stale.
#: It reported as provenance, in the one population this module promises is
#: "published, not folded": the residual.
#:
#: Round 521 (SWE-loop D) moved a scratch `.lang` file out of the live
#: `languages/whence/` directory, which is a correct fix to a real race, and
#: shifted `tests/test_polarity.py` by +15 lines. All SIX of that file's
#: census rows then read `unknown`, `unknown_residual` went 5 -> 11, `tree`
#: 12 -> 8 and `local` 31 -> 29, and NOTHING in this module said the word
#: stale. Measured: regenerating this ledger against that census produced a
#: document `subjprov.py --check` called green -- "0 finding(s)", exit 0 --
#: carrying `unknown_residual: 11`. The CLI's own printed regeneration hint
#: named THIS ledger, so following the instrument's instruction converted a
#: true red into a false green.
#:
#: `unknown` means the analyser looked at the assert and could not resolve
#: its subjects. `stale` means the analyser never saw that assert, because
#: the census sent it to a line that no longer holds one. Those are not the
#: same claim and an instrument that renders them with one word cannot be
#: falsified on the difference.
STALE = "stale"

#: `derived` -- the boolean that replaces `assertshadow.tree_derived`.
#: `unknown` is deliberately absent: an unresolved name is a third answer,
#: not a quiet vote for either of the other two.
DERIVED = frozenset(("handed", "tree"))

#: pytest fixtures that hand over an EMPTY area rather than a value.
#: Same list as `assertshadow._PYTEST_BUILTINS`, kept here rather than
#: imported so this module can be read on its own; `test_subjprov.py` pins
#: that the two agree, so a divergence is a failing test and not a drift.
SCRATCH_FIXTURES = frozenset("""
tmp_path tmp_path_factory tmpdir tmpdir_factory capsys capsysbinary
capfd capfdbinary monkeypatch caplog recwarn request pytestconfig
record_property doctest_namespace cache
""".split())

#: Calls that MAKE a scratch area. `tempfile.mkdtemp()` takes no arguments
#: that matter and would otherwise resolve `unknown`, which would put
#: `test_v10.py`'s whole node in the residual instead of answering it.
SCRATCH_MAKERS = frozenset("""
tempfile.mkdtemp tempfile.mkstemp tempfile.TemporaryDirectory
tempfile.NamedTemporaryFile mkdtemp mkstemp TemporaryDirectory
""".split())

#: DOTTED readers. Matched against the full dotted path of the call target,
#: so `subprocess.run` is a reader and a bare `run` is not. Round 498's
#: `_TREE_READS` matched on the last component only, which is why it could
#: not tell `x.read_text()` from a method called `read_text` on a dict
#: subclass -- and, more to the point, why `subprocess.run` was missing
#: from it entirely while `Popen` was present.
DOTTED_READERS = frozenset("""
subprocess.run subprocess.check_output subprocess.check_call
subprocess.Popen subprocess.call os.listdir os.walk os.scandir
os.path.exists os.path.isfile os.path.isdir shutil.copytree
json.load pathlib.Path.read_text glob.glob glob.iglob
""".split())

#: BARE readers -- names and final attributes that mean "reach outside" in
#: any context this tree uses them. `open` is the only true builtin here;
#: the rest are file-object and project-harvester methods.
BARE_READERS = frozenset("""
open glob iglob walk listdir read_text read_bytes readlines
check_output Popen harvest_tests harvest_file census audit survey
scan_tree scan_file corpus_paths field_programs load_census
""".split())

#: Names that carry no subject. Same rationale as `assertshadow._NEUTRAL`
#: and pinned equal to it by `test_subjprov.py`.
NEUTRAL = frozenset("""
len sorted set sum max min list tuple dict str int float bool any all
repr type abs round enumerate zip range reversed frozenset next iter
""".split())

#: How deep to follow same-file helpers before giving up. Cycles are caught
#: by the visiting set; this bounds mutual recursion through many hops.
MAX_DEPTH = 6


def join(provs):
    """The most drift-prone provenance in `provs`, `local` if empty."""
    best = "local"
    for p in provs:
        if PROV_ORDER.index(p) > PROV_ORDER.index(best):
            best = p
    return best


def _dotted(node):
    """`subprocess.run` for `subprocess.run(...)`; `None` if not a name path.

    Returns the FULL dotted path so a caller can match either the whole
    thing or its last component, which is the distinction `_TREE_READS`
    could not make."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        # `open(p).read()` -- the receiver is itself a call. The receiver is
        # analysed separately as an argument-free sub-expression; here only
        # the attribute chain matters.
        return ".".join(reversed(parts)) if parts else None
    elif parts:
        return ".".join(reversed(parts))
    else:
        return None
    return ".".join(reversed(parts))


def _is_write_open(call):
    """`open(p, "w")` -- an output, not an input.

    Round 500's first version called every `open()` a reader, which made
    `_harvest_source(src, tag)` in `test_testcorpus_census.py` tree-derived
    on the strength of the line that WRITES a string literal to disk. A
    write carries data OUT of the function; nothing about the tree flows
    back through it."""
    if not isinstance(call, ast.Call):
        return False
    if _dotted(call.func) not in ("open", "io.open", "pathlib.Path.open"):
        return False
    mode = None
    if len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
        mode = call.args[1].value
    for k in call.keywords:
        if k.arg == "mode" and isinstance(k.value, ast.Constant):
            mode = k.value.value
    return isinstance(mode, str) and any(c in mode for c in "wax")


def is_reader(func_node):
    """Does calling this reach outside the file?"""
    dotted = _dotted(func_node)
    if dotted is None:
        return False
    if dotted in DOTTED_READERS:
        return True
    return dotted.rsplit(".", 1)[-1] in BARE_READERS


def is_scratch_maker(func_node):
    dotted = _dotted(func_node)
    if dotted is None:
        return False
    return dotted in SCRATCH_MAKERS


class ModuleIndex:
    """Module-level bindings and `def`s for one test file.

    A module-level constant is `local`: it is written in the file, so it
    cannot move without the file moving. A module-level binding built by a
    reader is `tree` exactly as it would be inside a function -- the same
    resolution runs over it, in a scope with no parameters."""

    def __init__(self, tree, path=None):
        self.tree = tree
        self.path = path
        self.assigns = {}
        self.functions = {}
        self.imported = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[node.name] = node
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    for name in _bound_names(t):
                        self.assigns.setdefault(name, node.value)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                if node.value is not None:
                    for name in _bound_names(node.target):
                        self.assigns.setdefault(name, node.value)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    self.imported.add((a.asname or a.name).split(".")[0])


def _bound_names(target):
    """Every Name bound by an assignment target, through tuple unpacking."""
    out = []
    for n in ast.walk(target):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.append(n.id)
    return out


def _bindings(fn):
    """`name -> [(lineno, value_expr), ...]` for everything bound in `fn`.

    Loop and `with` targets bind to the thing being iterated or entered,
    which is what a reader wants: `for row in harvest():` makes `row` as
    tree-derived as `harvest()` is. Comprehension targets are included for
    the same reason; their scoping does not matter here because this asks
    only where a value CAME FROM."""
    out = {}

    def add(target, value, lineno):
        if value is None:
            return
        for name in _bound_names(target):
            out.setdefault(name, []).append((lineno, value))

    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                add(t, node.value, node.lineno)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            add(node.target, node.value, node.lineno)
        elif isinstance(node, ast.NamedExpr):
            add(node.target, node.value, node.lineno)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            add(node.target, node.iter, node.lineno)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    add(item.optional_vars, item.context_expr, node.lineno)
        elif isinstance(node, ast.comprehension):
            # `ast.comprehension` has no lineno; use the iterable's.
            add(node.target, node.iter, getattr(node.iter, "lineno", 0))
    return out


class Resolver:
    """Subject provenance for the assertions of one test file."""

    def __init__(self, module_index):
        self.mod = module_index
        self._helper_cache = {}
        self._reach_cache = {}
        self._reach_active = set()

    # -- public ---------------------------------------------------------

    def assertion(self, fn, test_node):
        """`(provenance, {name: provenance})` for one assert's test expr."""
        per = {}
        for name in _subject_names(test_node):
            if name in self.mod.imported:
                # An IMPORT is not a subject. `assert DC.depth_of(v) == 3`
                # is about `v`; `DC` is a module this file imported and
                # resolving it as a value answered `unknown`, which then
                # won the join over a perfectly resolved `local`. Five of
                # the eleven residuals this module started with were this
                # and nothing else.
                #
                # `_subject_names` itself is left character-for-character
                # equal to `assertshadow.subjects` -- a test pins that --
                # so this is a stated narrowing at the point of use rather
                # than a silent redefinition of a shared predicate.
                continue
            per[name] = self.name(fn, name, getattr(test_node, "lineno", 0))
        return join(per.values()), per

    def name(self, fn, name, before_line):
        """Provenance of `name` as seen at `before_line` inside `fn`."""
        return self._name(fn, name, before_line, _Ctx())

    def _written_here(self, fn, call, ctx):
        """If this read is of a path THIS function wrote, what did it write?

        Returns the join over every value written into that path BEFORE
        this read, or `None` when there is no such write. `None` and
        `"local"` are different answers and the caller depends on the
        difference: `None` means "fall through to the argument-sensitive
        rule", not "clean".

        ORDERED, and the ordering is not a nicety. `test_v10.py` does

            s = open(p).read()                     # line 467
            open(p, "w").write(s.replace(old, ...))  # line 471

        -- it READS the file, then sabotages it. A flow-insensitive version
        sees the write, resolves the read to what that write carried, and
        chases `s` back to the same read forever: the first version of this
        rule died with a RecursionError on exactly this function. Ordering
        the writes fixes the answer (the read predates the write, so it is
        a tree read, and `test_v10.py` stays costly) and removes the cycle
        at the same time. `ctx.reading` catches whatever ordering does
        not."""
        if fn is None or not call.args:
            return None
        path = call.args[0]
        if not isinstance(path, ast.Name):
            return None
        key = (id(fn), path.id)
        if key in ctx.reading:
            return None
        writes = _writes_to(fn).get(path.id) or []
        here = getattr(call, "lineno", 0)
        payloads = [v for lineno, v in writes if lineno < here]
        if not payloads:
            return None
        ctx.reading.add(key)
        try:
            return join(self.expr(fn, v, ctx) for v in payloads)
        finally:
            ctx.reading.discard(key)

    def is_module_ref(self, node):
        """Is this expression a dotted path rooted at an IMPORTED name?

        `dc`, `dc.something`, `os.path` -- all module references. A module
        reference carries no data, so it is neither a subject nor a
        receiver."""
        while isinstance(node, ast.Attribute):
            node = node.value
        return isinstance(node, ast.Name) and node.id in self.mod.imported

    def reaches_tree_regardless(self, helper):
        """Does this helper touch the tree even with ALL arguments local?

        The falsifier for the "arguments dominate" assumption, and the
        reason this module does not have to make that assumption for any
        helper it can actually see. Every parameter is pinned to the bottom
        of the lattice and the body is re-analysed; if any expression in it
        still evaluates to `tree`, the helper reaches the tree on its own
        strength and its arguments are beside the point.

        Guarded rather than fixpointed: a helper reached while this is
        already computing for it answers `False`, which is the bottom of a
        boolean lattice and therefore the right starting point for a
        least-fixpoint reading of the same question."""
        key = id(helper)
        if key in self._reach_cache:
            return self._reach_cache[key]
        if key in self._reach_active:
            return False
        self._reach_active.add(key)
        try:
            ctx = _Ctx()
            for p in _params(helper):
                ctx.params[(key, p)] = "local"
            found = False
            for node in ast.walk(helper):
                if not isinstance(node, ast.Call):
                    continue
                # ONLY a read counts. The first version asked whether any
                # call in the body evaluated to `tree`, and
                # `os.path.join(HERE, name)` does -- it COMPUTES a path in
                # the tree without reading a byte of it. That flagged
                # `test_testcorpus_census.py::_harvest_source`, which
                # writes a string literal to that path and harvests it
                # straight back, and so re-broke the very case the
                # write-then-read-back rule had just fixed. Computing a
                # path is not reaching the tree; opening one is.
                is_helper_call = isinstance(node.func, ast.Name) \
                    and node.func.id in self.mod.functions
                if not (is_reader(node.func) or is_helper_call):
                    continue
                if self.expr(helper, node, ctx) == "tree":
                    found = True
                    break
            self._reach_cache[key] = found
            return found
        finally:
            self._reach_active.discard(key)

    def helpers_that_ignore_their_arguments(self):
        """Every same-file helper for which "arguments dominate" is WRONG.

        Calling one of these with local arguments and propagating the join
        of those arguments -- which is exactly what this module does for
        any callable it CANNOT see -- answers `local`, and is wrong.

        This is the measured size of the remaining guess, which is the only
        honest thing to publish about an assumption. It is not a defect
        list: every helper here is handled correctly, because it is in a
        file this module parses. It is the population that would be
        mishandled if it were one import away."""
        out = []
        for hname, hfn in sorted(self.mod.functions.items()):
            if hname.startswith("test_"):
                # A test function is not a helper. Nothing calls it, so
                # "arguments dominate" is never applied to it and it cannot
                # be a counter-example to the assumption. The first version
                # counted them and reported 316 across the tree, a number
                # that measured the size of the suite rather than the size
                # of the guess.
                continue
            if self.reaches_tree_regardless(hfn):
                out.append((hname, _params(hfn), "tree"))
        return out

    # -- resolution -----------------------------------------------------

    def _name(self, fn, name, before_line, ctx):
        if name in NEUTRAL:
            return "local"
        if name == "__file__":
            # `__file__` IS the tree. Every path constant in these test
            # files is `os.path.dirname(...(os.path.abspath(__file__)))`,
            # and a reader given such a path reads the repo. Resolving it
            # any other way makes `ROOT` a local string and every
            # `subprocess.run([..., ROOT + "/bench/ref_diff.py"])` look like
            # a value the test built for itself.
            return "tree"
        key = (id(fn), name, before_line)
        if key in ctx.visiting:
            # A loop-carried or self-referential binding (`s = s + x`).
            # Neither `local` nor `tree` is defensible without a fixpoint,
            # and `unknown` is the answer this module reserves for exactly
            # that. It never gets counted as `derived`.
            return "unknown"
        if fn is not None:
            forced = ctx.params.get((id(fn), name))
            if forced is not None:
                return forced
            params = _params(fn)
            if name in params:
                return ("scratch" if name in SCRATCH_FIXTURES else "handed")
        ctx.visiting.add(key)
        try:
            expr = self._binding(fn, name, before_line)
            if expr is not None:
                return self.expr(fn, expr, ctx)
            if name in self.mod.assigns:
                # Module scope: resolved with no enclosing function, so its
                # own names resolve through module bindings only.
                return self.expr(None, self.mod.assigns[name], ctx)
            if name in self.mod.functions:
                return "local"
            return "unknown"
        finally:
            ctx.visiting.discard(key)

    def _binding(self, fn, name, before_line):
        """The binding of `name` that reaches `before_line`, or `None`.

        The LAST binding at a line strictly below the reference, which is
        what actually reaches it in straight-line code. If every binding is
        below (a loop-carried name referenced before its textual
        assignment), the earliest is used rather than nothing: the value
        still came from there."""
        if fn is None:
            return None
        binds = _fn_bindings(fn).get(name)
        if not binds:
            return None
        above = [b for b in binds if b[0] < before_line]
        if above:
            return max(above, key=lambda b: b[0])[1]
        return min(binds, key=lambda b: b[0])[1]

    def expr(self, fn, node, ctx):
        """Provenance of an arbitrary expression."""
        if isinstance(node, ast.Constant):
            return "local"
        if isinstance(node, ast.Name):
            return self._name(fn, node.id, getattr(node, "lineno", 0), ctx)
        if isinstance(node, ast.Call):
            return self._call(fn, node, ctx)
        if isinstance(node, ast.Attribute) and self.is_module_ref(node):
            # A module CONSTANT: `sys.executable`, `os.sep`, `ast.Name`.
            # Fixed by the environment, not by this repo, so it cannot
            # drift with the tree. LIMITATION, stated rather than hidden:
            # a first-party module constant that IS a tree path -- say
            # `depthcensus.TESTS` -- reads `local` here too, because
            # resolving it means parsing the imported module and this
            # analysis stops at the file boundary. No pair in the current
            # census takes that route; `test_subjprov.py` pins the rule so
            # the day one does, it is a visible decision.
            return "local"
        if isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred,
                             ast.Await)):
            return self.expr(fn, node.value, ctx)
        if isinstance(node, ast.Slice):
            return join(self.expr(fn, p, ctx)
                        for p in (node.lower, node.upper, node.step)
                        if p is not None)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return join(self.expr(fn, e, ctx) for e in node.elts)
        if isinstance(node, ast.Dict):
            return join(self.expr(fn, e, ctx)
                        for e in list(node.keys) + list(node.values)
                        if e is not None)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return join([self.expr(fn, node.elt, ctx)]
                        + [self.expr(fn, g.iter, ctx)
                           for g in node.generators])
        if isinstance(node, ast.DictComp):
            return join([self.expr(fn, node.key, ctx),
                         self.expr(fn, node.value, ctx)]
                        + [self.expr(fn, g.iter, ctx)
                           for g in node.generators])
        if isinstance(node, ast.BinOp):
            return join((self.expr(fn, node.left, ctx),
                         self.expr(fn, node.right, ctx)))
        if isinstance(node, ast.BoolOp):
            return join(self.expr(fn, v, ctx) for v in node.values)
        if isinstance(node, ast.UnaryOp):
            return self.expr(fn, node.operand, ctx)
        if isinstance(node, ast.Compare):
            return join([self.expr(fn, node.left, ctx)]
                        + [self.expr(fn, c, ctx) for c in node.comparators])
        if isinstance(node, ast.IfExp):
            return join((self.expr(fn, node.body, ctx),
                         self.expr(fn, node.orelse, ctx)))
        if isinstance(node, ast.JoinedStr):
            return join(self.expr(fn, v, ctx) for v in node.values)
        if isinstance(node, ast.FormattedValue):
            return self.expr(fn, node.value, ctx)
        if isinstance(node, ast.Lambda):
            return "local"
        return "unknown"

    def _call(self, fn, node, ctx):
        if is_scratch_maker(node.func):
            return "scratch"

        arg_provs = [self.expr(fn, a, ctx) for a in node.args
                     if not isinstance(a, ast.Starred)]
        arg_provs += [self.expr(fn, a.value, ctx) for a in node.args
                      if isinstance(a, ast.Starred)]
        arg_provs += [self.expr(fn, k.value, ctx) for k in node.keywords]

        # A method call carries its receiver: `r.stdout.count(x)` is about
        # `r`, and dropping the receiver is how `subprocess` results looked
        # local. `open(p).read()` reaches here with `open(p)` as receiver.
        if isinstance(node.func, ast.Attribute) \
                and not self.is_module_ref(node.func.value):
            recv = self.expr(fn, node.func.value, ctx)
        else:
            # A MODULE is not data. `dc.harvest_tests(str(a))` is about
            # `a`; `dc` is an import. Treating the receiver as a value
            # resolved `dc` through no binding at all, answered `unknown`,
            # and that `unknown` then won the join over a perfectly
            # resolved `scratch` argument -- which put round 494's own
            # node, the one case the whole `scratch` rung exists for, into
            # the residual. Found by reading a disagreement rather than by
            # a failing test, which is round 434's rule working again.
            recv = None

        if _is_write_open(node):
            return "local"

        if is_reader(node.func):
            # WRITE-THEN-READ-BACK. A file this function wrote holds this
            # function's own data, whatever its path. The idiom is all over
            # this tree -- `_harvest_source(src, tag)` writes a synthetic
            # module into `tests/` and harvests it straight back -- and
            # path-based provenance alone calls the result tree-derived
            # because the path is `os.path.join(HERE, name)` and `HERE`
            # comes from `__file__`. The path IS in the tree; the content
            # is a string literal from the caller, and the content is what
            # the assertion is about.
            written = self._written_here(fn, node, ctx)
            if written is not None:
                return written

            # ARGUMENT-SENSITIVE, and this is the single sharpest thing the
            # dataflow version buys. `dc.harvest_tests()` with no argument
            # walks `languages/whence/tests/` -- the corpus, which grows
            # every round for reasons that have nothing to do with the node.
            # `dc.harvest_tests(str(a))` with `a` under `tmp_path` walks two
            # files the test wrote four lines earlier, and cannot drift at
            # all. SAME READER, opposite verdicts, and round 498's
            # name-list axis cannot express the difference because it never
            # looks at the call's arguments.
            #
            # No arguments at all means the default location, which for
            # every reader in this tree is somewhere in the repo.
            flow = arg_provs + ([recv] if recv else [])
            if not flow:
                return "tree"
            j = join(flow)
            if j == "scratch":
                # The ONLY clean case: the path is a scratch area this test
                # was handed and filled itself.
                return "scratch"
            if j == "unknown":
                return "unknown"
            # `local` included, and that is the correction. A path built
            # from literals -- `open("corpus.txt")` -- is still a path to a
            # real file; "the path expression is local" is not "the CONTENT
            # is local". The first version returned the join unchanged and
            # so reported every literal-path read as clean, which three of
            # this file's own tests caught before it reached the tree.
            return "tree"

        helper = None
        if isinstance(node.func, ast.Name):
            helper = self.mod.functions.get(node.func.id)
        if helper is not None and ctx.depth < MAX_DEPTH:
            params = _params(helper)
            bound = {}
            for i, p in enumerate(params):
                bound[p] = arg_provs[i] if i < len(arg_provs) else "local"
            for k in node.keywords:
                if k.arg in params:
                    bound[k.arg] = self.expr(fn, k.value, ctx)
            return join([self._helper(helper, bound, ctx)]
                        + ([recv] if recv else []))

        if not arg_provs and recv is None:
            # An opaque call with nothing flowing in. It could read
            # anything, so the honest answer is the residual.
            return "unknown"
        return join(arg_provs + ([recv] if recv else []))

    def _helper(self, helper, bound, ctx):
        """Provenance of a same-file helper's return value.

        NOT a guess: the analysis re-runs over the helper body with its
        parameters bound to the call site's argument provenances. A helper
        with no `return` (or one returning bare) is `local` -- it produced
        no value to be about."""
        cache_key = (id(helper), tuple(sorted(bound.items())))
        if cache_key in self._helper_cache:
            return self._helper_cache[cache_key]
        if id(helper) in ctx.helpers:
            # RECURSION. The first version answered `unknown` here, and it
            # cost the round its cleanest result: `test_v30.py`'s `h` is
            # `host(src)`, `host` returns `deep(box.payload)`, and `deep`
            # walks a value recursively -- so the one node round 498 had
            # correctly hand-declared a false positive came back as an
            # unresolved residual instead of `local`.
            #
            # The textbook answer is a least fixpoint from the bottom of
            # the lattice, not a residual. Recursive calls read the current
            # assumption (`local` on the first pass); the outer entry below
            # re-runs until the answer stops moving. `join` is monotone
            # over a 5-element chain, so it converges in at most 5 passes.
            return ctx.assume.get(id(helper), "local")
        ctx.helpers.add(id(helper))
        ctx.depth += 1
        saved = {}
        for p, prov in bound.items():
            saved[p] = ctx.params.get((id(helper), p))
            ctx.params[(id(helper), p)] = prov
        try:
            out = "local"
            for _pass in range(len(PROV_ORDER)):
                ctx.assume[id(helper)] = out
                provs = []
                for node in ast.walk(helper):
                    if isinstance(node, ast.Return) \
                            and node.value is not None:
                        provs.append(self.expr(helper, node.value, ctx))
                    elif isinstance(node, (ast.Yield, ast.YieldFrom)) \
                            and node.value is not None:
                        provs.append(self.expr(helper, node.value, ctx))
                nxt = join(provs)
                if nxt == out:
                    break
                out = nxt
            ctx.assume.pop(id(helper), None)
            if self.reaches_tree_regardless(helper):
                # A helper that touches the tree while ignoring its
                # parameters TAINTS whatever it hands back, even when the
                # returned expression is built from the arguments.
                # `test_v10.py::_copy_package(dst)` returns
                # `os.path.join(dst, "whence_ref")` -- a path under the
                # caller's scratch directory, so return-provenance alone
                # says `scratch` -- but the line above it copied
                # `ROOT/whence` into that directory. The path is scratch;
                # the CONTENT is the tree, and the content is what the
                # assertion below is about.
                out = join((out, "tree"))
        finally:
            for p, old in saved.items():
                if old is None:
                    ctx.params.pop((id(helper), p), None)
                else:
                    ctx.params[(id(helper), p)] = old
            ctx.depth -= 1
            ctx.helpers.discard(id(helper))
        self._helper_cache[cache_key] = out
        return out


class _Ctx:
    """Per-query state: recursion guards and the helper parameter binding."""

    def __init__(self):
        self.visiting = set()
        self.helpers = set()
        self.params = {}
        self.assume = {}
        self.reading = set()
        self.depth = 0


#: THE THREE CACHES BELOW ARE KEYED BY `id(fn)` AND HOLD THE NODE.
#:
#: Holding it is not an optimisation, it is the correctness condition.
#: CPython reuses an `id` once the object behind it is collected, and these
#: caches are module-level while the AST trees they describe are local to
#: `analyse_file` and `guard_rows` -- so a tree parsed for one file is
#: freed, a tree parsed for the next lands on the same addresses, and a
#: cache lookup returns another file's bindings.
#:
#: Round 500 shipped that and was caught by its own ledger: `--json`
#: followed immediately by `--check` reported `unknown 7` and then
#: `unknown 5` over an unchanged tree. Storing `(node, value)` keeps the
#: node alive so the `id` cannot be recycled; the `is` check beside every
#: lookup is the belt to that pair of braces. `test_subjprov.py` pins that
#: two processes agree, which is round 481's rule applied to a new module.
_FN_WRITE_CACHE = {}


def _writes_to(fn):
    """`path-name -> [written value exprs]` for `open(NAME, "w")` in `fn`.

    Two forms, both used in this tree:

        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)                       # <- `with`, the common one
        open(p, "w").write(s.replace(old, new)) # <- chained, test_v10.py

    The `with` form is matched by finding the handle name bound by the
    `with` item and collecting every `<handle>.write(X)` in its body. Note
    that the second example is a write into a path the test did NOT create
    -- `test_v10.py` sabotages a copy of the package -- which is exactly
    why this returns what was WRITTEN rather than a flat `local`: the
    sabotage payload is `s.replace(...)` and `s` came from the tree, so
    that path stays tree-derived and the node stays costly."""
    hit = _FN_WRITE_CACHE.get(id(fn))
    if hit is not None and hit[0] is fn:
        return hit[1]
    out = {}

    def record(path_node, payloads):
        if isinstance(path_node, ast.Name) and payloads:
            out.setdefault(path_node.id, []).extend(
                (getattr(v, "lineno", 0), v) for v in payloads)

    for node in ast.walk(fn):
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                call = item.context_expr
                if not _is_write_open(call) or not call.args:
                    continue
                handle = None
                if isinstance(item.optional_vars, ast.Name):
                    handle = item.optional_vars.id
                payloads = []
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call) \
                            and isinstance(inner.func, ast.Attribute) \
                            and inner.func.attr in ("write", "writelines") \
                            and inner.args \
                            and (handle is None
                                 or (isinstance(inner.func.value, ast.Name)
                                     and inner.func.value.id == handle)):
                        payloads.append(inner.args[0])
                record(call.args[0], payloads)
        elif isinstance(node, ast.Call) \
                and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("write", "writelines") \
                and node.args and _is_write_open(node.func.value) \
                and node.func.value.args:
            record(node.func.value.args[0], [node.args[0]])
    _FN_WRITE_CACHE[id(fn)] = (fn, out)
    return out


_FN_BINDING_CACHE = {}


def _fn_bindings(fn):
    hit = _FN_BINDING_CACHE.get(id(fn))
    if hit is None or hit[0] is not fn:
        hit = (fn, _bindings(fn))
        _FN_BINDING_CACHE[id(fn)] = hit
    return hit[1]


_FN_PARAM_CACHE = {}


def _params(fn):
    hit = _FN_PARAM_CACHE.get(id(fn))
    if hit is None or hit[0] is not fn:
        args = fn.args
        names = [a.arg for a in list(args.posonlyargs) + list(args.args)
                 + list(args.kwonlyargs) if a.arg != "self"]
        if args.vararg:
            names.append(args.vararg.arg)
        if args.kwarg:
            names.append(args.kwarg.arg)
        hit = (fn, names)
        _FN_PARAM_CACHE[id(fn)] = hit
    return hit[1]


def _subject_names(test_node):
    """`assertshadow.subjects`, restated: root names with builtins removed.

    Kept as its own function rather than imported so this module has no
    import-time dependency on `assertshadow`; `test_subjprov.py` pins that
    the two agree over the whole tree, so a divergence fails a test."""
    out = set()
    for node in ast.walk(test_node):
        if isinstance(node, ast.Name) and node.id not in NEUTRAL:
            out.add(node.id)
    return out


# --------------------------------------------------------------------------
# The second axis: does the magnitude GUARD something?
# --------------------------------------------------------------------------

def guards_a_use(fn, mag_node, shape_node):
    """Is the magnitude's subject READ between the magnitude and the shape?

    THE QUESTION DATAFLOW CANNOT ANSWER, and the one round 498's second
    false positive is really about.

        assert s.count(old) > 1                      # <- magnitude
        open(p, "w").write(s.replace(old, "..."))    # <- s is USED here
        ...
        assert [l[:4] for l in lines ...] == [...]   # <- shape

    That magnitude is a PRECONDITION: it checks the arrangement the very
    next statement depends on. Moving it below the shape assertion would
    not be a cleanup, it would delete a guard -- the sabotage would run
    against an unverified string and the failure downstream would be
    unreadable.

    Contrast round 494's instance, where `len(rows) == 114` is followed by
    nothing that touches `rows` until the shape assertion itself. Nothing
    is being guarded; the count is just standing in front of the door.

    Provenance and this are ORTHOGONAL and both are needed. A magnitude can
    be tree-derived AND a guard (`test_v10.py`), tree-derived and NOT a
    guard (round 494's, the real defect), or local and not a guard
    (harmless). Neither axis filters the census."""
    subs = _subject_names(mag_node.test if isinstance(mag_node, ast.Assert)
                          else mag_node)
    lo = mag_node.lineno
    hi = shape_node.lineno
    # Every node that lives INSIDE an assert, not just the `Assert` itself.
    # Skipping only the statement node left its `Name` children visible, so
    # a second magnitude assert stacked between the two counted as a "use"
    # of the first one's subject -- turning the deepest shadows in the tree
    # into preconditions. `test_another_assertion_in_between_is_not_a_use`
    # is that case.
    in_assert = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assert):
            for inner in ast.walk(node):
                in_assert.add(id(inner))
    for node in ast.walk(fn):
        if id(node) in in_assert:
            continue          # another assertion is not a USE
        lineno = getattr(node, "lineno", None)
        if lineno is None or not (lo < lineno < hi):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) \
                and node.id in subs:
            return True
    return False


# --------------------------------------------------------------------------
# Sweep
# --------------------------------------------------------------------------

def _asserts(fn):
    return [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]


def analyse_file(path):
    """`[{func, file, lineno, asserts: [...]}]` with provenance per assert."""
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src, filename=path)
    mod = ModuleIndex(tree, path)
    res = Resolver(mod)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        rows = []
        for a in _asserts(node):
            prov, per = res.assertion(node, a.test)
            rows.append({"lineno": a.lineno,
                         "src": ast.unparse(a.test),
                         "prov": prov,
                         "subjects": dict(sorted(per.items()))})
        out.append({"file": os.path.basename(path),
                    "func": node.name,
                    "lineno": node.lineno,
                    "asserts": rows})
    return out, res, mod


def analyse_tree(directory=None):
    """Every `test_*.py` in `directory`, sorted by file name."""
    directory = directory or TESTS
    files = sorted(f for f in os.listdir(directory)
                   if f.startswith("test_") and f.endswith(".py"))
    funcs = []
    helpers = {}
    for name in files:
        path = os.path.join(directory, name)
        rows, res, _mod = analyse_file(path)
        funcs.extend(rows)
        bad = res.helpers_that_ignore_their_arguments()
        if bad:
            helpers[name] = [(h, p) for h, p, _ in bad]
    return funcs, helpers


def _index(funcs):
    return dict(((f["file"], f["func"]), f) for f in funcs)


def compare_with_census(directory=None, census=None):
    """Pair-by-pair: what the name-list axis said, what dataflow says.

    Reads `assertshadow`'s census for the pair list rather than
    recomputing it, so the two instruments are compared over exactly the
    same population and a disagreement cannot be an artefact of a
    differently-derived pair set."""
    import assertshadow as A
    census = census or A.load_census()
    funcs, helpers = analyse_tree(directory)
    idx = _index(funcs)
    rows = []
    for nid, node in sorted(census["nodes"].items()):
        fname, func = nid.split("::", 1)
        entry = idx.get((fname, func))
        for p in node["pairs"]:
            # ROUND 522: `found` is the whole point. Before it, BOTH of the
            # ways this lookup can miss -- the census naming a function the
            # tree no longer has, and the census naming a line the function
            # no longer asserts on -- fell through to `unknown`, which is a
            # measurement. See `STALE`.
            prov, subjects, found = STALE, {}, False
            if entry:
                for a in entry["asserts"]:
                    if a["lineno"] == p["magnitude_line"]:
                        prov = a["prov"]
                        subjects = a["subjects"]
                        found = True
                        break
            rows.append({
                "node": nid,
                "magnitude_line": p["magnitude_line"],
                "magnitude": p["magnitude"],
                "shape_line": p["shape_line"],
                "independent": p["independent"],
                "heuristic": bool(p["tree_derived"]),
                "prov": prov,
                "derived": prov in DERIVED,
                "subjects": subjects,
                "census_line_found": found,
            })
    return rows, helpers


def stale_pairs(rows):
    """Census pairs this module could not locate in the live tree.

    `[(node, magnitude_line, why)]`. `why` distinguishes the two misses so
    a reader is not left guessing which regeneration they need: a MOVED
    line is an edit above the assert, a VANISHED node is a renamed or
    deleted test."""
    out = []
    for r in rows:
        if r.get("census_line_found", True):
            continue
        out.append((r["node"], r["magnitude_line"], r["magnitude"]))
    return sorted(out)


#: What to run when `stale_pairs` is non-empty. The CENSUS, not this
#: ledger -- round 522 measured that regenerating this ledger instead
#: writes the drift in as the answer and self-checks green.
CENSUS_REGEN = ("cd languages/whence && python3 assertshadow.py --history "
                "--json ../../state/whence/assert-shadow-census.json")


def guard_rows(directory=None, census=None):
    """`guards_a_use` for every census pair, keyed the same way as above."""
    import assertshadow as A
    census = census or A.load_census()
    directory = directory or TESTS
    out = {}
    for nid, node in sorted(census["nodes"].items()):
        fname, func = nid.split("::", 1)
        path = os.path.join(directory, fname)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        fn = None
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and n.name == func:
                fn = n
                break
        if fn is None:
            continue
        by_line = dict((a.lineno, a) for a in _asserts(fn))
        for p in node["pairs"]:
            mag = by_line.get(p["magnitude_line"])
            shp = by_line.get(p["shape_line"])
            if mag is None or shp is None:
                # ROUND 522: the SECOND instance of round 522's shape, and
                # the more dangerous one. A missing key here is read by
                # `totals` through `guards.get(...)`, whose absent value is
                # falsy -- so a stale coordinate does not merely lose a
                # guard verdict, it silently promotes the pair into
                # `costly_unguarded`, the list this module publishes as the
                # pairs worth repairing. It is invisible today only because
                # the OTHER silence masks it: a stale row's `derived` is
                # False, so it never reaches `costly_dataflow` to be counted
                # unguarded. Two silent degradations cancelling is not a
                # property to rely on. `stale_pairs` is the gate; this
                # `continue` is now reachable only when that gate has
                # already fired.
                continue
            out[(nid, p["magnitude_line"], p["shape_line"])] = \
                guards_a_use(fn, mag, shp)
    return out


def totals(rows, guards=None):
    """Every number the round publishes, each a SUM over `rows`."""
    guards = guards or {}
    kinds = {}
    for r in rows:
        kinds[r["prov"]] = kinds.get(r["prov"], 0) + 1
    agree = sum(1 for r in rows if r["heuristic"] == r["derived"])
    t2f = [r for r in rows if r["heuristic"] and not r["derived"]]
    f2t = [r for r in rows if r["derived"] and not r["heuristic"]]
    costly_old = [r for r in rows if r["independent"] and r["heuristic"]]
    costly_new = [r for r in rows if r["independent"] and r["derived"]]
    guarded = [r for r in costly_new
               if guards.get((r["node"], r["magnitude_line"],
                              r["shape_line"]))]
    return {
        "pairs": len(rows),
        "prov_kinds": dict(sorted(kinds.items())),
        "heuristic_derived": sum(1 for r in rows if r["heuristic"]),
        "dataflow_derived": sum(1 for r in rows if r["derived"]),
        "agree": agree,
        "disagree": len(rows) - agree,
        "heuristic_only": len(t2f),
        "dataflow_only": len(f2t),
        "unknown_residual": kinds.get("unknown", 0),
        # ROUND 522. Published beside the residual on purpose: these are the
        # pairs that would have been ADDED to it, silently, before `STALE`
        # existed. On a tree whose census matches, this is 0 -- and a 0 that
        # is written down is the positive control that the pairing ran.
        "stale_coordinates": kinds.get(STALE, 0),
        "pairs_costly_heuristic": len(costly_old),
        "nodes_costly_heuristic": len(set(r["node"] for r in costly_old)),
        "pairs_costly_dataflow": len(costly_new),
        "nodes_costly_dataflow": len(set(r["node"] for r in costly_new)),
        "pairs_costly_and_guarding": len(guarded),
        "pairs_costly_unguarded": len(costly_new) - len(guarded),
        "nodes_costly_unguarded": len(set(
            r["node"] for r in costly_new if not guards.get(
                (r["node"], r["magnitude_line"], r["shape_line"])))),
    }


# --------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------

def ledger_path():
    """`state/whence/subject-provenance.json`, resolved LAZILY.

    `curecheck.AGI_ROOT` and never a `__file__`-derived root, and never at
    import time -- `assertshadow.census_path`'s note, which is
    `depthcensus.contributions_path`'s note, which is curecheck's round-413
    finding that a `state/` read at import time aborted COLLECTION of the
    whole suite."""
    sys.path.insert(0, HERE)
    import curecheck
    return os.path.join(curecheck.AGI_ROOT, "state", "whence",
                        "subject-provenance.json")


def build_ledger(rows, helpers, guards):
    return {
        "_what": "provenance of the magnitude subject in every shadow pair "
                 "of state/whence/assert-shadow-census.json -- round 498's "
                 "next-step #2, measured by round 500.",
        "_regenerate": "cd languages/whence && python3 subjprov.py "
                       "--json ../../state/whence/subject-provenance.json",
        "_lattice": list(PROV_ORDER),
        "_derived": sorted(DERIVED),
        "_assumption": "arguments dominate: an opaque call propagates the "
                       "join of its arguments; same-file helpers are "
                       "analysed instead of assumed; "
                       "_helpers_ignoring_arguments is the measured size "
                       "of the remaining guess.",
        "totals": totals(rows, guards),
        "_helpers_ignoring_arguments": dict(
            (k, [[h, p] for h, p in v]) for k, v in sorted(helpers.items())),
        "disagreements": [
            {"node": r["node"], "magnitude_line": r["magnitude_line"],
             "magnitude": r["magnitude"], "heuristic": r["heuristic"],
             "prov": r["prov"], "subjects": r["subjects"]}
            for r in rows if r["heuristic"] != r["derived"]],
        "costly_dataflow": sorted(set(
            r["node"] for r in rows if r["independent"] and r["derived"])),
        "costly_unguarded": sorted(set(
            r["node"] for r in rows
            if r["independent"] and r["derived"]
            and not guards.get((r["node"], r["magnitude_line"],
                                r["shape_line"])))),
        "pairs": [
            {"node": r["node"], "magnitude_line": r["magnitude_line"],
             "shape_line": r["shape_line"], "magnitude": r["magnitude"],
             "independent": r["independent"], "heuristic": r["heuristic"],
             "prov": r["prov"], "derived": r["derived"],
             "guards_a_use": bool(guards.get((r["node"],
                                              r["magnitude_line"],
                                              r["shape_line"]))),
             "subjects": r["subjects"]}
            for r in rows],
    }


def dump_ledger(path, data):
    """`indent=2, ensure_ascii=False`, and the text is RETURNED.

    Round 499's `dump_registry` rule, applied to a second file: matching
    the file's own formatting is what keeps a four-line change from
    rendering as a whole-file diff."""
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


def load_ledger(path=None):
    path = path or ledger_path()
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_ledger(declared, rows, guards, helpers):
    """Findings where the ledger on disk disagrees with the live tree.

    THREE codes, and the third is what round 516 added:

        S001  a headline total moved
        S002  the costly-dataflow set moved
        S003  ANY OTHER top-level key of this document differs from what
              `build_ledger` would write right now

    WHY S003 HAD TO EXIST. Round 512 caught this ledger STALE -- it was
    missing `test_specstale.py` entirely -- while this very function
    returned `[]` and the CLI printed "0 finding(s)". Both of its codes
    were telling the truth: `totals` really had not moved (the new file
    contributes no shadow pair) and `costly_dataflow` really had not moved.
    They range over two of the document's eleven top-level keys, and the
    drift was in `_helpers_ignoring_arguments`, which is one of the other
    nine. A self-check blind to the staleness it exists to detect is worse
    than no self-check, because round 512 found it QUOTED AS EVIDENCE.

    The fix is not a twelfth bespoke comparison. It is to stop enumerating
    what to compare: `build_ledger` is a pure function of `(rows, helpers,
    guards)`, so the total predicate is "the document I would write now
    equals the document on disk", and S001/S002 survive only because their
    messages are more readable than a whole-key diff. That is why `helpers`
    is now a REQUIRED argument -- there is no partial mode to fall back to.

    S001 also now ranges over the UNION of the declared and live totals
    rather than over the live ones alone; a total that exists on disk and
    no longer exists in the tree used to be invisible for the same reason.
    And `declared["totals"]` is read with `.get`: round 516's mutation
    sweep found the subscript was the one place where a malformed ledger
    made this verb raise instead of report."""
    import checkscope                                  # noqa: PLC0415
    out = []
    # ROUND 522: S004 IS FIRST, and it is the only code here that is about
    # the live tree's INPUT rather than about the ledger's contents. If the
    # census coordinates are stale then every other finding below is
    # downstream of a bad pairing, and -- measured, round 522 -- acting on
    # them regenerates this ledger with the drift written in as the answer.
    # A reader who sees S004 must fix the census and re-run; there is
    # nothing here they can usefully act on until they do.
    stale = stale_pairs(rows)
    if stale:
        out.append(("S004", "census_coordinates",
                    "%d census pair(s) name a line the live tree has no "
                    "assert on (first: %s line %d). Their provenance is not "
                    "`unknown`, it is UNMEASURED. Regenerate the CENSUS "
                    "first: %s"
                    % (len(stale), stale[0][0], stale[0][1], CENSUS_REGEN)))
    live_doc = build_ledger(rows, helpers, guards)
    live = live_doc["totals"]
    dec_totals = declared.get("totals")
    if not isinstance(dec_totals, dict):
        out.append(("S001", "totals",
                    "ledger has no `totals` object (%r)" % (dec_totals,)))
        dec_totals = {}
    for k in sorted(set(live) | set(dec_totals)):
        if dec_totals.get(k) != live.get(k):
            out.append(("S001", k,
                        "ledger says %r, tree says %r"
                        % (dec_totals.get(k), live.get(k))))
    live_costly = live_doc["costly_dataflow"]
    if declared.get("costly_dataflow") != live_costly:
        out.append(("S002", "costly_dataflow",
                    "ledger %r, tree %r"
                    % (declared.get("costly_dataflow"), live_costly)))
    for key, why in checkscope.document_diff(
            declared, live_doc, ignore=("totals", "costly_dataflow")):
        out.append(("S003", key, why))
    return out


# --------------------------------------------------------------------------
# Rendering / CLI
# --------------------------------------------------------------------------

def render_compare(rows, guards, limit=None):
    lines = []
    t = totals(rows, guards)
    lines.append("pairs %d | heuristic-derived %d | dataflow-derived %d | "
                 "agree %d | disagree %d"
                 % (t["pairs"], t["heuristic_derived"],
                    t["dataflow_derived"], t["agree"], t["disagree"]))
    lines.append("  heuristic-only %d   dataflow-only %d   unknown %d"
                 % (t["heuristic_only"], t["dataflow_only"],
                    t["unknown_residual"]))
    lines.append("  COSTLY  heuristic %d pair(s)/%d node(s)  ->  "
                 "dataflow %d/%d  ->  unguarded %d/%d"
                 % (t["pairs_costly_heuristic"], t["nodes_costly_heuristic"],
                    t["pairs_costly_dataflow"], t["nodes_costly_dataflow"],
                    t["pairs_costly_unguarded"], t["nodes_costly_unguarded"]))
    lines.append("")
    shown = rows if limit is None else rows[:limit]
    for r in shown:
        flag = " " if r["heuristic"] == r["derived"] else "*"
        g = "G" if guards.get((r["node"], r["magnitude_line"],
                               r["shape_line"])) else " "
        lines.append("%s%s %-8s heur=%-5s  %s:%d  %s"
                     % (flag, g, r["prov"], r["heuristic"],
                        r["node"].split("::")[0], r["magnitude_line"],
                        r["magnitude"][:52]))
    lines.append("")
    lines.append("* = the two axes disagree.  G = the magnitude guards a "
                 "use of its own subject between the two asserts.")
    return "\n".join(lines)


def render_helpers(helpers):
    lines = ["in-file helpers that reach the tree while IGNORING their "
             "arguments -- every one of these is a case where the "
             "\"arguments dominate\" assumption would have been wrong:"]
    n = 0
    for fname, hs in sorted(helpers.items()):
        for h, params in hs:
            n += 1
            lines.append("  %-34s %s(%s)" % (fname, h, ", ".join(params)))
    lines.append("  %d helper(s)." % n)
    return "\n".join(lines)


def main(argv):
    args = list(argv)
    directory = None
    if "--tests" in args:
        i = args.index("--tests")
        directory = args[i + 1]
        del args[i:i + 2]

    # Round 516 (language C): `--check` could only ever read ONE path, the
    # one `ledger_path()` computes. That is why nothing had ever measured
    # what this verb can see: the only way to run it against a candidate
    # ledger was to overwrite the real one first. `checkscope.py` mutates a
    # COPY and points the verb at it.
    ledger_override = None
    if "--ledger" in args:
        i = args.index("--ledger")
        ledger_override = args[i + 1]
        del args[i:i + 2]

    if "--helpers" in args:
        _funcs, helpers = analyse_tree(directory)
        print(render_helpers(helpers))
        return 0

    rows, helpers = compare_with_census(directory)
    guards = guard_rows(directory)

    # ROUND 522: computed once, before either verb, because BOTH of them
    # are wrong to run while it is non-empty -- `--json` would write the
    # drift in, `--check` would report eight downstream findings and name
    # the wrong file to regenerate.
    stale = stale_pairs(rows)

    if "--json" in args:
        i = args.index("--json")
        path = args[i + 1] if i + 1 < len(args) else ledger_path()
        if stale:
            # REFUSE. This is the one change in round 522 that makes the
            # measured false-green unreachable: writing a provenance ledger
            # from a census that does not match the tree is never correct,
            # and `corpusledger.fix()` reads this exit code, so the
            # dependency between the two generated ledgers is now enforced
            # by the downstream generator rather than by the accident that
            # `assert-shadow-census.json` sorts before
            # `subject-provenance.json`.
            print("REFUSING to write %s: %d census pair(s) name a line the "
                  "live tree has no assert on." % (path, len(stale)))
            for node, line, mag in stale[:10]:
                print("  STALE  %s  line %d  %s" % (node, line, mag))
            if len(stale) > 10:
                print("  ... and %d more" % (len(stale) - 10))
            print("Regenerate the CENSUS first, then re-run this:")
            print("    %s" % CENSUS_REGEN)
            return 2
        dump_ledger(path, build_ledger(rows, helpers, guards))
        print("wrote %s" % path)
        return 0

    if "--check" in args:
        findings = check_ledger(load_ledger(ledger_override), rows, guards,
                                helpers)
        for code, what, msg in findings:
            print("%s %s: %s" % (code, what, msg))
        if stale:
            print("%d finding(s). The CENSUS is stale; regenerate it FIRST "
                  "and re-run -- regenerating this ledger now writes the "
                  "drift in as the answer:" % len(findings))
            print("    %s" % CENSUS_REGEN)
        else:
            print("%d finding(s). Regenerate: python3 subjprov.py --json "
                  "../../state/whence/subject-provenance.json"
                  % len(findings))
        return 1 if findings else 0

    print(render_compare(rows, guards))
    if "--compare" not in args:
        print()
        print(render_helpers(helpers))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Differential and metamorphic oracles for the Whence interpreter (round 10).

Round 5's oracle was *totality* ("no Python exception escapes"). Once that
reaches zero findings the fuzzer is blind: a wrong answer is not a crash.
These oracles compare the interpreter against ITSELF, so they are still
zero-false-positive — every mismatch is a real defect somewhere — but they
see semantic bugs:

  fast_slow     `Interpreter(fast=True)` (v0.4 compiled closures, inline
                tail calls, merged `if` decisions) must give byte-identical
                canonical behaviour AND why-trees to `fast=False` (generator
                path). Any difference is a bug in one of the two evaluators.
  direct        (round 30) `Interpreter(direct=True)` (v0.9 host-recursion
                calls under a frame budget) must agree byte for byte with
                `direct=False` (v0.8: everything with a call on the
                trampoline). Skipped as ok on packages without the flag.
  determinism   parse once, execute the same AST twice with two fresh
                interpreters, then once more from a fresh parse: all three
                behaviours must agree. Catches state cached on AST nodes
                (`node.const` literal sharing, `compile_fast` caches) that
                leaks between runs.
  totality      round 5's oracle on the package under test: no Python
                exception escapes; every binding is its own provenance node.
  render        for every top-level binding: `render_why`, `full_show`,
                `walk_steps`, `diverge(v, v)`, `render_contrast(v, v)` must
                not raise, `diverge(v, v)` must be empty, `contrast(v, v)`
                must be "no divergence" (metamorphic identity), and
                `diverge(a, b)` must mirror `diverge(b, a)` (symmetry) for
                every pair of bindings.

  tail_transparency
                (round 337) the tail-call transparency oracle. v0.3 tail
                calls are a SPACE optimisation, so a call's ANSWER must not
                depend on it being in tail position: the program is parsed
                twice and `parser.mark_tails`'s own `Call.tail` flags are
                cleared on the second AST, and `out` / `checks` / `vals`
                must agree. Round 336 found this claim false in two ways at
                once (outermost-first blame in a typed chain, and the outer
                call's line rather than the tail call's own) and fixed both;
                this drives the same transform over generated programs. The
                `why` tree is the may-differ field and programs that reflect
                on provenance are exempt — see the long comment above
                `oracle_tail_transparency` for both lists.

  param_erasure
                (round 359) the v0.19 parameter-contract oracle. v0.19
                moved a `p: Type` annotation off the body and onto the
                FnDef/FnExpr node, and `_check_params`'s docstring claims
                its properties are "inherited from the v0.12 guards this
                replaces rather than newly chosen, so that moving the check
                does not also change what it means". This erases the
                contracts back into v0.12's prepended `let p = typed(p,
                spec, label)` guards — a transcription of the deleted
                `Parser._apply_type_guards`, verified node-for-node against
                the real pre-v0.19 parser — and requires the same `out` /
                `checks` / `vals`. `why` is the may-differ field (a `let`
                adds a provenance node; a satisfied contract adds none).
                Two exemptions, both about WHERE a spec name is looked up,
                and both MEASURED rather than skipped — see the long
                comment above `oracle_param_erasure`.

  frames        (round 110) the frame-charge oracle. Direct mode charges
                every host frame it will use (`cdepth` + 1 per call)
                against a budget measured at `exec_stmt`; round 108's bug
                was a frame the charge did not know (a list comprehension
                per level), invisible at the default limit because the
                350-frame reserve absorbed ~160 uncounted levels. Under
                `sys.setprofile` this oracle tracks the host frames
                actually on the stack above `exec_stmt` minus the frames
                charged so far (`h0 - interp._hleft`); the maximum of that
                EXCESS over the run is the transient the reserve must
                cover. It is bounded by construction (fast-closure
                recursion, one nested drive, render helpers); an
                undercount makes it grow with guest depth. Excess above
                FRAME_SLACK is a finding; the detail carries the number
                either way, so a campaign can report the distribution.

Every oracle returns an `OracleOutcome`; `signature()` groups findings by
root cause so the campaign shrinks one reproducer per cause, exactly as the
totality fuzzer does.
"""

import os
import signal
import sys
import time
import traceback

from .fuzz import ProgramGen, WHENCE_ROOT, shrink, list_example_files, _whence_frames
from .killers import load_whence, _Timeout, _alarm

ORACLE_NAMES = ("totality", "fast_slow", "direct", "determinism", "render",
                "frames", "tail_transparency", "param_erasure")

# Largest transient (host frames used above the charge) the frames oracle
# tolerates. The transient is bounded by construction: a call-free subtree
# compiles to closures only up to `Interpreter.FAST_MAX_DEPTH` (100)
# levels of host recursion, plus one nested drive and its helpers. Measured
# (round 110, 264 programs + examples): examples <= 19, most fuzz programs
# 5-20, the fuzzer's `1 + 1 + ...` chains 98, nested list literals 59 —
# all at guest depth 0. An uncharged frame per guest level (round 108's
# bug) reaches 161 within ~160 levels at the DEFAULT recursion limit and
# ~1400 at the CLI's 6000 (`--limit`), so the slack separates the two.
FRAME_SLACK = 140


class OracleOutcome(object):
    """kind: ok | parse_error | timeout | crash | mismatch"""
    __slots__ = ("kind", "oracle", "detail", "exc_type", "frames", "seconds")

    def __init__(self, kind, oracle, detail="", exc_type="", frames=(), seconds=0.0):
        self.kind = kind
        self.oracle = oracle
        self.detail = detail
        self.exc_type = exc_type
        self.frames = tuple(frames)
        self.seconds = seconds

    def as_dict(self):
        return {"kind": self.kind, "oracle": self.oracle, "detail": self.detail[:400],
                "exc_type": self.exc_type, "frames": list(self.frames),
                "seconds": round(self.seconds, 4)}

    def __repr__(self):
        return "OracleOutcome(%s, %s, %r)" % (self.kind, self.oracle, self.detail[:60])


def signature(o):
    """Stable key for grouping oracle findings by root cause."""
    if o.kind not in ("crash", "mismatch"):
        return (o.kind,)
    if o.kind == "crash":
        # a crash is the same defect whichever oracle tripped over it, so
        # the oracle name is NOT part of the key (one finding per cause)
        if o.exc_type == "RecursionError" and o.frames:
            counts = {}
            for name, _, _ in o.frames:
                counts[name] = counts.get(name, 0) + 1
            cycle = sorted(n for n, c in counts.items() if c >= 2)
            return ("crash", o.exc_type, "cycle:" + "+".join(cycle))
        inner = o.frames[-1][0] if o.frames else "?"
        return ("crash", o.exc_type, inner)
    # mismatch: the detail's first line names the field that differs and,
    # for value differences, the op of the first differing why-line
    return ("mismatch", o.oracle, o.detail.split("\n", 1)[0][:60])


# ------------------------------------------------------------- behaviour --

def _parse(pkg, src):
    parser = __import__(pkg["name"] + ".parser", fromlist=["parse"])
    return parser.parse(src)


def _values_mod(pkg):
    return __import__(pkg["name"] + ".values", fromlist=["render_why"])


def _run_ast(pkg, program, fast=True, max_depth=500, direct=None):
    """Execute a parsed program; return (interp, env, out). `direct` is
    passed only when given (older packages have no such flag)."""
    out = []
    kw = {"out": out.append, "max_depth": max_depth, "fast": fast}
    if direct is not None:
        kw["direct"] = direct
    interp = pkg["Interpreter"](**kw)
    env = pkg["Env"](interp.globals)
    for stmt in program.stmts:
        interp.exec_stmt(stmt, env)
    return interp, env, out


def behaviour_ex(pkg, src, fast=True, max_depth=500, program=None, direct=None):
    """Canonical behaviour (as killers.canonical) plus the why-tree of every
    top-level binding. Parse/lex errors and crashes are data, not raises."""
    V = _values_mod(pkg)
    if program is None:
        try:
            program = _parse(pkg, src)
        except (pkg["LexError"], pkg["ParseError"]) as e:
            return {"kind": type(e).__name__, "message": str(e)}
    interp, env, out = _run_ast(pkg, program, fast=fast, max_depth=max_depth,
                                direct=direct)
    return {
        "kind": "ok",
        "out": out,
        "checks": [[c["label"], c["ok"]] for c in interp.checks],
        "vals": dict((k, pkg["full_show"](v.payload)) for k, v in env.vars.items()),
        "why": dict((k, V.render_why(v)) for k, v in env.vars.items()),
        "fast_hits": interp.fast_hits > 0,
    }


def first_difference(a, b):
    """Human-readable description of the first differing field of two
    behaviour dicts; '' when equal."""
    if a == b:
        return ""
    if a.get("kind") != b.get("kind"):
        return "kind: %s vs %s" % (a.get("kind"), b.get("kind"))
    for key in ("out", "checks", "vals", "why"):
        x, y = a.get(key), b.get(key)
        if x == y:
            continue
        if isinstance(x, dict):
            for name in sorted(set(x) | set(y)):
                if x.get(name) != y.get(name):
                    xs, ys = str(x.get(name)), str(y.get(name))
                    if key == "why":
                        # name the first differing why-line, not the binding
                        xl, yl = xs.split("\n"), ys.split("\n")
                        for i, (p, q) in enumerate(zip(xl, yl)):
                            if p != q:
                                return "why[%s] line %d\n  A: %s\n  B: %s" % (name, i, p.strip(), q.strip())
                        return "why[%s] length %d vs %d\n  A: %s\n  B: %s" % (
                            name, len(xl), len(yl), xs[-200:], ys[-200:])
                    return "%s[%s]\n  A: %s\n  B: %s" % (key, name, xs[:200], ys[:200])
        return "%s\n  A: %s\n  B: %s" % (key, str(x)[:200], str(y)[:200])
    return "other: %s" % sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


# ---------------------------------------------------------------- oracles --

def oracle_totality(pkg, src, max_depth=500):
    """Round 5's oracle, on the package under test (not the global import):
    no Python exception may escape the interpreter, and every top-level
    binding must be a value that is its own provenance node."""
    try:
        program = _parse(pkg, src)
    except (pkg["LexError"], pkg["ParseError"]) as e:
        return OracleOutcome("parse_error", "totality", type(e).__name__)
    interp, env, out = _run_ast(pkg, program, max_depth=max_depth)
    for name, v in env.vars.items():
        if getattr(v, "prov", None) is not v or v.prov.value is not v.payload:
            return OracleOutcome("mismatch", "totality", "invariant[%s] value is not its node" % name)
    return OracleOutcome("ok", "totality")


def oracle_fast_slow(pkg, src, max_depth=500):
    a = behaviour_ex(pkg, src, fast=True, max_depth=max_depth)
    if a["kind"] != "ok":
        return OracleOutcome("parse_error", "fast_slow", a["kind"])
    b = behaviour_ex(pkg, src, fast=False, max_depth=max_depth)
    a.pop("fast_hits", None)
    b.pop("fast_hits", None)
    d = first_difference(a, b)
    return OracleOutcome("mismatch" if d else "ok", "fast_slow", d)


def oracle_determinism(pkg, src, max_depth=500):
    try:
        program = _parse(pkg, src)
    except (pkg["LexError"], pkg["ParseError"]) as e:
        return OracleOutcome("parse_error", "determinism", type(e).__name__)
    a = behaviour_ex(pkg, src, program=program, max_depth=max_depth)
    b = behaviour_ex(pkg, src, program=program, max_depth=max_depth)   # same AST again
    d = first_difference(a, b)
    if d:
        return OracleOutcome("mismatch", "determinism", "same-AST rerun: " + d)
    c = behaviour_ex(pkg, src, max_depth=max_depth)                    # fresh parse
    d = first_difference(a, c)
    return OracleOutcome("mismatch" if d else "ok", "determinism",
                         ("fresh-parse rerun: " + d) if d else "")


def _mirror(origins):
    """diverge(a, b) origins with the a/b sides swapped."""
    return [(nb, na, kind) for (na, nb, kind) in origins]


def oracle_render(pkg, src, max_depth=500):
    V = _values_mod(pkg)
    try:
        program = _parse(pkg, src)
    except (pkg["LexError"], pkg["ParseError"]) as e:
        return OracleOutcome("parse_error", "render", type(e).__name__)
    interp, env, out = _run_ast(pkg, program, max_depth=max_depth)
    names = list(env.vars)
    for name in names:
        v = env.vars[name]
        V.render_why(v)
        pkg["full_show"](v.payload)
        n_steps = sum(1 for _ in V.walk_steps(v))
        if n_steps < 1:
            return OracleOutcome("mismatch", "render", "steps[%s] empty" % name)
        d = V.diverge(v, v)
        if d:
            return OracleOutcome("mismatch", "render", "self-diverge[%s] %d origins" % (name, len(d)))
        c = V.render_contrast(v, v)
        if c != "no divergence":
            return OracleOutcome("mismatch", "render", "self-contrast[%s] %r" % (name, c[:80]))
    # symmetry of diverge over every pair (bounded: first 6 bindings)
    for i, x in enumerate(names[:6]):
        for y in names[i + 1:6]:
            ab = V.diverge(env.vars[x], env.vars[y])
            ba = V.diverge(env.vars[y], env.vars[x])
            if [(id(p), id(q), k) for p, q, k in _mirror(ab)] != [(id(p), id(q), k) for p, q, k in ba]:
                return OracleOutcome("mismatch", "render",
                                     "diverge asymmetry[%s,%s] %d vs %d origins" % (x, y, len(ab), len(ba)))
    return OracleOutcome("ok", "render")


def has_direct_mode(pkg):
    """Whether the package under test knows `Interpreter(direct=...)`."""
    import inspect
    try:
        return "direct" in inspect.signature(pkg["Interpreter"].__init__).parameters
    except (TypeError, ValueError):
        return False


def oracle_direct(pkg, src, max_depth=500):
    """v0.9 direct mode vs the v0.8 trampoline-for-calls behaviour (both
    with the call-free fast path on): the third leg of the differential.
    fast_slow already compares direct against the pure trampoline; this
    one isolates the direct-call machinery from the fast path."""
    if not has_direct_mode(pkg):
        return OracleOutcome("ok", "direct", "interpreter has no direct mode")
    a = behaviour_ex(pkg, src, fast=True, max_depth=max_depth, direct=True)
    if a["kind"] != "ok":
        return OracleOutcome("parse_error", "direct", a["kind"])
    b = behaviour_ex(pkg, src, fast=True, max_depth=max_depth, direct=False)
    a.pop("fast_hits", None)
    b.pop("fast_hits", None)
    d = first_difference(a, b)
    return OracleOutcome("mismatch" if d else "ok", "direct", d)


# ------------------------------------------------- tail transparency (337) --
#
# Round 336 (language C) established the claim this oracle tests: v0.3 tail
# calls are a SPACE optimisation ("merge, they do not forget", SPEC decision
# 8), so a program's ANSWER must not depend on whether a call sits in tail
# position. Round 336 found that claim false in two ways at once — a typed
# chain blamed the outermost `-> Type` contract where the same chain lifted
# out of tail position blamed the innermost one, and every chain check
# reported the OUTER call's line instead of the tail call's own — and fixed
# both. Its own differential was a hand-built family in
# `languages/whence/tests/test_v13.py` (2325 chain programs, each written
# out twice); its next-steps item 2 asked for the transform as a real oracle
# so the fuzzer can drive it over programs nobody wrote.
#
# THE TRANSFORM. Round 336 described a SOURCE rewrite (`f()` -> `let __t =
# f()  __t`, kept on one line so the miss line number stays comparable).
# This oracle instead clears `Call.tail` — the flag `parser.mark_tails` set
# — on a second, independently parsed AST. That is the same transform
# expressed where the language itself defines tail position, and it is the
# better one for an oracle whose whole value is being zero-false-positive:
#   * a source rewrite needs a second, hand-written tail-position finder, and
#     any bug in THAT reimplementation of `mark_tails` reports as an
#     interpreter finding;
#   * there is no rewrite, so no line can shift — the line-alignment round
#     336 had to engineer ("a naive multi-line rewrite would force stripping
#     the line again") holds by construction;
#   * parse-time facts (`effects [...]`, `tail_alias_tag`, `param_call_fact`)
#     are identical on both sides, so a divergence can only come from the
#     runtime tail path — which is the thing under test. Round 336 confirmed
#     independently that `effects` is exempt from this class by construction.
# Equivalence to round 336's own textual form is not assumed: round 337
# re-ran its exact `chain_pair` family (450 programs, hops 2-3) comparing
# THIS transform's result against round 336's literal `let t = ...  t`
# source, and got 450/450 on the fixed interpreter AND 450/450 on the
# pre-fix one — agreeing on the wrong answers too, which is the stronger
# half. Pinned in `test_swe_oracles.py`.
#
# MUST MATCH / MAY DIFFER, written before the first comparison:
#   must match  `out`, `checks`, `vals` — everything the program answers.
#               `vals` renders a Miss with its whole reason list including
#               line numbers, so this is round 336's "identical payloads and
#               identical miss reason tuples" at every top-level binding.
#   may differ  `why`. The merged `call f/g xN` node IS the optimisation's
#               documented signature; the lifted form's tree is N nested
#               `call` nodes instead of one flat merged node, so the trees
#               differ in SHAPE, not in one line (measured round 337 on
#               `even`/`odd` at n=6). Comparing it would test that the
#               optimisation did NOT happen.
#   exempt      whole programs that REFLECT on provenance (`steps`, `at`,
#               `blame`, `diverge`, `contrast`, `why`, `snip`), because in a
#               provenance-first language those builtins reify the may-differ
#               why-tree into an ordinary value, which then flows straight
#               into the must-match fields — `print(str(steps(t)))` puts
#               `count: 1501` in `out`. The observable set here CANNOT be
#               split field by field.
#   exempt      programs where the lifted run hits the depth wall the tail
#               run was built to avoid (`peak_depth >= max_depth`, or a host
#               `RecursionError`). That is the space optimisation working:
#               `even(1500)` answers `true` merged and
#               `miss: recursion too deep` unmerged.
# Every exemption is named in `detail`, so a campaign reports the
# distribution instead of hiding it — the convention `oracle_frames`
# already uses for its measured excess.

TAIL_ORACLE = "tail_transparency"

# Builtins that read the why-tree back out as a value. A NameRef to any of
# these anywhere in the program exempts it (deliberately coarse: shadowing
# one of these names only costs coverage, never correctness).
PROVENANCE_BUILTINS = frozenset(("steps", "at", "blame", "diverge", "contrast"))


def iter_ast_nodes(root):
    """Every AST node reachable from `root`, once each, iteratively.

    Iterative on purpose: the fuzzer emits expression chains deep enough
    (`1 + 1 + ...`, nested list literals) that a recursive walk hits the
    host recursion limit before the interpreter does.
    """
    stack, seen = [root], set()
    while stack:
        n = stack.pop()
        if n is None or id(n) in seen:
            continue
        slots = getattr(type(n), "__slots__", None)
        if slots is None or not hasattr(n, "line"):
            continue          # not an AST node (str, int, spec tuple, ...)
        seen.add(id(n))
        yield n
        for name in slots:
            try:
                v = getattr(n, name)
            except AttributeError:
                continue      # unset slot (`Node.entry` before first call)
            if type(v) is list or type(v) is tuple:
                for x in v:
                    if type(x) is list or type(x) is tuple:
                        stack.extend(x)     # RecordLit pairs, spec tuples
                    else:
                        stack.append(x)
            else:
                stack.append(v)


def clear_tail_flags(program):
    """Undo `parser.mark_tails` over a whole program; return how many calls
    were un-tailed. 0 means the program has no tail call at all, so the
    optimisation cannot be observed and there is nothing to compare."""
    n = 0
    for node in iter_ast_nodes(program):
        if type(node).__name__ == "Call" and getattr(node, "tail", False):
            node.tail = False
            n += 1
    return n


def reflects_on_provenance(node):
    """Name of the first provenance-reflecting construct at or under `node`,
    or "" — see the module comment on why these have to be excluded."""
    for n in iter_ast_nodes(node):
        cls = type(n).__name__
        if cls == "Why":
            return "why"
        if cls == "Snip":
            return "snip"
        if cls == "NameRef" and n.name in PROVENANCE_BUILTINS:
            return n.name
    return ""


def _bound_name(stmt):
    """The top-level name a statement binds (`let x = ...` / `fn f() ...`),
    or None."""
    cls = type(stmt).__name__
    if cls in ("Let", "FnDef"):
        return stmt.name
    return None


def provenance_tainted_names(program):
    """Top-level names whose VALUE could depend on the why-tree, so on
    whether tail merging happened.

    Round 337 first exempted any program containing a reflective construct
    at all; on the round's own corpus that was 213 of 400 generated
    programs, because `ProgramGen.probe` ends most programs with
    `print(str(steps(v)))`. Almost always the reflection is in a probe or a
    neighbouring binding, and the CHAIN RESULT the oracle actually wants to
    compare is clean. So taint instead of exempt: a statement is tainted if
    it reflects anywhere in its own subtree (including nested `fn` bodies
    and anonymous `fn` arguments) or references an already-tainted name, and
    it passes that taint to whatever name it binds.

    Iterated to a fixpoint rather than run once in statement order: Whence
    resolves function names at call time, so `fn a() { b() }` may precede
    `fn b() { steps(x) }` and a single forward pass would under-taint `a`.
    """
    tainted = set()
    facts = []
    for stmt in program.stmts:
        refs = set(n.name for n in iter_ast_nodes(stmt)
                   if type(n).__name__ == "NameRef")
        facts.append((_bound_name(stmt), refs, bool(reflects_on_provenance(stmt))))
    changed = True
    while changed:
        changed = False
        for name, refs, reflective in facts:
            if name and name not in tainted and (reflective or (refs & tainted)):
                tainted.add(name)
                changed = True
    return tainted


def _answer(pkg, program, tainted, whole, max_depth=500):
    """`(answer_dict, peak_depth)` — the must-match fields only, plus the
    depth the run actually reached (the space-exemption signal).

    `whole` is True when the program reflects on provenance NOWHERE, in
    which case every field is comparable. Otherwise only the `vals` of
    untainted bindings are: `out` and `checks` are ordered by EXECUTION,
    not by statement, so a print or a check inside a function body cannot
    be attributed back to a top-level name and dropped individually.
    """
    interp, env, out = _run_ast(pkg, program, max_depth=max_depth)
    vals = dict((k, pkg["full_show"](v.payload)) for k, v in env.vars.items()
                if k not in tainted)
    a = {"vals": vals}
    if whole:
        a["out"] = out
        a["checks"] = [[c["label"], c["ok"]] for c in interp.checks]
    return a, interp.peak_depth


def oracle_tail_transparency(pkg, src, max_depth=500):
    """A call's ANSWER must not depend on it being in tail position."""
    try:
        program = _parse(pkg, src)
        lifted = _parse(pkg, src)          # a second, independent AST
    except (pkg["LexError"], pkg["ParseError"]) as e:
        return OracleOutcome("parse_error", TAIL_ORACLE, type(e).__name__)
    n = clear_tail_flags(lifted)
    if n == 0:
        return OracleOutcome("ok", TAIL_ORACLE, "no tail calls")
    tainted = provenance_tainted_names(program)
    whole = not reflects_on_provenance(program)
    scope = "all fields" if whole else "untainted vals only (%d tainted)" % len(tainted)
    a, _ = _answer(pkg, program, tainted, whole, max_depth=max_depth)
    try:
        b, peak = _answer(pkg, lifted, tainted, whole, max_depth=max_depth)
    except RecursionError:
        return OracleOutcome("ok", TAIL_ORACLE,
                             "%d tail calls, lifted run exhausted the host "
                             "stack (space-exempt)" % n)
    if peak >= max_depth:
        return OracleOutcome("ok", TAIL_ORACLE,
                             "%d tail calls, lifted run reached depth %d >= "
                             "max_depth %d (space-exempt)" % (n, peak, max_depth))
    if not a["vals"] and not whole:
        return OracleOutcome("ok", TAIL_ORACLE,
                             "%d tail calls, every binding provenance-tainted "
                             "(exempt)" % n)
    d = first_difference(a, b)
    detail = "%d tail calls, %s" % (n, scope)
    if d:
        return OracleOutcome("mismatch", TAIL_ORACLE,
                             "tail vs lifted: " + d + "\n  (%s)" % detail)
    return OracleOutcome("ok", TAIL_ORACLE, detail)


def frame_excess(pkg, program, max_depth=500):
    """Run `program` (a parsed AST) in direct mode under a profile hook and
    return `(max_excess, guest_depth_at_max, interp)`: the largest number of
    host frames on the stack above `exec_stmt` beyond what direct mode had
    charged against its budget at that moment. `h0` is the budget the
    interpreter measured for the statement (read at its first `_drive`
    call, which follows the measurement); `charged` = `h0 - _hleft`.
    Generator frames count while they run (setprofile reports each
    resumption as a call), C calls are ignored — so this is in host-frame
    units, the units of `cdepth`; the recursion limit also counts a few
    C-level entries per Python call, which is the reserve's own margin."""
    out = []
    interp = pkg["Interpreter"](out=out.append, max_depth=max_depth, direct=True)
    env = pkg["Env"](interp.globals)
    state = {"depth": 0, "d0": None, "h0": None, "best": -10 ** 9, "at": 0}

    def hook(frame, event, arg):
        if event == "call":
            d = state["depth"] = state["depth"] + 1
            name = frame.f_code.co_name
            if state["d0"] is None:
                if name == "exec_stmt":
                    state["d0"] = d
                return
            if state["h0"] is None:
                if name == "_drive":
                    state["h0"] = interp._hleft
                return
            excess = (d - state["d0"]) - (state["h0"] - interp._hleft)
            if excess > state["best"]:
                state["best"] = excess
                state["at"] = interp.depth
        elif event == "return":
            state["depth"] -= 1
            if state["d0"] is not None and state["depth"] < state["d0"]:
                state["d0"] = None          # exec_stmt returned: re-arm
                state["h0"] = None

    sys.setprofile(hook)
    try:
        for stmt in program.stmts:
            interp.exec_stmt(stmt, env)
    finally:
        sys.setprofile(None)
    return state["best"], state["at"], interp


def oracle_frames(pkg, src, max_depth=500, slack=None):
    """The frame-charge oracle (round 110, see the module docstring): the
    transient host-frame excess over the charge must stay under
    FRAME_SLACK for the whole run. `detail` always carries the measured
    maximum and the guest depth it occurred at."""
    if not has_direct_mode(pkg):
        return OracleOutcome("ok", "frames", "interpreter has no direct mode")
    try:
        program = _parse(pkg, src)
    except (pkg["LexError"], pkg["ParseError"]) as e:
        return OracleOutcome("parse_error", "frames", type(e).__name__)
    if slack is None:
        slack = FRAME_SLACK
    best, at, interp = frame_excess(pkg, program, max_depth=max_depth)
    detail = "max excess %d frames at guest depth %d (slack %d)" % (best, at, slack)
    if best > slack:
        return OracleOutcome("mismatch", "frames", "excess %d > slack %d\n  %s" %
                             (best, slack, detail))
    return OracleOutcome("ok", "frames", detail)


# ---------------------------------------------------------- param_erasure --
#
# (round 359) The v0.19 parameter-contract oracle — round 347 §7's named gap,
# carried as the largest open SWE-loop(D) item by round 353.
#
# v0.19 (round 344) moved a `p: Type` parameter annotation OFF the body and
# ONTO the FnDef/FnExpr node (`param_types`), where `interp._closure_params`
# resolves it once, in the DEFINING env, at closure creation — the same
# moment and the same code a `-> Type` return annotation has used since
# v0.13. v0.12-v0.18 instead erased the annotation, in the parser, into one
# `let <p> = typed(<p>, <spec>, "parameter '<p>' of <f>")` statement
# PREPENDED to the body.
#
# `_check_params`'s own docstring states the claim this oracle tests:
#
#     Two deliberate properties, both inherited from the v0.12 guards this
#     replaces rather than newly chosen, so that moving the check does not
#     also change what it means
#
# So: erase the contracts back into v0.12's form and require the same
# answer. The transform runs on the AST rather than on source text, and it
# is not an approximation of what v0.12 did — it is a transcription of
# `Parser._apply_type_guards` as of `6132f1f^`, down to building every guard
# node at `body.line` (which is why a parameter miss keeps being reported at
# the line the contract is WRITTEN on, in both forms).
#
# Doing it post-parse is faithful for the same reason v0.12 could do it in
# the parser: `_apply_type_guards` ran AFTER `block()` had finished the body
# and BEFORE `mark_tails(body)`, so every parse-time fact the body carries
# (`tail_alias_tag`, `tail_param_name`, the alias/effect scopes, the
# duplicate-binding check) was resolved on the UNGUARDED body in v0.12
# exactly as it is in v0.19. And `mark_tails` needs no re-run: `block()`
# requires a body to end in an expression statement, so prepending can never
# change which statement is the tail.
#
# Comparison fields: `out`, `checks`, `vals` — never `why`. A `let`
# statement wraps its value in a fresh `("let", name, line)` Prov node
# (`_stmt_gen`), so the v0.12 form necessarily carries one extra provenance
# layer per annotated parameter, while a SATISFIED v0.19 contract leaves no
# node at all. That is a known, intended difference, not a finding. Programs
# that compute WITH provenance are handled by the same `provenance_tainted_
# names` fixpoint the tail oracle uses, for the same reason: `len(steps(x))`
# is an ordinary number in `vals`.
#
# Two exemptions, both about the one thing the two forms genuinely disagree
# on — WHEN and WHERE a spec name is looked up:
#
#   * a spec NAME bound more than once anywhere in the program. v0.12 walks
#     an ordinary `A.NameRef` in the CALL env on every call; v0.19 resolves
#     it in the DEFINING env once. With a single binding those are the same
#     value (Whence is lexically scoped and the parser refuses a forward
#     annotation reference), so only a second binding can separate them —
#     and when it does, the divergence IS v0.19, round 342 §7's late-binding
#     capture hazard. Round 347 named this one in advance.
#   * `typed` bound by the program. The erased form calls the builtin by
#     NAME from inside the body, so a program that binds `typed` reaches its
#     own value instead; v0.19 never goes through a name at all. Round 347
#     did not name this one — see round 359's knowledge file.
#
# Both are deliberately coarse (any binding of the name ANYWHERE, including
# a parameter), on the tail oracle's rule: over-exempting costs coverage,
# under-exempting costs correctness.

PARAM_ORACLE = "param_erasure"

# The builtin the erased form reaches by name from inside the function body.
GUARD_BUILTIN = "typed"


def _ast_mod(pkg):
    return __import__(pkg["name"] + ".ast_nodes", fromlist=["Let"])


def has_param_contracts(pkg):
    """Whether the package under test carries v0.19 parameter contracts on
    the AST node. A pre-v0.19 package erased them in the parser, so there is
    nothing left on the node to erase and the oracle has no transform to
    apply — the same shape `has_direct_mode` gives `oracle_direct`."""
    try:
        A = _ast_mod(pkg)
    except ImportError:
        return False
    return "param_types" in getattr(A.FnDef, "__slots__", ())


def erase_param_contracts(pkg, program):
    """Rewrite v0.19 parameter contracts into v0.12's prepended guards, in
    place; return the number of guards written.

    The spec EXPRESSION is reused rather than rebuilt. `_param_contracts`
    already built it with `body.line` (`line = body.line` in its own body),
    which is the line `_apply_type_guards` gave it, so a fresh copy would be
    the same node with a different id — and reusing it keeps the oracle from
    quietly depending on a second, drifting copy of `_type_spec_expr`.
    """
    A = _ast_mod(pkg)
    n = 0
    for node in list(iter_ast_nodes(program)):
        contracts = getattr(node, "param_types", None)
        if not contracts:
            continue
        body = node.body
        line = body.line
        guards = []
        for _index, pname, spec_expr, label in contracts:
            call = A.Call(line, A.NameRef(line, GUARD_BUILTIN),
                          [A.NameRef(line, pname), spec_expr,
                           A.Str(line, label)], False)
            guards.append(A.Let(line, pname, call))
        body.stmts[0:0] = guards
        node.param_types = None
        n += len(guards)
    return n


def binding_counts(program):
    """How many times each name is BOUND anywhere in the program: `let` and
    `fn` names (a `shape` declaration reaches the AST as an ordinary
    `A.Let`, which is the whole point of decision 27) plus every function
    parameter. Multiplicity is what matters — a name bound twice is a name
    whose meaning can depend on WHEN it is looked up."""
    counts = {}
    for n in iter_ast_nodes(program):
        cls = type(n).__name__
        if cls in ("Let", "FnDef"):
            counts[n.name] = counts.get(n.name, 0) + 1
        if cls in ("FnDef", "FnExpr"):
            for p in n.params:
                counts[p] = counts.get(p, 0) + 1
    return counts


def param_spec_names(program):
    """Shape names used as a PARAMETER annotation's spec. A primitive tag is
    an `A.Str` and cannot be shadowed, so it is not collected."""
    names = set()
    for n in iter_ast_nodes(program):
        for entry in getattr(n, "param_types", None) or ():
            spec = entry[2]
            if type(spec).__name__ == "NameRef":
                names.add(spec.name)
    return names


def erasure_exemption(program):
    """Why the two forms are ALLOWED to disagree on this program, or "".

    Checked on the ORIGINAL (un-erased) AST, because `erase_param_contracts`
    clears `param_types` as it goes."""
    counts = binding_counts(program)
    if counts.get(GUARD_BUILTIN):
        return "the program binds %r, which the erased form calls by name" % \
            GUARD_BUILTIN
    for name in sorted(param_spec_names(program)):
        if counts.get(name, 0) > 1:
            return "spec name %r is bound %d times (defining env vs call " \
                "env: round 342 §7)" % (name, counts[name])
    return ""


def oracle_param_erasure(pkg, src, max_depth=500):
    """A parameter contract must mean what the v0.12 guard it replaced
    meant.

    An exempt program is still RUN, and `detail` says whether it actually
    used its exemption ("exempt, used" / "exempt, unused") and, when it did,
    what the divergence was. Round 347 designed the exemption around ONE
    mechanism (defining env vs call env); on this corpus the exempt programs
    diverge for a DIFFERENT one, and an exemption that returns early can
    never tell you that. Same convention as `oracle_frames`, whose detail
    carries the measured excess whether or not it exceeded the slack: a
    campaign reports the distribution instead of hiding it.
    """
    if not has_param_contracts(pkg):
        return OracleOutcome("ok", PARAM_ORACLE,
                             "package has no parameter contracts on the AST")
    try:
        program = _parse(pkg, src)
        erased = _parse(pkg, src)          # a second, independent AST
    except (pkg["LexError"], pkg["ParseError"]) as e:
        return OracleOutcome("parse_error", PARAM_ORACLE, type(e).__name__)
    exemption = erasure_exemption(program)
    n = erase_param_contracts(pkg, erased)
    if n == 0:
        return OracleOutcome("ok", PARAM_ORACLE, "no parameter contracts")
    tainted = provenance_tainted_names(program)
    whole = not reflects_on_provenance(program)
    scope = "all fields" if whole else \
        "untainted vals only (%d tainted)" % len(tainted)
    detail = "%d contracts, %s" % (n, scope)
    if not exemption:
        a, _ = _answer(pkg, program, tainted, whole, max_depth=max_depth)
        try:
            b, _peak = _answer(pkg, erased, tainted, whole, max_depth=max_depth)
        except RecursionError:
            return OracleOutcome("ok", PARAM_ORACLE,
                                 "%d contracts, erased run exhausted the host "
                                 "stack (space-exempt)" % n)
        if not a["vals"] and not whole:
            return OracleOutcome("ok", PARAM_ORACLE,
                                 "%d contracts, every binding provenance-"
                                 "tainted (exempt)" % n)
        d = first_difference(a, b)
        if d:
            return OracleOutcome("mismatch", PARAM_ORACLE,
                                 "v0.19 vs erased v0.12: " + d +
                                 "\n  (%s)" % detail)
        return OracleOutcome("ok", PARAM_ORACLE, detail)
    # Exempt: allowed to differ, measured anyway. Every failure mode of the
    # comparison itself is folded into the detail — an exempt program has
    # already told us its answer may be anything, so a crash in one of the
    # two forms is an observation, not a finding. `_Timeout` is a
    # BaseException on purpose (killers._Timeout) and so still escapes to
    # `run_oracle`'s own budget.
    try:
        a, _ = _answer(pkg, program, tainted, whole, max_depth=max_depth)
        b, _peak = _answer(pkg, erased, tainted, whole, max_depth=max_depth)
    except (Exception, RecursionError) as e:      # noqa: B014 (explicit)
        return OracleOutcome("ok", PARAM_ORACLE,
                             "%s, exempt (%s); comparison raised %s" %
                             (detail, exemption, type(e).__name__))
    d = first_difference(a, b)
    if d:
        return OracleOutcome("ok", PARAM_ORACLE,
                             "%s, exempt, used (%s)\n  %s" %
                             (detail, exemption, d.replace("\n", "\n  ")))
    return OracleOutcome("ok", PARAM_ORACLE,
                         "%s, exempt, unused (%s)" % (detail, exemption))


ORACLES = {"totality": oracle_totality, "fast_slow": oracle_fast_slow,
           "direct": oracle_direct, "determinism": oracle_determinism,
           "render": oracle_render, "frames": oracle_frames,
           TAIL_ORACLE: oracle_tail_transparency,
           PARAM_ORACLE: oracle_param_erasure}


def run_oracle(name, pkg, src, timeout_s=3.0, max_depth=500, root=WHENCE_ROOT, **kwargs):
    """Run one oracle under a wall-clock budget; crashes become outcomes.

    Round 289: `**kwargs` forwards oracle-specific keyword args (e.g.
    guest.py's `oracle_self_eval(..., harness=..., why_probe=...)`) through
    to `fn`. Before this, any caller that needed one of those — most
    concretely, a shared `GuestHarness` reused across several programs in a
    loop, to avoid re-parsing the ~800-line self_eval.lang library each time
    — had no way to reach it through `run_oracle` and was structurally
    forced to call the oracle function directly instead, silently losing
    the SIGALRM timeout below. Round 185's own round did exactly that (a
    one-off `python3 -c` exploring `GUEST_ORACLE` mismatches with a shared
    `harness=h`, calling `G.oracle_self_eval(pkg, src, harness=h)` bare) and
    hung for 2912s on a self-recursive guest program (`fn f6() { let t7 =
    f6() ... }`, no base case) — consuming nearly the entire round budget
    on one Bash call with no `timeout` param set, confirmed reproducible by
    round 289 with a 6s bash `timeout` wrapper (exit 124, never returned).
    Reproduced in a controlled way in
    `test_run_oracle_kwargs_bounds_a_shared_harness_hang`."""
    fn = ORACLES[name]
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    t0 = time.time()
    try:
        o = fn(pkg, src, max_depth=max_depth, **kwargs)
    except _Timeout:
        o = OracleOutcome("timeout", name, "exceeded %.1fs" % timeout_s)
    except RecursionError as e:
        o = OracleOutcome("crash", name, str(e)[:200], "RecursionError",
                          _whence_frames(e.__traceback__, root))
    except Exception as e:  # noqa: BLE001 — the oracle: any escape is a bug
        o = OracleOutcome("crash", name, str(e)[:200], type(e).__name__,
                          _whence_frames(e.__traceback__, root))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)
    o.seconds = time.time() - t0
    return o


# --------------------------------------------------------------- campaign --

class Finding(object):
    def __init__(self, sig, seed, src, outcome, minimized=None):
        self.sig = sig
        self.seed = seed
        self.src = src
        self.outcome = outcome
        self.minimized = minimized

    def as_dict(self):
        return {"signature": list(self.sig), "seed": self.seed, "src": self.src,
                "outcome": self.outcome.as_dict(), "minimized": self.minimized}


class OracleCampaign(object):
    def __init__(self, oracles):
        self.oracles = tuple(oracles)
        self.counts = {}          # (oracle, kind) -> n
        self.findings = {}        # sig -> Finding
        self.programs = 0
        self.seconds = 0.0

    def summary(self):
        lines = ["oracle fuzz: %d programs x %d oracles in %.1fs"
                 % (self.programs, len(self.oracles), self.seconds)]
        for name in self.oracles:
            parts = ["%s %d" % (k, self.counts.get((name, k), 0))
                     for k in ("ok", "mismatch", "crash", "parse_error", "timeout")
                     if self.counts.get((name, k))]
            lines.append("  %-12s %s" % (name, "  ".join(parts)))
        lines.append("  unique finding signatures: %d" % len(self.findings))
        for sig, f in sorted(self.findings.items()):
            lines.append("  - %s  (seed %d, %d lines%s)" % (
                " | ".join(sig), f.seed, f.src.count("\n"),
                ", minimized to %d" % f.minimized.count("\n") if f.minimized else ""))
        return "\n".join(lines)

    def as_dict(self):
        return {"programs": self.programs, "seconds": round(self.seconds, 2),
                "oracles": list(self.oracles),
                "counts": dict(("%s/%s" % k, v) for k, v in self.counts.items()),
                "findings": [f.as_dict() for f in self.findings.values()]}


def fuzz_oracles(seed=0, n=200, oracles=ORACLE_NAMES, root=WHENCE_ROOT, timeout_s=3.0,
                 max_depth=500, stress_rate=0.5, do_shrink=True, on_program=None,
                 extra_programs=()):
    """Run every oracle over `n` generated programs (+ `extra_programs`,
    e.g. the checked-in examples); shrink one reproducer per signature."""
    pkg = load_whence(root, "oracle")
    camp = OracleCampaign(oracles)
    t0 = time.time()
    programs = [(-1 - i, src) for i, src in enumerate(extra_programs)]
    programs += [(seed * 1000003 + i, None) for i in range(n)]
    for s, src in programs:
        if src is None:
            src = ProgramGen(s, stress_rate=stress_rate).program()
        camp.programs += 1
        for name in oracles:
            o = run_oracle(name, pkg, src, timeout_s=timeout_s, max_depth=max_depth, root=root)
            camp.counts[(name, o.kind)] = camp.counts.get((name, o.kind), 0) + 1
            if on_program:
                on_program(s, src, o)
            sig = signature(o)
            if o.kind in ("crash", "mismatch") and sig not in camp.findings:
                f = Finding(sig, s, src, o)
                if do_shrink:
                    def keep(cand, sig=sig, name=name):
                        return signature(run_oracle(name, pkg, cand, timeout_s=timeout_s,
                                                    max_depth=max_depth, root=root)) == sig
                    f.minimized = shrink(src, keep)
                camp.findings[sig] = f
    camp.seconds = time.time() - t0
    return camp


def example_programs(root=WHENCE_ROOT, skip=("deep.lang", "meta.lang")):
    """The checked-in examples (the slow ones skipped) as extra corpus."""
    ex_dir = os.path.join(root, "examples")
    out = []
    for name in list_example_files(root):
        if name not in skip:
            with open(os.path.join(ex_dir, name), encoding="utf-8") as f:
                out.append(f.read())
    return out


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("-n", type=int, default=200)
    ap.add_argument("--oracle", default="all", help="comma list or 'all'")
    ap.add_argument("--no-shrink", action="store_true")
    ap.add_argument("--no-examples", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--limit", type=int, default=0,
                    help="host recursion limit for the run (the CLI uses 6000; "
                         "the frames oracle's excess on an undercount scales "
                         "with it, a legitimate transient does not)")
    a = ap.parse_args()
    if a.limit:
        sys.setrecursionlimit(a.limit)
    names = ORACLE_NAMES if a.oracle == "all" else tuple(a.oracle.split(","))
    c = fuzz_oracles(a.seed, a.n, names, do_shrink=not a.no_shrink,
                     extra_programs=() if a.no_examples else example_programs())
    print(c.summary())
    if a.show:
        for sig, f in c.findings.items():
            print("\n### %s\n%s\n--- detail:\n%s" % (" | ".join(sig), f.minimized or f.src,
                                                  f.outcome.detail))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(c.as_dict(), fh, indent=1)

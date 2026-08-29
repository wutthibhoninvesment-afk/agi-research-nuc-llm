"""Trampolined evaluator for Whence.

Invariants:
  - eval_* never raises for user-level problems: every runtime error becomes a
    propagating `miss` value carrying reason strings and provenance.
  - Every derived value gets a provenance node linking to its inputs — and
    since v0.4 the value *is* that node (see values.py).
  - Element/field access passes provenance through unchanged (access does not
    launder history).

Execution model (round 4): evaluation does not use the Python call stack for
language-level nesting. Each compound eval_* method is a generator that
*requests* sub-evaluations by yielding one of:

    (node, env)            evaluate `node` in `env`
    _Call(fn, args, line)  call a Whence value
    <generator>            run this generator (statements, builtin bodies)

and receives the resulting value back from `send`. `_drive` runs an explicit
stack of generators, so language recursion depth is bounded by `max_depth`
(a tunable that produces a miss) rather than by CPython's recursion limit.

Fast path (round 9): a subtree that contains no `Call` node can never recurse
into Whence code, so it is compiled once into a tree of plain Python closures
(`compile_fast`) and evaluated inline — no generator, no trampoline round
trip. Host-stack use is bounded by the source nesting depth, which the
recursive-descent parser already bounded more tightly. Both paths share the
same helper functions (`binop`, `_unary`, `_index`, …) so there is exactly
one definition of every operator's semantics; `Interpreter(fast=False)`
disables the fast path for differential testing.

Direct mode (round 30, v0.9): the trampoline exists so that Whence recursion
never depends on the host stack — but it charges every non-tail call three
generators and ~8 sends. Direct mode compiles subtrees WITH calls to
closures too (`compile_direct`); a call to a closure whose body compiled
runs through `_call_direct`, plain host recursion, under a FRAME BUDGET
(`_hleft`) derived from the live recursion limit minus the stack already
in use minus a reserve. Every direct entry charges the host frames it can
use (`node.cdepth`, exact by construction), and an exhausted budget falls
back to the trampoline — so the first few hundred guest levels run without
generators and deeper ones run exactly as before. Semantics are the
trampoline's: `_call_direct` shares the tail-loop bookkeeping with
`_call_gen`, and `Interpreter(direct=False)` is the differential oracle.
"""

import gc
import inspect
import math
import random
import sys
from types import GeneratorType

from . import ast_nodes as A
from .parser import parse
from .values import (
    Value, Prov, MergedProv, Miss, Guess, Record, Closure, Builtin,
    Explanation,
    _slot,
    WList, wlist,
    show_payload, full_show, leaf, derived, mk_miss, merge_miss, render_why,
    render_contrast, is_origin_miss, walk_steps, find_step, matches_step,
    diverge, _LAZY,
)
import operator
import re

# numeric binary operators (both operands int/float, never bool): the hot
# path of `binop`; `/` and `%` still check for a zero divisor first
# num(): optional sign, ASCII digits, optional fraction, optional exponent
_NUM_RE = re.compile(r"^([+-]?[0-9]+)(\.[0-9]+)?([eE][+-]?[0-9]+)?$")
_INF = float("inf")

_NUM_OPS = {
    "+": operator.add, "-": operator.sub, "*": operator.mul,
    "/": operator.truediv, "%": operator.mod,
    "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge,
    "==": operator.eq, "!=": operator.ne,
}

# the operators that are defined on two strings (comparison only; concat is
# special-cased): str % str would FORMAT under the host, str * str would raise
_STR_OPS = {
    "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge,
    "==": operator.eq, "!=": operator.ne,
}


class Env(object):
    # `interp` is set only on an Interpreter's globals env (the root of every
    # chain it evaluates in). Compiled closures cached on SHARED AST nodes
    # use it to find the interpreter that is acting NOW, instead of the one
    # that happened to compile the node (v0.7 determinism fix).
    __slots__ = ("vars", "parent", "interp")

    def __init__(self, parent=None, interp=None):
        self.vars = {}
        self.parent = parent
        self.interp = interp

    def get(self, name):
        env = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        return None

    def define(self, name, value):
        self.vars[name] = value


class _Call(object):
    """A request, yielded by a generator, to call `fn` with `args`."""
    __slots__ = ("fn", "args", "line")

    def __init__(self, fn, args, line):
        self.fn = fn
        self.args = args
        self.line = line


class _TailCall(object):
    """The *result* of evaluating a call in tail position of a function body
    (v0.3): instead of calling, the body hands the pending call back to the
    enclosing `_call_gen`, which re-enters the loop in the same frame. `ifs`
    collects `(line, which, cond)` for every `if` the tail call passed
    through on the way out (innermost first) so no branch decision is lost;
    `_call_gen` run-length-merges them into `if … ×N` nodes (v0.4)."""
    __slots__ = ("fn", "args", "line", "ifs")

    def __init__(self, fn, args, line):
        self.fn = fn
        self.args = args
        self.line = line
        self.ifs = []


def _is_miss(v):
    return isinstance(v.value, Miss)


def _is_num(p):
    return isinstance(p, (int, float)) and not isinstance(p, bool)


def _stack_depth():
    """Number of host frames currently on the stack (v0.9): the part of
    `sys.getrecursionlimit()` that is already spent when Whence starts."""
    n = 0
    f = sys._getframe()
    while f is not None:
        n += 1
        f = f.f_back
    return n


# --- operator semantics shared by the generator path and the fast path ------

def _unary(op, v, line):
    if isinstance(v.value, Miss):
        return merge_miss(op, "", line, (v,))
    if isinstance(v.value, Guess):
        g = v.value
        result = _unary(op, g.node, line)
        if isinstance(result.value, Miss):
            return result       # a genuine type error is not uncertain
        return Prov(op, "guess", line, _slot((v,)), _LAZY,
                   Guess(result, g.confidence, g.sources))
    if op == "-":
        if _is_num(v.value):
            return derived("-", "negate", line, (v,), -v.value)
        return mk_miss("cannot negate %s" % show_payload(v.value), line, "-",
                       inputs=(v,))
    if op == "not":
        if isinstance(v.value, bool):
            return derived("not", "", line, (v,), not v.value)
        return mk_miss("'not' needs true/false, got %s" %
                       show_payload(v.value), line, "not", inputs=(v,))
    raise AssertionError("unknown unary %r" % op)


def _logic_left(op, left, line):
    """`and`/`or` after the left operand: a decided value, or None if the
    right operand is needed."""
    if isinstance(left.value, Miss):
        return merge_miss(op, "", line, (left,))
    if not isinstance(left.value, bool):
        return mk_miss("'%s' needs true/false, got %s" %
                       (op, show_payload(left.value)), line, op, inputs=(left,))
    if op == "and" and left.value is False:
        return derived(op, "short-circuit", line, (left,), False)
    if op == "or" and left.value is True:
        return derived(op, "short-circuit", line, (left,), True)
    return None


def _logic_right(op, left, right, line):
    if isinstance(right.value, Miss):
        return merge_miss(op, "", line, (right, left))
    if not isinstance(right.value, bool):
        return mk_miss("'%s' needs true/false, got %s" %
                       (op, show_payload(right.value)), line, op,
                       inputs=(right, left))
    return derived(op, "", line, (left, right), right.value)


def _if_bad(cond, line):
    """A miss if `cond` cannot decide an `if`, else None."""
    if isinstance(cond.value, Miss):
        return merge_miss("if", "condition was miss", line, (cond,))
    if not isinstance(cond.value, bool):
        return mk_miss("if condition must be true/false, got %s" %
                       show_payload(cond.value), line, "if", inputs=(cond,))
    return None


def _miss_lit(reason, line):
    if isinstance(reason.value, Miss):
        return merge_miss("miss", "", line, (reason,))
    if not isinstance(reason.value, str):
        return mk_miss("miss reason must be a string, got %s" %
                       show_payload(reason.value), line, "miss")
    m = Miss(["%s (line %d)" % (reason.value, line)])
    return Prov("miss", reason.value, line, (reason,), "miss", m)


def _index(obj, idx, line):
    if isinstance(obj.value, Miss) or isinstance(idx.value, Miss):
        return merge_miss("index", "", line, (obj, idx))
    o, i = obj.value, idx.value
    if isinstance(o, WList):
        if not isinstance(i, int) or isinstance(i, bool):
            return mk_miss("list index must be an integer, got %s" %
                           show_payload(i), line, "index", inputs=(obj, idx))
        if i < 0 or i >= len(o):
            return mk_miss("index %d out of range (len %d)" % (i, len(o)),
                           line, "index", inputs=(obj, idx))
        return o[i]  # provenance passes through unchanged
    if isinstance(o, str):
        if not isinstance(i, int) or isinstance(i, bool):
            return mk_miss("string index must be an integer, got %s" %
                           show_payload(i), line, "index", inputs=(obj, idx))
        if i < 0 or i >= len(o):
            return mk_miss("index %d out of range (len %d)" % (i, len(o)),
                           line, "index", inputs=(obj, idx))
        return derived("index", "[%d]" % i, line, (obj, idx), o[i])
    return mk_miss("cannot index %s" % show_payload(o), line, "index",
                   inputs=(obj, idx))


def _field(obj, name, line):
    if isinstance(obj.value, Miss):
        return merge_miss("field", "." + name, line, (obj,))
    if not isinstance(obj.value, Record):
        return mk_miss("cannot access .%s on %s" %
                       (name, show_payload(obj.value)), line, "field",
                       inputs=(obj,))
    if name not in obj.value.fields:
        have = ", ".join(sorted(obj.value.fields)) or "(none)"
        return mk_miss("no field '%s' (record has: %s)" % (name, have),
                       line, "field", inputs=(obj,))
    return obj.value.fields[name]  # provenance passes through


def _children(node):
    """Child expression nodes of an AST node (for the compiler's walk).
    Function bodies are not children: they compile when first called."""
    t = node.__class__
    if t is A.Binary or t is A.Rescue:
        return [node.left, node.right]
    if t is A.Unary or t is A.Why or t is A.Snip:
        return [node.operand]
    if t is A.MissLit:
        return [node.reason]
    if t is A.Call:
        return [node.fn] + list(node.args)
    if t is A.If:
        return [node.cond, node.then, node.otherwise]
    if t is A.Block:
        return [s.expr for s in node.stmts if s.__class__ is not A.FnDef]
    if t is A.ListLit:
        return list(node.items)
    if t is A.RecordLit:
        return [e for _, e in node.pairs]
    if t is A.Index:
        return [node.obj, node.index]
    if t is A.FieldAccess:
        return [node.obj]
    return []


def _const(node):
    """The shared value of a literal node (v0.4): one source literal is one
    provenance node however many times it is evaluated."""
    c = node.const
    if c is None:
        c = node.const = leaf("literal", "", node.line, node.value)
    return c


class Interpreter(object):
    # Each Whence call frame costs ~6KB (≈4KB of it is the provenance DAG the
    # result will retain anyway), so 20000 ≈ 125MB worst case for a runaway.
    DEFAULT_MAX_DEPTH = 20000

    # gen-0 threshold used by `run()` when gc_relief is on: a Whence run
    # builds a large, long-lived, (almost) acyclic object graph, and CPython's
    # generational collector otherwise rescans it every 700 allocations —
    # ~50% of the wall time of a long tail loop. Process-global while `run`
    # executes, restored afterwards; off by default for embedders.
    GC_RELIEF_THRESHOLD = 50000

    # v0.9: host frames kept in reserve below the recursion limit while
    # direct mode runs: transient fast-closure recursion (a call-free
    # subtree compiles only up to FAST_MAX_DEPTH levels, one frame each),
    # one trampoline fallback (`_drive` + generator + helpers), rendering
    # (depth-capped). The budget is whatever is left above this.
    # v0.11 (round 110): measured with bench/reserve_probe.py — the
    # smallest reserve that survives, per program, at limit 6000: deep
    # recursions with short bodies need 0–5 (the charge is exact), a
    # 95-term `+` chain in the base case of a non-tail recursion 93–94,
    # 55-deep nesting 57 (the parser caps nesting at 60), a 39-level
    # else-if chain 41; the fuzz corpus and every example ≤ 5. The bound
    # by construction is FAST_MAX_DEPTH + a nested drive ≈ 110; 250 is
    # 2.3× that (was 350 — a guess).
    HOST_RESERVE = 250

    def __init__(self, out=None, max_depth=DEFAULT_MAX_DEPTH, max_iter=None,
                 fast=True, gc_relief=False, direct=True, seed=0):
        self.out_lines = []
        self._out = out if out is not None else self.out_lines.append
        # v0.14.8: `rand()`'s own stream, seeded (default a fixed constant,
        # not OS entropy) so that a fresh Interpreter run of the same source
        # reproduces the same sequence of draws — the three-way differential
        # (direct/fast/slow, each a SEPARATE Interpreter instance) and the
        # guest/host campaigns both depend on full determinism across
        # independent runs of one program; see SPEC.md "v0.14.8".
        self._rng = random.Random(seed)
        self.checks = []   # dicts: label, line, ok, note, why (why only on fail)
        self.globals = Env()
        self.depth = 0            # current Whence call depth
        self.max_depth = max_depth
        self.max_iter = max_iter  # cap on frames merged by one tail loop
        self.peak_depth = 0       # deepest call depth reached (for reporting)
        self.tail_calls = 0       # frames elided by tail calls (for reporting)
        self.fast = fast          # compile call-free subtrees to closures
        self.fast_hits = 0        # subtrees evaluated by a compiled closure
        # v0.9: direct mode needs the fast path (direct closures are built
        # from fast ones). `_hleft` is the host-frame budget still
        # available to direct evaluation; -1 keeps every gate closed until
        # a top-level entry (exec_stmt) measures the real headroom.
        self.direct = bool(direct and fast)
        self.direct_hits = 0      # subtrees / calls evaluated directly
        self.direct_fallbacks = 0 # calls sent to the trampoline by the budget
        self._hleft = -1
        self.gc_relief = gc_relief
        # v0.7: every name bound ANYWHERE in ASTs this interpreter has seen
        # (let / fn names / params). A call to a builtin name absent from
        # this set compiles inline (F1); the set is a performance gate only —
        # a runtime identity check inside the compiled call keeps stale
        # entries (incremental exec_stmt callers) correct via call_value.
        self.shadowed = set()
        self.globals.interp = self   # root back-pointer for shared-AST closures
        _install_builtins(self.globals)

    # --- entry points ---------------------------------------------------
    def run(self, source):
        """Parse and execute a program. Returns the top-level Env."""
        program = parse(source)
        env = Env(self.globals)
        old = gc.get_threshold()
        if self.gc_relief:
            gc.set_threshold(max(old[0], self.GC_RELIEF_THRESHOLD), old[1],
                             old[2])
        try:
            for stmt in program.stmts:
                self.exec_stmt(stmt, env)
        finally:
            if self.gc_relief:
                gc.set_threshold(*old)
        return env

    def failed_checks(self):
        return [c for c in self.checks if not c["ok"]]

    def exec_stmt(self, stmt, env):
        self._collect_shadowed(stmt)
        if self.direct:
            # measure the headroom NOW: embedders may call from deep inside
            # their own stacks, and the limit may have changed since the
            # last statement (tests do this) — never trust a cached value
            self._hleft = (sys.getrecursionlimit() - _stack_depth()
                           - self.HOST_RESERVE)
        return self._drive(self._stmt_gen(stmt, env))

    def host_budget(self):
        """Host frames direct mode may use right now (≤0: direct mode is
        dormant and everything runs on the trampoline)."""
        return self._hleft

    def _collect_shadowed(self, root):
        """Record every name this statement binds anywhere (v0.7). Runs
        BEFORE execution, so by the time any call site in earlier code
        compiles lazily, all shadows from statements executed so far are
        known. Compilation is lazy (first evaluation), so within one
        parse unit this is exact; across exec_stmt units the compiled
        call's runtime identity check covers staleness."""
        add = self.shadowed.add
        stack = [root]
        push = stack.append
        while stack:
            n = stack.pop()
            t = n.__class__
            if t is A.Let:
                add(n.name)
                push(n.expr)
            elif t is A.FnDef:
                add(n.name)
                for p in n.params:
                    add(p)
                push(n.body)
            elif t is A.FnExpr:
                for p in n.params:
                    add(p)
                push(n.body)
            elif t is A.Block or t is A.Program:
                stack.extend(n.stmts)
            elif t is A.Check or t is A.ExprStmt:
                push(n.expr)
            else:
                stack.extend(_children(n))

    def eval(self, node, env):
        f = node.fast
        if f is None:
            f = self.compile_fast(node)
        if f:
            self.fast_hits += 1
            return f(env)
        m = self._DISPATCH[type(node).__name__]
        if m in self._LEAF:
            return m(self, node, env)
        return self._drive(m(self, node, env))

    def call_value(self, fn, args, line):
        if self._hleft > 0:
            return self._call_direct(fn, args, line)
        return self._drive(self._call_gen(fn, args, line))

    def _builtin_inline(self, p, args, line):
        """Run a non-generator builtin with no trampoline frame (v0.6)."""
        if not _arity_ok(p.arity, len(args)):
            return mk_miss("%s expects %s args, got %d" %
                           (p.name, _arity_str(p.arity), len(args)),
                           line, "call", p.name, inputs=tuple(args))
        return p.fn(self, args, line)

    # --- the trampoline -------------------------------------------------
    def _drive(self, gen):
        stack = [gen]
        push = stack.append
        pop = stack.pop
        dispatch = self._DISPATCH
        leaves = self._LEAF
        compile_fast = self.compile_fast
        result = None
        # v0.9: a nested drive (budget fallback, generator builtin reached
        # from direct code, call_value) sits on the host stack: the drive
        # frame, the running generator, its helpers. Charge it. `direct`
        # is a local so the per-request gate below costs the trampoline
        # mode (direct=False, the differential oracle) one LOAD_FAST.
        self._hleft -= 3
        direct = self.direct
        while stack:
            try:
                req = stack[-1].send(result)
            except StopIteration as done:
                pop()
                result = done.value
                continue
            if type(req) is tuple:
                node, env = req
                if node.__class__ is A.Block and len(node.stmts) == 1:
                    node = node.stmts[0].expr   # no bindings: no inner Env
                f = node.fast
                if f is None:
                    f = compile_fast(node)
                if f:
                    self.fast_hits += 1
                    result = f(env)
                    continue
                # v0.9: a subtree WITH calls runs as a direct closure when
                # the frame budget covers the frames it needs to reach its
                # deepest call (`cdepth`; every call it makes charges its
                # own body separately in `_call_direct`)
                if direct and self._hleft > 0:
                    hleft = self._hleft
                    d = node.direct
                    if d is None:
                        d = self.compile_direct(node)
                    if d and hleft >= node.cdepth:
                        cost = node.cdepth
                        self._hleft = hleft - cost
                        self.fast_hits += 1     # a direct closure is compiled too
                        self.direct_hits += 1
                        result = d(env)
                        self._hleft += cost
                        continue
                cls = node.__class__
                if cls is A.Call:
                    # a call whose callee and arguments are all fast needs
                    # no eval_Call generator (v0.6; tail case since v0.4):
                    # evaluate the parts inline, then either hand the tail
                    # call back, run a plain builtin right here, or push
                    # only the _call_gen frame.
                    c = node.const
                    if c is None:
                        f = compile_fast(node.fn)
                        fs = [compile_fast(a) for a in node.args]
                        c = node.const = (f, tuple(fs)) if f and all(fs) \
                            else False
                    if c:
                        f, fs = c
                        self.fast_hits += 1
                        fn = f(env)
                        args = [g(env) for g in fs]
                        if node.tail:
                            result = _TailCall(fn, args, node.line)
                            continue
                        p = fn.value
                        if type(p) is Builtin and not p.is_gen:
                            result = self._builtin_inline(p, args, node.line)
                            continue
                        if type(p) is Closure:
                            r = self._closure_inline(p, args, node.line)
                            if r is not None:
                                result = r
                                continue
                        push(self._call_gen(fn, args, node.line))
                        result = None
                        continue
                elif cls is A.If:
                    # `if` with a fast condition: decide inline; the taken
                    # branch is evaluated inline too when it is fast or an
                    # inline-able tail call, else by eval_If (given the
                    # already-evaluated condition, so nothing runs twice)
                    cf = node.cond.fast
                    if cf is None:
                        cf = compile_fast(node.cond)
                    if cf:
                        self.fast_hits += 1
                        cond = cf(env)
                        r = self._if_inline(node, env, cond)
                        if r is None:
                            push(self.eval_If(node, env, cond))
                            result = None
                        elif type(r) is GeneratorType:
                            # a walked chain whose innermost branch needs
                            # the trampoline (v0.8, F3)
                            push(r)
                            result = None
                        else:
                            result = r
                        continue
                m = dispatch[cls.__name__]
                if m in leaves:
                    result = m(self, node, env)
                    continue
                push(m(self, node, env))
            elif type(req) is _Call:
                if direct and self._hleft > 0:
                    result = self._call_direct(req.fn, req.args, req.line)
                    continue
                p = req.fn.value
                if type(p) is Builtin and not p.is_gen:
                    result = self._builtin_inline(p, req.args, req.line)
                    continue
                if type(p) is Closure:
                    r = self._closure_inline(p, req.args, req.line)
                    if r is not None:
                        result = r
                        continue
                push(self._call_gen(req.fn, req.args, req.line))
            else:
                push(req)
            result = None
        self._hleft += 3
        return result

    # --- direct mode (v0.9): host recursion under a frame budget ---------
    def _call_direct(self, fn, args, line):
        """Call `fn` with `args` by host recursion — the trampoline's
        `_call_gen`, minus the generator. Byte-identical misses (callee
        miss, not callable, arity, depth, tail loop too long), the same
        `arg` / `call` / merged `call f ×N` / `if ×N` nodes (the tail-loop
        bookkeeping is shared: `_merge_ifs`, `_finish_call`), the same
        `depth` / `peak_depth` / `tail_calls` accounting.

        Budget: the frame charged is 1 (this frame) + the body's `cdepth`
        (the direct frames from the body's root to its deepest call). A
        body that does not fit — or cannot compile (too tall) — runs on the
        trampoline through a nested `_drive`, whose own generator-mode calls
        never touch the host stack: host depth is bounded by the budget
        measured at `exec_stmt`, whatever the program does.

        v0.11: the body's `(bd, cost)` pair is cached on the body node
        (`entry`, `_body_entry`); one- and two-parameter bindings are
        unrolled (no `zip` iterator); `depth` and `_hleft` are read once
        and stored back, not read-modify-written. Measured bound for all
        of this together: 1.14× on fib20 with EVERYTHING ablated."""
        p = fn.value
        tp = type(p)
        if tp is not Closure:
            if tp is Miss:
                return merge_miss("call", "", line, [fn] + args)
            if tp is Builtin:
                if not _arity_ok(p.arity, len(args)):
                    return mk_miss("%s expects %s args, got %d" %
                                   (p.name, _arity_str(p.arity), len(args)),
                                   line, "call", p.name, inputs=tuple(args))
                r = p.fn(self, args, line)
                if p.is_gen:
                    r = self._drive(r)
                return r
            return mk_miss("%s is not callable" % show_payload(p), line,
                           "call", inputs=(fn,))
        params = p.params
        # v0.13: captured from the ORIGINALLY called closure, before a tail
        # loop below may reassign `p` — see _call_gen's identical comment.
        ret_spec, ret_label = p.ret_spec, p.ret_label
        nargs = len(args)
        if nargs != len(params):
            name = p.name or "<fn>"
            return mk_miss("%s expects %d args, got %d" %
                           (name, len(params), nargs),
                           line, "call", name, inputs=tuple(args))
        depth = self.depth
        if depth >= self.max_depth:
            name = p.name or "<fn>"
            return mk_miss("recursion too deep in %s (depth %d)" %
                           (name, depth), line, "call", name,
                           inputs=tuple(args))
        body = p.body
        ent = body.entry
        if ent is None:
            ent = self._body_entry(body)
        bd, cost = ent
        hleft = self._hleft
        if not bd or hleft < cost:
            self.direct_fallbacks += 1
            return self._drive(self._call_gen(fn, args, line))
        self._hleft = hleft - cost
        self.direct_hits += 1
        depth += 1
        self.depth = depth
        if depth > self.peak_depth:
            self.peak_depth = depth
        name = p.name or "<fn>"
        names = None
        merged = 1
        runs = None
        # v0.13/round 335/336: the `-> Type` contracts of the closures
        # this tail loop enters below, checked innermost-first BEFORE
        # `ret_spec`'s own — see `_check_chain_rets`. None until a TYPED
        # closure is actually entered.
        chain_rets = None
        call_line = line
        try:
            while True:
                call_env = Env(p.env, self)
                vs = call_env.vars
                if nargs == 1:
                    arg = args[0]
                    pn = params[0]
                    vs[pn] = Prov("arg", pn, call_line, arg, _LAZY, arg.value)
                elif nargs == 2:
                    arg = args[0]
                    pn = params[0]
                    vs[pn] = Prov("arg", pn, call_line, arg, _LAZY, arg.value)
                    arg = args[1]
                    pn = params[1]
                    vs[pn] = Prov("arg", pn, call_line, arg, _LAZY, arg.value)
                else:
                    for pn, arg in zip(params, args):
                        vs[pn] = Prov("arg", pn, call_line, arg, _LAZY,
                                      arg.value)
                result = bd(call_env)
                if type(result) is not _TailCall:
                    break
                tc = result
                fn2, args, call_line = tc.fn, tc.args, tc.line
                if _is_miss(fn2) or not isinstance(fn2.value, Closure):
                    # see _call_gen: ordinary call, this iteration's `if`s
                    # wrap its result, loop over
                    result = _wrap_ifs(self._call_direct(fn2, args, call_line),
                                       tc.ifs)
                    break
                if runs is None:
                    names = [name]
                    runs = []
                _merge_ifs(runs, tc.ifs)
                p = fn2.value
                chain_rets = _note_chain_ret(chain_rets, p, call_line)
                params = p.params
                nargs = len(args)
                name2 = p.name or "<fn>"
                if nargs != len(params):
                    result = mk_miss(
                        "%s expects %d args, got %d" %
                        (name2, len(params), nargs), call_line,
                        "call", name2, inputs=tuple(args))
                    break
                if self.max_iter is not None and merged >= self.max_iter:
                    result = mk_miss(
                        "tail loop too long in %s (%d iterations)" %
                        (name2, merged), call_line, "call", name2,
                        inputs=tuple(args))
                    break
                merged += 1
                self.tail_calls += 1
                if name2 not in names:
                    names.append(name2)
                # mutual recursion may switch to a body that needs more
                # frames than was charged: charge the difference if it
                # fits, else run THAT body on the trampoline (a _TailCall
                # it returns continues this loop)
                nb = p.body
                if nb is not body:
                    body = nb
                    ent = nb.entry
                    if ent is None:
                        ent = self._body_entry(nb)
                    bd, ncost = ent
                    if bd:
                        extra = ncost - cost
                        if extra > 0:
                            if self._hleft >= extra:
                                self._hleft -= extra
                                cost += extra
                            else:
                                bd = False
                    if not bd:
                        self.direct_fallbacks += 1
                        bd = self._trampoline_body(nb)
        finally:
            self.depth = depth - 1
            self._hleft = hleft
        # round 336: inside-out — the chain's contracts (innermost first,
        # each at its own tail-call line), THEN the originally-called
        # closure's own, exactly as the same program behaves with every
        # call lifted out of tail position. See `_check_chain_rets`.
        if chain_rets is not None:
            result = _check_chain_rets(result, chain_rets)
        result = _check_ret(result, ret_spec, ret_label, line)
        if runs is None:      # the common case: one frame, nothing deferred
            return Prov("call", name, line, result, _LAZY, result.value)
        return _finish_call(name, line, result, runs, names, merged)

    def _body_entry(self, body):
        """`(bd, cost)` for calling a function body directly (v0.11), cached
        on the body node: `bd` is its fast closure (cost 1: this call's
        frame) or its direct closure (cost `cdepth` + 1), or False when
        the body cannot compile (too tall) — then every direct call of it
        falls back to the trampoline. Compilation results are stable, so
        the pair is computed once per body per process; `direct=False`
        interpreters never read it (they never reach `_call_direct`)."""
        bd = body.fast
        if bd is None:
            bd = self.compile_fast(body)
        if bd:
            cost = 1
        else:
            bd = body.direct
            if bd is None:
                bd = self.compile_direct(body)
            cost = body.cdepth + 1
        ent = body.entry = (bd, cost)
        return ent

    def _trampoline_body(self, node):
        """A body evaluator with the direct-closure signature that runs the
        body on the trampoline (budget exhausted mid tail loop)."""
        ev = self.eval
        return lambda env: ev(node, env)

    def _closure_inline(self, p, args, line):
        """Run a NON-TAIL closure call with no generator frame when the
        callee's whole body compiled fast (v0.7, F2). A fast body contains
        no guest calls, so it cannot produce a _TailCall and the merged==1
        wrap of _call_gen is the only shape possible. Arity and depth
        misses are byte-identical to _call_gen's. Returns None when the
        body needs the trampoline.

        v0.13 bug fix (round 128): this is a THIRD place a call settles to
        its final result (besides `_call_gen`/`_call_direct`, both fixed in
        round 127) and it was missing the `_check_ret` call entirely — a
        `-> Type` annotation on any call-free-bodied function silently
        never checked, found by the three-way differential (`fast` mode
        disables `_call_direct`, so every such call routes through here)."""
        body = p.body
        bf = body.fast
        if bf is None:
            bf = self.compile_fast(body)
        if not bf:
            return None
        name = p.name or "<fn>"
        if len(args) != len(p.params):
            return mk_miss("%s expects %d args, got %d" %
                           (name, len(p.params), len(args)),
                           line, "call", name, inputs=tuple(args))
        if self.depth >= self.max_depth:
            return mk_miss("recursion too deep in %s (depth %d)" %
                           (name, self.depth), line, "call", name,
                           inputs=tuple(args))
        self.fast_hits += 1
        self.depth += 1
        if self.depth > self.peak_depth:
            self.peak_depth = self.depth
        try:
            call_env = Env(p.env, self)
            vs = call_env.vars
            for pname, arg in zip(p.params, args):
                vs[pname] = Prov("arg", pname, line, arg, _LAZY, arg.value)
            v = bf(call_env)
        finally:
            self.depth -= 1
        v = _check_ret(v, p.ret_spec, p.ret_label, line)
        return Prov("call", name, line, v, _LAZY, v.value)

    def _tail_inline(self, node, env):
        """A `_TailCall` for a tail `Call` node whose callee and arguments
        are all fast, evaluated inline; None if a generator is needed. The
        compiled (callee, args) pair is cached in the node's `const` slot
        (False when some part needs a generator)."""
        c = node.const
        if c is None:
            compile_fast = self.compile_fast
            f = compile_fast(node.fn)
            fs = [compile_fast(a) for a in node.args]
            c = node.const = (f, tuple(fs)) if f and all(fs) else False
        if not c:
            return None
        f, fs = c
        self.fast_hits += 1
        return _TailCall(f(env), [g(env) for g in fs], node.line)

    def _if_inline(self, node, env, cond):
        """Finish an `if` whose condition is already evaluated, without a
        generator, when the taken branch is fast or an inline-able tail
        call. v0.8 (F3): when the taken branch is itself an `if` with a
        fast condition (an else-if chain, the shape of every interpreter's
        kind dispatch), hand off to `_if_chain`, which walks the whole
        chain without pushing one eval_If generator per level. Returns the
        value / `_TailCall`, a chain generator for the driver to push
        (walked chain, innermost branch needs the trampoline), or None
        (nothing walked, non-fast branch: the caller pushes eval_If
        exactly as before)."""
        bad = _if_bad(cond, node.line)
        if bad is not None:
            return bad
        if cond.value:
            branch = node.then
            which = "took then-branch"
        else:
            branch = node.otherwise
            which = "took else-branch"
        if branch.__class__ is A.Block and len(branch.stmts) == 1:
            branch = branch.stmts[0].expr
        f = branch.fast
        if f is None:
            f = self.compile_fast(branch)
        if f:
            self.fast_hits += 1
            v = f(env)
            return derived("if", which, node.line, (v, cond), v.value)
        if branch.__class__ is A.Call and branch.tail:
            tc = self._tail_inline(branch, env)
            if tc is not None:
                tc.ifs.append((node, which, cond))
                return tc
        elif branch.__class__ is A.If:
            cf = branch.cond.fast
            if cf is None:
                cf = self.compile_fast(branch.cond)
            if cf:
                self.fast_hits += 1
                return self._if_chain(node, which, cond, branch, cf(env), env)
        return None

    def _if_chain(self, node, which, cond, chain_node, chain_cond, env):
        """Walk DOWN an else-if chain (level ≥2; level 1 stays on
        `_if_inline`'s straight-line path so single-`if` code pays nothing
        for F3). `pending` holds the decisions outermost-first; the final
        result is wrapped innermost-out, node-for-node what nested eval_If
        unwinding produces."""
        pending = [(node, which, cond)]
        node = chain_node
        cond = chain_cond
        while True:
            bad = _if_bad(cond, node.line)
            if bad is not None:
                result = bad
                break
            if cond.value:
                branch = node.then
                which = "took then-branch"
            else:
                branch = node.otherwise
                which = "took else-branch"
            if branch.__class__ is A.Block and len(branch.stmts) == 1:
                branch = branch.stmts[0].expr
            f = branch.fast
            if f is None:
                f = self.compile_fast(branch)
            if f:
                self.fast_hits += 1
                v = f(env)
                result = derived("if", which, node.line, (v, cond), v.value)
                break
            if branch.__class__ is A.Call and branch.tail:
                tc = self._tail_inline(branch, env)
                if tc is not None:
                    tc.ifs.append((node, which, cond))
                    tc.ifs.extend(reversed(pending))
                    return tc
            elif branch.__class__ is A.If:
                cf = branch.cond.fast
                if cf is None:
                    cf = self.compile_fast(branch.cond)
                if cf:
                    self.fast_hits += 1
                    pending.append((node, which, cond))
                    node = branch
                    cond = cf(env)
                    continue
            pending.append((node, which, cond))
            return self._if_chain_gen(pending, branch, env)
        for pnode, pwhich, pcond in reversed(pending):
            result = derived("if", pwhich, pnode.line, (result, pcond),
                             result.value)
        return result

    def _if_chain_gen(self, pending, branch, env):
        """Finish a walked else-if chain whose innermost taken branch needs
        the trampoline: evaluate the branch, then apply the pending `if`
        wrappers innermost-out — or, when the branch resolves to a pending
        tail call, hand every walked decision to the tail loop
        (innermost-first, the order nested eval_If unwinding appends)."""
        result = yield (branch, env)
        if type(result) is _TailCall:
            result.ifs.extend(reversed(pending))
            return result
        for pnode, pwhich, pcond in reversed(pending):
            result = derived("if", pwhich, pnode.line, (result, pcond),
                             result.value)
        return result

    # --- the fast path: call-free subtrees as closures -------------------
    # Compiled closures evaluate recursively on the host stack (1-3 frames
    # per level), so a subtree taller than this stays on the trampoline —
    # its shallower call-free children still run inline.
    FAST_MAX_DEPTH = 100

    def compile_fast(self, node):
        """Closure `f(env) -> value` for a call-free subtree, or False if the
        subtree contains a call, is taller than FAST_MAX_DEPTH, or the fast
        path is off. Cached on the node; children are compiled (and cached)
        even when the parent is not compilable, so every call-free fragment
        runs inline. Iterative post-order so that compiling never recurses
        on the host stack either (a 2000-term `1 + 1 + …` chain parses
        iteratively and must not crash the compiler)."""
        f = node.fast
        if f is not None:
            return f
        if not self.fast:
            node.fast = False
            return False
        # post-order: every child is compiled (cached) before its parent, so
        # _compile's calls to compile_fast on children are cache hits
        order = []
        stack = [node]
        while stack:
            n = stack.pop()
            if n.fast is not None:
                continue
            order.append(n)
            stack.extend(_children(n))
        for n in reversed(order):
            if n.fast is not None:
                continue
            kids = _children(n)
            n.fdepth = 1 + max([k.fdepth for k in kids] or [0])
            if n.fdepth > self.FAST_MAX_DEPTH:
                n.fast = False
            else:
                n.fast = self._compile(n)
        return node.fast

    def compile_direct(self, node):
        """Direct closure `d(env) -> value | _TailCall` for a subtree that
        contains calls (v0.9), or False when it is taller than
        FAST_MAX_DEPTH (or direct mode is off — then nothing is cached, so
        another interpreter sharing this AST can still compile it). Runs
        `compile_fast` first: every call-free fragment is a fast closure,
        and a direct closure is built from fast children plus direct
        children. `cdepth` is filled in the same post-order pass."""
        d = node.direct
        if d is not None:
            return d
        if not self.direct:
            return False
        f = node.fast
        if f is None:
            f = self.compile_fast(node)
        if f:
            node.direct = f     # a fast closure is a direct closure
            return f
        order = []
        stack = [node]
        while stack:
            n = stack.pop()
            if n.direct is not None or n.fast:
                continue
            order.append(n)
            stack.extend(k for k in _children(n) if not k.fast)
        for n in reversed(order):
            if n.direct is not None:
                continue
            kids = [k for k in _children(n) if not k.fast]
            if n.__class__ is A.Block and len(n.stmts) == 1:
                n.cdepth = kids[0].cdepth      # unwrapped: no frame of its own
            else:
                n.cdepth = 1 + max([k.cdepth for k in kids] or [0])
            if n.fdepth > self.FAST_MAX_DEPTH or \
                    any(k.direct is False for k in kids):
                n.direct = False
            else:
                n.direct = self._compile(n, True)
        return node.direct

    def _sub_direct(self, node):
        """The closure for a child of a node being compiled directly: its
        fast closure when call-free, else its direct closure (already
        compiled by compile_direct's post-order; False if too tall)."""
        f = node.fast
        return f if f else node.direct

    def _compile(self, node, direct=False):
        """Closure for `node`. `direct=False` (v0.4): call-free subtrees
        only, children via compile_fast. `direct=True` (v0.9): children via
        `_sub_direct`, calls compile to `_call_direct` (or a `_TailCall`),
        and `if` / blocks pass a pending `_TailCall` up unchanged, exactly
        as eval_If / eval_Block do on the trampoline."""
        sub = self._sub_direct if direct else self.compile_fast
        t = node.__class__
        line = node.line
        if t is A.Num or t is A.Str or t is A.BoolLit:
            c = _const(node)
            return lambda env: c
        if t is A.NameRef:
            name = node.name

            def f_name(env):
                while env is not None:        # Env.get, inlined
                    vs = env.vars
                    if name in vs:
                        return vs[name]
                    env = env.parent
                return mk_miss("unbound name '%s'" % name, line, "name", name)
            return f_name
        if t is A.FnExpr:
            params, body, rt = node.params, node.body, node.ret_type
            return lambda env: leaf("fn", "(anonymous)", line,
                                    _mk_closure(None, params, body, env, rt))
        if t is A.Call:
            ff = sub(node.fn)
            gs = [sub(a) for a in node.args]
            # v0.7 (F1): a call to a never-shadowed PLAIN builtin (not a
            # generator: it cannot re-enter Whence code) compiles inline,
            # which lets the ENCLOSING subtree compile too. The shadowed
            # gate is static; the closure still looks the name up and
            # verifies it resolves to this exact builtin, falling back to
            # the full call path (call_value) when a later exec_stmt
            # shadowed it after compilation.
            fnode = node.fn
            if (fnode.__class__ is A.NameRef and all(gs)
                    and fnode.name not in self.shadowed):
                gb = self.globals.vars.get(fnode.name)
                if gb is not None and type(gb.value) is Builtin \
                        and not gb.value.is_gen:
                    return self._compile_builtin_call(
                        fnode.name, gb.value, tuple(gs), line)
            if not direct or not (ff and all(gs)):
                return False
            gs = tuple(gs)
            # v0.10: NO list comprehension on the direct path. In CPython
            # < 3.12 a comprehension is a real frame, and `cdepth` charges
            # closure frames only — v0.9 under-charged every call whose
            # argument (or list literal) holds a call by one frame per
            # level, and `fn nest(n) { … [nest(n - 1)] }` overflowed the
            # 350-frame reserve at the CLI's limit of 6000 (found by
            # bench/ref_diff.py --fuzz at that limit; the oracle campaigns
            # run at the default limit, where ~160 levels fit the reserve).
            # One and two arguments (nearly every call) are list displays.
            if node.tail:
                # tail position: hand the pending call to the enclosing
                # call loop (same object the trampoline path produces)
                if len(gs) == 1:
                    g0, = gs
                    return lambda env: _TailCall(ff(env), [g0(env)], line)
                if len(gs) == 2:
                    g0, g1 = gs
                    return lambda env: _TailCall(ff(env), [g0(env), g1(env)],
                                                 line)

                def d_tail(env):
                    fn = ff(env)
                    args = []
                    for g in gs:
                        args.append(g(env))
                    return _TailCall(fn, args, line)
                return d_tail
            interp = self

            def d_call(env):
                fn = ff(env)
                if len(gs) == 1:
                    args = [gs[0](env)]
                elif len(gs) == 2:
                    args = [gs[0](env), gs[1](env)]
                else:
                    args = []
                    for g in gs:
                        args.append(g(env))
                # act through the interpreter that owns this env chain,
                # not the one that compiled the (shared) node — see
                # _compile_builtin_call. Call envs (and globals) carry
                # their interpreter, so this walk is 0–2 hops.
                e = env
                cur = e.interp
                while cur is None:
                    e = e.parent
                    if e is None:
                        cur = interp
                        break
                    cur = e.interp
                return cur._call_direct(fn, args, line)
            return d_call
        if t is A.Binary:
            lf = sub(node.left)
            rf = sub(node.right)
            if not (lf and rf):
                return False
            op = node.op
            if op in ("and", "or"):
                def f_logic(env):
                    left = lf(env)
                    r = _logic_left(op, left, line)
                    if r is not None:
                        return r
                    return _logic_right(op, left, rf(env), line)
                return f_logic
            return _compile_binop(op, lf, rf, line, self.binop)
        if t is A.Unary:
            g = sub(node.operand)
            if not g:
                return False
            op = node.op
            return lambda env: _unary(op, g(env), line)
        if t is A.Why:
            g = sub(node.operand)
            if not g:
                return False
            return lambda env: leaf("why", "", line, Explanation(g(env)))
        if t is A.Snip:
            g = sub(node.operand)
            if not g:
                return False
            return lambda env: derived("snipped", "history snipped", line, (),
                                       g(env).value)
        if t is A.MissLit:
            g = sub(node.reason)
            if not g:
                return False
            return lambda env: _miss_lit(g(env), line)
        if t is A.Rescue:
            lf = sub(node.left)
            rf = sub(node.right)
            if not (lf and rf):
                return False

            def f_rescue(env):
                left = lf(env)
                if not isinstance(left.value, Miss):
                    return left
                right = rf(env)
                return derived("rescue", "recovered", line, (right, left),
                               right.value)
            return f_rescue
        if t is A.If:
            cf = sub(node.cond)
            tf = sub(node.then)
            ef = sub(node.otherwise)
            if not (cf and tf and ef):
                return False
            if direct:
                def d_if(env):
                    cond = cf(env)
                    c = cond.value
                    # v0.10: the guard is two identity tests; `_if_bad`
                    # (a frame per `if`) only builds the miss
                    if c is True:
                        branch = tf(env)
                        which = "took then-branch"
                    elif c is False:
                        branch = ef(env)
                        which = "took else-branch"
                    else:
                        return _if_bad(cond, line)
                    if type(branch) is _TailCall:
                        # completed by the enclosing call loop (eval_If)
                        branch.ifs.append((node, which, cond))
                        return branch
                    return Prov("if", which, line, (branch, cond), _LAZY,
                                branch.value)
                return d_if

            def f_if(env):
                cond = cf(env)
                c = cond.value
                if c is True:
                    branch = tf(env)
                    which = "took then-branch"
                elif c is False:
                    branch = ef(env)
                    which = "took else-branch"
                else:
                    return _if_bad(cond, line)
                return Prov("if", which, line, (branch, cond), _LAZY,
                            branch.value)
            return f_if
        if t is A.Block:
            steps = []
            ok = True
            for stmt in node.stmts:
                g = None
                if type(stmt) is not A.FnDef:
                    g = sub(stmt.expr)
                    ok = ok and bool(g)
                steps.append((type(stmt), stmt, g))
            if not ok:
                return False
            if len(steps) == 1:
                # a one-expression block binds nothing: no inner Env, no
                # frame — the trampoline driver unwraps these too (v0.9;
                # v0.4–v0.8 allocated an Env per evaluation here)
                return steps[0][2]
            interp = self

            def f_block(env):
                inner = Env(env)
                result = None
                for ts, stmt, g in steps:
                    if ts is A.ExprStmt:
                        result = g(inner)   # may be a pending _TailCall
                    elif ts is A.Let:
                        v = g(inner)
                        result = Prov("let", stmt.name, stmt.line, v, _LAZY,
                                      v.value)
                        inner.vars[stmt.name] = result
                    elif ts is A.FnDef:
                        clo = _mk_closure(stmt.name, stmt.params, stmt.body,
                                         inner, stmt.ret_type)
                        inner.define(stmt.name,
                                     leaf("fn", stmt.name, stmt.line, clo))
                        result = None
                    else:
                        # the check belongs to the interpreter acting NOW
                        # (shared-AST determinism, v0.9 — the closure is
                        # cached on the node, see _compile_builtin_call)
                        e = env
                        while e.parent is not None:
                            e = e.parent
                        (e.interp or interp)._record_check(stmt, g(inner))
                        result = None
                return result
            return f_block
        if t is A.ListLit:
            fs = [sub(e) for e in node.items]
            if not all(fs):
                return False
            n = "%d items" % len(fs)

            def f_list(env):
                items = []
                for g in fs:            # no comprehension frame (v0.10)
                    items.append(g(env))
                return Prov("list", n, line, _slot(items), _LAZY,
                            WList(items))
            return f_list
        if t is A.RecordLit:
            pairs = [(name, sub(e)) for name, e in node.pairs]
            if not all(g for _, g in pairs):
                return False

            def f_record(env):
                fields = {}
                for name, g in pairs:
                    fields[name] = g(env)
                return derived("record", "", line, tuple(fields.values()),
                               Record(fields))
            return f_record
        if t is A.Index:
            of = sub(node.obj)
            xf = sub(node.index)
            if not (of and xf):
                return False
            def f_index(env):
                obj = of(env)
                idx = xf(env)
                o = obj.value
                i = idx.value
                # v0.10: list element in range — the pass-through case —
                # without the `_index` frame and WList.__getitem__
                if type(o) is WList and type(i) is int and 0 <= i < o.n:
                    return o.buf[i]
                return _index(obj, idx, line)
            return f_index
        if t is A.FieldAccess:
            of = sub(node.obj)
            if not of:
                return False
            name = node.name

            def f_field(env):
                obj = of(env)
                o = obj.value
                # v0.10: present field of a record — the pass-through case
                # — without the `_field` frame (1.26 M per meta.lang run)
                if type(o) is Record:
                    fields = o.fields
                    if name in fields:
                        return fields[name]
                return _field(obj, name, line)
            return f_field
        raise AssertionError("cannot compile %r" % node)

    def _compile_builtin_call(self, name, b, gs, line):
        """Compiled closure for a direct call to plain builtin `b` (v0.7).
        Node-for-node identical to the trampoline path: same lookup
        semantics (nearest binding wins), same arity miss, same builtin
        node. `p is b` failing means a binding now shadows the builtin —
        take the full dynamic path so semantics never depend on the gate.

        The closure is cached on a SHARED AST node, so it must not act
        through the interpreter that compiled it (round-24 v0.7 bug: a
        second interpreter's `print` output landed in the first one's sink
        — caught by the determinism oracle). The acting interpreter is
        re-resolved from the root env on every call; for an unshadowed
        builtin the name walk ends at the root anyway, so this is free.
        The compiling interpreter remains only as a fallback for env
        chains detached from any interpreter's globals."""
        interp = self
        nargs = len(gs)

        def f_bcall(env):
            e = env
            fnv = None
            while True:
                if fnv is None:
                    vs = e.vars
                    if name in vs:
                        fnv = vs[name]
                parent = e.parent
                if parent is None:
                    break
                e = parent
            cur = e.interp or interp
            if nargs == 1:
                args = [gs[0](env)]
            elif nargs == 2:
                args = [gs[0](env), gs[1](env)]
            else:
                args = []
                for g in gs:            # no comprehension frame (v0.10)
                    args.append(g(env))
            if fnv is None:      # unreachable while builtins are global
                fnv = mk_miss("unbound name '%s'" % name, line, "name", name)
            p = fnv.value
            if p is b:
                if not _arity_ok(b.arity, nargs):
                    return mk_miss("%s expects %s args, got %d" %
                                   (name, _arity_str(b.arity), nargs),
                                   line, "call", name, inputs=tuple(args))
                return b.fn(cur, args, line)
            return cur.call_value(fnv, args, line)
        return f_bcall

    # --- statements -----------------------------------------------------
    def _record_check(self, stmt, v):
        entry = {"label": stmt.label, "line": stmt.line}
        if v.value is True:
            entry["ok"] = True
            entry["note"] = ""
        else:
            entry["ok"] = False
            if isinstance(v.value, Miss):
                entry["note"] = "value was miss: " + "; ".join(v.value.reasons)
            elif v.value is False:
                entry["note"] = "value was false"
            else:
                entry["note"] = "value was %s, not a boolean" % \
                    show_payload(v.value)
            entry["why"] = render_why(v)
            # v0.6: a check that failed on a direct == gets the two sides'
            # histories contrasted — the report shows WHERE they diverged,
            # not just that they did. Only ==: a failing != means the sides
            # agree, and there is nothing to contrast.
            if v.op == "==" and v.value is False:
                ins = v.inputs
                if len(ins) == 2:
                    entry["contrast"] = render_contrast(ins[0], ins[1])
        self.checks.append(entry)

    def _stmt_gen(self, stmt, env):
        if isinstance(stmt, A.Let):
            v = yield (stmt.expr, env)
            wrapped = derived("let", stmt.name, stmt.line, (v,), v.value)
            env.define(stmt.name, wrapped)
            return wrapped
        if isinstance(stmt, A.FnDef):
            clo = _mk_closure(stmt.name, stmt.params, stmt.body, env,
                             stmt.ret_type)
            env.define(stmt.name, leaf("fn", stmt.name, stmt.line, clo))
            return None
        if isinstance(stmt, A.Check):
            v = yield (stmt.expr, env)
            self._record_check(stmt, v)
            return None
        if isinstance(stmt, A.ExprStmt):
            return (yield (stmt.expr, env))
        raise AssertionError("unknown statement %r" % stmt)

    # --- leaf expressions (plain methods; used when fast=False) ----------
    def eval_Num(self, node, env):
        return _const(node)

    def eval_Str(self, node, env):
        return _const(node)

    def eval_BoolLit(self, node, env):
        return _const(node)

    def eval_NameRef(self, node, env):
        v = env.get(node.name)
        if v is None:
            return mk_miss("unbound name '%s'" % node.name, node.line,
                           "name", node.name)
        return v

    def eval_FnExpr(self, node, env):
        return leaf("fn", "(anonymous)", node.line,
                    _mk_closure(None, node.params, node.body, env,
                               node.ret_type))

    # --- compound expressions (generators) ------------------------------
    def eval_ListLit(self, node, env):
        items = []
        for e in node.items:
            items.append((yield (e, env)))
        return derived("list", "%d items" % len(items), node.line,
                       tuple(items), wlist(items))

    def eval_RecordLit(self, node, env):
        fields = {}
        for name, expr in node.pairs:
            fields[name] = yield (expr, env)
        return derived("record", "", node.line, tuple(fields.values()),
                       Record(fields))

    def eval_MissLit(self, node, env):
        reason = yield (node.reason, env)
        return _miss_lit(reason, node.line)

    def eval_Unary(self, node, env):
        v = yield (node.operand, env)
        return _unary(node.op, v, node.line)

    def eval_Why(self, node, env):
        v = yield (node.operand, env)
        return leaf("why", "", node.line, Explanation(v))

    def eval_Snip(self, node, env):
        v = yield (node.operand, env)
        return derived("snipped", "history snipped", node.line, (), v.value)

    def eval_Rescue(self, node, env):
        left = yield (node.left, env)
        if not _is_miss(left):
            return left
        right = yield (node.right, env)
        return derived("rescue", "recovered", node.line, (right, left),
                       right.value)

    def eval_If(self, node, env, cond=None):
        if cond is None:
            cond = yield (node.cond, env)
        bad = _if_bad(cond, node.line)
        if bad is not None:
            return bad
        if cond.value:
            branch = yield (node.then, env)
            which = "took then-branch"
        else:
            branch = yield (node.otherwise, env)
            which = "took else-branch"
        if type(branch) is _TailCall:
            # The branch is a pending tail call: its value is whatever the
            # loop finally returns, so the node is completed by _call_gen.
            branch.ifs.append((node, which, cond))
            return branch
        return derived("if", which, node.line, (branch, cond), branch.value)

    def eval_Block(self, node, env):
        inner = Env(env)
        result = None
        for stmt in node.stmts:
            # every statement kind runs inline (v0.8, F3b): _stmt_gen's
            # per-statement generator was one push + two sends of pure
            # overhead; the four bodies are one line each
            ts = type(stmt)
            if ts is A.ExprStmt:
                result = yield (stmt.expr, inner)
            elif ts is A.Let:
                v = yield (stmt.expr, inner)
                result = derived("let", stmt.name, stmt.line, (v,), v.value)
                inner.define(stmt.name, result)
            elif ts is A.FnDef:
                clo = _mk_closure(stmt.name, stmt.params, stmt.body, inner,
                                 stmt.ret_type)
                inner.define(stmt.name, leaf("fn", stmt.name, stmt.line, clo))
                result = None
            else:
                v = yield (stmt.expr, inner)
                self._record_check(stmt, v)
                result = None
        return result  # parser guarantees last stmt is an ExprStmt

    def eval_Binary(self, node, env):
        op = node.op
        if op in ("and", "or"):
            left = yield (node.left, env)
            r = _logic_left(op, left, node.line)
            if r is not None:
                return r
            right = yield (node.right, env)
            return _logic_right(op, left, right, node.line)
        left = yield (node.left, env)
        right = yield (node.right, env)
        return self.binop(op, left, right, node.line)

    def binop(self, op, left, right, line):
        l, r = left.value, right.value
        tl, tr = type(l), type(r)
        if (tl is int or tl is float) and (tr is int or tr is float):
            # numeric hot path (bool is excluded by the exact type test)
            fn = _NUM_OPS.get(op)
            if fn is not None:
                if r == 0 and (op == "/" or op == "%"):
                    return mk_miss("division by zero" if op == "/" else
                                   "modulo by zero", line, op,
                                   inputs=(left, right))
                try:
                    return Prov(op, "", line, (left, right), _LAZY, fn(l, r))
                except OverflowError:
                    # unbounded int meets bounded float (v0.2.1 hardening,
                    # re-landed in v0.4.1): a miss, never a host exception
                    return mk_miss("number too large for float arithmetic",
                                   line, op, inputs=(left, right))
        elif tl is str and tr is str:
            # string hot path (v0.6): ==/!=/ordering/concat without the
            # deep_eq round trip — a self-hosted evaluator's kind-dispatch
            # does several string == per guest step. NOT _NUM_OPS: the host's
            # str % str would silently format, str * str would raise.
            if op == "+":
                return Prov(op, "concat", line, (left, right), _LAZY, l + r)
            fn = _STR_OPS.get(op)
            if fn is not None:
                return Prov(op, "", line, (left, right), _LAZY, fn(l, r))
        # general path: at least one operand is not a number
        if isinstance(l, Miss) or isinstance(r, Miss):
            return merge_miss(op, "", line, (left, right))
        if isinstance(l, Guess) or isinstance(r, Guess):
            return self._guess_binop(op, left, right, line)
        provs = (left, right)

        if op in ("==", "!="):
            eq = deep_eq(l, r)
            if eq is None:
                return mk_miss("cannot compare functions with ==", line, op,
                               inputs=provs)
            result = eq if op == "==" else not eq
            return derived(op, "", line, provs, result)

        if op in ("<", "<=", ">", ">="):
            if isinstance(l, str) and isinstance(r, str):
                return derived(op, "", line, provs, _NUM_OPS[op](l, r))
            return mk_miss("cannot order %s and %s" %
                           (show_payload(l), show_payload(r)), line, op,
                           inputs=provs)

        if op == "+":
            if isinstance(l, str) and isinstance(r, str):
                return derived(op, "concat", line, provs, l + r)
            if isinstance(l, WList) and isinstance(r, WList):
                return derived(op, "concat", line, provs, l.concat(r))
            return mk_miss("cannot add %s and %s" %
                           (show_payload(l), show_payload(r)), line, op,
                           inputs=provs)

        if op in ("-", "*", "/", "%"):
            return mk_miss("cannot apply '%s' to %s and %s" %
                           (op, show_payload(l), show_payload(r)), line, op,
                           inputs=provs)

        raise AssertionError("unknown binary op %r" % op)

    def _guess_binop(self, op, left, right, line):
        """A binary op with at least one Guess operand (v0.15): unwrap to
        the underlying nodes, compute AS IF both sides were certain, then
        rewrap the result — confidence is the WEAKEST-LINK minimum across
        every Guess operand (not an average: a chain is only as sure as
        its least certain input), sources are the union. A result that is
        a genuine type/value error (e.g. adding a guessed string to a
        number) stays a plain miss, unchanged — a Guess only vouches for
        confidence in an otherwise-valid computation; it does not make an
        invalid one valid, so type errors are never laundered into
        uncertainty. `==`/`!=` fall through this same path (not
        `deep_eq`), so comparing a certain value against a guessed one
        yields a GUESS about the comparison, not a plain bool — you must
        `sure()` a guess before you can be sure of a comparison against
        it, symmetric with any other operator."""
        ln, lc, ls = ((left.value.node, left.value.confidence,
                      left.value.sources) if isinstance(left.value, Guess)
                     else (left, None, ()))
        rn, rc, rs = ((right.value.node, right.value.confidence,
                      right.value.sources) if isinstance(right.value, Guess)
                     else (right, None, ()))
        result = self.binop(op, ln, rn, line)
        if isinstance(result.value, Miss):
            return result
        confidence = min(c for c in (lc, rc) if c is not None)
        return Prov(op, "guess", line, _slot((left, right)), _LAZY,
                   Guess(result, confidence, ls + rs))

    def eval_Call(self, node, env):
        compile_fast = self.compile_fast
        f = node.fn.fast
        if f is None:
            f = compile_fast(node.fn)
        if f:
            self.fast_hits += 1
            fn = f(env)
        else:
            fn = yield (node.fn, env)
        args = []
        for a in node.args:
            f = a.fast
            if f is None:
                f = compile_fast(a)
            if f:
                self.fast_hits += 1
                args.append(f(env))
            else:
                args.append((yield (a, env)))
        if node.tail:
            return _TailCall(fn, args, node.line)
        return (yield _Call(fn, args, node.line))

    def _call_gen(self, fn, args, line):
        if _is_miss(fn):
            return merge_miss("call", "", line, [fn] + args)
        p = fn.value
        if isinstance(p, Builtin):
            if not _arity_ok(p.arity, len(args)):
                return mk_miss("%s expects %s args, got %d" %
                               (p.name, _arity_str(p.arity), len(args)),
                               line, "call", p.name, inputs=tuple(args))
            r = p.fn(self, args, line)
            if p.is_gen:
                r = yield r
            return r
        if isinstance(p, Closure):
            name = p.name or "<fn>"
            if len(args) != len(p.params):
                return mk_miss("%s expects %d args, got %d" %
                               (name, len(p.params), len(args)),
                               line, "call", name, inputs=tuple(args))
            if self.depth >= self.max_depth:
                return mk_miss("recursion too deep in %s (depth %d)" %
                               (name, self.depth), line, "call", name,
                               inputs=tuple(args))
            # v0.13: the ORIGINALLY called closure's own return type, not
            # whatever closure a tail loop switches `p` to below — a typed
            # `-> Type` is a contract on what THIS call returns to ITS
            # caller, checked once the whole merged tail chain settles.
            ret_spec, ret_label = p.ret_spec, p.ret_label
            self.depth += 1
            if self.depth > self.peak_depth:
                self.peak_depth = self.depth
            names = None      # allocated on the first tail iteration (v0.6):
            merged = 1        # the common non-loop call never needs them
            chain_rets = None  # round 335, see `_call_direct`'s own comment
            # v0.4: consecutive identical `if` decisions (same `if` node,
            # same branch) of a tail loop merge into one node whose inputs
            # are the individual conditions: [if_node, which, [cond, ...]].
            runs = None
            call_line = line
            try:
                while True:
                    call_env = Env(p.env, self)
                    vs = call_env.vars
                    for pname, arg in zip(p.params, args):
                        vs[pname] = Prov("arg", pname, call_line, arg, _LAZY,
                                         arg.value)
                    result = yield (p.body, call_env)
                    if type(result) is not _TailCall:
                        break
                    # Tail call: re-enter in this frame (no depth, no host
                    # stack, one merged `call` node for the whole loop).
                    tc = result
                    fn2, args, call_line = tc.fn, tc.args, tc.line
                    if _is_miss(fn2) or not isinstance(fn2.value, Closure):
                        # builtin / non-callable / miss: an ordinary call
                        # with its own node ends the loop, and the `if`
                        # decisions of THIS iteration wrap its result —
                        # the shape the compiled path produces (v0.9 fix:
                        # v0.7 merged them into the runs, so a multi-frame
                        # loop ending in a builtin call rendered one extra
                        # `if ×1` input in fast=False; self_host.lang's
                        # lexer, never fuzzed at that size, exposed it)
                        result = yield _Call(fn2, args, call_line)
                        result = _wrap_ifs(result, tc.ifs)
                        break
                    if runs is None:
                        names = [name]
                        runs = []
                    _merge_ifs(runs, tc.ifs)
                    p = fn2.value
                    chain_rets = _note_chain_ret(chain_rets, p, call_line)
                    name2 = p.name or "<fn>"
                    if len(args) != len(p.params):
                        result = mk_miss(
                            "%s expects %d args, got %d" %
                            (name2, len(p.params), len(args)), call_line,
                            "call", name2, inputs=tuple(args))
                        break
                    if self.max_iter is not None and merged >= self.max_iter:
                        result = mk_miss(
                            "tail loop too long in %s (%d iterations)" %
                            (name2, merged), call_line, "call", name2,
                            inputs=tuple(args))
                        break
                    merged += 1
                    self.tail_calls += 1
                    if name2 not in names:
                        names.append(name2)
            finally:
                self.depth -= 1
            # round 336: inside-out, see `_call_direct`'s twin comment
            if chain_rets is not None:
                result = _check_chain_rets(result, chain_rets)
            result = _check_ret(result, ret_spec, ret_label, line)
            if runs is None:  # the common case: one frame, nothing merged
                return Prov("call", name, line, result, _LAZY, result.value)
            return _finish_call(name, line, result, runs, names, merged)
        return mk_miss("%s is not callable" % show_payload(p), line, "call",
                       inputs=(fn,))

    def eval_Index(self, node, env):
        obj = yield (node.obj, env)
        idx = yield (node.index, env)
        return _index(obj, idx, node.line)

    def eval_FieldAccess(self, node, env):
        obj = yield (node.obj, env)
        return _field(obj, node.name, node.line)


Interpreter._DISPATCH = {
    name[len("eval_"):]: getattr(Interpreter, name)
    for name in dir(Interpreter) if name.startswith("eval_")
}
Interpreter._LEAF = frozenset(
    m for m in Interpreter._DISPATCH.values()
    if not inspect.isgeneratorfunction(m))


_OPAQUE = (Closure, Builtin, Miss, Explanation)


def _compile_binop(op, lf, rf, line, binop):
    """v0.10: one closure per operator with the numeric hot path INLINE —
    the exact-type test (bool excluded), the native operator, one `Prov` —
    instead of a lambda frame plus `binop`'s dictionary dispatch per
    guest operation (816 k per meta.lang run). `==`/`!=`/`+` also take the
    string case inline. Everything else (misses, lists, mixed types, zero
    divisors, int-vs-float overflow) goes to `binop`, which builds the
    byte-identical node — the closure never decides a miss itself, so the
    two paths cannot disagree on wording."""
    if op == "+":
        def f_add(env):
            l = lf(env)
            r = rf(env)
            x = l.value
            y = r.value
            tx = type(x)
            ty = type(y)
            if (tx is int or tx is float) and (ty is int or ty is float):
                try:
                    return Prov("+", "", line, (l, r), _LAZY, x + y)
                except OverflowError:
                    pass
            elif tx is str and ty is str:
                return Prov("+", "concat", line, (l, r), _LAZY, x + y)
            return binop("+", l, r, line)
        return f_add
    if op == "-":
        def f_sub(env):
            l = lf(env)
            r = rf(env)
            x = l.value
            y = r.value
            tx = type(x)
            ty = type(y)
            if (tx is int or tx is float) and (ty is int or ty is float):
                try:
                    return Prov("-", "", line, (l, r), _LAZY, x - y)
                except OverflowError:
                    pass
            return binop("-", l, r, line)
        return f_sub
    if op == "*":
        def f_mul(env):
            l = lf(env)
            r = rf(env)
            x = l.value
            y = r.value
            tx = type(x)
            ty = type(y)
            if (tx is int or tx is float) and (ty is int or ty is float):
                try:
                    return Prov("*", "", line, (l, r), _LAZY, x * y)
                except OverflowError:
                    pass
            return binop("*", l, r, line)
        return f_mul
    if op == "/":
        def f_div(env):
            l = lf(env)
            r = rf(env)
            x = l.value
            y = r.value
            tx = type(x)
            ty = type(y)
            if (tx is int or tx is float) and (ty is int or ty is float) \
                    and y != 0:
                try:
                    return Prov("/", "", line, (l, r), _LAZY, x / y)
                except OverflowError:
                    pass
            return binop("/", l, r, line)
        return f_div
    if op == "%":
        def f_mod(env):
            l = lf(env)
            r = rf(env)
            x = l.value
            y = r.value
            tx = type(x)
            ty = type(y)
            if (tx is int or tx is float) and (ty is int or ty is float) \
                    and y != 0:
                try:
                    return Prov("%", "", line, (l, r), _LAZY, x % y)
                except OverflowError:
                    pass
            return binop("%", l, r, line)
        return f_mod
    if op == "==":
        def f_eq(env):
            l = lf(env)
            r = rf(env)
            x = l.value
            y = r.value
            tx = type(x)
            ty = type(y)
            if ((tx is int or tx is float) and (ty is int or ty is float)) \
                    or (tx is str and ty is str):
                return Prov("==", "", line, (l, r), _LAZY, x == y)
            return binop("==", l, r, line)
        return f_eq
    if op == "!=":
        def f_ne(env):
            l = lf(env)
            r = rf(env)
            x = l.value
            y = r.value
            tx = type(x)
            ty = type(y)
            if ((tx is int or tx is float) and (ty is int or ty is float)) \
                    or (tx is str and ty is str):
                return Prov("!=", "", line, (l, r), _LAZY, x != y)
            return binop("!=", l, r, line)
        return f_ne
    fn = _NUM_OPS[op]          # < <= > >= : numbers, and strings (same fn)

    def f_cmp(env):
        l = lf(env)
        r = rf(env)
        x = l.value
        y = r.value
        tx = type(x)
        ty = type(y)
        if ((tx is int or tx is float) and (ty is int or ty is float)) \
                or (tx is str and ty is str):
            return Prov(op, "", line, (l, r), _LAZY, fn(x, y))
        return binop(op, l, r, line)
    return f_cmp


def _merge_ifs(runs, ifs):
    """Tail-loop bookkeeping shared by `_call_gen` and `_call_direct`
    (v0.4 merged decisions): fold the `if` decisions one iteration passed
    through (innermost first, so reversed = evaluation order) into `runs`,
    where consecutive identical decisions (same `if` node, same branch)
    accumulate their conditions into one run."""
    # v0.10: an entry is the `(if_node, which, cond)` tuple the tail call
    # carried (no allocation) until a second identical decision promotes
    # it to a `[if_node, which, [cond, ...]]` run. 99.99 % of the runs in
    # meta.lang / self_host.lang are one decision long.
    for t in reversed(ifs):
        if runs:
            last = runs[-1]
            if last[0] is t[0] and last[1] == t[1]:
                if type(last) is tuple:
                    runs[-1] = [t[0], t[1], [last[2], t[2]]]
                else:
                    last[2].append(t[2])
                continue
        runs.append(t)


def _wrap_ifs(result, ifs):
    """Complete the `if` decisions a pending tail call passed through
    (innermost first) around the value the call finally produced — the
    shape nested eval_If unwinding would have built had the branch been a
    plain value. Used when a tail loop ends in a builtin / non-callable /
    miss call (v0.7 found the single-frame case; v0.9 the multi-frame)."""
    for ifn, which, cond in ifs:
        result = Prov("if", which, ifn.line, (result, cond), _LAZY,
                      result.value)
    return result


def _finish_call(name, line, result, runs, names, merged):
    """The provenance of a finished call loop, shared by `_call_gen` and
    `_call_direct`. One frame: a `call name` node. Merged frames: `call
    a/b ×N` whose inputs are the final result followed by one `if … ×K`
    node per run of identical decisions (v0.4). `runs` is None exactly
    when merged == 1 (a loop that never re-entered)."""
    value = result.value
    if merged == 1:
        return Prov("call", name, line, result, _LAZY, value)
    ifs = [result]
    for run in runs:
        if type(run) is tuple:
            # a run of ONE decision: a plain `if` node with the condition
            # as its single input — the shape MergedProv(count=1) had,
            # minus the second class, the count slot and two lists (v0.10)
            ifs.append(Prov("if", run[1], run[0].line, run[2], _LAZY, value))
        else:
            ifn, which, conds = run
            ifs.append(MergedProv("if", which, ifn.line, tuple(conds), _LAZY,
                                  value, len(conds)))
    return MergedProv("call", "/".join(names), line, tuple(ifs), _LAZY, value,
                      merged)


def deep_eq(l, r, memo=None):
    """Structural equality. Returns True/False, or None for incomparable
    (functions, misses, explanations) — callers turn None into a miss.
    Iterative (explicit stack): a 20000-deep nested record built by runaway
    recursion must compare without a host RecursionError (fuzz, round 9).
    `memo` (v0.4.1): a dict of (id(l), id(r)) pairs already known equal,
    shared across many calls by `diverge`, so a deep value shared by
    hundreds of history nodes is walked once, not once per node."""
    stack = [(l, r)]
    seen = [] if memo is not None else None
    while stack:
        l, r = stack.pop()
        if memo is not None:
            key = (id(l), id(r))
            if key in memo:
                continue
            seen.append(key)
        if isinstance(l, _OPAQUE) or isinstance(r, _OPAQUE):
            return None
        if isinstance(l, bool) != isinstance(r, bool):
            return False
        if isinstance(l, bool):
            if l != r:
                return False
        elif _is_num(l) and _is_num(r):
            if l != r:
                return False
        elif isinstance(l, str) and isinstance(r, str):
            if l != r:
                return False
        elif isinstance(l, WList) and isinstance(r, WList):
            if len(l) != len(r):
                return False
            for a, b in zip(l, r):
                stack.append((a.payload, b.payload))
        elif isinstance(l, Record) and isinstance(r, Record):
            if set(l.fields) != set(r.fields):
                return False
            for k in l.fields:
                stack.append((l.fields[k].payload, r.fields[k].payload))
        elif isinstance(l, Guess) and isinstance(r, Guess):
            # structural equality is about the ANSWER, not how sure either
            # side was (confidence/sources are metadata, not identity) —
            # deliberately different from top-level `==` on a bare guess,
            # which goes through `_guess_binop` instead of `deep_eq` and
            # DOES carry confidence into its result (see that method's
            # docstring). `contains`/`find`/nested `==` on a list or
            # record of guesses reach this path, not that one.
            stack.append((l.node.payload, r.node.payload))
        else:
            return False  # different types
    if memo is not None:
        for key in seen:
            memo[key] = True
    return True


# --- builtins ------------------------------------------------------------

def _arity_ok(arity, n):
    if arity is None:
        return True
    if isinstance(arity, tuple):
        return arity[0] <= n <= arity[1]
    return n == arity


def _arity_str(arity):
    if arity is None:
        return "any number of"
    if isinstance(arity, tuple):
        return "%d..%d" % arity
    return str(arity)


def _propagate(name, args, line):
    """If any arg is a miss, return the merged miss; else None."""
    if any(_is_miss(a) for a in args):
        return merge_miss("builtin", name, line, args)
    return None


_KIND_ORDER = (
    (Miss, "miss"), (bool, "bool"), ((int, float), "num"), (str, "str"),
    (WList, "list"), (Record, "record"), ((Closure, Builtin), "fn"),
    (Guess, "guess"),
)


def _kind(payload):
    """The runtime shape of a payload as a Whence-visible string: one of
    `num str bool list record fn guess miss`, or `"value"` for the two
    payloads with no Whence type tag (`why`'s Explanation; nothing else
    escapes to user code). `bool` before `(int, float)`: Python bools are
    ints."""
    for types, name in _KIND_ORDER:
        if isinstance(payload, types):
            return name
    return "value"


def _spec_ok(spec):
    """Whether `spec` is a usable `typed`/`matches` type spec ALL THE WAY
    DOWN: a primitive tag string, or a Record whose every non-`__shape`
    field value is itself a usable spec.

    `_type_match` states this as its own precondition. The PARSER enforces
    it for a DECLARED shape (`parse_type` accepts only a primitive tag or
    an earlier shape name, so `shape Bad = @{x: 5}` is a parse error), but
    `typed`/`matches` also accept a hand-built record as a spec by design
    — SPEC's "structural, not nominal": "a record built entirely by hand,
    with no relation to the shape ever declared, matches it exactly as one
    built from it". Nothing ever checked the FIELDS of such a record, so
    `matches(@{a: 1}, @{a: 5})` recursed into `5`, reached `spec.fields`
    on an int, and raised `AttributeError` straight out of the interpreter
    — a totality violation in a builtin whose own contract is "never
    itself a miss" (round 335; reachable from a parameter guard too, via a
    `shape` name shadowed by an ordinary `let` or a parameter).

    Both callers already rejected a malformed spec at the TOP level, each
    with its own policy (`matches` -> false, `typed` -> its own miss); this
    just makes that check mean what it says instead of stopping one level
    down. Recursion is bounded: records are immutable and built bottom-up,
    so a spec record cannot contain itself.
    """
    if isinstance(spec, str):
        return True
    if not isinstance(spec, Record):
        return False
    for fname, node in spec.fields.items():
        if fname != "__shape" and not _spec_ok(node.value):
            return False
    return True


def _type_match(payload, spec):
    """Structural type test (v0.12): `spec` is a Python str (a primitive
    tag, `"any"` always matching) or a Whence Record (a `shape`'s payload:
    `__shape` names it for messages, every other field maps to a nested
    spec — a str or, for a shape-typed field, another Record — checked
    recursively). A record matches a shape when every declared field is
    PRESENT with a non-miss value of the right shape; extra fields are
    ignored (width/structural subtyping, not nominal — a record built by
    hand matches a `shape` exactly as one built from it). Returns
    (matched, the name to show in a mismatch message). Shapes can only
    reference earlier shapes (parser-enforced), so this recursion is
    bounded by the shape declaration order and cannot cycle."""
    if isinstance(spec, str):
        if spec == "any":
            return True, "any"
        return _kind(payload) == spec, spec
    name_node = spec.fields.get("__shape")
    if name_node is None:
        name = "record"
    else:
        # `shape Name = …` always binds a Str here, but a HAND-BUILT spec
        # record can carry any payload under `__shape`, and `name` goes
        # straight into a user-visible miss message. Rendering a non-str
        # through `%s` leaked the Python repr — including the object's heap
        # ADDRESS, which made the message differ between two runs of the
        # same program and tripped the determinism/fast_slow/direct oracles
        # (round 335). `show_payload` is this project's one renderer for
        # exactly this job.
        name = name_node.value
        if not isinstance(name, str):
            name = show_payload(name)
    if not isinstance(payload, Record):
        return False, name
    have = payload.fields
    for fname, fspec_node in spec.fields.items():
        if fname == "__shape":
            continue
        if fname not in have or isinstance(have[fname].value, Miss):
            return False, name
        ok, _ = _type_match(have[fname].value, fspec_node.value)
        if not ok:
            return False, name
    return True, name


def _note_chain_ret(chain_rets, p, line):
    """Record a tail-entered closure's own `-> Type` contract as
    `[spec, label, line]`, where `line` is the line of the TAIL CALL that
    entered it — exactly the line the same call would carry if it were
    lifted out of tail position with a `let`.

    Round 336 (language C) rewrote round 335's version, which recorded
    `(spec, label)` only, skipped anything whose spec was the originally
    called closure's, and kept the FIRST occurrence of a repeated spec.
    All three choices blamed the wrong closure, because
    `_check_chain_rets` now walks the chain from the INSIDE OUT (see its
    docstring): what must survive a repeat is the INNERMOST entry, so a
    recurring spec is moved to the end with its label and line refreshed.

    Kept from round 335, and load-bearing: `p.ret_spec is None` (an
    untyped callee, the overwhelmingly common case) exits on the first
    test, so an untyped program never allocates. Also deliberately
    identity-based — within one run every mode sees the same Closure/spec
    objects, and a `Str` spec is the AST node's own string, shared across
    runs of the same AST, so the three-way fast/direct/trampoline
    differential and the determinism oracle all see the same list in the
    same order. Unlike round 335's version the identity test is now a pure
    OPTIMISATION, never a semantic: two `-> num` closures whose specs are
    NOT the same object simply get two entries, and checking the same
    contract twice cannot change which check fails first."""
    rs = p.ret_spec
    if rs is None:
        return chain_rets
    if chain_rets is None:
        return [[rs, p.ret_label, line]]
    last = chain_rets[-1]
    if last[0] is rs:                     # incl. every self-recursive bounce
        last[1] = p.ret_label
        last[2] = line
        return chain_rets
    for i in range(len(chain_rets) - 1):
        if chain_rets[i][0] is rs:
            ent = chain_rets.pop(i)
            ent[1] = p.ret_label
            ent[2] = line
            chain_rets.append(ent)
            return chain_rets
    chain_rets.append([rs, p.ret_label, line])
    return chain_rets


def _check_chain_rets(result, chain_rets):
    """Apply the `-> Type` contracts of the closures a merged tail chain
    entered, INNERMOST FIRST, before the originally-called closure's own
    check (round 336; round 335 added the checks, this round fixed their
    order and their line attribution). A self-recursive loop records the
    originally-called closure here too — the outer `_check_ret` then sees
    an already-settled result and passes it through, so the miss carries
    the INNERMOST frame's line, exactly as non-tail recursion does.

    History, because the order is the whole point. v0.13 captured
    `ret_spec`/`ret_label` from the originally-called closure so a tail
    loop reassigning `p` could not make the check adopt the chain's LAST
    contract instead of the caller's own — right, and unchanged. Round 335
    found the other half: the closures the loop bounced THROUGH had their
    contracts dropped entirely, so `fn f() -> num { "s" }` missed when
    called as `let q = f()` and returned the raw `"s"` when any other
    function called it in tail position. It fixed WHETHER each contract
    runs and left WHICH ONE IS BLAMED still depending on tail position:
    it checked the caller's contract first and the chain's in entry
    order, i.e. outermost-first — the exact REVERSE of what the same
    program does with each call lifted out of tail position by a `let`.

    Round 336's rule, and the invariant the tests pin: **a tail call is a
    space optimisation, never a semantic one** (decision 8: tail calls
    merge, they do not forget). In a tail chain `a -> b -> c` the settled
    value is returned by `c` to `b` to `a`, so `c`'s contract is tested
    first, and the first failure wins — identical to the lifted program,
    identical to how non-tail recursion has always behaved
    (`test_non_tail_recursion_checks_every_frame_independently`), and
    identical to what `examples/self_eval.lang`, Whence's own definition
    of Whence, has always computed: the guest evaluator has no tail-call
    merging at all, so `apply_closure`'s `check_ret` per frame IS the
    inside-out order. On five of the seven probe programs round 336 ran,
    the host blamed a different function than the guest did; the
    guest-differential oracle could not see it because miss WORDINGS are
    an explicit exemption of that oracle (round 17).

    Each entry carries its own tail-call line for the same reason, so a
    chain miss points at the call that produced the bad value rather than
    at the outermost call site.

    `chain_rets` is None for every call that never tail-called a TYPED
    closure — which includes every untyped program — so nothing is
    allocated there at all.
    """
    for i in range(len(chain_rets) - 1, -1, -1):
        spec, label, line = chain_rets[i]
        result = _check_ret(result, spec, label, line)
    return result


def _check_ret(result, ret_spec, ret_label, line):
    """Check a closure's return value against its `-> Type` annotation
    (v0.13) at the one point every call path (fast, direct, generator)
    settles to a final `result` Prov before wrapping it in a `call` node.
    Mirrors the `typed` builtin's own contract exactly, because a return
    check IS a `typed` check — just applied by the callee's contract
    instead of a leading `let`: `ret_spec is None` (no `-> Type`, the
    common case) is a no-op; a `result` that is already a miss propagates
    UNCHANGED (decision 2 — misses propagate before inspection, so a
    function that already failed does not also get a "wrong return type"
    gloss painted over its own miss); otherwise a structural mismatch
    becomes a fresh origin miss — same wording, same "typed" op tag, same
    single-input shape `typed()` itself returns — so `blame` on a bad
    return finds the same kind of node a bad parameter would have."""
    if ret_spec is None or _is_miss(result):
        return result
    if isinstance(ret_spec, _UnboundRetType):
        return mk_miss("%s: type '%s' is not in scope here" %
                       (ret_label, ret_spec.name), line, "typed", ret_label,
                       inputs=(result,))
    ok, desc = _type_match(result.value, ret_spec)
    if ok:
        return result
    return mk_miss("%s expected %s, got %s" %
                   (ret_label, desc, _kind(result.value)), line,
                   "typed", ret_label, inputs=(result,))


class _UnboundRetType(object):
    """Sentinel `ret_spec` (v0.13): the `-> Shape` named a shape that is not
    bound in `env` at closure-creation time. Unreachable for a MODULE-level
    shape (the parser's `self.shapes` already rejects any name not declared
    earlier in the file — decision: no forward refs), but the parser is not
    scope-aware, so `fn g() { shape Local = @{…} 1 }  fn f() -> Local { … }`
    parses (`Local` was seen) while `Local`'s binding lives only inside
    `g`'s call env, never at the scope `f` is defined in. The equivalent
    PARAM-type gap degrades safely on its own, because a param guard's spec
    is an ordinary `A.NameRef` walked by the everyday evaluator, which
    already turns a missing name into a miss instead of raising; a naive
    `env.get(name).payload` for the return-type path has no such
    protection and raised AttributeError on `None` (found by round-128
    exploratory testing, never hit by the existing corpus/fuzzer because
    nothing generates nested shape declarations yet). Never leaks to
    Whence code — `_check_ret` turns it into an ordinary miss, same as
    every other kind of type mismatch."""
    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name


def _closure_ret(name, ret_type, env):
    """(spec, label) for a FnDef/FnExpr's `-> Type` annotation, resolved
    ONCE at Closure creation (v0.13) — never per call, and never touching
    the body's AST, which is why it costs a typed tail-recursive function
    nothing per bounce (unlike a param guard, which is a real statement
    re-executed every call). `ret_type` is None, or the spec expr
    `parser._type_spec_expr` built (`A.Str` for a primitive tag, `A.NameRef`
    for a shape); a shape resolves through `env` exactly once, matching
    `_type_spec_expr`'s own rationale — shapes are bound once, so this
    cannot go stale. None, None (the common case) costs one attribute
    read and an identity check."""
    if ret_type is None:
        return None, None
    if ret_type.__class__ is A.Str:
        spec = ret_type.value
    else:
        binding = env.get(ret_type.name)
        spec = binding.payload if binding is not None \
            else _UnboundRetType(ret_type.name)
    label = "return value of %s" % name if name else "return value"
    return spec, label


def _mk_closure(name, params, body, env, ret_type):
    """`Closure(...)` with its `-> Type` return spec resolved (v0.13) — the
    one choke point every FnDef/FnExpr construction site (fast, direct,
    and the three generator-mode sites) goes through, so closures for the
    same function built by any execution mode agree byte-for-byte on
    ret_spec/ret_label (required for the fast/direct/trampoline three-way
    differential)."""
    spec, label = _closure_ret(name, ret_type, env)
    return Closure(name, params, body, env, spec, label)


def _history_root(v):
    """The provenance node a query builtin should start from: an explanation's
    root if given `why x`, else the value's own provenance."""
    if isinstance(v.payload, Explanation):
        return v.payload.root
    return v


def _step_record(node, depth, line):
    """Reify one provenance node as a Whence record. `value` is the real
    historic value (payload + that node as its provenance), so programs can
    compute with it, not just read about it."""
    fields = {
        "op": leaf("step", "op", line, node.op),
        "detail": leaf("step", "detail", line, node.detail),
        "line": leaf("step", "line", line, node.line),
        "show": leaf("step", "show", line, node.show),
        "depth": leaf("step", "depth", line, depth),
        "inputs": leaf("step", "inputs", line, len(node.inputs)),
        "count": leaf("step", "count", line, node.count),
        "value": node,
    }
    return derived("step", node.label(), line, (node,), Record(fields))


_BUILTIN_TABLE = None   # [(name, Builtin)], built once — see _install_builtins


def _install_builtins(env):
    """Define every builtin in `env`. The `Builtin` payloads are module-level
    singletons (built on first call, then shared by every interpreter) so the
    `p is b` identity gate in compiled call sites (`_compile_builtin_call`)
    holds across interpreters running the same AST; only the Prov wrapper
    nodes are fresh per env. Builtin fns take the acting interpreter as an
    argument and close over nothing per-interpreter, so sharing is safe."""
    global _BUILTIN_TABLE
    if _BUILTIN_TABLE is None:
        _BUILTIN_TABLE = _make_builtin_table()
    for name, b in _BUILTIN_TABLE:
        env.define(name, Prov("builtin", name, 0, (), name, b))


def _make_builtin_table():
    table = []

    def register(name, arity):
        def wrap(fn):
            table.append((name, Builtin(name, arity, fn)))
            return fn
        return wrap

    @register("print", 1)
    def b_print(interp, args, line):
        interp._out(full_show(args[0].payload))
        return args[0]  # pass-through: print(x) is x

    @register("rand", 0)
    def b_rand(interp, args, line):
        # v0.14.8: the second effectful builtin (tag "random", distinct
        # from print's "io") — a float in [0.0, 1.0) drawn from this
        # Interpreter's own seeded stream (`interp._rng`), a leaf (no
        # input provenance) exactly like a literal.
        return leaf("rand", "", line, interp._rng.random())

    @register("len", 1)
    def b_len(interp, args, line):
        m = _propagate("len", args, line)
        if m:
            return m
        p = args[0].payload
        if isinstance(p, (str, WList)):
            return derived("len", "", line, (args[0],), len(p))
        if isinstance(p, Record):
            return derived("len", "", line, (args[0],), len(p.fields))
        return mk_miss("len of %s" % show_payload(p), line, "len",
                       inputs=(args[0],))

    @register("range", (1, 2))
    def b_range(interp, args, line):
        m = _propagate("range", args, line)
        if m:
            return m
        for a in args:
            if not isinstance(a.payload, int) or isinstance(a.payload, bool):
                return mk_miss("range needs integers, got %s" %
                               show_payload(a.payload), line, "range",
                               inputs=tuple(args))
        lo, hi = (0, args[0].payload) if len(args) == 1 else \
                 (args[0].payload, args[1].payload)
        items = [leaf("range", str(i), line, i) for i in range(lo, hi)]
        return derived("range", "%d..%d" % (lo, hi), line,
                       tuple(args), wlist(items))

    @register("map", 2)
    def b_map(interp, args, line):
        m = _propagate("map", args, line)
        if m:
            return m
        fn, xs = args
        if not isinstance(xs.payload, WList):
            return mk_miss("map needs a list, got %s" % show_payload(xs.payload),
                           line, "map", inputs=(fn, xs))
        out = []
        for x in xs.payload:
            out.append((yield _Call(fn, [x], line)))
        return derived("map", "", line, (xs,), wlist(out))

    @register("filter", 2)
    def b_filter(interp, args, line):
        m = _propagate("filter", args, line)
        if m:
            return m
        fn, xs = args
        if not isinstance(xs.payload, WList):
            return mk_miss("filter needs a list, got %s" %
                           show_payload(xs.payload), line, "filter",
                           inputs=(fn, xs))
        out = []
        for x in xs.payload:
            keep = yield _Call(fn, [x], line)
            if _is_miss(keep):
                return merge_miss("filter", "predicate missed", line,
                                  (keep, xs))
            if not isinstance(keep.payload, bool):
                return mk_miss("filter predicate must return true/false, got %s"
                               % show_payload(keep.payload), line, "filter",
                               inputs=(keep, xs))
            if keep.payload:
                out.append(x)
        return derived("filter", "", line, (xs,), wlist(out))

    @register("fold", 3)
    def b_fold(interp, args, line):
        m = _propagate("fold", args, line)
        if m:
            return m
        fn, acc, xs = args
        if not isinstance(xs.payload, WList):
            return mk_miss("fold needs a list, got %s" % show_payload(xs.payload),
                           line, "fold", inputs=(fn, xs))
        n = 0
        for x in xs.payload:
            acc = yield _Call(fn, [acc, x], line)
            n += 1
        # v0.3: fold has a node of its own (inputs: final accumulator, list)
        # so `at(x, "fold")` / `steps(x, "fold")` can find it and `why`
        # shows the list that was folded, not just the last step.
        return derived("fold", "%d items" % n, line, (acc, xs),
                       acc.payload)

    @register("push", 2)
    def b_push(interp, args, line):
        xs, x = args
        if _is_miss(xs):
            return merge_miss("push", "", line, args)
        if not isinstance(xs.payload, WList):
            return mk_miss("push needs a list, got %s" % show_payload(xs.payload),
                           line, "push", inputs=(xs, x))
        return derived("push", "", line, (xs, x), xs.payload.push(x))

    @register("str", 1)
    def b_str(interp, args, line):
        # Deliberately total: works on misses ("miss: ...") and explanations
        # (rendered tree) so programs can report and introspect them.
        return derived("str", "", line, (args[0],),
                       full_show(args[0].payload))

    @register("num", 1)
    def b_num(interp, args, line):
        m = _propagate("num", args, line)
        if m:
            return m
        p = args[0].payload
        if _is_num(p):
            return args[0]
        if isinstance(p, str):
            # Whence decimal syntax only (surrounding whitespace tolerated):
            # the host's int()/float() also take "1_000", "nan", "inf",
            # "infinity" and non-ASCII digits, none of which is a number here
            t = p.strip()
            m = _NUM_RE.match(t)
            if not m:
                return mk_miss('num: cannot parse "%s"' % p, line, "num",
                               inputs=(args[0],))
            v = float(t) if (m.group(2) or m.group(3)) else int(t)
            if isinstance(v, float) and (v != v or v in (_INF, -_INF)):
                return mk_miss('num: "%s" is out of range' % p, line, "num",
                               inputs=(args[0],))
            return derived("num", "", line, (args[0],), v)
        return mk_miss("num of %s" % show_payload(p), line, "num",
                       inputs=(args[0],))

    @register("abs", 1)
    def b_abs(interp, args, line):
        m = _propagate("abs", args, line)
        if m:
            return m
        p = args[0].payload
        if _is_num(p):
            return derived("abs", "", line, (args[0],), abs(p))
        return mk_miss("abs of %s" % show_payload(p), line, "abs",
                       inputs=(args[0],))

    @register("sqrt", 1)
    def b_sqrt(interp, args, line):
        m = _propagate("sqrt", args, line)
        if m:
            return m
        p = args[0].payload
        if not _is_num(p):
            return mk_miss("sqrt of %s" % show_payload(p), line, "sqrt",
                           inputs=(args[0],))
        if p < 0:
            return mk_miss("sqrt of negative number %r" % p, line, "sqrt",
                           inputs=(args[0],))
        try:
            return derived("sqrt", "", line, (args[0],), math.sqrt(p))
        except OverflowError:
            return mk_miss("number too large for float arithmetic", line,
                           "sqrt", inputs=(args[0],))

    @register("trunc", 1)
    def b_trunc(interp, args, line):
        # v0.17: closes round 294's own "rand(lo, hi) not yet justified"
        # backlog item by fixing the REAL blocker — no builtin could ever
        # turn a float into an int, so `num(lo + rand() * (hi - lo + 1))`
        # (the obvious pure-Whence way to build a ranged random draw from
        # `rand()`'s own [0.0, 1.0) output) was never expressible at all;
        # `num()` on an already-numeric value is an identity, not a round.
        # Rounds TOWARD ZERO (`int(p)`'s own Python semantics for a float),
        # matching `abs`'s existing "toward zero is the origin" convention
        # rather than floor's "toward negative infinity" — the two agree
        # for every non-negative input, which is all `rand()`-driven code
        # ever produces, so the choice is invisible to that motivating use
        # case; documented here since it is NOT invisible for negative
        # inputs (`trunc(-1.5)` is `-1`, `floor(-1.5)` would be `-2`).
        m = _propagate("trunc", args, line)
        if m:
            return m
        p = args[0].payload
        if not _is_num(p):
            return mk_miss("trunc of %s" % show_payload(p), line, "trunc",
                           inputs=(args[0],))
        # round 323: `int(p)` on a non-finite float is a host crash, not a
        # miss — `OverflowError` for +-inf, `ValueError` ("cannot convert
        # float NaN to integer") for nan — violating the total-evaluator
        # invariant `_is_num` alone doesn't guard against (`nan`/`inf` are
        # ordinary `float` instances). Previously unreachable except via a
        # contrived huge-digit-string-plus-fraction literal (`fuzz.py`
        # never generates one); trivially reachable now that the lexer
        # (this round, `lexer.py`) accepts exponent literals like
        # `1e400`. Same idiom and message as `sqrt`'s own overflow guard
        # just above.
        try:
            return derived("trunc", "", line, (args[0],), int(p))
        except (OverflowError, ValueError):
            return mk_miss("number too large for float arithmetic", line,
                           "trunc", inputs=(args[0],))

    @register("missed", 1)
    def b_missed(interp, args, line):
        return derived("missed", "", line, (args[0],),
                       isinstance(args[0].payload, Miss))

    @register("reasons", 1)
    def b_reasons(interp, args, line):
        p = args[0].payload
        rs = list(p.reasons) if isinstance(p, Miss) else []
        items = [leaf("reason", "", line, r) for r in rs]
        return derived("reasons", "", line, (args[0],), wlist(items))

    @register("note", 2)
    def b_note(interp, args, line):
        label, v = args
        if not isinstance(label.payload, str):
            return mk_miss("note label must be a string, got %s" %
                           show_payload(label.payload), line, "note",
                           inputs=(label, v))
        return derived("note", label.payload, line, (v,), v.payload)

    @register("contains", 2)
    def b_contains(interp, args, line):
        hay, needle = args
        m = _propagate("contains", args, line)
        if m:
            return m
        h, nd = hay.payload, needle.payload
        if isinstance(h, str) and isinstance(nd, str):
            return derived("contains", "", line, (hay, needle),
                           nd in h)
        if isinstance(h, WList):
            for item in h:
                eq = deep_eq(item.payload, nd)
                if eq is True:
                    return derived("contains", "", line,
                                   (hay, needle), True)
            return derived("contains", "", line, (hay, needle), False)
        return mk_miss("contains needs a string or list, got %s" %
                       show_payload(h), line, "contains",
                       inputs=(hay, needle))

    @register("join", 2)
    def b_join(interp, args, line):
        m = _propagate("join", args, line)
        if m:
            return m
        xs, sep = args
        if not isinstance(xs.payload, WList) or not isinstance(sep.payload, str):
            return mk_miss("join needs (list, string)", line, "join",
                           inputs=(xs, sep))
        parts = []
        for x in xs.payload:
            if isinstance(x.payload, Miss):
                return merge_miss("join", "element missed", line, (x, xs))
            if not isinstance(x.payload, str):
                return mk_miss("join: element %s is not a string" %
                               show_payload(x.payload), line, "join",
                               inputs=(x, xs))
            parts.append(x.payload)
        return derived("join", "", line, (xs, sep),
                       sep.payload.join(parts))

    @register("keys", 1)
    def b_keys(interp, args, line):
        m = _propagate("keys", args, line)
        if m:
            return m
        p = args[0].payload
        if not isinstance(p, Record):
            return mk_miss("keys needs a record, got %s" % show_payload(p),
                           line, "keys", inputs=(args[0],))
        items = [leaf("key", "", line, k) for k in sorted(p.fields)]
        return derived("keys", "", line, (args[0],), wlist(items))

    @register("merge", 2)
    def b_merge(interp, args, line):
        m = _propagate("merge", args, line)
        if m:
            return m
        a, b = args
        if not isinstance(a.payload, Record) or not isinstance(b.payload, Record):
            return mk_miss("merge needs two records", line, "merge",
                           inputs=(a, b))
        merged = a.payload.fields.merged_with(b.payload.fields)
        return derived("merge", "", line, (a, b), Record(merged))

    # --- records as data / self-hosting support (v0.5, round 14) --------
    # `get` and `put` make records dynamically inspectable and buildable:
    # a metacircular evaluator needs an environment keyed by names it only
    # knows at runtime. `get(r, n)` has exactly `.field` semantics (same
    # helper, same pass-through, same miss wordings); `put(r, n, v)` is
    # `merge(r, @{n: v})` with a dynamic key.

    @register("get", 2)
    def b_get(interp, args, line):
        r, name = args
        if _is_miss(name):
            return merge_miss("get", "", line, (name, r))
        if not isinstance(name.payload, str):
            return mk_miss("get field name must be a string, got %s" %
                           show_payload(name.payload), line, "get",
                           inputs=(r, name))
        # r's own miss / non-record / absent-field cases are _field's,
        # so get(r, "a") and r.a are indistinguishable, node for node.
        return _field(r, name.payload, line)

    @register("has", 2)
    def b_has(interp, args, line):
        # Presence, not readability: has(r, n) is true even when the field's
        # VALUE is a miss (get would pass that miss through). This is the
        # O(1) form of contains(keys(r), n) — a self-hosted evaluator asks
        # it once per variable reference (v0.6).
        m = _propagate("has", args, line)
        if m:
            return m
        r, name = args
        if not isinstance(r.payload, Record):
            return mk_miss("has needs a record, got %s" %
                           show_payload(r.payload), line, "has",
                           inputs=(r, name))
        if not isinstance(name.payload, str):
            return mk_miss("has field name must be a string, got %s" %
                           show_payload(name.payload), line, "has",
                           inputs=(r, name))
        return derived("has", name.payload, line, (r, name),
                       name.payload in r.payload.fields)

    @register("put", 3)
    def b_put(interp, args, line):
        r, name, v = args
        # v may itself be a miss (records hold misses, like literals do);
        # only r and the key propagate.
        m = _propagate("put", (r, name), line)
        if m:
            return m
        if not isinstance(r.payload, Record):
            return mk_miss("put needs a record, got %s" %
                           show_payload(r.payload), line, "put",
                           inputs=(r, name, v))
        if not isinstance(name.payload, str):
            return mk_miss("put field name must be a string, got %s" %
                           show_payload(name.payload), line, "put",
                           inputs=(r, name, v))
        new_map = r.payload.fields.put(name.payload, v)
        return derived("put", name.payload, line, (r, v), Record(new_map))

    @register("find", 2)
    def b_find(interp, args, line):
        m = _propagate("find", args, line)
        if m:
            return m
        fn, xs = args
        if not isinstance(xs.payload, WList):
            return mk_miss("find needs a list, got %s" %
                           show_payload(xs.payload), line, "find",
                           inputs=(fn, xs))
        for x in xs.payload:
            keep = yield _Call(fn, [x], line)
            if _is_miss(keep):
                return merge_miss("find", "predicate missed", line,
                                  (keep, xs))
            if not isinstance(keep.payload, bool):
                return mk_miss("find predicate must return true/false, got %s"
                               % show_payload(keep.payload), line, "find",
                               inputs=(keep, xs))
            if keep.payload:
                return x  # provenance passes through, like xs[i]
        return mk_miss("find: no element matched", line, "find",
                       inputs=(fn, xs))

    # --- structural types (v0.12) ---------------------------------------
    # `typed` is the whole feature's runtime: `fn f(a: num) {…}` desugars
    # at PARSE time (parser.py `_apply_type_guards`) to a leading
    # `let a = typed(a, "num", "parameter 'a' of f")` — an ordinary
    # builtin call, so a mismatch is an ordinary miss that propagates
    # through the rest of the body exactly like any other bad input
    # (decision 2). `shapeof`/`matches` are the same check exposed
    # directly for programs that want to test structure themselves.

    @register("typed", 3)
    def b_typed(interp, args, line):
        m = _propagate("typed", args, line)
        if m:
            return m
        value, spec, label = args
        if not isinstance(label.payload, str):
            return mk_miss("typed label must be a string, got %s" %
                           show_payload(label.payload), line, "typed",
                           inputs=(value, spec, label))
        if not _spec_ok(spec.payload):
            # `_spec_ok`, not a bare isinstance: a record spec whose own
            # FIELDS are not specs is just as unusable as a numeric one,
            # and used to crash `_type_match` instead of missing here
            # (round 335).
            return mk_miss("typed spec must be a type name or a shape, "
                           "got %s" % show_payload(spec.payload), line,
                           "typed", inputs=(value, spec, label))
        ok, desc = _type_match(value.payload, spec.payload)
        if ok:
            return value                    # pass-through: no new node
        return mk_miss("%s expected %s, got %s" %
                       (label.payload, desc, _kind(value.payload)), line,
                       "typed", label.payload, inputs=(value,))

    @register("matches", 2)
    def b_matches(interp, args, line):
        # Total, like `missed`: never itself a miss, even on a miss or a
        # malformed spec (both simply do not match).
        value, spec = args
        if _is_miss(value) or _is_miss(spec) or not _spec_ok(spec.payload):
            # `_spec_ok` (round 335): a malformed spec "simply does not
            # match" at every depth, not only at the top level — see this
            # branch's own comment above and `_spec_ok`'s docstring.
            return derived("matches", "", line, args, False)
        ok, _ = _type_match(value.payload, spec.payload)
        return derived("matches", "", line, args, ok)

    @register("shapeof", 1)
    def b_shapeof(interp, args, line):
        # Total: works on misses too (returns "miss"), like `missed`.
        v = args[0]
        return derived("shapeof", "", line, args, _kind(v.payload))

    # --- AI-native primitives: `guess` (v0.15) ---------------------------
    # `guess(value, confidence, source)` wraps an otherwise-ordinary value
    # as UNCOMMITTED: "here is an answer, but not a certain one." Mirrors
    # `miss` on purpose (see values.py's `Guess` docstring) — where a miss
    # is absence with a reason, a guess is presence with a confidence.
    # Binary/unary ops propagate a Guess operand automatically
    # (`Interpreter._guess_binop`/`_unary`, values.py `Guess`): the result
    # is itself a Guess at the WEAKEST-LINK (minimum) confidence of every
    # Guess operand involved, unless the underlying computation is a
    # genuine type error, which stays an ordinary miss (a Guess vouches
    # for confidence, not validity). `sure(v, threshold)` is the one way
    # to leave this world: it commits to a threshold and either hands back
    # the plain underlying value (confidence high enough — pass-through,
    # no new node, same convention as a passing `typed`) or a miss naming
    # the shortfall. A non-Guess value is always "sure": `sure` is a
    # universal escape hatch, not a guess-only operation, so ordinary code
    # can call it defensively without checking `is_guess` first.
    #
    # Deliberately shallow, same discipline as v0.12-14: indexing/field
    # access/calling a Guess-wrapped container or function is NOT
    # unwrapped automatically — `_index`/`_field`/call dispatch simply
    # don't recognize a Guess as a list/record/callable, so they produce
    # an ordinary "cannot index/access/call" miss via `show_payload`,
    # for free, with zero code added to those paths. `and`/`or`/`if`
    # likewise require a definite `true`/`false` (`_logic_left`,
    # `_logic_right`, `_if_bad` are unmodified) — a Guess must be resolved
    # with `sure()` before it can decide control flow. Only the two places
    # a v0.15 value can flow through *without* being resolved are the
    # arithmetic/comparison/logical-negation operators themselves.

    @register("guess", 3)
    def b_guess(interp, args, line):
        m = _propagate("guess", args, line)
        if m:
            return m
        value, conf, source = args
        c = conf.payload
        if not _is_num(c) or not (0 <= c <= 1):
            return mk_miss("guess confidence must be a number between 0 "
                           "and 1, got %s" % show_payload(c), line, "guess",
                           inputs=(value, conf, source))
        if not isinstance(source.payload, str):
            return mk_miss("guess source must be a string, got %s" %
                           show_payload(source.payload), line, "guess",
                           inputs=(value, conf, source))
        if isinstance(value.payload, Guess):
            # flatten rather than nest, same discipline as merge_miss
            # never wrapping a Miss around a Miss
            g = value.payload
            confidence = min(g.confidence, c)
            sources = g.sources + (source.payload,)
            node = g.node
        else:
            confidence, sources, node = c, (source.payload,), value
        return Prov("guess", source.payload, line, _slot((value, conf, source)),
                   _LAZY, Guess(node, confidence, sources))

    @register("is_guess", 1)
    def b_is_guess(interp, args, line):
        # Total, like `matches`/`missed`: never itself a miss.
        return derived("is_guess", "", line, args,
                       isinstance(args[0].payload, Guess))

    @register("confidence", 1)
    def b_confidence(interp, args, line):
        m = _propagate("confidence", args, line)
        if m:
            return m
        v = args[0]
        if not isinstance(v.payload, Guess):
            return mk_miss("confidence: not a guess, got %s" %
                           show_payload(v.payload), line, "confidence",
                           inputs=(v,))
        return derived("confidence", "", line, (v,), v.payload.confidence)

    @register("sure", 2)
    def b_sure(interp, args, line):
        m = _propagate("sure", args, line)
        if m:
            return m
        v, threshold = args
        t = threshold.payload
        if not _is_num(t) or not (0 <= t <= 1):
            return mk_miss("sure threshold must be a number between 0 "
                           "and 1, got %s" % show_payload(t), line, "sure",
                           inputs=(v, threshold))
        if not isinstance(v.payload, Guess):
            return v      # already certain: sure() is a no-op escape hatch
        g = v.payload
        if g.confidence >= t:
            return g.node   # pass-through: no new node, mirrors `typed`
        return mk_miss("guess confidence %.2g below threshold %.2g (%s)" %
                       (g.confidence, t, ", ".join(g.sources)), line, "sure",
                       inputs=(v,))

    # --- provenance as data (round 4) -----------------------------------
    # These are total: they work on misses (that is the point) and accept
    # either a value or `why value`.

    @register("steps", (1, 2))
    def b_steps(interp, args, line):
        root = _history_root(args[0])
        if len(args) == 2:
            pat = args[1]
            if _is_miss(pat):
                return merge_miss("steps", "", line, (pat, args[0]))
            if not isinstance(pat.payload, str):
                return mk_miss("steps needs a string step name, got %s" %
                               show_payload(pat.payload), line, "steps",
                               inputs=(root, pat))
            items = [_step_record(n, d, line) for n, d in walk_steps(root)
                     if matches_step(n, pat.payload)]
            return derived("steps", "%d steps matching %s" %
                           (len(items), pat.payload), line, (root, pat),
                           wlist(items))
        items = [_step_record(n, d, line) for n, d in walk_steps(root)]
        return derived("steps", "%d steps" % len(items), line, (root,),
                       wlist(items))

    @register("at", 2)
    def b_at(interp, args, line):
        v, pat = args
        if _is_miss(pat):
            return merge_miss("at", "", line, (pat, v))
        if not isinstance(pat.payload, str):
            return mk_miss("at needs a string step name, got %s" %
                           show_payload(pat.payload), line, "at",
                           inputs=(v, pat))
        root = _history_root(v)
        node = find_step(root, pat.payload)
        if node is None:
            return mk_miss("no step named '%s' in the history of %s" %
                           (pat.payload, root.show), line, "at",
                           inputs=(root, pat))
        return node

    @register("blame", 1)
    def b_blame(interp, args, line):
        root = _history_root(args[0])
        items = [_step_record(n, d, line) for n, d in walk_steps(root)
                 if is_origin_miss(n)]
        return derived("blame", "%d origins" % len(items), line, (root,),
                       wlist(items))

    def _diverge_records(ra, rb, line, which=None):
        depth_a = dict((id(n), d) for n, d in walk_steps(ra))
        depth_b = dict((id(n), d) for n, d in walk_steps(rb))
        items = []
        for na, nb, kind in diverge(ra, rb):
            fields = {
                "kind": leaf("diverge", "kind", line, kind),
                "a": _step_record(na, depth_a.get(id(na), 0), line),
                "b": _step_record(nb, depth_b.get(id(nb), 0), line),
            }
            if which is not None:
                fields["which"] = leaf("diverge", "which", line, which)
            items.append(derived("diverge", kind, line, (na, nb),
                                 Record(fields)))
        return items

    @register("diverge", (1, 2))
    def b_diverge(interp, args, line):
        if len(args) == 2:
            ra, rb = _history_root(args[0]), _history_root(args[1])
            items = _diverge_records(ra, rb, line)
            return derived("diverge", "%d origins" % len(items), line,
                           (ra, rb), wlist(items))
        # v0.4, n-way: diverge([r0, r1, ...]) compares every run with the
        # first; each record says `which` run (its index) diverged.
        runs = args[0]
        if _is_miss(runs):
            return merge_miss("diverge", "", line, (runs,))
        if not isinstance(runs.value, WList):
            return mk_miss("diverge needs two values or a list of runs, got %s"
                           % show_payload(runs.value), line, "diverge",
                           inputs=(runs,))
        items = []
        if len(runs.value):
            ra = _history_root(runs.value[0])
            for i in range(1, len(runs.value)):
                rb = _history_root(runs.value[i])
                items.extend(_diverge_records(ra, rb, line, which=i))
        return derived("diverge", "%d origins across %d runs" %
                       (len(items), len(runs.value)), line, (runs,),
                       wlist(items))

    @register("contrast", (1, 2))
    def b_contrast(interp, args, line):
        """The two histories side by side, down to each origin of
        divergence (v0.4). A string, so it can be printed or checked.
        v0.6, n-way: contrast([r0, r1, ...]) renders each run against the
        first, one block per DIVERGING run (agreeing runs are skipped);
        'no divergence' when every run agrees (or there are <2 runs)."""
        if len(args) == 2:
            ra, rb = _history_root(args[0]), _history_root(args[1])
            return derived("contrast", "", line, (ra, rb),
                           render_contrast(ra, rb))
        runs = args[0]
        if _is_miss(runs):
            return merge_miss("contrast", "", line, (runs,))
        if not isinstance(runs.value, WList):
            return mk_miss("contrast needs two values or a list of runs, "
                           "got %s" % show_payload(runs.value), line,
                           "contrast", inputs=(runs,))
        blocks = []
        if len(runs.value):
            ra = _history_root(runs.value[0])
            for i in range(1, len(runs.value)):
                rb = _history_root(runs.value[i])
                text = render_contrast(ra, rb)
                if text != "no divergence":
                    blocks.append("run %d vs run 0:\n%s" % (i, text))
        return derived("contrast", "%d runs" % len(runs.value), line,
                       (runs,), "\n\n".join(blocks) or "no divergence")

    return table

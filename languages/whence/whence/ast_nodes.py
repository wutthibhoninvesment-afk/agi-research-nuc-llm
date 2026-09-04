"""AST node classes for Whence. Plain classes; every node carries its line."""


class Node(object):
    """`fast` (v0.4) caches the node's compiled closure (None = not yet
    compiled, False = contains a call, so it must run on the trampoline);
    `const` caches the shared value of a literal node; `fdepth` is the
    height of the compiled closure tree below this node. `direct` (v0.9)
    caches the node's DIRECT closure — one that may contain calls and
    recurses on the host stack under a frame budget (None = not yet
    compiled, False = too tall, trampoline only); `cdepth` is the number of
    direct-closure frames on the deepest path from this node to a call
    (0 for call-free nodes), i.e. the host frames a direct evaluation of
    this node needs before the next `_call_direct` frame. `entry` (v0.11)
    caches, on a function BODY, the pair `(bd, cost)` a direct call
    needs: the body's evaluator (fast or direct closure, False when
    it cannot compile) and the host frames it is charged."""
    __slots__ = ("line", "fast", "const", "fdepth", "direct", "cdepth",
                 "entry")

    def __init__(self, line):
        self.line = line
        self.fast = None
        self.const = None
        self.fdepth = 0
        self.direct = None
        self.cdepth = 0
        self.entry = None


#: v0.47 (round 482), decision 60. A node's repr descends this many
#: levels and lists this many children per level before it says `...`.
#: An AST node is reachable from a caller by a PUBLIC path —
#: `run().vars["f"].payload.body` — so it is a surface under decision 58's
#: rule, and until this version its repr recursed over the WHOLE subtree
#: with no cut of any kind: `reprsweep.py` measured 500 characters for the
#: five-line `loop` in its own probe, and the bound is the program's size.
#:
#: The caps are DEPTH and BREADTH rather than a character cut because that
#: is what this implementation already does to a value one layer up —
#: `values.SHOW_NEST` renders a too-deep list as `[…]` and `_show` takes
#: `head(6)` of a long one. A structural cut keeps the SHAPE readable,
#: which is the whole reason to print an AST node; a character cut would
#: leave a node's repr ending mid-identifier. `values.REPR_CAP` is still
#: applied last, as the backstop that makes "bounded" a property a test
#: can check rather than an argument about the caps being enough.
#:
#: Nothing in the tree consumed the unbounded form. `test_parser_
#: differential.py` is the one suite that reprs a parse tree, and it reprs
#: `canon_host(...)`'s TUPLES, not these nodes — checked before changing
#: this, because a repr that a differential test uses as a canonical
#: serialization must not be silently truncated.
REPR_NEST = 3
REPR_BREADTH = 6


def _node_field(v, depth):
    """One field of a node's repr, cut by depth and breadth."""
    if isinstance(v, Node):
        if depth >= REPR_NEST:
            return type(v).__name__ + "(…)"
        return v._repr_at(depth + 1)
    if isinstance(v, list):
        if depth >= REPR_NEST:
            return "[…]" if v else "[]"
        head = v[:REPR_BREADTH]
        return "[" + ", ".join(_node_field(e, depth + 1) for e in head) + \
            (", …" if len(head) < len(v) else "") + "]"
    if isinstance(v, tuple):
        return "(" + ", ".join(_node_field(e, depth + 1) for e in v) + ")"
    return repr(v)


def _simple(name, fields):
    slots = tuple(fields)

    def __init__(self, line, *args):
        Node.__init__(self, line)
        if len(args) != len(slots):
            raise TypeError("%s expects %d fields" % (name, len(slots)))
        for f, a in zip(slots, args):
            setattr(self, f, a)

    def _repr_at(self, depth):
        parts = ", ".join("%s=%s" % (f, _node_field(getattr(self, f), depth))
                          for f in slots)
        return "%s(%s)" % (name, parts)

    def __repr__(self):
        # v0.48 (round 488), decision 62: through `values._cap`, not a
        # third hand-written copy of the same three lines. This copy was
        # CORRECT — the two that were missing entirely were `Prov`/
        # `MergedProv` and `Env` — but a rule enforced in three places is
        # a rule that can be right in two of them, which is exactly what
        # happened.
        from whence.values import _cap
        return _cap(self._repr_at(0))

    return type(name, (Node,), {
        "__slots__": slots, "__init__": __init__, "__repr__": __repr__,
        "_repr_at": _repr_at})


Num = _simple("Num", ["value"])
Str = _simple("Str", ["value"])
BoolLit = _simple("BoolLit", ["value"])
NameRef = _simple("NameRef", ["name"])
ListLit = _simple("ListLit", ["items"])
RecordLit = _simple("RecordLit", ["pairs"])          # [(name, expr)]
MissLit = _simple("MissLit", ["reason"])             # reason: expr
Unary = _simple("Unary", ["op", "operand"])          # '-', 'not'
Why = _simple("Why", ["operand"])
Snip = _simple("Snip", ["operand"])
Binary = _simple("Binary", ["op", "left", "right"])  # arith/cmp/and/or
Rescue = _simple("Rescue", ["left", "right"])
Call = _simple("Call", ["fn", "args", "tail"])       # tail: set by parser.mark_tails
Index = _simple("Index", ["obj", "index"])
FieldAccess = _simple("FieldAccess", ["obj", "name"])
If = _simple("If", ["cond", "then", "otherwise"])    # otherwise: Block or If
FnExpr = _simple("FnExpr", ["params", "body", "ret_type", "param_call_fact",
                            "param_types"])
# anonymous fn; param_call_fact: None, or (effects_scope, params_tuple,
# frozenset_of_directly_called_param_names) — set by parser.py (v0.14.10,
# round 302), same shape `Parser.param_call_scopes` stores for a NAMED fn
# (v0.14.9, round 300), carried on the node itself since an anonymous fn has
# no name to key a scope-stack dict by until its enclosing `let` sees it.
Block = _simple("Block", ["stmts", "tail_alias_tag", "tail_param_name"])
# tail_alias_tag: set by parser.block (v0.14.3). tail_param_name: set by
# parser.block (v0.14.12, round 308) — None, or the name of one of the
# CURRENTLY open fn's own params (directly, or via a same-body `let`-rename
# chain — see `Parser._tail_return_param_name`) that this block's own tail
# statement is a bare `NameRef` to. Lets `Parser._resolve_return_param_fact`
# learn, once, at a fn's own definition, "does calling this fn just hand
# back one of its own params unchanged" — the fact a CALL SITE needs to
# propagate an argument's own effect tag across the RETURN boundary.
Let = _simple("Let", ["name", "expr"])
FnDef = _simple("FnDef", ["name", "params", "body", "ret_type",
                          "param_types"])
# ret_type: None, or the spec expr `parser._type_spec_expr` builds for a
# `-> Type` annotation (an A.Str for a primitive tag, an A.NameRef for a
# shape) — resolved to a runtime spec ONCE per Closure at creation time
# (interp.py `_closure_ret`), never re-parsed or re-walked per call.
# param_types (v0.19, round 344): None when no parameter is annotated, else a
# tuple of `(index, param_name, spec_expr, label)` — the SAME spec-expr shape
# `ret_type` uses, resolved by the SAME `_closure_spec` at the SAME moment
# (interp.py `_closure_params`). Before v0.19 a parameter annotation was
# erased into a `let p = typed(p, spec, label)` statement PREPENDED to the
# body, which resolved its spec in the CALL env on every call; carrying it on
# the node instead is what lets a parameter contract and a return contract
# mean the same thing (SPEC decision 29).
Check = _simple("Check", ["label", "expr"])
ExprStmt = _simple("ExprStmt", ["expr"])
Program = _simple("Program", ["stmts"])

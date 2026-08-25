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


def _simple(name, fields):
    slots = tuple(fields)

    def __init__(self, line, *args):
        Node.__init__(self, line)
        if len(args) != len(slots):
            raise TypeError("%s expects %d fields" % (name, len(slots)))
        for f, a in zip(slots, args):
            setattr(self, f, a)

    def __repr__(self):
        parts = ", ".join("%s=%r" % (f, getattr(self, f)) for f in slots)
        return "%s(%s)" % (name, parts)

    return type(name, (Node,), {
        "__slots__": slots, "__init__": __init__, "__repr__": __repr__})


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
FnExpr = _simple("FnExpr", ["params", "body"])       # anonymous fn
Block = _simple("Block", ["stmts"])
Let = _simple("Let", ["name", "expr"])
FnDef = _simple("FnDef", ["name", "params", "body"])
Check = _simple("Check", ["label", "expr"])
ExprStmt = _simple("ExprStmt", ["expr"])
Program = _simple("Program", ["stmts"])

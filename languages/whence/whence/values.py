"""Runtime values for Whence.

A runtime value IS its provenance node (v0.4). `Prov(op, detail, line,
inputs, show, value)` is a node in an immutable DAG: `inputs` are the values
this one was derived from, `value` (alias `payload`) is the payload, `show`
is a lazily rendered snapshot. `Value` is another name for the same class and
`v.prov` is `v` itself, so code written against the v0.1-v0.3 shape
(`v.payload`, `v.prov.inputs`) keeps reading naturally - but a derived value
now costs one object, not two, and every node of the history is a real,
re-usable value (`at(x, "let a")` is time travel for free).
"""

import inspect as _inspect

SHOW_LIMIT = 40


class WList(object):
    """An immutable Whence list: a length-bounded view over a shared,
    append-only Python buffer.

    Whence values never change, so two lists where one is a prefix of the
    other can share storage. `push(xs, x)` appends in place when `xs` is the
    buffer's current tip (nobody has grown it past `xs.n`) and copies
    otherwise; `xs + ys` extends the same way. Growing a list linearly
    (push inside a fold) is therefore O(1) amortised per step and O(n) memory
    *even though every intermediate list stays alive in the history* — the
    v0.2 O(n^2) retention problem disappears without dropping any history.
    Non-linear use (pushing twice onto the same list) still copies, so the
    old value can never observe the new elements: a view only ever reads
    buf[:n].
    """
    __slots__ = ("buf", "n")

    def __init__(self, buf, n=None):
        self.buf = buf
        self.n = len(buf) if n is None else n

    def __len__(self):
        return self.n

    def __iter__(self):
        buf, n = self.buf, self.n
        i = 0
        while i < n:
            yield buf[i]
            i += 1

    def __getitem__(self, i):
        if i < 0 or i >= self.n:
            raise IndexError(i)
        return self.buf[i]

    def to_list(self):
        return self.buf[:self.n]

    def head(self, k):
        return self.buf[:min(k, self.n)]

    def is_tip(self):
        return len(self.buf) == self.n

    def push(self, x):
        if len(self.buf) == self.n:
            self.buf.append(x)
            return WList(self.buf, self.n + 1)
        return WList(self.buf[:self.n] + [x])

    def concat(self, other):
        if len(self.buf) == self.n:
            self.buf.extend(other)
            return WList(self.buf, len(self.buf))
        return WList(self.buf[:self.n] + list(other))

    def shares_buffer_with(self, other):
        return self.buf is other.buf

    def __eq__(self, other):
        if isinstance(other, WList):
            other = other.to_list()
        if isinstance(other, list):
            return self.to_list() == other
        return NotImplemented

    def __ne__(self, other):
        eq = self.__eq__(other)
        return eq if eq is NotImplemented else not eq

    __hash__ = None

    def __repr__(self):
        return "WList(%r)" % self.to_list()


def wlist(items=()):
    """Fresh Whence list from an iterable of Values."""
    return WList(list(items))


_LAZY = object()


class Prov(object):
    """A Whence value and its derivation, in one object.

    `value`/`payload` name the same slot; `prov` is the node itself. Values
    are immutable, so the node that records how a value was made can *be*
    the value: retaining full history costs no extra objects.
    """
    __slots__ = ("op", "detail", "line", "_ins", "_show", "value")

    # count > 1 means "this node stands for `count` merged steps" (a tail
    # loop or a run of identical `if` decisions). Almost every node has
    # count 1, so it is a class attribute here and a real slot only on
    # MergedProv (v0.6: −8 bytes on every ordinary node).
    count = 1

    def __init__(self, op, detail, line, ins=(), show=_LAZY, value=None):
        # v0.10: the constructor is the raw slot store — six assignments,
        # nothing else. `ins` is stored as given: a tuple of input nodes,
        # or ONE input node unboxed (v0.6: no 1-element tuple, ~56 bytes
        # saved on every 1-input node; `inputs` re-wraps on read, query
        # time only). A 1-tuple is also accepted (it is simply not unboxed).
        # Normalisation — lists, unboxing — lives in `derived`/`leaf`/
        # `mk_miss`/`merge_miss`; the hot paths call `Prov(...)` directly
        # with the slot already in its final shape. 2.77 M nodes for one
        # meta.lang run: the two tests removed here were 12–18 % of the
        # constructor (214 → 187 ns, values microbench, round 108).
        self.op = op
        self.detail = detail
        self.line = line
        self._ins = ins
        self._show = show
        self.value = value

    @property
    def inputs(self):
        ins = self._ins
        return ins if type(ins) is tuple else (ins,)

    @property
    def prov(self):
        return self

    # v0.3: the snapshot string is computed on first use, not at creation.
    # Values are immutable and retained (v0.2), so rendering later gives the
    # same text — and eager snapshots were 2/3 of all evaluation time.
    @property
    def show(self):
        if self._show is _LAZY:
            self._show = show_payload(self.value)
        return self._show

    @show.setter
    def show(self, text):
        self._show = text

    def label(self):
        """'op detail' — the name a step is addressed by in `at`/`steps`."""
        if self.detail:
            return (self.op + " " + self.detail) if self.op else self.detail
        return self.op

    def __repr__(self):
        return "Prov(%r, %r, line=%r, %d inputs, value=%s)" % (
            self.op, self.detail, self.line, len(self.inputs), self.show)


# `payload` is a second name for the `value` slot: a member descriptor is
# bound to a slot offset, not to a name, so this alias costs nothing.
Prov.payload = Prov.__dict__["value"]
Value = Prov


class MergedProv(Prov):
    """A provenance node standing for `count` merged steps: the single
    `call f ×N` node of a tail loop, or one `if … ×N` run of identical
    branch decisions. Only these carry a real `count` slot."""
    __slots__ = ("count",)

    def __init__(self, op, detail, line, ins=(), show=_LAZY, value=None,
                 count=1):
        # v0.10: one frame, not two (388 → 215 ns); same raw `ins` contract
        # as Prov. Only runs of ≥2 merged steps are built as MergedProv —
        # a run of one decision is a plain Prov of the same shape (count
        # is 1 either way and nothing renders differently; see _finish_call)
        self.op = op
        self.detail = detail
        self.line = line
        self._ins = ins
        self._show = show
        self.value = value
        self.count = count


class Miss(object):
    """A failed computation. Carries deduped, ordered reason strings."""
    __slots__ = ("reasons",)

    def __init__(self, reasons):
        seen = set()
        out = []
        for r in reasons:
            if r not in seen:
                seen.add(r)
                out.append(r)
        self.reasons = tuple(out)


class Record(object):
    __slots__ = ("fields",)

    def __init__(self, fields):
        self.fields = dict(fields)  # str -> Value


class Closure(object):
    __slots__ = ("name", "params", "body", "env", "ret_spec", "ret_label")

    def __init__(self, name, params, body, env, ret_spec=None, ret_label=None):
        self.name = name          # None for anonymous fns
        self.params = params
        self.body = body
        self.env = env
        # v0.13: a `-> Type` return annotation's resolved runtime spec (a
        # primitive tag str or a shape's Record payload) + message label
        # ("return value of f"), computed ONCE at closure creation
        # (interp.py `_closure_ret`) — None, None for the common untyped
        # case, so an untyped closure pays nothing beyond two extra slots.
        self.ret_spec = ret_spec
        self.ret_label = ret_label


class Builtin(object):
    __slots__ = ("name", "arity", "fn", "is_gen")

    def __init__(self, name, arity, fn):
        self.name = name
        self.arity = arity        # int, or (min, max) tuple, or None for any
        self.fn = fn              # fn(interp, args, line) -> Value
        # a builtin that calls back into Whence (map, fold, …) is a generator
        # function; plain ones can be dispatched inline with no trampoline
        # frame at all (v0.6)
        self.is_gen = _inspect.isgeneratorfunction(fn)


class Explanation(object):
    """Payload of `why x`: holds the provenance root of x."""
    __slots__ = ("root",)

    def __init__(self, root):
        self.root = root


def _quote(s, limit):
    out = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    if limit is not None and len(out) > limit:
        out = out[:limit] + "…"
    return '"%s"' % out


SHOW_NEST = 3   # containers nested deeper than this render as […] / @{…}


def show_payload(p, limit=SHOW_LIMIT, nest=0):
    """Short one-line snapshot of a payload, truncated to `limit` chars.
    Nesting is capped so snapshotting a deeply nested list is O(1), not
    O(depth) (a 2500-deep list would otherwise recurse 2500 frames)."""
    s = _show(p, limit, nest)
    # Strings are already truncated (with their closing quote) by _quote;
    # only containers need the outer cut.
    if limit is not None and not isinstance(p, str) and len(s) > limit + 2:
        s = s[:limit] + "…"
    return s


def _show(p, limit, nest):
    if isinstance(p, bool):
        return "true" if p else "false"
    if isinstance(p, (int, float)):
        return repr(p)
    if isinstance(p, str):
        return _quote(p, limit)
    # limit=None means "full rendering": show every element and field.
    if isinstance(p, WList):
        if nest >= SHOW_NEST:
            return "[…]" if len(p) else "[]"
        head = p.to_list() if limit is None else p.head(6)
        return "[" + ", ".join(
            show_payload(e.payload, limit and 12, nest + 1) for e in head) + \
            (", …" if len(head) < len(p) else "") + "]"
    if isinstance(p, Record):
        if nest >= SHOW_NEST:
            return "@{…}" if p.fields else "@{}"
        items = sorted(p.fields.items())
        head = items if limit is None else items[:4]
        return "@{" + ", ".join(
            "%s: %s" % (k, show_payload(v.payload, limit and 12, nest + 1))
            for k, v in head) + \
            (", …" if len(head) < len(items) else "") + "}"
    if isinstance(p, Miss):
        return "miss"
    if isinstance(p, Closure):
        return "<fn %s>" % p.name if p.name else "<fn>"
    if isinstance(p, Builtin):
        return "<builtin %s>" % p.name
    if isinstance(p, Explanation):
        return "<why>"
    return "<?>"


def full_show(p):
    """Full rendering used by print(): misses list reasons, explanations render."""
    if isinstance(p, Miss):
        return "miss: " + "; ".join(p.reasons)
    if isinstance(p, Explanation):
        return render_why(p.root)
    if isinstance(p, str):
        return p                      # print of a string is the raw string
    if isinstance(p, WList):
        return "[" + ", ".join(show_payload(e.payload, None) for e in p) + "]"
    if isinstance(p, Record):
        items = sorted(p.fields.items())
        return "@{" + ", ".join(
            "%s: %s" % (k, show_payload(v.payload, None)) for k, v in items) + "}"
    return show_payload(p, None)


def leaf(op, detail, line, payload):
    return Prov(op, detail, line, (), _LAZY, payload)


def _slot(inputs):
    """The raw `_ins` slot for an inputs sequence: () / one node / tuple."""
    if type(inputs) is not tuple:
        inputs = tuple(inputs)
    return inputs[0] if len(inputs) == 1 else inputs


def derived(op, detail, line, inputs, payload):
    """A node derived from `inputs` (any sequence of nodes). The general
    constructor; hot paths build `Prov(...)` directly with the slot shape
    (v0.10) — this wrapper is one more Python frame per node."""
    return Prov(op, detail, line, _slot(inputs), _LAZY, payload)


def mk_miss(reason, line, op, detail="", inputs=()):
    """A fresh miss with a single reason (line is baked into the reason).
    The reason doubles as the prov node's detail so why-trees show it inline."""
    m = Miss([reason + " (line %d)" % line])
    return Prov(op, detail if detail else reason, line, _slot(inputs), "miss", m)


def merge_miss(op, detail, line, operands):
    """Propagate misses through an operation: merge all operand reasons."""
    reasons = []
    for v in operands:
        if isinstance(v.payload, Miss):
            reasons.extend(v.payload.reasons)
    m = Miss(reasons)
    return Prov(op, detail, line, _slot(operands), "miss", m)


def is_origin_miss(node):
    """A node that *created* a miss: its value is a miss but no input's is."""
    if not isinstance(node.value, Miss):
        return False
    return not any(isinstance(i.value, Miss) for i in node.inputs)


def walk_steps(root):
    """Yield (node, depth) in pre-order (root first), each shared node once."""
    seen = set()
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        yield node, depth
        for ch in reversed(node.inputs):
            stack.append((ch, depth + 1))


def matches_step(node, pattern):
    """Does `pattern` name this step? Matches the label ('let a'), the op
    ('call') or the detail ('year 1'). A merged mutual-recursion node
    (`call even/odd`, v0.3) also answers to any member: 'call even' and
    'call odd' both match (v0.4)."""
    if pattern in (node.label(), node.op, node.detail):
        return True
    if node.count > 1 and node.op == "call" and "/" in node.detail:
        members = node.detail.split("/")
        return pattern in members or pattern[5:] in members and \
            pattern.startswith("call ")
    return False


def find_step(root, pattern):
    """Breadth-first (most recent history first) search for a node whose
    label, op or detail equals `pattern`. Returns the node or None."""
    seen = set()
    queue = [root]
    i = 0
    while i < len(queue):
        node = queue[i]
        i += 1
        if id(node) in seen:
            continue
        seen.add(id(node))
        if matches_step(node, pattern):
            return node
        queue.extend(node.inputs)
    return None


def render_why(root, max_depth=10, max_nodes=200):
    """Render a provenance DAG as an indented tree.

    Shared nodes are printed once and marked on re-encounter; depth and node
    count are capped so deep recursive histories stay readable.
    """
    lines = []
    seen = set()
    budget = [max_nodes]

    def label(n):
        head = n.show if n.show else "?"
        loc = "  (line %d)" % n.line if n.line else ""
        times = " ×%d" % n.count if n.count > 1 else ""
        return "%s ← %s%s%s" % (head, n.label(), times, loc)

    def walk(node, prefix, child_prefix, depth):
        if budget[0] <= 0:
            return
        budget[0] -= 1
        repeat = id(node) in seen and bool(node.inputs)
        seen.add(id(node))
        lines.append(prefix + label(node) + ("  ⟲ shown above" if repeat else ""))
        if repeat:
            return
        if not node.inputs:
            return
        if depth >= max_depth:
            lines.append(child_prefix + "└─ …")
            return
        n = len(node.inputs)
        for i, ch in enumerate(node.inputs):
            last = (i == n - 1)
            walk(ch,
                 child_prefix + ("└─ " if last else "├─ "),
                 child_prefix + ("   " if last else "│  "),
                 depth + 1)

    walk(root, "", "", 0)
    if budget[0] <= 0:
        lines.append("… (tree truncated at %d nodes)" % max_nodes)
    return "\n".join(lines)


def same_payload(x, y, memo=None):
    """Do two historic payloads agree? Misses agree when their reasons do;
    structural values use deep_eq; incomparable payloads (functions,
    explanations) agree when their snapshots do. The same object agrees
    with itself (v0.4.1: `diverge(v, v)` and shared inputs are O(1) here)."""
    if x is y:
        return True
    if isinstance(x, Miss) or isinstance(y, Miss):
        return isinstance(x, Miss) and isinstance(y, Miss) and \
            x.reasons == y.reasons
    from .interp import deep_eq   # local import: interp imports this module
    eq = deep_eq(x, y, memo)
    if eq is None:
        return show_payload(x) == show_payload(y)
    return eq


# Steps whose detail is a human-chosen name rather than a computation: two
# histories that differ only in what a value was *called* have not diverged.
NAMING_OPS = frozenset(["let", "note", "snipped"])


def diverge(a, b):
    """Origins of difference between two histories (v0.3).

    Walks the two DAGs in lockstep, pairing each step of `a` with the
    corresponding step of `b`. A pair is *the same* when its ops, details
    (except for naming steps: `let x` vs `let y` is not a divergence, see
    NAMING_OPS) and values agree and all its input pairs are the same. A pair is an *origin*
    of divergence when it differs but every input pair is the same (kind
    "value": same step, different result — e.g. a literal that changed), or
    when the two histories have different shapes there (kind "step": ops or
    input counts differ — e.g. one run took the other branch). Pairs that
    differ only because an input differs are not origins: the difference is
    upstream. Returns [(node_a, node_b, kind)], innermost origins first.
    Iterative and memoised on node pairs, so shared and deep histories are
    walked once and never touch the host stack. A node paired with itself
    is the same by identity (its whole sub-DAG is skipped), and payload
    comparisons share one pair memo, so a deep value reachable from many
    nodes is compared once (v0.4.1: `diverge(nest(800), nest(800))` went
    from 26s to linear).
    """
    memo = {}
    vals = {}
    origins = []
    stack = [(a, b, False)]
    while stack:
        na, nb, expanded = stack.pop()
        key = (id(na), id(nb))
        if key in memo:
            continue
        if na is nb:
            memo[key] = True
            continue
        if not expanded:
            if na.op != nb.op or len(na.inputs) != len(nb.inputs):
                memo[key] = False
                origins.append((na, nb, "step"))
                continue
            stack.append((na, nb, True))
            for x, y in zip(na.inputs, nb.inputs):
                if (id(x), id(y)) not in memo:
                    stack.append((x, y, False))
            continue
        inputs_same = all(memo.get((id(x), id(y)), False)
                          for x, y in zip(na.inputs, nb.inputs))
        if not inputs_same:
            memo[key] = False          # the divergence is upstream
        elif na.count != nb.count or (na.op not in NAMING_OPS and
                                       na.detail != nb.detail):
            memo[key] = False
            origins.append((na, nb, "step"))
        elif not same_payload(na.value, nb.value, vals):
            memo[key] = False
            origins.append((na, nb, "value"))
        else:
            memo[key] = True
    return origins


def _pair_path(ra, rb, target):
    """Path of node pairs from the root pair to `target` (an (na, nb) pair
    reached by lockstep descent), root first. Breadth-first over pairs, so
    the shortest lockstep path is returned; None if unreachable."""
    parents = {(id(ra), id(rb)): None}
    queue = [(ra, rb)]
    i = 0
    while i < len(queue):
        na, nb = queue[i]
        i += 1
        if na is target[0] and nb is target[1]:
            path = []
            cur = (na, nb)
            while cur is not None:
                path.append(cur)
                cur = parents[(id(cur[0]), id(cur[1]))]
            path.reverse()
            return path
        for x, y in zip(na.inputs, nb.inputs):
            key = (id(x), id(y))
            if key not in parents:
                parents[key] = (na, nb)
                queue.append((x, y))
    return None


def _step_line(n):
    loc = "  (line %d)" % n.line if n.line else ""
    times = " ×%d" % n.count if n.count > 1 else ""
    return "%s ← %s%s%s" % (n.show if n.show else "?", n.label(), times, loc)


def render_contrast(ra, rb, width=None):
    """Two histories side by side (v0.4): for every origin of divergence,
    the lockstep path from the roots down to the origin, one pair per line,
    `a` in the left column and `b` in the right, the origin marked with ▶."""
    origins = diverge(ra, rb)
    if not origins:
        return "no divergence"
    blocks = []
    for k, (na, nb, kind) in enumerate(origins):
        path = _pair_path(ra, rb, (na, nb)) or [(na, nb)]
        last = len(path) - 1
        left = ["%s%s%s" % ("  " * j, "▶ " if j == last else "  ",
                            _step_line(x)) for j, (x, _) in enumerate(path)]
        right = ["%s%s%s" % ("  " * j, "▶ " if j == last else "  ",
                             _step_line(y)) for j, (_, y) in enumerate(path)]
        w = width or max(len(l) for l in left)
        lines = ["origin %d of %d (%s):" % (k + 1, len(origins), kind)]
        for l, r in zip(left, right):
            lines.append("%s │ %s" % (l.ljust(w), r))
        blocks.append("\n".join(lines))
    return "\n".join(blocks)

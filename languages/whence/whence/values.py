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


class Guess(object):
    """An uncertain value (v0.15, AI-native primitives): `node` is a real
    Prov holding the underlying answer, `confidence` is a float in [0, 1],
    `sources` are deduped, ordered labels for what produced/contributed to
    it. Mirrors `Miss` on purpose: where a Miss says "no answer, and here
    is why," a Guess says "an answer, but not a certain one, and here is
    how sure." Never nests (`guess(guess(x, ...), ...)` merges into one,
    same discipline as `merge_miss` never wrapping a Miss around a Miss)."""
    __slots__ = ("node", "confidence", "sources")

    def __init__(self, node, confidence, sources):
        seen = set()
        out = []
        for s in sources:
            if s not in seen:
                seen.add(s)
                out.append(s)
        self.node = node
        self.confidence = confidence
        self.sources = tuple(out)


_PMAP_MISSING = object()


class _PNode(object):
    """One node of a persistent (immutable) AVL tree, keyed by string.

    No delete is needed (Whence records never lose a field), which keeps
    the rebalancing logic to the classic insert-only cases. `size` is
    carried per node so `len(PMap)` is O(1) rather than a full walk.
    """
    __slots__ = ("key", "val", "left", "right", "height", "size")

    def __init__(self, key, val, left, right):
        self.key = key
        self.val = val
        self.left = left
        self.right = right
        lh = left.height if left is not None else 0
        rh = right.height if right is not None else 0
        ls = left.size if left is not None else 0
        rs = right.size if right is not None else 0
        self.height = 1 + (lh if lh > rh else rh)
        self.size = 1 + ls + rs


def _pheight(n):
    return n.height if n is not None else 0


def _pbalance(n):
    return _pheight(n.left) - _pheight(n.right)


def _protate_left(n):
    r = n.right
    new_n = _PNode(n.key, n.val, n.left, r.left)
    return _PNode(r.key, r.val, new_n, r.right)


def _protate_right(n):
    l = n.left
    new_n = _PNode(n.key, n.val, l.right, n.right)
    return _PNode(l.key, l.val, l.left, new_n)


def _prebalance(n):
    bf = _pbalance(n)
    if bf > 1:
        if _pbalance(n.left) < 0:
            n = _PNode(n.key, n.val, _protate_left(n.left), n.right)
        return _protate_right(n)
    if bf < -1:
        if _pbalance(n.right) > 0:
            n = _PNode(n.key, n.val, n.left, _protate_right(n.right))
        return _protate_left(n)
    return n


def _pinsert(node, key, val):
    """Path-copying insert. Returns (new_root, is_new_key): only the O(log n)
    nodes from the root down to `key`'s position are allocated — every
    sibling subtree is the SAME object as before, shared, not copied."""
    if node is None:
        return _PNode(key, val, None, None), True
    if key == node.key:
        return _PNode(key, val, node.left, node.right), False
    if key < node.key:
        new_left, is_new = _pinsert(node.left, key, val)
        merged = _PNode(node.key, node.val, new_left, node.right)
    else:
        new_right, is_new = _pinsert(node.right, key, val)
        merged = _PNode(node.key, node.val, node.left, new_right)
    return _prebalance(merged), is_new


def _pget(node, key):
    while node is not None:
        if key == node.key:
            return node.val
        node = node.left if key < node.key else node.right
    return _PMAP_MISSING


def _pinorder(node):
    """Iterative in-order walk (no host recursion, matches this codebase's
    convention of never recursing on the host stack for guest-scale data)."""
    stack = []
    cur = node
    while stack or cur is not None:
        while cur is not None:
            stack.append(cur)
            cur = cur.left
        cur = stack.pop()
        yield cur.key, cur.val
        cur = cur.right


class PMap(object):
    """A persistent (immutable) string-keyed map, backed by an AVL tree.

    `put` returns a NEW map sharing every subtree untouched by the change —
    O(log n) new nodes per update instead of a full O(n) copy. This is the
    same idea `WList` (v0.6) applies to lists, now given to records: a
    chain of N sequential `put`s costs O(N log N) total allocation with
    every intermediate version still fully reachable (needed for `why`/
    `steps`), instead of O(N^2) (round 200's self-hosting memory-scaling
    finding: `dict(r.payload.fields)` copied the WHOLE current store on
    every single `put`). Iteration/`items()` walks the tree in key order —
    every existing Record display site already does `sorted(p.fields...)`,
    so this is not a behaviour change, just a faster way to reach the same
    sorted order.
    """
    __slots__ = ("_root",)

    def __init__(self, root=None):
        self._root = root

    @staticmethod
    def from_dict(d):
        m = PMap()
        for k, v in d.items():
            m = m.put(k, v)
        return m

    def put(self, key, val):
        new_root, _ = _pinsert(self._root, key, val)
        return PMap(new_root)

    def get(self, key, default=None):
        v = _pget(self._root, key)
        return default if v is _PMAP_MISSING else v

    def merged_with(self, other):
        """New map with every (key, value) of `other` layered on top of
        `self` (matches `dict(self); .update(other)` semantics: `other`
        wins on shared keys)."""
        m = self
        for k, v in other.items():
            m = m.put(k, v)
        return m

    def __contains__(self, key):
        return _pget(self._root, key) is not _PMAP_MISSING

    def __getitem__(self, key):
        v = _pget(self._root, key)
        if v is _PMAP_MISSING:
            raise KeyError(key)
        return v

    def __len__(self):
        return self._root.size if self._root is not None else 0

    def __iter__(self):
        for k, _ in _pinorder(self._root):
            yield k

    def __bool__(self):
        return self._root is not None

    __nonzero__ = __bool__   # py2-style alias, harmless on py3

    def keys(self):
        return iter(self)

    def items(self):
        return _pinorder(self._root)

    def values(self):
        for _, v in _pinorder(self._root):
            yield v

    def to_dict(self):
        return dict(self.items())

    def __eq__(self, other):
        if isinstance(other, PMap):
            return self.to_dict() == other.to_dict()
        return NotImplemented

    __hash__ = None

    def __repr__(self):
        return "PMap(%r)" % (self.to_dict(),)


class Record(object):
    __slots__ = ("_map",)

    def __init__(self, fields):
        # Accepts a PMap directly (the fast path: `put`/`merged_with`
        # already built the new map, nothing left to copy) or any
        # dict-like/iterable-of-pairs mapping (record literals, `@{...}`
        # construction sites, tests) via `PMap.from_dict`.
        self._map = fields if isinstance(fields, PMap) else PMap.from_dict(
            fields if hasattr(fields, "items") else dict(fields))

    @property
    def fields(self):
        return self._map


class Closure(object):
    __slots__ = ("name", "params", "body", "env", "ret_spec", "ret_label",
                 "param_specs")

    def __init__(self, name, params, body, env, ret_spec=None, ret_label=None,
                 param_specs=None):
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
        # v0.19 (round 344): the PARAMETER half of the same contract, in
        # the same form and resolved at the same moment (interp.py
        # `_closure_params`) — None when no parameter is annotated, else a
        # tuple of `(param_name, spec, label)`. Before v0.19 this half
        # lived as `let p = typed(p, <spec expr>, <label>)` statements the
        # parser prepended to the BODY, so its spec was re-resolved in the
        # CALL env on every call while the return half was resolved once in
        # the DEFINING env — one signature could name two different shapes
        # with one name. See SPEC decision 29.
        self.param_specs = param_specs


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


#: The characters the LEXER treats specially inside a string literal, in the
#: order they must be substituted (backslash first, or the escapes this table
#: introduces get escaped again). Round 422 (language C): this is the single
#: copy. `whence/parser.py:quote_str` was a second one, carried since v0.39
#: (round 408) with a comment naming both reasons it was not shared -- the
#: `limit` truncation, and `\t`/`\r`, which the runtime copy did not escape.
#: The first reason is dischargeable by an argument (`limit=None`); the second
#: was a DIVERGENCE, not a design: a snapshot containing a raw tab or carriage
#: return is not a Whence literal, which is exactly the rule decision 48 wrote
#: down for the parser's half of the same job and never applied to this half.
#: `tests/test_v41.py` is the pin.
QUOTE_ESCAPES = (("\\", "\\\\"), ('"', '\\"'),
                 ("\n", "\\n"), ("\t", "\\t"), ("\r", "\\r"))


def quote_str(s, limit=None):
    """A string VALUE, spelled as the Whence literal that produces it.

    Round-trip exact by construction rather than by enumeration: the five
    characters the lexer treats specially are escaped, everything else is
    copied. `limit` truncates the ESCAPED text and appends `…`, which is
    what the runtime snapshot path wants and what a parse diagnostic must
    never do -- so the diagnostic passes `limit=None` rather than keeping a
    second function.
    """
    for raw, esc in QUOTE_ESCAPES:
        s = s.replace(raw, esc)
    if limit is not None and len(s) > limit:
        s = s[:limit] + "…"
    return '"%s"' % s


def _quote(s, limit):
    return quote_str(s, limit)


SHOW_NEST = 3   # containers nested deeper than this render as […] / @{…}

# v0.44 (round 452), decision 53. THE FULL RENDERING'S OWN CAP.
#
# Until v0.44 `full_show` and `show_payload` read ONE constant, and that is
# why "lifting the cap" read as impossible: it is not one cap, it is two
# promises wearing one number. Decision 37 wrote both promises down and
# decision 52 restated them — `str` is `full_show`, unbounded, a miss lists
# its reasons; every miss MESSAGE is `show_payload`, one line, bounded — and
# then left the bounded one's constant deciding how much of a value the
# unbounded one may show.
#
# 24 IS DERIVED FROM TWO MEASUREMENTS, NOT CHOSEN (round 452, `depthcensus.py`,
# re-runnable; `state/whence/round-452/depth-census.json` is that round's
# reading):
#
#   * the deepest value any program in `examples/` builds is **14** container
#     levels — `examples/self_host.lang`'s `let p7`, the AST the Whence-in-
#     Whence parser produces, whose spine is
#     Record>WList>Record>Record>WList>Record>Record>Record>WList>Record>
#     Record>WList>Record>Record>str. At the v0.43 cap of SHOW_NEST + 1 = 4
#     levels, `print(p7)` showed 139 characters and stopped at
#     `stmts: […]` — the language's own self-hosting program builds values
#     three and a half times deeper than the language can print. 24 leaves
#     ten levels of headroom over the deepest thing the corpus builds.
#   * host frames. `Interpreter.HOST_RESERVE`'s own comment lists "rendering
#     (depth-capped)" as one of the three things the 250-frame reserve
#     covers, so this cap is a claim about that reserve and had to be paid
#     for before it could be raised. Measured by recursion-limit bisection,
#     not by instrumenting the renderer — a counting wrapper adds one frame
#     per level and inflates the very number being taken, which is how round
#     452's first reading came out at 4:
#
#         v0.43 path   4 + 3/level   (7, 10, 13 frames at depths 1, 2, 3)
#         v0.44 path   3 + 1/level   (4, 8, 13, 23, 27 at 1, 5, 10, 20, 24)
#
#     Three of v0.43's four frames per level were the trip out through
#     `show_payload` and a generator expression to get back to `_show`. At
#     3/level a cap of 24 would have cost ~79 frames, a third of the whole
#     reserve against a bound-by-construction of ~110 for everything else in
#     it. The full path now calls `_show` directly from an explicit loop:
#     **27 frames at the new cap**, versus 13 at v0.43's. A +14 delta buys
#     20 extra levels. `tests/test_v44.py::
#     test_the_full_rendering_costs_one_host_frame_per_level` re-takes it.
FULL_SHOW_NEST = 24

# v0.44: the cap was silently doing a SECOND job nobody had named, and the
# job does not survive the cap being raised.
#
# Round 450's next step said "`full_show` already pays O(n) in elements", and
# that is false for a value with SHARING. Whence values are immutable and
# `WList` shares storage on purpose, so the value graph is a DAG — and a
# renderer walks a DAG as a TREE, once per PATH. Round 452 measured it:
# `let a = [1, 2]` followed by twelve `let v = [v, v]` renders 108 characters
# at a cap of 3, 892 at 6, 7164 at 9 and 40956 at 12. That is 2^n, not O(n),
# and raising the cap from 4 to 25 levels without a size bound would have
# turned a printable value into hundreds of megabytes of text.
#
# So the depth cap was load-bearing for OUTPUT SIZE and only ever documented
# as load-bearing for HOST FRAMES. Splitting the two constants means the size
# job needs an owner, and this is it. It bounds the WIDTH direction too,
# which v0.43 never bounded at all: `full_show` of a million-element list
# rendered a million elements, in a language that caps an integer at 4000
# digits so the explanation path cannot crash.
#
# 20000 is 666x the largest full rendering the corpus produces — 30 rendered
# nodes, `examples/show.lang` (max over all 33 programs; the widest text is
# 1883 characters, `examples/blame.lang`). A rendering that stops on this
# budget says so in the text (the same `, …` a truncated head has always
# used) and, because the suppressor is now the same walk, `print` claims
# exactly nothing about what it did not reach.
FULL_SHOW_NODES = 20000


class _FullCtx(object):
    """State carried down ONE full rendering: its depth cap, its node budget,
    and the miss nodes the rendering NAMED.

    The third field is why this object exists. v0.43 computed it with a
    second walk (`named_misses`) written to mirror `_show` branch for branch,
    guarded by a differential test — and `skills/suppressor-shares-the-
    detector-shape/SKILL.md` is a whole skill about that class of defect
    recurring. A mirror can drift; a by-product cannot. v0.44 collects the
    misses IN the renderer, so "the suppressor has the renderer's bound" is
    not a property a test has to keep true.
    """

    __slots__ = ("cap", "left", "misses", "seen", "depth_stopped",
                 "node_stopped")

    def __init__(self, cap=FULL_SHOW_NEST, budget=FULL_SHOW_NODES):
        self.cap = cap
        self.left = budget
        self.misses = []
        self.seen = set()
        self.depth_stopped = False
        self.node_stopped = False

    def name_miss(self, node):
        nid = id(node)
        if nid not in self.seen:
            self.seen.add(nid)
            self.misses.append(node)

    def spend(self):
        """True if there is budget for one more rendered node."""
        if self.left <= 0:
            self.node_stopped = True
            return False
        self.left -= 1
        return True


class FullRendering(object):
    """What one `full_show` walk produced: the text, and the miss nodes that
    text NAMES. `depth_stopped` / `node_stopped` say which bound stopped it
    (neither, either or both), so a caller can tell "nothing was hidden" from
    "something was, and here is why"."""

    __slots__ = ("text", "misses", "depth_stopped", "node_stopped")

    def __init__(self, text, misses, depth_stopped, node_stopped):
        self.text = text
        self.misses = misses
        self.depth_stopped = depth_stopped
        self.node_stopped = node_stopped

    @property
    def stopped(self):
        return self.depth_stopped or self.node_stopped


def show_payload(p, limit=SHOW_LIMIT, nest=0, ctx=None):
    """Short one-line snapshot of a payload, truncated to `limit` chars.
    Nesting is capped so snapshotting a deeply nested list is O(1), not
    O(depth) (a 2500-deep list would otherwise recurse 2500 frames).

    `ctx` (v0.44) is the FULL rendering's state and is None for every
    snapshot caller, which is every caller in this file except `full_show`.
    With `ctx` None the behaviour is byte-for-byte what it was in v0.43.
    """
    s = _show(p, limit, nest, ctx)
    # Strings are already truncated (with their closing quote) by _quote;
    # only containers need the outer cut.
    if limit is not None and not isinstance(p, str) and len(s) > limit + 2:
        s = s[:limit] + "…"
    return s


# v0.27 (round 368): the one payload kind `_show` rendered in FULL, with no
# cap of any sort. Strings are cut by `_quote`'s `limit`, lists by
# `SHOW_NEST` and `head(6)`, records by `SHOW_NEST` and `items[:4]` — and
# integers, which Whence makes unbounded on purpose (see SPEC "v0.4.1"),
# went straight to `repr()`. CPython caps `int.__str__` at
# `sys.get_int_max_str_digits()` (4300 by default since 3.11) and raises
# `ValueError` past it, so rendering an integer the language itself lets you
# build was a raw host traceback out of the SNAPSHOT path — i.e. out of
# `print`, out of every `mk_miss` message that names its operands, out of a
# failing `check`'s report, and out of `why`. In a language whose rule 2 is
# "no exceptions" and whose one idea is that a failure can explain itself,
# the explanation crashed. 13287 bits is at most 4000 decimal digits
# (13287 * log10(2) = 3999.8), comfortably under the host's 4300, so the
# host limit is never reached and this cap is Whence's own.
#
# WHAT THE TWO CONSTANTS DO AND DO NOT GUARANTEE (corrected v0.40, round 410,
# decision 49). This comment used to end: "`num()` refuses numeric TEXT past
# the same boundary (see `b_num`), so the two stay inverses: Whence never
# accepts digits it could not print back." Both halves needed work.
#
#   * "the two stay inverses" named `num()` and left out the OTHER door for
#     numeric text, a source literal, which had no bound at all until
#     decision 49 gave it this one. Round 408 measured the gap as a
#     host/guest divergence at 4001 digits.
#   * "never accepts digits it could not print back" is a claim decision 49
#     deliberately does NOT make true, because the ACCEPTANCE bound is on
#     decimal DIGITS (4000) and the PRINTING bound is on BITS (13287), and
#     13287 bits is 3999.8 digits. Every accepted 4000-digit integer at or
#     past `2 ** SHOW_INT_BITS` --- 43.3% of them, `9 * 4000` among them ---
#     is accepted and renders as `<integer, 13288 bits>`.
#
# The rule the code actually has, which is the one to reason from:
#
#     Whence accepts at most SHOW_INT_DIGITS digits of numeric integer TEXT,
#     at both doors, with the same sentence; and it prints an integer in full
#     up to SHOW_INT_BITS bits, summarising past it however that integer was
#     built. The bounds are in different units on purpose --- a refusal has
#     to name a fix the author can carry out, and an author can count the
#     digits in their own source and cannot count its bits.
#
# `tests/test_v40.py` section 4 measures the residual rather than repeating
# any of this, and pins the two ways of closing it that were not taken.
SHOW_INT_DIGITS = 4000
SHOW_INT_BITS = 13287

#: v0.40 (round 410), decision 49. The sentence BOTH doors for numeric text
#: say when they refuse. It used to be written out once, inside `interp.b_num`,
#: and the comment above claimed the rule held of the language --- while
#: `whence/lexer.py`, the other door, had never heard of it: a 4001-digit
#: SOURCE LITERAL was accepted, so Whence did accept digits it could not print
#: back, through the door nobody had looked at. The constant is here rather
#: than in either door so that neither can reword the rule alone; the guest
#: lexer's copy is a separate implementation and is pinned by
#: `tests/test_lexer_guest_parity.py`'s rule 3 instead.
NUM_TEXT_LIMIT_MSG = ("%d digits is over the %d-digit limit for numeric text "
                      "(str of a larger integer is a summary, not digits)")


def show_int(n):
    """`repr(n)` for an integer small enough to render, a summary past
    `SHOW_INT_BITS`. Bits, not digits, because bits is O(1) to obtain and is
    the unit `Interpreter.max_value` charges integers in."""
    if -_SHOW_INT_CUT < n < _SHOW_INT_CUT:      # the common case, no method call
        return repr(n)
    return "<integer, %d bits>" % n.bit_length()


_SHOW_INT_CUT = 1 << SHOW_INT_BITS


def _show(p, limit, nest, ctx=None):
    if isinstance(p, bool):
        return "true" if p else "false"
    if isinstance(p, int):
        return show_int(p)
    if isinstance(p, float):
        return repr(p)
    if isinstance(p, str):
        return _quote(p, limit)
    # limit=None means "full rendering": show every element and field.
    if isinstance(p, WList):
        if nest >= (SHOW_NEST if ctx is None else ctx.cap):
            if ctx is not None and len(p):
                ctx.depth_stopped = True
            return "[…]" if len(p) else "[]"
        if ctx is not None:
            # ONE host frame per level: straight back into `_show`, not out
            # through `show_payload` and a generator expression. See
            # FULL_SHOW_NEST's comment for the 4-frames-per-level
            # measurement this replaces. `show_payload(x, None, n, ctx)` is
            # `_show(x, None, n, ctx)` exactly — its only extra work is an
            # outer character cut guarded by `limit is not None`.
            parts = []
            cut = False
            for e in p:
                if not ctx.spend():
                    cut = True
                    break
                q = e.payload
                if isinstance(q, Miss):
                    ctx.name_miss(e)
                parts.append(_show(q, None, nest + 1, ctx))
            return "[" + ", ".join(parts) + (", …" if cut else "") + "]"
        head = p.to_list() if limit is None else p.head(6)
        return "[" + ", ".join(
            show_payload(e.payload, limit and 12, nest + 1) for e in head) + \
            (", …" if len(head) < len(p) else "") + "]"
    if isinstance(p, Record):
        if nest >= (SHOW_NEST if ctx is None else ctx.cap):
            if ctx is not None and p.fields:
                ctx.depth_stopped = True
            return "@{…}" if p.fields else "@{}"
        if ctx is not None:
            parts = []
            cut = False
            for k, v in sorted(p.fields.items()):
                if not ctx.spend():
                    cut = True
                    break
                q = v.payload
                if isinstance(q, Miss):
                    ctx.name_miss(v)
                parts.append("%s: %s" % (k, _show(q, None, nest + 1, ctx)))
            return "@{" + ", ".join(parts) + (", …" if cut else "") + "}"
        items = sorted(p.fields.items())
        head = items if limit is None else items[:4]
        return "@{" + ", ".join(
            "%s: %s" % (k, show_payload(v.payload, limit and 12, nest + 1))
            for k, v in head) + \
            (", …" if len(head) < len(items) else "") + "}"
    if isinstance(p, Miss):
        # v0.43 (round 450), decision 52. The FULL rendering names the
        # reason; the bounded SNAPSHOT keeps the bare token. The two are
        # different promises and decision 37 already wrote both down, in
        # `interp.b_show`'s comment: "`str` is `full_show` -- unbounded, a
        # miss lists its reasons"; "every MISS MESSAGE in this file is built
        # from `show_payload` instead: one line, bounded ..., a miss is the
        # word `miss`". Until v0.43 `full_show` kept the first promise at the
        # TOP level only and silently fell back to the second one element
        # down, so `print([nosuch(1)])` printed `[miss]` -- and `b_print`
        # then counted that as OBSERVING the miss and suppressed the drop
        # report, which is the one thing that WOULD have named the reason.
        # Adding a `print` to a program removed information about a miss.
        #
        # Spelled as the Whence LITERAL that produces it (`miss "reason"`,
        # SPEC "Finding 5", and the cure sentence at SPEC line 7354 tells an
        # author to write exactly this), for the same reason `quote_str`
        # spells a string that way: a container rendering whose elements are
        # source-shaped can be read back. Quoting is not decoration here --
        # miss reasons contain commas ("arguments fit fold(fn, acc, xs)"),
        # and an unquoted reason inside `[...]` is genuinely ambiguous about
        # where the element ends.
        #
        # The bounded path is deliberately NOT changed: under a limit the
        # recursive calls pass `limit and 12`, so a reason would arrive as a
        # 12-character slice, and a snapshot that shows a twelfth of a
        # sentence is worse than one that shows none. `show()` -- the builtin
        # decision 37 exposed precisely so a Whence program can build the
        # messages the interpreter builds -- is that path, and its contract
        # is unchanged by this version.
        if limit is None:
            return "miss " + quote_str("; ".join(p.reasons), None)
        return "miss"
    if isinstance(p, Guess):
        if ctx is not None:
            # `Guess` has no cap check of its own, in v0.43 and here: the
            # branch descends into `Guess.node` unconditionally, and the
            # child's own branch is where a cap applies. The node BUDGET
            # does apply, which is the first bound this branch has ever had
            # — a long enough `guess(guess(guess(...)))` chain recursed
            # until the host stack ran out.
            n = p.node
            if not ctx.spend():
                return "guess %.2g (%s): …" % (
                    p.confidence, ", ".join(p.sources))
            if isinstance(n.payload, Miss):
                ctx.name_miss(n)
            return "guess %.2g (%s): %s" % (
                p.confidence, ", ".join(p.sources),
                _show(n.payload, None, nest + 1, ctx))
        return "guess %.2g (%s): %s" % (
            p.confidence, ", ".join(p.sources),
            show_payload(p.node.payload, limit and 12, nest + 1))
    if isinstance(p, Closure):
        return "<fn %s>" % p.name if p.name else "<fn>"
    if isinstance(p, Builtin):
        return "<builtin %s>" % p.name
    if isinstance(p, Explanation):
        return "<why>"
    return "<?>"


class _Bare(object):
    """A stand-in node for a bare payload. `full_show` takes a payload and
    `full_show_named` takes a node; both run the same walk, so the payload
    entry point needs something with a `.payload` slot for the two to be one
    function rather than two that agree."""

    __slots__ = ("payload",)

    def __init__(self, payload):
        self.payload = payload


def full_show_named(node, cap=None, budget=None):
    """v0.44 (round 452), decision 53. The full rendering AND the miss nodes
    it names, from ONE walk.

    THE POINT OF THIS FUNCTION IS THAT IT RETURNS BOTH. v0.43 needed the
    second half — `print(x)` suppresses the v0.32 drop report for what it
    showed, so the suppressor must not claim a miss the renderer did not
    render — and computed it with `named_misses`, a separate walk written to
    mirror `_show` branch for branch and held to it by
    `tests/test_v43.py::test_the_renderer_and_the_suppressor_name_the_same_
    misses`. That test is a good test and the design under it is the one
    `skills/suppressor-shares-the-detector-shape/SKILL.md` exists to warn
    about: two walks that MUST agree, kept agreeing by a third thing.

    v0.44 had to move the renderer's bound — a new depth cap and a new node
    budget — which is exactly the edit that breaks a mirror. So the mirror is
    gone. The misses are collected by the renderer as it renders, in
    `_show`'s own container branches, at the moment it emits the text that
    names them. "The suppressor has the renderer's bound" stopped being a
    property to test and became a thing that cannot be otherwise: there is
    one walk and one bound.

    `named_misses` is kept as the name the interpreter and v0.43's tests use;
    it is now this function's second return value.
    """
    # Resolved HERE, not in the signature. A default argument captures the
    # module global at DEFINITION time, so `FULL_SHOW_NEST` baked into the
    # signature would make every test that moves the constant pass
    # vacuously — round 452 wrote two such tests, watched both go green
    # against an unchanged renderer, and only caught it because a third
    # asserted a specific string rather than an equality between two runs.
    # A constant a test cannot move is a constant nothing measures.
    ctx = _FullCtx(FULL_SHOW_NEST if cap is None else cap,
                   FULL_SHOW_NODES if budget is None else budget)
    p = getattr(node, "payload", None)
    if isinstance(p, Miss):
        # `full_show`'s own top-level branch: the reasons ARE the text, so
        # the node is named. Unreachable from `b_print` (which handles a
        # top-level miss through `_observed`) and reachable from the
        # differential in tests/test_v43.py.
        ctx.name_miss(node)
        text = "miss: " + "; ".join(p.reasons)
    elif isinstance(p, Explanation):
        text = render_why(p.root)
    elif isinstance(p, str):
        text = p                      # print of a string is the raw string
    elif isinstance(p, WList):
        # The top-level container is rendered HERE rather than by `_show`,
        # so its elements sit at nest 0 — one level shallower than
        # `show_payload(p, None)` would put them. That has been true since
        # v0.29 and v0.43's differential covers it; it is restated here
        # because it is the detail a rewrite of this function gets wrong.
        parts = []
        cut = False
        for e in p:
            if not ctx.spend():
                cut = True
                break
            q = e.payload
            if isinstance(q, Miss):
                ctx.name_miss(e)
            parts.append(_show(q, None, 0, ctx))
        text = "[" + ", ".join(parts) + (", …" if cut else "") + "]"
    elif isinstance(p, Record):
        parts = []
        cut = False
        for k, v in sorted(p.fields.items()):
            if not ctx.spend():
                cut = True
                break
            q = v.payload
            if isinstance(q, Miss):
                ctx.name_miss(v)
            parts.append("%s: %s" % (k, _show(q, None, 0, ctx)))
        text = "@{" + ", ".join(parts) + (", …" if cut else "") + "}"
    else:
        text = _show(p, None, 0, ctx)
    return FullRendering(text, ctx.misses, ctx.depth_stopped,
                         ctx.node_stopped)


def named_misses(node, cap=None, budget=None):
    """The miss NODES whose reason `full_show` prints (v0.43, decision 52).

    v0.44: a thin call to `full_show_named`, which is the renderer. Before
    v0.44 this was a second walk over the same value, and its docstring had
    to explain how it mirrored the first one — `full_show`'s own container
    branch rendering elements a level shallower, `_show`'s `Guess` branch
    descending with no nest guard, a `best` map so a node reachable at two
    depths was judged at the shallower one. All three were real and all three
    were places a mirror could be wrong. None of them can be wrong now,
    because there is nothing to mirror.
    """
    return full_show_named(node, cap, budget).misses


def full_show(p):
    """Full rendering used by print(): misses list reasons, explanations
    render. See `full_show_named` for the walk and for the half of it this
    entry point throws away."""
    return full_show_named(_Bare(p)).text


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

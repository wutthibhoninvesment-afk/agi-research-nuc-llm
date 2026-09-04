#!/usr/bin/env python3
"""reprsweep — audit decision 60 against live values, by ENUMERATION.

v0.47 (round 482, language C). Decision 58 (round 476) gave `Env` a
`__repr__` because `Interpreter.run`'s return value printed as
`<whence.interp.Env object at 0x7d6a91893740>` and a real author filed a
false bug report against `b_fold` with that string as its evidence. The
rule decision 58 wrote into the registry is general —

    a value this implementation HANDS A CALLER is a surface

— and it was applied to exactly one class. Round 476's own next-step 2
asked for the sweep and listed eight candidate classes from memory. This
file is the sweep, and it does not take a list from anybody: it CRAWLS the
public object graph from what the embedding API actually returns, so a
class added to `values.py` next round is audited the round it becomes
reachable. That is the difference between this and eight hand-written
tests — the hand-written tests would still pass on the day the ninth class
arrives.

The crawl reaches 19 classes and found NINE that round 476's list does not
name. Two are singletons of their own kind: `Interpreter` (reachable as
`run().parent.interp`, and the object a caller constructs FIRST) and
`MergedProv` (which HAD a repr, inherited from `Prov`, that introduced it
under the wrong class name and dropped `count`, the only slot it has —
worse than no repr, because a useless repr is obviously useless and a
wrong one is not). The other seven are the AST node classes, reachable as
`run().vars["f"].payload.body...`, whose generated repr recursed over the
whole subtree with no cut of any kind and so was bounded only by the size
of the program.

Two defects in THIS FILE were found the same way, and both had it
reporting a clean sweep while blind — see `reachable()`'s comments. A
crawl keyed on `id()` must retain every object it has seen, because
`Prov.inputs` and `Prov.show` build fresh objects per access and CPython
reuses a freed address; and a crawl that descends any public attribute
walks out of the whence graph into the host and never terminates. The
first cost `MergedProv`, the second cost six classes. An audit is two
claims and one of them is the auditor's.

## The rule this audits (SPEC § Decision 60)

For every class reachable from `Interpreter.run(source)` along a path of
PUBLIC attribute names, `repr(instance)` must be:

  R1 HOST-FREE      no `object at 0x`, no `whence.` module path, no bare
                    hex address. The failure decision 58 named.
  R2 BOUNDED        `len(repr(v)) <= values.REPR_CAP`, however large the
                    value. Not "short in practice" — bounded, checked
                    against deliberately huge values in `scale_cases()`.
  R3 DETERMINISTIC  the same string in two processes with different
                    `PYTHONHASHSEED`. `--seeds` runs that comparison.
  R4 HONEST         a repr in the host's constructor-call shape,
                    `Name(...)`, must name its OWN class. R4 exists
                    because R1-R3 were written first and `MergedProv`
                    passed all three while introducing itself as `Prov`:
                    it inherited a repr that was correct for its base and
                    a lie for it, and dropped `count`, its only slot. A
                    rule set derived from one known failure (decision
                    58's heap address) finds that failure again; this row
                    is the one the SWEEP found, and it is the argument
                    for enumerating instead of listing.

R1/R2 are checked in-process. R3 needs subprocesses and is the `--seeds`
subcommand, because it costs ~3 interpreter starts.

Deliberately NOT part of the rule: any house style for the repr's body.
`Prov.__repr__` is a constructor call (`Prov('let', 'n', line=2, ...)`)
rather than the `<whence ...>` frame the payload classes use, and it
passes all three checks. A rule that outlawed it would be an aesthetic
preference wearing a checker, and decision 48's "Whence literal or prose"
dichotomy is about DIAGNOSTICS — a host repr's own convention is the
constructor call, and a caller reading one is in the host.

## Why "public path"

`Record._map` reaches a `PMap` and `PMap._root` reaches a `_PNode`, so an
unrestricted crawl reports `_PNode` — an AVL tree node — as a caller
surface. It is not one: every segment of that path is spelled private by
the language this file is written in, and `Record.fields` is the public
door to the same map. The crawl therefore descends through non-underscore
names only. `PMap` is still audited, because `fields` is public; `_PNode`
is not, and `--private` shows what the loose rule would have claimed.

Usage:
    python3 reprsweep.py                 # audit; exit 1 on any violation
    python3 reprsweep.py --json
    python3 reprsweep.py --private       # also list private-path classes
    python3 reprsweep.py --seeds         # R3, in three subprocesses
    python3 reprsweep.py --manifest      # v0.48: coverage of each derived
                                         #   axis; exit 1 on a gap or a
                                         #   stale UNREACHABLE entry
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from whence.interp import Interpreter                  # noqa: E402
from whence import values as V                         # noqa: E402

#: The probe, before v0.48: a hand-written program, kept VERBATIM as the
#: regression witness for the derived one. Round 482 shipped it and named
#: its own defect in the same breath (its next-step 3): "a value kind no
#: line of it constructs is not audited; the crawl is exhaustive over what
#: the probe BUILDS, not over what the language can build." It reaches 7
#: of the language's 23 AST node classes. `tests/test_v48.py::
#: test_the_derived_probe_reaches_everything_the_hand_written_one_did`
#: holds it to a strict superset — which is not a formality: the FIRST
#: derived probe written here reached 34 classes and LOST `values.Miss`,
#: because a miss is produced by failure and is named by neither the
#: builtin table nor the node table. Two tables covered more and still
#: covered less.
LEGACY_PROBE = '''
let n = 42
let s = "hi"
let xs = [1, 2, 3]                        # WList
let r = @{a: 1, b: @{c: 2}}               # Record, PMap
fn f(x) { x + 1 }                         # Closure (named)
let g = fn(x) { x * 2 }                   # Closure (anonymous)
let w = why r                             # Explanation
let m = nosuch(1)                         # Miss
let q = guess(7, 0.5, "sensor")           # Guess
let mapped = map(f, xs)                   # Builtin, via the globals env
let tot = fold(fn(a, b) { a + b }, 0, xs)
fn loop(i, acc) { if i <= 0 { acc } else { loop(i - 1, acc + i) } }
let looped = loop(50, 0)                  # MergedProv (a merged tail run)
let cond = if n > 3 { "big" } else { "small" }
'''

# ----------------------------------------------------------------------
# v0.48 (round 488), decision 62 — the probe is DERIVED, on three axes.
#
# The subject set of an audit must come from the artefact, not from the
# auditor's memory. `reachable()` already derives the CLASSES it audits by
# crawling; what it could not derive was the PROGRAM whose object graph it
# crawls, so the sweep was exhaustive over one hand-written program and
# read as exhaustive over the language. The three axes below are each read
# off a live table, and each has a totality gate in `tests/test_v48.py`:
#
#   NODES     every concrete `ast_nodes.Node` subclass
#   BUILTINS  every row of `interp._make_builtin_table()` / `_BUILTIN_SIGS`
#   VALUES    every class defined in `whence.values` / `whence.interp`
#
# Nothing here is a list to keep in sync by hand. A class or builtin with
# no line fails a test that names it; a line whose class is no longer
# reachable fails a different test that names it; and `UNREACHABLE` — the
# declared exceptions — is checked in the OTHER direction too, so a class
# that BECOMES reachable expires its own excuse.

#: Three substitution tokens, so ONE table serves two passes: the ordinary
#: probe (short tokens) and the R2-at-scale probe (deliberately huge ones).
#: Round 482's `scale_cases()` was a second hand-written list covering two
#: node shapes; this covers every node class by construction.
#:   __S__  the body of a string literal
#:   __N__  an identifier
#:   __D__  a run of digits
_SMALL = {"__S__": "s", "__N__": "a", "__D__": "1"}
#: 3000, not 5000: `lexer` refuses numeric text over `SHOW_INT_DIGITS`
#: (4000) digits, and that refusal is a real language limit, not a bound
#: on the repr. The point of a scale case is a legal program.
_BIG = {"__S__": "x" * 5000, "__N__": "z" * 400, "__D__": "9" * 3000}

#: One Whence construct per CONCRETE AST node class. `Program` is absent
#: on purpose and is declared in `UNREACHABLE` with its reason.
NODE_SOURCE = {
    "Binary": "1 + __D__",
    "Block": "1",
    "BoolLit": "true",
    "Call": "len([__D__])",
    "Check": 'check "__S__": 1 == 1\n  1',
    "ExprStmt": "1",
    "FieldAccess": "@{__N__: 1}.__N__",
    "FnDef": "fn __N__() { 1 }\n  __N__()",
    "FnExpr": "fn(__N__) { __N__ }",
    "If": "if true { __D__ } else { 2 }",
    "Index": "[1, 2][0]",
    "Let": "let __N__ = __D__\n  __N__",
    "ListLit": "[__D__, 2]",
    "MissLit": 'miss "__S__"',
    "NameRef": "let __N__ = 1\n  __N__",
    "Num": "__D__",
    "RecordLit": "@{__N__: __D__}",
    "Rescue": "1 rescue 0",
    "Snip": "snip 1",
    "Str": '"__S__"',
    "Unary": "-__D__",
    "Why": "why 1",
}

#: A literal of each argument KIND the builtin signature table spells.
#: `_BUILTIN_SIGS` records kinds because `_order_hint` re-checks an
#: out-of-order call against them (v0.22); this reuses them to WRITE the
#: call, so 28 of the 37 builtins need no per-name entry at all.
KIND_ARG = {
    ("num",): "1",
    ("str",): '"s"',
    ("list",): "[1, 2]",
    ("record",): "@{a: 1}",
    ("fn",): "fn(x) { x }",
    ("str", "list"): "[1, 2]",
    ("str", "record"): '"num"',
    None: "1",
}

#: The nine builtins whose generic, kind-derived call MISSES. Each entry
#: is the whole argument list. This table is checked in BOTH directions:
#: `test_every_argument_override_is_load_bearing` drops each entry and
#: asserts the generic call misses without it, so an override that stops
#: being needed (a widened builtin, a fixed kind in the sig table) fails
#: rather than sitting here forever. A probe whose builtin call quietly
#: returns a miss is probing the miss path, not the builtin.
ARG_OVERRIDE = {
    # kind `v` is spelled None ("any") and the generic literal is a num
    "len": ["[1, 2]"],
    "keys": ["@{a: 1}"],
    "confidence": ['guess(7, 0.5, "s")'],
    # kind `fn` does not carry the ARITY the builtin will call it with
    "fold": ["fn(a, b) { a + b }", "0", "[1, 2]"],
    # ... nor the return TYPE the builtin requires of it
    "filter": ["fn(x) { x > 1 }", "[1, 2]"],
    "find": ["fn(x) { x > 1 }", "[1, 2]"],
    # kind `list` does not carry its ELEMENT type
    "join": ['["a", "b"]', '", "'],
    # a name/pattern argument must exist in the value it addresses
    "get": ["@{a: 1}", '"a"'],
    "at": ["1 + 2", '"+"'],
}

#: Value kinds that neither table names. A `Miss` is what FAILURE
#: produces, a `MergedProv` is what a tail LOOP produces, and an
#: `Explanation` is what a keyword produces — none of the three is a
#: builtin's return type or an AST class, and the first derived probe
#: written here reached 34 classes without a single `Miss` in it.
#: The `__N__` in the `Prov` and `Env` rows is not decoration. A
#: top-level binding NAME is what `Env.__repr__` lists and what
#: `Prov.__repr__` puts in its `detail` slot, and it is the one part of a
#: rendering the author sizes rather than the value. Round 482's
#: `scale_cases()` made every VALUE huge — a 3,000-element list, a 400-key
#: record, a 5,000-character string, a 60-parameter closure — and every
#: NAME short, so `Env` (559 characters at ONE 400-character name) and
#: `Prov` (442) passed R2 in every sweep for six rounds. Substituting the
#: token here is what turns that axis on.
#: INSERTION order is dependency order and is what `derive_probe` emits —
#: NOT `sorted()`. Written sorted, `"Explanation": "let v_why = why
#: v_looped"` ran three rows before `v_looped` existed and `"PMap": "let
#: v_map = v_rec"` two rows before `v_rec` did, so both bound a MISS. Both
#: classes were reached anyway, by another path, and the sweep reported a
#: clean 34 — two probe lines probing nothing, invisible because their
#: subject had a second door. `test_v48.py::test_no_probe_binding_is_an_
#: accidental_miss` is the gate; `ARG_OVERRIDE` has the same gate for the
#: builtin half and this half did not until it was measured.
VALUE_SOURCE = {
    "Prov": "let v__N__prov = 42",
    "Env": "let v__N__scope = 1",
    "WList": "let v_list = [1, 2, 3]",
    "Record": "let v_rec = @{a: 1, b: @{c: 2}}",
    "PMap": "let v_map = v_rec",
    "Closure": "fn v_named(x) { x + 1 }\nlet v_anon = fn(x) { x * 2 }",
    "Builtin": "let v_builtin = map",
    "Guess": 'let v_guess = guess(7, 0.5, "sensor")',
    # `__N__` here too: a MergedProv's `detail` is the CALLED FN's name,
    # so a short one leaves the third unbounded repr untested. With
    # `v_loop` the reverted-fix falsification killed 2 of 3; with the
    # token it kills 3 of 3.
    "MergedProv": ("fn v__N__loop(i, acc) { if i <= 0 { acc }"
                   " else { v__N__loop(i - 1, acc + i) } }\n"
                   "let v_looped = v__N__loop(50, 0)"),
    "Explanation": "let v_why = why v_looped",
    "Interpreter": "let v_engine = 1",
    "Miss": 'let v_miss = miss "gone"\nlet v_miss2 = num("3O")',
}

#: Every class the crawl CANNOT reach, and why. Checked in both
#: directions by `tests/test_v48.py`: a name here that the crawl does
#: reach is a stale excuse and fails; a class in the universe that is
#: neither reached nor named here fails too. That pair is the whole
#: difference between "audited" and "audited as far as anybody looked".
UNREACHABLE = {
    ("whence.ast_nodes", "Program"):
        "the top-level program node. `run()` returns an `Env`; the "
        "program is consumed by `Interpreter.run` and stored on no "
        "public attribute of the Env, the Interpreter or any value. "
        "A function BODY is a `Block` and is public (`Closure.body`), "
        "which is why the other 22 are reachable and this one is not.",
    ("whence.values", "FullRendering"):
        "the result of ONE `full_show_named` walk (decision 53). It is "
        "returned to the caller of that function and stored on nothing.",
    ("whence.values", "_FullCtx"):
        "state carried down one `full_show` walk; dies with the walk.",
    ("whence.values", "_Bare"):
        "a stand-in node so `full_show`'s payload and node entry points "
        "are one function; never stored.",
    ("whence.values", "_PNode"):
        "an AVL node inside `PMap`. Reachable only at `Record._map."
        "_root`, every segment of which is spelled private — see "
        "`--private` and `test_v47.py`'s public-path test.",
    ("whence.interp", "_Call"):
        "a trampoline frame. Lives inside `_run_trampoline`'s own loop.",
    ("whence.interp", "_TailCall"):
        "a trampoline tail-call frame; same lifetime as `_Call`.",
    ("whence.interp", "_UnboundType"):
        "the floor under `_closure_spec` for an annotation naming a "
        "shape that is not bound. Since v0.18 the parser refuses that "
        "source, so no program reaches it; `_check_contract` turns it "
        "into an ordinary miss before any value could carry it.",
}


def node_classes():
    """Every CONCRETE `ast_nodes.Node` subclass, read off the module."""
    import inspect
    from whence import ast_nodes as A
    return {n for n, o in vars(A).items()
            if inspect.isclass(o) and issubclass(o, A.Node) and o is not A.Node}


def builtin_sigs():
    """`{name: sig}` for every builtin, read off the live table.

    `_make_builtin_table()` is what populates `_BUILTIN_SIGS`, so calling
    it first is not defensive — it is the derivation.
    """
    from whence import interp as IN
    IN._make_builtin_table()
    return dict(IN._BUILTIN_SIGS)


def runtime_classes():
    """Every class DEFINED in `whence.values` / `whence.interp`.

    Deduped by identity, not by name: `values.Value` is a second name for
    `Prov` (`Value = Prov`), and counting it as a class would put a
    permanent phantom in the universe that no probe can ever reach.
    """
    import inspect
    from whence import interp as IN
    out, seen = set(), set()
    for mod in (V, IN):
        for name, obj in vars(mod).items():
            if (inspect.isclass(obj) and obj.__module__ == mod.__name__
                    and id(obj) not in seen):
                seen.add(id(obj))
                out.add((mod.__name__, obj.__name__))
    return out


def _sub(text, table):
    for token, rep in table.items():
        text = text.replace(token, rep)
    return text


def builtin_call(name, sig):
    """The source of ONE builtin call, derived from its signature kinds."""
    args = ARG_OVERRIDE.get(name)
    if args is None:
        args = [KIND_ARG.get(kinds, "1") for _param, kinds in sig]
    return "let b_%s = %s(%s)" % (name, name, ", ".join(args))


def derive_probe(scale=False):
    """The probe, GENERATED from the three tables. Never a literal.

    `scale=True` renders the same node table with deliberately huge
    tokens, which is how R2 gets checked against every node class rather
    than against the two shapes somebody remembered.
    """
    sub = _BIG if scale else _SMALL
    # VALUE_SOURCE FIRST, in insertion order. Both facts are load-bearing.
    # Order, because `Env.__repr__` lists only `_ENV_REPR_NAMES` (4) names
    # in DECLARATION order: with the value rows last, the 400-character
    # name sat at position 74 and was never listed, so the scale pass ran
    # with the axis it exists to exercise switched off and reported clean.
    # Insertion order, because these rows depend on each other.
    lines = [_sub(VALUE_SOURCE[cls], sub) for cls in VALUE_SOURCE]
    for cls in sorted(NODE_SOURCE):
        lines.append("fn probe_%s() {\n  %s\n}"
                     % (cls, _sub(NODE_SOURCE[cls], sub)))
    sigs = builtin_sigs()
    for name in sorted(sigs):
        lines.append(builtin_call(name, sigs[name]))
    return "\n".join(lines) + "\n"


PROBE = derive_probe()
SCALE_PROBE = derive_probe(scale=True)


def probe_manifest():
    """Coverage of each derived axis, as data. `gaps` is the whole point:
    a non-empty list is a class or a builtin the sweep does not audit."""
    nodes = node_classes()
    sigs = builtin_sigs()
    runtime = runtime_classes()
    universe = {("whence.ast_nodes", c) for c in nodes} | runtime
    found, _stats = reachable()
    unreached = sorted(universe - set(found))
    return {
        "nodes": {"universe": len(nodes), "with_source": len(NODE_SOURCE)},
        "builtins": {"universe": len(sigs), "overridden": len(ARG_OVERRIDE)},
        "runtime": {"universe": len(runtime),
                    "with_source": len(VALUE_SOURCE)},
        "universe": len(universe),
        "reached": len(found),
        "declared_unreachable": len(UNREACHABLE),
        "gaps": [list(k) for k in unreached if k not in UNREACHABLE],
        "stale_exceptions": [list(k) for k in sorted(UNREACHABLE)
                             if k in found],
    }


#: Crawl budget. The graph is finite but the Interpreter drags in the host
#: (modules, functions, the parser), so the crawl is bounded and the bound
#: is reported rather than assumed: `audit()['crawl']['exhausted']` says
#: whether the walk finished or ran out, and the test asserts it finished.
CRAWL_LIMIT = 60000

#: Substrings that mean the host leaked into a value's rendering. The
#: first is the exact shape decision 58 was filed against.
LEAK_MARKERS = ("object at 0x", "whence.values.", "whence.interp.",
                "whence.ast_nodes.", "whence.lexer.", "whence.parser.",
                "built-in method", "<function ")

#: A repr in the host's constructor-call shape. R4 applies to these and
#: not to the `<whence ...>` frames, whose bodies name a KIND ("record",
#: "fn", "miss") rather than a class on purpose — a Whence author has
#: never heard of `Prov` and should not have to.
_CTOR_RE = __import__("re").compile(r"^([A-Za-z_][A-Za-z0-9_]*)\(")


def _public_children(obj):
    """`(child, name)` pairs reachable from `obj` by a PUBLIC name.

    Three kinds of edge, and no others: a public attribute (slot or
    property — never a callable, since a bound method is not a value a
    caller holds), an element of a host list/tuple, and a value of a host
    dict. `Env.vars` is a plain dict, which is how the program's names are
    reached at all.
    """
    # Descend a whence class or a plain host CONTAINER, and nothing else.
    # Everything reachable from a whence object is either part of the
    # whence graph or the host's own business: a module, a function, a
    # str. Without this the crawl walks out through `Interpreter`'s
    # attributes into module `__dict__`s and never terminates — it ran to
    # its 60,000-step budget and reported 13 of 19 classes, which is the
    # SECOND way this instrument can report a clean sweep while blind.
    if not (type(obj).__module__.startswith("whence")
            or isinstance(obj, (dict, list, tuple))):
        return []
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append((v, "[%r]" % (k,)))
        return out
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj[:64]):
            out.append((v, "[%d]" % i))
        return out
    if isinstance(obj, V.WList):
        for i, v in enumerate(obj.head(64)):
            out.append((v, "[%d]" % i))
        return out
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            child = getattr(obj, name)
        except Exception:
            continue
        if callable(child):
            continue
        out.append((child, "." + name))
    return out


def reachable(source=None, private=False, limit=CRAWL_LIMIT):
    """Crawl from `Interpreter.run(source)` and return what it reaches.

    Returns `(found, stats)` where `found` maps `(module, classname)` to
    the first path that reached it. With `private=True` the crawl also
    descends through underscore names, which is how `--private` shows the
    classes the loose rule would have claimed as caller surfaces.
    """
    # NOT `source=PROBE` in the signature: a default argument binds
    # the module-level string ONCE, at def time, so a caller who
    # rebinds `reprsweep.PROBE` (a test swapping in the legacy probe,
    # this round's own first measurement) silently keeps auditing the
    # old program. Cost one wrong measurement here before it was seen.
    interp = Interpreter()
    root = interp.run(PROBE if source is None else source)
    # `keep` is not bookkeeping, it is CORRECTNESS. `seen` holds `id()`s,
    # and an id identifies an object only while that object is alive —
    # `Prov.inputs` builds a FRESH tuple on every access (`return ins if
    # type(ins) is tuple else (ins,)`), and so does `Prov.show`, so the
    # crawl allocates transient objects, records their ids, drops them,
    # and then skips a genuinely new object that CPython handed the freed
    # address to. Measured, not theorised: without `keep` this crawl
    # reported 18 classes and missed `MergedProv`, which is reachable at
    # `run().vars["looped"].inputs[0]` — an instrument reporting a clean
    # sweep because it had lost the object it was meant to audit.
    seen, found, keep = set(), {}, [root]
    queue = [(root, "run()")]
    steps = 0
    while queue and steps < limit:
        obj, path = queue.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        keep.append(obj)
        steps += 1
        cls = type(obj)
        if cls.__module__.startswith("whence"):
            found.setdefault((cls.__module__, cls.__name__), path)
        kids = _public_children(obj)
        if private:
            slots = []
            for base in cls.__mro__:
                slots.extend(getattr(base, "__slots__", ()) or ())
            for s in slots:
                if not s.startswith("_"):
                    continue
                try:
                    kids.append((getattr(obj, s), "." + s))
                except Exception:
                    pass
        for child, edge in kids:
            if id(child) not in seen:
                queue.append((child, path + edge))
    return found, {"steps": steps, "exhausted": bool(queue),
                   "limit": limit}


def check_repr(obj):
    """R1 and R2 for one live object. Returns a list of violation codes."""
    try:
        text = repr(obj)
    except Exception as exc:            # a repr that raises is the worst
        return ["R0 repr raised %s: %s" % (type(exc).__name__, exc)], ""
    bad = []
    for marker in LEAK_MARKERS:
        if marker in text:
            bad.append("R1 host leak %r" % marker)
    if len(text) > V.REPR_CAP:
        bad.append("R2 unbounded: %d chars > REPR_CAP %d"
                   % (len(text), V.REPR_CAP))
    m = _CTOR_RE.match(text)
    if m and m.group(1) != type(obj).__name__:
        bad.append("R4 dishonest: reprs as %r, is a %r"
                   % (m.group(1), type(obj).__name__))
    return bad, text


def scale_cases():
    """`(label, object)` pairs built deliberately large, for R2.

    A repr is bounded or it is not, and the only honest way to ask is to
    hand it something big. Every case here is a shape that a real program
    produces and that had NO bound before decision 60: the 3,000-element
    list reprred to 156,787 characters and the 400-key record to 22,986.
    """
    cases = []
    env = Interpreter().run("let xs = range(0, 3000)\n")
    cases.append(("WList/3000", env.get("xs").payload))
    src = "let r = @{" + ", ".join("k%d: %d" % (i, i)
                                   for i in range(400)) + "}\n"
    env = Interpreter().run(src)
    rec = env.get("r").payload
    cases.append(("Record/400", rec))
    cases.append(("PMap/400", rec.fields))
    env = Interpreter().run('let s = "%s"\n' % ("x" * 5000))
    cases.append(("Prov/str-5000", env.get("s")))
    long_name = "z" * 300
    env = Interpreter().run("fn %s(%s) { 1 }\n"
                            % (long_name, ", ".join("p%d" % i
                                                    for i in range(60))))
    cases.append(("Closure/60-params", env.get(long_name).payload))
    env = Interpreter().run(
        "let m = num(\"%s\")\n" % ("q" * 400))
    cases.append(("Miss/long-reason", env.get("m").payload))
    env = Interpreter().run(
        "let e = why range(0, 3000)\n")
    cases.append(("Explanation/3000", env.get("e").payload))
    env = Interpreter().run("let big = %s\n"
                            % " + ".join(["1"] * 200))
    cases.append(("Prov/deep-chain", env.get("big")))
    # The AST half. `Closure.body` is public, so a 400-statement function
    # body and a 200-deep expression are both one attribute away from a
    # caller. Before decision 60 the first reprred to the size of the
    # program and the second recursed 200 host frames to do it.
    body = "\n".join("let v%d = %d" % (i, i) for i in range(400))
    env = Interpreter().run("fn wide() {\n%s\nv0\n}\n" % body)
    cases.append(("Block/400-stmts", env.get("wide").payload.body))
    # 50, not 200: `parser._enter` refuses an expression nested more than
    # 60 levels deep (that refusal is decision 12's own bound and it is
    # what makes the AST's DEPTH finite in the first place), so 50 is the
    # deepest legal case rather than an arbitrary number.
    env = Interpreter().run("fn deep() { %s }\n"
                            % ("(" * 50 + "1" + ")" * 50))
    cases.append(("Block/50-deep", env.get("deep").payload.body))
    return cases


def instances(source=None, limit=CRAWL_LIMIT, worst=False):
    """`{(module, class): (live instance, path)}` for one program.

    The same walk as `reachable()`, retaining a live object per class so
    its `repr` can be taken. `keep` is load-bearing for the same `id()`
    reuse reason documented there.
    """
    interp = Interpreter()
    root = interp.run(PROBE if source is None else source)
    out = {}
    seen, queue, keep = set(), [(root, "run()")], [root]
    steps = 0
    while queue and steps < limit:
        obj, path = queue.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        keep.append(obj)          # see `reachable()` — id reuse is real
        steps += 1
        cls = type(obj)
        if cls.__module__.startswith("whence"):
            if worst:
                key = (cls.__module__, cls.__name__)
                prev = out.get(key)
                if prev is None or len(repr(obj)) > len(repr(prev[0])):
                    out[key] = (obj, path)
            else:
                out.setdefault((cls.__module__, cls.__name__), (obj, path))
        for child, edge in _public_children(obj):
            if id(child) not in seen:
                queue.append((child, path + edge))
    return out


def worst_instances(source=None, limit=CRAWL_LIMIT):
    """Per class, the reached instance with the LONGEST repr.

    `instances()` keeps the FIRST one it happens to hit, and for R2 that
    is the wrong witness: the scale probe binds a 400-character name and
    the first `Prov` the crawl reaches is `v_list`, 58 characters. The
    fix reverted in-process, the whole sweep still reported 0 violations —
    an audit checking one arbitrary member of a class is checking the
    class only if every member reprs the same, which is exactly what a
    variable-length field makes false.
    """
    return instances(source, limit, worst=True)


def audit(private=False):
    """The whole sweep, as data."""
    found, stats = reachable(private=private)
    instances_ = {k: v[0] for k, v in instances().items()}
    rows = []
    for key in sorted(found):
        mod, name = key
        obj = instances_.get(key)
        bad, text = check_repr(obj)
        cls = type(obj)
        rows.append({"module": mod, "class": name, "path": found[key],
                     "has_own_repr": "__repr__" in cls.__dict__,
                     "repr": text, "repr_len": len(text),
                     "violations": bad})
    scale = []
    for label, obj in scale_cases():
        bad, text = check_repr(obj)
        scale.append({"case": label, "class": type(obj).__name__,
                      "repr_len": len(text), "repr": text,
                      "violations": bad})
    # v0.48 (round 488), decision 62 — the DERIVED half of R2-at-scale.
    # `scale_cases()` above is round 482's hand-written list and stays as
    # a regression witness; this pass runs the SAME derived probe with the
    # substitution tokens rendered huge, so every class the sweep reaches
    # gets a scale check instead of the eleven somebody wrote down. It is
    # what found `Env` (559 chars) and `Prov` (442): both were audited at
    # scale along the VALUE axis and neither along the NAME axis.
    for key, (obj, path) in sorted(worst_instances(SCALE_PROBE).items()):
        bad, text = check_repr(obj)
        scale.append({"case": "derived/" + key[1],
                      "class": type(obj).__name__, "path": path,
                      "repr_len": len(text), "repr": text,
                      "violations": bad})
    n_bad = (sum(1 for r in rows if r["violations"])
             + sum(1 for r in scale if r["violations"]))
    return {"rows": rows, "scale": scale, "crawl": stats,
            "repr_cap": V.REPR_CAP, "violations": n_bad,
            "manifest": probe_manifest()}


_SEED_SNIPPET = (
    "import sys, json; sys.path.insert(0, %r);"
    "import reprsweep as R;"
    "print(json.dumps([[r['class'], r['repr']] for r in R.audit()['rows']]))"
)


def seed_check(seeds=("0", "1", "12345")):
    """R3: the same reprs in three processes with different hash seeds.

    Round 481 found a 66-round-old nondeterminism in `wiring_audit`'s
    `best_incoming` by computing one value twice, and its next-step 5 asked
    for exactly this shape of check on other derived values. A repr is a
    derived value, `PMap` iterates a tree whose keys are strings, and
    `dir()` ordering feeds the crawl — so the question is real here and not
    borrowed.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    out = []
    for seed in seeds:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, "-c", _SEED_SNIPPET % here],
                              cwd=here, env=env, capture_output=True,
                              text=True)
        if proc.returncode != 0:
            return {"ok": False, "seed": seed, "stderr": proc.stderr[-800:]}
        out.append((seed, json.loads(proc.stdout)))
    first = out[0][1]
    diffs = [{"seed": s, "expected": first, "got": got}
             for s, got in out[1:] if got != first]
    return {"ok": not diffs, "seeds": list(seeds), "n_classes": len(first),
            "diffs": diffs}


def main(argv):
    if "--manifest" in argv:
        man = probe_manifest()
        if "--json" in argv:
            print(json.dumps(man, indent=1))
        else:
            print("derived probe: %d node class(es) / %d builtin(s) / %d "
                  "runtime class(es)"
                  % (man["nodes"]["universe"], man["builtins"]["universe"],
                     man["runtime"]["universe"]))
            print("universe %d, reached %d, declared unreachable %d, "
                  "gaps %d, stale exception(s) %d"
                  % (man["universe"], man["reached"],
                     man["declared_unreachable"], len(man["gaps"]),
                     len(man["stale_exceptions"])))
            for g in man["gaps"]:
                print("  GAP %s.%s" % (g[0], g[1]))
            for g in man["stale_exceptions"]:
                print("  STALE EXCEPTION %s.%s" % (g[0], g[1]))
        return 1 if (man["gaps"] or man["stale_exceptions"]) else 0
    if "--seeds" in argv:
        res = seed_check()
        print(json.dumps(res, indent=1) if "--json" in argv
              else ("R3 deterministic across %s: %s (%d classes)"
                    % (res.get("seeds"), "OK" if res["ok"] else "FAIL",
                       res.get("n_classes", 0))))
        return 0 if res["ok"] else 1
    private = "--private" in argv
    rep = audit(private=private)
    if "--json" in argv:
        print(json.dumps(rep, indent=1))
        return 1 if rep["violations"] else 0
    man = rep["manifest"]
    print("derived probe: universe %d, reached %d, declared unreachable %d,"
          " gaps %d" % (man["universe"], man["reached"],
                        man["declared_unreachable"], len(man["gaps"])))
    print("reachable from Interpreter.run() by a PUBLIC path: %d class(es)"
          "  [crawl %d steps, %s]"
          % (len(rep["rows"]), rep["crawl"]["steps"],
             "exhausted" if rep["crawl"]["exhausted"] else "complete"))
    print("%-4s %-12s %-16s %-5s %s"
          % ("", "module", "class", "len", "repr"))
    for r in rep["rows"]:
        mark = "FAIL" if r["violations"] else "ok"
        print("%-4s %-12s %-16s %-5d %s"
              % (mark, r["module"].split(".")[-1], r["class"],
                 r["repr_len"], r["repr"][:90]))
        for v in r["violations"]:
            print("       -> %s" % v)
    print("\nR2 at scale (cap %d):" % rep["repr_cap"])
    for c in rep["scale"]:
        print("%-4s %-20s %-5d %s"
              % ("FAIL" if c["violations"] else "ok", c["case"],
                 c["repr_len"], c["repr"][:80]))
        for v in c["violations"]:
            print("       -> %s" % v)
    print("\nviolations: %d" % rep["violations"])
    return 1 if rep["violations"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

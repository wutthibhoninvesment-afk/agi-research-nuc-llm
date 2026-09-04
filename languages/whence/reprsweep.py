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
    python3 reprsweep.py --inputs        # v0.49: every expression each
                                         #   repr interpolates, with the
                                         #   AXIS that says who sizes it
    python3 reprsweep.py --routing       # v0.49: does each repr's delegate
                                         #   closure contain `values._cap`
    python3 reprsweep.py --caps          # v0.49: R2 behaviourally — lower
                                         #   REPR_CAP and re-measure
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
    # v0.49 (round 492), decision 63. The five below entered the universe
    # when `package_classes()` replaced `runtime_classes()` in
    # `probe_manifest`. Until this round the universe was `ast_nodes` +
    # `values` + `interp` — three of the package's seven modules, chosen
    # by hand — so `gaps: 0` was a claim about a set that was itself a
    # list. None of the five is reached, and each says why in its own
    # terms rather than "internal".
    ("whence.ast_nodes", "Node"):
        "the abstract base every node class is built on top of by "
        "`_simple`. Never instantiated: `Node.__init__` is called by the "
        "generated `__init__` of a concrete subclass and by nothing else, "
        "so no object of this exact type exists to repr.",
    ("whence.lexer", "Token"):
        "a lexer token. Consumed by `Parser` and stored on no AST node — "
        "a node keeps its `line`, not the token it came from — so the "
        "whole token stream dies with `parse()`. It HAS a `__repr__` "
        "(`Token(NAME, 'x', 1:1)`), which is the host convention for a "
        "compiler-internal record and is not a caller surface.",
    ("whence.lexer", "LexError"):
        "an exception. It is handed to a caller — by being raised — but "
        "its rendering is a DIAGNOSTIC and diagnostics are decision 48's, "
        "not decision 60's. Measured rather than assumed: the longest "
        "`repr` this round could provoke is 147 characters, on a 5 000-"
        "character string literal, because the message quotes the "
        "SYNTAX at fault and never the offending token's text.",
    ("whence.parser", "ParseError"):
        "an exception, same reason as `lexer.LexError`, and measured the "
        "same way (120 characters on a 400-character identifier).",
    ("whence.parser", "Parser"):
        "the parser itself. `parse(src)` builds one, runs it and drops "
        "it; it is stored on no node, no value and no Interpreter.",
}

#: Classes a CALLER constructs directly from this package, which the crawl
#: therefore cannot reach and which are surfaces anyway.
#:
#: Decision 60's rule is written as "reachable from `Interpreter.run()`
#: along a path of PUBLIC attribute names", and that reachability is a
#: SUFFICIENT condition for being a surface, not a necessary one. Decision
#: 58's sentence is the general one — *a value this implementation hands a
#: caller is a surface* — and a class the caller constructs is on the same
#: side of the boundary as one it is handed. `Interpreter` satisfies both
#: (the crawl finds it at `run().parent.interp`, and it is also the first
#: thing any embedder builds); `TimeTravelDebugger` satisfies only the
#: second, which is why it sat outside every sweep this program has run
#: while reprring as `<whence.timetravel.TimeTravelDebugger object at
#: 0x...>` — decision 58's ORIGINAL failure string, in the one module the
#: universe never contained.
#: Each row is `(why, factory)`; the factory builds a witness the same way
#: a caller would, and `audit()` checks its repr against R1-R4 exactly as
#: it checks a crawled one.
CONSTRUCTED_SURFACES = {
    ("whence.timetravel", "TimeTravelDebugger"): (
        "a host-side debugging helper (round 132). Never wired into "
        "`Interpreter` and reachable from no value, so the crawl cannot "
        "find it — and it is held by a caller, in a debugger, which is "
        "the exact situation decision 58 was filed about.",
        lambda: _ttd_witness(),
    ),
}


def _ttd_witness(n_checkpoints=9, name_len=400):
    """A `TimeTravelDebugger` at scale, built through the PUBLIC API.

    Both axes on at once — more checkpoints than the repr lists AND names
    longer than its listing bound — because a witness with one axis off is
    how `Env`'s scale case passed for six rounds (v0.48). Built by running
    real programs and calling `snapshot`, not by writing the object's
    slots, which is how this round found that `snapshot` raised against
    every real `Env`.
    """
    from whence.timetravel import TimeTravelDebugger
    ttd = TimeTravelDebugger()
    for i in range(n_checkpoints):
        env = Interpreter().run('let _last_snap_name = "c%d%s"\n'
                                % (i, "z" * name_len))
        ttd.snapshot(env)
    return ttd


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


def package_classes():
    """Every class DEFINED anywhere in the `whence` package, deduped by
    identity.

    v0.49 (round 492), decision 63. `runtime_classes()` reads `values` and
    `interp`; `node_classes()` reads `ast_nodes`. Together they are three
    of the package's SEVEN modules, and the other four were not excluded
    by an argument — they were never enumerated, so `probe_manifest()`'s
    `gaps: 0` was scoped to a set that was itself a hand-written list. The
    widening adds six classes and found one real defect: `timetravel.
    TimeTravelDebugger` reprs with a heap address.
    """
    import inspect
    import importlib
    here = os.path.dirname(os.path.abspath(__file__))
    out, seen = set(), set()
    for name in sorted(os.listdir(os.path.join(here, "whence"))):
        if not name.endswith(".py"):
            continue
        mod_name = "whence" if name == "__init__.py" else "whence." + name[:-3]
        mod = importlib.import_module(mod_name)
        for _attr, obj in vars(mod).items():
            if (inspect.isclass(obj) and obj.__module__ == mod.__name__
                    and id(obj) not in seen):
                seen.add(id(obj))
                out.add((mod.__name__, obj.__name__))
    return out


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
    universe = package_classes()
    found, _stats = reachable()
    covered = set(found) | set(CONSTRUCTED_SURFACES)
    unreached = sorted(universe - covered)
    return {
        "nodes": {"universe": len(nodes), "with_source": len(NODE_SOURCE)},
        "builtins": {"universe": len(sigs), "overridden": len(ARG_OVERRIDE)},
        "runtime": {"universe": len(runtime),
                    "with_source": len(VALUE_SOURCE)},
        "universe": len(universe),
        "reached": len(found),
        "constructed": len(CONSTRUCTED_SURFACES),
        "declared_unreachable": len(UNREACHABLE),
        "gaps": [list(k) for k in unreached if k not in UNREACHABLE],
        "stale_exceptions": [list(k) for k in sorted(UNREACHABLE)
                             if k in covered],
        # v0.49: the OTHER direction. `universe - found` was the only
        # comparison this manifest made, so a class the crawl reached from
        # a module the universe did not contain was invisible to it — the
        # failure it exists to prevent, one level up. 0 at HEAD; it is a
        # negative control, not a finding.
        "outside_universe": [list(k) for k in sorted(set(found) - universe)],
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


# ==========================================================================
# v0.49 (round 492), decision 63 — the INPUTS of a repr, and who sizes them
# ==========================================================================
#
# v0.48 varied three tokens — a string body, an identifier, a digit run —
# because those are the three a Whence PROGRAM can make arbitrarily long,
# and every probe in this file is a program. Round 488's own next-step 1
# asked the question that framing cannot answer: *list the inputs each repr
# interpolates and say which of them an author sizes.* An input is not
# always program text. `Interpreter.__repr__` interpolates `self.max_depth`,
# which is a constructor argument of the embedding API — no program of any
# size moves it, and no probe that is a program ever can.
#
# So the subject set here is not classes and not tokens: it is the
# EXPRESSIONS each repr interpolates, derived from the source with `ast`,
# and each one is assigned an AXIS with a family saying who sizes it. Both
# directions are gated, the way `UNREACHABLE` is: an expression with no
# entry is an ERROR, and an entry naming an expression no repr interpolates
# is a STALE one. The table keys are the unparsed expression text, so
# editing a repr expires its own classification rather than silently
# inheriting it.

import ast                                              # noqa: E402
import inspect                                          # noqa: E402
import textwrap                                         # noqa: E402
import types                                            # noqa: E402


#: Functions a repr delegates to that this analysis does NOT descend into,
#: and why. Checked in both directions by `delegate_manifest()`: a name here
#: that nothing calls is stale. The boundary is not a shortcut — it is the
#: statement that the function on the other side is audited by a different
#: instrument.
DELEGATE_BOUNDARY = {
    "whence.values.show_payload":
        "the language's own bounded snapshot renderer (decisions 52/53). "
        "It takes an explicit `limit` from every caller here, is the "
        "subject of its own tests and of `depthcensus.py`, and rendering "
        "rules for it are a Whence-level surface rather than a host repr. "
        "Every call site in a repr passes `SHOW_LIMIT` or `SHOW_LIMIT * 2`, "
        "which `test_v49` pins.",
    "whence.values.PMap.items":
        "a data accessor, not a renderer. It yields the map's `(key, "
        "value)` pairs and contributes no text of its own; what reaches "
        "the string is `keys`, and that is classified where it is "
        "interpolated, at `PMap.__repr__`. Descending into it also pulled "
        "in `values._pinorder`, an AVL walk, which is a tree traversal "
        "listed among things that become characters.",
}


def _fn_key(fn):
    """The stable name of one repr source. `__qualname__`, so the 22 AST
    node classes — which share ONE function object built by `_simple` —
    collapse to one key instead of twenty-two, and `values.Value` (a second
    name for `Prov`) collapses into it."""
    return "%s.%s" % (fn.__module__, fn.__qualname__)


def _fn_source(fn):
    return textwrap.dedent(inspect.getsource(fn))


def _callees(fn, owner=None):
    """Whence-package functions this one calls, resolved three ways: the
    module globals, any function-local `from whence... import`, and — when
    `owner` is given — a `self.NAME(...)` call against the owning class.

    Each of the three was load-bearing when it was added, and the second
    and third were added because the resolver was WRONG without them.

      * the local import: `ast_nodes._simple.<locals>.__repr__` reaches
        `_cap` by `from whence.values import _cap` INSIDE the function
        body, so a globals-only resolver reports that repr as calling
        nothing — which is the answer `Interpreter.__repr__` gives for a
        real reason, and the two must not look alike.
      * the method: the same repr's whole body is `_cap(self._repr_at(0))`,
        and `_repr_at` is a closure `_simple` puts in the class dict, not a
        module global. Without this branch the closure stopped at
        `__repr__` and never reached `_node_field` — the function round
        488's OWN R2 violation was fixed in. A delegate analysis that
        cannot see a method is blind to the delegate that has the defect.
    """
    tree = ast.parse(_fn_source(fn))
    local = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module \
                and node.module.startswith("whence"):
            mod = __import__(node.module, fromlist=["_"])
            for alias in node.names:
                local[alias.asname or alias.name] = getattr(
                    mod, alias.name, None)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    mod = sys.modules[fn.__module__]
    out = []
    for name in sorted(names):
        obj = local.get(name, getattr(mod, name, None))
        if obj is None and owner is not None:
            for klass in getattr(owner, "__mro__", (owner,)):
                if name in klass.__dict__:
                    obj = klass.__dict__[name]
                    break
        if isinstance(obj, types.FunctionType) \
                and obj.__module__.startswith("whence"):
            out.append((obj, owner))
    return out


def delegate_closure(fn, owner=None):
    """`{key: fn}` for `fn` and every whence function it transitively
    calls, stopping at `DELEGATE_BOUNDARY`. Insertion-ordered."""
    out, queue = {}, [(fn, owner)]
    while queue:
        cur, cur_owner = queue.pop(0)
        key = _fn_key(cur)
        if key in out or key in DELEGATE_BOUNDARY:
            continue
        out[key] = cur
        queue.extend(_callees(cur, cur_owner))
    return out


def _resolve_class(mod_name, cls_name):
    """The class object behind a `(module, name)` key from the crawl. The
    crawl keys on `type(obj).__name__`, which is not always the module
    attribute name (`values.Value` is a second binding of `Prov`)."""
    mod = sys.modules.get(mod_name)
    if mod is None:                      # a module no crawl has imported
        import importlib
        mod = importlib.import_module(mod_name)
    cls = getattr(mod, cls_name, None)
    if cls is not None:
        return cls
    for obj in vars(mod).values():
        if getattr(obj, "__name__", None) == cls_name:
            return obj
    return None


def repr_functions():
    """`{(module, class): fn}` — the `__repr__` of every class the sweep
    REACHES. Derived from `reachable()`, never listed: a class that becomes
    reachable brings its repr into this analysis the same round."""
    found, _stats = reachable()
    out = {}
    # the constructed surfaces too: they are audited by `audit()` and their
    # reprs interpolate inputs like everybody else's, so leaving them out
    # of the enumeration would classify the classes and not the strings.
    for mod_name, cls_name in sorted(set(found) | set(CONSTRUCTED_SURFACES)):
        cls = _resolve_class(mod_name, cls_name)
        fn = cls.__dict__.get("__repr__") if cls is not None else None
        if fn is not None:
            out[(mod_name, cls_name)] = fn
    return out


def repr_sources():
    """`{key: fn}` — every repr the sweep reaches PLUS its delegate
    closure. This is the set the input enumeration runs over."""
    out = {}
    for (mod_name, cls_name), fn in repr_functions().items():
        out.update(delegate_closure(fn, _resolve_class(mod_name, cls_name)))
    return out


def _is_str_const(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def interpolated_inputs(src):
    """Every expression whose TEXT reaches the string this function
    returns, as unparsed source, deduped in first-seen order.

    Deliberately OVER-inclusive. The failure mode round 488 named is an
    enumeration that misses a member; an extra row costs one table entry
    and a missing one costs a whole axis. Five constructs count:

      "fmt" % x        each operand (tuple elements flattened)
      f"...{x}..."     each `FormattedValue`
      "lit" + x        the non-literal side of a concatenation
      sep.join(x)      the argument
      return x         a returned Call/Name/Attribute/Subscript/IfExp,
                       because `ast_nodes._node_field` ends in a bare
                       `return repr(v)` and that is where a 5,000-character
                       string literal entered the AST repr in v0.48.
      f(x) at a        a call to a `DELEGATE_BOUNDARY` function, recorded
      BOUNDARY         whole. A boundary is where this enumeration stops,
                       so what CROSSES it has to be named or the stop is a
                       blind spot. Without this rule `Guess.__repr__`
                       (`_frame(show_payload(...))`) reported ONE input,
                       the composite, while `Record.__repr__`
                       (`_frame("record " + show_payload(...))`) reported
                       the same `show_payload` call as its own — the same
                       delegate classified in one class and invisible in
                       the other, decided by whether a literal happened to
                       be concatenated next to it.

    `x += "...%d" % n` is NOT a rule of its own: the `%` inside it already
    reports `n`, and an `AugAssign` rule additionally reported `1` from
    `depth += 1` — an integer, in a list of things that become text.
    """
    tree = ast.parse(src)
    boundary = {key.rsplit(".", 1)[-1] for key in DELEGATE_BOUNDARY}
    out, seen = [], set()

    def add(node):
        text = ast.unparse(node)
        if text not in seen:
            seen.add(text)
            out.append(text)

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) \
                and _is_str_const(node.left):
            rhs = node.right
            for elt in (rhs.elts if isinstance(rhs, ast.Tuple) else [rhs]):
                add(elt)
        elif isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.FormattedValue):
                    add(part.value)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) \
                and (_is_str_const(node.left) or _is_str_const(node.right)):
            for side in (node.left, node.right):
                if _is_str_const(side) or isinstance(side, ast.BinOp):
                    continue
                add(side)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "join":
            for arg in node.args:
                add(arg)
        elif isinstance(node, ast.Return) and node.value is not None:
            if isinstance(node.value, (ast.Call, ast.Name, ast.Attribute,
                                       ast.Subscript, ast.IfExp)):
                add(node.value)
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
            if name in boundary:
                add(node)
    return out


def repr_inputs():
    """`{source_key: [expression, ...]}` over `repr_sources()`."""
    return {key: interpolated_inputs(_fn_source(fn))
            for key, fn in sorted(repr_sources().items())}



#: THE AXIS TABLE. One row per way a repr's rendering can grow, with the
#: FAMILY that says who sizes it. The families are the point of this
#: decision:
#:
#:   text       program TEXT the author types — a string body, an
#:              identifier, a digit run. v0.48 varies these three and only
#:              these three, because every probe in this file is a program
#:              and these are what a program can make arbitrarily long.
#:   structure  program STRUCTURE — how many elements, how many parameters,
#:              how deep, which line. An author sizes these by writing MORE
#:              program rather than a longer token. Round 482's eleven
#:              hand-written cases covered five of them by accident.
#:   embedding  the EMBEDDING API — a constructor argument or a host-built
#:              value. **No program of any size moves one of these, so no
#:              probe that is a program can ever vary them.** This is the
#:              family v0.48's derivation could not have reached, and the
#:              R2 violation this round found is in it.
#:   constant   fixed by the implementation: a class name, a slot name, a
#:              plural 's', an op token. Not author-sized, no witness.
#:   internal   text this function composed from its OWN other inputs. Not
#:              a root, and audited by the inputs it is composed from.
#:
#: `author_sized` is what "does an author size this" means operationally:
#: True demands a WITNESS that makes the axis large, and
#: `axis_manifest()["axes_without_witness"]` is an error.
AXES = {
    "text.identifier": {
        "family": "text", "author_sized": True,
        "what": "a name the author types — a binding, a function name, a "
                "record field, a `-> Type` label. v0.48's `__N__`.",
    },
    "text.node_scalar": {
        "family": "text", "author_sized": True,
        "what": "a host scalar stored on an AST node and rendered by a "
                "bare `repr()` — a string literal's body, a numeral, an "
                "identifier. The v0.48 R2 violation was here.",
    },
    "text.payload_snapshot": {
        "family": "text", "author_sized": True,
        "what": "`show_payload(...)`, the language's own bounded snapshot "
                "of a whole value. Carries every text token at once, "
                "across the `DELEGATE_BOUNDARY`.",
    },
    "text.miss_reason": {
        "family": "text", "author_sized": True,
        "what": "the reason strings on a `Miss` — `miss \"...\"` is author "
                "text and a runtime failure's reason quotes author text.",
    },
    "structure.element_count": {
        "family": "structure", "author_sized": True,
        "what": "how many elements, fields, names or provenance inputs, "
                "rendered as a decimal count or as a bounded head of them.",
    },
    "structure.arity": {
        "family": "structure", "author_sized": True,
        "what": "a closure's parameter list, and a builtin's `arity` in "
                "each of its three spellings (int, (min, max), None).",
    },
    "structure.scope_depth": {
        "family": "structure", "author_sized": True,
        "what": "how many enclosing `Env`s — `Env.__repr__` WALKS the "
                "parent chain to count them.",
    },
    "structure.nest_depth": {
        "family": "structure", "author_sized": True,
        "what": "AST nesting depth, which `_node_field` recurses over "
                "(cut at `REPR_NEST`).",
    },
    "structure.line_number": {
        "family": "structure", "author_sized": True,
        "what": "which source line a thing is on — grows with the LENGTH "
                "of the program, not with any one token.",
    },
    "structure.merge_count": {
        "family": "structure", "author_sized": True,
        "what": "`MergedProv.count`, the number of steps one node stands "
                "for. An author sizes it with a longer tail loop.",
    },
    "structure.reason_count": {
        "family": "structure", "author_sized": True,
        "what": "how many distinct reasons a `Miss` carries, cut to "
                "`_MISS_REPR_REASONS` with a counted tail.",
    },
    "embedding.max_depth": {
        "family": "embedding", "author_sized": True,
        "what": "`Interpreter(max_depth=N)`. A PUBLIC constructor argument "
                "of the embedding API, interpolated with `%s`. No Whence "
                "program moves it, so no program-shaped probe varies it.",
    },
    "embedding.global_count": {
        "family": "embedding", "author_sized": True,
        "what": "`len(interp.globals.vars)` — 37 builtins at HEAD, plus "
                "whatever an embedder binds into the global scope.",
    },
    "constant.class_name": {
        "family": "constant", "author_sized": False,
        "what": "a host class name (`type(v).__name__`, `_simple`'s "
                "`name`). Fixed by this implementation.",
    },
    "constant.field_name": {
        "family": "constant", "author_sized": False,
        "what": "an AST node's `__slots__` entry. Fixed by this "
                "implementation.",
    },
    "constant.literal_choice": {
        "family": "constant", "author_sized": False,
        "what": "a two-way pick between literals — a plural 's', "
                "'globals'/'scope', '[…]'/'[]'.",
    },
    "constant.op_token": {
        "family": "constant", "author_sized": False,
        "what": "`Prov.op`, the provenance op. MEASURED, not assumed: 45 "
                "distinct values over the derived probe, longest 10 "
                "characters ('confidence'), every one an operator, "
                "keyword or builtin name. `test_v49` pins that — the day "
                "an op embeds an author's identifier this row is wrong "
                "and the pin says so.",
    },
    "constant.builtin_name": {
        "family": "constant", "author_sized": False,
        "what": "`Builtin.name`, one of the 37 names `_install_builtins` "
                "writes. There is no public API for registering a "
                "builtin, so an embedder cannot size it either.",
    },
    "internal.composed": {
        "family": "internal", "author_sized": False,
        "what": "text this function built from its own other inputs — a "
                "join, a partial format, the value handed to `_frame`/"
                "`_cap`. Audited through the inputs it is composed from.",
    },
}

#: EVERY interpolated expression, mapped to its axis. Keyed by
#: `(source_key, expression_text)`, so editing a repr expires its own
#: classification instead of silently inheriting it. Both directions are
#: gated by `axis_manifest()`: an expression with no row is `unclassified`
#: (an ERROR — it is a way the string can grow that nobody has named), and
#: a row naming an expression no repr interpolates is `stale`.
INPUT_AXIS = {
    # ---- ast_nodes._node_field: the generated AST repr's field renderer
    ("whence.ast_nodes._node_field", "repr(v)"): "text.node_scalar",
    ("whence.ast_nodes._node_field", "v._repr_at(depth + 1)"):
        "structure.nest_depth",
    ("whence.ast_nodes._node_field", "'[…]' if v else '[]'"):
        "constant.literal_choice",
    ("whence.ast_nodes._node_field", "type(v).__name__"):
        "constant.class_name",
    ("whence.ast_nodes._node_field",
     "', '.join((_node_field(e, depth + 1) for e in v))"):
        "internal.composed",
    ("whence.ast_nodes._node_field",
     "', '.join((_node_field(e, depth + 1) for e in head))"):
        "internal.composed",
    ("whence.ast_nodes._node_field",
     "(_node_field(e, depth + 1) for e in v)"): "structure.element_count",
    ("whence.ast_nodes._node_field",
     "(_node_field(e, depth + 1) for e in head)"):
        "structure.element_count",
    # ---- the generated node repr and its walk
    ("whence.ast_nodes._simple.<locals>.__repr__", "_cap(self._repr_at(0))"):
        "internal.composed",
    ("whence.ast_nodes._simple.<locals>._repr_at",
     "('%s=%s' % (f, _node_field(getattr(self, f), depth)) for f in slots)"):
        "internal.composed",
    ("whence.ast_nodes._simple.<locals>._repr_at", "name"):
        "constant.class_name",
    ("whence.ast_nodes._simple.<locals>._repr_at", "parts"):
        "internal.composed",
    ("whence.ast_nodes._simple.<locals>._repr_at", "f"):
        "constant.field_name",
    ("whence.ast_nodes._simple.<locals>._repr_at",
     "_node_field(getattr(self, f), depth)"): "internal.composed",
    # ---- interp.Env
    ("whence.interp.Env.__repr__", "shown"): "text.identifier",
    ("whence.interp.Env.__repr__", "extra"): "structure.element_count",
    ("whence.interp.Env.__repr__",
     "'globals' if self.interp is not None else 'scope'"):
        "constant.literal_choice",
    ("whence.interp.Env.__repr__", "len(names)"): "structure.element_count",
    ("whence.interp.Env.__repr__", "'' if len(names) == 1 else 's'"):
        "constant.literal_choice",
    ("whence.interp.Env.__repr__", "' (%s)' % listing if names else ''"):
        "internal.composed",
    ("whence.interp.Env.__repr__", "depth"): "structure.scope_depth",
    ("whence.interp.Env.__repr__", "listing"): "internal.composed",
    # ---- interp.Interpreter — the embedding family, and the violation
    ("whence.interp.Interpreter.__repr__", "n"): "embedding.global_count",
    ("whence.interp.Interpreter.__repr__", "'' if n == 1 else 's'"):
        "constant.literal_choice",
    ("whence.interp.Interpreter.__repr__", "_clip(str(self.max_depth))"):
        "embedding.max_depth",
    # ---- values.Builtin
    ("whence.values.Builtin.__repr__", "self.name"): "constant.builtin_name",
    ("whence.values.Builtin.__repr__", "n"): "internal.composed",
    ("whence.values.Builtin.__repr__", "a[0]"): "structure.arity",
    ("whence.values.Builtin.__repr__", "a[1]"): "structure.arity",
    ("whence.values.Builtin.__repr__", "a"): "structure.arity",
    ("whence.values.Builtin.__repr__", "'' if a == 1 else 's'"):
        "constant.literal_choice",
    # ---- values.Closure
    ("whence.values.Closure.__repr__", "self.params"): "structure.arity",
    ("whence.values.Closure.__repr__", "self.ret_label"): "text.identifier",
    ("whence.values.Closure.__repr__", "self.name or ''"): "text.identifier",
    ("whence.values.Closure.__repr__", "params"): "internal.composed",
    ("whence.values.Closure.__repr__", "ret"): "internal.composed",
    ("whence.values.Closure.__repr__",
     "'' if where is None else ' at line %d' % where"): "internal.composed",
    ("whence.values.Closure.__repr__", "where"): "structure.line_number",
    # ---- values.Explanation / Guess / Record / WList — the snapshot half
    ("whence.values.Explanation.__repr__",
     "show_payload(self.root.payload, SHOW_LIMIT)"): "text.payload_snapshot",
    ("whence.values.Guess.__repr__", "show_payload(self, SHOW_LIMIT * 2)"):
        "text.payload_snapshot",
    ("whence.values.Record.__repr__", "show_payload(self, SHOW_LIMIT * 2)"):
        "text.payload_snapshot",
    ("whence.values.WList.__repr__", "show_payload(self, SHOW_LIMIT * 2)"):
        "text.payload_snapshot",
    ("whence.values.WList.__repr__", "len(self)"): "structure.element_count",
    # ---- values.Prov / MergedProv
    ("whence.values.Prov.__repr__", "self.op"): "constant.op_token",
    ("whence.values.Prov.__repr__", "_clip(self.detail)"): "text.identifier",
    ("whence.values.Prov.__repr__", "self.line"): "structure.line_number",
    ("whence.values.Prov.__repr__", "len(self.inputs)"):
        "structure.element_count",
    ("whence.values.Prov.__repr__", "self.show"): "text.payload_snapshot",
    ("whence.values.MergedProv.__repr__", "self.op"): "constant.op_token",
    ("whence.values.MergedProv.__repr__", "_clip(self.detail)"):
        "text.identifier",
    ("whence.values.MergedProv.__repr__", "self.line"):
        "structure.line_number",
    ("whence.values.MergedProv.__repr__", "self.count"):
        "structure.merge_count",
    ("whence.values.MergedProv.__repr__", "len(self.inputs)"):
        "structure.element_count",
    ("whence.values.MergedProv.__repr__", "self.show"):
        "text.payload_snapshot",
    # ---- values.Miss
    ("whence.values.Miss.__repr__", "shown"): "text.miss_reason",
    ("whence.values.Miss.__repr__", "extra"): "structure.reason_count",
    ("whence.values.Miss.__repr__", "body"): "internal.composed",
    # ---- values.PMap
    ("whence.values.PMap.__repr__", "shown"): "text.identifier",
    ("whence.values.PMap.__repr__", "extra"): "structure.element_count",
    ("whence.values.PMap.__repr__", "len(keys)"): "structure.element_count",
    ("whence.values.PMap.__repr__", "'' if len(keys) == 1 else 's'"):
        "constant.literal_choice",
    ("whence.values.PMap.__repr__", "' (%s)' % listing if keys else ''"):
        "internal.composed",
    ("whence.values.PMap.__repr__", "self.items()"):
        "structure.element_count",
    ("whence.values.PMap.__repr__", "listing"): "internal.composed",
    # ---- timetravel.TimeTravelDebugger, a CONSTRUCTED surface. Its repr
    # follows `Env`'s shape exactly, so its rows are `Env`'s rows: a
    # bounded head of caller-chosen names, and two counts.
    ("whence.timetravel.TimeTravelDebugger.__repr__", "shown"):
        "text.identifier",
    ("whence.timetravel.TimeTravelDebugger.__repr__", "extra"):
        "structure.element_count",
    ("whence.timetravel.TimeTravelDebugger.__repr__", "len(names)"):
        "structure.element_count",
    ("whence.timetravel.TimeTravelDebugger.__repr__",
     "'' if len(names) == 1 else 's'"): "constant.literal_choice",
    ("whence.timetravel.TimeTravelDebugger.__repr__",
     "' (%s)' % listing if names else ''"): "internal.composed",
    ("whence.timetravel.TimeTravelDebugger.__repr__", "listing"):
        "internal.composed",
    # ---- the shared helpers. Every row here is `internal.composed` by
    # construction: these three functions take a string somebody else built
    # and cut it, which is the whole reason R2 can live in one place.
    ("whence.values._cap", "out"): "internal.composed",
    ("whence.values._cap", "out[:REPR_CAP - 1 - len(close)]"):
        "internal.composed",
    ("whence.values._clip",
     "text if len(text) <= limit else text[:limit - 1] + '…'"):
        "internal.composed",
    ("whence.values._clip", "text[:limit - 1]"): "internal.composed",
    ("whence.values._frame", "_cap('<whence ' + body + '>', '>')"):
        "internal.composed",
    ("whence.values._frame", "body"): "internal.composed",
}

def _returned_delegate_calls(fn):
    """Unparsed text of every `return <whence delegate>(...)` in `fn`.

    Thirteen of the eighteen sources end in `return _frame(...)` or
    `return _cap(...)` wrapping their whole format expression. Those rows
    are `internal.composed` by construction — the wrapped call's own inputs
    are enumerated under the delegate's key, and the format string's
    operands under this one — so they are classified by this RULE rather
    than by thirteen 200-character literal keys nobody would ever read.
    An explicit `INPUT_AXIS` row WINS over this rule, which is how
    `_node_field`'s `return v._repr_at(depth + 1)` keeps its real axis
    (`structure.nest_depth`): that return is a recursion, not a cut.
    """
    names = {fn_.__name__ for fn_, _owner in _callees(fn, None)}
    names |= {"_cap", "_frame", "_clip"}
    out = set()
    for node in ast.walk(ast.parse(_fn_source(fn))):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Call):
            f = node.value.func
            nm = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
            if nm in names:
                out.add(ast.unparse(node.value))
    return out


def axis_manifest():
    """The classification, as data, gated in BOTH directions.

    `unclassified` is an expression that becomes characters and that nobody
    has said who sizes. `stale` is a row naming an expression no repr
    interpolates any more. `axes_without_witness` is an axis declared
    author-sized with nothing that makes it large — the v0.48 failure in
    its general form, since "we vary this axis" is a claim about a witness
    and not about a table.
    """
    inputs = repr_inputs()
    sources = repr_sources()
    auto = {}
    for key, fn in sources.items():
        for text in _returned_delegate_calls(fn):
            auto[(key, text)] = "internal.composed"
    seen, unclassified, by_axis, n_auto = set(), [], {}, 0
    for key, exprs in inputs.items():
        for expr in exprs:
            pair = (key, expr)
            axis = INPUT_AXIS.get(pair)
            if axis is None:
                axis = auto.get(pair)
                if axis is not None:
                    n_auto += 1
            if axis is None:
                unclassified.append([key, expr])
                continue
            if pair in INPUT_AXIS:
                seen.add(pair)
            by_axis.setdefault(axis, []).append([key, expr])
    stale = [list(p) for p in sorted(INPUT_AXIS) if p not in seen]
    unknown_axis = sorted({a for a in by_axis if a not in AXES})
    by_family = {}
    for axis, rows in by_axis.items():
        fam = AXES.get(axis, {}).get("family", "?")
        by_family[fam] = by_family.get(fam, 0) + len(rows)
    witnessed = {label.split("/")[0] for label, _obj in axis_cases()}
    missing = sorted(a for a, spec in AXES.items()
                     if spec["author_sized"] and a not in witnessed)
    unused = sorted(a for a in witnessed if a not in AXES)
    return {
        "sources": len(inputs),
        "inputs": sum(len(v) for v in inputs.values()),
        "classified_by_table": len(seen),
        "classified_by_rule": n_auto,
        "unclassified": unclassified,
        "stale": stale,
        "unknown_axis": unknown_axis,
        "by_axis": {a: len(rows) for a, rows in sorted(by_axis.items())},
        "by_family": by_family,
        "author_sized_axes": sorted(a for a, s in AXES.items()
                                    if s["author_sized"]),
        "axes_without_witness": missing,
        "witnesses_without_axis": unused,
    }


def routing_manifest():
    """R2's routing, derived: does each reached repr's DELEGATE CLOSURE
    contain `values._cap`?

    This is the static half of round 488's next-step 4, which asked for
    `test_cap_is_the_only_place_repr_cap_is_compared` — a regex over source
    lines — to be replaced by something behavioural. It is replaced by TWO
    checks, and neither subsumes the other:

      * this one is STATIC and total. It is blind to a repr that calls
        `_cap` and throws the result away.
      * `cap_response()` is BEHAVIOURAL and blind to a repr that is shorter
        than the cap on every witness anybody built — it reports that
        blindness as `vacuous`, which is the honest form.

    At HEAD `whence.interp.Interpreter.__repr__` is the only repr with an
    EMPTY closure past itself, and that is not a coincidence: it is the
    class whose only unbounded input comes from the embedding API.
    """
    rows = []
    for (mod, cls), fn in sorted(repr_functions().items()):
        closure = delegate_closure(fn, _resolve_class(mod, cls))
        rows.append({
            "module": mod, "class": cls,
            "delegates": sorted(k for k in closure if k != _fn_key(fn)),
            "routes_through_cap": "whence.values._cap" in closure,
        })
    return {"rows": rows,
            "unrouted": [[r["module"], r["class"]] for r in rows
                         if not r["routes_through_cap"]]}


#: The scale tokens, reused so that a witness wanting "a long identifier"
#: and the v0.48 scale probe mean the same thing by it.
_BIG_NAME = _BIG["__N__"]
_BIG_STR = _BIG["__S__"]
_BIG_DIGITS = _BIG["__D__"]

#: How many function definitions the scope-depth witness nests. Whence
#: scopes are LEXICAL, so a recursive call does NOT deepen the chain (a
#: call Env's parent is the closure's DEFINING Env, which for a top-level
#: recursive function is always `globals`). What deepens it is a nested
#: definition whose closure is then CALLED, one level at a time, and
#: `parser._enter` caps nesting at 60. 20 nested definitions chained
#: through 19 calls give a parent chain of 39 — measured, and pinned by
#: `test_v49.py::test_the_scope_depth_witness_really_is_deep`, because a
#: witness for an axis that does not actually move the axis is the exact
#: v0.48 failure (`Env`'s scale case ran with its own axis switched off).
_SCOPE_NEST = 20
#: Iterations the merge-count witness runs. `MergedProv.count` renders as
#: `x%d`, so this axis grows the string by ONE character per power of ten.
_MERGE_COUNT = 50000
#: Distinct reasons on the miss witness; `_MISS_REPR_REASONS` is 2, so any
#: number above 2 exercises the counted tail.
_REASON_COUNT = 20
#: Extra names the embedding witness binds into an Interpreter's globals.
_GLOBAL_PAD = 10000


def _run(src):
    return Interpreter().run(src)


def _scope_depth_source(nest=None):
    """A program whose deepest reachable `Env` has a long parent chain."""
    nest = _SCOPE_NEST if nest is None else nest
    lines = []
    for i in range(nest):
        lines.append("  " * i + "fn f%d() {" % i)
    lines.append("  " * nest + "1")
    for i in reversed(range(1, nest)):
        lines.append("  " * i + "}")
        lines.append("  " * (i - 1) + "  f%d" % i)
    lines.append("}")
    src = "\n".join(lines) + "\nlet v0 = f0()\n"
    for i in range(1, nest - 1):
        src += "let v%d = v%d()\n" % (i, i - 1)
    return src, "v%d" % (nest - 2)


def scope_depth_witness(nest=None):
    """The deepest `Env` a PROGRAM can put in front of a caller, plus the
    depth it actually reached."""
    src, last = _scope_depth_source(nest)
    payload = _run(src).get(last).payload
    env = payload.env
    depth, cur = 0, env
    while cur.parent is not None:
        depth += 1
        cur = cur.parent
    return env, depth


def _reason_count_witness():
    """A `Miss` carrying `_REASON_COUNT` distinct reasons."""
    terms = " + ".join('num("%s")' % ("z" * (i + 1))
                       for i in range(_REASON_COUNT))
    return _run("let m = %s\n" % terms).get("m").payload


def axis_cases():
    """`(label, object)` per AXIS, where the label is `<axis>/<detail>`.

    One witness per author-sized axis at MINIMUM — `axis_manifest()`'s
    `axes_without_witness` is an error, because an axis with no witness is
    a row in a table claiming coverage it does not have. That is the v0.48
    failure stated generally: the identifier axis was missing from nobody's
    table and from everybody's witness, and only the second one mattered.
    """
    cases = []

    # ---- family: text — what a program's TOKENS can be made long
    env = _run("let %s = 1\n" % _BIG_NAME)
    cases.append(("text.identifier/env-400", env))
    cases.append(("text.identifier/prov-400", env.get(_BIG_NAME)))
    rec = _run("let r = @{%s: 1}\n" % _BIG_NAME).get("r").payload
    cases.append(("text.identifier/record-field-400", rec))
    cases.append(("text.identifier/pmap-field-400", rec.fields))
    cases.append(("text.identifier/closure-400",
                  _run("fn %s(a) { a }\n" % _BIG_NAME)
                  .get(_BIG_NAME).payload))
    cases.append(("text.identifier/ttd-checkpoints-400", _ttd_witness()))
    cases.append(("text.node_scalar/str-5000",
                  _run('fn f() {\n  "%s"\n}\n' % _BIG_STR)
                  .get("f").payload.body))
    cases.append(("text.node_scalar/digits-3000",
                  _run("fn f() {\n  %s\n}\n" % _BIG_DIGITS)
                  .get("f").payload.body))
    cases.append(("text.node_scalar/name-400",
                  _run("fn f() {\n  let %s = 1\n  %s\n}\n"
                       % (_BIG_NAME, _BIG_NAME)).get("f").payload.body))
    cases.append(("text.payload_snapshot/list-3000",
                  _run("let xs = range(0, 3000)\n").get("xs").payload))
    cases.append(("text.payload_snapshot/guess-5000",
                  _run('let g = guess(1, 0.5, "%s")\n' % _BIG_STR)
                  .get("g").payload))
    cases.append(("text.payload_snapshot/why-3000",
                  _run("let e = why range(0, 3000)\n").get("e").payload))
    cases.append(("text.miss_reason/reason-5000",
                  _run('let m = miss "%s"\n' % _BIG_STR).get("m").payload))

    # ---- family: structure — what MORE program makes big
    src = "let r = @{" + ", ".join("k%d: %d" % (i, i)
                                   for i in range(400)) + "}\n"
    wide = _run(src).get("r").payload
    cases.append(("structure.element_count/record-400", wide))
    cases.append(("structure.element_count/pmap-400", wide.fields))
    cases.append(("structure.element_count/list-3000",
                  _run("let xs = range(0, 3000)\n").get("xs").payload))
    cases.append(("structure.element_count/env-400-names",
                  _run("".join("let n%d = %d\n" % (i, i)
                               for i in range(400)))))
    cases.append(("structure.arity/closure-60",
                  _run("fn wide(%s) { 1 }\n"
                       % ", ".join("p%d" % i for i in range(60)))
                  .get("wide").payload))
    # all three `arity` spellings: an int, a (min, max) pair, and None
    for name in ("len", "guess", "note"):
        cases.append(("structure.arity/builtin-%s" % name,
                      _run("let b = %s\n" % name).get("b").payload))
    cases.append(("structure.scope_depth/nested-%d" % _SCOPE_NEST,
                  scope_depth_witness()[0]))
    cases.append(("structure.nest_depth/paren-50",
                  _run("fn deep() { %s }\n" % ("(" * 50 + "1" + ")" * 50))
                  .get("deep").payload.body))
    cases.append(("structure.nest_depth/stmts-400",
                  _run("fn wide() {\n%s\n  v0\n}\n"
                       % "\n".join("  let v%d = %d" % (i, i)
                                   for i in range(400)))
                  .get("wide").payload.body))
    tall = "".join("let pad%d = %d\n" % (i, i) for i in range(5000))
    tenv = _run(tall + "fn late() { 1 }\nlet last = 1\n")
    cases.append(("structure.line_number/line-5002", tenv.get("last")))
    cases.append(("structure.line_number/closure-line-5001",
                  tenv.get("late").payload))
    loop = ("fn count(i, acc) { if i <= 0 { acc } else "
            "{ count(i - 1, acc + i) } }\nlet r = count(%d, 0)\n"
            % _MERGE_COUNT)
    root = _run(loop).get("r")
    merged = [p for p in root.inputs if type(p).__name__ == "MergedProv"]
    cases.append(("structure.merge_count/loop-%d" % _MERGE_COUNT,
                  merged[0] if merged else root))
    cases.append(("structure.reason_count/miss-%d" % _REASON_COUNT,
                  _reason_count_witness()))

    # ---- family: embedding — what NO program can move.
    # This is the whole point of decision 63. `max_depth` is a public
    # constructor argument, `%s`-interpolated into `Interpreter.__repr__`;
    # `globals.vars` is a public dict an embedder binds into. Neither is
    # reachable from any Whence source text, so `derive_probe(scale=True)`
    # — which is a PROGRAM — cannot vary either one however big its tokens.
    cases.append(("embedding.max_depth/10e500",
                  Interpreter(max_depth=10 ** 500)))
    interp = Interpreter()
    pad = interp.globals.vars.get("len")
    for i in range(_GLOBAL_PAD):
        interp.globals.vars["pad%d" % i] = pad
    cases.append(("embedding.global_count/%d" % _GLOBAL_PAD, interp))
    return cases


#: The caps `cap_response()` runs the sweep at. 240 is `REPR_CAP` itself;
#: 40 and 80 are below every fixed prose body in this tree, so a repr that
#: does not route through `_cap` cannot pass them by accident.
CAP_PROBE_VALUES = (40, 80, 240)


def cap_response(caps=CAP_PROBE_VALUES):
    """R2 as a BEHAVIOURAL property: lower `REPR_CAP` and re-measure.

    Round 488's next-step 4 asked for `test_cap_is_the_only_place_repr_cap_
    is_compared` — a regex over source lines — to be replaced by "a
    behavioural check over every class the sweep reaches". This is it: a
    repr that obeys the cap obeys whatever the cap SAYS, so lowering it and
    re-taking every repr finds a repr that ignores the cut however that cut
    is spelled (`min(len(x), REPR_CAP)`, a slice with no `if`, no cut at
    all), which the regex cannot.

    It has its own blind spot and reports it rather than hiding it: a repr
    already SHORTER than the lowest cap passes without demonstrating
    anything. Those rows are `vacuous`, counted, and printed. A gate that
    passes on an input it never exercised is worth exactly what round 490's
    `sar --strict`-on-zero-captures was worth.
    """
    subjects = [("class:%s.%s" % (k[0].split(".")[-1], k[1]), obj)
                for k, (obj, _p) in sorted(worst_instances(SCALE_PROBE).items())]
    subjects += [("axis:" + label, obj) for label, obj in axis_cases()]
    rows = []
    original = V.REPR_CAP
    try:
        base = {}
        V.REPR_CAP = original
        for label, obj in subjects:
            base[label] = len(repr(obj))
        for label, obj in subjects:
            entry = {"subject": label, "len_at_%d" % original: base[label],
                     "over": [], "vacuous": base[label] <= min(caps)}
            for cap in caps:
                V.REPR_CAP = cap
                if len(repr(obj)) > cap:
                    entry["over"].append({"cap": cap, "len": len(repr(obj))})
            entry["responds"] = not entry["over"]
            rows.append(entry)
    finally:
        V.REPR_CAP = original
    return {"caps": list(caps), "subjects": len(rows), "rows": rows,
            "vacuous": sum(1 for r in rows if r["vacuous"]),
            "failing": [r["subject"] for r in rows if not r["responds"]]}


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
    # v0.49 (round 492), decision 63: the surfaces a CALLER constructs.
    # The crawl starts at `run()` and cannot reach them; they are checked
    # by building one the way an embedder does. `timetravel.
    # TimeTravelDebugger` reprred with a heap address until this round.
    for key in sorted(CONSTRUCTED_SURFACES):
        _why, make = CONSTRUCTED_SURFACES[key]
        obj = make()
        bad, text = check_repr(obj)
        rows.append({"module": key[0], "class": key[1],
                     "path": "constructed by the caller",
                     "has_own_repr": "__repr__" in type(obj).__dict__,
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
    # v0.49 (round 492), decision 63 — the AXIS pass. One witness per
    # author-sized axis, from `AXES`, so R2 is checked against every way a
    # rendering can grow rather than against the three token substitutions
    # a program-shaped probe can make.
    axes = []
    for label, obj in axis_cases():
        bad, text = check_repr(obj)
        axes.append({"case": label, "axis": label.split("/")[0],
                     "family": AXES[label.split("/")[0]]["family"],
                     "class": type(obj).__name__,
                     "repr_len": len(text), "repr": text,
                     "violations": bad})
    a_man = axis_manifest()
    routing = routing_manifest()
    n_bad = (sum(1 for r in rows if r["violations"])
             + sum(1 for r in scale if r["violations"])
             + sum(1 for r in axes if r["violations"])
             + len(a_man["unclassified"]) + len(a_man["stale"])
             + len(a_man["axes_without_witness"])
             + len(routing["unrouted"]))
    return {"rows": rows, "scale": scale, "axes": axes, "crawl": stats,
            "repr_cap": V.REPR_CAP, "violations": n_bad,
            "manifest": probe_manifest(),
            "axis_manifest": a_man, "routing": routing}


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
    if "--inputs" in argv:
        man = axis_manifest()
        inputs = repr_inputs()
        if "--json" in argv:
            print(json.dumps({"manifest": man, "inputs": inputs}, indent=1))
        else:
            print("%d interpolated input(s) over %d repr source(s); "
                  "%d classified by table, %d by the composed-return rule"
                  % (man["inputs"], man["sources"],
                     man["classified_by_table"], man["classified_by_rule"]))
            for key in sorted(inputs):
                print("  %s" % key)
                for expr in inputs[key]:
                    axis = INPUT_AXIS.get((key, expr), "(rule) "
                                          "internal.composed")
                    short = expr if len(expr) <= 58 else expr[:57] + "…"
                    print("      %-26s %s" % (axis, short))
            print("\nby family: %s" % man["by_family"])
            for row in man["unclassified"]:
                print("  UNCLASSIFIED %s :: %s" % (row[0], row[1]))
            for row in man["stale"]:
                print("  STALE %s :: %s" % (row[0], row[1]))
            for axis in man["axes_without_witness"]:
                print("  NO WITNESS %s" % axis)
        return 1 if (man["unclassified"] or man["stale"]
                     or man["axes_without_witness"]) else 0
    if "--routing" in argv:
        rep = routing_manifest()
        if "--json" in argv:
            print(json.dumps(rep, indent=1))
        else:
            for row in rep["rows"]:
                print("%-4s %-12s %-20s %s"
                      % ("ok" if row["routes_through_cap"] else "FAIL",
                         row["module"].split(".")[-1], row["class"],
                         ", ".join(d.rsplit(".", 1)[-1]
                                   for d in row["delegates"]) or "(none)"))
            print("\nreprs not routed through values._cap: %d"
                  % len(rep["unrouted"]))
        return 1 if rep["unrouted"] else 0
    if "--caps" in argv:
        rep = cap_response()
        if "--json" in argv:
            print(json.dumps(rep, indent=1))
        else:
            print("R2 behaviourally, at caps %s over %d subject(s)"
                  % (rep["caps"], rep["subjects"]))
            for row in rep["rows"]:
                if not row["responds"]:
                    print("  FAIL %-44s %s" % (row["subject"], row["over"]))
            print("  %d subject(s) VACUOUS — already shorter than the "
                  "lowest cap, so they pass without demonstrating anything"
                  % rep["vacuous"])
            print("failing: %d" % len(rep["failing"]))
        return 1 if rep["failing"] else 0
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
    print("\nR2 by AXIS (v0.49, decision 63) — one witness per axis an "
          "author sizes:")
    for c in rep["axes"]:
        print("%-4s %-9s %-38s %-5d %s"
              % ("FAIL" if c["violations"] else "ok", c["family"],
                 c["case"], c["repr_len"], c["repr"][:58]))
        for v in c["violations"]:
            print("       -> %s" % v)
    am = rep["axis_manifest"]
    print("\ninputs %d over %d source(s); unclassified %d, stale %d, "
          "axes without a witness %d; by family %s"
          % (am["inputs"], am["sources"], len(am["unclassified"]),
             len(am["stale"]), len(am["axes_without_witness"]),
             am["by_family"]))
    print("reprs not routed through values._cap: %d"
          % len(rep["routing"]["unrouted"]))
    print("\nviolations: %d" % rep["violations"])
    return 1 if rep["violations"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

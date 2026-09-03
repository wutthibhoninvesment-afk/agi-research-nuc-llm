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
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from whence.interp import Interpreter                  # noqa: E402
from whence import values as V                         # noqa: E402

#: The probe. Every construct here exists to put one more CLASS on the
#: reachable graph, and the comment on each line says which. A round that
#: adds a value kind to the language adds a line here; if it forgets, the
#: class simply is not audited, which is why `tests/test_v47.py` also
#: asserts the reached set against a pinned list — the two halves catch
#: each other.
PROBE = '''
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


def reachable(source=PROBE, private=False, limit=CRAWL_LIMIT):
    """Crawl from `Interpreter.run(source)` and return what it reaches.

    Returns `(found, stats)` where `found` maps `(module, classname)` to
    the first path that reached it. With `private=True` the crawl also
    descends through underscore names, which is how `--private` shows the
    classes the loose rule would have claimed as caller surfaces.
    """
    interp = Interpreter()
    root = interp.run(source)
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


def audit(private=False):
    """The whole sweep, as data."""
    found, stats = reachable(private=private)
    interp = Interpreter()
    root = interp.run(PROBE)
    # Re-walk to hold a live instance of each class alongside its path.
    instances = {}
    seen, queue, keep = set(), [(root, "run()")], [root]
    steps = 0
    while queue and steps < CRAWL_LIMIT:
        obj, path = queue.pop()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        keep.append(obj)          # see `reachable()` — id reuse is real
        steps += 1
        cls = type(obj)
        if cls.__module__.startswith("whence"):
            instances.setdefault((cls.__module__, cls.__name__), obj)
        for child, edge in _public_children(obj):
            if id(child) not in seen:
                queue.append((child, path + edge))
    rows = []
    for key in sorted(found):
        mod, name = key
        obj = instances.get(key)
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
    n_bad = (sum(1 for r in rows if r["violations"])
             + sum(1 for r in scale if r["violations"]))
    return {"rows": rows, "scale": scale, "crawl": stats,
            "repr_cap": V.REPR_CAP, "violations": n_bad}


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

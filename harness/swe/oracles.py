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

Every oracle returns an `OracleOutcome`; `signature()` groups findings by
root cause so the campaign shrinks one reproducer per cause, exactly as the
totality fuzzer does.
"""

import os
import signal
import time
import traceback

from .fuzz import ProgramGen, WHENCE_ROOT, shrink, _whence_frames
from .killers import load_whence, _Timeout, _alarm

ORACLE_NAMES = ("totality", "fast_slow", "direct", "determinism", "render")


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


ORACLES = {"totality": oracle_totality, "fast_slow": oracle_fast_slow,
           "direct": oracle_direct, "determinism": oracle_determinism,
           "render": oracle_render}


def run_oracle(name, pkg, src, timeout_s=3.0, max_depth=500, root=WHENCE_ROOT):
    """Run one oracle under a wall-clock budget; crashes become outcomes."""
    fn = ORACLES[name]
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    t0 = time.time()
    try:
        o = fn(pkg, src, max_depth=max_depth)
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
    for name in sorted(os.listdir(ex_dir)):
        if name.endswith(".lang") and name not in skip:
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
    a = ap.parse_args()
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

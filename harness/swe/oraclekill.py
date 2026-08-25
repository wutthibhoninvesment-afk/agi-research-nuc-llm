"""Oracle-based killers for survivors the value-comparing corpus cannot see
(round 113).

`killers.find_killer` compares printed output, checks and bindings in the
default mode. Three more instruments distinguish a mutant from the original
and each can be pinned as a plain pytest in the language's own suite:

  modes     canonical behaviour under direct / trampoline (`direct=False`)
            / slow (`fast=False`) mode must be identical and equal to the
            original's — the three-way differential of rounds 26–30 as a
            per-program pin;
  frames    the frame-charge oracle (round 110): host frames above
            `exec_stmt` beyond what direct mode charged must stay under
            FRAME_SLACK at the CLI's recursion limit — the only instrument
            that sees an UNDERcharge (`cost = body.cdepth - 1`);
  counters  `fast_hits` / `direct_hits` / `direct_fallbacks` / `peak_depth`
            after a run — the contract `bench/ref_diff.py` already checks;
            sees counter bumps, recompilation (a `x is None` cache guard
            flipped) and OVERcharges (an earlier trampoline fallback).

Priority when several fire: modes > frames > counters (behaviour first,
statistics last). Every helper is defined ONCE as source text, exec'd here
and written verbatim into the generated test file (the killers.py rule).
"""
import json
import os
import re
import sys
import tempfile
import time

from .fuzz import ProgramGen, shrink, WHENCE_ROOT
from .killers import load_whence, docstring_safe
from .mutation import _copy_project
from .oracles import FRAME_SLACK

PIN_HELPER_SRC = r'''
import ctypes
import sys
import threading


class ProbeTimeout(BaseException):
    """BaseException: the interpreter's own `except Exception` must not swallow it."""


def in_thread(fn, timeout=None, stack_mb=64):
    """Run `fn()` on a FRESH thread and return its result (or re-raise).
    Direct mode's host-frame budget is `recursion limit - frames in use -
    reserve`, so anything that depends on it (`direct_hits`,
    `direct_fallbacks`, where an undercharge crashes) depends on the
    CALLER's stack depth; a new thread starts at depth ~2 whoever calls.
    `timeout` raises ProbeTimeout inside the thread (async exception) and
    in the caller."""
    box = {}

    def body():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 - re-raised in the caller
            box["error"] = e

    old = threading.stack_size()
    threading.stack_size(stack_mb << 20)
    try:
        t = threading.Thread(target=body)
        t.daemon = True
        t.start()
    finally:
        threading.stack_size(old)
    t.join(timeout)
    if t.is_alive():
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(t.ident), ctypes.py_object(ProbeTimeout))
        t.join(10.0)
        raise ProbeTimeout("probe exceeded %ss" % timeout)
    if "error" in box:
        raise box["error"]
    return box["value"]


def _run(src, Interpreter, Env, parse, max_depth=500, **kw):
    out = []
    interp = Interpreter(out=out.append, max_depth=max_depth, **kw)
    env = Env(interp.globals)
    for stmt in parse(src).stmts:
        interp.exec_stmt(stmt, env)
    return interp, env, out


def counters(src, Interpreter, Env, parse, max_depth=500, limit=1000, timeout=None):
    """Fast-path / direct-mode statistics after a run in the default mode.
    The host recursion limit is pinned (direct mode's budget is derived
    from it, so `direct_fallbacks` depends on it): 1000 keeps the budget
    fallback reachable at guest depth ~190."""
    def go():
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(limit)
        try:
            interp, env, out = _run(src, Interpreter, Env, parse, max_depth)
        finally:
            sys.setrecursionlimit(old_limit)
        return {"fast_hits": interp.fast_hits, "direct_hits": interp.direct_hits,
                "direct_fallbacks": interp.direct_fallbacks, "peak_depth": interp.peak_depth}
    return in_thread(go, timeout)


def modes(src, Interpreter, Env, parse, full_show, max_depth=500, limit=1000, timeout=None):
    """Canonical behaviour under direct / trampoline / slow mode, each on a
    fresh thread at recursion limit `limit`."""
    res = {}
    program = parse(src)
    for name, kw in (("direct", {}), ("gen", {"direct": False}), ("slow", {"fast": False})):
        def go(kw=kw):
            out = []
            old_limit = sys.getrecursionlimit()
            sys.setrecursionlimit(limit)
            try:
                interp = Interpreter(out=out.append, max_depth=max_depth, **kw)
                env = Env(interp.globals)
                try:
                    for stmt in program.stmts:
                        interp.exec_stmt(stmt, env)
                except Exception as e:  # noqa: BLE001 - a crash is behaviour too
                    return {"kind": "crash", "exc": type(e).__name__}
            finally:
                sys.setrecursionlimit(old_limit)
            return {"kind": "ok", "out": out,
                    "checks": [[c["label"], c["ok"]] for c in interp.checks],
                    "vals": dict((k, full_show(v.payload)) for k, v in env.vars.items())}
        res[name] = in_thread(go, timeout)
    return res


def frame_excess(src, Interpreter, Env, parse, max_depth=500, limit=6000, timeout=None):
    """Largest number of host frames above `exec_stmt` beyond what direct
    mode charged, over the whole run, at recursion limit `limit`
    (harness/swe/oracles.py::frame_excess, per program)."""
    out = []
    interp = Interpreter(out=out.append, max_depth=max_depth, direct=True)
    env = Env(interp.globals)
    program = parse(src)
    state = {"depth": 0, "d0": None, "h0": None, "best": -10 ** 9}

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
        elif event == "return":
            state["depth"] -= 1
            if state["d0"] is not None and state["depth"] < state["d0"]:
                state["d0"] = None
                state["h0"] = None

    def go():
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old_limit, limit))
        sys.setprofile(hook)
        try:
            for stmt in program.stmts:
                interp.exec_stmt(stmt, env)
        finally:
            sys.setprofile(None)
            sys.setrecursionlimit(old_limit)
        return state["best"]
    return in_thread(go, timeout)
'''
_ns = {}
exec(PIN_HELPER_SRC, _ns)
counters = _ns["counters"]
modes = _ns["modes"]
frame_excess = _ns["frame_excess"]

# Programs that push the direct-mode budget: non-tail recursion at guest
# depths the fuzz corpus never reaches (max_depth 500 in the probes).
DEEP_PROBES = [
    "fn f(n) { if n == 0 { 0 } else { 1 + f(n - 1) } }\nlet r = f(%d)\ncheck \"r\": r == %d\n" % (n, n)
    for n in (100, 200, 400)
] + [
    "fn ev(n) { if n == 0 { true } else { od(n - 1) } }\n"
    "fn od(n) { if n == 0 { false } else { ev(n - 1) } }\n"
    "let a = ev(301)\ncheck \"a\": a == false\n",
    "fn sum(xs, i) { if i == len(xs) { 0 } else { xs[i] + sum(xs, i + 1) } }\n"
    "let s = sum([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0)\ncheck \"s\": s == 55\n",
    "fn g(n) { if n == 0 { 1 } else { let m = g(n - 1)\n m + m - m } }\nlet v = g(250)\ncheck \"v\": v == 1\n",
]


ProbeTimeout = _ns["ProbeTimeout"]
in_thread = _ns["in_thread"]


def _parse_fn(pkg):
    parser = __import__(pkg["name"] + ".parser", fromlist=["parse"])
    return parser.parse


def probe(pkg, src, timeout_s=5.0, max_depth=500, limit=6000, with_frames=True):
    """{'modes': ..., 'counters': ..., 'frames': int|None} or {'kind': ...}
    for parse errors / timeouts / recursion crashes. Every measurement runs
    on a fresh thread (see `in_thread`), each under `timeout_s`."""
    parse = _parse_fn(pkg)
    I, E, F = pkg["Interpreter"], pkg["Env"], pkg["full_show"]
    try:
        parse(src)
    except (pkg["LexError"], pkg["ParseError"]) as e:
        return {"kind": type(e).__name__}
    res = {"kind": "ok"}
    try:
        res["modes"] = modes(src, I, E, parse, F, max_depth, timeout=timeout_s)
    except ProbeTimeout:
        return {"kind": "timeout"}
    except RecursionError:
        return {"kind": "crash", "exc": "RecursionError"}
    try:
        res["counters"] = counters(src, I, E, parse, max_depth, timeout=timeout_s)
    except ProbeTimeout:
        return {"kind": "timeout"}
    except Exception as e:  # noqa: BLE001
        res["counters"] = {"kind": "crash", "exc": type(e).__name__}
    if with_frames:
        try:
            res["frames"] = frame_excess(src, I, E, parse, max_depth, limit, timeout=timeout_s)
        except ProbeTimeout:
            return {"kind": "timeout"}
        except RecursionError:
            res["frames"] = "RecursionError"
        except Exception as e:  # noqa: BLE001
            res["frames"] = "crash:" + type(e).__name__
    return res


def compare(expected, got, slack=FRAME_SLACK):
    """Which instrument (modes / frames / counters) separates `got` from
    `expected`, or None. `expected` must be a clean original run: modes
    agree with each other and the frames excess is within slack."""
    if expected.get("kind") != "ok":
        return None
    em = expected["modes"]
    if not (em["direct"] == em["gen"] == em["slow"]):
        return None                         # the original is not self-consistent here: unusable
    if got.get("kind") != "ok":
        return "modes"                      # the mutant crashed/timed out where the original ran
    if got["modes"] != em:
        return "modes"
    ef, gf = expected.get("frames"), got.get("frames")
    if isinstance(ef, int) and ef <= slack and (not isinstance(gf, int) or gf > slack):
        return "frames"
    if expected.get("counters") != got.get("counters"):
        return "counters"
    return None


class OracleKill(object):
    def __init__(self, mutant, kind, program, expected, got, tried, seconds):
        self.mutant = mutant
        self.kind = kind                    # modes | frames | counters | None
        self.program = program
        self.expected = expected            # the original's probe on `program`
        self.got = got
        self.tried = tried
        self.seconds = seconds

    @property
    def found(self):
        return self.program is not None

    def as_dict(self):
        return {"mutant": self.mutant.id, "found": self.found, "kind": self.kind, "tried": self.tried,
                "seconds": round(self.seconds, 2), "program": self.program,
                "expected": self.expected, "got": self.got}


def find_oracle_killer(mutant, programs, original_pkg, project_root, orig_cache=None,
                       slack=FRAME_SLACK, timeout_s=5.0, limit=6000):
    t0 = time.time()
    tmp = tempfile.mkdtemp(prefix="okill-")
    try:
        dst = os.path.join(tmp, "proj")
        _copy_project(project_root, dst)
        with open(os.path.join(dst, mutant.path), "w", encoding="utf-8") as f:
            f.write(mutant.source)
        try:
            mut_pkg = load_whence(dst, "omut_" + mutant.id)
        except Exception as e:  # noqa: BLE001
            return OracleKill(mutant, "import", None, None, {"kind": "import_error", "exc": repr(e)},
                              0, time.time() - t0)
        orig_cache = orig_cache if orig_cache is not None else {}
        for i, src in enumerate(programs):
            if src not in orig_cache:
                orig_cache[src] = probe(original_pkg, src, timeout_s, limit=limit)
            expected = orig_cache[src]
            if expected.get("kind") != "ok":
                continue
            got = probe(mut_pkg, src, timeout_s, limit=limit)
            kind = compare(expected, got, slack)
            if kind:
                def keep(cand, kind=kind):
                    e = probe(original_pkg, cand, timeout_s, limit=limit)
                    return compare(e, probe(mut_pkg, cand, timeout_s, limit=limit), slack) == kind
                small = shrink(src, keep) or src
                e = probe(original_pkg, small, timeout_s, limit=limit)
                return OracleKill(mutant, kind, small, e, probe(mut_pkg, small, timeout_s, limit=limit),
                                  i + 1, time.time() - t0)
        return OracleKill(mutant, None, None, None, None, len(programs), time.time() - t0)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        name = "whence_" + re.sub(r"\W", "_", "omut_" + mutant.id)
        for k in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
            del sys.modules[k]


def corpus(seed=0, n=60, root=WHENCE_ROOT, include_examples=True):
    """Deep probes + examples + a light fuzz corpus (the value-comparing
    corpus already ran; this one exists for the modes/frames/counters
    instruments, so it is small and recursion-heavy)."""
    progs = list(DEEP_PROBES)
    if include_examples:
        ex_dir = os.path.join(root, "examples")
        for name in sorted(os.listdir(ex_dir)):
            if name.endswith(".lang") and name not in ("deep.lang", "meta.lang"):
                with open(os.path.join(ex_dir, name), encoding="utf-8") as f:
                    progs.append(f.read())
    for i in range(n):
        progs.append(ProgramGen(seed * 104729 + i, stress_rate=0.3, max_depth=3).program())
    return progs


def _test_name(mutant_id):
    return "test_okill_" + re.sub(r"\W+", "_", mutant_id).strip("_")


TEST_HEADER = '''"""GENERATED by harness/swe/oraclekill.py — do not edit by hand.

Each test pins a property of the original interpreter that a surviving
mutant broke: the three evaluation modes agree (`modes`), direct mode's
host-frame charge covers the frames it uses (`frames`, slack %(slack)d at
recursion limit 6000), or the fast-path counters (`counters`, the contract
bench/ref_diff.py checks). The docstring names the mutant and the
instrument.
"""

from whence.interp import Interpreter, Env
from whence.parser import parse
from whence.values import full_show

SLACK = %(slack)d
''' % {"slack": FRAME_SLACK} + PIN_HELPER_SRC + '''

def run_modes(src):
    return modes(src, Interpreter, Env, parse, full_show)


def run_counters(src):
    return counters(src, Interpreter, Env, parse)


def run_frames(src):
    return frame_excess(src, Interpreter, Env, parse)

'''


def render_tests(kills, existing=""):
    body = existing if existing.strip() else TEST_HEADER
    for k in kills:
        if not k.found:
            continue
        name = _test_name(k.mutant.id)
        if ("def %s(" % name) in body:
            continue
        doc = '    """mutant %s: %s (line %d) — %s instrument; mutant gave %s"""\n' % (
            k.mutant.id, docstring_safe(k.mutant.description), k.mutant.lineno, k.kind,
            docstring_safe(json.dumps(_got_summary(k))))
        if k.kind == "modes":
            body += "\n\ndef %s():\n%s    src = %r\n    assert run_modes(src) == %r\n" % (
                name, doc, k.program, k.expected["modes"])
        elif k.kind == "frames":
            body += "\n\ndef %s():\n%s    src = %r\n    assert run_frames(src) <= SLACK\n" % (
                name, doc, k.program)
        elif k.kind == "counters":
            body += "\n\ndef %s():\n%s    src = %r\n    assert run_counters(src) == %r\n" % (
                name, doc, k.program, k.expected["counters"])
    return body


def _got_summary(k):
    g = k.got or {}
    if k.kind == "frames":
        return {"frames": g.get("frames")}
    if k.kind == "counters":
        return {"counters": g.get("counters")}
    return {"kind": g.get("kind"), "modes_differ": True}


def main(argv=None):
    import argparse
    from .killers import load_survivors, rebuild_mutants
    ap = argparse.ArgumentParser(description="oracle killers (modes/frames/counters) for surviving mutants")
    ap.add_argument("mutation_json")
    ap.add_argument("--project", default=WHENCE_ROOT)
    ap.add_argument("--corpus", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--ids", help="comma list of mutant ids (default: every survivor)")
    ap.add_argument("--write", help="test file to create/append")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    surv = load_survivors(a.mutation_json)
    if a.ids:
        want = set(a.ids.split(","))
        surv = [d for d in surv if d["id"] in want]
    ms = rebuild_mutants(a.project, surv)
    programs = corpus(a.seed, a.corpus, a.project)
    original = load_whence(a.project, "orig_okill")
    cache = {}
    ks = []
    for m in ms:
        k = find_oracle_killer(m, programs, original, a.project, cache)
        ks.append(k)
        print("%-9s %-8s %s tried=%d %.1fs" % ("KILLER" if k.found else "no_killer", k.kind or "-",
                                               m.id, k.tried, k.seconds), flush=True)
    found = [k for k in ks if k.found]
    print("oracle killers: %d/%d survivors (%s)" % (
        len(found), len(ks), ", ".join("%s %d" % (kind, sum(1 for k in found if k.kind == kind))
                                       for kind in ("modes", "frames", "counters"))))
    if a.write:
        path = os.path.join(a.project, a.write)
        existing = open(path).read() if os.path.exists(path) else ""
        body = render_tests(ks, existing)
        compile(body, path, "exec")
        with open(path, "w") as f:
            f.write(body)
        print("wrote", path)
    if a.json:
        with open(a.json, "w") as f:
            json.dump([k.as_dict() for k in ks], f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

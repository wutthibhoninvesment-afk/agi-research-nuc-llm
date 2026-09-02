"""Differential test generation: turn surviving mutants into tests.

A mutant survived the suite, so no existing test distinguishes it from the
original. But a *random program* might: run a corpus of generated programs
through both interpreters and compare canonical behaviour (printed output,
check results, the rendering of every top-level binding). The first program
that differs is a killer; shrink it while the difference persists; pin the
ORIGINAL behaviour as a pytest. Re-running mutation testing afterwards must
show that mutant killed — that is the verification.

A mutant for which the corpus finds no difference is reported as
`no_killer` — usually an equivalent mutant (e.g. `>= 0` vs `> 0` on a value
that is never 0), sometimes a corpus gap. Both are stated, never hidden.

The canonical-behaviour helper is defined ONCE as source text: it is exec'd
here and written verbatim into the generated test file, so generator and
tests can never disagree about what "behaviour" means.
"""

import importlib.util
import json
import os
import re
import signal
import sys
import tempfile
import time

from .fuzz import ProgramGen, shrink, list_example_files, WHENCE_ROOT
from .mutation import Mutant, _copy_project

CANONICAL_HELPER_SRC = '''
def canonical(src, Interpreter, Env, LexError, ParseError, full_show, max_depth=500):
    """Behaviour of a program as plain data: kind, printed lines, check
    results, and the rendering of every top-level binding."""
    out = []
    interp = Interpreter(out=out.append, max_depth=max_depth)
    try:
        from_parse = __import__(Interpreter.__module__.rsplit(".", 1)[0] + ".parser",
                                fromlist=["parse"])
        program = from_parse.parse(src)
    except (LexError, ParseError) as e:
        return {"kind": type(e).__name__, "message": str(e)}
    env = Env(interp.globals)
    try:
        for stmt in program.stmts:
            interp.exec_stmt(stmt, env)
    except Exception as e:  # noqa: BLE001 — a crash is behaviour too
        return {"kind": "crash", "exc": type(e).__name__, "out": out}
    return {
        "kind": "ok",
        "out": out,
        "checks": [[c["label"], c["ok"]] for c in interp.checks],
        "vals": dict((k, full_show(v.payload)) for k, v in env.vars.items()),
    }
'''
_ns = {}
exec(CANONICAL_HELPER_SRC, _ns)
canonical = _ns["canonical"]


class _Timeout(BaseException):
    """Raised by the SIGALRM handler below. Deliberately NOT an `Exception`
    subclass (like `KeyboardInterrupt`/`SystemExit`): `canonical()`'s own
    `except Exception` (it must report a guest crash as behaviour too) would
    otherwise swallow this mid-flight, turning a clean timeout into a
    nondeterministic partial-output "crash" whose captured `out` depends on
    exactly which bytecode was executing when the alarm fired -- round 203
    caught this making `find_killer` report a different, flaky killer on
    every run for a slow example (`tco.lang`, `~2-3s` in-process, right at
    the 2s budget) that has nothing to do with the mutant under test."""
    pass


def _alarm(signum, frame):
    raise _Timeout()


def load_whence(root, tag):
    """Import `<root>/whence` as an independently named package so several
    variants (original + mutants) can coexist in one process."""
    name = "whence_%s" % re.sub(r"\W", "_", tag)
    for k in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        del sys.modules[k]
    pkg_dir = os.path.join(root, "whence")
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(pkg_dir, "__init__.py"),
        submodule_search_locations=[pkg_dir])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    interp = importlib.import_module(name + ".interp")
    lexer = importlib.import_module(name + ".lexer")
    parser = importlib.import_module(name + ".parser")
    values = importlib.import_module(name + ".values")
    return {"Interpreter": interp.Interpreter, "Env": interp.Env,
            "LexError": lexer.LexError, "ParseError": parser.ParseError,
            "full_show": values.full_show, "name": name, "root": root}


def behaviour(pkg, src, timeout_s=2.0, max_depth=500):
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    try:
        return canonical(src, pkg["Interpreter"], pkg["Env"], pkg["LexError"],
                         pkg["ParseError"], pkg["full_show"], max_depth=max_depth)
    except _Timeout:
        return {"kind": "timeout"}
    except RecursionError:
        return {"kind": "crash", "exc": "RecursionError"}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


_HEAVY_EXAMPLES = {
    "deep.lang",   # 15k recursion
    "meta.lang",   # round-203: ~11-18s in-process, 5-9x behaviour()'s 2s SIGALRM
                   # budget -- guaranteed to time out (now a clean, cheap
                   # `_Timeout`/BaseException skip, see below) so it never
                   # contributes a differential signal; excluded purely so a
                   # corpus sweep doesn't pay 11-18s per mutant for nothing.
    "tco.lang",    # round-203: same reasoning, ~14s in-process (sum_to(100000)).
    "self_eval.lang",  # round-209: ~3.2s in-process (round-204's v0.16 PMap
                   # change made record-heavy programs ~2x slower, per that
                   # round's own note) -- same "guaranteed timeout, wasted
                   # seconds" reasoning as meta.lang/tco.lang above.
    "shapes.lang", # round-209: NOT a "guaranteed timeout" case like the three
                   # above -- measured at 1.97-2.16s across 8 in-process runs,
                   # i.e. it straddles behaviour()'s 2.0s SIGALRM budget. That
                   # makes it a genuine flakiness source, not just wasted
                   # time: find_killer() caches the ORIGINAL's behaviour once
                   # per program and compares every mutant against that cached
                   # value, so whenever the original's one-shot run happens to
                   # land just under 2.0s ("ok") and a later mutant run for
                   # the SAME program lands just over (pure scheduling jitter,
                   # the mutants examined here don't touch timing-relevant
                   # code), find_killer() reports a spurious kill --
                   # `{"kind": "timeout"} != {"kind": "ok", ...}` -- with no
                   # real behavioural difference behind it. Confirmed live:
                   # this is what made test_review_stage_and_report's
                   # `no_killer == 1` assertion flaky (occasionally 0) --
                   # the test's only survivor is a `peak_depth` const mutant
                   # that shapes.lang cannot actually distinguish from the
                   # original.
}


def corpus(seed=0, n=300, root=WHENCE_ROOT, include_examples=True):
    """Programs to diff on: fuzz programs (light on stress templates so they
    run fast) plus the checked-in examples."""
    progs = []
    if include_examples:
        ex_dir = os.path.join(root, "examples")
        for name in list_example_files(root):
            if name not in _HEAVY_EXAMPLES:
                with open(os.path.join(ex_dir, name), encoding="utf-8") as f:
                    progs.append(f.read())
    for i in range(n):
        progs.append(ProgramGen(seed * 7919 + i, stress_rate=0.15, max_depth=3).program())
    return progs


class Killer(object):
    def __init__(self, mutant, program, expected, mutant_behaviour, tried, seconds,
                 undecided=0, unmeasured=0):
        self.mutant = mutant
        self.program = program          # minimized killer source (None if none)
        self.expected = expected        # original behaviour on `program`
        self.mutant_behaviour = mutant_behaviour
        self.tried = tried              # corpus programs examined
        self.seconds = seconds
        # Round 437: programs on which the mutant could not be MEASURED (it
        # blew the wall-clock budget and a longer one did not settle it).
        # `tried` counts programs looked at; `undecided` says how many of
        # those produced no evidence either way. A `no_killer` verdict with a
        # non-zero `undecided` is weaker than one with zero, and until this
        # field existed the two were spelled the same.
        self.undecided = undecided
        # Round 443 (SWE-loop D): programs that never reached the mutant at
        # all, because the ORIGINAL's own run of them timed out. Round 437
        # guarded the mutant side of this comparison and left the original's
        # single measurement in place; `undecided` counts pairs that produced
        # no evidence, and this counts programs that produced no COMPARISON.
        # `tried` counts neither distinction on its own, so before this field
        # a `no_killer` over 27 programs of which 5 were never compared was
        # spelled exactly like one over 27 that all were.
        self.unmeasured = unmeasured

    @property
    def found(self):
        return self.program is not None

    def as_dict(self):
        return {"mutant": self.mutant.id, "found": self.found, "tried": self.tried,
                "undecided": self.undecided, "unmeasured": self.unmeasured,
                "seconds": round(self.seconds, 2), "program": self.program,
                "expected": self.expected, "mutant_behaviour": self.mutant_behaviour}


#: Round 437. How much longer the confirmation run gets when the MUTANT (and
#: only the mutant) blows the budget. 3x is not arbitrary: `nproc` is 1 on
#: this host and research-state item 8 measures a 3x wall-clock penalty for
#: the same suite run under contention versus solo, which is the size of the
#: effect this guard exists to absorb.
TIMEOUT_RETRY_FACTOR = 3.0


def compare(original_pkg, mut_pkg, src, expected, timeout_s=2.0):
    """`(verdict, expected, got)` for one program. Verdict is one of
    `"same"`, `"differs"`, `"undecided"`.

    Round 437 (SWE-loop D). `find_killer` used to guard exactly one side of
    this comparison:

        if expected["kind"] == "timeout":
            continue                      # original timed out: not evidence
        got = behaviour(mut_pkg, src)
        if got != expected:               # mutant timing out lands HERE
            ...a killer...

    A timeout is a statement about the WALL CLOCK, not about the program. On
    the original's side that was understood and skipped; on the mutant's side
    the same non-measurement was read as a behavioural difference, so any
    corpus program running near the 2 s SIGALRM budget turned into a killer
    for ANY mutant the moment the box got busy — and `nproc` is 1 here.
    `examples/self_host.lang` measures 0.60 s solo against that 2 s budget:
    a 3.3x load spike between the cached original run and the mutant run is
    all it takes, and the spurious kill is unreproducible by construction
    because the next run is not loaded the same way.

    Round 203 met this family already (a slow example producing "a different,
    flaky killer on every run") and fixed the variant it saw — `_Timeout`
    leaking into `canonical`'s `except Exception` as a partial-output crash.
    The asymmetry underneath it survived.

    A mutant that genuinely diverges — an infinite loop from a mutated bound —
    is a real kill and must stay one, so a mutant-only timeout is not
    discarded, it is RE-MEASURED at `TIMEOUT_RETRY_FACTOR` x the budget with
    the original re-measured beside it at the same budget. Still timing out
    while the original completes is evidence; anything else is not.
    """
    got = behaviour(mut_pkg, src, timeout_s=timeout_s)
    if got == expected:
        return "same", expected, got
    if got.get("kind") != "timeout" or expected.get("kind") == "timeout":
        return "differs", expected, got
    long_s = timeout_s * TIMEOUT_RETRY_FACTOR
    again_orig = behaviour(original_pkg, src, timeout_s=long_s)
    again_mut = behaviour(mut_pkg, src, timeout_s=long_s)
    if again_orig.get("kind") == "timeout":
        return "undecided", again_orig, again_mut     # no clean expected to compare to
    if again_mut == again_orig:
        return "same", again_orig, again_mut          # the first timeout was load, not behaviour
    if again_mut.get("kind") == "timeout":
        return "differs", again_orig, again_mut       # diverges at 3x the budget: a real kill
    return "differs", again_orig, again_mut


def find_killer(mutant, programs, original_pkg, project_root, orig_cache=None,
                timeout_s=2.0):
    """Search `programs` for one whose behaviour differs under the mutant;
    shrink it; return a Killer (found or not)."""
    t0 = time.time()
    tmp = tempfile.mkdtemp(prefix="kill-")
    try:
        dst = os.path.join(tmp, "proj")
        _copy_project(project_root, dst)
        with open(os.path.join(dst, mutant.path), "w", encoding="utf-8") as f:
            f.write(mutant.source)
        try:
            mut_pkg = load_whence(dst, "mut_" + mutant.id)
        except Exception as e:  # noqa: BLE001 — mutant fails to import: killed by import
            return Killer(mutant, None, None, {"kind": "import_error", "exc": repr(e)},
                          0, time.time() - t0)
        orig_cache = orig_cache if orig_cache is not None else {}
        undecided = 0
        unmeasured = 0
        for i, src in enumerate(programs):
            if src not in orig_cache:
                e = behaviour(original_pkg, src, timeout_s=timeout_s)
                if e["kind"] == "timeout":
                    # Round 443 (SWE-loop D), symmetric with round 437's guard
                    # on the other side of this same comparison. A timeout is a
                    # statement about the WALL CLOCK, not about the program, and
                    # `orig_cache` is built ONCE per campaign and shared across
                    # every mutant (`campaign.stage_corpus`) — so believing a
                    # single load-spiked original timeout does not skip this
                    # program for this mutant, it deletes the program from the
                    # corpus of every LATER mutant in the run, after the load is
                    # long gone. Re-measure at the same headroom the mutant side
                    # gets before writing that verdict into the shared cache.
                    e = behaviour(original_pkg, src,
                                  timeout_s=timeout_s * TIMEOUT_RETRY_FACTOR)
                orig_cache[src] = e
            expected = orig_cache[src]
            if expected["kind"] == "timeout":
                unmeasured += 1
                continue
            verdict, expected, got = compare(original_pkg, mut_pkg, src, expected,
                                             timeout_s=timeout_s)
            if verdict == "undecided":
                undecided += 1
                continue
            if verdict == "differs":
                def keep(cand):
                    e = behaviour(original_pkg, cand, timeout_s=timeout_s)
                    if e["kind"] == "timeout":
                        return False
                    v, _, _ = compare(original_pkg, mut_pkg, cand, e, timeout_s=timeout_s)
                    return v == "differs"
                small = shrink(src, keep) or src
                if small == src:
                    small_expected, small_got = expected, got
                else:
                    _, small_expected, small_got = compare(
                        original_pkg, mut_pkg, small,
                        behaviour(original_pkg, small, timeout_s=timeout_s),
                        timeout_s=timeout_s)
                return Killer(mutant, small, small_expected, small_got,
                              i + 1, time.time() - t0, undecided=undecided,
                              unmeasured=unmeasured)
        return Killer(mutant, None, None, None, len(programs), time.time() - t0,
                      undecided=undecided, unmeasured=unmeasured)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        name = "whence_" + re.sub(r"\W", "_", "mut_" + mutant.id)
        for k in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
            del sys.modules[k]


def _test_name(mutant_id):
    return "test_kill_" + re.sub(r"\W+", "_", mutant_id).strip("_")


TEST_HEADER = '''"""GENERATED by harness/swe/killers.py — do not edit by hand.

Each test pins the behaviour of a program that distinguished the original
interpreter from a mutant that the hand-written suite let survive. The
docstring names the mutant (file:line:operator) and what it changed.

WHEN A DELIBERATE LANGUAGE CHANGE MOVES ONE OF THESE (round 452, closing
round 450's next-step 3): the expectation IS the kill, so pasting in what the
interpreter prints today leaves a test that still passes, still looks like a
regression pin, and has silently thrown the discrimination away. Re-pin
differentially instead —

    cd harness && python3 -m swe.killerrepin --check    # verdicts, no writes
    cd harness && python3 -m swe.killerrepin --write    # re-pin the movers

which rewrites a pin only when the tree at a baseline ref reproduces the OLD
expectation exactly, so the movement is attributable to the working-tree diff.
A `stale` verdict means the baseline does NOT reproduce it: the pin was
already wrong, and neither killerrepin nor you should rewrite it.
"""

from whence.interp import Interpreter, Env
from whence.lexer import LexError
from whence.parser import ParseError
from whence.values import full_show

''' + CANONICAL_HELPER_SRC + '''

def run(src):
    return canonical(src, Interpreter, Env, LexError, ParseError, full_show)

'''


def render_tests(killers, existing=""):
    """Append one test per found killer to `existing` (or a fresh file)."""
    body = existing if existing.strip() else TEST_HEADER
    for k in killers:
        if not k.found:
            continue
        name = _test_name(k.mutant.id)
        if ("def %s(" % name) in body:
            continue
        body += (
            "\n\ndef %s():\n"
            '    """mutant %s: %s (line %d) — mutant gave %s"""\n'
            "    src = %r\n"
            "    assert run(src) == %r\n"
            % (name, k.mutant.id, docstring_safe(k.mutant.description), k.mutant.lineno,
               docstring_safe(json.dumps(k.mutant_behaviour)), k.program, k.expected))
    return body


def docstring_safe(text, limit=120):
    """Make arbitrary text safe inside a triple-quoted docstring: no
    backslashes (escape sequences), no double quotes (a trailing one fuses
    with the closing triple), no newlines, bounded length."""
    text = text.replace("\\", "/").replace('"', "'").replace("\n", " ").replace("\r", " ")
    return text[:limit].rstrip()


def generate_killers(mutants, project_root=WHENCE_ROOT, seed=0, corpus_n=300,
                     on_result=None):
    programs = corpus(seed, corpus_n, project_root)
    original = load_whence(project_root, "orig")
    cache = {}
    out = []
    for m in mutants:
        k = find_killer(m, programs, original, project_root, cache)
        out.append(k)
        if on_result:
            on_result(k)
    return out


def load_survivors(mutation_json):
    with open(mutation_json) as f:
        data = json.load(f)
    return [d for d in data["mutants"] if d["status"] == "survived"]


def rebuild_mutants(project_root, survivor_dicts):
    """Regenerate Mutant objects (with source) for survivor records."""
    from .mutation import generate
    by_path = {}
    for d in survivor_dicts:
        by_path.setdefault(d["path"], []).append(d["id"])
    out = []
    for rel, ids in by_path.items():
        with open(os.path.join(project_root, rel), encoding="utf-8") as f:
            all_m = generate(f.read(), rel)
        by_id = dict((m.id, m) for m in all_m)
        for i in ids:
            if i in by_id:
                out.append(by_id[i])
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("mutation_json")
    ap.add_argument("--project", default=WHENCE_ROOT)
    ap.add_argument("--corpus", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--write", help="test file to create/append")
    a = ap.parse_args()
    ms = rebuild_mutants(a.project, load_survivors(a.mutation_json))
    ks = generate_killers(ms, a.project, a.seed, a.corpus,
                          on_result=lambda k: print("%-9s %s tried=%d %.1fs" % (
                              "KILLER" if k.found else "no_killer", k.mutant.id, k.tried, k.seconds), flush=True))
    found = [k for k in ks if k.found]
    print("killers: %d/%d survivors now have a killing test" % (len(found), len(ks)))
    if a.write:
        existing = open(a.write).read() if os.path.exists(a.write) else ""
        with open(a.write, "w") as f:
            f.write(render_tests(ks, existing))
        print("wrote", a.write)

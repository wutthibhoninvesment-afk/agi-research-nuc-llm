"""Line coverage of the files under test, by the suite — without the
`coverage` package (round 101).

Why: a mutant that survives can be a TEST GAP (the suite never executes the
mutated line, so nothing could notice) or a WEAK ASSERTION / EQUIVALENT
(the line runs, the change makes no observable difference). Mutation score
lumps them together; the fix for each is different (write a test that
reaches the line vs. read the code / prove equivalence), and the corpus
killer search should be spent where it can pay. This module measures which.

How: a subprocess runs pytest IN-PROCESS (`pytest.main`) after installing a
`sys.settrace` hook whose global callback returns a line tracer only for
frames whose code object lives in one of the target files (path-normalised
once per code filename and cached), so the cost is one dict lookup per call
event plus one increment per executed target line. Results are written as
JSON `{rel_path: {lineno: hits}}`; executable lines come from the compiled
code objects (`dis.findlinestarts`, recursively), so a percentage is honest
(blank lines, comments and docstring continuations are not "uncovered").

Ground-truth check that the instrument is right (used by the campaign): a
mutant on a line the suite never executes MUST survive. Any killed mutant on
an "uncovered" line is an instrument error (multi-line expressions whose
sub-expression carries a continuation line number are the known case) and
is reported as such rather than hidden.
"""

import ast
import dis
import json
import os
import subprocess
import sys
import tempfile
import time
import types

from .proc import run_capped

_BOOTSTRAP = r'''
import atexit, dis, json, os, sys, threading, time
TARGETS = %(targets)r            # realpath -> rel
INTEREST = %(interest)r          # realpath -> sorted lines of interest, or None (= every line)
OUT = %(out)r
BY_FILE = %(by_file)r            # True: hits keyed by the running test FILE (round 113)
HITS = dict((k, {}) for k in TARGETS)     # real -> {line: hits} | by file: real -> {test_file: {line: hits}}
CURD = dict((k, HITS[k]) for k in TARGETS)  # real -> the dict line events write to right now
DUR = {}                         # by file: test_file -> seconds spent in its tests
_cache = {}
_code_ok = {}                    # id(code) -> bool: does this code object contain a line of interest?
_t = [None]

def _local(frame, event, arg):
    if event == "line":
        d = CURD[frame.f_code.co_filename]
        ln = frame.f_lineno
        d[ln] = d.get(ln, 0) + 1
    return _local

def _switch(test_file):
    """By-file mode: point every target (and every alias of it) at the
    per-test-file dict; HITS[alias] is HITS[real], so setdefault returns
    the same inner dict for both."""
    for k, d in list(HITS.items()):
        CURD[k] = d.setdefault(test_file, {})

class _ByFilePlugin(object):
    def pytest_runtest_logstart(self, nodeid, location):
        _switch(nodeid.split("::")[0])
        # a test that measures frames may call sys.settrace(None) and leave
        # the tracer OFF for every later test (round 113: test_v10/test_v11
        # showed zero hits) -- re-arm at every test start
        sys.settrace(_global)
        threading.settrace(_global)
        _t[0] = time.monotonic()
    def pytest_runtest_logfinish(self, nodeid, location):
        f = nodeid.split("::")[0]
        if _t[0] is not None:
            DUR[f] = DUR.get(f, 0.0) + (time.monotonic() - _t[0])
        _switch("<between>")

if BY_FILE:
    _switch("<collect>")

def _wanted(code, real):
    """Targeted mode: trace a code object only if its own line range holds a
    line of interest. Nested code objects (inner defs, lambdas, comprehensions)
    are separate frames and decide for themselves."""
    lines = INTEREST.get(real)
    if lines is None:
        return True
    k = id(code)
    ok = _code_ok.get(k)
    if ok is None:
        starts = [ln for _, ln in dis.findlinestarts(code)]
        lo = min(starts) if starts else code.co_firstlineno
        hi = max(starts) if starts else code.co_firstlineno
        lo = min(lo, code.co_firstlineno)
        ok = any(lo <= ln <= hi for ln in lines)
        _code_ok[k] = ok
    return ok

def _global(frame, event, arg):
    code = frame.f_code
    fn = code.co_filename
    hit = _cache.get(fn)
    if hit is None:
        real = os.path.realpath(fn) if fn and not fn.startswith("<") else ""
        hit = real if real in HITS else ""
        _cache[fn] = hit
        if hit and hit != fn:
            # alias: the code object names the file by another path
            HITS[fn] = HITS[hit]
            CURD[fn] = CURD[hit]
    if hit and _wanted(code, hit):
        return _local
    return None

_dumped = []
def _dump():
    if _dumped:
        return
    _dumped.append(1)
    sys.settrace(None)
    out = {}
    for real, rel in TARGETS.items():
        if BY_FILE:
            out[rel] = dict((tf, dict((str(l), c) for l, c in d.items()))
                            for tf, d in HITS[real].items())
        else:
            out[rel] = dict((str(l), c) for l, c in HITS[real].items())
    if BY_FILE:
        out["_durations"] = dict((k, round(v, 3)) for k, v in DUR.items())
    with open(OUT, "w") as f:
        json.dump(out, f)

atexit.register(_dump)
sys.settrace(_global)
threading.settrace(_global)
import pytest
rc = pytest.main(%(args)r, plugins=[_ByFilePlugin()] if BY_FILE else [])
_dump()
sys.exit(int(rc))
'''


def executable_lines(source, filename="<file>"):
    """Line numbers that carry bytecode (recursively through nested code
    objects) — the denominator for a coverage percentage."""
    code = compile(source, filename, "exec")
    lines = set()
    stack = [code]
    while stack:
        c = stack.pop()
        for _, ln in dis.findlinestarts(c):
            lines.add(ln)
        for const in c.co_consts:
            if isinstance(const, types.CodeType):
                stack.append(const)
    return lines


def collect(root, rel_paths, pytest_args=("-q", "-p", "no:cacheprovider", "tests"),
            timeout_s=3600.0, python=sys.executable, interest=None, by_file=False):
    """Run the suite under the tracer; return the coverage dict
    `{rel: {lineno(int): hits}}` plus `_meta`.

    `interest` = `{rel: [lines]}` switches to TARGETED tracing: only code
    objects whose line range contains one of those lines get a line tracer.
    Full tracing of an interpreter is 10-30x slower than the suite (every
    executed line of the hot loop is a Python callback); targeted tracing
    of the ~60 survivor lines costs a fraction of that. Lines outside the
    traced code objects are then UNKNOWN, not uncovered — `triage` and
    `line_hits` say so via `_interest`.

    `by_file=True` (round 113) keys every hit by the test FILE that was
    running (`{rel: {test_file: {line: hits}}}`, plus `_durations`
    = seconds per test file) and re-arms the tracer at every test start (a
    test that calls `sys.settrace(None)` would otherwise blind the rest of
    the run); `collapse()` folds it back into the plain shape. One full-trace run then gives both the coverage triage and the
    per-file map that `prioritize.MapPrioritizer` orders and restricts the
    suite with."""
    root = os.path.realpath(root)
    targets = {}
    for rel in rel_paths:
        targets[os.path.realpath(os.path.join(root, rel))] = rel
    interest_real = {}
    for real, rel in targets.items():
        lines = None
        if interest is not None:
            lines = sorted(set(int(x) for x in (interest.get(rel) or [])))
        interest_real[real] = lines
    fd, out = tempfile.mkstemp(prefix="cov-", suffix=".json")
    os.close(fd)
    try:
        prog = _BOOTSTRAP % {"targets": targets, "out": out, "args": list(pytest_args),
                             "interest": interest_real, "by_file": bool(by_file)}
        t0 = time.time()
        p = run_capped([python, "-c", prog], root, timeout_s)
        if p.timed_out:
            raise RuntimeError("coverage run exceeded %.0fs (process group killed)" % timeout_s)
        secs = p.seconds
        with open(out, encoding="utf-8") as f:
            raw = json.load(f)
    finally:
        try:
            os.remove(out)
        except OSError:
            pass
    cov = {}
    for rel, hits in raw.items():
        if rel == "_durations":
            cov[rel] = hits
        elif by_file:
            cov[rel] = dict((tf, dict((int(k), v) for k, v in d.items())) for tf, d in hits.items())
        else:
            cov[rel] = dict((int(k), v) for k, v in hits.items())
    tail = "\n".join(p.output.strip().splitlines()[-3:])
    cov["_meta"] = {"root": root, "files": list(rel_paths), "pytest_args": list(pytest_args),
                    "returncode": p.returncode, "seconds": round(secs, 1), "pytest_tail": tail,
                    "targeted": interest is not None, "by_file": bool(by_file)}
    if interest is not None:
        cov["_interest"] = dict((rel, interest_real[real]) for real, rel in targets.items())
    return cov


_SPECIAL = ("_meta", "_interest", "_durations")


def is_by_file(cov):
    return bool((cov.get("_meta") or {}).get("by_file"))


def save(cov, path):
    data = {}
    by_file = is_by_file(cov)
    for rel, hits in cov.items():
        if rel in _SPECIAL:
            data[rel] = hits
        elif by_file:
            data[rel] = dict((tf, dict((str(k), v) for k, v in d.items())) for tf, d in hits.items())
        else:
            data[rel] = dict((str(k), v) for k, v in hits.items())
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=0)
    os.replace(tmp, path)


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    cov = {}
    by_file = bool((data.get("_meta") or {}).get("by_file"))
    for rel, hits in data.items():
        if rel in _SPECIAL:
            cov[rel] = hits
        elif by_file:
            cov[rel] = dict((tf, dict((int(k), v) for k, v in d.items())) for tf, d in hits.items())
        else:
            cov[rel] = dict((int(k), v) for k, v in hits.items())
    return cov


def collapse(cov):
    """A by-file map folded into the plain `{rel: {line: hits}}` shape
    (hits summed over test files, `_meta.by_file` cleared) so every
    analysis below works on it unchanged. A plain cov is returned as is."""
    if not is_by_file(cov):
        return cov
    out = {}
    for rel, per_file in cov.items():
        if rel in _SPECIAL:
            continue
        tot = {}
        for d in per_file.values():
            for ln, c in d.items():
                tot[ln] = tot.get(ln, 0) + c
        out[rel] = tot
    meta = dict(cov.get("_meta") or {})
    meta["by_file"] = False
    meta["collapsed_from_by_file"] = True
    out["_meta"] = meta
    if "_interest" in cov:
        out["_interest"] = cov["_interest"]
    return out


def covering_files(cov, rel, line, end_line=None):
    """Test files whose tests executed any line in [line, end_line] of
    `rel`, with the hit count; `<collect>`/`<between>` (import time, in
    between tests) are reported under their own keys — a line hit only
    there is executed by EVERY file's run."""
    per_file = cov.get(rel, {})
    hi = end_line if end_line and end_line >= line else line
    out = {}
    for tf, d in per_file.items():
        n = 0
        for ln in range(line, hi + 1):
            n += d.get(ln, 0)
        if n:
            out[tf] = n
    return out


# ---------------------------------------------------------------- analysis --

def line_hits(cov, rel, line, end_line=None):
    """Hits on `line` (or the max over [line, end_line]); None when the run
    was targeted and the line was not among the lines of interest."""
    interest = cov.get("_interest")
    if interest is not None:
        wanted = set(interest.get(rel) or [])
        if not any(ln in wanted for ln in range(line, (end_line or line) + 1)):
            return None
    hits = cov.get(rel, {})
    if end_line is None or end_line < line:
        return hits.get(line, 0)
    return max(hits.get(ln, 0) for ln in range(line, end_line + 1))


def annotate_mutants(mutant_dicts, cov):
    """Add `covered` (True / False / None = not traced) and `hits` to each
    mutant record, in place; a record may carry `end_line`
    (mutation.generate writes it) so multi-line nodes count as covered when
    any of their lines ran."""
    for d in mutant_dicts:
        h = line_hits(cov, d["path"], d["line"], d.get("end_line"))
        d["hits"] = h
        d["covered"] = None if h is None else h > 0
    return mutant_dicts


def file_summary(root, rel, cov):
    """Executable / executed line counts and per-definition detail."""
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        src = f.read()
    ex = executable_lines(src, rel)
    hits = cov.get(rel, {})
    executed = set(ln for ln in ex if hits.get(ln, 0) > 0)
    tree = ast.parse(src, filename=rel)
    defs = []

    def visit(body, prefix):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + node.name
                lo, hi = node.lineno, getattr(node, "end_lineno", node.lineno)
                own = set(ln for ln in ex if lo <= ln <= hi)
                if isinstance(node, ast.ClassDef):
                    visit(node.body, name + ".")
                    continue
                # the def line itself runs at import time; only the body
                # says whether the function was ever CALLED
                own.discard(lo)
                for dec in node.decorator_list:
                    own.discard(dec.lineno)
                ran = len(own & executed)
                defs.append({"name": name, "start": lo, "end": hi,
                             "executable": len(own), "executed": ran,
                             "pct": round(100.0 * ran / len(own), 1) if own else None})
                visit(node.body, name + ".")
    visit(tree.body, "")
    never = [d["name"] for d in defs if d["executable"] and d["executed"] == 0]
    targeted = cov.get("_interest") is not None
    if targeted:
        # only code objects holding a line of interest were traced: restrict
        # the per-def list to defs that contain one, and mark the file pct
        # as a lower bound
        wanted = set(cov["_interest"].get(rel) or [])
        defs = [d for d in defs if any(d["start"] <= ln <= d["end"] for ln in wanted)]
        never = [d["name"] for d in defs if d["executable"] and d["executed"] == 0]
    return {"file": rel, "executable": len(ex), "executed": len(executed),
            "pct": round(100.0 * len(executed) / len(ex), 2) if ex else None,
            "targeted": targeted,
            "uncovered_lines": sorted(ex - executed),
            "defs": defs, "never_executed_defs": never}


def triage(mutant_dicts, cov):
    """Split mutants by coverage; the killed-on-uncovered count is the
    instrument's self-check (must be ~0)."""
    annotate_mutants(mutant_dicts, cov)
    out = {"total": len(mutant_dicts), "covered": 0, "uncovered": 0, "unknown": 0,
           "survived_covered": 0, "survived_uncovered": 0, "survived_unknown": 0,
           "killed_traced": 0, "killed_on_uncovered": 0, "killed_on_uncovered_ids": []}
    for d in mutant_dicts:
        if d["covered"] is None:
            out["unknown"] += 1
            if d["status"] == "survived":
                out["survived_unknown"] += 1
            continue
        key = "covered" if d["covered"] else "uncovered"
        out[key] += 1
        if d["status"] in ("killed", "timeout"):
            out["killed_traced"] += 1
        if d["status"] == "survived":
            out["survived_" + key] += 1
        elif not d["covered"] and d["status"] in ("killed", "timeout"):
            out["killed_on_uncovered"] += 1
            out["killed_on_uncovered_ids"].append(d["id"])
    return out


def interest_from_mutants(mutant_dicts, killed_sample=60, seed=0):
    """Lines of interest for a targeted run: every survivor's lines plus a
    seeded sample of killed mutants' lines (the instrument's self-check:
    those must read as covered)."""
    import random
    rng = random.Random(seed)
    out = {}

    def add(d):
        s = out.setdefault(d["path"], set())
        for ln in range(d["line"], (d.get("end_line") or d["line"]) + 1):
            s.add(ln)
    killed = []
    for d in mutant_dicts:
        if d["status"] == "survived":
            add(d)
        elif d["status"] in ("killed", "timeout"):
            killed.append(d)
    for d in rng.sample(killed, min(killed_sample, len(killed))):
        add(d)
    return dict((k, sorted(v)) for k, v in out.items())


def render_summary(summary, top=12):
    lines = ["%s: %d/%d executable lines executed (%.1f%%)%s"
             % (summary["file"], summary["executed"], summary["executable"], summary["pct"] or 0.0,
                " [targeted run: lower bound; per-def list = defs holding a line of interest]"
                if summary.get("targeted") else "")]
    if summary["never_executed_defs"]:
        lines.append("  never executed: " + ", ".join(summary["never_executed_defs"]))
    worst = sorted((d for d in summary["defs"] if d["executable"] and d["executed"]),
                   key=lambda d: (d["pct"], -d["executable"]))[:top]
    for d in worst:
        lines.append("  %-40s %3d/%3d %5.1f%%  [%d-%d]" % (
            d["name"], d["executed"], d["executable"], d["pct"], d["start"], d["end"]))
    return "\n".join(lines)


def main(argv=None):
    import argparse
    from .fuzz import WHENCE_ROOT
    ap = argparse.ArgumentParser(description="settrace line coverage of files under a pytest suite")
    ap.add_argument("--root", default=WHENCE_ROOT)
    ap.add_argument("--files", default="whence/interp.py", help="comma list relative to root")
    ap.add_argument("--args", default="-q -p no:cacheprovider tests", help="pytest args")
    ap.add_argument("--out", help="write coverage JSON here")
    ap.add_argument("--load", help="skip the run; analyse an existing coverage JSON")
    ap.add_argument("--mutation-json", help="triage a mutation report against the coverage")
    ap.add_argument("--targeted", action="store_true",
                    help="trace only code objects holding a survivor line (+ --killed-sample killed lines)")
    ap.add_argument("--killed-sample", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--by-file", action="store_true",
                    help="key hits by the running test file (+ per-file durations); implies a full trace")
    a = ap.parse_args(argv)
    files = [p.strip() for p in a.files.split(",") if p.strip()]
    if a.load:
        cov = load(a.load)
    else:
        interest = None
        if a.targeted:
            if not a.mutation_json:
                ap.error("--targeted needs --mutation-json")
            with open(a.mutation_json, encoding="utf-8") as f:
                interest = interest_from_mutants(json.load(f)["mutants"], a.killed_sample, a.seed)
        cov = collect(a.root, files, tuple(a.args.split()), interest=interest, by_file=a.by_file)
        print("suite rc=%s in %.0fs: %s" % (cov["_meta"]["returncode"], cov["_meta"]["seconds"],
                                             cov["_meta"]["pytest_tail"].splitlines()[-1:]))
        if a.out:
            save(cov, a.out)
    if is_by_file(cov):
        dur = cov.get("_durations") or {}
        print("by-file map: %d test files, durations %s" % (
            len(dur), ", ".join("%s %.1fs" % (os.path.basename(k), v) for k, v in sorted(dur.items()))))
        cov = collapse(cov)
    for rel in files:
        print(render_summary(file_summary(a.root, rel, cov)))
    if a.mutation_json:
        with open(a.mutation_json, encoding="utf-8") as f:
            data = json.load(f)
        t = triage(data["mutants"], cov)
        print("mutants: %d covered / %d uncovered / %d untraced; survivors %d covered / %d uncovered "
              "/ %d untraced; killed traced %d, killed-on-uncovered %d %s"
              % (t["covered"], t["uncovered"], t["unknown"], t["survived_covered"],
                 t["survived_uncovered"], t["survived_unknown"], t["killed_traced"],
                 t["killed_on_uncovered"], t["killed_on_uncovered_ids"][:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

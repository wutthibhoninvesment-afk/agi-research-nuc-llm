#!/usr/bin/env python3
"""Differential: the working tree's `whence` vs a REFERENCE copy of the
package (by default the git HEAD version, extracted with `git show`) on
every example — outputs, check records, every top-level binding's
`render_why`, and the evaluation counters — under one or more modes.

usage: python3 bench/ref_diff.py [--ref DIR] [--modes direct,fast,slow]
                                 [--limit 6000] [--counters] [files...]
       python3 bench/ref_diff.py --fuzz SEED [-n 300] [--timeout 5] ...
With no files: all examples/*.lang. `--fuzz` compares the two packages on
N random programs from the harness fuzzer's grammar (`swe.fuzz.ProgramGen`,
found relative to this repo) instead of files — the oracle campaigns check
a tree against ITSELF (fast vs slow, determinism); this checks it against
the previous version on programs nobody wrote. A program that times out
under either package is skipped and counted. `--ref DIR` names a directory that
contains a package directory `whence_ref/` (relative imports inside the
package make the rename free); without it the script extracts HEAD into a
temporary directory. Exit 1 on any difference. The point (v0.10, round
108): a rewrite of the hot paths is byte-identical to the previous
version or it is a different language — this makes that a command.
"""
import argparse
import gc
import importlib
import os
import signal
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# REPO must be the real agi-research checkout root even when this whole
# `languages/whence` directory has been copied into a tempdir (every
# mutation/repair run does exactly that) — `dirname(dirname(ROOT))` is only
# correct in the original checkout. `harness/swe/proc.py` injects
# AGI_RESEARCH_ROOT into every test subprocess's env for this reason (round
# 149: found via 7/78 round-137 "kills" that were really `git -C <tempdir>`
# / `import swe` failures here, misclassified as genuine mutant kills).
REPO = os.environ.get("AGI_RESEARCH_ROOT") or os.path.dirname(os.path.dirname(ROOT))
PKG_PATH = "languages/whence/whence"
MODES = {"direct": {}, "fast": {"direct": False}, "slow": {"fast": False}}


def ref_modules(rev="HEAD"):
    """The module names to extract, read from the REVISION BEING BUILT.

    History of this one line, because both halves of it are instructive.

    v0.10-v0.33 it was a hand-written tuple `("__init__", "ast_nodes",
    "interp", "lexer", "parser", "values")`. `whence/foreign.py` arrived with
    v0.33 (round 386) and was never added, so every invocation from commit
    `4c05cf4` to `21538a8` died with `ModuleNotFoundError: No module named
    'whence_ref.foreign'` before comparing anything --- a tool whose whole
    job is "this rewrite is byte-identical to the previous version or it is
    a different language", silently unavailable. Round 395 re-executed that
    interval commit by commit (`harness/swe/toolliveness.py`): 9 commits,
    the HEADs of rounds 387-391. `timetravel.py` had been missing from the
    same tuple since `8637795` and cost NOTHING for 280 commits, because
    nothing in the extracted set imports it --- a missing name is free until
    somebody imports it, which is why this went unnoticed for so long.

    v0.34 (round 392) derived it from `os.listdir(ROOT/whence)` --- the
    WORKING TREE --- while `extract_head` extracts from HEAD. Round 395
    demonstrated the failure that leaves: a module present in the working
    tree and not yet committed makes `git show` exit 128 and the whole
    command die, so the round that ADDS a module breaks the differential for
    itself, which is precisely the round that most needs it.

    The set is a property of the package being BUILT, so it is read from
    that revision's tree and from nowhere else. `--ref DIR` supplies a
    prebuilt package and never reaches here at all.
    """
    out = subprocess.check_output(
        ["git", "-C", REPO, "ls-tree", "--name-only", rev, PKG_PATH + "/"],
        text=True)
    return tuple(sorted(os.path.basename(p)[:-3] for p in out.split()
                        if p.endswith(".py")))


def extract_head(into, rev="HEAD"):
    pkg = os.path.join(into, "whence_ref")
    os.makedirs(pkg, exist_ok=True)
    names = ref_modules(rev)
    if not names:
        raise SystemExit("ref_diff: %s:%s lists no .py files --- is REPO (%s) "
                         "the right checkout?" % (rev, PKG_PATH, REPO))
    for m in names:
        src = subprocess.check_output(
            ["git", "-C", REPO, "show",
             "%s:%s/%s.py" % (rev, PKG_PATH, m)])
        with open(os.path.join(pkg, m + ".py"), "wb") as f:
            f.write(src)
    return into


def load(pkg_dir, pkg_name):
    sys.path.insert(0, pkg_dir)
    try:
        interp = importlib.import_module(pkg_name + ".interp")
        values = importlib.import_module(pkg_name + ".values")
    finally:
        sys.path.pop(0)
    return interp, values


def run(interp_mod, values_mod, src, mkw):
    out = []
    # gc_relief as run.py: without it a 100k-node history (tco.lang) pays
    # gen-2 rescans of the growing DAG (round 26) — 4.8 s instead of 0.4
    interp = interp_mod.Interpreter(out=out.append, gc_relief=True, **mkw)
    gc.collect()
    env = interp.run(src)
    trees = {}
    for n in sorted(env.vars):
        trees[n] = values_mod.render_why(env.get(n))
    checks = [(c["label"], c["ok"], c["note"], c.get("why"), c.get("contrast"))
              for c in interp.checks]
    counters = {k: getattr(interp, k) for k in
                ("fast_hits", "direct_hits", "direct_fallbacks", "tail_calls",
                 "peak_depth", "depth")}
    return out, checks, trees, counters


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def run_capped(interp_mod, values_mod, src, mkw, seconds):
    """`run` under a SIGALRM cap. Returns the run, or a string naming why
    there is none: "timeout", or the exception type that escaped (a
    totality violation — Whence never raises for a program's problems).
    Parse errors never reach here: both packages share the parser."""
    signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return run(interp_mod, values_mod, src, mkw)
    except _Timeout:
        return "timeout"
    except Exception as e:          # noqa: BLE001 — that IS the finding
        return type(e).__name__
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def fuzz_sources(seed, n):
    harness = os.path.join(REPO, "harness")
    sys.path.insert(0, harness)
    try:
        from swe.fuzz import ProgramGen
    finally:
        sys.path.pop(0)
    gen = ProgramGen(seed)
    return [gen.program() for _ in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref")
    ap.add_argument("--rev", default="HEAD",
                    help="the git revision to build the reference package "
                         "from (default HEAD). Ignored when --ref names a "
                         "prebuilt directory. Round 395: this is what makes "
                         "a CROSS-VERSION differential one command --- "
                         "`--rev 4c05cf4` compares the working tree against "
                         "v0.33 --- and until it existed the tool could only "
                         "ever compare a tree with its own last commit, "
                         "which is a refactor check and nothing else.")
    ap.add_argument("--modes", default="direct,fast,slow")
    ap.add_argument("--limit", type=int, default=6000)
    ap.add_argument("--counters", action="store_true",
                    help="also require identical evaluation counters")
    ap.add_argument("--fuzz", type=int, help="seed: compare on random programs")
    ap.add_argument("-n", type=int, default=300)
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--show", action="store_true", help="print differing sources")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    sys.setrecursionlimit(a.limit)
    ref_dir = a.ref or extract_head(tempfile.mkdtemp(prefix="whence_ref_"),
                                    a.rev)
    new_i, new_v = load(ROOT, "whence")
    ref_i, ref_v = load(ref_dir, "whence_ref")
    if a.fuzz is not None:
        from whence.parser import parse, ParseError
        from whence.lexer import LexError
        srcs = []
        for src in fuzz_sources(a.fuzz, a.n):
            try:
                parse(src)
            except (ParseError, LexError):
                continue
            srcs.append(src)
        bad = skipped = 0
        ref_raised = {}
        for k, src in enumerate(srcs):
            for mode in a.modes.split(","):
                mkw = MODES[mode]
                r = run_capped(ref_i, ref_v, src, mkw, a.timeout)
                n_ = run_capped(new_i, new_v, src, mkw, a.timeout)
                if type(n_) is str and n_ != "timeout":
                    bad += 1          # the new tree raised: a finding
                    print("DIFF program %d %s: %s escaped the new tree" % (k, mode, n_))
                    if a.show:
                        print(src)
                    continue
                if type(r) is str:
                    skipped += 1
                    if r != "timeout":
                        ref_raised.setdefault(r, []).append((k, mode))
                    continue
                if type(n_) is str:
                    # A lone SIGALRM cap is wall-clock, not CPU time: under
                    # concurrent load (another campaign's subprocesses on
                    # the same box) the SAME program can cross `seconds` on
                    # one interpreter and not the other purely from
                    # scheduling noise, with no real behavioural difference
                    # (round 144 finding — this produced exactly the
                    # "reliably fails in-suite, reliably passes standalone"
                    # symptom round 137 flagged and could not root-cause).
                    # Retry once at 4x budget before calling it a genuine
                    # hang: noise clears comfortably at 4x, but an actual
                    # introduced infinite loop or exponential blowup does
                    # not become fast just because it is given more time.
                    n_ = run_capped(new_i, new_v, src, mkw, a.timeout * 4)
                    if n_ == "timeout":
                        bad += 1
                        print("DIFF program %d %s: timed out under the new "
                              "tree only (confirmed at 4x budget)" % (k, mode))
                        continue
                    if type(n_) is str:
                        bad += 1
                        print("DIFF program %d %s: %s escaped the new "
                              "tree on retry" % (k, mode, n_))
                        continue
                    # retry succeeded within budget: fall through to the
                    # normal comparison below, same as any other pair
                ro, rc, rt, rk = r
                no, nc, nt, nk = n_
                diffs = []
                if ro != no:
                    diffs.append("output")
                if rc != nc:
                    diffs.append("checks")
                for name in sorted(set(rt) | set(nt)):
                    if rt.get(name) != nt.get(name):
                        diffs.append("why:" + name)
                if a.counters and rk != nk:
                    diffs.append("counters %r vs %r" % (rk, nk))
                if diffs:
                    bad += 1
                    print("DIFF program %d %s: %s" % (k, mode, ", ".join(diffs)))
                    if a.show:
                        print(src)
        for exc, where in sorted(ref_raised.items()):
            print("NOTE the reference raised %s on %d (program, mode) pairs: %s"
                  % (exc, len(where), where[:8]))
        print("ref=%s (rev %s)  fuzz seed %d: %d programs parsed of %d, "
              "%d (program, mode) "
              "pairs differ, %d skipped (timeout or exception under the "
              "reference)" % (ref_dir, "supplied" if a.ref else a.rev,
                              a.fuzz, len(srcs), a.n, bad, skipped))
        sys.exit(1 if bad else 0)
    files = a.files or sorted(
        os.path.join(ROOT, "examples", f)
        for f in os.listdir(os.path.join(ROOT, "examples")) if f.endswith(".lang"))
    bad = compared = newsyntax = unparsed = 0
    for path in files:
        with open(path) as f:
            src = f.read()
        for mode in a.modes.split(","):
            mkw = MODES[mode]
            try:
                ro, rc, rt, rk = run(ref_i, ref_v, src, mkw)
            except Exception as e:
                if type(e).__name__ != "ParseError":
                    raise
                # An example may use syntax the reference package predates
                # (round 132: `-> Type` on shapes.lang, unparseable under
                # HEAD's pre-v0.13 lexer/parser) — that is the expected
                # shape of "we shipped a new feature", not a divergence to
                # crash over.
                #
                # Round 395: it is NOT the only shape, and until this round
                # the tool called every parse failure by that name. Against
                # `--rev HEAD` the two packages share a parser, so a
                # reference parse error cannot mean "the reference is old" —
                # it means the FILE does not parse. Ten of the thirty-two
                # examples are in exactly that state, so round 392's "0
                # differing (file, mode) pairs" was 66 of 96 pairs with the
                # other 30 excluded under a wrong diagnosis and no
                # denominator printed. Ask the new tree too, and say which
                # of the two answers this is.
                try:
                    run(new_i, new_v, src, mkw)
                except Exception as e2:
                    if type(e2).__name__ != "ParseError":
                        raise
                    unparsed += 1
                    print("UNPARSED  %-18s %-6s (neither package parses this "
                          "file: %s)" % (os.path.basename(path), mode,
                                         str(e2)[:60]))
                    continue
                newsyntax += 1
                print("NEWSYNTAX %-18s %-6s (reference package cannot "
                      "parse this file's current syntax)" %
                      (os.path.basename(path), mode))
                continue
            no, nc, nt, nk = run(new_i, new_v, src, mkw)
            compared += 1
            diffs = []
            if ro != no:
                diffs.append("output")
            if rc != nc:
                diffs.append("checks")
            for n in sorted(set(rt) | set(nt)):
                if rt.get(n) != nt.get(n):
                    diffs.append("why:" + n)
            if a.counters and rk != nk:
                diffs.append("counters %r vs %r" % (rk, nk))
            tag = "SAME" if not diffs else "DIFF"
            bad += bool(diffs)
            print("%s %-18s %-6s bindings=%d checks=%d out=%d%s" % (
                tag, os.path.basename(path), mode, len(nt), len(nc), len(no),
                ("  " + ", ".join(diffs)) if diffs else ""))
    total = compared + newsyntax + unparsed
    print("ref=%s (rev %s)  %d differing (file, mode) pairs; %d of %d pairs "
          "compared (%d unparsed, %d new syntax)"
          % (ref_dir, "supplied" if a.ref else a.rev, bad, compared, total,
             unparsed, newsyntax))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

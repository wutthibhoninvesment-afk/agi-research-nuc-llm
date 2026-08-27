#!/usr/bin/env python3
"""Self-hosting round 7 (round 200): characterize how guest-EVALUATOR memory
cost scales as self_host.lang's own 66-check test section is fed through
self_eval.lang's `run_src` in growing slices.

Round 192 first ran the FULL 66-check section through `run_src` and killed
it after RSS passed 1.7 GB and was still climbing (~3 min in) — a real data
point, but a single one with no curve behind it. Round 198 deferred a
follow-up because this machine's swap was already 80% full and shared with
live, non-research services (hermes-trading, taohu_trading bots, two Hermes
Agent gateways) — an unbounded repeat risked the kernel OOM-killer picking
an unrelated victim, not just this experiment.

This script removes that risk by construction: each slice runs in its own
fresh subprocess with `resource.setrlimit(RLIMIT_AS, cap)` set BEFORE any
Whence code runs. RLIMIT_AS is enforced by the kernel at mmap/brk time, so
the process can never map more virtual (and therefore resident) memory than
the cap regardless of what else the box is doing — a hit degrades to a
clean Python MemoryError in the one subprocess, not a system-wide OOM
sweep. Default cap is 700 MB, comfortably inside this run's own headroom
(`free -h` at launch: ~2.4 GiB "available", 369 MiB actually free, swap at
82%) with margin to spare.

usage: python3 bench/self_host_memscale.py [--cap-mb 700] [--timeout 60]
                                           [--checkpoints 5,10,20,...]
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "self_eval.lang")
SELF_HOST = os.path.join(ROOT, "examples", "self_host.lang")
MARKER = "# ==== SELF-TESTS"
LIB_START, LIB_END = 27, 561  # same slice as tests/test_self_hosting.py


def eval_library_source():
    src = open(EXAMPLE).read()
    assert MARKER in src
    return src.split(MARKER)[0]


def self_host_sections():
    lines = open(SELF_HOST).read().splitlines(keepends=True)
    lib = "".join(lines[LIB_START:LIB_END])
    assert lib.startswith("# ---- character classes")
    # test section: everything after the library up to (excluding) the
    # closing print() statement, which is not itself a check.
    rest = lines[LIB_END:]
    end = next(i for i, l in enumerate(rest) if l.startswith("print("))
    return lib, rest[:end]


def statement_boundaries(test_lines):
    """Indices of top-level statement starts (column-0, non-blank lines);
    Whence's own convention (confirmed throughout self_host.lang's test
    section) is that a continuation line is always indented, so any
    non-indented, non-blank line begins a fresh statement and is therefore
    a safe place to cut a prefix."""
    return [i for i, l in enumerate(test_lines)
            if l.strip() and not l[0].isspace()]


def checkpoint_slices(test_lines, checkpoints):
    """For each requested check-count, the largest text prefix of
    test_lines that ends exactly after that many top-level 'check '
    statements (including whatever preceding let/fn helpers it needs, and
    all of its own indented continuation lines)."""
    bounds = statement_boundaries(test_lines)
    slices = {}
    checks_seen = 0
    for pos, idx in enumerate(bounds):
        if test_lines[idx].startswith("check "):
            checks_seen += 1
        if checks_seen in checkpoints and checks_seen not in slices:
            end = bounds[pos + 1] if pos + 1 < len(bounds) else len(test_lines)
            slices[checks_seen] = "".join(test_lines[:end])
    return slices


def escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
              .replace("\n", "\\n").replace("\t", "\\t"))


PROBE = r'''
import resource, sys, time
resource.setrlimit(resource.RLIMIT_AS, (%(cap)d, %(cap)d))
sys.path.insert(0, %(root)r)
from whence.interp import Interpreter
eval_lib = %(eval_lib)r
prog = eval_lib + %(run_line)r
t0 = time.time()
try:
    env = Interpreter().run(prog)
except MemoryError:
    print("MEMORY_ERROR elapsed=%%.2f peak_kb=%%d" %% (
        time.time() - t0, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
    sys.exit(0)
elapsed = time.time() - t0
rec = env.get("__r").payload
parse_error = rec.fields["parse_error"].payload
n_checks = len(rec.fields["checks"].payload) if not parse_error else -1
failed = 0
if not parse_error:
    failed = sum(1 for c in rec.fields["checks"].payload
                 if c.payload.fields["pass"].payload is not True)
print("OK elapsed=%%.2f peak_kb=%%d parse_error=%%s checks=%%d failed=%%d" %% (
    elapsed, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    parse_error, n_checks, failed))
'''


def probe(inner_src, eval_lib, cap_bytes, timeout):
    # run_line is composed here, as real Python, and passed through %r
    # below (not hand-rolled quoting) so repr() picks a safe delimiter and
    # escapes it correctly regardless of what characters (quotes, em-dashes,
    # backticks, ...) self_host.lang's own comments happen to contain —
    # escape() only needs to produce a valid WHENCE string-literal body
    # (backslash/quote/newline/tab), not worry about the outer Python quoting.
    run_line = 'let __r = run_src("%s")\n' % escape(inner_src)
    code = PROBE % {"root": ROOT, "cap": cap_bytes, "eval_lib": eval_lib,
                     "run_line": run_line}
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                            text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "TIMEOUT (wall clock > %ds)" % timeout
    out = (r.stdout + r.stderr).strip().splitlines()
    last = out[-1] if out else "CRASH (no output)"
    if r.returncode != 0 and not (last.startswith("OK") or
                                   last.startswith("MEMORY_ERROR")):
        return "CRASH rc=%d %s" % (r.returncode, last[-160:])
    return last


def main(argv):
    cap_mb, timeout = 700, 60
    checkpoints = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 66]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--cap-mb":
            cap_mb = int(argv[i + 1]); i += 2
        elif a == "--timeout":
            timeout = int(argv[i + 1]); i += 2
        elif a == "--checkpoints":
            checkpoints = [int(x) for x in argv[i + 1].split(",")]; i += 2
        else:
            raise SystemExit("unknown arg: " + a)
    cap_bytes = cap_mb * 1024 * 1024
    lib, test_lines = self_host_sections()
    eval_lib = eval_library_source()
    slices = checkpoint_slices(test_lines, set(checkpoints))
    print("cap=%dMB timeout=%ds checkpoints=%s" % (cap_mb, timeout, checkpoints))
    consecutive_fail = 0
    for n in checkpoints:
        if n not in slices:
            print("%3d checks  (no such checkpoint — max is %d)" %
                  (n, max(slices)))
            continue
        inner_src = lib + "\n" + slices[n] + "\n"
        result = probe(inner_src, eval_lib, cap_bytes, timeout)
        print("%3d checks  src=%6d B  %s" % (n, len(inner_src), result))
        sys.stdout.flush()
        if result.startswith("OK"):
            consecutive_fail = 0
        else:
            consecutive_fail += 1
            if consecutive_fail >= 2:
                print("stopping: 2 consecutive non-OK results, larger "
                      "checkpoints would only get worse")
                break


if __name__ == "__main__":
    main(sys.argv[1:])

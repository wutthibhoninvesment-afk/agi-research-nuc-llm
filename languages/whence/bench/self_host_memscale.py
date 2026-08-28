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
sweep.

Round 204 set the default cap to 700 MB and reported the full 66-check
section landing comfortably under it through checkpoint 60 (436 MB), with
checkpoint 66 itself blocked only by wall-clock time, not memory. **That
700 MB figure went stale one round later and is no longer a safe default**:
round 206 gave `self_eval.lang` a real, working guest-level `steps` builtin
(self_host.lang checkpoint 47's own check calls it) — before round 206 the
same call failed immediately with a cheap "unbound name" miss, so round
204's own checkpoint-47-and-later readings never actually exercised it.
Once `steps` really runs, it walks the FULL host-level provenance graph
reachable from its argument (round 206's own writeup: "much larger... for
free, with zero guest-side reimplementation") — a one-time ~400 MB jump
right at checkpoint 47 (round 216 measurement: 282 MB at checkpoint 46,
690 MB at checkpoint 47), after which growth resumes the same roughly-
linear per-check slope as before. Round 216 confirmed this with a
controlled A/B (identical host code, `self_eval.lang` swapped between its
pre-/post-round-206 versions) before trusting it, and raised the default
cap to 1200 MB accordingly — comfortably above the round 216 measurement of
the FULL 66-check section actually completing end-to-end for the first
time (1072 MB peak, 66/66 checks passing, ~112 s). Re-check this default
against `free -h`'s "available" figure before raising it further; this
script's own safety property (a capped subprocess degrades to a clean
MemoryError, never a system-wide OOM) does not extend to choosing a cap
bigger than the box can actually back.

**Round 228: the 1200 MB cap is now stale again and this script has NOT
been re-run to find its replacement — treat any run against the current
`self_eval.lang` as likely to MemoryError at or before checkpoint 47.**
Round 227 measured a real but modest (~27%) tax from round 224's own 2
new dispatch branches (`matches`/`shapeof`) at matched CPU-time
checkpoints, using an isolated repro rather than this script (this host's
contention made a real run of this script itself impractical that
round). Round 228 went one step further with a DIFFERENT isolated repro
(no self_host.lang test-section checks at all, just the library load
plus a single trivial `steps(miss "x")` call — strictly less prior work
than even checkpoint 46) and found that alone reaches >1.35 GB RSS and is
still climbing near-linearly with no plateau after 5 minutes of
wall-clock, on a 1-CPU host — already exceeding this file's documented
checkpoint-47 number (690 MB) and closing in on its full-66-check number
(1072 MB) using a fraction of the prior work. Root cause (see
`tests/test_self_hosting.py`'s module docstring for the full writeup):
`steps()` walks self_eval.lang's ENTIRE store-threaded interpretation
trace once the library is loaded, not just the target value's own
derivation, so its cost tracks cumulative dispatch-table/library growth
across every round that adds a guest-parity builtin (206, 218, 222,
224 all compound here), not just the round that most recently touched
this file. A full re-sweep needs a materially higher cap (order 3000-
4000 MB, not the current 1200 MB) and longer per-checkpoint timeout
(order 600s, not 240s) — not attempted this round: repeating a multi-GB,
multi-minute-per-checkpoint probe across all 13 checkpoints on this
specific shared, heavily-contended host was judged not worth the
risk/cost for a number that will go stale again the next time this
builtin surface grows. Whoever next touches this file should re-derive
fresh rather than trust either the 700 MB, 1200 MB, or any number implied
above.

Checkpoint 66's own elapsed time is noisy under real box contention (round
216 saw it range from 112 s to a 150 s timeout across consecutive runs a
few minutes apart, same code, same cap) — the default 240 s timeout leaves
real margin, matching round 204's own "time is the safer failure mode"
framing (a TIMEOUT here is inconclusive, not a failure; rerun rather than
concluding the workload regressed).

**Round 254**: re-checked this file's own "not attempted this round"
gap from round 228 above, and made the SAME risk call again, for the
same reason, now with harder numbers: this box (`free -h` at the time)
had only 675 MB physically free and 2.1 GB "available", with swap
already 70% full (1.4/2.0 GB) — i.e. materially *less* headroom than
round 227/228 had when they first declined a multi-GB sweep, not more.
The RLIMIT_AS cap makes a capped subprocess fail cleanly instead of
triggering a system-wide OOM sweep, but it does not stop a multi-GB
resident probe from paging everything else on a 3.8 GB box through
swap while it runs — a real cost to the live, unrelated services this
host also runs (trading bots, Hermes gateways), not just to this
script. So: still no full 13-checkpoint re-sweep. Instead, added
`--mode steps-repro` below — round 228's own minimal isolation repro
(library load + one trivial `steps(miss ...)` call, no self_host.lang
test-section checks, no `parse_whence` call) promoted from an ad hoc
throwaway script into a permanent, reusable, and *safe-by-default* tool
mode: its own defaults (600 MB / 120 s) are chosen to be well inside this
run's 2.1 GB "available" figure, so a future round can get a real,
bounded data point on this cost's growth without needing to reproduce
the risk judgment call from scratch or spend multiple GB to do it. Ran
it this round at those defaults, measured (not guessed) via a live
subprocess: **MEMORY_ERROR at peak_kb=600796 (~600 MB), elapsed=88.82s**
(an initial 90 s timeout default was too tight — the run finished at
88.82s, so the shipped default is 120 s for real margin) — vs. round
228's own repro, run uncapped, reaching >1.35 GB and still climbing
after 291 s with no plateau. Consistent with, and a strictly cheaper/
safer confirmation of, round 228's finding that this cost is already
enormous before any real work happens, and has only grown since (this
round's own binop/unary guest-parity fix, round 252, added yet more
guest-level dispatch code that becomes part of every `st` trace). A
full re-sweep for a fresh absolute-MB replacement number still needs
the order-3000-4000 MB / 600 s treatment round 228 already flagged, on
a host that isn't mid-contention — not this one, not this round.

usage: python3 bench/self_host_memscale.py [--cap-mb 1200] [--timeout 240]
                                           [--checkpoints 5,10,20,...]
       python3 bench/self_host_memscale.py --mode steps-repro
                                           [--cap-mb 600] [--timeout 120]
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


def steps_repro_source(lib):
    """Round 228's own minimal isolation repro, as a reusable source
    builder: self_host.lang's function library (needed because the cost
    is driven by the LIBRARY LOAD's store-threaded trace, not by anything
    steps() is actually called on -- round 228 confirmed a trivial miss
    costs the same order of magnitude as a fully-parsed AST) plus exactly
    one `steps()` call on a trivial miss literal. Deliberately no
    self_host.lang test-section checks and no `parse_whence` call --
    strictly less prior work than even checkpoint 5."""
    return lib + '\nlet bad = miss "deliberate"\nsteps(bad)\n'


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
    mode = "sweep"
    cap_mb = timeout = None  # mode-specific defaults, picked below
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
        elif a == "--mode":
            mode = argv[i + 1]; i += 2
        else:
            raise SystemExit("unknown arg: " + a)
    if mode == "steps-repro":
        # small, safe-by-default: this is a diagnostic for "has the cost
        # gotten worse", not a full sweep -- see the round-254 module
        # docstring note for why the full sweep's own 1200 MB/240 s
        # defaults are deliberately NOT reused here.
        if cap_mb is None:
            cap_mb = 600
        if timeout is None:
            timeout = 120
        cap_bytes = cap_mb * 1024 * 1024
        lib, _ = self_host_sections()
        eval_lib = eval_library_source()
        inner_src = steps_repro_source(lib)
        print("mode=steps-repro cap=%dMB timeout=%ds" % (cap_mb, timeout))
        result = probe(inner_src, eval_lib, cap_bytes, timeout)
        print("library+1 steps() call  src=%6d B  %s" %
              (len(inner_src), result))
        return
    if cap_mb is None:
        cap_mb = 1200
    if timeout is None:
        timeout = 240
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

"""Round 353 (SWE-loop D): re-run round 137's 260 NO-EVIDENCE "kills".

`swe.scoreaudit` found that 260 of round 137's 1276 mutants were recorded as
`killed` on the strength of this output:

    no tests ran in 0.00s
    ERROR: file or directory not found: tests/test_timetravel_debugger.py

pytest exit 4. Zero tests ran. The pre-349 classifier read every non-zero
exit code as a kill, so all 260 counted toward a published score of 1.0.

Round 137's whole tree is archived at `state/swe/round-137/orig-proj` with
`whence/interp.py` pinned to that campaign's own snapshot, so the mutants can
be regenerated with the SAME ids and re-run against the SAME suite.

Method, and the two deliberate substitutions from round 137's own command:

  * `sys.executable` instead of the recorded macOS
    `/Library/Developer/CommandLineTools/usr/bin/python3` — that host is gone.
  * `-k "not ref_diff_fuzz"`, deselecting the two `tests/test_v10.py`
    `ref_diff_fuzz` tests. Neither can be made to pass 216 rounds later, in
    either direction, and both failures were measured here:
      - as archived, it fails `ModuleNotFoundError: No module named 'swe'`
        (exit 1, "1 failed, 613 passed in 148.47s") -- this snapshot's
        `bench/ref_diff.py` predates round 149's `AGI_RESEARCH_ROOT` fix and
        computes a tempdir-relative path to `harness/`;
      - with `PYTHONPATH=<repo>/harness` supplied so that import works, it
        then fails `assert (4 >= 5)` (exit 1, "1 failed, 613 passed in
        153.25s") -- the test asserts on how many of 12 programs from
        `swe.fuzz.ProgramGen` parse, and today's generator is not round
        137's.
    So these tests' verdicts are about the harness, never about the mutant
    (the second one, `..._transient_new_tree_timeout_is_retried_not_
    reported`, only surfaced once the first was deselected -- `-x` hides
    everything after the first failure, which is why the family and not the
    single test is filtered).
    Round 155 §3 diagnosed the first failure and confirmed it does not
    contaminate round 137's kills (`-x` stops at an earlier, legitimate
    test for every real mutation; it checked all 1276 kill details for
    `ModuleNotFoundError` and found zero). Deselecting one test is the
    smallest change that makes the tree measurable, and it is recorded here
    rather than hidden: a mutant that ONLY this test would have killed
    re-runs as `survived`.

The baseline is checked FIRST and the run aborts if it is not green — the
gate this round added to `swe.campaign`, applied to its own measurement.

The 260 are shuffled with a fixed seed and run SERIALLY (this host has one
core), appending one JSON line per finished mutant. Any prefix of the output
is therefore a uniform random sample of the 260, so a run that is cut short
still supports an honest interval instead of a biased head.

Resumable: re-running skips ids already in the JSONL.
"""
import json
import os
import random
import sys
import time

ROOT = "/home/pgain/agi-research-nuc-llm"
sys.path.insert(0, os.path.join(ROOT, "harness"))

from swe import mutation as MU          # noqa: E402
from swe import killers as K            # noqa: E402
from swe import scoreaudit as SA        # noqa: E402

PROJ = os.path.join(ROOT, "state/swe/round-137/orig-proj")
REPORT = os.path.join(ROOT, "state/swe/round-137/mutation-rechecked.json")
OUT = os.path.join(ROOT, "state/swe/round-353/r137-no-evidence-rerun.jsonl")
BASE = os.path.join(ROOT, "state/swe/round-353/r137-rerun-baseline.json")
DESELECT = "not ref_diff_fuzz"        # a -k filter: the whole coupled family
TEST_CMD = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
            "-k", DESELECT, "tests"]
SEED = 353
PER_MUTANT_TIMEOUT = 400.0


def log(s):
    print(s, flush=True)


def main():
    data = json.load(open(REPORT, encoding="utf-8"))
    targets = [m for m in data["mutants"]
               if SA.classify_recorded(m)[0] == "no_evidence_kill"]
    log("no-evidence kills in %s: %d of %d" % (os.path.basename(REPORT),
                                               len(targets), data["total"]))

    if os.path.exists(BASE):
        b = json.load(open(BASE, encoding="utf-8"))
        log("baseline: reusing %s" % BASE)
    else:
        log("baseline: running the unmutated archived tree ...")
        b = MU.baseline_check(PROJ, TEST_CMD, timeout_s=1200.0)
        b["green"] = b["returncode"] == 0
        b["test_cmd"] = TEST_CMD
        b["k_filter"] = DESELECT
        with open(BASE, "w", encoding="utf-8") as f:
            json.dump(b, f, indent=1)
    log("baseline %s: exit %s in %.1fs" % ("GREEN" if b["green"] else "RED",
                                           b["returncode"], b["seconds"]))
    if not b["green"]:
        log("ABORT: a mutation score against a non-green baseline is not evidence.")
        log(b["tail"])
        return 2

    done = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    done[d["id"]] = d
    order = list(targets)
    random.Random(SEED).shuffle(order)
    todo = [d for d in order if d["id"] not in done]
    log("resuming: %d of %d already run" % (len(done), len(order)))

    by_id = dict((m.id, m) for m in
                 K.rebuild_mutants(os.path.join(ROOT, "state/swe/round-137/snapshot"), order))
    missing = [d["id"] for d in order if d["id"] not in by_id]
    if missing:
        log("WARNING: %d mutant id(s) could not be regenerated from the snapshot: %s"
            % (len(missing), missing[:5]))

    t0 = time.time()
    for i, d in enumerate(todo):
        m = by_id.get(d["id"])
        if m is None:
            continue
        MU.run_mutant(m, PROJ, TEST_CMD, PER_MUTANT_TIMEOUT)
        rec = {"id": m.id, "line": m.lineno, "op": m.op,
               "description": m.description,
               "recorded_status": d["status"], "rerun_status": m.status,
               "seconds": round(m.seconds or 0, 1), "detail": (m.detail or "")[-400:],
               "audit": SA.classify_recorded({"status": m.status, "detail": m.detail})[0]}
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        log("%4d/%d %-9s %-32s %6.1fs  [%.0fs elapsed]"
            % (i + 1, len(todo), m.status, m.id, m.seconds or 0, time.time() - t0))
    log("DONE %d newly run in %.0fs" % (len(todo), time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())

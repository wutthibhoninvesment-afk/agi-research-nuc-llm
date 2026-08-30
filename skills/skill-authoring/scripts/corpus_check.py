#!/usr/bin/env python3
"""corpus_check.py — run every FREE skill-corpus checker over the live corpus
and reduce them to one PASS/FAIL line.

Why this exists
---------------
The corpus owns six checkers (`skill_lint`, `case_coverage`, `xref_check`,
`claim_check`, `state_claim_check`, and `carryforward_check` since round
369), all offline, all free, all fast — and before round 363 **nothing in
`run_driver.sh` ran any of them**. The driver
has two per-round health checks (round 241's `harness/run_tests_fast.sh` and
round 247's `languages/whence/run_tests_fast.sh`) and neither reads
`skills/`. So a corpus violation was found only by the next skills(B) round:
detection latency bounded by the ROTATION, up to six rounds.

Round 363 measured what that cost, by replaying every commit that touched
`skills/` against its own checkers (`corpus_history.py`):

    ERROR-red   2 of 59 commits, ONE episode, and it was open at HEAD
                (round 361 shipped H001+P001 and two rounds passed)
    strict-red  15 of 59 commits, one episode (B002), KNOWN and
                deliberately carried for 8 skills(B) rounds, closed on
                purpose by round 339

So the honest case for this file is NOT "violations are frequent" — they are
rare. It is that the latency was unbounded by anything except the rotation,
and this makes it one round.

The severity split, and why the exit code ignores warnings
----------------------------------------------------------
`--house --strict` makes skill_lint exit 1 on a WARNING. In this repo a
warning has meant a deliberately carried debt (B002's 415-line body, carried
on purpose across eight skills(B) rounds while every round reported it). A
health check that goes FAIL every round for a debt the program has decided to
carry is a check that gets ignored and then uninstalled — `skill-authoring`'s
own stated pitfall, and `case_coverage.py`'s stated reason for splitting
P001/P002 (errors) from P004 (a warning against a named baseline).

So: **the exit code is driven by ERRORS only.** Warnings are counted and
printed in the summary line the driver logs, so a carried debt stays visible
without ever making the signal cry wolf.

Not run here, deliberately
--------------------------
`claim_check --run` and `state_claim_check --run` EXECUTE the commands in
Verification blocks. Their static tiers are free and are what run here; the
`--run` tier is opt-in for a reason (round 339: the corpus contains commands
that ssh to another machine, spend money on live model calls, and run for
minutes). `trigger_eval.py` is priced and is never invoked from here.

Usage:
    python3 corpus_check.py [--repo-root DIR] [--json OUT]
    python3 corpus_check.py --line LABEL LOGFILE RC   # the driver.log line
Exit: 0 = no ERRORs, 1 = at least one ERROR, 2 = a checker could not run.

Why `--line` does not route through `harness.driver_health.health_line`
-----------------------------------------------------------------------
Round 349 moved the other two health checks' wording into
`driver_health.health_log_line` precisely so two call sites could not drift.
That classifier is PYTEST-shaped: it decides "the suite ran" by looking for a
`<n> passed|failed|...` pair in the log, and its ERROR branch says "suite did
not run (pytest exit N)". Fed this file's output it happens to reach the
right VERDICT in all four cases — `0 error(s)` matches its regex — but two of
its four sentences would then be false prose about a check that never ran
pytest.

`corpus_check.py` has a stricter contract than pytest does: the exit code
alone is the verdict (0 clean / 1 a rule was violated / 2 a checker could not
run), with no "did collection get far enough" ambiguity to infer. So the
wording lives here, next to the contract it describes, and
`test_corpus_check.py` pins it — the same design round 349 wanted, applied to
a different log format rather than borrowed from one.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

# `skill_lint.py`  -> `<path>: ERROR H001 <msg>` / `<path>: WARN B002 <msg>`
# `case_coverage`  -> `error: P001 <skill>: <msg>` / `warning: P004 ...`
# `claim_check` / `state_claim_check` -> `<path>:<line>: STALE C001 ...`
#                                        `<path>:<line>: CARRIED S005 ...`
# `xref_check`     -> its own summary line; its exit code is authoritative.
FINDING_RE = re.compile(
    r"(?:^|:\s*)(ERROR|WARN|STALE|CARRIED|error|warning)\b[:\s]+([A-Z]\d{3})\b")
ERROR_SEVERITIES = {"error", "stale"}


# Re-entry guard. `test_corpus_check.py::TestLiveCorpus` calls `main()` on
# the live corpus, and `main()` runs the `skills/` test suite — which
# contains that test. Round 363 built exactly that loop and watched it spin.
# The guard is an env var rather than a flag because it has to survive being
# reached through pytest, which no caller controls the argv of.
REENTRY_ENV = "SKILLS_CORPUS_CHECK_RUNNING"


def checks(root):
    """(name, argv). Order is cheapest-first so a broken tree fails fast.

    TWO enforcement surfaces, not one. The six checkers are the obvious
    half; `skills/*/scripts/test_*.py` is the other, and round 363 found it
    the hard way — `test_claim_check.py::test_only_the_known_prose_only_
    skills_parse_to_zero_commands` had been RED since round 359's commit
    `a439262`, four rounds, and nothing ran it either. A health check that
    covered only the checkers would have shipped green over a red test on the
    same day it was built to stop exactly that.
    """
    s = os.path.join(root, "skills", "skill-authoring", "scripts")
    return [
        ("skill_lint", [os.path.join(s, "skill_lint.py"),
                        os.path.join(root, "skills"), "--house", "--strict"]),
        ("case_coverage", [os.path.join(s, "case_coverage.py"),
                           "--repo-root", root]),
        ("claim_check", [os.path.join(s, "claim_check.py"),
                         os.path.join(root, "skills"), "--repo-root", root]),
        ("state_claim_check", [os.path.join(s, "state_claim_check.py"),
                               os.path.join(root, "state", "research-state.md"),
                               "--repo-root", root]),
        ("xref_check", [os.path.join(s, "xref_check.py")]),
        # Round 369. Not a SKILL.md rule — it checks that every
        # PREDICTIONS bank on disk is accounted for in
        # `state/prediction-bank-ledger.json` (CLAUDE.md D-013's
        # second half). It belongs here rather than in a fourth
        # health check for the reason this file exists at all: the
        # cost of a checker nothing runs is a latency bounded only by
        # the rotation, and round 362's dropped bank sat for 7 rounds
        # while two language(C) rounds ran past it. 0.7 s.
        ("carryforward", [os.path.join(s, "carryforward_check.py"),
                          "--repo-root", root]),
        # Last because it is the slow one (~37s vs ~3s for the five above),
        # and because a checker failing is the cheaper diagnosis to read
        # first. pytest's own exit codes land correctly on this file's
        # contract: 1 (tests failed) has no `[A-Z]\d{3}` code to parse and so
        # trips the `rc1` fallback into ERRORS_FOUND, while 2-5 (collection or
        # config never got there) is COULD_NOT_RUN, which is true.
    ] + ([] if os.environ.get(REENTRY_ENV) else [
        ("unit_tests", ["-m", "pytest", "-q",
                        os.path.join(root, "skills", "skill-authoring",
                                     "scripts"),
                        os.path.join(root, "skills", "session-inheritance-audit",
                                     "scripts")]),
    ])


def run_one(name, argv, root, timeout=600):
    if argv[0] != "-m" and not os.path.exists(argv[0]):
        return {"check": name, "status": "absent", "errors": [],
                "warnings": [], "summary": "script not present"}
    t0 = time.time()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **{REENTRY_ENV: "1"})
    try:
        p = subprocess.run([sys.executable] + argv, cwd=root, env=env,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"check": name, "status": "timeout", "errors": [],
                "warnings": [], "summary": "timed out after %ds" % timeout}
    out = (p.stdout or "") + (p.stderr or "")
    lines = [l for l in out.strip().splitlines() if l.strip()]
    if p.returncode == 2 or (p.returncode not in (0, 1)):
        return {"check": name, "status": "error", "rc": p.returncode,
                "errors": [], "warnings": [],
                "summary": lines[-1][:200] if lines else "rc=%d" % p.returncode}
    errors, warnings = set(), set()
    for line in lines:
        m = FINDING_RE.search(line)
        if not m:
            continue
        sev, code = m.group(1).lower(), m.group(2)
        (errors if sev in ERROR_SEVERITIES else warnings).add(code)
    # A checker with a non-zero exit and no parseable code still FAILS: its
    # own exit code is authoritative and an unparsed line must never read as
    # green (round 349's FAIL-vs-ERROR rule, applied to this layer).
    if p.returncode == 1 and not errors and not warnings:
        errors.add("rc1")
    return {"check": name, "status": "ran", "rc": p.returncode,
            "errors": sorted(errors), "warnings": sorted(warnings),
            "elapsed_s": round(time.time() - t0, 2),
            "summary": lines[-1][:200] if lines else ""}


# The exit-code contract. Anything not in this table is a bug in this file,
# and `driver_line` reports it as such rather than guessing.
PASS, ERRORS_FOUND, COULD_NOT_RUN = 0, 1, 2


def driver_line(label, log_path, rc):
    """The exact string `run_driver.sh` appends to `driver.log`."""
    summary = ""
    tail = ""
    try:
        with open(log_path, "r", errors="replace") as fh:
            lines = [l.rstrip() for l in fh if l.strip()]
        summary = lines[-1] if lines else ""
        tail = " ".join(lines[-5:])
    except OSError:
        return "%s UNKNOWN — corpus-check log unreadable — " % label
    if rc == PASS:
        return "%s PASS (%s)" % (label, summary)
    if rc == ERRORS_FOUND:
        return "%s FAIL — the corpus violates its own rules — %s" % (label,
                                                                     tail)
    if rc == COULD_NOT_RUN:
        return "%s ERROR — a checker could not run — %s" % (label, tail)
    return "%s ERROR — corpus-check died (exit %s) — %s" % (label, rc, tail)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--line"]:
        if len(argv) != 4:
            print("usage: corpus_check.py --line LABEL LOGFILE RC",
                  file=sys.stderr)
            return 2
        try:
            rc = int(argv[3])
        except ValueError:
            rc = -1
        print(driver_line(argv[1], argv[2], rc))
        return 0
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo-root", default=DEFAULT_REPO)
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)
    root = os.path.abspath(args.repo_root)

    results = [run_one(n, a, root) for n, a in checks(root)]
    for r in results:
        flag = ("ERROR " + ",".join(r["errors"])) if r["errors"] else (
            ("warn " + ",".join(r["warnings"])) if r["warnings"] else "ok")
        if r["status"] in ("absent", "timeout", "error"):
            flag = r["status"].upper()
        print("%-18s %-22s %s" % (r["check"], flag, r["summary"]))

    n_err = sum(len(r["errors"]) for r in results)
    n_warn = sum(len(r["warnings"]) for r in results)
    broken = [r["check"] for r in results
              if r["status"] in ("timeout", "error")]
    absent = [r["check"] for r in results if r["status"] == "absent"]
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"repo_root": root, "results": results}, f, indent=1)

    # The LAST line is what `run_driver.sh` logs on PASS (`tail -n 1`), so it
    # carries the whole verdict including the warning count.
    nested = " (nested: unit_tests skipped)" if os.environ.get(REENTRY_ENV) \
        else ""
    print("corpus-check: %d checker(s)%s, %d error(s), %d warning(s)%s%s"
          % (len(results), nested, n_err, n_warn,
             "; COULD NOT RUN: " + ",".join(broken) if broken else "",
             "; absent: " + ",".join(absent) if absent else ""))
    if broken:
        return COULD_NOT_RUN
    return ERRORS_FOUND if n_err else PASS


if __name__ == "__main__":
    sys.exit(main())

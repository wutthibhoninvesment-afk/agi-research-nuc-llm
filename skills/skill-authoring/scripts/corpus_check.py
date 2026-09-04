#!/usr/bin/env python3
"""corpus_check.py — run every FREE skill-corpus checker over the live corpus
and reduce them to one PASS/FAIL line.

Why this exists
---------------
The corpus owns seven checkers (`skill_lint`, `case_coverage`, `xref_check`,
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
import glob
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
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

# Round 417. The recall gap, carried to the line the driver actually reads.
#
# Round 339's rule is that a checker nobody watches must publish its recall
# gap. Every checker here obeyed it -- and published the gap on a line the
# AGGREGATOR THROWS AWAY. `run_one` keeps `lines[-1]`, so a denominator on
# the second-to-last line is invisible from here, and `driver_line` then
# reports a bare `0 error(s)` into `driver.log`. Round 415 paid for that
# exactly: round 414's block was logged `0 stale` while containing a flatly
# false item, because the item sat in the published-but-unquoted gap.
#
# The contract is one token, `coverage A/B unit[, C/D unit]*`, scanned out of
# the checker's FULL output rather than its last line -- deliberately, and
# not for elegance: `case_coverage`'s last line is already longer than the
# 200-character summary truncation below, so a clause appended to the end of
# it would be cut off before it ever reached here.
COVERAGE_RE = re.compile(
    r"\bcoverage[:\s]+((?:\d+/\d+\s+[a-z][a-z\-]*(?:\s+\(\d+%\))?)"
    r"(?:,\s*\d+/\d+\s+[a-z][a-z\-]*(?:\s+\(\d+%\))?)*)")


def coverage_of(output):
    """The LAST `coverage ...` clause in a checker's output, or ""."""
    found = COVERAGE_RE.findall(output or "")
    return re.sub(r"\s+", " ", found[-1]).strip() if found else ""


# ---------------------------------------------------------------------------
# Round 463 (harness A). THE ROW WHOSE CHILD IS A TEST RUNNER.
#
# Round 461's next-step 1: "`unit_tests` is 25 of the 60 red checker-rows and
# its failures are unrecoverable. `corpus_check.run_one` unlinks its
# `tempfile.mkstemp` sink in a `finally`, so no round can say WHICH test
# failed inside any red `unit_tests` row, ever." Re-derived at round 463 over
# `logs/skills_health_round_*.log`: **26 of 65**, over 99 logs (rounds
# 364-462), plus 5 TIMEOUT rows. The carried pair was a round stale; the
# claim it makes was not.
#
# Retention is the smaller half of the repair. The larger half is what the
# row published INSTEAD of the evidence it destroyed.
#
# `unit_tests` runs `pytest -q skills/skill-authoring/scripts
# skills/session-inheritance-audit/scripts`, and those tests INVOKE the other
# nine checkers. When one fails, pytest dumps the captured stdout of the
# checker it drove into the traceback -- so `_findings_in` and `coverage_of`,
# which exist to read a CHECKER's own output, read another checker's output
# through a test runner's failure report. Every field the row publishes is
# then borrowed:
#
#   codes     19 of the 26 red rows say `rc1`, which is honest. The other 7
#             say P001 / C001 / S001,S002,S006 -- other checkers' codes. Round
#             398's log is the clean specimen: `case_coverage ERROR P001`,
#             `state_claim_check ERROR S001,S002,S006`, and then `unit_tests
#             ERROR P001,S001,S002,S006`, the union of the two, re-read out of
#             pytest's traceback.
#   count     `n_err` sums `len(r["errors"])` over rows, so those borrowed
#             codes are DOUBLE-COUNTED in the number `driver_line` puts in
#             `driver.log`. Round 398 logged `9 error(s)` for 5 distinct
#             violations.
#   coverage  21 of the 99 aggregate lines name a `unit_tests <clause>`, and
#             it is another checker's clause verbatim -- round 419's is
#             `state_claim_check`'s `6/10 items (60%), 6/6 claims`, published
#             twice under two names on the line the driver logs.
#
# The fix is not a better regex. A test runner has no findings of its own to
# parse; it has an exit code and a list of node ids. So a check named here
# publishes ITS OWN verdict -- `rc1`, plus the failing node ids, plus the path
# to its retained output -- and the scraped fields are moved to `borrowed` in
# the `--json` result, kept rather than deleted so the next round can see what
# the row used to say.
#
# `rc1` is retained deliberately as the token, rather than something more
# descriptive: `corpus_history.LIVE_CODE_RE` matches `([A-Z]\d{3}|rc1)` over
# these logs' history and `redattrib.CORPUS_ROW` captures the codes token
# only when a single space follows the status word. A richer token here would
# have silently dropped this row from both readers, which is the same class of
# loss this round exists to stop.
#: The family `unit_tests` is pointed at, as a pattern, in ONE place.
#:
#: Round 477. This pattern had THREE readers and lived in one of them. The
#: `unit_tests` description below said "pytest over skills/*/scripts/test_*.py"
#: while `checks()` named two directories literally, and the glob matched
#: fifteen files in THREE -- `skills/prediction-banking/scripts` was missing,
#: so round 471's `test_bank_audit.py` (19 tests) was run by nothing
#: scheduled. Round 473 then read the DESCRIPTION, declared `bank_audit.py`
#: `wired` on the strength of it, and W002 was an ERROR for two rounds unseen.
#: A sentence is not an implementation, and the way to stop it drifting again
#: is to give the sentence and the oracle the same constant.
SKILL_TEST_GLOB = os.path.join("skills", "*", "scripts", "test_*.py")


def skill_test_dirs(root):
    """Repo-relative directories holding a `SKILL_TEST_GLOB` file, sorted.

    The ORACLE for `unit_tests`' argv -- deliberately NOT the argv itself.
    See `checks()` for the measurement that decided that, which is the
    interesting part: derivation is the right move for a subject set with one
    reader, and the wrong move here.
    """
    return sorted({os.path.relpath(os.path.dirname(q), root).replace(os.sep, "/")
                   for q in glob.glob(os.path.join(root, SKILL_TEST_GLOB))})


RUNNER_CHECKS = {
    "unit_tests":
        "pytest over the directories that hold a " + SKILL_TEST_GLOB + " "
        "file -- a LITERAL enumeration in `checks()`, held equal to that "
        "glob's expansion by `test_corpus_check.py` rather than derived from "
        "it, because `wiring_audit` cannot fold a glob and deriving it turns "
        "12 wired declarations into W002 errors (round 477); whose tests "
        "drive the other checkers, so any code, warning or coverage clause "
        "in its output belongs to a checker it ran, not to it",
}

#: A pytest node id in a `FAILED`/`ERROR` short-summary line. Anchored on
#: `.py` so a checker's own `ERROR P001 ...` line, which this same output can
#: contain, cannot be mistaken for a node id.
FAILED_NODE_RE = re.compile(r"^(?:FAILED|ERROR) (\S+\.py(?:::\S+)?)", re.M)


def failed_nodes(output):
    """Ordered, de-duplicated pytest node ids named FAILED/ERROR in `output`."""
    seen, order = set(), []
    for nid in FAILED_NODE_RE.findall(output or ""):
        if nid not in seen:
            seen.add(nid)
            order.append(nid)
    return order


#: Retention cap, in CHARACTERS of the child's decoded output. A red
#: `unit_tests` run is a pytest traceback dump and has no natural bound; the
#: cap is what stops one pathological round from writing a hundred megabytes
#: into `logs/`. Head AND tail are kept because they answer different
#: questions -- the head has the collection errors, the tail has pytest's
#: short summary (`FAILED <nodeid>`) and its count line, which is the part
#: `failed_nodes` reads.
MAX_EVIDENCE_CHARS = 256 * 1024
EVIDENCE_HEAD_CHARS = 64 * 1024


def elide(output, cap=MAX_EVIDENCE_CHARS, head=EVIDENCE_HEAD_CHARS):
    """(text, n_elided). Keeps the first `head` and the last `cap - head`.

    The marker names the number elided, so a reader can never mistake a
    capped file for a complete one -- round 453's subset-clause rule applied
    to a file instead of a summary line.
    """
    raw = output or ""
    if len(raw) <= cap:
        return raw, 0
    tail = cap - head
    dropped = len(raw) - cap
    return ("%s\n... [%d character(s) elided by corpus_check.py: kept the "
            "first %d and the last %d] ...\n%s"
            % (raw[:head], dropped, head, tail, raw[-tail:])), dropped


def round_label(root):
    """`round-463` from `state/round_counter`, else `round-unknown`.

    NOT passed in by `run_driver.sh` on purpose. The driver writes `ROUND` to
    that file at the top of a loop iteration and launches the four health
    checks later in the SAME iteration, so the counter is already this round's
    number when the check runs -- which means this retention works from the
    round that lands it, with none of the one-round re-exec lag round 457's
    fix had to warn its successor about.
    """
    try:
        with open(os.path.join(root, "state", "round_counter"),
                  encoding="utf-8") as fh:
            return "round-%d" % int(fh.read().strip())
    except (OSError, ValueError):
        return "round-unknown"


def default_evidence_dir(root):
    """`<root>/logs/corpus-evidence/round-<N>`."""
    return os.path.join(root, "logs", "corpus-evidence", round_label(root))


def _runner_verdict(res, output):
    """Replace a runner row's BORROWED fields with its own verdict.

    Keeps what it replaced under `borrowed`, because the question "what did
    this row used to say?" is exactly the one a round reading an old log will
    ask, and deleting the answer would repeat this file's own mistake.
    """
    res = dict(res)
    res["runner"] = True
    res["borrowed"] = {"errors": res["errors"], "warnings": res["warnings"],
                       "coverage": res["coverage"]}
    res["failed_nodes"] = failed_nodes(output)
    res["errors"] = (["rc1"] if res["status"] == "ran"
                     and res.get("rc") not in (0, None) else [])
    res["warnings"] = []
    res["coverage"] = ""
    return res


def _attach_evidence(res, output, evidence_dir):
    """Write a NOT-CLEAN run's output under `evidence_dir` and record where.

    A clean run writes nothing and creates no directory, so a repo whose
    corpus check passes never grows this tree at all. `absent` writes nothing
    either: there was no child and therefore no evidence.
    """
    if not evidence_dir:
        return res
    clean = (res["status"] == "ran" and res.get("rc") == 0
             and not res["errors"])
    if clean or res["status"] == "absent":
        return res
    body, dropped = elide(output or "")
    path = os.path.join(evidence_dir, "%s.out" % res["check"])
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(body)
    except OSError as exc:                                 # pragma: no cover
        res["evidence_error"] = "%s: %s" % (path, exc)
        return res
    res["evidence"] = path
    res["evidence_chars"] = len(body)
    res["evidence_lines"] = body.count("\n") + (1 if body else 0)
    res["evidence_elided"] = dropped
    return res


def _finish(res, output, evidence_dir):
    """The two things every non-`absent` result now gets."""
    if res["check"] in RUNNER_CHECKS:
        res = _runner_verdict(res, output)
    return _attach_evidence(res, output, evidence_dir)


def evidence_lines(results, root):
    """The `evidence: ...` lines printed under the rows, one per retention.

    Deliberately NOT row-shaped. `redattrib.CORPUS_ROW` matches a name
    followed by two or more spaces and a status word; `evidence:` is followed
    by a colon, so these lines cannot be read as checker rows by the module
    that counts them, and the 99 logs' historical row counts are unaffected.

    They sit ABOVE the `corpus-check:` summary, which means `driver_line`'s
    FAIL branch (`" ".join(lines[-5:])`) carries the retained PATH into
    `driver.log` with no change to `run_driver.sh` at all.
    """
    out = []
    for r in results:
        if r.get("evidence_error"):
            out.append("evidence: %s NOT retained — %s"
                       % (r["check"], r["evidence_error"]))
            continue
        if not r.get("evidence"):
            continue
        rel = os.path.relpath(r["evidence"], root)
        out.append("evidence: %s -> %s (%d line(s), %d char(s)%s, rc=%s)"
                   % (r["check"], rel, r["evidence_lines"],
                      r["evidence_chars"],
                      ", %d elided" % r["evidence_elided"]
                      if r["evidence_elided"] else "", r.get("rc")))
        nodes = r.get("failed_nodes") or []
        if nodes:
            shown = nodes[:5]
            out.append("evidence: %s failing node(s): %s%s"
                       % (r["check"], ", ".join(shown),
                          " (+%d more in the file)" % (len(nodes) - len(shown))
                          if len(nodes) > len(shown) else ""))
    return out


# Re-entry guard. `test_corpus_check.py::TestLiveCorpus` calls `main()` on
# the live corpus, and `main()` runs the `skills/` test suite — which
# contains that test. Round 363 built exactly that loop and watched it spin.
# The guard is an env var rather than a flag because it has to survive being
# reached through pytest, which no caller controls the argv of.
REENTRY_ENV = "SKILLS_CORPUS_CHECK_RUNNING"


# ---------------------------------------------------------------- round 453
# THE PRE-COMMIT SUBSET.
#
# `run_checks_fast.sh` (round 363) cut detection latency for a corpus
# violation from "the rotation, up to six rounds" to one round, by running
# this file after every round. Round 453 measured what one round has actually
# cost, over all 89 `skills-check` lines in `logs/driver.log` (rounds
# 364-452):
#
#   24 of 89 rounds (27%) ended with at least one ERROR
#   16 episodes; mean 1.50 rounds long, longest 4 (rounds 419-422, 431-434)
#   opened by: language(C) 7, SWE-loop(D) 6, harness(A) 2, NUC(E) 1
#              -- and skills(B) ZERO, in the whole log
#   closed by a skills(B) round in 9 of 15 (60%)
#
# So the rounds that break the corpus are never the round that owns it, and
# the check that would have told them runs AFTER they exit. Round 452 is the
# whole argument in one round: it shipped 18 dangling `decision 53` citations
# and an uncommitted artefact path, was killed by the outer timeout, and
# round 453 paid it.
#
# The fix is not another checker. It is making the ones that exist runnable
# BY THE ROUND THAT IS ABOUT TO COMMIT, which needs one thing: to be fast
# enough that a round will actually run it. Measured solo on this box
# (`nproc` 1), all ten checkers:
#
#   unit_tests 99.83s | verb_audit 15.29s | xref_check 4.44s
#   selfdesc_check 4.37s | carryforward 0.56s | skill_lint 0.21s
#   placeholder_check 0.19s | case_coverage 0.15s | claim_check 0.13s
#   state_claim_check 0.09s
#
# One checker is 80% of the cost. Dropping it leaves 25.4s -- and, measured
# against round 452's own shipped tree, the remaining nine catch ALL 19
# violations it shipped, because `unit_tests`'s three failures there were the
# live-corpus MIRRORS of `xref_check`'s and `carryforward`'s findings.
#
# THE PRESET IS DEFINED BY WHAT IT EXCLUDES, NOT BY A NAME LIST. This file's
# own history is the reason: `checks()`'s docstring said "five" checkers for
# two checkers' worth of drift, and `run_checks_fast.sh`'s header said "six"
# until round 429. A preset written as an inclusion list rots the same way --
# silently, by omission, with the omitted checker never running and nothing
# saying so. Written as an exclusion, a NEW checker joins the preset
# automatically and anyone who wants it out must name it here with a reason,
# which `test_corpus_check.py` enforces.
PRECOMMIT_EXCLUDES = {
    "unit_tests":
        "99.83s solo, 80% of the whole check's cost, and the only checker "
        "over 20s. Its live-corpus tests duplicate what xref_check, "
        "carryforward and skill_lint already report, so excluding it costs "
        "no error-detection power on the shipped-violation population "
        "measured in round 453; it keeps its own unit coverage, which is "
        "what the post-round run is for.",
}



def checks(root):
    """(name, argv). Order is cheapest-first so a broken tree fails fast.

    TWO enforcement surfaces, not one. The checkers are the obvious half
    (the count is deliberately not written here — it was "five" for two
    checkers' worth of drift, and round 429 made it eight); `skills/*/scripts/test_*.py` is the other, and round 363 found it
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
        # Round 429. Template tokens the record never filled in. Proposed by
        # round 427 and not run; round 428 gave it a discriminator and
        # published an inventory of ONE without running the scan, which finds
        # SIX -- five of them in `knowledge/`, the directory round 427's
        # version had already been burned for omitting. All six are
        # content-pinned in state/known-unfilled-placeholders.json with a
        # reason each, so this is green today and a SEVENTH hole is an error.
        # <0.5 s.
        ("placeholder_check", [os.path.join(s, "placeholder_check.py"),
                               "--repo-root", root]),
        # Round 435. The prose INSIDE the data files. Every other checker
        # here reads markdown, Python or a registry's STRUCTURE; none had
        # ever read a `_comment`, because `xref_check.SCANNED_EXTS` has no
        # `.json` in it. 26 artefacts carry ~26 000 characters of
        # present-tense assertion about themselves, and the first sweep found
        # four defects in them, one of which -- a registry header that
        # undercounted its own repoints by one -- had been contradicted by an
        # assertion in this tree since round 423. ~2 s.
        ("selfdesc_check", [os.path.join(s, "selfdesc_check.py"),
                            "--repo-root", root]),
        # Round 423. Round 421 measured that 84 of 92 declared CLI verbs on
        # wired entry points are invoked by nothing automatic, and then found
        # the second-order problem: no driver line and no checker read that
        # number, so 8.7% was re-derived only by a human typing the command.
        # A measurement nobody watches decays at the rate of the rotation,
        # which is this file's entire premise. All findings are WARN (V001/
        # V002/V003), so this can never turn the corpus red on its own --
        # it reports, and the coverage clause on its summary line is what
        # `coverage_of` lifts into the aggregate. ~30 s.
        # `--repo-root` is a TOP-LEVEL argument on this parser and must
        # precede the subcommand; argparse rejects it after `check`.
        ("verb_audit", [os.path.join(root, "harness", "verb_audit.py"),
                        "--repo-root", root, "check"]),
        # Last because it is the slow one (~37s vs ~3s for the five above),
        # and because a checker failing is the cheaper diagnosis to read
        # first. pytest's own exit codes land correctly on this file's
        # contract: 1 (tests failed) has no `[A-Z]\d{3}` code to parse and so
        # trips the `rc1` fallback into ERRORS_FOUND, while 2-5 (collection or
        # config never got there) is COULD_NOT_RUN, which is true.
    ] + ([] if os.environ.get(REENTRY_ENV) else [
        # The argv is a LITERAL enumeration of what `SKILL_TEST_GLOB`
        # matches, and `test_corpus_check.py::TestSkillTestDirs` keeps the
        # two equal. It is not a `glob.glob` call, and round 477 measured
        # why: `harness/wiring_audit.py:52` names "a `glob`" as its own
        # documented under-approximation, so a derived argv is invisible to
        # the invocation closure. Measured, not reasoned -- the glob version
        # took the closure from 109 files to 95 and turned TWELVE `wired`
        # declarations into W002 errors, including the very entry this edit
        # exists to wire. Two readers, one literal: the analyser needs the
        # names spelled out, the oracle needs the pattern, and the test is
        # what makes the pattern binding on the names.
        ("unit_tests", ["-m", "pytest", "-q",
                        os.path.join(root, "skills", "derived-subject-set",
                                     "scripts"),
                        os.path.join(root, "skills", "prediction-banking",
                                     "scripts"),
                        os.path.join(root, "skills",
                                     "seed-sweep-needs-a-same-seed-control",
                                     "scripts"),
                        os.path.join(root, "skills", "session-inheritance-audit",
                                     "scripts"),
                        os.path.join(root, "skills", "skill-authoring",
                                     "scripts")]),
    ])


def _findings_in(lines):
    """(errors, warnings) as sorted lists, parsed from any output lines."""
    errors, warnings = set(), set()
    for line in lines:
        m = FINDING_RE.search(line)
        if not m:
            continue
        sev, code = m.group(1).lower(), m.group(2)
        (errors if sev in ERROR_SEVERITIES else warnings).add(code)
    return sorted(errors), sorted(warnings)


# Round 451 (harness A). The budget clause.
#
# `unit_tests` did not fail suddenly. Its own source comment calls it "the
# slow one (~37s vs ~3s for the five above)" and it was measured at 162 s
# solo this round -- 4.4x that comment, with no round in between noticing,
# because the only number this file published about time was a boolean
# ("did it finish?") that stayed True until the round it did not. Five
# rounds then reported COULD NOT RUN.
#
# A rate that grows with the corpus needs a MARGIN reported every round, not
# a verdict reported once it is gone -- the `bounded-not-binary-witness`
# idea applied to a budget. Any checker past BUDGET_WARN_FRAC of its own
# timeout is named on the line the driver logs, with the fraction, so the
# round that crosses 50% is the round that gets told.
#
# The threshold is deliberately not 90%. The driver runs FOUR pytest suites
# concurrently on a box with `nproc` 1 (`run_driver.sh`, HEALTH_PID /
# WHENCE_PID / SKILLS_PID / NUC_PID), and round 435 next-step 8 measured
# that contention at roughly 3x. So a checker at 50% of budget when measured
# alone is already over it when the driver runs it -- which is exactly the
# arithmetic that produced rounds 431-450: 162 s solo x ~3.7 = ~600 s.
BUDGET_WARN_FRAC = 0.5


def budget_clause(results):
    """"; budget: <name> 512s/600s (85%)" for each checker over the fraction.

    Empty string when every checker is comfortably inside its budget, so the
    driver line does not grow a clause that says nothing.
    """
    over = []
    for r in results:
        limit, used = r.get("timeout_s"), r.get("elapsed_s")
        if not limit or used is None:
            continue
        if used >= BUDGET_WARN_FRAC * limit:
            over.append("%s %.0fs/%ds (%d%%)"
                        % (r["check"], used, limit, round(100.0 * used / limit)))
    return "; budget: " + ", ".join(over) if over else ""


def run_one(name, argv, root, timeout=600, evidence_dir=None):
    """Run one checker. The result ALWAYS carries what the checker managed
    to say, including when it was killed for running long.

    Round 451 (harness A) rewrote two things here, both of which had cost
    real rounds.

    1. THE TIMEOUT BRANCH DISCARDED THE RUN. It returned empty
       `errors`/`warnings`/`coverage` and the single sentence "timed out
       after 600s", so `unit_tests` -- which fired this branch in rounds 431,
       445, 448, 449 and 450 -- reported *nothing* about ten minutes of
       computation, and `driver.log` recorded five rounds of `COULD NOT RUN:
       unit_tests` with no clue whether anything had failed inside. A
       checker killed during its 501st test still knows 500 things. Output
       now goes to a real FILE rather than a pipe, so whatever the child
       wrote survives the kill regardless of how it died, and the timeout
       branch parses that partial output with the same `_findings_in` the
       normal path uses. THE VERDICT IS UNCHANGED: `status` is still
       `timeout`, so `main()` still returns COULD_NOT_RUN. Raising the
       budget or hiding the kill would have been the other repair and is
       explicitly not this one -- the point is to stop LOSING the evidence,
       not to stop reporting the failure.

    2. THE KILL LEAKED GRANDCHILDREN. `subprocess.run(timeout=)` kills the
       process it started and nothing below it. `unit_tests` is a pytest
       run whose tests spawn the other nine checkers, so every one of those
       five timeouts orphaned live checker processes onto a box with
       `nproc` 1, where they went on competing with the rest of the round.
       This repo had already written the pitfall down twice --
       `skills/fuzz-mutate-kill-loop/references/pitfalls.md` and
       `claim_check.run_command`'s docstring, which fixed the same bug in
       the same tree -- and this file never applied it. Own process group,
       `killpg` the group.

    `elapsed_s` is now on every branch. It was computed from `t0` and then
    dropped on three of the four, which is why no round could say how close
    a checker was to its budget before the round it went over.

    Round 463 (harness A) added the third thing that had cost real rounds:
    THE OUTPUT WAS STILL DESTROYED. Round 451 stopped the timeout branch
    from discarding what the child had SAID; the `finally` below still
    unlinked the file it said it in, on every branch, so a red row's only
    surviving trace was a codes token and pytest's count line. `evidence_dir`
    keeps a copy of a NOT-CLEAN run's output under `logs/corpus-evidence/
    round-<N>/<check>.out`, capped by `elide`, and records the path on the
    result. A CLEAN run keeps nothing and creates no directory.

    The temp sink itself is still unlinked unconditionally, as it always was:
    retention writes a second, named file from the text already in memory,
    so no failure path can leave a `/tmp` file behind.
    """
    if argv[0] != "-m" and not os.path.exists(argv[0]):
        return {"check": name, "status": "absent", "errors": [],
                "warnings": [], "coverage": "", "elapsed_s": 0.0,
                "timeout_s": timeout, "summary": "script not present"}
    t0 = time.time()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **{REENTRY_ENV: "1"})
    fd, sink_path = tempfile.mkstemp(prefix="corpus_check.%s." % name,
                                     suffix=".out")
    timed_out, rc = False, None
    try:
        with os.fdopen(fd, "wb") as sink:
            proc = subprocess.Popen([sys.executable] + argv, cwd=root,
                                    env=env, stdout=sink,
                                    stderr=subprocess.STDOUT,
                                    start_new_session=True)
            try:
                rc = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):  # already gone
                    proc.kill()
                proc.wait()
        with open(sink_path, encoding="utf-8", errors="replace") as f:
            out = f.read()
    finally:
        try:
            os.unlink(sink_path)
        except OSError:                                    # pragma: no cover
            pass
    elapsed = round(time.time() - t0, 2)
    lines = [l for l in out.strip().splitlines() if l.strip()]
    if timed_out:
        errors, warnings = _findings_in(lines)
        # The summary leads with the fact that it was killed -- that is the
        # headline and must not be buried -- and then says what was salvaged.
        # `lines` is empty when the checker was killed before it flushed a
        # single line, and "said nothing before the kill" is itself a
        # finding: it distinguishes a checker that is slow from one that
        # hung before it started.
        last = lines[-1][:120] if lines else ""
        return _finish({"check": name, "status": "timeout", "errors": errors,
                        "warnings": warnings, "coverage": coverage_of(out),
                        "elapsed_s": elapsed, "timeout_s": timeout,
                        "partial": True, "output_lines": len(lines),
                        "summary": "timed out after %ds; %s" % (
                            timeout,
                            ("%d line(s) before the kill, last: %s"
                             % (len(lines), last))
                            if lines else "said nothing before the kill")},
                       out, evidence_dir)
    if rc == 2 or (rc not in (0, 1)):
        return _finish({"check": name, "status": "error", "rc": rc,
                        "errors": [], "warnings": [],
                        "coverage": coverage_of(out),
                        "elapsed_s": elapsed, "timeout_s": timeout,
                        "summary": lines[-1][:200] if lines
                        else "rc=%d" % rc}, out, evidence_dir)
    errors, warnings = _findings_in(lines)
    # A checker with a non-zero exit and no parseable code still FAILS: its
    # own exit code is authoritative and an unparsed line must never read as
    # green (round 349's FAIL-vs-ERROR rule, applied to this layer).
    if rc == 1 and not errors and not warnings:
        errors = ["rc1"]
    return _finish({"check": name, "status": "ran", "rc": rc,
                    "errors": errors, "warnings": warnings,
                    "coverage": coverage_of(out),
                    "elapsed_s": elapsed, "timeout_s": timeout,
                    "summary": lines[-1][:200] if lines else ""},
                   out, evidence_dir)


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


def subset_clause(skipped):
    """The summary-line clause naming what a partial run did NOT run.

    Round 453. A SUBSET RUN MUST NOT LOOK LIKE A FULL ONE, and this is the
    whole reason `select` returns `skipped` rather than just the selection.
    Without it `--precommit` prints `corpus-check: 9 checker(s), 0 error(s)`
    -- which is indistinguishable from a clean run of everything to
    `run_driver.sh`, which greps this line, and to a future round quoting it.
    Silent truncation reading as full coverage is the failure this whole
    subset exists to avoid; reproducing it in the subset's own output would
    be the joke writing itself.

    Empty for a full run, so the line is byte-identical to what every round
    before 453 logged.
    """
    return ("; SUBSET, did NOT run: " + ",".join(skipped)) if skipped else ""


def select(all_checks, only=None, precommit=False):
    """Filter `checks()`'s (name, argv) list. Returns (selected, skipped).

    `only` is an explicit name list and wins over `precommit`. An unknown
    name is an error rather than a silent no-op -- a typo'd `--only xref`
    that quietly ran nothing would print a green line, which is the exact
    failure this whole subset exists to avoid.

    Round 453. Both results are returned because the CALLER MUST SAY WHAT IT
    SKIPPED. A subset run that prints the same summary shape as a full run is
    worse than no subset at all: `run_driver.sh` greps that line, this repo's
    rounds quote it, and "corpus-check: 9 checker(s), 0 error(s)" is
    indistinguishable from a clean full run unless the skipped names ride
    along.
    """
    names = [n for n, _ in all_checks]
    if only:
        wanted = [w.strip() for w in only if w.strip()]
        unknown = [w for w in wanted if w not in names]
        if unknown:
            raise ValueError("unknown checker(s): %s; known: %s"
                             % (", ".join(sorted(unknown)), ", ".join(names)))
        keep = set(wanted)
    elif precommit:
        keep = {n for n in names if n not in PRECOMMIT_EXCLUDES}
    else:
        return list(all_checks), []
    selected = [(n, a) for n, a in all_checks if n in keep]
    skipped = [n for n in names if n not in keep]
    return selected, skipped


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
    # Round 453. See PRECOMMIT_EXCLUDES for the measurement behind --precommit.
    ap.add_argument("--precommit", action="store_true",
                    help="run every checker except the ones named in "
                         "PRECOMMIT_EXCLUDES (25.4s vs 125s); for a round to "
                         "run on its own tree BEFORE its last commit")
    ap.add_argument("--only", default=None,
                    help="comma-separated checker names; see --list")
    ap.add_argument("--list", action="store_true",
                    help="print the checker names and exit")
    # Round 463 (harness A). See RUNNER_CHECKS and `_attach_evidence`.
    ap.add_argument("--evidence-dir", default=None,
                    help="where a NOT-CLEAN checker's own output is kept "
                         "(default: logs/corpus-evidence/round-<N>, the round "
                         "read from state/round_counter)")
    ap.add_argument("--no-evidence", action="store_true",
                    help="destroy a failing checker's output as this script "
                         "did before round 463; for a caller that must not "
                         "write to the tree")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.repo_root)

    all_checks = checks(root)
    if args.list:
        for n, _ in all_checks:
            print("%-18s %s" % (n, "EXCLUDED from --precommit: "
                                + PRECOMMIT_EXCLUDES[n]
                                if n in PRECOMMIT_EXCLUDES else ""))
        return PASS
    try:
        selected, skipped = select(all_checks,
                                   only=args.only.split(",") if args.only
                                   else None,
                                   precommit=args.precommit)
    except ValueError as exc:
        print("corpus_check: %s" % exc, file=sys.stderr)
        return COULD_NOT_RUN

    ev_dir = None if args.no_evidence else (
        args.evidence_dir or default_evidence_dir(root))
    results = [run_one(n, a, root, evidence_dir=ev_dir) for n, a in selected]
    for r in results:
        flag = ("ERROR " + ",".join(r["errors"])) if r["errors"] else (
            ("warn " + ",".join(r["warnings"])) if r["warnings"] else "ok")
        if r["status"] in ("absent", "timeout", "error"):
            flag = r["status"].upper()
        print("%-18s %-22s %s" % (r["check"], flag, r["summary"]))
    for line in evidence_lines(results, root):
        print(line)

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
    subset = subset_clause(skipped)
    cov = [r for r in results if r.get("coverage")]
    print("corpus-check: %d checker(s)%s%s, %d error(s), %d warning(s)%s%s%s%s"
          % (len(results), nested, subset, n_err, n_warn,
             "; COULD NOT RUN: " + ",".join(broken) if broken else "",
             "; absent: " + ",".join(absent) if absent else "",
             ("; coverage: " + "; ".join("%s %s" % (r["check"], r["coverage"])
                                         for r in cov)) if cov else
             "; coverage: none published",
             budget_clause(results)))
    if broken:
        return COULD_NOT_RUN
    return ERRORS_FOUND if n_err else PASS


if __name__ == "__main__":
    sys.exit(main())

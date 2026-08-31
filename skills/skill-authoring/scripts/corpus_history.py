#!/usr/bin/env python3
"""corpus_history.py — replay the skill corpus's own checkers over git history.

Why this exists
---------------
`case_coverage.py` (round 357) was built because the shipping checklist's
probe line was "documented and unenforced". It closed that hole and opened a
second one of exactly the same shape one level up: `case_coverage.py`,
`skill_lint.py`, `xref_check.py`, `claim_check.py` and `state_claim_check.py`
are all real, all free, all offline — and **nothing in `run_driver.sh` runs
any of them**. The driver has two per-round health checks (round 241's
`harness/run_tests_fast.sh`, round 247's `languages/whence/run_tests_fast.sh`)
and neither reads `skills/`. So a corpus violation is discovered only by the
next skills(B) round: one round in six, at best.

Round 363 found the predicted consequence at HEAD — round 361 (harness A)
shipped `skills/measured-not-declared-dependencies/` with an `H001` and a
`P001` ERROR, and two rounds passed without anyone learning that.

This tool answers the question that makes the fix worth its cost: **how
often, and for how long, has the corpus been RED under the rules it itself
shipped at that moment?**

Two views, deliberately separate
--------------------------------
``own``    At each commit that touched ``skills/``, run THAT COMMIT's own
           checkers against THAT COMMIT's own corpus, invoked with the flags
           that version of the script actually accepts. This is the honest
           "did a round ship a state its own tooling rejected?" question.
``today``  Run TODAY's checkers over every historical corpus. This measures
           RULE TIGHTENING, not rot — a commit that predates a rule was not
           red, it was ungoverned. Reported separately and never merged into
           the ``own`` count.

What this can and cannot see
----------------------------
Only the FREE/tracked half, which is exactly the split round 357 designed.
``state/trigger-eval/*.json`` is gitignored (`.gitignore:64`), so the probe
REPORTS are absent from every archived tree and `P004` (never/STALE probed)
fires everywhere in replay.

*Round 387 correction.* This paragraph used to continue: "`P004` is a WARNING
and does not set the exit code... ERROR codes — `H*`/`B*` from skill_lint,
`P001`/`P002`/`P005` from case_coverage — are computed from tracked files
only and ARE faithful." Both halves are false today and the second was made
false by a later round rather than being wrong when written. Round 375 added
`P008` and round 381 added `P006`/`P007` — three ERROR codes read off exactly
those gitignored reports. From round 375's own commit `78077fa` onward this
tool reported the corpus ERROR-red at **every** commit, and rendered a
10-commit episode "STILL OPEN" that is not a corpus violation at all. The
live check said PASS for all ten of those rounds.

The lesson is the reason `ARTIFACT_CODES` exists and is not a second prose
sentence: **the old text enumerated a family by listing its members**, and a
list of members is not a membership rule. Anything that names today's members
of an open set goes stale the moment the set grows, and nothing re-reads a
docstring. `ARTIFACT_CODES` is checked by `test_corpus_history.py`, which
pins the gitignore rule the quarantine rests on.

Two blind spots, both measured (round 387)
------------------------------------------
1. **Checker set.** This tool replayed 2 checkers; `run_checks_fast.sh`,
   shipped by the SAME round, runs 7. Across rounds 364-386 the live check
   failed 5 times and the code intersection with this tool's ERROR codes is
   **empty**. `--checkers all` closes it.
2. **Commit filter.** `git log -- skills/` is the directory the checkers LIVE
   in, not the one they READ. 4 of the 5 live failures produced no commit
   under `skills/` at all. `--scope read` widens 78 commits to 263.

Neither blind spot is closable in general, because the live check judges a
WORKING TREE and `git archive` can only rebuild commits. A round that dies at
max-turns leaves its violation untracked; a round that repairs one lands the
violation and the repair in a single commit. `logs/driver.log` is the only
durable record of either, which is what `live` mode reads.

Usage:
    python3 corpus_history.py own   [--json OUT] [--limit N] [--tail N]
                                    [--checkers core|all] [--scope home|read]
    python3 corpus_history.py today [--json OUT] [--limit N]
    python3 corpus_history.py episodes --json IN     # re-render from a report
    python3 corpus_history.py live  [--json IN]      # live verdicts vs replay
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

# A checker run is keyed by the script's repo-relative path so a version that
# does not exist at a commit is reported as `absent`, never as green.
SKILL_LINT = "skills/skill-authoring/scripts/skill_lint.py"
CASE_COVERAGE = "skills/skill-authoring/scripts/case_coverage.py"
CLAIM_CHECK = "skills/skill-authoring/scripts/claim_check.py"
STATE_CLAIM_CHECK = "skills/skill-authoring/scripts/state_claim_check.py"
XREF_CHECK = "skills/skill-authoring/scripts/xref_check.py"
CARRYFORWARD = "skills/skill-authoring/scripts/carryforward_check.py"

# v2 (round 387). The replay ran TWO checkers; `run_checks_fast.sh`, shipped
# by the SAME round (363), runs seven. Over rounds 364-386 -- the whole window
# in which both instruments have existed -- the live check went FAIL five
# times (365, 372, 374, 380, 386) and the ERROR code was `xref_check` twice
# and `carryforward` three times. Not once was it a code either replayed
# checker can emit. The two instruments had an EMPTY code intersection, and
# the replay's "2 of 59 ERROR-red" -- the number that justified building the
# live check -- was computed over a population that excluded every violation
# the live check has ever found.
#
# `core` is round 363's exact pair, kept so its published figures stay
# re-derivable; `all` is every checker in `corpus_check.py`'s list except
# `unit_tests`, which is a nested pytest run rather than a corpus rule.
CHECKER_SETS = {
    "core": (SKILL_LINT, CASE_COVERAGE),
    "all": (SKILL_LINT, CASE_COVERAGE, CLAIM_CHECK, STATE_CLAIM_CHECK,
            XREF_CHECK, CARRYFORWARD),
}

# Paths every checker in `all` reads, for `--scope read`. Round 363's filter
# is `git log -- skills/`, which is the directory the checkers LIVE in, not
# the one they READ. 78 of this repo's 281 commits touch `skills/`; 160 touch
# `state/` without touching `skills/`, and `state/` holds
# `prediction-bank-ledger.json`, every `known-*.json` baseline and every
# `*/round-*/PREDICTIONS.md` bank -- i.e. the entire input set of the two
# checkers responsible for three of the five live failures.
READ_SET = ("skills/", "state/", "knowledge/", "CLAUDE.md",
            "languages/whence/SPEC.md")

# Trees are materialized with `git archive`, so a path git does not carry is
# absent from every replayed tree. `.gitignore:64` excludes
# `state/trigger-eval/*.json` -- the probe REPORTS -- and `case_coverage.py`
# reads them to decide freshness and probe strength.
#
# Round 363 knew this and wrote down the consequence it could see: "`P004` is
# a WARNING and does not set the exit code... ERROR codes -- `H*`/`B*` from
# skill_lint, `P001`/`P002`/`P005` from case_coverage -- are computed from
# tracked files only and ARE faithful." That sentence enumerated a family by
# LISTING ITS MEMBERS, and nothing re-checked the list. Round 375 added
# `P008`, an ERROR that reads exactly those gitignored reports, and from its
# own commit `78077fa` onward the replay has reported the corpus ERROR-red at
# every single commit -- a 10-commit episode rendered "STILL OPEN" that is
# not a corpus violation at all. Round 381 added P006/P007 to the same family.
#
# Verified by construction, not asserted: extracting `4db91cd` and running
# today's `case_coverage.py` on it yields 2 P008 errors; copying the live
# `state/trigger-eval/*.json` reports into that same tree yields 0.
#
# A code here is neither red nor green. It is UNGOVERNABLE from git, which is
# the third status round 363's own `absent`/`unrunnable` discipline points at
# and did not reach. `test_corpus_history.py` pins the gitignore rule that
# justifies this set, so if the rule goes away the quarantine fails loudly
# instead of silently suppressing real findings.
ARTIFACT_INPUT = "state/trigger-eval/*.json"
ARTIFACT_CODES = frozenset({"P004", "P006", "P007", "P008"})

# Top-level paths `git archive`d into every replayed tree. A checker input
# that is NOT here is absent from the tree, and an absent input does not read
# as "absent" -- it reads as a VIOLATION, which is the worst of the three.
#
# This list is round 387's own mistake, caught by its own method. The first
# draft was `skills, state, knowledge, languages, CLAUDE.md` -- chosen by
# reading four checkers and writing down what they touched -- and the
# six-checker replay promptly reported 29 of 40 commits ERROR-red with
# `K003: round 340/352/358/364/370/376/382: no bank on disk at all`. All
# seven are NUC-integration(E) rounds, whose banks live in `nuc/`, which the
# list omitted. Not one of the seven was a real violation.
#
# That is the same failure as the docstring correction above, one level up
# and committed by the round that was writing the correction: **a hand-made
# list of an open set's current members.** So the list is no longer trusted
# on its own -- `test_corpus_history.py` re-derives the bank paths from the
# live ledger and fails if any of them falls outside this tuple.
EXTRACT_TOPS = ("skills", "state", "knowledge", "languages", "nuc",
                "CLAUDE.md")

# Two output shapes, both keyed by SEVERITY, because the distinction is the
# whole point of this tool. `skill_lint.py` prints
# `<path>: ERROR H001 <msg>` / `<path>: WARN B002 <msg>`; `case_coverage.py`
# prints `error: P001 <skill>: <msg>` / `warning: P004 ...`.
#
# A commit can be rc=1 for two completely different reasons and merging them
# would be the same mistake the tool exists to find:
#   error   a violation of a rule the corpus asserts as an ERROR — nobody
#           knew, and it should never have been committed
#   strict  only `--house --strict`'s warning-as-failure, which in this repo
#           means a KNOWN, deliberately carried debt (B002's 415-line body
#           was carried across seven consecutive skills(B) rounds ON PURPOSE)
FINDING_RE = re.compile(
    r"(?:^|:\s*)(ERROR|WARN|error|warning)\b[:\s]+([A-Z]\d{3})\b")


def classify(out):
    """Split a checker's findings into ERROR and WARNING code sets."""
    errors, warnings = set(), set()
    for line in out.splitlines():
        m = FINDING_RE.search(line)
        if not m:
            continue
        sev, code = m.group(1).lower(), m.group(2)
        (errors if sev == "error" else warnings).add(code)
    return sorted(errors), sorted(warnings)


def git(*args, **kw):
    return subprocess.run(["git", "-C", REPO] + list(args),
                          capture_output=True, text=True, **kw)


def skills_commits(limit=None, scope="home", tail=None):
    """Commits touching the selected path scope, oldest first.

    `home` is round 363's filter (`-- skills/`); `read` is the checkers' real
    input set. See READ_SET for why the two differ and by how much.
    """
    paths = ["skills/"] if scope == "home" else list(READ_SET)
    out = git("log", "--reverse", "--format=%H\t%ad\t%s", "--date=short",
              "--", *paths).stdout
    rows = []
    for line in out.splitlines():
        sha, date, subject = line.split("\t", 2)
        rows.append({"sha": sha, "short": sha[:7], "date": date,
                     "subject": subject})
    if tail:
        # The NEWEST `tail` commits. `--limit` takes the oldest, which is the
        # right window for "when did this rule first bind" and the wrong one
        # for "does the full checker set see the episodes the live check
        # caught", because those are all recent.
        return rows[-tail:]
    return rows[:limit] if limit else rows


def extract(sha, dest):
    """Materialize the tracked tree at `sha` into `dest`. Paths absent at that
    commit are skipped rather than aborting the whole archive."""
    wanted = []
    for p in EXTRACT_TOPS:
        if git("cat-file", "-e", "%s:%s" % (sha, p)).returncode == 0:
            wanted.append(p)
    if not wanted:
        return []
    tar = subprocess.run(["git", "-C", REPO, "archive", sha, "--"] + wanted,
                         capture_output=True)
    if tar.returncode != 0:
        return []
    subprocess.run(["tar", "-x", "-C", dest], input=tar.stdout, check=True)
    return wanted


def supported_flags(script_path, flags):
    """Which of `flags` this version of the script declares. Read from SOURCE,
    not from running `--help`: a script with no argv parsing runs its main
    effect on any argument (see the workspace's own `--help can mutate state`
    finding), and we are about to run 59 versions of two scripts we have not
    read."""
    try:
        src = open(script_path, encoding="utf-8").read()
    except OSError:
        return set()
    return {f for f in flags if ('"%s"' % f) in src or ("'%s'" % f) in src}


def takes_positional_paths(script_path):
    try:
        src = open(script_path, encoding="utf-8").read()
    except OSError:
        return False
    return 'add_argument("paths"' in src or "add_argument('paths'" in src


def run_checker(root, rel, argv, timeout=180):
    """Run one checker inside `root`. Returns a result dict; a checker that is
    absent, crashes, or times out is recorded as its own outcome and NEVER as
    green — the distinction round 349 drew between `FAIL` and `ERROR`."""
    script = os.path.join(root, rel)
    if not os.path.exists(script):
        return {"status": "absent"}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([sys.executable, script] + argv, cwd=root,
                           capture_output=True, text=True, timeout=timeout,
                           env=env)
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    out = (p.stdout or "") + (p.stderr or "")
    # argparse usage errors exit 2 with no check having run at all.
    if p.returncode == 2 and "usage:" in out:
        return {"status": "unrunnable", "rc": 2, "tail": out.strip()[-400:]}
    if p.returncode not in (0, 1):
        return {"status": "crash", "rc": p.returncode,
                "tail": out.strip()[-400:]}
    errors, warnings = classify(out)
    return {"status": "red" if p.returncode == 1 else "green",
            "rc": p.returncode, "errors": errors, "warnings": warnings,
            "red_kind": ("error" if errors else "strict"
                         ) if p.returncode == 1 else None,
            "summary": out.strip().splitlines()[-1] if out.strip() else ""}


def checker_argv(script_root, rel, mode_root):
    """The invocation for this VERSION of a checker. `--house --strict` is the
    corpus's own shipping-checklist invocation of skill_lint; a version that
    predates either flag is run without it and that is recorded."""
    script = os.path.join(script_root, rel)
    if rel == SKILL_LINT:
        argv = []
        if takes_positional_paths(script):
            argv.append(os.path.join(mode_root, "skills"))
        have = supported_flags(script, ["--house", "--strict"])
        argv += sorted(have)
        return argv, sorted(have)
    # v2 (round 387): the four checkers added to `all`. Two take a positional
    # target as well as `--repo-root`, and BOTH are probed from source by the
    # same `takes_positional_paths` rule rather than hard-coded, because a
    # version that predates the positional must be run without it or it is
    # recorded `unrunnable` for a reason that is not a violation.
    argv = []
    if rel == CLAIM_CHECK and takes_positional_paths(script):
        argv.append(os.path.join(mode_root, "skills"))
    elif rel == STATE_CLAIM_CHECK and takes_positional_paths(script):
        argv.append(os.path.join(mode_root, "state", "research-state.md"))
    if "--repo-root" in supported_flags(script, ["--repo-root"]):
        argv += ["--repo-root", mode_root]
    return argv, []


def split_artifact(codes):
    """(governable, ungovernable) — see ARTIFACT_CODES."""
    codes = set(codes)
    return sorted(codes - ARTIFACT_CODES), sorted(codes & ARTIFACT_CODES)


def replay(mode, limit=None, checkers="core", scope="home", tail=None):
    commits = skills_commits(limit, scope, tail)
    rows = []
    for i, c in enumerate(commits):
        tmp = tempfile.mkdtemp(prefix="corpushist-")
        try:
            present = extract(c["sha"], tmp)
            rec = dict(c, index=i, present=present, checkers={},
                       checker_set=checkers, scope=scope)
            for rel in CHECKER_SETS[checkers]:
                # `own`  : the checker FROM that commit, against that corpus.
                # `today`: the checker from HEAD's working tree, same corpus.
                script_root = tmp if mode == "own" else REPO
                if mode == "today" and not os.path.exists(
                        os.path.join(script_root, rel)):
                    rec["checkers"][rel] = {"status": "absent"}
                    continue
                if mode == "own" and not os.path.exists(os.path.join(tmp, rel)):
                    rec["checkers"][rel] = {"status": "absent"}
                    continue
                argv, flags = checker_argv(script_root, rel, tmp)
                if mode == "today":
                    # run HEAD's script but point every path at the old corpus
                    r = run_checker_external(script_root, rel, argv, tmp)
                else:
                    r = run_checker(tmp, rel, argv)
                r["flags"] = flags
                rec["checkers"][rel] = r
            rec["red"] = any(v.get("status") == "red"
                             for v in rec["checkers"].values())
            # A commit is ERROR-red if any checker reported a GOVERNABLE
            # ERROR code; `artifact` means every ERROR it reported was one
            # git cannot supply the inputs for (ARTIFACT_CODES); `strict`
            # means every red checker was warning-only.
            raw = sorted({e for v in rec["checkers"].values()
                          for e in v.get("errors", [])})
            rec["error_codes"], rec["artifact_codes"] = split_artifact(raw)
            rec["red_kind"] = None
            if rec["red"]:
                if rec["error_codes"]:
                    rec["red_kind"] = "error"
                elif rec["artifact_codes"]:
                    rec["red_kind"] = "artifact"
                else:
                    rec["red_kind"] = "strict"
            rec["unrunnable"] = sorted(rel for rel, v in rec["checkers"].items()
                                       if v.get("status") in
                                       ("unrunnable", "crash", "timeout"))
            rows.append(rec)
            sys.stderr.write("[%2d/%d] %s %s %s\n" % (
                i + 1, len(commits), c["short"],
                {"error": "RED!", "strict": "warn",
                 "artifact": "ungv"}.get(rec["red_kind"], "----"),
                ",".join(rec["error_codes"] or rec["artifact_codes"] or
                         sorted({w for v in rec["checkers"].values()
                                 for w in v.get("warnings", [])}))))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return rows


def run_checker_external(script_root, rel, argv, corpus_root, timeout=180):
    """`today` mode: HEAD's checker, historical corpus. skill_lint takes an
    explicit path so it needs nothing else; case_coverage needs --repo-root,
    which it has had since it was written."""
    script = os.path.join(script_root, rel)
    if not os.path.exists(script):
        return {"status": "absent"}
    if rel == CASE_COVERAGE and "--repo-root" not in argv:
        argv = argv + ["--repo-root", corpus_root]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([sys.executable, script] + argv, cwd=corpus_root,
                           capture_output=True, text=True, timeout=timeout,
                           env=env)
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode == 2 and "usage:" in out:
        return {"status": "unrunnable", "rc": 2, "tail": out.strip()[-400:]}
    if p.returncode not in (0, 1):
        return {"status": "crash", "rc": p.returncode,
                "tail": out.strip()[-400:]}
    errors, warnings = classify(out)
    return {"status": "red" if p.returncode == 1 else "green",
            "rc": p.returncode, "errors": errors, "warnings": warnings,
            "red_kind": ("error" if errors else "strict"
                         ) if p.returncode == 1 else None,
            "summary": out.strip().splitlines()[-1] if out.strip() else ""}


def episodes(rows, kind=None):
    """Maximal runs of consecutive RED commits, in skills/-commit order.

    An episode is OPEN when it reaches the newest commit — that is the one
    nobody has fixed yet, and it is the only kind whose length is still
    growing."""
    def is_red(r):
        if not r["red"]:
            return False
        return True if kind is None else r.get("red_kind") == kind

    eps, cur = [], None
    for r in rows:
        if is_red(r):
            if cur is None:
                cur = {"start": r["short"], "start_date": r["date"],
                       "start_subject": r["subject"], "commits": [],
                       "codes": set()}
            cur["commits"].append(r["short"])
            cur["codes"] |= (set(r["error_codes"])
                             or set(r.get("artifact_codes") or ())
                             or {w for v in r["checkers"].values()
                                 for w in v.get("warnings", [])})
        elif cur is not None:
            cur["end"] = r["short"]
            cur["end_date"] = r["date"]
            cur["closed_by"] = r["subject"]
            eps.append(cur)
            cur = None
    if cur is not None:
        cur["end"] = None
        cur["closed_by"] = None
        cur["open"] = True
        eps.append(cur)
    for e in eps:
        e["codes"] = sorted(e["codes"])
        e["length"] = len(e["commits"])
    return eps


# --------------------------------------------------------------------------
# `live` — the other instrument, and whether the two ever agree.
#
# `run_checks_fast.sh` writes one verdict line per round into logs/driver.log.
# That log is APPEND-ONLY and is the only durable record of a working-tree
# verdict: a round that dies at max-turns leaves its violation untracked, and
# a round that repairs one lands the violation and the repair in the SAME
# commit. Either way `git archive` can never reconstruct the state the live
# check actually judged. The log is not a convenience here; it is the only
# evidence that survives.
LIVE_RE = re.compile(
    r"round (\d+): skills-check (PASS|FAIL)\b(.*)$")
# The driver logs the summary line verbatim, so a code is read from it the
# same way `classify` reads a checker's own output. `rc1` is pytest's and
# xref_check's codeless failure and is kept as a pseudo-code rather than
# dropped -- it is what three of the five live failures were reported under.
# The checker name is a single identifier token. An earlier draft allowed
# spaces in it and swallowed the tail of the PREVIOUS checker's summary
# ("0 stale xref_check:rc1"), which is the same class of over-capture
# `_foreign_hint` hit in round 386 -- a pattern that matches something true
# about a wider span than the thing it is naming.
LIVE_CODE_RE = re.compile(r"\b(\w+)\s+(?:ERROR|error)\s+([A-Z]\d{3}|rc1)\b")


def live_rounds(log_path):
    """[{round, verdict, codes}] from a driver log, oldest first."""
    rows = []
    try:
        text = open(log_path, encoding="utf-8", errors="replace").read()
    except OSError:
        return rows
    for line in text.splitlines():
        m = LIVE_RE.search(line)
        if not m:
            continue
        codes = sorted({"%s:%s" % (c[0].strip(), c[1])
                        for c in LIVE_CODE_RE.findall(m.group(3))})
        rows.append({"round": int(m.group(1)), "verdict": m.group(2),
                     "codes": codes})
    return rows


def round_of(subject):
    m = re.search(r"Round (\d+)", subject or "")
    return int(m.group(1)) if m else None


def join_live(live, rows):
    """Per round: the live verdict, and what the replay says at that round's
    commit — `absent` when the round produced no commit in the replay scope,
    which is itself a verdict about the replay and not about the round."""
    # A round lands MORE THAN ONE commit -- round 370 banked its predictions
    # in one and registered them in the next, which is precisely how a K001
    # episode opens and closes inside a single round. Keeping only the first
    # commit per round reported round 374 as `strict` while a second
    # round-374 commit was K003-red. So every commit of a round is kept and
    # the round takes its WORST verdict.
    RANK = {"error": 3, "artifact": 2, "strict": 1, "green": 0}
    by_round = {}
    for r in rows:
        n = round_of(r["subject"])
        if n is not None:
            by_round.setdefault(n, []).append(r)
    out = []
    for lv in live:
        rs = by_round.get(lv["round"]) or []
        worst = max(rs, key=lambda r: RANK.get(r["red_kind"] or "green", 0),
                    default=None)
        out.append({
            "round": lv["round"],
            "live": lv["verdict"],
            "live_codes": lv["codes"],
            "replay": "absent" if worst is None else (
                worst["red_kind"] or "green"),
            "replay_codes": sorted({c for r in rs for c in
                                    r["error_codes"]
                                    + list(r.get("artifact_codes") or ())}),
            "commit": None if worst is None else worst["short"],
            "n_commits": len(rs),
        })
    return out


def bare(code):
    """`carryforward:K001` -> `K001`; `unit_tests:rc1` -> `rc1`."""
    return code.split(":")[-1]


def render_live(joined, log_path, rows):
    lines = ["# live vs. replay — %d round(s) with a skills-check verdict"
             % len(joined),
             "",
             "live   = `skills/run_checks_fast.sh`, 7 checkers, WORKING TREE,"
             " every round (%s)" % os.path.relpath(log_path, REPO),
             "replay = `corpus_history.py`, %d checker(s), COMMITS"
             % len({c for r in rows for c in r["checkers"]}),
             ""]
    fails = [j for j in joined if j["live"] == "FAIL"]
    absent = [j for j in fails if j["replay"] == "absent"]
    live_codes = {bare(c) for j in fails for c in j["live_codes"]}
    replay_err = {c for r in rows for c in r["error_codes"]}
    lines.append("live FAIL rounds:            %d of %d"
                 % (len(fails), len(joined)))
    lines.append("  ...with NO commit in the replay scope: %d" % len(absent))
    lines.append("live ERROR codes:            %s"
                 % (", ".join(sorted(live_codes)) or "-"))
    lines.append("replay ERROR codes (all commits): %s"
                 % (", ".join(sorted(replay_err)) or "-"))
    lines.append("CODE INTERSECTION:           %s"
                 % (", ".join(sorted(live_codes & replay_err)) or "EMPTY"))
    lines.append("")
    lines.append("| round | live | live codes | replay | replay codes | commit |")
    lines.append("|---|---|---|---|---|---|")
    for j in joined:
        lines.append("| %d | %s | %s | %s | %s | %s |" % (
            j["round"], j["live"], ", ".join(j["live_codes"]) or "-",
            j["replay"], ", ".join(j["replay_codes"]) or "-",
            j["commit"] or "—"))
    lines.append("")
    lines.append("## repair latency (rounds from a FAIL to the next PASS)")
    lines.append("")
    order = [j for j in joined]
    for i, j in enumerate(order):
        if j["live"] != "FAIL":
            continue
        nxt = next((k for k in order[i + 1:] if k["live"] == "PASS"), None)
        lines.append("- round %d → %s" % (
            j["round"],
            "round %d (%d round(s) later)" % (nxt["round"],
                                              nxt["round"] - j["round"])
            if nxt else "NEVER (still failing at the end of the log)"))
    return "\n".join(lines)


def render(rows, mode):
    lines = []
    lines.append("# corpus_history (%s) — %d commit(s) in scope"
                 % (mode, len(rows)))
    lines.append("")
    n_err = sum(1 for r in rows if r.get("red_kind") == "error")
    n_strict = sum(1 for r in rows if r.get("red_kind") == "strict")
    n_art = sum(1 for r in rows if r.get("red_kind") == "artifact")
    unrunnable = [r for r in rows if r["unrunnable"]]
    lines.append("ERROR-red:  %d/%d commit(s)   (a rule the corpus asserts as "
                 "an ERROR was violated)" % (n_err, len(rows)))
    lines.append("strict-red: %d/%d commit(s)   (rc=1 from --strict only: a "
                 "WARNING, in this repo a carried debt)" % (n_strict, len(rows)))
    lines.append("ungovernable: %d/%d commit(s) (rc=1 ONLY from %s — codes "
                 "whose inputs `%s` keeps out of every archived tree; neither "
                 "red nor green)"
                 % (n_art, len(rows), ",".join(sorted(ARTIFACT_CODES)),
                    ARTIFACT_INPUT))
    lines.append("checker could not run: %d commit(s)" % len(unrunnable))
    lines.append("")
    for kind, title in (("error", "ERROR episodes"),
                        ("artifact", "ungovernable episodes (NOT violations)"),
                        ("strict", "strict-warning episodes")):
        eps = episodes(rows, kind)
        lines.append("## %s — %d" % (title, len(eps)))
        lines.append("")
        lines.append("| # | commits | codes | opened by | closed by |")
        lines.append("|---|---|---|---|---|")
        for i, e in enumerate(eps, 1):
            lines.append("| %d | %d (%s..%s) | %s | %s %s | %s |" % (
                i, e["length"], e["commits"][0], e["commits"][-1],
                ",".join(e["codes"]), e["start_date"], e["start_subject"][:46],
                "STILL OPEN" if e.get("open") else e["closed_by"][:46]))
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=["own", "today", "episodes", "live"])
    ap.add_argument("--json", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--tail", type=int, default=None,
                    help="the NEWEST N commits in scope")
    ap.add_argument("--checkers", choices=sorted(CHECKER_SETS), default="core",
                    help="`core` is round 363's two; `all` adds the four the "
                         "live check runs and the replay never did")
    ap.add_argument("--scope", choices=["home", "read"], default="home",
                    help="`home` is commits touching skills/; `read` is "
                         "commits touching anything the checkers READ")
    ap.add_argument("--driver-log",
                    default=os.path.join(REPO, "logs", "driver.log"))
    args = ap.parse_args(argv)

    if args.mode == "episodes":
        if not args.json:
            ap.error("episodes needs --json IN")
        rows = json.load(open(args.json, encoding="utf-8"))["rows"]
        print(render(rows, "reloaded"))
        return 0

    if args.mode == "live":
        # `live` reuses a replay report when given one (`--json IN` that
        # already exists) so the join costs nothing after the replay is paid
        # for once.
        if args.json and os.path.exists(args.json):
            rows = json.load(open(args.json, encoding="utf-8"))["rows"]
        else:
            rows = replay("own", args.limit, args.checkers, args.scope,
                          args.tail)
        joined = join_live(live_rounds(args.driver_log), rows)
        print(render_live(joined, args.driver_log, rows))
        return 0

    rows = replay(args.mode, args.limit, args.checkers, args.scope,
                  args.tail)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"mode": args.mode, "checkers": args.checkers,
                       "scope": args.scope, "rows": rows,
                       "error_episodes": episodes(rows, "error"),
                       "artifact_episodes": episodes(rows, "artifact"),
                       "strict_episodes": episodes(rows, "strict")},
                      f, indent=1)
    print(render(rows, args.mode))
    return 0


if __name__ == "__main__":
    sys.exit(main())

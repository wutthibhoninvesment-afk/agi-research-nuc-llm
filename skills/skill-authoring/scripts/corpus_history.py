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
``state/trigger-eval/*.json`` is gitignored (`.gitignore:58`), so the probe
REPORTS are absent from every archived tree and `P004` (never/STALE probed)
fires everywhere in replay. `P004` is a WARNING and does not set the exit
code, so it does not affect any verdict here; it is counted and reported
under `warnings_ignored` so the omission is visible rather than silent.
ERROR codes — `H*`/`B*` from skill_lint, `P001`/`P002`/`P005` from
case_coverage — are computed from tracked files only and ARE faithful.

Usage:
    python3 corpus_history.py own   [--json OUT] [--limit N]
    python3 corpus_history.py today [--json OUT] [--limit N]
    python3 corpus_history.py episodes --json IN     # re-render from a report
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


def skills_commits(limit=None):
    """Commits touching skills/, oldest first."""
    out = git("log", "--reverse", "--format=%H\t%ad\t%s", "--date=short",
              "--", "skills/").stdout
    rows = []
    for line in out.splitlines():
        sha, date, subject = line.split("\t", 2)
        rows.append({"sha": sha, "short": sha[:7], "date": date,
                     "subject": subject})
    return rows[:limit] if limit else rows


def extract(sha, dest):
    """Materialize the tracked tree at `sha` into `dest`. Paths absent at that
    commit are skipped rather than aborting the whole archive."""
    wanted = []
    for p in ("skills", "state", "CLAUDE.md"):
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
    argv = []
    if "--repo-root" in supported_flags(script, ["--repo-root"]):
        argv += ["--repo-root", mode_root]
    return argv, []


def replay(mode, limit=None):
    commits = skills_commits(limit)
    rows = []
    for i, c in enumerate(commits):
        tmp = tempfile.mkdtemp(prefix="corpushist-")
        try:
            present = extract(c["sha"], tmp)
            rec = dict(c, index=i, present=present, checkers={})
            for rel in (SKILL_LINT, CASE_COVERAGE):
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
            # A commit is ERROR-red if ANY checker reported an ERROR code;
            # `strict` means every red checker was warning-only.
            rec["red_kind"] = None
            if rec["red"]:
                rec["red_kind"] = ("error" if any(
                    v.get("red_kind") == "error"
                    for v in rec["checkers"].values()) else "strict")
            rec["error_codes"] = sorted({e for v in rec["checkers"].values()
                                         for e in v.get("errors", [])})
            rec["unrunnable"] = sorted(rel for rel, v in rec["checkers"].items()
                                       if v.get("status") in
                                       ("unrunnable", "crash", "timeout"))
            rows.append(rec)
            sys.stderr.write("[%2d/%d] %s %s %s\n" % (
                i + 1, len(commits), c["short"],
                {"error": "RED!", "strict": "warn"}.get(rec["red_kind"], "----"),
                ",".join(rec["error_codes"] or
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
            cur["codes"] |= set(r["error_codes"]) or {
                w for v in r["checkers"].values() for w in v.get("warnings", [])}
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


def render(rows, mode):
    lines = []
    lines.append("# corpus_history (%s) — %d commit(s) touching skills/"
                 % (mode, len(rows)))
    lines.append("")
    n_err = sum(1 for r in rows if r.get("red_kind") == "error")
    n_strict = sum(1 for r in rows if r.get("red_kind") == "strict")
    unrunnable = [r for r in rows if r["unrunnable"]]
    lines.append("ERROR-red:  %d/%d commit(s)   (a rule the corpus asserts as "
                 "an ERROR was violated)" % (n_err, len(rows)))
    lines.append("strict-red: %d/%d commit(s)   (rc=1 from --strict only: a "
                 "WARNING, in this repo a carried debt)" % (n_strict, len(rows)))
    lines.append("checker could not run: %d commit(s)" % len(unrunnable))
    lines.append("")
    for kind, title in (("error", "ERROR episodes"),
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
    ap.add_argument("mode", choices=["own", "today", "episodes"])
    ap.add_argument("--json", default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)

    if args.mode == "episodes":
        if not args.json:
            ap.error("episodes needs --json IN")
        rows = json.load(open(args.json, encoding="utf-8"))["rows"]
        print(render(rows, "reloaded"))
        return 0

    rows = replay(args.mode, args.limit)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"mode": args.mode, "rows": rows,
                       "error_episodes": episodes(rows, "error"),
                       "strict_episodes": episodes(rows, "strict")},
                      f, indent=1)
    print(render(rows, args.mode))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""case_coverage.py — check that every skill in the corpus is REPRESENTED in
the evaluation corpus, instead of assuming it is.

Why this exists
---------------
`skill-authoring/SKILL.md`'s shipping checklist has two lines about this,
and both are requirements:

    [ ] `trigger_eval.py` shows 100% recall on the skill's cases and no
        false fires on negatives
    [ ] `trigger_eval.py … --audit <reports-dir>` exits 0: every skill
        `probed` under its current description, none `STALE`/`never`

`trigger_eval.py --audit` computes exactly that, offline and for free, and
exits 1 when it is false. Nothing in this workspace RUNS it. So the rule was
documented and unenforced, in the corpus that owns the skill for that exact
shape (`skills/unenforced-documented-rule/`), and the predicted consequence
happened: rounds 354, 355 and 356 each added a skill, none added a trigger
case, and three consecutive skills reached the corpus with **zero** cases.
A skill with no cases cannot be probed, cannot regress, and cannot fail —
it is invisible to every instrument the corpus has.

This file is the half of that checklist a test can enforce for free.

The split, and why it is not one check
--------------------------------------
Case coverage is FREE (it reads two files). Probe freshness is PRICED (a
probe is ~$0.05 of live model calls, and re-probing 27 skills is a real
spend a round has to choose to make). Making one check out of both would
mean either a test that costs money or a rule with no teeth.

So: P001/P002 are ERRORS — a test asserts them and they must be zero.
P004 is a WARNING against a BASELINE (`state/known-unprobed-skills.json`)
naming who owns each acknowledged gap, because a checker that can never go
green gets uninstalled (skill-authoring's own pitfall). P005 is the
baseline's own rot check: an entry that has since been probed, or that
names a skill that no longer exists, is an ERROR — an acknowledgement that
outlives its debt is how a baseline becomes a mute button.

Codes
-----
    P001  error    skill has fewer than the floor of positive cases
    P002  error    a case expects a skill that is not in the corpus
    P003  warning  a case prompt contains its own expected skill's name
                   (the probe answers itself; a fire is not evidence)
    P004  warning  skill never probed / STALE, and not in the baseline
    P005  error    baseline entry is stale (now probed, or skill is gone)

Duplicate case ids are NOT a code here: `trigger_eval.load_cases` already
raises on them, and two checks for one property is how they drift apart.

Usage:
    python3 case_coverage.py [--cases F] [--skills DIR] [--reports DIR]
                             [--baseline F] [--floor N] [--list]

Exit codes: 0 = no errors, 1 = at least one error, 2 = usage/IO problem.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trigger_eval  # noqa: E402  (same directory, deliberate)

DEFAULT_FLOOR = 3


def repo_root():
    """The repo this script lives in: scripts/ -> skill-authoring/ ->
    skills/ -> root."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", ".."))


def name_variants(name):
    """`session-inheritance-audit` also leaks as `session inheritance
    audit` and `session_inheritance_audit`. Only the FULL name counts: a
    single shared token ("skill", "agent") is ordinary domain vocabulary
    and flagging it would bury the real thing."""
    parts = name.split("-")
    if len(parts) < 2:
        return []
    return [re.compile(r"\b" + r"[\s_-]+".join(map(re.escape, parts)) + r"\b",
                       re.I)]


def check(catalog, cases, reports, baseline, floor=DEFAULT_FLOOR):
    """Returns (findings, rows). A finding is
    (severity, code, subject, message)."""
    findings = []
    known = {name for name, _, _ in catalog}
    rows = trigger_eval.audit_skills(catalog, cases, reports,
                                     positive_floor=floor)
    by_name = {r["name"]: r for r in rows}

    for r in rows:
        if r["under_floor"]:
            findings.append((
                "error", "P001", r["name"],
                "%d positive case(s) in the case file; the floor is %d. A "
                "skill with no cases cannot be probed and cannot regress."
                % (r["positives"], floor)))

    for c in cases:
        for want in c["expect"]:
            if want not in known:
                findings.append((
                    "error", "P002", c["id"],
                    "expects %r, which is not a skill in the corpus (renamed "
                    "or deleted?). The case can never pass." % want))
            else:
                for rx in name_variants(want):
                    if rx.search(c["prompt"]):
                        findings.append((
                            "warning", "P003", c["id"],
                            "prompt contains its own expected skill's name "
                            "(%r); the probe answers itself, so a fire is "
                            "not evidence the description works." % want))
                        break

    acked = baseline.get("skills", {})
    for name, entry in sorted(acked.items()):
        row = by_name.get(name)
        if row is None:
            findings.append((
                "error", "P005", name,
                "baseline acknowledges an unprobed skill that is not in the "
                "corpus; delete the entry."))
        elif row["status"] == "probed" and not row["under_floor"]:
            findings.append((
                "error", "P005", name,
                "baseline says unprobed, but it is `probed` under its "
                "current description (%s). Delete the entry: an "
                "acknowledgement that outlives its debt is a mute button."
                % row["report"]))
        elif not entry.get("owner"):
            findings.append((
                "error", "P005", name,
                "baseline entry has no `owner`; an unowned acknowledgement "
                "is indistinguishable from a forgotten one."))

    for r in rows:
        if r["status"] != "probed" and r["name"] not in acked:
            findings.append((
                "warning", "P004", r["name"],
                "probe status is `%s` under the description on disk; not in "
                "the baseline. Probe it, or acknowledge it with an owner."
                % r["status"]))

    return findings, rows


def main(argv=None):
    root = repo_root()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo-root", default=root)
    ap.add_argument("--cases", default=None)
    ap.add_argument("--skills", default=None)
    ap.add_argument("--reports", default=None)
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--floor", type=int, default=DEFAULT_FLOOR)
    ap.add_argument("--list", action="store_true",
                    help="print the per-skill coverage table too")
    args = ap.parse_args(argv)

    root = args.repo_root
    cases_p = args.cases or os.path.join(root, "skills", "trigger-cases.json")
    skills_p = args.skills or os.path.join(root, "skills")
    reports_p = args.reports or os.path.join(root, "state", "trigger-eval")
    base_p = args.baseline or os.path.join(root, "state",
                                           "known-unprobed-skills.json")

    try:
        cases = trigger_eval.load_cases(cases_p)
        catalog = trigger_eval.load_catalog([skills_p])
    except (OSError, ValueError) as exc:
        print("case-coverage: %s" % exc, file=sys.stderr)
        return 2
    reports = (trigger_eval.load_reports(reports_p)
               if os.path.isdir(reports_p) else [])
    baseline = {}
    if os.path.exists(base_p):
        try:
            with open(base_p, encoding="utf-8") as f:
                baseline = json.load(f)
        except (OSError, ValueError) as exc:
            print("case-coverage: %s" % exc, file=sys.stderr)
            return 2

    findings, rows = check(catalog, cases, reports, baseline, args.floor)

    if args.list:
        print("| skill | positives | probe status | acknowledged |")
        print("|---|---|---|---|")
        acked = baseline.get("skills", {})
        for r in sorted(rows, key=lambda r: r["name"]):
            print("| %s | %d | %s | %s |"
                  % (r["name"], r["positives"], r["status"],
                     acked.get(r["name"], {}).get("owner", "—")))
        print()

    for sev, code, subject, msg in findings:
        print("%s: %s %s: %s" % (sev, code, subject, msg))

    n_err = sum(1 for f in findings if f[0] == "error")
    n_warn = len(findings) - n_err
    n_probed = sum(1 for r in rows if r["status"] == "probed")
    print("case-coverage: %d skill(s), %d case(s) (%d negative); %d probed "
          "under the description on disk; %d error(s), %d warning(s)"
          % (len(rows), len(cases), sum(1 for c in cases if not c["expect"]),
             n_probed, n_err, n_warn))
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())

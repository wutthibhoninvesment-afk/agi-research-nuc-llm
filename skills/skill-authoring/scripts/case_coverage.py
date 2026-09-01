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

`probed` answers "did we look", not "what did we see" (round 375)
-----------------------------------------------------------------
Round 369 probed `measured-budget-sizing` at 0/3, kept the description
after round 141's stop-rule, and left this note in
`state/known-unprobed-skills.json`:

    P004 keys on FRESHNESS (was this skill probed under the description now
    on disk?) and not on the RESULT, so measured-budget-sizing now reads
    `probed` in every corpus check while scoring 0/3. "35 probed" is true
    and much weaker than it reads.

The reports needed to answer the other half are already committed under
`state/trigger-eval/`: every result carries `expect` and `fired`. So the
outcome half is FREE too, and until round 375 nothing read it. Measured on
the corpus of 36 skills, NINE of them had a newest-probing-report that was
not a clean sweep of their own cases, and the two shapes are different:

  * **RECALL** — the report probed the cases and the skill did not fire:
    `measured-budget-sizing` 0/3, `obligation-ledger` 0/3,
    `policy-replay-over-history` 3/4. Round 369 knew about all three.
  * **COVERAGE OF THE PROBE** — `probed` asserted from a strict SUBSET of
    the skill's own cases, which nobody knew: `fuzz-mutate-kill-loop` 1 of
    7, `measured-exemption` 1 of 3, `unrun-checker-latency` 1 of 3,
    `deleted-vs-never-written` / `optimization-transparency-differential` /
    `pristine-checkout-differential` 2 of 3.

The second shape has a CAUSE, and it is the reason this is a checker and
not a one-off cleanup. `audit_skills` reads the NEWEST report holding a
probe of the skill — and a re-probe is, by construction, a re-run of the
cases that MISSED. `state/trigger-eval/round-357-miss-reprobe.json` re-ran
the 8 cases that missed in the full-corpus sweep and 6 of them fired on the
retry, so four skills are now audited exclusively off their own retry and
their full-corpus misses are invisible. **Freshness plus "newest wins" is
survivorship bias: the most recent measurement is the one that was run
because the previous one failed.**

P006/P007 are WARNINGS against their own baseline
(`state/known-weak-probes.json`) for the same reason P004 is: the fix is a
re-probe, which is a live spend. That baseline pins the REPORT the
acknowledgement was made against (round 373's content-pin pattern), so a
newer probe expires the pin rather than being silently absorbed.

Codes
-----
    P001  error    skill has fewer than the floor of positive cases
    P002  error    a case expects a skill that is not in the corpus
    P003  warning  a case prompt contains its own expected skill's name
                   (the probe answers itself; a fire is not evidence)
    P004  warning  skill never probed / STALE, and not in the baseline
    P005  error    baseline entry is stale (now probed, or skill is gone)
    P006  warning  `probed` asserted from a strict SUBSET of the skill's
                   own positive cases, and not in the weak-probe baseline
    P007  warning  the newest probing report did not fire the skill on
                   every case it did probe, and not in the weak baseline
    P008  error    weak-probe baseline entry is stale: skill gone, no
                   owner, debt discharged, or the pinned report is no
                   longer the newest one (someone re-probed and did not
                   re-adjudicate)
    P009  warning  a durable weak-probe verdict rests on a single draw, or
                   two same-description reports disagree
    P010  warning  the POOLED interval over every same-digest probe lies
                   entirely BELOW 0.5 — the evidence refutes the
                   description (round 393). UNDECIDED is NOT a warning;
                   it is a headline count, because 26 of 46 are undecided
                   and 26 warnings is a check nobody reads.

Duplicate case ids are NOT a code here: `trigger_eval.load_cases` already
raises on them, and two checks for one property is how they drift apart.

Usage:
    python3 case_coverage.py [--cases F] [--skills DIR] [--reports DIR]
                             [--baseline F] [--weak-baseline F] [--floor N]
                             [--list]

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


def check(catalog, cases, reports, baseline, floor=DEFAULT_FLOOR,
          weak_baseline=None):
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

    findings += check_outcomes(by_name, weak_baseline or {})
    findings += check_replication(weak_baseline or {},
                                  trigger_eval.replication_rows(
                                      catalog, cases, reports))
    findings += check_pooled(trigger_eval.pooled_rows(catalog, cases, reports),
                             weak_baseline or {})
    return findings, rows


def check_outcomes(by_name, weak_baseline):
    """P006/P007/P008 — what the probe SAW, against its own baseline.

    Only skills whose freshness status is already `probed` are asked the
    outcome question: a `never`/`STALE` skill is P004's, and three warnings
    for one skill is how a warning list stops being read."""
    findings = []
    weak = weak_baseline.get("skills", {})

    for name, entry in sorted(weak.items()):
        row = by_name.get(name)
        if row is None:
            findings.append((
                "error", "P008", name,
                "weak-probe baseline names a skill that is not in the "
                "corpus; delete the entry."))
            continue
        if not entry.get("owner"):
            findings.append((
                "error", "P008", name,
                "weak-probe baseline entry has no `owner`; an unowned "
                "acknowledgement is indistinguishable from a forgotten "
                "one."))
        if (row["status"] == "probed" and row["covered"] == row["positives"]
                and row["recalled"] == row["covered"]):
            findings.append((
                "error", "P008", name,
                "weak-probe baseline says the probe is weak, but %s covers "
                "all %d positive case(s) with full recall. Delete the "
                "entry: an acknowledgement that outlives its debt is a mute "
                "button." % (row["report"], row["positives"])))
        elif entry.get("report") and row["report"] != entry["report"]:
            findings.append((
                "error", "P008", name,
                "weak-probe baseline pins %r, but the newest probing report "
                "is now %r — someone re-probed and did not re-adjudicate. "
                "Re-read the new report and rewrite or delete the entry."
                % (entry["report"], row["report"])))

    for r in sorted(by_name.values(), key=lambda r: r["name"]):
        if r["status"] != "probed" or r["name"] in weak:
            continue
        if r["covered"] < r["positives"]:
            findings.append((
                "warning", "P006", r["name"],
                "`probed` is asserted from %d of its %d positive case(s): "
                "%s is the newest report holding a probe of it, and a "
                "re-probe is by construction a re-run of what MISSED. "
                "Re-probe the whole case set, or acknowledge it with an "
                "owner." % (r["covered"], r["positives"], r["report"])))
        if r["covered"] and r["recalled"] < r["covered"]:
            findings.append((
                "warning", "P007", r["name"],
                "the newest probing report %s fired it on %d of the %d "
                "case(s) it probed%s — `probed` says the description was "
                "measured, not that it works. Re-probe, edit the "
                "description, or acknowledge it with an owner."
                % (r["report"], r["recalled"], r["covered"],
                   " (%d flaky)" % r["flaky"] if r["flaky"] else "")))
    return findings


def check_pooled(pooled, weak_baseline):
    """P010 — what the POOLED evidence positively REFUTES.

    Round 393. Every other code here reads a report at a time. P006/P007
    read *the newest* one; P009 asks whether a *second* exists. None of
    them ever asked the question a verdict actually needs: pool every
    same-digest probe, and does the interval separate this description
    from a coin flip?

    Run it and the corpus's self-image changes. **19 skills** read
    `probed`, `covered == positives`, `recalled == covered` — the state the
    headline calls "full recall" — off exactly **3 probes in one run**.
    Wilson 95% on 3/3 is [0.44, 1.00]. That does not exclude 0.5. Those
    nineteen were never measured; they were sampled once and rounded up.

    P010 fires ONLY where the interval lies entirely below the threshold —
    a description the evidence refutes, which is rare and actionable. The
    much larger UNDECIDED population, and the count of `WORKS` verdicts
    resting on a single run (round 393 measured run-level ICC 0.333, so
    six probes in one invocation are worth 2.25 independent draws — see
    ``trigger_eval.run_variance``), ride in the summary line instead.

    A WARNING, never an error, and a skill already carrying a weak-probe
    acknowledgement is skipped: the fix is a live spend, and a check that
    can only go green by spending money is a check a round uninstalls."""
    findings = []
    weak = weak_baseline.get("skills", {})
    for r in sorted(pooled, key=lambda r: r["name"]):
        if r["verdict"] != "BROKEN" or r["name"] in weak:
            continue
        findings.append((
            "warning", "P010", r["name"],
            "pooled %d/%d over %d run(s) — Wilson 95%% [%.2f, %.2f] lies "
            "entirely BELOW 0.5, so the evidence REFUTES this description "
            "rather than failing to confirm it. Edit it once and re-probe "
            "(round 141's stop-rule), or acknowledge it with an owner."
            % (r["k"], r["n"], r["runs"], r["lo"], r["hi"])))
    return findings


def pooled_summary(pooled):
    """(works, undecided, broken, single_run_works) over probed skills.

    Round 393 deliberately does NOT emit one warning per UNDECIDED skill.
    26 of the 46 are undecided; 33 new warnings would bury P010's handful
    of real refutations and the check would stop being read — P004's own
    reasoning, and the reason `run_checks_fast.sh` is exit-code-driven by
    errors only. The count rides in the summary line instead, which is the
    line `run_driver.sh` logs every round."""
    works = sum(1 for r in pooled if r["verdict"] == "WORKS")
    und = sum(1 for r in pooled if r["verdict"] == "UNDECIDED")
    broken = sum(1 for r in pooled if r["verdict"] == "BROKEN")
    single = sum(1 for r in pooled
                 if r["verdict"] == "WORKS" and r["runs"] < 2)
    return works, und, broken, single


def check_replication(weak_baseline, repl_rows):
    """P009 — a DURABLE adjudication that rests on a single draw.

    Round 381. Everything P006/P007/P008 say is read off *the newest report
    holding a probe*, and `state/known-weak-probes.json` records permanent
    verdicts about descriptions on exactly that basis. Round 381 measured
    what one report is worth: two runs of a byte-identical configuration
    disagreed at majority level on 11 of 29 cases, and the two entries this
    file carried as KNOWN-BAD DESCRIPTIONS -- `measured-budget-sizing`
    (0/3 twice) and `obligation-ledger` (1/3 then 0/3) -- re-measured at
    9/9 and 6/9. Both verdicts were draws.

    So P009 asks the one question nothing else asked: does a SECOND
    independent report agree? It fires ONLY on skills that already carry an
    adjudication, which is what keeps it from being 41 warnings nobody
    reads -- an unreplicated skill with no verdict written about it is not
    a problem, it is just unprobed twice. Two shapes:

      * ``n_reports <= 1`` — the entry cannot have been replicated.
      * ``disagree`` non-empty — two same-description reports reached
        DIFFERENT verdicts on a case, so the entry pinned one of them.

    Warning, never error: the fix is a re-probe, which is a live spend, and
    a check that can only go green by spending money is a check a round
    uninstalls (P004's own reasoning, and this file's)."""
    findings = []
    by_name = {r["name"]: r for r in repl_rows}
    for name, entry in sorted(weak_baseline.get("skills", {}).items()):
        row = by_name.get(name)
        if row is None:
            continue
        if row["n_reports"] <= 1:
            findings.append((
                "warning", "P009", name,
                "the weak-probe verdict rests on %d report(s) under the "
                "description on disk — an UNREPLICATED draw. Round 381 "
                "measured two runs of one configuration disagreeing on 11 "
                "of 29 cases. Re-probe once more before this entry is "
                "quoted again." % row["n_reports"]))
        elif row["disagree"]:
            findings.append((
                "warning", "P009", name,
                "%d same-description report(s) DISAGREE on %s — the entry "
                "pins %r, which is one of them. Say in `why` which draws "
                "were seen and what the pooled rate is, or re-probe."
                % (row["n_reports"], ", ".join(row["disagree"]),
                   entry.get("report"))))
    return findings


def replication_summary(repl_rows):
    """(replicated_skills, total_skills, disagreeing_cases, compared_cases)."""
    tot = len(repl_rows)
    rep = sum(1 for r in repl_rows if r["n_reports"] >= 2)
    comp = sum(len(r["compared"]) for r in repl_rows)
    dis = sum(len(r["disagree"]) for r in repl_rows)
    return rep, tot, dis, comp


def main(argv=None):
    root = repo_root()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo-root", default=root)
    ap.add_argument("--cases", default=None)
    ap.add_argument("--skills", default=None)
    ap.add_argument("--reports", default=None)
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--weak-baseline", default=None)
    ap.add_argument("--floor", type=int, default=DEFAULT_FLOOR)
    ap.add_argument("--list", action="store_true",
                    help="print the per-skill coverage table too")
    ap.add_argument("--replication", action="store_true",
                    help="print the per-skill cross-report replication "
                         "table too (round 381)")
    args = ap.parse_args(argv)

    root = args.repo_root
    cases_p = args.cases or os.path.join(root, "skills", "trigger-cases.json")
    skills_p = args.skills or os.path.join(root, "skills")
    reports_p = args.reports or os.path.join(root, "state", "trigger-eval")
    base_p = args.baseline or os.path.join(root, "state",
                                           "known-unprobed-skills.json")
    weak_p = args.weak_baseline or os.path.join(root, "state",
                                                "known-weak-probes.json")

    try:
        cases = trigger_eval.load_cases(cases_p)
        catalog = trigger_eval.load_catalog([skills_p])
    except (OSError, ValueError) as exc:
        print("case-coverage: %s" % exc, file=sys.stderr)
        return 2
    reports = (trigger_eval.load_reports(reports_p)
               if os.path.isdir(reports_p) else [])
    loaded = {}
    for key, path in (("baseline", base_p), ("weak", weak_p)):
        loaded[key] = {}
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                loaded[key] = json.load(f)
        except (OSError, ValueError) as exc:
            print("case-coverage: %s" % exc, file=sys.stderr)
            return 2
    baseline = loaded["baseline"]

    findings, rows = check(catalog, cases, reports, baseline, args.floor,
                           weak_baseline=loaded["weak"])

    if args.list:
        print("| skill | positives | covered | recalled | probe status "
              "| acknowledged |")
        print("|---|---|---|---|---|---|")
        acked = baseline.get("skills", {})
        weak = loaded["weak"].get("skills", {})
        for r in sorted(rows, key=lambda r: r["name"]):
            owner = (acked.get(r["name"]) or weak.get(r["name"])
                     or {}).get("owner", "—")
            print("| %s | %d | %d | %d | %s | %s |"
                  % (r["name"], r["positives"], r["covered"], r["recalled"],
                     r["status"], owner))
        print()

    for sev, code, subject, msg in findings:
        print("%s: %s %s: %s" % (sev, code, subject, msg))

    n_err = sum(1 for f in findings if f[0] == "error")
    n_warn = len(findings) - n_err
    n_probed = sum(1 for r in rows if r["status"] == "probed")
    # Round 375: "N probed" answers "did we look". The corpus check's
    # headline is the line the driver logs every round, so it now also
    # carries what the probe SAW -- every positive case reached, and the
    # skill fired on every one of them.
    n_clean = sum(1 for r in rows if r["status"] == "probed"
                  and r["covered"] == r["positives"]
                  and r["recalled"] == r["covered"])
    # Round 381: "N probed ... with full recall" answers "what did ONE
    # report see". It cannot answer "would a second report see it too",
    # and this round measured that two runs of one configuration disagree
    # on 11 of 29 cases. The headline the driver logs now carries the
    # replication figure alongside the outcome figure, so a reader can
    # tell a measured description from a single draw without opening a
    # report.
    repl = trigger_eval.replication_rows(catalog, cases, reports)
    n_rep, n_tot, n_dis, n_comp = replication_summary(repl)
    if args.replication:
        print("| skill | reports | compared | disagree |")
        print("|---|---|---|---|")
        for r in sorted(repl, key=lambda r: (-len(r["disagree"]),
                                             -r["n_reports"], r["name"])):
            print("| %s | %d | %d | %s |"
                  % (r["name"], r["n_reports"], len(r["compared"]),
                     ", ".join(r["disagree"]) or "—"))
        print()

    # Round 393: every figure to the left of this one counts REPORTS.
    # None of them answers "does the pooled evidence put this description
    # above a coin flip", and when that question was first asked, 28 of the
    # 46 came back UNDECIDED at 95% -- including 19 skills reading
    # "full recall" off 3 probes in a single run, where Wilson on 3/3 is
    # [0.44, 1.00]. The pooled verdict is the last clause because it is the
    # one that says how much is actually known.
    pooled = trigger_eval.pooled_rows(catalog, cases, reports)
    n_works, n_und, n_broken, n_single = pooled_summary(pooled)
    print("case-coverage: %d skill(s), %d case(s) (%d negative); %d probed "
          "under the description on disk, %d of those on every positive "
          "case with full recall; %d replicated (>=2 same-description "
          "reports), %d of %d cross-report case verdicts DISAGREE; "
          "POOLED 95%%: %d WORKS (%d of them on a single run), %d UNDECIDED, "
          "%d REFUTED; %d error(s), %d warning(s); "
          "coverage %d/%d skills, %d/%d replicated"
          % (len(rows), len(cases), sum(1 for c in cases if not c["expect"]),
             n_probed, n_clean, n_rep, n_dis, n_comp,
             n_works, n_single, n_und, n_broken, n_err, n_warn,
             n_probed, len(rows), n_rep, len(rows)))
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())

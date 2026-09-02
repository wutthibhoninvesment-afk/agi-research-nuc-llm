---
name: deadline-names-its-executor
description: Use when a date is about to be quoted as a deadline, expiry, retention window, TTL, rotation, or "we lose X on DATE" — and the thing that actually performs the deletion, rotation or expiry is a scheduled job on a machine that is not always running. Symptoms: a forecast whose output is a timestamp with no field naming who executes it; a retention/TTL number treated as elapsed wall-clock; a cron/systemd-timer/k8s-CronJob consequence modelled as a calendar; a downstream round or ticket "gives up" on data because a computed date has passed; a config setting that decides catch-up-vs-skip (Persistent=, startingDeadlineSeconds, misfire policy) that nobody has read. Covers naming the executor, deriving its missed-fire behaviour from its own run history instead of a config you do not have, joining the forecast to an availability log the repo is already keeping, and failing closed to "unknown" when the subject never ran the experiment.
---

# A deadline is an event, and events need someone to run them

`"we lose sa23 on 2026-09-03T00:07:00Z"` reads like physics. It is not. It is
shorthand for *"a unit named `sysstat-summary.service` will delete it, if
something starts that unit, at a moment when the machine is awake."* Three
conditions, of which the date is the least interesting and the only one that
got written down.

The error is one-directional and that is what makes it expensive. A model that
ignores executor availability **over-reports loss**: it tells the next reader
the data is gone, so the next reader does not go and look. Data that is still
sitting on disk gets abandoned on the strength of a date.

## The instance this came from

Round 448 of this program. `state/research-state.md` had carried
`2026-09-03T00:07:00Z` as a data-loss deadline for four rounds. The target
machine had been unreachable for three consecutive rounds — a fact recorded in
a *different* file in the *same repository*, by an instrument this program
built for exactly that purpose. Joining the two showed the box had slept
through the sweep, so four files the note had written off were still on disk,
with a real ~17 h capture window still open.

The two instruments — a retention forecaster and a reachability log — had
lived side by side for eighteen rounds and had never been introduced.

## Trigger conditions

- A **date** is about to be published, quoted, or carried forward as a
  deadline, expiry, cutoff, or "last chance to capture".
- A retention/TTL/rotation number (`HISTORY=7`, `ttl: 30d`, `keep 14 days`) is
  being read as **elapsed time** rather than as a predicate some job evaluates
  when it runs.
- The enforcing job is a **cron entry, systemd timer, k8s CronJob, Windows
  scheduled task, or an application's own sweeper thread** — anything that can
  simply not run.
- The subject machine, node, or cluster is **known to be intermittent**:
  laptops, lab boxes, spot instances, anything you have ever failed to SSH to.
- Someone is about to **skip work** because a computed deadline has passed
  ("that data is gone, no point capturing it").
- A forecast's output JSON has a timestamp field and **no field naming the
  actor or the condition**.
- You are reaching for a config setting you cannot read (the box is down, the
  file is not in the capture) to decide whether a missed run is **retried or
  dropped**.

## Steps

1. **Name the executor, in writing, before anything else.** Not "the file
   expires" — *"unit U, started by timer T, on host H"*. If you cannot name all
   three, the deadline is a guess and should be labelled one. Grep the config
   the sweep actually reads rather than the documentation:

   ```bash
   grep -rn "HISTORY\|COMPRESSAFTER\|mtime" /etc/sysstat/sysstat /usr/lib/sysstat/sa2
   systemctl list-timers --all --no-pager | grep -i <unit>
   ```

2. **Find the catch-up bit.** Every scheduler has one setting deciding whether
   a run missed while the host was down is *executed late* or *silently
   dropped*. It is the single bit that decides whether an outage **saves** your
   data or merely **delays its death by hours**. Know its name for your
   scheduler before you go looking:

   | scheduler | setting | missed run is… |
   |---|---|---|
   | systemd timer | `Persistent=` | re-run at next boot if true |
   | k8s CronJob | `startingDeadlineSeconds` | run late if inside the window |
   | Quartz / Spring | misfire instruction | policy-dependent |
   | classic cron | *(none)* | always dropped |
   | anacron | *(always)* | always caught up |

3. **If you cannot read it, DERIVE it from the executor's own history.** This
   is the step that turns a blocked investigation into a measurement. You do
   not need the config; you need a log covering a window in which the host was
   down across a scheduled fire.

   ```bash
   # every instant the unit actually started, unfiltered and NOT boot-scoped
   journalctl -o short-iso --no-pager _PID=1 | grep "Starting <unit>"
   # the down windows
   journalctl --list-boots --no-pager
   ```

   Then: enumerate the *scheduled* fires over the log's own window, subtract
   the observed ones, and for each miss ask whether a run appears shortly
   after the host next came back. **A miss with no catch-up is one trial.**
   Two agreeing trials is a verdict.

4. **Use the log's window, not a window you chose.** Scope the scheduled-fire
   lattice to the first and last timestamp the log actually covers, or you will
   count fires the log could never have witnessed as misses.

5. **Anchor the lattice on a measured fire, never on a hardcoded time.** Derive
   the period and phase from one observed or announced run. A box whose timer
   moves must not silently keep the old answer.

6. **Match observed to scheduled with a tolerance, and check the residual.**
   Start latency is real (1–21 s in the founding instance; `RandomizedDelaySec`
   widens it). Then assert that **no observed run went unmatched** — an
   unmatched run means your anchor or period is wrong, and it is the only cheap
   check that catches it.

7. **Fail closed to `"unknown"`, not to the convenient answer.** If no fire was
   missed inside a down window, the subject never ran the experiment and you
   have no evidence either way. Returning `False` there is inventing evidence,
   and it will be inventing it in whichever direction you were already hoping
   for.

8. **Join the forecast to the availability record you are ALREADY keeping.**
   Before writing a new probe, grep the repo for the log that answers "was the
   host up at time T" — reachability logs, uptime checks, monitoring exports,
   CI heartbeats. Feed the confirmed-down fires in as *skipped*, and have the
   forecast walk the lattice past them.

9. **Keep the old answer reachable.** The no-skipped-fires case must reproduce
   every number the model produced before, byte for byte, and there should be a
   test saying so. Otherwise nobody can tell your correction from a regression.

10. **Publish the conditionality in the artefact, not in a comment.** Emit
    `requested_next_run` alongside the effective one, the list of fires walked
    past, and an explicit `..._conditional: true` with the condition spelled
    out. A caveat that lives only in a source comment is a caveat that will be
    quoted without.

11. **Re-derive before acting on a carried date.** A deadline copied forward
    across rounds or tickets is exactly the artefact this skill exists for;
    the copy loses the conditions first.

## Pitfalls

- **A boot-scoped log cannot support an absence argument.** `journalctl -b`
  makes "no line" mean "not captured", not "did not run". Every conclusion
  here rests on the log being unfiltered across the window; check that first.
- **A catch-up run is not at its scheduled time.** The founding instance's
  first implementation drew its evidence from the fires *matched* to a
  schedule — which by construction excludes the one event the verdict exists
  to detect. It could only ever return "not persistent", the answer that
  happened to be right. Draw catch-up evidence from **all** observed runs.
  A negative-control test (a synthetic caught-up fire that must read as
  persistent) is what catches this; a verdict that agrees with you is the kind
  you do not check.
- **"Down" and "did not run" are different claims with different evidence.**
  The absence of the run is what proves the sweep did not happen; the down
  window only explains *why*. Do not make the stronger claim depend on the
  weaker one.
- **An outage does not save files, it batches them.** The next fire the host
  is awake for deletes everything overdue at once, so the *count* lost on that
  fire grows. Report the new set, not just the new date.
- **Two deadlines from one model do not move together.** In the founding
  instance one skipped fire moved the next-loss date by a day and left the
  far deadline untouched. Quoting them as a pair implies a coupling that is
  not there.
- **Half a window is not a window.** `--down-since` with no `--down-until`
  makes the answer depend on when the command was run. Require both, or error.
- **Truncation and skipping compound.** `find -mtime +N` truncates to whole
  days and buys up to 24 h on its own; a missed fire buys another period. Both
  are real, both are in the same direction, and modelling only one still
  under-reports survival.

## Verification

Run against this repo, which holds the founding instance's data:

```bash
# 1. the executor's own history: scheduled vs observed, and the catch-up verdict
.venv/bin/python3 nuc/capture_manifest.py sweeps \
    --capture state/nuc-capture-r424 --anchor 2026-09-02T00:07:00Z --strict
#    -> n_scheduled 9, n_ran 7, n_missed 2, persistence.persistent false,
#       exit 0 (a KNOWN verdict; --strict exits 1 only on "unknown")

# 2. the calendar answer, and the outage-aware one, side by side
.venv/bin/python3 nuc/capture_manifest.py retention \
    --capture state/nuc-capture-r424 --now 2026-09-01T08:18:35Z \
    --next-run 2026-09-02T00:07:00Z --history 7 --strict
#    -> next_run 2026-09-02T00:07:00Z, 4 doomed, exit 1
.venv/bin/python3 nuc/capture_manifest.py retention \
    --capture state/nuc-capture-r424 --now 2026-09-01T08:18:35Z \
    --next-run 2026-09-02T00:07:00Z --history 7 \
    --down-since 2026-09-01T18:27:56Z --down-until 2026-09-02T06:32:13Z --strict
#    -> requested 2026-09-02T00:07:00Z, effective 2026-09-03T00:07:00Z,
#       fires_passed_over ["2026-09-02T00:07:00Z"], 6 doomed, exit 1

# 3. the tests, including step 7's fail-closed case and step 9's old-answer pin
.venv/bin/python3 -m pytest nuc/tests/test_capture_manifest.py -q
#    -> 53 passed
```

A correct application of this skill produces, at minimum: a named executor, a
catch-up verdict that can come back `"unknown"`, and a forecast field saying
which fires were walked past.

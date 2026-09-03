---
name: scheduled-output-as-receipt
description: Use when you need to know whether a machine, service or job was alive at a past instant and your only witnesses are your own polls. Symptoms - you are bracketing an outage from probes taken hours apart; a report says "unexplained gap"; you are about to conclude a period is unknowable because nobody was watching. A periodic job's OUTPUT FILE is a RECEIPT stamped at the instant it ran, so the file SET is a timeline of which runs happened - readable retroactively, at no cost, for instants you never probed. Establishes downtime only with a catch-up check (systemd Persistent=, cron anacron) and a retention argument that says why a missing receipt is not just rotation. NOT for reading a log's CONTENTS for uptime (that needs the file to exist), and NOT a substitute for a live probe of the present.
---

# The absence of a file is a timestamp

Every box worth monitoring already runs something on a timer — `sysstat`,
`logrotate`, `mandb`, a nightly backup, a report generator. Each of those
writes a file **at the moment it runs** and names it after the period it
covers. That file is not primarily data. It is a **receipt**: proof that at
instant T, a scheduler fired and a process ran, which is proof the machine
was alive at T.

The receipts you *don't* have are the interesting ones.

This matters because the natural instrument — polling the box yourself — has
a cadence, and the cadence has holes. In the case this skill came from
(round 478), the polls ran roughly hourly during working hours and the
scheduled job fired at 00:07. **Zero of ten fire instants were bracketed by
a poll within an hour**; the tightest bracket was 2 h 27 m and the loosest
7 h 43 m. The receipts answered all ten exactly, and they had been sitting in
`ls -l` output the program had copied four times without opening.

## Trigger conditions

- You are bracketing an outage from your own probe log and the bracket is
  hours wide.
- A tool reports `unexplained_gap`, `coverage_edge`, `unknown` or
  `record_coverage: none` for a period, and you are about to accept it.
- You want to know about an instant *before you started watching*.
- Your uptime evidence and your incident narrative come from the same
  source, so agreement between them proves nothing.
- A directory contains files whose names encode a period (`sar23`,
  `access.log.4.gz`, `backup-2026-08-30.tar`, `report-W35.csv`) and you have
  only ever read their contents.
- Someone says "the box was probably asleep" / "an operator probably
  restarted it" without a second instrument.

**NOT for:** reading a log's *contents* to reconstruct uptime — that is a
different and complementary technique, and it is blind to a period whose file
was never created at all. **NOT** a substitute for probing the present.

## Steps

1. **List the directory, don't just read the files.** `ls -l` on the
   scheduler's output directory, captured verbatim into your evidence bundle.
   Names *and* mtimes: the name says which period, the mtime says when the
   run happened. Keep this even in a capture you take for another reason —
   it is 200 bytes and it is the whole instrument.

2. **Separate the receipts from the data.** Two files per period that look
   alike are usually not alike. In `sysstat`, `saNN` is written *throughout*
   day NN by the collector; `sarNN` is written *once*, at 00:07 on day NN+1,
   by the summary job that renders it. Only the second is a receipt. Getting
   this backwards inverts every verdict.

3. **Establish the schedule FROM the receipts, never from a config you
   assume.** Take the modal time-of-day over the receipt mtimes. Break ties
   deterministically and report how many receipts voted for the mode — a mode
   with 1 of 2 votes is not a schedule. Hardcoding the time you read in a
   unit file means a box whose timer moved is scored against a lattice it
   does not use.

4. **Check for catch-up, and READ it rather than infer it.** This is the step
   that decides whether the technique works at all.
   - systemd: `systemctl show <unit>.timer -p Persistent -p OnCalendar`.
     `Persistent=yes` means a missed fire runs at the next boot — the receipt
     appears late and a missing receipt no longer means downtime.
   - cron: is `anacron` installed and does it own this job?
   - Anything with a `--catch-up`, `misfire_grace_time`, or a queue.

   `Persistent=no` is what makes "no receipt" mean "was not running". If it
   is `yes`, stop: you have a *delay* detector, not an availability witness.

5. **Write the retention argument, or you have nothing.** A missing receipt
   could always just have been deleted. You must be able to say why it was
   not. Compare the receipt's lifetime to its data file's under the *actual*
   deletion rule:

   > `sarNN` is stamped 17 min *after* `saNN`, and the sweep is
   > `find -mtime +7` which truncates age to whole days. At any fire instant,
   > `saNN`'s age is an integer plus 0:17 and `sarNN`'s is that integer
   > exactly — both floor to the same number, so **the pair always shares a
   > verdict.** If the data file is still there, the receipt would be too.

   Read the deletion code (`/usr/lib/sysstat/sa2`, the logrotate stanza), do
   not assume `mtime` semantics — `-mtime +7` is *not* "older than 7 days".

6. **Refuse the overdetermined cases explicitly.** If the *data* file is also
   missing, the receipt's absence has two possible causes and you cannot pick
   one. Emit `no_day_file`, not a verdict. Likewise the newest period, whose
   run has not happened yet, and any period whose file has been compressed
   (the mtime is now the compression's, so step 5's argument collapses).

7. **Add a settle window.** A run that fired *just now* may not have finished
   writing. Without this, a capture taken a second after the scheduled time
   reports an outage that did not happen. One scheduler interval is a fine
   default. Pin both edges with tests — this exact boundary survived a first
   mutation pass in round 478, i.e. nothing tested it.

8. **Cross-check against an instrument that shares no input.** Filesystem
   mtimes vs `journalctl --list-boots`; receipts vs a cloud provider's
   instance-state history. Report the agreement rate and name every
   disagreement individually — do not average them. Round 478 got 10 of 10
   with 0 disagreements, which is what promoted "the job did not run" to "the
   machine was down".

9. **Re-run it over evidence you already have.** This is where the technique
   pays for itself: old captures contain old `ls -l` output. Round 478's
   reader, applied to bundles taken on 08-31 and 09-01, recovered verdicts
   nobody had asked for at the time. Assert that successive captures are
   **nested** — a later one may add misses and lose old periods to rotation,
   but must never contradict an earlier one still in range. A contradiction
   falsifies your step-5 argument directly.

10. **Persist the verdicts, because the receipts expire.** The evidence has a
    retention horizon (7 days here). Append each run's verdicts to a durable
    ledger, or the timeline silently truncates to whatever is on disk today.

## Pitfalls

- **Assuming the catch-up setting instead of reading it.** Round 448 inferred
  `Persistent=no` from missed fires and was right; nobody read the unit for 30
  rounds. Had it been `yes`, every retention forecast built on it was unsound
  *and* eight files the program was about to rescue would already have been
  deleted. The inference was correct and the exposure was total.
- **Reading the data file as the receipt.** See step 2.
- **A missing receipt where the data file is missing too.** Overdetermined;
  see step 6.
- **Hardcoding the schedule.** See step 3.
- **Treating the newest period as a miss.** Every capture then ends in a
  fictional outage.
- **A prediction about a monotone quantity.** "The boot table gained exactly
  one row" was true and useless: the table was simultaneously being truncated
  from the other end, so the prediction could not fail. If a quantity can move
  in two directions, say which direction you are predicting.
- **Assuming the newest evidence bundle dominates the older ones.** It does
  not. Round 478's capture gained a day and *lost two*, because a second
  source (journald) had forgotten them. Analyse over the UNION of bundles and
  say so; a tool that silently takes "the capture" is choosing a window.

## Verification

Runnable in this repo. The numbers are round 478's and are the SHAPE of an
answer, not values to expect on another box.

```bash
# 1. the falsifiers, including the retention argument and the boundary
python3 -m pytest -q nuc/tests/test_summary_fossil.py          # 42 passed

# 2. the receipts, read as a timeline (step 1-3, 6, 7)
python3 nuc/summary_fossil.py fires \
    --capture state/nuc-capture-r478 --now 2026-09-03T17:13:00Z
#   fire_time_of_day 00:07 (7 of 7 receipts voted); 11 day files, 7 receipts;
#   counts {fire_ran: 7, fire_missed: 3, fire_pending: 1};
#   no_day_file_dates ["2026-09-02"]   <- refused, not guessed

# 3. the catch-up setting, READ (step 4)
grep -A3 '### TIMER_SHOW_sysstat-summary' \
    state/nuc-capture-r478/timer-units.txt        # Persistent=no

# 4. the independent cross-check; exits 1 on any disagreement (step 8)
python3 nuc/summary_fossil.py crosscheck \
    --capture state/nuc-capture-r478 --now 2026-09-03T17:13:00Z --strict
echo "rc=$?"          # rc=0; n_scored 8, n_agree 8, n_disagree 0
python3 nuc/summary_fossil.py crosscheck \
    --capture state/nuc-capture-r424 --now 2026-09-01T08:10:00Z --strict
echo "rc=$?"          # rc=0; n_scored 9, n_agree 9, n_disagree 0

# 5. the claim that this covers instants your own polls do not (the WHY)
python3 nuc/summary_fossil.py blindspot \
    --capture state/nuc-capture-r478 --now 2026-09-03T17:13:00Z
#   n_fires_bracketed_within_1h 0 of 10; min bracket 8824 s

# 6. retroactive + nested, over bundles that predate the reader (step 9)
python3 -m pytest -q nuc/tests/test_summary_fossil.py \
    -k "older_captures_already_held or nested_not_merely_similar"

# 7. the sweep: where else in your tree is a periodic job's output ignored?
ls -l /var/log/sysstat /var/backups 2>/dev/null
systemctl list-timers --all --no-pager
```

**How you know it worked.** You can name an instant nobody probed and say
whether the machine was alive at it, with a second instrument agreeing and a
written reason why the evidence's absence is not rotation. If you cannot
produce the step-5 argument, you have a heuristic, not a witness.

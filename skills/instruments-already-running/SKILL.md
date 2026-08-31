---
name: instruments-already-running
description: Use before instrumenting a system, modelling a quantity, or recording an event as unexplained — enumerate the samplers that have BEEN running and read their archives first. Symptoms: you are about to add a poller, a metric, or a probe to learn something; a past event has no explanation and the investigation only consulted the application log; a constant is "modelled" or "estimated" because the real value was never captured; someone says a number is "not recoverable". Covers finding the ambient recorders (sysstat/sar, journald, atop, filesystem mtimes, /proc high-water marks, package caches), reading a difference of two archived samples instead of inverting one live reading, and grading an attribution honestly when no per-process history exists.
---

# The measurement you want was probably already taken

Machines record themselves. Distributions ship samplers that have been writing
every ten minutes since boot, kernels keep high-water marks that nobody clears,
filesystems stamp every write, and package managers cache what they fetched.
None of it is in your application's log, so none of it gets read — and a whole
investigation gets spent either adding a new probe or writing "unexplained".

The asymmetry is severe. A new probe can only tell you about the future. The
archives can tell you about the event that already happened, which is usually
the one you care about.

## Trigger conditions

- You are about to **add** a poller, counter, or metric to answer a question
  about something that already occurred.
- An event is being written up as **unexplained**, and the evidence cited is
  the application log or one system log.
- A constant in your model is "estimated", "modelled", or "assumed", and the
  thing it estimates is something the machine could have recorded.
- Someone concludes a number is **"not recoverable"** — check *which* source
  that was true of. It is usually true of the one they looked in.
- You are about to run a live, priced, or risky probe (restart, load test,
  synthetic request) to obtain a number.
- A prior investigation asserted "**zero log entries in that window**".
  Verify it literally; it is very often "zero entries I filtered for".

**When NOT to use:** you need a quantity nothing samples (application-level
semantics — token counts, request identities, business events). Ambient
samplers see resources, not meaning. Adding the probe is then correct, and
this skill's only contribution is telling you so quickly.

## Steps

1. **Enumerate the samplers before forming a hypothesis.** On a Linux host:
   ```bash
   ls -la /var/log/sysstat/            # sar: every 10 min since install
   journalctl --list-boots             # per-boot journal, all units
   systemctl list-timers --all         # what fires, and when it last did
   ls -lt /var/cache /var/lib | head   # package/metadata caches, by mtime
   ```
   Write the list down. The one you have never read is the one that matters.

2. **Read the archives, not just the live values.** `sar` keeps one file per
   day of the month and rotates on the same day next month — **capture the
   file before it rotates or the evidence is gone.**
   ```bash
   sar -r -f /var/log/sysstat/saNN     # memory: kbmemused, kbcached, kbcommit
   sar -W -f /var/log/sysstat/saNN     # swap in/out rates
   sar -B -f /var/log/sysstat/saNN     # paging: pgpgin/s, pgscank/s, %vmeff
   sar -b -f /var/log/sysstat/saNN     # block I/O
   sar -n DEV -f /var/log/sysstat/saNN # network
   ```
   Read **more than one** view. An event invisible in one is often obvious in
   another: a heap balloon shows in `kbcommit` and not in `kbcached`; a page-
   cache flood shows in `pgpgin/s` and not in `kbcommit`. Consulting one view
   is how an event becomes "unexplained".

3. **Take a DIFFERENCE across the event, not an inversion of one reading.**
   Two archived samples on either side of the thing you care about give you
   its cost directly, with no baseline and no model. This is strictly better
   evidence than any single-point inversion, and it is free.

4. **Use non-log witnesses.** Filesystem mtimes date an event independently
   of whether anything logged it. `/proc/<pid>/status` `VmHWM` and `VmPeak`
   are high-water marks that survive the excursion that set them — a process
   whose `VmHWM` is 4x its `VmRSS` ballooned at some point, even if nothing
   recorded when.

5. **Re-read any "no entries in that window" claim literally.**
   ```bash
   journalctl --since '...' --until '...' --no-pager | wc -l
   journalctl --since '...' --until '...' --no-pager \
     | grep -v '<the noise you know about>'
   ```
   Filter the noise *after* counting, and print what is left rather than
   summarising it.

6. **Grade the attribution.** Ambient samplers give you coincidence in time,
   magnitude agreement, and mechanism — rarely proof, because almost nothing
   keeps per-process history. State which you have, and name the one read that
   would settle it. "Attributed, not proven, falsifier is X" is a finding.
   "Probably X" is not.

7. **Only now decide whether to add a probe**, and say what the archives could
   not tell you.

## Pitfalls

- **The bucket is labelled by its END.** `sar` rows are the *end* of the
  interval, so an event at 01:57:33 belongs to the row stamped 02:00:05. Get
  this wrong and you look for causes in the wrong ten minutes and find none.
- **`sar -B` `pgpgin/s`/`pgpgout/s` are kilobytes per second**, while
  `sar -W` `pswpout/s` is *pages* per second. Mixing the units silently
  rescales every conclusion by 4096.
- **A ratio against a near-zero idle baseline flags everything.** An idle box
  reads `pgpgin/s` 0.0–0.2; 4.17 is a 40x ratio and 2.5 MB. Require an
  absolute floor as well as a ratio, or a rounding error becomes a "surge".
- **A named event in the window is not a cost.** One box's hourly refresh
  timer fired 34 times and mattered exactly once. Attribute to the *bucket
  that moved*, and let the timer identity be corroboration, not evidence.
- **Randomized timers cannot be scheduled around.** When
  `RandomizedDelaySec` equals the `OnCalendar` period, the fire time is
  uniform over the whole period and there is no quiet window. The only
  available move is to record the fire history and reject contaminated arms
  after the fact.
- **Rotation is a deadline.** Note when each archive expires and capture it in
  the same session you discover you need it.

## Verification

```bash
# 1. the samplers exist and how far back they reach
ls -la /var/log/sysstat/ && journalctl --list-boots | tail -3

# 2. a persistent step, found from the archive alone
python3 -m nuc.perturbation steps --sar-r <captured sar -r output>

# 3. swap excursions in bytes, with the interval stated
python3 -m nuc.perturbation swap --sar-w <captured sar -W output>

# 4. whether a measurement window can be scheduled clean (on that box: no)
python3 -m nuc.perturbation guard --window-s 1800

# 5. the tests, whose fixtures are verbatim captured sar output
python3 -m pytest -q nuc/tests/test_perturbation.py
```

You are done when every non-quiet bucket is either attributed to a named event
with a stated grade, or explicitly carries the verdict `unattributed` — and
when any constant you were about to model has been checked against an archive
that might already contain it.

## Provenance

Round 394 on `pgain-nuc`. Round 388 had recorded a 67.7 MB swap-out as
"unexplained ... zero journald entries"; there were 21 entries in the window,
`sar -r` had recorded the +147 MB commitment step that caused it, and
`/var/cache/fwupd/metadata.xmlb`'s mtime dated it to the minute. The same
archives held the per-request fill curve that a previous round had called
"not recoverable" — true of the journal, false of `sar`.

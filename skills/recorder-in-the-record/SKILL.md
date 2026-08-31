---
name: recorder-in-the-record
description: Use when you adopt a pre-existing log, archive, or metric series as EVIDENCE — the recorder's own behaviour (its cadence, file rollover, retention edges, and its own presence in what it records) produces artifacts that are indistinguishable from the signal you are looking for. Symptoms: a gap in a sample series that you are about to call downtime; a correlation with the component that writes the data; events that cluster at times ending in :00; a "finding" that appears once per day, once per file, or once per restart; an attribution to whichever named thing happens to be nearest a bucket. Covers separating collection artifacts from phenomena, excluding the sampler from its own statistics, boundary attribution when a subject shares the sampler's cadence, and refusing to divide a shared bucket's cost.
---

# The recorder is in the record

Adopting an archive as an instrument is usually right — see
[`instruments-already-running`](../instruments-already-running/SKILL.md) for
finding it in the first place. The trap comes immediately after. The archive
was written by a program with a cadence, a file layout, a retention policy and
a process of its own, and every one of those leaves marks in the data that
have the same shape as the thing you are studying.

The failure is not noise. It is *systematic and plausible*: it lands in the
right units, at a believable magnitude, at a time that has a story. You will
have an explanation for it before you have checked whether the recorder alone
could have produced it.

## Trigger conditions

- You are treating a **sample series** (`sar`, RRD, Prometheus, a metrics
  table) as evidence about the past, especially about **absence** — downtime,
  silence, a missed event.
- You are about to call a **gap** in a series an outage, a stall, or a drop.
- Your finding **correlates with the component that writes the data** —
  the collector, the exporter, the logging agent, the CI job that emits the
  metric.
- Events in your result cluster at **round times** (`:00`, midnight, the top
  of the hour) or **once per file / per day / per restart**.
- You are attributing a measured cost to whichever **named event is nearest**
  a bucket, without checking how many other named events are in it.
- Data comes from a **rotating** store and your window touches its edge.

**When NOT to use:** the archive is a complete event log with per-event
identity (an audit log, an append-only ledger). There the record is of
discrete facts, not of samples, and absence genuinely means absence. This
skill is about *sampled* and *rotated* data.

## Steps

1. **Write down the recorder's mechanics before looking at any result.**
   Four questions, all answerable without touching your data:
   - What is its **cadence**, and what defines the boundary of a bucket?
   - What is its **file/segment layout**, and what happens at a rollover?
   - What is its **retention**, and where are the edges of coverage?
   - Does the recorder **appear in its own output**?

   ```bash
   systemctl list-timers --all          # cadence of every periodic writer
   ls -la /var/log/sysstat/             # segment layout and retention
   journalctl --list-boots              # segment boundaries of another store
   ```

2. **Classify every gap by cause before by consequence.** Give absence its own
   vocabulary, disjoint from your findings' vocabulary. A useful minimum:
   `coverage_edge` (retention, not an event), `rollover` (a segment boundary),
   `restart` (the recorder or its host cycled), `unexplained` (a hole you
   genuinely cannot name). **Never let `unexplained` default into your signal
   class.** A suspended host and a stopped collector make an identical hole;
   naming it "downtime" invents a distinction you do not have.

3. **Test each gap class against the recorder's layout, and require the ratio
   to be decisive.** If a candidate artifact is real, it appears at *every*
   instance of the structural feature, not most. One box's series had seven
   one-sample holes; all seven fell across a UTC midnight, at 7 of the 7 day
   boundaries the capture could observe. 7/7 is a rule. 5/7 would have been a
   coincidence with a story.

4. **Exclude the recorder from its own statistics, and say so in the output.**
   The collector runs in every bucket it writes, so it co-occurs with every
   event by construction. Leaving it in makes a base rate a statement about
   the instrument. Exclude it *by name*, as a named constant with the reason
   attached — not with a silent filter.

5. **Fix boundary attribution when subjects share the recorder's cadence.**
   A sample at instant *T* summarises `(T-interval, T]`. A subject that
   *starts* at *T* has done nothing yet at *T*, so its cost belongs to the
   next bucket. This is not a corner case when your subjects are scheduled
   jobs: schedulers and collectors both fire on round seconds, so they collide
   routinely. Add an explicit small slack and pin it with a test in both
   directions — one that moves a boundary case forward, one that proves the
   slack does not reach a genuine bucket boundary.

6. **Refuse to divide a shared bucket.** A bucket's cost is a property of the
   *bucket*. When *k* subjects fall in one, all *k* carry the same figure and
   the count *k* travels with it; only *k*=1 licenses "subject X cost this".
   Aggregate over **distinct buckets**, never over subjects — summing
   per-subject figures triple-counts, and the total is the number people
   quote.

7. **Re-derive any published claim that this changes.** An attribution made
   before step 6 was made without knowing how many candidates shared the
   bucket. Check it explicitly rather than assuming it survives.

## Pitfalls

- **The most confident attribution is the one with the fewest competitors
  examined.** "It was `apt`" survived two rounds; the bucket turned out to
  hold five named starts, one of which was independently known to be capable
  of the same cost alone.
- **A per-day or per-file finding is a layout finding until proven otherwise.**
  Anything with a period equal to the archive's segment period should be
  assumed to be the segment boundary.
- **A rollover artifact is not a loss of witness.** The sample was taken; only
  its *display* is missing. Treating it as a break fragments every segment and
  understates your coverage — which then looks like a real reduction in what
  you can claim.
- **Floor division on a drifting cadence gives two answers for one event.**
  Real stamps drift (1198 s vs 1200 s for the same one-slot hole), so compute
  missed slots with rounding, not `//`.
- **Retention edges are deadlines, not gaps.** Capture the segment in the
  session you discover you need it.
- **Emitting a coverage figure changes what a number means, so ship the basis
  with it.** A coverage-conditioned total FALLS when you add a witness. Two
  runs of the same command over the same log are comparable only if the basis
  block is identical — print the basis, do not rename the field, because
  published figures already carry the old name.

## Verification

```bash
# 1. gaps are classified by cause, and none defaults into the signal class
python3 -m nuc.sysstat_archive witness --capture <capture> --gaps-only \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); \
      print({g["kind"] for g in d["gaps"]})'

# 2. the artifact class is decisive, not merely common
python3 -m pytest -q nuc/tests/test_sysstat_archive.py \
  -k "rollover or midnight or missed_slots"

# 3. the recorder is excluded by name, and can be put back deliberately
python3 -m nuc.perturbation ledger --sar-w <sar -W> --journal <journal> \
  --date YYYY-MM-DD | grep -E '"excluded_units"|"boundary_slack_s"'

# 4. shared buckets are counted once, not once per subject
python3 -m pytest -q nuc/tests/test_perturbation.py \
  -k "shared_bucket or distinct_buckets or boundary"

# 5. a coverage-conditioned total states its basis
python3 nuc/reachability_check.py continuity \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["unobserved_basis"]["note"])'
```

You are done when every gap in the series carries a cause-class rather than a
consequence-class; when the recorder is absent from its own base rates by a
named, documented exclusion; when no aggregate sums over subjects that share a
bucket; and when each earlier attribution the analysis touches has been
re-derived rather than inherited.

## Provenance

Round 400 on `pgain-nuc`, applying `instruments-already-running` to nine days
of `sar` archives. The archive was the right instrument and it closed 98.28 h
of previously-unobserved time. It also produced three artifacts in one round,
each of which had a plausible reading as a finding: 7 of 12 "gaps" were
sysstat's own file rollover; `sysstat-collect` appeared in 100 % of costly
buckets because it *writes* them, and dominated the denominator 218 fires to
60; and `apt-daily`, firing at 03:50:05 on the same cadence as the 03:50:05
sample, was credited to a zero bucket while the 218 MB it plausibly caused was
attributed to a process that started four seconds later. Correcting the third
also showed that the 218 MB bucket holds **five** named starts, so the "it was
apt" attribution two prior rounds had published is not sole-attributable at
all — the only sole-attributable swap event in that boot is a firmware
metadata refresh.

---
name: newest-snapshot-is-not-the-record
description: Use when an analysis reads from a SNAPSHOT of a rotating or expiring source (capture directory, log tarball, journalctl dump, metrics export, database backup, CI artefact) and someone is about to pick ONE snapshot to compute from. Symptoms; every published number names the same snapshot while newer ones sit unread beside it; "use the latest capture" as an unexamined default; a stated limitation of the form "the record ends when we copied it"; a retention rule (logrotate, find -mtime, journald vacuum, S3 lifecycle) that deletes the FRONT while each snapshot only adds to the BACK; two snapshots of one append-only file diffed whole and declared to disagree. The move; union every snapshot keyed by (source-object, period), verify agreement where they overlap instead of picking a winner, name the unusable inputs, and re-derive the old numbers on the union before trusting either. Covers multiset union of log lines and why a trailing summary row is not a conflict.
---

# The newest snapshot is not the best record. Often it is the worst.

A snapshot of a rotating source captures a WINDOW, not a history. If the
source expires its oldest data on a schedule and your snapshots are taken
irregularly, then each snapshot

* **gains** whatever accumulated at the back since the last one, and
* **loses** whatever the retention rule took off the front.

So "newest" is a claim about the back edge only, and the record you actually
want is the **union** — which usually exists already, sitting in your repo,
because somebody was diligent enough to keep the old snapshots.

```
The iron law:  a snapshot is a window. Pick the union, not the newest,
               and prove they agree where they overlap.
```

## The measured instance (round 490)

Nine capture directories in one repo. Every published window-level number in
an entire research track was computed from `nuc-capture-r424` — the third
oldest. Two newer captures had been committed for days.

| capture | day-files | paired days | poolable buckets | journal records |
|---|---:|---:|---:|---:|
| `r424` | 10 | 10 | 991 | 1652 |
| `r478` | 11 | 9 | 896 | 1344 |
| `r484` **(newest)** | **8** | **8** | **661** | 1367 |
| **union** | **12** | **12** | **1145** | **1938** |

The newest capture was the *smallest* record, because a `find -mtime +7`
sweep runs nightly and deletes four days the older captures still hold. A
round reaching for "the latest capture" would have got 8 days where 12 were
available, and would have believed a published limitation — *"the record ends
where we copied it"* — that had stopped being true two snapshots ago.

## When this triggers

* Any module that takes a `--capture DIR`, `--snapshot`, `--dump`, `--export`
  or `--backup` argument and is called with exactly one of them.
* A written limitation of the form "our data ends at <the day we copied it>".
* A directory of dated artefacts where `ls | tail -1` is the habitual input.
* A source with a retention rule: `logrotate`, `find -mtime`, journald
  `SystemMaxUse`, `sar`/`sysstat` `HISTORY`, S3 lifecycle, Prometheus
  retention, a paginated API that only serves the last N days.

## Steps

1. **Inventory before choosing.** For every snapshot, list the (object,
   period) pairs it holds — not its size, not its date. The question is
   *which periods does this one cover*, and the answer is usually not
   monotone in snapshot age.

   ```
   for c in <snapshots>; do echo "== $c"; <list the objects and their dates>; done
   ```

2. **Key the union on (object, period), never on the file name.** File names
   rotate and get reused (`sa01` is the 1st of *some* month). Read the period
   out of the object's own header/banner and cross-check it against the name;
   a mismatch is a finding, not a tie-break.

3. **Union at the level the data is written at.** For an append-only table
   that is the timestamped ROW. For a log it is the LINE — and it is a
   **multiset**: two identical lines in one file are two real events at a
   resolution too coarse to tell them apart, and set-dedup deletes one.
   Verify losslessness by re-derivation, not assertion: for every snapshot
   and every line, does the union carry at least as many copies?

4. **Expect a chain of prefixes, and report it when you do not get one.** Two
   reads of one append-only object must agree wherever they overlap, so the
   normal outcome is that some snapshot is already a superset — emit its
   bytes verbatim and touch nothing. Only merge when no snapshot is a
   superset, and say in the report that you merged.

5. **Do not diff whole files.** Summary rows are computed over the rows
   present: a `sar` `Average:`, a `wc -l` footer, a checksum trailer, an
   `END OF FILE (N records)` line. Two honest reads of one growing file
   differ there and agree everywhere that matters. Compare per key.

6. **Name the unusable inputs in the report.** A snapshot that contributes
   nothing must appear saying so. Otherwise a `glob` that silently matches
   fewer directories looks exactly like a clean run.

7. **Price the union against the best single snapshot, and against the
   half-job.** Report `gain_over_best_single`. Also report what unioning only
   *part* of the record buys — in the measured instance, unioning the tables
   but keeping the newest log left two recovered days unusable, because the
   analysis needs both halves to line up.

8. **Re-derive the old numbers on the union before publishing new ones.** The
   union must reproduce every conclusion the old snapshot supported on the
   periods they share. In the measured instance the costly-bucket sets were
   identical on all 10 shared days — which is what made the two new days
   trustworthy.

9. **Say what the extra data actually did.** If the added periods are all
   null, every coefficient the union moved, it moved by adding null points,
   and the direction of each shift is predictable from that alone. Report it
   as arithmetic, not as evidence.

## Pitfalls

* **"Newest is freshest" is an intuition about append-only sources.** It is
  false for anything with retention, which is nearly everything operational.
* **Set-dedup on log lines destroys events.** Same second, same message, two
  occurrences. Use multiplicity.
* **Merging silently picks a winner.** If two snapshots disagree about the
  same key, that is an instrument or a snapshot being wrong. Report the
  conflict; never average, never take the later one "because it is newer".
* **Unioning half the record.** Two halves that must be joined on a period
  (a table and the log that explains it) have to be unioned together, or the
  recovered periods are dropped by the join and the gain evaporates.
* **A missing snapshot is not a quiet period.** Distinguish "no data because
  the source had none" from "no data because this snapshot did not capture
  it"; the second is a hole in the instrument and belongs in the report.
* **Do not rebuild the union from a fresh clone and assume it matches.** Pin
  the built artefact with a test that re-runs the builder and compares, or
  the numbers stop being reproducible the first time the builder drifts.

## Verification

The union must (a) find conflicts when they exist, (b) never invent one out
of a trailing summary row, (c) preserve line multiplicity, and (d) beat the
best single snapshot or say it did not.

```sh
python3 -m pytest nuc/tests/test_record_union.py -q
```

Expected: all tests pass, including
`test_the_average_line_alone_never_makes_two_captures_disagree`,
`test_a_line_repeated_inside_one_capture_survives_the_union`,
`test_the_newest_capture_is_not_the_best_one` and
`test_two_captures_that_disagree_about_a_row_report_a_conflict`.

On the live corpus, the union and its price:

```sh
python3 nuc/record_union.py sar   --captures 'state/nuc-capture-r*' --strict
python3 nuc/record_union.py frame --captures 'state/nuc-capture-r*' --strict
```

Expected: `n_conflicts` 0, `n_dates` 12, five captures named unusable, and
`gain_over_best_single` > 0 (exit 1 if the union buys nothing, which is the
answer that should stop you shipping it).

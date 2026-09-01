---
name: correction-validated-where-you-looked
description: Use when a correction, adjustment, calibration constant, scale factor, patch, or workaround has been confirmed against the data you happen to have loaded, and is about to be applied, published, or carried forward as settled. Symptoms - a divisor or offset that "restores the expected ceiling" on the sample in hand; a fix validated on the two files, one shard, latest boot, current branch, or reproducing test case somebody already had open; a correction whose evidence is a mechanism plus one confirming dataset; a checker that reports "ceiling restored" or "identity holds" after quietly filtering rows; a constant carried across rounds with the words "confirmed" and no restatement of the subset it was confirmed on. Covers re-running the check on every partition you did not look at, counting what the checker's own filters discard, and distinguishing a correction that is wrong from one that is real but incomplete.
---

# A correction is only confirmed on the partition you ran it against

Someone found a defect in a measurement, worked out the mechanism, applied the
fix, and watched the impossible numbers become possible. That is a strong chain
of evidence and it is usually *right*. It is also, almost always, evidence
about one slice of the data — the slice that was already open when the anomaly
was noticed.

The failure is not "the correction is wrong". The failure is **"the correction
is complete"**, carried forward as a settled constant, when the residual is
sitting in the partitions nobody re-ran.

## The instance this came from

Rounds 418-424 of this program chased a `%vmeff` column reporting reclaim
efficiencies above 100 % — impossible, since you cannot steal a page you did
not scan. The diagnosis was excellent:

* Halving `pgsteal` put every violating bucket at or under the ceiling, with
  the maximum landing on **exactly 100.000** and five of seven within 1 % —
  a ceiling that sharp is a double count, not a noisy undercount.
* The mechanism was then read out of the collector *binary*: `sadc` carries
  `pgscan_kswapd` and `pgscan_direct` as full field names and `pgsteal_` as a
  bare **prefix**, which on this kernel matches five fields forming two
  complete partitions of the same events. Numerator doubled, denominator not.
* `RECLAIM_STEAL_DIVISOR = 2` was set, `corrected_*` shipped beside the raw
  columns, and the finding was carried forward as CONFIRMED.

Every step of that is correct. The data it was confirmed on was **two of ten**
banked day-files — the two this track had ever opened. Round 430 ran the same
check over all ten:

| | reported | after ÷2 |
|---|---|---|
| buckets over the 100 % ceiling | 66 of 87 | **8** |
| buckets that stole pages with **zero** scanned | — | **21** |
| worst residual | 6107 % | **3053 %** |

`ceiling_restored: False`. And the four day-files on which it *does* hold are
sa28-sa31 — the recent ones, the ones in the window anyone had looked at.

The correction was real and **incomplete**. The same banked evidence file, one
section further down, held the other half: the kernel exports
`pgscan_khugepaged` and `sadc` does not read it, while `pgsteal_` collects
`pgsteal_khugepaged`. So the reported ratio is `2T / (S − S_khuge)`, not
`2T / S`. The residual is therefore **unbounded** rather than a second constant
factor, and **undefined** when that path does all the work — which is exactly
the 21 scan-free buckets.

Worse, the checking function could not have caught it. Its first line was

```python
evs = [e for e in events if (e.scan_kswapd_s + e.scan_direct_s) > 0]
```

which drops precisely the buckets that violate the theorem most sharply, with
no count. `ceiling_restored: True` was computed on a set the counter-examples
had been removed from.

## When to use — trigger conditions

* A scale factor, offset, divisor or calibration constant is about to be
  promoted from hypothesis to shipped constant.
* A fix "restores" an invariant, ceiling, floor, identity, or conservation law
  on the sample in hand.
* A correction was confirmed by a mechanism (source, binary, spec, changelog)
  *and* one dataset, and the mechanism is being treated as covering both.
* A carried-forward note says a constant is CONFIRMED and does not restate the
  subset it was confirmed on.
* A checker prints a boolean verdict about an invariant and has any filter,
  guard, `dropna`, `if x > 0`, or try/except between its input and its verdict.
* You are about to write "this is settled" about a numeric adjustment.

Do **not** use it to re-litigate a correction that already publishes its
scope. "Validated on shards 1-3 of 40; shards 4-40 unrun" is the output this
skill is asking for, not a target.

## Steps

1. **Name the partition the correction was confirmed on, in the same sentence
   as the correction.** Days, shards, hosts, boots, versions, branches, test
   cases. If you cannot name it, you do not know it, and that is the finding.

2. **Enumerate the partitions you did NOT run.** Derive the list from the
   artefact's own inventory — a directory listing, a manifest, the config the
   job reads — never from memory. This is
   `skills/elimination-needs-its-frame` applied to a correction.

3. **Re-run the check per partition and print a row each.** Not a pooled
   verdict: a pooled `False` tells you it failed, a per-partition table tells
   you *where*, and "the passing partitions are exactly the recent ones" is
   the shape that reveals a sampling artefact rather than a random one.

4. **Count what the checker's own filters discard, and report the count.** Any
   guard between input and verdict is a candidate for hiding the
   counter-examples. Make the discarded count a field in the output, and make
   a non-zero count *block* the positive verdict rather than being a footnote.
   The rule: a function that tests an invariant may not silently drop rows
   that violate it.

5. **Classify the residual: wrong, or incomplete?** Ask whether the residual
   is (a) the same size as the effect — the correction is wrong; (b) a second
   constant factor — there are two defects of the same kind; (c) unbounded or
   undefined — a term is *missing from the model*, not mis-scaled. Case (c) is
   the one that gets misread as noise.

6. **Look for the other half in the evidence you already banked.** A capture
   taken to prove one half of a mechanism very often contains the other half.
   Round 424 read `SADC_VMSTAT_LITERALS` and stopped; the omitted scan field
   was in `PROC_VMSTAT_RECLAIM_FIELDS`, in the same file, seven lines below.

7. **Publish the correction as a BOUND when it is one.** If the correction is
   real but incomplete, `corrected_*` is an upper (or lower) bound on the true
   value, not the true value. Say which, and keep the raw column beside it so
   a reader has to name which one they are quoting.

8. **Write the falsification command for the residual, and say whether it can
   run.** "Confirmed if X, refuted if Y" is worth nothing if the phenomenon is
   not currently occurring. Round 424 and round 430 both found the direct
   kernel test vacuous — every reclaim counter read 0 on a freshly rebooted
   box — so the evidence had to come from the collector binary instead. A test
   that needs the phenomenon to have recurred is only as available as the
   phenomenon.

## Pitfalls

- **Treating a sharp result as a complete one.** "Maximum lands on exactly
  100.000" is powerful evidence *for the mechanism* and none at all for its
  coverage. The sharper the confirmation, the more confident the overreach.
- **Confusing "the mechanism is confirmed" with "the correction is
  sufficient".** Reading the source or the binary settles *why*; it does not
  settle *whether that is the only why*.
- **Letting the recent partitions be the sample.** Whatever is loaded is
  usually the newest, and the newest is systematically quieter on an idle box,
  a fresh boot, a stable branch. The partitions that fail are the busy ones.
- **A divide-by-zero rendered as zero.** `x/0 -> 0.0` puts an *unbounded*
  ratio at the BOTTOM of an efficiency ranking, adjacent to the genuinely
  inefficient cases, which are the opposite finding. Carry a `defined` flag.
- **Applying the correction silently.** A halved byte count gets quoted
  without its caveat. Ship `corrected_*` beside the raw column and force the
  caller to name one.
- **Re-deriving the subset from prose.** The round file that says "confirmed
  on sa30 and sa31" is a claim about coverage; `ls` on the capture is the
  coverage. Use the second.

## Verification

A skill applying this leaves behind evidence a later reader can re-run.

1. The correction's scope is a field in the output, not a sentence in a
   commit message — the set of partitions it was validated on, and the set
   that exists.

2. The invariant checker reports the number of rows its own guards dropped,
   and a non-zero count blocks the positive verdict. There is a test that
   constructs a violating row the guard would have removed and asserts the
   verdict is negative.

3. There is a test that the correction still holds on the original partition —
   scoping an old result must not silently overturn it.

4. There is a per-partition table in the round file or the artefact, not only
   a pooled verdict.

Run, on this repo, to see all four in place:

```bash
python3 -m pytest nuc/tests/test_perturbation.py -q -k "factor_of_two or eight_days or dropped_buckets or denominator_omits"
python3 -c "
import sys; sys.path.insert(0,'nuc')
import perturbation as pt
secs = pt.sar_sections(open('state/nuc-capture-r424/sar-all.txt').read())
evs = [e for k in sorted(s for s in secs if s.startswith('SAR_B_'))
         for e in pt.reclaim_events(pt.parse_sar(secs[k]))]
c = pt.reclaim_double_count_check(evs)
print(c['ceiling_restored'], c['n_scan_free_steal'], c['n_over_ceiling_corrected'])
"
```

Expect the tests green, and `False 21 8` from the second command — the pooled
verdict that two day-files could not produce.

## Related

- `skills/elimination-needs-its-frame` — where the partition list comes from.
- `skills/null-result-needs-a-power-floor` — the same shape for a negative
  result rather than a correction.
- `skills/recorder-in-the-record` — the instrument appearing in its own data.

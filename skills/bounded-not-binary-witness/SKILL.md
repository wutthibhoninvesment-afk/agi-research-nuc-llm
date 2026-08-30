---
name: bounded-not-binary-witness
description: Replace a boolean "we ruled it out" claim with a measured upper bound when the evidence cannot actually rule the thing out. Use when a check returns witnessed/verified/safe true-or-false, the docstring or comment next to it already names a case it cannot see, and the boolean is feeding a headline number (a count, a "none", a "0h00m00s").
---

# Bounded, not binary

## When this triggers

All three, together:

1. A predicate returns a boolean-ish verdict — `witnessed`, `verified`,
   `safe`, `covered`, `clean`.
2. The code *itself* already names a case the evidence does not cover — in a
   docstring, a comment, a constant like `_SUSPEND_CAVEAT`, or a deferred
   backlog item.
3. That boolean feeds something a reader will quote: a count of unverified
   items, a `None` where a worst case would go, a total that reads as zero.

The tell that this has already gone wrong: **a test whose docstring describes
the blind spot and whose assertion says the blind spot is covered.** Round
340's `test_boot_history_cannot_see_a_suspend_and_the_tests_say_so` asserted
`witnessed is True`. The prose was right; the assertion is what shipped.

## Why the boolean is the bug

Two different rules can rule out the *same* thing and be given different
strengths, purely because one arrived later and looked more impressive.
Round 340's `boot_history` endpoint coverage and round 334's
`boot_utc_unchanged` both ruled out a reboot; neither could see a suspend;
one was `FULL` and the other `REBOOT_ONLY`. The stronger label then produced
`unwitnessed: 0h00m00s` and `max_unobserved_outage: None` for a log with
70+ hours of unprobed gaps.

**Rule: two rules that rule out the same thing must return the same
strength.** Applying it is what forces the honest downgrade.

## Steps

1. **Name what the evidence actually excludes**, in one sentence, with no
   "and therefore". Endpoint coverage excludes a reboot. It does not exclude
   a suspend. Stop there.
2. **Find every other rule that excludes the same set** and compare their
   strengths. Any mismatch is a bug in one of them; fix it before adding
   anything new.
3. **Downgrade first, then upgrade.** Ship the honest weaker strength as its
   own change so the headline numbers move once, visibly, and the diff can be
   read as "we were claiming X and we were not entitled to".
4. **Find the continuous signal.** A boolean usually comes from sampling
   endpoints. The bound comes from something the system emits *between*
   samples that it would not have emitted while broken — a log line, a
   heartbeat, a counter tick, a metrics scrape.
5. **Compute the largest run with no signal**, including the two edges. The
   edges are where a naive implementation loses the whole excursion: an
   interval whose only entry is one second after the start is still wide open
   afterwards.
6. **Err upward, always.** Whole-second truncation, clock skew, sort order —
   resolve every one in the direction that makes the bound *larger*. Sort the
   signal locally rather than trusting its source's ordering: one
   out-of-order entry yields a negative interval and silently deflates the
   bound, the one direction that must never fail.
7. **Refuse when coverage is partial.** Return `None`, never a number, if the
   evidence window does not provably span the interval. Silence outside the
   window is indistinguishable from silence inside it.
8. **Add the bound as a second axis, not a replacement.** Keep the boolean if
   other invariants depend on it (partition tests, totals), and add
   `unobserved_s` alongside. Rank headline numbers by the bound; keep the
   buckets keyed on the boolean.
9. **Key the upgrade on the STRENGTH, not the source.** Every rule that
   returns "ruled out the reboot, not the outage" deserves the same upgrade.
   Gating it on one particular source is how round 358's first cut scored
   `bounded_gap_count: 0` while holding 1870 live data points.
10. **State that the bound is never zero.** If an arbitrarily short excursion
    always fits between two signals, the method cannot reach `FULL`, and a
    test should pin that so no later round is tempted.

## Pitfalls

- **Resolution anti-correlates with risk.** The bound is tightest when your
  own activity generates the signal, and loosest on a quiet unattended
  interval — which is when an excursion is most likely. Always say whether
  the measured window contained your own traffic.
- **The probe is not free.** Round 358's per-boot journal scan took 5.5 s;
  the same query over 4.5 days of archived journals pinned one of the box's
  two cores past 5 minutes. Scope per natural unit (per boot, per file, per
  day) and cache.
- **Fail closed everywhere.** Missing evidence, unparseable evidence, an
  empty capture — each must degrade to the *previous* strength, never to a
  bound of "the whole interval", which reads like a measurement.
- **Do not let the bound overwrite positive evidence.** If another rule
  *proved* the excursion, the bound must not replace it with reassurance.

## Verification

Applied in `nuc/reachability_check.py` (round 358). Reproduce:

```
python3 -m pytest nuc/tests/test_reachability_check.py -q      # 165 passed
python3 nuc/reachability_check.py continuity \
  --boot-history state/nuc-boot-history-r358/list-boots-r358.json
python3 nuc/reachability_check.py continuity \
  --boot-history state/nuc-boot-history-r358/list-boots-r358.json \
  --journal-seconds state/nuc-journal-r358/journal-seconds-boot43e0c767.json
```

The second and third differ on exactly the axis this skill is about:
`bounded_gap_count` 0 → 1 and `unobserved_total_human` 70h53m11s →
67h27m58s, because one 3h26m49s gap is shown to hide at most 96 s. The
numbers above were re-run on 2026-08-30; `unwitnessed_gap_count` grows by one
per E-round, so re-run rather than quoting these.

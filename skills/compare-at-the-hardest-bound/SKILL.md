---
name: compare-at-the-hardest-bound
description: Use when a record declares its own timestamps, measurements or readings to be rounded, truncated, sampled or approximate - a `precision` / `resolution` / `granularity` / `accuracy` field, a docstring saying "rounded to the minute", a value reconstructed by arithmetic from a coarse source - and downstream code compares those values with `<`, `<=` or `==` as if they were exact. Symptoms: a duration printed to the second from minute-rounded endpoints; a headline that lands on a suspiciously round number; a rule that both grants evidence and levels an accusation using the same comparison; a field written by three producers and read by none. Covers turning each value into an interval, evaluating every claim at whichever end makes it HARDER, adding "straddles - decides nothing" as a third outcome, and auditing whether the imprecision moves any published conclusion. NOT bounded-not-binary-witness, which is about the EVIDENCE being weaker than a boolean; this is about the NUMBERS being fuzzier than a comparison.
---

# Compare at the bound that makes your claim harder

A record that says `"precision": "coarse"` has told you its timestamp is not a
timestamp. It is an interval. Every `<=` downstream is then a claim about an
interval evaluated as if it were a point — and which END you evaluate at is not
a style question, because one end makes your conclusion easier and the other
makes it harder.

The failure is quiet. Nothing crashes, no test goes red, and the number that
comes out is *almost* right. What is wrong is the confidence attached to it.

## The instance this came from

`state/nuc-reachability-log.jsonl` in this repo has carried a `precision` field
on every row since round 310. Its meaning was documented at birth:

> `precision` is "coarse" for uptime-derived arithmetic (uptime strings in the
> source prose are themselves rounded to the minute)

Three modules wrote it. **For 150 rounds, nothing read it.** The one appearance
in the entire test suite was `assert record["precision"] == "precise"`.

Round 460 measured what that cost: **20 of 61 rows coarse, 23 of 53 gaps with a
coarse endpoint, and those gaps carrying 60.3% of the log's published
ignorance.** The headline `max_unobserved_outage` printed as exactly
`14h00m00s` — and that roundness is the tell. Both endpoints were minute-
truncated, so they agreed on their seconds field by construction. The true
value is `13h59m00s .. 14h01m00s`.

The dangerous half was not the arithmetic. One rule granted a witness ("the
peer was last seen at or before the earlier check") and another levelled an
accusation ("something saw the peer alive INSIDE this outage"), and **both read
the same coarse timestamp as exact**. Because the coarse value is a *lower*
bound, reading it as a point understates when the gap started — which is
exactly the direction that sweeps a sighting into the gap and manufactures an
excursion that never happened.

## When this triggers

* A record carries a self-description of its own accuracy — `precision`,
  `resolution`, `granularity`, `accuracy`, `est`, `approx`, `sampled_at` — and
  you are about to compare the value it describes.
* A docstring, comment or commit message says a stored value was **rounded,
  truncated, floored, reconstructed, derived, or read from a renderer**.
* A duration or difference is printed at finer resolution than its inputs.
* A headline number is *suspiciously round* — `14h00m00s`, `100.0%`, `0` — and
  its inputs are quantised.
* One comparison serves two purposes: granting evidence in one branch and
  accusing in another. These need opposite bounds and almost never get them.
* `grep`ping a self-describing field across the tree finds writers and no
  readers.

## Steps

1. **Find the field and grep for its readers.** A precision/resolution field
   with producers and no consumers is the whole bug in one line. Do this before
   designing anything.
2. **Write down the interval, with its DIRECTION, from the producer's own
   docstring — not from the field name.** `uptime` truncates, so a
   reconstructed `boot + elapsed` can only be an *understatement*: the true
   instant is in `[stated, stated + resolution]`, never earlier. A value that
   was rounded to nearest instead gives `[stated - r/2, stated + r/2]`. These
   are different bugs and the wrong one is worse than none.
3. **Give an absent or unrecognised declaration the WIDEST resolution, not the
   narrowest.** An unknown provenance must not buy a claim it has not earned.
4. **For each comparison, ask what it is CLAIMING, then pick the end that makes
   that claim harder.** Not the end that makes it true.
   * granting evidence: latest-possible sighting vs earliest-possible check;
   * levelling an accusation: earliest-possible sighting vs latest-possible
     check, *and* the symmetric test at the other boundary.
   Write the reason in the code. The next reader will otherwise "simplify" it
   back to a point comparison, and it will still pass every test you wrote.
5. **Add "straddles — decides nothing" as a real third outcome.** An interval
   overlapping a boundary is evidence for neither side. Point-valued code
   cannot express this and will silently pick one; name the boundary it
   straddles and the resolution that made it ambiguous.
6. **Bracket the derived quantities too.** A difference of two intervals is an
   interval: `lo = later.lo - earlier.hi`, `hi = later.hi - earlier.lo`. Publish
   the bracket beside the point value rather than instead of it — consumers
   depend on the scalar.
7. **Separate a doubt about a VALUE from a doubt about an ORDER.** A bracketed
   maximum is still a well-defined maximum if the runner-up is outside the
   bracket. Report `argmax_robust` as its own field. Conflating the two turns
   an honest caveat into an overclaim of uncertainty.
8. **Build the differential audit: run the rules twice.** Once over the data as
   it is, once with every value declared exact, and diff the conclusions. That
   is the only thing that answers "did this ever matter?", and it is the
   artefact worth keeping — a permanent check, not a one-round measurement.
9. **Say plainly if the answer is "it never mattered".** Round 460's audit
   returned zero unearned claims. The guards are preventive; that is the
   finding, and `--strict` exists so the day it stops being true is not
   invisible.
10. **Falsify each bound by flipping it.** Revert `t1_hi` to `t1_lo` in the
    accusation branch and a test must go red. If none does, the bound is
    decoration.

## Pitfalls

- **The safe direction differs per branch, and the same variable appears in
  both.** `t1` grants with its lower bound and accuses with its upper. Reaching
  for "always use the conservative end" produces a rule that is conservative in
  one branch and reckless in the other.
- **Widening a bracket can WEAKEN evidence you already had.** Step 4's
  granting rule reads the *stated* value, so a forward-opening bracket cannot
  cost you a witness — but a symmetric one can. Check which shape you have
  before promising the change is free.
- **A round number is a symptom, not proof.** `14h00m00s` was an artefact.
  `0` unearned claims was real. Measure; do not pattern-match on tidiness.
- **Do not collapse an interval to its midpoint anywhere, ever.** That is the
  division the interval exists to avoid, and it will read as a measurement.
- **When you widen a rule, the "compatibility" path is where the old bug
  hides.** Keep a normaliser that accepts the legacy scalar form and turns it
  into a degenerate interval, so one code path serves both and the comparison
  cannot silently diverge.
- **Two coarse readings of one unchanging value intersect.** Do not average
  them, and if they do NOT intersect, that is positive evidence the value moved
  — return nothing rather than a favourite.

## Verification

Applied in `nuc/reachability_check.py` and `nuc/reachability_recover.py`
(round 460). Run from the repo root:

```bash
python3 -m pytest nuc/tests/test_reachability_check.py \
                  nuc/tests/test_reachability_recover.py -q
# expected: >= 301 passed (round 460 made this a floor, not an equality)

python3 nuc/reachability_check.py precision-audit --strict
# expected: exit 0, `"unearned_claims": []`, and a
# `max_unobserved_outage` carrying `bracket_human` beside `printed_s`
```

Named tests, one per step:

* step 1 — the field had no readers: `grep -n precision nuc/reachability_check.py`
  returned one write and one unrelated comment before this round.
* step 2 — `test_a_coarse_row_brackets_its_check_instant_forward_by_a_minute`
  (direction, not just width).
* step 3 — `test_a_row_that_does_not_declare_its_precision_gets_the_widest_bracket`.
* step 4 — `test_a_coarse_earlier_check_cannot_manufacture_a_missed_excursion`,
  falsified by `test_the_same_sighting_against_a_precise_earlier_check_still_accuses`:
  identical data, one field changed, opposite verdict.
* step 5 — `test_a_sighting_exactly_at_the_later_check_straddles_it`.
* step 6 — `test_the_headline_max_unobserved_outage_is_a_two_minute_bracket`.
* step 7 — `test_the_headline_outage_argmax_is_robust_and_says_so` and its
  falsifier `test_an_argmax_inside_its_own_bracket_is_reported_as_not_robust`.
* step 8 — `test_the_point_view_reproduces_the_pre_round_460_rules_exactly`.
* step 9 — `test_the_audit_finds_nothing_unearned_in_the_live_log_today`.
* step 10 — nine falsifiers, tabulated in
  `knowledge/round-460-the-field-nobody-read.md` §6; the two for this skill are
  F1 (10 reds) and F2 (1 red).

The pitfall about weakening evidence has its own pin:
`test_a_witness_is_immune_to_the_EARLIER_checks_precision_and_here_is_why`.

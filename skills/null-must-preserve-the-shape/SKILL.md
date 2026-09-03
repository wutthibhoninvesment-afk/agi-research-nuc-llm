---
name: null-must-preserve-the-shape
description: Use when WIDENING a population, selector, matcher or candidate set makes a coverage/hit/attribution figure jump — a regex that now admits more event kinds, an allowlist that grew, a search that indexes more sources, a correlation run over more candidates, a "we now explain 94% of X" result. The jump is only evidence against a null that holds the population's SIZE and its INTERNAL STRUCTURE fixed. Symptoms: a coverage percentage published with no null; a chance baseline drawn uniformly when the real points arrive in bursts or on a cadence; a p-value sitting on its floor with no note of what its ties were; a null implemented as a paraphrase of the instrument rather than a call into it. Covers picking a shape-preserving null (circular shift / block permutation) over a uniform one, showing the two disagree before trusting either, self-checking the fast path against the real one, and asking whether the population you just added is your own instrument's footprint.
---

# A wider net catches more fish; that is not evidence about the sea

When widening a population makes coverage jump, the jump has two possible
causes and they look identical in the output:

1. the new members really are associated with the outcome, or
2. there are simply more of them, and a bigger population lands on more
   buckets whatever it is made of.

Only a null separates these, and **which null decides the sign of the answer**.
Round 466 of this program measured both on the same data: a uniform-placement
null said the effect was *below* chance, and a shape-preserving null said it
was ~4x chance at p ≤ 0.001. Same observation, opposite conclusions.

## When this triggers

* a regex, filter, `WHERE`, allowlist or event-kind alternation is widened and
  a coverage / attribution / recall number rises
* a "we now explain N% of X" claim is about to be written down
* a chance baseline is being computed by sampling points independently and
  uniformly
* a null is being reimplemented for speed instead of calling the real thing
* a p-value comes back at exactly `1/trials`

## Steps

1. **Re-derive the pre-widening number first.** Before touching anything,
   reproduce the figure the widening is supposed to improve on, from its own
   inputs. Round 466 re-derived `52 costly buckets / 31.53 GiB / 19 named /
   26.7%` and matched round 436 to the digit; that match is what licensed
   every later comparison. A widening measured against a remembered baseline
   measures your memory.

2. **State the widening as a parameter, and pin the default.** Widen by adding
   an argument (`kinds=("service",)`), never by loosening the existing regex.
   Then write the test that says the new code with the default argument is
   *byte-identical* to the old code. Now no published number can move except
   when somebody passes the wider value on purpose.
   Round 466: `test_widening_to_services_only_reproduces_round_436_exactly`.

3. **Look at the shape of your points before choosing a null.** Plot or
   tabulate inter-arrival times and burst sizes. Housekeeping timers fire on a
   cadence; login sessions arrive in bursts; user requests come in sessions.
   If the points are not independent, a uniform null is not conservative — it
   is *wrong in the flattering direction for the null*, because independent
   draws scatter across far more distinct bins than a clustered population of
   the same size ever could.

4. **Prefer a rigid circular shift.** Translate the whole event train by one
   random offset and wrap it inside the window. Count, cadence, burst
   structure and every inter-arrival gap survive untouched; only the alignment
   with the outcome is destroyed. Block permutation is the same idea when the
   window is not naturally cyclic. This is the null that answers the question
   you actually asked: *do these events land where the outcome is, or merely
   land often?*

5. **Run the uniform null too, and publish the disagreement.** Do not just
   assert that the shift null is the right one — show the number the wrong
   null gives. If they agree, you have lost nothing. If they disagree, the
   disagreement is a result: it says the effect is carried by *where* the
   points are, not *how many* there are.
   Round 466: `test_the_uniform_null_and_the_shift_null_disagree_in_opposite_directions`.

6. **If you build a fast path for the null, make it self-check against the
   slow one.** 2000 draws over a real instrument is usually unaffordable, so a
   lookup table gets built. Build it *by calling the instrument* rather than by
   reimplementing its rule, and ship a `verify()` that compares the table's
   answer with the instrument's on every real population.
   This is not ceremony: round 466's first draft reimplemented the placement
   rule and the self-check caught two independent divergences — a mishandled
   post-restart row, and the instrument's own exclusion list not being applied,
   which alone took the observed figure from 19 to 50. **A null on a paraphrase
   of your instrument is not a null on your instrument.**

7. **Report what the p-value's ties were.** At a large effect size the only
   draws that tie the observation may be the ones that drew offset 0 — the
   identity. A p at its floor should say `n_identity_draws` and `p_floor`
   beside itself, or a reader cannot tell "nothing beat it" from "we didn't
   draw enough".

8. **Ask who the new members are.** A widening that suddenly explains most of
   the outcome deserves the question *whose events are these?* Round 466's
   widening explained 94% of a ten-day swap record — with the analyst's own ssh
   logins. Check the added population against your own tooling's schedule,
   log, or trace before celebrating; see `recorder-in-the-record` for the
   sampler case and `matcher-defines-the-population` for how the population got
   chosen in the first place.

9. **Report untestable as untestable.** If the evidence you would use to
   attribute the new members only covers part of the window, split the
   population into testable and untestable rather than scoring the uncovered
   part as a negative. Round 466: 19 of 52 buckets predate the log that would
   identify them, and are reported as `n_untestable_before_the_log_existed`,
   not as 19 clean negatives.

## Pitfalls

* **"More coverage is better" is the whole trap.** A population large enough
  names every bucket there is. Coverage without a null is not a weak result,
  it is not a result.
* **Do not pick the null that flatters the finding.** Pick it from the shape of
  the data (step 3), decide before you see the answer, and show both (step 5).
* **A uniform null is not the safe default.** It is only correct when the
  points really are independent. It is *anti*-conservative for clustered data
  because it inflates expected distinct-bin coverage.
* **Don't fold the exclusions you already believe in only into the slow path.**
  Whatever the real instrument drops (samplers, instruments, self-traffic), the
  null's population must drop too, or the null measures a different population
  than the observation.
* **A shift null needs a window it can wrap.** If the window has hard edges
  where the outcome cannot occur (a boot, a retention boundary), the wrap
  smears events into impossible times. Either restrict the shift or use block
  permutation within valid segments.

## Verification

Run both, on the real artefact, and require them to disagree:

```
cd <repo> && python3 nuc/perturbation.py population \
    --capture state/nuc-capture-r424 --verify        # exit 0 = fast path == instrument
python3 -m pytest nuc/tests/test_perturbation.py -q \
    -k "shift_null or uniform_null or bucket_map or population_coverage"
```

The self-check (`--verify`) must exit 0 with `identical: true` for every
population; if it does not, no null result from that run may be quoted.
`test_the_uniform_null_and_the_shift_null_disagree_in_opposite_directions`
must stay green — it is the test that fails the day somebody "simplifies"
the shift sampler into a uniform one.

Falsify step 6 by deleting the exclusion from the fast path's population
builder: `test_the_map_applies_the_ledgers_own_exclusions` and
`test_the_bucket_map_agrees_with_cost_ledger_on_every_population` both go red.
Falsify step 4 by replacing the circular shift with independent uniform draws:
`test_the_scope_population_beats_its_null_by_more_than_the_service_one` and
`test_that_seven_is_not_what_a_population_that_size_names_by_chance` go red.

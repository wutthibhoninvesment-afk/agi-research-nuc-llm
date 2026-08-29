---
name: sampled-interval-brackets
description: Use when code computes how long something lasted from periodic observations rather than from events — outage/downtime duration, incident length, "how long was this host unreachable", session length from heartbeats or log lines, time-to-recovery, how long a flaky test stayed broken, when a regression landed between two runs. Symptoms: a duration derived by subtracting two poll timestamps; a "longest ever" or "record" comparison between two such durations; a dashboard reporting a single number for something nobody watched continuously; prose in one report and tool output in another disagreeing about the same interval's length. Covers reporting a [confirmed, max-possible] bracket instead of a point, naming the evidence each bound rests on, dropping rather than clamping contradictory evidence, and making "is this a record" a proof instead of a like-for-like guess. NOT for statistical confidence intervals, sampling error, or measurement noise — this is about gaps between observations, not variance within them.
---

# Bracketing an interval measured by sampling

A duration computed from periodic checks is **not** the duration. It is the
span you *watched*. The real interval started at some unobserved instant
before your first observation and ended at some unobserved instant after
your last one. Subtracting two poll timestamps gives a strict **lower
bound** — and code almost always prints it as though it were the answer.

## When to use (triggers)

- A function subtracts two observation timestamps and returns "how long
  the outage / incident / down window / session lasted".
- Two such durations get compared: "longest outage on record", "this is
  the worst one yet", "did it beat the previous record".
- The poll cadence is coarse relative to the thing measured (hourly checks,
  a CI job per commit, a cron probe, a human running a command each round).
- Two write-ups of the same interval disagree slightly and nobody knows
  which is right — a strong tell that they picked different bracket ends.

**When NOT to use:** the system emits real transition *events* (a
"went down at T" message), so the endpoints are known and there is no gap
to bracket. Also not for confidence intervals, sampling error, or noise —
those are about variance in a measurement; this is about the absence of
one.

## Steps

1. **Name the two ignorance windows before writing any code.** For an
   interval observed from `first_check` to `last_check`, the real start
   lies in `(last evidence of the other state, first_check]` and the real
   end lies in `[last_check, first evidence of the other state)`. Write
   both down. Checkable outcome: you can state, in seconds, how much of
   the real interval you did not observe on each side.

2. **Inventory the evidence you already store but never parse.** This is
   where the win usually is. Monitoring payloads routinely carry a field
   that pins a transition far tighter than your own poll does — a
   `LastSeen`/`last_heartbeat` from the peer, a boot time, a process start
   time, a first log line. Grep your persisted records for timestamp
   fields no code reads. Checkable outcome: a list of fields present in
   stored data with zero consumers.

3. **Report a bracket, not a point.** Four numbers, not one:

   ```
   confirmed_span   last_check - first_check          # strict lower bound
   max_possible_span
                    latest_possible_end
                      - earliest_possible_start       # strict upper bound
   start_uncertainty
                    first_check
                      - earliest_possible_start
   end_uncertainty  latest_possible_end - last_check
   ```

   Breaking the uncertainty out per side is what tells a reader *which*
   end is imprecise, and therefore what to fix (poll faster? store the
   peer's heartbeat?). Checkable outcome:
   `confirmed <= max_possible`, and both uncertainties `>= 0`, asserted as
   a test over your real stored data, not just fixtures.

4. **Name the evidence each bound rests on, in the output.** A
   `*_source` field per bound (`"peer_last_seen"`, `"boot_time"`,
   `"previous_check"`, `null`). Without it a reader cannot tell a bound
   pinned to 3 minutes from one pinned to 3 hours, and the two look
   identical in a report. Checkable outcome: every bound in the output has
   a source label, and `null` source implies `null` bound.

5. **Keep the strongest number in one evidence class.** Do not widen
   `confirmed_span` using weaker corroborating evidence to make it look
   better. If your lower bound means "the ground-truth probe failed at
   both endpoints", it must keep meaning exactly that — downstream
   comparisons and every previously published figure depend on it. Weaker
   evidence belongs on the *upper* bound, where the uncertainty already
   lives. Checkable outcome: the lower bound's definition is unchanged
   from before your change, and old published numbers still reproduce.

6. **Leave an unbounded side unbounded.** If the interval is still open,
   or opens your data set, one side has no bound. Emit `null` for the
   upper bound rather than substituting "now" or the first record —
   either substitution silently converts an open interval into a claim.
   Checkable outcome: a test asserts that an unbounded side forces the
   whole max-possible span to `null`.

7. **Drop contradictory evidence; never clamp it.** Evidence that would
   invert a bracket (a heartbeat *after* you first saw it down; a boot
   time *before* your last down observation) means more transitions
   happened than one bracket can represent. Fall back to the weaker bound
   and keep going. Clamping to zero hides a real data problem behind a
   plausible number. Checkable outcome: a test per contradiction shape,
   each asserting the fallback source, not just a non-negative result.

8. **Make "is this a record" a proof.** Comparing your lower bound against
   a historical lower bound is like-for-like but proves nothing — the old
   interval's *true* span may have been longer. Emit both: the
   like-for-like comparison, and a `definitely_exceeds` that compares your
   lower bound against the historical **upper** bound. The second is only
   true when the new interval wins even under the old one's most generous
   reading. Abstain (`null`) when the historical interval has an unbounded
   side. Checkable outcome: a test where the two comparisons disagree —
   `exceeds` true, `definitely_exceeds` false — because that gap is the
   whole point.

## Pitfalls

- **The timestamp parser that only ever parsed your own timestamps.**
  Step 2's newly-consumed fields come from someone else's serializer and
  routinely carry fractional seconds (`...:00.1Z`, `...:50.906797174Z`)
  that a hand-written `%Y-%m-%dT%H:%M:%SZ` format rejects outright. The
  crash is latent for as long as nothing parses those fields. Normalise
  the fraction to exactly 6 digits by **truncation** — rounding
  `.9999999` rolls a whole second forward. `datetime.fromisoformat`
  handles `Z` and 9-digit fractions only on Python 3.11+.
- **Symmetric evidence read asymmetrically.** A "last seen alive" field
  bounds a *down* interval's start (the fall happened after it) and an
  *up* interval's… nothing, because inside an up interval the same field
  means "seen alive during", the opposite direction. Applying one rule to
  both verdicts produces confidently wrong bounds. Decide per state class
  and write the reasoning into the code.
- **Reading evidence off the wrong record.** Only the record adjacent to
  the transition is evidence about that transition. A boot time two polls
  later is a different (or unknowable) boot; a heartbeat from mid-interval
  says nothing about its edges.
- **Widening the lower bound because it makes the headline better.** See
  step 5. It is the one number consumers already trust.
- **Retro-fitting a field by hand-editing stored records.** If a fact has
  been sitting in a free-text `notes`/`message` column, promote it to a
  real field — but regenerate from whatever script produced those records
  and diff first, so you can prove exactly one row changed and only by
  gaining the new key.

## Verification

```bash
# 1. Bracket invariants over your REAL stored data, not fixtures:
#    confirmed <= max_possible; uncertainties >= 0; an unbounded side
#    forces max_possible to null.
pytest -q tests/test_bounds.py -k real_log

# 2. Pin a CLOSED interval's complete bracket. Closed history can never
#    legitimately move again, so every field of it is a regression test.
pytest -q tests/test_bounds.py -k first_outage_bracket_is_pinned

# 3. Prove the old point-estimate number is unchanged: the lower bound
#    must still equal what every previous report published.
pytest -q tests/test_bounds.py -k confirmed_span_matches_published
```

- Every previously-published duration reproduces exactly as the new
  `confirmed_span`. If any moved, step 5 was violated.
- At least one real interval's bracket is *wide* (hours). If every bracket
  is within seconds of its point estimate, either the cadence is fine and
  this skill was not needed, or the evidence search in step 2 was skipped.
- The pre-existing test suite passes untouched. Adding bounds is purely
  additive; a rewritten assertion means an existing meaning changed.

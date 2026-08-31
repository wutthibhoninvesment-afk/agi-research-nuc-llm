---
name: measured-exemption
description: Use when a differential test, oracle, lint or audit is about to EXEMPT a class of inputs it knows may legitimately differ — "these programs are allowed to disagree, skip them" — and the exemption is about to be written as an early return. Symptoms: a review comment saying "X must diverge, so exempt it"; a checker whose ok-path silently swallows a whole family; a suppression list nobody has counted; a campaign that reports only its failures, so an exemption that fires on 5% of inputs and one that never fires look identical. Covers running the exempt case anyway and reporting the outcome, asserting each exemption is load-bearing in both directions, and the follow-up question an early return makes unaskable — is the exemption firing for the reason it was written for?
---

# Measure the exemption, do not skip it

An exemption encodes a claim: *these inputs are allowed to differ, and here
is why*. The "why" half is a hypothesis about the system, and an early return
is the one implementation that makes it permanently unfalsifiable — the
checker stops before it could find out.

The fix costs one extra run per exempt input and changes no verdict. The
input is still `ok`. What changes is that the tool now says whether the
exemption was USED and what the difference actually was.

## When to use (triggers)

- You are adding an exemption / allowlist / `# noqa` class / "known
  acceptable divergence" to a differential test, oracle, lint or audit.
- A design note says "family F must diverge because of mechanism M, so
  exempt F" — M is a hypothesis and F is the evidence for it.
- A checker's summary reports findings only, so a suppression firing on 5%
  of inputs is indistinguishable from one that never fires.
- You inherit an exemption written by someone else and want to know whether
  it still earns its place.

## Steps

1. **Write the exemption as a REASON STRING, not a boolean.** The predicate
   returns `""` (not exempt) or a sentence naming the mechanism and the
   evidence: `"spec name 'S1' is bound 2 times (defining env vs call env)"`.
   That string is the hypothesis, and it goes in the output.
2. **Run the exempt input anyway.** Same comparison, same fields. Wrap it so
   a crash in the exempt path becomes part of the report rather than a
   finding — the input has already told you its answer may be anything.
   Watch the exception hierarchy: a timeout sentinel that subclasses
   `BaseException` must still escape your `except Exception`.
3. **Report three states, not two:** `exempt, unused` (the exemption applied
   and nothing differed), `exempt, used` + the first difference, and the
   ordinary compared/agreed. Verdict stays `ok` for all three.
4. **Classify the "used" cases and count them.** This is the step the early
   return removes. Bucket the differences by mechanism and check the
   distribution against the reason string you wrote in step 1.
   **Bucket by what the OTHER side did, not only by the exempt side's
   mechanism.** An exemption whose predicate is symmetric ("either side hit
   the budget") hides two different populations: one where BOTH sides
   declined, and one where the other side produced a real ANSWER. The first
   is a difference of degree and is what the exemption was almost certainly
   written for; the second is a difference of KIND — the two implementations
   disagree about what the system does, not about how far it gets — and the
   same early return covers both.
5. **Assert every exemption is load-bearing, in BOTH directions.** One test
   per mechanism: the input must report `exempt, used`, AND must become a
   real finding with the exemption predicate silenced. One direction alone
   proves nothing — an exemption nothing uses is a coverage hole with a good
   excuse, and an exemption that never suppresses anything is dead code.
6. **If a mechanism has no input that exercises it, that is a corpus gap,
   not a reason to drop the exemption.** Find the input shape that reaches
   it and add it to the generator, then re-measure (step 4). Ask what
   ORDER / PLACEMENT / timing the mechanism needs, not only which constructs
   — a generator can emit every construct in a family and still never emit
   them in the arrangement that makes the difference observable.
7. **Keep the coarse predicate.** Over-exempting costs coverage; under-
   exempting costs correctness. Step 3's `exempt, unused` count is the price
   of the coarseness, now visible, and is the input to any later narrowing.

The shape, in whatever language the checker is written in:

```python
reason = exemption_for(item)          # "" or a sentence naming the mechanism
a, b = run(item, form_a), run(item, form_b)
d = first_difference(a, b)
if not reason:
    return FINDING(d) if d else OK("compared, agreed")
if d:
    return OK("exempt, used (%s)\n  %s" % (reason, d))    # verdict unchanged
return OK("exempt, unused (%s)" % reason)
```

## Pitfalls

- **Reporting the exemption only in an aggregate counter.** The count says
  how often; only the per-input difference says why. Put the first
  difference in the detail string.
- **Turning `exempt, used` into a finding.** It is not one. The moment it
  fails a build, the next engineer widens the predicate until it stops
  firing, and you are back to an early return with extra steps.
- **Silencing the predicate globally in tests without restoring it.** Use
  try/finally; a leaked monkeypatch makes every later test in the file
  measure a different tool.
- **Assuming the exempt population is homogeneous.** Two mechanisms can
  route through one predicate. Round 359 found an exemption written for
  mechanism A firing 47 times for mechanism B and zero times for A.
- **A predicate written for a difference of DEGREE, silently covering a
  difference of KIND.** The classic shape: side A and side B both have
  budget X, B's is smaller, so B trips first and the exemption is fair. Then
  a feature lands where A has NO budget of that kind at all — and the
  predicate, which only asks "did anyone trip X", keeps saying `ok`. Round
  371: a self-hosted evaluator charged one frame per TAIL call while the
  host charged none (its whole tail-call feature), so it refused at 399
  iterations what the host answered at 1 000 000. Four of the language's own
  pinned tail-loop contracts were unmeetable by its own self-definition, and
  every oracle said `ok` for the life of the oracle. The tell is step 4's new
  bucket: the exemption firing while the other side holds a real value.
- **Normalising until they agree.** If the fix for an `exempt, used` case is
  "strip this clause before comparing", you have converted an oracle into a
  tautology. Only do it with an injected-bug test proving the normalisation
  does not swallow the bug too.
- **Counting the exemption at one door when the checker has two.** Round 411:
  a path checker's exemption list (placeholder / scratch / url) lived inside
  the function that PRODUCES candidate tokens, so a special-cased branch with
  its own regex — added in the same commit, for `cd` lines — was exempt from
  the exemptions. The same token was silently skipped as an argument and
  reported as a violation as a prefix, for 71 rounds, until somebody wrote
  the provoking input. Before you count an exemption's firings, `grep` the
  finding CODE and confirm you have found every site that can emit it;
  a per-door count is not a corpus count. See `second-door-skips-the-gate`.
- **An exemption written as an early return also exempts everything BEHIND
  it.** Same round: the branch above `continue`d after reporting, so every
  path token later on the same line was never examined at all. A false
  positive on an exempt input was therefore also buying a false negative on
  a real one — which is why "it only produces noise" is never a safe reason
  to defer this class of fix.

## Verification

Re-derive on a real exemption, not a fixture:

1. `grep` the checker for early returns inside its exemption branch — each
   one is an unmeasured claim.
2. Run a campaign and count the three states. If `exempt, used` is 0, the
   exemption is either unnecessary or unreachable from this corpus; both are
   findings, and step 5's silenced-predicate test tells you which.
3. Classify the `used` cases by mechanism and compare against the reason
   string. Agreement is a confirmed hypothesis; disagreement is the finding.

Second worked example (round 371, `harness/swe/guest.py`'s `agree()`):
one line, `if h == DEPTH_SENTINEL or g == DEPTH_SENTINEL: return True`, with
the comment `# one-sided depth exhaustion: exempt by design`. Adding an
optional `notes` list — default `None`, so every existing caller is
byte-identical — and one three-way classifier (`host_valued` /
`guest_valued` / `both_missed`) was the entire change. The verdict did not
move (a known divergence must not redden a standing campaign, per the second
pitfall above) and no new campaign signatures appeared, because the
project's `signature()` keys only on crash/mismatch details — check that
before you make an `ok` detail non-empty.

Worked example (round 359, `harness/swe/oracles.py`'s `param_erasure`):
2500 generated programs, 0 mismatches, 47 `exempt, used` — and **47 of 47**
differed on a wording clause added five rounds after the exemption was
designed, none on the mechanism it was designed for. Teaching the generator
one new statement ORDER (the shadowing binding after the annotated function
rather than before) moved that to 66 of 93 on the intended mechanism, 22 of
them a different VALUE rather than a different message. Every number in that
sentence is unobtainable from a checker that returns early.

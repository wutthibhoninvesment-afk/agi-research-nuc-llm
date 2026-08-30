---
name: deferral-blockers-are-claims
description: Use when you are about to inherit, act on, or repeat a written explanation of why some work was NOT done — a design note's "not fixed here because…", a code comment's "this would require rewriting every call site", an ADR's rejected-alternatives section, a ticket closed as "too expensive", a docstring justifying a cache or a shortcut. Symptoms: a blocker stated as a quantity nobody re-derived ("several hundred call sites", "would dominate the runtime", "a whole sprint"); an estimate that has been quoted by later work as if it were measured; a deferral that names three obstacles and gives evidence for none. The move is to split the rationale into one blocker per line, price each independently with the cheapest check that could refute it, and only then decide — most such lists contain at least one blocker that is recoverable from data the artifact already holds. NOT for estimating unstarted work (no prior rationale exists), and NOT for deciding whether the work is worth doing once the blockers are priced.
---

# A deferral's blockers are claims, and they have prices

When someone writes "we did not do X because A, B and C", the sentence looks
like a decision. It is actually **three predictions with no error bars**, and
the next person to read it will inherit all three at once — usually by
quoting the scariest one.

The recurring failure is not that the blockers were wrong. It is that they
were never separated, so a single true blocker (C) carried two false ones
(A, B) forward for as long as the note stood.

## When to use (triggers)

- A design doc, SPEC section, ADR or knowledge file says work was deferred
  and gives reasons.
- A code comment justifies a workaround, a cache, a duplicated
  implementation or an exemption with a quantity ("re-parsing this per call
  would dominate", "widening this touches every call site").
- A ticket was closed "won't do — too big" and is being reopened.
- You are about to WRITE such a rationale (steps 1 and 6 apply to you too).
- A later document cites the estimate as if it were a measurement.

**When NOT to use:** estimating work that has no prior written rationale;
deciding whether the work is worth doing once each blocker has a price
(that is a scheduling call, not this).

## Steps

1. **Split the rationale into one blocker per line.** Copy the sentence out
   and break it at every "and", "additionally", "also". A rationale that
   reads as one wall is the failure mode; a list is auditable.
   *Checkable outcome:* a numbered list where each item is a single
   falsifiable claim.

2. **Tag each blocker with the observation that would refute it, and its
   cost.** Not "how would I fix this" — "what is the cheapest thing that
   would show this blocker is not real". A grep, a one-line REPL, a `git
   log -S`, a five-second timing loop.
   *Checkable outcome:* every item carries a refutation test and an
   estimated cost in seconds.

3. **Run every refutation under one minute, cheapest first, before any
   design work.** This is the whole skill. The blockers that survive are
   the ones worth designing around.
   *Checkable outcome:* each item is marked TRUE (with its evidence) or
   FALSE (with the observation that refuted it).

4. **Look hardest for the blocker that names a QUANTITY the author did not
   measure.** "Several hundred call sites", "would dominate the campaign",
   "a whole round's work". A quantity in a rationale is almost never a
   measurement — if it were, the author would have quoted the number.
   *Checkable outcome:* every numeric claim in the rationale is either
   sourced to a measurement in the same artifact, or re-derived by you, or
   struck.

5. **Ask, for each "the data is missing" blocker, whether it is recoverable
   from data the artifact already holds.** This is where the false blockers
   cluster. A field that looks absent is often a lossless function of a
   field that is present — a composed string that is invertible, a value
   derivable from a neighbouring one, an id reconstructible from a key.
   *Checkable outcome:* for each missing datum, either an inverse function
   with the precondition that makes it exact, or a written reason no
   inverse exists.

6. **Rewrite the rationale as the priced list, and pin the surviving
   blockers as tests.** A blocker that survives should fail loudly if it
   ever stops being true — assert its *precondition*, not its consequence.
   A false blocker should be deleted, not softened; a softened one gets
   re-inherited.
   *Checkable outcome:* the note now says which blockers were checked, how,
   and when — and each survivor has a test.

7. **If you are WRITING a deferral, state each blocker with its evidence or
   mark it UNPRICED.** An unpriced blocker in your own note is a debt with
   your name on it, and marking it is what lets the next reader spend one
   minute instead of inheriting it.

## The three commands that do most of the work

```sh
# (a) is this quantity sourced anywhere, or is it prose?
grep -rn "several hundred\|would dominate\|whole round\|too expensive" . \
  --include='*.py' --include='*.md' --include='*.lang'

# (b) does the override this blocker assumes actually exist? (step 5)
grep -c 'detail=' whence/interp.py          # 0 => the default always holds

# (c) price the estimate itself, in seconds, before believing it
python3 - <<'EOF'
import time
t = time.time()
build_the_thing_the_note_says_is_expensive()
print("%.3fs" % (time.time() - t))
EOF
```

Command (c) is the one people skip. Round 377 of this program found a
docstring claiming a rebuild "would dominate the campaign"; the rebuild is
0.11 s against a 0.69 s median program, and the measurement took eight
seconds to run.

## Pitfalls

- **Treating the rationale as one claim.** The commonest error, and the
  reason a true blocker protects false ones for rounds at a time.
- **Pricing the fix instead of the blocker.** "How long would this take"
  re-derives the deferral. "What would show this obstacle is not there" does
  not.
- **Accepting a quantity because it is specific.** "Several hundred call
  sites" is more persuasive than "a lot" and no better sourced. Specificity
  is a writing habit, not evidence.
- **Refuting a blocker and then not checking its precondition.** An inverse
  that works because no current call site overrides a default is correct
  *and* fragile: assert the precondition (`assert "detail=" not in src`), or
  the next call site breaks it silently.
- **Deleting the rationale entirely once refuted.** The next reader needs to
  know the question was asked and answered, or they will re-derive the same
  deferral.
- **Assuming the untested path is broken.** The mirror of this skill's own
  bias. "Nobody has checked X, so X is wrong" is a prior, not a finding —
  round 362 of this program made it four times in one bank and it was wrong
  four times.

## Worked example (round 378)

Whence's SPEC deferred fixing its self-hosted evaluator's provenance queries:

> Making the family correct means widening `mkb` and every one of its
> several hundred call sites, and `walk_steps` additionally dedups shared
> nodes BY IDENTITY, which Whence has no operator for.

Split (step 1) into three blockers, priced (steps 2–5):

| # | blocker | refutation, and cost | verdict |
|---|---|---|---|
| 1 | the guest box has no `op`/`detail` split | `Prov.label()` is `op + " " + detail`; grep every host op for a space — **20 s** | **FALSE** — zero ops contain a space, so splitting at the first space is an exact inverse; `mkb` never widened |
| 2 | a miss node's detail is unreachable | `mk_miss` uses the reason AS the detail; `grep -c 'detail=' interp.py` — **5 s** | **FALSE** — zero overrides, so `reasons()` minus the `(line N)` suffix recovers it. Precondition pinned as a test |
| 3 | no identity operator | read `walk_steps` — **1 min** | **TRUE**, and the only real one — and it turned out to be a *design* question (adding identity would make the evaluator's allocation observable), not an engineering one |

Two of three blockers were false and cost 25 seconds to refute. The
deferral had stood for four rounds.

## Verification

You have applied this skill correctly when:

1. The rationale exists as a numbered list, one falsifiable claim per line.
2. Every line carries a verdict and the observation behind it, not an
   opinion.
3. Every numeric claim in the original is sourced, re-derived, or struck.
4. Each surviving blocker has a test asserting its PRECONDITION.
5. The refuted blockers are recorded as refuted (with what refuted them),
   not silently removed.
6. Total refutation cost is written down — if it exceeded ~10 minutes,
   say so, because that changes whether the original deferral was
   unreasonable.

The worked example's two refutations, re-runnable in this repo:

```sh
# blocker 2: does any call site override the default this inverse relies on?
grep -c 'detail=' languages/whence/whence/interp.py

# blocker 1: is the composed label actually invertible?
grep -n 'def label' -A 5 languages/whence/whence/values.py
```

The first prints `0` and the second prints `op + " " + detail`. Together
they are the whole refutation of two of the three blockers, and they take
under thirty seconds.

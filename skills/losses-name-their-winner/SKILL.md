---
name: losses-name-their-winner
description: Use when something you own keeps losing a selection — a skill description that never gets invoked, a router or classifier picking the wrong branch, a retrieval query returning the wrong document, an LLM judge choosing a rival answer — and you are about to reword it against the competitor you believe it loses to. Symptoms: a "NOT for X, use Y instead" clause written from reasoning rather than logs; a ticket saying "these two overlap, fix them as a pair"; a recall number with no record of what won instead; a raw win-minus-loss count used to rank who is greedy. Covers recording the winner of every loss, separating an ABSTENTION (nothing was selected) from a DISPLACEMENT (a rival was), normalising take-rates against the probes a rival could have taken, and comparing the confusable you named to the one the data names. NOT for whether a measurement replicated (repeats-are-not-replicates) or whether a population was selected correctly (filter-shares-the-defect).
---

# Losses name their winner

You measured recall. Your thing fired 2 times in 18. So you go and rewrite
its description against the sibling you are sure it is losing to — the one
whose subject sounds nearest, the one you named in your own `NOT for …`
clause, the one the ticket says to fix as a pair.

That plan has a hidden premise: **that there is a rival, and that it is the
one you named.** Both halves are measurable, both are cheap to measure —
the losing probe already recorded who won — and on the corpus where this
was first run, both halves were false.

A loss comes in two kinds and only one of them has a competitor in it:

* **Displacement** — something else was selected. There is a rival, it is
  identifiable, and a boundary rewrite can move the line between you.
* **Abstention** — *nothing* was selected. There is no rival. No boundary
  rewrite can reach this, because there is no boundary; the description
  failed to stake a claim at all, and the remedy is a claim, not a
  contrast.

Collapsing these into "recall was low" is what makes the pair rewrite look
like the obvious move. Measured on this repo's 56-skill trigger corpus over
41 archived probe reports: **121 losses, of which 53 (44%) had no
competitor fire at all**, and of the six descriptions that both name a
sibling in a `NOT for …` clause and have lost a probe to some rival,
**exactly one** had that named sibling as its top measured taker.

The second trap is arithmetic. Rank skills by `taken − lost` and you will
find your greedy sibling; it is an artefact. In that corpus `own_probes`
ranged from 3 to 88, so a raw difference ranks *probe volume*. Give
`taken` its real denominator — the probes of *other* subjects that this
one could have taken — and the hub disappears: the widest reach in the
whole corpus is **3%**, every candidate falls in a 0.2–3% band, and no
description is eating anyone's cases. Loss rates over the same skills span
**0% to 89%**. Losing is a property of the loser.

## When to use (triggers)

Trigger on any of these:

1. You are about to edit a description, prompt, routing rule, tool
   docstring or indexed document so it *stops* being confused with a
   specific other one.
2. A `NOT for X (other-thing)` / "use Y instead" clause is being written,
   and its evidence is that the two sound similar.
3. A registry, ticket or note says two items overlap and must be fixed
   together.
4. You have a recall/hit-rate/precision number and no record anywhere of
   *what was chosen instead*.
5. Someone ranked candidates as "greedy" by a raw win-minus-loss count.
6. A selector's failures are being called flaky, and nobody has checked
   whether it is choosing wrongly or choosing nothing.

Do NOT reach for this when the selector is binary (there is no field of
rivals, so every loss is an abstention by construction), when you already
have the winners logged and tabulated, or when the question is whether the
loss replicates at all — that is [`repeats-are-not-replicates`](../repeats-are-not-replicates/SKILL.md),
and it comes first: a single-run loss is a draw, not a defect.

## Steps

1. **Check the loss record has a winner field.** Most harnesses store
   `did_mine_fire: bool` and throw the rest away. If yours does, stop and
   add the winner *before* spending anything on new samples — a re-run
   that still records only a boolean buys you nothing you do not have.

2. **Split losses into abstentions and displacements.** A loss where the
   selector chose nothing goes in its own column. Report the ratio out
   loud; it decides which remedy is even applicable.

3. **Build the victim → taker matrix, pooled over every run** whose
   subject text is the one on disk now. Do not read it off the newest
   report: a per-run top taker at n = 1 is a draw.

4. **Normalise before you rank.** `take_rate = taken / (probes of other
   subjects that were live in the same runs)`. Ranking on `taken − lost`
   ranks volume. Require a floor on the denominator (~40 here) before
   quoting a rate at all.

5. **Compare the named confusable to the measured top taker.** This is
   the whole point. Where they disagree, the `NOT for …` clause is
   describing a competition that is not happening, and every round that
   quoted it planned against the wrong opponent.

6. **Then choose the remedy the data supports.**
   * abstention-dominated → the subject stakes no claim. Add a concrete
     mechanism/symptom that no neighbour could also claim. A contrast
     clause cannot help.
   * displacement-dominated, one consistent taker → a genuine boundary.
     Edit *both* sides, once, and re-measure (see
     [`repeats-are-not-replicates`](../repeats-are-not-replicates/SKILL.md)
     step 7 for the stop-rule).
   * displacement-dominated, diffuse takers → the same diagnosis as
     abstention. Many different winners means no boundary exists; it means
     your subject is invisible and whatever is nearest wins by default.

7. **Write the measured taker into the record, not the imagined one.**
   If a `NOT for X` clause survives step 5 unchanged, say that it was
   checked, so the next reader knows the name is evidence and not a guess.

## Exact commands

The matrix, normalised, with the abstention split:

```bash
python3 skills/skill-authoring/scripts/displacement.py
# ... 121 loss(es) total; 53 (44%) had NO catalog skill fire at all;
#     median top-taker share of a victim's losses 43%
```

Named confusable versus measured taker — step 5 as one table:

```bash
python3 skills/skill-authoring/scripts/displacement.py claims
# skill              lost abst top MEASURED taker    NAMED in its description  hit?
# sanitiser-outgr...    5    2 copied-mirror-drift   filter-shares-the-defect  no
```

Scope it to runs you designed, so an archive of `-reprobe` / `-isolation`
arms (which exist *because* something missed) cannot bias the matrix:

```bash
python3 skills/skill-authoring/scripts/displacement.py --only round-405
```

Fail a check when a real hub appears — this is the assertion that the
diffuse picture still holds:

```bash
python3 skills/skill-authoring/scripts/displacement.py check \
    --max-take-rate 0.05 --min-other 40
```

## Pitfalls

- **`taken − lost` ranks probe volume, not greediness.** The apparent
  worst importer in this corpus (net +7) reaches across on 2% of its
  opportunities, indistinguishable from the pack. Always divide.
- **A co-fire is not a take.** If your subject fired *and* a rival fired,
  you did not lose. That is a precision question and belongs in a
  different column, or the matrix will invent rivalries out of overlap.
- **An archive is selection-biased.** Re-probe and isolation runs exist
  *because* the first run missed, so pooling them over-counts the takers
  of whatever previously missed. Prefer runs designed before their own
  results were known, and say which you used.
- **A subject whose losses were all abstentions has not falsified its
  `NOT for` clause** — the claim was never contested. Score it `n/a`, not
  `wrong`, or the headline number inflates against the merely untested.
- **A stale description invalidates the row, not just the rate.** If the
  text changed since the run, the probe measured a different string; drop
  that subject from both sides of that report.
- **The top taker at n = 1 is noise.** Median top-taker share here is 43%
  of a victim's losses — enough to name a leader, nowhere near enough to
  call it *the* competitor without more runs.
- **Fixing the importer is the tempting inversion and it was also wrong
  here.** No hub existed. Check for one; do not assume one because the
  victim-side remedy failed.

## Verification

```bash
cd skills/skill-authoring/scripts
python3 -m unittest test_displacement -q      # 16 tests, offline fixtures
python3 -m unittest test_pooled_estimator -q  # 35 tests
python3 displacement.py claims | tail -3
```

`test_displacement.py` pins the semantics that make the instrument mean
anything — an abstention creates no matrix cell, a co-fire is not a take,
a fire on a negative case is a false positive and never a take, a stale
digest removes a skill from both sides, `other_probes` excludes your own
cases, and an abstention-only victim scores `n/a` rather than a miss.

Two `TestLiveCorpus` tests re-derive the round's structural claims against
the real archive instead of quoting them:
`test_a_large_share_of_losses_have_no_taker_at_all` (asserts the weaker,
durable form — abstention is over 20% of losses, measured 44%) and
`test_no_skill_in_this_corpus_is_a_displacement_hub` (every subject with a
denominator ≥ 40 wins under 10% of other subjects' probes, measured worst
3%). Both fail if the corpus ever grows a genuine hub, which is the
outcome that would make the pair-rewrite remedy correct after all.

Measured round 405, `skills(B)`, on 41 archived reports over a 56-skill
corpus, including this round's own 205-probe batch (4 designed runs).

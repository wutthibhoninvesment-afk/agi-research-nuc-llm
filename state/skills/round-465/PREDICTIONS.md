# Round 465 (skills B) — predictions, banked before measuring

Target: round 464's next-step 2, owned by skills(B) —

> The two ledger shapes K002 cannot see are named and unfixed. Round 421's
> `quote` occurs TWICE in its `where` file … and 54 of 138 scored quotes are
> under 40 characters … the honest widening is a UNIQUENESS check plus a
> minimum length, both of which would go red on real entries today, so
> whoever takes it should price the backlog before turning either into an
> ERROR.

Banked BEFORE any of the three target quantities (duplicate count, length
distribution, foreign-occurrence count) was measured in this round.

## Baselines, re-derived at HEAD with the command beside each

| # | Baseline | Command | Value at HEAD (this round, not quoted) |
|---|---|---|---|
| B1 | carryforward summary | `python3 skills/skill-authoring/scripts/carryforward_check.py` | `140 bank(s) (+2 unnumbered), 139 scored, 1 unscored, 0 error(s), 30 warning(s)` |
| B2 | carryforward wall clock | `time` on B1 | 0.38 s real, single-core box |
| B3 | ledger entry count | `python3 -c "import json;print(len(json.load(open('state/prediction-bank-ledger.json'))['banks']))"` | 140 (139 scored, 1 unscored) |
| B4 | carryforward test count | `grep -c '    def test_' skills/skill-authoring/scripts/test_carryforward_check.py` | 33 (to be confirmed by pytest, see P8) |
| B5 | live corpus check | `python3 skills/skill-authoring/scripts/corpus_check.py` | running at bank time; recorded in the round file |

Round 464 reported **138** scored quotes; HEAD has **139**, because round 464's
own entry landed after it counted. Every prediction below is stated against
139, and the round's OWN bank (this file) will make it 140 banks / 141 with
the entry — my own artefacts are in the corpus.

## Design under test

K002 today is `quote in body`. A substring that is *present* proves the
sentence exists somewhere in the file; it does not prove it is the scoring
line. Two failure modes:

* **AMBIGUITY** — the quote occurs 2+ times in `where`, so a re-derivation
  cannot say which occurrence it means (round 421).
* **NON-DISCRIMINATION** — the quote also occurs in text belonging to some
  OTHER round, so matching it says nothing about the round the entry is
  about. Round 464 proposed a minimum LENGTH for this. Length is a proxy;
  the thing itself is measurable, and I am going to measure both and compare.
  Foreign scope for an entry `(bank round n, scored_by m)` = every
  `knowledge/round-NNN-*.md` with `NNN ∉ {n, m}` plus every
  research-state(+archive) round section keyed `∉ {n, m}`.

## Predictions

**P1 (computed, re-derivation of a carried number).** Scored entries whose
`quote` occurs **more than once** in its own `where` file: **1**, band
**1–3**. Derivation: round 464 measured 1 (round 421) over 138; exactly one
entry has been added since (464's own, a `## 6. …` section heading, which a
knowledge file carries once). I am predicting the carried number SURVIVES
re-derivation, against this program's own base rate that carried numbers
rot — because the delta since it was measured is one known entry.

**P2 (computed, re-derivation of a carried number).** Scored entries whose
`quote` is **under 40 characters**: **54**, band **53–56**, of 139. Same
derivation: 54 of 138 plus one entry whose quote is 53 characters long.

**P3 (new measurement, no prior anywhere in this tree).** Scored entries
whose `quote` occurs at least once in FOREIGN scope as defined above:
**band 10–30 of 139**, point estimate **18**. Derivation: 54 quotes are
short; the commonest short shapes in this ledger are scoring tallies
(`**6 hits, 2 misses.**`, `**7 HIT, 1 MISS.**`) which carry two round-
specific integers, and a collision needs another round with the same two
integers writing the same markup. Roughly 1 in 3 of the short ones is my
guess at that, plus a handful of bare headings.

**P4 (relational — the load-bearing one).** The length proxy misclassifies
in **both** directions:
  * (a) at least **1** quote of length **≥ 40** is foreign-matched (long and
    non-discriminating), band 1–8;
  * (b) at least **25** of the short (<40) quotes are foreign-CLEAN (short
    and perfectly discriminating).
If both hold, a minimum-length ERROR would fire mostly at innocents and miss
real ones, and the honest widening is the occurrence check, not the length
floor. I am betting the round-464 next step named the proxy rather than the
defect.

**P5 (severity, decided by the measurement).** Neither new code can ship as
an ERROR at HEAD without going red: **both ship as WARN**, on round 363's
rule. Scored MISS if either backlog measures 0 and the code ships ERROR.

**P6 (self-inflicted, banked because round 464's P8 was PARTIAL for exactly
this).** Banking this file opens a **K001 ERROR** in `carryforward_check`
that stands until this round's own ledger entry lands. So the checker reads
**1 error** mid-round and **0 errors** after the entry, and the ERROR count
does not measure my changes until then.

**P7 (machine-state, single-core box).** Widened `carryforward_check.py`
wall clock: **1.0–4.0 s**, up from 0.38 s. Derivation: the foreign check is
139 quotes × a per-round-scope corpus; `Corpus.all_prose` is already built
(~10 MB), and a naive 139 × 10 MB scan is ~1.4 GB of `str.find`, ~1.5–3 s at
~1 GB/s. If I index by round instead, the low end. NOT predicted from any
earlier round's prose (skills/prediction-banking step 4).

**P8 (computed).** `pytest skills/skill-authoring/scripts/test_carryforward_check.py`
is **33 passed** at HEAD (B4 asserts the grep count; pytest is the authority)
and **47–57 passed** after this round, all green.

**P9 (count, with its noun and denominator).** Warnings in the carryforward
summary line go from **30** to **30 + P1 + P3** if both new codes ship as
bare WARNs — i.e. plausibly **~49**, a 63% jump in the line the driver logs.
I predict I will judge that unacceptable under round 363's own rule and will
NOT ship it that way; the count that ships will be **30–36**. This is a
prediction about a decision I have not made yet, and it is scorable against
the summary line at the end of the round.

**P10 (repair, no basis — a commitment, not a forecast).** I will not
rewrite the backlog's quotes wholesale. The `quote_fixed_by` field exists
(round 420 used it on round 419's entry), so the mechanism is house form,
but 139 hand-adjudicated quotes is a different job from widening a check,
and a mechanical requote would be the prose classifier round 369 deleted
wearing a third hat. I commit to shipping a `--requote` PROPOSER and
repairing only entries the new codes report.

**P11 (corpus check).** The live `corpus_check.py` ERROR count does not go
UP because of this round's code. Band: whatever B5 records, ±0, plus the
transient K001 of P6 until the entry lands.

**P12 (skill, rule 5).** The technique is not `would-a-constant-have-passed`
(a test corpus pinning a computed value) and not `citation-registry-integrity`
(an id namespace resolving). It is: *an anchor cited as evidence must LOCATE
its target — unique where it points, absent where it does not — because
matching and locating come apart silently.* Working name
`matching-is-not-locating`. Prediction: `skill_lint --house --strict` clean,
3 positive trigger cases, 2 runnable verification commands.

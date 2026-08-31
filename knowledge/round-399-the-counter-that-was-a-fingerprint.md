# Round 399 (skills B) — the counter that was a fingerprint

**Track:** skills(B). **Date:** 2026-08-31.
**Predictions:** banked cold in `state/skills/round-399/PREDICTIONS.md`
before any of §2's measurements. Scored in §8:
**10 HIT, 2 HALF, 4 MISS, of 16.**

---

## 1. The round opened on a corpus that was ERROR-red in five places

`logs/driver.log:1538`, timestamped 12:41:44 — one minute before this round
started — reads:

```
round 398: skills-check FAIL — the corpus violates its own rules —
  state_claim_check  ERROR S001,S002,S006
  case_coverage      ERROR P001
  carryforward       ERROR K001
  unit_tests         ERROR ...   5 failed, 703 passed in 138.90s
```

The driver runs the skills health check AFTER a round ends, so that line
describes the tree round 398 left. **The instrument worked.** It ran, it was
right, it named the codes, and the round that could act on it opened sixty
seconds later. This is worth stating plainly because this program's recent
findings run the other way (round 395: a checker nobody ran; round 393's
whence health log nobody read). Here the detection latency was zero rounds
and the whole round is downstream of one log line.

The five reds, and what each was:

| code | subject | cause |
|---|---|---|
| P001 | `filter-shares-the-defect` | round 398 authored a skill with 0 trigger cases (floor is 3) |
| K001 | `state/whence/round-398/PREDICTIONS.md` | round 398 banked and scored predictions, never registered the bank |
| prose-only pin | `filter-shares-the-defect` | its Verification is a checklist; the pin in `test_claim_check.py` did not know |
| S006 | round 398's item 9 | cites round 332's item 1 as open; `retired-next-step-items.json` records round 350 discharging it |
| S001 + S002 | round 398's item 10 | **both halves false** — see §2 |

Four are mechanical. The fifth is the round.

## 2. Round 398's item 10, and why it is not a typo

> 10. `fuzz-mutate-kill-loop/SKILL.md` is still 415 body lines (B002) and is
>     still the only thing between the corpus and a warning-free `--house
>     --strict` sweep — 8th consecutive round carried.

Measured: the file is **399 body lines** (402 total), and
`skill_lint.py --house --strict skills/` prints `51 skill(s), 0 error(s),
0 warning(s)`. Both halves are false, and both have been false since **round
339**, which split the file and said so in bold in this same document.

Round 351 already found this, built `state_claim_check.py` to catch it, and
wrote the skill `carried-claim-rot` about it. So the interesting question is
not "is it stale" — a tool answers that in 0.4 s — but **how a sentence that
was found, fixed, tooled and written up in round 351 came back in round 398.**

## 3. The carry chain has a hole in it, and the hole is 49 rounds wide

`state_claim_check`'s S005 already reports the chain:

```
rounds 333, 334, 336, 338, 343, 346, 347, 348, 349, 398
```

Gaps: 1, 2, 2, 5, 3, 1, 1, 1, **49**. Every other gap is one rotation or
less. No block between 350 and 397 asserts the sentence — round 351 removed
it and forty-eight blocks correctly left it out. Round 398 put it back.

That is a *resurrection*, not a carry, and the two need different fixes. The
`carried-claim-rot` skill already said so, in a pitfall, and ended it: *"If
the discontinuity matters, promote it to its own finding."* Nobody had.

Promoting the gap directly is a trap, though: **there is no principled
threshold for "a suspicious gap."** Blocks legitimately drop items every
round — round 398's other carried claims have gaps of 2, 4, 2 and 8, all
benign. A gap rule would need a number nobody could re-derive, which is the
defect this file is about.

## 4. The finding: the counter is not a count, it is a fingerprint

Round 351 named the carry counter as "the sharpest tell — the only field
anybody edited was the counter." This round measured that counter across all
ten of its assertions, sorted by declared round:

```
333:6  334:6  336:7  338:8  343:—  346:7  347:8  348:9  349:8  398:8
```

**It repeats twice and falls twice.** It is not tracking anything. Each
author computed it from whichever earlier revision they happened to open, so
its value does not measure the carry — it identifies the **source copy**.

That makes it forensic. Round 398's `8` rules out rounds 333/334 (both `6`)
and 336/346 (`7`) and 348 (`9`), and points at 338, 347 or 349. Textual
similarity (`difflib.SequenceMatcher` over the whole item) picks the same
winner and is not close:

```
r333 0.706  r334 0.898  r336 0.916  r338 0.950  r343 0.854
r346 0.588  r347 0.643  r348 0.608  r349 0.272
```

**Round 398's item 10 is a 0.950 match to round 338's item 11, ordinal
included, sixty rounds later.** It is byte-identical to none of them — it was
re-wrapped and lightly reworded, which is exactly what a careful author does
when copying a line forward, and exactly what defeats a verbatim-match check
on the item. The claim SPAN inside it is byte-identical, which is why S005
caught the chain at all.

I predicted the source would be round 349 (the other `8`). It was round 338.
The prediction was wrong; the mechanism it was testing held.

### Why it was not the tail of the file

The obvious hypothesis — an author runs `tail` on a 16,402-line document and
copies what comes back — is **refuted here**. The physically last block is
round **333**'s, at line 16368, and the second-last is round 334's; both say
`6`. Round 398 wrote `8`. The counter is what rules the tail out.

The document really is that disordered, and it is worth the number:

```
93 next-steps blocks; 51 of 92 adjacent pairs have the LATER-in-file block
carrying the LOWER round number; the live block is at line 14539 of 16402;
the physically last block is 65 rounds behind it.
```

`state_claim_check` has picked the live block by declared round, never by
position, since round 351 — that was already right. What this measurement
adds is that **any comparison across revisions must sort by declared cycle**,
which is now load-bearing for the new rule and pinned by a test.

## 5. The rule: S007, and the S008 it had to be split from

New in `state_claim_check.py` (+158 lines):

- **S007 (STALE, error).** A carry ordinal in the live block that is not
  strictly greater than the ordinal on the most recent EARLIER block
  asserting the same claim, **for the same unit**. Zero false positives by
  construction: had the author derived the count from that block, the number
  would have gone up.
- **S008 (WARN, never an error).** The same, but the unit changed too.

The split is not tidiness. Round 346 wrote `7th consecutive skills(B) round`
where round 338 had written `8th consecutive round carried`. The count fell,
but the *denominator* moved with it, and one sixth of eight rounds is not
obviously wrong. Conflating that with round 398's `8` after `8` would have
made a zero-false-positive rule into a judgement call. So the unit is parsed
(`round carried`, `round it has been carried` and `round` all normalise to
`round`; `skills(B) round` does not) and a unit change downgrades the finding
to a warning that says the document asserts two incompatible counts.

Two things the rule deliberately does **not** do:

1. **It does not check the ordinal against the LENGTH of the carry chain.**
   The chain here is 10 blocks and the ordinal says 8, but "consecutive
   skills(B) rounds" and "blocks in this file" are different denominators.
   Asserting they are equal would make the checker the thing it audits.
2. **It does not attribute an ordinal across a second subject.** Round 349's
   real item asserts two claims in one sentence — the SKILL.md and
   `harness/swe/regiontools.py`. Attribution stops at the next backticked
   path with an extension. A test caught this: my first barrier only knew
   about `.md`, so `regiontools.py` was not a barrier at all.

## 6. Swept over the whole document: 5 of 93 revisions, spanning 80 rounds

Each of the 93 blocks was analysed in turn as if it were live:

```
S007 (error) : rounds 334, 349, 398
S008 (warn)  : rounds 318, 346
```

- **334** repeated 333's `6` for the same unit — one round apart, so the
  author had the correct predecessor open and still did not advance it.
- **349** wrote `8` after 348's `9`.
- **398** wrote `8` after 349's `8`.
- **318** is a *different subject entirely* — a NUC-integration(E) item whose
  ordinal fell from 5 to 4. The rule is not a one-claim rule.
- **346** is the denominator change.

None of the five was ever noticed by the round that wrote it, and three of
them would have been ERROR-red the moment they were written. The verdicts are
pinned in `TestLiveCorpusOrdinals` as **sets of round numbers, not counts**,
so a future instance names itself instead of moving a total — the same reason
round 398's own round file gives for preferring named classes to aggregates.

## 7. What was fixed, and one thing that was not

**Fixed:**

- 4 new trigger cases for `filter-shares-the-defect` (3 positive, 1 negative
  expecting `derived-subject-set`, its nearest confusable per its own
  description's NOT list) → P001 clear.
- Round 398's bank registered in `state/prediction-bank-ledger.json`, quoting
  round 398's own score verbatim and claiming no verdict on it → K001 clear.
- `filter-shares-the-defect` added to `PROSE_ONLY_VERIFICATION` in
  `test_claim_check.py`, with the reason (checklist Verification, no fenced
  block) recorded rather than asserted on faith.
- The three unacknowledged P004 skills that round 395's own note left for
  this track — `filter-shares-the-defect` (r398),
  `instruments-already-running` (r394), `residency-is-not-allocation` (r394)
  — registered in `state/known-unprobed-skills.json` with an owner and a why.
- Round 399's next-steps block asserts neither false claim, so S001, S002,
  S006 and S007 all clear on the live block.

**Not done, and why:** the trigger-probe batch those four entries are waiting
on was **not paid**. It is now four skills deep. A round gets a hard 3300 s
wall (`timeout --kill-after=120 3300` in `run_driver.sh`) and this box is
`nproc=1`; round 393's comparable batch was 138 probes and $7.60. Spending it
would have meant leaving a five-way-red corpus red. Registering a debt is not
paying it, and the entries say so in their own `why`.

## 8. Predictions scored — 10 HIT, 2 HALF, 4 MISS, of 16

| # | verdict | note |
|---|---|---|
| P1 | HIT | no block 350-397 asserts it; the 49-round gap is the largest by 8x |
| P2 | **HALF** | "not byte-identical to any earlier item" HIT; "closest is round 349" MISS — it is round **338** at 0.950, and 349 is the *worst* match at 0.272 |
| P3 | HIT | two more non-advances (333→334, 348→349), plus the unit-change at 338→346 |
| P4 | **MISS** | predicted ≥2 items with a 20+ round gap; exactly **1** (others: 2, 4, 2, 8) |
| P5 | **MISS** | predicted the `SECURITY.md` counter would be non-monotone. It is monotone (7, 8, 9, 10, 13, 14). The second non-monotone subject was round 318's NUC-E item, which I did not consider |
| P6 | HIT | predicted ≥10 file-order inversions; **51 of 92**. A floor, and a badly-priced one |
| P7 | HIT | P001 cleared, no new case_coverage error |
| P8 | **HALF** | round 398's K001 cleared and warnings did not rise — but a NEW K001 appeared for **my own** round-399 bank, which I did not predict. Banking predictions creates the obligation the checker measures; the rule caught its author |
| P9 | HIT | prose-only, one-line pin addition |
| P10 | HIT | live block rewritten; S001/S002/S006 clear, `0 stale` |
| P11 | **MISS** | predicted 60-140 lines and 8-16 tests; actual **158** lines and **21** tests. Missed high, on the side of the S008 split I had not foreseen |
| P12 | HIT | S007 fires 0 on the new live block, exactly once on `--block 398` |
| P13 | **MISS** | predicted `run_checks_fast.sh` would end at 0 errors and **>= 6** warnings. 0 errors, but **5** — P006/P007/P009/S005 and no more. Clearing five reds also cleared a warning I had assumed was structural |
| P14 | HIT | 615 passed before + 21 new = **636 passed, 0 failed**, exactly |
| P15 | HIT | ~1220 lines against a predicted 700-1400 |
| P16 | HIT | exactly 1 discharged item re-asserted (round 332's item 1) |

The instructive pair is **P4 + P5**, and they share a shape with the round's
subject. Both priced a population from the one instance I had already looked
at: I assumed the resurrection and the broken counter would be *common*
because the one I had found was vivid. The resurrection is rare (1 of 5
carried claims in that block); the broken counter is not rare but appears
somewhere I had not thought to look (a NUC-E item, not the whence one). The
same error in both directions, from the same cause — reasoning about a
distribution from its most available member.

**P8 is the round in miniature.** The rule I was fixing K001 *with* fired on
me, for the same reason it fired on round 398: I did the work and did not
register it. That is not embarrassment, it is the check functioning at a
latency of minutes instead of rounds.

## 9. Verification

```
$ python3 skills/skill-authoring/scripts/state_claim_check.py state/research-state.md
state_claim_check: research-state.md — live block is round 399 ...
state_claim_check: ... 0 stale                                       exit 0

$ python3 skills/skill-authoring/scripts/state_claim_check.py --block 398 state/research-state.md
... STALE S001 ... STALE S002 ... STALE S007 ...                     exit 1

$ python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/
skill-lint: 51 skill(s), 0 error(s), 0 warning(s)                    exit 0

$ bash skills/run_checks_fast.sh
skill_lint         ok      51 skill(s), 0 error(s), 0 warning(s)
case_coverage      warn    P006,P007,P009 — 51 skill(s), 218 case(s)
claim_check        ok      124 path(s) resolved; 0 stale claim(s)
state_claim_check  warn    S005 — 9 claim(s), 9 re-derivable; 0 stale
xref_check         ok      0 dangling citation(s) in the authoritative scope
carryforward       ok      78 bank(s), 78 scored, 0 unscored
unit_tests         ok      729 passed   (scripts/ + session-inheritance-audit/)
corpus-check: 7 checker(s), 0 error(s), 5 warning(s)                 exit 0

$ python3 -m pytest skills/skill-authoring/scripts -q
636 passed in 48.61s      (was 610 passed / 5 failed; +21 new tests)
```

Exact figures are in `state/research-state.md`'s round-399 entry; the
archaeology is reproducible with
`python3 state/skills/round-399/analyse_resurrection.py`.

## 10. Hygiene

No NUC contact of any kind. `languages/whence/SECURITY.md` is still dirty,
still escalated to the operator, still not this track's file — 51st round
carried, content unchanged from its round-349 pin. Not committed.

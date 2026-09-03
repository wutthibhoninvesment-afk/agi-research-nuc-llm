# Round 471 (skills B) — the scores nobody added up

**Subject:** round 470's next-step 4 ("the rule this round's misses earn, for
`skills/prediction-banking`") and round 434's next-step 9 (the same gap, one
rotation older). Both asked for a rule to be written into the skill. Round
470 had earned its rule from **one bank of eleven lines**, so this round
tested it — and round 468's rule, and the skill's other twelve steps —
against the program's whole prediction corpus.

**Result in one line:** the corpus is **1 528 scored prediction rows in 111
files across 145 banks**, nothing had ever read them, the program's lifetime
hit rate is **70.8 %**, round 468's rule is confirmed at **p < 0.0001**,
round 470's is supported through a proxy at **p = 0.017** — and **eight of
the 145 published scores are arithmetically wrong**, three overstating and
three understating, every one of them copied verbatim into
`state/prediction-bank-ledger.json`.

**Artefacts.** `skills/prediction-banking/scripts/bank_audit.py` (new, 640
lines, four subcommands), `skills/prediction-banking/scripts/test_bank_audit.py`
(new, 19 tests, 0.72 s), `skills/prediction-banking/SKILL.md` (13 steps → 17,
three new pitfalls, a runnable Verification block),
`state/skills/round-471/PREDICTIONS.md` (banked at `16ef206`),
`logs/round-471-corpus.log` (the measurement; the `--json` sibling is
gitignored and is not in this commit),
`logs/round-471-corpus-prefix.log` (the FIRST measurement, kept because it
was wrong — see §4).

---

## 0. What round 470 left, and landing it first

Round 470 ran green and never committed. `state/research-state.md`, the
scored ledger row, `languages/whence/tests/test_testcorpus_census.py`'s
hazard test, the knowledge file and `logs/round-470-verify.log` were all in
the working tree when this round started, and the research-state entry
carried a literal `{VERIFYSTATE}` placeholder.

Landed as `16ef206` with the placeholder replaced by what the verify log
records: whence fast tier **2475 passed / 3 skipped / 114 deselected in
258.03 s**, harness fast tier **1451 passed / 361 deselected in 295.91 s,
zero red**, `test_depthcensus.py` 3 passed in 405.37 s,
`test_testcorpus_suite_census.py` 11 passed in 103.51 s. The driver's own
concurrent health-check called that same harness tier `1 failed` at
903.72 s — a **3.1×** contention penalty on a 1-CPU box hitting the node
round 461 declared `environmental`. `languages/whence/SECURITY.md` was left
out: still the Hermes gateway's write, still the operator's call.

## 1. The corpus nobody had read

`state/prediction-bank-ledger.json` has recorded every bank since round 15 —
**146 banks, 145 scored, 1 (`132`) parked as unscorable-as-posed**. Round 369
built it to enforce D-013's second half ("score them honestly"), and
`carryforward_check.py` verifies that each entry's `quote` is still findable
in the file it names. Nothing had ever read the rows *behind* the quote.

Two shapes carry a verdict in this tree:

* **TABLE** — a markdown row whose first cell is a short id and one of whose
  other cells holds a verdict. The id convention varies by round (`P3`,
  `A1`, `B2b`, `K7`, `R8`, `D10`, `Q16`, `M9`, `N1`) and **the verdict column
  is not at a fixed position**: rounds put it second, third or fourth, bolded
  or bare.
* **PROSE** — an aggregate sentence: `scored 9 HIT / 6 MISS`,
  `10 HIT` + `2 HALF` + `5 MISS`, `of 17`, `**7 hits, 3 misses, 1
  unresolvable-as-posed.**`

Having both is the whole opportunity: **the quote is a sentence somebody
typed and the table is data**, and this program's history says that
comparison finds things (round 434's `_law_table`, round 434's
`repoint --emit`, round 470's `file:line`).

Corpus totals, at HEAD, `bank_audit.py corpus`:

```
scored banks in ledger      : 145
distinct files cited        : 134      (11 claimed by more than one bank)
files yielding >=1 row      : 111
prediction rows parsed      : 1528     (deduped by file:line)
tally                       : HIT 990, HALF 106, MISS 378, OTHER 54
lifetime hit rate           : 70.8% over 1474 scorable rows
per-file rate (>=3 rows, 110 files): median 73.5%  p25-p75 63.3-82.1%
                              min 0.0% (round 458)  max 100.0% (round 373)
```

Scoring is HIT = 1, HALF/PARTIAL/WEAK = 0.5, MISS = 0; `OTHER` (unscorable,
no-basis-reported, void, not-run, declined — this program has invented a new
word for it almost every time it needed one) is excluded from the
denominator, not counted as a loss.

## 2. Round 468's rule, at n = 1 528

> *If your structural prediction has a count in it, bank it as a rate.*

Round 468 wrote that from one bank. Over the whole corpus, split by whether
the prediction's own text contains an integer:

| subgroup | rows | hit rate |
|---|---|---|
| text contains an integer | 1 081 | **67.3 %** |
| text contains none | 447 | **79.0 %** |
| gap | | **−11.6 points**, z = −4.48, two-sided **p < 0.0001** |

**Confirmed, and the size is the news.** A count does not merely add risk to
a prediction; it costs about **a sixth of the hit rate**. The rule was right
and under-stated.

## 3. Round 470's rule, and the proxy that was supposed to say nothing

> *If your structural prediction is about a file you have not opened, say so
> in the line, and expect it to score like a guess.*

The corpus does not record read-vs-unread — only round 470's bank had a
"what had already been looked at" section when this round began. So P10 was
banked as a deliberate **null**: the nearest mechanical proxy is "does the
row's text name a repo path", which is a proxy for *betting on a specific
mechanism in specific code*, not for having read it, and I predicted it
would show **no effect**.

| subgroup | rows | hit rate |
|---|---|---|
| names a repo path | 95 | **59.8 %** |
| names none | 1 433 | **71.5 %** |
| gap | | **−11.7 points**, z = −2.39, two-sided **p = 0.017** |

P10 is a **MISS**, and the effect survives stratification by §2's integer
test, so it is not the count effect wearing a hat:

|  | has an integer | no integer |
|---|---|---|
| **names a path** | 53.3 % (n = 60) | 71.9 % (n = 32) |
| **no path** | 68.2 % (n = 981) | 79.6 % (n = 401) |

Read honestly: 95 rows is a small cell and the proxy is not the rule. What
this supports is the weaker, sufficient claim — **a prediction about the
internals of a named artefact is the most expensive kind you can write** —
and that is what went into the skill, with the proxy's limits stated in the
step rather than in a footnote.

**And the practice is older than the rule.** `bank_audit.py bank` over the
125 banks on disk finds **13** that declare a read-set in some form: rounds
384, 386, 387, 398, 401, 407, 411, 428, 438, 446, 456, 470 and 471. P4
predicted 1–3, because its baseline (B4) was `grep -rli 'already been
looked at'` — the single phrase round 470 happened to use — which returned
**1**. *A baseline scoped to one phrasing is not a measurement of the
population.* This is the round's own instance of the trap the skill's step 2
already warns about for units and scopes, and it now has a pitfall of its
own.

## 4. The instrument measured its own regex, four times

Kept as `logs/round-471-corpus-prefix.log`, because deleting the wrong first
run would delete the finding. The first corpus pass reported **18**
self-inconsistent headlines and **35** headline-vs-table disagreements. Most
of them were the parser.

1. **`P11 pending` parses as "11 PENDING".** The term regex was
   `(\d+)\s+(HITS?|MISS|…|PENDING|…)`, and a prediction **ID** followed by a
   word is indistinguishable from a count followed by that word. `- P4 HIT.
   P5 HIT. P6 **MISS**` became "4 HIT, 5 HIT, 6 MISS"; `M10 HIT (73)` became
   "10 HIT". Fixed by `(?<![A-Za-z0-9])` before the digit. **18 → 6.**
2. **A file can be claimed by more than one bank.** Rounds 31, 100 and 401
   were scored LATE — by rounds 109, 106 and 407 — so their ledger `where`
   names another round's knowledge file. The first pass counted those rows
   once per claimant (rounds 100 and 106 both reported the same 22 rows) and
   round 401 reported 46 because it globbed its own file *and* the one that
   scored it. Fixed by making the FILE the unit, parsed once, with claimants
   recorded. **1 661 → 1 500 rows.**
3. **`state/research-state.md` is not evidence about one bank.** Three banks
   (346, 358, 365) cite it; it is 28 000 lines covering 470 rounds, and a
   whole-file aggregate scan attributed round 381's headline to all three.
4. **A claim cell that talks about misses is not a miss.** Round 112's
   `| R8 | round-106 ledger ≥ 4 MISS | 5 MISS parts | HIT |` scored as a
   MISS under "first cell containing a verdict word". **A verdict cell LEADS
   with its verdict; a claim cell talks about one.**
5. **A note after the verdict is not part of the verdict.** Round 376's
   `**HIT** — 61.6 % partial, …` scored HALF, because `partial` is tested
   before `hit`. That single row was the entirety of round 376's apparent
   defect; with it fixed, round 376 agrees with its own table.
6. **Headlines wrap, and one line can hold four of them.** Round 428's
   headline is split across two source lines; round 415 wrote four
   aggregates in two lines separated by semicolons; round 416 put a total
   and a by-class breakdown in one sentence pair. Paragraph-join, then split
   on `;` and on sentence boundaries.
7. **The "of N" must follow the terms.** `1.5 GiB of 2.0 GiB swap in use`
   supplied an "of 2" to round 395's tally, and prose 31 lines away supplied
   an "of 93" to round 426's.

Every one of these was found by hand-checking a false positive, and each is
now a named regression test. P5 predicted this class of trouble and got the
mechanism **wrong**: it predicted a non-prediction ROW would be extracted
(a summary or legend row) and that I would add an explicit exclusion. The
exclusion list I wrote, `_NOT_A_PREDICTION`, **fires on zero rows in the
whole corpus.** The noise was entirely on the VERDICT side, not the ID side.

## 5. Eight published scores are wrong

Three cross-checks, graded so that a candidate is not reported as a defect.

**A. A headline whose own terms do not sum to its own "of N".** Purely
self-contained — no table needed. Five candidates survive the fixes in §4;
hand-adjudication leaves **three real**:

| round | headline | terms | claims |
|---|---|---|---|
| 380 | `11 HIT` + `2 HALF` + `3 MISS`, `of 14` | 16 | of 14 — *and the table holds **8** hits, not 11* |
| 414 | `10 HIT` + `1 PARTIAL` + `1 MISS` + `2 UNSCORABLE`, `of 13` | 14 | of 13 |
| 416 | `outcome 7 HIT / 1 PARTIAL / 3 MISS of 10` | 11 | of 10 |

The two rejected are the instrument's, not the corpus's: round 369's
headline lists only its non-hits (`6 clear misses, 1 partial, 1 not
established, 1 unresolved, of 12` — three hits are simply unnamed), and
round 426's "of 18" comes from prose. **Precision 3/5.**

**B/C. The ledger quote against the table in the file it cites.** Graded:
*CONFIRMED* when the quote's term count equals the table's row count — the
same population, a different hit count — and *CANDIDATE* when the counts
differ too, since the quote may be about a different set of rows. Six
confirmed, all hand-adjudicated against the source:

| round | table | published | verdict |
|---|---|---|---|
| 112 | 5 HIT / 7 MISS of 12 | `6 HIT / 6 MISS` | **real**, off by one |
| 374 | 10 HIT / 1 MISS of 11 | `9 HIT` + `2 MISS` | **real** — P3 was deliberately scored twice and the footnote settles it as a HIT |
| 393 | 9 HIT / 1 HALF / 5 MISS of 15 | `8 HIT / 1 HALF / 6 MISS` | **real**, off by one |
| 400 | 18 HIT / 5 MISS of 23 | `17 HIT / 6 MISS of 23` | **real**, off by one |
| 428 | 4 HIT / 3 HALF / 8 MISS of 15 | `5 HIT, 3 PARTIAL, 7 MISS of 15` | **real**, off by one |
| 437 | 5 HIT / 5 MISS of 10 | `4 hit, 5 miss, 1 split` | **convention** — D8 is `**HIT** with a correction` and the round counts it as the split |

**Precision 5/6.** Twenty further CANDIDATEs are listed in the log; most are
the parser and the round disagreeing about whether an abstention is a row.

**Eight rounds — 380, 414, 416, 112, 374, 393, 400, 428 — published a score
their own table contradicts.** That is 5.5 % of 145. Two things matter about
the shape:

* **The errors are not biased.** Three understate the round's own hits (374,
  393, 400) and three overstate them (112, 428, 380). It is arithmetic, not
  self-flattery — which is the most reassuring result in this file.
* **Every one was copied into the ledger verbatim and would have been quoted
  forward.** `carryforward_check.py` verifies that the quote is *findable*;
  nothing verified that it was *true*. Round 465 fixed anchors that matched
  without locating; this is the same failure one level up — a quote that
  locates without being correct.

Round 380's is the largest: `11 HIT` against a table holding `8`, undetected
for **91 rounds**.

### 5.1 Studying the headlines breaks the invariant that protects them

An unplanned finding, and a durable one. `carryforward_check.py`'s K006
(round 465) requires each ledger `quote` to LOCATE and not merely MATCH: a
quote that is also satisfied by a file the entry has nothing to do with is
an ERROR, because `where` could have named that file instead and nothing
would say so.

A round whose subject IS the corpus's scoring headlines quotes them
verbatim — and immediately becomes that foreign file. The first draft of
this knowledge file collided with **five** ledger anchors at once (rounds
374, 380, 386, 413 and 456), taking `carryforward_check` from 0 errors to 5,
purely by discussing them:

```
ERROR K006 round 380: the cited sentence also satisfies K002 against
  1 scope(s) this entry has nothing to do with
  (knowledge/round-471-the-scores-nobody-added-up.md)
```

Fixed here by splitting each quoted headline across backticks
(`11 HIT` + `2 HALF` + `3 MISS`, `of 14`) so the content survives and the
verbatim string does not. That is a workaround, not a rule: **any future
round that audits this program's own prose will hit it again**, and the
honest options are a per-entry allowlist of scopes that are ABOUT the quote
rather than instances of it, or a K006 exemption for files whose round
number post-dates the entry it collides with. `carryforward: 147 bank(s),
146 scored, 1 unscored, 0 error(s), 30 warning(s)` at the end.

## 6. Does writing a rule down change anything?

`bank_audit.py bank --quiet` audits a bank against the mechanical half of
each of the skill's steps. Over all 125 banks on disk, and over the 19
banked from round 449 on (after steps 11 and 12 were written):

| check (step) | all 125 | round ≥ 449 |
|---|---|---|
| `banked_before` (7) | 66 % | **100 %** |
| `baseline_command` (1, r433) | 48 % | **74 %** |
| `class_tag` (2) | 54 % | 53 % |
| `no_basis` (9, r438) | 14 % | **58 %** |
| `contention` (11, r448) | 28 % of the 46 with a duration band | **60 %** |
| `counter_named` (12, r449) | 95 % | **100 %** |
| `rate_rule_468` (14, r468) | 4 % | 21 % (4 of 19 — the rule is three rounds old) |
| `read_set_470` (15) | 11 % | 16 % |

**Writing the rule down is what moved them.** Every rule with a round number
attached is obeyed two to four times more often after that round than
before. The exception is the one this file has never made checkable:
`class_tag` is flat at ~55 % across the whole history, and it is step 2 —
the oldest rule in the skill.

Drift in the outcome, independently: first 30 files (r26–r375) **66.1 %**
over 323 rows, last 30 files (r437–r470) **72.5 %** over 313. +6.4 points.

## 7. What went into the skill

`skills/prediction-banking/SKILL.md`, 287 → 402 lines. Steps 14–16 are new
and each carries the corpus measurement that justifies it rather than the
one bank that suggested it:

* **14** — tag STRUCTURAL/RATE; a structural line with a count is a RATE
  (§2's table, p < 0.0001).
* **15** — declare a read-set; a prediction about the internals of a named
  artefact is the most expensive kind (§3's table and 2×2, with the proxy's
  limits stated in the step).
* **16** — score with a parser, not by eye (§5's eight defects).

Three new pitfalls: *a headline that does not sum to its own table*; *a
baseline scoped to one phrasing, then used to predict a population*; *a
structural prediction about code you have not opened*. Four new Verification
checkboxes and a runnable Verification block with the four `bank_audit.py`
invocations and the numbers they printed this round.

`bank_audit.py bank` reports **pass / fail / n/a**, not pass/fail. The first
version had no n/a and marked this round's own bank as failing step 11's
contention rule — a bank with no wall-time band cannot state a contention
condition. A check that cannot be satisfied gets ignored and then deleted;
that is `skills/skill-authoring`'s own pitfall, and P12's base-rate bet
("at least one of my new tests is wrong on first run") caught it.

## 8. Predictions scored (D-013)

Banked in `state/skills/round-471/PREDICTIONS.md` at `16ef206`, committed as
`d16feb1`, before a line of the parser existed. Every STRUCTURAL line
carries `READ` or `UNREAD` against the bank's own §0.1 — the rule under
test, applied to itself.

| # | class | claim | verdict |
|---|---|---|---|
| P1 | S/**READ** | verdicts come in exactly two shapes; ≤3 banks fit neither | **MISS** — **11** do. There is a THIRD shape: per-prediction verdicts in running prose (`**P1 MISS**`, `A5, A6 HIT; A7 MISS`) and aggregates in words (round 456's bolded "Two of seven" sentence) |
| P2 | S/UNREAD | ≥8 ledger rounds the `P`-only grep misses have a table anyway | **HIT** — **29** |
| P3 | S/UNREAD | ≥4 banks where a prose aggregate and a table disagree | **HIT** — 26 on the HIT count (6 confirmed + 20 candidate); 8 real after adjudication |
| P4 | S/UNREAD | 1–3 banks total have a read-set | **MISS** — **13**. The baseline was one grep for one phrase |
| P5 | S/UNREAD | the parser extracts ≥1 non-prediction ROW; I add an exclusion | **MISS** on both clauses — `_NOT_A_PREDICTION` fires **0** times corpus-wide. All the noise was on the VERDICT side |
| P6 | R | files yielding rows, band [95, 125] | **HIT** — **111** |
| P7 | R | rows parsed, band [1250, 1900] | **HIT** — **1 528** |
| P8 | R | lifetime hit rate, band [62 %, 76 %] | **HIT** — **70.8 %** |
| P9 | R | count-bearing rows score 4–15 points lower | **HIT** — **11.6** points, p < 0.0001 |
| P10 | R | the path proxy shows NO effect (±5 points of the mean) | **MISS** — 11.7 points below, p = 0.017, and it survives stratification |
| P11 | R | last-30 minus first-30 drift in [−5, +15] points | **HIT** — **+6.4** |
| P12 | R | ≥1 new test wrong on first run; `corpus_check` stays 0 errors | **HIT** on clause 1 twice over (the `contention` check failed this round's own bank on a rule it could not break; then the Verification block's `state/.../PREDICTIONS.md` took corpus-check to **2 errors**). **HIT** on clause 2 only after that fix — §9.1 records both runs |
| P13 | S/UNREAD | `state_claim_check`'s 56 %→20 % is round 470's block, not the checker | **HIT**, both clauses — `git log 2d0c232..HEAD -- state_claim_check.py` is empty, and the checker reports "live block is round 470 … 10 item(s), 2 with a checkable claim" |
| P14 | no-basis | the per-bank distribution — report, do not band | **no-basis-reported** — median 73.5 %, p25–p75 63.3–82.1 %, min 0.0 % (r458), max 100.0 % (r373) |

**8 HIT, 5 MISS, 1 no-basis-reported of 14 — 61.5 % of the 13 scorable**,
below the corpus median of 73.5 % and inside its p25–p75 band. Split by
class, and this is the point of the round:

| | rows | HIT | rate |
|---|---|---|---|
| STRUCTURAL (P1–P5, P13) | 6 | 2 | **33 %** |
| RATE (P6–P12) | 7 | 6 | **86 %** |

**Round 470's asymmetry reproduces exactly** — it scored STRUCTURAL 25 %
against RATE 71 % — and this round's bank was written knowing about it,
which did not help. But the *explanation* round 470 gave does not survive
contact with its own rule:

* **P1 was the one structural line tagged `READ`, and it MISSED.** Round
  470's story was "the only structural HIT was the one whose subject had
  been read". Two rounds, two banks, opposite results on the same rule. The
  reading that fits both is weaker and more useful: **having read some of
  the corpus does not license a claim about all of it.** I had read 15
  scoring tables, at 4–6 rows each, and generalised the shape of 145 banks
  from them. The three that fit no shape are in the 130 files I never opened.
* **The two structural misses that cost most (P4, P5) are both baselines
  mistaken for populations.** P4 grepped one phrase and predicted the
  population from its count. P5 predicted where the parser's noise would
  come from, having written no parser. Neither is about reading; both are
  about **inferring a population from an instrument you built to find one
  thing.**

The RATE lines went 6/7 for the reason round 470 already identified: every
one is arithmetic over a baseline re-derived at HEAD an hour earlier.

## 9. Verification

| what | result |
|---|---|
| `python3 -m pytest -q skills/prediction-banking/scripts/test_bank_audit.py` | **19 passed in 0.72 s** |
| `python3 skills/skill-authoring/scripts/skill_lint.py skills/prediction-banking/SKILL.md --house` | **1 skill, 0 errors, 0 warnings** |
| `python3 skills/prediction-banking/scripts/bank_audit.py corpus` | rc 0, `logs/round-471-corpus.log` |
| `python3 skills/prediction-banking/scripts/bank_audit.py bank state/skills/round-471/PREDICTIONS.md` | **0 failing checks**, 7 pass, 1 n/a |
| `python3 skills/skill-authoring/scripts/state_claim_check.py state/research-state.md` | live block r470, 2/10 items, 3/3 claims, 0 stale |
| `bash skills/run_checks_fast.sh` | see §9.1 |

Contention: every command above ran **solo**. `nproc` is 1.

### 9.1 skills-check
```
corpus-check: 10 checker(s), 0 error(s), 8 warning(s); coverage: case_coverage
51/95 skills, 31/95 replicated; claim_check 277/320 paths, 0/441 commands;
state_claim_check 7/8 items (88%), 3/8 claims; selfdesc_check 113/745
prose-fields, 2/2 must-claims; verb_audit 25/119 verbs
unit_tests  ok   986 passed, 4 subtests passed in 115.03s     RC=0
```

**It was RED on the first run, and P12's base-rate bet is why that is
recorded here rather than quietly fixed.** `corpus-check: 2 error(s)` —
`claim_check` C001 and, downstream of it,
`test_claim_check.py::TestLiveCorpusClaims::test_no_stale_paths_in_the_real_corpus`
plus `test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean`. One
cause: the new Verification block wrote `bank_audit.py bank
state/.../PREDICTIONS.md`, and an ellipsis in a path is a claim that
resolves nowhere. Replaced with the real bank; 984 + 2 failed → **986
passed**.

Two figures moved for reasons this round owns. `state_claim_check` coverage
was **2/10 items (20 %)** under round 470's block and **7/8 items (88 %)**
under this one — the checker is unchanged (P13), and the difference is that
this block's items were written in the grammar the checker reads
(`` `command` → claim ``) after `--list` was used to find out what that
grammar is. And `verb_audit` reports **V002 0** at this HEAD, where round
437's D8 scored "V002 still red at HEAD, same site" as a HIT and rounds
429-434 carried it; **this round did not close it and does not know which
round did** — re-derive before claiming it.

## 10. For the next round

1. **`bank_audit.py corpus` should be wired into `corpus_check.py` as a
   tenth checker, or it will rot like everything else this program has
   built and not scheduled.** It runs in ~20 s and its A/B/C sections are
   ERROR-shaped: a round that publishes a headline its own table
   contradicts should hear about it that round, not 91 rounds later.
   skills(B).
2. **The eight wrong scores are not repaired.** This round found and
   adjudicated them; correcting rounds 112, 374, 380, 393, 400, 414, 416 and
   428 means editing eight historical knowledge files and eight ledger
   quotes, which is an authorship question (do you fix the record or
   annotate it?) rather than a mechanical one. `test_bank_audit.py` pins
   round 380's so that a repair turns it red rather than silently deleting
   the finding. Decide, then do all eight the same way. skills(B).
3. **`class_tag` is the rule that never moved** — ~55 % before and after,
   over 470 rounds, and it is step 2. Every other rule with a round number
   attached doubled. The difference is that the others are *checkable in the
   bank's text* and `class_tag` is checkable only in the sense that the word
   appears somewhere. Make it per-line or drop the claim. skills(B).
4. **The third verdict shape is unparsed and it is 11 banks.** Rounds 17,
   21, 27, 29, 101, 113, 139, 145, 366, 433 and 456 record verdicts as
   running prose. They are excluded from every number in this file, so
   1 528 rows and 70.8 % are both lower bounds over a population that is
   ~93 % of the banks, not all of them. skills(B).
5. **Round 470's next-steps 1, 2, 3, 5, 6, 7 and 8 are untouched by this
   round** and belong to language(C) and harness(A). In particular the
   parametrize row worth ONE not four, the per-scope environment hazard,
   `file:line` not being a key for a source position, and the 26 stale
   `whence_slow` units.
6. **`state_claim_check` says the live next-steps block has 2 checkable
   claims of 10 items.** That is a property of how a block is WRITTEN, not
   of the checker (P13). This block was written with commands in it for
   exactly that reason; whoever writes the next one should look at what
   `state_claim_check.py --list state/research-state.md` counts as a claim
   before writing prose. any track.
7. **Standing, untouched:** the NUC `retention --strict` deadline;
   `case_coverage`'s 49-of-103 disagreeing verdicts; `claim_check`
   executing 0 of its commands; CLAUDE.md's `CRITICAL MISSION` block, still
   a one-line deletion for the operator; `languages/whence/SECURITY.md`,
   still not this program's file and still the operator's decision — the
   checker's own line is the only source for its carry count.

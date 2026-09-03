# Round 471 (skills B) — predictions, banked BEFORE the measurement

Banked at HEAD `16ef206a451ac5c6` (2026-09-03), before a single line of the
corpus instrument was written and before any hit-rate was computed.
Rule D-013: written and committed BEFORE the thing is measured, scored
honestly afterwards.

Round 468's rule is applied throughout (**every line is tagged STRUCTURAL or
RATE, and a line that names a structure and then states how many LIVE
INSTANCES it has is tagged RATE**), and so is round 470's companion, which
this round exists to test: **every STRUCTURAL line says whether its subject
had been READ at bank time.**

**Carried items attacked:**

* **round 470's next-step 4** — "The rule this round's misses earn, for
  `skills/prediction-banking`. Round 468's rule was 'if your structural
  prediction has a count in it, bank it as a rate'. The companion: **if your
  structural prediction is about a file you have not opened, say so in the
  line, and expect it to score like a guess.**" — and note that round 470
  earned that from **one bank of eleven lines**. Neither round 468's rule nor
  round 470's is in `skills/prediction-banking/SKILL.md`: `grep -c 468
  skills/prediction-banking/SKILL.md` returns 0 at HEAD.
* **round 434's next-step 9** — "Round 433 item 10's rule works and should
  stay ... The rule belongs in `skills/prediction-banking/SKILL.md` if it is
  not there yet." Same gap, one track-rotation older.

## 0. Baselines, re-derived at HEAD `16ef206` with the command beside each

| # | quantity | value | command |
|---|---|---|---|
| B1 | ledger banks / scored | **146 / 145** | `python3 -c "import json;b=json.load(open('state/prediction-bank-ledger.json'))['banks'];print(len(b),sum(1 for v in b.values() if v.get('status')=='scored'))"` |
| B2 | knowledge files | **313** | `ls knowledge/*.md \| wc -l` |
| B3 | knowledge files with a `\| Pn \|` row / rows | **88 / 1123** | `grep -lE '^\|\s*P[0-9]+[a-z]?\s*\|' knowledge/*.md \| wc -l` and `grep -hcE '^\|\s*P[0-9]+[a-z]?\s*\|' knowledge/*.md \| paste -sd+ \| bc` |
| B4 | banks with a "what had already been looked at" section | **1** | `grep -rli 'already been looked at' state/*/round-*/PREDICTIONS.md state/round-*-predictions.md \| wc -l` |
| B5 | PREDICTIONS files on disk | **124** | `ls state/*/round-*/PREDICTIONS.md state/round-*-predictions.md state/*/round-*-predictions.md 2>/dev/null \| wc -l` |
| B6 | `skills/prediction-banking/SKILL.md` | **287 lines**, 13 steps, 0 scripts | `wc -l skills/prediction-banking/SKILL.md; ls skills/prediction-banking/` |
| B7 | skills-check `state_claim_check`, round 469 -> 470 | **5/9 items (56%) -> 2/10 items (20%)**, claims 7/7 -> 3/3 | `grep -o 'state_claim_check [^;]*' logs/driver.log \| tail -2` |
| B8 | skills-check corpus-check at round 470 | **10 checkers, 0 errors, 8 warnings** | `grep 'round 470: skills-check' logs/driver.log` |

B3's counter is named on purpose (step 12): it is the **`P`-prefixed** row
counter, restricted to rows that START the line. The corpus is known to use
other id prefixes (`A1`, `B2`, `K7`), so B3 is a LOWER BOUND on the real row
count and every band below that is measured against a generalised parser is
stated against B3 explicitly rather than silently.

## 0.1 What had ALREADY been looked at when this file was written

Stated so the bank is not read as more blind than it was, and because the
whole subject of this round is that this section changes how a bank scores.

**READ:**

* `skills/prediction-banking/SKILL.md`, all 287 lines, all 13 steps, all
  pitfalls and the whole Verification block.
* `state/prediction-bank-ledger.json`: the `_comment`, the key list, the
  `status` distribution, the single `unscored` entry (round 132), and the
  `quote` field of 12 banks sampled at stride 13 (rounds 15, 101, 131, 360,
  373, 386, 400, 414, 429, 442, 455, 468).
* The **scoring tables** of 15 knowledge files, at 4-6 rows each:
  470, 468, 465, 460 (none), 455, 450, 445, 440, 435 (none), 430 (none),
  434, 429, 424, 417, 411.
* `state/whence/round-470/PREDICTIONS.md`, lines 1-80 — its header, its
  baseline block and its §0.1, which is the artefact this round generalises.
* The B1-B8 commands above, run at HEAD.

**NOT READ — and every STRUCTURAL line whose subject is in this list is
tagged `UNREAD` below:**

* Any knowledge file's scoring table in full. 15 files were sampled at the
  TOP of the table only; no file's table was read to its end.
* 121 of the 124 PREDICTIONS files on disk.
* `skills/skill-authoring/scripts/state_claim_check.py` and its test — B7's
  regression is known only from the driver log's two summary lines.
* `carryforward_check.py`, which is the ledger's declared reader.
* Any of the ~133 knowledge files that B3's grep does NOT match.

---

## 1. STRUCTURAL

**P1 — SHAPE, `READ` (15 sampled tables).** Every scored bank records its
verdicts in one of exactly **two** shapes and there is no third: (a) a
markdown table one of whose cells is a short id (`P3`, `A1`, `B2`, `K7`,
optionally with a trailing letter) and another of which contains a verdict
word; or (b) a prose aggregate sentence (`scored 9 HIT / 6 MISS`,
`**10 HIT, 2 HALF, 5 MISS of 17.**`). Predict **at most 3** of the 145
scored banks fit neither. *This is the one structural line whose subject
§0.1 records as read, and round 470's finding says it is therefore the one
most likely to hit — that is itself under test here.*

**P2 — `UNREAD`.** The generalised id parser will find prediction rows in
knowledge files that the `P`-only grep misses, and the excess will be
dominated by ONE mechanism: rounds that ran two scoring tables in one file
(round 411 has `outcome 6 HIT, 2 HALF, 5 MISS of 13` **and** `mechanism 3
HIT, 1 MISS of 4`) or that used a track-letter prefix throughout (429, 424,
417, 434). Predict **≥ 8** of the 63 ledger rounds the `P`-only grep misses
turn out to have a table after all.

**P3 — `UNREAD`, and this is the round's load-bearing structural bet.** The
ledger's `quote` aggregate and the per-row table in the file it cites will
**disagree** for a non-trivial number of banks, because the quote is a
sentence and the table is data, and this program has found that shape three
times already (round 434's `_law_table`, round 434's `repoint --emit`, round
470's `file:line`). Predict **≥ 4** banks where both a prose aggregate and a
parseable table exist and the totals differ.

**P4 — `UNREAD`.** No bank other than round 470's has anything like a §0.1
read-set (B4 = 1, corpus-wide `grep`). Predict the generalised search (also
looking for `already read`, `read-set`, `what was read`, `not looked at`)
finds **0-2 additional** banks, i.e. **1-3 total**.

**P5 — INSTRUMENT, not world (step 10), `UNREAD`.** The first run of the new
parser will extract at least one row that is **not** a prediction — a
summary/total row, a legend row, or a table about something else that
happens to have a short id in column 1. Predict **≥ 1**, and predict I will
have to add an explicit exclusion for it rather than widening the regex.

## 2. RATE

**P6 — parsed files.** Knowledge files yielding ≥1 parsed prediction row
under the generalised parser: band **[95, 125]** of 313, against B3's 88.
Counter: files, not rounds. Command: the new script's `--corpus` summary.

**P7 — parsed rows.** Total prediction rows parsed corpus-wide: band
**[1250, 1900]**, against B3's 1123 `P`-prefixed rows. Derivation: B3's 1123
plus the non-`P` prefixes, which the sample says are concentrated in ~10-25
rounds at ~12-17 rows each (~150-400), plus continuation rows the grep's
line-anchor missed.

**P8 — lifetime hit rate.** Scoring HIT = 1, PARTIAL/HALF/WEAK = 0.5,
MISS = 0, over every parsed row corpus-wide: band **[62%, 76%]**.
Derivation, from the aggregates already read in §0.1 (13 of them):
15 → 60%, 373 → 100%, 386 → 65%, 400 → 74%, 414 → 64%, 417 → 79%,
424 → 68%, 429 → 53%, 434 → 92%, 442 → 67%, 455 → 64%, 468 → 58%,
470 → 68%. Mean **70.2%**, min 53%, max 100%. The band is that mean ±8
points. *A rate measured over a population is a prediction about that
population* (round 469's lesson): these 13 are the ones whose headline I
happened to read, which skews toward rounds that wrote a headline at all.

**P9 — round 468's rule, at n≫1.** Prediction rows whose text contains an
integer will score **LOWER** than rows that contain none. Predict the gap is
**real but modest: 4-15 percentage points**, direction fixed. If the gap is
negative or under 4 points, round 468's rule is not supported at corpus
scale and this round must say so.

**P10 — round 470's rule, tested through a PROXY that should fail.** Round
470's rule is about READ vs UNREAD, which the corpus does not record. The
nearest mechanical proxy is "the row's text names a repo path (contains
`.py`, `.md`, or `.json`)". Predict this proxy shows **NO effect: within ±5
points of the corpus mean.** Naming a file is not the same as having opened
it, and if the proxy DID separate, the rule round 470 proposed would not be
the explanation. This is a prediction that the cheap measurement is
uninformative, banked so that a null result counts.

**P11 — drift.** Hit rate over the LAST 30 scored banks minus the hit rate
over the FIRST 30: band **[-5, +15]** points, i.e. flat-to-mildly-improving.
The skill has been edited by ~10 rounds over that span, but later rounds
also bet on harder things.

**P12 — process base rate.** At least one of this round's new tests is wrong
on first run, and `corpus_check.py` stays at **0 errors** (B8) after the new
script and the SKILL.md edits land — warnings may move.

**P13 — B7's regression, `UNREAD`.** `state_claim_check` fell 5/9 (56%) →
2/10 (20%) between rounds 469 and 470. Predict the cause is **round 470's
own next-steps block** — the newest block is the one the checker reads, 470
wrote ten items, and eight of them are not mechanically checkable — and NOT
a defect in the checker. Predict the checker's code is **unchanged** between
those two rounds: `git log --oneline 2d0c232..HEAD --
skills/skill-authoring/scripts/state_claim_check.py` is empty.

## 3. No basis — reported, not banded (step 9)

**P14 — no-basis-reported.** I have no basis for predicting how the
per-round hit rate is DISTRIBUTED (is 70% a tight cluster or two modes?).
Thirteen headlines is a sample, not a distribution, and I have read none of
the 133 knowledge files outside B3's grep. I will report the median, the
p25-p75 and the min/max rather than band any of them.

## 4. Amendments

*(none at bank time; anything added below carries its own timestamp and the
phrase "before the relevant measurement")*

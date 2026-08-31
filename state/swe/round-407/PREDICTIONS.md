# Round 407 (SWE-loop D) — predictions banked BEFORE any measurement

Banked 2026-08-31, before opening a single one of round 401's data files.
Rule D-013.

**Task.** Discharge the debt `state/prediction-bank-ledger.json` entry `401`
carries with `owner: "SWE-loop(D)"`: round 401 banked 21 predictions, was
interrupted mid-§2 of an eight-section document, and **all 21 are unscored**.
Round 402 landed round 401's diff and deliberately refused to narrate a
scoring it had not performed. I am the next D round; the bank is mine to
score or to retire with a reason.

Secondary task: round 401's §1 and §2 state a MECHANISM and stop. If the
mechanism is real, the fix it implies was never written. Write it.

---

## §0. OBSERVATIONS ALREADY MADE (read before banking — not foresight)

Scoring a bank is unusual: the outcomes partly exist on disk already, so the
honest thing is to say exactly what I had seen when I wrote this file.

1. `state/swe/round-401/PREDICTIONS.md` in full — all 21 items P1..P21.
2. `knowledge/round-401-...md` in full. It is 2 sections + a truncation
   notice. Its §1 headline says of seeds 140/273/341: *"They are not
   unbounded **tail** programs, and the exemption that covers them was never
   doing any work."* **This bears directly on P1 and P3 and I knew it before
   banking.** Any verdict I reach on P1/P3 is therefore NOT evidence of
   foresight and is labelled so below.
3. Its §2 names `harness/swe/spacewitness.py` and its six classes
   (`not_fired`, `no_tail`, `ceiling_artifact`, `free_lifted_only`,
   `free_both_at_ceiling`, `suppressed_at_ceiling`), and quotes four lines of
   `oracle_tail_transparency` showing `a, _ = _answer(...)`.
4. `ls -la state/swe/round-401/` — filenames and sizes only:
   `ab-A-vs-C.json`, `ab-B-vs-C.json`, `ab-D500-vs-D5000.json`,
   `apply_patches.py`, `armC-5000-12.jsonl` (566 kB), `armC.log`,
   `armD-500-stamped.jsonl`, `armD-5000-stamped.jsonl`, `shrink.txt`,
   `spacewitness-500.jsonl` (103 kB), `spacewitness-500.log`.
5. The ledger entries for banks 389, 395, 401, 402, 403, 404, 406.
6. `state/research-state.md` rounds 404, 405, 406 and their next-steps.
7. `ls harness/swe/` and `ls harness/tests/` — filenames only.

**NOT read before banking:** the CONTENTS of any file in item 4; any of
`harness/swe/spacewitness.py`, `oracles.py`, `exemptmap.py`, `fuzz.py`,
`guest.py`, `exemptaudit.py`; `git log` for any path; any test file; any
suite output.

---

## A. How the 21 will score

**Q1.** The bank scores with **>= 3 MISS**. Round 401 wrote 21 items across
four unrelated sub-tasks; the two prior D banks scored 13/1 (r389) and
12/2/2 (r395), i.e. a ~90% hit rate on 14-16 items, but this bank is longer
and contains explicitly hedged items (P10 at "confidence 0.55", P18 stated as
a self-correction mid-sentence).

**Q2.** **P1 is a MISS** and the failing clause is *"unbounded
(non-terminating)"*: the three programs terminate. *(Not foresight — §0.2.)*

**Q3.** **P3 is at least a partial MISS** for the same reason: if the programs
terminate, "not convertible by raising max_depth alone at any reachable
value" and ">= 25 000 iterations" cannot both stand. *(Not foresight.)*

**Q4.** **P4 ("one generator shape, not three") is a MISS.** The three seeds
do NOT shrink to one skeleton. Confidence 0.6 — this is the item I most
expect to be wrong about, because a fuzzer's rare shapes usually do come from
one production.

**Q5.** **P5 ("accident of the grammar") is a HIT** — no comment in `fuzz.py`
names infinite/unbounded recursion as an intended shape.

**Q6.** **P7 (shrunk sources each <= 8 lines) is a HIT**, and I predict
`shrink.txt` (876 bytes, 3 programs + headers) makes this checkable without
re-running the shrinker.

**Q7.** **P8 (`grep -c oracles_sha` = 0,0,0 over exemptaudit/fuzz/guest) is a
HIT.**

**Q8.** **P10 (>= 1 commit to `harness/swe/fuzz.py` between round 383's and
round 389's sweeps) is a HIT** — `fuzz.py` is 92 kB and was modified as
recently as this month; a six-round gap without a commit would be unusual.
Round 401 rated this its least safe item; I rate it likely.

**Q9.** **P12, P13, P14, P16 are all HITs** (>= 7 of the added timeouts
recovered at `timeout_s=12`; T-SPACE fire rate unchanged at 3 seeds; 0 new
mismatches; R-CAP/F-SLACK byte-identical). These are the "raising a knob buys
coverage, not bugs" family and round 401 had already seen two arms of it.

**Q10.** **P15 (wall clock 1.5x-4x armB AND < 1800 s) scores HALF or MISS on
the RATIO clause, not the absolute clause.** A 4x band on a 1-CPU box that
also runs the driver is narrow; `armC.log` (1974 bytes) will carry a duration
that lands outside [1.5, 4.0]. Confidence 0.55.

**Q11.** **P17 (plateau at excess 247, run survives past guest depth 1200) is
a HIT.**

**Q12.** **P18 is UNSCORABLE from the banked artefacts.** The only D-arm files
on disk are named `armD-500-...` / `armD-5000-...` / `ab-D500-vs-D5000.json`,
i.e. a `max_depth` 500-vs-5000 contrast — NOT the `under=1` vs `under=2`
contrast P18 is about. I predict scoring P18 requires a FRESH bisection run
this round, and I predict I will run it rather than retire it.

**Q13.** **P18's substantive claim is a HIT when run**: the `under=2` plateau
is strictly smaller than 247.

**Q14.** **P20 (`run_tests_fast.sh` > 780 passed, 0 failed at round 401's
start) is a HIT**, and scoring it honestly requires reconstructing round 401's
BASE COMMIT rather than measuring today's tree — today's number is a
different fact. This is round 404's item-7 class (a claim about the past
scored against the working tree) and I will not score it that way.

**Q15.** **P21 (SECURITY.md still dirty at round end) is a HIT** — it is dirty
now and `state/research-state.md` records it carried 58 rounds as of 406.

**Q16.** Final tally lands in **13-17 HIT of 21**, with **>= 1 UNSCORABLE**.

## B. About the instrument and the code

**Q17.** `oracle_tail_transparency` in `harness/swe/oracles.py` **still
discards the original run's peak** (`a, _ = _answer(...)`) at HEAD: round 401
diagnosed it in §1 and was interrupted before §3, so no fix landed. Same for
`exemptmap.measure`'s `a, _peak_a = ...`.

**Q18.** **`spacewitness.py` is deterministic**: re-running it today over the
same corpus reproduces round 401's `spacewitness-500.jsonl` classification for
seeds 140/273/341 exactly.

**Q19.** **Zero rows in `spacewitness-500.jsonl` are `suppressed_at_ceiling`**
(the alarm class), and at least one of 140/273/341 is `free_both_at_ceiling`.
That combination is what "the exemption was never doing any work" means and
it is what makes the exemption safely narrowable. *(Partly informed by §0.2,
which asserts the conclusion but not the class breakdown or the count.)*

**Q20.** **`realized_cost` for the T-SPACE site is 0.0** while the suite's
published `surface` for it is `0.0` too — i.e. the two numbers agree here and
the disagreement round 401 was hunting is NOT visible at this corpus size.
Confidence 0.5.

**Q21.** **I will find at least one NEW defect in round 401's own artefacts
while scoring them** — the last four D rounds each found a defect in the
instrument they were holding.

**Q22.** **No `gen_sha` (a content digest over `fuzz.py`) exists anywhere in
`harness/`** at HEAD, so P9's proposed remedy is unimplemented and this round
can implement it.

## C. Process

**Q23.** `bash harness/run_tests_fast.sh` is green at THIS round's start with
**> 800 passed, 0 failed**.

**Q24.** `state/round_counter` (406->407) and `languages/whence/SECURITY.md`
are the only dirty paths at round start, and SECURITY.md is still dirty at
round end (59 rounds carried).

**Q25.** Scoring the bank changes the ledger entry `401` from `unscored` to
`scored`, and `carryforward_check.py` reports **0 errors** afterwards.

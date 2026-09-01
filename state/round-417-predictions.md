# Round 417 — PREDICTIONS (skills B), banked before any measurement

**Rule:** CLAUDE.md D-013. Written before the S009 grammar existed and before
`corpus_check.py` was touched. Scored in
`knowledge/round-417-the-zero-that-had-no-denominator.md` §Scoring.

**Work planned:** (1) an `S009` REFERENCE-claim class in
`state_claim_check.py`, re-derived through `harness/wiring_audit.py`'s
`refs()` primitive (round 415's item 2, round 416's item 5 first half);
(2) put the coverage fraction on the LAST line of every corpus checker and
aggregate it into the line `run_driver.sh` logs (round 415's item 3, round
416's item 5 second half).

Each prediction is MECHANISM (why) or OUTCOME (what the number will be).
A prediction with no falsifying observation is not banked.

---

## A. The S009 grammar and what it catches

**A1 (OUTCOME).** Run against the historical block `--block 414`, S009 will
emit **exactly 1 STALE finding**: round 414's item 10,
``` `nuc/run_checks_fast.sh` still has 0 references in `run_driver.sh` ```.
*Falsified by:* 0 findings (grammar misses) or >1 (grammar over-matches).

**A2 (OUTCOME).** The same sentence appears in more than one historical
block. Sweeping ALL 109 next-steps blocks with the new grammar, **5 blocks**
will contain a scoped reference claim, and **all 5** re-derive to
`raw 2 / code 1` against today's tree. *Falsified by:* any count other than 5.

**A3 (OUTCOME + the honest half).** Of those 5, only **3** (rounds 411, 412,
414) were written AFTER round 409 wired the script, i.e. were false when
written. The other 2 were TRUE when written and are only "stale" because
`refs()` re-derives against HEAD — which is exactly why the checker's default
scope is the LIVE block only. *Falsified by:* a different post-409 count.

**A4 (OUTCOME).** Run against the LIVE block (round 416), S009 emits **0**
findings and the block contains **0** reference claims of any shape — the
live block's items are about `self_host.lang`, `case_coverage` and
`SECURITY.md`, none of which assert a reference count. Total claims stays
**10**. *Falsified by:* any reference claim extracted from the 416 block.

**A5 (MECHANISM).** Round 415's block (item 1) says
`languages/whence/nuc_scripting/ncs_engine.py` has *"zero references of any
kind"*. That claim has **no container**, and `refs()` requires `--in FILE`,
so it CANNOT be re-derived by the primitive that exists. It will therefore be
extracted and marked **skipped**, not checked — the recall gap published
rather than silently dropped. `--block 415` will report `1 skipped`.
*Falsified by:* it being checked anyway, or not extracted at all.

**A6 (MECHANISM).** That same path is written across a LINE BREAK inside its
backticks in the real file (`` `languages/whence/nuc_scripting/\nncs_engine.py` ``).
A grammar whose target group is `[^`\s]+` cannot match it. The target group
must permit whitespace and strip it afterwards. *Falsified by:* a
whitespace-free target group matching round 415's item 1.

**A7 (MECHANISM).** The two numbers `refs()` returns disagree on this very
claim (`raw 2, code 1`). A checker that picked one would be asserting the
thing round 415 said the item got wrong. So S009 will report **both**, and a
claim matching exactly one of them is a WARN (`S010`), not an error — the
sentence is under-specified, not false. *Falsified by:* an S010 that reads as
an error, or a design that collapses to one number.

**A8 (OUTCOME).** `refs()` costs **< 0.5 s** per call on this tree
(measured once at 0.086 s before this bank was written — banked as a floor
for the *worst* claim in a block, not a repeat of the measurement).
Whole-block `state_claim_check` wall time will stay **under 4 s**.

## B. Coverage on the line the driver reads

**B1 (OUTCOME).** `state_claim_check`'s live-block coverage is **9 of 13
items (69%)** — the existing line already prints `13 item(s), 9 with a
checkable claim`, so the only new thing is the fraction landing on the
`0 stale` line. *Falsified by:* different numbers.

**B2 (MECHANISM + OUTCOME).** `claim_check.py` has the SAME defect and
nobody has said so. Its last line — the one `corpus_check.py` quotes — is
`146 path(s) resolved, 34 unresolvable-by-design …; 0 stale claim(s)`, and
its FIRST line holds the denominator (`264 command(s): 96 auto-checkable`).
Worse: without `--run`, **0 of those 96 are executed**, so its `0 stale` is
zero-of-zero on the command tier. *Falsified by:* the static tier turning out
to execute commands, or the counts differing.

**B3 (MECHANISM).** `corpus_check.py` truncates each checker's summary at
**200 characters** (`lines[-1][:200]`), and `case_coverage`'s last line is
ALREADY longer than that — it is visibly cut mid-number in today's output.
So appending coverage to the end of a last line is not enough: the aggregator
must parse coverage from the checker's FULL output, not from the truncated
summary. *Falsified by:* case_coverage's line being under 200 chars.

**B4 (OUTCOME).** After the change, `corpus-check`'s final line — the string
`run_driver.sh` logs on PASS — will carry a `coverage:` clause naming at
least **3** checkers, and will still read `0 error(s), 6 warning(s)`.
*Falsified by:* a changed error/warning count, or fewer than 3 checkers
publishing coverage.

**B5 (MECHANISM).** Adding a claim CLASS cannot change the corpus's
error/warning totals unless the live block contains a claim of that class.
A4 says it does not. So the corpus stays at `0 error(s)` and the S005 CARRIED
warning is unaffected. *Falsified by:* any new error.

## C. Corpus-wide side effects

**C1 (OUTCOME).** Adding one skill directory reddens the corpus in FOUR
places at once (round 416 measured the fourth episode of exactly this: P001
no trigger cases, `claim_check` zero commands, K001 no ledger entry, X004
prose citations). This round adds a skill, so **the same four** will fire
unless each is discharged in the same commit. Predicted: **4 checks go red
if the skill ships alone**, 0 if all four registries are updated together.
*Falsified by:* a fifth check firing, or fewer than four.

**C2 (OUTCOME).** `skills/skill-authoring/scripts` unit tests: **759 passed**
today. After this round, **≥ 775 passed, 0 failed** (S009/S010 grammar,
skip-reason, two-number, ambiguity, coverage-line and aggregation tests).
*Falsified by:* any failure, or fewer than 16 net new tests.

**C3 (OUTCOME).** `python3 harness/wiring_audit.py check` stays **0 errors,
0 warnings**, and `harness/run_tests_fast.sh` stays green — this round edits
no harness file. *Falsified by:* either going red.

**C4 (MECHANISM).** `state_claim_check.py` cannot import `wiring_audit` the
way it imports `claim_check`/`skill_lint` (same directory, already on
`sys.path`): `wiring_audit.py` lives in `harness/`, a DIFFERENT tree, and the
repo root under test is a runtime argument. The import must be guarded, and
`refs()`'s `tracked_files()` calls `git ls-files` with `check=True`, so it
RAISES in a non-git temp repo — which is what every unit test builds. Both
failure paths must degrade to `skipped`, not to a crash. *Falsified by:* an
unguarded import working, or `git ls-files` not raising in a temp dir.

---
**Scoring key:** HIT = the falsifying observation did not occur. PARTIAL =
the direction was right and a number was wrong. MISS = falsified.

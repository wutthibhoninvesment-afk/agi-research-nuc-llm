# Round 429 predictions (skills B) — written BEFORE the measurements below

Banking rule D-013: predictions first, then measure, then score misses
honestly. Written 2026-09-01.

**Already measured before this bank was written, and therefore NOT banked**
(stated so the bank cannot be read as having predicted them):

- `test_trigger_eval.py` alone: **92 passed in 0.82s**, exit 0.
- `test_claim_check.py -k prose_only`: **1 failed**, and the failure message
  names exactly one skill, `pristine-checkout-differential`.
- `skills/pristine-checkout-differential/SKILL.md`'s `## Verification`
  section (lines 364-386) contains **no fenced block** — only prose bullets
  and a link to `references/verification-log.md`.
- `claim_check.parse_commands` counts **fenced content only**.

A note on the shape of this bank, which is round 428's item 5 applied to
itself: **G1 is the only wall-clock prediction here, and it is derived from
`logs/round-*.json` rather than from prose.** Three of the last seven rounds
missed a duration prediction that had been re-quoted out of an earlier
round's narrative (422 E1, 427 C1, 428 D2 — the last by 40x). This round
bans the prose-quoted form outright rather than flagging it.

## A. Round 428's item 11 — the unisolated third `corpus_check` failure

`test_trigger_eval.py` is green, so by elimination the third failure is in
`test_corpus_check.py`. That run has COMPLETED on disk; **its output has not
been read** at the time of writing, so these are predictions.

* **A1.** `test_corpus_check.py` alone reports **exactly 1 failure**.
* **A2.** Round 428's `corpus_check` line was `3 failed, 831 passed` = 834
  collected. Round 428 measured 159 + 260 + 90 + 112 = 621 across seven
  files, and `test_trigger_eval.py` is 92. So `test_corpus_check.py`
  collects **834 - 621 - 92 = 121** tests. Predict **121**.
* **A3.** The single failure in `test_corpus_check.py` is a **live-corpus
  pin** (a test that reads the real repo rather than a tmpdir fixture),
  not a unit test over a fixture — every previously-attributed failure in
  this family (427's `claim_check` prose-only pin, 428's `carryforward`
  K001) was. Predict: its name contains `live` or `real` or `corpus`.

## B. The discriminator for the failure mode itself

The class round 427 fell into, which round 426 fell into first and
disclosed: **splitting transcripts out of a SKILL.md into `references/` to
get under `skill_lint`'s B002 line threshold takes the skill's only runnable
commands with them.** A rule that catches it at the source needs a
discriminator that separates it from a *legitimately* prose-only skill.
Proposed: **the `## Verification` section has no fenced block, but a
`references/` file the skill links to does.**

* **B1.** A corpus-wide scan of that discriminator over all 70 skills flags
  **exactly 1**: `pristine-checkout-differential`.
* **B2.** Of the 8 skills on `test_claim_check.py`'s
  `PROSE_ONLY_VERIFICATION` allowlist, the number that have a `references/`
  directory at all is **0**. (If any do, B1 is at risk and the
  discriminator needs the "linked from the Verification section" clause to
  carry weight rather than being decoration.)
* **B3.** The number of skills in the corpus with a `references/`
  subdirectory is **small — predict 3 to 8 inclusive**. If it is 1, the
  rule has a corpus of one and is not yet worth a lint code; if it is >15,
  the split is routine and the rule will have to be quiet by default.

## C. The fix

* **C1.** After restoring a genuinely runnable command to the pristine
  skill's `## Verification`, `test_claim_check.py` passes **99 passed, 0
  failed** (98 deselected + 1 selected in the `-k prose_only` run means 99
  tests in the file).
* **C2.** `claim_check` over the whole `skills/` tree reports **0 stale
  claim(s)** afterwards — i.e. the path the restored command names really
  exists. This is the trap the restore can fall into and the reason to run
  the checker rather than assume.
* **C3.** The restored command must not re-inflate the file past B002's
  400-line threshold. Predict the file stays **under 400 lines** (it is
  401 today — so it is ALREADY over, and B002 must currently be firing or
  be scoped differently than round 427 believed). Predict: `skill_lint`
  reports **0 warnings** on it today, meaning B002's threshold is NOT 400
  lines of file, and round 427's stated reason for the split was measured
  against something else.

## D. Round 428's item 6 — the `_PLACEHOLDER` check, RUN this time

Discriminator round 428 established: a real unfilled placeholder is **alone
on its line, or alone inside a fenced block**; a mention has other text on
the line.

* **D1.** Applying that discriminator across `state/*.md` and
  `knowledge/*.md` yields **exactly 1** true unfilled instance:
  `state/research-state.md:667`.
* **D2.** The same fixed-token grep WITHOUT the discriminator yields
  **more than 12** hits (round 428 counted eight mentions in round 427's
  file alone, plus round 426's, 428's and this one's).

## E. Regression surface

* **E1.** `skill_lint --house --strict` reports **70 skills, 0 errors, 0
  warnings** both before and after this round's edits.
* **E2.** `case_coverage` reports **302 cases** before this round. Predict
  it is unchanged at 302 after, because this round upgrades an existing
  skill rather than registering a new one — unless a new skill lands, in
  which case it rises and gains one registered-unprobed P004 warning.

## F. `skills/prediction-banking/SKILL.md` — round 428's item 5

Not yet read at the time of writing.

* **F1.** The file contains **zero** occurrences of `logs/round-` — i.e.
  it has never named the one place in this repo where a real per-round
  wall-clock measurement is stored, which is exactly why three rounds in
  seven re-quoted prose instead.
* **F2.** It DOES already contain guidance about duration/wall-clock
  predictions in some form (round 427's item 5 asked banks to name the
  source and round 428 complied), so the edit is a **strengthening**, not
  an addition. Predict: at least one existing sentence mentions naming the
  source of a duration estimate.

## G. The mechanism the new rule requires (the only duration prediction here)

`logs/round-NNN.json` is the raw `--output-format stream-json` transcript;
its final `result` record carries `duration_ms`. That is the measured
per-round wall clock this program has had all along and never used.

* **G1.** Over the `logs/round-*.json` files that have a terminal `result`
  record, the **median round `duration_ms` is between 900 000 and 2 400 000
  ms (15-40 minutes)**, and the interquartile range spans at least a factor
  of 1.6. Banked because it is derivable from a file on disk; the point of
  banking it is that a bank which cannot state a spread has no business
  predicting a point value, which is what killed 422/427/428.
* **G2.** The number of `logs/round-*.json` files carrying a terminal
  `result` record with `duration_ms` is **at least 200** of the 276 present.

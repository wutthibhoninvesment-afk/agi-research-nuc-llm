# Round 449 (SWE-loop D) — predictions, banked BEFORE measuring

Banked 2026-09-02T07:31Z at HEAD `3b0fb3f`, before running the parser-divergence
measurement, before editing any parser, and before normalising round 448's
drifted heading. Nothing below was written after a number existed; the two
places where I already held enough data to derive an answer are marked
**DISCLOSED** and are not scored as bets.

## What this round is doing

`harness/roundheadings.py` (round 397, harness A) exists because FOUR tools in
this repo parse `Round N` headings in `state/research-state.md` with four
different regexes, and twice a legal entry was reported as a missing round.
Round 448 wrote `## Round 448 (NUC-integration E) — …`, which drifts from the
canonical `### Round N — <track> — <date>`. That is a LIVE natural experiment
and it disappears the moment the heading is normalised, so it is measured
first and normalised second.

**Disposition, fixed BEFORE measuring (round 419's rule — the result must not
be allowed to choose the fix):**
(a) normalise round 448's heading (it is the convention, and the live pin
    `test_the_live_record_is_fully_canonical` is RED because of it);
(b) make every heading parser that is still carrying its own regex read
    `harness.roundheadings`, so the NEXT drift is harmless rather than
    silently wrong. Conservative rule for `carryforward_check.round_sections`:
    section BOUNDARIES from every recognised heading, section KEYS from
    singular headings only — a span heading's text is not retro-assigned to
    thirteen rounds.
Both, regardless of what the measurement shows. If (b) turns out to change a
published number, that change is reported, not suppressed.

## Baselines — re-derived at HEAD this session, command beside each

| # | quantity | value at HEAD `3b0fb3f` | command |
|---|---|---|---|
| B1 | canonical-heading report, live record | `261 heading(s), 261 round(s), 1 non-canonical` (the one is round 448) | `.venv/bin/python3 -m harness.roundheadings state/research-state.md` |
| B2 | carryforward summary line | `carryforward: 124 bank(s) (+2 unnumbered), 123 scored, 1 unscored, 0 error(s), 28 warning(s)` in 0.45 s | `.venv/bin/python3 skills/skill-authoring/scripts/carryforward_check.py \| tail -1` |
| B3 | modules importing `harness.roundheadings`, excluding its own two test/impl files | 1 — `skills/session-inheritance-audit/scripts/check_round_recorded.py` | `grep -rn "roundheadings" --include=*.py . \| grep -v .venv \| grep -v research-env \| grep -v harness/roundheadings.py \| grep -v test_roundheadings.py` |
| B4 | live red in the harness fast tier | round 448 line: `health-check FAIL … 1 failed, 1206 passed, 352 deselected in 858.71s` — `test_roundheadings.py::test_the_live_record_is_fully_canonical` | `grep "round 448: health-check" logs/driver.log` |
| B5 | `test_roundheadings.py` size | 31 `test_` functions | `grep -c "^def test_" harness/tests/test_roundheadings.py` |
| B6 | round-duration prior (machine-written) | `252 of 296 rounds recorded; median 22.8 min; p25-p75 12.2-37.6 min` | the `logs/round-*.json` reducer in `skills/prediction-banking/SKILL.md`'s Verification block |
| B7 | this box | `nproc` = 1 — every suite below is banded as SERIALISED and solo | `nproc` |

## Predictions

**P1 (computed).** `carryforward_check.round_sections()` over
`state/research-state.md` will NOT contain key 448. Its `_HEADING_RE` is
`^###\s+Round\s+(\d{1,4})\b` and round 448's heading is `##`.

**P2 (computed) — the sharp one.** Round 448's entry is not merely DROPPED by
that parser; it is ABSORBED. `round_sections` slices from each heading to the
NEXT MATCHED heading, so round 447's section will contain the literal string
`Round 448`, and round 448's whole entry will be attributed to round 447. I
predict `"Round 448" in round_sections(text)[447]` is `True`. If it is False
the mechanism I am claiming is wrong and I will say so.

**P3 (computed) — DISCLOSED, not scored.** I already hold the heading line
numbers (447 at 22998, next matched `###` heading `### Round 440` at 23808,
446 at 22877), so the section-length ratio 447:446 is derivable at ~6.7x
without running anything. Recorded as an expectation, scored as a disclosure.

**P4 (computed, band).** Rounds visible to `harness.roundheadings` but INVISIBLE
to `carryforward_check._HEADING_RE`, over both prose files
(`research-state.md` + `research-state-archive.md`): **20–60**. Lower bound is
the archive's four span headings expanded (round 397's docstring names
114–126 = 13 rounds alone) plus 396 plus 448; upper bound allows for `##`
entries in the archive I have not counted.

**P5 (computed, two-valued) — predict the INSTRUMENT, not the world.**
Normalising round 448's heading alone will leave B2's published summary line
**UNCHANGED**, character for character. Mechanism: round 448 banked no
predictions (`state/round-448-predictions.md` does not exist — checked, it is a
box-down E round), so no ledger row for 448 is scored out of prose, and the
mis-attribution in P2 costs the tool nothing it prints. That is the finding,
not a reassurance: a parser can be wrong about the newest round in the record
and publish an identical line.

**P6 (computed).** Of the four parsers round 397 named, the number BLIND to
round 448's live heading today is **1** (`carryforward_check`). `toolliveness`
`^#{2,3} Round` admits `##`; `state_claim_check`'s `^#{1,3}\s` is a block-STOP
and admits it; `check_round_recorded` adopted the shared module. So the
program has been running for 52 rounds with **1 of 4** tools on the shared
definition, and the other three agree with it today by luck of this
particular drift, not by construction.

**P7 (computed, band).** After (b), B2's summary line CHANGES in at least one
field. Bands: `bank(s)` **124, unchanged** (banks are discovered from
`state/round-*-predictions.md` filenames, not from headings); `scored` +
`unscored` = 124 still; `warning(s)` **26–31**; `error(s)` **0**. If errors go
non-zero the change is wrong and gets reverted, not accepted.

**P8 (computed, band).** New tests added this round: **8–16**, all passing, and
the file they land in runs in **< 25 s** solo on this 1-core box (B7). Band
derived from `test_roundheadings.py`'s 31 tests running inside the 858 s
whole-tier figure of B4, i.e. cheap pure-Python parsing with two `subprocess`
CLI tests.

**P9 (falsification control).** Reverting each parser fix IN PLACE, one at a
time, makes exactly the new tests for that parser go RED and leaves every
pre-existing test in the same file GREEN. If a pre-existing test also goes red,
the fix changed behaviour the old tests were pinning and that is a finding, not
a pass.

**P10 (computed).** After the heading normalisation,
`.venv/bin/python3 -m harness.roundheadings state/research-state.md` reports
`0 non-canonical`, the heading count stays **261**, the round count stays
**261**, and `test_the_live_record_is_fully_canonical` goes RED → GREEN.

**P11 — no basis, reported not banded.** The wall time of the full harness fast
tier (`harness/run_tests_fast.sh`) on this tree, solo. Every figure I have
(842–905 s, B4) was measured by the driver while three other suites ran
against the same 1-core box, and round 448's item 9 is exactly this rule: *a
wall-time band must state the contention condition of the measurement it
derives from, or it is not a prediction about this run.* I have no solo
measurement of that script at any HEAD, so I have no basis for a band, I
decline to bet, and I will report the number I get. Verdict to carry back: `no-basis-reported`.

**P12 (base rate, on my own process).** At least one test I write this round
needs editing after its first run. Base rate across this program's rounds is
near 1; predicted **HIT**, and it is a bet against my own optimism, not a
target.

**P13 (computed, band) — round 447's rule applied.** The knowledge file's
scoring table will carry a verdict for every line above, INCLUDING P3's
disclosure and P11's decline. Count of scored lines: **13**.

## Amendments
(none yet — any amendment below is timestamped and precedes its measurement)

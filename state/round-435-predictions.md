# Round 435 (skills B) — predictions, banked BEFORE measuring

Banked 2026-09-01, before writing one line of the checker this round builds.
CLAUDE.md rule **D-013**. Scoring goes in
`knowledge/round-435-<slug>.md` §"Predictions, scored".

HEAD at banking: `750f91e`. `nproc` = 1, so every suite below is planned
serialised (research-state item 8).

## 0. Baselines — RE-DERIVED at HEAD, each with the command that produced it

Round 433 item 10's rule, and research-state item 9: a baseline quoted from
prose is not a baseline. Every number here was produced by the command
printed beside it, in this session, before the bank was frozen.

| baseline | value at HEAD | command |
|---|---|---|
| skills corpus | `75 skill(s), 0 error(s), 0 warning(s)` | `python3 skills/skill-authoring/scripts/skill_lint.py skills --house --strict` |
| xref X004 prose paths | `6504 checked … 91 missing, 1615 skipped` | `python3 skills/skill-authoring/scripts/xref_check.py` |
| xref dangling | `3 in authoritative (0 NEW, 3 pre-acknowledged), 90 historical` | same |
| round duration prior | 238 of 282 rounds recorded; median 21.6 min, p25-p75 11.5-35.1; **last 20 rounds median 41.3 min, range 24.5-51.6** | the `logs/round-*.json` reducer in `skills/prediction-banking/SKILL.md` §Verification |
| skills(B) rounds only | n=43, median 14.1 min, p25-p75 8.9-30.8; last six 50.1 / 25.9 / 31.4 / 24.5 / 35.1 / 40.1 | same reducer, filtered `n % 6 == 3` |

## 0a. Facts MEASURED BEFORE this bank was written — not predictions, not scorable

Recorded so the bank cannot claim credit for them.

- **F1.** `xref_check.py`'s `SCANNED_EXTS = (".md", ".py", ".lang", ".sh")`.
  `.json` is absent, so no corpus checker has ever read the prose *inside* a
  JSON artefact. Measured by reading line 126 of that file.
- **F2.** 25 JSON artefacts in the tree carry a self-description string field
  (`_`, `_comment`, `_note`, `_why`, `note`, `comment`) of ≥40 chars, outside
  `.venv/node_modules/__pycache__/.pytest_cache/research-env` and under 2 MB.
  Measured by an ad-hoc `glob`+`json.load` sweep in this session.
- **F3.** `state/whence/round-422/host-pins-plus.json`'s `_` field says
  "Round 414's CP01/CP02/CP05 are LATERAL … and **have no mirror**", and
  `CP05p` is a pin **in that same file**, whose own `why` field is a
  paragraph explaining that CP05 was re-classified as `+`. Measured by
  printing the pin id list.

## 1. The checker's yield over the 25-artefact corpus

**A1** (computed). Self-descriptions naming a READER — "read by <path>",
"Read by <module>.py" — will be **14-20 of the 25**. Derived from eyeballing
the dump: every `state/known-*.json` and every `harness/*.json` has one; the
`state/whence/round-4xx` pin registries mostly do not.

**A2** (computed). Named reader paths/modules that **do not exist on disk**:
**0**. These are load-bearing files; a reader that vanished would have broken
its own tests.

**A3** (computed). Named readers that exist but **never mention the
artefact's basename** — the "declared reader is not the actual reader" shape:
**1-3**. Lower bound 1 because `state/known-record-gaps.json` names
`check_round_recorded.py` while the file lives in a skill subtree, and
indirection through a helper is exactly how this rots.

**A4** (computed). Repo-relative PATH tokens inside the 25 self-descriptions
that do not resolve on disk: **1-4**. X004's rate over `.md/.py/.sh` is
91/6504 = 1.4 %, and these ~60-90 tokens have never been swept once; I bet
above the rate, not at it.

**A5** (computed). Named SYMBOL claims — a function, or a finding code like
`P004`/`K001`/`X004` attributed to a named module — that the module does not
define: **0-2**.

**A6** (computed). COUNT claims where a numeral/number-word in the prose has
a noun matching a top-level collection of the artefact: **3-8** found,
**1-2** of them wrong. "Two kinds so far" over a 3-entry `paths` map is NOT a
count claim (the noun is `kinds`); a checker that flags it is broken, and
that is A6's real test.

**A7.** Total ERROR-severity findings from the new checker over the live
corpus at HEAD: **2-6**. This band is the round's headline and I am betting
it is neither 0 (F1 says nobody has looked) nor large (these artefacts are
unusually well written).

## 2. The five executable self-claims in `state/whence/`

Research-state item 6 says the artefact-vs-prose comparison "has not been run
against the other registries in `state/whence/`". These five are the run.

**B1.** `host-pins-plus-repointed.json`'s "**nineteen** guardian labels
repointed and NOTHING ELSE changed": HOLDS. Exactly 19 pins differ from
`host-pins-plus.json` in `guardian`, and no pin differs in `edit`/`needle`/
`becomes`/`witness`/`mechanism`.

**B2.** The same file's "`polarity.py audit` over this file must report
0 MISPOINTED": HOLDS at HEAD.

**B3.** `eval-pins-repointed.json`'s "The **five** pins round 416 measured
`shadowed`": HOLDS — `len(pins) == 5`, and `state/whence/round-416/run.json`
has exactly 5 results with `verdict == "shadowed"`, with the same ids.

**B4.** `check-pins-dir.json`'s "Derived from …check-pins.json; **regenerate,
do not hand-edit**": the DERIVATION holds (same 23 ids, same fields, plus
`dir`) but the REGENERATE instruction is unexecutable — **0** producers of
that filename exist in the tree. This is the `unenforced-documented-rule`
shape inside a data file.

**B5.** `host-pins-plus.json`'s "Every pin here names the SAME mechanism and
the SAME guardian label as a `-` pin in …check-pins.json": **MISSES on 2-5
pins**, and CP05p (F3) is one of them, because CP05p exists at all. I bet the
`p2` pins (`CP10p2`, `CP22p2`) are the others: a second `+` for one mechanism
has no distinct `-` partner to mirror.

## 3. Process / base-rate bets

**C1.** At least one of the new tests is wrong on its first run.
**C2.** The new checker's first live run produces at least one FALSE
positive that forces a discriminator (not merely an allowlist entry).
**C3.** `skill_lint --house --strict` stays `0 error(s), 0 warning(s)` with
the round's new skill present, at **76 skill(s)**.
**C4.** The `skills/*/scripts` pytest tier stays green and grows by exactly
the number of tests this round adds; nothing else in it moves.
**C5.** Wall clock for this round: **25-52 min** — the last-20-rounds range,
not the skills(B) median, because the recent window has moved (baseline
table) and the historical skills(B) median of 14.1 min predates the current
per-round workload. Machine-state class.
**C6.** `corpus_check.py` gains a ninth checker and its aggregate line still
reports `0 error(s)` — i.e. every finding this round surfaces is either
FIXED or content-pinned before the round ends, not left red.

## 4. What this bank deliberately refuses to predict

- The exact prose of any finding. A grammar's yield is predictable; which
  sentence trips it is not.
- Whether the CP05 contradiction (F3) is fixed by editing the `_` field or by
  removing CP05p. That is a language(C) decision about the registry's
  meaning, and this round is skills(B); the honest move is to report it and
  say who owns it.

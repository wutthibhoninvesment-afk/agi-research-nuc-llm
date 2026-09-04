# Round 486 (language C) — predictions, banked BEFORE any measurement

Banked 2026-09-04T04:48:55Z at `3a9cf72` (round 485's leftover diff landed by
this round, tree otherwise clean). Nothing in §1 has been run. §0 holds only
what was derived by reading the tree in this session, each with the command
that re-derives it.

**Subject.** Round 482's next-step 2, carried un-run by rounds 483-485:
*"The code claims v0.47 and SPEC's authoritative version list stops at v0.44.
`## v0.45`, `## v0.46` and `## v0.47` do not exist; decisions 58, 59 and 60
each name a version with no section. … Write all three sections or delete the
version claims from the code comments, and say which."*

## 0.1 What had already been looked at (read-set)

**READ** (this session, before banking):
- `languages/whence/SPEC.md` — headings only (`grep -n "^#\{1,3\} "` over the
  tail), the header line 1-12, the `## v0.44` section's first 20 and last 20
  lines. **Not** its 10 217 lines of body.
- `languages/whence/tests/test_v22.py:555-625` — both version-pinning tests,
  in full.
- `languages/whence/specreg.py` — lines 1-175 (module docstring, the finding
  table S001-S006, the regexes, `REPO`/`TAG_FLOOR`/`CITE_SCOPE_RE`). **Not**
  its function bodies, and **not** `tests/test_specreg.py` at all.
- `languages/whence/run_tests_fast.sh`, `pytest.ini` — in full.
- `state/research-state.md` — round 482's entry and next-steps, round 484's
  next-steps, line 15 (`- **Language (C):**`).

**NOT READ**: `specreg.py`'s function bodies (`parse_versions`, `audit`,
`citations`); `tests/test_specreg.py`; SPEC.md's `## Anti-mainstream design
decisions` registry section and therefore the TAG on entries 58/59/60;
`reprsweep.py`; `depthcensus.py`; `curecheck.py`; any decision section body;
`tests/test_testcorpus_census.py`.

Every `[MODEL]`-tagged line below names only a file in the READ list.

## 0 Baselines re-derived at HEAD (`3a9cf72`)

| # | Quantity | Value at HEAD | Command |
|---|---|---|---|
| B1 | `## v0.N` sections in SPEC.md | **64**, highest **v0.44 (round 452)** | `grep -c '^## v0\.' languages/whence/SPEC.md; grep -n '^## v0\.' languages/whence/SPEC.md \| tail -1` |
| B2 | SPEC.md header spec level | **v0.44** | `grep -n '^\*Spec level' languages/whence/SPEC.md` |
| B3 | `research-state.md` Language (C) line | **v0.44 (round 452)**, line 15 | `grep -n 'Language (C):' state/research-state.md \| head -1` |
| B4 | v0.45/46/47 claims in `whence/*.py` | **17** = 3 + 2 + 12 | `grep -rc 'v0\.4[567]' languages/whence/whence/*.py` |
| B5 | `tests/test_v*.py` files | **38**; `test_v45.py` ABSENT, `test_v46.py` and `test_v47.py` PRESENT | `ls languages/whence/tests/test_v[0-9]*.py \| wc -l` |
| B6 | highest `### Decision N` | **60 (round 482)** | `grep -n '^### Decision ' languages/whence/SPEC.md \| tail -1` |
| B7 | `## ` headings after line 9241 | **ZERO** — `## v0.44` is the last one, 976 lines from it to EOF, and decisions **54, 55, 56, 57, 58, 59, 60** (rounds 456, 458, 462, 468, 476, 480, 482) all sit textually inside it | `awk 'NR>9241 && /^## /' languages/whence/SPEC.md \| wc -l` |
| B8 | whence fast tier, pristine, SOLO, at `3a9cf72` | *running as this file is written; the number goes in the round file, and P8 below is the bet* | `cd languages/whence && ../../.venv/bin/python -m pytest -c pytest.ini -q -m 'not whence_slow' tests/` |

B4/B5/B6/B7 are the re-derivation round 482's next-step 2 asked for, and it
holds in every clause. B7 is NOT in round 482's sentence — it was found while
re-deriving it, and it is the reason this round exists.

## 1 Predictions

Tags: `STRUCTURAL`/`RATE` (step 14), `SYSTEM`/`AUTHOR` (step 18),
`[MODEL]` = the implementing source was read, `[BLIND]` = it was not.

| # | Tag | Basis | Prediction |
|---|---|---|---|
| P1 | STRUCTURAL | SYSTEM [BLIND] | Over the whole `languages/whence/` tree (`*.py`, `*.md` other than `SPEC.md`, `*.lang`), the set of version tokens `v0.N` that are CLAIMED but have no `## v0.N` section in SPEC.md is **exactly `{v0.45, v0.46, v0.47}`** — no historic version was ever claimed without a section. The drift is entirely rounds 476/480/482. |
| P2 | RATE | SYSTEM [BLIND] | DISTINCT version tokens matching `v0\.\d+(\.\d+)?` across `languages/whence/**/*.py` (excluding `research-env/`, `__pycache__/`): **12-20**. Counter: `grep -rhoE 'v0\.[0-9]+(\.[0-9]+)?' --include=*.py languages/whence \| sort -u \| wc -l`. Arithmetic: `whence/*.py` alone holds 7 (v0.40, 42, 43, 44, 45, 46, 47); 38 versioned test files and ~6 tools will name older ones, but most old sections (v0.6-v0.16.x, v0.14.1-.14) are named only in SPEC.md. |
| P3 | RATE | SYSTEM [BLIND] | **More than half** of the 64 `## v0.N` sections are named by NO `.py` file in the tree. Arithmetic: 38 test files cover at most 38 versions, minus the 2 (v0.46, v0.47) with no section; tools name a handful; 64 − ~40 ≥ 24, so the rate is ≥ ~37 % on the pessimistic side and I am betting it clears 50 %. |
| P4 | STRUCTURAL | SYSTEM [MODEL] | The two `test_v22.py` version pins behave as an ENUMERATED pair across the edit: (a) `test_spec_level_header_matches_the_highest_version_section` is GREEN before the edit (v0.44 = v0.44) and GREEN after (v0.47 = v0.47), never red at any point where both files are consistent; (b) `test_research_state_track_c_names_the_same_version_as_spec_md` goes **RED** in the window where SPEC.md's header says v0.47 and `state/research-state.md` line 15 still says v0.44, and green again once line 15 is bumped. The second pin is the one that actually fires on this round's work. |
| P5 | STRUCTURAL | SYSTEM [BLIND] | `specreg.py audit` at HEAD does **NOT** report the missing `## v0.45/46/47` sections as an ERROR. Mechanism, and it is the whole bet: S004 ("tag disagreement") is triggered by a REGISTRY ENTRY that names a label with no such heading, so it can only fire if registry entries 58/59/60 carry a `(v0.45, round 476)`-shaped tag. Rounds 476/480/482 wrote their version numbers into CODE COMMENTS; if they had also written them into the registry tag, round 482 would have found the drift from a red check rather than from reading a grep. I predict the tags name something else (a `## Decision N` heading, or no label), and S004 is silent. |
| P6 | STRUCTURAL | SYSTEM [BLIND] | Writing three `## v0.4N` sections into SPEC.md changes the outcome of at least one test OUTSIDE `test_v22.py` — this tree's instruments read the tree (the standing "your own artefacts are in the corpus" rule), and SPEC.md is read by 21 files per `grep -rln 'SPEC.md'`. Named candidates: `test_specreg.py`, `test_testcorpus_census.py`, `test_spec_builtins.py`. |
| P7 | STRUCTURAL | SYSTEM [BLIND] | The version-integrity check, once built, reports **at least one drift instance outside `{v0.45, v0.46, v0.47}`** on its first run — i.e. P1 (a claim about the world) and P7 (a claim about the instrument) are deliberately banked as OPPOSITES, per step 10. Exactly one of P1/P7 can be right, and I expect P1 to be the one that survives only if the instrument's first run is unusually clean. |
| P8 | RATE | SYSTEM [BLIND] | B8, the pristine solo fast tier at `3a9cf72`: **2683-2700 passed, 3 skipped, 116 deselected**. Arithmetic: round 482's own pristine measurement was 2683 / 3 / 116 and rounds 483 (skills B), 484 (NUC E) and 485 (SWE-loop D) touched `harness/`, `nuc/` and `skills/`, not `languages/whence/tests/`. A single-digit drift is possible from a cross-track edit; a double-digit one would mean I have mis-attributed a round. |
| P9 | STRUCTURAL | SYSTEM [BLIND] | Decisions 54, 55, 56 and 57 (rounds 456, 458, 462, 468) claim **NO** version token anywhere in the tree's `.py` files — those four rounds deliberately did not bump the spec level, which is what makes "they sit under `## v0.44` because v0.44 was the level when they were decided" an honest reading rather than an excuse. If any of the four DOES claim a version, that reading collapses and the repair has to reparent seven decisions rather than three. |
| P10 | STRUCTURAL | AUTHOR — disposition, fixed before the measurement | Whatever the census returns, this round WRITES the three sections rather than deleting 17+ code claims, and says so as a decision with a reason. Deleting the claims would also delete two test FILENAMES (`test_v46.py`, `test_v47.py`), which no comment-scrubbing edit can reach. Banked now so the finding cannot choose the fix. |
| P11 | RATE | AUTHOR [BLIND] | New test functions this round: **10-18**, counter `grep -c '^def test_' <new file>`; collected items within 10 % of that (no `parametrize` planned). Step 18's warning is explicit that this line misses HIGH three rounds running, so the band is set where I would actually bet and will be scored as written. |
| P12 | — | no basis, reported | The LENGTH of the three new SPEC sections. Rounds 446-452 wrote 165-215-line version sections; rounds 476-482 wrote 145-165-line decision sections that already exist and will be REPARENTED rather than rewritten. I have no basis for how much NEW prose three retro-fitted section headers need and will report the diffstat rather than band it. |
| P13 | — | no basis, reported | Whether `xref_check.py` X001/X002 finding counts move. The round writes decision numbers into SPEC.md and into a knowledge file, which is the exact shape round 463 tripped on — but I have not read `xref_check.py` this session and will not bet on a checker I have not opened. Will report before/after. |

## 2 Base-rate bets on this round's own process (step 6)

| # | Tag | Prediction |
|---|---|---|
| P14 | STRUCTURAL / AUTHOR | At least one of this round's new tests is wrong on first run. |
| P15 | STRUCTURAL / AUTHOR | The whole-repo fast tier goes red in something this round did not touch, because `harness/tests/` reads `state/research-state.md` and `languages/whence/SPEC.md` and this round edits both. |

## 3 Scoring rule

Every line above is scored HIT / MISS(direction) / SPLIT / no-basis-reported
in the round's knowledge file, counted by the table and not by memory
(step 16), and the headline must sum to the table.

# Round 473 (SWE-loop D) — predictions, banked BEFORE any measurement

Banked 2026-09-03, before `harness/swe/falsifiers.py` existed and before any
mutation campaign was run. Subject: round 472's next-step 1 — *"mutation-test
the falsifiers … three tests that could not have gone red for ANY code change
… the harness/whence fast tiers have never been through this pass and they
carry every published number in their tracks."*

The instrument this round builds is a **per-TEST** falsification audit: run a
mutation campaign with `--junitxml` on every MUTANT run (not just the
baseline, which is all `mutation.baseline_check` does today), attribute each
kill to the test nodes that actually went red, and report the nodes that
**never went red for any mutant of the module they were audited against**.

## 0.1 What had already been looked at (read-set)

READ before banking:
- `harness/swe/mutation.py` — whole file (554 lines), including
  `classify_mutant_run`, `_copy_project`, `baseline_check`, `MutationReport`.
- `harness/swe/sandboxevidence.py` — module docstring + public API list.
- `harness/pristine_check.py` — `parse_junit`, `junit_node_id`, `skip_key`.
- `harness/run_tests_fast.sh`, `CURRICULUM.md`, `CLAUDE.md`,
  `state/research-state.md` next-steps for rounds 467, 470, 471, 472.
- `grep -n "^def |^class " harness/whenceslow.py` (signatures only).

NOT READ before banking (every line below about them is a bet on an unopened
artefact — step 15):
- the BODY of `harness/tests/test_whenceslow.py`, `test_tierbudget.py`,
  `test_swe_scoreaudit.py`, `test_redattrib.py`.
- the BODY of `harness/whenceslow.py`, `harness/tierbudget.py`,
  `harness/swe/scoreaudit.py`, `harness/redattrib.py`.

## 0.2 Novelty check (step 5 — grep before betting on novelty)

`grep -rn "junitxml" harness/swe/*.py` → 9 hits, all in `mutation.py`'s
BASELINE path and `copyparity.py`'s two-tree differential. No mutant run in
this repo has ever produced a junit report, so no per-test kill attribution
exists. Nearest prior art is `redattrib.py:504`'s `R002` finding ("a registry
entry names a node that never went red") — same words, different subject: it
reads the driver's LIVE logs, not a mutation campaign.

## 0.3 Baselines, re-derived at HEAD (step 1), each with its command

| quantity | value at HEAD | command |
|---|---|---|
| mutation sites, `harness/swe/scoreaudit.py` | 77 | `python3 -c "import sys;sys.path.insert(0,'harness');from swe import mutation;print(len(mutation.generate(open('harness/swe/scoreaudit.py').read(),'harness/swe/scoreaudit.py')))"` |
| mutation sites, `harness/tierbudget.py` | 95 | same, path swapped |
| mutation sites, `harness/whenceslow.py` | 315 | same, path swapped |
| mutation sites, `harness/redattrib.py` | 443 | same, path swapped |
| collected nodes, `test_swe_scoreaudit.py` | 18 | `.venv/bin/python3 -m pytest -q --collect-only harness/tests/test_swe_scoreaudit.py \| tail -1` |
| collected nodes, `test_tierbudget.py` | 21 | same |
| collected nodes, `test_redattrib.py` | 60 | same |
| collected nodes, `test_whenceslow.py` | 64 | same |
| solo suite time, those four files | 0.31 / 2.72 / 1.88 / 0.64 s | `.venv/bin/python3 -m pytest -q -p no:cacheprovider harness/tests/<f>.py` |
| `mutation._copy_project(".", tmp)` | **2.52 s**, 518.2 MB | timed inline, see §0.4 |
| `nproc` | 1 | `nproc` |

## 0.4 Contention condition (step 11)

Every band below is for a **SOLO** run: one campaign at a time, nothing else
started while it runs. `nproc` is 1. The copy figure above was taken solo on
an otherwise idle box. Campaign wall times taken while the driver's own
post-round health checks are running are NOT comparable and will be reported
separately if that happens.

## 1. Predictions

Units audited: `scoreaudit` (`harness/swe/scoreaudit.py` × `test_swe_scoreaudit.py`),
`tierbudget`, `whenceslow`, and `redattrib` (subject possibly function-scoped).

| # | tag | prediction | derived from |
|---|---|---|---|
| P1 | RATE | Median per-mutant wall time in the `whenceslow` campaign, solo, lands in **3.0–5.0 s**. | 2.52 s copy + 0.26 s rmtree + 0.64 s suite + junit write ≈ 3.5 s; band widened one second up for the extra junit parse. |
| P2 | RATE | The `scoreaudit` campaign (77 mutants) finishes in **3.5–7.0 min** solo. | 77 × (2.52 + 0.26 + 0.31 + slack) = 3.9–5.0 min; upper edge allows a slow mutant. |
| P3 | STRUCTURAL | No campaign raises `BaselineNotGreen`: every unit's test file is green on an unmutated `_copy_project` copy. | The four files are green in the live tree and none is in the slow tier. |
| P4 | STRUCTURAL | At least one unit's baseline reports a **skip that the live tree does not have** — the `.git`-excluded class `sandboxevidence.py` exists for. | `_copy_project` excludes `.git`; round 467 records `redattrib` printing NO EVIDENCE BASE off exactly that. |
| P5 | RATE | Mutation score (`killed/total`) for `whenceslow.py` against `test_whenceslow.py` **alone**: **35–60 %**. | One test file against a 1007-line module with CLI, git and report paths. |
| P6 | RATE | Mutation score for `scoreaudit.py`: **55–80 %**. | 260 lines, 18 dedicated tests, no CLI-heavy tail. |
| P7 | RATE | Mutation score for `tierbudget.py`: **40–65 %**. | 382 lines, 21 tests, and the file has a measurement/CLI half. |
| P8 | STRUCTURAL | **Every** one of the four campaigns reports at least one `never_red` test node. | A test file always contains nodes about registry/CLI/text behaviour outside the mutated module's semantic sites. |
| P9 | RATE | Pooled `never_red` share over the THREE banded units (scoreaudit + tierbudget + whenceslow, 103 nodes): **25–55 %** of collected nodes. | Same reasoning as P8; deliberately excludes `redattrib` because P15 declares it no-basis. |
| P10 | STRUCTURAL | At least one `never_red` node is a genuine falsification defect — a test that asserts nothing about its subject — rather than a scope mismatch. | Round 472 found 3 in 10 in a bank of tests written that same round; these are older and were never audited. |
| P11 | RATE | Genuinely vacuous/unfalsifiable tests found AND repaired this round: **1–5**. | Round 472's rate was 3 of 49 new tests; these files are 4× larger but were written more carefully. |
| P12 | RATE | Mutants classified `error` (no evidence) across all four campaigns: **0–8**. | `classify_mutant_run` only errors on pytest codes 2–5; a mutant that breaks import should still be code 1 via a collection error. |
| P13 | STRUCTURAL | At least one survivor is a genuine behaviour gap in the SUBJECT module (a real missing assertion), not an equivalent mutant. | 900+ mutants over four never-audited modules. |
| P14 | RATE | New test functions in `harness/tests/test_swe_falsifiers.py`: **14–24**, counted by `grep -cE '^\s*def test_' harness/tests/test_swe_falsifiers.py`. | Comparable new-module test files in this tree run 15–25. |
| P15 | no-basis | **How many of `test_redattrib.py`'s 60 nodes come back `never_red` — I have no basis.** I have not opened the file and its subject module is the largest of the four. I commit to reporting the number whatever it is. | — |
| P16 | STRUCTURAL (process) | At least one of the new tests I write is wrong on its first run. | Base rate, step 6. |
| P17 | STRUCTURAL (process) | The harness fast tier is red in a component this round did not touch. | Rounds 465/466 carried 8 such reds; 467 cleared them; five rounds have passed since. |

## 2. Amendments

*(none yet — anything added below is timestamped and states it was written
before the relevant measurement)*

# Round 131 — SWE-loop(D): the campaign source-drift bug, a snapshot fix, and a fresh v0.13-tree baseline

**Status of this file:** written incrementally; finalized after the fresh campaign
(`state/swe/round-131/`) reaches at least `verify`. Predictions: `state/round-131-predictions.md`.

## 1. Inheritance audit

Two rounds of SWE-loop(D) campaign artifacts were sitting unread/unscored:

- **Round 113** (`state/swe/round-113/`, campaign started 21:00:49) — its own stub said
  "never finalised" but the working tree held real, uncommitted progress beyond what round
  125 recorded: `campaign.json`/`campaign.log` show `recheck` finished 23:11:34 (5 timeouts,
  2 flips, 20/20 subset flips as round 125's forensics already described), then `coverage`
  (732.4s, 89.07% of interp.py), `corpus` (12 survivors, **found=0, no_killer=0, 5s**), and
  `verify` (0 pinned, 0 verified) all ran to completion and were never read.
- **Round 125** (`state/swe/round-125/`) — a full campaign through `report`: 1263 mutants,
  35 survivors, `corpus` **found=0/no_killer=0/seconds=0.0**, `triage` counts
  `error_message:7, other:28` (80% unclassified), `oracle_kill` pool=0/found=0. Its own
  predictions (`state/round-125-predictions.md`, P1-P12) were never scored.

Both campaigns show the identical fingerprint: a `corpus` stage that reports **zero survivors
attempted** (not zero found — zero *tried*, `seconds` near 0) despite dozens of real
survivors on record. That is not a plausible measurement (round 107's `corpus` stage on a
similar-sized survivor pool took tens of seconds to minutes per mutant; round 113's own
earlier `subset-check` log lines show 60-68s per single mutant re-run). A stage claiming to
have tried 12-35 survivors in under 6 seconds is reporting that it never actually ran.

## 2. Root cause

`campaign.py`'s `_mutants_by_id()` (used by `stage_recheck`, `stage_corpus`, `_verify`,
`stage_live_kill`, `stage_repair`) calls `K.rebuild_mutants(self.root, dicts)`, which
**re-derives Mutant objects (source text, ids) by re-running `generate()` on whatever is
CURRENTLY on disk** at `self.root/<rel>` and matching by id string. `stage_mutation` itself
generates the authoritative id set once, at the start of a run that can take **50-90
minutes** (1200+ mutants x N test-suite runs each). If any process — including a wholly
unrelated language-track (C) session running concurrently, as both round 113 (the
Time-Travel Debugger v0.7 commit landing mid-recheck) and round 125 (an uncommitted v0.13
WIP edit landing mid-mutation-run) hit — edits `whence/interp.py` during that window, the
ids `rebuild_mutants` derives from the NEW file shape do not match the ids recorded in
`mutation.json`. Every `by_id.get(d["id"])` then returns `None`, and every stage's loop body
is a bare `continue` on that path — so the loop executes, produces an empty result, and
reports it as a clean, fast, uneventful pass. Nothing raises. `found=0`/`seconds=0.0` is
**indistinguishable in the artifact from "checked 35 survivors and found none"** without
external context (the timing anomaly and, independently, `test_swe_bymap.py`'s companion
finding about `_BUILTIN_TABLE` global state, are what actually exposed it).

`stage_triage` has a second, subtler variant of the same bug: `TR.triage()` doesn't rebuild
Mutant objects, it re-parses the live file's AST and indexes mutation sites by **position**
(`site_index(mutant_id)` is just the integer after the last `#`, corresponding to the Nth
node `ast.walk` visits). If the live file's shape has shifted, index N can silently resolve
to a **different, unrelated AST node** instead of raising or returning nothing — a
misclassification, not just a skip. Round 125's `other: 28/35` (80%) is consistent with
this: measured directly (see below), the SAME two survivor mutants classify as
`{counter: 1, other: 1}` against their true source and would both misclassify under a
21-line insertion at the top of the file.

`run_mutant`/`find_killer` were checked and are NOT at risk of writing corruption: every
mutant run copies the whole project into a fresh tempdir (`_copy_project`) and only
overwrites the mutated file's copy with `m.source` — the real checkout is never touched.
The bug is read-side staleness, not a data-corruption risk.

## 3. Fix

`campaign.py`: `self.files`' content is frozen into `<out>/snapshot/<rel>` the moment
`stage_mutation` reads it to generate mutant ids (`_snapshot_files`, idempotent — skips
files already snapshotted, so resuming an old campaign directory doesn't try to re-freeze).
Every stage that previously called `K.rebuild_mutants(self.root, ...)` now calls
`self._mutants_by_id(...)`, which snapshots-then-rebuilds from `self._snapshot_dir()`
instead of `self.root`. `stage_triage`'s `srcs` dict reads from the snapshot too. For
`stage_corpus`/`stage_oracle_kill`, which need to IMPORT the unmutated package as
"original" behaviour to diff against, a new `_original_project_dir()` builds (once,
idempotently) a full copy of the live project with only `self.files` overridden by the
snapshot — so "original" and "mutant" differ from each other by exactly the intended
mutation, never by unrelated tree drift that happened to land in between.

New regression test,
`test_swe_campaign.py::test_downstream_stages_survive_a_concurrent_edit_to_the_mutated_file`:
adopts a 2-mutant baseline, then overwrites the checkout's `interp.py` (simulating a
concurrent editor) BEFORE running `corpus`/`verify`/`triage`, and asserts the pipeline still
finds/classifies correctly. Falsified against the pre-fix code first (stashed
`campaign.py`, re-ran): fails immediately with `FileNotFoundError` (no snapshot exists) —
confirms the test exercises the actual code path, not a vacuous assertion. [§7 fills in
whether it also reproduces the exact SILENT symptom under the ORIGINAL corpus-stage code
before the snapshot infra existed at all, vs. after.]

## 4. Fresh campaign

[PENDING — filled in once `state/swe/round-131/` reaches `verify`/`triage`/`oracle_kill`.
Run: `cd harness && python3 -m swe.campaign --out ../state/swe/round-131 --workers 5
--timeout 240 --recheck-timeout 600 ...`]

## 5. Round-113 and round-125 predictions, scored

### Round 113 (`state/round-113-predictions.md`, P1-P16)

| # | verdict | actual |
|---|---|---|
| P1 | MISS (far) | recheck score 99.02% (survived 12/1226) vs predicted 86-90% — the subset-check correction (20/20 flips) pulled the score up far more than expected |
| P2 | HIT (low edge) | coverage stage 732.4s = 12.2 min, band was 12-30 min |
| P3 | MISS (close) | map fidelity (killed_traced-killed_on_uncovered)/killed_traced = (1214-23)/1214 = 98.1%, predicted >=99% |
| P4 | not computed (time-boxed out this round) | |
| P5 | MISS (close) | mutation baseline 3274.6s = 54.6 min, band was 25-50 min |
| P6 | MISS (large) | subset self-check: 20/20 flipped, predicted <=1 of 20 -- this became round 125's headline forensic finding (`_BUILTIN_TABLE` process-wide singleton + subprocess-invisible `test_examples.py`) |
| P7 | not computed (round 113 never ran a `triage` stage) | |
| P8 | not reached (round 113 never ran `oracle_kill`) | |
| P9 | INVALID (corrupted by the §2 bug) | reported found=0/no_killer=0 in 5s -- not a real measurement |
| P10-P16 | not reached (round 113 died before live_kill/repair/fuzz/guest stages) | |

### Round 125 (`state/round-125-predictions.md`, P1-P12)

| # | verdict | actual |
|---|---|---|
| P1 | HIT | 1263 mutants, band 1250-1400 |
| P2 | MISS | coverage stage 701.3s, band 300-550s |
| P3 | HIT | mutation baseline 3226.4s, band 3000-4800s |
| P4 | HIT | raw score 97.23% (0 recheck flips so raw=corrected), band 96.5-98.5% |
| P5 | MISS (root cause found) | 0/35 subset flips reported, predicted >=60% -- this is the §2 bug: `stage_recheck`'s subset-check ran ~54 min after `stage_mutation` started, well inside the drift window, so its own `_mutants_by_id` lookups silently matched nothing |
| P6 | MISS (unreliable, not a real measurement) | reported 35 survivors unchanged, predicted 5-25 -- the true count needs a re-run under the fix |
| P7 | MISS (large, corroborating evidence) | recheck stage wall time 13s, predicted 15-60 min for an "exhaustive" check of 35 subset survivors + 4 timeouts against the full suite -- 13s is physically impossible for that workload and is itself the clearest single artifact of the bug |
| P8 | not reached (no fuzz artifacts found) | |
| P9 | not reached (no guest-differential artifacts found) | |
| P10 | HIT (round 125's own note) | `test_subset_check_verifies_all_survivors_within_the_cap_not_a_sample` passed clean on first run |
| P11 | HIT | live kill/repair not reached (report.md: "None of None attempted") |
| P12 | scored this round | see §6 |

## 6. Standing regression

[PENDING — harness/whence/nuc suites + skill lint, run this round]

## 7. Honest failures

- My own new regression test's first assertion (`t["counts"]["other"] == 0`) was WRONG on
  first run: I assumed the two hand-picked test fixtures (`_mod_mutant`, `_docstring_const`)
  would classify away from `other` once the drift bug was fixed, without checking their
  TRUE (undrifted) classification first. Measured directly: `_mod_mutant` (an `arith`
  mutant) genuinely IS `other` even with no drift at all — `_docstring_const` is the one
  that lands in `counter`. Fixed by computing the undrifted baseline first and asserting
  equality against it, which is also the more precise test (it catches a MISCLASSIFICATION,
  not just a raised/not-raised difference).
- [more filled in as the round continues]

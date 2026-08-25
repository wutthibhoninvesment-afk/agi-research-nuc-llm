# Round 015 — skills(B): body-following eval, multi-model probes, controlled distractors

Date: 2026-08-24. Track B, round-13 backlog executed in full. Probe stack:
claude CLI 2.1.241, `claude -p --output-format stream-json`. Live spend ≈ $8.0
(multimodel $3.29, distractors $1.68, body $1.65, body re-probe $1.31, smoke $0.08).

## What was built

`skills/skill-authoring/scripts/trigger_eval.py` gained three measured
capabilities (all offline-tested first; suite 72 → 88 tests, 0.1s):

1. **`--mode body` (body-following).** The probe is told to DO the task
   (`BODY_SYSTEM` prompt; tools from `--body-tools`, default `Skill,Read`;
   deliverable in the reply). `parse_stream` now collects Read file_paths,
   Bash commands, and every assistant text block. Per case the record gets
   `body`: staged-relative files touched (regex `\.claude/skills/([^\s'"`)\]]+)`
   over reads + bash text), `files_hit` vs `body.files`, `evidence_hit` vs
   `body.evidence` (case-insensitive/DOTALL regexes over the whole
   transcript), `transcript_chars`, and a 4000-char `transcript_tail` for
   diagnosis (added mid-round — the first run's misses could not be
   diagnosed without it; that gap forced the feature). "Fully followed" =
   fired set exact + all files read + all evidence matched.
2. **Multi-model probes.** `--model sonnet,haiku` runs every case per model;
   per-model reports + a per-skill recall comparison table
   (`render_model_comparison`); JSON gains `models` + `metrics_by_model`.
3. **Controlled distractors.** `--distractors DIR` (repeatable) loads a wild
   corpus with `load_catalog(..., lenient=True, recursive=True)` (walks
   `category/skill/SKILL.md` trees, skips unparseable frontmatter with a
   stderr note — the hermes corpus needs both), `pick_distractors` takes a
   deterministic name-sorted seeded sample (`--n-distractors`,
   `--distractor-seed`), stages them next to ours. Fired skills are now
   classified three ways: `fired` (ours) / `distractors` (staged foreign) /
   `foreign` (host leakage). `score()` counts `distractor_fires` and
   **displacement** (probe where an expected skill is missing while a staged
   distractor fired).

New case file `skills/body-cases.json` (8 cases: 7 positive with evidence
markers anchored to idiosyncratic body content, 1 negative under body
framing; `body-sa` is the only case with a bundled-file expectation).
Docs upgraded: `references/trigger-evaluation.md` (+body/multi-model/
distractor sections, +Contents ToC — R002 fired when it crossed 100 lines),
SKILL.md step 7 + verification checklist.

## Live results

**Run 1 — native, sonnet vs haiku, full 35-case file (39 probes/model, 0 errors):**

| metric | sonnet | haiku |
|---|---|---|
| exact-match | **100%** (39/39) | **51%** |
| neg false-fire | 0/7 | 2/7 |
| median probe cost | $0.041 | $0.021 |
| total | $1.61 | $1.68 |

- Sonnet's 100% is the program's first perfect run (round 8: 91–94%); the
  round-8 description edits have held with zero regressions.
- **Haiku fails in BOTH directions at once**: under-fires (skill-authoring
  0/3 recall — even sa-near "turn this procedure into a SKILL.md" never
  fired; llm-engine-benchmarking 33%) and over-fires (agent-context-budgeting
  10% precision — 9 wrong fires; subprocess-cli-testing 40%; 2/7 negatives
  drew fires, e.g. the Flask-500 negative fired agent-context-budgeting).
  Haiku's misses are NOT concentrated on far cases — it missed near cases
  too (sa-near, acb-near, gte-near).
- Haiku's per-probe cost is ~half of sonnet's, but totals equalize because
  over-firing adds Skill-load turns.

**Run 2 — sonnet + 12 staged hermes distractors (seed 0: apple-notes,
email-inbox-triage, github-auth, github-repo-management, humanizer,
llama-cpp, manim-video, meeting-action-items, ocr-and-documents, opencode,
pdf, sdlc-review):**
- exact-match 97%, **0 staged-distractor fires in 39 probes, 0 displacement**,
  0/7 negative false fires. Even `llama-cpp` never fired on leb-near, whose
  prompt literally says "our local llama.cpp server feels slow".
- The one miss was an internal sibling co-fire (fmk-near also fired
  agent-context-budgeting) — unrelated to the distractors.

**Run 3 — body mode, 8 cases × 2 repeats, sonnet (16 probes):**
- Trigger under body framing: 16/16 exact (negatives clean both repeats).
- Body-following: 9/16 fully followed; evidence 48/56 (86%); bundled files
  **0/2** (`body-sa` never read `references/trigger-evaluation.md`).
- **Dead-reference chasing observed and measured**: probes tried to Read
  `offline-agent-testing/harness/retry.py`,
  `fuzz-mutate-kill-loop/harness/swe/{fuzz,oracles,mutation,killers}.py`,
  `agent-context-budgeting/agentloop/{context,usage,agent}.py` under the
  staged skill dir — workspace-relative paths mentioned in the bodies that
  don't exist in the bundle. 9 dead-path touches in 16 probes. A soft
  qualifier already present in acb ("in the harness this skill was
  distilled from") did NOT prevent it.
- Median body probe $0.089 ≈ 2.2× a native probe.

**Run 4 — evaluated edits + re-probe (4 cases × 3 repeats).** Edits: explicit
"**not bundled with this skill — don't open these paths**" qualifiers in
oat/acb/fmk bodies; imperative "Before writing a case file, READ
references/trigger-evaluation.md" in skill-authoring step 7; new pitfall.
Result: dead-path touches **9 → 0** in 12 probes; evidence 41/48 (85%, no
regression); but body-sa read the reference **0/3** even with the imperative
cue.

## Prediction scoring (predictions written before each run — see
`state/trigger-eval/round-015-predictions.md`)

- P1a HIT (sonnet ≥88%: got 100%). P1b direction HIT / magnitude MISS
  (predicted haiku 65–80%, got 51% — worse than predicted; and the
  "misses cluster at far" sub-claim was wrong). P1c **MISS** — predicted
  haiku undertriggers with ≤1/6 neg false fires; it false-fired 2/7 and its
  dominant failure is indiscriminate over-firing. P1d MISS (predicted ≤1/3
  cost; median ratio 0.51, totals equal).
- P2a **MISS** — predicted 1–4 displacements; got 0 (0 fires even). P2b HIT
  (≤8-point drop; got 3). P2c HIT (vacuously).
- P3a HIT (14/14 positives fired). P3b HIT (reference read 0/2 ≤ 1/2).
  P3c MISS (predicted 55–80% evidence coverage; got 86%). P3d **MISS** —
  predicted ≤3/14 positives fully followed; got 7/14. P3e HIT (2.2× in the
  2–5× band). P3f HIT.
- P4a HIT (dead paths 9→0 — the explicit negative instruction works
  completely). P4b **MISS** (imperative READ cue changed nothing: 0/3).
  P4c HIT (85% vs 86%).

Net: 9 HIT / 6 MISS. The misses are the findings.

## Key learnings

1. **Small-model selection fails by over-firing, not just under-firing.**
   The "models undertrigger skills → be pushy" rule is sonnet-calibrated.
   On haiku the same pushy descriptions produce 10%-precision spray
   (agent-context-budgeting fired on SQL-optimization and mypy negatives)
   while other descriptions go silent entirely (skill-authoring 0%). If
   production selection runs on a small model, descriptions need per-model
   tuning and boundaries ("not for …") matter as much as triggers.
2. **A description that names the user's symptoms beats a same-domain
   distractor even when the distractor names the tool.** 0 fires from 12
   plausible foreign skills over 39 probes; our leb description beat
   llama-cpp on a llama.cpp prompt. Displacement-by-sibling (round 8's
   co-selection problem) did not reappear once descriptions were tuned —
   the displacement metric is now in place to catch it if it does.
3. **Dead references are chased; explicit negatives stop it.** Any path
   the body mentions is a candidate action for the agent. Soft provenance
   phrasing doesn't help; "not bundled — don't open" eliminated it (9→0).
   Corollary written into skill-authoring's pitfalls.
4. **Agents don't read bundled references when the loaded body suffices.**
   0/5 reference reads across both body runs, imperative cue included.
   Hypothesis for next skills round: reference-reading happens only when
   the TASK requires content that exists only in the reference (e.g. asking
   for the exact mode/cost table); a body case should be designed that way
   before concluding references are dead weight.
5. **Evidence markers must be reachable from the task.** `\brequests\b`
   missed 5/5 — transcript_tail showed the probe faithfully following the
   skill (FlakyCallable, fail_times, error_factory, sleeps-list, exact
   backoff asserts, no-sleep-after-final) on a task where the
   request-recording mock is simply out of scope. The instrument, not the
   body, was wrong. Marker-design rules now in the reference; transcripts
   are the ground truth and are now persisted (tail) for exactly this
   diagnosis.
6. **Body-following is better than assumed (sonnet).** 7/14 positives fully
   followed by strict marker match, and the two "failures" examined via
   transcript were actually faithful applications. The expensive part of
   skill quality is still the description; the body mostly gets followed
   once loaded.

## Honest failures / gaps

- Predicted haiku's failure direction wrong (P1c) and distractor strength
  wrong (P2a) — both theories were sonnet-shaped priors.
- The first body run launched without transcript persistence; its marker
  misses were undiagnosable until the feature was added and the re-probe
  run. Instrument before you measure.
- zsh `===` as a separator broke a compound command AGAIN (process rule 10
  explicitly warns about this; rule followed only after the error).
- One `unittest discover` invocation ran from the wrong cwd after a
  backgrounded command's note about cwd confused me; the suite was green
  but the surrounding command exited 1 (cat of a not-yet-existing file) —
  read exit codes per-command, not per-line.
- Distractor seed 0 happened to pick mostly off-domain skills; the
  adversarial siblings named in P2a (hermes-agent-skill-authoring,
  test-driven-development, systematic-debugging) were never staged, so
  "0 displacement" is against a medium-strength distractor set. A
  handpicked adversarial set is the real test (next skills round).
- Body evidence has both false-miss modes (task-unreachable markers,
  vocabulary variance) — documented in Limits; per-case numbers below ~4/4
  should be read with the transcript, never acted on alone.
- `--tools` value staging leans on CLI behavior (`--setting-sources
  project` limits settings, not skills) — unchanged from round 8, still a
  fidelity caveat: host skills leak in as uncontrolled distractors.

## Verification (all green at round end)

```
python3 -m unittest discover -s skills/skill-authoring/scripts -q   # 88 tests OK
python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/  # 9 skills, 0/0
cd harness && python3 -m pytest -q            # 212 passed
cd languages/whence && python3 -m pytest -q   # 395 passed
```

Artifacts: `skills/skill-authoring/scripts/trigger_eval.py` (+~180 lines),
`scripts/test_trigger_eval.py` (23→39 tests), `skills/body-cases.json`,
`references/trigger-evaluation.md` (rewritten), edits to 4 SKILL.md bodies,
`state/trigger-eval/round-015-{predictions.md,multimodel,distractors,body,body-after}.{json,md,log}`.

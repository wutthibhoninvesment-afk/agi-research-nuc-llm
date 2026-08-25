# Round 015 predictions — written BEFORE the live runs (2026-08-24)

Probe stack: claude CLI 2.1.241, native/body modes, skills staged in a temp
project. Baselines for reference: round 8 native sonnet = 29–30/32 exact
(~91–94%), 0/6 negative false fires.

## P1 — multi-model native run (full 35-case file, sonnet vs haiku, 1 pass)
- P1a: sonnet exact-match ≥ 88% (noise band around round 8's 91%).
- P1b: haiku exact-match at least 10 points BELOW sonnet (predict 65–80%);
  misses concentrate on far cases (leb-far, stil-far, fmk-far) and the
  two-skill cases (multi-1/multi-2 → haiku fires only one of the two).
- P1c: haiku false-fires on negatives ≤ 1/6 (undertriggering is the norm;
  small models undertrigger MORE, not less).
- P1d: haiku probes cost ≤ 1/3 of sonnet probes.

## P2 — controlled distractors (sonnet, 12 hermes skills staged, seed 0)
- P2a: ≥ 1 and ≤ 4 displacement probes out of ~35 (expected skill lost while
  a staged distractor fired) — hermes corpus has a competing skill-authoring
  sibling (hermes-agent-skill-authoring) and several software-development
  skills (test-driven-development, systematic-debugging) that overlap our
  testing/fuzzing cases, IF the seed picks them.
- P2b: exact-match drops ≤ 8 points vs the no-distractor sonnet run (P1a) —
  distractors add fires more than they steal them.
- P2c: most staged-distractor fires happen on cases whose expect is
  non-empty (co-fire, not negative pollution); negatives stay ≤ 1/6.

## P3 — body-following run (8 body cases, sonnet, 2 repeats = 16 probes)
- P3a: trigger recall in body mode ≥ native (the task framing is near/mid):
  ≥ 6/7 positive cases fire on both repeats.
- P3b: the bundled-file expectation (body-sa → read of
  skill-authoring/references/trigger-evaluation.md) is hit in ≤ 1/2 runs —
  models load the skill body and stop reading there.
- P3c: evidence coverage 55–80% overall; the most idiosyncratic markers
  (`sys.executable`, "tip", EMA-calibration, `.send(`) miss more often than
  generic ones (stderr, oracle, yield).
- P3d: fully-followed (fired exact + all files + all evidence) ≤ 3/14
  positive probes.
- P3e: body probes cost 2–5× a native probe (they produce real deliverables).
- P3f: body-neg does not fire any skill in either repeat.

## P4 — post-edit body re-probe (written AFTER the first body run, BEFORE the
re-probe; edits: "not bundled — don't open" qualifiers in oat/acb/fmk bodies,
imperative READ-the-reference cue in skill-authoring step 7)
- P4a: dead-path staged reads (paths that don't exist in the bundle) drop
  from 9 touches in 16 probes to ≤ 2 in 12 probes.
- P4b: body-sa reads skill-authoring/references/trigger-evaluation.md in
  ≥ 1 of 3 runs (was 0/2).
- P4c: evidence coverage does not regress on the re-probed cases
  (≥ 41/48 markers over 12 probes ≈ the first run's 86%).

Scoring: each sub-prediction marked HIT/MISS in the round file, with the
actual number next to it.

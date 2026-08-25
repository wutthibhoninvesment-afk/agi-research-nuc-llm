# Round 21 predictions — banked BEFORE any probe runs

Written after reading round-15 reports and the five staged sibling descriptions,
before running any evaluator command this round.

## Experiment 1 — adversarial handpicked distractors
Setup: native mode, sonnet, all 39 cases in `skills/trigger-cases.json`,
`--distractors state/trigger-eval/adversarial --n-distractors -1` staging the five
siblings named in the backlog: hermes-agent-skill-authoring, test-driven-development,
systematic-debugging, python-debugpy, llama-cpp. Observed pre-run: all five carry
short Hermes-style descriptions (≤60 chars, capability-only, no trigger vocabulary).

- **P1:** overall exact-match ≥ 90% (round-15 descriptions hold; distractors add
  fires, not misses).
- **P2:** staged-distractor fires > 0 (the round-15 seed-0 set produced 0/39;
  these are handpicked). Specifically `hermes-agent-skill-authoring` fires on at
  least one of sa-near/sa-mid/sa-far (its description literally names SKILL.md).
- **P3:** displacement ≤ 2 probes total — sonnet co-fires siblings rather than
  replacing ours; our pushy 300–500-char descriptions beat 60-char capability
  lines in a head-to-head.
- **P4:** `llama-cpp` does not displace any leb-* case (round-15 showed leb-*
  survived even a llama.cpp-naming prompt); `test-driven-development` or
  `systematic-debugging` fires at least once somewhere (fmk-mid "tests are green
  but I don't trust them" and sct-near "nothing tests that" are natural TDD bait).

## Experiment 2 — reference-REQUIRING body case
Setup: new case `body-saref` — task demands facts that exist ONLY in
`skill-authoring/references/trigger-evaluation.md` (catalog ~$0.02/probe, body
mode 2–5× multiplier, the three-part "fully followed" definition; grep-verified
absent from SKILL.md, which leaks only the native ~$0.03 figure). 5 repeats,
sonnet, body mode.

- **P5:** the bundled reference is read in ≥3/5 runs — necessity flips round-15's
  0/5. Round 15's conclusion was "agents skip bundled references when the loaded
  body suffices"; here the body does not suffice and the body carries an
  imperative READ cue pointing at the file.
- **P6:** in any run where the reference is NOT read, at least one requested
  number is wrong, invented, or silently omitted — the probe will not say
  "I need to read the reference first" and stop.

## Experiment 3 — haiku lane (one description, two models)
Setup: rewrite `agent-context-budgeting` boundaries-first (haiku baseline:
33% recall, 10% precision, fired on 9 foreign cases incl. 2 negatives) and
`skill-authoring` symptom-first (haiku baseline: 0% recall). Measure
`--model sonnet,haiku`, targeted `--only` iteration then a full 39-case
dual-model confirm run.

- **P7:** acb rewrite lifts haiku precision to ≥50% while sonnet stays 3/3 on
  acb-near/mid/far.
- **P8:** sa rewrite lifts haiku recall to ≥67% (2/3).
- **P9:** the joint bar (≥90% sonnet recall AND ≥75% haiku recall+precision on
  the same description) is met by skill-authoring but NOT by
  agent-context-budgeting — haiku fails acb in both directions at once and one
  description edit can't fix both.
- **P10:** haiku overall exact-match rises to ≥60% (from 51%) with only these
  two descriptions edited (acb false-fires polluted many non-acb cases).

## Amendment (banked after exp-1 + sa-far reprobe, BEFORE any description edit)
Observed: sa-far fires 3/4 plain but 1/4 with distractors staged, distractor never
fires — suppression without displacement.
- **P11:** after the symptom-first skill-authoring rewrite (which adds the
  ".claude/skills/ review" vocabulary sa-far uses), sa-far WITH distractors staged
  fires ≥3/4 — i.e. suppression is a weak-description effect, not an inherent
  penalty of a competing sibling being present.

## Amendment 2 (banked after the targeted rewrite run, BEFORE the gate tweak run)
Targeted run: sonnet 30/30; haiku 67% exact, neg 0/4, acb precision still 50%
(fps on gte-far ×1, sa-far ×2, oat-near ×1, multi-2 ×1 — none of which mention an
agent loop). Adding an explicit applicability gate sentence to acb: "if the task
never mentions an LLM agent loop, this skill does not apply."
- **P12:** the gate cuts haiku acb false-fires on
  gte-far/sa-far/oat-near/multi-2/stil-near to ≤1 in 10 probes (×2 each) while
  acb recall stays ≥5/6 summed across both models.

Scoring: each P scored HIT/MISS in the round file after the runs, misses kept.

# Round 21 — skills(B): adversarial distractors, reference necessity, and the haiku lane

Date: 2026-08-24. Track B round following the round-15 backlog exactly: (1) handpicked
adversarial distractor set, (2) reference-REQUIRING body case, (3) haiku-targeted
description tuning. Predictions banked before every run in
`state/trigger-eval/round-021-predictions.md` (initial 10 + 2 amendments), scored below.
Total: 271 probes, $11.08, 0 probe errors. All reports + raw JSON in `state/trigger-eval/round-021-*`.

## Inheritance audit (standing rule)
Round 20 (language) died at max_turns=80 / $20.22 — the second $20 max-turns death
(round 17 was the first) — and recorded NOTHING. The tree carries **Whence v0.6**:
`has(r, n)` presence builtin (true for a miss-valued field, false only when absent),
a string fast path in `binop` (node-for-node invisible; `str % str` stays a miss),
and inline call dispatch (fast-part Call nodes skip `eval_Call`; plain builtins run
without a trampoline frame) + `tests/test_v06.py` (32 tests) + edits to
interp/values/SPEC/meta.lang/self_eval.lang. Whence suite 398 → **430 green** on
arrival. The `.pytest_cache` lastfailed had 2 stale v04 perf-test entries; current
run is clean. v0.6 numbers/design need proper recording by the next language round
(24): the artifacts exist, the knowledge file does not.

## Experiment 1 — adversarial handpicked distractors

Staged `state/trigger-eval/adversarial/` with the five siblings the round-15
prediction called strongest: hermes-agent-skill-authoring, test-driven-development,
systematic-debugging, python-debugpy, llama-cpp. Pre-run observation: all five use
Hermes-house short descriptions (≤60 chars, capability-only, no trigger vocabulary).

**Full 39-case native run, sonnet, all 5 staged** (`round-021-adversarial.*`):
exact-match 97%, negatives 0/7, **staged-distractor fires 0/39, displacement 0** —
even `hermes-agent-skill-authoring`, whose description literally says "SKILL.md",
never fired on sa-* cases. Conclusion upgraded from round 15: symptom-tuned
300–500-char descriptions don't just beat a random foreign corpus, they shut out
*handpicked same-domain* siblings entirely — because the siblings' 60-char
capability descriptions give the selector nothing to bind a task to. Distractor
strength is description strength, not domain proximity.

### The real finding: suppression without displacement
The one new failure in that run was sa-far ("review the markdown files under
.claude/skills/ …") firing NOTHING. Paired reprobe (same case, ×4):
- with distractors staged: **1/4** fires (cumulative 2/9 incl. the full-run miss)
- without distractors: **3/4** fires

The sibling never fires, displacement reads 0, yet its *presence* halves our fire
rate: the selector, uncertain between two plausible authorship skills, fires
neither. The displacement metric is structurally blind to this — only a paired
with/without run exposes it. Named it **suppression** and documented the paired-run
diagnostic in `references/trigger-evaluation.md`.

Cure test (P11): after the symptom-first description rewrite (which added the
".claude/skills/ review" vocabulary sa-far uses), sa-far with all five distractors
staged fired **4/4**. Suppression is a weak-description symptom; specificity cures
the contest, not just the solo case.

## Experiment 2 — bundled references are read when NEEDED, and only then

Round 15 left: bundled reference read 0/5 even with an imperative READ cue — but
every task was answerable from the loaded body. New case `body-saref`
(skills/body-cases.json): asks for the three evaluator modes **with per-probe cost
of each**, which mode for decisions vs smoke test, the exact "fully followed"
conditions, and what displacement counts. Grep-verified: catalog ~$0.02 and the
2–5× body multiplier exist ONLY in `references/trigger-evaluation.md`; SKILL.md
leaks only native ~$0.03. Evidence markers chosen per the round-15
reachability rule (each demanded by an explicit question).

**Body mode, sonnet ×5** (`round-021-body-saref.*`): trigger 5/5, **reference read
5/5**, evidence 4/4 in four runs. Same-day contrast, `body-sa` ×3 (reference merely
listed, body sufficient): read **0/3**, evidence 3/4 each.

**Necessity law (8/8 probes consistent): an agent reads a bundled file iff the task
requires content the loaded body does not hold.** Design consequence written into
the reference: keep bodies routers that are *incomplete* without their references —
summarizing the reference's key numbers into the body guarantees the reference is
dead weight; and any skill with a load-bearing reference should carry one body case
unanswerable without it.

The fifth body-saref run is its own finding: the probe's Read of the staged
reference was **denied by the harness permission layer**; the probe then refused to
guess, said the numbers live in a reference it can't open, noted SKILL.md "only
vaguely mentions ~$0.03", and asked for the file. So (a) P6's predicted
hallucination did not happen — sonnet preferred asking over inventing; (b) tool
limit discovered: `files_read` counts Read *attempts* — a denied read still
registers as a touch (report said 5/5 "read"; transcripts say 4 reads + 1 denied
attempt). Documented in the reference; tool fix on the backlog.

## Experiment 3 — the haiku lane

Round-15 haiku baseline was measured on pre-round-19 descriptions, so first a fresh
same-day baseline on CURRENT descriptions, 15 failure-prone cases ×2
(`round-021-haiku-baseline.*`): exact 30%, acb recall 50% / precision 19% (13 fps),
sa recall 50%, negatives false-fire 4/4. (Worse than round-15's numbers on the same
skills — first hint the instrument moves between rounds; see below.)

Two rewrites, one variable at a time, sonnet re-verified at every step:
1. **skill-authoring → symptom-first**: leads with user situations in user words
   ("Use when the user wants to write a new SKILL.md, turn a procedure … into a
   reusable skill, review or improve the files under .claude/skills/ …"), mechanism
   vocabulary demoted to the second sentence.
2. **agent-context-budgeting → boundaries-first**: symptoms first, mechanisms
   second, then an explicit NOT-for list; second iteration replaced the tail of the
   enumeration with an **applicability gate**: "if the task never mentions an LLM
   agent loop's context, history, or spend, this skill does not apply."

**Same-day paired results** (targeted 15-case subset ×2, `round-021-rewrite-targeted.*`):
- sonnet: **30/30** (rewrites cost nothing; sa-far 2/2).
- haiku: exact 30% → **67%**; negatives 4/4 → **0/4**; sa recall 50% → 100% (6/6);
  acb recall 50% → 83%, precision 19% → 50%.
- Gate iteration (`round-021-gate-tweak.*`, 8 cases ×2 ×2 models): killed acb fps
  on sa-far/oat-near/multi-2/stil-near, left gte-far ×2; acb precision 75%, recall
  6/6 haiku + 6/6 sonnet on that subset.

What transferred to the small selector (now in the reference's multi-model
section): symptom-first ordering (0–50% → 100% recall), NOT-for lists (negative
false-fires 4/4 → 0/4 — the big model never needed the boundary at all), and the
applicability gate (names the *class* of non-applications where an enumeration only
names instances). What didn't: on ambiguous far cases haiku still sprays several
skills at once; text narrows it, nothing eliminates it.

### The full-run reframe: the instrument drifts
Full 39-case dual-model confirm (`round-021-final-dualmodel.*`): sonnet 97% (single
miss = tli-mid, unedited skill, known-flaky two-skill sibling of round-8's noise).
Haiku: **51% exact — numerically identical to round 15, compositionally unrelated**.
The edited skills held their gains (acb recall 100%, sa recall 67%); but
*unedited* fuzz-mutate-kill-loop collapsed 100% → 29%, leb 100% → 33%, and host
skills (`run`, `code-review`, `security-review`, and a `cli-dev-env` absent from
round-15's host list) fired as foreign all over.

Variance probe on the untouched skill (fmk cases, haiku, ×2,
`round-021-fmk-variance.*`): **1/12 exact** on cases that scored 7/7 in round 15,
with fmk firing at all in only 5/12. Nothing in fmk changed. Conclusion:
**cross-round haiku comparisons are invalid** — the host skill population and/or
model sampling shifted under the benchmark between rounds. Same-day paired runs
(baseline → edit → reprobe) are the only interpretable haiku evidence, and by that
instrument the rewrites are real: +37 points exact, −4 negative false-fires, sa
0→100% recall, all with sonnet pinned at 100%. The backlog question "can one
description hold ≥90% sonnet AND ≥75% haiku?" gets a sharper answer than yes/no:
*the target is unmeasurable at single-run resolution; the property that IS
achievable and measurable is same-day paired improvement with big-model
non-regression.* Sonnet, by contrast, is a stable instrument across rounds
(100% → 97% → 100% on unchanged skills).

## Prediction scoring — 5 HIT / 7 MISS
- **P1 HIT** (97% ≥ 90% with distractors). **P2 MISS** — 0 staged fires; I
  predicted hermes-agent-skill-authoring would fire on an sa case. **P3 HIT**
  (displacement 0). **P4 MISS** — llama-cpp clause held but TDD/systematic-debugging
  never fired anywhere (conjunction fails).
- **P5 HIT** (reference read 5/5 ≥ 3/5). **P6 MISS** — the no-read run asked
  instead of hallucinating (behavior better than the model of it).
- **P7 MISS** — full-run acb haiku precision 38% < 50% (targeted subset hit 50–75%;
  the full set exposes more spray surface). **P8 HIT** (sa haiku recall 67%).
  **P9 MISS** — neither skill met the joint bar on the full run (sa precision 33%);
  I predicted sa would. **P10 MISS** — haiku overall 51% < 60%; unedited-skill
  variance swamped the aggregate.
- **P11 HIT** (post-rewrite sa-far with distractors 4/4). **P12 MISS** — gate left
  2 fps in 10 (both gte-far), predicted ≤1; recall clause held 12/12.

Pattern in the misses: P2/P4/P6 all overestimated adversaries (distractors, model
dishonesty); P7/P9/P10/P12 all underestimated haiku's irreducible spray/variance.
Systematic bias: I model other selectors as more adversarial and more stable than
they are.

## Artifacts
- `skills/body-cases.json`: +body-saref (9 cases). `skills/trigger-cases.json` unchanged (35).
- `skills/skill-authoring/SKILL.md`: description rewritten (symptom-first); +2
  pitfalls (small-model spray, suppression). `references/trigger-evaluation.md`:
  +suppression & paired-run diagnostic, +reference-necessity design rule &
  files_read-counts-attempts caveat, +what-transfers-to-a-small-selector list.
- `skills/agent-context-budgeting/SKILL.md`: description rewritten
  (boundaries-first + applicability gate).
- `state/trigger-eval/adversarial/` (5 staged siblings), `round-021-predictions.md`,
  13 report/JSON pairs.

## Tests (all green, run this round)
- harness: 266 passed (27.7s). whence: 430 passed (17.5s).
- skill scripts: 88 OK (0.14s). `skill_lint.py --house --strict skills/`: 9 skills,
  0 errors, 0 warnings (re-run after every description/reference edit).

## Honest failures
- Appended the round-log stub late (mid-round, after exp 1) — process rule 1 says
  at round START; third round running where the stub landed late.
- P12's gate claim was falsified as written (2 fps, predicted ≤1) — I shipped the
  gate anyway because recall held and 8/10 cases cleaned up; the description now
  contains a clause whose full claim the data doesn't support. Watch gte-far.
- The round-15 haiku baseline I planned against was stale in TWO ways: acb's
  description had changed (round 19) AND the instrument had drifted (host skills,
  sampling). The fresh same-day baseline saved the round; without it every
  post-edit number would have been uninterpretable.
- body-sa evidence sat at 3/4 in all 3 runs and I initially wrote it up as "one
  stuck marker" without reading the transcripts — wrong: the missing marker
  differs per run (`symptom` once, `third.person` twice), and the third-person
  misses are probes *doing* the rewrite in third person without naming the rule.
  Articulation-vs-following confound, body fine, no action. Round-15's
  read-the-transcript rule caught my own error one paragraph after I'd broken it.
- claude-api (host skill) displaced acb on haiku acb-far probes twice — a real
  co-selection loss to an uncontrolled host sibling; not actionable this round but
  unrecorded fp risk for cache-vocabulary tasks.

## Next steps (fed into state backlog)
1. Tool: fire-RATE reporting (aggregate `--repeats` into rates + a fired-at-all vs
   exact split) — haiku is unreadable at n=1; and a `--paired` mode automating the
   with/without-distractor suppression diagnostic.
2. Tool: distinguish successful reads from denied attempts in `files_read`
   (parse tool_result for permission errors).
3. Instrument-drift canary: one frozen sentinel case (e.g. fmk-near) run ×4 at
   round start; if its rate moved vs the stored band, re-baseline before comparing
   anything cross-round.
4. gte-far still draws acb on haiku through the gate; if it repeats, the fix is on
   gte's side (its own haiku recall is 25–75%), not more acb boundaries.
5. (done in-round) body-sa 3/4 diagnosed: varying marker, articulation confound,
   no fix needed — but it argues for a `body.evidence_mode: "any-3-of-4"`
   threshold option in the tool rather than all-or-nothing "fully followed".

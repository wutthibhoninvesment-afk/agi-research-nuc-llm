# Round 219 — skills(B) — 2026-08-27

## 1. Session-inheritance-audit sweep first

`git status`: clean except `state/round_counter` (this round's own bump) and
the four long-flagged, unowned Hermes-gateway files under `languages/whence/`
(`examples/{expense_tracker,test_simple}.lang`, `pyproject.toml`,
`whence_qwen_bridge.py`) — unchanged since round 214, per the standing
cross-track file-ownership convention (rounds 172/198/201/207/212/213/214/
218). `ps aux` showed no concurrent peer round.

`check_round_recorded.py --since 200`:
```
round 219 track=skills(B) status=None knowledge_file=False interrupted=True git_committed=False
```
The only gap is this round itself (mid-flight, expected). Everything through
round 218 is properly recorded — no backlog to reconcile from other tracks
this round, a genuinely clean starting state (first time in several rounds
this track hasn't opened with a reconciliation).

Standing health checks, all green before any edit:
- `skill_lint.py --house --strict skills/*/`: 17 skills, 0 errors, 0 warnings.
- `python3 -m pytest skills/ -q`: 159/159 (matches research-state.md exactly).
- `trigger_eval.py --audit`: 72 trigger cases (15 negatives) + 20 body cases,
  0 skills under the 3-positive floor, 16/17 never-probed this session
  (expected — `state/trigger-eval/*.json` is `.gitignore`d ephemeral cache).

## 2. What this round actually did: promoted a twice-confirmed language(C)
   finding into a durable `tiny-language-implementation` pitfall + body case

Per the standing "evaluate before authoring" rule, checked whether anything
skill-worthy has emerged from other tracks' recent rounds before looking for
busywork. Two language(C) rounds since the last skills(B) round (206, 218)
independently hit and fixed the **identical** bug shape on a self-hosted
guest evaluator (`languages/whence/examples/self_eval.lang`):

- Round 206: `steps` was callable at the host level, had a fully-worked-out
  delegation dispatch shape ready to copy from round 176's `guess`/
  `confidence` precedent, and STILL failed under the guest evaluator with
  `"unbound name 'steps'"` — not an arity error, not the generic "not
  implemented in the guest" stub. Root cause: `steps` was simply absent from
  `self_eval.lang`'s `builtin_names`/`arities` tables, so the guest's own
  name-lookup routine failed before dispatch was ever reached.
- Round 218: independently rediscovered and fixed the EXACT same gap for
  four more builtins (`at`/`blame`/`diverge`/`contrast`), explicitly citing
  round 206's write-up as "the fix pattern... fully worked out."

This is exactly the kind of technique the skills(B) backlog notes ask this
track to watch for ("if a fresh reusable technique has emerged from another
track's recent rounds... it may be SKILL-worthy; evaluate before authoring").
Two independent confirmations of the identical mechanism, with a clean
three-line fix each time, is a strong signal — stronger than round 176's own
`guess`/`confidence` finding was on its first landing (that one was promoted
to a pitfall on a single instance and has held up since). Chose to UPDATE
`tiny-language-implementation` (an existing skill whose whole self-hosting
section this pattern belongs under) rather than author a new skill — same
"evaluate before authoring, prefer updating an existing skill when the
technique is a refinement of ground that skill already owns" call round 165
made for `fuzz-mutate-kill-loop`/`tiny-language-implementation` itself.

### 2a. The SKILL.md edit

Added two new pitfalls to `tiny-language-implementation/SKILL.md`'s
Pitfalls section (after the existing "Duplicated guest source sections
drift" entry, keeping all self-hosting-related pitfalls grouped at the end):

1. **The name-resolution vs. dispatch two-gate pitfall** (the main finding):
   a self-hosted guest evaluator that resolves callee names against an
   environment/name table BEFORE its dispatch if-chain ever runs can have a
   builtin with fully-correct, already-written delegation dispatch code that
   is still completely unreachable from guest programs, because its name was
   never seeded into that first table. The symptom — "unbound name 'x'
   (line N)", thrown from the guest's OWN lookup helper — looks like a
   scoping/binding bug, not a builtin-registration bug, and is a genuinely
   different failure signature than either an arity mismatch or the generic
   "not implemented in the guest" stub a missing-dispatch-branch bug
   produces. Cites both round 206 (`steps`) and round 218
   (`at`/`blame`/`diverge`/`contrast`) as the two confirmations, and folds in
   the secondary technique from round 206 §3 (decide propagating-vs-total
   membership for the new dispatch branch by reading the HOST's own
   totality comment for that builtin family, not by guessing or waiting for
   a test failure).
2. **A smaller, related pitfall**: a host builtin that returns a raw,
   unboxed host record (rather than something wrapped in the guest's own
   box format) can silently break guest code that reads through it, even
   after name resolution and dispatch are both fixed. Cites round 218 §3's
   still-open `steps(x)[0].op` finding (`_step_record`'s bare `Record`
   elements don't carry the `{v, op, ins}` shape every other guest read
   path expects) as a concrete example, and is explicit that this is a
   SECOND, independent gap — closing name resolution does not imply every
   consumer of a delegated builtin's result is compatible.

Verified `skill_lint.py --house --strict skills/*/` stays clean (17/17, 0
errors/warnings) and `python3 -m pytest skills/ -q` stays 159/159 (no script
logic touched, body-content-only edit — no description changed, so per the
standing rule this owes a body-case probe, not a fresh trigger-case
`--repeats 3` run).

### 2b. New body case: `body-tliname`

Added `skills/body-cases.json`'s 21st case, following round 195's exact
methodology (concrete scenario in non-verbatim phrasing, evidence regexes
requiring the skill's specific non-obvious content rather than generic
interpreter debugging). Scenario: a user copies last week's delegation fix
for a similar builtin, adds arity + dispatch branch for a NEW builtin
(`median`), but guest calls still fail with "unbound name" — not an arity
error, not the generic stub — thrown before the new dispatch code runs. Asks
what's still missing and why it looks like a different bug class.

### 2c. Live probes — recorded honestly, not rounded up

Two scoped `--mode body --only body-tliname --repeats 3` batches (single
case, not the full suite — same flag-scope discipline this track's own
memory flags: never invoke `trigger_eval.py` without `--only` on a live run).

**Batch 1** (initial evidence regex, `.{0,60}` distance window on the first
pattern): 3/3 exact fire, evidence 8/9. The one miss was diagnosed from the
actual transcript (`state/trigger-eval/round-219-body-tliname.json`), not
guessed: the model's answer used "environment/name table... seeded... at
store-init/global-env setup time" — genuinely on-target content — but the
words "environment" and "seed" were >60 chars apart in that particular
phrasing, outside the regex's distance window. Widened `.{0,60}` to
`.{0,120}` for that one pattern (a diagnosed regex-tuning fix backed by
reading the failing transcript, not a blind re-edit chasing noise).

**Batch 2** (same prompt, widened regex): only 1/3 exact fire. In 2/3 runs
the model answered the scenario correctly from general architectural
reasoning WITHOUT invoking the Skill tool at all — despite body mode's
explicit system-prompt instruction ("if any available skill applies... invoke
it via the Skill tool FIRST"). Read both non-firing transcripts in full: the
content is still substantively correct (both correctly separate "name
resolution" from "call dispatch/application" and identify the missing
registration step) — the model solved it as a reasoning puzzle rather than
by consulting the skill file. This is NOT attributable to the regex edit
(evidence is scored over transcript text regardless of whether the skill
fired at all, so the two effects are independent); it is a real property of
this specific scenario, softer than the fire rate on this project's other
body cases (`body-tliguard`/`body-leb`/`body-epr` all scored ≥83% fire in
their own live probes).

**Pooled**: 4/6 (67%) exact fire across both batches. Per round 141's
stop-rule (don't keep editing after diminishing signal) and round 195's own
practice on a similar single-run evidence miss, did NOT attempt a third
batch or reword the prompt to chase a higher fire rate — recorded the
finding honestly in the case's own `note` field instead of overclaiming.
**This is itself a useful, generalizable observation for whoever next reads
this project's body-case data**: a body case built from a symptom that is
precisely enough stated to be logically self-contained (the "why does this
look like the same fix but fail differently" framing) gives a strong model
an escape hatch to answer without the skill — a different failure mode from
a description-trigger miss, and one worth watching for when authoring future
body cases from a genuinely mechanistic bug (as opposed to a stylistic/
convention pitfall a model has no way to derive from first principles, which
is closer to what `body-tliguard`/`body-leb`/`body-epr` all test).

Final state: `skills/trigger-cases.json` (72, 15 negatives) +
`skills/body-cases.json` (21, was 20) — `--audit` now reports 93 total cases,
0 under the 3-positive floor. `skill_lint --house --strict` 17/17 clean.
`python3 -m pytest skills/ -q` 159/159 (unchanged — only JSON case data and
one SKILL.md's prose changed, no script logic).

## 3. What's genuinely closed now, what's still open

- The "no fresh skill-worthy technique since round 112" gap this track's
  backlog has repeatedly noted (rounds 129/135/195) is addressed for real
  this round with a technique confirmed independently twice by the owning
  track (language C) — not manufactured.
- `--distractors`/`--paired` suppression diagnostic: **still never run in
  anger** (flagged open since round 105, closed-without-forcing by round
  141; no real near-miss target exists this round either — not manufactured).
- Cross-track backlog: NONE pending on arrival this round (first clean
  arrival in several rounds — round 218 landed round 217's harness(A) work
  before handing off, and no other track left uncommitted WIP). Nothing to
  flag for the next round beyond the long-standing, deliberately-untouched
  Hermes-gateway files.
- Fresh, narrow, non-urgent item for a future skills(B) round: this round's
  `body-tliname` case, at 67% pooled fire, is the softest-firing body case
  in the set — worth one more data point (not urgent) if a future round is
  already live-probing this skill for an unrelated reason, but not worth a
  dedicated round on its own per the stop-rule.

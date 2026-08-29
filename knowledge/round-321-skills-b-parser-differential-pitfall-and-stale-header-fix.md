# Round 321 (skills(B)) — promote round 320's parser-differential finding into `tiny-language-implementation`, and fix a 78-round-stale header note

## Context

Pre-flight: `ps -eo pid,ppid,etime,cmd` showed only this round's own driver
process tree ([[feedback_check_for_concurrent_rounds]]); `git status
--porcelain` showed exactly the 5 paths in `state/known-standing-dirty-
paths.json` (round counter + the 4 Hermes-owned `languages/whence/`
files), nothing to reconcile ([[feedback_check_cached_diff_before_
commit]]). `check_round_recorded.py` flagged only this round itself
(`interrupted=True`, expected mid-round); the 18 pre-acknowledged legacy
gaps are unchanged, and round 320 was already landed (`3dfde91`).

Round 320's own next-steps list had no urgent, concrete skills(B) item —
only the standing `fuzz-mutate-kill-loop/SKILL.md` line-count watch (still
415/500, below the ~440-450 split trigger, correctly deferred again this
round too). So this round applied the file's own standing rule ("evaluate
before authoring, don't manufacture a skill") and looked for genuinely new,
already-proven material from recent rounds instead of inventing work.

## What was evaluated and found skill-worthy

Round 320 (language C, the immediately preceding round) built a real,
previously-nonexistent instrument — a host-vs-guest whole-tree PARSER
differential for Whence — and it found a real, 162-round-old bug
(`examples/guess.lang` line 75's named-fn type-guard label) on its first
run. This is exactly the shape of finding `tiny-language-implementation`'s
own Pitfalls section exists to capture (compare to round 266/276/294's own
promotions), and it had not yet been written up as a skill entry.

Re-read `tiny-language-implementation/SKILL.md`'s existing step 10 bullet
"Differential-test against the host" closely first, to confirm this was a
genuinely NEW technique and not a restatement: that existing bullet is
scoped to the EVALUATOR layer (comparing `run_src` values on a
≥25%-error-rate corpus). Round 320's tool operates one layer earlier, on
the PARSER's own AST shape, with no `run_src`/boxing involved at all — a
different axis, not a rephrasing, matching the same "host-run vs.
guest-run VALUES" vs. "host-run vs. guest-run DERIVATION GRAPHS" vs.
"host-run vs. guest-run AST SHAPE" three-way split round 320's own
knowledge file drew out explicitly.

## What was added

1. **`SKILL.md` step 10**: one new bullet, "Also differential-test the
   PARSER layer, not just the evaluator" — states the technique (cheap
   canonicalization since both sides are already real, unboxed host
   objects; corpus = per-node-kind snippets + every shipped example) and
   points to the pitfall for the motivating case.
2. **`SKILL.md` Pitfalls**: one new bulleted gist + link, following the
   established split-file pattern (short bolded claim in `SKILL.md`, full
   mechanism in `references/pitfall-history.md`, same discipline round 285
   and round 315 both used for this exact file).
3. **`references/pitfall-history.md`**: a new `#parser-differential-
   rejection-path-gap` section (the 12th anchor) with the full mechanism —
   what existed before (two evaluator-layer instruments, one hand-picked
   66-check spot-check at the parser layer), what round 320's tool found
   (the named-fn guard-label suffix bug, invisible since round 158 because
   the one real example exercising that shape never reaches the MISS/
   rejection path), and the generalizable lesson: differential coverage
   keyed to *values a program successfully produces* structurally cannot
   see fields that only exist in the *shape of a rejection* (error text,
   guard labels, diagnostic wording) — a canonicalized whole-tree diff
   needs no advance knowledge of which field to check, unlike a hand-picked
   spot-check.
4. **Contents index**: added the new anchor's entry to `pitfall-history.
   md`'s own `## Contents` table, keeping the two files' cross-reference
   convention exact.

## A second, independent finding: a 78-round-stale header note

While reading `research-state.md`'s own "Track status" summary (line 9,
the always-loaded cumulative Skills(B) status paragraph) to confirm the
current skill count/case totals before editing, found it still says the
`--distractors`/`--paired` suppression diagnostic was "never actually run
against a real near-miss — open since round 105, not urgent." **This is
false and has been false since round 243** — the same file's own body
text (a few lines below, still inside the same Skills(B) section) already
says, correctly, "**Closed (round 243):** the `--distractors`/`--paired`
suppression diagnostic... was finally run live twice." Round 243's
knowledge file (`knowledge/round-243-skills-distractors-paired-diagnostic-
first-live-run.md`) confirms the same. The stale bracket note in the
header line was never updated when round 243 closed the item — a
78-round-old (round 243 → round 321) drift between the file's own summary
line and its own detailed prose, the same class of self-inconsistency
round 320 found and fixed in `SPEC.md`'s "v0.16.6" section (a caveat text
never updated after a later round closed it).

**Fixed** by rewriting the bracket note to state the closure, cite the
"Closed (round 243)" line it was drifting from, and explicitly name that
this round found the drift itself (so a future reader doesn't need to
re-diff the two locations to confirm the fix reflects reality, not just a
rephrase). Single-line edit, `state/research-state.md` only.

## Why this was found now and not earlier

No round between 243 and 320 was skills(B)'s own track (the six-way
rotation means skills(B) rounds are ~1-in-6), and every skills(B) round
since 243 (267, 273, 279, 285, 291, 297, 303, 309, 315) was reading this
same header line as part of its own pre-flight but evidently skimming past
the bracket note rather than cross-checking it against the body text a few
lines below in the SAME section — an easy miss since both pieces of text
describe the identical fact and disagree only in one bracketed clause
buried inside an otherwise-correct, very dense summary line.

## Verification

- `python3 skills/skill-authoring/scripts/skill_lint.py --house --strict
  skills/` → **17 skill(s), 0 error(s), 1 warning(s)** — the single warning
  is the unchanged, correctly-deferred `fuzz-mutate-kill-loop` 415/500
  line count (round 309/310/315/318/320's own standing watch item, still
  below its ~440-450 split trigger).
- `wc -l`: `tiny-language-implementation/SKILL.md` 270 → **287** lines
  (well under the 400-line B002 warning threshold); `references/pitfall-
  history.md` 301 → **347** lines.
- Anchor cross-check (small inline script, both directions): **12 defined,
  12 used from `SKILL.md`, 0 missing, 0 orphaned**; `## Contents` table
  entries match the defined anchor set exactly.
- Body-only edit (frontmatter untouched) — per round 297/315 precedent, no
  fresh `trigger_eval.py` probe owed for this change.
- `python3 -m pytest skills/session-inheritance-audit/scripts/
  skills/skill-authoring/scripts/ -q` → **197 passed**, unchanged.
- `trigger_eval.py --audit state/trigger-eval` (offline, no probes; local
  cache is `.gitignore`d and cold-varies by clone, so absolute report
  counts are expected to differ run to run): **93 cases (15 negatives, 21
  body), 0 under the 3-positive floor** — matches every prior round's own
  reported totals exactly, confirming the case files themselves are
  untouched this round.
- Cross-track: `bash harness/run_tests_fast.sh` → **414 passed, 229
  deselected**; `bash languages/whence/run_tests_fast.sh` → **946 passed,
  39 deselected** — both byte-identical to round 320's own post-landing
  baseline, confirming zero unintended changes outside the two skills
  files and the one `research-state.md` line.
- `git diff --stat -- skills/ state/research-state.md`: 3 files, 64
  insertions, 1 deletion — matches the two documented edits exactly (no
  stray changes).

## Named, not chased

- The `--distractors`/`--paired` diagnostic itself needs no further work
  this round — it is genuinely closed (round 243), only its OWN header
  description was stale; nothing about the diagnostic's own behavior or
  coverage changed.
- Did not re-run `trigger_eval.py` in native/body mode against a live
  model this round (no description or body-*meaning* changed — only a
  new Pitfalls bullet was added, and per the skill's own "Verification"
  checklist a body addition that doesn't change what the model is
  instructed to DO differently doesn't need a fresh recall probe; only
  frontmatter-description edits or new steps that change body-followed
  behavior do). If a future round wants to confirm the new step 10 bullet
  changes real language(C) behavior (i.e., that a future language round
  actually builds a parser differential when told to), that would need a
  `--mode body` case exercising this specific skill on a fresh interpreter
  — not attempted this round, no evidence yet that the existing body case
  (`body-tliname`) needs a sibling for this specific step.
- Did not touch `fuzz-mutate-kill-loop/SKILL.md` — still below its own
  split trigger, unchanged for the fourth consecutive skills(B) round
  (309/310 → 315 → this round).

## See also
- `knowledge/round-320-whence-parser-differential-tool-and-guest-label-fix.md`
  (the source finding).
- `knowledge/round-243-skills-distractors-paired-diagnostic-first-live-run.md`
  (the closure this round's header fix now correctly reflects).
- `knowledge/round-315-skills-b-tiny-language-implementation-pitfall-split.md`
  (the split-file mechanism this round reused unchanged).

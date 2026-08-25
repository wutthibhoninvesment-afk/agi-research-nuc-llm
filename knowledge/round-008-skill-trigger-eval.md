# Round 008 — skills(B): measuring skill triggering instead of guessing it

Date: 2026-08-24. Track B, second dedicated round (first: round 3). The
round-3 skill left one claim untested — "test by observation: give a fresh
instance an indirect task and see what fires" — and two linter gaps
(reference depth, SKILL.md↔reference duplication). This round closes all
three and uses the new instrument to upgrade three descriptions with
measured, not imagined, effect.

## What was built

1. **`skills/skill-authoring/scripts/trigger_eval.py`** (~330 LOC stdlib)
   — a fresh-instance trigger-rate evaluator.
   - **native mode**: copies the skills under test into a throwaway
     project's `.claude/skills/`, runs `claude -p --output-format
     stream-json --tools Skill --permission-mode dontAsk
     --no-session-persistence --setting-sources project` there with an
     appended probe system prompt ("invoke every applicable skill, then
     reply `SKILLS=…` and stop"), and counts a skill as fired when a
     `Skill` tool_use for it appears in the stream. This is the real
     selection path: real skill index, real system prompt, and the host's
     ~45 user-level skills present as distractors.
   - **catalog mode**: name+description list pasted into one prompt, model
     answers `{"skills": […]}`. No tools, cheaper.
   - Labelled JSON case file (`expect: [our skills]`, `[]` for negatives);
     fires outside the staged set are reported as *foreign* but never
     penalised. Per-skill tp/fp/fn → recall/precision, exact-match rate,
     negative false-fire count, cost; `--repeats N`, `--only ids`,
     `--concurrency`, `--json`. Exit 0/1/2. Runner injectable → **23
     offline tests** (fake runner) cover stream parsing, plugin-prefixed
     skill names, staging, catalog prompt shape, scoring, and exit codes.
2. **`skill_lint.py` +3 checks** (35 → 49 tests):
   - **R003** reference links onward to another local `.md` not linked
     from SKILL.md (one-level-deep rule).
   - **R004** a ≥120-char normalised paragraph or fenced block of SKILL.md
     appears verbatim in a linked reference (content in two places).
   - **R005** a bundled file is never mentioned from SKILL.md — by path,
     basename, or an ancestor directory mentioned *as a directory*
     (`references/layouts/<layout>.md`, `templates/`); `LICENSE*` and
     private `_*.py` helpers exempt.
3. **Meta-skill upgraded**: step 7 is now "run `trigger_eval.py`", step 3
   says *symptom vocabulary*, step 5 names the three new checks, two new
   pitfalls (mechanism-vs-symptom; catalog-as-proxy), checklist made
   measurable; new one-level reference `references/trigger-evaluation.md`
   (case design, mode trade-offs, reading the report, iteration loop).
4. **Three descriptions upgraded from measurements** (see below); case
   file `skills/trigger-cases.json` (32 cases: 8 skills × near/mid/far,
   2 two-skill cases, 6 look-alike negatives). All reports under
   `state/trigger-eval/*.{md,json}`.

## Verification
```
$ python3 -m unittest discover -s skills/skill-authoring/scripts    → Ran 72 tests, OK (0.08s)
$ python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/
  → skill-lint: 8 skill(s), 0 error(s), 0 warning(s)
$ python3 skills/skill-authoring/scripts/trigger_eval.py skills/trigger-cases.json --skills skills --json …
  baseline (native):          32 ok, exact-match 91%, negatives false-fire 0/6, $1.07
  after description edits:    32 ok, exact-match 94%, negatives false-fire 0/6, $1.10
regression: harness 148 passed (6.1s) · whence 243 passed (53s)
```

## The experiment

**Baseline (native, single run).** 29/32 exact. Misses: `stil-far`
(profiling shows 67% of time building display strings for values never
printed → expected `shared-tip-immutable-lists`), `fmk-far` ("Harden the
expression evaluator before we ship"), `multi-1` (calculator language +
CLI exit-code tests → `subprocess-cli-testing` lost to
`tiny-language-implementation`). 0/6 negatives fired, and no foreign
skill ever *replaced* ours — `claude-api` fired *alongside* on two
API-flavoured prompts.

**Is a miss a gap or noise?** 4 extra repeats of five cases:

| case | fires (baseline + 4 repeats) | verdict |
|---|---|---|
| stil-far | 1/5 | real gap |
| multi-1 (2nd skill) | 2/5 | real gap (co-selection loses) |
| fmk-far | 4/5 | mostly noise |
| sct-far | 4/5 | mostly noise |
| oat-far | 5/5 | solid |

**Treatment** — description edits only, nothing else touched:
- `shared-tip-immutable-lists`: added the *symptom* the prompt used —
  "profiling shows most time spent building display/show/repr strings,
  snapshots, or renderings of values that are never printed", plus
  "memory grows every iteration of a loop that appends…". The original
  said "snapshot strings computed eagerly per value dominate a profile" —
  same mechanism, different words, and the model did not bridge them.
- `subprocess-cli-testing`: added "when building a language, calculator,
  or tool that has a `run.py`, `main()`, or command-line entry point (add
  these tests alongside the implementation's unit tests)" — an explicit
  co-selection cue — and "prints a traceback when actually invoked from a
  shell".
- `fuzz-mutate-kill-loop`: "harden, stress, or make robust … before
  shipping or release".

**Effect** (5 repeats each, native): stil-far 1/5 → **5/5**, multi-1 2/5
→ **5/5**, sct-far 4/5 → 5/5, fmk-far 4/5 → 5/5. Full 32-case rerun:
all three original misses fixed; two *different* single-run misses appeared
(`sa-near`, `fmk-near`, both 1/1 at baseline). Noise check on those:
see the addendum at the bottom: 5/5 and 5/5 — noise.

**Catalog mode vs native mode.** Catalog mode scored **100%** on the same
32 cases at baseline — including all three cases native mode missed. The
cheap proxy saturates: an 8-entry list with no distractors, framed as a
selection question, is a far easier task than the real index. Decisions
must be made on native numbers; catalog mode is at best a smoke test.

## Key learnings
1. **Trigger quality is measurable for ~$0.03 a probe.** 32 probes ≈ $1,
   ~4 min at concurrency 4. Description edits become an evaluated change,
   with before/after numbers — the loop the round-3 skill only described.
2. **Symptom vocabulary beats mechanism vocabulary.** The one stable gap
   this round was a description that named the *fix* ("snapshot strings
   computed eagerly") where the user names what they *see* ("display
   strings for values never printed"). Adding the observed phrasing took
   fire rate from 20% to 100%.
3. **Co-selection is a separate failure mode.** A skill can fire 100% alone
   and lose half the time when a sibling also applies (multi-1). The cure
   is an explicit cue in the description that names the sibling context
   ("when building a language … that has a command-line entry point").
4. **Single runs lie in both directions.** Per-case fire rates of 80% mean
   a 32-case run flips 1–2 cases each time, on *different* cases. Rule:
   never edit for a single miss; re-run `--repeats 4 --only <id>` first,
   and report fire rates, not one exact-match number.
5. **Cheap proxies saturate.** Catalog mode was 100% where native was 91%.
   Any eval that removes the distractors and the framing measures a
   different, easier task.
6. **Linting the "invisible file" rule finds real problems in the wild:**
   over 124 corpus skills, R005 flagged 43 files in 25 skills after
   refinement — e.g. `github-pr-workflow/references/ci-troubleshooting.md`,
   `grounded-citations/references/grounding-rationale.md`,
   `notion/references/block-types.md` — verified by grep: zero mentions in
   their SKILL.md. Those references can never be read. R004 found one real
   duplication (a 324-char routing table in `claude-automation-recommender`
   copied into its reference). R003 found none — authors do keep
   references flat.
7. **Refinement needed two rounds against the corpus:** the first R005 cut
   fired 153× because directory-level mentions (`templates/`,
   `references/layouts/<layout>.md`) were not counted; the fix is "an
   ancestor directory mentioned as a directory, not via a sibling's path"
   (`re.escape(dir) + r"/(?![\w.-])"`).

## Honest failures
- **I destroyed the meta-skill file mid-round.** A Python `s.replace(old,
  new)` where `old` was computed by slicing between two markers — and the
  end marker (`## Pitfalls`) also occurred *inside step 4* before the start
  marker — produced an empty `old`, and `str.replace("", x)` interleaves
  `x` at every character: 113 lines → 117,761 lines. No git in this
  workspace; recovered by rewriting the file from the copy still in
  context. Rule added to state: assert `len(old) > 0` and `count(old) == 1`
  before every programmatic replace (the later edits did exactly this).
- **zsh does not word-split `$var`**: the first wild-corpus lint run passed
  124 newline-joined paths as one argument; the linter printed them back
  inside its own error message and I mis-read that as "0 findings". Use
  `xargs` (or `${(f)var}`) for multi-path loops in zsh.
- Only one probe model (sonnet). Selection behaviour may differ on other
  models; `--model` exists but was not exercised.
- The `--setting-sources project` flag does not stop user-level skills from
  loading into the staged project, so the distractor set is "whatever the
  host has" — realistic but not controlled.
- Body quality (does the agent *follow* the steps, which bundled files does
  it read) is still not automated; the probe stops after the Skill loads.
- No new standalone skill this round: the technique is the meta-skill's
  step 7 and lives there (a separate "trigger-eval" skill would duplicate
  its trigger list, the very anti-pattern step 5 forbids).

## Addendum — noise check on the two post-edit near misses
5 repeats each (native, $0.43): `sa-near` **5/5**, `fmk-near` **5/5**.
Both were single-run flips, not regressions from the edits. Combined
evidence across the round: every case now sits at ≥ 4/5 or 5/5 on its
repeated runs, 0/6 negatives ever fired (four full-suite passes), and no
foreign skill ever displaced ours. Total spend on probes this round: ~$4.8
(≈ 160 probes).

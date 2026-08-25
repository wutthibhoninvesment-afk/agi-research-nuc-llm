# Round 003 — skills(B): skill authoring, distilled + enforced

Date: 2026-08-24. Sources: Anthropic Agent Skills best-practices docs (fetched
live), a 123-file SKILL.md corpus survey (`~/.hermes/skills/` 90 files,
`~/.claude/plugins/` 33), and rounds 1–2 artifacts.

## What was built
1. **`skills/skill-authoring/`** — meta-skill on writing SKILL.md files, plus
   a bundled linter:
   - `scripts/skill_lint.py` (~250 LOC stdlib): enforces official frontmatter
     constraints (name ≤64 chars kebab-case, no reserved words; description
     non-empty ≤1024 chars, no XML tags), body <500 lines, relative links
     resolve, long reference files need a ToC, Windows-path detection
     (fence-aware), third-person + trigger-phrasing heuristics, and — behind
     `--house` — this workspace's required sections (triggers / numbered
     steps / pitfalls / verification / fenced commands). `--strict` promotes
     warnings. Exit codes 0/1/2.
   - `scripts/test_skill_lint.py`: **35 tests, 0.02s** (frontmatter parser
     incl. block scalars and nested mappings; every check code positive AND
     negative; discovery; exit codes).
2. **`skills/subprocess-cli-testing/`** — new skill from round-2 material:
   locking a CLI's exit-code/stdout/stderr contract with a thin subprocess
   layer (reference impl: `languages/whence/tests/test_examples.py`).
3. **Upgraded** both existing skills' descriptions to third-person
   what+when with explicit trigger clauses (they had "what" only — the
   canonical undertriggering cause).

## Test output (verification)
```
$ python3 -m unittest discover -s skills/skill-authoring/scripts   → Ran 35 tests, OK
$ python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/
  → skill-lint: 4 skill(s), 0 error(s), 0 warning(s)   (exit 0)
regression: harness 72 OK · whence 105 passed in 0.18s
```

## Wild-corpus validation of the linter
Ran the linter over all 90 Hermes skills + known-bad plugin exemplars:
- Reproduced the survey's anti-patterns independently: 7× B001 bodies over
  500 lines (worst: `research-paper-writing` 1611), 2× N004 reserved word
  "claude" in name, 1× R001 broken link (`gif-search` links literal `url`).
- Gap found and fixed: my parser handles YAML block-scalar descriptions
  *correctly*, so it initially missed the real hazard — naive line-based
  extractors index them as EMPTY and the skill silently never triggers
  (seen live in `math-olympiad`, 906-char description parsed as 0 chars,
  and `aorgy-news-n8n`). Added **D006** warning; confirmed it fires on both.

## Key findings (the distilled discipline)
1. **The description is the trigger; the body is the procedure.** All
   "when to use" content goes in the description because the body loads only
   after the skill fires. Models undertrigger → write descriptions pushy,
   third person, with enumerated contexts that don't name the skill.
2. **Description length is host-calibrated, not absolute.** Hermes hardlines
   ≤60 chars because its index truncates at 57; Claude Code renders full
   descriptions, where 200–500 chars of trigger phrases wins. Both corpora
   are internally consistent — copy the convention of the target harness.
3. **Three-level token budget**: metadata (always loaded) → body (<500
   lines, on trigger) → bundled files (zero cost until read). References one
   level deep; ToC on >100-line refs; routing table for multi-domain skills;
   content lives in exactly one place; an unreferenced file is invisible.
4. **Checkable beats hortatory.** Best-in-class skills end each step in a
   verifiable outcome, name pitfalls as failure-mode + mechanism, pre-empt
   rationalizations (Excuse→Reality tables), state one fenced "iron law",
   and include counter-triggers ("When NOT to use"). "Be careful" lines are
   sediment — delete them.
5. **Ship scripts, not prose, for deterministic logic**; say explicitly
   run-it vs read-it. Detection heuristic: if test transcripts independently
   rewrote the same helper, bundle it.
6. **Lint what's lintable, observe the rest.** Hard constraints + section
   presence are automatable (hence skill_lint); trigger quality is only
   testable by giving a fresh instance an indirectly-phrased task and
   watching what fires and which files get read.

## Honest failures / limits
- D004/D005 (person, trigger phrasing) are regex heuristics: D005 flags 85/90
  Hermes skills whose *house style* is deliberately terse — correct per
  official docs, noisy against foreign conventions. That's why warnings
  don't fail the run without `--strict`.
- The linter can't check "references one level deep" (would need to crawl
  nested links; only missing targets are caught) nor duplicate content
  between SKILL.md and references.
- Step 7 of the meta-skill (fresh-instance trigger testing) was NOT
  executed this round — no second instance available in-session; it's the
  untested claim in the skill. Candidate for round 5's SWE-loop: point
  agentloop at indirect prompts and measure trigger rates.
- Candidate skills "why-tree/blame-trail debugging" and "errors-as-values
  interpreter design" deliberately not authored: the former is
  Whence-specific (weak reuse), the latter already lives as step 2 of
  `tiny-language-implementation` — a separate skill would duplicate content,
  violating finding 3.

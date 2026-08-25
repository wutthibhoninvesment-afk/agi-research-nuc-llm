---
name: skill-authoring
description: Use when the user wants to write a new SKILL.md, turn a procedure, technique, or workflow from a session into a reusable skill, review or improve the files under .claude/skills/ or another skill directory, or figure out why a skill Claude never picks up — or picks up but ignores. Covers the frontmatter rules, trigger-rich third-person descriptions, house body format, progressive disclosure into bundled references, an automated linter (skill_lint.py), and a fresh-instance trigger-rate evaluator (trigger_eval.py) that measures whether a description actually fires on indirectly phrased tasks before it ships.
---

# Authoring SKILL.md files

## When to use (triggers)
- A reusable technique emerged from a session and should become a skill.
- Writing a new SKILL.md, or reviewing/upgrading an existing one.
- A skill exists but never triggers (description problem) or triggers and
  gets ignored (body problem).
- Deciding between two descriptions — measure, don't argue.

**When NOT to use:** don't create a skill for something done once (no
evidence it recurs), for what the model already knows (a skill explaining
what a PDF is), or as a router whose content is only pointers to sibling
skills — that duplicates their triggers and adds an indirection hop.

## Steps

1. **Verify a real technique exists.** The test: while doing the task, did
   you repeatedly supply the same non-obvious context, or repeat a hard-won
   procedure across tasks? If all your example transcripts independently
   rewrote the same helper code, that code belongs in `scripts/`, not prose.

2. **Frontmatter — hard constraints** (validated by the linter, see step 6):
   - `name`: ≤64 chars, `^[a-z0-9]+(-[a-z0-9]+)*$`, no reserved words
     ("anthropic", "claude"), and it should equal the directory name.
     Prefer gerund or noun-phrase forms consistent with the collection.
   - `description`: non-empty, ≤1024 chars, no XML tags, **third person**.

3. **Write the description as the trigger, calibrated to the host.** All
   "when to use" information goes in the description, not the body — the
   body is only loaded *after* the skill fires. Models undertrigger skills,
   so be deliberately pushy: state what it does, then enumerate concrete
   trigger contexts ("Use when …, or when the user mentions …"), including
   phrasings that don't name the skill. Write the *symptoms the user will
   describe* ("memory grows every iteration", "tests hit the real API"),
   not only the mechanism the skill applies. Know your host's index
   budget: Claude Code renders full descriptions (200–500 chars of trigger
   phrases works); some harnesses truncate their skill index near 60 chars
   — there, the capability must fit the truncation window. Never write
   capability without trigger ("Controls TouchDesigner via MCP" only fires
   if the user already says TouchDesigner).

4. **Body = procedure, in house format** (imperative voice, not "you can"):
   - `## When to use (triggers)` — bullets, plus a **When NOT to use**
     counter-trigger when misfiring is plausible.
   - `## Steps` — numbered; each step ends in a checkable outcome, not
     advice. For discipline skills, state the one load-bearing invariant as
     a short fenced "iron law" and pre-empt rationalizations (an
     Excuse→Reality table beats ten warnings).
   - Exact commands in fenced blocks, copy-pasteable, with expected output.
   - `## Pitfalls` — each a *named failure mode with its mechanism*
     ("`set -u` + `local r=$1 m=$((r%5))` fails because arithmetic runs
     before `local` assigns"), never "be careful with X".
   - `## Verification` — commands + expected output that prove the skill
     was followed; a `- [ ]` checklist for multi-phase work.

5. **Budget tokens with progressive disclosure.** Three levels: description
   (always loaded) → body (loaded on trigger; keep well under 500 lines) →
   bundled files (loaded on demand, zero cost until read). Split detail
   into `references/*.md` linked **one level deep** from SKILL.md; give any
   reference over ~100 lines a `## Contents` at the top; for multi-domain
   skills use a routing table (`| User wants… | Load |`). Content lives in
   SKILL.md *or* a reference, never both; an unreferenced file is invisible
   (the linter checks all three: R003 link depth, R004 duplicated chunks,
   R005 unmentioned bundled files). Ship deterministic logic as
   `scripts/*.py` and say explicitly whether to **run** it or **read** it.
   Cut sediment: if a sentence doesn't change behavior, delete it — the
   model is already smart. No machine-local paths (`/Users/you/…` breaks
   every other user; skill-relative only), no time-sensitive facts, no
   ALL-CAPS MUSTs where a reason works.

6. **Lint it** (script bundled with this skill — run it, don't read it):
   ```bash
   python3 skills/skill-authoring/scripts/skill_lint.py --house skills/<name>/
   # expected: "1 skill(s), 0 error(s), 0 warning(s)", exit 0
   ```
   Errors are the official constraints; `--house` also enforces the step-4
   section format. `--strict` promotes warnings for CI use.

7. **Measure triggering; don't introspect.** Write a case file of tasks
   phrased *without* the skill's name (near / mid / far paraphrases, plus
   negatives that resemble the domain), then run the bundled evaluator —
   it stages the skills in a throwaway project and asks a *fresh*
   `claude -p` instance which skills it invokes (run it, don't read it):
   ```bash
   python3 skills/skill-authoring/scripts/trigger_eval.py cases.json \
       --skills skills/ --json out.json        # native mode, ~$0.03/probe
   # expected: per-skill recall/precision table; exit 0 only if every case matched
   ```
   Recall < 100% on a skill → its description lacks the vocabulary of the
   missed prompt; false fires on negatives → the description is too broad.
   Re-run after each edit; with `--repeats N` the report aggregates into
   per-case fire RATES splitting fired-at-all from exact — the readable
   unit for noisy probe models (small models are unreadable at n=1).
   Three deeper probes when the basic numbers look fine: `--model
   sonnet,haiku` compares fire rates across probe models (descriptions
   tune themselves to one model); `--distractors <corpus-dir>
   --n-distractors 12` stages a known foreign corpus and counts
   *displacement* — add `--paired` to also run every probe without the
   distractors and get per-case SUPPRESSED/DISPLACED verdicts (a sibling
   can sink your fire rate without ever firing itself); and `--mode body`
   runs real tasks and checks the agent *followed* the loaded body —
   which bundled files it actually read (error-result Reads don't count;
   denials are flagged), and whether idiosyncratic markers from the steps
   (`body.evidence` regexes, `evidence_min` for any-N-of-M) appear in the
   transcript (`--transcripts DIR` keeps the full text). Before ANY
   cross-round comparison, run the frozen sentinel first: `--canary
   canary.json` exits 1 when the instrument has drifted out of its stored
   band — on drift, re-baseline; don't compare. Before writing or editing
   a case file, READ
   [references/trigger-evaluation.md](references/trigger-evaluation.md) —
   the near/mid/far case-design rules, body/evidence marker guidance, and
   how to read each report live there, not in this file; cases written
   without them measure string matching instead of selection.

## Pitfalls
- **Second-person or first-person descriptions** ("You can use this to…",
  "I can help…") — inconsistent point-of-view inside the system prompt
  measurably hurts selection. Third person only.
- **Block-scalar descriptions** (`description: >-`) — naive line-based
  frontmatter extractors read the literal `>-` and index an empty
  description; the skill silently never triggers. Keep it one (long) line.
- **Colons in unquoted YAML values** — `description: Use when: x` parses
  as a nested mapping and breaks parsers; wrap the value in quotes.
- **Writing the skill before the technique is proven** — documents
  imagined problems; evaluation-driven authoring (step 1/7) beats
  speculation.
- **Vague pitfalls** — "watch out for encoding issues" changes nothing;
  name the exact failure and its mechanism or delete the line.
- **Describing the mechanism instead of the symptom** — a description that
  says "snapshot strings computed eagerly" does not fire on "display
  strings dominate the profile"; users describe what they *see*, so the
  trigger list needs symptom vocabulary, not only the technique's.
- **Descriptions tuned on one probe model spray on a smaller one** — a
  description at 100% recall/precision on sonnet measured 0–50% recall and
  10–19% precision on haiku. Symptom-first ordering, a NOT-for list, and an
  applicability gate ("if the task never mentions X, this skill does not
  apply") recover most of it; verify with `--model sonnet,haiku`, not by
  rereading the description.
- **A same-domain sibling can suppress your skill without firing** —
  displacement stays 0 while your fire rate drops (the selector fires
  neither contender). Only a paired with/without `--distractors` probe of
  the same case reveals it; see the reference.
- **Comparing trigger rates across rounds without a canary check** — the
  instrument is the live host, and its skill population + probe model
  shift underneath the benchmark (a case measured 7/7 → 1/12 across
  rounds with the skill untouched). Run `--canary` first; on drift,
  re-baseline the same day and compare within-day only.
- **Acting on a single probe of a small model** — small-model selection
  is noisy enough that n=1 is a coin report; use `--repeats ≥4` and read
  the per-case rate table, and phrase every small-model claim as a rate.
- **Catalog-in-a-prompt as a proxy for the real selector** — asking a model
  "which of these descriptions applies?" scores differently from the real
  skill-index path (no distractors, no system framing); decide on native
  mode numbers, see the reference.
- **The 500-line body** that grew by accretion — every token competes with
  the conversation after load; move detail to references, keep the routing.
- **Workspace-relative paths in the body become dead references when the
  skill is staged elsewhere** — body-mode probes measurably chase them
  (`Read .claude/skills/<name>/harness/retry.py` → file-not-found, wasted
  turns). A soft qualifier ("in the harness this was distilled from") is
  not enough; say "not bundled with this skill — don't open these paths",
  or bundle the file.

## Verification
```bash
cd ~/agi-research
python3 -m unittest discover -s skills/skill-authoring/scripts -v
# expected: Ran 116 tests, OK  (test_skill_lint.py + test_trigger_eval.py, offline)
python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/
# expected: 0 error(s), 0 warning(s), exit 0
```
- [ ] Description states what AND when, third person, symptom-vocabulary
      trigger phrases included
- [ ] Linter clean under `--house --strict`
- [ ] `trigger_eval.py` shows 100% recall on the skill's cases and no false
      fires on negatives (native mode, repeated if a miss looks like noise)
- [ ] For a skill whose body carries the value (procedures, bundled files):
      a `--mode body` case exists and the evidence markers match, or a real
      session followed the steps without improvising

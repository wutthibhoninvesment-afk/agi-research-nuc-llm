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
   R005 unmentioned bundled files). A `#fragment` on a link is checked too
   — R006 fails a link whose anchor no target heading or `<a id>` defines,
   across SKILL.md *and* each reference's own `## Contents` list, and R007
   warns on an `<a id>` nothing links to. Ship deterministic logic as
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
   band — on drift, re-baseline; don't compare. Then compare with
   `--baseline prior.json`: a per-case delta table with verdicts
   (REGRESSED / IMPROVED / CO-FIRE / noise? / same) replaces reading two
   reports side by side — a description rewrite that ships without this
   step can silently lose a far case (measured: 2/2 → 0/2, found two
   rounds later). A miss whose transcript is a one-turn `SKILLS=<the
   expected skill>` with no tool call is a probe-protocol artifact, not a
   description problem — the report counts these as `declared-not-invoked`;
   the strict protocol (the default since v4.2; `--protocol default`
   reproduces older reports) removes it — re-probe under it, or read
   the rate with `--count-declared`, before editing. At session start
   and after every description edit run `--audit <reports-dir>` (offline):
   it lists, per skill, whether the description on disk now was ever
   probed (`probed` / `STALE` / `never`) and the case counts — a skill
   with cases but no report is `never`, and that is the state two skills
   shipped in. Before writing or editing
   a case file, READ
   [references/trigger-evaluation.md](references/trigger-evaluation.md) —
   the near/mid/far case-design rules, body/evidence marker guidance, and
   how to read each report live there, not in this file; cases written
   without them measure string matching instead of selection.

8. **Make the Verification block re-derivable, then re-derive it** (script
   bundled with this skill — run it, don't read it). A Verification block is
   a set of factual claims (`# expected: Ran 165 tests`, `8 passed`, `exit
   0`) that nothing ever re-executes, so it rots invisibly: this corpus has
   now been caught five times, most bluntly with a `cd ~/agi-research` that
   had been dead since the workspace was renamed, silently making every
   command under it unrunnable.
   ```bash
   python3 skills/skill-authoring/scripts/claim_check.py skills/
   # expected: "0 stale claim(s)", exit 0 — static, safe anywhere
   python3 skills/skill-authoring/scripts/claim_check.py --run --timeout 150 skills/
   # opt-in: executes only the commands it classifies `auto` and diffs
   # their real output against the claim
   ```
   `--list` prints the auto/manual verdict per command with its reason;
   classification **fails closed**, so a command whose program is not on the
   allowlist is never executed — the corpus contains commands that spend
   money, ssh to another host and write into the checkout, and a denylist
   would eventually guess one of those wrong. Two authoring rules follow
   from what it can and cannot check:
   - Prefer a claim that cannot rot over one that is merely correct today.
     A repo-relative `cd languages/whence` is checkable and portable; an
     absolute `cd ~/project` is neither.
   - State a NUMBER, not "all passed". A claim with no number is reported
     `UNQUANTIFIED` — it can only ever be checked for its exit code, so a
     silent count drift never surfaces.

9. **Check that every identifier the corpus CITES is actually DEFINED**
   (script bundled with this skill — run it, don't read it). Step 8 covers
   claims that rot; this covers *pointers* that never resolved. A skill that
   says "rule B002" or "SPEC decision 29" promises the reader a lookup, and a
   dangling identifier renders as ordinary prose — no broken link, no error,
   nothing to notice.
   ```bash
   python3 skills/skill-authoring/scripts/xref_check.py
   # expected: "0 NEW", exit 0 — new dangling citations only
   python3 skills/skill-authoring/scripts/xref_check.py --show-acknowledged
   # what state/known-dangling-citations.json is currently covering, and who owns it
   ```
   Two authoring rules follow, and they apply to the SKILL.md you are writing
   right now:
   - **Cite a rule code only if a script emits it.** `R006`, `C001`, `B002`
     are checkable because `xref_check.py` derives the registry from the
     `"CODE"` string literals in `skills/*/scripts/*.py`. Inventing a
     plausible-looking code for prose is how that family stops being
     trustworthy.
   - **An illustrative path in prose is still a path.** Write
     `skills/<name>/SKILL.md`, not a realistic-looking directory that
     happens not to exist. The full rationale, the registry-vs-definition
     rule and the scope model live in
     [citation-registry-integrity](../citation-registry-integrity/SKILL.md).

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
- **A reference's `## Contents` list rots silently** — a `#fragment` fails
  open: the reader lands at the top of a 400-line file and reads the wrong
  section, with no error anywhere. Nothing surfaces it, because the *file*
  still exists — a file-existence link check passes. Hand-slugging is the
  usual cause and it is genuinely hard: GitHub drops the punctuation but
  keeps one hyphen per *surviving* space and never collapses runs, so
  ``## Fire rates (`--repeats N`)`` is `#fire-rates---repeats-n` (three)
  while `## Instrument drift — canary` is `#instrument-drift--canary`
  (two, the em dash dropped from between its two spaces). Do not count
  hyphens by eye — run the linter (R006); it found one already-rotted
  entry in this skill's own ToC whose three sibling `(`--flag`)` entries
  were all correct.
- **A Verification block is documentation, so it rots like documentation.**
  It reads as evidence — exact commands, exact numbers — but nothing
  re-executes it, so every number in it is only as fresh as the last round
  that happened to run that command by hand. Five confirmed instances in
  this corpus, and the two worst were not numbers: `cd ~/agi-research`
  survived the workspace being renamed, silently making every command in
  two blocks unrunnable, and a `--strict` sweep claiming `exit 0` had been
  false for ~24 rounds. Both are `claim_check.py` C001/C002 findings now
  (step 8), and the live-corpus test in `test_claim_check.py` is what makes
  the next one a test failure rather than an audit somebody remembers.
- **Fenced `#` comments are not headings, and treating them as such empties
  the section silently.** A tool that slices `## Verification` … next
  heading must blank fenced blocks first: `# 1. Bracket invariants…` inside
  a bash fence matches `^#{1,6}\s+` exactly. Written naively this emptied 7
  of 19 Verification blocks in this corpus and reported *success* — zero
  parsed commands and zero findings are indistinguishable. Any corpus sweep
  needs a positive-control assertion ("these N skills, and only these,
  parse to zero commands"), not just "no findings".
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
- **Editing a description without re-probing it** — a mechanism-first
  rewrite (capability list, then "use when") shipped with a green lint
  and cost the skill its far case (2/2 → 0/2) and a co-firing sibling on
  its near case; nobody saw it until the next full run two rounds later.
  Every description change is followed by `--only <its cases> --repeats
  3 --baseline <last-clean-run>.json` the same session.
- **A case file is not a probe** — two skills shipped with three trigger
  cases and a body case each and were never run (the cases made them look
  tested; the round that wrote them had no budget line for the probe).
  `--audit` names them `never`; a description whose digest is not in any
  report is unmeasured, whatever the case file says.
- **A capability list leads, the triggers trail** — the selector reads
  the first clause; if it is "X loop for Y: technique, technique,
  technique", a far-phrased task ("harden calc.py before we ship") is
  claimed by a sibling whose first clause matches the task's noun.
  Symptom-first, method last.
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
- **Chasing one haiku miss past diminishing returns** — a single near-case
  collision between two skills took 5 rounds and 5 distinct edits (symptom
  rewrite, NOT-for on the loser, NOT-for on the winner, shared-noun removal,
  a confirming re-probe) to move 0/6 → 1/6, never a flip. After 3
  same-mechanism edits with zero measured movement on the target case,
  stop editing that case — it is a small-model base-rate property, not a
  fixable description defect; widen the haiku band instead and redirect
  the probe budget. See the reference's "When to stop editing a
  description" for the mechanism order that actually moves a number
  (shared-noun removal, tried last, was the only one that worked).

- **A checker that can never go green gets uninstalled.** Two of this
  corpus's checks found real debt owned by someone else on their first run.
  Without a baseline file the check exits non-zero forever, somebody stops
  reading it, and the next genuine regression lands unseen — the same
  failure the check existed to prevent. Ship the baseline (keyed by
  identifier, never file:line) in the same commit as the checker, with an
  owner named per entry.

## Verification
Every command below is repo-root-relative; run them from the repo root. (An
absolute `cd ~/agi-research` used to open this block and had been dead since
the workspace was renamed — see `claim_check.py`'s C001.)
```bash
python3 -m unittest discover -s skills/skill-authoring/scripts -v
# expected: Ran 316 tests, OK  (skill_lint + trigger_eval + claim_check
#           + xref_check, offline). Re-derived round 345; was 247 before
#           test_xref_check.py, so a lower count in an older report is not
#           evidence of a regression. (Re-derived TWICE in round 345: the
#           first figure, 311, was stale within the hour because the same
#           round then added 5 tests. Re-derive this LAST.)
python3 skills/skill-authoring/scripts/skill_lint.py --house skills/<name>/
# expected: 1 skill(s), 0 error(s), 0 warning(s), exit 0   <- the bar for a new skill
python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/
# expected: 21 skill(s), 0 error(s), 0 warning(s), exit 0. Warning-free since
# round 339 split fuzz-mutate-kill-loop under the 400-line B002 threshold;
# before that a known B002 made --strict exit 1, so a pre-339 report saying
# "exit 1" is not evidence of a regression.
python3 skills/skill-authoring/scripts/claim_check.py skills/
# expected: 21 skill(s), 0 stale claim(s), exit 0 (static; --run also executes
# the `auto` commands and diffs their output against these very claims)
python3 skills/skill-authoring/scripts/xref_check.py
# expected: "0 NEW", exit 0. 28 citations are pre-acknowledged in
# state/known-dangling-citations.json (two registry gaps owned by language(C)
# and by the operator); --show-acknowledged lists them.
```
- [ ] Description states what AND when, third person, symptom-vocabulary
      trigger phrases included
- [ ] Linter clean under `--house --strict`
- [ ] `trigger_eval.py` shows 100% recall on the skill's cases and no false
      fires on negatives (native mode, repeated if a miss looks like noise)
- [ ] `trigger_eval.py … --audit <reports-dir>` exits 0: every skill
      `probed` under its current description, none `STALE`/`never`
- [ ] For a skill whose body carries the value (procedures, bundled files):
      a `--mode body` case exists and the evidence markers match, or a real
      session followed the steps without improvising

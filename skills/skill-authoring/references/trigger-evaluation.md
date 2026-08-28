# Trigger evaluation with `trigger_eval.py`

## Contents
- [Case file](#case-file) — shape and the near/mid/far design rules
- [Modes](#modes) — native / catalog / body trade-offs
- [Body-following](#body-following---mode-body) — files + evidence regexes
- [Fire rates](#fire-rates--repeats-n) — repeats-aggregated per-case rates
- [Multi-model comparison](#multi-model-comparison)
- [Controlled distractors](#controlled-distractors) — displacement, `--paired`
- [Instrument drift](#instrument-drift--canary) — the canary sentinel
- [Probe audit](#probe-audit---audit) — is every skill's CURRENT description probed?
- [Reading the report](#reading-the-report) / [Iteration loop](#iteration-loop) / [Limits](#limits)

The description is the only thing the model sees before deciding to load a
skill, so description quality is a measurable property: give a fresh
instance an indirectly-phrased task and record what fires.

## Case file

JSON list; each case is a task prompt plus the set of *your* skills that
should fire (empty for negatives):

```json
[
  {"id": "gte-far", "prompt": "There's a sys.setrecursionlimit(100000) hack at the top of our evaluator module. Get rid of it without breaking deep programs.",
   "expect": ["generator-trampoline-evaluator"]},
  {"id": "neg-1", "prompt": "Write a bash script that renames all .jpeg files to .jpg.", "expect": []}
]
```

Design rules that made the cases informative:
- **Three distances per skill.** *near* = the user names the symptom the
  description names; *mid* = a paraphrase in the user's own words; *far* =
  a consequence of the problem with no shared vocabulary. Misses cluster
  at *far*, and each far miss names a vocabulary gap to add.
- **Negatives that share surface features** with the domain (a Flask 500
  error next to an "errors as values" skill; "optimize this SQL" next to a
  performance skill). Generic negatives never fire and prove nothing.
- **Two-skill cases** catch a skill that loses when a sibling also applies.
- Never use the skill name, the directory name, or a phrase copied from the
  description in a prompt — that measures string matching, not selection.

## Modes

| mode | what it measures | cost (sonnet) | fidelity |
|---|---|---|---|
| `native` (default) | the real path: skills staged in a temp project's `.claude/skills/`, `claude -p` with only the `Skill` tool, a `Skill` tool_use counts as fired | ~$0.03 / probe, ~20 s | high — the host's own user-level skills are present as distractors |
| `catalog` | descriptions pasted into one prompt, model returns a JSON list | ~$0.02 / probe | lower — no distractors, no system-prompt framing; over-fires on multi-skill cases |
| `body` | body-following: the probe *does the task* (default tools `Skill,Read`, deliverable in the reply); records which staged bundled files were read and which case `body.evidence` regexes match the transcript | ~2–5× a native probe | tests the body, not just the trigger — see below |

Use native mode for trigger decisions. Catalog mode is a quick smoke test
for a description draft when the CLI is unavailable.

## Body-following (`--mode body`)

A skill that fires but is then ignored is a body problem, and it is
measurable too. Body cases add a `body` object:

```json
{"id": "body-sa", "prompt": "…a real task, deliverable in one reply…",
 "expect": ["skill-authoring"],
 "body": {"files": ["skill-authoring/references/trigger-evaluation.md"],
          "evidence": ["third.person", "symptom", "trigger.?eval|skill_lint"]}}
```

- `files` — staged-relative paths (`<skill>/<relpath>`) the agent should
  read while following the body. Detected from `Read` file_paths and Bash
  command text touching `.claude/skills/…`. Only meaningful for skills
  that bundle references/scripts.
- `evidence` — case-insensitive regexes matched against the whole
  transcript (every assistant text block). Pick **idiosyncratic markers**
  from the body — house choices a competent model would *not* produce
  unaided (`sys.executable` not `python3`; "monotonic" compaction; the
  raise-on-exhaustion mock). Generic markers (`stderr`, `yield`) measure
  model competence, not body-following — the report can only be read
  against that confound if the markers are distinctive.
- A case counts as *fully followed* when the fired set matches, every
  expected file was read, and every evidence regex matched.

The task must be completable in one reply with the body-mode toolset
(default `Skill,Read`; override with `--body-tools` if a body's steps
require running commands — then Bash paths count as file touches too).

Bundled references are read when the task actually *requires* their
content and skipped when the loaded body suffices (measured: 0/5 reads on
a task the body could answer, even with an imperative READ cue; 5/5 on a
task demanding facts that exist only in the reference). Two consequences:
if a reference matters, keep the body a router that is *incomplete*
without it (don't summarize the reference's key numbers into the body);
and every skill that bundles a load-bearing reference should have one
body case whose answer is impossible without reading it.

Read outcomes are matched to their tool_results: a Read whose result
errored is NOT counted in `files_read`; it lands in `files_failed` with
the error text and a `denied` flag (permission-denial pattern vs e.g. a
missing file). Bash touches remain attempt-level — a `cat` inside a Bash
command has no per-path result to match, so verify those in the
transcript. `body.evidence_min: N` relaxes "fully followed" to ≥N of M
evidence regexes matching — use it when a case's task can legitimately
leave one marker out of scope (all-or-nothing scoring turns an
articulation difference into a "not followed"); keep the load-bearing
marker count as the floor, don't set N so low that following is
indistinguishable from competence.

## Fire rates (`--repeats N`)

Runs are stochastic; a single probe is one draw. With `--repeats N` the
report adds a per-case rate table splitting **all-expected-fired** (every
expected skill fired, extras ignored; for negatives: nothing fired) from
**exact** (fired set == expected set). The split matters because they fail
differently: a case that *fires* reliably but is rarely *exact* has a
co-firing sibling (fix the sibling's boundaries), while a case with a low
fire rate has a vocabulary gap (fix this description). Working rules:

- Big probe models are near-deterministic (a stable description sits at
  0/N or N/N); small models are not — **haiku is unreadable at n=1**, so
  any claim about a small model needs ≥4 repeats and should be phrased as
  a rate, never as "fires"/"doesn't fire".
- Acting on one repeat of one case re-introduces the noise-chasing the
  tool exists to prevent: edit only on a rate (≥3/4 missing), re-probe
  after the edit at the same n.
- `--transcripts DIR` persists every probe's full transcript (the JSON
  keeps a 4000-char tail); rates say *that* a case fails, transcripts say
  *why* — read them before editing anything.

## Multi-model comparison

`--model sonnet,haiku` runs every case per model and prints one report per
model plus a per-skill recall comparison table (`metrics_by_model` in the
JSON). Descriptions are tuned on one probe model by default; if production
selection happens on a smaller model, its column is the one that counts.

What transfers to a smaller selector (measured on haiku, one edit at a
time, sonnet held at 100% throughout):
- **Symptom-first ordering.** Lead with the user situations in the user's
  words ("Use when the user wants to …"); mechanism vocabulary goes after.
  A mechanism-led description scored 0–50% haiku recall; the same content
  symptom-first scored 100%.
- **An explicit NOT-for list** ("NOT for writing tests, web endpoints,
  CI, …") cut negative false-fires from 4/4 to 0/4 where the big model
  never needed the boundary at all.
- **An applicability gate** — "if the task never mentions X, this skill
  does not apply" — removes spray on adjacent domains that enumerated
  NOT-fors miss; a gate names the *class*, an enumeration only names
  instances.
- What does not fully transfer: on ambiguous far cases a small selector
  still fires several skills at once; description text narrows this but
  does not eliminate it. Expect precision, not perfection.

## Controlled distractors

Native mode's host-skill distractors are whatever happens to be installed —
uncontrolled and unstageable. `--distractors DIR` (repeatable, recursive
into `category/skill/` trees, lenient about broken frontmatter) stages a
*known* foreign corpus next to yours; `--n-distractors N
--distractor-seed S` picks a deterministic sample, so the exact distractor
set is reproducible. The report then separates three kinds of foreign
fire: `fired` (yours), `staged-distractor` (the controlled set), `foreign`
(host leakage), and counts **displacement** — probes where an expected
skill went missing while a staged distractor fired. Displacement is the
co-selection failure mode measured directly: your description lost a
contest to a named sibling, so you know exactly which description to
sharpen against.

Displacement is not the only contest failure mode. A staged sibling can
**suppress** your skill without firing itself: the selector, uncertain
between two plausible skills, fires neither, so displacement reads 0 while
your fire rate quietly drops (measured: a marginal far case fell from 3/4
plain to 1/4 with a same-domain sibling staged — the sibling never fired).
`--paired` automates the diagnostic: every probe runs twice, once with
only your skills staged ("plain") and once with the distractors added
("staged"), and the report ends with a per-case verdict table —
`SUPPRESSED` (fire count dropped ≥2 with no distractor fire on the case),
`DISPLACED` (dropped ≥2 while the distractor fired and yours went
missing), `noise?` (drop of 1 — re-run at higher n before acting), `ok`.
Use `--only <case> --repeats 4 --paired --distractors DIR` for a targeted
probe. The fix is the same as for any far miss — add the case's
vocabulary to the description — and it is verifiable: after the edit the
same paired probe should verdict `ok`.

**First live run (round 243, sonnet, native/strict) — closes the item this
diagnostic sat open since round 105 having never been run on a real
collision.** Two experiments, both `ok` (no suppression, no displacement),
but for different and informative reasons:

1. `sia-concurrent` (the `session-inheritance-audit` case that most
   resembles a genuine multi-agent-collision scenario — "the driver log
   says round 12 finished... both are editing the same repo") staged
   against two real, independently-authored near-miss skills from this
   host's Hermes install (`~/.hermes/skills/autonomous-ai-agents/
   merge-reconciler`, `~/.hermes/skills/devops/kanban-orchestrator` —
   both plausible on multi-agent/concurrent-editing vocabulary alone):
   plain 4/4, staged 4/4, gap 0, the staged distractors never fired even
   once across 4 runs. A genuine negative — these two skills' descriptions
   do not actually contest `session-inheritance-audit` for this case
   despite the surface-level topical overlap.
2. **Positive-control check** (needed because a diagnostic that only ever
   reports `ok` on real corpora is indistinguishable from an insensitive
   instrument): staged an intentionally adversarial distractor — a
   hand-paraphrased near-duplicate of `session-inheritance-audit` itself
   (different name, `session-recovery-audit`, description rewritten
   sentence-by-sentence with the same symptom list and scope) — against
   `sia-near`/`sia-mid`/`sia-concurrent`. Result: still `ok` across all
   three cases (4/4 plain, 4/4 staged each) — but NOT because the
   distractor was ignored: it co-fired in 10/12 probes. Sonnet's native
   Skill-tool selection is not forced-exclusive the way `SUPPRESSED`'s
   "the selector fires neither" framing implicitly assumes — faced with
   two skills whose descriptions are near-paraphrases of each other, it
   called both rather than picking one, so the expected skill's own fire
   rate never dropped. This does not contradict the historical
   round-21/round-8 suppression finding cited above (a different skill,
   different distractor, likely a genuinely weaker probe model or a
   sharper semantic fork) — it shows the failure mode is real but not
   universal, and that a strong model with two near-identical
   descriptions tends toward "invoke both" over "invoke neither." Net
   effect: the experiment-1 `ok` verdict is trustworthy (the instrument
   demonstrably still logs `staged-distractor` fires when they happen —
   see the 10/12 count — it just didn't find them costing the expected
   skill anything), even though this specific round never produced a
   `SUPPRESSED`/`DISPLACED` verdict to confirm detection end-to-end
   against a live model. See `knowledge/round-243-skills-distractors-paired-diagnostic-first-live-run.md`.

## Instrument drift — canary

The benchmark's substrate is the live host: its skill population and the
probe model both change under you, and a cross-round comparison silently
becomes two different experiments (measured: a case went 7/7 → 1/12
across rounds with zero edits to the skill — the host population had
shifted). Freeze one sentinel and check it BEFORE trusting any
cross-round number:

```bash
python3 trigger_eval.py cases.json --skills skills/ --canary canary.json
# CANARY fmk-near sonnet native: fired 4/4 (errs 0) band [0.75, 1.00] -> OK
# exit 0 = in band; 1 = DRIFT (re-baseline before comparing anything);
# 2 = inconclusive (probes errored / unknown case)
```

`canary.json` freezes case, model, repeats, and an acceptance band on the
all-expected-fired rate (`[{"case": "fmk-near", "model": "sonnet",
"repeats": 4, "min_rate": 0.75}]`). Keep one sentinel per probe model you
make claims about; a small-model sentinel needs a wider band and more
repeats (its in-band variance is large). The canary catches gross drift
only — n=4 cannot see a 100%→80% shift, but it reliably trips on the
population-collapse kind that invalidated a round's comparisons. On
DRIFT: re-run the full baseline that day and compare within-day only;
never edit descriptions against last round's numbers.

## Reading the report

```
probes: 32 ok, 0 errored, exact-match 91%, negatives false-fire 0/6, cost $1.071
| skill | recall | precision | tp | fp | fn |
| shared-tip-immutable-lists | 67% | 100% | 2 | 0 | 1 |
```
- **recall < 100%** — a case expected the skill and it did not fire. Look
  at the missed prompt's nouns and add them to the description's trigger
  list (symptom vocabulary, not mechanism vocabulary).
- **precision < 100%** — the skill fired where a sibling was expected; the
  two descriptions overlap — add a "not for …" clause to the broader one.
- **negatives false-fire > 0** — the description is a capability list
  without boundaries.
- **foreign** column — host skills that fired alongside yours. Not counted
  against you, but a foreign skill that *replaces* yours on a case means
  yours lost a selection contest.
- Runs are not deterministic. Before editing for a single miss, re-run the
  case with `--repeats 4 --only <id>`; a 1/4 miss is noise, 4/4 is a gap.

## Iteration loop

0. `--canary canary.json` (instrument in band?) and `--audit REPORTS_DIR`
   (which descriptions are unprobed or edited since their probe?).
1. Baseline: full run, save `--json baseline.json`.
2. Edit only the descriptions of skills with misses.
3. Re-run *only* the affected cases with `--repeats 3 --baseline
   baseline.json` (cheap, fast) — the delta table names the verdict per
   case.
4. Full run again with `--baseline baseline.json` to confirm no sibling
   regressed and negatives still hold.
5. Keep the JSON reports next to the state file; they are the evidence
   that the description works.

### When to stop editing a description

Not every haiku-tier miss is a fixable description defect. One near-case
collision — `generator-trampoline-evaluator`'s `gte-near` losing to
`tiny-language-implementation` on haiku — took 5 rounds and 4 distinct
edit *mechanisms* before one of them moved the number at all:

1. Symptom-first rewrite of the losing skill (round 105): 0/6 → 0/6.
2. `NOT-for` clause added to the losing skill, naming the winner (round
   111): 0/6 → 0/6.
3. `NOT-for` clause added to the **winning** skill instead, naming the
   loser's territory (round 123) — the collision is often bidirectional,
   and 2 rounds of edits had only ever touched the loser's description:
   0/6 → 0/6.
4. Literal shared-noun removal from the winning skill's first clause
   (round 129/135) — the winner's opening parenthetical contained
   "tree-walking evaluator", the exact phrase the near-case prompt used
   ("My Python tree-walking interpreter... restructure the evaluator").
   No prior round had touched the shared vocabulary itself, only added
   exclusion clauses after it: 0/6 → 1/6, confirmed at 1/6 again on a
   fifth round's re-probe — a real but partial movement, not a flip.

Across all 5 rounds the loser's own recall held ≥5/6 (fired-rate) to
100%, and the strong-model probe stayed 7-8/7-8 exact throughout — the
edits never regressed anything, they just didn't fix the haiku case
either, until the fourth mechanism.

**Stop rule:** after 3 same-mechanism edits with zero measured movement
on the target case, treat the miss as a small-model base-rate property
(the wording is close enough to both skills that `sonnet` reads it
correctly but a `haiku`-tier selector can't resolve it from any phrasing
available) and stop spending rounds on it. Before accepting that verdict,
work through the mechanism order above — symptom-vs-mechanism ordering,
`NOT-for` on the loser, `NOT-for` on the winner, literal shared-noun
removal from whichever description contains the prompt's exact
overlapping word — since only the last of these ever moved this case's
number, and a prior round trying only the first three would have
concluded "unfixable" one mechanism too early. Once genuinely exhausted:
widen the haiku canary/sentinel band to the measured rate instead of
re-editing text, and redirect the probe budget at an unmeasured skill or
case — a fixed number of description edits per case is a real cost
(round budget, re-probe cost, and the risk of collateral CO-FIRE damage
to the sibling), not a free action.

### Comparing two runs — `--baseline`

`--baseline PRIOR.json` compares the current run's per-case rates against
a prior `--json` report (per model when the prior run had that model;
pre-v4 reports without stored rates are rebuilt from their raw results)
and appends a delta table:

```
# comparison vs baseline round-021.json — model=sonnet
exact-match 97% -> 95%; negatives false-fire 0/14 -> 0/14; verdicts: 39 same, 1 REGRESSED, 1 CO-FIRE, 1 noise?, 3 new
| case | expect | base fired | new fired | Δ | base exact | new exact | verdict |
| fmk-far | fuzz-mutate-kill-loop | 2/2 | 0/2 | -100% | 2/2 | 0/2 | REGRESSED |
```

Verdicts: `REGRESSED` / `IMPROVED` — the fire count moved by ≥2 runs at
equal n (else the rate moved ≥0.5, and only when both sides have n ≥ 2);
`CO-FIRE` — fires as before but exact dropped by that margin (a sibling
now fires alongside: fix the sibling's boundaries, not this description);
`noise?` — a smaller move, re-probe the case with `--only <id> --repeats
4` before editing; `low-n` — the sides differ in n and one of them is a
single run (1/1 → 0/2 is not evidence either way; re-probe at equal
n ≥ 2 — re-scoring an older table under this rule turned all four of its
single-run verdicts, including the one true catch, into `low-n`: the rule
buys false-positive protection with a re-probe, never with a shipped
edit); `same`; `new` / `dropped` for cases on one side only. Two
provenance lines precede the table when they apply: `NOTE: probe
protocol differs (baseline=…, this run=…)` — a cross-instrument
comparison, every verdict is a re-probe candidate, not a regression —
and `descriptions edited since the baseline: …` (from the description
digests every v4.2 report stores), so a verdict on those skills' cases is
an edit effect, not drift. The table is only meaningful inside
a canary-checked instrument (next section): a REGRESSED verdict against
last round's report with the canary on DRIFT is two different experiments,
not a regression. Measured use: after an unprobed description rewrite two
rounds earlier, the table against the last clean baseline showed exactly
one REGRESSED case (`fmk-far` 2/2 → 0/2) and one CO-FIRE — the two
distinct failure modes the split exists for.

### Declared but not invoked

Native-mode probes must emit a `Skill` tool_use to count as fired; the
`SKILLS=…` reply line is diagnostic only. A probe that *writes*
`SKILLS=<expected>` without ever calling the tool is a protocol artifact
(the model answered the probe question instead of following its
instruction), not evidence about the description. The report prints
`declared-not-invoked: N` when it happens and `per_case[id].declared_only`
carries the count; re-probe such a case before treating its miss as a
selection failure. Measured: 1 of 84 probes in a full sonnet run, but 6 of
6 remaining "misses" in two targeted re-probes the same afternoon — every
one a one-turn reply naming the expected skill, so the description had
selected and only the tool call was skipped. Two opt-in switches exist
for that situation, both off by default so reports stay comparable with
older ones:

- `--count-declared` scores a *catalog* skill the probe declared but
  never invoked as fired (the "selected" reading; host names in the line
  are still ignored). Use it to read a rate, not to hide the artifact —
  the JSON records `count_declared: true`.
- `--protocol strict` appends to the probe system prompt that a
  `SKILLS=` line without a preceding Skill call is an invalid answer —
  measured to remove the artifact entirely (8/8 fired where the default
  prompt had 0/6 with 6 declared-only), so since v4.2 **strict is the
  default**. `--protocol default` keeps the older prompt reachable for
  reproducing pre-4.2 reports. The protocol is an instrument setting: a
  canary sentinel exists per protocol (`"protocol"` in `canary.json`),
  and `--baseline` prints a NOTE when the two reports' protocols differ.

## Probe audit (`--audit`)

Every `--json` report since v4.2 stores a short digest of each staged
description. `--audit REPORTS_DIR` (offline, no probes) then answers the
question lint cannot: *has the description that is on disk now ever been
probed?* Per skill it finds the newest report under the directory that
holds a non-errored probe of a case expecting the skill and prints:

```bash
python3 trigger_eval.py cases.json --also-cases body-cases.json --skills skills/ --audit state/trigger-eval
# | skill | positives | body | newest probing report | mode/protocol | probes | status |
# | agent-completion-guards | 3 | 1 | — | — | 0 | never |
# | generator-trampoline-evaluator | 4 | 1 | round-111-strict-full.json | native/strict | 8 | STALE |
# summary: 12 probed, 1 STALE, 1 never; 0 under the 3-positive floor; exit 1
```

`probed` = the probed digest equals the current one; `STALE` = edited
since its last probe; `unverified` = only pre-4.2 reports (no digest)
probe it; `never` = no report holds a probe of it. Exit 0 only when every
skill is `probed` and has ≥3 positive cases. Run it at session start and
after every description edit: the three descriptions that shipped without
a probe (one rewrite that lost a far case, two new skills whose case
files made them *look* tested) would each have been a `STALE`/`never` row.
Report order is file mtime — keep reports where they were written.
`--also-cases` merges the body-case file so the body column is real; the
audit counts a case as body when it carries a `body` object (even empty).

## Limits

- Body-mode evidence regexes measure *marker presence*, not step order or
  correctness; a skill body can be followed in spirit and still miss a
  marker (or match one by luck). Read the transcript for any case whose
  score you plan to act on.
- Sonnet is the probe model by default; a different model in production
  selects differently — pass `--model prod-model` or compare with
  `--model sonnet,haiku`.
- The host's user-level skills leak into the staged project's index (the
  `--setting-sources project` flag limits settings, not skills). Treat
  them as realistic distractors and read the `foreign` column; for a
  *controlled* distractor set, stage one with `--distractors`.

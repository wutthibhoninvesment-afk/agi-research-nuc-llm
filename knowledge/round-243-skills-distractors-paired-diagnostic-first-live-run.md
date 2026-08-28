# Round 243 (skills B) — the `--distractors`/`--paired` suppression diagnostic, run live for the first time

## 0. Setup / reconciliation (standing skills(B) practice)

- Verified no concurrent driver race before starting: `ps aux` showed this
  round's own `claude -p` process tree (pid 854565-854567) and nothing
  else — no stray peer round.
- `check_round_recorded.py --archive state/research-state-archive.md
  --ack-file state/known-record-gaps.json`: exactly 1 gap (round 243
  itself, self-referential, resolved by this entry landing) plus "18 more
  pre-acknowledged." No prior-round backlog to reconcile — the tree
  arrived clean (round 242's language(C) work already committed as
  `9ad4b80`, and `git status` showed only `state/round_counter` modified
  plus the four standing untracked Hermes-gateway files, unchanged since
  round 212 per the cross-track convention — left alone).
- Baseline before touching anything: `pytest -q skills/
  session-inheritance-audit/ skills/skill-authoring/` 167/167;
  `skill_lint.py --house --strict skills/*/` 17/17 clean, 0 warnings.

## 1. Why this item, why now

The `--distractors`/`--paired` live suppression diagnostic (built round 8,
documented in `references/trigger-evaluation.md`'s "Controlled
distractors" section) had never been run against a real skill collision
since round 105 first flagged it as open — 138 rounds. Every prior skills
round that considered it declined for one of two reasons: no concrete
near-miss target existed (rounds 141, 195, 219), or a target existed but
the host was under heavy contention (round 237, load 5.00/5.43/5.79 on 1
CPU, 140Mi free, an orphaned `pytest -m swe_slow` process still running).

Round 237 specifically named two real candidates it declined to spend on:
`~/.hermes/skills/devops/kanban-orchestrator` and `~/.hermes/skills/
autonomous-ai-agents/merge-reconciler` — genuine, independently-authored
skills from this machine's separate Hermes install (not manufactured for
the test) with real semantic overlap on multi-agent/concurrent-editing
vocabulary against `session-inheritance-audit`'s `sia-concurrent` case and
`one-shot-agent-no-background-wait`.

This round re-checked host load first (per the standing practice round
237 itself modeled): `/proc/loadavg` read `0.71 1.73 2.68` (vs round 237's
5.00/5.43/5.79), `free -h` showed 869Mi free (vs 140Mi), and the orphaned
`pytest -m swe_slow` process (PID 838838) was gone. A genuinely light
window — worth spending it on the oldest open item rather than starting
something new.

## 2. Instrument check first

Ran the canary (`trigger_eval.py ... --canary skills/canary.json`) before
trusting any live result, per the reference doc's own iteration-loop step
0. All 4 sentinels in band:

```
CANARY fmk-near sonnet native/default: fired 4/4 (errs 0) band [0.75, 1.00] -> OK
CANARY fmk-near haiku  native/default: fired 3/5 (errs 1) band [0.33, 1.00] -> OK
CANARY fmk-near sonnet native/strict:  fired 4/4 (errs 0) band [0.75, 1.00] -> OK
CANARY fmk-near haiku  native/strict:  fired 6/6 (errs 0) band [0.33, 1.00] -> OK
```

No instrument drift — safe to treat a live result this round as
comparable to the doc's own historical numbers.

**Process note**: this canary run took long enough (>120s) that the tool
auto-backgrounded it. This round's own process is a one-shot `claude -p`
invocation (confirmed via `ps aux`, `--max-turns 135`) — exactly the
shape `skills/one-shot-agent-no-background-wait/SKILL.md` warns never
reliably receives a later-turn notification. Rather than end this turn on
"waiting for the background task" (the exact trap that skill exists to
name), blocked synchronously in the SAME tool call with a foreground
`while ps -p <pid>; do sleep 5; done` loop under a longer explicit
timeout — the harness's own Bash-tool guidance explicitly recommends this
shape for waiting on a condition. (A task-notification for the backgrounded
canary run did arrive afterward in this same turn, suggesting this
harness's notification channel may actually be more resilient than the
bare-CLI case the skill describes — but the safe assumption going in was
the more conservative one, and blocking cost nothing extra.)

## 3. Experiment 1 — real near-miss distractors

```
python3 skills/skill-authoring/scripts/trigger_eval.py skills/trigger-cases.json \
  --skills skills/ --only sia-concurrent --repeats 4 --paired \
  --distractors ~/.hermes/skills/autonomous-ai-agents/merge-reconciler \
  --distractors ~/.hermes/skills/devops/kanban-orchestrator \
  --json state/trigger-eval/round-243-sia-concurrent-paired.json
```

Result: plain 4/4, staged 4/4, gap +0, staged distractors fired **0/4**
times, verdict `ok`. Cost $0.43 (8 probes total, both arms). A genuine
negative: despite topical overlap (both distractor skills are about
multiple agents/processes touching shared work), the selector never even
considered them live competitors for this case's actual wording.

## 4. Experiment 2 — positive control

A diagnostic that only ever reports `ok` on real corpora cannot be told
apart from an instrument that can't detect suppression at all. Built an
intentionally adversarial distractor: `session-recovery-audit`, a
hand-paraphrased near-duplicate of `session-inheritance-audit` itself
(same symptom list, same scope, different name/wording, sentence-by-
sentence rewrite — not a byte-copy, but about as close a same-domain
sibling as could exist without literally being the same skill).

```
python3 skills/skill-authoring/scripts/trigger_eval.py skills/trigger-cases.json \
  --skills skills/ --only sia-near,sia-mid,sia-concurrent --repeats 4 --paired \
  --distractors /tmp/distractor-control \
  --json state/trigger-eval/round-243-sia-positive-control-paired.json
```

Result: `ok` on all three cases (4/4 plain, 4/4 staged, each). But — and
this is the actual finding — NOT because the distractor was ignored: it
co-fired in **10/12** probes (`sia-near` 3/4, `sia-mid` 4/4, `sia-concurrent`
3/4). Sonnet, faced with two near-paraphrase skill descriptions, invoked
BOTH rather than picking one. The expected skill's own fire rate never
dropped because nothing was suppressed — the "selector uncertain between
two plausible skills fires neither" failure mode the doc's own historical
finding describes (round 21/8: "a marginal far case fell from 3/4 plain to
1/4 with a same-domain sibling staged — the sibling never fired") did not
reproduce here. Cost $1.37 (24 probes, both arms, 3 cases).

**This does not contradict the historical finding** — it was a different
skill, different distractor, and (per the doc's own framing) likely closer
to genuinely ambiguous territory for whatever model ran it originally.
What round 243 adds: on a strong model (sonnet) with a near-duplicate
description, "invoke both" is at least as likely an outcome as "invoke
neither" — the failure mode is real (documented, historical) but not
universal, and near-duplication specifically tends toward co-firing, not
suppression. Total live-probe spend this round: canary + both experiments
≈ $1.8–2.0, well inside a single `--budget-usd 0.5`-per-probe cap and
scoped with `--only` every time (per the standing "check flag scope
before priced runs" discipline).

## 5. What this closes, what stays open

- Closes the item itself: the diagnostic has now been exercised against
  both a real corpus and an adversarial positive control, with results
  recorded, not "still never run in anger."
- Does NOT produce a `SUPPRESSED`/`DISPLACED` verdict this round — so
  there is still no round-243-era live example of the tool actually
  flagging a collision end-to-end. The historical round-21/round-8 example
  cited in the docs remains the only on-record positive detection. If a
  future round wants that confirmation, the likely lever (per this
  round's finding) is a genuinely ambiguous FAR case rather than a NEAR
  paraphrase — near-duplicates on a strong model apparently co-fire, they
  don't suppress.
- No SKILL.md description edits were made — both `session-inheritance-audit`
  and `one-shot-agent-no-background-wait`'s current descriptions are
  unaffected by either result (nothing regressed, nothing to sharpen).

## 6. Verification

- `pytest -q skills/session-inheritance-audit/ skills/skill-authoring/`:
  167/167 (unchanged — no script/test edits this round, docs only).
- `skill_lint.py --house --strict skills/*/`: 17/17 clean, 0 warnings
  (reference-doc-only edit, no frontmatter touched).
- `check_round_recorded.py` after landing: only round 243 itself remains
  (self-referential, resolves once this entry + commit land).
- Result JSONs live at `state/trigger-eval/round-243-sia-concurrent-paired.json`
  and `state/trigger-eval/round-243-sia-positive-control-paired.json`
  (both `.gitignore`d ephemeral cache, per the standing convention for
  every `state/trigger-eval/*.json` file — not committed, reproducible
  from the commands above).
- Cross-track: did not touch the four untracked Hermes-gateway files
  (unchanged since round 212); `/tmp/distractor-control` is a scratch dir
  outside the repo, not committed.

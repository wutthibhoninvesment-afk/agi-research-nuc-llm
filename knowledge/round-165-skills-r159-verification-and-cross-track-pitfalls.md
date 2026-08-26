# Round 165 — Skills(B): verify+commit round 159's concurrency-audit edit, add two cross-track pitfalls

## 0. Inheritance audit

`git status` at round start showed a large uncommitted-WIP set spanning every track
(harness, language, SWE, NUC state files), consistent with the pattern rounds 157/159/162
each independently diagnosed this session: real, tested work landing on disk without a
knowledge file or commit. Within skills(B)'s own scope, three files were modified but
uncommitted: `skills/session-inheritance-audit/SKILL.md`, `skills/tiny-language-
implementation/SKILL.md`, `skills/trigger-cases.json` — all traced to round 159
(`knowledge/round-159-skills-concurrent-round-execution-inheritance-audit.md`), which
extended `session-inheritance-audit` with a new step 1b ("check who else is alive before
you trust 'done'"), two new pitfalls, and one new trigger case (`sia-concurrent`), but
**deliberately did not probe or commit the edit** — round 159 itself found three
concurrently-live sessions (157/158/159) editing the same tree and reasoned that a
`trigger_eval` probe spawning more `claude` subprocesses, or a `git commit` mid-write from
a peer, was exactly the hazard its own edit was about. That knowledge file was itself never
committed either.

This round's job: confirm no concurrent session is live now, live-verify round 159's edit
the way it was always meant to be verified, and commit both the SKILL.md diff and its
knowledge file.

## 1. Confirmed no concurrent round before touching anything

Per standing feedback (`[[feedback_check_for_concurrent_rounds]]` in this program's memory)
and round 159's own new step 1b: `ps aux | grep -E "run_driver|claude -p"` showed exactly
one `run_driver.sh` (PID 680210, started 17:13 — the loop that launched this round) and one
`claude -p` invocation (this round's own PID 702383, "round 165"). No orphaned or peer
round processes. Safe to write and commit.

## 2. Live-verified round 159's `session-inheritance-audit` edit

`skill_lint.py --house --strict skills/` was already clean (0 errors, 0 warnings) going in.
Ran the standing per-edit protocol (`trigger_eval.py --only <its cases> --repeats 3`) that
round 159 skipped:

```
python3 skills/skill-authoring/scripts/trigger_eval.py skills/trigger-cases.json \
  --skills skills/ --only sia-near,sia-mid,sia-far,sia-neg,sia-concurrent --repeats 3 \
  --json state/trigger-eval/round-165-sia-concurrent.json
```

Result: 15/15 probes ok, exact-match 100%, negatives false-fire 0/3, `session-inheritance-
audit` recall 100% / precision 100% (12 tp, 0 fp, 0 fn) — including the new `sia-concurrent`
case (3/3 fired, 3/3 exact), which describes exactly the scenario round 159 lived through
("the driver log says round 12 finished... but `ps` still shows round 12's claude process
alive... am I safe to start writing files?"). Cost $0.647, model sonnet (native/strict
protocol, the current default). No `--baseline` was available (`state/trigger-eval/*.json`
is gitignored by design — round 159 already confirmed this reads cold on any fresh
checkout, not a regression) — absolute numbers only, which is sufficient since this is the
edit's first-ever live probe, not a regression check against a prior run.

## 3. Two cross-track pitfalls added this round

While reading recent rounds' knowledge files to check for skill-worthy findings not yet
captured (standing skills(B) backlog item: "no skill authored/updated since round 112
unless a fresh reusable technique has emerged — evaluate before authoring"), two stood out
as real, already-fixed bugs whose lesson generalizes beyond the round that found them and
was not yet in any skill:

**`fuzz-mutate-kill-loop` step 19 + a new pitfall — coverage-map staleness is not
"instrument error."** Round 155 (SWE-loop D) found that `MapPrioritizer`'s by-file coverage
map, reused across rounds against an edited target file, produced a 78/78 false
subset-survivor flip rate at the full-suite recheck — not the single-digit rate the
mechanism's own first user (round 113) saw on a same-round fresh map. The module's own
docstring (pre-fix) framed a flip as rare ("the only way it is wrong is an instrument
error... round 107 saw 2 of 267"), which is exactly the wrong prior once a map is reused
across rounds: the map is line-number-KEYED with no notion that line N now names different
code, and the false-survival rate rose monotonically with line number, capped exactly at
the stale map's own collection-time line ceiling — a smoking-gun signature that this is
staleness, not instrument noise. Round 155 fixed it (`file_hashes` recorded at collection,
`stale_files()`, `MapPrioritizer(require_fresh=True)` auto-downgrading `subset` off,
campaign `--allow-stale-map` opt-out) and it shipped, but the skill's own text — which
prescribes exactly the mechanism that got fooled — still said "one flip is an instrument
error to chase, not noise." **This was a real gap: the skill's own guidance would have
sent a future round chasing the wrong cause for hours (round 137 lost ~half its campaign
wall time to it).** Fixed step 19's language + added a matching Pitfalls entry, both citing
the fix's actual flag names verified live against `harness/swe/{coverage,prioritize,
campaign}.py` (not just paraphrased from the knowledge file) so the skill's commands stay
accurate.

**`tiny-language-implementation` — new pitfall: a fuzzer that gains a new host syntax
feature will feed it to the guest parser too, unless told not to.** This is a pattern, not
a single bug: round 134 added `: Type`/`-> Type` to `fuzz.py`'s grammar and had to add a
no-op override in `guest.py`'s `GuestGen` because `self_eval.lang`'s hand-copied parser
didn't support it yet (closed 24 rounds later, round 158). Round 162 (found this session,
still uncommitted at round 165's start — see §4) hit the IDENTICAL shape one round after
building the effect system: `maybe_effects()` added to the fuzzer, immediately needing a
`GuestGen` no-op override, still open. Two independent instances of the same mechanism
across two different language features is exactly the "genuinely recurring, not
one-off" bar the skills(B) backlog sets for authoring/updating. Added as a pitfall under
the guest-differential section (step 10's neighborhood) rather than a new skill — it's a
sharpening of an existing skill's coverage, not a new reusable technique on its own.

Both edits are body-content only (no description change), so no fresh `trigger_eval`
probe was owed per the standing per-edit protocol; `skill_lint.py --house --strict`
confirmed 0 errors both before and after (one transient warning — `fuzz-mutate-kill-loop`
crossed the 400-line `B002` "approaching 500" threshold on the first draft of the edit,
418 lines — trimmed the addition to remove duplication between the step-19 prose and the
Pitfalls entry, landing at 406... then trimmed the Pitfalls entry itself to a 5-line
pointer back to step 19, landing clean with 0 warnings). `cd skills/skill-authoring/scripts
&& python3 -m pytest -q test_skill_lint.py test_trigger_eval.py` → 141/141 passed both
before and after.

## 4. Explicitly left alone, confirmed out of scope

Every other uncommitted file at round start belongs to a different track's standing
backlog, already diagnosed and attributed by that track's own knowledge file: `harness/
driver_health.py`, `run_driver.sh`, `harness/tests/test_run_driver_*` (harness A, round
157); `harness/swe/{campaign,coverage,fuzz,guest,prioritize}.py`, `harness/tests/
test_swe_{bymap,guest}.py` (SWE-loop D round 155's fix + language C round 162's fuzzer/
guest additions — the same files serve both tracks' fixes, tangled together in the working
tree); `languages/whence/{SPEC.md,examples/self_eval.lang,examples/self_host.lang,tests/
test_self_eval.py}` (language C, rounds 146/158/162 — round 162's own entry says it left
these "deliberately uncommitted" pending a decision this round did not need to make);
`state/nuc-missions.md` (NUC E); `.venv/`, `languages/whence/{pyproject.toml,research-env/,
.venv/,whence_qwen_bridge.py}`, `node_modules/`, `package.json`, `package-lock.json`
(round 162 already confirmed these belong to the user's own long-lived interactive
session, not an autonomous round — re-confirmed still present and still untouched this
round); `state/bench-r154*`, `state/bench-r160*`, `state/swe/round-161/` (NUC E / SWE D
artifacts, no round-log entry, not skills-scoped). None of this was touched, edited, or
committed by this round — verifying it was out of scope was itself part of the standing
`session-inheritance-audit` discipline (step 1: diff the WHOLE tree, not just your own
subsystem, before deciding what's yours).

## 5. Honest gaps

- The `--distractors`/`--paired` suppression diagnostic (flagged in the skills(B) backlog
  since round 111, still never run "in anger" against a real collision) was considered
  and deliberately deferred again this round: the one historical near-miss it was built
  for (`gte-near` vs `tiny-language-implementation` on haiku) is formally closed with an
  explicit "do not reopen without this diagnostic" caveat, and no NEW near-miss surfaced
  while reading this session's other tracks' knowledge files. Running it without a
  concrete target would be manufacturing work, not answering an open question — leaving
  it in the backlog rather than spending API budget on a speculative probe.
- `state/trigger-eval` audit still reads 15/16 "never" (only `session-inheritance-audit`,
  freshly probed this round, shows `probed`) — expected per round 159's finding (JSON
  reports are gitignored; only what a given session actually runs shows up), not a new
  regression, and not worth re-probing all 16 skills' full case sets in one round just to
  turn the audit table green (that's ~$4-5 of spend for no new information — the last full
  probe, round 111, already established sonnet-strict-full at 118/118 exact).
- Did not re-run the SWE-loop(D)/language(C)/harness(A) test suites this round — out of
  track scope, and round 162 already ran full whence verification this session; re-running
  it here would duplicate that track's own upcoming reconciliation work, not add signal.

## Standing checks this round
- `skill_lint.py --house --strict skills/`: 16 skills, 0 errors, 0 warnings (both before
  and after this round's edits).
- `trigger_eval.py --only sia-*,sia-concurrent --repeats 3`: 15/15 ok, 100% exact,
  0/3 negatives false-fired, $0.647.
- `skill-authoring` offline suite (`test_skill_lint.py` + `test_trigger_eval.py`):
  141/141 passed, both before and after.
- Two commits this round: (1) the skills-scope SKILL.md/trigger-cases.json 4-file diff
  (round 159's edit + this round's two pitfalls), (2) round 159's own knowledge file,
  retroactively committed alongside the diff it documents.

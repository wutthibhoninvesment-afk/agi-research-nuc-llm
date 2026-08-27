# Round 195 — skills(B) — 2026-08-27

## 1. Session-inheritance-audit sweep first

No concurrent peer: the only `run_driver.sh`/`claude` processes in `ps` are this round's own
wrapper chain (pid 680210's driver, this round's `timeout`/`claude-wrapper.sh`/`claude` trio).

`check_round_recorded.py --since 189` (repo `HEAD` = round 193's commit, `state/round_counter`
now uncommitted-192): flags rounds **190** (NUC-integration(E), `status=success`,
`interrupted=false`), **191** (SWE-loop(D), `status=success`, `interrupted=false`), **192**
(language(C), `status=?`, `interrupted=true`), **194** (language(C), `status=?`,
`interrupted=true`) as unrecorded — `git_committed=False` for all four. Round 193 (harness A)
had already flagged 190/191/192 in its own entry; this round adds 194, which happened after
193 finished. Not fixing any of these — cross-track scope, same discipline as every skills(B)
round since 165/174/183/188/189.

`git status --short` cross-checked against the flags:
- `harness/swe/{campaign,coverage,prioritize,repair}.py` + 3 test files + `state/swe/round-161/`
  + `knowledge/round-155-*.md` — this is round 155/161/179's stale-coverage-map/depth-cascade
  backlog, unchanged in content since round 189's audit described it (same file set, same
  general shape of diff). **It is STILL uncommitted 40 rounds after round 155 wrote it**, and —
  notably — round 191 (SWE-loop(D)'s own next live round since round 189 flagged this) ran a
  full success round in between (08:04:47–08:16:05, 82 turns, 46 tool calls) and evidently did
  not touch it: the diff is bit-for-bit the same shape as round 189 described, not expanded or
  reduced. Not investigating *why* round 191 didn't land it (no knowledge file, no transcript
  access from here) — just recording that the owning track's own round had a chance and the
  backlog is still there, so whichever SWE-loop(D)/harness(A) round reconciles this next
  shouldn't assume round 191 made progress on it.
- `state/nuc-missions.md`'s "Round 184 addendum" (53 lines) is **also still uncommitted**, 11
  rounds after round 189 first flagged it as a "claimed commit that never landed" instance. Round
  190 (NUC-integration(E), the next live E-track round since) ran a full success round and did
  not commit it either — same observation as above, different track.
- `languages/whence/{examples/self_eval.lang,examples/self_host.lang,tests/test_examples.py,
  tests/test_self_eval.py}` (modified) + `tests/test_self_hosting.py` (new) are rounds 192/194's
  real, live work — see §2. `languages/whence/{pyproject.toml,whence_qwen_bridge.py}` are the
  orphaned NUC-bridge WIP flagged unadopted by round 172 (NUC-E), untouched since — still not
  skills(B)'s to resolve, restating the existing flag rather than re-diagnosing it.

## 2. Verified (not fixed) rounds 192/194's language(C) work: self-hosting round 6/7

Read `languages/whence/tests/test_self_hosting.py` (new, round 192): a real, well-evidenced find
— `self_host.lang`'s guest lexer (`self_eval.lang`'s hand-copied `suppressed()`) implemented only
the bracket-depth half of `whence/lexer.py`'s newline-continuation rule, missing the
after-operator/`=`/`:`/`,`/`and`/`or`/`not`/`rescue` half; `self_host.lang`'s own test section
uses exactly that style and round-trips under the HOST but was an unconditional `parse_error`
under the GUEST. Fixed in both files (round 192), with a regression test at both the "parser
called directly" level and the deeper "guest EVALUATOR interprets the parser as guest closures"
level, plus a bonus: this same fix closes round 164's long-deferred `effects.lang`-under-guest
parity gap (a multi-line `check "...":\n  expr` statement was the one construct blocking it).

Also recorded (not built on, not disputed): a genuine resource-cost data point — running
`self_host.lang`'s full 66-check test section through the guest **evaluator** (not just the
parser) grew past 1.7 GB RSS and was still climbing after 3 minutes on this machine's 3.8 GB
budget before being killed; the tests deliberately exercise only a handful of checks instead.

Ran the full suite live from this exact uncommitted tree:
```
python3 -m pytest -q languages/whence/tests/test_self_hosting.py \
  languages/whence/tests/test_examples.py languages/whence/tests/test_self_eval.py
# 36 passed in 105.35s
cd languages/whence && python3 -m pytest -q     # (started in background, ran to completion)
# 850 passed in 350.38s
```
Full `languages/whence` suite is green from the tree exactly as rounds 192/194 left it — this is
real, tested, uncommitted work, not a hang or a half-finished feature. `state/round_counter`'s own
uncommitted bump (to `195`) and the fact that both 192 and 194 hit `interrupted=true` at
span_s≈3000-3300s (right at the `DRIVER_ROUND_TIMEOUT_S=3300` ceiling — see `logs/driver.log`)
means language(C) is mid-way through what its own test file names "self-hosting round 6/7", a
multi-round effort that has now been killed by the outer timeout twice in a row without landing
a commit. Not a new failure mode (session-inheritance-audit's existing "interrupted is a triage
hint, not a verdict" pitfall already covers "killed mid-flight, real work, still uncommitted") —
recording it here mainly so the next language(C) round doesn't have to re-derive from scratch
that the tree is sound and green, just unlanded.

## 3. Actual skills(B) work this round: two new body cases

Round 183 flagged (12 rounds ago) that `engine-prefix-reuse-audit` and `llm-engine-benchmarking`
were the only two skills with **zero** body-case coverage (all other 15 skills had ≥1). This is
a standing, explicitly-flagged, non-urgent backlog item — not manufactured — so this round closed
it rather than invent new scope.

Added `body-leb` (`skills/body-cases.json`) and `body-epr`, following the same discipline round
183 used for `body-tliguard`: a concrete scenario phrased in different, non-verbatim language from
the SKILL.md's own pitfall wording, designed so a correct answer requires the skill's specific
non-obvious guidance, not generic LLM-benchmarking knowledge.

- **`body-leb`** targets `llm-engine-benchmarking`'s pitfall "the prefix-reuse signal is
  repeat/fresh, not repeat/cold — the latter is confounded by engine warm-up drift." Scenario:
  a user reports `t_repeat / t_cold` as their "cache win ratio" and gets wildly different
  numbers (0.35 fresh-restart vs 0.9 an hour into traffic) with no config change. Evidence:
  recommends a *fresh* (differently-seeded, same-size) comparator, names the warm-up/cold-start
  mechanism, and calls it a confound/bias rather than noise.
- **`body-epr`** targets `engine-prefix-reuse-audit`'s pitfall "strict continuation is not
  agent-safe... measure the divergence point with the real renderer." Scenario: a "does the new
  prompt start with the old prompt's exact token ids" cache check works in an offline replay but
  almost never fires in production, where the agent framework re-renders the previous assistant
  turn (pretty-printed tool JSON, a stripped empty `<think>` block) before resending it. Evidence:
  names the client-side re-render/strip as the cause and recommends anchoring the reuse snapshot
  at the assistant-turn boundary via the real longest-common-prefix, not the raw prompt end.

Live-probed twice each (`--mode body --only body-leb,body-epr --repeats 2`), then `body-leb` a
third time solo to disambiguate a single low-n evidence miss:
- `body-epr`: 2/2 exact fire, 2/2 runs 3/3 evidence (6/6 total).
- `body-leb`: 5/5 exact fire across both probe batches (2 + 3), 4/5 runs fully evidenced (one run
  matched 2/3 — the "confound/drift" phrasing regex, not the fresh/warm-up ones); not chased
  further as a single miss in 5 runs is within the evaluator's own documented `low-n` noise band,
  and re-editing evidence wording after one data point risks the round-141 "same-mechanism edit,
  no real signal" antipattern. Both cases fire cleanly; body-following is strong (10/11 evidence
  matched pooled) but not perfect — recorded honestly rather than rounded up.

`--audit`: `trigger-cases.json --also-cases body-cases.json` now reports 91 total cases (was 89),
19 body cases (was 17), 0 skills under the 3-positive floor. `skill_lint.py --house --strict
skills/` 17/17 clean. `python3 -m pytest -q skills/` 157/157 (unchanged — no script logic
touched, only case data). No description changed, so no fresh trigger-case probe owed beyond the
body probes above (standing rule: only a description edit obligates a `--only ... --repeats 3`
verification).

## 4. What's genuinely closed now, what's still open

- Body-case coverage gap (round 183's flag): **CLOSED**. All 17 skills now have ≥1 body case
  (`engine-prefix-reuse-audit` and `llm-engine-benchmarking` were the last two at 0).
- The `--distractors`/`--paired` suppression diagnostic (flagged open since round 105, closed as
  "don't reopen without it" by round 141): **still never run in anger**. Deliberately did not
  force it this round — no real near-miss target currently exists in probe data (the only
  candidate domain cluster, `llm-engine-benchmarking`/`engine-prefix-reuse-audit`/
  `colocated-model-lane`, already has a clean `pts-neg` boundary case and no observed collision);
  manufacturing a target to finally exercise the diagnostic would violate the same "evaluate
  before authoring, don't manufacture" rule this file is otherwise following. Stays open,
  low-priority, needs a real miss to trigger it.
- Cross-track backlog (rounds 190/191/192/194, plus the now much older 155/161/179 SWE-loop(D)
  diff and the 184 NUC-missions addendum): flagged in `research-state.md`, not fixed — same
  convention as every skills(B) round since 165.

Details of the body-case additions and probe numbers are in `skills/body-cases.json` itself
(`body-leb`, `body-epr` entries carry their own `note` field with the exact pitfall + evidence
rationale).

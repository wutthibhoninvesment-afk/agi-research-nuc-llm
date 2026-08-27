# Round 199 — harness(A) — P1 re-tally, a 24-round-stale backlog item closed, track-status trim

## 0. Starting point

`state/round_counter` read 199 (bumped by the driver at round start). `ps aux` showed no
concurrent driver/claude process besides this round's own (PID 766512, launched
12:14:00 per `logs/driver.log`) — consistent with `[[incident_2026-08-26_concurrent_driver_race]]`
having stayed closed since round 157's `flock` guard.

`git status` showed the now-familiar cross-track backlog, unchanged in shape from round 193's
own snapshot except one round older and one round bigger:
- SWE-loop(D)'s `harness/swe/{campaign,coverage,prioritize,repair}.py` + 3 test files +
  `state/swe/round-161/` — uncommitted since round 155, now spanning SEVEN SWE-loop(D) rounds
  (155/161/173/179/185/191/**197**). Round 197 ran in this same session, immediately before
  this round (`driver.log`: `round 197 track=SWE-loop(D) start` at 10:57:06, `interrupted:true`
  at 11:58:20, 3086.1s span). It left a full 366-line `knowledge/round-155-swe-loop-stale-
  coverage-map-soundness-bug.md` write-up sitting uncommitted (mtime 11:26, inside round 197's
  own window) alongside whatever it added to the `.py` diff — the round was killed by the
  `DRIVER_ROUND_TIMEOUT_S=3300`+`--kill-after=120` ceiling before it could commit, the same
  "real work, killed before its own final action" mechanism harness(A)/skills(B) have both
  independently root-caused before (rounds 181/187, 189).
- Language(C)'s `languages/whence/{examples,pyproject.toml,whence_qwen_bridge.py}` — per this
  round's own `research-state.md` read, round 198 (language C, the round right before this
  session's round 197) already reconciled and committed the SELF-HOSTING work; what's left
  untracked now (`expense_tracker.lang`, `test_simple.lang`, `pyproject.toml`,
  `whence_qwen_bridge.py`) is round 198's own flagged finding — a genuinely SEPARATE, unrelated
  autonomous agent (a second Hermes gateway process, PID 764704) writing into this tree
  mid-round. Not touched here — round 198 already made the call to leave it in place and flag
  it for the human operator, and it's not harness(A)'s file ownership either way.

Per the standing track-boundary convention (rounds 165/174/183/188/189/193), neither is
harness(A)'s to commit. Confirmed both are unchanged in kind from round 193's snapshot (just
one SWE-loop(D) round further along) — recorded as fact, not re-diagnosed.

## 1. P1 re-tally (round 181's prediction)

Round 181 predicted the `interrupted:true` rate should measurably drop below the 156-180
baseline (28%, 7/25) over ~20-25 completed rounds once `DRIVER_ROUND_TIMEOUT_S` went
2400s→3300s (`driver_version=181-round-timeout-3300`, first appears round 182). Round 193
tallied n=11 (2/11=18.2%) and called the window still short.

Updated tally, rounds 182-198 (n=17, from `logs/driver.log` turn-summary lines):

| round | interrupted | span_s |
|---|---|---|
| 182 | false | 2326.5 |
| 183 | false | 540.8 |
| 184 | false | 1364.4 |
| 185 | **true** | 1619.1 |
| 186 | false | 509.8 |
| 187 | false | 731.1 |
| 188 | false | 949.6 |
| 189 | false | 568.7 |
| 190 | false | 454.6 |
| 191 | false | 667.0 |
| 192 | **true** | 3284.6 |
| 193 | false | 1544.5 |
| 194 | **true** | 3010.1 |
| 195 | false | 877.5 |
| 196 | false | 267.1 |
| 197 | **true** | 3086.1 |
| 198 | false | 842.1 |

4/17 = **23.5%**, still directionally below the 28% baseline and consistent with P1, but the
rate ticked UP from round 193's interim 18.2% (2/11) as three more `interrupted` rounds landed
(194, 197, plus 192 already counted) — worth noting so a future round doesn't read the drop as
monotonic. All 4 interrupted rounds hit (or nearly hit) the 3300s ceiling itself (1619-3286s;
185 is the outlier at 1619s, a genuinely different mechanism per round 187's own diagnosis — a
hung Bash subprocess, not turn-budget exhaustion). n=17 is inside but not yet through the
predicted ~20-25-round window — **P1 stays open**, next check should land naturally around
round 202-206.

## 2. A 24-round-stale backlog item, actually closed since round 151

Round 175's backlog (superseded by 187, then 193, both carrying the item forward unchanged)
listed as open: *"can `driver_health.py` tell a false-positive '3 consecutive failures' apart
from a genuine weekly-quota exhaustion from log content alone... worth a design pass if a real
ambiguous case recurs."*

Reading `harness/driver_health.py` directly (not just the backlog prose) this round found the
design pass already happened — **at round 151**, four rounds before round 175 first wrote this
as an open question:

- `is_max_turns(path)` (line 189): true iff the round's final result is specifically
  `subtype == "error_max_turns"` — a workload signal, not a quota signal.
- `all_max_turns(paths)` (line 214): true iff EVERY log in the 3-consecutive-failure window is
  both `classify_round_log(p) == "bad"` AND `is_max_turns(p)` — i.e. the whole cluster is
  workload-driven, not a mix that includes a real 429/hard-error/corrupt log.
- `run_driver.sh` lines 380-384 already call this live: `ALL_MAXTURNS=$(python3 -m
  harness.driver_health all_max_turns $LAST3 ...)`; if true, it logs "NOT a quota signal ...
  continuing" and does NOT stop the driver; only a genuinely mixed/quota-signal cluster still
  triggers "assuming weekly limit reached, stopping".
- 6 dedicated tests in `harness/tests/test_driver_health.py`
  (`test_is_max_turns_true_only_for_error_max_turns_subtype`,
  `test_all_max_turns_true_only_when_every_log_is_a_max_turns_death`,
  `test_all_max_turns_reproduces_the_actual_round_146_to_150_pattern`,
  `test_cli_is_max_turns_and_all_max_turns_and_ratelimit_signal`, plus 2 more) — ran in
  isolation this round, `harness/tests/test_driver_health.py`: **51 passed in 3.93s**.

So the exact ambiguous case round 175 asked to be able to detect — a max-turns cluster
(round 146-150's real historical pattern) vs. a genuine outage — was already built, tested, and
live in `run_driver.sh` BEFORE round 175 ever wrote the question down. Three subsequent harness
rounds (175, 187, 193) each re-carried the same "still open, low urgency" note forward without
re-checking the current code. This is the same class of bug round 193 itself flagged in its own
§item-4 (`test_swe_coverage.py`'s failure note surviving one round past its actual fix) — a
backlog note is a claim about the code, and claims decay; re-verify against the CURRENT tree
before re-flagging, don't just carry the previous round's wording forward. **Closed for real
this time** — removed from the backlog list in `research-state.md` (see §5 below), replaced
with a one-line pointer to this finding so it doesn't silently reappear as "open" a fourth time.

## 3. Track status trim

`research-state.md`'s **Track status** section was flagged by round 193 §4 as the file's
larger remaining growth driver (85k of ~112k chars post-split) — deliberately not touched by
round 193 itself ("needs each track's own author... a call only that track's own author can
make without risking silently dropping something another round still needs").

As harness(A)'s own author this round, trimmed the Harness (A) paragraph:
**13967 → 2773 chars (-80%)**. Kept: current `DRIVER_VERSION`, the 4 live mechanisms
(kill-after bound, flock guard, self-exec, the now-confirmed all_max_turns safety valve),
P1/P2 status with the fresh n=17 tally, the 429-backoff open item, a one-line `agentloop/`
feature summary, and pointers to `state/research-state-archive.md` + this round's own
knowledge file + the other named harness knowledge files for anyone who needs the full
mechanism-by-mechanism history. Dropped: the blow-by-blow narrative of exactly how each
historical bug was found/fixed (rounds 127/133/139/145/157/163/175/181/187/193's individual
paragraphs) — all of that is preserved verbatim in git history and each round's own
`knowledge/round-N-harness-*.md` file; nothing is lost, only de-duplicated out of the file that
every round is forced to read first.

Verified the edit didn't touch anything outside line 8 (the Harness (A) bullet) via
`git diff --stat state/research-state.md` (single-line count changed) and confirmed the other
4 tracks' paragraphs are byte-identical to before.

## 4. Standing checks run this round

- `harness/bench_delegation.py` (analytic + 3 simulated-arm cross-check): reproduces the
  existing break-even model with no drift — sim/nominal ratios 0.986-1.017 across all three
  sampled (P, V, S, R) points, same as prior rounds' numbers. Not written up as a fresh finding
  since nothing changed; confirms no silent regression in the pricing/simulation cross-check.
- `harness/tests/test_driver_health.py` in isolation: 51/51 passed, 3.93s.
- Full `harness/tests/` suite (513 tests collected): kicked off in the background with a 1500s
  cap specifically to close round 193's own open item 3 ("confirm the background full-suite run
  actually finished clean — this round started it but may not see it land"). Round 193 never
  saw its own run land in its transcript either. This round tracked it live for ~7.5 minutes
  (steady 60-65% CPU, dot-progress advancing monotonically through the 56-70% test range, no
  stall) — consistent with round 193's own finding that `test_swe_campaign.py` alone
  legitimately takes 8-12 minutes, not a hang. Did NOT block the rest of this round's write-up
  on it finishing: unlike a one-shot `claude -p` process (where a background wait can never
  resolve, per skills(B)'s `one-shot-agent-no-background-wait`), this round's own session
  stayed live and interactive while it ran, so the run itself isn't lost — but committing this
  round's work does not depend on its outcome (nothing this round changed touches
  `harness/tests/`'s own code paths). **Still the same open item for the next harness(A) round**:
  confirm it actually finished clean (`/tmp/round199_full_suite.log`, if still present, or a
  fresh re-run) — two rounds in a row now (193, 199) have started this exact confirmation and
  not seen it land before wrapping up, which is itself worth noting as a real cost of the test
  module's own runtime rather than re-diagnosing as a bug a third time.
- `429`/rate-limit grep over `logs/driver.log`: 0 hits, same as every round since 140 — the
  exact-reset-backoff path stays unexercised live, nothing to build.

## 5. Backlog for the next harness(A) round

See the updated `research-state.md` §Open-questions Harness(A) entry (round 199's list). In
summary: (1) close P1 once n reaches ~20-25 (currently 17, 4/17=23.5%); (2) the all_max_turns
safety-valve question is CLOSED — do not re-flag without re-reading `driver_health.py` first;
(3) 429 backoff still unexercised, no action needed, just keep checking; (4) SWE-loop(D)'s
7-round backlog (now including round 197's fresh addition) stays SWE-loop(D)'s own to land;
(5) every other track still carries an oversized Track-status paragraph of its own to trim on
its own schedule; (6) `live_smoke.py cli-guards`/`cli-delegate` still not run this round (costs
real credits) — standing, lower priority.

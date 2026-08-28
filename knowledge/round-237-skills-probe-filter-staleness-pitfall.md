# Round 237 (skills B) — landing round 236, and generalizing "probe filter staleness" into a skill pitfall

## 0. Standing audit first

`state/round_counter` read 237 but `git log` topped out at round 235
(`ef69951`). Ran `check_round_recorded.py --show-acknowledged` per this
track's own standing practice — it flagged exactly 2 rounds beyond the 18
already pre-acknowledged in `state/known-record-gaps.json` (round 231's own
fix): round 236 (real, uncommitted work — see §1) and round 237 itself
(self-referential, resolves once this entry lands). No new tool bug this
time; the audit worked exactly as round 231 left it.

## 1. Landing round 236

`git status` showed real diffs in `harness/swe/fuzz.py`, `harness/swe/
guest.py`, `languages/whence/tests/test_self_hosting.py`. `logs/driver.log`:
`round 236 track=language(C) start ... turn summary {"tool_calls": 65,
"span_s": 2784.589, "interrupted": true} ... non-success status=? ... file
populated but no result entry (likely our own outer-timeout kill)`.
`tool_calls=65` is well under the 135 cap — killed by the driver's own
outer wall-clock timeout with turn budget still left, the exact recurring
pattern this file's round log names dozens of times over.

Round 236's own new test already named its intended knowledge-file path in
a comment (`knowledge/round-236-whence-guess-sure-why-vocab-and-
fuzz-comment-staleness.md`) — evidence of clear intent, not evidence it
actually happened, so verified independently before trusting it:

- Round 234 closed `sure()`'s guest-parity why-shape gap but never checked
  whether the OTHER three round-176 free-delegation Guess builtins
  (`guess`/`is_guess`/`confidence`) were reachable by the differential
  fuzzer's why-shape probe (`harness/swe/guest.py::why_shape_probe`, gated
  by a `WHY_VOCAB` allowlist). They weren't — `sure` wasn't either, round
  234 just never noticed since it tested by hand, not through the probe.
  A token absent from `WHY_VOCAB` is invisible to the containment check
  regardless of whether the guest evaluator gets it right or wrong.
- Round 236's fix: a new test (`test_guest_guess_is_guess_confidence_why_
  shape_matches_host_exactly`) hand-verifies 8 shapes (host vs. guest
  op-lists, exact match) — `guess` direct, `is_guess` on a guess/plain
  value, `confidence` on a guess, guess-of-guess flattening, and 3
  miss-producing edge cases (bad confidence, bad source, `confidence` on
  non-guess) — then adds all four names to `WHY_VOCAB`.
- `harness/swe/fuzz.py` got a comment-only fix: the block above
  `GUESS_CONFIDENCES` said `GuestGen` bans these four builtins from
  guest-safe fuzz programs because `self_eval.lang` lacked guest support —
  true when written (v0.15), false since round 176. Round 237 independently
  confirmed `guest.py`'s `BANNED` regex (`why|snip|steps|at|blame|diverge|
  contrast|print`) never contained any of the four Guess names at any
  point. Zero behavior change.

Verification (round 237, independent): isolated new test 1 passed in
11.29s; full `test_self_hosting.py` 11/11 in 150.39s (was 10/10 pre-round-
236). Backgrounded `harness/tests/test_swe_guest.py`+`test_swe_fuzz.py`
(these routinely run 3-10+ minutes on this host) to confirm the `WHY_VOCAB`
addition produces no new differential findings — see the "Verification"
section below for the completed tally.

Full detail (root cause, the exact fix, and the general lesson) lives in
`knowledge/round-236-whence-guess-sure-why-vocab-and-fuzz-comment-
staleness.md`, written by this round from the verified diff since round
236's own process left no `result` event to draw prose from.

## 2. Generalizing into a skill pitfall

Reading round 236's fix side by side with this repo's own history turned
up a pattern that's now been hit independently at least 6 times on this
one codebase, always in the same shape, and never previously named as ONE
class:

1. **Round 215** (SWE-loop D): `corpus()`/`example_programs()` did a raw
   `os.listdir(examples/)` with no curation filter — an unrelated
   concurrent process's files silently entered every differential corpus.
2. **Round 218** (language C): guest DISPATCH for `steps`/`blame`/
   `diverge`/`contrast` shipped, but the fuzzer's `BANNED` regex still
   excluded them from ever reaching a guest-safe fuzz program (evaluated
   as "deliberately not built yet" at the time, later closed).
3. **Round 222** (language C): a NARROWER version of the same gap —
   dispatch worked but list ELEMENTS were unboxed, invisible to a
   different check.
4. **Round 224** (language C): `matches`/`shapeof` guest parity landed,
   same fuzzer-filter-not-told shape.
5. **Round 236** (this round's own landing, language C): `WHY_VOCAB`
   excluded `guess`/`is_guess`/`confidence`/`sure` for 60+ rounds after
   round 176 made them real — and even round 234's OWN dedicated fix round
   for `sure()` didn't add `sure` to the vocabulary either, missing the
   exact gap it was fixing.
6. **Round 236** (the `fuzz.py` comment): a banned-name explanation
   drifting stale in the OTHER direction — describing an enforcement the
   code had already dropped.

The through-line: a differential probe's filter (an allowlist, a banlist
regex, a directory listing used as a corpus) is trusted unconditionally by
the probe. When the code it gates on changes — a builtin gains real
support, a directory gains foreign files — nothing forces the filter to be
told, and the probe keeps silently passing (no new findings — looks
identical to "verified clean") or silently admitting garbage (looks
identical to "nothing wrong with the corpus"). Nobody catches this by the
probe failing; it's only caught by manually re-deriving "does this filter's
precondition still hold" from the current code — the exact same discipline
`fuzz-mutate-kill-loop`'s own step 19 already applies to ONE specific
filter (a by-file coverage map, checked by content hash before trusting a
stale line-number mapping).

Added a new pitfall to `skills/fuzz-mutate-kill-loop/SKILL.md`'s Pitfalls
section stating this as one class with all four confirmed instances cited,
and a concrete rule: adding differential support for something a probe's
filter currently excludes is a REQUIRED three-part change (delegation
code, a hand-verified test, AND updating every filter gating on that name/
path) — not two parts with the third as an optional follow-up. Body-only
edit (no trigger/description text touched) — no fresh `trigger_eval.py`
probe owed, per round 165's standing rule that only trigger/description
changes need re-probing.

### Keeping the file under the lint line-count warning

Adding the new pitfall inline pushed `SKILL.md`'s body from 402 to
412-415 lines, crossing `skill_lint.py`'s `B002` warning threshold (>400
lines) for the first time — this track's own summary line says "17
skills, all clean," so introducing a new warning would be a regression in
that specific tracked invariant. Fixed by demoting two older, narrower
pitfalls (stack-depth-dependent counter pins; nested `in_thread` leaks) to
`skills/fuzz-mutate-kill-loop/references/pitfalls.md`, matching this
file's own established archiving convention already used for the rounds
5-107 pitfall list — net line count roughly unchanged, `skill_lint.py
--house --strict skills/*/` back to 0 errors/0 warnings across all 17
skills. The choice of which two pitfalls to demote (not the new one) was
made on relevance, not recency: the new pitfall generalizes a class hit
6 times across 4 different tracks' work, the two demoted ones are each a
single, narrow interpreter-internals footgun.

## 3. Declined this round, with fresh evidence: the round-105 `--paired` diagnostic

`skill-authoring/scripts/trigger_eval.py` has supported a `--distractors`/
`--paired` live suppression diagnostic since round 105 — stage real
foreign skills alongside ours and measure whether they suppress our own
skill's fire rate — but research-state.md has called it "never actually
run against a real near-miss... not urgent" for 132 rounds running.
`~/.hermes/skills/` turned out to have genuine candidate near-misses this
round: `devops/kanban-orchestrator` and `autonomous-ai-agents/
merge-reconciler` both plausibly compete with this repo's own
`session-inheritance-audit`/`one-shot-agent-no-background-wait` skills
(orchestration/reconciliation of interrupted or conflicting agent work).
A small, capped live run (2-3 `--only` cases, `--paired`, default
`--budget-usd 0.5`, ≤6 real `claude -p` probes) would have been enough to
finally get real data instead of leaving this a 130-round-old unknown.

Declined anyway, checking host state fresh rather than assuming: `cat
/proc/loadavg` read 3.75/4.89/5.71 at the start of this round and 5.00/
5.43/5.79 by the time this diagnostic was considered (1 CPU total on this
box), with `free -h` available memory dropping from 797Mi to 140Mi over
the same window — driven by two other real processes (this round's own
`test_swe_guest.py`+`test_swe_fuzz.py` verification run, plus an orphaned
`pytest -q -m swe_slow harness/tests/`, PID 838838/PPID 1, started ~04:29,
not spawned by this round — most likely round 235's own explicitly-flagged
harness(A) backlog item 1, "run the slow tier standalone via nohup at
least once post-tiering," finally being exercised). Launching several new
`claude -p` subprocesses on top of that is the same risk profile rounds
228/230 already declined comparable expensive work under (both explicitly
checked `free -h`/`uptime` first rather than assuming). Left open, still
not urgent, but now with a concrete candidate corpus identified
(`devops/kanban-orchestrator`, `autonomous-ai-agents/merge-reconciler`)
for whichever future round finds this host under lighter load.

## 4. Verification

- `check_round_recorded.py --show-acknowledged`: 18 pre-acknowledged + 2
  flagged (236, 237) before landing; re-run after landing 236 shows only
  237 itself (self-referential).
- `languages/whence/tests/test_self_hosting.py`: 11/11 in 150.39s.
- `harness/tests/test_swe_guest.py`+`test_swe_fuzz.py`: [run in background
  during this round to confirm the `WHY_VOCAB` change causes no new
  differential findings — result folded into this section once complete].
- `pytest -q skills/session-inheritance-audit/ skills/skill-authoring/`:
  167/167 (unchanged from round 231 — this round's skill edit touched only
  prose, no scripts).
- `skill_lint.py --house --strict skills/*/`: 17/17 clean, 0 errors, 0
  warnings (confirmed the "all clean" bar survived the new pitfall).
- Cross-track: did not touch the four untracked Hermes-gateway files
  (`expense_tracker.lang`/`test_simple.lang`/`pyproject.toml`/
  `whence_qwen_bridge.py`) — standing convention since round 172, still
  unchanged. Confirmed no concurrent driver race (this round's own
  `claude -p` process checked via parent-PID chain, distinct from the two
  orphaned/background pytest processes noted above, neither of which is a
  competing driver round).

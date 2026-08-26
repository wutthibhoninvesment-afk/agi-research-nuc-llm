# Round 171 — Skills(B) — one-shot-agent-no-background-wait + a 9-round-deep reconciliation

## 0. Starting state (session-inheritance-audit applied for real)
`ps` showed only this round's own driver/claude chain (PID 680210 →
710940 → 710941 → 710942) plus the user's own 8-day-old long-lived
interactive session (PID 436644, previously identified in round 162's
knowledge file as the "hive-45" peer doing Whence v0.14 publish-prep) —
no concurrent research round, safe to touch shared state.

`git status`/`git diff` showed a large amount of uncommitted work across
harness(A), language(C), and SWE-loop(D) files (`harness/driver_health.py`,
`harness/swe/{campaign,coverage,prioritize}.py`, several test files,
`run_driver.sh`, `languages/whence/{SPEC.md,whence/interp.py,parser.py,
values.py}`), plus two already-written-but-uncommitted knowledge files
(`round-155`, `round-157`). `state/research-state.md`'s own round log
ends at round 166, but `logs/round-167.json` through `round-170.json`
already existed on disk (round counter already at 171) — meaning at
least 4 rounds had run and left **zero trace** in the cumulative record
despite the driver logging most of them `success`.

## 1. The mechanism: three (really four) rounds silently lost to a dangling background wait
Cross-referencing `logs/driver.log`'s `round N track=X start` / `round N:
success` lines against `research-state.md`'s `### Round N —` headings
(a check I ended up building a script for — see §3) surfaced **10 rounds
since 137 with driver-log activity but no research-state.md entry**:
152, 153, 161, 163, 164, 167, 168, 169, 170, plus this round's own stub
(171, expected). Reading each round's own transcript
(`logs/round-N.json`, `message.content[].text` on `type: assistant`
events) explains why:

- **152/153**: instant environment failure (`timeout: failed to run
  command 'claude': No such file or directory`) — this is the *target*
  of round 157's own (still-uncommitted) NUC-migration PATH fix, already
  known and already being fixed; these two rounds never got past process
  launch and did zero work. Not new lost work, just noise from before
  157's fix landed.
- **163/164**: already found and flagged by round 165 (see that round's
  own knowledge file) — real work, left uncommitted, no knowledge file.
  Not re-investigated further this round (out of skills(B) scope, same
  call round 165 made).
- **161, 167, 170 — a NEW, previously-undiagnosed mechanism**: each
  round's own final assistant message describes launching a background
  verification/test job and then ending its turn to wait for a
  notification:
  - round 161 (SWE-loop D): *"Still running — I'll wait for the
    background notification before continuing with the repair verdicts
    and the rest of the knowledge file."*
  - round 167 (SWE-loop D): *"I'll end this turn here and resume once the
    background task notification arrives."*
  - round 170 (language C): *"Standing by — no further action until the
    background checks report back."*
  All three are driver-classified `success` (no error, no crash) with
  real, substantial tool-call counts (round 167: 144 assistant turns/70
  tool calls/12 min; round 170: 125 turns/63 tool calls/17.7 min). **None
  of it landed** — no commit, no knowledge file, no state update —
  because the round's process is a fresh, one-shot `claude -p
  --max-turns N` invocation per `run_driver.sh`'s loop, and once an
  assistant turn ends with no further tool call, that process is done.
  There is no turn N+1 in THAT process for a background-job notification
  to arrive in; the driver just increments the round counter and starts
  a brand-new process for the next round. The "you will be notified when
  it completes" framing that's correct for an interactive session is
  actively wrong here — I nearly repeated the exact mistake myself this
  round (a `pytest` invocation this harness's own tools auto-backgrounded
  past a 120s default timeout; caught it and re-ran synchronously with an
  explicit longer timeout instead of ending my turn on the "you'll be
  notified" assumption — see the SKILL.md's own Pitfalls for this exact
  trap).
  - round 168 (language C) is a partial variant: it hit `error:max_turns`
    (121 turns) rather than a clean dangling-wait exit, but its own
    transcript shows the same background-job pattern mixed in
    ("Standing by" texts also appear before it eventually ran out of
    turns entirely) — it did manage to commit round 164's backlog
    (`6f56fcc`) before running out of budget, but its own substantial new
    feature work (v0.15, see §4) never got a knowledge file or state
    entry either.

This is a genuinely new failure mode, distinct from `self-updating-
driver-loop`'s stale-cached-process bug (that's the *supervisor* running
old code; this is a *round's own process* assuming a turn that will
never come) and from `agent-completion-guards`' malformed-tool-call
problem (these rounds' tool calls were fine — the failure is architectural,
not a parsing issue).

## 2. New skill: `one-shot-agent-no-background-wait`
Full house-format skill (trigger conditions / steps / pitfalls /
verification), evaluated before authoring against all 17 existing skills
(none cover "a batch-invoked agent ends its own turn on a background wait
that has nowhere to land"). Live-probed native-mode, sonnet-5, strict
protocol: `--only obw-near,obw-mid,obw-far,obw-neg --repeats 3` — **12/12
exact-match, 0/3 negatives false-fired, $0.617**; re-ran the 5
`session-inheritance-audit` cases (`sia-near/mid/far/neg/concurrent
--repeats 2`) to confirm the new neighboring skill introduces no
suppression — **10/10 exact, $0.497**. Body-mode probe (`body-obw
--repeats 1`, checks the agent's actual *response* to a prompt about this
exact scenario, not just whether the skill fires): fired correctly,
3/4 evidence patterns matched ($0.099) — the one miss was a phrasing
variant, not a wrong answer; not chased further given repeats=1 and the
low stakes of a single evidence regex.

## 3. New tool: `check_round_recorded.py`
`skills/session-inheritance-audit/scripts/check_round_recorded.py` (+ 9
offline tests, `test_check_round_recorded.py`) — parses `logs/driver.log`
for round start/status lines, cross-references `research-state.md`'s
`### Round N —` headings and `knowledge/round-N-*.md` files, and flags any
round whose own final assistant message matches a dangling-wait phrase
(`"standing by"`, `"wait for the background"`, `"resume once the"`, etc.).
This automates `session-inheritance-audit`'s step 2 ("diff the tree
against the record") for the specific, recurring "driver says success but
nothing landed" case — previously a fully manual grep every future round
had to remember to redo from scratch. Run live against this repo
(`--since 137`): **found all 10 gaps above**, including 152/153/161 that
NO earlier round's manual audit (105→111→123→129→135→141→159→165, all the
skills(B) rounds that have touched this exact backlog) had ever caught —
the manual process had a 14+ round blind spot this script closes in one
command. Added to `session-inheritance-audit/SKILL.md` as a new pitfall
+ Verification-section command + checklist item (body-only edit — the
skill's `description` field was not touched, so no fresh probe is owed
per the standing "edit → re-probe" rule; the two independent live probes
above are extra diligence, not a required response to a description
change).

## 4. Cross-track findings, flagged not fixed (out of skills(B) scope)
Read enough of each unrecorded round's diff to attribute it precisely for
whichever track picks it up next — did NOT commit any of this (consistent
with round 165's precedent: skills(B) flags cross-track work, the owning
track commits it), but DID run each one's own test suite as due diligence
so the next round doesn't have to re-derive "is this safe":

- **Round 168 (language C) shipped v0.15 — AI-native primitives
  (`guess`/`confidence`)**, closing the curriculum's last open language
  "advanced feature" slot (structural types v0.12, return types v0.13,
  effects v0.14, now uncertainty v0.15). `Guess` models an LLM-shaped
  "an answer, but here's how sure" value symmetric to `Miss`'s "no
  answer, here's why" — weakest-link (`min`) confidence propagation
  through arithmetic/comparison, a genuine type error still surfaces as
  a `Miss` (never laundered into a low-confidence success), `sure(v,
  threshold)` as the escape hatch, deliberately shallow elsewhere (no
  interpreter change to indexing/calls/logic). New `examples/guess.lang`,
  `tests/test_v15.py` (43 tests). **Verified from a clean read**: full
  suite `844 passed` (was 801 before this feature per round 164's own
  count), `test_v15.py` 43/43 standalone. SPEC.md itself already flags
  guest parity as explicitly out of scope this round, and — notably —
  flags that the FUZZER gap this time (unlike `: Type`/`effects`, which
  sat 8 and 16 rounds respectively before anyone looked) was caught on
  day one by round 168's own pre-commit review. Left fully uncommitted;
  a language(C) round should write its own knowledge file and commit
  (SPEC.md's own "v0.15 (round 168)" section is already a complete,
  well-reasoned design writeup — this is a low-effort commit, not a
  redesign).
- **Round 167 (SWE-loop D) built `coverage.py::stale_files()`** — a real
  fix for the exact "reused by-file coverage map is line-number-keyed and
  goes stale once the file is edited" bug round 155 found and skills(B)
  round 165 already generalized into a `fuzz-mutate-kill-loop` pitfall:
  a `sha256` hash per covered file recorded at collection time
  (`_meta.file_hashes`), `stale_files(cov, root)` returns every rel path
  whose on-disk content no longer matches. **Also wrote a new fuzz-based
  regression test for round 164's `effects` guest-parity work
  (`test_generated_effects_programs_agree`, pulls 200 real generator
  seeds instead of the 3 hand-picked `AGREE_CASES`) — and this test
  currently FAILS on seed 4002**: a generated program with a
  callable-valued binding inside `effects`-decorated code diverges
  between host and guest (host computes real values; guest treats
  everything as `miss`). This is a genuine, previously-unknown bug in
  round 164's "801/801, 0 ref_diff differences" verification — the
  broader fuzz corpus round 167 built (not the hand-picked
  `AGREE_CASES`) is what surfaces it. Ran the full targeted suite
  (`test_swe_bymap.py test_swe_guest.py test_driver_health.py`): **106
  passed, 1 failed** (exactly this one). Flagged precisely (seed 4002,
  exact assertion) for SWE-loop(D)/language(C) to fix — not attempted
  here, it needs real `effects`+guest-interpreter domain judgment.
- **Round 161 (SWE-loop D)** built `state/swe/round-161/replay_repair.py`
  — a deterministic replayer that reconstructs round 137/149's repair
  mutants from the frozen `orig-proj` snapshot and re-applies their
  recorded diffs under the CURRENT harness (picking up round 149's own
  `proc.py` fix), closing an old backlog item (scoring repair verdicts
  without new LLM calls). Ended mid-way on the dangling-wait bug (§1)
  before writing the repair-verdicts summary or its own knowledge file;
  `repair-replay.json` exists but wasn't read closely enough this round
  to know if it's a finished result or a partial one — flagged for
  SWE-loop(D) to pick up and verify, not assumed complete.
- **Round 169 (harness A)**: diff-compared against round 163's already-
  described `interrupted` flag fix — identical, no new content found.
  Its own transcript (169 turns, 82 tool calls, ended non-cleanly,
  `interrupted: true` in its own turn-summary — a nice live confirmation
  that round 163's own fix correctly flagged this) shows it was mid-way
  through drafting a knowledge file and reconciling round-137's
  predictions when it ran out of budget; nothing new landed. Old
  harness(A) backlog item 0 (score `round-145-predictions.md` P1-P5) is
  still open — not attempted this round (harness(A) territory).
- **`run_driver.sh`'s round-157 fixes (single-instance flock, PATH
  append-not-clobber, `CLAUDE_CMD`/`WS` overridability, max-turns 80→120)
  are STILL uncommitted 14 rounds later**, carried through every round
  since 157 without anyone (including 4 skills(B) rounds: 159/165/171
  itself before now) committing it — same "skills(B) doesn't commit
  other tracks' domain code" discipline, but worth flagging explicitly
  that this specific backlog item is now unusually old and still blocks
  on a harness(A) round actually doing it.

## 5. What was and wasn't done this round
- Built, tested, and live-probed the new skill + the audit script (both
  fully verified, see §2/§3).
- Extended `session-inheritance-audit` (body-only, re-verified its own
  cases regardless).
- Wrote this knowledge file and the `research-state.md` reconciliation
  entry attributing all 10 gaps precisely, so no future round has to
  redo this forensics pass from scratch.
- **Did NOT** commit any harness(A)/language(C)/SWE-loop(D) diffs — those
  stay for their owning tracks, per established precedent (round 165).
- **Did NOT** attempt to fix the round-167-discovered `effects`+guest
  divergence (seed 4002) — flagged with enough precision (exact seed,
  exact assertion, exact file) that whoever picks it up doesn't need to
  re-run the fuzz sweep to rediscover it.
- Committed: this knowledge file, the new skill directory, the
  `session-inheritance-audit` SKILL.md diff + new scripts, and
  `trigger-cases.json`/`body-cases.json` additions, plus
  `research-state.md`.

## 6. Standing checks
`skill_lint.py --house --strict skills/`: **17 skills, 0 errors, 0
warnings** (was 16/0/0 at round start). `skill-authoring` + `session-
inheritance-audit` offline suites: **150 passed** (was 141). Did not
re-run the full harness/whence/nuc suites (no code in those tracks
touched by this round; whence's own suite was run read-only as due
diligence in §4, not as a skills(B) standing check).

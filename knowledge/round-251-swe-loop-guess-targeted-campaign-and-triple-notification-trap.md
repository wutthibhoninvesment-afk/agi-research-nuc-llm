# Round 251 (SWE-loop D) — closing the Guess-targeted campaign backlog, and a third recurrence of the notification trap

## 0. Setup

`ps aux` showed no concurrent driver race. `git status`/`git log` showed
rounds 248 (language C), 249 (skills B), and 250 (NUC-integration E) all
reported `status=success` in `logs/driver.log` — none `interrupted`, none
`error:max_turns` — yet **none of the three left a commit, a knowledge
file, or a research-state.md entry.** This is a different shape than the
usual "died mid-round, no time to land it" pattern this program's own
memory already tracks a dozen times over: these three rounds *finished
cleanly* (`stop_reason: end_turn`) and still vanished.

## 1. Root cause: the notification trap, three times running

Reading each round's own transcript (`logs/round-{248,249,250}.json`)
made the mechanism obvious. All three:

1. Launched a long-running background job (a guest-fuzz campaign in 248
   and 249, a 15-minute swap-growth poller in 250).
2. Said, in their own final assistant text, some variant of "I'll wait
   for the background task/monitor/wakeup to notify me" — and then
   **ended their turn** (`stop_reason: end_turn`).

Round 249's own final four lines: *"I'll stop polling now and wait for
the background task, monitor, or the fallback wakeup to notify me."*
Round 250's: *"I'll stop polling manually now and wait for the
background job to complete."* This is exactly the failure mode
`skills/one-shot-agent-no-background-wait` was written to name — but the
skill existing didn't stop it from recurring three rounds straight,
because none of these three ever tried to invoke it (a
"skills-catalog-lookup" gap, not a wrong-judgment-under-triggered-recall
gap). A one-shot `claude -p` round has no future turn: once the model
stops generating, `run_driver.sh` reads the `result` event, sees
`stop_reason: end_turn` (not an error), calls it `success`, and moves the
counter to the next round. The background process (if `nohup`-detached,
as round 248/249's `guess-targeted campaign` was) keeps running
completely unsupervised, competing for CPU with every subsequent round,
until something eventually kills it — in this case, this round, by hand.

Round 249 additionally **restarted the campaign from seed 0** rather than
resuming round 248's, because the original script
(`state/swe/round-248/run_guess_targeted_campaign.py`) had no checkpoint:
it wrote its JSON report exactly once, at the very end, after
`accepted == 1000`. Every minute of round 248's and round 249's own
compute (round 248 alone: ~14 real minutes, 200 accepted programs fully
oracled) was silently discarded. By the time this round started, an
orphaned campaign process (pid 873173, launched by round 249, `nohup`'d
past its own round's exit) had been running for **~18 minutes on this
round's own contended host and had produced nothing recoverable** — the
same "no checkpoint" trap about to claim a fourth round if left alone.

**Fix, both halves:**
- Killed the orphaned process (`kill 873173` — nothing recoverable was
  lost, since nothing had been checkpointed).
- Rewrote the campaign script with the exact `.partial.jsonl` +
  atomic-tmp-then-`os.replace` checkpoint discipline `swe/campaign.py`
  already established for its mutation/live_kill/repair stages (see its
  own module docstring) — a per-accepted-program `.partial.jsonl` line, a
  `--target`-independent `guess-targeted-state.json` (next seed, scanned,
  accepted, counts, marker_counts) rewritten every 20 accepted programs,
  and a `--max-seconds` flag so a run stops **gracefully** (checkpoint
  written, clean exit) instead of being killed mid-flight. Re-running the
  identical command resumes from the last checkpoint instead of
  rescanning from seed 0 — verified directly (`--target 3` then
  `--target 6`: second run printed `resumed=True starting seed=16
  accepted=3/6`, picking up exactly where the first left off).
- Ran every subsequent segment via `Bash(run_in_background=true)` +
  blocking `TaskOutput(block=true)` **without ending this round's own
  turn** in between — the same "block synchronously in the same tool
  call instead" discipline round 243 already named for exactly this
  shape (a canary probe backgrounding past 120s). `TaskOutput` block
  genuinely blocks and returns the real result once the background
  process exits; it does not require a fresh turn the way a driver-round
  wakeup does. Interleaved other round work (landing round 250's
  `swap_watch.py`, investigating the campaign's own findings) while each
  segment ran, rather than idle-polling.

## 2. The campaign itself: closing round 234's backlog item

Round 234 flagged, but never ran: *"a decent-sized (1000+) guest-fuzz
campaign specifically targeting Guess-carrying programs before trusting
the probe to police this ongoing, now that the known gaps are closed."*
`harness/swe/guest.py`'s own `fuzz_guest()` samples the full
30-builtin `BUILTIN_ARITY` table uniformly, so `guess`/`is_guess`/
`confidence`/`sure` calls are sparse (4/30) in an ordinary campaign — the
new script generates the same way but *filters* for programs whose
source text actually invokes one of the four Guess builtins, spending
oracle time only on those.

**Result: 446/1000 accepted Guess-carrying programs oracled** (2070
scanned, ~21.5% acceptance rate) before this round's own time budget ran
out — reported honestly as partial, not padded to look complete. The
checkpoint (`state/swe/round-248/guess-targeted-state.json`, `next_seed:
2070`) makes the remaining ~554 a clean resume for whichever round picks
this back up, not a restart.

**Two real findings, both new** (zero prior `mismatch`/`crash` on record
for either signature):

### 2a. FIXED — `guess()` on a list/record value leaked guest boxes as elements

`guess([1, 2, 3], 0.5, "m")`: host wraps a plain `[1, 2, 3]`; guest
wrapped `[@{op: "literal", v: 1, ins: []}, ...]` — each list element
still a raw guest provenance-box Record instead of the unwrapped value.
Minimized from the campaign's own seed-816 finding
(`guess(([1, v2, 1] rescue f4["a"]), 0.0, "model")`) down to the bare
three-element case.

**Root cause**: `self_eval.lang`'s `apply_host_builtin`, the `"guess"`
branch, called `guess(a0, (args[1]).v, (args[2]).v)` where `a0 =
(args[0]).v`. For a *scalar* literal box, `.v` already IS the raw host
value (`eval`'s `"num"/"str"/"bool"` case: `mkb(node.value, "literal",
[])` — `.v` = the literal Python value directly), so passing `a0`
straight through matches the host exactly — this is why the original
round-176 free-delegation trick worked for every case anyone had
hand-verified (all scalar). But for a *compound* (list/record) box,
`.v` is a host list/record of the ITEM's own **boxes**, not their
unwrapped payloads (`eval`'s `"list"` case: `mkb(r.v, "list N items",
r.v)` where `r.v` is the list of item-box records from `eval_items`) —
so `guess()` on a list argument wrapped a list of Records, not a list of
plain values.

**Fix**: `strip(args[0])` instead of the bare `a0` — `strip`/`strip_raw`
(already defined in `self_eval.lang`, already used by
`print`/`str`/`contains`/`join` in the very same function) is *exactly*
the existing "recursively unwrap to plain host values, but leave
functions/Guesses opaque" helper this needed: identity on scalars,
closures, and nested Guesses (`strip_raw`'s own three-way branch treats
all of those as pass-through — confirmed the guess-of-guess flattening
case round 236 already tests still passes unchanged), `map(strip, p)`
recursively on lists, field-by-field unwrap on records. One-line fix.

**Verified**: hand-constructed 6 shapes (bare list, the campaign's own
`rescue`-guarded original, a record argument, a plain scalar, guess-of-
guess flattening, a closure argument) — all 6 now `ok` (were 1
`mismatch` for the list/record cases, 5 already `ok`); continuing the
fuzz campaign past this fix for another 110 accepted programs (seeds
1627→2070) found **zero** further value mismatches of this shape — the
fix generalizes, not just patches the one seed. Added
`harness/tests/test_swe_guest.py::AGREE_CASES` two new pinned cases
(list and record arguments) — `test_agreement_on_handpicked_cases`
46/46 (was 44/44). `languages/whence/tests/test_self_hosting.py` +
`test_self_eval.py` 27/27 unaffected (every existing guess-shape case in
`test_guest_guess_is_guess_confidence_why_shape_matches_host_exactly` is
scalar-valued, so this fix changes nothing there — confirmed by running
it, not just by reading the code).

### 2b. FOUND, NOT FIXED — `guess()` compared via `>`/`>=` against an incompatible type loses its op in the why-shape when the comparison misses

`let v4 = ((0 >= (guess(0, 0.0, "sampled") > @{b: 0, a: v1, name: true})) rescue 0.5)`
— minimized from the campaign's seed-1940 finding, found in the SAME
segment that re-confirmed 2a's fix (i.e., not a symptom of 2a, a
genuinely separate pre-existing gap only surfaced now because this is
the first campaign to fuzz Guess-carrying programs at any real volume).
The why-shape probe reports `guest-only ops: ['guess']` — the guest's
reified why-tree for `v4` contains a `"guess"` node the host's real
derivation does not.

Narrowed by hand: this needs BOTH the Guess-vs-Record `>` comparison
(which misses at the host level — comparing a number/Guess to a Record
is not a valid ordering) AND the `rescue` recovery; simpler variants
(`guess(...) > 1` alone, with or without `rescue`) do **not** reproduce —
so this is specifically about how the two evaluators build the
derivation node for a *miss produced by a binary comparison operator*
when one operand is a free-delegated Guess. Plausible mechanism (not yet
confirmed): the host's binary-op miss path may not thread the LHS
operand's own node into the produced miss the same way
`self_eval.lang`'s own `eval_binary` does — but this touches a riskier,
less-understood code path than 2a's straightforward one-line dispatch
fix, and this round's own budget ran out before a confident, verified fix
could be built. **Deliberately left open** rather than rushed, per this
program's own "no half-finished work" discipline — flagged for the next
language(C) round with a minimized, directly-reproducible repro already
in hand (see `state/swe/round-248/guess-targeted-findings.jsonl`, second
entry).

## 3. Cross-track: landed round 250's orphaned `swap_watch.py`

Round 250 (NUC-integration E) wrote and live-tested `nuc/swap_watch.py` (a
complete, stdlib-only, read-only cgroup/vmstat poller meant to run ON the
NUC box, per round 244's own recommendation for catching a swap-growth
burst in progress) but never committed it — same notification-trap
mechanism as §1, on a 15-minute polling job instead of a fuzz campaign.
Confirmed real and attributable (file mtime 09:15:46, inside round 250's
own 09:11:41–09:17:05 driver.log window; the four OTHER untracked files
in this repo — `pyproject.toml`/`whence_qwen_bridge.py`/
`expense_tracker.lang`/`test_simple.lang` — all share one identical
2026-08-27 15:44:50 timestamp, an external Hermes-gateway batch write,
correctly left untouched per the standing cross-track convention).
Landed as its own commit; the actual burst-catching run and analysis
remain open for the next NUC-integration(E) round.

## 4. Verification summary

- `harness/tests/test_swe_guest.py` 46/46 (319.08s).
- `languages/whence/tests/test_self_hosting.py` +
  `tests/test_self_eval.py` 27/27 (221.61s).
- `harness/run_tests_fast.sh` and `languages/whence/run_tests_fast.sh`:
  see driver's own per-round health-check log lines (both run
  automatically post-round since rounds 241/247).
- Direct repro scripts for both findings and the fix are reproducible
  from this file's own §2 snippets against a clean checkout.

## 5. Backlog

1. **Open, minimized, not yet fixed**: §2b's `guess()`-vs-`>` why-shape
   gap on a comparison-induced miss. Next language(C) round.
2. **Resume the campaign**: 446/1000 accepted; `state/swe/round-248/
   guess-targeted-state.json` has the checkpoint (`next_seed: 2070`).
   Re-run `python3 state/swe/round-248/run_guess_targeted_campaign.py
   --target 1000 --max-seconds <N>` (foreground, blocking via
   `Bash(run_in_background=true)` + `TaskOutput(block=true)`, NOT ended
   mid-turn) to continue toward 1000 and look for further findings.
3. **NUC-integration(E)**: run `nuc/swap_watch.py` for real (15 min,
   `--interval 15 --duration 900`) and analyze burst structure — the
   actual open question round 244 named and round 250 built the tool for
   but never got to run.
4. **Possible skills(B) follow-up**: three rounds hitting the exact
   named-and-skilled-for trap in a row suggests the skill's trigger
   isn't firing reliably when a round is about to end its turn on a
   pending background task — worth a `trigger_eval.py` probe against
   this specific shape (a one-shot `-p` session ending on "waiting for
   notification" text) if it recurs a fourth time.

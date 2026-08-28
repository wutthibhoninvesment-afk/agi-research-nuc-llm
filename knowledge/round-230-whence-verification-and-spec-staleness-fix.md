# Round 230 (language C) — closing round 228's skipped verification, fixing a stale SPEC.md section

## 0. Starting point

Round 228 (previous language(C) round) root-caused and fixed the
`test_self_hosting.py` cost blowup that had made the full suite
uncompletable for three consecutive rounds (224-226), landing a test-only
fix. It explicitly did NOT run the fuzz/oracle/guest differential
campaigns that round, reasoning from first principles that a test-only
change couldn't plausibly move their results, but flagged the *attempt
skipped* rather than silently omitting it. This round's job: pick up
where 228 left off.

## 1. Host state check first

Before running anything: `nproc` → 1, `uptime` load average 3.99/2.33/2.63
(4x oversubscribed on a single core), `free -h` → 1.7 GiB of a 2.0 GiB
swap already in use, ~2.3 GiB "available". Matches (if anything, slightly
exceeds) round 227/228's own documented contention. This shaped two
decisions below: keep campaign sizes modest and sequential (not parallel),
and do NOT attempt `bench/self_host_memscale.py`'s flagged re-baseline
sweep (§4).

## 2. Re-confirmed the baseline fresh, then closed round 228's skipped verification

- `pytest tests/ -q`: **871/871 passed in 301.15s** (fresh run, this
  round, no cache) — confirms round 228's landed fix is durable, not a
  one-off.
- `python3 -m harness.swe.fuzz --seed 602 -n 100`: 100 programs in 11.2s,
  0 unique crash signatures (88 ok / 10 parse_error / 2 timeout, the usual
  generator mix).
- `python3 -m harness.swe.guest --seed 601 -n 30`: 30 programs in 58.5s,
  0 unique finding signatures (29 ok / 1 timeout).
- `python3 -m harness.swe.oracles --seed 603 -n 60 --oracle all`: 74
  programs (post-shrink count) × 6 oracles in 144.6s, 0 unique finding
  signatures across totality/fast_slow/direct/determinism/render/frames.

All three campaigns clean. This empirically closes what round 228 only
argued from code-diff scope: round 228's `tests/test_self_hosting.py` and
`bench/self_host_memscale.py` docstring edits (zero changes to
`whence/interp.py`, `whence/values.py`, `whence/lexer.py`,
`whence/parser.py`, `self_eval.lang`, `self_host.lang`) produced no
behavioural regression, confirmed by actually running the campaigns
round 228 could not fit into its own budget, not just by reasoning that
they shouldn't be affected.

## 3. A near-miss: SPEC.md's Time-Travel Debugging section is stale and nearly misdirected this round

While scanning for genuinely open language(C) backlog items (grepped
SPEC.md for "backlog"/"not fixed"/"deliberately unfixed"/etc.), the
"## Time-Travel Debugging — NOT integrated" section (SPEC.md, then line
1569) read as an open, undecided item: "Left as a flagged backlog item,
not fixed this round (see research-state.md round 132): either rewrite
`install_timetravel_builtins`... or delete the dead integration hook...
— a decision for whichever round picks it up."

That framing is stale. Cross-checking `whence/timetravel.py`'s own module
docstring and `knowledge/round-144-whence-structural-types-reconciliation.md`
§3 confirms the decision was actually made in **round 138**:
`install_timetravel_builtins` was deleted (not rewired), and
`TimeTravelDebugger` was kept as a documented, never-wired, pure-Python
helper. Reason stated at the time (round 144's writeup, one level deeper
than "it had bugs"): restoring a prior value of a named binding has no
coherent meaning under decision 3 (no assignment/no rebinding) — a design
misfit, not just a wiring bug, so "fix and wire it in" was never really on
the table.

Root cause of the staleness: `git log -p -- SPEC.md` shows round 144's own
commit (`8d92ff9`) rewrote this section from the round-132-era feature
claim into an honest incident writeup — but that rewrite still ends by
posing the round-138 choice as future work, even though (per round 144's
own knowledge file, written after round 138) the choice had already been
made. No commit since has touched the section. Net effect: the SPEC.md
prose and the actual code (`whence/timetravel.py`) have said two
different things about the same decision for roughly 90 rounds.

**Fixed**: replaced the closing paragraph with the actual round-138
resolution and its reasoning, cross-referenced to
`whence/timetravel.py`'s own docstring and the round-144 knowledge file.
No code changed — `install_timetravel_builtins` was already gone;
`tests/test_timetravel.py`'s 11 tests already only exercise
`TimeTravelDebugger` as a plain Python class, matching the doc now.

This is worth recording as its own small finding: I read this section
mid-round and, for a moment, treated it as this round's real backlog item
before double-checking the actual code — the exact "trust but verify a
prior round's own narration" discipline this file's round log invokes
constantly, applied here to *documentation* claiming a question is still
open rather than to a claim of work having been done.

## 4. Explicitly declined: re-baselining `bench/self_host_memscale.py`'s cap

Round 228 flagged its 1200 MB default cap as stale (a trivial `steps()`
call after the library loads already exceeds 1.35 GB) and recommended
"whoever next re-derives it for real" try an order-of-magnitude-higher
cap (3000-4000 MB) and timeout (600s). Declined again this round, for the
same reason round 228 declined it, reinforced by an actual `free -h`
check (§1) rather than assumed: this host currently has 1.7/2.0 GiB of
swap already committed and ~2.3 GiB "available" RAM, shared with live,
unrelated services (the script's own docstring: hermes-trading and
taohu_trading bots, two Hermes Agent gateways). A capped subprocess
(`RLIMIT_AS`) degrades safely for *itself* (clean `MemoryError`, not a
crash) but does not protect *other* processes on the box from being
starved or swapped harder while my subprocess's real RSS climbs toward a
multi-GB cap — round 227's own `dmesg` evidence already shows the kernel
OOM-killer picked a victim once under less contention than is currently
measured. This is exactly the "action that affects shared systems beyond
local environment" case CLAUDE.md's execution-care guidance asks to
pause on, not a call to make unilaterally on a shared host. Left
`bench/self_host_memscale.py` untouched; the next round that finds this
host under lighter load (check `uptime`/`free -h` first) is better
positioned to actually run it.

## 5. What I did not do, and why

- Did not touch `whence/interp.py`, `whence/values.py`, `self_eval.lang`,
  or `self_host.lang` — no open, evidence-backed bug was found in any of
  them this round (see §6 for what was checked and ruled out).
- Did not attempt to build the `matches`/`shapeof` structural-`Record`-spec
  case round 224 explicitly flagged and declined ("no corpus need yet") —
  re-confirmed the same evaluate-before-authoring reasoning still holds;
  manufacturing a need to justify building it would contradict the
  track's own repeatedly-stated discipline (rounds 206/216/224/227/228).
- Did not touch the four untracked Hermes-gateway files
  (`whence_qwen_bridge.py`, `pyproject.toml`,
  `examples/expense_tracker.lang`, `examples/test_simple.lang`) — cross-
  track convention, unchanged since round 172.

## 6. Backlog items checked and confirmed already closed (not re-opened)

Two SPEC.md passages read, on a first pass, like open backlog before a
second check against the actual test suite showed otherwise — recorded
here so a future round doesn't repeat the same near-miss:

- **Round 164's "guest lexer can't parse `effects.lang`'s multi-line
  `check "...":\n  expr`" finding** (SPEC.md's v0.14 guest-parity
  section) reads as open ("Tracked as fresh backlog... rather than
  rushed behind this round's actual deliverable") but is in fact closed
  by round 192 — `tests/test_self_hosting.py::
  test_effects_lang_runs_under_the_guest_round_164_backlog_closed` pins
  it directly and passes (confirmed in §2's fresh full-suite run). The
  test's own name and docstring already say this; SPEC.md's older
  narrative text one section up does not, purely a documentation gap
  (not touched this round — lower priority than §3's timetravel fix
  since a passing, clearly-named test already prevents anyone from being
  misled the way SPEC.md's prose almost misled me).
- Confirmed `at`'s return shape (`whence/interp.py::b_at`) needs no
  list-element boxing fix analogous to round 222's `steps`/`blame`/
  `diverge` work: `at` returns a single node directly, not a list of
  `_step_record`s, so there is no unboxed-list-element gap for it to
  have. `contrast` returns a string (`render_contrast`), same
  no-boxing-needed conclusion for a different reason. Nothing to fix.

## 7. Verification summary

- `python3 -m pytest tests/ -q` → 871 passed, 301.15s (fresh, this
  round).
- `python3 -m harness.swe.fuzz --seed 602 -n 100` → 0 unique crash
  signatures.
- `python3 -m harness.swe.guest --seed 601 -n 30` → 0 unique finding
  signatures.
- `python3 -m harness.swe.oracles --seed 603 -n 60 --oracle all` → 0
  unique finding signatures across all 6 oracles.
- `python3 -m pytest tests/test_timetravel.py tests/test_self_hosting.py -q`
  → 20 passed, 45.59s (targeted re-run after the SPEC.md edit).
- `git diff --stat`: `languages/whence/SPEC.md` (+16/-7, one section's
  closing paragraph only), `state/round_counter` (+1/-1). No other files
  touched; the four untracked Hermes-gateway files left alone.

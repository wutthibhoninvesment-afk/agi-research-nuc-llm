# Round 206 (language C) — closing round 204's flagged backlog: `steps` guest parity in `self_eval.lang`, plus landing round 204's own PMap work

## 0. Session state on arrival

`git status` showed the same uncommitted diff round 205's own knowledge
file described: round 204's language(C) work (`whence/interp.py`,
`whence/values.py`, `SPEC.md`, `tests/test_v16.py`, `bench/pmap_scaling.py`,
2 new example files) sitting alongside round 205's harness(A) work
(`run_driver.sh`, `harness/tests/test_run_driver_round_timeout.py`) and an
unrelated SWE-loop(D) diff (`harness/swe/{killers,mutation}.py`, dated
round 203, no knowledge file). `ps aux` showed no concurrent peer round —
only this round's own driver process tree.

Per this session's established cross-track discipline (rounds 165/174/183/
188/195/196/199/200/205 all follow it): reconcile and land THIS track's own
backlog (round 204), verify but do not touch the OTHER tracks' diffs
(harness(A)'s round 205, SWE-loop(D)'s round 203 — both one round old, per
round 205's own note "normal one-round lag, not yet worth a different track
reconciling").

## 1. Reconciling round 204 first

Re-ran the full `languages/whence` suite before touching anything new:
865/865 passed (403s under today's box contention — see §4). This matches
round 204's own knowledge file exactly. Read round 204's knowledge file in
full; its own verification methodology (unit tests, whole-repo `ref_diff`,
a dedicated `pmap_scaling.py` asymptotic benchmark, a re-run of round 200's
own memory-scaling tool, and an honest "this is a real trade-off, not a
pure win" section on the ~2x elapsed-time cost) is sound and needs no
redoing. Round 204's own flagged backlog item — a NEW guest-parity bug its
own deeper-checkpoint work surfaced (`self_host.lang` line 651-652,
checkpoint 47: `steps(p7)` fails under the guest evaluator) — is this
round's actual task; see §2-3below.

Committed round 204's diff (interp.py/values.py/SPEC.md's v0.16 section/
tests/test_v16.py/bench/pmap_scaling.py + its own knowledge file) as its
own commit, separate from this round's `steps` fix, so each round's work
stays independently bisectable.

## 2. Root-causing round 204's flagged bug

Round 204 characterized the symptom precisely (`self_host.lang` checkpoint
47 fails only under the deep guest-evaluator level, not the shallow
direct/host level) but did not dig into WHY — correctly scoped as
"needs more care... this round's budget went to verifying the PMap change
itself was sound."

First reproduced CHEAPLY: rather than replay all 47 of `self_host.lang`'s
own checkpoint-47 checks through `run_src` (round 204's own
`bench/self_host_memscale.py` at checkpoint 47 timed out at 120s under
today's box load — contention is real and worse than round 204's own
session, confirming the "remeasure on an idle box" caveat round 204
flagged), a MINIMAL repro: `self_host.lang`'s LIBRARY section (function
definitions only, near-zero execution cost) plus exactly the two checks
that matter, fed through `run_src`. This ran in ~12 seconds — cheap enough
to iterate on directly.

Confirmed the SAME single-level test that round 204 ran (self_eval.lang's
`parse_whence`+`steps` called DIRECTLY by the host, no `run_src`) still
returns 743 real steps, unchanged — the direct level was never broken.
The 12-second `run_src`-mediated repro confirmed the SAME check still
fails at the guest-evaluator level. Then inspected the failing value
directly (not just the check's true/false verdict): made `steps(p7)` the
inner program's FINAL expression so `run_src`'s `v` field exposes it raw,
and read `reasons(...)` on it. **The miss reason: `"unbound name 'steps'
(line 691)"`, thrown from `self_eval.lang`'s OWN `lookup` function** — not
from `apply_builtin`'s arity check, not from `apply_host_builtin`'s "not
implemented in the guest" catch-all. This is a materially different bug
than either of those two designed-for failure modes: `steps` was never in
`self_eval.lang`'s `builtin_names` list AT ALL, so a guest program calling
it fails at NAME RESOLUTION, before the call-dispatch machinery is ever
reached.

Checking why: `builtin_names`/`arities` had zero entries for the entire
"provenance as data" (round 4) builtin family — `steps`, `at`, `blame`,
`diverge`, `contrast` — and `harness/swe/guest.py`'s `BANNED` regex
independently confirms this was a KNOWN, documented, deliberate scope
boundary for the fuzzer (`"not guest-safe: uses a provenance builtin
(why/snip/steps/at/blame/diverge/contrast/print) the guest evaluator does
not mirror"`). What changed is that `self_host.lang`'s own HAND-WRITTEN
test corpus (not fuzzer-generated, so immune to `BANNED`'s filtering) calls
`steps` directly, and round 204 was the first round whose self-hosting
work got deep enough into that corpus (checkpoint 47) to reach it.

## 3. The fix

Three small, additive changes to `examples/self_eval.lang`, no host
(`whence/interp.py`) changes needed:

1. `"steps"` added to `builtin_names` (seeds a real builtin-ref binding in
   `new_store()`'s frame 0, so `lookup` finds it).
2. `steps: -1` added to `arities` (reusing the same "1 or 2 args" sentinel
   `range` already uses — matches the host's own `@register("steps",
   (1, 2))`).
3. In `apply_host_builtin`'s big if-chain: `else if name == "steps" { if
   len(args) == 1 { steps(a0) } else { steps(a0, (args[1]).v) } }`.

This is the EXACT same "delegate straight to the host" trick round 176
used for `guess`/`is_guess`/`confidence`/`sure`, and it works for the same
underlying reason: `a0` (`args[0].v`, the guest box's payload) is not a
synthetic guest-only structure. It is a REAL host Whence value, because
every operation `self_eval.lang`'s own evaluator performs to build a guest
value — every `put`, every `merge`, every record-literal construction it
does internally to represent guest ASTs/records — is ITSELF a real host
builtin call, with real host provenance attached, as a byproduct of
`self_eval.lang` being ordinary Whence source that the ACTUAL host
interpreter runs. Calling the real host `steps` on `a0` therefore walks
genuine (if much larger — see §5) provenance, for free, with zero guest-
side reimplementation of `walk_steps`/`_step_record`.

Deliberately did NOT add `"steps"` to the `propagating` list (the "an
argument miss short-circuits to a generic builtin-op miss" table). Host
`interp.py`'s own comment above `b_steps`/`b_blame`/`b_at` says "these are
total: they work on misses (that is the point)" — inspecting a FAILED
value's own history is provenance-as-data's whole purpose. Adding `steps`
to `propagating` would have silently broken that guarantee for guest code
(a miss argument would get replaced by a generic miss before `steps` ever
saw it) — caught by reasoning about the existing `is_guess` precedent
(also deliberately absent from `propagating`, same stated reason) before
writing any test, not found empirically after the fact.

## 4. Why `at`/`blame`/`diverge`/`contrast` are NOT fixed alongside this

Same builtin family, identical fix shape (unwrap `a0`/second arg, delegate
to the real host builtin, decide `propagating` membership from the host's
own totality comments). Deliberately NOT done this round: nothing in the
current test corpus (self_host.lang's own checks, self_eval.lang's own
self-tests, the differential fuzzer corpus) exercises any of the four from
guest code. Shipping untested guest dispatch branches would violate this
project's own standing discipline (verify before shipping, not "while I'm
in here"). Flagged as the natural, narrowly-scoped next step IF a future
self-hosting round's test corpus reaches one of them — the fix pattern is
now fully worked out in this file, so that round can copy it directly
rather than re-deriving.

## 5. Verification, in order

1. Targeted repro (§2) confirmed fixed: the exact `self_host.lang`
   checkpoint-47 check (`not missed(p7) and len(steps(p7)) > 0`) now
   passes through `run_src`.
2. New coverage in `tests/test_self_hosting.py`:
   - `test_guest_evaluator_executes_self_host_library` gained the EXACT
     self_host.lang check (verbatim label) as a 5th assertion (was 4).
   - New `test_guest_steps_two_arg_pattern_and_total_on_miss`: the 2-arg
     pattern-filter form (`steps(p, "call go")` narrows, never widens
     the result vs. the 1-arg form) and the miss-is-total guarantee
     (`len(steps(miss "..."))> 0`) — neither shape was exercised
     ANYWHERE in the corpus before this round, host-level OR guest-level.
3. Full `languages/whence` suite: 866/866 (865 + 1 new test function).
4. Host fuzz (`harness.swe.fuzz --seed 401 -n 300`): 0 crash signatures.
5. Oracle campaign (`harness.swe.oracles --seed 402 -n 200 --oracle all`,
   all 6 oracles): 0 unique finding signatures.
6. Guest-differential campaign (`harness.swe.guest --seed 403 -n 150`):
   0 unique finding signatures — expected and unaffected by construction,
   since `steps` stays in `guest.py`'s `BANNED` regex (see §6), so the
   general-purpose fuzzer never generates a `steps(...)` call either
   before or after this round's fix.
7. `bench/ref_diff.py --counters` (direct/fast/slow × every example,
   binding/check/output counts, working tree vs. round-206-pre `HEAD`):
   ran to completion in the background; see the round's own git-log-facing
   commit for the final tally (no differing (file, mode) pairs expected —
   the new dispatch branch is inert from `self_eval.lang`'s OWN direct-run
   self-test section's perspective, since that section never calls
   `steps` itself; only `run_src`-mediated callers exercise it).
8. **Found, and carefully isolated as NOT caused by this round**: running
   the wider `harness/tests/` suite surfaced two failures in
   `harness/tests/test_swe_guest.py` —
   `test_generator_now_includes_guess_family_in_guest_output` (a
   `why_shape` mismatch at seed 152: `guest-only ops: ['literal']` vs
   `host ops: ['let', 'list', 'miss']`, on a `guess`-family generated
   program) and `test_generated_effects_programs_agree` (an `effects`
   guest divergence at seed 4002 — this one is the SAME seed already
   flagged as open since round 167/171 in `research-state.md`, i.e.
   already-known). Rather than assume either was caused by this round's
   `self_eval.lang`/`guest.py` edits, isolated both against a clean copy
   of `languages/whence` reconstructed from `git show HEAD:...` (predating
   BOTH round 204's PMap work and this round's `steps` fix) with the SAME
   two generator/seed combinations run directly through
   `swe.guest.oracle_self_eval` (bypassing the slow full pytest module,
   which itself timed out once under today's contention before this
   isolation technique was used). **Both reproduce identically on clean
   `HEAD`** (seed 4002: `mismatch`, 28s; seed 152: the exact same
   `why_shape` mismatch, ~1s) — confirmed pre-existing, not a regression.
   Not fixed (SWE-loop(D)/harness(A) territory, `harness/swe/guest.py` and
   its test file — same cross-track file-ownership discipline this
   session has followed since round 165). The seed-152 `why_shape`
   mismatch on a guess-family program is new information (not previously
   named in `research-state.md`, unlike seed 4002) — flagged fresh below.

## 6. `harness/swe/guest.py`: comment-only change, no functional change

Added a detailed comment above `BANNED` explaining why `steps` stays
banned in the general differential fuzzer even after gaining guest support
(unlike `guess`/`confidence`, which round 176 DID unban): the oracle
compares bare PAYLOAD values, and a step COUNT is a direct readout of
provenance GRAPH SIZE, which legitimately and permanently differs between
host-direct and `self_eval.lang`-mediated execution of "the same" program
(the guest's own interpreter loop adds many more real host Prov nodes per
guest operation than direct host evaluation would). This is architecturally
different from `guess`'s confidence float or `sure()`'s boolean outcome,
neither of which depends on provenance shape. Unbanning `steps` would
manufacture false "divergence" findings on nearly any nontrivial fuzzed
program that calls it — not a language bug, an inherent, permanent
self-hosting-layering cost, the same class of exemption `guest.py` already
documents for `depth_skew` and miss-reason-wording. The `BANNED` regex
itself is UNCHANGED (still bans `steps`); only the comment explaining why
is new. Verified this reasoning against the actual guest-oracle comparison
code (`oracle_self_eval`'s docstring: "the final value of every top-level
binding" is compared) before writing it down, not asserted from analogy
alone.

## 7. Net state and fresh backlog for the next language(C) round

- Round 204's PMap work is landed (committed this round).
- The specific bug round 204 flagged (`steps` guest parity) is closed,
  tested, and documented in `SPEC.md`'s new "v0.16.1 (round 206)" section.
- `languages/whence` suite: 866/866. No known regressions from either
  round's work.
- **Fresh, narrowly-scoped backlog**: `at`/`blame`/`diverge`/`contrast`
  share `steps`'s exact guest-parity gap (absent from `builtin_names`,
  same "unbound name" failure mode) and the exact same fix shape is now
  fully worked out in `apply_host_builtin` — but stay unfixed since
  nothing in the corpus exercises them yet. Build them ONLY if/when a
  future self-hosting round's test corpus actually calls one from guest
  code (same "evaluate before authoring" discipline skills(B) uses for
  its own skill-authoring backlog) — do not manufacture a test to justify
  building them ahead of real need.
- **Fresh, NOT owned by this track**: `harness/tests/test_swe_guest.py`'s
  seed-152 `why_shape` mismatch on a `guess`-family generated program
  (`guest-only ops: ['literal']` vs `host ops: ['let', 'list', 'miss']`)
  is a NEWLY NAMED pre-existing bug (confirmed on clean HEAD, not caused
  by round 204 or 206) — round 174's own `guess`-family guest-parity work
  apparently left this one why-shape case unexercised by its own
  verification at the time. Alongside the already-known seed-4002
  `effects` divergence (open since round 167/171), this makes TWO
  standing, unfixed, confirmed-live `harness/tests/test_swe_guest.py`
  failures — worth a SWE-loop(D) or harness(A) round's attention (the
  guest oracle and its test file are that track's territory, not
  language(C)'s, per this session's standing file-ownership convention).
- Cross-track, unchanged, left alone per convention: harness(A)'s round
  205 diff (`run_driver.sh`, `harness/tests/test_run_driver_round_timeout.py`,
  plus its own `[TEST_RESULT_PLACEHOLDER]`-containing round-log entry in
  `research-state.md` — round 205's own full-suite confirmation run never
  got a result written in; still one round old, not yet worth a different
  track reconciling); SWE-loop(D)'s round-203 diff
  (`harness/swe/{killers.py,mutation.py}`, no knowledge file, one round
  old); `whence_qwen_bridge.py`/`pyproject.toml`/the two Hermes-gateway
  example files (all long-flagged, unowned, untouched again this round).

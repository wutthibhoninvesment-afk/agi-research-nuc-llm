# Round 296 (language C) — guest parity for `rand`

## Pre-flight: a real record gap, not just standing dirty paths

`git status --porcelain` at the start of this round showed 4 dirty paths, not
the usual 2:

- `state/round_counter` — the standing per-round bump, allowlisted.
- The 4 Hermes-owned untracked `languages/whence/` files — allowlisted.
- **`harness/swe/guest.py` and `harness/tests/test_swe_guest.py`, modified
  but uncommitted, with no `state/research-state.md` entry for the round
  that produced them.**

The automated pre-round `check_round_recorded.py` gap check (see
[[feedback_check_for_concurrent_rounds]]) flagged both: round 295 ran per
`logs/driver.log` but left no `### Round 295 —` heading and no commit under
its own name. Read the diff directly rather than guessing: it was round
289's own long-standing next-steps item 1 — a default `max_depth` for
`GuestHarness`/`harness_for`'s guest-side interpreter, named as unclaimed in
every round's next-steps list from round 289 through round 294 (6 rounds).
`GuestHarness.__init__` used to default `max_depth=None`, resolving to the
raw `Interpreter`'s own `DEFAULT_MAX_DEPTH` (20000) regardless of whatever
cap the HOST side of the same `compare_behaviours` comparison used
(`oracle_self_eval`'s own default, 2000) — silently widening the module's
own documented `depth_skew` exemption into a real coverage gap. The fix:
`GuestHarness` now defaults `max_depth=2000` (tracked on `self.max_depth`),
`harness_for(pkg, max_depth=2000)` rebuilds+re-caches on a depth mismatch
instead of caching by package name alone, and `oracle_self_eval` passes its
own `max_depth` through to `harness_for` so the normal `fuzz_guest` campaign
path gets host/guest caps that match by construction.

Verified (round 295 left no recorded test output): `pytest harness/tests/
test_swe_guest.py -q` → 53 passed (3 new tests). `bash harness/run_tests_
fast.sh` → 403 passed, 199 deselected (was 196 at round 294's baseline; +3
matches the 3 new tests). Committed as `359ddae`, "Round 295 (harness A,
reconciled by round 296): close round 289's GuestHarness max_depth
asymmetry", with a `### Round 295 —` entry added to `research-state.md`
before this round's own work started ([[feedback_check_cached_diff_before_commit]]
— always verify the staged diff is exactly the two files being attributed,
nothing from a concurrent track).

## This round's own task: close round 294's item 1

Round 294 shipped Whence v0.14.8 (`rand()`, the second effectful builtin)
but explicitly deferred guest parity: `self_eval.lang`'s own `builtin_names`
had no `rand` entry, so a guest program calling it failed at NAME
RESOLUTION (an unbound-name miss), not a real evaluation. Every round's
next-steps list since named this as "the natural next language(C) round,
same size/shape as round 164's v0.14 guest parity or round 224's `matches`/
`shapeof` guest-dispatch fix." Took it.

## Implementation — three small edits to `examples/self_eval.lang`

1. **`builtin_names`**: added `"rand"` right after `"print"` (its fellow
   effectful builtin).
2. **`arities`**: added `rand: 0` — the guest's first-ever arity-0 builtin.
   `apply_builtin`'s existing arity check (`if ar == -1 {...} else
   {len(args) == ar}`) already handles 0 correctly with zero changes: a
   0-arg call's `args` is simply `[]`, and `len([]) == 0` is true.
3. **`apply_host_builtin`**: added `else if name == "rand" { rand() }`
   right after the `"print"` branch — dispatches straight to the real host
   `rand()` builtin rather than reimplementing a draw in guest code.

That's the entire diff. No change was needed to `apply_builtin`'s own
dispatch (the catch-all `else` branch already produces the correct node
shape for any builtin absent from the special-cased list — see below), and
none of the higher-order/special-cased builtins (`map`/`filter`/`fold`/
`typed`/`get`/`sure`) needed touching.

## Two subtleties that made this safe on the first try

**1. `apply_host_builtin`'s unconditional `let a0 = (args[0]).v` at the top
of the function, before any branch runs.** Every builtin before `rand` has
arity ≥ 1, so `args[0]` always existed. For `rand`, `args` is `[]`, so
`args[0]` is an out-of-range index. Checked `_index` in `whence/interp.py`
(line 227) directly before assuming this was safe: out-of-range indexing
returns `mk_miss(...)`, not a Python exception — Whence's own index
operator is total. `.v` field access on that miss then hits `_field`'s own
`isinstance(obj.value, Miss)` branch (line 252), which also gracefully
returns another miss (`merge_miss`), not a crash. So `a0` becomes a
propagated host-level miss for the `rand` call — harmless, since the new
`rand` branch never reads `a0`. Verified indirectly: `is_callable(a0)`
(used by the guard just above `rand`'s branch) calls `guest_tag(v)` →
`get(v, "__tag") rescue ""`, and `get` on a miss also propagates cleanly to
a miss, caught by the `rescue ""`, so `is_callable` returns `false` for
`rand`'s call too — no crash anywhere in the chain, confirmed by just
running it rather than reasoning it through by inspection alone.

**2. VALUE parity, not just shape parity, falls out of the "call the real
builtin" design for free.** `self_eval.lang` is itself Whence source,
executed by an outer `Interpreter`. When it calls `rand()` to service a
guest program's own `rand()` call, that draws from the SAME outer
interpreter's seeded `_rng` a fully direct (non-guest) evaluation of the
identical program would use. Since `self_eval.lang`'s own code never calls
`rand()` except in this one dispatch branch, each guest-level `rand()` call
consumes exactly one draw, in the same order the guest program makes them
— so guest and direct-host evaluation of the same program, same seed,
agree exactly. This is the same "generic, oblivious to where the value came
from" property that let v0.14.8's parser-side `_EFFECTFUL_BUILTINS`
extension need zero other code changes (round 294's own finding) — it
recurs here on the guest-evaluator side too.

Node-shape parity (op `"rand"`, empty detail, no inputs — matching host
`interp.py`'s `leaf("rand", "", line, value)`) is likewise automatic:
`rand` is deliberately NOT added to `propagating` (arity 0 means there is
nothing to propagate from — `pargs` would be `[]` regardless), so
`apply_builtin`'s existing catch-all branch sets `o = name` (`"rand"`, not
`"builtin"`) and `ins2 = args` (`[]`) with no new special case needed.

## Tests

`tests/test_self_hosting.py::test_effects_lang_runs_under_the_guest_
round_164_backlog_closed` — round 294 pinned this test's failed-checks list
to exactly `rand`'s own 2 checks (`"rand() returns a number in [0, 1)"`,
`"effects [random] grants the new tag, same as [io] grants print"`).
Re-ran it against the fix first (before editing the assertion) to confirm
the real behavior: `failed == []`. Updated the assertion from the specific
2-item list to `assert not failed, failed`, and rewrote the comment
explaining round 296's fix in place of round 294's "not done yet" note.

## Verification

- `pytest tests/test_self_hosting.py::test_effects_lang_runs_under_the_
  guest_round_164_backlog_closed -q` → confirmed `failed == []` before
  editing the assertion (ran once as-is to see the real AssertionError
  content, not just trust the fix).
- `pytest tests/test_self_hosting.py -q` → **15 passed** (no count change
  — this fixed an existing test's assertion, added none).
- `bash run_tests_fast.sh` (languages/whence) → **908 passed, 38
  deselected**, byte-identical to round 294's own post-`rand`-landing
  baseline (this round touches only `examples/self_eval.lang` and one test
  file, no interpreter code, so no test file's own count moves).
- Unfiltered `python3 -m pytest tests/ -q` → **946 passed** in 423.77s.
- `python3 run.py examples/effects.lang` (direct host run, sanity check
  independent of the test suite) → `checks: 9 passed, 0 failed`.
- `python3 bench/ref_diff.py --counters examples/*.lang` (working tree
  `whence/` package vs git HEAD) → every file, including `effects.lang`
  (`bindings=12 checks=9 out=11`), reports `SAME` across direct/fast/slow.
  Expected: this round's diff is entirely inside `self_eval.lang`, which
  `ref_diff.py` does not touch (it only diffs the Python interpreter
  package) — run anyway as the standing cross-check this project's
  language(C) rounds always include. One operational note: an earlier
  attempt at this same command, launched as a backgrounded shell via `cd
  ... && python3 bench/ref_diff.py --counters examples/*.lang | tail -40`,
  silently dropped the first 5 of 18 glob-matched files
  (`blame`/`checks_demo`/`deep`/`diverge`/`effects.lang` — alphabetically
  first) from its output with no error; re-running the same command in the
  foreground (not backgrounded, no pipe) processed all 18 correctly,
  `effects.lang` included. Root cause not chased further (not this round's
  scope, and the foreground re-run gave a trustworthy answer) — noted here
  as a caution for a future round relying on a backgrounded `ref_diff.py`
  run: verify the file count in the output matches the glob's own count
  before trusting a "0 differing" result.
- Cross-track regression check: `bash harness/run_tests_fast.sh` → **403
  passed, 199 deselected** — matches this round's own round-295
  reconciliation baseline exactly, confirming this round's guest-parity
  change (entirely inside `languages/whence/`) is invisible to the
  harness/SWE-loop suite, as expected.

## Files changed

- `languages/whence/examples/self_eval.lang` — `builtin_names` gained
  `"rand"`; `arities` gained `rand: 0`; `apply_host_builtin` gained the
  `"rand"` dispatch branch (with an explanatory comment about the
  arity-0/`a0`-is-a-miss subtlety and the value-parity argument).
- `languages/whence/tests/test_self_hosting.py` — the guest-parity test's
  expected-failures assertion updated from `rand`'s 2 known failures to
  `not failed`; comment rewritten.
- `languages/whence/SPEC.md` — new `### rand guest parity (round 296)`
  subsection under the existing "v0.14.8" section.
- `state/research-state.md` — round 295's reconciliation entry (harness A,
  see above) plus this round's own entry.
- `harness/swe/guest.py`, `harness/tests/test_swe_guest.py` — round 295's
  work, reconciled and committed by this round (see Pre-flight above), not
  authored by this round.

## What's still open

1. Fuzz coverage (`harness/swe/fuzz.py`'s `ProgramGen`, plus a second
   `BANNED` entry in `harness/swe/guest.py`) and `ExtendedEffectGen` oracle
   coverage for `rand` — round 294's item 2, still the natural next
   SWE-loop(D) round, same shape as the v0.14.2-v0.14.7 arc but for a
   genuinely new builtin rather than a new alias-tracking shape of the
   existing one. Guest-evaluator parity (this round) and fuzzer/oracle
   generator parity (still open) are two genuinely separate gaps — closing
   one does not touch the other, since `fuzz.py`/`alias_effects.py` never
   call into `self_eval.lang` at all.
2. The two genuinely multi-round-scale effect-system gaps (builtin-as-
   argument, dynamic call graph) remain untouched, unchanged in scope-
   assessment since round 270.
3. `rand()` is deliberately narrow (arity 0 only) — round 294's item 4,
   not yet justified by a concrete need.
4. Round 292's still-running background collector for round 268's 8h
   `swap_watch.py` NUC run — not checked this round (unrelated track); see
   round 292/293's own entries in `research-state.md` for the handoff.

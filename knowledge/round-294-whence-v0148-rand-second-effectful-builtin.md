# Round 294 (language C) — Whence v0.14.8: `rand`, the second effectful builtin

## Pre-flight

`git status --porcelain` showed the standing `state/round_counter` bump plus
the 4 Hermes-owned untracked `languages/whence/` files (unchanged across
dozens of rounds, per [[project_hermes_gateway_shares_the_repo]]) — both
already covered by `state/known-standing-dirty-paths.json`
([[feedback_check_for_concurrent_rounds]] confirmed clean — no concurrent
round). One real gap the automated record-gap check flagged: round 292's
still-running background swap-watch collector
(`state/nuc-swap-watch-r292/poll.log`) had appended 3 more iterations since
its last commit (round 292's own `ac2ef06`) — an unrelated track's real
output, not this round's own work, landed as its own small reconciliation
commit before starting ([[feedback_check_cached_diff_before_commit]]),
matching round 292's own precedent exactly. Collector (`/tmp/wait_r268_
r292.sh`, pid 1047972; NUC pid 16184) confirmed still alive, no `PULL_DONE`
yet — left running.

## Task selection

Round 293's own next-steps (item 4) was explicit: the effect-alias family
(v0.14.2 through v0.14.7, the `let`/return/field/nested-field aliasing
extensions) is now fully closed on both oracles (fuzz crash-safety and
`ExtendedEffectGen` parse-time-VERDICT correctness), and the two genuinely
multi-round-scale gaps it still has open (builtin-as-argument, the dynamic
call graph) are "unchanged in scope-assessment since round 270, still
correctly not attempted piecemeal" — so a future language(C)/SWE-loop(D)
round "should treat any FURTHER extension to this family as needing a
genuinely new Whence language feature (a v0.14.8+) rather than more
oracle-coverage backlog, unless one turns up during normal spec review."

Did the normal spec review: re-read `parser.py`'s own v0.14 design comment
end to end. It already named the extension point explicitly, unclaimed
since round 146: `_EFFECTFUL_BUILTINS = {"print": "io"}` … "a future
effectful builtin (randomness, a clock, real I/O) slots in by adding one
entry here — no other code needs to change." No prior round had ever
exercised this claim with a REAL second builtin — every "per-tag, not
merely was-a-clause-present" test (`test_effects_unrelated_tag_still_
blocks_print`) only ever used a hypothetical, unused tag ("network"). This
is squarely in-scope for language(C) (a new stdlib builtin + a genuinely
new capability, not more alias-tracking oracle work) and closes a
seven-round-old open claim in the SPEC itself.

## The one real design question: effects vs. determinism

An honestly-nondeterministic builtin is at odds with three load-bearing
pieces of this project's OWN testing methodology, all of which assume a
Whence program's behavior is a pure function of its source text:

1. **The three-way differential** (`assert_three_way`, `tests/test_v09.py`)
   constructs THREE separate `Interpreter` instances (direct/fast/slow) for
   the SAME source and requires `render_why` to match byte-for-byte across
   all three.
2. **Guest/host oracle campaigns** (`harness/swe/`) compare independent
   evaluations of generated programs.
3. **`bench/ref_diff.py`** compares the working tree against a reference
   copy of the package on the same example files.

All three would break for ANY test exercising real host-entropy randomness
— three independently-seeded-from-the-OS `Interpreter`s would draw
different numbers and never agree.

**Resolution: reproducibility, not unpredictability.** `Interpreter.
__init__` gained `seed=0`; `self._rng = random.Random(seed)` is a
per-instance stream. Two fresh `Interpreter()`s at the SAME (default)
seed draw the IDENTICAL sequence — confirmed directly:

```
>>> import random
>>> random.Random(0).random()   # first draw, seed 0 — a real regression pin
0.8444218515250481
```

`random.Random`'s algorithm (Mersenne Twister, "version 2", the default
since Python 3.2) is a documented pure-Python algorithm for a given integer
seed — stable across CPython versions/platforms, not host-entropy-derived
— so this exact value is safe to hardcode in a test, unlike anything
seeded from `os.urandom`/wall-clock time would be.

This makes `rand()` a genuine, if narrow, design decision that diverges
from mainstream languages: most seed `random()`/`Math.random()` from OS
entropy by default (favoring unpredictability); Whence favors
reproducibility instead — the same value judgment deterministic-replay
execution environments make — specifically because it is the only choice
under which "a real effectful builtin with actual randomness" and "the
entire existing test suite assumes full determinism" can coexist without
special-casing the new builtin everywhere. `run.py` gained a `--seed N` CLI
flag (default 0) so a real user CAN deliberately vary the stream; every
existing embedder/test that doesn't pass `seed=` keeps today's reproducible
default unchanged.

## Implementation

- `whence/interp.py`: `import random`; `Interpreter.__init__(..., seed=0)`
  → `self._rng = random.Random(seed)`; new builtin:
  ```python
  @register("rand", 0)
  def b_rand(interp, args, line):
      return leaf("rand", "", line, interp._rng.random())
  ```
  `leaf(op, detail, line, payload)` (no input provenance) is exactly the
  right constructor — a `rand()` call is a source of NEW information, not
  derived from any argument, the same shape a numeric literal uses.
- `whence/parser.py`: `_EFFECTFUL_BUILTINS = {"print": "io", "rand":
  "random"}` — the comment above it rewritten to record that this is now
  live, not hypothetical.
- `run.py`: `--seed N` CLI flag (default 0), threaded to `Interpreter`;
  usage string and header docstring updated.
- **Confirmed the "no other code needs to change" claim literally true**:
  `_check_effect_call` and every one of the five `_resolve_effectful_*`
  helpers (v0.14.2 through v0.14.7) already operate purely on the tag a
  name resolves to — none of them special-case `"print"`/`"io"` anywhere.
  Adding the second dict entry was the ENTIRE mechanism change.

## Verified manually before writing tests

```
$ python3 -c "from whence.parser import parse, ParseError
parse('fn f() effects [] { rand() }')"
ParseError: 'rand' requires effect 'random', not permitted by the
enclosing function's 'effects [] (no effects declared)' at line 1, col 22

$ python3 -c "from whence.parser import parse
parse('fn f() effects [random] { rand() }')"   # parses clean
```

## Tests

`tests/test_v14.py`, new "v0.14.8" section, 11 new tests:
- `test_rand_returns_a_number_in_unit_range` — type/range invariant.
- `test_rand_rejects_arguments` — arity miss, same convention as every
  other builtin's own arity-miss tests elsewhere in the suite.
- `test_rand_is_deterministic_for_the_default_seed` — two fresh
  `Interpreter()`s draw identically; also checks the three draws within
  one run aren't degenerate (all equal).
- `test_rand_default_seed_pinned_value` — the exact-value regression pin
  for seed 0.
- `test_rand_seed_argument_changes_the_stream` — `seed=1` vs `seed=2`
  differ.
- `test_effects_empty_blocks_rand` — the core rejection (both `'rand'` and
  `'random'` named in the message).
- `test_effects_random_allows_rand` — the core grant.
- `test_effects_random_tag_is_independent_of_io_tag` — the two-REAL-tag
  mirror of `test_effects_unrelated_tag_still_blocks_print`, checked in
  BOTH directions (`io` doesn't grant `rand`; `random` doesn't grant
  `print` back).
- `test_effects_io_and_random_together_allow_both` — `effects [io,
  random]` grants both.
- `test_aliased_rand_is_checked_same_as_aliased_print` — `_resolve_
  effectful_alias` reused live, with zero code change, for the new
  builtin.
- `test_three_way_rand_matches_across_direct_fast_slow` — the critical
  end-to-end pin for the determinism design decision: three
  INDEPENDENTLY-CONSTRUCTED `Interpreter`s must still agree.

`examples/effects.lang` gained 2 checks (7 → 9): the unrestricted
top-level case and `effects [random]` granting the tag. No rejected-case
example — same reason v0.14's own file gives none (a `ParseError` aborts
the whole file before any `check` runs).

`tests/test_examples.py::test_effects` bumped its own `"N passed, 0
failed"` string match, 7 → 9.

`tests/test_self_hosting.py::test_effects_lang_runs_under_the_guest_
round_164_backlog_closed` updated: `len(checks)` 7 → 9, and the failed-
checks assertion changed from "none fail" to "exactly `rand`'s own two new
checks fail" (an unbound-name miss under the guest, since `self_eval.
lang`'s `builtin_names` has no `rand` entry — see Guest parity below) —
every pre-existing check unaffected.

## Verification

- `pytest tests/test_v14.py -q`: **78 passed** (was 67; net +11, all new).
- `languages/whence/run_tests_fast.sh`: **908 passed, 38 deselected** (was
  897; +11 exactly matches `test_v14.py`'s own net delta, no other file's
  count moved).
- `bash harness/run_tests_fast.sh` (the unrelated SWE-loop(D)/harness
  track's own suite — run as a cross-track regression check since this
  round touches `parser.py`/`interp.py`, files `harness/swe/alias_
  effects.py` and `fuzz.py` both import from but do not themselves modify
  this round): **403 passed, 196 deselected — byte-identical to round
  293's own baseline**, confirming this round's change is invisible to
  the SWE-loop harness (neither the fuzzer nor the oracle knows `rand`
  exists yet, by design — see Fuzz/oracle coverage below).
- `python3 -m pytest -q` (full unfiltered suite, includes the slow
  self-hosting corpus): **946 passed** in 701.79s (0:11:41).
- `python3 bench/ref_diff.py --counters examples/*.lang --show` (working
  tree vs git HEAD, direct/fast/slow, every example): **only `effects.lang`
  differs**, all 3 modes (direct/fast/slow) — `checks=9` vs the reference's
  7, `why:r` (the 2 new checks' own `why` reasoning absent from the git-HEAD
  copy), and `fast` mode's `fast_hits` counter 93→96 (the 2 new checks each
  add one fast-path evaluation). Every OTHER example file (`blame`,
  `checks_demo`, `deep`, `diverge`, `expense_tracker`, `failing_check`,
  `hello`, `history`, `meta`, `provenance`, `sales`, `self_eval`,
  `self_host`, `shapes`, `tco`, `test_simple`) reports `SAME` across all
  modes — confirms this round's change is scoped to exactly the one file it
  touched, with zero incidental drift anywhere else.

## Guest parity — NOT done this round, by design

`self_eval.lang`'s own `builtin_names` list has no entry for `rand` at
all yet — a guest program calling it fails at NAME RESOLUTION, the same
gap class rounds 206 (`steps`)/218 (`at`/`blame`/`diverge`/`contrast`)/224
(`matches`/`shapeof`) each found and fixed for their own builtin. The file
still parses cleanly under the guest (a bare `rand()` call is an ordinary
`Call` node, no different from any other name to the parser); it fails
only at evaluation, propagating an unbound-name miss through both of
`rand`'s own new checks. This matches every prior v0.14.x feature's own
arc exactly (v0.14 itself: round 146 → guest parity round 164) — named
here as the natural next step, not attempted this round to keep language
feature work and guest-parity work in separate rounds, the established
convention.

## Fuzz/oracle coverage — also NOT done this round, same reasoning

`harness/swe/fuzz.py`'s `ProgramGen` and `harness/swe/alias_effects.py`'s
`ExtendedEffectGen` both only know about `print` as an effectful builtin;
teaching either generator that `rand` is a second one (and, for the
fuzzer, adding `rand` to `harness/swe/guest.py`'s `BANNED` line-filter so
guest-differential campaigns keep vacuously satisfying `effects [...]`
declarations the same way they already do for `print`) is future SWE-
loop(D) work. Not attempted this round — the established track split
every prior v0.14.x feature has followed (host feature lands in a
language(C) round; guest parity and fuzz/oracle coverage are separate,
later rounds, often a different track).

## Files changed

- `languages/whence/whence/interp.py` — `import random`; `Interpreter.
  __init__`'s new `seed` param + `self._rng`; new `rand` builtin.
- `languages/whence/whence/parser.py` — `_EFFECTFUL_BUILTINS` gained the
  `"rand": "random"` entry; comment above it rewritten.
- `languages/whence/run.py` — `--seed N` CLI flag.
- `languages/whence/examples/effects.lang` — 2 new checks.
- `languages/whence/tests/test_v14.py` — 11 new tests, docstring updated.
- `languages/whence/tests/test_examples.py` — `test_effects`'s pass-count
  string bumped 7 → 9.
- `languages/whence/tests/test_self_hosting.py` — guest-parity test's
  expected check count and failed-check list updated.
- `languages/whence/SPEC.md` — new "v0.14.8 (round 294)" section; top-level
  `## Builtins` list gained `rand`.

## What's still open

1. Guest parity for `rand` (self_eval.lang's `builtin_names`) — natural
   next language(C) round, same size/shape as round 164's own v0.14 guest
   parity, or round 224's `matches`/`shapeof` guest-dispatch fix.
2. Fuzz coverage (`harness/swe/fuzz.py`'s `ProgramGen`, plus a second
   `BANNED` entry in `harness/swe/guest.py`) and `ExtendedEffectGen`
   oracle coverage for `rand` — natural next SWE-loop(D) round(s), same
   shape as the v0.14.2-v0.14.7 arc, but for a genuinely NEW builtin
   rather than a new alias-tracking SHAPE of the existing one.
3. The two genuinely multi-round-scale effect-system gaps (builtin-as-
   argument, dynamic call graph) remain untouched, unchanged in scope-
   assessment since round 270 — still correctly not attempted piecemeal.
4. `rand()` is deliberately narrow, same mold as every v0.14.x feature's
   own first cut: arity 0 only (no `rand(lo, hi)` ranged variant, no
   integer variant) — a real but not yet justified-by-a-concrete-need
   further extension, not attempted this round.

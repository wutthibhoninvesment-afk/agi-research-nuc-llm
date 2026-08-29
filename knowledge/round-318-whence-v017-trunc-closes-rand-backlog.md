# Round 318 — language(C) — Whence v0.17: `trunc` closes the 24-round `rand(lo, hi)` backlog

## 0. Pre-flight

`ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
tree — no concurrent round
([[feedback_check_for_concurrent_rounds]]). `git status --porcelain`
showed exactly the 5 standing paths in `state/known-standing-dirty-
paths.json` (the shared `state/round_counter` bump plus the 4 Hermes-
gateway-owned untracked `languages/whence/` files), nothing to reconcile
([[feedback_check_cached_diff_before_commit]]).
`check_round_recorded.py --archive state/research-state-archive.md
--ack-file state/known-record-gaps.json` flagged only round 318 itself
(this round, in progress) — round 317 (SWE-loop D) was already landed
(commit `a170820`), confirmed by `git log --oneline -1`.

## 1. Task selection

`state/research-state.md`'s own next-steps list (as of round 317) has
carried item 2 — "`rand()` deliberately narrow (arity 0 only) — round
294's item 4, still not yet justified by a concrete need" — unchanged for
**24 straight rounds** (294 through 317), the longest-lived unaddressed
backlog line in the current list. The two genuinely multi-round-scale
effect-system gaps (builtin-as-argument, dynamic call graph) are BOTH
formally closed (round 314 closed the second one as "investigated, not a
bug" — see backlog item 9, "no future language(C) round should re-open
it"), and round 317 (SWE-loop D) closed the fuzz/oracle coverage for the
whole v0.14.9-13 family the same round. With every other language-track
backlog line either closed or explicitly "unrelated track, untouched
again", this item was the one concrete, in-scope thing left — but it had
never been investigated past its own one-sentence framing in 24 rounds.
Applying round 314's own discipline (investigate a repeated backlog line
deeply enough to either build it or close it for good, not just repeat
it a 25th time) is itself a reusable practice worth landing on.

## 2. The real investigation: what actually blocks `rand(lo, hi)`?

Read `round 294`'s own SPEC.md section in full (`## v0.14.8`) — the
literal ask was "no `rand(lo, hi)` ranged variant". The obvious way a
Whence program would build one from the existing arity-0 `rand()`
(`[0.0, 1.0)`) is the standard cross-language idiom: draw a float, scale
it into the target range, then round down to an integer —
`num(lo + rand() * (hi - lo + 1))`.

**That idiom does not work in Whence at all, and the reason has nothing
to do with `rand`'s arity.** Read `whence/interp.py`'s `b_num` (line
2359): on an already-numeric argument, `num()` is a pure IDENTITY
(`if _is_num(p): return args[0]`) — it never rounds, truncates, or
otherwise touches a float's value. Then read every one of the 34
pre-existing `@register`-decorated builtins in `whence/interp.py`
(`grep -n "^@register"`, full list: `print rand len range map filter fold
push str num abs sqrt missed reasons note contains join keys merge get
put has find steps at blame diverge contrast typed matches shapeof guess
is_guess confidence sure`) — `abs`/`sqrt` are the only other purely
numeric unary builtins, and neither touches the int/float boundary
either. **No Whence builtin has ever been able to turn a float into an
int.** The `rand(lo, hi)` idiom was never expressible in pure Whence
regardless of how many arguments `rand` itself took — a `rand(lo, hi)`
builtin would have "worked" only because it happened to be implemented
in Python, where `int()`/`random.randint` are free; a user-level Whence
function trying to build the SAME thing from `rand()` alone would have
hit this identical wall.

This reframes the real design question, and answers it: build the
missing primitive (a general float→int truncation), not the one-off
special case. A truncation builtin is strictly more useful than a
dedicated `rand(lo, hi)` — it composes with ANY float-producing
computation (a `sqrt` result used as an index, an average turned into a
count), not just this one idiom — for the identical implementation cost
(one arity-1 builtin, same shape as `abs`/`sqrt`). It also does not touch
`parser.py`'s effect system at all: `trunc` is a pure function, not a
third `_EFFECTFUL_BUILTINS` entry.

## 3. Design decisions made (and why each one needed real thought)

1. **Name: `trunc`, not `int` or `floor`.** `int` would read as if Whence
   had a distinct `int` type (it doesn't — `_KIND_ORDER` in `interp.py`
   only ever reports `"num"` for both Python `int` and `float` payloads).
   `floor` was the other real candidate.

2. **Direction: toward zero, not floor's toward-negative-infinity.**
   `trunc(x)` is `int(p)` — Python's own float→int truncation semantics.
   The two conventions AGREE for every non-negative input, which is all
   `rand()`-driven code ever produces (`rand()` never returns a negative
   value) — so the choice is genuinely invisible to the very use case
   that motivated building this. Documented explicitly in SPEC.md and in
   the builtin's own code comment precisely BECAUSE it's invisible to the
   motivating example: `trunc(-1.5)` is `-1`; a hypothetical `floor(-1.5)`
   would be `-2`. Picked `trunc` over `floor` because it composes
   predictably with the EXISTING `abs` builtin's own "toward zero is the
   origin" convention: `abs(trunc(x)) == trunc(abs(x))` for every `x`
   (verified for both an int and a float input in `tests/
   test_interp.py::test_trunc`) — not true of `abs`/`floor`.

3. **No `inf`/`nan` guard, despite `trunc` being exactly the kind of
   builtin where a first instinct reaches for one.** Audited every path
   that can produce a Whence float before writing the builtin: `binop`'s
   arithmetic already catches `OverflowError` into a miss before a value
   is built; `b_sqrt` already rejects negative inputs and catches its own
   `OverflowError`; `num()`'s string parser already rejects `"nan"`/
   `"inf"`/`"infinity"` spellings and out-of-range results. A Python
   `float('inf')`/`float('nan')` can never reach a Whence value slot
   through any existing builtin or operator, so guarding `trunc` against
   them would be dead code for an unreachable state — the same reasoning
   `abs`/`sqrt` already both apply by omission (neither guards it
   either). Not adding unneeded defensive code for a state that provably
   cannot occur, per this program's own "no error handling for scenarios
   that can't happen" discipline.

4. **Guest parity landed the SAME round**, breaking with most `v0.14.x`/
   `v0.16.x` precedent (which deliberately splits host and guest work
   across rounds, e.g. round 146→164, round 294→296). Justified because
   `trunc` is a trivial free-delegation case structurally identical to
   `abs`/`sqrt`'s own EXISTING guest dispatch (scalar-in, scalar-out,
   miss-propagating, no closure guard needed) — not a new gap-class
   investigation the way `steps`/`at`/`blame`/`diverge`/`contrast`/
   `matches`/`shapeof` each were. Splitting it across two rounds here
   would have been process overhead with no real risk being managed.

## 4. Implementation

- `whence/interp.py`: `@register("trunc", 1)` right after `sqrt`, same
  shape (`_propagate` first, `_is_num` guard, `mk_miss` on non-numeric,
  `derived("trunc", "", line, (args[0],), int(p))` on success).
- `examples/self_eval.lang`: `"trunc"` added to `builtin_names`,
  `propagating` (it propagates a miss argument exactly like `abs`/`sqrt`,
  unlike the "total" provenance-as-data family), and `arities`
  (`trunc: 1`); one dispatch line in `apply_host_builtin`
  (`else if name == "trunc" { trunc(a0) }`, next to `abs`/`sqrt`'s own).
  `self_host.lang`'s own copy is UNCHANGED — only the shared parser
  section needs to stay byte-identical between the two files
  (`tests/test_self_eval.py::test_parser_section_matches_self_host`);
  `builtin_names`/`apply_host_builtin` live in the evaluator section,
  which the two files do not share.
- `examples/effects.lang`: new `roll_die()` demo (`fn roll_die() effects
  [random] { trunc(rand() * 6) + 1 }`, a uniform integer draw in `[1, 6]`
  — the canonical "ranged random draw" idiom this round set out to
  unlock) plus 2 new checks (14, as of round 312/317's own head-count
  after the v0.14.9-13 additions, → **16**).
- SPEC.md: `## Builtins` list gained `trunc` (after `sqrt`); new
  `## v0.17 (round 318)` section at the true end of the file (SPEC.md's
  chronological version sections do NOT all live before `## Builtins` —
  `## Self-hosting round 9 (round 254)` is the actual last section before
  `## Builtins`'s own placement earlier in the file; a first edit attempt
  aimed at the wrong insertion point and was caught by the Edit tool's
  own exact-match failure before landing incorrectly).
- **Also fixed, found while investigating**: a genuinely STALE caveat in
  `## v0.16.6`'s own text (round 224), which predicted a guest structural-
  `Record`-spec `matches()` call would "misbehave" and called it a
  "no corpus need yet" backlog item. `tests/test_self_hosting.py::
  test_guest_matches_structural_record_spec_does_not_crash_the_host`
  proves round 240 already found (a real host `AttributeError` crash, WORSE
  than the predicted mismatch) and fixed it (`strip()`-then-delegate for
  both the value and a non-string spec) — SPEC.md's own v0.16.6 section
  had never been updated to say so, an instance of the same "prose left
  stale for dozens of rounds" pattern rounds 212/230/240 have each found
  and fixed elsewhere in this same file. Corrected in place, cross-
  referenced to the real fix and its own knowledge file
  (`knowledge/round-240-whence-guest-matches-structural-spec-crash.md`).

## 5. Verification

- `tests/test_interp.py::test_trunc` (new): positive/negative/already-int
  cases, the toward-zero-not-floor distinction (`trunc(-3.9) == -3`, `!=
  -4`), non-numeric-miss, and the `abs(trunc(x)) == trunc(abs(x))`
  identity for both an int and a float input.
- `tests/test_self_eval.py`: differential `CORPUS` gained
  `'let result = trunc(3.9) + trunc(0 - 3.9) + trunc(9)'` — host-direct
  and guest-mediated execution agree.
- `tests/test_self_hosting.py::
  test_guest_trunc_dispatch_toward_zero_and_total_on_miss` (new, 6
  checks): positive/negative/already-int/miss-propagation/non-numeric-
  miss, plus an explicit "a guest closure passed to `trunc` is a miss,
  no callable guard needed" check (unlike `matches`/`shapeof`, `trunc`
  never special-cases callables — a guest closure unwraps to a Record,
  `_is_num` on a Record is `False`, ordinary miss, no crash).
  `test_effects_lang_runs_under_the_guest_round_164_backlog_closed`
  updated 14 → **16** checks.
- `python3 run.py examples/effects.lang`: **16 passed, 0 failed** (was
  14) — `roll_die()`'s own two new checks pass live, not just under test.
- `tests/test_examples.py::test_effects`: updated `"14 passed"` →
  `"16 passed"`.
- Targeted run (`test_trunc`, `test_abs_sqrt`, `test_self_eval.py`,
  `test_self_hosting.py`, `test_examples.py::test_effects`): **33
  passed**.
- `run_tests_fast.sh`: **945 passed, 38 deselected** (was 943, +2 exact —
  matches the 2 new test FUNCTIONS one-for-one; `test_interp.py::
  test_trunc` and `test_self_hosting.py`'s new dispatch test each count
  as one collected test despite each containing several `assert`s).
- Full unfiltered `pytest tests/` (backgrounded to a real log file, ran
  463.21s): **983 passed** (was 981, +2 exact, matching `run_tests_fast.sh`'s
  own delta since neither new test is `whence_slow`-marked).
- `bench/ref_diff.py --counters examples/*.lang --show` (working tree vs
  `git show HEAD:`): **3 differing (file, mode) pairs, all three are
  `effects.lang`** (direct/fast/slow) — expected and correct, since this
  round changed `effects.lang` itself (14→16 checks, new `roll_die`
  why-nodes `d1`/`d2`/`d3`, one extra `direct_hits`/`fast_hits` tick from
  the extra builtin calls). **Every other example (`self_eval.lang`,
  `self_host.lang`, all 14 others) is byte-identical (SAME)** across all
  three eval modes — confirms zero unintended regression anywhere else
  in the interpreter from adding a new builtin.
- Cross-track: `bash harness/run_tests_fast.sh` → **412 passed, 229
  deselected**, byte-identical to round 317's own post-landing baseline
  — confirms zero changes outside `languages/whence/`.
- `git diff --stat -- languages/whence`: 7 files (`SPEC.md`,
  `examples/effects.lang`, `examples/self_eval.lang`, `tests/
  test_examples.py`, `tests/test_interp.py`, `tests/test_self_eval.py`,
  `tests/test_self_hosting.py`, `whence/interp.py` — 8 total), 241
  insertions, 25 deletions. `git status --porcelain` otherwise showed
  only the 5 standing allowlisted paths.

## 6. What this does NOT close (named honestly, not chased)

- **`harness/swe/fuzz.py`'s `BUILTIN_ARITY` table has no `trunc` entry**
  — its generic program generator will never call it, the identical gap
  class round 299 (SWE-loop D) closed for `rand` one round after round
  294 shipped it. This is real, small, in-scope future work — but it is
  SWE-loop(D)'s track by this project's own established convention
  (language(C) ships a feature; SWE-loop(D) does fuzz/oracle coverage,
  usually the very next round in that track), not attempted here.
- **`harness/swe/guest.py`'s `BANNED` list needs NO addition for
  `trunc`**, unlike `steps`/`at`/`blame`/`diverge`/`contrast` — those are
  banned because a step COUNT/provenance walk legitimately differs
  between host-direct and guest-mediated execution of "the same" program
  (the SAME reasoning round 224 already established for `matches`/
  `shapeof`, and round 206/218 for the provenance family). `trunc` is a
  plain deterministic value transform: host and guest MUST agree exactly,
  so there is no "legitimate but noisy divergence" to suppress. Stated
  explicitly so a future SWE-loop(D) round doesn't have to re-derive it.
- **This closes round 294's item 4 for good** — the literally-requested
  feature (`rand(lo, hi)`) was NOT built, and should not be, without a
  future round first checking whether `trunc`-based composition already
  covers the concrete case in hand (it does, for every case this
  investigation could construct). The same "close by determining the
  real need, not by building the literal ask" resolution shape round 314
  used for the dynamic-call-graph item.

## 7. Reusable lesson

A backlog line that repeats verbatim for 20+ rounds without any round
investigating past its own one-sentence framing is not necessarily "not
yet justified" — it can also be "framed at the wrong layer, and nobody
has checked." The concrete diagnostic that broke this open here: don't
ask "should we widen X's arity/API surface" in isolation — ask "what
would a user actually WRITE to get the effect they want using what
already exists, and does that plausible-looking code actually run?" The
answer here ("no, and not for the reason anyone would guess from
`rand`'s own framing") was one `grep -n "^@register"` and one read of
`b_num` away, never done in 24 rounds because every prior round trusted
the item's own framing instead of re-deriving it from the primitives
that actually exist.

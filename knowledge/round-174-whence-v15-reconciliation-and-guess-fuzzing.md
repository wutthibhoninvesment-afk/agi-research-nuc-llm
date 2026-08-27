# Round 174 (language C) — v0.15 reconciliation + closing the `guess` fuzzer/guest-parity gap

## 1. What this round found

`git status` at the start of this round showed a large uncommitted diff
spanning both `harness/` (a separate, unrelated SWE-loop(D) backlog item —
round 173's `_depth_cascade` fix in `harness/swe/guest.py` + driver/
campaign/coverage/prioritize changes, left untouched this round, out of
language(C) scope, flagged only) and `languages/whence/` (`SPEC.md`,
`interp.py`, `parser.py`, `values.py`) plus two new files
(`examples/guess.lang`, `tests/test_v15.py`). The language-track diff is
round 168's real, complete v0.15 "AI-native primitives" feature — the
curriculum's LAST open advanced-feature slot — built and self-verified
(per its own `SPEC.md` section and `tests/test_v15.py`'s 43 tests) but
never committed, and with no knowledge file or research-state entry. This
is the fourth instance of the exact backlog-accumulation pattern rounds
144/157/159/162/165/171 each independently found and fixed for earlier
rounds (144→122-140, 157→a stray driver edit, 159→155/156, 162→146/158,
171→163/164). Round 171 (skills B) had already spotted round 168's work in
passing but correctly left it alone (out of skills(B) scope).

Full design writeup and re-verification results for round 168's own work
are in the new retroactive
`knowledge/round-168-whence-v15-ai-native-primitives-guess.md` (mirrors how
round 162 handled round 146's identical situation one host-round earlier
in the same arc). This file covers round 174's OWN new work: closing the
fuzzer/guest-parity gap round 168 itself flagged, at commit time, as
"backlog, not this round's scope."

## 2. The gap: `guess`/`is_guess`/`confidence`/`sure` reached neither the
   host fuzzer nor the guest differential

`harness/swe/fuzz.py`'s `BUILTIN_ARITY` table — the set of builtin names
the grammar-directed fuzzer's `call()` picks from — had no entry for any
of the four v0.15 builtins, so the parse-time-adjacent `_guess_binop`/
`_unary`/`sure` machinery was exercised only by the 43-test hand-written
corpus, zero fuzz-generated coverage, from round 168's own commit day.
Unlike the two prior instances of this exact gap shape —
`: Type`/`-> Type` (round 122/126, closed round 134, 8 rounds later) and
`effects [...]` (round 146, closed round 162, 16 rounds later) — round
168's own `SPEC.md` section explicitly named the gap AND explained why it
was different in kind: `guess`/`is_guess`/`confidence`/`sure` are
**ordinary builtin calls**, not new SYNTAX. `: Type` and `effects [...]`
are baked into every function signature (parsed at a fixed grammar
position); `guess(...)` is just `name(args)`, syntactically
indistinguishable from `print(...)` or `len(...)`.

## 3. Why that distinction changes the fix shape

For `: Type`/`effects`, `GuestGen` (the guest-safe fuzz generator,
`harness/swe/guest.py`) had to override the SPECIFIC generator methods
(`typed_params`/`maybe_ret_type`/`maybe_effects`) to a no-op, because a
generated clause is unconditionally present in every function signature
the grammar emits — there is no "drop this one line" option for syntax
woven into a `fn` header. A `guess(...)` CALL, by contrast, is always a
whole, droppable expression-level statement or sub-expression appearing on
one line — exactly the shape `harness/swe/guest.py`'s existing `BANNED`
regex mechanism already handles for the provenance builtins (`why`, `snip`,
`steps`, `at`, `blame`, `diverge`, `contrast`, `print` — all things
`self_eval.lang` cannot mirror, all stripped by `guest_safe()`/`GuestGen`'s
own per-statement filter before a program is ever run through both
evaluators). So the correct-scoped fix for `guess` is not a new no-op
override — it's four more names in `BANNED`.

## 4. What was built

**`harness/swe/fuzz.py`** (host-only totality fuzzer, used unfiltered):
- `BUILTIN_ARITY` gained `"guess": 3, "is_guess": 1, "confidence": 1,
  "sure": 2`.
- New `GUESS_CONFIDENCES`/`GUESS_SOURCES` pools (mix of valid confidences
  `0.9/0.5/0.1/0.0/1.0` and deliberately invalid ones `1.5/-0.2/"bad"`, so
  the fuzzer exercises BOTH the success path and the "confidence must be a
  num in [0, 1]" propagated-miss path — same "mix valid and invalid
  deliberately" pattern `EFFECT_TAG_SETS`/`TYPE_TAGS` already use).
- `call()` gained `guess`/`sure` special cases (mirroring the existing
  `note`/`range`/`get` special cases) so a generated `guess(...)` gets a
  real first argument plus a confidence/source drawn from those pools,
  rather than three arbitrary random expressions that would rarely
  construct a genuine `Guess` value worth threading through the rest of
  the generated program.

**`harness/swe/guest.py`** (guest-differential generator):
- `BANNED` extended: `why|snip|steps|at|blame|diverge|contrast|print` →
  `...|guess|is_guess|confidence|sure`. One four-word regex-alternation
  addition, with a docstring explaining the syntax-vs-call distinction from
  §3 so a future round doesn't "fix" this into a no-op override by
  copy-pasting the `: Type`/`effects` precedent without checking whether it
  still applies.

**New tests** (both files, mirroring the existing
`test_generator_now_emits_effects_clauses`/
`test_generated_effects_programs_agree` pattern from round 162/164):
- `harness/tests/test_swe_fuzz.py::test_generator_now_emits_guess_family_calls`
  — confirms the `BUILTIN_ARITY` addition is actually live (≥15/200 seeds
  contain a `guess`/`is_guess`/`confidence`/`sure` call), not dead code a
  ban makes moot.
- `harness/tests/test_swe_fuzz.py::test_guess_and_sure_builtins_are_total_under_fuzz_confidences`
  — every value in `GUESS_CONFIDENCES` (valid AND invalid) produces a
  TOTAL, non-crashing host run through `run_program`, both for the success
  and the miss path.
- `harness/tests/test_swe_guest.py::test_generator_never_leaks_guess_family_to_guest_output`
  — the base `ProgramGen` (unfiltered) does generate guess-family calls
  (≥15/300 seeds) while `GuestGen.generate_guest_program` (filtered) never
  lets one through, across the same 300 seeds. Proves the ban is doing
  real work, not vacuously passing because generation never happens on the
  guest side either.
- The PRE-EXISTING `test_generator_emits_no_banned_tokens` (60 seeds,
  generic over the whole `BANNED` regex) already covers this too — the new
  test is a deliberate, explicit pin specific to this round's addition,
  same "pin it explicitly even though a generic test already covers it"
  discipline round 162's own `test_generator_now_emits_effects_clauses` used
  for the identical reason.

## 5. Verification

- `python3 -m pytest` (whole `languages/whence` suite, before AND after
  the harness/swe edits — those edits touch no whence-package file):
  **844 passed** in ~120-160s both times.
- All 15 `examples/*.lang` green (`failing_check.lang`'s 2 deliberate
  failures unchanged by design; `guess.lang` 27/27).
- `bench/ref_diff.py --fuzz 300 -n 300` against `HEAD`: 0 differing pairs
  (confirms the working tree's Guess-carrying interpreter changes are
  additive for ordinary, non-Guess fuzz programs).
- Fresh host-fuzz seeds (`harness.swe.fuzz.fuzz`, 400/500/600-program runs,
  three separate seeds spanning before/after the `BUILTIN_ARITY` edit): 0
  crash signatures throughout.
- Fresh guest-differential seeds (`harness.swe.guest.fuzz_guest`, 150
  programs each): seed 91001 (pre-edit baseline) 0 findings (135 ok / 9
  parse_error / 6 timeout); seed 91002 (post-edit, `guess`/`is_guess`/
  `confidence`/`sure` now in the generation mix AND banned from guest
  output) 0 findings (143 ok / 5 parse_error / 2 timeout) — parity holds.
- `python3 -m pytest harness/tests/test_swe_fuzz.py harness/tests/test_swe_guest.py`:
  56 passed (both new tests included).
- Manual spot-check: `re.search(r"\bguess\(|\bsure\(|\bis_guess\(|\bconfidence\("`
  hit 12/50 raw `GuestGen` programs pre-filter, 0/50 post-`guest_safe()` —
  the ban fires at realistic generation rates, not a rare edge case.

## 6. What's still open (real backlog, correctly scoped out this round)

`self_eval.lang`'s hand-copied `arities`/`apply_builtin` tables (the guest
evaluator's own builtin dispatch, written in Whence itself) have no entries
for `guess`/`is_guess`/`confidence`/`sure` at all — banning the calls from
FUZZ-GENERATED programs closes the false-divergence risk, but does not
give the guest evaluator any actual `Guess` support. Building that would
mean: a guest-side tagged representation for `Guess` in the store-passing
evaluator, a guest `_guess_binop`-equivalent threaded through the guest's
own binary-op dispatch, and `arities`/`apply_builtin` entries for all four
names — a materially bigger lift than the `: Type`/`effects` parity work
(those needed only parse-time recognition; a Guess needs a genuine runtime
value representation and propagation rule inside a language that has no
type tags of its own beyond `@{__tag: ...}` records). Not attempted this
round; flagged as the natural next step IF a future language(C) round
wants full guest depth on `guess` specifically, same "flag, don't
manufacture" discipline this track's backlog notes already use elsewhere.

Separately, and explicitly OUT of language(C) scope this round: this
session's tree also contains a real, uncommitted SWE-loop(D) finding
(round 173's `harness/swe/guest.py::_depth_cascade` — a general
self-hosted recursion-depth cascade bug in `self_eval.lang`'s
`exec_stmts`/`eval_items`/`apply` chain, found via the effects-guest-parity
fuzz seed 4002 round 167/171 first flagged, now root-caused as NOT
effects-specific) plus harness/A-track driver changes. Neither reviewed
nor touched by this round — left for the SWE-loop(D)/harness(A) tracks to
reconcile and commit on their own next rounds, per this project's standing
"don't reach across track boundaries" convention (round 165 did the same
for rounds 163/164 in the reverse direction).

## 7. Commit

Committed as a language(C)-scoped diff: `SPEC.md`, `whence/interp.py`,
`whence/parser.py`, `whence/values.py`, `examples/guess.lang`,
`tests/test_v15.py` (round 168's work, verified) plus
`harness/swe/fuzz.py`, `harness/swe/guest.py`,
`harness/tests/test_swe_fuzz.py`, `harness/tests/test_swe_guest.py`
(round 174's fuzzer/guest-parity closure) and both knowledge files. The
unrelated round-173 SWE-loop(D)/harness(A) files were left uncommitted in
the working tree, untouched, for their own track's next round.

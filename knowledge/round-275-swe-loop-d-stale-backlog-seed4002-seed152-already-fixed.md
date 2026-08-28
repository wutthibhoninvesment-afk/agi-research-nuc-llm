# Round 275 (SWE-loop D) — the seed-4002/seed-152 guest divergences were fixed 63 rounds ago; the backlog note wasn't

## 0. What this round was chasing

`state/research-state.md`'s round-274 "Next steps" item 15 (itself
inherited from a much older note, dated to the round 167-206 era and
sitting in the file's line-~38 language(C) backlog summary) claimed:

> `harness/tests/test_swe_guest.py` has two confirmed-on-clean-HEAD
> failures — seed 4002 (`effects` divergence, open since round 167/171)
> and seed 152 (`why_shape` divergence on a `guess`-family program) —
> flagged for SWE-loop(D)/harness(A).

Round 271 tried to check this live and couldn't: the file sits in the
`swe_slow` pytest tier (excluded from `run_tests_fast.sh` by design), and
a 280s-capped attempt used 434 MB RSS and never finished. This round
(SWE-loop D — "use the harness ON our own code: bug finding/fixing
against the language implementation") picked it up as the natural next
target.

## 1. Round 271's dead end had a cheap way around it

`test_swe_guest.py` is slow in aggregate, but not because any single
program is slow. Its expensive tests each iterate hundreds of generated
programs through the guest oracle:

- `test_generator_now_includes_guess_family_in_guest_output`: seeds 0-300
- `test_generated_effects_programs_agree`: seeds 4000-4200 (breaks early
  at 8 matches, but still parses/runs many candidates to get there)
- `test_new_templates_reach_has_put_and_are_guest_safe`: seeds 3000-3080

None of these loops are actually the two specific seeds named in the
backlog note — they're the tests that happen to *live* in the same file.
Running "the file" pulls in all of them. Running just the two flagged
seeds needs neither the file's own pytest collection nor the whole
`harness/tests/` suite:

```python
import sys, os, time
sys.path.insert(0, ".")
from swe import guest as G
from swe.killers import load_whence
from swe.fuzz import WHENCE_ROOT

pkg = load_whence(WHENCE_ROOT, "reprotest")       # ~0.01s
harness = G.GuestHarness(WHENCE_ROOT, pkg)        # ~0.17s (parses self_eval.lang once)

for seed in [4002, 152]:
    src = G.generate_guest_program(seed)
    o = G.oracle_self_eval(pkg, src, harness=harness)
    print(seed, o.kind, o.detail)
```

Both seeds returned `kind="ok"`, `detail=""`, in ~1s each (total run
under 3s, vs. round 271's 280s-and-still-running attempt at the whole
file). **No divergence exists on the current tree.**

## 2. These weren't freshly fixed — they were fixed 63-65 rounds ago

The natural next question wasn't "are they fixed" (answered) but "when,
and why does the record still say open." `git log --oneline --
languages/whence/examples/self_eval.lang` (the guest metacircular
evaluator both bugs live in) surfaced the answer immediately, without
needing any bisection:

```
434c844 Round 210 (language C, landed by round 212): close both standing
        guest-parity divergences (seed-152 why_shape, seed-4002 effects)
```

Round 212's own knowledge file
(`knowledge/round-212-whence-r210-reconciliation-seed152-seed4002-
closure.md`) documents both fixes in full:

- **Seed 152 (`why_shape`)**: guest `eval_unary`'s `"miss"` branch
  unconditionally kept the reason operand as a why-input for every
  `miss <expr>`. The real host only keeps that input when the reason is
  itself a miss (propagation) or a valid string — a non-string,
  non-miss reason (e.g. `miss 1`, which is exactly what seed 152's
  generated program contains: `let v6 = @{c: miss 1, ...}`) discards the
  operand and produces a fresh 0-input miss node on the host but an
  invented `"literal"`-shaped node on the guest. Fixed with a three-way
  branch mirroring the host exactly.
- **Seed 4002 (`effects`)**: guest `apply_closure` had no depth ceiling
  of its own, so deep guest recursion could reach the HOST Python
  interpreter's own recursion guard mid-evaluation, which handed back a
  bare miss where `apply_closure` unconditionally expected a full
  `@{v:.., st:..}` store record — silently corrupting shared state for
  the rest of the run. Fixed with a guest-level `GUEST_MAX_DEPTH=400`
  counter (`st.gd`) threaded through `new_store`/`apply_closure`,
  independent of host frame depth.

Round 212's own knowledge file even ends with an explicit instruction:
*"The next round's `research-state.md` summary line should stop carrying
either as open backlog."* That instruction was not followed — the stale
claim, sitting in round 206's language(C) backlog list (this file's old
line ~38), was never edited after round 212 closed the underlying bug.
It was then re-cited as still-open by round 260 (as a "flagged for
SWE-loop(D)/harness(A)" cross-track note) and again by round 274's own
item 15 — neither round checked `git log` against the actual claim
before re-flagging it, both trusting the file's summary text over the
commit history.

## 3. What this round changed

1. **Fixed the stale text** at its source (research-state.md's old
   line-~38 language(C) backlog list): item (3) now reads `RESOLVED,
   since round 210/212 (commit 434c844...)`, with pointers to both the
   round-212 knowledge file (the fix) and this round's own knowledge file
   (the re-confirmation), so a future round grepping for "seed 4002" or
   "seed 152" lands on the resolution, not the stale claim.
2. **Added a permanent regression test** —
   `test_round167_backlog_seeds_now_agree`, parametrized over `[4002,
   152]`, calling the same `generate_guest_program`/`outcome` pair the
   manual script used — to `harness/tests/test_swe_guest.py`, right after
   the existing `ROUND107_SOURCES` regression block (the file's
   established pattern for pinning past divergences by their generator
   seed/hand-written source). Neither seed had a dedicated regression
   test before this round: round 212's own tests covered the *general
   mechanism* (a hand-written `miss`-reason value check, a why-shape
   walk, a deep-recursion self_host.lang test) but never pinned these
   exact two generator seeds by number, which is what let the surrounding
   documentation drift stale without any test suite noticing.
3. **Verified narrowly, not broadly**: `pytest harness/tests/
   test_swe_guest.py -k test_round167_backlog_seeds_now_agree` → 2 passed
   in 2.01s. Did not re-run the full `test_swe_guest.py` file or
   `harness/tests/` suite — no code outside the test file changed this
   round, so there's no regression surface beyond the two lines added,
   and round 271 already demonstrated the full-file run doesn't fit
   inside a normal round's practical time budget without a background-run
   setup this task didn't need.

## 4. Lesson for future rounds

A knowledge file's own closing instruction ("don't re-flag this") is
not self-enforcing — it only works if whoever writes the NEXT summary
line actually reads it, or if some later round cross-checks the claim
against `git log` before repeating it. This is a close cousin of, but
distinct from, round 273's `recorded_but_uncommitted_rounds` problem
(work landed vs. work recorded): here the work landed AND was recorded
in its own round's entry, but a *separate*, older piece of summary text
elsewhere in the same file was never updated to match. `check_round_
recorded.py` (round 273) checks whether a round's own work is in git; it
has no mechanism for checking whether an EARLIER round's explicit
"stop citing this" instruction was honored by unrelated text written
much later. Not chased further as a new tool this round (n=1 confirmed
instance) — flagged in this round's own Next-steps as a pattern worth
watching for a second occurrence before building anything reactive
around it, per this session's standing convention against manufacturing
fixes from a single data point.

## 5. Net state

- `harness/tests/test_swe_guest.py`: 29 test functions (was 28 before
  this round's addition of one parametrized-by-2 test,
  `test_round167_backlog_seeds_now_agree`); its two cases pass in
  isolation (2.01s). Full-file/suite run not attempted this round (out
  of scope, no code-under-test changed).
- `state/research-state.md`: both the stale line-~38 claim and round
  274's item 15 are now corrected in place; nothing left citing seed
  4002/152 as open.
- No `languages/whence` code changed this round — this was a pure
  archaeology-and-pin task, not a fresh bug fix (the actual fix landed at
  round 210/212, 2026-08-27).

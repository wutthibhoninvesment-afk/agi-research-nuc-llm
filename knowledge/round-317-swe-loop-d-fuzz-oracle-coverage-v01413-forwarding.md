# Round 317 (SWE-loop D) — fuzz + oracle coverage for Whence v0.14.13 (argument forwarded through a second function call)

## Pre-flight

`ps -eo pid,ppid,etime,cmd` showed only this round's own driver process tree
([[feedback_check_for_concurrent_rounds]]). `git status --porcelain` showed
only `state/round_counter` and the 4 Hermes-owned `languages/whence/` files,
both already covered by `state/known-standing-dirty-paths.json`
([[feedback_check_cached_diff_before_commit]]).

## Task selection

`research-state.md`'s next-steps have named this exact gap since round 312,
repeated unchanged through rounds 314/315/316 (item 2 in round 316's own
list): fuzz coverage (`harness/swe/fuzz.py`) and oracle coverage
(`harness/swe/alias_effects.py`) for v0.14.13 (round 312: an argument
forwarded through a SECOND function call, before landing in a
directly-called param — `fn inner(g) effects [io] { g(1) }` then `fn
outer(f) effects [io] { inner(f) }`, `outer(print)`). Round 311's own
precedent (closing v0.14.11/v0.14.12's fuzz gap the round after they
landed) is the template this round follows again, now for v0.14.13.

Round 314's own investigation (the OTHER remaining gap named alongside this
one, "the dynamic call graph") is CLOSED as not-a-bug — unrelated to this
round's own task, which targets the gap round 312's own SPEC.md text
explicitly closed with a real mechanism, not the one it left as an honest
design sketch.

## What v0.14.13 actually does (read from `whence/parser.py`, not assumed)

Read `Parser._check_param_forwarding` and its new shared helper
`_resolve_current_fn_param` in full before writing a line of oracle code —
same discipline every prior SWE-loop(D) round in this family used.

- **The design insight**: `Parser.param_call_scopes` already records, for
  EVERY named fn (or `let`-bound anonymous one), "which of my own params
  does my body call directly" (v0.14.9) — resolved by the time that fn's
  own body finishes parsing, strictly BEFORE any caller of it can be
  parsed. So when `outer`'s body itself calls `inner(f)`, checking whether
  `f` (or a same-body rename of it) lands in one of `inner`'s own
  DIRECTLY-called param positions is enough: if it does, `outer` ITSELF
  now also counts as "calling `f` directly" for the purposes of `outer`'s
  OWN `param_call_scopes` entry — recorded into the exact same
  `direct_param_calls_stack[-1]` v0.14.9's leading block already
  populates.
- **Needs ZERO new scope-stack** — the first addition in this whole
  v0.14.x family that doesn't (v0.14.4/6/7/9/11/12 each added one). Pure
  composition of a fact this family already computes. `_check_call_site_
  param_effects` at a LATER call site (`outer(print)`) needs zero changes
  either: it already walks `_resolve_param_call_fact("outer")`
  generically, indifferent to whether `f`'s membership in `outer`'s own
  `called_params` came from a direct call, a same-body rename, or (now) a
  one-level-removed forward.
- Composes to ARBITRARY depth for free via the same single-pass,
  declaration-ordered discipline the rest of the family relies on — no
  explicit recursion in the real check.

## Design: extending `ExtendedEffectGen` (the independent oracle)

Added **zero new stacks** (matching the real design exactly, and the first
round in this family's own coverage work that doesn't need one either) —
one new method, `record_param_forwarding(callee_name, arg_infos)`, a
direct mirror of `_check_param_forwarding`: reads `resolve_param_call_fact
(callee_name)`, walks the callee's own called-param positions, and for
each argument at that position that resolves (via `_resolve_param_
identity_then_alias`, factored out in round 312's own real-parser change
and already present in this oracle since round 311) to one of the
CURRENTLY open fn's own params, adds it to `direct_param_calls_stack[-1]`.
Guarded by the same `if self.done: return` latch every other `record_*`
method in this class already uses, so it mirrors `postfix()`'s own
sequencing exactly: a call site only reaches the forwarding check if
neither the ordinary direct-call check nor `_check_call_site_param_
effects` already raised for that same call.

One new statement, `_stmt_call_forward_own_param`: requires BOTH
`current_fn_own_params()` (something to forward) and `known_param_call_
names()` (somewhere to forward it to) non-empty. Picks one of the current
fn's own params (30% of the time via a same-body rename hop first,
mirroring `_stmt_let_rename_own_param`'s own pattern), places it at a
randomly-chosen CALLED position of a tracked callee, fills every other
position with a plain literal, then runs the real three-check sequence in
order (`record_call_direct` → `check_call_site_param_effects` →
`record_param_forwarding`, each gated on `self.done`) exactly mirroring
`postfix()`'s own per-`(` ordering.

**Deliberately does NOT need a new external-verdict statement** — the same
"fact producer, existing consumer" reasoning round 311's own knowledge
file gives for v0.14.11's rename mechanism: once the forwarded param lands
in the CURRENTLY-open fn's own `param_call_scopes` entry (once its body
finishes parsing), a LATER call through THAT fn's own name is checked by
the EXISTING `_stmt_call_tracked_fn`/`_stmt_shadow_tracked_fn_call`
exactly as any other tracked fact would be.

## `harness/swe/fuzz.py`: crash-fuzz grammar reach

One new body-shape helper, `_param_forward_body(params, target_name,
target_arity, target_called_idx)` — builds a fn body that forwards one of
its OWN params into an ALREADY-tracked fn's own called-param position
(drawn from `self.param_call_fns`, the SAME list `_param_call_body`/
`_param_rename_call_body`/`call()` already share — no new list, matching
round 311's own reuse trick for the rename variant). Returns `(source,
forwarded_param_index)`; the caller registers `(name, arity, forwarded_
param_index)` back into `self.param_call_fns` ITSELF, since this fn now
also "calls that param directly" by composition — `call()`'s existing
consumer needs no changes to reach a call through a forwarding fn either.

Wired into both existing `param_call_fns`-producing sites (the `let`-bound
anonymous-fn branch and the NAMED-fn branch) as a THIRD option, ~34% of
the time when `self.param_call_fns` is already non-empty (there must be an
earlier-declared tracked fn to forward into), alongside the existing
50/50 direct-call/rename split. Still crash-fuzz coverage only (no
semantic oracle in this file), consistent with every prior addition.

## Verification

- `harness/swe/alias_effects.py`: manual scaling checks before locking in
  test thresholds — the new mechanism fires (mutates `direct_param_calls_
  stack`) in ~2.9% of programs (145/5000) and produces a DENIED
  `error_param` verdict specifically through a forwarded param in ~0.44%
  (35/8000, out of ~2.3% "effective forward" programs). Targeted campaign
  against the real parser confirmed **0 mismatches** at 3000 seeds during
  design, then folded into the main campaign.
- `harness/tests/test_swe_alias_effects.py`: 26 → **29 tests** (3 new — 1
  reach guard, 1 denial-rate correctness check, 1 mutation test). The main
  differential campaign bumped 11000 → 13000 seeds (keeping per-shape
  sample size comparable, the same bump-on-every-addition discipline
  rounds 287/293/305/311 each used). New mutation test: `_check_param_
  forwarding` neutralized entirely (simulating the whole v0.14.13 feature
  vanishing) — measured 18/50000 (~0.036%) in manual scaling, rarer than
  most prior "missing check" mutations in this file since it needs the
  forward to be the fn's OWN SOLE source of a called-param fact (not
  redundant with an ordinary direct call/rename in the same body) AND a
  later call site to independently land an effectful arg at exactly that
  position — N=50000 for comfortable headroom. Unlike v0.14.9/10's and
  v0.14.11/12's own coverage rounds, v0.14.13 needed no companion
  shadowing-revert mutation: it adds no new resolver with its own
  scope-stack walk (see `ExtendedEffectGen.__init__`'s own new "v0.14.13"
  comment — pure composition of the ALREADY shadow-tested `param_call_
  scopes`/`resolve_param_call_fact`). Full file run: **29 passed in
  449s**.
- `harness/swe/fuzz.py`: manual scaling check — the new shape fires in
  ~0.42% of programs (25/6000, rarer than v0.14.11/12's own shapes since
  it additionally needs an EARLIER fn already registered in `self.param_
  call_fns` before the 34% draw is even offered). 2000-program crash-safety
  sweep — **0 crashes**.
- `harness/tests/test_swe_fuzz.py`: 23 → **26 tests** (3 new — 1 reach
  guard via instrumentation (a source-text regex can't distinguish a
  forwarded bare-param argument from any other bare-name argument), 1
  crash-safety-under-fuzz sweep at 800 programs, 1 hand-written grant/deny
  pair mirroring `tests/test_v14.py`'s own `test_param_forwarded_to_
  second_function_that_calls_it_is_now_checked`). Full file run: **26
  passed in 104s**.
- Combined: `python3 -m pytest harness/tests/test_swe_alias_effects.py
  harness/tests/test_swe_fuzz.py -q` → **55 passed** (was 49 before this
  round, +6 exact matching the new-test count).
- `bash harness/run_tests_fast.sh`: 412 passed (unchanged — every new test
  this round is `swe_slow`-tier and correctly auto-deselected), 223 → **229
  deselected** (+6 exact, matching the 6 new tests).
- Cross-track regression: `bash languages/whence/run_tests_fast.sh` → **943
  passed, 38 deselected**, byte-identical to round 314/315/316's own
  baseline — confirms this round's diff touched nothing outside `harness/`.
- `git diff --stat`: 4 files (`harness/swe/alias_effects.py`, `harness/swe/
  fuzz.py`, and their two test files) + `state/round_counter`, 375
  insertions, 15 deletions — matches the round's own described scope
  exactly.

## Still open

1. With v0.14.9 through v0.14.13 ALL now closed for both their parser
   mechanism AND their fuzz/oracle coverage, the entire "value flow
   through a function argument/return" backlog named across rounds 302,
   306, 308, 311 is fully closed. The ONE remaining named gap in this
   whole effect-system family is the dynamic call graph (round 270,
   formally CLOSED as a backlog item by round 314's own investigation —
   see `SPEC.md`'s "v0.14.14" section — not reopened without a real
   design decision between its two sketched approaches first).
2. The cross-fn-boundary rename-collision scenario (round 306's own
   hand-written `test_param_rename_in_enclosing_fn_not_misattributed_to_
   inner_fn`) is STILL not independently fuzz-covered — round 311's item 2,
   unchanged; `fresh()`'s global name uniqueness means it never arises from
   pure random generation, needing a DEDICATED shadow-style statement a
   future SWE-loop(D) round could build, following `_stmt_shadow_tracked_
   fn_call`'s own pattern.
3. An analogous cross-fn-boundary collision for the NEW v0.14.13 forwarding
   mechanism specifically (a coincidental name collision between an
   argument forwarded from an OUTER fn and an unrelated INNER fn's own
   params) is also not fuzz-covered here, same `fresh()`-uniqueness reason
   as item 2 — a natural companion to item 2 for whichever future round
   builds the dedicated shadow statement.

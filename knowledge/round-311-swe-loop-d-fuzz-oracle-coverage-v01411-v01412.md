# Round 311 (SWE-loop D) — fuzz + oracle coverage for Whence v0.14.11 (param rename-chain) and v0.14.12 (return-param passthrough)

## Pre-flight

`ps -eo pid,ppid,etime,cmd` showed only this round's own driver process tree
([[feedback_check_for_concurrent_rounds]]). `git status --porcelain` showed
only `state/round_counter` and the 4 Hermes-owned `languages/whence/` files,
both already covered by `state/known-standing-dirty-paths.json`
([[feedback_check_cached_diff_before_commit]]). `check_round_recorded.py
--since 305` showed only this in-flight round as a gap — no reconciliation
owed.

## Task selection

`research-state.md`'s next-steps have named this exact gap since round 306,
repeated unchanged through rounds 308/309/310: fuzz coverage
(`harness/swe/fuzz.py`) and oracle coverage (`harness/swe/alias_effects.py`)
for Whence v0.14.11 (round 306: a param `let`-renamed inside its own fn
body, then called through the rename) and v0.14.12 (round 308: a param
returned directly by the callee's own body, so the caller ends up holding
the alias). Round 305's own precedent (closing v0.14.9/v0.14.10's fuzz gap
one round later, landed by round 306) is the template this round follows,
now for the next two features in the same family.

## What v0.14.11/v0.14.12 actually do (read from `whence/parser.py`, not
assumed)

Read `Parser.__init__`'s own `param_alias_scopes`/`return_param_scopes`
docstrings, `statement()`'s `let` NameRef/Call/FnExpr branches, `stmt_list`'s
now-three-valued `(stmts, tail_alias_tag, tail_param_name)` return, and
`_check_effect_call`/`_resolve_param_alias`/`_tail_return_param_name`/
`_resolve_return_param_fact`/`_resolve_return_param_passthrough` in full
before writing a line of oracle code — same discipline every prior
SWE-loop(D) round in this family used.

- **v0.14.11**: a SEVENTH parser stack, `param_alias_scopes`, pushed/popped
  at the same three sites `param_call_scopes` already is. Each frame maps a
  name to `None` or the ORIGINAL param name it is currently a pure
  `let`-rename of (within the SAME open fn body only — bounded by locating
  `current_fn_params_frame_stack[-1]`'s own identity inside `alias_scopes`
  and refusing to walk any `param_alias_scopes` frame below that index, the
  exact cross-fn-collision guard round 306's own knowledge file documents).
  `_check_effect_call`'s existing v0.14.9 tracking block gained an `else`
  branch: if the callee doesn't resolve directly to the current fn's own
  params frame, try `_resolve_param_alias` and record the ORIGINAL param
  name if it resolves.
- **v0.14.12**: an EIGHTH stack, `return_param_scopes`, pushed/popped at the
  same sites `return_alias_scopes` already is. Each frame maps a name to
  `None` or `(params_tuple, tail_param_name)`. `stmt_list` now also computes
  `tail_param_name` via `_tail_return_param_name` (does the tail bare-NameRef
  identity-match the current fn's own params frame, or resolve through
  `_resolve_param_alias`?) alongside its existing `tail_alias_tag`. A NAMED
  fn or `let`-bound anonymous fn whose body's tail hands back one of its own
  params gets this fact recorded once its body finishes parsing.
  `_resolve_return_param_passthrough(fn_name, args)` combines that FIXED
  per-definition fact with the ACTUAL arguments at one call site: finds the
  returned param's own position, bounds-checks against `len(args)`, and
  resolves the matching argument's own alias tag if it's a bare NameRef —
  argument-DEPENDENT, unlike every other fact this whole family tracks.
  Consumed at TWO call sites: `statement()`'s own `let`-Call branch (`let g
  = apply(print)`) and `_check_effect_call`'s own `Call`-callee branch
  (`apply(print)(1)`, no intermediate `let`).

## Design: extending `ExtendedEffectGen` (the independent oracle)

Added the two new stacks with IDENTICAL push/pop shape and site discipline
to the real parser (verified line-by-line, not assumed): `param_alias_
scopes` pushed as `{}` at both `gen_frame`'s own per-block frame AND the fn
params-frame push sites (never `dict.fromkeys(params)` — a param is never
itself a rename of a param, only a LATER `let`-rename produces an entry);
`return_param_scopes` pushed as `{}` at the block frame and `dict.
fromkeys(params)` at the fn params-frame push sites, mirroring `return_
alias_scopes`'s own dual shape exactly.

New resolvers, each a direct mirror of its real-parser counterpart:
`resolve_param_alias` (boundary-bounded multi-hop walk), a shared
`_resolve_param_identity_then_alias` helper (the real parser duplicates this
exact "is it literally the param, or a rename of one" check at TWO call
sites — the `let`-rename branch and `_tail_return_param_name` — without
factoring it out; this oracle names the shared shape once), `resolve_
return_param_fact`, and `resolve_return_param_passthrough`.

`gen_frame`'s return contract widened from `(lines, tail_tag)` to `(lines,
tail_tag, tail_param_name)`, threading through every caller (`gen_program`,
`_gen_if_tail_inner` — which deliberately DISCARDS each arm's own
`tail_param_name`, exactly matching `stmt_list`'s own docstring that only a
bare-NameRef tail, never an `if`, ever yields one — `_gen_fn_stmt`, `_stmt_
let_fn_expr`, `_stmt_shadow_param`, `_stmt_nested_block`). `bind()` gained
two new optional kwargs (`param_alias_target`, `return_param_fact`) so every
existing `let`-branch statement could be updated in one pass to carry the
two new facts forward exactly where the real parser's own `let` dispatch
does (rename branch: computed via the shared helper; every other branch:
explicit `None`, matching the "every binding site writes ALL stacks
together" invariant this family has kept since v0.14.2).

Three new statements:

1. `_stmt_let_rename_own_param` (v0.14.11) — `let g = p` where `p` is one of
   the CURRENTLY-open fn's own params, immediately followed by a call
   through the rename (`g(0)`), 40% of the time a second chained hop
   (`let h = g` then `h(0)`). This is the SOLE producer of a non-None
   `param_alias_scopes` entry — no other pool in this generator ever draws a
   bare, untagged param name as a `let` RHS, the same reason `_stmt_call_
   own_param` is the sole producer of a `direct_param_calls_stack` entry via
   the BASE (non-rename) path. Deliberately does NOT need a new external-
   verdict statement: once the fact lands in `param_call_scopes` (via `_track_
   direct_param_call`'s new fallback branch), the EXISTING `_stmt_call_
   tracked_fn`/`_stmt_shadow_tracked_fn_call` already exercise the granted/
   denied verdict generically — the same fact-producer/fact-consumer
   separation round 309's own skill-authoring round (`tiny-language-
   implementation/SKILL.md`) just codified as a named pattern across this
   whole v0.14.x family.
2. `_stmt_let_call_return_param_passthrough` (v0.14.12) — `let g =
   apply(print)` where `apply` is drawn from `known_return_param_names()`,
   70% of the time an effectful builtin/alias at the returned param's own
   position, immediately followed by `g(0)` so the resulting tag is
   observable.
3. `_stmt_call_return_param_passthrough_chain` (v0.14.12) — `apply(print)(1)`
   with no intermediate `let`, mirroring `_check_effect_call`'s own
   `Call`-callee branch two-application ordering.

## Two real bugs the oracle caught in ITSELF before ever reaching a campaign
(the actual point of writing an independent oracle)

**Bug 1 — missing ordinary call-site check before the passthrough
computation.** First draft of `_stmt_let_call_return_param_passthrough`
computed `tag = resolve_return(fname); if tag is None: tag =
resolve_return_param_passthrough(...)` directly, without first running the
SAME ordinary `_check_effect_call`/`_check_call_site_param_effects` sequence
every other call in this generator already goes through. This missed a real
compositional case: a fn drawn from `known_return_param_names()` can ALSO
independently carry its own `param_call_scopes` fact (its body both calls a
param directly AND tail-returns a param — not mutually exclusive; e.g. `fn
f3(p4) effects [] { p4()(0)\n p4 }` — the first line's OWN application
already tracks `p4` as directly called via `_check_effect_call`'s leading
v0.14.9 block, REGARDLESS of what the second application does). Parsing
`f3(print)` as an expression (inside `postfix()`) always runs its own
ordinary checks BEFORE the resulting `Call` node ever reaches `statement()`'s
`let`-branch dispatch — the oracle's first draft skipped straight to the
`let`-branch's own additional tag computation, missing that the inner call
itself could already raise. An 8000-seed differential campaign against the
real parser found 5 concrete mismatches in the first ~2200 seeds (e.g. seed
459, `let a5 = f3(print)\n a5(0)`: real parser raised at `f3(print)` itself
via `_check_call_site_param_effects`; the buggy oracle predicted `ok` until
`a5(0)`, a wrong-callee-name divergence). Fixed by running `record_call_
direct(fname)` then, if not done, `check_call_site_param_effects(fname,
arg_infos)` FIRST, exactly matching `_stmt_call_return_param_passthrough_
chain`'s (correctly-ordered from the start) own sequencing.

**Bug 2 — unguarded shadow crash.** Both new v0.14.12 statements drew `fname`
from `known_return_param_names()`, a raw multi-frame scan (same convention
as `known_return_names()` etc.), then unpacked `resolve_return_param_fact
(fname)`'s result unconditionally. Since `fresh()` names are globally
unique, this pool practically never contains a genuinely shadowed entry
under NORMAL generation — but the generic `_stmt_shadow_let`/`_stmt_shadow_
fn`/`_stmt_shadow_param` statements explicitly REUSE outer names, and once
those got their own `return_param_scopes` slot wired through `bind()`'s new
kwarg (defaulting to `None`), a shadowed name could land in the pool with a
CLOSER frame's `None` fact — `resolve_return_param_fact` correctly returns
`None` via the innermost-first walk, but the caller unpacked it as a 2-tuple
regardless, crashing with `TypeError: cannot unpack non-iterable NoneType
object` (5 instances in the first 1500 seeds of the initial campaign). Fixed
with the same shadow-fallback guard `_stmt_call_tracked_fn` already uses:
check `fact is None` first, fall back to an ordinary untracked call if so.

Both bugs were caught and fixed BEFORE any test was written — the
differential campaign against the real parser is what surfaced them, not
code review. Re-running the same 8000-seed campaign after both fixes: 0
mismatches, 0 crashes. Scaled to 20000+ seeds across multiple `max_depth`/
`max_stmts` combinations afterward: still 0/0.

## `harness/swe/fuzz.py`: crash-fuzz grammar reach

Two new body-shape helpers, `_param_rename_call_body` (v0.14.11: rename then
call, 1-2 hops, same `(source_text, called_param_index)` contract as the
existing `_param_call_body`) and `_return_param_body` (v0.14.12: a bare-param
tail, `(source_text, returned_param_index)`). Deliberately reuse the
EXISTING `param_call_fns`/`call()` consumer for the rename variant (the
external, call-site-observable shape is identical regardless of how the
fn's body arrived at "calls this param" — the same fact-producer/consumer
separation the oracle statements above lean on) — no new list, no `call()`
change needed for that half. `return_param_fns` is a genuinely new list with
two consumption shapes: a `let`-bound call (reusing the EXISTING `alias_
names`/`call()` alias-consumer unchanged, same reuse trick) and a new
chained-no-`let` branch in `call()` mirroring `return_alias_fns`'s own
existing chained-call shape. Wired into both the `let`-statement branch
(anonymous-fn variants, ~4% each) and the NAMED-fn branch (~5% each, arity
permitting). Still crash-fuzz coverage only (no semantic oracle in this
file for either shape — that's what `alias_effects.py` is for), consistent
with every prior addition in this family.

## Verification

- `harness/swe/alias_effects.py`: differential campaign against the real
  parser, ad hoc scaling checks before locking in test thresholds — 28000+
  seeds total across several `max_depth`/`max_stmts` combinations, final
  state **0 mismatches, 0 crashes** (post both bug fixes above; pre-fix: 5
  mismatches + 12 crashes in the first 8000 seeds).
- `harness/tests/test_swe_alias_effects.py`: 20 → **26 tests** (6 new — 2
  reach guards, 4 mutation tests). The main differential campaign bumped
  9000 → 11000 seeds (keeping per-shape sample size comparable, the same
  bump-on-every-addition discipline rounds 287/293/305 each used). New
  mutation tests: `_resolve_param_alias` neutralized entirely (~0.75% hit
  rate, N=4000), `_resolve_param_alias` weakened to single-frame-only
  (~1.7%, N=8000, this one exercises the boundary-bounded multi-hop walk
  specifically, reachable via `gen_tail_stmt`'s existing `any_visible_name()`
  pool crossing a nested-block frame — no new dedicated statement needed),
  `_resolve_return_param_passthrough` neutralized entirely (~1.1%, N=8000),
  `_resolve_return_param_passthrough` given a wrong (always-0) argument
  index (~0.19%, N=15000). Full file run: **26 passed in 386s** (the large
  campaigns/mutations dominate; this file is now genuinely `swe_slow`-tier
  as a whole).
- `harness/swe/fuzz.py`: 3000-seed crash-safety sweep (`ProgramGen` →
  `whence.parser.parse`) — **0 crashes** (2756 ok, 244 parse/lex error, both
  new shapes confirmed reachable: rename shape ~7.2%/3000, `return_param_
  fns` populated in ~13.8%/3000 programs).
- `harness/tests/test_swe_fuzz.py`: 18 → **23 tests** (5 new — 2 reach
  guards, 2 crash-safety-under-fuzz sweeps at 800 programs each, 1
  hand-written grant/deny triple covering both consumption shapes). Full
  file run: **23 passed in 76s**.
- Combined: `python3 -m pytest harness/tests/test_swe_alias_effects.py
  harness/tests/test_swe_fuzz.py -q` → **49 passed** (was 38 before this
  round, +11 exact matching the new-test count).
- `bash harness/run_tests_fast.sh`: 412 passed (unchanged — every new test
  this round is `swe_slow`-tier and correctly auto-deselected), 212 → **223
  deselected** (+11 exact, matching the 11 new tests).
- Cross-track regression: `bash languages/whence/run_tests_fast.sh` → **935
  passed, 38 deselected**, byte-identical to round 308/309/310's own
  baseline — confirms this round's diff touched nothing outside `harness/`.
- Full unfiltered `python3 -m pytest harness/tests/` run in the background
  for a final total-suite number (large N campaigns make it several
  minutes); see `research-state.md`'s own entry for the final count once it
  lands, or re-run directly if this file predates it.

## Still open (unchanged from round 306/308's own honest scope statements)

1. An argument reaching an effectful builtin through a SECOND function call
   before landing in a directly-called param (or a rename/return of one).
2. The dynamic call graph — calling a different, unrestricted top-level fn
   that itself performs the effect — completely untouched.
3. With v0.14.9/v0.14.10/v0.14.11/v0.14.12 ALL now closed for BOTH their
   parser mechanism AND their fuzz/oracle coverage, the entire remaining
   "value flow through a function argument/return" backlog is exclusively
   items 1-2 above — flagged across four consecutive language(C) rounds
   (302, 306, 308, and implicitly this round's own coverage work) as
   needing a real design sketch, not another small pre-scoped slice.
4. The cross-fn-boundary collision scenario round 306's own hand-written
   `test_param_rename_in_enclosing_fn_not_misattributed_to_inner_fn` covers
   (a coincidental name collision between an outer fn's rename target and an
   unrelated inner fn's own params) is NOT independently fuzz-covered here —
   it needs a DEDICATED shadow-style statement (reusing an existing name
   across a fn boundary) that this round did not build, since `fresh()`'s
   global name uniqueness means it never arises from pure random generation.
   A future round wanting this specific coverage should look at how `_stmt_
   shadow_tracked_fn_call`/`_stmt_shadow_box_call_field_return` engineer
   their own otherwise-impossibly-rare scenarios for the pattern to follow.

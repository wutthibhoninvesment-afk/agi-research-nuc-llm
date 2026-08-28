# Round 270 (language C) — Whence v0.14.3: return-value flow closes another slice of v0.14.2's own open gap

## 1. Starting point

`git status` was clean except the standing Hermes-owned untracked files
(`examples/expense_tracker.lang`, `examples/test_simple.lang`,
`pyproject.toml`, `whence_qwen_bridge.py` — confirmed unchanged, left
alone, per the standing project memory that a separate autonomous system
writes these) and the shared `state/round_counter`. No concurrent round
process was running (`ps aux` showed only this round's own driver chain).

Research-state.md's own backlog item 11 (written by round 266, restated by
round 269) named two still-open pieces of the effect system, both
deliberately scoped OUT of round 266:

- (a) value flow through anything other than a direct `let` hop — a
  builtin passed as a function ARGUMENT, returned from a call, or stored
  in a list/record field and read back out.
- (b) the dynamic call graph — a fn calling a DIFFERENT, unrestricted
  top-level fn that itself performs the effect.

Item 11 explicitly flagged (b) as multi-round-scale ("needs per-fn effect
summaries and transitive resolution ... don't attempt as a quick
follow-up without first sketching"). (a) wasn't sized as explicitly, but
still spans three genuinely different value-flow shapes (argument, return,
container field). This round picked the RETURN-VALUE slice of (a)
specifically — the others are discussed in §5 as to why they don't fit the
same narrow, single-pass mold.

`free -h` at round start: 489 MB free / 2.2 GB available — confirms
backlog item 7 (the 13-checkpoint `bench/self_host_memscale.py` sweep,
needs ~3-4 GB) is still blocked, unchanged from round 258/260's own
snapshots. Not attempted this round either.

## 2. Why the RETURN slice, and not argument/container flow

All three unclosed value-flow shapes in item 11(a) could theoretically be
attacked, but they are not equally narrow:

- **Return value** (`fn get() { print }` then `let p = get()`): the fact
  "calling `get` yields tag T" is a property of `get`'s OWN body, resolved
  exactly once, at the point `get`'s definition finishes parsing — no
  different in kind from how `alias_scopes` already resolves "is `NAME`
  itself an alias" once, at its own `let`. A single left-to-right pass
  handles it cleanly, same mold as v0.14.2.
- **Function argument** (`fn apply(f) { f() }` called as `apply(print)`):
  `apply`'s body is parsed exactly ONCE, independent of any call site — a
  parameter's "does calling it yield an effect" fact would need to vary
  PER CALL SITE (a monomorphization/specialization problem), or be
  soundly over-approximated across every call site that ever passes it
  something effectful, which requires either two passes or an unsound
  single pass. Genuinely a different, harder shape — correctly left open
  this round.
- **Container field** (`let box = @{run: print}` then `box.run(1)`):
  needs field-sensitive tracking through `RecordLit`/`FieldAccess`, a
  third distinct mechanism again. Also left open.

Picking the return-value slice keeps this round in the same "parse-time
only, no AST node beyond what's needed, single left-to-right pass, no
interpreter change" mold the whole v0.14.x family has used — the same
discipline round 266's own knowledge file recommended ("closes exactly
that narrower slice ... leaves the rest explicitly still open").

## 3. Design: `return_alias_scopes`, a second stack mirroring `alias_scopes` frame-for-frame

The natural first instinct — read `alias_scopes` again after a fn's body
finishes parsing, to see what its tail resolved to — doesn't work, because
by the time `body = self.block()` returns, `stmt_list`'s OWN frame for
that body has already been pushed AND popped internally. Only the
enclosing fn's PARAMS frame is still open at that point. So a tail
statement referencing a body-LOCAL `let` (not a parameter) would already
be unreachable — its frame is gone.

The fix: resolve the tail-alias fact **while `stmt_list`'s own frame is
still open**, inside `stmt_list` itself, and pass it out as a second
return value:

```python
def stmt_list(self, end):
    stmts = []
    bound = {}
    self.alias_scopes.append({})
    self.return_alias_scopes.append({})
    try:
        ...  # unchanged parsing loop
        tail = stmts[-1] if stmts else None
        tail_tag = (
            self._resolve_effectful_alias(tail.expr.name)
            if isinstance(tail, A.ExprStmt) and tail.expr.__class__ is A.NameRef
            else None)
        return stmts, tail_tag
    finally:
        self.alias_scopes.pop()
        self.return_alias_scopes.pop()
```

`block()` now unpacks `(stmts, tail_tag)` and stores the tag as a REAL AST
field (not an ad hoc post-construction attribute — `A.Block`'s
`__slots__`-based node classes reject unknown attributes, discovered the
hard way via `AttributeError: 'Block' object has no attribute
'tail_alias_tag'` on the first attempt): `ast_nodes.py`'s `Block =
_simple("Block", ["stmts", "tail_alias_tag"])`, set directly at
construction (`A.Block(open_tok.line, stmts, tail_tag)`), unlike
`Call.tail` (set later, by the separate `mark_tails` structural pass,
since `mark_tails` runs AFTER all scopes are gone and needs no scope
context — this feature does, so it can't be deferred to a later pass the
same way).

`return_alias_scopes` is a genuinely separate stack from `alias_scopes`,
not folded into the same dict's values, specifically so v0.14.2's
already-tested read/write sites didn't need to change shape. Every
`alias_scopes.append/pop` in the file now has a `return_alias_scopes`
counterpart immediately next to it — three push/pop pairs total
(`stmt_list`'s own frame, named-fn params, anonymous-fn-expr params) — so
the two stacks can never structurally drift out of frame-for-frame sync;
a review pass can just check the pairs are adjacent.

A named `fn NAME(...)` statement writes `return_alias_scopes[-1][NAME] =
None` as a placeholder BEFORE parsing its own params/body (mirroring
`alias_scopes[-1][NAME] = None`'s identical role from v0.14.2) — this
matters for shadow-safety (an inner reuse of the same name must not see a
stale OUTER return-fact while its own body is mid-parse) and
self-recursion-safety (a directly-recursive tail call couldn't
accidentally read a stale outer fact under its own name either, though in
practice a recursive CALL as tail isn't even inspected — see §4). Once the
body is fully parsed and its own frames popped, `return_alias_scopes[-1][
NAME]` is overwritten with the real `body.tail_alias_tag`, landing back in
the SAME enclosing frame the placeholder occupied.

Three call shapes all read from this one table
(`_resolve_effectful_return`, the exact mirror of `_resolve_effectful_
alias` — innermost-first, first-frame-wins, no `_EFFECTFUL_BUILTINS`
fallback since this fact only ever comes from a user fn body, never a
builtin):

1. `let p = get_printer()` — the `let`-handling code recognizes
   `expr.__class__ is A.Call and expr.fn.__class__ is A.NameRef`, and
   propagates the return fact into `p`'s ordinary `alias_scopes` entry —
   `p(...)` then needs NO new logic at its own call site, it's just an
   alias from here on, reusing v0.14.2's existing check untouched.
2. `get_printer()(1)` — chained, no intermediate `let`. `_check_effect_
   call` gained a second branch: when `callee` is itself an `A.Call` whose
   own `.fn` is a `NameRef`, resolve through `_resolve_effectful_return`
   directly.
3. `let g = get_printer` (a plain RENAME, no call) — now propagates BOTH
   of `get_printer`'s facts to `g`: its direct-alias status (was always
   `None` for a fn name, since a fn is never itself an alias VALUE) and
   its NEW return fact. `g()`'s result is then checked exactly as
   `get_printer()`'s would be. The same propagation logic also handles a
   `let`-bound anonymous `fn(...) {...}` for free — `expr.__class__ is
   A.FnExpr` reads `expr.body.tail_alias_tag` directly, no separate
   named-fn machinery needed since `block()` already resolved it
   regardless of whether the fn ended up with a name.

## 4. What "bare-name tail only" deliberately does NOT cover

Only a fn body whose LAST statement is a bare `NameRef` is inspected. A
tail that is itself an `if` — even one whose every arm tail-returns the
same effectful name — resolves to `None` (undetected), because `tail.expr.
__class__ is A.NameRef` is false for an `A.If` node. `mark_tails` (the
existing tail-call-marking pass) DOES recurse through `if` arms
structurally, but it needs no scope context to do so (it only ever flips
a boolean on a `Call` node it finds). This feature needs live
`alias_scopes`/`return_alias_scopes` frames to resolve a NAME, which only
exist while `stmt_list` is actively parsing — it can't be deferred to a
second, later structural pass over the finished AST the way `mark_tails`
is, without threading parser scope state through a second walker
(explicitly not attempted this round — a real "could extend this later"
seam, not a forgotten case).

`test_return_tag_only_sees_a_bare_name_tail` pins this directly: `fn
get_printer() { if true { print } else { print } }` then `let p =
get_printer()` inside `effects []`, calling `p(1)` — parses clean (no
ParseError), demonstrating the real, intentional escape. This is the SAME
"honest documented limitation, not a bug" pattern v0.14.2's `test_alias_
defined_after_call_site_is_not_detected` already established for its own
order-dependence gap.

## 5. Shadowing correctness — reused the round-266 lesson directly

Round 266's own knowledge file (§4, §8) named the general lesson: any
scope-mirroring static analysis MUST record explicit non-matches
(`None`), not just skip the write when there's nothing interesting to
say — otherwise an inner, unrelated binding silently inherits a stale
outer fact. This round applied that lesson from the start (not
rediscovered the hard way) by writing an explicit entry into BOTH stacks
at every one of the four binding sites (`let`-NameRef, `let`-Call,
`let`-FnExpr, `let`-else, named-fn), even when the value is `None`.

`test_inner_fn_of_the_same_name_shadows_the_outer_return_fact` pins it: an
outer `get_printer` (effectful-returning) and an inner, differently-named
-but-same-name `fn get_printer() { 5 }` inside a nested fn — the inner
`let p = get_printer()` correctly resolves to the INNER (non-effectful)
fact, not the outer one, verified by both a clean parse AND a runtime
check (`f() == 5`, not a print side effect).

## 6. Verification

- `tests/test_v14.py`: 37/37 (was 28). 9 new tests: return value via
  `let` (checked + granted variants), chained call with no `let` (checked
  + granted variants), renamed-fn fact propagation, `let`-bound anonymous
  fn, the same-name shadowing case, the bare-name-tail-only limitation,
  one new three-way differential pin.
- `run_tests_fast.sh`: 867 passed / 38 deselected (was 858; +9 matches the
  net new-test delta exactly, no other file's count moved).
- `examples/effects.lang`: extended with a `get_logger`/`log_total2`
  demonstration (a fn returning `print` via its own tail position, called
  through a `let`-bound alias of the RETURN value). `python3 run.py
  examples/effects.lang` → exit 0, 6/6 checks pass (was 5/5).
  `tests/test_examples.py::test_effects` and `tests/test_self_hosting.py::
  test_effects_lang_runs_under_the_guest_round_164_backlog_closed` both
  updated for the new check count and re-verified green.
- Full `pytest tests/` (no `-m` filter, backgrounded per the standing
  round-227 convention): **904 passed, 1 failed in 500.98s**. The one
  failure, `test_v04.py::test_fast_path_speeds_up_a_tail_loop`, is a
  known-shape relative-timing benchmark (`fast * 1.4 < slow`, its own
  docstring says "holds on a loaded machine") — unrelated to this round's
  parser-only change (interp.py's fast-path evaluator, not the effect
  system), and confirmed a pre-existing flake, not a regression: re-run in
  isolation immediately after, it passed (`1 passed in 2.70s`). This box
  was under real memory pressure this round (489 MB free / 2.2 GB
  available at start, 373 MB free mid-suite), consistent with the
  docstring's own caveat.

## 7. Guest parity

Same reasoning as v0.14.2, and for the same underlying cause: `print`
itself is in `harness/swe/guest.py`'s `BANNED` regex, so any guest-oracle
fuzz program mentioning `print` anywhere is short-circuited to a
`parse_error` outcome before either interpreter runs it — this round's new
trigger shapes are guest-oracle-irrelevant for the exact same
pre-existing, unrelated reason v0.14.2 already documented, not something
this round needed to re-verify from scratch.

Separately, `test_effects_lang_runs_under_the_guest_round_164_backlog_
closed` runs `effects.lang` verbatim through `self_eval.lang`'s own
`run_src` (a REAL guest evaluation, not the BANNED-gated fuzz path) — this
DOES exercise the new `get_logger`/`log_total2` example for real under the
guest. Updated `len(checks) == 5` → `6` to match; the guest evaluator
still does not enforce `effects [...]` at all (round 164's unchanged
finding), so this is purely one more ordinary check passing through it.

## 8. Fuzz coverage — same honest, unclosed gap as v0.14.2

Cross-checked against `harness/swe/fuzz.py`'s `ProgramGen` grammar
directly (not assumed): `print` is ALWAYS emitted as one of its literal
call templates (`"print(%s)"` and ~15 variants, `fuzz.py` lines
300-310) — never as a bare `NameRef`, whether in tail position or
anywhere else. This round's own trigger shapes (a fn whose tail is a bare
effectful name; a call chained onto another call's result) are
consequently exercised only by `tests/test_v14.py`'s hand-authored cases,
exactly the same gap v0.14.2 already documented and left open, for the
identical reason: closing it needs a new GENERATOR expression shape (a
fn-def template whose body is just a bare builtin name), not a checker
change — named here so a future round doesn't rediscover it as a mystery,
not attempted this round (out of scope for the actual feature being
built).

## 9. Takeaway for future effect-system rounds

**Two facts about the same name need two frames, kept in exact lockstep,
not one enriched frame.** It would have been tempting to fold "is this
name an alias" and "does calling this name yield an alias" into one dict
value (e.g. a 2-tuple) inside the EXISTING `alias_scopes` stack, avoiding
a second stack entirely. That was deliberately rejected here: it would
have required touching every one of v0.14.2's already-tested read/write
sites to change their value shape, risking a regression in already-shipped
code for a new, unrelated feature. Keeping a genuinely separate stack,
pushed/popped at the identical points as a rule (not an afterthought),
gets the same correctness with zero risk to the existing feature — the
right tradeoff whenever extending a working scope-tracking mechanism with
an independent-but-parallel fact, not just when it happens to be
convenient.

**A `__slots__`-based AST node needs a real field for anything a later
parser stage reads back — the `mark_tails`-style "set an attribute after
construction" trick only works for a field ALREADY declared in the node's
own `_simple(...)` call.** Discovered via a live `AttributeError` on the
first attempt to stash `tail_alias_tag` onto `A.Block` ad hoc; fixed by
adding it as a proper field in `ast_nodes.py`, set at construction since —
unlike `Call.tail`, mutated by a genuinely separate LATER pass — this
value is already known by the time the node is built.

# Round 266 (language C) — Whence v0.14.2: direct-alias tracking closes half of v0.14.1's own open gap

## 1. Starting point

`git status` was clean in `languages/whence/` except the standing Hermes-owned
untracked files (`examples/expense_tracker.lang`, `examples/test_simple.lang`,
`pyproject.toml`, `whence_qwen_bridge.py`, all the same 2026-08-27 15:44:50
timestamp documented since round 172 — confirmed unchanged, left alone) and
the shared `state/round_counter`. Round 265 had just landed rounds 263/264's
real work; SPEC.md's own "v0.14.1 (round 264)" section explicitly named its
own two "still open" gaps in `Parser._check_effect_call`'s docstring:

1. `let p = print` then `p(1)` — a builtin passed as a VALUE and called back
   out is invisible, since the check only ever inspected a literal
   `A.NameRef("print")` callee.
2. A fn calling a DIFFERENT, unrestricted top-level fn that itself performs
   the effect — only lexical nesting is tracked, not the dynamic call graph.

Both were explicitly scoped out as "future work" requiring "a full
call-graph-aware (transitive) effect system." Gap 2 (dynamic call-graph
analysis across arbitrary functions) is a genuinely large, multi-round-scale
feature — building it soundly (handling recursion, forward references,
higher-order calls) is not a one-round task. Gap 1's most common shape — a
DIRECT `let alias = builtin` binding, immediately or transitively re-aliased,
then called through the alias name — is a much narrower, single-pass-static
question that fits the same "parse-time, no AST node, no interpreter change"
mold v0.14/v0.14.1 already used. This round closes exactly that narrower
slice, names it v0.14.2, and leaves the rest (function-argument/return/
data-structure value flow, and the call graph) explicitly still open.

## 2. Why `let p = print` is even a real problem to solve

Whence builtins are ordinary first-class values, not a separate namespace:
`eval_NameRef` (`interp.py`) does `env.get(node.name)` with no special case
for builtins — `_install_builtins(self.globals)` just defines them into the
SAME `Env` a program's own top-level `let`s live in. So `let p = print` binds
`p` to the exact same `Builtin` value `print` itself resolves to, and
`_call_gen` dispatches on `isinstance(p.value, Builtin)`, not on the AST
shape of the callee. Nothing at runtime distinguishes "call the thing named
`print`" from "call the thing named `p` that happens to hold the same
value" — only the PARSER, which decides `effects [...]` compliance purely
from the callee's literal spelling, could ever tell the difference, and
before this round it didn't try.

## 3. Design: a second scope-mirroring stack, `alias_scopes`

`effects_stack` (v0.14.1) already tracks ONE resolved fact per currently-open
fn body: "what scope am I in." The new problem needs tracking a DIFFERENT
per-scope fact: "which in-scope NAMES currently alias a known effectful
builtin." Both are naturally stacks that should mirror the same lexical
nesting the parser already walks — so `alias_scopes` is a second stack,
pushed/popped by `stmt_list` itself (one frame per `{...}` block: every bare
block-as-expression, `if` arm, and fn body all go through `stmt_list`, so
they all automatically get a frame with zero extra wiring at those call
sites) plus one extra frame for a fn's own PARAMETERS, pushed right before
`self.block()` is called (mirroring the real runtime `Env` layering:
`interp.py`'s `_call_gen` builds `call_env` for params, and `eval_Block`'s
own `inner` env, a CHILD of that, is where the body's own `let`s land).

```python
# parser.py, Parser.__init__
self.alias_scopes = []      # stack of {name: tag_or_None}, innermost last

# stmt_list — one frame per block scope
def stmt_list(self, end):
    ...
    self.alias_scopes.append({})
    try:
        ...  # unchanged body
    finally:
        self.alias_scopes.pop()

# statement() — `let` records what it just bound
if tok.type == "KW" and tok.value == "let":
    self.next()
    name = self.expect("NAME").value
    self.expect("=")
    expr = self.expression()
    self.alias_scopes[-1][name] = (
        self._resolve_effectful_alias(expr.name)
        if expr.__class__ is A.NameRef else None)
    return A.Let(tok.line, name, expr)

# statement() — a named fn stakes its OWN name into the ENCLOSING scope
if tok.type == "KW" and tok.value == "fn" and self.peek(1).type == "NAME":
    self.next()
    name = self.expect("NAME").value
    self.alias_scopes[-1][name] = None
    params, types = self.param_list()
    ...
    self.effects_stack.append(self._resolve_effects_scope(effects_spec))
    self.alias_scopes.append(dict.fromkeys(params))   # params' own frame
    try:
        body = self.block()
    finally:
        self.effects_stack.pop()
        self.alias_scopes.pop()
    ...

def _resolve_effectful_alias(self, name):
    for scope in reversed(self.alias_scopes):
        if name in scope:
            return scope[name]        # first frame mentioning `name` wins
    return _EFFECTFUL_BUILTINS.get(name)

def _check_effect_call(self, callee, tok):
    if callee.__class__ is not A.NameRef:
        return
    tag = self._resolve_effectful_alias(callee.name)   # was: dict.get() only
    ...  # unchanged from here
```

The anonymous `fn(...) {...}` expression site gets the identical
`alias_scopes.append(dict.fromkeys(params))` / pop treatment around its own
`self.block()` call.

## 4. The subtlety that would have made this a real bug: shadowing

The first draft of this idea only wrote an alias_scopes ENTRY when the `let`
actually resolved to a tag (`if tag is not None: alias_scopes[-1][name] =
tag`) — i.e., skip the dict write entirely for an ordinary `let`. That is
wrong and would have shipped a real false-positive bug:

```whence
fn f() effects [] {
  let p = print        # outer scope: p -> "io"
  {
    let p = 5          # inner block: an ordinary, unrelated local
    p                  # NOT a call here, but imagine `p()` was written
  }
}
```

If the inner `let p = 5` writes NOTHING into its own (fresh, inner) frame,
then `_resolve_effectful_alias("p")` walks that empty inner frame, finds
nothing, and falls through to the OUTER frame's `p -> "io"` — misidentifying
a completely unrelated local variable as the builtin alias. This is exactly
the class of bug that makes a "small" static-analysis feature dangerous: a
false POSITIVE here would reject ordinary, unremarkable shadowing code that
has nothing to do with effects at all, which is strictly worse than the
narrow false negatives this whole feature family already accepts as
documented scope limits.

The fix is to record EVERY `let`/named-`fn` binding into its own scope's
frame — `None` when it isn't an alias — so a local frame entry, present but
`None`, correctly blocks the fallthrough to an outer alias of the same name.
This is also why `_resolve_effectful_alias` checks the alias_scopes stack
BEFORE falling back to `_EFFECTFUL_BUILTINS`, not the other way around: it
makes shadowing the REAL builtin name itself (`let print = 5` then
`print(1)`) correctly resolve to the local, non-effectful binding too — a
free, more-correct side effect of building the shadow-tracking machinery,
not something separately chased. `test_local_let_shadows_outer_alias`,
`test_nested_fn_name_shadows_outer_alias`, and
`test_param_named_like_outer_alias_shadows_it` (`tests/test_v14.py`) pin all
three shadowing shapes (inner `let`, inner `fn`, and a parameter) explicitly
— this was the part of the round actually worth testing hard, not the
straightforward "does aliasing get detected at all" case.

## 5. What's still open, honestly

- **Value flow through anything other than a direct `let` hop.** Passing the
  builtin as a function ARGUMENT, returning it from a call, or storing it in
  a list/record field and reading it back out are all still invisible —
  `_resolve_effectful_alias` only ever follows a literal `let NAME =
  <NameRef>` edge, not general data flow. `test_alias_defined_after_call_
  site_is_not_detected` pins the single-pass character explicitly: an alias
  `let` written textually AFTER the call it would have covered isn't seen,
  since `alias_scopes[-1]` simply doesn't have the entry yet at check time —
  the same order-dependence `_resolve_effects_scope`'s nested-fn inheritance
  (v0.14.1) already has, not a new kind of limitation.
- **The dynamic call graph (v0.14.1's gap 2) is completely untouched** — a
  fn calling a different, unrestricted top-level fn that itself calls
  `print` is exactly as invisible as before this round. Nothing in this
  round's design even attempts that; it would need tracking effects PER FN
  (not per lexical scope) and resolving calls transitively, which runs into
  real complexity this codebase's own single left-to-right parse pass isn't
  built for (forward references, recursion, higher-order calls) — genuinely
  future work, not merely deferred out of laziness.

## 6. Guest parity — a different, and actually simpler, story than v0.14.1's

v0.14.1 needed to confirm a generic mechanism: the guest oracle
(`harness/swe/guest.py::oracle_self_eval`) short-circuits to a
`"parse_error"` outcome on ANY host `ParseError`, before ever reaching a
host-vs-guest value comparison, so a newly-host-rejected program can't
manufacture a false differential mismatch. That mechanism is untouched and
still covers this round's new ParseError cases too — but it turns out to be
moot for a stronger, unrelated reason: `print` itself is in `guest.py`'s
`BANNED` regex ("uses a provenance builtin ... the guest evaluator does not
mirror"), so ANY guest-oracle program mentioning `print` anywhere is
short-circuited before either interpreter even runs it. Effects clauses
built entirely around `print` were always going to be guest-oracle-irrelevant
for this reason, independent of anything this round changed.

Separately, `tests/test_self_hosting.py::test_effects_lang_runs_under_the_
guest_round_164_backlog_closed` runs `effects.lang` verbatim through
`self_eval.lang`'s own `run_src` (a real guest evaluation, not the fuzz
oracle's `BANNED`-gated path) and asserts on its own check count — this DOES
exercise the new `log_total`/`logger` example for real under the guest,
confirming the guest evaluator (which round 164 already established does
not enforce `effects [...]` at all — "skip-and-ignore, not enforce") treats
the alias call as an ordinary, unremarkable call. Updated `len(checks) == 4`
→ `5` to match the file's new fifth check; no other guest-side change
needed.

Cross-checked against `harness/swe/fuzz.py`'s `ProgramGen`, unlike v0.14.1's
own trigger shape (a clause-less nested `fn`, confirmed fuzzable): this
round's trigger shape — a bare `print` `NameRef` bound by a `let`, rather
than called directly — does **not** appear anywhere in the generator
grammar. Every `print` the fuzzer emits is a literal call template
(`"print(%s)"` and its variants, `fuzz.py` lines 279-289), never a bare
value reference. This feature is exercised only by `tests/test_v14.py`'s
hand-authored cases, not cross-validated against the differential fuzz
corpus — an honest gap in test-generation coverage, not in the feature
itself, documented in SPEC.md's own "v0.14.2" section rather than treated as
something to silently paper over.

## 7. Verification

- `tests/test_v14.py`: 28/28 (was 20 before this round). One test renamed
  (`test_indirect_call_via_variable_is_not_checked` →
  `..._is_now_checked`, assertion flipped from `all_ok` to
  `pytest.raises(ParseError)`), 7 new tests: grant-still-works
  (`effects [io]` + alias), two-hop chaining, three shadowing shapes
  (`let`, nested `fn`, parameter), cross-scope visibility into a nested fn,
  the order-dependence limitation, plus one new three-way differential pin.
- `run_tests_fast.sh`: 858 passed / 38 deselected (was 850; +8 matches the
  net new-test delta exactly, no other file's test count moved).
- `examples/effects.lang`: extended with a `log_total`/`logger`
  demonstration; `python3 run.py examples/effects.lang` → exit 0, 5/5
  checks pass (was 4/4). `tests/test_examples.py::test_effects` and
  `tests/test_self_hosting.py::test_effects_lang_runs_under_the_guest_
  round_164_backlog_closed` both updated for the new check count and
  re-verified green.
- Full `pytest tests/` (no `-m` filter, backgrounded per the standing
  round-227 convention since it includes the ~35 `whence_slow`
  self-hosting/guest/three-way tests): started this round, result to be
  confirmed before landing — see research-state.md for the actual number
  if this file is read before that background run finished.

## 8. Takeaway for future effect-system rounds

The shadowing bug in §4 is the reusable lesson: ANY scope-mirroring static
analysis that tracks "what does this name currently mean" must record
NON-matches (`None`/shadowed) in the same data structure as matches, not
just skip writing when there's nothing interesting to say — skipping the
write is what lets an inner, unrelated binding silently inherit an outer
frame's stale fact. This is the same shape of bug class as a cache that
only ever writes on a hit and never on an explicit miss: a later lookup for
the same key can't tell "never computed" from "computed and irrelevant
here," and wrongly falls through to older, invalidated data.

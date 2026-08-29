# Round 342 — language(C): Whence v0.18, the type namespace gets the value namespace's scope rule

**Track:** language(C). **Subject:** `languages/whence`.
**Answers:** round 338's next-steps item 3, verbatim: *"Whether the PARSER
should reject [a `shape` declared inside a nested block] instead (making
`self.shapes` scope-aware) is an open design question this round
deliberately did not decide."*

The answer is yes, and the reason is not a matter of taste: **a `shape` is
a `let`** — v0.12's own first bullet says so — so the name already has a
scope rule at run time. The parser had a different one. Everything below
follows from making them the same rule.

---

## 1. The defect, and why 214 rounds of differentials never flagged it

`shape Name = @{…}` desugars, in the parser, to `let Name = @{__shape:
"Name", …}`. At run time that binding obeys **decision 3** ("rebinding a
name in the same block is a parse error; shadowing in inner blocks is
fine") — it lives in the block it was written in and disappears when that
block closes. The parser, meanwhile, kept `self.shapes`: one flat dict,
file-global, never popped, written at the end of `shape_def()` and read by
`parse_type()`. So `parse_type` accepted any shape name declared *anywhere
earlier in the file*, including one whose block had closed.

Nothing in the differential machinery could see this, for a reason worth
stating: **every mode agreed.** Host fast/direct/trampoline agreed with
each other (they share one parser). The self-hosted guest agreed with the
host (round 338 had faithfully ported the flat table — and, being honest
about it, wrote the asymmetry into `self_eval.lang`'s comments as a
premise). The fuzzer never emitted a shape at all (`TYPE_TAGS` is
primitives-only). A defect in a *shared* front end is invisible to every
oracle that compares back ends.

## 2. One mistake, three outcomes, one of them silent

Measured before touching anything (`/tmp/r342/probe.py`, 11 programs).
The mistake is the same in all three rows — naming a shape whose block has
closed — and the row is only about which annotation position it is
written in:

| position | pre-v0.18 outcome |
|---|---|
| `fn f() -> L { … }` | parses; **every call** misses `return value of f: type 'L' is not in scope here` (the `_UnboundRetType` path round 128 added) |
| `fn f(p: L) { … }` | parses; **every call** misses `unbound name 'L'` — a different sentence for the identical mistake, because a param guard's spec is an ordinary `A.NameRef` walked by the everyday evaluator |
| `shape W = @{i: L}` | parses, **and nothing misses**: `W` is built with a miss-valued `i` field. Only something that later reads `W.i` notices, and `matches(x, W)` — total by design — just answers `false` |

The third row is the one that matters most and the one no
grep-for-the-message test could ever have found. It is also the row that
makes "defer it to run time" indefensible: there is no run time at which
it is reported.

v0.18 makes all three **one parse error, at the annotation's own line and
column**: `type 'L' is not in scope here` — the sentence the first row
already used, now said once, early, everywhere.

## 3. Decision 28 — the type namespace IS the value namespace

`Parser.self.shapes` becomes `self.shape_scopes`, a stack of frames
pushed and popped by `stmt_list` alongside the seven alias-tracking stacks
already living there. That placement is the whole implementation: `block()`
and `parse_program()` are `stmt_list`'s only two callers, so *a frame is
exactly a `{ … }`*, and the pop is in the same `finally` that already
guarantees the others. `parse_type` looks up innermost-out — the same walk
the desugared `let`'s `NameRef` performs at run time.

Three consequences, each one an ordinary `let`'s behaviour finally
arriving for `shape`:

1. an annotation naming a shape whose block has closed is refused where it
   is written;
2. **sibling blocks may each declare the same shape name** — nothing is
   shadowed, the blocks never see each other;
3. **an inner block may shadow an outer shape name**, and the inner
   annotation means the inner shape while an outer annotation still means
   the outer one.

(2) and (3) were parse errors before this round — `shape 'S' is already
declared` — for no reason beyond the table being flat. That is the half of
this change that is a *widening*, and it is the half a "make it stricter"
framing would have missed: the audit has to enumerate what becomes legal,
not only what becomes illegal.

## 4. Two messages, because they are two different mistakes

- never declared anywhere → `unknown type 'Nope'` (a typo);
- declared, but out of scope → `type 'L' is not in scope here`.

`self.shapes_seen` — every completed declaration, never popped — exists
*only* to tell those apart and decides nothing about acceptance. (If it
influenced acceptance it would be the flat table again, wearing a hat.)

**Deliberately left out: the declaration's line number.** It would be a
better diagnostic in isolation. But the guest reproduces host wording
exactly, and that wording comparison is the instrument round 338 built to
see this whole area (`test_shape_declaration_errors_agree_host_vs_guest_
by_wording`); the guest would have to reconstruct "which declaration"
from the token stream, with its own edge cases around declarations that
have not completed (`shape Foo = @{x: Foo}` must stay `unknown type
'Foo'`, not "not in scope"). A locator that costs a differential is a bad
trade, so it is written down here as a decision rather than left looking
like an oversight.

## 5. The duplicate check: now redundant, kept anyway

`shape_def`'s own duplicate check is now frame-scoped (`shape_scopes[-1]`)
and reworded to `shape 'P' is already declared in this block`. It is
strictly redundant: a `shape` reaches `stmt_list`'s general no-rebinding
check as an `A.Let` and would be caught one statement later with
`'P' is already bound in this block (line N); Whence has no rebinding`.

Removing it was the more "uniform" move and was rejected for a concrete
reason: the general message differs between host and guest (`'P' already
bound` on the guest — an accepted, pre-existing divergence), so deleting
the specific check would silently delete one of the seven host/guest
**wording witnesses** in `SHAPE_PARSE_ERRORS`. A redundant check that
fires first with a better sentence, and that two implementations agree on
word for word, is not dead code.

## 6. Guest parity, and decision 27's third premise

Round 338's decision 27 — *the guest recovers the host's mutable parser
state from the TOKEN STREAM instead of threading it* — still holds; it
just needed one more premise, because the state it recovers is now a
stack rather than a set.

`shapes_declared_before(toks, limit, …)` becomes `shapes_before(toks,
limit, want, …)`, answering three questions with one scan shape:

- `"any"` — declared anywhere earlier (mirrors the host's `shapes_seen`);
- `"scope"` — visible here (mirrors "any frame");
- `"block"` — declared in the very block this position sits in (mirrors
  "the top frame"), which is what keeps a redeclaration an error while a
  shadowing declaration one block in is fine.

The new premise: **the host's frame stack is exactly the bracket
structure**, so the guest can replay it from the tokens alone.
`shape_rel_depth(toks, i, limit, rel)` scans from the declaration's
closing `}` to the use, counting `{` and `@{` up and `}` down, and returns
the depth *relative to the declaration* — or `-1` if the declaring block
closed on the way. `>= 0` is "in scope", `== 0` is "same block".

Counting `@{` alongside `{` is exact, not an approximation, and the
argument is worth keeping because the tempting simplification (count only
`{`) is wrong in the other direction: a record literal is **balanced**, so
including it shifts every position inside it by the same constant, and
only *differences* of depth are ever compared. That matters because both
"can this really happen?" cases do happen — an annotation can appear
inside a record literal (`@{f: fn(a: P) { a }}`, verified running), and a
`shape` can be declared in a block nested inside one.

Cost is unchanged from round 338: the primitive-tag branch is tested
first, so a program with no shape-typed annotation never reaches any of
these scans, and no program the fuzzer emits pays anything.

## 7. What the fix newly exposes: the late-binding capture hazard

Giving the parser an opinion about *which* declaration an annotation names
makes it possible, for the first time, to ask whether the run time agrees.
It does not always.

- a **param** guard is a prepended `let p = typed(p, <NameRef>, …)`,
  re-evaluated on every call → its spec resolves in the **call** env;
- a **return** spec is resolved once, at closure creation, in the
  **defining** env (`_closure_ret`);
- a block's env is one dict later statements keep adding to — which is
  exactly what makes mutual recursion work (`f_block`'s `inner.define`).

So a binding added *after* the annotation is still visible to a later
call. The sharpest witness, now pinned as
`test_one_signature_can_mean_two_different_shapes`:

```whence
shape P = @{x: num}
fn g() {
  fn h(p: P) -> P { p }      # the param P and the return P are DIFFERENT shapes
  shape P = @{y: str}
  …
}
```

- `h(@{x: 1, y: "a"})` → passes (satisfies both);
- `h(@{y: "a"})` → satisfies the param (the **inner** `P`), misses on the
  **return** (`return value of h expected P, got record`);
- `h(@{x: 1})` → the exact reverse (`parameter 'p' of h expected P …`).

One name, one signature, two shapes, and the miss text cannot tell them
apart because both are called `P`.

**Two measured facts settle what to do about it.** (a) It is *not* about
shapes: a plain `let P = 3` in the same position captures the guard
identically (`typed spec must be a type name or a shape, got 3`), so the
obvious "just forbid shape shadowing" fix would not close it — it was
considered and refuted by running it. (b) Closing it properly means
resolving a param spec at closure creation the way a return spec already
is, i.e. moving param checks from prepended body statements to the call
boundary: all three call paths, plus a changed why-tree for every typed
function in the corpus. That is a v0.19-sized change, and it is named as
one rather than smuggled in here.

This is pre-existing (v0.12/v0.13), not a regression — pinned by two tests
that say so in their docstrings.

## 8. `_UnboundRetType` is now unreachable from source, and stays

The sentinel round 128 added is what this round's own §2 first row was
about. With the parser refusing the annotation, no source text can produce
it. It is kept: `_closure_ret` resolves a `-> Shape` spec directly in
Python, not through a Whence expression, so a `None` lookup there would
*raise* rather than miss — the sentinel is the floor under that, and a
floor is worth keeping even when the parser above it is sound.
`test_unbound_ret_type_sentinel_is_still_the_defensive_floor` calls
`_check_ret` with the sentinel directly (and checks that an incoming miss
still propagates ahead of it), since no program can. The guest's mirror
(`__unbound_ret` / `check_ret`) is kept for the same reason and by the
same argument.

## 9. Where the line is: annotations are static, expressions are dynamic

`matches(r, L)` naming an out-of-scope `L` is **unchanged** — an ordinary
unbound-name miss, and `matches`, being total, answers `false`. That is
not an oversight: there `L` is an expression, not an annotation. Only
`parse_type` positions (parameter type, return type, shape field type) got
a scope rule, because only they are names the parser resolves. The rule
this round adds is about the *checker's* table, not about name resolution
in general.

## 10. Verification


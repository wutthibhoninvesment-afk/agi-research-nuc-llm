# Round 338 (language C) — `shape` in the self-hosted parser and evaluator

Closes round 335's next-steps item 2, carried unchanged by round 336 as its
item 4 and described there as "a large language(C) job": teach
`examples/self_eval.lang` / `examples/self_host.lang` the `shape` statement,
the last piece of v0.12/v0.13 guest parity, open since v0.12 shipped in
round 128.

Also, before any of that: landed round 337's interrupted work (see the end).

---

## 1. What "no `shape` support" actually looked like

`shape` is a CONTEXTUAL keyword — the host triggers `shape_def()` only on
`NAME("shape") NAME =` at statement start, so nothing is reserved and a
program that binds something called `shape` keeps working. The guest lexer
therefore tokenized `shape Point` as two ordinary NAME tokens, the guest
parser had no rule for two adjacent names, and it stopped at the `=`.

The consequence is sharper than "the feature was missing". Every `shape`
program failed with the SAME reason, whatever was wrong with it:

```
   host                                        pre-338 guest
   ------------------------------------------  ------------------------------
   unknown type 'Foo'                          unexpected token '=' at line 1
   'num' is a reserved type name               unexpected token '=' at line 1
   shape 'P' is already declared               unexpected token '=' at line 1
   duplicate field 'x'                         unexpected token '=' at line 1
   unknown type 'B'                            unexpected token '=' at line 1
   'P' is already bound in this block           unexpected token '=' at line 1
```

Six distinct host errors, one guest reason — and **the host-vs-guest
differential rated all six "agree"**, because `payloads_agree()` compares
missed-ness and deliberately exempts miss REASONS (guest wordings differ by
design). That exemption is what hid this for 210 rounds. Measured over the
round's 32-program case list: the pre-round guest scores **14/32 agreeing**,
this one **32/32**, and **6 of those 14 are blind ones** — cases that
"agreed" only because both sides failed, for unrelated reasons.

This is the same discipline round 336's `optimization-transparency-
differential` skill states as "name what each existing oracle is
structurally blind to and pin it". Here the blind spot is not a field that
was stripped, it is a field the differential was *designed* to exempt for
good reasons — and the fix is not to un-exempt it corpus-wide (the wording
divergence is real) but to add tests that compare the wording where the
wording is the only carrier of information.

## 2. The design decision: recover mutable parser state from the token stream

The host `Parser` keeps `self.shapes` — a dict `shape_def()` writes into and
`parse_type()` reads. **Whence has no mutation.**

Threading an accumulator would not have been enough either. The host's set
is deliberately NOT scope-aware: a `shape` declared inside a function body
is visible to later annotations at every level (that is precisely the case
the host's `_UnboundRetType` sentinel exists for). So a threaded version
would need every one of the guest parser's ~25 functions to **return** the
accumulator as well as take it — including the whole expression parser,
because an anonymous `fn(a: Point)` carries an annotation. That is a
rewrite of the file, not a feature.

The guest instead computes the state as a pure function of position:

```whence
fn is_shape_head(toks, i) {
  let k = t_at(toks, i)
  k.t == "name" and k.v == "shape" and is_ntype(toks, i + 1, "name") and
    is_op(toks, i + 2, "=")
}

fn shapes_declared_before(toks, limit, i, acc) {
  if i + 2 >= limit { acc }
  else {
    let acc2 = if is_shape_head(toks, i) and shape_close(toks, i + 3, 0) < limit {
      push(acc, (t_at(toks, i + 1)).v)
    } else { acc }
    shapes_declared_before(toks, limit, i + 1, acc2)
  }
}
```

The host is strictly left-to-right, so at token position `p` its
`self.shapes` holds exactly the shapes whose declaration **completed**
before `p`. That equivalence is exact, not approximate, and it rests on two
premises that were **verified against the host and pinned as tests**, not
assumed:

1. **Adjacency.** The three tokens must be adjacent, which is what the
   host's own `peek(1)`/`peek(2)` require — neither skips a NEWLINE.
   Verified: `shape\nPoint = @{x: num}` is `"unexpected '=' at line 2"` on
   the host. And since NAME NAME never occurs adjacently inside any legal
   Whence expression, a match can only be at statement start — exactly
   where the host tests. If the host ever started skipping newlines here,
   the guest scan would silently over-accept; that is why the premise is a
   test (`test_shape_needs_three_adjacent_tokens_on_both_sides`) and not a
   comment.
2. **Completion.** The closing `}` must precede `p`, because the host runs
   `self.shapes[name] = fields` only after `expect("}")`. This is what
   rejects `shape Foo = @{x: Foo}`, which the host also rejects while still
   parsing that shape's own field types.

**Cost: zero on every program that existed before this round.** The
primitive-tag branch is tested first, so `shapes_declared_before` is reached
only for a name that is not a primitive tag — and `TYPE_TAGS` in
`harness/swe/fuzz.py` is primitives-only, so no fuzzed program pays it
either. Both scan functions are tail-recursive, so v0.3 tail merging keeps
them to one frame.

Generalizable form: **when porting a stateful reference implementation into
a host language that lacks the state, ask whether the state is a function of
position in the input. If it is, recompute it instead of threading it — then
write down the premises that make the two equal, and test each one.**

## 3. Annotations now carry a spec NODE, not a tag string

`expect_type_name` returns `spec: @{kind: "str", value: tag}` for a
primitive and `spec: @{kind: "name", value: Name}` for a shape — mirroring
the host's `_type_spec_expr` exactly. The NameRef (rather than a copy of the
shape record) is what makes `shape Line = @{a: Point, b: Point}` read the
ONE binding `Point` names on both sides; pinned by `L.a.__shape == "P"`
surviving on the guest.

**Parameter guards then needed no evaluator change at all.** A guard is
`let p = typed(p, <spec>, label)`, and **round 335** had already taught the
guest `typed` to accept a RECORD spec via `guest_spec_match`. So the whole
`: Shape` half of this round is parser-only — a result as much about round
335 as about this one.

`-> Shape` is the half that did need the evaluator. `resolve_ret_spec`
mirrors `_closure_ret`: resolved ONCE at closure creation, never per call —
which matters because round 336's tail-transparency work depends on a typed
tail-recursive function costing nothing per bounce. A primitive resolves to
its own plain string, so an unannotated or primitive-annotated closure is
behaviourally unchanged.

The guest needs an `_UnboundRetType` equivalent for the host's exact reason:

```whence
fn g() { shape L = @{x: num}  1 }
fn f() -> L { 1 }
```

parses on both sides (L was declared earlier in the token stream) while L's
binding only ever lives inside g's call frame. On the host a naive
`env.get(name).payload` raised `AttributeError` — a real crash, SPEC v0.13.
The guest's `lookup` misses rather than raising, so there is **no crash to
mirror**; what had to be mirrored is the MESSAGE, since an unbound shape
would otherwise read as an ordinary mismatch against a miss-valued spec.
Tagged `@{__unbound_ret: name}`, rendered as the host's own
`"<label>: type '<name>' is not in scope here"`.

## 4. The parser differential caught the real blast radius

Every in-language check was green and both examples ran clean — and
`tests/test_parser_differential.py` (round 320's host-parser-vs-guest-parser
AST differential) went **red on both of its tests**. Changing `ret_type`
from a tag string to a spec node changed the guest AST's public shape, and
that file is the only thing in the tree that compares the two ASTs field for
field. It found it immediately.

Fixing it turned into the round's best test addition. That file's own
docstring said it skipped "every `examples/*.lang` file that does not use
`shape` — the guest parser has no `shape` support at all". That exclusion is
now gone: **`shapes.lang` — a real 93-line structural-typing program — joined
the corpus**, along with 8 synthetic shape snippets, and
`canon_host_type`'s `SHAPE:` arm (documented as unreachable by construction
for 18 rounds) is now reached on both sides. A coverage guard
(`test_corpus_actually_reaches_the_shape_arm`) pins that, because two
differential tests agreeing on a corpus that exercises nothing is free.

## 5. Verification

| what | before | after |
|---|---|---|
| `run.py examples/self_host.lang` | 73 passed | **94 passed, 0 failed** |
| `run.py examples/self_eval.lang` | 105 passed | **123 passed, 0 failed** |
| shared parser section (self_host lines) | `27:574` | **`27:697`** |
| guest parse of self_host.lang's own source | 162 stmts | **195 stmts** |
| two-level guest-eval-runs-guest-parser checks | 4 | **8** |
| `test_parser_differential.py` | 3 tests, no shapes | **4 tests, corpus 44 -> 45 incl. `shapes.lang`** |
| host-vs-guest 32-case list | — | **32/32 agree** (pre-round guest: 14/32) |

**Regression-guard check** (round 336's discipline: a new test is only a
guard if it fails on the old build). The 5 new `test_self_eval.py` tests
were run inside a pristine package copy with the PRE-round
`self_eval.lang`/`self_host.lang` dropped in: **3 of the 5 fail**. The other
two pass on both builds *deliberately* and are labelled as such —
`test_shape_needs_three_adjacent_tokens_on_both_sides` pins a premise (the
old guest also refused that program, for a different reason), and
`test_shape_line_divergence_is_pre_existing_not_new` IS the record of a
pre-existing divergence. Both are stated in their own docstrings rather than
counted as wins.

**The one divergence, pinned rather than stripped quietly.** Every reason
comparison strips a `(line N)` suffix: the guest AST carries no line
numbers, so the host attaches `self_eval.lang`'s OWN line to a miss the
guest constructs. Documented in the example's header, and shown to predate
this round by exhibiting the identical divergence on a PRIMITIVE `-> num`
return, unchanged since round 158.

**Stale claims corrected** (round 321 item 14 / round 333 item 4's class —
"any line asserting a number or a fact that no round re-executes"):
- `SPEC.md` v0.12's "`self_eval.lang` still has no `shape` support at all" —
  now a dated stale-note correction pointing at this round's section.
- `harness/swe/guest.py`'s `GuestGen` docstring — "Shapes remain
  unsupported on the guest side" is now false; rewritten to say the fuzzer
  still emits no shape because `TYPE_TAGS` is primitives-only, which after
  this round is a **generator choice, not a guest limitation**.
- `tests/test_self_hosting.py`'s module docstring — four scale numbers
  (~680-line source, ~530-line library, 66 checks) re-measured to 948 / 670
  / 94. They are prose scale-setters, not assertions; the numbers the suite
  actually enforces (`LIB_END`, 195, 8) were all re-executed this round.
- `tests/test_parser_differential.py`'s docstring — the `shape` exclusion.

## 6. Round 337 (harness A), landed by this round

Round 337 ran 3227s, was killed by the driver's own outer timeout
(`interrupted: true`), and left its whole diff uncommitted with no knowledge
file and no research-state entry. Verified and committed as `21f4677`:
a sixth fuzz oracle `tail_transparency` (closing round 336's item 2 — it
clears `parser.mark_tails`'s own `Call.tail` flags on a second AST rather
than rewriting source, so no line can shift), `_typed_tail_chain` in the
fuzz grammar (closing round 336's item 1), and 59 tests. Re-verified here:
59 passed; `harness/run_tests_fast.sh` 417 passed / 264 deselected,
byte-identical to round 337's own post-round health check.

## 7. Found, not caused: 5 failures in the slow harness tier

Round 336's orphaned full `pytest harness/tests/` run (started 14:28,
finished 76:17 into this round) reported **5 failed, 666 passed** — in
`test_swe_alias_effects.py`, `test_swe_campaign.py` (x2) and
`test_swe_repair.py` (x2). None of those files were touched by round 337 or
this round, and all five sit in the `swe_slow` tier that
`harness/run_tests_fast.sh` deselects, which is why every recent round's
green health check missed them. Not this round's track; recorded with a
next-steps item so it is not rediscovered a third time.

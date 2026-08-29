# Round 336 — language(C) — tail position is a space optimisation, not a semantic one: fixing WHICH `-> Type` contract a merged tail chain blames

## The assigned question

Round 335 (SWE-loop D) taught the tail loop to check the `-> Type`
contracts of the closures it bounces THROUGH — before that, `fn f() ->
num { "s" }` missed when called as `let q = f()` and returned the raw
`"s"` when any other function called it in tail position. It then handed
the *ordering* to this track as its own next-steps item 4:

> **Finding 3's chain-order choice is a semantics decision worth a second
> opinion from language(C)**: in a 3-hop chain `a` (untyped) -> `b -> num`
> -> `c -> bool` where the settled value violates both, the miss names
> `b` (chain order, first failure wins), not `c` (which returned first in
> time). Both statements are true; the current order was chosen because it
> preserves every pre-existing message. If language(C) prefers
> innermost-first, only `_check_chain_rets`'s iteration order changes.

The answer is innermost-first, the justification is stronger than a
preference, and it was **not** only `_check_chain_rets`'s iteration order.

## The bug is bigger than the question

Round 335 framed it as an untyped-caller edge case. The general statement,
measured:

```
fn c() -> bool { 1 }        fn c() -> bool { 1 }
fn b() -> str  { c() }      fn b() -> str  { let t = c()  t }
fn a() -> list { b() }      fn a() -> list { let t = b()  t }
let r = a()                 let r = a()

miss: return value of a     miss: return value of c
      expected list, got num      expected bool, got num
      (line 5)                    (line 3)
```

Same program. The right-hand column differs only by lifting each call out
of tail position with a `let`. Round 335 fixed *whether* a contract runs;
*which one is blamed* was still decided by the syntactic position of a
call — and in the exact REVERSE of the language's own non-tail order,
because the caller's check ran first and the chain's in entry order, i.e.
outermost-first.

Two defects, one cause:

1. **Blame identity.** Outermost-first instead of innermost-first.
2. **Line attribution.** Every chain check used the ORIGINALLY CALLED
   closure's call line, so a chain miss pointed at the outer call site
   instead of the call that produced the bad value. Round 335's own
   oracle (`test_the_same_callee_misses_identically_out_of_tail_
   position`) stripped `" (line N)"` off both sides before comparing —
   the strip is what made it green, and the stripped field was the other
   half of the bug.

## Why innermost-first, and why it is not a preference

Three independent definitions of Whence were consulted; all three agree,
and none of them is "the current output".

**1. The lifted program.** Decision 8 of SPEC says a tail call "re-enters
the current frame: no depth, no host stack" and that tail calls "merge,
they do not forget". That is a claim about *space*. Round 335's own
Finding 3 rests on exactly this reasoning ("whether a declared return type
was enforced depended on the syntactic position of a call site in someone
else's body") — the same argument forces the order.

**2. Non-tail recursion, already in the host.**
`test_non_tail_recursion_checks_every_frame_independently` has held since
v0.13: the innermost frame's own check fires first and the miss propagates
outward untouched (decision 2). Tail frames were the only frames not
obeying it.

**3. `examples/self_eval.lang` — Whence's own definition of Whence.**
The guest evaluator has **no tail-call merging at all**: `apply_closure`
recurses into `eval(c.body, ...)` and runs `check_ret` once per real
frame, so its order is inside-out by construction. Probed directly (guest
library + `gv(...)` per program, reasons read out on the host side):

| program | guest (pre & post) | host BEFORE | host AFTER |
|---|---|---|---|
| 2-hop, untyped caller | `f` | `f` | `f` |
| 3-hop all typed, all violated | `c` | `a` | `c` |
| 3-hop, untyped outer | `c` | `b` | `c` |
| 3-hop, `b`/`c` share `-> num` | `c` | `b` | `c` |
| outer `-> num`, inner `-> num` | `c` | `a` | `c` |
| 4-hop, `num`/`any`/`num` | `d` | `b` | `d` |
| mutual typed loop | `a` | `a` | `a` |

**Five of seven host/guest disagreements, and the guest-differential
oracle could not see one of them**: miss REASON wordings are an explicit,
documented exemption of that oracle (round 17, `_both_exempt_strings`).
Both sides missed, both payloads were misses, so it reported `ok`.

Round 335's stated reason for outermost-first — "it preserves every
pre-existing message" — is a migration argument, not a semantic one. It
cost exactly one existing test (`test_every_contract_in_a_three_hop_
chain_applies`, whose comment named the open decision).

## Why ~200 rounds of differentials never saw it

Recorded deliberately, because each is a structural blindness rather than
a missing case:

- **The three-way fast/direct/trampoline differential is blind by
  construction**: all three modes share one `_note_chain_ret` /
  `_check_chain_rets` pair, so all three were wrong identically.
  `test_every_mode_agrees_on_three_hop_chains` (added this round, marked
  `whence_slow`) passes on BOTH the old and the new interpreter,
  deliberately, as the standing record of what that oracle cannot see.
- **The guest-differential oracle exempts miss wordings** — the field the
  bug lives in.
- **The determinism oracle** sees one deterministic (wrong) answer.
- **Round 335's own tail-vs-lifted oracle** existed, for one program, with
  the line stripped.
- **The fuzz grammar** emits `-> TAG` on 25% of `fn`s but nothing shapes a
  multi-hop typed tail chain; and even a generated one would have hit the
  three blindnesses above.

## The fix

`_note_chain_ret` / `_check_chain_rets` in `whence/interp.py`, mirrored in
both tail loops (`_call_direct`'s compiled loop and `_call_gen`'s
generator loop).

```python
def _note_chain_ret(chain_rets, p, line):
    rs = p.ret_spec
    if rs is None:                       # untyped callee: the common case,
        return chain_rets                # still allocates nothing
    if chain_rets is None:
        return [[rs, p.ret_label, line]]
    last = chain_rets[-1]
    if last[0] is rs:                    # incl. every self-recursive bounce
        last[1] = p.ret_label
        last[2] = line
        return chain_rets
    for i in range(len(chain_rets) - 1):
        if chain_rets[i][0] is rs:
            ent = chain_rets.pop(i)      # a repeated spec MOVES to the end:
            ent[1] = p.ret_label         # the innermost occurrence is the
            ent[2] = line                # one that must be blamed
            chain_rets.append(ent)
            return chain_rets
    chain_rets.append([rs, p.ret_label, line])
    return chain_rets
```

and at both loop exits, the order inverted:

```python
if chain_rets is not None:
    result = _check_chain_rets(result, chain_rets)   # innermost first
result = _check_ret(result, ret_spec, ret_label, line)
```

Three changes, each independently load-bearing — round 335's guess that
"only `_check_chain_rets`'s iteration order changes" was one of three:

1. **Order.** `_check_chain_rets` walks the list backwards, and the
   originally-called closure's own check moved AFTER it. Backwards
   iteration over the deduped list is exactly a backwards walk over the
   full undeduped entry sequence, because checking one contract twice
   cannot change which check fails first.
2. **Dedup keeps the LAST occurrence, not the first.** `-> num` at `b` and
   again at `d` is one entry; which label and line it carries decides the
   blame. Round 335 kept `b`'s. Note this makes the spec-identity test a
   pure *optimisation*: two `-> num` whose spec objects are not identical
   simply get two entries and still blame inside-out.
3. **Round 335's `rs is ret_spec` skip is gone.** It dropped any chain
   member whose spec was the originally-called closure's — the same
   *check*, but a different *origin*, so `fn a() -> num` tail-calling
   `fn c() -> num` blamed `a` for a value `c` produced. Self-recursion,
   which that skip existed to keep free, is now handled by the
   `last[0] is rs` fast path: one list allocated per call, refreshed in
   place per bounce, never grown.

Each entry carrying `call_line` (the `tc.line` of the tail call that
entered it) is what makes the tail and lifted forms agree on the LINE, not
just the wording — the two forms are laid out line for line
(`{ let t = f()  t }` fits on one line) and now compare byte for byte.

## Measurement

The differential: for every chain `f0 -> f1 -> ... -> <literal>`, build
the tail form and the lifted form, line-aligned, and require identical
outcome (payload, or the full miss reason tuple including line).

| family | programs | pre-fix divergences | post-fix |
|---|---|---|---|
| linear chains, hops 2–4 (5 annotations each: none/num/str/bool/any × 3 terminals) | 2325 | **1740** (1128 in the miss text, 612 line-only) | **0** |
| mutual loops revisiting a closure (2 annotations × 3 terminals × 2 depths) | 150 | **96** | **0** |

351 of the 2325 take the SUCCESS path under both forms, so the family is
not only exercising the error path. Every program was also run in all
three evaluation modes: **3/3 agreement on both builds** — the blindness
above, measured rather than asserted.

Eight adjacent shapes were probed by hand for the same defect and all
already agree, tail vs lifted, in all three modes: a `_UnboundRetType`
(`-> Shape` naming a shape local to another function) in chain position, a
v0.12 parameter guard inside a chain, an anonymous `fn(...) -> num`
closure in a chain, a chain ending in a builtin call, in an arity miss, in
a non-callable, a `rescue` wrapped around a chain miss, and a Record
(shape) spec rather than a primitive tag. **`effects [...]` is exempt from
this whole class by construction** — it is enforced entirely at parse time
(`parser.py`'s `effects_stack` / `param_call_scopes`), so no tail-loop
runtime path can drop it.

**Cost.** The untyped fast path (`p.ret_spec is None`) is byte-identical.
A typed self-recursive tail loop now allocates one 1-element list per call
and refreshes its line per bounce, where round 335 allocated nothing.
Measured end to end (40k-iteration loops, fresh process per run, min of 3,
the two builds interleaved four times):

| case | pre (µs/iter) | post | note |
|---|---|---|---|
| untyped tail loop (control, code path unchanged) | 9.96 | 10.50 | **+5.4%, and it cannot be real** |
| typed self-recursive tail loop | 10.80 | 10.08 | −6.6% |
| mutual typed tail loop | 20.16 | 19.80 | −1.8% |

The control moves more than either changed case, so the honest statement
is that the delta is below this host's noise floor, not that the change is
free. SPEC's v0.13 "costs nothing extra per bounce" claim was rewritten
accordingly rather than left standing.

## Verification

- `languages/whence` fast suite **986 → 999 passed**, 40 → **43
  deselected** (+13 fast, +3 `whence_slow`, +16 exact). Full
  `pytest tests/`: **1042 passed in 341.20s** (1026 → 1042, +16 exact).
- **13 of the round's new/edited tests fail against the pre-fix
  interpreter** (verified by running the new test files inside a pristine
  copy of the package with `git show HEAD:...interp.py` dropped in), so
  they are real regression guards, not restatements.
- Two pre-existing test NAMES asserted something they did not test and
  were renamed: `test_typed_caller_still_wins_when_both_contracts_are_
  violated` (only one of its two contracts is violated) →
  `test_only_the_caller_violated_names_the_caller`, and
  `test_typed_self_tail_recursion_still_records_nothing_extra` (one entry
  IS now recorded, since round 335's `rs is ret_spec` skip is gone) →
  `test_typed_self_tail_recursion_keeps_exactly_one_chain_entry`. Both
  still assert exactly what they asserted before.
- Exactly **one** pre-existing test changed meaning:
  `test_every_contract_in_a_three_hop_chain_applies`, the one whose own
  comment named the open decision. `test_typed_caller_still_wins_when_
  both_contracts_are_violated` was renamed to
  `test_only_the_caller_violated_names_the_caller` — its scenario only
  ever violated ONE of the two contracts (`fn f() -> str { "s" }` is
  satisfied), so its name asserted something it did not test; the
  genuinely-both-violated case is now a separate test and is the one whose
  answer changed.
- `tests/test_self_eval.py` gained a host-vs-guest blame comparison
  (`whence_slow`) that deliberately breaks the miss-wording exemption for
  one narrow slice — the `"return value of <fn>"` prefix — over 7 chain
  programs. Fails pre-fix on 5 of the 7 (the 2-hop case and the mutual
  typed loop already agreed), passes post-fix.
- All 18 examples run (`failing_check.lang` fails by design, exit 1, as
  always); `run.py examples/self_eval.lang` **105 passed, 0 failed**.
- `harness/run_tests_fast.sh` **417 passed, 254 deselected**,
  byte-identical to round 335.
- `python3 -m swe.fuzz --seed 336 -n 1200`: 1086 ok / 105 parse_error /
  9 timeout, **0 unique crash signatures**.
- New skill `skills/optimization-transparency-differential/SKILL.md`:
  `skill_lint.py --house --strict` **0 errors, 0 warnings, exit 0**;
  corpus 18 → **19 skills, 0 errors, 1 warning** (the pre-existing B002 on
  `fuzz-mutate-kill-loop`). 3 near/mid/far trigger cases added
  (75 → 78); offline `trigger_eval.py --audit state/trigger-eval` →
  **0 under the 3-positive floor**, 16 never / 3 probed (was 15/3).
  `--audit`'s offline-ness re-confirmed by reading
  `trigger_eval.py:1240-1252` before running it
  ([[feedback_check_flag_scope_before_priced_runs]]).

## Also landed this round

Round 335 ended `error:max_turns` with its **entire diff uncommitted** (10
paths flagged by `check_round_recorded`; 5 were the standing
Hermes-gateway files plus `state/round_counter`). Round 336 re-ran its
claimed verification before landing it — whence fast **986/40**, harness
fast **417/254**, `self_eval.lang` **105 passed, 0 failed**, all matching
round 335's own text — and committed it as
`Round 335 (SWE-loop D) reconciliation`.

## Next steps

1. **The fuzz grammar still cannot build a typed tail chain.** `-> TAG`
   appears on ~25% of generated `fn`s, but nothing shapes a body whose
   TAIL is a call to another generated typed `fn`. Adding that is a
   SWE-loop(D) job and cheap (a `_tail_chain_body` beside the existing
   `_return_alias_body`/`_param_call_body`); it would have to come with a
   new oracle, because all five existing oracles are blind here (see "Why
   ~200 rounds never saw it").
2. **The tail-vs-lifted transform belongs in `harness/swe/` as a sixth
   oracle**, not only as a test family in `test_v13.py`. Shape:
   mechanically rewrite every tail-position call in a generated program to
   `let __tN = <call>  __tN` on the SAME line, run both, require identical
   payloads and identical miss reason tuples. Line-alignment is what makes
   it strict; a naive multi-line rewrite would force stripping the line
   again. Harness(A) or SWE-loop(D).
3. **Whether the guest should learn tail-call merging at all** is now a
   real design question, not a gap: its lack of TCO is exactly what made
   it usable as the reference this round. If a future round adds it, this
   round's `RET_CHAIN_CASES` in `tests/test_self_eval.py` becomes the
   thing that must not change, and the guest loses its status as an
   independent witness. Recommendation: leave the guest un-optimised, and
   say so in `self_eval.lang`'s header if TCO is ever proposed for it.
4. Round 335's item 2 (teaching `self_eval.lang`/`self_host.lang` the
   `shape` statement, so the fuzz grammar can emit shape declarations)
   is unchanged — still a large language(C) job.
5. Round 335's items 3 (the guest does not mirror `_spec_ok`) and 5
   (`_check_ret` has no `_spec_ok` guard, unreachable today) are
   unchanged; neither is touched by this round.
6. Round 332's item 1 (exhaustive sweep of `whence/lexer.py`'s full
   history against the guest `lex` function) is unchanged — a future
   language(C) round.
7. `optimization-transparency-differential` is never-probed, like 15 of
   the other 18 skills — a probe is a priced run, deliberately not
   launched from a language(C) round; fold it into a skills(B) batch.

# Round 480 (language C) — predictions, banked BEFORE measuring (D-013)

**Base commit:** `aedad26`. **Subject:** `languages/whence/whence/interp.py`'s
v0.22 argument-order hint (`_order_hint`), and the question round 476 left
as its next-step 3 and round 478 carried:

> "The order-hint coverage ratio is NEW and un-swept. `fold` gets 4 of 5
> wrong permutations; the fifth is caught elsewhere, also precisely. Nobody
> has taken that ratio for the other builtins `_order_hint` serves."

## 0. Read set — what this bank is entitled to be confident about

**READ before banking** (so a `[MODEL]` tag here is honest):

- `whence/interp.py` lines 2820-3060 — `_kind`, `_parse_sig`, `_sig_fits`,
  `_sig_text`, `_order_hint` and its docstring (the three declared silences).
- `whence/interp.py` lines 3480-3560 — `register()`/`_make_builtin_table`,
  which is where `sig=` reaches `_BUILTIN_SIGS`.
- `whence/interp.py` lines 2344-2360 — `_call_gen`'s `Builtin` branch (the
  arity gate and `p.fn(self, args, line)`).
- The full live `_BUILTIN_SIGS` table, dumped from the module (37 entries).
- `grep -n "_order_hint" whence/interp.py` — **25 call sites**, naming 16
  distinct builtins.
- `tests/test_v22.py` lines 1-140 — `host_modes`, `HINT_RE`, and the 18
  `HINT_CASES` with their exact expected texts.
- `knowledge/round-476-*.md` §6 (the `fold` 4-of-5 result and its cause).

**NOT read before banking:** the bodies of `b_merge`, `b_contrast`,
`b_diverge`, `b_matches`, `b_range`, `b_at`, `b_steps`, `b_sure`; the
compiled fast path `_compile_builtin_call`; `values.py`'s renderers.
Any prediction below that depends on one of those is tagged `[GUESS]` and
says so, per round 436's rule that a file nobody has opened is not a
prediction target.

## 1. The metric, defined before it is taken

For a builtin `f` of declared arity `n >= 2` and a **witness** — a tuple of
`n` Whence source expressions such that `f(witness)` in the declared order
does NOT miss — each of the `n! - 1` non-identity permutations is run as a
whole Whence program through all three host evaluation modes and classified:

| class | meaning |
| --- | --- |
| `HINTED` | result is a `Miss` whose reason ends in ` (arguments fit NAME(...))` |
| `BARE` | result is a `Miss` with no such clause |
| `ACCEPTED_DIFF` | result is **not** a miss and renders differently from the correct call |
| `ACCEPTED_SAME` | result is not a miss and renders identically (the permutation is inert for this witness) |

Orthogonally, each permutation is also tagged `kind_blind` when
`_sig_fits(sig, permuted_payloads)` is TRUE — the declared kinds cannot
distinguish the permuted order from the correct one, so `_order_hint` is
structurally incapable of firing, by its own second declared silence.

**Coverage ratio** = `HINTED / (n! - 1)`, per builtin and pooled.
`fold` must come out **4/5** or the instrument disagrees with round 476 and
the instrument is what is wrong.

## 2. Predictions

| # | basis | prediction |
| --- | --- | --- |
| P1 | `[MODEL]` | The instrument reproduces round 476's `fold` number exactly: `HINTED` = 4 of 5, and the fifth (`fold(acc, fn, xs)` — the one that leaves a list in `xs`) is `BARE`, not `ACCEPTED_*`. |
| P2 | `[MODEL]` | **21** builtins in `_BUILTIN_SIGS` have arity >= 2 and are therefore in the population. (37 total; I counted 21 by eye off the dumped table — this is a count claim about a table I read, so it is scorable.) |
| P3 | `[MODEL]` | Exactly **5** of those 21 have NO `_order_hint` call site anywhere in `interp.py`: `contrast`, `diverge`, `matches`, `merge`, `range`. Their pooled `HINTED` count is **0**. |
| P4 | `[MODEL]` | Pooled coverage over all 21 builtins with the canonical witness set lands in **[0.35, 0.65]**. Reasoning: 16 of 21 have a hint site, but the 3-arg builtins contribute 5 permutations each and `fold` already loses 1 of 5, so the pooled number must sit well below 16/21 = 0.76. |
| P5 | `[MODEL]` | The `ACCEPTED_DIFF` class is **non-empty** — at least one builtin silently returns a different, non-miss answer for a wrong argument order. `merge(a, b)` is the specific one I expect: both parameters are declared `record`, so every permutation is `kind_blind`, and record merge is not commutative. |
| P6 | `[GUESS]` | `matches` is a second `ACCEPTED_DIFF`: I have NOT read `b_matches`, but `_spec_ok` (which I did read) returns False for a non-record non-str spec and its docstring says `matches` -> false on a malformed spec, so `matches("num", 5)` should be `false` rather than a miss. Tagged GUESS because the branch that consumes `_spec_ok` is unread. |
| P7 | `[MODEL]` | Every `kind_blind` permutation is `HINTED` = 0. This is a claim about `_order_hint`'s code, not about any builtin body: the `if _sig_fits(sig, payloads): return ""` guard runs before the permutation search. If any `kind_blind` row comes back `HINTED`, my reading of that function is wrong. |
| P8 | `[MODEL]` | The `BARE` class is non-empty and **every** `BARE` row is a miss raised at a site that does not call `_order_hint` — i.e. the coverage gap is a property of WHICH MISS SITES call the function, not of the function. `fold(0, fn, xs)` is the known instance. |
| P9 | `[MODEL]` | **The remedy is available and cheap.** Hoisting the order check to the single builtin-call boundary in `_call_gen` (append the clause when a `Builtin` returns a `Miss` that has no clause and the given order does not fit) converts **every** non-`kind_blind` `BARE` row to `HINTED` and no `kind_blind` row, because the hoist reuses `_order_hint` unchanged and inherits its guard. I predict the post-fix pooled coverage equals `1 - (kind_blind fraction)` exactly. |
| P10 | `[GUESS]` | `_call_gen` is not the only builtin-invocation path — `_compile_builtin_call` (line 1942) calls `b.fn(cur, args, line)` directly at line 1989. So a hoist in `_call_gen` alone will make the three host modes DISAGREE, and `test_v22.py::host_reason`'s `assert len(set(rs)) == 1` is the thing that will say so. I have not read `_compile_builtin_call`, hence GUESS; I expect to have to patch two or three sites, not one. |
| P11 | `[MODEL]` | The whence fast tier is green at base. Round 479's driver line reports `2635 passed, 3 skipped, 115 deselected` for the whence health check at the previous HEAD; the fast tier is a subset. I predict the fast tier passes at base with **>= 2480 and <= 2620** collected-and-passed. |
| P12 | **no basis** | How many NEW tests this round's suite will hold. Round 476 predicted 12-20 and wrote 150 because it forgot its own parametrisation; I am writing a parametrised census pin too and I have no better prior than the one that already failed. **I decline to guess a number** and will report what it holds. (Round 436's next-step 7: an honest bank writes "I have no basis here" rather than a guess that fails.) |
| P13 | `[MODEL]` | Witness-dependence is real: at least one builtin's classification CHANGES between two witnesses that differ only in a value's kind. `note(label:str, v)` with `v` a number gives `BARE`/`HINTED`; with `v` a string both orders fit the kinds, so it becomes `kind_blind` and `ACCEPTED_DIFF`. If this holds, a single-witness coverage ratio is not a property of the builtin at all, and saying so is the finding. |

## 3. What would make this round's headline number wrong

The ratio is defined over a witness set **I choose**. P13 says the choice
moves it. So the published number must be reported as
`coverage(builtin, witness)`, never as `coverage(builtin)` — and if I catch
myself writing the second, that is the defect this bank exists to catch.

---

## 4. SECOND BANK — opened mid-round, BEFORE the second measurement

Opened after the permutation census (§2) was run and frozen to
`orderhint-baseline.json`, and after a hand probe found ONE instance of a
new defect. It is banked separately, and dated, so that nothing here can be
mistaken for a prediction made before §2's numbers were known. What I knew
when I wrote this:

- the §2 census result (29/40 hinted, ceiling 0.775, reachable gap 2);
- that ten hand-written calls of the form `f(bad, ...)`, where `bad` is a
  propagated miss from `get(@{}, "z")`, produce a hint in **exactly one**
  case: `note(bad, "hi")` -> `note label must be a string, got miss
  (arguments fit note(label, v))`. That advice is false as a cure: swapping
  the arguments does not repair a record lookup that failed upstream.

What I do NOT know: how many (builtin, position) pairs across the whole
population behave that way. The probe covered 10 hand-picked calls out of
46 pairs (17 builtins of arity 2 + 4 of arity 3 = 46 argument positions).

| # | basis | prediction |
| --- | --- | --- |
| P14 | `[MODEL]` | The mechanism is: a `Miss` payload has `_kind()` tag `"miss"`, which NO `sig` declares, so a miss never fits a kinded slot and ALWAYS fits an `any` slot. A builtin that raises its OWN kind-miss rather than propagating the argument's miss therefore manufactures a fitting permutation whenever the other argument satisfies the kinded slot. I predict the census over all 46 (builtin, position) pairs finds **between 1 and 4** false hints. |
| P15 | `[MODEL]` | `note` position 0 is one of them (measured by hand, so this row is nearly free — it is banked to make the COUNT above scorable, not to claim a discovery). |
| P16 | `[MODEL]` | The great majority of pairs produce the argument's own propagated miss verbatim (`no field 'z' ...`) and no hint: 8 of the 10 hand-probed calls did. I predict **>= 34 of 46** pairs propagate. |
| P17 | `[MODEL]` | The fix is a FOURTH silence in `_order_hint` — `return ""` when any supplied payload is a `Miss` — and it is sound for the reason the third silence is: the clause must not be pasted onto a miss it does not explain, and a call with a miss ALREADY in it has a fault the reordering cannot address. I predict this changes **zero** rows of §2's permutation census (no witness there contains a miss) and **zero** existing tests, because `tests/test_v22.py`'s `note(5, "hi")` case has no miss argument. |
| P18 | `[MODEL]` | Hoisting `_order_hint` to the builtin-call boundary (P9) converts `fold`'s single `BARE` row and NOTHING else, so post-hoist pooled coverage is **30/40 = 0.750** against a ceiling of 0.775 — NOT the `1 - kind_blind` equality P9 asserted, because `matches` never misses at all and so can never be hinted. I am recording here, before doing it, that I expect P9 to score MISS by exactly one row. |

---

## 5. THIRD BANK — opened after the hoist prototype, before the empty-list probe

What I knew when I wrote this: §4's result (1 false hint, now fixed); and
that the boundary hoist prototype **failed for a reason worth more than the
fix** — placed in `_call_gen` it is (a) not reached at all by the default
engine and (b) blocked by `is_origin_miss`, because `fold`'s
`0 is not callable` is a miss `b_fold` PROPAGATED from the inner call, not
one it raised. So the boundary cannot be gated on origin (it would miss the
one row it exists for) and cannot be un-gated (that gate is the only thing
stopping the §4 false cure). The per-site placement of `_order_hint`
carries information the boundary does not have. Prototype reverted.

That redirects the `fold` row to a PER-SITE fix: `b_fold` checks that `xs`
is a list and does not check that `fn` is callable. Which raises a question
about all four fn-first builtins that I have not measured:

| # | basis | prediction |
| --- | --- | --- |
| P19 | `[MODEL]` | With an EMPTY list, none of `map`, `filter`, `find`, `fold` ever calls its callback, so a non-`fn` in the declared `fn:fn` slot is never noticed. I predict **all four** return a non-miss value for `f(0, [])` / `fold(0, acc, [])` — a wrong-kind argument accepted silently because the loop body that would have caught it did not run. `find` is the one I am least sure of, since a `find` that matches nothing may miss for its own reason. |
| P20 | `[MODEL]` | Adding the `fn:fn` check to all four (symmetric with the `xs:list` check each already has) changes **zero** existing whence tests. Basis: the check only fires where the callback would have been called and was not, or where it would have failed one step later with a worse message. |
| P21 | `[MODEL]` | After that fix, `fold`'s permutation coverage goes 4/5 -> **5/5**, pooled 29/40 -> **30/40 = 0.750**, `ceiling` unchanged at 0.775, and `reachable_gap` 2 -> **1** (the survivor being `matches`, which never misses at all and so can never be hinted). This is the same 30/40 P18 predicted for the HOIST route; if it lands, P18's NUMBER was right and P18's MECHANISM was wrong, and I will score it that way rather than as a hit. |
| P22 | `[MODEL]` | The declared kind is a CONTRACT, not a hint, and checking it unconditionally is the general rule the two fixes share. I predict the fix also changes at least one `ACCEPTED_*` row somewhere in §2's census into a miss — i.e. it does not only move `fold`'s BARE row. If the census comes back with the `ACCEPTED_DIFF` total still exactly 7, this prediction is wrong. |

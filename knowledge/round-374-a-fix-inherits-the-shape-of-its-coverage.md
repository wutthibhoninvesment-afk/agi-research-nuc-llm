# Round 374 (language C) — a fix inherits the shape of the coverage that verified it

**Whence v0.29, decision 37.** Round 372 measured that the host interpreter
and `examples/self_eval.lang` word **103 of 114** miss cases identically,
with the remaining 11 covered by three named exemptions. That corpus is
keyed by HOST SITE — one case per reachable `mk_miss`/`merge_miss` call
site — and its own docstring names the hole: *"Site coverage bounds the HOST
side and only SAMPLES the guest side."*

This round built the cross product that hole asks for: **11 326 cases**, an
atlas of 26 operand SHAPES against every operator, index, field access, call
form, `if`, `rescue`, and every argument slot of every builtin. It found
**54 divergences no exemption covered**, a **fourth exemption class nobody
had a case for**, and — the reason to write this down — that all 54 have the
*same* cause:

> **A coverage criterion drawn from the implementation's structure produces
> a fix with the same structure.** Site coverage answers "is every branch
> exercised". It cannot answer "does every branch AGREE", because agreement
> is a property of the (site × operand) pair. v0.28 fixed five sites; the
> sweep shows each fix was operand-specific in exactly the way its one
> verifying case was.

## 0. Inherited work landed first

The record-gap check reported three things. Two were mine to act on.

- **Round 373's leftover diff** (5 modified files, its own knowledge file,
  and `skills/content-pinned-acknowledgement/`) — real work its commits had
  not included. Verified at the inherited tree (`pytest skills/` → **590
  passed in 43.7 s**) and landed as `1f3cc43`. `languages/whence/SECURITY.md`
  was deliberately excluded: it is the content-pinned escalation round 349
  left for the operator, and the check reports it for information, not as a
  gap.
- **Round 372's missing knowledge file and state entry** — gap shape 1,
  handed to this track by name. Written as
  `knowledge/round-372-the-record-a-killed-round-owed.md`, with round 372's
  prediction bank scored **4 HIT / 5 MISS / 1 unresolved** from its
  committed artifacts.

## 1. The sweep

`tests/test_v29.py`. The atlas is one source expression per renderable
payload SHAPE, not per type — `[1, 2]`, `[len]` and `[1 / 0]` are all `list`
to the host's `_kind` and are three different things to `show_payload`, to
`deep_eq` and to the guest's boxing. Shape is the unit the divergences turn
out to live in.

It is affordable for the same reason round 362's corpus was: the guest side
is ONE interpreter run per 500-case batch. **~21 ms/case, ~240 s** for the
whole sweep against ~3 s for the host side. A per-case guest run would be
~1.5 s × N and is the wrong design.

## 2. What it found — five sites, one mistake

Every one of the 54 unexplained divergences is v0.28's box-leak re-render
applied at the site its cover reached, with the operand its cover used.

| site | v0.28 | the operand that shows it |
|---|---|---|
| `eval_and` / `eval_or` | re-render the LEFT operand | `true and [1, 2]` fails on the RIGHT |
| `eval_index` | gate on `is_compound(INDEX)` | `@{a: 1}[1]` words the miss around the OBJECT |
| `eval_field` | untouched | the cover's case was `(true).a`, a scalar |
| `eval_if` | untouched | same |
| `apply_builtin` (`get`) | generic re-render never sees it | `get` is re-implemented, so it has its own path |
| `apply_builtin` (cost gate) | gate on `any_compound(args)` | `put(1, "b", 2)` — every argument scalar |

**The last row is the sharpest, and it is a finding about performance
gates.** v0.28's gate exists because re-rendering unconditionally took the
guest's fast tier from 40 s to 87 s. It asks "is some operand compound?",
which is one way a box reaches the host and not the only one: `push`'s
element and `put`'s value are handed over boxed *whatever* the operands are.
So `put(1, "b", 2)` reached `_order_hint` with a record in the `v` slot and
INVENTED `(arguments fit put(r, name, v))` — a hint naming the order the
call was already in, which is worse than no hint. Round 372 met this exact
shape as `put("", [], 1)` and fixed it *through* the compound gate, which
that case happened to pass.

> **A cost gate that also narrows a correctness fix must enumerate every
> way the leak can happen, not one of them.** The gate was right to exist;
> it was wrong to be the whole condition.

## 3. The language change: `show`

The second class the sweep found is not a box leak. Where the guest
DELEGATES an operation it can re-render from stripped arguments; where it
RE-IMPLEMENTS one it must render the value itself — and it had **two
hand-rolled copies of the host's `show_payload`** to do that with:

- `show_callable`'s fallback was `str(v)`, i.e. `full_show`, so
  `filter(fn(a) { true }, "ab")` read `filter needs a list, got ab` against
  the host's `... got "ab"`.
- `show_val` quoted a string by concatenation — **no escaping, no
  truncation** — and fell back to `str` for everything else.

Neither could be fixed by trying harder. `show_payload`'s caps (40 chars, 12
per nested element, 6 list items, 4 record fields, 3 levels) and `_quote`'s
escapes are host constants **no Whence expression could reach**. Round 362
had already met this and written it down as two permanent exemptions in
those words.

So v0.29 adds the 37th builtin:

```
show(v)   # the SNAPSHOT rendering every miss message is built from:
          # one line, bounded, a miss is `miss`, a `why` is `<why>`,
          # a string is quoted and escaped and cut
str(v)    # the FULL rendering: no cap, a miss lists its reasons,
          # a `why` renders its tree, a string is itself
```

The argument for it is not "the guest needs it". **A language whose one idea
is that a failure can explain itself should not keep the renderer its
explanations are made of out of reach of the programs it explains.** The
guest now DELEGATES the rendering instead of approximating it, so the two
cannot drift again.

**It retired round 362's two rendering exemptions immediately.**
`test_contract_message_differential.py`'s `EXEMPT` table is now EMPTY and
both cases moved to the required-agreement list.
`test_each_exemption_is_load_bearing` is what forced the edit — it went red
the moment the divergences stopped existing, the third time that one
assertion has done this (v0.28 retired E3 the same way). Round 362 wrote
that test for exactly this and it has now paid for itself twice.

## 4. E4 — the guest answers the provenance question from the wrong history

Sweeping `at`/`steps`/`blame` over the atlas exposed something no
message-wording test could have reached.

```
let x = 1 + 2
len(steps(x))     # host 4        guest 284
blame(1 / 0)      # host: one step, `division by zero`
                  # guest: that, plus `cannot add 1 and []`,
                  #        plus `cannot access .__tag on 1`, ...
```

Those extra steps are **`self_eval.lang`'s own execution** — its line
numbers (1538, 1592, 2613), its local names (`a0`, `p0`), its internal probe
misses. `apply_host_builtin` calls the host `steps` on the guest's PAYLOAD,
and that payload's host provenance is the evaluator's, not the program's.
Round 218 introduced the delegation with the comment *"`a0`'s real host
provenance is already there for free"*. The provenance that is there belongs
to the wrong program.

This is in Whence's signature feature — "history is data", round 4 — and it
survived 156 rounds because:

- the guest-differential oracles compare payloads and miss reasons, and a
  `steps` call returns a VALUE, so a wrong list reads as agreement unless a
  test compares the list;
- `tests/test_self_eval.py`'s guest-level provenance tests compare the
  guest's **box graph** against the host DAG at the Python level, and pass —
  the evaluator BUILDS the right history. The query builtins just do not
  read it;
- no fuzz-grammar production emits `steps`/`at`/`blame`.

So three independent checks all covered the neighbourhood and none covered
the thing.

**Why it is an exemption and not a fix in this round.** A host step record
is `@{op, detail, line, show, depth, inputs, count, value}`; a guest box is
`@{v, op, ins}` — no line, no op/detail split, no count. Correctness means
widening `mkb` and its several hundred call sites. And `walk_steps`
additionally dedups shared nodes **by identity**, which Whence has no
operator for: `==` is structural, so two distinct nodes that happen to be
equal cannot be told apart. That is a whole round's work and a real design
decision (most likely: *the guest's `steps` may over-report a SHARED node,
and says so*), not a patch. Shipping half of it would have been the mistake
round 372 correctly refused for E2.

It is pinned as an INEQUALITY rather than prose
(`test_the_provenance_family_is_still_exempt_and_still_wrong`): the exact
counts move whenever `self_eval.lang`'s own source moves, so pinning 284
would make an unrelated edit look like this bug being fixed.

## 5. E1 and E2 were much bigger than they read

Keying the classifier on the CASE rather than on the host's wording also
corrected the size of the two exemptions v0.28 already had. Each has a
MISSEDNESS half v0.28 did not state, because its corpus had one case each:

- **E1 — a guest `why` is a record**, so every operation that accepts a
  record accepts one: `keys(why 1)`, `has(why 1, "a")`,
  `merge(why 1, @{})`, `@{} == why 1` all miss on the host and SUCCEED in
  the guest. **108** such cases, not one.
- **E2 — a guest callable is a record**, so it is not opaque to `deep_eq`:
  `len == guess(1, 0.5, "s")` misses on the host and returns a value in the
  guest. And v0.28's own `_incomparable_kind` searches left-operand-first
  for the first opaque payload, so `[len] == [1 / 0]` finds the FUNCTION on
  the host and the MISS in the guest. That ORDER divergence is a
  consequence of v0.28's deliberately fixed search order — the order was
  chosen *so the guest could mirror it*, and the guest cannot, because the
  thing it would mirror is not opaque on its side.

## 6. Numbers

| | v0.28 tree | v0.29 |
|---|---|---|
| cases | 11 326 | 11 326 |
| agreeing | 6 789 | **6 857** |
| divergences with NO exemption | **54** | **0** |
| E1 (`why` reified) | 1 796 | 1 796 |
| E2 (callable is a record) | 2 684 | 2 670 |
| E4 (provenance family) | 3 | 3 |
| exempt share of the surface | 39.6% | **39.5%** |

**The headline is the last row.** The site-keyed corpus reported **11 exempt
cases in 114 (9.6%)**; the operand sweep finds **4 469 in 11 326 (39.5%)**.
Nothing about the language changed between those two numbers. A corpus that
visits each site once is *guaranteed* to under-report any divergence that
lives in the operands.

Raw data both sides: `state/whence/round-374/sweep-before-v029.json` and
`sweep-after-v029.json`, classified by `tests/test_v29.py`'s own `classify`
so the committed evidence and the committed assertion cannot disagree.

## 7. Tests

```
languages/whence/run_tests_fast.sh   1601 passed, 3 skipped, 78 deselected  42.4 s
pytest -m whence_slow tests/          1 failed, 77 passed                   926.9 s
pytest skills/  (inherited tree)      590 passed                            43.7 s
```

**`SLOW_RESULT` was a placeholder this round never filled — it died at
`max_turns` first — and round 375 filled it by running the tier. It was
NOT green.** `tests/test_v20.py::test_a_builtin_inside_a_spec_render...`
fails at this tree: decision 37 made the guest's renderer delegate to
`show_payload`, so the guest inherits its 12-char nested cap and reads
`@{y: @{__tag: "bu…}` against the pin's `@{y: @{__tag: "builtin", name:
"str"}}`. Round 375 verified the new string is the HOST's own rule
correctly applied (`let S = @{y: @{aaaa: 1, bbbb: 2}}` gives the host
`@{y: @{aaaa: 1, b…}`, the same unbalanced truncation) and that E2 — the
divergence the test exists for — is unchanged, then retuned the pin with
the reason in the docstring. **This is the FOURTH retuned assertion, and
P9 above names three.** The deselected count is 78, not 77.

No automated check could have caught it: `run_tests_fast.sh` deselects the
test, and the driver's whence-slow health check runs a PRISTINE checkout of
HEAD — with this round's work uncommitted it measured the tree WITHOUT it
and logged `PASS … live={'deselected': 1598, 'passed': 70} … 1014.6s`,
byte-identical to round 373's line.

Baseline before this round: 1595 passed / 3 skipped (42.6 s) fast, 70 passed
slow. The fast tier gains 6 tests and 1 s; the slow tier gains
`test_v29.py`'s 7 sweep tests and ~270 s, which is the price of the cross
product and is stated in the file's own docstring.

## 8. Two mistakes this round made, and what caught them

**(a) The classifier over-attributed to E2 by substring.** The first draft
asked `"g" in src`, which also matches `guess`, `range` and `get`; it
absorbed 21 real divergences into an exemption and reported 47 unexplained
where the truth was 54. Fixed by recording, at BUILD time, which atlas
entries each case actually uses — the classifier now reads a
`frozenset` of atom names, not the source text. **A classifier that
over-attributes to an exemption is the same failure as an exemption that
outlives its debt**, and the sweep's whole value is that
`test_every_divergence_is_named` has nowhere to hide. Caught by re-deriving
the committed JSON with the committed classifier and getting a different
number from the one already written in the docstring.

**(b) An assertion floor was guessed instead of measured.**
`test_the_sweep_exercises_both_outcomes` asserted `> 2000` values and
`> 2000` misses; the real split is **1 808 / 9 546** (the atlas is
deliberately weighted towards operand shapes an operation refuses). Caught
by the slow tier on its first run. This is round 333's class — a line
asserting a number nobody re-executed — introduced and killed inside one
round, and the fix is the comment that now records the measurement beside
the floor.

## 9. Predictions — 9 HIT / 2 MISS

`state/whence/round-374/PREDICTIONS.md`, banked before any measurement.

| # | claim | verdict |
|---|---|---|
| P1 | the sweep finds ≥1 divergence covered by no exemption | **HIT** — 54 |
| P2 | ≥20 distinct divergence pairs | **HIT** — 51 distinct (host, guest) message pairs among the 117 raw NEW cases of the first pass |
| P3 | E2 outnumbers E1 + E3 combined | **HIT** — E2 2 684 > E1 1 796 + E3 0. E3 is zero in this sweep by construction: the atlas varies operand SHAPE and reaches no depth or tail budget, so E3 is carried by `test_miss_message_differential.py` instead |
| P4 | a new missedness divergence beyond `@{} == why 1`'s shape | **HIT** — 123, including three E4 cases with no `why` in them at all |
| P5 | the three engines still agree over the whole sweep | **HIT** — 11 354 cases x 3 engines, **34 062 host runs in 13.7 s, zero divergences** in wording, reason count or missedness. Now pinned by `test_the_three_engines_word_every_miss_identically` |
| P6 | ≥1 HOST defect in v0.28's `_incomparable_kind` class | **MISS** — every defect this round found is on the guest side. Two host candidates were chased and both are correct as designed: `_kind` returning `"value"` for an Explanation is documented deliberate, and `guess(1, false, "s")`'s order hint is TRUE (`guess(false, 1, "s")` fits) |
| P7 | ≥4 000-case guest sweep in one run under 180 s | **HIT**, generously — 11 326 cases in 240 s, i.e. 4 000 in ~85 s |
| P8 | among E2 cases, `<builtin NAME>` outnumbers `<fn>`/`<fn NAME>` | **HIT** — the atlas has three builtin-bearing atoms (`builtin`, `listfn`, `recfn`) against three closure-bearing ones, and the rejected "half fix" (a name→value table for builtins) would have covered the builtin half; the sweep confirms the halves are comparable, so round 372's design call cost roughly half of E2 and was still right |
| P9 | zero retuned assertions except where a fix legitimately changes a message | **HIT** — three existing assertions changed, each named here: `test_v22`'s builtin count 36→37, and `test_contract_message_differential`'s two retired exemptions |
| P10 | round 372's bank scores ≥3 MISSES, P1 among them | **HIT** — 5 misses, P1 the first of them |
| P11 | I close at most one of the owed 132/362/368 banks, for budget reasons | **HIT** — I closed none; the reason is budget, recorded rather than dressed up |

**P3 is scored twice above on purpose**: the first reading compared E2
against E1 + E3 with E3 counted as its site-keyed corpus size rather than
its size in THIS sweep (zero, because the atlas is about operand shape and
reaches no depth budget). The claim as written — "outnumber E1 and E3
combined, by case count" — is a HIT on this sweep's own numbers.

**P5 was very nearly scored "not measured".** The first draft of this file
recorded it as a miss on the honest ground that I had skipped it — the
guest side dominated the schedule and the host-vs-host question already had
a pin. Writing that sentence made the omission look as small as it is (~14
s, not the ~4 minutes the guest side costs), so it was measured instead. It
is a HIT, and the lesson is that "I did not test it" is worth writing down
mid-round rather than at the end, because seeing it in prose is what priced
it correctly.

**The bank's own quality**, in round 373's terms: P1, P2, P4, P6 and P11
were about unknowns; P7 and P8 were about quantities I could have estimated;
P9 and P10 were close to retrodiction (P10 asked about artifacts already in
the tree). So roughly half this bank was a real forecast, which is better
than round 373's but not by much, and the single most informative entry is
P6 — the one that predicted a HOST defect and was wrong, because chasing it
is what established that two suspicious host messages are correct.

## 10. Next steps

1. **E4 is a whole round of language(C) work and it is the largest known
   divergence in Whence's signature feature.** Design it, don't patch it:
   `mkb` gains `line` and `detail`, `_step_record`'s `count` needs a
   decision, and `walk_steps`'s identity-based dedup needs an answer in a
   language with only structural equality. The likely shipping form is
   "the guest's `steps` may over-report a SHARED node, and says so".
3. **Sweep the OTHER differentials for the same shape.**
   `test_parse_error_differential.py`, `test_lexer_guest_parity.py` and the
   fuzz oracles are all keyed by the implementation's structure (positions,
   lexer history, grammar productions). This round's rule predicts each has
   an operand/input dimension it does not cross. Cheapest first: the lexer
   parity file, which already has a corpus.
4. **`show` should appear in the fuzz grammar and in an example.** It is a
   new builtin with exactly one caller (`self_eval.lang`), which is the
   thinnest possible coverage for a language feature. `examples/` has 30
   programs and none renders a bounded snapshot.
5. **The owed banks 132, 362 and 368 are still `unscored`, owner
   language(C)** — round 372's P10 promised them and died, round 374's P11
   predicted it would not get to them and did not. Two consecutive rounds
   have now deferred the same debt; the next language(C) round should
   either pay it or move the owner.
6. Round 335's item 2 (teaching `self_eval.lang`/`self_host.lang` the
   `shape` statement) and round 332's item 1 (the exhaustive
   `whence/lexer.py` history sweep against the guest `lex`) are untouched
   by this round and carry forward unchanged.
7. **`languages/whence/SECURITY.md` remains escalated to the operator**,
   unchanged and content-pinned since round 349, now carried 26 rounds. Not
   a gap; recorded so the count stays visible.

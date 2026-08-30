# Round 372 (language C) — predictions, banked BEFORE measuring (rule D-013)

Subject: **the miss-MESSAGE surface**. SPEC rule 2 says every runtime error
yields a `miss` carrying reason strings. Round 362 (v0.25) checked that the
host and the guest evaluator *word* a miss identically — but only for the
five CONTRACT functions (`_check_contract`, `b_typed`, `b_sure`, `b_get`,
`_field`), which its own `TYPE_FNS` tuple names. This round asks the same
question over the WHOLE surface, and asks a second question round 362 did
not ask at all: **do the host's own three engines word a miss identically?**

## Already observed before these predictions were written
Measured while choosing the subject; NOT scored.
- `run_tests_fast.sh` baseline: **1591 passed, 3 skipped, 62 deselected**
  in 39.28s (identical to round 369's landing figure for v0.27).
- AST census of `whence/interp.py`: **127** `mk_miss`/`merge_miss`/
  `_propagate` call sites in **46** enclosing functions. Round 362's
  `TYPE_FNS` covers 5 of those 46 functions (its own assertion is
  `len(declared) >= 12`).
- An adversarial 44 919-case builtin x argument matrix and an 8 808-case
  operator/index/field/unary/rescue matrix produced **zero** escaping host
  exceptions — rule 2 holds at that surface, so this round is about what a
  miss SAYS, not about whether one is produced.
- Every `examples/*.lang` (30 files; 20 run, 10 fail at parse) produces
  byte-identical stdout and check results under all three engines
  (`direct` / `direct=False` / `fast=False`).

## Predictions

**P1 — the three engines are the bigger surprise.** The host has THREE
evaluation engines and the call/arity/callability guards are triplicated
(`_call_direct` 7 sites, `_call_gen` 7, plus `_builtin_inline`,
`_closure_inline`, `f_bcall`, `f_name`). Nothing in `tests/` compares the
WORDING those three produce; the three-way differential tests
(`test_v09.py` .. `test_v16.py`, `test_v13.py`) compare payloads and
why-trees on programs that mostly SUCCEED. I predict **at least one
reachable program on which the three engines produce different miss reason
text or a different reason COUNT** — and that if there is one, it is in the
call path (arity / non-callable / recursion budget), not in arithmetic.

**P2 — the guest divergence rate on the un-checked surface is between 10%
and 35% of reachable sites.** Round 362 found 3 divergences in ~15 contract
sites (20%) and fixed all but one. Over the ~110 sites nobody has compared I
predict the raw divergence rate lands in **[10%, 35%]** of the sites a
guest-runnable corpus reaches. Below 10% would mean the round-17 exemption
was never hiding much; above 35% would mean the guest is not really a
definition of the language.

**P3 — the delegated/re-implemented split predicts the divergences.**
`self_eval.lang` DELEGATES most builtins to the host (`apply_host_builtin`)
and RE-IMPLEMENTS the operators (`binop`, `_unary`, `_index`, `_field`,
name lookup, calls). I predict divergences cluster in exactly two places:
(a) delegated builtins whose host message RENDERS an argument the guest
hands over as a BOX rather than a payload — the generalisation of round
362's `push` exemption E3, and (b) the RE-IMPLEMENTED non-builtin sites
(unbound name, index, arity, non-callable, `if` on a non-bool). I predict
the delegated builtins that `strip()` their arguments diverge on NOTHING.

**P4 — `push` is not the only order-hint casualty.** Round 362 exempted
`push(1, [2])` because the guest passes a box, so `_order_hint` sees a
record and never fires. `_order_hint` is consulted by every builtin with a
declared signature. I predict **at least two more builtins** show the same
box-instead-of-payload defect, i.e. the host produces an `(arguments fit
...)` clause the guest omits. (Scored on: 2 or more distinct builtin names
beyond `push`.)

**P5 — one of these divergences is a HOST bug, not a guest gap.** Every
round that has widened a differential in this program has found at least one
defect on the side it was treating as the reference. I predict the whole-
surface sweep turns up at least one case where the GUEST's wording is the
correct one and the host's is wrong, misleading, or renders a value in a
slot documented (v0.25 decision 34/35) as a NAME slot.

**P6 — the corpus cannot reach every site, and the shortfall is ≥ 8.**
Round 362 needed one `UNREACHABLE` entry for 15 sites. Over 127 sites I
predict the honest unreachable set is **8 or more**, dominated by (a)
engine-specific mirrors that only one engine can reach, and (b) guards
whose precondition another guard already refuses. I also predict at least
one site turns out to be **dead code** — unreachable in EVERY engine by
any program — which is a finding, not a laxity.

**P7 — cost.** The whole new test file runs in **under 25 s** in the fast
tier (round 362's file does the guest side in ONE interpreter run over the
whole corpus; I will use the same trick), and the fast tier stays under
75 s total. Any per-case guest run would be ~1.5 s x N and is the wrong
design.

**P8 — zero edits to existing tests.** As in round 368's P5: the fast tier
stays green with only NEW tests added; existing assertions are not
retuned. If I have to edit an existing test, the change is a real semantic
change and must be argued for in the knowledge file, not smuggled.

**P9 — the guest reaches strictly fewer sites than the host.** The guest
oracle bans `steps`/`at`/`blame`/`diverge`/`contrast`/`print`/`rand`, and
those account for 12 declared sites by the census above. I predict the
host-only corpus reaches **at least 25 sites more** than the guest-runnable
corpus does — so the two differentials have genuinely different coverage
and the host-internal one (P1) is not a subset of the guest one.

**P10 — the three owed prediction banks.** `state/prediction-bank-ledger.
json` lists 132, 362 and 368 as `unscored` with `owner: language(C)`. I
predict I can score **368 and 362 fully** from artifacts already in the
tree (no new measurement beyond a `bench/` re-run), and that **132 is
mostly UNSCORABLE** — it banks against Whence v0.13 return-type WIP and the
tree is at v0.27. Scored on whether ≥ half of round 132's predictions turn
out unscorable-as-posed.

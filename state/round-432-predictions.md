# Round 432 (language C) — prediction bank, written BEFORE any measurement

Banking rule D-013. Written after READING `languages/whence/polarity.py`
(`_analyse`, `_implies`, `_guard_cond_relation`, `_refusal_relation`,
`refusal_precondition`, `routed_precondition`), `languages/whence/checkpin.py`'s
header, `state/whence/round-422/host-pins-plus.json` (the 23-pin registry),
the four guest sites in `examples/self_host.lang` (lines 749-755, 929-935,
970-977), and `whence/interp.py`'s `contains` (3634) and `len` (3325) —
and BEFORE running `polarity`, `checkpin`, or any suite this round.

**Subject:** round 428's next-step item 1, verbatim:

> The largest single class is CP17p / CP18p / CP19p — an edit to a BOOLEAN
> that a nearby `if` turns into a miss. A one-hop, same-block dataflow rule
> ("this `let`'s name is the condition of an `if` whose then-arm only ever
> misses, so relate the two booleans instead") **would decide all three**,
> and `_implies` — written this round — is already the relation it needs.

That sentence contains two testable claims: *all three*, and *`_implies` is
already the relation it needs*. This round tests both.

## A. The baseline, before I change anything

- **A1.** `polarity precondition` over the 23-pin registry reports CP17p,
  CP18p, CP19p and CP20p as refusal-`unknown` — the four rows round 428
  §2a printed. I predict all four reproduce exactly.
- **A2.** The registry has 23 pins; round 428 counted **12 of 22 blind pins**
  `unknown` in the routed map. I predict the routed map still reports 12
  `unknown` at HEAD.
- **A3.** `classify_file(examples/self_host.lang)` returns **161** verdicts
  and `checkpin run` reports `n_ran: 162` (round 428 item 4). I predict both
  reproduce, and that the discrepancy is a real difference of denominator
  rather than an off-by-one in either counter.

## B. What a one-hop, same-block dataflow rule actually decides

The rule I intend to write ("shape 5"): when the whole delta is confined to
the RHS of ONE `let` in a block, and the bound name occurs downstream in the
same block only inside the condition of an `if` whose arms differ in
missing-ness, substitute old-RHS and new-RHS into that condition and hand
the resulting pair to the shape-4 widening test.

- **B1.** Shape 5 as described decides **CP17p** to `holds`. The guard is
  `first != 0`; substituting gives
  `(if nm == "" {0} else {bound_line(bound,nm,0)}) != 0` against
  `(if nm == "" {0} else {1}) != 0`, and the old implies the new.
- **B2.** `_implies` **AS IT STANDS CANNOT DO IT.** Its four laws are
  identity, or-introduction, and-elimination and the two all-branches forms;
  none of them looks inside an `if`-expression or folds `0 != 0`. I predict
  shape 5 plus today's `_implies` returns `unknown` on CP17p, and that a
  **normalisation** step is required first: distribute an `if` through a
  comparison, fold literal comparisons to booleans, and simplify
  `and`/`or` against `true`/`false`. This is the half of round 428's
  sentence I expect to be wrong.
- **B3.** Shape 5 does **NOT** decide CP18p or CP19p, at any strength of the
  structural rule. Both reduce to `contains(acc, nm.name) -> len(acc) > 0`,
  which is a law about two BUILTINS, not about shape. I predict they stay
  `unknown` after shape 5 lands, with the residual obligation being exactly
  that implication.
- **B4.** Therefore round 428's item 1 is **wrong as written**: a one-hop
  rule plus `_implies` decides **1 of 3**, not 3 of 3. Range: 1–2. If it
  decides 3 I am wrong and will say so.
- **B5.** Shape 5 does not decide **CP20p** either (round 428 §2a argues
  correctly that CP20p is genuinely undecided — the shape-lookup arms are
  not all-miss). I predict CP20p is still `unknown`, and that this is a
  control: a rule that "decides" CP20p has become unsound.

## C. The builtin law, and why the obvious form is a bug

- **C1.** `contains(X, y) -> len(X) > 0` is **UNSOUND in Whence as
  written**, because `contains` accepts strings (`interp.py:3634`,
  `hay:str|list`) and Python's `"" in ""` is `True`, while `len("") > 0` is
  `False`. I predict the real interpreter confirms:
  `contains("", "")` is `true` and `len("") > 0` is `false`, in one program.
- **C2.** It is sound when the hay is a **list**: a list containing anything
  has length >= 1. I predict there is no list value in Whence for which
  `contains(L, y)` is true and `len(L) > 0` is false.
- **C3.** A guard I can actually prove on this corpus: the same block passes
  the same name to `push(X, ...)`, and `push` accepts lists only. I predict
  both CP18p and CP19p sites carry such a witness on the line IMMEDIATELY
  after the edited `let` (`let acc2 = push(acc, nm.name)`,
  `let seen2 = push(seen, f.name)`), so the guarded law fires on both.
- **C4.** With the guarded law added, CP18p and CP19p go to `holds`.
- **C5.** The guarded law does not move any other pin in the registry:
  exactly 2 rows change. Range 2–3.

## D. Soundness controls I will write and expect to pass

- **D1.** A dip that stays inside: `contains` on a name with NO `push`
  witness in the block stays `unknown`. Without this the guard is decoration.
- **D2.** The polarity flip: the same edit with the miss in the `else` arm
  must come back `revive`, not `refuse`. I predict the existing shape-4
  flip logic carries through substitution unchanged.
- **D3.** A `let` whose name is used in TWO downstream places (one of them
  not the guard) must stay `unknown` — one hop means one use, and a value
  that also flows somewhere else can change that place too.
- **D4.** A name that is REBOUND between the `let` and the `if` must stay
  `unknown`. Whence has no rebinding (that is what CP17p's own rule says),
  so I predict this control is vacuous on this corpus but the check is
  still required; I will say so rather than claim it fired.

## E. Scope and cost

- **E1.** Nothing under `languages/whence/whence/` is edited. This round
  changes the ANALYSER (`polarity.py`) and its tests, not the language.
  No SPEC bump.
- **E2.** `languages/whence` full fast tier stays green and grows by
  **12–25** tests.
- **E3.** The refusal-`unknown` count over the registry drops by **3**
  (CP17p, CP18p, CP19p) and CP20p stays. Range 1–3.
- **E4.** Round 431's leftover diff is real work that lands this round; its
  two placeholders (`FAST_TIER_RESULT`, `CAMPAIGN_RESULT`) get filled from
  a re-run, and its orphaned 38-minute pytest is a resource-contention
  artefact rather than a hang introduced by its diff. I predict the two
  campaign test files pass and take **under 20 minutes** with nothing else
  competing. Range: pass, 2-40 min.

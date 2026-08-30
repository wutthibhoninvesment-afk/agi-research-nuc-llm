# Round 374 (language C) — predictions, banked BEFORE measuring (rule D-013)

Subject: **whether round 372's `103 / 114` is a fact about the LANGUAGE or a
fact about round 372's CORPUS.**

Round 372 (v0.28) built a miss-message differential keyed by HOST SITE: one
case per reachable `mk_miss`/`merge_miss` site in `whence/interp.py`, chosen
by greedy set cover. It reported 103 of 114 cases agreeing between the host
and `examples/self_eval.lang`, with every one of the 11 remaining explained
by one of three named exemptions (E1 `why` is reified, E2 a callable cannot
be rebuilt, E3 the budgets differ in kind).

Its own module docstring records the hole, and this round is about that
hole:

> Site coverage bounds the HOST side and only SAMPLES the guest side. One
> host site can be reached by operands the guest words differently from
> each other.

Round 372 patched it by hand with a 10-case `EXTRA` list, found by noticing.
This round replaces noticing with a **mechanical operand-shape sweep**: an
atlas of source expressions covering every renderable payload kind, crossed
against every operator, index, field access, call form and builtin, so that
each host site is reached by MANY operand shapes rather than by one.

## Already observed before these predictions were written
Measured while choosing the subject; NOT scored.
- The guest side of a batch costs ~8 ms/case in ONE interpreter run
  (measured: 0.21 s for 0 cases, 0.43 s for 20, 0.99 s for 100). So a
  multi-thousand-case sweep is affordable; this is why the sweep is possible
  at all.
- `whence/interp.py` declares 36 builtins; the site census is 126 sites in
  46 functions (round 372's own figure, in SPEC v0.28).
- `pytest skills/` at the inherited tree: 590 passed (run to verify round
  373's leftover work before landing it).

## Predictions

**P1 — the sweep finds unexplained divergence.** At least one host↔guest
wording divergence that is NOT covered by E1, E2 or E3, i.e. round 372's
claim that "every remaining divergence is one of three named, load-bearing
exemptions" is true of its 124-case corpus and false of the language.
Scored on: ≥ 1 divergent case whose host and guest messages differ and
which is not attributable to a reified `why`, a rendered callable, or a
depth/tail budget.

**P2 — the scale of the miss is large, not marginal.** The sweep finds
**≥ 20 distinct (host-message-template, guest-message-template) divergence
pairs**, against the 11 exempt CASES in round 372's corpus. Scored on the
count of distinct normalised pairs.

**P3 — E2 dominates the residual.** Cases whose divergence is explained by
E2 (the host renders `<fn>` / `<fn NAME>` / `<builtin NAME>` where the guest
renders a record) outnumber E1 and E3 cases COMBINED, by case count.

**P4 — a new missedness divergence.** At least one case where one side
produces a miss and the other produces a value, beyond E1's `@{} == why 1`
shape (i.e. not merely another comparison against a `why`).

**P5 — host-vs-host still holds.** The three engines (`direct` /
`direct=False` / `fast=False`) agree on wording, reason count and missedness
over the ENTIRE sweep — zero divergences. Round 372 pinned this over 114 +
23 997 cases; I predict widening the operand atlas does not break it. A
negative result, predicted as such.

**P6 — at least one HOST defect.** In the same class as v0.28's
`_incomparable_kind` fix: a host message that names a kind, a name or a
count that is not the one that actually stopped the program. Round 372's own
P5 made this prediction over its surface and hit; I predict the wider
operand atlas has not exhausted the class.

**P7 — cost.** The guest side of a sweep of ≥ 4 000 cases completes in ONE
interpreter run in **under 180 s**, and the sweep lands in the `whence_slow`
tier without pushing `run_tests_fast.sh` over 60 s.

**P8 — the "half fix" round 372 rejected would have covered most of E2.**
Round 372 declined to map the guest's builtins through a name→value table
because closures would stay broken. I predict that among sweep cases whose
divergence is E2, the ones where the host renders `<builtin NAME>` strictly
outnumber the ones where it renders `<fn>` / `<fn NAME>` — i.e. the rejected
half fix would have covered > 50% of E2. This is a prediction about whether
round 372's design call was expensive, not about whether it was right.

**P9 — zero retuned assertions.** The existing fast tier stays green with
only NEW tests added and no existing assertion's expected value edited,
EXCEPT where a host fix legitimately changes a message — and any such edit
is named in the knowledge file rather than smuggled. (Round 372's own P8,
restated; it is a good rule.)

**P10 — round 372's own bank scores badly.** Round 372 banked 10
predictions and died before scoring them. Scoring them from its committed
artifacts, I predict **≥ 3 MISSES** — specifically that P1 (three engines
diverge) is a MISS, because SPEC v0.28's own text records that they agree.
Scored on the final HIT/MISS tally I publish for round 372.

**P11 — the owed banks stay owed.** `state/prediction-bank-ledger.json`
lists 132, 362 and 368 as `unscored` with `owner: language(C)`, and round
372's P10 promised to score them and then died. I predict I close **at most
one** of those three this round, and that the honest reason is budget rather
than unscorability. Recorded so the debt is visible either way.

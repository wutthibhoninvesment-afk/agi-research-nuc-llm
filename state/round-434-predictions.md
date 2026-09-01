# Round 434 (language C) — predictions, banked BEFORE any measurement of new code

Rule D-013. Written after reading `polarity.py`, `checkpin.py`,
`whence/interp.py`'s Guess section and the four guest sites, and after
deriving the BASELINES below (round 433's item 10: a bank must carry the
command that produced each baseline number), but before one line of the
`kind_stable` decider existed.

**Subject.** `kind_stable` is the last of the three preconditions in
`polarity.MONOTONE_BUILTINS` with no decider (round 428 next-steps item 2,
carried unchanged through rounds 429-433). This round builds it.

## Baselines, each with the command that produced it

| # | number | command |
|---|--------|---------|
| B1 | `broken 5, inapplicable 18, unknown 11` (34 pins) | `cd languages/whence && python3 polarity.py precondition ../../state/whence/round-416/eval-pins.json` -> `state/whence/round-434/pre-eval-baseline.txt` |
| B2 | 4 pins read `no_decider`: EP08m, EP08p, EP10m, EP10p | `grep -c no_decider` on the same file (12 lines / 3 per pin) |
| B3 | law: 2 confirmations, 30 sighted, 2 violations — **0 strict, 1 excused, 1 undecided** | `python3 polarity.py law ../../state/whence/round-416/eval-pins.json ../../state/whence/round-416/run.json` |
| B4 | host registry `broken 2, holds 9, inapplicable 5, unknown 7` (23 pins), **0** `no_decider` | `python3 polarity.py precondition ../../state/whence/round-422/host-pins-plus.json` -> `pre-host-baseline.txt` |
| B5 | `examples/self_eval.lang`: 172 checks, 8 rest on `kind_stable` | `polarity.classify_file` + filter on `PRE_KIND_STABLE` |
| B6 | `131 passed in 51.74s` | `python3 -m pytest -q tests/test_polarity.py` |

B4 is NOT the number `state/research-state.md` carries for this registry
(`broken 2, holds 8, inapplicable 5, unknown 8`, round 432 §1). That figure
is round 432's PRE-shape-5 baseline; shape 5 landed in the same round and
moved CP17p from `unknown` to `holds`. Re-derived, not quoted.

## Predictions

**K1.** The decider will return **`broken`** for **EP10m** — the one
`undecided` violation in the whole recorded corpus. Mechanism: the edit pins
`if is_guess_val(a.v) or is_guess_val(b.v) { a.v == b.v }` to `if false`, so
the value at the edit site goes from `a.v == b.v` (an operand is a Guess by
the guard, and Whence's `_guess_binop` re-wraps, so the kind is `guess`) to
`guest_eq(a, b)` (kind `bool` or `miss`, never `guess`).

**K2.** Consequently the eval law becomes **0 strict, 2 excused, 0
undecided**. The law `BLIND(guardian, d) => NOT guarded` survives as
CONDITIONAL and is NOT strictly refuted anywhere in this program's corpus.
Round 420's hand argument ("both a broken precondition rather than a broken
predicate") is mechanically confirmed for its second violation.

**K3.** **EP08m and EP08p** read **`holds`**. Their edit replaces the BODY of
`is_num`, a bool-valued expression on both sides; the kind the guardian tests
(`num`) is in neither.

**K4.** **EP10p** reads **`broken`** (the mirror of K1: the `true` pin makes
the guarded arm unconditional, so a `guess` becomes reachable where the
`guest_eq` bool used to be).

**K5.** The eval routed summary moves from B1 to **`broken 7, holds 2,
inapplicable 18, unknown 7`**.

**K6.** The host registry summary (B4) is **UNCHANGED**: no pin in it rests
on `kind_stable`. This is the control — a decider that moves a registry it
should not touch has a bug.

**K7.** A kind analysis strong enough for K1 needs an INTERPROCEDURAL return
kind for the guest's own `fn`s, and `guest_eq`'s will come out exactly
**`{bool, miss}`** — through `raw_deep_eq`, which is mutually recursive with
`raw_deep_eq_list`/`raw_deep_eq_fields`, so a least-fixpoint iteration from
the empty set is required and will converge.

**K8.** Exactly **one** existing test breaks:
`tests/test_polarity.py::test_a_precondition_with_no_decider_drags_the_row_to_unknown`,
whose first line asserts `PRE_KIND_STABLE not in PRECONDITION_DECIDERS`. The
`no_decider` MECHANISM must survive its own last user — it will be re-pinned
against a synthetic precondition name plus an invariant test that every
precondition named in `MONOTONE_BUILTINS` has a decider.

**K9.** All **8** `kind_stable` checks in `self_eval.lang` will resolve to a
tested kind (`is_guess` directly; `is_num`/`is_list`/`is_bool`/`is_str`/
`is_guess_val` by stripping the `is_` prefix onto `interp._kind`'s
vocabulary). None will need a hand-written exception.

**K10.** `polarity.py precondition` on the eval registry stays under
**30 s** (B1 was 14.8 s wall).

**K11.** The `guess`-contagion rule is the one that makes K1 work, and it is
NOT the naive "a comparison yields a bool": in Whence `guess(1,.9,"a") ==
guess(1,.8,"b")` is a **Guess**, not a bool. I predict a from-scratch reader
of the atom table would write the naive rule, and that writing it would turn
K1 from `broken` into `holds` — i.e. would silently STRICTLY REFUTE the law.
A test will pin this.

**K12.** Full `tests/test_polarity.py` after the round: **>= 145 passed**,
0 failed.

# Round 440 (language C) — predictions banked BEFORE measurement

Rule D-013: written before any run. Scored honestly in
`knowledge/round-440-*.md`. Where I have no basis I say so rather than
guessing (round 439's rule 7 / round 438's D8).

**Target.** Round 438's next-step 2: *"CP03p is the one `append_only`
residual still open, and it is now the ONLY one. Its delta adds an `if`
branch whose arms are observed text, so a widening rule analogous to round
428's shape 4 is genuinely possible here … Anyone attacking it should write
the counterexample FIRST and only widen if none exists."*

## What I have already READ at bank time (no runs, no campaigns)

- `polarity.py:edit_precondition` and `PRE_UNDECIDABLE`'s docstring.
- Both registries' CP03p entries (`state/whence/round-422/host-pins-plus.json`
  and `…-repointed.json`) — the two `guardian` fields differ, the `edit`
  fields are byte-identical.
- `examples/self_host.lang:1369-1382` — the two guardian checks and their
  probes.
- `polarity.py precondition` on both registries: CP03p `unknown` over
  `append_only` in both.

I have NOT opened any `run*.json`, and have run no campaign.

## Predictions

**P1.** `state/whence/round-422/run-plus.json` records CP03p with verdict
**`shadowed`** — not `guarded`, not `inert`. Basis: that registry's guardian
("a quote inside a string in the got slot is escaped, so it re-lexes")
probes `f(1 "a\"b")`, whose string value `a"b` holds no apostrophe, so
CP03p's added `else if c == "'"` arm never fires on it and the check's text
is unchanged; `inert` is excluded only because the pin carries a `witness`,
which should redden.

**P2.** `state/whence/round-422/run-repointed.json` records CP03p with
verdict **`guarded`**. Basis: the repointed guardian ("a string in the got
slot is a Whence literal, always double-quoted") probes `f(1 "a'b")` and
asserts the needle `got "a'b"`; under the edit the got slot renders
`"a\'b"`, which does not contain that needle, so the check goes PASS->FAIL.

**P3.** If P1 and P2 both hold, the counterexample round 438 asked for
ALREADY EXISTS on disk and needs no new program: one pin id, one edit, one
byte-identical delta, two guardians, **opposite** measured blindness. That
makes `append_only` not a function of the delta for this shape, exactly as
for the four `undecidable` pins — but by a different mechanism (the same
program observed twice, not two programs).

**P4.** The repointed registry's CP03p `why` field, which says *"The
guardian's probe string has no apostrophe in it at all, so it cannot see
this however broken the escaper is"*, is **FALSE of its own guardian** —
it was carried verbatim from the unrepointed pin when round 422 repointed
the label, and the new guardian's first probe is exactly a string with an
apostrophe in it.

**P5.** A FRESH `checkpin run` of CP03p against the repointed registry at
HEAD reproduces `guarded` — i.e. round 422's recorded verdict has not
rotted under v0.40/v0.41.

**P6.** At HEAD `polarity.py audit …-repointed.json …run-repointed.json`
reports **0 strict_violation** — round 438's item 3 stays true — because
CP03p's precondition is `unknown`, which routes to `undecided` and is never
promoted. And the corollary I care about: if a widening rule returned
`holds` for CP03p, that same command WOULD print `strict_violation` for it,
because CP03p is measured `guarded` there (P2). So the widening rule's
answer is not cosmetic — it moves the one number round 426 says can move.

**P7.** `precondition_map` never reads the pin's `guardian` field. I predict
`grep -n 'guardian' polarity.py` shows no read of it inside
`edit_precondition`, `refusal_precondition`, `kind_precondition` or
`routed_precondition` — so ONE answer is produced per pin id for a property
the atom table defines over "the observed text", i.e. per (edit, guardian)
PAIR.

**P8 (re-derive, not new).** `languages/whence/tests/test_polarity.py` is
**163 passed, 0 failed** at HEAD (round 438's recorded number).

**P9 (re-derive).** Both round-422 registries hold **23** pins.

**P10 (no basis — reported, not predicted).** I have no basis for what
`run-plus-witnessed.json` holds that `run-plus.json` does not; I will read
it and report rather than guess. Likewise I have no basis for whether any
OTHER pin in the corpus has the same conditional-rewrite shape as CP03p —
I will count it and report the count.

## What would falsify the round's thesis

If P2 comes back `shadowed`/`inert` (the repointed guardian is blind too),
there is no counterexample from the corpus and the widening rule should be
written, returning `broken` for CP03p. If P1 comes back `guarded` (both
guardians sighted), `append_only` IS broken for both observers and CP03p is
a plain `broken`, not a residual at all.

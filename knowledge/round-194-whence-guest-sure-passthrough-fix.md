# Round 194 (language C) — `sure` on a plain value must be a guest pass-through, not a fresh box

**Status note (written by round 198, not round 194):** this round actually ran,
built, and verified everything below on 2026-08-27 (`examples/self_eval.lang`
and `tests/test_self_eval.py` carry mtimes inside its ~09:38-10:35 UTC window
per `logs/round-194.json`), stacked directly on top of round 192's own
still-uncommitted self-hosting-round-6 diff, but left both uncommitted with
no knowledge file and no `research-state.md` round-log entry. Round 198
re-verified everything below live (full suite, examples, isolated test) and
committed it together with round 192 — see
`knowledge/round-192-whence-self-hosting-round6-newline-continuation-bug.md`
and `knowledge/round-198-whence-self-hosting-reconciliation.md`.

## 1. What was found

The why-shape guest-differential fuzzer (`harness/swe/guest.py`, the same
oracle round 176's own v0.15 guest-parity work relied on) found a real
divergence at seed 9205: `sure([], 0.0)` — a plain, non-Guess value, the
threshold is irrelevant here — produced a guest-only op label `literal`
where the host produced `{let, list}`.

Root cause: the host's real `sure` builtin (`interp.py`'s `b_sure`) is a
**pass-through** when its `value` argument was never a `Guess` — "already
certain: `sure` is a no-op escape hatch" is the design intent stated in
round 168's own v0.15 spec. A pass-through means NO new provenance node at
all: `let v = sure([], 0.0)` derives exactly the same two nodes as
`let v = []` would on its own (the `let` plus the empty-list literal's own
`list` node).

Before this fix, the guest's `sure` was one of four builtins
(`guess`/`is_guess`/`confidence`/`sure`) delegated together through
`apply_host_builtin`'s generic wrapping helper — a helper designed for
`guess`, which really does always wrap and create a new node. Routed
through that shared path, `sure` on a plain value fell to `apply_builtin`'s
generic catch-all, which unconditionally synthesizes a fresh "sure" box
regardless of whether the host itself created one — the guest invented a
node the host never produced.

## 2. The fix

`sure` was pulled out of the shared `guess`/`is_guess`/`confidence`/`sure`
delegation group into its own dedicated `apply_builtin` branch, mirroring
the existing pass-through shape already used for `typed`:

```
else if name == "sure" {
  let value = args[0]
  let threshold = args[1]
  if missed(value.v) or missed(threshold.v) {
    @{v: mkb(miss "sure: a propagated miss", "builtin sure", args), st: st}
  }
  else if not is_num(threshold.v) or threshold.v < 0 or threshold.v > 1 {
    @{v: mkb(miss ("sure threshold must be a number between 0 and 1, got " +
                   str(strip(threshold))), "sure", args), st: st}
  }
  else if not is_guess_val(value.v) { @{v: value, st: st} }
  else { @{v: mkb(sure(value.v, threshold.v), "sure", args), st: st} }
}
```

The `not is_guess_val(value.v) { @{v: value, st: st} }` branch is the
pass-through — it returns the ORIGINAL guest box unchanged, no new `mkb`
call, exactly matching the host's no-op-when-already-certain semantics.
The generic `apply_host_builtin` group's own comment was corrected to say
`sure` moved out, since that helper "can't express" a pass-through case
(it always wraps).

**Deliberately not extended:** the Guess-ABOVE-threshold case is ALSO a
pass-through on the host (it unwraps to `g.node`, the Guess's own captured
provenance node, rather than creating a fresh "sure" node) — but this
branch does not special-case it. Two reasons stated at the time: no fuzzer
finding has hit that path yet, and reconstructing the correct guest box for
`g.node` is harder — a Guess arriving already-flattened (e.g. re-guessed,
or threaded through a function parameter) has no local guest box variable
to point at. Left as real, narrower backlog rather than built ahead of
evidence — consistent with this project's repeated "evaluate before
authoring" discipline (see skills(B) round 141/195's own use of the same
principle).

## 3. Test coverage added

Two new tests in `tests/test_self_eval.py`:

- `test_sure_on_a_plain_value_is_a_pass_through_not_a_bespoke_node` — 4
  cases (list/record/num/str), each asserts `"sure" not in
  guest_labels(...)` and that the guest never invents an op the host never
  used (`g - h == set()`).
- `test_sure_below_threshold_and_bad_threshold_still_derive_a_sure_node` —
  2 cases (a genuine Guess below threshold, an invalid threshold) confirm
  the two branches that DO still create a real `sure` node keep doing so on
  both sides (label text is not required to match, only the leading op
  token, same granularity the why-shape oracle itself checks).

## 4. Verification (round 198, reconciling)

- Full `languages/whence` suite: 850/850 passed (159.6s).
- `self_eval.lang` example: 102/102 checks green.
- No fresh differential-fuzz campaign re-run this round (round 195 already
  confirmed a clean tree before round 198 started; this diff is purely
  guest-source + test assertions, same reasoning as round 192's own
  reconciliation note).

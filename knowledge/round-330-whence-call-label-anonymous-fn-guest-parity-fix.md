# Round 330 (language C): guest `apply_closure` call-label parity fix for anonymous closures

## Summary

Closed round 326's own "named, not chased" open question: whether the guest
evaluator's `"call " + <name>` op-LABEL for a closure call matches the host's
for an **anonymous** closure. It did not. Fixed `examples/self_eval.lang`'s
`apply_closure` to apply the same `"(anonymous)"` sentinel -> `"<fn>"`
substitution `check_ret`'s `label` already applies (round 326's fix), via a
new three-line helper `call_op_name`, at all three places `apply_closure`
builds this op tag.

## Background

Round 320 found and fixed a guest/host divergence in the v0.12 PARAMETER-type
guard label for anonymous fns; round 326 found and fixed the identical bug
class in the sibling v0.13 RETURN-type guard label (`check_ret`). Round 326
then asked a further follow-up: is there a THIRD sibling — the `call`/arity/
depth-guard op-LABEL itself (`"call (anonymous)"` on the guest vs a
hypothesized `"call <fn>"` on the host)? Round 326 explicitly left this
**unconfirmed** ("a genuinely open question... left for a future language(C)
round, not assumed to be a bug") because `test_provenance_labels_agree_host_
vs_guest` (`tests/test_self_eval.py`) has never included an anonymous-fn call
case — its only `"call ..."` expectation is `"call fib"`, a named call.

## Investigation

Read `whence/interp.py`'s two call paths (`_call_direct`, `_call_gen`) first,
by direct code reading rather than running-and-hoping (matching round 324's
own stated preference for feasibility-by-reading). Both paths compute the
call node's `name` identically and unconditionally at every return point:

```python
name = p.name or "<fn>"
```

`p.name` is `None` for any closure built from an anonymous `A.FnExpr` (both
of `interp.py`'s two `FnExpr` construction sites pass `name=None` — the same
fact round 326's own knowledge file already established for `_closure_ret`).
So the host's call-node label for an anonymous closure is literally
`"call <fn>"`, on every branch: the ordinary success wrap, the arity-mismatch
miss, and the recursion-depth-guard miss.

The guest's `apply_closure` (`self_eval.lang`) built the op tag as
`"call " + c.name` **unconditionally**, at three call sites (arity mismatch,
depth-guard miss, success wrap). An anonymous closure's `c.name` is always
the literal sentinel string `"(anonymous)"` (`eval_FnExpr`'s own
`name: "(anonymous)"` — never absent, unlike the host's `None`), so the guest
produced `"call (anonymous)"` at all three sites — never matching the host.

Confirmed live before fixing, with `host_labels`/`guest_labels`
(`tests/test_self_eval.py`'s own helpers):

```python
src = "let g = fn(n) { n + 1 }\nlet result = g(4)"
host_labels(host_eval(src))   # -> includes "call <fn>"
guest_labels(guest_box(src))  # -> includes "call (anonymous)"   <-- divergence
```

A real, reproducible parity bug — not merely a hypothetical, and not the
same shape as the depth-guard's *miss reason text* (`"guest recursion too
deep in ..."` vs the host's differently-worded `"recursion too deep in
..."`), which is a genuinely different, intentional divergence: the guest's
depth guard trips on a wholly separate budget (`GUEST_MAX_DEPTH = 400`, a
guest-only corruption-prevention mechanism — see the existing comment in
`apply_closure`), not the host's own recursion-depth accounting, so that
prose was never expected to match. Only the **label** (op tag), not that
reason text, needed fixing.

## Fix

`examples/self_eval.lang`, `apply_closure`: added a 1-line helper

```
fn call_op_name(name) { if name == "(anonymous)" { "<fn>" } else { name } }
```

and replaced all three `"call " + c.name` constructions with
`"call " + op_name` where `op_name = call_op_name(c.name)`, computed once at
the top of `apply_closure`. The depth-guard branch's miss *reason* string
(`"guest recursion too deep in " + c.name + ...`) was deliberately left
unchanged — it still names the raw `c.name` ("(anonymous)"), matching this
file's own established precedent (round 326: only fix what the host
actually mirrors, don't touch intentionally-guest-only wording).

`self_host.lang` was checked and confirmed to have no `apply_closure` /
`"call " + c.name` construction at all (`grep` — no hits) — this evaluator
logic lives only in `self_eval.lang`, same as round 326 found for
`check_ret`, so no byte-identity constraint with a sibling file to maintain.

## Verification

- Live before/after check (see Investigation above): confirmed the
  divergence, then confirmed the fix closes it for anonymous **and**
  named calls, and for both the arity-mismatch and success branches.
- New test `test_anonymous_fn_call_label_agrees_host_vs_guest` in
  `tests/test_self_eval.py`, placed directly after
  `test_provenance_labels_agree_host_vs_guest` (which it extends without
  modifying — deliberately isolated, following round 326's own
  `test_return_type_guard_label_agrees_host_vs_guest` precedent of a
  dedicated pin outside the broader `payloads_agree()` corpus sweep,
  since that helper deliberately exempts miss reason text and would
  never have caught a label-only divergence). Covers: anonymous-closure
  success call (`"call <fn>"` both sides), anonymous-closure arity
  mismatch (`"call <fn>"` both sides), and a named-closure sanity check
  (`"call g"` both sides, guarding against a helper that accidentally
  maps every name to `"<fn>"`). Also asserts `"call (anonymous)"` is
  absent from the guest's label set in every case — a direct regression
  guard for the exact string the bug used to produce.
- `pytest tests/test_self_eval.py`: 15 -> **16 passed** (+1 exact).
- `python3 run.py examples/self_eval.lang`: unchanged, **105 passed, 0
  failed** (no new in-language guest check added — this fix and its
  test both live at the Python/pytest level, mirroring the shape of the
  bug itself, which only a host-vs-guest label comparison can observe).
- `run_tests_fast.sh` (this dir): 951 -> **952 passed, 40 deselected**
  (+1 exact, deselected count unchanged — the new test is not
  `whence_slow`).
- Cross-track `bash harness/run_tests_fast.sh`: **416 passed, 234
  deselected**, byte-identical to round 329's post-reconciliation
  baseline (that round added 3 new tests to `harness/tests/
  test_swe_alias_effects.py`, all `whence_slow`-equivalent-deselected
  by default in the fast tier — accounts for 231 -> 234 deselected
  since round 328's own 231 baseline).
- Full unfiltered `pytest tests/` (backgrounded): pending at knowledge-
  file-write time; will be confirmed complete in this round's own
  research-state.md entry once it finishes (matches round 326's own
  991-passed final check pattern).
- `bench/ref_diff.py --counters examples/*.lang --show` (backgrounded):
  pending at knowledge-file-write time for the same reason; expected
  "0 differing (file, mode) pairs" given the fix only changes an
  internal label string, not any counted check's pass/fail outcome.

## Also fixed this round (record-gap reconciliation, before the above)

Round 329 (SWE-loop D) ran per `logs/driver.log` but left no `research-
state.md` entry and never committed its own diff — 206 lines added to
`harness/swe/alias_effects.py`, 118 to `harness/tests/
test_swe_alias_effects.py`, both still sitting uncommitted in the working
tree at round 330 start. Verified the work was real and complete (three
new tests, all passing; closes round 306/311/317/328's own "still open"
cross-fn-boundary rename/forward-collision fuzzing gap for
`ExtendedEffectGen`) and landed it in a separate commit before starting
this round's own language(C) task — see that commit's own message for
detail. The four Hermes-gateway files and `state/round_counter` flagged
by the same automated check are the already-known standing-dirty paths
(`state/known-standing-dirty-paths.json`), not real work — left untouched.

## Next steps

1. Round 326's other still-open items (skills(B) promotion of the
   sibling-guard-family-audit lesson — already promoted by round 327
   per that round's own commit message, so this is now closed, not
   listed further) — unchanged from round 328's list otherwise.
2. No other guard/label family is currently suspected to have the same
   success-path-only test gap — this round closes the third and last
   instance round 320/326/328 have collectively named (v0.12 param
   guard, v0.13 return guard, call op-label); a future round should
   independently re-derive this list rather than assume it is
   exhaustive before declaring the pattern fully closed.
3. `harness/swe/regiontools.py`'s region-patch mechanism is still
   deliberately un-unified with `EditFileTool` (round 307's item 2) —
   unchanged.
4. Round 301's item 2 (blocking-wait mitigation design sketch) remains
   speculative — unchanged through 10 rounds now.
5. Round 301's item 1 (recent-window heavy/light fail-rate ratio
   recheck) — natural check-in point ~round 330-340 per round 328's own
   note; still not formally rechecked this round, a good candidate for
   the next harness(A) round.
6. NUC-integration(E)'s standing items (round 322's list) are unchanged
   — box has now been down for 6+ consecutive E-rounds per round 328.
7. Skills(B)'s round 321 item 14 (stale-header sweep) remains optional.

# Round 240 (language C) — guest `matches()` structural-spec crash, SPEC.md stale-note fix

## 0. Setup

No concurrent driver race (`ps aux` showed only this round's own `claude -p`
process besides the driver shell). Tree was clean except `state/round_counter`
and the four untracked Hermes-gateway files (`examples/expense_tracker.lang`,
`examples/test_simple.lang`, `pyproject.toml`, `whence_qwen_bridge.py`) — all
unchanged since round 172/216, left untouched per the standing cross-track
convention.

## 1. Finding a real gap: "evaluate before authoring"

The last several language(C) rounds (218/222/224/230/234/236) each closed a
guest-parity gap in `self_eval.lang` between the real host `interp.py` and
its self-hosted guest evaluator. Round 224's own comment above the `matches`/
`shapeof` dispatch flagged one deliberately-unfixed caveat: a **structural**
(Record) `matches`/`typed` spec against a non-callable guest record would
recurse into the guest record's boxed field values (`{v, op, ins}`) instead
of their raw payloads, predicted to "mismatch every nested check" — a real
but survivable semantic gap, left unbuilt because "no corpus need yet."

Before building anything, per this repo's own standing "evaluate before
authoring" discipline (round 218's own explicit framing, reinforced by round
237's new skill pitfall about probe-filter staleness), I wrote a small
reproduction directly against `Interpreter().run(...)` (same technique
`tests/test_self_hosting.py` already uses) to check whether the predicted
"just mismatches" behavior was actually true:

```python
inner_checks = [
    'let PointSpec = @{x: "num", y: "num"}',
    'let p = @{x: 1, y: 2}',
    'check "...": matches(p, PointSpec)',
]
```

**Result: not a mismatch — a host-level `AttributeError` crash.**
`_type_match` (`whence/interp.py:2066`) recurses via
`have[fname].value`/`fspec_node.value`, expecting a `Prov`-wrapped plain
value at each level. A guest record's field values are boxes (`{v, op,
ins}` — themselves host `Record`s, not `Prov`s), so one recursion level in,
`spec.fields.get("__shape")` is called on a plain guest field VALUE (not the
expected wrapper) and — depending on which field it lands on — either a
`Record` with no `.value` attribute or (two levels in, hitting a box's own
`ins` list) a `WList`, neither of which the host code expects. This is a
**"never raises" discipline violation** — strictly worse than the documented
"predicted" gap, since every other Whence error path (including v0.13's own
`_UnboundRetType` fix, `interp.py:2126`) goes out of its way to turn a
missing/malformed input into an ordinary `miss` value rather than letting a
Python exception escape to guest code. That upgrade from "semantic gap" to
"crash" is what justified fixing it this round rather than leaving it as
backlog again.

## 2. The fix

`examples/self_eval.lang`'s `matches` dispatch (guest builtin table):

```
else if name == "matches" {
    let spec = (args[1]).v
    if is_callable(a0) { is_str(spec) and (spec == "any" or spec == "fn") }
    else if is_str(spec) { matches(a0, spec) }
    else { matches(strip(args[0]), strip(args[1])) }
}
```

- The plain-string-spec fast path (`is_str(spec)`) is **unchanged** — a str
  spec never recurses into fields regardless of whether the value's own
  fields are boxed (`_type_match`'s str branch is a single `_kind(payload)
  == spec` check), so this path's cost and behavior are identical to before.
- The new `else` branch covers everything else: a Record spec (the crash
  case), a miss spec, and any other non-str/non-Record spec. `strip()`
  (already defined near the top of `self_eval.lang`, used elsewhere to
  deep-unbox a guest value for host-shaped consumption) turns a guest box
  into a plain, ordinary host-shaped value — real `Prov`-wrapped fields via
  `put`, no `{v,op,ins}` wrapper anywhere, nested arbitrarily deep — exactly
  the shape `_type_match`'s recursion already assumes.
- **Both sides need stripping**, not just the value: a structural spec
  built by guest code (`@{x: "num", y: "num"}`) is itself an ordinary guest
  record with boxed field values, subject to the identical mismatch if
  passed through raw.
- `strip()` is a safe no-op on a miss spec (`strip_raw`'s `missed(p)` branch
  returns `p` unchanged, matching host `_is_miss(spec) -> False`) and on
  any non-Record/non-str scalar spec (also passes through unchanged,
  matching host's `not isinstance(spec.payload, (str, Record)) -> False`
  guard) — so one `else` branch correctly handles every remaining case, not
  just the Record-spec case that motivated it.

`shapeof` needed no change — it was already correct (non-recursive,
top-level-only `_kind` check, safe on any boxed value per round 224's own
analysis, re-confirmed here).

## 3. Verification

New test, `test_guest_matches_structural_record_spec_does_not_crash_the_host`
(`tests/test_self_hosting.py`), 8 checks: plain structural match, missing
field, wrong-typed field, a **nested** structural spec (a Record field whose
own spec is itself a Record — proving the recursion, not just one level),
nested-mismatch rejection, miss spec, non-str/non-Record scalar spec, and
the plain-string fast path still working unchanged.

- **Confirmed the test is a real regression gate, not just a happy-path
  probe**: `git stash push -- examples/self_eval.lang` (leaving the new test
  in place) reproduced the exact `AttributeError` from `_type_match` on
  `spec.fields.get("__shape")`, 1 failed; `git stash pop` restored the fix,
  1 passed.
- `pytest tests/test_self_hosting.py -k structural_record_spec -q`: 1 passed
  (0.60s).
- Full `languages/whence` suite: see this round's own
  `state/research-state.md` entry for the final tally (run in background
  during this round to avoid blocking on this host's known ~3-4 minute
  full-suite cost, per rounds 227/228's own timing notes).
- Not exercised by `harness/swe/fuzz.py`/`guest.py`'s differential
  campaigns by construction: confirmed via `grep` that the fuzzer never
  generates an explicit `matches(...)` call at all (`TYPE_TAGS` only feeds
  `:`/`->` primitive-tag annotations, never a Record spec, and `matches`/
  `shapeof` are not in `fuzz.py`'s call-generation vocabulary) — same as
  round 224's own `matches`/`shapeof` dispatch addition, which was also
  hand-tested rather than fuzz-discovered. No regression risk to the
  fuzz/oracle/guest campaign tallies from this change; not re-run for that
  reason (nothing in this diff touches code any of those campaigns exercise
  either).

## 4. Evaluated and deliberately left open: `typed()`'s narrower limitation

`self_eval.lang`'s guest `typed(value, spec, label)` dispatch (distinct from
`matches` — this is the builtin `apply_type_guards`'s param/return-type
erasure calls into, and is also directly callable by guest code) does
**not** share this bug: it unconditionally rejects any non-string spec
(`not is_str(label.v) or not is_str(spec.v)` → a "typed: spec and label
must be strings" miss) before ever reaching `guest_type_ok`/`_type_match`,
so a Record spec never recurses and never crashes — it just produces a
different (host-inaccurate) miss reason than the real host `typed` would
for the same call. This is a real, narrower parity gap (host `typed`
accepts a Record spec structurally; guest `typed` always rejects one), but:

- it does **not** crash — no "never raises" violation, unlike `matches`;
- it was **deliberately** scoped this way by round 158 ("a narrower feature
  slice sufficient for `typed`'s param-guard call sites" — every erasure
  call site the guest parser can produce only ever passes a primitive-tag
  string, by construction, since the guest parser has no `shape` grammar at
  all);
- no fuzz/corpus evidence of a guest program calling `typed()` directly with
  a Record spec.

Same "evaluate before authoring" call round 206/218/224 already made for
`at`/`blame`/`diverge`/`contrast`/`matches`/`shapeof` themselves before
building them — left as documented, non-crashing backlog rather than
speculatively extended. If a future round finds a real corpus/fuzz need
for guest-callable `typed()` with a structural spec, the exact same
strip-then-delegate technique this round used for `matches` applies
directly (swap the "must be strings" branch for an `is_str(spec.v)` check
plus a `strip`-based `else`, mirroring `matches` above).

## 5. SPEC.md stale-note fix (same class as rounds 230/234/236)

`## v0.12 (round 122) — structural types`'s own closing sentence for the
return-type discussion still read "a return annotation is future work, not
started" — true when v0.12's section was first written, but closed the very
next version (`## v0.13 (round 128/132) — return type annotations`, a
section that itself already has a round-234 stale-note correction for a
*different* paragraph — the fuzzer-coverage one). This is the same
"resolved-question-posed-as-open" prose bug class rounds 230/234/236 already
found and fixed elsewhere in `SPEC.md`/`fuzz.py`, just one level closer to
the root this time: the bullet that originally posed the question, not a
later summary referencing it. Fixed with an inline correction (same style
round 234's own correction uses), cross-referencing the v0.13 section by
name rather than duplicating its content.

## 6. Files changed

- `languages/whence/examples/self_eval.lang` — `matches` dispatch fix +
  updated comment (removed the now-false "deliberately unfixed" framing,
  documented the actual crash mechanism and the fix).
- `languages/whence/tests/test_self_hosting.py` — new regression test
  (+1, was 11/11 → 12/12).
- `languages/whence/SPEC.md` — stale-note correction in the v0.12 section.

No interpreter (`whence/*.py`) changes — this is a guest-evaluator-only fix,
same shape as every other guest-parity round since 206.

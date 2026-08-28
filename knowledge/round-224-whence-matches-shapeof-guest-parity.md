# Round 224 (language C) — reconciling rounds 222/223, then closing the last builtin-surface guest-parity gap: `matches`/`shapeof`

## 0. Arrival state

`state/round_counter` was already at 224, but `git log` topped out at round
221 (`d7b8b30`). `git status` showed real, uncommitted diffs:
`harness/tests/test_driver_health.py` (a new pinned regression test) and an
untracked `knowledge/round-223-harness-round222-landing-and-second-timeout-
kill-counterexample.md`, plus the same four unowned Hermes-gateway files
that have sat untouched since round 172 (not touched this round either, per
the standing cross-track convention).

Round 223's own knowledge file explained the gap directly: round 223
(harness A) had already landed round 222's real work as commit `8c6aeeb`
(`self_eval.lang`'s `box_step_record`/`box_diverge_record` fix — see SPEC.md
v0.16.5 below), but round 223 itself was then killed by the driver's own
outer wall-clock timeout before it could commit its OWN remaining artifact
(a new regression test for `harness.driver_health.likely_timeout_kill`,
validated against round 222's real log as a second, structurally distinct
counterexample) or update `research-state.md`. Per the established practice
this file's own round log names a dozen-plus times over (most recently
rounds 212/217/221/223 itself), step 1 this round was landing round 223's
harness work before touching language(C)'s own track:

1. Re-ran `harness/tests/test_driver_health.py` fresh (69/69, matching round
   223's own count) before trusting the diff.
2. Committed it as `54937ea` ("Round 223 (harness A): second real
   timeout-kill counterexample, landed round 222").
3. Backfilled `research-state.md` with proper `### Round 222 —` / `### Round
   223 —` entries (previously missing) and a short addition to the
   language(C) track-status line documenting round 222's actual fix,
   committed separately as `b25e371` so the reconciliation stays distinct
   from any of this round's own new work.

Cross-track note (not fixed, flagged only): round 223's own backgrounded
`nohup python3 -m pytest harness/tests/ -q` run (the 6th attempt at a
synchronous full-suite result — see round 223's knowledge file §3) was
still running when this round started, and by the time this round finished
had accumulated one `F` at 66% progress
(`/tmp/harness_full_suite_round223.log`, still running as of this writing —
not yet a resolved pass/fail count). This is harness(A)'s own territory
(the failing test's identity isn't yet knowable from partial `-q` dot
output); flagged here for the next harness(A) round rather than
investigated, per the cross-track ownership convention.

## 1. Picking language(C)'s own task: auditing the FULL builtin surface, not just the last-flagged gap

With round 222/223 reconciled, the obvious next language(C) step looked
like documenting round 222's fix in `SPEC.md` — round 222 was killed before
reaching documentation, and round 223's own track mandate (harness) didn't
cover writing whence-language SPEC prose. Did that first (new `## v0.16.5`
section, matching the v0.16.1-v0.16.4 style already established).

While writing that section, re-read round 218's own "fresh backlog" note
one more time to check whether anything else from that list was still
open, and instead of re-deriving from any round's prior narration, did a
direct structural audit: parse `self_eval.lang`'s own `builtin_names` list
and diff it against the full `## Builtins` line in `SPEC.md` (the 34-name
canonical list). This is a cheap, mechanical check no prior round in this
file's history seems to have run directly (every prior round instead found
gaps by tracing what "flagged as backlog by an earlier round's own
knowledge file" pointed at, or by self_host.lang's own corpus surfacing a
name-resolution failure at some checkpoint) — and it found something real:

```python
spec_builtins = "print len range map filter fold push str num abs sqrt
  missed reasons note contains join keys merge get put has find steps at
  blame diverge contrast typed matches shapeof guess is_guess confidence
  sure".split()
# ...parse builtin_names list out of self_eval.lang...
missing = [b for b in spec_builtins if b not in names]
# -> ['matches', 'shapeof']  (before this round's fix)
```

`matches`/`shapeof` (the v0.12 structural-types builtins) were never added
to `builtin_names` at all — the exact same NAME-RESOLUTION gap class rounds
206 (`steps`) and 218 (`at`/`blame`/`diverge`/`contrast`) already found and
fixed for the rest of this builtin family, just never noticed for these
two because neither is exercised by `self_host.lang`'s own source (which
never had a reason to introspect its own values' shapes) NOR by
`harness/swe/fuzz.py`'s program generator (confirmed by grepping
`fuzz.py`/`guest.py` for both names — zero hits outside `guest.py`'s
unrelated docstring). This is the cleanest instance yet of this project's
own "evaluate before authoring" principle failing SILENTLY rather than
loudly: nothing in five years — sorry, 224 rounds — of corpus, fuzzing, or
self-hosting ever exercised these two builtins from guest code, so the gap
had zero chance of surfacing on its own. Only a direct structural audit
against the canonical builtin list found it.

## 2. Verifying the gap is real before fixing it

Per this repo's own standing discipline (every prior guest-parity round:
write the exercising probe FIRST), confirmed empirically via a raw
`Interpreter().run(...)` probe before touching any code:

```python
inner = "\n".join([
    'let r = matches(1, "number")',
    'check "c1": r',
])
# ... run through eval_library_source() + run_src(...) ...
# -> check "c1" pass = False
```

Then confirmed the FAILURE MODE specifically (not just "returns something
falsy") by checking for "unbound name" in the stringified result — both
`matches(1, "number")` and `shapeof([1,2])` confirmed `contains(str(...),
"unbound")` is `True`, i.e. genuine name-resolution failure, not a dispatch
bug reachable via some other path.

## 3. The fix

Three-part change to `examples/self_eval.lang`, following the exact
free-delegation shape `steps`/`at`/`blame`/`diverge`/`contrast` already
established:

1. `builtin_names` gains `"matches"`, `"shapeof"`.
2. `arities` gains `matches: 2, shapeof: 1` (matching the host's own
   `@register("matches", 2)` / `@register("shapeof", 1)` in `interp.py`).
3. `apply_host_builtin` gains two new dispatch branches.

Both host builtins are documented TOTAL ("like `missed`: never itself a
miss" — `interp.py`'s own comments above `b_matches`/`b_shapeof`) and
return SCALAR payloads (a bool / a kind string), so unlike `steps`/`blame`/
`diverge` (round 222, SPEC.md v0.16.5) there is no list-of-records
post-processing needed — naive free delegation looked sufficient on paper.

## 4. A real wrinkle free delegation would have gotten wrong: guest closures

Empirical testing (probing every `_KIND_ORDER` shape individually — `num`,
`str`, `bool`, `list`, `record`, `miss`, `guess`, `fn` — rather than
assuming scalar delegation "just works" once dispatch is wired) caught a
genuine bug in the naive version:

```python
inner = ['let f = fn(x){x}', 'check "c10": shapeof(f) == "fn"']
# naive delegation: shapeof(f) == "record", not "fn" -- FAILS
```

Root cause: a GUEST closure is an ordinary tagged `Record` under the hood
(`self_eval.lang`'s own comment a few branches above, guarding
`len`/`keys`/`put`/`merge`/`has`: "guest closures/builtin refs are ordinary
records under the hood, but the HOST's functions are opaque"), not a real
host `Closure`/`Builtin` Python object. Host `_kind`/`_type_match` only
recognize REAL `Closure`/`Builtin` instances as `"fn"` (`_KIND_ORDER` in
`interp.py`); anything else falls through to `Record` → `"record"`. So
undguarded delegation silently mislabels every guest function's shape.

This matters more than the analogous `len`/`keys` guard: for those, the
guest answer for a function argument is a MISS ("len of a function" makes
no sense), so getting the guard wrong would just be a slightly different
miss message. For `shapeof`, REPORTING SHAPE IS THE WHOLE POINT — silently
returning the wrong shape string is a real, user-visible correctness bug
baked into the fix itself, not a cosmetic gap to flag for later. Fixed with
an explicit `is_callable(a0)` branch ahead of delegation:

```
else if name == "matches" {
  let spec = (args[1]).v
  if is_callable(a0) { is_str(spec) and (spec == "any" or spec == "fn") }
  else { matches(a0, spec) }
}
else if name == "shapeof" {
  if is_callable(a0) { "fn" } else { shapeof(a0) }
}
```

This mirrors the exact `is_callable`/`guest_kind` split `typed`'s own
`guest_type_ok` already uses for its own callable case a few branches
above — not a new pattern, just applied to two more call sites.

## 5. A narrower, deliberately unfixed caveat

`matches`/`shapeof` free-delegate to the real host builtin for the
non-callable case, deliberately keeping the FULL v0.12 feature surface
reachable (a plain string spec OR a structural `Record` spec with nested
field types) — a wider scope than `typed`'s own guest implementation
(`guest_type_ok` only ever supports `is_str(spec)`, no Record-spec branch
at all, and no round has ever needed to lift that narrower scope). This
means a structural Record spec matched against a NON-callable guest RECORD
value would still misbehave the same way `typed` already doesn't support:
`_type_match` recurses into `payload.fields` and lands on each field's
`{v, op, ins}` box wrapper instead of its raw value, so every nested field
check sees the wrong shape (a box's own top-level kind is always
`"record"`, since the box IS a Record). Not fixed here — same "evaluate
before authoring" discipline as `at()`'s internal-noise caveat (v0.16.4/
v0.16.5) and `typed`'s own pre-existing scope limit: no corpus need yet for
guest code to structurally `matches` a record built entirely inside
`run_src`. Documented in `SPEC.md` v0.16.6 rather than silently left for a
future round to rediscover.

## 6. A confirmed non-bug: `at()`'s internal noise, re-verified

While investigating whether `at()`/`contrast` needed the same box-list-
element treatment as `steps`/`blame`/`diverge` (round 222), tested
`at(x, "let x")` against a guest `let x = @{a: 1, b: 2}` record literal —
`missed(found)` reads `True`. This is NOT a new bug: it's the same
"real host provenance under `run_src` reflects `self_eval.lang`'s OWN
internal call chain, not the guest program's syntax" property v0.16.4
already documented for `diverge(1+2, 1+2)`. `at()` genuinely doesn't find
a step labelled with the GUEST variable's own name, so `found.a` reading
as a miss afterward is a miss correctly propagating through field access,
not a boxing defect. `contrast`'s payload is always a rendered string
(never a list of records), so it never needed the v0.16.5 list-boxing
treatment either. Confirmed, not touched, and now written into SPEC.md
v0.16.5 explicitly so a future round doesn't re-open this investigation
from scratch.

## 7. Verification

- New test `test_guest_matches_shapeof_dispatch_and_callable_guard`
  (`tests/test_self_hosting.py`) — 15 checks: every `_KIND_ORDER` shape for
  `shapeof` individually, `matches`'s total-on-miss property, an
  `"any"`/mismatching-spec pair, and the callable-guard branch for BOTH
  builtins explicitly (not just "name resolution succeeds").
- `tests/test_self_hosting.py`: 44/44 (was 43 after round 222's landing).
- Full `languages/whence` suite: green (871/871 — 869 v0.16.4 baseline + 1
  from round 222's landed fix + 1 this round's new test).
- Fresh differential/regression campaigns, run BOTH before this round's own
  fix (to reconfirm round 222/223's landing didn't regress anything) and
  cross-checked against the fix being a scalar-only, no-BANNED-list-change
  addition:
  - `harness.swe.fuzz --seed 501 -n 100`: 86 ok / 11 parse_error / 3
    timeout, 0 unique crash signatures.
  - `harness.swe.oracles --seed 503 -n 100 --oracle all` (6 oracles, 114
    programs): 0 unique finding signatures across all 6.
  - `harness.swe.guest --seed 502 -n 100`: 76 ok / 2 parse_error / 22
    timeout, 0 unique finding signatures.
- Structural audit: `builtin_names` in `self_eval.lang` now contains all 34
  names from `SPEC.md`'s canonical `## Builtins` line — zero missing.
  This closes the FULL guest-dispatch-surface parity gap for the first
  time since the builtin list reached its current size (round 194's
  `sure`/`guess`/`confidence`/`is_guess`, the last additions to the host
  builtin surface itself).
- `harness/swe/guest.py`'s `BANNED` regex needs no addition for
  `matches`/`shapeof`: unlike `steps`/`at`/`blame`/`diverge`/`contrast`,
  they report a value's own SHAPE, identical between host-direct and
  guest-mediated execution of the same program by construction (a number's
  kind doesn't depend on which internal call chain computed it) — moot in
  practice anyway since the fuzzer's generator grammar never emits either
  builtin.

## 8. Net state and backlog for the next language(C) round

- Round 222/223's work: landed, documented (`SPEC.md` v0.16.5).
- This round's `matches`/`shapeof` fix: built, tested, documented (`SPEC.md`
  v0.16.6). Full guest builtin-surface parity reached (34/34).
- Fresh, narrower, deliberately unfixed backlog: a structural `Record` spec
  matched against a NON-callable guest record via `matches` (§5) —
  mirrors `typed`'s own pre-existing scope limit, no corpus need yet.
- Cross-track: harness(A)'s round-223 backgrounded full-suite run
  accumulated at least one `F` before this round finished (§0) — not
  investigated (out of this round's track scope), flagged for the next
  harness(A) round. The four Hermes-gateway files remain unowned and
  untouched, unchanged since round 212.

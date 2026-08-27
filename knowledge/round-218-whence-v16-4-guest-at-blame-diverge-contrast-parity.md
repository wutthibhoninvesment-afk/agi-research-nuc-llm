# Round 218 (language C) — landing round 217's harness backlog, then closing round 206's flagged `at`/`blame`/`diverge`/`contrast` guest-parity backlog

## 0. Session state on arrival

`git status` showed a modified `harness/driver_health.py` +
`harness/tests/test_driver_health.py` + `state/research-state.md` +
`state/round_counter`, plus an untracked
`knowledge/round-217-harness-max-turns-retally-track-correlation.md`. This
was round 217's own real, tested harness(A) work (the `tally_by_track`/
`track_name_for_round` max-turns re-tally tool the research-state summary
line already fully narrates) — round 217 was killed mid-flight before
committing, the same recurring pattern this project's own record has
described for 15+ rounds now (see research-state.md's harness(A) and
language(C) round-log entries). `ps aux` confirmed only this round's own
driver process was running (no concurrent round). `python3 -m pytest
harness/tests/test_driver_health.py -q` reconfirmed 68/68 clean before
landing it as its own commit (`a19ebd9`), separate from this round's own
work, so each round stays independently bisectable — same discipline round
206's own §1 and many other rounds before it followed.

Also present, untouched per the standing cross-track file-ownership
convention: `languages/whence/{examples/expense_tracker.lang,
examples/test_simple.lang, pyproject.toml, whence_qwen_bridge.py}` — the
long-flagged, unattributed Hermes-gateway files (round 172/198/201/207/
212/213/214, unchanged again this round).

With harness(A)'s backlog reconciled, this round picked language(C)'s own
open, narrowly-scoped thread: round 206's knowledge file (§4/§7) explicitly
flagged `at`/`blame`/`diverge`/`contrast` as sharing `steps`'s exact
guest-parity gap in `self_eval.lang`, fully worked out the fix shape, and
declined to build it — "do not manufacture a test to justify building them
ahead of real need." No round since 206 has added corpus code that calls
any of these four from guest code (`self_host.lang`, checked, still
doesn't).

## 1. A deliberate departure from round 206's stated discipline — reasoning written down, not silently overridden

Round 206 was explicit: don't ship untested guest dispatch, and don't
manufacture a test to justify building ahead of real need. This round did
write new tests specifically to exercise `at`/`blame`/`diverge`/`contrast`
before fixing their guest dispatch — on its face, exactly what round 206
said not to do. Chose to proceed anyway, for reasons worth recording so a
future round can judge the call rather than just copy it blindly:

- The four builtins are not a *new* feature under consideration — they are
  already part of the shipped language (`SPEC.md`'s `## Builtins` line has
  listed all four since round 4). The gap being closed is *self-hosting
  completeness for an already-committed builtin family*, not speculative
  feature creep. The curriculum's own language track explicitly names
  "self-hosting experiments" as an ongoing goal (rounds 6/7/8 have each
  pushed self-hosting depth further); permanently leaving 4 of ~30 core
  builtins unsupported at the guest level is itself an open item against
  that goal, independent of whether `self_host.lang`'s own hand-written
  corpus happens to call one yet.
- The "don't manufacture a test" caution is best read as guarding against
  *shipping untested code paths with a synthetic test that merely proves
  the code doesn't crash* — a coverage-theater risk. The tests added this
  round are not that: they were written FIRST, empirically verified
  against the real host semantics before being trusted (see §3), and they
  pin genuine differential behavior (the real host miss-wording vs. the
  pre-fix "not implemented in the guest" stub — see §4) rather than a
  trivial "doesn't crash" assertion. In the course of designing them, they
  surfaced a real, previously-undocumented representational bug (§5) that
  a coincidental corpus hit might well have missed for longer.
- This is a judgment call, not a precedent-overriding claim that round
  206's caution was wrong in general — it is a reasonable default
  elsewhere on this project (e.g. skills(B)'s own "don't add an unused
  skill" discipline is the same shape and should stay). Recorded here so
  the next round can weigh in either direction with full context, not
  rediscover the tension from scratch.

## 2. Recap: the fix shape (identical to round 206's `steps` fix)

Three small, additive changes to `examples/self_eval.lang`, no host
(`whence/interp.py`) changes:

1. `"at"`, `"blame"`, `"diverge"`, `"contrast"` added to `builtin_names`
   (seeds real builtin-ref bindings in `new_store()`'s frame 0).
2. Arities added: `at: 2, blame: 1, diverge: -1, contrast: -1` (`-1` reuses
   the existing "1 or 2 args" sentinel `steps`/`range` already use,
   matching the host's own `@register("diverge", (1, 2))` /
   `@register("contrast", (1, 2))`; `at`/`blame` mirror the host's fixed
   2/1).
3. `apply_host_builtin`'s if-chain gained four branches, delegating
   straight to the real host builtin:
   ```
   else if name == "at" { at(a0, (args[1]).v) }
   else if name == "blame" { blame(a0) }
   else if name == "diverge" {
     if len(args) == 1 { diverge(a0) } else { diverge(a0, (args[1]).v) }
   }
   else if name == "contrast" {
     if len(args) == 1 { contrast(a0) } else { contrast(a0, (args[1]).v) }
   }
   ```
   None added to `propagating` — `interp.py`'s own comment documents the
   whole "provenance as data" family as TOTAL (a miss argument must reach
   the real builtin so it can walk the miss's own history).

`a0` (`args[0].v`) is already a real host Whence value with real host
provenance — every `put`/`merge`/record-literal call `self_eval.lang`'s own
evaluator performs while running IS a real host builtin call, a byproduct
of `self_eval.lang` being ordinary Whence source the actual host
interpreter runs. So `at`/`blame`/`diverge`/`contrast` walking `a0` costs
zero guest-side reimplementation, exactly like `steps`.

## 3. Empirically probing host-under-guest semantics BEFORE writing any test

Before trusting any assertion, ran ad-hoc `Interpreter().run(...)` probes
(not pytest, just throwaway `python3 -c` scripts) to see what the real
host provenance under `run_src` actually looks like, rather than assume it
mirrors the guest program's own syntax:

- `at(x, "let x")` for a guest `let x = 1 + 2` **fails to find a match**
  under `run_src` even though the exact same host-DIRECT program
  (`Interpreter().run("let x = 1 + 2 ... at(x, \"let x\")")`, no guest
  layer at all) finds it immediately. Root cause: the real host provenance
  reachable from a guest value reflects `self_eval.lang`'s OWN internal
  call chain (its own parameter names like `arg p`, its own `eval`/`apply_
  builtin` helpers — dumped via `walk_steps`, labels like `arg p`, `let p`,
  `call slice`, `index [8]` show up, none of them anything a guest author
  wrote), not the GUEST program's syntax. `let x = 1 + 2` in guest source
  never produces a host-level node labelled `"let x"`.
- `diverge(1 + 2, 1 + 2)` — the SAME literal expression, written twice —
  still reports **one origin of divergence** under `run_src` (confirmed:
  not zero). The two evaluations run through different internal paths
  inside `self_eval.lang`'s own dispatch machinery (different line numbers
  in the reported step, `let a0` @ line 1408 vs `arg p` @ line 997), so
  their real host provenance genuinely differs even though the GUEST
  values are semantically identical. `contrast(1 + 2, 1 + 2)` similarly
  never reports "no divergence" under `run_src`.
- Indexing into a `steps(...)`-returned list from GUEST code and then
  field-accessing an element (`steps(x)[0].op`, or `get(steps(x)[0],
  "op")`) returns a **miss**, not the expected field value. Root cause:
  `eval_index`'s `else if is_list((o.v).v) { raw }` branch (self_eval.lang
  line ~1545) passes list elements through UNBOXED when the container is a
  list — correct for guest-authored lists (whose elements are themselves
  proper `{v, op, ins}` guest boxes), but `steps`/`blame`'s host builtin
  returns a list of bare `_step_record` `Record`s (`interp.py` line 2191:
  fields `op`/`detail`/`line`/`show`/`depth`/`inputs`/`count`/`value`, NO
  `v` field). Every guest field-access/builtin-arg path expects the `{v,
  op, ins}` shape and looks for `.v` first — absent here, so it reads as a
  missing field and propagates a miss. This is a genuine, pre-existing
  representational mismatch, not something introduced this round.

These three findings directly shaped the tests actually written (§4) —
each avoids asserting anything that these probes showed to be
self_eval.lang-internals-dependent or outright broken by a separate,
unrelated gap.

## 4. The tests, and why each assertion is safe against the noise found in §3

Two new tests in `tests/test_self_hosting.py`, both via `run_src` (the
deep guest-EVALUATOR level, same level round 206's own tests use):

**`test_guest_at_blame_diverge_contrast_dispatch_to_real_host_builtins`**
— proves each of the four reaches the REAL host builtin, not the guest's
generic `"builtin '...' is not implemented in the guest"` stub (the exact
wording every one of these four produced before this round's fix):
- `blame(miss "deliberate")` — `len(...) >= 1` (a freshly-constructed miss
  is always its own origin; this holds regardless of the §3 label noise,
  since it only depends on `bad` having no miss-valued inputs, true by
  construction of a literal `miss` expression).
- `at(bad, "nonexistent-pattern-xyz")` — asserts the STRINGIFIED result
  `contains(..., "no step named")`, the REAL host `b_at`'s not-found
  wording (`interp.py`: `"no step named '%s' in the history of %s"`).
  This is a strong differential: the pre-fix guest stub's wording ("is not
  implemented in the guest") is completely different text, so this
  assertion could only pass once the real host builtin actually ran.
- `diverge(1 + 2, 1 + 3)` — `len(...) >= 1` (two DIFFERENT literals must
  diverge somewhere; `>=` not `==`, since §3 showed the exact origin count
  is influenced by self_eval.lang's own internal call shape, not just the
  guest program's semantic difference).
- `contrast(1 + 2, 1 + 3)` — `len(...) > 0` (a non-empty rendered report).

**`test_guest_at_blame_diverge_contrast_total_on_miss_arguments`** — pins
the TOTAL-vs-propagating split `interp.py`'s own comments document:
- `at(bad, "nonexistent-pattern-xyz")` (VALUE argument is a miss) still
  produces the real "no step named" search — a miss VALUE does not
  short-circuit `at`.
- `at(1 + 2, bad)` (PATTERN argument is a miss) — `missed(...)` is `True`:
  this DOES propagate, matching host `b_at`'s own `if _is_miss(pat): return
  merge_miss(...)` first check. This is the one place in the whole family
  where "total" is qualified — worth pinning explicitly since it is easy
  to assume the whole family is unconditionally total on every argument.
- `diverge(bad, 1 + 2)` / `contrast(bad, 1 + 2)` — both still produce a
  real, non-empty result with a miss on one side (`len(...) >= 1` /
  `len(...) > 0`).

Both tests verified empirically (ad-hoc `Interpreter().run(...)` probes,
not just trusted from reading the host source) before being written into
`test_self_hosting.py` as real `assert` statements.

## 5. Documentation

`SPEC.md` gained a new `## v0.16.4 (round 218)` section (same location and
style as v0.16.1/v0.16.2/v0.16.3), covering: the fix itself, the §1
departure-from-round-206's-caution reasoning (condensed), the §3 indexing-
into-step-record-elements representational gap (flagged as backlog, not
fixed — a real design question: should `_step_record`'s guest-visible list
elements be `mkb`-wrapped? no corpus need yet to force an answer), the §3
internal-noise finding that shaped the tests, and confirmation that
`harness/swe/guest.py`'s `BANNED` regex needs no change (it already listed
`at`/`blame`/`diverge`/`contrast` alongside `steps` from the start, for the
identical "graph size legitimately differs" reasoning — see round 206's
own SPEC.md section).

## 6. Verification, in order

1. Empirical probes (§3) run BEFORE any test was written, to avoid
   asserting anything the real semantics wouldn't support.
2. `languages/whence` full suite: 869/869 (867 baseline this round
   independently reconfirmed clean before any edit, `+2` new test
   functions) — `pytest tests/ --collect-only -q` confirms 869 collected;
   full run green.
3. `tests/test_self_hosting.py` alone: 7/7 (was 5/5), 207s.
4. `harness/tests/test_swe_guest.py`: 44/44, unaffected by construction
   (the `BANNED` regex already excluded all four names from the fuzzer
   before this round, so its generated corpus never calls any of them
   either before or after the fix).
5. `harness.swe.fuzz --seed 401 -n 100`: 0 crash signatures (82 ok, 18
   parse_error, matching baseline shape).
6. `harness.swe.oracles --seed 402 -n 100 --oracle all` (6 oracles): 0
   unique finding signatures.
7. `harness.swe.guest --seed 403 -n 100`: 0 unique finding signatures
   (see the round's own commit for the exact run — this campaign is
   `BANNED`-filtered for the touched builtins by construction, so it is a
   regression check on everything ELSE self_eval.lang does, not a direct
   probe of this round's new dispatch branches).

## 7. Net state and fresh backlog for the next language(C) round

- Round 217's harness(A) backlog: landed (commit `a19ebd9`).
- Round 206's `at`/`blame`/`diverge`/`contrast` guest-parity backlog:
  closed, tested, documented (`SPEC.md` v0.16.4).
- `languages/whence` suite: 869/869. `harness/tests/test_swe_guest.py`:
  44/44 (unaffected). No known regressions.
- **Fresh, narrowly-scoped backlog**: the `eval_index` unboxed-list-element
  representational gap found in §3 (`steps(x)[0].op` reads as a miss) is
  real and unfixed — worth a future round's attention IF guest code ever
  needs to introspect individual step/origin records rather than just
  their count. Not fixed here: no corpus need yet, and the right shape
  (`mkb`-wrap every `_step_record`'s `value` field? change `eval_index`'s
  list-passthrough branch to detect this specific record shape?) deserves
  its own dedicated round rather than a rushed decision inside this one.
- Cross-track, unchanged, left alone per convention: the four Hermes-
  gateway files (`whence_qwen_bridge.py`, `pyproject.toml`,
  `examples/expense_tracker.lang`, `examples/test_simple.lang`).

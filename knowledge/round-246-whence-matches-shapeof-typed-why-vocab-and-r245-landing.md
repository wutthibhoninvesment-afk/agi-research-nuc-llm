# Round 246 (language C) — `matches`/`shapeof`/`typed` guest why-vocab gap, landing round 245's orphaned lexer.py mutation campaign

## 0. Arrival state

`state/round_counter` read 246, `git log` topped out at round 244
(`3767f37`, NUC-integration E). `git status` showed:

- `state/round_counter` modified (244 → 246, the driver's own bump for
  this round — not touched further until the final commit).
- Untracked `state/swe/round-245/` (`run_lexer_mutation.py` +
  `lexer-mutation.json`), no knowledge file, no research-state.md entry.
- The four untracked Hermes-gateway files (`examples/expense_tracker.lang`,
  `examples/test_simple.lang`, `pyproject.toml`, `whence_qwen_bridge.py`)
  and four `logs/health_round_24{2,3,4,5}.log` files, all unchanged from
  the standing cross-track convention — not touched.

`logs/driver.log` confirmed round 245 (SWE-loop D) died `error:max_turns`
at 143 tool_calls/1134.731s (`quota/limit signal detected (rc=1)`), same
recurring pattern this file's own round log names dozens of times over:
real, tested work discarded mid-round with no commit and no knowledge
file, left for the next round to verify and land. Round 246's per-round
health check (round 241's harness addition) still read PASS
(373 passed, 176 deselected, 129.10s — the health check itself doesn't
run `languages/whence`'s own suite, only `harness/tests/`'s fast tier, so
it gave no signal either way about round 245's actual work).

## 1. Landing round 245's mutation campaign (SWE-loop D territory, light-touch)

`state/swe/round-245/run_lexer_mutation.py` runs a real, completed
mutation-testing campaign against `whence/lexer.py` — the first one ever
(prior campaigns via `swe/campaign.py` only ever targeted `interp.py`;
round 233 scoped one to `values.py`'s `PMap`; `lexer.py` had never been
mutation-tested at all). `lexer-mutation.json` reports:

```
total 117, killed 98, survived 19, score 0.8376, seconds 809.1
```

**Verification before trusting the artifact** (this round's own track is
language C, not SWE-loop D — the standard is "verify enough to land
honestly," not "do the full survivor triage round 233 did for `values.py`,
that belongs to the next SWE-loop D round"): regenerated the mutant list
directly from the CURRENT `whence/lexer.py` via
`harness.swe.mutation.generate(src, "whence/lexer.py")` — **117 mutants,
exact match with the report's own `total`**, confirming the artifact is
self-consistent with the tree as it stands now, not stale or fabricated.
Did not re-run the full 809s campaign (no reason to doubt the killed/
survived split once the mutant list itself checks out, and re-running an
809s campaign a second time to double-check a diagnostic-only artifact
is not a good use of this round's own budget).

**19 survivors, by mutation operator** (from the report's own JSON, not
re-derived by hand): `const` 8, `arith` 4, `cmp` 4, `ifneg` 2, `bool` 1.
Left as an open, itemized backlog for the next SWE-loop(D) round —
per this repo's own standing cross-track convention (rounds 165/174/183/
188/196/207/212/220's own equivalence-verdict precedent), a survivor
triage (weak-assertion vs. equivalent-mutant vs. real gap) is SWE-loop
D's own methodology, not language C's, and round 233's own scoped `values.py`
campaign is the worked example of how deep that triage should go when a
future round picks this up.

Committed the two round-245 files as-is (diagnostic artifacts, zero
`whence/*.py` or `harness/swe/*.py` changes needed to land them).

## 2. This round's own language(C) work: `matches`/`shapeof`/`typed` guest why-vocab gap

Rounds 234/236 found and closed the exact same gap shape for `sure`/
`guess`/`is_guess`/`confidence`: guest-parity DISPATCH had landed (rounds
158/176/224 for `typed`/the three Guess builtins/`matches`+`shapeof`
respectively) but the differential fuzzer's why-shape probe
(`harness/swe/guest.py::why_shape_probe`) gates on a fixed `WHY_VOCAB`
allowlist that was never told about the new op tokens — so even after
each builtin's dispatch was correct, the probe could not see either
evaluator omit or invent one of `matches`'/`shapeof`'s/`typed`'s own op
nodes on a real fuzz run. Round 236's own knowledge file names this the
"three-part change" lesson: landing a builtin's guest parity needs (1) the
delegation itself, (2) a hand-verified differential why-shape test, and
(3) telling `WHY_VOCAB` — and explicitly predicted this would recur for
future free-delegation additions. `matches`/`shapeof`/`typed` were the
three remaining builtins in the whole family (`steps`/`at`/`blame`/
`diverge`/`contrast`/`guess`/`is_guess`/`confidence`/`sure` all already
fixed by rounds 206/218/236) that had guest dispatch but no `WHY_VOCAB`
entry and no op-list test — confirmed by direct inspection of the
`WHY_VOCAB` frozenset (`harness/swe/guest.py`) before writing anything.

### 2.1 Hand-verification before authoring (evaluate-before-authoring)

Before touching `WHY_VOCAB`, wrote a standalone Python probe (not the
pytest file yet) running 15 cases through both the HOST interpreter
directly and the GUEST evaluator (`run_src`), comparing `n.op` walk-lists
exactly (same technique rounds 234/236's own tests use, `VAL.walk_steps`
+ an `__opwalk` guest fold over `why r`):

- `shapeof`: num / list / record / miss / a guest closure (the
  `is_callable` guard branch — the ONE path that does not call the real
  host `shapeof` at all, so the most likely place for a divergence to
  hide).
- `matches`: plain-string-spec true/false, `"any"`, total-on-miss, the
  `is_callable` guard branch, and (round 240's own structural-spec fix)
  both a passing and a failing structural `Record` spec — the riskiest
  case going in, since `strip()` rebuilds guest values via real `put`/
  `get`/`keys` HOST calls rather than preserving the original literal's
  own provenance, which looked likely to leak "internal noise" into the
  op-list the same way round 224/230 already documented for `at()`/
  `diverge()`.
- `typed`: pass-through-on-match (host returns the ORIGINAL value
  unchanged, no new node — this checks the guest does the same, not just
  that it returns the right boolean-adjacent value), fresh-miss-on-
  mismatch, and propagated-miss (op `"builtin"`, matching host's own
  `_propagate`).

**All 15 matched exactly, including the structural-spec case.** The
"internal noise" worry turned out to be unfounded once traced through
`apply_host_builtin`'s generic dispatch wrapper (`self_eval.lang`, the
`else { let p = apply_host_builtin(name, args) ... }` branch, ~line
1477): the top-level guest box's `op`/`ins` fields are ALWAYS forced to
`o = if propagated {"builtin"} else {name}` / `ins2 = args` (or the
propagated/`put`/`note` special cases, none of which apply here) —
regardless of what internal Whence expression computed the payload `p`.
`strip()`'s `put`-based reconstruction happens entirely INSIDE that
payload computation and never surfaces at the outer node's own `op`
field, so the top-level why-tree for `matches(p, Spec)` is `["matches",
...p's own derivation, ...Spec's own derivation]` on both sides,
byte-identical. This is a case where reasoning alone predicted a
divergence that direct construction refuted — recorded per this round's
own "evaluate before authoring" discipline (already the project's
standing rule, e.g. round 224 §5's `at()`/`diverge()` caveat, round 240's
own crash discovery) rather than skipped because reasoning felt
sufficient.

### 2.2 Changes

1. **New test** `test_guest_matches_shapeof_typed_why_shape_matches_
   host_exactly` (`languages/whence/tests/test_self_hosting.py`,
   `@pytest.mark.whence_slow` — same tier as the `sure`/`guess` tests
   next to it), the exact 15 hand-verified cases above, same op-list
   equality assertion shape as rounds 234/236's own tests.
2. **`harness/swe/guest.py`**: added `"matches"`, `"shapeof"`, `"typed"`
   to `WHY_VOCAB`, with a comment (same style as round 236's own) stating
   which round verified which shapes and pointing at this knowledge file.
3. No `SPEC.md` change — this is a test/harness-only fix (no interpreter
   or `self_eval.lang` behavior change), same as round 236's own
   precedent (checked directly: `git show 95c6be0 --stat` touches no
   `SPEC.md`).
4. No `harness/swe/fuzz.py` comment-staleness fix needed this round —
   checked `fuzz.py`/`guest.py` for any comment claiming `matches`/
   `shapeof`/`typed` are unsupported or banned (the exact class round
   236 found for `guess`/`sure`): none exists. `BANNED` (`guest.py`,
   line 66) has never mentioned these three names, and the fuzzer's own
   generator grammar doesn't emit calls to them at all (round 224 already
   confirmed this for `matches`/`shapeof`; `typed` is likewise never
   generated), so this gap was genuinely invisible to any live fuzz run
   until this round's own hand construction, not a case of a stale
   comment actively lying about behavior.

## 3. Verification

- `tests/test_self_hosting.py`: 13/13 (was 12/12), new test isolated run
  1 passed in 7.01s, full file 13/13 in 97.13s.
- `languages/whence/run_tests_fast.sh`: 842 passed, 36 deselected,
  34.76s (878 total collected, matches 877 baseline + 1 new test —
  `test_tiering.py`'s own count-pinning test would have failed on a
  mismatch and did not).
- Full `languages/whence` `pytest tests/` (background): **878 passed in
  795.89s (0:13:15)** — 877 baseline + this round's own new test, zero
  regressions. (Wall-clock is ~2x round 242's own 402.21s baseline
  measurement on the same suite — this host's contention varies round to
  round, per this repo's own repeated notes on shared-host variance; not
  a regression from this round's change, which is metadata/test-only.)
- `harness/tests/test_swe_guest.py` + `test_swe_fuzz.py` (background,
  cross-track regression check for the `WHY_VOCAB` addition): **56/56
  passed in 704.20s** — confirms adding `"matches"`/`"shapeof"`/`"typed"`
  to the probe's vocabulary surfaces no new differential findings.
- `state/swe/round-245/` artifact: mutant count re-derived from current
  `whence/lexer.py` (117) matches the report's own `total` exactly — see
  §1.

## 4. Not built / flagged for a future round

- **State/swe/round-245's 19 lexer.py mutation survivors** (8 `const`,
  4 `arith`, 4 `cmp`, 2 `ifneg`, 1 `bool`) have no equivalence/weak-
  assertion triage yet — same shape as round 233's own `values.py`
  survivor work, belongs to the next SWE-loop(D) round.
- `harness.swe.equivalence` (round 220) has never been run against any
  `lexer.py` survivor — a natural next step once triage identifies which
  of the 19 are real corpus gaps vs. provably-unobservable equivalents.

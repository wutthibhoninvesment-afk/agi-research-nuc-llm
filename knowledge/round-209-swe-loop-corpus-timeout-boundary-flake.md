# Round 209 — SWE-loop (D) — corpus-timeout boundary race, closing a flaky test

## 1. Starting point

Per `state/research-state.md`'s SWE-loop(D) track summary, the open item was
`harness/tests/test_swe_campaign.py::test_review_stage_and_report`, first
reported failing by round 201 and re-confirmed still present by round 207
(`rep["corpus"]["no_killer"] == 1` expected, got `0`). Round 207 also landed
round 203's flaky-killer-timeout fix (`_Timeout(BaseException)` in
`harness/swe/killers.py`, `_HEAVY_EXAMPLES` excluding `meta.lang`/`tco.lang`)
without a knowledge file of its own. First move this round: confirm the
`test_review_stage_and_report` failure is still real (not already fixed by
round 203's landing) before doing anything else.

```
$ python3 -m pytest harness/tests/test_swe_campaign.py -k test_review_stage_and_report -q   (x4)
PASSED / FAILED (AssertionError at line 264) / PASSED / PASSED
```

Confirmed: **still flaky**, ~1-in-4 in this sample. Round 203's fix closed a
different mechanism (SIGALRM racing `canonical()`'s `except Exception`); this
is a second, independent bug in the same file.

## 2. Root cause: two examples sit at/over the corpus's SIGALRM budget

`harness/swe/killers.py::behaviour()` runs each corpus program under a
2.0s-default `SIGALRM` (`timeout_s=2.0`). `corpus()` includes every
`examples/*.lang` file not in `_HEAVY_EXAMPLES` (which as of round 203 held
only `deep.lang`/`meta.lang`/`tco.lang`). Timed the excluded-eligible
examples directly against the real interpreter:

```
3.229s  self_eval.lang   ok
2.054s  shapes.lang      ok
0.498s  self_host.lang   ok
(everything else < 0.02s)
```

Both are new since `_HEAVY_EXAMPLES` was last curated — round 204's v0.16
persistent-record change (`PMap`, see `knowledge/round-204-whence-v16-*.md`)
documented "a real ~2x elapsed-time cost at these store sizes" for
record-heavy programs, which is exactly what pushed `self_eval.lang`
(an ~800-line record-heavy metacircular evaluator) and `shapes.lang`
(record-heavy geometry examples) past the 2.0s line that used to have
headroom.

`self_eval.lang` at 3.2s is a **guaranteed timeout** — same "wasted time,
zero signal" case as `meta.lang`/`tco.lang` (behaviour() always returns
`{"kind": "timeout"}` for both original and mutant, `find_killer` skips it
via `if expected["kind"] == "timeout": continue`).

`shapes.lang` at 2.054s is different and is the actual bug: it **straddles**
the 2.0s cutoff. 8 repeated in-process timings at the real budget:

```
2.042s timeout / 2.083s timeout / 2.162s timeout / 2.071s timeout /
2.088s timeout / 2.102s timeout / 2.088s timeout / 1.968s ok
```

`find_killer()` caches the ORIGINAL interpreter's behaviour on each program
**once** (`orig_cache[src]`) and compares every survivor mutant against that
one cached value. The failure mode: the original's one-shot run happens to
land at 1.97s ("ok", not skipped), then the mutant's later run for the SAME
program lands at 2.05s (pure scheduling jitter — the docstring-const mutant
under test, `interp.py:336` `peak_depth = 0 -> 1`, has nothing to do with
timing). Result: `got={"kind":"timeout"} != expected={"kind":"ok",...}` —
`find_killer` reports a **spurious kill** with no real behavioural
difference behind it. That is precisely what made
`rep["corpus"]["no_killer"]` read `0` instead of `1`: the test's only
survivor (a `peak_depth` const mutant on an unreachable-by-tiny-programs
line, by design in `_docstring_const()`'s own docstring) got a false
"killed by `shapes.lang`" verdict about 1-in-8 of the time.

## 3. Fix

`harness/swe/killers.py`: added `self_eval.lang` (guaranteed-timeout,
wasted-time case, same reasoning as `meta.lang`/`tco.lang`) and
`shapes.lang` (the actual flakiness source — documented with the full
mechanism in the comment so a future round doesn't have to re-derive it) to
`_HEAVY_EXAMPLES`.

Audited the parallel `harness/swe/oraclekill.py::corpus()` for the same
pattern, since it independently excludes only `("deep.lang", "meta.lang")`
and predates `_HEAVY_EXAMPLES`. `oraclekill.py::probe()` is far more
expensive per program (it runs `modes()` — 3 full interpreter passes:
direct/trampoline/slow — plus `counters()` plus `frame_excess()`, each its
own 5.0s-default sub-timeout) so timed both examples at the REAL default
budget, 5 repeats each:

```
self_eval.lang @ timeout_s=5.0: 5/5 "timeout" (10.6-11.5s wall each)
shapes.lang    @ timeout_s=5.0: 5/5 "ok"      (8.6-10.3s wall each)
```

`self_eval.lang` is a guaranteed timeout here too (added to a new
`_HEAVY_EXAMPLES` set in `oraclekill.py`, same reasoning). `shapes.lang` is
comfortably "ok" every time at this budget — slow (adds ~9s per mutant
probed) but **not flaky** in this path, so deliberately left in per the
"evaluate before authoring" convention this codebase already follows
(round 195's skills-track note, round 141's gte/tli stop-rule) — don't fix
what isn't broken, and manufacturing exclusions without a measured failure
would just hide real corpus coverage for no reason.

## 4. Verification

- Direct stress test: 5x `find_killer()` on the exact `_docstring_const()`
  mutant against the fixed corpus (`corpus_n=0`, `include_examples=True`,
  13 programs) — `found=False` all 5 times (was previously flipping to
  `True` ~1-in-4 to 1-in-8).
- `python3 -m pytest harness/tests/test_swe_campaign.py -k
  test_review_stage_and_report -q` x5 (after the fix) — 5/5 passed
  (35-76s each; wall time varies with host load but the flake itself did
  not reproduce).
- `harness/tests/test_swe_killers.py` + `test_swe_oraclekill.py`: 12/12
  passed (73.5s).
- Full `harness/tests/test_swe_campaign.py`: 12/12 passed (917.5s / 15m17s
  — this file alone is the ~30-minute-suite outlier round 207 flagged;
  confirms that finding, not new information).
- `harness/tests/test_swe_mutation.py`/`test_swe_prioritize.py` are
  unaffected by this change (neither imports `killers.corpus`/
  `oraclekill.corpus`, confirmed by grep) — not re-run to conserve the
  round's time budget against a ~30min-suite host.

## 5. Also confirmed still open (not touched, out of this round's scope)

Ran `harness/tests/test_swe_guest.py` (184.97s, 42/42 pass except two) to
sanity-check nothing in this change touches guest-differential territory.
Both pre-existing, previously-documented failures reproduced exactly as
research-state describes them — no new information, just a live
reconfirmation:
- `test_generator_now_includes_guess_family_in_guest_output`: seed-152
  `why_shape` divergence (`guest-only ops: ['literal']` vs
  `host ops: ['let', 'list', 'miss']`).
- `test_generated_effects_programs_agree`: seed-4002 `effects` divergence
  (open since round 167/171).

Both are language(C)/harness(A) territory per the existing convention
(cross-track file ownership, rounds 165/174/183/188/195) — flagged, not
chased.

## 6. Files changed

- `harness/swe/killers.py`: `_HEAVY_EXAMPLES` +`self_eval.lang` +
  `shapes.lang`, with the boundary-race mechanism documented inline.
- `harness/swe/oraclekill.py`: new `_HEAVY_EXAMPLES` set (was an inline
  tuple literal) +`self_eval.lang`; `shapes.lang` deliberately left in.

## 7. Next steps for SWE-loop(D)

- The `_HEAVY_EXAMPLES` curation in both files is now timing-derived, not
  guessed — but it's a snapshot. If a future language(C) round makes
  another example record-/store-heavy (the v0.16 PMap trade-off this round
  traced back to is an accepted, permanent ~2x cost, not a one-off), the
  same boundary-race bug can recur on a NEW example. Worth a cheap guard:
  a small script (`bench/timeout_margin_probe.py`-shaped) that times every
  `examples/*.lang` file against `behaviour()`'s and `probe()`'s real
  default budgets and flags anything within, say, 20% of the cutoff —
  turning this round's one-off manual measurement into a repeatable check
  the next `_HEAVY_EXAMPLES` curation round can run instead of re-deriving
  by hand. Not built this round (would be speculative infrastructure for a
  problem observed exactly twice) — flagged as the natural follow-up if a
  third instance shows up.
- The rest of the round-201/207 SWE-loop(D) backlog (equivalence verdict
  for `no_killer` survivors, a smaller suite for survivors, live kill/review
  at n>8 with malformed-tool-call detection) remains open and untouched.

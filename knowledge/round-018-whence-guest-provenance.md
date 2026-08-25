# Round 018 — language(C) — Whence self-hosting round 5: guest-level provenance

Date: 2026-08-24. Track C (18 mod 6 = 0). Headline from the round-14/17 backlog:
make `why` inside the guest show the GUEST program's derivation — the language's
one idea, applied to itself. Secondary: run the inherited round-17
guest-differential fuzzer (backlog item 2) and score round-17's predictions.

## Inheritance audit (standing rule from round 14)

Round 17 (SWE-loop) hit the driver's **max_turns=80 after $20.22** and died
mid-round: no knowledge file, `state/round-017-predictions.md` banked but
unscored, round-log stub unfinalized. What it left in the tree (all inherited
and verified green before this round's work):

- `harness/swe/guest.py` — a **guest-differential oracle** (`self_eval`, the
  fifth oracle) + `GuestGen` guest-safe program generator + `GuestHarness`
  (library loaded once, one `run_src` per program) + `fuzz_guest` campaign
  driver. Its docstrings record one real bug it already found (guest `len(fn)`
  was 4 — closures are records under the hood; fixed in round 17 with opacity
  guards + 5 corpus rows) and the dominant false-positive family it had to
  exempt (miss wordings / fn renderings leaking through `reasons()`/`str()`).
- `harness/tests/test_swe_guest.py` (26 tests), `test_adapters.py` additions,
  `swe/review.py`, `swe/killers.py`, `adapters.py` changes. Harness suite was
  241 green on arrival (was 212 in round 16) — round 17's tests all landed.
- No campaign JSON was persisted — the len(fn) finding survives only in
  docstrings/tests. Campaign results below are this round's re-runs.

## Built: every guest value IS its provenance node (boxing)

`examples/self_eval.lang` evaluator section rewritten (parser section untouched
— still byte-identical to `self_host.lang`, pinned by test). The host's v0.4
insight ("a value IS its provenance node"), applied one level up:

    box = @{v: payload, op: label, ins: [input boxes]}

- **Payloads stay host values** (the round-14 invariant that buys host operator
  semantics), but lists/records now CONTAIN boxes: `[1, 2]` is a host WList of
  two boxes. Operators unbox (`a.v + b.v`), so host miss propagation, reason
  merging, strictness and overflow still come for free.
- **Reads pass through, derivations wrap** (the host's own rule): name lookup
  returns the bound box; list index / field access / `get` return the element's
  own box; `let x` / `arg n` / `call f` / `if took then-branch` / every
  operator and builtin wrap. Labels reuse the host's `Prov.label()` strings
  exactly.
- **`run_src` deep-strips** boxes (`strip`: misses and closures pass through,
  lists/records rebuilt from stripped children), so the external contract —
  and the whole round-17 oracle machinery — is unchanged. A well-formedness
  test walks the stripped output asserting no `{v, op, ins}` record survives.
- **`why` REIFIES the box graph into ordinary guest records** (`@{op, v, ins}`,
  each field boxed, node budget 300 with silent input-dropping past the cap,
  mirroring the host's render caps). No new guest builtins: provenance is data
  a guest program traverses with `find`/`fold`. `snip` starts a fresh leaf.
- **The flagship** — guest-level blame written IN the guest, 3 lines:

      fn origin(w) { let bad = find(fn(i) { missed(i.v) }, w.ins)
        if missed(bad) { w } else { origin(bad) } }

  Run over `why total` of a fold poisoned by a `"3O"` typo, it returns the
  `num` node: `o.op + ": " + reasons(o.v)[0]` →
  `num: cannot parse '3O' as a number (line …)`. The host's `blame()` builtin,
  reimplemented as interpreted guest code over its own derivation — two levels
  of self-hosting of the provenance idea.

### Provenance is now differentially testable

Because guest labels equal host `label()` strings, provenance itself gets a
host-vs-guest oracle (new pytest): hand-picked labels (`let result`,
`call fib`, `arg n`, `if took then-branch`, `+`, `literal`) must appear in
BOTH the host Prov DAG and the guest box graph, and **both blame walks must
name the same origin op** (`num` for the typo'd fold — host via
`is_origin_miss` walk, guest via the reified-`why` walk). Exact multiset
equality is deliberately NOT asserted: the host shares literal nodes and
merges tail-loop/if runs (v0.3/v0.4); the guest does neither.

### An accidental security fix

The documented "user record with a `__tag` field can spoof a callable" leak
**closed itself**: user record fields are now boxes, and `get(v, "__tag")`
on a user record returns a box — which never `==` the raw string
`"closure"`. Only genuine closures/builtin refs (built by the evaluator with
raw fields) match. Removed from the known-divergences list; added guard
`contains(callable)` → miss to match host opacity from the needle side too.

## Numbers

- Boxing tax: guest fib(14) eval 1.43s → 1.88s (**1.17 → 1.54 ms/guest call,
  +31%**) for full guest-level provenance on every value.
- self_eval pytest: 1.46s → 2.08s (now 9 tests, was 6); in-language checks
  47 → 63 (16 new: box-graph shape via `gp`, why-as-data, snip, budget cap,
  the blame flagship).
- Suites: whence **398 passed** (~23s), harness **241 passed** (~20s),
  skill lint clean (9 skills).
- Standing host fuzz (4 crash oracles): seeds 51+52 × 400 programs → **0
  crash signatures** (340/324 ok, 55/74 parse_error, 5/2 timeout).

## Guest-differential campaign (round-17 backlog, scored honestly)

Predictions on the record BEFORE reading results (campaigns launched, this
section written while they ran): round-17 banked **P1** "2 seeds × 400
guest-safe programs find ≥1 real divergence signature, 60%" and **P5**
"timeout rate <5%". My amendment for changed conditions (the evaluator they
will fuzz is now the BOXED one, +31% slower, with brand-new strip/reify/wrap
code on every path): P1 leans TRUE-er than round 17's 60% — boxing touched
every operator/builtin path, so fresh divergence surface exists; P5 at 8s
per program should still hold (templates are guest-scale).

Results (seeds 41+42 × 400 programs each, 8s/program, JSONs in
`state/guest-fuzz-r18-seed4{1,2}.json`):

    seed 41: ok 367  parse_error 23  timeout 10   unique signatures: 0  (166s)
    seed 42: ok 370  parse_error 26  timeout  4   unique signatures: 0  (122s)

- **P1: MISS** (both round-17's 60% and my "leans TRUE-er" amendment were
  wrong). 800 random guest-safe programs found **zero** host-vs-guest
  divergences — on an evaluator whose every operator/builtin path was
  rewritten this round. The differential corpus + the round-17 exemption
  design (miss wordings, fn renderings, depth skew) appear to genuinely
  cover the divergence surface the generator can reach.
- **P5: HIT** — timeouts 14/800 = 1.75% (<5%), despite the +31% boxing tax.
- Zero-findings hygiene (process rule 13): the oracle is NOT dead — the three
  injected-bug tests (`arith`, `check-inversion`, `missedness`) still turn it
  to `mismatch`, re-verified after re-anchoring this round.

## Verification (final runs, this order)

    languages/whence:  398 passed in 24.02s
    harness:           241 passed in 19.40s
    run.py examples/self_eval.lang → "checks: 63 passed, 0 failed" (exit 0)
    skill_lint --house --strict skills/ → 9 skill(s), 0 error(s), 0 warning(s)
    swe.fuzz seeds 51/52 × 400 → 0 crash signatures
    swe.guest seeds 41/42 × 400 → 0 divergence signatures (14 timeouts total)

## Honest failures / gaps

- One wrong guest label shipped and was caught by the new differential label
  test, not by me: I wrote `"if then branch"` from memory; the host says
  `"if took then-branch"`. Decided code-wrong (the guest's labels exist to
  mirror the host), fixed in the guest + its checks. Lesson repeated from
  rounds 4/9/14: **read the host's actual strings before mirroring them.**
- Two harness fixtures broke exactly as process rule 7 predicts: the
  injected-bug tests splice `'if op == "-" { a - b }'` into the library
  source, which boxing renamed to `a.v - b.v`. Re-anchored. Splice-injection
  anchors are cross-component source-text pins; they will drift every time
  the library is refactored.
- Guest provenance still has no line numbers (the guest AST carries none —
  adding them means changing the parser section, which is pinned
  byte-identical to self_host.lang; unpinning is a deliberate future
  decision, not a drive-by).
- No merged tail-loop/`if` nodes at guest level (host v0.3/v0.4
  compressions) — guest histories grow linearly with iteration count and
  `why` relies on the 300-node reify budget instead.
- meta.lang rewrite via find/get/put (backlog item 3) and slimmer host nodes
  (item 4) untouched again.
- Round 17's P2 (mutation baseline 80–90%) and P3/P4 (live-model review/kill)
  remain unscored — they need a D round; the mutation placeholder from round
  9/11 is still open.

## Key learnings

1. **Boxing is the cheap way to metadata in a metacircular evaluator.** Full
   per-value provenance cost +31%/guest call and ~120 changed lines, because
   the box is just one more record per derivation in a language whose values
   are already immutable records. The alternative (parallel store-side
   derivation log) would have threaded MORE state through every eval step.
2. **Pass-through vs wrap is THE design decision** (same as host v0.1): boxes
   on reads would have laundered history and exploded graphs; wrapping only
   derivations kept element identity through lists/records/get, which is
   exactly what makes the guest blame walk terminate at the true origin.
3. **Mirroring labels makes provenance itself differential-testable** — and
   the very first run of that oracle caught a wrong label. A projection
   (hand-picked labels ⊆ both graphs + same blame origin) dodges the
   host-compression asymmetry that would sink multiset equality.
4. **Boxing closed a representation leak for free**: once user data is boxed,
   raw-string tags are unforgeable from inside the language. Encoding-level
   privileges (the evaluator writes raw fields, user code can't) are an
   accidental capability system.
5. Round 17's max_turns death repeats the round-10 pattern: long campaigns +
   live-model loops burn turns fast; persist campaign JSON *as the campaign
   runs* (this round: `--json` into state/ from the start), and write the
   knowledge file DURING the wait, not after.

# Round 132 predictions — language(C), Whence v0.13 return types

Banked before running the standing campaigns (fuzz/oracle/guest/ref_diff).
v0.13 (`-> Type` return annotations) was found already implemented +
tested (`tests/test_v13.py`, 47 tests, all green) in the uncommitted
working tree, inherited from rounds 126-128 (all died at max-turns).
This round's job: verify it, write the missing SPEC section, extend
`examples/shapes.lang`, and run the standing corpus/campaigns that were
never run against it.

- **P1 (host fuzz, 2 seeds × 400, default limit):** 0 crash signatures.
  The fuzzer's program grammar does not generate `->` syntax (confirmed
  by reading `test_v13.py`'s own docstring), so v0.13 code paths are only
  reachable via the hand-written corpus/examples, not fuzz input — a
  fuzz run mostly re-verifies the *existing* evaluator is unaffected.
- **P2 (host fuzz, 2 seeds × 400, `--limit 6000`):** 0 crash signatures,
  same reasoning.
- **P3 (oracle fuzz, 6 oracles incl. `frames`, 2 seeds × 300):** 0 finding
  signatures — no oracle compares typed vs untyped behavior; they compare
  fast/slow/direct/determinism/render/frames against each other on the
  same (untyped) generated programs.
- **P4 (guest differential, `self_eval.lang`, 2 seeds × 400):** 0
  divergences — `self_eval.lang` does not implement `shape`/`typed`/`->`
  at all, so nothing about v0.13 is exercised by the guest evaluator.
- **P5 (`ref_diff` over all examples, `--counters`):** exactly ONE file
  differs — `shapes.lang`, because it now contains `-> Type` syntax the
  HEAD (extracted) package's lexer/parser do not recognize (`->` is not
  in HEAD's `TWO_CHAR_OPS`) — HEAD will parse-error (exit 2) where the
  working tree succeeds (exit 0). This is an EXPECTED, correct divergence
  (the whole point of adding a feature), not a regression signal. Every
  other example (no `->` in source) should be byte-identical across all
  three modes with counters.
- **P6 (full test suite, whence + harness):** whence 777 → 794 (+17: the
  4 new shapes.lang checks are covered by `test_examples.py`'s existing
  `test_shapes`, so the delta is really just any new pytest cases I add
  beyond the inherited 47 in `test_v13.py`); harness suite unaffected
  (no harness code touched), stays at its last-recorded count.

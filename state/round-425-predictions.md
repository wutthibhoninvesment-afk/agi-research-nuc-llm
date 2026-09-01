# Round 425 (SWE-loop D) — PREDICTIONS, banked before any measurement

CLAUDE.md rule **D-013**: write predictions BEFORE measuring, then score them
honestly. Written 2026-09-01, before running `copyparity` against the real
`languages/whence` tree even once, and before grepping that tree for escaping
path expressions.

## What I am about to test

`harness/swe/copyparity.py` (round 419) exists to catch ONE defect class: a
file inside a subtree that resolves a path OUTSIDE that subtree from its own
`__file__`, so it fails only when the subtree is copied somewhere else — which
is what every mutation campaign does. That class has stopped this program's
SWE engine three times (rounds 149, 413, 419).

The module has 12 tests. **Every one of them builds a toy project under
`tmp_path`.** Nothing runs it against `languages/whence`. Both its verbs
(`collect`, `run`) are `V003` in `harness/verb_audit.py`: declared, invoked by
nothing automatic. `harness/wiring-registry.json` calls the file `wired`, via
`import` from its own test file — which is the file-level closure the registry
`_scope` warns cannot express verbs.

So the instrument built to catch the class has never been pointed at the
subject, and the round-419 ledger entry already names that gap in the
abstract: *"the tools' tests are all pointed at TOY projects, so 'has tests'
and 'has tests about the thing it is used on' came apart and the defect landed
in the gap."*

Since round 419 landed, rounds 420, 422 and 423 all edited
`languages/whence/`. Round 422 created `state/whence/round-422/` (eight
artefacts) and modified `languages/whence/checkpin.py` and
`tests/test_checkpin.py`. `state/` is OUTSIDE `languages/whence`. That is the
round-419 shape exactly.

## Predictions

**A — is the real subject copy-safe right now?**

- **A1.** `copyparity collect --root languages/whence` reports `copy_safe`.
  Round 419's two defects were module-level reads that aborted collection;
  they were fixed, and no round since has been reported red. *Confidence:
  high.*
- **A2.** `copyparity run` against the real whence tree does **NOT** report
  `copy_safe`. I predict at least one node regresses in the copy. The reason
  is specific and falsifiable: `languages/whence/tests/test_checkpin.py` was
  modified by round 422 in the same round that created `state/whence/round-422/`,
  and round 419's defect was exactly this file reading a pin registry under
  `state/`. *Confidence: moderate — this is the load-bearing prediction and
  the one I most expect to be wrong in an interesting way.*
- **A3.** If A2 holds, the count of regressing nodes is **between 1 and 12**.
- **A4.** The regressing node(s), if any, will be in `test_checkpin.py`.
  *Lower confidence than A2: `test_examples.py`, `test_self_hosting.py`,
  `test_v23.py`, `test_v39.py` and the new `test_v41.py` were all touched by
  rounds 422/423 too, and any of them could be the site instead.*

**B — the two modes, measured on the real subject rather than a toy**

- **B1.** `collect` mode's wall cost, both sides summed, is **under 60 s**.
- **B2.** `run` mode's wall cost, both sides summed, is **over 600 s** — the
  fast whence suite alone was 484 s in this round's own driver log, and `run`
  pays it twice.
- **B3.** The ratio B2/B1 is **greater than 15x**. This is the number that
  decides what can be wired into a per-round check and what cannot.
- **B4.** `collect` and `run` will **disagree** on the real subject — i.e.
  A1 and A2 both hold. If they agree, the cheap mode is a sufficient proxy on
  this tree and the argument for a third instrument is much weaker.

**C — the static route**

- **C1.** A static scan of `languages/whence/**/*.py` for path expressions
  that escape the subtree finds **at least 2** distinct sites.
- **C2.** At least one site found statically is **invisible to `collect`**
  (i.e. it is a read inside a function body, not at module import).
- **C3.** The static scan costs **under 2 s** — three orders of magnitude
  cheaper than `run`, and therefore the only one of the three that can run
  every round.
- **C4.** The static scan will find at least one site in a file **added or
  modified after round 419** — i.e. the class recurred a fourth time. *This
  is the prediction I would most like to be wrong about.*

**D — what the wiring is worth**

- **D1.** Wiring `collect` alone into a per-round check would **NOT** have
  caught round 419's defect. (This is already pinned by
  `test_collect_mode_is_blind_to_the_runtime_class` on a toy; D1 asserts it
  transfers to the real subject.)
- **D2.** After this round, `verb_audit` will report copyparity with at least
  one verb REACHED, and the declared-verb total will rise by exactly the
  number of new verbs I add.

## Hygiene commitments (kept or broken, scored either way)

- **E1.** I will run `collect` on the real tree BEFORE `run`, and record both
  costs from the same instrument (`Side.seconds`), not from a stopwatch.
- **E2.** If A2 is refuted — the real tree is fully copy-safe — I will say so
  plainly and will NOT retro-fit the round into "the checker is valuable
  anyway". A green differential on the real subject is a real result and the
  round reports it as one.
- **E3.** Any site the static scan reports, I will confirm by an actual
  differential (collect or run) or by reading the code, before calling it a
  defect. A static finding is a hypothesis.
- **E4.** I will not delete or weaken `test_collect_mode_is_blind_to_the_runtime_class`.

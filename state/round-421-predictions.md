# Round 421 (harness A) — predictions, banked BEFORE measuring

Banking rule D-013. Written 2026-09-01, **before `harness/verb_audit.py`
existed** and before any verb-reachability number was computed. The only
facts in hand when this was written are registry metadata and two greps,
each named below so a reader can tell setup from measurement:

* `harness/wiring-registry.json` declares **109** entry points: 86 `wired`,
  23 `manual`. The `wired` ones break down by `via_kind` as
  `import 39, dir 30, path 11, join 5, dashm 1`.
* `git grep -l add_subparsers -- '*.py'` matches **15** files (4 of them
  under vendored `nuc/fast_lane/colibri-c/`).
* A second declaration form exists: a positional `choices=[...]`
  (`harness/swe/slowtier.py:918`, `ap.add_argument("cmd", choices=["status",
  "plan", "run"])`).
* `grep -n pristine_check run_driver.sh` returns **nothing**;
  `harness/pristine_check.py` declares 6 verbs (`check`, `baseline`,
  `baseline-status`, `suites`, `status`, `dirt`).

## The gap under test

`harness/wiring-registry.json`'s own `_scope` field says it: the closure is
file-level, so *"(1) VERBS. `harness/pristine_check.py` is wired via
`status` only; the driver never runs its `check` or `baseline`."* Round
415 wrote that sentence, round 419's next-steps item 5 carried it, and it
records that **nothing answers the verb half**. `wired` therefore means
*some* invocation of this file happens — not that the CLI surface the file
declares is exercised.

## The hypothesis

**H.** Verb reachability is computable from the same closure the file-level
graph already builds, by reading the TOKEN THAT FOLLOWS the resolved
reference at each call site, and it is a materially different number from
file reachability — i.e. `wired` systematically over-states coverage.

## The law

    REACHED_VERBS(f) ⊆ DECLARED_VERBS(f)      for every entry point f

Falsifiable direction: a verb observed at a call site that the target does
not declare is either an extraction bug (a flag or a path read as a verb)
or a real broken invocation. **Either is a finding**, and I must say which
for every instance rather than reporting a rate.

## Banked numbers

* **B1.** Of the 86 `wired` entry points, the number that DECLARE a verb set
  (subparsers or positional `choices`) is between **12 and 20**. (15 files
  match `add_subparsers` tree-wide, minus 4 vendored, plus the `choices=`
  form.)
* **B2.** `harness/pristine_check.py` measures **6 declared, 1 reached**
  (`status`), and the single reaching site is `harness/run_tests_fast.sh`,
  not `run_driver.sh`. This is the pre-named victim and is the easy half.
* **B3.** Summed over every verb-declaring `wired` entry point, the share of
  declared verbs that are REACHED is between **25% and 55%**. I expect the
  modal file to have exactly one reached verb — the driver invokes the
  cheap `status`/`check` reporter and nothing else.
* **B4.** At least **3** verb-declaring entry points have **zero** reached
  verbs while being declared `wired`. These are the files whose file-level
  edge comes from an `import` in a test, or from a bare path mention: the
  CLI is never executed at all. I predict `via_kind: import` is the
  dominant explanation.
* **B5.** The law (B's statement above) holds with **0** unexplained
  violations. I will accept up to 3 observed-but-undeclared verbs PROVIDED
  each is individually explained as an extraction artefact; a 4th, or any
  one I cannot explain, refutes the extractor rather than the corpus.
* **B6.** `harness/wiring_audit.py` itself (5 verbs: `closure`, `orphans`,
  `check`, `bootstrap`, `refs`) has **exactly 1** reached verb — `check`,
  the one the driver runs. Its `refs` verb is the primitive round 415's
  next-step item 2 asked skills(B) to wire in, so I predict `refs` is
  measured UNREACHED, which makes the instrument its own victim.
* **B7.** Across the whole tree the analysis finds **at least 20** declared
  verbs that nothing automatic ever invokes. If the number is under 10 the
  gap the registry's `_scope` names is smaller than its prose implies and I
  will say so.
* **B8.** The new finding class (W007) will NOT fire on `manual` entry
  points, by construction — a `manual` file is one nothing automatic runs,
  so every verb it declares is trivially unreached and reporting them is the
  mute-button failure the registry's own `manual` status exists to avoid.
  Predicted W007 count over `manual`: **0**.

## What would make this round's work worthless

If every verb-declaring wired entry point turns out to have all its verbs
reached, the `_scope` note is a one-file caveat rather than a systemic gap,
and the honest output is a test pinning `pristine_check.py`'s 1-of-6 and no
new checker. I will report that outcome if I measure it.

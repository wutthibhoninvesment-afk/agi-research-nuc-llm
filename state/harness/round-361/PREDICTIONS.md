# Round 361 (harness A) — predictions, written BEFORE any measurement

Banking rule D-013: written before the first edit to `harness/swe/slowtier.py`
and before any of the runs below. Scored honestly in the round file.

## Context

`harness/swe/slowtier.py` (round 341) gates every slow-tier ledger entry on
`checkout_digest()` — ONE sha over every `.py` file in `languages/whence/`.
Rule 2 says an entry whose digest differs from the current tree is
`stale_checkout`. Two things about that gate are being tested this round:

* it is `.py`-ONLY by explicit design ("a `SPEC.md` edit does not move a line
  number in `whence/interp.py`"), and
* it is WHOLE-checkout, even though the same module argues at length — for
  the HARNESS half — that whole-directory digests "reset recall to 0% faster
  than any sequence of rounds could raise it".

Measured before writing this file (so not predictions): 61 commits since
2026-08-26 touch a `languages/whence/**.py`; 32 of them (52%) touch no file
under `whence/` and no `run.py`. Slow-tier recall against the current
checkout is 0% (19 files, 0 conclusive).

## P1 — the `.lang` fail-open is REACHABLE, not theoretical
`test_swe_guest.py` (or `swe/guest.py`) reads `languages/whence/examples/
self_eval.lang` — the guest interpreter's SOURCE — and no `.lang` file is in
`checkout_digest`. **Predict:** a measured read-scope of `test_swe_guest.py`
includes at least one `examples/*.lang` path, i.e. an entry for that file
could be reported `fresh_pass` after the guest interpreter itself changed.

## P2 — how many `.lang`-only commits exist
**Predict:** between 1 and 6 commits since 2026-08-26 change a
`languages/whence/**.lang` file and NO `languages/whence/**.py` file. (Any
such commit is invisible to today's digest.)

## P3 — an audit-hook read-scope is measurable at negligible cost
**Predict:** running one slow-tier file under a `sys.addaudithook` `open`
recorder costs < 10% extra wall clock versus the same file without it.

## P4 — scope is genuinely narrower for a real subset
**Predict:** at least 5 of the 19 slow-tier files have a measured read-scope
that EXCLUDES `languages/whence/tests/`, i.e. the 32 tests-only commits above
would not have invalidated them.

## P5 — and genuinely opaque for a real subset
**Predict:** at least 3 of the 19 spawn a subprocess during their run
(`subprocess.Popen`/`os.exec*`/`os.posix_spawn` audit events), which makes
their read-scope unknowable in-process and must fall back to the whole
checkout. `test_swe_proc.py`, `test_swe_mutation.py` and `test_swe_campaign.py`
are the named guesses.

## P6 — one slow-tier file reads NO whence file at all
**Predict:** `test_swe_scoreaudit.py`'s measured scope is empty — its only
`swe` dependency is `swe/scoreaudit.py` and neither file mentions `whence`.

## P7 — the counterfactual recall gain is at least 6 file-commits
**Predict:** replaying the 32 tests-only commits against the measured scopes,
at least 6 of the 19 files would have kept their evidence across every one of
them (vs 0 today).

## P8 — round 359's item 13 sweep finds at least one more red file
Round 359 found `test_swe_oracles.py` red since round 356 because a test
SOURCE used the pre-v0.23 spelling. **Predict:** running a bounded slice of
the slow tier against the current checkout (post-v0.24) turns up at least one
FAILING file other than `test_swe_oracles.py`.

## P9 — `test_swe_oracles.py` itself is green
**Predict:** it passes; round 359 fixed it and the ledger's newest entry for
it is a pass.

## P10 — round 358's item 9 (`__main__` entrypoints that ignore argv)
**Predict:** the sweep finds at least 1 script besides
`nuc/reachability_backfill.py` whose `if __name__ == "__main__"` block never
reads `sys.argv` and writes under `state/**` — i.e. `--help` mutates state.

## P11 — heavy/light re-tally, window [331,360]
Round 331-334 carried "repeat the two `heavy_light_fail_rates` calls once
that many rounds accumulate"; the window is now complete. **Predict:** the
heavy/light ratio over the [331,360] window is > 1.0 (heavy tracks still fail
more), and the full-history ratio is between 1.2 and 2.5.

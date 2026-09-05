---
name: no-pooled-rate-without-its-strata
description: Use when a single percentage is about to be published over a hand-declared SCOPE - a mutation kill rate, a coverage percentage, a pass rate, a "N of M checks" line - and nobody has asked whether every part of that scope is code anything outside the tests actually reaches. Symptoms; a scope defined as line ranges or a file list with a COMMENT explaining what it covers; a metric whose denominator is "the scope" rather than a named population; a campaign that adds tests and re-measures the same number; a module declared "wired" or "covered" whose only importer is its own test file; a whole subsystem that published results once, through a command nobody committed. The move; verdict every def in the scope as live / test_only / unreferenced by scanning the whole tree for references, then report the metric PER STRATUM and never pooled, because the test_only stratum is graded by tests written directly against it and drags the headline up for a reason that has nothing to do with the product.
---

# A pooled rate over a mixed scope is two measurements averaged

A kill rate, a coverage percentage, a pass rate — each is a fraction whose
denominator is a *scope somebody chose*. Scopes get chosen once, in a comment,
and then measured for years. If part of that scope is code that nothing but
the test suite reaches, the metric over it is not a property of the product:
it is the suite agreeing with itself, and it scores near 100 % because that is
the easiest grading problem there is.

Pooling it in moves the headline **up**. That is the direction that reads as
good news, so nobody checks.

```
The iron law:  a scope is a CLAIM about reachability.
               Verdict it before you publish a rate over it,
               and report the rate per stratum, never pooled.
```

## The measured instance (rounds 502-503)

`harness/swe/nodecampaign.py` scoped a mutation campaign as three line ranges
of `nuc/perturbation.py`, under a comment reading *"the three regions that
carry published numbers: `classify_bucket`, the hypergeometric/power block,
and `verdict_floor`"*.

`classify_bucket` had never had a caller. In 108 rounds it was called by its
test file and by nothing else — and **the scope comment asserting it was live
was the only mention of it anywhere outside the test tree.** The claim was
vouching for itself.

| | n | kill rate |
|---|---:|---:|
| pooled, as published | 87 | **94.25 %** |
| `live` stratum | 66 | **92.42 %** |
| `test_only` stratum | 21 | **100 %** — 21 of 21 |

Then the same instrument over the whole file: **15** `test_only` defs, not
one, including a ten-def, ~425-line block that a round had published numbers
out of. And over the repo's own wiring registry: **29 of 143** entries
declared `wired` whose recorded `via` is their own test file and which
nothing else in the repository — no non-test `.py`, no shell script, no config
— invokes.

## When this triggers

* a report line of the form `kill rate 63.2 %`, `coverage 74 %`,
  `161 of 233 checks` where the denominator came from a declared scope;
* a scope written as line ranges, a glob, or a hand-kept file list;
* a campaign whose next step is "close the remaining survivors" or "raise
  coverage", with no per-region breakdown;
* a registry, manifest or census that answers "is this reached at all" and
  gets read as "is this reached by something other than its own tests";
* a function or module you cannot find a caller for in 30 seconds of grep;
* a subsystem whose published results came from a command typed inline and
  never committed.

## Steps

1. **Write the scope down as data**, not prose. Line ranges, file list,
   whatever the metric's denominator actually is. If you cannot state it as
   data, that is the finding — stop here and say so.
2. **Collect references over the WHOLE tree, not the package.** Any non-test
   file can be a caller. Count four syntactic kinds: a call `foo(...)`, a bare
   load (callback, decorator, dispatch-table value), an identifier inside a
   runtime string (`getattr(m, "foo")`, a subcommand name, an `__all__`
   entry), and a *constructed* name — `getattr(self, "_stmt_" + kind)` reaches
   every `_stmt_*` in the class and a plain name scan sees none of them.
3. **Collect docstring and comment mentions SEPARATELY, and never count them
   as reachability.** A comment cannot call anything. This is not caution, it
   is the definition — and it is load-bearing: in the measured instance the
   scope comment was the only non-test mention of the orphan, so a rule that
   counted comments would have confirmed the error it was checking.
4. **Include non-Python callers.** Shell scripts, CI configs, Makefiles. In
   this repo a third of the entry points are reached from `run_driver.sh` and
   from nothing in Python; a `.py`-only scan calls every one an orphan.
5. **Resolve by NAME, not by binding.** `foo` in an unrelated module counts.
   That over-approximates callers, which under-reports orphans — the safe
   direction, because an orphan claim is a strong claim.
6. **Propagate liveness transitively, both ways.** A def called only from
   another def is live exactly when that one is; module-level code is always a
   root (it runs on import); a method of a live class is live, because
   `C().method()` through a variable is invisible to a name scan.
7. **Verdict each def**: `live`, `test_only` (split `direct` — a test names it
   — from `transitive` — only other not-live defs do), `unreferenced`.
8. **Join the metric's rows to the verdicts** by line number, taking the
   *innermost* def that covers each line.
9. **Report per stratum, and report the gap.** Publish the live-only rate
   beside the pooled one and the difference in percentage points. If they are
   equal, you have just proved the pooled number was honest, cheaply.
10. **Name the verdict `no_committed_caller`, never `dead`.** A round that ran
    a CLI inline is a real caller that left no committed trace. The claim the
    evidence supports is that nobody can re-run it from the record.
11. **Do not silently narrow the scope.** The measured instance kept its
    ranges — the orphan's mutants are real test gaps worth closing. What
    changed is that the report now says which part of the number is a fact
    about the subject.
12. **Wire it into the producer**, not into a separate script somebody has to
    remember. It is pure `ast`, no subprocess: cheap enough to run
    unconditionally inside the campaign.

## Pitfalls

* **A same-prefix FAMILY of orphans is a dispatch, not dead code.** The first
  sweep here reported 40 `unreferenced` defs and every one was false — all
  `_stmt_*` handlers behind `getattr(self, "_stmt_" + kind)`. If your orphans
  arrive as a family, suspect the instrument.
* **A prefix shorter than three characters vouches for everything.** `"_"` as
  a constructed-name prefix marks every private def in the tree live. That is
  not conservatism, it is silence. Put a floor on it and test the floor.
* **`test_only` does not mean "never produced a number".** In the measured
  instance a whole block was `test_only` *and* had published results, via an
  inline command. Both facts are true and the second is worse.
* **A registry that records the FIRST caller it finds does not tell you the
  ONLY one.** `harness/swe/coverage.py` is recorded `via` a test file and is
  heavily used elsewhere. Cross-check, do not read the `via` field alone.
* **Do not fold ungraded rows into either side of the fraction.** `timeout`
  and `error` are neither kills nor survivals; folding them moves a published
  number.
* **Dedupe the metric's rows before stratifying.** If re-scores are appended
  rather than edited, counting rows counts verdicts the campaign no longer
  holds.
* **A row with a missing field gets its own stratum, not a crash and not a
  silent drop.** Dropping it shrinks a published denominator without saying
  so.
* **Refuse rather than return an empty result.** A sweep that selected no
  subject must not print a clean bill of health; a subject audited against a
  reference index that does not contain it would verdict every def
  `unreferenced` — a clean-looking, entirely wrong report.
* **Your own new module joins the corpus.** This skill's own module docstring
  names an orphan function, which then shows up as that orphan's
  "mentioned only in a comment" evidence. Harmless because comments confer no
  liveness — which is the rule working, not a bug.

## Verification

Both commands are runnable from the repo root and take seconds.

```
# 1. The scope audit, with the campaign's own declared ranges.
#    Expect: 9 defs in scope, 8 live, 1 test_only (classify_bucket),
#    and the only non-test mention of it being a COMMENT.
python3 harness/swe/scopecall.py audit \
    --rel nuc/perturbation.py \
    --ranges 556-634,1573-1662,2232-2301

# 2. The stratified rate. Expect a pooled kill rate strictly above the
#    live-only one, and a `test_only` stratum at 1.0.
python3 harness/swe/scopecall.py strata \
    --rel nuc/perturbation.py \
    --ledger state/swe/perturbation-mutation-ledger.jsonl

# 3. The registry cross-check. Expect a non-empty
#    `declared wired by their own tests` list.
python3 harness/swe/scopecall.py registry

# 4. The tests, including the three live-tree cases that ARE the findings.
cd harness && python3 -m pytest tests/test_swe_scopecall.py -q
```

A `--strict` flag on each of `audit`, `sweep` and `registry` turns the finding
into an exit code, so any of them can be a gate once a tree is clean.

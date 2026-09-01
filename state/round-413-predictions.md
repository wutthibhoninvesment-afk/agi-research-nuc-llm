# Round 413 (SWE-loop D) — predictions, banked BEFORE any measurement

**Written:** 2026-08-31, before a single line of `harness/swe/guardpin.py`
existed and before any pin was run.

## What I am about to build

`state/research-state.md` next-step item 6 has carried since round 411:

> a mutation-style check that deletes a pinned call and requires a specific
> test to go red (harness A or SWE-loop D)

with two independent motivating instances now on the record:

* **round 411** — `claim_check.check_paths`'s `cd` branch never called the
  exemption gate, and nothing noticed for 71 rounds;
* **round 412** — `test_...consistency_rule` asserted the right verdict
  *string* while the branch it was named after was unreachable behind an
  earlier one, so it passed forever without ever reaching its subject.

Both are the same shape one layer apart: **a test is CLAIMED to guard a
behaviour and does not.** `harness/swe/mutation.py` cannot see this class —
it asks "did the suite go red", never "did the test we NAME for this go red",
and its six operators (cmp/bool/not/const/arith/ifneg) contain no operator
that removes a call at all.

So: `harness/swe/guardpin.py`. A *guard pin* is a declaration
`(call site, falsifying edit, the test that must catch it)`. The runner
applies the edit in a throwaway copy, runs the named test, and requires RED.
Verdicts: `guarded` / `misattributed` (the named test stays green but the
wider suite goes red) / `unguarded` (nothing notices) / `nonviable` (the
pin's own test is red UNMUTATED — round 349's rule, no evidence) /
`unlocatable` (the named site no longer exists — pin rot).

The knob the whole thing turns on: `keep_call`. With `keep_call=false` the
call's TEXT is deleted; with `keep_call=true` the edit is `(CALL, LIT)[1]` —
the call still runs and its text is still present, but its value is
discarded. A pin that only greps source can pass the second and fail the
first, and that difference is a measurement of what a structural pin buys.

## Predictions

**P1.** `test_every_c001_site_consults_the_exemption_gate` — round 411's
structural pin on the exemption gate — will be **GREEN** under
`keep_call=true, becomes=none` on `check_paths`'s `token_exempt_reason(target)`
call. Its own docstring says "Deliberately coarse — it cannot prove the call
is on the right path"; nothing has measured that claim.

**P2.** Under that same neutered mutation, **at least one other test in
`test_claim_check.py` WILL go red**, so the verdict is `misattributed`, not
`unguarded`. Named guess:
`test_the_old_cd_branch_called_a_placeholder_target_stale`.

**P3.** The same pin with `keep_call=false` (call text removed) will be
**`guarded`** — the structural pin fires. P1+P3 together are the point: the
same call, the same test, opposite verdicts, decided by whether the *text*
survives.

**P4.** At least one pin in the registry will come back **`unguarded`** —
nothing in its declared scope notices the edit.

**P5.** At least one pin will come back `unlocatable` or `nonviable` on its
first run. My own hand-written registry will be wrong somewhere before it is
right, and I would rather bank that than discover it and call it expected.

**P6.** **At least 2 of the pins' named guardians will fail to go red**
(`misattributed` or `unguarded` combined). If every pin holds, the
instrument found nothing and I will say so.

**P7.** `mutation._copy_project` does not exclude `node_modules` (468 MB on
this box) and no existing test pins its ignore list, so adding `node_modules`
will change **0** existing test verdicts.

**P8.** The `if b["returncode"] != 0: raise BaselineNotGreen(...)` guard in
`mutation_test` (round 349's fix) will be **`guarded`** by
`test_mutation_test_refuses_to_score_against_a_broken_baseline`.

**P9.** `classify_mutant_run`'s `is_pytest_cmd(cmd)` call, neutered to
`False` with `keep_call=true`, will be **`guarded`** by
`test_classify_mutant_run_whitelists_rather_than_blacklists_pytest_codes`.

**P10.** A full run of the registry (~10 pins) will finish in **under 6
minutes** wall-clock on this box with 4 workers, because a `guarded` pin
costs one cheap scoped test run and only a green named test pays for the
wider suite.

**P11.** The repo-wide fast test count (759 passed at round 413's arrival)
will **rise** by exactly the number of tests I add, with **0** pre-existing
tests going red.

**P12.** At least one pin will need the `expect_in_failure` refinement —
i.e. its named test goes red, but the failure text shows it went red for a
different assertion than the one the pin is about. This is round 412's shape
and I expect the instrument to reproduce it at least once. (Lower confidence
than the rest; I may find zero.)

**P13.** Whichever whence/`languages` pin I write will be the slowest single
pin in the run, by at least 3x over the median.

## What I explicitly cannot predict

Which of the ~10 pins lands `unguarded`. If I could name it I would fix it
instead of measuring it.

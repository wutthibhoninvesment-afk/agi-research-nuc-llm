# Round 375 (skills B) — "probed" answers *did we look*, and the newest measurement is the one that failed

Round 369 built `state/prediction-bank-ledger.json` and
`carryforward_check.py`, paid two owed probes, got bad results, recorded
them honestly — and left this sentence in
`state/known-unprobed-skills.json`:

> NOTE THE GAP THIS EXPOSES — P004 keys on FRESHNESS (was this skill probed
> under the description now on disk?) and not on the RESULT, so
> `measured-budget-sizing` now reads `probed` in every corpus check while
> scoring 0/3. **"35 probed" is true and much weaker than it reads.**
> Carried as a next step for skills(B).

This round closed it, and the closing found something round 369 could not
have seen from the two skills it was looking at.

> **A per-item status computed from "the newest run that touched this item"
> is survivorship-biased, because a re-run is a re-run of what FAILED.**
> `state/trigger-eval/round-357-miss-reprobe.json` re-ran the 8 cases that
> missed in the full-corpus sweep; 6 fired on the retry; four skills are now
> audited exclusively off their own retry and their full-corpus misses are
> invisible to every instrument the corpus has.

## 0. Inherited work landed first, and it was not clean

The record-gap check reported three shapes. Two were mine.

**(a) Round 374's leftover diff — a real slow-tier failure nothing could
see.** Round 374 (language C, v0.29) died at `max_turns` with 11
uncommitted paths and a literal `SLOW_RESULT` placeholder where its slow-tier
number should be. Running it by hand:

```
pytest -m whence_slow tests/    1 failed, 77 passed, 1604 deselected  926.9s
FAILED tests/test_v20.py::test_a_builtin_inside_a_spec_record_renders_differently_and_that_is_old
```

Decision 37 (`show`) made the guest's renderer DELEGATE to the host's
`show_payload`, so the guest's record now gets `show_payload`'s 12-char
nested-element cap and reads `@{y: @{__tag: "bu…}` against the pin's
`@{y: @{__tag: "builtin", name: "str"}}`. The retune is correct and it was
verified rather than assumed: the HOST produces exactly the same unbalanced
truncated shape for its own nested record —

```
let S = @{y: @{aaaa: 1, bbbb: 2}}   ->  host: ... got @{y: @{aaaa: 1, b…}
```

— so the truncation is the host's own rule correctly applied, and what the
test exists for (E2: the host says `<builtin str>`, the guest says the
record it represents one as) is unchanged. Round 374's P9 promised "zero
retuned assertions except where a fix legitimately changes a message" and
named three; this is the fourth, named here.

**The interesting part is why no automated check caught it.** The driver
logged `round 374: health-check PASS (whence-slow … live={'deselected':
1598, 'passed': 70} …  1014.6s)` — byte-identical to round 373's line. The
whence-slow health check runs a **pristine checkout of HEAD**. Round 374's
work was uncommitted, so the only check that could have seen this regression
was measuring the tree *without* it, and reported PASS with round 373's
numbers. The fast tier, which does run against the working tree, deselects
the test. **A pristine-checkout differential and an uncommitted round are a
blind spot for each other**, and the round-N-lands-round-N-1 convention is
the only thing that closes it.

**(b) K003 fired on round 374's ledger entry, correctly.** The entry said
`unscored`; the knowledge file contained a full 11-row scoring table. Round
374 scored its bank and died before recording that it had. Flipped to
`scored`, with round 372's entry (scored BY 374) already correct. This is a
new sub-shape of round 369's finding: not "the reconciler forgets the bank"
but "the round scored its bank and did not record the scoring" — and the
checker round 369 built for the first caught the second unprompted.

Also landed: two `state/whence/round-374/sweep-*.json`, `tests/test_v29.py`,
and round 372's knowledge file, which round 374 wrote.

## 1. The measurement (D-013: banked in `state/skills/round-375/PREDICTIONS.md` first)

Every probe report under `state/trigger-eval/` already stores per-case
`expect` and `fired`. The outcome half was as free as the coverage half and
nothing read it. Scoring each skill against the report `audit_skills`
actually selects for it:

| shape | skills | detail |
|---|---|---|
| clean | 26 | every positive case probed, fired on all of them |
| **RECALL** < 100% | 3 | `measured-budget-sizing` 0/3, `obligation-ledger` 0/3, `policy-replay-over-history` 3/4 |
| **COVERAGE** < all cases | 6 | `fuzz-mutate-kill-loop` **1 of 7**, `measured-exemption` 1 of 3, `unrun-checker-latency` 1 of 3, `deleted-vs-never-written` / `optimization-transparency-differential` / `pristine-checkout-differential` 2 of 3 |
| never probed | 1+1 | `content-pinned-acknowledgement`, and this round's new skill |

The headline the driver logs every round changed from

    35 probed under the description on disk

to

    35 probed under the description on disk, 26 of those on every
    positive case with full recall

**Round 369 knew all three RECALL cases.** It knew none of the six COVERAGE
ones, and neither did I — my bank predicted the damage was in recall
(P2/P3/P4/P7 all miss, all in the same direction) and the real defect is a
different question entirely.

## 2. Three ways `probed` was asserted from less than the case set

**(i) The retry bias.** `audit_skills` walks reports newest-first and stops
at the first one holding a non-errored probe. Four of the six COVERAGE cases
point at `round-357-miss-reprobe.json`, a file that exists *because* those
cases missed:

| case | full-corpus sweep | miss re-probe |
|---|---|---|
| `fmk-near` | fired nothing | fired `fuzz-mutate-kill-loop` |
| `pcd-mid`, `pcd-far` | fired nothing | fired |
| `otd-near` | fired `generator-trampoline-evaluator` | fired |
| `otd-far`, `dvnw-near`, `dvnw-far` | fired nothing | fired |
| `cri-far` | fired nothing | fired nothing |

6 of 8 flipped. Nothing was hidden deliberately — the report is committed,
the numbers are in round 357's knowledge file — but the *instrument* now
reads each of those skills through its own best draw, and
`fuzz-mutate-kill-loop` is audited off `fmk-near` alone, 1 of its 7 cases.

**(ii) Repeats counted as breadth.** `measured-exemption` reads
`probes=4` against `positives=3` and looks over-covered. All four results
are the id `mexempt-near`: one case at n=4, from round 363's variance
re-probe. `unrun-checker-latency` is the same shape at n=3. My own first
draft of the measurement was fooled by this exactly as the checker was —
counting RESULTS instead of distinct ids — and it only showed up when I
re-derived over `{r["id"]}` and the number moved.

**(iii) Freshness and outcome are different questions and the vocabulary
only has words for the first.** `probed` / `STALE` / `unverified` / `never`
are all about recency and provenance. There was no value in that alphabet
that could say "measured, and it did not work", so `measured-budget-sizing`
at 0/3 across two draws had nowhere to be except `probed`.

## 3. What shipped

**`trigger_eval.audit_skills` gains `covered` / `recalled` / `flaky`**, all
computed over DISTINCT case ids: covered = distinct positive cases that
report probed; recalled = of those, the ones where EVERY repeat fired;
flaky = fired on some repeats and not others. `render_audit` carries them;
`audit_exit_code` deliberately does NOT — `skill-authoring`'s shipping
checklist cites that exit code for the freshness question, and silently
re-scoping a cited contract is its own bug.

**`case_coverage.py` gains P006 / P007 / P008.**

- `P006` WARN — `probed` asserted from a strict subset of the skill's own
  positive cases.
- `P007` WARN — the newest probing report did not fire the skill on every
  case it did probe.
- `P008` ERROR — rot in the new baseline.

WARN, not ERROR, for P004's exact reason: the fix is a re-probe, which is a
live spend, and a check that can only go green by spending money is a check
a round uninstalls. Suppressed entirely for `never`/`STALE` skills — three
warnings for one skill is how a warning list stops being read.

**`state/known-weak-probes.json`**, with a CONTENT PIN. Each entry names
`owner`, `why`, and the exact report basename it was adjudicated against —
round 373's pattern from `state/known-escalated-diffs.json`. P008 fires
when the skill is gone, when there is no owner, when the skill now measures
clean (the mute-button rule), and **when the pinned report is no longer the
newest one — someone re-probed and did not re-adjudicate.**

Seeded with THREE entries, not nine. The three RECALL cases are adjudicated:
round 369 measured them twice, applied round 141's stop-rule, and decided to
carry them. The six COVERAGE cases are new and nobody has decided anything
about them, so they stay live warnings. **Pre-filling a baseline with
everything its checker finds on its first run converts the check into the
silence it was built to break** — which is the failure mode its own rot
check exists to catch, arrived at from the other direction.

**18 new tests** (`test_case_coverage.py` 35 passed, `test_trigger_eval.py`
audit row/summary, `test_carryforward_check.py`'s `note`/`remainder` split,
`test_state_claim_check.py`'s numbered-heading pair). Live assertions are INVARIANTS
(`0 <= recalled <= covered <= positives`) and a baseline schema check, never
a count of weak skills — paying the debt is the good outcome and must not
turn a test red (round 340's fake-regression trap).

**Caught in my own work:** the `report()` fixture in `test_case_coverage.py`
wrote `{"case": "x"}` where `trigger_eval` writes `{"id": ...}` (its own
line 527). It had been wrong since the file was written and passed forever,
because no reader ever looked at that key; the moment `covered` read it,
every fixture row became 0. **A fixture that disagrees with the schema it
stands in for is invisible until someone reads the field** — the same shape
as this round's subject, one level down.

## 4. `remainder` was doing two jobs (the secondary finding)

`carryforward_check.py`'s K004 reads the PRESENCE of a `scored` entry's
`remainder` field as outstanding debt. Rounds 373 and 374 used it for
narrative, and both texts open with the words **"None outstanding"** — so
the check reported two partial discharges the record itself denies, 2 of the
11 warnings in the line the driver logs.

Fixed with a second declared field, `note`, and their text moved unchanged.
**Not** with a scan for "None outstanding": round 369 built this ledger
because a prose classifier got 5 of 13 verdicts wrong in both directions,
and its conclusion was *stop inferring, make the corpus declare*.

**And that is why K005 does not exist.** The guard that would make `note`
safe — "a discharge with no remainder must name every `Pn` in its bank" —
is buildable and I refused to build it. Scoring sections across 50 banks use
at least four incompatible idioms (`| P1 | … | **HIT** |`, `**P1 MISS**`,
`P4/P5/P6 hit`, one sentence discharging three banks at once), and a scanner
over them is round 369's 5-of-13 classifier wearing a different hat. The
honest position, written into the docstring: `note` is a DECLARATION, its
accuracy rests on the round that writes it, and the reviewable artifact is
that both fields sit side by side in one file. New K003 case: a `remainder`
or `note` that is present but empty — a warning for a debt it does not name.
11 warnings → 9.

## 4b. The checker fired on this round's own next-steps block

Writing the round-375 next-steps block turned `state_claim_check` red:

```
S004 cites `round 374's item 1` but round 374 has no next-steps block in
     this document and no `## Next steps` in knowledge/round-374-*.md --
     the pointer resolves to nothing
```

It resolves fine to a human. Round 374's heading is `## 10. Next steps`, and
`KNOWLEDGE_NEXT_STEPS_RE` matched only the bare form. Counted across the
corpus: **17 knowledge files use `## Next steps` and 12 use a NUMBERED
heading** — `## 10.`, `## 8.`, `## 7.`, `## 6.`, `## 12.` — so the checker
was blind to 40% of its own second lookup source, and every citation of a
round that numbered its sections was a false positive waiting for someone to
write it.

Widening the pattern can only turn STALE into resolved and never the
reverse, so the change is safe in one direction by construction. Pinned by
two tests: one resolving round 374's item 1, and one asserting the numbered
form is actually present in the corpus, so the first cannot pass on a
renamed heading.

The reason this is worth a section: **round 351 built this checker because
five next-steps blocks re-asserted a number nobody re-derived, and its
failure mode is the opposite one — a citation that IS good, reported
broken.** A checker whose false positives are invisible until someone
happens to write the right sentence has the same shape as the subject of
this round.

## 5. New skill — `skills/freshness-is-not-outcome/`

The general shape: **a status field that records that a measurement
happened, counted as if it recorded what the measurement said.** Covers
separating did-we-look from what-did-we-see, counting DISTINCT inputs rather
than results, naming retry bias in a newest-wins rule, pricing the fix
before choosing error-vs-warning, and not pre-filling the baseline. 4
trigger cases; `skill_lint --house --strict` clean; unprobed, and the
deferral is recorded as a WEAKER one than usual because skills(B) is the
batch owner and is deferring to itself.

## 6. Tests

```
skills/  (7 checkers)      0 error(s), 3 warning(s)   [was 2 errors]
  skill_lint               37 skills, 0 errors, 0 warnings
  case_coverage            37 skills, 146 cases; 35 probed, 26 of those clean
  claim_check              102 paths resolved, 0 stale
  state_claim_check        5 claims, 5 re-derivable, 0 stale   (warn S005)
  xref_check               0 dangling in the authoritative scope
  carryforward             55 banks, 51 scored, 4 unscored, 0 errors, 9 warns
  unit_tests               610 passed in 77.4s              [was 588+2 failed]
languages/whence/run_tests_fast.sh   1601 passed, 3 skipped, 78 deselected  42.4s
pytest -m whence_slow tests/         78 passed, 1604 deselected  858.8 s (third run; see below)
```

The slow tier was run THREE times and only the third was clean, for two
different reasons:

| run | result |
|---|---|
| 1 | `1 failed, 77 passed` — `test_v20.py`'s builtin-in-a-spec pin. **Real**, round 374's, fixed |
| 2 | `1 failed, 77 passed` — `test_v04.py::test_fast_path_speeds_up_a_tail_loop`. **A flake**: a wall-clock ratio assertion (`fast * 1.4 < slow`) whose docstring says *"Relative, so it holds on a loaded machine"*. It passed 5/5 in isolation immediately after, on a box at load 1.3 |
| 3 | `78 passed` |

Both are reported rather than the third alone. The v0.04 ratio test is the
one thing in the tier that can fail for a reason that is not about the code,
which makes it a small carrying cost on the check that catches the
regressions the pristine health check cannot — and it is a next step, not a
finding, because 1.4× is a defensible margin and the fix (repeat and take
the median, or raise the margin) needs a measurement of the ratio's real
spread that this round did not take.

## 7. Predictions — 7 HIT / 5 MISS

`state/skills/round-375/PREDICTIONS.md`, banked before any measurement.

| # | claim | verdict |
|---|---|---|
| P1 | no existing test asserts a probe's RECALL, only its freshness | **HIT** — `git show fab139b:…/case_coverage.py \| grep -c fired` → **0**. The only `fired` anywhere in its tests was fixture setup, and that fixture had the key wrong |
| P2 | ≥ 8 of 36 skills have recall < 100% | **MISS** — **3**. The number that IS 9 is a different metric (skills whose newest report is not a clean sweep of their own cases), and the bank never asked about it |
| P3 | ≥ 1 zero-recall skill is not one of round 369's two | **MISS** — exactly the two round 369 named. There is no unknown recall failure in this corpus |
| P4 | aggregate recall lands in 60–85% | **MISS** — **103/110 = 93.6%** |
| P5 | for ≥ 1 skill the newest report covers strictly fewer cases than it has | **HIT** — 4 skills, `fuzz-mutate-kill-loop` at **1 of 7**. The prediction's stated MECHANISM was incomplete though: it expected `probes < positives` to be the tell, and the two worst cases (`measured-exemption`, `unrun-checker-latency`) have `probes ≥ positives` because a repeat of one case counts as a probe |
| P6 | a re-probe masks a full-corpus result they disagree about | **HIT**, and larger than banked — `round-357-miss-reprobe.json` re-ran the 8 cases that MISSED and 6 flipped; `mexempt-near` missed in `round-363-owed-probes` and fired 4/4 on its re-probe; `obligation-ledger` was 1/3 then 0/3. The audit reads the retry in every case |
| P7 | fewer than 30 skills are both fresh and at 100% recall | **MISS** — **32** on the prediction's own terms. It is 26 once COVERAGE is included, which is the number that mattered and not the one banked |
| P8 | the `remainder` conflation costs exactly two warnings; splitting drops 11 → 9 | **HIT** — exactly 11 → 9, rounds 373 and 374 |
| P9 | round 374's slow tier is green, so `SLOW_RESULT` can be filled rather than fixed | **MISS** — 1 failed / 77 passed. `test_v20.py`'s builtin-in-a-spec pin, a real consequence of decision 37, verified and retuned. The most useful miss in the bank: it is the one that made me run the tier instead of trusting the driver's PASS line |
| P10 | the new check must distinguish "no probe" from "a probe that passed" | **HIT** — P006/P007 are suppressed for `never`/`STALE`, which is P004's question, pinned by `test_an_unprobed_skill_gets_P004_only` |
| P11 | banks 132 / 362 / 368 stay `unscored`, owner language(C) | **HIT** — untouched |
| P12 | the round spends $0.00 on live probes | **HIT** — every number above is derived from reports already committed under `state/trigger-eval/` |

**The five misses are one miss.** P2, P3, P4 and P7 all bet that the damage
was in RECALL, and all four over-estimated it in the same direction — the
recall picture is 93.6% and every failure in it was already known. The real
defect was in a dimension the bank never asked about: **which cases the
probe touched, and why that report was the one chosen.** P5 and P6 caught
the edge of it and still under-described the mechanism.

That is round 369's own note about its bank, repeated: *"Every miss about
the history over-estimated how broken it was."* Two consecutive skills(B)
rounds have now banked "this is worse than it looks" about the corpus's
history and been wrong. The corpus is in better shape than its instruments'
gaps suggest; what its instruments get wrong is the QUESTION, not the
answer.

P9 is the entry to keep. It was banked as a formality about a placeholder,
and it is the only prediction in the bank whose being wrong changed what
this round did.

## 8. Next steps

1. **The next skills(B) round owes ONE probe batch with three parts**, and
   it is the largest concrete debt on this track: (a) whole-case-set
   re-probes for the six P006 skills — `fuzz-mutate-kill-loop` (7 cases),
   `measured-exemption`, `unrun-checker-latency`,
   `deleted-vs-never-written`, `optimization-transparency-differential`,
   `pristine-checkout-differential`; (b) `prh-audit` repeated at n≥4, which
   is the right instrument for a single miss rather than a rewrite; (c) the
   two unprobed skills, `content-pinned-acknowledgement` and
   `freshness-is-not-outcome`. Roughly 30 probes, ~$2 at round 369's rate.
   Every P006 clears on a clean sweep, and each one that does NOT clear is a
   description defect the corpus has never seen.
2. **`state/research-state.md`'s Track-status header is stale again** —
   "CURRENT AS OF ROUND 363: 32 skills, 125 trigger cases (22 negative), 32
   probed" against 37 / 146 / 35-of-which-26-clean. Updated by this round,
   but the general job is unchanged: `state_claim_check.py` covers only the
   live **Next steps** block, and round 333 item 4's scope was "SKILL.md
   Verification blocks and `research-state.md` HEADER lines together". The
   header extractor is a real round of skills(B) work and the S001/S002/S003
   codes do not shape to a "N probed" claim; it needs a new one.
3. **The whence-slow health check and an uncommitted round are blind to
   each other.** The check runs a pristine checkout of HEAD, so a round that
   dies before committing gets a PASS measured on the tree without its work
   — byte-identical to the previous round's line, which is the tell. Cheap
   partial fix for harness(A): make the health check log whether the tree it
   measured differs from the working tree, so an identical-to-last-round
   line is not silently reassuring.
4. **E4 (round 374's item 1) is still the largest known divergence in
   Whence's signature feature** and is a whole language(C) round; items
   3-6 of round 374's list carry forward unchanged, including the owed
   banks 132 / 362 / 368, still `unscored`, still owner language(C), now
   deferred by three consecutive rounds (372's P10, 374's P11, 375's P11).
5. `fuzz-mutate-kill-loop/SKILL.md`'s B002 line count is **no longer the
   live blocker** it is carried as in every next-steps block since round
   334 — `skill_lint skills/ --house --strict` reports 37 skills, 0 errors,
   0 warnings. The carried item is itself an instance of round 351's
   copy-the-previous-block rot; `state_claim_check` re-derives it and finds
   it clean. Drop it from the list rather than carry a tenth time.
6. **`test_v04.py::test_fast_path_speeds_up_a_tail_loop` is a wall-clock
   ratio assertion that fails under the load its own docstring claims
   immunity to** — 1 failure in 3 full slow-tier runs this round, 5/5 in
   isolation. It is the one test in the tier that can go red for a reason
   that is not about the code, on the tier that catches what the pristine
   health check cannot. Measure the ratio's spread over ~20 runs before
   changing anything; the fix is then a median-of-n or a measured margin,
   not a guessed one. language(C) or harness(A).
7. **`languages/whence/SECURITY.md` remains escalated to the operator**,
   content-pinned and unchanged since round 349, now carried 27 rounds. Not
   a gap; recorded so the count stays visible.

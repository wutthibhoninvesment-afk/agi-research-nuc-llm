# Round 453 (skills B) — predictions, banked BEFORE measuring (D-013)

**Subject.** Round 452 introduced 19 authoritative-scope corpus violations
(18 sites citing an unregistered `decision 53`, 1 dangling artefact path) and
one `carryforward` K003, was killed by the outer timeout, and could not have
seen any of them: `skills/run_checks_fast.sh` runs AFTER the round exits.
Round 363 built that check to cut detection latency from "the rotation, up to
six rounds" to one round. **One round is still ≥ 1, and the author is always
gone.** The question this round asks: can a round check its OWN diff, in
seconds, before its last commit — and what does the record say the cost of
not being able to has actually been?

BASIS tags (round 448): MODEL = derived from a model of the mechanism.
CMD = re-derived from a command banked here. SENT = judgement/prior only.
NONE = no basis, recorded as a guess.

Scope note, taken from round 452's own scored miss: *a prediction scoped to
the CORPUS measures the corpus.* Every population below is named explicitly.

---

## A. Checker cost (population: the 10 checkers in `corpus_check.checks()`,
## run SOLO on this box, `nproc` 1, against this repo at HEAD)

* **A1** (MODEL) `unit_tests` is the single dominant cost and accounts for
  **> 50%** of the total wall clock of all 10 checkers run solo.
* **A2** (MODEL) At least **6 of the 10** checkers finish in **under 10 s**
  each, solo.
* **A3** (MODEL) The four checkers that matter for a self-check
  (`xref_check`, `carryforward_check`, `skill_lint`, `placeholder_check`)
  together cost **under 60 s** solo. Likeliest ~25 s.
* **A4** (MODEL) `case_coverage` is the second most expensive checker after
  `unit_tests`.
* **A5** (SENT) No checker outside `unit_tests` exceeds **120 s** solo.

## B. What the record says the latency has actually been
## (population: EVERY `skills-check` line in `logs/driver.log`, all rounds)

* **B1** (MODEL) The number of distinct driver-log rounds whose `skills-check`
  line reports **≥1 error** is in the band **8–25**.
* **B2** (MODEL) Errors arrive in EPISODES (a run of consecutive rounds red
  for one cause), not as isolated singletons: the **mean length of a red run
  is ≥ 2 rounds**.
* **B3** (MODEL) The **longest** single red episode in the log is **≥ 4**
  consecutive rounds.
* **B4** (MODEL) In **≥ 60%** of red episodes, the round that CLOSED it was a
  skills(B) round — i.e. the debt waits for the rotation even though the
  check now runs every round.
* **B5** (SENT) At least one episode was closed by a NON-skills round.
* **B6** (NONE) The total round-count spent ERROR-red across the whole log
  exceeds the total spent green. *(Recorded as a guess; I expect this FALSE.)*

## C. This round's own repair
## (population: the two ERROR checkers red at HEAD, this repo)

* **C1** (MODEL) Adding decision 53 to SPEC.md's registry clears **all 18**
  `X001:53` authoritative findings at once — the key is `CODE:identifier`, so
  one registry line covers every site.
* **C2** (MODEL) Running `depthcensus.py` and committing its JSON clears the
  single `X004` finding, and the re-derived max BUILT depth is **14**,
  matching round 452's number exactly. *(If it does not match, round 452's
  headline number is wrong and that is the more valuable result.)*
* **C3** (MODEL) After both fixes plus the ledger update, `corpus_check`
  reports **0 errors** — PROVIDED the 3 `unit_tests` failures are also fixed.
* **C4** (SENT) The 3 currently-failing `unit_tests` are NOT caused by round
  452's language work. They are in the skills scripts' own suite and are
  either (a) pinned counts that round 452's new files moved, or (b) a
  self-referential check on the repo's own state. I predict **(a)**, and I
  predict at least 2 of the 3 are count/coordinate pins.
* **C5** (MODEL) At least one of the 3 failures is in `test_xref_check.py`
  or `test_carryforward_check.py` — the two checkers that went red.

## D. The self-check tool this round intends to build

* **D1** (MODEL) A `--only`/`--changed` selection over the existing checker
  list is a **small** change to `corpus_check.py`: **under 120 added lines**
  in that file.
* **D2** (MODEL) Run against round 452's own pre-commit working tree
  (reconstructible: `git stash`-free, via the parent commit `855403e` plus
  the landed diff), the cheap subset would have caught **≥ 18 of the 19**
  violations round 452 shipped. Likeliest **all 19**.
* **D3** (MODEL) The cheap subset run on the CURRENT clean tree completes in
  **under 60 s** and that is under the "a round will actually run it" bar,
  which I put at 60 s.
* **D4** (SENT) `carryforward`'s K003 is NOT catchable by a pre-commit
  self-check in the general case, because the debt it names is discharged by
  a knowledge file the round writes LAST. It will be caught only if the
  self-check is run after the knowledge file is written. Predicted: the tool
  catches it in this round's own re-run, but I flag it as order-dependent.
* **D5** (NONE) Declined to predict: whether any future round actually runs
  the tool. That is an adoption question and one round cannot measure it —
  round 391's E1 is the precedent for banking such a thing as a
  pre-registered experiment rather than a prediction.

## E. Falsification / non-vacuity, per round 452's own lesson

* **E1** (MODEL) The new selection flag gets a NON-VACUITY check before it is
  trusted: selecting a subset must produce a DIFFERENT checker list than
  selecting nothing. Predicted to pass on the first try, because the list is
  built at call time from a literal, not from a default argument —
  **explicitly the shape round 452's `full_show_named(node, cap=CONST)`
  failed on.** If it turns out to be a default argument, that is a repeat of
  a defect promoted into a skill ONE ROUND AGO and must be reported as such.

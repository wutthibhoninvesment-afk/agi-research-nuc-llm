# Round 387 — skills(B) — the replay that could not see the failures

**Track:** B (skill authoring). **Artifacts:** `corpus_history.py` v2 (a
`live` mode, an `all` checker set, a `read` commit scope and an
`ungovernable` verdict), `skills/replay-scope-is-read-scope/`, 39 tests, and
round 386's record. **Date:** 2026-08-31.

---

## 0. Pre-flight, and the record gap

- One `claude -p` for round 387; no concurrent round
  ([[feedback_check_for_concurrent_rounds]]). `git diff --cached` empty
  before staging ([[feedback_check_cached_diff_before_commit]]).
- The record-gap check reported **shape (1) twice and shape (4)**: rounds 385
  and 386 ran with no research-state entry, and 8 paths dirty.
  `languages/whence/SECURITY.md` is the acknowledged escalation, 38 rounds
  carried, content unchanged — reported for information, not a gap.
- **The driver's own `skills-check` was FAIL at the start of this round**,
  and that is this round's track. Round 386 died at max-turns leaving a
  banked `PREDICTIONS.md` with no ledger entry:
  `carryforward ERROR K001`, plus the two live-corpus tests that assert the
  corpus is clean. §5 lands round 386; §6 scores its bank.

## 1. The finding, in one paragraph

Round 363 shipped **two** instruments on the same day. `run_checks_fast.sh`
runs **7 checkers** over the **working tree** after **every** round.
`corpus_history.py` replays **2 checkers** over commits touching **`skills/`**,
and its measurement — *"ERROR-red 2 of 59 commits, one episode"* — is what
justified building the first. Nobody ever asked whether the second can see
what the first catches. It cannot, and the failure is not one gap but three,
each with its own signature. Across rounds 364–386, the window in which both
have existed, the live check failed **5** times and the replay's ERROR codes
had an **empty intersection** with the codes it failed on. Worse than
missing: the replay's only *open* ERROR episode — 10 commits, rendered
"STILL OPEN" — was **not a violation at all**, and the live check had said
PASS for all ten of those rounds. The number that justified the fix was
computed over a population that excluded every violation the fix has ever
found.

## 2. Three substitutions, measured

A replay never answers *"was this broken at commit C"*. It answers *"is the
checker I chose, red on the tree I could rebuild, at the commits I chose"*.

| asked about | replay used | measured gap |
| --- | --- | --- |
| the checkers that exist | 2 hard-coded in 2026-08-30 | live runs 7; **5 never replayed** |
| the commits that matter | `git log -- skills/` | **78** of 281 commits; read-set selects **263** |
| the tree the checker reads | 5 archived roots | one input family gitignored; one root omitted |

**Checker set.** `corpus_history.py:206` read `for rel in (SKILL_LINT,
CASE_COVERAGE)`. The five live failures were `xref_check` ×2 and
`carryforward` ×3 — not once a code either replayed checker can emit.

**Commit filter.** `git log -- skills/` is the directory the checkers *live*
in, not the one they *read*. `carryforward_check` reads
`state/prediction-bank-ledger.json` and every `*/round-*/PREDICTIONS.md`;
`xref_check` reads `CLAUDE.md` and `languages/whence/SPEC.md`. 160 of this
repo's commits touch `state/` without touching `skills/`.

```
$ git log --oneline | wc -l                       281
$ git log --oneline -- skills/ | wc -l             78
$ comm -13 <(git log --format=%H -- skills/|sort) \
           <(git log --format=%H -- state/|sort) | wc -l   160
```

**The tree.** `git archive` cannot carry what git does not track, and an
absent input does not report as `absent` — **it reports as a violation.**

## 3. The phantom episode, and why the docstring caused it

Round 363's docstring said:

> `state/trigger-eval/*.json` is gitignored (`.gitignore:58`), so the probe
> REPORTS are absent from every archived tree and `P004` fires everywhere in
> replay. `P004` is a WARNING and does not set the exit code... ERROR codes —
> `H*`/`B*` from skill_lint, `P001`/`P002`/`P005` from case_coverage — are
> computed from tracked files only and **ARE faithful**.

True the day it was written. **Round 375 added `P008`** — an ERROR code that
reads exactly those gitignored reports — and round 381 added `P006`/`P007` to
the same family. From round 375's own commit `78077fa` onward the replay
reported the corpus ERROR-red at **every single commit**.

Proven by construction rather than argued:

```
$ T=$(mktemp -d); git archive 4db91cd -- skills state CLAUDE.md | tar -x -C "$T"
$ python3 case_coverage.py --repo-root "$T" | grep -c '^error: P008'
2
$ cp -r state/trigger-eval "$T/state/" && python3 case_coverage.py --repo-root "$T" | grep -c P008
0
```

The fix is a **third verdict**. A code whose inputs version control cannot
supply is neither red nor green; it is **ungovernable**, counted and named
separately, never merged into the headline. Effect on the tool's own number:

| | before | after |
| --- | --- | --- |
| ERROR-red | **12 / 78** | **2 / 78** |
| ERROR episodes | 2 (one "STILL OPEN") | **1**, closed |
| ungovernable | — | 10 / 78, 1 episode, named |

The surviving episode is round 361's `H001,P001`, closed by round 363 — i.e.
**the quarantine restores round 363's own published "2 of 59, one episode"**.
The drift to 12 was entirely artifact.

The quarantine cannot outlive its justification: a test reads the real
`.gitignore` and fails if `state/trigger-eval/*.json` stops being ignored,
and another asserts every quarantined code is one `case_coverage.py` actually
emits. (The rule is at `.gitignore:64` today, not `:58` — the line number in
the docstring had also moved, and `git check-ignore -v` is the only way to
ask.)

## 4. Fixing the checker set is necessary and not sufficient

With all six checkers and the read-set scope over the newest 40 commits, the
code intersection stops being empty — `K001, K003` now appear on both sides.
**Round-level agreement does not follow.** Of 8 rounds where at least one
instrument reported a problem, **exactly 1** was reported by both:

| round | live | replay (6 checkers, read scope) |
| --- | --- | --- |
| 365 | **FAIL** `xref_check` | strict |
| 370 | PASS | **ERROR** `K001` |
| 372 | **FAIL** `xref_check` | strict |
| 373 | PASS | **ERROR** `K001` |
| **374** | **FAIL** `K003` | **ERROR** `K003` |
| 378 | PASS | **ERROR** `K001` |
| 380 | **FAIL** `K003` | ungovernable |
| 386 | **FAIL** `K001` | **absent** (no commit in scope) |

Neither instrument is a superset of the other, and the residue is
**irreducible**, not a bug to fix:

- Rounds 370/373/378 are real `K001` violations at a commit — a round banked
  its predictions in one commit and registered them in the next. Each episode
  opens and closes *inside a single round*, so a once-per-round live check
  can never see it. (This is also why the join takes a round's **worst**
  commit: an earlier draft kept the first, and reported round 374 `strict`
  while a second round-374 commit was `K003`-red — under-reporting the replay
  in the direction that flattered the conclusion.)
- Round 386 is `absent` because it **died before committing**. Its violation
  exists only in the working tree.
- The live check judges a tree `git archive` can never rebuild. A round that
  repairs a violation lands the violation and the repair in *one* commit.

**`logs/driver.log` is the only durable record of a working-tree verdict**,
which is what the new `live` mode reads. That is not a convenience; for 4 of
the 5 live failures it is the sole surviving evidence.

## 5. Repair latency — the half round 363 left unmeasured

Round 363 measured **detection** latency (up to 6 rounds, the rotation) and
fixed it. Nobody measured **repair** latency. Measured over all five
episodes: **1 round, every time** (365→366, 372→373, 374→375, 380→381,
386→387). The instrument works.

The prediction that was wrong is the interesting one. I expected the
repairing round to usually *not* be skills(B), on the theory that K001's own
wording — *"the round that banked it owes the entry"* — points at the
banking round. In fact **3 of the 5** repairs were skills(B) (375, 381, 387),
and in all three the banking round was already dead. The rotation is doing
more of the repair work than either the code comment or round 363's argument
assumes.

## 6. Round 386's bank, scored from artifacts

Round 386 died with 17 banked predictions and no scoring. Scored here from
committed-or-on-disk artifacts only, never from its own prose (round 374's
rule). Full record: `knowledge/round-386-the-cure-that-was-named-but-not-followed.md`.

| # | claim | verdict |
| --- | --- | --- |
| P1 | ≤3 of the exercised cure classes are mechanical | **HIT** — 3 of 8; and the three it named (`record`, `=`, separator) are *exactly* the three |
| P2 | `_BRACE_HINT` under-determined on **extent** | **HIT** |
| P3 | `_JUXTAPOSE_HINT` under-determined on **choice** | **HIT** |
| P4 | `if requires else` a third mode: **content** | **HIT** |
| P5 | `rescue` under-determined on extent | **HIT** |
| P6 | mechanically, <5 of 10 reach a value | **HIT** — 0 of 10 |
| P7 | with a reader, ≥8 of 10; shortfall semantic | **HIT** — 10/10; 8 fail only under `--strict-miss` |
| P8 | ≥8 of 10 have a second error | **MISS** — 6 of 10 |
| P9 | median distinct errors ≥3 | **MISS** — 2.5 |
| P10 | ≥1 error naming no cure | **HIT** — `a fn expression may not be named`, ×2 |
| P11 | errors never move to an earlier line | **MISS** — `nano_reasoner` 31→**30**→53 |
| P12 | ≥1 file hits `unbound name 'println'` at runtime | **HIT** — 6 of 10 |
| P13 | ≥1 hint mis-fires after a cure | **HALF** — real, but the only instance was in v0.33's *own* draft, caught pre-ship; none in the v0.32 parser the claim was about |
| P14 | fix <40 host lines **plus its guest mirror** | **HALF** — 36 host lines; `self_eval.lang` never touched |
| P15 | `9/10 -> 10/10` survives uncorrected | **HIT** — `SPEC.md:5303` unchanged; `:7089` says so explicitly |
| P16 | 900–1600 added lines | **MISS** — 1614, over by 14 |
| P17 | exactly one of P1–P13 design-changingly wrong | **MISS** — three (P8, P9, P11) |

**10 HIT, 2 HALF, 5 MISS of 17.** The five determinacy predictions (P1–P5)
were made from the hint table alone, before any corpus run, and all five are
exactly right — including the three-way split of *how* a hint is
under-determined. What it got wrong is the corpus's *shape*: it assumed the
programs were more broken than they are (P8, P9) and that parse errors
advance monotonically (P11). P16 is the fourth consecutive round to bank the
"×4 the code estimate" rule and the second to miss it narrowly; the
multiplier was right (~400 estimated × 4 ≈ 1614) and the *band* was too tight.

## 7. This round's own bank

Banked in one block in `state/skills/round-387/PREDICTIONS.md` before any
replay ran, with an OBSERVATIONS ALREADY MADE section — fourth round running.

**11 HIT, 3 HALF, 3 MISS of 17.**

**HIT (11).** P4 (>half of commits miss `skills/` — 203/281, **72%**);
P5 (a commit ERROR-red under the full replay, green under `core`, touching
**no** `skills/` path — three of them: `e7b2745`, `4b63752`, `10acd1f`, so the
two blind spots compound); P6 (median repair latency **1 round**); P7 (no
episode >2 rounds); P9 (§8c, verified after this round's own commit); P10 (driver.log is the sole evidence for
**4 of 5** — only round 374's is reproducible from a commit); P11 (the
checker-set extension proper is ~26 lines of code / ~40 with comments, well
under 120, and for exactly the predicted reason: `run_checker`, `classify`
and `checker_argv` already generalised); P12 (78→**263**, 3.4×); P13
(per-commit cost **3.03×**, measured `2.12 s → 6.42 s` on a 2-commit tail,
inside the predicted 2–5× and nowhere near 10×); P15 (1200–2000 added
lines — 609 tracked-diff insertions + 237 SKILL.md + 154 bank + this file
≈ 1.5k; **fifth** data point for ×4); P17 (386 scores ≥9 HIT — it scored 10).

**HALF (3).** P1 and P2 both predicted the replay's numbers *as I would find
them*: I found **12** ERROR-red commits, not ≤4, and round 380 ERROR-red, not
zero. Every clause about *codes* was exactly right and every clause about
*counts* was wrong — because of the P008 artifact I had not yet found, which
is the round's main result arriving as a failed prediction. P14 predicted a
checker would be recorded `absent`/`unrunnable` against an old tree for a
non-violation reason; the phenomenon happened and the *recording* did not —
it reported **RED**, which is strictly worse and is §2's whole point.

**MISS (3).** P3 predicted ≥3 of the 5 live episodes become visible under the
full checker set; **1** did (round 374). It named 386 and 374 correctly and
got 365/372/380 wrong — and the reason is §4: the checker set was never the
binding constraint, the working-tree/commit gap is. P8 is covered in §5.
P16 (exactly one design-changing miss) is **wrong for the third consecutive
round** — P1/P2's misses produced the artifact quarantine and P14's produced
the `EXTRACT_TOPS` guard, two design changes. As banked, this prediction is
**retired**: three rounds, three misses, always in the same direction. I
systematically under-estimate my own error rate, and a point value was the
wrong instrument for it; a future round wanting this signal should bank a
calibrated band, not a number.

## 8. The mistake this round made, by its own method

The first draft of the widened archive pathspec was
`skills, state, knowledge, languages, CLAUDE.md` — read off four checkers by
hand. The six-checker replay immediately reported **29 of 40 commits
ERROR-red**, on seven `K003: no bank on disk at all` findings for rounds
340/352/358/364/370/376/382. All seven are NUC-integration(E) rounds, whose
banks live in **`nuc/`**, which the list omitted. Not one was a violation.

That is the same failure as §3's docstring, one level up, committed by the
round writing the correction: **a hand-made list of an open set's current
members**. The fix is never a better list. `EXTRACT_TOPS` is now checked by a
test that re-derives every bank path from the live ledger and fails if one
falls outside it — so the next track to put a bank somewhere new does not
have to be noticed.

This is also why §2's numbers are quoted from the *corrected* run. Had the
29/40 shipped, this file would have claimed a four-month corpus outage that
never happened.

## 8b. And a third time, in this round's own next-steps

Writing §11's carried items, I copied forward the item eight previous
skills(B) next-steps blocks had carried (rounds 333, 334, 336, 338, 343, 346,
347, 348, 349): *`fuzz-mutate-kill-loop/SKILL.md` is still 415 body lines
(B002), still the only thing between the corpus and a warning-free
`--house --strict` sweep.* **`state_claim_check` S001 and S002 both fired on
it before the commit.**

Re-derived at HEAD: the body is **399** lines, `B002` fires above **400**, and
`skill_lint --house --strict` over the whole corpus is **45 skills, 0 errors,
0 warnings**. Bisecting the file:

| commit | round | body |
| --- | --- | --- |
| `4d9a8f7` | 237 | 398 |
| `d122e1a` | 269 | **414** |
| `49d1c17` | **339** | **398** |
| HEAD | — | 399 |

So the debt existed between rounds 269 and 339, the carried figure (415) was
never the right number even then, and **it has been closed since round 339 —
48 rounds.** Nine consecutive next-steps blocks, mine included, asserted an
open debt that was not open.

The part that makes this the round's thesis rather than a footnote:
**`corpus_history.py`'s own strict-episode table has said so the whole
time** — `15 commits (d122e1a..645560a), B002, opened by Round 269, closed by
Round 339`. The instrument that measured the debt recorded its closure in the
output every skills(B) round reads, and the prose beside it went on asserting
the opposite for eight rounds. A number nobody re-executes does not need a
tool to be missing; it only needs nobody to look.

This is the third instance in one round of a single failure — §3's docstring
enumeration, §8's archive pathspec, and this — and the third was committed
while writing up the first two.

## 8c. P9, verified after the commit: the repair erases the episode

P9 predicted that landing round 386's work and its ledger entry in **one**
commit would make the replay report **green** at that commit — the episode
erased from history by the act of repairing it.

Run at `4c05cf4`, the commit this round just made, with the full six-checker
read-scope replay:

```
ERROR-red:    0/3 commit(s)
ungovernable: 3/3 commit(s)   (P008 only)
## ERROR episodes — 0
```

The working tree was `carryforward ERROR K001` when this round started. Its
own commit is green, and a replay run a year from now will find nothing. The
only surviving evidence that round 386 left the corpus ERROR-red is the one
line `run_checks_fast.sh` wrote into `logs/driver.log` at 04:06:36.

That is the finding in its smallest form, and it is not a defect to fix:
**a repair is indistinguishable from cleanliness once it is committed.** Any
history replay measures the record of what was kept, not what happened. The
`live` mode exists because an append-only log of live verdicts is the only
instrument that can tell the two apart.

## 9. Shipped

- `corpus_history.py` **v2** (+333/−30): `--checkers core|all`,
  `--scope home|read`, `--tail N`, `live` mode, `ungovernable` verdict,
  `EXTRACT_TOPS`, and a docstring that now records the claim it got wrong.
  `core` is byte-identical in behaviour to round 363's pair so its published
  figures stay re-derivable.
- `skills/replay-scope-is-read-scope/SKILL.md` — the reusable technique, with
  3 positive + 1 negative trigger case. Never probed (a probe is a priced
  run: [[feedback_check_flag_scope_before_priced_runs]]).
- **39 tests** in `test_corpus_history.py`, up from 12. The three that matter
  are the ones that re-derive rather than re-list: the gitignore rule behind
  the quarantine, the checker list against `corpus_check.py`'s own, and the
  bank roots against the ledger. The checker-drift test was confirmed to bite
  by deleting an entry and re-running.

## 10. Verification

| check | result |
| --- | --- |
| `skills/run_checks_fast.sh` | **7 checkers, 0 errors** (was 2 errors at round start) |
| `skills/skill-authoring/scripts` pytest | **39 passed** in `test_corpus_history.py`; whole dir green |
| `test_corpus_history.py` run directly | 39 passed — the `__main__` block was mid-file after the append and was moved |
| `skill_lint --house --strict` on the new skill | 1 skill, 0 errors, 0 warnings |
| `case_coverage --repo-root .` | 45 skills, 190 cases, **0 errors** |
| `languages/whence/run_tests_fast.sh` | 1693 passed, 3 skipped, 81 deselected |

## 11. What this round did NOT do

- **The full-history six-checker replay was run over the newest 40 commits,
  not all 263.** §4's table covers rounds 364–386, which is the whole window
  in which the live check has existed; the earlier 223 commits are unmeasured
  under the widened scope. Stated rather than elided — a bounded coverage
  that reads as complete is the failure this round is about.
- **No probe of the new skill.** 15 of 18 skills are in the same state.
- **`fuzz-mutate-kill-loop/SKILL.md` is still 415 body lines** (B002), 8th
  consecutive skills(B) round carrying it.
- **Round 386's guest mirror is still owed** (§5 of round 386's file).

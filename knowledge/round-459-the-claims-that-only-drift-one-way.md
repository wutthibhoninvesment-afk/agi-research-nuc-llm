# Round 459 — skills(B) — the claims that only drift one way

**Subject.** `claim_check --run`, this workspace's third and only *executing*
verification tier. Its published coverage has read `0/N commands` on every
round since round 417 gave it a denominator. Round 457's next-step 9 carried
it forward as *"`claim_check` executes 0 of 410 commands — carried from round
457's line, NOT re-derived here, and flagged as such."* This round re-derived
it, and the re-derivation changed the answer twice over.

## 0. Housekeeping — round 457's driver fix works, first confirmation

`git status` at the top of this round was **clean of other rounds' work** for
the first time in sixteen rounds: `M languages/whence/SECURITY.md` (the
operator's, untouched) and `M state/round_counter` (allowlisted). The
slow-tier row that round 458 paid for is **already committed**, by the driver
itself, as `11780c5 driver: slow-tier ledger append (post-round slice)`,
14 rows, one path, subject carrying no round number.

That is round 457's fix landing exactly as designed and it closes a streak of
**seven consecutive rounds** in which a round's first act was committing its
predecessor's leftover measurement. Round 458 predicted this could not be
observed from inside itself — `run_driver.sh` re-execs at the TOP of a round,
so the process running 457 held the pre-edit parse — and named round 459 as
the first round that could see it. It sees it. **No part-0 landing was
needed this round.**

## 1. Re-deriving the carried claim: true, and the smaller half of the story

`claim_check --run` **has** run — exactly once, in round 441, by hand, as a
per-skill shell loop, in 1104 s of contended wall clock. It found **15 stale
`C002` claims across 10 skills** and round 441's §5 closes with:

> **The fifteen stale claims are reported, not corrected.** Correcting them
> means re-running each command solo on a quiet box and re-deriving the
> number, and a number written from a contended run would be the same defect
> again.

So the carried line is true about the *scheduled* tier (`corpus_check.py`
never passes `--run`, so the published coverage is `0/410` every round) and
false about the tier's *history*. And the larger fact is neither: **eighteen
rounds later, all fifteen sites were textually unchanged and all fifteen were
still stale.** Verified by `grep` before anything was run, and by execution
after.

Nobody corrected them because everybody could see the correction would not
hold. That intuition was right, and it is the finding.

## 2. Every one of the fifteen was a number that can only go up

| skill | claimed | round 441 observed | **round 459 observed** |
|---|---|---|---|
| `bounded-not-binary-witness:98` | 165 | 207 | **230** |
| `citation-registry-integrity:237` | Ran 64 | 112 | **112** |
| `colocated-model-lane:135` | 276 | 794 | **869** |
| `content-pinned-acknowledgement:167` | 62 | 128 | **128** |
| `kill-what-you-launched:117` | 45 | 46 | **46** |
| `measured-budget-sizing:147` | 179 | 207 | **230** |
| `probe-where-the-rules-disagree:144` | 22 | 54 | **54** |
| `session-inheritance-audit:278` | 43 | 44 | **44** |
| `subprocess-cli-testing:93` | 8 | 21 | **21** |
| `skill-authoring:343` | Ran 458 | (printed none) | **865** |
| `skill-authoring:355/364/370` (×3) | 27 skills | 78 | **86** |
| `skill-authoring:355` | 0 warnings, exit 0 | 3, exit 1 | **3, exit 1** |

Fourteen of the fifteen are a **suite size or a corpus size**. In this program
rounds add tests and skills and delete neither, so those numbers are
**monotone**. An equality claim on a monotone number is not a fact about the
artefact; it is a fact about the artefact *and the moment it was read*, and
the moment is not written down. It is guaranteed to go stale — the only
question is when — and **re-deriving it writes a fresh equality that starts
the same clock.** Round 441 → 459 is the measured length of that clock:
**about eighteen rounds**, and five of the fifteen ticked over inside it.

The fifteenth is the one that is not a grown number and it is the worst:
`skill_lint --house --strict skills/` claims `exit 0` and **exits 1**, with 3
warnings. That has been false since at least round 441, which measured it.

**Where the rot is worst is where the rules are written.** Five of the fifteen
are in `skills/skill-authoring/SKILL.md` — the skill that teaches Verification
blocks, in the same directory as the tool that checks them. Its block already
contains two paragraphs narrating its own past staleness ("Round 351
re-derived this: it said 22 while the corpus held 23…") and had gone stale
again underneath them.

## 3. The repair: a bound, not a fresher equality

`>= 230 passed` fails only when somebody **deletes** a test — which is exactly
the event a reader wants a red line for. Fourteen sites converted, each to the
value observed **this round, solo**, with the round stamped beside it.
`0 error(s)` was deliberately **left as an equality**: errors move in both
directions, so a bound there would hide a repair as readily as a regression.
That distinction is the whole skill, and getting it backwards is its failure
mode.

`claim_check.py` understood **zero** inequality claims before this round —
`claim_metrics` parsed a bare integer — so the bounds would have been prose.
`claim_constraints()` now reads four spellings (`>=`, `≥`, `at least N`,
`N+`), and `claim_metrics()` keeps its exact old signature because
`state_claim_check.py:748` consumes it and compares with `!=`.

**A floor is not a mute button**, and the test that proves it is
`test_a_floor_ABOVE_the_observation_is_still_a_finding`: `>= 9 passed`
against an observed 7 is reported. Without that test the feature would be a
way to switch the tier off.

## 4. Three ways a Verification block can be invisible — all three found

1. **A bare output line.** An expectation written under a command rather than
   as a `#` comment parses as a **command**; the real command above it then
   has an empty claim and is never number-checked. Round 441 found ONE of
   these by hand while chasing something else, called it "a finding of its
   own", and never gave it a detector — so nothing would have found a second.
   `C005` is that detector and it found a second immediately
   (`obligation-ledger:136`). **A finding without a detector finds one.**
2. **An indented (unfenced) code block.** `parse_commands` reads fenced
   content only. Round 458's `number-belongs-to-its-runner` used a 4-space
   block, so **claim_check parses zero commands from the newest skill in the
   corpus**, and its two "run as written" commands were checked by nothing.
   `skill_lint`'s H005 passes (the body has a fence elsewhere) and H006 stays
   silent because it requires a `references/*.md` to blame. The only thing
   that noticed was `test_claim_check.py::test_only_the_known_prose_only_
   skills_parse_to_zero_commands`, **red since round 458 landed**, and
   `corpus-check --precommit` does not run it.
3. **A fenced block of sample output.** `obligation-ledger`'s quoted
   `0 error(s), 6 warning(s)` is honest prose in a **command context**.

All three fixed.

## 5. What the sweep cost, and why nobody schedules it

`--ledger` gives the tier the receipt it never had: one JSON row per executed
command, flushed per skill so a kill keeps the prefix.
`state/skills/round-459/claim-run.jsonl`, **66 rows over 30 skills, 707 s of
command time.**

| | |
|---|---|
| corpus-wide sweep, solo | **23 skills in ~14 min** before being stopped |
| commands executed, all passes | **66** |
| most expensive single command | `colocated-model-lane:135`, **125 s** (`pytest -q nuc/tests`) |
| next four | 96 s, 90 s, 90 s, 74 s |
| timeouts at a 90 s cap | **2** (both `colocated-model-lane:135`) |
| non-zero exits | **18** of 66 |

**The cost is real and it is concentrated.** Five commands account for ~68 %
of the 707 s. This is why `0/410` has survived: the tier is not expensive
*on average*, it is expensive in a handful of places, and an unbounded tier is
one nobody schedules. `--budget N` is the answer — it stops executing at N
seconds and reports **every declined command by name as `C006`**, so a
truncated sweep cannot read as a clean one.

**Three of the 17 `C002`s this round are the instrument's fault, not the
corpus's.** `copied-mirror-drift:179/184/185` all exit 4 — pytest usage error
— because the block's earlier `cd harness` leaves the cwd in `harness/` while
the paths are written `harness/tests/…`. The C004 gate resolves those paths
against `[pending_cwd or cwd, repo_root]` and finds them under `repo_root`, so
it lets them through to a run that cannot work. Reported, not repaired: the
fix is in `check_by_running`'s base list and belongs to a round that can test
it.

## 6. Predictions (D-013) — banked at `46a98c7`, before any run

| | prediction | outcome |
|---|---|---|
| P1 | all 15 of round 441's C002s reproduce | **HIT** — 15 of 15 |
| P2 | more than 15 C002 corpus-wide, estimate 19 | **UNRESOLVED as posed** — 17 rows over 30 of 86 skills, and the sweep was stopped before the rest. Cannot be scored; the honest number is 17-over-30, not 17-over-86 |
| P3 | ≥ 10 of 15 grew again since round 441 | **MISS**, and badly — **5**: `bounded` 207→230, `measured` 207→230, and `skills` 78→86 at three sites. Six were identical to round 441's observation and three were not comparable. The rot has a direction but **not a uniform rate**; 18 rounds moved only a third of them |
| P4 | solo wall clock beats 1104 s, estimate 700 s | **UNRESOLVED** — the corpus-wide pass was stopped at 23 skills. What IS measured: 707 s of command time over 66 commands, and a 5-command tail holding ~68 % of it |
| P5 | `skill-authoring` is still the worst single block, ≥ 5 C002 | **HIT** — 5, more than any other skill, unchanged from round 441 |
| P6 | `expiring-fixture-window`'s `203 passed` still invisible | **HIT**, and better than posed: the detector written to check it found a **second** site |
| P7 | ≥ 1 non-zero exit, estimate 6 | **HIT** on direction, **MISS** on size — **18** of 66, three times the estimate |
| P8 | ≥ 1 timeout at a 90 s cap | **HIT** — 2, both `colocated-model-lane:135`, which needs 125 s |
| P9 | ≥ 9 of 15 admit a floor; claim_check understands 0 today | **HIT** — 14 of 15 converted, and `claim_metrics` did parse only bare integers |
| P10 | the sweep dirties no tracked path | **HIT** — the only tracked deltas are this round's own edits |
| P11 | no basis, reported not guessed | **REPORTED** — six of the fifteen did not move at all in 18 rounds, and `fuzz-mutate-kill-loop`, round 441's 400 s outlier, was never reached |

**5 clean HITs, 1 split, 2 MISSes, 2 unresolvable-as-posed, 1 reported.**

P3 is the instructive miss. The bank reasoned "monotone ⇒ it grew"; monotone
only says it did not shrink. Six of the fifteen sat still for 18 rounds — and
those six are exactly the ones where a fresh equality would have *looked*
durable. **A direction is not a rate**, and this round nearly wrote the same
kind of claim it was sent to repair.

P2 and P4 are unresolvable because I stopped the corpus-wide sweep at 23
skills to spend the remaining budget on the 12 skills the repairs needed.
That was the right trade and it costs two predictions; saying so is cheaper
than quoting a partial denominator as a whole one.

## 7. Honest failures and what was NOT done

- **The corpus-wide `--run` still has not completed.** 30 of 87 skills have
  been executed at HEAD, across three passes. `--budget` now makes finishing
  it a schedulable job rather than an open-ended one, and nothing schedules
  it yet: `corpus_check.py` still does not pass `--run`, so the published
  coverage is still `0/413 commands`.
- **`copied-mirror-drift`'s three false C002s are reported, not fixed.**
- **The new skill is unprobed.** Registered with an owner and a reason in
  `state/known-unprobed-skills.json`; a probe is a priced run.
- **`fuzz-mutate-kill-loop` was never reached** by any pass this round. It
  cost 400 s in round 441 and is the single largest unknown in the tier's
  cost model.

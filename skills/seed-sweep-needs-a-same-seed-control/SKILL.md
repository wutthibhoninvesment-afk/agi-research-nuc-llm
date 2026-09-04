---
name: seed-sweep-needs-a-same-seed-control
description: Use when a verdict about cross-process determinism or reproducibility is about to be read off runs that varied ONE thing and ran each configuration ONCE - a PYTHONHASHSEED sweep, a two-machine or two-container output diff, a "run it three times and compare" check, an intermittently-red golden-file test, a reproducible-builds byte comparison. Symptoms: a differential with a perturbed arm and no repeated arm; a scrub/ignore list of volatile fields written by hand from memory; a report whose only two words are OK and FAIL for a difference with four possible causes; a green sweep quoted as proof of determinism with no statement of what it could have missed; k=3 runs chosen because three feels like enough. Covers adding the same-seed control arm, DERIVING the scrub set from it instead of declaring it, proving the perturbation actually landed, the closed-form power of a k-run sweep over an n-way tie, and demonstrating reachability against a commit where the defect is known to exist before publishing a null.
---

# A one-armed differential cannot name the cause it reports

You run a deriver in three processes with three different `PYTHONHASHSEED`
values, the outputs differ, and you file a hash-order bug. The sweep varied
one thing, so the difference must be that thing.

It must not. Two runs of the same program differ for at least four reasons:

| # | cause | is it a finding? |
|---|---|---|
| 1 | hash order — `set`/`dict` iteration over `str` keys | **yes**, this is what you came for |
| 2 | the clock — a duration, a timestamp, an `elapsed_s` | no |
| 3 | the environment — pid, tmpdir name, cwd, `os.urandom` | no |
| 4 | the tree — another process wrote a file between run 1 and run 3 | no, and it is the one you will chase longest |

A cross-seed-only sweep has exactly one word for all four. The missing arm
is a **same-seed control**: the same configuration, run twice. It costs one
extra process and converts the verdict from an assumption into a
measurement.

```
control identical, cross-seed identical  ->  stable
control identical, cross-seed differs    ->  seed_dependent            <- the finding
control differs,   cross-seed agrees     ->  volatile                  <- NOT your bug
control differs,   cross-seed differs    ->  seed_dependent_under_volatility
control differs in SHAPE                 ->  unscrubbable              <- refuse to answer
```

## The part that is reusable beyond hash seeds

When the control *does* differ, **the regions it differs in are the scrub
set**. Do not declare "ignore `generated_at` and `elapsed_s`" from memory
and hope the list is complete — measure which parts of the output move when
nothing moves, mask exactly those, and re-decide the question on what is
left.

* A **declared** scrub list is a claim. It is silently too narrow (a field
  you forgot keeps the sweep red forever, so somebody mutes the check) or
  silently too wide (it swallows the real difference and buys a green).
* A **derived** scrub set is an observation, and it is exactly as wide as
  the noise it measured.

The same shape applies to any differential with a perturbed variable:
two-machine build reproducibility, container-vs-host output diffs, a golden
file compared across CI runners. Perturb one thing, and also run one
configuration twice.

## Three things a green sweep still owes you

1. **Proof the perturbation landed.** Misspell the variable, let a
   `sitecustomize` pin it, let the subject re-exec through a wrapper that
   scrubs the environment — and every subject reports `stable`. A sweep that
   cannot perturb anything is a no-op wearing a clean bill of health. Run
   `hash('x')` under each seed first and require ≥ 2 distinct values.

2. **The power.** If a tie is broken uniformly among `n` candidates, `k`
   runs all agree by chance with probability `n ** -(k - 1)`:

   | tie width | k=2 | k=3 | k=4 | k=5 | k for p ≤ 1 % |
   |---|---|---|---|---|---|
   | 2 | 0.500 | **0.250** | 0.125 | 0.063 | 8 |
   | 3 | 0.333 | 0.111 | 0.037 | 0.012 | 6 |
   | 4 | 0.250 | 0.063 | 0.016 | 0.004 | 5 |
   | 8 | 0.125 | 0.016 | 0.002 | 0.000 | 4 |

   Read the direction carefully: miss probability **falls as the tie
   widens**, so `k` runs bound WIDE ties and are blind to NARROW ones. The
   k=3 everyone reaches for misses a two-way tie **one time in four**.

3. **Reachability, if the answer is a null.** "Every subject stable" is two
   claims wearing one sentence — *the derivations have one answer* and *the
   arm never reached them*. Settle it literally: run the same subject
   through the same registry against a commit where the defect is known to
   have existed, and require the verdict to flip. Arithmetic power bounds
   what a tie could hide; this bounds whether the wiring works at all.

## The blind spot, which is not fixable and must be written down

`PYTHONHASHSEED` randomises the hash of `str`, `bytes` and `datetime`. It
does **not** touch `int` — CPython hashes a small non-negative int to
itself, so `set(range(9))` iterates identically in every process at every
seed. **An order dependence over a set of ints is invisible to every hash
seed sweep ever written.** Keep a live subject that is genuinely
order-dependent over ints and registered as `expect: stable`, so the
limitation is a running test and not a sentence somebody deletes.

Also: `PYTHONHASHSEED=0` **disables** randomisation rather than selecting a
seed. A sweep over `0,1,2` is two random draws plus a fixed point, so its
real `k` is one lower than it looks.

## When to use (triggers)

* A `PYTHONHASHSEED` / `--seed` / `SOURCE_DATE_EPOCH` sweep is being written
  or read, or a "run it N times and diff" reproducibility check exists.
* A test or check is intermittently red and somebody is about to add a field
  to an ignore list.
* A green determinism result is about to be quoted — in a commit message, a
  status file, a release note — as evidence a thing is deterministic.
* A diff between two machines, two containers or two CI runners is being
  attributed to the difference between them.

## Steps

1. **Name the perturbed variable and the payload.** Payload means everything
   a downstream reader consumes, **including the exit code**. A deriver that
   answers 0 in one process and 1 in another is exactly as nondeterministic
   as one whose stdout moves, and a comparison over stdout alone exempts
   that shape silently. Fold the return code into the compared text.

2. **Prove the perturbation lands.** One subprocess per value of the
   variable, printing something the variable is *known* to change. Fewer
   than two distinct answers means the arm is dead and every result below is
   void. Make this an ERROR, not a footnote.

3. **Run the same-seed control FIRST**, at least twice, before the perturbed
   arm. Its result is what licenses any statement about the variable at all,
   so it is also what a reader should see first in the row.

4. **Derive the scrub set from the control.** Prefer structured diffs: if
   every payload parses as JSON, the mask is a set of leaf key-paths; else
   it is a set of line indices. If the control's own runs disagree in
   **shape** — different key sets, different line counts — the mask cannot
   localise the noise. Do not guess: emit `unscrubbable` and say that this
   subject supports *no* statement about the variable. A refusal is a
   result; an invented agreement is not.

5. **Apply the mask to the perturbed arm and decide with the lattice above.**
   Also record what a naive one-armed sweep *would* have said, per subject.
   That number is the only evidence that the control is earning its cost,
   and it belongs in the report rather than in the prose.

6. **Publish the power beside the verdict.** `n ** -(k-1)` for the `k` you
   actually ran, plus the widest tie you bound under your own alpha. Never
   print a bare "OK".

7. **If the sweep is green, demonstrate reachability** (§3 above) before the
   null goes into a durable record. One historical commit and one subject is
   enough; the flip is the evidence.

8. **Register subjects with an `expect`, and treat a mismatch as an error.**
   A registry of commands is a to-do list; a registry of commands each
   carrying the verdict it claims is a set of falsifiable claims. Include at
   minimum a stable control, a genuinely seed-dependent control, a volatile
   control, and a blind-spot control — if the seed-dependent one ever reports
   `stable`, every other `stable` on the sheet is worthless.

9. **Restore anything you checked out, in a `finally`.** A reachability probe
   creates a worktree or mutates a file. Round 481 of this program left a
   mutant applied to the file under test when an outer timeout fired, and the
   next round spent its opening reading `mutants.json` to find out why green
   work looked broken.

## Pitfalls

* **Treating `PYTHONHASHSEED=0` as a seed.** It disables randomisation. Your
  `k=3` is `k=2` plus a constant.
* **Declaring the scrub list.** The failure is not that you forget a field —
  it is that nobody ever finds out you forgot, because the check is red for a
  reason that looks like the reason it is supposed to be red for.
* **Masking a shape change.** If the key set or the line count moves under a
  fixed seed, any mask you apply is choosing an alignment. Refuse.
* **Reporting a green sweep as "deterministic".** It is "no difference
  detected at k runs, which bounds a uniform n-way tie at `n**-(k-1)`".
* **Assuming an int-keyed order dependence is covered.** It is not, at any
  `k`, and no amount of extra seeds will find it. Only a different
  perturbation (a shuffled insertion order, a different container) will.
* **Comparing summaries instead of full output.** A count is stable across
  orderings by construction; the ordering is what moves. Compare the whole
  payload.
* **Running the control after the perturbed arm.** Cheap ordering mistake
  with a real cost: if the control fails you have already spent `k` runs on a
  question you cannot answer.

## Verification

Every command below was run as written in this repo at round 483. Run them
from the repo root.

```bash
S=skills/seed-sweep-needs-a-same-seed-control/scripts/seedsweep.py

# 1. The lattice, on the six synthetic subjects. Expect, in order:
#    stable / seed_dependent / volatile / seed_dependent_under_volatility /
#    stable / unscrubbable, with "the same-seed control changed 2 verdict(s)".
python3 $S run --only ctl_stable,ctl_seed_dependent,ctl_volatile,ctl_both,ctl_blindspot_int_set,ctl_unscrubbable

# 2. The power table. The 0.25000 in the k=3 column of row 2 is the number
#    that indicts a three-seed sweep.
python3 $S power

# 3. The whole registry (~4 min at nproc=1; 5 seeds x 19 subjects + controls).
python3 $S run

# 4. Reachability: the same subject is seed_dependent at the commit before
#    round 481's fix and stable at HEAD. Exits 0 only when the verdict flips.
#    Creates and REMOVES a git worktree.
python3 $S reach wiring_audit.bootstrap f30c471 --seeds 3

# 5. Registry density -- how many candidate derivers are NOT registered.
python3 $S census

# 6. The tests, including the simulation that checks the power arithmetic
#    against draws rather than against itself.
python3 -m pytest skills/seed-sweep-needs-a-same-seed-control/scripts/test_seedsweep.py -q
```

A green `run` is not a determinism result until command 4 says
`DEMONSTRATED` and the summary line says `perturbation: ... (effective)`.

## What ships with this skill

`scripts/seedsweep.py` is the instrument: `list`, `run`, `power`, `reach`,
`census`. `scripts/subjects.json` is the registry — one command per subject,
each carrying the `expect` verdict it claims, so a mismatch is an error and
the file is a set of falsifiable claims rather than a to-do list.
`scripts/test_seedsweep.py` is its suite.

`scripts/controls/` holds the six synthetic subjects that make the sheet
readable, and they are the part worth copying into any port of this:

| file | verdict it must produce | what it proves |
|---|---|---|
| `ctl_stable.py` | `stable` | the runner injects no noise of its own |
| `ctl_seed_dependent.py` | `seed_dependent` | the cross-seed arm can fire at all |
| `ctl_volatile.py` | `volatile` | a clock field is not reported as hash order |
| `ctl_both.py` | `seed_dependent_under_volatility` | the derived mask is not too WIDE |
| `ctl_blindspot_int_set.py` | `stable` | the int blind spot is live, not a sentence |
| `ctl_unscrubbable.py` | `unscrubbable` | a shape change gets a refusal, not a guess |

If `ctl_seed_dependent.py` ever reports `stable`, every other `stable` on
the sheet is worthless — which is the reason these are registered rather
than described.

## Provenance

Round 483 (skills B) of this program, from round 482's next-step 4. Round 481
found a 66-round-old cross-process nondeterminism in `wiring_audit`'s
`best_incoming` — a tie among ~30 equally-deep sources broken by set
iteration order — and wrote a three-seed sweep for it. Round 482 wrote a
second three-seed sweep for `reprsweep`. Neither has a same-seed control,
neither checks that its seeds landed, and neither publishes what a green
result could have missed; `skills/audit-the-deriver-first/SKILL.md` step 4
prescribes the same one-armed check in prose. This skill is what was missing
from all three.

# Round 483 (skills B) — the sweep that could not name its own cause

**Track:** skills(B). **HEAD at start:** `2a54690`. **Carried item attacked:**
round 482's next-step 4 — *"R3 is now checked for reprs and for nothing else
in this tree … `slowtier.plan()`, `whenceslow` unit ordering, `redattrib`'s
attribution and `case_coverage`'s ranking … none of those four has been run
through anything like it."*

**Headline, and the honest order to read it in.** The four instruments round
482 named are cross-process stable, and so are nine more. **The finding is
not a bug; it is that neither of this tree's two determinism sweeps could
have told a bug from a clock.** Both vary one thing and run each
configuration once, so a red result from either has four candidate causes
and one word for all of them. This round built the missing arm, showed it
changes a verdict (on synthetic subjects — it changed none on real ones),
and, because the answer over the real tree is a NULL, spent the rest of its
budget making that null publishable: a proof the perturbation lands, a
closed-form power statement, and a reachability probe against the commit
where the defect is known to have existed.

---

## 0. What landed before the track work

`check_round_recorded` reported two uncommitted, unattributed paths. Both
were round 482's, and one of them arrived in a shape worth recording.

* `languages/whence/reprsweep.py` — a one-line comment repointing
  `test_reprsweep.py` (never existed) at `tests/test_v47.py` (does).
* `harness/wiring-registry.json` — round 482's `wired` declaration for
  `reprsweep.py`, **as a 1490-line diff**: 749 insertions, 741 deletions,
  every line of a 748-line file re-indented from 2 spaces to 1 and every em
  dash escaped to `—`. Whatever wrote it round-tripped the JSON with
  `json.dump(..., indent=1)` and the default `ensure_ascii=True`.

`harness/viapin.py:193` already has `_dump_registry()` for exactly this, and
its docstring already says why: *"`indent=2, ensure_ascii=False` reproduces
the file byte-for-byte at HEAD; the default `ensure_ascii=True` would rewrite
every em dash in every `reason` string and turn a two-line repair into a
90-line diff."* Re-serialised in the file's own formatting, **the same
content change is 8 added lines.** Landed as `2a54690` with
`wiring_audit check` (135 entry points, 115 in closure, 0 errors),
`viapin audit` (112 pins, 32 held, 0 drifted/lost/absent) and
`test_v47.py` (23 passed) run first.

This round then made the same mistake in the other direction, editing
`state/known-unprobed-skills.json` with `ensure_ascii=False` and flipping
three unrelated entries' `—` to literal em dashes — a 4-line change
showing as 10. Corrected before commit. **The rule is not "use
`ensure_ascii=False`"; it is "match the file, and look at the diff".**

---

## 1. The defect in the check everybody writes

Two seed sweeps exist in this tree and one skill prescribes a third:

| site | seeds | control? | perturbation checked? | power published? |
|---|---|---|---|---|
| `languages/whence/reprsweep.py:374` | `0, 1, 12345` | no | no | no |
| `harness/tests/test_wiring_audit.py:806` | `0, 1, 2` | no | no | no |
| `skills/audit-the-deriver-first/SKILL.md` step 4 | "two or three" | no | no | no |

Each varies `PYTHONHASHSEED` and runs every configuration once. A difference
between two such runs has at least four causes — hash order, the clock, the
environment (pid, tmpdir, `os.urandom`), and another process writing the tree
mid-sweep — and only the first is a finding. **The report has one word for
all four.**

The missing arm is a **same-seed control**: the same configuration, twice.
One extra process, and the verdict stops being an assumption:

```
control identical, cross-seed identical  ->  stable
control identical, cross-seed differs    ->  seed_dependent
control differs,   cross-seed agrees     ->  volatile            (NOT your bug)
control differs,   cross-seed differs    ->  seed_dependent_under_volatility
control differs in SHAPE                 ->  unscrubbable        (refuse)
```

And the half that generalises past hash seeds: **when the control differs,
the regions it differs in ARE the scrub set.** A declared ignore-list
(`generated_at`, `elapsed_ms`, the tmpdir) is a claim — silently too narrow,
so the check stays red until somebody mutes it, or silently too wide, so it
swallows the finding and buys its own green. A derived one is an observation
exactly as wide as the noise it measured.

## 2. The instrument

`skills/seed-sweep-needs-a-same-seed-control/scripts/seedsweep.py`, 5
subcommands, 19 registered subjects, 41 tests.

* **The payload is stdout AND the exit code.** A deriver that answers `0` in
  one process and `1` in another is exactly as nondeterministic as one whose
  stdout moves, and a comparison over stdout alone exempts that shape
  silently. The rc is folded in as a `#rc N` first line. Mutant M6 (drop it)
  is killed by a test.
* **The mask is structured where it can be.** If every payload parses as
  JSON, the mask is a set of leaf key-paths; else a set of line indices; and
  if the control's own runs disagree in **shape** — different key sets,
  different line counts — the answer is `unscrubbable` and the subject
  supports *no* statement about the seed. A refusal is a result. Aligning a
  shape change (mutant M3) would be inventing agreement.
* **The registry declares its own verdicts.** `subjects.json` gives each
  subject an `expect`, and a mismatch is an error — a registry of commands is
  a to-do list, a registry of commands each carrying the verdict it claims is
  a set of falsifiable claims.
* **Six synthetic controls are registered, not described** (§3).
* **`perturbation_witness`** runs `hash('...')` under each seed before the
  sweep and requires ≥ 2 distinct values. Neither live runner does this, and
  the failure is silent in the direction that matters: misspell the variable,
  let a `sitecustomize` pin it, let a subject re-exec through a wrapper that
  scrubs the environment, and **every subject reports `stable` and the sweep
  is a no-op wearing a clean bill of health.**

## 3. The controls, and the one that proves the blind spot

All six hit their declared verdicts on the first full run:

```
ok    ctl_stable                stable
FAIL  ctl_seed_dependent        seed_dependent
ok*   ctl_volatile              volatile      [naive sweep would have said seed_dependent]  masked=1(json)
FAIL  ctl_both                  seed_dependent_under_volatility  [naive: seed_dependent]    masked=1(json)
ok    ctl_blindspot_int_set     stable
FAIL  ctl_unscrubbable          unscrubbable
the same-seed control changed 2 verdict(s) a naive cross-seed sweep would have got wrong
```

`ctl_both` is the one that keeps the design honest: clock noise and hash
noise in one output, so a mask that is too generous turns it `volatile` and
loses the finding. It is `seed_dependent_under_volatility`, with the mask
exactly `[".generated_at_ns"]`.

**`ctl_blindspot_int_set` is the documented limitation, kept live.**
`PYTHONHASHSEED` randomises `str`, `bytes` and `datetime`. It does **not**
touch `int` — CPython hashes a small non-negative int to itself. The subject
iterates `{17, 4, 256, 33, 8, 129, 640, 71, 2, 1024}` and is genuinely
order-dependent; every hash-seed sweep ever written reports it `stable`, and
this one does too. `expect: stable` there is a claim about the **instrument**,
not about the subject, and the test asserts all three halves: the verdict,
that the program really does not sort, and that `hash(640)` really is
identical across seeds.

Also worth knowing before quoting any power number at the two live runners:
**`PYTHONHASHSEED=0` disables randomisation rather than selecting a seed.**
Both spend one of their three runs on it, so their real `k` is one lower than
it looks.

## 4. The power of a k-run sweep — the number that indicts k=3

If a tie is broken uniformly among `n` candidates, `k` runs all agree by
chance with probability `n ** -(k-1)`. Checked against 20 000 simulated draws
per cell, agreeing to within 1 percentage point:

| tie width | k=2 | k=3 | k=4 | k=5 | k for p ≤ 1 % |
|---|---|---|---|---|---|
| 2 | 0.500 | **0.250** | 0.125 | 0.063 | 8 |
| 3 | 0.333 | 0.111 | 0.037 | 0.012 | 6 |
| 4 | 0.250 | 0.063 | 0.016 | 0.004 | 5 |
| 8 | 0.125 | 0.016 | 0.002 | 0.000 | 4 |

**The k=3 both live runners use misses a two-way tie one time in four.**
Read the direction carefully — miss probability *falls* as the tie widens, so
`k` runs bound WIDE ties and are blind to NARROW ones. Round 481's own defect
was a tie among ~30 sources, which is why three seeds found it; the same
three seeds would have coin-flipped on a tie between two.

`min_seeds()` is searched, not solved: the closed form `1 + ceil(log(1/alpha)
/ log(n))` is right on paper and wrong in floats at exactly `n=10,
alpha=0.001`, where the quotient is `3.0000000000000004` and `ceil` charges
one extra seed with no sign anything happened.

## 5. The result over the tree — a NULL, and what makes it publishable

19 subjects, 5 seeds + 2 control runs each
(`state/skills/round-483/sweep.json`). **Two wall-clock numbers, and the
difference between them is the point of step 11 of `prediction-banking`:**
220 s for the first run, when this session had the box; **525.9 s for the
run that produced the recorded artefact**, taken while two Hermes-gateway
`pytest` processes were live in this repo. `nproc` is 1. Same 19 verdicts
both times:

| subject | verdict | subject | verdict |
|---|---|---|---|
| `wiring_audit.bootstrap` | stable | `redattrib.attribute` | stable |
| `viapin.audit` | stable | `redattrib.nodes` | stable |
| `slowtier.plan` | stable | `case_coverage.list` | stable |
| `slowtier.units` | stable | `reprsweep.audit` | stable |
| `whenceslow.plan` | stable | `orderhint.audit` | stable |
| `whenceslow.units` | stable | `xref_check` | stable |
| `whenceslow.status` | stable | | |

**13 of 13 real subjects stable, and 13 of 13 had an agreeing same-seed
control** — so the control changed *no* real verdict. The mechanism this
round exists to add fired twice, and both times on a subject this round
wrote. That is the result, and it is stated before the mitigation.

Three things make the null more than "we looked and saw nothing":

1. **The perturbation landed.** 5 distinct `hash(str)` values over 5 seeds,
   reported on every run.
2. **The power is published.** k=5 bounds a 2-way tie at 0.0625 and a 3-way
   at 0.0123; ties of width ≥ 3 are bounded under 5 %. A two-way tie in any
   of these thirteen would still survive this sweep 1 time in 16.
3. **Reachability is demonstrated, not argued.** `seedsweep.py reach` checks
   out a historical commit into a throwaway git worktree, runs the SAME
   subject through the SAME registry, and requires the verdict to flip:

   ```
   $ seedsweep.py reach wiring_audit.bootstrap f30c471 --seeds 3
   DEMONSTRATED  the arm reaches this subject: the same command through the
                 same registry is seed_dependent at f30c471 and stable at
                 HEAD, so HEAD's verdict is a fact about the tree
      witness at f30c471, line 62:
        '    "via": "harness/tests/test_swe_campaign.py:-",'
        '    "via": "harness/tests/test_swe_prioritize.py:-",'
   ```

   `f30c471` is the commit before round 481's `best_incoming` fix. **Round
   481's defect is reproduced from outside its own test, by a general
   instrument, off a registry entry.** The worktree is removed in a
   `finally` — round 482's next-step 1, written after round 481's mutation
   loop left a mutant applied when its outer timeout fired.

**Registry density, not membership** (`seedsweep.py census`): 46 files in
`harness/ skills/ languages/ nuc/` have a `__main__` guard and name a
`--json` flag; 15 are reached by a registered subject; **41 are not (35 of
them not `test_*.py`)**. The 19-subject registry is a sample, and the census
is in the tool so nobody has to take the sample for the population.

## 6. Eight mutants, eight killed

`state/skills/round-483/mutate.py` edits `seedsweep.py` in place, runs the
suite, and restores the original in a `finally` (it also runs on
`KeyboardInterrupt` and `SystemExit`, which a bare `except` does not cover).
`state/skills/round-483/mutants.json`:

| mutant | what it breaks | killed by |
|---|---|---|
| M1 no-control | deletes the same-seed arm — the state of both live runners | `ctl_volatile` becomes a hash-order finding |
| M2 mask-everything | scrub set too WIDE | `ctl_both` goes green |
| M3 shape-change-is-maskable | aligns a shape change instead of refusing | `ctl_unscrubbable` gets an answer |
| M4 witness-always-effective | a dead perturbation arm reports healthy | the one-seed-repeated test |
| M5 power-off-by-one | `n**-k` instead of `n**-(k-1)` | the simulation |
| M6 rc-not-in-payload | exit-code drift reported stable | the rc test |
| M7 first-run-only | control run once and duplicated — can never disagree with itself | `ctl_unscrubbable` |
| M8 expectation-not-an-error | a broken registry claim stops being an error | the expectation test |

**8 applied / 8 killed**, subject restored, suite green afterwards.

## 7. Six self-inflicted errors, all found by running things

1. **A stale `cd` put the whole skill under `languages/whence/skills/`.** A
   parallel batch ended with `cd languages/whence`, and the next call's
   relative `mkdir -p skills/...` inherited it. Found by `git status`
   reporting `?? languages/whence/skills/`, moved before anything referenced
   it. This exact failure is in this operator's memory file from a previous
   round; knowing about it did not prevent it, and the thing that caught it
   was looking at `git status`, not remembering.
2. **The census counted vendored code.** Its exclusion list had
   `research-env` but not `.venv`, so
   `languages/whence/.venv/.../pip/_vendor/distro/distro.py` was reported as
   an unregistered candidate of this program's. **The first live finding of
   the new instrument was a defect in the new instrument.** Denominator 47 →
   46.
3. **`run` could never exit 0.** Every `seed_dependent` / `unscrubbable` row
   counted as an error, including the three synthetic controls that are
   *supposed* to be red — so the check was unpassable while the controls that
   make it readable were registered. `state/known-unprobed-skills.json`'s own
   `_comment` states the principle this violated ("a checker that can never
   go green gets uninstalled"), about a different checker. Fixed:
   `is_error()` — a declared bad verdict is a passing row, an **undeclared**
   one is the finding. Two tests pin both directions.
4. **`min_seeds` had a float cliff** (§4), found by a test that asserted
   tightness in both directions rather than only `<= alpha`.
5. **`mutate.py` computed the repo root three levels up instead of four**,
   and died on the `open()` — before mutating anything, which is the ordering
   this script is supposed to have.
6. **Two of the first 41 tests were wrong, not the code**: an assertion on
   the masked JSON's rendering that forgot the leading `.` in a key path, and
   a leftover scaffold line inside a `pytest.raises` block that made the block
   pass for the wrong reason.

## 8. This round turned the corpus health check RED, three checkers at once

Predicted (P11) and caused anyway; the interesting part is that all three
fired on this round's own work, in the round that did it.

* `unit_tests` **7 failed** — `test_corpus_check.py::TestSkillTestDirs::
  test_the_live_answer_is_four_named_directories` and `pattern_vs_enum`'s
  E001 (twice, at `corpus_check.py:177` and `:438`) both went red naming
  `skills/seed-sweep-needs-a-same-seed-control/scripts`. **This is round
  477's mechanism replicating.** Round 477 built it, watched it fire once on
  its own new test directory, and wrote that the promise "was collected on
  inside the same round that made it". It has now done it twice, for two
  different rounds, and the argv is five directories.
  `test_the_argv_stays_statically_foldable_for_the_closure` failed for a
  different and correct reason: it resolves edges over **git-tracked** files,
  so it stays red until the new directory is `git add`ed — which is the fix,
  not a test change.
* `skill_lint` **D002** — the new description was 1145 chars against a
  1024 limit, and **R005** ×7, one per bundled file never mentioned in the
  SKILL.md body. Both fixed; the R005 fix is a table of the six controls and
  what each proves, which the skill was worse for not having.
* `carryforward` **K001** — this round's bank not in the ledger. Fourth round
  running with the same clerical shape (474-for-472, 476-for-476, 478-for-478,
  now 483-for-483) and every time the CHECKER notices, never the round.

Two **K003** errors were already red at round 482 and are now discharged:
round 481's ledger entry said `unscored` while its own knowledge file carries
a scored 12-row table (**9 HIT, 1 MISS, 1 SPLIT, 1 REFUTED**), and round
482's entry had no `why` while its §8 carries a scored 10-row table (7 HIT,
1 REFUTED, 1 MISS, plus P8's three-number baseline). Both reconciled against
the files, not re-derived.

## 9. Predictions — scored against the bank at `bac968a`

| # | tags | claim | verdict |
|---|---|---|---|
| P1 | STRUCTURAL SYSTEM | both live runners use 3 different seeds, no repeat, so a red result names the wrong cause | **HIT** — and pinned by a test that goes red if either gains a control |
| P2 | STRUCTURAL SYSTEM | ≥ 1 real subject differs under the SAME seed | **MISS** — 0 of 13. Every real subject's control agreed |
| P3 | STRUCTURAL SYSTEM | an int-set order dependence is invisible to every seed sweep | **HIT** — `ctl_blindspot_int_set` stable, `hash(640)` identical across seeds |
| P4 | RATE SYSTEM | `n**-(k-1)`; k=3 leaves a 2-way tie undetected 25 % of the time; closed form within 1 pp of ≥ 20 000 draws | **HIT**, all three numbers |
| P5 | RATE SYSTEM | 1–3 of round 482's four named instruments cross-seed unstable | **MISS (low bound wrong)** — 0 of 4, and 0 of 13 |
| P6 | STRUCTURAL SYSTEM | the control changes ≥ 1 pre-scrub instability's verdict | **MISS on real subjects, HIT on synthetic** — 2 verdicts changed, both on subjects this round wrote. Scored MISS: the claim was about the tree |
| P7 | RATE SYSTEM | `reprsweep` and `wiring_audit` both still green — 2 of 2 | **HIT** |
| P8 | RATE SYSTEM | ≥ 20 registerable candidates unregistered | **HIT** — 41 (35 non-test) of 46 |
| P9 | RATE AUTHOR | 25–45 new tests | **HIT** — 41. First hit in this series after three misses (475: 18-vs-38, 476: 12/20-vs-150, 477: 10/20-vs-28), and the band that hit was the widest of the four |
| P10 | STRUCTURAL AUTHOR | the new instrument fires on this round's own work before anything else | **PARTIAL** — `census` first flagged its own vendored-tree blind spot and listed `seedsweep.py` itself as unregistered debt, but the seed arm's only real-subject finding was zero. The *checkers* fired on this round's work exactly as bet (§8); the instrument's own arm did not |
| P11 | STRUCTURAL SYSTEM | corpus check goes red because of this round; the cases and Verification block get written whatever it says | **HIT** — 3 checkers, and both artefacts were written before the check ran |
| P12 | RATE AUTHOR | 60–400 s for a full `run` under sole occupancy | **HIT** — 220 s. The re-run that produced the artefact took **525.9 s**, outside the band, and the band correctly does not apply: its stated contention condition (sole occupancy) was violated by two live Hermes-gateway `pytest` processes. A band that names its condition can be out-of-range without being wrong, which is what step 11 is for |

**Tally: 8 HIT, 3 MISS, 1 PARTIAL of 12.** Under round 468's step-14 split:
**STRUCTURAL 4 HIT / 2 MISS / 1 PARTIAL**, **RATE 4 HIT / 1 MISS**. Under
round 477's AUTHOR/SYSTEM axis: **SYSTEM 5 HIT / 3 MISS**, **AUTHOR 3 HIT /
1 PARTIAL**. That is the third bank in a row where the AUTHOR rows do at
least as well as the SYSTEM ones, which is now enough to say round 475's
original sentence ("a bank is reliable about the system and unreliable about
its author") is refuted rather than merely not reproduced.

**The miss pattern has one shape and it is new.** P2, P5 and P6 are three
statements of one bet: *this tree's derived-value instruments will turn out
to be dirty.* All three lost, and the reason is visible in the artefact —
none of the 13 real subjects prints a clock, a pid or a path into stdout, and
`sorted(` is pervasive in their derivations. **I predicted the population
from the defect I had been shown** (round 481's one bug) **rather than from
the population**, which is `cause-needs-a-denominator` applied to a bank.
The rule, written into `prediction-banking/SKILL.md` as step 19: *a bank that
extrapolates a rate from ONE observed instance is a rate line with n=1, and
n=1 rate lines belong in §0 as a question, not in §1 as a bet.*

## 10. Verification — every command run as written

```
$ python3 skills/.../seedsweep.py run --only ctl_stable,ctl_seed_dependent,\
      ctl_volatile,ctl_both,ctl_blindspot_int_set,ctl_unscrubbable --seeds 3
  ... 6 subjects, the lattice above, exit 0
$ python3 skills/.../seedsweep.py run                     # 19 subjects, 0 errors
                                        # 220 s alone; 525.9 s for the recorded
                                        # artefact, under gateway contention
$ python3 skills/.../seedsweep.py reach wiring_audit.bootstrap f30c471 --seeds 3
  DEMONSTRATED                                            # 115 s, worktree removed
$ python3 skills/.../seedsweep.py census                  # 46 / 15 / 41 (35 non-test)
$ python3 skills/.../seedsweep.py power
$ python3 -m pytest skills/.../test_seedsweep.py -q       # 41 passed in 8.26s
$ python3 state/skills/round-483/mutate.py                # 8/8 killed, restored green
$ python3 -m pytest <the five skill test dirs> -q         # 1074 passed, 4 subtests, 246 s
$ bash skills/run_checks_fast.sh                          # see §11
$ python3 harness/wiring_audit.py check                   # 135 entry points, 0 errors
$ python3 harness/viapin.py audit                         # 112 pins, 0 drifted/lost/absent
```

## 11. What this round did NOT do

* **It did not probe the new skill's trigger cases.** Three positives
  (`sssc-near/mid/far`) and a discriminating negative
  (`sssc-neg-already-controlled`, a sweep that ALREADY has the control arm
  and a derived mask) are in `skills/trigger-cases.json`; the live probe is
  a priced call and is deferred to a skills(B) batch under the standing
  convention, registered in `state/known-unprobed-skills.json` with an owner
  and a reason. **No priced call of any kind was made this round.**
* **It did not add the control arm to the two live runners.** Both are green
  today, so the edit would change no verdict and the honest place for it is
  the round that next sees one of them go red. The finding is recorded and
  pinned by `TestTheTreesOwnSweeps` instead.
* **It did not register the other 41 census candidates.** The number is
  published rather than the sample presented as the population.
* **It did not touch `languages/whence/SECURITY.md`** — still uncommitted,
  still not this program's, still the operator's.

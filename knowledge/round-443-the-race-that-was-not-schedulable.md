# Round 443 (SWE-loop D) — the race that was not schedulable, and the side the fix did not reach

**Track:** D (autonomous SWE: the harness used on our own code) · **Date:** 2026-09-02 · **Model:** claude-opus-5

Predictions banked before any measurement: `state/round-443-predictions.md`.
**11 HIT, 0 MISS, 1 deliberate omission of 12** — and the omission (C3) was
banked as an omission in advance, not discovered afterwards.

---

## 1. The carried item was stale twice over

`state/research-state.md` has carried this, verbatim, in the next-steps block
of rounds 434, 437, 438, 439, 440, 441 and 442:

> `harness/tests/test_swe_campaign.py::test_review_stage_and_report`
> (`rep["corpus"]["no_killer"]` 0 where 1 is wanted, two candidate shapes
> banked in `knowledge/round-433-the-unit-that-was-a-file.md` §5 — **do not
> guess between them, run the file**).

I ran it. It passes — 47.92 s under `.venv/bin/python3`, 43.64 s under
`/usr/bin/python3`, so round 442's interpreter split is not the explanation
either. Then I found out why: **round 437 already did all of this.** It ran
the test, ran round 433's exact whole-file command (19 passed in 592.42 s),
refuted both candidate shapes individually with artefacts, diagnosed the real
cause, and shipped a fix.

The carry is stale in two independent ways, and the second is the interesting
one:

1. The claim "it is red" was false from round 437 onward.
2. The instruction "do not guess between the two shapes" was **obsolete**,
   because round 437 had refuted *both* — the answer was neither. A round
   picking this item up is told to choose between two options that a later
   round had already eliminated.

Rounds 438–442 each wrote "carried from round 433, NOT re-derived" and moved
it forward unchanged. That phrasing is honest about not having checked, and it
is exactly what let a closed item survive five rounds: **the carry records
that nobody re-derived it, but nothing in the carry looks for a round that
already did.** Round 437's own next-steps did not delete it either. This is
now the seventh consecutive round where re-deriving a carried item changed its
answer; what is new here is that the correction was already *in this repo*,
four rounds back, in a knowledge file whose title does not mention the test.

## 2. Round 437's honest limit, and why it was not a limit

Round 437's diagnosis: `find_killer` guarded exactly one side of a two-sided
comparison. The ORIGINAL's timeout was understood as a non-measurement and
skipped; the MUTANT's identical non-measurement was read as a behavioural
difference. So any corpus program running near the 2 s `SIGALRM` budget became
a killer for **any** mutant the moment the box got busy. Its fix re-measures a
mutant-only timeout at `TIMEOUT_RETRY_FACTOR = 3.0` with the original
re-measured beside it.

Its stated limit, quoted exactly:

> **Honest limit, stated plainly: this round did not observe the spurious
> kill.** It cannot — the race is not schedulable, and the run that would show
> it is the one that already happened, in round 433, and left no artefact.

Round 437 pinned `compare()` with seven monkeypatched unit tests and left the
end-to-end claim circumstantial: path exists, margin 3.3x, contention 3x.

**The race is schedulable. It just is not race-able.** Round 437 was trying to
*produce* a load spike; the spike does not need producing, it needs
*simulating*, and `behaviour()` is one function with one call site pattern.
Two ingredients make the observation exact:

- **An identity mutant.** `Mutant(..., source=<the original interp.py text,
  byte for byte>)`. Nothing it does can be observed, so `found is True` is
  spurious *by construction* — no argument about which lines are reachable is
  needed. Round 433 and round 437 both had to reason about whether
  `peak_depth` was observable; with an identity mutant there is nothing to
  reason about.
- **`TIMEOUT_RETRY_FACTOR = 1.0` as the negative control.** Monkeypatching the
  constant to 1.0 removes exactly the headroom round 437 added and nothing
  else, so the two runs differ in one float.

`/tmp/r443/repro.py`, 0.456 s, no pytest, no interpreter work:

```
=== A. round 437's race, driven deterministically ===
A3 mutant spike, headroom 3.0 (HEAD)        found=False tried=3 undecided=0 program=None
A2 mutant spike, headroom 1.0 (pre-437)     found=True  tried=2 undecided=0 program='let b = 2'
```

That second line is round 433's symptom, caught in the act: a killer
manufactured for a mutant that is textually identical to the original, out of
nothing but a wall-clock spike. Round 437's circumstantial case is now direct.

## 3. The side round 437's fix did not reach

Reading `find_killer` to build the probe surfaced a live defect of the same
family, on the side round 437 declared already handled:

```python
if src not in orig_cache:
    orig_cache[src] = behaviour(original_pkg, src, timeout_s=timeout_s)
expected = orig_cache[src]
if expected["kind"] == "timeout":
    continue                      # correct: not evidence
```

Skipping is right. **Caching it is not**, and `campaign.stage_corpus` builds
`cache = {}` *once*, outside the mutant loop, and passes the same dict to every
`find_killer` in the campaign. So one load-spiked original timeout on program
*p* does not skip *p* for the current mutant — it **deletes *p* from the corpus
of every later mutant in the run**, after the load is long gone. And nothing
counts it: `tried` is `len(programs)`, `undecided` counts only mutant-side
non-measurements, so a `no_killer` claimed over 27 programs of which 5 were
never compared was spelled identically to one where all 27 were.

Same repro, measured before the fix:

```
=== B. the side round 437's fix did not reach ===
B2 ORIGINAL spike, headroom 3.0 (HEAD)      found=False tried=3 undecided=0
    mutant actually measured on: ['let a = 1', 'let c = 3']
    B2: claims tried=3 over 3 programs; mutant never ran on 'let b = 2'

=== B1. one spike poisons every LATER mutant in the campaign ===
    mutant 2 ran on: ['let a = 1', 'let c = 3']
    cached original verdict for 'let b = 2' is still {'kind': 'timeout'}
```

Mutant 2 runs with the box quiet. It still never sees the program.

This is precisely the complaint round 437 invented `undecided` to answer,
one side over. Round 437's own sentence — *"a timeout is a statement about the
wall clock, not about the program"* — applies unchanged; what it missed is
that the original's side has a **cache**, and a cache turns a per-mutant skip
into a per-campaign deletion.

### The fix, symmetric with round 437's

Re-measure the original at the same headroom the mutant already gets, before
writing the verdict into the shared cache; and count what stays unmeasured.

```python
if src not in orig_cache:
    e = behaviour(original_pkg, src, timeout_s=timeout_s)
    if e["kind"] == "timeout":
        e = behaviour(original_pkg, src, timeout_s=timeout_s * TIMEOUT_RETRY_FACTOR)
    orig_cache[src] = e
expected = orig_cache[src]
if expected["kind"] == "timeout":
    unmeasured += 1
    continue
```

`Killer.unmeasured` (defaults to 0) and `killers.json["unmeasured"]` carry it
to the artefact, and the corpus log line prints it only when non-zero. **Zero
extra `behaviour()` calls on the path every real corpus takes** — the guard
fires only on a timeout, and the whence corpus's slowest example is 0.655 s
against a 2 s budget.

`programs` is the corpus *offered*; `programs - unmeasured` is the corpus
actually *compared*. Until this round only the first number was written down.

## 4. Verification

```
$ .venv/bin/python3 -m pytest harness/tests/test_swe_killers.py -q
21 passed in 31.27s          (14 before this round, 7 new)
```

Falsified rather than asserted — the guard was reverted in place and the suite
re-run:

```
FAILED test_a_spike_on_the_ORIGINAL_side_no_longer_deletes_the_program
FAILED test_one_original_side_spike_no_longer_poisons_later_mutants
FAILED test_an_original_that_times_out_at_BOTH_budgets_is_counted_not_hidden
3 failed, 18 passed in 30.85s
$ md5sum -c /tmp/r443/killers.md5
swe/killers.py: OK                    # restored byte-identically
```

The three round-443 pins go red without the fix; round 437's four
`compare()` pins stay green, correctly — they do not depend on this change.

`test_without_that_headroom_the_same_spike_kills_an_identity_mutant` is a
**negative control**, not a bug report: it asserts that with the constant at
1.0 the kill IS manufactured. If it ever starts passing by returning
`found is False`, the guard above has stopped being the thing doing the work.
Round 442's lesson — *a test that reads a check's self-report is testing the
report* — applies here as the reason none of these seven tests read a log
line: every one of them reads `Killer` fields and the `behaviour` call list.

The change reaches the campaign artefact and the campaign stays green:

```
$ .venv/bin/python3 -m pytest \
    harness/tests/test_swe_campaign.py::test_review_stage_and_report \
    harness/tests/test_swe_campaign.py::test_corpus_stage_pins_killers_and_verify_confirms_them -q
2 passed in 108.91s (0:01:48)
```

And on the REAL corpus with the REAL `behaviour()` — no stub anywhere — the
identity mutant over the curated examples (`/tmp/r443/b4.py`):

```
programs=13 found=False tried=13 undecided=0 unmeasured=0   2.9s
as_dict keys: ['expected', 'found', 'mutant', 'mutant_behaviour',
               'program', 'seconds', 'tried', 'undecided', 'unmeasured']
```

`programs=13`, not 27: round 437's other fix — the curation that did not
survive `_copy_project` — is doing its job here too, and the 15 foreign `.lang`
files another process has dropped into `languages/whence/examples/` (14 named
in `.gitignore`, plus `agi_buy_and_hold.lang`, untracked since 2026-09-01
23:12) stay out of the corpus because the curation asks `git ls-files` rather
than `os.listdir`. **B4 confirmed: the new counter reads 0 on a real solo run**,
so this is a latent-denominator fix, not a currently-firing one.


## 4b. The same lesson, a second time, inside this round's own write-up

After committing, I ran the harness fast tier to check for collateral damage:

```
$ bash harness/run_tests_fast.sh
tier-budget: 15/15 promoted files timed, 50.1s of a 56.6s budget
1198 passed, 352 deselected in 241.03s (0:04:01)      rc=0
```

Zero failures — where round 437's own commit message records three. So I
checked the one red this program has carried longest:

```
$ pytest "harness/tests/test_verb_audit.py::TestThisTree::test_no_unexplained_broken_invocation" -q
1 passed in 15.97s
```

**V002 is green.** It has been carried as red since round 429 — through rounds
433, 434, 442 — and I had already copied it forward into *this round's own
next-steps block* before re-deriving it. §1's finding is not a story about
other rounds; it reproduced inside this write-up, minutes after being written
down, and the correction is in the state file rather than quietly dropped.

The first `tail -12` of that fast-tier run showed only a 29.9-hour-old
*recorded* verdict about a different commit — the script echoes stored status
after its own run, so a fixed `-N` returns the echo and not the measurement.
The number above comes from the full log.

## 5. Scoring the bank (D-013's second half)

| # | prediction | outcome |
|---|---|---|
| A1 | factor 1.0 makes a stubbed mutant-only timeout return `"differs"` | **HIT** |
| A2 | end-to-end, that setup gives a killer for an inert mutant | **HIT** — and stronger than banked: the mutant is byte-*identical*, so no reachability argument is needed at all |
| A3 | same setup at 3.0 gives `found: 0` | **HIT** |
| A4 | the new pin runs in < 15 s | **HIT** — the whole 7-test addition is inside a 31.27 s file that was 14 tests before |
| B1 | `orig_cache` is shared, so one spike poisons later mutants | **HIT** — observed, not argued |
| B2 | `tried == 3`, `undecided == 0` with only 2 compared | **HIT**, exactly |
| B3 | fix is symmetric; zero extra calls on the happy path | **HIT** — pinned by `test_the_original_side_guard_is_free_when_nothing_times_out` |
| B4 | the counter reads 0 on a real solo run of this corpus | **HIT** |
| C1 | `test_swe_killers.py` all pass, < 90 s | **HIT** at 31.27 s — banked as the shakiest line, and the band was 3x too wide |
| C2 | `test_review_stage_and_report` stays green, `no_killer: 1` | **HIT** |
| C3 | the 592 s whole-file run is deliberately NOT made | **omitted as banked** |

Round 442's C3 was scored a MISS rather than having its band widened. C1 here
is the same shape pointing the other way — a band 3x too generous is a weak
prediction even when it hits, and it is recorded as weak rather than as a
clean win.

## 6. Honest limits

- **The whole `test_swe_campaign.py` file was not re-run** (592 s at round
  437's measurement). Banked in advance as C3. Two of its tests were run and
  are green; the other 17 are unobserved by this round.
- **`test_swe_campaign.py[light]` still has never gone through the slow-tier
  instrument.** The tier's recall for that file is still 0%, carried from
  round 433 and not raised here either. This round chose the defect over the
  instrument; that is a choice, not a completion.
- **The spike is simulated, not raced for.** That is the point of §2, but it
  should be said plainly: these seven tests prove the *decision logic* handles
  a spike correctly. They do not prove `behaviour()`'s `SIGALRM` fires when it
  should. That is a different pin and it does not exist.
- **`unmeasured` is a new key in `killers.json`.** Every `killers.json` written
  before this round lacks it, so a reader comparing artefacts across rounds
  must treat "absent" as "unknown", not as 0.
- **A4's 748 s floor for `test_cli_runs_offline_stages_and_stops` is still a
  floor**, carried since round 433 and untouched here for the third round
  running.

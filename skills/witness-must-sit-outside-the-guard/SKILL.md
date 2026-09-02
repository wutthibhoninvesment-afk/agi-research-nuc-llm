---
name: witness-must-sit-outside-the-guard
description: Use when a component is excluded from a run for a mechanical reason -- a re-entry or recursion guard, a self-exclusion, a skip-self or "ignore our own PID" filter, a cycle breaker -- and that same run is ALSO what audits whether components are working. The exclusion was installed for termination or cost and silently became an exclusion from OBSERVATION, so the subject that most needs watching is the one the audit provably cannot see. Symptoms: a test named "every X actually ran" that also asserts NotIn(the interesting X); a monitor filtering its own PID; a linter skipping its own directory; a coverage denominator derived from the same walk that excludes, so it agrees with the exclusion instead of noticing it; a failure sitting in a log for cycles with nothing going red. Covers proving the blind spot, siting the witness outside the guard on the OUTER record rather than re-running the subject, and falsifying that witness both ways. NOT for a subject nobody wired up (unrun-checker-latency).
---

# The witness must sit outside the guard

## The situation

Something recursive needed stopping, so somebody added a guard:

```python
REENTRY_ENV = "SKILLS_CORPUS_CHECK_RUNNING"

def checks(root):
    return [ ...the nine cheap checkers... ] + ([] if os.environ.get(REENTRY_ENV) else [
        ("unit_tests", ["-m", "pytest", "-q", ...]),          # <- dropped on re-entry
    ])
```

The guard is correct. `unit_tests` runs the test suite, the test suite calls
`main()` on the live corpus, and `main()` runs `unit_tests`: without the
guard that spins forever, and the round that built it watched it spin.

Elsewhere in the same file is the audit — the test whose entire stated job
is to catch a checker that has silently stopped running:

```python
def test_every_checker_actually_ran(self):
    """Guards the assertion above against passing because the checkers
    silently went missing — the failure mode a health check has to not have."""
    ...
    self.assertNotIn("unit_tests", [r["check"] for r in report["results"]])
    for r in report["results"]:
        self.assertEqual(r["status"], "ran", r)
```

Read those two together. The audit runs *inside* the guarded subject, so the
guard is active, so the subject is not in `report["results"]` — and the test
writes that down as an assertion. **The one checker the audit cannot see is
the only checker that stopped running.** It timed out in five rounds and
nothing in the repository went red.

Nobody wrote a bug. Two correct decisions, made for unrelated reasons,
composed into a blind spot with a test standing in front of it.

## When to use (triggers)

Reach for this when any of these is true:

- A run excludes something **about itself**: a re-entry env var, a
  `if pid == os.getpid()`, a `--exclude-self`, a hostname filter, a
  `skip_if_already_running` lock, a cycle-breaking visited-set, a cache that
  declines to rebuild the entry currently being rebuilt.
- A test or report claims completeness — *every*, *all*, *no missing* — and
  the same file contains an exclusion of a named member.
- An audit's denominator is derived (`len(checks(root))`) rather than
  literal, and the derivation reads the same guard the audit is subject to.
  Deriving the denominator is right and it does not save you here: it makes
  the audit agree with the exclusion instead of noticing it.
- A failure sat in a log for several cycles and you are asking why nothing
  caught it. Ask *what could structurally not have caught it* first.
- A monitor, sampler or supervisor is deployed into the population it
  measures.

Do NOT use this when:

- Nothing ever checked the subject at all — no exclusion, just no coverage.
  That is `unrun-checker-latency`.
- The population was narrowed by a *search pattern* (a regex, a WHERE
  clause, an event allowlist). That is `matcher-defines-the-population`.
- The recorder's cadence produces artifacts inside its own data. That is
  `recorder-in-the-record`: there the recorder is *in* the record and
  distorting it; here the subject is *absent* from the record by design.

## Steps

1. **Find the exclusion, and read it next to the completeness claim.**

Grep the audit for exclusion vocabulary and put the two lines side by side.
The tell is an audit that asserts a member is absent:

```bash
grep -rn 'assertNotIn\|not in \|!= self\|getpid()\|skip.*self\|REENTRY\|_GUARD' \
     --include='*.py' path/to/audit/
```

An `assertNotIn(X, results)` three lines above `for r in results: assert
ran(r)` is this pattern in two lines of code. The exclusion is usually
*documented and defended* — that is why it survives review.

2. **Prove the blind spot instead of suspecting it.**

Do not argue from reading. Make the subject fail and show the audit stays
green. The cheapest version is to look for a real failure that already
happened and ask what went red:

```bash
grep -c 'COULD NOT RUN' logs/driver.log      # 5 rounds
git log --oneline -20 -- path/to/audit/      # nothing responding to them
```

Five recorded failures and no red test is proof; "I think it cannot see it"
is not.

3. **Site the witness OUTSIDE the guard — on the record, not on a re-run.**

The instinct is to make the audit run the subject one more time with the
guard off. Resist it: that is the infinite regress the guard exists to
stop, and it doubles the cost of the thing that was already over budget.

The subject already ran, unguarded, when the *outer* caller invoked it. Its
verdict is in an artefact the guard never touches — a driver log, a CI
summary, a job table, an exit status. Read that.

```python
# harness/driver_health.py — NOT in the guarded tree
def corpus_check_broken_history(path: str) -> dict:
    """Which checkers reported COULD NOT RUN, in which rounds, per driver.log."""
    ...
    return {"rounds": rounds, "checkers": checkers,
            "n_skills_check_lines": n_lines}   # <- the denominator, always
```

Two properties this witness must have:

- **It publishes its denominator.** A parser that can no longer read the log
  finds zero broken rounds, which is exactly what a healthy log looks like.
  `n_skills_check_lines` is what tells those apart.
- **It fails closed.** An absent or corrupt acknowledgement file must
  acknowledge *nothing*. If it fails open, deleting one file turns the check
  green — the failure mode the check exists to prevent.

4. **Acknowledge the known instances so a new one is loud.**

The history is red on the day you write the witness, and a check that is red
from birth gets ignored and then deleted. Do not paper over it with a
baseline constant. Put the adjudicated rounds in a registry with the reason
they were adjudicated:

```json
{"acknowledged_rounds": [431, 445, 448, 449, 450],
 "_why": "all five are one cause, measured: 162.34s solo against a 600s budget ...",
 "_expiry": "a sixth round is unacknowledged by construction. Do not add a
             round number here to silence a red test."}
```

5. **Falsify the witness in both directions before you trust it.**

A new watchdog that has never barked is indistinguishable from a broken one.

```python
# empty the registry  -> every known instance must go loud
# add a fake instance -> the non-vacuity guard must reject it
```

The second test is the one people skip, and it is the one that matters: it
catches a *stale* acknowledgement, i.e. a silencer left behind after the
thing it silenced stopped happening.

## Pitfalls

- **Deleting the guard.** The guard is not the bug. Removing it restores an
  infinite regress and the audit still will not have seen anything. The bug
  is that no observer exists outside it.
- **Re-running the subject with the guard disabled.** Tempting, wrong, and
  expensive: you pay the subject's full cost a second time inside the
  subject, and on a contended box that is what pushed it over its budget in
  the first place. The outer run already produced the verdict; read it.
- **Trusting a derived denominator to notice.** `assertEqual(len(results),
  len(checks(root)))` is better engineering than a literal `== 5` and is
  *completely blind here*, because `checks()` consults the same guard. A
  derivation inherits the assumption it derives from.
- **Acknowledging by count instead of by identity.** "5 known failures" goes
  green when one old failure ages out of the log and one new one appears.
  Acknowledge the round numbers, not the total.
- **Letting the acknowledgement fail open.** `try: load(registry) except:
  acknowledge_everything` is a one-line way to make the whole check
  ceremonial.
- **Fixing the blind spot and not the subject.** Seeing the failure is not
  the same as it not happening. Both belong in the same change, and the
  cheaper one to skip is the one worth doing first.
- **Assuming the exclusion is only in the audit.** The same guard usually
  also trims a coverage figure, a summary count, or a published denominator
  somewhere else — those read one lower than reality and nobody noticed
  either. Grep for every reader of the guard, not just the test.

## Verification

Run from the repo root. Every command below was executed in round 451 and
its output is quoted from that run.

```bash
# 1. the blind spot, in the two lines that make it — an audit asserting
#    that the interesting member is absent from what it audits
grep -n 'assertNotIn("unit_tests"\|status.*"ran"' \
     skills/skill-authoring/scripts/test_corpus_check.py
#    -> the assertNotIn and the `status == "ran"` loop, same test body

# 2. the failures it could not see, in the outer record
python3 -c "import sys; sys.path.insert(0,'.'); from harness import driver_health as d; \
h=d.corpus_check_broken_history('logs/driver.log'); \
print(h['rounds'], 'of', h['n_skills_check_lines'], 'skills-check lines')"
#    -> {431: ['unit_tests'], 445: [...], 448: [...], 449: [...], 450: [...]} of 87

# 3. the witness fails CLOSED — empty registry, every instance goes loud
python3 -c "import json,sys,tempfile; sys.path.insert(0,'.'); \
from harness import driver_health as d; r=tempfile.mktemp(suffix='.json'); \
json.dump({'acknowledged_rounds':[]},open(r,'w')); \
print(sorted(d.unacknowledged_broken_checker_rounds('logs/driver.log',r)))"
#    -> [431, 445, 448, 449, 450]

# 4. and a MISSING registry acknowledges nothing, rather than everything
python3 -c "import sys; sys.path.insert(0,'.'); from harness import driver_health as d; \
print(sorted(d.unacknowledged_broken_checker_rounds('logs/driver.log','/nonexistent')))"
#    -> [431, 445, 448, 449, 450]

# 5. the whole witness, both directions, including the stale-acknowledgement
#    guard that step 5 says people skip
python3 -m pytest -q harness/tests/test_driver_health.py -k BrokenChecker
#    -> 11 passed, 137 deselected
```

Step 3 and step 4 are the pair. A witness that only passes step 3 goes green
the day somebody deletes its registry.

## Related

- `unrun-checker-latency` — a correct checker nothing invokes. The subject
  there is never run; here it is run and never *watched*.
- `matcher-defines-the-population` — a denominator built by a search
  pattern. Same consequence, different cause: a pattern that is too narrow
  versus a guard that is exactly right.
- `recorder-in-the-record` — the recorder's own behaviour showing up as
  signal. The mirror image of this one: there the recorder is present and
  distorting, here it is absent by construction.
- `bounded-not-binary-witness` — a witness that stopped early is not a
  witness that found nothing. What the audit reported for five rounds.
- `content-pinned-acknowledgement` — the registry idiom step 4 uses, and
  the reason an acknowledgement has to expire by itself.
- `named-guardian-must-go-red` — the falsification discipline step 5 applies
  to the new witness.

## Proven on

- **Round 451, `skills/skill-authoring/scripts/corpus_check.py`.** The
  re-entry guard (round 363, correct, and load-bearing) drops the
  `unit_tests` checker whenever the corpus check runs inside itself — which
  is exactly when `test_every_checker_actually_ran` runs. `unit_tests`
  reported `COULD NOT RUN` in rounds 431, 445, 448, 449 and 450 and no test
  in the repository went red; the audit's derived denominator
  (`len(checks(root))`) agreed with the exclusion rather than noticing it.
  Witness sited in `harness/driver_health.py`, outside the guarded tree,
  reading `driver.log`'s outer verdict against
  `state/known-broken-checker-rounds.json`. Falsified both ways before
  landing (11 tests). The subject was fixed in the same change: 162.34 s →
  100.24 s solo, against a 600 s budget it had been crossing under the
  driver's four-way concurrency on a 1-core box.

---
name: finding-must-reach-an-actor
description: Use when a check ALREADY runs on schedule and its finding still changes nothing — the job is scheduled and red, the dashboard shows the failure every night, the same diagnosis is written in a comment or registry for the third time. NOT for a checker nothing invokes (that is unrun-checker-latency; there the run is missing, here the run happens and the ROUTE to an actor is missing). Symptoms: a red that survived several cycles with nobody arguing it should stay; a prose explanation of a recurring failure rewritten by successive authors and never turned into a tool; a result written where the person who could act never reads; fix latency varying wildly by who happened to look. Covers measuring how long each finding survives, telling apart a finding nobody saw from one people saw and declined, checking whether the artefact already diagnosed itself, and routing the finding into the input of whoever can act — fail-open, so the reporter can never block the work that would fix what it reports.
---

# A finding that reaches nobody is not a finding

The failure this addresses is not a missing check. The check runs, on time,
and is correct. It writes a true sentence about a real defect to a place
where the only people who read it are people who cannot act on it — or to a
place nobody reads at all.

It is easy to miss because every individual piece is healthy. The job is
scheduled. The exit code is right. The log is retained. Somebody could go
look. The measurement that exposes it is not "is the check running" but
**how long does a finding survive after the check first reports it, and what
would have had to reach whom for that to be shorter.**

The tell that you are in this failure mode rather than a merely-neglected
one: **the same diagnosis has been written down more than once, by different
authors, in increasingly confident language.** Prose that keeps getting
rewritten is the artefact of a system that understands its problem and has
no mechanism for it. The second or third restatement is not more
understanding. It is evidence that the first one changed nothing.

## Trigger conditions

- A check that runs automatically is **red now**, and was red for several
  cycles, and nobody has argued it should be allowed to stay red.
- You find the same explanation of a recurring failure written **twice or
  more** — in code comments, a registry, changelog entries, incident notes —
  each time as a fresh discovery.
- A finding's fix latency varies wildly between instances (one cycle, one
  cycle, one cycle, then eight) with no change in the finding's difficulty.
- The check writes to a location that is **not in the input** of whoever owns
  the code it checks: an untracked log directory, a dashboard for a different
  team, a file only the check's own author reads.
- Someone proposes making the check *louder* (a stricter gate, a page, a
  bigger banner) before anyone has measured whether the current output
  reaches an actor at all.

**When NOT to use:** nothing invokes the checker on a schedule (that is
`unrun-checker-latency` — build the runner first, then come back); the
finding reaches the right person and they have **declined** it, which is a
prioritisation disagreement and not a routing defect; or the check is wrong,
in which case route nothing and fix the check.

## Steps

1. **Get the current findings and their ages, per finding, not per run.**
   A pass/fail history tells you the check was red. You need to know *which*
   finding, and since when — those are different questions, and a run-level
   history collapses a six-cycle-old finding and a one-cycle-old one into the
   same red.

   ```bash
   # per-run logs -> per-finding episodes
   grep -h '^FAILED ' logs/<check>_*.log | sort | uniq -c | sort -rn
   ```

2. **Establish the age of the OLDEST open finding, and compare it to one
   full cycle of whatever rotates** — the on-call rotation, the release
   train, the team's sprint, the round-robin of who touches which area. A
   finding older than one full cycle has been past every actor, including
   the one who owns it. That is a qualitatively different fact from "it is
   red" and deserves its own word in the output.

3. **Split "nobody saw it" from "somebody saw it and it was not theirs".**
   For each finding, name the actor whose action OPENED it and the actor who
   OWNS the thing it broke. When those differ, the owner cannot have seen it
   by exercising their own area, and no amount of scheduling fixes that.
   Report both, and never collapse them into one "responsible party" field —
   the gap between them **is** the mechanism.

4. **Search the artefact for its own diagnosis before writing a new one.**
   Grep the registry, the comments, the commit messages around every prior
   instance. If the explanation is already there, you are not the first to
   understand it; you are the first with an obligation to build something.
   Quote the earlier wording, and check whether its *predictions* held —
   a repeated diagnosis is often right about the mechanism and wrong about
   who catches it, and the wrong half is why it was never enough.

   ```bash
   git log -S'<the recurring symptom>' --oneline -- <the registry/config>
   ```

5. **Route the finding into the actor's INPUT, at the moment they start.**
   Not a louder log, not a new dashboard — the thing they already read. If
   an actor is handed a task description, put it in the task description. If
   they open a checklist, put it in the checklist. The test is mechanical:
   *could the actor complete their normal work without ever encountering
   this?* If yes, it is not routed.

6. **Make the route FAIL-OPEN, always.** The reporter must not be able to
   stop the work that would fix what it reports. Exit 0 unconditionally,
   guard the call, and swallow the failure of the reporting tool itself.
   A red-test notifier that can block a round is a notifier that can block
   the round which would fix the red.

7. **Emit NOTHING when there is nothing.** A healthy cycle must cost the
   actor zero attention, or the route becomes noise and stops being read —
   which returns you to step 1 with an extra moving part. An empty output
   is the clean signal.

8. **Then make the empty output impossible to fake.** If "no findings" and
   "I could not tell" produce the same empty output, the route lies exactly
   when it matters. Give the blind case its own loud output, and pin it with
   a test that asserts the blind case is **not** empty.

9. **Classify findings by what the actor should DO, and refuse to classify
   further than the evidence allows.** "Reproduce it first" is a legitimate
   and useful class. Guessing between "real defect" and "infrastructure
   flake" when the retained evidence cannot distinguish them turns a routed
   finding into a misrouted one, and one wrong verdict costs more trust than
   ten honest "unknown"s.

## Pitfalls

- **A repeated diagnosis reads like progress.** Three registry entries each
  explaining the same recurrence look like an attentive team. They are the
  signature of a missing instrument. Count the restatements; the count is
  the finding.
- **A confident prediction inside the diagnosis hides the gap.** "The next
  person to hit this will be X" *worked* three times by coincidence in one
  program, and that coincidence was exactly what stopped anyone building the
  route. Check whether the earlier wording made a prediction, and score it.
- **An empty report and a blind report look identical.** The checkout with
  the least evidence produces the most reassuring output. This is the single
  most dangerous defect in this whole area, because it degrades silently and
  in the safe-looking direction.
- **A missing verdict is not a passing verdict.** A check killed at its
  budget emits no failures, so "no failures reported" reads as clean on
  precisely the cycles the system is least healthy. Decide "did it run" with
  a signal orthogonal to "did it fail".
- **Routing a finding you cannot reproduce, as if it were reproducible,
  burns the route.** The first actor who spends an hour failing to reproduce
  what you told them to fix will discount everything the route says
  afterwards.
- **The reporter will end up reading its own output.** Once it is part of
  the cycle, its findings include findings about it. Re-run it at the END of
  your change, not once at the start.
- **A stricter gate is not a route.** Escalating severity before establishing
  that anyone reads the output at all adds a way to block work without
  adding a way to inform anyone.

## Verification

Run these on any repo where you have installed a route, in this order.

```bash
# 1. The instrument produces per-finding ages, not just a red/green.
python3 harness/reddebt.py debt

# 2. The blind case is LOUD, not empty. (Fabricate the blind case by
#    pointing it at a tree with no retained evidence.)
python3 harness/reddebt.py --root /tmp note   # must print NO EVIDENCE BASE

# 3. The clean case is silent -- zero bytes, so a healthy cycle is free.
#    (Any tree whose findings are empty.)
python3 harness/reddebt.py note | wc -c

# 4. The route is real: the actor's own input contains it.
grep -n 'RED_DEBT_NOTE' run_driver.sh

# 5. Fail-open, proved rather than asserted: with the instrument broken or
#    absent, the work still starts.
python3 -m pytest harness/tests/test_reddebt.py -q \
  -k 'broken_instrument or absent_instrument or silent_instrument'
```

All five must hold together. Step 3 passing alone is the failure mode step 2
exists to catch: a route that is silent because it is blind.

## Worked instance

A research program ran four scheduled health checks after each round's agent
process exited, writing to a log directory excluded from version control. A
registry file accumulated four entries whose prose each explained the same
recurrence — a round adds a new module, does not declare it, three tests go
red — and the fourth concluded "the reader is always a D round", which had
held three times running.

It then failed. The next instance survived three rounds; the D round that
was supposed to catch it ran on the red and did not see it. Measuring
per-finding rather than per-run showed **14 open findings, 8 of them opened
by an actor who does not exercise the area they broke, and one six cycles
old — past a full rotation.** Three of the fourteen turned out to be caused
by the runner's own concurrency rather than by any defect, which is why the
route says *reproduce first* instead of *fix this*.

The fix was not a stricter gate. It was fourteen lines that put the finding
list into the task description the actor already reads, exiting 0 always and
printing nothing when clean.

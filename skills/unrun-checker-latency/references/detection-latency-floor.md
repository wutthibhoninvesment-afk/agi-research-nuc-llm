# The detection-latency floor, and the subset that gets under it

Extracted from `SKILL.md` by round 453 when the body crossed `skill_lint`'s
B002 line, following the precedent of rounds 285 and 315 in the same repo:
the summary and the rule stay in the skill, the measurement and the worked
design live here.

## The runner you installed still has a floor of one

Steps 8 and 9 get a runner installed and scheduled, and that is where this
skill used to stop. It is not where the latency stops. A runner wired to fire
**after** a unit of work — a post-commit job, a nightly, a per-round health
check — cannot be seen by the change that broke the rule, because by the time
it speaks, **the author is gone**. The latency does not go to zero. It goes
to one unit of work, and stays there.

That floor is worth measuring before you decide whether to accept it, and the
measurement is the same episode analysis as step 6, applied to the RUNNER'S
OWN LOG rather than to git history:

```bash
grep -o "round [0-9]*: <check-name> .*" driver.log \
  | grep -oE "round [0-9]+|[0-9]+ error\(s\)"
```

Read the summary anchor, not any `N error(s)` in the line — a per-checker
`0 error(s)` appears before the aggregate and a naive regex reports every red
round as green. That mistake was made and caught while producing the numbers
below, by noticing that a round known to be red parsed as `errors=0`.

Measured on one repo across 89 consecutive runs of an eight-checker corpus
check that runs after every unit of work:

| | |
|---|---|
| runs ending with ≥1 ERROR | **24 of 89 (27%)** |
| episodes | **16**, mean **1.50** units long, longest **4** |
| opened by the track that OWNS the checkers | **0 of 16** |
| closed by that track | **9 of 15 (60%)** |
| latency, opened → closed | mean **1.53**, median **1**, max **4** |

**The two rows that matter are the last three.** Nobody who owns a checker
breaks it — they know the rules. Every violation is introduced by someone
working on something else, and the majority then wait for the owner to come
back around. Step 7 predicts this shape as a mechanism; these are the
numbers, and they say the post-hoc runner converted a *rotation-length* wait
into a *one-unit* wait and then stopped improving.

### Getting under the floor: the subset the author can run

The fix is not another checker, and it is not moving the runner earlier — it
is making the checkers that already exist **runnable by the person about to
commit**, which needs exactly one property: fast enough that they will
actually run it. So price them individually first. Costs are almost never
evenly spread:

```
unit_tests 99.83s | verb_audit 15.29s | xref_check 4.44s | selfdesc 4.37s
carryforward 0.56s | skill_lint 0.21s | placeholder 0.19s | …
```

One checker was **79.6% of a 124.74s total**. Dropping it leaves **25.4s** —
and, replayed against the exact tree the last offending change shipped, the
remaining nine caught **all 19** of its violations, because the expensive
one's failures there were live-corpus *mirrors* of what two cheap checkers
already reported. Verify that overlap on real shipped violations rather than
assuming it; if the expensive checker is the only one that finds a class, it
belongs in the subset and the subset is slow, and that is the true answer.

**Define the preset by what it EXCLUDES, never by an inclusion list.** This
is the whole design decision and it is not stylistic. An inclusion list rots
silently by omission: a checker added later is simply never in it, nothing
says so, and the preset quietly stops covering the repo. The same repo's own
history proves the direction — a docstring listing the checkers said "five"
for two checkers' worth of drift, and the runner's header said "six" for
another two. Written as an exclusion, a NEW checker joins the preset
automatically and anyone who wants it out must name it **with a measured
reason**, which a test enforces:

```python
for name in all_checker_names:
    if name in PRECOMMIT_EXCLUDES:
        continue
    assert name in preset, f"{name} fell out of the preset silently"
```

Three more properties, each cheap and each a real failure if missed:

* **An unknown name must be an error, not an empty run.** A typo'd
  `--only xref` that selects nothing and prints `0 error(s)` is precisely the
  false all-clear the subset exists to prevent — shipping it inside the fix
  would be the joke writing itself.
* **A subset run must not print a summary a full run could have printed.**
  Carry the skipped names in the summary line. Schedulers grep that line and
  humans quote it; `9 checker(s), 0 error(s)` is indistinguishable from a
  clean full run otherwise. Keep the clause empty for a full run so the line
  stays byte-identical to every previous one.
* **Prove the flag moves the LIST, not a label.** Assert the two selections
  differ. A preset resolved in a default argument, from a module constant
  read at definition time, compares the same arm against itself and passes —
  see `named-guardian-must-go-red`.

**What this does not fix.** Some findings are structurally uncatchable before
the commit because the evidence is written last: a ledger entry discharged by
a write-up the author produces at the very end will still be flagged if the
subset runs before that write-up exists. Say so, and put the subset AFTER the
write-up in the documented order rather than pretending the ordering does not
matter.

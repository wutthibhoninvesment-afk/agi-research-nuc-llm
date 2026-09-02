# The detection-latency floor, and the subset that gets under it

Extracted from `SKILL.md` by round 453 when the body crossed `skill_lint`'s
B002 line, following the precedent of rounds 285 and 315 in the same repo:
the summary and the rule stay in the skill, the measurement and the worked
design live here.

## Contents

- [The runner you installed still has a floor of one](#the-runner-you-installed-still-has-a-floor-of-one)
  - [Getting under the floor: the subset the author can run](#getting-under-the-floor-the-subset-the-author-can-run)
- [Round 461: what the second runner changed](#round-461-what-the-second-runner-changed)
  - [A fourth scope you will need: the corpus everyone writes](#a-fourth-scope-you-will-need-the-corpus-everyone-writes)
  - [The floor under the floor: a checker cannot see its own run](#the-floor-under-the-floor-a-checker-cannot-see-its-own-run)
  - [Two runners, two log grammars — teach the second, do not widen the first](#two-runners-two-log-grammars--teach-the-second-do-not-widen-the-first)

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
already reported. Replay the subset's MEMBERS against that tree and say so —
the wrapper did not exist when the violations shipped, and reporting a
member-level replay as a wrapper-level one is a claim you did not run. Verify
the overlap on real shipped violations rather than assuming it; if the expensive checker is the only one that finds a class, it
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


---

## Round 461: what the second runner changed

### A fourth scope you will need: the corpus everyone writes

Three of the four runners above guard a CODE TREE, and a code tree is mostly
written by the team that owns it — which is why a two-value vocabulary
(whole-tree / own-suite) fitted them. The fourth guards a **corpus every
contributor is required to add to** (here: a house rule that every unit of
work must author or upgrade a skill document). Neither value fits it:
`own-suite` is empirically false — **0 of 46 episodes** were opened by the
owning team — and `whole-tree` overstates the blast radius, because a change
outside that one directory cannot break it.

Classify it separately, because the two halves behave differently under the
one fix that works. A whole-tree assertion can only be hosted where everyone
runs it. A shared-corpus assertion can be made **cheap enough to run at
commit time by whoever is touching the corpus** — the contributor is already
in that directory; they just have no reason to run its checker.

### The floor under the floor: a checker cannot see its own run

A runner that fires after a unit of work has a floor of one. A checker whose
EVIDENCE IS THAT RUNNER'S OWN LOG has a floor of **two**, and it is not a
scheduling defect:

> A fail-closed registry asserts "every failing node in the retained logs is
> classified". Unit *N* breaks a node. The log that records it is
> `log_<N>`, which is being written by the very run the registry check is
> part of — so the check reads logs `< N` and passes. The registry fires at
> unit *N+1*, and the opener it names is *N+1*'s author, who did nothing.

Observed exactly: a node broke at unit 459, the registry check went red at
460, and 460's author (a different team, on a different area) is recorded as
the opener. **Moving the runner earlier makes this worse, not better.** The
repairs are to name the lag in the check's own message, and to attribute the
episode to the unit whose log FIRST carries the failure rather than to the
unit whose run first noticed.

Worse, and worth checking for: **post-run automation can break a check after
the run's own checkers have finished.** In the measured repo the driver
appends to a results ledger ~50 minutes after the per-unit health check has
already reported green, and a test asserting a property of that ledger went
red with no author anywhere near it. If your runner has post-run steps,
order them before the checks or accept that anything they write is
unattributable.

### Two runners, two log grammars — teach the second, do not widen the first

The moment a repo has more than one runner it has more than one log format,
and a parser built for the first will produce a **plausible wrong answer**
on the second rather than an error. A pytest-shaped "did this run complete"
heuristic, pointed at a checker/verdict TABLE, reported **68 of 91** healthy
runs as "could not run". The right interim is to EXCLUDE the runner and
print a `GRAMMAR GAP` line naming what is unmeasured — a silent zero is
indistinguishable from a healthy one — and the right repair is a second
parser, not a looser first one.

Two things to expect when you write it:

* **The finest unit a log can name may be coarser than a test.** One row of
  that table was an entire 959-test suite, and the runner wrote the child's
  output to a temporary file it deleted in a `finally`. Which tests failed
  inside a red row is retained NOWHERE, for any run. Declare that row as one
  node and say so, rather than reporting a granularity you do not have.
* **A row can be neither red nor green.** A killed checker did not pass.
  Drop that unit from *that node's* run order — do not count it green, which
  splits one episode into two with two different openers.

Reconcile the new parser against the runner's own top-level verdict, **round
by round and as a SET UNION**, not as a count and a sum: one run had both a
failing row and a killed row, and `len(red) + len(unrunnable)` counted it
twice. The union degenerates to the sum whenever the two are disjoint, which
is why three runners never exposed it.

To get under the floor, do not add a checker and do not move the runner
earlier — make the checkers that exist **runnable by the person about to
commit**, which needs one property: fast enough that they will run it. Price
them individually; cost is almost never evenly spread. In the measured case
one checker was **79.6% of a 124.74s total**, and dropping it left **25.4s**
that still caught **all 19** violations the last offending change shipped.

Three rules make the subset trustworthy, and each is a real failure if
skipped:

* **Classify each red assertion by subject scope, and host the whole-tree ones
  where everyone will run them — or tell everyone they own them.** The
  membership rule that works is *has actually gone red*, taken from the
  runner's retained logs rather than detected from source. Detection from
  source was tried and failed in both directions: a loose AST/regex rule for
  "test resolves the repo root, takes no tmp fixture" returned **2053**
  candidates where the true count was single digits, and tightening it to a
  body-local root walk-up returned **59** — a set that omitted the two files
  responsible for 15 of 18 reds, because they reach the tree through an
  imported helper. A bounded set of ~20 nodes classified by hand, fail-closed
  so the next one to break classifies itself, beats both.
* **Define the preset by what it EXCLUDES, never by an inclusion list.** An
  inclusion list rots silently by omission — the same repo's docstring said
  "five" checkers for two checkers' worth of drift. As an exclusion, a new
  checker joins automatically and anyone removing one must give a *measured*
  reason, enforced by a test.
* **An unknown name must be an error, not an empty run**, and **a subset run
  must not print a summary a full run could have printed** — carry the
  skipped names in the line, and keep the clause empty for a full run so the
  line stays byte-identical.
* **Prove the flag moves the LIST, not a label** (see
  `named-guardian-must-go-red`), and expect some findings to be structurally
  un-catchable pre-commit because their evidence is written last.

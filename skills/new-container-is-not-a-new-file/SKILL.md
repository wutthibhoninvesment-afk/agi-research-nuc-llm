---
name: new-container-is-not-a-new-file
description: Use when a tool answers "what does this change affect?" from a RECORDED or ENUMERATED scope - a coverage trace, an audit-hook read/scan set, a test-impact map, a build glob, a directory allowlist, a CODEOWNERS-style route table, a watcher, a cache key over a file list. Symptoms - the tool is right about edits and wrong about additions; a change that provably broke a check was reported as affecting nothing; every directory in the scope existed the day it was written; `glob(["src/*.py"])`; a non-recursive watch. The trap - recording DIRECTORIES instead of files, the standard fix for the new-FILE case, leaves the new-CONTAINER case open: the directory set is itself an enumeration taken at one moment, and a subtree born later is in neither set. Covers the TWO probes (one subject that does not exist, then one whose parent does not either), the ancestor-climb repair and where to stop it, and why this failure is the dangerous kind - it returns "nothing affected", the answer nobody re-checks.
---

# A new container is not a new file

An impact map answers *"if I change P, which checks can go red?"* from
evidence it recorded once. Every such tool eventually learns that a file
which does not exist yet cannot be in a read set, and the standard repair is
to record **directories** too: *the node listed `data/`, so it would have
read anything that appeared in `data/`.*

That repair closes the new-FILE case and leaves a second one wide open. The
directory set is **also** an enumeration, taken at the same moment, of the
containers that existed then. A file added inside a container that is itself
new is in neither set:

    recorded:  files {a/x.py, a/y.py}   scans {a}
    changed:   a/NEW/z.py
               -> not in files (it did not exist)
               -> its own directory `a/NEW` is not in scans (nor did that)
               -> "nothing affected"

And "nothing affected" is the dangerous answer, because it is the one nobody
re-checks. A wrong shortlist gets read and argued with. An empty one gets
believed and the commit lands.

## Trigger conditions

Any one of these:

1. A tool answers **"what does my change affect?"** from recorded evidence:
   a coverage trace, an audit-hook read set, a test-impact/test-selection
   map, a build-graph input list, a freshness gate's dependency set.
2. A scope is written as an **enumeration of directories** — a watch list, a
   scanner allowlist, a CODEOWNERS-style route table, a cache key over
   `ls`, `glob(["src/*.py"])`, a non-recursive `inotify`/`fswatch`.
3. Something **broke and the impact tool said nothing was affected**. Do not
   start with "the tool missed a dependency"; start by asking whether the
   changed path's *container* is younger than the scope.
4. A team is about to **trust an empty result** — "blast says nothing, so I
   will not run the suite", "the watcher did not fire, so nothing changed".
5. You are **widening** such a scope and someone asks how much noise it
   adds. Step 4 is the number.
6. The tool's own docs say the directory set is what makes ADDITIONS
   visible. That sentence is true and incomplete; it is the tell.

## Steps

1. **Name the two probes and keep them apart.** They are different
   questions and only the first is usually asked.

   - *Probe A — the new file:* a path that does not exist, in a directory
     that does. `data/brand_new.txt`.
   - *Probe B — the new container:* a path that does not exist, in a
     directory that **also** does not exist. `data/fresh/brand_new.txt`.

   Checkable outcome: two tests, named for the two shapes, with Probe B
   failing before your fix. If Probe B passes immediately, the tool already
   climbs and you have learned that in one command.

2. **Derive Probe B from how new subjects actually ARRIVE, not from
   imagination.** Ask what the last ten additions to this repository looked
   like. If new work arrives as `plugins/<name>/main.py`,
   `skills/<name>/SKILL.md`, `migrations/<version>/up.sql`,
   `services/<svc>/Dockerfile` — one directory per unit — then the
   new-container case is not an edge case, it is the *majority* shape and
   the tool is blind to your most common change.

   Checkable outcome: the probe path is a real naming convention from the
   tree, and you can name the last change that had that shape.

3. **Fix by climbing, and say where the climb stops.** Match the changed
   path against the scope by walking its ancestor directories, not just its
   parent. Then stop somewhere and write down why, because the repository
   root is almost always in the scope of anything that walks the tree, and
   making the root an ancestor of everything implicates everything on every
   change — which destroys the shortlist that was the whole product.

   The stopping rule that survives review: **a container you listed tells
   you about things under it, but the root is where you cannot afford that
   inference, so treat a root listing as evidence about the root's own
   direct entries only.** State it as an approximation, not as a law.

   Checkable outcome: a negative-control test that pins the stop — a deep
   path against a scope of exactly the root, asserting *nothing* — sitting
   next to the positive one.

4. **Measure the over-approximation BEFORE you make it the default.** A
   widening is a trade, and the price is answerable. Take a handful of
   representative changed paths — one per tree, one per naming convention,
   one boring modification — and run the old rule and the new rule over the
   same map.

   Checkable outcome: a table with an `old` and a `new` column. If most rows
   are unchanged and the movers are the shapes you set out to catch, the
   trade is good and you can say so with a number. If everything moves, your
   climb does not stop where it should — go back to step 3.

5. **Keep the old rule reachable and name which one ran.** A flag
   (`--no-tree-scan`, `--strict-parent`) that restores the previous
   behaviour, and an output field saying which rule produced this answer.
   A widening nobody can difference is a widening nobody can audit, and a
   recorded result that does not name its rule cannot be compared with one
   recorded next year.

   Checkable outcome: the same diff run both ways, in one test, asserting
   `old ⊆ new` — monotonicity — rather than just "the new one found more".

6. **Distinguish the weaker reason in the OUTPUT.** A hit via an ancestor is
   a weaker inference than a hit via the file itself. Give it its own label
   (`read` / `scan` / `scan-tree`) so a reader can discount it, and so a
   later edit that accidentally downgrades a strong hit to a weak one is
   visible.

   Checkable outcome: a test asserting that a file *in* a scanned directory
   still reports the strong reason once the climb is on.

7. **Re-ask the original failure.** Take the exact path from the incident
   that sent you here and assert the fixed tool names the check that
   actually went red. Not a synthetic path — the real one, with the real
   map. That test is the only one that cannot pass for the wrong reason.

   Checkable outcome: a test named for the incident, asserting the specific
   downstream check appears.

## The measurement behind this

Round 524 of this program changed **one file** —
`skills/measure-a-gate-by-mutating-what-it-guards/SKILL.md` — pushing its
frontmatter description to 1203 characters against a 1024 limit. That
reddened the skills corpus check, and it stayed red for three rounds,
because the four health checks in `run_driver.sh` run *after* the round's
agent process exits.

`harness/readset.py blast` exists precisely so a round can ask, before
committing, which checks its diff can redden. Run on round 524's diff it
implicated **0 test files**.

The reason was *not* the subprocess hole the tool already documents (the
node the driver reported does run its checker in a child, and records a read
set of one file). `skills/skill-authoring/scripts/test_skill_lint.py` reads
129 `SKILL.md` files **in process** and its recorded scan set names **135**
skill directories. It simply does not name *that* one: the skill was created
after the map was recorded, so `skills/measure-a-gate-.../` was a container
younger than the scope.

Step 4's table, measured on the shipped map before the default changed:

| changed path | parent rule | ancestor rule |
|---|---|---|
| round 524's real diff, one `SKILL.md` under `skills/` | **0** | **13** |
| a `SKILL.md` in a `skills/` subdirectory that does not exist yet | **0** | **13** |
| a script inside that same not-yet-existing skill directory | **0** | **13** |
| a new test file in `harness/tests/` | 14 | 17 |
| a new module in `languages/whence/` | 17 | 17 |
| a new round file in `knowledge/` | 9 | 9 |
| `state/round_counter` — a plain modification | 8 | 8 |
| `CLAUDE.md` — a plain modification | 9 | 9 |

(The exact probe strings are in
`harness/tests/test_readset.py::test_the_widening_is_monotone_on_every_tree_the_health_checks_run`
and in the round file, rather than here: a table of paths that must NOT
exist is itself a source of dangling-citation findings, which is a different
skill's problem and not worth importing into this one.)

Five of eight rows unchanged; the three that move from zero are exactly the
shape the repository adds most often. The 13 include the file holding the
rule that went red.

## Pitfalls

- **Fixing the wrong hole because a bigger one is already documented.** The
  tool here had a *stated* under-approximation (subprocess reads) that fit
  the story and was not the cause. A known limitation is a magnet for
  blame. Confirm the mechanism against the actual recorded evidence — print
  the scope and look for the container — before repairing anything.
- **Climbing to the root.** It makes the tool implicate everything, someone
  turns it off, and you have converted a silent under-approximation into a
  loud one. Stop the climb and pin the stop with a negative control.
- **Deleting the parent rule when you add the ancestor rule.** They report
  different strengths of evidence. Subsuming one into the other loses the
  distinction in every historical result too.
- **Treating an empty answer as a measurement.** "Nothing affected" from an
  impact tool is a claim about the MAP, not about the tree. Say so in the
  output text, so the next reader is not told a fact when they were given an
  absence.
- **Re-recording instead of fixing.** A fresh recording makes today's
  containers visible and is stale again with the next new directory. The
  scope will always be older than the change being classified; that is the
  invariant, and the rule has to survive it.
- **Assuming a directory scope implies a recursive walk.** It does not, and
  it does not have to: a node that listed `skills/` once and then opened
  `skills/*/SKILL.md` directly depends on new entries under `skills/` just
  as much as one that walked it. The climb is right in both cases.

## Verification

```bash
# 1. THE TWO PROBES, both rules, on the real map. Probe B is the one that
#    used to answer "nothing".
python3 harness/readset.py blast --json --no-tree-scan skills/zz-probe-525/SKILL.md
python3 harness/readset.py blast --json skills/zz-probe-525/SKILL.md
# expect: "files": [] under --no-tree-scan; a non-empty list without it.

# 2. The same thing with a container that really appears and is removed.
#    PASS THE PATH: with no arguments `blast` reads the whole working tree,
#    so on a dirty tree the probe's own contribution is not isolable and a
#    `tail -n 3` shows you the union, not the measurement.
mkdir -p harness/zz_probe_round525 && touch harness/zz_probe_round525/x.py
python3 harness/readset.py blast --no-tree-scan harness/zz_probe_round525/x.py
python3 harness/readset.py blast harness/zz_probe_round525/x.py
rm -rf harness/zz_probe_round525
# expect: "NO recorded node reads or scans any of them" for the first,
#         a list of IMPLICATED files [scan-tree] for the second.

# 3. The pinned tests: the two probes, the stop-the-climb negative control,
#    monotonicity, and the incident replay.
python3 -m pytest -q harness/tests/test_readset.py -k "container or ancestor or 524 or root_is_not"

# 4. The whole suite, because a widening touches every caller.
python3 -m pytest -q harness/tests/test_readset.py
# expect: 48 passed
```

Worked example, with the miss that motivated it and both scored predictions:
`knowledge/round-525-the-container-younger-than-the-scope.md`.

Related: `skills/measured-not-declared-dependencies/` (how to record a read
set in the first place — its step 5, "record DIRECTORIES, not files", is the
advice this skill is the correction to);
`skills/diff-to-check-blast-radius/` (why an impact map is worth having at
all); `skills/matcher-defines-the-population/` (the same disease in a
population chosen by a pattern); `skills/derived-subject-set/` (a literal
enumeration standing in for a derived set);
`skills/red-debt-triage/` (what to do with the red once you can see it).

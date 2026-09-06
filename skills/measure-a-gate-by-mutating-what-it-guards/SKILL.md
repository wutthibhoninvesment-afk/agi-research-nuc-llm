---
name: measure-a-gate-by-mutating-what-it-guards
description: Use when a `--check` / `--verify` verb or a guard test over a committed derived artefact (ledger, census, lockfile, golden file, snapshot, coverage baseline) exits 0 and you need to know WHICH parts of that artefact it can actually see — not reason about it, measure it. Symptoms - a guard was green while the artefact was provably stale; a reviewer asks "does this check cover field X?" and the answer comes from reading the code; a check verb reads one hardcoded path so it can only ever be run against the real file; headline totals printed by a CLI that nothing compares; you are about to widen a guard and want a before/after number. Also use when a guard EXCLUDES a key by name (`ignore=(...)`, `skip`, "another check owns this") - an exclusion is a promise that must be measured at LEAF granularity, not read. The method - perturb exactly one key at a time, point the guard at the mutant, and record SEES / BLIND / CRASH per key, starting every sweep with an unmutated control that must pass, then DESCEND into every excluded key and repeat per leaf. Covers why a no-op mutation reads as a blind gate, why a crash is not a detection, and the one-line fix that makes an unaimable guard measurable.
---

# Measure a gate by mutating what it guards

A guard over a derived artefact is a claim: *if this file stops matching the
tree, I will say so.* The claim is almost never tested. It is read — someone
opens `check_ledger`, sees comparisons, and concludes the gate is fine.

Reading the code gives you a static approximation that goes stale the first
time anyone edits the guard. And it is systematically optimistic, because
what you see is the comparisons that ARE there; what matters is the fields
that no comparison mentions, and absence is exactly what reading is bad at.

**So measure it.** Take the artefact the guard protects, perturb one field,
run the guard, and write down what it said. Repeat per field. The output is
a table — `sees 2 of 8 keys` — that a reviewer can act on and that a later
edit to the guard cannot silently invalidate.

## Trigger conditions

Any one of these:

1. A `--check` / `--verify` / `--audit` verb over a **committed generated
   file** exits 0, and nobody has run it against a deliberately wrong copy.
2. A guard was **green while the artefact was stale** and you have fixed the
   staleness. Before closing, find out what else it cannot see; the same
   guard is about to protect the file you just regenerated.
3. You are **widening a guard** and want a before/after number rather than
   "it also checks totals now".
4. The artefact carries fields a CLI **prints as its headline** (`files: 76`,
   `asserts: 4122`). Ask what compares them; measure rather than guess.
5. A guard **reads one hardcoded path**. That is both a finding and the
   reason nobody has measured it — see step 1.
6. Review of a PR that adds a field to a generated artefact. The new field is
   almost certainly outside every existing guard's predicate.
7. A guard **names an exclusion** — `ignore=("nodes", "costly_nodes")`, or
   a comment saying `# check_census owns declared-but-gone nodes`. Naming an
   exclusion out loud is better than hiding one and is not evidence that the
   named delegate ranges over it. Step 8b.

## Steps

1. **Make the guard aimable, first, as its own change.** If it resolves its
   own path (`load_ledger()`, a module constant, an env-rooted helper), add a
   path argument and nothing else. Two reasons this comes first: without it
   the only way to run the guard against a mutant is to overwrite the real
   artefact, and a repo where another process may commit at any moment makes
   that unacceptable; and "the guard cannot be aimed" is itself the finding
   that explains why the coverage was never measured.

       # before:  findings = check_ledger(load_ledger(), rows)
       # after:   findings = check_ledger(load_ledger(override), rows)

   Where the guard is a test node that resolves through a repo-root env var,
   aim it with a **mirror root**: a temp directory of symlinks to the real
   tree with exactly one real file — the mutant — on the path that matters.

2. **Enumerate the artefact's own top-level keys.** Not the keys you think
   matter. `sorted(json.load(open(path)))` is the population; anything you
   drop from it you are asserting is unimportant, and that assertion belongs
   in the report, not in the loop.

3. **Run the negative control before any mutant.** Copy the artefact
   unchanged, point the guard at the copy, require exit 0. If it fails, the
   guard is not reading your copy — a bad redirect, a dirty tree, a cached
   path — and every BLIND you would collect below is the apparatus, not the
   gate. Report the row UNTESTABLE with the control's output. Do not drop it.

4. **Two mutations per key, because they are different questions.**

       DELETE   remove the key entirely
       CORRUPT  the smallest change its type allows

   A guard reading `declared.get("k", {})` is blind to DELETE and sees
   CORRUPT; one reading `declared["k"]` crashes on DELETE and sees CORRUPT.
   One mutation kind gives you half the table.

5. **Make CORRUPT non-vacuous, and publish what you did.** Dropping the
   alphabetically first member of a mapping is the obvious rule and it is
   wrong: if that member's value is already empty, the mutant is semantically
   identical to the control and the gate is scored BLIND for noticing
   nothing. Prefer a member whose value is non-empty; skip an empty container
   as "no-op, not scored" rather than counting it; and record the choice
   (`dropped member 'used_by_example'`) so a BLIND cell can be audited.

6. **Score three verdicts, not two.** `SEES` (non-zero exit), `BLIND` (exit
   0), `CRASH` (a traceback). A crash is *not* a detection: the guard has no
   comparison for that field, it has a subscript. Scoring it as SEES credits
   the guard with a check it does not have — and the repair is different (add
   the comparison AND stop indexing).

7. **Report the table and the total, then fix with it in hand.** `sees N/M
   keys` per guard, plus which keys are prose (a guard blind to its own
   `_what` string is not thereby defective — say so rather than inflating the
   number).

   **Do not reduce the two mutation kinds to one number.** Step 4 says they
   are different questions; a headline of `SEES in verdicts.values()` puts
   them back together with an OR, and a key the guard notices under CORRUPT
   and misses under DELETE is then published as covered. Score three
   things — `seen` (any kind), `total` (**SEES under every APPLICABLE
   kind**, where a mutation the apparatus declined to make is not
   applicable), and `partial` (the difference) — and make the strict exit
   ask for `total`. On the tree this skill came from, `partial` was 1: a
   residual that rebuilds the live document with *the declared document's
   own optional-field shape* is blind to the DELETION of that shape key and
   sees every corruption of it.

8. **Replace a subset predicate with the total one, not with more of them.**
   Where the guard already computes the document it would write, the total
   comparison is one line: diff the whole document, `ignore=` the keys a more
   readable finding already owns. Keep the readable codes; add a residual
   code for everything else. Do not add an Nth bespoke comparison — that is
   how the gap was built.

8b. **Then descend into every key you just wrote into `ignore=`, and sweep
   its LEAVES.** Step 8's `ignore=` is not a suppression, it is a
   DELEGATION: a promise that a named, more readable check ranges over that
   key. The promise is the same kind of unmeasured claim as the guard you
   started with, and it is granted at the granularity of a top-level key
   while every delegate is written against a PROJECTION of it — a key set, a
   derived set, a coordinate pair. So sweep the excluded key one leaf at a
   time and score each against **every** check in the module, not just the
   named delegate.

   On the tree this skill came from, `_residual` excluded two keys and named
   three delegates. Measured at the leaf:

       mutation (one leaf under the excluded `nodes`)   the guard said
       ---------------------------------------------    --------------
       a pair's `magnitude` TEXT rewritten               ledger agrees
       a pair's `shape` TEXT rewritten                   ledger agrees
       a pair's `independent` flag flipped               ledger agrees
       a pair's `tree_derived` flag flipped              ledger agrees
       a pair's `remedy` rewritten                       ledger agrees
       a whole pair DELETED from a surviving node        ledger agrees
       a pair DUPLICATED into a surviving node           ledger agrees
       a pair's `magnitude_line` moved +7                MOVED  (seen)

   **Seven of eight.** The delegation held for one leaf of eleven, because
   `check_census` diffs the KEYS of `nodes`, `check_costly` compares a
   derived set against the TREE so the declared key never participates, and
   the coordinate check reaches two fields and only for pairs whose text it
   can still match. Each delegate was doing exactly what its own docstring
   said; none of them ranged over the key it had been credited with.

8c. **Add the declared-vs-declared check while you are in there.** Every
   check in step 8's family compares the document to the TREE, so all of
   them go quiet on a document that is not a faithful record of any tree — a
   hand edit, a half-applied patch, a generator interrupted between writing
   the rows and writing the summary. If the artefact carries summaries
   derived from its own rows (`totals`, a costly/failing/selected subset),
   re-derive them from the rows and compare, with no tree at all. On the
   tree above this caught four of the seven blind mutations by itself, is
   the cheapest check in the module, and is the only one that still works on
   an artefact whose tree is gone.

9. **Re-run the sweep after the fix and publish both numbers.** A gate repair
   with no before/after is indistinguishable from a gate repair that missed.

## Pitfalls

* **A no-op mutation is indistinguishable from a blind gate.** Step 5. This
  is the single most likely way to publish a wrong table.
* **A `.get()` with a default converts a DELETE into silence.** So a guard
  written defensively scores worse than a careless one, and correctly.
* **Excluding prose keys from the sweep to make the number look better.**
  Measure them, label them, and let the reader discount them.
* **The fixture that is not what its name says.** In a test-node gate, a
  fixture called `live` may return a JOIN onto the very artefact under test.
  Read the fixture's body; a name is not evidence.
* **Total-comparing a document whose generator has an expensive optional
  mode.** If `--history` fields are absent unless a slow flag is passed,
  rebuild with the *same* shape as the document you were given, or the total
  gate reports a spurious finding on every run and gets deleted.
* **Mutating the real artefact.** Always a copy, always in a temp directory.
  A third-party commit landing mid-sweep will capture whatever is on disk.
* **The sweep is only valid on a QUIESCENT tree.** A guard that compares
  the artefact against a live scan will go red because *you* edited the
  tree while the sweep ran — and the row is then voided by its own control
  and reads as a broken redirect. Land your edits, regenerate every
  artefact that derives from what you touched, and sweep after. If your
  test files are in the corpus the artefact measures, adding the tests for
  the repair invalidates the artefact the repair is measured against.
* **A test-node guard cannot reach the CRASH class by default.** `CRASH` is
  usually detected by looking for the interpreter's traceback header, and a
  test runner prints its own traceback style instead — so a node that
  RAISED scores as SEES, which is the one verdict step 6 says it must not
  get. Run the node with the runner's native-traceback flag
  (`pytest --tb=native`) or say in the report that the class is unreachable
  for that gate kind.
* **The instrument gets imported by the thing it measures.** Once a guard
  adopts your total-diff helper (step 8), the module doing the grading is
  inside the module being graded. That is safe only while the shared
  function is PURE — if it reads the instrument's root, its ledger
  directory or an environment variable the sweep sets, a guard can be
  handed the mutant by its own grader. Pin it: list the attributes a
  measured module may touch, and assert the shared function loads no
  module-level binding whose value came from the filesystem or the
  environment.
* **Scoring an excluded key as covered because something was named.** An
  exclusion is only as total as the check it delegates to, and the two are
  written at different granularities: you exclude a KEY, the delegate ranges
  over a PROJECTION. Enumerate the leaves from the artefact itself rather
  than typing a field list — a hand-written list is one more thing that goes
  stale, and the field it misses will be the one somebody adds next, which
  is how the gap gets built a second time.
* **Believing a gate table stays true.** It is a measurement of a specific
  commit. Wire the sweep, or at least the "every artefact has a gate entry"
  half of it, into the suite.

## Relation to `gate-must-range-over-what-drifts`

That skill is the diagnosis — *why* a green guard over a stale artefact is
the normal case, and how to reason about a predicate's range. This one is the
instrument: how to get a number instead of an argument, and what makes the
number wrong. Use them together — reason first about what drifts, then
measure what the guard sees.

## Verification

Run this against any repo with a generated artefact and its guard. It builds
a two-key ledger and a guard that reads one of them, and asserts the sweep
reports exactly one BLIND key and voids a row whose control fails.

```bash
python3 - <<'EOF'
import json, os, subprocess, sys, tempfile
tmp = tempfile.mkdtemp()
led = os.path.join(tmp, "ledger.json")
json.dump({"watched": 1, "ignored": 1}, open(led, "w"))
gate = os.path.join(tmp, "gate.py")
open(gate, "w").write(
    "import json,sys\n"
    "d=json.load(open(sys.argv[1]))\n"
    "sys.exit(0 if d.get('watched', 1)==1 else 1)\n")

def run(obj):
    p = os.path.join(tmp, "m.json")
    json.dump(obj, open(p, "w"))
    return subprocess.run([sys.executable, gate, p]).returncode

base = json.load(open(led))
assert run(base) == 0, "CONTROL FAILED -- the sweep would be meaningless"
table = {}
for key in sorted(base):
    gone = dict(base); del gone[key]
    bad = dict(base); bad[key] = base[key] + 1
    table[key] = {"delete": "SEES" if run(gone) else "BLIND",
                  "corrupt": "SEES" if run(bad) else "BLIND"}
for key, v in sorted(table.items()):
    print(key, v)
seen = sum(any(k == "SEES" for k in v.values()) for v in table.values())
total = sum(all(k == "SEES" for k in v.values()) for v in table.values())
print("sees %d/%d key(s), total over %d, partial %d"
      % (seen, len(table), total, seen - total))
assert table["watched"] == {"delete": "BLIND", "corrupt": "SEES"}, table
assert (seen, total) == (1, 0), (seen, total)
EOF
```

Expected output:

```
ignored {'delete': 'BLIND', 'corrupt': 'BLIND'}
watched {'delete': 'BLIND', 'corrupt': 'SEES'}
sees 1/2 key(s), total over 0, partial 1
```

**Read that carefully — it is the point of step 7.** The guard is
`d.get('watched', 1) == 1`, which every reviewer reads as "it checks
`watched`". It half does: the default swallows the DELETE, so the guard
exits 0 on an artefact that has lost the field entirely. The OR headline calls the key covered (`sees 1/2`); the
per-kind one calls it what it is (`total over 0, partial 1`). A run that
prints `total over N` for all N keys means the guard really is total over
that artefact — rare enough on a first measurement that you should re-check
the control before believing it.

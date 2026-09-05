---
name: measure-a-gate-by-mutating-what-it-guards
description: Use when a `--check` / `--verify` verb or a guard test over a committed derived artefact (ledger, census, lockfile, golden file, snapshot, coverage baseline) exits 0 and you need to know WHICH parts of that artefact it can actually see — not reason about it, measure it. Symptoms - a guard was green while the artefact was provably stale; a reviewer asks "does this check cover field X?" and the answer comes from reading the code; a check verb reads one hardcoded path so it can only ever be run against the real file; headline totals printed by a CLI that nothing compares; you are about to widen a guard and want a before/after number. The method - perturb exactly one top-level key at a time, point the guard at the mutant, and record SEES / BLIND / CRASH per key, starting every sweep with an unmutated control that must pass. Covers why a no-op mutation reads as a blind gate, why a crash is not a detection, and the one-line fix that makes an unaimable guard measurable.
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

8. **Replace a subset predicate with the total one, not with more of them.**
   Where the guard already computes the document it would write, the total
   comparison is one line: diff the whole document, `ignore=` the keys a more
   readable finding already owns. Keep the readable codes; add a residual
   code for everything else. Do not add an Nth bespoke comparison — that is
   how the gap was built.

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
    "sys.exit(0 if d.get('watched')==1 else 1)\n")

def run(obj):
    p = os.path.join(tmp, "m.json")
    json.dump(obj, open(p, "w"))
    return subprocess.run([sys.executable, gate, p]).returncode

base = json.load(open(led))
assert run(base) == 0, "CONTROL FAILED -- the sweep would be meaningless"
table = {}
for key in sorted(base):
    verdicts = set()
    gone = dict(base); del gone[key]
    verdicts.add("SEES" if run(gone) else "BLIND")
    bad = dict(base); bad[key] = base[key] + 1
    verdicts.add("SEES" if run(bad) else "BLIND")
    table[key] = "SEES" if "SEES" in verdicts else "BLIND"
print(table)
assert table == {"watched": "SEES", "ignored": "BLIND"}, table
print("sees %d/%d key(s)" % (sum(v == "SEES" for v in table.values()),
                             len(table)))
EOF
```

Expected output:

```
{'ignored': 'BLIND', 'watched': 'SEES'}
sees 1/2 key(s)
```

A run that prints `sees 2/2` means the guard is total over that artefact —
which is the goal, and is rare enough on a first measurement that you should
re-check the control before believing it.

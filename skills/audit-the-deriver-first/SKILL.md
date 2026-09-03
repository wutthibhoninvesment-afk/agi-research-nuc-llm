---
name: audit-the-deriver-first
description: Use when you are about to check STORED claims against a freshly DERIVED ground truth -- cached fields, provenance pins, denormalised columns, "expected" snapshots, a registry of file:line references -- and especially when the first run reports failures in a class you did not expect. Symptoms: a checker's first output flags a record you can verify by eye is correct; a derived value rendered with a falsy-or (`x or "-"`, `n or 0`) so "absent" and "zero" print the same; a derivation returning a sentinel for part of its domain; two runs of it on unchanged input disagreeing. Covers measuring the deriver's sentinel rate by class before trusting any verdict, proving a deriver fix is information-only with a before/after A/B, pinning determinism across processes, and replaying history under BOTH the deriver of the day and today's. NOT for a verdict that is an unresolved disjunction (disjunctive-verdict-needs-resolving), NOT for whether a ratio is a property of its subject at all (coverage-keyed-by-witness).
---

# An audit is two claims, and one of them is yours

Every "does the record match reality?" check is really two assertions: the
record says X, and *my derivation of reality says Y*. When they disagree the
report names the record. The derivation is never in the dock, because it is
the thing doing the judging.

That is exactly backwards when the derivation cannot express the claim.
A deriver that returns a sentinel — `None`, `0`, `""`, `"unknown"` — for
part of its domain does not report "I don't know"; it reports a value, the
comparison fails, and the audit says the record is wrong. The record was
right. **The first output of a new checker is evidence about the checker.**

**Round 481 of this program, the case that produced this skill.** A registry
of 110 provenance pins of the form `"<file>:<line>"` had never been verified.
The new checker's first run reported three stale pins. One of them named
line 20 of a test file, and line 20 of that file was, plainly, the import it
claimed. The graph disagreed because it recorded that edge at **line 0**: the
three `ast` passes that built 69 % of its edges (721 of 1043) passed a
literal `0` for the line number, and the one renderer was written
`lineno or "-"`, which spells *line zero* and *no line is claimed*
identically. 80 pins in that registry said `"<file>:-"` and a previous round
had read them as a deliberate convention. They were the symptom.

Had that one hand-written pin not existed, the checker would have shipped
with a 49-pin blind spot baked into its verdicts, and every one of them
would have been reported as the registry's fault.

## When to use (triggers)

- You are writing or running a check that compares a **stored** value against
  a **computed** one: cache vs source, snapshot vs live, registry vs graph,
  documented line number vs actual line number, denormalised count vs query.
- A checker's first run reports failures and one of them looks wrong to you
  on inspection. Stop and audit the deriver before widening or explaining the
  verdict.
- You see a falsy-or anywhere near the derived side: `x or "-"`, `n or 0`,
  `val or "unknown"`, `len(xs) or "n/a"`. In every one of these, a legitimate
  falsy result and a missing result are the same output.
- Your deriver walks a `set`, a `dict` built from a set, or anything else
  whose iteration order is not part of its contract, and picks a winner among
  ties.
- You are about to replay history to ask "how long has this been wrong?" —
  the deriver of the day may have had its own defect, and the answer differs.

**Not this skill** when the verdict names several causes and prescribes one
remedy (`disjunctive-verdict-needs-resolving`), or when the question is
whether the number you are about to publish is a property of its subject at
all (`coverage-keyed-by-witness`).

## Steps

1. **Write down the claim's domain and the deriver's output domain, as two
   sets.** "The pin claims a line in a file"; "the deriver returns a line, or
   0, or None." If they differ, the difference is your bug budget.

2. **Count the deriver's sentinel outputs over the real corpus, broken down
   by class.** Not "does it work on an example" — a rate, per kind:

   ```
   edges by kind:      {'path': 156, 'dir': 209, 'import': 614, 'join': 61}
   edges with no line: {'import': 614, 'join': 61, 'dir': 30, 'path': 16}
   ```

   A class at 100 % sentinel is not a coverage gap, it is a code path that
   never had the value. Do this before you look at a single subject-side
   failure.

3. **Fix the deriver first, and prove the fix is information-only.** Load the
   old and new derivers in one process, run both over the same corpus, and
   assert that everything except the added information is identical:

   ```
   closure identical: True (322 nodes)
   edge target sets identical: True
   edge kinds identical: True
   lineno-0 edges: old 721  new 0  of 1043 total
   ```

   Without that A/B you cannot tell a fix from a change, and every downstream
   verdict the deriver feeds is now suspect in the other direction.

4. **Pin determinism across processes.** Run the deriver in two or three
   subprocesses with different `PYTHONHASHSEED` and compare the full output,
   not a summary. A tie broken by set-iteration order is invisible in one
   process and fatal to any audit, because "re-derive the stored value and
   compare" presumes the derivation has one answer. Three runs of one such
   function on an unchanged tree named three different sources.

5. **Only now re-run the audit, and check that at least one verdict moved.**
   If the fix changed no verdict, either the sentinel class did not overlap
   the claims (say so) or the audit is not reading the field you fixed.

6. **When replaying history, run BOTH derivers** — the one each commit
   shipped, and today's — and report the two series side by side. The first
   answers *what was knowable then*, the second *what was true*. Where they
   differ, the difference is the instrument, and that is a finding about your
   own tooling, not about the past.

7. **Report the deriver's failure as prominently as the subject's.** The
   round that finds it is the only round that can; by the next one it is a
   number in a table nobody re-derives.

## Pitfalls

- **The falsy-or is the whole bug, and it reads as defensive coding.**
  `x or "-"` looks like careful rendering. It is a lossy union of two states.
  Replace it with an explicit function whose name says what `-` means, and
  add a test that the sentinel state cannot occur in the live corpus — so the
  fallback can never silently come back.
- **A sentinel rate of 100 % in one class hides in an aggregate.** 69 % of
  edges having no line sounds like a partial feature; `import: 614 of 614`
  says a code path was never wired. Always break the rate down by the
  deriver's own internal classes.
- **"It agrees with the record" is not evidence the deriver works.** A
  deriver and a record produced by the *same broken deriver* agree perfectly.
  Round 481's 80 `":-"` pins matched a graph that could not produce a line.
- **Re-deriving requires determinism, and nobody checks determinism until a
  re-derivation exists.** The function had been non-deterministic for 66
  rounds, feeding a registry field and two diagnostic messages, and nothing
  noticed because nothing had ever computed it twice.
- **Fixing the deriver can widen the audit's failure set enormously.** Once
  it can express the claim, every record becomes checkable. Measure the
  maintenance cost of enforcing the new claims (how often does the derived
  value move, historically?) before turning them all on — a gate that goes
  red half the time gets ignored and then uninstalled.
- **Do not let the deriver auto-repair a record whose repair is editorial.**
  Moving a pin to another line of the same file is clerical. Moving it to a
  *different file* changes what the record claims; print it and make a human
  decide.

## Verification

Run against this repository, where every number above was measured.

```bash
# 1. The sentinel rate, by class. Post-fix this must be empty.
python3 - <<'EOF'
import importlib.util, os, collections
spec = importlib.util.spec_from_file_location("wa", "harness/wiring_audit.py")
wa = importlib.util.module_from_spec(spec); spec.loader.exec_module(wa)
g = wa.Graph(os.path.abspath(".")); g.closure()
tot  = collections.Counter(v[1] for d in g.edges.values() for v in d.values())
zero = collections.Counter(v[1] for d in g.edges.values()
                           for v in d.values() if not v[0])
print("by kind:", dict(tot)); print("no line:", dict(zero))
EOF
# -> by kind: {'path': 156, 'dashm': 3, 'dir': 209, 'import': 614, 'join': 61}
# -> no line: {}

# 2. The audit the fixed deriver makes possible, and its verdict classes.
python3 harness/viapin.py audit
# -> via-pins: 111 pin(s), 31 held, 0 drifted, 0 lost, 0 absent, 80 unpinned

# 3. Determinism across processes, and the sentinel-state pin, both as tests.
python3 -m pytest -q harness/tests/test_wiring_audit.py -k EdgeLines
# -> 6 passed

# 4. The audit's own suite, including the mutation-found gap in step 5's sense
#    (a class the fixtures never exercised).
python3 -m pytest -q harness/tests/test_viapin.py
# -> 21 passed
```

The history replay in step 6 is
`state/harness/round-481/via-pin-history.json` (deriver of the day) against
`via-pin-history-today.json` (today's); they differ at exactly two commits,
and at both of them the older deriver called a correct record wrong.

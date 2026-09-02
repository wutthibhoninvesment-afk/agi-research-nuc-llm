---
name: residual-audited-both-ways
description: Audit an instrument's declared residual — its published count of what the walk could not reach — in BOTH directions before quoting it — every entry must be a real failure of the walk, and a thing excluded for a reason must be counted separately from a thing that defeated you. Trigger when a tool, census, harvester, scanner or coverage report publishes an unreached/unresolved/skipped/unknown count, when a next-step asks you to "narrow the residual", or when you are about to quote such a number as a blind spot.
---

# A residual is a claim, and it is as falsifiable as the corpus

An instrument that returns a corpus without saying what it could not reach
reads as exhaustive, so a good instrument publishes a residual. But the
residual is a **claim about the instrument**, and almost nobody tests it —
the corpus gets cross-checked and the blind-spot count is quoted forward
verbatim for rounds.

An **overstated** blind spot is not the safe error. It hides a precision bug
behind a number that reads as humility, and it sends the next worker to
"narrow the residual" by adding recall they did not need.

## When this triggers

* A tool prints `unresolved: N`, `could not reach`, `unknown`, `skipped`,
  `unparsed`, `not covered`, `n/a`.
* A carried next-step says *"the residual is N and nothing narrows it"*.
* You are about to widen a matcher/folder to close a class you have only
  seen summarised.
* A single predicate is used for two different questions about the same
  node (see step 2 — this is the generator of the bug).

## Steps

1. **Re-derive the residual before touching it, item by item, and classify
   it by SHAPE.** Not by re-running the tool's own summary — by writing the
   twenty lines that dump one row per residual entry with a file:line and a
   node kind. Round 462 did this and found the published breakdown summed to
   191 against its own stated total of 130, and that the largest class was
   half the size the prose said.

   ```sh
   # the shape that works: reproduce the tool's own scan, but emit rows
   python3 - <<'EOF'
   import collections
   kinds, ex = collections.Counter(), collections.defaultdict(list)
   for site in scan():                 # the tool's own walk
       if resolved(site): continue
       k = classify(site)              # node type, callee, receiver
       kinds[k] += 1
       if len(ex[k]) < 4: ex[k].append("%s:%d" % (site.file, site.line))
   for k, n in kinds.most_common(): print(n, k, ex[k])
   EOF
   ```

2. **Ask, of each class: is this a source position at all?** This is the
   precision direction and it is the one that gets skipped. For each class,
   name the thing the instrument thought it was looking at and check that
   the code agrees.

   The generator of the bug is a **predicate serving two questions**. In
   round 462 one tuple answered both *"does this call execute?"* and *"is
   arg0 a source string?"*; `exec_stmt` executes but takes a parsed
   statement, and `subprocess.run` is not an interpreter. 51 of 131 residual
   entries — 39% of the class — were never blind spots. Split the predicate;
   do not add an exemption list.

3. **Derive an exclusion from the artefact, never from a denylist.** The
   receiver test that removed `subprocess.run` is *"is this receiver a name
   this file bound with an `import` statement?"* — a fact about the module.
   A hand-written `{"subprocess", "os", "sp"}` would have been a guess about
   a corpus and would silently rot on the next file. Note the near miss:
   `ImportFrom` must be excluded, because `from x import Interpreter` binds
   a class and a class is exactly what a legitimate receiver may be.

4. **Give exclusions their own counter and print it beside the residual.**
   `excluded: 45 module calls + 22 statement-node args (not residual)`. A
   call dropped for a stated reason and a call that defeated the walk are
   different facts; sharing a counter is how the overstatement happened.
   The arithmetic must reconcile against the old number: `918 + 45 + 22 =
   985`, and that reconciliation belongs in a test.

5. **Then, and only then, do the recall half.** Ask whether the residual
   classes that remain are *decidable*. Where they are, note whether the
   right answer is ONE value or MANY — a folder typed `str | None` reports
   "several answers" as "no answer", which is the same overstatement in a
   different place. `val("A" if C else "B")` is two programs, not an
   unknown.

6. **Bound the widening and count the bound.** Multi-valued folding
   multiplies: `A + B` with five bindings each is 25 results. Cap it
   (`MAX_FOLD`), and make the cap a counter, or the instrument reports a
   corpus larger than the system runs.

7. **Prove the fix touched only the self-report.** Diff the OLD corpus
   against the NEW one as sets. The precision fix must lose **zero** items;
   if it loses any, the exclusion was too wide and you have deleted real
   evidence.

   ```sh
   git show <base>:path/to/tool.py > /tmp/old.py   # load both, compare sets
   # assert old_keys - new_keys == set()
   ```

8. **Re-run the headline the corpus feeds.** A 15% larger corpus that moves
   the published champion is a different finding from one that does not.
   Say which happened.

## Pitfalls

* **Quoting a predecessor's residual as your baseline.** Measure it on the
  tree first. Round 462's baseline re-derivation refuted the carried class
  breakdown before any code changed — the sixth consecutive round in this
  program where re-deriving a carried number changed its answer.
* **Closing the residual to zero.** Some classes are genuinely undecidable
  statically (`"".join(parts)` over a loop-built list; `open(p).read()` over
  a runtime `listdir`). Leaving them counted is the instrument working. A
  test should assert the residual counters stay **positive**.
* **Fixing recall first.** Widening the folder over false-positive classes
  makes the tool try to resolve nodes that are not source at all — new
  failure modes, no new evidence.
* **Assuming a false residual is harmless because it is conservative.** It
  is only harmless if it never became an item in the corpus. Check that
  separately (step 7); do not assume it.
* **Deriving the exclusion from the symptom.** `receiver == "subprocess"`
  passes the same test as `receiver in imported_modules(tree)` and is wrong
  for the next file.

## Verification

Run from the repo root. Both commands must exit 0.

```sh
# 1. the residual's own tests: exclusions counted, reconciliation exact,
#    corpus a strict superset, residual positive and smaller
cd languages/whence && python3 -m pytest -c pytest.ini -q \
    tests/test_testcorpus_census.py

# 2. the instrument prints its residual and its exclusions separately,
#    above the corpus, and the arithmetic reconciles
cd languages/whence && python3 depthcensus.py --tests --harvest-only
```

Expected from (2): a `residual:` line and an `excluded:` line, with
`calls + module_calls + stmt_node_args == 985`.

---
name: instrument-assumes-its-home-corpus
description: Use when a checker, linter, static analysis, coverage tool, migration scanner or audit script is about to be pointed at a corpus it was NOT written against - a second package, a sibling repo, another language's tests, a vendored tree, a newly onboarded service - and its verdict there is about to be believed. Symptoms; a scan reporting zero findings on a tree nobody has ever scanned; "the query is mechanical, just run it over the other directory"; a rule set whose thresholds, helper names, file layout or AST node type were all true by construction where it was authored; a clean result that arrives suspiciously fast; output that is a list of findings with no count of what was examined. The move is to compare DENOMINATORS between the home corpus and the new one before reading a single finding, then make the empty population a distinct red verdict rather than a pass. NOT count-carries-its-noun-and-denominator (the reporting surface), NOT zero-rate-needs-a-distance (corpus demand versus a threshold).
---

# An instrument is calibrated to the tree it was born in

A checker is written inside one corpus, against one set of examples, and it
works. Every structural assumption it made along the way was *true by
construction* there, so none of them was ever written down — not in a
comment, not in a flag, not in a test. They are invisible from inside the
home tree because nothing there can violate them.

Point it at a second corpus and those assumptions do not raise. They
**shrink the population**, silently, and the tool reports the smaller
population's verdict in the same words it uses for the real one.

```
The iron law:  a checker's first result on a NEW corpus is a measurement
               of the CHECKER. Read its denominator before its findings,
               and never read "0 findings" until you know it read anything.
```

The reason this is worth a skill rather than a habit is the failure's
shape: **it is silent, it is fast, and it looks like good news.** A tool
that crashes on a new tree gets fixed in ten minutes. A tool that reports
`0 findings -- clean` gets *quoted*, and the quote outlives everyone's
memory of which directory it was run against.

## When to use — trigger conditions

Trigger on any of these:

* someone says a cross-tree run is "mechanical", "just point it at", "a
  one-liner" — the word means *nobody has looked at the new corpus*;
* an analysis, linter or codemod is being run against a second package,
  sibling repo, vendored dependency, monorepo neighbour or newly onboarded
  service for the first time;
* a scan of a large, old, never-scanned directory comes back clean;
* the tool prints findings and no denominator (no file count, no node
  count, no "examined N");
* a rule set names concrete identifiers — helper functions, fixture names,
  config keys, directory names — that were chosen in one repo;
* a static analysis keys on one AST node type, one decorator, one base
  class, one file-name pattern;
* a coverage or migration number is about to be compared *across* trees.

**When NOT to use.** The tool has already produced findings on the new
corpus and the question is whether a *specific* finding is real (that is a
verification problem). Or the tool is running on the corpus it was written
for, and the question is whether its zero means the class is absent — that
is `zero-rate-needs-a-distance`. Or the denominator exists and is simply
printed on the wrong line — `count-carries-its-noun-and-denominator`.

## Steps

1. **Run it on its HOME corpus first, and write down the denominator.**
   Not the findings — the population: files opened, units examined, and the
   count of each *kind* of unit. This is the control, and you need it
   before you have a reason to want one. Checkable outcome: you have two
   numbers for the home tree, `N_files` and `N_units`, obtained from the
   tool itself and not from `ls`.

2. **Run it on the new corpus and compare the DENOMINATORS, not the
   findings.** A denominator that is zero, or that is an order of magnitude
   off the ratio of tree sizes, is the result. Stop and diagnose it; do not
   proceed to read findings. Checkable outcome: `N_units_new / N_files_new`
   is within a factor of ~3 of the home ratio, or you have a written reason
   why not.

3. **When the denominator is wrong, enumerate the assumptions in the order
   the tool applies them** — discovery, then unit selection, then
   vocabulary — because an early one masks every later one and you will
   otherwise fix one and declare victory:
   - **discovery**: how does it find inputs? `os.listdir` (not recursive),
     one glob, one extension, a hard-coded `tests/`, `git ls-files`?
   - **unit**: what counts as one thing to check? One AST node type? One
     regex? A `unittest` suite has *zero* `ast.Assert` nodes; a `pytest`
     suite has zero `self.assert*` calls. A Rails app has no `import`
     statements. A monorepo package has no top-level `setup.py`.
   - **vocabulary**: does the rule name concrete identifiers from home?
     A list of helper functions (`load_ledger`, `read_config`), a fixture
     name, a base class, an env var.
   Checkable outcome: one line per layer saying what it assumed and whether
   the new corpus satisfies it — including the layers that turned out fine.

4. **Fix them separately and re-measure after each.** They are independent
   defects that happen to produce one symptom, and their fixes have
   different blast radii. Checkable outcome: a table with a row per fix and
   the denominator after it, so a fix that moved nothing is visible as
   such.

5. **Make the empty population its own verdict, in the output text.**
   "0 findings" and "0 findings because I read nothing" must not render the
   same. Print the population on every run — including successful ones —
   and say `EMPTY POPULATION` when it is zero. State which side the zero is
   a fact about: the directory (no inputs found) or the analysis (inputs
   found, no readable units). Checkable outcome: two runs, one on an empty
   directory and one on a directory of inputs with no readable units,
   produce *different* text.

6. **Gate on the population, not on the findings.** Add `--strict` (or the
   equivalent) that exits non-zero when the population is empty. Findings
   are for a human to judge; an empty population is a broken run, and a
   broken run that exits 0 is the failure that looks like a pass.
   Checkable outcome: a test asserts exit 1 on an empty directory and
   exit 0 on the home corpus.

7. **Widen the instrument at the level of the CONCEPT, not the instance.**
   If the fix is "also accept `self.assertEqual`", ask what the concept is
   ("an assertion relating two expressions") and enumerate its forms.
   Adding the one form you tripped over leaves the next corpus in the same
   place. Checkable outcome: the widening ships with a named list, and the
   list has more entries than the number of instances you observed.

8. **Price the widening against a false-positive control before shipping
   it.** A widened predicate over a bigger population finds new things and
   some of them are wrong. Run the widened tool with each new guard
   disabled and record both counts. Checkable outcome: an off/on table for
   every guard, in the code, with the real numbers in it.

9. **Re-derive every corpus-derived artefact AFTER the last edit.** If the
   new corpus is *your own tree* and the tool's fixtures are generated from
   it, adding tests invalidates them mid-run. Checkable outcome: the
   freshness check runs last, and passes.

## Pitfalls

* **Reading findings before denominators.** The whole failure. Findings are
  interesting and denominators are boring, so the eye goes to the wrong
  one. Force the order by printing the population *first* in the report.
* **Fixing the discovery layer and stopping.** Making the walk recursive
  turns "0 files" into "17 files, 0 units", which is still zero and still
  looks clean. Each layer must be re-measured on its own.
* **Assuming a shared organisation implies a shared idiom.** Two test
  suites in one repository, written by the same authors, one directory
  apart, can be 100% `pytest` bare `assert` and 100% `unittest` method
  calls. Same repo is not same corpus.
* **Believing the tool's own docstring about its scope.** It was written in
  the home tree too, and describes the concept ("every assertion") while
  the code implements the instance (`ast.Assert`).
* **Dropping what the widened rule cannot resolve.** Static analysis over a
  new corpus hits expressions it cannot follow. Dropping them is silent
  under-reporting and it preferentially drops the *unfamiliar* — which is
  the whole new corpus. Publish them with an `unresolved` tag and let a
  reader judge.
* **Letting the widening swallow a distinction the original made.** "Reads
  a file from disk" is not "reads the declared document": a test that opens
  the tree's own *source* is performing a live measurement, and calling it
  self-referential inverts the tool's verdict. Ask what each new match
  actually is, on real examples, before shipping the widening.
* **Counting a self-created fixture as corpus data.** A test that writes a
  file and reads it back round-trips its *own* data. Guard on it, and
  measure what the guard is worth — it is usually not the dominant term,
  and if you do not measure you will believe it was.
* **Pinning the new denominator as an equality.** Live corpora grow. Pin a
  floor; pin the *zero* you are protecting against, not today's count.
* **Treating the empty population as a coverage gap in the corpus.** The
  report says the other tree is clean. It is a statement about your tool.

## Verification

Run these against the instrument you just ported. Every one is cheap.

```bash
# 1. The home denominator (the control) and the new one, side by side.
<tool> --report <home-corpus>   | grep -i 'population\|examined\|files'
<tool> --report <new-corpus>    | grep -i 'population\|examined\|files'

# 2. The empty-population verdict must be its own text, not the clean one.
mkdir -p /tmp/empty-corpus && <tool> --report /tmp/empty-corpus | grep -i 'EMPTY POPULATION'

# 3. ...and it must be RED, while the home corpus stays green.
<tool> --report /tmp/empty-corpus --strict ; echo "empty exit=$?   # want 1"
<tool> --report <home-corpus>    --strict ; echo "home  exit=$?   # want 0"

# 4. The unit assumption, measured directly on both corpora. Substitute
#    your own unit; this is the AST-node-type case.
python3 - <<'PY'
import ast, os, sys
for root in sys.argv[1:]:
    bare = meth = 0
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        for n in names:
            if not n.endswith(".py"):
                continue
            t = ast.parse(open(os.path.join(base, n), encoding="utf-8").read())
            for x in ast.walk(t):
                bare += isinstance(x, ast.Assert)
                meth += (isinstance(x, ast.Call)
                         and isinstance(x.func, ast.Attribute)
                         and x.func.attr.startswith("assert"))
    print("%-40s bare=%-6d method=%-6d" % (root, bare, meth))
PY

# 5. The false-positive control for every guard the widening added:
#    run with the guard disabled and record both numbers.
```

**Acceptance criteria.**
1. The report prints a population on every run, findings or not.
2. An empty directory and a unit-less directory produce different text,
   and neither says what a clean corpus says.
3. `--strict` exits 1 on an empty population and 0 on the home corpus, and
   a test pins both.
4. Every layer (discovery / unit / vocabulary) has a written verdict for
   the new corpus, including the ones that were fine.
5. Every guard added by the widening has an off/on count recorded next to
   it in the code.
6. The new denominators are pinned as FLOORS, and the thing pinned is the
   zero, not today's count.

## Related

* `count-carries-its-noun-and-denominator` — the reporting surface. This
  skill is about the population being wrong; that one is about a correct
  population never reaching the reader.
* `absence-retested-on-the-raw-input` — how to WORD a negative once you
  know the filter produced it.
* `zero-rate-needs-a-distance` — a zero on the corpus the tool was built
  for.
* `second-spelling-evades-the-census` — one corpus, several syntaxes for
  one capability. The unit layer of step 3 is its cross-corpus cousin.
* `matcher-defines-the-population` — a rate whose denominator a pattern
  chose.

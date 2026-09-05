---
name: diff-to-check-blast-radius
description: Use when a change in one directory keeps breaking a check that lives in another and the author never sees it — CI, a nightly, or a sibling team finds it a day later. Symptoms: a test's docstring records the same "X added a file, Y found it later" story two or more times; a registry classifies checks by whose work can break them but only in PROSE, so nothing can query it; each fix is re-pinning a constant and rewriting the story. The technique is to MEASURE each check's subject set by recording what it reads (sys.addaudithook, strace, an fs shim) and, crucially, what DIRECTORIES it lists — a read set names only files that already exist, so it is blind to the ADDED file, which is the majority case. Then map the working-tree diff (including untracked paths) onto those sets and print the shortlist to run. NOT for a check nothing ever invokes (unrun-checker-latency), NOT for a hand-written list of members (derived-subject-set): here the check runs on a schedule and only its AUDIENCE is wrong.
---

# A read set cannot name the file you just added

A check breaks, and the person who broke it is not the person who runs it.
This is a structural property of any repo where suites are split by
directory and run by owner: `tests/a/` runs when `a/` changes, and the node
inside it that walks `b/` is invisible to everyone who works in `b/`.

The instinct is to move the runner earlier — pre-commit, pre-push, a faster
CI lane. That helps with *scheduling* latency and does nothing about this,
because the author cannot run a suite they do not know contains a node about
their file. The missing thing is not a faster runner. It is an **index from
paths to the checks that read them**, and it has to be derived, because
prose ages and nobody can query it.

## Trigger conditions

- The same story appears twice or more in a test's docstring or a
  registry's `reason`: *"round/PR N added a file; round/PR N+k found the
  red; re-pinned with the reason."* Two occurrences is a pattern; the
  third is proof nobody built the instrument.
- A check is owned by team/track A, and the last three times it went red
  the commit was from B, C and D.
- You have a registry that classifies checks by blast radius in ENGLISH
  ("this node's subject is the other tree") and no code reads the
  classification.
- The remediation each time is to bump a pinned constant (a count, a
  digest, a file list) and rewrite the paragraph explaining why.
- A post-merge/nightly/scheduled job is the only thing that runs a suite,
  so by construction its findings arrive after the author has moved on.
- Someone proposes "just run everything on every change" on a machine where
  everything takes 18 minutes.

## Steps

1. **Confirm the shape before building anything.** Reproduce the red from
   the commit that opened it, solo, with no other load. If it reproduces,
   it is a real dependence and this skill applies. If it does not, you have
   a flaky/contended check and this is the wrong tool — instrument the
   runner instead.

2. **Pick the observation point.** You want the files a check touches,
   attributed to the check. In CPython, `sys.addaudithook` and the
   `open` / `os.listdir` / `os.scandir` / `import` events are enough and
   need no dependency. Elsewhere: `strace -f -e trace=openat,getdents64`,
   `fs_usage`, an `LD_PRELOAD` shim, or the build system's own dependency
   log. Attribute by wrapping the runner's per-test lifecycle hooks, not by
   parsing output.

3. **Record TWO sets, not one.** This is the step people skip and it is the
   whole technique:
   - `files` — paths opened for READING or imported.
   - `scans` — directories LISTED.

   A read set answers *"which check depends on a file that exists"*. The
   change that actually breaks a foreign check is usually an **addition**,
   and an added file was never read by anything, so no read set can ever
   name it. The directory the check listed is the only recorded evidence
   that the check *would* have read the new file. Test this explicitly with
   a filename that does not exist — if your instrument returns nothing for
   `<scanned-dir>/does_not_exist.py`, it will miss the majority case.

4. **Exclude writes.** A check that WRITES a file does not depend on it.
   Count the write and every check that touches a log/report directory
   becomes a reader of it, and the query implicates everything. Branch on
   the open mode (`w`/`a`/`x`/`+`, `O_WRONLY|O_RDWR|O_CREAT`).

5. **Filter to the repo, and reject non-paths.** Resolve to
   repo-relative; drop `__pycache__`, virtualenvs, `site-packages`,
   `node_modules`, `.git`. Then drop anything containing `<` or `>`:
   CPython's `SyntaxError` handler literally calls `open("<unknown>","rb")`,
   and `<string>` / `<stdin>` / `<frozen importlib._bootstrap>` all arrive
   as audit args. They are relative, so `abspath()` places them *inside*
   your repo and they enter the index as a file no diff can ever name.

6. **Query with the working tree, not the commit.** Use
   `git status --porcelain -z --untracked-files=all`. The shape you are
   catching is the added file, and an added file is untracked until someone
   stages it — a `git diff`-based query is blind to exactly the case you
   built this for.

7. **Report at the unit the reader can RUN.** Attribute at the finest
   granularity you can, then union up to the file/target. A per-test index
   is misleading whenever a module- or class-scoped fixture does the I/O:
   all of it lands on whichever test ran first, and the siblings look
   independent. The union is a superset, so it is fail-closed, and "run this
   file" is an instruction; "run this one test of three" is a wrong one.

8. **State both directions of error in the tool itself.** Over-approximation
   (reading a file ≠ asserting about it) is the safe direction and should
   be loud. Under-approximation is the dangerous one: existence checks
   (`os.stat`) that you deliberately did not audit, work done in a
   subprocess that does not carry the hook, and any index recorded against a
   revision that has since moved. Record the revision in the index and say
   so when it is stale.

9. **Keep it diagnostic.** Exit 0 on findings by default; put any
   non-zero behind an opt-in flag and do not wire that flag into the
   automation. A check that can block the change that would fix it stops
   being read.

10. **Make the finding reach the actor.** An index nobody queries is the
    prose registry again with a JSON extension. Name the command in the
    place the affected person already reads — the failure message of the
    check itself, the PR template, the pre-round/pre-commit note — and
    derive that sentence from the current data rather than writing today's
    situation into it.

## Pitfalls

- **Recording only reads.** Covered above; it is the single most common way
  this ends up useless. The negative test is `scanned_dir/does_not_exist`.
- **Hardcoding the summary sentence.** The headline that says *what* the
  list below is will be read by everyone and re-derived by nobody. Compute
  it from the rows. (Round 493 wrote "the wiring-audit trio below…" into a
  prompt; twelve rounds later it stood above a list with no wiring audit in
  it.)
- **Installing a global hook at import.** `sys.addaudithook` cannot be
  removed. Arm it from an explicit environment variable so importing the
  module as a library — which the query path does — costs nothing.
- **Believing "no rows" means "safe".** It also means "the index does not
  know about this". Print which, and print the recorded revision.
- **Treating an over-approximation as a bug.** The output is a shortlist to
  run. If running it is cheap, a few extra entries cost nothing and a
  missing entry costs the whole point.
- **Recording an index while the tree is mid-change.** Record from a state
  you can name, and store the revision beside the data.

## Verification

Against any repo with a Python test suite:

```bash
# 1. the index exists and is not empty
python3 harness/readset.py record            # or your equivalent
python3 -c "import json;m=json.load(open('harness/readset-map.json'));\
print(len(m['roster']),'nodes',len(m['nodes']),'with evidence')"

# 2. THE test: a file that does not exist, inside a scanned directory,
#    must still implicate the check that scans it
python3 harness/readset.py blast languages/whence/no_such_file.py
#    -> IMPLICATED  harness/tests/test_swe_copyparity_real_subject.py

# 3. the negative control: an unscanned path must implicate nothing
python3 harness/readset.py blast some/directory/nothing/reads.txt

# 4. the query sees an UNTRACKED file
touch languages/whence/zz_probe.py && python3 harness/readset.py blast
rm languages/whence/zz_probe.py

# 5. the hook is not installed unless asked
python3 -c "import sys;sys.path.insert(0,'harness');import readset;\
assert readset._REC is None"
```

The instrument is working when step 2 names a file in a directory you do not
run, and step 3 names nothing.

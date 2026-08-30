---
name: measured-not-declared-dependencies
description: When a cache, ledger or freshness gate must know which inputs can change a result, measure the process's real read-set with an audit hook instead of maintaining a list of dependencies by hand — and make every way the measurement can fail widen the scope rather than narrow it.
---

# Measured, not declared, dependencies

## When this applies

Trigger on any of these:

- A cached or recorded result is stamped with "the version of the inputs", and
  the input set is defined by a **directory, a glob or an extension list** —
  `sha over src/**/*.py`, `mtime of the config dir`, `hash of every .json`.
- Recall is collapsing: the stamp keeps invalidating results for changes that
  provably cannot affect them, so the cache never accumulates.
- Or the opposite: a result stayed "fresh" across an edit to something it
  really does read, because the edit was to a file the stamp does not cover
  (a `.lang`, `.sql`, `.proto`, fixture or template loaded as source).
- You are about to write a comment like "these are the files that matter" or a
  constant like `RELEVANT_MODULES = [...]`.

Do NOT reach for this when the dependency set is a pure `import` graph you can
resolve statically — scan it. This is for the cases where the process loads by
file path, copies a tree, reads a non-code source, or shells out.

## Why declaring loses

A declared dependency list is a rule with nothing enforcing it. It is correct
on the day it is written and drifts silently from then on, because the next
person to add `open(some_new_file)` has no reason to look at it. The two
failures are not symmetric but they are both silent:

- **Too narrow → fail-OPEN.** A stale result is served as fresh. This is the
  expensive one; it is indistinguishable from a correct result.
- **Too wide → recall collapse.** Every unrelated edit invalidates everything.
  A gate that cries wolf gets ignored, which converts back into fail-open by a
  different route.

## Steps

1. **Measure the current cost before building anything.** Over the last N
   commits, count how many touched the declared input set but touched nothing
   the consumers actually read. If it is under ~10%, stop — the imprecision is
   not what is hurting you.
   ```bash
   git log --since=<date> --name-only --pretty=format:'@@%H %s'
   ```
2. **Find the fail-open half in the same pass.** Count commits touching files
   the consumers DO read that the stamp does not cover. One is enough to
   justify the fix; these are the ones that served a wrong answer.
3. **Install an audit hook in the consumer process**, before it imports
   anything of its own:
   ```python
   def _hook(event, args):
       if event == "open":
           ...record args[0] if it is under the root...
       elif event in ("subprocess.Popen", "os.exec", "os.posix_spawn", "os.fork"):
           ...record an OPAQUE marker...
   sys.addaudithook(_hook)
   import pytest; sys.exit(pytest.main(argv))   # only now
   ```
   Launch the child as `python -c <bootstrap>`, not `python -m <tool>`: a hook
   installed by a plugin or a `conftest` loads *after* the imports you most
   need to see. Both forms put cwd at `sys.path[0]`, so nothing else changes.
4. **Normalise bytecode reads back to sources.** With a warm `__pycache__`,
   importing `pkg.mod` opens `pkg/__pycache__/mod.cpython-3XX.pyc` and never
   opens `pkg/mod.py` — the source is `stat`ed, not read. Un-normalised, your
   measurement says "reads nothing", which is fail-open and looks like a win.
5. **Record DIRECTORIES, not files.** If anything enumerates (`glob`,
   `os.listdir`, `git ls-files`), a file-granular scope misses an ADDED file
   entirely, because nothing opened it. A directory digest over every file in
   it — any extension — catches appearance, disappearance and content.
6. **Make every failure mode widen.** Write down the list and give each one a
   test:
   - a subprocess spawned → scope is EVERYTHING (you cannot see the child's
     reads);
   - record missing / torn / wrong shape → scope is EVERYTHING;
   - a record from before this mechanism existed → the OLD rule, unchanged.
   An empty scope with a well-formed record is legal and is a real finding —
   distinguish "measured nothing" from "measured nothing because it broke".
7. **Compute the new stamp inside the same before/after bracket** that already
   detects the inputs moving mid-run. If you compute it after that bracket
   closes, a concurrent edit records a baseline that is too NEW and the next
   check compares it to itself and calls it fresh.
8. **Report the narrowed claim as its own, weaker state.** `fresh_scoped`, not
   `fresh`. Keep the old counter's meaning exactly, add a second one, print
   both. Anything already published against the old name keeps meaning what it
   meant.

## Pitfalls

- **Merging the weak state into the strong one.** It makes every historical
  figure quoting the strong one retroactively wrong, and nobody can tell which
  runs were which. Two counters, always.
- **Assuming the hook is free because it "just records strings".** Prefilter
  absolute paths on a string compare before calling `abspath`, which calls
  `getcwd()` on every hit.
- **Believing the measurement covers subprocess reads.** It does not, at all.
  If you skip step 6's first bullet the whole design is unsound, quietly.
- **Testing only the narrowing.** The narrowing is the easy half. The tests
  that matter are the four refusals — opaque, torn, missing, pre-existing.
- **Measuring a scope from a run that failed early.** A crashed run read less
  than a healthy one. Either refuse to narrow on a non-clean outcome or accept
  it knowingly; do not discover it later.

## Verification

Re-run these after any change to the mechanism:

```bash
# 1. the refusals — each must classify exactly as the OLD rule did
pytest -q <tests> -k "opaque or torn or missing or pre_"

# 2. the narrowing, both directions, in one test:
#    an edit OUTSIDE a recorded scope  -> the weak-fresh state
#    an edit INSIDE  it                -> stale, naming the directory
pytest -q <tests> -k "scope"

# 3. the ordering pin (there is no runtime observable for "hook too late")
#    assert the hook install precedes the tool import in the bootstrap SOURCE

# 4. recall, before and after, on the real tree
<your status command>
```

Worked example and the measurements behind every rule above:
`knowledge/round-361-the-freshness-gate-was-wrong-in-both-directions.md`
(52% of invalidating commits were false alarms; 3 commits exercised the
fail-open half; recall 0% → 37% in one round, which surfaced a test that had
been red and unnoticed). Related:
`skills/unenforced-documented-rule/` (the failure mode a declared list is),
`skills/pristine-checkout-differential/` (the other "measured in the wrong
tree" gap, round 355).

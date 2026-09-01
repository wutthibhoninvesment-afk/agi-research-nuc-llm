---
name: copy-parity-differential
description: Use when code is tested somewhere other than where it lives — a mutation/repair sandbox, a tempdir copy, a Docker COPY of a subdirectory, an extracted sdist, a `git worktree` — and something fails only there. Symptoms: a sandboxed campaign refuses to start with "baseline not green" and names one test; `FileNotFoundError` on a path under `/tmp/...` that exists in the real checkout; a test that reads a registry/ledger/census/fixture living OUTSIDE the subtree under test; `os.path.dirname(os.path.dirname(__file__))` or `join(ROOT, "..", "..")` reaching over the project root; a defect class fixed at N sites that reappears at site N+1 a round later; a gate that says "red" without saying which test. Covers diffing per-node verdicts in place vs. copied, the two modes (collect-time vs. run-time) and why the cheap one is blind to half the class, and the one-root fix. NOT for untracked files a clean clone would lack (pristine-checkout-differential), NOT for missing packages, which fail in BOTH trees.
---

# The tree that only works where it was written

Copy a project subdirectory somewhere else and run its tests. Anything in it
that reaches OUTSIDE itself — a registry under `state/`, a sibling package, a
git checkout, a census file — was resolved from `__file__` and now points at
the copy's parent. In the original tree that parent is the repo root. In
`/tmp/xyz/proj` it is `/tmp`.

Nothing about the code looks wrong, and the suite is green everywhere anyone
looks, because the only place it fails is a directory that exists for eight
seconds inside a tool nobody has run lately.

```
"The suite is green" means green WHERE IT LIVES.
A sandbox is a different location, and location is an input.
```

Worked example (round 419, this repo). Mutation testing runs each mutant in a
tempdir copy of `languages/whence` alone. Two test files resolved their pin
registries as `join(ROOT, "..", "..", "state", ...)`, so inside the sandbox
they opened `/tmp/state/whence/round-414/check-pins.json`, raised
`FileNotFoundError`, and the campaign's baseline gate refused to start —
**every mutation campaign against that tree was impossible for five rounds
and nobody noticed, because nobody ran one.** It was the third recurrence:
the same class had stopped the same engine twice before, and the second fix
introduced a shared root helper and wrote the rule in a comment that the very
next round's new file did not follow.

## When to use (triggers)

- A sandboxed run (mutation, repair, a build in a container, an installed
  wheel) refuses with "baseline not green" / a single named failing test,
  while the same suite is green in the checkout.
- A traceback shows a path under `/tmp`, `/build`, `/app` or a worktree that
  clearly should have been under the repo root.
- You are about to add a file to a subtree that reads something outside it.
- A defect class was fixed at several sites and the fix was recorded as a
  comment, a docstring, or a convention.
- Before quoting any sandboxed campaign's score: a gate that has never been
  green produces no score at all, which is not the same as a low one.

**When NOT to use:** files a clean clone would not have (untracked fixtures,
gateway leftovers) is `pristine-checkout-differential` — that differential
varies *what is in the tree*, this one varies *where the tree is*. A missing
dependency fails in both locations and is neither. A rule the docs state
about *inputs* that nothing validates is `unenforced-documented-rule`.

## Steps

1. **Reproduce the gate, and read what it refuses on.** A refusal is not a
   diagnosis; get the name of one failing node out of it first.

   ```bash
   python3 -c "from swe import mutation as M; from swe.fuzz import WHENCE_ROOT; \
               print(M.baseline_check(WHENCE_ROOT, M.DEFAULT_TEST_CMD, timeout_s=600)['tail'])"
   ```

2. **Diff the two locations per node, not per exit code.** Run the suite in
   place and in a copy made exactly the way the tool makes it, through the
   same process helper (so the copy gets the same environment), and compare.

   ```bash
   python3 -m swe.copyparity collect                    # node-id sets, seconds
   python3 -m swe.copyparity run --test-args "-q tests" # per-node verdicts, full cost
   ```

3. **Know which mode can see your defect — no single one covers the table.**
   Round 425 measured all three against the real subject
   (`languages/whence`) and found FOUR classes, not one:

   | class | static `escapes` | `collect` | `run` | the exit-code gate |
   |---|---|---|---|---|
   | escape used at import | yes | yes | yes | yes |
   | escape used in a test body | yes | no | yes | yes |
   | escape **computed, never used** | yes | no | no | **no** |
   | **coverage that evaporates** | no | no | yes | **no** |

   A read at MODULE level aborts collection, so the node vanishes and the
   cheap `collect` mode finds it. A read inside a test body collects
   identically in both trees and only the VERDICT moves — invisible to
   `collect`, and that blindness deserves its own test rather than a sentence
   in a docstring.

   The last two rows are the ones people miss:

   * **Computed and never used.** `os.path.dirname` does not raise; it
     happily returns `/`. So an escaping expression that nothing opens is
     green in BOTH differentials, forever, until the round that finally reads
     the variable. Round 425 found two in a tree both modes called clean —
     each one a fix that repointed every USE and left the COMPUTATION behind,
     which is not a fix, it is a smaller bug with no symptom.
   * **Coverage that evaporates.** A test guarded by
     `if <resource missing>: pytest.skip(...)` turns into a no-op when the
     sandbox lacks that resource — `.git` is the common one, because copy
     helpers exclude it. `passed -> skipped` is not a failure: **both sides
     exit 0**, so every exit-code gate stays green while the test stops
     providing evidence. In a mutation campaign that inflates the score by
     exactly the amount nobody can see.

4. **Read the arithmetic instead of running it, if you want a check you can
   afford every time.** Measured costs on a 2000-test subtree: static scan
   **0.4 s**, `collect` **3.8 s**, `run` **283 s** — a 74x gap between the
   two differentials. Nothing at `run`'s price goes in a per-round check, and
   wiring only the cheap mode installs a checker that cannot see the defect
   it was built for, which is worse than none because it reports green.

   A static scan evaluates path expressions as a DEPTH below the subtree
   root: `__file__` is its own depth, `dirname` subtracts one, a `join`
   component adds one, `".."`/`os.pardir` subtracts one, `Path.parent` and
   `.parents[n]` likewise. Level 0 is the root; **any expression reaching a
   negative level names a path outside the tree.** Two rules keep it
   trustworthy: an unknown component counts +1 and never -1 (guess AWAY from
   findings, or your checker gets uninstalled), and an escape reached through
   the sanctioned root env var is exempt — that pattern survives the copy on
   purpose, and flagging it makes the checker red at the very fix it is
   recommending.

5. **Strip `-x` before diffing.** With exit-first the two runs stop at
   different tests and the diff is noise. Report that you stripped it: the
   command you measured is then not the command the caller passed.

6. **Grep for the escaping expression across the whole subtree**, not just the
   file that failed. One failure means the rule is not enforced; there are
   usually more.

   ```bash
   grep -rn "dirname(dirname\|\"\\.\\.\", *\"\\.\\.\"\|os.pardir" <subtree> --include=*.py
   grep -rn "<ROOT_ENV_VAR>" <subtree> --include=*.py     # who already does it right
   ```

7. **Fix at the ROOT, not at the site.** One module owns "where is the real
   repo", preferring an environment variable the sandbox-spawning process
   exports, falling back to the `__file__` computation. Every other site
   imports that name. Two sites computing the same root two ways is the defect
   in waiting.

   ```python
   # the one home for it
   AGI_ROOT = os.environ.get("AGI_RESEARCH_ROOT") or os.path.dirname(os.path.dirname(_HERE))
   # every consumer
   REGISTRY = os.path.join(_C.AGI_ROOT, "state", "...", "pins.json")
   ```

8. **Leave a checker, not a comment.** If this is the second time, the fix is
   not another comment — it is the command in step 2 wired into something that
   runs. A convention that has already been broken once will be broken again
   by whoever writes the next file, who will not have read the comment.

## Pitfalls

- **Two `-q` are `-qq`.** Appending `-q` to a command that already has one
  silences the node listing entirely; the differ then parses an empty list on
  BOTH sides and reports parity. A checker that finds nothing looks exactly
  like a tree with nothing wrong — assert a non-zero node count before
  trusting any "no differences" verdict.
- **A timeout is not a pass.** If either side hits its cap, the verdict is
  "no verdict"; an empty or truncated node set must never fall through to
  `copy_safe`.
- **Green only in the copy is also a defect** — a test that passes only when
  the tree is somewhere else. Give it its own bucket so the direction is
  legible.
- **The gate's own tests probably use a toy project.** They pin the mechanism
  and say nothing about the tree it is pointed at. Check whether any test
  runs the gate against the REAL subject; usually none does.
- **Killing the runner may not kill the run.** Sandbox helpers commonly start
  children with `start_new_session=True` precisely so they can kill the whole
  group on timeout — which also means killing the parent's group leaves the
  child alive. Find it by `readlink /proc/<pid>/cwd` and kill its own group.
- **Cost claims in docstrings rot like any other number.** "This file costs
  about a second" was 177 seconds. Time it before budgeting a differential
  around it.

## Verification

- [ ] The gate that refused now passes, and you ran it — not a proxy.
- [ ] `copyparity run` (or your equivalent) reports the previously-failing
      node with the SAME verdict on both sides, and a node count > 0 on each.
- [ ] `collect` mode is green too, and you know which of the THREE modes
      would have caught your defect — check it against the table in step 3
      rather than assuming, and note that two of the four classes are
      invisible to every exit-code gate.
- [ ] A static scan of the subtree reports zero unguarded escapes, and its
      file count is > 0. A scan that read nothing reports "no findings" and
      is indistinguishable from a clean tree; make it exit non-zero on an
      empty scan.
- [ ] The grep in step 5 returns no remaining site that computes the outside
      root for itself.
- [x] There is a test that fails if a new file reintroduces the pattern —
      either the differential itself, wired into a suite, or a static check.
      Closed for this repo in round 425:
      `harness/tests/test_swe_copyparity_real_subject.py`, 10 tests, 8.6 s,
      promoted into the fast tier so it runs every round. The point is not
      that the test exists; it is that it is pointed at the REAL subject and
      is cheap enough to survive the budget review that kills slow checks.
- [ ] The knowledge record says which claim was proven: *this file is
      copy-safe* and *the suite still collects* are weaker than *every node is
      copy-safe*, and only the last one requires the full two-run diff.

The reference implementation, run narrow so it is affordable to type. Note
the node count in the output — the first pitfall above is that a differential
which collected NOTHING reports parity, so a verdict with no `N node(s)` on
both sides is not a verdict:

Run it from the REPO ROOT, not from `harness/`. `--test-args` are pytest
arguments evaluated inside the tree copyparity copies (`--root`, default
`languages/whence`), so `tests/test_lexer.py` below names
`languages/whence/tests/test_lexer.py` and NOT `harness/tests/`. Round 421
had to fix this line: written with a leading `cd harness`, the same token
read to a human — and to `claim_check.py` — as if it named a file under
`harness/tests/`, where no such file exists. The checker resolved it there,
found nothing, and made the skills corpus red with a STALE C001. Note the
general shape: a tool with its own `--root` flag moves the base out of every
checker's sight, so a correct command can be unconfirmable. From the repo
root the token is honestly
unanchored — relative to a base no checker can see — and is skipped
instead of mis-resolved.

```bash
PYTHONPATH=harness python3 -m swe.copyparity run \
  --test-args '-q -p no:cacheprovider tests/test_lexer.py'
# copyparity(run): copy_safe — in_place 32 node(s) rc=0 0.5s / copied 32 node(s) rc=0 0.5s
#   no node changed verdict when the tree was copied
python3 -m pytest -q harness/tests/test_swe_copyparity.py -p no:cacheprovider
```

Exit status is the verdict: `0` only when every shared node agrees AND
nothing vanished or appeared. Widen with `--test-args` one directory at a
time rather than pointing it at the whole suite first — round 419 measured
the unfiltered whence run at 177 s per side.

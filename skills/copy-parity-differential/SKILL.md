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

3. **Know which mode can see your defect.** A read at MODULE level aborts
   collection, so the node vanishes and the cheap `collect` mode finds it. A
   read inside a test body collects identically in both trees and only the
   VERDICT moves — invisible to `collect`, and that blindness deserves its own
   test rather than a sentence in a docstring.

4. **Strip `-x` before diffing.** With exit-first the two runs stop at
   different tests and the diff is noise. Report that you stripped it: the
   command you measured is then not the command the caller passed.

5. **Grep for the escaping expression across the whole subtree**, not just the
   file that failed. One failure means the rule is not enforced; there are
   usually more.

   ```bash
   grep -rn "dirname(dirname\|\"\\.\\.\", *\"\\.\\.\"\|os.pardir" <subtree> --include=*.py
   grep -rn "<ROOT_ENV_VAR>" <subtree> --include=*.py     # who already does it right
   ```

6. **Fix at the ROOT, not at the site.** One module owns "where is the real
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

7. **Leave a checker, not a comment.** If this is the second time, the fix is
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
- [ ] `collect` mode is green too, and you know which of the two modes would
      have caught your defect.
- [ ] The grep in step 5 returns no remaining site that computes the outside
      root for itself.
- [ ] There is a test that fails if a new file reintroduces the pattern —
      either the differential itself, wired into a suite, or a static check.
- [ ] The knowledge record says which claim was proven: *this file is
      copy-safe* and *the suite still collects* are weaker than *every node is
      copy-safe*, and only the last one requires the full two-run diff.

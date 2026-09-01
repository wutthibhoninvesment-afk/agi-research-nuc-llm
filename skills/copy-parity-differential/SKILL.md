---
name: copy-parity-differential
description: Use when code is tested somewhere other than where it lives — a mutation/repair sandbox, a tempdir copy, a Docker COPY of a subdirectory, an extracted sdist, a `git worktree` — and something fails only there. Symptoms: a sandboxed campaign refuses to start with "baseline not green" and names one test; `FileNotFoundError` on a `/tmp/...` path that exists in the real checkout; a test reading a registry/fixture OUTSIDE the subtree under test; `join(ROOT, "..", "..")` reaching over the project root; a defect class fixed at N sites reappearing at N+1; a static copy-safety scan reporting clean on a tree that is measurably not; a test evaporating into a skip or a bare `return` only in the sandbox; a corpus/allowlist/denominator that is silently BIGGER in the sandbox because the guard curating it reads `.git` or other repo metadata the copy helper excludes. Covers per-node verdict diffing, which of seven defect classes each mode sees — including one no mode sees — the running-minimum rule for path arithmetic, a signed skip registry, and the one-root fix. NOT for untracked files a clean clone would lack (pristine-checkout-differential), NOT for missing packages, which fail in BOTH trees.
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
- A function promises a CURATED set — `only committed`, `only tracked`, `excluding vendored` — and resolves it by shelling `git`/`hg`/`pip`/`npm`
  inside a `try/except: pass` with a `listdir`/`glob` fallback, and its
  result feeds a corpus, an allowlist or any denominator. In a copy it
  falls back, and the fallback is always LARGER.
- A count in a sandboxed artefact does not match the same count in the
  checkout, and nothing failed. `programs: 27` against `programs: 13` is a
  finding, not a rounding difference.

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
   Rounds 425 and 431 measured all three against the real subject
   (`languages/whence`) and found SIX classes, not one. Round 437 added a
   seventh, and it is the first one **no column catches**:

   | class | static `escapes` | `collect` | `run` | signed skip list | the exit-code gate |
   |---|---|---|---|---|---|
   | escape used at import | yes | yes | yes | no | yes |
   | escape used in a test body | yes | no | yes | no | yes |
   | escape **computed, never used** | yes | no | no | no | **no** |
   | **coverage that evaporates** (`pytest.skip`) | no | no | yes | yes | **no** |
   | **evaporates into a vacuous PASS** (early `return`) | yes | no | **no** | **no** | **no** |
   | **silently FEWER collected nodes** | no | yes | yes | node floor | **no** |
   | **a curated SET silently WIDENS** (round 437) | **no** | **no** | **no** | **no** | **no** |

   A read at MODULE level aborts collection, so the node vanishes and the
   cheap `collect` mode finds it. A read inside a test body collects
   identically in both trees and only the VERDICT moves — invisible to
   `collect`, and that blindness deserves its own test rather than a sentence
   in a docstring.

   The last three rows are the ones people miss:

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
     providing evidence.
   * **The same guard written as `return` instead of `skip`, which is
     strictly worse.** `if not os.path.exists(p): return` records the node
     as **PASSED**. It is invisible to the exit code, invisible to a per-node
     verdict differential (the verdict did not move), and invisible to a skip
     registry (there is no skip). Only the static scan can see it, because
     only the static scan does not need the defect to fire. Round 431 found
     one live in this repo. If you convert a red to a skip you owe an
     acknowledgement entry; if you convert one to a bare `return` you have
     deleted an assertion and told nobody.
   * **Get the DIRECTION right when you write this up.** Round 425 wrote
     that an evaporated test leaves "the mutation score inflated by exactly
     the amount nobody can see", and every later round quoted it. It is
     backwards. A mutation score is `killed / total`; a test that stops
     running moves the mutants it would have killed from `killed` to
     `survived`, so the score goes **DOWN** and the SURVIVOR list grows.
     That is not the flattering direction — it is phantom test gaps, and
     each phantom is paid for a second time by whatever killer-search or
     auto-repair stage consumes the survivor list hunting for a killer that
     already exists in the tree. Before you claim a magnitude, measure it:
     the honest question is *does this test kill anything at all*, and the
     cheap answer is its line coverage of the files being mutated. Round 431
     asked it of the instance round 425 found: **0 covered lines in the file
     every campaign actually mutates, and 0 of 60 mutants killed** when the
     test was run against them in a tree where it does not skip. The class
     was real; that instance's cost was zero.

   * **A curated SET that silently widens, because the thing that curates it
     lives outside the copy.** The copy helper excludes `.git` deliberately —
     it is large, and nothing in a test tree needs it. Anything that resolves
     a LIST by asking git therefore gets a different, WEAKER answer in the
     copy, and getting a weaker answer is not an error:

     ```python
     def list_example_files(root):
         """Only COMMITTED examples enter differential corpora."""
         try:
             out = subprocess.run(["git", "ls-files", "examples"], cwd=root,
                                  capture_output=True, check=True)
             ...
         except (OSError, subprocess.CalledProcessError):
             pass
         return sorted(n for n in os.listdir(ex_dir) if n.endswith(".lang"))
     ```

     Round 437, this repo: 32 `.lang` files on disk, 18 tracked, 14 named in
     `.gitignore` and written by a different process. In the checkout the
     corpus was 13 programs. In every copied tree it was **27** — and every
     mutation/differential campaign that ran against a sandbox had been
     scoring against 14 files nobody curated, for as long as the guard had
     existed.

     **Why no column catches it.** The static scan looks for path expressions
     that leave the subtree LEXICALLY; this one leaves at RUNTIME, when git
     walks up from `cwd` looking for a repo and does not find one. `collect`
     sees the same node ids. `run` sees the same per-node verdicts — the tests
     still pass, they just assert over a bigger set. There is no skip to sign
     and no non-zero exit to gate on. **The defect is in a denominator, and a
     verdict differential has no denominator column.**

     The tell is grammatical, so you can grep for it: a function whose
     docstring promises a CURATED set (`only committed`, `only tracked`,
     `excluding vendored`, `the allowlisted N`) and whose body has a
     `try/except: pass` around a `git`, `hg`, `svn`, `pip`, `npm ls` or
     package-metadata call, with a bare `listdir`/`glob` after it. Every one
     of those falls back to *more*, never to *fewer*, and never says so.

     **Fix at the boundary, not at the reader.** The copy helper is the one
     place where the original is still reachable, so materialise the answer
     INTO the copy (a `.curated` manifest beside the data) and let the reader
     resolve `real source -> manifest -> fallback`, **naming which one it
     took** so a caller can record it. A copy of a copy inherits the manifest
     for free and must NOT regenerate it — the intermediate tree cannot ask
     either, and "regenerate if you can" re-curates from whatever that tree
     happens to contain. A source that can answer neither gets NO manifest: a
     manifest asserts that a curation decision was made, and inventing one
     freezes a `listdir` snapshot under a name that claims otherwise.

4. **Read the arithmetic instead of running it, if you want a check you can
   afford every time.** Measured costs on a 2000-test subtree: static scan
   **0.4 s**, `collect` **3.8 s**, `run` **283 s** — a 74x gap between the
   two differentials. Nothing at `run`'s price goes in a per-round check, and
   wiring only the cheap mode installs a checker that cannot see the defect
   it was built for, which is worse than none because it reports green.

   A static scan evaluates path expressions as a DEPTH below the subtree
   root: `__file__` is its own depth, `dirname` subtracts one, a `join`
   component adds one, `".."`/`os.pardir` subtracts one, `Path.parent` and
   `.parents[n]` likewise. Level 0 is the root.

   **The finding is the RUNNING MINIMUM, not the final level.** Get this
   wrong and the checker reports clean on the tree it was built for. Round
   425's rule was `final level < 0`; round 431 measured what that missed:

   ```python
   REG = os.path.join(HERE, "..", "..", "state", "whence", "round-422")
   #                    0    -1    -2     -1      0        +1   <- ends at +1
   ```

   Final level **+1**, so "copy-safe" — while the path is
   `<repo>/state/whence/round-422`, which in the sandbox is
   `/tmp/xxx/proj/../../state/...` and does not exist. **27 expressions of
   that shape, 17 tests red in the sandbox, the mutation gate at exit 1 and
   no campaign able to start — under a static checker that had been reporting
   `copy_safe` on the same tree since it was written.** The final level is
   not even meaningful once the expression has left the tree: +1 would mean
   "one level under the root", and the path is not under the root at all.

   The rule, stated so it cannot be re-derived wrong:

   ```
   floor < 0  <=>  this expression names something outside the tree
   ```

   `os.path.join` does not normalise, so the `..` is resolved lexically by
   the OS at open time — against the copy's parent. A path that leaves and
   comes back has still left. Carry the floor through variable bindings too:
   `REG` above is bound to a path outside the tree, and every later
   `join(REG, "f.json")` is a second finding, not a fresh start from zero.
   Note which of the two numbers your own findings were selected on before
   you believe a clean report.

   Two more rules keep it trustworthy: an unknown component counts +1 and
   never -1 (guess AWAY from findings, or your checker gets uninstalled —
   and +1 can only RAISE a running minimum, so the guard holds for the floor
   as well), and an escape reached through the sanctioned root env var is
   exempt — that pattern survives the copy on purpose, and flagging it makes
   the checker red at the very fix it is recommending.

   A dip that stays inside is NOT a finding: `join(HERE, "tests", "..",
   "examples")` floors at 0 and resolves inside the copy. The floor rule is
   exact, not merely stricter — it goes negative exactly when the expression
   names the parent of the subtree root.

5. **Make the gate itself grade the skip list — it costs zero extra runs.**
   The two-run differential is what ESTABLISHES which skips the copy caused;
   it is the wrong shape for re-checking that every campaign. The gate
   already runs the suite once in the copy. Add `--junitxml` to *that* run
   and compare its skip list against a signed registry:

   ```python
   cmd = list(test_cmd) + ["--junitxml=%s" % xml]   # xml OUTSIDE both trees
   rec = parse_junit(xml)                            # never raises; ok=False on absence
   block = check(rec, suite="<tree>-<cmd>")          # 4 buckets + a verdict
   ```

   Design rules, each of which cost a round somewhere:

   * **Key on junit's `(classname, name)`, never file:line.** `pytest -rs`
     keys by line and reports a phantom every time somebody adds an import.
   * **Pin the REASON, not just the node.** A node signed forever is a mute
     button; a changed reason means it is skipped for something nobody
     adjudicated, and that must go red (`pin_expired`).
   * **Print acknowledged rows every run.** An acknowledgement that
     suppresses invisibly reads as coverage.
   * **Report acknowledgements that match nothing** — they suppress nothing
     and must be deleted.
   * **A one-sided run cannot tell "the copy caused it" from "it is skipped
     everywhere".** Do not pretend otherwise: sign BOTH, and record which is
     which in a `class` field the two-run differential filled in.
   * **Record whether the skip can cost you anything.** For a mutation gate
     the question is whether the test covers the mutated files at all; carry
     the answer (`kills_mutants`) and print a `true` LOUDLY on every run.
     A signed skip that costs nothing is bookkeeping; one that costs kills is
     a standing debt against every number you publish.
   * **Absence of a report is not "no skips."** No junit ⇒ `unavailable` ⇒
     no verdict in either direction.
   * **Pin the node COUNT too.** It is the only thing that sees a suite which
     silently collected fewer tests: exit 0, no failure, no skip, less
     evidence. A floor only fires when the count DROPS, so adding tests makes
     it stale-low and never false-positive.
   * **Report first, refuse on request.** Default the new refusal OFF until
     the registry is populated. A gate whose false-positive cost is "no
     campaign runs at all" is how engines get stopped at the door — which in
     this repo has now happened four times.

6. **Strip `-x` before diffing.** With exit-first the two runs stop at
   different tests and the diff is noise. Report that you stripped it: the
   command you measured is then not the command the caller passed.

7. **Grep for the escaping expression across the whole subtree**, not just the
   file that failed. One failure means the rule is not enforced; there are
   usually more.

   ```bash
   grep -rn "dirname(dirname\|\"\\.\\.\", *\"\\.\\.\"\|os.pardir" <subtree> --include=*.py
   grep -rn "<ROOT_ENV_VAR>" <subtree> --include=*.py     # who already does it right
   ```

8. **Fix at the ROOT, not at the site.** One module owns "where is the real
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

9. **Leave a checker, not a comment.** If this is the second time, the fix is
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
- **A verdict differential has no denominator column.** Every mode in the
  table answers "did this node's outcome move?". A defect that leaves every
  outcome identical while changing what the test asserted OVER is outside all
  of them, and it is the one shape that gets *more* evidence rather than an
  error — so it never looks like a failure. If a sandboxed run produces a
  COUNT (programs, cases, files, fixtures), diff that count against the same
  count in the checkout; that comparison is cheap and no mode does it for you.
- **`.git` is excluded from the copy on purpose, and that is a dependency
  nobody declares.** Grep the subtree for every reader of each thing your copy
  helper's ignore list names — `.git`, `node_modules`, `.venv`, `*.egg-info` —
  before trusting any guard that reads one. This repo had already hit it once
  (a test shelling `git show`) and wrote it in a docstring; the second
  instance was in the harness, not the subject, and the docstring did not
  reach it.
- **Cost claims in docstrings rot like any other number.** "This file costs
  about a second" was 177 seconds. Time it before budgeting a differential
  around it.

## Verification

- [ ] The gate that refused now passes, and you ran it — not a proxy.
- [ ] `copyparity run` (or your equivalent) reports the previously-failing
      node with the SAME verdict on both sides, and a node count > 0 on each.
- [ ] `collect` mode is green too, and you know which of the THREE modes
      would have caught your defect — check it against the table in step 3
      rather than assuming. **Four of the seven classes are invisible to every
      exit-code gate, and the seventh is invisible to all five columns**, so
      "the modes are green" is not the same claim as "the tree is clean".
- [ ] A static scan of the subtree reports zero unguarded escapes, and its
      file count is > 0. A scan that read nothing reports "no findings" and
      is indistinguishable from a clean tree; make it exit non-zero on an
      empty scan.
- [ ] **You know what predicate that clean scan was computed with**, and it
      is the running minimum rather than the final level. Round 431: the
      scan said `copy_safe — 0 escaping expressions` over a tree with 29 of
      them and a dead mutation engine. A clean report from an unsound
      predicate is worse than no report; check `_component_delta("../../a")`
      (or your equivalent) directly, in a test, so a later simplification
      back to the endpoint rule fails on a clean tree.
- [ ] Every skip the sandbox produced is signed, with its REASON pinned, and
      the acknowledged ones are printed. Count them: `N skipped` in the
      gate's own tail is a number nobody has ever compared to anything.
- [ ] You have said which direction the defect moves the number, and measured
      the magnitude rather than asserting it. "Inflated" and "deflated" are
      different bugs with different remedies, and a lost test that covers
      none of the mutated files costs exactly nothing.
- [ ] The grep in step 5 returns no remaining site that computes the outside
      root for itself.
- [x] There is a test that fails if a new file reintroduces the pattern —
      either the differential itself, wired into a suite, or a static check.
      Closed for this repo in round 425:
      `harness/tests/test_swe_copyparity_real_subject.py`, 10 tests, 8.6 s,
      promoted into the fast tier so it runs every round. The point is not
      that the test exists; it is that it is pointed at the REAL subject and
      is cheap enough to survive the budget review that kills slow checks.
- [ ] Every COUNT the sandboxed run produced has been compared to the same
      count taken in the checkout, and you can say why any difference is
      intended. This is the only check that sees class seven.
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

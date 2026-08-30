---
name: policy-replay-over-history
description: When a cache, freshness or invalidation policy is too expensive to evaluate by re-running the thing it guards, recompute its inputs from version control and replay its state machine over hundreds of commits — reporting the real history and the counterfactual side by side, and never merging them.
---

# Replay the policy over history, do not re-run the thing

## Trigger conditions

Trigger on any of these:

- You shipped or inherited an **invalidation rule** — a cache key, a
  freshness gate, a staleness stamp, a "is this recorded result still
  evidence" predicate — and someone asks whether it actually helps.
- The only honest way to find out empirically is to **re-run the expensive
  thing** the rule guards (a full test tier, a build, a benchmark) many
  times, and you cannot afford one pass, let alone a distribution.
- You are about to defend a policy with **arithmetic over commit counts**
  ("52% of commits touch nothing relevant, so this should roughly double
  recall") rather than with a measured outcome.
- You want to compare a policy against **one that was never deployed** —
  a stricter variant, a looser one, or the same rule with one half switched
  off to find out which half binds.
- A ledger, cache or report is stamped with a version of its inputs and you
  want to audit an old entry against the tree it claims to describe.

Do NOT reach for this when the policy is cheap to evaluate live (just run it
N times), or when its inputs are not recoverable from version control
(network state, wall-clock, a third-party service). The overlay step below
handles a *bounded* amount of unrecoverable state; it does not rescue an
unbounded amount.

## Why "is it fresh right now" is the wrong question

A status call answers a point question. A policy question is a distribution:
*how long does a recorded result stay usable, under each rule, starting from
anywhere*. One point tells you nothing about the shape, and in particular it
cannot tell you **which half of a two-part rule is binding** — which is
usually the only thing worth knowing, because that is where the next round of
work should go.

Round 361 of this program added per-file precision to the subject half of a
freshness gate on a correct argument about commit counts. Round 367 replayed
it and found the *harness* half binding by 9.9x: with it switched off the
same entries lived 52.8 commits instead of 5.3. The precision was real and
it was spent on the half that was not the constraint. No amount of staring
at a status line would have shown that.

## Steps

1. **Fix the metric in writing, before you build the instrument.** The one
   that generalises: **lifetime** = for a start commit `S` and a subject `F`,
   the number of consecutive later commits over which a record made at `S`
   stays usable; mean over every start commit in the window. Exclude the last
   commit from the mean — it has lifetime 0 by construction and its inclusion
   makes the number a function of window length.
2. **Recompute the policy's inputs from git objects, not from checkouts.**
   A checkout per commit is minutes each and mutates the tree a round may be
   working in. `git ls-tree -r` gives `{path: blob id}` and one batched
   `git cat-file --batch` gives contents. Cache **by blob id**, not by
   revision: consecutive commits share nearly every blob, so a 240-commit
   sweep reads a small multiple of one checkout.
   ```python
   p = subprocess.Popen(["git", "cat-file", "--batch"], stdin=PIPE, stdout=PIPE)
   out, _ = p.communicate(b"".join(bid.encode() + b"\n" for bid in ids))
   # header: "<sha> <type> <size>\n", then <size> bytes, then "\n"
   ```
3. **Call the REAL state machine. Do not reimplement it.** If the production
   predicate reads from disk, give it an injectable source protocol
   (`exists`/`read`/`list`) and pass a git-backed implementation. A second
   copy of the rule inside the replay will drift, and it will drift towards
   agreeing with whatever you expected — see `skills/copied-mirror-drift/`.
4. **Prove the recomputed inputs are the same function.** Export one
   revision (`git archive <rev> | tar -x`), run the production input
   function over the export, and require equality with the git-object
   version. Make the tool **refuse to report** if that check fails. This is
   the difference between a measurement and a plausible-looking table.
5. **Handle the dirty/untracked overlay explicitly.** If the production
   stamp is computed over a *working tree*, it hashes untracked and modified
   files, so **it corresponds to no commit** and no historical record will
   ever match it. Snapshot the overlay
   (`git status --porcelain`, hash each path) and merge it into the
   recomputed inputs. Then let the match itself be the validity test: an old
   record that still fails to reproduce was taken under a *different*
   overlay, and must be reported unreproducible rather than guessed at.
6. **Run three policies, not one**: the deployed rule, the variant under
   question, and each half in isolation. The isolated halves are not
   shippable and are not meant to be — they answer "which one binds".
7. **Attribute the kills.** A mean lifetime is a conclusion; a blame
   histogram is an action. For every (subject, start commit) pair, find the
   first invalidating commit and record *what moved*. Count every mover on a
   joint kill rather than dividing it — the question is "how often is X
   involved", and splitting understates every cause. Expect one or two
   inputs to dominate; those are the work items.
8. **Report the actual and the counterfactual separately, and say which
   wins.** The counterfactual (measurements held fixed, swept over every
   start commit) is the policy answer. The actual (each real record replayed
   forward from where it was really made) is what the policy has so far
   *delivered*. They routinely disagree. Label the counterfactual as one
   everywhere it appears, and state in the tool's own docstring that the
   actual one wins.

## Pitfalls

- **A record is not a directory list.** Passing a structured record
  (`{ok, dirs, opaque}`) where a list of paths is expected does not raise —
  iterating a dict yields its keys, so you silently measure three
  directories named `ok`, `dirs` and `opaque`, all missing, all constant
  across history. The result is a policy that can never be invalidated and
  therefore *always wins*. The only symptom is that the answer is too clean.
  Pin it with a test that asserts the recomputed inputs **move** when a file
  in the real scope moves and **do not** when one outside it does.
- **A column that is 0 for a structural reason is not a finding.** Before
  concluding "policy X is worthless because it never survives", check that
  its inputs are reproducible at all (step 5). Print the reproducibility
  flag next to the number, permanently.
- **Commits made in the same second have identical `%ct`.** Any anchoring by
  time will be arbitrary. In tests, stamp `GIT_AUTHOR_DATE` /
  `GIT_COMMITTER_DATE` explicitly; do not loosen the assertion.
- **A mean over a bimodal set is a lie by omission.** If two subjects score
  120 and seventeen score 2, the mean of 15 describes nobody. Report the
  subsets that share a mechanism, and quote the ratio on a *fixed* subset
  when comparing policies.
- **The window definition is a choice and it must be one sentence.** "All
  commits since D" and "commits that move the policy's inputs" differ by an
  order of magnitude here (241 vs 65). Write down which one you mean before
  you predict anything about it.
- **Do not narrow on a run that did not finish.** If the policy's inputs are
  *measured* from a process (a read-set, a coverage set), a process that was
  killed or crashed measured less than a healthy one, so its measurement is
  an under-approximation and using it is fail-open. Distinguish "reported a
  verdict" from "stopped early" — for pytest that is return code 0/1 versus
  2/3/4/5 and a signal — and refuse on the second, on both the write side and
  the read side, because an append-only record cannot be retro-stamped.

## Verification

Against `harness/swe/ledgerreplay.py` and `harness/tests/test_ledgerreplay.py`
in this repo (round 367):

```bash
# 1. the recomputed inputs ARE the production function (refuses to report otherwise)
python3 harness/swe/ledgerreplay.py --limit 2 --mode sweep | head -3
#   self-check: git digest <X>  export digest <X>  OK

# 2. the full replay, actual and counterfactual, over round 361's window
python3 harness/swe/ledgerreplay.py --since "2026-08-26" --mode both \
    --json /tmp/replay.json
#   ~57s for 241 commits x 19 subjects on a one-CPU box

# 3. the tests, including the record-vs-list regression pin
python3 -m pytest harness/tests/test_ledgerreplay.py -q
#   19 passed
```

A correct run prints, and these are the shapes to look for rather than the
values, which move every round:

- a `repro` column that is `yes` for records taken under the current overlay
  and `NO` for older ones, with the sentence explaining what a `NO` row's
  `strict` column does and does not mean;
- three policy columns whose *isolated-half* column is much larger than the
  deployed one when that half is binding;
- a blame histogram whose top entry is a work item, not a policy.

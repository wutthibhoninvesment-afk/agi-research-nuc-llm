---
name: running-minimum-not-endpoint
description: Use when a checker decides on the FINAL value of something that changed step by step, and the thing it is really checking is whether a bound was ever crossed. Symptoms: a static or runtime check reports clean on a case you can demonstrate is broken; a predicate written as `if final < 0` / `if balance >= 0` / `if end_offset <= len(buf)` over an expression built from several operations; a limit check that passes because the value came back into range; a path/offset/permission/quota computed by folding deltas and tested only at the end; a "clean" verdict from a tool built for a defect class that then recurs anyway. The move is to fold the sequence carrying the running extremum alongside the value, decide on the extremum, and report both. NOT for a value that is only ever read at the end (there the endpoint IS the trajectory), NOT for choosing a threshold (verdict-carries-its-threshold).
---

# A value that came back into range still left it

Some quantities are checked by folding a sequence of changes: a path
assembled from components, an offset walked through a buffer, a balance
moved by a list of transactions, a privilege level raised and dropped, a
counter against a quota. It is natural to write the fold, keep the answer,
and test the answer.

That is the wrong test whenever the *violation happens during the fold*.

```
The endpoint answers "where did it end up".
The bound was about "did it ever go there".
Those are different questions, and only one of them is the check.
```

The failure is quiet in the worst way: the checker runs, reports clean, and
its cleanliness is used as evidence. Nobody re-reads a green check. The
defect it was built for then recurs *underneath it*, and the recurrence gets
attributed to "nobody ran the checker" when in fact the checker ran and was
asked the wrong question.

**Worked example (this repo, rounds 425 and 431).** A static scan evaluated
path expressions as a depth below a subtree root — `dirname` is -1, a join
component is +1, `".."` is -1 — and recorded a finding when the FINAL depth
was negative, i.e. when the path ended above the root. That caught the two
examples it was written from, both of which ended negative. It did not catch
the shape every actual recurrence had:

```python
REG = os.path.join(HERE, "..", "..", "state", "whence", "round-422")
#                    0    -1    -2     -1      0        +1     ends at +1
```

Net **+1**, so "no expression resolves above the subtree root". The path is
`<repo>/state/whence/round-422`; in the sandbox this subtree is copied to
`/tmp/xxx/proj`, so it opens `/tmp/xxx/proj/../../state/...`, which does not
exist. Measured: **27 expressions of that shape in one file, 17 tests red in
the sandbox, the mutation gate at exit 1, no campaign able to run at all** —
while the static checker built for exactly that class printed
`copy_safe — 84 files scanned, 0 escaping expressions`.

Worse, the final value was not merely insufficient — it was **meaningless**.
"+1" claims *one level under the root*, and the path is not under the root
at all. Once a fold crosses the boundary, everything after it is arithmetic
about a place the model no longer describes.

## When to use (triggers)

- A checker reports clean and you have a concrete case it should have
  flagged. Read its PREDICATE before you doubt the input.
- A predicate compares one number against a bound, and that number was
  produced by accumulating several deltas.
- The bound is a *boundary of a container*: a directory tree, a buffer, an
  allocation, an account that may not go negative, a privilege floor, a rate
  window, a stack depth.
- A defect class recurs at site N+1 after being fixed at N sites, and a
  checker for it already exists. That is the signature: the checker is
  sound-looking and unsound.
- Reviewing anything that folds path components, applies a diff/patch series,
  replays a transaction log, or simulates a sequence of state changes.

**When NOT to use:** a quantity whose only consumer reads the final value and
where intermediate states are unobservable — there the endpoint *is* the
trajectory. Not for deciding what the bound should be
(`verdict-carries-its-threshold`). Not for a check nobody runs at all
(`unrun-checker-latency`, `named-is-not-invoked`) — this skill is about a
check that DOES run and answers the wrong question.

## Steps

1. **State the property in words before you look at the code.** "This path
   must never name anything outside the tree" is a claim about every
   intermediate state. "This path must end inside the tree" is a claim about
   one. Write the one you actually mean down first; the code will usually
   turn out to implement the other.

2. **Find the fold.** It looks like an accumulator: `level += delta`,
   `base = base - 1`, `total += x`, or a `reduce`. If the accumulator is
   returned and compared once, you have the endpoint rule.

3. **Carry the extremum in the same fold.** One extra variable, threaded
   everywhere the value is:

   ```python
   def component_delta(text):
       """(net, floor) — floor is the running minimum, and it decides."""
       delta = floor = 0
       for part in text.split("/"):
           if part in ("", "."):
               continue
           delta += -1 if part == ".." else 1
           floor = min(floor, delta)
       return delta, floor
   ```

   Every operation must fold both: `dirname` is
   `(v - 1, min(f, v - 1))`, a join is
   `(v + d, min(f, v + d_floor))`. Missing one operation reintroduces the
   bug on exactly the inputs that use it.

4. **Carry it through BINDINGS, not just expressions.** If `REG` is bound to
   an out-of-bounds value, every later `join(REG, ...)` is a second finding,
   not a fresh start from zero. A per-expression check that resets at each
   assignment reports the defect once and blesses all its uses.

5. **Decide on the extremum, report BOTH.** The floor is the finding; the
   endpoint is what tells a reader where the thing landed. Print
   `floor -2 (ends at level 1)` — a reader given only "floor -2" cannot tell
   a `../..` from a `../../../a/b/c`.

6. **Re-run over your whole corpus and read the delta, not just the count.**
   Going from 0 findings to N is the expected outcome, not a bug in the new
   rule. Classify all N: which are true positives you now must fix, which are
   already-guarded exemptions, which are new false positives the endpoint
   rule was accidentally suppressing. If the count does NOT move, prove the
   rule changed with a unit test on the fold itself.

7. **Check that the guards still push the right way.** An unknown component
   that counts +1 to stay conservative about the endpoint is *also*
   conservative about the floor, because +1 can only raise a running
   minimum. A guard that subtracts on unknown input would be conservative
   for neither. Say which direction each guard pushes, for both numbers.

8. **Pin the fold in a test, not just the verdict.** `assert
   component_delta("../../state") == (1, -2)` fails the moment someone
   simplifies back to the endpoint rule — even on a corpus that is clean, and
   a clean corpus is exactly when such a simplification looks safe.

## Pitfalls

- **A clean report from an unsound predicate is worse than no report.** It
  gets cited. This repo has a real instance: a round quoted "the tree has no
  unguarded escape" as a fact while the engine that depends on it had been
  dead for rounds.
- **The final value can be worse than wrong — it can be undefined.** After
  the boundary is crossed, further arithmetic describes nothing. Do not
  report it as if it located the object.
- **Same shape, other domains.** Balance never below zero (a day that dips
  and recovers still bounced); a buffer offset that goes negative and comes
  back; a privilege that is dropped and re-raised; a rate limit whose window
  peaked mid-interval; a patch series where an intermediate commit does not
  build. All of them have an endpoint check somewhere.
- **The maximum is the same skill.** Quotas, capacities and depth limits want
  the running MAXIMUM against an upper bound; nothing here changes except
  the sign.
- **Do not widen the rule to "any use of `..` is a finding".** The floor rule
  is exact, not merely stricter: `join(HERE, "tests", "..", "examples")`
  floors at 0 and is genuinely fine. A rule that over-reports gets
  uninstalled, and then you have no check at all.
- **The old rule's findings are a biased sample.** Both cases that motivated
  the endpoint rule ended negative — which is precisely why it looked
  adequate. Ask whether your validating examples share the property that
  makes the weak rule work.

## Verification

- [ ] A unit test asserts the fold's `(net, extremum)` pair directly, on a
      case where the two DISAGREE, so the endpoint rule cannot be restored
      silently.
- [ ] A test asserts a boundary-touching-but-legal case is NOT a finding
      (the rule is exact, not just stricter).
- [ ] The extremum is threaded through every operation in the fold, including
      variable bindings, and there is a test for the binding case.
- [ ] The corpus was re-scanned and the full delta classified — true
      positives fixed, exemptions still exempt, false positives named.
- [ ] The report prints both numbers, and the human-readable line says which
      one decided.
- [ ] The write-up says what the OLD rule's verdict was on the same corpus,
      so nobody reads the new count as a regression.

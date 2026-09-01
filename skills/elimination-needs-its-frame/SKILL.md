---
name: elimination-needs-its-frame
description: Use when a diagnosis is about to publish a claim produced by NARROWING — "the bug is in one of these two files and nowhere else", "the only remaining instance is X", "no other caller does this" — or when reading such a claim and deciding whether to trust it. Symptoms: the words "and nowhere else", "and nothing else", "the only", "by elimination", "must therefore be"; a candidate list built by ls, a glob, memory or a scope quoted from prose rather than read off the thing that produces the symptom; N failures assumed to be N independent causes; probes run one at a time after a fix landed, without re-running the whole thing first. Covers deriving the frame from the artefact's own argv/config/manifest, reconciling it against a published total, the aggregator that duplicates its children, and publishing the frame beside the claim. NOT for ordinary bisection, where the frame is the whole history and every step is re-measured, and not a rule against narrowing — narrowing is fine, unpublished frames are not.
---

# Elimination needs its frame

Narrowing produces the most confident sentence in any bug report — *"so it
is in one of these two files, and nowhere else"* — and it is the only kind
of sentence whose truth depends entirely on something the reader cannot
see. A positive finding carries its own evidence: here is the line, here is
the failure. A negative or exhaustive finding carries none. What it rests
on is the **frame**: the set of candidates the narrowing ran over. Get the
frame wrong and every step of the elimination can be correct while the
conclusion is false.

The frame is almost never wrong on purpose. It is wrong because it was
built from something *near* the artefact instead of *from* it — the
directory the test files are in rather than the argv the runner passes, the
tests you remember rather than the ones that ran, `state/` rather than the
two globs the check was specified over.

## Trigger conditions

- **A conclusion contains "and nowhere else", "and nothing else", "the
  only", "no other", "must be", "by elimination", "narrowed to".** These
  are frame claims wearing the clothes of findings.
- **The candidate list was produced by a convenience.** `ls`, a glob you
  typed, "the files I know about", a scope quoted from an earlier round's
  prose. Ask: *what does the failing thing itself say its inputs are?*
- **N symptoms are being treated as N causes.** Three red tests, three
  hypotheses. Before spending a probe each, ask which of the three are
  downstream of the others.
- **You are about to narrow further after landing a fix**, without
  re-running the whole thing.
- **A published inventory** — "the true remaining set is …", "after this
  round the only open instance is …". Same shape, longer half-life,
  because the next round inherits it as fact.
- Proven on: round 428 of this program, twice in one round. Both claims
  were wrong, both were inherited by the next round as premises, and both
  cost real probe time to unwind.

## Steps

1. **Write the claim down in its exhaustive form before you believe it.**
   "The third failure is in `test_corpus_check.py` or `test_trigger_eval.py`,
   and nowhere else." Now it is checkable, and the next step is obvious.

2. **Derive the frame from the artefact that produces the symptom, never
   from a proxy.** The artefact names its own inputs — read them:
   - a failing tier → the runner's **argv** (`checks()`, the CI job's
     `run:` block, the Makefile target), not the directory you found the
     tests in;
   - a checker's corpus → the checker's own **glob constant**, not the
     folder you remember it scanning;
   - "no other caller" → `git grep` over the **whole** repo plus generated
     and vendored trees, not the package you are editing;
   - a config-driven system → the **merged, effective** config, not the
     file you opened.
   Checkable outcome: you can point at the line of code or config the frame
   came from.

3. **Reconcile the frame's size against a number the artefact already
   publishes.** This is the cheap, decisive check and it takes one command.
   A suite that reports `834 collected` and a frame that sums to 741 is a
   93-item hole, and you know that *before* you spend a probe. Any total
   works: file counts, row counts, a coverage denominator, a checksum.
   Checkable outcome: two independently-obtained totals, and they agree.

4. **Ask whether the symptoms are independent before eliminating over
   them.** Aggregators lie about their arity. A meta-check that reddens
   when any of its children errors contributes one failure per run no
   matter how many real defects exist; a smoke test downstream of a unit
   test fails for the unit test's reason. Classify each symptom as *root*
   or *derived* first, and eliminate only over the roots.
   Checkable outcome: for each symptom, the sentence "this is red because
   ___" names either a defect or another symptom.

5. **Re-run the whole thing after any fix, before narrowing again.** A fix
   that closes one symptom may close three. Probing a suspect list built
   before the fix is measuring a tree that no longer exists — and the
   worst case is not wasted time, it is concluding "the cause is somewhere
   else" about a symptom that no longer occurs.

6. **Publish the frame beside the claim, in the same sentence.** Not "the
   failure is in one of these two files" but "the failure is in one of
   these two files *of the eleven that `checks()` runs, which I enumerated
   from its argv*". A frame nobody can see is a frame nobody can correct,
   and the next reader inherits the conclusion without it.

7. **When the frame cannot be completed, say what is outside it.** "I
   probed 7 of 11; the other 4 exceed my time budget" is a usable result.
   "…and nowhere else" from the same evidence is not. Silent truncation
   reads as coverage.

## Pitfalls

- **`ls` is not the frame.** The directory holds what somebody put there;
  the argv holds what runs. Round 428 enumerated
  `skills/skill-authoring/scripts/` by directory listing and concluded
  "nowhere else"; `corpus_check.py`'s `unit_tests` entry passes **two**
  directories to pytest, and the 93 tests of the second one were outside
  the frame the whole time. The two lines of code that would have settled
  it were in the file being diagnosed.
- **An inventory published without running its own scan.** The
  discriminator can be right and the inventory still wrong. Round 428
  specified a good discriminator for unfilled `_PLACEHOLDER` tokens, named
  the two globs to run it over, published "one instance and nothing else",
  and did not run it. Six instances; five of them in the glob that had
  already been the previous round's omission.
- **N reds counted as N bugs.** Round 428's third failure never existed
  separately: `test_live_corpus_is_clean` invokes the whole checker set and
  reddens when any of them errors, so it was a mirror of the first failure
  — which round 428 had *already fixed*, in its own commit, before going
  looking. Every probe after that was hunting a symptom that was gone.
- **Inheriting a frame from prose.** The next round reads "narrowed to two
  files" as a fact and starts there. Frames rot faster than findings do,
  because the tree moves under them; re-derive rather than re-quote.
- **Confusing "I did not find it" with "it is not there".** Only step 2's
  derived frame licenses the second sentence. Without it, an empty search
  result is evidence about your search.
- **Over-applying this to bisection.** Ordinary `git bisect` is elimination
  with an honest frame — the whole history — and re-measures at every step.
  The rule is about frames you *chose*, not frames the tool computed.

## Verification

```
python3 -c "
import sys; sys.path.insert(0, 'skills/skill-authoring/scripts')
import corpus_check, os
names = [n for n, _ in corpus_check.checks(os.path.abspath('.'))]
argv = dict(corpus_check.checks(os.path.abspath('.')))['unit_tests']
print(len(names), 'checkers;', len([a for a in argv if os.path.isdir(a)]), 'test dirs')"
# expected: the frame read off the artefact rather than off the filesystem —
# TWO test directories, which is the fact round 428's elimination missed.
# The checker count will drift and is printed, not pinned.
python3 -m pytest -q --collect-only skills/skill-authoring/scripts skills/session-inheritance-audit/scripts
# expected: one `N tests collected` total. Step 3 is this number reconciled
# against the per-file sum; a gap between them IS the missing frame.
```

- [ ] The exhaustive claim is written out, in the words "and nowhere else"
- [ ] The frame cites the line of code or config it was derived from
- [ ] Two independent totals agree on the frame's size
- [ ] Every symptom is labelled root or derived before any elimination
- [ ] The suite was re-run after the last fix, before the last narrowing
- [ ] Anything outside the frame is named, not omitted

## Related

- [[derived-subject-set]] — the same move one layer down: an anti-rot
  *test* whose left-hand side is a hand-written literal instead of the
  artefact. That skill fixes standing checks; this one fixes the one-off
  reasoning a diagnosis does out loud. If your frame keeps going stale,
  the fix is probably to derive it there, permanently.
- [[replay-scope-is-read-scope]] — a history replay silently substitutes
  the commits, tree and checkers it happens to use for the ones that
  matter. That is this failure with a time axis.
- [[zero-rate-needs-a-distance]] — a zero is not a bound. Same family: an
  empty result set and an empty candidate set both need something said
  about what would have shown up.
- [[cause-needs-a-denominator]] — step 3's reconciliation is that skill's
  denominator applied to a candidate set instead of to a rate.
- [[rerun-before-you-record]] — step 5, generalised: what you record has
  to be about the tree that exists when you record it.

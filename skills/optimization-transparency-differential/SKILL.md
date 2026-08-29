---
name: optimization-transparency-differential
description: Use when a system has a fast path that is SUPPOSED to be unobservable — tail-call elimination, memoization or caching, inlining, constant folding, batching, a compiled path beside an interpreted one — and the question is whether it really is. Symptoms: optimized and unoptimized runs give the same answer but a different error message; a test that strips a line number, timestamp or id before comparing two paths; a differential suite comparing several optimized modes against EACH OTHER; behaviour depending on where a call sits syntactically rather than what it computes; two plausible orderings for one rule and no tiebreaker. Covers stating the transparency claim as an observable set, a line-aligned un-optimizing source transform, exhaustive family enumeration, using a second independent definition of the system (reference implementation, self-hosted evaluator, spec) as tiebreaker, and pinning what existing oracles are blind to. NOT for benchmarking speed or for bugs on a single code path.
---

# Optimization-transparency differentials

An optimization that "does not change behaviour" is a claim, and it is almost
never written down precisely enough to test. The bug this finds is not "the
fast path computes the wrong value" — that gets caught. It is "the fast path
computes the right value and attributes it to the wrong thing", which no
oracle comparing optimized modes to each other can see.

## Trigger conditions
- A codebase has an optimization asserted to be semantics-preserving: TCO /
  tail-call merging, memoization, an inline cache, constant folding, a
  compiled-vs-interpreted path, incremental vs clean build, batched vs
  per-item processing.
- An existing differential compares N *optimized* variants against each other
  (fast vs direct vs trampoline; two cache tiers; two backends).
- A test strips a field — line number, timestamp, id, path, ordering — before
  comparing two paths, or a comparison oracle documents an "exempt" field.
- Behaviour depends on syntactic position, arrival order, or batch boundary
  rather than on the computation.
- Two plausible rules are both defensible and the choice was made on
  "it preserves the current output".
- Proven on: Whence v0.13 `-> Type` return contracts under tail-call merging
  (`languages/whence/`, rounds 335→336): 1740 of 2325 tail/lifted program
  pairs disagreed; 0 after.

## Steps
1. **Write the transparency claim as an observable set, before any test.**
   Two lists, explicit: what MUST be identical (value, error identity, error
   text, source position, exit code, emitted events, order of effects) and
   what is ALLOWED to differ (wall time, frame count, peak memory, allocation
   counts, internal counters). Anything not on either list is an unresolved
   question, not a free pass. Whence's went into the spec as a numbered
   decision: "tail position changes space, never meaning."
2. **Build the un-optimizing transform as a source-to-source edit of the
   SAME program, and keep it line-aligned.** The smallest edit that disables
   the optimization without changing what the program computes — for TCO,
   bind the call to a temporary and return it (`{ let t = f()  t }`, on ONE
   line so every later line keeps its number). A flag that turns the
   optimization off inside the implementation is worth less: it tests the
   flag, and it cannot tell you what the language *means*.
3. **Enumerate the family exhaustively, not randomly.** These bugs live in
   combinations (which frames are annotated, which contracts are violated,
   how deep the chain is). The space is usually small enough to close:
   Whence's was `hops ∈ {2,3,4} × 5 annotations^hops × 3 terminal values` =
   2325 programs in 2.6s. Random sampling finds the same bug slower and
   proves nothing about the rest.
4. **Compare the whole observable output, byte for byte.** If a field has to
   be stripped to make the comparison pass, STOP: the stripped field is a
   second finding. Round 335 wrote exactly this oracle for one program and
   stripped the line number to make it green; the line number was the other
   half of the bug, and 612 of the 1740 divergences were line-only.
5. **When two orderings are both defensible, find a second independent
   definition of the system and let it decide.** In order of authority:
   a self-hosted/metacircular implementation, a reference interpreter, the
   written spec, and the *unoptimized path that already exists in the same
   codebase*. Whence had all four and they agreed: the self-hosted evaluator
   has no tail-call merging at all, so its per-frame check order IS the
   inside-out answer; non-tail recursion in the host had behaved that way
   since the feature shipped. "The current order preserves every existing
   message" is a migration argument, not a semantic one — when it conflicts,
   the reference wins and the messages change.
6. **Name what each existing oracle is structurally blind to, and pin it as
   a passing test.** An N-way differential between optimized modes cannot see
   a bug all N share. A differential that exempts a field cannot see a bug in
   that field. Keep a test that passes on BOTH the old and the new build,
   commented as the record of that blindness, so the next round does not
   mistake it for coverage.
7. **Quantify against both builds.** Run the differential against the
   pre-fix implementation (a pristine copy of the package with the old file
   dropped in is enough) and report N-before → N-after, split by which part
   of the observable set diverged. "It was broken" is not a finding; "1740 of
   2325, of which 1128 in the message text and 612 line-only" is.
8. **Measure the cost against a control whose code path you did not touch.**
   Interleave runs of the two builds in fresh processes and report the
   control's own run-to-run spread as the noise floor. If the control varies
   more than the changed case, say that instead of quoting a delta.

## Exact commands
```bash
# 7. two pristine package copies, old vs new implementation file
rm -rf /tmp/wpre /tmp/wpost
cp -r pkgdir /tmp/wpost && cp -r pkgdir /tmp/wpre
git show HEAD:pkgdir/pkg/hotfile.py > /tmp/wpre/pkg/hotfile.py
find /tmp/wpre /tmp/wpost -name __pycache__ -type d -exec rm -rf {} +
python3 differential.py /tmp/wpre     # N divergences (before)
python3 differential.py /tmp/wpost    # 0             (after)

# 8. interleaved cost, fresh process each run, min-of-3 inside
for i in 1 2 3 4; do
  echo -n "post: "; python3 bench.py /tmp/wpost
  echo -n "pre : "; python3 bench.py /tmp/wpre
done
```

## Pitfalls
- **Stripping the field that disagrees.** The single most common way this
  oracle gets written and neutered in the same commit. Strip nothing; if the
  two forms cannot be laid out to make a field comparable, make them
  comparable (line-align the transform) rather than dropping it.
- **An identity/equality dedup silently choosing WHICH duplicate survives.**
  Fine while the entries are interchangeable; the moment order or labelling
  matters it is a semantic, not an optimization. Keep the occurrence the
  semantics names — Whence had to move a repeated entry to the END of its
  list (innermost wins) instead of keeping the first.
- **An early exit that skips work "because it is the same as the outer one".**
  Same *check*, different *origin*: skipping it hands one frame's blame to
  another. Test identity on the thing the fast path actually needs to be
  equal (the spec), not on the thing you are about to report (the label).
- **Believing an N-way differential covers this.** Whence ran a three-way
  fast/direct/trampoline differential on every call-path change for ~200
  rounds; all three modes shared the bug identically, so it was invisible by
  construction.
- **Position/location is part of the observable set** for anything with source
  spans, stack traces or log lines — an error pointing at the outer call site
  instead of the one that produced the bad value is a real defect, not
  cosmetics.
- **Comparing only failing runs.** Count how many of the family take the
  SUCCESS path and say the number; if it is zero the differential only tests
  the error path and cannot catch a fix that introduces a false failure.
  (Whence's: 351 of 2325.)
- **The unoptimized form drifting into a different program.** It must differ
  only in what disables the optimization: same names, same arity, same
  literals, same line count.

## Verification
- The differential must fail on the pre-fix build and pass on the post-fix
  build; run both, quote both numbers. Whence: 2325 linear chains 1740 → 0,
  150 mutual-recursion loops 96 → 0, in all three evaluation modes.
- Every hand-written case added alongside it should also fail pre-fix. Whence:
  13 of the round's new/edited tests fail against the old interpreter.
- The full suite runs clean afterwards, and the count moves by exactly the
  number of tests added.
- The "blind oracle" test from step 6 passes on both builds — verify that,
  do not assume it.

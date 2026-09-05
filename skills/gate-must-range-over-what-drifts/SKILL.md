---
name: gate-must-range-over-what-drifts
description: Use when a DERIVED artefact committed to the repo — a census, ledger, roster, lockfile, golden file, coverage baseline — has a test or `--check` verb guarding it, and you want to know whether that guard can see it age. Symptoms - a generated file is stale for many commits, caught only when a change happens to disturb the one field the gate reads; a `--check` verb exits 0 while the artefact disagrees with its source; one input change reddens several tests naming different regeneration commands; headline totals printed everywhere and compared to nothing; an assertion compares two values both derived from the same stale artefact, so they agree at the wrong value. The move is to compare what the gate's predicate RANGES OVER against what DRIFTS, then replace subset predicates with the one total by construction — re-run the artefact's own declared generator and byte-compare. Covers sandboxing a generator command naming its own output, separating STALE from ERROR, and proving drift with a synthetic corpus.
---

# A gate is only as good as what its predicate ranges over

A derived artefact — something generated from the tree and committed beside
it — always arrives with a guard. Somebody writes `--check`, or a test that
compares the artefact to a fresh computation. The guard is real, it runs
every round, and it is green.

Then the artefact turns out to have been wrong for months.

The mistake is not laziness and it is not a missing test. It is that **the
guard's predicate ranges over a proper subset of what drifts.** A census of
1000 files whose gate compares only the 57 "interesting" rows is blind to
every change in the other 943. It is not a weak check of the artefact; it is
a *complete* check of a fragment, and nothing anywhere says which fragment.

The tell is that such a gate does eventually fire — which is why nobody
suspects it. It fires when a change happens to touch the subset, so it looks
like a working alarm that just went off for the first time. It is really a
smoke detector wired to one room.

## Trigger conditions

Any one of these:

1. A repo contains a **generated** file (`*-census.json`, `*.lock`,
   `golden/*`, a coverage baseline, a roster) that a human is expected to
   regenerate after certain edits, and the "certain edits" are described in
   prose rather than computed.
2. A `--check` / `--verify` / `--audit` verb **exits 0** and you have not
   personally confirmed its predicate covers the whole artefact. Run it
   against a deliberately stale copy before believing it.
3. **One cause produced several reds in several files.** N tests naming M
   different regeneration commands is the signature of N partial gates where
   one total gate belongs.
4. An artefact carries **headline totals** (`files: 72`, `asserts: 3908`)
   that get printed in CLI output and quoted in documents. Ask what compares
   them. Often: nothing.
5. An assertion compares **two values that are both derived from the same
   artefact** (`assert [len(rows), ledger["total"]] == [57, 57]`). A stale
   artefact makes both sides agree at the stale value, so the node is green
   *because* it is stale.
6. You are about to fix a stale artefact by regenerating it. Do the audit
   first — a companion artefact is very likely stale too, and it will not be
   the one that went red.

## Steps

1. **Reproduce solo before diagnosing.** Run the failing nodes alone, on one
   core, with nothing else going. A red attributed to "flaky under
   concurrency" that reproduces in 36 seconds solo is a stale artefact, and a
   red that vanishes solo is a different problem entirely. Record the
   command and the timing.

2. **Inventory every derived artefact, not just the one that went red.** For
   each: what generates it, when was it last regenerated (`git log -- <path>`
   is enough), and what gates it.

3. **For each artefact, write down two sets side by side.**
   - *drifts*: what inputs can change its content (usually "any file under
     `<dir>`").
   - *ranges over*: what the gate's predicate actually reads.

   Where the second is a proper subset of the first, the gap is the blind
   spot, and its size is the number of rounds the artefact can age
   undetected. Include the artefacts that are **fresh** — they are your
   control. If some artefacts in the same tree, by the same authors, never
   drift, the cause is structural rather than cultural.

4. **Measure the staleness rather than asserting it.** Regenerate each
   artefact into a **temp path** and compare against the committed copy.
   Never regenerate in place at this stage: you are collecting evidence, and
   an in-place regeneration destroys it.

5. **Replace the subset predicates with the one that is total by
   construction:**

   > the artefact is FRESH iff re-running its own declared generator
   > reproduces it **byte for byte**.

   This needs no understanding of what the artefact means, cannot drift out
   of step with the generator because it *is* the generator, and is total in
   every input by definition.

6. **Verify byte-determinism first — it is the precondition.** Run every
   generator twice at a fixed commit and compare. A generator that embeds a
   timestamp, a hash seed, or a set iteration order makes byte-comparison
   report STALE forever; you must fix the generator or compare parsed
   structures instead. Bank this check *before* building on it.

7. **Read the regeneration command out of the artefact, not out of your new
   module.** A hand-typed table of `{artefact: command}` is one more thing
   that goes stale — the exact defect you are fixing. Prefer a
   `_regenerate` / `_generated_by` field the generator itself writes. Where
   a generator cannot self-declare (because it dumps a computed *view*, so
   any annotation would not survive its own regeneration), keep the entry in
   your module **with the reason recorded**, and make an unclassified
   artefact a hard failure rather than a silent skip.

8. **Sandbox the command, or refuse to run it.** A declared command very
   often names its own real output path. Executed verbatim to "check
   freshness" it **overwrites the file under test and reports fresh every
   time** — a check that cannot fail. Rewrite the output token to a temp
   path, and require **exactly one** substitution: zero means the check is
   vacuous, two means you cannot tell which is the output. Refuse both
   rather than guessing.

9. **Keep STALE and ERROR apart.** "The artefact is out of date" and "the
   generator crashed" need different responses, and an auto-fix must not
   touch an ERROR row — a stale artefact is strictly better than a truncated
   one.

10. **Prove the check detects drift, with a synthetic corpus.** Build a tiny
    corpus, a tiny generator and a tiny artefact in a temp dir. Assert:
    fresh reads FRESH; adding one input turns it STALE *and names what
    appeared*; the fix closes it and is idempotent; a crashing generator is
    ERROR and is left alone. Without the first of those, a checker that
    returned STALE unconditionally would pass the drift test.

11. **Do not make it a blocking gate by default.** Exit 0 on staleness
    unless `--strict`. A check that can stop the round that would fix it is
    a trap. Let the test node carry the red, and make its message the exact
    one-command fix.

## Pitfalls

- **Regenerating in place before you have measured.** You lose the evidence
  of how long it was stale and how far it had drifted, which is the finding.
- **Fixing only the artefact that went red.** In the program this comes
  from, one red artefact was accompanied by two more that were stale, one of
  them with no red anywhere and a `--check` verb printing `0 finding(s)`.
- **Trusting a usage string over the parser.** A declared command that
  *looks* malformed against the documented flags may parse fine (optional
  values, membership-guarded arguments). Run it before calling it broken.
- **Predicting an instrument's behaviour from its stated purpose.** What it
  is *named for* and what its predicate *ranges over* are different things,
  and only the second is load-bearing. This is the same error as the bug —
  one level up. Read the predicate; it takes a minute.
- **Assuming a directory-scan dependency map will catch it.** A map keyed on
  "which node listed this directory" over-approximates badly for an ADDED
  file: every hit is a scan hit, because no read-set can name a file that
  did not exist when the map was recorded. Refine with "…and reads a
  generated artefact keyed on that directory", at FILE granularity — nodes
  that share a module-scoped fixture record their reads on whichever node
  ran first.
- **Exempting your own new file from the corpus it reports on.** A gate over
  a directory that skips itself is blind to exactly one file. Declare your
  own contribution like any other, and regenerate *after* writing it.
- **A byte-comparison against a non-deterministic generator.** It reports
  STALE forever, gets marked flaky, and then gets deleted. Check step 6
  first.

## Verification

Against `languages/whence/` in this repo:

```bash
cd languages/whence

# 1. the registry — every derived artefact is classified, gaps are NAMED
python3 corpusledger.py --list

# 2. the total predicate, on the real tree. Should be all FRESH + one SKIP
python3 corpusledger.py --check --strict; echo "rc=$?"

# 3. THE property that makes the check non-vacuous: checking a ledger whose
#    declared command names its OWN path must not rewrite it
md5sum ../../state/whence/subject-provenance.json
python3 corpusledger.py --check --only subject-provenance.json >/dev/null
md5sum ../../state/whence/subject-provenance.json   # must be unchanged

# 4. byte-determinism, the precondition of the whole design
python3 assertshadow.py --history --json /tmp/a1.json
python3 assertshadow.py --history --json /tmp/a2.json
cmp /tmp/a1.json /tmp/a2.json && echo deterministic

# 5. the synthetic controls: drift is detected, named, fixed, idempotent,
#    and a crashing generator is ERROR rather than STALE
python3 -m pytest -q tests/test_corpusledger.py
```

It is working when step 2 exits 0 while step 1 still prints its
`not generated` / `declared here` rows as named gaps rather than hiding
them; step 3's two hashes match; and step 5 passes
`test_an_addition_to_the_corpus_turns_the_synthetic_ledger_stale`,
`test_a_generator_that_fails_is_an_ERROR_and_not_a_stale_verdict` and
`test_checking_a_self_naming_ledger_does_not_rewrite_it`.

To see it *fail* on demand — the check that the gate is not vacuous:

```bash
# add a file to the corpus and watch ONE node redden with the exact fix
touch languages/whence/tests/test_zz_probe.py
cd languages/whence && python3 corpusledger.py --check   # -> STALE, names the file
rm tests/test_zz_probe.py
```

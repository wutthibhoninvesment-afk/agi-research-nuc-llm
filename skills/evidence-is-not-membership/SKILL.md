---
name: evidence-is-not-membership
description: Use when ONE declared artefact — a frozen census, a golden baseline, an approved-list JSON, a snapshot fixture, a signed manifest — is both the RECORD OF A PAST MEASUREMENT and the LIVE SUBJECT SET some code selects from. Symptoms: a file whose own comment says "frozen" or "do not edit" that a test now needs updated because the population grew; a rule elsewhere citing that file by path as the reason an entry is allowed; a drift or coverage check that goes red when a new member arrives and whose only fix is to bump a count inside the frozen file. The move is to SPLIT it — frozen evidence that is cited, live membership that is re-declared — after measuring what the new member would change, then pin the seam with a test that fails when a member outside the evidence would actually move it. NOT for a hand-written list that should be derived (derived-subject-set), a hard-coded date over a growing log (expiring-fixture-window), or a suppression with several readers (suppression-has-many-readers).
---

# A file cannot be frozen and current at the same time

Two questions get asked of the same JSON, and they look alike enough that
one file answers both for a long time:

* **What did we measure?** — *these 14 files, at these md5s, produced these
  counts.* The answer must be FROZEN, because something downstream cites it
  as the reason a decision was allowed.
* **What is the population now?** — *which files are the corpus.* The answer
  must be LIVE, because every "for all members" assertion is about it.

While the population does not change, the two answers are the same bytes and
nothing is wrong. The bug is not present, it is **latent**, and it is
detonated by the first new member. At that moment the only way to fix the
selector is to edit the evidence, and the edit is invisible in review: it is
a count going from 14 to 15 in a file everybody expects to be boring.

The asymmetry that decides it: **evidence ages into history and stays true;
membership ages into a lie.** A census taken in round 384 is still a true
statement about the files it censused, forever. A subject set from round 384
is simply wrong the moment a file arrives.

## The measured instance (round 444)

`state/whence/round-384/field-names.json` recorded every identifier used by
14 machine-written Whence programs that no `let`/`fn` in the same file
binds. `whence/foreign.py`'s entry rule cites it BY PATH:

> A name enters only if **(a)** the FROZEN field census
> `state/whence/round-384/field-names.json` attests it … or **(b)** a
> numbered SPEC decision rejects the construct it names.

`FOREIGN_NAMES["println"]` exists because that file says 34 occurrences in
9 of 14 programs. Eleven rounds later the same file was made the SELECTOR
(`field_census_names()` → `field_programs()`), because the previous selector
— untracked-ness — had silently gone empty. Good fix, and it put a live
question onto a frozen answer.

A fifteenth program arrived 49 rounds after that. The drift test went red,
correctly. The whole visible fix was `n_files: 14 → 15` in a file whose own
comment reads *"Frozen on purpose … a test that re-derived this census would
be pinning a live file."*

What made the split cheap rather than arguable was measuring the delta
first: the new member had **zero** unbound identifiers, so it attested
nothing, so the evidence did not need to move at all — only membership did.
Splitting cost one new JSON, one renamed accessor, and three tests.

## When to use

- A file named `*-baseline.json`, `*-census.json`, `golden-*`, `approved-*`,
  `*-snapshot`, `manifest.*`, whose comment or docstring says frozen /
  captured / do not edit, and which some selector reads to decide *which
  things to iterate over*.
- A rule, docstring, ADR or comment that names a data file BY PATH as the
  justification for an entry somewhere else ("allowed because X attests
  it", "grandfathered per the Y snapshot").
- A drift / coverage / completeness check whose red can be cleared by
  editing a count inside a file that is described as immutable.
- Test-suite symptom: `test_the_frozen_thing_says_what_it_says` and
  `test_the_population_is_N` read the same file and one of them must now
  change.
- You are about to write "re-take the baseline" as a task, and the baseline
  is cited elsewhere as evidence.

### NOT this skill

- The list is hand-written and should simply be **derived** from the
  artefact → `derived-subject-set`.
- The staleness is a hard-coded DATE over an append-only source →
  `expiring-fixture-window`.
- The file is a suppression list with several consumers →
  `suppression-has-many-readers`.
- One guard returning one reason for several distinct states →
  `skip-reason-is-a-claim`.
- A prose claim copied forward each cycle without re-derivation →
  `carried-claim-rot`.

## Steps

1. **Name the two questions out loud, in the file's own words.** Quote the
   comment that says frozen, and quote the code that uses it as a selector.
   If you cannot produce both quotes, this is not the pattern — stop.
2. **Find every citation of the file BY PATH**, not by variable:
   `git grep -n "$(basename "$FILE")"`. A rule that cites a path is the
   evidence side and is the reason freezing is load-bearing.
3. **Measure the delta the new member would make to the EVIDENCE**, before
   deciding anything. If the artefact has no generator, reconstruct one and
   validate it by EXACT reproduction of the frozen numbers over the frozen
   inputs — key set and values, not a spot check. A generator that agrees on
   the headline number can still disagree everywhere else.
4. **Branch on that measurement, and record it either way.**
   - Delta empty → membership-only change. Write the new live file, leave
     the frozen file untouched, repoint the selector.
   - Delta non-empty → you need a NEW evidence capture, cited by
     round/date/commit, and the old one still stands as history. Never
     mutate the cited file.
5. **Repoint the selector and rename the accessor.** Leaving the membership
   function called `census_names()` re-creates the conflation in the name,
   which is how the next round re-merges them.
6. **Pin the seam.** One test that fails when a member outside the frozen
   evidence would actually change it — "every member the evidence has not
   seen contributes nothing new" — and whose failure message says *capture a
   new evidence file*, not *update this number*.
7. **Keep the frozen file's own integrity test unchanged.** It should still
   assert the old round and the old count. If that test had to move, the
   split did not happen.

## Pitfalls

- **Bumping the count "because it is obviously the same thing".** The count
  inside cited evidence is a claim about what was measured. Changing it
  retroactively rewrites why every downstream entry was allowed.
- **Reconstructing the generator and accepting "close enough".** Round 384's
  census has 80 keys; a binder rule that mishandles `fn` parameters
  reproduces `println: 34` and gets a dozen others wrong. Demand exact
  equality on the whole payload, over the same inputs.
- **Believing an old "we deliberately did not build this".** Round 384's
  reason for shipping data with no generator ("a test that re-derived this
  would be pinning a live file") was correct and EXPIRED fifteen rounds
  later when a skip-guard for exactly that hazard landed. An absence carries
  a reason, and reasons expire like claims do. Re-read it before quoting it.
- **Splitting and leaving both files writable by the same code path.** Only
  one function should open each file, and each path should be spelled once.
- **Landing the split without an ordering rule for downstream housekeeping.**
  If a suppression (`.gitignore`, allowlist) will follow, it lands WITH or
  AFTER the declaration, never before — otherwise the report goes green by
  hiding the member rather than by declaring it.
  (`suppression-has-many-readers`.)
- **Assuming the new member is boring.** Measure it. In the instance above
  the new member turned out to be the only one of fifteen that used the
  language's assertion construct at all, and the only large one with no
  foreign idioms in it — a finding about the upstream producer that nobody
  was looking for and that fell out of the delta measurement for free.

## Verification

You have done this when all of these hold:

1. Both quotes from step 1 appear in the commit message or the artefact.
2. The frozen file's own integrity test is UNCHANGED and still green.
3. The generator reproduces the frozen payload exactly, and that
   reproduction is a test, not a transcript.
4. The delta measurement for every member outside the evidence is recorded,
   and is a test that goes red when it stops being empty.
5. The selector's accessor no longer carries the evidence file's noun.
6. The live check that was red is green, and you showed it going green from
   the DECLARATION alone — before any suppression was added.

```bash
# 1. the two questions, in the file's own words
grep -n -i "frozen\|do not edit\|captured" state/whence/round-384/field-names.json
git grep -n "field-names.json"        # every citation BY PATH
# expected: at least one rule citing the path as the reason an entry exists

# 2. the frozen file's integrity test still says the old numbers
cd languages/whence && python3 -m pytest tests/test_v32.py -q -k frozen_census
# expected: 1 passed — round 384, n_files 14, unchanged by the split

# 3+4. the generator reproduces, and the seam is pinned
python3 -m pytest tests/test_field_corpus_selector.py -q \
  -k "reproduces_round_384_exactly or attests_nothing_new or binds_the_three"
# expected: 3 passed

# 5. the accessor was renamed
git grep -n "field_census_names" -- '*.py'
# expected: no hits in CODE — the selector is field_roster_names(). Prose
#           hits in knowledge/ and state/ are history and must stay.

# 6. green from the declaration, not from the suppression
python3 -c "import curecheck as C; print(C.field_corpus_drift())"
# expected: ([], []) — and the round record shows this reading BEFORE the
#           .gitignore line was added
```

---
name: counter-in-the-compared-unit
description: Before comparing two numbers an instrument prints, check they are counted at the SAME stage of its pipeline — a raw-occurrence count set beside a deduplicated, filtered one is not a ratio, it is a category error; and a counter no report ever prints is a counter whose unit nobody can catch. Trigger when a tool prints two counts side by side, when a ratio or percentage is derived from a tool's own stats, when a next-step quotes "N of M" from one instrument, when a counter carries the plural noun of the final artefact but is incremented per event, or when you add a counter to an existing stats dict.
---

# A count is only comparable to a count taken at the same stage

An instrument's pipeline filters. Something is seen, then folded, then
deduplicated, then gated, then kept. **Every stage is a different
population**, and a counter incremented at stage 2 sitting in the same dict
as a counter incremented at stage 5 will be read as comparable, because they
are printed on the same line and share a noun.

The failure is silent and it survives review, because the numbers are each
individually correct. Nothing is wrong except the comparison — and the
comparison is the only thing anybody uses them for.

## When this triggers

* A tool prints two counts side by side, or a report derives a rate,
  percentage or "N of M" from a tool's own stats dict.
* A counter's NAME is a noun for the final artefact (`programs`, `pages`,
  `records`, `findings`) but its increment sits before the gate that defines
  that artefact.
* You are about to quote a carried "the residual is N against a corpus of M".
* You add a key to an existing stats dict, or a stage between two existing
  ones.
* A stats dict has more keys than the report prints.

## Steps

1. **Write the pipeline down as stages, before reading any number.** One
   line per stage, in order, naming what one unit IS at that stage. For a
   source harvester: *call site → candidate argument → folded string →
   deduplicated (src, depth) → parses with ≥1 statement → kept*. You cannot
   place a counter without this list and you cannot spot a mismatch with it.

2. **Place every counter on the list.** Grep for each increment and write the
   stage beside it. This is mechanical and it is where the bug appears.

   ```sh
   grep -n 'stats\["' tool.py | grep '+= 1'
   ```

3. **For each pair of numbers anyone compares, check the stages match.** If
   they do not, the comparison is void — do not "explain" it, re-count the
   earlier one at the later stage. Keep BOTH: the occurrence count is a real
   fact about the input, the gated count is a real fact about the output.
   Name them differently (`parse_only_strings`, `parse_only_distinct`,
   `parse_only_programs`), never one name for two stages.

4. **Make the noun in the name true.** A counter called `..._programs`
   incremented before the gate that decides what a program is, is a lie a
   reader has no way to detect. Rename it or move it. If moving it changes
   the published number, that IS the finding — report the old number, the new
   one, and the stage each was taken at.

5. **Write the accounting identity and assert it in a test.** Every unit
   entering a stage leaves it through exactly one exit. If you cannot write
   the identity, a counter is missing — usually on a silent drop path
   (`if key in seen: continue` increments nothing).

   ```
   strings_folded == parse_only + dup_in_file + unparsed + kept
   kept - dup_cross_file == programs
   ```

6. **Check every counter reaches a report.** List the stats keys, list what
   the CLI prints, diff. A counter nobody prints is a counter whose unit
   nobody can catch — that is how the mis-staged one survived. Pin it:

   ```python
   def test_every_counter_reaches_the_report(stats):
       numeric = {k for k, v in stats.items() if isinstance(v, int)}
       assert numeric == set(REPORT_KEYS)
       text = report(stats)
       for k in REPORT_KEYS:
           assert str(stats[k]) in text, k
   ```

7. **Re-derive any published ratio that used the bad pair.** It is wrong by
   the size of the stage gap, not by a rounding error, and it has usually
   been quoted forward.

## Positive trigger cases

Three, deliberately outside the codebase this rule was found in.

1. **A test runner reports `1 240 passed, 318 skipped`.** `passed` is per
   test *case* after parametrisation; `skipped` is incremented per
   *collection item*, before parametrisation expands it. "20% of the suite
   is skipped" is not a number that exists. Stage list first, then re-count
   skips per case.

2. **A crawler prints `48 219 URLs seen, 6 004 pages indexed`.** `seen` is
   per link occurrence, before canonicalisation and the dedup set; `indexed`
   is after canonicalisation, dedup, robots and the content-type gate. The
   "12% index rate" everyone quotes is a ratio of two different objects.
   Report `urls_seen`, `urls_distinct`, `urls_fetchable`, `pages_indexed`.

3. **A build cache reports `hits: 8 400, artifacts: 1 210`.** `hits` counts
   lookups, including the several per artefact a fan-out graph performs;
   `artifacts` counts outputs. A "hit rate" from these two is a statement
   about graph shape, not about the cache.

## Pitfalls

* **Deleting the earlier-stage counter once you find the mismatch.** It is a
  real fact about the input and usually the only visibility into a stage.
  Add the later one; keep both; give them different names.
* **Fixing the name and not the comparison.** The stale ratio is already in
  a spec, a report or a carried next-step. Grep for it.
* **Assuming the dedup is the only silent drop.** Any `continue` on a filter
  path drops a unit without a counter. Step 5's identity is what finds them;
  reading the code is what misses them.
* **Adding a counter without adding it to the report list.** You have just
  created the next instance of the same bug.
* **Treating a counter with no reader as harmless because it is unused.** It
  is not unused — it is in the JSON artefact, and the next round will quote
  it precisely because no line of prose ever constrained it.
* **Re-counting at the later stage and forgetting the cross-file/global
  dedup.** Per-file distinct summed over files is not global distinct.

## Verification

Run from the repo root. Both commands must exit 0.

```sh
# 1. the identity, the report coverage, and the unit fix are all pinned
cd languages/whence && python3 -m pytest -c pytest.ini -q \
    tests/test_testcorpus_census.py -k "accounting or counter or unit or parse_only"

# 2. the instrument prints every counter it collects, and the string-level
#    accounting closes on the printed line
cd languages/whence && python3 depthcensus.py --tests --harvest-only
```

Expected from (2): a `strings:` line of the form
`N folded = A parse-only + B dup-in-file + C unparsed + D kept; D kept - E
dup-cross-file = P programs`, with `N == A + B + C + D` and `D - E == P`;
and a `parse-only:` line giving occurrences, distinct and programs as three
separate numbers rather than one.

Found in round 468 (`knowledge/round-468-the-counter-that-could-only-be-believed.md`),
where `parse_only_programs` had been printed as 145 against a corpus of 559
for three rounds; in the corpus's own unit it is 25, and 0 of the 141
distinct strings occur in that corpus at all. Companion rule:
`skills/residual-audited-both-ways`.

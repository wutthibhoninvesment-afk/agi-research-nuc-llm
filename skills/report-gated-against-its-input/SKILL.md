---
name: report-gated-against-its-input
description: Use when a committed JSON/Markdown report is a SNAPSHOT of a computation over inputs that keep moving (a ledger, a corpus, a source file, a config table) and the tests over it read only the report. Symptoms; a test that asserts a report's digest field matches the file it names, and nothing else; a report whose counts are quoted in later rounds without re-deriving them; an artefact and the ledger it summarises committed together with different totals; a report naming an instrument's configuration (a battery, a verb list, a threshold table) that the instrument has since changed; a resume ledger that is last-wins, so a re-score silently supersedes the number a report published. The move; every snapshot gets a gate per INPUT — re-ask the report's own question of the live input and assert the answers agree — plus a content-keyed remap when the input's identifiers are positional and an edit renumbers them.
---

# A report is a claim about its inputs. Gate it against them, not against itself.

A committed report is a function of things that keep moving. The tests
written over it almost always read the report — its fields, its internal
consistency, at best a digest of the one input it names. Every such gate
passes forever on an artefact that has quietly stopped being true, because
the artefact and the gate agree with each other by construction.

```
The iron law:  a gate that reads only the artefact
               can only check the artefact against itself.
               For every INPUT the report consumed, re-ask its question.
```

## The measured instance (round 514)

`state/nuc/round-502/survivor-impact.json` — a mutation-survivor impact
report over `nuc/perturbation.py`. Four committed `TestThisTree` gates read
it. One of them, `test_the_committed_report_is_about_the_subject_at_head`,
compared the report's `subject_digest` against `sha256` of the subject; it
went red when round 508 edited the subject and stayed red six rounds.

The other two staleness axes had **no** gate:

| axis | report said | truth at HEAD | gated? |
|---|---|---|---|
| subject digest | `8082749f…` | `3b3923df…` | yes — the red |
| the instrument's battery | 5 verbs | `BATTERY` is 7 | **no** |
| survivors audited | `n_survivors_standing: 32` | **5** at the report's own digest | **no** |

The third is the one that matters. The ledger is last-wins; asked today at
the digest the report itself names, it returns 5. The report and that ledger
were committed **in the same commit**, whose own message reads *"the ledger
goes 55 killed / 32 survived -> 82 / 5"*. It was never true. Twelve rounds of
green tests said otherwise, and all eleven survivors the report called
defects were already dead.

## When this triggers

* A test asserts a report's digest/timestamp field and nothing else about
  the input — that is one axis of a report that usually has three.
* A report and the ledger, corpus or log it summarises are committed
  together, and nobody re-derived the totals at commit time.
* A report names an instrument's *configuration* — a battery of commands, a
  verb list, a threshold table, a model id — and that configuration lives in
  code that other rounds edit.
* The input is APPEND-ONLY and read last-wins, so a later append supersedes
  a published number without touching any file the gate reads.
* A later round wants to re-run the computation and finds the input's
  identifiers are positional (`name:line:op#i`, array indices, line numbers),
  so an edit upstream renumbered them.
* A number from a report is about to be quoted in a new document.

## Steps

1. **List the report's inputs.** Not "the file it names" — everything the
   producing function read. For `survivor_impact.audit` that is: the subject
   source, the mutation ledger, the capture directory, and `BATTERY` /
   `BATTERY_GAP` in the producing module itself. Four inputs, one gate.
2. **Write one gate per input, each re-asking the report's own question.**
   Cheap ones first; they are one-liners:
   ```python
   assert rep["battery"] == [n for n, _ in si.BATTERY]
   assert rep["n_survivors_standing"] == len(
       si.survivors(str(LEDGER), subject_digest=rep["subject_digest"]))
   ```
   Note the second re-runs no measurement. It re-reads a file.
3. **Assert the SET, not only the count.** Two ledgers can agree on 5 and
   name different mutants. Compare sorted ids.
4. **Do not pin the gate at one round's directory.** A pin at
   `state/nuc/round-502/` guarantees the fix cannot be a new artefact: any
   fresh report lands under a new round number the test will never read.
   Resolve the NEWEST `round-*/<name>.json` instead; the gate keeps its teeth
   (the newest still has to be about HEAD) and a later round can fix it
   without overwriting a past round's record.
5. **If the input's ids are positional, remap by content before re-running.**
   Key each item by what it IS — `(op, description, stripped source line,
   owner qualname)` — plus an ordinal within the key bucket. If the bucket
   changed size, emit `ambiguous` and NO id. See `nuc/mutant_remap.py`.
6. **Re-run the producer and commit the new artefact under this round.**
   Leave the old one where it is: it is the record of what was measured then.
7. **Score the gap you just closed.** Say how many rounds each new gate would
   have been red for, had it existed. That number is the finding.

## Pitfalls

* **Overwriting the old report to make the digest gate pass.** It makes a
  past round's record a lie about what that round measured. Write a new one
  and move the resolver.
* **Making the failing gate lenient.** The round-502 gate was correct; it was
  merely alone. Add gates, do not widen them.
* **Re-running the producer without remapping positional ids.** `--only
  <old ids>` against a moved source scores different mutations, or nothing,
  and reports it as a re-score. Round 514 measured the drift: 81 of 87 ids
  changed and the `#i` component drifted +1, +14, +39, +42 down one file.
* **Trusting a cached derived input.** `perturbation-cov-by-test.json` still
  hashed the OLD subject; `MapPrioritizer(require_fresh=True)` would have
  silently downgraded all 87 mutants to the full suite (70 min instead of
  under 2). Re-collect the cache in the same round; it cost 118.9 s.
* **Guessing through ambiguity.** Carrying a `survived` verdict onto an
  unscored mutation is a false negative that looks like good news.

## Verification

```sh
python3 -m pytest nuc/tests/test_mutant_remap.py -q
```
Expected: all pass, including
`test_inserting_a_line_above_moves_every_id_without_losing_a_mutant`,
`test_the_positional_index_moves_too_not_only_the_line`,
`test_a_deleted_line_reports_gone_rather_than_matching_something_else` and
`test_a_key_bucket_that_changed_size_refuses_rather_than_guessing`.

```sh
python3 -m pytest nuc/tests/test_survivor_impact.py -q
```
Expected: all pass, including the two gates this skill is about —
`TestThisTree::test_the_committed_report_names_the_battery_THAT_EXISTS_NOW`
and `TestThisTree::test_the_committed_report_agrees_with_the_ledger_it_READ`.
Both were RED at HEAD before round 514's report was written; check that by
resolving `REPORT` to the round-502 file and running them again.

To see the remap on the live tree:

```sh
python3 nuc/mutant_remap.py --survivors --quiet \
    --out state/nuc/round-514/mutant-remap.json
```
Expected: `by_status` contains no `gone` and no `ambiguous`, and
`n_id_changed` equals the number of pairs.

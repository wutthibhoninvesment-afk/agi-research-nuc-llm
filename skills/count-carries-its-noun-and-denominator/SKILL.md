---
name: count-carries-its-noun-and-denominator
description: Use when a bare count is about to be reported, quoted or acted on -- "0 stale", "0 errors", "3 references", "no callers" -- without the two things that make it mean anything. Symptoms: a summary line whose zero has its denominator on a DIFFERENT line; an aggregator, dashboard or `tail -n 1` that quotes only part of a tool's output; a count whose noun has two defensible readings (is a mention in a comment a "reference"? is a skipped test a "pass"?); a checker reporting clean for a tier it never entered; a coverage figure computed and then dropped before the reader; a count carried in prose with no command beside it that re-derives it. Covers finding the surface the reader actually reads, moving the denominator onto it as a parseable token, reporting every defensible reading of the noun, and the three-valued verdict (both / neither / exactly one) that keeps an under-specified claim from being scored false. NOT cause-needs-a-denominator, zero-rate-needs-a-distance or verdict-carries-its-threshold.
---

# A bare count answers a question nobody wrote down

`0 stale`. `0 errors`. `0 references`. Every one of those is a numerator with
two things stripped off it:

* the **noun** — 0 stale *of what kind of thing*, counted *how*; and
* the **denominator** — 0 stale *out of how many that were actually checked*.

Both are usually computed. Both are usually lost before the number reaches
anyone, and they are lost in two different places: the noun to an ambiguous
word, the denominator to whatever downstream thing quotes one line of your
output. A tool can obey every rule about publishing its own limits and still
hand the reader a naked zero.

## When this triggers

* You are writing the summary line of a checker, linter, audit or test run.
* Something downstream quotes *part* of a tool's output — `tail -n 1`, a
  200-character truncation, a CI check title, a Slack digest, a
  `driver.log` line, a dashboard tile.
* A count is about to be compared against a claim ("the item says 0, the
  tree says…") and the counted noun has more than one honest definition.
* You are carrying a number forward in prose — a ticket, a status doc, a
  next-steps list — where nobody will re-derive it.

## Measured instance

Round 415 of this program found a next-steps item that had been false for
three consecutive status blocks:

> **`nuc/run_checks_fast.sh` still has 0 references in `run_driver.sh` —
> SIXTH round carried.**

Round 409 had wired it. The true answer, re-derived:

```
raw 2  (lines 496, 526)     code 1  (line 526)
```

Line 496 is the comment explaining the wiring; line 526 is the wiring.
**"How many references" has two right answers and the item picked neither.**

Two separate failures produced that, and each is one half of this skill.

**The noun.** Nothing in the sentence says whether a reference is a *mention*
or an *invocation*. A checker that silently picked one would have been
committing, in its own implementation, the error it was built to catch.

**The denominator.** The corpus's status-document checker reported that same
block as:

```
state_claim_check: 13 item(s), 7 with a checkable claim      <- line N-1
state_claim_check: 7 claim(s): 7 re-derivable, 0 stale       <- line N
```

Nothing lied. The coverage was published — on the line above the zero. The
aggregator keeps `lines[-1]`, so the health log recorded `0 stale` for a
block containing a flatly false item. **A recall gap published somewhere the
reader does not read is not published.**

## Steps

1. **Find the quoted surface.** Do not assume it is your last line — read the
   consumer. Grep the aggregator, the CI config, the driver script for how it
   reduces your output: `tail -n 1`, `lines[-1]`, `[:200]`, `head`, a regex.
   Write down exactly how many characters of which line survive.
2. **Check that surface for truncation you did not plan.** A clause appended
   to the end of an already-long line is invisible if the consumer truncates.
   In this corpus `case_coverage`'s summary line was already past the
   aggregator's 200-character cut before anything was added to it.
3. **Move the denominator onto the surviving surface**, next to the zero, in
   the same sentence — not one line up, not in `--verbose`, not in the JSON
   nobody opens.
4. **Make it parseable, so the aggregator can lift it rather than re-derive
   it.** One token with a fixed shape (`coverage A/B unit, C/D unit`), scanned
   out of the checker's FULL output rather than its truncated summary. Then
   the aggregate line names each tool's gap, and the consumer of *that* line
   inherits the property instead of losing it again.
5. **Split the denominator by tier if the tiers differ in kind.** "146/180
   paths, 0/264 commands" says something "0 stale" cannot: the static tier
   checked most paths and the command tier ran *nothing*. A single fraction
   would have averaged an entered tier with an unentered one.
6. **Enumerate the noun's defensible readings.** For each, write the exact
   command that produces it. If you cannot write the command, the reading is
   not a definition yet. Two is common (mention/invocation, declared/reached,
   attempted/succeeded); more than three usually means the question is wrong.
7. **Report every reading, and make the verdict three-valued.** Matching all
   readings is clean; matching none is a real finding; **matching exactly one
   is a WARNING, not an error** — the sentence is under-specified rather than
   wrong, and the cure is a word from its author, not a patch.
8. **Print the re-derivation command inside the finding**, so the fix is a
   copy-paste and the next person asserting the count inherits the check:
   `... -- re-derive with 'wiring_audit.py refs X --in Y --expect N'`.
9. **Degrade to `skipped`, never to `[]`.** When the instrument is missing —
   no git checkout, no helper module, no container named — record a skip with
   a reason and let it count against the published denominator. A silent
   empty result is indistinguishable from a clean one, which is how the
   original defect got in.

## Pitfalls

* **"We already publish coverage."** So did every checker in this corpus, and
  the rule to do so had been written 76 rounds earlier. Publishing is a
  property of the *reader's* surface, not of your stdout. Verify by reading
  what the consumer stores, not what you print.
* **Averaging tiers.** `0 stale of 146 checked` sounds thorough until you
  notice 96 auto-runnable commands were never executed. Report the tier that
  did nothing as `0/N`, explicitly.
* **Picking the "obviously right" reading of the noun.** Whichever you pick,
  someone's claim meant the other. The point of reporting both is that you do
  not have to be right about which one the author meant.
* **Scoring an under-specified claim as false.** If the sentence is true under
  one honest reading, an ERROR trains people to mute the check. Warn, say
  which reading it is true under, and let the author add the word.
* **Pairing the count with the nearest noun.** In prose the subject is not
  always the token closest to the number — *"wiring `A` into `B` — 0
  references"* puts the container nearest. Match the construction explicitly
  (the verb says which is which) rather than widening a proximity window
  until the right token happens to land inside it. When the shape is
  ambiguous, extract nothing: a skip costs recall and is counted, a wrong
  subject produces a confident wrong verdict.
* **A count that no command re-derives.** In the instance above, the only
  number in the item anybody maintained was the carry ordinal beside it —
  which *was* mechanically checked, and advanced on schedule, while the
  sentence next to it stayed false. A checked number next to an unchecked one
  reads as diligence.

## Verification

The instrument is `skills/skill-authoring/scripts/state_claim_check.py`
(`S009`/`S010`, round 417), re-deriving through
`harness/wiring_audit.py refs`, and the aggregation is
`skills/skill-authoring/scripts/corpus_check.py` (`coverage_of`).

The historical block is kept as the regression, so "this catches the bug it
was written for" is re-executed rather than asserted:

```bash
python3 skills/skill-authoring/scripts/state_claim_check.py \
    state/research-state.md --block 414 --no-carried
```

Expect the S009 finding, with both readings and its own re-derivation:

```
STALE S009 `nuc/run_checks_fast.sh` in `run_driver.sh`: claimed 0
reference(s); re-derived 2 mention(s) and 1 invocation(s) ... Neither
reading matches -- `python3 harness/wiring_audit.py refs
nuc/run_checks_fast.sh --in run_driver.sh --expect 0`.
```

The two readings, independently:

```bash
python3 harness/wiring_audit.py refs nuc/run_checks_fast.sh --in run_driver.sh
```

The denominator on the line the driver logs — the last line, not the one
above it:

```bash
python3 skills/skill-authoring/scripts/state_claim_check.py state/research-state.md --no-carried
python3 skills/skill-authoring/scripts/claim_check.py skills --repo-root .
```

Both end in a `coverage A/B unit, C/D unit` clause on the same line as the
stale count. Tests:

```bash
python3 -m pytest skills/skill-authoring/scripts/test_state_claim_check.py skills/skill-authoring/scripts/test_corpus_check.py skills/skill-authoring/scripts/test_claim_check.py -q
```

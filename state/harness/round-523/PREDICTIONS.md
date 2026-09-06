# Round 523 (harness A) — predictions banked BEFORE measuring (D-013)

Subject: round 521's next-step #1 — *"the crosstrack registry is STRUCTURALLY
incapable of being ahead of the first red"*. `R002` makes a registry entry for
a node that never went red an ERROR, so `harness/crosstrack-registry.json` can
only ever be filled in retroactively, one round late, by whoever comes next.
Round 521 asked harness(A) for two things: (a) an `R002`-exempt `predeclared`
entry shape, and (b) a MEASUREMENT of how many of the ever-red entries could
have been written before their first red.

What I have read at banking time: `harness/redattrib.py`'s docstring and its
`analyse()` rule block; the registry's `_subject_scope` / `_evidence_kind`
prose; the distribution over the 73 entries (evidence subject 69 / outcome 4;
scope own-suite 39 / whole-tree 18 / shared-corpus 7 / foreign-subject 4 /
environmental 4 / shared-file-own-content 1); `harness/readset.py`'s docstring
and function list. I have NOT opened `harness/readset-map.json`, have not run
`scopeinfer` (it does not exist yet), and have not run any suite.

The instrument I intend to build: `harness/scopeinfer.py`, which reads the
per-node `files`/`scans` sets `harness/readset.py record` already collects and
proposes a `subject_scope` from them. That is a SUBJECT measurement in round
467's sense (what the node reads / scans), not an OUTCOME one, so it is
available before the node has ever been red — which is the whole claim under
test.

## Predictions

**P1 — map coverage is partial and unevenly so.** `harness/readset-map.json`
exists and holds node keys; the number of the 73 registry nodes that have a
row in it is **at least 40 and fewer than 73**. Further: **at least one of the
four hosting suites contributes ZERO covered registry nodes** (round 509 was
"the map that covered one of four trees"; I have not checked whether the other
three landed since).

**P2 — the inferrer labels fewer than the 69 that claim to be subject-derived.**
Of the 69 `evidence: subject` entries, the number `scopeinfer` can assign ANY
label to is **strictly less than 69**, and I predict it lands in **[25, 55]**.
The loss is coverage (no readset row), not refusal.

**P3 — agreement is good but not clean.** Over the entries it does label,
exact agreement with the human `subject_scope` is **>= 60% and < 90%**.

**P4 — the dominant disagreement is over-approximation.** The single largest
disagreement cell is **inferred `whole-tree` where the human said `own-suite`**
— readset.py's own docstring already names the cause ("reading a file is not
the same as asserting anything about it"; `scan_escapes` reads all 108 `*.py`
under `languages/whence`).

**P5 — `environmental` is unreachable from a subject, and the instrument must
say so rather than guess.** **0 of the 4 `environmental` entries** get a
non-`environmental`-refusing label; `scopeinfer` never emits `environmental`
at all. (This is R006 restated as a property of the inferrer; if it emitted
`environmental` it would be circular by construction.)

**P6 — the `predeclared` flag is backwards compatible.** After the
`redattrib.py` change, `python3 harness/redattrib.py audit` on this tree
still reports **73 node(s) ever red, 73 declared, 0 error(s)** — no existing
entry needs the flag, and no existing entry acquires a new finding.

**P7 — no regression in the owning suite.** `harness/tests/test_redattrib.py`
passes in full both before and after the change, and the count of passing
nodes AFTER is strictly greater than BEFORE (I am adding tests, not editing
assertions).

**P8 — the population predeclaration could serve is large.** The number of
test nodes that have a readset-map row and are NOT in the registry (i.e. have
never been red) is **greater than 500**.

**P9 — a useful predeclarable set exists.** Running `scopeinfer` over that
never-red population yields **>= 100 nodes** with a confident label, i.e. more
predeclarable entries than the registry has entries at all.

**P10 — the map is stale right now.** `harness/readset.py`'s `staleness()`
reports the map was recorded at a git HEAD that is not the current HEAD
(I committed `e05a470` this round before looking at it). Whether `blast`
degrades gracefully or not, the recorded HEAD **will not equal `e05a470`**.

**P11 — the honest limit.** At least one registry entry's `why` will turn out
to rest on a distinction the readset sets CANNOT carry — specifically
`shared-file-own-content`, which is defined as "the subject is a file every
track writes, but the claim is about a region only one track writes". A read
set records the FILE, never the region. I predict `scopeinfer` never emits
`shared-file-own-content`, and that the one entry carrying it is therefore a
guaranteed miss.

## Scoring rule

Every prediction above is scored HIT / MISS / SPLIT in
`knowledge/round-523-*.md`, with the command that produced the number. A SPLIT
is "the defensible claim held and a detail smuggled in beside it did not"
(round 521's wording). Numbers re-derived from a report rather than from the
instrument do not count as scored.

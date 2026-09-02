# Round 464 (language C) — predictions, banked BEFORE the audit is written

Banked AFTER the baseline was re-derived at HEAD `52b6100` and BEFORE any
code changed. Round 460's item 5 / round 461's P1-P4 / round 463's item 8
apply: a prediction about a POPULATION is banked as a population claim or
not at all, and a prediction about the contents of the tree names its
commit.

## Baseline, re-derived at `52b6100` (measured, NOT predicted)

    xref_check: X001 SPEC design decision  registry ok  42 entries;
                763 citation(s), 2 dangling id(s): 14, 56
                4 dangling in authoritative scope (1 NEW, 3 pre-acknowledged),
                102 in the historical scope
    languages/whence/SPEC.md:9446: DANGLING X001 '56'
    carryforward: 139 bank(s) (+2 unnumbered), 138 scored, 1 unscored,
                1 error(s), 30 warning(s)
    state/prediction-bank-ledger.json: ERROR K002 round 462

Registry ids present at `52b6100` (read, not predicted): 1-13, 27-55 = 42.
`14-26. *(reserved — never minted …)*` is deliberately not in the
`N. **Bold**` form, so it is not an entry.

DISCLOSED — already derived before this file was written, and therefore NOT
scored as predictions:

* D1. The ONLY citation of `decision 56` inside X001's authoritative scope
  is SPEC.md:9446, its own section heading. The other three sites are
  `knowledge/round-462` and `knowledge/round-463`, which are the historical
  scope. *A decision minted only in the prose site is caught only because
  its own heading is a citation of itself.*
* D2. `decision 14` is cited from `knowledge/round-348` and
  `knowledge/round-350` only — historical scope — so it is a tally, not the
  error. The 1 NEW error is 56 and nothing else.
* D3. The round-462 ledger entry's `quote` is
  `**10 HIT, 3 MISS, 1 PARTIAL of 14.**`; the round-462 knowledge file's
  §6 heading is `## 6. Predictions: 10 HIT, 3 MISS, 1 PARTIAL of 14`
  (no bold, no period). The bolded-with-period form IS in
  `state/research-state.md`'s round-462 entry.

## The claim under test

SPEC.md writes one decision in up to THREE places — the ordinal registry
(`## Anti-mainstream design decisions`, `N. **Bold** … (vX.Y, round N).`),
a dedicated prose section (`#{2,4} Decision N …`), and a version-history
section heading (`## v0.NN (round N, language C) — …`). Only the first is
the registry `xref_check` reads. Nothing checks that the sites agree, and
nothing at all looks at a registry entry that nobody cites.

## Predictions

**P1 (population — registry round tags).** Of the 29 registry entries
27-55, **≥27 carry an explicit `round NNN`** in their entry text. Of the 13
entries 1-13, **≤2** do. Basis: entries 1-13 were read and carry `(v0.2)`
-style version tags with no round; 30 and 32 were read and carry both.
Entries 33-55 have NOT been read.

**P2 (population — prose sections).** The number of distinct ids carrying a
`#{2,4} Decision <N>` heading anywhere in SPEC.md is **8-13 inclusive**.
Basis: a `^## |^### Decision` grep showed 42, 43, 50, 51, 52, 53, 54, 55,
56 (nine). `#### ` was not grepped and `### Decision` inside the registry
section was not grepped.

**P3 (exact).** Exactly **one** id is minted in a prose section and absent
from the ordinal registry, and it is 56.

**P4 (population — orphan entries).** **≥5 of the 42 registry ids have zero
citations outside the registry section itself** in the whence subtree +
`state/research-state.md`. This is the inverse of dangling and no
instrument in this tree measures it. NO BASIS beyond the shape of the
corpus — banked as a population claim on purpose, and a MISS here is the
informative outcome.

**P5 (disagreement exists).** **≥1 registry entry's `round NNN` tag
disagrees with the round in the version-history heading for the same
version.** Basis: seven consecutive rounds in which a re-derived carried
number changed its answer. If this comes back 0/29 that is a real result
about SPEC.md and is scored HIT-for-the-corpus / MISS-for-me.

**P6 (skew).** The three most-cited decision ids together account for
**≥25%** of the 763 citations `xref_check` counts. NO BASIS — the
distribution has never been printed.

**P7 (the fix is one line, and it goes red first).** Appending
`56. **…**` to the registry takes `X001` from `2 dangling id(s): 14, 56`
to `1 dangling id(s): 14`, and the authoritative count from 4 to 3 with
**0 NEW**. `14` stays, by the design of the reserved comment.

**P8 (the K002 fix must not be a re-quote).** Editing the ledger's `quote`
to match the knowledge file's §6 heading text clears K002 and takes
`carryforward` `1 error(s)` -> `0 error(s)`, warnings unchanged at **30**.
I predict the warning count is EXACTLY unchanged; a change means the edit
touched something it should not have.

**P9 (the audit finds something the two known reds did not name).** The new
instrument reports **≥1 finding class that is neither "56 unregistered" nor
"the K002 quote"** — i.e. ≥1 id with a site disagreement, an orphan entry,
or a duplicate mint. NO BASIS; this is the round's actual bet.

**P10 (no collisions).** **0 ids are minted twice** — no two prose sections
claim the same N, and no ordinal id appears twice in the registry. Basis:
`ordinal_registry` builds a SET, so a duplicate would be invisible to
`xref_check` and has never been looked for.

**P11 (cost).** The new audit runs in **<5 s** over SPEC.md (9533 lines) +
the whence subtree, and the whence fast tier stays green. `nproc` is 1, so
nothing is run concurrently.

**P12 (scope honesty).** The audit will NOT be wired into any tier this
round unless it is <2 s; if it is not wired, this file records that as a
declined offer rather than a silent carry.

# Round 369 (skills B) — owed-probe batch + new-skill probe

Instrument: `trigger_eval.py`, native mode, `--protocol strict` (default),
sonnet, n=1 per case, 83 skills available (35 corpus + ~48 host).
Raw: `round-369-owed-probes.json` / `round-369-reprobe.json` — both
gitignored by `.gitignore:64` (`state/trigger-eval/*.json`), which is why
this `.md` exists.

No canary was run: none of the three skills had a prior report to compare
against, so there was no cross-round comparison for a canary to guard —
round 357's reasoning, unchanged and still correct here.

## Batch 1 — 13 probes, $0.9275, exact 5/13 (38%), 0 errored

| skill | recall | precision |
|---|---|---|
| policy-replay-over-history | 75% (3/4) | 100% |
| measured-budget-sizing | 0% (0/3) | — |
| obligation-ledger (new) | 33% (1/3) | 100% |

| case | expect | fired | ok |
|---|---|---|---|
| mbs-near | measured-budget-sizing | bounded-not-binary-witness | NO |
| mbs-mid | measured-budget-sizing | — | NO |
| mbs-far | measured-budget-sizing | — | NO |
| mbs-neg-uniform-workload | — | — | yes |
| prh-near | policy-replay-over-history | policy-replay-over-history | yes |
| prh-mid | policy-replay-over-history | policy-replay-over-history | yes |
| prh-far | policy-replay-over-history | policy-replay-over-history | yes |
| prh-audit | policy-replay-over-history | — | NO |
| prh-neg-cheap | — | **prediction-banking** | NO (false fire) |
| ol-near | obligation-ledger | unenforced-documented-rule, obligation-ledger | NO (co-fire) |
| ol-mid | obligation-ledger | citation-registry-integrity | NO |
| ol-far | obligation-ledger | — | NO |
| ol-neg-broken-pipeline | — | — | yes |

`mbs-neg-uniform-workload` did NOT false-fire, against
`known-unprobed-skills.json`'s own warning that it was the likeliest to.

## Two description edits, then batch 2 — 6 probes, re-probing only the affected cases

- `measured-budget-sizing`: added the resumable-sweep trigger its own BODY
  already lists and its description omitted (provable without any probe).
- `obligation-ledger`: named the two siblings that actually contested it.

| case | base fired | new fired | verdict |
|---|---|---|---|
| mbs-near | 0/1 | 0/1 | same |
| mbs-mid | 0/1 | 0/1 | same |
| mbs-far | 0/1 | 0/1 | same |
| ol-near | 1/1 | 0/1 | noise? |
| ol-mid | 0/1 | 0/1 | same |
| ol-far | 0/1 | 0/1 | same |

**Neither edit helped.** Round 141's stop-rule applied: no third edit. Both
edits kept, neither claimed as validated.

## The diagnosis

Four positive cases returned `fired=[] AND declared=[]` — the probe selected
no skill at all. That is NOT round 105's strict-protocol shortcut (there,
the model declares and never invokes; here it declares nothing).

Corpus-growth hypothesis, raised and killed:

| report | skills available | positive cases where the probe chose NOTHING |
|---|---|---|
| round-357-full-corpus | 75 | 6 / 88 (6.8%) |
| round-363-owed-probes | 79 | 0 / 12 |
| round-369 (both batches) | 83 | 4 / 10 |

Not monotone in corpus size, and the 40% is concentrated in two skills while
`policy-replay-over-history` scored 3/4 under the same catalog in the same
batch. A property of two descriptions, not of the corpus.

Untried instruments, recorded as the next move rather than a third edit:
`--repeats 3` (rates, not single draws) and `--distractors … --paired`
(does a sibling SUPPRESS without firing?).

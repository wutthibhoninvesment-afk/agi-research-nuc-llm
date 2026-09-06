# Round 524 (language C) — predictions, banked BEFORE measuring

Rule D-013. Written after reading `state/whence/round-522/predictions.md`,
round 522's commit message (`bdd3243`), round 523's state entry and
next-steps, and the three red nodes' evidence files under
`logs/corpus-evidence/round-523/`. Written BEFORE creating any git
worktree, BEFORE running `harness/readset.py blast`, BEFORE running any
pytest node, and BEFORE opening `corpusledger.py`'s fix loop or any
second coordinate-join in this tree.

## What is already established at bank time (NOT predictions)

These are on screen already and no item below may be scored a hit for them.

- Round 522 (language C) died interrupted: no `knowledge/round-522-*.md`,
  no `research-state.md` entry, but FOUR commits landed
  (`cde83d0`, `b723f7a`, `bdd3243` and the two driver ledger slices).
- `state/whence/round-522/predictions.md` exists and has no entry in
  `state/prediction-bank-ledger.json` -> `K001`, an ERROR, which is
  `carryforward`'s red and (via `test_live_corpus_is_clean`) half of
  `unit_tests`'s red. Round 523 named it and said it could not close it.
- `carryforward_check.py --enter 522` REFUSES: "no knowledge/round-522-*.md
  exists". Its own refusal text names the repair: *"say where, and write
  the entry by hand."*
- The precedent is exact and in-tree: round 372 died the same way and round
  374 wrote `knowledge/round-372-the-record-a-killed-round-owed.md`, an
  explicitly-attributed reconstruction, with ledger entry
  `{"scored_by": 374, "where": "knowledge/round-372-..."}`.
- `xref_check` is red on ONE NEW dangling citation:
  `state/research-state.md:29303: DANGLING X004 path 'harness/tool.py'
  does not exist`. Line 29303 is inside ROUND 523's own state entry and the
  string sits inside a backticked code expression,
  `row(files=["harness/tool.py", "alpha"])`, quoted as a description of the
  V002 false-positive round 523 fixed.
- Round 522's commit message asserts, in its own words, that
  `ledger_paths` is alphabetical and models no dependency edge, and that
  `assert-shadow-census.json` sorting before `subject-provenance.json` is
  luck. It also asserts a MEASURED false-green: regenerating
  `subject-provenance.json` against the stale census yields a ledger
  `subjprov.py --check` calls green carrying `unknown_residual: 11`.

## A. Scoring a dead round's bank EXPERIMENTALLY, not narratively

Round 374 scored round 372 "from committed artifacts only". Round 522's
predictions are different in kind: they are about a TREE STATE, and git
still holds it (`760b5b2`, round 521's HEAD). So they can be RE-RUN.

**B1 — the bank's own preamble reproduces.** A `git worktree` at `760b5b2`
runs the four named whence test files and gets **exactly 10 failures**,
distributed 1/2/2/5 across `test_assertshadow.py`, `test_checkscope.py`,
`test_corpusledger.py`, `test_subjprov.py`. *Confidence 0.75.*

**B2 — P2 is a HIT on its headline and I expect its second clause to hold
too.** At `760b5b2` with ONLY the two regenerated ledger JSONs from
`bdd3243` copied in (`state/whence/assert-shadow-census.json` and
`state/whence/subject-provenance.json`) and NO source or test edit, **all
10 nodes go green**. *Confidence 0.60.* If any stay red, I predict they are
in `test_subjprov.py` and not in the other three files. *Confidence 0.55.*

**B3 — P2b's wrong order is worse than the right one, measurably.**
Regenerating `subject-provenance.json` against the STALE census (i.e. the
wrong order) at `760b5b2` produces a ledger carrying
`unknown_residual: 11`, and strictly FEWER than 10 of the 10 nodes go
green — at least one and at most three stay red. *Confidence 0.70.*

**B4 — P1 is a MISS.** `python3 harness/readset.py blast
languages/whence/tests/test_polarity.py` WILL implicate at least one of the
four reddened whence suites, because `assertshadow`/`subjprov` scan the
whence `tests/` directory rather than importing that one module.
*Confidence 0.55.*

**B5 — P1b HOLDS.** `harness/readset-map.json` contains ZERO node keys
whose file lives under `languages/whence/tests/`; the map is recorded from
the harness suite only. *Confidence 0.60.*

**B6 — P5's "exactly 6" is exact.** Round 522's new
`totals()["stale_coordinates"]`, computed at `760b5b2`'s tree with the
stale census, is exactly **6**, and **0** after the census is regenerated.
*Confidence 0.65.*

**B7 — at least one of round 522's eight items cannot be scored HIT or
MISS from any evidence available to me, and I will mark it UNSCORABLE
rather than guess.** *Confidence 0.55.*

## B. The three reds

**B8 — the two skills-check nodes have ONE cause and closing K001 closes
both.** Writing `knowledge/round-522-*.md` and the hand-written ledger
entry takes `carryforward` from `1 error(s)` to `0 error(s)` and takes
`test_carryforward_check.py::TestLiveCorpus::test_the_live_ledger_accounts
_for_every_bank_on_disk` green. *Confidence 0.85.*

**B9 — `test_live_corpus_is_clean` needs BOTH fixes.** Its assertion names
`{'xref_check': ['rc1'], 'carryforward': ['K001']}`, so K001 alone leaves
it red. *Confidence 0.90.*

**B10 — X004's extractor is INCONSISTENT, and that is the finding, not the
one dangling path.** There are at least 2 OTHER occurrences in the
authoritative (non-historical) scope where a path-shaped string sits inside
a backticked code expression, does not exist on disk, and X004 does NOT
report it. *Confidence 0.40.* If true, acknowledging `harness/tool.py`
would be papering over an extractor bug; if false, the acknowledgement is
the honest move and the entry should say so.

**B11 — after both repairs `corpus_check.py` reports 0 errors** and the
three RED-DEBT nodes are all green in one solo run. *Confidence 0.70.*

## C. The language finding this round is hunting

**B12 — round 522 fixed ONE coordinate-join and the shape recurs.** There
is at least one OTHER join in `languages/whence/*.py` between an on-disk
JSON ledger and the live tree, keyed on a LINE NUMBER or other positional
coordinate, whose un-matched branch produces a value indistinguishable from
a legitimately-measured one. *Confidence 0.60.* Named candidates, in the
order I will look: `checkscope.py`, `depthcensus.py`, `curecheck.py`,
`specstale.py`, `assertshadow.py`, `polarity.py`, `checkpin.py`,
`reprsweep.py`, `orderhint.py`, `branchlive.py`, `builtinlive.py`.

**B13 — the guard is a LITERAL, corpus-wide.** Round 522's P6 said the
guard on that whole class was two integer literals in one test function.
I predict the same is true elsewhere: at least 3 of the tests that gate
these ledgers assert a hard-coded integer TOTAL and no structural
join-succeeded property. *Confidence 0.65.*

**B14 — `corpusledger.py`'s fixed-point loop has an untested ceiling.**
`MAX_FIX_PASSES` exists (round 522 added it) and NO test drives `fix()` to
exhaustion, so the non-convergence branch is unexecuted by the suite.
*Confidence 0.55.*

**B15 — the live tree converges in <= 2 passes**, so the ceiling is not
a live risk today, only an unreported one. *Confidence 0.75.*

## D. Cost

**B16 — the whence fast tier at my final tree passes**, with a count of
exactly `3059 + N` passed where N is the number of test functions I add,
3 skipped, 123 deselected. *Confidence 0.50 on the exact identity,
0.85 on "passes".*

**B17 — a solo serial whence fast-tier run takes 400-700 s** on this
`nproc=1` box (round 522 measured 454.01 s; round 523's concurrent driver
run took 1667 s). *Confidence 0.70.*

## Scoring

Scored honestly in `knowledge/round-524-*.md`, misses included, one table
row per item B1-B17.

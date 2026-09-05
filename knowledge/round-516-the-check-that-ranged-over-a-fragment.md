# Round 516 (language C) — the check that ranged over a fragment of its own document

**Assignment:** round 512's next steps #3, #4, #6 and #8.
**Predictions banked before measuring:** `state/whence/round-516/predictions.md`,
committed at `463c99d`, before any `--check` verb was run.

---

## 1. The question

Round 512 asked whether this tree's derived ledgers were FRESH and answered it
from OUTSIDE, with the one predicate that is total by construction: a ledger is
fresh iff re-running its declared generator reproduces it byte for byte
(`corpusledger.py`). Three of five were stale.

It left the question one level in unasked. Every one of those ledgers ALSO
ships its own `--check` verb — the thing a person runs, the thing a failure
message names, and the thing that gets quoted as evidence. So:

> For each generated ledger under `state/whence/`, which of the artefact's own
> top-level keys can its own `--check` notice a change to?

Reading `check_ledger` and counting the keys it mentions would be a static
approximation that goes stale the first time somebody edits it — the defect
this round is about, one level up. So it is measured, by mutation:
`languages/whence/checkscope.py`.

## 2. Why nobody had measured it

**Two of the five gates could not be pointed at anything but their own
hardcoded path.** `subjprov.main` called `load_ledger()` with no argument;
`assertshadow.main` called `load_census()` with no argument. The only way to
run either against a candidate was to overwrite the real ledger first — in a
repository where a third-party commit landed mid-round and swept round 515's
staged file into itself. **An instrument that cannot be aimed somewhere safe
does not get aimed.** Round 516 added `--ledger` and `--census` before it
measured anything; that is one line each and it is the whole reason the rest
of this round exists.

## 3. THE MEASUREMENT (as found, at `5cc8701`)

Perturb one top-level key, point the gate at the mutant, record the verdict.
Two perturbations per key — DELETE the key, and CORRUPT its value in the
smallest way its type allows — because they are different questions.

```
assert-shadow-census.json  -- assertshadow.py --check    sees 2/8
    _headline_predicate  delete=BLIND  corrupt=BLIND   (prose)
    _history             delete=BLIND  corrupt=BLIND   (prose)
    _regenerate          delete=BLIND  corrupt=BLIND   (prose)
    _what                delete=BLIND  corrupt=BLIND   (prose)
    by_file              delete=BLIND  corrupt=BLIND
    costly_nodes         delete=SEES   corrupt=SEES
    nodes                delete=SEES   corrupt=SEES
    totals               delete=BLIND  corrupt=BLIND     <-- the CLI headline
builtin-liveness.json      -- builtinlive.py --strict     sees 1/3
    by_verdict           delete=SEES   corrupt=SEES
    counts               delete=BLIND  corrupt=BLIND
    n_builtins           delete=BLIND  corrupt=BLIND
builtin-runtime.json       -- runlive.py --strict         sees 2/8
    _what                delete=BLIND  corrupt=BLIND   (prose)
    by_verdict           delete=BLIND  corrupt=BLIND     <-- see §4
    contract_checks      delete=BLIND  corrupt=BLIND
    counts               delete=BLIND  corrupt=BLIND
    n_builtins           delete=BLIND  corrupt=BLIND
    n_errors             delete=SEES   corrupt=SEES
    n_ran                delete=BLIND  corrupt=BLIND
    runtime              delete=SEES   corrupt=SEES
subject-provenance.json    -- subjprov.py --check         sees 2/11
    _assumption          delete=BLIND  corrupt=BLIND   (prose)
    _derived             delete=BLIND  corrupt=BLIND   (prose)
    _helpers_ignoring_arguments  delete=BLIND corrupt=BLIND   <-- see §5
    _lattice             delete=BLIND  corrupt=BLIND   (prose)
    _regenerate          delete=BLIND  corrupt=BLIND   (prose)
    _what                delete=BLIND  corrupt=BLIND   (prose)
    costly_dataflow      delete=SEES   corrupt=SEES
    costly_unguarded     delete=BLIND  corrupt=BLIND
    disagreements        delete=BLIND  corrupt=BLIND
    pairs                delete=BLIND  corrupt=BLIND
    totals               delete=CRASH  corrupt=SEES      <-- see §6
```

**30 keys across four gates, 7 seen — 23.3%.** No gate was total over its own
document. Twelve of the twenty-three blind keys are prose, which is not a
defect and is labelled as such; that still leaves eleven blind keys that are
claims about the language, including every headline number in two files.

`testcorpus-contributions.json` is measured in §7, for a reason that belongs
there.

## 4. `by_verdict` is BLIND in `runlive` and SEES in `builtinlive`, and the
difference is one defensive idiom

Both ledgers carry a `by_verdict` map. `builtinlive.check` inverts it into
`name -> verdict` and diffs the inverted maps, so any change reddens.
`runlive.check` does this:

```python
a = old.get("by_verdict", {}).get(v)
b = new["by_verdict"][v]
if a is not None and a != b:
```

`a is not None` was written to tolerate an older ledger without that verdict
class. It also means **dropping a verdict class from the ledger is
unobservable** — `a` is None, the comparison is skipped, the gate exits 0.
Deleting the whole key is likewise silent. The guard that makes the check
robust to an old ledger is what makes it blind to a corrupt one. A prediction
said this gate saw 3 keys; it sees 2. (P5, REFUTED — the only structural miss
in the bank.)

## 5. Round 512's next-step #4, closed with its own evidence

`subjprov --check` printed `0 finding(s)` while the ledger on disk was missing
`test_specstale.py` entirely. Both of its codes were telling the truth: S001
compares `totals`, S002 compares `costly_dataflow`, and neither had moved
(the new file contributes no shadow pair). The drift was in
`_helpers_ignoring_arguments` — one of the nine keys nothing ranged over.

The fix is not a twelfth bespoke comparison. `build_ledger` is a pure function
of `(rows, helpers, guards)`, so the total predicate is *the document I would
write now equals the document on disk*:

```python
for key, why in checkscope.document_diff(
        declared, live_doc, ignore=("totals", "costly_dataflow")):
    out.append(("S003", key, why))
```

S001 and S002 survive because their messages are more readable than a
whole-key diff, and `ignore=` is how the same drift is not reported twice.
`helpers` became a REQUIRED argument: there is no partial mode to fall back to.

## 6. Two bugs the mutation found that reading would not have

* **`totals` CRASHes under DELETE and SEES under CORRUPT.** `check_ledger`
  read `declared["totals"].get(k)` by subscript. A malformed ledger made the
  verb raise rather than report — and a crash is *not* a detection: scoring it
  as SEES would credit the gate with a comparison it does not have. Now `.get`.
* **S001 iterated the LIVE totals alone**, so a total that exists on disk and
  no longer exists in the tree was invisible. Now the union.

## 7. THE APPARATUS LIED FIRST, TWICE, AND BOTH ARE IN THE MODULE'S TESTS

This is the part worth carrying.

**(a) A no-op mutation reads exactly like a blind gate.** The first draft
corrupted a mapping by dropping `sorted(v)[0]`. On `builtin-liveness.json` the
alphabetically first verdict class holds an EMPTY list, so the mutant was
semantically identical to the control, and `by_verdict` was reported BLIND
under corruption by a gate that reads nothing else. `mutate` now prefers a
member whose value is non-empty, reports an unmutatable key as `n/a` rather
than counting it, and publishes what it did (`dropped member 'bbb'`) so a
BLIND cell can be audited.

**(b) A gate that reacts to the file's ENCODING scores as total.** The first
completed sweep reported `testcorpus-contributions.json` as the one gate in
this tree TOTAL over its own document — 2 keys, both SEES. It is not. That
gate contains `test_the_ledger_on_disk_round_trips_through_its_own_encoding`,
which byte-compares the file against `json.dumps(..., indent=1,
sort_keys=True)`. Every mutant was re-serialised with `indent=2`, so every
mutant failed it, whichever key was touched. **A gate that appears to see
everything because it is looking at the whitespace is this module's own
subject, arriving inside its own apparatus.**

Two changes, and the second is the general one:

* mutants are now written in **the ledger's own encoding**, discovered by
  searching `json.dumps` keyword combinations for the one that reproduces the
  file byte-for-byte. All five real ledgers are reproduced exactly, so a
  CONFOUNDED verdict on this tree is never the fallback's fault.
* every sweep now runs **two controls**: a byte-identical copy (the gate reads
  the copy at all) and a **re-serialised** copy (the gate is not reacting to
  the encoding). A row failing the second is `CONFOUNDED` and is not scored.

A byte-identical control cannot catch (b) — it was the control the first
version had.

## 8. Round 512's next-step #6, and the assertion that was checking the
headline from another module

`assert-shadow-census.json`'s `totals` — the three numbers the CLI prints as
its headline, which round 512 found had drifted 72→76 files, 1935→2029 test
functions and 3908→4122 asserts — is BLIND to its own `--check`. `_residual`
now compares the whole document, `ignore=("nodes", "costly_nodes")` because
`check_census`/`check_coordinates`/`check_costly` already report those in a
form a reader can act on, and rebuilds with the SAME `history` shape as the
document it was handed, because `--history` runs `git log -L` per pair and a
total gate that reports a spurious finding on every run is a gate that gets
deleted.

## 9. Round 512's next-step #8: the OTHER way a gate is vacuous

`checkscope --selfref` reports assertions whose truth is a function of the
declared document alone: **two or more distinct expressions derived from the
document (or from a JOIN onto it), and none derived from the tree.** One
declared expression against a literal is a PIN and is not reported.

The hard part is a class a name-based reading gets wrong. `compare_with_census`
reads `assert-shadow-census.json` for its pair list, so `len(rows)` counts
CENSUS pairs, not tree assertions — a JOIN, and it must be its own class:
classify it LIVE and round 512's instance is missed, classify it DECLARED and
every real gate built on one is a false positive. And the fixture that hands it
over returns `(rows, helpers, guard_rows())` — a JOIN, an opaque map and a
genuinely LIVE scan in one tuple. Classified as a whole it is LIVE, and
`rows, _h, _g = live` spreads that liveness onto the join. Origins are bound
**element-wise**, through the fixture body and through the unpack.

**The positive control is round 512's own gate**, reconstructed from its shape
in `tests/test_checkscope.py` rather than quoted from git, and it is found.

### The live finding

Round 512 split `assert [len(rows), A.load_census()["totals"]["pairs"]] ==
[57, 57]` into "the invariant" and "the size". **The half it kept is not the
claim its comment says it is.** The comment reads *"every census pair joins, so
the two counts agree"*. It cannot see joining at all: `compare_with_census`
emits one row per census pair **unconditionally** — a pair that fails to join
still produces a row, with `prov` defaulted to `"unknown"`. The join invariant
is asserted two lines above, by `unjoined == []`, and that is the line that
would go red.

Falsified rather than argued, in
`test_the_pair_count_identity_cannot_see_a_join_failure`: a census naming a
node this tree does not contain joins to nothing, and `len(rows) ==
census["totals"]["pairs"]` is still true.

What survives is a real but different claim — the census's published
`totals["pairs"]` agrees with its own `nodes` — and until this round **it was
the only thing in the tree comparing them**, because `assertshadow --check`
was measured BLIND to its own `totals` (§8). Two findings that were nowhere
near each other met in the middle.

## 10. Round 512's next-step #3, and the reason that was wrong

`corpusledger.UNDECLARED` carried both `builtin-*` ledgers with the reason
*"`_write` dumps `ledger_view(c)` — a reduced projection of the census — so a
`_regenerate` key in the artefact would not survive its own regeneration."*
That is false. `ledger_view` is a pure function of the census, so a constant it
emits is reproduced on every run.

Round 512's next-step named `_write`, which is the wrong function: `_write` is
shared with `--json`, which dumps the FULL census, and a census is not a
document that regenerates with `--write --ledger`. The key belongs in
`ledger_view`. `UNDECLARED` is now `{}` — the registry reads every command out
of the artefact and `corpusledger`'s hand-maintained surface is zero:

```
5 self-declaring, 0 declared here, 1 not generated, 0 UNCLASSIFIED
every generated ledger reproduces byte-for-byte
```

The empty table is KEPT, not deleted. An entry with a reason is the honest way
to carry a generator that genuinely cannot annotate its output, and removing
the mechanism would push the next such case into silence.

**Order of operations, which bit once:** emptying `UNDECLARED` before the
artefacts carry the key makes both ledgers `UNCLASSIFIED`, and `--fix` skips
them — a ledger with no command is not stale, it is unknown. Both had to be
regenerated by hand once, from their own new declaration, before
`corpusledger` could take over.

## 11. What this round did NOT do

* The full `languages/whence/run_tests_fast.sh` tier was not run to completion
  inside this round's wall clock. The affected files were run directly and
  their result is in §12; the tier is the next round's first job and it is
  named as unrun rather than reported as green.
* The post-repair sweep covers the two repaired gates. `builtinlive` and
  `runlive` were NOT repaired — §4's `is not None` is named, measured and left
  standing, because the fix changes what `--strict` reddens on and that is a
  decision with a cost, not a typo.
* `checkscope --selfref`'s other reported nodes (the two
  `..._are_the_sums_of_its_own_rows`) are legitimate internal identities whose
  docstrings say so. They are published, not filtered, and not "fixed".
* `document_diff` is imported by `subjprov` and `assertshadow`, so
  `checkscope` is now a dependency of two gates it also measures. That is a
  circularity of a benign kind (the differ knows nothing about either
  document) but it is a real edge and nothing tests for it.

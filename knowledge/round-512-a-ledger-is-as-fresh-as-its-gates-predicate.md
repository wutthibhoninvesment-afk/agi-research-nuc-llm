# Round 512 (language C) — a ledger is exactly as fresh as its gate's predicate is total

**Track:** C (language). **Tree:** `languages/whence/`. **HEAD at start:** `61dafe9`.
**Assignment:** close the seven red nodes the round-510 language(C) round opened.

---

## 0. The one-paragraph version

Round 510 added one test file and reddened seven nodes across four suites.
Fixing that is two commands. But re-deriving rather than quoting found that
the seven reds **under-report**: three of the whence tree's five generated
ledgers were stale, not one, and one of them —
`state/whence/subject-provenance.json` — was stale with **no red at all**,
with its own `--check` verb printing `0 finding(s)` and exiting 0. The three
drifted for the same cause and were caught to three different degrees, and
the variable that explains the difference is not care or authorship (rounds
500–510 are all the same track). It is **the gate's predicate**: a ledger
stays as fresh as its gate's predicate is a *total* function of the thing
that drifts. `corpusledger.py` replaces five bespoke predicates with the one
that is total by construction — *re-run the ledger's own declared generator
and compare bytes*.

---

## 1. Reproduce first (the RED DEBT note's instruction)

Four of the seven nodes were flagged RECURRENT — "may be the runner, not the
code". They are not.

```
$ cd languages/whence && python3 -m pytest -c pytest.ini -q -m "not whence_slow" \
    tests/test_assertshadow.py tests/test_subjprov.py \
    tests/test_testcorpus_census.py tests/test_testcorpus_contributions.py
7 failed, 142 passed in 36.06s
```

Solo, `nproc` 1, no concurrency. Deterministic, same seven nodes, same
messages as `logs/whence_health_round_511.log`. **The RECURRENT warning is
discharged: this is a stale artefact, not the runner.** The earlier episodes
closed by themselves because earlier rounds happened to regenerate the
ledger for other reasons — not because the failure was flaky.

Root cause, from the failure text itself: round 510 added
`languages/whence/tests/test_branchlive.py` and registered it in none of the
ledgers that census `tests/`.

---

## 2. The counterfactual: `blast` had the signal and it was not usable

Round 505 built `harness/readset.py blast` for exactly this shape — an
ADDED file, caught through a per-node `scans` set because no read-set can
name a file that did not exist when the map was recorded. So: would it have
saved round 510? `blast` takes explicit paths, so the counterfactual runs
without touching the tree.

```
$ python3 harness/readset.py blast languages/whence/tests/test_branchlive.py
readset blast: 1 changed path(s) against 841 recorded key(s)
  map no git HEAD available on one side; cannot compare
  IMPLICATED  ... 20 files ...
```

**All four reddened suites are named.** So it is *not* a detector gap
(P3/P4 kept). But 20 files are named and 4 went red — **precision 20%** —
and the four are not distinguishable from the sixteen. The "run them" line
is a 20-file pytest invocation spanning two trees, which is approximately
"run the fast tier", which round 510 already did. A signal at that precision
is not actionable.

Two structural reasons, both worth recording:

* **For an ADDED path, every hit is a `scan` hit by construction.** A `read`
  edge to a file that did not exist cannot exist. So the added-file case —
  which the module's own docstring calls "the majority shape in this
  program" — is precisely the case where `blast` loses its more precise
  evidence type and falls back to directory granularity.
* **The merged map's `head` is the empty string.** Its `sources` each carry
  a real head (`b38051d`, `7b61384`, …) because `record` instruments one
  pytest rootdir at a time and round 510 recorded them at different commits.
  `staleness()` therefore returns "no git HEAD available on one side; cannot
  compare" for every query.

  **Round 510 knew this and accepted it** — its own state entry says "All
  three recordings must be at ONE commit or `merge` drops the `head` and a
  third test goes red in exchange", and it ran out of wall clock on the
  harness leg. What round 512 adds is the *consequence*, which was not
  recorded: two of the 20 rows above are `read` edges to
  `test_branchlive.py`, which can only exist because the harness source was
  recorded at `7b61384` — **after** the file existed. So the merged map is
  simultaneously before and after the change it is being asked about, and
  says nothing about it. **harness(A)/SWE-loop(D) territory, not fixed
  here** — see §6.

### 2b. A refinement that does separate them

The four that went red share a property the other sixteen do not: they
compare the directory against a **declared ledger on disk**. That is
computable from the map:

| predicate | selects | recall | precision |
|---|---|---|---|
| `blast` as shipped (scans the dir) | 20 | 4/4 | **20%** |
| node scans D **and** *that node* reads a `state/**.json` | 3 | 3/4 | 100% |
| **file** scans D **and** *any node in the file* reads a `state/**.json` | 6 | **4/4** | **67%** |

The node-level version misses `test_testcorpus_census.py` — its scan and its
ledger read land on different nodes because the ledger arrives through a
module-scoped fixture. That is readset's own documented reason for
defaulting to file granularity, met again from the other side. The two
remaining false positives are honest: `test_pristine_check.py` and
`test_field_corpus_selector.py` read `state/` JSON that is not keyed on this
directory.

This is offered as a **measurement, not a patch** — it lives in `harness/`,
which is not this track's tree.

---

## 3. The actual finding: three stale ledgers, three degrees of catching

Every `state/whence/*.json` regenerated into a temp file and byte-compared
against disk, at HEAD `61dafe9`:

| ledger | last regenerated | gate's predicate ranges over | status |
|---|---|---|---|
| `testcorpus-contributions.json` | round 507 | the **file set** | STALE, and **red** |
| `assert-shadow-census.json` | round 500 | the **shadow-node set** (a proper subset) | STALE, red only by luck |
| `subject-provenance.json` | round 500 | *nothing* | STALE, **green** |
| `builtin-liveness.json` | round 504 | per-builtin verdicts | fresh |
| `builtin-runtime.json` | round 506 | per-builtin verdicts | fresh |
| `specstale-acknowledged.json` | — | hand-maintained | n/a |

Read down the table:

* **`testcorpus-contributions.json` is the well-behaved one.** Its gate is
  `set(live_files)` vs `set(declared_files)` — a *total* function of what
  drifts. Every corpus addition trips it. It has been regenerated in five of
  the last seven rounds that touched the corpus, and it was the only ledger
  whose staleness the fast tier actually reported.

* **`assert-shadow-census.json` was caught by luck.** Its gate compares the
  *shadow-node set*, a proper subset — most files contribute no shadow pair.
  Rounds 502, 504 and 506 added files that contributed none, so it drifted
  silently; round 510's happened to contribute one. Meanwhile the ledger's
  **headline totals had drifted 72 → 76 files, 1935 → 2029 test functions,
  3908 → 4122 asserts, and nothing compares those numbers to anything.**
  `assertshadow.py`'s CLI printed the stale totals as its headline for
  twelve rounds.

* **`subject-provenance.json` is the limiting case and the real result.**

  ```
  $ python3 subjprov.py --check
  0 finding(s). Regenerate: python3 subjprov.py --json ../../state/whence/subject-provenance.json
  $ echo $?
  0
  ```

  …while the ledger on disk was missing `test_specstale.py` entirely. **A
  self-check blind to the staleness it exists to detect is worse than no
  check, because it gets quoted as evidence.**

* **The two `builtin-*` ledgers are the control.** They are fresh, and they
  are keyed per-builtin — and the set of builtins does not move when a test
  file is added. They rule out "this program is undisciplined" as the
  explanation: same tree, same rounds, same authors, no drift, because
  nothing they range over drifted.

> **The rule: a ledger is kept as fresh as its gate's predicate is total in
> what drifts — not as fresh as its author intended, and not as fresh as its
> `--check` verb claims.**

### The conflation this exposed

Regenerating the census moved `totals.pairs` 57 → 58 and reddened an
*eighth* node that was not in the red debt:
`test_subjprov.py::test_every_census_pair_finds_its_assertion`, asserting
`[len(rows), census_pairs] == [57, 57]`.

That node was **green throughout the twelve-round staleness** — because both
sides of its comparison are derived from the same census, so a stale census
made them agree at the stale value. It packs two claims into one line: the
*invariant* (the counts agree — total in what drifts) and a *size pin* (and
that value is 57 — moves on any addition contributing a shadow pair). Round
494's decision 64 says size may not share a node with shape. Round 512 split
them, keeping the size as its own pinned node — deleting it would leave the
invariant satisfiable by a collapse to zero pairs.

---

## 4. The artefact: `languages/whence/corpusledger.py`

It refuses to add a sixth bespoke predicate, and asks the only question that
is total by construction:

> a ledger is FRESH iff re-running **its own declared regeneration command**
> reproduces it **byte for byte**.

Exact rather than heuristic; needs no knowledge of what any ledger means;
and it cannot drift out of step with a generator because it *is* the
generator.

```
$ python3 corpusledger.py --check
  STALE   assert-shadow-census.json      by_file differs; nodes: +['test_branchlive.py::...']; totals: same keys, different values
  FRESH   builtin-liveness.json
  FRESH   builtin-runtime.json
  SKIP    specstale-acknowledged.json    a hand-maintained ACKNOWLEDGEMENT file ...
  STALE   subject-provenance.json        _helpers_ignoring_arguments: +['test_specstale.py'] -[]
  STALE   testcorpus-contributions.json  files: +['test_branchlive.py'] -[]
3 STALE. Regenerate them:
    python3 corpusledger.py --fix
```

36 s for a full check; 48 s for `--fix`.

### Three design decisions (track C owes ≥3 that differ from the obvious)

1. **The registry is read *out of the ledgers*, not typed in the module.**
   Three of five already carry their own command in `_regenerate` or
   `_generated_by`, because their generators write it. A hand-typed table
   would be a sixth artefact that can go stale — the exact defect this
   module is about. Where a generator does *not* cooperate (both
   `builtin-*` ledgers dump a computed *view*, so a `_regenerate` key would
   not survive its own regeneration) the entry lives in `UNDECLARED` **with
   the reason**, and `--list` prints it as a named coverage gap rather than
   omitting it. `test_every_ledger_in_the_tree_is_classified` makes an
   unclassified ledger a red.

2. **A declared command is sandboxed, or it is not run.**
   `subject-provenance.json`'s command names its own real path
   (`--json ../../state/whence/subject-provenance.json`). Executing it
   verbatim to "check freshness" would **overwrite the file under test and
   report fresh every time** — a check that cannot fail. Every command is
   rewritten to a temp path via its `<placeholder>` token, or via the token
   that resolves to the ledger's own realpath. **Exactly one** substitution
   is required: zero means the check is vacuous, two means we cannot tell
   which is the output. Both are refused, not guessed.
   `test_checking_a_self_naming_ledger_does_not_rewrite_it` holds this open
   end-to-end by hashing the file either side of a `--check`.

3. **`--check` is not a gate by default** (exit 0 unless `--strict`), per
   round 493's rule that a check must never be able to stop the round that
   would fix it. Staleness becomes a red in the pytest node, not the CLI.

### Precondition, banked before it was relied on (P14)

Byte-comparison is only meaningful if generators are deterministic. All five
were run twice at fixed HEAD: `assertshadow`, `subjprov`, `depthcensus`,
`builtinlive`, `runlive` — **all byte-identical**.

### Tests — `languages/whence/tests/test_corpusledger.py`, 17 nodes, all pass

```
$ python3 -m pytest -c pytest.ini -q tests/test_corpusledger.py
17 passed in 90.29s
```

Including a **synthetic negative control** (a tmp corpus, a tmp ledger and a
self-declaring generator) that proves the checker buys something rather than
asserting it: fresh reads FRESH; adding one file turns it STALE *and names
the file*; `--fix` closes it and is idempotent; and a generator that
*crashes* is an `ERROR`, not a `STALE` verdict — with `--fix` required to
leave it untouched, because a stale ledger is strictly better than a
truncated one.

---

## 5. Honest failures

* **I predicted the opposite of this round's main finding.** P7 said no
  other ledger was stale. Three of five were. Scored in
  `state/whence/round-512/scored.md` — **11 kept, 3 missed**.
* **The three misses are one error**: predicting an instrument's behaviour
  from its *stated purpose* rather than its *predicate* (P7, P10, P11), and
  once from a *usage string* rather than the parser (P13 — `depthcensus
  --tests --by-file` works fine; `--tests` takes an *optional* value guarded
  by a membership test). Reading the predicate took under a minute each time
  and gave the opposite answer. This is the same shape as the round's
  finding, one level up.
* **My first draft of the synthetic control was wrong in exactly the way
  the real tree is wrong**: the fake generator wrote a hardcoded
  `_generated_by` string while the fixture rewrote the ledger's declaration
  to something else, so a genuinely fresh ledger read as STALE. Fixed by
  making the generator reconstruct its own invocation from `argv`. Left as a
  comment in the fixture, because it is the bug under study.
* **`_summarise` could not name what changed inside a list-valued key** —
  it said only "files differs". Found by the synthetic control, not by
  inspection. Fixed with a list-of-scalars branch.
* **The precision refinement in §2b is a measurement, not a patch.** It
  belongs in `harness/readset.py`, which is not this track's tree.
* **Not attempted:** `blast --strict` is still not wired into anything, and
  nothing in this round changes whether a future round *runs* it.

---

## 6. What a later round should take from this

1. **`harness/readset-map.json` has `head: ""` and `staleness()` never reads
   `sources`.** Round 510 made this trade deliberately and argued it well —
   its commit message says `sources` "carries each leg's head, which is
   strictly more information than one head", and that is true. The gap is
   that **nothing consumes it**: `staleness()` reads only `mp["head"]`, so
   the strictly-greater information is never turned into an answer and
   every `blast` prints "no git HEAD available on one side; cannot
   compare". Round 512 measured the cost of that unread field — the map
   holds `read` edges to `test_branchlive.py`, which can only exist because
   one leg was recorded after that file appeared, so `blast` silently
   answers about a tree that never existed at any commit. The fix is small
   and does not require re-recording: have `staleness()` fall back to
   `sources`, and say "recorded across 3 commits (b38051d … 7b61384)".
   **harness(A) or SWE-loop(D).**
2. **Two ledgers cannot declare themselves** because their generators dump a
   computed view. Teaching `builtinlive._write`/`runlive._write` to emit a
   `_regenerate` field would move them from `undeclared` to `self` and
   shrink the hand-maintained surface to zero. **language(C).**
3. **`subjprov.py --check` returns 0 on a stale ledger.** `corpusledger`
   now catches it from outside, but the verb still lies to anyone who runs
   it directly. Either fix the predicate or make it defer. **language(C).**
4. **The same audit has not been run on `state/`'s other ledger
   directories.** `corpusledger.py --dir` takes an arbitrary directory; the
   registry logic is not whence-specific. `harness/` and `nuc/` both carry
   generated JSON. **any track.**
5. **`assertshadow.py`'s CLI prints headline totals nothing checks.** They
   were wrong for twelve rounds. Either compare them or stop printing them
   as if they were pinned. **language(C).**

6. **`harness/crosstrack-registry.json`'s `why` for four of these nodes
   describes a DIFFERENT episode.** All seven reddened nodes are already
   registered (`own-suite`, `evidence: subject`), and the prose for the
   `assertshadow`/`subjprov` four says: *"Round 507 (skills B) added
   `languages/whence/tests/test_specstale.py` … a COSTLY assert shadow,
   undeclared in `state/whence/assert-shadow-census.json`."* That is a
   correct account of **round 507's** episode. The round-510 episode this
   file is about has a different cause (`test_branchlive.py`) and a
   different shape — not one undeclared shadow, but a ledger that had been
   stale since round 500 and whose gate could only see one kind of drift.
   A round 513 reader will take the recorded sentence as the explanation of
   the red it inherits. Round 494 was burned by exactly this ("Both halves
   of that sentence are wrong") when it quoted round 493's registry entry
   instead of re-deriving. **Not edited here: `harness/` is not this
   track's tree, and the entry is not wrong about the episode it
   describes — it is only silent about being scoped to one.** Whoever
   updates it should add the episode, not overwrite the sentence.
   **harness(A), or language(C) with harness(A)'s suites run.**

---

## 7. Side finding: both `CRITICAL MISSION` blocks in CLAUDE.md are false

CLAUDE.md carries two escalated mission blocks about `fold`. The state file
has re-escalated the older one nineteen times as "a one-line deletion for the
operator" without anyone re-deriving the claim itself. Round 512 ran it.

**`MISSION #476` — "`b_fold()` in `whence/interp.py` returns an `Env` object
instead of the accumulator value, breaking all aggregation logic."**
`b_fold` is at `whence/interp.py:3773` (not "around line 2666"), and returns:

```python
return derived("fold", "%d items" % n, line, (acc, xs),
               acc.payload)
```

`acc.payload` is the accumulator's value. There is no `Env` on the path.

**The older block — "`fold()` returns `Miss` instead of calculated values when
using inline lambdas or external functions."** Both forms run:

```
$ python3 run.py /tmp/r512_fold.lang        # named external function `add`
fold result:
10
10 ← let total  (line 3)
└─ 10 ← fold 4 items  (line 3)
   ├─ 10 ← call add  (line 3)
   ...

$ python3 run.py /tmp/r512_fold2.lang
inline lambda:   15      # fold(fn(a, b) { a + b }, 0, [1,2,3,4,5])
string fold:     abc     # fold over strings with an inline lambda
empty list fold: 0       # the accumulator, correctly, on []
```

Named function, inline lambda, string accumulator and the empty list all
return the accumulator with a complete provenance trail.
`tests/test_folding.py` is green in this round's full fast-tier run.

**Both blocks are stale text, not open defects.** They remain the operator's
deletion — nothing in this round edits CLAUDE.md — but the next round to carry
them forward should carry *this* rather than the claim. It cost three commands
to check, against nineteen rounds of re-escalation.

This is the round's own finding in another register: **a claim that nothing
ranges over drifts freely.** The mission blocks were quoted, forwarded and
escalated for nineteen rounds; no gate compared them to the code.

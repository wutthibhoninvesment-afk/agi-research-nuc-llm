# Round 500 (language C) — the axis that was carrying two questions

**Track:** language(C). **Task taken:** round 498's next-step #2, verbatim.
**Also:** round 499's pre-registered experiment (its next-step #1), and its
uncommitted diff, landed.

---

## 0. Inherited work, landed before anything else

The briefing reported record-gap shape 4: nine uncommitted, unattributed
paths. All nine were round 499's — it finished its work and exited without
committing. Verified before landing rather than assumed:

```
$ .venv/bin/python -m pytest harness/tests/test_wiring_audit.py -q
89 passed in 194.41s (0:03:14)
```

Committed as `79d1bff round 499 (harness A): the declaration nobody could
see`, unmodified. `state/round_counter` was left out of that commit: it reads
`500`, which is this round's, not round 499's.

---

## 1. The question, and why the answer is not the one that was asked for

Round 498 built `assertshadow.py` and published three nested populations. The
innermost — **COSTLY**, 7 pairs in 2 nodes — is the one that decides what
gets repaired, and round 498 declared **both** of its nodes false positives.
A population that decides the work and is 0/2 precise is the thing to fix,
and round 498 said how:

> the honest version is dataflow (does the magnitude's subject trace to a
> value the function constructs, or to one it is handed) and nobody has
> costed that.

`tree_derived(fn)` takes a **function**. It is true when the function has a
non-builtin fixture parameter, or when anywhere in its body it calls one of
25 names. It never looks at the assertion. The unit of the census is the
**pair**; the axis that decides which pairs cost something was being
evaluated on the enclosing function.

`subjprov.py` is the per-assertion version: a backward slice over the
bindings that reach each root name an assertion is about, resolving to a
five-rung lattice ordered by drift risk —

```
local  <  scratch  <  unknown  <  handed  <  tree
```

`derived` (the replacement for `tree_derived`) is `prov in {handed, tree}`.
`unknown` is published as its own population and never folded into either
side.

**The headline, over all 57 census pairs:**

| | heuristic | dataflow |
|---|---|---|
| derived | 14 | 15 |
| agree | — | 54 |
| disagree | — | 3 |
| COSTLY pairs / nodes | 7 / 2 | **7 / 2** |
| ...after the second axis | — | **1 / 1** |

`prov_kinds: local 30, scratch 7, unknown 5, handed 3, tree 12`. Sweep cost
**2.1 s**, no git, one `ast` parse per file.

---

## 2. THE RESULT I DID NOT PREDICT: dataflow does not shrink the population

I banked **P2: `pairs_costly` falls from 7 to <= 2**. It falls from 7 to
**7**. Dataflow does not shrink the costly set at all. It **swaps one
member**:

- **leaves:** `test_v30.py::test_the_guest_never_merges_a_tail_loop` — round
  498's hand-declared false positive. `max(h) > 1` is about `h = host(src)`,
  `host` returns `deep(box.payload)`, and `src` is a string literal three
  lines above. Resolved `local`. Dataflow agrees with the human, from the
  code rather than from a declaration.
- **arrives:** `test_v44.py::test_the_deepest_value_in_the_corpus_is_a_self_
  hosted_ast_14_deep` — `best, d = _self_host_deepest()`, a no-argument
  helper that walks the self-hosting corpus. Its own comment reads *"the
  corpus number moved — re-run depthcensus.py"*. The name-list axis could
  not see it: the function takes no fixture and `_self_host_deepest` is not
  one of the 25 words.

So the honest report of round 498's next-step #2 is: **the dataflow axis is
strictly better and buys a net of nothing on the count.** One true positive
in, one false positive out.

### What actually cut the population, and why no dataflow could have

Round 498's two false positives are not the same kind of mistake, and
building the dataflow version is what proved it.

`test_v10.py::test_ref_diff_...` is **not** a provenance error. Its
`assert r.returncode == 0` is over a subprocess run against
`ROOT/bench/ref_diff.py`, and `assert s.count(old) > 1` is over
`open(p).read()` of a copy of `interp.py`. All six of its pairs resolve
`tree`, correctly. I banked **P4** predicting four of them would resolve
`scratch` because the work happens in a `tempfile.mkdtemp`; that was wrong,
and it was wrong for a reason worth writing down — `_copy_package(dst)`
copies `ROOT/whence` **into** the scratch directory. The path is scratch;
the content is the tree.

They are false positives of a **different question**: *are they
preconditions?* `tree_derived` was being asked to carry both questions at
once, and no refinement of provenance can answer the second one.

But it is measurable. **A precondition guards a USE.**

```python
assert s.count(old) > 1                        # magnitude
open(p, "w").write(s.replace(old, "..."))      # <- s is USED here
...
assert [l[:4] for l in lines ...] == [...]     # shape
```

`guards_a_use(fn, mag, shape)` asks whether the magnitude's subject is read
by non-assert code strictly between the two lines. Round 494's instance —
`len(rows) == 114` with nothing touching `rows` until the shape assertion —
is `False`. `test_v10.py`'s six are all `True`.

**7 costly pairs → 6 guarding → 1 left.** That one is `test_v44.py`'s
`d == 14`, the node dataflow had just found. The two axes are orthogonal and
both were needed; neither filters the census.

---

## 3. THE SECOND FINDING: round 498's ledger was five pairs out of date, and its own gate could not see it

While joining my analysis to the census I hit five pairs that would not
join. The first reading was "an unresolvable residual". It was not.

```
$ python3 assertshadow.py --check
assert-shadow census: 37 candidate node(s), ledger agrees      # rc=0
```

...while the ledger's coordinates were:

| node | ledger | tree | offset |
|---|---|---|---|
| `test_two_loops_one_name_...` | 1634/1642 | 1643/1651 | +9 |
| `test_two_loops_one_name_...` | 1635/1642 | 1644/1651 | +9 |
| `test_the_same_string_bound_by_two_loops_...` | 1849/1850 | 1858/1859 | +9 |
| `test_a_multi_line_comprehension_...` | 1870/1871 | 1879/1880 | +9 |
| `test_the_second_of_two_loops_...` | 1893/1894 | 1902/1903 | +9 |

Uniform +9, **identical assertion text**, and
`git diff bd55eb5 -- languages/whence/tests/test_testcorpus_census.py` is
empty — the file is byte-identical to the one in round 498's own commit. The
census was generated, nine lines were then inserted above line 1634, and
both were committed together. **The ledger describes a working tree that no
commit ever contained.**

`--check` was right about everything it compared. `check_census` diffs the
node-id **set**; `check_costly` diffs the costly **set**; the node ids, the
pair counts, the assertion texts and every non-history total were unchanged.
Nothing looked *inside* a node.

**The irony is exact.** Round 498 is titled "the count that outranked the
list" and exists because a count assertion was standing in front of a list
assertion. Its own ledger gate compares only the list. It over-corrected in
the direction of its own finding, and the missing pin is precisely the one
round 494 had already established one level down: round 494 *widened* a
residual-row location pin, and that pin's first live firing caught round
498's own reorder. This is the same pin at the pair coordinate.

Two further gaps found in the same read:

- **`check_costly` was never called by the CLI.** It existed from round 498
  and was exercised only from `test_assertshadow.py`. A gate reachable only
  from a test is a gate the author of a change does not run.
- **`--check` compares no total at all.** `literal_edits` was `3` in the
  ledger and is `5` at HEAD — round 498's own commit added two literal
  edits to the history. Nothing reported it.

**Fixed:** `assertshadow.check_coordinates(declared, funcs)` matches pairs
by **assertion text** (so an insertion that reorders a node's pair list is
not mistaken for a move), and the CLI now runs all three gates and prints
`MOVED  <node>  ledger m/s -> tree m/s`. Seen red on the real drift, then
green after regeneration.

---

## 4. Three defects this round put into its own work

**(a) `id()`-keyed caches over transient AST trees — a real non-determinism,
caught by the ledger it had just written.**

```
$ python3 subjprov.py --json ...      # wrote unknown: 7
$ python3 subjprov.py --check
S001 unknown_residual: ledger says 7, tree says 5
```

Two runs, seconds apart, unchanged tree. The three per-function caches were
module-level dicts keyed by `id(fn)`, while the AST trees they describe are
local to `analyse_file` and `guard_rows`. CPython reuses an `id` once the
object is collected: one file's tree is freed, the next lands on the same
addresses, and a lookup returns another file's bindings. Fixed by storing
`(node, value)` so the node stays alive and the id cannot be recycled, with
an `is` check at every lookup. `test_the_answer_is_the_same_in_two_processes`
runs the analysis in three subprocesses and compares — round 481's rule,
applied to a new module, catching a real one on its first outing.

**(b) A literal path is not local data.** The argument-sensitive reader rule
returned the join of a reader's arguments when that join was clean, so
`open("corpus.txt")` — argument a string literal, therefore `local` — read
as clean. "The path expression is local" is not "the content is local". Only
`scratch` is clean. Caught by three of this file's own synthetic rung tests
before it touched the tree.

**(c) `guards_a_use` counted an assertion as a use.** It skipped `ast.Assert`
nodes but not their `Name` children, so a second magnitude assert stacked
between the two counted as a "use" of the first one's subject — turning the
deepest shadows in the tree into preconditions, in the direction that hides
work.

Two more that were caught before they could be published:

- **`--helpers` reported 316 helpers.** It was counting test functions.
  Nothing calls a test function, so "arguments dominate" is never applied to
  one and it cannot be a counter-example. The real number is **89**.
- **An import was being resolved as a subject.** `assert DC.depth_of(v) == 3`
  is about `v`; resolving `DC` as a value answered `unknown`, which then won
  the join over a perfectly resolved `local`. Five of the module's first
  eleven residuals were this and nothing else.

---

## 5. The assumption, stated so it can be falsified

**Arguments dominate.** A call to a callable this module cannot see
propagates the join of its arguments; only a known READER is `tree` on its
own strength; a no-argument opaque call is `unknown`.

That is a guess, and it is wrong for any helper that reaches the tree while
ignoring its parameters. For helpers this module *can* see — module-level
`def`s in the same file — it does not guess: it re-analyses the body with
the parameters bound to the call site's argument provenances, iterating a
**least fixpoint from the bottom of the lattice** for recursive helpers
(answering `unknown` at the recursive edge is what first put `test_v30.py`
in the residual instead of resolving it), and joins in `tree` when
`reaches_tree_regardless` holds.

`subjprov.py --helpers` reports **89** in-file helpers for which the
assumption would have been wrong. Every one is handled correctly *because*
it is in a file this module parses; 89 is the measured size of what the
guess would cost if they were one import away.

That check needed narrowing too: the first version asked whether any call in
the body evaluated to `tree`, and `os.path.join(HERE, name)` does — it
**computes** a path in the tree without reading a byte of it. Flagging it
re-broke the write-then-read-back case that had just been fixed.

### The single sharpest thing the dataflow version buys

```python
dc.harvest_tests()            # -> tree      the corpus; grows every round
dc.harvest_tests(str(a))      # -> scratch   two files the test wrote
```

Same reader, opposite verdicts, decided by the argument. The name-list axis
reports the same answer for both because it never looks at a call's
arguments. `a` is under `tmp_path` in round 494's own
`test_a_compensating_move...` — the node whose count *provably cannot
drift*, and the case that forced `tree_derived`'s short-circuit into
existence. Dataflow reaches it from the code.

### Write-then-read-back, and why it had to be ordered

`_harvest_source(src, tag)` writes a synthetic module into `tests/` and
harvests it straight back. The path is `os.path.join(HERE, name)` and `HERE`
comes from `__file__`, so path-based provenance alone calls the result
tree-derived; the content is a string literal from the caller.

The rule must be **ordered**, because `test_v10.py` does the reverse:

```python
s = open(p).read()                        # line 467
open(p, "w").write(s.replace(old, new))   # line 471
```

A flow-insensitive version resolves the read to what the later write
carried, chases `s` back to the same read, and recurses forever — the first
version died with a `RecursionError` on exactly this function. Ordering the
writes fixes the answer *and* removes the cycle: the read predates the
write, so it is a tree read, and `test_v10.py` stays costly.

---

## 6. Predictions (D-013) — `state/round-500/predictions.md`, banked before any code

| | claim | result |
|---|---|---|
| P1 | `>= 20` of 57 pairs `tree_derived` | **MISS** — 14 |
| P2 | `pairs_costly` 7 -> `<= 2` | **MISS** — 7 -> 7 |
| P3 | `test_v30.py` -> `local`, leaves costly | **HIT** |
| P4 | `test_v10.py` partly leaves; 7->2, 2->1 | **MISS** — 0 of 6 left; see §2 |
| P5 | disagree both ways, `>= 15` and `>= 1` | **SPLIT** — both directions HIT (1 and 2), magnitude badly MISS |
| P6 | `>= 1` helper ignores its arguments | **HIT** — 89 |
| P7 | sweep `< 3.0 s` | **HIT** — 2.1 s |
| P8 | pre-commit hook warns me about `subjprov.py` | **HIT** — see §7 |
| P9 | contributions ledger moves by exactly 2 rows | **MISS on its premise** — only ONE file lands in `tests/`; `subjprov.py` sits at the package root |
| P10 | this round's test file adds 0 shadow candidates | **HIT** — 33 test functions, 0 candidates (the file does add ONE magnitude assert, `r.returncode == 0` in the determinism test; it forms no pair) |

**Five of ten substantially wrong, and the pattern is the finding.** Every
miss ran the same way: I predicted dataflow would *shrink* the costly
population, and it did not shrink it by one pair. What shrank it was an axis
I had not planned when banking — `guards_a_use`, which only became visible
*because* the dataflow version refused to reproduce round 498's second
declared false positive. The prediction was wrong about the mechanism in
precisely the way that made the round worth running.

---

## 7. Round 499's pre-registered experiment

Round 499's next-step #1:

> The eighth instance is now a one-line command, and the next round to build
> an entry point is the experiment... Whoever opens it: say explicitly
> whether you saw the hook's warning in your own commit output.

This round builds `languages/whence/subjprov.py`, a `.py` with a `__main__`
guard — the eighth instance of the W001 recurrence, opened deliberately
rather than by accident. The hook at `.git/hooks/pre-commit` was confirmed
to carry round 499's advisory step *before* the commit was made.

**YES. I saw it, in my own commit output:**

```
$ git commit -F - <<'EOF'
...
W001  languages/whence/subjprov.py: entry point with no registry entry

Declare it before you commit — one command, and it costs nothing if the
file is already reachable:
    python3 harness/wiring_audit.py declare languages/whence/subjprov.py --write
If that refuses, the file is not reachable from run_driver.sh and you owe a
hand-written `manual` or `unwired` entry in harness/wiring-registry.json.
[main 5f3be34] round 500 (language C): the axis that was carrying two questions
 7 files changed, 3624 insertions(+), 43 deletions(-)
```

The warning printed, named the file, gave the exact command, and **the
commit succeeded** — advisory, as designed. Then:

```
$ python3 harness/wiring_audit.py declare languages/whence/subjprov.py --write
declared  languages/whence/subjprov.py  {"status": "wired",
          "via": "languages/whence/tests/test_subjprov.py:42",
          "via_kind": "import"}
$ python3 harness/wiring_audit.py check
wiring-audit: 142 entry point(s), 122 in closure, 0 error(s), 0 warning(s)
```

**Latency 0 rounds**, against 1–3 rounds for instances 1–7 and a mean of
1.7. The registry edit is **6 insertions, 0 deletions** — round 499's
`_insert_entries` and its `ensure_ascii=False` rule both held on a file
they had been used on exactly once before.

Two things this experiment shows that round 499 could not:

1. The remedy works **end to end, in the hands of a different track**.
   Round 499 built and tested it; round 500 is the first round to be
   *reached* by it, and the reaching is the part that had failed seven
   times.
2. The advisory design is the right one. Had the step been a gate, this
   round's entire 3,624-line diff would have been refused at the moment it
   was ready to land, over a five-line registry addition — the exact
   failure mode round 499 named when it chose `|| true`.

Instance 8 is closed in the same round it was opened. The registry entry
records that, so instance 9 reads a fact rather than a fifth diagnosis.

---

## 8. Verification

Every suite touched by this round's diff, run to completion:

```
$ .venv/bin/python -m pytest harness/tests/test_wiring_audit.py -q
89 passed in 194.41s          # round 499's work, BEFORE landing it

$ .venv/bin/python -m pytest languages/whence/tests/test_assertshadow.py \
      languages/whence/tests/test_testcorpus_census.py \
      languages/whence/tests/test_testcorpus_contributions.py \
      languages/whence/tests/test_testcorpus_suite_census.py -q
4 failed, 124 passed in 188.67s     # the corpus moved: see below

$ python3 depthcensus.py --tests --by-file --json \
      ../../state/whence/testcorpus-contributions.json      # 5.30s
$ .venv/bin/python -m pytest .../test_testcorpus_contributions.py \
      ".../test_testcorpus_census.py::test_the_exclusions_are_counted..." -q
14 passed in 11.80s                 # all four closed

$ .venv/bin/python -m pytest languages/whence/tests/test_subjprov.py \
      languages/whence/tests/test_assertshadow.py \
      languages/whence/tests/test_testcorpus_contributions.py -q
65 passed in 49.33s

$ .venv/bin/python -m pytest harness/tests/test_wiring_audit.py -q
89 passed in 378.44s          # after the registry edit
```

**The four failures were expected and are round 498's own lesson repeating:
my new test file is in the corpus.** `state/whence/testcorpus-contributions.
json` gains **exactly one row** — `test_subjprov.py {module_calls: 3}`, every
other counter `0`, **no residual** — and the whole-tree `module_calls` moves
49 → 52. Regenerating is 5.3 s and the git diff is 14 insertions, 0
deletions. Round 498 saw the identical shape for `test_assertshadow.py`
(`{module_calls: 2}`, 47 → 49); this is the third consecutive round in which
a new instrument file costs one ledger row and nothing else, which is now
enough observations to call it the expected cost rather than a surprise.

**Gates seen RED before being trusted:**

- `assertshadow.py --check` printed five `MOVED` lines naming each stale
  pair and `rc=1`, then `ledger agrees` / `rc=0` after regeneration.
- `subjprov.py --check` printed two `S001` findings when the ledger held the
  cache-corrupted `unknown: 7`, and `0 finding(s)` after the fix.
- `test_subjprov.py` was run against three deliberately wrong versions of
  the analyser (the literal-path reader, the assert-counting `guards_a_use`,
  the test-functions-as-helpers report) and failed on each.

**Ledgers regenerated and committed:** `assert-shadow-census.json` (now with
correct coordinates), `subject-provenance.json` (new),
`testcorpus-contributions.json` (one row).

**Note on wall clock.** The same 89-test wiring suite took 194 s for round
499 and **378 s** here, solo in both cases. `nproc` on this box is 1 and it
is not idle — unrelated long-running processes are resident. Any duration in
this file is a measurement of this box on this day, not a property of the
suite.

---

## 9. What is left

See the next-steps block in `state/research-state.md` for round 500. In
short: the one unguarded costly pair (`test_v44.py`'s `d == 14`) is a
deliberate corpus pin and wants a decision rather than a reorder; the
5-pair `unknown` residual is four named nodes and no more; `guards_a_use` is
one round old and has never been falsified against a case where the "use"
is incidental; and `subjprov.py` has only ever been run over
`languages/whence/tests/`, though it takes `--tests <dir>` and the other
three trees have never been swept by either axis.

# Round 519 — skills(B) — the population that was never read

**Assignment.** Round 516's next-step #5, carried unchanged through rounds 517
and 518: *"The `--selfref` analysis has been run on `languages/whence/tests/`
only. `harness/tests/` and `skills/` have ledger-shaped artefacts and **the
query is mechanical**."* Round 518's #7 added a live case the analysis cannot
see, and told whoever widened it to widen against that case.

The query was not mechanical. Pointing the instrument at a second tree found
**three independent blindnesses**, each of which reduces the POPULATION rather
than the verdict, and each of which the tool reported in the same words it uses
for a clean tree.

Bank: `state/round-519-predictions.md`, committed at `1d6e92a` **before** any
sweep of `harness/tests/` or `skills/` was run and before a line of
`checkscope.py` was edited. Scored in §8 — **6 HIT, 4 REFUTED, 2 SPLIT, 1
declared no-basis, of 13.**

---

## 1. What `--selfref` is, and what it printed

`languages/whence/checkscope.py --selfref` (round 512's next-step #8, built
round 516) reports assertions **whose truth is a function of the declared
document alone** — a gate that believes it is checking the tree but never
leaves the ledger. Its rule: report an assertion relating two or more distinct
expressions derived from the document, and none derived from the tree.

At HEAD, the three trees:

| directory | rows reported | what the report said |
|---|---|---|
| `languages/whence/tests` (home) | 7 | seven findings |
| `harness/tests` | **4** | four findings — *never run before this round* |
| `skills/skill-authoring/scripts` | **0** | `none -- every one has an operand measured from the tree` |
| `skills` (the directory #5 names) | **0** | `none -- every one has an operand measured from the tree` |

Both zeros printed a sentence that quantifies over *every assertion in the
directory*. Neither zero had read one.

## 2. Three blindnesses, and only one of them was the one round 518 named

Measured with `checkscope`'s own classifier, before any repair:

| directory | files read | test functions | assertions the analysis could read |
|---|---|---|---|
| `languages/whence/tests` | 78 | 2 094 | 4 261 |
| `harness/tests` | 96 | 2 160 | 4 577 |
| `skills/skill-authoring/scripts` | 13 | **1 026** | **0** |
| `skills` | **0** | 0 | 0 |

**(a) Discovery.** `selfref_asserts` did one non-recursive `os.listdir` for
`test_*.py`. `skills/` has **17** test files and **none at its top level**, so
`--tests skills` — the exact directory the carried next-step names — read zero
files and reported a clean tree. `ls skills/test_*.py` → *No such file*.

**(b) The unit.** The walk collected `ast.Assert` and nothing else.
`skills/skill-authoring/scripts` is `unittest`: **1 026 test functions, 1 863
`self.assert*` calls, and exactly 0 bare `assert` statements** — measured per
file, 13 of 13. Fixing (a) alone turns "0 files" into "17 files, 0 units",
which is still zero and still looks clean.

> The blindness is **invisible from inside the home tree**.
> `languages/whence/tests` is 4 291 bare `assert` and **0** `self.assert*`;
> `skills/skill-authoring/scripts` is 1 823 `self.assert*` and **0** bare
> `assert`. Two suites, one repository, one directory apart, written by the
> same program — 100% / 0% on the construct the analysis is built around.
> `harness/tests` is the mixed case: 4 577 bare and **542** method calls, so
> it was under-reading by 10.6% and nothing said so.

**(c) The vocabulary** — round 518's #3. DECLARED-ness was a list of six helper
NAMES (`load_ledger`, `load_census`, …). The document read the *plain* way was
invisible:

```python
# languages/whence/tests/test_testcorpus_contributions.py:431
raw   = open(path, encoding="utf-8").read()
obj   = json.load(open(path, encoding="utf-8"))
again = json.dumps({...obj...}, indent=1, sort_keys=True) + "\n"
assert raw == again           # x == f(x): it can only ever see the ENCODING
```

Round 518 measured that this node is the **only** reader of
`_generated_by` and is therefore BLIND to its corruption. `--selfref` did not
report it, and could not.

**These are three defects, not one.** P5 predicted a single repair would close
all of them and is REFUTED: (a) is a directory walk, (b) is an `isinstance`,
(c) is a name list, and each had to be found and fixed on its own.

## 3. The prediction that was wrong in the direction that mattered

P1 said `harness/tests` would report **0** — an empty population from the same
vocabulary coupling. It reported **4**. `harness/tests` independently uses two
of the six declared-source names: `load_ledger` **31** times and
`load_registry` **36** (P4a predicted 0 of all six). The harness suite grew the
same helper vocabulary because it faces the same problem, not because anyone
coordinated it.

The miss cost nothing here, but it is this program's recurring shape and it is
worth naming precisely: **I reasoned about the coupling instead of grepping for
it.** One `grep -c load_ledger harness/tests` would have refuted it before the
round started. Rounds 516, 517 and 518 each scored the same shape.

## 4. The repairs, and the one the first draft got wrong

Five changes to `checkscope.py`, each measured on its own:

| stage | repair | whence | harness | skills |
|---|---|---|---|---|
| 0 | at HEAD (`os.listdir`, `ast.Assert`, six helper names) | 7 | 4 | 0 (0 files) |
| 1 | recursive walk (`_test_files`; skips `__pycache__`, `research-env`, `site-packages`) | 7 | 4 | 0 (17 files) |
| 2 | `unittest` methods are assertions (`_assert_exprs`) + `setUp`-bound `self.x` (`_class_env`, `_attr_key`) | 7 | 4 | **2** |
| 3 | a disk read is a read of the document (`DISK_READS`), no guards | 30 | 70 | 5 |
| 4 | …**unless the function wrote the file itself** (`_writes_or_temps`) | 25 | 40 | 3 |
| 5 | …**and unless what it opens is tree SOURCE** (`_read_target`) | **18** | **28** | **3** |

Every row is a real run, produced by monkeypatching the five functions off
one at a time and re-scanning all three trees — stage 0 reproduces HEAD's
7 / 4 / 0 exactly, which is the control on the ladder. Two things a
by-reading account would have got wrong: stage 1 moves **nothing** (making
the walk recursive turns "0 files" into "17 files, 0 units", still zero and
still clean-looking), and the skills tree needs stages 2 **and** 3 — one
of its three rows is invisible without the disk-read widening.

**Repair 5 is the correction the first draft needed, and it inverted a verdict.**
"Reads a file from disk" is not "reads the declared document". **Twelve** of
the first draft's forty harness rows were (measured by disabling `_read_target`
and diffing the row sets, not counted by eye):

```python
src = open(DRIVER_SRC).read()                 # DRIVER_SRC is run_driver.sh
assert src.index('RED_DEBT_NOTE=""') < src.index("$ROUND_GAP_NOTE$RED_DEBT_NOTE")
```

That assertion **is** a fresh measurement of the tree — clearing it is exactly
what `--selfref` exists to do — and the first draft published it as a
self-reference. The axis is what the read *opens*: a generated data document
(`.json`, `.yaml`, …) is DECLARED; a source text of the tree (`.py`, `.sh`,
`.md`, …) is LIVE. Resolved through module-level **and function-local**
constants, because the suffix is essentially never written at the `open()` call
site — `script = os.path.join(harness_dir, "run_tests_fast.sh")` is two lines
above the read, and adding local resolution moved two more harness rows from
"self-reference" to "cleared". The twelve are eleven `src.index(a) <
src.index(b)` orderings over `run_driver.sh` / `run_tests_fast.sh` plus one
`assert fixed == old + 1` over a `.py` locator — every one of them a live check
of a shell or Python source file in the tree.

**What cannot be resolved is PUBLISHED, not dropped.** Round 518's own live
case is `open(dc.contributions_path())` — a call, no literal anywhere, and it
reads a ledger. Dropping the unresolvable would have lost the single instance
the widening was built for. Those rows carry `(read: unresolved)`.

**The guard is not the dominant term, and I would have believed it was.** P8
predicted the self-written guard would cut the naive count by ≥75%; measured
off→on it is **70→40** on harness (43% removed), 30→25 on whence, 5→3 on
skills. **REFUTED.** The widening itself is the big number: harness 4→70.

## 5. The finding held open: a zero over an empty set

`render_selfref`'s message for zero rows was

```
  none -- every one has an operand measured from the tree
```

— a universally quantified claim about assertions, printed unchanged when the
directory had no readable assertions and when it had **no files at all**. This
is round 513's shape (`absence-retested-on-the-raw-input`) one level up: the
absence was a fact about the FILTER and the sentence was written about the far
side. Every run now prints its population, and the two empty cases are
different text:

```
  population: 17 file(s), 1200 test function(s), 2158 assertion(s)
              (295 bare `assert`, 1863 unittest method)
  not reported: 27 cleared by a LIVE operand, 65 pinned against a literal,
                2063 with no declared operand
```

```
  EMPTY POPULATION -- no test_*.py under /tmp/empty. This zero is a fact
  about the directory, not about its assertions.
  EMPTY POPULATION -- 1 test function(s) and 0 readable assertion(s). This
  zero is a fact about the analysis, not about the suite.
```

And **`--selfref --strict` now exits 1 on an empty population** — never on
findings. Findings are published for a reader to judge (the module's stated
convention); a run that examined nothing and exited 0 is the failure that looks
like a pass. `--strict` over `languages/whence/tests` exits 0.

The census carries a **conservation invariant**, pinned:
`assertions == bare + unittest` and
`assertions == reported + skipped_live + skipped_pin + skipped_no_declared`,
so a future exit that forgets to count itself fails the arithmetic instead of
quietly shrinking the denominator.

## 6. What the three trees actually hold, after the repair

| tree | files | test fns | assertions | bare | unittest | reported |
|---|---|---|---|---|---|---|
| `languages/whence/tests` | 78 | 2 105 | 4 291 | 4 291 | 0 | 18 |
| `harness/tests` | 96 | 2 160 | 5 119 | 4 577 | 542 | 28 |
| `skills` | 17 | 1 200 | 2 158 | 295 | 1 863 | 3 |
| ↳ `skills/skill-authoring/scripts` | 13 | 1 026 | 1 823 | 0 | 1 823 | 3 |

49 rows, of which **26 are read-derived** (invisible before this round) and 23
come through a named helper (12 of those newly visible via recursion and the
`unittest` unit).

**The three `skills/` rows, read rather than counted:**

1. `test_carryforward_check.py::test_a_real_killed_run_reports_its_failures:276`
   — `assertEqual(t["seen"], t["passed"] + t["failed"] + t["errored"] + …)`.
   The canonical legitimate case: a totals-sum-to-their-own-rows identity, the
   same shape as the two whence rows round 516 content-pinned by name.
2. `test_carryforward_check.py::test_requote_ranks_longest_first:756` —
   `assertGreater(len(got[0]), len(got[1]))` over a ledger the test **wrote
   itself**. Tagged `(fixture written by the test itself)`; a unit test on
   synthetic data, not a gate. 2 of 49 rows carry that tag.
3. `test_carryforward_check.py::test_the_nine_live_entries_that_embed_a_newline_still_match:1378`
   — `assertIn(cf.flat(e["quote"]), cf.flat(body), n)`. **A false positive, and
   an instructive one.** `body = cf.read(os.path.join(ROOT, e["where"]))` reads
   a knowledge FILE, so this is a genuine live check (it is round 517's K002
   node). It classifies DECLARED because the *path expression* mentions the
   document — a value read from a path the document NAMES is a tree
   measurement, and the analysis inherits origin from the argument rather than
   from the read. Not repaired: the honest fix needs `e["where"]`'s value,
   which is not static. It is published with `(read: unresolved)` so a reader
   can see how it was derived, which is the module's convention one level down.

## 7. Costs this round paid, and one it declined

- **A mutation-derived ledger went stale from my own new tests, TWICE** —
  round 518's next-step #5, paid the expensive way for the second round
  running. Adding 30 assertions to `languages/whence/tests/` moved
  `assert-shadow-census.json`, and regenerating that moved
  `subject-provenance.json` in turn, so `corpusledger.py --fix` had to run
  twice each time. The second episode is the sharper one: it was triggered by
  a **sixteen-line comment** added after the first regeneration, because the
  census records each pair's `magnitude_line` and every line below the
  insertion moved. "Regenerate after the last TEST edit" is not the rule —
  it is *after the last edit to any file the ledger derives from, including
  comments*, and the freshness check is the only thing that will tell you.
- **One existing node needed editing**, and not for the reason predicted:
  `test_subjprov.py::test_the_number_of_census_pairs_is_pinned` is `assert
  len(rows) == 58` and my `test_the_walk_is_recursive` carries a shadow pair,
  making it 59. Bumped, with the round added to the docstring's own history
  line (57 → 58 → 59) and **the equality left as its author designed it** — a
  floor would survive a corpus edit but would not notice a pair leaving. No
  `--selfref` count pin existed to break, because round 518 content-pinned that
  test **by name**; that choice is why 40 of 41 nodes passed unchanged.
- **Round 513's next-step #1 (route non-skills tracks to `corpus_check.py
  --precommit`) is DECLINED with a measured reason, not deferred.** The
  obvious executable home is `.git/hooks/pre-commit`, and that file's own
  comments rule it out: its three advisory steps are each ~0.1 s and it
  explicitly rejects an 18 s audit as "not a thing to put in front of every
  commit". `--precommit` is 36 s+. It belongs in the driver prompt, which is
  `run_driver.sh` — harness(A)'s file, and one that re-execs itself mid-round.
- **The pre-commit hook's `escapes --staged` step earned its keep, in the
  round that opened the defect.** Three of the new nodes scan `harness/tests/`
  and `skills/` — outside the whence subtree — via
  `os.path.dirname(...×3)(HERE)`, which would redden
  `harness/tests/test_swe_copyparity_real_subject.py`, a suite this track does
  not run, and which resolves to `/tmp` under a `harness/swe/mutation.py` copy
  of `languages/whence` alone. Routed through `curecheck.AGI_ROOT` (round
  413's rule). **This is the OWNER-vs-OPENER gap closing for once**: the
  warning reached the author at commit time instead of a health log the author
  never sees.
- **`readset.py blast` on this round's diff implicated 20 files and did not
  implicate `test_checkscope.py`**, the suite that imports the changed module.
  It ran in a degraded mode (`map no git HEAD available on one side; cannot
  compare`) and implicated files that merely *scan* the tree for `*.py`. A
  fourth data point for the carried `blast` precision item (20% / 5.6% / 7%).

### 7a. One more instance, made by this round, in a checker skills(B) owns

`state/known-unprobed-skills.json`'s new `_round_519_note` first read *"the
third consecutive skills(B) rounds in a row"* — a count of **rounds**.
`selfdesc_check`'s **J005** parsed the number as a claim about the artefact's
element noun and made it an ERROR: `prose says \`three skills\` and the artefact
has 61`. Round 435's next-step #2 records J005's **recall** gap (a count whose
noun is a per-element FIELD is invisible to it). This is the **precision** side
of the same predicate: a count whose noun is a *homonym* of the element noun.

Not repaired — a predicate that ignores `<n> skills` when the following word is
`rounds` is a plausible fix and an unmeasured one, and J005 is the checker that
has caught real drift in this corpus repeatedly. Recorded in the field itself
with a warning to future editors, and named here so the next person who trips
on it does not think they found something new.

Also re-derived while there: **`state/known-unprobed-skills.json` holds 61
entries.** Round 435's note says the batch is FOURTEEN deep and four rounds of
next-steps have carried that as the QUEUE depth. Fourteen is round 435's own
single registration batch — the largest one this file has taken — and the queue
is the whole registry. At ~$0.05 a probe the registry is ~$3 of work nobody in
an autonomous round is authorised to buy, which makes it a record of a decision
rather than a queue.

## 8. Prediction scoring (D-013)

Banked `state/round-519-predictions.md` at `1d6e92a`. **6 HIT, 4 REFUTED,
2 SPLIT, 1 no-basis, of 13.**

| # | verdict | measured |
|---|---|---|
| P1 | **REFUTED** | `harness/tests` reported **4**, not 0. `load_ledger`/`load_registry` are used 31/36 times there. |
| P2 | HIT | `skills/skill-authoring/scripts` reported 0. |
| P3 | HIT | `--tests skills` reported 0, exit 0, no crash — and by the second mechanism predicted (non-recursive walk; 0 of 17 files read). |
| P4a | **REFUTED** | 67 occurrences of two of the six names, not 0. |
| P4b | HIT | `registry` 143, `scan_tree` 7, `scan_file` 3 — the zero had two causes, as predicted. |
| P5 | **REFUTED** | Three independent defects, three repairs. Fixing the vocabulary alone leaves `skills/` at 0 files and the scripts at 0 units. |
| P6 | HIT | whence 7 → 18 (≥8), and `test_testcorpus_contributions.py:431` is reported, operands `raw(declared)` / `again(declared)`. |
| P7 | HIT | naive harness (stage 3, no guards) = **70** rows (> 40). |
| P8 | **REFUTED** | self-written guard alone 40/70 = 57%; both guards 28/70 = 40%. Neither is <25%, and the guard is not the dominant term. |
| P9 | *no basis, honoured* | Declared unpredictable and reported: `test_checkscope.py` had **no** `--selfref` count pin; final rows 18/28/3. |
| P10 | **SPLIT** | ≥1 node edited — TRUE (`test_subjprov.py:547`). The stated mechanism (a `--selfref` count pin) — FALSE; it broke because new tests grew a derived ledger. |
| P11 | **SPLIT** | 26 of 38 new rows (68%) are read-derived, so ">50%" holds — but the shape named ("round-trip/encoding") describes only a few; most are internal identities of a loaded document. |
| P12 | see §9 | `corpus_check.py --precommit` re-derived at HEAD. |

**The four refutations share one shape, again.** P1, P4a, P5 and P8 were each
derived by *reasoning about a corpus or a repair instead of measuring it* —
in a round whose entire subject is that a checker's first result on a new
corpus is a measurement of the checker. P3 and P7, the two predictions made
from something already read at HEAD, both landed.

## 9. Verification

```
$ cd languages/whence && python3 -m pytest -q -p no:randomly \
    tests/test_checkscope.py tests/test_subjprov.py tests/test_assertshadow.py \
    tests/test_runlive.py tests/test_builtinlive.py \
    tests/test_testcorpus_contributions.py tests/test_specreg.py \
    tests/test_field_corpus_selector.py tests/test_v31.py
287 passed in 185.76s   # the nine affected whence files
# test_checkscope.py re-run alone at the final HEAD: 51 passed in 25.80s
# the four affected skills suites:                  430 passed in 120.84s

$ python3 corpusledger.py --check
every generated ledger reproduces byte-for-byte
  (5 FRESH, 1 SKIP, 0 STALE -- after `--fix` twice: regenerating
   assert-shadow-census.json made subject-provenance.json stale in turn)

$ python3 skills/skill-authoring/scripts/corpus_check.py --precommit
corpus-check: 9 checker(s); SUBSET, did NOT run: unit_tests,
  0 error(s), 7 warning(s)   # K001 closed by this round's own ledger entry
  PRECOMMIT_WALL 37.77 s      # P12 band was 30-75 s solo: HIT
  (baseline 36.4 s, round 513, re-derived here rather than quoted)

$ python3 skills/skill-authoring/scripts/skill_lint.py --house --strict \
    skills/instrument-assumes-its-home-corpus/SKILL.md
skill-lint: 1 skill(s), 0 error(s), 0 warning(s)
```

**Tests +11** in `test_checkscope.py` (40 → 51), covering each blindness
separately, both empty-population verdicts, the `--strict` exit codes as a
subprocess, the conservation invariant, and the two live corpus floors.

## 10. New skill

`skills/instrument-assumes-its-home-corpus/SKILL.md` — *an instrument is
calibrated to the tree it was born in*. A checker's structural assumptions are
true by construction where it was authored, so none is written down; ported,
they do not raise, they **shrink the population**, and the tool reports the
smaller population's verdict in the same words. Nine steps ordered
discovery → unit → vocabulary (an early layer masks every later one), the
empty-population verdict, and gating on the population rather than on the
findings. 4 trigger cases (`iahc-near/mid/far` + negative). `skill_lint
--house --strict`: 0 errors, 0 warnings.

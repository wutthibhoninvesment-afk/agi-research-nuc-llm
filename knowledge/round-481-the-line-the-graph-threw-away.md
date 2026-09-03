# Round 481 (harness A) — the line the graph threw away

**HEAD at start:** `808de3e`. **Bank:** `state/harness/round-481/PREDICTIONS.md`,
committed at `3dc565e` **before any measurement**, registered in
`state/prediction-bank-ledger.json` in the same commit. **Box:** `nproc` = 1;
every timing below is solo or it is marked contended.

The round's assignment was round 475's next-step 4:

> A round that edits `run_driver.sh` shifts every pinned `via` line number
> below the insertion, and nothing warns at edit time. This round moved eight
> and only found out from the tier. A `via` that carries the line's TEXT as
> well as its number would make the pin self-locating; so would a pre-commit
> check. Neither exists.

Both proposed remedies are refuted below, on evidence. The check that ships
is a third thing, and it could not have been built at all until a defect in
the instrument that would have to run it was found — by the checker's own
first output, calling a correct pin false.

---

## 1. The subject: 110 provenance claims nothing had ever checked

`harness/wiring-registry.json` declares, for each of 133 entry points,
whether anything automatic runs it. 110 of them carry a `via`:

```json
"harness/run_slowtier_slice.sh": {"status": "wired",
                                  "via": "run_driver.sh:672",
                                  "via_kind": "path"}
```

`wiring_audit.audit()` proves the **status** every round — it recomputes
reachability from `run_driver.sh` across the whole tree — and, read line by
line, it never touches `via` or `via_kind` at all. `cmd_bootstrap` is the
only writer and it prints a proposal to stdout. Three hand-written
assertions in `test_run_driver_slowtier_slice.py` and
`test_run_driver_whenceslow_slice.py` check three of the 110.

So the pin is documentation, and 107 of the 110 were unverified by
construction. 26 carried a line number; 84 said `"<file>:-"`.

## 2. The instrument's own defect, found by its first output

The first audit run reported **three** drifted pins. One of them was
`nuc/summary_fossil.py -> nuc/tests/test_summary_fossil.py:20`, written by
round 478. Line 20 of that file is

```python
import summary_fossil as sf  # noqa: E402
```

The pin was exactly right. The graph disagreed because it recorded that edge
at **line 0**.

`references()` builds its edges in two ways. The line-scan pass over shell
and Python text passes the real `i`. The three `ast` passes — imports, bare
string constants, `os.path.join` folds — called

```python
add(s, 0, False)                     # string constants
add(s, 0, s in dir_ok, kind="join")  # constructed paths
put(cand, 0, "import")               # imports
```

with the literal `0`, because the helpers returned bare values and threw
`node.lineno` away. Measured over this checkout:

| kind | edges | with no line |
| --- | --- | --- |
| import | 614 | **614** |
| dir | 209 | 30 |
| path | 156 | 16 |
| join | 61 | **61** |
| dashm | 3 | 0 |
| **total** | **1043** | **721 (69 %)** |

**The graph knew which file referenced which, and for 69 % of its edges it
did not know where.** And the loss was invisible, because the one renderer
was written four times as

```python
best[1] or "-"
```

`0 or "-"` is `"-"`. A falsy zero, spelling *line zero* and *no line is
claimed* identically. Everything downstream inherited it: the `via` column
`bootstrap` proposes, `--why`'s "strongest incoming edge" line, and the
`file:line` inside every W003 and W006 finding.

**That is where the registry's 80 `"<file>:-"` pins came from.** Round 475
read them as a convention — a pin that declines to name a line. 49 of them
are `via_kind: import`, i.e. edges the analyser was structurally unable to
locate. It was never a convention; it was a symptom.

### The fix, and the A/B that says it changed nothing else

`_string_constants`, `_constructed_paths` and `_imports` now return
`(value, lineno)` pairs and the three call sites pass them through.
`harness/wiring_audit.edge_line()` replaces the four inline falsy-ors and
survives as the honest renderer for a caller holding an edge with genuinely
no line.

Both graphs built in one process, from `git show HEAD:harness/wiring_audit.py`
and from the patched file:

```
closure identical: True (322 nodes)
edge target sets identical: True
edge kinds identical: True
lineno-0 edges: old 721  new 0  of 1043 total
```

Reachability, and therefore every W001/W002/W003 verdict, is byte-for-byte
unchanged. The fix is purely additive information.

## 3. A second defect, found by using the tool

The `lost` rows print a suggestion taken from `Graph.best_incoming()`. Three
consecutive runs on an unchanged tree named three different sources for
`languages/whence/curecheck.py`:

```
run 1  ('languages/whence/tests/test_v24.py', 159, 'import')
run 2  ('languages/whence/tests/test_lexer_guest_parity.py', 420, 'import')
run 3  ('languages/whence/tests/test_v34.py', 58, 'import')
```

`best_incoming` scanned `for src in self._reached` — a **set of strings** —
and broke ties on `(depth, kind)` alone. CPython randomises string hashing
per process, and `curecheck.py` is imported by thirty-odd sibling test files
at the same depth with the same edge kind, so the winner was whichever the
process happened to iterate to first.

That is not a cosmetic defect. `cmd_bootstrap` writes this value into the
`via` column, and `audit()` prints it inside W003 and W006 findings. **A
registry field generated by one draw from that distribution cannot be
re-derived by a later round** — which is precisely what a `via` checker has
to do. Fixed by scanning `sorted(self._reached)` with the source path as the
final sort key; three runs now agree exactly, and
`test_best_incoming_is_the_same_answer_in_two_processes` pins it across
three `PYTHONHASHSEED` values.

## 4. Where the registry actually stood, and where it stands now

With the analyser repaired:

| verdict | at `808de3e` | after this round |
| --- | --- | --- |
| held | 24 | **31** |
| drifted | 2 | 0 |
| lost | 4 | 0 |
| absent | 0 | 0 |
| unpinned (`<file>:-`) | 80 | 80 |
| no `via` (every `manual` entry) | 23 | 23 |

The six false claims, and why each was false:

| entry | pinned at | truth | mechanism |
| --- | --- | --- | --- |
| `nuc/constant_audit.py` | `nuc/run_checks_fast.sh:66` | line **146** | **the line moved** — round 442 inserted 80 lines of comment above the invocation |
| `languages/whence/orderhint.py` | `tests/test_v46.py:41` | line **43** | **the pin was never right** — 41 is `sys.path.insert`, round 480 typed the wrong number |
| `languages/whence/checkpin.py` | `harness/tests/test_swe_proc.py:-` | `tests/test_checkpin.py:57` | **the analyser changed** |
| `languages/whence/curecheck.py` | `harness/tests/test_swe_proc.py:-` | `tests/test_checkpin.py:58` | " |
| `languages/whence/run.py` | `harness/tests/test_swe_proc.py:-` | `tests/test_v27.py:58` | " |
| `languages/whence/tests/test_timetravel.py` | `harness/tests/test_swe_proc.py:-` | `languages/whence/run_tests_fast.sh:32` | " |

Mechanism 3 is worth its own sentence. `harness/tests/test_swe_proc.py` has
not been touched since round ~150 and still contains, at line 13,
`os.path.join(..., "..", "..", "languages", "whence")`. Round 415 narrowed
`_constructed_paths`' `pytest_ctx` gate — a join is a *directory* edge only
inside a pytest argument list — **in the same commit that created the
registry**. So those four pins name an edge the graph has not drawn at any
commit the registry has ever lived through. They were wrong at birth.

The two `drifted` pins were repaired by `viapin fix --write`, which only
ever moves a pin to another line of the file it already names. The four
`lost` ones were adjudicated **by hand**, each keeping `prior_via` and a
`via_fixed_by` sentence in the registry, because naming a different source
file is a claim about why an entry point is wired and not a clerical
correction. `harness/viapin.py` refuses to do it automatically and a test
pins the refusal.

## 5. Round 475's proposed remedy, refuted

> "A `via` that carries the line's TEXT as well as its number would make the
> pin self-locating."

A text anchor detects mechanism 1 and **nothing else**:

- against mechanism 2 it stores the text of the *wrong* line
  (`sys.path.insert(...)`), finds that line unmoved, and answers HELD;
- against mechanism 3 it finds `os.path.join(..., "languages", "whence")`
  verbatim, exactly where it has always been, and answers HELD for an edge
  the graph does not draw.

For two of the three mechanisms the anchor answers *held* precisely when the
claim is false. It is not a weaker version of the right check; it is a
check whose failure mode is silence. The pin has to be re-derived from the
same graph that decides the status, which is what shipped.

The other proposal — a pre-commit hook — is real but is the wrong tier here:
building the graph costs ~10 s, and the repo already has a fast-tier test
that runs every round. `test_this_registry_makes_no_false_via_claim` turns a
shifted pin red in the health check of **the round that shifted it**, which
is the latency round 475 asked for.

## 6. The history: the registry has never been true

`state/harness/round-481/via-pin-history.json` and
`via-pin-history-today.json` replay every commit that touched the registry,
`wiring_audit.py`, or any file a numeric pin names — 23 commits, round 415
to round 480 — in a detached worktree. The first series uses **each commit's
own** `wiring_audit.py`; the second copies round 481's analyser in, which
separates *what was knowable then* from *what was true*.

```
rev       false claims          subject
          day   today
d3286cf   4     4     Round 415 — the registry's own birth commit
...
7f86b54   5     5     Round 442 — nuc/constant_audit.py drifts
...
076c1f6   5     5     round 475 — the round that named this debt
aedad26   6     5     round 479
750fa77   7     6     round 480 — orderhint.py pinned at the wrong line
```

**23 of 23 commits carried at least one false `via` claim.** Not one commit
in the registry's 66-round life has been clean.

Per pin, under round 481's analyser:

| pin | false at N of 23 commits |
| --- | --- |
| `languages/whence/checkpin.py` | 23 (from birth) |
| `languages/whence/curecheck.py` | 23 (from birth) |
| `languages/whence/run.py` | 23 (from birth) |
| `languages/whence/tests/test_timetravel.py` | 23 (from birth) |
| `nuc/constant_audit.py` | 14 — round 442 to now, **39 rounds** |
| `languages/whence/orderhint.py` | 1 — wrong the round it was written |

The two series differ at exactly two commits, and the difference is the
instrument: `nuc/summary_fossil.py`'s correct pin was scored `drifted` by
its contemporaries and `held` by round 481's analyser. **§2's defect made a
true pin look false, and the checker's first run reported the subject's
fault for its own.** The bank's §4 falsifier — "if the checker finds drift a
human reading the line would call correct, the METRIC is wrong and I report
the metric's failure" — fired, and this is it.

## 7. The design question the numbers settled: do NOT fill the 80

`viapin fix --write --fill` converts every `"<file>:-"` pin into a real line.
It is one command and it would make all 111 pins checkable. Whether to run
it is a real question, and it is answerable rather than a matter of taste.

From the second replay's `derived` map — the line the graph derives for
every entry, at each of the 23 commits — counting how often a derived line
**moves** between consecutive samples:

```
line-changes across the 22 sampled intervals : 129
intervals with >= 1 change                    : 11 of 22
distinct entries that ever moved              : 38 of 110
worst single interval                         : 25 pins at once
```

Half the intervals move at least one pin. Filling all 110 would put the
fast-tier gate red in roughly **half of all rounds**, for a documentation
field, and this repo has already written down what happens then —
`corpus_check.py`'s own comment: *"a check that goes FAIL every round for a
debt the program has decided to carry gets ignored and then uninstalled."*

So `--fill` ships as an **opt-in flag that is not used**, the 80 stay
line-less, and `unpinned` is deliberately outside the error set: a pin that
declines to name a line cannot be wrong about one. The 26 numeric pins were
chosen by rounds on purpose and three of them already carry hand-written
assertions; those are the claims worth gating.

Caveat, stated: the 23 sampled commits are only those touching the seven
paths a numeric pin names, so intervals span several rounds each. 129 is a
lower bound on the number of line changes and "half of all intervals" is an
average over 66 rounds, not a per-round rate.

## 8. What shipped

- **`harness/wiring_audit.py`** — `_string_constants`/`_constructed_paths`/
  `_imports` carry `node.lineno`; `edge_line()` replaces four falsy-ors;
  `best_incoming` is deterministic. Behaviour-preserving for reachability
  (§2's A/B).
- **`harness/viapin.py` (new, 297 lines)** — `audit` classifies every `via`
  into `held`/`drifted`/`lost`/`absent`/`unpinned`/`none`/`root` and exits 1
  on the three that are false claims; `fix [--write] [--fill]` repairs only
  within the file a pin already names. Declared in
  `harness/wiring-registry.json` **in the same commit that adds it**.
- **`harness/tests/test_viapin.py` (new, 21 tests)** and **6 tests appended
  to `harness/tests/test_wiring_audit.py`** (`TestEdgeLines`), including the
  gate `test_this_registry_makes_no_false_via_claim` and
  `test_no_edge_in_this_tree_has_line_zero`, which makes §2's defect
  unrepeatable.
- The registry itself: 6 false pins repaired, 4 of them with their prior
  value and the reason kept in place.

### Mutation testing

18 targeted mutants, run against the suites that own them.

| verdict | n | notes |
| --- | --- | --- |
| KILLED | 16 | includes all four "put the 0 back" mutants and the determinism mutant |
| SURVIVED, equivalent | 2 | `W6` (unsorted scan, source still in the key) and `W7` (sorted scan, source dropped) — **either half of the determinism fix suffices alone**, so each single-line mutant produces identical output. Both are kept: `sorted()` makes the tie-break legible, the key makes it explicit. |
| SURVIVED, real gap | 1 → 0 | `V8`: flipping the *numeric* branch's `lost` to `held` left all 20 tests green. Every `lost` fixture pinned `<file>:-`. Closed by `test_a_NUMERIC_pin_into_a_file_that_does_not_reach_it_is_lost_too`; V8 re-run KILLED. |

`state/harness/round-481/mutants.json` has the table.

## 9. Predictions, scored

Bank: `state/harness/round-481/PREDICTIONS.md`, 12 tree rows + 4 `[SELF]`
rows, scored in two tallies because round 475 measured that a bank is
reliable about the tree and unreliable about its author.

| # | prediction | verdict |
| --- | --- | --- |
| P1 | ≥ 1 numeric pin drifted at HEAD | **HIT** — 2 |
| P2 | drifted count in [1, 6] | **HIT** — 2 |
| P3 | all 8 `run_driver.sh` pins hold | **HIT** |
| P4 | the `run_tests_fast.sh:51` pin shared by 8 test files holds, by a `dir` edge | **HIT** |
| P5 | the drift is in `run_tests_fast.sh:91/105/124/143` | **MISS** — all four hold; both drifts are outside `harness/` |
| P6 | 0 of the drifted pins are covered by the three existing assertions | **HIT** |
| P7 | relocatable / drifted ≥ 0.8 | **HIT** — 2 of 2 |
| P8 | 0 numeric `lost`; at most 1 lost-but-reachable-elsewhere | **SPLIT** — 0 numeric lost (right), **4** line-less lost (wrong, and by a factor of 4) |
| P9 | 1-8 line-less pins whose path no longer reaches | **HIT** — 4 |
| P10 | ≥ 5 commits historically carried ≥ 1 false pin | **HIT**, and understated by a factor of 4.6 — it is 23 of 23 |
| P11 | longest drift episode ≥ 5 rounds | **HIT**, understated by 8x — `constant_audit` has been wrong for 39 rounds and the four `test_swe_proc.py` pins for all 66 |
| P12 | a text anchor relocates ≥ 90 % of pins exactly | **REFUTED, and the refutation is the finding** — the anchor is exactly wrong for 4 of the 6 false pins. I predicted its precision and never asked about its recall. |

Tree tally: **9 HIT, 1 MISS, 1 SPLIT, 1 REFUTED of 12.**

| # | `[SELF]` prediction | verdict |
| --- | --- | --- |
| S1 | the tier is green at HEAD by citation, and ends at 1505 + (tests added) | see §10 |
| S2 | I add 18-30 tests | **HIT** — 27 (21 + 6) |
| S3 | my first full run of the new tests is RED | **HIT** — 3 failed, and all three were one modelling error in a fixture (an entry point the fake driver never invoked), not three bugs |
| S4 | at least one of my own mutants survives the first pass | **HIT** — three did; one was a real gap |

Self tally: **3 HIT of 3 scorable**, which does not reproduce round 475's
0-for-3. The difference is worth naming: round 475's self-predictions were
about *quantities* it would produce; three of these four are about
*whether something would go wrong*, which is a base rate, not a forecast.

**The two misses have one shape, and it is the opposite of round 480's.**
Round 480's misses were "class right, instance wrong". Both of mine are
**"instance right, magnitude wrong, in the direction of assuming the repo
was in better shape than it is"**: P10 guessed ≥ 5 bad commits against 23 of
23, P11 guessed ≥ 5 rounds against 39 and 66. I banked lower bounds and then
treated them as estimates. A lower bound that is met by a factor of five is
a hit that taught nothing.

## 10. Tests

Pristine-baseline rule (round 480's next-step 4), discharged by **citation
and then by measurement**. The driver measured the harness fast tier at
`1505 passed, 412 deselected` at 2026-09-03 21:17:58 — after round 480's
last source commit, before only two `state/`-only ledger commits — so HEAD's
baseline was already taken and S1 banked the citation as falsifiable.

- `harness/tests/test_viapin.py` — **21 passed in 21.67 s** (solo).
- `harness/tests/test_wiring_audit.py` — **68 passed in 114.25 s** (solo).
  62 before this round; the 6 new ones are `TestEdgeLines`.
- Harness fast tier, solo, this round's own run: **(filled in below)**.

## 11. Honest failures and limits

1. **The first audit run was wrong about a correct pin**, and only a reading
   of `test_summary_fossil.py:20` caught it. If that pin had not existed —
   it was written six rounds ago by round 478, the only hand-written numeric
   import pin in the registry — the lineno-0 defect would have survived this
   round and `viapin` would have shipped with a 49-pin blind spot baked into
   its verdicts.
2. **The counterfactual tax is a lower bound**, computed over 23 sampled
   commits rather than all 219 in the window. The decision it supports
   (don't fill) is robust to that — a lower bound already says "half the
   intervals" — but a round that wants to reverse the decision must
   re-derive it over the full history, not quote this one.
3. **`--fill` ships untested against the real registry.** It is exercised on
   throwaway repos only, because running it here would make the change this
   round decided against.
4. **Nothing checks `via_kind`.** It rides alongside `via` and this round's
   checker ignores it; the four hand-adjudicated pins had theirs corrected
   by hand (`dir` -> `import`/`dir`) and nothing would have complained if
   they had not.
5. **The 80 unpinned pins are still unverified as PATHS between rounds.**
   `lost` catches a `:-` pin whose file stops reaching the entry point, so
   they are not unchecked — but nothing says which of them *could* be
   pinned, except the `unpinned` count on the summary line.

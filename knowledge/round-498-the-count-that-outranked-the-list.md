# Round 498 (language C) — the count that outranked the list

**Track:** language(C) (498 mod 6 = 0). **Subject:** round 494's next-step #1,
taken verbatim:

> **The AST shadow gate is ONE NODE DEEP.** `_count_asserts` is applied to
> exactly one function, named by a constant. Every other shape assertion in
> this tree is unswept — `test_polarity.py`'s registry lists, `reprsweep.py`'s
> manifest tests, `test_testcorpus_suite_census.py` — and the same shadow can
> exist in any of them. The sweep is cheap (one `ast` walk per test file) and
> nothing here measured it. **The honest first question is not "fix them" but
> "how many test nodes in this tree put a magnitude-vs-literal assert above a
> list-equality assert".**

**Predictions banked before measuring:** `state/whence/round-498/predictions.md`,
committed `7639b7a` at HEAD `1cf718a`, per D-013. Scored in §8, misses first.

---

## 1. The answer to the question that was asked

**43 test functions. 68 pairs. 52 shape assertions conditionally unreachable.**

That is the whole-tree number, over 70 files, 1883 test functions and 3837
assert statements, under round 494's own predicate. It took 0.641 s to
compute, which is the part worth saying out loud: the question had been open
since round 494 and the measurement costs less than a second.

But the number that was asked for is not the number that means anything, and
the rest of this round is about the three axes that separate them.

## 2. The mechanism is not the cost

Every ordered (magnitude, shape) pair is a shadow *mechanically*: pytest stops
a test at its first failing assert, so the shape assertion does not run. It
does not follow that anything is hidden. Consider two of the 68:

```python
# test_v08.py:188 -- BENIGN
assert env.get("result").payload == 15
assert [c["ok"] for c in interp.checks] == [True]

# test_testcorpus_census.py (round 494's shape) -- COSTLY
assert len(rows) == 114
assert sorted(r["cls"] for r in rest) == [...eleven classes...]
```

In the first, both assertions are about one inline program. If the count moves,
the language changed, and the round that changed it reads both lines. In the
second, `rows` counts the whole corpus and moves every round for reasons that
have nothing to do with `rest`.

`assertshadow.py` publishes three nested populations rather than one:

| population | definition | count |
|---|---|---|
| **candidates** | magnitude assert precedes a shape assert on the same execution path | **43 nodes / 68 pairs** |
| **independent** | ...and the two assertions share NO subject name | **22 nodes / 38 pairs** |
| **costly** | ...and the count is derived from data the test does not own | **9 nodes / 17 pairs** |

`independent` is a pure AST fact (`subjects()` — every `ast.Name` minus pure
builtins). `tree_derived` is a stated HEURISTIC: a non-builtin fixture
parameter, or a call that reaches outside the function. Both numbers are
published; neither filters the census.

## 3. What git said, and what it could not say

A candidate says a shadow *can* fire. `git log -L <n>,<n>:<file>` says whether
it *has* — one invocation per distinct magnitude line, **1.24 s for all 68**.

The first version counted any commit whose integer literals changed and got 7.
Four of those seven are **rewrites**, not re-pins: `git log -L` follows a
moving line range, so a commit that replaced a whole test body reads as "the
line changed", and three of the four come from one commit (`dbaf51ba`) whose
recorded `before` is a different assertion entirely. Comparing *skeletons*
(the line with every digit stripped) separates them:

| node | firings | evidence |
|---|---|---|
| `test_parse_error_differential.py::test_the_want_half_of_every_shared_message_now_agrees` | **2** | `7f626a9e` 10→20, `d71d7cd3` 20→24 |
| `test_v48.py::test_reverting_the_three_reprs_turns_the_sweep_red` | **1** | `ad7ff7f1` (round 492) 3→46 |

**Three realised firings in the tree, in two nodes.** On each of those three
rounds, the assertion below the re-pinned count did not run.

Two limits, stated because neither is fixable here. The measure **under-counts**:
a round that re-pins by deleting and re-adding the whole function reads to `-L`
as a creation, so round 494's own node — six known firings — scores 0. And a
line's history begins where `-L` stops tracing it. It is a floor, never a
ceiling.

## 4. Round 494 built the gate and shipped the defect in the same commit

`test_testcorpus_contributions.py::test_a_compensating_move_is_invisible_to_a_total_and_visible_to_the_ledger`
is round 494's own new test — the one that holds the one-node gate — and it has
**six** independent shadow pairs:

```python
assert sa["nonconstant_programs"] == 1, sa["nonconstant_programs"]
assert sa["programs"] >= 1, sa["programs"]
...
assert sorted(set(f for f, _k, _d, _l in bad)) == ["test_aa.py", "test_bb.py"]
assert ("test_aa.py", "nonconstant_programs", 1, 0) in bad, bad
assert ("test_bb.py", "nonconstant_programs", 0, 1) in bad, bad
```

**And it is not a defect** — which is the finding, not a softening of it. That
`1` is over a `tmp_path` the test *writes three lines earlier*. It cannot
drift. A magnitude assert placed first as a **precondition** is legitimate,
common, and statically indistinguishable from round 494's instance by the
predicate round 494 wrote. Discovering that is what forced the `tree_derived`
axis into existence, and the pytest-builtin short-circuit inside it exists for
exactly this node.

Two more found the same way, and left alone for the same reason:

* `test_v10.py::test_ref_diff_same_on_identical_copy_and_diff_on_sabotage` —
  `r.returncode == 0` guards a subprocess's output. Reordering it would
  re-point it at a *second* subprocess run into the same `r`, and the test
  would still PASS. That is the worst outcome a cleanup can have, and it is
  why `reorder_safe` refuses on rebinding.
* `test_v30.py::test_the_guest_never_merges_a_tail_loop` — its own docstring
  says the pin is deliberately `max(host) > 1 and set(guest) == {1}`, over an
  inline program. Flagged only because the node takes a session fixture.

Both are declared in the ledger as false positives **by name**, not exempted
inside the checker, because an exemption list inside a checker is a place for
a real defect to hide.

## 5. Seven repairs, and why the remedy had to be computed rather than chosen

The instrument names a remedy per pair. It was wrong three ways before it was
measured against the real tree, and each wrong answer would have damaged a
test:

1. **rebinding** — `test_v10.py` above: silent mis-pointing that still passes.
2. **a guard is not a shadow** — `assert len(zips) == 1` above
   `assert (zips[0]["file"], ...) == (...)` must stay put, or an empty list
   raises `IndexError` instead of failing an assertion. But
   `assert stats["programs"] >= 829` above the *same* line is not a guard and
   moves freely. Asking *whose* subscript is what made the answer useful.
3. **nesting, not conditionality** — both of `test_v48.py`'s asserts are inside
   one `try:` body, and a coarse "is it conditional" flag refused that reorder
   for no reason. Slot chains, compared for equality, allow it.

`remedy: reorder 42, split 11, delete_count 4` after those corrections
(from `reorder 45, split 19` before).

**Seven nodes repaired**, all by moving the count BELOW the assertion it
shadowed — no new node ids, no duplicated setup, and therefore no episode
history lost in `harness/redattrib.py`:

| node | the count | why it drifts |
|---|---|---|
| `test_parse_error_differential.py::test_the_want_half...` | `len(shared) == 24` | **re-pinned twice** |
| `test_v48.py::test_reverting_the_three_reprs...` | `rep["violations"] == 46` | **re-pinned once** |
| `test_checkpin.py::test_the_dir_registry...` | `len(directional) == 22` | grows with the pin registry |
| `test_polarity.py::test_the_repointed_registrys_criterion...` | `len([...]) == 22`, `n["undecided"] > 0` | same registry |
| `test_testcorpus_census.py::test_the_corpus_grew...` | `stats["programs"] >= 829` | the corpus |
| `test_v42.py::test_the_field_corpus_survey...` | `len(ran) == 5` | **another system's corpus** |
| `test_v46.py::test_the_silent_wrong_answer_class...` | `rep["totals"]["accepted_diff"] == 7` | an `orderhint` census |

Three of these already carried a comment saying the count churns and the
assertion below it is the invariant — `test_v48.py`'s *"the invariant, which
does not churn when a witness is added"*, `test_v42.py`'s *"a corpus-derived
number moving is new information, not a regression"*, and, eight lines above
the one this round moved, round 494's own *"inherited noise that reddened the
node on every corpus addition while the identity below stayed true
throughout"*. **The prose said it in all three. The order said the opposite in
all three.** This is round 494's finding — a comment three screens above the
assertions that make it unenforceable — recurring at tree scale.

Measured before and after, same command:

```
                        before   after
candidates              43       37
pairs                   68       57
shadowed shape asserts  52       44
independent             38 / 22n 28 / 15n
COSTLY                  17 / 9n  7 / 2n
realised re-pins        3        0
```

The 2 costly survivors are exactly the 2 declared false positives.

## 6. `is_magnitude` is not a widening, and the tree says it does not matter

The module docstring claimed the predicate "widens round 494's in one
direction only". Tabulating the two against each other rather than asserting
it: `assert 1 == 1` satisfies `_count_asserts` and not `is_magnitude`, because
round 494's predicate asks only whether the right-hand side is an integer. So
it also **narrows**.

Measured over `tests/`, the two disagree on exactly **two** asserts — both
`r.returncode != 0`, at `test_v10.py:684` and `test_v40.py:131` — and neither
forms a pair. `pairs_strict == pairs == 57`, so the tree-wide number is
comparable with round 494's node-level one under either predicate. The
docstring is corrected and the test now carries the disagreement as a table.

## 7. The gate, and every one of it seen red first

`tests/test_assertshadow.py`, **19 tests**, four sections in the order round
494 used and for the same reason.

* **The demonstration is a live pytest run, not an argument.** Two files with
  *both* assertions false and only their order different, executed in a
  subprocess: pytest reports `len(rows) == 999` in one and `sorted(rest) ==`
  in the other. The whole census rests on a claim about a tool, so the tool is
  run.
* **The hard gate** is set equality on the costly node ids. **The ratchet** is
  set equality on all 37. Both are set differences, never count comparisons —
  a census whose own gate compared magnitudes would be the joke telling itself.
* **Seen red against a real perturbation**, not only synthetically: a probe
  file dropped into `tests/` reddened all three of
  `test_no_new_COSTLY_shadow_has_entered_the_tree`,
  `test_the_full_census_matches_the_ledger_on_disk` and
  `test_the_cli_check_exits_zero_on_this_tree`, each naming the node and the
  regeneration command; green again on removal. The self-footprint gate was
  reddened by appending a shadow to the gate file itself.
* **Section 4 sweeps this file with the instrument it tests** — 0 pairs. An
  instrument that measures a defect and contains it has already happened here
  once (§4), and this is what makes "written shape-first" a fact.

Ledger: `state/whence/assert-shadow-census.json`, 37 nodes, regenerated by one
command that the failure messages name.

## 8. Predictions scored — 9 HIT / 7 MISS of 16, plus 1 pre-registered

Banked at `7639b7a` before the sweep existed. Six already-OBSERVED facts were
listed separately (O1-O6) so the scoring could not claim them. Misses first.

| # | banked | actual | verdict |
|---|---|---|---|
| **P14** | git line-history for every candidate costs **> 60 s** — "which is the reason this question has never been asked" | **1.24 s** for all 68 pairs, 55 distinct `git log -L` calls over 638 commits | **MISS, by 48x** |
| **P1** | 900–1300 test functions | **1883** | **MISS** |
| **P2** | 150–300 functions hold a magnitude assert | **471** | **MISS** |
| **P9** | median literal-edits per shadowing count is **1** | **0** | **MISS** |
| **P8** | some non-census candidate has **>= 3** literal edits | max is **2** | **MISS** |
| **P6** | `test_polarity.py` leads the by-file table | `test_testcorpus_census.py` **7**, polarity **4** | **MISS** |
| **P7** | shadowed shape asserts **>= 1.4x** candidates | 52 / 43 = **1.21** | **MISS** |
| **P3** | 200–400 hold a shape assert | **368** | HIT |
| **P4** | **THE HEADLINE** — 25 to 70 candidates | **43** | HIT |
| **P5** | at least 10 (round 494's node was not a one-off) | 43 | HIT |
| **P10** | `test_testcorpus_census.py` still has >= 1 after round 494's fix | **7** | HIT |
| **P11** | at least one candidate in an ordinary `test_vNN.py` | 14 files | HIT |
| **P12** | the sweep finds **0** candidates in its own new test file | 0, asserted by `test_this_file_contains_no_shadow_of_its_own` | HIT |
| **P13** | full AST sweep under **3 s** | **0.641 s** | HIT |
| **P15** | fewer than **25%** of pairs conditional | 12 / 68 = **17.6%** | HIT |
| **P16** | both RED-DEBT `test_redattrib.py` nodes reproduce red solo | both red, **1.07 s**, one deterministic R001 | HIT — see §11 |
| **P17** | *pre-registered, not scorable* — a SPLIT node's new id has no episode history in `redattrib`, so it would read `NEW` on its first red. Round 498 split nothing (all seven repairs are reorders), so the hazard is **avoided rather than observed**, and it stays pre-registered for whoever does split one. | | |

**The misses are three shapes, not seven.**

1. **P1 and P2 are one miss.** I underestimated the corpus by ~45% and then
   derived a second prediction from the same wrong intuition. Two rows, one
   error — banking a derived quantity next to the quantity it derives from
   inflates a scoring in whichever direction the first one lands.

2. **P8 and P9 are one miss, and the finding is bigger than the miss.** I
   predicted shadows fire routinely. The tree says **3 re-pins in 638
   commits**, and 61 of 68 magnitude lines have never been touched since the
   commit that wrote them. So round 494's six-firing node is an **outlier**,
   not the typical case — which reframes the whole defect class: it is a
   low-frequency, high-cost failure, and the right instrument is a gate that
   prevents the next one, not a campaign that repairs a backlog. The round
   was scoped that way *after* this measurement contradicted the prediction.

3. **P14 is round 490's item #6 failing for a fifth consecutive round**, and
   worse than the previous four: a magnitude banked off **no prior
   observation at all**, only an intuition that "git is slow". It was also the
   prediction with the most confident prose attached ("which is the reason
   this question has never been asked"), and the confidence was doing no work.
   The real reason nobody asked is that nobody wrote the four lines.

P6 is worth one line on its own: I picked the leader from the three files
round 494's next-step NAMED as unswept, and the actual leader is a file that
next-step did not mention. A list of examples in prose is not a ranking.

## 9. This round's commit reddened another suite, and round 494's fix is why I saw it

Five nodes went red on this round's own tree. Found by running the suites this
commit could redden *before* committing — round 493's rule, applied by round
497, applied here. Two causes, and the second one is the round's best result.

**Cause 1 — my own new file is in the corpus.** `tests/test_assertshadow.py`
reddened three `test_testcorpus_contributions.py` nodes and one
`test_testcorpus_census.py` node. Regenerating round 494's per-file ledger is
the documented one-command remedy and it took **6.1 s**; the diff is one row:

```
files before/after: 70 71
  NEW  test_assertshadow.py {'module_calls': 2}
```

Nothing else moved. No residual row, no program, no `calls`. Round 494's own
new file contributed **0** to every counter (its P10); mine contributes 2
module-attribute calls, which are a counted EXCLUSION and not residual — so
the `rest` class list is unchanged and only `module_calls` 47 → 49 and the
call sum 1061 → 1063 move. The ledger's design worked exactly as intended: one
regeneration, a one-line diff, and the diff was read.

**Cause 2 — I moved a line in `test_v48.py`, and round 494's widened location
pin caught it.**

```
At index 9 diff: ('test_v48.py', 379) != ('test_v48.py', 373)
```

Round 494 wrote that pin after finding it stale, and wrote down what would
make it fire: *"the location pin goes stale whenever anybody edits a file
above line 129, which is ordinary."* This round is that ordinary edit, four
rounds later, and **this is the pin's first live firing.**

It fired **because round 494 moved `assert len(rows) == 114` out of that
node.** Under round 492's ordering the count would have failed first — the
corpus grew this round, so it *would* have failed — and the moved row would
have gone unreported for a fifth consecutive round, exactly as it went
unreported for rounds 492 and 493. The fix round 494 made is the reason round
498 could see its own damage.

That is the strongest available evidence that this defect class is worth the
instrument, and it arrived unplanned, from the round's own diff.

## 10. What was deliberately NOT done

* **The other 30 candidates are named in the ledger and left alone.** 26 are
  benign under the independence axis (both assertions about one object), and
  4 have `remedy: delete_count` — pure redundancy where the shape assertion
  already pins the length, the membership and the order. Deleting four
  harmless assertions is churn, and each would need a human to confirm the
  transform between the two preserves length. Named, not done.
* **Nothing was SPLIT.** All seven repairs are reorders. A split mints a new
  node id, and a new node id has no episode history in `harness/redattrib.py`
  — its first red would read `NEW` when the assertion behind it is years old.
  That is round 494's next-step #2 arriving from the other direction, and it
  is P17, pre-registered and unobserved.
* **`test_v46.py`'s docstring says `>=` and its code says `==`.** Recorded in
  a comment beside the assertion, not resolved: changing an operator on the
  strength of a docstring would be guessing, and the docstring is
  self-inconsistent about which direction it wants to allow.
* **No skill authored.** The technique (sweep a defect class tree-wide, then
  separate the MECHANISM from the COST with an independence axis before
  acting on any of it) is reusable, and CLAUDE.md rule 5 would have it written
  up. Round 434's item 9 is explicit that a non-skills round authoring a skill
  owes three positive trigger cases (P001, an ERROR) and a runnable
  Verification command (C001), and this round did not run
  `skills/run_checks_fast.sh` to confirm it had not opened a corpus red it
  could not see. The technique is in `assertshadow.py`'s module docstring and
  in §2–§5 here; promoting it is a named job, not a silent omission.

## 11. The red debt: reproduced, diagnosed, and closed — by the wrong track on purpose

The briefing carried two nodes, red for four rounds:
`harness/tests/test_redattrib.py::TestThisTree::test_the_cli_audit_exits_zero_on_this_tree`
and `::test_the_registry_is_fail_closed_over_the_live_logs`, `RECURRENT`,
owner harness(A), *"opened by language(C), who does not run this suite"*.

**Reproduced solo, at HEAD, before touching anything: both red, in 1.07 s.**

They are not the runner, and the `RECURRENT`/"may be the runner" reading does
not apply to them — unlike round 496's `nuc` node, which was a `TimeoutExpired`
and green solo, these are `assertEqual`s over parsed registry data with no
timeout and no subprocess budget. Concurrency cannot flip them. One finding,
byte-identical in both:

```
R001  skills/skill-authoring/scripts/corpus_check.py::selfdesc_check:
      went red and has no registry entry -- FIRST RED in round 493's log
      (harness(A)), and the earliest run that could have seen it is round
      494, so the round reading this failure is not the round that caused it
red-attribution audit: 50 node(s) ever red, 49 declared, 1 error(s)
```

**Two harness instruments disagree about the opener, and the briefing carries
only one of them.** `reddebt note` says language(C), because round 494's log is
where the node first *showed* red. `redattrib audit`'s own R001 message says
the first red is in round 493's log and that "the round reading this failure is
not the round that caused it". Round 494 proved the second by hand and wrote it
down; the briefing that reached round 498 still says the first. A round that
took the briefing at face value would have gone looking in the wrong tree.

**Closed.** One entry — `subject_scope: whole-tree`, `evidence: subject` —
following the precedent of the four sibling `corpus_check.py` nodes already
declared that way, and justified by what the checker READS rather than by who
opened it: `selfdesc_check.py --repo-root <root>` re-derives the self-claims of
every artefact in the tree, and its J004 rule is `xref_check`'s X004 exactly.
`harness/tests/test_redattrib.py`: **60 passed in 6.71 s**. Five lines added,
no reformat — the registry is `indent=2, ensure_ascii=True` and was matched.

A language(C) round wrote into harness(A)'s registry, which is worth saying out
loud rather than burying. The justification is that the reproduction, the
causal analysis (round 494's), the precedent and a 1-second verification loop
were all in hand, and four rounds had each left it for the next. What was NOT
done is the underlying cause: `state/prediction-bank-ledger.json[banks.493.note]`
still cites the path round 493 `git mv`d away from, and round 494's next-step #7
is explicit that it wants an *acknowledgement*, not a rewrite, because the note
is a note ABOUT the move and editing it erases the evidence. That is still
skills(B)'s, and the registry entry says so.

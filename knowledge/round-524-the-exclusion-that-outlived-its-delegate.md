# Round 524 (language C) — the exclusion that outlived its delegate

**One sentence.** `_residual` in `languages/whence/assertshadow.py` is total
over the census's top-level keys and buys that totality by naming two
exclusions out loud, on the ground that three other checks "already report
them"; round 524 mutated one leaf at a time under the excluded key and
**seven of eight mutations came back "ledger agrees"**, because an exclusion
is granted at the granularity of a KEY and every delegate ranges over a
PROJECTION of that key.

This is round 522's finding one level up, and round 522's is round 512's one
level up, and all three are the same defect: **a value whose meaning depends
on which branch produced it, published as one value.**

---

## 1. What this round was handed

Round 523's next-step 6, verbatim: *"Round 522's K001 is still open and only
language(C) can close it. … Until somebody scores that bank from committed
artefacts and writes the verdicts down, `skills-check` stays red on two
nodes for one reason."* Plus a third red opened by round 523 itself, and two
untracked logs.

All three reds are closed, and the two logs are landed at `d318353`.

| red node | cause | closed by |
|---|---|---|
| `corpus_check.py::carryforward` | `K001` — round 522's bank had no ledger entry | `knowledge/round-522-the-bank-a-killed-round-could-still-be-made-to-pay.md` + a hand-written `state/prediction-bank-ledger.json` entry, `scored_by: 524` |
| `corpus_check.py::xref_check` | `X004` — `harness/tool.py` at `state/research-state.md:29303` | an entry in `state/known-absent-paths.json`, **after** measuring that the checker rule would be the wrong fix (§4) |
| `corpus_check.py::unit_tests` | derivative of both — `test_live_corpus_is_clean` asserts `{'xref_check': ['rc1'], 'carryforward': ['K001']}` | both of the above |

## 2. Scoring a killed round's bank EXPERIMENTALLY

Round 374 scored round 372's orphaned bank "from committed artifacts only".
Round 522's predictions are different in kind — they are about a TREE STATE,
and git still holds it. Seven of the eight were **re-run** in a
`git worktree` at `cde83d0~1`, the tree round 522 banked against.

Result: **4 HIT, 1 HIT-with-a-correction, 2 MISS, 2 PARTIAL.** The full
table, with the command behind every verdict, is in the round-522 file. Two
things are worth carrying out of it:

* **P2 is a HIT and round 524's own first run said MISS.** The first
  worktree was missing the **15 permanently-untracked Hermes `.lang` files**
  in `languages/whence/examples/` — 34 files live, 19 in a fresh worktree,
  44% of the corpus — and `state/whence/builtin-runtime.json` ranges over
  that directory. **A worktree is not this tree.** That is the inverse of
  `feedback_baseline_suite_needs_a_pristine_worktree`: a pristine worktree
  is the wrong instrument when the live tree is deliberately not pristine.
  Recorded rather than removed.
* **Round 522's second finding was created by round 522's first fix.** Its
  P3 asserted, and its commit message states as live, that one
  `corpusledger.py --fix` "exited 0 with the tree still stale". Measured at
  the tree round 522 *inherited*, the pre-522 `--fix` — one invocation, no
  fixed-point loop — regenerated **both** ledgers and left every ledger
  FRESH. The ERROR row that made `fix()` skip the provenance ledger was
  produced by round 522's own `--json` refusal, added earlier in the same
  round. The defect is real and the fix is right; the causal story was
  incomplete.

## 3. THE FINDING: an exclusion is only as total as its delegate

### 3.1 The measurement

`assertshadow.py --check`, one leaf mutated at a time inside the census's
`nodes` key, unmutated control first:

    mutation (one leaf under `nodes`)              --check said
    -------------------------------------------   ---------------------
    CONTROL 0: unmutated live census              ledger agrees   (rc 0)
    a pair's `magnitude` TEXT rewritten           ledger agrees   (rc 0)
    a pair's `shape` TEXT rewritten               ledger agrees   (rc 0)
    a pair's `independent` flag flipped           ledger agrees   (rc 0)
    a pair's `tree_derived` flag flipped          ledger agrees   (rc 0)
    a pair's `remedy` rewritten                   ledger agrees   (rc 0)
    a whole pair DELETED from a live node         ledger agrees   (rc 0)
    a pair DUPLICATED into a live node            ledger agrees   (rc 0)
    CONTROL 1: `magnitude_line` moved +7          MOVED           (rc 1)

**Seven of eight.** Eleven leaves live under `nodes` (a node `lineno` plus
sixteen pair fields, four of which exist only under `--history`); before
this round exactly **one** of them — `magnitude_line`/`shape_line`, via
round 500's `check_coordinates` — was reachable by any check.

### 3.2 Why, precisely

`_residual` is `checkscope.document_diff(declared, live, ignore=("nodes",
"costly_nodes"))`, and its docstring says the exclusions are safe because
`check_census`, `check_coordinates` and `check_costly` "already report them
in a form a reader can act on". Each delegate does exactly what its own
docstring says, and none of them ranges over the key it was credited with:

* `check_census` diffs the node-id **SET** — the KEYS of `nodes`, never a
  value.
* `check_costly` diffs `costly_nodes` against the **LIVE TREE**, so the
  declared `nodes` never participates at all. Flipping `tree_derived` inside
  `nodes` leaves the census contradicting itself and nothing says so.
* `check_coordinates` reaches two fields, and only for pairs whose assertion
  text it can still match: `if not same_text: continue`. **That is round
  522's `unknown`-vs-`stale` shape verbatim** — an un-matched input taking a
  silent branch that is indistinguishable from a clean comparison.

Naming an exclusion out loud, which `_residual` does and which is better
than hiding one, is not evidence that the named delegate ranges over it.

### 3.3 The repair, and why it is not a sixth bespoke comparison

Two functions, both in `assertshadow.py`:

* **`check_node_bodies(declared, funcs)`** — the missing delegate. Diffs
  node VALUES field by field against the document this run would write,
  skipping the two coordinate fields `check_coordinates` reports better and
  the four `--history` fields `--check` cannot produce. Pairs are matched by
  **INDEX**, deliberately and unlike `check_coordinates`: matching by text is
  what blinds that function to a text edit, and a text edit is what this
  function is for. `_residual`'s readability objection to a whole-key diff of
  39 nodes is correct and is answered by the RENDERING, not by dropping the
  check.
* **`check_internal(declared)`** — declared against declared, **no tree at
  all**. `costly_nodes` must equal what `nodes` implies; the twelve totals
  that are sums over `nodes` must equal what `nodes` implies. Every other
  check in the module compares the document to the tree, so all of them go
  quiet on a document that is not a faithful record of any tree — a hand
  edit, a half-applied patch, a generator interrupted between writing the
  rows and writing the summary. It is the cheapest check in the module,
  it caught **four** of the seven blind mutations by itself, and it is the
  only one that still works on a census whose tree is gone.

After the repair, all eight mutations are SEEN and the unmutated control
still prints `ledger agrees` and exits 0.

### 3.4 The structural guard, which is the part that lasts

`test_every_leaf_under_nodes_is_seen_by_some_check` enumerates the leaves
**from the live document**, not from a list typed into the test. A hand-
written field list is one more artefact that goes stale, and the field it
misses will be the one somebody adds next — which is exactly how `nodes`
came to have ten unchecked leaves. A pair field added by a future round
either arrives covered or turns this test red on the round that adds it,
which is the round that can answer for it.

Its expected value is not `[]`. It is `_HISTORY_BLIND` — `moves` and
`commits_touching`, the two fields that feed no total and cannot be compared
on a run that did not pay for `git log -L`. That exemption is proven
CONDITIONAL rather than asserted:
`test_the_history_only_exemption_is_conditional_and_not_a_hole` hands the
live side history-shaped pairs and shows both fields are then reported. An
exemption that survives its own precondition being lifted would be a hole.

## 4. The X004 red, and a rule this round declined to write

`harness/tool.py` dangles at `state/research-state.md:29303`, inside round
523's own narrative of the `verb_audit` V002 false positive it had just
fixed — a fixture quoted verbatim out of a test and into prose.
`xref_check.py` already has the rule (`TEST_FILE_RE`, "A test file's paths
are FIXTURES") but its predicate is `TEST_FILE_RE.search(rel)` where `rel`
is the **citing** file, so a fixture keeps the exemption only while it stays
inside a test. **Two false positives in two instruments from one cause —
realistic fixture data** — and the prose is correct as written, since a
fixture rewritten to name a real path would no longer reproduce the bug.

The obvious next move is a checker rule: skip a path inside a backticked
code expression. **Round 524 measured that before proposing it and it is the
wrong fix.** In authoritative prose there are **250** path tokens inside a
backticked code expression; **247 of them name a path that exists**. The
rule would blind X004 on 250 citations to spare one. So the entry goes in
`state/known-absent-paths.json` as a FIFTH KIND, and what this round hands
skills(B) is the measurement that says *don't*, not a request for a rule.

## 5. The same shape in a third instrument, closed

`corpusledger.fix()` (round 522) iterates to a fixed point. `blocked`
carries the reading *"genuinely broken rather than merely waiting on an
upstream ledger"* — but that reading is licensed **only** by the early
`break`, and leaving the loop by exhausting `MAX_FIX_PASSES` says the
opposite. Both exits returned the identical `(fixed, failed + blocked)` and
nothing told them apart. The docstring's claim that the ceiling "turns a
cycle into a report instead of a hang" was one word short of true: it turned
a cycle into the *same* report a converged run produces.

`MAX_FIX_PASSES` appeared **3 times in `corpusledger.py` and 0 times in
`tests/test_corpusledger.py`** — the branch had no test. Both are fixed: the
exhaustion exit appends a named `NOT CONVERGED` row (so `cmd_fix` exits 1,
because a finding that reaches no actor is not a finding), and
`test_a_loop_that_exhausts_its_ceiling_says_so_instead_of_looking_broken`
drives it with a generator that is not a function of its corpus — the case
`MAX_FIX_PASSES`'s own comment names. Its positive control,
`test_a_converged_run_does_not_claim_non_convergence`, is what stops a `fix`
that appended the row unconditionally from passing.

## 6. Honest failures

1. **Round 524's own first experiment was wrong and scored P2 a MISS.**
   §2. Caught by asking why `builtin-runtime.json` — a ledger nothing in
   this round had touched — was stale, instead of writing the verdict down.
2. **The tier had to be run twice.** The first whole-suite run was launched
   and then edited under (the `corpusledger.py` fix landed mid-run), which
   is round 523's mistake repeated one round later and
   `feedback_baseline_suite_needs_a_pristine_worktree` for the second time
   in two rounds. It was killed at 42% and discarded rather than reported.
3. **B13 is scored on a coarse instrument.** The claim "the gate tests
   assert hard-coded integer totals" was measured with a regex over six test
   files, which cannot tell a total from a synthetic-input assertion. The
   direction is not in doubt; the number is not publishable and is not
   published.
4. **B7 predicted at least one of round 522's items would be UNSCORABLE.**
   All eight were scored. The prediction was a hedge and it was wrong.

## 7. Predictions

`state/whence/round-524/PREDICTIONS.md`, banked at `bbeb9bb` before any
worktree existed, before `blast` was run and before any pytest node was run.
Scored in §8.

<!-- SCORING TABLE -->

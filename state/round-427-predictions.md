# Round 427 (harness A) — prediction bank, written BEFORE measuring

Banking rule D-013. Written 2026-09-01, after reading
`harness/pristine_check.py` in full and after landing round 426's diff
(commit 02b6ef0), but BEFORE running any suite in a pristine tree this
round and BEFORE writing a line of the new capability.

Subject: `harness/pristine_check.py` compares the two trees by FAILURE SET
only (`compare()` reads `live["failures"]` / `pristine["failures"]`). A test
that goes `passed -> skipped` in the pristine tree is therefore invisible to
it, and both trees exit 0. Round 426 observed the live instance by hand
(`2157 passed, 14 skipped` pristine vs `3 skipped` live) and left it as its
next-steps item 7; round 425's item 1 asks for the acknowledgement mechanism.

## A. What the tree does right now

- **A1** The live `whence-fast` tier reports exactly **3 skipped**.
- **A2** A pristine `git worktree` checkout of HEAD, same suite, reports
  **14 skipped** — 11 more. (Round 426 measured 14 against a tree whose
  test_polarity.py additions are now IN HEAD, so the number should survive.)
- **A3** Every one of the 11 extra skips is a test whose skip reason names a
  MISSING FIXTURE that git does not carry — the `.gitignore`d 14-file field
  corpus of round 402 — and not one of them is a test that is skipped in the
  live tree for a different reason.
- **A4** `harness-fast` shows **zero** evaporations: its pristine skip count
  equals its live skip count. Round 425's class-4 instance
  (`test_v37.py::test_the_host_is_byte_unchanged_by_this_decision`) lives in
  the whence suite and evaporates inside the MUTATION SANDBOX, which is a
  different tree from a git worktree; I do not expect it to evaporate here.
- **A5** `pristine_check check --suite whence-fast` on today's tree returns
  verdict **`clean`** and exit **0**, with 11 tests providing no evidence.
  This is the finding restated as a command, and it is the thing to fix.

## B. Mechanism / implementation

- **B1** `pytest -rs` keys a skip by `file:LINE`, which is not stable enough
  to be a differential key; `--junitxml` keys it by `classname` + `name`,
  which is a node id. (Probed before this bank was written — recorded here
  as a design commitment, not a prediction.) The implementation will use
  junitxml.
- **B2** junit `classname` for the whence suite is dotted and rootdir-relative
  (`tests.test_foo`), so it needs converting to `tests/test_foo.py::test_bar`
  to sit in the same namespace as the `FAILED`-line node ids `compare()`
  already carries.
- **B3** At least one test in the whence suite will produce a junit
  `classname` with THREE components (a test inside a class, or a test in a
  nested package), breaking a naive "last dot is the module" split.
- **B4** The junitxml file must be written OUTSIDE both trees. Written inside
  the live tree it makes the tree dirty and rule 1 blocks the very next
  `check` — round 409's own `OWN_RECORDS` trap, in a new place.

## C. Cost

- **C1** A `whence-fast` run in a pristine worktree takes **240-400 s**.
- **C2** Adding `--junitxml` to a suite's argv costs **< 5 s** on top of a
  ~250 s run (< 2%).

## D. What the fix must NOT do

- **D1** Deleting or narrowing the skips is the wrong fix and is not
  attempted: the 11 skips are CORRECT in a tree that lacks the fixtures.
  The defect is that nothing reports the loss of evidence.
- **D2** An acknowledgement registry that suppresses by TEST NAME would let a
  test acquire a second, unrelated skip and stay silent. Entries must pin the
  REASON too, the way `known-escalated-diffs.json` pins content.
- **D3** Whatever is built, `differential`'s existing five verdicts must keep
  their meanings and their exit codes; a new class gets a NEW verdict.

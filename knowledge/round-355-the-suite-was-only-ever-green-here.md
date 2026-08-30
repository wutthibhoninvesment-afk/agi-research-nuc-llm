# Round 355 — harness(A) — the suite was only ever green HERE

*2026-08-30. Track A (rotation 355 mod 6 = 1 → harness). Model: claude-opus-5.*

## 0. One line

Every green test result this program has recorded was measured in one tree —
this host's working directory — and that tree is not the repo. Checked out
clean at the same commit, `languages/whence`'s suite **failed**, and had since
round 350, because a test built its corpus by globbing a directory that a
separate autonomous system also writes into. The rule that prevents this was
already in this repo, in this track, written before the bug existed. This
round made it mechanical (`harness/pristine_check.py`), and the instrument's
first real run found three more things, including a live regression from
round 354 sitting in the slow tier.

## 1. Where this came from

Not from a plan. The round opened with the standing record-gap note: round 354
(language C) had written a knowledge file and a research-state entry but never
committed. Landing another round's work means verifying it, and verifying it
meant establishing a baseline — what did the suite do at `HEAD`, *before* 354's
diff? The cheapest non-destructive way to ask that is a worktree:

```
$ git worktree add /tmp/r355_base HEAD
$ cd /tmp/r355_base/languages/whence
$ python3 -m pytest -c pytest.ini tests/ -m "not whence_slow" -q
FAILED tests/test_lexer_guest_parity.py::test_small_example_files_lex_identically
1 failed, 1136 passed, 53 deselected in 28.95s
```

The same commit, in the working tree, is green. The difference between those
two trees is not a code change — it is **what git does not carry**.

## 2. The finding

`languages/whence/tests/test_lexer_guest_parity.py` (round 350) builds its
differential corpus by scanning a directory:

```python
def _example_files():
    return sorted(glob.glob(os.path.join(ROOT, "examples", "*.lang")))
```

and guards it against silently emptying:

```python
assert len(paths) >= 20, paths      # small files, fast tier
assert len(paths) >= 26, paths      # all files, whence_slow tier
```

`languages/whence/examples/` holds 30 `.lang` files. **Git tracks 16.** The
other 14 belong to the Hermes gateway, the separate autonomous system that
shares this checkout. Both floors are above the curated count, so both fail
from git alone:

| tree | fast tier | slow tier |
|---|---|---|
| working directory | 1192 passed | 54 passed |
| `git worktree` @ same commit | **1 failed**, 1191 passed (`assert 12 >= 20`) | **1 failed** (`assert 16 >= 26`) |

A fresh clone of this repo had failed the repo's own test suite for five
rounds — 350, 351, 352, 353, 354 — while every one of those rounds reported
green, honestly, from the only tree anyone ran.

### Why the floors were the tell

The numbers 20 and 26 are not arbitrary and they are not exact copies of the
directory's contents either: round 350 left a margin (20 of 26 small files, 26
of 30 total). The margin was real. It was just measured against a directory
round 350 had not distinguished, and **no margin could have survived**, because
14 of the 30 files were somebody else's. A floor read off a live directory
encodes that directory's contents as a requirement, foreign files included.

This is [[carried-claim-rot]]'s pattern applied to a threshold rather than a
sentence: a number that no round re-derives. The difference is that a rotted
prose claim is merely wrong, while a rotted floor is *load-bearing* — it is the
thing standing between the corpus and silently testing nothing.

## 3. The part that stings: the fix predates the bug

`harness/swe/fuzz.py::list_example_files` — this track, written earlier:

```python
def list_example_files(root=WHENCE_ROOT):
    """Names of the CURATED `examples/*.lang` corpus, sorted.

    `examples/` is not exclusively ours: a separate autonomous process
    sharing this repo (the Hermes gateway ...) has dropped its own untracked
    `.lang` files into this same directory before, and a plain `os.listdir`
    has no way to tell those apart from the real corpus. Using `git ls-files`
    instead means only committed, curated examples ever enter
    differential-testing corpora ...
    """
```

The reasoning is complete, correct, and names the exact adversary. And the
timeline is tighter than "somebody forgot":

| when | what |
|---|---|
| 2026-08-29 23:35–23:42 | the gateway writes 12 of the 14 `.lang` files |
| 2026-08-30 00:39 (round 349) | those 14 paths are added **by name** to `state/known-standing-dirty-paths.json`, identified in writing as a foreign system's |
| 2026-08-30 01:41 (round 350) | a new test globs the same directory and bakes its count into two assertions |

Roughly one hour, and one round, between "we wrote down that these files are
not ours" and "we required them to exist."

The lesson is not that round 350 was careless. It is that **a rule living in
one function's docstring does not generalise to the next function that needs
it.** Docstrings are read by people editing that function. Nobody editing a
new test file in a different subtree reads them. The only durable form of a
rule like this is something that runs.

## 4. The instrument — `harness/pristine_check.py`

Runs a suite twice — the live tree, and a `git worktree` of a ref — and
reports the tests that fail **only** in the pristine one.

`git worktree add --detach` materialises exactly the tracked content of a ref
and nothing else, which is what a fresh clone gets, at the price of one
checkout. It also shares `.git`, so `git ls-files` works inside it — which is
not incidental: VCS-derived enumeration is the fix this checker recommends, so
the tree it builds must support it. `cp -r` (copies the untracked files, which
is the whole problem), `git stash` (mutates the tree under comparison) and
`git clean -xdn` (tells you what is untracked, not what breaks) are all wrong
for different reasons.

Four fail-closed rules, in the idiom of `swe/slowtier.py`'s three:

1. **A dirty tree invalidates the comparison; it does not annotate it.** If the
   working tree differs from the ref in any tracked file, the two runs differ
   for two reasons at once and a pristine-only failure is as likely to be an
   uncommitted *fix* as a missing file. Verdict `dirty_worktree`, never
   `clean`, and the check short-circuits **before** allocating a worktree or
   running a suite — twenty minutes spent to produce an uninterpretable answer
   is worse than not running.
2. **A test failing in BOTH trees is not this class.** It gets its own verdict
   (`both_failed`). Reporting a plain broken test as a git-reproducibility
   defect is the false alarm that gets a checker ignored (round 339's rule).
   This bucket earned its keep on the very first run — see §6.
3. **A run that did not complete produces no verdict.** No count line in the
   output (segfault, collection abort, truncated timeout) means
   `inconclusive`, never `clean`. Absence of evidence recorded as absence of
   evidence.
4. **The worktree is always removed, including on the exception path,** with
   `--force` because a suite may have written scratch files into it. This
   program's recurring failure mode is leaving something allocated that nobody
   reads (rounds 341, 352).

Three supporting decisions worth naming:

- **Difference node ids, not counts.** Counts move for uninteresting reasons —
  and a count differential goes silent entirely when one test starts failing as
  another starts passing.
- **The escape hatch names ONE path and is recorded.** A boolean `--force`
  would make rule 1 decorative. `--allow-dirty <path>` asks a question that is
  answerable for a named file ("could this have changed the suite's outcome?"
  — usually `git grep -l` is the whole proof) and unanswerable for "the tree".
  Every waiver lands in the ledger as `allowed_dirty`.
- **`state/round_counter` is excused via round 291's existing registry**, not a
  new one. It is ` M` in every round by design; letting it veto every
  differential would make the checker unrunnable from inside the driver it
  serves. Being excused from the *blocking* rule does not make it present in a
  clone — it stays in the untracked/modified accounting.

`run_tests_fast.sh` now prints the last **recorded** verdict after the fast
tier, exactly as round 341 did for the slow tier and at the same price (one
JSONL read). The real check costs a second full suite run; its verdict is free
to display. An unrun check prints `no recorded check (absence of evidence, not
a pass)` — never green.

## 5. The fix to the test itself

`_example_files()` now enumerates via `git ls-files`, with the same fallback
shape as `fuzz.py` (a corpus of 16 beats a collection error if git is absent).
Both floors re-derived against the curated corpus and written down with the
measurement: **12 small files / 3972 tokens; 16 files total / 35188 tokens; 0
divergences.** Both old thresholds (`> 3000`, `> 30000`) still hold — only the
*file-count* floors were wrong, which is the precise shape of the defect.

Two deliberate choices:

- **Not fixed by `git add`-ing the 14 files.** That makes the symptom go away
  and leaves the test still unable to tell its corpus from anyone else's — and
  it would mean adopting another system's files and seeing their churn in every
  diff forever.
- **Duplicated from `fuzz.py` rather than imported.** The whence suite must not
  gain a dependency on `harness/` (same goal as round 349's `-c pytest.ini`
  routing). That creates exactly the [[copied-mirror-drift]] situation on
  purpose — and the checker is what makes it safe, since divergence between the
  two copies surfaces as a test that passes here and fails from git alone. One
  test pins the copy count at exactly two, so a third has to be a decision.

The regression pin asserts the **discrimination**, not the outcome. A test
asserting only "the corpus is non-empty" would pass again the instant someone
reverted the fix, because a glob and a `git ls-files` agree in any clean
checkout. Verified by reverting the fix rather than by reading it:

```
$ <put the glob back>; python3 -m pytest -c pytest.ini tests/test_lexer_guest_parity.py -q
FAILED tests/test_lexer_guest_parity.py::test_the_corpus_is_what_git_tracks_and_not_what_the_directory_holds
1 failed, 81 passed in 45.76s
```

## 6. What the instrument's first real run found

Running all three suites through the differential for the first time turned up
three things nobody was looking for. Two are the checker working; one is the
checker being wrong about itself.

**(a) A live round-354 regression in the `whence_slow` tier.** v0.22's
decision 32 appends a named cure to `unexpected '='`, and
`test_self_eval.py::test_shape_needs_three_adjacent_tokens_on_both_sides`
asserted that message by equality:

```
E  assert "unexpected '=' (Whence has no assignment; a name binds once —
          write `let name = value`)" == "unexpected '='"
```

Round 354's knowledge file says the `whence_slow` result "is reported
separately below/in research-state." It never was — and the round never landed
in git either, which is why this round was landing it. **The slow tier was
broken on the branch and no artifact of round 354 said so.** Rule 2 filed it as
`both_failed`, correctly: it is a real bug, and it is not this round's class.
Fixed by relaxing to a prefix check *plus* an explicit pin that the only
difference is v0.22's hint — a relaxation with no compensating assertion is how
a test dies quietly. `tests/test_v22.py` still owns the exact wording. Slow
tier now: 54 passed, 1193 deselected in 308.6s.

**(b) A test of mine that was invisible to itself.** The census test asserting
"exactly two implementations of the `git ls-files` rule" greps for the literal
`"git", "ls-files", "examples"` — which its own source contains. `git grep`
reads *tracked* content, so it passed while the file was untracked and turned
red the moment it was committed. A test whose result depended on tree state
rather than file content, written *in the round about tests whose results
depend on tree state*. Fixed by excluding its own path, with a comment telling
the next reader not to "repair" it by dropping the assertion instead.

**(c) The ledger was recording a moving target.** Entries stored
`"ref": "HEAD"`. Read tomorrow, that claims a verdict about a different commit
— `slowtier`'s rule 2 in miniature. Now stores `resolved` (the sha) alongside,
and `None` rather than a guess when rev-parse fails.

There is a fourth, smaller one worth keeping: rule 1's own test asserted that
*no calls at all* were made before the short-circuit. That was over-specified —
what the rule promises is that no worktree is allocated and no suite is run,
and the millisecond `git rev-parse` for `resolved` legitimately precedes it.
The assertion was rewritten to say what the rule actually means, rather than
the rule being bent to fit the assertion.

## 7. What the differential said about the rest of the repo

`harness-fast` is **`clean`**: 530 passed in both trees, identical. The harness
suite has no undeclared dependency on anything git does not carry. That is a
real result, not a null one — it is the first time this repo has evidence for
that claim rather than an assumption, and it bounds the finding to one suite
rather than leaving it open.

A static sweep (`git grep` for `glob.glob|os.listdir|iterdir|scandir` across
tracked Python) returns 34 files, but every other one scans a directory this
repo alone writes — `skills/`, `knowledge/`, `harness/tests/`. `examples/` is
the only *shared* directory in the tree, which is why the dynamic check found
one instance and not twenty. It is also why the static sweep is the wrong
instrument: it cannot tell a shared directory from an owned one, and the
differential does not need to.

## 8. Verification

All figures measured in this checkout, this round.

```
harness       bash harness/run_tests_fast.sh        530 passed, 303 deselected
                                                    (was 476 before this round)
              pytest -q harness/tests/test_pristine_check.py
                                                     54 passed in 0.42s
whence        pytest -c pytest.ini tests/ -m "not whence_slow"
                                                   1193 passed,  54 deselected
              pytest -c pytest.ini tests/ -m whence_slow
                                                     54 passed, 1193 deselected
                                                     in 308.6s
              tests/test_lexer_guest_parity.py       82 passed (both tiers)
corpus        curated examples: 16 files / 35188 tokens / 0 divergences
                         small: 12 files /  3972 tokens
```

The differential itself, before and after the fix, both at a committed tree:

```
BEFORE (fd7d91a^ content, ref fd7d91a):
  harness-fast   clean            live 476 passed   pristine 476 passed
  whence-fast    git_incomplete   live 1192 passed  pristine 1 failed, 1191 passed
      GIT-INCOMPLETE  tests/test_lexer_guest_parity.py::test_small_example_files_lex_identically
```

Pins checked by mutation rather than assumed. Reverting `_example_files` to the
glob fails the new corpus test (shown in §5). Four mutations of the checker
itself — dropping rule 1's short-circuit, forcing `completed=True`, dropping
`--force` from worktree removal, disabling the pristine-only comparison — each
killed 1–2 tests. **4/4 caught.** The `--force` mutant matters most: it proves
the four real-git tests at the bottom of the test file earn their runtime,
since no injected-runner fake would have caught it.

## 9. Honest failures and limits

- **A worktree is not a clone in one respect, and this round did not close
  it.** Hooks and `.git/config` are shared. A suite depending on a local git
  config value or a hook still passes in the pristine tree, and this check will
  not see it. Fixture and corpus dependencies — the common case, and the one
  found here — are covered correctly. Named rather than papered over.
- **`untracked_breaks_test` has never been observed live.** The mirror verdict
  (a stray file *breaking* a test) is implemented and unit-tested and has zero
  real instances. Same status as `reachability_check.py`'s `"ambiguous"`
  (round 310's item 3): fixture-tested only.
- **The check cannot run in this repo without a hand waiver, and the reason is
  an open escalation.** `languages/whence/SECURITY.md` — the gateway's edit to
  a *tracked* file, escalated to the operator by round 349 and unresolved for
  six rounds — is the single path that trips rule 1. It was waived by name
  after `git grep` showed no test or source file reads it (only knowledge prose
  and the allowlist JSON). That is a defensible waiver and it is recorded in
  the ledger, but a permanent one would be rule 1 rotting into decoration.
- **The `gitignored` bucket is classified and then unused.** `worktree_dirt`
  separates `!!` from `??` so a dependency on local state is not misfiled as a
  version-control bug, but nothing yet *reports* on it, and no such dependency
  has been found. The distinction is currently prophylactic.
- **One round's data is not a rate.** This round found one instance in one of
  three suites. Whether "a suite that has only ever run in one tree" is a
  common defect here or a one-off is unknown, and a single observation should
  not be written up as either.
- **The `harness-fast` `clean` verdict is about the FAST tier only.** The
  `test_swe_*` slow tier (30+ minutes, 303 deselected tests) has never been
  through the differential. It is the largest uncovered surface, and it is
  exactly the tier `slowtier.py` exists because nobody can run synchronously.
- **The knowledge that fixed this was in the repo and the round still had to
  rediscover it by accident.** No mechanism proposed here would have surfaced
  `fuzz.py::list_example_files` to round 350. The differential catches the
  *consequence*, not the missed reuse. That gap is real and unaddressed.

## 10. Next steps

Round 354's live block was read directly rather than copied. Items 2, 4, 5 and
6 below are inherited from it verbatim in substance; the rest are this round's.

1. **Put the `test_swe_*` slow tier through the differential.** It is the
   biggest surface never checked (303 deselected tests, 30+ minutes), and
   `slowtier.py`'s bounded-budget runner is the right vehicle: run a slice in
   the pristine tree and one in the live tree, ledger both against the same
   digest. Wiring `pristine_check`'s suite registry to `slowtier`'s
   file-at-a-time planner is the concrete task. harness(A) or SWE-loop(D).
2. **Decide whether the differential belongs in the driver's per-round loop.**
   Today it is a tool a round runs by hand, with only its recorded verdict
   shown per round. A full three-suite check is ~15 minutes against a
   55-minute round budget — affordable occasionally, not every round. A
   cadence (every Nth round, or on any round that adds a test file) needs
   choosing rather than drifting into "never again."
3. **`untracked_breaks_test` and the `ignored` bucket are both unexercised.**
   The mirror verdict has zero real instances and the gitignored
   classification is computed and never reported on. Neither is a bug; both
   are prophylactic, and a future round should either find a use or say so.
4. **The worktree/clone gap is open**: shared hooks and `.git/config` mean a
   suite depending on local git configuration still passes in the pristine
   tree. Closing it needs a real clone, which costs history transfer. Not
   attempted, and the common case (fixtures, corpora) is covered.
5. **`languages/whence/SECURITY.md` now blocks a checker, not just a
   question.** Round 354 called it the fifth consecutive round; this is the
   sixth. Round 349 §8 has the evidence table — the rewrite asserts four
   security controls that do not exist in this repo and deletes an authorship
   attribution. New this round: it is the single path that trips
   `pristine_check`'s rule 1, so the differential cannot run here without a
   hand-written `--allow-dirty` naming it. Still the operator's decision, not
   a track's.
6. **Round 354's language(C) items are inherited unstarted**, and round 355
   touched none of them: the mandatory statement separator (item 1, and 354
   called it the largest open item it left); decision 32 generalised to user
   functions (2); a test that no declared builtin kind is stricter than its
   handler (3); a differential over every guest-constructed miss reason (4);
   dropping `test_spec_builtins.py`'s now-redundant round-349 source-greps
   (5); an `examples/*.lang` that demonstrates v0.22 by catching misses as
   values (6).
   **One correction to that list.** Item 5's premise held; but this round's
   `test_self_eval.py` fix (§6a) shows the v0.22 work had a second, unlisted
   consequence — a slow-tier test asserting the old message text. A future
   language(C) round changing an error string should grep the whole tree for
   the literal, not just the fast tier.
7. **Round 353's SWE-loop(D) items** (re-running round 137's 260 mutants on a
   second host; `scoreaudit`'s blindness to a pre-existing failing test; the
   nine archived reports that can never acquire a baseline; the
   `param_erasure` oracle) are untouched by this round, as they were by 354.
8. **`harness/swe/regiontools.py`** is still deliberately un-unified with
   `EditFileTool` (round 307's item 2) and **round 301's item 2** (blocking-
   wait mitigation sketch) remains speculative. **Neither re-derived this
   round** — carried on round 354's carry of round 353's re-derivation, and
   flagged as such rather than restated as fresh. `state_claim_check.py`
   scores them at 24 and 28 carries respectively.
9. **NUC-integration(E)'s standing items** are untouched; the rotation has not
   reached that track since round 352, and the box's state is unknown.

### A carried claim this round nearly re-introduced

Two items in the first draft of this list were wrong, and the way they got
there is worth recording because it is this round's own subject in a different
medium.

Drafting §10 by reading the **tail** of `research-state.md` picks up an old
frozen block, not the live one: round 351 established that the trailing stack
is only roughly reverse-chronological, so file order does not select the newest
block. From that tail came "`fuzz-mutate-kill-loop/SKILL.md` is still 415 body
lines (B002), the only thing between the corpus and a warning-free
`--house --strict` sweep — 8th consecutive round carried."

Every part of that is false, and has been since round 339:

```
$ python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/*/
skill-lint: 26 skill(s), 0 error(s), 0 warning(s)
$ <body line count of fuzz-mutate-kill-loop/SKILL.md>
399
```

B002 fires above 400. The file dropped 415 → 399 in round 339 as a side effect,
nine next-steps blocks re-asserted 415 anyway, and **round 351 found it, wrote
`state_claim_check.py` to detect it, and corrected the live block.** The tool
worked here exactly as designed:

```
$ python3 skills/skill-authoring/scripts/state_claim_check.py --run state/research-state.md
state_claim_check: research-state.md — live block is round 354 (line 9871) of
60 blocks; 11 item(s), 3 with a checkable claim
state_claim_check: 3 claim(s): 3 re-derivable, 0 skipped (none); 0 stale
```

Round 354's live block is **clean** — it never carried the claim. The rot was
entirely in this round's drafting method. The correction is not "be careful":
it is that `state_claim_check.py --run` names the live block by line number,
which is the only reliable way to find it, and reading the file's tail is not a
substitute. Cost: one command. This round did not run it until after the
first draft.


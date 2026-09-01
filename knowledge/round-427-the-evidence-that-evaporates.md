# Round 427 (harness A) — the evidence that evaporates without going red

**Track:** harness(A). **Subject:** `harness/pristine_check.py`, the
instrument this program built (round 355) to answer *"does this repo pass its
own tests from git alone?"*, and which has compared the two trees by FAILURE
SET only for 72 rounds.

**One sentence.** A test whose fixture git does not carry can fail — which
the differential sees, calls `git_incomplete`, and exits 1 — or it can
*skip*, which produces an empty failure set on both sides, verdict `clean`,
exit 0 in both trees, and a count line every round quotes; this round
measured **11 whence tests in that state at HEAD**, built the differential
that sees them, and found that the fix which created them was recommended by
this repo's own skill for eighteen rounds.

## 0. Pre-flight: round 426's diff, and a literal placeholder in the record

The record-gap check reported round 426 as *"has a research-state.md entry
AND a knowledge file but never actually landed in git"* — the fourth
interrupted round in five (422, 424 and 426 interrupted; 423, 425 and this
one landing someone else's diff). Round 426's work is real and its tests are
green: verified before landing, `66 passed in 25.28s` on
`languages/whence/tests/test_polarity.py` (round 426's own run: 56.94 s).
Landed as commit `02b6ef0`.

**One substitution, because it was a defect and not a finding.** The
round-426 entry in `state/research-state.md` contained the literal token
`FULL_LIVE_PLACEHOLDER` where a full-suite result belonged. Round 426 died at
the turn cap before filling it in. This round did not run a full live suite
on round 426's behalf and did not invent a number; it replaced the token with
a statement that the suite was not run, plus the driver's own post-round
health check, which is the only full-suite measurement of round 426's tree
that exists (`logs/driver.log` 10:57:52: `2104 passed, 3 skipped, 91
deselected in 613.61s` and `1115 passed, 298 deselected in 683.16s`).

Worth naming as a class: **an interrupted round can leave a template token in
the permanent record, and nothing in this repo looks for one.** `state_claim_
check.py` checks claims that parse as claims; `FULL_LIVE_PLACEHOLDER` parses
as nothing. It survived a driver health check, a skills check and a
record-gap check, and would have survived indefinitely had round 427 not read
the entry it was landing.

**It is not the first, and the first is still there.** Grepping this round's
own output for placeholder tokens — a check run against my own files out of
embarrassment, not diligence — turned up
`state/research-state.md:667`: round 205 wrote

> Ran the full `harness/tests/` suite in the background (third round in a row
> attempting this confirmation…) — `[TEST_RESULT_PLACEHOLDER]`.

Round 207 **found it, wrote a paragraph about it** (line 739: "the
`[TEST_RESULT_PLACEHOLDER]` in its round-log entry above was STILL
running…"), used it as evidence for a skill — and did not fill it in. It has
sat in the permanent record for **222 rounds**. Two instances, both from the
same cause (a suite launched and never read), both ending in `_PLACEHOLDER`.
That last fact matters for the fix: my first instinct was that a fixed token
list catches only repeats, and the repeat is exactly what the record
contains. A grep for `_PLACEHOLDER` alone would have caught both.

`languages/whence/SECURITY.md` is NOT in that commit: still the round-349
escalation, still content-pinned at `61248e50a3f5`, still the operator's.

## 1. The class, stated exactly

`compare()` in `harness/pristine_check.py`, as it stood at `02b6ef0`:

```python
lf, pf = set(live["failures"]), set(pristine["failures"])
if pf - lf:      verdict = "git_incomplete"
elif lf - pf:    verdict = "untracked_breaks_test"
elif lf:         verdict = "both_failed"
else:            verdict = "clean"
```

Every branch reads a FAILURE SET. A test that reacts to a missing fixture
with `pytest.skip` contributes to none of them. `pf - lf` is empty, `lf - pf`
is empty, `lf` is empty — `clean`, exit 0, in both trees.

That is not hypothetical and it was not cheap to see. Run against the real
records this round measured, HEAD's own `compare` (loaded straight out of
`git show HEAD:harness/pristine_check.py`, not paraphrased):

```
OLD compare verdict: clean  exit: 0
OLD record keys mentioning skip: []
```

with these two inputs, measured at `02b6ef0`, one live tree and one
`git worktree --detach` of the same commit:

| suite        | live                                     | pristine                                 |
|--------------|------------------------------------------|------------------------------------------|
| whence-fast  | `2104 passed, 3 skipped, 91 deselected`  | `2093 passed, 14 skipped, 91 deselected` |
| harness-fast | `1115 passed, 298 deselected`            | `1115 passed, 298 deselected`            |

**Eleven tests. Both sides exit 0. Both sides green.**

## 2. Why `-rs` is the wrong flag, measured before writing anything

Round 426's next-steps item 7 named the flag: *"diff the SKIP list, not just
the pass count — `-rs` is the flag."* It is not, and five minutes of probing
before the design settled says why. `pytest -q -rs` prints:

```
SKIPPED [1] test_probe.py:6: module-level decorator reason
SKIPPED [1] test_probe.py:11: runtime skip reason with: colon and [brackets]
```

**Keyed by file and LINE.** A differential on that key reports a phantom
evaporation every time someone inserts an import above the test, and
aggregates two distinct tests that share a location and reason into `[2]`.
`--junitxml` carries `classname` + `name` — node identity — and costs one
flag on a run you are already paying for:

```
'tests.test_v34' | 'test_no_field_program_stalls_on_a_no_cure_error_any_more'
```

Two more facts that only a probe gives you, both now load-bearing in the
code:

- **An xfail is a skip in junit.** `<skipped type="pytest.xfail">`. An xfail
  is a test that ran and behaved as declared; counting it would put a
  permanent false positive in every report this instrument ever generates.
  `parse_junit` filters on `type`, and `test_an_xfail_is_not_a_skip` pins it.
- **This pytest emits no `file`/`line` attribute on `<testcase>`.** So the
  readable node id has to be *reconstructed* from the dotted `classname`,
  and that reconstruction is a heuristic (a capitalised trailing component
  is a class). Which leads to the one design decision worth copying.

## 3. The heuristic is not allowed to decide anything

`junit_node_id("harness.tests.test_agent.AgentLoopTests", "test_x")` →
`harness/tests/test_agent.py::AgentLoopTests::test_x`. That is a guess about
Python naming convention. A guess must not be able to change a verdict, so
it cannot: **every comparison and every acknowledgement is keyed on the raw
`(classname, name)` pair**, and the reconstructed id is used for printing
only. `test_the_node_id_heuristic_cannot_change_a_verdict` proves it by
replacing `junit_node_id` with `lambda c, n: "GARBAGE"` and asserting the
keys, the counts and the verdict are identical.

The heuristic's own assumption — that no directory or module in the test tree
is capitalised — is checked against the real tree by
`test_the_test_tree_has_no_capitalised_module_or_directory`, which walks
`harness/tests` and `languages/whence/tests` rather than asserting it in a
docstring. If someone adds `harness/tests/Helpers/`, that goes red and the
heuristic gets replaced instead of patched.

## 4. The finding behind the finding: this repo's own skill built the class

`skills/pristine-checkout-differential/SKILL.md` is where this technique
lives. Two of its sections cancelled each other out, and had since round 409.

**Step 4, verbatim, before this round:**

> Difference the FAILING TEST IDS, not the pass counts. Counts move for
> uninteresting reasons (collection differences, **skips**, a parametrised
> case count that depends on the corpus you are investigating).

**A pitfall, verbatim, before this round:**

> An IGNORED corpus makes every worktree red at every commit, forever. […]
> **The fix is a SKIP with a reason that names the cause** […]

The pitfall tells you to convert a `git_incomplete` into a skip. Step 4 tells
you that skips are noise. The instrument implemented step 4 exactly. So the
recommended remedy for one pitfall *manufactures* a defect the same document
tells you to ignore — and the document has said both things, in the same
file, for eighteen rounds.

This is not a reading of the text; it is the measured history:

| commit                  | round | `field_corpus_absent` call sites | tests skipped by it |
|-------------------------|-------|----------------------------------|---------------------|
| `50c7bb3`               | 409   | 2 files                          | **4**               |
| `02b6ef0`               | 427   | 4 files                          | **11**              |

Both numbers are runs, not greps: `50c7bb3` checked out into a worktree and
its whence fast tier executed gives `1936 passed, 14 skipped` of which 4 name
`FIELD_CORPUS_ABSENT_REASON`; `02b6ef0` gives `2093 passed, 14 skipped` of
which 11 do.

Round 409 wrote the guard to close four reds it had itself found, and wrote
it well — `curecheck.field_corpus_skip_reason` is a careful four-state
decision that deliberately refuses to skip on partial drift. **The growth
from 4 to 11 was never a decision.** Each later test that touched the corpus
reached for the sibling's guard because it was there. That is the single
concrete reason the acknowledgement registry built this round is keyed **per
node and never per reason**: a new test inheriting an already-acknowledged
skip reason goes red on purpose, because *"should this test depend on a
corpus git does not carry?"* is a question, and inheriting the answer from a
neighbour is how 4 became 11 with nobody answering it once.

## 5. What was built

### `harness/pristine_check.py` (+~330 lines)

- `parse_junit(path)` — per-node outcomes from a `--junitxml` report. Never
  raises; a missing, empty or malformed file returns `ok=False`, which every
  caller treats as **absence of evidence**, never as "no skips". Rule 3 of
  the module's four, applied to a new class.
- `skip_key` / `junit_node_id` — decide vs. read, §3.
- `compare_skips(live, pristine, suite, acks)` — the differential. Four
  buckets, because they mean four different things: `unacknowledged` (sets
  the verdict), `acknowledged` (printed, never silent, no verdict),
  `pin_expired` (**louder** than unacknowledged), `dead_acknowledgements`
  (suppresses nothing → delete it). Plus `condensed`, the mirror — skipped
  here, runs from git alone — reported and never a verdict, because the live
  tree having *less* evidence than git is not a git defect.
- Three non-findings encoded so they can never be reported as findings:
  skipped in BOTH trees; absent from the live run entirely (a test the ref
  has and this tree does not never had evidence here); failing live and
  skipped pristine (evidence was already gone, and the failure differential
  owns it).
- `_JunitScratch` — a `/tmp` directory removed on every exit path, including
  a raise, and **not** removed if the caller supplied it. The report must
  live outside both trees: written into the live tree it is an untracked file
  that makes rule 1 block the very next `check` (round 409's `OWN_RECORDS`
  trap in a new place), written into the worktree it is dirt handed to
  `git worktree remove`.
- New verdict `skip_evaporation`, exit code **1**, ranked directly below
  `git_incomplete` and above `untracked_breaks_test` and `both_failed`. The
  ranking is the argument: it has the *same cause* as `git_incomplete` — git
  does not carry what the test needs — and differs only in how loudly the
  test reacted. **A checker that ranked the quiet reaction lower would reward
  defending a test with `pytest.skip`.**
- `baseline` now records the skip LIST, not a count, and says so
  (`skips: 14 recorded — a skip is not a pass, and \`check\` is what decides
  whether any of these ran in the live tree`). Round 426 had a baseline
  saying `14 skipped` and still had to re-run the whole suite by hand to
  learn *which* eleven.
- `run_suite`'s junit report is **opt-in**, so a bare `run_suite`'s argv is
  still exactly `SUITES[name]["argv"]`. That registered argv is the claim
  "this is what the driver runs"; silently appending would make it false.

### `state/known-pristine-skips.json` — the third acknowledgement registry

Deliberately not merged with either of the other two.
`known-standing-dirty-paths.json` models untracked files a third party leaves
behind (unconditional entries); `known-escalated-diffs.json` models a tracked
diff a round adjudicated (content-pinned); this one models **a test that
stops being evidence in a fresh clone**. Shared discipline, different
subject. Eleven entries, every one pinned to the exact skip reason text, each
naming round 426 as finder and this round's measurement commit.

The pin is the point. A name-only allowlist would let a test acquire a
second, unrelated reason to skip and stay silent forever; here, change *why*
a test skips and the acknowledgement expires by itself and reports **louder**
than an unacknowledged skip — it is a skip nobody adjudicated wearing a
signature that says somebody did.

### Tests: `harness/tests/test_pristine_check.py`, 87 → 126

All green, `126 passed in 3.12s`. 38 of the 39 are offline (injected
runners, no worktree, no pytest subprocess). The 39th is the one that
matters:

`test_a_real_gitignored_fixture_makes_a_real_test_evaporate` — 5.09 s, no
fakes at all. It builds a real git repo, a real `.gitignore` naming a real
fixture, a two-test suite whose second test skips when that fixture is
missing (round 404's shape, from scratch), commits, writes the fixture into
the working tree only, and runs the **real** `differential` three times
against three real worktrees:

1. no acknowledgement → `skip_evaporation`, exit 1, `pristine_skips == 1`,
   `live_skips == 0`, nothing red on either side;
2. matching acknowledgement → `clean`, one entry in `acknowledged`;
3. same entry, `reason_pin` changed → `skip_evaporation` again, one entry in
   `pin_expired`.

That is the whole mechanism — detection, suppression, and expiry of the
suppression — proven end to end without a single test double.

## 6. The skill, upgraded where it was wrong

`skills/pristine-checkout-differential/SKILL.md`:

- **Step 4 lost the word "skips"** from its list of uninteresting reasons a
  count moves, with a sentence saying so and naming the cost.
- **New step 4a** — difference the SKIPPED ids, keyed by node id and never by
  line, with the `-rs`-vs-`--junitxml` evidence, a 15-line `outcomes()`
  helper a reader can paste, the xfail trap, the write-outside-both-trees
  rule, and the three look-alike non-findings.
- **Step 5 went from four verdicts to five**, with the ranking argument.
- **Two new pitfalls.** The first states plainly that the skill's own
  ignored-corpus remedy manufactures this class, with the 4→11 measurement,
  and adds: *if you convert a red to a skip, you owe an acknowledgement entry
  in the same change*. The second is the acknowledgement-registry design —
  pin the reason, per node never per reason, print acknowledged entries every
  run, report dead entries.
- **A third pitfall**: a baseline that records only counts cannot be re-read.
- **Verification split into `references/verification-log.md`.** The body
  crossed `skill_lint`'s B002 threshold (400 lines) at 459. Rather than cut
  new content to fit, the round-355 and round-409 transcripts moved to a
  reference file with anchors and a contents list — the STEPS are what a
  reader needs at 3am, the transcripts are what they need when they doubt
  one. `skill_lint --house --strict skills/`: **69 skills, 0 errors, 0
  warnings**, which is the state round 426 left it in.

## 7. What this still cannot see, stated so nobody reads more into it

- **Round 425's class-4 instance is NOT closed by this.**
  `languages/whence/tests/test_v37.py::test_the_host_is_byte_unchanged_by_this_decision`
  goes `passed -> skipped` inside the **mutation sandbox**, which is
  `_copy_project`'s tree, not a git worktree — it excludes `.git`, and a git
  worktree does not. Measured this round: that test does **not** evaporate in
  a pristine worktree, and it is not among the 11. What round 427 built is
  the same *shape* of mechanism round 425's item 1 asked for, in a different
  tree; `mutation.baseline_check` still needs its own. Do not read this
  round's registry as covering it.
- **A skip that exists in both trees is invisible here by design**, and that
  is a much larger population than 11. This differential answers "is this
  repo's evidence complete *in a fresh clone*", not "is this repo's evidence
  complete".
- **Hooks and `.git/config` are shared by a worktree**, so a suite depending
  on local git config still passes in the pristine tree. Pre-existing
  limitation of the module, unchanged.
- **The check costs a full second suite run.** It is a periodic check, not a
  per-commit one, and the driver still does not run it (round 374's finding
  stands: `harness/run_tests_fast.sh:105` runs `status`, which re-prints a
  stored verdict, and swallows its exit code with `|| true`). That last fact
  is why adding a new exit-1 verdict could not break the driver — checked
  before adding it, not after.

## 8. The prediction bank, scored (D-013)

`state/round-427-predictions.md`, written after reading the module and after
landing round 426's diff, but before running any suite this round and before
writing a line of the capability.

| # | prediction | result | verdict |
|---|------------|--------|---------|
| A1 | live `whence-fast` = 3 skipped | `2104 passed, 3 skipped` | **HIT** |
| A2 | pristine `whence-fast` = 14 skipped | `2093 passed, 14 skipped` | **HIT** |
| A3 | all 11 extras name a fixture git does not carry; none skipped live for another reason | 11/11, and **one distinct reason string** shared by all eleven | **HIT** |
| A4 | `harness-fast` shows zero evaporations | live 0 skips / pristine 0 skips, 1115 nodes each | **HIT** |
| A5 | `check` returns `clean`, exit 0, with 11 tests providing no evidence | HEAD's own `compare`, loaded from `git show`, on the measured records: `clean`, exit `0` | **HIT** |
| B2 | junit `classname` is dotted and needs converting | `tests.test_v34` / `harness.tests.test_agent.AgentLoopTests` | **HIT** |
| B3 | ≥1 test yields a THREE-component classname, breaking a naive last-dot split | **PARTIAL** — see below | **PARTIAL** |
| B4 | the report must live outside both trees | held; `_JunitScratch` | **HIT** |
| C1 | pristine `whence-fast` takes 240–400 s | **128.79 s** | **MISS** |
| C2 | `--junitxml` adds < 5 s to a ~250 s run (< 2%) | +3.92 s, but on a 125 s run = 3.1%, and inside the noise | **PARTIAL** |
| D1 | the 11 skips are correct; deleting them is not the fix | not attempted | **HIT** |
| D2 | a name-only acknowledgement is insufficient; pin the reason | implemented and pinned by `test_an_acknowledgement_expires_when_the_skip_reason_changes` | **HIT** |
| D3 | the five existing verdicts keep meaning and exit codes; the new class gets a new verdict | unchanged; `skip_evaporation` added at exit 1 | **HIT** |

**B3 is PARTIAL and the way it is wrong is worth more than the hit would
have been.** The prediction named *three components* as the breaking case.
Measured: the whence suite's classnames are **2 components without
exception** (2107 of 2107, `tests.test_x`), and the harness suite's are 3
(922) and 4 (193). The 3-component ones — `harness.tests.test_adapters` —
are plain modules and break nothing. **The component COUNT is not the
discriminator at any depth; a capitalised trailing component is**
(`harness.tests.test_agent.AgentLoopTests`). The prediction reached for a
proxy (depth) for the property that actually matters (capitalisation), which
is the same error shape as measuring a corpus by counting the directory.

**C1 is a 2–3× overshoot in the same direction as round 422's E1** (80–200 s
predicted, 40.94 s measured). Two consecutive banks in this program have
over-estimated a suite's wall-clock by roughly the same factor. The number
being over-estimated came from prose — round 426's research-state entry
quotes `257.06 s` for the fast tier — and a re-quoted number was carried into
a prediction about a different tree instead of being re-derived. `logs/` has
the real per-round timings and nothing consults them when a bank is written.

**B1 is not scored.** It was written as a design commitment ("`-rs` keys by
line, junit keys by node; the implementation will use junitxml") after the
probe that established it, and a bank entry that records a decision already
made is not a prediction. It is marked as such in the bank itself rather than
being quietly counted as a hit.

**C2 is PARTIAL twice over, and the second half is a lesson about my own
measurement rather than about pytest.** Controlled A/B, same suite, same
box, back to back:

```
NOJUNIT  2104 passed, 3 skipped, 91 deselected in 124.49s   real 125.09
JUNIT    2104 passed, 3 skipped, 91 deselected in 128.38s   real 129.01   (261,380-byte report)
```

`+3.92 s`. The absolute clause ("< 5 s") holds; the ratio clause ("< 2%")
does not, at 3.1% — **and it fails only because C1's denominator was wrong**,
which is the same error propagating into a second prediction. But the honest
reading is weaker than either: **the whence fast tier measured 127.87,
128.79, 124.49 and 128.38 s across four runs on this box today**, a spread of
4.3 s. An effect of 3.92 s at n = 1 is *not resolved* by this measurement. It
is bounded above by roughly 4 s and that is all this round can say. Reporting
`+3.92 s` as if it were the overhead would be a number with no error bar,
which is the thing this program keeps catching other rounds doing.

**Bank total: 10 HIT · 2 PARTIAL · 1 MISS of 13 scored, 1 not-a-prediction.**

## 9. Disclosed costs, including the ones this round caused

- **`case_coverage` 54/69 → 53/69 probed.** Editing this skill's
  `description` invalidated its probe reports:
  `P004 pristine-checkout-differential: probe status is STALE under the
  description on disk`. That is a real loss of coverage and it is the price
  of the description being *correct* about the new triggers — the old one
  described a failure-only differential. A `trigger_eval` round re-probes it;
  this round cannot, and does not pretend the number is unchanged. Same class
  as round 426's own disclosure.
- **Three trigger cases added, unprobed** (`pcd-skip-near`, `pcd-skip-mid`,
  `pcd-skip-neg-ratio`; 295 → 298). They document the new triggers and they
  worsen the recall denominator until probed. **No boundary case against
  `skip-reason-is-a-claim` was added**, for round 426's reason: a case
  expecting another skill degrades *that* skill's denominator, and that is
  its owner's trade to make. The boundary is stated in the `## Related`
  section instead, where it costs nobody anything.
- **`skill_lint` B002.** The body reached 459 lines (warn threshold 400,
  error 500). Fixed by splitting the round-355/409 transcripts into
  `references/verification-log.md` with anchors and a contents list, and by
  compressing prose — **not** by cutting the new steps. Final:
  `69 skills, 0 errors, 0 warnings`, which is the state round 426 left.
- **`claim_check` regression caused by that split, caught by the corpus
  check and fixed.** Moving the Verification section took every runnable
  command with it, and the skill parsed to **zero** commands —
  `test_only_the_known_prose_only_skills_parse_to_zero_commands` went red
  naming it. A skill whose verification cannot be re-run is a skill whose
  verification is a story. Fixed by keeping this round's actual `check`
  invocation and output inline.
- **`carryforward` K001, caused by this round's own bank.**
  `state/round-427-predictions.md` existed on disk with no
  `state/prediction-bank-ledger.json` entry — exactly what that checker is
  for. Discharged in §8 and entered in the ledger as `scored`.

## 10. Two process notes, both cheap and both cost this round time

- **`pgrep -f <pattern>` matches the shell running it.** Three background
  waiters of the form `while pgrep -f "pytest ... harness/tests"; do sleep;
  done` spun forever, because each one's own `bash -c` command line contains
  the pattern. They were killed by PID (exit 144, the expected signal
  status) and the measurement re-run directly. This is
  `feedback_pkill_f_matches_your_own_shell` in the polling direction rather
  than the killing one; the same fix applies — resolve PIDs first, or match
  on something the waiter itself cannot contain.
- **`| tail -20` on `harness/run_tests_fast.sh` returns only the epilogue.**
  The script echoes `pristine_check status` and a `procreap` scan after the
  run, and both together are longer than 20 lines, so the pytest result —
  the thing being measured — is discarded. Known
  (`feedback_tail_n_can_hide_the_measurement`, and this repo's own round 409
  item 3), hit anyway. Redirect to a file and grep for the count line.

## 11. Results

```
harness fast tier   1154 passed, 298 deselected in 225.09s   (was 1115 — +39 new tests)
test_pristine_check  126 passed in 3.12s                      (was 87)
skill_lint --house --strict skills/   69 skill(s), 0 error(s), 0 warning(s)
whence-fast, live tree      2104 passed,  3 skipped, 91 deselected in 127.87s
whence-fast, pristine HEAD  2093 passed, 14 skipped, 91 deselected in 128.79s
harness-fast, live tree     1115 passed, 298 deselected (0 skipped)
harness-fast, pristine HEAD 1115 passed, 298 deselected (0 skipped)
whence-fast at 50c7bb3 (r409), pristine   1936 passed, 14 skipped — 4 field-corpus
```

No SPEC bump: nothing under `languages/whence/whence/` was touched and
Whence stays at v0.41. The whence measurements above are of round 426's
committed tree (`02b6ef0`) and this round did not edit that language.

## Next steps (as of round 427)

1. **Round 425's item 1 is now half-answered and the other half is still
   SWE-loop(D).** The acknowledged-baseline mechanism it asked for exists
   (`state/known-pristine-skips.json` + `compare_skips`), reason-pinned,
   with expiry and dead-entry reporting — but it lives in
   `pristine_check`, whose second tree is a `git worktree`. Round 425's
   actual instance evaporates in the MUTATION SANDBOX (`_copy_project`,
   which excludes `.git`), and this round MEASURED that it does not
   evaporate in a worktree. `mutation.baseline_check` needs the same
   mechanism pointed at its own tree; the registry format and the four
   buckets are there to copy. SWE-loop(D).
2. **The 11 acknowledged evaporations are acknowledged, not fixed, and the
   fix is a decision nobody has made.** A fresh clone runs 11 fewer whence
   tests than this box, permanently, because round 402 `.gitignore`d the
   14-file field corpus that a separate system writes. Three real options,
   none of them this round's to pick: commit a curated subset as fixtures
   (and take ownership of files another system writes — the trap this
   repo's own skill warns about); synthesise an equivalent corpus that git
   CAN carry; or accept the loss and stop counting those tests as evidence
   in published numbers. language(C) or the operator.
3. **A literal template token survives into the permanent record and
   nothing looks for one — TWICE now, 222 rounds apart.**
   `FULL_LIVE_PLACEHOLDER` (round 426) passed a driver health check, a
   skills check and a record-gap check;
   `[TEST_RESULT_PLACEHOLDER]` (round 205, `state/research-state.md:667`)
   is **still there**, and round 207 found it, wrote a paragraph citing it,
   and left it. Same cause both times: a suite launched in the background
   whose result the round never read. Both end in `_PLACEHOLDER`, so the
   objection that a fixed token list only catches repeats is answered by
   the record — the repeat is what the record has. A grep for
   `_PLACEHOLDER|TODO|TBD|XXX|FIXME` over `state/*.md` and `knowledge/*.md`
   is ten lines and belongs beside `state_claim_check` in
   `corpus_check.py`. Round 205's instance is unrecoverable (its output
   lived in `/tmp`) and should be marked as such in place rather than
   filled in by a later round. harness(A) or skills(B).
4. **Nothing runs `pristine_check check`, and now it has something to say.**
   `harness/run_tests_fast.sh:105` runs `status`, which re-prints a stored
   verdict and swallows the exit code with `|| true`; the last stored record
   before this round was 14.9 hours old and pinned to `50c7bb3`, a commit
   HEAD had moved off. The differential costs a second full suite run so it
   cannot be per-round, but the gap between "14.9 h stale" and "never" is a
   scheduling decision nobody has made. `verb_audit` already counts `check`
   and `baseline` among the unreached verbs (round 425's item 5). harness(A).
5. **Two banks in a row over-estimated wall-clock by 2–3×** (this round's
   C1, round 422's E1), both by re-quoting a number from prose instead of
   from `logs/round-NNN.json`, which has the real timings and which no bank
   has ever consulted. A bank that predicts a duration should be required to
   name the log line it derived the estimate from. skills(B).
6. **Round 426's items 1–6 carry forward unchanged** — `refusal` is still
   undecided, the designed pin-pair experiment is still the cheapest route
   to `p = 0.029`, the `plus` campaign still has not been re-run against the
   current guest file, and the repointed registry still needs taking
   seriously or retiring. All language(C).
7. **Round 425's items 2–20 carry forward** except where closed above.
   Round 408's item 9 — CLAUDE.md's `🔴 CRITICAL MISSION` block, stale in
   both halves — is re-escalated for the TWELFTH time and still needs the
   operator. `languages/whence/SECURITY.md` is still carried and still the
   operator's decision; **do not copy a carry count for it from this file**,
   the checker's own line is the only source.

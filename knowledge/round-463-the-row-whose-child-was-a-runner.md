# Round 463 (harness A) — the row whose child was a runner

**Subject:** round 461's next-step 1. *"`unit_tests` is 25 of the 60 red
checker-rows and its failures are unrecoverable. `corpus_check.run_one`
unlinks its `tempfile.mkstemp` sink in a `finally`, so no round can say WHICH
test failed inside any red `unit_tests` row, ever. ... skills(B) owns the
file; harness(A) owns the log-retention convention."*

Taken. The retention half is what was asked for. The other half — what the
row published *instead* of the evidence it destroyed — was not asked for,
was found while measuring the baseline, and is the larger finding.

Predictions banked at `4cc4274` **before** the baseline ran:
`state/harness/round-463/PREDICTIONS.md`. Scored in §8.

---

## 0. The baseline, re-derived before anything changed

Round 460's item 5 and round 461's P1-P4 rule: re-derive a carried number
before quoting it, and prefer one whose COMMAND is banked.

```sh
python3 - <<'EOF'
import sys, collections; sys.path.insert(0, "harness"); import redattrib as R
rows = R.corpus_rows()["skills_health_round"]
red, tot = collections.Counter(), collections.Counter()
for rnd, per in rows.items():
    for chk, (st, codes) in per.items():
        tot[chk] += 1
        if st == "ERROR": red[chk] += 1
print(len(rows), "logs", min(rows), "-", max(rows)); print(red.most_common())
EOF
```

| checker | red rows | rows | not-conclusive |
|---|---|---|---|
| **unit_tests** | **26** | 99 | 5 (TIMEOUT) |
| carryforward | 20 | 94 | 0 |
| case_coverage | 7 | 99 | 0 |
| xref_check | 5 | 99 | 0 |
| skill_lint | 4 | 99 | 0 |
| claim_check | 2 | 99 | 0 |
| state_claim_check | 1 | 99 | 0 |
| | **65** | | |

**26 of 65, not 25 of 60.** The carried pair was one round stale — round 462's
log had landed since round 461 wrote it. The *claim* it makes was exactly
right, and the direction of the staleness is the boring one. Seventh
consecutive round in which re-deriving a carried number changed its answer.

99 logs, rounds 364-462. `unit_tests` is the reddest row in the repo by 30%
over the runner-up, and it is red on 26% of the rounds it has existed for.

## 1. The evidence loss, confirmed

`run_one` streams the child to a `tempfile.mkstemp` sink so a killed child's
output survives the kill (round 451's repair), reads it, and then:

```python
    finally:
        try:
            os.unlink(sink_path)
        except OSError:
            pass
```

On every branch. The timeout branch that round 451 taught to *parse* partial
output still deleted the file it parsed. What survives a red `unit_tests`
row in `logs/skills_health_round_<N>.log` is one line:

```
unit_tests         ERROR rc1              2 failed, 937 passed in 353.93s (0:05:53)
```

The COUNT survives. The IDENTITIES do not, and no instrument in the repo can
recover them. `redattrib.py evidence` now states that as a number: **70
not-green rows over rounds 364-462, 0 with a retained file.**

## 2. The finding round 461 did not ask for: the row's fields were borrowed

19 of the 26 red rows say `rc1`. **Seven say something else** — `P001`,
`C001`, `S001,S002,S006` — and those are not `unit_tests`'s codes. They are
other checkers' codes.

`unit_tests` is `pytest -q skills/skill-authoring/scripts
skills/session-inheritance-audit/scripts`, and those tests **invoke the other
nine checkers**. When one fails, pytest dumps the captured stdout of the
checker the test drove into its traceback. `_findings_in` and `coverage_of`
— written to read *a checker's own output* — then read *another checker's
output through a test runner's failure report*.

`logs/skills_health_round_398.log` is the clean specimen, and it is the whole
argument in four lines:

```
case_coverage      ERROR P001                ...
state_claim_check  ERROR S001,S002,S006      ...
unit_tests         ERROR P001,S001,S002,S006 5 failed, 703 passed in 138.90s
corpus-check: 7 checker(s), 9 error(s), 10 warning(s)
```

The third row is the **literal union of the two above it**. And because
`n_err = sum(len(r["errors"]))`, the aggregate says **9 error(s) for 5
distinct violations** — and that line is what `driver_line` copies into
`driver.log` for a human.

Same generator, third field: **21 of the 99 aggregate lines publish a
`unit_tests <coverage clause>` that belongs to another checker.** Round 419's
is `state_claim_check`'s, verbatim:

```
; coverage: ... state_claim_check 6/10 items (60%), 6/6 claims; ... unit_tests 6/10 items (60%), 6/6 claims
```

One measurement, published twice under two names, on the line the driver
logs. Nothing in the repo said so.

**This is not a parsing bug.** The regex is correct; it is pointed at a
stream whose author is not who the row says it is. No pattern distinguishes
"the checker I ran printed P001" from "I printed P001" in a captured-stdout
dump.

## 3. The repair

### 3.1 A runner publishes its own verdict

`RUNNER_CHECKS` names the rows whose child runs the other children, with the
reason. For such a row `run_one` no longer publishes scraped fields:

* `errors` is `["rc1"]` when the child exited non-zero, `[]` otherwise.
* `warnings` and `coverage` are empty.
* `failed_nodes` holds the pytest node ids from the output's short summary.
* **`borrowed` keeps what was replaced.** "What did this row used to say?" is
  the first question a reader of an old log asks, and deleting the answer
  would repeat the mistake one level up.

`rc1` is kept as the *token* deliberately, and this is where a correct fix
nearly became a silent regression. Two downstream readers parse it:

```python
corpus_history.LIVE_CODE_RE = re.compile(r"\b(\w+)\s+(?:ERROR|error)\s+([A-Z]\d{3}|rc1)\b")
redattrib.CORPUS_ROW       = re.compile(r"^(\w[\w.]*) {2,}(ok|warn|ERROR|TIMEOUT|ABSENT)(?: (\S+))?")
```

A richer token — `5-failed` was the first draft — fails the first
alternation and drops the row from `corpus_history` entirely, trading a
visible over-count for an invisible under-count. `test_rc1_is_kept_as_the_
token_so_both_downstream_readers_still_parse` pins both.

### 3.2 Retention

`_attach_evidence` writes a NOT-CLEAN run's output to
`logs/corpus-evidence/round-<N>/<check>.out`.

* **Predicate:** `rc != 0 or errors`. A `warn`-only run is CLEAN — rc 0, no
  errors — so it keeps nothing, and a green corpus check **creates no
  directory at all**. An `absent` check had no child and keeps nothing.
* **Cap:** `elide()` at 256 K characters, keeping the first 64 K and the last
  192 K with a marker naming the elided count. The tail is the bigger half on
  purpose: pytest prints its short summary LAST, so a head-only cap retains a
  file and still loses the answer. `test_a_capped_pytest_dump_still_yields_
  its_failing_node_ids` is that assertion.
* **Round number from `state/round_counter`, not from the driver.**
  `run_driver.sh` writes `ROUND` at the top of a loop iteration (line ~258)
  and launches the four health checks later in the SAME iteration (line
  ~542), so the counter already holds this round's number. **`run_driver.sh`
  is not edited by this round**, which means there is none of the one-round
  re-exec lag round 457's fix had to warn its successor about — the retention
  worked in the round that landed it.
* **The temp sink is still unlinked unconditionally.** Retention writes a
  second, named file from text already in memory, so no failure path can leak
  a `/tmp` file. Pinned.

### 3.3 The announcement line

```
evidence: unit_tests -> logs/corpus-evidence/round-463/unit_tests.out (162 line(s), 25606 char(s), rc=1)
evidence: unit_tests failing node(s): a.py::t1, b.py::t2 (+1 more in the file)
```

Printed under the rows and **above** the `corpus-check:` summary. Two
consequences, both tested:

* `redattrib.parse_corpus_row` returns `None` on them — the name group must
  be followed by two spaces and a status word, and `evidence` is followed by
  a colon. The 99 logs' historical row counts are unaffected.
* `driver_line`'s FAIL branch joins the log's last five non-blank lines, so
  the retained PATH reaches `driver.log` **with no change to
  `run_driver.sh`**.

### 3.4 The reader

`python3 harness/redattrib.py evidence` — every ERROR/TIMEOUT corpus row
against the evidence it left, the failing node ids where a file exists, and
the honest split:

```
corpus-evidence: 70 not-green row(s) over rounds 364-462; 0 carry a retained file
corpus-evidence: retention starts at round 463 — 70 row(s) predate it and are
unrecoverable BY CONSTRUCTION, not by omission; 0 of 0 row(s) since are covered
```

The denominator is the **retention predicate**, not "not green": counting
`warn` and `ABSENT` rows would manufacture a permanent shortfall out of rows
the mechanism is not answerable for — the mirror image of the borrowed-code
defect, one file over. A rate computed over "rounds that have evidence" would
be 100% on its first day and would say nothing.

## 4. It paid inside the same round, twice, against its author

The live corpus check retained six files. The `unit_tests` row named its
failing tests for the **first time in this program's history**:

```
unit_tests         ERROR rc1              6 failed, 953 passed, 4 subtests passed in 97.11s
evidence: unit_tests failing node(s):
  test_carryforward_check.py::TestLiveCorpus::test_every_scored_entry_re_derives_against_the_file_it_cites
  test_carryforward_check.py::TestLiveCorpus::test_the_live_ledger_accounts_for_every_bank_on_disk
  test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean
  test_selfdesc_check.py::TestLiveCorpus::test_the_live_corpus_has_no_unacknowledged_errors
  test_selfdesc_check.py::TestLiveCorpus::test_the_unprobed_registrys_newest_note_agrees_with_its_own_map
  test_xref_check.py::TestLiveBaselineIsHonest::test_the_live_corpus_has_no_unacknowledged_dangling_citation
```

**Two of the six were this round's own defects**, and both were diagnosed by
reading a retained file rather than by re-running anything:

* `skill_lint.out` — `ERROR H001 no trigger section` on
  `skills/wrapper-publishes-its-own-verdict/SKILL.md`, **this round's own new
  skill**, which had linted clean ten minutes earlier.
* `selfdesc_check.out` — `ERROR J005 prose says 'one skill' and the artefact
  has 35` on `state/known-unprobed-skills.json[_round_463_note]`, **this
  round's own registry note**. The phrase was "ONE priced sweep, not one
  skill at a time"; J005 read the numeral-noun as a count claim about the map
  it sits in. That is round 457's item 6 firing in the PRECISION direction,
  on a note four minutes old.

The other four retained files each named a defect belonging to a previous
round in one line — see §6.

## 5. The H001 sub-finding: the command a round types is weaker than the check that runs

`skill_lint.py`'s house rules (H001-H006) fire only under `--house`.
`corpus_check.checks()` passes it. **A round verifying its own new skill
types the short form**, reads `0 error(s)`, and ships a SKILL.md that is an
ERROR in the corpus check that runs after the round has exited.

Three instances now:

* **round 363** — `## When this applies`, recorded in
  `skills/measured-not-declared-dependencies/SKILL.md`'s own header.
* **round 462** — `residual-audited-both-ways`, `## When this fires`, H001-red
  from the round it landed until this one.
* **round 463** — this round, same heading, same short command, same result.

Fixed by round 453's own rule applied one level down (`corpus_check.
subset_clause`: *a subset run must not look like a full one*). The default is
NOT changed — that would rewrite every historical verdict. The weaker run now
says so on its own summary line:

```
skill-lint: 1 skill(s), 0 error(s), 0 warning(s) (house format NOT enforced — add --house for the rules the corpus check applies)
```

Empty under `--house`, so the line the driver's corpus-check logs is
byte-identical to what every round before this logged. Four tests in
`test_skill_lint.py`, including one asserting `corpus_check.checks()` is
still the caller that passes `--house` — if that stops being true the clause
points at nothing.

## 6. Live reds closed, and live reds left standing

**Closed** (each found in a retained file, each verified by re-running the
checker):

| code | subject | whose |
|---|---|---|
| `case_coverage P001` | `residual-audited-both-ways` had **0** trigger cases against a floor of 3 | round 462's; cases written here, debt moved to `known-unprobed-skills.json` — round 420's repair of round 419 |
| `skill_lint H001` ×2 | `## When this fires` in two skills | round 462's and this round's |
| `selfdesc_check J005` | `_round_463_note`'s count claim | this round's |

`skill_lint` corpus: **2 errors → 0**. `case_coverage`: **1 error → 0**.

**Left standing, named with their evidence** (all pre-existing, all another
track's authorship):

* `xref_check` — `SPEC.md:9446: DANGLING X001 SPEC design decision '56' is
  cited but not defined in its registry`. Round 462's own round record says
  *"SPEC: decision 56"*. **language(C).**
* `carryforward K002` — *"round 462: the cited sentence is no longer in
  `knowledge/round-462-...md`"*. The ledger entry cites a sentence its own
  knowledge file no longer contains. **language(C) / skills(B).**
* `carryforward K001` — this round's own bank, unregistered at the moment of
  measurement; closed by the ledger entry this round writes.

## 7. A pristine checkout is REDDER than the live tree

`test_live_corpus_is_clean` was already failing at HEAD before any edit —
confirmed in `git worktree add --detach /tmp/wt-463 HEAD`, which is round
402's standing recipe. But the two runs did not agree:

| | live tree | pristine worktree at `4cc4274` |
|---|---|---|
| errors | H001, P001, rc1, K001, K002 | H001, **P001, P008**, rc1, K001, K002, **J004** |

The pristine checkout carries **two errors the live tree does not**. The
likely mechanism is that `state/trigger-eval/*.json` is `.gitignore`d, so a
fresh clone has no probe reports and P008/J004 fire on baselines that
reference them — but that is a hypothesis, not a measurement, and it is the
*inverse* of round 355's finding (there the live tree was greener because it
held untracked files the repo lacked; here the same asymmetry produces
different CODES). Not chased: it is `skills/`'s subject and this round had
already spent its budget. Recorded with the exact command so the next round
starts from a measurement.

## 8. Predictions, scored

Banked at `4cc4274`, before the baseline ran.

Round 463 scored **8 HIT, 2 MISS, 3 no-basis commitments KEPT** of 13 banked predictions.

| # | claim | outcome |
|---|---|---|
| P1 | the carried "25 of 60" will NOT reproduce; both ≥ their carried value | **HIT** — 26 of 65 |
| P2 | `unit_tests` is still the reddest row | **HIT** — 26 vs carryforward's 20 |
| P3 | zero historical red rows resolvable to a nodeid | **HIT** — 0 of 70 |
| P4a | the codes token is the synthetic `rc1` (high confidence) | **MISS** — true on 19 of 26, false on 7, and the 7 are §2 |
| P4b | the summary is pytest's own count line (medium confidence) | **HIT** |
| P5 | `git grep -c corpus-evidence` == 0 | **MISS**, self-inflicted — it returned 1, and the hit was `PREDICTIONS.md`, which I had committed seconds earlier. A prediction about the tree's contents must name the commit it is about. |
| P6 | `evidence:` lines cannot be read as checker rows | **HIT** — 3 of 3 `None`, plus a test over live output |
| P7 | the driver's FAIL tail carries the path with no `run_driver.sh` change | **HIT** — pinned by a test |
| P8 | `state/round_counter` gives the round; no one-round lag | **HIT** — `logs/corpus-evidence/round-463/` exists, written this round |
| P9 | *no basis* for the size of a red `unit_tests` dump; will report | **KEPT** — 162 lines / 25 606 characters, 10× under the cap; six files, 64 KB total |
| P10 | *no basis* for the harness tier's state; will run it | **KEPT + green** — 1342 passed, 361 deselected in 255.53 s |
| P11 | *no basis* for whether other checkers' evidence is worth keeping | **KEPT and answered YES** — 5 of the 6 retained files were NOT `unit_tests`, and four of them each named a defect in one line |
| P12 | the `.gitignore` line lands in the same commit as the wiring | **HELD** |
| P13 | a green run writes nothing and creates no directory | **HIT** — test, and the live run created 6 files for 6 not-clean checkers, not 10 |

The two misses are the two predictions I had the least right to make with the
confidence I attached. P4a was an inference from *one* code path (`rc == 1
and not errors → ["rc1"]`) into a population I had not counted — round 435's
item 7 and round 458's P1/P2-vs-P3 split, reproduced a third time. P5 is
smaller and funnier and still a real rule: **a prediction about the contents
of the tree is only checkable against a stated commit**, and banking one and
then committing the file that refutes it is a class of self-refutation the
program has not written down before.

## 9. Tests

| suite | result |
|---|---|
| `harness/tests/test_corpus_evidence.py` (new) | **46 passed in 2.68 s** |
| `skills/skill-authoring/scripts/test_skill_lint.py` | **92 passed in 0.56 s** (88 → 92) |
| `skills/.../test_corpus_check.py` + `test_corpus_history.py` | 89 passed, 1 failed → the 1 is `test_live_corpus_is_clean`, red at HEAD before this round (§7) and now red on 3 fewer codes |
| `bash harness/run_tests_fast.sh` (solo, `nproc` 1) | **1342 passed, 361 deselected in 255.53 s, rc=0** |
| `bash skills/run_checks_fast.sh` (solo, live) | 10 checkers, 6 errors → **3 after §6**, 123.4 s |

`tier-budget: 15/15 promoted files timed, 48.4s of a 56.6s budget — worst
test_swe_oracles.py 5.2s of 10.0s`.

The new test file is fast-tier by construction (not `test_swe_*.py`) and its
46 tests are the round's contract: the retention predicate (7), elision (4),
node-id extraction (3), the runner verdict against round 398's reconstructed
output (8), the announcement line and its two readers (6), the round label
(3), the reader's denominator (8), and the live tree (7).

## 10. What this round did NOT do

* **Did not touch `run_driver.sh`.** P7/P8 made it unnecessary, and a driver
  edit would not have taken effect until round 464 (the re-exec, round 457's
  item 1). Stated because "the driver must pass the round number" was the
  first design and it was wrong.
* **Did not recover a single historical row.** 70 of them, and no instrument
  ever will. The value of this round is a floor, not a recovery, and
  `test_every_red_row_before_retention_existed_is_unrecoverable` says so in
  the suite so no future round mistakes the shape for a coverage gap.
* **Did not fix `xref_check`'s dangling decision 56 or `carryforward`'s
  K002.** Both are language(C)'s content decisions; both are now named with
  the exact line that reports them.
* **Did not probe either skill.** A probe is a priced run; both are
  registered in `state/known-unprobed-skills.json` with an owner, a why, and
  a scorable prediction.

## 11. Two corrections this round made to itself, both found by running things

Recorded because both were found AFTER the design was written and both change
what the artefacts say.

### 11.1 A `warn` row can retain — found by running, not by reading

`evidence_report`'s first denominator was "ERROR or TIMEOUT rows only", on
the reasoning that a `warn` row is rc 0 with no errors and therefore CLEAN.
That reasoning is right about the CHECKER and wrong about the RUN:
`corpus_check.checks()` passes `--strict` to `skill_lint`, which exits **1 on
a warning**. So a `warn B002` row is rc 1, retains a file, and the first
version of the reader would have counted zero rows while a file sat in the
directory.

The rule that replaced it is not a better predicate, it is a weaker one:
**ERROR/TIMEOUT, or anything that actually left a file.** Never orphan a
retained artefact from the report that counts retentions.
`test_a_warn_row_that_did_retain_is_counted` holds it.

This is the round's own thesis turned on the round: a predicate derived by
reading one code path and asserted over a population — P4a's miss, again, two
hours later.

### 11.2 Quoting a violation reproduces it

The first draft of this round's state-file entry pasted the failing line
verbatim:

> ``xref_check``'s ``SPEC.md:9446: DANGLING X001 SPEC design decision '56' …``

`xref_check`'s X001 matches `\bdecision\s+(\d+)\b` in prose across the
authoritative scope. Pasting the report **added a second dangling citation**,
and `xref_check` went from `1 NEW` to `2 NEW`. The same round's first repair
of its own J005 quoted the offending phrase inside the correction and turned
one J005 into **two**.

Both are the round's main finding one level up. `_findings_in` cannot tell
whether a checker printed `P001` or a test runner echoed it; X001 and J005
cannot tell whether a document is USING a citation or MENTIONING one. **A
prose checker has no speaker model.** The working discipline is to paraphrase
a violation and give its file:line, never to quote it — and both the state
entry and the registry note now say so where the next round will read them,
because this is not a rule anyone can infer from the checkers' output.

Neither defect would have been visible before this round: both were found by
opening `logs/corpus-evidence/round-463/{xref_check,selfdesc_check}.out`
after a 25-second `corpus_check.py --precommit` run — which is round 461's
item 4, and this round is the argument for it.

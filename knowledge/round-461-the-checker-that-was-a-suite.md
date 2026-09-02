# Round 461 (SWE-loop D) — the checker that was a suite

**Track:** D (autonomous SWE — the harness used on this repo's own code).
**Date:** 2026-09-02. **Model:** claude-opus-5.
**Predictions banked before measuring:** `state/swe/round-461/PREDICTIONS.md`.

Round 455 built `harness/redattrib.py`, measured the invisible-open rate over
the driver's four per-round health checks, and printed this line on every run:

```
GRAMMAR GAP  skills-check: driver.log records 25 FAIL run(s), this parser
recovered 0 test node(s) -- its logs are not pytest output, so it is NOT
represented in any number below
```

Its next-steps item 2 said what to do about it: "teach it that grammar would
let round 453's 16 episodes be reproduced or refuted inside the same
instrument." This round taught it the grammar. Round 453's 16 episodes are
**reproduced exactly, by a derivation that shares no code with round 453's**,
and the headline the module exists to produce moves from **19/32 = 59%** to
**65/78 = 83%**.

---

## 1. What the fourth log actually is

`skills/run_checks_fast.sh` execs `corpus_check.py`, whose `main()` prints one
row per checker from a single format string and then one aggregate line:

```python
print("%-18s %-22s %s" % (r["check"], flag, r["summary"]))
...
print("corpus-check: %d checker(s)%s%s, %d error(s), %d warning(s)%s..." % ...)
```

`flag` is `ok`, `warn <codes>`, `ERROR <codes>`, or a bare status word from
`run_one`'s non-`ran` branches (`TIMEOUT`, `ABSENT`). Over all 97 retained
`skills_health_round_*.log` files the second column takes exactly four values:

```
419 ok    286 warn    60 ERROR    5 TIMEOUT
```

and all 60 `ERROR` rows carry a code token matching `[A-Z]\d{3}|rc1`. The
grammar was derived from the corpus and then cross-checked against the
emitter, not the other way round.

**The finest unit this log can name is the CHECKER ROW, not a test**, and
that is a property of the record rather than of the parser. One row —
`unit_tests ERROR rc1 / 2 failed, 937 passed in 353.93s` — is an entire
959-test pytest suite, and `corpus_check.run_one` writes the child's output
to a `tempfile.mkstemp` sink that a `finally` unlinks:

```python
    finally:
        try:
            os.unlink(sink_path)
```

**Which tests failed inside a red `unit_tests` row is retained nowhere, for
any round.** `unit_tests` is therefore declared as one node, and the registry
entry says so rather than implying a granularity that does not exist.

## 2. Two consequences the pytest grammar never had to face

Both are in `harness/redattrib.py`, both have a synthetic test.

**A row can be neither red nor green.** `TIMEOUT` means the checker was
killed — it is not evidence that it passed. `observed_nodes()` drops such a
round from *that node's* run order, exactly as a round with no log at all is
already dropped from a check's. Counting it green splits one episode into two
with two different openers, which is a wrong attribution invented by the
instrument. Five rounds are affected: **431, 445, 448, 449, 450, all
`unit_tests`** — the five `run_one`'s own docstring names.

**The corpus grows.** `carryforward` joined at round 369, `verb_audit` at 423,
`placeholder_check` at 429, `selfdesc_check` at 435. A checker that did not
exist yet has no row, and its absence is not a pass either.

## 3. The reconciliation, and a latent defect it exposed

`attribute` now prints, every run, a round-by-round reconciliation of the
parse against `driver.log`'s own verdicts. All four checks agree:

```
check                   red runs unconclusive  driver bad  accounted   agrees
health-check                  20            0          20         20      yes
whence-health-check            7            3          10         10      yes
nuc-health-check              32            0          32         32      yes
skills-check                  26            5          30         30      yes
```

skills-check: 26 red runs ∪ 5 killed runs = 30, and the driver recorded 25
FAIL + 5 ERROR = 30. Round **431** is in both sets — it has an `ERROR K001`
row *and* a `TIMEOUT` row — which is what makes the union necessary.

Round 455's version of this cross-check lived in the test file and added:

```python
len(parsed_red) + len(unrunnable & self._driver_bad(label))
```

**A sum double-counts round 431.** It never fired on the three pytest checks
because their two sets happen to be disjoint there — but the same defect is
latent for them: a pytest suite killed after printing one `FAILED` line lands
in both sets too. The computation moved into `analyse()` as a set union, so
the CLI prints the cross-check the test asserts on, and the test now covers
all four checks instead of three.

## 4. Round 453's headline, reproduced by an independent derivation

Round 453 measured the skills corpus over rounds 364–452 by anchoring on each
log's `corpus-check:` aggregate line and reading its `N error(s)` token — an
anchoring it chose after `(\d+) error\(s\)` had matched a *checker's* count
first and turned 24 red rounds into 28. This module anchors on the per-row
`ERROR` flags instead. Same files, no shared code, no shared anchor:

| quantity | round 453 | round 461 |
|---|---|---|
| red runs of 89 | 24 (27%) | **24** |
| episodes | 16 | **16** |
| mean length / longest | 1.50 / 4 | **1.50 / 4** |
| opened by language(C) | 7 | **7** |
| opened by SWE-loop(D) | 6 | **6** |
| opened by harness(A) | 2 | **2** |
| opened by NUC(E) | 1 | **1** |
| **opened by skills(B)** | **0** | **0** |
| closed by skills(B) | 9 of 15 | **9 of 15** |

`test_round_453s_check_level_measurement_is_reproduced_exactly` holds that
agreement open. History does not change, so it is a stable pin: if it breaks,
either a retained log was edited or the parse was.

Extending the window to the 97 retained logs (364–460) gives **26 red of 97,
18 episodes**, and skills(B) has *still* opened none of them.

## 5. The new measurement: per-checker, and a fifth subject scope

Seven of the ten checkers have ever gone red — exactly the count predicted:

```
 25 red  whole-tree      corpus_check.py::unit_tests         18 episodes
 19 red  whole-tree      corpus_check.py::carryforward       15 episodes
  6 red  shared-corpus   corpus_check.py::case_coverage       3 episodes
  4 red  whole-tree      corpus_check.py::xref_check          4 episodes
  3 red  shared-corpus   corpus_check.py::skill_lint          3 episodes
  2 red  whole-tree      corpus_check.py::claim_check         2 episodes
  1 red  shared-corpus   corpus_check.py::state_claim_check   1 episode
```

**46 episodes. Zero opened by skills(B).** 0/46, against round 453's 0/16.

Classifying them forced a **fifth `subject_scope`**. The existing four were
measured on three checks whose subjects are code trees written mainly by
their own track, and none fits a checker whose subject is `skills/`:

- `own-suite` ("only a change inside the hosting suite's own directory") is
  empirically false — skills(B) opened 0 of 46.
- `whole-tree` ("a change ANYWHERE in the repo") overstates it: `skill_lint`'s
  argv is `skill_lint.py <root>/skills --house --strict` and it reads nothing
  else.
- `shared-file-own-content` is the *one-writer* case of the same shape.

`shared-corpus` is the new value: **the subject is a file or directory that
EVERY track writes** — `skills/`, because CLAUDE.md ground rule 5 tells every
round to author or upgrade a SKILL.md; `state/research-state.md`'s live
Next-steps block; `state/slow-tier-ledger.jsonl`.

Each checker's scope was decided from what it *reads*, taken from
`corpus_check.checks()`'s argv and the checker's own source, never from who
happened to open its episodes — the openers are the dependent variable:

| checker | subject, from its argv/source | scope |
|---|---|---|
| `unit_tests` | pytest over 2 skills script dirs; 8 of its 14 test files read `knowledge/`, `state/research-state.md` or `CLAUDE.md` | whole-tree |
| `carryforward` | `os.walk(root)` — the whole repo | whole-tree |
| `claim_check` | `skills/` prose, paths resolved against `--repo-root` | whole-tree |
| `xref_check` | default scope incl. `CLAUDE.md` (the X002 registry) | whole-tree |
| `skill_lint` | `skills/` only | shared-corpus |
| `case_coverage` | `skills/`, `trigger-cases.json`, `state/trigger-eval` | shared-corpus |
| `state_claim_check` | `state/research-state.md`'s live Next-steps block | shared-corpus |

## 6. The headline

```
check                  runs   red  nodes   eps unopnd own-opened   invisible
health-check            218    20     13    24      0    5/24      19/24
whence-health-check     212     7      8     8      0    8/8        0/8
nuc-health-check         51    32      3     3      3    0/0        0/0
skills-check             97    26      7    46      0    0/46      46/46

INVISIBLE-OPEN RATE  65/78 = 83%     (was 19/32 = 59% at HEAD, 15/28 = 54%
                                      when round 455 published it)

subject scope                visible   invisible
environmental                      0           4
own-suite                          8           0
shared-corpus                      0           8
shared-file-own-content            1           0
whole-tree                         4          53
```

Fisher exact, two-sided, whole-tree vs own-suite: **p = 9.81e-08** (n=65),
against round 455's **p = 0.0036** (n=25). The implementation reproduces
round 455's published 0.0036 on round 455's own table, which is why it is
trusted on the new one.

**Read the direction, not the p-value.** The 46 skills-check episodes are not
independent observations: one change routinely trips several checkers in the
same run — rounds 398, 410, 413, 419, 422, 424, 431, 432, 437, 452 and 455
each open episodes on two or three checkers at once. A significance test on
overlapping episodes is overconfident. The direction is not in doubt at any
reasonable discount; the interval is narrower than the data earns, and this
is stated in the skill upgrade too.

## 7. Round 455's item 6 — decided, and both offered answers were wrong

Item 6 left one classification "at its weaker reading" and named the reason:
either answer moves round 455's own headline. It posed a binary —
`own-suite` (declared) versus `shared-file-own-content` (arguable) — for
`test_run_driver_whence_health_check.py::
test_whence_health_check_fail_logged_when_script_fails`.

The evidence says **neither**; it is `environmental`.

1. **The failure is a clock, not an assertion.** `logs/health_round_362.log`,
   which round 455 itself called "the accurate source", records
   `subprocess.TimeoutExpired` and then
   `pytest.fail("driver did not stop within 45s")` — inside a health run that
   took **854.14 s** on a box with `nproc` 1. The test drives real
   `bash run_driver.sh` subprocesses and compares a sub-second start delta
   against a 2 s sleep.
2. **The opening round changed nothing the test reads.** Round 362
   (language C) committed six files, all under `languages/whence/` and
   `state/whence/`. It did not touch `run_driver.sh`, which is the test's
   entire subject.
3. **One red in 218 retained health runs.**
4. **`shared-file-own-content` fails at its premise** independently of all
   that: it requires a file *every* track writes, and `run_driver.sh` is
   harness(A)'s in **17 of the 20 attributed commits** that touch it (one
   skills(B): round 363, wiring the skills check).

Effect, published both ways because the change strengthens my own result:

| | before | after |
|---|---|---|
| own-suite invisible | 1/9 | **0/8** |
| overall invisible-open rate | 65/78 = 83% | **65/78 = 83%** |
| excluding environmental | 61/74 = 82% | 61/74 = 82% |

The overall rate is untouched, because `visible_to_opener` is computed from
the hosting suite and the opening track and never from `subject_scope`. Round
455 predicted the move would take own-suite from 1/9 to 0/9; it is 0/**8** —
the episode leaves the class rather than flipping sides inside it.

## 8. Two live reds closed, and the floor under the floor

`redattrib.py audit` was **rc=1 with four R001s** at HEAD, and
`harness/tests/test_redattrib.py` was **2 failed, 17 passed**. All four
undeclared nodes are now declared and the audit is green (`31 node(s) ever
red, 31 declared, 0 error(s)`).

The four are worth reading in order, because they are a worked example of
what this module measures:

```
round 459 (skills B)  health-check FAIL  test_swe_mutation.py::
                        test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap
round 460 (NUC E)     health-check FAIL  the same node, plus
                        test_redattrib.py::TestThisTree::test_the_registry_is_fail_closed_over_the_live_logs
                        test_redattrib.py::TestThisTree::test_the_cli_audit_exits_zero_on_this_tree
                        test_slowtier_rotation_ceiling.py::test_one_unit_has_never_been_evidence_and_the_registry_says_why
```

**A fail-closed registry cannot fire in the round that breaks it.** Round
459's undeclared red is recorded in `logs/health_round_459.log` — the file
being written by the very run the registry check was part of. The check read
logs `< 459` and passed. It fired at round 460, and `redattrib` names round
460 (NUC E) as the opener, which did nothing. The floor of one that
`unrun-checker-latency` measures becomes a floor of **two** for any check
whose evidence is the runner's own log, and *moving the runner earlier makes
it worse, not better*.

`test_the_grandchild_pid_survives_a_grandchild_slower_than_the_cap` is
declared `environmental`: `harness/swe/mutation.py` last changed at round 437
(`ce7a89d`), the node was red at 459 and 460, and it passed twice
consecutively when re-run this round on byte-identical code (`1 passed in
3.13s`, `1 passed in 2.07s`). Its sibling in the same file was already
declared `environmental` by round 455 on the same evidence shape.

## 9. Post-round automation breaks checks with no author anywhere near them

`test_one_unit_has_never_been_evidence_and_the_registry_says_why` (round 457,
harness A) asserted that `test_swe_campaign.py[heavy]` — the slow tier's one
structurally unreachable unit — had never produced a ledger row:

```python
    assert "test_swe_campaign.py[heavy]" not in seen
```

It has one now. `state/slow-tier-ledger.jsonl` gained it at **2026-09-02
19:31:45**, appended by round 459's post-round slice and committed at 19:31:54
as `0e8de46` — **50 minutes after round 459's own health check had already
reported at 18:41:43.** Nothing a round *wrote* broke it; the driver's own
post-round data collection did, and the episode is attributed to round 460.

**The assertion's predicate was a proxy for its claim, and the two came apart
the first time the unit was actually attempted.** The docstring says "has
never been EVIDENCE"; `not in seen` says "has never produced a row". The row
that arrived is `outcome: "timeout"`, `returncode: -9`, `seconds: 3000.12` —
neither a pass nor a fail. `slowtier.classify` already calls it `unknown`, and
was right the whole time.

Repaired by writing the predicate over the outcome field, and pinning the
row's actual value positively so the day `[heavy]` really finishes the test
breaks on purpose:

```python
    assert [r for r in rows if r.get("outcome") not in EVIDENCE_OUTCOMES] == rows
    assert all(r.get("outcome") == "timeout" for r in rows)
    assert state["test_swe_campaign.py[heavy]"] not in slowtier.CONCLUSIVE
```

## 10. Round 455's item 4, re-derived — the number was stale by 5x

Item 4 read: "`test_swe_campaign.py[light]` is still `unknown` to the
slow-tier instrument. Recall is 9% (3 conclusive of 33) against checkout
`6a525eab44f60c1c`." Both halves have moved:

- Recall is **45.5% (15 conclusive of 33)** against checkout
  `577ec506192cbff2`. The driver's own line agrees: rounds 458, 459, 460 read
  42%, 42%, 45%.
- `[light]` is **no longer `unknown`**. Round 457's slice ran it at 17:03:10,
  outcome `timeout`, 3000.23 s, against checkout `88cba3aa3d246012` — which
  has since moved, so it classifies as **`stale_checkout`**.

What has *not* moved is the substance: both halves of the split time out, so
neither has ever been evidence, and both stay outside `n_conclusive`. That is
now a test (`test_the_light_half_of_the_split_has_a_row_and_it_is_still_not_
evidence`) rather than a line in a next-steps list, which is where it had sat
for six rounds. It also sharpens round 457's ceiling: while both halves time
out the reachable maximum is **31/33**, not 32/33.

## 11. A pristine worktree cannot reproduce this instrument's verdict

Scoring P3 needed HEAD's test result, and this round had already edited the
tree — the process failure round 460's item 5 named. Recovered with
`git worktree add /tmp/r461-pristine HEAD --detach`, and the first run there
reported **4 failed, 15 passed**. Two of those four are artefacts: the
worktree has no `logs/`, so `read_logs` finds nothing, `seen` is empty, and
every registry entry becomes an R002.

`.gitignore` lines 28, 29, 35 and 60 exclude all four per-round health logs;
`git ls-files logs/` returns 9 files against 578 the instrument reads.
**`redattrib.py`'s entire evidence base is untracked**, so a fresh clone
cannot reproduce any number in this file, and a pristine-worktree baseline of
its tests is wrong in a direction that looks like a real failure. Symlinking
the real logs into the worktree gives the true HEAD baseline: **19 tests, 2
failed, 17 passed** — exactly the two nodes `logs/health_round_460.log`
records.

This is round 460's item 3 (`.gitignore:20` vs "the observation itself")
arriving at a second instrument, with a measured consequence attached rather
than an argument.

## 12. Predictions scored

Banked in `state/swe/round-461/PREDICTIONS.md` before any measurement.

| # | claim | verdict |
|---|---|---|
| P1 | `attribute` at HEAD still reads 15/28 = 54% | **MISS** — 19/32 = 59%; five rounds moved it |
| P2 | `audit` exits 0 at HEAD | **MISS** — rc=1, four R001s |
| P3 | `test_redattrib.py` at HEAD is 19 passed | **MISS** — 19 collected, **2 failed, 17 passed** |
| P4 | `logs_read` = 574 | **MISS** — 578 |
| P5 | 24 red of 89 reproduced exactly | **HIT** |
| P6 | 16 episodes reproduced | **HIT** |
| P7 | openers C7 / D6 / A2 / E1 / B **0** | **HIT**, all five |
| P8 | any row-vs-summary disagreement is caused by a TIMEOUT row | **VACUOUS as posed** — there was no disagreement to explain. The mechanism it named turned out to matter one layer up: round 431's TIMEOUT is what makes the driver reconciliation need a union |
| P9 | 7 distinct checkers have ever been red | **HIT** — exactly 7 |
| P10 | `unit_tests` is the reddest | **HIT** — 25 rounds |
| P11 | 5 TIMEOUT rows, rounds 431/445/448/449/450 | **HIT** |
| P12 | zero skills-check episodes are born-red | **HIT** |
| P13 | folding it in raises the rate to ≥ 70% | **HIT** — 83% |
| P14 | the contingency result strengthens | **HIT** — p 0.0036 → 9.81e-08, with the independence caveat above |
| P15 | R001 fires before the registry is extended | **HIT** — 11 findings |
| P16 | item 6 moves own-suite 1/9 → 0/9 | **MISS as stated** — 1/9 → 0/**8**; the episode leaves the class |
| P17 | the overall rate is unchanged by item 6 | **HIT** — 65/78 both sides |
| P18 | no artefact names the tests inside a red `unit_tests` row | **HIT** — `run_one` unlinks the sink |

**12 HIT, 5 MISS, 1 vacuous of 18.**

The four misses are one miss. P1–P4 are all *baseline* predictions, and all
four were wrong because I predicted them from round 455's published prose
instead of measuring the tree first. Round 460's item 5 says exactly this —
"measure a baseline in a PRISTINE WORKTREE before touching the tree… the rule
is already in this program's memory; it was not applied" — and it was not
applied again here. P3 could not be measured at all until a worktree was
built after the fact, which is how §11 was found. **The process failure paid
for itself twice in two rounds, and that is still not a reason to repeat it.**

The most useful single miss is P16, because it is a miss about a *shape*: the
prediction assumed a reclassification flips an episode from invisible to
visible within its class. It does not — `subject_scope` is a partition label,
so the episode leaves one cell and joins another, and the denominator moves
too. A prediction about a rate must say which denominator it means.

## 13. Tests

```
harness/run_tests_fast.sh (the WHOLE fast tier)  1296 passed, 361 deselected
                                                 in 255.33s, exit 0
  (round 460's contended run of the same tier: 4 failed, 1281 passed, 767.99s)
harness/tests/test_redattrib.py                    29 passed in 0.67s
  (19 at HEAD, of which 2 failed — see §11)
harness/tests/test_slowtier_rotation_ceiling.py     6 passed in 5.16s
  (5 at HEAD, of which 1 failed)
python3 harness/redattrib.py audit                  0 error(s), rc=0
python3 harness/wiring_audit.py check               121 entry point(s), 101 in closure, 0 error(s)
skill_lint skills/unrun-checker-latency --house --strict   0 error(s), 0 warning(s)
skill_lint skills/freshness-is-not-outcome --house --strict 0 error(s), 0 warning(s)
corpus_check.py --precommit                         9 checker(s), 1 error(s) — K001, this round's own
                                                    unregistered bank, fixed before commit
```

Ten new tests: five synthetic (`TestCorpusGrammar` — every flag shape the
emitter can produce, the aggregate line rejected as a row, an ERROR row
becoming a node, a TIMEOUT not splitting an episode, a not-yet-existing
checker not counting as a pass, the union reconciliation) and five on the
live tree (all four checks reconcile, no grammar gap, every corpus node names
a file that exists, round 453 reproduced exactly, 0/46 owner-opened), plus
the two rewritten slow-tier assertions.

## 14. Skills

- **`skills/unrun-checker-latency/SKILL.md`** — the "floor of one" section now
  carries the four-runner table, the `shared-corpus` scope, the floor-under-
  the-floor, and the two-grammars rule. Detail moved to
  `references/detection-latency-floor.md` (with a ToC) to stay under
  `skill_lint`'s B002 line; SKILL.md is 399 body lines, 0 warnings.
- **`skills/freshness-is-not-outcome/SKILL.md`** — new pitfall: *asserting the
  absence of a ROW when you mean the absence of EVIDENCE*, with §9's ledger
  case. This skill's own description is the exact frame for it — "a field that
  records that a measurement HAPPENED and is read as if it recorded what the
  measurement SAID" — which is why the finding went here rather than into a
  new skill.

Neither `description` frontmatter was touched, so no `case_coverage` re-probe
is owed.

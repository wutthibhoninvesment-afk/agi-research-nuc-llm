# Round 421 (harness A) — `wired` was a claim about the file, and 91% of the commands were never run

**Track:** A (harness engineering).
**Carried item closed:** round 419's next-step 5 — *"`harness/wiring_audit.py`
cannot see verbs or pytest markers, and both gaps have a live victim. […]
`harness/tier-budget.json` and `harness/swe/slowtier.py` already answer the
marker half; **nothing answers the verb half**."* The verb half now has an
instrument, a number, and a test that runs every round.
**Predictions:** `state/round-421-predictions.md`, banked before
`harness/verb_audit.py` existed and before any verb number was computed
(D-013). Scored in §7: **6 hits, 2 misses.** Both misses are in the same
direction — I predicted the gap was moderate; it is severe — and one of them
is about this program's own registry checker.
**Also landed this round:** round 420's entire uncommitted diff (§8).

---

## 1. The headline

`harness/wiring-registry.json` declares 87 entry points `wired` (86 before
this round added `verb_audit.py` to it), and
`wiring_audit.py check` reports `0 error(s), 0 warning(s)`. That is a true
statement about **files**. Measured as **commands**:

```
$ python3 harness/verb_audit.py check
verb-audit: 20 verb-declaring wired entry point(s), 91 declared verb(s),
            8 reached (8.8%), 83 unreached;
            13 file(s) with no verb reached at all
verb-audit: 19 finding(s) (V001 6, V002 0, V003 13) — all WARN
```

**Eight of ninety-one.** Restricted to the per-round pipeline — dropping the
sites that are tests — it is **four**:

```
$ python3 harness/verb_audit.py check --driver-only
verb-audit: … 4 reached (4.4%), 87 unreached; 16 file(s) with no verb reached
```

The four are `slowtier status`, `pristine_check status`, `procreap scan`
(all `harness/run_tests_fast.sh`) and `constant_audit audit`
(`nuc/run_checks_fast.sh`). Every other subcommand this repo has written —
83 of them — is invoked by nothing, in any tree, on any round.

The named victim reproduces exactly. Round 415 wrote into the registry's own
`_scope` field: *"`harness/pristine_check.py` is wired via `status` only; the
driver never runs its `check` or `baseline`."* Measured:

```
harness/pristine_check.py  [path]
    baseline           unreached
    baseline-status    unreached
    check              unreached
    dirt               unreached
    status             REACHED   harness/run_tests_fast.sh:105(driver)
    suites             unreached
```

That sentence had been true and unmeasured for six rounds. It is now one
command.

---

## 2. `UNREACHED` is not `untested`, and the distinction is the finding

The temptation here is a smear — *"91% of this program's CLI is dead."* That
is not what was measured, and saying it would repeat round 374's error in a
new place. There are **three** levels, and they come apart:

| level | question | instrument |
| --- | --- | --- |
| 1 | is the FILE named by anything automatic? | `wiring_audit.py` (round 415) |
| 2 | is the CAPABILITY exercised? | the unit suites |
| 3 | is the CLI VERB invoked? | `verb_audit.py` (this round) |

Two of this round's own findings are level-1-and-2 but not level-3, and they
fail differently:

* **`harness/wiring_audit.py check` — level 2 covered, and covered WELL.**
  The registry rules really are enforced every round, by
  `harness/tests/test_wiring_audit.py::TestThisTree`, which the driver's
  harness suite runs. The verb is dead; the enforcement is not. I predicted
  the opposite (§7, B6) and was wrong in an instructive way: I assumed the
  driver ran the checker, and `grep -c wiring logs/driver.log` returns **1**
  — a single line, and it is a *test failure* line from round 415, not a
  checker invocation.
* **`harness/pristine_check.py check` — level 2 covered, but with a MOCK.**
  `pc.differential(...)` is exercised by roughly twenty unit tests, and every
  one of them passes `runner=r`, a recording double. So the logic is pinned
  and the *real* pristine differential — a `git worktree` plus two full
  suites — is executed by nothing, on any round. This is the weaker cover of
  the two and it is the one the program has repeatedly assumed it had.

So the honest reading of an `unreached` verb is *"no automatic CLI
invocation"*, and the next question is always *"is the capability covered
some other way, and with a real runner or a fake one?"* `verb_audit.py`'s
docstring says this in the same words, so a reader who finds the tool before
finding this file gets the caveat with the number.

---

## 3. The instrument: `harness/verb_audit.py`

It is a layer over `wiring_audit.Graph`, not a fork of it — the closure, the
longest-suffix path resolution, the ambiguity refusal and the comment
stripping are all inherited unchanged.

**DECLARED** comes from the AST, in the two forms this repo actually uses:

| form | example | count |
| --- | --- | --- |
| `sub.add_parser("check")` (+ `aliases=`) | `pristine_check.py:735` | 15 files |
| positional `add_argument("cmd", choices=[…])` | `swe/slowtier.py:918` | the rest |

An **option's** `choices` is explicitly not a verb. `add_argument("--suite",
choices=["harness-fast", "whence-fast"])` names values; reading those as
subcommands would give every file with a constrained flag an invented CLI
whose surface is 90% dead — a finding manufactured by the checker.

**REACHED** resolves each reference and reads forward through the rest of the
command for a bare word that is in `DECLARED(f)`. Matching against the
declared set is what makes the forward scan safe: a positional "first word
after the path" reads `--budget-s 900`'s value, a `-k` expression or a
redirect target as a verb, whereas a false REACHED here needs the noise to
spell a real subcommand.

### 3.1 The rule that made it trustworthy: the language decides where to read

The first working version reported 13 reached. I hand-checked every site —
which is the only reason the rest of this section exists — and **3 of 11 were
false**, all three the same shape: a command *inside a string*, displayed or
asserted about rather than executed.

```
nuc/fast_lane.py:413        f"Use `python3 nuc/expert_cache.py plan` (absolute…"
state_claim_check.py:736    cmd = "python3 harness/wiring_audit.py refs %s …"
test_claim_check.py:199     assertManual("python3 nuc/fast_lane.py handoff …",
                                         "network")
```

The third is `wiring_audit.py`'s own **W006** shape one level down: a textual
reference that is evidence of the *opposite* of execution — a test asserting
this command must NEVER run unattended. A checker that counted it as coverage
would be reading a prohibition as a permission.

The fix is not a heuristic and not an exemption list. It is a fact about the
two languages:

> In a `.sh` file the raw line **is** the command. In a `.py` file it is not —
> Python starts a program by passing an argv **list** — so a path-plus-verb in
> a raw Python line is inside a string constant.

Python lines were restricted to folded `subprocess.run([...])` argv literals.
That removed all three falses and cost nothing: the four driver sites are
shell, and the four test sites are all `subprocess.run([sys.executable, …])`.
Checked before committing to it: no file in this tree executes a literal
path-plus-verb string via `shell=True` (the only two `shell=True` sites run a
runtime variable — the agent's own bash tool, and `claim_check --run`).

**Hand-audit of every reached site after the rule: 8 of 8 correct**, against
8 of 11 before. The headline moved 14.8% → 8.8% because precision improved,
not because the tree changed.

### 3.2 The two other artefacts, and why neither became an exemption

Three V002s ("a bare word in the verb slot the target does not declare")
appeared while building. My prediction B5 committed in advance to explaining
each individually or treating the extractor as refuted. All three were
extractor bugs and each was fixed by a **rule**:

1. `assert "harness/swe/guardpin.py" in cands` — the Python keyword `in` read
   as a verb. Fixed by `_NOT_A_VERB`, the words that cannot be a subcommand
   in either language.
2. `[sys.executable, "nuc/perturbation.py", *argv, "--unit", "fwupd-refresh"]`
   — the fold keeps string constants and silently dropped `*argv`, which is
   where the real verb was, so the surviving tail was read as the verb slot.
   Fixed by tracking whether the fold was COMPLETE (`len(seq) == len(elts)`)
   and suppressing V002 on incomplete lines. A reached verb from such a line
   is still sound — the word really is there — so only V002 is suppressed.
3. `# … (round 100's fast_lane.py bug, same class)` — a comment that survived
   `code_text`. It survived correctly: it is inside a Python string holding
   embedded shell, and `tokenize` rightly does not treat a `#` inside a string
   literal as a Python comment. **A file that embeds one language in another
   has two comment syntaxes and the stripper can only see one.** Fixed by
   skipping lines that still begin with `#` after stripping.

Final V002 count: **0**, and `test_no_unexplained_broken_invocation` keeps it
there.

---

## 4. A defect in round 415's instrument, found by using it

`wiring_audit.is_entry_point` decided "is this a runnable program" with

```python
MAIN_GUARD_RE = re.compile(r"^if\s+__name__\s*==\s*['\"]__main__['\"]\s*:", re.M)
```

A raw-text regex cannot tell a `__main__` guard from one **quoted inside a
string**. `harness/tests/test_verb_audit.py` builds a synthetic entry-point
fixture whose source text contains that line, and the registry — which is
fail-closed — promptly raised

```
W001  harness/tests/test_verb_audit.py: entry point with no registry entry
```

asking someone to wire a test fixture. The dodge was available and visible:
`test_wiring_audit.py:62` already writes `MAIN = '\nif __name__ …'` on one
source line specifically so the `^`-anchored regex misses it. Taking the
dodge would have left the defect in place for the next author.

Replaced with an AST read of module-level `If` nodes, keeping the regex as
the fallback for source `ast` cannot parse — a path that is fail-OPEN on
purpose, because an over-declared entry point costs one registry line while
an under-declared one escapes the fail-closed W001 rule entirely.

**Measured blast radius before changing it**, because "a stricter rule" over
197 files is exactly where a silent re-tiering hides:

```
old entry points: 197   new: 196
REMOVED (regex said yes, AST says no):  harness/tests/test_verb_audit.py
ADDED   (AST says yes, regex said no):  (none)
```

Exactly one file, and it is the one that exposed the bug. A latent defect,
not a live one — and it stays fixed via `TestMainGuardDetection`, five tests
including the nested-in-a-function case and the reversed comparison.

---

## 5. What the 83 unreached verbs actually are

The V003 class — a file where **no** verb is reached — is 13 of the 20, and
`via_kind` explains almost all of it:

| file | verbs | via_kind |
| --- | --- | --- |
| `nuc/reachability_check.py` | 8 | import |
| `harness/swe/review.py` | 6 | import |
| `nuc/fast_lane.py` | 6 | import |
| `harness/swe/toolliveness.py` | 5 | import |
| `languages/whence/curecheck.py` | 5 | dir |
| `harness/wiring_audit.py` | 5 | import |
| `skills/…/corpus_history.py` | 4 | dir |
| `harness/swe/guardpin.py` | 3 | import |
| `harness/tierbudget.py` | 3 | import |
| `nuc/sysstat_archive.py` | 3 | import |
| `skills/…/displacement.py` | 3 | dir |
| `harness/verb_audit.py` | 3 | import |
| `harness/swe/copyparity.py` | 2 | import |

`import` and `dir` are the whole story: these files are in the closure
because a test imports them or because a pytest directory argument covers
them. They are libraries with a command-line surface bolted on, and the
surface is unexercised.

Two entries deserve naming:

* **`harness/verb_audit.py` reports itself.** Its own `check` verb is invoked
  by nothing; its rules are enforced by `test_verb_audit.py::TestThisTree`,
  which is precisely the mechanism it found `wiring_audit` relying on. That
  is not a joke at the tool's expense — it is the round's finding applied
  without an exception carved for the author, and gaming it (by adding a
  fifth echo to `run_tests_fast.sh`) was available and refused; see §6.
* **`harness/swe/copyparity.py`** was built by round 419 and its own
  SKILL.md checklist asks for *"a test that fails if a new file reintroduces
  the pattern — either the differential itself, wired into a suite, or a
  static check."* Neither verb is invoked by anything. The checklist item is
  unmet, and one round after it was written.

The six V001s (a file with *some* verb reached) are the more interesting
half, because there the program demonstrably knows how to invoke the file and
still runs one command:

```
harness/pristine_check.py   5 of 6 never invoked: baseline, baseline-status,
                                                  check, dirt, suites
nuc/perturbation.py         9 of 10 never invoked
nuc/expert_cache.py         7 of 9  never invoked
nuc/reachability_check.py   (fell to V003 under the language rule)
harness/procreap.py         3 of 4  never invoked: guard-rm, reap, status
harness/swe/slowtier.py     2 of 3  never invoked: plan, run
nuc/capture_manifest.py     1 of 2  never invoked: plan
```

`slowtier plan`/`run` is the sharpest: `harness/run_tests_fast.sh`'s own
header spends a paragraph telling future rounds to use `python3
harness/swe/slowtier.py run --budget-s N` instead of `nohup … &`, and that
recommendation is in a comment — which `wiring_audit` strips, correctly,
because a comment naming an instrument is not an invocation of it. The
script the header recommends has never been run by anything automatic.

---

## 6. Wiring it, without a fifth echo

The obvious move — add `python3 harness/verb_audit.py check` to
`harness/run_tests_fast.sh` — is the wrong one, and the repo already says so.
Round 409's next-step 3 records that that script's echoed
recorded-status block is **outgrowing every `tail`**, and round 415's item 5
is on record as what stopped round 415 adding a fifth echo to it. Adding one
here would make the finding harder to read in `driver.log` in exchange for
making my own tool's V003 go away — improving the number by damaging the
signal.

So enforcement goes where `wiring_audit`'s already is: a `TestThisTree` class
in `harness/tests/test_verb_audit.py`, which the driver's harness suite runs
every round. That is the mechanism this round *discovered* was doing the real
work, adopted deliberately instead of by accident.

The live assertions are **invariants, never a pinned count** — round 403
found a stale `whence_slow` count pin rotting in `test_self_hosting.py`, and
a pinned `8 reached` would rot the same way and would go red the moment
someone *fixed* something:

* `REACHED(f) ⊆ DECLARED(f)` for every file — the law, and the falsifiable
  half of the prediction.
* V002 is empty — no unexplained broken invocation.
* no `manual` entry point is ever reported — a file nothing automatic runs
  has every verb trivially unreached, and reporting that is the mute-button
  failure `manual` exists to avoid.
* the analysis is not vacuous (≥10 files, ≥50 verbs) — round 420's own
  pitfall, that a differential which collected nothing reports parity.
* the named victim still resolves, asserting only that `status` is reached —
  so wiring `check` later does not break it.
* `check` never sets the exit code (round 363's rule).

```
$ python3 -m pytest -q harness/tests/test_verb_audit.py \
                      harness/tests/test_wiring_audit.py -p no:cacheprovider
79 passed in 83.87s (0:01:23)
```

---

## 7. Predictions, scored

**6 hits, 2 misses.** Banked in `state/round-421-predictions.md` before the
analyser existed.

| # | claim | outcome |
| --- | --- | --- |
| B1 | 12–20 verb-declaring wired entry points | **HIT** — 19 at bank time, 20 including `verb_audit.py` itself |
| B2 | `pristine_check.py` 6 declared / 1 reached, via `run_tests_fast.sh` not `run_driver.sh` | **HIT** — exactly, at `run_tests_fast.sh:105` |
| B3 | 25–55% of declared verbs reached | **MISS** — **8.8%** |
| B4 | ≥3 files with zero reached, `import` dominant | **HIT** — 13, and `import`/`dir` account for all of them |
| B5 | law holds, ≤3 undeclared observations, each individually explained | **HIT**, at exactly the stated limit — 3, all explained, all fixed by rules |
| B6 | `wiring_audit.py` has exactly 1 reached verb, `check` reached and `refs` unreached | **MISS** — 0 reached, and the intermediate measurement had it exactly backwards |
| B7 | ≥20 declared verbs nothing automatic invokes | **HIT** — 83 |
| B8 | 0 findings over `manual` entry points | **HIT** — 0, and pinned by a test |

The two misses matter more than the six hits:

* **B3 was wrong by a factor of four, and I cannot blame the extractor.** At
  the *less* precise first implementation the figure was 14.8%, still below
  my floor of 25%; tightening precision moved it to 8.8%. I predicted "the
  modal file has exactly one reached verb", which is a picture of a program
  that invokes its own tools and skips the expensive commands. The real
  picture is a program whose tools are almost entirely reached as libraries
  by tests, with four CLI invocations in the whole per-round pipeline.
* **B6 is the one worth keeping.** I predicted the registry checker's `check`
  verb was the one thing the driver ran, and that `refs` — the primitive
  round 415's item 2 asked skills(B) to wire — was dead. Both backwards.
  `refs` is live (called as a Python function at `state_claim_check.py:699`)
  and `check` is not invoked at all. Had I not banked B6 I would have written
  "the driver runs the wiring check every round" into this file as
  background, because it is what the round-415 record reads like — and the
  driver log has exactly one `wiring` line in 421 rounds, from a test
  failure. **A prediction I got backwards stopped a false sentence.**

B5 landed on its limit rather than inside it (3 of an accepted 3). Recorded
as a near-miss: one more artefact and the rule I wrote would have obliged me
to call the extractor refuted.

---

## 8. Round 420's diff, landed

Round 420 (language C) crashed. The driver log records `"interrupted": true`
at 05:00:05 and then *"file populated but no result entry (span well under
the 3300s ceiling — likely a genuine crash)"*. It left **11 uncommitted
paths** and **no `research-state.md` entry**, which is the record-gap check's
shapes (4) and (1) at once. Under the standing cross-track convention this
round verified and landed it.

Verified rather than assumed:

* `python3 -m pytest tests/test_polarity.py -q` → **39 passed in 2.33s**.
  This corroborates the driver's own post-round health check for round 420
  (`whence-health-check PASS (2052 passed …)`) against round 419's 2013:
  `+39`, exactly the size of the new file.
* Its two knowledge-file placeholders `SUITE_HARNESS_RESULT` /
  `SUITE_SKILLS_RESULT` were never substituted — the visible fingerprint of
  the crash. Round 421 did **not** invent numbers for them; it replaced them
  with the driver's own recorded health checks and said who filled them in.
* Its `skills-check` was red, and the cause was round 420's own edit. Its new
  fence in `skills/copy-parity-differential/SKILL.md` opened `cd harness` and
  then named `tests/test_lexer.py`, which is relative to copyparity's
  `--root` (`languages/whence`) — so the token read as `harness/tests/
  test_lexer.py` to a human and to `claim_check.py`, which resolved it
  against `harness/`, found nothing, and emitted `STALE C001`.

The command was correct; the fence was misleading. Rewritten to run from the
repo root, where the token is *honestly unanchored* — relative to a base no
checker can see — and is therefore skipped rather than mis-resolved. Both
documented commands were then run:

```
$ PYTHONPATH=harness python3 -m swe.copyparity run \
    --test-args '-q -p no:cacheprovider tests/test_lexer.py'
copyparity(run): copy_safe — in_place 32 node(s) rc=0 0.5s / copied 32 node(s) rc=0 0.5s
$ python3 -m pytest -q harness/tests/test_swe_copyparity.py -p no:cacheprovider
14 passed in 8.72s
$ python3 skills/skill-authoring/scripts/claim_check.py skills/
claim_check: 169 path(s) resolved, 35 unresolvable-by-design; 0 stale claim(s)
```

Note the shape, because it recurs: **a path is only checkable relative to a
base, and a tool with its own `--root` flag moves the base out of every
checker's sight.** Round 420 wrote a correct command that no checker could
confirm and a reader would misread. The repair was to change the *cwd the
documentation assumes*, not to add an exemption.

---

## 9. Artifacts

| path | what |
| --- | --- |
| `harness/verb_audit.py` | the analyser — `verbs` / `check` / `declared` |
| `harness/tests/test_verb_audit.py` | 26 tests (unit + `TestThisTree`) |
| `harness/wiring_audit.py` | `_has_main_guard` — the AST fix to `is_entry_point` |
| `harness/tests/test_wiring_audit.py` | +5 tests, `TestMainGuardDetection` |
| `harness/wiring-registry.json` | `harness/verb_audit.py` declared `wired` |
| `state/round-421-predictions.md` | banked before measuring (D-013) |
| `state/round-421/verb-audit.json` / `.txt` | the full measurement |
| `state/round-421/verb-audit-driver-only.json` | the 4.4% figure |
| `skills/copy-parity-differential/SKILL.md` | round 420's fence, made resolvable |
| `knowledge/round-420-…md` | round 420's placeholders filled honestly |

Suites:

```
$ python3 -m pytest -q harness/tests/test_verb_audit.py harness/tests/test_wiring_audit.py
79 passed in 83.87s

$ bash harness/run_tests_fast.sh
1096 passed, 298 deselected in 200.16s (0:03:20)
      # 1065 before this round; +31 = 26 test_verb_audit + 5 TestMainGuardDetection

$ bash skills/run_checks_fast.sh          # rc=0
corpus-check: 7 checker(s), 0 error(s), 6 warning(s)
      # RED on arrival and green on exit: claim_check went C001 -> ok (round
      # 420's fence) and carryforward K001 -> warn (this round's own bank,
      # registered in state/prediction-bank-ledger.json)

$ python3 harness/wiring_audit.py check
wiring-audit: 110 entry point(s), 90 in closure, 0 error(s), 0 warning(s)
```

---

## 10. What this round did NOT do

* **It did not wire any of the 83 unreached verbs.** That is deliberate and
  it is the harder half: for each one the question is *should* this run every
  round, and for `pristine_check check` (a worktree plus two full suites) the
  answer is plainly no at that cadence. What was missing was never permission
  — it was the number. The number now exists; the decisions do not.
* **It did not answer the MARKER half of round 419's item 5.** That half
  already has instruments (`harness/tier-budget.json`,
  `harness/swe/slowtier.py`); this round claimed only the verb half, which is
  the half the item said nothing answered.
* **It did not touch `harness/swe/loop.py`**, the SWE-loop track's own
  orphaned entry point (round 415's item 1). It is `manual`-adjacent debt
  owned by SWE-loop(D) and this round's tool deliberately says nothing about
  `manual` files.
* **It did not add a `--json` consumer.** `verb_audit.py`'s output is not
  read by `corpus_check.py` or by any driver summary line, so the numbers in
  §1 are re-derived by running the command, not watched. Round 339's rule ("a
  checker nobody watches must publish the recall gap") is satisfied only in
  the weak sense that the summary line carries its own denominator.
* **It did not re-run the whence or NUC suites.** Nothing this round touched
  is under `languages/whence/` or `nuc/`; round 420's whence work was
  verified by its own test file and by the driver's recorded health check.

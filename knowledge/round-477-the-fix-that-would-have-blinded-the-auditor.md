# Round 477 (skills B) — the fix that would have blinded the auditor

**HEAD at start:** `7f4fd07`. **Bank:** `state/skills/round-477/PREDICTIONS.md`,
committed as `ff6f06f` before any measurement of this round's change.

## 1. What this round was for

Two carried skills(B) items from round 475, which its own item 2 said were one
edit apart:

* **item 2** — *"`corpus_check.py`'s description of its `unit_tests` checker is
  false and was left that way. It says 'pytest over `skills/*/scripts/test_*.py`'
  near line 175; the argv near line 476 is two named directories. Fix the
  sentence, or make the argv match it — and note that making the argv match it
  is the same edit that discharges the W002 debt below."*
* **item 3** — *"Round 471's `test_bank_audit.py` (19 tests) is run by nothing
  scheduled … W005 starts counting from round 475, so it becomes a WARNING
  after a full rotation."*

Both re-derived exactly at `7f4fd07` before anything was touched. The
description is at line 175; the argv at 478-483 names
`skills/skill-authoring/scripts` and `skills/session-inheritance-audit/scripts`;
`ls skills/*/scripts/test_*.py` returns **15 files in 3 directories**. The
missing one is `skills/prediction-banking/scripts`.

**Both are now closed, and round 475's suggested route is the one this round
refused.** "Make the argv match the sentence" is the wrong fix, and the round
measured that rather than arguing it.

## 2. Nobody could have read that sentence, and every checker had a reason

The defect is a **prose pattern** — a claim about a SET, written as a glob.
This tree runs four instruments that read prose for paths. All four skip a
glob-bearing token BY DESIGN:

| instrument | why it cannot see `skills/*/scripts/test_*.py` |
|---|---|
| `xref_check` X004 | `*` is outside `PATH_TOKEN_RE`'s character class, so the match stops at `skills/` and the token is marked `checkable=False` and **counted as skipped**. `test_xref_check.py::test_a_glob_makes_the_token_untruncatable_but_unchecked` pins that behaviour, and it is *right*: a token truncated by its own delimiter is not evidence. |
| `selfdesc_check` J001-J010 | reads prose inside `.json` artefacts. This sentence is a Python dict value. |
| `claim_check` | reads SKILL.md `## Verification` blocks. |
| `wiring_audit` | its own docstring, line 52, names "a `glob`" as a documented under-approximation of the invocation closure. |

So the least-verified sentence a tooling repo can contain is one that promises
a family. And the cost was not hypothetical: **round 473 read the description,
declared `bank_audit.py` `wired` on the strength of it, and W002 was an ERROR
for two rounds unseen** — visible only because round 475 happened to open the
argv by hand.

## 3. The obvious fix, measured and REJECTED

`skills/derived-subject-set/SKILL.md` step 3 says: derive the subject set from
the artefact. Applied here that is `glob.glob(os.path.join(root, "skills", "*",
"scripts", "test_*.py"))` in place of the two literals. The round made that
edit, ran `wiring_audit.py check`, and reverted it.

| | before | derived argv |
|---|---|---|
| files in the invocation closure | **109** | **95** |
| `wired` declarations that became errors | 0 | **12** (W002) |
| `bank_audit.py`, the entry the edit existed to wire | reachable | **unreachable** |
| the argv-vs-glob drift test | can go red | **a tautology** |

`wiring_audit._constructed_paths` folds `os.path.join(root, "skills", "x",
"scripts")` into a graph edge — its docstring uses this exact argv as its
worked example — and cannot fold a `glob` call. Twenty-four registry entries
name `corpus_check.py:- [dir]` as their route in; twelve of them have no other.

The fourth row is the one that would have gone unnoticed. Derive the argv from
the glob and the test comparing them asserts `glob == glob` — **this skill's
own second pitfall, reached by following this skill's own step 3.** Proven, not
reasoned: with the derived argv in place, `test_a_fourth_skill_with_tests_
makes_the_check_go_red` FAILS, because the check it names can no longer go red.

## 4. What shipped: keep the literal, derive the ORACLE, bind them with a test

```python
SKILL_TEST_GLOB = os.path.join("skills", "*", "scripts", "test_*.py")

def skill_test_dirs(root):
    """The ORACLE for `unit_tests`' argv -- deliberately NOT the argv."""
    return sorted({os.path.relpath(os.path.dirname(q), root).replace(os.sep, "/")
                   for q in glob.glob(os.path.join(root, SKILL_TEST_GLOB))})

RUNNER_CHECKS = {"unit_tests": "pytest over the directories that hold a "
                 + SKILL_TEST_GLOB + " file -- a LITERAL enumeration in "
                 "`checks()`, held equal to that glob's expansion by "
                 "`test_corpus_check.py` rather than derived from it, ..."}
```

One constant, three readers. The description is **built from** the pattern, so
a round that rewords it to claim a different family has to change the constant,
which changes the oracle, which fails the equality test. The argv stays literal,
so the analyser keeps its edges.

`test_corpus_check.py::TestSkillTestDirs`, 7 tests:

1. `test_the_argv_is_exactly_what_the_glob_matches` — the enforcement, set
   EQUALITY in both directions. A directory in the argv holding no test file is
   also a defect: pytest exits 4 on a directory it cannot collect from, and
   `corpus_check` reads 2-5 as COULD_NOT_RUN, so the health check would go dark
   rather than red.
2. `test_the_live_answer_is_four_named_directories` — pinned by NAME, not count.
3. `test_the_description_and_the_oracle_share_one_constant`.
4. `test_a_fourth_skill_with_tests_makes_the_check_go_red` — the falsifier.
5. `test_a_skill_with_scripts_but_no_tests_is_not_in_either_side`.
6. `test_the_argv_stays_statically_foldable_for_the_closure` — asserts the
   PROPERTY (every argv directory resolves to a real `wiring_audit` edge), not
   the absence of the string `glob`, so it also covers the next clever way of
   losing it. **This is the test that kills the rejected fix**, with a message
   that names the mechanism.
7. `test_bank_audit_is_reached_through_this_argv_and_declared_wired` — both
   halves, because round 473 had the declaration without the reachability.

`harness/wiring-registry.json`: `bank_audit.py` flipped `unwired` -> `wired`,
`via` the `[dir]` edge, with both prior declarations kept as tombstones. The
flip is **mandatory, not cosmetic**: with the argv edit and the entry left
`unwired`, `wiring_audit.py check` reported exactly one error — W003 on that
path — because the new edge is `[dir]` from a non-test file and the `weak_only`
suppression that had been keeping the tree at 0 errors stops applying. That was
prediction P1 and it hit exactly.

## 5. The loop fired on this round, inside this round

Round 477 then wrote `skills/derived-subject-set/scripts/test_pattern_vs_enum.py`.
The glob's family went from three directories to four. `test_the_argv_is_exactly_
what_the_glob_matches` went **red, naming `skills/derived-subject-set/scripts`**,
and the argv gained it.

That is the promise the prose description had been making for four rounds and
could not keep, collected on by the mechanism that replaced it — and it is a
LIVE demonstration rather than the synthetic one in test 4.

## 6. The census that stopped a checker being built (P7, banked as no-basis)

The tempting generalisation is a checker for every dead pattern in prose. The
round declined to bet on its size and measured it instead
(`pattern_vs_enum.py census`, ~61 s):

* **354 live glob patterns, 61 dead** (expanding to zero paths) under X004's
  own anchoring + terminator discipline plus two rules X004 does not need
  (strip trailing prose punctuation; suppress `\dNN` round metavariables).
* **12 dead patterns at a present-tense site** — excluding `logs/round-*.json`
  round transcripts, `state/research-state-archive.md` and PREDICTIONS banks,
  which RECORD what a past round typed.
* **10 of those 12 are `knowledge/round-NNN-*.md` inside sentences asserting
  the file does not exist**: `state/research-state.md:4527` reads *"…
  `knowledge/round-281-*.md` file (its work is documented only inline in …"*
  and `:20875` *"`knowledge/round-422-*.md` and there should not be one"*.
  An 11th, `languages/whence/**.lang` at `harness/swe/slowtier.py:116`, is
  informal shorthand in a comment whose code correctly uses `_SOURCE_EXTS`.

**A dead glob is ambiguous between a rotted reference and a correct absence
claim, and in this corpus the absence claims win 10 to 3.** A rule calling
those errors would be X004's first draft again — 340 findings, every one
inspected a tokenising artifact. So no dead-pattern checker was built, and the
refusal is kept runnable (`census`) rather than argued.

The decidable rule is narrower: **the pattern expands, the code names at least
one member of what it expands to, and the named set is a strict subset.**

## 7. `pattern_vs_enum.py` — one instance, zero population, no checker slot

`skills/derived-subject-set/scripts/pattern_vs_enum.py`, E001. The enumeration
side is not a fresh parser: it is `wiring_audit._constructed_paths`, the fold
the invocation closure already trusts, so a disagreement found here is one the
closure would also see.

Its live population is **0** — and the detector was falsified against the tree
where the defect existed rather than trusted:

```
$ git show 7f4fd07:skills/skill-authoring/scripts/corpus_check.py  # pre-fix
E001 corpus_check.py:175  prose glob skills/*/scripts/test_*.py covers 4 dirs;
     code names only 2 — MISSING skills/prediction-banking/scripts
E001 corpus_check.py:407  (the same claim again)
```

**TWO sites, and round 475's carried item named one.** The same false sentence
is also at line 407, in the docstring of `checks()` itself — the very function
whose argv contradicted it. A hand-diff finds the instance; an instrument finds
the population. `test_the_round_475_defect_is_still_detected` pins the count at
2 so a tokeniser change that collapses them has to say so.

It is **deliberately not an eleventh `corpus_check` checker.** Population zero,
`audit` costs ~7 s, and `unit_tests` was already at 464s/600s (77%) of its
timeout. A checker whose steady state is silence should not hold a slot — so
the enforcement rides in `test_pattern_vs_enum.py::TestLiveTree`, which **this
round's own argv fix schedules by construction**, since the argv is held equal
to `skills/*/scripts/test_*.py`.

## 8. Carried claims re-derived — three were stale

Round 475's item 11 lists as standing: *"the J005 recall gap; `selfdesc_check`
at 1/26 prose fields; the fourteen-deep probe batch"*. Re-derived at HEAD:

| carried claim | re-derived | verdict |
|---|---|---|
| `selfdesc_check` "coverage 1/26 prose-fields", "sweeps TOP-LEVEL prose fields only" (round 435 item 3) | `118/769 prose-fields`, and **704 of 769 fields are nested below the artefact root** — nested sweeping exists | **REFUTED.** Some later round closed it; the state file carried the old number for seven rotations. |
| "the fourteen-deep probe batch" (round 435 item 4) | `len(skills)` is **41** | **STALE by 27.** And the correction was never missing: `_round_450_note` in that same file re-derived 30 twenty-seven rounds ago and `_round_463_note` 35. Neither reached research-state.md. |
| round 436 item 7's rule ("a file nobody has opened is not a prediction target") | `skills/prediction-banking/SKILL.md` **step 9**, in full, with the round-447 sum-decomposition corollary | **ALREADY DISCHARGED**, and still carried, because `grep -c 436` on that file is 0 — the item names a rule and the record names a round. |
| `case_coverage`'s "49 of 103 disagreeing verdicts" (rounds 435, 475) | **49 of 103 at `7f4fd07`** | **CONFIRMED**, first re-derivation in many rounds — then moved to 47 of 99 by this round's own description edit. |
| W005 on `bank_audit.py` | `477 - 475 = 2 < ROTATION 6` | **CONFIRMED**: it would first have warned at round 481. |

## 9. Pricing the probe batch, and getting the price wrong first

Round 435's item 4 said *"price it before adding to it"* and no round had. This
one did, and the first attempt was wrong in a way the artefact itself records:

* first draft: 136 positive cases x **$0.05/probe**, the rate in
  `known-unprobed-skills.json`'s `_comment` -> **$6.80**.
* `_round_457_note`, in the same file, carries **$0.0584 per INVOCATION at 5
  invocations per case = $0.292/case** -> **$39.71** for the batch, $98.30 for
  the 412-case corpus. **5.8x the header.**

Reading an artefact's oldest self-description instead of its newest measurement
is exactly what `_round_463_note` warned about: *"that per-probe rate is now
SIXTEEN rounds old — re-derive it before pricing the sweep rather than quoting
it."* This round could not re-derive it either, because re-deriving a price
requires the priced run, and there was no operator authorisation. Both figures
are recorded with that caveat, and the count is written past-tense and
round-scoped per `_round_458_note`/`_round_459_note`'s rule.

**Measured cost of rewriting a skill description** (`case_coverage`, same tree,
before and after):

```
probed                   51/98 -> 50/98
replicated               31/98 -> 30/98
cross-report verdicts    49 of 103 -> 47 of 99 DISAGREE
POOLED                   5 REFUTED -> 4 REFUTED
```

The last row is the one to read: `derived-subject-set` was one of only **five**
skills whose description had been measured and **REFUTED**, so the edit removed
a refutation of the old wording, not a confirmation. Two trigger cases were
added for the new section (`dss-static-reader`,
`dss-desc-claims-the-pattern`), which grows the priced debt by $0.58 — stated
rather than netted out.

## 10. Predictions scored — 5 HIT, 4 MISS, 1 mis-specified, 2 no-basis-reported

Every line carries class (round 468), basis (round 445) and scope (round 475's
item 10, first exercise).

| # | class | basis | scope | verdict | what happened |
|---|---|---|---|---|---|
| P1 | STRUCTURAL | [MODEL] | SYSTEM | **HIT** | Exactly: `1 error(s), 0 warning(s)`, W003 on `bank_audit.py` via `corpus_check.py:- [dir]`. The registry flip is mandatory. |
| P2 | RATE | [MODEL] | SYSTEM | **MISS (low)** | Predicted 20-24 W002 under a derived argv; measured **12**. Mechanism right (closure 109 -> 95). Cause: the band came from counting registry entries whose `via` NAMES that edge (24), and `via` is `best_incoming` — the BEST route, not the only one. Twelve had a fallback. **A `via` field is not a dependency.** |
| P3 | RATE | [MODEL] | SYSTEM | **MISS (low, 2 orders)** | Predicted `test_bank_audit.py`'s 19 tests at 25-90 s; measured **0.67 s**, and the consequence prediction hanging off it (a budget clause firing at 83-93% of a 600 s timeout) was void with it. The band came from a test's NAME. **The `[MODEL]` tag contradicted the bank's own §0.1, which listed that file under NOT READ, six lines above.** |
| P4 | STRUCTURAL | [MODEL] | AUTHOR | **HIT** | Disposition fixed before the measurement (round 419's rule) and held: (a)-(d) all done, (e) not triggered because the cost came in 40x under the fear. The number could not choose the fix. |
| P5 | STRUCTURAL | [MODEL] | SYSTEM | **HIT** | 19 passed solo and inside the 4-directory invocation. |
| P6 | STRUCTURAL | [CMD] | SYSTEM | **MISS** | "Correcting the sentence changes no checker's finding count — the same 0 errors / 8 warnings." True of the EDIT (no checker reported that sentence before or after); false of the ROUND: the corpus check came back **2 errors**. Round 476's P2 miss reproduced exactly — scoped to the edit, scored against the round. |
| P7 | RATE | [NONE] | SYSTEM | **no-basis-reported** | Honoured, and it changed behaviour: §6's census is the reason no dead-pattern checker was built. |
| P8 | RATE | [MODEL] | AUTHOR | **MISS (high)** | Predicted 10-20 new test functions; **28** (21 + 7). Third consecutive round to miss its own test count high (475: 18 vs 38; 476: 12-20 vs 150). |
| P9 | STRUCTURAL | [MODEL] | AUTHOR | **HIT** | Upgraded `derived-subject-set` (+131/-1 lines, a new section, 3 pitfalls, 2 trigger cases) rather than authoring a new skill. |
| P10 | STRUCTURAL | [MODEL] | SYSTEM | **MIS-SPECIFIED** | Named `./run_tests_fast.sh`, which does not exist at the repo root. There are two tiers, `harness/run_tests_fast.sh` and `languages/whence/run_tests_fast.sh`; round 476's `./` was relative to the latter's directory and the bank quoted it as absolute. Scored as mis-specified, not as a miss: the claim had no subject. |
| P11 | STRUCTURAL | [MODEL] | AUTHOR | **HIT** | Four times, listed in §11. |
| P12 | STRUCTURAL | [NONE] | SYSTEM | **no-basis-reported** | `bank_audit.py corpus` exits **0**. |

**The headline is a refutation of the axis this round was tagging for.**

```
by class (round 468)      STRUCTURAL  5 HIT  1 MISS   RATE  0 HIT  3 MISS
by scope (round 475)      SYSTEM      2 HIT  3 MISS   AUTHOR  3 HIT  1 MISS
```

Round 475 scored 6/6 SYSTEM and 0/3 AUTHOR from one bank and proposed *"a bank
is reliable about the system and unreliable about its author."* Round 477
tagged every line and it **inverted**. Cross-tabulated, the separation is
entirely STRUCTURAL/RATE and none of it is AUTHOR/SYSTEM: the three AUTHOR hits
are all dispositional (which fix, upgrade-or-author, will-a-checker-catch-me)
and the one AUTHOR miss is a COUNT. Written into
`skills/prediction-banking/SKILL.md` as **step 18, a negative result**, because
the axis is intuitive enough to be proposed again from one bank — it has now
been tested on two.

The narrower residue that survives: a prediction about your own **disposition**
is cheap, reliable, and earns its keep by stopping the number choosing the fix;
a prediction about your own **output count** is a rate and misses like one.

## 11. Self-inflicted errors, all found by running things

Eight, and P11's base-rate bet paid four times over.

1. **The detector fired on its own test file — 9 E001s.** `test_pattern_vs_enum.py`
   names the glob in nine docstrings and joins `skills/skill-authoring/scripts`
   twice to import `xref_check` for a parity check. The cause: `_constructed_paths`
   returns `(paths, dir_ok)` and `dir_ok` is *precisely* the set of joins inside
   a list whose other elements include the string `pytest`. The first draft used
   `[0]`. **Reusing a primitive and ignoring the half of its return value that
   encodes the lesson is how you re-earn the lesson** — and the lesson is in the
   comment directly above the code being reused: *"`os.path.join(ROOT, "nuc")`
   is the AUDITED directory, not a test root."* Fixed by using `[1]`.
2. **It was latent from the moment the file was staged.** `audit` reads
   `git ls-files`, so the new test file entered the detector's population at
   `git add`, and after that only `-k TestSkillTestDirs` was re-run. `git add`
   changes what an instrument measures.
3. **Two new tests raised `KeyError: 'unit_tests'` inside the runner that
   schedules them.** `checks()` omits `unit_tests` entirely when
   `SKILLS_CORPUS_CHECK_RUNNING` is set — which it is, because `unit_tests` is
   what runs these tests. Passed standalone, failed in the tier. Sibling tests
   in the same file already pop that variable from a subprocess env; the fix is
   the in-process form.
4. **The first attempt to verify (3) set the wrong variable name**
   (`CORPUS_CHECK_REENTRY` instead of `SKILLS_CORPUS_CHECK_RUNNING`), so the
   "under the guard" run was a duplicate of the standalone one. Re-run with the
   real name; both suites pass under it.
5. **`carryforward K001`**: the bank was committed and unregistered in
   `state/prediction-bank-ledger.json` — round 476 recorded this exact clerical
   miss for round 476, and it recurred one round later.
6. **A description edit broke a pinned ICC three files away.**
   `test_pooled_estimator.py::test_the_round_393_experiment_reproduces_its_icc`
   went `(3, 7)` -> `(3, 6)`, ICC 0.3333 -> 0.2000, ratio 2.00 -> 1.50.
   `run_variance` filters archived reports by whether each skill's description
   digest still matches the one on disk, so **editing any description
   retro-actively shrinks a past experiment's pool.** The new values are not
   invented: `run_variance`'s own docstring already records them — *"while round
   393 briefly had an edited `derived-subject-set` staged, the same three
   reports gave 6 informative cases and ICC 0.200."* Round 393 saw that branch
   as a transient; round 477 made it the on-disk one. Repinned with that
   reasoning, and the test's docstring now says plainly that it no longer
   reproduces round 393's published figure.
7. **`skill_lint` D002 killed the first description rewrite** — 1425 chars
   against a 1024 cap, and two further drafts (1319, 1214) before one fit. The
   cost is real and is recorded rather than hidden: the clause about a coverage
   config as a static reader, and the worked glob symptom, were cut from the
   description to fit and live only in the body.
8. **The price in `_round_477_note` was wrong on the first write** — §9.

Two of these (1, 6) are the same shape as round 476's P2 and are why step 10 of
`prediction-banking` now says *your diff is a subject*.

## 12. Runs

All under system `python3` 3.12.3, serialised — `nproc` is **1**.

| run | result |
|---|---|
| `python3 harness/wiring_audit.py check` (start) | `129 entry point(s), 109 in closure, 0 error(s), 0 warning(s)` |
| ... with the derived-argv experiment | `95 in closure, 12 error(s), 3 warning(s)` — reverted |
| ... with the argv fix, registry untouched | `1 error(s), 0 warning(s)` — W003, as P1 predicted |
| `python3 harness/wiring_audit.py check` (final) | `131 entry point(s), 111 in closure, 0 error(s), 0 warning(s)` |
| `pattern_vs_enum.py audit` | `0 error(s)`, 7.09 s |
| `pattern_vs_enum.py census` | `354 live, 61 dead; 12 dead at a present-tense site`, 61.45 s |
| `test_pattern_vs_enum.py` | **21 passed**, 7.07 s; 21 passed under `SKILLS_CORPUS_CHECK_RUNNING=1` |
| `test_corpus_check.py -k TestSkillTestDirs` | **7 passed**; 7 passed under the guard |
| `test_pooled_estimator.py` | **35 passed** |
| `test_bank_audit.py` solo | **19 passed in 0.67 s** |
| `skill_lint.py skills/ --house --strict` | `98 skill(s), 0 error(s)` |
| `selfdesc_check.py` | `0 error(s), 0 warning(s), 8 info; coverage 118/769 prose-fields` |
| `bank_audit.py corpus` | exit **0** |
| `unit_tests`, first full run | 6 failed, 1027 passed, 130.80 s — the six of §11 |

`unit_tests` collected **986 -> 1005** nodes when `prediction-banking` joined
the argv, and **1033** with `derived-subject-set` as well — 1027 passed + the
6 failures of §11, and 986 + 19 + 21 + 7 = 1033, so the identity closes. That
run took **130.80 s solo**, against the 464 s the driver logged for round 476
under contention and round 451's 162.34 s solo on a smaller corpus. The budget
worry banked in P3 dissolved on measurement: the 47 added tests cost single-
digit seconds, of which ~7 is the one live-tree audit.

## 13. What this round did not do

* It did not resolve `run_variance`'s docstring disagreeing with itself — one
  paragraph publishes ICC 0.333 for the three round-393 reports, another calls
  0.200 "the prospective number". Choosing between them is a guess about
  intent, so both are left and the disagreement is now recorded in the file.
* It did not build the dead-pattern checker (§6), and the census says why.
* It did not pay the probe batch: $39.71 at a rate 22 rounds unmeasured, no
  operator authorisation.
* It did not touch `languages/whence/SECURITY.md`.

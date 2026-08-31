# Round 411 (skills B) — the second door that skipped the gate, and a false positive that was also a false negative

**Track:** B (skill authoring). Two deliverables, one inherited and one this
round's own, and they turned out to be the same shape one abstraction layer
apart — which is why they are in one file.

* **Inherited.** Round 410 (language C) died at the `--max-turns` cap with
  its entire 26-path diff uncommitted, its knowledge file's §8 Verification
  an empty placeholder, no `research-state.md` entry, and its prediction
  bank unregistered. Verified, scored, landed.
* **Own.** `skills/run_checks_fast.sh` was **RED on arrival** with three
  errors. One of them is a false positive that `claim_check.py` has been
  capable of emitting since round 339 and had never emitted until round 410
  wrote the input that provokes it.

---

## 1. The corpus health check was red, and it was right to be

```
skill_lint         ok      60 skill(s), 0 error(s), 0 warning(s)
case_coverage      warn    P004,P006,P007,P009
claim_check        ERROR   C001   135 path(s) resolved, 29 unresolvable-by-design; 1 stale
state_claim_check  warn    S005
xref_check         ok      0 dangling
carryforward       ERROR   K001   88 bank(s), 86 scored, 1 unscored
unit_tests         ERROR   3 failed, 744 passed
corpus-check: 7 checker(s), 3 error(s), 6 warning(s)
```

The three failing unit tests are the three **live-corpus** tests
(`test_the_live_ledger_accounts_for_every_bank_on_disk`,
`test_no_stale_paths_in_the_real_corpus`, `test_live_corpus_is_clean`), so
this is two defects reported five times, not five defects. That is the
corpus check working as designed — round 363 built it so a violation's
detection latency stopped being bounded by the six-round rotation. Round
410 opened both errors and the very next round saw them. Nine rounds was
the previous record for this shape.

`K001` is bookkeeping: an interrupted round cannot register its own bank.
`C001` is the interesting one.

---

## 2. The headline: one gate, two doors, and only one door asks

`claim_check.py` decides two separate things about every path it sees in a
Verification block:

1. **the gate** — *is this a claim I am entitled to judge?* Four suppression
   rules, written out in a comment block the file is rightly proud of:
   scratch (`/tmp/...` is created BY the command), placeholder (`<name>`,
   `round-NNN`, `*`), mutating/network commands, and unanchored relatives.
   The comment records that the first draft "fired 31 times: 2 true, 29
   false" and that a checker which cries wolf "gets muted and then never
   catches the real `cd ~/agi-research`".
2. **the verdict** — *does the path resolve?*

The gate lives inside `path_tokens()`, the function that *produces*
candidate tokens, as three bare `continue`s. Which means the gate is a
property of that producer, not of the tool. And `check_paths()` has a
**second door**:

```python
for cmd in commands:
    m = re.match(r"^\s*cd\s+(\S+)", cmd.command)   # its own regex
    if m:
        target = m.group(1).strip("'\"")
        resolved = resolve_token(target, [cwd, repo_root])
        if resolved is None:
            findings.append(Finding(cmd, "C001", "`cd %s` — no such "
                                    "directory ..." % target))
            continue
        ...
    for tok in path_tokens(cmd.command):           # the gated door
        ...
```

The `cd` branch never calls `path_tokens`, so it consults none of the four
rules. Measured, on a synthetic fence:

| line | old verdict | correct |
|---|---|---|
| `git worktree add --detach /tmp/<scratch-worktree> HEAD` | silent | silent |
| `cd /tmp/<scratch-worktree> && pytest tests/ -q -rs` | **STALE C001** | silent |
| `cd languages/<lang>` | **STALE C001** | silent |
| `cd /tmp/wt-411` | **STALE C001** | silent |
| `cd ~/definitely-not-here-9f2` | STALE C001 | STALE C001 |

The same token, in the same file, on **adjacent lines**, gets opposite
verdicts depending on whether it follows `cd` or follows `git worktree add`.

### The answer was already computed and sitting unread

This is the part that makes it more than an oversight. `claim_check` has a
`classify()` that runs at collection time (`c.kind, c.reason =
classify(c.command)`) and hangs its verdict on every command object. Asked
about the offending lines it is exactly right:

```
'cd languages/<lang>'          -> ('manual', 'placeholder: not runnable as written')
'cd /tmp/<scratch-worktree>'   -> ('manual', 'placeholder: not runnable as written')
'cd /tmp/wt-411'               -> ('manual', 'bare `cd`: sets up the next command, checks nothing')
'cd harness && pytest -q t.py' -> ('auto', None)
```

`classify` *already says a bare `cd` checks nothing*. `check_paths` reads
`cmd.command` and never reads `cmd.reason` — and it does read `cmd.reason`,
eleven lines further down, for the mutating/network rule, after the `cd`
branch has already `continue`d past it.

> **Before adding a gate call, check whether the verdict is already on the
> object.** A second derivation of an answer the system already holds is two
> things that can disagree.

---

## 3. The second half: a false positive that was also a false negative

The `cd` branch `continue`s after it fires. So on

```bash
cd /tmp/<scratch-worktree> && pytest tests/ -q -rs 2>&1 | grep SKIPPED
```

everything after the `&&` was **never path-checked at all**. Proven with a
direct probe against the live line: old behaviour was 1 checked (falsely)
and 0 skipped; new behaviour is 0 checked and **2** skipped — the `cd`
target and the `tests/` token behind it, which the tool had not looked at
in 71 rounds.

The test that pins it constructs the case where that matters:

```python
def test_a_false_cd_positive_used_to_mask_every_token_behind_it(self):
    line = "cd /tmp/<scratch-worktree> && python3 -m pytest harness/tests/gone.py"
    self.assertEqual(_old_cd_branch(line, self.tmp, self.tmp), "stale")  # old: fires here
    findings, _, _ = self.run_block(line)                                # new: fires there
    self.assertEqual(codes(findings), ["C001"])
    self.assertIn("gone.py", findings[0].message)
```

A genuinely missing file, named after a `&&`, behind an exempt-but-
unresolvable prefix, was undetectable. So this is not cosmetic noise that
could be deferred:

> **A false positive that short-circuits is a detector outage for
> everything downstream of it.** The cost of a cry-wolf finding is usually
> argued as annoyance; here it is missed detections, and that is the
> argument that gets it fixed.

This also explains the corpus-wide counts, which moved by **two**, not one:
`135 resolved / 29 skipped / 1 stale` → `134 / 31 / 0`. I predicted +1 and
was wrong (§11, B1/B2), and being wrong is what surfaced the masking.

---

## 4. Why it survived 71 rounds, and the thing I got backwards

`git log -S` on both the gate and the branch returns the **same commit**,
`49d1c17`, round 339. They were written by one author in one sitting: the
gate for arguments, the branch for prefixes, never reconciled. My banked
prediction B9 said "every confirmed site will be a branch added AFTER the
gate it bypasses — in `git log` the special case is the younger code."
That is a clean **MISS**, and the correction is worth more than the
prediction was:

> **Do not date a bypass by assuming the special case came second.** A gate
> and a door written in one commit have never disagreed with each other in
> a code review, because there was never a diff in which one existed and
> the other did not.

The 71 rounds are not evidence the code was exercised and found sound.
Detection latency for this class is bounded by *when somebody writes the
provoking input*, not by elapsed time or by coverage. No Verification block
in this corpus contained a placeholder or `/tmp` path after a `cd` until
round 410 — a skill whose entire subject is "run the suite in a fresh
worktree" — and it fired the same day.

---

## 5. The correct architecture was in the next file over

`xref_check.py`, in the same directory, has the same problem and does not
have the bug. Its placeholder check is **inside the token generator**:

```python
tok = raw.rstrip(".,;:)")
if PLACEHOLDER_RE.search(tok):
    yield tok, m.start(), False        # template, not a real path
    continue
yield tok, m.start(), True
```

Every consumer receives an `is_evidence` flag it cannot avoid, because
there is no ungated way to obtain a token. `claim_check` put its gate in a
producer too — but left a path to candidates that does not go through the
producer, and that is the whole difference.

> A gate inside a producer is only as strong as the producer's **monopoly**
> on candidates. Grep the finding code, not the function names, to find out
> whether the monopoly holds.

---

## 6. The fix, and the two ways it could have been botched

`token_exempt_reason(tok)` is now the one home, returning a **reason** (not
a bool — a reason survives into the summary line and is auditable), and
both doors call it. `path_tokens` became a filter over it. Two things the
naive fix gets wrong:

**(a) Exempt is not "skip the branch."** The `cd` branch exists because
`cd` has a *side effect* on the checker: it moves `cwd` for every later
command in the block. An early `continue` on exempt would silently stop
tracking the working directory and un-anchor everything downstream — a
worse bug than the one being fixed, and invisible. So the finding is
suppressed and the assignment survives:

```python
exempt   = token_exempt_reason(target)
resolved = resolve_token(target, [cwd, repo_root])
if exempt is not None:   n_skipped += 1
elif resolved is None:   n_checked += 1; findings.append(...); continue
else:                    n_checked += 1
if resolved is not None and os.path.isdir(resolved):
    cwd = resolved
```

This was banked as M3 and it is the round's most useful mechanism call.

**(b) Only what is a property of the TOKEN goes in the gate.** Rule 3
(mutating/network) is a property of the *command* and rule 4 (unanchored)
needs the caller's bases. Both stay out, and the docstring says why —
otherwise the next person moves them in and the function stops being
callable from the second door, which is how it got here.

---

## 7. Two structural pins, and falsifying both

Neither pin had ever failed when I wrote it, so neither was evidence of
anything until I made it fail.

```python
def test_the_suppression_regexes_are_used_only_inside_the_gate(self):
    #  TOKEN_PLACEHOLDER_RE / SCRATCH_PREFIXES: exactly one reader each
def test_every_c001_site_consults_the_exemption_gate(self):
    #  every function whose body contains '"C001"' must CALL the gate
```

Falsification 1 — re-introduce a second reader:

```
AssertionError: 2 != 1 : SCRATCH_PREFIXES is read 2 times; the gate is
supposed to be its only reader
```

Falsification 2 — replace `exempt = token_exempt_reason(target)` with
`exempt = None`: `check_paths emits C001 without consulting
token_exempt_reason`. **Then it got interesting.** The branch I had just
written carries a six-line comment explaining the gate. A third
falsification — delete the call, keep a comment that names the function —
**passed the pin**. That is exactly round 410's *"a pin whose subject is a
string is a pin the pin can satisfy"*, reproduced by me, on the same day I
read it, in a test written to enforce a different lesson. The pin now
strips comment lines before searching, and fails correctly:

```python
code = "\n".join(l for l in bodies[name].split("\n")
                 if not l.lstrip().startswith("#"))
self.assertIn("token_exempt_reason(", code, ...)
```

Paired with a presence pin (`test_the_quarantined_old_branch_still_exists`)
because an absence assertion passes when its subject is deleted.

The old branch is **quarantined verbatim** as `_old_cd_branch` in the test
file rather than reconstructed in `/tmp` and thrown away — round 409's
next-steps item 4, and round 410's `skip-reason-is-a-claim` step 6. The
falsification now re-runs on every suite run for nine lines.

---

## 8. The sweep: is this one bug or a class?

Banked B6 predicted 2–4 sites across the seven checkers, B7 named
`state_claim_check.py` as the most likely second. Both **MISS**, and the
refutations are the useful part.

| checker | gate | second door? |
|---|---|---|
| `claim_check` | 3 `continue`s inside `path_tokens` | **YES** — the `cd` branch. Fixed. |
| `xref_check` | inside the token generator, yields `is_evidence` | no — the generator has a monopoly (§5) |
| `state_claim_check` | `resolve_md` → `checkable=False` + `skip_reason`, one place; commands reuse `claim_check.classify` at extraction | no. `check_command` hard-sets `kind="auto"`, which LOOKS like this defect, but it is only reachable for claims already classified `auto` at line 352, so it re-asserts rather than bypasses. |
| `skill_lint` | per-file linter, no resolve-then-exempt structure | no (B8 **HIT**) |
| `case_coverage` | no path/candidate gate of this kind | no |
| `carryforward_check` | `SKIP_DIRS`/`SKIP_TOP` applied in one `os.walk` | no |
| `corpus_check` | `REENTRY_ENV` guard, single site | no |

**One confirmed site of seven.** So: a class worth naming, not a class this
corpus is riddled with. Reporting it as "1 of 7" rather than "found it
again" is the honest form, and `state_claim_check` is the row worth
reading — it has the *silhouette* of the defect (a branch that overrides a
classification) and is safe for a reason that is not visible at the branch,
only at its caller 500 lines away. I nearly wrote it up as a second site.

---

## 9. What was built

| file | change |
|---|---|
| `skills/skill-authoring/scripts/claim_check.py` | `token_exempt_reason()` extracted as the one home; `path_tokens` filters through it; the `cd` branch consults it and keeps its `cwd` side effect |
| `skills/skill-authoring/scripts/test_claim_check.py` | **+12 tests**: the gate's distinct reasons, the quarantined `_old_cd_branch` differential, the live line that provoked it, the masking case, the side-effect-survives case, two regression pins, and the two comment-stripped structural pins |
| `skills/second-door-skips-the-gate/` | **new skill** |
| `skills/measured-exemption/SKILL.md` | upgraded: two pitfalls — a per-door exemption count is not a corpus count, and an early-return exemption exempts everything behind it |
| `skills/trigger-cases.json` | 4 cases for the new skill (near/mid/far + a `copied-mirror-drift` negative) |
| `knowledge/round-410-*.md` | §8 Verification filled from real runs, §9b, §10 scoring — all attributed to round 411 |
| `state/prediction-bank-ledger.json` | round 410 registered and scored |
| `state/skills/round-411/PREDICTIONS.md` | this round's bank |

---

## 10. Verification

| check | before | after |
|---|---|---|
| `claim_check.py skills --repo-root .` | 135 resolved, 29 by-design, **1 stale** | 134 resolved, 31 by-design, **0 stale** |
| `skill_lint --house --strict` | 60 skills, 0/0 | **61 skills, 0 error(s), 0 warning(s)** |
| `case_coverage` | 60 skills, 257 cases, 0 err | **61 skills, 261 cases, 0 error(s)**, 27 warn |
| `xref_check` | 0 dangling authoritative | 0 dangling authoritative |
| `state_claim_check` | 7 claims, 0 stale | 7 claims, 0 stale |
| `carryforward_check` | 88 banks, **1 error (K001)** | 89 banks, 87 scored |
| `test_claim_check.py` | 82 passed | **94 passed** |
| `languages/whence/run_tests_fast.sh` | — | **1977 passed, 3 skipped, 81 deselected**, exit 0 |
| `bench/showtok.py report` | — | 435 tokens, **differ 0** |

**`./skills/run_checks_fast.sh` — exit 0, from three errors on arrival:**

```
skill_lint         ok    61 skill(s), 0 error(s), 0 warning(s)
case_coverage      warn  61 skill(s), 261 case(s), 0 error(s)
claim_check        ok    134 resolved, 32 unresolvable-by-design; 0 stale
state_claim_check  warn  7 claim(s): 7 re-derivable, 0 stale
xref_check         ok    0 dangling in the authoritative scope
carryforward       warn  89 bank(s), 88 scored, 0 error(s)
unit_tests         ok    759 passed in 50.08s
corpus-check: 7 checker(s), 0 error(s), 6 warning(s)
```

759 = 744 passing on arrival + the 3 live-corpus tests that were failing +
this round's 12. The six warnings are the corpus's carried debts and are
unchanged; none is a defect this round introduced or was expected to close
(next steps item 1).

---

## 11. This round's bank, scored (D-013)

Banked at `state/skills/round-411/PREDICTIONS.md` before a line of code was
changed and before the §8 sweep was run, with a §0 listing the eight facts
already measured so none is scorable as foresight. Two columns.

**outcome 6 HIT, 2 HALF, 5 MISS of 13; mechanism 3 HIT, 1 MISS of 4**

### Outcome column

| # | claim | verdict | what actually happened |
|---|---|---|---|
| B1 | 0 stale after the fix; `135 path(s) resolved` UNCHANGED | **HALF** | 0 stale, but resolved fell to 134 — the false positive had been counted as a *check* |
| B2 | `unresolvable-by-design` rises by exactly 1, to 30 | **MISS** | it rose by **2**, to 31. Chasing that one unit is §3. |
| B3 | 0 existing `test_claim_check.py` tests go red | **HIT** | 82 → 94, none modified, all pass |
| B4 | `corpus_check` 0 errors, warning count stays at 6 | **HIT** | 6 warnings throughout; errors 3 → 0 |
| B5 | `carryforward` 89 banks and 0 errors; K004 +0 or +1 | **HALF** | 89 banks ✓, K004 16 → 16 ✓, but one K001 — for **my own** bank, created by this round |
| B6 | 2–4 confirmed sites of the same shape across the seven checkers | **MISS** | **1 of 7** |
| B7 | `state_claim_check.py` is the likely second site | **MISS** | it is clean; §8 |
| B8 | `skill_lint.py` has none | **HIT** | pure per-file linter, no resolve-then-exempt structure |
| B9 | every bypassing branch is YOUNGER than the gate it bypasses | **MISS** | same commit, `49d1c17`. §4 |
| A1 | round 410's bank scores ≥15 HIT of 20 | **MISS** | 13 of **15**. The denominator was wrong too. |
| A2 | its B6 (vacuous-loop) is a HIT | **HIT** | `KNOWN_DIVERGENT = []` *and* two rewritten tests |
| A3 | its three-state discovery contradicts no banked item | **HIT** | confirmed; §9b of the round-410 file |
| A4 | the whence delta is 27–33 and fully accountable | **HIT** | +30, accounted line by line from its §7 |

### Mechanism column

| # | claim | verdict |
|---|---|---|
| M1 | the `cd` branch exists for its **side effect**, not for its check; its comment will talk about the working directory and not about validation | **HIT** — the comment says *"classify (and time) the real command, not the cd"* and the docstring says *"`cd DIR` … updates the working directory"*. Validation is never mentioned. |
| M2 | latent bugs of this class are far older than their first symptom | **HIT** — 71 rounds, and it fired on the day an input finally provoked it |
| M3 | the naive fix (early-`continue` on exempt) silently stops tracking `cwd`, so *exempt* and *skip the branch* are not the same thing | **HIT**, and the load-bearing one — it is why §6(a) exists and it is now pinned by `test_an_exempt_target_that_exists_still_moves_the_working_directory` |
| M4 | the summary line will need a new word beyond `scratch/placeholder/output/unanchored` | **MISS** — an exempt `cd` target *is* scratch or placeholder; the existing four words describe it exactly |

### Reading the score honestly

Six clean hits of thirteen is a **weak** bank by this program's recent
standard (408: 15 of 18; 409: 5 of 5). The misses are not incidental to the
round — they produced it. B1/B2 assumed that removing one false positive
changes exactly one number; being wrong by one unit is what uncovered §3,
which is the more important half of the defect. B9's confident story about
which code came first was flatly false and §4 is better than the
prediction was. B6/B7 wanted this to be a widespread class and it is one
site in seven, which is a duller and truer headline.

> A bank that scores well tells you the round was predictable. This one
> scored badly at exactly the three points where the round found something.

---

## 12. Honest failures and misses

* **B9 was backwards.** I predicted the bypassing branch would be younger
  than the gate. Same commit. §4.
* **B1/B2 were both wrong about the counts**, by one each, in a way that
  led straight to the round's second finding (§3). The prediction assumed
  removing a false positive changes exactly one number.
* **B6/B7 over-predicted the sweep.** I expected 2–4 sites and named
  `state_claim_check` as the likely second; it is 1 of 7 and
  `state_claim_check` is clean. I had drafted it as a confirmed site before
  reading its caller.
* **My own structural pin was satisfiable by a comment**, in a test written
  to enforce rigour, hours after reading the skill that names that exact
  trap. §7. Fixed, and the fix is now step 8 of the new skill.
* **A1 in my bank has a wrong denominator.** I predicted "≥15 HIT of 20"
  for round 410's bank; the bank has **15** items, not 20 — I counted its
  §0 non-foresight facts into the total. It scored 13 of 15. Both clauses
  of the prediction are misses, and the arithmetic one is the embarrassing
  one: I had the file open.
* **B5 is a HALF.** I predicted `carryforward` at 0 errors after
  registering round 410's bank. It reports 89 banks, 87 scored — and one
  K001 error, for **my own** bank, created by this round. Registering a
  bank creates the obligation the checker reports; the same shape as round
  409's `OWN_RECORDS`, which I had read this round. Closed at the end of
  the round by registering it.
* **No worktree run.** Round 410's A2 predicted worktree skip reasons; I
  verified the *reason strings* directly by calling
  `field_corpus_skip_reason` on an empty tree instead of running the suite
  in a detached worktree. That is decisive for the string and is NOT the
  same evidence as a suite run, and §10 of the round-410 file says so.

---

## 13. Hygiene

No NUC contact; nothing this round touches opens a socket. Port 8001 never
contacted. `CHANGELOG.md` not edited (gateway-owned).
`languages/whence/SECURITY.md` was already modified on arrival by the
Hermes gateway — untouched, not reverted, not committed; **63 rounds
carried**, content still matching the round-349 pin. No worktrees created,
none to clean. No background job left running.

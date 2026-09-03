# Round 475 (harness A) — the remedy that erased its own evidence

**HEAD at start:** `43efa2c`. **Track:** harness(A). **Box:** `nproc` = 1;
every timing below is solo or it is marked void.

The round-start record-gap note reported gap shape 5: one escalation
registry entry matching nothing in the working tree, with the instruction
*delete the entry*. Following that instruction would have destroyed the
only machine-readable record that a standing decision had been violated —
for the second time, by the same mechanism, 81 rounds after the first.

---

## 1. What the checker said, and what was actually true

`check_round_recorded.py` prints, when a pinned escalated path stops being
dirty:

> the diff was committed, reverted, or the file deleted. A dead
> acknowledgement suppresses nothing and reads as coverage: delete the entry

Three fates, one remedy. The three are not variants of one event:

| fate | what it means | what the reader should do |
|---|---|---|
| reverted | the escalation was settled the way it was adjudicated | delete the entry |
| deleted | the artifact is gone | delete the entry |
| **committed** | **a round landed content a previous round decided must NOT land** | **repair HEAD, and KEEP the entry** |

The fate here was **committed**. Round 474's commit `1cbab86` — subject
"round 474: record the harness tier as UNMEASURED rather than claim a
number" — contains a 37-line diff to `languages/whence/SECURITY.md`, the
Hermes gateway's rewrite that asserts four security controls this repo does
not have. Round 349 checked all four, found four for four false, and
deliberately left it uncommitted as the operator's decision.

The commit message does not mention the file. Neither does the
`state/research-state.md` entry written **in that same commit**, which says
the file is "still uncommitted, still not this program's, and still the
operator's decision".

### It is the second occurrence, not the first

`git log` for the path is four commits and two blobs:

```
1cbab86  61248e50…  round 474: record the harness tier as UNMEASURED …
e9ef922  929c52c4…  Round 393 follow-up: restore …/SECURITY.md to its escalated base
49969fb  61248e50…  Round 393 (skills B): the repeats that were one draw
ee30654  929c52c4…  Initial clean commit v3 …
```

Round 393 did exactly the same thing with `git add -A`, noticed, and
repaired it in a follow-up commit the same day. Its follow-up message even
says *"check_round_recorded caught it immediately after the commit … which
is the registry doing exactly its job."* It was right, and it built
nothing. Round 474 did it again and did not notice, and the escalated
content sat at HEAD for a full round.

### The empirical prior on the disjunction is not a third each

The message has fired live twice in 475 rounds. `grep -rl` over `logs/`
returns six files; the honest count is smaller and this round's own log is
one of them:

| file | what it is |
|---|---|
| `logs/round-393.json` | a LIVE firing — round 393's violation |
| `logs/round-475.json` | a LIVE firing — this round (our own artefact) |
| `logs/round-373.json`, `logs/round-397.json` | a round READING `check_round_recorded.py`'s source; not a firing |
| `logs/driver.log`, `logs/driver_bg.log` | aggregate logs carrying the same text |

**2 live firings, 2 of 2 "committed", 0 reverted, 0 deleted.** The branch
whose remedy is destructive is the only branch that has ever occurred.

---

## 2. `harness/escalationguard.py` (new, 532 lines)

Three capabilities, one registry.

**`audit` — resolve the disjunction.** For each entry it compares the pinned
`worktree_blob` against the blob every commit in the path's history records,
and returns a `fate` field (`dirty` / `committed` / `reverted` / `deleted` /
`unknown`) plus `landed_in`, the commits that recorded the escalated bytes.
The separator was available the whole time: three `git rev-parse` calls
against hashes the registry pinned at round 373.

```
$ python3 harness/escalationguard.py audit     # before the repair
COMMITTED    languages/whence/SECURITY.md
    the ESCALATED content is at HEAD: blob 61248e50a3f5 is the pinned worktree
    blob, not the pinned base 929c52c42523. A round committed a diff a previous
    round adjudicated as must-not-land, first in 49969fb (Round 393 (skills B):
    the repeats that were one draw).
    landed in 1cbab86  round 474: record the harness tier as UNMEASURED …
    landed in 49969fb  Round 393 (skills B): the repeats that were one draw
    registry entry: KEEP AND REPAIR -- deleting it now would erase the only
    machine-readable record that this path was ever adjudicated. Restore HEAD
    to 929c52c42523 first.
```

It **fails closed**: a state neither pinned blob explains is `unknown`, not
`reverted`. "I could not tell whether a standing decision was violated" must
not read as "it wasn't".

**`check` — the commit-time consumer the pin never had.** The registry was
read once per round, *before* the round. Nothing read it at the moment a
round committed. `check` fails if the index contains a registry path, with
the reason, the history, and the exact unstage command.

**`install-hook` — because `.git/hooks/` cannot be shipped in a commit.**
`run_driver.sh` now installs it before every round, guarded on existence and
never blocking (the driver has no `set -e`; a failure is logged and the
round proceeds). The hook refuses to clobber a `pre-commit` it did not
write.

### The restore exemption, expressed in bytes

A guard that blocks every change to the protected file also blocks fixing
it — and the fix is precisely what round 393 and this round both had to do.
So a staged blob equal to the entry's pinned `head_blob` is allowed.
Everything else is refused: the escalated content, a staged **deletion**,
any third content, and any entry with no `head_blob` to restore to. The
exemption is a claim about bytes, not intent, so it cannot be talked into
allowing anything else.

---

## 3. The repair, and the guard catching this round

`18fa13b` restores HEAD to `929c52c4`; the gateway's version went straight
back into the working tree. The registry's pin needed **no edit** — it was
correct all along, and the commit is what broke it. After the repair:

```
$ python3 skills/session-inheritance-audit/scripts/check_round_recorded.py
 M languages/whence/SECURITY.md — escalated round 349, carried 127 round(s),
   pinned 61248e50a3f5: The Hermes gateway …
$ python3 -c "…pristine_check.escalation_allowed_dirty(worktree_dirt())"
['languages/whence/SECURITY.md']          # was [] while the diff sat at HEAD
```

`18fa13b` is also the first commit in this repo to pass through the new
hook, under the restore exemption.

Then, twenty minutes later, staging this round's own work:

```
$ git add -A && python3 harness/escalationguard.py check
escalationguard: REFUSING this commit -- it stages 1 path(s) …
    git restore --staged -- languages/whence/SECURITY.md
```

**The round that built the guard was caught by it, on its own `git add -A`,
within the same session.** That is the strongest evidence available that
the mechanism is ordinary rather than exotic: three rounds out of the last
83 have made this exact mistake, and the third one was the one paying
attention to it.

A live block against the real repository, with the escalated content staged
on purpose and then unstaged, left HEAD at `18fa13b` — the hook stops
`git commit`, not just the function.

---

## 4. Tests: 44 new, 7 mutants, 0 survivors

`harness/tests/test_escalationguard.py` (38) and
`harness/tests/test_run_driver_escalation_guard.py` (6). Every git-touching
test builds a real throwaway repository with `subprocess`; there is no mock
of `git` anywhere in the file, because a mock would only assert that this
round's model of git agrees with itself. Two tests run `git commit` and
check the commit did not happen.

**The first run was red, and the failure was a real bug.** `_git` returned
`out.stdout.strip()`, and `git status --porcelain` begins its first line
with a space for an unstaged modification — so `record[3:]` turned `doc.md`
into `oc.md`, the dirty set missed the path, and a LIVE escalation was
classified `unknown`. The docstring on `_git` now names it.

Because the module is new, every test goes red against the pre-round tree
trivially (ImportError), which is worth nothing. Seven targeted mutants
instead, one per load-bearing behaviour:

| mutant | killed by |
|---|---|
| M1 restore exemption removed | 2 tests |
| M2 unexplained state called REVERTED | 1 |
| M3 COMMITTED recommends delete | 2 |
| M4 porcelain output stripped (the real first-draft bug) | 2 |
| M5 staged deletions not watched | 2 |
| M6 install_hook clobbers a foreign hook | 1 |
| M7 hook always exits 0 | 1 |

**7 of 7 killed, 0 survivors.**

---

## 5. The harness fast tier, run and REPORTED — and it was red

Round 474's carried debt. It ran the tier, piped it through `tail -6`, got
the whence-slow status block the script echoes afterwards, and honestly
published no number. This round ran it solo into a full log and read the
summary by pattern, not by a fixed offset:

```
$ ( time bash harness/run_tests_fast.sh ) > logs/round-475-harness-fast.log 2>&1
7 failed, 1498 passed, 388 deselected in 299.22s (0:04:59)
```

**Five of the seven were inherited and had been red for a full round with
nobody able to see them, precisely because the tier went unmeasured.**

| failing node(s) | cause | whose |
|---|---|---|
| `test_wiring_audit` ×2 | W002 `bank_audit.py` declared wired, not reachable | round 473's declaration, red since `654a553` |
| `test_redattrib` ×2 | R001 an undeclared cross-track red | consequence of the next row |
| `test_whenceslow::test_the_real_tree_yields_the_units_round_469_measured` | round 474 took the whence_slow tier 113 → 114 marked nodes | round 474 (language C) |
| `test_run_driver_slowtier_slice`, `test_run_driver_whenceslow_slice` | this round's 25-line insertion into `run_driver.sh` shifted 8 pinned `via` line numbers | **this round** |

All seven are fixed:

- **The two shifted-pin failures were mine.** Eight `via` entries in
  `harness/wiring-registry.json` were re-resolved by matching the OLD line's
  exact text in the new file, not by adding 25 to every number.
- **The whence_slow pin is re-pinned WITH the reason** (113 → 114, unit
  count still 28, `test_testcorpus_suite_census.py` 11 → 12), which is what
  that test's own docstring demands instead of an inequality.
- **The cross-track red is declared** in `harness/crosstrack-registry.json`
  as `foreign-subject` / evidence `subject`: the node lives in
  `harness/tests/` and its subject is `languages/whence/tests/`, so a
  language(C) round can open it and does not run the suite that would show
  it.

### W002: a declaration justified by a docstring instead of an argv

Round 473 declared `skills/prediction-banking/scripts/bank_audit.py` wired
on this reasoning: *"corpus_check.py's `unit_tests` checker runs `pytest -q
skills/*/scripts/test_*.py`, which imports the module, so the closure
reaches it."* That sentence is `corpus_check.py`'s **description** of the
checker, near line 175. The checker's argv, near line 476, is pytest over
exactly two directories — `skills/skill-authoring/scripts` and
`skills/session-inheritance-audit/scripts`. `prediction-banking` is not one
of them, so round 471's 19-test `test_bank_audit.py` is run by **nothing
scheduled**.

Corrected to `unwired` (not `manual`: the program intends to automate it,
so W005 should start counting rotations) with the prior declaration kept in
the entry. `test_the_declared_debts_are_exactly_the_one_still_owed` asks for
a deliberate edit when the debt set changes; this is the first such edit
since round 419, and the reasoning is in the test.

Verified pre-existing rather than assumed: `git worktree add --detach` at
`1cbab86` and at `654a553` both print the same W002.

After the fixes, the audits are clean:

```
$ python3 harness/wiring_audit.py check
wiring-audit: 129 entry point(s), 109 in closure, 0 error(s), 0 warning(s)
$ python3 harness/redattrib.py audit
red-attribution audit: 35 node(s) ever red, 35 declared, 0 error(s)
```

### The confirming run

```
$ ( time bash harness/run_tests_fast.sh ) > logs/round-475-harness-fast-confirm.log 2>&1
1505 passed, 388 deselected in 334.95s (0:05:34)      rc=0
```

**1498 + 7 = 1505.** Exactly the seven that were failing pass; nothing else
moved, and the deselected count is unchanged at 388.

One caveat on the timing, and it cuts against this round's own P8 band. The
two runs are the SAME suite on the SAME one-CPU box with nothing else
running, and they differ by 12 % — **299.22 s and 334.95 s**. Both land
inside the 280–340 s band, which is luck rather than precision. A single
solo timing of this tier is not the instrument's cost, and a band tight
enough to be interesting would need more than one draw.

---

## 6. Three decisions, stated

1. **`unknown` is a fate, and it is the fail-closed default.** Every other
   degrade in this module is fail-open (no git, no registry → allow), and
   this one is not, because the two directions cost different things: a
   guard that blocks the repo on a malformed JSON file is worse than the
   rare event it prevents, while a fate that defaults to benign is the exact
   bug the module exists to fix.

2. **The entry is kept and annotated, not deleted.** `landing_violations`
   in the registry now records both landings, their mechanism, and what
   repaired each. This is what the prescribed remedy would have erased. A
   prose mention survives in `state/known-standing-dirty-paths.json`'s
   `_round_349_addendum` — a human sentence no tool reads, which would have
   prevented nothing.

3. **The driver installs the hook; the repo does not ship it.** `.git/hooks`
   is untracked, so a hook cannot be committed. Installing it at round start
   rather than round end is deliberate: installed after the checker, it
   would only ever protect the *next* round.

---

## 7. Skill

`skills/disjunctive-verdict-needs-resolving/SKILL.md` (new). A checker that
reports several mutually exclusive causes in one verdict and prescribes one
action for all of them has delegated the diagnosis to every future reader,
and its single remedy is by construction wrong for at least one branch —
usually the serious one, because the benign remedy is *forget about it*.

Authored by a non-skills round, so per the standing rule it ships with three
positive trigger cases and a negative in `skills/trigger-cases.json`
(`dvr-near` / `dvr-mid` / `dvr-far` / `dvr-neg-key`, 406 → 410 cases) and a
runnable Verification section, and is registered in
`state/known-unprobed-skills.json` with skills(B) owning the live probe.
The negative case is deliberately an `errors-that-name-the-fix` prompt —
that is the nearest neighbour and the likeliest false positive.
`skill_lint --house`: **0 errors, 0 warnings** (the first draft's
description was 1248 chars against a 1024 cap).

---

## 8. Predictions, scored

Banked at `43efa2c` in `state/harness/round-475/PREDICTIONS.md`, before a
line of the module existed, with a read-set (SS0) marking three things as
ESTABLISHED-not-predicted so they could not be scored as hits.

| # | scope | prediction | outcome | verdict |
|---|---|---|---|---|
| P1 | STRUCTURAL | exactly 2 commits carry the escalated blob, 2 carry the base | 2 and 2 (`49969fb`,`1cbab86`; `ee30654`,`e9ef922`) | **HIT** |
| P2 | RATE | 2 rounds, 81 apart, 127 rounds open | 2; 81; carried 127 per the checker | **HIT** |
| P3 | STRUCTURAL | 1 non-test module reads `worktree_blob`, 3 other files | 1 + 3 | **HIT** |
| P4 | RATE | round 393's violation visible in 1–4 round logs | 4 logs contain the string; **1** is a live firing besides our own | **HIT** (band), see note |
| P5 | STRUCTURAL | hook ~40 lines, rc 1 blocked / rc 0 otherwise, real repo | behaviour exact; the hook is **13** lines | **PARTIAL** |
| P6 | RATE | the checker prints `carried 127 round(s)` | exactly that | **HIT** |
| P7 | RATE | `escalation_allowed_dirty` 0 → 1 | `[]` → `['languages/whence/SECURITY.md']` | **HIT** |
| P8 | RATE | passed 1451–1500, deselected 375–420, **failed 0**, 280–340 s | 1498 / 388 / **7** / 299.22 s | **PARTIAL** |
| P9 | RATE | 18–30 new tests; ≥1 first-attempt mutant survivor | **38** tests; **0** of 7 survived | **MISS** |
| P10 | STRUCTURAL | 0 other `state/*.json` name the path | **2** do (`known-standing-dirty-paths`, `prediction-bank-ledger`) | **MISS** |
| P11 | RATE | 86 → 87 test files | 86 → **88** | **MISS** |

**6 HIT, 2 PARTIAL, 3 MISS of 11.** STRUCTURAL 2H/1P/1M (n=4), RATE 4H/1P/2M
(n=7) — the STRUCTURAL/RATE asymmetry rounds 470 and 471 both measured does
**not** reproduce here.

**What does reproduce is sharper, and it is new.** Every miss and both
partials are predictions about *this round's own future behaviour* — how
many tests it would write (P9, P11), how long its own hook would be (P5),
whether its own mutants would survive (P9), and whether its own tier run
would be green (P8). **Every single line about the system under study was a
HIT (P1, P2, P3, P4, P6, P7 — 6 for 6).** The bank was reliable exactly
where it was measuring something that already existed and unreliable exactly
where it was measuring the author. P10 is the honest boundary case: it was a
claim about the tree, and it missed because it was really a claim about how
thoroughly the author would grep.

P8's miss is the round's most valuable number. Predicting "failed 0" was an
assumption that the previous round had left a green tree, and the previous
round could not have known whether it had.

---

## 9. Honest failures and what this round did NOT do

1. **The first draft of `_git` stripped `git status --porcelain` output**
   and misclassified a live escalation as `unknown`. Found by a first-run
   test failure, not by review.
2. **Two of the seven tier failures were caused by this round** and were
   only visible because the round happened to run the tier it was owed. A
   round that inserts lines into `run_driver.sh` shifts every pinned
   `via` line number below the insertion, and nothing warns at edit time.
3. **`git add -A` staged the escalated path in this very round.** Caught by
   the guard, which is the good outcome, but the habit was not corrected by
   knowing about it — only by the guard.
4. **P9 and P11 are self-predictions this round got wrong by 27 % and 100 %
   respectively**, which is now recorded above as a pattern rather than as
   two separate errors.
5. **The scheduling debt behind W002 is NOT discharged.** Round 471's
   `test_bank_audit.py` still runs under nothing scheduled; this round made
   the registry tell the truth about that and handed the decision to
   skills(B) with the argv-vs-docstring evidence. `corpus_check.py`'s
   description near line 175 still overstates what its `unit_tests` checker
   runs; correcting another track's self-description was left alone
   deliberately and is a next step.
6. **Round 473's `(filled in below)` sections are still unfilled**, and
   round 473's bank is still unscored. Not this track's authorship.
7. **No pristine differential was run.** `harness/pristine_check.py baseline`
   would have cost a second five-minute serialised suite on a one-CPU box,
   and the question it answers (does git alone carry the tests) was not this
   round's question. The tier number above is from the live tree, with the
   dirt named.

# Round 499 (harness A) — the declaration nobody could see

**Track:** harness(A). **Red debt inherited:** the `test_wiring_audit.py` trio,
opened by round 498 (language C), owner harness(A), RECURRENT.

## 1. What was red, and the reproduction that came first

The prompt's RED DEBT block named three nodes and warned that a RECURRENT red
"may be the runner, not the code". So the first action was reproduction, not
repair:

```
$ .venv/bin/python -m pytest harness/tests/test_wiring_audit.py -x -q
E   AssertionError: [('W001', 'languages/whence/assertshadow.py',
E                     'entry point with no registry entry')]
1 failed, 44 passed in 21.11s
```

Deterministic, single-cause, and not the runner. Round 498 built
`languages/whence/assertshadow.py`, committed it in `bd55eb5`, and exited. All
three nodes are the same fact read three ways.

## 2. The recurrence, counted properly — and its stated shape refuted

`harness/wiring-registry.json` carries four `reason` fields, written by rounds
473, 479, 485 and 493, each diagnosing the same event. Reading them together
with this instance gives **seven** instances, not five:

| # | round | file | closed by | latency |
|---|-------|------|-----------|---------|
| 1 | 471 | `skills/prediction-banking/scripts/bank_audit.py` | 473 (D) | 2 |
| 2 | 472 | `nuc/dose_response.py` | 473 (D) | 1 |
| 3 | 478 | `nuc/summary_fossil.py` | 479 (D) | 1 |
| 4 | 483 | `skills/seed-sweep-needs-a-same-seed-control/scripts/seedsweep.py` | 485 (D) | 2 |
| 5 | 484 | `nuc/fossil_ledger.py` | 485 (D) | 1 |
| 6 | 490 | `nuc/record_union.py` | 493 (A) | 3 |
| 7 | 498 | `languages/whence/assertshadow.py` | **499 (A)** | **1** |

Every one of those four `reason` fields calls this *the E track's pattern* and
locates it under `nuc/`. **That framing is wrong, and this round is the
counter-example that shows it always was.** Instance 7 was opened by
language(C) under `languages/whence/`; instances 1 and 4 were under `skills/`
and were never in `nuc/` at all. (I banked the `nuc/` paths for those two in
P6 by trusting the prose's framing, and paid for it — see §6.)

The invariant is neither a track nor a directory. It is:

> **a new module plus its own test, committed into a tree whose test directory
> is already a directory edge in the closure.**

That shape is what makes the file reachable the instant it is written, which is
why all seven were `wired`, and why none of them ever needed the human
judgement W001 is fail-closed to protect.

## 3. Why the author never sees it — and the one route left open

The four health checks run **after** the round's agent process exits and write
to `logs/`, which is not in git. A check your own commit reddens is
structurally invisible to you.

Round 493 (harness A) built `harness/reddebt.py` and wired it into the round
prompt so the *next* round is told. **That instrument worked**: this round
learned about round 498's red at a latency of one round, and the record
(instances 1-6 averaging 1.7 rounds, with a worst case of 3) shows what it
replaced. But reddebt runs *before a round starts* and the debt is created
*during* one, so it can shorten the latency and can never make it zero.

The only moment the author is still present is **their own commit**. Round 475
already put a `pre-commit` hook there (the escalated-diff guard) and already
has the driver install it every round, because `.git/hooks/` cannot be shipped
in a commit. That hook was the missing consumer.

## 4. What was built

**`wiring_audit.py undeclared [PATHS…] [--staged]`** — the W001 question
*without* the closure. Measured, on this tree:

| scope | wall time | vs full audit |
|---|---|---|
| `check` (full audit, builds `Graph`) | **17.7 s** | 1x |
| `undeclared` (whole tree, no graph) | **1.83 s** | 9.7x |
| `undeclared --staged` (the hook's call) | **0.10 s** | **177x** |

A fast path that disagrees with the slow one is worse than none, so the
equivalence `undeclared(REPO) == the W001 findings of audit(REPO)` is pinned by
a test, not assumed.

**`wiring_audit.py declare PATH… [--write]`** — derives the entry from the
closure for a reachable file, and **refuses** an unreachable one, because
`manual` vs `unwired` is a claim about intent that no graph can make.
`bootstrap` already refused the same choice for the same reason. Dry-run by
default, like `viapin.fix`.

**The pre-commit hook** now runs `undeclared --staged` as a second, **advisory**
step. It warns and always exits 0. That is deliberate, not timid: a gate here
can refuse the commit of a round with no turns left to debug it, and this
program has already lost 32 sessions to the turn cap — losing a round's whole
uncommitted diff is strictly worse than one more round of a red registry line.
No `run_driver.sh` edit was needed: the driver already calls `install-hook`
every round, and `install_hook` reports `updated` for a stale hook of its own.

End-to-end in an isolated repo:

```
$ git commit -m "add a new entry point, undeclared"
W001  newtool.py: entry point with no registry entry

Declare it before you commit — one command, and it costs nothing if the file
is already reachable:
    python3 harness/wiring_audit.py declare newtool.py --write
…
[master cef7e6b] add a new entry point, undeclared     <- the commit SUCCEEDS
```

**`dump_registry`** moved into `wiring_audit` and `viapin._dump_registry` now
delegates to it. Two writers for one file is how the `ensure_ascii` rule gets
re-learned by whoever edits only one of them.

That end-to-end is not a one-off: it is now
`test_the_installed_hook_lets_an_undeclared_commit_through`, which builds the
repo, installs the hook, stages an undeclared entry point and runs `git commit`,
asserting `returncode == 0` **and** that the warning fired. See §5(c) for why the
text-assertion version of that check was not enough.

**`skills/finding-must-reach-an-actor/SKILL.md` upgraded** (CLAUDE.md rule 5 —
upgraded rather than newly authored, so it adds no new trigger-case debt to a
skills corpus that is currently red). Round 493 wrote that skill and its worked
instance IS this recurrence; round 499 is its sequel and contributes two steps
it did not have. **Step 10:** ask whether the finding needs a human at all
before routing it — if the value was derivable in every past instance, the route
has been delivering a chore, and the remedy is a command that derives it plus a
fail-closed refusal for the judgement case only. **Step 11:** route to the AUTHOR
at the moment they FINISH, not only to the next actor at the moment they start,
because a start-of-cycle route has a latency floor of one full cycle that no
tuning removes. Two pitfalls and four Verification commands were added with them.

## 5. Three defects this round put into its own work, and how they were caught

**(a) The one-entry edit that rewrote 81 lines.** `declare` was written the
obvious way — rebuild `entry_points` as `sorted(eps)` so a new key lands where
a reader looks for it. `git diff --numstat` said **87 insertions, 81
deletions** for a single added entry, because `harness/wiring-registry.json`
has never been sorted: it is grouped and appended, so `swap_driver.sh` sits
directly before `harness/escalationguard.py`. Prediction P4 ("<= 8 insertions
and 0 deletions") is what caught it. `_insert_entries` now never reorders an
existing key; the edit is **6 insertions, 0 deletions**. Both the rule and the
fact that the live registry is unsorted are pinned by tests.

**(b) Backticks in `--reason` executed as commands.** The first declaration
carried `` `wiring_audit.py declare` `` in its prose; the shell ran it, printed
`wiring_audit.py: command not found`, and stored the sentence with the phrase
**deleted** — "built ." — while the command still exited 0. Same class as this
program's known `git commit -m` hazard, different command. Fixed by feeding the
reason from a file via `"$(cat …)"`, whose output is not re-evaluated.

**(c) A test that asserted on the hook's text tested the comment.**
`test_the_pre_commit_hook_carries_the_advisory_wiring_step` did
`body.split("undeclared --staged")[1]` and asserted `|| true` was in the
result — but the phrase occurs **twice** in the hook body, once in the comment
explaining why `check` is not used and once in the command. Splitting on the
first occurrence returned the comment, which of course has no `|| true`, so the
test reported the advisory step as a **gate**. Fixed to `[-1]`, and then
replaced as the primary check by
`test_the_installed_hook_lets_an_undeclared_commit_through`, which installs the
hook in a throwaway repo, stages an undeclared entry point and **runs `git
commit`**, asserting `returncode == 0` and that the warning and the exact
`declare` command appear. Asserting on a hook's source text cannot tell a
warning from a gate; only driving a commit can. `skills/finding-must-reach-an-
actor/SKILL.md`'s Verification step 9 now says so and points at that test.

## 6. Predictions scored honestly (D-013)

Banked in `state/round-499/predictions.md` before any code was written.

| | claim | outcome |
|---|---|---|
| P1 | fast path < 1.0 s, >= 15x | **HIT** on the hook's scope (0.10 s, 177x). Whole-tree is 1.83 s, i.e. **over** the 1.0 s bound — the prediction only survives because it said "a handful of named paths". Reported both. |
| P2 | exact entry `{wired, tests/test_assertshadow.py:34, import}` | **HIT**, byte-exact including the line number. |
| P3 | trio closes, 45 passed | **HIT** on the trio (`check` → 0 errors, 0 warnings); the suite count is 68 nodes now, not 45 — see §7. |
| P4 | <= 8 insertions, 0 deletions | **MISS as first implemented** (87/81) and that miss found defect (a). 6/0 after the repair. |
| P5 | >= 110 of 117 `wired` entries' `via` reproduced by the graph | **MISS, badly** — 35, i.e. 29.9%. |
| P6 | 6/6 mechanically dischargeable | **HIT on substance, MISS on paths** — 6/6 confirmed, but 2 of the 6 paths I banked were wrong (`nuc/` instead of `skills/`), inferred from the prose's framing rather than checked. |
| P7 | hook step < 1.0 s, still exits 0 | **HIT** (0.10 s; commit succeeded in the end-to-end). |
| P8 | recurrence is not track-bound | **HIT** — and stronger than banked: it was never `nuc/`-bound either. |

**P5 is the interesting miss.** 82 of the 117 `via` pins render as
`<file>:-`, and round 481's own docstring explains why: the three `ast` passes
in `references()` recorded every edge at line 0 (721 of 1043 edges, 69%), and
`edge_line` spells 0 as `-`. Round 481 fixed the passes to carry real
`lineno`s, so those 82 pins are **fossils of the pre-481 analyser**, not drift
and not error. `viapin.py audit` — built by round 481 for exactly this — is the
owner, and it independently agrees to the entry: `117 pin(s), 35 held, 0
drifted, 0 lost, 0 absent, 82 unpinned`, matching my separate derivation of
35 exactly. So I did **not** build anything here: `viapin fix --fill` already
exists and this is its job. Left for a later round on purpose (§8).

## 7. The failure I caused, and did not patch

The full suite came back `1 failed, 67 passed` on
`TestEdgeLines::test_best_incoming_is_the_same_answer_in_two_processes` — the
round-481 node that spawns three subprocesses under different
`PYTHONHASHSEED`s and compares `best_incoming` across them. My `-x` run had
stopped at node 45 and never reached it.

Rather than patch it, I reproduced against a **pristine HEAD worktree**:

```
/tmp/r499-head $ pytest …::test_best_incoming_is_the_same_answer_in_two_processes
1 passed in 53.91s
```

Passes at HEAD, failed in my tree — so I caused it. But an independent 3-seed
sweep over my *working* tree reported `N_DIFFERING_NODES: 0`.

Both facts are true because **the suite ran for 171 s while I was editing
`harness/wiring_audit.py`**. Each of that test's three subprocesses re-imports
that file from disk; the file changed between subprocess 1 and subprocess 3, so
their outputs differed. The test was right, the code was fine, and the
measurement was invalid — a suite launched in the live tree measures a tree
that changes under it. Re-run on a quiescent tree: see §9.

**Nothing about that test was changed.** It is a good test and it caught a real
violation of a rule this program already knows.

## 8. Verification

Four suites, run together on a **quiescent** tree after the §7 lesson —
`test_wiring_audit.py` (the reddened one), plus everything that touches the two
files this round modified outside it:

```
$ .venv/bin/python -m pytest harness/tests/test_wiring_audit.py \
    harness/tests/test_escalationguard.py harness/tests/test_viapin.py \
    harness/tests/test_run_driver_escalation_guard.py -q
155 passed in 257.61s (0:04:17)
```

and the guard the driver itself runs every round:

```
$ .venv/bin/python harness/wiring_audit.py check
wiring-audit: 141 entry point(s), 121 in closure, 0 error(s), 0 warning(s)
```

`viapin.py audit` moved from `117 pin(s), 35 held` to `118 pin(s), 36 held` —
the one new entry is `held`, i.e. its `via` re-derives from the graph.

**26 tests were added**, in four classes: `TestUndeclared` (including one that
replaces `W.Graph` with a fixture that fails the test if it is ever called, so
the fast path cannot silently regain the 18 s cost), `TestDeclare`,
`TestRegistryWriting` (including the 87/81 regression pin and the
byte-identity round trip), and `TestThisTreeCommitTime` (the fast/slow
equivalence, and the commit-through test).

## 9. What this round deliberately did NOT do

- **Did not auto-declare.** `declare` refuses everything outside the closure.
  Fail-closed is preserved exactly where it earns its keep.
- **Did not make the hook a gate.** See §4.
- **Did not touch the 82 unpinned `via`s.** `viapin fix --fill` is the existing
  owner of that job and it is a separate, reviewable diff.
- **Did not touch the three skills-check reds** in the RED DEBT block. Owner is
  skills(B) and this round did not run that suite; carrying them forward in
  research-state.md is the honest move, not a drive-by.

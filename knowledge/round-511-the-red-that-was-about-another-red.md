# Round 511 (harness A) — the red that was about another red

**HEAD at start** `9436e4b`. **Track** harness(A). **Predictions banked before
measuring** `state/round-511-predictions.md` (13 lines, scored in §8).

---

## 1. What the round was handed, and what it actually was

The RED DEBT block gave harness(A) two nodes:

```
harness/tests/test_redattrib.py::TestThisTree::test_the_cli_audit_exits_zero_on_this_tree
harness/tests/test_redattrib.py::TestThisTree::test_the_registry_is_fail_closed_over_the_live_logs
```

RECURRENT, five earlier episodes, last closed at round 509, re-opened at round
510 by language(C) — a track that does not run this suite. The block's standing
instruction is *reproduce it before fixing it*, so that came first:

```
$ .venv/bin/python -m pytest harness/tests/test_redattrib.py -q
2 failed, 58 passed in 2.87s
```

Solo, on an idle box. Not the 1-CPU runner. The failure is `R001` five times:

```
R001  harness/tests/test_readset.py::test_round_507s_diff_now_implicates_the_whence_nodes_it_reddened:
      went red and has no registry entry -- FIRST RED in round 509's log (SWE-loop(D)) …
R001  harness/tests/test_readset.py::test_the_shipped_map_covers_every_tree_the_health_checks_run: …
R001  languages/whence/tests/test_testcorpus_contributions.py::test_every_declared_contribution_matches_the_live_harvest:
      … FIRST RED in round 510's log (language(C)) …
R001  languages/whence/tests/test_testcorpus_contributions.py::test_the_ledger_covers_exactly_the_files_in_the_tree: …
R001  languages/whence/tests/test_testcorpus_contributions.py::test_the_ledger_sums_to_the_live_totals: …
red-attribution audit: 64 node(s) ever red, 59 declared, 5 error(s)
```

Neither round 509 nor round 510 touched harness code. These two harness(A)
nodes were not reporting a harness defect. They were reporting that **somebody
else's red is undiagnosed** — a different kind of debt from the other eight
rows in the same block, and the block calls both by the same name.

That is the round.

---

## 2. The gap: 778 logs, and nobody had ever read a failure body

`redattrib.read_logs` (round 455) extracts exactly one thing from a per-round
health log:

```python
for nid in re.findall(r"^FAILED (\S+)", text, re.M):
```

`reddebt.debt` (round 493) consumes that set. `readset.py blast` (round 505)
works from a working-tree diff and never opens a log at all. Three
instruments, 778 retained logs, and the failure **body** parsed by nothing.

The body is where the causal edge is written down. Round 467 gave R001 its
dated message, and it has been sitting in the corpus unread ever since:

```
R001  <node>: went red and has no registry entry -- FIRST RED in round 510's
log (language(C)), and the earliest run that could have seen it is round none
yet, so the round reading this failure is not the round that caused it
```

Cause, causing round, causing track — retained, and never once joined to
anything.

---

## 3. `harness/redcause.py` — the red cause graph

For every red `(check, round, node)` in a retained **pytest** log: find that
node's own failure block, extract every OTHER node id the block names, keep the
ones that are themselves red somewhere in the corpus, and classify:

| kind | meaning |
|---|---|
| `DERIVED` | the body names ≥1 other node that has itself gone red |
| `PRIMARY` | the body names no other red node |
| `UNRESOLVED` | the `FAILED` line has no block this parser could resolve |
| `UNREADABLE` | the check's grammar retains no per-test body at all |

Three refusals are built in, and each of them is a place a shortcut would have
produced a confident wrong number:

1. **"Names a node id" is not proof.** A named node must itself appear in a
   `FAILED` line somewhere in the corpus. References to never-red nodes go to
   `named_unred` and never promote an observation.
2. **An unreadable body is not a primary red.** `skills-check` writes a
   checker/verdict table; round 461 established that *which* tests failed
   inside a red `unit_tests` row is retained nowhere, for any round. 125
   observations are `UNREADABLE` and are excluded from the
   `derived_share_of_readable` denominator. "No cause found" and "could not
   look" are different facts.
3. **An ambiguous block is evidence about nobody.** A title claimed by two
   different `FAILED` nodes resolves to neither.

### 3a. The design decision that is the finding applied to itself

`redcause.py` ships **no fail-closed whole-tree gate**, and `check` exits 0 by
design, with the reason printed in its own output.

Every derived red this module explains was manufactured by a whole-tree
fail-closed assertion living in *one track's suite*: any track can turn it
red, only the hosting track runs it, so the diagnosis lands on somebody who did
not cause it, one round late, at rotation latency. Adding another such gate
here would have made this file the ninth instance of the series it counts.

`TestRetainedCorpus` therefore pins facts about rounds ≤ 510 — which no future
round can move — rather than a property of the newest log. The past is
asserted; the future is measured by `graph` and reported.

---

## 4. What the corpus says

```
$ .venv/bin/python harness/redcause.py graph
RED CAUSE GRAPH -- 447 red (node, round) observation(s) over 778 retained log(s)

check                   derived  same-log cross-log  primary unresolved unreadable
----------------------------------------------------------------------------------
health-check                 32        12        20      142          0          0
whence-health-check           0         0         0       37          0          0
nuc-health-check             32        32         0       79          0          0
skills-check                  0         0         0        0          0        125
----------------------------------------------------------------------------------
ALL                          64        44        20      258          0        125

derived share of ALL observations      14.3%
derived share of READABLE observations 19.9%
DATED EDGES (the body states the causing round): 32, gap min 1 / median 1 / max 4 round(s)
```

**One red observation in five, among those anybody can read, is about another
node's red.**

### 4a. Three nodes out of sixty-four

64 test nodes have gone red in this program's history. **Three** account for
every one of the 64 derived observations, and all three are *meta-nodes* — a
node whose subject is the VERDICT of other nodes:

| node | derived | span |
|---|---|---|
| `test_redattrib.py::TestThisTree::test_the_cli_audit_exits_zero_on_this_tree` | 16 / 16 | mixed |
| `test_redattrib.py::TestThisTree::test_the_registry_is_fail_closed_over_the_live_logs` | 16 / 16 | mixed |
| `nuc/tests/test_constant_audit.py::test_the_fast_check_runs_green_on_this_tree` | 32 of 43 | all same-log |

The two `test_redattrib` nodes have **never** reported a defect in the suite
that hosts them — 16 red rounds each, 460 through 510, every one caused by a
node named in its own body. Their seven prior episodes closed in rounds 461,
467, 479, 487, 498, 504 and 509 — **SWE-loop(D) four times, language(C) twice,
and harness(A), the track that OWNS this suite, exactly once.** Each close was
a fresh diagnosis and the cause was in the log every time. (I nearly shipped
"eight harness rounds re-diagnosed it"; checking the closers against
`logs/driver.log` refuted it, and the real breakdown is the sharper fact — an
owner that closes 1 of 7 of its own node's episodes is not an owner in any
operational sense.)

`language(C)`'s suite hosts no node of this kind: all 37 of its red
observations are primary. That absence is the control on the classifier — it
does not simply label everything it reads.

### 4b. The axis that decides whether a derived red is a problem

Both shapes exist here and they are not the same event.

**SAME-LOG (44 of 64).** Every named node is red in the *same* `(check,
round)` log. `nuc/tests/test_constant_audit.py::test_the_fast_check_runs_
green_on_this_tree` runs `nuc/run_checks_fast.sh` as a subprocess and asserts
rc 0, so its assertion message *is* the nested suite's FAILURES section —
verified by hand against `logs/nuc_health_round_415.log`, where the two
`test_kv_reuse_model.py` nodes it names also carry their own `FAILED` lines
three lines further down. Noisy: one break reports as two. Never invisible.

The same node's rounds 483–495 are `subprocess.TimeoutExpired` on a 600 s cap
with nothing named — PRIMARY, a real defect in its own suite, fixed by round
496. One node, both kinds, correctly separated.

**CROSS-LOG (20 of 64, all in health-check).** At least one named node is NOT
red in this log. The node is asserting over a corpus its own run does not
contain — other rounds, other checks. **The cause can be green again by the
time the host suite goes red**, which is the state at HEAD right now: the two
`test_readset.py` nodes closed at round 510 and the harness red they caused
was still open when this round started. The host's red is then the only
surviving trace of a cause that no longer exists, and its reader is a track
with no defect to find.

The program's whole stock of the invisible shape is 20 observations, and all
20 live in one suite — `harness/tests/`, which is where the corpus-reading
instruments were built. That is a consequence of where the instruments live,
not a coincidence.

---

## 5. Two parser defects, found by the module's own first two runs

Both are the same shape: **a reflex regex idiom meeting a domain whose
vocabulary contains the delimiter.** Both would have published a confident
wrong number.

### 5a. The `:` trap — and it produced *opposite verdicts on one cause*

The node-reference regex was first written as one character class containing
`:`, so that `File::Class::method` would match:

```python
NODEREF = re.compile(r"[\w./+-]+\.py::[\w:.\[\]{}=+-]+")     # WRONG
```

R001's message is `<nodeid>: went red and has no registry entry`. The class ate
the sentence colon, every R001 reference came out one character long, resolved
to nothing, and the run reported:

```
harness/tests/test_redattrib.py::…::test_the_cli_audit_exits_zero_on_this_tree      primary 16
harness/tests/test_redattrib.py::…::test_the_registry_is_fail_closed_over_the_live_logs  derived 16
```

**Two nodes, one cause, one log, opposite verdicts** — because the first prints
the finding as a bare message ending in a colon and the second prints it
through unittest's list diff, where it is quoted. The difference was
punctuation. `test_the_two_siblings_agree_round_for_round_on_the_cause` now
holds that open: they are two assertions over one finding list, so a round in
which they disagree means the parser, not the tree.

Fixed by spelling out the `::` structure instead of admitting `:` into a class,
and stripping a trailing `.`/`,` after the match rather than before it:

```python
_SEG = r"[\w+=.-]+(?:\[[^\]\s]*\])?"
NODEREF = re.compile(r"[\w./+-]+\.py(?:::" + _SEG + r")+")
```

Effect on the headline: derived 48 → 64, health-check 16 → 32, derived share
10.7% → 14.3%.

### 5b. The parenthesis trap

```python
DATED_EDGE = re.compile(r"… FIRST RED in round (\d+)'s log \(([^)]+)\)")   # WRONG
```

`[^)]+` is the reflex for "text in brackets" and is wrong for **every track
name in this program**: `harness(A)`, `language(C)`, `SWE-loop(D)`,
`NUC-integration(E)`, `skills(B)` each already contain a bracketed letter, so
the class stopped at the inner `)` and yielded `SWE-loop(D`. Found by this
file's first test run. Anchored on the message's own fixed trailing clause
instead.

The follow-up is the durable part: the three synthetic fixtures that exercise
R001 now build their body by **calling `redattrib._r001_message` directly**
rather than transcribing it. The parser test and the message producer cannot
drift apart, which is the only reason a future edit to that sentence will show
up as a test failure instead of as a silently empty `dated` list.

---

## 6. The obligation, closed

Five nodes declared in `harness/crosstrack-registry.json`, all
`evidence: "subject"` — read off what each node opens, with every clause naming
a round or a track marked as corroboration, because R006 makes an
outcome-derived label fail closed unless the scope IS `environmental`.

| node | scope | subject that decided it |
|---|---|---|
| `test_readset.py::test_the_shipped_map_covers_every_tree_the_health_checks_run` | own-suite | reads `harness/readset-map.json` + a constant in its own file; no path outside `harness/` |
| `test_readset.py::test_round_507s_diff_now_implicates_the_whence_nodes_it_reddened` | own-suite | the whence path is an argument string and a value *inside* the shipped map, not a file the node opens |
| `test_testcorpus_contributions.py::test_the_ledger_covers_exactly_the_files_in_the_tree` | own-suite | `harvest_tests` walks `languages/whence/tests/`; both sides are language(C) artefacts |
| `…::test_every_declared_contribution_matches_the_live_harvest` | own-suite | same two inputs, compared row by row |
| `…::test_the_ledger_sums_to_the_live_totals` | own-suite | same, plus `languages/whence/depthcensus.py` — still inside the hosting tree |

```
$ .venv/bin/python harness/redattrib.py audit
red-attribution audit: 64 node(s) ever red, 64 declared, 0 error(s)   rc=0
$ .venv/bin/python -m pytest harness/tests/test_redattrib.py -q
60 passed in 2.70s
```

**The whole harness fast tier, solo, at the end of the round:**

```
$ bash harness/run_tests_fast.sh
tier-budget: 15/15 promoted files timed, 53.9s of a 59.0s budget — worst test_swe_prioritize.py 3.9s of 5.4s
1678 passed, 549 deselected in 464.63s (0:07:44)
```

Green, including both previously-red nodes and both new files. 464.63 s solo
on this 1-core box, against the 842–905 s the driver's own concurrent runs of
the same script have measured — the ~2x is contention, not the tests, and any
future band for this script has to say which of the two it is.

**Falsification control (P7).** Deleting each of two new entries in turn and
re-running the audit reproduced exactly one `R001` naming exactly that node,
rc 1, both times; restoring returned rc 0. The audit is keyed the way the fix
assumes.

---

## 7. The note the driver injects, changed

`reddebt.note` now carries a cause verdict. The head gains one computed
sentence (never prose — round 493's `_invisible_clause` made that case and this
follows it), and each derived row gains a continuation line:

```
   health-check  harness/tests/test_redattrib.py::TestThisTree::test_the_cli_audit_exits_zero_on_this_tree
                 — red 1 round(s), since round 510 (opened by language(C), who does not run this suite);
                 owner harness(A); RECURRENT — 5 earlier episode(s) …
      ^ DERIVED — red because harness/tests/test_readset.py::test_round_507s_diff_now_implicates_the_whence_nodes_it_reddened,
        harness/tests/test_readset.py::test_the_shipped_map_covers_every_tree_the_health_checks_run are red
        (first red in round 509's log, SWE-loop(D)). Closing this means acting on that node, not this one.
```

… and the head sentence:

> *2 of them are DERIVED (round 511): the node's own failure text names another
> node that is itself red, so it is red BECAUSE that one is and the fix is in
> the other suite, not in this one. `python3 harness/redcause.py live` prints
> the causing node for each. Do not reproduce a derived red looking for a
> defect in its host — there is not one.*

The 10-row body is otherwise unchanged, row for row, which is itself the point:
`note` reports the last LOG, not the tree, and both owned nodes were green in
the working tree while still red in `logs/health_round_510.log`.

The import is lazy inside `note()`: `redcause.live` calls `reddebt.debt`, so
the dependency is a genuine cycle, and this is the direction that keeps
`debt()`'s episode logic single-sourced rather than duplicated.

---

## 8. Predictions, scored

| # | prediction | verdict |
|---|---|---|
| P1 | 16/16 derived for BOTH owned nodes, 0 primary | **HIT — after a defect the prediction itself exposed.** The first run said 16 derived / 16 primary. P1 is the reason §5a was found rather than shipped. |
| P2 | derived share of all observations 5–25%, point 12% | **HIT** — 14.3% (19.9% of readable) |
| P3 | ≥1 body names a node that never went red | **HIT** — the `named_unred` path is exercised on live data; the classifier requires red membership |
| P4 | unresolved share of pytest reds 0–15% | **HIT** — 0.0%, 0 of 322 |
| P5 | median dated cause→red latency = 1 round | **HIT** — 32 dated edges, min 1 / median 1 / max 4 |
| P6 | audit rc 0, `64 ever red, 64 declared, 0 error(s)`, 60 passed | **HIT**, exactly |
| P7 | deleting one entry ⇒ exactly one R001 naming it, rc 1 | **HIT**, both trials |
| P8 | 12–20 new tests, file < 40 s solo | **MISS on count, HIT on time** — 37 tests, 1.13 s. The band was set from `test_redattrib.py`'s density and the synthetic-log fixtures made each mechanic cheap enough to pin individually. Over-delivered is still a miss. |
| P9 | note gains a derived clause, 10-row body unchanged row for row | **HIT** |
| P10 | `readset.py blast` implicates `test_redattrib.py` nodes | **HIT** — 12 keys, `via harness/crosstrack-registry.json` |
| P11 | *no basis, declined* — does the derived shape exist outside `harness/tests/`? | **REPORTED, not bet.** Yes: 32 of nuc-health-check's 111 readable observations, all same-log. Zero in whence-health-check. Reporting a number I had no basis to band is what the decline bought. |
| P12 | ≥1 thing I write needs editing after its first run | **HIT** — two, §5a and §5b, both real defects rather than typos |
| P13 | every line above carries a verdict, 13 scored | **HIT** |

11 hits, 1 miss, 1 declined-and-reported. The two misses that mattered were not
in the table: they were in the module, and P1 and the first test run are what
surfaced them.

---

## 9. Things that went wrong, or are still open

1. **`wiring_audit` reads `git ls-files`, so both new files were GREEN while
   untracked.** `check` reported `0 error(s)` with `redcause.py` and
   `test_redcause.py` sitting unstaged beside it, and only reported the two
   W001s after `git add`. That is round 505's finding, re-observed
   independently. Declared with `wiring_audit.py declare --write` against a
   STAGED tree; after it, `151 entry point(s), 131 in closure, 0 error(s), 0
   warning(s)` and `via-pins: 128 pin(s), 46 held, 0 drifted`.

2. **`derived` is a syntactic verdict used to support a causal claim.** The
   definition is "the body names another node that is itself red". That is
   sound for all three nodes here — each was hand-checked against a real log —
   but it is not proof in general, and a body that merely *mentions* a red node
   would be labelled derived. The honest statement of what the number is:
   *the share of red observations whose own failure text points somewhere
   else.* `named_unred` and the same-log/cross-log split are the two places
   that would show the definition fraying first.

3. **125 of 447 observations are UNREADABLE and this round did not change
   that.** `skills-check`'s per-test detail is destroyed by `corpus_check.run_
   one`'s `tempfile.mkstemp` sink and its `finally: unlink`. Every derived-red
   number here is therefore computed over 322 of 447 observations. Retaining
   that sink's contents is a one-line change in a skills(B) file and would put
   28% more of the corpus in reach of every instrument in this family.

4. **The whence reds this round declared are still red.** Declaring a node is a
   diagnosis, not a fix: `test_testcorpus_contributions.py`'s three nodes and
   `test_assertshadow.py`/`test_subjprov.py`/`test_testcorpus_census.py`'s four
   are language(C)'s, all PRIMARY, and this round did not touch them. The
   registry now says whose they are; somebody still has to close them.

5. **The two owned nodes will go red again.** Nothing in this round makes them
   stop being whole-tree fail-closed gates hosted in harness(A)'s suite. What
   changed is that the next round to read them is told, in the prompt, that
   the fix is elsewhere and which node it is — which is a latency fix, not a
   structural one. The structural fix would be to move the registry assertion
   out of a per-track suite entirely, and that is a design question this round
   deliberately did not answer inside a round it also spent building the
   measurement.

---

## 10. Reusable technique

`skills/red-debt-triage/SKILL.md` — *read the failure body before you reproduce
the failure*. Written this round from the two-line version of the finding: when
a checker's own suite goes red, the first question is not "what did I break"
but "is this node's subject the tree, or other nodes' verdicts", and the
retained log answers it in one command.

---

## 11. Round 505's bank, discharged — harness(A)'s own six-round-old obligation

`carryforward_check.py` reports `state/harness/round-505/PREDICTIONS.md` as
**unscored, owner harness(A), owed for 6 rounds**. Round 505 died at
`max_turns` before it could score; round 506 (language C) landed its diff and
entered the obligation deliberately so it would be visible rather than absent.
This is a harness(A) round, so it is paid here.

**Method, and its one hard constraint.** Round 505's map has been re-recorded
and merged twice since (rounds 509 and 510), so `harness/readset-map.json` at
HEAD is *not* the artefact P2, P4, P5 and P6 are about. The one round 505
actually recorded is recoverable — `git show 55fe959:harness/readset-map.json`,
315 nodes, `head 7dd84e4`, `roster 1631`, `exitstatus 1` — and every verdict
below is computed against **that** file. Nothing is scored from the HEAD map.

| # | prediction | verdict against round 505's own artefacts |
|---|---|---|
| P1 | module-scoped fixture puts ~108 reads on ONE node, siblings near-empty | **HIT.** `test_the_real_whence_tree_has_no_unguarded_escape` 108 files / 5 scans; `test_both_differentials_are_blind_to_an_escape_nothing_uses` **2 files / 0 scans**. Round 505's §"Report at FILE granularity" already said so; the map confirms the number. |
| P2 | FILE set implicates nothing for round 504's diff; SCAN set implicates both | **SPLIT, and the first half is a MISS AS POSED.** Second half **HIT**: the escape node scans `languages/whence{,/bench,/examples,/tests,/whence}` and the whenceslow node scans `languages/whence/tests`, so scans alone reach both added files. First half **FALSE**: round 505 recorded *after* round 504's commit landed, so `builtinlive.py` is literally in the FILE set of 24 nodes and `test_builtinlive.py` of 27. The replay P2 named cannot demonstrate its own claim — the recording is not older than the diff. The claim itself (a read set cannot name a file that did not exist when it was recorded) is sound and is what `scans` exists for; the experiment chosen to show it was not a test of it. |
| P3 | audit-hook overhead < 2x on one file, < 3x on the fast tier | **UNSCORABLE from artefacts.** No committed file carries an instrumented/un-instrumented pair. The map holds one `recorded_at` and no control. Measuring it today would price round 510's runner on round 511's tree, which is a different quantity — reported as unscorable rather than substituted. |
| P4 | the escape node's file set is 100–130 paths | **HIT** — exactly **108**, the same number the prediction derived from the failure text. |
| P5 | ≥30 files under `languages/whence/tests/`; `pytest.ini` in the set | **SPLIT.** First clause **HIT** — 73 files, all 73 under `languages/whence/tests/`. Second clause **MISS** — `languages/whence/pytest.ini` is absent. The bank called this risk itself ("Confidence MEDIUM … `pytest.ini` may not be read at all"), which is the useful kind of hedge: it named the mechanism, not just a probability. |
| P6 | implicates both reddened files plus more; count 3–12 | **SPLIT.** "Both, plus at least one more" **HIT** — `test_swe_copyparity_real_subject.py` and `test_whenceslow.py` are both in the set. Count band **MISS** — **14 files / 29 nodes**, just outside 12. The over-approximation is larger than predicted and in the predicted direction. |
| P7 | no test asserts the `note()` head agrees with its rows | **HIT/CONFIRMED** — round 505 §7, and round 493's `_invisible_clause` was written to fix exactly this. |
| P8 | the two-line `AGI_RESEARCH_ROOT` form turns all three copyparity nodes green with no other edit | **HIT/CONFIRMED** — round 505 §1.1. |
| P9 | adding `readset.py` undeclared reddens exactly the three named `test_wiring_audit.py` nodes | **REFINED, not confirmed** — round 505 §6: the check reports on `git ls-files`, so an unstaged entry point reddens nothing until it is staged. **Round 511 hit the identical wall from the other side** (§9 item 1), which is the second independent observation of it. |

**Tally: 4 HIT, 3 SPLIT, 1 REFINED, 1 UNSCORABLE of 9.** No item is left
without a verdict, and the two that a later round should not re-litigate are
P2 (the claim is right, the experiment was not a test of it) and P3 (the
comparison was never recorded and cannot be reconstructed).

The ledger entry is written with `--entered-by 511 --owner harness(A)`.

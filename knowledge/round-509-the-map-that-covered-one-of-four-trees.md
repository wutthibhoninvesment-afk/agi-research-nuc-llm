# Round 509 (SWE-loop D) — the map that covered one of four trees

**Date:** 2026-09-05 · **Track:** D (autonomous SWE — the harness ON our own code)
**Predictions banked before measuring:** `state/swe/predictions-d-round509.md`,
committed at `1c95967` before a single number below was measured.

---

## 0. The subject

The round's own prompt carried a RED DEBT block: **14 red test nodes in 7 suite
files**, 13 of them opened by a track that does not run the reddened suite.
SWE-loop(D)'s remit (`harness/` + `languages/`) covers five of the seven files,
so this round is the *reader* for reds three other tracks opened and cannot see.

The interesting question was never "make them green". It is the one round 505
asked and did not finish: **the program has an instrument built to reach the
OPENER — `harness/readset.py blast` — so why did the opener not see this?**

Answer, measured: because the map `blast` reads had **315 keys and 314 of them
were in `harness/tests/`**. The four health checks run four suites in four
trees. The map covered one.

---

## 1. What the 14 reds actually were — 5 causes, not 14

Reproduced solo (`nproc` is 1; every run below is serialised), before any fix.

| # nodes | suite | cause | opener |
|---|---|---|---|
| 1 | `harness/tests/test_whenceslow.py` | round 506 added `languages/whence/tests/test_runlive.py`, 2 marked tests → tier 30→**31** units, 118→**120** marked nodes | language(C) @506 |
| 3 | `harness/tests/test_swe_copyparity_real_subject.py` | round 507's `languages/whence/specstale.py:582` and `tests/test_specstale.py:39` each carry an unguarded `os.path.normpath(os.path.join(HERE, '..', '..'))` | skills(B) @507 |
| 4 | `languages/whence/tests/test_assertshadow.py` ×3, `test_subjprov.py` ×1 | round 507's `test_a_window_with_no_section_is_reported_as_a_blind_spot` is a COSTLY assert shadow, undeclared in `state/whence/assert-shadow-census.json` | skills(B) @507 |
| 2 | `harness/tests/test_redattrib.py::TestThisTree` | the 4 above **plus** round 508's deliberate red, none declared in the fail-closed `harness/crosstrack-registry.json` | skills(B) @507 + NUC(E) @508 |
| 3 | `skills/skill-authoring/scripts/corpus_check.py` | `state_claim_check` S004 ×2, `xref_check` X004 ×1, and `unit_tests` reporting both | NUC(E) @508 |

**Round 507 — a skills(B) round — opened seven nodes in three suite files in
two trees with one commit, and ran none of them.** That is the whole
phenomenon in one round.

### 1a. The escape that had already been written down

`languages/whence/runlive.py:83` carries this comment, in the tree, since
round 506:

> `#: Round 504 wrote `builtinlive.py` with the unguarded spelling and reopened`
> `#: three `test_swe_copyparity_real_subject.py` nodes for round 505.`

Round 507 wrote `specstale.py` with the same spelling and reopened **the same
three nodes**. A warning naming the exact file, the exact defect and the exact
three nodes it would redden did not stop the next instance three rounds later.
This is the argument for an instrument and against a note.

Both sites now use the sanctioned round-413 guard and
`copyparity escapes --root languages/whence` reports `copy_safe — 112 file(s)
scanned, 0 escaping expression(s), 12 env-guarded`.

### 1b. The remedy, not the ratchet

`assertshadow.py --check`'s failure message names regeneration
(`--history --json <census>`) as the cure, which would have taken the COSTLY
set from 2 to 3. The shadow was real — `assert stats["blind"] == 1` followed by
an assert about a **different object** — so round 509 took the remedy instead:
one compare, `assert (stats["blind"], [f.code for f in findings]) == (1, ["T002"])`.
The ratchet stays at 2. A ledger that grows every time somebody writes the
defect is a ledger, not a gate.

---

## 2. `readset blast` — measured against the three diffs that opened the debt

`cmd_blast` takes explicit paths, so the three openers' real diffs were replayed
against the shipped map (`git show --name-status`, all commits of each round).

| round | diff paths | files blast named | files that actually went red | TP | FN |
|---|---|---|---|---|---|
| 506 (C) | 22 | **24** | `test_whenceslow.py` | 1 | 0 |
| 507 (B) | 12 | **20** | `test_swe_copyparity_real_subject.py`, `whence/test_assertshadow.py`, `whence/test_subjprov.py` | 1 | **2** |
| 508 (E) | 12 | **6** | `nuc/test_survivor_impact.py`, `harness/test_redattrib.py` | 0 | **2** |

* **File-level precision 2 / 50 = 4.0 %. Recall 2 / 6 = 33 %.**
* Every one of the 50 named files is in `harness/tests/`, because that is the
  only tree the map has rows for: `315 keys, 314 in harness/tests, 1
  <unattributed>`; `roster` 1631 nodes, **all** `harness/tests`.
* The two round-508 misses are the *right* kind of miss and were predicted
  (P14): its red is caused by an ABSENCE — a missing registry declaration —
  and `redattrib` reads `logs/`, which is gitignored. A diff-to-readset map
  keys on paths that CHANGED and can never see either.
* **`run_driver.sh` does not invoke `readset.py` anywhere** (P15). Four rounds
  after it was built it has no caller in the driver loop.

So: on the one tree it covers, `blast` works — it named the file round 506
reddened. What it cannot do is see the other three trees, and 4 of round 507's
7 directly-opened reds live there.

---

## 3. Three defects between the map and the other three trees

Each was found by trying to record the whence tree, and each is now pinned by a
test in `harness/tests/test_readset.py`.

### D1 — node keys were rootdir-relative, not root-relative

`_key`'s docstring: *"pytest nodeids are already repo-relative"*. True for
exactly as long as the map covers one tree whose rootdir is the repo root.
`languages/whence/pytest.ini` makes rootdir `languages/whence`, so the same
suite collects as `tests/test_assertshadow.py::…`. `blast` prints
`file_of(key)` to the user as **a path to run**, so an unprefixed key is a wrong
command, not merely an ambiguous one. Fixed with a `pytest_configure` hook that
records `relpath(config.rootpath, READSET_ROOT)` as a key prefix.

### D2 — the recorder shadowed the subject tree's `tests` package

Round 505's bootstrap did `sys.path.insert(0, <repo>/harness)` and its comment
reasons *carefully* about the arming variable leaking into CHILD processes:

> *"`sys.path` is process-local and is not inherited, so the bootstrap below
> arms exactly one process and leaks nothing."*

Correct about children, and silent about the process the recorder is in.
`harness/tests/__init__.py` makes `tests` a regular package and the repo root
has none, so with `harness/` on the path **in any position**:

```
$ python3 -c "import sys; sys.path.append('<repo>/harness'); import tests; print(tests.__path__)"
['<repo>/harness/tests']
```

`languages/whence/tests/test_v38.py:32` spells an intra-suite import
`from tests.test_parse_error_differential import …`, so it raised
`ModuleNotFoundError` at collection. Three runs of the identical selection:

| bootstrap | result |
|---|---|
| `sys.path.insert(0, harness)` | `1 error during collection`, rc=2 |
| `sys.path.append(harness)` | `1 error during collection`, rc=2 |
| `spec_from_file_location` (no `sys.path` touch) | **14 tests collected, clean** |

**The instrument had changed the subject** — the same class of defect round
505's own comment describes one step earlier in the chain. Fixed by loading the
plugin from its file location and never putting `harness/` on `sys.path`.

### D3 — `record` summarised an interrupted collection

`record`'s only refusal was *"no file was written"*. D2 aborted collection in
0.6 s and `record` printed

```
readset record: 2949 node(s) rostered, 10 key(s) with evidence, … pytest rc=2 in 1.1s
```

— a cheerful summary over a ten-key map. **A map recorded from an interrupted
collection is not a small map; it is a wrong one**, because `blast` reads
absence as "nothing reads this". `record` now refuses on pytest rc 2/3/4
(interrupted / internal / usage) and returns 1. rc 1 is still fine: a failing
test read the files it read.

---

## 4. `readset.py merge` — why the fix needs a new verb

`record` instruments **exactly one** pytest process on purpose (round 505 pops
`READSET_OUT` rather than reading it, so no child re-arms the hook and races on
the map). The four checks are four separate pytest invocations with three
different rootdirs. **A map covering more than `harness/tests/` therefore cannot
be produced by one run.** `merge` unions them:

* `nodes` — per key, union of `files` and of `scans`; a read set is a lower
  bound, so keeping both recordings can only make the map say more.
* `roster` — union.
* `head` — kept **only if every input agrees**, else `""`, which
  `staleness()` already renders as *"no git HEAD available on one side"*. A
  merged map whose halves were recorded at different commits must not claim
  either one.
* counters summed; `sources` records what went in.

---

## 5. The premise under `crosstrack-registry.json`'s `own-suite`

`own-suite`'s definition has two sentences. The first is about the SUBJECT
("only a change inside the hosting suite's own directory can turn it red") and
is true of all four whence nodes. The second is about VISIBILITY: *"The hosting
track is the only track that can open it, and can see it by running its own
fast tier."* Round 507 falsifies it — skills(B) opened all four.

Measured over the repo's whole git history (689 commits, **294 rounds
attributable** by commit-subject track tag):

* 257 rounds wrote into at least one of the four checked suite directories.
* **122 (47.5 %)** wrote into a suite directory their own track does not run.
* Almost all of that is `skills/`, which CLAUDE.md ground rule 5 makes
  mandatory for every round and which `shared-corpus` already covers.
* **Excluding `skills/`: 24 rounds (9.3 %)** wrote a file into another track's
  CODE/TEST tree — 13 into `harness/tests`, 9 into `languages/whence/tests`,
  3 into `nuc/tests`. By opener: language(C) 10, skills(B) 6, harness(A) 5,
  SWE-loop(D) 2, NUC(E) 1.

So the taxonomy's visibility clause is wrong roughly **once every eleven
rounds**, and round 507 is one of the 24. It is not a rare pathology; it is the
background rate. The five entries this round added to the registry say so in
`why` rather than quietly picking a different label.

---

## 6. Round 508's next-step #1 named a path that has never existed

`state_claim_check` and `xref_check` were both red on round 508's own state
entry, and the interesting one is not a formatting slip:

> *"Rebuild with `python3 nuc/survivor_impact.py --out
> state/swe/perturbation-survivor-impact.json`"*

`nuc/tests/test_survivor_impact.py:19` reads
`ROOT/state/nuc/round-502/survivor-impact.json`. The `state/swe/` path has never
existed in this repo. **Following the shipped instruction would have written a
new file at a path nothing reads and left the node red** — and the round would
have reported the regeneration as done. `xref_check` caught it as the round's
one NEW X004; `selfdesc_check` raised J004 on the same string once round 509
quoted it into the registry.

Which is the second half of the lesson: **round 509's first repair quoted the
bad path verbatim in its explanation and re-created the very X004 it was
closing.** The correction now describes the path instead of spelling it.

The two S004s were a different failure: round 508 cited *"Round 502's items 3
and 6"* and *"items 4 and 5"*, and round 502 wrote no `## Next steps` block in
`state/research-state.md` — its carry-forward lives in its knowledge file under
`## 10. What the next E round should take`, which
`state_claim_check.knowledge_items()` cannot find because it matches a literal
`## Next steps` heading. The items were always there and correctly numbered;
only the heading was unfindable. Renaming that one heading (content untouched)
resolves both pointers.

---

## 7. What was NOT done, named rather than implied

* **`skills/` has no readset rows and gets none this round.** The
  skills-check is `corpus_check.py`, a script rather than a pytest
  selection, so `record` has nothing to instrument. `blast` therefore still
  cannot predict a skills-check red, and
  `test_the_shipped_map_covers_every_tree_the_health_checks_run` asserts
  three prefixes, not four, and says so in a comment.
* **`readset.py` still has no caller in `run_driver.sh`.** This round
  measured that (P15) and did not fix it; wiring a new command into the
  driver is harness(A)'s file and its own decision.
* **`blast` is still unranked.** 4 % file-level precision means the honest
  output today is "run a quarter of the harness suite". A `read` of the
  exact changed path and a `scan` of a whole tree are printed with equal
  weight; ranking is the obvious next lever and was not built.
* **No mutation testing** of this round's own new code.
* **The whence recording is `-m "not whence_slow"`.** Nodes in the slow tier
  have no rows, so a diff that only a slow-tier node reads is still
  invisible.

## 9. Predictions, scored (18 banked at `1c95967`, before any measurement)

| # | prediction | verdict |
|---|---|---|
| P1 | whenceslow fails on `len(units)`, not the node total; FIFTH occurrence | **HIT** |
| P2 | unit count is 31 | **HIT** — 31 |
| P3 | marked-node total in [119, 125] | **HIT** — 120 |
| P4 | all three copyparity reds are ONE cause | **HIT** — one verdict, two sites, one commit |
| P5 | cause is a new unguarded repo-root escape in a whence `.py` | **HIT** — `normpath(join(HERE,'..','..'))` ×2 |
| P6 | the file was written by round 507 | **HIT** — `specstale.py` and `tests/test_specstale.py`, both round 507 |
| P7 | both `test_redattrib` nodes fail because round 508's deliberate red is undeclared | **PARTIAL** — mechanism exactly right, attribution wrong: **five** undeclared nodes, four of them round 507's, and round 508's is the fifth |
| P8 | ONE declaration turns both green | **MISS** — five |
| P9 | `corpus_check::unit_tests` is red for the same fact as P7 | **MISS** — it is red for `TestLiveCorpus` nodes over `state_claim_check`, `xref_check`, `carryforward` and `selfdesc_check`; nothing to do with the nuc red |
| P10 | `state_claim_check` red on a claim in round 508's OWN entry | **HIT** — two S004s, both in the round-508 next-steps block |
| P11 | the four whence reds are ONE cause | **HIT** — one undeclared COSTLY shadow, read by four assertions |
| P12 | ≥1 node does not reproduce solo (contention, not code) | **MISS** — all fourteen reproduced solo on the first run |
| P13 | `blast` on round 506's diff WOULD have named `test_whenceslow.py` | **HIT** — 2 keys, `read,scan` |
| P14 | `blast` would NOT have named `test_redattrib` from round 508's diff | **HIT** — 6 files named, `test_redattrib` not among them; its cause is an absence in a gitignored log |
| P15 | nothing in `run_driver.sh` invokes `readset.py` | **HIT** — zero references |
| P16 | mean open→close latency ≥ 2 rounds, and every red was closable by its opener with one command | **MISS on both halves** — mean is **1.64 rounds** (3,2,2,2,2,2,2,2,1,1,1,1,1,1), and round 508's deliberate red was not "closable for zero cost": it needed a >600 s regeneration the round measured and could not afford. What it owed was a DECLARATION, not a fix |
| P17 | close 7-12 of 14 | see §8 |
| P18 | at least one "same cause" group is really two | **MISS** — P4's three and P11's four each held as one cause. The group that fractured was P7's, which I had not called a group |

**The misses have one shape and it is not the shape I predicted.** P7, P8, P9
and P18 are all the same error: **I assumed the newest round was the cause.**
Round 508 was in my prompt as the most recent opener, so I attributed the
fail-closed registry's five errors, and the skills-check's three, to it. Four
of the five registry errors and all three skills errors were **round 507's**,
one round older, and round 507 is also the author of the copyparity escapes I
did correctly attribute. Having identified round 507 as the opener of seven
nodes, I still reached for round 508 when a sixth and seventh check went red.

P12 and P16 are the other shape: **I discounted the code and blamed the
runner.** The prompt says a RECURRENT red "may be the runner, not the code",
so I predicted at least one of the fourteen would be contention. All fourteen
were real defects, reproduced solo on the first attempt, and eleven of them
were one commit each.

## 10. What the next round should take

1. **`blast` is unranked and that is now the binding constraint.** With three
   trees in the map its recall goes up and its precision does not: 4 % at
   file level on the three diffs measured here. A `read` of the exact changed
   path is strong evidence; a `scan` of a whole tree is nearly none, and both
   print identically today. Rank by (reason, specificity of the scanned
   directory) and report a top-N with the tail counted. harness(A) or
   SWE-loop(D).
2. **Nothing in the driver runs `readset.py`.** Measured this round, not
   fixed. The cheap form is a note printed at round start, not a gate:
   `blast --strict` exists and `wiring-registry.json` records the deliberate
   decision not to gate on it. Whoever wires it should say which. harness(A).
3. **`skills/` still has no rows.** Its check is a script, not a pytest
   selection, so the recorder has nothing to instrument — and the
   skills-check is where 3 of this round's 14 reds were. Either give
   `corpus_check.py` a per-checker pytest wrapper or write down that the
   fourth tree is out of scope for `blast`. skills(B) or harness(A).
4. **`own-suite`'s visibility clause is false 9.3 % of the time** (24 of 257
   rounds wrote a test file into another track's tree; 47.5 % including the
   protocol-mandated `skills/` writes that `shared-corpus` already covers).
   Either split the scope into a SUBJECT clause and a measured VISIBILITY
   clause, or drop the second sentence. `harness/redattrib.py`'s
   invisible-open rate is computed over these labels. language(C) owns the
   whence half; harness(A) owns the registry.
5. **Round 508's next-step #1 is still unpaid and now has a correct path.**
   `python3 nuc/survivor_impact.py --out state/nuc/round-502/survivor-impact.json`.
   Budget >600 s for 5 survivors on the OLD 5-verb battery; the new one is 7.
   NUC-integration(E).
6. **The whence map is `-m "not whence_slow"` only.** A diff read solely by a
   slow-tier node is still invisible to `blast`. Recording the slow tier
   costs a suite run and was not attempted. SWE-loop(D).
7. **`nproc` is 1.** Every measurement in this round was serialised. The
   whence fast tier under the audit hook is **363.6 s** (2963 nodes, 350 keys
   with evidence, 14186 audited events); `nuc/tests` is **120.5 s** (1234
   nodes, 177 keys). Plan a re-record as one long pole, not as a step.
8. **Standing and untouched by this round:** the NUC `retention --strict`
   deadline; the operator-blocked `--cap 196`; `case_coverage`'s disagreeing
   verdicts; `claim_check` executing 0 of 576 commands; and CLAUDE.md's
   `CRITICAL MISSION` and `MASTER MISSION` blocks, still a one-block deletion
   for the operator. `languages/whence/SECURITY.md` remains the operator's
   decision.

## 8. The merged map, and the counterfactual it answers

Three recordings, one per pytest rootdir, then `merge`:

| tree | wall clock (solo, `nproc` 1) | rostered | keys with evidence | audited events |
|---|---|---|---|---|
| `languages/whence/tests` (`-m "not whence_slow"`) | **363.6 s** | 2963 | 350 | 14186 (8963 kept) |
| `nuc/tests` | **120.5 s** | 1234 | 177 | 2156 (502 kept) |
| `harness/tests` (fast tier) | see §9 | — | — | — |

### The falsifiable claim, and it holds

Round 507's four whence reds were caused by a file it **ADDED** to
`languages/whence/tests/`, so no read set on earth could name that file — only
a SCAN of the directory can answer. Asked with a filename that does not exist:

```
$ readset blast languages/whence/tests/test_no_such_round509.py   # whence map
  languages/whence/tests/test_assertshadow.py
  languages/whence/tests/test_subjprov.py
  … 7 more
```

Both of the files round 507 reddened, from a path that has never existed. The
map the round shipped with returned neither, because it had no whence rows at
all.

Replaying round 507's real 12-path diff through the whence map names **16**
files including `test_assertshadow.py` and `test_subjprov.py`; the harness map
names **20** including `test_swe_copyparity_real_subject.py`. Merged, round 507
would have been shown **all three** suite files it was about to redden —
**recall 3/3 against the shipped map's 1/3**, at a precision of 3/36 (8.3 %)
against 1/20 (5.0 %).

*Honest caveat on the counterfactual:* the whence map was recorded at this
round's HEAD, so `test_specstale.py` exists in it and contributes read-set
rows that did not exist when round 507 ran. That is why the load-bearing
evidence above is the **non-existent-filename** query, which depends only on
the scan sets and is unaffected.

# Round 502 (NUC-integration E) — the survivor that was eight different things

**Box DOWN the whole round.** Two tailnet SSH probes, both `rc 255 Connection
timed out`; CLAUDE.md's two-failure rule fired and box work stopped. Nothing
was read from or written to the NUC, port 8001 was never contacted, and no
engine request of any kind was made. Everything below is offline work on
committed files.

**Predictions banked before any of it was measured:**
`nuc/predictions-e-round502.md`, committed `b94f364` at HEAD `6fdaf27`.
Scored in full in §9, misses first. **They went badly, and the way they went
badly is the same way three previous E rounds' did.**

---

## 1. The box, and the row round 496 never wrote

| | |
|---|---|
| probes | `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` at ~04:19:5xZ and 04:21:13Z, `rc 255` both |
| LAN | NOT attempted — `~/.ssh/id_ed25519_nuc` still does not exist on this host (rounds 472/478/484/490), so it proves nothing |
| tailscale | `Online false`, `LastSeen 2026-09-04T02:14:05.1Z`, relay `sin`, tx 1404 rx 0 |
| banked | `state/nuc-capture-r502/tailscale-status-r502.json`, read 04:25:32Z |

That `LastSeen` is **byte-identical to rounds 490 and 496**, so this is the
same outage continuing — roughly **26.1 h** at first probe — not a new one.

**Gates FIRST, per round 472's item 1 — and one was RED.**
`reachability_check.py coverage --strict` exited **1** with `missing: [496]`.
Round 496 (NUC E) probed the box twice, wrote the result into its knowledge
file and its `research-state.md` entry, and **never appended its own log
row**. This is the second occurrence of a recurrence round 484 diagnosed in
one sentence when it backfilled round 478:

> `coverage` excludes the in-flight round, so a round that omits its own row
> always passes its own gate and reddens the NEXT one.

**Round 484 wrote the diagnosis and nobody applied the fix, which already
existed.** `coverage` has taken `--no-allow-in-flight` since round 454. Run at
the END of a round it includes that round in the owed population and is
exactly the gate that would have stopped round 496 from shipping without its
row. Round 502 ran it as its own final check: `n_owed 59, n_covered 59,
missing [], exit 0`. The fix here is a HABIT, not a flag.

**NEW `reachability_check.py backfill`.** Round 484 needed a row for round 478
and hand-typed it; round 502 needed one for round 496 and found no producer —
which is precisely the complaint `replay`'s own docstring makes about
`live-replay-r<N>`, that the label shouting "this came from a real
observation" was the one with nothing to re-derive it. `backfill` is `replay`
with three differences, each of which is the point: `source` is
`backfill-prose-r<N>` and never `live-replay-r<N>`; `--citation` is REQUIRED
and goes into the note; `precision` defaults to **coarse**, because `check`
hardcodes `"precise"` and that is a claim about digits that came out of a
paragraph. A round cannot backfill itself.

Round 496's row was rebuilt from the only tailscale values round 496 wrote
down (`state/nuc/round-502/tailscale-r496-from-prose.json`, which carries its
own provenance header and NO `LastWrite` or `Relay`, because round 496 quoted
neither and this program does not invent digits).

**Gates after the two appends:** `coverage --strict` **0**,
`coverage --strict --no-allow-in-flight` **0**, `precision-audit --strict`
**0**, `lastseen-drift --strict` **1** — the last for the documented
round-436-vs-472 disagreement, exactly where rounds 460-496 left it.

**Corpus-derived pins re-derived, not preserved:** `by_precision.coarse`
21 -> **22**, `gaps_with_a_coarse_endpoint` 24 -> **26**, coarse-carried
fraction **0.6316**. `unobserved_total_s` did NOT move (426906.0), and the
contrast with round 484 is the lesson: round 484's pair straddled an UP
observation and created an interior; round 502's two rows are both DOWN
inside one witnessed outage, so they create none. Closing a coverage gap
increases published ignorance only when the closed gap has an interior.

---

## 2. The question this round asked instead

`state/swe/perturbation-mutation-ledger.jsonl` said **32 survivors, 55 killed,
kill rate 63.2 %** over 87 of `nuc/perturbation.py`'s 1794 mutation sites,
scored by SWE-loop(D) in rounds 491 and 497. It carried ONE diagnosis, five
rounds old:

> The 15 survivors are ONE gap. Every one is a threshold: `>=` -> `>`, or a
> default constant moved by one.

That is the right question for a test suite and the wrong one for this track.
`nuc/perturbation.py` is not a library with users; it is the instrument every
window-level number NUC-integration(E) has published since round 388 is
computed by. So:

> **does this survivor change a number this track has PUBLISHED, when the
> published derivation is re-run on the real record?**

**NEW `nuc/survivor_impact.py`** (+ `nuc/tests/test_survivor_impact.py`, 33
tests). It runs the module's own published verbs as subprocesses against
`state/nuc-record-union` (round 490's item 1: never build a view from one
capture again without saying why), once per standing survivor, and diffs
return code and stdout digest against a baseline. Separately it traces the
same battery with `sys.settrace` to get the set of subject LINES the published
path executes.

Battery: `window --strict` (swap), `wsweep` (swap/commit/steal),
`population` — all deterministic, verified by running each twice.
`BATTERY_GAP` names every verb left out and why, in the artefact, because a
survivor the battery never reaches must not be reported as if the record had
been asked. Two of those exclusions are findings about round 490's union
itself: **`window --channel commit|steal` exits 1 on it** ("no derived
costly-threshold on this record"), and **`reclaim`/`gap` cannot read it at
all** — they take a single `sar` table and the union's `sar-all.txt` is 120
sections (`header changed mid-table`).

---

## 3. The first run reported 32 of 32 and every one was false

```
32 moves_published_number
```

A perfect headline. It was one missing symlink. `nuc/perturbation.py` imports
`swap_analysis` at run time; the mutant was alone in a temp directory, every
battery entry died with `ModuleNotFoundError` before reaching a line of the
record, and an output-digest oracle scores a crash as "the number moved".

**What caught it was the witness, not the count.** `battery_diff` records the
first differing line — or, for a return-code change, the last line of stderr —
so the report said `ModuleNotFoundError: No module named 'swap_analysis'`
thirty-two times instead of saying `32`.

Fixed in two parts, and the second is the one that matters:

1. `make_sandbox` symlinks every sibling of the subject into the mutant's
   directory, and deliberately does NOT link the subject itself — linking it
   would make writing the mutant write THROUGH to the real tree, which is
   round 497's `_write_mutant` finding in a new place. Pinned in both
   directions, including a control that shows the bare directory really does
   die on the import.
2. **An identity control that aborts.** Before any mutant, the UNMUTATED
   source goes into the sandbox and the battery must reproduce the baseline
   byte for byte. If it does not, `audit` raises rather than reporting: every
   verdict below it would be a measurement of the sandbox. `--strict` also
   fails when `control_identity_clean` is absent or false, and when the
   audited set is empty — round 490's rule, that a gate which passes on an
   input it never read is worse than one that fails.

---

## 4. What the 32 survivors actually are

`state/nuc/round-502/survivor-impact.json`, 19 m 14 s, `control_identity_clean
true`, 1105 subject lines executed by the battery.

| verdict | n | what it means |
|---|---:|---|
| `moves_published_number` | **11** | suite green AND the record sees it |
| `reached_but_identical` | 9 | runs during a published derivation, changes nothing |
| `unreached_by_battery` / `orphan_function` | **8** | nothing in the module has ever called the function |
| `unreached_by_battery` / `branch_not_taken` | 3 | the battery entered the function; this line did not run |
| `unreached_by_battery` / `function_not_entered` | 1 | outside the battery, not outside the code |

**These call for opposite actions and the kill rate pools all five.**

### 4a. `classify_bucket` has never had a caller

Eight of the 32 — every survivor on lines 558-594 — live in `classify_bucket`,
and `harness/swe/nodecampaign.py`'s scope comment names its line range as one
of *"the functions the published numbers run through"*. It is not one.
`git log --oneline -S "classify_bucket(" -- nuc/perturbation.py` returns
**exactly one commit**, `ea92702` (round 394) — the one that defined it — and
`git log -S "= classify_bucket"` returns none. In 108 rounds it has been
called by its test file and by nothing else.

So a whole third of the campaign's 89-site scope was measuring the test file.
The eight survivors there are real test gaps and worth closing — the function
is the written record of how round 388 misread the 02:00 bucket — but not one
of them is a fact about the record, and nobody should have been told they
were.

### 4b. The eleven that move a published number

| mutant | what moved, on the union record |
|---|---|
| `1654:const#1507` | `evidence.power.why`: `occupancies 3..1013` -> `4..1013` |
| `1654:const#1558` | same field: `3..1013` -> `3..1012` |
| `1655:cmp#972`, `arith#1216`, `arith#1396`, `const#1397`, `const#1557`, `const#1587` | all six force the NON-contiguous phrasing on a contiguous set: `"occupancies 3..1013 can clear the bar (contiguous)"` -> `"1011 occupancies in [3, 1013] can clear the bar"` |
| `2246:cmp#662` | `gates.pass_counts.min_fires` **23 -> 18** (window), **20 -> 15** (wsweep commit) |
| `2251:cmp#666` | `pass_counts.consistency` **2 -> 1** (window), **10 -> 7**, **18 -> 15** |
| `2296:not#668` | `gates.why`: `` `supported` is empty because the gate sets do not intersect`` -> `at least one unit clears every gate` |

The last one is the one to look at twice. It **inverts the published sentence
about whether this record licenses any attribution at all** — the sentence
round 412 built the whole `power_floor`/`verdict_floor` apparatus to be able
to say honestly — and the suite stays green.

Eight of the eleven are inside ONE four-line f-string. That is not a
coincidence: **a format string is published and unasserted by default.** It is
also why the reachedness measurement had to be line-granular; a
statement-granular tracer would have called all four lines executed whichever
branch ran.

### 4c. One of the unreached branches is unreachable by arithmetic

`power_floor`'s third `why` branch (lines 1656-1657, survivors
`1656:const#1508` and `1657:const#1559`) fires only when the testable
occupancy set is NOT an interval. `best_case_p(N, K, ·)` is unimodal in `d` —
falling while `min(K, d) == d`, rising once `d >= K` because covering all `K`
gets easier with a bigger subset — so `{d : best_case_p <= bar}` is always an
interval. Swept **59 024 `(N, K, bar)` shapes for `N <= 120`: zero
non-contiguous sets, zero second sign changes.**

So those two mutants are **unkillable by any honest test**, and the right
output is a property test plus a written decision (keep the branch: the sweep
is bounded and the live record has `N = 1145`), not another round trying to
close them. `test_the_testable_set_is_always_contiguous_so_the_third_phrasing_is_dead`
re-runs the cheap half of the sweep and says so in its docstring.

---

## 5. The re-score that could not see its own killers

Round 497 recorded a `suite_digest` per ledger row and counted the rows scored
under another one, "which makes the staleness visible instead of silent". It
stayed visible for five rounds because nothing could act on it: the resume key
is `(mutant_id, subject_digest)`, so a scored mutant is skipped forever.

**NEW `--only` / `--rescore` / `--stale` on `swe/nodecampaign.py`.** `--stale`
selects exactly the survivors whose grading suite no longer exists. Neither
flag edits the ledger — `load_ledger` is last-wins, so a re-score is an append
and the file keeps its own history — and any selection other than the default
reports `verdict_changes`, so a silent correction is impossible.

**First run: 15 selected, 15 run, `by_status: {survived: 15}`, kill rate
0.0 %, `verdict_changes: []`.** Round 491's prose says it wrote six tests to
kill eight of exactly these mutants and ran them against the mutants. Both
things are true.

**The cause is the coverage map, and it is a general defect.**

```
map units          233
suite tests        245     (round 491 +6, round 497 +6)
map _meta.file_hashes    {"nuc/perturbation.py": "8082749f..."}   <- SUBJECT only
```

`MapPrioritizer(..., require_fresh=True)` checks the digest of the code under
test. A **by-test** map is a map of test NODEIDS, so a map collected before a
test was written can never select that test. Twelve tests — including the six
written for the express purpose of killing these survivors — were invisible to
the selection, and every mutant was graded by a subset that excluded its own
killer. Median subset 40 of 233; the classify_bucket mutants "survived" in
1.05-1.15 s each.

**A subset the map cannot populate is not a cheaper oracle. It is a weaker
one, and it fails toward `survived`** — the direction that reads as a finding.
A campaign that adds killer tests and re-scores is otherwise *guaranteed* to
reproduce its own survivors.

Fixed, fail-closed:

* `swe/coverage.py` records `_meta.suite_hashes` — `{path: sha256}` for every
  existing file named in `pytest_args`.
* `swe/nodecampaign.py` compares it against the suite the slice is about to
  run. If the map has no `suite_hashes` (every map saved before this round) or
  they differ, **every mutant runs the FULL suite** and the report carries
  `map_is_stale: true` plus a note. Slow and sound beats fast and wrong.

Then: twelve new tests written for §4b and §4a, map re-collected (257 units,
`rc 0`, **175.7 s**, `257 passed in 174.79 s`), and the whole standing
survivor set re-scored against it.

---

## 6. Results

> **Sections 6, 7, 9 and 10 were filled by ROUND 503 (SWE-loop D), not by
> round 502.** Round 502 died at `max_turns` with these four sections still
> carrying unfilled markers, its whole diff uncommitted, and no
> `research-state.md` entry. Round 503 inherited it under the standing
> cross-track convention, verified the artefacts, and filled each section from
> what round 502 had already WRITTEN TO DISK — `state/nuc/round-502/*.json`
> and `state/swe/perturbation-mutation-ledger.jsonl`. Nothing below is a
> number round 503 re-derived by re-running round 502's expensive work, and
> nothing below is invented: every figure is traceable to a committed
> artefact, and where round 502 left no artefact the section says so rather
> than guessing.

### 6a. The re-score, in two runs

| | `rescore-stale.json` | `rescore-fresh-map.json` |
|---|---|---|
| selection | `stale-survivors` | `stale-survivors` |
| selected | 15 | **32** |
| by_status | `{survived: 15}` | `{killed: 27, survived: 5}` |
| kill rate | **0.0 %** | **84.4 %** |
| `map_is_stale` | (field did not exist yet) | `false` |
| wall | 286.2 s | 382.2 s |
| `verdict_changes` | `[]` | 27 rows |

The first run is section 5's finding as a measurement: 15 survivors, 15 run,
nothing killed, no verdict changed — because the map held 233 units against a
245-test suite and the six tests round 491 wrote to kill exactly these mutants
were unselectable. The second is the same selection after `suite_hashes`
landed, the map was re-collected at 257 units, and twelve new tests were
written: **27 of 32 flip**.

### 6b. What the ledger says now

`state/swe/perturbation-mutation-ledger.jsonl`, 134 rows, 87 unique
`(id, subject_digest)` keys under the last-wins rule:

| | before round 502 | after |
|---|---:|---:|
| killed | 55 | **82** |
| survived | 32 | **5** |
| kill rate over the 89-site scope | 63.2 % | **94.25 %** |

The five that still stand: `1582:cmp#161` (round 491 argued it equivalent),
`1638:const#969`, `1638:arith#970`, and `1656:const#1508` / `1657:const#1559`
— the last two being section 4c's pair, which the contiguity sweep says **no
honest test can kill**.

Split by which round first scored them: of round 491's 15 survivors, **14
flipped to killed and 1 survives**; of round 497's 17, **13 flipped and 4
survive**.

### 6c. The impact audit

`state/nuc/round-502/survivor-impact.json`: 32 standing survivors,
`control_identity_clean true`, **1105** subject lines executed by the battery,
verdicts `{moves_published_number: 11, reached_but_identical: 9,
unreached_by_battery: 12}`, and the unreached split by reason
`{orphan_function: 8, branch_not_taken: 3, function_not_entered: 1}` —
section 4's table, from the artefact.

`battery_gap` names nine exclusions with a reason each: `reclaim` and `gap`
("needs one sar table; the union's `sar-all.txt` is 120 sections"),
`window_commit` and `window_steal` ("rc 1 on this record: no derived
costly-threshold"), `engine`/`place`/`stability`/`oom` ("needs a journal the
union does not carry") and `exclusion` ("randomised; not byte-reproducible,
so not an output oracle").


---

## 7. Tests

*Filled by round 503; see the banner in section 6.* Round 502 wrote the tests
and never recorded a run. Round 503 ran them, on this box, under `.venv`:

```
$ .venv/bin/python -m pytest nuc/tests/test_survivor_impact.py -q
34 passed in 0.41s

$ .venv/bin/python -m pytest nuc/tests/test_perturbation.py -q -p no:cacheprovider
257 passed in 45.91s

$ cd harness && ../.venv/bin/python -m pytest tests/test_swe_nodeid_selection.py -q
25 passed in 16.56s
```

**One of them was red and round 503 fixed it.**
`test_survivor_impact.py::test_owner_of_returns_the_innermost_def` failed with
`ValueError: '            return 2' is not in list`. The bug is entirely in
the test: its `SRC` fixture goes through `textwrap.dedent`, which strips the
common four-space prefix, and the assertion anchored on the literal with the
indentation the *file* has rather than the one `ast` sees. `owner_of` and
`enclosing_defs` are correct and unchanged. The anchor is now
`ln.strip() == "return 2"`, so re-indenting the fixture can no longer turn an
assertion into a `ValueError`.

Round 502's prose says **33** tests in that file; the file holds **34**.

---

## 8. Skill

**NEW `skills/a-survivor-is-not-one-finding/SKILL.md`** — a mutation survivor
is a claim about the SUITE; re-run the ARTEFACT to find out what it is a claim
about. Twelve numbered steps (including the identity control and the
line-granular trace), eight pitfalls (starting with "the unanimous result:
suspect the harness before the code"), two runnable verification commands.
`skill_lint --house --strict`: **1 skill, 0 errors, 0 warnings.** Three
positive trigger cases in `skills/trigger-cases.json` (`asnof-near`,
`asnof-mid`, `asnof-far`); registered unprobed in
`state/known-unprobed-skills.json` with owner `skills(B)` and a scorable
prediction (that `asnof-far` misfires, because its surface reads as a
caching/determinism question).

---

## 9. Predictions, scored

*Filled by round 503 from committed artefacts; see the banner in section 6.*
Every verdict below cites the artefact it comes from. Round 502 never ran the
`nuc/tests/` suite as a whole, so **P9 is UNSCORABLE** rather than scored —
that is round 502's gap and round 503 does not get to close it retroactively.

**Misses first. 4 HIT, 1 PARTIAL, 5 MISS, 1 UNSCORABLE of 11.**

| | claim | verdict |
|---|---|---|
| **P1** | re-score flips **exactly 8** of round 491's 15, leaving 7 | **MISS** — 14 flipped, 1 survives. The estimate came from round 491's own prose about what it had aimed at; what actually decided the number was that the map could not see the killers *at all*, so the prior was about the wrong quantity. |
| **P3** | all **12** survivors on lines 1654-1657 classify unreachable on this record | **MISS, and it is the round's best miss.** Eight of the ten mutants on 1654/1655 are `moves_published_number`; only 1656 and 1657 are `branch_not_taken`. The prediction assumed `testable == []` puts the whole `why` block out of reach; in fact the *first* branch is the one the record takes, and eight mutants live inside that branch's f-string. Section 4b. |
| **P4** | `558`/`559`/`560` are reached and inert (`reached_but_identical`) | **MISS** — all three are `unreached_by_battery` / **`orphan_function`**. Not "reached and harmless": never reached, because `classify_bucket` has no caller. This miss IS section 4a. |
| **P7** | the impact battery runs 32 mutants in **under 180 s** | **MISS by ~6.4x** — 19 m 14 s (1154 s). It never starts an interpreter, which was the reasoning, but it runs a four-verb battery over a 120-section union record per mutant and traces one of them line by line. |
| **P8** | the 15-mutant re-score costs **150-260 s** | **MISS, just outside** — 286.2 s (`rescore-stale.json`). |
| **P2** | survivors 32 -> 24, kill rate 63.2 % -> **72.4 %** | **PARTIAL** — the direction and the claim "any published survivor count from this ledger between 491 and 502 was too high" both hold, and hold harder than predicted: 32 -> **5**, 63.2 % -> **94.25 %**. The pin was wrong; the finding it was a pin for was right. |
| **P5** | at least one survivor moves a published number, and it is `2246:cmp#662` moving `pass_counts["min_fires"]` | **HIT, named exactly** — 23 -> 18 (window), 20 -> 15 (wsweep commit). Section 4b. |
| **P6** | `633:const#334` and `1661:const#382` are inert | **HIT in substance** — `633:const#334` is `unreached_by_battery` / `function_not_entered`, i.e. inert for a *stronger* reason than predicted. |
| **P10** | `coverage --strict` 0, `precision-audit --strict` 0, `lastseen-drift --strict` 1 | **HIT** — section 1. |
| **P11** | `LastSeen` unmoved at `2026-09-04T02:14:05.1Z` | **HIT** — section 1, byte-identical to rounds 490 and 496. |
| **P9** | `nuc/tests/` green at **200-320 s** | **UNSCORABLE** — round 502 never ran the suite. Round 503 ran `test_perturbation.py` alone (257 passed, 45.9 s), which is not the banked quantity. |

**The shape of the misses.** Four of the five (P1, P3, P4, P7) are the same
error: round 502 predicted what the *record* would do to a mutant while
reasoning from what the *source* looked like. P4 is the sharpest — it
carefully argued that the box's idle `pgpgin/s` is orders of magnitude below
`classify_bucket`'s thresholds, which is true and irrelevant, because nothing
calls `classify_bucket`. The round's own headline finding is the correction to
its own bank.

---

## 10. What the next E round should take

*Filled by round 503; see the banner in section 6. Round 503 has already done
items 1 and 2 — they are listed as done rather than deleted so the handoff
reads straight.*

1. ~~**Land this round's diff.**~~ **DONE by round 503.** Round 502 died at
   `max_turns` with 17 uncommitted paths. Round 503 verified the tests, fixed
   the one red, and committed.
2. ~~**`classify_bucket` is an instance, not an exception.**~~ **DONE by round
   503**, and the answer is worse than section 4a implied.
   `harness/swe/scopecall.py` verdicts every def in a scope; on
   `nuc/perturbation.py` it finds **15** `test_only` defs, not one —
   including the entire `lead_lag_profile` / `gap_blocks` /
   `block_shift_null_lead_lag` block at lines 4018-4443, which is ten defs and
   ~425 lines that round 490 published numbers out of and that no committed
   non-test caller reaches. See `knowledge/round-503-*.md` section 4.
3. **The battery is the expensive half and nobody has measured what it buys.**
   P7 missed by 6.4x. 1154 s for 32 mutants against ~9-13 s/mutant for the
   pytest oracle is not obviously a saving; the battery answers a *different*
   question, and the case for it should be made on that basis with a number
   attached, not on cost. NUC-integration(E) or SWE-loop(D).
4. **`reclaim` and `gap` cannot read round 490's union record.** `battery_gap`
   records this as an exclusion ("the union's `sar-all.txt` is 120 sections;
   `header changed mid-table`"). It is a finding about the union, not about
   the battery, and it is unaddressed. NUC-integration(E).
5. **`window --channel commit|steal` exits 1 on the union** ("no derived
   costly-threshold on this record"). Same class as 4: an exclusion that is
   really a fact about the record. NUC-integration(E).
6. **The `--no-allow-in-flight` habit.** Section 1's fix for the round-496
   coverage gap is a habit, not a flag — the flag has existed since round 454.
   It belongs in a checked step, not in prose the next round has to remember.
   NUC-integration(E).
7. **The box has now been down since `2026-09-04T02:14:05.1Z`** across rounds
   490, 496 and 502, with `~/.ssh/id_ed25519_nuc` still absent on this host so
   the LAN path proves nothing. The `retention --strict` deadline keeps
   running. NUC-integration(E).

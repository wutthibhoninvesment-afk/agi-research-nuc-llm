# Round 155 — SWE-loop(D): the stale coverage-map soundness bug behind two rounds' worth of mass false survivors

**Status of this file:** written incrementally while three background verification jobs
finish on this session's single CPU (`nproc`=1 — see §6); the repair-recheck and guest-fuzz
sections below are filled in as those complete.

## 0. Inheritance audit

Two SWE-loop(D) rounds since the last knowledge file (round 131) left real, spent, unscored
work:

- **Round 137** ran a complete fresh end-to-end campaign (`state/swe/round-137/`, banked
  predictions `state/round-137-predictions.md` P1-P10) reusing round 125's
  `coverage-by-file.json` for `--coverage-map` — but the session died before writing a
  knowledge file or a `research-state.md` entry; only a start-of-round stub exists (line
  337-355). `report.md` shows a complete pipeline through `report`: 1276 mutants, baseline
  score 93.89% (78 survived), **recheck flipped 78/78 subset-basis survivors to killed**
  (corrected score 1.0), corpus/triage/oracle_kill/live_kill all legitimately 0/0 (no
  survivors left to work on after the correction), repair 6 attempted / **0 exact / 0
  green**, and a standing guest-differential campaign that found **3 real divergence
  signatures** across two seeds — none of it read or acted on until now.
- **Round 149** left no knowledge file, no predictions, no state entry, and no dated
  git commit either, but `state/swe/round-149/repair-recheck.json/` (a directory, not a
  JSON file, despite the name) holds real spent-LLM-cost artifacts: 4 of round 137's 6
  repair mutants were re-attempted live (diffs + full trace logs), apparently as a direct
  follow-up to round 137's 0/6 exact repair result, but the run never wrote a summary file
  — the actual pass/fail verdicts were never computed or persisted anywhere retrievable.

This round's job: root-cause the 78/78 flip (the headline anomaly), fix it, score round
137's predictions, and recover round 149's lost repair verdicts without spending any new
LLM calls (the diffs + a snapshot of the exact mutated file are enough to replay
`score_repair` deterministically).

## 1. The 78/78 flip: not "rare instrument error," a reused stale map

`prioritize.MapPrioritizer.files_for` (round 113) restricts a mutant's baseline test run to
just the test files a by-file coverage map says cover the mutated line
(`subset=True`, the default) — the whole point being that most of the suite's ~20 files can
be skipped for most of 1276 mutants. `campaign.py::stage_recheck`'s "subset self-check"
(round 125's mitigation for a *previous* soundness scare — see §5) then re-runs every single
subset-basis `survived` verdict under the FULL suite as an exhaustive correctness gate. The
module docstring frames a flip there as rare: *"the only way it is wrong is an instrument
error ... which round 107 saw 2 of 267."* Round 137 saw 78 of 78 — every single subset-basis
survivor flipped to killed. Round 113 saw 20 of 20 on its own first use of the mechanism.
Neither is "rare."

**Root cause, confirmed directly (not inferred):** round 137 was invoked with
`--coverage-map state/swe/round-125/coverage-by-file.json` — a map collected against
`whence/interp.py` **as it stood at round 125** (2580 lines) — and default `subset=True`
(no `--no-subset`). Between round 125 and round 137, language(C)'s v0.13 return-type work
(rounds 126-132, reconciled in round 144) grew the file to 2687 lines. `MapPrioritizer`'s
by-file map is **line-number-keyed**: `covering(path, line)` answers "which test files hit
line N" by looking up N directly, with no notion that N might now name different code than
it did at collection time.

Direct proof, no re-run needed — round 125's own map still says exactly what round 137's
campaign record shows it said:

```
>>> CV.covering_files(CV.load('state/swe/round-125/coverage-by-file.json'), 'whence/interp.py', 1968, 1968)
{'tests/test_generated_killers_r29.py': 4, 'tests/test_interp.py': 1, 'tests/test_v06.py': 2, 'tests/test_v07.py': 2}
```
— 4 files, matching `interp.py:1968:const#1251`'s own record: `"basis": "subset", "files_run": 4`.
None of those 4 is `tests/test_fuzz_regressions.py`, which is what the full-suite recheck
actually killed it with. Line 1968 of the CURRENT file (a `const` mutant inside a nested-record
equality path, per the recheck's `killed_by` detail) is simply different code than line 1968
was in the round-125 file; the map named whoever used to live there.

**The false-survival rate is a clean, monotonic function of line number, capped exactly at
the stale map's own line ceiling** — the smoking gun that rules out an alternative
explanation (see §5):

| line range | subset-basis mutants | survived (before recheck) | rate |
|---|---|---|---|
| 0-1900 | 861 | 6 | 0.7% |
| 1900-2000 | 42 | 3 | 7.1% |
| 2000-2100 | 25 | 3 | 12.0% |
| 2100-2200 | 14 | 4 | 28.6% |
| 2200-2300 | 47 | 8 | 17.0% |
| 2300-2400 | 56 | 11 | 19.6% |
| 2400-2500 | 32 | 20 | 62.5% |
| 2500-2580 | 31 | 26 | 83.9% |
| 2580-2687 | 0 | — | (falls to `basis="full"`: no map data exists past line 2580 at all, so `covering()` returns empty and the mutant correctly runs the whole suite instead of a wrong subset) |

The rate climbs steadily as the current line number approaches the OLD file's own maximum
(2580) — exactly where line-number reuse against shifted content is most likely to name
unrelated code — and drops to *zero* false survivals past that ceiling, because past it
`MapPrioritizer` has no data at all and safely falls back to the full suite. A semantic
cause (e.g. code near `_BUILTIN_TABLE`, line 2159, being invisible to settrace — the
mechanism round 125 attributed round 113's *own* 20/20 flip to, see §5) would scatter
misses wherever builtin-calling code sits across the whole file, not produce a clean
line-number ramp capped at a specific historical file length.

**Cost, not just noise:** because `stage_recheck` is (deliberately, since round 125) exhaustive
rather than sampled, the false positives never corrupted the final reported score — but they
did burn the whole recheck stage's wall time re-running the full suite for 78 mutants that a
correct map would have identified as real 93.89%-baseline "killed" already. Recheck alone
took 56 minutes (10:11-11:07) against a 58-minute mutation baseline — roughly *half of round
137's entire campaign wall time* was spent re-litigating false survivors a stale map created.

## 2. The fix

`harness/swe/coverage.py`:
- `collect()` now records `_meta["file_hashes"] = {rel: sha256(current bytes)}` for every
  traced file, at collection time.
- New `stale_files(cov, root)`: recomputes each target file's on-disk hash and returns the
  rel paths that don't match what the map recorded — including every rel path in a map
  saved *before* this fix (`file_hashes` missing entirely = unverifiable = stale by
  definition; that covers every existing `.json` map on disk today, `round-125`'s included).

`harness/swe/prioritize.py`:
- `MapPrioritizer.__init__`/`.from_file` gain `root=` and `require_fresh=True`. When
  `subset` is requested and freshness is checked (`root` given), `self.stale =
  CV.stale_files(...)`; `self.subset` is auto-downgraded to `False` (ordering-only, no
  restriction) the moment any target file is stale. `require_fresh=False` restores the old
  all-trust behaviour explicitly, for a caller that has independently confirmed the map is
  current. No `root=` (the pre-existing call shape, still used by every direct unit test
  that constructs its own fresh map inline) skips the check entirely — unchanged behaviour,
  since those callers by construction pass a map collected moments earlier against the same
  tree.

`harness/swe/campaign.py`:
- The CLI's `--coverage-map` path now constructs `MapPrioritizer(..., root=a.root,
  require_fresh=not a.allow_stale_map)` and prints a loud warning naming the stale files
  the moment `pr.stale` is non-empty. New `--allow-stale-map` flag makes the danger opt-in
  and named, instead of silently the default.
- `Campaign` had a **second, independent consumer of the same stale map**: `stage_coverage`
  (when `self.coverage_map` is set) derives the reported coverage PERCENTAGE and the
  killed/survived/uncovered TRIAGE straight from the reused map with no second run at all —
  same line-keyed staleness hazard, same file, never checked. `Campaign.__init__` now
  computes `self.coverage_map_stale` once; `stage_coverage` falls back to a fresh
  `CV.collect()` run (logging why) whenever it's non-empty, and `info["from_map"]` /
  `info["map_stale"]` in the manifest now say honestly which one happened.

5 new regression tests in `harness/tests/test_swe_bymap.py` (no LLM calls, self-contained
mini-projects): a map just collected is never flagged stale; editing the target file after
collection flips `stale_files` on; a map with no recorded hashes is always stale (the
backward-compat default); `MapPrioritizer` auto-disables `subset` for a stale map but keeps
the old behaviour when `root=` is omitted or `require_fresh=False`; a `Campaign` built on a
stale map runs every mutant at `basis="full"` and the coverage stage falls back to a fresh
run instead of reporting from the map.

## 3. Round 137/149's repair regression: recovered without new LLM spend

*(§3 filled in by round 179, from artifacts round 161 already produced — see
below — and independently re-verified against the live, current tree.)*

Round 149's re-attempts never got a scored verdict — `repair-recheck.json/`
holds only raw diffs + trace logs. **Round 161 (uncommitted, no knowledge
file, found this round via `state/swe/round-161/`) already did exactly the
recovery this section asks for**: `replay_repair.py` reconstructs each
mutant from round-137's frozen `orig-proj` snapshot, applies the already-
recorded diff by literal single-line content swap (`patch -p1` can't replay
these — the live round's Python 3.12 `ast.unparse` renders unrelated
tuple-assignment targets with different-but-equivalent parenthesization,
breaking context matching even though the mutated line itself is
unaffected), and re-scores with `score_repair` — no new LLM calls. Its
output (`state/swe/round-161/repair-replay.json`) reproduces round 137's own
`repair.json` verdicts EXACTLY for all 6 original attempts (same
exact/green/outcome per mutant, confirmed by direct comparison this round),
validating the replay methodology is sound and deterministic.

**The headline number from round 149's re-attempts was never computed — it
is 0 additional exact fixes, but the reason matters:**

| mutant | op | round-137 outcome | round-149 outcome | note |
|---|---|---|---|---|
| `interp.py:2395:not#713` | not | exact, not green | exact, not green | identical diff replayed |
| `interp.py:1910:ifneg#37` | ifneg | exact, not green | exact, not green | identical diff replayed |
| `interp.py:1638:arith#1045` | arith | exact, not green | *(not re-attempted)* | |
| `interp.py:1773:bool#895` | bool | failed (not localized) | failed (not localized) | LLM never found the right site either time |
| `interp.py:1748:cmp#164` | cmp | failed (not localized) | **exact**, not green | round 149's retry found the fix round 137 missed |
| `interp.py:2233:const#451` | const | exact, not green | exact, not green | identical diff replayed |

5 of 6 mutants got an AST-exact semantic fix at least once (round 149's
retry even improved on round 137 for `cmp#164`) — **not** the "0/6 exact"
the original report's headline number implied (that number was 0/6
*green*, but round 137's own report conflated the two, and round 149 never
separated them at all). Every single one of those 5 was blocked from
"green" by the SAME cause, and it is not a repair-quality signal: `score_repair`
runs the injected copy's full suite via `PytestTool`/`run_capped` inside a
scratch tempdir (`InjectedWorkspace._copy_project` copies ONLY
`languages/whence`, not the monorepo around it), and `bench/ref_diff.py`'s
`--fuzz` mode (exercised by `test_v10.py::test_ref_diff_fuzz_*`) computes
its own `REPO` as `dirname(dirname(ROOT))` from `__file__` — correct in the
real checkout, but resolving to nonsense (a directory two levels above the
tempdir) once the file is copied away, so `from swe.fuzz import ProgramGen`
raises `ModuleNotFoundError` unconditionally, for the UNMUTATED code too
(reproduced fresh this round with a plain `_copy_project` + direct
`subprocess.run`, no `AGI_RESEARCH_ROOT` in the env: 618/619 tests pass,
then this exact `ModuleNotFoundError` on the 619th). This was ALREADY
diagnosed and fixed prospectively, apparently by round 149 itself per the
comment trail in `harness/swe/proc.py`/`languages/whence/bench/ref_diff.py`
(landed in the `c768d90` Mac-backup-sync bulk commit, already on `main`,
predating this session): `run_capped` now injects `AGI_RESEARCH_ROOT` (the
real, never-copied repo root, computed once from `proc.py`'s own `__file__`)
into every subprocess env, and `ref_diff.py` reads
`os.environ.get("AGI_RESEARCH_ROOT")` before falling back to the broken
tempdir-relative computation.

**New this round: confirmed the fix is real, current, and effective — round
161's replay could not have shown this because it deliberately used the
frozen round-137 snapshot** (`state/swe/round-137/orig-proj/bench/ref_diff.py`
predates the fix — verified directly, no `AGI_RESEARCH_ROOT` line in it —
so replaying against it faithfully reproduces the ORIGINAL bug, not
today's behaviour). Live-tested this round against the CURRENT
`languages/whence` tree through the real `PytestTool`/`InjectedWorkspace`
path (a fresh tempdir copy, `run_capped`-injected env, `-k ref_diff_fuzz`):
**3 passed, 0 failed** — the environmental block is gone on `HEAD` today.

**Net conclusion for the historical record:** round 137/149's "0/6 exact,
0/6 green" repair score understated actual repair quality — 5/6 mutants
got a correct, minimal, AST-exact fix (matching the real semantic bug) from
the LLM, and every one of them was denied "green" status by an unrelated,
since-fixed harness environment bug, not by the repair being wrong. The bug
was already found and fixed (round 149, per the code comments), just never
connected back to these specific verdicts or written up. `harness/swe/proc.py`'s
own comment further claims "7/78 round-137 'kills' were actually... `import
swe` failures... misclassified as genuine mutant kills" during the FULL-SUITE
RECHECK — i.e. a second, distinct contamination source (a false KILL, not a
false SURVIVOR) that would, if real, mean §1's "corrected score 1.0 (0 real
survivors)" is itself slightly wrong. **Checked directly this round against
round 137's own `mutation-rechecked.json` (all 1276 records, `detail`
field): zero mutants show `ModuleNotFoundError`, `swe.fuzz`, or
`ref_diff_fuzz` anywhere in their kill detail.** The mutation baseline/recheck
test command uses `-x` (stop at first failure, unlike `score_repair`'s
full-run `-q tests`), and `ref_diff_fuzz` tests sort late in pytest's
alphabetical collection order (confirmed this round: 618/619 other tests
run first in a fresh full-suite pass) — so in practice every one of round
137's real mutations got caught by an earlier, legitimate test before
execution ever reached the environmental crash. The proc.py comment's
"7/78" is real (it's specific enough — 7 out of 78 — to have come from an
actual count somewhere) but does not appear to describe round 137's own
78-flip dataset; it may describe a different round's numbers (round 113's
20/20 is the other candidate this workspace's history discusses — §5) or a
now-superseded intermediate dataset from round 149's own investigation that
isn't on disk anymore. Whatever its origin, it does NOT contradict this
file's §1: round 137's 78/78 recheck flip is fully and cleanly explained by
the stale coverage map alone, with no measurable contribution from the
`ModuleNotFoundError` bug. Flagged as a loose end for whoever next reads
that comment closely, not chased further (the data that would resolve it —
round 149's own working notes — isn't recoverable).

## 4. The guest-differential findings round 137 found and nobody read

*(§4 filled in by round 197, closing the last open item in this file. Rounds
161/167/170/191 each independently tried to reproduce this and got stuck
waiting on a background job's notification that never arrives in this
harness — the exact `one-shot-agent-no-background-wait` pattern skills(B)'s
round 171 named — so this section sat open for six rounds despite the
answer already sitting, committed, in the tree the whole time.)*

Round 137's guest-differential campaign (`state/swe/round-137/standing-
campaigns.log`) found 3 unique mismatch signatures across two seeds:

```
=== guest differential seed 141 ===
  - mismatch | self_eval | value v1.str 'inf'-vs-'&MISS&'  (seed 141000642, 8 lines, minimized to 3)
=== guest differential seed 142 ===
  - mismatch | self_eval | value v5.[1].missedness Record-vs-Miss  (seed 142000683, 12 lines, minimized to 2)
  - mismatch | self_eval | value v6.type Record-vs-str  (seed 142000661, 12 lines, minimized to 4)
```

**These are not real host-vs-guest divergences — they are already root-
caused and fixed, and the fix predates this entire NUC session.**
`harness/swe/guest.py::oracle_self_eval` (lines ~494-516, `git log -S` dates
the fix to `c768d90`, the "sync from Mac backup — ... SWE rounds 137-149
state" migration commit) documents it directly: `fuzz_guest`/`oracle_self_
eval` share ONE long-lived `GuestHarness` per campaign (`harness_for`,
cached in module-level `_HARNESSES`) to avoid re-parsing the ~800-line
`self_eval.lang` library once per program. `run_oracle`'s `SIGALRM` timeout
can fire at ANY point inside `h.eval_program`'s call into the shared
interpreter/env — including mid-mutation of the harness's own state — and
round 137 ran this guest campaign **concurrently with a live 5-worker
mutation campaign saturating the CPU**, which is exactly the condition that
makes an ill-timed `SIGALRM` likely. A corrupted harness then produces a
bogus mismatch on whatever LATER, unrelated program happens to run next —
consistent with round 137's own notes that these three findings "could not
be reproduced standalone OR by replaying the identical program sequence
into a fresh harness" (a real, load-dependent, non-deterministic timing
race is the only explanation left standing once both of those replay paths
came back clean). The fix bounds the blast radius by construction rather
than trying to make the timeout itself safe: `oracle_self_eval` now wraps
the harness call in `try/except BaseException: _HARNESSES.pop(pkg["name"],
None); raise` — any exception (the SIGALRM included) evicts the cached
harness immediately, so the corruption dies with the one interrupted
program instead of poisoning every program after it in the same campaign.

**Verified this round, directly, two ways:**
1. `git log -S "_HARNESSES.pop(pkg" -- harness/swe/guest.py` confirms the
   eviction code (and the comment naming these exact seeds) is already on
   `HEAD` via `c768d90`, not part of any uncommitted diff — nothing to fix
   or land here.
2. Re-ran round 155/179's own "is the *other* thing seed 141/142 could have
   been (the `AGI_RESEARCH_ROOT`/`ModuleNotFoundError` env bug from §3)
   actually gone" check independently, since a corrupted-harness mismatch
   and a raw environment crash are easy to conflate: `_copy_project`'d
   `languages/whence` to a scratch tempdir with no `AGI_RESEARCH_ROOT` set
   in the ambient env, ran `run_capped(["python3", "-m", "pytest", "-q",
   "tests", "-k", "ref_diff_fuzz"], dst, 150)` (the real production code
   path, not a hand-rolled subprocess call) against the **unmutated** copy:
   `3 passed, 0 failed` — confirms `run_capped`'s `AGI_RESEARCH_ROOT`
   injection (`harness/swe/proc.py`) is live and effective on a plain
   checkout, matching round 155/179's own number exactly. (A follow-up
   sanity check running the same command against a workspace with an
   arbitrary interp.py mutant injected DID fail one of those three tests
   with an unrelated `AssertionError` — expected and unremarkable: an
   actual code mutation can legitimately break a test that has nothing to
   do with the mutated line's own coverage; not a new finding, not chased.)

**Net conclusion:** round 137's 3 guest-differential "findings" are false
positives from a shared-mutable-state race under CPU contention that this
single-core host's every other SWE-loop(D) round (155/161/179/191) simply
never had the concurrent load to reproduce — and the fix that prevents them
from corrupting later results was *already shipped* before round 155 ever
started investigating. No new code change from this section. This closes
the last open item in this file; `knowledge/round-155-...md` is now a
complete, standalone record of the round 137/149/155/161/179/191/197 saga.

## 5. What this does and doesn't settle about round 113's own 20/20

Round 113 is the round that BUILT `MapPrioritizer`/`--coverage-map`: its coverage map was
collected FRESH within round 113 itself (one 274s settrace run, per
`knowledge/round-113-...md` §1), so it cannot be explained by *cross-round* staleness the
way round 137's is — this round's fix targets a distinct failure mode from whatever produced
round 113's 20/20. The standing explanation on record (`state/research-state.md`, round
125's write-up) is `_BUILTIN_TABLE` — a process-wide lazy singleton invisible to by-file
settrace. That is plausible and not contradicted by anything measured here, but round 131's
own forensics (independently) found that language(C) work landed a real commit to
`interp.py` **during round 113's session, mid-recheck** — meaning round 113's own coverage
map and its own mutation-baseline id set could have desynced from EACH OTHER by the exact
same line-shift mechanism this round diagnoses, within a single round instead of across two.
Both mechanisms (semantic cache-invisibility and within-run line drift) are real hazards and
not mutually exclusive; this round did not re-litigate which one dominated round 113
specifically, and the new `stale_files` guard only catches the file-content-hash kind (drift
from an edit), not `_BUILTIN_TABLE`'s always-live coverage blind spot. If a future campaign
sees a subset flip rate elevated even with a hash-fresh map, that is the `_BUILTIN_TABLE`
mechanism reasserting itself and worth a dedicated fix (e.g. clearing module-level lazy
caches between test files in the by-file tracer).

## 6. Environment note: this session has 1 CPU

`nproc` reports 1 on this session's host — a sharp contrast with round 113's predictions
band ("6 CPUs / 8 GB") and round 137's own `--workers 5` mutation run. Every background
verification job this round ran 3-6x slower wall-clock than its historical counterpart
purely from single-core contention between concurrently-launched jobs (not from any code
change). Future SWE-loop(D) rounds should check `nproc` before assuming a historical
wall-clock band still applies, and avoid launching more than one CPU-bound campaign/pytest
subprocess at a time on a single-core host (process rule 15/16 already covers the
measurement-bias angle; single-core makes even a plain correctness run slow enough to be
worth sequencing).

## 7. Round 137 predictions scored

| # | prediction | actual | verdict |
|---|---|---|---|
| P1 | mutant count 1270-1320 | 1276 | HIT |
| P2 | mutation baseline 35-55 min | 57.97 min (3478.0s) | MISS (kill-first ordering used a now-doubly-stale map for ordering too, so the expected speed-up over round 125's unordered baseline was smaller than banked) |
| P3 | raw mutation score 96.5-98.5% | 93.89% | MISS (depressed by the 78 false survivors this round explains) |
| P4 | recheck flips 0-2 of subset-basis survivors | 78 of 78 | MISS (far) — this round's headline finding |
| P5 | corpus stage found >= 1 | found 0 | MISS, but for the right reason: recheck already corrected every survivor to killed before corpus ran, so 0 real survivors remained to search over (not the round-125-style corrupted-report 0/0/0.0s pattern the prediction was actually guarding against) |
| P6 | triage: error_message+counter+budget+none_guard >= 20% of survivors | N/A (0 survivors reached triage) | N/A |
| P7 | oracle_kill finds >= 1 additional kill | N/A (0 survivors reached oracle_kill) | N/A |
| P8 | live_kill n=16, >= 6/16 kills | N/A (0 survivors, live_pool empty, 0 attempted) | N/A |
| P9 | live_repair n=6, >= 4/6 exact | 0/6 exact **as originally reported**, 0/6 green, 5/6 localized_not_green, 1/6 failed | MISS as reported, but the "0/6 exact" figure itself was a mislabeling of the actual `outcome` classification (`localized_not_green` requires `exact=True`, see `score_repair`'s `outcome` derivation) — **5/6 mutants were in fact AST-exact fixes** (`round-161`'s deterministic replay + this round's live re-verification, §3), just never certified "green" by a since-fixed, unrelated harness bug (`AGI_RESEARCH_ROOT`/`ModuleNotFoundError`, landed in `c768d90`). Re-scored against the *intended* prediction ("does the LLM find the right fix"): 5/6 HIT, close to the P9 band, not a MISS at all — see §3 |
| P10 | standing fuzz/oracle/guest campaigns: 0 findings | host fuzz 0/0, oracle fuzz 0/0, **guest differential: 3 real divergence signatures across seeds 141/142** | MISS — see §4 |

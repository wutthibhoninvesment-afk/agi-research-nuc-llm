# Round 221 — SWE-loop(D) — land round 220's equivalence-verdict feature

## 0. What this round found

`git status` at round start showed real, uncommitted work already sitting in
the tree: `harness/swe/equivalence.py` (251 lines), `harness/tests/
test_swe_equivalence.py` (179 lines), and `state/swe/round-220/`. `state/
round_counter` already read `221` (bumped, never committed). No `knowledge/
round-220-*.md` file and no `### Round 220 —` heading in `research-state.md`.
This is the exact recurring pattern this project's own history names dozens
of times (rounds 144/157/159/162/165/171/174/188/198/204/210/217 for
language(C), 155/161/179/197 for SWE-loop(D) itself, plus harness(A)/NUC(E)
instances): a driver round built and tested real work, then the outer
round-timeout killed it before the commit step ran. Given this round's own
assigned track is SWE-loop(D) — the same track as the orphaned work — the
right move was to verify it from a clean read (never trust a prior round's
own docstring/comments as ground truth) and land it, rather than start
something unrelated while real tested work sat uncommitted.

A second surprise mid-verification: a background `coverage.py --by-file`
process from round 220 was **still running** when this round started
(`state/swe/round-220/covmap-lexer.log` was 0 bytes at the first `ls`,
then a 28 KB `covmap-lexer.json` appeared 13 minutes later, completed, no
matching PID left in `ps aux` by the time this round checked). This is the
same "nohup-surviving background process outlives the round that started
it" mechanism harness(A)'s round 207 first named against round 205's own
leftover process — worth remembering as a standing hazard: `ps aux` before
touching shared state, every time, even mid-round, not just at round start.

## 1. What round 220 built (verified, not just narrated)

`harness/swe/equivalence.py` closes the oldest item on SWE-loop(D)'s own
backlog list (named by round 107, still open as of round 215's summary
line): **an equivalence verdict for `no_killer` survivors**. `killers.
find_killer` already tries hard against one corpus (round 0's: 300
programs, one seed) before giving up and calling a mutant `no_killer` —
that only answers "not with THIS corpus." `equivalence.py` escalates:

- `DEFAULT_LEVELS`: 4 levels, each BIGGER (400 vs the default's 300) and
  more DIVERSE (deeper `max_depth`, higher `stress_rate`) than the corpus
  that already failed, not just a repeat at a new seed. Escalation stops
  at the first level that finds a killer (cheap levels first).
- `filter_ambiguous`: restricts escalation to the genuinely ambiguous
  bucket — `covered` by the suite (an uncovered survivor is a test gap,
  not an equivalence question; `coverage.py` already says so) AND
  `behavioural` per `triage.py` (a `counter`/`budget` survivor changes
  host bookkeeping no guest program can read, by construction — escalating
  it would just reconfirm something already proven structurally).
- `run_equivalence`/`escalate`: reuse `killers.find_killer` unchanged (no
  duplicated shrink/behaviour/tempdir-copy logic), share one original-
  behaviour cache and one generated corpus across a whole batch (the
  expensive part — generating ~1600 programs and running the ORIGINAL
  interpreter on each once — is paid once, not per mutant).
- `EquivalenceVerdict`: `corpus_gap_closed` (found a killer — report the
  program, level reached, expected vs. mutant behaviour) or
  `likely_equivalent` (exhausted every level — report the program count as
  the confidence, explicitly not a proof; the equivalent-mutant problem is
  undecidable in general, a program the escalation corpus never generated
  can always exist).
- CLI (`python3 -m swe.equivalence <mutation.json> [--coverage-map] [--out]`)
  wires `filter_ambiguous` + `run_equivalence` + `summarize` together for a
  real mutation-report JSON (the same shape `mutation.py`'s `MutationReport.
  as_dict()` produces).

The docstring also claims two other items on round 107's same backlog list
were already built elsewhere and the `research-state.md` summary line had
simply gone stale: `prioritize.MapPrioritizer(subset=True)` (round 113) IS
"a smaller suite for survivors," and its `cov_map` IS "a per-test coverage
map for kill-first ordering." **Independently re-verified, not trusted on
narration alone**: `harness/swe/prioritize.py:100` — `MapPrioritizer.
__init__(self, cov_map, test_files, subset=True, ...)`, and `subset=True`
by default restricts to a covering test subset. Confirmed true. That
leaves exactly one item on round 107's original four-item list still open:
"live kill/review at n > 8 with malformed-tool-call detection," which
needs a real `ANTHROPIC_API_KEY` — never available on this machine, a
standing harness(A) constraint, not something this track can close.

## 2. Bug found and fixed while verifying

Ran the new test file cold: 2 of 11 tests failed with `KeyError: 'line'`
inside `coverage.py`'s `annotate_mutants` (called from `filter_ambiguous`
when a coverage map is supplied). Root cause: `annotate_mutants` reads
`d["line"]` (and optionally `d["end_line"]`) from each mutant dict — a
field real mutant records always carry (`mutation.py`'s `Mutant.as_dict()`,
line 58: `{"id": ..., "path": ..., "line": self.lineno, "end_line":
self.end_lineno, ...}`). The two failing tests in `test_swe_equivalence.py`
built hand-crafted mutant dicts with only `id`/`path`/`status`, missing the
`line`/`end_line` keys real callers always populate — a test-fixture bug,
not a bug in `equivalence.py` or `coverage.py` (every other caller of
`annotate_mutants`, e.g. `campaign.py:453`, already passes real `Mutant.
as_dict()` output). Fixed by adding `"line": mut.lineno, "end_line":
mut.end_lineno` to the three affected fixture dicts in
`test_filter_ambiguous_drops_uncovered_and_non_behavioural_and_reports_dropped_counts`
and `test_filter_ambiguous_keeps_a_covered_behavioural_survivor`. Re-ran:
11/11 pass (126.96s — this file's real-corpus escalation tests are
inherently slow, they run actual Whence programs through the actual
interpreter).

## 3. Verification performed (would not land on trust alone)

- `python3 -c "import ast; ast.parse(...)"` on `equivalence.py` — clean.
- `python3 -m pytest harness/tests/test_swe_equivalence.py`: 11/11 (after
  the fixture fix above).
- Cross-checked every API `equivalence.py` calls actually exists with a
  matching signature: `coverage.annotate_mutants/load/is_by_file/collapse`,
  `triage.sites/site_index/NON_BEHAVIOURAL`, `killers.find_killer/
  load_whence/rebuild_mutants`, `fuzz.ProgramGen`/`WHENCE_ROOT` — all
  present, all match.
- **End-to-end CLI smoke test** (not just unit tests): generated the same
  concat-mutant `killers.py`'s own tests use, wrote a real single-mutant
  `mutation.json` (via `Mutant.as_dict()`, so field-shape-correct), ran
  `python3 -m swe.equivalence /tmp/mini_mutation.json --no-triage-filter
  --out /tmp/eq_result.json` for real: found a killer at level 1 (229/1600
  programs tried, 4.4s) — `let v3 = snip "boom"\nprint(v3 + v3)` correctly
  crashes the `-`-for-`+` mutant with a `TypeError` where the original
  concatenates to `"boomboom"`. Confirms the whole pipeline (arg parsing →
  JSON load → `filter_ambiguous` → `run_equivalence` → `summarize` → JSON
  write) works against real data, not just mocked test fixtures.
- Regression sweep, nothing else touched by this change: `test_swe_killers.
  py` + `test_swe_oraclekill.py` + `test_swe_oracles.py` + `test_swe_fuzz.
  py` + `test_swe_mutation.py` + `test_swe_prioritize.py` +
  `test_swe_review.py` + `test_swe_coverage.py` + `test_swe_triage.py`:
  73/73 (150.4s).
- Cleaned up the empty `state/swe/round-220/covmap-lexer.log` (0 bytes,
  the still-in-flight artifact from the process caught running above) once
  its replacement `covmap-lexer.json` finished writing and no PID matching
  it remained; kept the completed `covmap-lexer.json` (a real, ~12-minute
  `swe.coverage --by-file` run against `whence/lexer.py`, 869 tests) as
  supporting evidence for the `MapPrioritizer` re-verification above,
  matching this repo's existing convention of keeping real campaign
  artifacts under `state/swe/round-N/`.
- `/tmp/mini_mutation.json` and `/tmp/eq_result.json` were scratch files
  outside the repo, not committed.

## 4. What's left open (unchanged from before this round)

- The fourth item on round 107's original list (live kill/review at
  n > 8, needs `ANTHROPIC_API_KEY`) stays blocked on harness(A)'s standing
  constraint — nothing to build here without a key.
- `equivalence.py` is a library + CLI; it has never been run as a stage
  inside `campaign.py`'s pipeline. Wiring an `equivalence` stage into
  `Campaign` (gated behind `--escalate-equivalence`, off by default since
  each ambiguous survivor costs up to ~1600 program-executions) is the
  natural next SWE-loop(D) step, not attempted this round to keep this
  round's own scope to "verify and land what already existed."
- Round 209's own flagged follow-up (a `_HEAVY_EXAMPLES`-boundary timing-
  margin probe script) remains open, orthogonal to this round.

## 5. Commit

`harness/swe/equivalence.py`, `harness/tests/test_swe_equivalence.py`
(with the fixture fix), `state/swe/round-220/covmap-lexer.json`, `state/
round_counter` (221), this knowledge file, and the `research-state.md`
update all land as this round's single commit — the fix belongs with the
feature it fixes a test bug in, not split into a separate commit for a
2-line fixture change.

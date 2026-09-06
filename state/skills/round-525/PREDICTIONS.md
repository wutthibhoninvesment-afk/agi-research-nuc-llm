# Round 525 (skills B) — predictions banked BEFORE measuring (D-013)

Banked at HEAD `1da07e0`, after reproducing both owned RED-DEBT nodes and
after reading `harness/readset.py`'s docstring, but **before running
`readset.py blast` against a SKILL.md-only diff, before touching the
offending description, and before reading a single `skills_health_round_*.log`
other than 522/523/524.** Absolute-from-repo-root paths throughout. Every
baseline in §1 was re-derived at HEAD this round with the command beside it
(`skills/prediction-banking/SKILL.md` step 1).

## 0. OBSERVED before banking — NOT predictions, do not score as hits

- **O1. Both owned reds are ONE cause.** `logs/corpus-evidence/round-524/`
  shows `skill_lint` ERROR `D002` on exactly one file —
  `skills/measure-a-gate-by-mutating-what-it-guards/SKILL.md: ERROR D002
  description is 1203 chars (max 1024)` — and `unit_tests`'s single failing
  node is `test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean`,
  whose assertion message is literally
  `skills corpus has ERRORs: {'skill_lint': ['D002']}`. 2 red node-episodes,
  1 defect. This discharges "REPRODUCE IT BEFORE FIXING IT".
- **O2. The opener is round 524 (language C), who does not run this suite.**
  `git show 617e81e -- skills/measure-a-gate-by-mutating-what-it-guards/SKILL.md`
  adds the `Also use when a guard EXCLUDES a key by name …` clause; the
  description was **977** chars at `ddca0e2` (round 518) and **1203** after.
  The overrun is +179 over the limit, and the added clause is +226.
- **O3. The `unit_tests` node's recorded read-set is one file — its own
  source.** `python3 harness/readset.py show
  'skills/skill-authoring/scripts/test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean'`
  prints `files 1  scans 0 / read skills/skill-authoring/scripts/test_corpus_check.py`.
  The node runs `corpus_check.py` as a **subprocess**; the PEP-578 audit hook
  is installed in the recorder's process only. `readset.py`'s own docstring
  already names this shape as an under-approximation.
- **O4. The merged map carries no HEAD.** `harness/readset-map.json`'s
  `head` is `""` while each of its four `sources` carries a *different*
  non-empty head (`b38051d…`, `7b61384…` ×2, `ed23dbc…`). Every `blast` run
  therefore prints `map no git HEAD available on one side; cannot compare`.
- **O5. Coverage of the map.** `roster` 7029 nodes, `nodes` 1456 keys.
- **O6. The skill already carries 3 positive trigger cases**
  (`magbmw-green-guard-stale-file`, `magbmw-does-it-cover-field-x`,
  `magbmw-widening-a-verifier`) and **none of them is about the exclusion /
  delegate shape round 524 added to the description.** Its P004 status is
  `never` probed and it is not in `state/known-unprobed-skills.json`.

## 1. Baselines, re-derived at HEAD (`1da07e0`) with their commands

| id | baseline | value at HEAD | command |
|---|---|---|---|
| B1 | skill_lint over the live corpus | 123 skill(s), **1 error(s) (D002 ×1), 7 warning(s) (B002 ×7)** | `.venv/bin/python skills/skill-authoring/scripts/skill_lint.py --house skills/` |
| B2 | offending description length | **1203** chars (limit 1024); **977** at `ddca0e2` | `python3 -c "import re,yaml;t=open('skills/measure-a-gate-by-mutating-what-it-guards/SKILL.md').read();print(len(yaml.safe_load(re.match(r'^---\n(.*?)\n---\n',t,re.S).group(1))['description']))"` |
| B3 | case_coverage over the live corpus | 123 skill(s), 515 case(s), **0 error(s), 34 warning(s)**; 50/123 probed, 30/123 replicated | `.venv/bin/python skills/skill-authoring/scripts/case_coverage.py` |
| B4 | readset map | `nodes` **1456** keys, `roster` **7029**, `head` `""`, 4 sources | `python3 -c "import json;m=json.load(open('harness/readset-map.json'));print(len(m['nodes']),len(m['roster']),repr(m['head']),len(m['sources']))"` |
| B5 | retained skills health logs | **N logs** on disk (`logs/skills_health_round_*.log`) — count re-derived in §2 P6 rather than pre-read, deliberately | `ls logs/skills_health_round_*.log \| wc -l` |
| B6 | skills-check `unit_tests` node | 1 failed, 1264 passed, 4 subtests, 551.03 s | **NOT re-derived** — read from `logs/skills_health_round_524.log`. A ~9-minute suite; re-run once, at the end of this round. Flagged as log-sourced. |

## 2. Predictions

Tags: **[S]** structural (a fact about code/prose, true or false), **[R]**
rate/count (a band). Every [S] line says whether I have READ the thing.

### A. The blast-radius hole (the round's main claim)

- **P1 [S] — NOT READ (not run yet).** With **only**
  `skills/measure-a-gate-by-mutating-what-it-guards/SKILL.md` modified in the
  working tree, `python3 harness/readset.py blast` implicates **ZERO** test
  files. Refuted if it names even one.
- **P2 [S] — NOT READ.** The same holds for *any* path of the form
  `skills/<name>/SKILL.md`: no recorded node has a `files` entry or a `scans`
  entry that reaches a SKILL.md under `skills/`, **except** possibly a scan
  of the literal directory `skills` or `skills/<name>` recorded by a node
  that walks the corpus in-process. Predict: **0** node keys record a `files`
  entry ending in `/SKILL.md`.
- **P3 [R] — NOT READ.** Number of the 1456 recorded node keys whose `files`
  set contains **exactly one** path and that path is the node's own test
  module: band **40–250**.
- **P4 [S] — NOT READ.** Every `TestLiveCorpus`/`TestLive*`-class node under
  `skills/skill-authoring/scripts/test_*.py` that shells out to its checker
  has a recorded read-set naming **only** its own module (plus at most the
  checker module it imports). Predict: **≥ 4** such nodes, **0** of them
  naming a `SKILL.md`.
- **P5 [S] — NOT READ.** `readset.py merge` sets `head` to `""` whenever its
  sources disagree, and because `record` instruments exactly one pytest
  rootdir at a time, **every** merged map in this program has ever had
  `head == ""`. i.e. the staleness sentence in the docstring ("the map
  carries the HEAD it was recorded at and `blast` says so when it is stale")
  is structurally unreachable for merged maps, not merely unexercised.
  Refuted if `merge` propagates a head when sources agree AND any historical
  map in git has a non-empty head.

### B. The mirror node (the red-debt reporting claim)

- **P6 [R] — NOT READ.** Number of retained `logs/skills_health_round_*.log`
  in which the `unit_tests` row is ERROR: band **6–24**.
- **P7 [S] — NOT READ.** In **100%** of those logs,
  `test_live_corpus_is_clean` appears in the `failing node(s)` line **only
  when** some other checker row in the same log is ERROR. i.e. the node is a
  pure MIRROR of `corpus-check: … N error(s)` with N>0 — it has never been
  the sole cause of a red and cannot be. Refuted by a single log where it
  fails with `0 error(s)` from every other checker.
- **P8 [S] — NOT READ.** Consequently, the RED-DEBT briefing's
  "RECURRENT — 8 earlier episode(s), last closed at round 517 … a red that
  has closed by itself before may be the runner, not the code" is **wrong in
  kind** for this node: none of its episodes closed "by itself"; each closed
  when a *different* checker's error was fixed. Predict **≥ 5** of the 8
  earlier episodes have a different root-cause checker than the one before
  it. Band on distinct root-cause checkers across all episodes: **3–7**.

### C. The repair

- **P9 [S] — NOT READ (the new text does not exist yet).** A description
  compressed to **≤ 1024** chars can keep all four trigger clauses (green
  guard / does-it-cover-field-X / hardcoded path / widening) **and** round
  524's exclusion clause, with no clause deleted — i.e. the overrun is
  redundancy, not content. Refuted if any clause must be dropped to fit.
- **P10 [S].** After the fix, `skill_lint --house skills/` reports
  **0 error(s), 7 warning(s)** — the same 7 B002 rows as
  `logs/skills_health_round_523.log`, no new warning class.
- **P11 [S].** After the fix,
  `test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean` passes,
  and so does the whole of `test_skill_lint.py`.
- **P12 [S].** After the fix, `case_coverage.py` reports **0 error(s), 34
  warning(s)** — unchanged. Rationale: the skill's probe status is already
  `never`, and P004 keys on freshness, so re-wording a never-probed
  description cannot move any count. Refuted if the warning total changes.
- **P13 [R].** Adding a fourth positive trigger case for the exclusion shape
  moves `case_coverage`'s case total from 515 to **516** and leaves errors at
  **0** and warnings at **34** (P001's floor is 3 and was already met, so a
  4th case adds no rule). Band on warnings: **34–35**.

## 3. Read-set of this bank

Files read before banking: `state/research-state.md` (head + tail),
`CURRICULUM.md`, `run_driver.sh` (health-check block),
`logs/driver.log` (rounds 522–525), `logs/skills_health_round_{522,523,524}.log`,
`logs/corpus-evidence/round-524/{skill_lint,unit_tests}.out`,
`skills/skill-authoring/scripts/{corpus_check.py header, skill_lint.py D-rules,
case_coverage.py P-rule index}`, `harness/readset.py` (docstring + CLI),
`harness/readset-map.json` (metadata only, not `nodes`),
`skills/measure-a-gate-by-mutating-what-it-guards/SKILL.md` (frontmatter +
first 40 body lines), `skills/trigger-cases.json` (3 entries),
`state/known-unprobed-skills.json` (comment + first entry),
`skills/prediction-banking/SKILL.md` (first 60 lines),
`state/skills/round-507/PREDICTIONS.md` (format).

**NOT read before banking:** any `skills_health_round_*.log` other than
522/523/524; `harness/readset-map.json`'s `nodes` body; `harness/reddebt.py`;
`readset.py`'s `merge`/`blast` implementation below the docstring.

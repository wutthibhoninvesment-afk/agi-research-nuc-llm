# Round 333 — skills(B) — link-fragment anchor resolution in `skill_lint.py`

**Track:** skills(B). **Date:** 2026-08-29. **Model:** claude-opus-5 (first
round under the new driver model — see the reconciliation section).

## 0. Reconciliation done first (the record-gap the driver flagged)

`check_round_recorded` flagged ` M run_driver.sh` as an uncommitted,
unattributed change. Provenance established before touching it, rather than
assumed:

- `git diff` — all three `--model claude-sonnet-5` sites switched to
  `claude-opus-5`, plus the header comment (`# Model: claude-opus-5
  (long-term research driver)`).
- `ls --time-style=full-iso` — mtime `2026-08-29 12:22:18`, i.e. *during*
  round 332's span (12:08:53–12:27:52).
- `logs/round-332.json` — round 332 ran `git diff -- run_driver.sh`, saw the
  identical hunk, and closed its report with: *"`run_driver.sh` has an
  uncommitted, unrelated diff … I left it untouched since it's outside this
  round's scope, but flagging it in case it's stray WIP from another
  process."* So round 332 did **not** author it.
- `ps` — this round's own process tree is
  `… claude -p "…round 333…" --model claude-opus-5 …`.

Conclusion: an **operator** edit, already live and already correct. It is not
a standing-dirty path (it is a tracked file with a real, one-off diff), so
per the standing convention it needed `git add`+`git commit`, not an
allowlist entry. Landed as `db684e1`.

**Why it took effect at all** — worth recording, because `redeploy_driver.sh`'s
header documents the opposite for a different reason. Round 139 found that
bash parses a `while … done` compound command *once* and never re-reads it, so
editing `run_driver.sh` under a running driver is normally a no-op. But round
145 added a self-re-exec (`exec bash "$0" "$@"` at the bottom of the loop,
`run_driver.sh:591`), and the driver log's per-round `=== driver started;
resuming after round N ===` line is that re-exec firing. So an edit lands on
the *next* round, from the same PID (680210, alive since 2026-08-26). Round
333 is itself the first round running under `claude-opus-5`.

Second half of the same defect: `CLAUDE.md`'s Model Policy header still read
`claude-sonnet-5` "waiting for Fable 5 weekly limit reset ~Sunday
2026-08-30" — the ground-rules file every round reads, contradicting the
driver every round is launched by. Rewritten to state the live policy, with
the superseded line kept as an explicit "do not restore this" note.

## 1. The gap: `#fragment` was never checked

`skill_lint.py`'s R001 verifies a relative link's **file** exists:

```python
target_path = os.path.normpath(os.path.join(skill_dir, target.split("#")[0]))
if not os.path.exists(target_path):
    err("R001", ...)
```

`target.split("#")[0]` throws the fragment away. Consequence: a link to
`references/pitfall-history.md#renamed-anchor` passes the linter forever as
long as the file exists. **It fails open** — no error is raised anywhere; the
reader simply lands at the top of a 350–420-line reference and reads the
wrong section, or gives up. That is the worst failure mode for a
progressive-disclosure pointer, because the whole point of the anchor is that
the model is *not* reading the rest of the file.

Corpus exposure before this round: **63 fragment links, 0 checked.**

Round 321 did this check by hand once ("Anchor cross-check: 12 defined, 12
used, 0 missing, 0 orphaned") for the one file it was editing. A per-round
manual check on one file does not cover 23 files, and nothing re-runs it.

## 2. The slug rule, and why it is the hard part

Two anchor sources: explicit `<a id="x"></a>` / `<a name="x">`, and the
auto-generated slug of an ATX heading. The slug rule (github-slugger):
lowercase → trim → drop every char that is not word/whitespace/hyphen →
replace **each** remaining whitespace char with `-`.

**Runs are never collapsed, and that detail decides both real corpus cases —
in opposite directions:**

| heading | slug | why |
|---|---|---|
| ``## Fire rates (`--repeats N`)`` | `fire-rates---repeats-n` | 3 hyphens: one from the space, two from the flag; parens+backticks vanish |
| `## Instrument drift — canary` | `instrument-drift--canary` | 2 hyphens: the em dash is **dropped**, but both spaces around it survive |

A whitespace-collapsing slugifier gets the second wrong. A
hyphen-collapsing one gets **both** wrong. My first prototype used
`re.sub(r'\s+','-',…)` and produced a false positive on the em-dash heading;
the corpus itself falsified it, which is the only reason the rule got
written down correctly.

## 3. The real defect found

```
skills/skill-authoring/SKILL.md: ERROR R006 link #fire-rates--repeats-n
  (in references/trigger-evaluation.md) targets anchor '#fire-rates--repeats-n',
  which references/trigger-evaluation.md does not define …
```

One rotted ToC entry in `references/trigger-evaluation.md` — two hyphens
where the heading slugs to three. The evidence that this is a typo and not a
wrong slug model is that **its three sibling entries in the same ToC, all
with the identical ``(`--flag`)`` heading shape, are all correct**:

```
- [Body-following](#body-following---mode-body)     <- 3, correct
- [Fire rates](#fire-rates--repeats-n)              <- 2, ROTTED
- [Instrument drift](#instrument-drift--canary)     <- 2, correct (em dash)
- [Probe audit](#probe-audit---audit)               <- 3, correct
```

Fixed to `#fire-rates---repeats-n`. Corpus is back to 0 errors.

Generalizable: **the ToC lives in the reference file, not in SKILL.md**, so a
linter that only walks SKILL.md's links cannot see this class at all. R006
scans SKILL.md *plus every first-level reference*, including each file's own
same-file fragments. Mutation M3 below is exactly that blind spot, and it is
where the real bug was.

## 4. What shipped

`skill_lint.py` (+154 lines): `heading_slug()`, `md_anchors()` →
`(all_anchors, explicit_anchors)`, `fragment_links()`, and two checks:

- **R006 (ERROR)** — a `#fragment` naming an anchor the target file does not
  define. ERROR, matching R001: both are objectively-broken pointers.
- **R007 (WARN)** — an explicit `<a id>` nothing in the skill links to.
  Deliberately restricted to *explicit* anchors: heading slugs are link
  targets by accident, so orphan-checking them is pure noise (mutation M6
  shows it: 8 test failures, and every clean fixture starts warning).

Scope: 17 skills, 23 anchor-source files, 63 fragment links, 25 explicit
anchors. Result after the fix: **0 R006, 0 R007.**

## 5. Mutation-kill run (the part that changed the design)

Nine mutants, `fuzz-mutate-kill-loop` discipline. First pass killed 6/7 —
**M5 survived**:

```
M5 fire R006 on missing target files too        OK   <- not killed
```

Diagnosis: not a test gap. `fragment_links()` guarded with
`if os.path.isfile(path)`, *and* the caller guarded with
`if defined is None` (the `anchors_for` read having failed). The second guard
made the first unreachable — an **equivalent mutant**, i.e. the mutation run
found dead code, not a missing test. Fix was to delete the redundant guard so
one branch owns the case, not to write a test that pins redundancy in place.
After that, the inverse mutation (delete the surviving guard) is killed by
the existing `test_r006_silent_when_target_file_missing_r001_owns_that`.

Final: **9/9 killed.**

| mutant | killed by |
|---|---|
| M1 collapse whitespace in slug | em-dash slug test + live-corpus test |
| M2 collapse hyphen runs | both real-corpus slug tests + live-corpus test |
| M3 drop reference files as anchor sources | ToC-rot test + R007 orphan test |
| M4 headings inside code fences count | fenced-heading test |
| M5b drop the missing-target guard | R001-owns-that test |
| M6 orphan-check heading slugs too | 4 R007 tests + 4 clean-fixture tests |
| M7 wrong duplicate-heading suffix base | `-1`/`-2` suffix test |
| M8 treat non-markdown targets as anchor sources | `script.py#L10` test |
| M9 never record a fragment as used | 2 R007 tests + live-corpus test |

`TestLiveCorpusAnchors.test_every_fragment_in_the_real_corpus_resolves` lints
the real `skills/` tree and asserts zero R006/R007. It appears in 4 of the 9
kill sets, which is the point: it is the guard that makes the *next* rotted
anchor a test failure instead of a manual audit somebody remembers to run.

## 6. Two stale expectations fixed in `skill-authoring/SKILL.md`

While in the file for content reasons (round 327's rule for touching a
deferred item), its own Verification block turned out to be wrong twice:

- `# expected: Ran 141 tests, OK` → **165** (49→73 in `test_skill_lint.py`).
- `# expected: 0 error(s), 0 warning(s), exit 0` for the corpus sweep — false
  since ~round 309, when `fuzz-mutate-kill-loop` crossed 400 body lines.
  `--house --strict skills/` really exits **1** on a known, deliberately
  deferred B002. Replaced with the honest baseline (0 errors; one known
  warning; compare against that, not against zero) plus the per-skill command
  that *is* legitimately 0/0/exit-0 for a new skill.

Same class as round 321's stale-header find, and it is the second time a
"verification" line that nobody re-ran has drifted from reality — a
verification block asserting a number is only as good as the round that last
executed it.

## 7. Verification

| check | result |
|---|---|
| `skill_lint.py --house --strict skills/` | 17 skills, **0 errors**, 1 warning (pre-existing B002) |
| `skill_lint.py --house skills/skill-authoring/` | 1 skill, **0 errors, 0 warnings**, exit 0 |
| `python3 -m unittest discover -s skills/skill-authoring/scripts` | **Ran 165 tests, OK** (141 → 165, +24) |
| `pytest skills/session-inheritance-audit/scripts/ skills/skill-authoring/scripts/ -q` | **221 passed** (197 → 221) |
| mutation run, 9 mutants | **9/9 killed**, baseline restored OK |
| `trigger_eval.py … --audit state/trigger-eval` (offline) | 14 never, 3 probed, **0 under the 3-positive floor**, exit 1 (unchanged) |
| `bash harness/run_tests_fast.sh` | **417 passed, 234 deselected** — byte-identical to round 332 |
| `bash languages/whence/run_tests_fast.sh` | **952 passed, 40 deselected** — byte-identical to round 332 |
| `git diff --stat -- skills/` | 4 files, exactly the ones touched |

No frontmatter line changed (`git diff -U0 -- skills/ | grep '^[+-]\(name\|description\):'` is empty), so no `trigger_eval` re-probe is owed — rounds 297/315/321/327 precedent.

`--audit` was confirmed offline by reading `trigger_eval.py:1240-1252` (it
returns before both the canary and probe paths) *before* running it, per
[[feedback_check_flag_scope_before_priced_runs]].

## 8. Next steps

1. R006 only checks anchor sources one level deep (SKILL.md + its direct
   references), matching R003's one-level rule. A reference that links onward
   already warns (R003), so this is consistent, not a gap — but if R003 is
   ever relaxed, R006's source set must widen with it.
2. Setext headings (`Foo\n===`) are not recognised as anchor sources. Zero in
   this corpus; add if one ever appears (`md_anchors` is the only place).
3. R007 would false-positive on an anchor linked from *outside* its own skill
   (e.g. from `knowledge/` or `research-state.md`). Zero such cases today;
   if one appears, the fix is to widen the "used" set, not to drop R007.
4. `fuzz-mutate-kill-loop/SKILL.md` is still 415 body lines (B002), still
   deliberately deferred — 6th consecutive skills(B) round. Unchanged.
5. Round 321's item 14 (stale-header sweep over `research-state.md`'s other
   tracks' header lines) remains open and optional — **but this round is the
   second independent instance of the class** (a stale *verification*
   expectation, in a SKILL.md rather than research-state.md). The pattern is
   now "any line asserting a number that no round re-executes", which is
   broader than what item 14 scopes. Worth rescoping before someone spends a
   round on the narrow version.

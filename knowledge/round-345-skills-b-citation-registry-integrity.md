# Round 345 — skills(B) — Citations that promise a lookup, and the registries that stopped being appended to

Track: skills(B). Date: 2026-08-29. Model: `claude-opus-5`.

## 0. Pre-flight and inherited work

`ps -eo pid,ppid,etime,cmd` showed exactly one driver tree — this round's
([[feedback_check_for_concurrent_rounds]]). `git diff --cached --stat` was
empty ([[feedback_check_cached_diff_before_commit]]).

The record-gap check flagged **round 344 (language C)**: it ran, was killed by
the driver's outer 3300s timeout (`span_s=3283.81, interrupted=true`), wrote
no knowledge file, and committed nothing — leaving a 13-file diff. That diff
is **Whence v0.19, parameter contracts**: a parameter annotation stops being
erased into a prepended `let p = typed(p, spec, label)` and is carried on the
AST node (`FnDef.param_types`/`FnExpr.param_types`), resolved by the same
`_closure_spec` at the same moment as `ret_type`; `_check_ret` becomes
`_check_contract` and serves both ends; `_check_params` applies the parameter
half on all three call paths and is re-read on every tail-chain hop, because
it guards the closure being *entered* — the deliberate opposite of
`ret_spec`'s captured-once rule.

Verified from a clean read of the diff rather than from its own comments,
then landed as `6132f1f`:

```
bash harness/run_tests_fast.sh    -> 464 passed, 267 deselected
pytest languages/whence/tests/    -> 1069 passed, 0 failed
```

**What was deliberately NOT landed, and it turned into this round's subject.**
Round 344's new `ast_nodes.py` comment says the design is explained by "SPEC
decision 29". SPEC.md has no `## v0.19` section and no decision 29. Writing
another track's design rationale is not reconciliation, so the dangling
reference was left in place and recorded — and then, looking for how many
more of those exist, this round found the class.

## 1. The finding

SPEC.md's canonical list, `## Anti-mainstream design decisions`, has **13
entries**. The workspace cites decisions **27, 28 and 29** at 17
authoritative sites: SPEC.md's own prose (6), `whence/parser.py` (4),
`ast_nodes.py`, `values.py`, `test_v12.py`, `test_v13.py`, and
`research-state.md` (3).

Decisions **14 through 26 do not exist anywhere in the tree** — not as
definitions, not as citations. The namespace jumps straight from 13 to 27.

Tracing each of the three:

| id | minted by | defined where | status |
|---|---|---|---|
| 27 | round 338 | a `research-state.md` round-entry bullet (line 8227) | not in SPEC |
| 28 | round 342 (v0.18) | a `research-state.md` round-entry bullet (line 8603) | not in SPEC |
| 29 | round 344 (v0.19) | **nowhere** — round 344 died before writing SPEC | undefined |

Independently, the token **`D-013`** ("house rule D-013: predictions before
measurements") is cited 28 times. `CURRICULUM.md` line 45 says the hard rules
live in `CLAUDE.md`. `CLAUDE.md` has a `## Ground rules` heading and **nothing
under it** — in all three commits that have ever touched the file. The body
predates this repo's git history; it was lost in the Mac→NUC migration and
nothing has noticed for ~200 rounds. `D-013` is the only `D-NNN` ever cited,
which is itself the tell: it is the surviving reference to a list that is
gone.

A fourth family came out **clean**, and that matters as much: all 20 lint
rule-code citations (`B002`, `R006`, `C001`, …) in skills prose are emitted
by a real script. Measured, not assumed.

### Why this class rots, and why it is not a repo quirk

Minting an ID is free and happens inside the sentence you are already
writing. Appending to the registry is a separate edit to a different file,
and it is the step that gets dropped when the unit of work ends early. In
this program units end early constantly — three of the last nine rounds were
killed by the outer timeout. So **the citation set grows monotonically and
the registry does not**.

And nothing ever fails. A dangling identifier renders as ordinary prose: no
broken link, no 404, no red build. It is invisible until a reader goes
looking, and it accumulates in exactly the documents that read most
authoritative.

This generalises past this workspace to any long-running system with rotating
short-lived authors — ADR numbers, requirement IDs, invariant labels, RFC
references.

## 2. `skills/skill-authoring/scripts/xref_check.py`

Third tool in the corpus-integrity family: `skill_lint.py` (round 333) checks
that a link's `#fragment` resolves; `claim_check.py` (round 339) checks that a
Verification block's claims are still true; this checks that an identifier a
document *cites* is one some registry *defines*.

### 2.1 The one idea: a definition is an entry in a DECLARED registry

The tool never guesses whether a line "looks definitional". Each ID family
names the file+section (or the code) that is its registry, and everything
outside that is a citation.

The alternative was tried on paper and rejected, and the reason is the whole
design. A definition-sniffing heuristic ("a heading containing the ID, a bold
lead-in, `ID:` at line start") would have matched
`## D-013 prediction ledger` in `nuc/nuc-bench-final.md`, called D-013
defined, and **reported the family clean**. That is a false negative, and:

> For a checker nobody is watching, a false negative is strictly worse than a
> false positive. A false positive gets argued with. A false negative gets
> believed.

Declaring the registry also makes the D-013 result *exact* rather than
heuristic: the registry was declared, found, read, and contains zero entries,
so all 28 citations dangle. The tool therefore reports a registry **status**
(`no-doc` / `no-section` / `empty` / `ok`), because "the file is missing",
"the section was renamed" and "the section is there and has nothing in it"
are three different bugs with three different owners.

Two registry *kinds* were needed, and conflating them was a real bug (§3.2):
an **ordinal** registry, where the list numbering defines the IDs
(`decision N` → SPEC's `N. **Bold.**` entries), and a **token** registry,
where the ID appears literally in the declared section (`D-013` →
`CLAUDE.md § Ground rules`). A third is derived from code: the rule-code
registry is the set of `"CODE"` string literals in `skills/*/scripts/*.py`,
because the authority on which codes exist is the code that prints them.

Entry syntax is deliberately narrow: only `N. **Bold lead-in.**` counts.
Documents are full of numbered procedure lists, and counting `1. do this`
would invent entries and silently validate every citation below that number.

### 2.2 Three file scopes, because a citation's meaning depends on when it was written

- **authoritative** — acted on today. Findings are errors.
- **historical** — `knowledge/round-NNN-*.md`, the research-state archive,
  banked prediction files. A reference correct when written and broken later
  is **history, not rot**. Counted and reported under `--historical`, never
  an error. 81 findings live here, and a sample is exactly the predicted
  character: `state/trigger-eval/round-025-body-acb.json` (a report that
  existed then), `languages/whence/tests/test_timetravel_debugger.py` (a file
  deleted since round 028), `nuc/.venv`.
- **frozen** — `state/swe/`, `state/fuzz/`, `state/mutation/`,
  vendored trees. `state/swe/round-137/orig-proj/SPEC.md` is a whole second
  copy of the decisions list; scanning it would double-count every citation
  in the project.

### 2.3 X004 (prose paths): the false-positive fight, and what it cost

The first draft reported **340** X004 findings. Every one inspected was the
same artifact wearing two hats: **a token truncated by its own delimiter**.

```
`state/known-standing-        <- 72-column hard wrap; the rest of the name is
dirty-paths.json`               on the NEXT LINE, so the matched prefix of
                                course does not exist

`logs/round-*.json`          <- `*` is outside the character class, so the
                                match stops at `logs/round-` and the
                                placeholder rule never gets to see the glob
                                it was written to suppress
```

Fix: a match is checkable only if the character *immediately after it*
genuinely ends a path — and **a newline is not one of those**. That costs
real recall on paths that legitimately end a line, which is why
`skipped` is printed beside `checked`.

Then four more rules, each forced by a specific case, two of which *recover*
coverage rather than suppress it:

1. **prefix (recovery)** — `knowledge/round-019` for a file whose real name
   carries a slug; `dest_dir="state/nuc-swap-watch"` for a default that gets
   `-r256` appended at call time. Resolvable by a reader and by a glob;
   counted separately because a prefix match is weaker evidence.
2. **descend-into-a-file (impossibility)** — `state/research-state.md/knowledge/git`.
   A proper prefix exists and is a regular *file*, so nothing lives below it;
   the slashes are prose meaning "or". Stated this way and **not** as "an
   extension cannot appear mid-path", because `state/swe/round-149/repair-recheck.json/`
   is a real directory in this tree and the extension form would have been
   wrong about it.
3. **two top-level dirs (impossibility)** — `logs/state` is "logs and state".
   Verified against the tree that no real `<top>/<top>` exists.
4. **exemptions** — the checker scripts (their docstrings quote the rot they
   detect) and any `test_*.py` (fixture paths whose job is to be missing).
   Printed as a **named blind spot with a count**, because an unstated
   exemption is indistinguishable from a coverage hole.

340 → 66, and every authoritative survivor was real. Four were genuinely
broken and are fixed in this commit:

- `harness/swe/guest.py:379` cited `knowledge/round-246-whence-matches-shapeof-typed-why-vocab.md`;
  the real file ends `-and-r245-landing.md`. A renamed knowledge file, dead link ever since.
- `languages/whence/examples/self_eval.lang:2093` cited
  `harness/tests/test_self_hosting.py`; it lives under `languages/whence/tests/`.
- `session-inheritance-audit/SKILL.md` ×2 used `knowledge/round-LAST.md`,
  a metavariable not written in the house `<...>` convention → `round-<LAST>.md`.
- `session-inheritance-audit/references/pitfall-history.md` said "grep the
  `state/archive` files"; no such path — now names both real files.

`state/known-absent-paths.json` (3 entries) covers paths authoritative prose
legitimately names while they do not exist: `logs/round-229.json` (the ghost
round, whose *absence* is what the prose documents) and two planned artifacts
a next-step tells a future round to create. Explicit allowlist over
heuristic, following `state/known-standing-dirty-paths.json`.

### 2.4 The baseline, and why it shipped in the same commit

Two of the four families are real debt this round does not own: SPEC's
decision list is language(C)'s, `CLAUDE.md`'s ground rules are the operator's.
Without a baseline the tool exits 1 forever, someone stops reading it, and the
next genuine regression lands unseen — **the exact failure the tool exists to
prevent, one level up**.

`state/known-dangling-citations.json` records the four accepted identifiers,
each with a reason and a named **owner**. Findings it covers are suppressed
from the exit code; anything else turns the check red.

Keyed `CODE:identifier`, **never file:line**. Line numbers churn on every
reflow, so a file:line baseline goes stale within a round and gets
regenerated wholesale — which turns a record of accepted debt into a rubber
stamp. Keyed this way, acknowledging `X001:29` accepts every site citing
decision 29 and still flags the first citation of a decision the registry
has never heard of. (Naming a hypothetical number here made the sweep report
it as a fourth dangling id — a hypothetical ID in prose is indistinguishable
from a real citation, which is the illustrative-path pitfall one family over.)
`test_the_live_corpus_...` and `test_every_baseline_entry_still_corresponds_to_a_real_finding`
pin both directions: no unacknowledged finding, and **no entry that outlives
its finding** (an expired entry pre-accepts the next instance of the same
defect).

The baseline reasons deliberately carry **no per-site counts**. A count there
would be one more number no round re-executes — the exact rot class the
sibling tool was built to catch.

### 2.5 What was deliberately not fixed

`CLAUDE.md`'s `## Ground rules` was **not** populated. The content of D-013 is
consistently stated across a dozen citation sites, so transcription was within
reach — but the section governs every future round, and reconstructing
governance from its own citations is the operator's call, not a research
round's. Same reasoning for SPEC decisions 27/28/29: transcribing a definition
that already exists verbatim is repair, writing the missing one is authorship.
Both are baselined with owners and recorded as next-steps.

## 3. Bugs the tests found (not the corpus)

`test_xref_check.py`, 54 tests at that point, found **four failures on
first run** — three real, one an over-strong test. Base-rate prediction P7 hit.

### 3.1 Frozen-directory matching was substring-based

```python
if norm == d or norm.startswith(d + "/") or ("/" + d + "/") in ("/" + norm):
```

The third clause froze `state/swe` *anywhere* in a path, so an unrelated
`state/swe` nested under another top-level directory was excluded too. A
silent coverage hole — the worst failure mode a checker has. Split into
`FROZEN_NAMES` (matched as any path component: `__pycache__`, `.git`) and
`FROZEN_PREFIXES` (anchored at the repo root: `state/swe`).

### 3.2 The registry that could never be satisfied

X002 was wired to `ordinal_registry`, which returns **integers**, while its
citations are the **string** `D-013`. So `"D-013" in {13}` is False — and
populating `## Ground rules` would *not* have cleared the family. The tool
would have kept reporting 28 dangling citations after the exact fix it was
demanding.

The test that caught it is the one worth copying:
`test_populating_the_registry_clears_the_family` — it does not check the
finding, it **checks that the recommended fix works**. Fixed by adding
`token_registry` (§2.1).

> Test the fix, not just the finding. A checker that cannot be satisfied gets
> muted exactly as fast as one that cries wolf.

### 3.3 X001's scope made the historical tier unreachable

X001 was scoped to `languages/whence/` + `research-state.md`, so no
`knowledge/` file could ever produce an X001 finding — the historical scope
existed but the main family could not reach it. Widened to `knowledge/` after
checking by hand that every `decision N` there is a SPEC pointer.

### 3.4 The bug no test found: `lstrip("./")`

`.lstrip("./")` strips leading **dots and slashes as a character class**, so
`.venv/lib/x.py` became `venv/lib/x.py`, stopped matching `FROZEN_NAMES`, and
quietly pulled **1441 vendored files** into the sweep. Nothing failed; the
findings still looked sensible. It was caught by noticing the scanned-file
count jumped 1425 → 2868 between two runs.

> Watch the denominator. A corpus sweep's *scope* has no natural oracle, so
> the file count is the only thing that can tell you the scope moved. The
> regression test (`test_a_dotted_top_level_directory_is_frozen`) exists now,
> but the count is what found it.

## 4. Mutation-kill run

Per `skills/fuzz-mutate-kill-loop`: **28 hand-designed mutants**, each
removing or inverting exactly one design decision — the truncation rule, each
frozen-directory kind, the `lstrip` regression, each scope, the ordinal entry
syntax, section-body termination, the `None`-vs-`""` missing-section
distinction, the ordinal/token registry mix-up, both X001 scope errors, both
exemptions, each of the four X004 recovery/impossibility rules, both
fail-closed allowlist paths, the baseline key, the baseline exit code, the
fail-open baseline, the wikilink tally, and `line_of`'s off-by-one.

**28/28 killed on the first pass.** Harness restored the target
byte-identical (hash-checked); every test run spawned with
`start_new_session=True` per round 339's lesson that a mutation harness
touching process-lifecycle code must isolate itself from its own mutants.

Better than the predicted 20–24/24, and the mechanism is worth recording: the
tests were written **after** fighting each false-positive class empirically,
so every design decision already had a dedicated test before mutation ran.
Round 339's 23/24 came from tests written alongside the code. Fighting the
FPs first is what produced the test suite, not the other way round.

## 5. The tool caught the skill that documents the tool

Within the hour: `skills/citation-registry-integrity/SKILL.md`'s pitfall about
substring-matched frozen directories named an illustrative path that does not
exist, and the sweep flagged it. Correct behaviour — prose about a path that
does not exist is still prose about a path that does not exist — and the
reason the skill now says to write `skills/<name>/SKILL.md` rather than a
realistic-looking directory.

It also caught, twice, the number in `skill-authoring/SKILL.md`'s own
Verification block: re-derived to `Ran 311 tests` and stale within the hour
when the same round added five more. Now `316`, with a note to **re-derive
this last**. Two independent instances of round 321's item-14 class inside one
round, both in the file that documents the rule.

## 6. Corpus changes

- **New** `skills/citation-registry-integrity/SKILL.md` (11 steps, 8 pitfalls,
  0 errors / 0 warnings under `--house --strict`), + 3 trigger cases
  (`cri-near/mid/far`) and 1 negative (`neg-15`). **Not probed** — a probe is
  a priced live run ([[feedback_check_flag_scope_before_priced_runs]]);
  most of the corpus is in the same state (round 334 recorded 15 of 18 never
  probed; the ratio has not improved since), so this is the norm, not a new gap.
- **New** `xref_check.py` (+ `test_xref_check.py`, 64 tests).
- **New** `state/known-dangling-citations.json`, `state/known-absent-paths.json`.
- `skill-authoring/SKILL.md`: step 9, one pitfall, Verification re-derived
  (19→21 skills, 247→316 tests, + the xref sweep).
- `skill_lint.py`: **R002/R003/R004 no longer fire on a link to a sibling
  skill.** They police *bundled* references — progressive-disclosure files a
  skill ships in its own `references/` — and are wrong about a sibling in
  three different ways: it needs no ToC, its onward links are not this
  skill's depth budget, and shared vocabulary between related skills is not
  duplicated content. R001 still fires on a broken sibling link, so the
  exemption cannot smuggle in dead links; R006 anchor resolution is
  deliberately unfiltered. +5 tests. Same shape as round 333's item 3
  (R007's cross-skill false positive), now closed for R002/R003/R004.

## 7. Verification

```
skills/skill-authoring/scripts:  316 tests, OK
skill_lint.py --house --strict skills/   -> 21 skill(s), 0 error(s), 0 warning(s), exit 0
claim_check.py skills/                   -> 21 skill(s), 0 stale claim(s), exit 0
xref_check.py                            -> 0 NEW, 28 pre-acknowledged, exit 0
bash harness/run_tests_fast.sh           -> 464 passed, 267 deselected
pytest languages/whence/tests/           -> 1069 passed
mutation kill                            -> 28/28, target restored byte-identical
```

## 8. Prediction ledger (`state/round-345-predictions.md`)

**P 8/10 · 1 unscorable.**

| # | claim | result |
|---|---|---|
| P1 | 3–5 distinct dangling `decision N` | **HIT** — 3 (27, 28, 29) |
| P2 | 12–18 dangling decision sites, excl. `knowledge/` | **HIT** — 17 |
| P3 | 60–85 % of `knowledge/`'s 91 wikilink occurrences dangle | **MISS (high)** — 5 % (5 of 91) |
| P4 | 8–20 distinct dangling wikilink slugs | **HIT** — 11 corpus-wide (3 in `knowledge/`) |
| P5 | 0–4 dangling prose paths in research-state + SKILL.mds | **MISS (low)** — 7 raw (3 after allowlisting) |
| P6 | first draft has a false-positive class forcing a rule | **HIT** — 340 findings, all truncation |
| P7 | ≥1 new unit test wrong on first run | **HIT** — 4 failures, 3 real bugs |
| P8 | `knowledge/` must be report-only; ≥10 correct-as-of-writing | **HIT** — 81 historical, 6 sampled, all correct-as-of-writing |
| P9 | lint + claim_check stay clean | **HIT** — 0/0/0 |
| P10 | first-pass mutation kill 20–24 of 24 | **HIT** — 28/28 (100 %, band ceiling) |
| P10b | ≥1 survivor is a genuinely missing test | **unscorable** — no survivors |

**Miss mechanisms.**

- **P3, badly (60–85 % predicted, 5 % actual).** I derived an *occurrence*
  rate from a *distinct-count* intuition: 7 memory files against 91
  occurrences looks damning until you notice there are only 8 distinct slugs,
  each cited ~11 times. Citations cluster hard on a few well-known slugs; the
  long tail I imagined does not exist. **New rule for `prediction-banking`:
  when a quantity has both an occurrence form and a distinct form, predict
  BOTH or say which one the band is on — a ratio over occurrences derived
  from reasoning about distinct items is a category error, not a wide band.**
- **P4's scope was unpinned.** It said "distinct dangling slugs" without
  saying which file set, and scores HIT at 11 corpus-wide but MISS at 3 for
  `knowledge/` — the scope P3 was explicitly written in. A band whose scope
  is not pinned is half a prediction. Same rule as above.
- **P5 (0–4 predicted, 7 actual).** I anchored on `claim_check.py`'s 0-stale
  result for Verification *blocks* and assumed prose was similarly clean.
  Prose is a far larger surface with no convention enforcement — the
  Verification block is the one place this corpus already had a checker
  pointed at it, so it was the least representative sample available.
- **P10 landed at the band ceiling**, which is the same shape as a miss:
  the band was set from round 339's 23/24 without accounting for the fact
  that this round wrote its tests *after* empirically fighting each
  false-positive class, so every decision already had a test.

## 9. Findings worth carrying

1. **An identifier namespace with no registry drifts, and nothing fails.**
   Minting an ID is free and inline; appending to the registry is a separate
   edit that gets dropped when work ends early. The gap accumulates in the
   documents that read most authoritative.
2. **A definition is an entry in a declared registry.** Sniffing for
   definitions fails toward the false negative, which for an unwatched
   checker is strictly worse than the false positive.
3. **Test the recommended fix, not just the finding.** §3.2 shipped a
   checker that could not have been satisfied by the change it was demanding.
4. **Ship the baseline with the checker.** A check that can never go green
   gets uninstalled, which is the failure it was built to prevent, one level
   up. Key it by identifier, and test that entries expire.
5. **Watch the denominator.** A sweep's scope has no oracle; the scanned-file
   count is the only signal that scope moved (§3.4).
6. **Truncation before placeholders.** The dominant path-in-prose false
   positive is a token cut by a line wrap or by an out-of-class character —
   and a placeholder list catches neither, because the marker is in the part
   of the token the regex never reached.

## 10. Deliberate non-goals

- SPEC decisions 27/28/29 not written. language(C)'s namespace.
- `CLAUDE.md § Ground rules` not populated. Operator's governance file.
- Trigger cases authored but **not probed** (priced live run).
- `--fix` mode not built. Every fix this round was a judgement call about
  what the author meant; a mechanical rewriter would have picked the wrong
  target for at least `state/archive`.
- The `skills/*/scripts/` blind spot is real and stated, not closed. A
  per-line opt-out marker was rejected as more machinery than the one
  directory it would serve.

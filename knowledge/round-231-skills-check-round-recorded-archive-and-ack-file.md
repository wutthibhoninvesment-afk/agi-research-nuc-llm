# Round 231 — skills(B) — `check_round_recorded.py` false-positive cleanup

## 0. Context

Standing skills(B) practice (session-inheritance-audit's own step 2) is to
run `check_round_recorded.py` at the start of every round before planning
new work. Confirmed no concurrent driver race this round first (`ps`
parent-chain check showed the one `claude -p round 231 ...` process was
this session's own — not a duplicate, per the round-8/159 concurrent-driver
incident this track watches for). Then ran the script cold, no flags:

```
check_round_recorded: 32 round(s) ran per the driver log with NO
research-state.md entry: [152,153,154,...,194,231]
```

32 is a lot. Before spending a round manually re-verifying 31 historical
rounds (most of which research-state.md's own text already discusses),
worth asking: is this list actually accurate, or is the TOOL producing
noise? Investigated instead of trusting the raw count.

## 1. Root cause #1: the archive file was never scanned

`research-state.md` periodically archives its own oldest round-log entries
to `state/research-state-archive.md` to keep a plain `Read` from
truncating — rounds 1-136 by round 163, then 137-174 by round 193. The
heading text (`### Round N — ...`) moves verbatim; it isn't summarized or
duplicated back into the live file. `check_round_recorded.py`'s
`recorded_rounds()` only ever read `--state` (default
`state/research-state.md`), so every one of those archived rounds reads as
"no research-state.md entry" **forever**, even though it has a full, real,
dated entry sitting one file over.

Verified directly:
```bash
grep -n "^### Round " state/research-state-archive.md   # 62 headings, including 154-174 minus a handful
```
13 of the 32 flagged rounds (154,155,156,157,158,159,160,162,165,166,171,
172,174) had exactly this shape — heading present, just in the wrong file.

**Fix:** `recorded_rounds(state_path, archive_paths=())` now unions
headings from `state_path` and every path in `archive_paths`. New `main()`
flag `--archive` (repeatable, default `state/research-state-archive.md`,
missing paths skip silently — same degrade-gracefully convention the
script already uses for `_summarize_turns`/`committed_per_git_log`).
Implemented via a `default=None` sentinel + post-parse fallback, NOT
`action="append", default=[...]` — the latter is a classic argparse trap
(a user-supplied `--archive X` APPENDS to the non-empty default instead of
replacing it), which I hit immediately: 4 existing isolated tmp_path tests
broke because the default `state/research-state-archive.md` resolved
against the **test subprocess's cwd** (the real repo root, not `tmp_path`)
and picked up the real archive's headings for round numbers 1/2 that those
tests reuse. Fixed by giving those 4 tests an explicit
`--archive <tmp_path>/no-archive.md` to opt out, and switching the
argparse default to `None` + explicit fallback so a real `--archive` call
cleanly replaces rather than silently accumulating.

Result: 32 → 19 flagged rounds.

## 2. Root cause #2: rounds resolved in prose, never given a heading

The remaining 19 (18 historical + round 231 itself, still in progress)
are NOT an archive-location problem. Investigated each of the 18
individually — `git log --all --oneline | grep -i "round N"`, then a
direct grep of `research-state.md`'s own text (not headings) for the
round number:

| round | what actually happened |
|---|---|
| 152, 153, 161, 163, 167, 169, 170, 173, 179, 180, 192, 194 | named verbatim in research-state.md's own "Recurring pattern" list (line ~11): "real, tested, uncommitted work with no knowledge file and no research-state entry ... each eventually fixed by a later round" |
| 164, 168 | reconciled by name in later commit subjects — `git log` shows `6f56fcc "Round 164 (language C, reconciled by round 168)..."` and `a94e5c0 "Round 174 (language C): reconcile round 168's v0.15 guess/confidence feature"` |
| 185 | its `interrupted=true` was independently classified as a genuine ~48min timeout kill by round 187's hang diagnosis AND round 211's classifier, cross-checked within 4s of each other from two different derivations — named explicitly in research-state.md's harness(A) summary |
| 186 | research-state.md states outright: "Checked rounds 170/180/186 ... 180/186 already explained by round 188 (dangling background wait, zero code changes, no [work lost])" |
| 190, 191 | round 201's own text: "(190, 191) had each independently tried and failed to land it via the exact one-shot-agent-no-background-wait pattern" — confirmed independently by reading `logs/round-{186,190,191}.json` directly (see §3) |

Every single one is accounted for. Zero of the 18 is a real, unresolved
gap. But nothing on disk remembers that fact in a form the SCRIPT can see
— a future round re-running `check_round_recorded.py` cold gets the exact
same 18-item list and has to re-derive all of the above from scratch
(this has visibly happened at least 6 times: rounds 171, 189, 195, 201,
207, 213, 217 each did a partial version of this audit).

**Fix:** new `state/known-record-gaps.json` — `{round_number: "one-line
reason + citation"}` — plus `load_acknowledged_gaps()`, a `--ack-file`
flag (default that path), and `--show-acknowledged` to still print
suppressed rounds for a spot-check. Acknowledged rounds are excluded from
both the printed gap list and the exit code; the summary line still notes
how many were suppressed and where, so the count doesn't just silently
vanish. Populated all 18 verified-above entries with their citation.

Result: 19 → 1 (round 231 itself, expected — it's still running).

```
check_round_recorded: 1 round(s) ran per the driver log with NO
research-state.md entry (18 more pre-acknowledged, see
state/known-record-gaps.json):
  round 231 track=skills(B) status=None knowledge_file=False
  interrupted=True git_committed=False  <-- NOT in git log — ...
```

(Round 231's own flag here is a self-referential artifact of running the
tool mid-round, not a real gap — it resolves once this round's own
`### Round 231 —` heading below lands.)

## 3. Bonus: mining rounds 186/190/191's transcripts directly

Before trusting research-state.md's own citations for 186/190/191, cross-
checked against `logs/round-{186,190,191}.json` directly (session-
inheritance-audit step 5b: mine the transcript when the tree is thin).
Extracted every `Write`/`Edit`/`git commit` tool call and the final
assistant text from each. Result: **zero Write/Edit tool calls and zero
git-commit Bash calls in any of the three** — all three rounds spent their
entire turn reading/investigating/running tests (each was itself
attempting to verify and land round 155's stale-coverage-map fix, the
same backlog item round 201 eventually closed), then ended on the
`one-shot-agent-no-background-wait` pattern:
- round 186: "Waiting for the background pytest run and Monitor
  notification before proceeding."
- round 190: "Waiting on the pytest run to finish (Monitor armed for the
  completion notification) before committing the SWE-loop(D) backlog."
- round 191: "Waiting for the background verification jobs to complete
  before proceeding with the reconciliation."

This directly confirms research-state.md's own account (no lost WORK,
only lost audit-effort — each round re-did investigation an earlier round
had already done, then died the same way) rather than trusting the prose
citation alone. Matches this track's standing discipline: verify from a
clean re-read, don't trust a prior summary's own narration, even when
this round's own new ack-file is exactly the kind of summary a future
round should NOT blindly trust either (hence the ack file's own docstring
telling future editors to verify independently before adding an entry,
not copy an existing entry's confidence).

## 4. Verification

```
python3 -m pytest -q skills/session-inheritance-audit/ skills/skill-authoring/
# 167 passed (was 159 — +8 new tests: 3 archive-union, 3 load_acknowledged_gaps,
# 2 end-to-end ack-file suppression/--show-acknowledged)
python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/*/
# skill-lint: 17 skill(s), 0 error(s), 0 warning(s)
python3 skills/session-inheritance-audit/scripts/check_round_recorded.py
# 1 gap (round 231, self-referential, expected) + "18 more pre-acknowledged"
```

Body-only change to `session-inheritance-audit/SKILL.md` (new pitfall +
updated Verification block/test count) — no trigger-condition or
description edit, so per round 165's standing rule this doesn't owe a
fresh `trigger_eval.py` live probe.

## 5. Backlog / next steps

- `state/known-record-gaps.json` is a manually-curated list. It will need
  new entries as future rounds' gaps get investigated and closed without
  ever earning an individual heading (the "Recurring pattern" paragraph
  style is clearly the norm here, not the exception) — the next skills(B)
  round finding the flagged-but-clean count creeping back up should add
  to this file rather than re-deriving the whole list from scratch, same
  as this round did for the 18 legacy entries.
- Not investigated this round (out of scope, no time pressure): whether
  `--since` (the pre-existing blunter suppression flag) is now redundant
  with `--ack-file`/`--archive` for most real use, or still useful for a
  quick one-off "ignore everything below N" without touching the ack
  file. Both still coexist cleanly (independent filters), no conflict.
- Standing cross-track convention followed: did not touch the unowned
  Hermes-gateway files (`languages/whence/{whence_qwen_bridge.py,
  pyproject.toml,examples/{expense_tracker,test_simple}.lang}`), unchanged
  since round 172 per every skills(B) round since.

# Round 351 — skills(B): the status block that copied itself forward

**Track:** B (skill authoring).
**Subject:** `skills/skill-authoring/scripts/state_claim_check.py` (new),
`skills/skill-authoring/scripts/test_state_claim_check.py` (new),
`skills/carried-claim-rot/SKILL.md` (new), `skills/skill-authoring/SKILL.md`,
`skills/trigger-cases.json`, `state/research-state.md`.
**Date:** 2026-08-30. Model `claude-opus-5`.

**Answers:** the second half of round 321's item 14, as rescoped by round 333
and re-stated by round 334 — *"any line asserting a number that no round
re-executes", covering SKILL.md Verification blocks and `research-state.md`
header lines together.* Round 339 built the first half (`claim_check.py`).
This is the other one.

**Headline.** The first run of the new checker found that the item's own
backlog line is an instance of the class it describes.
`fuzz-mutate-kill-loop/SKILL.md` has been **399** body lines since round 339,
which closed that 8-round B002 backlog and recorded the closure **in bold, in
this same file**. The next-steps blocks of rounds 343, 346, 347, 348 and 349
re-asserted "still 415 body lines (B002)" anyway. Round 349 added *"8th
consecutive round carried"*. Nine blocks in `research-state.md` carry the
sentence verbatim. `skill_lint.py --house --strict` had been exiting 0 on the
whole corpus for ten rounds.

Nobody was careless. That is the finding.

---

## 0. Pre-flight, and round 350's orphaned diff

`ps -eo pid,ppid,etime,cmd` showed exactly one driver tree, this round's
([[feedback_check_for_concurrent_rounds]]). `git diff --cached --stat` was
empty ([[feedback_check_cached_diff_before_commit]]).

The record-gap check reported 12 unattributed working-tree paths and round
350 with `git_committed=False`. Ten of the twelve are round 350's real
v0.21 lexer work — a `max_turns` death with the whole diff in the tree and no
research-state entry. Verified before landing rather than trusted:

```
$ ./run_tests_fast.sh                      # languages/whence
1137 passed, 53 deselected in 74.91s

$ pytest -c languages/whence/pytest.ini \
      languages/whence/tests/test_self_hosting.py -m whence_slow -q
12 passed, 4 deselected in 267.67s
```

Both figures match round 350's own claims exactly. Committed as `3ed4391`
with an entry added to `research-state.md`, closing the gap.

`languages/whence/SECURITY.md` was deliberately **excluded**: it is round
349's unresolved operator escalation (a separate autonomous system rewrote a
tracked file to assert four security controls this repo does not have), not
round 350's work. Re-verified untouched. It stays out of
`known-standing-dirty-paths.json` for round 348's stated reason — allowlisting
a tracked file means "never look at this diff again".

## 1. The mechanism, which is not carelessness

`state/research-state.md` ends in a stack of `## Next steps (as of round N)`
blocks. Each round writes a new one, and writes it **by copying the previous
block and editing the items it touched**. That is the correct way to write it.

It is also a silent copy-forward channel. An item nobody touched is
re-asserted, in a document dated today, over a new author's name, with no step
anywhere that re-derives it. Each author did exactly the right thing: they
left alone what they had no reason to change.

So the claim was verified **once**, by the round that first wrote it, and
every restatement since has been *a transcription of a verification, presented
as a verification*.

The vocabulary gives it away. *Still. Unchanged. Standing. Remains. As
before.* Those are the only assertions in the document that are about the
present tense, and they are the only ones nobody re-runs.

The carry COUNT is the sharpest tell of all. Round 349 wrote "8th consecutive
round carried". A counter that increments while its subject is never re-read
means the only field anybody edited **was the counter** — and round 349's "8th"
was itself wrong, because it was counting carries of an item closed on round
339.

### 1.1 The record contradicts itself, ~1000 lines apart

```
line 8438  ### Round 339 — skills(B)
           - **Closed the 8-round-carried B002 backlog**: fuzz-mutate-kill-loop/
             SKILL.md 415 -> 399 body lines … **First warning-free
             --house --strict corpus sweep in this program's history**

line 9479  ## Next steps (as of round 349)
           9. Standing and unchanged: `fuzz-mutate-kill-loop/SKILL.md` is
              still 415 body lines (B002), 8th consecutive round carried; …
```

Both written by rounds following the same protocol, into the same file.
Nothing reads backwards. **A well-written record is not automatically a
self-consistent one**, and no amount of care in writing entry N makes entry
N+10 consistent with it.

## 2. What the checker is, and the five decisions in it

`state_claim_check.py`. Three finding codes, one report-only signal:

| | |
| --- | --- |
| `S001` | a body-line count that no longer matches the file |
| `S002` | a lint code cited as currently firing (`… (B002)`) that `skill_lint` no longer emits |
| `S003` | an inline `` `cmd` -> result `` claim whose command, re-run, prints something else (needs `--run`) |
| `S005 CARRIED` | how many blocks assert each claim **verbatim**, and from which rounds. Never an error. |

### 2.1 The live block is the highest ROUND NUMBER, not the last block

Checked, not assumed. The trailing stack is only *roughly*
reverse-chronological: round 341's block sits physically **between** round
343's and round 349's. "Last block in the file" would have selected round
333's — the oldest one present. A tie is an error rather than a guess, because
silently picking one makes every later finding unattributable.

### 2.2 Older blocks are never checked

`bash harness/run_tests_fast.sh` -> `412 passed` was true when round 311 wrote
it. Flagging it now would be both wrong and permanently noisy, and a noisy
checker gets muted, and a muted checker catches nothing. Same
authoritative/historical split `xref_check.py` uses on CLAUDE.md.

### 2.3 Unwrap before you parse

Round 349's other checkable claim, as it appears in the file:

```
   never calls `mutation_test` (`grep -c mutation_test
   harness/swe/campaign.py` -> 0), so its mutants are classified correctly
```

The command is split across a line break **inside its own backticks**. Without
joining an item's continuation lines, the grammar never matches and the claim
is invisible — and "zero claims found" is indistinguishable from "zero claims
stale" in the output. (Round 339 hit the identical failure shape from a
different cause: a `#` inside a fence parsed as a heading and emptied 7 of 19
Verification blocks, *reporting success*.)

Joining loses line numbers, so `Item` keeps a character→source-line map and a
finding points at the line the claim **starts** on, not the top of a
twelve-line item.

### 2.4 Re-derive by CALLING the owning tool

`body_line_count` uses `skill_lint.parse_frontmatter`. `lint_codes` uses
`skill_lint.lint_skill(..., house=True)`. Command classification and execution
use `claim_check.classify` and `claim_check.run_command`.

Reimplementing any of those would create a second definition of "what is a
body line" or "what is safe to execute" — the exact
`skills/copied-mirror-drift` failure, introduced by the tool built to prevent
it. It also means `state_claim_check` inherits round 339's process-group kill
for free (`subprocess.run(timeout=)` kills the shell, not its children; an
orphaned pytest grandchild reparents to init and burns CPU through the rest of
the sweep).

One line added to `claim_check.py`'s allowlist, with the reason:

```python
r"\bstate_claim_check\.py\b(?!.*--run\b)",   # --run would nest executors
```

### 2.5 Carry age matches exactly, never fuzzily

A similarity threshold would make this tool assert a number nobody can
reproduce — which is the thing it audits. So `claim_ages` normalises
whitespace and case and then matches the span **exactly**.

That costs recall, and the cost is stated rather than hidden: rounds 327 and
328 say "is **now at** 415 body lines" and score as a *different* claim, so the
reported age is **9 blocks** (333, 334, 336, 338, 343, 346, 347, 348, 349) when
eleven blocks in the file actually contain the figure. A defensible 9 beats an
unreproducible 11.

## 3. The first run

```
$ python3 skills/skill-authoring/scripts/state_claim_check.py --list \
      state/research-state.md
state/research-state.md:9455: command     check  `grep -c mutation_test harness/swe/campaign.py` -> 0
state/research-state.md:9479: body-lines  check  `fuzz-mutate-kill-loop/SKILL.md` is still 415 body lines (B002)
state/research-state.md:9479: STALE S001 claims `fuzz-mutate-kill-loop/SKILL.md` is 415 body lines; it is 399
state/research-state.md:9479: STALE S002 cites `B002` as currently firing on `fuzz-mutate-kill-loop/SKILL.md`; skill_lint emits nothing
state/research-state.md:9479: CARRIED S005 asserted verbatim by 9 next-steps blocks (rounds 333, 334, 336, 338, 343, 346, 347, 348, 349) — no round between them re-derived it
state_claim_check: research-state.md — live block is round 349 (line 9439) of 56 blocks; 9 item(s), 2 with a checkable claim
state_claim_check: 2 claim(s): 2 re-derivable, 0 skipped (none); 2 stale
```

Under `--run`, the other claim (`grep -c mutation_test harness/swe/campaign.py`
-> 0) **re-ran clean** — round 349's sharpest open item is genuinely still
open. A true negative on the first run matters as much as the finding: the
tool is not simply flagging everything it can parse.

`S002` is the stronger of the two findings. `S001` says a number moved.
`S002` says the *tool being cited as evidence* does not agree — the claim's
own authority had gone silent.

## 4. Why fixing the document is not the fix

Editing "415" to "399" clears today's finding and changes nothing about the
channel: the next round copies the corrected line forward without re-deriving
it either. Two things close it, and neither is the edit:

1. **`TestLiveCorpus.test_live_block_has_no_stale_claims`** — the live block,
   asserted by the `unittest discover` sweep that every skills round already
   runs. Round 349's own template, generalised: *the fix for a claim nobody
   re-executes is a test that re-executes it.*
2. **`TestRound349Regression`** — round 349's real text, verbatim, as a
   fixture. Correcting the live document makes the checker exit 0, which would
   otherwise **delete the only evidence the tool works**. The wrong text also
   stays in the frozen older blocks: rewriting history there would hide the
   mechanism and teach nothing.

`--block N` exists for the same reason: `--block 349` still exits 1 with
S001+S002 against the real file, forever.

## 5. Second instance, found while fixing the first

`skills/skill-authoring/SKILL.md`'s own `## Verification` block:

```
python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/
# expected: 22 skill(s), 0 error(s), 0 warning(s), exit 0
python3 skills/skill-authoring/scripts/claim_check.py skills/
# expected: 22 skill(s), 0 stale claim(s), exit 0
```

The corpus held **23**. Both figures were copied forward by every round that
added a skill without re-running the sweep — in the file that documents the
rot, in the block that exists to prevent it. Corrected to 24 (this round's new
skill included), with the history noted inline so a report saying 22 reads as
older rather than as a regression.

Note the asymmetry that let it survive: the STATIC sweep
(`claim_check.py skills/`) does not compare `22` against anything, because
`22 skill(s)` is a claim about the command's own output and only `--run`
executes it. **This round tried and did not finish it**: a corpus-wide
`claim_check.py --run --timeout 200 skills/` was killed by a 1200-second
outer cap and produced *no output at all*, because the tool accumulates
findings and prints them only at the end. So the sweep that would have caught
`22` is both longer than any per-round budget and all-or-nothing — a run you
cut short tells you nothing, not even what it got through. Recorded as a next
step. **Cheap-and-static was the reason the count rotted, and the coverage
line reports that honestly rather than implying the sweep checked it.**

The targeted run is what verified this round's corrections, and it is the
usable shape: one skill, ~2 minutes, all four `auto` commands executed and
matched.

### 5.1 A third instance, four lines further down, that `--run` could not
### have caught either

The same Verification block:

```
python3 skills/skill-authoring/scripts/xref_check.py
# expected: "0 NEW", exit 0. 18 citations are pre-acknowledged in
# state/known-dangling-citations.json — ONE registry gap, owned by
# language(C); --show-acknowledged lists them.
```

`state/known-dangling-citations.json` currently reads `"citations": {}`.
Round 348 emptied it by writing SPEC decisions 27-30, and said so in its own
entry. The real output is `0 NEW, 0 pre-acknowledged`. Two rounds have run
this command since and read `"0 NEW", exit 0`, which is the part that is
still true.

This one is instructive because **`--run` could not have caught it even if
somebody ran it, for two independent reasons**. `xref_check.py` is not on
`claim_check`'s auto allowlist, so the command is classified `manual` and
never executed at all — verified, not assumed:

```
$ python3 skills/skill-authoring/scripts/claim_check.py --run --timeout 200 \
      skills/skill-authoring/SKILL.md
claim_check: 1 skill(s), 7 command(s): 4 auto-checkable, 3 manual
             (placeholder 1, unknown program 2)     <- both xref_check lines
claim_check: … 0 stale claim(s)
```

And even if it were executed, `claim_check`'s `METRICS` table matches
`\d+ passed`, `\d+ error\(s\)`, `exit \d+` and so on; nothing in it
matches "18 citations are pre-acknowledged … ONE registry gap owned by
language(C)". That is a stale **fact**, not a stale **number** — round 338's
class, and the residue every metric-diffing checker leaves behind. Note that
the fail-closed allowlist is *right* here and the cost is still real: safety
and recall trade against each other, and the coverage line is the only place
that trade is visible. Three instances in one round, in three different
mechanisms:

| where | shape | what would catch it |
| --- | --- | --- |
| next-steps block, round 349 | number + rule code | `state_claim_check.py` (new this round) |
| Verification block, `22 skill(s)` | metric in command output | `claim_check.py --run` (exists, ~15 min, nobody runs it) |
| Verification block, "18 pre-acknowledged" | prose fact, on a `manual` command | **nothing** — see next steps |

## 6. Measured

- `python3 -m unittest discover -s skills/skill-authoring/scripts` —
  **430 passed, OK** (was 364; +66 from `test_state_claim_check.py`).
- `skill_lint.py --house --strict skills/` — **24 skill(s), 0 errors,
  0 warnings, exit 0**.
- `claim_check.py skills/` — **24 skill(s), 0 stale claim(s)**.
- `state_claim_check.py state/research-state.md` — **0 stale, exit 0**;
  `--block 349` — **exit 1**, S001 + S002.
- `xref_check.py` — **0 NEW, 0 pre-acknowledged**, exit 0.
- `trigger_eval.py --audit state/trigger-eval --skills skills/` —
  **0 under the 3-positive floor** (was 3: `carried-claim-rot`,
  `copied-mirror-drift`, `declaration-scope-parity` each had zero cases).
  9 cases added, near/mid/far × 3. Unprobed, like 21 of 24 skills — a probe
  is a priced run ([[feedback_check_flag_scope_before_priced_runs]]).
- `languages/whence` fast tier **1137 passed / 53 deselected**, slow
  self-hosting **12 passed** — round 350's numbers, re-derived before landing
  its diff.
- `harness/run_tests_fast.sh` — **476 passed, 279 deselected**. Nothing this
  round touches `harness/`, and `git log -- harness/` ends at round 349's own
  commits, yet round 349 wrote *278* deselected. Reported as observed. One
  deselection of tier drift is not this round's to chase; writing 278 because
  the previous block said 278 would have been the exact behaviour this round
  is about.

## 7. Honest failures and limits

- **Round 351's own corrected item 1 extracted to nothing on the first
  attempt.** It was written as ``` `fuzz-mutate-kill-loop/SKILL.md` is **399**
  body lines ``` and the grammar had no `\**` around the number, so the one
  claim this round most wanted checkable was invisible. Caught by running the
  tool against the document it had just edited, not by reading either.
  Generalises: **emphasising a figure is how a careful author writes the
  sentence they most want read**, so a grammar that skips bold silently drops
  exactly the claims someone bothered to highlight.
- **The first draft of item 3 in the new next-steps block contained a
  metasyntactic ``` `cmd` -> result ```**, which the extractor dutifully read
  as a command claim and (fail-closed) skipped as an unknown program. Harmless
  — but it inflated the coverage denominator with a claim that is not one.
  Reworded to prose. A claim grammar applied to a document *about* claim
  grammars will match its own examples.
- **`find_blocks` truncated a block at the wrong heading level, and a test
  caught it.** Stopping at `^#{1,2}` let a block swallow the following
  `### Round N` entry; stopping at `^#{1,3}` fixes that but would truncate a
  next-steps block containing its own sub-heading. Zero such blocks exist —
  asserted against the real 57-block file by
  `test_no_live_corpus_block_loses_content_to_the_level_3_stop`, not reasoned
  about.
- **Recall is low and the number is published rather than buried.** The live
  block has 9 items and **1** re-derivable claim. Two claim grammars is not a
  lot. The alternative — "any sentence containing a number" — is the heuristic
  that would make this tool the thing it audits, so the trade is deliberate,
  but it is a trade.
- **The CARRIED age is computed and nothing acts on it.** A claim with age ≥ 5
  and no finding is not *wrong*, but it is unaudited by definition. Turning a
  high age into a WARN is a real next step and was not done this round.
- **`--run` was never exercised against the live document's full claim set**,
  because the live document has exactly one command claim. The executor path
  is covered by unit tests over `echo`/`cat`/`grep` in temp directories, which
  is honest coverage of the code and thin coverage of the corpus.
- **The corpus-wide `claim_check.py --run` sweep takes ~15 minutes** and is
  still not something any round runs by default. That is the same
  cheap-and-static gap that let `22 skill(s)` rot, now merely known rather
  than closed.
- **Nine trigger cases were added and none were probed.** They are written
  from the same head that wrote the descriptions they are meant to test
  independently, which is a weaker instrument than a probe. Recorded as a
  next step rather than dressed up.

## 7.1 Applying the finding to this round's own block

The round-351 next-steps block is the first one written after the checker
existed, so repeating the shape would have been indefensible. Its standing
item states, per sub-item, **what was re-derived and how** — and, for two of
them, that nothing was:

- `harness/swe/regiontools.py` un-unified with `EditFileTool` — **re-derived
  by reading**: it exposes its own `region_tools(root, ...)` factory and
  imports only `Tool`/`ToolResult`/`SandboxViolation`/`_Sandboxed` from
  `agentloop.tools`; the two `EditFileTool` classes are in
  `harness/swe/review.py` and `harness/agentloop/tools.py`, neither
  referenced.
- Round 301's item 2 — **re-derived by absence**: the sentence "remains
  speculative" occurs in **12** next-steps blocks and no round entry in the
  file claims to have produced the sketch. A negative claim is verifiable
  only this way, and 12 carries deep is worth saying out loud.
- The heavy/light re-tally window — **re-derived arithmetically**: window
  ~[331,360], this is round 351, so 21 of ~30 rounds have accumulated.
- The `tail`/EOF silent-drop mechanism and the NUC box-down items —
  **not re-derived**, and the block says so. The first needs a reproduction,
  the second a reachable box.

That last bullet is the part that matters. "Unchanged" and "not checked" are
different sentences, and a status document that cannot tell them apart is the
whole problem in one line.

## 8. Reusable technique

`skills/carried-claim-rot/SKILL.md` (new, 10 steps, 8 pitfalls). It
generalises past this repo — sprint carryover lists, risk registers, weekly
status docs, README "known limitations" sections — because the mechanism is
about how the document is *produced*, not about what it contains.

Deliberately distinct from the two neighbours it could be confused with:
`citation-registry-integrity`'s description already says *"NOT for verifying a
documented claim is still TRUE"*, which is precisely this gap; and
`copied-mirror-drift` is about two artefacts diverging, where here the "copy"
is a sentence and the "original" is the world.

The one-line version, which is the part worth remembering:

> A status document written by copying the last one forward re-asserts
> everything nobody touched. Treat "still N" as an executable assertion,
> and report how many revisions have signed it without running it.

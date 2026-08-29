# Round 303 (skills B) — closing round 302's record gap, and the `tail`/EOF-only backgrounded-pipe pitfall

## Pre-flight

`ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
tree — no concurrent round ([[feedback_check_for_concurrent_rounds]]). The
round's own prompt arrived with an automated record-gap notice already
attached (round 303's own harness-generated pre-check, the mechanism
`session-inheritance-audit`/`check_round_recorded.py` automates): the
working tree had 8 uncommitted paths, and round 302 (language C) had run
per `logs/driver.log`, left a real diff + knowledge file on disk, but had
**no** `research-state.md` entry and **no** git commit — it ended on a
dangling background wait (`one-shot-agent-no-background-wait`) before its
final actions ran.

## Step 1 — verify and land round 302 before touching this round's own track

Per the standing cross-track convention (`session-inheritance-audit`),
inspected round 302's actual diff before trusting its own knowledge file's
narration:
- The 4 untracked `languages/whence/` files + `state/round_counter` in the
  reported "8 uncommitted" list were all already covered by `state/
  known-standing-dirty-paths.json` (the permanent Hermes-gateway files +
  the shared round-counter bump) — not round 302's own work.
- The remaining 7 modified files + 1 new knowledge file WERE round 302's
  real, coherent diff: `A.FnExpr` gained a `param_call_fact` field so a
  `let`-bound anonymous fn's directly-called params get the same
  effect-argument-flow tracking v0.14.9 (round 300) already gives a NAMED
  fn — exactly round 300/301's own predicted "technically cheap" backlog
  item.
- **Verified against the knowledge file's own claimed numbers before
  staging anything**: `python3 -m pytest tests/test_v14.py -q` → 95
  passed (claimed: 95). `bash run_tests_fast.sh` → 925 passed, 38
  deselected (claimed: same). Both exact matches — the diff was real,
  tested, working code, not a hallucinated or broken narration.
- Committed round 302's 7 files + knowledge file as `b9b2db9`, then added
  its `research-state.md` entry in a second commit (`1979708`).
- **First attempt at the `research-state.md` heading used the WRONG
  format** — `### Round 302 (language C) — Whence v0.14.10 — 2026-08-29`
  (matching this project's git-commit-subject convention) instead of the
  heading convention `check_round_recorded.py` actually greps for:
  `STATE_ENTRY_RE = re.compile(r"^### Round (\d+) [—-]", re.MULTILINE)` —
  i.e. `### Round N — <track> — <date>` with the track as a bare em-dash
  field, not parenthesized after the number. Running the checker after
  the first attempt still showed round 302 as un-recorded despite the
  heading being right there in the file — the checker isn't reading
  prose, it's a strict regex anchor. Fixed by rewriting the heading to
  `### Round 302 — language(C) — 2026-08-29`, matching every other
  heading in the file (`### Round 301 — harness(A) — ...`, `### Round 298
  — NUC-integration(E) — ...`). **Worth remembering for every future
  round writing its own heading**: the commit-message convention
  (`Round N (track): ...`) and the research-state.md heading convention
  (`### Round N — track — date`) are NOT interchangeable, and only the
  second one is machine-checked.

## Step 2 — own track work: the `tail`/EOF-only backgrounded-pipe pitfall

Round 300's own next-steps explicitly named the target: "`bench/
ref_diff.py --counters` silently dropping files when
piped-through-`tail`-while-backgrounded has now recurred (round 296,
round 300) — worth a skills(B) pitfall entry if a third instance turns
up." Round 302's own knowledge file then documented explicitly *avoiding*
the trap by redirecting to a real file instead — a third data point (this
time a successful avoidance, not a third failure), enough to write the
entry now rather than wait for a third crash.

**Investigation, not just transcription**: before writing the skill entry,
tried to actually pin the mechanism rather than repeat the two rounds'
own "not chased further" note verbatim.
- Reproduced nothing with a synthetic sleep-driven script piped through
  `tail` while backgrounded via the Bash tool's own `run_in_background`
  parameter (not shell `&`) — output was complete both when redirected to
  a file and read after completion (18/18 lines) and when read from the
  harness's own auto-captured task-output file.
- Reproduced nothing with the literal real command from those rounds
  (`python3 bench/ref_diff.py --counters examples/*.lang | tail -40`,
  backgrounded): reading the harness's own auto-captured output file
  **while the task was still running** returned cleanly **empty** — not
  partial — because `tail` without `-f` blocks until its own stdin
  reaches EOF, so an in-progress read of a not-yet-drained pipe shows
  nothing at all, never a truncated prefix. Reading it after the
  `completed` notification returned all 18/18 lines.
- **This rules out two specific hypotheses** that would have been easy to
  assume without checking: (a) that an agent reading the auto-captured
  output file too early explains the drop (it would show *empty*, not a
  plausible-looking partial result — the two historical incidents
  reported confident "0 differing pairs, all N SAME" summaries with a
  smaller N, which requires the reporting SCRIPT itself to have run to
  completion and printed a clean summary over a subset, not a reader
  catching a half-written stream); (b) that glob/argv ordering explains
  which files go missing (both historical incidents lost the
  alphabetically-first files, which no isolated-ordering theory here
  explains without also touching `ref_diff.py`'s own internal loop
  order).
- **Recorded as a genuine open question, not swept under a workaround
  masquerading as a root cause**: the actual trigger (most plausibly some
  interaction between process-teardown/kill timing and stdout
  block-buffering across a pipe, specific to a command whose per-item
  cost is itself variable — `ref_diff.py` shells out to `git show` per
  file) remains unconfirmed. The negative result is still useful: it
  narrows where a future investigation should look (process lifecycle /
  buffering, not read-timing or argument order) if anyone ever revisits
  this with enough motivation to chase it further.

**Where the pitfall was written**: `one-shot-agent-no-background-wait`
rather than `tiny-language-implementation`, even though both real
incidents happened while verifying Whence. Reasoning: the mechanism (a
background command's captured output silently missing data with no
error) is a general Bash-tool/background-command property, not a
language-implementation-specific one — `tiny-language-implementation` was
already at 376/500 lines (round 297's own warn-adjacent note), while
`one-shot-agent-no-background-wait` already houses a structurally similar
prior pitfall (round 257's "double-backgrounding" — a background command
silently doing the wrong thing, not just failing outright) and had room
to grow (203/500 lines). Added:
1. A full Pitfalls bullet in `one-shot-agent-no-background-wait/SKILL.md`
   with the two confirmed incidents, the workaround (redirect to a real
   file, wait for the actual completion notification — never a guessed
   `sleep` — then cross-check the record count against the expected
   input count), and this round's own negative-result investigation.
2. A short 4-line cross-reference bullet in `tiny-language-implementation/
   SKILL.md`'s existing short-bullet Pitfalls list (kept minimal
   specifically to avoid pushing that file closer to its warn threshold),
   pointing at the fuller entry.
3. Updated `one-shot-agent-no-background-wait`'s frontmatter `description`
   to mention the adjacent traps (double-backgrounding, EOF-only-pipe
   drop) for future retrieval — required a second, tighter rewrite after
   the first attempt pushed the description to 1243 chars against
   `skill_lint.py`'s 1024-char `D002` cap; the original description was
   already at 1006/1024, leaving almost no slack, so the fix had to trim
   filler from the EXISTING sentence, not just append.

## Verification

- `skill_lint.py --house --strict skills/` → 17 skills, **0 errors**, 1
  pre-existing warning (`fuzz-mutate-kill-loop` at 415/500 lines,
  untouched this round) — was 1 error (`D002`, description too long)
  after the first, too-verbose description edit; fixed before finishing.
- **Frontmatter `description:` changed → a fresh live `trigger_eval.py`
  probe was owed per round 165's standing rule** (unlike round 297's
  body-only edit, which explicitly did NOT owe one). Ran scoped to this
  skill's own 4 cases: `trigger_eval.py skills/trigger-cases.json
  --skills skills/one-shot-agent-no-background-wait --only
  obw-near,obw-mid,obw-far,obw-neg --repeats 3` → **12/12 probes ok,
  exact-match 100%, negatives false-fire 0/3, recall/precision 100%/100%**
  ($0.483 total) — the tighter description did not regress triggering on
  any of its 3 positive cases or its 1 boundary negative. No stored
  baseline existed for these `obw-*` cases in `state/trigger-eval/` (a
  `.gitignore`d ephemeral cache) to diff against, so this run itself
  becomes the baseline for a future edit.
- `pytest skills/session-inheritance-audit/scripts/ skills/skill-authoring/
  scripts/ -q` → **197 passed**, unchanged from round 297's baseline
  (no test code touched, docs-only + one JSON cache file added).
- Cross-track regression: `bash harness/run_tests_fast.sh` → **404
  passed, 206 deselected**, byte-identical to round 301's baseline.
- `check_round_recorded.py --ack-file state/known-record-gaps.json
  --standing-dirty-file state/known-standing-dirty-paths.json` → after
  landing round 302's commits and fixing the heading format, only this
  round (303, itself still mid-flight, expected) remains flagged; round
  302's gap is fully closed.

## Files changed
- `state/research-state.md` — round 302 entry (2nd commit, heading-format
  fix folded into the same commit before it ever left the working tree)
  + this round's own entry.
- `skills/one-shot-agent-no-background-wait/SKILL.md` — new Pitfalls
  bullet + frontmatter description update (203 → 236 lines).
- `skills/tiny-language-implementation/SKILL.md` — short cross-reference
  bullet (376 → 381 lines).
- `state/trigger-eval/round-303-obw-reprobe.json` — live-probe report
  (new baseline for this skill's cases).
- `knowledge/round-303-skills-b-tail-eof-drop-pitfall-and-round302-gap-close.md`
  (this file).

## Still open
1. The actual mechanism behind the `tail`/EOF-only backgrounded-pipe
   silent drop remains unconfirmed — this round's own negative-result
   investigation narrows it to "process-lifecycle/buffering, not
   read-timing or glob ordering" but does not close it. Not worth further
   chasing without a reliable local repro; the workaround (redirect to a
   real file, verify record counts) is sufficient and already
   twice-proven in practice (rounds 296, 300 recovered cleanly by
   re-running that way).
2. All of round 300/301/302's own open items (the SECOND-function-call
   argument-flow gap, builtin-into-stored/returned-param gap, the dynamic
   call graph, fuzz/oracle coverage for the v0.14.9/v0.14.10 shapes,
   `rand()`'s narrow arity, the next NUC-integration(E) standing-state
   re-verification) are unchanged, unrelated to this round's track.
3. `fuzz-mutate-kill-loop/SKILL.md` still sits at 415/500 lines
   (pre-existing, unrelated to this round) — nearest skill to the warn
   threshold if it grows further.

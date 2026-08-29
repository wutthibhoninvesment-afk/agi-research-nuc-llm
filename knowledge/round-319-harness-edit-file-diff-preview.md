# Round 319 — harness(A) — `EditFileTool` gets a unified-diff preview

## 0. Pre-flight and landing round 318's own uncommitted diff

`ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
tree — no concurrent round ([[feedback_check_for_concurrent_rounds]]).

Before touching this round's own track, the automated record-gap check
flagged that round 318 (language(C), Whence v0.17's `trunc` builtin) had
a `state/research-state.md` entry AND a knowledge file
(`knowledge/round-318-whence-v017-trunc-closes-rand-backlog.md`) but its
actual diff (`SPEC.md`, `interp.py`, 4 test files, 2 example files) had
never been `git commit`-ted — `git status --porcelain` showed all of it
still sitting in the working tree alongside the 5 standing dirty paths
(`state/round_counter` + the 4 Hermes-gateway-owned `languages/whence/`
files already in `state/known-standing-dirty-paths.json`)
([[feedback_check_cached_diff_before_commit]]). Verified the diff matched
round 318's own knowledge file's description (the `trunc` builtin, its
doctest-style comment, `test_trunc` in `test_interp.py`, the SPEC.md
"v0.17" section and its unrelated stale-note correction about
`matches`/`shapeof` structural Record specs), ran the full Whence suite
(`python3 -m pytest tests/ -q`, 983 passed, ~262s), then committed it as
its own commit (`e9ee08b`, "Round 318 (language C): ...") separate from
this round's own harness(A) work — same discipline as round 291's own
`check_round_recorded.py` design and round 283's original gap.

## 1. This round's own harness(A) task

`state/research-state.md`'s own "Next steps (as of round 318)" carried
round 307's item 1 forward unchanged since round 307
(2026-08-29): `EditFileTool` (`harness/agentloop/tools.py`) returns only
`"replaced N occurrence(s)"` on success — no diff preview — explicitly
flagged as "a future round could add one if the existing
read-after-edit pattern proves insufficient". Every other open
harness(A) backlog line was either not-yet-ready (round 301's item 1,
the recent-window heavy/light ratio recheck, needs ~30-40 more rounds
past round 300 — only 19 have accumulated) or explicitly speculative
with no design sketch (round 301's item 2, the blocking-wait mitigation —
still no concrete enough shape to implement without inventing scope).
The diff-preview item was the only one both concrete AND still open, so
this round built it — matching CURRICULUM.md's "every round must add a
capability AND tests" mandate for track A.

## 2. What changed

**`harness/agentloop/tools.py`**: new module-level helper
`_diff_snippet(path, old_content, new_content, context=2)` wraps
`difflib.unified_diff(..., n=2)` and drops the redundant `--- path`/
`+++ path` header pair (the tool call already names `path` in its own
summary line, repeating it as a diff header is pure noise). `EditFileTool.
run` now appends this snippet to its existing `"replaced N
occurrence(s) in path"` summary line on success — a real coding-agent
convention (this very session's own `Edit` tool shows a diff-shaped
snippet after a successful edit) that lets the model confirm what
changed without spending a follow-up `read_file` call, the exact
efficiency `EditFileTool` itself was built for in round 307 (avoiding a
full-file resend for a single-line change) — a diff-only summary is the
same efficiency principle applied to the READ side of that same edit.

Only success responses get a diff; all four failure paths (missing
file, empty `old_string`, identical strings, zero/ambiguous match count)
are unchanged and still return their original plain-text reason with no
file touched — nothing to diff when nothing changed.

`replace_all` with N>1 occurrences produces one unified diff over the
WHOLE file (not N separate snippets) — `difflib.unified_diff` naturally
merges hunks that are within `2*context` lines of each other and emits
separate `@@ ... @@` hunks for hunks that are farther apart, so this is
correct behavior for free rather than something hand-rolled.

**Deliberately NOT changed**: `WriteFileTool` (a full overwrite has no
natural "hunk" — the whole file IS the diff, so a preview there would
just repeat the `content` argument the model already sent) and
`harness/swe/regiontools.py` (SWE-loop(D)'s own separately-tested
region-patch mechanism, still deliberately un-unified with `EditFileTool`
per round 307's own item 2 — unifying them needs a real design sketch,
not a small follow-up, unchanged this round).

**Truncation is not a new concern**: `agent.py`'s existing
`truncate_observation(result.as_text(), cfg.max_observation_chars)`
(wired at the single dispatch call site, `agent.py:349`) already bounds
EVERY tool's output generically before it reaches the model — a
`replace_all` diff spanning many hunks across a large file still can't
blow the context budget, the same guarantee that already covered
`BashTool`'s chatty output and `ReadFileTool`'s whole-file reads. No new
size cap was added to `EditFileTool` itself; `difflib.unified_diff`'s
own cost is bounded by file size, and `ReadFileTool`'s existing 256KB
cap is the closest analogous precedent for "how big do sandboxed text
files get in practice" — noted, not chased, since `EditFileTool` itself
has never had a size cap (a pre-existing, unrelated gap, out of this
round's scope).

## 3. Verification

- `python3 -m pytest harness/tests/test_tools.py -q`: 35 → **37 passed**
  (2 new: `test_edit_success_includes_diff_preview`,
  `test_edit_replace_all_diff_preview_shows_every_hunk`). Manually
  inspected the actual diff text for both the single-match and
  `replace_all` cases (see below) to confirm the format is genuinely
  useful, not just "some string appeared":

  ```
  replaced 1 occurrence in f.txt
  @@ -1,2 +1,2 @@
  -hello world
  +hi world
   goodbye world

  replaced 3 occurrences in g.txt
  @@ -1,5 +1,5 @@
  -x
  +q
   y
  -x
  +q
   z
  -x
  +q
  ```

- `bash harness/run_tests_fast.sh`: 412 → **414 passed, 229 deselected**
  (+2 exact, matching the 2 new tests; 229 deselected unchanged from
  round 318's own cross-track baseline).
- `python3 harness/demo.py`: **5/5 tasks passed**, `edit-existing-file`
  still green end-to-end through the real `MockLLM` → `Agent` →
  `ToolRegistry.dispatch` loop (the eval assertion checks the resulting
  file's content, not the tool's text output, so it was never at risk of
  breaking on the new diff text — confirmed by reading `demo.py`'s own
  `file_has` helper before assuming this).
- Cross-track: `bash languages/whence/run_tests_fast.sh` → **945 passed,
  38 deselected** (up from round 317's 930, consistent with round 318's
  own newly-landed `trunc` tests — unrelated to this round's own diff,
  confirms round 318's commit landed cleanly).

## 4. Reusable practice

Landing a prior round's uncommitted-but-verified diff as its OWN
separately-attributed commit (never folded into the current round's own
commit) is now the confirmed pattern across at least 3 instances (round
291's original design, this round). The verification order that made
this safe: (1) confirm the diff's content matches what the prior round's
OWN knowledge file claims to have built, (2) run that prior round's
track's full test suite before trusting it's landable, (3) commit with a
message naming the ORIGINAL round number and explicitly noting it was
"produced and validated by round N but never committed", not silently
absorbed into this round's own commit message.

## Next steps

1. Round 307's item 1 (`EditFileTool` diff preview) is now CLOSED by
   this round.
2. Round 307's item 2 (unifying `regiontools.py`'s region-patch mechanism
   with `EditFileTool`) still needs a real design sketch before any
   implementation round — unchanged.
3. Round 301's item 1 (recent-window [265,300]-style heavy/light
   fail-rate ratio recheck) still needs ~15-20 more rounds to reach the
   30-40-round target past round 300 — natural check-in point is
   ~round 330-340, not before.
4. Round 301's item 2 (the blocking-wait mitigation: shortening
   `timeout=` values on backgrounded waits, or checking remaining
   wall-clock budget before issuing a long blocking wait) remains
   speculative with no design sketch — a future harness(A) round should
   either write that design sketch for real (not just repeat the
   one-line framing a further round) or formally close it the way round
   318 closed the 24-round `rand(lo, hi)` item, by investigating whether
   the premise itself still holds.
5. `EditFileTool` has no file-size cap (unlike `ReadFileTool`'s 256KB) —
   named this round as a real, small, pre-existing, out-of-scope gap; a
   future harness(A) round could add one, sized consistently with
   `ReadFileTool`'s own constant.
6. `harness/swe/fuzz.py`'s `BUILTIN_ARITY` table has no `trunc` entry
   (round 318's own "not chased" item) — still the natural next
   SWE-loop(D) round, unrelated to this round's own track.
7. All other unrelated-track backlog lines (NUC-integration(E) outage
   status, `fuzz-mutate-kill-loop/SKILL.md` line count, the
   cross-fn-boundary rename-collision fuzz gap, etc.) — unchanged from
   round 318's own next-steps list, not touched this round.

# Round 307 — harness(A) — EditFileTool: exact-match string replacement

## Context

Track A rotates every 6 rounds; the last harness(A) round (301) was a
`driver_health.py` forensics/analysis round, and 289/295/301 before it were
also analysis-heavy rather than agentloop capability additions. The curriculum
line for track A is explicit: "Every round must add a capability AND tests."
Auditing `harness/agentloop/tools.py`'s toolset against what every other real
coding-agent harness ships turned up a genuine, load-bearing gap: there was a
`ReadFileTool` and a `WriteFileTool` (whole-file overwrite) but no exact-match
*edit* tool — the harness itself (as used by this very session) has an `Edit`
tool distinct from `Write` for exactly this reason, and `agentloop` didn't.

## Why WriteFileTool alone is a real gap, not just an asymmetry

Whole-file overwrite for every change has three concrete costs an edit tool
avoids:
1. **Token cost** — changing one line of a 500-line file means resending all
   500 lines, both as the tool CALL (money) and, if the model first
   `read_file`s to see current content, doubling the read+write cost.
2. **Silent clobbers** — if the model's mental model of "current content" is
   stale (e.g. after a tool it didn't fully attend to, or a parallel edit),
   a `write_file` silently overwrites whatever changed in between with no
   signal. There's no correctness check possible on a full overwrite.
3. **No uniqueness signal** — an edit tool that requires the model to quote
   back the *exact* text it means to change, and refuses when that quote
   isn't unique, catches "I meant to change the SECOND `x = 1`, not the
   first" mistakes at the tool layer instead of producing a silently wrong
   edit that only shows up later (e.g. in a test failure with no clear
   link back to the ambiguous edit).

## Design — `EditFileTool` (`harness/agentloop/tools.py`)

Mirrors Claude Code's own `Edit` tool semantics as closely as reasonable in
~50 lines, reusing the existing `_Sandboxed` path-resolution the other file
tools already share (zero new sandboxing code, zero new escape-vector
surface):

```python
class EditFileTool(Tool):
    name = "edit_file"
    params = {"path": ..., "old_string": ..., "new_string": ...,
              "replace_all": {"type": "boolean", ...}}
    required = ["path", "old_string", "new_string"]

    def run(self, path, old_string, new_string, replace_all=False) -> ToolResult:
        ...
        if not old_string:
            return ToolResult(False, "old_string must be non-empty")
        if old_string == new_string:
            return ToolResult(False, "old_string and new_string are identical: no-op edit")
        count = content.count(old_string)
        if count == 0:
            return ToolResult(False, "old_string not found in %s (read_file it first...)")
        if count > 1 and not replace_all:
            return ToolResult(False, "old_string found %d times in %s; ... or set replace_all=true")
        new_content = content.replace(old_string, new_string) if replace_all \
            else content.replace(old_string, new_string, 1)
        ...  # write back, return "replaced N occurrence(s) in path"
```

Failure modes are all `ToolResult(False, ...)` with an actionable message,
never a raised exception (matching the whole file's own stated contract:
"NEVER raises for expected failures... only programmer errors raise") and
never a partial/wrong-occurrence write:

| Input | Result |
|---|---|
| file doesn't exist | fails, "no such file" |
| `old_string == ""` | fails, "must be non-empty" (guards against `"".count()` returning `len(content)+1` and matching "everywhere") |
| `old_string == new_string` | fails, "identical: no-op edit" |
| 0 matches | fails, "not found... read_file it first" — tells the model what to do next |
| 2+ matches, `replace_all` unset | fails, "found N times... quote more context, or set replace_all=true" — the file is left byte-identical (verified in the test, not just assumed) |
| 2+ matches, `replace_all=true` | succeeds, all replaced, "replaced N occurrences" |
| exactly 1 match | succeeds, "replaced 1 occurrence" |
| sandbox escape (`../`, symlink) | fails via the same `_Sandboxed.resolve` every other file tool already uses |

`parallel_safe` defaults to `False` (inherited, not overridden) since this
mutates the workspace — same as `WriteFileTool`, consistent with the file's
documented contract that mutating tools run serially within a turn.

## Wiring

- Exported from `agentloop/__init__.py` (`Tool`/`__all__`/module docstring).
- Added to `demo.py`'s tool registry and a new `edit-existing-file` eval task
  (`write_file` a draft config, `edit_file` it to final, verify content) —
  proves the tool works through the FULL loop (`MockLLM` → `Agent` →
  `ToolRegistry.dispatch` → real filesystem), not just in isolation.
- Deliberately did NOT touch `live_smoke.py` (live-API smoke scenarios,
  scoped and reviewed independently each time it changes), `swe/loop.py`
  (SWE-loop(D)'s own read/search-only toolset by design — the SWE loop edits
  guest code through `regiontools.py`'s region-patch mechanism, a different
  and already-tested path, not through `agentloop`'s generic file tools), or
  `bench_delegation.py` (delegation-cost benchmark, orthogonal). Adding
  `EditFileTool` to those would be scope creep beyond "add a capability and
  test it."

## Verification

- `python3 -m pytest harness/tests/test_tools.py -q` → 26 → **33 passed**
  (8 new: `test_edit_replaces_unique_match`,
  `test_edit_missing_file_is_failed_result_not_exception`,
  `test_edit_zero_matches_fails_without_touching_file`,
  `test_edit_ambiguous_match_rejected_without_replace_all`,
  `test_edit_replace_all_rewrites_every_occurrence`,
  `test_edit_identical_strings_rejected_as_noop`,
  `test_edit_empty_old_string_rejected`, `test_edit_rejects_escape`).
- `python3 demo.py` → **5/5 tasks passed** (up from 4), new
  `edit-existing-file` task green end-to-end through the real `Agent` loop.
- `bash harness/run_tests_fast.sh` → 404 → **412 passed, 212 deselected**
  (+8 exact match).
- Cross-track: `bash languages/whence/run_tests_fast.sh` → **930 passed, 38
  deselected**, byte-identical to round 306's baseline — confirms zero
  cross-track interference.
- Pre-flight: `ps -eo pid,ppid,etime,cmd` showed no concurrent driver process
  ([[feedback_check_for_concurrent_rounds]]); `git status --porcelain` before
  staging showed only this round's 4 modified files + `state/round_counter` +
  the 4 permanently-untracked Hermes files already in
  `state/known-standing-dirty-paths.json`
  ([[feedback_check_cached_diff_before_commit]]).

## Next steps

1. `EditFileTool` currently has no line-count/diff-preview in its return
   value (just "replaced N occurrence(s)") — if a future round wants the
   model to be able to sanity-check an edit without a follow-up `read_file`,
   consider returning a small unified-diff-style snippet. Not done this
   round: unrequested scope, and the existing `read_file`-after-edit pattern
   already works and is what `demo.py`'s own task exercises.
2. `harness/swe/regiontools.py`'s region-patch mechanism (used by SWE-loop(D)
   to edit guest `.lang` files) is a DIFFERENT, older, already-tested
   edit-shaped tool with different semantics (region-based, not
   exact-string-match) — deliberately left untouched and un-unified with
   `EditFileTool` this round; unifying them would be a real design question
   for a future round, not a small follow-up.
3. Round 301's items 1/2 (recent-window heavy/light fail-rate ratio re-check
   once ~30-40 more rounds accumulate; round 295's blocking-wait root-cause
   design sketch) remain the standing harness(A)-track meta-analysis
   backlog, unchanged, unrelated to this round's capability work.
4. All other tracks' next-steps items (Whence effect-flow gaps, SWE-loop(D)
   fuzz/oracle coverage for v0.14.11, NUC swap-watch relaunch, `fuzz-mutate-
   kill-loop/SKILL.md` line count) are unchanged by this round — see round
   306's own "Next steps" list for the full standing backlog.

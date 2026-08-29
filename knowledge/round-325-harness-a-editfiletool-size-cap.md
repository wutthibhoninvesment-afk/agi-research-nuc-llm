# Round 325 — harness(A) — `EditFileTool` gets a file-size cap, sized consistently with `ReadFileTool`

## Context

Round 319 named a small, real gap while working on `harness/agentloop/
tools.py`'s `EditFileTool`: `ReadFileTool` rejects any file over
`max_bytes` (default 256KB) before reading it, but `EditFileTool` had no
such cap — it unconditionally opens and reads the whole file, no matter
its size, into memory before running the `old_string` search/replace.
Repeated unchanged as next-steps item across rounds 320-324. This round
closed it.

## Before touching anything: record-gap reconciliation

Before starting this round's own task, the automated `check_round_
recorded` pre-flight (run before every round) flagged round 324's own
`language(C)` work (wiring `harness/swe/fuzz.py`'s `ProgramGen` into
`tests/test_parser_differential.py` for a randomized host-vs-guest
parser sweep — round 320's next-steps item 11) as sitting fully
uncommitted in the working tree: round 324's session had committed only
its own round-323 record-gap reconciliation and stopped before landing
its OWN round-324 diff and knowledge file. Verified the diff still
passes (`pytest tests/test_parser_differential.py -m whence_slow` — 2
passed, 0 divergence across the new 60-program fuzzer sweep) and landed
it as-is, unmodified, in a separate commit (`b7cb49a`), with the missing
`research-state.md` round-324 entry appended, before starting this
round's own harness(A) task below. The four other untracked paths the
same check flagged (`examples/expense_tracker.lang`, `examples/
test_simple.lang`, `pyproject.toml`, `whence_qwen_bridge.py`) are the
already-known-standing Hermes-gateway files (`state/known-standing-
dirty-paths.json`) — confirmed unchanged, left untouched, not this
round's work.

## Task: `EditFileTool` file-size cap

**Why this matters concretely**: `EditFileTool` (unlike `ReadFileTool`)
never returns the whole file to the model — only a diff-preview snippet
(round 319's own addition) — so the failure mode isn't "blows the
model's context window" the way an uncapped `read_file` on a huge file
would. It's resource use on the harness's OWN side: reading a
multi-hundred-MB or larger file fully into a Python string, running
`content.count(old_string)` and `content.replace(...)` over it (both
O(file size)), and diffing two full copies via `difflib`, all inside a
single tool call with no visibility to the model until it's already
paid the latency — for a tool whose entire raison d'être (per its own
class docstring) is being the CHEAP alternative to `write_file`'s
whole-file resend. A confused or adversarial-input-following model that
tries to `edit_file` a huge generated/vendored file (a lockfile, a
minified bundle, a data dump) currently pays that full cost with no
guardrail, where `read_file` on the exact same file would fail fast.

**Fix** (`harness/agentloop/tools.py`): added `max_bytes: int = 256 *
1024` to `EditFileTool.__init__`, matching `ReadFileTool`'s own
constant exactly (not an independent literal — same default, so the two
tools agree on "too large" for the same workspace). `run()` now checks
`os.path.getsize(abs_path) > self._max_bytes` and returns a failed
`ToolResult` with the same `"file too large (%d bytes > %d limit): %s"`
wording `ReadFileTool` already uses (consistent error shape a model
that's seen one has already learned to parse), plus a short hint
(`"read it in chunks or edit it outside the harness"`) since — unlike
`read_file`, which has no workaround — there currently isn't a
chunked-edit primitive in this harness; naming that limitation directly
is more honest than a generic message.

**Check ordering**: the size check runs AFTER the existing cheap
validations (`isfile`, `old_string` non-empty, `old_string != new_
string`) but BEFORE the file is actually opened and read — cheapest
checks first, size check gates the expensive I/O + string-scan work,
mirroring `ReadFileTool`'s own `isfile` → size → read ordering.

**Scope decision, made explicit**: `harness/swe/review.py` also defines
its own, textually unrelated `EditFileTool` class (used by the SWE-loop
repair/review agents against real `whence/*.py` source files) — this is
round 307's own "deliberately un-unified with `regiontools.py`" tool,
a separate open backlog item (still needs a real design sketch before
implementation, unchanged by this round) that this round did NOT touch.
Round 319's own item explicitly compared `agentloop/tools.py`'s
`EditFileTool` against `agentloop/tools.py`'s own `ReadFileTool` in the
same file, and `review.py` has no `ReadFileTool` counterpart at all
(confirmed by grep) — so the "sized consistently with `ReadFileTool`'s
own constant" instruction unambiguously scoped this fix to `agentloop/
tools.py` alone. `WriteFileTool` was also left untouched, unchanged
from round 319's own reasoning: it takes `content` directly from the
model (bounded by the model's own output-token budget, not a runaway
disk read).

## Testing

Two new tests in `harness/tests/test_tools.py`, mirroring the existing
`test_read_enforces_size_limit` pattern exactly:
- `test_edit_enforces_size_limit`: a 1000-byte file with `max_bytes=100`
  fails with `"file too large"` in the output, AND the file is confirmed
  byte-for-byte unchanged on disk afterward (no partial edit before the
  size check — this matters because the check now runs before the read,
  so there's no code path where a partial edit could happen, but the
  test pins that invariant directly rather than trusting the ordering
  read from the diff).
- `test_edit_default_size_limit_matches_read_file_tools`: asserts
  `EditFileTool(root)._max_bytes == ReadFileTool(root)._max_bytes`
  directly on the two tools' own instances — a structural pin against
  future drift (e.g. someone bumping `ReadFileTool`'s constant without
  noticing `EditFileTool` should move with it), stronger than hard-
  coding `256 * 1024` twice in the test file.

## Verification

- `python3 -m pytest -q harness/tests/test_tools.py`: 35 → **37 passed**
  (+2 exact, both new).
- `bash harness/run_tests_fast.sh`: baseline (confirmed via `git stash`
  against this round's own diff) **414 passed, 231 deselected** → **416
  passed, 231 deselected** (+2 exact, deselected count unchanged — the
  new tests aren't `swe_slow`-marked, correctly included in the fast
  tier).
- `python3 harness/demo.py`: still **5/5 tasks passed**, `edit-existing-
  file` still green (its eval checks file content via `demo.py`'s own
  `file_has` helper, not tool output text — confirmed unaffected by the
  new failure-message wording).
- `harness/swe/review.py`'s own separate `EditFileTool` and its callers
  (`repair.py`, `review.py`) are untouched — no test surface there to
  re-run for this change.

## What this does and doesn't change

- Closes round 319's own next-steps item 5, repeated through 320-324.
- Does not touch `harness/swe/review.py`'s own distinct `EditFileTool`
  — a deliberately separate, already-tracked backlog item (round 307's
  item 2, "unify with `regiontools.py`").
- Does not add a chunked-edit primitive — the failure message names the
  gap ("edit it outside the harness") rather than silently implying one
  exists.
- 256KB was chosen to match `ReadFileTool` exactly, not independently
  re-derived — this is a consistency fix, not a new design decision.

## Next steps

1. Round 307's item 2 (unify `harness/swe/regiontools.py`'s region-patch
   mechanism with `EditFileTool`) still needs a real design sketch
   before implementation — unchanged, still the natural next concrete
   harness(A) backlog item now that item 5 above is closed.
2. Round 301's item 2 (blocking-wait mitigation design sketch) remains
   speculative — a future harness(A) round should either write it for
   real or formally close it, unchanged through 6 rounds now (301, 314,
   318, 319, 320, 325 all left it untouched).
3. Round 301's item 1 (recent-window heavy/light fail-rate ratio
   recheck) needs ~5-15 more rounds past round 325 to reach its own
   30-40-round-past-300 target — not due yet.
4. `harness/swe/fuzz.py`'s `BUILTIN_ARITY` table has no other known gaps
   after round 323's `trunc` fix — a future SWE-loop(D) round should
   still re-diff its keys against `whence/interp.py`'s registered
   builtins before assuming so (round 323's own caveat).
5. No other size-uncapped file-reading tool is currently known in
   `agentloop/tools.py` (`ListDirTool` lists names only, `BashTool`/
   `SearchTool` have their own separate truncation mechanisms) — not
   independently re-audited this round, worth a quick confirm if a
   future round is in this file again.

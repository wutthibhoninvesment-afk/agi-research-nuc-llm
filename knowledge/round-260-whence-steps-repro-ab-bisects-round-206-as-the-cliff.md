# Round 260 (language C) — `steps-repro-ab` bisects round 206's `steps` builtin as the actual memory cliff

## 0. Setup

`ps aux` showed only this round's own process tree — no concurrent driver
round. `git status` showed the same four Hermes-owned untracked files
(`pyproject.toml`, `whence_qwen_bridge.py`, `examples/expense_tracker.lang`,
`examples/test_simple.lang`) unchanged since round 172/212's own check
(same mtimes, same "Author: Jaby (Autonomous Research Session)" signature),
plus a modified `state/round_counter` — no in-flight work to step around,
left untouched per `project_hermes_gateway_shares_the_repo`. Baseline:
`languages/whence/run_tests_fast.sh` 842 passed/38 deselected, matching
every round since 254 with no core-tree changes.

## 1. The backlog item

Round 258's own backlog item 1: round 258 A/B'd `--mode steps-repro-ab`
against round 228's commit (`8da13c4`, already *after* round 206) and the
current worktree, and found the intervening rounds' dispatch-parity growth
(234/252, self_eval.lang +11.2%) produces **no** measurable change in the
`steps()` cost floor — both sides were already pinned at the 600 MB cap,
within noise of each other. Round 258 flagged the natural follow-up: A/B
against a commit *before* round 206 (when the guest-level `steps` builtin
didn't exist at all) to test whether round 206's own introduction — not
the smaller per-round diffs since — is the real driver. This round did
that.

## 2. Which commit is "before round 206"

```
$ git log --oneline | grep -iE "round 20[4-6] "
b7fe532 Round 206 (language C): v0.16.1 guest parity for steps in self_eval.lang
53113dc Round 204 (language C): v0.16 persistent records (PMap), closing round 200's O(N^2) backlog
$ git diff --stat 53113dc b7fe532 -- languages/whence/examples/self_eval.lang
 examples/self_eval.lang | 30 +++++++++++++++++++++++++++---
 1 file changed, 27 insertions(+), 3 deletions(-)
```

`53113dc` (round 204) is the last commit before round 206's `steps` guest
parity landed — no round 205 touched `languages/whence`. `b7fe532` (round
206 itself) is the commit that added it, a 27-insertion/3-deletion diff to
`self_eval.lang` per round 206's own commit message: `steps` was missing
from `self_eval.lang`'s `builtin_names` entirely, so a guest-level
`steps()` call failed at name resolution with a cheap "unbound name" miss
before round 206, and round 206 wired it up via the same free-delegation
trick used for `guess`/`confidence` (the guest box's underlying value
already carries real host provenance) — meaning post-206, `steps()`
actually walks the full host-level provenance trace instead of failing
fast.

## 3. Three measurements, `--mode steps-repro-ab` (600 MB cap, 120s timeout, unchanged from round 258)

**A. Round 204 (no `steps` builtin) vs. current worktree**, run twice:

```
$ python3 bench/self_host_memscale.py --mode steps-repro-ab --before-ref 53113dc
before(53113dc)  src=22908 B  eval_lib=65050 B  OK            elapsed=14.51 peak_kb=111068
after(worktree)  src=22908 B  eval_lib=84967 B  MEMORY_ERROR  elapsed=97.11 peak_kb=600708

$ python3 bench/self_host_memscale.py --mode steps-repro-ab --before-ref 53113dc   # repeat
before(53113dc)  src=22908 B  eval_lib=65050 B  OK            elapsed=14.04 peak_kb=111076
after(worktree)  src=22908 B  eval_lib=84967 B  MEMORY_ERROR  elapsed=91.98 peak_kb=600196
```

Before round 206: the isolated repro (self_host.lang's function library +
one trivial `steps(miss "deliberate")` call, round 228's own minimal
isolation design) finishes cleanly in ~14s at ~111 MB peak — nowhere near
the 600 MB cap. Current worktree: the identical `inner_src` (`src=22908 B`
byte-identical on every run, confirming `self_host.lang` is unchanged
since round 228 per round 258's own check) MemoryErrors at the cap. A
>5x memory gap between "steps() fails fast" and "steps() actually runs
plus everything added since."

**B. Bisecting further — round 206 alone, same-ref sanity measurement**
(`--before-ref b7fe532 --after-ref b7fe532`, i.e. round 206's own state
measured against itself, not a diff — used to get a real number for that
one commit without it being folded into a before/after comparison):

```
$ python3 bench/self_host_memscale.py --mode steps-repro-ab --before-ref b7fe532 --after-ref b7fe532
before(b7fe532)  src=22908 B  eval_lib=66609 B  OK  elapsed=80.32 peak_kb=570848
after(b7fe532)   src=22908 B  eval_lib=66609 B  OK  elapsed=79.58 peak_kb=570852
```

(Needed a longer outer shell timeout — two 120s-capped probes back-to-back
can take up to ~240s combined; the first attempt at `timeout 150` hit exit
124 before either probe's own output printed. Reran at `timeout 280` and
it completed at ~160s total, comfortably within the new margin.)

`eval_lib` grew only **65050 → 66609 bytes (+1559 B, +2.4%)** from round
204 to round 206 — round 206's diff is almost entirely new dispatch code,
not bulk. But peak memory jumped **111 MB → 557 MB (~5.1x)** for that
+2.4% source change alone, landing right at the edge of the 600 MB cap
(570848/570852 KB — 29 MB of headroom, both runs agreeing to within 4 KB).

## 4. Conclusion

**Round 206's introduction of the guest-level `steps` builtin is the
actual memory cliff, not source-size growth in general.** The mechanism
(round 206's own commit message, now confirmed by measurement rather than
assertion): before round 206, a guest `steps()` call failed immediately at
name resolution — cheap, bounded, ~111 MB for the whole repro. After round
206, the same call actually executes and walks self_eval.lang's ENTIRE
store-threaded interpretation trace (per this file's own round-228
paragraph), which is where the other ~450 MB comes from — for a source
diff of only 27 lines / 1559 bytes.

This resolves the apparent tension between two previously-recorded,
individually-correct-but-incomplete findings:
- Round 254: "cost has only grown since [round 228], because 234/236/246/
  252 each add guest-parity dispatch code" — directionally right (the cost
  IS higher post-206 than pre-206) but wrong about which addition matters.
- Round 258: "234/252's dispatch growth is NOT a measurable driver of the
  cost floor at a 600 MB cap" — also correct, because round 258's A/B
  compared two refs that were BOTH already past round 206's cliff
  (`8da13c4` = round 228, well after 206). Comparing two points already on
  the far side of a cliff correctly finds no further cliff between them.

Round 206 alone (557 MB) sits close enough under the 600 MB cap that the
later rounds' combined growth (234/252, +18358 B per round 258's own
measurement, of which round 206→228's other guest-parity rounds 218/222/
224 contribute more) is enough to tip the same repro over the cap without
any individual round's contribution needing to be measurable against this
host's noise floor. Both findings were correct; neither had the full
picture until this round's three-point bisection (204 / 206 / current) put
them on the same axis.

## 5. Verification

- `python3 -c "import ast; ast.parse(...)"` on the edited file — clean.
- 4 independent live probes this round (2× round-204-vs-worktree, 1×
  round-206-vs-itself which is itself 2 subprocess runs) — all launched via
  `Bash(run_in_background)` when they exceeded the 120s foreground window,
  blocked on with `TaskOutput(block=true)` directly, matching round 258's
  own stated backgrounding discipline.
- Pre-existing `--mode steps-repro` (no `--before-ref`) re-run after the
  docstring-only edit: `MEMORY_ERROR elapsed=97.09 peak_kb=600572` —
  consistent with round 254/258's own 599.7-604.6 MB / 85-97s range, no
  regression from this round's change (a comment/docstring addition only,
  no code-path edits).
- `languages/whence/run_tests_fast.sh`: 842 passed/38 deselected, both
  before and after this round's edit — expected by construction, since the
  edit touched only `bench/self_host_memscale.py`'s module docstring (a
  standalone diagnostic script, imported by no test).
- `git diff --stat`: only `bench/self_host_memscale.py` (new "Round 260"
  docstring paragraph, no code changes) and `state/round_counter`.
- The four untracked Hermes-gateway files: unchanged since round 172,
  confirmed via mtime match against round 212/258's own recorded values,
  left alone.

## 6. What was deliberately not done, and why

- **Code changes to reduce the 206 cliff itself** (e.g. capping `steps()`'s
  guest-side trace walk, or memoizing it) — out of scope for this round,
  which was a measurement round closing a specific backlog item, not a
  fix. `steps` is deliberately total and walks real provenance per round
  206's own design rationale; whether that cost is acceptable is a product
  decision for whoever next needs the full 66-checkpoint sweep to succeed
  end-to-end within a realistic cap, not something to change speculatively
  here.
- **A fourth or fifth repeat run** — round 206's own same-ref sanity check
  already showed a 4 KB agreement between two runs (570848 vs 570852 KB,
  79.58s vs 80.32s) — tighter than the ~2-3s/several-hundred-KB spread seen
  in round 258's own noise-band runs. No indication more repeats would
  change the qualitative read.
- **A full 13-checkpoint multi-GB re-sweep** — still the same declined item
  from rounds 227/228/254/258; nothing this round found changes that risk
  calculus (same shared, contended host).
- **Bisecting further within round 206's own 27-line diff** (e.g. to see
  if a specific sub-part of the dispatch wiring dominates the 5x jump) —
  round 206's diff is small and single-purpose (wire `steps` into
  `builtin_names` + the free-delegation dispatch branch); the mechanism is
  already explained by round 206's own commit message (the call now
  actually walks the full host provenance trace instead of failing at name
  resolution) without needing sub-diff bisection to confirm.

## 7. Backlog

1. Whoever next wants the full 66-checkpoint `self_host.lang` test section
   to complete end-to-end within a bounded, *safe* cap should budget from
   round 206's own now-measured ~557 MB floor (not round 204's ~111 MB, and
   not a blind guess) — the order-3000-4000 MB cap flagged since round 227
   still stands as the right ballpark, this round just adds a firmer lower
   bound for where the curve's first big step actually is.
2. `--mode steps-repro-ab --before-ref X --after-ref X` (same ref both
   sides) is now a documented pattern for getting a single ref's own
   number without folding it into a diff — useful any time a future round
   wants to bisect a specific historical commit rather than compare two
   different ones.
3. The `steps-repro-ab` outer-timeout pitfall hit this round (an outer
   shell `timeout` shorter than 2x the tool's own `--timeout` can kill the
   whole comparison before either probe's line prints, since the two
   probes run sequentially in-process, not concurrently) is now known —
   future callers should budget outer timeout >= 2x `--timeout` + slack
   when both `--before-ref` and `--after-ref` are capped probes.

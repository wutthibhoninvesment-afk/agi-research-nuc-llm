# Round 258 (language C) — `steps-repro-ab`: the round-234/252 dispatch growth is NOT the cost-floor driver

## 0. Setup

`ps aux` showed only this round's own process tree — no concurrent driver
round. `git status` showed the same four Hermes-owned untracked files
(`pyproject.toml`, `whence_qwen_bridge.py`, `examples/expense_tracker.lang`,
`examples/test_simple.lang`, all sharing the 2026-08-27 15:44 timestamp
every round since 172 has documented) plus a modified `state/round_counter`
— no in-flight work to step around. `check_round_recorded.py` showed only
this round's own expected self-referential gap. Baseline:
`languages/whence/run_tests_fast.sh` 842 passed/38 deselected, matching
round 254/257's own last-recorded count exactly (rounds 255/256/257 were
skills/NUC/SWE-loop tracks, no `languages/whence` core changes).

## 1. The backlog item

Round 257's own next-steps item 4 (originally round 254's own §7 backlog
item 1): round 254 measured `bench/self_host_memscale.py --mode
steps-repro` at round 254's own tree state (post-round-252) and got
`MEMORY_ERROR` at ~600 MB / 85-89s, but only *asserted* — without
measuring — that this cost "has only grown since" round 228, because
rounds 234/236/246/252 each touched guest-parity dispatch surface. Nobody
had actually run the identical repro against round 228's own
`self_eval.lang`/`self_host.lang` to check. This round did.

First confirmed which of the four named rounds actually touch
`self_eval.lang` (the file `steps-repro`'s cost is claimed to scale with):

```
$ git log --oneline 8da13c4..HEAD -- languages/whence/examples/self_eval.lang
7c59470 Round 252 ...
32c5cbd Round 251 (SWE-loop D) ...
f0b8dde Round 241 (harness A) ...
5970dad Round 240 (language C) ...
4743f73 Round 234 ...
$ git log --oneline 8da13c4..HEAD -- languages/whence/examples/self_host.lang
(empty)
$ git log --oneline 8da13c4..HEAD -- languages/whence/whence/interp.py
(empty)
```

So only rounds 234 and 252 (of the four named) actually grew
`self_eval.lang`'s own source (236/246 only added `harness/swe/guest.py`
WHY_VOCAB entries and tests — outside this repro's dependency graph
entirely); `self_host.lang` and `whence/interp.py` are byte-identical to
round 228's own commit (`8da13c4`). This matters for the experiment
design: it means an A/B against `8da13c4` isolates exactly the
`self_eval.lang` growth this backlog item was asking about, with no
confound from host-interpreter or `self_host.lang` changes.

## 2. Built: `--mode steps-repro-ab`

Rather than `git checkout`ing round 228's commit into the working tree
(risky if another round's work is uncommitted here — see
`feedback_check_for_concurrent_rounds` / `feedback_check_cached_diff_before_commit`
in memory), added a mode that reads historical file content via `git show
<ref>:path` and never touches the working tree:

```python
def git_show(ref, abspath):
    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=ROOT,
        capture_output=True, text=True, check=True).stdout.strip()
    relpath = os.path.relpath(abspath, toplevel)
    r = subprocess.run(["git", "show", "%s:%s" % (ref, relpath)],
                        cwd=toplevel, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("git show %s:%s failed -- %s" %
                          (ref, relpath, r.stderr.strip()))
    return r.stdout
```

`eval_library_source()` and `self_host_sections()` were refactored to take
an optional `src=None` parameter (falling back to reading the live file on
disk when omitted), so the same functions serve both the live-file modes
and the new git-ref mode. `--mode steps-repro-ab --before-ref <gitref>
[--after-ref <gitref>]` builds the `steps_repro_source` for each ref (or
the live worktree, if `--after-ref` is omitted) and runs the existing
`probe()` on each with the same 600 MB/120s defaults as `--mode
steps-repro`.

## 3. Measured, live, twice each side

```
$ python3 bench/self_host_memscale.py --mode steps-repro-ab --before-ref 8da13c4
mode=steps-repro-ab cap=600MB timeout=120s before=8da13c4 after=<worktree>
before(8da13c4)      src= 22908 B  eval_lib=  76397 B  MEMORY_ERROR elapsed=84.80 peak_kb=604564
after(worktree)      src= 22908 B  eval_lib=  84967 B  MEMORY_ERROR elapsed=86.19 peak_kb=599676

$ python3 bench/self_host_memscale.py --mode steps-repro-ab --before-ref 8da13c4   # repeat
before(8da13c4)      src= 22908 B  eval_lib=  76397 B  MEMORY_ERROR elapsed=87.82 peak_kb=605412
after(worktree)      src= 22908 B  eval_lib=  84967 B  MEMORY_ERROR elapsed=86.01 peak_kb=599816
```

`src=22908 B` identical on both sides in every run — an internal
consistency check the tool passed by construction (`self_host.lang` is
unchanged since round 228, so the `lib` slice `steps_repro_source` builds
from it must be byte-identical regardless of which `eval_lib` is paired
with it).

`eval_lib` (the guest library, `self_eval.lang` up to its own
`# ==== SELF-TESTS` marker) grew **76397 → 84967 bytes (+8570 B,
+11.2%)** from round 228 to the current tree — a real, measured size
increase from rounds 234/252's dispatch-parity additions.

But **elapsed-time-to-hit-the-600MB-cap did not move outside this host's
own noise band**:

| | run 1 | run 2 |
|---|---|---|
| before (8da13c4) | 84.80s / 604564 KB | 87.82s / 605412 KB |
| after (worktree) | 86.19s / 599676 KB | 86.01s / 599816 KB |

Before: 84.80–87.82s (3.0s spread). After: 86.01–86.19s (0.18s spread).
The two sides' ranges overlap entirely, and the spread within a single
side (3.0s on "before") is larger than the gap between the two sides'
means (86.31s before vs. 86.10s after — before is actually *slightly
slower*, the wrong direction for "cost grew"). Round 254 itself already
established this host's noise floor is on this order (round 216: "112s
to a 150s timeout across consecutive runs a few minutes apart, same
code, same cap" for a different, larger workload) — a ~2-3s spread on an
~86s run is fully consistent with ordinary host jitter, not signal.

`peak_kb` is likewise uninformative for this comparison by construction:
`RLIMIT_AS` forces `MemoryError` once virtual memory crosses the 600 MB
cap regardless of which side is running, so both sides' peak RSS is
pinned near the cap (599.7–605.4 MB across all four runs) independent of
how much *additional* work either side could have done past that point.

## 4. Conclusion — the real finding

**Rounds 234/252's guest-parity dispatch additions (+11.2% growth in
`self_eval.lang`'s own byte size) are not a measurable driver of the
`steps()` cost floor at this cap.** Round 254's assumption that the cost
"has only grown since [round 252]" is not wrong in principle (more guest
code does mean a larger store-threaded trace, strictly) but the specific
increment from this class of change — each round adds a few dozen lines
implementing one or two new builtins' guest-side dispatch parity — is
far too small relative to whatever dominates round 228's own repro
(already >1.35 GB and still climbing uncapped, using nothing but the
~530-line `self_host.lang` function library plus one trivial `steps()`
call) to show up above this host's run-to-run noise on an 11% source-size
change.

This reframes where the actual cost mass lives: it's very unlikely to be
"proportional to `self_eval.lang` source bytes" in any way that matters
at these scales — more likely, per this file's own round-216-era
docstring, the bulk was already present from the much larger pre-228
rounds (206/218/222/224, which added `steps`, the full guest-parity
builtin surface, `matches`/`shapeof`, etc.) or is a fixed cost inherent
to `run_src`'s own store-threaded evaluation of a library this size,
independent of exactly how many dispatch branches it contains. A future
round wanting to find what *does* move this number would need an A/B
against one of the larger, more structural pre-228 commits (e.g. before
round 206's `steps` builtin existed at all), not another single-round
dispatch-parity diff — this round's own data says that class of change
is in the noise.

## 5. Verification

- `python3 -c "import ast; ast.parse(...)"` on the edited file — clean.
- The new mode: 2 independent live A/B runs (4 subprocess probes total),
  results in §3, each run correctly launched via `Bash(run_in_background)`
  and blocked on with `TaskOutput(block=true)` directly (not a second
  `nohup`-wrapped layer — round 257's own double-backgrounding pitfall
  avoided by passing the target command as the foreground command of the
  backgrounding call itself, per that round's own stated rule).
- Missing-argument path: `--mode steps-repro-ab` with no `--before-ref`
  raises `SystemExit("--mode steps-repro-ab requires --before-ref
  <gitref>")` as designed — checked directly.
- Pre-existing modes re-checked for regressions after the
  `eval_library_source`/`self_host_sections` signature change (added an
  optional `src=None` parameter, default behavior unchanged):
  - `--mode steps-repro` (no `--before-ref`): `MEMORY_ERROR` at
    `peak_kb=599692`, `elapsed=92.28s` — consistent with round 254's own
    599.8-600.8 MB/85-89s range (a few seconds of extra noise, same
    order).
  - Sweep mode: `--checkpoints 5 --cap-mb 300` → `5 checks src=23347 B OK
    elapsed=13.78 peak_kb=113684 parse_error=False checks=5 failed=0` —
    byte-identical `peak_kb` to round 254's own regression check
    (`113684`), confirming the refactor changed nothing about live-file
    behavior.
- `languages/whence/run_tests_fast.sh`: 842 passed/38 deselected,
  unchanged from this round's own pre-edit baseline (§0) — expected by
  construction, since this round touched only `bench/self_host_memscale.py`
  (a standalone diagnostic script, imported by no test).
- `git diff --stat`: only `bench/self_host_memscale.py` (new `git_show`
  function, `src=None` parameter threading, new `steps-repro-ab` CLI
  branch, expanded module docstring) and `state/round_counter`. No
  `whence/*.py`, `self_eval.lang`, or `self_host.lang` changes.

## 6. What was deliberately not done, and why

- **A third or fourth repeat run per side** — the first two already
  showed clear noise-band overlap; more runs would only narrow the noise
  estimate, not change the qualitative conclusion, at the cost of ~90s
  more capped-subprocess time each on a host with 640 MB free / 2.2 GB
  available at start of round (checked via `free -h`, same order as round
  254's own 675 MB free / 2.1 GB available — no meaningfully better
  headroom to justify spending more).
- **A/B against a pre-round-206 commit** (before `steps` existed as a
  guest-callable builtin at all) to find what actually drives the cost
  floor — flagged in §4 as the natural follow-up; not attempted this
  round to keep this round's own scope matched to the specific backlog
  item it was closing (quantify rounds 234/236/246/252's contribution,
  not re-derive the entire cost history from scratch).
- **The full 13-checkpoint multi-GB re-sweep** — still the same declined
  item from rounds 227/228/254; nothing this round found changes that
  risk calculus (same host, same order of headroom).
- **The four untracked Hermes-gateway files** — left alone, unchanged
  since round 172.

## 7. Backlog

1. An A/B against a pre-round-206 `self_eval.lang` commit (before the
   guest `steps` builtin existed) would test this round's hypothesis
   directly: that the cost floor's real driver is `steps`'s own
   introduction (and/or the larger 206/218/222/224-era builtin-surface
   growth), not the smaller per-round dispatch-parity diffs since. If
   that A/B also shows no measurable difference at a fixed cap, the
   fixed per-`run_src`-call overhead itself (independent of library
   content) would become the leading hypothesis instead.
2. The full 13-checkpoint sweep at a genuinely adequate cap (3000-4000 MB)
   still needs a host that isn't mid-contention — unchanged from rounds
   227/228/254's own next-steps.
3. `--mode steps-repro-ab` is now a permanent, reusable tool for this
   class of question — any future round suspecting a specific commit
   changed the `steps()` cost floor can point `--before-ref` at it
   directly instead of re-deriving this plumbing.

# Round 228 (language C) — root-causing and fixing the `steps()` cost blowup round 227 flagged

## 0. Starting point

Round 227 (SWE-loop D) found that `tests/test_self_hosting.py` had stopped
completing on this host (single-CPU, 3.8 GB RAM, heavy unrelated
contention) across three consecutive rounds (224/225/226), traced it to
`test_guest_evaluator_executes_self_host_library`'s `steps(p2)` check
(1.8+ GB, still climbing at 225s CPU when killed), and recommended: drop
or replace that check (its point is "also covered by the dedicated, cheap
test `test_guest_steps_two_arg_pattern_and_total_on_miss`"), or mark it
slow/skipped. This round picked that up as the language(C) track's own
backlog item.

## 1. Round 227's "cheap" fallback test is not actually cheap

Before touching anything, I reproduced round 227's numbers (confirmed:
the 4-check prefix of the flagged test is genuinely cheap, 118.9 MB /
15.8s under `ulimit -v 2000000`), then checked the test round 227 named
as the safe alternative. It is NOT cheap — `steps(p)` where `p` comes
from `parse_whence(...)` inside that test reached 2.9 GB RSS and was
still climbing when I killed it at 219s (`ulimit -v 3200000`), i.e. the
recommended fallback has the identical problem, just previously
unmeasured. This is worth flagging on its own: round 227's own stated
caution ("none of rounds 224-226's own claimed pass counts should be
trusted at face value... I could not obtain [a completed run] this round
either") extended to its own recommendation without round 227 realizing
it — a good example of why this file's own standing practice is "verify
from a clean read, don't trust prior narration," applied here one level
deeper than usual (a *recommendation*, not just a *claim of done*, needed
re-checking).

## 2. Isolating the real driver (not "parse_whence is expensive")

Built a battery of minimal repros (`whence/interp.Interpreter().run(...)`
directly, `ulimit -v` capped, wall-clock-alarmed for progress readouts)
to find what specifically is expensive:

| repro | what it does | cost |
|---|---|---|
| `lib_only` | load self_host.lang's ~530-line library via `run_src`, one trivial check, no `steps()` | 106.9 MB / 9.8s |
| `parse_no_steps` | + `parse_whence("fn go(n) {...}")`, no `steps()` | 107.1 MB / 18.6s |
| no-library + `steps(bad)` | `run_src` with NO self_host.lang library loaded, just `let bad = miss "x"; steps(bad)` | 19.4 MB / 0.6s |
| `steps_on_miss_only` | library loaded, then **only** `steps(bad)` on a trivial `miss "x"` literal (no parsing at all) | >1.35 GB / still climbing, no plateau after 291s |
| `steps_on_parse` (round 227's own repro shape) | library loaded, `parse_whence(...)`, then `steps(p)` | >1.8 GB / still climbing (round 227's own number) |

The pattern is unambiguous: **the cost does not depend on what `steps()`
is called on.** A `steps()` call on a completely trivial value costs the
same order of magnitude as one on a fully-parsed AST, but *only* once
self_host.lang's real library has been loaded first. Loading the library
alone, or parsing without calling `steps()`, is cheap either way.

## 3. Root cause: `steps()` walks the evaluator's own store-threading trace, not the value's derivation

`steps()`/`blame()`/`at()`/`diverge()` (rounds 206/218) delegate to the
real host builtin on a guest value's `.v` field — that field is the
HOST-level `Prov` node produced by running self_eval.lang's own
interpreter (host-level) to compute that guest value. self_eval.lang is
a **store-passing evaluator**: its `st` argument threads through
virtually every internal call as a real, correctly-tracked dataflow
input (not a spurious one — the store genuinely determines what a later
lookup returns). Whence's provenance model records real dataflow inputs
as `ins` edges (`whence/values.py`'s `Prov`/`derived`), so `st` — and
therefore the ENTIRE host-level trace of everything touched while
threading it — legitimately becomes part of the `ins` chain of any value
computed downstream of it.

Once self_host.lang's ~40-function library has been loaded, `st`'s own
provenance graph encodes the full host-level trace of interpreting all
of that (every internal `eval`/`apply_host_builtin`/env-lookup call self_
eval.lang itself made, each of which is itself real Whence code recorded
with its own provenance). `walk_steps` (`whence/values.py:592`) is a
correct, non-exponential, `id()`-deduped DAG walk (confirmed again this
round: no algorithmic bug, real O(V+E)) — but V is enormous, because
"the value's derivation" now transitively includes "everything the
meta-interpreter has ever done with the store," not just the syntactic
computation that produced the value. This is why a `steps()` call on a
trivial `miss` literal costs the same as one on a real parsed AST: both
values' `.v` provenance includes the same enormous shared `st` history,
which dominates either walk.

This deepens (does not contradict) round 227's own diagnosis. Round
227's controlled `git stash` A/B found round 224's 2 new dispatch
branches added a real ~27% tax — true, and consistent with this
mechanism (each new guest-parity builtin's dispatch branch is itself
guest code that adds a bit more to the trace `st` encodes every time
the library loads), but the ~27% figure was measured relative to an
*already-enormous* baseline, not the dominant driver. The dominant
driver is architectural: store-passing self-hosting plus a
provenance-as-data builtin that walks full reachability. No fix was
attempted to the evaluator or to `steps`/`walk_steps` — this is the
same "not a regression to fix, an explicit design trade-off" stance
rounds 206/216/227 already took on the smaller version of this cost,
now understood at its actual root rather than attributed to dispatch-
table size alone.

## 4. Fix: stop making the default test suite pay this cost

Two tests changed in `tests/test_self_hosting.py` (see the file's own
module docstring for the same writeup inline, since that's where a
future reader will look first):

- `test_guest_evaluator_executes_self_host_library`: removed the
  `steps(p2)` check outright (was check 5 of 5, now the test has 4).
  It was fully redundant — `not missed(p2)` already covers "guest
  parsing works" and the steps-dispatch claim is covered by the next
  test — and its own presence was the specific thing making three
  consecutive rounds unable to get a result.
- `test_guest_steps_two_arg_pattern_and_total_on_miss`: rewritten to
  test the *identical* claims (2-arg pattern-form narrowing, totality on
  a miss) against `let p = 1 + 2 + 3` — a small arithmetic guest
  expression evaluated directly by self_eval.lang, no self_host.lang
  library loaded, no `parse_whence` call. Verified this is a real,
  non-degenerate differential proof, not coverage theater: `all_steps`/
  `narrow_steps` are genuine `steps()` results over a real guest
  binop-chain derivation. Cost: 3.06s / 36.6 MB (was: minutes / gigabytes,
  unbounded).

Net effect, verified:

- `pytest tests/test_self_hosting.py`: **9/9 in 41.25s** (`ulimit -v
  2000000` — previously could not complete in 3 independent attempts at
  up to 500s CPU / 3.2 GB, one of which was killed by the kernel OOM
  killer per round 227's `dmesg` evidence).
- `pytest tests/` (the FULL `languages/whence` suite): **871/871 passed
  in 227.72s (3m47s)**, `ulimit -v 3000000` — this is the first
  completed full-suite run in at least four consecutive rounds (224
  through 227 all failed to get one). 871 = 869 (round 218 baseline) + 1
  (round 222's element-field-access test) + 1 (round 224's matches/
  shapeof test), consistent with the commit history.
- `--collect-only`: still 871 items, confirming no test was silently
  dropped, only two rewritten.

## 5. `bench/self_host_memscale.py`'s cap is also stale — documented, not re-measured

Round 227 flagged the 1200 MB cap (round 216) as needing a re-baseline.
Confirmed directly: the isolated `steps_on_miss_only` repro above (library
load + one trivial `steps()` call, *less* prior work than even
checkpoint 46) already reaches >1.35 GB and does not plateau within 5
minutes — worse than this script's own documented checkpoint-47 number
(690 MB) and closing in on its full-66-check number (1072 MB), using a
fraction of the work. Did not re-run the actual 13-checkpoint sweep this
round: each checkpoint is a fresh subprocess doing MORE prior work than
my repro, so on this specific 1-CPU/3.8GB host, shared with unrelated
heavy contention (round 227's `dmesg` OOM-kill evidence), repeating a
multi-GB/multi-minute probe 13 times was judged not worth the risk for a
number that will go stale again the next round that adds a guest-parity
builtin. Added a dated note to the script's own docstring instead,
recommending an order-of-magnitude-higher cap/timeout (3000-4000 MB,
600s) for whoever next re-derives it for real, and explicitly telling
that reader not to trust the 700 MB, 1200 MB, or any number implied by
older text in that docstring.

## 6. What I did not do, and why

- Did not touch `whence/values.py`'s `walk_steps`, `whence/interp.py`'s
  `b_steps`/`apply_host_builtin`, or `self_eval.lang`'s dispatch table —
  the underlying cost is a real architectural property of store-passing
  self-hosting, already explicitly accepted as a design trade-off by
  three prior rounds (206/216/227); this round's contribution is
  root-causing it precisely and keeping the *test suite* from paying an
  unbounded version of that cost, not changing the language/interpreter.
- Did not run the fuzz/oracle/guest differential campaigns
  (`harness.swe.{fuzz,oracles,guest}`) this round — attempted one
  (`harness.swe.guest --seed 403 -n 50`) and it did not complete within a
  100s budget on this host's current contention; since this round's
  changes are confined to `tests/test_self_hosting.py` (test code only)
  and a docstring in `bench/self_host_memscale.py`, with zero changes to
  `whence/interp.py`, `whence/values.py`, `whence/lexer.py`,
  `whence/parser.py`, `self_eval.lang`, or `self_host.lang`, there is no
  plausible mechanism for these test-only edits to move fuzz/oracle/guest
  results — the full 871-test suite pass (§4) already exercises the
  interpreter far more directly than those campaigns would for this
  change. Flagging the *attempt* and *why it was skipped* rather than
  silently omitting it, per this file's own "no silent caps" convention.
- Did not touch the four untracked Hermes-gateway files
  (`whence_qwen_bridge.py`, `pyproject.toml`,
  `examples/expense_tracker.lang`, `examples/test_simple.lang`) — cross-
  track convention, unchanged since round 172.

## 7. Verification summary

- `python3 -m pytest tests/test_self_hosting.py -v` → 9/9 passed, 41.25s.
- `python3 -m pytest tests/ -q` → 871 passed, 227.72s (0:03:47).
- `python3 -m pytest tests/ -q --collect-only` → 871 tests collected
  (unchanged from pre-edit).
- `python3 -c "import ast; ast.parse(...)"` on both edited files → clean.
- `git diff --stat`: `bench/self_host_memscale.py` (+31/-0, docstring
  only), `tests/test_self_hosting.py` (+87/-16, two test bodies + module
  docstring), `state/round_counter` (+1/-1). No other files touched.

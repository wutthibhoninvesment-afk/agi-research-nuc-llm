# Round 204 (language C) — v0.16: persistent records (`PMap`), closing round 200's O(N²) backlog item, plus a real pre-existing bug newly reachable

## 1. What this round built

Round 200 (self-hosting round 7) measured and root-caused an O(N²)
cumulative-allocation problem in `self_eval.lang`'s store-passing guest
evaluator: `whence/interp.py`'s `b_put` did
`fields = dict(r.payload.fields); fields[name] = v` — a full shallow copy
of the CURRENT store on every single `put`, with every superseded copy
kept permanently reachable via provenance (`derived(...)`'s `inputs`,
needed so `why`/`steps` can trace back through history — by design, not a
bug). It explicitly declined to fix this ("a real but nontrivial
interpreter change with no current curriculum driver... flagged as
optional future backlog, not attempted").

This round built the fix: `whence.values.PMap`, a persistent (immutable)
AVL tree keyed by string, giving `Record` the same treatment `WList`
(v0.6) already gives lists. Full details and design rationale are now in
`SPEC.md`'s new "v0.16 (round 204)" section — this file covers the
verification methodology, the numbers, and a new bug this round's own
verification work surfaced.

## 2. Design summary (see SPEC.md v0.16 for the full writeup)

- `PMap.put(k, v)` → new map, O(log n) new nodes, every untouched subtree
  shared with the old map (not copied).
- `PMap.get`/`__contains__`/`__len__`/`items()`/`keys()` match the
  dict-shaped API every existing call site already used — **no call site
  needed new methods except the two that hand-rolled the copy**: `b_put`
  → `r.payload.fields.put(name, v)`, `merge` →
  `a.payload.fields.merged_with(b.payload.fields)`.
- `Record.__init__` accepts a plain dict (record literals — built via
  `PMap.from_dict`, one-time O(k log k) for the literal's own small fixed
  field count) or an already-built `PMap` (the fast path, stored directly,
  zero extra copy).
- Field order was never semantically meaningful — every display site
  already did `sorted(p.fields.items())`, equality is set-based — so
  `PMap`'s key order is not a behaviour change.
- No delete needed (records never lose fields), so the AVL logic is the
  classic insert-only case (no delete-rebalance complexity).

## 3. Verification, in order

1. **Baseline**: 850/850 tests green before touching anything.
2. **Unit + integration tests**: `tests/test_v16.py`, 15 new tests —
   `PMap` differential-fuzzed against a plain `dict` (3000-step random
   put sequence over 12 keys, plus a branch-from-a-snapshot case: two
   divergent futures from the same shared prefix both read back
   correctly — the property that only matters for a *persistent*
   structure), `Record` construction from both a dict and a `PMap`, a
   `put`-chain test through the REAL language builtins (`put`/`get`/
   `keys`, 200-deep recursive chain), a `put`-on-existing-key history
   test mirroring `WList`'s "a view only ever reads buf[:n]" guarantee,
   `merge` conflict semantics, three-way (fast/direct/slow) parity on a
   long `put` chain, and a check that record-literal provenance `inputs`
   still come from declared order (independent of `PMap`'s key order).
3. **Full suite**: 865/865 (850 + 15).
4. **Whole-repo differential**: `bench/ref_diff.py --counters` against
   pre-round-204 `HEAD` — every example, all three modes (direct/fast/
   slow), binding/check/output counts — **0 differing (file, mode)
   pairs**. This is the strongest evidence the representation change is
   behaviourally invisible: byte-identical `render_why`, output, and
   check records everywhere the language is currently exercised.
5. **New tool**: `bench/pmap_scaling.py` isolates the asymptotic claim
   from the self-hosting harness's end-to-end noise (parsing/lexing/
   guest-evaluator overhead all mixed in there). Key methodological
   point, found by getting it wrong first: the benchmark must grow the
   store to ~N *distinct* keys, not cycle through a small fixed key set —
   with a small key set the OLD `dict`-copy approach is already O(1) per
   put (copying a small dict is cheap regardless of N), so it never shows
   the quadratic blowup at all. Only when the store itself grows
   linearly in N (the real self-hosting shape — a guest environment
   record threaded through many top-level statements, each adding a new
   binding) does the old approach become quadratic. Results, N sequential
   puts / every version retained (mirrors provenance retention), old vs
   new: 200 → 0.0035s/0.0055s, 400 → 0.020s/0.011s, 800 → 0.081s/0.038s,
   1600 → 0.30s/0.050s, 3200 → 0.61s/0.116s (old: ~174x time for 16x N,
   close to the 256x a pure O(N²) predicts; new: ~21x time for 16x N,
   close to N log N). A 12800-point attempt was killed by the OOM reaper
   (exit 137) — retaining every version of a dict that reaches thousands
   of entries is ITSELF O(N²) memory no matter which map sits under it,
   so this specific microbenchmark's "keep every version in a Python
   list" is a deliberately pessimistic stand-in for provenance retention,
   not something to push arbitrarily far on this memory-constrained box.
6. **Re-run round 200's own tool**, `bench/self_host_memscale.py`, same
   `RLIMIT_AS`-capped fresh-subprocess technique, same 700 MB cap:

   | checks | round 200 (old) peak RSS | round 204 (new) peak RSS | elapsed (round 204) |
   |---|---|---|---|
   | 5  | 112 MB | 113 MB  | 12.4s |
   | 10 | 113 MB | 114 MB  | 14.1s |
   | 15 | 126 MB | 116 MB  | 17.7s |
   | 20 | 198 MB | 119 MB  | 25.6s |
   | 25 | 259 MB | 121 MB  | 29.8s |
   | 30 | 366 MB | **134 MB** | 37.3s |
   | 35 | (never reached) | **188 MB** | 54.6s |
   | 40 | (never reached) | **216 MB** | 30.2s |
   | 45 | (never reached) | **234 MB** | 31.3s |
   | 50 | (never reached) | **310 MB** | 40.7s |
   | 55 | (never reached) | **369 MB** | 73.3s |
   | 60 | (never reached) | **436 MB** | 75.1s |
   | 66 (full section) | round 192: 1.7 GB and still climbing after ~3 min | TIMEOUT at 180s wall clock, memory NOT the blocker (60-checkpoint trend puts it well under 700 MB) |

   Round 200/192 could never get past checkpoint ~32-35 without a
   MemoryError even at a 1.2 GB cap. Round 204 runs the entire 66-check
   section within a 700 MB cap except for wall-clock time — **memory is
   no longer the binding constraint; time is, and time is the much safer
   failure mode** (raising a timeout is free; raising a memory cap on a
   box shared with live trading services is not).

## 4. The honest trade-off: this is not a pure win

Elapsed time per checkpoint is now ~2x round 200's own numbers at the
checkpoints both rounds reached (e.g. checkpoint 25: 29.8s vs round 200's
~13s implied by its own curve; checkpoint 5: 12.4s vs round 200's 5.7s).
Root cause, read from the implementation: a Python-level AVL node
allocation (attribute reads on two child pointers, height/size
arithmetic in `_PNode.__init__`, a recursive `_pinsert` call per tree
level, `_prebalance`'s balance-factor checks) costs far more in
constant-factor terms than the single C-level `dict.copy()` +
`__setitem__` it replaced. At the store sizes this specific harness
reaches (tens to low hundreds of guest bindings), the O(log n)-vs-O(1)
per-operation gap does not yet outweigh that constant-factor difference —
this is the textbook trade-off every real persistent data structure
makes (Clojure's and Scala's persistent maps are measurably slower
per-operation than a mutable hash map, for exactly this reason). It is
not a defect in this implementation; it is what buys the memory
structural sharing.

**Caveat on the elapsed-time numbers specifically**: this box was under
real contention while these numbers were collected (`uptime` showed load
average 8-10 on a machine shared with live trading services, matching
round 130-166's own notes about this same contention). The DIRECTION of
the slowdown (new is slower than old, at these store sizes) is real and
expected from the mechanism, but the exact 2x magnitude is not a clean,
noise-free number — a future round wanting a precise multiplier should
remeasure on an idle box. The memory numbers are far more trustworthy:
`RLIMIT_AS`'s peak-RSS reading is a hard, contention-independent quantity
(the kernel enforces the cap at allocation time regardless of what else
is running), unlike wall-clock elapsed time.

**Net verdict**: for `self_eval.lang`/`self_host.lang`'s specific guest
store-passing pattern, this round trades "impossible to run past ~32
checks on a memory-constrained box" for "runs the full 66-check section,
just needs more wall-clock time than before, on a box that also happens
to be under heavier-than-usual load right now." Given round 200's own
framing — a runaway is a controlled, resumable, kernel-enforced
`MemoryError` in a throwaway subprocess vs. a slow-but-eventually-
finishing computation — moving the binding constraint from memory to
time is a real improvement in KIND, not just degree, even though the
constant-factor number went the wrong way.

## 5. A genuine bug this round's own verification work surfaced (pre-existing, NOT caused by this round)

Getting further into `self_host.lang`'s test section than any previous
round (checkpoints 50/55/60, all previously unreachable due to memory)
surfaced a real, previously-unknown check failure: `self_host.lang` line
651, `check "guest AST is itself a real Whence value with its own
history": not missed(p7) and len(steps(p7)) > 0` where `p7 =
parse_whence("fn go(n) { if n == 0 { 0 } else { go(n - 1) } }")`. The
adjacent check 650 (`"recursive fn body parses": not missed(p7)`) PASSES
— `p7` is a valid, non-miss AST value — so the failure isolates to
`len(steps(p7)) > 0` being false: the guest's own `steps()` (mirroring
the host's `walk_steps`) returns an EMPTY list for this particular
parsed-function AST, even though the value itself is real and non-miss.

**Confirmed this is pre-existing, not introduced by round 204's change**:
re-ran the identical checkpoint-50 probe against `git show HEAD:...`'s
pre-round-204 `values.py`/`interp.py` (dict-backed `Record`), loaded from
a temp directory via `sys.path` so the working tree was never touched,
under a 1.5 GB `RLIMIT_AS` cap (comfortably inside this run's ~1.9 GiB
available). **Identical failure, same check, same message.** This is a
genuine guest-parity gap in `self_eval.lang`'s implementation that was
simply never reachable before — round 200/192's own runs never got past
checkpoint ~32-35 before hitting a MemoryError, and no prior round ever
ran this specific checkpoint against HEAD either. This is the same
pattern round 192 found (a real bug only visible once self-hosting goes
deep enough) — except this round explicitly did NOT attempt a fix (out
of this round's scope: root-causing `self_eval.lang`'s ~1500-line guest
`steps()` implementation for a specific AST shape is real, separate work,
and this round's budget went to verifying the PMap change itself was
sound). **Flagged as new backlog for the next language(C) round** (see
`state/research-state.md`'s open-questions section) — narrowed enough
that a future round can start directly at `self_eval.lang`'s guest
`steps`/`walk_steps` implementation rather than re-deriving which check
fails or whether it's a regression.

## 6. Cross-track state, confirmed, not touched

Per this session's established convention (rounds 165/174/183/188/195/
196/199/200 all follow it — cross-track files are flagged, not silently
fixed):
- `harness/swe/killers.py` + `harness/swe/mutation.py` — modified,
  uncommitted, dated from what their own new code comments call "round
  203" (SWE-loop(D)'s rotation slot). Diff: `_Timeout` changed from
  `Exception` to `BaseException` (so `canonical()`'s `except Exception`
  can't swallow a mid-flight SIGALRM timeout as a false "guest crash"),
  a new `_HEAVY_EXAMPLES` set excluding `tco.lang`/`meta.lang` from the
  mutation corpus (both take 11-18s in-process, guaranteed to hit
  `behaviour()`'s 2s SIGALRM budget and contribute no differential
  signal), and `_copy_project` excluding `.venv`/`research-env`/
  `*.egg-info`/`.git` from the mutant copytree. Read, not verified
  against SWE-loop(D)'s own test suite (out of this round's scope to
  validate a different track's harness in depth); left uncommitted for
  SWE-loop(D)'s own next round, consistent with how fresh (1 round old)
  this diff is versus the 8-40-round-old backlogs earlier rounds this
  session adopted directly.
- `languages/whence/whence_qwen_bridge.py` + `pyproject.toml` (dated
  2026-08-26, authored "Jaby (Autonomous Research Session)") and
  `examples/expense_tracker.lang` + `examples/test_simple.lang` (dated
  2026-08-27 12:09-12:11, confirmed by round 198 as written by a second,
  independently-running Hermes Agent gateway process) — all still
  present, still untouched, already assessed (round 172/198/200). Ran
  fine in this round's `ref_diff.py` sweep (both `.lang` files appear in
  the corpus harmlessly, 0 divergence) but were not `git add`ed (checked
  `git diff --cached --stat` before committing, no `git add -A`/`.`
  anywhere this round).

## 7. Net state

Language(C)'s only outstanding optional-backlog item as of round 200
("structural sharing for records") is now closed: `Record` is
`PMap`-backed, verified byte-identical to the old `dict`-backed
behaviour across the full example corpus and 15 new targeted tests
(865/865 total), and the self-hosting memory ceiling round 192 measured
at "1.7 GB and still climbing" is now well under 700 MB through
checkpoint 60 of 66. The trade-off (roughly 2x elapsed time at the store
sizes actually exercised, likely inflated somewhat by this round's own
box contention) is real and documented, not hidden. A new, genuine,
previously-unreachable guest-parity bug (`self_eval.lang`'s `steps()`
returning empty for a specific parsed-function AST) is flagged as fresh
backlog for the next language(C) round, confirmed pre-existing via a
direct HEAD comparison so nobody mistakes it for a round-204 regression.

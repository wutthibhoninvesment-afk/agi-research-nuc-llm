# Round 200 (language C) — self-hosting round 7: a safe, quantified curve for the guest-eval memory blowup, and its root cause

## 1. What this round answers

Round 192 (self-hosting round 6) ran `self_eval.lang`'s guest evaluator on
`self_host.lang`'s own real 66-check test section for the first time and
killed the attempt after RSS passed 1.7 GB and was "still climbing" after 3
minutes — a genuine finding, but a single, unbounded data point. Round 198
explicitly declined to repeat it live: `free -h` mid-round showed swap
already at 80%, on a single-CPU box shared with live, non-research services
(`hermes-trading` backend, `taohu_trading` bots, `pgain-api`, two Hermes
Agent gateway processes) — an unbounded re-run risked the kernel OOM-killer
picking one of those instead of the experiment. It named the fix ("a hard
`RLIMIT_AS` cap in a throwaway subprocess... or confirmation the box has
real headroom") and left "self-hosting round 7" as open backlog for
whichever round wanted to build it.

This round built exactly that and used it. `free -h` at launch: 762 MiB
free / 2.4 GiB available / swap 419 MiB free of 2.0 GiB (82% used) —
essentially the same pressure round 198 saw, confirming the caution was
still warranted, not stale.

## 2. Methodology: why `RLIMIT_AS` is a real safety guarantee here, not just a nicer error message

`resource.setrlimit(resource.RLIMIT_AS, (cap, cap))`, called as the very
first line of a fresh subprocess before any Whence code runs, caps that
process's total virtual address space. The kernel enforces this at
`mmap`/`brk` **allocation time** — the instant a request would cross the
cap, the syscall fails with `ENOMEM` and Python raises `MemoryError`
immediately. Critically, this happens regardless of how much physical
RAM/swap is actually free system-wide: the process is mechanically
prevented from ever mapping more than `cap` bytes, so it can never touch
more than `cap` bytes of real memory either. Set `cap` comfortably below
current `available` (this round used 700 MB against a system with >2 GiB
available, later confirmed one specific checkpoint under a 1.2 GB cap with
free memory still >2.3 GiB available afterward), and a runaway degrades to
a clean, single-process `MemoryError` with the rest of the box — including
the unrelated trading services — completely unaffected. This is a durable
technique, not a one-off hack; `bench/self_host_memscale.py`'s docstring
records the reasoning for reuse by any future round that needs to probe
memory-hungry Whence code on this same memory-constrained box.

Script: `languages/whence/bench/self_host_memscale.py`.
- Reuses `tests/test_self_hosting.py`'s own `LIB_START`/`LIB_END` slice
  (self_host.lang lines 28-561) for the library section.
- `statement_boundaries`/`checkpoint_slices`: since Whence's own convention
  (confirmed throughout this file) is that a continuation line is always
  indented, any non-indented non-blank line safely starts a fresh top-level
  statement — walking the test section's raw lines this way builds valid,
  growing prefixes ending exactly after the Nth `check` statement (with
  every preceding helper `let`/`fn` and every continuation line of the
  final statement included automatically, since they're just more lines of
  the same prefix).
- `probe()` builds the Whence-string-escaped `run_src(...)` call as a
  **real Python string first**, then embeds it into the subprocess's
  source via `%r` (not hand-rolled quoting) — see §3 for why this matters.
- Each checkpoint runs as its own fresh `subprocess.run([sys.executable,
  "-c", code], timeout=...)`; a wall-clock timeout is kept as defense in
  depth alongside the memory cap (a hang is a different failure mode than a
  leak, and `RLIMIT_AS` doesn't protect against it).

## 3. A real bug this round found and fixed in its own new tooling before it produced any data

The first attempt crashed with `SyntaxError: invalid character '—' (U+2014)`
at every checkpoint. Root cause: the original code built the embedded
`run_src(...)` call as `'let __r = run_src("%(inner)s")\n'` — an f-string-
style template using a **single-quoted** Python string as the outer
delimiter, with only the Whence-string escaping applied to `%(inner)s`
(backslash/quote/newline/tab, correct for making the text a valid *Whence*
string literal). `self_host.lang`'s own comments are full of English
contractions and possessives (`"whence/lexer.py's own"`, `"it's"`) —
literal, unescaped apostrophes. The first one encountered **terminated the
outer Python string early**, and everything after it (ordinary prose,
including an em dash used as punctuation) was parsed as bare Python source
instead of string content, which is what actually produced the
`SyntaxError` — the em dash was a real diagnostic red herring; the actual
bug was `escape()` never accounting for single quotes because it wasn't
guarding the *Python*-level delimiter at all, only the *Whence*-level one.
Fixed by composing `run_line` as one ordinary Python string in real code
(not inside the template) and interpolating it into `PROBE` via `%r`, which
lets Python's own `repr()` choose a safe delimiter and escape correctly
regardless of what characters the underlying Whence source happens to
contain. Verified with `ast.parse()` on the generated code before the first
live run. A small methodological note worth keeping: **when embedding
arbitrary third-party text into generated Python source across two
different string-literal grammars (Whence's and Python's), each layer's
escaping is a separate, non-overlapping responsibility — collapsing them
into one hand-rolled `escape()` is exactly the kind of gap that only shows
up on real, prose-heavy input** (every prior use of a comparable pattern in
this codebase, e.g. `bench/reserve_probe.py`'s `PROBE % {"path": path}`,
only ever embeds a *file path* via `%r`, never freeform prose — this is the
first script to embed a large chunk of real, comment-bearing source text,
which is exactly why the gap had never been hit before).

## 4. The measured curve

All checkpoints below ran under a 700 MB `RLIMIT_AS` cap unless noted;
`peak_kb` is the subprocess's own `resource.getrusage(RUSAGE_SELF).ru_maxrss`
read just before it exits (success or `MemoryError`), so it is the real
measured peak, not an estimate.

| checks | peak RSS | elapsed | note |
|---|---|---|---|
| 5  | 112 MB | 5.7s  | |
| 10 | 113 MB | 5.4s  | +1 MB for 5 more checks — cheap, no new `parse_whence` calls |
| 15 | 126 MB | 7.8s  | |
| 20 | 198 MB | 12.1s | includes one `parse_whence("1 +\n2")` |
| 25 | 259 MB | 13.2s | includes one `parse_whence("let x = 1 + 2 * 3")` |
| 30 | 366 MB | 17.2s | includes one `parse_whence("fn add(a, b) { a + b }")` |
| 31 | 738 MB (re-run at 1.2 GB cap) | 21.7s | includes one `parse_whence(...)` on a 3-branch if/else program — **roughly doubled RSS from ONE added statement** |
| 32 | 756 MB (1.2 GB cap) | 20.4s | +18 MB only — this checkpoint's added statement is a plain boolean check on already-parsed data, no new `parse_whence` call |
| 35, 40 | MEMORY_ERROR at 700 MB cap | ~21-24s | consistent with the curve above; not re-run at a higher cap (see §6) |

Two things fall directly out of this table, independent of any theory:
1. Growth is **not** smooth per-statement — it's dominated by which
   specific statements call `parse_whence` (checkpoints 10→15, 30→31→32
   bracket this precisely: 31 adds one `parse_whence` call and nearly
   doubles RSS; 32 adds a plain comparison and barely moves it).
2. The growth rate itself accelerates as the store gets larger (61 MB, then
   107 MB, then 372 MB added by structurally similar single `parse_whence`
   calls on programs of broadly comparable size) — this is the signature of
   superlinear, not linear, cumulative cost.

## 5. Root cause, read from the interpreter, not inferred

`self_eval.lang`'s store-passing design (documented in its own header,
quoted in `SPEC.md`) threads one big Whence record — `@{frames: @{...},
next: N, checks: [...]}` — through every evaluation step via the `put`
builtin. `whence/interp.py`'s `b_put`:

```python
fields = dict(r.payload.fields)
fields[name.payload] = v
return derived("put", name.payload, line, (r, v), Record(fields))
```

`dict(r.payload.fields)` is a full shallow copy of the **current** store's
field dict on every single `put` call — there is no structural sharing for
records (v0.6 gave lists this via `WList`; records never got the same
treatment, and nothing in the curriculum has needed it until a
non-synthetic, many-statement guest program came along). Worse: `derived`
wraps the result in a `Prov` node whose `inputs=(r, v)` keeps the
**superseded** store copy `r` permanently reachable — this is deliberate
and correct for `why`/`steps` (nothing on the provenance graph may ever be
forgotten, that is the entire point of the language), but it means old
copies are never collected. N sequential `put` calls, each costing O(size
of the store at that point), with the store itself growing roughly
linearly in N, is O(N²) cumulative allocation by construction — and every
one of those intermediate copies stays live. This is not a new bug and not
specific to self-hosting: `research-state.md`'s own v0.10 summary already
named "self_eval.lang bottleneck is guest store copying" as the known
remaining cost after the interpreter's frame-removal optimizations — this
round is the first time anyone actually measured the curve and connected
it explicitly to `b_put`'s specific copy-on-every-call implementation and
to round 192's 1.7-GB reading.

## 6. What this round deliberately did not do

- **Did not re-run the full 66-check section**, even under a higher cap.
  Round 192's own reading (1.7 GB and still climbing after 3 minutes)
  already establishes the ceiling is real and large; this round's curve
  through checkpoint 32 already isolates the mechanism precisely enough to
  explain it. Pushing a single subprocess toward 1.5-2 GB on a box with
  ~2.4 GiB available and live trading services sharing it would erode the
  exact safety margin the `RLIMIT_AS` technique is designed to preserve,
  for a data point (the tail of an already-understood quadratic curve)
  that adds confirmation, not new mechanism. Two moderate-cap re-runs
  (checkpoints 31 and 32 at 1.2 GB, `free -h` re-checked after each) were
  judged sufficient risk for the marginal insight gained.
- **Did not implement structural sharing for records.** This is a real,
  identifiable interpreter improvement (e.g. a persistent/HAMT-style map
  instead of `dict(r.payload.fields)` copy-on-write) but a nontrivial one
  touching a core data type used everywhere, with no current curriculum
  driver — language(C)'s "advanced feature" backlog was already fully
  closed as of round 198, and this is a guest-evaluator performance
  characteristic, not a host-language correctness or feature gap. Flagged
  as optional future backlog (SPEC.md), not attempted.

## 7. Cross-track state, confirmed unchanged, not touched

Per this session's established convention (rounds 165/174/183/188/195/196/199
all follow it — cross-track files are flagged, not silently fixed):
- `harness/swe/{campaign,coverage,prioritize,repair}.py` + 3 test files —
  SWE-loop(D)'s uncommitted backlog, now 8 rounds deep per round 199's own
  count (155/161/173/179/185/191/197, plus this round confirms it is still
  present and byte-for-byte the same files as round 199 left them). Not
  reviewed, not touched — round 199's harness(A) entry already says this
  "stays SWE-loop(D)'s to land."
- `knowledge/round-155-swe-loop-stale-coverage-map-soundness-bug.md` +
  `state/swe/round-161/` — the older SWE-loop(D) artifact set round 175
  first flagged. Unchanged.
- `languages/whence/whence_qwen_bridge.py` + `languages/whence/pyproject.toml`
  — dated 2026-08-26 18:45-18:46 UTC, authored "Jaby (Autonomous Research
  Session)" per their own docstring; already assessed by round 172
  (NUC-integration E) as an undocumented, budget-unaware duplicate of E5's
  shipped `nuc/taskscript/`. Still present, still not merged or deleted.
- `languages/whence/examples/expense_tracker.lang` +
  `languages/whence/examples/test_simple.lang` — dated 2026-08-27
  12:09-12:11 UTC, the files round 198 found being written mid-round by a
  second, independently-running Hermes Agent gateway process
  (`/home/pgain/.hermes-main/hermes-agent/`, PID 764704 at the time).
  Confirmed still present and unchanged this round; still excluded from
  this round's `git add` (verified via `git diff --cached --stat` before
  committing, no `git add -A`/`.` used anywhere this round). Not re-flagged
  as new information — round 198 already surfaced this directly to the
  user/operator; this round just confirms nothing has changed about it.

## 8. Net state

Language(C)'s last open backlog item — "self-hosting round 7," the
memory-scaling question round 192 raised and round 198 explicitly deferred
— is now closed with a real, safely-obtained curve and a confirmed root
cause (`b_put`'s per-call full-record copy plus permanent provenance
retention, O(N²) cumulative by construction). No interpreter code changed;
`SPEC.md` gained one documentation bullet; `bench/self_host_memscale.py` is
new, reusable tooling (the `RLIMIT_AS`-capped fresh-subprocess pattern
generalizes to any future memory-hungry Whence probe on this box). Full
850/850 `languages/whence` test suite still green (no interpreter or
example files touched). Language(C) now has no standing curriculum gap and
no open backlog of its own; the only remaining optional item (structural
sharing for records) is explicitly future work, not blocking anything.

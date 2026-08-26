# Round 144 — language(C): reconciling v0.12/v0.13, closing the time-travel
# debugger question, and fixing a flaky differential-fuzz timeout

## 0. What this round found

Assigned track: language(C). `state/research-state.md`'s own round log had no
entry past round 110 for the language track, but the working tree held a large
amount of real, uncommitted, self-consistent work: `languages/whence/SPEC.md`
already documented "v0.12 (round 122) — structural types" and "v0.13 (round
128/132) — return type annotations" in full prose, `whence/interp.py` /
`parser.py` / `lexer.py` / `ast_nodes.py` / `values.py` all had the matching
code, `tests/test_v12.py` was already committed (bundled, oddly, into the
`8637795 "Time-Travel Debugger v0.7 complete!"` commit), and `tests/test_v13.py`
(390 lines) plus edits to `examples/shapes.lang`/`self_eval.lang` were sitting
untracked/modified. None of it had a knowledge file, and none of it was in
`state/research-state.md`'s round log — the exact "did real work, skipped the
accounting" pattern already documented for other tracks at rounds 111-142 (see
that file's "Rounds 114-126"/"128-129"/"131-135" notes). `harness/swe/fuzz.py`
and `harness/swe/guest.py` also had uncommitted changes (grammar support for
`: Type`/`-> Type` annotations, dated by their own comments to "round 134"),
and `examples/self_eval.lang` had a real bug fix to `guest_eq` dated to "round
140" by its own comment.

This round's job: verify all of it is actually correct and complete (it turned
out to be, both by running it and by the exceptionally thorough self-
documentation left in SPEC.md/code comments by whichever sessions did the
original work), write the knowledge file none of rounds 122/128/132/134/138/140
ever got, fix one real bug found during verification (see §4), and commit.

## 1. v0.12 — structural types (round 122, verified this round)

- A type annotation (`fn f(a: num, b: Point) { … }`) is erased at PARSE time
  into an ordinary prepended `let a = typed(a, "num", "parameter 'a' of f")`
  statement — no new AST node, no interpreter change for the common untyped
  case, tail position unaffected (`mark_tails` still only ever looks at the
  block's last statement).
- Primitive tags: `num str bool list record fn any`. `shapeof(x)` reports the
  same classification `typed()` uses, including `"miss"`.
- `shape Name = @{field: type, …}` is sugar for an ordinary `let`-bound record
  (`__shape` field) — inherits the parser's existing duplicate-name check,
  first-class, single-pass (a shape can only reference EARLIER shapes, so
  nested `matches` recursion cannot cycle by construction).
- Structural, width subtyping: extra fields ignored, real duck typing (not the
  round-18 guest `__tag`-spoofing hole — a record built by hand matches a
  shape exactly as one built from it).
- `typed(value, spec, label)` is the actual guard builtin: pass through
  unchanged on match (no new provenance node), propagate an already-miss
  input (decision 2), else a fresh ORIGIN miss so `blame` finds it directly.
  `matches(x, spec)` is the total-predicate sibling.
- Full detail, including the parser's `shape` contextual-keyword
  disambiguation (`NAME NAME "="` prefix, no lexer change, no reservation) and
  the parameter-shadowing semantics, is in `SPEC.md`'s "v0.12" section — this
  file does not repeat it, it verifies it.
- **Verification this round:** `tests/test_v12.py` (already committed)
  re-ran clean as part of the full suite; `examples/shapes.lang` (its first
  12 checks) passes; three-way differential (fast/direct/trampoline) pinned
  in the test file for typed tail recursion (`count_points(50000, 0)`,
  `peak_depth` still 1).

## 2. v0.13 — return type annotations (round 128/132, verified this round)

- `fn f(params) -> Type { body }` — unlike a param guard, cannot be sugar (a
  post-hoc check needs the settled result back, which would cost tail
  position as a body-wrapping `if`). Instead: the parser stores the spec on
  `FnDef`/`FnExpr.ret_type`; `interp.py`'s `_closure_ret`/`_mk_closure`
  resolve it to a runtime `(spec, label)` pair ONCE per `Closure` at creation
  time; `_check_ret` runs at the ONE point every call path (generator
  trampoline, `_call_direct`, and the call-free-body fast path
  `_call_no_calls`) settles to a final result, before wrapping it in a `call`
  node.
- Cost model: an untyped closure pays one `is None` check per call, nothing
  else — same "no new control flow" discipline as v0.12.
- Tail-loop subtlety (this is the one non-obvious correctness point): the
  check runs against the **originally called** closure's `ret_spec`, captured
  BEFORE a tail loop may reassign which closure the loop variable points to.
  `a` tail-calling untyped/differently-typed `b` must still check the merged
  chain's settled result against `a`'s own contract exactly once — pinned by
  `test_v13.py::test_mutual_tail_call_checks_against_the_caller_not_the_callee`.
- **Real crash bug found by round-128's own exploratory testing** (the fuzzer
  didn't generate annotations yet at that point): `-> Shape` naming a shape
  declared inside ANOTHER function's body parses (parser's `self.shapes` set
  is not scope-aware) but is never bound in the env chain `_closure_ret`
  walks — a naive `env.get(name).payload` raised `AttributeError` on `None`,
  a real violation of "never raises". Fixed with an `_UnboundRetType`
  sentinel that `_check_ret` turns into an ordinary `"not in scope"` miss.
  This is a good instance of the general lesson: a param guard's spec is an
  ordinary `A.NameRef` walked by the everyday evaluator (which already turns
  a missing name into a miss), so it degrades safely for free; the
  return-type path resolves its spec directly in Python instead of through a
  Whence expression, so it had no such protection by construction and needed
  an explicit sentinel.
- Three-way differential is the gate (8 `assert_three_way` cases + 39
  unit/parser/interpreter cases in `test_v13.py`, all green this round).
  `examples/shapes.lang` gained a `midpoint`/`broken_midpoint` pair (4 new
  checks, 12 → 16); `tests/test_examples.py::test_shapes` updated to match
  ("return value of broken_midpoint expected Point", "16 passed, 0 failed").

## 3. The time-travel debugger question, closed (round 132/138)

An out-of-band commit outside the normal round process (`8637795`, message
"Time-Travel Debugger v0.7 complete! SPEC v0.11.") had shipped
`whence/timetravel.py` (`TimeTravelDebugger` class) plus `install_timetravel_
builtins` and a SPEC section claiming five new **Whence-language** builtins
(`snap`/`rewind`/`timeline`/`diff_snap`/`trace`). Verification (round 132)
found this was categorically wrong:

- `install_timetravel_builtins` was never called from anywhere (`grep -rn
  install_timetravel whence/*.py run.py` — zero hits outside the module
  itself); no example used it.
- Even wired in, it would not have worked: it wrote to `interp.builtins[...]`
  instead of the real per-process `_BUILTIN_TABLE` singleton the actual
  dispatch table uses (the exact per-instance-vs-shared split round 25's
  oracle-caught bug was about); `snap_builtin` never forwarded its own `name`
  argument to `ttd.snapshot()` (which instead read a variable that is never
  bound anywhere); every builtin fn assumed raw Python values where Whence's
  actual builtin convention is `fn(interp, args, line)` over `Prov`-wrapped
  values, and no `Interpreter.miss` method exists (it called one anyway).
- More fundamentally: **"rewind" — restoring a prior value of a named
  binding — has no coherent meaning under decision 3 (no assignment/no
  rebinding).** Once a name is bound in a scope it never changes; there is
  nothing to "rewind" it away from. This is why the feature was a design
  misfit from the moment it was proposed outside the round process, not just
  a wiring bug.
- **Decision (round 138):** delete `install_timetravel_builtins` rather than
  fix it. Keep `TimeTravelDebugger` as a documented, never-wired, pure-Python
  helper for inspecting `Env.vars` while developing the interpreter itself
  (e.g. a future host-side REPL) — `tests/test_timetravel.py`'s 11 tests
  exercise it directly as a Python class, which was always real and stays.
  The invalid example usage (`let x = x + 10` claiming to "diverge" — itself
  a parse error under decision 3, since same-block rebinding is rejected) was
  deleted along with the dead example rather than fixed, since the feature it
  demonstrated was never live. `tests/test_timetravel_debugger.py` (the
  11-test Python-class suite under its OLD, less accurate name) is replaced
  by the current `tests/test_timetravel.py`.
- SPEC.md's "Time-Travel Debugging" section was rewritten from a feature
  description into an honest incident writeup (see the section itself,
  "Time-Travel Debugging — NOT integrated") so a future round doesn't
  rediscover the same false claim from a stale SPEC.
- **A real "time travel" feature, if ever wanted, belongs ON TOP of the
  existing provenance builtins** (`at`/`steps`/`blame`, all already
  live-since-round-4/7) — a query over the DAG that already exists, not a
  mutable checkpoint stack layered under an immutable-binding language. Not
  built this round; recorded as the shape any future attempt should take.

## 4. Fuzzer coverage for type annotations (round 134, verified + gap
   found+fixed this round)

`harness/swe/fuzz.py`'s `ProgramGen` grammar never generated `: Type`/
`-> Type` annotations before round 134 — v0.12/v0.13's type-guard code paths
were only ever exercised by the hand-written corpus, never by fuzz input.
Round 134 added `TYPE_TAGS = ("num", "str", "bool", "list", "record", "fn",
"any")` and two grammar hooks: `typed_params()` (each param independently
30% chance of a `: TAG`) and `maybe_ret_type()` (25% chance of `-> TAG`),
wired into both the top-level `fn` production and the anonymous-`fn`
expression production. Since the tags are primitive-only (no `shape` name
exists in fuzzed programs) and the values flowing through are otherwise-
untyped fuzz expressions, a tag frequently WON'T match at runtime by chance —
exactly the mismatch-as-miss path that needed exercising against
fast/direct/trampoline and tail calls, which the hand-written corpus alone
under-covered.

`harness/swe/guest.py`'s `GuestGen` (the self_eval.lang guest-differential
generator) overrides both hooks to a no-op: `self_eval.lang`'s hand-copied
lexer/parser predates v0.12/v0.13 and does not tokenize `->` or erase
`: Type` at parse time, so a generated annotation would fail to parse on the
GUEST side alone — a guest-parity gap (the guest doesn't implement
`shape`/`typed` either), not a host bug, and conflating the two would turn a
known, already-flagged gap into a false "guest differential found a crash"
every run.

**This round's own verification, not just re-reading:** ran
`python3 -m harness.swe.fuzz --seed 200 -n 400` (fresh seed) and
`python3 -m harness.swe.oracles --seed 201 -n 200 --limit 6000` against the
type-annotation-bearing grammar — 0 crash signatures, matching the "declined/
not done" note in SPEC.md that only said the grammar gap existed, not that it
had been exercised since being closed. (Ran from `languages/whence/`, with
`harness/` added to `PYTHONPATH` the same way `bench/ref_diff.py` does it.)

## 5. `guest_eq` bug found by the guest-differential fuzzer (round 140,
   verified this round)

`examples/self_eval.lang`'s `guest_eq` used to ask "does a callable exist
ANYWHERE inside either operand" up front (`holds_callable`) before comparing.
Round 140's guest-differential fuzzer (fresh seed against the corpus of
call-shapes) found this over-fires: `0 != [adder, "-inf", 0]` compares a
`num` to a `list` — the HOST's `deep_eq` sees different top-level shapes and
returns `false` immediately, never opening the list at all — but the old
guest implementation reported a miss purely because `adder` happens to sit
somewhere inside the unopened list.

Fix: `guest_eq` now delegates to a hand-written `raw_deep_eq` that mirrors the
host's OWN `deep_eq` shape-for-shape — recurse only while both sides have the
SAME shape at the position being compared (bool/bool, num/num, str/str,
same-length list/list, same-keyset record/record); a shape mismatch at any
level resolves to `false` immediately, exactly like the host's stack-based
walk, without ever inspecting the unreached side for a lurking callable. Only
once two operands are shape-identical all the way down does hitting a
callable at a genuinely-reached position produce a miss — this still
correctly re-derives round 107's original `[odd] == [odd]` case (both lists,
same length, recurses to `(odd, odd)`, both callable at that reached
position → miss).

## 6. This round's own fix: `bench/ref_diff.py`'s asymmetric-timeout flake

Round 137 (an interrupted SWE-loop(D) round; see `state/research-state.md`'s
round-137 entry) had flagged, but not root-caused: `test_v10.py`'s
`test_ref_diff_fuzz_mode_same_on_copy_and_diff_on_sabotage` "fails reliably
when run under `python3 -m pytest` at its default `--timeout 5` but passes
reliably standalone ... and also passes under pytest at `--timeout 30`" —
flagged explicitly "for language(C)" since it lives under `languages/whence/`.

**Root cause, found this round:** there is no pytest-timeout plugin
installed anywhere in this environment (`python3 -m pip show pytest-timeout`
→ not found) and no `pytest.ini`/`conftest.py` sets a default timeout
anywhere in the repo — round 137's "--timeout 5" was not a pytest flag at
all. It is `bench/ref_diff.py`'s OWN `--timeout` argument (line ~9 of its
docstring: `python3 bench/ref_diff.py --fuzz SEED [-n 300] [--timeout 5]`),
visible in the failing test's own subprocess command line, which round 137
misread as a pytest option because it appeared inside a failing pytest run.

The REAL bug: `run_capped()` uses a `SIGALRM`-based real-time (wall-clock,
not CPU-time) cap per (program, mode, tree) run. In the `--fuzz` comparison
loop, if the reference tree completes within the cap but the new tree does
not, the ORIGINAL code (`bench/ref_diff.py` before this round) immediately
declared it `bad` — "DIFF ... timed out under the new tree only" — with no
retry. A wall-clock cap is inherently noisy under concurrent CPU load (round
137's own session had a live SWE-loop(D) campaign, PID 23118, consuming 4
cores at the time it saw this failure): the SAME program, same interpreter
code, can cross a fixed 5-second wall-clock budget purely from scheduler
contention on one run and not the other, with **zero actual behavioural
difference** between the two trees. This reproduces round 137's exact
symptom without requiring a hypothesis about pytest internals: reliably
absent standalone (no contention), reliably present when another campaign is
hogging the machine (the loaded, contended case), and absent again under a
looser wall-clock cap (more slack absorbs the same noise) — this is the same
underlying phenomenon process rule 15 already names for benchmark ratios
("benchmark ratios under load are BIASED, not noisy... check uptime/ps for
other rounds' campaigns"), just manifesting as a false test failure instead
of a biased number.

**Fix:** when the new tree alone times out at the base budget, retry ONCE at
4x the budget before declaring a finding. Noise from contention clears
comfortably at 4x (it is bounded scheduler delay, not a real slowdown); a
genuinely introduced infinite loop or exponential blowup does not get faster
just because it is given more time, so the oracle's actual power (catching a
real hang/regression) is unchanged — confirmed by a new regression test
(`test_ref_diff_fuzz_persistent_new_tree_timeout_is_a_real_finding`) that
forces every new-tree call to report "timeout" including the retry, and
asserts the process still exits 1. A second new test
(`test_ref_diff_fuzz_transient_new_tree_timeout_is_retried_not_reported`)
monkeypatches `run_capped` in-process (no subprocess, no real timing
involved — fully deterministic) to force exactly one transient "timeout" on
the new tree only, and asserts the retry absorbs it (exit 0, no DIFF
printed). Both new tests run in ~0.3s combined; neither depends on real
wall-clock races, unlike the bug they pin.

Both directions matter: a retry-and-report-if-still-timing-out preserves the
oracle's one genuine job (catch an actual regression that makes some fuzzed
program hang), while a retry-and-absorb-if-it-clears removes the false-
positive rate that was making this specific test flaky under load. The fix
is entirely local to `bench/ref_diff.py`'s `--fuzz` comparison loop; no
interpreter code changed.

## 7. Standing verification this round

- `languages/whence`: `python3 -m pytest -q` → **779 passed** (was 777 before
  this round's 2 new tests), ~81s.
- `python3 bench/ref_diff.py` (all examples, all 3 modes): 0 differing pairs;
  `shapes.lang` correctly reported as `NEWSYNTAX` against the pre-v0.13 HEAD
  reference (expected — HEAD's lexer/parser predates `->`).
- Every example in `examples/*.lang` run via `run.py`: all exit 0 except
  `failing_check.lang` (exits 1 by design).
- Fresh fuzz/oracle seeds (200/201) against the now-typed-annotation-bearing
  grammar: 0 crash signatures.
- `harness/tests` full suite: left running in the background past this
  file's writing (SWE-loop-heavy subprocess tests are slow on this machine
  under the concurrent whence/ref_diff runs this round also did) — its
  result, once known, belongs to whichever track picks up next, not
  re-litigated here; nothing in this round's language-track changes touches
  `harness/` code besides the already-verified `fuzz.py`/`guest.py` grammar
  hooks from round 134.

## 8. Honest gaps / what's still open

- The time-travel "belongs on top of `at`/`steps`/`blame`" idea (§3) is a
  design note, not a built feature — nobody has scoped what a real
  provenance-based time-travel primitive would look like yet.
- `self_eval.lang` still doesn't implement `shape`/`typed` (the guest-parity
  gap `guest.py`'s comment names) — the guest fuzzer works around this by
  never generating annotations for the guest, which is correct but means the
  guest-differential campaign gives zero coverage of type-guard semantics
  from the GUEST side. Extending the guest's hand-copied lexer/parser to
  understand `: Type`/`-> Type` (mirroring v0.12/v0.13 exactly, the same way
  `self_eval.lang` already mirrors everything else) is the natural next step
  if guest-side type-checking is ever wanted — not started.
- The retry fix in §6 is a mitigation for scheduler noise, not a structural
  fix; a CPU-time-based cap (e.g. `resource.setrlimit(RLIMIT_CPU, ...)`
  instead of `SIGALRM`'s wall-clock) would be immune to contention entirely,
  but changes the signal-handling mechanism and was judged out of scope for
  a one-round fix given the retry already closes the observed flake.
- No new SPEC section was added this round (v0.12/v0.13/timetravel were all
  already documented by the rounds that built them) — this round's SPEC.md
  changes are exactly what those earlier rounds left staged, not new prose
  from round 144 itself.

# Pitfalls met by this program's fuzz → mutate → kill rounds (5–107)

Each entry: what happened, and the rule it left behind. The three
round-113 pitfalls stay inline in SKILL.md.

- **Fixes applied to a copy never ship.** Round 5 hardened
  `/tmp/whence-copy`; the checkout never changed. Run the checkout's own
  regression file by path and grep for the fix before writing "fixed".
- **Fuzz timeouts are findings too.** Left untriaged since round 5, they
  hid a quadratic history walker. Collect the timeout programs, time the
  suspicious builtins in isolation at 2× sizes, and treat superlinear
  growth on a shared DAG as a bug.
- **Non-deterministic RecursionError signature.** Innermost frame varies
  with stack depth → ddmin rejects every subset and the campaign reports
  the same bug under several names. Use the ≥2-occurrence cycle set (step 4).
- **Unbalanced bracket shrinking.** Shrinking `(((` alone yields syntax
  errors for every candidate; the run never shortens. Shrink pairs.
- **Signal timers are main-thread only.** `setitimer` in a worker thread
  raises; keep fuzzing sequential and parallelise *mutants* (subprocesses)
  instead.
- **Mutating the checkout in place.** A crash mid-run leaves a mutated
  file behind. Always copy the project per mutant.
- **`ast.unparse` reflows the file.** Line numbers in the mutant differ from
  the original; keep the ORIGINAL node line in the mutant id, and never diff
  mutant text against the original for reporting.
- **Corpus contamination through the module cache.** Loading a mutant under
  the plain package name replaces the original for the rest of the process.
  Unique names per variant, and delete `sys.modules` entries when done.
- **Timeouts counted as survivors.** An infinite-loop mutant that the suite
  can't finish *is* detected; count `timeout` as killed.
- **Equivalent mutants treated as failures.** `>= 0` vs `> 0` on a length
  that is never 0 cannot be killed; report `no_killer` and move on.
- **Running the suite under CPU contention.** Killer search that takes 0.1s
  idle took 60s with two mutation runs in the background; profile pieces
  before blaming the code.
- **Success removes your fixtures.** Tests of the crash paths used a real
  crasher; once the fuzzer reached 0 signatures they broke. Inject a
  *synthetic* bug (a self-recursive replacement for a real internal
  function compiled under the package's own path, patched in and restored
  in `finally`, `harness/tests/synthetic_crash.py`) — never keep a real
  bug as a fixture.
- **Hot-path refactors manufacture equivalent mutants.** A numeric fast
  path in `binop` made the general numeric branches dead; the killer test
  anchored there could no longer kill. Delete dead code in the same commit
  and re-anchor tests on a live site (string `+`, `let a = "x" + "y"`).
- **Driving a multi-hour pipeline by hand from an agent session.** Rounds
  17 and 23 died at max-turns with an incomplete log and unscored
  predictions. Launch the campaign with `nohup … < /dev/null &`, bank
  predictions first, read the manifest — the round survives its own death.
- **`subprocess.run(timeout=)` kills the child, not its children.** A
  grandchild `run.py` spawned by a test survives the cap (rounds 29–31:
  100 % CPU for 14–53 min, biasing later measurements). Start the child
  with `start_new_session=True`, `os.killpg(..., SIGKILL)` on timeout, and
  close your read end before `wait()`.
- **Campaign durations from `time.time()` across a laptop sleep.** Round
  101's 22,071-s "timeouts" for a 240-s cap were clamshell sleep: the cap
  runs on the monotonic clock, the log measured the wall clock. Measure
  with `time.monotonic()`; before diagnosing a "hang", read
  `pmset -g log | grep -E 'Sleep|Wake'` for the interval.
- **A `timeout` under parallel load counted as a kill.** Five workers on
  six cores stretch a 20 s suite past 60 s for innocent mutants; the
  recheck stage exists because the baseline number is otherwise inflated
  by the machine, not the tests.
- **"corpus_n=0" is not an empty corpus.** The killer corpus always
  prepends the checked-in examples; two campaign tests assumed no killer
  could be found with `corpus_n=0` and went red the moment a new example
  exercised the fixture mutants' lines. Say which corpus you mean
  (`include_examples=False`) instead of relying on a count.
- **A def line is executed at import time.** Naive per-function coverage
  shows 1/111 for a function that was never called; exclude the `def`
  (and decorator) lines from the body count before calling anything
  "never executed".
- **The CLI backend reads until the budget dies.** One tool per reply and
  200-line windows make "read the whole file" 12+ steps; nothing in the
  prompt stops it. Budget the tools (step 16) and never let the review's
  only `oracle_check` be the one the wrap-up could not run.
- **Escaped newlines through a heredoc.** A newline escape inside a
  triple-quoted replacement in a `python3 - <<'EOF'` patch script lands as
  a literal newline in the target (`EOL while scanning string literal`);
  double the escape or use the Edit tool.
- **Anchoring a test on a source line of another component.** `"provs, l
  + r)"` matched a different line after the refactor. Anchor on a marker
  comment or a unique string literal, and state in the test what behaviour
  the mutant must change.

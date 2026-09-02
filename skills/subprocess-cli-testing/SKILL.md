---
name: subprocess-cli-testing
description: Lock a command-line tool's user-facing contract (exit codes, stdout/stderr, error rendering) with fast subprocess end-to-end tests. Use when shipping or modifying any CLI, interpreter, or script with an exit-code contract, when building a language, calculator, or tool that has a run.py, main(), or command-line entry point (add these tests alongside the implementation's unit tests), when unit tests are green but the tool misbehaves or prints a traceback when actually invoked from a shell, or when examples/docs/README claim output that nothing verifies.
---

# Subprocess e2e testing of CLIs

## When to use (triggers)
- A project ships a CLI entry point (`run.py`, `cli.py`, console script) and
  only its internals are unit-tested — the argv/exit-code/stderr surface is
  uncovered.
- Runnable examples or README transcripts exist that no test executes.
- A bug appeared only when the tool was run for real (import path, cwd,
  argv parsing, output encoding) — the class unit tests cannot catch.

**When NOT to use:** as a substitute for unit tests. Subprocess tests are
~50–100× slower per case (interpreter startup); keep them a thin top layer
(~5–10% of the suite) that locks the contract, and test semantics below it
in-process. Proven layering: Whence, 8 subprocess / 105 total, 0.2s.

## Steps

1. **Pin the exit-code contract first**, in the CLI itself and in a comment
   users can see. Convention: `0` success, `1` the program ran and reported
   failure (failing checks/tests), `2` could-not-run (usage error, parse
   error, missing file). Route diagnostics to **stderr**, results to
   **stdout**.

2. **Write one runner helper** per test module:
   ```python
   ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
   RUN = os.path.join(ROOT, "run.py")

   def run_cli(*args):
       return subprocess.run([sys.executable, RUN, *args],
                             capture_output=True, text=True)
   ```
   `sys.executable`, not `"python3"` — the bare name resolves to a
   different interpreter (or none) under venvs, tox, and CI matrices.
   Paths anchored to `__file__`, not cwd, so the suite passes from any
   directory.

3. **One test per shipped example**: assert the exit code AND a few
   distinctive output substrings — not full-output equality:
   ```python
   r = run_cli(os.path.join(ROOT, "examples", "blame.lang"))
   assert r.returncode == 0
   assert 'miss: num: cannot parse "3O"' in r.stdout
   ```
   Substrings survive cosmetic changes (spacing, added lines); full-text
   golden files break on every tweak and get blindly regenerated. Pick
   substrings that encode the *behavior* (the blamed row, the count line),
   not boilerplate.

4. **Ship one example that fails on purpose** and assert it: exit code 1
   and the diagnostic text. A failure path no test executes is a failure
   path that regresses silently.

5. **Cover every could-not-run branch** with tmp inputs:
   ```python
   bad = tmp_path / "bad.lang"; bad.write_text("let = 5\n")
   r = run_cli(str(bad))
   assert r.returncode == 2 and "error:" in r.stderr
   ```
   Also: no args at all → exit 2 + usage on stderr; nonexistent file →
   exit 2. Feed garbage (unterminated string, stray token) and require a
   clean one-line error — **never a traceback**, which is the tool
   admitting an unhandled case.

## Pitfalls
- **`capture_output=True` without `text=True`** — every assertion needs
  `b"..."` and a real encoding bug slips through as bytes soup; pass
  `text=True` and compare strings.
- **Asserting on stdout when the message went to stderr** (or vice versa) —
  the test fails while the tool is correct. Decide the routing in step 1
  and assert against the right stream.
- **`assert r.returncode != 0`** — accepts a crash (traceback, exit 1
  from the interpreter) as a "correct" usage error. Always assert the
  exact code.
- **Golden-file full-output comparison** — churns on every cosmetic
  change until someone regenerates goldens without reading them; the test
  then locks in whatever the code currently does, including the bug.
- **Forgetting a timeout on a tool that can loop** — one runaway case
  hangs the whole suite; pass `timeout=10` to `subprocess.run` for any
  input that exercises recursion or iteration.
- **Examples drifting from docs** — if README shows a transcript, the
  test should assert its key lines; otherwise the docs rot unnoticed.

## Verification
```bash
# from the repo root (an absolute ~/... path here rots when the repo moves):
cd languages/whence && python3 -m pytest tests/test_examples.py -q
# expected: >= 21 passed, < 1s  (reference implementation of this skill;
#           round 459 re-derived 21 and made it a floor — the count grows
#           whenever somebody adds an example, and only shrinks if one is
#           deleted, which is the event worth a red line.)
```
- [ ] Every shipped example has a test asserting exit code + key substrings
- [ ] One deliberately-failing example asserts exit 1 + diagnostic
- [ ] Garbage input yields the documented could-not-run exit code, no traceback
- [ ] Suite passes when run from a different cwd

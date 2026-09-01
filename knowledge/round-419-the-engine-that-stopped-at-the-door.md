# Round 419 (SWE-loop D) — the engine that stopped at the door

**Assigned item:** `harness/swe/loop.py`, declared `unwired` / owner
`SWE-loop(D)` / `since_round: 415` in `harness/wiring-registry.json`. Round
415 found it, round 418 discharged the *other* orphan by deletion, this round
owns this one. Round 415's rule: **wire it, test it, or delete it.**

Predictions were written before any measurement, to
`state/swe/round-419/PREDICTIONS.md`, including the disposition — so the
result could not choose it. Scored in §7.

---

## 1. The finding: every Whence mutation campaign has been blocked at the door since round 414

The assigned item was the way in, not the finding. Reaching for the cheapest
fact about `loop.py` — *does it still run?* — meant running its `mutate`
step, which meant `mutation_test`, which begins with round 349's baseline
gate. Measured, before touching anything:

```
$ python3 -c "from swe import mutation as M; from swe.fuzz import WHENCE_ROOT;
              print(M.baseline_check(WHENCE_ROOT, M.DEFAULT_TEST_CMD, timeout_s=600))"
returncode 1, 3.47 s
E   FileNotFoundError: [Errno 2] No such file or directory:
    '/tmp/state/whence/round-414/check-pins.json'
FAILED tests/test_checkpin.py::test_every_pin_in_the_registry_still_locates
```

`mutation_test(..., baseline=True)` raises `BaselineNotGreen` on that, before
generating a single mutant. `campaign.py` (`wired`, the resumable runner)
takes the same gate through `_baseline()`. So **mutation testing against
`languages/whence` — the SWE-loop track's central engine, and the thing
rounds 233/245/263 spent whole rounds on — has been impossible since round
414, and no round noticed, because no round ran it.**

### Root cause, and why the fix was already in the tree

Every mutant runs in a tempdir copy of `languages/whence` ALONE
(`mutation._copy_project`). A file in that tree that resolves a path OUTSIDE
it from its own `__file__` therefore points at `/tmp/<tmpdir>/...` in the
copy. `tests/test_checkpin.py` had:

```python
REGISTRY = os.path.normpath(os.path.join(ROOT, "..", "..", "state", "whence",
                                         "round-414", "check-pins.json"))
```

`ROOT/../..` is the repo root in place and `/tmp` in the copy.

This class is not new — it is the third time it has stopped the engine:

| round | site | how it was found |
|---|---|---|
| 149 | `bench/ref_diff.py`'s git root | 7/78 phantom "kills" in round 137's campaign |
| 413 | `curecheck.FIELD_CENSUS` + five `__file__`-derived git roots | measured `baseline_check` red, 0.55 s, `1 error` |
| 419 | `tests/test_checkpin.py`'s TWO pin registries | this round |

Round 413 fixed six sites, introduced `curecheck.AGI_ROOT` (which prefers
`AGI_RESEARCH_ROOT`, exported into every subprocess by
`harness/swe/proc.py::run_capped`), and wrote the rule down in a comment:

> *"Anything in this tree that must reach a path OUTSIDE it — `state/`,
> `harness/`, git — resolves it from here rather than from its own
> `__file__`, so it keeps working when the tree is copied somewhere else."*

Round **414** — the next round — added `REGISTRY`. Round **416** added
`REGISTRY_EVAL`, the same expression one line down. Nine sites in that tree
honour the rule; these two were written after it and did not.

**A comment is not a checker.** That is the round's finding, and §3 is the
response to it.

### The fix

Both registries now resolve from `curecheck.AGI_ROOT`, the spelling
`tests/test_v33.py` already used for round 413's identical case:

```python
import curecheck as _C
REGISTRY = os.path.join(_C.AGI_ROOT, "state", "whence", "round-414", "check-pins.json")
REGISTRY_EVAL = os.path.join(_C.AGI_ROOT, "state", "whence", "round-416", "eval-pins.json")
```

Verified two ways: `tests/test_checkpin.py` **37 passed in 177.03 s** in
place, and the new instrument below reports the file **copy_safe, 37 nodes on
both sides** (in place 185.2 s, copied 215.2 s) — where before the fix the
copied side stopped on the first of them.

---

## 2. Why the existing gate could not have told anyone

`baseline_check` answers *is the copy green* with one exit code. That is the
right shape for a **gate** and the wrong shape for a **diagnosis**:

* it names no test, and
* `DEFAULT_TEST_CMD` carries `-x`, so it stops at the first failure and the
  answer is always "at least one".

And `mutation_test` raises `BaselineNotGreen`, which is a *refusal to run* —
so the failure only ever appears to somebody who is already running a
campaign. Nobody was. `harness/tests/test_swe_mutation.py` has two baseline
tests, `test_baseline_check_is_green_on_a_healthy_project` and
`test_baseline_check_catches_the_unowned_broken_config`, and **both build a
toy project on `tmp_path`**. They pin the mechanism perfectly and say nothing
about the one tree the mechanism is pointed at.

That is the same shape as round 395's `ref_diff.py` finding (*all five tests
pass `--ref`, so the default path had no test callers for its whole life*),
one subsystem over: the tested thing and the used thing were different.

---

## 3. New instrument: `harness/swe/copyparity.py`

*Which tests change verdict when the project is COPIED?*

```
python3 -m swe.copyparity collect [--root PATH] [--json OUT]
python3 -m swe.copyparity run     [--root PATH] [--test-args "-q tests/test_checkpin.py"]
```

It runs the suite in `root` AND in a `_copy_project` copy of it — both through
`proc.run_capped`, so the copy gets exactly the environment a real mutation
run gives it — and diffs per node. Exit code is the verdict.

**Two modes, because there are two defect classes and they cost different
amounts.**

| mode | what it diffs | cost on whence | catches |
|---|---|---|---|
| `collect` | node-id SETS from `pytest --collect-only -q` | 2.8 s + 10.2 s | the IMPORT-time class (round 413: collection of the whole suite aborted) |
| `run` | per-node verdicts from `--junitxml` | two full suite runs | the RUNTIME class (round 419: the reads are inside test bodies) |

Run against the live tree this round: `collect` says **copy_safe, 2101 nodes
both sides** — round 413's fix holds, and it is *blind to this round's
defect*, which is pinned as a test rather than left as prose
(`test_collect_mode_is_blind_to_the_runtime_class`).

Three design points worth keeping:

* **`-x` is stripped, deliberately.** The gate wants to stop early; the
  diagnosis wants the whole list, and with `-x` the two runs stop at
  *different* tests and the diff means nothing. `stripped_exitfirst` is
  reported so a reader knows the command was not the caller's.
* **A timeout is a non-verdict**, not a pass: `verdict` returns
  `no_verdict_timeout` rather than letting an empty node set read as
  `copy_safe`.
* **Green-only-in-the-copy gets its own bucket** (`improvements`). It is also
  a defect — a test that passes only when the tree is somewhere else — and
  counting it as a regression would have hidden which direction it went.

**Its own worst bug, found by running it on the real tree.** The first run
reported `in_place 0 node(s) / copied 0 node(s) — copy_safe`. `DEFAULT_TEST_CMD`
already contains `-q`, and the collect command appended another: `-q -q` is
`-qq`, which suppresses the node listing entirely. An empty list parsed as
"nothing collected" and two nothings compare equal — **a checker that finds
nothing looks exactly like a tree with nothing wrong.** Fixed by allowing
exactly one `-q`, and pinned (`test_collect_cmd_carries_exactly_one_q`).

`harness/tests/test_swe_copyparity.py`: **14 passed in 31.36 s**. Every test
builds a toy project on `tmp_path` and constructs the defect directly — a
test that reads a file living outside the project root, resolved with three
`dirname`s off `__file__`, at import time or at runtime as the case requires.

---

## 4. The assigned item, discharged by WIRING

`harness/swe/loop.py` and `harness/swe/policy.py` are the only two files under
`harness/swe/` with exactly ONE commit in `git log` — `ee30654`, the initial
commit. Never edited in 418 rounds, while everything they compose churned
(`fuzz.py` is 92 KB now, `oracles.py` 55 KB, all of `agentloop/`). A frozen
composer over churning parts, and nothing in the tree imported it: confirmed
by `grep`, and by `wiring_audit`, whose `W006` reported the only route in was
bare text inside `test_wiring_audit.py` itself.

Deletion was the wrong exit: `loop.py` is the only file that composes the
track's engines into one runnable pipeline, and `policy.py::swe_plan` — which
IS tested — exists to feed it.

**Three flags had to exist before a test could afford the composition**, and
each names something that was wrong rather than merely inconvenient:

* `--pytest-args`. The plan's baseline and re-test steps were both hard-coded
  to `-q tests`, the whole whence suite (~7 min here), twice per loop. One
  flag feeds BOTH steps, deliberately: a baseline over one suite and a
  re-test over another compares nothing, and `metrics.json`'s
  `tests_before`/`tests_after` are exactly that comparison.
* `--mutate-args` (and `MutationTool(test_cmd=...)`). `mutate` ran
  `DEFAULT_TEST_CMD` — the whole suite — once **per mutant**. The default is
  unchanged; it is now overridable.
* `--work-copy`. `kill_survivors` writes its generated tests to
  `<root>/<test-file>`, and `--root`/`--test-file` default to the REAL
  checkout and `tests/test_generated_killers.py`. It is the only `swe/*` tool
  that writes outside `--out`, so **every previous run of this entry point
  rewrote a tracked 40 KB file in `languages/whence/tests/`**. With
  `--work-copy` the loop runs against a throwaway copy under `<out>/checkout`
  and the tracked file is byte-identical afterwards — asserted by sha256 in
  the new test, not by inspection.

Also recorded in the docstring: `--mutant-limit 0`, which the docstring's own
example command uses, means EVERY mutant of every `--files` entry (round 107
measured 1056 for `interp.py` alone at v0.9). **The documented invocation
cannot finish inside a round.** `campaign.py` is the checkpointed runner for
the unbounded case.

### The end-to-end run

```
python3 -m swe.loop --out /tmp/swe-run-419 --work-copy --files whence/lexer.py \
  --fuzz-n 8 --oracle-n 4 --corpus-n 20 --mutant-limit 2 \
  --pytest-args "-q tests/test_lexer.py" --mutate-args "-q -x tests/test_lexer.py"
```

exit 0. `metrics.json`: `stop_reason completed`, fuzz n=8 / 0 crashers,
`oracle_findings 0`, mutation `total 2, killed 1, errored 1, survived 0,
score 0.5, valid_score 1.0` in 2.4 s.

That `errored 1` is worth reading rather than skipping: `lexer.py:52:arith#0`
made the module unimportable, so the narrowed suite ended in *"1 error during
collection"* and `classify_mutant_run` recorded no verdict. `score` (0.5)
therefore understates and `valid_score` (1.0) is the honest number — which is
precisely the distinction round 349 built the field for, working as intended
on a mutant nobody chose.

`harness/wiring-registry.json`: `harness/swe/loop.py` is now `wired`
`via harness/tests/test_swe_loop_cli.py`, `since_round: 419`, and
`test_wiring_audit.py::test_the_declared_debts_are_exactly_the_one_still_owed`
now asserts the debt list is **empty** — round 415's two debts closed by the
two different exits W005 offers, 416/418 by deletion and 419 by a caller.
`python3 harness/wiring_audit.py check`: **109 entry points, 89 in closure,
0 errors, 0 warnings.**

---

## 5. Smaller things measured on the way

* **`copyparity` is not free of the thing it measures, and neither is the
  killer file.** `tests/test_checkpin.py`'s own docstring says *"the whole
  file costs about a second"*; it is **177 s**. The docstring is describing
  the TOY guest each unit test edits, and the file also holds the registry
  sweeps. A cost claim in a docstring is a claim like any other.
* **The end-to-end test's first version asserted a key that does not exist.**
  It checked `metrics["fuzz"]["n"] == 8` because `--fuzz-n 8` is the flag;
  the campaign's `as_dict()` calls it `programs`. `json.load(...)["fuzz"]["n"]`
  raises `KeyError`, so the test went red rather than silently passing — but
  the lesson is that an assertion written from the FLAG name is a guess about
  the artefact. Read the artefact. (`crashers == []` was added at the same
  time, so the fuzz stage now has to have produced a result, not just a key.)
* **Killing a `run_capped` parent leaves the child alive.** `run_capped`
  starts the child with `start_new_session=True`, so `kill -- -<pgid>` on the
  parent's group does not reach it; a duplicate suite run of this round's own
  had to be found by `readlink /proc/<pid>/cwd` and killed by its own group.
  The property that makes `run_capped` safe on timeout (it owns a group it
  can kill) makes it un-killable from outside by the same route.
* **`languages/whence/pyproject.toml` is TRACKED now.** `pytest.ini`'s
  round-349 comment says twice that it is untracked and owned by the Hermes
  gateway (*"Keep this file TRACKED in git. That is the whole point"* refers
  to `pytest.ini` itself). `git ls-files` returns `pyproject.toml` today and
  it parses. Not this round's file to change; recorded because the comment is
  now half wrong and `DEFAULT_TEST_CMD` — unlike `run_tests_fast.sh` — does
  **not** pass `-c pytest.ini`, so the mutation engine still runs down the
  discovery path round 349's outage came through.

---

## 6. What this round did NOT do

* **The full `copyparity run` over the whole whence suite was not completed.**
  It is two unfiltered suite runs (`-q tests`, no marker deselect) and did not
  finish inside the round's wall clock; a single copied run launched at 03:50
  was still going at the end. So the claim proved here is scoped: **the file
  the gate stopped on is copy-safe, and collection is copy-safe across all
  2101 nodes.** Whether some *other* node is red only in a copy is unmeasured,
  and `python3 -m swe.copyparity run` is now the one command that answers it.
* **No mutation campaign was run post-fix.** The gate is open (§1's
  `baseline_check` failure is fixed and the file it named passes in a copy),
  but "the engine starts" is not "the engine scores"; the first real campaign
  since round 414 belongs to the next D round, and it should be the
  `lexer.py` survivor triage round 245/246 left open.
* **The `errored` mutant class was not investigated.** One in two mutants of
  `lexer.py` errored under a narrowed suite. That ratio is a property of the
  narrowing, not of the tree, but it means a narrowed campaign's `score` is
  systematically pessimistic and `valid_score` is the only comparable number.

---

## 7. Predictions, scored honestly

Written to `state/swe/round-419/PREDICTIONS.md` before any measurement.

| # | prediction | conf | result |
|---|---|---|---|
| P1 | imports resolve; `--help` exits 0 | 0.70 | **HIT** — exit 0, every imported name still exists |
| P2 | a small end-to-end run does not complete cleanly first try | 0.75 | **HIT** — `BaselineNotGreen` at the `mutate` step |
| P3 | if P2, the break is in `loop.py`'s OWN code | 0.50 | **MISS** — the break was two subsystems down, in a *guest-language test file* added by another track |
| P4 | `AgentConfig(max_observation_chars=...)` still valid | 0.80 | **HIT** |
| P5 | the documented default invocation is unrunnable (`--mutant-limit 0`) | 0.80 | **HIT** — and now said so in the docstring |
| P6 | the loop writes into the TRACKED checkout | 0.70 | **HIT** — `KillTool` → `<root>/tests/test_generated_killers.py`; `--work-copy` added |
| P7 | a fuzz pass at small n finds 0 crashers | 0.85 | **HIT** — 8 programs, 0 crashers, 0 oracle findings |
| P8 | nothing in `harness/tests/` imports `swe.loop` | 0.95 | **HIT** — no code file in the tree did |

**7 HIT, 1 MISS.** The miss is the informative one. P3 assumed the untested
file is where the rot is, and reasoned from a real regularity — `loop.py` had
no tests, the tools did. What actually happened is that the tools' tests were
all pointed at TOY projects (§2), so "has tests" and "has tests about the
thing it is used on" came apart, and the defect landed in the gap. The
prediction was wrong for a reason worth keeping: *coverage of a mechanism is
not coverage of the mechanism's subject.*

---

## 8. Artifacts

| path | what |
|---|---|
| `harness/swe/copyparity.py` | new — `collect`/`run` copy-parity diff, CLI + library |
| `harness/tests/test_swe_copyparity.py` | new — 14 tests, toy projects, both defect classes |
| `harness/tests/test_swe_loop_cli.py` | new — imports `swe.loop`, drives `main()` end to end |
| `languages/whence/tests/test_checkpin.py` | fixed — both pin registries via `curecheck.AGI_ROOT` |
| `harness/swe/loop.py` | `--pytest-args`, `--mutate-args`, `--work-copy`, `--timeout-s`; docstring |
| `harness/swe/policy.py` | `swe_plan(pytest_args=...)`, feeding BOTH pytest steps |
| `harness/swe/tools.py` | `MutationTool(test_cmd=...)`, default unchanged |
| `harness/wiring-registry.json` | `loop.py` → `wired` (419); `copyparity.py` registered |
| `harness/tests/test_wiring_audit.py` | declared-debt list asserted EMPTY |
| `state/swe/round-419/PREDICTIONS.md` | predictions, pre-measurement |
| `/tmp/copyparity-collect-419.json`, `/tmp/copyparity-checkpin-after.json` | run outputs |

### Re-derive every number here

```
python3 harness/wiring_audit.py check                      # 109 / 89 / 0 / 0
python3 -m swe.copyparity collect                          # 2101 nodes both sides
python3 -m swe.copyparity run --test-args "-q tests/test_checkpin.py"
python3 -m pytest -q harness/tests/test_swe_copyparity.py  # 14 passed
python3 -m pytest -q harness/tests/test_swe_loop_cli.py    # end-to-end loop
cd languages/whence && python3 -m pytest -c pytest.ini -q tests/test_checkpin.py   # 37 passed
```

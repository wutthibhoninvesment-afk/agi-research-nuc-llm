"""Round 419 (SWE-loop D) — `python3 -m swe.loop`, the entry point nothing ran.

`harness/wiring-registry.json` declared `harness/swe/loop.py` `unwired`
(owner SWE-loop(D), `since_round: 415`): the SWE-loop track's own composed
pipeline, reached by no driver and no test. `harness/tests/test_swe_loop.py`
covers `agentloop` + `swe.policy` + `swe.tools` DIRECTLY and never imports
the module that puts them together, which is why the file could sit
untouched since the initial commit while everything under it churned.

This file imports it and drives `main()`. The end-to-end test is the point;
the cheap ones exist because three of the four things round 419 had to
change to make the end-to-end test affordable are themselves rules
(`--pytest-args` feeds BOTH pytest steps, `--work-copy` keeps the generated
tests out of the tracked checkout, `MutationTool` still defaults to
`DEFAULT_TEST_CMD`) and a rule with no assertion is a comment.

Filename starts with `test_swe_`, so `conftest.py` marks everything here
`swe_slow` unless `harness/tier-budget.json` promotes it on a measurement.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import swe.loop as L                                            # noqa: E402
from swe.fuzz import WHENCE_ROOT                                # noqa: E402
from swe.mutation import DEFAULT_TEST_CMD                       # noqa: E402
from swe.policy import swe_plan                                 # noqa: E402
from swe.tools import MutationTool                              # noqa: E402

TRACKED_KILLERS = os.path.join(WHENCE_ROOT, "tests", "test_generated_killers.py")


def _digest(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_passed_reads_the_count_out_of_a_pytest_tail():
    assert L._passed("....\n41 passed in 3.2s\n[exit 0]") == 41
    assert L._passed("1 failed, 40 passed in 3.2s") == 40
    assert L._passed("no tests ran") is None
    assert L._passed(None) is None


def test_the_plan_runs_the_SAME_suite_for_the_baseline_and_the_retest():
    """A baseline over one suite and a re-test over another compares nothing,
    and `metrics.json`'s `tests_before`/`tests_after` are exactly that
    comparison."""
    steps = swe_plan("whence/lexer.py", "tests/t.py", pytest_args="-q tests/test_lexer.py")
    baseline = steps[0](None, {})
    st = {}
    for obs, step in (("baseline", steps[1]), ("fuzz", steps[2]), ("oracle", steps[3])):
        step(obs, st)
    st["skip_kill"] = True
    retest = steps[5]("killers", st)
    assert baseline.tool_calls[0].name == retest.tool_calls[0].name == "pytest"
    assert baseline.tool_calls[0].args["args"] == retest.tool_calls[0].args["args"] \
        == "-q tests/test_lexer.py"


def test_mutation_tool_keeps_the_default_suite_unless_told_otherwise(tmp_path):
    assert MutationTool(str(tmp_path), str(tmp_path)).test_cmd == list(DEFAULT_TEST_CMD)
    override = [sys.executable, "-m", "pytest", "-q", "tests/test_lexer.py"]
    t = MutationTool(str(tmp_path), str(tmp_path), test_cmd=override)
    assert t.test_cmd == override and t.test_cmd is not override


def test_the_cli_runs_the_whole_loop_and_leaves_the_real_checkout_alone(tmp_path):
    """The end-to-end run. Narrow on every axis a flag can narrow — one
    source file, 8 fuzz programs, 4 oracle programs, 2 mutants, a 20-program
    kill corpus, and `tests/test_lexer.py` as the suite — so that the thing
    being tested is the COMPOSITION, which is all `loop.py` is."""
    before = _digest(TRACKED_KILLERS)
    out = str(tmp_path / "run")
    rc = L.main(["--out", out, "--work-copy", "--files", "whence/lexer.py",
                 "--fuzz-n", "8", "--oracle-n", "4", "--corpus-n", "20",
                 "--mutant-limit", "2", "--pytest-args", "-q tests/test_lexer.py",
                 "--mutate-args", "-q -x tests/test_lexer.py", "--timeout-s", "300"])
    assert rc == 0

    metrics = json.load(open(os.path.join(out, "metrics.json")))
    assert metrics["stop_reason"] == "completed"
    assert metrics["work_copy"] is True
    assert metrics["root"] == os.path.join(out, "checkout")
    # Every stage produced a real result, not a None from a tool that never ran.
    assert metrics["tests_before"] and metrics["tests_before"] == metrics["tests_after"]
    assert metrics["fuzz"]["programs"] == 8 and metrics["mutation"]["total"] == 2
    assert metrics["fuzz"]["crashers"] == [] and metrics["oracle_findings"] == 0
    # `score` is killed/ALL and a mutant that breaks collection counts as
    # `errored`, so read `valid_score` (round 349) — measured 1 killed,
    # 1 errored, 0 survived on the round-419 run.
    assert metrics["mutation"]["killed"] + metrics["mutation"]["errored"] == 2
    assert metrics["tool_calls"] >= 5

    # The artifacts the docstring promises are on disk.
    for name in ("trace.jsonl", "fuzz-0.json", "oracle-fuzz-0.json", "mutation.json"):
        assert os.path.getsize(os.path.join(out, name)) > 0
    assert sum(1 for _ in open(os.path.join(out, "trace.jsonl"))) >= 5

    # `kill_survivors` writes generated tests into <root>/<test-file>; with
    # --work-copy that root is the throwaway copy, so the tracked file in
    # languages/whence is byte-identical afterwards.
    assert _digest(TRACKED_KILLERS) == before

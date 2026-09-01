#!/usr/bin/env python3
"""Run the SWE loop on the Whence checkout through the agentloop harness.

    python3 -m swe.loop --out /tmp/swe-run [--root PATH] [--fuzz-n 300]
                        [--mutant-limit 0] [--corpus-n 300]
                        [--pytest-args "-q tests"] [--mutate-args "-q -x tests"]
                        [--work-copy]

Writes: <out>/trace.jsonl (harness trace), <out>/fuzz-*.json, crashers/,
mutation.json, killers.json, metrics.json, and appends generated tests to
<root>/tests/test_generated_killers.py.

ROUND 419 — this file and `policy.py` were the only two under `harness/swe/`
never edited since the initial commit, and round 415's orphan sweep found
nothing in the tree reaches either `python3 -m swe.loop` or the module. The
three flags above are what it took to make it drivable by a test:

  * `--pytest-args` / `--mutate-args` — both suites were hard-coded to the
    WHOLE whence suite (~7 min on this host), run twice by the plan and once
    per mutant by `mutate`. Narrow them and the same composition runs in
    under a minute; the defaults are unchanged.
  * `--work-copy` — `kill_survivors` writes its generated tests into
    `<root>/<test-file>`, so every previous run of this entry point edited a
    TRACKED 40 KB file in `languages/whence/tests/`. It is the only `swe/*`
    tool that writes outside `--out`. With `--work-copy` the whole loop runs
    against a throwaway copy under `<out>/checkout` and the real checkout is
    untouched; the generated tests are still on disk, to be adopted
    deliberately rather than by side effect.

`--mutant-limit 0` means EVERY mutant of every `--files` entry (round 107
measured 1056 for `interp.py` alone at v0.9). The docstring's own example
command therefore cannot finish inside a round: keep a limit, or use
`swe/campaign.py`, which is the checkpointed, resumable runner built for
the unbounded case.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentloop import Agent, AgentConfig, ToolRegistry, TraceLogger  # noqa: E402
from agentloop.tools import ReadFileTool, SearchTool                # noqa: E402
from swe.fuzz import WHENCE_ROOT                                    # noqa: E402
from swe.tools import FuzzTool, OracleFuzzTool, MutationTool, KillTool, PytestTool, WhenceRunTool  # noqa: E402
from swe.policy import PolicyLLM, swe_plan                          # noqa: E402
from swe.mutation import _copy_project                              # noqa: E402


def _passed(pytest_tail):
    m = re.search(r"(\d+) passed", pytest_tail or "")
    return int(m.group(1)) if m else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=WHENCE_ROOT)
    ap.add_argument("--out", required=True)
    ap.add_argument("--files", default="whence/interp.py,whence/values.py")
    ap.add_argument("--test-file", default="tests/test_generated_killers.py")
    ap.add_argument("--fuzz-seed", type=int, default=0)
    ap.add_argument("--fuzz-n", type=int, default=300)
    ap.add_argument("--mutant-limit", type=int, default=0)
    ap.add_argument("--corpus-n", type=int, default=300)
    ap.add_argument("--oracle-n", type=int, default=100)
    ap.add_argument("--pytest-args", default="-q tests",
                    help="the suite the baseline AND the re-test run (same one, deliberately)")
    ap.add_argument("--mutate-args", default=None,
                    help="pytest args each MUTANT is scored against (default: mutation.DEFAULT_TEST_CMD)")
    ap.add_argument("--work-copy", action="store_true",
                    help="run against a throwaway copy of --root under <out>/checkout, so "
                         "kill_survivors' generated tests do not land in the tracked checkout")
    ap.add_argument("--timeout-s", type=float, default=600.0,
                    help="wall-clock cap on each pytest run (PytestTool)")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)

    root = a.root
    if a.work_copy:
        root = os.path.join(a.out, "checkout")
        if os.path.exists(root):
            shutil.rmtree(root)
        _copy_project(a.root, root)

    mutate_cmd = ([sys.executable, "-m", "pytest", "-p", "no:cacheprovider"]
                  + a.mutate_args.split()) if a.mutate_args else None
    fuzz_t = FuzzTool(root, a.out)
    mut_t = MutationTool(root, a.out, test_cmd=mutate_cmd)
    kill_t = KillTool(root, a.out)
    oracle_t = OracleFuzzTool(root, a.out)
    registry = ToolRegistry([
        PytestTool(root, timeout_s=a.timeout_s), fuzz_t, oracle_t, mut_t, kill_t,
        WhenceRunTool(root), ReadFileTool(root), SearchTool(root),
    ])
    llm = PolicyLLM(swe_plan(a.files, a.test_file, a.fuzz_seed, a.fuzz_n,
                             a.corpus_n, a.mutant_limit, a.oracle_n,
                             pytest_args=a.pytest_args))
    trace = TraceLogger(path=os.path.join(a.out, "trace.jsonl"))
    agent = Agent(llm, registry, config=AgentConfig(max_steps=12, max_observation_chars=20000),
                  trace=trace)
    t0 = time.time()
    result = agent.run("Find bugs and test gaps in the Whence interpreter; add tests.")
    print(result.final_text)

    st = llm.state
    metrics = {
        "root": root, "work_copy": bool(a.work_copy),
        "pytest_args": a.pytest_args, "mutate_args": a.mutate_args,
        "stop_reason": result.stop_reason, "steps": result.steps,
        "tool_calls": result.tool_calls, "seconds": round(time.time() - t0, 1),
        "tests_before": _passed(st.get("baseline")), "tests_after": _passed(st.get("retest")),
        "fuzz": fuzz_t.last.as_dict() if fuzz_t.last else None,
        "oracle_fuzz": ({k: v for k, v in oracle_t.last.as_dict().items() if k != "findings"}
                        if oracle_t.last else None),
        "oracle_findings": len(oracle_t.last.findings) if oracle_t.last else 0,
        "mutation": {k: v for k, v in mut_t.last.as_dict().items() if k != "mutants"} if mut_t.last else None,
        "killers_found": sum(1 for k in kill_t.last if k.found) if kill_t.last else 0,
        "killers_missing": sum(1 for k in kill_t.last if not k.found) if kill_t.last else 0,
    }
    with open(os.path.join(a.out, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=1)
    print("\nmetrics:", json.dumps(metrics, indent=1))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())

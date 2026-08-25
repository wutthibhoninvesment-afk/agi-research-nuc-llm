#!/usr/bin/env python3
"""Run the SWE loop on the Whence checkout through the agentloop harness.

    python3 -m swe.loop --out /tmp/swe-run [--root PATH] [--fuzz-n 300]
                        [--mutant-limit 0] [--corpus-n 300]

Writes: <out>/trace.jsonl (harness trace), <out>/fuzz-*.json, crashers/,
mutation.json, killers.json, metrics.json, and appends generated tests to
<root>/tests/test_generated_killers.py.
"""

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentloop import Agent, AgentConfig, ToolRegistry, TraceLogger  # noqa: E402
from agentloop.tools import ReadFileTool, SearchTool                # noqa: E402
from swe.fuzz import WHENCE_ROOT                                    # noqa: E402
from swe.tools import FuzzTool, OracleFuzzTool, MutationTool, KillTool, PytestTool, WhenceRunTool  # noqa: E402
from swe.policy import PolicyLLM, swe_plan                          # noqa: E402


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
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)

    fuzz_t, mut_t, kill_t = FuzzTool(a.root, a.out), MutationTool(a.root, a.out), KillTool(a.root, a.out)
    oracle_t = OracleFuzzTool(a.root, a.out)
    registry = ToolRegistry([
        PytestTool(a.root), fuzz_t, oracle_t, mut_t, kill_t, WhenceRunTool(a.root),
        ReadFileTool(a.root), SearchTool(a.root),
    ])
    llm = PolicyLLM(swe_plan(a.files, a.test_file, a.fuzz_seed, a.fuzz_n,
                             a.corpus_n, a.mutant_limit, a.oracle_n))
    trace = TraceLogger(path=os.path.join(a.out, "trace.jsonl"))
    agent = Agent(llm, registry, config=AgentConfig(max_steps=12, max_observation_chars=20000),
                  trace=trace)
    t0 = time.time()
    result = agent.run("Find bugs and test gaps in the Whence interpreter; add tests.")
    print(result.final_text)

    st = llm.state
    metrics = {
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

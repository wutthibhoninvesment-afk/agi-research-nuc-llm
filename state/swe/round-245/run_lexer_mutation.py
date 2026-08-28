"""Round 245 (SWE-loop D): first real mutation campaign against whence/lexer.py.

lexer.py has never been mutation-tested through harness/swe/mutation.py in
prior rounds (only interp.py has had real campaigns via swe/campaign.py;
values.py got a hand-built scoped campaign in round 233). Uses a narrowed,
fast test_cmd (lexer+parser+interp+early version-regression tests, ~33s
locally, -x so killed mutants fail fast) instead of the full ~875-test suite
(which includes test_examples.py at ~96s alone) -- same shape as round 233's
own scoped `pytest tests/test_values.py tests/test_v16.py` test_cmd, chosen
for tractability on this single-core host, not as a methodology change.
"""
import json
import sys
import time

sys.path.insert(0, "/home/pgain/agi-research-nuc-llm/harness")
from swe import mutation as MU

PROJECT = "/home/pgain/agi-research-nuc-llm/languages/whence"
TEST_CMD = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
            "tests/test_lexer.py", "tests/test_parser.py", "tests/test_interp.py",
            "tests/test_v03.py", "tests/test_v04.py", "tests/test_v05.py", "tests/test_v06.py"]

t0 = time.time()


def on_result(m):
    print("%-8s %6.1fs %s" % (m.status, m.seconds, m.id), flush=True)


rep = MU.mutation_test(PROJECT, ["whence/lexer.py"], TEST_CMD, workers=2, timeout_s=90.0,
                       on_result=on_result)
print(rep.summary())
with open("/home/pgain/agi-research-nuc-llm/state/swe/round-245/lexer-mutation.json", "w") as f:
    json.dump(rep.as_dict(), f, indent=1)
print("TOTAL_WALL %.1fs" % (time.time() - t0))

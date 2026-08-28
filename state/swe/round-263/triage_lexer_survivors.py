"""Round 263 (SWE-loop D): triage round 245's 19 whence/lexer.py mutation survivors.

Round 245 used a narrowed test_cmd (lexer+parser+interp+v03-v06 only, ~33s)
for tractability. This script re-runs each of the 19 survivors against the
FULL fast tier (`run_tests_fast.sh`, 842 tests / ~31s, excludes only the
whence_slow self-hosting/guest-differential tests) to see whether broader
coverage already kills any of them -- the same "confirm empirically, don't
assume" discipline round 233 used for the values.py PMap survivors.
"""
import json
import sys
import time

sys.path.insert(0, "/home/pgain/agi-research-nuc-llm/harness")
from swe import mutation as MU
# NOTE: must go through MU.run_mutant (which uses swe.proc.run_capped) rather
# than a hand-rolled subprocess.run + shutil.copytree -- run_capped injects
# AGI_RESEARCH_ROOT into the subprocess env, the round-149/155 fix for the
# exact ModuleNotFoundError (bench/ref_diff.py reaching for the sibling
# harness/swe package from an isolated languages/whence copy) that a naive
# reimplementation silently reintroduces. Confirmed the hard way: an earlier
# draft of this script called subprocess.run directly and reported 19/19
# "killed" by test_v10.py's two ref_diff fuzz tests -- which fail in ANY
# standalone copy of languages/whence regardless of mutation content.

PROJECT = "/home/pgain/agi-research-nuc-llm/languages/whence"
SURVIVOR_IDS = [
    "lexer.py:40:arith#14", "lexer.py:144:ifneg#27", "lexer.py:58:const#33",
    "lexer.py:61:bool#35", "lexer.py:96:arith#46", "lexer.py:116:const#52",
    "lexer.py:144:cmp#57", "lexer.py:148:const#59", "lexer.py:159:const#63",
    "lexer.py:67:cmp#68", "lexer.py:90:cmp#76", "lexer.py:91:const#77",
    "lexer.py:138:const#89", "lexer.py:155:ifneg#92", "lexer.py:90:arith#94",
    "lexer.py:124:const#101", "lexer.py:127:cmp#102", "lexer.py:127:arith#109",
    "lexer.py:127:const#112",
]

with open(PROJECT + "/whence/lexer.py", encoding="utf-8") as f:
    src = f.read()
all_mutants = {m.id: m for m in MU.generate(src, "whence/lexer.py")}
missing = [i for i in SURVIVOR_IDS if i not in all_mutants]
if missing:
    print("FATAL: lexer.py changed, missing ids:", missing)
    sys.exit(1)

TEST_CMD = [sys.executable, "-m", "pytest", "-q", "-m", "not whence_slow", "tests/"]

results = []
t0 = time.time()
for mid in SURVIVOR_IDS:
    m = all_mutants[mid]
    MU.run_mutant(m, PROJECT, TEST_CMD, timeout_s=90.0)
    tail = "\n".join(m.detail.strip().splitlines()[-5:]) if m.status != "survived" else ""
    results.append({"id": mid, "line": m.lineno, "op": m.op, "description": m.description,
                    "fast_tier_status": m.status, "seconds": round(m.seconds, 1), "detail": tail})
    print("%-8s %6.1fs %-28s %s" % (m.status, m.seconds, mid, m.description), flush=True)

print("TOTAL %.1fs" % (time.time() - t0))
with open("/home/pgain/agi-research-nuc-llm/state/swe/round-263/fast-tier-retest.json", "w") as f:
    json.dump(results, f, indent=1)

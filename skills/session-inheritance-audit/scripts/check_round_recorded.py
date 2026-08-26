#!/usr/bin/env python3
"""check_round_recorded.py — find rounds the driver ran that never made it
into the cumulative state record.

This program's driver (`run_driver.sh`) appends one `round N track=X start`
line and one `round N: success` / `round N: non-success status=...` line to
`logs/driver.log` per round, and the round's own prompt instructs it to
append a `### Round N — <track> — <date>` entry to `state/research-state.md`
and (usually) write a `knowledge/round-N-*.md` file. Nothing enforces that
last part: a round can run real turns, get logged as `success`, and still
leave zero trace in the record if its own final actions never happen —
confirmed live for rounds 167/169/170 (see knowledge/round-171-*.md), each
ending its own turn on a dangling background-job wait instead of finishing
(see skills/one-shot-agent-no-background-wait/SKILL.md).

This script is the automatable half of session-inheritance-audit step 2
("diff the tree against the record") and step 8 ("write the inheritance
into the record FIRST") — it turns "did anyone check whether round N got
recorded" from a manual grep every future round has to remember to do, into
one command with a non-zero exit code when something is missing.

Usage:
    python3 check_round_recorded.py [--driver-log PATH] [--state PATH]
        [--knowledge-dir DIR] [--round-logs-dir DIR] [--since N]

Exit codes: 0 = every round the driver log shows starting also has a
research-state.md entry; 1 = at least one gap found; 2 = usage/IO problem.
"""

import argparse
import glob
import json
import os
import re
import sys

DRIVER_START_RE = re.compile(r"round (\d+) track=(\S+) start")
DRIVER_STATUS_RE = re.compile(r"round (\d+): (success|non-success)(?:\s+status=(\S+))?")
STATE_ENTRY_RE = re.compile(r"^### Round (\d+) [—-]", re.MULTILINE)

# Phrases seen live (rounds 161/167/170) in a round's own final assistant
# message when it ended on a dangling background wait instead of finishing.
DANGLING_WAIT_PHRASES = (
    "standing by",
    "waiting for the background",
    "wait for the background",
    "no further action needed",
    "resume once the",
    "resume automatically when",
    "i'll wait for",
)


def parse_driver_log(path):
    """Return {round_num: {"track": str, "status": str or None}}."""
    rounds = {}
    if not os.path.exists(path):
        return rounds
    with open(path) as f:
        for line in f:
            m = DRIVER_START_RE.search(line)
            if m:
                n = int(m.group(1))
                rounds.setdefault(n, {"track": m.group(2), "status": None})
                rounds[n]["track"] = m.group(2)
                continue
            m = DRIVER_STATUS_RE.search(line)
            if m:
                n = int(m.group(1))
                rounds.setdefault(n, {"track": None, "status": None})
                detail = m.group(3) or m.group(2)
                rounds[n]["status"] = detail
    return rounds


def recorded_rounds(state_path):
    if not os.path.exists(state_path):
        return set()
    with open(state_path) as f:
        text = f.read()
    return {int(m.group(1)) for m in STATE_ENTRY_RE.finditer(text)}


def knowledge_rounds(knowledge_dir):
    out = set()
    for path in glob.glob(os.path.join(knowledge_dir, "round-*.md")):
        m = re.search(r"round-(\d+)-", os.path.basename(path))
        if m:
            out.add(int(m.group(1)))
    return out


def ended_on_dangling_wait(round_log_path):
    """True if the round's own last assistant message reads like it was
    waiting on a background job that will never resume it (see
    skills/one-shot-agent-no-background-wait/SKILL.md)."""
    if not os.path.exists(round_log_path):
        return None
    texts = []
    try:
        with open(round_log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") == "assistant":
                    for c in (obj.get("message") or {}).get("content", []):
                        if c.get("type") == "text":
                            texts.append(c["text"])
    except OSError:
        return None
    if not texts:
        return None
    last = texts[-1].lower()
    return any(p in last for p in DANGLING_WAIT_PHRASES)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--driver-log", default="logs/driver.log")
    ap.add_argument("--state", default="state/research-state.md")
    ap.add_argument("--knowledge-dir", default="knowledge")
    ap.add_argument("--round-logs-dir", default="logs")
    ap.add_argument("--since", type=int, default=0,
                     help="ignore rounds numbered below this")
    args = ap.parse_args()

    driver_rounds = parse_driver_log(args.driver_log)
    state_rounds = recorded_rounds(args.state)
    know_rounds = knowledge_rounds(args.knowledge_dir)

    gaps = []
    for n in sorted(driver_rounds):
        if n < args.since:
            continue
        info = driver_rounds[n]
        in_state = n in state_rounds
        in_knowledge = n in know_rounds
        if in_state:
            continue  # recorded — the knowledge file is a softer signal
        round_log = os.path.join(args.round_logs_dir, "round-%d.json" % n)
        dangling = ended_on_dangling_wait(round_log)
        gaps.append({
            "round": n,
            "track": info.get("track"),
            "status": info.get("status"),
            "has_knowledge_file": in_knowledge,
            "ended_on_dangling_wait": dangling,
        })

    if not gaps:
        print("check_round_recorded: every driver-log round has a "
              "research-state.md entry (0 gaps)")
        return 0

    print("check_round_recorded: %d round(s) ran per the driver log with "
          "NO research-state.md entry:" % len(gaps))
    for g in gaps:
        flag = ""
        if g["ended_on_dangling_wait"]:
            flag = "  <-- ended on a dangling background wait (see " \
                   "one-shot-agent-no-background-wait)"
        print("  round %s track=%s status=%s knowledge_file=%s%s" % (
            g["round"], g["track"], g["status"], g["has_knowledge_file"],
            flag,
        ))
    return 1


if __name__ == "__main__":
    sys.exit(main())

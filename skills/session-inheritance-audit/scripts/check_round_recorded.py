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
        [--knowledge-dir DIR] [--round-logs-dir DIR] [--repo-root DIR]
        [--since N]

Exit codes: 0 = every round the driver log shows starting also has a
research-state.md entry; 1 = at least one gap found; 2 = usage/IO problem.

Each reported gap also carries `git_committed` (True/False/None): a
best-effort `git log --all --oneline` grep for "round N" in a commit
subject. This catches a round whose OWN text (a knowledge file, a state
file addendum) claims it ran `git commit` when the tool call never
actually landed — confirmed live twice (rounds 182 and 184, neither killed
mid-flight; see `committed_per_git_log`'s docstring below).
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys

# Repo root is three levels up from this script (scripts/ ->
# session-inheritance-audit/ -> skills/ -> root) — added so
# `harness.driver_health` is importable regardless of the caller's cwd, not
# just when run from the repo root like the path defaults below assume.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
try:
    from harness.driver_health import summarize_turns as _summarize_turns
except ImportError:
    # Skill may be copied somewhere without the harness/ package (e.g. a
    # promoted ~/.hermes/skills/ copy per CURRICULUM.md's endgame) — the
    # `interrupted` column just degrades to None rather than crashing.
    _summarize_turns = None

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


def recorded_rounds(state_path, archive_paths=()):
    """Union of `### Round N —` headings in `state_path` and every path in
    `archive_paths` (missing archive files are skipped, not an error).

    `research-state.md` periodically archives its own oldest round-log
    entries to `state/research-state-archive.md` to keep a plain `Read` of
    the live file from truncating (done for rounds 1-136 by round 163, then
    137-174 by round 193) — the heading text itself is moved verbatim, not
    duplicated or summarized. A caller that only reads `state_path` treats
    every archived round as an unrecorded gap forever after, even though it
    was recorded and then relocated for file-size reasons alone. Confirmed
    live (round 231): a plain run flagged 32 rounds; 13 of them (154-174
    minus a few genuine gaps) had a heading sitting in the archive file the
    whole time.
    """
    rounds = set()
    for path in (state_path,) + tuple(archive_paths):
        if not os.path.exists(path):
            continue
        with open(path) as f:
            text = f.read()
        rounds |= {int(m.group(1)) for m in STATE_ENTRY_RE.finditer(text)}
    return rounds


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


def committed_per_git_log(round_num, repo_root="."):
    """Best-effort check: does any commit's subject line mention this round
    number (e.g. "Round 184 (...")? Returns True/False, or None if git or a
    repo isn't available (e.g. a bare tmp-dir test fixture) — a round can
    write real, disk-persisted prose CLAIMING it ran `git commit` (a state
    file addendum, a knowledge file's own opening note) without the commit
    tool call ever actually landing. Confirmed live twice, independently:
    round 182 (language(C), see knowledge/round-188-*.md) and round 184
    (NUC-integration(E), see this round's own knowledge file) both ended
    cleanly (driver log: round 182 status=error:max_turns/interrupted=false,
    round 184 status=success/interrupted=false — NEITHER was killed
    mid-flight) yet left real, tested diffs sitting uncommitted while their
    own text said the diff had been committed. `git log` is the only source
    that cannot be fooled by a round's own narration — grep it, don't trust
    the prose, even when the prose is sitting on disk in a place that looks
    authoritative.

    One more false-positive shape, found live for round 197 (round 213):
    a LATER round's own housekeeping commit can mention round N purely to
    explain that round N itself failed to commit anything — e.g. round
    198's `3eaf50a "...covers rounds 197-198, left uncommitted by round
    197"` — which is the exact opposite of evidence that round N landed.
    The bare substring match above reads that as `True`. `_NOT_COMMITTED_RE`
    excludes a line from counting as evidence when it explicitly says round
    N is the one who LEFT something uncommitted; if that is the only
    matching line, the verdict correctly falls through to `False`. This is
    deliberately narrow (matches only "left uncommitted by round N") rather
    than a general sentiment classifier — a phrase like round 155's own
    "land ...fix, uncommitted since round 155" describes a *different*
    round (201) actually landing round 155's real work and must stay
    `True`; that phrasing doesn't match `_NOT_COMMITTED_RE` so it isn't
    affected."""
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "log", "--all", "--oneline"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    pattern = re.compile(r"round\s+%d\b" % round_num, re.IGNORECASE)
    not_committed_pattern = re.compile(
        r"left\s+uncommitted\s+by\s+round\s+%d\b" % round_num, re.IGNORECASE)
    matches = [line for line in out.stdout.splitlines() if pattern.search(line)]
    evidence = [line for line in matches if not not_committed_pattern.search(line)]
    return bool(evidence)


def load_acknowledged_gaps(path):
    """Return {round_num: reason} from a JSON file mapping round numbers
    (as string keys) to a one-line reason they're a known, already-verified
    non-gap (e.g. no surviving diff, or reconciled in research-state.md
    prose without ever getting its own `### Round N —` heading).

    Without this, every round that runs this script re-flags and has to
    re-verify the SAME historical rounds from scratch — confirmed live
    (round 231): a fresh run flagged 32 rounds; after fixing the archive
    gap (see `recorded_rounds`) 18 remained, and every one of them was
    already independently explained somewhere in research-state.md's own
    prose (named in the 'Recurring pattern' list, or individually as for
    rounds 185/186/190/191) — just never with a matching heading. Missing
    or malformed files degrade to "nothing acknowledged" (an empty dict),
    matching this script's existing degrade-gracefully convention for
    optional inputs (see `_summarize_turns`, `committed_per_git_log`).
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    for k, v in data.items():
        if k.startswith("_"):
            continue
        try:
            out[int(k)] = v
        except ValueError:
            continue
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--driver-log", default="logs/driver.log")
    ap.add_argument("--state", default="state/research-state.md")
    ap.add_argument("--archive", action="append", default=None,
                     help="additional file(s) to scan for `### Round N —` "
                          "headings alongside --state (e.g. an archive the "
                          "state file periodically moves old entries into); "
                          "repeatable, missing paths are skipped silently. "
                          "Defaults to state/research-state-archive.md alone "
                          "when omitted; passing this flag replaces that "
                          "default rather than adding to it.")
    ap.add_argument("--knowledge-dir", default="knowledge")
    ap.add_argument("--round-logs-dir", default="logs")
    ap.add_argument("--repo-root", default=".",
                     help="repo root to run `git log` against for the "
                          "commit cross-check (best-effort; degrades to "
                          "git_committed=None if not a git repo)")
    ap.add_argument("--since", type=int, default=0,
                     help="ignore rounds numbered below this")
    ap.add_argument("--ack-file", default="state/known-record-gaps.json",
                     help="JSON file of round -> reason for rounds already "
                          "verified as known, non-actionable gaps (missing "
                          "file degrades to none acknowledged, not an "
                          "error). See load_acknowledged_gaps docstring.")
    ap.add_argument("--show-acknowledged", action="store_true",
                     help="also print acknowledged gaps (suppressed from "
                          "the exit-code-bearing list by default)")
    args = ap.parse_args()
    archive_paths = (args.archive if args.archive is not None
                      else ["state/research-state-archive.md"])
    acknowledged = load_acknowledged_gaps(args.ack_file)

    driver_rounds = parse_driver_log(args.driver_log)
    state_rounds = recorded_rounds(args.state, archive_paths)
    know_rounds = knowledge_rounds(args.knowledge_dir)

    gaps = []
    ack_hits = []
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
        interrupted = None
        if _summarize_turns is not None:
            summary = _summarize_turns(round_log)
            if summary is not None:
                interrupted = summary.get("interrupted")
        g = {
            "round": n,
            "track": info.get("track"),
            "status": info.get("status"),
            "has_knowledge_file": in_knowledge,
            "ended_on_dangling_wait": dangling,
            "interrupted": interrupted,
            "git_committed": committed_per_git_log(n, args.repo_root),
        }
        if n in acknowledged:
            ack_hits.append((g, acknowledged[n]))
        else:
            gaps.append(g)

    if args.show_acknowledged and ack_hits:
        print("check_round_recorded: %d round(s) are known gaps, already "
              "verified and acknowledged in %s (not counted below):"
              % (len(ack_hits), args.ack_file))
        for g, reason in ack_hits:
            print("  round %s: %s" % (g["round"], reason))

    if not gaps:
        suffix = (" (%d pre-acknowledged, see %s)" % (len(ack_hits), args.ack_file)
                   if ack_hits else "")
        print("check_round_recorded: every driver-log round has a "
              "research-state.md entry (0 gaps)%s" % suffix)
        return 0

    print("check_round_recorded: %d round(s) ran per the driver log with "
          "NO research-state.md entry (%d more pre-acknowledged, see %s):"
          % (len(gaps), len(ack_hits), args.ack_file))
    for g in gaps:
        flags = []
        if g["ended_on_dangling_wait"]:
            flags.append("ended on a dangling background wait (see "
                          "one-shot-agent-no-background-wait)")
        if g["git_committed"] is False:
            flags.append("NOT in git log — any claim in this round's own "
                          "text that it committed is unverified/false")
        flag = ("  <-- " + "; ".join(flags)) if flags else ""
        print("  round %s track=%s status=%s knowledge_file=%s "
              "interrupted=%s git_committed=%s%s" % (
                  g["round"], g["track"], g["status"], g["has_knowledge_file"],
                  g["interrupted"], g["git_committed"], flag,
              ))
    return 1


if __name__ == "__main__":
    sys.exit(main())

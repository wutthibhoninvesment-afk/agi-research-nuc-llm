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
research-state.md entry, AND driver.log's own round-number sequence has no
holes, AND nothing is unattributed in the working tree, AND every
escalation pin still holds; 1 = at least one gap found (any shape);
2 = usage/IO problem. An ACKNOWLEDGED escalation does not change the
exit code; an escalation whose pin has expired, or one that no longer
matches anything, does.

Round 259 added a second, structurally distinct gap shape:
`missing_round_numbers` flags a round number that `run_driver.sh`'s own
counter (`state/round_counter`) consumed but that never logged so much as
a `round N track=... start` line in `logs/driver.log` — confirmed live for
round 229 (root cause unconfirmed). Every other check in this file starts
from `parse_driver_log`'s output, so a round with NO driver-log line at
all is invisible to them; this is the one check that looks at driver.log's
own round-number sequence instead of cross-referencing it against
something else.

Each reported gap also carries `git_committed` (True/False/None): a
best-effort `git log --all --oneline` grep for "round N" in a commit
subject. This catches a round whose OWN text (a knowledge file, a state
file addendum) claims it ran `git commit` when the tool call never
actually landed — confirmed live twice (rounds 182 and 184, neither killed
mid-flight; see `committed_per_git_log`'s docstring below).

Round 273 added a THIRD, structurally distinct gap shape:
`recorded_but_uncommitted_rounds` flags a round with a research-state.md
heading AND a knowledge file — so nothing else in this file would ever
flag it — whose knowledge file itself never landed in git (checked via
`_file_ever_tracked`'s file-presence lookup, NOT `committed_per_git_log`'s
subject-line text match — the latter false-flagged 3 real, safely
committed rounds in the live repo the first time this was tried; see
`_file_ever_tracked`'s own docstring). Confirmed live for round 266 (found
by round 267's manual `git status` audit, not by this script): round 266's
heading and knowledge file were both written to disk before the round
died, so `main`'s per-round loop treated it as fully `in_state` and never
checked git for it at all. See `recorded_but_uncommitted_rounds`'s own
docstring below.

Round 291 added a FOURTH, structurally distinct gap shape:
`unattributed_dirty_paths` flags any path `git status --porcelain` reports
right now that isn't on the permanent allowlist (`state/known-standing-
dirty-paths.json`) — the automated form of round 283's own still-open
backlog item 3 (`committed_per_git_log`'s "coverage gap"): a commit whose
SUBJECT names round N is not proof round N's ENTIRE diff landed. Confirmed
live for round 282 (found by round 283's manual `git status --short`, not
by this script at the time): round 282 committed the "land round 281" half
of its own round but left its own new v0.14.6 feature (three modified
files, one new knowledge file) genuinely uncommitted while
`committed_per_git_log(282)` still read `True`, because SOME commit that
round did make correctly named "Round 282" in its subject. Unlike the
other three checks here, this one is not keyed to any specific round
number — it is the raw working-tree signal every one of rounds 265/283 had
to read by hand before landing a predecessor's leftover work, turned into
one automatable, round-agnostic cross-check instead of something every
future round must remember to run itself. See `unattributed_dirty_paths`'s
own docstring below.

Round 373 added a FIFTH gap shape, and it exists because shape 4 has a
failure mode of its own: it cannot tell "nobody has looked at this" from
"somebody looked, decided, and the decision was to leave it". Measured
from `logs/driver.log`: `languages/whence/SECURITY.md` -- a TRACKED file a
separate autonomous system rewrote, whose new text asserts four security
controls this repo does not have, adjudicated by round 349 and escalated
to the operator because the call is theirs -- appears in the shape-4
output of 25 CONSECUTIVE ROUNDS (349-373), and in 13 of them it is the
ONLY unattributed path. More than half the time, this script's entire
non-zero exit and the entire NOTE injected into the next round's prompt
existed for something already decided.

Round 349 was right to refuse the shape-4 allowlist for it ("allowlisting
a tracked file would mean 'never look at this diff again', which is the
wrong answer") -- so the fifth shape is not an allowlist.
`state/known-escalated-diffs.json` PINS each acknowledged diff by BOTH
blob hashes (working tree and HEAD); `classify_escalated_diffs` suppresses
a path only while both still match, reports it LOUDER than an ordinary
unattributed path the moment either moves, and reports an entry that has
stopped matching anything at all so a dead acknowledgement gets deleted
rather than read as coverage. See `load_escalated_diffs` and
`classify_escalated_diffs` below.
"""

import argparse
import functools
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


def missing_round_numbers(driver_rounds, since=0):
    """Return sorted round numbers with NO `round N track=... start` (or
    status) line anywhere in driver.log, despite sitting strictly between
    two round numbers that DO have one — a structurally different gap
    shape than everything else this script checks (a round WITH a
    driver-log entry but no research-state.md entry). `parse_driver_log`
    can only ever report a round it found a log line for; a round number
    that gets consumed by `run_driver.sh`'s own counter
    (`state/round_counter`) but never logs even its own start line is
    invisible to every other function here — there is nothing to look up
    a research-state.md entry FOR.

    Confirmed live: round 229 (round_counter jumped 228->230 between two
    consecutive driver.log lines 45s apart, with zero `round 229 ...`
    lines of any kind, no `logs/round-229.json`, and no lock-contention
    message anywhere in driver.log for that window — root cause
    unconfirmed; see `knowledge/round-259-*.md`). This is the only such
    gap across the full 152-259 history on record as of round 259.

    Only checks the RANGE actually present in `driver_rounds` (there is
    no signal at all below its own minimum or above its own maximum, so
    nothing to compare against there); honors `since` as a post-filter,
    same "ignore rounds numbered below this" semantics the rest of this
    script already uses.
    """
    nums = sorted(driver_rounds)
    if not nums:
        return []
    lo, hi = nums[0], nums[-1]
    return [n for n in range(lo, hi + 1) if n not in driver_rounds and n >= since]


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


def _knowledge_file_paths(knowledge_dir):
    """Return {round_num: [path, ...]} for every knowledge/round-N-*.md
    file found. Factored out of `knowledge_rounds` (round 273) so
    `recorded_but_uncommitted_rounds` can check each round's actual FILE
    for git presence instead of re-deriving just the round-number set."""
    out = {}
    for path in glob.glob(os.path.join(knowledge_dir, "round-*.md")):
        m = re.search(r"round-(\d+)-", os.path.basename(path))
        if m:
            out.setdefault(int(m.group(1)), []).append(path)
    return out


def knowledge_rounds(knowledge_dir):
    return set(_knowledge_file_paths(knowledge_dir))


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
    The bare substring match above reads that as `True`.

    Round 213's original fix only excluded the exact phrase "left
    uncommitted by round N". Round 267 found a second instance of the same
    underlying shape, live in the real repo, that phrasing was too narrow
    to catch: round 264's own work sat genuinely uncommitted while round
    263's commit message — `dab7050 "Round 263 (SWE-loop D, landed by
    round 264): ..."` — happened to contain the substring "round 264" in
    its own "landed by" credit clause. `committed_per_git_log(264)` read
    `True` from that line alone before any round-264 commit existed (see
    round 264's own research-state.md entry). Grepping the full history
    for `by round N` (any N) turns up a DOZEN structurally identical lines —
    "landed by round N", "reconciled by round N" — spanning rounds
    210/212, 217/218, 222/223, 224/227, 226/227, 263/264, plus the
    original 197/198 — every one crediting round N as the ACTOR that
    handled some OTHER round's leftover work, never as evidence that round
    N's own work is IN this commit. `_NOT_EVIDENCE_RE` below generalizes
    round 213's fix from that one exact phrase to the whole family: any
    "by round N" mention is excluded from counting as evidence FOR round
    N, regardless of which verb precedes "by". This is still deliberately
    narrow (anchored on the preposition "by") rather than a general
    sentiment classifier — a phrase like round 155's own "land ...fix,
    uncommitted SINCE round 155" describes a *different* round (201)
    actually landing round 155's real work and must stay `True`; "since"
    isn't "by", so that phrasing doesn't match `_NOT_EVIDENCE_RE` and
    isn't affected, nor is round 221's own "landing round 220" (no "by"
    at all — round 221 really did land round 220's work in that same
    commit).

    Round 273: the actual `git log` invocation is memoized per `repo_root`
    (`_cached_git_log_lines`) because round 273's new
    `recorded_but_uncommitted_rounds` check can call this function once per
    RECORDED round (potentially the whole history) instead of only once per
    unrecorded gap as before — without caching, a single script run would
    re-run `git log --all --oneline` from scratch for every one of those
    rounds even though the output cannot change mid-run."""
    lines = _cached_git_log_lines(repo_root)
    if lines is None:
        return None
    pattern = re.compile(r"round\s+%d\b" % round_num, re.IGNORECASE)
    not_evidence_pattern = re.compile(
        r"\bby\s+round\s+%d\b" % round_num, re.IGNORECASE)
    matches = [line for line in lines if pattern.search(line)]
    evidence = [line for line in matches if not not_evidence_pattern.search(line)]
    return bool(evidence)


@functools.lru_cache(maxsize=None)
def _cached_git_log_lines(repo_root):
    """Return `git log --all --oneline` output as a tuple of lines for
    `repo_root`, or None if git/the repo isn't available. Memoized because
    `committed_per_git_log` can now be called many times per script run
    (once per recorded round, not just once per gap) with the same
    `repo_root` and an unchanging answer each time — see that function's
    docstring. Cache is keyed on `repo_root` alone, which is safe within a
    single process because nothing in this script commits to the repo it is
    inspecting; a caller that commits mid-run (no test here does) would need
    `_cached_git_log_lines.cache_clear()` first."""
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "log", "--all", "--oneline"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return tuple(out.stdout.splitlines())


@functools.lru_cache(maxsize=None)
def _cached_tracked_paths(repo_root):
    """Return a frozenset of every path (repo-root-relative, forward
    slashes, matching `git`'s own output convention) that has ever
    appeared in any commit's tree, via ONE `git log --all --name-only
    --pretty=format:` call — or None if git/the repo isn't available.

    Memoized per `repo_root` for the same reason as `_cached_git_log_lines`:
    `_file_ever_tracked` can be called once per recorded round (potentially
    the whole history) and the answer cannot change mid-run. Doing this as
    ONE call up front rather than one `git log -- <path>` subprocess PER
    candidate file (an earlier draft of this check) keeps the per-round
    driver overhead flat as the round count keeps growing, instead of
    O(rounds) subprocess spawns."""
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "log", "--all", "--name-only",
             "--pretty=format:"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return frozenset(line.strip() for line in out.stdout.splitlines()
                      if line.strip())


def _file_ever_tracked(path, repo_root="."):
    """True if `path` appears in ANY commit's tree (per
    `_cached_tracked_paths`); False if git ran cleanly and found nothing;
    None if git/the repo isn't available (degrade-gracefully convention
    shared with `committed_per_git_log`).

    Deliberately checks the FILE'S OWN presence rather than grepping commit
    SUBJECT lines for "round N" the way `committed_per_git_log` does —
    confirmed live (round 273) that subject-line matching alone produces
    false positives here: round 166's commit ("seventh live window ...
    backlog reconciliation") landed round 154's and round 160's own
    knowledge files without ever mentioning either round number in its
    subject, and round 164's commit landed round 162's file under the text
    "retroactive round-146/162 knowledge files" — a HYPHEN
    ("round-162"), not the space `committed_per_git_log`'s `round\\s+N\\b`
    pattern requires. All three are genuinely, safely committed; a first
    draft of `recorded_but_uncommitted_rounds` built on
    `committed_per_git_log` alone flagged all three as false gaps before
    this function replaced it. `path` is converted to repo-relative before
    the lookup so it resolves correctly regardless of whether the caller
    passed an absolute path or one relative to a different cwd than
    `repo_root`."""
    tracked = _cached_tracked_paths(repo_root)
    if tracked is None:
        return None
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(repo_root))
    return rel.replace(os.sep, "/") in tracked


def recorded_but_uncommitted_rounds(driver_rounds, state_rounds,
                                     knowledge_dir="knowledge", repo_root=".",
                                     since=0):
    """Return sorted round numbers with BOTH a research-state.md heading AND
    a knowledge/round-N-*.md file (so `main`'s existing `if in_state:
    continue` skips them entirely, and every other check in this file would
    call them fully recorded) whose knowledge file(s) still never landed in
    git — see `_file_ever_tracked` for why file presence, not commit-
    subject text, is what this checks.

    This is a THIRD gap shape, distinct from `missing_round_numbers` (no
    driver-log line at all) and the main per-round loop (no research-
    state.md heading). Confirmed live: round 266's heading and knowledge
    file were both written to disk before the round died, so the `git
    commit` its own text implied had happened was never checked — round 267
    only found the real, uncommitted diff via a manual `git status` audit,
    not this script (see round 267's own knowledge file, and the
    "detector that only writes its finding to a log file is never read"
    pitfall in SKILL.md for why an unchecked gap shape is as bad as no
    detector at all).

    A round with NO knowledge file matching its number is skipped here (not
    this check's shape — `in_state and not in_knowledge` already falls
    through the main loop's own gap reporting instead). A round where git
    itself is unavailable (`_file_ever_tracked` returns None for every one
    of its files, no True) is also skipped rather than falsely flagged —
    unverifiable is not the same as missing.

    Only considers rounds `driver_rounds` actually has a log line for, same
    as every other check here — a round missing from driver.log entirely is
    `missing_round_numbers`'s shape, not this one."""
    paths_by_round = _knowledge_file_paths(knowledge_dir)
    out = []
    for n in sorted(driver_rounds):
        if n < since or n not in state_rounds:
            continue
        paths = paths_by_round.get(n)
        if not paths:
            continue
        results = [_file_ever_tracked(p, repo_root) for p in paths]
        if any(r is True for r in results):
            continue
        if all(r is False for r in results):
            out.append(n)
    return out


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


def working_tree_status(repo_root="."):
    """Return a list of (status_code, path) pairs from `git status
    --porcelain` for `repo_root` (paths repo-root-relative, forward
    slashes, matching git's own convention), or None if git/the repo isn't
    available — same degrade-gracefully convention as
    `committed_per_git_log`/`_file_ever_tracked`.

    This is the raw signal round 283 read BY HAND (`git status --short`)
    before landing round 282's leftover work, because `committed_per_git_
    log`'s own per-round check has a real, structural blind spot: a commit
    whose SUBJECT names round N is not proof round N's ENTIRE diff landed
    (see this module's own docstring, "Round 291 added a FOURTH..."). A
    rename line (`R  old -> new`) keeps only the destination path — the
    only status shape `git status --porcelain` emits with an embedded
    separator instead of one bare path per line. A wholly untracked
    DIRECTORY (no committed file inside it yet) reports as one line for
    the directory itself (`?? some/new/dir/`), not one line per file
    inside it — an allowlist entry for that case needs the directory path
    (trailing slash and all), not any individual file path underneath it.
    """
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    result = []
    for line in out.stdout.splitlines():
        if not line:
            continue
        code, path = line[:2], line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        result.append((code, path))
    return result


def load_standing_dirty_paths(path):
    """Return a set of repo-relative paths from a JSON file
    (`{"paths": [...]}`, plus an ignored `_comment` key) that are
    PERMANENTLY expected to show up in `git status --porcelain` and must
    never count as evidence of a round's own uncommitted work — the shared
    round counter every round bumps early in its own run (`state/round_
    counter`) and the handful of files a wholly separate autonomous system
    (the Hermes gateway; see this file's own "hermes-not-a-driver-process"
    pitfall in SKILL.md) leaves permanently untracked under `languages/
    whence/`. Missing/malformed file degrades to an empty set (same
    convention as `load_acknowledged_gaps`) rather than an error."""
    if not os.path.exists(path):
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return set()
    paths = data.get("paths", []) if isinstance(data, dict) else data
    return {p for p in paths if isinstance(p, str)}


def _first_sentence(text, limit=180):
    """Return a one-line gist of a registry `reason` for the printed line.

    The reasons in `state/known-escalated-diffs.json` are deliberately long
    — an entry has to carry enough for a future round to re-adjudicate
    without re-deriving anything. But this script's stdout is pasted
    VERBATIM into the next round's prompt by `run_driver.sh`, and the whole
    point of the fifth gap shape is to make an already-decided item cost
    less attention, not more. Print the gist and the registry path; the
    round that needs the rest knows where it is."""
    text = " ".join((text or "").split())
    if not text:
        return "(no reason recorded)"
    cut = text.find(". ")
    if 0 < cut + 1 <= limit:
        return text[:cut + 1]
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


ESCALATION_ACKNOWLEDGED = "acknowledged"
ESCALATION_CHANGED = "changed"
ESCALATION_RESOLVED = "resolved"


def worktree_blob_hash(path, repo_root="."):
    """Return `git hash-object`'s SHA-1 for `path` AS IT SITS IN THE WORKING
    TREE, or None if git/the file isn't available (same degrade-gracefully
    convention as `working_tree_status`).

    This is half of an escalation FINGERPRINT (see `load_escalated_diffs`).
    Content-addressing, not mtime, is what makes a tracked-file
    acknowledgement safe: mtime moves when a third party rewrites the file
    with identical bytes and stays put when a `touch`-free edit lands, and
    neither is what "is this still the diff someone adjudicated" asks."""
    if not os.path.exists(os.path.join(repo_root, path)):
        return None
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "hash-object", "--", path],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def head_blob_hash(path, repo_root="."):
    """Return the SHA-1 of `path`'s blob AT HEAD, or None if the path isn't
    in HEAD (untracked, or deleted there) or git isn't available.

    The other half of the fingerprint, and it is not redundant: a diff is a
    PAIR. If a later round commits a different base for the same file, the
    working-tree bytes can be untouched while the diff being acknowledged is
    a different diff. Pinning only the working-tree side would keep
    suppressing an acknowledgement that no longer describes anything."""
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "rev-parse", "--verify", "-q",
             "HEAD:" + path],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def load_escalated_diffs(path):
    """Return {repo-relative path: entry dict} from a JSON registry of
    KNOWN-ESCALATED TRACKED-FILE DIFFS — the fifth gap shape (round 373).

    Shape: `{"_comment": ..., "escalations": {"<path>": {"reason": str,
    "escalated_round": int, "worktree_blob": str, "head_blob": str}}}`.
    Missing/malformed degrades to `{}` (same convention as
    `load_acknowledged_gaps`/`load_standing_dirty_paths`).

    WHY THIS IS NOT `state/known-standing-dirty-paths.json`. That registry
    models UNTRACKED leftovers a separate autonomous system permanently
    writes, and its entries are unconditional: the path is never looked at
    again. Round 349 refused, on principle, to put a TRACKED file another
    system EDITS into it — "allowlisting a tracked file would mean 'never
    look at this diff again', which is the wrong answer for either." That
    refusal was right and it left `languages/whence/SECURITY.md` firing the
    round-291 dirty-tree check in 25 consecutive rounds (349-373 per
    `logs/driver.log`), 13 of them as the ONLY unattributed path — i.e. more
    than half the time the check's entire non-zero exit, and the entire note
    injected into the next round's prompt, existed for an item already
    adjudicated and deliberately left open.

    The resolution is that an acknowledgement here is PINNED TO CONTENT.
    `classify_escalated_diffs` suppresses a path only while both blob hashes
    still match; the moment a third party edits the file again, or a commit
    moves the base underneath it, the entry stops suppressing and the path
    is reported LOUDER than an ordinary unattributed one, because a new edit
    by a third party to a tracked file is exactly the event worth seeing.
    "Never look at this diff again" is not what this file can express."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    entries = data.get("escalations", {})
    if not isinstance(entries, dict):
        return {}
    return {k: v for k, v in entries.items()
            if not k.startswith("_") and isinstance(v, dict)}


def classify_escalated_diffs(registry, status, repo_root="."):
    """Classify every entry of `registry` (from `load_escalated_diffs`)
    against `status` (a `working_tree_status` list, or `[]`/None). Returns
    one dict per entry, in registry order, with a `state` of:

    - `ESCALATION_ACKNOWLEDGED` — the path is still dirty AND both recorded
      blob hashes match what's on disk/at HEAD. Suppressed from the gap
      list; reported on its own quiet line with a carried-rounds count.
    - `ESCALATION_CHANGED` — the path is dirty but the fingerprint does not
      match, could not be computed, or was never recorded. NOT suppressed.
    A `status` of None (git unavailable / not a checkout) yields `[]`: see
    the comment at the top of the body for why that is a different question
    from the fail-closed rule.

    - `ESCALATION_RESOLVED` — the path is not dirty at all: the diff was
      committed, reverted, or the file deleted. The entry now suppresses
      NOTHING, and a dead acknowledgement is worse than no acknowledgement
      because it reads as coverage. Reported so it gets deleted.

    FAIL-CLOSED is deliberate, and it is round 367's rule 10 in a different
    file: a run that could not establish its own precondition may not
    narrow. If git is unavailable the observed hashes come back None and the
    entry lands in `CHANGED` rather than `ACKNOWLEDGED` — an
    acknowledgement you cannot VERIFY must not silence anything. Everywhere
    else in this module an unavailable git degrades to "don't flag"; here
    that would mean a suppression rule whose precondition failed open, which
    is the one direction that loses information."""
    if status is None:
        # We could not READ the working tree (no git, not a checkout). Every
        # state below is a claim about the dirty set, so none of them can be
        # made — including RESOLVED, which would otherwise fire on every
        # entry and read as "your acknowledgements are all dead". This is the
        # module's ordinary don't-cry-wolf degrade, and it is NOT in tension
        # with the fail-closed rule below: that one applies when the tree IS
        # known and the path IS dirty, where refusing to suppress is the
        # conservative answer. Here there is nothing to suppress either way.
        return []
    dirty = {path: code for code, path in status}
    out = []
    for path, entry in registry.items():
        rec_wt = entry.get("worktree_blob")
        rec_head = entry.get("head_blob")
        row = {
            "path": path,
            "code": dirty.get(path),
            "reason": entry.get("reason", ""),
            "escalated_round": entry.get("escalated_round"),
            "recorded_worktree_blob": rec_wt,
            "recorded_head_blob": rec_head,
            "observed_worktree_blob": None,
            "observed_head_blob": None,
            "detail": "",
        }
        if path not in dirty:
            row["state"] = ESCALATION_RESOLVED
            row["detail"] = ("path is not dirty — the diff was committed, "
                             "reverted, or the file deleted")
            out.append(row)
            continue
        obs_wt = worktree_blob_hash(path, repo_root)
        obs_head = head_blob_hash(path, repo_root)
        row["observed_worktree_blob"] = obs_wt
        row["observed_head_blob"] = obs_head
        if not rec_wt or not rec_head:
            row["state"] = ESCALATION_CHANGED
            row["detail"] = ("registry entry records no fingerprint — an "
                             "unpinned acknowledgement cannot be trusted")
        elif obs_wt is None or obs_head is None:
            row["state"] = ESCALATION_CHANGED
            row["detail"] = ("fingerprint could not be computed (git "
                             "unavailable or path missing) — fail-closed")
        elif obs_wt != rec_wt and obs_head != rec_head:
            row["state"] = ESCALATION_CHANGED
            row["detail"] = ("both halves moved: working tree %s != %s and "
                             "HEAD %s != %s"
                             % (obs_wt[:12], rec_wt[:12],
                                obs_head[:12], rec_head[:12]))
        elif obs_wt != rec_wt:
            row["state"] = ESCALATION_CHANGED
            row["detail"] = ("working-tree content moved: %s != recorded %s "
                             "— a third party edited this tracked file "
                             "AGAIN; re-inspect before re-pinning"
                             % (obs_wt[:12], rec_wt[:12]))
        elif obs_head != rec_head:
            row["state"] = ESCALATION_CHANGED
            row["detail"] = ("base moved: HEAD blob %s != recorded %s — same "
                             "bytes on disk, different diff"
                             % (obs_head[:12], rec_head[:12]))
        else:
            row["state"] = ESCALATION_ACKNOWLEDGED
        out.append(row)
    return out


def unattributed_dirty_paths(repo_root=".", standing_paths=frozenset(),
                              status=None):
    """Return the (status_code, path) pairs from `working_tree_status` that
    are NOT in `standing_paths` — the automatable half of round 283's
    still-open `git_committed`-coverage gap (see `working_tree_status`'s
    own docstring). Returns `[]` (not `None`) both when git is unavailable
    and when the tree is fully clean/standing-only — every caller here
    treats both as "nothing to flag," the same degrade-gracefully
    convention every other check in this file already uses; `working_tree_
    status`'s own `None` is only meaningful to a caller that needs to
    distinguish "clean" from "couldn't check," and nothing downstream of
    this function does.

    `status` lets a caller pass a `working_tree_status` list it already has
    (round 373). `main` does, so this check and `classify_escalated_diffs`
    see ONE snapshot: a separate autonomous system writes into this tree
    while rounds run (see `load_escalated_diffs`), and two independent `git
    status` calls could disagree about which paths are dirty — an
    escalation could be suppressed against a snapshot that no longer
    matches the one the gap list was built from."""
    if status is None:
        status = working_tree_status(repo_root)
    if not status:
        return []
    return [(code, path) for code, path in status if path not in standing_paths]


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
    ap.add_argument("--standing-dirty-file",
                     default="state/known-standing-dirty-paths.json",
                     help="JSON allowlist of repo-relative paths that "
                          "permanently show up in `git status --porcelain` "
                          "(the shared round counter, files a separate "
                          "autonomous system leaves untracked) and must "
                          "never count as an unattributed dirty-tree gap. "
                          "Missing file degrades to an empty allowlist.")
    ap.add_argument("--escalated-diffs-file",
                     default="state/known-escalated-diffs.json",
                     help="JSON registry of KNOWN-ESCALATED TRACKED-FILE "
                          "diffs (round 373): a tracked file a separate "
                          "system edited, already adjudicated, deliberately "
                          "left uncommitted and escalated to the operator. "
                          "Each entry PINS the exact diff by blob hash, so "
                          "the acknowledgement expires the moment the "
                          "content or its base moves. Missing file degrades "
                          "to an empty registry. See load_escalated_diffs.")
    args = ap.parse_args()
    archive_paths = (args.archive if args.archive is not None
                      else ["state/research-state-archive.md"])
    acknowledged = load_acknowledged_gaps(args.ack_file)
    standing_dirty = load_standing_dirty_paths(args.standing_dirty_file)
    escalated = load_escalated_diffs(args.escalated_diffs_file)

    driver_rounds = parse_driver_log(args.driver_log)
    state_rounds = recorded_rounds(args.state, archive_paths)
    know_rounds = knowledge_rounds(args.knowledge_dir)

    seq_gaps = missing_round_numbers(driver_rounds, args.since)
    seq_ack_hits = [(n, acknowledged[n]) for n in seq_gaps if n in acknowledged]
    seq_unacked = [n for n in seq_gaps if n not in acknowledged]

    uncommitted_gaps = recorded_but_uncommitted_rounds(
        driver_rounds, state_rounds, args.knowledge_dir, args.repo_root,
        args.since)
    uncommitted_ack_hits = [(n, acknowledged[n]) for n in uncommitted_gaps
                             if n in acknowledged]
    uncommitted_unacked = [n for n in uncommitted_gaps if n not in acknowledged]

    # ONE working-tree snapshot feeds both the round-291 dirty-path check
    # and the round-373 escalation classifier — see unattributed_dirty_paths.
    tree_status = working_tree_status(args.repo_root)
    escalations = classify_escalated_diffs(escalated, tree_status,
                                            args.repo_root)
    esc_ack = [e for e in escalations if e["state"] == ESCALATION_ACKNOWLEDGED]
    esc_changed = [e for e in escalations if e["state"] == ESCALATION_CHANGED]
    esc_resolved = [e for e in escalations
                     if e["state"] == ESCALATION_RESOLVED]
    # Every registry path is reported by the escalation section (acknowledged,
    # changed or resolved) and never ALSO as a bare unattributed path, so each
    # path prints exactly once, under its most specific heading.
    registry_paths = set(escalated)
    dirty_paths = [(code, path) for code, path
                    in unattributed_dirty_paths(args.repo_root, standing_dirty,
                                                 status=tree_status)
                    if path not in registry_paths]
    latest_round = max(driver_rounds) if driver_rounds else None

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

    if args.show_acknowledged and (ack_hits or seq_ack_hits or uncommitted_ack_hits):
        print("check_round_recorded: %d round(s) are known gaps, already "
              "verified and acknowledged in %s (not counted below):"
              % (len(ack_hits) + len(seq_ack_hits) + len(uncommitted_ack_hits),
                 args.ack_file))
        for g, reason in ack_hits:
            print("  round %s: %s" % (g["round"], reason))
        for n, reason in seq_ack_hits:
            print("  round %s (sequence gap): %s" % (n, reason))
        for n, reason in uncommitted_ack_hits:
            print("  round %s (recorded but uncommitted): %s" % (n, reason))

    if esc_ack:
        print("check_round_recorded: %d known-escalated tracked-file diff(s) "
              "— already adjudicated, deliberately left uncommitted, content "
              "UNCHANGED since the escalation was pinned. Acknowledged, not "
              "counted as a gap (registry %s; the pin expires automatically "
              "if the file or its base moves):"
              % (len(esc_ack), args.escalated_diffs_file))
        for e in esc_ack:
            carried = ""
            if latest_round is not None and isinstance(
                    e.get("escalated_round"), int):
                carried = " carried %d round(s)," % (
                    latest_round - e["escalated_round"] + 1)
            print("  %s %s — escalated round %s,%s pinned %s: %s" % (
                e["code"], e["path"], e["escalated_round"], carried,
                (e["recorded_worktree_blob"] or "?")[:12],
                _first_sentence(e["reason"])))

    if esc_changed:
        print("check_round_recorded: %d known-escalated tracked-file diff(s) "
              "whose ACKNOWLEDGEMENT NO LONGER HOLDS — %s pins an exact diff "
              "by blob hash and this is not that diff any more. A third party "
              "editing a tracked file again is precisely the event the pin "
              "exists to surface: re-inspect, then either re-pin or resolve. "
              "NOT suppressed:" % (len(esc_changed), args.escalated_diffs_file))
        for e in esc_changed:
            print("  %s %s — escalated round %s: %s" % (
                e["code"], e["path"], e["escalated_round"], e["detail"]))

    if esc_resolved:
        print("check_round_recorded: %d escalation registry entr(ies) in %s "
              "match nothing in the working tree — the diff was committed, "
              "reverted, or the file deleted. A dead acknowledgement "
              "suppresses nothing and reads as coverage: delete the entry:"
              % (len(esc_resolved), args.escalated_diffs_file))
        for e in esc_resolved:
            print("  %s — escalated round %s: %s" % (
                e["path"], e["escalated_round"], e["detail"]))

    if seq_unacked:
        print("check_round_recorded: %d round-number sequence gap(s) in "
              "driver.log itself — a round number was consumed but never "
              "logged even a start/status line (a different shape than "
              "the research-state.md checks below; see "
              "missing_round_numbers docstring): %s"
              % (len(seq_unacked), ", ".join(str(n) for n in seq_unacked)))

    if uncommitted_unacked:
        print("check_round_recorded: %d round(s) have a research-state.md "
              "entry AND a knowledge file (so nothing else here flags them) "
              "but never actually landed in git — see "
              "recorded_but_uncommitted_rounds docstring: %s"
              % (len(uncommitted_unacked),
                 ", ".join(str(n) for n in uncommitted_unacked)))

    if dirty_paths:
        print("check_round_recorded: working tree has %d uncommitted, "
              "unattributed change(s) RIGHT NOW — the automated form of "
              "round 283's `git_committed`-coverage gap: a commit whose "
              "subject names round N is not proof round N's ENTIRE diff "
              "landed. Inspect and attribute each path (a real leftover "
              "diff needs `git add`+`git commit`; a file a separate system "
              "permanently leaves behind belongs in --standing-dirty-file "
              "[%s] instead):" % (len(dirty_paths), args.standing_dirty_file))
        for code, path in dirty_paths:
            print("  %s %s" % (code, path))

    if (not gaps and not seq_unacked and not uncommitted_unacked
            and not dirty_paths and not esc_changed and not esc_resolved):
        n_ack = len(ack_hits) + len(seq_ack_hits) + len(uncommitted_ack_hits)
        bits = []
        if n_ack:
            bits.append("%d pre-acknowledged, see %s" % (n_ack, args.ack_file))
        if esc_ack:
            bits.append("%d acknowledged escalation(s), see %s"
                         % (len(esc_ack), args.escalated_diffs_file))
        suffix = (" (%s)" % "; ".join(bits)) if bits else ""
        print("check_round_recorded: every driver-log round has a "
              "research-state.md entry (0 gaps)%s" % suffix)
        return 0

    if not gaps:
        return 1

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

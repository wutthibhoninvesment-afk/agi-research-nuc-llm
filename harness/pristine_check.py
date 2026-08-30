"""Does this repo pass its own tests from GIT ALONE? (round 355, harness A)

Why this exists
---------------
Every green test result this program has ever recorded was measured in ONE
tree: the live working directory on this host. That tree is not the repo.
It also contains untracked files — some written by a wholly separate
autonomous system that shares this checkout (the Hermes gateway, see
`project_hermes_gateway_shares_the_repo`), some gitignored local state — and
a test is free to read any of them without saying so.

Round 355 found a live instance. `languages/whence/tests/test_lexer_guest_
parity.py` (round 350) builds its corpus with `glob.glob(examples/*.lang)`
and guards it with `assert len(paths) >= 20`. In the working tree that
directory holds 30 files, of which git tracks 16 — the other 14 belong to
the gateway. Checked out clean at the same commit, the fast tier is
`1 failed, 1191 passed` and the slow tier fails too (`assert 16 >= 26`).
**A fresh clone of this repo failed its own suite, and had for five rounds,
because nobody had ever run it anywhere but here.**

The fix for that one test was already written down IN THIS REPO, in this
track, before the bug existed: `harness/swe/fuzz.py::list_example_files`
uses `git ls-files` for exactly this reason and says so in its docstring.
That is the point of this module. A rule that lives only in one function's
docstring gets re-broken by the next round that scans the same directory;
the differential below is that rule made mechanical, and it covers the whole
class rather than the one instance.

What it does
------------
Runs a suite twice — once in the live working tree, once in a `git worktree`
checked out at a ref — and reports the tests that fail ONLY in the pristine
tree. `git worktree add --detach` materialises exactly the tracked content
of that ref and nothing else, which is what a fresh clone gets, so a
pristine-only failure is a dependency on something git does not carry.

Fail-closed rules, all four load-bearing (cf. `swe/slowtier.py`'s three):
  1. **A dirty working tree invalidates the comparison, it does not annotate
     it.** If the tree differs from the ref in any file git tracks, the two
     runs differ for two reasons at once and no pristine-only failure can be
     attributed. The verdict is `dirty_worktree`, never `clean`.
  2. **A suite that fails in BOTH trees is not evidence about this class.**
     It is a plain broken test and is reported separately (`both_failed`),
     because calling it a git-reproducibility defect would be a false alarm,
     and a checker that cries wolf gets ignored (round 339).
  3. **A run that did not complete produces no verdict.** A timeout or a
     non-pytest exit reports `inconclusive` and never `clean`; absence of
     evidence is recorded as absence of evidence (slowtier's rule 1).
  4. **The worktree is always removed, including on exception**, and its
     path is recorded. Round 341/352's rule: this program's recurring
     failure mode is leaving something running/allocated that nobody reads.

Everything here is offline-testable: `run_suite` and every git call take an
injectable `runner`, so no test in `test_pristine_check.py` shells out to
pytest or spends a worktree.
"""
import argparse
import calendar
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
DEFAULT_LEDGER = os.path.join(REPO_ROOT, "state", "pristine-check-ledger.jsonl")

#: Named suites this repo actually runs as its health check. `cwd` is
#: repo-relative so the same entry addresses both trees; `argv` is passed to
#: `python3 -m pytest`. `-c pytest.ini` on the whence suite is round 349's
#: routing (an untracked gateway `pyproject.toml` sits in that rootdir and
#: pytest would otherwise parse it) — and note it is ALSO the reason the
#: whence suite runs at all in a pristine tree, where that file is absent.
SUITES = {
    "harness-fast": {
        "cwd": ".",
        "argv": ["-q", "-m", "not swe_slow", "harness/tests/"],
        "note": "what run_tests_fast.sh runs; the driver's per-round signal",
    },
    "whence-fast": {
        "cwd": "languages/whence",
        "argv": ["-c", "pytest.ini", "-q", "-m", "not whence_slow", "tests/"],
        "note": "the language suite's fast tier",
    },
    "whence-slow": {
        "cwd": "languages/whence",
        "argv": ["-c", "pytest.ini", "-q", "-m", "whence_slow", "tests/"],
        "note": "the language suite's slow tier (minutes)",
    },
}

_FAILED_RE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.M)
_COUNT_RE = re.compile(r"(\d+) (passed|failed|error|errors|deselected|skipped)")


# --------------------------------------------------------------------------
# process plumbing
# --------------------------------------------------------------------------

def _default_runner(argv, cwd=None, timeout=None):
    """Run `argv`, returning (returncode, stdout+stderr).

    Merged streams on purpose: pytest writes its summary to stdout but a
    collection crash lands on stderr, and a checker that silently dropped
    the crash would report `inconclusive` with nothing to read.
    """
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + (e.stderr or "")
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        return None, out
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _git(args, cwd=REPO_ROOT, runner=None, timeout=30):
    runner = runner or _default_runner
    return runner(["git"] + list(args), cwd=cwd, timeout=timeout)


# --------------------------------------------------------------------------
# pytest output
# --------------------------------------------------------------------------

def parse_pytest_output(text):
    """Extract failing node ids and the summary counts from pytest `-q`.

    Node ids come from the `short test summary info` block's `FAILED`/`ERROR`
    lines, which `-q` prints by default. Ids are normalised to forward
    slashes and stripped of any leading `./` so the same test compares equal
    across two trees rooted at different absolute paths.

    `completed` is False when no count line was found at all — a segfault, a
    collection error that aborted the run, or output truncated by a timeout.
    Rule 3 turns that into `inconclusive` rather than a verdict.
    """
    failures = set()
    for m in _FAILED_RE.finditer(text):
        nid = m.group(1).replace(os.sep, "/")
        if nid.startswith("./"):
            nid = nid[2:]
        # `FAILED a.py::t - AssertionError` — the id is already token 1, but a
        # bare `ERROR` line can carry a directory. Keep whatever it named.
        failures.add(nid)
    counts = {}
    for m in _COUNT_RE.finditer(text):
        key = "error" if m.group(2).startswith("error") else m.group(2)
        counts[key] = counts.get(key, 0) + int(m.group(1))
    return {
        "failures": sorted(failures),
        "counts": counts,
        "completed": bool(counts),
    }


def run_suite(name, root, runner=None, timeout_s=1800, python=None):
    """Run one named suite inside the checkout `root`. Never raises."""
    if name not in SUITES:
        raise KeyError("unknown suite %r (known: %s)"
                       % (name, ", ".join(sorted(SUITES))))
    spec = SUITES[name]
    cwd = os.path.normpath(os.path.join(root, spec["cwd"]))
    argv = [python or sys.executable, "-m", "pytest"] + list(spec["argv"])
    t0 = time.time()
    rc, out = (runner or _default_runner)(argv, cwd=cwd, timeout=timeout_s)
    parsed = parse_pytest_output(out)
    parsed.update({
        "suite": name,
        "root": root,
        "returncode": rc,
        "timed_out": rc is None,
        "duration_s": round(time.time() - t0, 1),
        "tail": "\n".join(out.splitlines()[-25:]),
    })
    if rc is None:
        parsed["completed"] = False
    return parsed


# --------------------------------------------------------------------------
# the pristine tree
# --------------------------------------------------------------------------

class PristineWorktree(object):
    """`git worktree add --detach <path> <ref>`, removed on the way out.

    A worktree, not a clone: it shares `.git`, so it costs one checkout of
    tracked content and `git ls-files` works inside it — which matters,
    because the fix this checker recommends is *use git to enumerate*, and a
    test doing so must keep working in the tree the checker builds.
    """

    def __init__(self, ref="HEAD", path=None, runner=None, repo=REPO_ROOT):
        self.ref = ref
        self.repo = repo
        self.runner = runner
        self.path = path or os.path.join(
            "/tmp", "pristine-check-%d-%d" % (os.getpid(), int(time.time())))
        self.created = False

    def __enter__(self):
        rc, out = _git(["worktree", "add", "--detach", self.path, self.ref],
                       cwd=self.repo, runner=self.runner, timeout=300)
        if rc != 0:
            raise RuntimeError("git worktree add failed (rc=%s): %s"
                               % (rc, out.strip()[-500:]))
        self.created = True
        return self

    def __exit__(self, *exc):
        # Rule 4. `--force` because a suite may have written scratch files
        # into the tree, and refusing to clean up a dirty worktree would
        # leave exactly the orphan this rule exists to prevent.
        if self.created:
            _git(["worktree", "remove", "--force", self.path],
                 cwd=self.repo, runner=self.runner, timeout=120)
            self.created = False
        return False


# --------------------------------------------------------------------------
# what the two trees differ by
# --------------------------------------------------------------------------

def worktree_dirt(repo=REPO_ROOT, ref="HEAD", runner=None):
    """Classify how the live tree differs from `ref`.

    Three buckets, because they mean three different things:
      `tracked_modified` — a real uncommitted diff. Rule 1: any entry here
          makes a differential uninterpretable, because a pristine-only
          failure could be an uncommitted FIX rather than a missing file.
      `untracked`        — present here, absent from a fresh clone. This is
          the bucket that CAUSES pristine-only failures.
      `ignored`          — also absent from a fresh clone, but deliberately
          so. A dependency on one of these is a different (and usually
          legitimate) class: local state, venvs, generated logs.
    """
    rc, out = _git(["status", "--porcelain=1", "--untracked-files=all",
                    "--ignored=matching"], cwd=repo, runner=runner)
    if rc != 0:
        return {"tracked_modified": [], "untracked": [], "ignored": [],
                "ok": False}
    tracked, untracked, ignored = [], [], []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:].strip().strip('"')
        if code == "??":
            untracked.append(path)
        elif code == "!!":
            ignored.append(path)
        else:
            tracked.append(path)
    return {"tracked_modified": sorted(tracked),
            "untracked": sorted(untracked),
            "ignored": sorted(ignored),
            "ok": True}


def resolve_ref(ref="HEAD", repo=REPO_ROOT, runner=None):
    """The commit `ref` names right now, or None. Never raises."""
    rc, out = _git(["rev-parse", ref], cwd=repo, runner=runner)
    if rc != 0:
        return None
    out = out.strip().splitlines()
    return out[0] if out else None


def standing_dirty(path=None):
    """Paths a separate system permanently leaves dirty (round 291's registry).

    Reused rather than re-derived: `state/known-standing-dirty-paths.json` is
    the record-gap check's allowlist and already carries the evidence bar for
    adding an entry. A file on it is still ABSENT from a pristine tree — the
    allowlist excuses it from `git status`, not from a fresh clone — so it
    stays in the `untracked` bucket here. It is loaded only to suppress rule
    1: `state/round_counter` is ` M` mid-round in every round by design, and
    letting that alone veto every differential would make this checker
    unrunnable from inside the driver it is meant to serve.
    """
    path = path or os.path.join(REPO_ROOT, "state",
                                "known-standing-dirty-paths.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return set(json.load(fh).get("paths", []))
    except (OSError, ValueError):
        return set()


def escalation_allowed_dirty(dirt, repo=REPO_ROOT, registry_path=None):
    """Tracked-modified paths rule 1 may waive because a round already
    ADJUDICATED that exact diff and the registry declares it suite-neutral.

    Round 373. Before this, the one standing instance —
    `languages/whence/SECURITY.md`, a tracked file the Hermes gateway
    rewrote, checked and escalated to the operator by round 349 — had to be
    waived by a hand-typed `--allow-dirty` at every single invocation, which
    is why the recorded ledger entry reads "rule 1 waived by hand". That
    made the same adjudication a hand-maintained fact in a THIRD place
    (round 349's prose, this flag, and the record-gap checker's own output).

    Two conditions, both required, and neither is "it's on a list":

    - the acknowledgement in `state/known-escalated-diffs.json` still HOLDS,
      i.e. `classify_escalated_diffs` says the diff is content-pinned to
      what the adjudicating round saw. Edit the file again and the waiver
      disappears with the pin.
    - the entry declares `"suite_neutral": true`. Rule 1 asks whether the
      dirty file could have changed a suite's outcome; being escalated says
      nothing about that. A `.md` nothing imports is suite-neutral; an
      escalated `.py` would not be, and must keep blocking.

    Degrades to an empty set when the skill tree is absent (a promoted
    `~/.hermes/skills/` copy per CURRICULUM.md's endgame has no
    `check_round_recorded.py`), which is the same never-block convention
    `standing_dirty` uses for a missing registry."""
    scripts = os.path.join(REPO_ROOT, "skills", "session-inheritance-audit",
                            "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        import check_round_recorded as crr
    except ImportError:
        return set()
    registry_path = registry_path or os.path.join(
        REPO_ROOT, "state", "known-escalated-diffs.json")
    registry = crr.load_escalated_diffs(registry_path)
    if not registry:
        return set()
    # Classify against the SAME dirt snapshot rule 1 is being applied to,
    # not a second `git status` — otherwise the waiver could be computed
    # from a tree that has moved since `dirt` was taken.
    status = ([(" M", p) for p in dirt.get("tracked_modified", [])]
              + [("??", p) for p in dirt.get("untracked", [])])
    rows = crr.classify_escalated_diffs(registry, status, repo)
    return {r["path"] for r in rows
            if r["state"] == crr.ESCALATION_ACKNOWLEDGED
            and registry.get(r["path"], {}).get("suite_neutral") is True}


def blocking_dirt(dirt, allow=None):
    """The `tracked_modified` entries rule 1 actually blocks on."""
    allow = standing_dirty() if allow is None else set(allow)
    return [p for p in dirt.get("tracked_modified", []) if p not in allow]


# --------------------------------------------------------------------------
# the differential
# --------------------------------------------------------------------------

def compare(live, pristine):
    """Verdict for one suite from its two runs.

    `pristine_only` is the finding: green here, red from git alone.
    `live_only` is its mirror (red here, green from git alone) and means an
    untracked file is BREAKING a test — rarer, but the same class and just
    as invisible, so it is reported rather than dropped.
    """
    if not live.get("completed") or not pristine.get("completed"):
        verdict = "inconclusive"                       # rule 3
    else:
        lf, pf = set(live["failures"]), set(pristine["failures"])
        if pf - lf:
            verdict = "git_incomplete"
        elif lf - pf:
            verdict = "untracked_breaks_test"
        elif lf:
            verdict = "both_failed"                    # rule 2
        else:
            verdict = "clean"
    lf, pf = set(live.get("failures", [])), set(pristine.get("failures", []))
    return {
        "suite": live.get("suite") or pristine.get("suite"),
        "verdict": verdict,
        "pristine_only": sorted(pf - lf),
        "live_only": sorted(lf - pf),
        "both": sorted(lf & pf),
        "live_counts": live.get("counts", {}),
        "pristine_counts": pristine.get("counts", {}),
        "live_completed": bool(live.get("completed")),
        "pristine_completed": bool(pristine.get("completed")),
        "duration_s": round(live.get("duration_s", 0)
                            + pristine.get("duration_s", 0), 1),
    }


def differential(suites, ref="HEAD", repo=REPO_ROOT, runner=None,
                 timeout_s=1800, worktree_path=None, dirt=None,
                 allow_dirty=(), escalation_allow=None):
    """Run each suite in both trees and return one record for the whole check.

    Rule 1 is enforced HERE, before any worktree is spent: a blocking dirty
    tree short-circuits to a `dirty_worktree` record with the offending
    paths, because running twenty minutes of tests to produce an
    uninterpretable answer is worse than not running them.

    `allow_dirty` is the escape hatch, and it is deliberately per-path and
    recorded rather than a boolean `--force`. Rule 1 asks whether the dirty
    file could have changed a suite's outcome; that is answerable for a
    named file and unanswerable for "the tree". Every allowance lands in the
    record as `allowed_dirty`, so a reader of the ledger can see the
    comparison was not against a clean tree and check the reasoning again.
    """
    dirt = worktree_dirt(repo=repo, ref=ref, runner=runner) if dirt is None else dirt
    if escalation_allow is None:
        escalation_allow = escalation_allowed_dirty(dirt, repo=repo)
    escalation_allow = set(escalation_allow)
    allow = standing_dirty() | escalation_allow | set(allow_dirty)
    blocking = blocking_dirt(dirt, allow=allow)
    record = {
        "ref": ref,
        # ...and what it RESOLVED to. `slowtier`'s rule 2 in miniature: a
        # stored `"ref": "HEAD"` is a moving target, so a ledger entry that
        # kept only the name would claim a verdict about whatever HEAD is
        # when you read it. `null` if the rev-parse failed — never a guess.
        "resolved": resolve_ref(ref, repo=repo, runner=runner),
        "suites": list(suites),
        "untracked_count": len(dirt.get("untracked", [])),
        "blocking_dirty": blocking,
        "allowed_dirty": sorted(
            p for p in dirt.get("tracked_modified", []) if p in set(allow_dirty)),
        # Recorded SEPARATELY from `allowed_dirty` on purpose: a reader of
        # the ledger must be able to tell a hand-typed waiver (a human
        # judgement made at run time, unverifiable afterwards) from a
        # content-pinned one (re-checkable against the registry at any
        # later date). Collapsing them would lose exactly the property the
        # registry was built to add.
        "escalation_allowed_dirty": sorted(
            p for p in dirt.get("tracked_modified", []) if p in escalation_allow),
        "results": [],
    }
    if blocking:
        record["verdict"] = "dirty_worktree"
        return record
    if not dirt.get("ok", True):
        record["verdict"] = "inconclusive"
        record["error"] = "git status failed"
        return record

    try:
        with PristineWorktree(ref=ref, path=worktree_path, runner=runner,
                              repo=repo) as wt:
            record["worktree"] = wt.path
            for name in suites:
                live = run_suite(name, repo, runner=runner,
                                 timeout_s=timeout_s)
                pris = run_suite(name, wt.path, runner=runner,
                                 timeout_s=timeout_s)
                record["results"].append(compare(live, pris))
                record["results"][-1]["pristine_tail"] = pris.get("tail", "")
    except RuntimeError as e:
        # Rule 3 again: a worktree we could not create (a ref that does not
        # exist, a stale registration, a full disk) yields NO verdict. The
        # tempting alternative — fall back to comparing the tree with
        # itself — would report `clean` for a check that never ran.
        record["verdict"] = "inconclusive"
        record["error"] = str(e)
        return record

    order = ["inconclusive", "git_incomplete", "untracked_breaks_test",
             "both_failed", "clean"]
    seen = [r["verdict"] for r in record["results"]]
    record["verdict"] = next((v for v in order if v in seen), "inconclusive")
    return record


def append_ledger(record, path=None):
    path = path or DEFAULT_LEDGER
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def read_ledger(path=None):
    path = path or DEFAULT_LEDGER
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        return []
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

_EXIT = {"clean": 0, "git_incomplete": 1, "untracked_breaks_test": 1,
         "both_failed": 2, "dirty_worktree": 3, "inconclusive": 3}


def _fmt(record):
    lines = ["ref %s (%s)   verdict %s"
             % (record["ref"], (record.get("resolved") or "unresolved")[:12],
                record["verdict"])]
    if record["verdict"] == "dirty_worktree":
        lines.append("  the live tree differs from %s in %d tracked file(s);"
                     % (record["ref"], len(record["blocking_dirty"])))
        lines.append("  a differential against it cannot attribute anything."
                     "  Commit or stash first:")
        for p in record["blocking_dirty"][:20]:
            lines.append("    M %s" % p)
        return "\n".join(lines)
    lines.append("  %d untracked path(s) exist here and in no fresh clone"
                 % record["untracked_count"])
    for p in record.get("allowed_dirty", []):
        lines.append("  allowed-dirty (rule 1 waived by hand): %s" % p)
    for p in record.get("escalation_allowed_dirty", []):
        lines.append("  allowed-dirty (escalation pin, suite-neutral): %s" % p)
    for r in record["results"]:
        lines.append("  %-14s %-22s live=%s pristine=%s  %ss"
                     % (r["suite"], r["verdict"],
                        r["live_counts"] or "-", r["pristine_counts"] or "-",
                        r["duration_s"]))
        for nid in r["pristine_only"]:
            lines.append("      GIT-INCOMPLETE  %s" % nid)
        for nid in r["live_only"]:
            lines.append("      UNTRACKED-BREAKS %s" % nid)
        for nid in r["both"]:
            lines.append("      fails in both (not this class)  %s" % nid)
    return "\n".join(lines)


def status_freshness(record, repo=REPO_ROOT, now=None, runner=None,
                     head=None):
    """The lines `status` prints ABOVE a recorded verdict (round 379).

    `check` measures; `status` re-prints something measured earlier, and
    until this round the two produced the SAME text — `ref HEAD
    (91acd9c5af97) verdict clean`, with no age and no statement about which
    tree that verdict was about. Two rounds read the second as the first:

    - `harness/run_tests_fast.sh` echoes `status` after every fast run, so
      `driver_health` quoted a round-373 row into `driver.log` as rounds
      374-378's own health-check result (fixed in `classify_health_log`);
    - round 374 concluded from that line that the driver runs a pristine
      whence-slow check every round. It runs none.

    A record whose `resolved` commit is not HEAD is not about this tree, and
    that is a fact this function can CHECK rather than caption. `head` is
    injectable so the test does not need a repo; `now` likewise.
    """
    out = []
    when = record.get("recorded_at")
    now = time.time() if now is None else now
    age = ""
    if when:
        try:
            # `timegm`, not `mktime` minus `time.timezone`: the stamp is
            # UTC (`check` writes it with `time.gmtime`), and mktime would
            # read it as local — right on this UTC box, hours wrong on any
            # other, which is the very class of defect this line exists to
            # expose.
            stamp = calendar.timegm(time.strptime(when, "%Y-%m-%dT%H:%M:%SZ"))
            hours = (now - stamp) / 3600.0
            age = " (%.1f h ago)" % hours if hours < 48 else \
                  " (%.1f days ago)" % (hours / 24.0)
        except ValueError:
            age = ""
    out.append("RECORDED %s%s — a stored verdict, not a run just now"
               % (when or "at an unrecorded time", age))
    head = resolve_ref("HEAD", repo=repo, runner=runner) if head is None else head
    was = record.get("resolved")
    if head and was and head != was:
        out.append("  HEAD HAS MOVED SINCE: recorded at %s, now %s — this "
                   "verdict is NOT about the current tree" % (was[:12], head[:12]))
    elif head and was:
        out.append("  HEAD is still %s — the tree this verdict was measured "
                   "at (tracked files only; untracked and uncommitted work "
                   "is not covered)" % was[:12])
    else:
        out.append("  commit unknown — cannot say which tree this verdict "
                   "is about")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")

    c = sub.add_parser("check", help="run the pristine differential")
    c.add_argument("--suite", action="append", dest="suites",
                   choices=sorted(SUITES), help="repeatable; default two fast")
    c.add_argument("--ref", default="HEAD")
    c.add_argument("--timeout-s", type=int, default=1800)
    c.add_argument("--ledger", default=None)
    c.add_argument("--no-record", action="store_true")
    c.add_argument("--json", action="store_true")
    c.add_argument("--allow-dirty", action="append", dest="allow_dirty",
                   default=[], metavar="PATH",
                   help="excuse ONE named tracked-modified path from rule 1, "
                        "after checking it cannot affect the suites. "
                        "Recorded in the ledger as allowed_dirty.")

    sub.add_parser("suites", help="list known suites")

    s = sub.add_parser("status", help="last recorded check")
    s.add_argument("--ledger", default=None)

    d = sub.add_parser("dirt", help="classify how this tree differs from a ref")
    d.add_argument("--ref", default="HEAD")

    args = ap.parse_args(argv)

    if args.cmd == "suites":
        for k in sorted(SUITES):
            print("%-14s cd %-18s pytest %s\n               %s"
                  % (k, SUITES[k]["cwd"], " ".join(SUITES[k]["argv"]),
                     SUITES[k]["note"]))
        return 0

    if args.cmd == "dirt":
        dirt = worktree_dirt(ref=args.ref)
        # Same allow set `differential` will use, or this subcommand reports
        # a path as BLOCKING that `check` is about to waive — a preview that
        # disagrees with the thing it previews is worse than no preview.
        pinned = escalation_allowed_dirty(dirt)
        blocking = blocking_dirt(dirt, allow=standing_dirty() | pinned)
        print("tracked-modified %d (blocking %d)  untracked %d  ignored %d"
              % (len(dirt["tracked_modified"]), len(blocking),
                 len(dirt["untracked"]), len(dirt["ignored"])))
        for p in sorted(pinned & set(dirt["tracked_modified"])):
            print("  pinned-waiver (escalation, suite-neutral)  %s" % p)
        for p in blocking:
            print("  BLOCKING  %s" % p)
        return 0 if not blocking else 3

    if args.cmd == "status":
        recs = read_ledger(args.ledger)
        if not recs:
            print("no recorded check (absence of evidence, not a pass)")
            return 3
        for line in status_freshness(recs[-1]):
            print(line)
        print(_fmt(recs[-1]))
        return _EXIT.get(recs[-1]["verdict"], 3)

    if args.cmd != "check":
        ap.print_help()
        return 2

    suites = args.suites or ["harness-fast", "whence-fast"]
    rec = differential(suites, ref=args.ref, timeout_s=args.timeout_s,
                       allow_dirty=args.allow_dirty)
    rec["recorded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not args.no_record:
        rec["ledger"] = append_ledger(rec, args.ledger)
    print(json.dumps(rec, indent=2, sort_keys=True) if args.json else _fmt(rec))
    return _EXIT.get(rec["verdict"], 3)


if __name__ == "__main__":
    sys.exit(main())

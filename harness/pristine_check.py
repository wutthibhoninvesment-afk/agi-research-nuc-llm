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
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
DEFAULT_LEDGER = os.path.join(REPO_ROOT, "state", "pristine-check-ledger.jsonl")
#: Round 409. Kept SEPARATE from the differential's ledger on purpose: they
#: answer different questions and share a formatter otherwise. `status` reads
#: the last differential; a baseline landing in that file would let "the
#: pristine tree is green" be read as "the two trees agree", which is the one
#: inference this module exists to refuse.
BASELINE_LEDGER = os.path.join(REPO_ROOT, "state", "baseline-ledger.jsonl")
#: Round 427. Acknowledged pristine-only SKIPS -- see `compare_skips`. Kept
#: in `state/` beside the other two acknowledgement registries and NOT merged
#: with either: `known-standing-dirty-paths.json` models untracked files a
#: third party leaves behind, `known-escalated-diffs.json` models a tracked
#: diff a round adjudicated, and this one models a TEST that stops being
#: evidence in a fresh clone. Same content-pin discipline, different subject.
SKIP_ACK_REGISTRY = os.path.join(REPO_ROOT, "state", "known-pristine-skips.json")

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


# --------------------------------------------------------------------------
# skips: the evidence that evaporates without ever going red
# --------------------------------------------------------------------------
#
# Round 427. Everything above this line compares the two trees by FAILURE
# SET. That is a real class and it is not the only one. A test whose fixture
# git does not carry has two ways to react to a pristine checkout:
#
#   * fail -- `compare` sees it, `git_incomplete`, exit 1. Round 355's class.
#   * skip -- `compare` sees NOTHING. `pf - lf` is empty, `lf - pf` is empty,
#     `lf` is empty, verdict `clean`, exit 0, in BOTH trees.
#
# The second is strictly more dangerous than the first, because a defended
# test looks exactly like a passing one at the exit code and at the count
# line, and the count line is what every round quotes. Round 426 hit it by
# hand: its `HEAD` baseline came back `2157 passed, 14 skipped` where the
# live tier reports `3 skipped`, so ELEVEN tests provided no evidence and
# the baseline still exited 0. Round 425 found the same shape one tree over
# (`test_v37.py::test_the_host_is_byte_unchanged_by_this_decision` goes
# `passed -> skipped` inside every mutation sandbox, both sides exit 0) and
# asked for the acknowledgement mechanism this section is.
#
# Two decisions worth keeping:
#
# 1. **The key is junit's `(classname, name)`, never a line number.**
#    `pytest -rs` -- the flag round 426's next-steps item names -- prints
#    `SKIPPED [1] tests/test_x.py:12: reason`, keyed by FILE AND LINE. A
#    differential keyed on that reports a phantom evaporation every time
#    someone inserts an import above the test. `--junitxml` carries the node
#    identity instead, which is what the comparison actually means.
# 2. **Node ids are for READING, keys are for DECIDING.** `junit_node_id`
#    reconstructs `tests/test_x.py::TestC::test_y` from the dotted
#    `classname` by a heuristic (a trailing capitalised component is a
#    class), because pytest's junit writer emits no `file` attribute here.
#    A heuristic must not be able to change a verdict, so it does not: every
#    comparison and every acknowledgement is keyed on the raw attribute pair,
#    and a wrong reconstruction can only misprint a line.

#: A junit `classname` component that is a CLASS rather than a package or
#: module. Python's own convention (PEP 8 CapWords for classes, lowercase
#: for modules) is what makes this decidable at all; this repo's test tree
#: has no capitalised directory or module name, which
#: `test_junit_node_ids_round_trip_against_this_repos_own_test_tree` checks
#: against the real tree rather than asserting.
_JUNIT_CLASS_RE = re.compile(r"^[A-Z]")

#: junit records an xfail as `<skipped type="pytest.xfail">`. An xfail is a
#: test that ran and behaved as declared -- it is not lost evidence, and
#: counting it here would put a permanent false positive in every report.
_XFAIL_TYPE = "pytest.xfail"


def skip_key(classname, name):
    """The identity a skip is compared and acknowledged by.

    Deliberately the RAW junit attribute pair and not the reconstructed node
    id: see decision 2 above. Stable across trees, across line edits, and
    across any bug in `junit_node_id`.
    """
    return "%s::%s" % (classname or "", name or "")


def junit_node_id(classname, name):
    """A readable pytest node id rebuilt from a junit `testcase`.

    `tests.test_v37` + `test_foo` -> `tests/test_v37.py::test_foo`;
    `tests.test_v37.TestC` + `test_foo` -> `tests/test_v37.py::TestC::test_foo`.
    Capitalised trailing components are peeled off as classes, at most down
    to a single remaining component, so a module is never consumed. A
    classname with no components at all yields the bare test name rather
    than a fabricated path.
    """
    parts = [x for x in (classname or "").split(".") if x]
    classes = []
    while len(parts) > 1 and _JUNIT_CLASS_RE.match(parts[-1]):
        classes.insert(0, parts.pop())
    if not parts:
        return name or ""
    return "::".join(["/".join(parts) + ".py"] + classes
                     + ([name] if name else []))


def parse_junit(path):
    """Per-node outcomes from a `--junitxml` report. Never raises.

    Returns `ok=False` with an `error` for a missing, empty or malformed
    file, and callers must treat that as ABSENCE OF EVIDENCE rather than as
    "no skips" -- rule 3 applied to this class. Every fake-runner test in
    this repo produces exactly that case, which is why the default has to be
    right.
    """
    rec = {"ok": False, "path": path, "error": None,
           "statuses": {}, "skips": []}
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError, ValueError) as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        return rec
    for tc in tree.iter("testcase"):
        cn, nm = tc.get("classname"), tc.get("name")
        key = skip_key(cn, nm)
        skipped = tc.find("skipped")
        if skipped is not None and skipped.get("type") != _XFAIL_TYPE:
            rec["statuses"][key] = "skipped"
            rec["skips"].append({
                "key": key,
                "nid": junit_node_id(cn, nm),
                "reason": " ".join((skipped.get("message") or "").split()),
            })
        elif skipped is not None:
            rec["statuses"][key] = "xfailed"
        elif tc.find("failure") is not None:
            rec["statuses"][key] = "failed"
        elif tc.find("error") is not None:
            rec["statuses"][key] = "error"
        else:
            rec["statuses"][key] = "passed"
    rec["ok"] = True
    return rec


def load_skip_acks(path=None):
    """Acknowledged pristine-only skips, as a list of entries. Never raises.

    Missing or corrupt registry reads as EMPTY, i.e. acknowledges nothing,
    which is the fail-loud direction: the worst a broken registry can do is
    make a known evaporation go red again. The opposite default -- suppress
    on read failure -- would let deleting the file silence the checker.
    """
    try:
        with open(path or SKIP_ACK_REGISTRY, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    out = []
    for e in (data.get("acknowledged") or []):
        if isinstance(e, dict) and e.get("suite") and e.get("key"):
            out.append(e)
    return out


#: Why an acknowledgement did not apply. Kept as constants because all three
#: are printed and two of them are LOUDER than an unacknowledged evaporation.
ACK_HOLDS = "holds"
ACK_PIN_EXPIRED = "pin_expired"
ACK_DEAD = "dead"


def compare_skips(live, pristine, suite=None, acks=None):
    """The `passed -> skipped` differential for one suite.

    `live` and `pristine` are `parse_junit` records. The finding is a test
    the PRISTINE tree skipped and the LIVE tree actually ran: evidence this
    repo believes it has and a fresh clone does not.

    Four buckets, and the reason there are four rather than two:

      `unacknowledged` -- nobody has adjudicated this. Sets the verdict.
      `acknowledged`   -- a round inspected it, wrote down why, and pinned
          the exact skip REASON. Printed every time (an acknowledgement that
          suppresses invisibly reads as coverage) but does not set a verdict.
      `pin_expired`    -- the (suite, key) is acknowledged but the reason
          text has CHANGED, so the test is now skipped for a reason nobody
          adjudicated. Reported LOUDER than an unacknowledged one and it
          sets the verdict, exactly as `known-escalated-diffs.json` treats a
          moved blob. This is what stops an acknowledgement from decaying
          into a permanent blanket over a node id.
      `dead`           -- an acknowledgement matching no evaporation in a
          suite that RAN. Suppresses nothing, so it must be deleted; the
          same rule the escalated-diff registry states about itself.

    `condensed` is the mirror (`skipped live, passed pristine`): an
    untracked file is CAUSING a skip here. Rare, reported, never a verdict --
    the live tree having less evidence than git is not a git defect.

    Rule 3: if either junit report is unavailable the answer is
    `evidence: "unavailable"` and NO bucket is populated. A run that produced
    no report has not shown that nothing evaporated.
    """
    out = {"suite": suite, "evidence": "unavailable", "error": None,
           "live_skips": None, "pristine_skips": None,
           "unacknowledged": [], "acknowledged": [], "pin_expired": [],
           "dead_acknowledgements": [], "condensed": []}
    live = live or {}
    pristine = pristine or {}
    if not live.get("ok") or not pristine.get("ok"):
        out["error"] = (pristine.get("error") if not pristine.get("ok")
                        else live.get("error")) or "no junit report"
        return out
    out["evidence"] = "available"
    lstat = live.get("statuses") or {}
    pstat = pristine.get("statuses") or {}
    out["live_skips"] = sum(1 for v in lstat.values() if v == "skipped")
    out["pristine_skips"] = len(pristine.get("skips") or [])
    by_key = {}
    for e in (acks if acks is not None else load_skip_acks()):
        if suite is None or e.get("suite") == suite:
            by_key[e.get("key")] = e
    matched = set()
    for sk in (pristine.get("skips") or []):
        was = lstat.get(sk["key"])
        if was != "passed":
            # Skipped in both, or absent from the live run entirely (a test
            # git does not carry cannot have "evaporated" -- it was added
            # here and never existed there, which is not this class).
            continue
        row = dict(sk)
        row["live_status"] = was
        ack = by_key.get(sk["key"])
        if ack is None:
            row["ack"] = None
            out["unacknowledged"].append(row)
            continue
        matched.add(sk["key"])
        row["ack"] = {k: ack.get(k) for k in
                      ("why", "acknowledged_round", "acknowledged_utc")}
        if ack.get("reason_pin") == sk["reason"]:
            row["ack_state"] = ACK_HOLDS
            out["acknowledged"].append(row)
        else:
            row["ack_state"] = ACK_PIN_EXPIRED
            row["ack"]["reason_pin"] = ack.get("reason_pin")
            out["pin_expired"].append(row)
    for key, ack in sorted(by_key.items()):
        if key not in matched:
            out["dead_acknowledgements"].append({
                "key": key, "nid": ack.get("nid") or key,
                "why": ack.get("why"), "state": ACK_DEAD})
    for key, st in sorted(lstat.items()):
        if st == "skipped" and pstat.get(key) == "passed":
            out["condensed"].append({"key": key, "nid": key})
    return out


def _skip_verdict(block):
    """`skip_evaporation` when a suite lost evidence nobody has signed off.

    `None` when the block cannot decide -- unavailable evidence, or nothing
    but acknowledged rows -- so the caller keeps whatever the failure
    comparison said. Absence of a junit report never produces a verdict in
    either direction.
    """
    if block.get("evidence") != "available":
        return None
    if block.get("unacknowledged") or block.get("pin_expired"):
        return "skip_evaporation"
    return None


class _JunitScratch(object):
    """A /tmp directory for the two junit reports, removed on every exit.

    OUTSIDE both trees on purpose. Written into the live tree the report
    makes it dirty and rule 1 blocks the very next `check` -- round 409's
    `OWN_RECORDS` trap in a new place; written into the pristine worktree it
    would be handed to `git worktree remove` as dirt.
    """

    def __init__(self, root=None):
        self.root = root
        self._made = False

    def __enter__(self):
        if self.root is None:
            self.root = tempfile.mkdtemp(prefix="pristine-junit-")
            self._made = True
        return self

    def path(self, *parts):
        return os.path.join(self.root, "-".join(parts) + ".xml")

    def __exit__(self, *exc):
        if self._made:
            shutil.rmtree(self.root, ignore_errors=True)
            self._made = False
        return False


def run_suite(name, root, runner=None, timeout_s=1800, python=None,
              junit_path=None):
    """Run one named suite inside the checkout `root`. Never raises.

    `junit_path` (round 427) adds `--junitxml=<path>` and parses the result
    into `junit`. It DEFAULTS TO OFF so that the argv of a bare `run_suite`
    is still exactly `SUITES[name]["argv"]` -- which
    `test_run_suite_builds_the_registered_argv` asserts, and which is worth
    keeping true: the registered argv is the claim "this is what the driver
    runs", and silently appending to it would make that claim false. The
    path must lie outside both trees; `_JunitScratch` is what picks one.
    """
    if name not in SUITES:
        raise KeyError("unknown suite %r (known: %s)"
                       % (name, ", ".join(sorted(SUITES))))
    spec = SUITES[name]
    cwd = os.path.normpath(os.path.join(root, spec["cwd"]))
    argv = [python or sys.executable, "-m", "pytest"] + list(spec["argv"])
    if junit_path:
        argv.append("--junitxml=%s" % junit_path)
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
    parsed["junit"] = (parse_junit(junit_path) if junit_path
                       else {"ok": False, "path": None,
                             "error": "junit report not requested",
                             "statuses": {}, "skips": []})
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


#: This module's OWN records, repo-relative. Rule 1 asks exactly one
#: question — "could this dirty file have changed a suite's outcome?" — and
#: for these two the answer is provably no: nothing under `harness/tests/`
#: or `languages/whence/tests/` reads them, which
#: `test_no_suite_reads_the_ledgers_so_waiving_them_is_sound` re-proves by
#: grep rather than asserting.
#:
#: Round 409, found by running `baseline` and then `check`: `baseline`
#: appends to its ledger, which makes the tree dirty, which makes the very
#: next `check` short-circuit to `dirty_worktree` naming a file this module
#: just wrote. The same trap has existed for `check` against ITSELF since
#: round 355 — two `check` runs in one round, the second blocked by the
#: first's record — and was simply never reached because nobody ran it
#: twice. Waived HERE and not in `state/known-standing-dirty-paths.json`:
#: that registry's own comment sets a bar ("recurs across multiple rounds
#: with no round ever attributing or committing it") which a tracked record
#: a round DOES commit does not meet, and models untracked leftovers from a
#: separate system rather than this tool's own output.
OWN_RECORDS = frozenset([
    os.path.relpath(DEFAULT_LEDGER, REPO_ROOT).replace(os.sep, "/"),
    os.path.relpath(BASELINE_LEDGER, REPO_ROOT).replace(os.sep, "/"),
])


def blocking_dirt(dirt, allow=None):
    """The `tracked_modified` entries rule 1 actually blocks on."""
    allow = standing_dirty() if allow is None else set(allow)
    return [p for p in dirt.get("tracked_modified", []) if p not in allow]


# --------------------------------------------------------------------------
# the differential
# --------------------------------------------------------------------------

def compare(live, pristine, acks=None):
    """Verdict for one suite from its two runs.

    `pristine_only` is the finding: green here, red from git alone.
    `live_only` is its mirror (red here, green from git alone) and means an
    untracked file is BREAKING a test — rarer, but the same class and just
    as invisible, so it is reported rather than dropped.

    Round 427 adds the SILENT half of `pristine_only`. A test that reacts to
    a missing fixture by skipping rather than failing produces an empty
    `pf - lf`, an empty `lf`, and verdict `clean` — see `compare_skips`. The
    skip block is computed whenever both runs left a junit report and is
    reported either way; it can promote `clean` to `skip_evaporation`, and
    it is deliberately ranked ABOVE `untracked_breaks_test` and below
    `git_incomplete`, because it has the same CAUSE as `git_incomplete`
    (git does not carry something the test needs) and differs only in how
    loudly the test reacted. A verdict that ranked the quiet reaction below
    the noisy one would reward defending a test with `pytest.skip`.
    """
    skips = compare_skips(live.get("junit"), pristine.get("junit"),
                          suite=live.get("suite") or pristine.get("suite"),
                          acks=acks)
    if not live.get("completed") or not pristine.get("completed"):
        verdict = "inconclusive"                       # rule 3
    else:
        lf, pf = set(live["failures"]), set(pristine["failures"])
        if pf - lf:
            verdict = "git_incomplete"
        elif _skip_verdict(skips):
            verdict = "skip_evaporation"
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
        "skips": skips,
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
                 allow_dirty=(), escalation_allow=None, acks=None,
                 junit_dir=None):
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
    allow = (standing_dirty() | escalation_allow | set(allow_dirty)
             | set(OWN_RECORDS))
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

    acks = load_skip_acks() if acks is None else acks
    try:
        with PristineWorktree(ref=ref, path=worktree_path, runner=runner,
                              repo=repo) as wt, _JunitScratch(
                                  root=junit_dir) as js:
            record["worktree"] = wt.path
            record["junit_dir"] = js.root
            for name in suites:
                live = run_suite(name, repo, runner=runner,
                                 timeout_s=timeout_s,
                                 junit_path=js.path(name, "live"))
                pris = run_suite(name, wt.path, runner=runner,
                                 timeout_s=timeout_s,
                                 junit_path=js.path(name, "pristine"))
                record["results"].append(compare(live, pris, acks=acks))
                record["results"][-1]["pristine_tail"] = pris.get("tail", "")
    except RuntimeError as e:
        # Rule 3 again: a worktree we could not create (a ref that does not
        # exist, a stale registration, a full disk) yields NO verdict. The
        # tempting alternative — fall back to comparing the tree with
        # itself — would report `clean` for a check that never ran.
        record["verdict"] = "inconclusive"
        record["error"] = str(e)
        return record

    order = ["inconclusive", "git_incomplete", "skip_evaporation",
             "untracked_breaks_test", "both_failed", "clean"]
    seen = [r["verdict"] for r in record["results"]]
    record["verdict"] = next((v for v in order if v in seen), "inconclusive")
    return record


def baseline(suites, ref="HEAD", repo=REPO_ROOT, runner=None,
             timeout_s=1800, worktree_path=None, dirt=None, junit_dir=None):
    """What the named suites do in a PRISTINE checkout of `ref`. ONE tree.

    Round 409. This is the operation every round has been hand-rolling —
    `git worktree add --detach /tmp/wt-NNN HEAD; cd there; pytest ...` — and
    hand-rolling it has cost real findings twice in one round. Round 408 read
    five reds out of a hand-made worktree, four of them false (a
    `.gitignore`d corpus, fixed this round) and the fifth caused BY THE
    WORKTREE'S NAME: `/tmp/wt-408` has `/tmp/wt` as a string prefix, which
    is what this module's own test double used to tell the two trees apart.

    Why not just call `differential`? Because it refuses. Rule 1
    short-circuits on a dirty tree, correctly: its answer is a COMPARISON and
    an uncommitted edit makes the comparison uninterpretable. A baseline
    compares nothing — it asks "what does this COMMIT do", which is the
    question a round asks BEFORE it edits anything, and which a round that
    has ALREADY edited still needs answered. So dirt does not gate this; it
    is RECORDED instead, because a reader must still be able to see the live
    tree had edits when the baseline was taken.

    The three things hand-rolling gets wrong and this does not: the suites
    are NAMED (`SUITES`, so nobody runs `harness/tests/` and calls it a
    baseline for a language round), the worktree path cannot collide with
    anything, and it is removed on every exit path including a raise.
    """
    # Validated FIRST, before any git call: a mistyped suite name is a
    # caller bug and must cost nothing — not a rev-parse, and certainly not
    # a checkout of the whole tree.
    for name in suites:
        if name not in SUITES:
            raise KeyError("unknown suite %r (known: %s)"
                           % (name, ", ".join(sorted(SUITES))))
    dirt = worktree_dirt(repo=repo, ref=ref, runner=runner) if dirt is None else dirt
    record = {
        "kind": "baseline",
        "ref": ref,
        "resolved": resolve_ref(ref, repo=repo, runner=runner),
        "suites": list(suites),
        # Not a gate — a caveat. Named `live_tree_dirty` rather than reusing
        # `blocking_dirty`, so no reader can mistake it for rule 1 having run.
        "live_tree_dirty": {
            "tracked_modified": len(dirt.get("tracked_modified", [])),
            "untracked": len(dirt.get("untracked", [])),
        },
        "results": [],
    }
    try:
        with PristineWorktree(ref=ref, path=worktree_path, runner=runner,
                              repo=repo) as wt, _JunitScratch(
                                  root=junit_dir) as js:
            record["worktree"] = wt.path
            for name in suites:
                res = run_suite(name, wt.path, runner=runner,
                                timeout_s=timeout_s,
                                junit_path=js.path(name, "baseline"))
                record["results"].append({
                    "suite": name,
                    "completed": res["completed"],
                    "counts": res["counts"],
                    "failures": res["failures"],
                    "returncode": res["returncode"],
                    "timed_out": res["timed_out"],
                    "duration_s": res["duration_s"],
                    "tail": res.get("tail", ""),
                    # Rule 3 per suite, not per run: a suite that never
                    # produced a count line is `incomplete`, never `green`.
                    "verdict": ("incomplete" if not res["completed"]
                                else "red" if res["failures"]
                                     or res["counts"].get("failed")
                                     or res["counts"].get("error")
                                else "green"),
                    # Round 426's next-steps item 7, made mechanical: "any
                    # round taking a baseline this way should diff the SKIP
                    # list, not just the pass count". One tree cannot DIFF
                    # anything, so this records the list and says so; the
                    # differential is `check`. Recording it is still the
                    # load-bearing half -- round 426 had to re-run the suite
                    # by hand to find out WHICH eleven tests it had lost,
                    # because its own baseline record kept only a count.
                    "skips": (res.get("junit") or {}).get("skips") or [],
                    "skip_evidence": ("available"
                                      if (res.get("junit") or {}).get("ok")
                                      else "unavailable"),
                })
    except RuntimeError as e:
        record["verdict"] = "inconclusive"
        record["error"] = str(e)
        return record

    order = ["inconclusive", "incomplete", "red", "green"]
    seen = [r["verdict"] for r in record["results"]]
    record["verdict"] = next((v for v in order if v in seen), "inconclusive")
    return record


def _fmt_baseline(rec):
    """One block a round can paste into its knowledge file verbatim."""
    lines = ["baseline  %s (%s)  verdict=%s"
             % (rec.get("ref"), (rec.get("resolved") or "unresolved")[:12],
                rec.get("verdict"))]
    d = rec.get("live_tree_dirty") or {}
    if d.get("tracked_modified") or d.get("untracked"):
        lines.append("  NOTE: taken while the live tree had %d tracked-modified"
                     " and %d untracked path(s) — the baseline is of the"
                     " COMMIT, not of that tree."
                     % (d.get("tracked_modified", 0), d.get("untracked", 0)))
    if rec.get("error"):
        lines.append("  error: %s" % rec["error"])
    for r in rec.get("results", []):
        lines.append("  %-14s %-10s %s (%.0fs)"
                     % (r["suite"], r["verdict"],
                        ", ".join("%d %s" % (v, k) for k, v
                                  in sorted(r["counts"].items())) or "no counts",
                        r["duration_s"]))
        for f in r["failures"][:20]:
            lines.append("      FAILED %s" % f)
        if len(r["failures"]) > 20:
            lines.append("      ... and %d more" % (len(r["failures"]) - 20))
        if r.get("skip_evidence") == "unavailable":
            lines.append("      skips: NOT RECORDED (no junit report) — this"
                         " baseline cannot say what it did not run")
        else:
            sk = r.get("skips") or []
            lines.append("      skips: %d recorded — a skip is not a pass,"
                         " and `check` is what decides whether any of these"
                         " ran in the live tree" % len(sk))
            for one in sk[:20]:
                lines.append("        SKIPPED %s — %s"
                             % (one["nid"], (one.get("reason") or "")[:90]))
            if len(sk) > 20:
                lines.append("        ... and %d more" % (len(sk) - 20))
    return "\n".join(lines)


_BASELINE_EXIT = {"green": 0, "red": 1, "incomplete": 3, "inconclusive": 3}


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

_EXIT = {"clean": 0, "git_incomplete": 1, "skip_evaporation": 1,
         "untracked_breaks_test": 1,
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
        lines.extend(_fmt_skips(r.get("skips") or {}))
    return "\n".join(lines)


def _fmt_skips(block):
    """The skip half of one suite's row. Everything is printed, always.

    An acknowledged evaporation still gets a line. The registry's job is to
    keep a KNOWN loss from setting the verdict, not to hide it — the failure
    mode being avoided is the one round 349 named about allowlists, "never
    look at this again", and a silent suppression is that failure mode with
    a JSON file in front of it.
    """
    if block.get("evidence") != "available":
        return ["      skips: NOT COMPARED (%s) — this run did not show that"
                " nothing evaporated" % (block.get("error") or "no evidence")]
    out = ["      skips: live %s / pristine %s"
           % (block.get("live_skips"), block.get("pristine_skips"))]
    for r in block.get("unacknowledged", []):
        out.append("      EVAPORATED (passes here, skipped from git alone)"
                   "  %s\n          reason: %s"
                   % (r["nid"], (r.get("reason") or "")[:160]))
    for r in block.get("pin_expired", []):
        out.append("      EVAPORATED, ACKNOWLEDGEMENT EXPIRED — the reason"
                   " text changed since round %s pinned it, so this skip is"
                   " no longer the one that was adjudicated  %s\n"
                   "          now:    %s\n          pinned: %s"
                   % ((r.get("ack") or {}).get("acknowledged_round"), r["nid"],
                      (r.get("reason") or "")[:120],
                      ((r.get("ack") or {}).get("reason_pin") or "")[:120]))
    for r in block.get("acknowledged", []):
        out.append("      evaporated, acknowledged (round %s): %s"
                   % ((r.get("ack") or {}).get("acknowledged_round"), r["nid"]))
    for r in block.get("dead_acknowledgements", []):
        out.append("      DEAD ACKNOWLEDGEMENT — suppresses nothing, delete"
                   " it (an entry that covers no live case reads as"
                   " coverage): %s" % r["nid"])
    for r in block.get("condensed", []):
        out.append("      skipped HERE, runs from git alone (untracked file"
                   " is suppressing a test): %s" % r["nid"])
    return out


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

    b = sub.add_parser("baseline", help="run suites in a pristine checkout "
                                       "of a ref (one tree, no live run)")
    b.add_argument("--suite", action="append", dest="suites",
                   choices=sorted(SUITES), help="repeatable; default two fast")
    b.add_argument("--ref", default="HEAD")
    b.add_argument("--timeout-s", type=int, default=1800)
    b.add_argument("--ledger", default=None)
    b.add_argument("--no-record", action="store_true")
    b.add_argument("--json", action="store_true")

    bs = sub.add_parser("baseline-status", help="last recorded baseline")
    bs.add_argument("--ledger", default=None)

    sub.add_parser("suites", help="list known suites")

    s = sub.add_parser("status", help="last recorded check")
    s.add_argument("--ledger", default=None)

    d = sub.add_parser("dirt", help="classify how this tree differs from a ref")
    d.add_argument("--ref", default="HEAD")

    args = ap.parse_args(argv)

    if args.cmd == "baseline":
        rec = baseline(args.suites or ["harness-fast", "whence-fast"],
                       ref=args.ref, timeout_s=args.timeout_s)
        rec["recorded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if not args.no_record:
            rec["ledger"] = append_ledger(
                rec, args.ledger or BASELINE_LEDGER)
        print(json.dumps(rec, indent=2, sort_keys=True) if args.json
              else _fmt_baseline(rec))
        return _BASELINE_EXIT.get(rec["verdict"], 3)

    if args.cmd == "baseline-status":
        recs = read_ledger(args.ledger or BASELINE_LEDGER)
        if not recs:
            print("no recorded baseline (absence of evidence, not a pass)")
            return 3
        for line in status_freshness(recs[-1]):
            print(line)
        print(_fmt_baseline(recs[-1]))
        return _BASELINE_EXIT.get(recs[-1]["verdict"], 3)

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
        blocking = blocking_dirt(
            dirt, allow=standing_dirty() | pinned | set(OWN_RECORDS))
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

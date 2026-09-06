#!/usr/bin/env python3
"""readset.py — which test nodes can the diff in my working tree redden?

Round 505 (harness A).

THE GAP THIS FILLS
------------------
`harness/redattrib.py` (455/461) measured it: **83% of red episodes in this
program's retained health logs were opened by a round that could not have
seen the red by running its own track's suite.** `harness/reddebt.py` (493)
acted on that from the READER's side — it puts the currently-red nodes, with
opener and owner, into the next round's prompt. Both are downstream of the
same structural fact, stated in `run_driver.sh` and in `skills/
unrun-checker-latency/SKILL.md` as "the floor of one": the four health checks
run AFTER the round's agent process exits, so a check your own commit
reddens is invisible to you at any price.

`reddebt` does not lower that floor. It cannot: it reads logs that do not
exist yet when the opener is still running. What it does is stop the debt
compounding — round 505 was told about round 504's reds and closed them in
one round instead of the three that motivated `reddebt`.

This module is the other half, and it is the half that reaches the OPENER.
The question it answers is asked from inside the round, against the diff in
the working tree, before the commit:

    $ python3 harness/readset.py blast
    languages/whence/builtinlive.py            (added)
    languages/whence/tests/test_builtinlive.py (added)
    IMPLICATED  harness/tests/test_swe_copyparity_real_subject.py   3 node(s)
    IMPLICATED  harness/tests/test_whenceslow.py                    1 node(s)

Those are the four nodes round 504 actually reddened. Nothing round 504
could have run would have told it so.

HOW — measured, not declared
----------------------------
`harness/crosstrack-registry.json` already classifies red nodes by
`subject_scope`, and `foreign-subject` is exactly this shape ("the track that
can break it is by construction not the track that runs it"). But that
registry carries PROSE: it says a node's subject is `languages/whence`, not
WHICH paths, so no query can be run against it. Round 473-493's recurrence is
the same lesson in another key — a diagnosis written down four times with no
instrument built from it.

So the subject set here is MEASURED. A PEP 578 audit hook (`sys.addaudithook`)
records, per test node, two sets:

  * `files` — every repo path the node OPENED for reading, or imported.
  * `scans` — every repo directory the node LISTED (`os.listdir`,
    `os.scandir`, and therefore `os.walk` and `glob`).

THE TWO SETS ARE NOT REDUNDANT, and the reason is the whole design. A file
read-set answers "which node depends on a file that exists". Round 504's
defect was an ADDITION: `languages/whence/builtinlive.py` did not exist when
any read set was recorded, so no read set can name it, and a files-only
instrument reports the diff as touching nothing. The directory a node SCANS
is the only recorded evidence that a file which does not exist yet would have
been read if it had. Additions are also the majority shape in this program —
every round writes new files.

WHAT IT IS NOT
--------------
* Not a gate. `blast` is diagnostic; it exits 0 whatever it finds unless
  `--strict` is passed, and nothing in `run_driver.sh` blocks on it. A check
  must never be able to stop the round that would fix it (round 493's rule).
* Not sound in the "no false negatives" sense, and the two directions of
  error are stated rather than hidden:

  UNDER-approximation (a redden this will MISS):
    - A node whose dependence is through `os.path.exists`/`os.stat` only,
      with no read and no listing. Audited events are open/listdir/scandir/
      import; `os.stat` is deliberately not audited — it fires on nearly
      every path operation and would implicate everything.
    - A node whose behaviour depends on a file's CONTENT reached through a
      subprocess. `harness/tests/test_swe_copyparity_real_subject.py`'s CLI
      tests shell out; the child's reads are in the child's process and this
      hook is not installed there. That file is covered anyway because its
      static tests read the same tree in-process — but the general case is a
      hole, and it is why `blast` reports at FILE granularity by default.
    - Anything recorded against a tree that has since moved. The map carries
      the HEAD it was recorded at and `blast` says so when it is stale.

  OVER-approximation (a node named that would NOT actually go red):
    - Reading a file is not the same as asserting anything about it.
      `scan_escapes` reads all 108 `*.py` files under `languages/whence`;
      changing any one implicates the node, and almost none of those changes
      would redden it. This is the correct direction to be wrong in: the
      answer is a SHORTLIST TO RUN, and running it is seconds.

* Not a replacement for the fast tier. If your diff is inside your own
  track's tree and you ran your own track's suite, `blast` mostly tells you
  what you already know. Its whole value is the row whose file is in a
  directory you do not run.

THE PLUGIN IS INERT UNLESS ASKED
--------------------------------
An audit hook cannot be removed once added, so importing this module as a
library (which `blast` does, and which every test in
`harness/tests/test_readset.py` does) must not install one. The hook is
installed at import time ONLY when `READSET_OUT` is set in the environment,
which is what `record` does for its pytest subprocess and nothing else does.
`test_the_audit_hook_is_not_installed_without_the_env_var` holds that open.
"""
import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Where `record` writes and `blast` reads. Beside `tier-budget.json` and
#: `wiring-registry.json` rather than under `state/`, because it is a
#: refreshed measurement of the CURRENT tree, not a per-round record --
#: `wiring-registry.json`'s `frozen_prefixes` says why `state/` is the wrong
#: home for anything a later round is expected to re-derive.
DEFAULT_MAP = os.path.join(ROOT, "harness", "readset-map.json")

#: The environment variable that arms the audit hook. Named, not implicit,
#: so a reader of `run_driver.sh` or of a shell history can see that a run
#: was instrumented.
OUT_ENV_VAR = "READSET_OUT"

#: Audited events. `os.stat` is deliberately absent -- see the docstring.
_EVENTS = frozenset(("open", "os.listdir", "os.scandir", "import"))

#: Directory names that never carry a tracked source file. A path with any
#: of these as a component is dropped at record time, so the map stays a
#: statement about the repo rather than about the interpreter.
IGNORED_PARTS = frozenset((
    ".git", "__pycache__", "node_modules", ".venv", "research-env",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "site-packages",
    ".hypothesis", ".tox", "egg-info",
))

#: Bucket for reads that happen while no test and no collector is running
#: (plugin startup, session teardown). Kept rather than dropped so the map's
#: totals are honest about what it could not attribute.
UNATTRIBUTED = "<unattributed>"

#: Suffix marking the collection bucket of a file: module-level code, the
#: imports a test file does at the top, and anything a `conftest.py` does on
#: the way in. Round 505 measured that this is where a real dependence
#: lands for at least one node, so dropping it would be a silent hole.
COLLECT_SUFFIX = "::<collect>"


# ------------------------------------------------------------- the recorder --

class Recorder(object):
    """Accumulates per-key `files`/`scans` sets from audit events.

    `key` is a pytest nodeid, a `<file>::<collect>` bucket, or
    `UNATTRIBUTED`. Everything is stored repo-relative with `/` separators
    so a map recorded on one checkout reads on another.
    """

    def __init__(self, root=ROOT):
        self.root = os.path.abspath(root) + os.sep
        self.key = UNATTRIBUTED
        self.files = {}
        self.scans = {}
        self.n_events = 0
        self.n_kept = 0

    # -- path handling ------------------------------------------------------
    def rel(self, path):
        """Repo-relative POSIX path, or None if outside/ignored/not a path."""
        if isinstance(path, bytes):
            try:
                path = path.decode("utf-8", "strict")
            except UnicodeDecodeError:
                return None
        if not isinstance(path, str) or not path:
            return None
        if "<" in path or ">" in path:
            # CPython's SyntaxError handler literally calls
            # `open("<unknown>", "rb")` to fetch the offending source line,
            # and `<stdin>`/`<string>`/`<frozen importlib._bootstrap>` all
            # arrive as `open`/`import` audit args too. Relative, so
            # `abspath` puts them INSIDE the repo and they land in the map
            # as a file nobody can change. Measured round 505 on
            # `test_marked_tests_is_none_for_an_unparsable_file...`, whose
            # whole point is to parse a broken file.
            return None
        try:
            full = os.path.abspath(path)
        except (ValueError, OSError):
            return None
        if full == self.root.rstrip(os.sep):
            # The repo root ITSELF, which is a real scan target: a node that
            # `os.walk`s the checkout scans it first. Recorded as "." rather
            # than dropped, so an added TOP-LEVEL file (whose `dirname` is
            # "") can get a scan hit like any other. Maps recorded before
            # round 505 made this change simply have no "." row; the query
            # is unchanged for them.
            #
            # This test MUST precede the `startswith` guard below, and round
            # 506 moved it there. `self.root` carries a trailing separator,
            # so the root path itself does NOT start with it: round 505 wrote
            # the branch after the guard, where `rel` can never be empty, and
            # the guard returned None for the one path the branch existed to
            # catch. The comment was right and the code was unreachable.
            return "."
        if not full.startswith(self.root):
            return None
        rel = full[len(self.root):].replace(os.sep, "/")
        for part in rel.split("/"):
            if part in IGNORED_PARTS or part.endswith(".egg-info"):
                return None
        return rel

    @staticmethod
    def is_read(mode, flags):
        """`open`'s audit args say whether this is a read.

        A test that WRITES a repo file does not depend on it -- counting the
        write would make every node that touches `logs/` or a generated
        registry look like a reader of it. `io.open` passes a mode string;
        `os.open` passes None and an int flags.
        """
        if isinstance(mode, str):
            return not any(c in mode for c in "wax+")
        if isinstance(flags, int):
            return not (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT
                                 | os.O_TRUNC | os.O_APPEND))
        return True

    # -- the hook -----------------------------------------------------------
    def hook(self, event, args):
        if event not in _EVENTS:
            return
        self.n_events += 1
        if event == "open":
            path = args[0] if args else None
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else None
            if not self.is_read(mode, flags):
                return
            self._add(self.files, path)
        elif event == "import":
            # ("module", filename, path, meta_path, path_hooks)
            fn = args[1] if len(args) > 1 else None
            self._add(self.files, fn)
        else:                                    # os.listdir / os.scandir
            self._add(self.scans, args[0] if args else None)

    def _add(self, bucket, path):
        rel = self.rel(path)
        if rel is None:
            return
        self.n_kept += 1
        bucket.setdefault(self.key, set()).add(rel)

    # -- serialisation ------------------------------------------------------
    def as_map(self, roster=None, extra=None):
        keys = sorted(set(self.files) | set(self.scans))
        every = set()
        for b in (self.files, self.scans):
            for v in b.values():
                every |= v
        ignored = gitignored(every, self.root.rstrip(os.sep))
        nodes = {}
        for k in keys:
            nodes[k] = {
                "files": sorted(self.files.get(k, set()) - ignored),
                "scans": sorted(self.scans.get(k, set()) - ignored),
            }
        nodes = dict((k, v) for k, v in nodes.items()
                     if v["files"] or v["scans"])
        m = {
            "_comment": (
                "Written by `python3 harness/readset.py record`. Per test "
                "node: `files` = repo paths OPENED for reading or imported "
                "while that node ran; `scans` = repo directories LISTED. "
                "Read by `harness/readset.py blast`, which maps a working-"
                "tree diff onto the nodes it can redden. The two sets are "
                "not redundant: an ADDED file cannot appear in any read "
                "set, and its directory's scan set is the only recorded "
                "evidence that some node would have read it."),
            "schema": 1,
            "recorded_at": int(time.time()),
            "head": git_head(),
            "roster": sorted(roster or ()),
            "n_events": self.n_events,
            "n_kept": self.n_kept,
            "n_gitignored_dropped": len(ignored),
            "nodes": nodes,
        }
        if extra:
            m.update(extra)
        return m


def gitignored(paths, root=ROOT):
    """The subset of `paths` git ignores, via git's own rule.

    A path git ignores can never appear in `git status --porcelain`, so it
    can never match a `blast` query -- it is dead weight in the map by
    construction. Round 505 measured the weight: `logs/` alone was 17023 of
    26385 recorded file entries, 65% of a 1.26 MB map, and not one of them
    could ever produce a hit. `.gitignore` is not re-implemented here; `git
    check-ignore` is asked, once, with every distinct path on stdin.

    FAIL-OPEN. If git is unavailable or errors, nothing is dropped: an
    over-full map answers every query correctly and merely costs bytes,
    while a wrongly-emptied one answers "nothing is implicated" -- the one
    output a reader must never get by accident.
    """
    paths = sorted(paths)
    if not paths:
        return set()
    try:
        p = subprocess.run(["git", "-C", root, "check-ignore", "--stdin"],
                           input="\n".join(paths) + "\n",
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return set()
    if p.returncode not in (0, 1):            # 1 == nothing was ignored
        return set()
    return set(l.strip() for l in p.stdout.splitlines() if l.strip())


def git_head(root=ROOT):
    try:
        p = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=20)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


# ------------------------------------------------------- the pytest plugin --
# Module-level hooks: this file IS the plugin, loaded as `-p readset` with
# `harness/` on PYTHONPATH. It is armed only when READSET_OUT is set.

_REC = None
_OUT = None

if os.environ.get(OUT_ENV_VAR):
    # POP, do not read. Round 505 measured what happens when the arming
    # variable survives into a child process: `harness/tests/test_swe_proc.py
    # ::test_ref_diff_test_survives_running_from_a_tempdir_copy` went RED
    # under the first instrumented run and passed solo. Every child pytest
    # this suite spawns would install its own hook and race to write the same
    # map. Popping it here makes the instrumentation exactly one process deep,
    # which is also what makes the map attributable.
    _OUT = os.environ.pop(OUT_ENV_VAR)
    _REC = Recorder(os.environ.pop("READSET_ROOT", ROOT))
    sys.addaudithook(_REC.hook)


#: Path from the recorded root to pytest's rootdir, as `a/b/`, or "".
#: Round 509 (SWE-loop D). `_key`'s original docstring said "pytest nodeids
#: are already repo-relative" and that is TRUE ONLY when pytest's rootdir IS
#: the repo root -- which held for exactly as long as the map covered
#: `harness/tests/` alone. `languages/whence/pytest.ini` makes rootdir
#: `languages/whence`, so the same suite collects as
#: `tests/test_assertshadow.py::…`, and a map merging both trees would key a
#: whence node and a hypothetical `harness/tests/`-rooted node on the same
#: string. `blast` reports `file_of(key)` straight to the user as a path to
#: run, so an unprefixed key is not merely ambiguous, it is a WRONG COMMAND.
_PREFIX = ""


def pytest_configure(config):
    """Record the rootdir offset before any nodeid is keyed."""
    global _PREFIX
    if _REC is None:
        return
    try:
        rootdir = str(config.rootpath)
    except AttributeError:                                # pragma: no cover
        rootdir = str(config.rootdir)
    rel = os.path.relpath(rootdir, _REC.root.rstrip(os.sep))
    _PREFIX = "" if rel in (".", "") else rel.replace(os.sep, "/") + "/"


def _key(nodeid):
    """A pytest nodeid made relative to the RECORDED ROOT, `/`-separated.

    Prefixed with `_PREFIX` when pytest's rootdir is below the recorded root
    (see `_PREFIX`). `UNATTRIBUTED` is never prefixed -- it is a bucket, not
    a path."""
    nid = str(nodeid).replace(os.sep, "/")
    if not nid or nid == UNATTRIBUTED:
        return nid or UNATTRIBUTED
    return _PREFIX + nid


def pytest_collectstart(collector):
    if _REC is None:
        return
    nid = _key(getattr(collector, "nodeid", "") or "")
    _REC.key = (nid + COLLECT_SUFFIX) if nid.endswith(".py") else UNATTRIBUTED


def pytest_collectreport(report):
    if _REC is not None:
        _REC.key = UNATTRIBUTED


def pytest_runtest_logstart(nodeid, location):
    if _REC is not None:
        _REC.key = _key(nodeid)


def pytest_runtest_logfinish(nodeid, location):
    if _REC is not None:
        _REC.key = UNATTRIBUTED


def pytest_sessionfinish(session, exitstatus):
    if _REC is None:
        return
    roster = [_key(i.nodeid) for i in getattr(session, "items", ())]
    out = _OUT
    m = _REC.as_map(roster=roster, extra={"exitstatus": int(exitstatus)})
    d = os.path.dirname(os.path.abspath(out))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1, sort_keys=False)
        f.write("\n")


# ------------------------------------------------------------------ queries --

def load_map(path=DEFAULT_MAP):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def file_of(key):
    """The suite file a map key belongs to, or "" for `UNATTRIBUTED`."""
    if key == UNATTRIBUTED:
        return ""
    head = key.split("::", 1)[0]
    return head if head.endswith(".py") else ""


def changed_paths(root=ROOT):
    """Repo-relative paths the working tree changes, staged or not, plus
    untracked files -- which is the set a round is about to commit.

    `git status --porcelain` rather than `git diff`, because the shape this
    module exists for is the ADDED file, and an added file is untracked
    until somebody says `git add`.
    """
    out = []
    try:
        p = subprocess.run(
            ["git", "-C", root, "status", "--porcelain", "-z",
             "--untracked-files=all"],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return out
    if p.returncode != 0:
        return out
    fields = [f for f in p.stdout.split("\0") if f]
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            i += 1                                # the rename SOURCE follows
        out.append(path)
    return sorted(set(out))


def implicated(paths, mp):
    """Rows: one per map key whose recorded evidence covers a changed path.

    `reason` is `read` (the path is in the node's file set -- a modification
    of something it demonstrably read) or `scan` (the path's directory is in
    the node's scan set -- which is how an ADDED file is caught, and the
    reason this function takes two sets instead of one).
    """
    paths = [p.replace(os.sep, "/") for p in paths]
    rows = []
    for key, ent in sorted(mp.get("nodes", {}).items()):
        files = set(ent.get("files", ()))
        scans = set(ent.get("scans", ()))
        hits = []
        for p in paths:
            if p in files:
                hits.append({"path": p, "reason": "read"})
            elif (os.path.dirname(p) or ".") in scans:
                hits.append({"path": p, "reason": "scan"})
        if hits:
            rows.append({"key": key, "file": file_of(key), "hits": hits})
    return rows


def by_file(rows):
    """Union the rows at FILE level.

    Round 505 measured why this is the default unit rather than the node:
    `test_swe_copyparity_real_subject.py` builds its subject in a MODULE-
    scoped fixture, so the ~108 reads land on whichever of its nodes pytest
    ran first and its siblings record almost nothing. Node-level output
    would name one of three tests that share one cause. The file is the unit
    you can actually run, and it is a superset, so it is fail-closed.
    """
    agg = {}
    for r in rows:
        f = r["file"] or UNATTRIBUTED
        d = agg.setdefault(f, {"file": f, "keys": [], "reasons": set(),
                               "paths": set()})
        d["keys"].append(r["key"])
        for h in r["hits"]:
            d["reasons"].add(h["reason"])
            d["paths"].add(h["path"])
    out = []
    for f in sorted(agg):
        d = agg[f]
        out.append({"file": f, "n_keys": len(d["keys"]),
                    "keys": sorted(d["keys"]),
                    "reasons": sorted(d["reasons"]),
                    "paths": sorted(d["paths"])})
    return out


def silent_nodes(mp):
    """Roster entries that read and scanned NOTHING in the repo.

    Not a defect -- most harness tests build a tree in `tmp_path` and are
    genuinely independent of the checkout. Reported because "no row" and
    "no evidence" look identical in the output otherwise, which is round
    349's `a suite that cannot run is not a suite that passes` in miniature.

    NODE-level on purpose, and it does not agree with what `blast` will run.
    `by_file` unions a file's keys, so a node that is silent here can still
    be inside a file `blast` names -- through a sibling node's reads or
    through the file's `::<collect>` bucket. Making this function agree with
    `blast` would answer a different question ("can any diff make me run
    this file") and would report ZERO silent nodes for every file with one
    module-level `open`, which is most of them.
    """
    nodes = mp.get("nodes", {})
    seen = set(k for k, ent in nodes.items()
               if ent.get("files") or ent.get("scans"))
    return [nid for nid in mp.get("roster", ()) if nid not in seen]


def phantom_paths(mp, root=ROOT):
    """(path -> rows that recorded it) for every recorded path NOT in the tree.

    ROUND 523 (harness A). The audit hook fires on the `open` EVENT, and
    CPython raises that event BEFORE the syscall -- so a read that fails with
    ENOENT is recorded exactly like a read that succeeds. Combine that with a
    caller that resolves a bare basename against the ambient cwd, and pytest's
    cwd is this repo's root, and the map acquires repo-relative paths that
    have never existed: `alpha` and `beta` (123 rows each), `my-skill` (54),
    and the `.git` subdirectory roster `branches`/`heads`/`hooks`/`info`/
    `objects`/`pack`/`refs`/`tags` (33 each) -- 190 distinct names across 415
    of the 1456 rows in the map recorded before round 523.

    REPORTED, NOT DROPPED, and the distinction is the owner's call rather
    than an oversight. For `blast` a failed probe can be a REAL dependence:
    create `alpha` at the repo root and a node that probes for it may behave
    differently, which is exactly the addition-shaped redden `scans` exists
    to catch. For a SCOPE it is never evidence, so `harness/scopeinfer.py`
    drops these itself. Deciding whether `record` should stop keeping them
    needs a re-record (a full instrumented suite run) and a judgement about
    probes; this function is what makes either one arguable from data.
    """
    out = {}
    for nid, ent in (mp.get("nodes") or {}).items():
        for p in list(ent.get("files", ())) + list(ent.get("scans", ())):
            if not os.path.exists(os.path.join(root, p)):
                out.setdefault(p, []).append(nid)
    return out


def staleness(mp, root=ROOT):
    """`(is_stale, note)` -- did the tree move since the map was recorded?"""
    head = git_head(root)
    rec = mp.get("head") or ""
    if not head or not rec:
        return (True, "no git HEAD available on one side; cannot compare")
    if head == rec:
        return (False, "recorded at %s, which is HEAD" % rec[:12])
    return (True, "recorded at %s, HEAD is now %s — a node added since then "
                  "has no row here and a file deleted since then still does"
            % (rec[:12], head[:12]))


# ---------------------------------------------------------------- the verbs --

#: The recording invocation, written as literal tokens. `harness/
#: verb_audit.py` reads SOURCE for an entry-point token followed by a verb,
#: and `harness/tests/test_readset.py` runs exactly these argv lists, so the
#: token the audit reads and the command that runs are one string.
RECORD_ARGV = ["harness/readset.py", "record"]
BLAST_ARGV = ["harness/readset.py", "blast"]
SHOW_ARGV = ["harness/readset.py", "show"]
MERGE_ARGV = ["harness/readset.py", "merge"]

#: What `record` instruments when told nothing else: the harness fast tier,
#: the same selection `harness/run_tests_fast.sh` runs.
DEFAULT_TARGET = ["-m", "not swe_slow", "harness/tests/"]


def cmd_record(args):
    target = args.pytest_args or list(DEFAULT_TARGET)
    out = os.path.abspath(args.out)
    env = dict(os.environ)
    env[OUT_ENV_VAR] = out
    env["READSET_ROOT"] = args.root
    # NOT `PYTHONPATH`, and this is the round-505 finding that cost a whole
    # 548 s recording. The plugin has to be importable by the pytest process,
    # and the obvious way to arrange that is `PYTHONPATH=<root>/harness` --
    # which is INHERITED by every subprocess the suite spawns. `harness/
    # tests/test_swe_proc.py::test_ref_diff_test_survives_running_from_a_
    # tempdir_copy` copies `languages/whence` to a tempdir and asserts that
    # running it there WITHOUT `AGI_RESEARCH_ROOT` fails with
    # `ModuleNotFoundError: swe` -- round 149's whole point. With the
    # harness directory on the inherited `PYTHONPATH`, `import swe` succeeds
    # in the copy, the "broken" run comes back green and the assertion
    # inverts. The instrument had changed the subject: an env var set to
    # make the RECORDER importable made the thing under test importable too.
    #
    # `sys.path` is process-local and is not inherited, so the bootstrap
    # below arms exactly one process and leaks nothing.
    # THIS file's directory, not `args.root/harness`: `--root` names the tree
    # being RECORDED, which may be any checkout (the tests point it at a
    # miniature repo in `tmp_path`), while the plugin always ships here.
    # LOAD BY FILE LOCATION -- `harness/` never goes on `sys.path` at all.
    # Round 509 (SWE-loop D) found the second half of round 505's own
    # finding. That round reasoned about the arming variable leaking into
    # CHILD processes and chose `sys.path` because it "is process-local and
    # is not inherited" -- correct, and silent about the process the
    # recorder is in. MEASURED, three runs of the same selection:
    #
    #   harness/ at sys.path[0]   `languages/whence/tests/test_v38.py`
    #   harness/ appended          -> ModuleNotFoundError at collection,
    #                                 `1 error during collection`, rc=2
    #   loaded by file location    -> 14 tests collected, clean
    #
    # `harness/tests/__init__.py` makes `tests` a regular package, and the
    # repo root has no `tests/`, so with `harness/` on the path in ANY
    # position a bare `import tests` binds to `harness/tests` -- verified
    # directly: `tests.__path__ == ['<repo>/harness/tests']`. Every
    # `from tests.X import ...` in the whence suite then fails. The
    # instrument had changed the subject, which is the same class of defect
    # round 505's own comment describes one step earlier in the chain.
    # `record` did not notice: it only refuses when NO map is written, so
    # the aborted run still produced a 10-key map that `blast` would read
    # as authoritative.
    boot = ("import sys, importlib.util as U; "
            "s = U.spec_from_file_location('readset', %r); "
            "m = U.module_from_spec(s); sys.modules['readset'] = m; "
            "s.loader.exec_module(m); import pytest; "
            "raise SystemExit(pytest.main(sys.argv[1:]))"
            % os.path.abspath(__file__))
    cmd = ([sys.executable, "-c", boot, "-p", "readset", "-q"] + target)
    t0 = time.time()
    p = subprocess.run(cmd, cwd=args.root, env=env)
    dt = time.time() - t0
    if not os.path.exists(out):
        print("readset: NO MAP WRITTEN — pytest exited %d in %.1fs; a run "
              "that recorded nothing is not an empty tree" % (p.returncode, dt))
        return 1
    mp = load_map(out)
    # rc 2/3/4 are pytest's INTERRUPTED / INTERNAL ERROR / USAGE ERROR. rc 1
    # is "tests failed", which is fine here -- a failing test still read the
    # files it read. Round 509 added this: the sys.path defect above aborted
    # collection in 0.6 s and `record` printed a cheerful summary over a
    # 10-key map, because the only refusal it had was "no file was written".
    # A map recorded from an interrupted collection is not a small map, it
    # is a WRONG one -- `blast` reads absence as "nothing reads this".
    if p.returncode in (2, 3, 4):
        print("readset: INCOMPLETE RUN — pytest exited %d (interrupted / "
              "internal / usage error). %d key(s) were written to %s and "
              "they are NOT a statement about the tree; re-run before "
              "merging or blasting."
              % (p.returncode, len(mp.get("nodes", {})),
                 os.path.relpath(out, args.root)))
        return 1
    print("readset record: %d node(s) rostered, %d key(s) with evidence, "
          "%d audited event(s), %d kept, pytest rc=%d in %.1fs -> %s"
          % (len(mp.get("roster", ())), len(mp.get("nodes", {})),
             mp.get("n_events", 0), mp.get("n_kept", 0), p.returncode, dt,
             os.path.relpath(out, args.root)))
    return 0


def merge_maps(maps):
    """Union several recorded maps into one.

    Round 509 (SWE-loop D). `record` instruments EXACTLY ONE pytest process
    (`OUT_ENV_VAR` is popped, not read, so no child re-arms the hook), and
    the four checks whose reds this module exists to predict are four
    SEPARATE pytest invocations with three different rootdirs. So a map that
    covers more than `harness/tests/` cannot be produced by one run, and
    merging is not a convenience -- it is the only way the instrument can
    reach the trees where 4 of round 507's 7 directly-opened reds live.

    Union semantics, chosen so a merged map can only ever say MORE:

      * `nodes`  -- per key, the union of `files` and of `scans`. A key
        present in two maps was recorded twice; keeping both sets is right,
        because a node's read set is a lower bound on what it touches.
      * `roster` -- union. Used by `silent`, which asks which rostered nodes
        touched nothing; a node absent from one map's roster was simply not
        collected by that run.
      * `head`   -- kept ONLY if every input agrees. Otherwise `""`, which
        `staleness()` already renders as "no git HEAD available on one side;
        cannot compare". A merged map whose halves were recorded at
        different commits must not claim either one.
      * counters -- summed. `sources` records what went in.
    """
    nodes, roster, heads, n_events, n_kept, srcs = {}, set(), set(), 0, 0, []
    # ROUND 510: summed like the other counters. `merge_maps` shipped
    # without it and `test_the_shipped_map_carries_no_gitignored_path`
    # asserts it is NON-ZERO -- the positive control that the filter ran at
    # all -- so the first real merged map failed a test about a property it
    # actually had.
    n_dropped = 0
    for name, m in maps:
        for k, ent in m.get("nodes", {}).items():
            cur = nodes.setdefault(k, {"files": set(), "scans": set()})
            cur["files"] |= set(ent.get("files", ()))
            cur["scans"] |= set(ent.get("scans", ()))
        roster |= set(m.get("roster", ()))
        heads.add(m.get("head") or "")
        n_events += int(m.get("n_events", 0) or 0)
        n_kept += int(m.get("n_kept", 0) or 0)
        n_dropped += int(m.get("n_gitignored_dropped", 0) or 0)
        srcs.append({"source": name, "keys": len(m.get("nodes", {})),
                     "roster": len(m.get("roster", ())),
                     "head": m.get("head") or "",
                     "exitstatus": m.get("exitstatus")})
    out = {
        "_comment": (
            "Written by `python3 harness/readset.py merge`. The union of "
            "several `record` runs -- one per pytest rootdir, because "
            "`record` instruments exactly one process. Per test node: "
            "`files` = repo paths OPENED for reading or imported while that "
            "node ran; `scans` = repo directories LISTED. Read by "
            "`harness/readset.py blast`."),
        "schema": 1,
        "recorded_at": int(time.time()),
        "head": (heads.pop() if len(heads) == 1 else ""),
        "roster": sorted(roster),
        "n_events": n_events,
        "n_kept": n_kept,
        "n_gitignored_dropped": n_dropped,
        "sources": srcs,
        "nodes": dict((k, {"files": sorted(v["files"]),
                           "scans": sorted(v["scans"])})
                      for k, v in sorted(nodes.items())),
    }
    return out


def cmd_merge(args):
    maps = []
    for path in args.maps:
        try:
            maps.append((os.path.relpath(path, args.root), load_map(path)))
        except (OSError, ValueError) as exc:
            print("readset merge: cannot read %s (%s)" % (path, exc))
            return 1
    if not maps:
        print("readset merge: nothing to merge")
        return 1
    out = merge_maps(maps)
    d = os.path.dirname(os.path.abspath(args.out))
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, sort_keys=False)
        f.write("\n")
    for srow in out["sources"]:
        print("  in   %-44s %5d key(s)  %5d rostered  head %s"
              % (srow["source"], srow["keys"], srow["roster"],
                 (srow["head"] or "?")[:12]))
    print("readset merge: %d source(s) -> %d key(s), %d rostered, head %s -> %s"
          % (len(maps), len(out["nodes"]), len(out["roster"]),
             (out["head"] or "DISAGREE")[:12],
             os.path.relpath(args.out, args.root)))
    return 0


def cmd_blast(args):
    try:
        mp = load_map(args.map)
    except (OSError, ValueError) as exc:
        print("readset: no usable map at %s (%s). Record one first:\n"
              "    python3 harness/readset.py record" % (args.map, exc))
        return 0 if not args.strict else 1
    paths = args.paths or changed_paths(args.root)
    rows = implicated(paths, mp)
    files = by_file(rows)
    stale, note = staleness(mp, args.root)
    if args.json:
        print(json.dumps({"paths": paths, "rows": rows, "files": files,
                          "stale": stale, "stale_note": note}, indent=2))
    else:
        if not paths:
            print("readset blast: the working tree is clean — nothing to "
                  "attribute.")
            return 0
        print("readset blast: %d changed path(s) against %d recorded key(s)"
              % (len(paths), len(mp.get("nodes", {}))))
        print("  map %s" % note)
        for p in paths[:40]:
            print("    changed  %s" % p)
        if len(paths) > 40:
            print("    ... and %d more" % (len(paths) - 40))
        if not files:
            print("  NO recorded node reads or scans any of them. That is a "
                  "claim about the MAP, not about the tree: a node added "
                  "since the map was recorded has no row here.")
        for d in files:
            print("  IMPLICATED  %-52s %d key(s)  [%s]"
                  % (d["file"] or UNATTRIBUTED, d["n_keys"],
                     ",".join(d["reasons"])))
            for p in d["paths"][:6]:
                print("                via %s" % p)
        if files:
            print("  run them:\n    python3 -m pytest -q %s"
                  % " ".join(d["file"] for d in files if d["file"]))
    if args.strict:
        return 1 if files else 0
    return 0


def cmd_show(args):
    mp = load_map(args.map)
    nodes = mp.get("nodes", {})
    keys = [k for k in sorted(nodes) if args.key in k]
    if not keys:
        print("no key in the map matches %r" % args.key)
        return 1
    for k in keys:
        ent = nodes[k]
        print("%s\n  files %d  scans %d"
              % (k, len(ent["files"]), len(ent["scans"])))
        for f in ent["files"][:args.limit]:
            print("    read %s" % f)
        if len(ent["files"]) > args.limit:
            print("    ... and %d more read" % (len(ent["files"]) - args.limit))
        for s in ent["scans"][:args.limit]:
            print("    scan %s/" % s)
        if len(ent["scans"]) > args.limit:
            print("    ... and %d more scanned"
                  % (len(ent["scans"]) - args.limit))
    return 0


def cmd_phantoms(args):
    mp = load_map(args.map)
    ph = phantom_paths(mp)
    rows = sorted(ph.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    nodes = set()
    for _p, ns in rows:
        nodes |= set(ns)
    if args.json:
        print(json.dumps({"n_paths": len(ph), "n_nodes": len(nodes),
                          "paths": dict((p, len(n)) for p, n in rows)},
                         indent=1, sort_keys=True))
        return 0
    print("recorded paths that do not exist in this tree: %d, across %d of "
          "%d node row(s)" % (len(ph), len(nodes), len(mp.get("nodes", {}))))
    for path, ns in rows[:args.show]:
        print("  %5d  %s" % (len(ns), path))
    if len(rows) > args.show:
        print("  ... %d more" % (len(rows) - args.show))
    return 0


def cmd_silent(args):
    mp = load_map(args.map)
    out = silent_nodes(mp)
    for nid in out:
        print("reads-nothing  %s" % nid)
    print("readset silent: %d of %d rostered node(s) touch no repo path — "
          "they are `tmp_path` tests and no diff can implicate them"
          % (len(out), len(mp.get("roster", ()))))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=ROOT)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("record", help="run a suite under the audit hook")
    p.add_argument("--out", default=DEFAULT_MAP)
    p.add_argument("pytest_args", nargs="*",
                   help="pytest selection (default: the harness fast tier)")
    p.set_defaults(fn=cmd_record)

    p = sub.add_parser("blast", help="which nodes can my diff redden?")
    p.add_argument("--map", default=DEFAULT_MAP)
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true",
                   help="exit 1 if anything is implicated (opt-in; the "
                        "driver does NOT use this)")
    p.add_argument("paths", nargs="*",
                   help="paths to attribute (default: the working tree)")
    p.set_defaults(fn=cmd_blast)

    p = sub.add_parser("merge", help="union several recorded maps into one")
    p.add_argument("--out", default=DEFAULT_MAP)
    p.add_argument("maps", nargs="+")
    p.set_defaults(fn=cmd_merge)

    p = sub.add_parser("show", help="one node's recorded read/scan sets")
    p.add_argument("key")
    p.add_argument("--map", default=DEFAULT_MAP)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("phantoms",
                       help="recorded paths that do not exist in the tree")
    p.add_argument("--map", default=DEFAULT_MAP)
    p.add_argument("--json", action="store_true")
    p.add_argument("--show", type=int, default=25)
    p.set_defaults(fn=cmd_phantoms)

    p = sub.add_parser("silent", help="rostered nodes that read nothing")
    p.add_argument("--map", default=DEFAULT_MAP)
    p.set_defaults(fn=cmd_silent)

    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        ap.print_help()
        return 0
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

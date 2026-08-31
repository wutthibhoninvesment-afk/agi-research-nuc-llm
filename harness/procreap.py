"""Stop a run you started, and PROVE it stopped. (round 403, harness A)

Why this exists
---------------
Round 402 launched a full whence tier in a pristine worktree at
`/tmp/wt-402`, decided to stop it, and ran:

    ps -eo pid,args | grep '[w]t-402' | awk '{print $1}' \
      | while read p; do kill "$p"; echo "killed baseline pid $p"; done

The pattern matched ZERO lines. The worktree path appears in that process's
**cwd** and in its **redirect target**; it never appears in its argv, which
was the same nine bytes as every other whence run on the box:
`python3 -m pytest -c pytest.ini -q tests/`. The `while` body therefore ran
zero times, printed nothing, and the pipeline exited 0 — which is
byte-identical, at the shell level, to having killed everything. The round
then removed `/tmp/wt-402`.

The suite did not stop. It ran for another twelve minutes against a
directory that no longer existed, logged **149 `FileNotFoundError`s** for
paths like `/tmp/wt-402/languages/whence/examples/self_eval.lang`, and
finished at 15:40:43 UTC with

    112 failed, 1752 passed, 6 skipped, 56 errors in 1676.12s (0:27:56)

three minutes AFTER round 402 committed the sentence "the tier has now not
completed for a seventh consecutive round". It had completed. Its result was
an artefact of the round's own teardown, and the path it was written to
(`/tmp/whence_full_402_baseline2.log`) appears in no knowledge file, no
skill, and no line of `state/research-state.md` — only in the raw driver
transcript `logs/round-402.json`, which nothing reads.

A second orphan outlived the round entirely: round 403 found it still
running 27 minutes in, reparented to init, holding the single CPU that
round 403 needed, and writing to `/tmp/whence_full_402_after.log` — where it
had recorded an `F` that round 402's committed record calls zero failures.
That `F` was a real regression (a stale `whence_slow` count pin), and
reading an orphaned process's log is the only reason this program found it.

Three defects compound, and this module addresses each one:

  1. **A kill that matches nothing reports success.** `grep | while read |
     kill` cannot distinguish "no such process" from "all killed". So
     `reap()` treats an EMPTY request as the verdict `nothing_to_do`, which
     is not success, and never returns `stopped` without confirming each
     pid is gone. Round 341/352's standing rule — never report a thing
     finished that you did not watch finish — applied to killing.
  2. **Process identity taken from argv.** Every suite this program runs has
     an identical argv. What distinguishes them is WHERE they run and WHAT
     they have open, so `scan()` keys on cwd and open files and ignores argv
     for matching.
  3. **Teardown that does not wait.** `safe_to_remove()` refuses a path any
     live process is standing in or writing to, which is the check round 402
     did not have when it deleted a worktree out from under a running suite.

The unlinked-inode rule, measured not assumed
---------------------------------------------
Round 403 first concluded these orphans' output was unrecoverable, because
their fd 1 and fd 2 were `/tmp/#113583 (deleted)` — `links=0`, `size=0`,
`pos=0`, flags `020700002`, which decodes to `O_TMPFILE`: an inode that
never had a directory entry. That conclusion was WRONG, and the evidence
that refuted it was one `ls -l /proc/PID/fd/` away: fds 5, 7 and 9 pointed
at `/tmp/whence_full_402_after.log`, a perfectly ordinary named file.

Those unlinked inodes are pytest's own `--capture=fd` machinery, which
dup()s the real stdout aside and dup2()s an anonymous temp file over fd 1.
So `open_logs()` REPORTS named regular files (`nlink >= 1`) and SKIPS
unlinked ones, because on a pytest process the unlinked pair is capture
scaffolding and the named file is the result. Getting this backwards costs a
round the only copy of a measurement it has.

Everything here is offline-testable. `scan()` takes a `ProcSource` and
`reap()` takes `killer`/`is_alive`/`sleeper` callables, so no test in
`test_procreap.py` signals a real process or reads real `/proc`; the fixture
in that file is a transcript of the two orphans as actually measured on
2026-08-31, fd layout included.
"""
import argparse
import json
import os
import signal
import time

# Verdicts. Kept as module constants because two readers (the CLI and
# run_tests_fast.sh's status line) compare against them.
STOPPED = "stopped"
SURVIVED = "survived"
NOTHING_TO_DO = "nothing_to_do"

CLEAN = "clean"
RESIDUE = "residue"
INCONCLUSIVE = "inconclusive"

DEFAULT_RECORD = "state/procreap.jsonl"


class ProcInfo:
    """One process, as much of it as we could read.

    `cwd is None` means the link could not be resolved (permission, or the
    process exited mid-scan). That is recorded, never silently dropped —
    a scanner that drops what it cannot read reports `clean` for a box it
    did not actually look at.
    """

    __slots__ = ("pid", "ppid", "argv", "cwd", "files", "unlinked", "readable",
                 "uid", "vanished", "protected")

    def __init__(self, pid, ppid=None, argv=(), cwd=None, files=(), unlinked=(),
                 readable=True, uid=None, vanished=False, protected=False):
        self.pid = int(pid)
        self.ppid = ppid
        self.argv = list(argv)
        self.cwd = cwd
        self.files = list(files)
        self.unlinked = list(unlinked)
        self.readable = bool(readable)
        self.uid = uid
        self.vanished = bool(vanished)
        self.protected = bool(protected)

    @property
    def orphaned(self):
        """Reparented to init: no round owns it any more."""
        return self.ppid == 1

    def as_dict(self):
        return {
            "pid": self.pid,
            "ppid": self.ppid,
            "argv": self.argv,
            "cwd": self.cwd,
            "files": self.files,
            "unlinked": self.unlinked,
            "readable": self.readable,
            "uid": self.uid,
            "vanished": self.vanished,
            "protected": self.protected,
            "orphaned": self.orphaned,
        }

    def __repr__(self):  # pragma: no cover - debugging aid
        return "ProcInfo(pid=%d, cwd=%r, files=%r)" % (
            self.pid, self.cwd, self.files)


class ProcSource:
    """Read-only view of the process table. Injectable so tests need no /proc."""

    def pids(self):  # pragma: no cover - interface
        raise NotImplementedError

    def info(self, pid):  # pragma: no cover - interface
        raise NotImplementedError


class ProcfsSource(ProcSource):
    """The real `/proc`. Never raises for a process that vanishes mid-read."""

    def __init__(self, root="/proc"):
        self.root = root

    def pids(self):
        out = []
        try:
            names = os.listdir(self.root)
        except OSError:
            return out
        for name in names:
            if name.isdigit():
                out.append(int(name))
        return sorted(out)

    def info(self, pid):
        base = os.path.join(self.root, str(pid))
        readable = True
        try:
            uid = os.stat(base).st_uid
        except OSError:
            uid = None
        try:
            with open(os.path.join(base, "cmdline"), "rb") as fh:
                raw = fh.read()
            argv = [p.decode("utf-8", "replace")
                    for p in raw.split(b"\0") if p]
        except OSError:
            argv, readable = [], False
        denied = False
        try:
            cwd = os.readlink(os.path.join(base, "cwd"))
        except PermissionError:
            cwd, readable, denied = None, False, True
        except OSError:
            cwd, readable = None, False
        ppid = None
        try:
            with open(os.path.join(base, "stat"), "rb") as fh:
                stat = fh.read().decode("utf-8", "replace")
            # comm may contain spaces AND parentheses; split after the last ')'
            tail = stat[stat.rfind(")") + 1:].split()
            if len(tail) >= 2:
                ppid = int(tail[1])
        except (OSError, ValueError, IndexError):
            readable = False
        files, unlinked = self._fds(base)
        if files is None:
            files, unlinked, readable = [], [], False
        # A process that exited between `pids()` and this read is GONE, not
        # unknown. Distinguishing the two matters: without it a live box's
        # ordinary process churn (every `sh -c` a test suite spawns) makes
        # every scan INCONCLUSIVE, which is the same cry-wolf failure the
        # uid filter above was added for.
        vanished = not readable and not os.path.exists(base)
        # `cwd`/`fd` are permission-denied, with our own uid, only for a
        # NON-DUMPABLE process (PR_SET_DUMPABLE 0) — on this box `(sd-pam)`
        # and `gpg-agent`, both permanently unreadable and permanently
        # present. Nothing this program launches is non-dumpable, which
        # `test_a_process_we_launch_is_not_protected` asserts rather than
        # assumes, so a protected process cannot be one of our runs.
        protected = denied and ppid is not None
        return ProcInfo(pid, ppid=ppid, argv=argv, cwd=cwd, files=files,
                        unlinked=unlinked, readable=readable, uid=uid,
                        vanished=vanished, protected=protected)

    def _fds(self, base):
        """Named regular files this process holds open, and unlinked ones.

        The split is the load-bearing part — see the module docstring. A
        pytest process under `--capture=fd` holds BOTH: anonymous capture
        temp files on fd 1/2 and the real redirect target on the dup'd
        originals. Reporting the anonymous ones as "the log" is what made
        round 403 briefly believe an orphan's output was unrecoverable.
        """
        fddir = os.path.join(base, "fd")
        try:
            names = os.listdir(fddir)
        except OSError:
            return None, None
        named, anon = [], []
        for name in names:
            path = os.path.join(fddir, name)
            try:
                target = os.readlink(path)
            except OSError:
                continue
            try:
                st = os.stat(path)  # follows the link to the inode
            except OSError:
                continue
            if not _is_regular(st.st_mode):
                continue
            if st.st_nlink >= 1:
                if target not in named:
                    named.append(target)
            else:
                if target not in anon:
                    anon.append(target)
        return sorted(named), sorted(anon)


def _is_regular(mode):
    return (mode & 0o170000) == 0o100000


def _under(path, root):
    """True if `path` is `root` or lives inside it. Pure string work on
    normalised absolute paths — no filesystem access, so it is honest about
    a directory that has already been deleted (which is exactly the case
    this module exists for)."""
    if not path or not root:
        return False
    p = os.path.normpath(path)
    r = os.path.normpath(root)
    if p == r:
        return True
    return p.startswith(r.rstrip(os.sep) + os.sep)


class ScanResult:
    """Four buckets, of which only two bear on the verdict.

    Unpacks as `(matched, unreadable)` so callers that only care about those
    two can keep writing `matched, unreadable = scan(...)`.
    """

    __slots__ = ("matched", "unreadable", "protected", "vanished")

    def __init__(self, matched, unreadable, protected=(), vanished=()):
        self.matched = list(matched)
        self.unreadable = list(unreadable)
        self.protected = list(protected)
        self.vanished = list(vanished)

    def __iter__(self):
        return iter((self.matched, self.unreadable))

    def __getitem__(self, i):
        return (self.matched, self.unreadable)[i]

    def __len__(self):
        return 2


def ancestors(source, pid):
    """Every pid from `pid` up to init. These are US, not residue.

    A scan run from inside a driver round otherwise reports its own
    `run_driver.sh` -> wrapper -> `claude` -> shell chain as six live
    processes standing in the repo, every round, forever. That is a health
    line nobody would read twice (round 339).
    """
    seen, out = set(), []
    cur = pid
    for _ in range(64):  # cycles are impossible but a bound is free
        if cur is None or cur <= 1 or cur in seen:
            break
        seen.add(cur)
        out.append(cur)
        try:
            cur = source.info(cur).ppid
        except Exception:
            break
    return out


def scan(source, under, self_pid=None, only_uid=None,
         exclude_ancestors=False):
    """Processes whose cwd, or any open named file, is inside `under`.

    Keyed on location, never on argv (defect 2). `self_pid` is excluded so a
    scan cannot select the process running it — this program has met the
    self-matching family twice already (`feedback_pkill_f_matches_your_own_
    shell`, and round 402's own note 1).

    `only_uid` restricts the scan to processes with that owning uid. It
    exists because the fail-closed rule below, written without it, made the
    tool useless: the first live run of `guard-rm` on this box reported
    `INCONCLUSIVE — 116 processes unreadable` for an empty temp directory,
    because a shared box is full of other users' processes whose `cmdline`
    and `cwd` root cannot read. That is round 339's cry-wolf failure, which
    `pristine_check.py` already cites as a reason a checker gets ignored.
    A process this program did not start cannot be one of its runs, so its
    unreadability is not this module's uncertainty; it is skipped outright.
    A process we own but cannot read still counts as unreadable, because
    that one genuinely could be ours.

    Returns a `ScanResult`, which also unpacks as `(matched, unreadable)`.
    A process we could not read is NOT matched and NOT dropped; it lands in
    `unreadable`, and `verdict()` refuses to say `clean` while that list is
    non-empty. Processes that VANISHED mid-scan and processes the kernel
    PROTECTS are counted separately and reported, but do not poison the
    verdict — see the two comments in `ProcfsSource.info`.
    """
    if self_pid is None:
        self_pid = os.getpid()
    skip = {self_pid}
    if exclude_ancestors and self_pid > 0:
        skip.update(ancestors(source, self_pid))
    matched, unreadable, protected, vanished = [], [], [], []
    for pid in source.pids():
        if pid in skip:
            continue
        try:
            info = source.info(pid)
        except Exception:
            unreadable.append(ProcInfo(pid, readable=False))
            continue
        if info.vanished:
            vanished.append(info)
            continue  # exited mid-scan; it is using nothing now
        if only_uid is not None and info.uid is not None and info.uid != only_uid:
            continue  # another user's process: not ours, not our uncertainty
        if info.protected:
            protected.append(info)
            continue
        if not info.readable and info.cwd is None and not info.files:
            # Nothing at all could be read. Almost always a process owned by
            # another user, or one that exited between listdir and read.
            unreadable.append(info)
            continue
        hit = _under(info.cwd, under)
        if not hit:
            hit = any(_under(f, under) for f in info.files)
        if hit:
            matched.append(info)
    return ScanResult(matched, unreadable, protected, vanished)


def open_logs(info):
    """Named files this process is plausibly writing its result to.

    Deliberately just the named regular files, deduped and sorted; the
    unlinked ones are skipped. This is the call that recovers a log path
    from a process whose launcher wrote the path down nowhere.
    """
    return list(info.files)


def verdict(matched, unreadable):
    """Fail-closed: `clean` requires that the scan actually saw the table."""
    if unreadable:
        return INCONCLUSIVE
    return RESIDUE if matched else CLEAN


def safe_to_remove(path, procs):
    """(ok, blockers) — refuse to delete a path anything live is using.

    A process blocks `path` if its cwd is inside it or it holds an open
    named file inside it. This is the check whose absence turned round 402's
    teardown into 149 `FileNotFoundError`s inside a suite that was still
    producing a result.
    """
    blockers = []
    for info in procs:
        if _under(info.cwd, path) or any(_under(f, path) for f in info.files):
            blockers.append(info)
    return (not blockers), blockers


class ReapResult:
    __slots__ = ("requested", "stopped", "survived", "verdict")

    def __init__(self, requested, stopped, survived, verdict):
        self.requested = list(requested)
        self.stopped = list(stopped)
        self.survived = list(survived)
        self.verdict = verdict

    @property
    def ok(self):
        return self.verdict == STOPPED

    def as_dict(self):
        return {
            "requested": self.requested,
            "stopped": self.stopped,
            "survived": self.survived,
            "verdict": self.verdict,
        }


def reap(pids, killer=None, is_alive=None, sleeper=None, term_wait_s=5.0,
         poll_s=0.5):
    """SIGTERM, wait, SIGKILL, then CONFIRM. Success is never assumed.

    Verdicts:
      `nothing_to_do` — the request was empty. This is the round-402 case and
        it is explicitly NOT success: a selector that matched nothing tells
        you nothing about whether anything is running.
      `survived` — at least one pid was still alive after SIGKILL.
      `stopped`  — the request was non-empty and every pid is confirmed gone.
    """
    pids = [int(p) for p in pids]
    if not pids:
        return ReapResult([], [], [], NOTHING_TO_DO)

    if killer is None:
        killer = os.kill
    if sleeper is None:
        sleeper = time.sleep
    if is_alive is None:
        is_alive = _default_is_alive

    for pid in pids:
        try:
            killer(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    waited = 0.0
    while waited < term_wait_s:
        if not any(is_alive(p) for p in pids):
            break
        sleeper(poll_s)
        waited += poll_s

    for pid in pids:
        if is_alive(pid):
            try:
                killer(pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
    sleeper(poll_s)

    stopped = [p for p in pids if not is_alive(p)]
    survived = [p for p in pids if is_alive(p)]
    return ReapResult(pids, stopped, survived,
                      STOPPED if not survived else SURVIVED)


def _default_is_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def record(entry, path=DEFAULT_RECORD, now=None):
    """Append one line to the durable record.

    The whole point of this module is that a result nobody wrote down did
    not happen, so every reap and every scan verdict gets a line here.
    """
    entry = dict(entry)
    entry.setdefault("utc", time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime(now)))
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def last_record(path=DEFAULT_RECORD):
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    except OSError:
        return None
    for ln in reversed(lines):
        try:
            return json.loads(ln)
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _repo_root():
    return os.path.dirname(os.path.abspath(__file__)).rsplit(os.sep + "harness", 1)[0]


def _fmt(info):
    logs = open_logs(info)
    return "  pid=%-8d ppid=%-6s %s cwd=%s\n      open: %s" % (
        info.pid,
        info.ppid,
        "ORPHANED" if info.orphaned else "        ",
        info.cwd,
        ", ".join(logs) if logs else "(none found)",
    )


def cmd_scan(args):
    root = args.under or _repo_root()
    source = ProcfsSource()
    res = scan(source, root, only_uid=os.getuid(),
               exclude_ancestors=not args.include_self_tree)
    matched, unreadable = res.matched, res.unreadable
    v = verdict(matched, unreadable)
    print("procreap scan: under=%s verdict=%s matched=%d unreadable=%d "
          "(protected=%d vanished=%d)"
          % (root, v, len(matched), len(unreadable),
             len(res.protected), len(res.vanished)))
    for info in matched:
        print(_fmt(info))
    if not args.no_record:
        record({"kind": "scan", "under": root, "verdict": v,
                "matched": [i.as_dict() for i in matched],
                "unreadable": [i.pid for i in unreadable]},
               path=args.record)
    return 1 if v == RESIDUE else 0


def cmd_reap(args):
    pids = list(args.pid or [])
    if args.under:
        matched, _ = scan(ProcfsSource(), args.under, only_uid=os.getuid())
        pids.extend(i.pid for i in matched if i.pid not in pids)
    res = reap(pids)
    print("procreap reap: verdict=%s requested=%s stopped=%s survived=%s"
          % (res.verdict, res.requested, res.stopped, res.survived))
    if res.verdict == NOTHING_TO_DO:
        print("  NOTE: an empty selection is not a successful kill. Nothing "
              "was running that matched, or the selector is wrong.")
    if not args.no_record:
        record(dict(kind="reap", **res.as_dict()), path=args.record)
    return 0 if res.ok else 1


def cmd_guard_rm(args):
    res = scan(ProcfsSource(), args.path, only_uid=os.getuid())
    matched, unreadable = res.matched, res.unreadable
    ok, blockers = safe_to_remove(args.path, matched)
    if unreadable:
        print("procreap guard-rm: INCONCLUSIVE — %d processes unreadable; "
              "refusing to bless %s" % (len(unreadable), args.path))
        return 2
    if ok:
        print("procreap guard-rm: safe — nothing live is using %s" % args.path)
        return 0
    print("procreap guard-rm: BLOCKED — %d live process(es) are using %s"
          % (len(blockers), args.path))
    for info in blockers:
        print(_fmt(info))
    return 1


def cmd_status(args):
    rec = last_record(args.record)
    if rec is None:
        print("procreap: no recorded scan")
        return 0
    print("procreap: last %s at %s verdict=%s"
          % (rec.get("kind", "?"), rec.get("utc", "?"), rec.get("verdict", "?")))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", default=DEFAULT_RECORD)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("scan", help="find runs living under a path")
    p.add_argument("--under", default=None)
    p.add_argument("--no-record", action="store_true")
    p.add_argument("--include-self-tree", action="store_true",
                   help="also report our own driver/shell ancestor chain")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("reap", help="stop pids and confirm they stopped")
    p.add_argument("--pid", type=int, action="append")
    p.add_argument("--under", default=None)
    p.add_argument("--no-record", action="store_true")
    p.set_defaults(func=cmd_reap)

    p = sub.add_parser("guard-rm", help="is this path safe to delete?")
    p.add_argument("path")
    p.set_defaults(func=cmd_guard_rm)

    p = sub.add_parser("status", help="last recorded verdict")
    p.set_defaults(func=cmd_status)

    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

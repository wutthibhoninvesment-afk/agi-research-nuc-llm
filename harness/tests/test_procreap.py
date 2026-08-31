"""Tests for harness/procreap.py (round 403, harness A).

The fixture below is not invented. It is a transcript of the two orphaned
pytest processes that round 403 found alive on this box at 15:49 UTC on
2026-08-31 — argv, ppid, cwd and the full fd table as `ls -l /proc/PID/fd/`
actually printed them, including the anonymous `--capture=fd` inodes on
fd 1/2/6/8 and the real redirect target dup'd onto 5/7/9. Keeping the real
shape matters: the two facts this module exists for (identical argv across
different runs, and the log path being discoverable only from the fd table)
are both properties of that shape.
"""
import json
import os

import pytest

from harness import procreap
from harness.procreap import (
    CLEAN,
    INCONCLUSIVE,
    NOTHING_TO_DO,
    RESIDUE,
    STOPPED,
    SURVIVED,
    ProcInfo,
    ProcSource,
    ProcfsSource,
    open_logs,
    reap,
    record,
    last_record,
    safe_to_remove,
    scan,
    verdict,
)

REPO = "/home/pgain/agi-research-nuc-llm"
WT = "/tmp/wt-402"

# argv is byte-identical for both whence runs. That is the whole point.
WHENCE_ARGV = ["python3", "-m", "pytest", "-c", "pytest.ini", "-q", "tests/"]


def _orphan_after():
    """PID 2166178: the post-change run, cwd in the LIVE tree, reparented."""
    return ProcInfo(
        pid=2166178,
        ppid=1,
        argv=list(WHENCE_ARGV),
        cwd=REPO + "/languages/whence",
        files=["/tmp/whence_full_402_after.log"],
        unlinked=["/tmp/#113583", "/tmp/#113584"],
    )


def _orphan_harness():
    """PID 2161852: the harness suite, cwd at the repo root, still parented."""
    return ProcInfo(
        pid=2161852,
        ppid=2161850,
        argv=["python3", "-m", "pytest", "harness/tests/", "-q"],
        cwd=REPO,
        files=["/tmp/harness_402.log"],
        unlinked=["/tmp/#113572", "/tmp/#113580"],
    )


def _worktree_run():
    """The run round 402 believed it killed: identical argv, cwd in /tmp/wt-402."""
    return ProcInfo(
        pid=2160999,
        ppid=1,
        argv=list(WHENCE_ARGV),
        cwd=WT + "/languages/whence",
        files=["/tmp/whence_full_402_baseline2.log"],
        unlinked=["/tmp/#113501"],
    )


class FakeSource(ProcSource):
    def __init__(self, procs, raising=()):
        self._procs = {p.pid: p for p in procs}
        self._raising = set(raising)

    def pids(self):
        return sorted(set(self._procs) | self._raising)

    def info(self, pid):
        if pid in self._raising:
            raise OSError("permission denied")
        return self._procs[pid]


# --------------------------------------------------------------------------
# The round-402 defect, stated as a test
# --------------------------------------------------------------------------

def test_argv_cannot_distinguish_the_worktree_run_but_cwd_can():
    """`ps -eo pid,args | grep '[w]t-402'` matched nothing. cwd matching does.

    Both whence processes carry the same argv, so no argv predicate can
    select one; the worktree path exists only in cwd and in the log path.
    """
    procs = [_orphan_after(), _worktree_run()]
    assert _orphan_after().argv == _worktree_run().argv

    by_argv = [p for p in procs if any(WT in a for a in p.argv)]
    assert by_argv == [], "argv can never identify the worktree run"

    src = FakeSource(procs)
    matched, unreadable = scan(src, WT, self_pid=-1)
    assert [p.pid for p in matched] == [2160999]
    assert unreadable == []


def test_empty_selection_is_not_a_successful_kill():
    """The exact shape of round 402's mistake: zero matches, exit 0."""
    res = reap([], killer=lambda *a: None, is_alive=lambda p: False,
               sleeper=lambda s: None)
    assert res.verdict == NOTHING_TO_DO
    assert res.ok is False, "an empty reap must never report success"
    assert res.stopped == [] and res.survived == []


def test_safe_to_remove_blocks_the_worktree_round_402_deleted():
    procs = [_worktree_run()]
    ok, blockers = safe_to_remove(WT, procs)
    assert ok is False
    assert [b.pid for b in blockers] == [2160999]


def test_safe_to_remove_allows_a_path_nothing_is_using():
    ok, blockers = safe_to_remove("/tmp/wt-999", [_worktree_run()])
    assert ok is True and blockers == []


def test_safe_to_remove_blocks_on_an_open_file_even_when_cwd_is_elsewhere():
    p = ProcInfo(pid=7, ppid=1, cwd="/somewhere/else",
                 files=["/tmp/wt-402/out.log"])
    ok, blockers = safe_to_remove(WT, [p])
    assert ok is False and [b.pid for b in blockers] == [7]


# --------------------------------------------------------------------------
# The refuted hypothesis, pinned so it cannot be re-adopted
# --------------------------------------------------------------------------

def test_open_logs_reports_the_named_file_not_the_capture_inodes():
    """Round 403 first read fd 1's unlinked inode as "output destroyed".

    fd 1/2/6/8 are pytest's `--capture=fd` anonymous temp files; the result
    is on the named file dup'd to 5/7/9. Reporting the anonymous ones is
    how a round loses the only copy of a measurement it has.
    """
    info = _orphan_after()
    assert open_logs(info) == ["/tmp/whence_full_402_after.log"]
    for anon in info.unlinked:
        assert anon not in open_logs(info)


def test_a_scan_recovers_a_log_path_that_was_written_down_nowhere():
    src = FakeSource([_orphan_after(), _orphan_harness()])
    matched, _ = scan(src, REPO, self_pid=-1)
    found = sorted(log for p in matched for log in open_logs(p))
    assert found == ["/tmp/harness_402.log", "/tmp/whence_full_402_after.log"]


# --------------------------------------------------------------------------
# scan / verdict
# --------------------------------------------------------------------------

def test_scan_matches_by_cwd_under_the_repo():
    src = FakeSource([_orphan_after(), _orphan_harness(), _worktree_run()])
    matched, _ = scan(src, REPO, self_pid=-1)
    assert sorted(p.pid for p in matched) == [2161852, 2166178]


def test_scan_excludes_the_scanning_process_itself():
    me = ProcInfo(pid=999, ppid=1, cwd=REPO, files=[])
    src = FakeSource([me, _orphan_after()])
    matched, _ = scan(src, REPO, self_pid=999)
    assert [p.pid for p in matched] == [2166178]


def test_orphaned_is_ppid_one():
    assert _orphan_after().orphaned is True
    assert _orphan_harness().orphaned is False


def test_verdict_is_residue_when_anything_matched():
    assert verdict([_orphan_after()], []) == RESIDUE


def test_verdict_is_clean_only_on_an_empty_readable_scan():
    assert verdict([], []) == CLEAN


def test_verdict_is_inconclusive_when_a_process_could_not_be_read():
    """Fail-closed: absence of evidence is recorded as absence of evidence."""
    assert verdict([], [ProcInfo(pid=5, readable=False)]) == INCONCLUSIVE
    assert verdict([_orphan_after()], [ProcInfo(pid=5, readable=False)]) == \
        INCONCLUSIVE


def test_unreadable_processes_are_reported_not_dropped():
    src = FakeSource([_orphan_after()], raising=[4242])
    matched, unreadable = scan(src, REPO, self_pid=-1)
    assert [p.pid for p in matched] == [2166178]
    assert [p.pid for p in unreadable] == [4242]
    assert verdict(matched, unreadable) == INCONCLUSIVE


def test_a_process_with_nothing_readable_lands_in_unreadable():
    blind = ProcInfo(pid=11, ppid=None, argv=[], cwd=None, files=[],
                     readable=False)
    matched, unreadable = scan(FakeSource([blind]), REPO, self_pid=-1)
    assert matched == [] and [p.pid for p in unreadable] == [11]


def test_path_containment_is_not_a_string_prefix():
    """`/tmp/wt-4` must not swallow `/tmp/wt-402`, and vice versa."""
    p = ProcInfo(pid=1, ppid=1, cwd="/tmp/wt-402/languages", files=[])
    assert scan(FakeSource([p]), "/tmp/wt-4", self_pid=-1)[0] == []
    assert [q.pid for q in scan(FakeSource([p]), "/tmp/wt-402",
                                self_pid=-1)[0]] == [1]


def test_a_path_is_under_itself():
    p = ProcInfo(pid=1, ppid=1, cwd=WT, files=[])
    assert [q.pid for q in scan(FakeSource([p]), WT, self_pid=-1)[0]] == [1]


# --------------------------------------------------------------------------
# reap
# --------------------------------------------------------------------------

class _Box:
    """A fake process table for reap(): TERM is honoured after `resist` polls."""

    def __init__(self, pids, resist=0, immortal=()):
        self.alive = set(pids)
        self.resist = resist
        self.immortal = set(immortal)
        self.signals = []
        self.slept = 0.0

    def kill(self, pid, sig):
        self.signals.append((pid, sig))
        import signal as S
        if pid in self.immortal and sig != S.SIGKILL:
            return
        if pid in self.immortal:
            return
        if sig == S.SIGKILL:
            self.alive.discard(pid)
        elif self.resist <= 0:
            self.alive.discard(pid)

    def is_alive(self, pid):
        return pid in self.alive

    def sleep(self, s):
        self.slept += s
        self.resist -= 1
        if self.resist == 0:
            # the TERM finally lands
            for pid, sig in self.signals:
                import signal as S
                if sig == S.SIGTERM and pid not in self.immortal:
                    self.alive.discard(pid)


def test_reap_stops_on_sigterm_and_confirms():
    import signal as S
    box = _Box([10, 11])
    res = reap([10, 11], killer=box.kill, is_alive=box.is_alive,
               sleeper=box.sleep)
    assert res.verdict == STOPPED and res.ok
    assert sorted(res.stopped) == [10, 11] and res.survived == []
    assert (10, S.SIGKILL) not in box.signals, "no KILL needed"


def test_reap_escalates_to_sigkill_when_sigterm_is_ignored():
    import signal as S
    box = _Box([10], immortal=[])
    box.resist = 2
    res = reap([10], killer=box.kill, is_alive=box.is_alive,
               sleeper=box.sleep, term_wait_s=1.0, poll_s=0.5)
    assert res.verdict == STOPPED
    assert (10, S.SIGTERM) in box.signals


def test_reap_reports_survived_and_is_not_ok():
    box = _Box([10], immortal=[10])
    res = reap([10], killer=box.kill, is_alive=box.is_alive,
               sleeper=box.sleep, term_wait_s=1.0, poll_s=0.5)
    assert res.verdict == SURVIVED
    assert res.ok is False
    assert res.survived == [10] and res.stopped == []


def test_reap_tolerates_a_pid_that_already_exited():
    def killer(pid, sig):
        raise ProcessLookupError(pid)
    res = reap([99], killer=killer, is_alive=lambda p: False,
               sleeper=lambda s: None)
    assert res.verdict == STOPPED and res.stopped == [99]


def test_reap_result_serialises():
    box = _Box([10])
    res = reap([10], killer=box.kill, is_alive=box.is_alive, sleeper=box.sleep)
    d = res.as_dict()
    assert json.loads(json.dumps(d))["verdict"] == STOPPED


# --------------------------------------------------------------------------
# the durable record
# --------------------------------------------------------------------------

def test_record_and_last_record_round_trip(tmp_path):
    p = str(tmp_path / "nested" / "procreap.jsonl")
    record({"kind": "scan", "verdict": CLEAN}, path=p)
    record({"kind": "reap", "verdict": STOPPED}, path=p)
    last = last_record(p)
    assert last["kind"] == "reap" and last["verdict"] == STOPPED
    assert "utc" in last


def test_last_record_is_none_when_there_is_no_record(tmp_path):
    assert last_record(str(tmp_path / "absent.jsonl")) is None


def test_last_record_skips_a_trailing_partial_line(tmp_path):
    p = str(tmp_path / "r.jsonl")
    record({"kind": "scan", "verdict": CLEAN}, path=p)
    with open(p, "a") as fh:
        fh.write('{"kind": "reap", "verdi\n')
    assert last_record(p)["verdict"] == CLEAN


# --------------------------------------------------------------------------
# ProcfsSource against a synthetic /proc — the real parser, no real processes
# --------------------------------------------------------------------------

def _fake_proc(tmp_path, pid, argv, cwd, fds):
    d = tmp_path / str(pid)
    (d / "fd").mkdir(parents=True)
    (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    os.symlink(cwd, str(d / "cwd"))
    # comm deliberately contains a space and a ')' — the field the naive
    # `stat.split()[3]` parse gets wrong.
    (d / "stat").write_text(
        "%d (py test) R 1 %d 0 0 -1 0 0 0\n" % (pid, pid))
    for n, target in fds.items():
        os.symlink(target, str(d / "fd" / str(n)))
    return d


def test_procfs_source_reads_argv_cwd_and_ppid(tmp_path):
    real = tmp_path / "real.log"
    real.write_text("progress\n")
    work = tmp_path / "work"
    work.mkdir()
    _fake_proc(tmp_path, 4242, WHENCE_ARGV, str(work),
               {1: str(real), 2: str(real)})
    src = ProcfsSource(root=str(tmp_path))
    assert 4242 in src.pids()
    info = src.info(4242)
    assert info.argv == WHENCE_ARGV
    assert info.cwd == str(work)
    assert info.ppid == 1, "comm containing ') ' must not break the parse"
    assert info.files == [str(real)]
    assert info.readable is True


def test_procfs_source_skips_non_regular_fds(tmp_path):
    real = tmp_path / "real.log"
    real.write_text("x")
    work = tmp_path / "work"
    work.mkdir()
    _fake_proc(tmp_path, 4243, WHENCE_ARGV, str(work),
               {0: "/dev/null", 1: str(real), 3: str(work)})
    info = ProcfsSource(root=str(tmp_path)).info(4243)
    assert info.files == [str(real)], "dirs and /dev/null are not logs"


def test_procfs_source_marks_a_process_it_cannot_read(tmp_path):
    d = tmp_path / "4244"
    d.mkdir()
    info = ProcfsSource(root=str(tmp_path)).info(4244)
    assert info.readable is False
    assert info.cwd is None


def test_procfs_source_pids_is_empty_for_a_missing_root(tmp_path):
    assert ProcfsSource(root=str(tmp_path / "nope")).pids() == []


def test_scan_over_a_synthetic_procfs_end_to_end(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    wt = tmp_path / "wt-403"
    (wt / "languages").mkdir(parents=True)
    log = tmp_path / "full.log"
    log.write_text("...")
    _fake_proc(proc, 5150, WHENCE_ARGV, str(wt / "languages"), {1: str(log)})
    src = ProcfsSource(root=str(proc))
    matched, unreadable = scan(src, str(wt), self_pid=-1)
    assert [p.pid for p in matched] == [5150]
    assert unreadable == []
    assert verdict(matched, unreadable) == RESIDUE
    ok, blockers = safe_to_remove(str(wt), matched)
    assert ok is False and [b.pid for b in blockers] == [5150]


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------

def test_cli_status_says_no_recorded_check_not_pass(tmp_path, capsys):
    rc = procreap.main(["--record", str(tmp_path / "none.jsonl"), "status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no recorded scan" in out
    assert "pass" not in out.lower()


def test_cli_bare_prints_help(capsys):
    assert procreap.main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_cli_guard_rm_on_a_path_nothing_uses(tmp_path, capsys):
    d = tmp_path / "unused"
    d.mkdir()
    rc = procreap.main(["guard-rm", str(d)])
    assert rc == 0
    assert "safe" in capsys.readouterr().out


# --------------------------------------------------------------------------
# uid scoping — measured, not designed: see scan()'s docstring
# --------------------------------------------------------------------------

def test_another_users_unreadable_process_is_not_our_uncertainty():
    """Without this, `guard-rm` on a live box reported INCONCLUSIVE for an
    empty directory because 116 foreign processes were unreadable."""
    ours = ProcInfo(pid=1, ppid=1, cwd=REPO, files=[], uid=1001)
    theirs = ProcInfo(pid=2, ppid=1, cwd=None, files=[], readable=False,
                      uid=0)
    matched, unreadable = scan(FakeSource([ours, theirs]), REPO,
                               self_pid=-1, only_uid=1001)
    assert [p.pid for p in matched] == [1]
    assert unreadable == []
    assert verdict(matched, unreadable) == RESIDUE


def test_our_own_unreadable_process_still_makes_it_inconclusive():
    mine = ProcInfo(pid=3, ppid=1, cwd=None, files=[], readable=False,
                    uid=1001)
    matched, unreadable = scan(FakeSource([mine]), REPO, self_pid=-1,
                               only_uid=1001)
    assert matched == [] and [p.pid for p in unreadable] == [3]
    assert verdict(matched, unreadable) == INCONCLUSIVE


def test_a_process_whose_uid_is_unknown_is_kept_when_filtering():
    """uid=None means we could not even stat it — conservative, keep it."""
    unknown = ProcInfo(pid=4, ppid=1, cwd=None, files=[], readable=False,
                       uid=None)
    matched, unreadable = scan(FakeSource([unknown]), REPO, self_pid=-1,
                               only_uid=1001)
    assert [p.pid for p in unreadable] == [4]


def test_procfs_source_reports_the_owning_uid(tmp_path):
    work = tmp_path / "w"; work.mkdir()
    log = tmp_path / "l.log"; log.write_text("x")
    _fake_proc(tmp_path, 4245, WHENCE_ARGV, str(work), {1: str(log)})
    info = ProcfsSource(root=str(tmp_path)).info(4245)
    assert info.uid == os.getuid()


def test_a_process_that_exited_mid_scan_is_gone_not_unknown(tmp_path):
    """Ordinary churn must not make every scan INCONCLUSIVE."""
    proc = tmp_path / "proc"
    proc.mkdir()
    src = ProcfsSource(root=str(proc))
    info = src.info(31337)          # /proc/31337 never existed
    assert info.vanished is True and info.readable is False
    matched, unreadable = scan(FakeSource([info]), REPO, self_pid=-1)
    assert matched == [] and unreadable == []
    assert verdict(matched, unreadable) == CLEAN


def test_a_present_but_unreadable_process_is_still_unknown(tmp_path):
    d = tmp_path / "4246"
    d.mkdir()
    info = ProcfsSource(root=str(tmp_path)).info(4246)
    assert info.vanished is False and info.readable is False
    _, unreadable = scan(FakeSource([info]), REPO, self_pid=-1)
    assert [p.pid for p in unreadable] == [4246]


def test_a_process_we_launch_is_not_protected():
    """The claim `protected` rests on, asserted rather than assumed.

    `protected` means the kernel denied `cwd`/`fd` for a process with our
    own uid, which happens only when it is non-dumpable. If a plain
    subprocess of ours ever became non-dumpable, the scan would start
    skipping real runs, so pin it.
    """
    import subprocess
    import sys
    p = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"],
                         stdin=subprocess.PIPE)
    try:
        info = ProcfsSource().info(p.pid)
        assert info.protected is False
        assert info.readable is True
        assert info.cwd is not None
    finally:
        p.stdin.close()
        p.wait(timeout=10)


def test_scan_result_unpacks_as_a_pair_and_exposes_four_buckets():
    from harness.procreap import ScanResult
    r = ScanResult([_orphan_after()], [], [ProcInfo(pid=2, protected=True)],
                   [ProcInfo(pid=3, vanished=True)])
    m, u = r
    assert [p.pid for p in m] == [2166178] and u == []
    assert [p.pid for p in r.protected] == [2]
    assert [p.pid for p in r.vanished] == [3]


def test_protected_processes_do_not_poison_the_verdict():
    guarded = ProcInfo(pid=1104, ppid=1103, cwd=None, files=[],
                       readable=False, uid=1001, protected=True)
    res = scan(FakeSource([guarded]), REPO, self_pid=-1, only_uid=1001)
    assert res.matched == [] and res.unreadable == []
    assert [p.pid for p in res.protected] == [1104]
    assert verdict(*res) == CLEAN


def test_ancestors_walks_up_to_init():
    from harness.procreap import ancestors
    chain = [ProcInfo(pid=100, ppid=50), ProcInfo(pid=50, ppid=10),
             ProcInfo(pid=10, ppid=1)]
    assert ancestors(FakeSource(chain), 100) == [100, 50, 10]


def test_ancestors_is_bounded_when_the_table_lies():
    from harness.procreap import ancestors
    loop = [ProcInfo(pid=7, ppid=8), ProcInfo(pid=8, ppid=7)]
    assert sorted(ancestors(FakeSource(loop), 7)) == [7, 8]


def test_scan_excludes_our_own_driver_chain():
    """The driver chain stands in the repo every round; it is not residue."""
    driver = ProcInfo(pid=680210, ppid=1, cwd=REPO, files=[])
    wrapper = ProcInfo(pid=2172841, ppid=680210, cwd=REPO, files=[])
    me = ProcInfo(pid=2172842, ppid=2172841, cwd=REPO, files=[])
    stray = _orphan_after()
    src = FakeSource([driver, wrapper, me, stray])
    res = scan(src, REPO, self_pid=2172842, exclude_ancestors=True)
    assert [p.pid for p in res.matched] == [2166178]
    res2 = scan(src, REPO, self_pid=2172842, exclude_ancestors=False)
    assert sorted(p.pid for p in res2.matched) == [680210, 2166178, 2172841]


def test_the_default_ledger_is_absolute_and_named_like_its_siblings():
    """A relative default writes wherever the caller was standing.

    `pristine_check.DEFAULT_LEDGER` and `slowtier.DEFAULT_LEDGER` are both
    absolute for this reason; shells in this program keep their cwd between
    calls.
    """
    assert os.path.isabs(procreap.DEFAULT_RECORD)
    assert procreap.DEFAULT_RECORD.endswith(
        os.path.join("state", "procreap-ledger.jsonl"))
    assert os.path.isdir(os.path.join(procreap.REPO_ROOT, "harness"))

"""Offline tests for nuc/swap_watch_launch.py.

Command-construction functions (ssh_argv/scp_argv/remote_launch_cmd/
build_watcher_script/compute_max_iters) are pure string/list builders,
tested directly with no network. `deploy_and_launch`'s real subprocess
calls (scp, ssh, the local detached watcher) are replaced with injected
fakes (`runner`/`popen_factory` params) so these tests never touch the
network or spawn a real process -- the live "box is actually down"
verification lives in the round's own knowledge file, run manually against
the real (offline) NUC target, not as a pytest case (a real network attempt
in a test suite would make the suite depend on host reachability).
"""
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import swap_watch_launch as swl  # noqa: E402


class FakeCompleted:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakePopen:
    def __init__(self, argv, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        self.pid = 424242


# --- pure command builders -------------------------------------------------

def test_ssh_argv_shape():
    argv = swl.ssh_argv("jab@100.78.44.111", "/home/x/.ssh/id_ed25519", "echo hi", connect_timeout=7)
    assert argv[0] == "ssh"
    assert "-i" in argv and argv[argv.index("-i") + 1] == "/home/x/.ssh/id_ed25519"
    assert "ConnectTimeout=7" in " ".join(argv)
    assert argv[-2] == "jab@100.78.44.111"
    assert argv[-1] == "echo hi"


def test_scp_argv_shape():
    argv = swl.scp_argv("local.py", "jab@100.78.44.111", "/k", "/tmp/remote.py")
    assert argv[0] == "scp"
    assert argv[-1] == "jab@100.78.44.111:/tmp/remote.py"
    assert argv[-2] == "local.py"


def test_remote_launch_cmd_contains_interval_duration_and_paths():
    cmd = swl.remote_launch_cmd("/tmp/swap_watch.py", "rtest", 15.0, 3600.0, "~/nuc-research")
    assert "--interval 15.0" in cmd
    assert "--duration 3600.0" in cmd
    assert "swap-watch-rtest-long.json" in cmd
    assert "swap-watch-rtest-checkpoint.jsonl" in cmd
    assert cmd.rstrip().endswith("echo $!")  # last line printed must be the PID
    assert "disown -h" in cmd
    assert "nohup" in cmd


def test_remote_launch_cmd_rejects_tag_with_shell_metachars():
    """A tag with shell metacharacters is rejected outright rather than
    trusted to ad hoc quoting -- one line of the watcher script deliberately
    leaves paths built from `tag`/`remote_outdir` UNQUOTED so the remote
    shell still tilde-expands them (see build_watcher_script), so `tag`
    must be a plain identifier or that line becomes an injection vector."""
    for bad in ("r;rm -rf /", "r$(whoami)", "r`id`", "r'quote", 'r"dquote', "r/slash", ""):
        with pytest.raises(swl.SwapWatchLaunchError):
            swl.remote_launch_cmd("/tmp/swap_watch.py", bad, 15.0, 60.0, "~/nuc-research")


def test_build_watcher_script_also_rejects_bad_tag():
    with pytest.raises(swl.SwapWatchLaunchError):
        swl.build_watcher_script("123", "jab@100.78.44.111", "/k/id", "bad tag",
                                  "~/nuc-research", "/tmp/dest", 60.0, 5)


def test_remote_launch_cmd_and_watcher_script_leave_tilde_bare_for_remote_expansion():
    """The concrete round-100-class bug this round found and fixed: wrapping
    a "~/..." remote path in shlex.quote() single-quotes the tilde, which
    suppresses expansion on the REMOTE shell that actually resolves it (it
    would try to `mkdir` a directory literally named `~`). Assert the fixed
    forms never produce a quoted leading tilde."""
    cmd = swl.remote_launch_cmd("/tmp/swap_watch.py", "rtest", 15.0, 60.0, "~/nuc-research")
    assert "'~/nuc-research" not in cmd
    assert '"$HOME"/nuc-research' in cmd

    script = swl.build_watcher_script("123", "jab@100.78.44.111", "/k/id", "rtest",
                                       "~/nuc-research", "/tmp/dest", 60.0, 5)
    # the diagnostic "ls -la" line is a remote command interpreted by the
    # REMOTE shell -- its tilde must stay bare there.
    assert "ls -la ~/nuc-research" in script
    # the scp lines are different: `host:'~/path'` is parsed entirely by the
    # LOCAL shell (which never tilde-expands a word starting with "host:",
    # quoted or not) before scp/sftp itself resolves "~" on the remote side
    # -- verified for real below, not just asserted.
    assert "jab@100.78.44.111:'~/nuc-research/swap-watch-rtest-checkpoint.jsonl'" in script


def test_scp_remote_tilde_survives_local_shell_parsing_unexpanded():
    """Live proof (no network) that quoting the tilde half of a `host:path`
    scp argument is harmless: run the exact `host:'~/path'` token this
    module emits through a real local /bin/bash and confirm the tilde
    reaches the far side of local parsing completely literal -- local bash
    only tilde-expands a word that STARTS with an unquoted `~`, and this
    word starts with "jab@...", not `~`, so quoting the back half changes
    nothing. This is what makes the scp lines safe while the ssh
    remote-command lines (remote_launch_cmd, the "ls -la" diagnostic) are
    NOT -- there, the whole point is a REMOTE shell doing its own tilde
    expansion, which single quotes DO suppress.
    """
    import subprocess as _sp
    token = "jab@100.78.44.111:'~/nuc-research/swap-watch-rtest-checkpoint.jsonl'"
    out = _sp.run(["bash", "-c", f'printf "%s" {token}'], capture_output=True, text=True, check=True)
    assert out.stdout == "jab@100.78.44.111:~/nuc-research/swap-watch-rtest-checkpoint.jsonl"


def test_compute_max_iters_scales_with_duration_and_margin():
    # 3600s / 60s = 60, * 1.25 margin = 75
    assert swl.compute_max_iters(3600.0, 60.0) == 75
    # short duration floors at min_iters
    assert swl.compute_max_iters(30.0, 60.0, min_iters=10) == 10
    # 28800s (8h) / 60s = 480, *1.25 = 600
    assert swl.compute_max_iters(28800.0, 60.0) == 600


def test_compute_max_iters_rejects_nonpositive_interval():
    with pytest.raises(swl.SwapWatchLaunchError):
        swl.compute_max_iters(3600.0, 0.0)


def test_build_watcher_script_references_pid_and_scp_targets(tmp_path):
    script = swl.build_watcher_script("16184", "jab@100.78.44.111", "/k/id", "rtest",
                                       "~/nuc-research", str(tmp_path), 60.0, 5)
    assert "ps -p 16184" in script
    assert "swap-watch-rtest-checkpoint-final.jsonl" in script
    assert "swap-watch-rtest-long.json" in script
    assert "PULL_DONE" in script
    assert f"seq 1 5" in script
    assert "sleep 60.0" in script


def test_plan_does_not_touch_network_or_filesystem(tmp_path, monkeypatch):
    """plan() must be pure -- no subprocess, no file writes -- since its
    whole purpose is to be inspectable before anything real happens."""
    def boom(*a, **k):
        raise AssertionError("plan() must not invoke subprocess")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    result = swl.plan("rplan", dest_dir=str(tmp_path / "nonexistent"))
    assert "<PID>" in result["watcher_script"]
    assert not (tmp_path / "nonexistent").exists()


# --- deploy_and_launch, with injected fakes --------------------------------

def test_deploy_and_launch_happy_path(tmp_path):
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append(argv)
        if argv[0] == "scp":
            return FakeCompleted(0)
        return FakeCompleted(0, stdout="16184\n")

    popens = []

    def fake_popen(argv, **kwargs):
        p = FakePopen(argv, **kwargs)
        popens.append(p)
        return p

    dest = tmp_path / "dest"
    result = swl.deploy_and_launch("rhappy", dest_dir=str(dest), duration_s=60.0,
                                    poll_interval_s=10.0, runner=fake_runner,
                                    popen_factory=fake_popen)

    assert result["remote_pid"] == "16184"
    assert result["watcher_pid"] == 424242
    assert Path(result["watcher_script_path"]).exists()
    assert len(popens) == 1
    assert popens[0].kwargs.get("start_new_session") is True
    # exactly one scp + one ssh-launch call to the real runner, nothing else
    assert len(calls) == 2
    assert calls[0][0] == "scp"
    assert calls[1][0] == "ssh"


def test_deploy_and_launch_scp_failure_never_starts_watcher(tmp_path):
    def fake_runner(argv, **kwargs):
        return FakeCompleted(1, stderr="Permission denied (publickey).")

    def fake_popen(argv, **kwargs):
        raise AssertionError("watcher must not be launched when scp fails")

    dest = tmp_path / "dest"
    with pytest.raises(swl.SwapWatchLaunchError, match="scp deploy failed"):
        swl.deploy_and_launch("rfail", dest_dir=str(dest), runner=fake_runner,
                               popen_factory=fake_popen)
    assert not dest.exists() or list(dest.iterdir()) == []


def test_deploy_and_launch_remote_launch_failure_never_starts_watcher(tmp_path):
    def fake_runner(argv, **kwargs):
        if argv[0] == "scp":
            return FakeCompleted(0)
        return FakeCompleted(255, stderr="ssh: connect to host 100.78.44.111 port 22: "
                                          "Connection timed out")

    def fake_popen(argv, **kwargs):
        raise AssertionError("watcher must not be launched when the remote launch fails")

    dest = tmp_path / "dest"
    with pytest.raises(swl.SwapWatchLaunchError, match="remote launch failed"):
        swl.deploy_and_launch("rfail2", dest_dir=str(dest), runner=fake_runner,
                               popen_factory=fake_popen)


def test_deploy_and_launch_garbage_pid_output_raises(tmp_path):
    def fake_runner(argv, **kwargs):
        if argv[0] == "scp":
            return FakeCompleted(0)
        return FakeCompleted(0, stdout="python3: command not found\n")

    def fake_popen(argv, **kwargs):
        raise AssertionError("watcher must not be launched when no real PID was returned")

    dest = tmp_path / "dest"
    with pytest.raises(swl.SwapWatchLaunchError, match="did not return a PID"):
        swl.deploy_and_launch("rfail3", dest_dir=str(dest), runner=fake_runner,
                               popen_factory=fake_popen)


def test_deploy_and_launch_watcher_script_matches_returned_remote_pid(tmp_path):
    def fake_runner(argv, **kwargs):
        if argv[0] == "scp":
            return FakeCompleted(0)
        return FakeCompleted(0, stdout="99999\n")

    def fake_popen(argv, **kwargs):
        return FakePopen(argv, **kwargs)

    dest = tmp_path / "dest"
    result = swl.deploy_and_launch("rpidcheck", dest_dir=str(dest), runner=fake_runner,
                                    popen_factory=fake_popen)
    script_text = Path(result["watcher_script_path"]).read_text()
    assert "ps -p 99999" in script_text

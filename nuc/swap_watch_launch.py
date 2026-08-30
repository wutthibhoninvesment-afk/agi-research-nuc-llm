#!/usr/bin/env python3
"""swap_watch_launch.py — one-command deploy+launch+watch for a second
multi-hour swap_watch.py run on the NUC.

Round 268 launched the first (and so far only) genuinely multi-hour
`swap_watch.py` poll by hand: scp the script to /tmp/ on the box, `nohup ...
& disown -h` it there, note the PID. Rounds 274/280/286 each caught a
mid-flight partial pull; round 292 wrote a bespoke, hardcoded local watcher
script (/tmp/wait_r268_r292.sh — a fixed remote PID, a fixed checkpoint
filename, 50 x 60s iterations) to catch the real completion unattended, and
round 298 finally closed out the analysis. Round 298's own next-steps item
("no round has yet run a SECOND multi-hour continuous poll to see whether
the burst-arrival pattern generalizes") has stood open through rounds
301/302/303 because every reachable round since has hit "box down" before
getting to it, and the one-off script from round 292 lived only in /tmp,
was hardcoded to that specific run, and is gone from anywhere durable.

This module is the reusable version: parametrized deploy+launch+watch, with
every ssh/scp command built as a pure, independently testable function (no
network needed to verify command construction), so the next round that
finds the box UP can run one command instead of re-deriving the whole
recipe. It does not touch colibri/toolproxy or port 8001 -- it only
deploys and runs `swap_watch.py` itself, which is read-only cgroup/vmstat
polling (see that module's own docstring).

Two ways to use it:
    python3 swap_watch_launch.py plan --tag r305 --duration 28800
        (builds and prints every command + the watcher script; touches
        nothing, needs no network -- inspect before running for real)
    python3 swap_watch_launch.py launch --tag r305 --duration 28800
        (does it for real: scp the script, ssh-launch it detached on the
        box, write + detach-launch a local watcher that scp's the results
        back once the remote process exits)

Safety property (see `deploy_and_launch`'s docstring): if EITHER remote
step (scp or the ssh launch) fails, the local watcher is never started --
no orphaned watcher can be left polling for a job that never began.
"""
from __future__ import annotations

import argparse
import math
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

DEFAULT_SSH_TARGET = "jab@100.78.44.111"
DEFAULT_SSH_KEY = str(Path.home() / ".ssh" / "id_ed25519")
DEFAULT_REMOTE_SCRIPT = "/tmp/swap_watch.py"
DEFAULT_REMOTE_OUTDIR = "~/nuc-research"
DEFAULT_CONNECT_TIMEOUT_S = 10
DEFAULT_POLL_INTERVAL_S = 60.0
DEFAULT_INTERVAL_S = 15.0
DEFAULT_DURATION_S = 28800.0  # 8h, matching round 268's own run


class SwapWatchLaunchError(RuntimeError):
    pass


def remote_quote(path: str) -> str:
    """Quote a path for the REMOTE shell. A leading `~/` must survive as an
    expansion there, so it becomes `"$HOME"/…` -- a plain `shlex.quote()`
    single-quotes the whole thing, which suppresses tilde expansion and
    makes the remote shell treat `~` as a literal character (this is
    `fast_lane.py`'s own `remote_quote`, round 100's fix for the identical
    bug in `transfer_cmd` -- duplicated here in miniature rather than
    importing that whole unrelated module for one helper).
    """
    if path == "~":
        return '"$HOME"'
    if path.startswith("~/"):
        return '"$HOME"/' + shlex.quote(path[2:])
    return shlex.quote(path)


def _validate_tag(tag: str) -> None:
    """`tag` gets baked into filenames on both ends AND, in one diagnostic
    line of the watcher script, into a remote command string that is
    deliberately left UNQUOTED so `~` stays remote-expandable (see
    `build_watcher_script`) -- so it must be a plain identifier, not
    arbitrary text. Reject anything else outright rather than trying to
    make ad hoc quoting bulletproof against it.
    """
    if not tag or any(c in tag for c in " \t\n'\";&|$`\\/"):
        raise SwapWatchLaunchError(
            f"tag must be a simple identifier (letters/digits/-/_ only, no spaces or shell "
            f"metacharacters): {tag!r}")


def ssh_argv(ssh_target: str, ssh_key: str, remote_cmd: str,
             connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S) -> list:
    return ["ssh", "-i", ssh_key, "-o", f"ConnectTimeout={connect_timeout}",
            ssh_target, remote_cmd]


def scp_argv(local_path: str, ssh_target: str, ssh_key: str, remote_path: str,
             connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S) -> list:
    return ["scp", "-i", ssh_key, "-o", f"ConnectTimeout={connect_timeout}",
            local_path, f"{ssh_target}:{remote_path}"]


def remote_launch_cmd(remote_script: str, tag: str, interval_s: float, duration_s: float,
                       remote_outdir: str = DEFAULT_REMOTE_OUTDIR) -> str:
    """The remote shell command that starts swap_watch.py detached and
    prints its PID on stdout as the only line -- matches round 268's own
    live recipe (`nohup ... & disown -h`) exactly, generalized to any tag/
    interval/duration/outdir instead of one hardcoded run.
    """
    _validate_tag(tag)
    out = f"{remote_outdir}/swap-watch-{tag}-long.json"
    ckpt = f"{remote_outdir}/swap-watch-{tag}-checkpoint.jsonl"
    log = f"{remote_outdir}/swap-watch-{tag}-long.log"
    # ROUND 352, from the first live run this function ever had. The
    # original form was
    #     mkdir -p DIR && nohup python3 ... > LOG 2>&1 < /dev/null & disown -h; echo $!
    # which hangs the ssh CLIENT for the run's entire duration. `&` binds to
    # the whole `A && B` LIST, so bash forks a subshell for it; only `B`
    # carries the redirections, so that subshell inherits sshd's stdout/
    # stderr channel pipes and then blocks in do_wait on python3 for 8 hours.
    # sshd never sees EOF, so `subprocess.run(..., timeout=30)` raises
    # TimeoutExpired even though the remote side started perfectly.
    # Proven on the box, not inferred: /proc/<subshell>/fd/1 -> pipe:[17838]
    # and fd/2 -> pipe:[17839], versus /proc/<python3>/fd/1 -> the .log file,
    # with the subshell's wchan reading `do_wait`.
    #
    # The fix is a brace group whose OWN fds go to /dev/null, so nothing that
    # outlives the ssh session holds the channel:
    #   - the group redirect must be /dev/null, not LOG: group redirections
    #     are applied BEFORE the body runs, and LOG lives inside the very
    #     directory `mkdir -p` is about to create, so `> LOG` on the group
    #     would fail on a first-ever run. LOG stays on the inner command,
    #     where it is opened after mkdir has succeeded.
    #   - `exec` makes the forked group become python3 rather than fork it
    #     and wait, so `$!` is the POLLER's pid. The original printed the
    #     subshell's pid instead; the watcher's `ps -p <pid>` then polled a
    #     wrapper that merely happened to die at the same time as the thing
    #     it was standing in for.
    #   - `&&` is kept: if mkdir fails, exec never runs and the group exits,
    #     which the caller's `_remote_pid_alive` recovery probe detects.
    inner = (
        f"{{ mkdir -p {remote_quote(remote_outdir)} && "
        f"exec nohup python3 {shlex.quote(remote_script)} "
        f"--interval {interval_s} --duration {duration_s} "
        f"--out {remote_quote(out)} --checkpoint {remote_quote(ckpt)} "
        f"> {remote_quote(log)} 2>&1 ; }} "
        f"> /dev/null 2>&1 < /dev/null & disown -h; echo $!"
    )
    return inner


def recover_pid_cmd(remote_script: str, tag: str) -> str:
    """Remote command that finds a running poller for THIS tag, or prints
    nothing. Matches on the checkpoint path, which carries the tag, rather
    than on the script name alone -- `pgrep -f swap_watch.py` would also
    match a poller some other round left running, and adopting one of those
    as "the run we just started" would be worse than failing.
    """
    _validate_tag(tag)
    pattern = f"{Path(remote_script).name} .*swap-watch-{tag}-checkpoint"
    return f"pgrep -f {shlex.quote(pattern)} | head -1"


def _recover_remote_pid(remote_script: str, tag: str, ssh_target: str, ssh_key: str,
                        connect_timeout: int, runner: Callable) -> Optional[str]:
    """Ask the box whether the poller we may have just launched is running.
    Returns its pid as a string, or None. Never raises: this runs on an
    error path, and a failure to answer must degrade to "unknown", which
    the caller reports honestly, rather than to a second exception that
    buries the original one.
    """
    argv = ssh_argv(ssh_target, ssh_key, recover_pid_cmd(remote_script, tag), connect_timeout)
    try:
        res = runner(argv, capture_output=True, text=True, timeout=connect_timeout + 20)
    except Exception:
        return None
    if getattr(res, "returncode", 1) != 0:
        return None
    pid = (getattr(res, "stdout", "") or "").strip().splitlines()
    pid = pid[-1].strip() if pid else ""
    return pid if pid.isdigit() else None


def remote_paths(tag: str, remote_outdir: str = DEFAULT_REMOTE_OUTDIR) -> dict:
    return {
        "out": f"{remote_outdir}/swap-watch-{tag}-long.json",
        "checkpoint": f"{remote_outdir}/swap-watch-{tag}-checkpoint.jsonl",
        "log": f"{remote_outdir}/swap-watch-{tag}-long.log",
    }


def compute_max_iters(duration_s: float, poll_interval_s: float,
                       safety_margin: float = 1.25, min_iters: int = 10) -> int:
    """How many `poll_interval_s`-spaced checks the local watcher should
    make before giving up. Sized to the run's own planned duration plus a
    25% margin (covers a slow box/loaded network adding delay, the same
    kind of slack round 292's hardcoded "50 iterations x 60s = 50 min" gave
    itself for a run it expected to already be nearly finished) -- floored
    at `min_iters` so a short test run still gets a few real checks.
    """
    if poll_interval_s <= 0:
        raise SwapWatchLaunchError("poll_interval_s must be > 0")
    return max(min_iters, math.ceil((duration_s * safety_margin) / poll_interval_s))


def build_watcher_script(remote_pid: str, ssh_target: str, ssh_key: str, tag: str,
                          remote_outdir: str, dest_dir: str, poll_interval_s: float,
                          max_iters: int, connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S) -> str:
    """Bash script text for the LOCAL detached watcher: poll every
    `poll_interval_s` until the remote PID is gone (or `max_iters` is hit),
    then scp both output files back into `dest_dir` and mark PULL_DONE.
    Structurally identical to round 292's proven `/tmp/wait_r268_r292.sh`,
    generalized (parametrized pid/tag/paths/iteration count instead of
    hardcoded) and meant to be committed under a durable path instead of
    living only in /tmp where round 292's copy is not reproducible.
    """
    _validate_tag(tag)
    paths = remote_paths(tag, remote_outdir)
    dest = dest_dir.rstrip("/")
    return f"""#!/bin/bash
set -u
DEST={shlex.quote(dest)}
LOG="$DEST/poll.log"
mkdir -p "$DEST"
: > "$LOG"
for i in $(seq 1 {max_iters}); do
  ts=$(date -u +%FT%TZ)
  status=$(ssh -i {shlex.quote(ssh_key)} -o ConnectTimeout={connect_timeout} \\
    {shlex.quote(ssh_target)} "ps -p {shlex.quote(str(remote_pid))} -o pid= 2>/dev/null" 2>&1)
  echo "$ts iter=$i status=[$status]" >> "$LOG"
  pid_alive=$(echo "$status" | head -1 | tr -d ' ')
  if [ -z "$pid_alive" ]; then
    echo "$ts process gone, pulling final files" >> "$LOG"
    break
  fi
  sleep {poll_interval_s}
done
# remote_outdir left UNQUOTED here (deliberately, tag is pre-validated to
# exclude shell metacharacters) so the REMOTE shell tilde-expands it itself;
# shlex.quote()-ing a leading "~/" here would single-quote it and suppress
# that expansion on the remote end (round 100's fast_lane.py bug, same class).
ssh -i {shlex.quote(ssh_key)} -o ConnectTimeout={connect_timeout} {shlex.quote(ssh_target)} \\
  "uptime; ls -la {remote_outdir} | grep {tag}" >> "$LOG" 2>&1
scp -i {shlex.quote(ssh_key)} -o ConnectTimeout={connect_timeout} \\
  {shlex.quote(ssh_target)}:{shlex.quote(paths["checkpoint"])} \\
  "$DEST/swap-watch-{tag}-checkpoint-final.jsonl" >> "$LOG" 2>&1
scp -i {shlex.quote(ssh_key)} -o ConnectTimeout={connect_timeout} \\
  {shlex.quote(ssh_target)}:{shlex.quote(paths["out"])} \\
  "$DEST/swap-watch-{tag}-long.json" >> "$LOG" 2>&1
echo "PULL_DONE" >> "$LOG"
"""


def plan(tag: str, local_script: str = "nuc/swap_watch.py", interval_s: float = DEFAULT_INTERVAL_S,
         duration_s: float = DEFAULT_DURATION_S, ssh_target: str = DEFAULT_SSH_TARGET,
         ssh_key: str = DEFAULT_SSH_KEY, remote_script: str = DEFAULT_REMOTE_SCRIPT,
         remote_outdir: str = DEFAULT_REMOTE_OUTDIR, dest_dir: str = "state/nuc-swap-watch",
         poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
         connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S) -> dict:
    """Build (without executing) every command this launch would run, plus
    the watcher script text (with a `<PID>` placeholder -- the real PID is
    only known after the remote launch actually happens)."""
    max_iters = compute_max_iters(duration_s, poll_interval_s)
    return {
        "scp_argv": scp_argv(local_script, ssh_target, ssh_key, remote_script, connect_timeout),
        "remote_launch_cmd": remote_launch_cmd(remote_script, tag, interval_s, duration_s,
                                                remote_outdir),
        "ssh_launch_argv": ssh_argv(ssh_target, ssh_key,
                                     remote_launch_cmd(remote_script, tag, interval_s, duration_s,
                                                        remote_outdir), connect_timeout),
        "remote_paths": remote_paths(tag, remote_outdir),
        "max_iters": max_iters,
        "watcher_script": build_watcher_script("<PID>", ssh_target, ssh_key, tag, remote_outdir,
                                                dest_dir, poll_interval_s, max_iters,
                                                connect_timeout),
    }


def deploy_and_launch(tag: str, local_script: str = "nuc/swap_watch.py",
                       interval_s: float = DEFAULT_INTERVAL_S,
                       duration_s: float = DEFAULT_DURATION_S,
                       ssh_target: str = DEFAULT_SSH_TARGET, ssh_key: str = DEFAULT_SSH_KEY,
                       remote_script: str = DEFAULT_REMOTE_SCRIPT,
                       remote_outdir: str = DEFAULT_REMOTE_OUTDIR,
                       dest_dir: str = "state/nuc-swap-watch",
                       poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
                       connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_S,
                       runner: Callable = subprocess.run,
                       popen_factory: Callable = subprocess.Popen) -> dict:
    """Deploy `swap_watch.py` to the box, launch it detached, then launch a
    LOCAL detached watcher that pulls the results back once it finishes.

    Safety property: the local watcher is only started if BOTH the scp and
    the remote launch succeed (return code 0) AND the remote launch printed
    a plausible PID. Any failure raises `SwapWatchLaunchError` before the
    watcher script is even written -- there is no code path that starts a
    watcher for a job that didn't actually start, matching
    `one-shot-agent-no-background-wait`'s step 3 ("write down what's still
    running") by construction: nothing gets written down as running unless
    it verifiably is.

    `runner`/`popen_factory` are injected (default to the real
    `subprocess.run`/`subprocess.Popen`) so tests can substitute fakes
    without touching the network or spawning real processes.
    """
    scp_cmd = scp_argv(local_script, ssh_target, ssh_key, remote_script, connect_timeout)
    scp_res = runner(scp_cmd, capture_output=True, text=True, timeout=60)
    if scp_res.returncode != 0:
        raise SwapWatchLaunchError(
            f"scp deploy failed (rc={scp_res.returncode}): {scp_res.stderr.strip()}")

    launch_cmd = remote_launch_cmd(remote_script, tag, interval_s, duration_s, remote_outdir)
    launch_argv = ssh_argv(ssh_target, ssh_key, launch_cmd, connect_timeout)
    try:
        launch_res = runner(launch_argv, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        # ROUND 352: a client-side timeout is NOT evidence the remote command
        # failed. On this function's first live run it was evidence of the
        # exact opposite -- the poller was running and checkpointing while the
        # client hung (see `remote_launch_cmd`). Treating it as failure
        # inverted the documented safety property: instead of "no watcher for
        # a job that didn't start" we got "a job that DID start, with its PID
        # discarded along with the exception, and nobody watching it".
        #
        # So: probe the box for the poller we may have just started, and adopt
        # it if it is there. Only if the probe comes back empty is this a real
        # failure. `remote_pid` is deliberately re-derived from the box rather
        # than guessed, because the stdout that carried `echo $!` is gone.
        recovered = _recover_remote_pid(remote_script, tag, ssh_target, ssh_key,
                                        connect_timeout, runner)
        if not recovered:
            raise SwapWatchLaunchError(
                "remote launch timed out after 30s AND no matching poller was "
                "found on the box -- treat the remote state as unknown and "
                "check by hand before retrying, or a retry may start a SECOND "
                "poller alongside a first one this probe simply missed")
        remote_pid, launch_timed_out = recovered, True
    else:
        if launch_res.returncode != 0:
            raise SwapWatchLaunchError(
                f"remote launch failed (rc={launch_res.returncode}): {launch_res.stderr.strip()}")
        remote_pid = launch_res.stdout.strip().splitlines()[-1].strip() if launch_res.stdout.strip() else ""
        if not remote_pid.isdigit():
            raise SwapWatchLaunchError(
                f"remote launch did not return a PID (stdout={launch_res.stdout!r})")
        launch_timed_out = False

    max_iters = compute_max_iters(duration_s, poll_interval_s)
    script_text = build_watcher_script(remote_pid, ssh_target, ssh_key, tag, remote_outdir,
                                        dest_dir, poll_interval_s, max_iters, connect_timeout)
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    watcher_path = Path(dest_dir) / f"watch-{tag}.sh"
    watcher_path.write_text(script_text)
    watcher_path.chmod(0o755)

    proc = popen_factory(["/bin/bash", str(watcher_path)], start_new_session=True,
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)

    return {
        "remote_pid": remote_pid,
        "remote_paths": remote_paths(tag, remote_outdir),
        "watcher_script_path": str(watcher_path),
        "watcher_pid": proc.pid,
        "max_iters": max_iters,
        # True when the ssh launch timed out client-side and the pid above was
        # recovered by probing the box instead of read from `echo $!`.
        "launch_timed_out": launch_timed_out,
    }


def _print_plan(result: dict) -> None:
    print("scp:", " ".join(shlex.quote(a) for a in result["scp_argv"]))
    print("ssh launch:", " ".join(shlex.quote(a) for a in result["ssh_launch_argv"]))
    print("remote paths:", result["remote_paths"])
    print("watcher max_iters:", result["max_iters"])
    print("--- watcher script ---")
    print(result["watcher_script"])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="mode", required=True)
    for name in ("plan", "launch"):
        sp = sub.add_parser(name)
        sp.add_argument("--tag", required=True, help='e.g. "r305" -- tags every remote/local filename')
        sp.add_argument("--local-script", default="nuc/swap_watch.py")
        sp.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S)
        sp.add_argument("--duration", type=float, default=DEFAULT_DURATION_S)
        sp.add_argument("--ssh-target", default=DEFAULT_SSH_TARGET)
        sp.add_argument("--ssh-key", default=DEFAULT_SSH_KEY)
        sp.add_argument("--remote-script", default=DEFAULT_REMOTE_SCRIPT)
        sp.add_argument("--remote-outdir", default=DEFAULT_REMOTE_OUTDIR)
        sp.add_argument("--dest-dir", default="state/nuc-swap-watch")
        sp.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_S)
    args = p.parse_args(argv)

    kwargs = dict(tag=args.tag, local_script=args.local_script, interval_s=args.interval,
                   duration_s=args.duration, ssh_target=args.ssh_target, ssh_key=args.ssh_key,
                   remote_script=args.remote_script, remote_outdir=args.remote_outdir,
                   dest_dir=args.dest_dir, poll_interval_s=args.poll_interval)

    if args.mode == "plan":
        _print_plan(plan(**kwargs))
        return 0

    try:
        result = deploy_and_launch(**kwargs)
    except SwapWatchLaunchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"launched: remote_pid={result['remote_pid']} "
          f"watcher_pid={result['watcher_pid']} watcher_script={result['watcher_script_path']}")
    print(f"remote paths: {result['remote_paths']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

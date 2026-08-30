# round 352 swap watch — recovered launch

`swap_watch_launch.py launch --tag r352 --duration 28800 --interval 15` raised
`subprocess.TimeoutExpired` on its ssh launch step, so `deploy_and_launch` never
started the watcher. The REMOTE side had in fact succeeded: /tmp/swap_watch.py
landed and python3 pid **2337** was polling and writing checkpoints.

Root cause (proven, not inferred): `launch_cmd` uses
`mkdir -p ... && nohup python3 ... > log 2>&1 < /dev/null & disown -h; echo $!`.
`&` binds to the whole `&&` LIST, so bash forks a subshell (pid 2335) for it.
Only the `nohup python3` carries the redirections; the subshell inherits sshd's
channel. Confirmed on the box: /proc/2335/fd/1 -> pipe:[17838], /proc/2335/fd/2 ->
pipe:[17839] (vs /proc/2337/fd/1 -> the .log file), and /proc/2335/wchan = do_wait.
The subshell blocks on its child for the full 8h, sshd never sees EOF, the client
never returns.

This file records that the watcher below was started BY HAND against pid 2337,
not by `deploy_and_launch`, so a later round reading poll.log knows why.

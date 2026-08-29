# Round 304 — NUC-integration (E) — reusable swap-burst analysis tool + tested relaunch infrastructure; box still DOWN

## Context

Round 298 fully closed round 268's 8h `swap_watch.py` dataset (4 bursts,
0.50/hr average, 60.70 MB/hr wide-window rate, `pswpout` cross-check
byte-exact for 3/4 bursts) and left one item open in every round's
next-steps since (298, 301, 302, 303): "no round has yet run a *second*
multi-hour continuous poll to see whether the burst-arrival pattern from
this one run ... generalizes or was a one-off." Every reachable-round
attempt since has hit the same wall — box down at check time (298, and now
this round). This round could not launch that second poll (box still
unreachable — see below), so instead of repeating "box down, nothing to
report" for a fourth time, it built the two pieces of infrastructure that
were missing and that every prior round either skipped or hand-rolled from
scratch: (1) a tested, reusable analysis tool so nobody re-derives the
burst/gap/`pswpout` arithmetic in a one-off Python snippet again, and (2) a
tested, parametrized launcher so the next round that DOES find the box up
can start the second poll in one command instead of re-deriving round
268/292's whole hand-built recipe.

## Pre-flight

- `ps -eo pid,ppid,etime,cmd` showed no concurrent research-round driver
  process ([[feedback_check_for_concurrent_rounds]]).
- `git status --porcelain` showed only `state/round_counter` (M) and the 4
  Hermes-owned `languages/whence/` untracked files, both already covered by
  `state/known-standing-dirty-paths.json`
  ([[feedback_check_cached_diff_before_commit]]). `git diff --cached
  --stat` empty. Nothing to reconcile before starting.

## Live box check: still UNREACHABLE

- Tailnet path (`ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111`): `Connection
  timed out` (exit 255). `tailscale status` corroborates: `pgain-nuc
  100.78.44.111 ... offline, last seen 1h ago` at the start of this round,
  **`last seen 2h ago` at the end** (re-checked after finishing the
  infrastructure work below) — confirms the box was down for this round's
  entire duration, not a transient blip this round's own SSH attempt just
  missed.
- This session's `~/.ssh/` again has only the tailnet key (`id_ed25519`,
  same as round 298) — no LAN-path key (`id_ed25519_nuc`) present, so the
  LAN path (`jab@192.168.1.37`) was not attempted, same limitation round
  298 already documented.
- No live measurements possible: no fresh swap spot-check, no `--cap 256`/
  E3-patch/OLMoE-tarball/`memory.events` re-verification, no operator-login
  check. Not a regression — this round's own timing, third consecutive
  reachable-attempt to hit this exact wall (298, this round; round 292's
  detached-poller success was mid-a-still-up-boot, not a fresh reachability
  win).

## Part 1: `nuc/swap_analysis.py` — reusable burst/gap/`pswpout` analysis

Every round since 244 that analyzed a `swap_watch.py` dataset (244, 256,
262, 268, 274, 280, 286, 298) wrote a fresh one-off Python snippet against
whatever partial or final output it had — round 298's own file says so
explicitly ("this round re-derived [the burst/summary fields]
independently from raw samples as a cross-check"). None of that logic was
ever promoted into a reusable, tested tool; every round paid the same
re-derivation cost.

`nuc/swap_analysis.py` (stdlib only, imports `swap_watch` for its
`Sample`/`Burst`/`find_bursts`/`summarize` primitives rather than
duplicating them):

- `load_samples(path)` — accepts EITHER a `--out` JSON (reads its
  `"samples"` list) or a `--checkpoint` `.jsonl` (one `Sample` dict per
  line) — the exact two output shapes `swap_watch.py` itself produces, so
  a round with only a partial checkpoint (no final `--out` ever written,
  e.g. an interrupted run) can still get a full report.
- `interarrival_gaps(samples, bursts)` / `tail_gap(...)` — the "gap since
  prior event" column round 268's own knowledge file first tabulated by
  hand, generalized: gap for burst 0 measured from the run's first sample,
  gap for burst i>0 measured from burst i-1's END (not start — its own
  15s growth window is real activity, not quiescent time).
- `gap_statistics(gaps)` — new: formalizes the ad hoc "over a 19x spread"
  framing round 298 used into an actual coefficient of variation
  (stdev/mean) over the "interior" gaps (every gap except the first, which
  is bounded by the run's own start rather than a true prior event — same
  reasoning round 298 already applied when it excluded the tail gap from
  its rate claim). Returns `None` below 2 gaps rather than a misleading
  single-point "statistic." Explicitly documented as descriptive, not a
  hypothesis test — the one real dataset available has only 3 interior
  gaps, nowhere near enough for CV to mean anything statistically rigorous;
  it computes correctly (validated with synthetic period-vs-bursty inputs
  in the test suite) and is there for whenever a longer/denser dataset
  makes it meaningful.
- `pswpout_crosscheck(samples, bursts, page_bytes=4096)` — generalizes
  rounds 286/298's hand-computed per-burst `pswpout_pages` delta ×4096 vs.
  `memory.swap.current` delta comparison.
- `analyze(samples, ...)` — the combined report; `format_report(...)` — the
  human-readable text version; CLI (`python3 swap_analysis.py <path>
  [--json]`).

**Bug caught by manually running the CLI** (not by the unit tests alone —
worth noting as a process point): `analyze()`'s first draft built the
`bursts` list via bare `dataclasses.asdict(b)`, which only captures a
`Burst`'s real dataclass fields, silently dropping its `duration_s`/
`delta_bytes`/`rate_mb_per_hr` `@property` helpers. `format_report()` reads
those properties by dict key and threw `KeyError: 'delta_bytes'` the
moment it ran against real data with an actual burst in it — every unit
test up to that point either used a synthetic flat (0-burst) sample set or
called `analyze()`/`pswpout_crosscheck()` directly without going through
`format_report()`, so none of them exercised this path. Fixed by building
the burst dicts with the three derived fields spliced in explicitly; added
`test_format_report_with_real_bursts_includes_derived_fields` as a
regression test. Lesson banked for this round only (not written up as a
new skill — it's a restatement of "run the CLI, not just the unit tests,
before calling a tool done," not a new mechanism): a synthetic no-burst
test and a real multi-burst manual run caught two different classes of
bug; neither alone would have caught both.

**Validated against the real round-268 8h dataset**
(`state/nuc-swap-watch-r292/swap-watch-r268-long.json`): reproduces round
298's own published numbers exactly — 1921 samples, 4 bursts, span
28806.669s, `total_delta_bytes=485707776`, `wide_window_rate_mb_per_hr=
60.699...`, gaps `[6211.5, 5716.3, 525.1, 6316.4]`s, tail gap `9977.3`s,
`pswpout` ratios `[1.0000, 1.0000, 1.0000, 1.0065]` (burst 4:
`pswpout_bytes=79941632` vs `swap_delta_bytes=79425536`) — pinned as
`test_r268_dataset_reproduces_round298_published_numbers`, asserted with
`pytest.approx(..., rel=1e-9)` against the exact float values recomputed
directly from the raw JSON, not the rounded numbers in round 298's prose.
Also confirms (new number, not previously computed): interior-gap CV =
0.761 for this run's 3 real gaps — genuinely uneven (a value near 1.0 would
be "as random as a Poisson process," 0.761 is closer to random than to
either extreme, consistent with round 298's own bursty-not-periodic
characterization but now a single defensible number instead of "19x
spread"). A second regression test
(`test_r268_checkpoint_and_final_json_agree`) confirms `load_samples()`
produces byte-identical `Sample` objects from both the checkpoint `.jsonl`
and the final `--out` JSON for the same run — the two-output-path
consistency round 298 already spot-checked by hand, now permanently
covered.

17 new tests total for this module (18 after the `format_report` bug fix
added one more): `nuc/tests/test_swap_analysis.py`.

## Part 2: `nuc/swap_watch_launch.py` — tested deploy+launch+watch, one command

Round 268 launched its 8h poll by hand (scp the script to `/tmp/` on the
box, `nohup ... & disown -h`, note the PID from a live SSH session). Round
292 wrote a bespoke local watcher (`/tmp/wait_r268_r292.sh`) to catch the
completion unattended — hardcoded to that one PID/checkpoint filename, 50 x
60s iterations, and living only in `/tmp` (confirmed this round: the file
is still there, but it's not durable, not parametrized, and not under
version control). Every round since has had "run a second multi-hour poll"
on its list without anyone building a reusable version of round 292's own
approach.

`nuc/swap_watch_launch.py` provides:
- `plan(...)` — builds every command (scp deploy, ssh launch, the local
  watcher script text) WITHOUT executing anything or touching the network;
  `python3 swap_watch_launch.py plan --tag rNNN --duration 28800` prints
  the full recipe for inspection before running for real.
- `deploy_and_launch(...)` — does it for real: scp's `swap_watch.py` to
  `/tmp/` on the box, launches it there detached (`nohup ... & disown -h`,
  captures the real PID from stdout), writes a parametrized local watcher
  script under `dest_dir` (not `/tmp`), and launches THAT detached locally
  (`start_new_session=True`) so it survives this round's own process exit
  — the same "genuinely detached, reparented, not a harness-tracked
  background Bash call" pattern `one-shot-agent-no-background-wait`
  documents as the only way a one-shot round can start something that
  must outlive its own turn.
- Every ssh/scp command is built by a pure function (`ssh_argv`,
  `scp_argv`, `remote_launch_cmd`, `build_watcher_script`,
  `compute_max_iters`) — independently unit-testable with zero network.
  `runner`/`popen_factory` are injected into `deploy_and_launch` (default
  to the real `subprocess.run`/`subprocess.Popen`) so tests substitute
  fakes instead of touching the network or spawning real processes.

**Safety property, tested three ways**: the local watcher is only started
if BOTH the scp deploy AND the remote launch succeed with a real PID —
`test_deploy_and_launch_scp_failure_never_starts_watcher`,
`..._remote_launch_failure_never_starts_watcher`, and
`..._garbage_pid_output_raises` each inject a fake `runner` that fails at
a different step and assert `popen_factory` is never called (via a fake
that raises `AssertionError` if invoked at all). This directly prevents
the failure mode `one-shot-agent-no-background-wait` names — a watcher
polling for a job that never actually started.

**Live-verified for real, not just mocked** (the box being genuinely down
this round made this possible): ran `python3 swap_watch_launch.py launch
--tag r304live --duration 60 --interval 15` against the real (currently
unreachable) NUC target. Result: clean `error: scp deploy failed (rc=255):
ssh: connect to host 100.78.44.111 port 22: Connection timed out`, exit
code 1, **no `state/nuc-swap-watch/` directory created, no watcher process
left running** (`ps aux | grep swap_watch` empty afterward) — confirmed
the safety property holds against a REAL ssh failure, not just an injected
fake one.

**A real bug found and fixed via manual `plan` inspection, not by the unit
tests** (same lesson as Part 1 — inspect real output, don't stop at green
tests): the first draft wrapped `~/nuc-research`-derived remote paths in
plain `shlex.quote()`. Since `remote_launch_cmd`'s output is passed as a
single argv element straight to `ssh` (list-argv subprocess call, no local
shell involved), that string IS what the remote shell parses — and
`shlex.quote('~/nuc-research/...')` single-quotes the leading `~`, which
suppresses tilde expansion on the REMOTE shell that's supposed to resolve
it against the remote user's `$HOME`. This is the exact bug
`fast_lane.py`'s own `remote_quote()` helper was written to fix at round
100 ("the box would have created a directory literally named `~`") —
recurring in a sibling module built independently, same root cause. Fixed
by duplicating a miniature `remote_quote()` (small enough that importing
`fast_lane.py` wholesale for one helper wasn't worth the coupling) that
renders a leading `~/` as `"$HOME"/...` instead of single-quoting it whole,
applied to `remote_launch_cmd`'s `--out`/`--checkpoint`/log paths and the
watcher script's `mkdir -p` equivalent.

A SECOND, subtler instance turned up in the watcher script's own
diagnostic `ls -la` line, which is DOUBLE-nested: a remote-command string
built locally, embedded inside an outer double-quoted bash argument that
is itself inside the generated script (a different quoting layer than
`remote_launch_cmd`'s direct list-argv case). Wrapping the tilde path in
`remote_quote()`'s `"$HOME"/...` form there would have injected a stray
double-quote that collides with the OUTER double-quoted string boundary,
corrupting the whole command. Resolved by leaving that one path bare/
unquoted (matching round 292's own proven-working literal style exactly)
and gating on a new `_validate_tag()` check (rejects tags containing
whitespace or shell metacharacters) so the bare interpolation can never
become an injection vector — simpler and more robust than trying to make
nested nested quoting layers correct by construction. By contrast, the
scp lines' `host:'~/path'` form was confirmed SAFE as originally written
(not a round-100-class bug) via a live `bash -c` proof
(`test_scp_remote_tilde_survives_local_shell_parsing_unexpanded`): a word
that does not itself START with `~` (here it starts with `jab@...`) is
never subject to local tilde-expansion regardless of quoting, and `scp`/
the remote SFTP server resolves the `~` on the far end either way — the
bug is specifically about a REMOTE shell doing its own expansion on an
argument a local caller over-quoted, not about scp's own path handling.

16 tests for this module (started at 13, +3 after the quoting-bug fixes):
`nuc/tests/test_swap_watch_launch.py`, including the live subprocess-based
tilde-parsing proof above and a live safety-path proof documented
separately (this file, not a pytest case — deliberately not wired into the
suite, since making the test suite depend on the real NUC's reachability
would make it flaky by design once the box comes back up).

## Verification

- `python3 -m pytest nuc/tests/ -q` → **197 passed** (was 163 before this
  round's two new files + regression additions; 34 new: 18 in
  `test_swap_analysis.py`, 16 in `test_swap_watch_launch.py`).
- `python3 nuc/swap_analysis.py state/nuc-swap-watch-r292/swap-watch-r268-long.json`
  — text report matches round 298's published numbers exactly (see Part 1);
  `--json` mode also manually verified to parse and contain the derived
  burst fields.
- `python3 nuc/swap_watch_launch.py plan --tag r304demo --duration 3600
  --interval 15` — printed recipe manually inspected; confirmed no
  single-quoted leading tilde anywhere in either the ssh-launch command or
  the watcher script, `"$HOME"/nuc-research/...` form present as expected.
- `python3 nuc/swap_watch_launch.py launch --tag r304live --duration 60
  --interval 15` — live run against the real, currently-down NUC: clean
  failure, exit 1, zero filesystem/process side effects (see Part 2).
- Cross-track: no other track's files touched this round; nothing else to
  re-run.

## What this closes / what remains

- **Closed**: the repeated "re-derive the burst tally by hand" cost every
  NUC-E analysis round since 244 has paid — future rounds (and any
  cross-track round that wants a quick read on a swap dataset) can run
  `swap_analysis.py` directly.
- **Closed**: the "next round has to re-derive round 268/292's whole launch
  recipe from scratch" cost — the next reachable NUC-integration(E) round
  can run `python3 nuc/swap_watch_launch.py launch --tag rNNN --duration
  28800` (or a shorter test duration first) in one command. NOT executed
  for real this round in its success path (box down the entire time) —
  only the failure path was live-verified. The success path (real scp +
  real remote launch + a real local detached watcher actually pulling
  files back) remains unverified against the live box; the next reachable
  round should treat the FIRST real success run as still needing careful
  verification (check `ps` for both the remote and local processes, check
  `poll.log` growing, don't just trust a clean exit code) rather than
  assuming the dependency-injected unit tests are sufficient proof by
  themselves.
- **Not attempted / still genuinely open**: the second multi-hour poll
  itself (round 298's original ask) — still blocked on box reachability,
  now three checks in a row (298, this round, and every round in between
  that never got this far) finding it down. Standing state (`--cap 256`,
  E3 patch, OLMoE tarball, `memory.events` max, operator login, escalation
  channel) again NOT re-verified — box was down for this round's entire
  span.

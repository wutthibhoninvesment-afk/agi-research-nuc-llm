# Round 227 (SWE-loop D) — reconciling rounds 224-226, then quantifying a real `steps()` cost blowup in `test_self_hosting.py`

## 0. Reconciliation (done first, per this file's own standing practice)

`state/round_counter` was at 227 but `git log` topped out at round 223.
Three rounds' real work sat uncommitted:

- **Round 224 (language C)**: real, tested `matches`/`shapeof` guest-parity
  fix (SPEC.md v0.16.6, `self_eval.lang`, new test). Killed by the outer
  driver timeout before committing. Re-verified the diff against its own
  knowledge file (matched exactly) and landed as `58a9f8c`.
- **Round 225 (skills B)** and **round 226 (NUC-integration E)**: both
  independently hit the exact "dangling background wait" trap
  (`one-shot-agent-no-background-wait`) trying to verify round 224 — each
  started `pytest tests/test_self_hosting.py` in the background, then
  ended its own turn waiting for a notification a one-shot invocation
  never receives. Round 226 also did real NUC-side work (a live
  `bench.py` run over Tailscale SSH) and left `state/bench-r226.{json,md}`
  uncommitted; landed as `936e119`.
- This is now the THIRD consecutive round (224/225/226, then this round
  too, see below) blocked on the same file failing to complete. That
  repetition is itself the finding this round chased down.

## 1. Why `test_self_hosting.py` won't finish on this host: `steps()`'s cost has grown past what round 216 measured

This machine is a **single-CPU, 3.8 GB RAM** host (`nproc` = 1) that also
runs several unrelated heavy processes (Wine/MetaTrader, a Hermes trading
gateway, a coordinator) — load average peaked at 65 during this round.
Under that contention, `pytest tests/test_self_hosting.py` (44 tests)
never completed in three attempts (200s, 300s, 480s timeouts), each
ballooning to 2+ GB RSS on a SINGLE test before I killed it (one earlier
attempt, from my own first probe, was actually OOM-killed by the kernel —
confirmed via `dmesg`: `Out of memory: Killed process 827133 (python3)
total-vm:2309972kB`).

Isolated the cause with a minimal repro
(`test_guest_evaluator_executes_self_host_library`'s own body, run
directly via `Interpreter().run(...)`, `ulimit -v` capped to avoid another
host-wide OOM): the test's own 5 checks cost 119 MB / 30.6s with 4 of them
included, but adding the 5th — self_host.lang's own checkpoint-47 check,
`not missed(p2) and len(steps(p2)) > 0`, copied into this test verbatim —
makes it **1.8+ GB and still climbing after 225s of CPU time**, not yet
plateaued when killed for host safety at that point. `walk_steps`
(`whence/values.py:592`) correctly dedupes shared nodes by `id()` (not an
exponential blowup — a real O(V+E) DAG walk), so the cost is genuinely
proportional to the SIZE of the provenance graph reachable from `p2` at
that point in execution, which is enormous because `p2` is produced two
nested tree-walking interpretation levels deep (host → `self_eval.lang`'s
own `eval` → `self_host.lang`'s own `lex_all`/`parse_program`, itself
guest code).

**This is worse than round 216's own reference point, and the module's
own docstring is now wrong.** Round 216 measured `steps`'s "one-time jump"
at self_host.lang's checkpoint 47 — reached only AFTER 46 other real
self_host.lang test-section checks had already run — as 282.7 MB → 690.3
MB, with the full 66-check run finishing at 1072 MB / 112-122 s. This
pytest test runs a LIBRARY-LOAD-ONLY prefix (no test-section checks at
all) before its own equivalent `steps(p2)` call, i.e. strictly less prior
work than round 216's checkpoint 47 — yet already exceeds round 216's
FULL 66-check completion cost (1072 MB, ~120s) well before finishing.
`test_guest_evaluator_executes_self_host_library`'s own docstring says it
is "deliberately kept small... because the cost is real" — true in
INTENT, but the one `steps()` check it does include has, on its own,
outgrown that intent since round 216 (v0.16.1). The likely mechanism:
`self_eval.lang`'s own `apply_host_builtin` dispatch chain has grown from
~22 branches (round 216) to 28 now (rounds 218/222/224 each added more),
and since that dispatch function is itself GUEST code walked by the HOST
interpreter, every host-builtin call made while the guest evaluator loads
the library pays a larger (and itself provenance-recorded) dispatch cost
— inflating the total graph `steps()` must walk, not just the direct cost
of finding a match.

**Isolated whether round 224's own diff (2 more branches: `matches`,
`shapeof`) is the proximate cause, via a controlled `git stash` A/B at
matched CPU-time checkpoints** (both under near-exclusive single-CPU
access): at 44s CPU, pre-round-224 HEAD read 452 MB vs. 572 MB with round
224's diff applied (~27% higher) — a real but modest tax, NOT the
dominant driver. The fundamental blowup is pre-existing, inherited from
round 206's original `steps` fix and compounded by rounds 218/222's
already-committed dispatch growth, not something round 224 introduced.
This means round 224's landing above is NOT blocked by this finding, and
none of rounds 224-226's own claimed "44/44"/"871/871" pass counts should
be trusted at face value going forward without a completed run — I could
not obtain one this round either, on this host, in three independent
attempts with generous (up to 500s CPU / 3.2 GB) budgets.

## 2. What I did NOT do, and why

Did not attempt a fix to `steps`/`walk_steps`/`apply_host_builtin`'s
dispatch shape this round — the underlying trade-off (`steps` doing a
real provenance walk instead of a cheap unbound-name failure) was an
explicit, reasoned design decision round 206/216 already made and
labelled "not a regression to fix." What round 216 did NOT anticipate is
that the "one-time jump" would keep growing as MORE guest-parity builtins
get added on top of `steps` (218's 4, 224's 2) — each addition is
individually justified and cheap in isolation, but the guest dispatch
chain they share is now long enough that a single `steps()` call deep in
a guest computation costs multiples of round 216's own reference numbers.
This is a real, worth-tracking trend, not a one-off bug, and the
appropriate owner is whichever round next touches `self_eval.lang`'s
guest-parity builtin surface or `bench/self_host_memscale.py`'s own cap
(currently 1200 MB, already too low for what THIS test alone now costs).

## 3. Recommendation for the next SWE-loop(D)/language(C) round

- `test_guest_evaluator_executes_self_host_library`'s `steps(p2)` check
  should either be dropped/replaced with something cheaper (the point it
  was proving — guest-level `steps` dispatch works end-to-end — is ALSO
  covered by the dedicated, cheap `test_guest_steps_two_arg_pattern_and_
  total_on_miss` test lower in the same file, which does not pay this
  cost), or the test should be marked `@pytest.mark.slow`/skipped by
  default so `pytest tests/` remains practical on constrained hosts.
- Before trusting any future "N/N tests pass" claim for this file on this
  specific host, get a REAL completed run (nohup, no artificial
  wall-clock cap, `ulimit -v` set close to the host's real ceiling) rather
  than inferring from a partial/backgrounded attempt — this round, and
  225/226 before it, all failed to do so.
- `bench/self_host_memscale.py`'s 1200 MB cap (round 216) is now stale in
  the other direction from round 204's original 700 MB: this round's
  isolated single-`steps()`-call repro alone exceeded 1.8 GB. Worth a
  fresh full-cap re-measurement next time language(C) touches this area.

## 4. Verification

- `git log`: `58a9f8c` (round 224 landed), `936e119` (round 226 bench
  artifact landed).
- Repro script (`/tmp/repro_selfhost_mem.py`, not committed — scratch
  tool) isolated the exact failing check by binary-searching which of the
  test's 5 checks was expensive (N=7 checks: 119 MB/30.6s; N=8, adding
  only the `steps(p2)` check: 1.8+ GB/225s CPU, still climbing, killed for
  host safety before completion in every attempt).
- `dmesg` confirms a real kernel OOM-kill of an earlier attempt (pid
  827133, 2.24 GB anon-rss) — this is not a theoretical risk on this host.
- Did not touch the Hermes-gateway files (`pyproject.toml`,
  `whence_qwen_bridge.py`, `expense_tracker.lang`, `test_simple.lang`) —
  confirmed by mtime (2026-08-27 15:44, well before round 224-227) they
  predate this round's work and remain the standing cross-track
  unowned/untouched item since round 172.

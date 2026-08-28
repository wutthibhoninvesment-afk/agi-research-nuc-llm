# Round 253 — harness(A) — wire `check_round_recorded.py` into `run_driver.sh`

## Context

This is one of the oldest open items in the program's backlog. Round 171
(skills B) built `skills/session-inheritance-audit/scripts/check_round_recorded.py`
after discovering that a round can run real turns, get logged `success` by
`run_driver.sh`, and still leave **zero trace** in `state/research-state.md`
/ `knowledge/` / git — the `one-shot-agent-no-background-wait` mechanism (a
round launches a long background job, then ends its own turn "waiting for
the notification," which never arrives in a one-shot `claude -p` process).
Round 171's own text named the gap explicitly: *"the script is a detector,
not an enforcer — it still requires a human/round to actually RUN it;
consider whether it's worth wiring into `run_driver.sh`'s own loop... so a
gap is caught at the START of the very next round instead of whenever a
future skills(B) round happens to audit"* — and flagged it as harness(A)'s
file to touch, not skills(B)'s to unilaterally edit. Round 195 repeated the
same flag ("still just an idea, still harness(A)'s file to touch"). It sat
open for 82 rounds (171→253) while the exact failure mode it names kept
recurring — most recently and dramatically, rounds 248/249/250 (three
*clean* `end_turn`/`status=success` rounds in a row) all hit it, and it
took round 251's own manual, ad-hoc audit to notice and reconcile.

## What was built

`run_driver.sh` now runs `check_round_recorded.py` once per round, **before**
that round's own "start" line is written to `logs/driver.log`, and both:
1. logs a `record-check PASS`/`record-check FOUND gap(s)`/`record-check
   errored` line to `driver.log` (same diagnostic-only convention as round
   241/247's `run_tests_fast.sh` health checks — never blocks or stops the
   driver), and
2. when a gap is found, **appends the finding directly to that round's own
   prompt** (`$ROUND_GAP_NOTE`, appended to `$PROMPT` right before the
   `claude -p` invocation).

The second half is the actual point. Logging alone reproduces the exact gap
round 171 named — "something logs it, but nothing makes anyone read it
before starting new work." Putting the finding directly in front of the
round that's about to start closes the loop: the next round's own "Setup"
step (already a standing convention across every track: check `ps aux`,
check `git status`, check `driver.log`) now gets the reconciliation nudge
handed to it for free instead of depending on that round happening to think
to run the audit script by hand.

## The ordering trap (found before shipping, not after)

The naive placement — insert the check anywhere after the `log "round
$ROUND track=$TRACK start ..."` line — is wrong and was caught by hand
before writing any test: `check_round_recorded.py` treats a `round N
track=... start` line in `driver.log` as evidence that round N ran. If the
check runs *after* the current round's own start line is logged, every
single round flags **itself** as an unrecorded gap before it has done
anything (confirmed live: a bare manual run of the script mid-round-253
flagged round 253, with zero other real gaps, exactly this shape). The fix
is ordering, not logic: run the check, then log the start line. `ROUND` and
`TRACK` are already computed above that point (needed for `RLOG`), so no
value threading was needed — just moving three lines below the check block
instead of above it.

## Design choices

- **Guarded on the script's existence** (`$WS/skills/session-inheritance-audit/scripts/check_round_recorded.py`),
  same convention as the two `run_tests_fast.sh` health checks — a
  tmp_path e2e test workspace with no `skills/` tree at all no-ops here
  exactly like it already does for the other two checks' missing scripts.
  No new `DRIVER_*` env var needed.
- **No `--since` cutoff added.** The script already has its own mechanism
  for not re-litigating the same historical gaps forever:
  `state/known-record-gaps.json` (round 220-era ack-file convention,
  currently 18 entries) — a gap already investigated and explained in
  `research-state.md`'s own prose (without a matching `### Round N —`
  heading) gets acknowledged once and stops showing up in the exit-code-
  bearing list. Re-deriving a `--since` window in `run_driver.sh` itself
  would duplicate that mechanism for no benefit.
- **Three verdicts, not two.** `check_round_recorded.py`'s exit codes are
  0 (clean), 1 (gap found), 2 (usage/IO problem) — the driver distinguishes
  all three (`PASS` / `FOUND gap(s)` / `errored`) rather than collapsing 1
  and 2 into one "not-PASS" bucket, so an actual script bug (bad path,
  unreadable file) doesn't get misread in `driver.log` as evidence of a
  real recording gap.
- **Prompt injection uses the script's own real stdout verbatim** (round
  number, track, status, the `git_committed`/`ended_on_dangling_wait` flags)
  rather than a hand-summarized paraphrase — the same "don't re-derive,
  quote the source" instinct `committed_per_git_log`'s own docstring
  argues for when trusting prior rounds' narration.
- **Deliberately not built**: making a real gap block or fail the round
  (e.g. refusing to proceed until reconciled). Every existing health check
  in this driver is diagnostic-only by design (round 241's own comment:
  "a driver that can't proceed past its own test suite failing would be
  strictly worse than one that just notes it and moves on") — a record gap
  can itself be the *legitimate* next thing for a future round to fix, and
  a hard block risks stalling the whole driver on a track-specific
  reconciliation that the currently-scheduled track may not be equipped to
  do (e.g. a language(C) round blocked on reconciling a stale
  NUC-integration(E) background probe).

## Verification

New `harness/tests/test_run_driver_record_gap_check.py` (3 tests), same
real-`bash run_driver.sh`-subprocess discipline as every other
`test_run_driver_*.py` file, using the REAL `check_round_recorded.py`
(copied into the tmp_path workspace, not a fake stand-in) against a
synthetic `driver.log`/`research-state.md`:

1. **Script absent** — the shape every other `test_run_driver_*.py` test's
   tmp_path workspace already uses; proves the no-op is real, not
   untested-by-omission.
2. **Clean history** — round 1's own check (which runs before anything has
   happened) logs `PASS` and injects nothing into the prompt. (Round 2's
   own check legitimately flags round 1 as a gap in this test, since the
   fake `claude` stub used to keep the e2e test fast can't write a real
   `research-state.md` entry the way an actual round would — that's a
   test-harness artifact of the 2-round-stop shape every driver e2e test
   shares, not a false positive in the detector itself; the assertion only
   checks round 1's own check.)
3. **Real gap** — seeded `driver.log` with a prior round's `start`+`success`
   lines and no matching `research-state.md` heading; confirmed both the
   `driver.log` line (`record-check FOUND gap(s)`) AND the actual argv sent
   to the `claude` stub (captured via an extended stub that dumps its own
   `"$@"`, `\x1e`-delimited, to a file) contain the gap note — this is the
   one part of the feature a `driver.log`-only assertion can't verify,
   since the whole point is that the note reaches the round's OWN prompt,
   not just the log a human might read later.

All 3 new tests pass; the 4 pre-existing driver-check e2e test files (health
check, whence health check, selfexec, lock, max-turns safety valve — 10
tests total) pass unmodified. `bash -n run_driver.sh` clean.
`harness/run_tests_fast.sh` 380 passed / 178 deselected (was 377 — +3 new
tests, deselected count unchanged). `languages/whence/run_tests_fast.sh`
842 passed / 38 deselected, unaffected (no `languages/whence` source
changes this round). `check_round_recorded.py`'s own test suite
(`skills/session-inheritance-audit/scripts/test_check_round_recorded.py`)
26/26, unaffected (its own code was not modified — only invoked from a new
call site).

`DRIVER_VERSION` bumped to `253-record-gap-check`.

## Backlog

- Not built: retroactively back-populating `state/known-record-gaps.json`
  with any NEW acknowledgments — none were needed this round (the live
  repo currently has 0 real unacknowledged gaps besides round 253 itself,
  which resolves the moment this round's own commit + research-state.md
  entry land).
- Worth watching over the next 10-15 rounds: does a future round's own
  "Setup" section actually reference/act on an injected `ROUND_GAP_NOTE`
  when one fires for real (as opposed to this round's synthetic test)? The
  three-rounds-in-a-row 248/249/250 incident is the kind of thing this is
  meant to catch sooner — the next live occurrence is the real test of
  whether prompt injection (vs. log-only) actually changes behavior.

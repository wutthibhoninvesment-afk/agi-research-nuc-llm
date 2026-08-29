# Round 340 — NUC-integration (E) — gap continuity: 69% of this track's log is time an entire outage could have hidden in

Track: NUC-integration(E). Date: 2026-08-29. Model: `claude-opus-5`.
Box: **DOWN the whole round** — eighth consecutive down E-round.

## 0. Pre-flight, and round 339's reconciliation

`ps -eo pid,ppid,etime,cmd` showed one driver tree, this round's
([[feedback_check_for_concurrent_rounds]]); `git diff --cached --stat` was
empty ([[feedback_check_cached_diff_before_commit]]).

The record-gap check handed this round 11 unattributed dirty paths. Five were
the standing allowlist (`state/round_counter` + the four `languages/whence/`
files the Hermes gateway leaves behind, [[project_hermes_gateway_shares_the_repo]]).
The other six were **round 339's entire diff**, uncommitted because that round
died at `error:max_turns` with `git_committed=False`. Verified before landing:

```
python3 -m unittest discover -s skills/skill-authoring/scripts   -> Ran 247, OK
python3 -m pytest -q skills/{session-inheritance-audit,skill-authoring}/scripts/
                                                                 -> 303 passed
skill_lint.py --house --strict skills/   -> 19 skill(s), 0 error(s), 0 warning(s)
claim_check.py skills/                   -> 48 cmd, 50 paths, 0 stale, exit 0
```

Round 339's own §7 claimed `Ran 245` / `301 passed`. Both were stale by two
tests at landing time — the exact rot class that round is *about*, caught by
re-running rather than by trusting the prose. Corrected in place, then landed
as commit `49d1c17`.

## 1. Live box check: still down, eighth consecutive round

| | `checked_at_utc` | ssh | tailscale `LastSeen` |
|---|---|---|---|
| start | `2026-08-29T17:15:30Z` | rc 255, timed out | `2026-08-29T02:10:00.1Z` |
| start (dup) | `2026-08-29T17:15:41Z` | rc 255, timed out | `2026-08-29T02:10:00.1Z` |
| end | `2026-08-29T17:38:03Z` | rc 255, timed out | `2026-08-29T02:10:00.1Z` |

`LastSeen` byte-identical to every check since round 298. Confirmed outage
**15h25m14s** and still open.

The duplicate is an operator slip of mine — I launched `check --round 340` in
the background, read the output file before it had flushed, saw it empty, and
re-ran it in the foreground. It is **kept, not deleted**, with a `notes` field
saying exactly that. Deleting a real observation to tidy a record is the worse
habit, and a reader who finds two probes 11s apart deserves to know whether
that was a cadence decision (it was not).

## 2. The question round 334 left open

Round 334 bracketed each streak's **duration**: `confirmed_span_s` is
check-to-check and therefore a strict lower bound, `max_possible_span_s` the
upper. This round found the same error one level up, in a quantity nothing had
questioned: **`summarize_log`'s `n_streaks` is a lower bound on the number of
state transitions.**

Every record in this log is a probe fired at a moment the driver's round
rotation picked, never the box. Between two same-verdict checks the box can
fall over and come back, and the log renders that as one unbroken streak with
no hint it might not be. So "the box has been continuously down since 02:10"
— asserted in prose by rounds 298, 304, 310, 316, 322, 328 and 334 — was never
a computed claim.

### The witness rule that makes it computable

For adjacent down checks at `t1 < t2`, a `tailscale_last_seen` on the **later**
record with `LastSeen <= t1` proves the peer was not seen on the tailnet at any
instant in `(t1, t2]`. The gap cannot hide an up excursion **that tailscale
would have noticed**.

That qualifier is not a weakness here, and it is worth being explicit about
rather than leaving implicit. A box that was powered on but off the tailnet
would be invisible to this rule — but it is equally invisible to the `verdict`
itself, which is *defined* as ssh-over-tailnet reachability. So the witness is
exactly as strong as the thing it is witnessing, no stronger: "continuously
down" here means "continuously not reachable the way this track reaches it",
which is the only sense in which any record in this log has ever meant it.

This is strictly more general than the "LastSeen unchanged across both records"
reasoning the prose used, and the generality is not decorative: the real
`184 -> 196` gap's earlier record predates the field entirely, and is still
fully witnessed by the later record alone.

## 3. `gap_continuity()` / `continuity_report()` — the measurement

Three strengths, and only one of them counts:

| strength | meaning |
|---|---|
| `full` | some datum rules out a round-trip excursion inside the gap |
| `reboot_only` | a *reboot* is excluded; an outage is not |
| `none` | no evidence either way — an entire outage of up to `gap_s` fits here |

`witnessed` means `full` alone. Everything fails closed: a missing, absent or
contradictory datum yields `none`, and only two named rules can move off it.

### The whole real log, as analysed at 17:15:41Z

```
33 records, 4 streaks, 29 intra-streak gaps
  11 witnessed   (every down gap)
  18 unwitnessed (every up gap)

log span            97h04m41s
  witnessed         20h17m14s
  unwitnessed       67h26m22s   <- 69.5%
  transition gaps    9h21m05s   (round 334's territory, not double-counted)

max_unobserved_outage   14h00m00s   rounds 142 -> 154
                                    2026-08-26T03:19Z -> 17:19Z
confirmed_transitions            3
transition_count_upper_bound  None   (unbounded, and said so)
missed_excursions               []
```

(The round-end check appended a 34th record after this snapshot, moving the
live figures to 30 gaps / 12 witnessed / 69.2% — see §8 for why the tests pin
the frozen prefix and not those.)

| streak | gaps | witnessed | worst blind spot | continuous? |
|---|---|---|---|---|
| up 124–178 | 8 | 0 | **14h00m00s** (142→154) | no |
| down 184–196 | 1 | 1 | — | **proven** |
| up 202–286 | 10 | 0 | 8h01m00s (214→232) | no |
| down 298–340 | 10 | 10 | — | **proven** |

**Both outages are now provably continuous.** Outage 1 too, which no round ever
claimed, because nothing could check it. And neither up streak is.

### The headline

**A complete 14-hour outage could have happened between rounds 142 and 154 and
left no trace anywhere in this log.** Not "we measured it imprecisely" — no
record of it existing at all. That is longer than every outage this track has
ever *observed*, and until this round nothing in the tool or the prose hinted
it was possible.

## 4. The claim rounds 322/328/334 made, and could not support

"The longest outage this track has measured" has three competitors, not two:

1. the longest observed outage's **lower** bound — `exceeds_longest_completed`
   (rounds 316+), like-for-like but not a proof;
2. its **upper** bound — `definitely_exceeds_longest_completed` (round 334), a
   proof against the outages we *saw*;
3. **an outage we never saw at all** — new this round.

`current_streak_duration` now reports `max_unobserved_same_verdict_streak_s`
and `definitely_longest_including_unobserved`, and abstains (`None`, never
`False`) when either competitor is unbounded — `False` would read as "we
checked a real alternative and beat it".

Against the frozen round-340 log:

| as of | elapsed | vs observed record | vs hidden 14h competitor |
|---|---|---|---|
| round 334's last check `13:02:44Z` | 10h49m37s | `True` | **`False`** (short by 3h10m23s) |
| round 340 `17:38:03Z` | 15h25m14s | `True` | **`True`** (by 1h25m14s) |

The crossing instant is computable: first down check `02:13:07Z` + the
`14h00m00s` hidden bound = **`2026-08-29T16:13:07Z`**. Rounds 322, 328 and 334
each asserted the record while their own elapsed was still *shorter than an
outage the log could have missed entirely*. The claim was not wrong — it was
**unsupported**, and nothing in the tool said so. Round 340 is the first round
in which it is supportable, and it is supportable by 85 minutes.

Both cases are pinned as tests (`test_real_log_current_outage_now_clears_the_
hidden_competitor`) against a fixed `now`, so they assert the finding rather
than drifting with the clock.

## 5. The negative result: `boot_utc` cannot witness this box's failure mode

The obvious up-side witness is round 334's `boot_utc` — unchanged across two up
checks means no reboot in between. It is implemented, and deliberately
classified `reboot_only`, **not** `full`:

`/proc/uptime`'s first field is CLOCK_BOOTTIME-based and keeps counting across
suspend, so a box that slept and woke reports the *same* boot time. And suspend
is this box's own documented failure mode — round 184's ARP-incomplete finding
was "the box itself is off/asleep, not a routing problem".

So a boot-time witness would be silent on precisely the excursion most likely
to happen here. Counting it as `witnessed` would have converted the round's
finding into false comfort. `test_boot_utc_unchanged_is_reboot_only_and_does_
not_count_as_witnessed` makes `witnessed is False` the load-bearing assertion.

(The CLOCK_BOOTTIME semantics are read from the kernel's documented behaviour,
**not verified on this box** — it has been unreachable all round. Verifying it
directly is on the return checklist in §8.)

## 6. The real fix, built and tested offline: witnesses from the box itself

`gap_continuity` exposes the ceiling of probe-based measurement. A down gap can
be witnessed because tailscale's `LastSeen` is *itself* a continuously
maintained record. An up gap cannot, because nothing we sample at check time
says anything about the interval between checks — **and no cadence fixes that.**
Halving the check interval halves the blind spot; it never closes it.

The way out is evidence the box generates while nobody is looking.
`journalctl --list-boots -o json` is exactly that: each boot carries its first
and last journal entry, so the box's own log says when it was running and, by
subtraction, when it was not — retroactively, for gaps arbitrarily far back.

Landed as `parse_boot_history` / `boot_history_probe` /
`_boot_history_witness`, wired through `gap_continuity(records, boots)` and a
`continuity --boot-history FILE` CLI flag. Two outcomes, and the asymmetry is
the value:

- a boot's `[first_entry, last_entry]` **covers** the gap ⇒ `full` witness for
  an interval nobody probed;
- a boot boundary falls **inside** the gap ⇒ a missed excursion *with exact
  bounds* ("the box stopped logging 06:00 and resumed 09:00"), which is
  strictly more than any probe rule can ever produce.

`test_boot_history_witnesses_shrink_the_real_logs_blind_spot` runs it end to
end: a history covering the `142 -> 154` window drops
`max_unobserved_outage` from **14h00m00s to 8h01m00s** and moves those seconds
from the unwitnessed bucket to the witnessed one.

**NOT run live** — the box has been unreachable since 02:10Z. `runner` is
injectable precisely so the parse and witness logic could be built and tested
in full while it is down; every failure mode (unreachable, non-zero exit,
empty/unparseable output, `Storage=volatile` listing only the current boot)
degrades to "no witnesses", never to an exception or a fabricated one.

And its own limit is pinned as a test rather than left in a comment:
`test_boot_history_cannot_see_a_suspend_and_the_tests_say_so`. A suspend keeps
one `boot_id` and leaves the boot's first/last entries straddling it, so this
source reports a suspended box as continuously up. **`boot_history` closes the
reboot half of the blind spot and leaves the suspend half open.** Naming that
beats shipping it as "the fix".

## 7. Instrument failure: the mutation harness re-tested the previous mutant

The mutation-kill run (`skills/fuzz-mutate-kill-loop`) reported four survivors
on the boot-history code. One of them, **M34 — "probe lets a raising runner
propagate" — died instantly when reproduced by hand.** A survivor that
disappears under reproduction is an instrument fault, not a finding.

Root cause, measured rather than guessed:

```
M33 file: size 62272, mtime 1788024657.15  ->  second 1788024657
M34 file: size 62272, mtime 1788024657.91  ->  second 1788024657
```

CPython validates a cached `.pyc` against `(source mtime truncated to whole
seconds, source size)` — nothing else, no content hash. Two mutants that happen
to produce a file of the same size inside the same second share a cache key, so
**M34 ran against M33's bytecode and its own mutation never executed.**

The failure is **one-directional**: a stale cache re-runs the *previous* mutant,
so it can only ever manufacture a false SURVIVED, never a false KILLED. That is
why the earlier 24/24 result on the continuity code was not invalidated by it —
and it was re-run cache-safe anyway rather than argued about. It is also why
the bug is easy to miss: it does not break a clean run, it fabricates work for
you, chasing a survivor that is not one.

Fix (both, neither sufficient alone): purge every `__pycache__` under the
target tree once at start, **and** spawn each run with
`PYTHONDONTWRITEBYTECODE=1` — the env var stops new caches forming, not a
pre-existing one being read.

### The remaining survivors split three ways

Diagnosing before writing a test mattered here; only three of four were test
gaps.

- **M26 / M30 / M33 — genuinely missing assertions.** A boot-history gap that
  neither covers nor straddles the window had no test. The sort fixture's
  `index` order happened to agree with its time order, making
  `test_..._sorts_by_first_entry_not_by_index` **vacuous** — fixed with an
  `index`-absent fixture. And the probe's failure parametrisation paired every
  bad exit code with *empty* stdout, so the returncode check was unobservable;
  it needs `rc=255` with **good** stdout, which is the realistic case (ssh
  dropping mid-stream).
- **M27 — an invalid mutant.** Its injection point sat after an unconditional
  `return` in the branch above, so the mutated line was unreachable for the
  verdict it was meant to affect. The fix was to move the mutation, not to add
  a test.
- **M23 — a true equivalent mutant** (an alias replaced by an *equal* literal).
  Retired and replaced by M23b, which mutates the set's **contents** — the
  drift the alias actually exists to prevent.

### `assert A is B` on module constants is not a test

M23 exposed a fake test I had written. To pin "these two rules must never drift
apart on which verdicts LastSeen applies to", I wrote
`assert rc._LAST_SEEN_WITNESSES_GAP is rc._LAST_SEEN_BOUNDS_START`. **CPython
deduplicates equal constants within one module's constant pool**, so two
separate `("down", "ambiguous")` literals *are* the same object:

```
$ python3 -c 'A=("down","ambiguous"); B=("down","ambiguous"); print(A is B)'
True
$ ... print([c for c in code.co_consts if isinstance(c, tuple)])
[('down', 'ambiguous')]        # one entry, not two
```

The assertion passed whether the aliasing existed or not — unfalsifiable, and
therefore worth less than no test, since it looked like coverage. Replaced with
a per-verdict **behavioural** agreement test, which also catches the drift that
actually matters (a change to the set's *contents*) rather than its identity.

All three lessons are now in
`skills/fuzz-mutate-kill-loop/references/pitfalls.md`.

## 8. A second-order lesson: tests that pin live-file aggregates are a trap

The first draft pinned `n_gaps == 29`, `unwitnessed_total == 67h26m22s` and so
on against the **live** log — every one of which the very next E round's single
appended record would have turned red, looking like a regression and really
being arithmetic. Round 334's real-log tests got away with exact pins only
because they pinned *closed* history (outage 1), which can never move again.

Generalised into `_real_log_through_round()`, which freezes the log at
`ROUND_340_ANALYSIS_UTC = "2026-08-29T17:15:41Z"` — by **timestamp, not round
number**, because this round appended its own round-end check afterwards and a
round-number filter would have swept it back in. Aggregates are pinned exactly
against the frozen prefix; only monotone invariants run against the live file:

- no up gap is ever `witnessed` (true by construction, and stays true when up
  checks resume, since `boot_utc` can only ever be `reboot_only`);
- `max_unobserved_outage_s >= 50400` — it can only grow, and a future round
  that finds it *has* grown owes the record claim a re-check;
- `missed_excursions == []` on the **live** log, deliberately: if a future
  append makes that fail, it is a **finding, not a regression** — the log would
  be carrying positive evidence that a streak it calls unbroken was broken.
  The test says so, so nobody relaxes it.

Verified live: the round-end check appended a 34th record, moved `n_gaps` to 30
and the fraction to 69.2%, and all 151 tests stayed green.

## 9. Predictions (D-013)

`nuc/predictions-e-round340.md`, written before the code was run, with
provenance marked — P4 and P7 are arithmetic on a log table I had already
dumped and are labelled `[post-hoc]`; the other seven are blind.

**9 / 9 confirmed, 0 misses.**

| | prediction | result |
|---|---|---|
| P1 | 29 intra-streak gaps | 29 ✓ |
| P2 | all 11 down gaps witnessed, by the `LastSeen <= t1` rule | ✓ |
| P3 | 0 of 18 up gaps witnessed | ✓ |
| P4 | worst blind spot 14h00m00s, r142→r154 | ✓ `[post-hoc]` |
| P5 | 0 detected missed excursions | ✓ (and both rules provably *can* fire) |
| P6 | record claim becomes supportable, first time, at `16:13:07Z` | ✓ |
| P7 | 67h26m22s unwitnessed ≈ 69% | 69.47% ✓ `[post-hoc]` |
| P8 | `boot_utc` is `reboot_only`, not a witness, because of suspend | ✓ |
| P9 | the fix is the box's own boot history, buildable offline | ✓ |

A clean sweep is worth suspicion, not celebration: P1–P4 and P7 are arithmetic
over a 33-line file I had already read, so they test my arithmetic, not my
model of the system. **P5, P6, P8 and P9 are the ones that carried real
information**, and P8 is the only one that could have gone the other way on a
fact about the world rather than about the data.

## 10. Verification

```
python3 -m pytest -q nuc/tests/                       -> 348 passed   (was 276; +72)
python3 -m pytest -q nuc/tests/test_reachability_check.py
                                                      -> 151 passed   (was 79; +72)
python3 nuc/reachability_check.py continuity          -> 30 gaps, 12 witnessed,
                                                         69.2% unwitnessed
python3 nuc/reachability_check.py status              -> down 15h25m14s,
                                                         definitely_longest_
                                                         including_unobserved: true
mutation run, cache-safe, 35 hand-designed mutants    -> 35 killed, 0 survived
python3 skills/skill-authoring/scripts/skill_lint.py --house --strict skills/
                                                      -> 19 skill(s), 0 error(s),
                                                         0 warning(s), exit 0
python3 skills/skill-authoring/scripts/claim_check.py skills/
                                                      -> 48 cmd, 50 paths,
                                                         0 stale, exit 0
```

Cross-track suites re-run to confirm nothing outside `nuc/` and `skills/` moved.

## 11. What this round deliberately did not do

- **No priced runs, no engine traffic, no port 8001.** The box was unreachable
  the entire round; every artifact here is offline-testable by construction.
- **`boot_history_probe` was not run live.** It is `runner`-injectable and
  fully fixture-tested; running it needs the box, and inventing a plausible
  boot history to "verify" it would be the opposite of this round's point.
- **No suspend-aware witness.** Picking a signal needs the box's actual
  journal (which log lines does *this* deployment emit around
  `systemd-suspend`?). Guessing at a grep pattern and shipping it as a witness
  would repeat the `boot_utc` mistake this round exists to avoid.
- **No mission ticked.** E1–E5 are all `[x]`; this round is apparatus, not a
  new mission, and the honest place for it is the mission file's addendum.

## 12. Next steps

1. **On the first up check: run `boot_history_probe` immediately** and save the
   output. It retroactively witnesses gaps arbitrarily far back, so its value
   is highest the first time — and journal retention means waiting loses data
   permanently. Save to `state/nuc-boot-history.json`, then
   `continuity --boot-history state/nuc-boot-history.json`.
2. **Verify the CLOCK_BOOTTIME claim on the box** (§5): suspend it, resume, and
   check whether `/proc/uptime` advanced across the suspended interval. It is
   the assumption `reboot_only` rests on and it is currently read from kernel
   documentation, not measured here.
3. **Design the suspend witness** once the box's real journal is readable —
   what does *this* deployment log around a suspend/resume?
4. Still parked and unchanged for an eighth round: the second multi-hour
   `swap_watch_launch.py` poll (round 304's ask); standing state (`--cap 256`,
   E3 patch, OLMoE tarball, `memory.events` max, operator login) not
   re-verified.
5. **Sweep the rest of this repo's tooling for live-file aggregate pins** (§8).
   The trap is not specific to reachability: any test that pins a count over a
   file future rounds append to has the same shape.

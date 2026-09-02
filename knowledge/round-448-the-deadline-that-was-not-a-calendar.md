# Round 448 (NUC-integration E) — the deadline that was not a calendar

**One line:** `state/research-state.md` has carried `2026-09-03T00:07:00Z` as a
data-loss deadline for four rounds; it is not a date, it is a *systemd timer
fire conditional on the box being awake*, and the box has now slept through
three of the last eleven fires — including the one on 2026-09-02 — so the four
day files the standing note wrote off are still on disk right now.

**Box DOWN the whole round.** Third consecutive down E round (436, 442, 448).

---

## 0. Reachability, and the rule that stopped the probing

Two attempts, one per documented path, both failed. CLAUDE.md's "if SSH fails
twice in a row, record the failure and exit cleanly" fired after the second.

```
probe-1 2026-09-02T06:31:32Z
$ ssh -o ConnectTimeout=15 -i ~/.ssh/id_ed25519 jab@100.78.44.111
ssh: connect to host 100.78.44.111 port 22: Connection timed out      rc=255

probe-2 2026-09-02T06:32:01Z
$ ssh -o ConnectTimeout=12 -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37
Warning: Identity file /home/pgain/.ssh/id_ed25519_nuc not accessible: No such file or directory.
ssh: connect to host 192.168.1.37 port 22: Connection timed out        rc=255
```

`tailscale status` corroborates: `pgain-nuc … offline, last seen 12h ago`,
`Online: False`, `LastSeen 2026-09-01T18:27:56.1Z`. This host is `srv1244884`,
tailnet `100.85.110.121`, with no LAN route and no `id_ed25519_nuc` on disk —
so the tailnet path is the only real probe, exactly as round 442 recorded.

**The reachability log had a hole and now has one fewer.** Round 442 probed
twice, wrote the failure into its knowledge file, and appended nothing to
`state/nuc-reachability-log.jsonl` — the durable record that exists precisely
to replace that prose. Its last entry before this round was round 436's. Round
448's record is appended, marked `source: "live-replay-r448"`, replaying the
two probes above rather than opening a third connection after the rule had
already fired. Pinned by
`test_round_448_is_in_the_log_because_round_442_left_a_hole`.

---

## 1. The finding: a sweep the box slept through deletes nothing

`capture_manifest.py retention` forecasts which `sysstat` day files
`sysstat-summary.service` deletes next. Rounds 430-447 quoted its two headline
numbers in the state file's standing next-steps item as though they were dates:

> the NUC `retention --strict` deadline (`2026-09-10T00:07:00Z`, next loss
> `2026-09-03T00:07:00Z`)

They are not dates. Deletion happens when `sysstat-summary.timer` **fires**,
and it fires only while the box is up. This box is up perhaps half the time.

The question that decides whether an outage *saves* a day file or merely
*delays its death by a few hours* is one systemd setting, `Persistent=`. With
it, a fire missed while the box was off runs at the next boot. Without it, the
fire is simply lost. **No capture this program has ever taken includes that
setting.** But the answer was already in the banked journal, because the box
ran the experiment on itself twice:

```
$ .venv/bin/python3 nuc/capture_manifest.py sweeps \
    --capture state/nuc-capture-r424 --anchor 2026-09-02T00:07:00Z --strict
window 2026-08-23T14:02:08Z .. 2026-09-01T08:16:20Z
n_scheduled 9   n_ran 7   n_missed 2
missed: 2026-08-30T00:07:00Z, 2026-09-01T00:07:00Z
persistence: False — "0 of 2 fires missed during an outage were re-run
                      within 3600 s of the box coming back"
```

Both missing fires fall inside a gap in `journalctl --list-boots`:

| missed fire | box down from | box back at | caught up? |
|---|---|---|---|
| 2026-08-30T00:07:00Z | 2026-08-29T02:10:07Z (end of boot -2) | 2026-08-30T00:32:32Z | **no** |
| 2026-09-01T00:07:00Z | 2026-08-31T16:28:00Z (end of boot -1) | 2026-09-01T05:33:31Z | **no** |

The first is decisive on its own: the box came back **25 minutes** after the
fire it missed and logged no `sysstat-summary` run until the *next day's*
scheduled 00:07. Two independent trials, both saying `Persistent=` is not in
effect. **A slept-through sweep is lost, not deferred.**

The absence argument is only sound because round 424 removed `-b` from the
plan's `journalctl`: an unfiltered `_PID=1` journal spanning the window is what
makes "no line" mean "did not run" rather than "not captured". A boot-scoped
capture could not have supported any of this.

## 2. What that costs, measured both ways

The box was last seen alive at `2026-09-01T18:27:56Z` and was still down at
`2026-09-02T06:32:13Z`, so the `2026-09-02T00:07` fire falls strictly inside a
confirmed outage and did not run.

```
### BASELINE — the calendar model rounds 430-447 quoted
next_run 2026-09-02T00:07:00Z | doomed 4 ['sar24','sa24','sar23','sa23']
earliest_loss 2026-09-03T00:07:00Z ['sa25','sar25']
sa01 deadline 2026-09-10T00:07:00Z

### OUTAGE-AWARE — --down-since 2026-09-01T18:27:56Z --down-until 2026-09-02T06:32:13Z
requested 2026-09-02T00:07:00Z -> effective 2026-09-03T00:07:00Z
fires_passed_over ['2026-09-02T00:07:00Z']
doomed 6 ['sar25','sa25','sar24','sa24','sar23','sa23']
earliest_loss 2026-09-04T00:07:00Z ['sa26','sar26'] | conditional: True
sa01 deadline 2026-09-10T00:07:00Z
```

Read that as an operational fact, not a model refinement:

- **`sa23`, `sa24`, `sar23` and `sar24` are still on the box.** ~1.08 MB of
  `sar` history the standing note had already written off. They die at the
  *next* fire the box is awake for.
- The window to capture them closes at **2026-09-03T00:07:00Z**, and only if
  the box is up then. It has been down for 12 h.
- Six files, not four, die on that fire — the outage does not save files, it
  **batches** them.
- The `sa01` deadline is unmoved at `2026-09-10T00:07:00Z`: one skipped fire
  is not enough to reach it. The two numbers the state file carried do not
  drift together, which is why quoting them as a pair was already misleading.

Error direction matters and it is the bad one: the calendar model **over**-
reports loss, so it tells a later round to give up on a file still sitting on
disk. Round 424 captured `sa23` at all *because* of this mechanism, and
attributed it to `find -mtime`'s truncation; truncation bought 24 hours, the
missed 2026-09-01 fire bought another 24.

## 3. What was built

`nuc/capture_manifest.py` (+~290 lines):

- `parse_service_fires` — every instant a unit actually `Starting`ed, from an
  unfiltered `_PID=1 -o short-iso` journal.
- `parse_boot_table` — `journalctl --list-boots`, ignoring the `### DISK` and
  `### CONF` sections the capture appends after the table.
- `scheduled_fires` / `_covering_boot_gap` / `sweep_history` — scheduled vs
  observed, each miss annotated with the boot gap that explains it. The
  lattice anchor is a *measured* fire, never a hardcoded `00:07`.
- `persistence_verdict` — derives `Persistent=` from behaviour. **Fails closed
  to `"unknown"`** when no fire was missed inside a boot gap: with no missed
  fire there is no experiment, and answering `False` there would be inventing
  evidence for the more convenient answer.
- `fires_lost_to_outage` — half-open on the left, closed on the right.
- `retention_forecast(..., skipped_fires=, period_days=)` and a `skipped`-aware
  `_next_sweep_at_or_after`. New output: `requested_next_run_utc`,
  `skipped_fires`, `fires_passed_over`, `earliest_loss_conditional`.
  **`skipped_fires=()` reproduces every pre-448 answer byte for byte**, pinned.
- CLI: new `sweeps` verb (`--strict` exits 1 on an `unknown` verdict — an
  unknown verdict means the deadline cannot be called conditional *on
  evidence*), and `retention --skipped-fire/--down-since/--down-until/
  --period-days`. `--down-since` without `--down-until` is an ERROR: one alone
  names no window, and silently reading the end as "now" would make the answer
  depend on when the command was run.

`capture_plan` — four defects, three of them round 436's open item 2:

1. Step 3b's comment said *"the USER manager, which owns the engine"* over a
   command reading `_SYSTEMD_USER_UNIT=qwen36-colibri.service`. Those are two
   different journals. Both are now captured, each under its own name.
2. No `### ` marker was emitted for that redirect, which is how round 436 found
   `journal-user-full.txt` holding an unlabelled lead section plus a
   hand-written `### USER_MANAGER` copy of part of it. Every journal stream the
   plan writes now announces itself, like steps 2 and 3d always did. Pinned by
   `test_every_journal_stream_the_plan_writes_announces_itself`, which asserts
   over *all* such lines rather than the two that exist today.
3. `qwen36-toolproxy` — its own `Consumed` records and 9 `Started` fires,
   present in no capture this program has ever taken — is captured.
4. New step 3e: `systemctl cat` + `systemctl show -p Persistent -p OnCalendar
   -p RandomizedDelaySec …` for both sysstat timers, so the next up-round
   *reads* what §1 had to *infer*.

The emitted plan is now checked with `bash -n`. It is generated shell a future
round pastes into a live box in its first thirty seconds; a quoting slip in it
is a wasted up-window, and this round introduced one (and caught it) while
adding the loop that step 3c originally was.

## 4. Second finding: `LastSeen` is not a stable datum

`nuc/reachability_check.py`'s opening docstring adopted `tailscale status
--json`'s `LastSeen` over the plain-text renderer because the renderer "is a
SNAPSHOT recomputed fresh each round" and `LastSeen` was "the actual
timestamp `tailscale status --json` carries". **The JSON field is recomputed
too.** One continuous outage, box down throughout, local `tailscaled` up since
2026-08-09 (`ExecMainStartTimestamp`, no restart):

```
round 436, 2026-09-01T19:30:39Z and 19:46:19Z -> 2026-09-01T18:30:00.1Z (twice, byte-identical)
round 448, 2026-09-02T06:32:13Z, 3 reads 3 s apart -> 2026-09-01T18:27:56.1Z (all three identical)
```

**124 seconds EARLIER, eleven hours later.** The shape of the values is the
tell: of the five distinct non-zero `LastSeen` values in the log's whole
history, three sit on an exact `:00` second and two of those on an exact
half-hour (`16:30:00.1`, `18:30:00.1`, `02:10:00.1`); round 448's does not
(`18:27:56.1`). A coarse reading later refined is the simplest account.

Round 436 argued "one continuous outage" from the *byte-identity* of the two
readings it took. The conclusion survives — both readings sit before its first
check either way — but the reasoning does not: it rested on the field being
immutable, and it is not.

Two consequences, opposite in sign, both now handled:

- **`streak_bounds` took the LATEST reading in a streak.** Correct while every
  reading is sound. Once two readings contradict each other at most one is
  right, and a bound called *earliest possible start* must hold whichever is
  wrong — so a disputed streak now takes the **minimum** and reports
  `earliest_possible_start_source: "tailscale_last_seen_min_disputed"` plus a
  `lastseen_disputed` list. On the live log that widens the current outage's
  declared start uncertainty from `1h00m38s` to `1h02m42s`. The bracket got
  wider; the previous one was narrower than the evidence supports.
- **A rounded-UP reading can manufacture a phantom missed excursion.** "Later"
  is exactly the direction that walks a value into a down gap, where
  `_gap_witness` reports it as *positive evidence* that the box came back to
  life mid-outage. With checks at 18:29 and 18:35, the round-436 value
  `18:30:00.1` lands strictly inside and the module would have asserted an
  excursion that never happened. The claim now fails closed when another
  reading of the same streak places the sighting at or before the earlier
  check. Negative control kept: an *undisputed* reading inside a gap is still
  reported, because the whole point of the field is that it can contradict us.

New: `lastseen_drift(records)` and the `lastseen-drift` CLI verb
(`--strict` exits 1 on any disputed streak). On the live log:
**1 drifting streak, spread 124.0 s, direction `earlier`.**

**A round-334 test was reversed on purpose.**
`test_streak_bounds_takes_the_latest_last_seen_across_the_whole_streak` is now
`..._scans_the_whole_streak_and_takes_the_earliest_if_disputed`. Its docstring
says which round wrote it, what it asserted, and why the measurement changed
the answer — the property it was really protecting (the *whole* streak is
scanned, not just its first record) is unchanged and still asserted.

## 5. A bug this round wrote, and its own negative control caught

`persistence_verdict` first read its observed fires from `history["ran"]` —
the fires **matched** to a scheduled slot. A catch-up run is by construction
*not* at its scheduled slot, so the one event the verdict exists to detect was
the one event excluded from its evidence. **The verdict could only ever come
back `False`,** which is the answer this round wanted, on the live data,
correctly, for the wrong reason.

It was caught by `test_a_caught_up_fire_would_read_as_persistent`, written as
a negative control precisely because a verdict that agrees with you is the
kind you do not check. Fixed to use every observed fire, matched or not.

## 6. Tests

```
$ .venv/bin/python3 -m pytest nuc/tests -q
828 passed in 95.09s (0:01:35)
```

**802 -> 828, +26, 0 failures, 0 skips.** 17 in `test_capture_manifest.py`,
9 in `test_reachability_check.py`.

Every pin falsified by reverting the fix it guards, then restored:

| revert | fails |
|---|---|
| `persistence_verdict` back to `history["ran"]` only | `test_a_caught_up_fire_would_read_as_persistent` |
| `_next_sweep_at_or_after` ignores `skipped` | `..._moves_the_loss_a_whole_period_and_widens_it`, `..._two_consecutive_slept_through_fires_compose` |
| disputed start rule back to `max` | `..._takes_the_earliest_reading_and_says_so`, `..._scans_the_whole_streak_and_takes_the_earliest_if_disputed` |
| drop the phantom-excursion guard | `..._cannot_manufacture_a_missed_excursion` |
| treat `0001-01-01T00:00:00Z` as a timestamp | `test_the_tailscale_zero_value_is_not_a_timestamp` |

## 7. `%vmeff` — CLOSED as a written decision, not carried a fourth time

Round 430 opened it; rounds 436 and 442 carried it. Round 436's own item 3
said to check `pgsteal_kswapd > 0` first. The banked capture answers it
without a live box:

```
$ grep -E "^(pgscan|pgsteal)" state/nuc-capture-r424/collector-evidence.txt
pgsteal_kswapd 0   pgsteal_direct 0   pgsteal_khugepaged 0
pgscan_kswapd 0    pgscan_direct 0    pgscan_khugepaged 0
```

Every reclaim counter is zero at capture time, so `%vmeff` is `0/0` and the
residual test is vacuous — for the fourth time. **Decision: it stays vacuous
and stops being carried.** It is not a defect and cannot be resolved by
analysis; it needs a box that has actually reclaimed, and re-listing it every
E round has cost four rounds' attention for four identical readings. It
belongs in a *precondition* — "run this when `pgsteal_kswapd > 0`" — not in a
next-steps list. Reopen it when a capture shows a non-zero counter.

## 8. Predictions (D-013) — banked in `nuc/predictions-e-round448.md`

Written before the first `ssh`, before `retention` was run, and before
`capture_plan`'s body was opened. **17 HIT / 1 MISS / 1 PARTIAL / 2
no-basis-reported of 21 scoreable.**

| id | basis | verdict |
|---|---|---|
| A1 | `[NONE]` | **no-basis-reported** — box DOWN; third consecutive down E round |
| A2 | `[CMD]` | HIT — the LAN key still does not exist; failure is a missing file, not a route |
| B1 | `[MODEL]` | HIT — `sa23` 9.012 d doomed, `sa24` 8.012 doomed, `sa25` 7.012 → `find_age_units` 7, spared |
| B2 | `[MODEL]` | HIT — exit 1 |
| B3 | `[SENT]` | HIT — doomed set exactly `{sa23, sa24, sar23, sar24}` |
| B4 | `[MODEL]` | HIT — `earliest_loss_utc 2026-09-03T00:07:00Z`, `next_files_lost` includes `sa25` |
| B5 | `[SENT]` | HIT — both halves re-derive exactly (`sa01` → `2026-09-10T00:07:00Z`) |
| B6 | `[MODEL]` | HIT — no field named the retrospectivity, no warning printed. **This is the round.** |
| C1 | `[SENT]` | HIT — comment says "the USER manager", command says `_SYSTEMD_USER_UNIT=` |
| C2 | `[SENT]` | HIT — no `### ` header on that redirect |
| C3 | `[SENT]` | **MISS** — the plan emits ONE user journalctl, not two. Round 436's sentence was a *recommendation*; I read it as a description of the plan. The concatenation happened in the artefact, not from this code |
| C4 | `[SENT]` | HIT — `grep -c toolproxy nuc/capture_manifest.py` → 0 |
| D1 | `[CMD]` | HIT — HEAD was 802 |
| D2 | `[MODEL]` | HIT — N stated as 26 before the run; 828 = 802 + 26, 0 failures |
| D3 | `[CMD]` | **PARTIAL** — `nuc-checks PASS`, exit 0, but **101 s**, below the 120-260 s band |
| D4 | `[NONE]` | **no-basis-reported** — reported in §9, not bet on |
| E1 | `[CMD]` | HIT — still vacuous, and closed by decision in §7 |

**The basis experiment.** Round 436 concluded *"everything predicted from a
banked COMMAND hit; everything predicted from a banked SENTENCE missed"* and
no round has tested it since. Scored per class this round:

| basis | hit | miss | rate |
|---|---|---|---|
| `[CMD]` | 4 | 0 | 4/4 |
| `[MODEL]` | 5 | 0 | 5/5 |
| `[SENT]` | 5 | 1 | **5/6** |

**Round 436's rule is too strong and should not be promoted to a house rule.**
Prose-derived predictions hit 5 of 6 here, and the one miss has a sharper
shape than "it came from a sentence": C3 was the only `[SENT]` claim whose
source sentence was written in the **imperative** ("it *should* capture … but
not both in one file") rather than the indicative. C1, C2 and C4 were all
descriptions of state and all hit. The usable rule is narrower and worth
banking: **a recommendation is not an observation — do not predict that a
defect exists because a previous round recommended fixing it.** Round 436's
own five misses are consistent with this reading; they were predictions of a
file's CONTENTS from prose *about* the file, which is the same error of
treating a previous round's intent as a measurement.

Two `[NONE]` lines were banked and both were reported rather than quietly
dropped — `skills/prediction-banking/SKILL.md` step 9's no-basis rule,
exercised this round by a round that did not author it. Verdict on the rule
after first outside use: **usable, and it changed behaviour.** A1 would
otherwise have been a coin-flip on box reachability dressed as a forecast, and
D4 an unearned claim about a suite this round never ran.

### The `[CMD]` band that missed

D3 is the round's one PARTIAL and it is a bank defect, not bad luck. The band
`120-260 s` was derived from round 442's measured 150.5 s — and round 442 ran
that measurement in a round that was *also* doing other work on a one-core
box. The floor was set from a contended number and the check then ran solo:

```
$ bash nuc/run_checks_fast.sh
828 passed in 100.10s (0:01:40)
constant-audit 23 constants, 18 derived (0.783), 4 bare, 0 transform-risk
nuc-checks PASS (pytest rc=0, audit rc=0)
real 1m41.119s      EXIT=0
```

Round 434 already established that this box's contention penalty is roughly
3x, and round 447's item 8 said to plan every suite as serialised. A band
copied from a number measured under different contention is the same shape of
error as round 445's P6: a band over a quantity I could have adjusted for
rather than guessed at. **Rule for the bank: a wall-time band must state the
contention condition of the measurement it is derived from, or it is not a
prediction about this run.**

## 9. The other checks, reported rather than bet on (D4)

- `bash nuc/run_checks_fast.sh` -> **`nuc-checks PASS`**, exit 0, 828 passed,
  `constant-audit 23 constants, 18 derived (0.783), 4 bare, 0 transform-risk`.
  **Seven consecutive PASSes** (442-448); round 442's interpreter fix holds.
- `bash skills/run_checks_fast.sh` -> `10 checker(s), 2 error(s), 8
  warning(s)`. **Both errors were this round's own** and both are now closed:
  `carryforward ERROR K001` (1 unscored bank — `nuc/predictions-e-round448.md`
  had no entry in `state/prediction-bank-ledger.json`, which is round 435's
  K001 rule doing exactly its job on the round that created the bank) and
  `unit_tests ERROR rc1`, whose two failures were
  `test_the_live_ledger_accounts_for_every_bank_on_disk` and
  `test_live_corpus_is_clean` — the same K001, seen twice. Registered; see §10.
- Worth recording because the state file has carried it since round 429:
  **`verb_audit` now reports `V002 0`.** Round 447's item 7 lists
  `test_no_unexplained_broken_invocation` as red on "every corpus-check line,
  including this round's". It is not red on this one — `verb-audit: 18
  finding(s) (V001 6, V002 0, V003 12) — all WARN`. Nothing this round touched
  `verb_audit` or any verb it audits, so this is a re-derivation, not a fix,
  and it belongs to whichever round between 447 and here changed it.
  harness(A) should confirm and close the carry rather than copy it forward
  again.

## 10. The two errors this round created, and closing them

`skills/run_checks_fast.sh` went from `0 error(s)` at HEAD to `2 error(s)`
the moment this round wrote its prediction bank, and both were the same fact:
`nuc/predictions-e-round448.md` existed on disk with no entry in
`state/prediction-bank-ledger.json`. Round 435's K001 rule discovers banks by
a repo-wide filename sweep precisely so that a bank under a new naming
convention cannot escape, and `nuc/predictions-e-roundNNN.md` is the seventh
such convention. It worked.

Registering the entry closed both:

```
carryforward       ERROR K001    1 error(s)     ->  ok    0 error(s)
unit_tests         ERROR rc1     2 failed       ->  ok    911 passed
corpus-check: 10 checker(s), 0 error(s), 8 warning(s)
```

The two failures were
`test_carryforward_check.py::TestLiveCorpus::test_the_live_ledger_accounts_for_every_bank_on_disk`
and `test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean` — one
fact, two readers.

**The ledger edit is 8 lines, not 955.** The first attempt round-tripped the
file with `json.dumps(indent=2, ensure_ascii=False)` and produced a
955-insertion/947-deletion diff for a one-entry addition. The file is written
`indent=1, ensure_ascii=True`; verified by asserting an exact round-trip
before editing:

```
$ python3 -c "import json; raw=open(P).read(); \
  print(json.dumps(json.loads(raw), indent=1, ensure_ascii=True)+chr(10) == raw)"
True
```

`quote` is re-read by K002 against the knowledge file, so it must match this
file's §8 headline verbatim, newline included — it was wrong once (written
before D3 was scored PARTIAL) and the test said so.

# Round 358 (NUC-integration E) — the witness that claimed too much, and the
# 3h26m gap that turned out to hide at most 96 seconds

Track: NUC-integration(E). Box: **UP**, same boot `43e0c767` as round 352
(boot_utc `2026-08-30T00:32:27Z`), uptime 5h15m at first contact, load 0.00.

Predictions were written first (`nuc/predictions-e-round358.md`, house rule
**D-013**) and are scored in §7.

Target: round 352 §8 **item 2** — the suspend blind spot in
`_boot_history_witness` — plus item 1 (the in-flight 8 h swap poll).

---

## 1. The claim that was too strong, and how large the overstatement was

Round 340 built `_boot_history_witness`: if some boot's
`[first_entry, last_entry]` covers an up-streak gap, the box was running and
logging across it, so the gap is `WITNESS_FULL`. Round 352 ran it live for
the first time and reported the effect:

| | round 352's live numbers |
| --- | --- |
| witnessed gaps, without boot history | 13 / 31 |
| witnessed gaps, WITH boot history | **31 / 31** |
| unwitnessed time | **0h00m00s** |
| `max_unobserved_outage` | **None** |
| `transition_count_upper_bound` | **4** |

Round 352 also wrote down, in the same file, why those numbers could not be
right: endpoint coverage says nothing about the boot's *interior*, so a box
that suspended for the whole gap looks identical to one that ran. It filed
that as §8 item 2 and shipped the numbers anyway.

**The contradiction was already inside the test suite.** Round 340's
`test_boot_history_cannot_see_a_suspend_and_the_tests_say_so` has a docstring
that says this source cannot see a suspend, and an assertion body that reads:

```python
assert rc.gap_continuity(recs, boots)[0]["gaps"][0]["witnessed"] is True
```

A test whose name and docstring describe a blind spot, asserting that the
blind spot is witnessed. The prose was right and the assertion was wrong, and
because the assertion is what runs, the wrong one is what shipped for 18
rounds.

**The principle that decides it** is the one round 352 stated and did not
act on: `boot_utc unchanged` and `boot_history` endpoint coverage rule out
*exactly the same thing* — a reboot — and neither rules out a suspend. Two
rules that rule out the same thing must return the same strength. So
endpoint coverage is now `WITNESS_REBOOT_ONLY`, not `WITNESS_FULL`, and the
round-352 column above collapses back:

| | boot history only, round 358 semantics |
| --- | --- |
| unwitnessed gaps | **19 / 32** (all 19 up gaps) |
| unwitnessed time | **70h53m11s** |
| `max_unobserved_outage` | **14h00m00s** (rounds 142→154) |
| `transition_count_upper_bound` | **None** |

`FULL` is not reachable from this source at all. That is not a defect to fix
later; it is what the source is.

## 2. The fix: a bound instead of a boolean

An excursion can only hide in a stretch where the box wrote nothing. Every
journal entry is a moment the box was demonstrably awake. So the longest
silent stretch inside a gap is an upper bound on any excursion hiding in it —
a suspend longer than that stretch would have had to swallow an entry that
exists. The claim changes shape:

```
"the box was up across this gap"     unearned, suspend-blind, boolean
"any excursion here is at most 96 s" earned, measured, a number
```

New machinery in `nuc/reachability_check.py`:

- `WITNESS_BOUNDED`, a fourth strength between `REBOOT_ONLY` and `FULL`.
- `journal_seconds_probe(since, until)` — one ssh call, `journalctl --since
  @T1 --until @T2 -o short-unix` piped through an `awk` run-length dedup
  **on the box**, so the wire carries one short line per second that has at
  least one entry instead of the raw entries (measured: 1631 lines for
  49 954-entries-per-day traffic).
- `parse_journal_seconds` — sorts locally rather than trusting journal order,
  because one out-of-order line would produce a negative interval and
  silently *deflate* the bound, the one direction it must never fail in.
- `interior_silence(t1, t2, seconds, covers_from, covers_to)` — returns
  `None`, never a number, when the capture window does not provably cover
  the gap. Silence before the window began is indistinguishable from real
  silence, and reporting the second as the first is the exact overstatement
  this change exists to remove.
- `gap_unobserved_s(gap)` — the quantitative axis, alongside the existing
  boolean one: `0` for FULL, the measured bound for BOUNDED, the whole gap
  otherwise. `continuity_report`'s `max_unobserved_outage_s` now ranks by
  this instead of by raw gap length.
- CLI: `journal-seconds --since --until --out` to capture; `continuity
  --journal-seconds FILE` to consume.

**A BOUNDED gap is still `witnessed: False`.** That was deliberate: the
witnessed/unwitnessed time buckets partition the log span exactly (round
340's `test_continuity_report_time_buckets_partition_the_log_span` pins it),
and a bound is not a refutation. The two axes answer different questions —
"did we rule it out?" and "how much could be hiding?" — and round 340 had
only the first, which is precisely how a suspend-blind rule came to report
`max_unobserved_outage: None`.

### Conservative on the truncation, on purpose

`parse_journal_seconds` yields whole seconds, and an entry stamped `S`
happened somewhere in `[S, S+1)`. The widest silence consistent with two
adjacent markers is therefore `later.hi - earlier.lo`, so each journal entry
contributes `S` as earliest-liveness and `S+1` as latest; the two probe
timestamps are exact. Every reported bound is an *upper* bound, which is the
only direction a bound on a hidden outage may err in. It is also why the
bound is never zero: an arbitrarily short excursion always fits between two
entries, so `FULL` stays out of reach — pinned by
`test_bound_is_never_zero_because_a_short_excursion_always_fits`.

## 3. The design error the live box found in the first cut (P13)

The first implementation put the silence upgrade *inside*
`_boot_history_witness`, so a gap had to be covered by a boot record before
its interior could be consulted. Run against the real log it produced:

```
journal_seconds_loaded = 1870
bounded_gap_count      = 0
```

1870 seconds of live journal evidence, zero gaps bounded. The reason is
specific and would not have shown up in any fixture: the boot history
available at that moment was round 352's, captured at 02:20Z, so the current
boot's `last_entry` in it *predates round 358's own check* and therefore does
not cover the gap the fresh interior capture was for.

The fix is also the more correct design. A journal entry proves the box was
awake at that instant no matter what any boot record says, so the upgrade is
keyed on the **strength** (`REBOOT_ONLY`, from either rule) rather than on
which rule produced it. `_silence_upgrade` never downgrades: a gap where the
boot history *proved* an excursion, or a down gap with a genuine LastSeen
`FULL` witness, passes through untouched.

P13 predicted this class of failure in advance ("this code will be wrong in
some way on its first contact with the real box"). It was, in a way no
offline test could have produced, and it was caught and fixed inside the
round.

## 4. The live measurement

Fresh `journalctl --list-boots` (`state/nuc-boot-history-r358/`) — 7 boots,
identical to round 352's except boot 0's `last_entry` has advanced:

| boot | first entry | last entry |
| --- | --- | --- |
| -6 `061f83ca` | 2026-08-19T10:00:51Z | 2026-08-20T00:30:05Z |
| -5 `db09a51c` | 2026-08-23T14:02:05Z | 2026-08-25T00:37:03Z |
| -4 `94b2e014` | 2026-08-25T00:37:32Z | 2026-08-25T00:46:50Z |
| -3 `5308fdec` | 2026-08-25T00:47:28Z | 2026-08-25T12:51:25Z |
| -2 `b3818eef` | 2026-08-25T12:57:39Z | 2026-08-27T04:46:47Z |
| -1 `391cb36e` | 2026-08-27T11:50:51Z | 2026-08-29T02:10:07Z |
| 0 `43e0c767`  | 2026-08-30T00:32:32Z | 2026-08-30T05:59:35Z |

Journal-seconds capture over the current boot (`--since 00:32:27Z --until
05:47:43Z`): **1870 distinct entry-seconds in 18 916 s = 9.9 %**. The box
writes something in roughly one second in ten while it is up.

**The headline, on the one up gap this capture covers — rounds 352 → 358:**

| | |
| --- | --- |
| gap | 2026-08-30T02:20:54Z → 05:47:43Z, **3h26m49s** |
| entry-seconds inside it | 1631 |
| longest interior silence | **96 s**, 02:21:20Z → 02:22:55Z |
| witness | `bounded`, source `boot_history+journal` |
| what could hide there | **0h01m36s**, not 3h26m49s |

A **129×** reduction in the claimable blind spot for that gap, and
`unobserved_total` for the whole log drops 70h53m11s → **67h27m58s** off
that single gap. Unlike round 352's `0h00m00s`, this number is earned.

### The caveat that comes free with the method

1631 of 12 409 seconds is 13 %, noticeably denser than the boot-wide 9.9 %,
and the reason is that **this round was ssh-ing into the box during that
window**. Every login writes `session-NNN.scope` records. So the bound is
tightest exactly when we are actively poking the box — i.e. when we least
need it — and loosest on a quiet unattended gap, which is when an excursion
is most likely and the bound matters most. The method is sound; its
resolution is anti-correlated with the risk it measures. Any future round
quoting a bound should say whether the window contained its own activity.

### Cost: the probe is not free on this box

`journalctl` over the **current** boot: **5.5 s**. Over the full
reachability-log span (2026-08-25T16:11Z → now, ~4.5 days): **still running
after 5 minutes at 100 % of one core** — it has to decompress ~3.3 G of
archived journals. Relaunched with a longer timeout; §8 records where it
landed. Practical rule: capture per-boot, not per-log-span, and cache.

## 5. Round 304 item 1 — the 8 h swap poll, mid-flight

Round 352's launch is healthy. Checked, **not** relaunched (round 274's rule,
and round 352 §3 is a fresh argument for it):

- remote pid **2337** alive, `--interval 15.0 --duration 28800.0`
- checkpoint `~/nuc-research/swap-watch-r352-checkpoint.jsonl`: **815
  samples** at 05:49Z (seq 814), ~42 % of the 1920 expected
- every sample so far: `swap_bytes` 0, `pswpin_pages` 0, `pswpout_pages` 0,
  `mem_current_bytes` 9.77 GB (32.6 % of the 30 GiB ceiling)
- due ~2026-08-30T10:25Z, i.e. **after this round ends**. The local watcher
  in `state/nuc-swap-watch-r352/` is still ticking (`iter=196` at 05:46Z) and
  will write `PULL_DONE` to `poll.log`.

Round 352's P14 ("≥1 swap burst in 8 h") is heading for a **MISS** with 815
samples of evidence. `mem_current` has crept 9.10 → 9.77 GB over 3.5 h — real
growth, but a ~65-hour extrapolation to the ceiling, on a box whose journal
shows no workload at all. Round 124's "traffic-diversity-dependent, not
immediate" reading survives a second boot.

## 6. Housekeeping — `languages/whence/SECURITY.md`

Still ` M`, byte-identical to what round 349 escalated: the Hermes gateway's
rewrite asserts four security controls (pre-commit secret hook, CI dependency
scanning, SHA-256 release checksums, signed tags) that do not exist in this
repo, and it deleted the human-authorship attribution. **Not committed, not
allowlisted, not modified** — round 349's reasoning is unchanged and this is
the tenth consecutive round the record-gap check has surfaced it. It is not a
leftover diff; it is an open operator decision, and the check is doing its
job by refusing to let it go quiet. P14 HIT.

## 7. Prediction scoring (D-013)

| | prediction | outcome |
| --- | --- | --- |
| P1 | pid 2337 still alive | **HIT** |
| P2 | checkpoint 700–1000 samples | **HIT** — 815 |
| P3 | swap still 0 B, `memory.events` max 0 | **HIT** — 815/815 samples |
| P4 | the 8 h poll will not reproduce round 136's 310.6 MB | **ON TRACK** (resolves ~10:25Z) |
| P5 | full-span journal query returns non-empty | **UNRESOLVED** — read false, but our own 1400 s client timeout produced it, not the box (§8) |
| P6 | 50k–400k distinct entry-seconds over the span | **MISS** — ~10 %/s while up ⇒ ~20k expected, an order of magnitude below the band |
| P7 | transfer under 5 MB | **HIT** — 22.5 kB for a 5 h boot; ~230 kB projected for the span |
| P8 | ≥1 of the 18 old gaps has silence > 600 s | **UNRESOLVED** — needs the data §8 did not deliver |
| P9 | worst silence 1800 s–4 h | **UNRESOLVED** — same |
| P10 | ≥1 gap bounded under 120 s | **HIT** — 96 s, rounds 352→358 |
| P11 | strength change alone restores non-None/non-zero headline numbers | **HIT** — `None` → 14h00m00s, `0h00m00s` → 70h53m11s |
| P12 | this does not confirm or refute suspend | **HIT** — it bounds, §2 |
| P13 | the code will be wrong on first contact with the box | **HIT, twice** — §3 (a design error, not a typo) and §8 (a client timeout that discarded 23 minutes of good remote work) |
| P14 | SECURITY.md unchanged, no operator action | **HIT** — §6 |
| P15 | no writes outside `~/nuc-research/**` and `/work/logs/**` | **HIT** — §9 |

Final tally: **11 HIT, 1 MISS, 3 UNRESOLVED**. Nothing is scored on data
this round did not obtain.

**P6 is the instructive miss.** I anchored on "an idle box is never truly
silent" and reasoned upward from entry counts (~50k/day). The right unit was
distinct *seconds*, and 50k entries collapse into ~1.9k seconds because
journald traffic is bursty: sessions, timers, and unit state changes fire in
clusters. Getting this wrong in the *high* direction is the safe side (I
budgeted for a payload 20× the real one), but it is the same class of error
as reasoning about prefill from token counts instead of from the measured
curve.

## 8. Full-span capture

Launched in the background with a 1400 s client timeout over
2026-08-25T16:11:00Z → 2026-08-30T05:47:43Z, after confirming no orphaned
`journalctl` was left on the box by the timed-out first attempt (`ps aux |
grep journalctl` = 0).

**It came back with `n_seconds: 0` after 23 minutes** — a failure, not a
measurement. Diagnosis, from elapsed time against the configured limit:
started 05:58:20Z, wrote at 06:21:57Z = **1417 s against a `timeout_s` of
1400**, so `subprocess.run` raised `TimeoutExpired` and
`journal_seconds_probe` returned `[]` exactly as designed. The client gave up
~17 seconds before its own deadline would have mattered; the remote side had
been running for 23 minutes and its result was discarded. **Third instance
this round, and the fourth E-round running, of code being wrong on first
contact with the real machine — and the second time in two E-rounds that the
failure was a client giving up on a remote side that was fine** (round 352
§3 was the same shape with `swap_watch_launch.py`).

**Why it takes that long, measured rather than guessed.** A 30-minute window
inside boot `-1` (2026-08-28T12:00–12:30Z) holds **81 991 entries — 2733
entries/second sustained** — and takes 8.2 s to scan. Boot -1 spans ~38 h, so
that boot alone is ~10 minutes of scanning, and boot -2 spans ~40 h more. The
cost is not archive decompression; it is that **this box's earlier boots
logged two orders of magnitude harder than the current one** (the current
boot averages well under 3 entries/s). Whatever was running on 08-28 is not
running now, and the journal's own volume is the evidence.

The payload was never the problem: 81 991 entries dedup to at most 1800
whole seconds, so the `awk` reduction was doing its job.

**One more defect this exposed.** The CLI wrote the empty capture to `--out`
anyway, producing a file that says "covers 2026-08-25 → 2026-08-30, 0
entry-seconds" — indistinguishable on disk from a real measurement of a
silent box. Nothing downstream would have been fooled (`make_silence_fn`
refuses an empty list, so every gap stays `REBOOT_ONLY`), but a human reading
the directory would have been, and I nearly quoted it. Fixed: an empty
capture is never written, and the exit code is non-zero. Pinned by
`test_cli_journal_seconds_never_writes_an_empty_capture`. The file has been
deleted rather than kept as an artifact.

**P5, P8 and P9 are therefore UNRESOLVED, not scored.** P5 (non-empty
full-span result) technically read as false, but the cause was our own client
timeout, not the box — scoring it as a MISS would credit a prediction with an
outcome it did not produce. P8 (>600 s silence in an old gap) and P9 (worst
silence 1800 s–4 h) need the data that did not arrive. What §10 item 1 now
asks for — per-boot captures cached by `boot_id` — is also the right way to
get them: each boot is a separate, resumable, cacheable scan, and boot -1
alone would have fit comfortably inside the timeout that killed the whole
span.

## 9. NUC hygiene

- Writes on the box: **none**. Every command this round was a read
  (`ps`, `wc -l`, `tail`, `uptime`, `journalctl`, `systemctl` not needed).
  `~/nuc-research/**` was read, not written.
- `/work/**` read-only; the round's log goes to `/work/logs/`, an allowed
  write path.
- **Port 8001 never contacted.** No unit restarted. No engine request of any
  kind — this round needed no inference.
- One real cost imposed: the full-span `journalctl` pinned one of two cores
  for ~5 minutes on the first attempt. Recorded because a "read-only" probe
  that saturates half the box's CPU is not free, and the next round should
  scope its window per-boot.

## 10. What this leaves

1. **Bound the other 18 up gaps.** This round bounded exactly one, because a
   per-boot capture only covers gaps inside that boot. The other 18 live in
   boots -1 through -6, each needing its own archived-journal scan. Those
   boots are **closed and immutable**, so the right shape is a cache keyed by
   `boot_id` (`state/nuc-journal-<boot_id>.json`) written once and never
   recomputed. Do it on an up-round; the journal is only readable from the
   box.
2. **The suspend hypothesis is still neither confirmed nor refuted**, and
   round 358 did not try — it bounds how much suspend could hide. The signal
   that would *detect* one is in the same journal and takes one grep:
   `journalctl -k | grep 'PM: suspend'` or `journalctl -u systemd-suspend`.
   Never run. It would turn a bound into an observation and is the cheapest
   open item on this track.
3. **`journal_seconds_probe`'s slow path is live-unverified.** The fast
   per-boot case works (5.5 s). The only live evidence for the archived-scan
   case is a 300 s timeout and a second attempt whose result is recorded
   above. Same shape as round 334's `boot_probe` and round 304's launcher:
   a code path that has met a fixture but not a machine.
4. **Round 352's knowledge file §2 has been annotated as superseded** rather
   than edited. Its numbers (`31/31`, `0h00m00s`, `None`, upper bound `4`)
   were the headline of an E-round and would otherwise be quoted forward.
   `state/nuc-missions.md` and `state/research-state.md` carry the same
   correction.
5. **I duplicated 24 rows of the reachability log, and the guard that would
   have stopped me did not exist.** `nuc/reachability_backfill.py`'s
   docstring has said "this script is meant to run exactly once — re-running
   it would duplicate every row" since round 310. I ran
   `reachability_backfill.py --help` as a smoke test. The script had no
   argument parsing at all, so `--help` fell straight through to the append
   loop and wrote a second copy of the entire backfill (`n_records` 37 → 61)
   while printing a success message. Reverted with `git checkout` — the log
   was committed minutes earlier, which is the only reason the revert was
   clean.

   This is round 356's finding in a different file: **a rule stated in prose
   that nothing enforces is not a rule.** Fixed with two guards, because they
   fail differently — argv is checked *first*, so an unrecognised option
   prints usage and writes nothing even on an empty log where the dedup guard
   would happily proceed; and rows already present are skipped by
   `(checked_at_utc, round)`, so a bare re-run is a no-op. Pinned by
   `test_backfill_refuses_unknown_args_and_is_idempotent`.

   The generalisable part: `--help` is the *least* dangerous thing anyone
   types, which is exactly why a script that ignores argv is dangerous. Any
   one-shot mutating script in this repo should be assumed to have the same
   hole until it is shown not to.
6. **`bounded-not-binary-witness` is unprobed**, acknowledged in
   `state/known-unprobed-skills.json` with owner `skills(B)`. A probe is a
   priced live run and the standing convention is that E-rounds do not launch
   priced batches; its four cases are written and ready.
7. Nothing on the box was written outside `/work/logs/nuc-continuity-r358.md`.
   No unit restarted. Port 8001 never contacted. `/work/**` read only.

---

## 11. The one-grep suspend check, run (§10 item 2, same round)

§10 item 2 called this "the cheapest open item on this track", so I ran it
rather than filing it. On the current boot `43e0c767` (00:32:27Z → now):

| query | matches |
| --- | --- |
| `journalctl -b 0 -k` ∋ `PM: suspend` \| `PM: hibernation` \| `Freezing user space` | **7** |
| …of which are actual suspend events | **0** |
| `journalctl -b 0` ∋ `systemd-suspend` \| `Reached target Sleep` \| `Suspending system` \| `systemd-sleep` | **0** |

All 7 are `PM: hibernation: Registered nosave memory: [mem …]`, stamped
`00:32:32` — boot-time hibernation *setup*, printed by every Linux boot on a
machine that could in principle hibernate. Neither `PM: suspend entry` nor
`Freezing user space`, the two kernel lines an actual suspend must emit,
appears at all.

**So: this box has not suspended once in 5.5 hours of uptime**, and the 96 s
bound from §4 has zero suspend events inside it to bound.

Supporting configuration, read the same call: `sleep.target`,
`suspend.target`, `hibernate.target` are all `static` (no `[Install]`
section, so nothing has enabled them); `/etc/systemd/logind.conf` is an empty
`[Login]` stanza, i.e. every idle/lid policy is at its compiled-in default;
`/sys/power/state` is `freeze mem disk`, so the hardware *can* suspend.
Capable, not configured, and never observed.

**What this does and does not settle.** It does not refute round 184 — that
inference was about a specific 2026-08-25 outage on a different boot, and
checking `-b -1` and earlier means scanning the archived journals, which
timed out at 120 s while the §8 capture held a core. It does establish, for
the first time in this program, that the suspend hypothesis is *checkable
with one grep*, and gives the exact signature to check:

```
journalctl -b <N> -k | grep -E 'PM: suspend (entry|exit)|Freezing user space'
journalctl -b <N>    | grep -E 'systemd-suspend|Reached target Sleep'
```

`PM: hibernation:` is a **false positive** and must be excluded — it fires
seven times on a boot that never slept.

It also sharpens `_BOOT_UTC_SUSPEND_CAVEAT` without weakening it. The caveat
is about what `boot_utc` *cannot rule out*, and that stays true regardless of
whether this box in fact suspends. But the whole reason the caveat is
weighted heavily here rather than treated as pedantry is round 184's
inference that suspend is *this box's* failure mode — and that inference now
has one boot's worth of direct evidence against it, and none for it. A future
round that runs the two greps over boots -1 to -6 either promotes round 184's
inference to a finding or retires it. Either outcome is worth one E-round's
first ten minutes.

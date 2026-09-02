# Round 454 (NUC-integration E) — the observation that bought ignorance

**One line:** round 448 found one missing row in the reachability log and wrote
a rule about it; there were **eight**, seven of them recoverable from a source
no round had ever read — and when the seven landed, the log's own measure of
how much it does not know went **up** by 9h46m, which is a defect, not a cost.

**Box DOWN the whole round.** Fourth consecutive down E round (436, 442, 448,
454). All findings offline.

---

## 0. Reachability, and the rule that stopped the probing

Two attempts, one per documented path, both failed. CLAUDE.md's "if SSH fails
twice in a row, record the failure and exit cleanly" fired after the second.

```
probe-1 2026-09-02T12:36:41Z
$ timeout 30 ssh -o ConnectTimeout=15 -o BatchMode=yes -i ~/.ssh/id_ed25519 jab@100.78.44.111
ssh: connect to host 100.78.44.111 port 22: Connection timed out          rc=255

probe-2 2026-09-02T12:37:02Z
$ timeout 25 ssh -o ConnectTimeout=12 -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37
Warning: Identity file /home/pgain/.ssh/id_ed25519_nuc not accessible: No such file or directory.
ssh: connect to host 192.168.1.37 port 22: Connection timed out           rc=255
```

`tailscale status --json` at 12:37:51Z: `Online false`,
`LastSeen 2026-09-01T18:27:56.1Z`, `LastWrite 2026-09-02T12:37:48.99Z`. This
host is `srv1244884` (tailnet `100.85.110.121`), no LAN route, no
`id_ed25519_nuc` on disk — the tailnet path is the only real probe.

**The LastSeen reading is byte-identical to round 448's, six hours earlier**, so
this is one continuous outage: 436, 442, 448 and 454 are all inside it.
`reachability_check.py status`, read after round 454's row landed:

```
verdict                        down        streak_start_round   436
elapsed_human                  17h34m34s   as_of_utc            2026-09-02T13:05:13Z
elapsed_upper_human            18h37m16s   start_uncertainty    1h02m42s
earliest_possible_start_utc    2026-09-01T18:27:56.1Z
earliest_possible_start_source tailscale_last_seen_min_disputed
longest_completed_same_verdict_streak_human   19h38m06s
exceeds_longest_completed      false       margin_human         2h03m32s
```

The `_min_disputed` source is round 448's own rule doing its job: two readings
of this streak disagree by 124 s, so the bracket takes the earlier one and says
that it is disputed rather than trusting the later. **This outage is 2h03m32s
short of being the longest this log has ever confirmed** — and its upper bracket
already exceeds that record, so which it is depends on when the box returns.

Round 454's row is in the log as `live-replay-r454` — it replays the two probes
above rather than opening a third connection after the rule had fired, the
shape round 448 established.

---

## 1. The rule had one known violation and eight real ones

Round 448 wrote, in `state/nuc-missions.md`:

> Round 442 probed twice, wrote the failure into prose, and appended nothing.
> **Every E round owes this log one line, up or down.**

and pinned it with `test_round_448_is_in_the_log_because_round_442_left_a_hole`.
Nobody had counted. Counting is one query:

```
E rounds (n mod 6 == 4) in [124, 448]           55
  ... with a row in state/nuc-reachability-log.jsonl   47
  ... with NO row                                       8
      148, 190, 220, 226, 250, 280, 292, 442
```

Seven of the eight are inside round 310's prose-backfill range (≤ 304) and one
(442) is in the live-`check` era. `logs/driver.log` says **190, 220, 226, 250,
280, 292 and 442 all ran as `track=NUC-integration(E)` and all reported
`success`.** They are not rounds that never happened.

**Why the backfill missed seven of them, and why that was not carelessness.**
`nuc/reachability_backfill.py` derived every row from `state/nuc-missions.md`'s
round addenda. Those seven rounds wrote no addendum, so there was nothing to
derive from. Round 310 read its source exhaustively; the source was incomplete.

---

## 2. The evidence was in a file nobody had opened

`logs/round-<N>.json` — the round's own transcript — was on disk for every one
of the seven. It carries the exact ssh command, the exact output, and a
millisecond timestamp. It is not a summary of the observation; it **is** the
observation.

That matters because the prose source could not have been fixed by trying
harder. Of the seven rounds, **exactly one (280) has a `knowledge/round-N-*.md`
file at all**, and only 220/226/250/280/292/442 have a `research-state.md`
heading. Six of the seven left no narrative record of any kind. The transcript
is the only place their probes survive.

| round | verdict | deciding probe (UTC) | evidence line |
|---|---|---|---|
| 190 | **down** | 2026-08-27T07:57:03Z | `ssh: connect to host 192.168.1.37 port 22: Connection timed out` (tailnet failed in the same command) |
| 220 | up | 2026-08-27T21:49:52Z | `21:49:52 up 9:59, 2 users, load average: 0.06, 0.02, 0.00` |
| 226 | up | 2026-08-28T00:55:39Z | `00:55:38 up 13:04, 2 users, ...` |
| 250 | up | 2026-08-28T09:13:01Z | `09:13:01 up 21:22, 2 users, ...` |
| 280 | up | 2026-08-28T20:07:00Z | `20:07:00 up 1 day, 8:16, 3 users, ...` |
| 292 | up | 2026-08-28T23:46:03Z | `23:46:03 up 1 day, 11:55, 3 users, ...` |
| 442 | **down** | 2026-09-02T01:10:55Z | `ssh: connect to host 100.78.44.111 port 22: Connection timed out` |

**Cross-check the recovery did not have to pass and did.** Rounds 220, 226 and
250 each ran `uptime -s` against the box on three different days. All three
recover `2026-08-27T11:50:48Z` — the same boot the log's existing round-202-era
rows already carry, written by a different round from a different reading.

### What `nuc/reachability_recover.py` will and will not conclude

Shell output is not an API, so the rules are narrow and written down:

1. A probe is a Bash call whose command contains `ssh` **and** a documented NUC
   target. Nothing else is looked at.
2. DOWN evidence is the ssh client's own failure line. UP evidence is a remote
   `uptime` line. **A probe carrying both is returned as `conflict`, never
   silently as `up`**, and `record_from_probes` raises on it.
3. The deciding probe on a `down` round is the last **tailnet** failure, not the
   last failure. *This was a bug I wrote and caught.* The LAN path is unusable
   from this host — the key does not exist — so its timeout is not a box-down
   signal at all, a point round 442's own knowledge file makes. `downs[-1]`
   pinned round 442 to 01:11:16Z, the weaker of its two observations, 21 s after
   the one that meant something. A round whose only failures are on the LAN path
   now gets a verdict whose `why` says "treat with suspicion".
4. `boot_utc` comes **only** from an absolute `uptime -s` line. `uptime`'s
   "up 1 day, 8:16" and `who -a`'s "system boot 2026-08-27 11:50" are rounded to
   the minute, and `boot_utc_crosscheck` runs a **120 s tolerance** against that
   field — feeding it minute-rounded values manufactures drift that is really
   rounding. Rounds 280 and 292 carry `null` and their notes say why.
5. Every row records the evidence line it was derived from, and `source` is
   `transcript-rN`, never `live`.

The pin that makes this auditable rather than asserted:
`test_every_recovered_row_in_the_live_log_still_re_derives` re-runs the
derivation against the real transcripts and demands **byte-identical** output
against the committed row. A recovered row that cannot be regenerated from its
stated evidence is a hand-written row wearing a provenance label. It caught two
of this round's own falsifiers.

Unlike `reachability_backfill.py`, this module is **re-runnable** — it reads
files rather than carrying a hardcoded list — and refuses to duplicate a round
that already has a row.

---

## 3. The finding: eight observations made the log know less

With all eight rows appended, `continuity_report` on the real log:

```
                        BEFORE (52 rows)   AFTER (60 rows)
unobserved_total_s          388923.0          424077.0
unobserved_total_human    108h02m03s        117h47m57s
```

**+35154 s — 9h46m — of ignorance, bought with eight observations.** An
observation cannot buy ignorance. Splitting it by verdict says where:

```
down   0 s  ->  27699 s     REGRESSION
up     +7455 s              REAL
```

The up-side +7455 s is honest: round 292 is a new *last* record of its streak,
so the interval r286→r292 is interior time the log did not previously span. The
other five up insertions redistribute existing unobserved time and conserve it
exactly (28860 = 9304 + 11147 + 8409; 13200 = 4933 + 8267; 12900 = 7212 + 5688).

The down-side 27699 s is a defect, and it is two gaps:

| was | is | why |
|---|---|---|
| r184→r196, 18880 s, **witnessed in full** | r184→**r190** 8223 s **unwitnessed** + r190→r196 witnessed | round 190's recovered row has no LastSeen |
| r436→r448, 38754 s, **witnessed in full** | r436→**r442** 19476 s **unwitnessed** + two witnessed | round 442's recovered row has no LastSeen |

8223 + 19476 = 27699 exactly.

### Mechanism

`_gap_witness` consulted **only the immediately-following record's**
`tailscale_last_seen_utc`:

```python
last_seen = later.get("tailscale_last_seen_utc")
if not last_seen:
    return {"strength": WITNESS_NONE, ...,
            "note": "no tailscale_last_seen_utc on the later record"}
```

Its own comment celebrates being "strictly more general than 'LastSeen
unchanged across the two records': it needs no LastSeen at all on the earlier
record". It needed one on the later record, and that is exactly the record a
recovered row cannot supply.

The witness had not gone anywhere. **A reading taken at R reporting the peer
last seen at S proves the peer was not on the tailnet in (S, R] — which covers
every gap of the streak inside that span, not only the one ending at R.** Round
196's row still proves the 184→190 half; the code simply stopped looking at it.

### Fix

`_gap_witness` now takes `forward_lastseen` — the readings of records strictly
*after* the gap's later endpoint, so every read time is ≥ t2 by construction —
and uses the first that satisfies `S ≤ t1`. It inherits round 448's dispute rule
unchanged (a reading falling *inside* the gap contradicts it and both fail
closed), and it **may witness but may not accuse**: the forward path can never
produce a `missed_excursion`. That claim stays with the record that made the
reading, where round 448 put it.

```
                        BEFORE (52)   AFTER (60, fixed)
unobserved_total_s        388923.0        396378.0
down-side unobserved           0.0             0.0
six INTERIOR insertions          —              +0
```

The invariant is pinned directly rather than as a number:
`test_inserting_an_interior_check_never_increases_unobserved_total` removes the
six interior rounds from the real log and asserts the total is unchanged.

**One thing I did not fix.** The up side has the same shape latent — a
`BOUNDED` gap split by a record with no `boot_utc` would regress the same way —
but there is no live instance (`bounded_gap_count` is 0 without a journal
capture, and the recovered up rows split gaps that were already unobserved in
full). Building for it would be building against a case I cannot exhibit. Named
here so the next round finds it rather than rediscovers it.

### A second defect found while fixing the first

`gap_continuity` called `_gap_witness` **twice per gap** — once for the gap
dict, once to collect `missed_excursions` — building the argument list
independently each time. Adding `forward_lastseen` to one and not the other
would have made the reported gap and the reported excursion disagree, silently.
Computed once and reused now.

---

## 4. The enforcer the rule never got

Round 448's rule lived in prose. The only test naming it,
`test_round_448_is_in_the_log_because_round_442_left_a_hole`, asserts a
historical fact about rounds 442 and 448 and would pass forever regardless of
what round 460 does. **Nothing in the repo failed when an E round ran and
appended nothing** — verified by grep: the log has exactly two readers under
`nuc/`, and `test_sysstat_archive.py`'s is a comment.

`reachability_check.py coverage`:

```
$ .venv/bin/python3 nuc/reachability_check.py coverage --strict
{ "n_e_rounds": 51, "first_visible_round": 154, "in_flight_round": 454,
  "n_owed": 50, "n_covered": 50, "missing": [], "missing_declared": {},
  "declared_but_not_missing": {},
  "logged_outside_population": [124, 130, 136, 142] }
EXIT=0
```

Three design points, each because the obvious version is wrong:

- **The population is `logs/driver.log`, not `N mod 6 == 4`.** The rotation is
  what CLAUDE.md intends; the driver log is what happened, and they disagree:
  `state/research-state.md`'s heading for round 220 says *SWE-loop(D)* while the
  driver line says *NUC-integration(E)* — and round 220's transcript contains
  live NUC ssh probes, so the driver line is the one matching the evidence.
- **The highest E round is exempt by default.** The driver writes a round's
  `start` line *before* the round runs, so a check without the exemption is red
  for the whole of every E round and green only in between — round 453's "check
  that runs after you are gone" shape, arriving from the other side.
  `--no-allow-in-flight` for post-hoc audits.
- **A declaration that suppresses nothing is reported as dead.** `--strict`
  fails on it. I wrote this field, then immediately tripped it: my first
  `state/nuc-reachability-declared-holes.json` declared round 148, which is
  *outside* the population (driver.log's own first line is round 152), so the
  declaration suppressed nothing and would have failed `--strict` forever. The
  registry ships **empty**, with round 148's evidence in a `_why_not_listed`
  key instead. Round 148 is the one unrecoverable hole: no transcript, no
  research-state heading, no archive heading, no knowledge file.

---

## 5. Two tests that pinned values guaranteed to move

Both are the same species: an assertion about a number that advances for a
reason unrelated to what the test is about, so the next round edits the number
instead of reading it.

**`test_the_live_log_has_exactly_one_drifting_streak_and_it_is_this_outage`**
asserted `d["streaks"][0]["end_round"] == 448`. `end_round` is the streak's last
record, so it became 454 the moment round 454 appended a row — a row that read
*the same LastSeen round 448 did* and therefore said nothing whatsoever about
drift. It now pins the drift: two distinct values, 124.0 s apart, in the outage
starting at round 436, all stable under any number of further readings of a
value already in the set.

**`test_round_448_is_in_the_log_because_round_442_left_a_hole`** asserted
`442 not in rounds` — it pinned the hole **open**. Round 448's own prose called
it a gap closed "by one round, not two", i.e. it wanted 442 recovered; the test
it shipped in the same commit made recovering it a failure. It now pins the
*provenance* of each row: 448's is a `live-replay-r448`, 442's is a
`transcript-r442`, and a recovered row must never claim to be `live`.

---

## 6. A latent bug the recovery exposed rather than caused

`_covers_the_whole_live_log`, the fixture helper round 382 rewrote *specifically*
to stop hard-coding a window, derived its window from `recs[0]` and `recs[-1]`.
`load_log` returns **file order** and promises nothing else; every real consumer
in the module sorts through `_sort_key` first. Appending eight recovered rows
whose timestamps predate rows already in the file is exactly the operation that
breaks the assumption:

```
file first/last : 2026-08-25T16:11:00Z .. 2026-08-28T23:46:03Z
true  min/max   : 2026-08-25T16:11:00Z .. 2026-09-02T12:37:51Z
```

The window ended four days before the log did and
`max_unobserved_outage_s` came out 20536.0 against a ceiling of 301 — which
*reads* as an instrument regression and is really an expired window, the very
failure round 382's docstring describes, arriving from a direction it did not
consider: not the clock walking past a fixed window, but an append landing out
of order. Fixed to min/max, and pinned by
`test_the_module_does_not_care_what_order_the_log_file_is_in`, which asserts
the file is *not* sorted (so the test cannot go vacuous) and that
`continuity_report` is identical over file order, sorted order and reversed
order.

**The log is append-only and will never be chronological again.** That is the
right trade: sorting the file would rewrite a record whose value is that nobody
rewrites it.

---

## 7. Four real-log pins updated, with the cause and not just the number

Every one of these moved because the recovery moved a real quantity. I initially
patched two of them with numbers I *predicted* rather than measured, and both
were wrong on the first run — the exact failure this program keeps cataloguing,
committed by the round writing about it. The committed numbers are measured.

| pin | was | is | cause |
|---|---|---|---|
| second up streak `end_round` | 286 | **292** | round 292 recovered; it is now the streak's last record |
| that streak's `confirmed_span_human` | 32h23m22s | **34h27m37s** | +7455 s, the r286→r292 interval |
| `n_gaps` through round 340 | 29 | **35** | six recovered rounds ≤ 340, each splits a gap |
| `unwitnessed_total_human` through 340 | 67h26m22s | **69h30m37s** | +7455 s — the *same* new gap, not new ignorance |
| **worst blind spot, second up streak** | 8h01m00s | **3h07m22s** | rounds 220/226/250/280 all landed inside it |

That last row is the recovery paying for itself: the longest window in which an
undetected outage could hide inside the program's longest up streak fell by
**4h53m38s**. The first up streak is unmoved at 14h00m00s because no round was
recovered inside it — round 190 is a `down` round and landed in the 184/196
outage instead.

**And a comment I had to strike.**
`test_real_log_worst_blind_spot_is_the_r142_to_r154_gap` carried:

> Against the live log the bound can only ever grow (a new up gap could be
> worse; **an old one cannot shrink**).

An old gap shrinks the instant an observation is recovered inside it, which is
what happened to the 8h01m gap above. The test still passes — but only because
none of the recovered rounds happened to fall inside the r142→r154 window, which
is luck, not an invariant, and the comment now says so.

---

## 8. Predictions (D-013) — banked in `nuc/predictions-e-round454.md`

Written after the probes and the tailscale read, before any test was run, any
`reachability_check` verb was run against a modified log, and before any of the
seven transcripts were opened.

**6 HIT, 1 PARTIAL, 2 MISS of 9.**

| # | prediction | outcome |
|---|---|---|
| P1 | appending r454 breaks the drift test **on `end_round`**, not on `n_drifting_streaks` or `spread_s` | **HIT**, exactly: `assert 454 == 448`, with `1` and `124.0` both passing first |
| P2 | recovering r442 breaks `test_round_448_...` on `442 not in rounds` and no other clause | **HIT** |
| P3 | appending only r454 leaves `test_round_448_...` green | **HIT** |
| P4 | ≥1 *more* test breaks from the log growing; "most likely a record count or a last-round in summarize/streak_bounds/continuity" | **PARTIAL** — see below |
| P5 | baseline `nuc/tests` 828 passed, 90–110 s | **HIT** on the count; 88.49 s, 1.5 s under the band |
| P6a | 5 of the 7 prehistoric holes have a knowledge file | **MISS** — the answer is **1** |
| P6b | 4 of the 7 yield a defensible verdict | **MISS** — the answer is **6** |
| P7 | inserting r442 creates no new streak; the outage still starts at 436 | **HIT** (8 streaks before and after) |
| P8 | a null LastSeen on r442's row does not move drift | **HIT** (1 streak, 124.0 s) |
| P9 | nothing in the repo enforces round 448's rule | **HIT** |

**P4, scored honestly as PARTIAL.** The count was right — exactly one more test
broke at that stage. The mechanism was wrong: it was
`test_constant_audit.py::test_the_fast_check_runs_green_on_this_tree`, a
*cascade* (the health-check wrapper runs the suite, so any failure inside it
fails that test too), not an independent pin. The mechanism I named did appear —
four real-log pins in `streak_bounds`/`continuity_report` — but one stage later,
when the six *up* rows landed, and I do not get to claim a prediction that
matched a change I had not yet decided to make.

**P6a and P6b are one miss with one cause, and it is the round's own lesson.**
I predicted from `state/research-state.md` hit counts, reasoning that a round
with a research-state entry would have a knowledge file. Four of them
(220/226/250/292) have a heading and no knowledge file. And I never considered
`logs/round-N.json` at all — so I under-predicted recoverability by a factor
of 1.5 while over-predicting the wrong source by a factor of 5.
**I banked a prediction about where evidence lives, and I had the wrong
inventory of places it can live.** That is a better finding than either number.

---

## 9. Round 448's standing action, run

Both commands, in the order round 448 fixed:

```
$ .venv/bin/python3 nuc/capture_manifest.py sweeps --capture state/nuc-capture-r424 \
      --anchor 2026-09-02T00:07:00Z --strict
n_scheduled 9  n_ran 7  n_missed 2   persistence FALSE                  exit 0
  "0 of 2 fires missed during an outage were re-run within 3600 s of the
   box coming back"

$ .venv/bin/python3 nuc/capture_manifest.py retention --capture state/nuc-capture-r424 \
      --now 2026-09-01T08:16:20Z --next-run 2026-09-03T00:07:00Z --history 7 \
      --down-since 2026-09-01T18:27:56Z --down-until 2026-09-02T12:37:51Z --strict
next_run_utc          2026-09-03T00:07:00Z
skipped_fires         ["2026-09-02T00:07:00Z"]
n_deleted_at_next_run 6   (sar25, sa25, sar24, sa24, sar23, sa23)
earliest_loss_utc     2026-09-04T00:07:00Z   earliest_loss_conditional true
                      "the box is UP at that fire; a fire slept through
                       deletes nothing and is not deferred"           exit 0
```

**Round 448's forecast is holding.** It predicted `sa23/sa24/sar23/sar24` would
still be on the box because the box slept through the 2026-09-02 fire, and that
they would die together with `sa25`/`sar25` — six files, not four — at the next
fire the box is awake for. The 09-02 fire is now confirmed skipped, the six
files are still the doomed set, and the box has been down for the 18 hours
since. **This remains a forecast, not a score**: the box has not been reachable
since round 424's capture, so nothing has re-read the directory. The scoring
belongs to the first up round, and it is round 448's prediction to score, not
this round's to claim.

---

## 10. Round 448's item 6 — round 370's item 3, RETIRED

Carried untouched for thirteen E rounds and asked to be retired by round 448.
Retiring it, with the reason:

Round 370's item 3 was "catch the int4→int8 unpack live". Round 424 ran it on
the first fresh boot since it was written and found it **half closed, half
impossible**: the journal holds the load retrospectively (`05:33:34` start,
`05:33:48` `resident weights loaded in 13.1s | RSS after load: 9.25 GB`), so
no polling is needed for the timeline — and there are **no `unpacking to int8
in slot` lines at all** on that boot (9 journal lines total; model dir
`qwen36_i4_gs64`). The item names a log line this configuration does not emit.
The other half, the `memory.current` trajectory, is permanently gone: an
unsampled level does not survive.

**Retired**, not "still open". Reopen only if the model directory changes.

---

## 11. Tests

```
$ .venv/bin/python3 -m pytest nuc/tests -q
869 passed in 96.04s (0:01:36)            # 828 -> 869, +41

$ bash nuc/run_checks_fast.sh
constant-audit 23 constants, 18 derived (0.783), 4 bare, 0 transform-risk
nuc-checks PASS (pytest rc=0, audit rc=0)                          EXIT=0
```

`nuc-checks` PASS makes **eight** consecutive (442-454), the streak round 442
started when it found the check had never once been green.

**Every new pin falsified by reverting the fix it guards:**

| falsifier | red |
|---|---|
| remove the forward-LastSeen witness | 8 tests, incl. the pre-existing `test_real_log_both_outages_are_provably_continuous` |
| delete round 430's row from the log | `coverage` reports `missing [430]`, `--strict` exit 1 |
| deciding probe back to `downs[-1]` | 2, incl. the r442 re-derive pin |
| `boot_utc` accepts the minute-rounded reading | 2, incl. the r292 re-derive pin |
| window helper back to `recs[0]`/`recs[-1]` | 2 |

---

## 12. Final state

Working tree left with exactly the two paths it started with:
`languages/whence/SECURITY.md` (escalated round 349, still the operator's
decision — the record-gap checker's own line is the only source for its carry
count) and `state/round_counter` (a registered standing-dirty path).

**Landed at the start of the round, not by it:** `state/slow-tier-ledger.jsonl`
gained one entry (`test_swe_bymap.py`, passed, 54.27 s, finished
2026-09-02T12:35:08Z) *after* round 453's last commit. This is the **fifth**
consecutive round to land its predecessor's ledger line — 448→449, 449→450,
451→452, 452→453, 453→454 — because the driver's slow-tier instrument appends
after the round's final commit, by construction. It is attributed each time and
adopted by none, which is correct but is now costing a commit a round; a driver
that appended before the round's window closed, or a standing-dirty entry with
a *content* rule rather than a path rule, would end it. harness(A).

**Commits:** `d0b02b6` (round 453's ledger orphan), `08a53e3` (the recovery),
`2099e31` (the witness fix, the coverage verb, the two rewritten tests), plus
this record.

---

## Next steps (round 454)

1. **If the box is up, capture `sa23`/`sa24`/`sar23`/`sar24` BEFORE anything
   else**, then run the current `capture_plan` (which since round 448 takes
   `Persistent=` and the toolproxy journal). Round 448's items 1-3 are all
   still unrun and all still require a reachable box: read `Persistent=` and
   compare it against the derived `false` — **if it says `true`, round 448's §2
   correction is wrong in the dangerous direction and must be withdrawn loudly**
   — and score the six-file survival forecast against the directory's own `ls`.
2. **`coverage --strict` is now the first command of every E round.** It will
   go red the round after an E round appends nothing, and it exempts only the
   round in flight. If a hole ever appears, `reachability_recover.py` closes it
   from `logs/round-N.json` before anyone writes prose about it.
3. **The up-side of the witness bug is latent and unexhibited.** A `BOUNDED`
   gap split by a record with no `boot_utc` regresses the same way the down side
   did. There is no live instance, so it is deliberately unbuilt — a round that
   supplies a journal capture and makes `bounded_gap_count > 0` on the live log
   will create one. NUC-integration(E).
4. **The recovered rows have no `tailscale_last_seen_utc` and could.** Round
   190's transcript carries `offline, last seen 3h ago` — coarse, deliberately
   dropped rather than converted, because a derived-to-the-hour LastSeen fed to
   `_gap_witness` is precisely the "rounded value walks into a gap" hazard round
   448 found. If a future round wants those fields, the honest route is a
   `precision`-aware LastSeen, not a division. NUC-integration(E).
5. **The transcripts are a source this program has barely used.** `logs/round-*.json`
   holds every command every round ran, with timestamps. This round used it to
   recover reachability; the same file could re-date any claim whose round left
   no knowledge file — and six of the seven rounds recovered here left none.
   skills(B) or harness(A).
6. **Round 370's item 3 is RETIRED** (§10) and should stop being carried.
   Round 448's item 4 (round 436's items 4-6 and 9: the `commit` channel vs the
   9.25 GB load, `Consumed` coverage at 4 of 26 units, the 13 costly buckets
   named by no fire, the separability route) stands **untouched by this round**.
7. **Still blocked on the operator:** `--cap 196` (band [129, 204],
   `bounded_by: engine_lru`, 1.096 GB margin — **twenty-third** round unchanged)
   and the E3 A/B with its six-gate table.
8. **`nproc` on this box is 1.** This round ran one pytest at a time and the
   full `nuc/tests` took 96 s; the same suite under the driver's concurrent
   health check takes appreciably longer. Plan every suite as serialised.
9. **Standing, and not touched by this round:** `case_coverage`'s disagreeing
   verdicts; `claim_check` executing 0 of its commands; the `%vmeff` residual
   (round 448 CLOSED it by written decision — do not re-open without a capture
   showing a non-zero `pgsteal_*`); and CLAUDE.md's `CRITICAL MISSION` block,
   re-escalated for the **nineteenth** time and still a one-line deletion for
   the operator. `languages/whence/SECURITY.md` is still uncommitted, still not
   this program's, and still the operator's decision — do not copy a carry count
   for it from any file; the record-gap checker's own line is the only source.

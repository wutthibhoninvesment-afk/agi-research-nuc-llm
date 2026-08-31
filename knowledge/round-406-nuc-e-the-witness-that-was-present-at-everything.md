# Round 406 (NUC-integration E) — the witness that was present at everything

**Box state: DOWN for the whole round.** `tailscale status` reported
`pgain-nuc` offline, last seen **2026-08-31T16:30:00.1Z**; a real ssh probe to
`jab@100.78.44.111` timed out (rc 255, "Connection timed out"). Two consecutive
ssh failures, so CLAUDE.md's rule applied and no further probing was attempted.
The failure is recorded in `state/nuc-reachability-log.jsonl` (record 45, round
406, `verdict: down`, `source: live`, `precision: precise`) and in the missions
addendum.

This is the first down window since the 298–346 outage ended. It opened between
round 400's last contact (**2026-08-31T13:14:19Z**, up) and 16:30:00.1Z, and the
box had been up for nine consecutive E-rounds on boot `43e0c767` before it.

Predictions were banked before any measurement, per **D-013**:
`nuc/predictions-e-round406.md`. Scored in §7, misses included.

---

## 1. Why a down round had anything to measure

Round 400 committed its raw captures to git — `state/nuc-capture-r400/`, 14
files, 656 kB, including nine days of rendered `sar` and the boot's journal.
That was not framed as the point of round 400; it was a by-product. It is the
reason this round has results instead of a reachability record.

It also means round 400's own handoff item 3 — *"prove or drop the fwupd
attribution — now the only sole-attributable event in the boot"* — was
answerable with the box unreachable. Every number below comes from files that
were already in the repository.

---

## 2. The claim, and where it came from

Round 394 observed a 67.7 MB swap-out in the 10-minute bucket ending
2026-08-31T02:00:05Z and attributed it to `fwupd-refresh`, which had started at
01:57:33Z and was the only named systemd unit in that bucket. Round 400 turned
that reasoning into a whole-boot instrument (`nuc/perturbation.py:cost_ledger`)
and reported:

> 62 named fires, 6 in a costly bucket (9.68 %), **1 sole-attributable —
> `fwupd-refresh` 01:57:33Z**

Re-running the ledger on the banked capture reproduces that **exactly**:

| | sa30 (2026-08-30) | sa31 (2026-08-31) | boot |
|---|---|---|---|
| buckets | 139 | 79 | 218 |
| costly buckets | 1 | 2 | 3 |
| named fires | 35 | 27 | 62 |
| fires in a costly bucket | 0 | 6 | 6 |
| sole-attributable | 0 | 1 | **1** |

The one entry:

```json
{"at_utc": "2026-08-31T01:57:33Z", "unit": "fwupd-refresh",
 "bucket_end": "02:00:05", "pswpout_s": 27.54,
 "bucket_swapped_bytes": 67682304, "bucket_shared_by": 1,
 "costly": true, "sole_attributable": true}
```

Nothing is wrong with this. `sole_attributable` is computed correctly and means
what it says: exactly one named unit started in a bucket that moved more than
`LEDGER_MIN_BYTES`. The defect is in reading it as a licence for *"fwupd-refresh
cost 67.68 MB"*.

## 3. The denominator nobody had computed

`sole_attributable` is a statement about a **bucket**. Causation is a statement
about the **unit**. The bridging number is how often that unit fires, and how
often it fires without the effect. Here is every `fwupd-refresh` fire on sa31:

```
00:37:05Z  bucket 00:40:05         344,064 B  shared_by=3
01:57:33Z  bucket 02:00:05      67,682,304 B  shared_by=1  <-- COSTLY
02:27:05Z  bucket 02:30:05               0 B  shared_by=1
03:57:05Z  bucket 04:00:03     220,889,088 B  shared_by=5  <-- COSTLY
04:24:53Z  bucket 04:30:05               0 B  shared_by=1
05:59:33Z  bucket 06:00:05               0 B  shared_by=1
06:55:28Z  bucket 07:00:05               0 B  shared_by=1
07:49:05Z  bucket 07:50:03               0 B  shared_by=1
08:43:33Z  bucket 08:50:05               0 B  shared_by=1
09:07:14Z  bucket 09:10:05               0 B  shared_by=1
10:41:53Z  bucket 10:50:05               0 B  shared_by=2
11:47:53Z  bucket 11:50:05               0 B  shared_by=1
12:50:05Z  bucket 13:00:05               0 B  shared_by=1
```

**13 fires on sa31; 10 in buckets that moved zero bytes.** Widening to the whole
boot:

> **`fwupd-refresh` fired 36 times. 33 of the 36 buckets moved exactly zero
> bytes — 91.7 %.**

And the half of that which needs no statistics at all: **on sa30 it fired 23
times, produced 23 zero-byte buckets, and hit none of the day's costly ones.**
Same box, same boot, same configuration, claimed cause present twenty-three
times, claimed effect absent every time. That is an independent replication in
which the hypothesis fails outright.

A frequency argument sits underneath it. 36 fires over 218 buckets is an
**occupancy of 16.5 %** — `fwupd-refresh` is within ten minutes of one in six of
everything that happens on this box. Being "the only name in the bucket" is what
chance looks like for a unit that common.

Its firing interval is irregular (gaps on sa31 of 80, 30, 90, 27, 95, 56, 54,
54, 24, 94, 66, 63 min — a 3.96× spread) for a nominally-daily
`fwupd-refresh.timer`. **Why it fires ~hourly is not determined by this round**
and the banked capture cannot settle it; see §5.

### The counter-argument, stated and answered

`fwupd-refresh` is in **both** of sa31's costly buckets. Placing 13 fires into
13 of 79 buckets, covering both costly ones has p = 156/6162 = **0.0253**, which
looks like evidence *for* the attribution. Three things defeat it:

1. One of the two hits is the 04:00:03 bucket, **shared with four other units**
   (`apt-daily`, `apt-news`, `esm-cache`, `packagekit`). Round 400's own finding
   is that a bucket cannot separate five units. That hit carries no attributional
   information, leaving one clean hit and P(≥1) = **0.3038**.
2. The suspect was chosen by having been noticed. Corrected over the 16 units in
   the ledger, nothing survives.
3. The sa30 replication is not a p-value at all. 23 fires, 23 zeroes.

**Verdict on round 400's item 3: DROP.** The 67.68 MB event at 02:00:05Z is
unexplained. It was unexplained when round 388 recorded it as unexplained, and
the two rounds that named a cause added a name, not an explanation.

## 4. The gate, built where the flag is

Put in `nuc/perturbation.py` next to `cost_ledger`, so a uniqueness flag and its
denominator cannot travel separately: `attribution_evidence(ledgers)` pools
per-day ledgers and grades every unit — `insufficient-data` (< 2 occurrences, no
within-unit replication), `no-evidence`, `shared-only`, `coincidence`,
`supported`. Exact hypergeometric tail, Bonferroni over every unit in the
ledger. Reachable as `python3 nuc/perturbation.py evidence --ledger A --ledger B`.

Run over the whole boot (`state/nuc-capture-r406/evidence.json`):

```
pooled N=218 buckets, K=3 costly, 16 units tested
by_verdict: {'coincidence': 1, 'shared-only': 4, 'no-evidence': 4, 'insufficient-data': 7}
supported: []

unit                       fires costly  clean  zero  p_family  verdict
fwupd-refresh                 36      2      1    33    1.0000  coincidence
apt-daily                      3      1      0     2    0.6545  shared-only
apt-news / esm-cache / packagekit  2   1     0     1    0.4383  shared-only
...
```

**No unit in the boot licenses a causal claim.** That is a stronger and less
comfortable result than "fwupd is innocent", and it is the honest one: this
instrument, over this record, cannot attribute anything. `supported: []` is
published rather than tuned away — the gate is demonstrably passable
(`test_a_unit_that_is_consistent_clean_and_rare_IS_supported`), the data just
does not pass it.

Generalised to `skills/cause-needs-a-denominator/SKILL.md`.

## 5. The capture was filtered, and nothing recorded that

The obvious stronger test is to attribute a bucket to the units that were
**running** during it rather than the one that happened to **start** in it —
`cost_ledger` places a fire at an instant, but cost accrues over a runtime, and
a unit starting at 01:45 and running twenty minutes spans three buckets while
being credited to one. That test needs one field: when each unit finished.

The banked journal has **358 `Starting` lines and zero `Finished` lines.** It
was grepped for `Starting|Started`, and a systemd *oneshot* logs `Finished`,
never `Started`. Consequences, measured:

- **330 of 358 fires (92.2 %) have no derivable duration.**
- **62 of 87 distinct units never get a terminal line** — and that set contains
  *every* housekeeping unit in the cost ledger: `fwupd-refresh`, `apt-daily`,
  `apt-news`, `esm-cache`, `man-db`, `logrotate`, `motd-news`, `fstrim`,
  `dpkg-db-backup`, `sysstat-summary`, `systemd-tmpfiles-clean`,
  `apt-daily-upgrade`, `e2scrub_all`.
- So the interval-attribution test is **unrunnable from banked data**, and so is
  the question in §3 about why a daily timer fires hourly (a `Failed`/retry loop
  and a healthy re-trigger are indistinguishable without terminal lines).

What makes this expensive is not the omission but that it was **invisible**.
`unit-starts.txt` is 112 kB of real journal and looks complete. Nothing in the
tree said "this is `Starting|Started` only". Round 406 designed an analysis
against a field that had never been captured before discovering it was absent.

`nuc/capture_manifest.py` makes it a checked claim: `audit` reports what a
capture directory banked against what `nuc/` actually parses, `plan` emits the
exact shell to close the gaps. On round 400's capture:

```
verdict: filtered   gaps: 10   blocking: 3
 [sar]! `sar -B` for sa23..sa29     paging, the page-cache channel (round 388's apt finding)
 [journal]! `Finished <unit>.service` lines
 [journal]! `Failed <unit>.service` lines
 [sar]  -u, -q, -S, -b, -d, -n DEV, -w   for every day file (no nuc/ module reads them yet)
```

Banked for all nine days: `-r` and `-W` only. `-B` for sa30/sa31 only. Seven
further activities exist in the binary `saNN` files and nowhere else — and
`sar` renders only the activity you ask for, so they expire with the day file.
**`sa23` is overwritten 2026-09-23.**

Round 400 flagged copying the binaries as TIME-CRITICAL in prose. The next E
round — this one — opened to an unreachable box. So the remediation is emitted
as a runnable script (`bash -n` clean, verified in test) that tars the binaries,
captures every activity with an unambiguous marker, takes the journal
**unfiltered**, and re-audits itself with `--strict`.

### Two bugs I introduced and caught in my own module

Recorded because both are the kind that ship silently:

1. The first draft rendered required `-B` (paging) as `-b` (block I/O) — a
   *different* sar activity — in the remediation it emits. Round 400's marker
   scheme `### SAR_<FLAG>_SA<NN>` upper-cases the flag, which merges `-B`/`-b`
   and `-S`/`-s`; only the column header distinguishes them. Fixed with an
   explicit `Activity` table carrying marker key and literal flag separately.
2. The generated plan emits multi-character keys (`SWAPSPACE`, `NET`, `CSW`)
   precisely to break that collision — and the section regex matched a single
   letter, so **the plan wrote markers its own auditor could not read**. A
   full-fidelity capture would have audited as missing every optional activity
   it had just successfully captured. Fixed, and pinned by
   `test_a_capture_matching_the_plans_markers_audits_as_COMPLETE`.

## 6. Two world-fact pins in the reachability suite, found by going down

Appending round 406's `down` record turned two green tests red. Neither is a
code regression; both encode a fact about the world.

- `test_real_log_second_outage_started_at_the_tailscale_last_seen` asserted
  `second["ongoing"] is (_last["verdict"] == "down")`. Round 352 wrote that
  derivation *specifically to stop pinning a world fact* — and it is correct
  only while the log has at most two down streaks. `_last["verdict"] == "down"`
  answers "is the box down **now**", i.e. whether the **last** streak is
  ongoing, not this one. Round 406 opened a third down streak and the assertion
  claimed the closed 298–346 outage was still running. Fixed to
  `second["ongoing"] is (second["end_round"] == _last["round"])` — a statement
  about the streak, unfalsifiable by a later unrelated outage.
- `test_a_capture_window_that_ends_before_the_log_does_loses_the_bound` (round
  382) truncated a capture one second before the newest record and asserted the
  final gap reverted to full length: `301.0 >= 16929.0`. But
  `max_unobserved_outage_s` is by definition the worst unwitnessed gap *inside
  an up streak* (`_worst(lambda v: v == "up")`) — a gap ending in a `down` check
  is a transition, and an outage cannot hide in it because the outage is what
  the check found. The fixture assumed the log ends in an up streak. Fixed to
  target the last gap the metric can actually see.

This is the same class round 382 fixed one layer up (an absolute time window a
growing file walks out of) and round 352 fixed one layer up from that. Each fix
removed the world-fact it could see and left one underneath.

## 7. Predictions scored — 9 HIT, 2 MISS, 1 PARTIAL of 12

| # | Prediction | Verdict |
|---|---|---|
| P1 | fwupd-refresh fires ≥ 10 times on 2026-08-31 | **HIT** — 13 |
| P2 | it is the most frequently firing non-excluded unit on sa31 | **HIT** — 13 vs 2 for the next |
| P3 | its `in_costly_bucket` count is exactly **1** | **MISS** — it is **2**. I conflated "sole-attributable" with "in a costly bucket"; it is in *both* of sa31's costly buckets, which briefly looked like evidence *for* the claim I was refuting (§3) |
| P4 | P(≥1 costly bucket by chance) > 0.15 | **HIT** — 0.3038 on sa31 |
| P5 | the correct verdict on item 3 is DROP | **HIT** |
| P6 | firing is irregular, gaps varying > 2× | **HIT** — 3.96× (24–95 min) |
| P7 | 0 `Finished` lines in the banked journal | **HIT** — and disclosed in the bank as already measured, so it is not evidence of foresight |
| P8 | interval-attribution unrunnable from banked data | **HIT** — 92.2 % of fires have no duration |
| P9 | re-running `cost_ledger` reproduces round 400's headline numbers | **HIT** — 62 / 6 / 1, byte-exact at 67,682,304 |
| P10 | `-r`,`-W` × 9 days; `-B` × 2 days; ≥ 8 further types × 0 days | **PARTIAL** — first two clauses exact. The "≥ 8" is unverified: I modelled **7** further activities and dropped `-y`/`-H` as not worth capturing, so the count I predicted was never tested |
| P11 | sa31 `-W` has < 84 buckets | **HIT** — 79 |
| P12 | ≥ 1 costly bucket on sa31 with no named fire | **MISS** — sa31's list is empty; both its costly buckets have named fires. The phenomenon is real but on the *other* day: sa30's single costly bucket (15:10:03, 6.83 MB) has **no named unit at all**, which is independent support for §3's null and is why the miss is worth more than the hit would have been |

## 8. Tests

| suite | result |
|---|---|
| `bash nuc/run_checks_fast.sh` | **638 passed, 0 failed**, `constant-audit 23 constants, 18 derived (0.783), 4 bare, 0 transform-risk`, **nuc-checks PASS** |
| baseline, measured not quoted | at HEAD the suite was **620 passed / 3 failed**. Subtracting this round's new file (untracked, so `git stash push -- nuc/` left it in place) gives **606**, which reproduces round 400's published figure exactly. 606 + 15 + 17 = **638** |
| the 3 failures at HEAD | not a code regression — all three are §6, triggered by round 406's own `down` record entering the live log |
| `nuc/tests/test_perturbation.py` | 50 → **65** (+15 attribution, 4 of them pinned to the real capture) |
| `nuc/tests/test_capture_manifest.py` | **17**, new |
| `nuc/tests/test_reachability_check.py` | **207**, two world-fact pins fixed |
| `bash skills/run_checks_fast.sh` | 7 checkers, **0 errors** after registering the new skill's 4 trigger cases and this round's ledger row (3 errors at first run: D002 description 1050 > 1024, P001 zero cases, K001 unscored bank) |

The regression tests read `state/nuc-capture-r400/` directly and are
**deliberately not skipped when it is absent**. It is the only copy of that data
off a box that has been unreachable since 16:30Z; a missing capture is the
failure, not a reason to pass quietly.

## 9. Hygiene

- **No contact with the box was possible.** Two ssh attempts, both timed out,
  then stopped per CLAUDE.md. No `scp`, no writes on the box, no unit touched.
- **Port 8001 never contacted. No engine request of any kind.** Every module
  added this round is pure text-in/dict-out and opens no socket.
- `/work/**` untouched (unreachable).
- Local writes only: `nuc/`, `skills/`, `state/`, `knowledge/`.
- `state/nuc-capture-r406/` holds the derived intermediates (split `-W` tables,
  two ledgers, the evidence JSON) so §3 and §4 are re-runnable without re-deriving.

## 10. Next E round, in order

1. **The box is down. First action is a reachability check; if it is up, run
   `python3 nuc/capture_manifest.py plan --capture state/nuc-capture-r400 > /tmp/cap.sh && bash /tmp/cap.sh`
   before anything else.** One command, ~2 MB, closes all three blocking gaps
   and self-verifies. `sa23` dies 2026-09-23; sa24 on 09-24, and so on.
2. With `Finished` lines in hand, run the interval-attribution the banked data
   could not support (§5), and re-grade the 02:00:05Z event. It is currently
   **unexplained**, which is where round 388 left it.
3. Determine why `fwupd-refresh.timer` fires ~hourly rather than daily — 36
   fires in 36 h. Needs `Failed`/`Finished` lines to separate a retry loop from
   a healthy re-trigger. This is a real operational oddity on the box,
   independent of the attribution question.
4. `attribution_evidence` returned `supported: []` over the whole boot. Either
   the ledger's window (10 min, `sar`'s cadence) is too coarse to attribute
   anything on this box, or attribution needs a second channel. Round 394's
   `sar -r` `Committed_AS` steps are the obvious candidate and are banked for
   all nine days — this is runnable offline **right now**, on the next down round.
5. Still blocked on the operator: `--cap 196` and the E3 A/B. Round 400's
   addendum applies unchanged, plus: any A/B must record how many units share
   each bucket, and now also each unit's occupancy over the whole record.
6. Round 370's item 3 still needs a FRESH boot. The 43e0c767 streak has ended,
   so the next up-round may satisfy it for free — capture `uptime -s` first.
7. harness(A) still owns wiring `nuc/run_checks_fast.sh` into `run_driver.sh` —
   **0 references, fourth round carried.** Note that `skills/run_checks_fast.sh`
   IS wired (round 363), so a basename grep lies.

# Round 490 (NUC-integration E) — the record that was already in the repo

**Track:** NUC-integration(E). **Base:** `d67034e`. **Bank:**
`nuc/predictions-e-round490.md`, committed at `a0f244d` before any quantity in
§2-§8 was measured.

**Box: DOWN the whole round.** Two tailnet probes (~10:59:2xZ, 11:00:11Z), both
`Connection timed out` rc 255; CLAUDE.md's two-failure rule fired. All findings
below are offline work on captures already committed to this repo.

**Artefacts:** `nuc/record_union.py` (new), `nuc/tests/test_record_union.py`
(new, 34 tests), `nuc/tests/test_lead_lag_blocks.py` (new, 21 tests),
`nuc/perturbation.py` (+`block_lead_lag_profile`,
`block_shift_null_lead_lag`, `effective_cells`, `gap_blocks`),
`nuc/dose_response.py` (+`split_scopes_by_round`),
`state/nuc-record-union/` (the built union), `state/nuc-capture-r490/`,
`state/nuc-reachability-log.jsonl` (66 rows).

## 0. The one-line finding

**Every window-level number this track has published was computed from round
424's capture, and a strictly better record has been sitting in this repo
since round 478 — unread.** `grep -rl nuc-capture-r478 --include='*.py'`
returns `fossil_ledger.py` and two test files; `perturbation.py` and
`dose_response.py` name r424 and nothing else. Round 472's central limitation
— *"round 424 is the observer's largest intervention and the instrument cannot
see it, because round 424's capture IS the end of the record"* — was closed by
files already committed, offline, on a round where the box was unreachable.

The corollary is sharper than the fix: **the newest capture is the smallest
record.** r484 holds 8 dates, r424 holds 10, r478 holds 11, and their union
holds 12. A round reaching for "the latest capture" gets the least data,
because the 00:07 sweep round 484 watched fire deletes the front while each
capture only adds to the back.

## 1. `nuc/record_union.py` — the sar and journal record, unioned

Round 484 built `fossil_ledger.py`, which unions the *sysstat sweep evidence*
across every capture and finds 11 fire instants where the newest capture alone
finds 8. The same nine capture directories carry the `sar` day-files and the
`systemd` journal that `perturbation.BucketMap` is built from. Nothing had ever
unioned those.

Three rules, taken from `fossil_ledger.py` because they were right there:
agreement is the null hypothesis; the comparison is per timestamped ROW, not
per section; an unusable input is named, not skipped.

**Result, over all nine captures:**

| | sar dates | paired days | poolable buckets | journal unit-starts |
|---|---|---|---|---|
| `nuc-capture-r424` | 10 | 10 | 991 | 1652 |
| `nuc-capture-r478` | 11 | 9 | 896 | 1344 |
| `nuc-capture-r484` (newest) | 8 | 8 | 661 | 1367 |
| **union** | **12** | **12** | **1145** | **1938** |

`n_conflicts` **0** across **120 sections**; `n_merged_sections` **0** — every
section had one capture that was already a row-superset of the others, which is
exactly the shape "two reads of one append-only file" predicts. 4 captures
read, **5 named unusable** (r406/r430/r460/r466/r472 carry no sar at all — all
down rounds).

**The `Average:` trap, predicted and confirmed (bank P3).** `sar` computes its
trailing `Average:` over the rows it was given, so r424's `2026-09-01` average
is over 3 samples and r478's over 76. A byte- or line-level diff calls that a
conflict. It is not one, the comparison is per timestamped row, and
`test_the_average_line_alone_never_makes_two_captures_disagree` holds it.

**The journal union is a MULTISET, and the first draft's own `--strict` gate
caught that it had to be.** Every journal in this repo holds 2-3 lines that are
byte-identical to another line in the *same* file:

```
2026-08-26T12:23:21+00:00 pgain-nuc systemd[1]: Reloading...
2026-08-30T00:32:34+00:00 pgain-nuc systemd[1]: Starting rsyslog.service - ...
```

Those are two real events inside a log whose resolution is one second, not one
event written twice. Whole-line dedup deletes one of each, and
`parse_unit_starts` counts fires, so the deletion is a fire. The rule is
per-line multiplicity: a line appearing k times in the capture that shows it
most appears k times in the union. `dedup_is_lossless` is then **re-derived**
against every capture rather than asserted.

Separators (`-- Boot <id> --`) carry no timestamp, so they are attached to the
line that FOLLOWS them and identified by content. **7 separators kept, 0
attachment disagreements** — journald has not (yet) moved the front of a boot
between two captures in a way this can see.

**Unioning only half the record buys much less than half the gain.** Union sar
with the *newest* journal alone: **10 paired days, 08-23 and 08-24 dropped** —
those two dates exist as sar day-files but the only journal that reaches them
is r424's. Bank P5 predicted at least three such dates; the answer is two.
**MISS**, and the same shape as round 484's three misses: extrapolating how bad
a known-bad thing is from one prior observation, and over-predicting.

## 2. Round 472's item 5, closed, and the answer is zero

`dose_response.py run` re-run twice — once on r424 (round 472's record) and
once on the union. r424 re-derives round 472's published numbers exactly:
**42 scored, 28 full-record**, `bytes_landed` rho **−0.2767** (round 472
published −0.277).

On the union: **46 scored, 31 full-record.**

| round | coverage on r424 | coverage on union | swap bytes | bytes landed |
|---|---|---|---|---|
| **424** | `partial` | **`full`** | **0** | **2 896 862** |
| 430 | `none` | **`full`** | 0 | 44 072 |
| 478 | untestable | **`full`** | 0 | 5 358 |
| 484 | untestable | `partial` | 0 | 3 006 |
| 466, 472 | untestable | `none` | 0 | 8 272 / 0 |

**Round 424 pulled 2.9 MB off the box — nine times the next heaviest round —
and its window contains zero swap bytes.** That is the measurement round 472
said it could not make.

**And the honest caveat, which is the whole of what the union did to the
regression.** All three new full-record windows have response exactly 0. A
zero-response point cannot create an association and can only dilute one, so
the *direction* of every coefficient shift is predictable from that fact alone
and none of it is new evidence about any dose. `response_total` is
**2 382 643 200 B on both records** — the union added 154 buckets and **not one
new costly bucket**, because the box has been at 16.9 % memory with swap 0
since the 09-01 reboot.

| dose | rho (r424, n=28) | rho (union, n=31) | p (union) | control |
|---|---|---|---|---|
| `n_logins` | +0.2568 | +0.3024 | 0.0964 | |
| `n_calls` | +0.2414 | +0.2895 | 0.1109 | |
| `bytes_landed` | −0.2767 | −0.3242 | 0.0750 | |
| `local_calls` | −0.3279 | −0.3911 | **0.0312** | **control** |
| `local_bytes` | −0.3985 | −0.4376 | **0.0149** | **control** |
| `transcript_bytes` | +0.3735 | +0.2677 | 0.1442 | control |

Verdict unchanged: **NULL — no dose reaches p ≤ 0.05.** But note what does:
**the only two terms below 0.05 are negative controls, and both point the wrong
way.** A control crossing significance is a statement about the design, not
about local work; nine correlated terms with no multiplicity correction expect
0.45 crossings by chance. Round 472 flagged `local_bytes` at p 0.037 as
"nearest significance" and it has gone further, not away.

## 3. THE FINDING: `n` was never 454

Round 472 published: *"At login-instant resolution (n=454) the coincidence is
strong and robust; at round-window resolution (n=28) there is nothing"*, and
read the gap between the two as a statement about what the effect is like — per
login, roughly fixed, not proportional to the work.

Part of that gap is arithmetic. An E round makes about fourteen logins over ten
to twenty-five minutes. A bucket is 600 s wide. **Most of those logins are in
the same bucket as each other**, so they are not 454 draws on the bucket grid.

`effective_cells` counts the independent unit — one round meeting one bucket,
however many times it knocked:

```
n_fires                484        (the population, on the union record)
n_fires_landed         478
n_cells                 69        <- the number of independent observations
n_cells_costly          10
rate_per_fire       0.20084
rate_per_cell       0.14493
fires_per_cell      min 1, median 6, mean 6.93, max 34
```

**The two resolutions round 472 contrasted are 69 and 28, not 454 and 28.**
That is a factor of 6.6 closer than the published framing, and it is most of
the reason the two analyses looked like they were about different things.

**The coincidence survives the collapse.** `shift_null_covered` run on the
per-CELL population: observed 0.1449 vs null mean 0.0381, **p 0.0065**
(per-fire: 0.2008 vs 0.0371, p 0.0010). So the association is real; it is
simply carried by five times less data than the published `n` implied.

**Two independent groupings agree exactly.** `gap_blocks(1500 s)` derives the
blocks from the journal's own silences and knows nothing about rounds;
`split_scopes_by_round` derives them from the driver transcripts and knows
nothing about the journal's gaps. Both return **34 blocks and 69 cells**.

**The control, at cell resolution.** The box's other logins, gap-blocked the
same way: 19 blocks, **86 cells, 4 costly, rate_per_cell 0.0465** against ours
at **10 of 69, 0.1449**. Round 472's split conclusion — the association is this
program's own logins — holds when the unit of observation is fixed.

## 4. Round 472's item 2 — the shoulder does NOT survive. §4b is WITHDRAWN

Round 472 measured `ours` peaking at offset 0 (rate 0.217) with a right
shoulder (+1 0.099, +2 0.061) about twice the left, called the asymmetry
"suggestive, not established", and named the confound itself: a login displaced
by one bucket can land where a LATER LOGIN OF THE SAME ROUND already sits, so
clustering and persistence make the same shoulder.

`block_lead_lag_profile` splits every landed fire at every offset into
`sibling_occupied` (the landing bucket already holds another fire of the same
round — the sibling is a sufficient explanation) and `clean` (it does not).
On the union record, 34 round-blocks, 484 fires, 409 sibling co-occupancies:

| offset | landed | rate | clean n | rate_clean | sib n | rate_sib |
|---:|---:|---:|---:|---:|---:|---:|
| −2 | 478 | 0.0272 | 416 | 0.0216 | 62 | 0.0645 |
| −1 | 476 | 0.0504 | 318 | 0.0157 | 158 | 0.1203 |
| **0** | 478 | **0.2008** | **7** | **0.0000** | 471 | 0.2038 |
| +1 | 471 | 0.0913 | 188 | 0.0426 | 283 | 0.1237 |
| +2 | 476 | 0.0567 | 367 | 0.0490 | 109 | 0.0826 |

* **At offset 0, seven of 478 landed fires have their bucket to themselves.**
  The "peak at zero" is a statement about buckets holding two or more logins of
  one round; the login is not the unit, the burst is. This is §3's finding
  arriving from the other direction.
* **At +1, 283 of 471 landings (60 %) are sibling-occupied**, at rate 0.1237
  against 0.0426 for the 188 clean ones. Most of the shoulder is siblings.
* **Mean asymmetry (after − before): all fires +0.00519, clean −0.00027.** It
  is gone.

And `block_shift_null_lead_lag` — round 472's item 3, the null the profile
never had — agrees. Each round's login train is translated rigidly by its own
whole-bucket offset, so within-round spacing and burst shape survive and only
grid alignment is destroyed. 1000 draws:

| statistic | observed | null mean | null p95 | p |
|---|---:|---:|---:|---:|
| `rate_at_zero` | 0.20084 | 0.03603 | 0.11186 | **0.0010** (= p floor) |
| `rate_plus_one_bucket` | 0.09130 | 0.03592 | 0.11502 | 0.0860 |
| `rate_minus_one_bucket` | 0.05042 | 0.03704 | 0.11268 | 0.2980 |
| `asymmetry_after_minus_before` | 0.00519 | −0.00125 | 0.04011 | **0.4060** |
| `asymmetry_..._clean` | −0.00027 | −0.00131 | 0.04454 | 0.4890 |

**Verdict.** The peak at zero is solid — it beats a null that preserves the
login train, at that null's floor. **The right-shoulder asymmetry of round
472's §4b has no support and is withdrawn**, loudly and here, as round 472's
item 2 asked. The causal reading it carried ("a login's cost outlives the
login") is not established by this record.

**Two caveats this round will not bury.** (a) The clean/dirty split is not
randomised: sibling-occupied fires come disproportionately from the busiest
rounds, so "sibling-occupied buckets are costlier" is partly the original
hypothesis and not only an artefact. (b) The clean subsets differ in size
across offsets — 7 at zero, 188 at +1, 478 at ±6 — so the clean profile is not
one population read at thirteen displacements, and the near-field clean ratio
(+1 0.0426 vs −1 0.0157) should not be read as a surviving shoulder.

**Bank P9 was a design claim and it HELD.** A block shift destroys a clustering
shoulder exactly as well as a persistence shoulder, so it answers item 3 and
cannot answer item 2. They are two instruments and the round shipped two.

## 5. The null is weaker than it was designed to be, and it says so

`block_shift_null_lead_lag` shifts by whole 600 s buckets on the reasoning that
two fires sharing a bucket before the shift still share one after it. It
reports `sibling_structure_preserved_in_all_draws`, and on the live record that
field is **False — 0 of 1000 draws.** Measured over 200 draws: observed 409
co-occupancies, null **median 256 (62.6 % of observed)**, range 131-360.

The cause is the record's holes. Where sar misses samples it closes one WIDE
bucket rather than leaving a gap, and where the box was down there is no bucket
at all, so a train shifted onto either stops being a train of 600 s
co-occupants. The design assumption was wrong; the field that was added to
check it is what said so, on its first live run. **The direction of the
resulting bias on `p` is NOT established by this round** and is a next step —
the honest statement today is that the null preserves about five-eighths of the
clustering it was meant to preserve exactly.

## 6. Round 484's items 2 and 4, paid

**Item 4 — `fossil_ledger.py append` every round.** Run over
`state/nuc-capture-r*` including this round's: exit 0, **ledger byte-identical,
11 fire instants, 0 conflicts**, `verify --strict` 0. `nuc-capture-r490` is
correctly named unusable (a tailscale-status-only capture, no boot table).
Bank P11 **HIT**.

**Item 2 — `margins --strict` on every capture.** Nine captures, and the honest
answer is that **three can be scored**: r424 (7 fires), r478 (5), r484 (6), all
exit 0. **r400 exits 1** for a named reason — it has no `journal-pid1-full.txt`
at all, so `margins` has nothing to read. Five have no derivable `now`
(no boot table, none declared) and are skipped by name. Bank P10 **HIT**.

**And running `margins` on the UNIONED journal decides more than any capture
can.** 8 fire instants against r424's 7 and r484's 6 — and three verdicts
(`2026-08-24`, `-25`, `-26`) flip from `sweep_pending` to **`sweep_missed`**,
because deciding them needs a journal that reaches back to 08-24 *and* forward
past their eighth day. Only r424 does the first and only r484 does the second.
The `-3.0 s` orphan round 484 found is reproduced exactly.

## 7. P15 — did round 484's capture cost the box its uptime? No

The box was last seen **2026-09-04T02:14:05.1Z**, **34m53s** after round 484's
probe at 01:39:42Z, on a boot that had run 16h37m. That is the shape the whole
observer-effect thread is about, and it is the kind of coincidence that becomes
folklore if nobody measures it.

Five up→down transitions exist in the reachability log; four have a `LastSeen`
to place. For each, `u` = (last-seen − last up probe) / (first down probe −
last up probe), which is U(0, 1) if the box dies uniformly inside the window
between two E-round probes:

| last UP | first DOWN | gap (min) | window (min) | u |
|---|---|---:|---:|---:|
| r292 | r298 | 143.9 | 147.1 | 0.9788 |
| r400 | r406 | 195.7 | 282.1 | 0.6935 |
| r430 | r436 | 277.0 | 337.6 | 0.8204 |
| **r484** | **r490** | **34.4** | **560.5** | **0.0613** |

Fisher's method against the small-`u` alternative: **X² = 6.753, df = 8,
p = 0.5635.** Three of four deaths land LATE in their window. **This round's is
the only early one and one draw at the 6th percentile is not evidence.** The
answer to P15 is a clean null, and it is worth having written down before the
next early death makes it look like a pattern.

## 8. Tests, and the mutation pass

`nuc/tests/test_record_union.py` 34 tests, `nuc/tests/test_lead_lag_blocks.py`
21 tests. **29 mutations; first pass 24 killed / 5 SURVIVED.** All five were
diagnosed rather than papered over, and they were four different failures:

1. **Dead code.** `split_section`'s explicit `Average:` branch sent the line to
   `tail`; so did the branch below it, because `seen_data` is always True by
   the time sar prints an average. Both arms reached the same place. **Deleted**
   (round 466's F7 rule), and the test re-pointed at a mutation that is real —
   widening `_TIME_TOKEN` so `Average:` becomes a row.
2. **An undetectable field.** Hard-coding `dedup_is_lossless = True` survives,
   because the union is lossless by construction and no input this module can
   produce makes it False. That is a true statement about the field: it is a
   tripwire for a future change to the union rule, not for today's code. The
   falsifier was re-pointed at `_multiplicity_losses`, which IS decidable, and
   given a case where it must return `[]`.
3. **A test that checked the report and not the behaviour.** Flipping
   "earliest separator attachment" to "latest" moved where the separator is
   EMITTED and left the disagreement record alone, which is all the test read.
   It now asserts the emitted position.
4. **Two missing boundary cases.** `gap_blocks` `>` vs `>=` needed a step of
   exactly `gap_s`; the co-occupancy counter needed a draw that does NOT
   preserve, which on a fully-covered synthetic fixture cannot happen — so the
   test now builds a second `BucketMap` with an hour missing from day 1, which
   is the same mechanism that makes the field False on the live record.

**Second pass: 29 of 29 killed, 0 survived.** Three more falsifiers were
added in §13 and killed on their first pass: **32 mutations, 32 killed** for
the round.

Full suite: `nuc/tests` — see §10.

## 9. Predictions scored

`nuc/predictions-e-round490.md`, banked at `a0f244d`.

| # | prediction | verdict |
|---|---|---|
| P1 | union covers 12 dates, 08-23..09-04, 09-02 absent | **HIT** — exactly |
| P2 | 0 conflicting rows across shared dates | **HIT** — 0 / 120 sections |
| P3 | a naive line diff trips on `Average:`; the row diff stays clean | **HIT** |
| P4 | union `n_paired` > every single capture; 11 or 12 | **HIT** — 12 vs 10 |
| P5 | ≥3 dates left `sar_only` by using the newest journal alone | **MISS** — 2 |
| P6 | union journal holds more unit starts than any capture | **HIT** — 1938 vs 1652 |
| P7 | `n_full_record` > 28; 430/478/484 move off `none`/`partial` | **HIT** — 31; 484 reached `partial`, not `full` |
| P8 | OPEN; clean +1 rate ≤ all-fires +1 rate | **KEPT + HIT** — 0.0426 ≤ 0.0913; §4b withdrawn as promised |
| P9 | the block-shift null answers item 3 and NOT item 2 | **HIT** |
| P10 | `margins --strict` not clean on all nine captures | **HIT** — r400 exit 1 |
| P11 | `fossil_ledger append` adds nothing; 11 instants, 0 disagreements | **HIT** |
| P12 | no file builds a `BucketMap` from r478 or r484 | **HIT** — grep confirms |
| P13 | ≥1 mutation survives the first pass, 0 the second | **HIT** — 5, then 0 |
| P14 | `nuc/tests` > 1076 green | see §10 |
| P15 | OPEN; report the down-transition distribution honestly | **KEPT** — §7, p 0.5635, n=4 |

**13 HIT / 1 MISS / 2 OPEN-KEPT of 15** (P14 in §10). The one miss is the same
shape as round 484's three: a single prior observation extrapolated, and
over-predicted. P7 is scored HIT on its main clause with the sub-clause noted:
round 484 reached `partial`, not `full`, because its own window is the end of
the union's record — the identical mechanism that made round 424 `partial` on
r424, one capture later.

## 10. Suite

`nuc/tests` **1076 -> 1131, all green, 564 s** (run alone; `nproc` is 1). The
two new files collect **55**; 1131 − 55 = 1076, which is exactly where round
484 left it. Bank P14 **HIT**.

**Two tests went red on the first full run and both were mine to fix.**

1. `test_fossil_ledger.py::test_the_live_union_beats_every_single_capture`
   pinned `n_captures_unusable == 5` and this round banked
   `state/nuc-capture-r490` — a down-round capture carrying a `tailscale
   status` and nothing else. **The corpus grew; the ledger did not break**,
   and it will happen on every future down round. The unusable count is now
   derived from the directory listing; `n_captures_read == 4` stays literal,
   because that one is a claim about the ledger rather than about how many
   directories exist. This is the "your own artefacts are in the corpus"
   failure, arriving through a test written six rounds earlier.
2. `test_constant_audit.py::test_the_fast_check_runs_green_on_this_tree` runs
   `run_checks_fast.sh` end to end, which runs the strict instruments and the
   suite; it was red because (1) was. It passes solo in 161 s and in the full
   green run.

## 11. Skill

`skills/newest-snapshot-is-not-the-record/SKILL.md` — the reusable technique:
a snapshot of a rotating source is a WINDOW, so "newest" is a claim about the
back edge only, and the record you want is the union you already have. Nine
numbered steps (inventory before choosing; key on (object, period) not on the
file name; union at the level the data is WRITTEN at and as a multiset;
expect a chain of prefixes; never diff whole files; name the unusable inputs;
price the union against the best single snapshot AND against the half-job;
re-derive the old numbers first; say what the extra data actually did), six
pitfalls, and a Verification section with two runnable commands.

Three positive trigger cases and one discriminating negative added to
`skills/trigger-cases.json` (`nsr-near`, `nsr-mid`, `nsr-far`,
`nsr-neg-one-snapshot` — one snapshot and no analysis reading from it, which
must NOT fire). `skill_lint --house --strict` 0 errors 0 warnings after the
description was cut from 1102 to 970 chars. Registered unprobed in
`state/known-unprobed-skills.json` with an owner, a reason, and a scorable
prediction about which case is weakest — round 405's rule, that naming a
sibling by reading loses 5 times out of 5, applied rather than quoted.

## 13. The round's own final check caught two defects in the round's own CLI

The last thing this round ran was the invocation its own artefacts document —
`python3 nuc/record_union.py sar --captures 'state/nuc-capture-r*' --strict`,
the exact string written into `skills/newest-snapshot-is-not-the-record/SKILL.md`,
into this round's next-steps, and into the missions addendum. It exposed two
defects, and the second is worse than the first.

1. **The CLI does not glob.** `fossil_ledger.py` expands every `--captures`
   pattern; `record_union.py` did not. A quoted glob reaches the process as one
   literal path that does not exist, so every documented invocation read
   **zero** captures.
2. **And `sar --strict` therefore exited 0.** Zero captures read means zero
   sections, which means zero conflicts, and the gate tested conflicts only.
   **A gate that passes on an input it never read is worse than one that
   fails** — `frame --strict` at least exited 1, because it asks for a gain
   and got none.

Both fixed: `expand_captures` (matching `fossil_ledger`'s behaviour exactly,
including passing a no-hit pattern through so the report names it) and
`_sar_strict_fails`, which now fails on `n_captures_read == 0` as well as on a
conflict. Three new falsifiers, **all killed on the first mutation pass** —
total for the round **32 mutations, 32 killed**.

The documented commands now run as documented: `sar --strict` **0** with
4 read / 6 named unusable / 12 dates / 0 conflicts; `frame --strict` **0** with
union 12, best single 10, **gain 2**; and `sar --captures 'state/no-such-*'
--strict` exits **1**.

**The same brittleness fixed once was still present twice.**
`test_the_live_captures_union_without_a_single_conflict` pinned
`n_captures_unusable == 5`, exactly as `test_fossil_ledger.py` did — and this
round had already fixed the fossil one an hour earlier, in this same file, for
this same reason. Both are now derived from the capture list. Fixing an
instance is not fixing the class, and the second instance was in code this
round wrote after diagnosing the first.

## 12. What this round did NOT do

* **`test_perturbation.py` still has never been mutation-tested.** Round 472
  asked for it (item 4), rounds 478 and 484 carried it, and round 490
  mutation-tested only its own two new files — the third consecutive round to
  do exactly that. It is the file carrying every published number in this
  track.
* **The block-shift null's clustering loss is measured and not corrected.**
  62.6 % preserved, direction of the bias unknown.
* **No capture was taken**, because the box was down. Every day the box stays
  down, the 00:07 sweep takes another day off the front and the union's
  08-27 goes on 09-05.
* **The `%vmeff` / `pgsteal_kswapd` residual** was not touched, for an eighth
  E round.

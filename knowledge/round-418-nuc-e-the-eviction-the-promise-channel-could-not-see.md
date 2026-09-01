# Round 418 — NUC-integration(E): the eviction the promise channel could not see

**Box: DOWN.** Sixth consecutive E round with no NUC. All work below is over
data already in git (`state/nuc-capture-r400/`), and nothing here opened a
socket.

Two items from round 412's handoff, both explicitly marked runnable offline:

* **item 2** — *"the 04:00:03 reclaim is newly unexplained in a SPECIFIC way.
  Round 412 showed nothing was allocated there, so the question is no longer
  'which unit allocated' but 'what touched already-committed pages'. `sar -B`
  (`pgscan`/`pgsteal`) is banked for sa30/sa31 in `sar-all.txt`, this round did
  not read it."*
* **item 3** — *"Stitch consecutive `sar` day-files. A level channel loses each
  day's first bucket, and three units vanish from the commit family for exactly
  that reason — 16 tested units → 13."*

Predictions banked BEFORE measuring: `nuc/predictions-e-round418.md`
(D-013). Scored in §8.

---

## 1. Reachability — the same outage, still

```
$ python3 nuc/reachability_check.py check --round 418
  "checked_at_utc": "2026-09-01T03:11:39Z",   "verdict": "down",
  "ssh_returncode": 255,  "ssh_stderr": "connect to host 100.78.44.111 port 22: Connection timed out",
  "tailscale_online": false,  "tailscale_last_seen_utc": "2026-08-31T16:30:00.1Z"
```

`tailscale_last_seen_utc` is **byte-identical to rounds 406 and 412**: one
continuous outage, ~10.7 h old at probe time by tailscale's own clock. Two ssh
attempts (tailnet `100.78.44.111`, then LAN `192.168.1.37`), both rc 255,
both `Connection timed out`; probing stopped there per CLAUDE.md.

One coordinate correction, found by making the second attempt rather than
assuming it: **`~/.ssh/id_ed25519_nuc` does not exist on the driver host.**

```
Warning: Identity file /home/pgain/.ssh/id_ed25519_nuc not accessible: No such file or directory.
```

CLAUDE.md offers the LAN path as `ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37`
and scopes it "Mac-adjacent hosts only" — true, and now stronger: the driver
box has no key for it at all, so on THIS host the LAN path is not a fallback
under any box state. `state/nuc-missions.md` wins per CLAUDE.md and already
leads with the tailnet path; this is a note for whoever reads the LAN line and
expects a second chance.

---

## 2. Item 2 — what touched already-committed pages

`sar -B` was captured on 2026-08-31 by round 400 and sat unread for nine
rounds. Round 412 established that `Committed_AS` does not move at all at
04:00:03 and correctly refused to conclude anything from it. Here is the same
bucket on the column family that can see it:

```
$ python3 nuc/perturbation.py reclaim --sar-b <sa31 -B> --date 2026-08-31
  "largest_bucket": {
    "time": "04:00:03",  "kind": "kswapd",
    "scan_kswapd_s": 1207.0,  "scan_direct_s": 0.0,  "steal_s": 401.7,
    "scanned_pages": 724200,  "stolen_pages": 241020,
    "stolen_bytes": 987217920,          # 941 MiB, as reported
    "paged_in_kb": 332856,              # 325 MiB read back from disk
    "paged_out_kb": 466704,
    "major_faults": 0.28,               # 168 over the bucket
    "vmeff_pct": 33.28 }
```

**The finding.** The commit channel is not a coarser instrument pointed at the
same event. Run the two side by side:

```
$ python3 nuc/perturbation.py gap --sar-b <sa31 -B> --sar-r <sa31 -r>
  time       stolen_bytes   commit level_bytes   ratio
  00:40:05    272,228,352                   0     0.0
  02:00:05    272,498,688         150,622,208     0.553
  04:00:03    987,217,920                   0     0.0
```

At 04:00:03 the level channel's cost is **exactly zero bytes** against
~1 GB reclaimed. Not small — zero. That is not coarseness, it is a different
question: `Committed_AS` counts *promises*, and reclaiming a resident page
revokes no promise. The mapping stays, the commitment stays, the page goes.
An eviction is invisible to the commit channel **by construction**, and the
swap channel only sees the sub-case where the stolen page was dirty anonymous
memory that had to be written out.

So the two channels this program has been arguing about are not ranked. They
are blind in different directions, and the record's largest perturbations fall
in the direction neither of them faces.

### No allocation ever stalled

`pgscand/s` — direct reclaim, the path where an allocation waits — is
**0.00 in every bucket of both days**. Seven reclaim events, all kswapd,
none direct.

```
sa30: 139 buckets, 4 reclaim (2.9 %), 0 direct
sa31:  79 buckets, 3 reclaim (3.8 %), 0 direct
```

For the track's actual goal — making the box usable for Hermes — this is a
usable negative: memory pressure on pgain-nuc manifests as **page-cache
eviction and re-read**, not as allocator latency. Anyone chasing a stall
should be looking at `majflt`/`pgpgin` after an eviction, not at
direct-reclaim depth. And 04:00:03's 168 major faults against 325 MiB paged in
is ~1.9 MiB per fault, i.e. readahead — whoever read that 325 MiB was
streaming (`apt-daily`), not demand-faulting weights back in. Whether the
engine paid for the eviction later is **not visible in this bucket**, and
saying otherwise would be inventing the causal link this round is trying to
avoid.

### The %vmeff artifact, and why it is not noise

Six of the seven reclaim buckets report `%vmeff > 100` — pgsteal exceeding
pgscank+pgscand, impossible if the columns counted the same pages.

```
time       scan/s     steal/s   ratio   %vmeff   %vmeff/2
13:30:05    649.51    1297.55   1.9977   199.77    99.885
14:50:05     55.44     110.88   2.0000   200.00   100.000
15:00:05   3105.98    6211.80   1.9999   199.99    99.995
15:10:03    685.14    1361.24   1.9868   198.68    99.340
00:40:05     55.60     110.77   1.9923   199.23    99.615
02:00:05     80.60     110.88   1.3757   137.56    68.780
04:00:03   1207.00     401.70   0.3328    33.28    16.640

reported : 6 of 7 above 100 %,  max 200.000
halved   : 0 of 7 above 100 %,  max 100.000,  5 of 7 within 1 % of the ceiling
```

`%vmeff <= 100` is a theorem, not a convention — you cannot steal a page you
did not scan. Halving `pgsteal` restores it exactly: the maximum lands on
**100.000**, and five of seven pin against the ceiling rather than scattering
below it. A random undercount of `pgscan` would not produce a ceiling that
sharp.

Mechanism this predicts, stated so it can be refuted rather than believed:
modern kernels export `pgsteal_*` under two independent breakdowns in
`/proc/vmstat` — by actor (`pgsteal_kswapd`, `pgsteal_direct`,
`pgsteal_khugepaged`) and by page type (`pgsteal_anon`, `pgsteal_file`) —
which cover the same pages twice, while `pgscan_kswapd`/`pgscan_direct` are
read as named singles. A tool that totals the `pgsteal_*` family charges every
reclaimed page twice.

**The code does not apply the correction.** `ReclaimEvent` reports what the
file says; `reclaim_double_count_check()` reports the evidence and the
corrected view side by side. A silently halved byte count is exactly the kind
of number that gets quoted without its caveat. **Every reclaim byte-figure in
this file is therefore an upper bound with a factor-of-two question over it**
— 04:00:03 stole 941 MiB as reported, ~470 MiB if the hypothesis holds.

Falsified or confirmed on the next UP round by one read-only command:

```bash
grep -E '^pg(scan|steal)' /proc/vmstat
```

---

## 3. Item 3 — stitching, and why it made things worse

### The hole is in the rendering, not the archive

`sar` consumes the first record of each day-file as its reference point and
never prints it. The swallowed sample's timestamp is what it puts on the
*header* line:

```
sa30  header 00:40:05   first row 00:50:05 (restart_before)   last row 23:50:05
sa31  header 00:00:05   first row 00:10:05                    last row 13:10:05
```

So sa31's 00:00:05 sample exists in the binary archive and is missing only
from the text this program captured. The consequence for a level channel: the
stitched boundary bucket spans **1200 s, not 600** — and a fire inside it
shares it with ten minutes of the previous day.

`nuc/perturbation.py` now has `Stitch`/`stitch_from()`, and `LedgerEntry`
carries `bucket_span_s` so a double-width bucket cannot be read as a
ten-minute one. Four refusals, each because the naive version would have been
wrong in a specific way:

```
sa29 -> sa30   cannot stitch into 2026-08-30 00:50:05: it follows a LINUX RESTART,
               so its predecessor describes a different boot's address space
sa29 -> sa31   they are 2 day(s) apart, not 1
-r   -> -W     different columns -- these are two different sar activity types
max_span 900   1200s apart, more than max_span_s
```

The restart refusal is not hypothetical: differencing sa30's first row against
sa29's last would have booked the boot's whole 25 GB address space as one
bucket's cost.

### The three units come back

```
$ python3 nuc/perturbation.py ledger --sar-w <sa31 -r> --channel commit \
      --min-bytes 51200000 --date 2026-08-31 --stitch-prev <sa30 -r>:2026-08-30

                        without stitch    with stitch
n_unclassified                       3              0
n_buckets                           78             79
n_undefined_buckets                  1              0
n_costly_buckets                     1              1
n_fires_in_costly_bucket             1              1
```

`dpkg-db-backup`, `logrotate` (00:00:05) and `sysstat-summary` (00:07:05) all
land in sa31's 00:10:05 bucket. Recovered — and their bucket cost **0 bytes**,
because `kbcommit` is pinned at 30 634 440 kB across the boundary. Three units
returned; zero attributions did.

### Recovering data made the power floor STRICTLY WORSE

This is the part worth writing down.

```
                          without stitch    with stitch
n_units_tested                        13             16
n_costly_buckets (K)                   4              4
per_unit_bar                    0.003846       0.003125
max_testable_occupancy                54             52
testable_fraction_of_N            0.2454         0.2350
n_testable_units                       8              8
supported                             []             []
```

The three recovered units enter the Bonferroni family and bring no costly
buckets with them. K does not move, the per-unit bar tightens, and the
testable band shrinks by two occupancies. **More data, less power.** None of
the three is itself testable (occupancy 1, below the band's floor of 2), so
the stitch cost two occupancies of testable range and bought zero testable
units.

That is not an argument against stitching — the alternative was reporting 13
units and silently pretending 3 fires did not happen, which is worse. It is an
argument that *"we recovered more data"* is not by itself a claim of improved
evidence, and a family-corrected instrument is where the difference shows up.

### Known limitation, recorded rather than fixed

The stitched bucket's window is widened to its true 1200 s, but `cost_ledger`
filters fires by `date`, so a previous-day fire falling in that window is
dropped. On THIS record there is no victim — sa30's last non-instrument fire
is `fwupd-refresh` at 23:48:05, which belongs to sa30's own 23:50:05 bucket —
but the blind spot is real and is a next-step item, not a claim of
correctness.

---

## 4. The steal channel, graded end to end

`pgsteal/s` is a RATE column, so it drops straight into the existing
`cost_ledger` / `attribution_evidence` / `power_floor` machinery as a third
`Channel`. Pooled over sa30+sa31 at the swap channel's derived floor
(4 825 665 B, quoted because `CHANNEL_MIN_BYTES["steal"]` is `None` and the
code refuses to invent one):

```
n_buckets 218   n_costly_buckets 7   n_units_tested 16   n_testable_units 9
supported []    supported_was_reachable true
power: testable occupancies 2..97 (44.0 % of N)
```

**`supported: []` on this channel is a statement about the box, not about the
arithmetic.** That is exactly what round 412 said round 406's null was
missing, and it is the first null on this record that has it: nine units were
testable and 44 % of occupancies could have cleared the bar.

### The verdict does not turn on the threshold

```
min_bytes   4 KiB   1 MiB   4.83 MB   32 MiB   128 MiB   1 GiB
K               7       7         7        7         7       3
supported      []      []        []       []        []      []
```

Stable over five orders of magnitude. Reclaim on this box is **bimodal** — a
bucket steals 0 or ≥ 260 MiB — so no threshold in that range creates or
destroys a costly bucket. Contrast the commit channel, whose verdict round 412
showed moves with an unpinned threshold and is therefore a setting. A bimodal
cost distribution is what makes a threshold-free verdict possible, and it is
worth checking for before agonising over a floor.

### K by channel, same floor, same fires

```
swap    3      steal    7      commit    9
```

Reclaim is rarer than allocation and commoner than swap-out, as expected — and
the three channels disagree about *which* buckets, not just how many.
Pooled, `{pswpout > 0}` is a strict subset of `{pgsteal > 0}`: every bucket
that swapped out also reclaimed, and three buckets (all on sa30) reclaimed
without swapping. On sa31 alone the two sets are **equal**.

### The closest this record has come to an attribution

```
fwupd-refresh   n_fires 36   n_costly 4 of 7   n_clean 2   n_zero_byte 32
                p_chance 0.0154   p_family 0.2461 (16-way Bonferroni)
                testable true    verdict "coincidence"
```

`p_chance = 0.0154` is the smallest p any unit has reached on any channel on
this record, and it had ample power (`p_best = 2.0e-06`). It is still refused,
and the reason is `consistency = 0.111`: the unit fires 36 times and moves the
reclaim channel 4 times.

Two of those four are held **alone**, and their bucket values are
`110.88` and `110.88` pg/s — identical to four significant figures, eleven
hours apart, on different days. That is genuine within-unit replication of a
point estimate that the family test still rejects.

**Which raises a methodological problem this round found and did not fix.**
`consistency = n_costly / n_fires` conflates two different units: one that
does not cost anything, and one whose cost is *conditional* on state.
`fwupd-refresh` runs hourly and does real work only when a remote metadata
fetch actually returns something new; 32 quiet fires are the expected
behaviour of a conditional job, not evidence against it. The consistency rule
as written cannot represent that, and every hourly-timer unit on this box has
the same shape.

### The biggest reclaim on the record has no named fire

```
sa30 costly_buckets_without_a_named_fire: ["13:30:05", "15:00:05", "15:10:03"]
     total_cost_bytes 22,072,860,672 (as reported; ~11 GB if halved)
     total_paged_in over the day 19.36 GB
```

Three buckets between 13:30 and 15:10 hold the overwhelming majority of the
boot's reclaim, and no systemd unit start covers any of them — while
`kbcommit` rises 18.43 GB at 13:30:05 and 7.32 GB at 15:00:05. That is the
engine load, and it is not a system unit: round 400 recorded the deployment
drift (the engine runs as user processes, `coli serve`). The attribution
machinery reports it correctly as *unattributed*, which is the right answer
and also the reason the journal half of the capture is the binding constraint
— `unit-starts.txt` covers system units only.

---

## 5. What changed in the code

`nuc/perturbation.py` (1285 → 1729 lines):

| new | what |
|---|---|
| `STEAL_CHANNEL` | `pgsteal/s` as a rate channel; `CHANNEL_MIN_BYTES["steal"] = None` |
| `Stitch`, `stitch_from()`, `auto_stitches()` | join consecutive day-files, with four refusals; `auto_stitches` keeps the REASON a day was not joined |
| `stitch_applies()` | "a stitch was supplied" and "a stitch did something" as two questions |
| `bucket_spans()` | a stitched bucket's true width |
| `bucket_costs(..., stitch=)` | a level channel's first bucket becomes definable |
| `cost_ledger(..., stitch=)` | plus `stitch`, `stitch_applied`, `n_wide_buckets`; per-bucket window from its own span |
| `LedgerEntry.bucket_span_s` | additive field; `attribution_evidence` still reads round-400 ledgers |
| `channel_sweep(..., stitch=)` | sweeps report `stitched_days` / `unstitchable_days` |
| `ReclaimEvent`, `reclaim_events()`, `reclaim_summary()` | `sar -B`, with the denominator kept and quiet buckets counted |
| `reclaim_double_count_check()` | the %vmeff ceiling test, correction NOT applied |
| `eviction_gap()` | reclaim bucket vs level channel, as a ratio |
| CLI `reclaim`, `gap`, `--stitch-prev`, `--stitch` | all four exercised by tests |

`reclaim_events` **raises** on a non-`sar -B` table rather than returning
zeros: a `sar -W` table parses cleanly and has no scan columns, so a lenient
reader would report "this box never reclaimed" — a false negative, which is
the precise claim the module exists to prevent.

---

## 6. Verification

```
nuc/tests/test_perturbation.py      96 -> 126 passed
nuc/tests/  (whole suite)          669 -> 699 passed, 69.4 s, exit 0
nuc/constant_audit.py audit nuc/   23 constants, 18 derived, 0.783, 0 transform risks (unchanged)
skills/run_checks_fast.sh          skill_lint 66 skills 0/0 · claim_check 159 resolved, 0 stale
                                   xref_check 0 NEW dangling · state_claim_check 0 stale of 12
repo-wide pytest                   2 failed, 811 passed
```

The two repo-wide failures were **K001 on this round's own bank** —
`test_carryforward_check.py::test_the_live_ledger_accounts_for_every_bank_on_disk`
and `test_corpus_check.py::test_live_corpus_is_clean`, both reporting
`('K001', 'nuc/predictions-e-round418.md', ...)`. That is D-013's second half
being enforced: predictions banked, not yet scored. Cleared by §8 + the ledger
entry, and re-measured after: **813 passed**, `corpus-check: 7 checker(s),
0 error(s), 6 warning(s)`.

`state_claim_check` on this round's own next-steps block reports **12 claims,
12 re-derivable, 0 stale, coverage 8/12 items (67 %)** — below round 417's
80 %, and the reason is worth stating rather than hiding: the metric credits
`Round N's item K` citations, and eight of this block's twelve items are new
work with nothing to cite. Four of them were given the command that
re-derives their number instead (round 414's own rule), which is what took the
coverage from 33 % to 67 %; the remaining four are genuinely uncheckable
offline because they name work on a box that is down.

### Reproducing every number in this file

```bash
python3 nuc/reachability_check.py check --round 418
python3 -m pytest nuc/tests/test_perturbation.py -q          # 126 passed
# the four r418 CLI verbs, against sections split out of sar-all.txt:
python3 nuc/perturbation.py reclaim --sar-b B31.txt --date 2026-08-31
python3 nuc/perturbation.py gap     --sar-b B31.txt --sar-r R31.txt
python3 nuc/perturbation.py ledger  --sar-w R31.txt --channel commit \
    --min-bytes 51200000 --date 2026-08-31 \
    --journal state/nuc-capture-r400/unit-starts.txt \
    --stitch-prev R30.txt:2026-08-30
python3 nuc/perturbation.py sweep --day R30.txt:2026-08-30 --day R31.txt:2026-08-31 \
    --journal state/nuc-capture-r400/unit-starts.txt --channel commit --stitch
```

---

## 7. Honest failures

1. **B5's second clause was wrong, and I had the data to know better.** I
   predicted 987 MB stolen was "larger than any `Committed_AS` step in the
   entire boot". The 13:30:05 step is **18.43 GB**. I had read only sa31's
   commit column and generalised over a boot whose first day I had not looked
   at — the exact error round 412 named about the journal ("true of the
   channel, false of the analysis").
2. **B9 predicted the steal null would be as powerless as the swap null.** It
   is not: `max_testable_occupancy` is 97, not single-digit. The prediction
   assumed the reason round 406's null was vacuous carried over to any
   channel; it was specific to K = 3.
3. **B7 over-claimed on sa31.** Predicted a strict superset there; the two
   sets are exactly equal, and the strictness lives entirely on sa30.
4. **The stitch's widened window has a blind spot I did not close.**
   `cost_ledger`'s date filter still drops previous-day fires that fall in it.
   No victim on this record; recorded in §3, not fixed.
5. **Every reclaim byte figure carries a factor-of-two question** that this
   round could not settle offline. The `/proc/vmstat` command that settles it
   is written down; nothing here is quoted without the caveat.
6. **The box was down for the sixth E round running**, so round 406's capture
   plan is carried a sixth time and `sa23` is still overwritten 2026-09-23.

---

## 8. Predictions scored (D-013)

`nuc/predictions-e-round418.md`, 22 items. **16 HIT, 1 PARTIAL, 2 MISS,
3 DISCLOSED-as-bookkeeping** (B1, B5-first-clause, C2 were labelled
already-read at banking time and are not evidence of foresight).

| # | verdict | measured |
|---|---|---|
| A1 | HIT | span 1200 s; 23:50:05 → 00:10:05; header stamp 00:00:05 |
| A2 | HIT | `n_unclassified` 3 → 0; exactly the three named units |
| A3 | HIT | recovered bucket 0 bytes; `kbcommit` 30 634 440 both sides |
| A4 | HIT | `n_buckets` 78 → 79, `n_undefined_buckets` 1 → 0 |
| A5 | HIT | 13 → 16 units, K = 4 unchanged, `max_testable_occupancy` 54 → 52 |
| A6 | HIT | refused, `LINUX RESTART` |
| A7 | HIT | refused, "2 day(s) apart" |
| A8 | HIT | rate-channel entries byte-identical; `stitch_applied` false |
| A9 | HIT | `bucket_span_s` 1200 on all three recovered entries |
| B1 | DISCLOSED | 3 scan buckets on sa31 |
| B2 | HIT | `pgscand/s` = 0.00 in every bucket of BOTH days |
| B3 | HIT | sa30 has 4 (predicted 2–8) |
| B4 | HIT | all 4 sa30 buckets exceed 100 %, at 198.68–200.00 |
| B5 | DISCLOSED / **MISS** | 987 217 920 B confirmed; "larger than any commit step" is false — 18.43 GB at 13:30:05 |
| B6 | HIT (stronger) | predicted ≤ 1 %; measured **exactly 0** |
| B7 | PARTIAL | strict superset pooled and on sa30; **equal** on sa31 |
| B8 | HIT | K_steal(sa31) = 3; 04:00:03 shared by 5 distinct units |
| B9 | **MISS** | `supported: []` held, but `d_max` is 97, not single-digit — the null has real power |
| B10 | HIT | `CHANNEL_MIN_BYTES["steal"] is None`; ledger refuses without `--min-bytes` |
| B11 | HIT | swap 3 < steal 7 < commit 9 at the same floor |
| C1 | HIT | 699 nuc tests, exit 0, no box |
| C2 | DISCLOSED | `id_ed25519_nuc` absent on the driver host |

Unpredicted findings: the `%vmeff` factor-of-two ceiling; the steal channel's
threshold-insensitivity across five orders of magnitude; `fwupd-refresh` at
`p_chance = 0.0154` with a twice-replicated 110.88 pg/s point estimate; and
`consistency` conflating "costs nothing" with "costs conditionally".

---

## 9. Handoff

1. **When the box comes up, `grep -E '^pg(scan|steal)' /proc/vmstat` before
   anything else.** One read-only command settles whether every reclaim byte
   in this file is right or double. Add it to the capture manifest.
2. **A future capture should take `sar -B` for every banked day, not two.**
   `sar -r` and `sar -W` cover sa23–sa31; `-B` covers sa30–sa31 only, and it
   is now the channel that sees the most.
3. **The day-boundary sample is recoverable at capture time and nobody has
   tried.** `sar` swallows each file's first record; whether `sadf` emits it
   is a one-command test on the box and would remove the 1200 s stitch
   entirely.
4. **`consistency` needs a conditional-work variant** (see §4). Every hourly
   timer on this box is penalised for the fires where it correctly did
   nothing.
5. **Close the stitched bucket's previous-day blind spot** in `cost_ledger`
   (§3).
6. **`nuc/capture_manifest.py plan` is carried a SIXTH time**; `sa23` is
   overwritten 2026-09-23.

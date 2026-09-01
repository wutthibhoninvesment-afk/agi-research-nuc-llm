# Round 424 (NUC-integration E) — the plan the outage outlived

**Date:** 2026-09-01 · **Box:** UP, boot `f13afb47`, `uptime -s 2026-09-01
05:33:27Z`, 2 h 36 m at first contact — a boot this program has never seen.
**Predictions (D-013):** `nuc/predictions-e-round424.md`, written before any
measurement. **Capture:** `state/nuc-capture-r424/` (3.2 MB).

---

## 0. The one-paragraph version

Rounds 406, 412 and 418 each found the box down and each carried the same
instruction forward: *if UP, run
`python3 nuc/capture_manifest.py plan --capture state/nuc-capture-r400` before
anything else.* Seventh carry. Round 424 found the box up and ran it — and
the plan was wrong, in a way that was **caused by the thing that let it run**.
Step 3 was `journalctl -b`. The outage ended with a **reboot**, so `-b` meant
2 h 40 m and 81 unit fires in place of 8 d 18 h and 1652. The audit the plan
ends with could not see that: run on both captures it returned the *same
verdict, same gap count, same `durations_derivable_fraction` 1.0*. And the
constant the plan printed about when the data expires — "sa23 is overwritten
on 2026-09-23" — was wrong by 21 days. `HISTORY=7`; `sa23` was scheduled for
deletion at **2026-09-02 00:07 UTC**, about fifteen hours after this round
captured it.

---

## 1. A remediation plan is exposed to whatever clears its precondition

This is the generalisable finding and it is not about systemd.

`capture_manifest.py plan` exists because round 400's capture was grepped
`Starting|Started` and lost every `Finished` line, so 92.2 % of unit fires had
no derivable duration. Round 406 wrote the fix as a *script* rather than prose,
on the explicit reasoning (in its docstring) that "a command can be run in the
first thirty seconds of a round; a paragraph has to be read, understood and
retyped first." That reasoning is correct and the script did its job.

But the script is a **pinned artifact**, computed from the box's state on
2026-08-31, and it is gated: it can only run when the box is reachable. The
gate and the invalidator turned out to be the same event.

| | as-planned (`journalctl -b`) | unrestricted |
|---|---|---|
| window | 2026-09-01T05:33:31 → 08:10:02 | 2026-08-23T14:02:08 → 2026-09-01T08:10:02 |
| span | 2 h 40 m | 8 d 18 h |
| `Starting` fires | **81** | **1652** |
| day files it can attribute | 1 of 10 | 10 of 10 |

Both captures close the `Finished` gap perfectly — `durations_derivable`
81/81 and 1652/1652, against round 400's 28/358. The plan **succeeded at
exactly what it was written to do** while losing 95 % of the window, and the
loss was in a dimension nobody had named.

The shape to look for elsewhere: *if a fix can only be applied under condition
C, ask what typically causes C, and whether that cause invalidates any
assumption the fix was pinned against.* Here C was "box reachable" and the
usual cause of a box becoming reachable is that it rebooted.

## 2. The audit graded which lines survived, never which days they covered

Round 406's `audit` checks that every required `sar` activity covers every day
file, and that every required journal line KIND is present. Both captures pass
every one of those checks. Before this round:

```
as-planned : verdict=filtered  n_gaps=1  n_blocking_gaps=1  durations_frac=1.0
full       : verdict=filtered  n_gaps=1  n_blocking_gaps=1  durations_frac=1.0
```

Byte-identical. The instrument had no channel for the only axis they differ on.

`journal_span_coverage` is that channel. It joins the two sources on the only
key they share — sysstat names files `sa<DD>` and carries no month, systemd
timestamps carry a full date — and asks, per day file, whether the journal
holds any `systemd[1]` line dated that day. After:

```
as-planned            verdict=narrow    blocking=9   span  1/10
nuc-capture-r424      verdict=complete  blocking=0   span 10/10   <- --strict exit 0
nuc-capture-r400      verdict=filtered  blocking=10  span  2/9
```

`narrow` is a third verdict on purpose. The boot-scoped capture is **not**
filtered — every required kind survived — and collapsing it into `filtered`
would send the next round hunting for a grep that is not there.

The retroactive part is the sharper one. **Round 400's capture covered 2 of its
9 day files.** Its cost ledger could never have attributed a fire on sa23–sa29,
because there were no fires in the file for those days. That was true for
twenty-four rounds and nothing reported it.

## 3. `--strict` could never pass, and a gate that is always red is not a gate

`state/nuc-capture-r424/` is the **first capture in this program's history to
exit 0 under `--strict`**. Not because previous captures were all bad: because
`Failed <unit>.service` was a required kind, so a box on which nothing failed
graded `filtered` forever.

The fix is a distinction the original model did not have. Absence of `Finished`
is evidence about the **capture** — round 400's grep dropped it. Absence of
`Failed` in a capture holding 1580 `Finished` lines is evidence about the
**box**: nothing failed. So `Gap` now carries `absence_means ∈ {filtered,
box-state, window}`, and any terminal kind at all (`Finished`/`Stopped`/
`Stopping`) witnesses that the capture was not grep-filtered, after which
`Failed`-absence stops being blocking. Round 400's capture has no witness, so
there it stays blocking — that path is still exercised, on real data.

Two journal kinds nobody had asked for turned up in the unfiltered capture:
**`Stopped` (133) and `Stopping` (95)**. They are the only source of a
*long-running service's* end time, which is what interval-attribution needs for
anything that is not a oneshot — including the engine.

## 4. The expiry constant was wrong by 21 days, and the outage is why the data survived

Every emitted plan since round 406 carried the line *"sa23 is overwritten on
2026-09-23; everything older is already gone."* That models sysstat as a
31-slot ring keyed on day-of-month. `/usr/lib/sysstat/sa2` ends:

```sh
find "${SA_DIR}" -type f -mtime +${HISTORY} | grep -E "${SAFILES_REGEX}" | xargs rm -f
```

with `HISTORY=7` in `/etc/sysstat/sysstat`. Files are **deleted at 7 days**;
the ring never gets a chance to wrap. Both mechanisms are real and the earlier
one binds. `sa2` itself branches on `HISTORY > 28`, so the constant was the
right answer to a different configuration.

`retention_forecast` derives it instead, and is validated against the box's own
`find`: at capture time the model and `find /var/log/sysstat -mtime +7` both
return exactly `{sa23, sar23}`.

```
next sweep 2026-09-02T00:07:00Z (15 h after capture), HISTORY=7
  DELETED: sar24 (age 8.000)  sa24 (8.012)  sar23 (9.000)  sa23 (9.012)
  next loss after that: 2026-09-02T23:50Z (sa25)
```

And the reason this is not a near miss but a four-round one: **no round had
ever banked the binary day files at all.** `git log --all --diff-filter=A` over
the whole history returns exactly one matching path, and it is this round's
`state/nuc-capture-r424/sysstat-binary.tar.xz`. Round 400's item 1 said, in its
own words, *"copy `sa*` into `~/nuc-research/` on every up-round — it is ~2 MB
for the set and one `scp`. This is the highest-value cheap action available and
it is time-critical in a way nothing else on this list is."* It was right, it
was carried for four E rounds, and it was carried against a deadline that was
itself stated 21 days too late. The whole set compresses to 367 kB.

The subtlety that mattered: `find -mtime +N` truncates age to **whole 24 h
units**. At the sweep on 2026-08-31T00:07Z `sa23` was 7.012 days old and
`int(7.012) == 7` is not `> 7`, so it survived a night a float comparison says
it should not have — which is why it was still there to capture.

And the inversion worth stating plainly: **the outage that blocked this capture
for seven rounds is the same thing that preserved what the capture was for.**
`sysstat-summary` is a timer. A box that is off at 00:07 does not sweep. Nine
day files existed under a 7-day retention because the box was down for most of
the window; the moment it came back, retention resumed.

## 5. The pre-rendered reports — round 400's open item, finally captured

**Correction to this round's first draft, which claimed a discovery that was
not one.** `ls -l /var/log/sysstat` holds `sar23 … sar30` beside `sa23 … sa31`
— sysstat's own pre-rendered daily reports, 192–499 kB each, written by
`sysstat-summary` at 00:07. Round 400 saw them, saw that `sar29` was missing,
and gave the correct structural reason, in its own handoff item 2: *"the box
has `sar23`–`sar30` but no `sar29` — because the summary cron fires at 00:07
and the box was down at 2026-08-30T00:07. A missing summary file is a third,
zero-cost outage witness."*

So the mechanism is round 400's, not this round's. What round 424 adds:

- **Round 400's item 2 has been open for four E rounds** and this is the first
  up-round since. Nobody re-derived the second witness.
- **They had never been CAPTURED.** Round 400's item 1 asked for `sa*` and got
  `sa*`; the plan's glob was `sa[0-9][0-9]`, which does not match `sar23`.
  They are in the tar and in the plan's glob now.
- **`sar31` is missing too**, which round 400 could not have known: the box was
  down at 00:07 on 2026-09-01 as well. So the absence is not a one-off — it
  reproduces on every outage that spans midnight, and the pre-rendered view is
  now absent for *both* outage boundaries in the archive.
- They expire on the same 7-day sweep as the binaries (§4), which is what makes
  the four-round delay expensive rather than merely untidy.

## 6. The factor of two is confirmed, and the command that would have confirmed it did not

Round 418 inferred a double count in `pgsteal` from the data's shape (six of
seven buckets at `%vmeff > 100`, an impossibility; divisor 2 restores the
ceiling with max exactly 100.000) and wrote down the falsification test:

> `grep -E '^pg(scan|steal)' /proc/vmstat` — confirmed if
> `pgsteal_anon + pgsteal_file == pgsteal_kswapd + pgsteal_direct + pgsteal_khugepaged`

Round 424 ran it. **All fourteen counters read 0.** The box had rebooted 2 h
40 m earlier and had not reclaimed a single page. The identity held as `0 == 0`
and settled nothing. *A test that needs the phenomenon to have recurred is only
as available as the phenomenon.*

What settled it was reading the **collector** instead of the kernel:

```
$ strings /usr/lib/sysstat/sadc | grep -E '^pg[a-z_]*$' | sort -u
pgscan_direct
pgscan_kswapd
pgsteal_
```

Three literals; the asymmetry is the entire finding. `pgsteal_` is a **bare
prefix**. On kernel 6.8 it matches five fields forming **two complete
partitions of the same events** — `{kswapd, direct, khugepaged}` by actor and
`{anon, file}` by page type — each of which already totals every stolen page.
`pgscan_kswapd` and `pgscan_direct` are **full field names** covering one
partition. Numerator summed twice, denominator once:
`%vmeff = pgsteal/(pgscank+pgscand)` reads exactly **2×** true efficiency.

Those literals are in the binary whether or not the box ever reclaimed
anything, which is why this route was available on a boot where the other was
not. Banked: `state/nuc-capture-r424/collector-evidence.txt` (sysstat 12.6.1-2,
kernel 6.8.0-138-generic).

**A second, smaller asymmetry the same evidence exposes, which was not
predicted:** `pgscan_direct` is a full name but is *still a prefix of*
`pgscan_direct_throttle`, a subset counter — so throttled scans are charged
twice in the **denominator**, biasing `%vmeff` the opposite way. It reads 0 on
this box and on any box not under allocator pressure, so it has never mattered
here. But "the error is entirely in the numerator" is not quite true, and the
prediction that said so is scored as a partial.

### What the correction buys — and it is not just smaller numbers

```
day  time        scan p/s  steal p/s      vmeff     corr      rep MiB   corr MiB
30   13:30:05      649.51    1297.55    199.774   99.887       3041.1     1520.6
30   14:50:05       55.44     110.88    200.000  100.000        259.9      129.9
30   15:00:05     3105.98    6211.80    199.995   99.997      14558.9     7279.5
30   15:10:03      685.14    1361.24    198.681   99.340       3190.4     1595.2
31   00:40:05       55.60     110.77    199.227   99.613        259.6      129.8
31   02:00:05       80.60     110.88    137.568   68.784        259.9      129.9
31   04:00:03     1207.00     401.70     33.281   16.640        941.5      470.7

TOTAL, 7 reclaim buckets: reported 21.98 GiB -> corrected 10.99 GiB
```

Two things become visible only after halving.

**A physical-plausibility check the reported figures fail.** `sa30 15:00:05`
reports **14.56 GiB stolen in one 600 s bucket** on a box whose `MemTotal` is
~26 GB and whose page cache at rest is ~5 GB. That is not a large number, it is
an impossible one. Corrected: 7.28 GiB — large, and possible.

**A distinction the doubling erased.** Published as upper bounds, six of seven
buckets are just "impossible" and are all equally suspect. Halved, five sit at
**~100 %** — every page kswapd looked at, it took, which is what evicting
clean file-backed page cache looks like — and **04:00:03 stands alone at
16.6 %**, the one bucket where reclaim actually had to work. That is round
418's own headline event, and it is the *least* efficient reclaim in the
record, not merely the one with the odd `%vmeff`. `02:00:05` sits between at
68.8 %.

Reported columns are **untouched**. Round 418's rule — a silently halved byte
count is exactly the number that gets quoted without its caveat — survives
confirmation. `ReclaimEvent` now carries `corrected_steal_s`,
`corrected_stolen_pages`, `corrected_stolen_bytes` and `corrected_vmeff_pct`
*beside* the raw columns, so a caller has to name which it is using.

## 7. `sadf` makes the boundary hole worse, not better (round 418 item 4, refuted)

Round 418 proposed `sadf` as a way to recover the day-file's first record,
which `sar` consumes as a rate reference and never prints — the cause of the
1200 s stitched bucket. Tested on `sa01`:

```
sadf distinct stamps: 16      sar distinct stamps: 17
sar : 05:33:33 (LINUX RESTART), 05:40:12 (column header), 05:50:01, ...
sadf: 05:33:33 (LINUX-RESTART),                           05:50:01, ...
```

Both consume the first record. `sar` at least *stamps its column header* with
`05:40:12`, leaking the record's existence and time; `sadf` drops it entirely.
Switching would have lost information. **The 1200 s stitch stays.**

But `sadf` has something `sar` does not, in a column round 418 had to infer:
it publishes the **interval per record** explicitly — `589` for the 05:50:01
row, not 600, because the first record landed at 05:40:12 rather than on a
10-minute boundary. `SAR_INTERVAL_S = 600` is an approximation and `sadf` hands
over the true span. That is the right use of `sadf`, and it is not the one it
was proposed for.

## 8. The engine load happened inside the record `sar` throws away

Round 370's item 3 — carried by rounds 376/382/406/412/418 — asked for
`memory.current` polled at ~5 s through a fresh boot's model load, to catch the
`unpacking to int8 in slot` transition. This is the first fresh boot since.

The journal has the load, retrospectively, without polling and without sending
a request:

```
05:33:34  ExecMainStart qwen36-colibri (user unit)
05:33:35  [tok]  loaded 248044 pieces from /work/models/qwen36_i4_gs64/tokenizer.json
05:33:35  [meta] q_heads=16 kv_heads=2 n_experts=256 topk=8 ...
05:33:48  resident weights loaded in 13.1s | RSS after load: 9.25 GB
```

**Item 3 is half-closed and half-permanently-lost, as predicted.** The
*timeline* survives: the whole load is 13.1 s, 05:33:34 → 05:33:48. The
`memory.current` *trajectory* does not, and no artifact records it after the
fact — an unsampled level does not survive.

Three honest corrections to the prediction:

- There are **no `unpacking to int8 in slot` lines at all** this boot. The unit
  logs 9 lines total. The model directory is `qwen36_i4_gs64`; whatever emitted
  that line is not in this configuration's path. The item should stop naming it.
- **sa01 shows no memory step, and the reason is finding §7.** `sar`'s first
  *printed* record for sa01 is 05:50:01; the first record, consumed as the
  reference, is **05:40:12**; `LINUX RESTART` is 05:33:33. The engine load ran
  05:33:34 → 05:33:48 — entirely inside the interval `sar` drops. The
  boundary hole and the one event on this boot worth seeing are the same hole.
- **The engine is nearly invisible to the commit channel.** At rest sa01 reads
  `kbmemused ≈ 4.99 GB`, `kbcommit ≈ 5.6 GB`, `kbcached ≈ 5.27 GB`, while the
  engine's own log says `RSS 9.25 GB`. The weights are file-backed mappings,
  not anonymous allocations. Round 418 found `Committed_AS` blind to eviction
  because it counts promises; the companion is that it is **also blind to the
  largest memory consumer on the box**, because a mapping is not a promise
  either. And with the page cache doing the work and ~22 GB free, **this boot
  reclaimed nothing at all** — every `pgsteal_*` counter is 0 after 2 h 40 m.

## 9. Predictions scored (D-013)

17 numbered predictions (A1-A6, B1-B5, C1-C4, D1-D2) + 3 hygiene
commitments. **10 HIT · 3 PARTIAL · 3 MISS · 1 VACUOUS of 17**, and all 3
commitments kept. (A first draft of this line said "13/3/4/1 of 22" by counting
the hygiene commitments into the denominator and mis-tallying; the table below
is the authority and sums to 17.)

| # | Verdict | Note |
|---|---|---|
| A1 | **HIT** | `-b` window 05:33:31→08:10:02, 2 h 40 m; contains no sa23–31 day. |
| A2 | **HIT** | 81 `Starting` fires vs round 400's 358. |
| A3 | **PARTIAL** | Predicted `--strict` would *pass* and hide the loss. It exited 1 — but for an unrelated reason (§3, `Failed` permanent-red), and the verdicts for the two captures were **identical**, so the claim it was testing is confirmed by a stronger route than the one predicted. |
| A4 | **HIT** | `sa01` present; `sa[0-9][0-9]` picks it up; the comment was stale. Plus the unpredicted `sarNN` discovery (§5). |
| A5 | **HIT** | `/var/log/journal` persistent, 3.3 G, 7 boots listed back to 2026-08-23. |
| A6 | **HIT** | 1571 fires in the sa23–sa31 window; 1652 across the whole journal. |
| B1 | **HIT** | Both partitions present, incl. `pgsteal_khugepaged`. |
| B2 | **VACUOUS** | All 14 counters 0. The identity held as `0 == 0`. **Not scored a hit** — it measured nothing (§6). |
| B3 | **HIT** | Mechanism confirmed exactly as stated, by the collector's literals. |
| B4 | **PARTIAL** | Numerator doubling confirmed; "**entirely** in the numerator" is not quite right — `pgscan_direct` over-matches `pgscan_direct_throttle` (§6). Zero-valued here, so no published figure moves. |
| B5 | **HIT** | Predicted the counter route would be unavailable and said so *in advance* so a null could not be retro-fitted. It was unavailable — more completely than the reason given. |
| C1 | **PARTIAL** | The load IS recoverable retrospectively from the journal. But there are **no `unpacking to int8 in slot` lines**; the predicted marker does not exist in this config. |
| C2 | **HIT** | Item 3 is half-closable, half-lost, for exactly the stated reason. |
| C3 | **MISS** | No ~9.77 GB step in sa01, and no step at all — the load ran inside the record `sar` drops, and the footprint is file-backed anyway (§8). |
| C4 | **HIT** | Predicted "smaller"; it is **zero**. |
| D1 | **MISS** | `sadf` does *not* emit the first record; it hides it more completely than `sar` (16 stamps vs 17). |
| D2 | **MISS** | Follows from D1. |
| E1–E3 | **KEPT** | See §11. |

**Unpredicted findings, flagged as such and claiming no foresight:** the entire
retention result (§4 — the 21-day error, the `-mtime` truncation, the
outage-preserves-the-archive inversion), the `sarNN` pre-rendered reports and
their outage-shaped absence (§5), the `Stopped`/`Stopping` kinds (§3), the
`pgscan_direct_throttle` over-match (§6), and `sadf`'s per-record interval
(§7).

## 10. Artifacts and tests

- `nuc/capture_manifest.py` 388 → 693 lines (measured `wc -l`). New: `journal_span_coverage`,
  `parse_sysstat_ls`, `find_mtime_matches`, `retention_forecast`,
  `SA2_SWEEP_RE`, `UNFILTERED_WITNESS_KINDS`, `BOX_STATE_KINDS`,
  `Gap.absence_means`, verdict `narrow`, CLI verb `retention`. `capture_plan`
  no longer emits `-b`, no longer hardcodes an expiry date, and now captures
  the boot table, the user manager and the collector evidence.
- `nuc/perturbation.py` 1805 → 1982 lines. (Round 418's file said it left
  the module at 1729; `git show 05eb40c:nuc/perturbation.py | wc -l` is 1805,
  so that figure was already stale before this round touched it. Both numbers
  here are `wc -l`, taken now.) New: `RECLAIM_STEAL_DIVISOR` (2,
  confirmed), `sadc_reclaim_literals`, `parse_vmstat_fields`,
  `steal_double_count_evidence`, and four `corrected_*` fields on
  `ReclaimEvent`.
- `nuc/tests/test_reachability_check.py` — one fixture fixed (§12).
- `state/nuc-capture-r424/` — `sysstat-binary.tar.xz` (367 kB, all 17 files),
  `sar-all.txt` (100 sections, 10 activities × 10 day files),
  `journal-pid1-full.txt` (9189 lines), `journal-pid1-curboot.txt` (the
  as-planned control), `journal-user-full.txt`, `journal-boots.txt`,
  `collector-evidence.txt`.
- `nuc/predictions-e-round424.md`.

**Tests 699 → 723, all green** (`723 passed in 213.34s`). Baseline at round
start was `2 failed, 697 passed`; §12 explains both failures.

## 11. Hygiene

- **Port 8001 never contacted. No engine request of any kind**, to :8000,
  :8080 or anything else. Every remote command was a read of `/proc`,
  `/var/log`, `/usr/lib/sysstat` or `journalctl`, plus one `tar` to stdout.
- **No unit started, stopped, restarted or reloaded.**
- **Nothing written on the box.** Not even `~/nuc-research/` — the tar streamed
  over stdout, so this round's remote footprint is strictly read-only.
- `/work/**` untouched. Both engine ports are loopback-only and were not used.

## 12. The two red tests at round start, and why one of them was this round

The baseline run was `2 failed, 697 passed`. Neither was inherited breakage.

`test_a_capture_window_that_ends_before_the_log_does_loses_the_bound` was
broken **by this round's own reachability record.** The fixture takes the
newest `up` record, walks back to the start of its streak, and requires the
streak to be at least two long. Rounds 406/412/418 all logged `down`; round
424 logged `up`; so the newest up streak is exactly **one** record and has no
interior gap.

That fixture has now pinned a fact about the world three times. Round 382
removed an absolute window. Round 406 removed "the log ends in an up streak".
Round 424 removed "the newest up streak has at least two records" — by asking
for the quantity actually wanted, *the newest adjacent `up`→`up` pair*, which
needs no streak-length assumption at all. The genuine precondition (there is
some `up`→`up` pair somewhere) is now what the assertion message says.

`test_the_fast_check_runs_green_on_this_tree` was the cascade: it shells out to
`nuc/run_checks_fast.sh`, which runs `nuc/tests/`. Both are green now.

One self-inflicted bug worth recording because it is a five-minute bug that
only ever appears once: `capture_manifest.py`'s
`if __name__ == "__main__": raise SystemExit(main())` sat immediately after
`main()`, mid-file. Appending helpers below it made the CLI raise
`NameError: parse_sysstat_ls` — module-level statements run in file order, so
a guard placed mid-file calls `main()` before the rest of the module exists.
The guard is now at the end of the file, with a comment saying why.

## 13. Handoff — next E round, in order

1. **Run `capture_manifest.py retention` FIRST, every up-round, and capture if
   it is non-empty.** The archive rolls off in ~8 days of box-uptime and the
   sweep only runs when the box is up. `--strict` exits 1 when the next sweep
   deletes something. Do not re-derive the deadline from prose.
2. **Attribution over the full window is now possible for the first time** —
   1652 fires with 100 % derivable durations against ten day files, span
   10/10, plus `Stopped`/`Stopping` for long-running services. Every ledger
   result in this program was computed on a journal covering 2 of 9 day files.
   Re-run `cost_ledger` / `attribution_evidence` / `channel_sweep` against
   `state/nuc-capture-r424/` and expect the power floors to move.
3. **Re-derive round 418's `fwupd-refresh` result on corrected steal.** Its
   `p_chance 0.0154` was computed on doubled bytes. The ordering is unlikely to
   change — the divisor is uniform — but the *magnitudes* in the round file
   are all 2× and the `consistency 0.111` blocker is unaffected.
4. **The `04:00:03` event is now the outlier for a new reason**: 16.6 %
   corrected reclaim efficiency against ~100 % for five of the other six. It is
   the only bucket where kswapd scanned much and stole little. Ask what was
   pinned or recently-referenced at 04:00 that was not at 15:00.
5. **Use `sadf` for per-record INTERVALS, not for the first record.** `sadf`
   publishes the true span (589 s, not 600) that `bucket_span_s` currently
   infers. The 1200 s stitch is not removable and should stop being an open
   item.
6. **`sar29`/`sar31` do not exist and never will** (§5). Any analysis wanting
   a pre-rendered day must check first.
7. **Round 370's item 3 should be rewritten or retired.** It names
   `unpacking to int8 in slot`, a line this configuration does not emit, and
   the `memory.current` trajectory it wants is unrecoverable for boot
   `f13afb47`. What is left is: on the *next* fresh boot, start the poller
   before `qwen36-colibri` reaches its 13-second load — which needs a poller
   already running at boot, i.e. a `~/nuc-research/` unit, i.e. operator
   approval this round did not have and did not take.
8. **Still blocked on the operator:** `--cap 196` and the E3 A/B, with round
   412's precondition that any A/B publishes its power floor before it runs.

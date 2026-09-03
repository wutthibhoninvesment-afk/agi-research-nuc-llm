# Round 478 (NUC-integration E) — PREDICTIONS, banked before measurement

**Written 2026-09-03T17:1xZ, committed before any capture from the box.**
House rule D-013: predictions first, then measure, then score misses honestly.

## 0. What was ALREADY OBSERVED before this bank (not predictions — declared)

Round 472's next-step item 1 is a gate that runs before anything else, and a
reachability probe cannot be deferred behind a bank without making the bank
about a box whose state we refuse to look at. So these four are OBSERVATIONS,
recorded here so no later section can pass them off as foresight:

* `tailscale status` 2026-09-03T17:10:40Z — `pgain-nuc` **active; direct
  124.120.12.172:1024**. ping 2/2, rtt 51.4/91.4/131.4 ms.
* `ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111` at 17:10:54Z — **SSH_OK**.
  `date -u` 17:10:54Z, `uptime -s` `2026-09-03 09:37:09`, `uptime` `up 7:33`,
  boot_id `0d0e3188-da12-4a4b-9f78-b26dd95d3ea2`. 17:10:54 − 09:37:09 = 7h33m45s,
  so **the box's clock is UTC** and boot = `2026-09-03T09:37:09Z`.
  This is a boot never before seen: rounds 424/430 ran on `f13afb47`
  (`uptime -s 2026-09-01 05:33:27`).
* The three strict checks, run FIRST per round 472 item 1, exit codes taken
  from the process and not from a pipeline tail: `coverage --strict` **0**,
  `precision-audit --strict` **0**, `lastseen-drift --strict` **1** — byte-for-byte
  the state rounds 460/466/472 left, the last for the documented reason
  (the 436-472 streak carries two LastSeen values, spread 124 s).
* Therefore the 436/442/448/454/460/466/472 outage is **CLOSED**, and closed by
  a REBOOT, exactly as the 406/412/418 outage was closed by round 424.
  Bracket: last seen `2026-09-01T18:27:56.1Z` → boot `2026-09-03T09:37:09Z` =
  **39h09m13s**, which beats round 472's confirmed 37h26m00s and is the longest
  outage in this log by a wide margin.

## 1. The deadline this round exists to beat

`capture_manifest.py retention --capture state/nuc-capture-r424
 --next-run 2026-09-04T00:07:00Z --now 2026-09-03T17:10:00Z
 --down-since 2026-09-01T18:27:56Z --down-until 2026-09-03T09:37:09Z`
run offline against round 424's banked `ls -l`, says:

* `skipped_fires`: **2026-09-02T00:07:00Z and 2026-09-03T00:07:00Z** — both
  fell inside the outage.
* `n_deleted_at_next_run`: **8** — `sa23 sa24 sa25 sa26 sar23 sar24 sar25 sar26`
  — at **2026-09-04T00:07:00Z**, i.e. **6h50m** after this bank.

That forecast is the PREDICTION, and it is conditional on P1. Every numbered
item below is scored in the round file.

## 2. Predictions

**P1 (0.80) — `systemctl show sysstat-summary.timer -p Persistent` reports
`Persistent=no`.** Round 448 §2 inferred "not persistent" from fires the box
demonstrably missed and never read the unit, because no capture this program
ever took included the timer text. Round 472 item 5 flags this as wrong *in the
dangerous direction* if it says `yes`. This is the first read.

**P2 (0.75, conditional on P1) — all 8 forecast-doomed files are still on the
box right now.** `ls /var/log/sysstat/` contains `sa23 sa24 sa25 sa26` and
`sar23 sar24 sar25 sar26`. If P1 is wrong and the timer IS persistent, the
missed fire ran at or just after boot 09:37:09Z and these 8 are already gone —
in which case P2 fails and the retention machinery's `--down-since` walk is
unsound and must be withdrawn loudly.

**P3 (0.85) — there is NO `sa02`.** The box was down for the whole of
2026-09-02 (18:27Z on 09-01 through 09:37Z on 09-03), so `sysstat-collect`
never fired on day 02 and the day file was never created. A round that assumes
day files are contiguous will mis-attribute this hole to retention.

**P4 (0.80) — `sa01` exists and its last record is between 18:10Z and 18:30Z**,
the last 10-minute collect before the box vanished. This is an independent
witness to the outage START that does not come from tailscale.

**P5 (0.85) — `sa03` exists, first record between 09:37Z and 09:50Z**, an
independent witness to the outage END that does not come from `uptime -s`.

**P6 (0.60) — `journalctl --list-boots` gains exactly ONE row beyond round
424's table.** i.e. the box did not bounce more than once during the outage;
the 39h was one continuous down period, not a flapping one.

**P7 (0.55) — the journal shows NO clean shutdown for the 09-01 18:2xZ
disappearance.** No `Stopped target`/`Reached target Shutdown` sequence
terminating boot `f13afb47`; the last `_PID=1` line before the boot boundary is
an ordinary one. That is the signature of power loss or a hard sleep, not an
orderly halt — and it is what every "the box just vanished" round has assumed
without ever checking.

**P8 (0.60) — exactly 11 `sa??` day files are present**: `sa01 sa03 sa23 sa24
sa25 sa26 sa27 sa28 sa29 sa30 sa31`.

**P9 (0.70) — the `qwen36-colibri` USER unit is active right now** and was
started by the boot, not by hand; `qwen36-toolproxy` likewise.

**P10 (0.50) — the new capture raises `dose_response`'s full-record window
count from 28 to at least 30.** Round 472 could score only 28 of 42 windows
because the sar record ends where round 424 copied it; `sa01` covers round 430
and round 436's window, and `sa03` covers this one.

**P11 (0.65) — the capture's `sysstat-binary.tar` is between 1.5 MB and 6 MB**
before compression.

**P12 (0.40) — `capture_manifest.py audit --strict` on the new capture exits
0 on the FIRST try.** Round 424's plan is machine-generated and has never been
executed end to end by a later round; every previous capture needed a repair.

## 3. What this round will NOT do

No engine request of any kind. Port **8001 never contacted**. No unit
restarted. No write outside `~/nuc-research/`, `/work/logs/`, `/tmp/`. If SSH
fails twice consecutively the round records it and exits.

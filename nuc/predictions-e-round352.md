# Round 352 (NUC-integration E) — PREDICTIONS, written BEFORE measuring

House rule **D-013**: predictions first, then measure, then score misses honestly.

Written 2026-08-30 ~02:23 UTC. Known at write time, and ONLY this:
`reachability_check.py check --round 352` returned `up`, ssh rc 0, tailscale
online, `boot_utc = 2026-08-30T00:32:27Z`, `source=live`, `precision=precise`;
and one sanity ssh returning `/proc/uptime = 6521.28 25940.92`,
`uptime -s = 2026-08-30 00:32:28`, box clock is UTC, `2 users`, load 0.00.
Nothing else on the box has been read this round. This is the FIRST up-round
for track E since round 292 — rounds 298/304/310/316/322/328/334/340/346 were
all down.

## A. Boot history (round 340's time-critical "first action on the first up check")

- **P1** `journalctl --list-boots -o json` exits 0 and lists **>= 2** boots.
  Rationale: the box demonstrably rebooted at 00:32:27Z today, so at minimum
  the current boot plus the one before it exist — UNLESS journald storage is
  `volatile`, which `boot_history_probe`'s docstring names as a real failure
  mode and which would list exactly 1. I am predicting persistent storage.
- **P2** The boot immediately preceding the current one has a `last_entry`
  at **2026-08-29 02:00-02:15Z**, and the current boot a `first_entry` at
  **2026-08-30 00:32-00:35Z**. Rationale: the reachability log's last
  successful tailscale `last_seen` for the old boot is 2026-08-29T02:10:00.1Z
  and this boot began 00:32:27Z. This would put the true outage bracket at
  ~22h20m — near the TOP of round 346's [19h38m06s, 22h22m26s] bracket, not
  the bottom.
- **P3** `gap_continuity --boot-history` produces **at least one**
  `source: boot_history` witness that no probe-based rule could produce.
  Sub-prediction, lower confidence (~50%): at least one is a
  `missed_excursion` — a boot boundary strictly inside a span the log calls
  one unbroken UP streak. Rounds 124-292 span many days of "up" checks fired
  ~40 min apart at best; a reboot hiding inside one is plausible but not
  established.

## B. Fresh-boot memory/swap state (all prior swap data is from the OLD boot)

Every swap figure this program has (rounds 130/136/142/154/208-298) came from
ONE continuous boot. This is a different boot, 1h48m old at probe time.

- **P4** `memory.swap.current` for `qwen36-colibri` is **0 B**. Rationale:
  round 130 measured 0 B at uptime 5h10m on the previous boot even with the
  cgroup already pinned at its ceiling; swap first moved off zero at round
  136 (12h53m). 1h48m is well before that.
- **P5** `memory.current` for `qwen36-colibri` is **below** its `memory.max`
  — I predict **12-25 GiB**, i.e. 40-83% of the ceiling. Rationale: round 124
  caught 52% at 3h13m on the previous boot and round 130 caught 100% at
  5h10m; 1h48m is earlier than either, but the fill rate depends on
  traffic diversity (round 124's own finding), and load average is 0.00.
  **Wide band on purpose — this is the weakest prediction here.**
- **P6** `memory.max` = **32212254720** (30.0 GiB) exactly, unchanged.
- **P7** `memory.events` `max` counter is **> 0** if P5 says the ceiling was
  ever touched this boot, **0** otherwise; I predict **0**, consistent with P5.

## C. Standing state re-verification (round 304's item 2, unverified for 9 rounds)

- **P8** The live colibri serve process still carries **`--cap 256`**.
- **P9** The **E3 prefix-reuse patch is NOT applied** to the running engine.
  Rationale: it has needed an operator-approved restart since round 28 and
  every round since has recorded that sign-off never came.
- **P10** The **OLMoE tarball is still present** on the NUC's NVMe.
  Low confidence — I have no round that says it was removed, but also none
  that has looked since the box came back.
- **P11** `qwen36-colibri` is running, as a **user** systemd unit
  (`systemctl --user`, round 100), and is **active** on this fresh boot
  (i.e. it is enabled/linger-started, not hand-started by the operator).
  Sub-prediction: `qwen36-toolproxy` likewise.

## D. Documentation coordinates (round 346's open note)

- **P12** `~/.ssh/id_ed25519_nuc` **does not exist on this driver host**, so
  the LAN command as written in CURRICULUM.md and CLAUDE.md
  (`ssh -i ~/.ssh/id_ed25519_nuc jab@192.168.1.37`) would fail on key path
  alone, independent of whether the LAN route exists. Round 346 asserted this
  from a directory listing and asked a future up-round to verify it; the
  second half (does 192.168.1.37 route from here at all) I predict **no** —
  this driver host reaches the box over the tailnet.

## E. The second multi-hour swap poll (round 304's item 1, deferred 9 rounds)

- **P13** `swap_watch_launch.py launch` succeeds end-to-end on the first
  attempt — scp lands, the remote `nohup` survives disown, and the local
  detached watcher starts. Rationale: every ssh/scp command in it is a pure
  function with offline tests, but its success path has NEVER run against a
  real box (same shape as round 304's launcher and round 334's `boot_probe`,
  both of which had to be verified live before being trusted). Confidence
  moderate, not high — this is exactly the class of code this program has
  repeatedly found to be wrong the first time it meets a real machine.
- **P14** On a fresh, idle boot the 8h poll will record **at least one swap
  burst** (a sample-to-sample `memory.swap.current` delta >= 1 MB).
  Rationale: round 238 established passive growth continues at zero requests
  and round 244 established it is bursty, not smooth — but both were on a
  boot already deep into its ceiling. If P4 (swap 0 B) holds and the cgroup
  has not yet touched `memory.max`, the round-130 finding ("hitting the
  ceiling and swapping are sequential cgroup-v2 events") predicts **no swap
  at all** until the ceiling is touched. **These two readings conflict, and
  the run is designed to decide between them.** I am predicting bursts, at
  ~55% confidence; a completely flat 8h trace on a fresh boot would be the
  more informative outcome.

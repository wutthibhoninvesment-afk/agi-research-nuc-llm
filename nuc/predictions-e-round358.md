# Round 358 (NUC-integration E) — PREDICTIONS, written BEFORE measuring

House rule **D-013**. Written 2026-08-30 ~05:50Z, after `reachability_check.py
check --round 358` returned `up` / boot_utc `2026-08-30T00:32:27Z` (same boot
`43e0c767` as round 352) and BEFORE any other command was run against the box.

This round's target is round 352 §8 **item 2** — the suspend blind spot in
`_boot_history_witness` — plus item 1 (collect/observe the in-flight 8h swap
poll, which is due ~10:25Z, i.e. AFTER this round ends).

## A. The in-flight swap poll (item 1)

- **P1** — remote pid 2337 is still alive on the box, still writing
  `~/nuc-research/swap-watch-r352-checkpoint.jsonl`. Confidence high: the local
  watcher's `poll.log` shows `status=[ 2337]` as recently as 05:46Z.
- **P2** — the checkpoint has ~195-200 samples at 15 s... **no**: round 352
  recorded 8h/15s but the local poll.log ticks ~1/min. I predict the checkpoint
  file holds **>1500** samples (8h at 15 s = 1920; ~3h20m elapsed => ~800 at
  15 s). Stated band: **700-1000 samples**. Moderate confidence — I have not
  read the launch parameters yet.
- **P3** — `memory.swap.current` is still **0 B** across every sample so far,
  and `memory.events` `max` is still **0**. Round 352's P14 ("≥1 swap burst in
  8h") is heading for a MISS. High confidence: round 352 saw flat 0 B through
  35 samples and load average 0.00, and nothing has been asked of the box since.
- **P4** — because of P3, the 8h poll will end up *not* reproducing round
  136's 310.6 MB swap reading. The distinguishing variable is NOT uptime (this
  boot is now 5h+ and flat) but traffic diversity — round 124's own reading.
  Moderate-high.

## B. Journal interior-silence probe (item 2), the main build

- **P5** — one `journalctl --since/--until -o short-unix` query covering the
  whole reachability-log span (2026-08-19 -> now) returns a NON-empty result;
  journal retention is 3.2 G and round 352 read 7 boots back to 08-19. High.
- **P6** — the number of DISTINCT whole seconds carrying at least one journal
  entry over that span is **50k-400k** (an idle box, but journald on a running
  systemd box is never truly silent). Wide band deliberately: I have never
  measured this box's journal density. Low confidence in the band, high that
  it is >1000.
- **P7** — the transfer, deduplicated to whole seconds, is **under 5 MB**.
  Moderate.
- **P8** — **the headline number.** The largest interior silence inside the
  18 up-streak gaps round 352 called `WITNESS_FULL` will be **>600 s** for at
  least one gap. Reasoning: those gaps span hours-to-days of an idle box; even
  a chatty journald has quiet stretches overnight, and systemd timers on a
  desktop-ish install cluster. If this is right, `unwitnessed 0h00m00s` /
  `max_unobserved_outage: None` were overstatements of a real size, not a
  technicality. Moderate-high.
- **P9** — the largest interior silence over the whole span is **1800 s-4 h**.
  Low confidence; this is the number I most expect to be wrong, and the
  reason to measure rather than argue.
- **P10** — at least one of the 18 gaps will have a silence bound SMALL
  enough (<120 s) that the bounded witness is nearly as good as `FULL`. High:
  short gaps (the log has same-round duplicate probes 11 s apart) cannot
  contain a long silence.
- **P11** — after the fix, `continuity_report`'s `max_unobserved_outage` goes
  from `None` back to a NON-None number, and `unwitnessed` time goes from
  `0h00m00s` to a non-zero number IF the strength change alone is applied
  without interior data. High — this is the arithmetic of the change.
- **P12** — the suspend hypothesis (round 184) will NOT be confirmed or
  refuted by this data. The probe bounds how much suspend could hide; it does
  not detect one. High.
- **P13** — this code will be wrong in some way on its first contact with the
  real box, as round 304's launcher, round 334's `boot_probe`, and round 352's
  `swap_watch_launch.py` all were. Stated explicitly so a failure counts as a
  result. Moderate — the cheap-probe-first discipline below is the mitigation.

## C. Housekeeping

- **P14** — `languages/whence/SECURITY.md` is still dirty with byte-identical
  content to what round 349 escalated to the operator; no operator action.
  High — round 352 recorded an eleventh boot with no operator action on any ask.
- **P15** — the box's `/work/**` needs no writes this round; everything lands
  in `~/nuc-research/**` and `/work/logs/**`. High.

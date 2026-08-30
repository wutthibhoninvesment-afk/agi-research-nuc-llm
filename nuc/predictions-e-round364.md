# Round 364 (NUC-integration E) — PREDICTIONS, written BEFORE measuring

House rule **D-013**. Written 2026-08-30 ~10:05Z, after
`reachability_check.py check --round 364` returned `up` / boot_utc
`2026-08-30T00:32:27Z` (**same boot `43e0c767` as rounds 352 and 358**) and
after reading the two artifacts already on disk from round 358
(`state/nuc-boot-history-r358/list-boots-r358.json`,
`state/nuc-journal-r358/journal-seconds-boot43e0c767.json`) and the
in-flight poll's liveness (`ps`, checkpoint line count) — and BEFORE running
any journal scan, any analysis of the poll's contents, or any continuity
recompute.

Two targets, both handoffs, neither a new mission (E1-E5 all remain DONE):

- **Round 304 item 1** — the 8 h swap poll, launched by round 352 after nine
  deferrals, observed mid-flight by round 358, **due 10:25:07Z**. This is the
  first round in the program that can actually COLLECT it.
- **Round 358's closing handoff** — "one scan per `boot_id`, cached to
  `state/nuc-journal-<boot_id>.json` (closed boots are immutable), timeout
  sized from that rate", after round 358's whole-span capture fail-closed to
  `n_seconds: 0` at 1417 s against a 1400 s client timeout.

## A. The 8 h swap poll (round 304 item 1)

- **P1** — the poll completes on its own at 10:25:07Z (02:25:07Z + 28800 s)
  and `swap-watch-r352-long.json` is written by pid 2337. High confidence:
  it has survived 8 h and 1823 checkpoint samples with no gap.
- **P2** — the final checkpoint holds **1919 or 1920** samples. At 10:01Z it
  held 1823; 15 s/sample for the remaining 24 min = ~96 more. High.
- **P3** — **`swap_bytes` is 0 on EVERY one of the ~1920 samples**, and
  `pswpin_pages`/`pswpout_pages` are 0 on every sample. Therefore **round
  352's P14 ("on a fresh, idle boot the 8 h poll will record at least one
  swap burst") is a MISS**, and round 358's P3 (predicting that MISS) is a
  HIT. High confidence — 1823/1920 samples are already flat 0.
- **P4** — `mem_current_bytes` ends between **9.77 GB and 10.6 GB**, i.e. it
  grew by less than 1 GB across the whole 8 h. At 05:49Z round 358 read
  9.10 → 9.77 GB over 3.5 h; the run-up looks like a step, not a ramp, and
  the box has been at load 0.00 since. Moderate.
- **P5** — `mem_current` never reaches the 30 GiB `memory.max` ceiling, and
  `memory.events`'s `max` counter is still **0** at the end of the poll.
  High, and it matters: rounds 130/136/142 all caught this cgroup pinned AT
  the ceiling on a *different* boot. If P5 holds, the ceiling is not a
  function of uptime — this boot is now 9.5 h old and nowhere near it.
- **P6** — the *shape* of `mem_current` over 8 h is **monotone
  non-decreasing** (the cgroup never returns memory). Moderate: I have never
  seen an 8 h trace of it, and a page-cache-backed `memory.current` can in
  principle fall under reclaim. This is the number I most expect to be wrong.
- **P7** — the local watcher `watch-r352.sh` (pid 1422385, ~1/min) notices
  pid 2337 gone within 60 s of 10:25:07Z, pulls both files by scp, and
  appends `PULL_DONE` to `state/nuc-swap-watch-r352/poll.log` **before
  10:27:00Z**, with no intervention from this round. Moderate-high: its
  break condition is an empty `ps -p 2337` and it has run 415 clean
  iterations. Named failure mode if wrong: the `ps` returns empty
  spuriously on one iteration and it pulls a partial file early — which
  would already have happened by now, so I discount it.

## B. Per-boot journal scan, cached (round 358's handoff)

- **P8** — the boot list is unchanged from round 358's: the same **7 boots**,
  `-6 … 0`, with boot `0` = `43e0c767` still current. High — the box has
  not rebooted (boot_utc identical to round 358's).
- **P9** — a **300 s sampling probe** on a closed boot returns in **under
  20 s**. Round 358 measured a 30-min window of boot -1 at 8.2 s. Moderate.
- **P10** — **entry density varies by more than 100x between boots.** Round
  358 measured boot -1 at 2733 entries/s and the current boot at ~0.099
  seconds-with-entries per second. Whatever is chatty on boot -1 is not
  running now. High.
- **P11** — the full per-boot sweep of all 6 CLOSED boots does **not** finish
  inside this round's remaining wall-clock (~45 min at the time of writing).
  Total closed-boot span is ~501,951 s ≈ 139 h; at boot -1's measured
  ~10 min/38 h that is ~36 min of pure `journalctl` on two cores, plus
  transfer, plus the ones that are denser. Moderate-high — and if it is
  right, **the deliverable is the cache mechanism plus as many boots as fit,
  not a complete sweep**, and the cache is what makes that acceptable.
- **P12** — the number of DISTINCT whole seconds carrying an entry, summed
  over all 7 boots, is between **80,000 and 400,000**. Low confidence in the
  band; the point is that it is bounded well below the 501,951 s of wall
  clock, i.e. the boots really do have silences.
- **P13** — at least one closed boot has an interior silence **> 600 s**.
  Moderate-high; an idle overnight box logs in bursts around timers.
- **P14** — **the headline.** Feeding per-boot captures into `continuity`
  lowers `unobserved_total` from round 358's **67h27m58s** to a strictly
  smaller number, but **NOT below 20 h**: most of that 67 h is inter-boot
  time when the box was genuinely OFF, which no journal scan can shrink
  because there is no journal to scan. Moderate. If I am wrong it will be
  because the reachability log's gaps mostly sit *inside* boots.
- **P15** — a merged single capture spanning ALL boots would be **wrong**,
  and the per-boot design is not just a performance choice: `covers_from` /
  `covers_to` over a range containing an inter-boot OFF window would let
  `interior_silence` report that OFF window as a bounded "silence" of the
  running box. I predict the existing `continuity --journal-seconds` accepts
  exactly ONE capture file, so this round has to extend it to accept many or
  it cannot use per-boot data at all. High on the design claim; moderate on
  the "exactly one" reading of the CLI, which I have seen only in `--help`.

## C. Cross-cutting

- **P16** — round 304 item 2 (standing state: `--cap 256`, E3 patch, OLMoE
  tarball, `memory.events` max, operator login, escalation channel) is
  **unchanged from round 352's reading**, including a **twelfth** consecutive
  boot with no operator action on any of this program's asks. High.
- **P17** — no unit restart, no engine request, and **zero contact with port
  8001** will be needed by anything in this round. Certain by construction:
  every probe above is `journalctl`/`ps`/`cat` over ssh.

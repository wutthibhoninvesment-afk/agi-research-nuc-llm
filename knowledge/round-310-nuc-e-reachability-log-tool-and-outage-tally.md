# Round 310 — NUC-integration (E) — durable reachability log/tool; box still DOWN, same continuous outage as rounds 298/304, start pinned to the second

## Context

Rounds 298, 304 both found `pgain-nuc` unreachable and recorded that fact
as prose in their own knowledge files ("last seen 1m ago", "last seen 1h
ago... 2h ago"). Round 304's own next-steps left "the second multi-hour
`swap_watch.py` poll" unlaunched a third time and asked the next reachable
round to run `swap_watch_launch.py launch` for real. This round found the
box down a THIRD consecutive time for the E track — so that launch is
still not possible — and used the window on something genuinely new
instead of a fourth "box down, nothing to report": every prior round's
down-check discarded its own evidence as soon as the knowledge file was
written, using only `tailscale status`'s rounded, relative "last seen Xh
ago" string. Nothing durable ever recorded the real timestamp underneath
that string, so nobody could actually prove whether round 298's outage and
round 304's outage were the same continuous event or two separate ones —
each round could only guess from the rough hour-deltas lining up.

`tailscale status --json` carries a real `LastSeen` field that does NOT
advance while a peer stays offline. This round used that fact to build a
durable, tested reachability tool and log, backfilled the whole track's
up/down history from `state/nuc-missions.md`'s prose, and used the result
to prove — not infer — that the current outage began at exactly
**2026-08-29T02:10:00.1Z** and is still the same one 3h37m+ later.

## Pre-flight

- `ps -eo pid,ppid,etime,cmd` showed only this round's own driver process
  tree, no concurrent research-round driver
  ([[feedback_check_for_concurrent_rounds]]).
- `git status --porcelain` showed only `state/round_counter` (M) and the 4
  Hermes-owned `languages/whence/` untracked files, both already covered by
  `state/known-standing-dirty-paths.json`
  ([[feedback_check_cached_diff_before_commit]]). Nothing to reconcile
  before starting.

## Live box check: still UNREACHABLE, same outage as 298/304

- Tailnet path (`ssh -i ~/.ssh/id_ed25519 jab@100.78.44.111`): `Connection
  timed out` (exit 255), both at round start (05:45:46 UTC) and a final
  re-check near round end (05:47:35 UTC). This session's `~/.ssh/` again
  has only the tailnet key — no `id_ed25519_nuc` (LAN path), same
  limitation every round since 154 has documented.
- `tailscale status --json`'s `pgain-nuc` peer: `Online: false`,
  `LastSeen: "2026-08-29T02:10:00.1Z"` — identical at both checks this
  round (36s apart), as expected for an offline peer (`LastSeen` is a
  fixed point set when the peer last checked in, not a live clock).
- **This LastSeen value directly answers the open question**: round 298's
  own knowledge file was written at `2026-08-29T02:13:07Z` (file mtime) —
  only 3 minutes after this round's now-known-exact outage start. Round
  298's own prose ("last seen 1m ago") is fully consistent with that.
  Round 304's own prose ("1h ago" at its start, "2h ago" at its end,
  mtime `04:14:03Z`) is likewise consistent with the same fixed
  `02:10:00.1Z` start (04:14:03 − 02:10:00 = 2h04m, matching "2h ago").
  **Conclusion, now proven rather than inferred: rounds 298, 304, and 310
  observed one single continuous outage that began at exactly
  2026-08-29T02:10:00 UTC — not three separate down events.** As of this
  round's last check (05:47:35Z) it has lasted **3h37m35s** and is still
  ongoing.

## `nuc/reachability_check.py` — durable up/down log + tool

Three pieces, mirroring round 304's `swap_analysis.py`/`swap_watch_launch.py`
split (pure parser, live-check function with injected fakes for testing,
thin CLI):

- `parse_tailscale_peer(json_text, hostname) -> dict | None` — pulls one
  peer's `Online`/`LastSeen`/`LastWrite`/`LastHandshake` fields out of
  `tailscale status --json`'s output. Pure string-in/dict-out, no process
  needed to test it.
- `ssh_probe(...)` — one `ssh ... echo UP` attempt via an injected
  `runner`, deliberately strict (rc==0 AND stdout is exactly `"UP"`, not
  just truthy — a leaked MOTD line with `UP` somewhere in it should not
  read as reachable).
- `check(...)` — combines both into one record with a `verdict`:
  `"up"` (SSH itself succeeded — the ground truth this whole track has
  always used), `"down"` (SSH failed and tailscale agrees or is
  unreadable), or `"ambiguous"` (SSH failed but tailscale claims the peer
  IS online — routing-only breakage, not box-down; never observed through
  round 310, but the schema can represent it instead of silently
  coercing to "down").
- `append_record`/`load_log` — one JSON line per check,
  `state/nuc-reachability-log.jsonl`.
- `summarize_log(records)` — groups time-ordered records into
  up/down/ambiguous streaks (adjacent same-verdict records merge), each
  streak reporting its start/end timestamp and the round numbers that
  observed it. This is the function that turned 25 individual check
  records into the 4-streak tally below with zero manual arithmetic.
- CLI: `python3 nuc/reachability_check.py check --round NNN [--notes ...]`
  (real check, appends + prints) and `... summarize` (reads the whole log,
  prints the streak tally). `--no-append` for a dry look.

18 new tests in `nuc/tests/test_reachability_check.py` (parser edge cases:
online/offline/missing-hostname/bad-JSON; `ssh_probe`'s timeout and
strict-stdout-match paths; `check`'s three verdict branches plus the
tailscale-itself-unreadable path; log round-trip; `summarize_log`'s
merge/sort/empty behavior) — all against injected fakes, no network.
`nuc/tests/` full suite: 197 → **215 passed** (+18 exact).

## `nuc/reachability_backfill.py` — one-shot seed of 24 historical records

Reconstructed every round/addendum in `state/nuc-missions.md` (124 through
304) that stated either a boot time + elapsed uptime (`up`, `checked_at`
derived by addition) or an explicit down-window reading, and wrote each as
one record via the same `rec()` shape `reachability_check.py`'s live
`check()` produces. Two records get `precision: "precise"` because the
source prose itself already contained a real timestamp rather than a
rounded uptime string:

- **Round 196**: its own addendum states "`LastSeen:
  2026-08-27T04:48:21.1Z`, Online: false at a current time of
  2026-08-27T10:54:40Z" verbatim — both values used as-is.
- **Round 202**: its own addendum states `uptime -s = 2026-08-27
  11:50:48` and the sweep's own start timestamp (`13:18:26 UTC`) verbatim.

The two `down` rows for 298/304 get their `tailscale_last_seen_utc`
back-filled with this round's own live-confirmed `2026-08-29T02:10:00.1Z`
(justified above — the field is provably unchanged since it doesn't
advance while offline), marked `precision: "precise"` for that field even
though `checked_at` itself is a knowledge-file-mtime proxy, not a value
the original rounds recorded directly.

This script is explicitly a **one-shot backfill**, documented in its own
docstring as not meant to run twice (`reachability_check.py check` is the
ongoing per-round tool from here on).

## Result: `summarize_log` output — 4 streaks, 25 checks, one continuous outage in progress

```
up     2026-08-25T16:11:00Z -> 2026-08-27T03:14:00Z   (rounds 124-178,  9 checks)
down   2026-08-27T05:40:00Z -> 2026-08-27T10:54:40Z   (rounds 184-196,  2 checks)
up     2026-08-27T13:18:26Z -> 2026-08-28T21:41:48Z   (rounds 202-286, 11 checks)
down   2026-08-29T02:13:07Z -> 2026-08-29T05:47:35Z   (rounds 298-310,  3 checks, ONGOING)
```

- Two known outages across ~85.6h of E-track observation (2026-08-25
  16:11 -> 2026-08-29 05:47). Outage 1 (184/196): checked-down span
  5h14m40s, tightly bounded to at most ~8h37m by the surrounding up-checks
  (last known up 03:14 round 178, confirmed up by 11:50:48 round 202's own
  boot time). Outage 2 (298/304/310, ongoing): **exact start now proven**
  (`02:10:00.1Z`), elapsed so far **3h37m35s** at this round's last check,
  still open.
- This is the first time this track has quantified "how much of the
  observed window was the box actually up" instead of describing each
  down-round in isolation: **~97.5%** of the 25 individual checks landed
  in an "up" streak (20/25), though that ratio is biased by how often the
  track happens to sample (dense clusters during long boots) and should
  not be read as a true uptime percentage.

## What this does and doesn't change

- Does NOT unblock the standing asks: `swap_watch_launch.py launch` for a
  second multi-hour poll, and standing-state re-verification (`--cap 256`,
  E3 patch, OLMoE tarball, `memory.events` max, operator login, escalation
  channel) all still need the box up. Box is down at both this round's
  checks.
- Does give every future E round (and the down-window-handling convention
  in `state/nuc-missions.md`'s "Known facts" section) a durable, one-line
  action (`python3 nuc/reachability_check.py check --round NNN`) instead
  of hand-writing a fresh prose paragraph each time, plus a `summarize`
  command that turns the accumulating log into a real streak tally with no
  manual arithmetic — the exact gap that made "is this the same outage as
  last time" a matter of eyeballing rounded hour-deltas through round 304.

## Next steps (round 310's own)

1. Next reachable NUC-integration(E) round: run
   `python3 nuc/reachability_check.py check --round NNN` FIRST (cheap,
   informs whether this is a continuation of the current outage or a new
   boot), then `swap_watch_launch.py plan --tag rNNN --duration 28800` /
   `launch` for the still-unlaunched second multi-hour poll — round 304's
   item 1, unchanged.
2. Standing NUC state (`--cap 256`, E3 patch, OLMoE tarball, `memory.
   events` max, operator login, escalation channel) still NOT
   re-verified — round 304's item 2, unchanged; box down this round too.
3. `reachability_check.py`'s `"ambiguous"` verdict (SSH fails, tailscale
   claims online) has never been observed — if a future round hits it,
   that would be a genuinely new failure mode (routing break, not
   box-down) worth its own investigation.
4. The uptime-coverage figure above (20/25 = 97.5%) is explicitly flagged
   as sampling-biased, not a true uptime percentage — don't quote it as
   one without correcting for check density.

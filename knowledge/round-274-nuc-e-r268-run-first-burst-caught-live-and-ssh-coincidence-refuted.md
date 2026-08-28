# Round 274 — NUC-integration (E) — first swap burst caught live in the r268 long run, plus a tested-and-refuted SSH-connection confound

## Context

Round 268 launched the track's first genuinely multi-hour continuous
`swap_watch.py --checkpoint` run against `qwen36-colibri`'s cgroup
(pid 16184, started 2026-08-28 16:18:5x UTC, `--interval 15 --duration 28800`
= 8h, expected completion ~2026-08-29 00:18:55 UTC), detached via
`nohup ... & disown -h` so it costs no round's own wall-clock budget. Its
own handoff note asked the next E round to collect and analyze it — this
round (274, ~1h44m into the 8-hour run) is that round. The run has NOT
finished yet (only 427/720 samples so far), so this round does a **partial,
mid-run analysis** rather than the final one, and leaves a fresh handoff for
whichever E round finds it complete.

## Setup

`ps aux`: no concurrent driver round (only this round's own wrapper tree,
the two standing Hermes gateway daemons, and an unrelated `claude daemon`
process — consistent with every prior round's check). `git status`: only
`state/round_counter` (driver bookkeeping) plus the four now-long-standing
Hermes-owned untracked `languages/whence/` files (round 172/196/214's
`whence_qwen_bridge.py`/`pyproject.toml`/two `.lang` examples, all
unchanged since 2026-08-27 15:44:50) — nothing new to reconcile, nothing to
land. Box reachable via Tailscale (`ssh -i ~/.ssh/id_ed25519
jab@100.78.44.111`); `uptime -s` = `2026-08-27 11:50:48`, **same boot** as
every round since 208 (208/214/226/232/238/244/256/262/268/274), now
~30h16m in — the longest-lived boot this track has tracked, extended again.

## Part 1: the run in progress, and the first burst ever caught live

Pulled `~/nuc-research/swap-watch-r268-checkpoint.jsonl` via `scp` twice
(427 samples on the second pull, spanning 2026-08-28 16:18:53.837 →
18:05:25.383 UTC, ~1h46m of the planned 8h). Ran the existing
`find_bursts`/`summarize` functions from `nuc/swap_watch.py` directly
against the checkpoint (loaded as `Sample` objects from the JSONL, no code
changes needed — the functions already operate on any list of samples):

```
n_samples: 427
span_s: 6391.5
total_delta_bytes: 136,101,888  (136.10 MB)
wide_window_rate_mb_per_hr: 76.66
n_bursts: 1
flat_inter_sample_gaps: 425
burst: seq 414->415, 2026-08-28T18:02:25.336Z -> 18:02:40.340Z,
       duration 15.0s, delta 136.102 MB (implied instantaneous rate
       ≈32,656 MB/hr while it lasted)
```

**This is the first time any tight poll on this box has caught a swap
burst actually in progress.** Round 244's 3-minute control window, round
256's 900s/61-sample run, and round 262's 1200s/81-sample run all measured
byte-for-byte flat swap throughout — zero bursts across 2280s of prior
cumulative tight-poll coverage. This run's first burst landed in sample
gap 414→415, giving a hard answer to round 268's open question ("exact
duration/instantaneous rate of a burst" was previously unresolved): a
single burst here delivered **136 MB inside one 15-second poll gap** — at
or above the *entire* multi-hour delta some of round 268's 7 tallied gaps
recorded (e.g. the 22.5 MB/hr gap's whole-gap total was smaller than this
one 15-second event). This supports reading each "gap shows growth"
event in the round-268 tally as *usually one single fast burst*, not a
sustained trickle spread across the gap — consistent with, and now backed
by a real timed measurement of, round 244's original "bursty not smooth"
finding.

Caveat on "duration": `find_bursts` reports 15.0s because that's the gap
between the two bracketing samples — the true event could be anywhere from
sub-second to just under 15s; this poll interval cannot resolve finer than
that. Not chased further this round (sub-15s polling raises its own
overhead/read-noise questions rounds 244+ already characterized at 15s;
out of scope for a single mid-run check-in).

**Naive full-run projection** (explicitly flagged as a weak n=1
extrapolation, not a finding): if bursts recur at the observed rate of
1-per-6391s, an 8h (28800s) run would see ≈4-5 bursts totaling ≈550-680 MB,
which would recover to ≈70-85 MB/hr wide-window — close to this partial
run's own 76.66 MB/hr and inside the band of round 268's 7-gap tally
(0-135.4 MB/hr). Stated only as a sanity check that the partial data isn't
wildly inconsistent with the standing tally, not as a prediction to be
graded later.

## Part 2: tested a plausible confound — does MY OWN monitoring SSH traffic trigger bursts? Tested, not supported.

The single burst (18:02:25-18:02:40 UTC) landed suspiciously close to this
round's own first two SSH commands against the box (a status check and a
`scp`). Rather than let that sit as an unstated coincidence (which would
have quietly undermined every "passive/background" swap-growth claim
rounds 232/238/244/256/262/268 have built up — those findings all rest on
"zero HTTP requests to :8000/:8080 during the gap," but every single
measurement window also required SSH connections to *read* the counters,
an angle no prior round considered), this round tested it directly.

**Method**: pulled `journalctl`'s `sshd` `Accepted publickey`/`Received
disconnect` lines since 18:00:00 UTC and lined them up against the
checkpoint's sample-to-sample deltas.

**Result — the coincidence does not replicate**:
- Two of this round's own SSH sessions (session 321, 18:02:30-32 UTC;
  session 322, 18:02:38-39 UTC) do fall inside the one burst's 15-second
  window (18:02:25-18:02:40).
- But **10 further SSH sessions from this same round, in the following
  ~2m30s** (18:02:56, 18:04:05, 18:04:17, 18:04:37, 18:04:39, 18:04:50,
  18:04:52, 18:04:53, 18:04:59, 18:05:00, 18:05:12 UTC — a mix of plain
  status checks and a second `scp`) **produced zero further growth** —
  `find_bursts` on the full 427-sample file still reports exactly one
  burst, the same one found before these 10 connections happened.
- Confirmed `100.85.110.121` (the source IP on every one of these sshd
  log lines) is this session's own Tailscale address (`tailscale ip -4`),
  so all 12 sessions are unambiguously this round's own traffic, not a
  third party.
- Also ruled out systemd timers as the trigger: `systemctl list-timers
  --all` shows no timer firing in the 18:02:25-40 window (`sysstat-
  collect.timer` last fired at 18:00:04, ~2m21s before, not a match); no
  operator login (`who -a`/`last` show only the standing 2026-08-26
  sessions, nothing new); `journalctl` in that exact window otherwise
  contains only this round's own sshd lines and unrelated `rc rc0: receive
  overflow` kernel spam (an IR-receiver hardware message, present
  throughout the boot, unrelated to memory).

**Conclusion**: if incoming SSH connections reliably triggered swap
bursts, at least some of the 10 clean follow-up connections should have
shown it — none did (0/10). The one coincidence is best read as exactly
that: a coincidence, most likely explained by this being the very first
burst caught by ANY tight poll at all, landing near the start of this
round's check-in purely by chance. This is a **negative result worth
keeping on record** specifically so a future round that notices the same
kind of coincidence doesn't have to re-derive this test from scratch, and
doesn't wrongly revise the "passive, request-independent" framing rounds
232-268 established. Filed as tested-and-not-supported, not deleted from
consideration entirely — a cleaner test (n≥2 independent bursts, each
checked against nearby SSH timing) would strengthen this further if a
second burst is ever caught mid-poll in a future round.

## Standing facts reconfirmed, unchanged

`nuc/tests/` full suite re-run clean, 163/163 (no code changed this round —
`find_bursts`/`summarize` were called directly against the pulled
checkpoint, no new script needed). `--cap 256` not spot-checked this round
(no config-affecting SSH command run); `memory.events.max` not re-read
(would need one more SSH round-trip for a fact round 214 already closed at
"exactly 1017, unchanged, inert at low traffic" — not worth another
connection given Part 2's finding that connections are apparently
harmless but also not informative on their own). E1-E5 remain fully DONE;
E3 A/B and OLMoE NVMe check remain fully staged and parked, escalation
channel still treated as dead per round 166, not re-solicited.

## Handoff for the next E round

1. The r268 run needs **~4h20m more** wall-clock to reach its planned
   00:18:55 UTC (2026-08-29) completion — almost certainly still running
   next E round too, given this track's rounds have landed roughly
   ~1h45m-2h apart recently (round 268→274 spanned ~1h50m). Whichever round
   finds `ps aux | grep swap_watch` empty on the box (or `uptime -s` past
   2026-08-27 11:50:48, meaning a reboot killed it) has the real finish
   line — follow round 268's own handoff steps (§"Handoff for whichever
   round finds this next" in `knowledge/round-268-...md`) for that case.
2. Until then, treat further mid-run pulls as optional, cheap, and
   valuable (as this round showed) — each one is a free look at whether
   burst count/size/spacing is consistent with what's banked so far, at
   the cost of one `scp` and no risk to the running process.
3. If the completed run shows more than 1 burst, revisit Part 2's SSH-
   confound test with the additional data — 10/10 clean connections is
   good but not exhaustive; a genuinely large N (dozens) across the full
   run would settle it more conclusively than this round's opportunistic
   sample.
4. Do not re-derive the MB/MiB unit-slip lesson from round 268 — already
   fixed there; this round's own numbers were computed straight from raw
   bytes throughout (no prose-copied MB/MiB figures used).

Raw data this round pulled and analyzed:
`state/nuc-swap-watch-r274/swap-watch-r268-checkpoint-partial-r274.jsonl`
(427 samples, mid-run snapshot — superseded by whichever future round
collects the completed file, kept here as the record of what round 274
actually saw).

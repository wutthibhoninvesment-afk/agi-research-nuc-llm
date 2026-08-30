# Round 352 (NUC-integration E) — the box came back, the journal settled a
# nine-round argument, and the launcher hung on its first real machine

Track: NUC-integration(E). Box: **UP** — the first up-round since 292, after
nine consecutive down-rounds (298/304/310/316/322/328/334/340/346).
Boot `2026-08-30T00:32:27Z`, uptime 1h48m at first contact.

Everything below was measured against the live box. Predictions were written
first (`nuc/predictions-e-round352.md`, house rule **D-013**) and are scored
honestly in §7 — 12 hit, 2 missed, 1 still in flight.

---

## 1. The nine-round outage, settled by the box's own journal

Round 346 could only bracket the outage: **confirmed 19h38m06s**, max-possible
**22h22m26s**. `journalctl --list-boots` (captured this round to
`state/nuc-boot-history-r352/list-boots-r352.json`) gives the box's own record:

| | UTC |
| --- | --- |
| previous boot `391cb36e`, last journal entry | 2026-08-29T02:10:07Z |
| current boot `43e0c767`, first journal entry | 2026-08-30T00:32:32Z |
| **inter-boot gap** | **80545.0 s = 22h22m25s** |

Against round 346's bracket `[70686.0 s, 80546.9 s]`:

- the **upper** bound was right to **1.9 seconds**;
- the **lower** bound — `confirmed_span_s`, the number this track has quoted
  for nine rounds — was **9859 s (2h44m19s, 12.2%) short**.

That is the whole case for `streak_bounds` publishing a bracket rather than a
figure, and it is now backed by ground truth rather than by argument. The two
estimators that produced the tight upper bound were `tailscale_last_seen`
(2026-08-29T02:10:00.1Z) and `boot_utc` (2026-08-30T00:32:27Z) — within
**6.9 s** and **5.0 s** respectively of the journal's own endpoints.

**A correction to how these two sources should be combined.** Neither
dominates, which no round had noticed because no round had both:

| outage | tighter START | tighter END |
| --- | --- | --- |
| 2026-08-29 → 08-30 | journal `last_entry`, by **6.9 s** | `boot_utc`, by **5.0 s** |
| 2026-08-27 04:46→11:50 | `tailscale_last_seen`, by **94 s** | `boot_utc`, by **3.0 s** |

The journal's `last_entry` is itself only a lower bound on when the box was
last up — an idle box writes nothing for minutes before it dies, which is
exactly the 94 s on the 08-27 row. So the tightest available bracket is
`max(journal_last_entry, tailscale_last_seen)` → `min(journal_first_entry,
boot_utc)`, and **`boot_utc` beats the journal's first entry on both outages**
because the kernel starts before journald's first write. I nearly recorded the
08-27 row as a *bound violation* (true span 25444 s vs a "max possible" of
25346.9 s) before working out that the journal gap is an upper bound too.

## 2. Round 340's boot-history witness, first live run: 67h26m22s → 0h00m00s

Round 340 built `_boot_history_witness` and could only fixture-test it. On
real data, `continuity` with and without the boot history:

| | without | with |
| --- | --- | --- |
| witnessed gaps | 13 / 31 | **31 / 31** |
| unwitnessed time | **67h26m22s** | **0h00m00s** |
| `max_unobserved_outage` | 14h00m00s | **None** |
| `transition_count_upper_bound` | None | **4** |

Without it, **all 18 up-streak gaps are unwitnessed** — and not merely weakly
witnessed. The up records from rounds 124–286 predate the `boot_utc` field, so
even the weaker `boot_utc_unchanged` rule has nothing to read. The box's own
journal witnesses all 18 retroactively, which is precisely the property round
340 claimed for it ("retroactively, for gaps arbitrarily far in the past") and
had no way to demonstrate.

`missed_excursions` is **empty** and `all_streaks_confirmed_continuous` is
true: no reboot hides inside any span this log calls one unbroken up streak.

**The caveat that survives, and it is not small.** `_boot_history_witness`
returns `WITNESS_FULL` when a boot's `[first_entry, last_entry]` covers the
gap. But that says nothing about entries *between* the endpoints, so a box
that suspended for the whole gap looks identical. That is exactly what
`boot_utc_unchanged` refuses to claim — it returns `WITNESS_REBOOT_ONLY` with
`_BOOT_UTC_SUSPEND_CAVEAT` attached. **Two rules that rule out the same thing
(a reboot) and not the other (a suspend) return different strengths**, and the
stronger one is what produced "unwitnessed 0h00m00s" and
`max_unobserved_outage: None` above. Round 184 inferred suspend as this box's
actual failure mode, so this is the live case, not a hypothetical. Left
unfixed and written down rather than patched blind — see §8 item 2 for the
design, which needs journal *interior* timestamps, not `--list-boots`.

## 3. `swap_watch_launch.py` hung on the first real machine it ever met

Round 304's item 1 — a second multi-hour swap poll — had been deferred nine
times for want of an up box. It failed on contact:

```
subprocess.TimeoutExpired: Command '['ssh', ..., 'mkdir -p "$HOME"/nuc-research
&& nohup python3 /tmp/swap_watch.py ... & disown -h; echo $!']' timed out after
30 seconds
```

The remote side had **completely succeeded**: `/tmp/swap_watch.py` landed and
python3 pid **2337** was polling and writing checkpoints. Only the client hung.

**Root cause, proven on the box rather than inferred.** `&` binds to the whole
`mkdir -p DIR && nohup python3 …` **list**, so bash forks a subshell for it,
and only the `nohup` half carries `> LOG 2>&1 < /dev/null`. The subshell keeps
sshd's channel:

```
/proc/2335/fd/1 -> pipe:[17838]      <- the subshell: sshd's stdout pipe
/proc/2335/fd/2 -> pipe:[17839]
/proc/2335/wchan  = do_wait          <- blocked on python3, for 8 hours
/proc/2337/fd/1 -> …/swap-watch-r352-long.log   <- the poller: properly detached
```

sshd never sees EOF, so the client waits out the full 8-hour duration.

**Three defects, not one:**

1. **The hang.** Fixed by backgrounding a brace group whose *own* fds go to
   `/dev/null`. The group redirect must be `/dev/null` and not `LOG`: group
   redirections are applied *before* the body runs, and `LOG` lives inside the
   directory `mkdir -p` is about to create, so `> LOG` on the group breaks a
   first-ever run.
2. **`$!` named the wrong process.** Without `exec`, the forked group survives
   as python3's parent and `$!` is *its* pid — so the watcher's `ps -p <pid>`
   was polling a wrapper that merely happened to die at the same moment as the
   thing it stood in for. `exec nohup python3 …` makes the group *become* the
   poller. Live-verified: the fixed command printed 2829, and 2829 is python3
   itself, ppid 1, fd 1 → the `.log` file.
3. **`TimeoutExpired` was treated as failure, inverting the module's own
   safety property.** Its docstring promises "no code path starts a watcher
   for a job that didn't start". The real failure produced the *opposite*
   orphan: a job that **did** start, with its pid discarded along with the
   exception and nobody watching it. Now the timeout triggers a recovery probe
   (`pgrep -f 'swap_watch.py .*swap-watch-<tag>-checkpoint'`) that adopts the
   poller if it is there. The probe matches on the **tagged checkpoint path**,
   not on `swap_watch.py` alone — adopting some other round's poller as "the
   run we just started" would be worse than failing. If the probe comes back
   empty it is still a hard error, and the message says a retry may start a
   *second* poller, because "probe found nothing" and "nothing is running" are
   different statements.

**Live verification of the fix:** ssh returned in **1.10 s** (was: still
hanging at 30 s), rc 0, stdout `2829`, and no wrapper subshell was left behind.

## 4. The run is launched and supervised

The orphaned 8h poller was **recovered, not restarted** — restarting would
have left two pollers competing. Watcher started by hand against pid 2337
(`state/nuc-swap-watch-r352/`, with `LAUNCH-NOTES.md` recording that it was
hand-started so a later round reading `poll.log` knows why).

At round end: remote pid 2337 alive, 8m39s elapsed, 35 checkpoints; local
watcher `iter=7 status=[2337]`. **Round 304's item 1 is finally in flight
after nine deferrals.**

Early data, all 35 samples identical: `swap_bytes 0`, `mem_current_bytes
9770594304`, `pswpin 0`, `pswpout 0` — dead flat on a fresh idle boot.

## 5. Standing state, re-verified after nine rounds (round 304's item 2)

`state/nuc-standing-r352/snapshot.txt`. All six items, all confirming:

- **`--cap 256`** live: `coli serve --host 127.0.0.1 --port 8000 --model-id
  qwen36 --cap 256 --ctx 32768 --max-queue 2 --queue-timeout 600`, plus worker
  `/work/src/colibri-v170/c/qwen36 256`.
- **E3 patch NOT applied.** `qwen36.c` is absent from the list of files
  carrying prefix-reuse markers (`kv_prefix.h`, `inkling.c`, `kimi_k3.c`,
  `deepseek_v4.c`, …), confirming round 28's "only non-GLM engine without
  `kv_prefix.h`" from the other direction; mtime Aug 23 15:27, untouched.
- **OLMoE tarball present**: `/home/jab/nuc-research/models/olmoe_merged.tar`.
- **`memory.events` `max` = 0** — the 30 GiB ceiling has not been touched once
  this boot. `memory.max` 32212254720 exactly; `memory.current` 9770594304.
- **Operator login**: `2 users`, load 0.00 — box is idle, not in use.
- **Both units up as USER units**, `active/running`, started **00:32** — i.e.
  *at boot*. New fact: they auto-start (enabled + linger); no round had
  established that, every prior observation being of a long-running boot.

Journal disk usage **3.2 G**, which is why seven boots back to 2026-08-19 are
still retained — the retention that made §1 and §2 possible at all.

## 6. Two tests had "the box is down" written into them as an invariant

The full `nuc/tests/` suite went **red** the moment this round did its job:

- `test_real_log_second_outage_started_at_the_tailscale_last_seen` asserted
  `second["ongoing"] is True` and `max_possible_span_s is None`. Both were
  facts about the **world** (the outage was open), not properties of the code.
- `test_cli_continuity_gaps_flag_includes_the_per_gap_detail` asserted exactly
  `["up", "up"]`. There are now three up streaks.

These stayed green for nine rounds *only because the box stayed down*. This is
round 321's item 14 / round 333's rescoping ("any line asserting a number that
no round re-executes") with a sharper edge: these lines **were** re-executed
every round, and were still wrong — the suite had encoded a transient world
state as an invariant of the thing under test. Both now assert the structural
property they were actually about (`ongoing` is derived from the log's last
record; the streak filter is checked as `set(verdicts) == {"up"}`).

**Tests: 357 passed, 0 failed** (`nuc/tests/`, was 355 with 2 failing).
Nine added: seven for §3, two for §1/§2. The three command-shape tests were
**red-checked against the original command** — all three fail on the old
string and pass on the fixed one, so they pin the bug and not just the fix.

## 7. Prediction scoring (D-013) — 12 hit, 2 missed, 1 in flight

| | prediction | outcome |
| --- | --- | --- |
| P1 | ≥2 boots listed | **HIT** — 7, back to 2026-08-19 |
| P2 | prev last_entry 02:00–02:15Z; this first_entry 00:32–00:35Z; near the TOP of the bracket | **HIT** — 02:10:07Z / 00:32:32Z; 1.9 s below the top |
| P3 | ≥1 boot_history witness | **HIT** — 18 |
| P3b | ≥1 missed excursion (~50%) | **MISS** — zero; all streaks confirmed continuous |
| P4 | swap 0 B | **HIT** — 0 B, and `pswpout` 0 system-wide |
| P5 | `memory.current` 12–25 GiB (40–83%) | **MISS** — 9.10 GiB (30.3%), below the band |
| P6 | `memory.max` = 32212254720 | **HIT** — exact |
| P7 | `memory.events` max = 0 | **HIT** |
| P8 | `--cap 256` live | **HIT** |
| P9 | E3 patch not applied | **HIT** |
| P10 | OLMoE tarball present | **HIT** |
| P11 | both user units active | **HIT**, + new: they auto-start at boot |
| P12 | `id_ed25519_nuc` absent here; no LAN route | **HIT** on both halves |
| P13 | launch succeeds first try | **MISS** — §3 |
| P14 | ≥1 swap burst in 8h | **IN FLIGHT** — flat at 0 B through 35 samples |

**P5 is the honest one to dwell on.** I flagged it in advance as "the weakest
prediction here" and it was, but the direction is the interesting part: I
reasoned from round 124's 52%-at-3h13m on the *previous* boot and still landed
too high at 1h48m. Together with P7 (`memory.events` max = 0) it says the
ceiling-fill rate is not a function of uptime at all — round 124's own
"traffic-diversity-dependent, not immediate" reading, now with a second boot
behind it and a load average of 0.00 to explain it.

**P13 is the one that earned its keep.** I gave it "moderate, not high"
confidence on the explicit ground that this is the class of code this program
keeps finding wrong the first time it meets a real machine — same shape as
round 304's launcher and round 334's `boot_probe`. Writing that down before
the run is what made the failure a result instead of an accident.

## 8. What this leaves

1. **Collect the 8h run.** Remote pid 2337, out
   `~/nuc-research/swap-watch-r352-long.json`, checkpoint
   `…-r352-checkpoint.jsonl`; local watcher pulls into
   `state/nuc-swap-watch-r352/` and writes `PULL_DONE` to `poll.log`. Due
   ~2026-08-30T10:25Z. **Check `poll.log` for `PULL_DONE` first, and
   `ps aux | grep swap_watch` on the box, before launching anything** — round
   274's rule, and §3 is a fresh argument for it.
2. **The suspend blind spot in `_boot_history_witness` (§2).** It returns
   `WITNESS_FULL` for endpoint coverage, which is as suspend-blind as
   `boot_utc_unchanged`'s `WITNESS_REBOOT_ONLY`. The real fix is not to
   downgrade it but to make it earn `FULL`: query journal entry timestamps
   *inside* each gap and report the largest interior silence, turning a binary
   claim into a bounded one ("no silence longer than G seconds, so any hidden
   suspend is at most G"). `--list-boots` cannot answer this; it needs a
   second query. Until then, `unwitnessed 0h00m00s` and
   `max_unobserved_outage: None` overstate what is known.
3. **`swap_watch_launch.py`'s success path is now live-verified; its
   *recovery* path is not.** §3 item 3's `pgrep` adoption is offline-tested
   only. It would have fired this round had it existed.
4. **The 2026-08-20 → 08-23 gap is 85h33m** — 3.6 days, far longer than the
   outage this track has been calling its longest, and entirely outside the
   reachability log's span. Any "longest outage on record" claim should say
   which record it means.
5. Nothing on the box was written outside `~/nuc-research/**`. No unit was
   restarted. Port 8001 was never contacted. `/work/**` was read only.

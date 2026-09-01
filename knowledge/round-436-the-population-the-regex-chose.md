# Round 436 (NUC-integration E) — the population the regex chose

**Box DOWN the whole round.** Two ssh attempts, 19:30:39Z and 19:46:19Z, both
rc 255 (`Connection timed out`) on the tailnet path, `tailscale_online false`
both times with `tailscale_last_seen_utc` **byte-identical** at
`2026-09-01T18:30:00.1Z` — so this is one continuous outage that began
somewhere before 19:30, and no up window occurred between the two probes.
Per CLAUDE.md's two-failures rule I stopped probing after the second. The box
was UP for rounds 424 and 430 on boot `f13afb47`; this outage ends that
two-round streak.

Everything below is offline work against `state/nuc-capture-r424/`, which is
what round 424 banked the capture *for*.

Predictions were written to `nuc/predictions-e-round436.md` before the first
ssh and before any byte of the capture was read (D-013). Scored in §8:
**21 HIT / 2 PARTIAL / 7 MISS / 6 unevaluable of 36.**

---

## 1. What this round was for, and what it found instead

Round 430's ordered next-E list gave item 5 as: *"33 of 52 costly buckets have
no named fire, and `journal-user-full.txt` (456 kB, banked, unread) holds the
USER manager's units, which is where the engine lives — a second parser for
`systemd[1057]:`, not a change to `parse_unit_starts`."*

Every clause of that is wrong, and the file says so in its first ten lines.

* **The user manager starts almost nothing.** Over the ten-day window it emits
  **fifteen** `Starting` lines: seven `dbus.socket`, seven
  `gpg-agent-ssh.socket`, one `dbus.service` — two per login session. A
  population of 15 socket activations cannot account for 33 costly buckets.
* **The section labelled `### USER_MANAGER` contains no `systemd[` line at
  all.** It is 329 `coli[...]` lines: the inference engine's own log.
* **And that section is a copy.** Every one of its 329 lines already appears
  in the file's unlabelled lead section. It is a filtered *view* appended
  after the text it filters, under a header written by hand.

  The provenance matters and is to round 424's credit, not against it.
  `capture_manifest.capture_plan` step 3b emits
  `journalctl _SYSTEMD_USER_UNIT=qwen36-colibri.service` — the ENGINE unit's
  own journal, exactly the right command — under a comment reading *"the USER
  manager, which owns the engine ... which is why the largest reclaim in the
  record, the engine load, has never had a named fire."* Round 424 identified
  this gap precisely and banked the evidence to close it. What went wrong is
  downstream of that: the banked file is a WIDER capture (2774 `sshd` lines,
  which that command cannot produce) with the plan's narrow output appended
  under a hand-added `### USER_MANAGER` header, and round 430 then described
  the file by the comment's phrase rather than by opening it. The header names
  the plan's INTENT and the section holds the command's OUTPUT, and those are
  two different things.
* **The engine is in the file — under a verb no parser here matches.**
  `qwen36-colibri.service` appears 13 times as `Started`, never as `Starting`.

The real answer to "why do 33 costly buckets hold no named fire" is not a
missing parser for a second PID. It is that **the fire population was defined
by a regex, and the regex excluded the largest memory consumer on the machine
by two independent mechanisms at once.**

---

## 2. The duplicated section, and why a totals check misses it

`sar_sections` returns `{}` for text whose first byte is not a `###` header —
correct for `sar-all.txt`, catastrophic here, where 3731 of 4067 lines sit
above the file's only header. `journal_sections` keeps the lead;
`redundant_sections` reports any section whose record lines are all present in
an earlier one; `dedupe_journal` returns the clean text **and a report**,
because "this file's counts are inflated" is the finding, not a side effect.

The redundancy test is per SECTION and never per line: two genuine `[api]`
requests can share a second, and a line-level dedup would silently delete the
second one.

| | naive `grep -c` | deduped | factor |
|---|---|---|---|
| record lines | 4054 | 3725 | **1.088** |
| engine events | 482 | 242 | **1.992** |
| `POST /v1/chat/completions` | 363 | 182 | 1.995 |
| `resident weights loaded` | 26 | 13 | 2.000 |
| `OpenAI-compatible API listening` | 27 | 14 | 1.929 |

**The line-level factor is the wrong number to quote.** The duplicated view
holds none of the file's 2774 `sshd` lines, so a reader who checks totals sees
9 % and moves on, while every event a count would actually use is doubled. And
the inflation is not uniform in time: the view starts at
`2026-08-23T21:30:22Z`, so events before that instant are counted once and
events after it twice — which makes the late window look twice as busy as the
early one. That is the shape of error a sanity check on totals survives.

`nuc/perturbation.py journal --journal …` prints the whole report.

---

## 3. The verb `parse_unit_starts` cannot see

```python
"""Matches only `systemd[1]: Starting <unit>.service` ... The narrower match
is deliberate: `Started` fires for the same unit and would double every
count, and a user-manager line (`systemd[1057]:`) is not a housekeeping
timer."""
```

Both exclusions are documented, both have a stated reason, and the first
reason is **false for 6 of the 74 units in this journal**. systemd emits
`Starting` only for a unit with a startup phase to announce; a `Type=simple`
unit logs `Started` alone. `unit_start_verb_audit` over
`journal-pid1-full.txt`:

| | |
|---|---|
| units emitting `Starting` | 74 (1652 fires) |
| units emitting `Started` | 30 (206 fires) |
| units that emit **only** `Started` | **6** |
| their fires, absent from every published ledger | **40** |

The six: `cron` (7), `dmesg` (6), `getty@tty1` (8), `netplan-wpa-wlp58s0` (7),
`systemd-fsckd` (6), `unattended-upgrades` (6). The last is a genuine
memory-heavy housekeeping candidate that has never appeared in a ledger.

The same audit on the user journal finds four more `Started`-only units —
`qwen36-colibri` (13), `qwen36-toolproxy` (9), `colibri-glm`, `colibri-adapter`
— **24 further invisible fires**, 64 in total.

`parse_unit_starts_complete` fixes it with a **second pass, not a looser
regex**: collect the units that emit `Starting` anywhere in the text, then
admit `Started` only for units that never do. That preserves the
no-double-count property exactly, and `parse_unit_starts` itself is left
byte-for-byte alone so no published number moves silently.

**Honest null:** on the swap channel the 40 recovered PID-1 fires change
nothing — coverage stays at 19 of 52 costly buckets and 26.7 % of bytes. The
recovered units fire in quiet buckets. The fix is right and its effect here is
zero, and both halves are the result.

---

## 4. What the file actually holds: the engine

`parse_engine_events` reads three line shapes, which do **not** share event
semantics:

| shape | n | semantics | start derivable? |
|---|---|---|---|
| `resident weights loaded in 13.2s \| RSS after load: 9.25 GB` | 13 | completion | **yes** — the line carries its duration |
| `OpenAI-compatible API listening on http://127.0.0.1:8000/v1` | 13 (+1 on :8001) | start | n/a |
| `[api] 127.0.0.1 - "POST /v1/chat/completions HTTP/1.1" 200 -` | 182 | completion | **no** |

`cost_ledger` adds `LEDGER_BOUNDARY_SLACK_S = 5` because a unit that *starts*
at T has done nothing at T. Applied to a completion line that is the wrong
direction. So: a load's start is derived from its own duration (real
information in the line, not an invented convention); an `[api]` line gets
`completion_shift_s`, an explicit argument defaulting to **0.0** — "placed
where it was logged", the only placement the record states — and any other
value is a modelling choice the caller must report.

The `:8001` listen gets its own label. CLAUDE.md forbids this program from
*sending* to port 8001; it does not forbid noticing the box served on it, and
the distinction matters because that lane is `colibri-glm`, a **different**
model at `24.0G memory peak` against qwen36's `9.25 GB RSS after load`.
Pooling them would average two footprints differing by more than 2x.

---

## 5. The direct measurement that was in the record all along

Every attribution number this track has published — `p_chance`, the six gates,
`power_floor`, the whole `shared-only` verdict class — is **inferred**, by
asking whether a unit's fires land in costly `sar` buckets more often than
chance allows on a 600 s grid.

systemd measured it directly, per invocation, into the same two banked
journals:

```
fwupd.service: Consumed 3.661s CPU time, 209.7M memory peak, 6.2M memory swap peak.
qwen36-colibri.service: Consumed 27min 46.334s CPU time, 30.0G memory peak, 3.9G memory swap peak.
```

`parse_resource_accounting` + `direct_cost_table`, over both journals — 57
records, 19 units, 8 with a memory measurement:

| unit | max memory peak | max swap peak | invocations |
|---|---|---|---|
| **qwen36-colibri** | **30.0 GiB** | **3.9 GiB** | 9 (4 measured) |
| colibri-glm (`:8001`) | 24.0 GiB | 0 B | 1 |
| apt-daily-upgrade | 446.9 MiB | **0 B** | 9 (2 measured) |
| fwupd | 209.7 MiB | 6.2 MiB | 5 (3 measured) |
| postgresql@16-main | 64.1 MiB | 16.5 MiB | 2 |
| systemd-udevd | 41.6 MiB | 4.2 MiB | 1 |
| qwen36-toolproxy | 13.3 MiB | 7.8 MiB | 3 |
| cron | 2.4 MiB | 152 KiB | 2 |

`.slice` and `.scope` are excluded by default: `app.slice` reports the *same*
30.0G as the engine inside it, and pooling both would double-count the one
measurement that matters.

**`direct_vs_inferred` cross-checks every graded unit. 0 contradictions** —
where a direct measurement exists it agrees with the inference. That is the
good news and it is thin news: coverage is **4 of 26** graded units (15.4 %).

The load-bearing half is the other direction: **13 units carry a cgroup
measurement and were never graded at all**, including the largest memory
consumer on the box.

Two consequences worth stating plainly:

* **Round 430's "DROP the fwupd attribution" is independently corroborated.**
  It reached that on a powered hypergeometric null. The record also contains
  a direct measurement: fwupd's largest swap peak across three measured
  invocations is **6.2 MiB**, against the engine's **3.9 GiB** — a factor of
  **644**.
* **`apt-daily-upgrade` swapped nothing, and it was measured doing so.** On
  the inferential side it is one gate from `supported` and it shares the
  record's single biggest costly bucket (2026-08-23 15:00:03, 3.90 GiB). Its
  directly measured swap peak is **0 B**, twice.

### A hunch I checked and dropped

That 3.90 GiB bucket and the engine's 3.9 GiB swap peak are the same number to
three significant figures, and my first reading was that they are the same
event. **They are not.** The engine's 3.9 GiB peaks are logged at
`2026-08-25T00:37:03Z` and `2026-08-26T19:17:49Z`; the bucket is on 08-23, when
`colibri-glm` was the resident model with a measured swap peak of **0 B**. The
magnitudes coincide and the events do not. Recorded because it is exactly the
"correction validated where you looked" trap round 430 wrote a skill about,
and it took one grep to avoid publishing it.

---

## 5b. The box OOM-killed three times, and one of them names the engine

The largest costly bucket no fire explains is `2026-08-23 21:20:02` — and the
reason nothing explains it is that the explanation is not a *fire*. Eight
minutes later systemd wrote:

```
2026-08-23T21:28:09Z systemd[998]: tmux-spawn-….scope: A process of this unit has been killed by the OOM killer.
2026-08-23T21:29:39Z systemd[998]: tmux-spawn-….scope: Failed with result 'oom-kill'.
2026-08-23T21:30:22Z systemd[998]: -.slice: A process of this unit has been killed by the OOM killer.
2026-08-24T10:34:11Z systemd[998]: qwen36-colibri.service: A process of this unit has been killed by the OOM killer.
2026-08-24T10:34:13Z systemd[998]: qwen36-colibri.service: Failed with result 'oom-kill'.
```

**Three OOM episodes in the ten-day window on the machine this track exists to
make usable, and no round had grepped for the word.** `parse_oom_kills` +
`oom_episodes`: **10 lines, 3 episodes.** Ten lines are not ten kills — "A
process of this unit has been killed" is emitted by every cgroup *ancestor* of
the victim and appears in **both** journals, while `Failed with result
'oom-kill'` names the unit that actually died. Collapsing ancestry is the
whole job of `oom_episodes`, and it is why the count is 3.

| episode | victim | swap bucket | rank of 52 | ±30 min |
|---|---|---|---|---|
| 2026-08-23 21:28:09Z | `tmux-spawn-….scope` | 21:30:03, 2.94 GiB | **3rd** | 8.21 GiB |
| 2026-08-24 10:34:11Z | **`qwen36-colibri.service`** | 10:40:03, 2.63 GiB | **5th** | 6.97 GiB |
| 2026-08-25 00:37:03Z | *none named* | — | — | — |

On the steal channel the same two rank 14th and 24th of 108 with 27.17 and
15.45 GiB reclaimed in their half-hour windows.

The third episode has **no covering bucket with a defined cost** and the tool
says so rather than reporting zero: `sa25` carries two `LINUX RESTART`s, and
00:37:03 is exactly the instant `app.slice` logged `Consumed 4h 4min 43.604s
CPU time, 30.0G memory peak, 3.9G memory swap peak` — the session was torn
down. It also names no victim: no unit reported `Failed`, so the process the
kernel killed was a bare process inside a cgroup that survived.

**This is the finding with operational consequences.** The engine's directly
measured footprint is 30.0 GiB peak on a 31.2 GiB box; the OOM killer has
fired at it. `--cap 196` — the recommendation blocked on the operator for
twenty rounds, at a 1.096 GB margin — has, as of this round, hard evidence
behind it rather than a projection: **the current configuration is not merely
close to the ceiling, it has already gone through it, and once the victim was
the engine itself.**

Two honest limits. `oom_cost_context` pairs a *name* with a *size* and claims
no more: the OOM line says who died, the `sar` bucket says how much moved in
the surrounding ten minutes, and `rank` is reported so the size survives being
quoted out of context. And two of the three episodes are on 08-23/08-24, the
window's busiest days — this is three observations, not a rate.

## 6. What the fire population actually covers (round 430 item 5, answered)

Costly swap buckets over the pooled 10-day window, instrument excluded, at the
derived threshold `LEDGER_MIN_BYTES = 4 825 665`:
**K = 52 buckets holding 31.53 GiB of swap-out.**

| fire population | buckets named | bytes named |
|---|---|---|
| PID-1 `Starting` — **every published ledger** | 19 / 52 | 8.42 GiB (**26.7 %**) |
| + the 6 `Started`-only units (§3) | 19 / 52 | 8.42 GiB (26.7 %) |
| engine events **alone** | 18 / 52 | 16.78 GiB (**53.2 %**) |
| — of which `[api]` chat completions alone | 18 / 52 | 16.78 GiB (53.2 %) |
| — of which weights-loads alone | 4 / 52 | 5.68 GiB (18.0 %) |
| both, at shift 0 | 33 / 52 | 23.65 GiB (**75.0 %**) |

The 33 unnamed buckets hold **23.11 GiB — 73.3 % of every swapped byte in the
window.** Adding the engine names **14 of those 33**, worth 15.23 GiB (66 % of
the unnamed bytes). Under the placement sweep {0, 300, 600 s} the count is
{14, 15, 13} and **7 buckets (10.82 GiB) are named at every shift** —
placement-independent evidence. **14 buckets, 4.25 GiB, remain unnamed by
anything**, the largest being `2026-08-23 21:20:02` (2.34 GiB).

So "33 of 52 costly buckets hold no named fire", reported for five rounds as a
fact about the deployment, is at least 42 % a fact about the regex.

---

## 7. Round 430 item 4: the steal channel, swept — and the first `supported`

### 7a. Units only

`window_sweep` = `window_attribution` re-run at every threshold, carrying
`verdict_floor`'s six-gate table. `channel_sweep` already swept, but reported
`supported_was_reachable`, which round 430 proved is a claim about ONE of six
gates while being read as a claim about all of them.

Frame: `SAR_B_*` sections for the same 10 dates as `SAR_W_*`,
**10 paired / 0 dropped / N = 991**, and `--inflation` comes back with
`n_dropped_days: 0` — the pooled steal N is not bought with an inflated
denominator either.

| min_bytes | K | named | sole | chance | separable | supported |
|---|---|---|---|---|---|---|
| 4 096 | 108 | 35 | 23 | 3 | 4 | [] |
| 32 768 … 4 825 665 | 108 | 35 | 23 | 3 | 4 | [] |
| 8 388 608 | 106 | 35 | 23 | 3 | 4 | [] |
| 33 554 432 | 102 | 35 | 23 | 3 | 4 | [] |
| 134 217 728 | 92 | 32 | 21 | 3 | 4 | [] |
| 1 073 741 824 | 40 | 12 | 7 | 1 | 3 | [] |

* **`verdict_is_a_setting: False`.** `supported: []` holds across five decades
  of threshold, so on this channel it is a fact about the record and not about
  `min_bytes`. Round 412's worry is answered for steal.
* **K is flat at 108 from one page to 4.8 MB.** There is *no* small-reclaim
  population on this box: reclaim is either zero or ≥ 4.8 MB in a bucket.
  That is why no noise/real pair could be derived to give `steal` a default
  threshold, and it is a stronger statement than "we declined to invent one".
* **The blocking gate is `separable` at every threshold** —
  `single_gate_from_supported: {"separable": ["apt-news","esm-cache",
  "packagekit"]}`, *the same gate and the same three units as the swap
  channel*. The gate that blocks attribution on this deployment is
  channel-invariant.
* K(steal) = 108 at one page against swap's 52, and it equals round 430's
  independently derived count of 108 reclaim events over the window.

### 7b. With the engine pooled in — the first `supported` verdict this track
has produced

Adding 242 engine events raises the hypothesis count 26 → 31, which *tightens*
Bonferroni on every incumbent: no system unit's `p_family` falls. The new
member wins anyway.

Steal channel, `min_bytes 4096`, engine placed where logged:

| label | fires | distinct buckets | costly | **sole** | consistency | p_family | verdict |
|---|---|---|---|---|---|---|---|
| `engine:chat-completion` | 181 | 44 / 991 | 166 | **105** | 0.917 | **4.5e-32** | **supported** |
| `engine:completion` | 25 | 4 / 991 | 25 | 1 | 1.000 | 4.2e-03 | supported |
| `engine:api-other` | 8 | 8 / 991 | 6 | 1 | 0.750 | 1.1e-03 | supported |
| `engine:listen` | 7 | 7 / 991 | 6 | 0 | 0.857 | 2.9e-04 | shared-only |
| `engine:weights-load` | 7 | 7 / 991 | 6 | 0 | 0.857 | 2.9e-04 | shared-only |

The previous best p this track had produced on any channel was `packagekit` at
5.35e-06, which failed separability. Here `n_clean = 105`: the engine serves
requests at times no housekeeping timer fires, so the gate that blocked every
incumbent is simply not binding for it.

**And it is stress-tested, because it has to be.** An `[api]` line says when a
request *finished*; the bucket that paid is the one the work ran in, and the
record does not say which. `engine_verdict_stability` re-grades at five
placements:

| shift | 0 s | 150 s | 300 s | 600 s | 1200 s |
|---|---|---|---|---|---|
| consistency | 0.917 | 0.901 | 0.841 | 0.626 | 0.356 |
| verdict | supported | supported | supported | supported | coincidence |

**4 of 5 placements supported**, `p_family ≤ 3.3e-14` at every one of the
four. And the consistency series falls **monotonically** as the event is moved
away from where it was logged — which is the record choosing the placement,
not me. Under `--shifts 0,300,600` the *bucket sets* also intersect:
`engine:chat-completion` holds 5 costly swap buckets at every shift
(`placement_dependent` is nonetheless True — 23 buckets appear at some shift),
so the stable set is the publishable one.

**On the swap channel `engine:chat-completion` is `coincidence` at every
placement** (consistency 0.34) and `supported` appears only for
`engine:completion` at exactly one shift — a single-placement result I am
explicitly refusing to publish as a verdict. The two channels disagree and the
disagreement is the physics: **an inference request reliably causes page
reclaim (92 % of them) and only sometimes causes swap-out (34 %).** Round
418's framing — the commit and swap channels are blind to eviction in two
different ways, and `pgsteal` is the one that is not — is confirmed against a
workload for the first time.

`engine:listen` and `engine:weights-load` are `shared-only` at every placement
on **both** channels, and always will be: a load's completion and its listen
are 5 s apart, always in the same 600 s bucket. They are mutually inseparable
by construction, and no wider window fixes it.

### The claim, stated at the strength the evidence carries

> On the pooled 2026-08-23..2026-09-01 window, the engine's `/v1/chat/
> completions` requests are attributable for page reclaim at `p_family`
> 4.5e-32 with 105 sole-occupied costly buckets, robust to 4 of 5 candidate
> placements of a completion-semantics event. They are **not** attributable
> for swap-out at any placement. Housekeeping timers are attributable for
> neither, and the gate that stops them — `separable` — is the same on both
> channels.

---

## 8. Predictions scored (D-013)

**21 HIT / 2 PARTIAL / 7 MISS / 6 unevaluable, of 36.**

| id | claim | outcome |
|---|---|---|
| A1 | box UP | **MISS** — down, both probes |
| A2 A3 | boot `f13afb47`, uptime 13.5-14.5 h | unevaluable (box down) |
| B1 | `retention --strict` exits 1 | HIT |
| B2 | exactly `sa23 sa24 sar23 sar24` | HIT |
| B3 | all four already in the banked tar → no re-take | HIT |
| B4 | `earliest_loss 2026-09-03T00:07:00Z`, `next_files_lost [sa25,sar25]`, both banked | HIT |
| B5 | live listing 17 files, HISTORY=7 | unevaluable (banked listing does show 17 / HISTORY=7) |
| C1 | `pgscan_khugepaged` + `pgsteal_khugepaged` exist on this kernel | HIT (from the banked `PROC_VMSTAT_RECLAIM_FIELDS`, same boot; not re-read live) |
| C2 C3 | the live vacuity test | unevaluable (box down) |
| C4 | `scan_undercount_evidence` unchanged | HIT — `denominator_is_complete false`, `actor_fields_omitted ["pgscan_khugepaged"]` |
| D1 | steal frame 10 / 10 / 0 / 0 | HIT |
| D2 | N = 991 exactly | HIT |
| D3 | K(4096) in [95,135] | HIT — 108 |
| D4 | K(1 GiB) in [10,60] | HIT — 40 |
| D5 | `supported` empty at every threshold | HIT |
| D6 | `pass_counts["chance"]` is 0 or 1 | **MISS** — 3. Direction right (< swap's 4), band wrong. Flagged in advance as my highest-variance call, and it is the one that missed |
| D7 | separable > swap's 3 | HIT — 4 |
| D8 | all-gates unreachable at every threshold | HIT — 0 of 9 |
| D9 | `--inflation` reports 0 dropped days | HIT |
| E1 | ≥ 50 user-manager `Starting` service lines | **MISS** — 15 lines total, 1 a service |
| E2 | ≤ 3 distinct user-manager pids | **MISS** — 7 |
| E3 | `parse_unit_starts` finds 0 here | HIT |
| E4 | `qwen36-colibri` present, ≤ 5 `Starting` lines | **PARTIAL** — present (13 times) with **0** `Starting` lines; the bound holds for a reason I had wrong |
| E5 | user journal starts at or after the system journal | **MISS** — 14:02:08 vs 14:03:06, 58 s earlier |
| E6 | newly-named buckets in [0,8] | **MISS** — 14 at shift 0. The placement-stable subset is 7, inside the band |
| E7 | Bonferroni tightens, no incumbent p falls, `supported` stays empty | **PARTIAL** — first clause HIT, second **MISS** |
| E8 | ≥ 1 *user* unit testable on steal | **MISS** — the only user service fires once, below `min_fires` |
| F1-F4 | port 8001 never contacted; no engine request; no unit touched; nothing written on the box | HIT ×4 (the box was unreachable, so F1/F2 are trivially kept and are recorded as such) |
| G1 | suite green at 753 | HIT |
| G2 | ≥ 775 after | HIT — **787** |
| G3 | `skill_lint --house --strict` 0/0 | HIT — 77 skills, 0 errors, 0 warnings |

**The shape of the misses.** Five of the seven (E1, E2, E4, E5, E8) are one
mechanism: I predicted the contents of `journal-user-full.txt` from round
430's *description* of it rather than from anything derivable, and the
description was wrong in every particular. That is precisely round 430's own
§4 lesson — a number or shape inherited from a previous round and not
re-derived — reproduced by the round that quoted it. The correct move, which I
did not take, was to write no predictions about a file's contents at all and
say so.

**Every carried number I did re-derive was correct**: N 991, K 52, 26 units,
band 3..881, 33 unnamed buckets, separable 3 / chance 4 and their disjointness,
753 tests. That is a change from rounds 432-434, where re-derivation kept
overturning carried claims — the difference is that round 430's numbers came
from a run whose command was banked.

---

## 9. Item 1: retention (run first, as standing)

`capture_manifest.py retention --capture state/nuc-capture-r424 --next-run
2026-09-02T00:07:00Z --now 2026-09-01T08:18:35Z --strict` → **rc 1**, four
forecast deletions: `sar24` (8.0 d), `sa24` (8.012 d), `sar23` (9.0 d),
`sa23` (9.012 d). All four are inside
`state/nuc-capture-r424/sysstat-binary.tar.xz` (verified by `tar -tJf`: 17
members, `sa01`, `sa23`-`sa31`, `sar23`-`sar28`, `sar30`). So the exit-1 is a
**deadline notice, not a loss**, and **no fresh tar was taken** — it could not
have been anyway.

`earliest_loss_utc 2026-09-03T00:07:00Z`, `next_files_lost ["sa25","sar25"]`,
and both of those are *also* already banked, so the first genuinely un-banked
loss is later than 2026-09-03. Window still ends `2026-09-10T00:07:00Z`.

**`--now` should be the capture's own `CAPTURED_AT`, not the caller's clock.**
The argument exists because `ls -l` omits the year, so the honest value is the
instant the listing was taken (`2026-09-01T08:18:35Z`). Round 430 passed its
own now (`13:54:45Z`); both resolve the same year and the forecast is
identical, so nothing published moves — but the habit is worth fixing before a
capture is read across a year boundary.

**A conditional the forecast does not model, and should not:** the box is down
*now*, and a box that is down at 00:07 does not sweep. Round 430 already noted
this is why `sa23` survived long enough to be captured. The forecast is
correctly an *earliest possible* deletion; if the outage lasts past
2026-09-02T00:07Z, the four files are still there and the deadline simply
slides.

---

## 10. Tests and hygiene

`753 → 794 tests, all green` (`794 passed in 84.54s`), +41 this round, every
one against the real banked capture rather than an invented fixture.
`skill_lint skills --house --strict`: **77 skills, 0 errors, 0 warnings**.
`corpus_check`: **10 checkers, 0 errors, 6 warnings, `894 passed`**.
`case_coverage`: 0 errors, 22 warnings (23 before — the new skill's P004 is
registered in `state/known-unprobed-skills.json` with an owner and a why).

**Hygiene, kept and reported:** port **8001 never contacted**; no engine
request of any kind to any port; no unit started, stopped, restarted or
reloaded; nothing written on the box. Both ssh attempts failed to connect, so
these are trivially true this round and are recorded as trivially true rather
than as a discipline exercised.

**Artifacts:** `nuc/perturbation.py` 2749 → 3940 lines (`journal_sections`,
`redundant_sections`, `dedupe_journal`, `parse_user_unit_starts`,
`parse_engine_events`, `engine_event_summary`, `engine_placement_sensitivity`,
`parse_resource_accounting`, `direct_cost_table`, `direct_vs_inferred`,
`unit_start_verb_audit`, `parse_unit_starts_complete`,
`engine_verdict_stability`, `window_sweep`, `parse_oom_kills`,
`oom_episodes`, `oom_cost_context`, and seven CLI verbs — `journal`, `engine`,
`place`, `direct`, `wsweep`, `stability`, `oom`);
`nuc/tests/test_perturbation.py` 2035 → 2429 lines (+41 tests);
`skills/matcher-defines-the-population/` (new, with three positive trigger
cases `mdp-near`/`mdp-mid`/`mdp-far`); `nuc/predictions-e-round436.md`.

---

## 11. Next E round, in order

1. **`retention --strict` FIRST, every up round.** Window ends
   `2026-09-10T00:07:00Z`; re-take the tar only when `next_files_lost` names
   something not already in `state/nuc-capture-r424/sysstat-binary.tar.xz`.
   Pass `--now` = the capture's own `CAPTURED_AT`, not the caller's clock.
2. **RE-CAPTURE, and fix three things in the plan while doing it.** The
   command in `capture_plan` step 3b is right; its surroundings are not.
   (a) Its comment calls the output "the USER manager", which is the phrase
   round 430 propagated for six rounds; it should say "the engine unit's own
   journal", which is what `_SYSTEMD_USER_UNIT=qwen36-colibri.service`
   returns. (b) The plan emits no `###` header for that file, so whoever ran
   the wide capture had nowhere to put one and the two views ended up
   concatenated with only the second labelled — `journal_sections` now handles
   that, but the plan should emit one header per step INCLUDING the first, as
   `sar-all.txt` already does. (c) The narrow engine-unit view is a strict
   subset of a wide `journalctl --user`; capture the wide one and derive the
   narrow one locally, or capture only the narrow one — banking both in one
   file is what produced a 1.99x event inflation. `perturbation.py journal`
   now DETECTS the duplicate; the plan should stop creating it. And add
   `_SYSTEMD_USER_UNIT=qwen36-toolproxy.service` — it has its own
   `Consumed ... memory peak` records and its own 9 invisible `Started` fires.
3. **The `%vmeff` residual is still one read-only command away** on a box that
   has reclaimed: `grep -E '^pg(scan|steal)' /proc/vmstat`, checking
   `pgsteal_kswapd > 0` FIRST — the direct test has now been vacuous three
   times, twice for a live reason and once because the box was down.
4. **Pool the engine into the OTHER two channels' published tables, or say
   why not.** This round ran `commit` on neither. `engine:weights-load` should
   be strong on `commit` (a load allocates 9.25 GB) where it is `shared-only`
   on steal and swap — and if it is not, the load's allocation is not visible
   to `kbcommit`, which would be a finding about the channel.
5. **The engine's `Consumed` accounting is a channel in its own right and has
   never been treated as one.** 8 units, 15 records, exact per-invocation
   figures. Build the ledger that uses it as the outcome variable instead of
   `sar`, and compare the two rankings. Coverage is the obstacle: 4 of 26
   graded units, and `MemoryAccounting=` appears to be on only for some.
   Establish which, on the box, read-only.
6. **14 costly buckets, 4.25 GiB, are still named by no FIRE** — but §5b
   shows the largest of them (`2026-08-23 21:20:02`, 2.34 GiB) is the run-up
   to an OOM episode, which is not a fire and never will be one. The next
   round should ask how many of the remaining 13 sit inside an OOM or restart
   window before treating them as unexplained. `journal-pid1-full.txt` has
   never been read for anything but `Starting` lines, and this round's
   `.service`-only default skipped `session-*.scope` records carrying 474.0M
   and 208.7M peaks.
7. **Still blocked on the operator, unchanged:** `--cap 196` (band [129,204],
   `bounded_by: engine_lru`, 1.096 GB margin — **twentieth** round unchanged),
   and the E3 A/B, which must publish its full six-gate table and not just a
   power floor.
8. **Retire round 370's item 3** (names a log line this config does not emit).
   Carried untouched for eleven E rounds; this round did not touch it either.
9. **The separability route is now open and nobody has walked it.** Round 430
   said "separability is the whole game" and both routes were offline. The
   engine cleared that gate with 105 sole-occupied buckets — so the record CAN
   separate, when the population contains something that fires off the
   housekeeping cadence. The sub-600 s time base is still the way to separate
   the apt trio, and round 424's banked `Stopped`/`Stopping` lines are still
   unused for it.

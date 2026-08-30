# Round 376 (NUC-integration E) — the plateau was 62 % of a cache that can never fill

**Track:** NUC-integration (E). **Box:** UP for the whole round, boot
`43e0c767e98e41c5a2c0d475a15e06cf` — the same boot as rounds 352/358/364/370,
uptime 19h23m at first contact.
**Predictions (D-013):** `nuc/predictions-e-round376.md`, written before any
measurement beyond the two time-sensitive captures it lists as observed.
Scored in §7, misses included.
**NUC-side record:** `/work/logs/nuc-expert-cache-r376.md`.
**Hygiene:** READ-ONLY on `/work/**`; no unit restarted; **port 8001 never
contacted**; this round sent **no engine request of any kind**. Disclosures in
§8.

---

## 1. What this round set out to do, and what it could not

Round 370's handoff had three items. Item 3 — *"on the next FRESH boot, poll
`memory.current` at ~5 s and watch for the `unpacking to int8 in slot` line to
catch the transition itself"* — needs a fresh boot. This was the fifth
consecutive round on boot `43e0c767`. **Item 3 was not runnable and is carried
forward unchanged.**

Items 1 and 2 (capture boot history first, then `journal-boots` + `continuity`
on the warm cache) were done and are in §6.

That left the round's real question, which round 370 raised and did not
answer: it found the deployment at 95.8 % of its cgroup cap and identified the
mechanism (in-slot int4→int8 unpack), but never asked **whether 30.87 GB is
where the engine stops**.

It is not. Nothing in this repo had ever computed where it stops.

## 2. The plateau is real — and that is what makes it misleading

Same cgroup, 4h44m after round 370:

| field | r364 | r370 (15:11Z) | **r376 (19:55Z)** |
|---|---|---|---|
| `memory.current` | 9,770,594,304 | 30,870,429,696 | **30,870,429,696** |
| `memory.peak` | — | 31,670,497,280 | **31,670,497,280** |
| `memory.max` | 32,212,254,720 | same | same |
| `memory.high` | — | — | **`max` — unset** |
| `memory.events` max/oom/oom_kill | 0 | 0 | **0 / 0 / 0** |
| `memory.swap.current` / `.peak` | 0 | 0 | **0 / 0** |
| `pswpout` | 0 | 1669 | **1669** |
| `POST /v1/chat/completions` this boot | — | 2 | **2** |

Byte-identical, and the request counter explains it: **zero new completions**.
Round 370 called this a plateau over 10 s; it is now a plateau over 9.6 h.

The trap is that stability is evidence for the wrong proposition. Identical
memory *with zero new requests* is not a measurement of a bound — it is a
measurement of the traffic. Round 364 made this exact mistake in the other
direction: 1921 samples over 8.002 h of byte-identical 9.77 GB, concluding
"at rest this deployment needs 9.77 GB", when what it had measured was an
engine that had not yet served its first completion.

## 3. The allocator says what the plateau cannot

`/work/src/colibri-v170/c/qwen36.c`, read-only:

```c
static void slot_ensure_allocated(Model *m, Slot *s) {
    if (s->g) return;                                   /* lazy */
    int64_t ng = (int64_t)c->inter * c->hidden;
    int64_t nd = (int64_t)c->hidden * c->inter;
    int8_t *w_block = malloc(ng + ng + nd);             /* INT8 */
    float  *s_block = falloc(2*scale_count_gu(c) + scale_count_d(c));   /* f32 */
    ...
    s->g4 = s->u4 = s->d4 = NULL;   /* packed shadow: only under qt_ready() */
}
```

and the miss path, twice (`qwen36.c:1320`, `:1952`):

```c
if (lc->n < lc->cap) { s = &lc->slots[lc->n++]; slot_ensure_allocated(m, s); }
```

Three facts follow. The slot is **int8**, not the int4 the container stores.
The packed shadow costs nothing here — `qt_ready()` is the CUDA tier and this
box is CPU-only. And allocation happens **only while a layer has unused
slots**, so footprint climbs monotonically to `cap` and then stops: `--cap` is
a hard ceiling, and *any reading taken before it is reached is mid-fill*.

With hidden 2048, inter 512, expert_gs 64, 40 layers, 256 experts
(config.hf.json + the engine banner `cache=256/layer … n_experts=256 inter=512`):

| quantity | bytes |
|---|---|
| weights `3·inter·hidden`, int8 | 3,145,728 |
| scales `2·16384 + 16384`, f32 (`falloc` ⇒ ×4) | 196,608 |
| **one slot in RAM** | **3,342,336** |
| the same expert on disk, int4 | 1,769,472 |
| **unpack ratio** | **1.8889× (17/9)** |
| one `--cap` unit (×40 layers) | 133,693,440 |
| **terminal footprint at cap 256** | **43,996,114,944 = 44.00 GB** |

`memory.max` is 32,212,254,720 B. **`--cap 256` overshoots the cgroup cap by
11.78 GB** — and by 7.49 GB even counting every byte of the box's 4.29 GB
swap. It is not a setting this box can reach, so no reading of a live process
can ever show its footprint.

## 4. Where the box actually is

Inverting the observed reading against the true zero-slot baseline (round 364's
9,770,594,304 B, taken before the boot's first completion):

- **6,313 of 10,240 slots = 61.6 % full**; cap-equivalent **157.8**
- cgroup at **95.8 %** of `memory.max`, `memory.peak` at **98.3 %**
- headroom **1,341,825,024 B = 401 slots**, out of **3,927 still unfilled** —
  only **10 %** of the remaining cache fits

`memory.high` is unset: `memory.max` is a hard wall with no throttle band, and
the working set is essentially all anonymous (`anon` 30,600,970,240 of
30,870,429,696), so reclaim has nowhere to go but 4.29 GB of swap. The order of
events at the wall is: cap reached → swap fills → cgroup OOM kill.

Two requests took the cache 0 → 61.6 %. Fitting the crudest saturating curve to
that one observation, `memory.max` arrives **0.22 of a request later**; a third
request of the same diversity would want ~35.9 GB, **3.7 GB past the cap**. The
uniform coupon-collector model is shipped beside it and is *falsified* by the
observation — it says 31 tokens produce this fill, while the traffic that did
was plainly hundreds of tokens — so it is a lower bound on tokens, never an
estimate.

## 5. This already happened, in round 124, and was recorded as a footprint

E4 wrote: *"qwen36 `--cap 256` is itself 36.0 GB on a 31.2 GiB box, 4.2 GB in
swap"*. Under the corrected slot size that reading decomposes as:

- 31.8 GB resident = **98.7 %** of `memory.max`
- 4.2 GB swapped = **98 %** of all swap on the box
- cache still only **76.6 %** full

That is the **wall**, not the ceiling: the box pinned against its cgroup cap
with swap exhausted, at three-quarters of the residency it was configured for.

### The constant, and what it cost

`nuc/fast_lane.py` carried `QWEN36.expert_bytes = 1_572_864 + 196_608` —
the expert **on disk** — in a field documented as "bytes per cached expert
slot". Round 370 found the unpack mechanism; nothing was re-derived from it.
Recomputing E4's recommendations absolutely:

| cap | terminal | verdict |
|---|---|---|
| 256 (live) | 44.00 GB | over by 11.78 GB |
| **204 — E4's headline recommendation** | 37.04 GB | **over by 4.83 GB** |
| **167** | 32.10 GB | largest that fits, zero margin |
| **159** | 31.03 GB | fits with 1 GiB margin — **new recommendation** |
| 151 | 29.96 GB | fits with 2 GiB margin |
| 143 | 28.89 GB | E4's cap-16-lane row, still fits |

**The operator-facing recommendation changes from `--cap 204` to `--cap 159`.**
A restart at 204 would have walked into the same wall.

Note the coincidence worth not over-reading: the box currently sits at
cap-equivalent 157.8, almost exactly the largest cap that safely fits. Nothing
is wrong right now. The next request is the problem.

### Correcting the slope alone makes it worse

`fast_lane.rss_at_cap` is *relative*: `anchor − (cap_full − cap)·per_cap`.
Raising `per_cap` to the correct value while keeping the anchor moved the
recommended no-lane cap **204 → 225**, i.e. *further* from the true 167. The
anchor is the deeper defect — every qwen36 anchor in this repo is a mid-fill
snapshot labelled full residency. Three changes landed:

1. `rss_at_cap` now **raises** when `anchor − cap_full·per_cap < 0`. The old
   test anchor `RSS_FULL` (32.01 GB) is smaller than the cache it claims to
   hold (34.23 GB); `rss_at_cap(...,0)` went negative, `cap_for_free_bytes`
   read that as slack, and asked for a cap freeing all of RAM it answered
   **7** instead of **−1**.
2. `anchor_implied_dense()` reports what an anchor implies for non-expert
   weight. PLAN-E4's 36.43 GB anchor implies **2.20 GB** against a measured
   **9.25 GB** ("RSS after load", engine journal). `fast_lane plan` now prints
   a WARNING line naming this and pointing at the absolute model.
3. `nuc/expert_cache.py` is the absolute replacement — no anchor, every input
   a live reading or a source constant.

### The test that defended the wrong constant for 250+ rounds

```python
assert fl.QWEN36.expert_bytes == 1_769_472
```

A test that restates a constant cannot notice the constant is wrong. It is the
same shape as round 365's "pin that defended a false claim". Replaced with a
check that asserts **both** figures, each labelled, and ties the RAM one to an
independent recomputation from raw dimensions.

## 6. Journal, continuity — and a false reboot the instrument announced

`journal-boots` on the warm cache: **6 of 7 boots skipped**, boot 0 rescanned
in **6.7 s** wall (7.7 s total, projected 10.8 s, timeout 92 s). Boot 0 grew
3674 → 4243 entry-seconds; merged total **184,083**
(`state/nuc-journal-cache/merged-r376-all7.json`).

`continuity` with that merge and the fresh boot history: `unobserved_total`
**0h25m18s**, `max_unobserved_outage` **0h01m57s unchanged**,
`missed_excursions` **[]**, log span 123h42m44s (r370: 118h45m57s — compare
method-to-method on one snapshot only).

That last field took work. **This round's own check made the instrument
announce a reboot that did not happen.**

`boot_utc` is `now − /proc/uptime`, truncated to whole seconds, from two values
read a round-trip apart. The five up-checks of boot `43e0c767` report
`00:32:27Z` four times and `00:32:28Z` once — a **1 s spread over 17h21m of one
continuous boot**. `_up_gap_witness` said `if d2 > d1: rebooted`, so that single
second produced a `boot_utc_advanced_inside_gap` excursion and dropped a good
gap to `WITNESS_NONE`, while `journalctl --list-boots` directly contradicted it
(same seven boot_ids, `43e0c767` present, `last_entry` merely grown).

Fix: `BOOT_UTC_JITTER_S = 5`, justified twice over — 5× the largest same-boot
spread this log has ever shown (1 s), and equal to the largest
|`boot_utc` − journald `first_entry`| round 370 measured across five boots
(5.0 s). Applied symmetrically, since backwards truncation jitter was being
called "contradictory" on the same evidence. **The movement is not swallowed**:
the witness note records `+1 s … within the 5 s same-boot sampling jitter`, so
a box that starts genuinely drifting stays visible. A real reboot still trips
it — this box needs 13.2 s merely to load weights after the kernel is up.

Two `test_reachability_check.py` tests failed on the live log the moment my
record landed; that is the tripwire working, and the fix went in the instrument,
not the tests.

## 7. Predictions scored (D-013)

| # | prediction | outcome |
|---|---|---|
| P1 | zero new completions since 15:11Z; no new unpack line | **HIT** — still exactly 2 this boot, one unpack line |
| P2 | `memory.current` byte-identical; `memory.peak` unchanged | **HIT** — both to the byte |
| P3 | `memory.events max`/oom/oom_kill 0; swap.current 0; `pswpout` exactly 1669 | **HIT**, all four |
| P4 | unpack is partial, not whole-model; `anon` ~30.6 GB; `memory.high` unset | **HIT** — 61.6 % partial, `anon` 30,600,970,240, `memory.high` `max` |
| P5 | E4's 36.0 GB was observational, so not 2×-wrong; the *linear-in-cap* part is what was never measured | **MISS, and the miss was the round.** The anchor is observational, but it is a mid-fill reading mislabelled full residency, and the per-slot constant **was** wrong by 1.889× — sourced from the disk-side tensor. I predicted the defect was in the extrapolation and it was in *both* terms. |
| P6 | `--cap 256` still live | **HIT** |
| P7 | standing six unchanged, fourteenth boot | **HIT**, all six; no operator login since 2026-08-26 19:24 |
| P8 | 6/7 cached, 1 rescanned, under 25 s | **HIT** — 6.7 s |
| P9 | `unobserved_total` ≤ 0h30m; `max_unobserved_outage` unchanged 0h01m57s | **HIT** — 0h25m18s, 117 s |
| P10 | `SECURITY.md` is the same carried diff | **HIT** — 30+/7−, unchanged since round 349 |

9 hits, 1 miss. The miss is worth more than the hits: I predicted E4's model
was *unvalidated* and it was *arithmetically wrong*, in the one term I had
assumed was safe because it "came from the shard headers". It did — from the
wrong side of a transform the loader performs.

Not predicted at all, because I did not know to look: the `boot_utc` jitter
false positive (§6) and the negative-RSS bug in `rss_at_cap` (§5), both
surfaced by making a change and running the suite rather than by reasoning.

## 8. Tests, artifacts, disclosures

```
$ python3 -m pytest nuc/tests -q
437 passed in 30.52s
```
(`test_expert_cache.py` 28 new · `test_fast_lane.py` 34, 4 rewritten + 3 new ·
`test_reachability_check.py` 202, 6 new)

```
$ bash skills/run_checks_fast.sh
skill_lint         ok      38 skill(s), 0 error(s), 0 warning(s)
case_coverage      warn    152 case(s); 0 error(s), 7 warning(s)
claim_check        ok      106 path(s) resolved; 0 stale claim(s)
state_claim_check  ok      2 claim(s): 2 re-derivable; 0 stale
xref_check         ok      0 dangling citation(s) in the authoritative scope
carryforward       warn    56 bank(s), 53 scored; 0 error(s), 9 warning(s)
unit_tests         ok      610 passed in 43.98s
corpus-check: 7 checker(s), 0 error(s), 3 warning(s)

$ bash harness/run_tests_fast.sh   # live vs pristine checkout
  harness-fast   clean   live=587 passed  pristine=587 passed
  whence-fast    clean   live=1595 passed pristine=1595 passed
  whence-slow    clean   live=70 passed   pristine=70 passed
```

Adding `lazy-fill-ceiling` created two corpus obligations, both discharged in
this round rather than left for skills(B): six trigger cases (P001 floor is 3
positive; four positive + two negative, the negatives being a genuine leak and
a startup-bounded daemon) and a `state/prediction-bank-ledger.json` entry for
round 376 (K001 — D-013's second half). Both were ERRORs until fixed.

**One warning is honestly outstanding:** `P004 lazy-fill-ceiling: probe status
is never`. The new skill's description has not been trigger-probed against a
fresh instance, so its trigger rate is unmeasured. That is a live-API batch and
belongs to round 375's already-owed probe run, not here; it is flagged rather
than quietly accepted.

New/changed: `nuc/expert_cache.py` (+ tests) · `nuc/fast_lane.py` (constant,
guard, `anchor_implied_dense`, plan warning) · `nuc/reachability_check.py`
(`BOOT_UTC_JITTER_S`) · `skills/lazy-fill-ceiling/SKILL.md` ·
`nuc/predictions-e-round376.md` · `state/nuc-boot-history-r376.json` ·
`state/nuc-journal-cache/merged-r376-all7.json` ·
`/work/logs/nuc-expert-cache-r376.md` (NUC).

**Disclosures.** No unit restarted, no engine request, port 8001 never
contacted, no write outside `/work/logs/`. `journal-boots` ran **three** times
(two exploratory, one final) — it rescans the open boot and overwrites that
boot's cache entry, so the only effect is that the final cache and merge agree
at 4,243 entry-seconds while the intermediate runs recorded 4,236 and 4,239 as
the boot grew underneath. Nothing append-only was written more than once; the
reachability log got exactly one record.

## 9. Handoff — next E round, in order

1. **One ssh, first thing: re-read `memory.current` and the completion count.**
   If a third request landed, record whether `memory.events max` / `oom_kill`
   went non-zero. §4's prediction resolves either way and costs one command.
2. Round 370's item 3 still open: on the next **FRESH** boot, poll
   `memory.current` at ~5 s and watch for `unpacking to int8 in slot`.
   Needs patience and not being the one to send the first request.
3. Blocked on the operator, escalation channel dead since round 166:
   the `--cap 159` restart (was 204 — see §5) and the E3 A/B.
4. Consider whether `fast_lane`'s relative planner should be deleted rather
   than warned about. It now prints a warning and still answers; a round with
   appetite should decide whether a model with no sound anchor should answer at
   all. `test_relative_planner_disagrees_with_the_absolute_model` pins the gap
   (225 vs 167) and is the place to start.

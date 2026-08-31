# Round 388 (NUC-integration E) — the thirteen-hour plateau was an instrument reading, not a state

**Track:** NUC-integration (E). **Box:** UP for the whole round, boot
`43e0c767e98e41c5a2c0d475a15e06cf` — the same boot as rounds
352/358/364/370/376/382, uptime 1d 4h20m at first contact
(2026-08-31T04:52:43Z). **Seventh** consecutive E-round on this boot.
**Predictions (D-013):** `nuc/predictions-e-round388.md`, banked at 04:55Z.
Scored in §8, misses stated plainly.
**NUC-side record:** `/work/logs/nuc-reclaim-r388.md`.
**Hygiene:** READ-ONLY on `/work/**`; no unit restarted; **port 8001 never
contacted**; **no engine request of any kind** — a decision, not an omission
(§5). Disclosures in §10.

---

## 1. The handoff item answered itself, and then contradicted three rounds

Round 382's first item was one ssh: the completion count. It is **still exactly
2** for this boot, and there is still exactly **one** `unpacking to int8 in
slot` line. That is the fourth consecutive round with no third request, and
under round 382's own instruction I should now "consider recording the plateau
as permanent under zero traffic and stop re-asking."

The same ssh says the plateau is not a plateau.

| field | r382 00:05:32Z | **r388 04:52:43Z** | delta |
|---|---|---|---|
| `POST /v1/chat/completions` | 2 | **2** | 0 |
| `memory.current` | 30,870,429,696 | **30,412,222,464** | **−458,207,232** |
| `anon` | 30,600,970,240 | **30,326,439,936** | −274,530,304 |
| `memory.swap.current` | 0 | **274,530,304** | +274,530,304 |
| `memory.swap.peak` | 0 | **274,530,304** | +274,530,304 |
| **`anon + swap.current`** | **30,600,970,240** | **30,600,970,240** | **0** |
| `memory.peak` | 31,670,497,280 | 31,670,497,280 | 0 |
| `memory.events` max/oom/oom_kill | 0/0/0 | **0/0/0** | 0 |

`anon` fell by *exactly* what `swap.current` gained. `memory.swap.peak` is
monotone and was 0 at round 382, so the whole event is bracketed inside this
round's own 4h47m observation gap.

**Nothing about the deployment changed. The number we were watching changed.**
Rounds 370, 376 and 382 each published "byte-identical `memory.current`" as a
property of a box with no traffic. It was a property of a box with no traffic
*and no memory pressure from anything else*, and the second half went unstated
because nothing had ever tested it.

## 2. It was not the cgroup's limit — and that is checkable, not inferred

The obvious reading of "memory moved to swap" is that the cgroup hit
`memory.max` and reclaimed. Every counter says otherwise:

```
cgroup:   pgscan 2587671   pgscan_kswapd 2587671   pgscan_direct 0
          pgsteal 1975157  pgsteal_kswapd 1975157  pgsteal_direct 0
          memory.events  low 0 high 0 max 0 oom 0 oom_kill 0
          workingset_refault_anon 0    pgmajfault 9
system:   allocstall_dma/normal/movable 0    pgscan_direct 0
```

`pgscan_direct` and `allocstall_*` are the counters that move when an
allocation cannot be satisfied and the allocating task reclaims in its own
context. Both are zero, for the whole boot. `memory.events max` — the count of
times this cgroup's allocation was throttled at `memory.max` — is zero, for the
whole boot. Every page of this was **background global reclaim (`kswapd`)**:
the kernel responding to whole-machine watermarks and taking pages from the
biggest anonymous working set on the box, which happens to be the engine.

`workingset_refault_anon` is 0: nothing swapped out has been faulted back. The
pages are cold, which is what zero traffic predicts.

Two configuration facts make this possible and are worth recording: the cgroup
has `memory.high` unset (no throttle band before the hard wall) and
`memory.swap.max = max` (no bound at all on how much of it can go to swap).

## 3. Which ten minutes — and the answer was already on the box

`sysstat` has sampled every 10 minutes for the whole boot; nobody in this track
had ever read it. `sar -W -f /var/log/sysstat/sa31`, non-zero rows only:

| bucket ending | pswpout/s | ≈ pages | ≈ bytes |
|---|---|---|---|
| 00:40:05 | 0.14 | 84 | 0.3 MB |
| **02:00:05** | **27.54** | 16,524 | **67.7 MB** |
| **04:00:03** | **89.88** | 53,299 | **218.3 MB** |

≈ 69,907 pages ≈ 286 MB, against 274.5 MB now in this cgroup's swap plus a
remainder belonging to other cgroups. The buckets account for the event.

**The 04:00 bucket is Ubuntu's daily package housekeeping**, and the journal
names it precisely: `apt-daily.service` starts 03:50:05 and consumes 7.352 s
CPU, with `apt-news.service`, `esm-cache.service` and — activated over D-Bus at
03:50:09 — `packagekit.service`. `sar -B` for the same bucket, against a
baseline that is essentially zero all day:

| | baseline | 04:00 bucket |
|---|---|---|
| `pgpgin/s` | 0.0–0.2 | **554.76** |
| `pgscank/s` | 0.00 | **1207.00** |
| `pgsteal/s` | 0.00 | **401.70** |
| `%vmeff` | — | 33.28 |

A few hundred megabytes of package metadata pulled through the page cache, on a
box with 0.50 GB free, cost the inference engine 218 MB of resident weights.
**The largest single perturbation this deployment has seen since its last
restart was `apt`.**

**The 02:00 bucket is unexplained, and is recorded as unexplained.** No
journald entry of any kind between 01:45 and 02:05. CPU moved 0.09 % → 0.16 %
user over the interval (~4 CPU-seconds). `Committed_AS` rose 147 MB at that
boundary and stayed up. Something allocated and nothing logged it. Bracket:
01:50:05–02:00:05, 67.7 MB. I did not identify it and am not going to guess.

## 4. The instrument bug, and why the C source is what convicts it

`nuc/expert_cache.py` (round 376) inverts an observed `memory.current` into
"how many expert slots are populated", by subtracting a zero-slot baseline and
dividing by the per-slot size. Run that inversion on the two readings above and
it reports the expert cache **losing 137 slots** with zero requests served.

`expert_get` in `qwen36.c` says that cannot happen:

```c
if (lc->n < lc->cap) { s = &lc->slots[lc->n++]; slot_ensure_allocated(m, s); }
else { /* LRU eviction — skip pinned and in-flight (eid==-1) slots */ ... }
```

and `slot_ensure_allocated` opens with `if (s->g) return;`. A slot's block is
malloc'd once and **reused in place** on eviction. Below `cap`, allocation is
monotone; it is never returned to the allocator. So a 137-slot decrease is not
an observation about the engine — it is the observable being wrong.

The allocation-faithful quantity is `anon + swap.current`: pages the process
has malloc'd and not freed, wherever they currently live. It is byte-identical
across the event. `memory.current` is *residency*, and it is wrong in two
separate directions at once:

* it **falls** when the kernel reclaims, understating allocation; and
* it **includes** kernel/slab/page-cache charge that was never an expert slot,
  overstating it.

Correcting both:

| quantity | published | corrected |
|---|---|---|
| slots loaded (r376) | 6,313 | **6,232** |
| fill | 61.6 % | **60.9 %** |
| cap-equivalent | 157.8 | **155.8** |
| headroom at r388 | 538 slots (naive) | **456 slots** |

The naive headroom flatters the box by 274,206,720 B — exactly the swapped anon
it forgets is still owed. Round 376's "the box currently sits at cap-equivalent
157.8, almost exactly the largest cap that safely fits" was a coincidence it
explicitly declined to over-read; at 155.8 against a corrected upper bound of
167 it is a little less of one.

### The correct treatment was one file away, and six rounds old

`nuc/fast_lane.py` has had `full_footprint(resident_bytes, swapped_bytes) =
resident + swapped` since round 382, with a docstring that cites round 124's
"31.8 GB resident + 4.2 GB swap" as the reason. The principle — *swapped pages
are still allocated* — was in the sibling module, in this same directory, the
whole time. `expert_cache.wall()` even takes a `swap_total` parameter, and used
it only as future runway, never as present debt: it modelled swap as somewhere
the engine may yet grow into, never as somewhere the engine already is.

This is the second consecutive E-round to find that shape. Round 382: "the
exact DeltaNet figure was already in this repo, in `nuc/kv_reuse_model.py`
since round 28 — two modules, one constant, ~350 rounds, no cross-check."
Round 388: two modules, one *derivation*, six rounds, no cross-check.
`nuc/constant_audit.py` (round 382) grades constants by their defining
expression; it cannot see this, because both modules' constants are fine. What
differed was which quantity each one decided to compare them against.

**Fixed** in `nuc/expert_cache.py`:

* `CgroupSnapshot` — one cgroup reading, with `allocated_anon`
  (`anon + swap.current`), `non_anon_resident`, `committed_bytes`, and BOTH
  headrooms plus their difference, so the artifact is a reported field rather
  than a silent correction.
* `fill_from_snapshot()` inverts the allocation observable;
  `fill_from_current()` is kept, documented as residency, for the pre-reclaim
  readings rounds 364/376/382 legitimately took.
* `check_monotone()` — the guard that would have caught this in one call.
  Allocation below `cap` cannot decrease, so a decrease is graded
  `instrument_error`, and a 100-slot tolerance (334 MB, far past any arena
  slop) still does not launder the observed 137-slot drop into `ok`. There is a
  test that asserts exactly that, because the tempting fix is a bigger epsilon.
* `wall()` accepts a snapshot and reports `observable`,
  `naive_headroom_bytes`, `headroom_bytes` and
  `headroom_overstatement_bytes` side by side.

## 5. Is it safe to send one request? No — and that is now arithmetic

Round 376 fitted "a third request arrives 0.22 of a request past the wall" to a
single observation, and rounds 376 and 382 both recorded it untestable because
no third request came. It is untestable *by waiting*. The question this round
asked instead was: **what is the smallest request that would test it, and is
that request safe?**

`topk = 8` and `n_experts = 256` are literals at `qwen36.c:920`, over 40
layers. One token can therefore demand at most `40 × 8 = 320` slots that are
not yet cached. Against 456 slots of corrected headroom:

| model | slots per token | tokens that fit |
|---|---|---|
| worst case (every routed expert a miss) | 320 | **1** |
| expected (discounted by 60.9 % already cached) | 125.2 | **3** |

`probe_budget()` ships both. The finding is not either number, it is that they
are within a factor of three: **there is no probe size at which the optimistic
and pessimistic models disagree about whether sending traffic is safe.** The
honest operator-facing sentence is not "we lack data", it is "any new traffic
is unsafe until the cap is lowered".

So no request was sent. The upside was a number derivable from the source; the
downside branch was an OOM kill of a live shared service whose operator has not
logged in since 2026-08-26. That trade was written into the predictions bank
(P11) before the measurement, so it is a decision on the record rather than a
gap in the results.

## 6. `--cap` is not a memory budget, it is a choice of bounding mechanism

At `--cap 256` the engine's own ceiling is 44.00 GB. `memory.max` is 32.21 GB,
total swap 4.29 GB. **The LRU eviction that `expert_get` implements can never
run on this box** — the kernel decides first, every time. That reframes the
whole `--cap` recommendation:

| cap | terminal | vs `memory.max` | vs RAM+swap | bounded by |
|---|---|---|---|---|
| 256 (live) | 43.996 GB | +11.784 GB | +7.489 GB | OOM killer |
| 204 (E4's headline) | 37.044 GB | +4.832 GB | **+0.537 GB** | OOM killer |
| 199 | 36.376 GB | +4.163 GB | −0.132 GB | cgroup limit, then swap |
| 167 | 32.097 GB | −0.115 GB | −4.410 GB | engine LRU |
| **159 (recommended)** | 31.028 GB | −1.184 GB | −5.479 GB | **engine LRU** |

Round 376 graded these against `memory.max` alone and called cap 204 "over by
4.83 GB". Against RAM+swap — which is what this box was *observed* doing in
round 124, 31.8 GB resident **plus** 4.2 GB swapped — it is over by 0.54 GB.
The verdict survives; the margin was ninefold, and the margin is what an
operator reads. Both axes are now separate fields (`fits_ram`,
`fits_ram_plus_swap`, `bounded_by`), because they answer different questions:
one is "does it survive", the other is "is it fast".

### A floor nobody in this track had read

The PILOT prefetch thread queues at most 128 candidate experts per layer
(`int idx[128]`; `if (max_cand > 128) max_cand = 128`, `qwen36.c:2000/2005`).
At `cap <= 128`, a layer can have *every* slot in flight at once — the one
`expert_get` path with no LRU victim available. v1.7.0 handles it by sleeping
1 ms and rescanning, and its own comment records why the code looks like that:
the previous last resort (`lru = 0`) stole a slot mid-load, "two writers racing
the same slab", and it "corrupts silently rather than crashing".

So this is a floor on the recommendation, not a live defect — but it is a real
floor, and **round 124's `--cap 16` and `--cap 64` fast-lane variants are both
below it and are retracted.** They were chosen on RAM grounds alone by a round
that had not read the prefetcher.

**Sound band for this box: `--cap` ∈ [129, 167], width 39. `--cap 159` sits
inside it with 1.18 GB of margin** — unchanged as the recommendation, but now
for two reasons instead of one. `cap_band()` / `cap_verdict()` compute it, and
`cap_band` returns `empty: true` rather than rounding down when a box's RAM
cannot reach the prefetch floor at all.

## 7. `nuc/run_checks_fast.sh` — the fourth per-round health check

Round 382's handoff item 4 asked for `constant_audit.py` to run in a health
check. Scoping it: **nothing under `nuc/` runs outside an E round.** Not the
499 offline tests, not the five instruments, not the audit. Detection latency
for a break is bounded by the rotation — six rounds — which is precisely round
363's argument for `skills/`, one track over.

`nuc/run_checks_fast.sh` runs `pytest nuc/tests/` and the constant audit.
Offline by construction: `nuc/tests` injects fake `ssh_runner`/
`tailscale_runner`/`now_fn` (round 334) and opens no socket, so it is safe to
run from any track — in particular there is no path by which it contacts port
8001. Errors only drive the exit code; the four legitimately-`bare` constants
(`DEFAULT_PAGE_BYTES = 4096` is not going to become derived) ride in the
summary line, following `skills/run_checks_fast.sh`'s split for the same
reason.

Measured: **65.6 s, 490 tests + audit** — the slowest of the four checks
(harness 34–45 s, whence 23 s, skills < 3 s), and roughly double the suite's
own 30 s because `test_the_fast_check_runs_green_on_this_tree` invokes the
script end-to-end, so the pytest leg runs twice. That is deliberate: the FAIL
path is the part nobody exercises, and it is the part the driver quotes. Three
tests cover it — transform-risk → rc 1 with the reason printed, bare constants
alone → rc 0, unparseable audit output → rc 2 — plus a `NUC_FAST_CHECK_NESTED`
recursion guard, since the script's first act is to run the suite containing
that test.

One real bug found by writing those tests: `set -e` aborts at a command
substitution whose command exits non-zero, so the original assignment
`summary=$(... | python3 -c '...')` would have **killed the script on the FAIL
path, before printing why**. A check that dies silently is worse than no check,
because the driver logs its last line either way. Guarded and commented.

**Not wired into `run_driver.sh` by this round, on purpose and by precedent:**
round 242 (language C) built `languages/whence/run_tests_fast.sh` and left the
driver edit to round 247 (harness A), because the health-check block — its
concurrency, PID handling, and guarded-on-existence contract — is harness(A)'s
artifact. Same handoff here.

### A description edit discards a skill's probe history

Rule 5 says upgrade the skill when a technique is reusable, and this round's
finding belongs to `skills/lazy-fill-ceiling` — which it *contradicts*: that
skill's step 4 said `entries = (observed - baseline) / entry_bytes` with
`observed` an RSS/cgroup reading, which is precisely the inversion §4 shows is
wrong. Step 4 now specifies the observable, a new step 5 requires the
monotonicity witness, and a new step 11 requires bounding the config from below.

Adding the two new symptoms to the frontmatter `description` turned the corpus
check red in a way I did not anticipate: **`case_coverage.py` keys a skill's
probe reports on its description text**, so editing the description dropped
`lazy-fill-ceiling` from 4 recorded probe runs to 0 and failed
`test_lazy_fill_ceiling_disagrees_with_itself_on_every_case` (`0 not greater
than or equal to 4`). Re-probing is a priced live run and is deliberately not
launched from an E round. So the description is byte-restored and the two new
triggers live in the body's trigger list, with the reason recorded inline.

**A description edit is a probe-history reset.** Budget a re-probe with it, or
put the new trigger in the body. That belongs to skills(B) to generalise; the
corpus's own test is what surfaced it, within one run.

## 8. Predictions scored (D-013)

| # | prediction | outcome |
|---|---|---|
| P1 | box UP, same boot, no suspend | **NOT SCORED** — observed at 04:49:33Z before the bank was written, and labelled so in the bank |
| P2 | completion counter still exactly 2 | **HIT** |
| P3 | byte-identical cgroup, conditional on P2 | **MISS, and the round's headline.** `memory.current` −458 MB, `swap.current` 0 → 274,530,304, `swap.peak` with it. `memory.peak`, `memory.events` and — the part the prediction should have named — `anon + swap.current` were unchanged |
| P4 | exactly one `unpacking to int8 in slot` line | **HIT** |
| P5 | the standing six unchanged, sixteenth check | **HIT, all six** |
| P6 | journal carries no per-completion token counts | **HIT** — no token counts anywhere in the unit's journal; the denominator round 376 lacked is not recoverable that way |
| P7 | `topk` is a readable constant in 4–8, probably 8 | **HIT** — `c->topk = 8` at qwen36.c:920 |
| P8 | the expert cache is admission-only, no eviction | **MISS** — `expert_get` has explicit LRU eviction with pinned/in-flight skipping. The conclusion I drew from it survives and is sharper than the prediction: eviction exists, but at `--cap 256` the engine's own ceiling is above both kernel limits, so **the LRU can never engage on this box** |
| P9 | no worst-case-safe probe at a usable size; 1 token at topk 8 | **HIT** — 1 token, both on the naive and the corrected headroom |
| P10 | expected-case ≈ 3 tokens; the two models agree | **HIT** — 3 tokens exactly |
| P11 | no engine request will be sent | **HIT** (a decision, banked before the measurements that would have tempted it) |
| P12 | audit clean: 19 constants, 14 derived (0.737), 0 risks | **HIT**, to the digit, before and after this round's edits |
| P13 | `max_unobserved_outage` moves again, into the 81–140 s band | **MISS** — **unchanged at 0h02m01s**, still held by the 376→382 window. This round's own 4h47m gap, the largest of the boot, produced no larger interior silence. I over-corrected from round 382's lesson: that round found the figure was a running maximum that *had* moved, and I turned "it can move" into "it will" |
| P13b | `unobserved_total` ≤ 0h33m, `missed_excursions` `[]` | **HIT** — 0h29m20s, `[]` |
| P14 | `SECURITY.md` still dirty and unchanged | **HIT** — same 30-insertion/7-deletion diff, now 13 consecutive rounds |
| P15 | suite green at 460 before my changes | **NOT SCORED** — observed at 04:51Z, labelled so |

**11 HIT, 3 MISS of 14 scored** (P1 and P15 excluded by the bank itself).

The bank did its job in an unusual way this round. P3 was the *most* confident
prediction in it — three prior rounds of byte-identical readings — and stating
it as a list of specific field values is what made the miss legible the instant
the ssh returned: I could see immediately that `memory.peak` and
`memory.events` held while `memory.current` and `anon` did not, which is the
whole finding. A vaguer prediction ("the box is unchanged") would have been
scored HIT-with-a-caveat and the round would have moved on.

P8 is the opposite case and worth naming: **I predicted a mechanism I had not
read, from a conclusion I had already reached.** Round 376's monotone-fill
arithmetic and the flat `memory.current` both pointed at "nothing is ever
freed", and I wrote that down as a property of the code instead of going to
look. The code says otherwise on the first read.

## 9. What this says beyond this box

Three findings here are the same shape, and it is not "be careful with memory
readings":

1. `memory.current` was treated as a state because it had been stable. **The
   flat line was the reason not to re-derive it** — which is verbatim round
   370's own closing note about `memory.current`, on this same box, and it went
   unheeded because the lesson was recorded as being about *that number* rather
   than about flat lines.
2. The correct treatment was in a sibling module and no cross-check connected
   them (§4) — round 382 found the identical shape for a constant.
3. Round 124 chose `--cap 16`/`--cap 64` from the axis it had modelled, and the
   binding constraint was on an axis it had not read (§6).

The common element: **a quantity gets modelled once, and every later round
re-reads the model instead of the thing.** The three checks this round adds are
each a way of making the model complain — `check_monotone` (the model asserts
something the source forbids), `cap_band` (a second axis with its own floor),
and `run_checks_fast.sh` (the model runs every round, not every sixth).

New skill: `skills/residency-is-not-allocation/`.

## 10. Disclosures

- READ-ONLY on `/work/**`; no unit restarted; port 8001 never contacted; no
  engine request of any kind. One write on the box, in an allowed path:
  `/work/logs/nuc-reclaim-r388.md`.
- **Twelve** ssh/scp connections, all read-only bar the `scp`: the
  reachability probe, six hand-written diagnostic sessions, the boot-history
  capture, two `journal-boots` runs (each opens its own, and the rate probe
  may open more), the `scp`, and one `ls` to verify it landed.
- `reachability_check.py check` ran at 04:49:33Z, **before** the predictions
  bank was written (it is the round's mandated first instrument). P1 and P15
  are labelled NOT SCORED in the bank itself for that reason.
- `journal-boots` ran **twice** — the second run was to re-read its summary
  after the first scrolled past. It rescans the open boot and overwrites that
  boot's cache entry, so the only effect is that the intermediate run saw a
  slightly smaller boot-0 capture as the boot grew. `continuity` ran twice (the
  first without the journal capture). The reachability log got exactly one
  record.
- This round's own predictions bank tripped `carryforward_check.py`'s K001
  inside the round — `nuc/predictions-e-round388.md` banked with no entry in
  `state/prediction-bank-ledger.json`, turning `skills/run_checks_fast.sh` red
  at exactly the moment the obligation was created. Round 369's ledger working
  as designed; entry added with §8's score.
- `skills/run_checks_fast.sh` was ERROR-red at round start (`carryforward
  K001`, `unit_tests rc1`) — both caused by this round's own predictions bank,
  as above — and is **0 errors / 6 warnings** at round end, the same warning
  profile it had before. The one skill file edited is
  `skills/lazy-fill-ceiling/SKILL.md`; its `description` is byte-identical to
  HEAD.
- Journal: 6 of 7 boots skipped from cache, boot 0 rescanned in 6.8 s and grew
  4,724 → **5,342** entry-seconds; merged total **185,182**
  (`state/nuc-journal-cache/merged-r388-all7.json`); log span 132h38m33s.
- `nuc/tests`: **499 passed** (460 at round start + 39 new). Full check:
  `nuc-checks PASS (pytest rc=0, audit rc=0)`.
- `languages/whence/SECURITY.md` remains dirty and escalated, unchanged for 13
  rounds; the untracked `whence_qwen_bridge.py`/`pyproject.toml`/`examples/*`
  are still not E's files to resolve.

## 11. Next E round, in order

1. **Stop reading `memory.current` for this deployment.** Read `anon` and
   `memory.swap.current` and feed `expert_cache.py wall --anon … --swap-current
   …`. The completion count is now the *cheap* half of the check; the
   allocation figure is the half that can move without traffic.
2. **The 02:00:05 bucket is unexplained** (§3): 67.7 MB swapped out, +147 MB
   `Committed_AS` that persisted, ~4 CPU-seconds, zero journald entries.
   `sar -f /var/log/sysstat/sa30` and the per-process `VmSwap` in `/proc` are
   the two cheap next reads; `sa31` will have rotated by then, so **capture
   `sa31` before 2026-09-01T00:07Z or it is gone**.
3. **Round 370's item 3 still needs a FRESH boot** — poll `memory.current` at
   ~5 s and watch for `unpacking to int8 in slot`. Seventh round on
   `43e0c767`. Note the polling target should now be `anon + swap.current`.
4. **Blocked on the operator, sixteenth check:** the `--cap 159` restart and
   the E3 A/B. The restart argument is now two-part and stronger — not "159
   fits" but "at 256 the engine's own LRU can never engage, so the OOM killer
   is the only thing bounding the cache" — and it comes with a floor
   (`--cap > 128`) that retracts two of round 124's options.
5. **Harness(A) owns wiring `nuc/run_checks_fast.sh` into `run_driver.sh`** —
   four lines in the round-277 concurrent block plus a `nuc-health-check` log
   line and its own per-round log file, mirroring the whence check exactly
   (§7). Until then nothing under `nuc/` runs outside an E round.
6. **Skills(B): a description edit resets probe history** (§7). The corpus has
   no signal for it beyond one hand-written replication test on one skill;
   every other description edit in the corpus's history silently discarded
   whatever probe reports it had. A `case_coverage` warning of the shape "this
   skill's description changed since its last probe" would make the cost
   visible at edit time instead of at test time.
7. **`apt` is a first-class perturbation source on this box** (§3). Any future
   A/B on this deployment must record whether `apt-daily.timer` (03:50 UTC),
   `apt-daily-upgrade.timer` (~06:20 UTC) or `fwupd-refresh.timer` fired inside
   the measurement window. Two rounds' worth of "identical readings" would have
   been reported as an A/B result if either arm had straddled 03:50.

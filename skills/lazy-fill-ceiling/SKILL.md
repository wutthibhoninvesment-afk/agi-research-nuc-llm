---
name: lazy-fill-ceiling
description: Use when a capacity or "does it fit" decision rests on an OBSERVED memory reading of a system whose cache, pool or arena fills lazily on demand — an LRU cache, a demand-paged model weight cache, a connection pool, a JIT code cache. Symptoms the user will describe: "RSS was flat for hours so that's its footprint", "measured at cap N, so cap N costs X GB", "memory plateaued, it's stable now", "it only OOMs sometimes", a config value picked by scaling linearly from one measurement, a sizing constant that is really the on-disk/compressed size where the runtime allocates a decompressed one, or an OOM arriving after a config had been fine for months. Covers deriving the TERMINAL footprint from the allocator's arithmetic rather than a snapshot, inverting a live reading into a fill fraction, checking a stated anchor for impossibility, and reporting distance-to-wall in workload units. NOT for services whose memory is bounded at startup, and NOT for leak hunting — this is a real bound not yet reached.
---

# A plateau is where the traffic stopped, not where the cache ends

A lazily-filled cache produces a reading that looks exactly like a steady
state: allocate on miss, never free, and once the workload stops touching new
keys the number goes flat and stays byte-identical for hours. Everything about
that reading invites the conclusion "this is the footprint". It is not. It is
**the footprint of the traffic seen so far**, and the real ceiling is set by
the configured capacity times the per-entry allocation — a number the running
process can tell you only by eventually dying.

The bug this prevents is not a leak and not a misconfiguration. It is a
*measurement being read as a bound*, and it survives review because the
measurement is genuine, reproducible, and stable.

Real instance (round 376 of this program). A demand-paged MoE engine's cgroup
sat byte-identical at 30,870,429,696 B across two rounds 4h44m apart, with
`memory.events max = 0` and zero swap. Two prior rounds recorded plateaus like
it as the engine's footprint at its configured `--cap 256`. Deriving the
allocator instead: each cached expert is `malloc(3*inter*hidden)` **int8**,
3,342,336 B, and cap 256 x 40 layers means a terminal 44.0 GB against a 30 GiB
cap. The observed plateau was the cache **61.6 % full**, sitting 401 slots from
a hard wall, and the config everyone had been recommending for 250 rounds
overshot that wall by 4.8 GB.

## When to use (triggers)
- A footprint, capacity or "will it fit" claim cites an observed RSS, cgroup
  reading, heap dump or `top` snapshot of a process with an on-demand cache.
- A sizing constant is being scaled linearly from one measurement to pick a
  new config value (cache size, pool size, cap, worker count).
- A resource reading is described as "stable", "plateaued", "flat", "steady
  state", or "byte-identical across samples".
- A per-entry size constant exists in code and the data is stored compressed,
  packed, quantized or serialized at rest — check which side of the transform
  the constant is on.
- An OOM or eviction storm appeared without a deploy, or only under "unusual"
  traffic.
- **An RSS or `memory.current` figure DROPPED with no work done** — that is a
  residency reading, not an allocation one, and step 4 is the fix.
- A `--cap`/pool-size recommendation was chosen from an upper bound alone, with
  no floor read off the prefetcher or worker pool (step 11).

*These last two are deliberately in the body and not in the frontmatter
`description`. Round 388 added them to the description, and
`case_coverage.py` keys a skill's probe reports on its description text: the
edit silently dropped this skill from 4 recorded probe runs to 0 and turned
`test_lazy_fill_ceiling_disagrees_with_itself_on_every_case` red. Re-probing
is a priced live run and was not launched from an E round. **A description
edit discards probe history — budget a re-probe with it, or put the new
trigger in the body.**

**When NOT to use:** a service that allocates everything at startup and whose
memory is bounded by construction; ordinary leak hunting (unbounded growth with
no configured ceiling — that is a different problem); or tuning throughput
knobs that do not allocate per distinct key.

```
The ceiling is  capacity x per-entry-allocation,  computed from the allocator.
An observation can only ever prove the ceiling is AT LEAST what you saw.
```

| Excuse | Reality |
|---|---|
| "It's been flat for 8 hours across 1921 samples." | Flat means no new keys arrived. Sample count measures your patience, not the bound. |
| "It plateaued right where the docs say cap N costs." | Check whether cap N is even reachable. If capacity x per-entry exceeds the limit, no reading of a live process can ever show it. |
| "We measured it in production at the real cap." | A reading taken while the cache was filling is a lower bound. Ask what fraction was full, don't assume 100 %. |
| "The per-entry constant came from the file header." | On-disk size is not allocation size whenever the loader decompresses, unpacks or widens. Read the `malloc`. |
| "It OOM'd once, we raised the limit, it's fine." | Raising the limit moves the wall; it does not make the terminal footprint smaller. Compute where the new wall is. |

## Steps

1. **Find the allocation site, not the docs.** Locate the function that
   allocates one cache entry and read its arguments literally. Note every
   term: payload, per-entry metadata, side tables, and any conditional
   allocation (a shadow copy kept "only when the GPU tier is live").
   *Outcome:* one expression for `entry_bytes` in terms of config dimensions.

2. **Confirm the fill is lazy and monotone.** Find the miss path. The pattern
   is `if (n < cap) { allocate new } else { reuse LRU victim }` — allocation
   stops at `cap`, so footprint climbs and then stops.
   *Outcome:* a stated claim that `cap` bounds the footprint, or a note that
   it does not (in which case this is a leak, not a fill).

3. **Compute the terminal footprint absolutely.**
   `terminal = baseline + capacity * entry_bytes`, where `baseline` is a
   reading taken *before the cache took its first entry*. Never anchor on a
   reading of a partly-filled cache.
   *Outcome:* one number, comparable directly against the hard limit.

4. **Pick an observable that tracks ALLOCATION, then invert it.**
   `entries = (observed - baseline) / entry_bytes` — but `observed` must not be
   RSS or `memory.current`. Those are *residency*, and they are wrong in two
   directions at once: they FALL when the kernel reclaims (pages the process
   still owns move to swap) and they INCLUDE kernel/slab/page-cache charge that
   was never a cache entry. Use `anon + swap.current` on cgroup v2, or
   `VmRSS + VmSwap` from `/proc/<pid>/status`. State the uncertainty in
   entries, not bytes, so nobody reads spurious precision.
   *Outcome:* "the cache is X % full", which is the sentence the snapshot was
   hiding — computed from a quantity that only goes up.

5. **Add a monotonicity witness, and make it refuse to be widened.** Step 2
   established that allocation below `cap` never decreases. So encode it:
   invert two consecutive readings and grade a decrease as `instrument_error`,
   not as data. Give it a tolerance no larger than the inversion's own rounding
   — the tempting fix, when it fires, is a bigger epsilon, and a test should
   assert that even an absurd tolerance still fails.
   *Outcome:* the next wrong observable is caught by the model instead of being
   published by it.

6. **Audit every stated anchor for impossibility.** If a recorded figure
   claims to be "measured at full capacity", check `anchor - capacity *
   entry_bytes >= known_fixed_size`. A negative result means the anchor cannot
   hold the cache it claims to, and any model built on it is arithmetic on
   nonsense — make the code raise rather than return a plausible number.
   *Outcome:* each historical anchor labelled sound / mid-fill / impossible.

7. **Report distance to the wall in the units that caused the fill.** Bytes of
   headroom are not actionable; "0.22 of another request like the last two" is.
   Fit the crudest saturating curve to the observations you have, state that it
   is one data point, and give the lower-bound model beside it.
   *Outcome:* a falsifiable prediction the next cycle can score.

8. **Re-derive every downstream recommendation.** A wrong per-entry constant
   does not fail loudly; it produces confident config values. Grep for the
   constant, fix it, and re-run every sizing it feeds.
   *Outcome:* the changed recommendations listed explicitly, old value -> new.

9. **Then fix the constant's PROVENANCE, not just its value, and do the same
   for every sibling in the same record.** Correcting the number leaves the
   next reader with the same opaque literal. Replace it with an expression
   over named dimensions (`3 * INTER * HIDDEN`, not `3_145_728`) so which side
   of the transform it sits on is legible from the code. Then grade the
   constants beside it: they carry the same provenance and were written by the
   same hand. Round 382 did this one round after round 376's fix and found the
   other two size constants in the same record were bare literals too — one
   exactly right, one a rounded restatement of a value another module in the
   same repo already had exact, and one whole term (context-proportional
   scratch state) simply absent. A value can be checked; its provenance is
   what decides whether anyone ever will.
   *Outcome:* every constant in the record either derived from named
   dimensions, or explicitly named as a single live reading that cannot be.

10. **Distrust the transform claim for models you have not read the loader
   for.** "int8 in the container" does not establish "int8 in the slot" — that
   is exactly the inference round 376 falsified. If a second model's geometry
   comes from a README rather than from its allocator, say so in the code
   beside it; that is the pre-bug state, not a fixed one.
   *Outcome:* each geometry record labelled allocator-read or document-read.

11. **Bound the config from BELOW as well as above.** Sizing work naturally
    asks "how large can `cap` be"; the miss path can have a floor too. If any
    prefetcher, worker pool or in-flight queue can hold more entries per bucket
    than `cap` itself, the eviction scan can find no victim and drop into a
    fallback path — often the least-tested code in the module, and often
    recently rewritten because its predecessor was racy. Read the prefetch
    depth, not just the limit. Round 388 found a 128-deep per-layer prefetch
    queue in the same file as the cache, making every `cap <= 128` unsound and
    retracting two recommendations a prior round had made on RAM grounds alone.
    *Outcome:* a closed band `[floor+1, max_cap]`, which reports EMPTY rather
    than rounding down when a box cannot satisfy both ends.

## Pitfalls

- **Fixing the slope while keeping the anchor makes it worse.** A relative
  model `f(cap) = anchor - (cap_full - cap) * per_cap` gets *more* wrong when
  you correct `per_cap` upward, because a bigger slope walks further from an
  anchor that was already low. Round 376 saw the recommended cap move 204 ->
  225 from the correction alone, away from the true 167. Replace the model with
  an absolute one; do not repair half of it.
- **A test that restates the constant cannot detect that the constant is
  wrong.** `assert GEOM.entry_bytes == 1_769_472` held green for 250 rounds
  over a value that was the on-disk size. Tie each constant either to an
  independent recomputation from raw dimensions or to a live measurement.
- **The plateau's stability is evidence for the wrong proposition.**
  Byte-identical readings prove no new keys arrived, which is exactly the
  condition under which the reading tells you least. Check the request/access
  counter beside the memory counter, always; identical memory with zero new
  requests is not a measurement of a bound.
- **`limit` without a soft watermark gives no warning.** Check for a throttle
  band (cgroup `memory.high`, a soft limit, a high-water hook). If it is unset,
  the first symptom is the kill.
- **Reclaim has nowhere to go when the working set is anonymous.** Before
  predicting "it will just evict", check what fraction of the footprint is
  file-backed. All-anonymous plus a small swap device means thrash, then kill.
- **Counting swap into the headroom hides the cliff.** Report "X to the hard
  limit, then Y of swap" as two numbers. A single sum reads as reassurance.
- **Swap is future runway AND present debt, and it is easy to model only the
  first.** A model that adds `swap_total` to the headroom while ignoring
  `swap.current` believes the process can grow into space it is already using.
  Round 388's headroom figure was overstated by exactly the swapped-out bytes:
  538 slots claimed, 456 real.
- **Reclaim need not come from the limit you are watching.** A cgroup can lose
  hundreds of MB to *global* `kswapd` pressure with `memory.events max` still
  at 0 — the counters that distinguish them are `pgscan_direct`/`allocstall_*`
  (the allocator reclaiming in its own context) versus `pgscan_kswapd`
  (background, whole-machine). Zero traffic to your service does not mean zero
  memory events for your service.
- **The perturbation is usually a timer, and the box already recorded it.**
  Before theorising, read `sar`/`sysstat` (10-minute buckets on a default
  Ubuntu install) for the swap-out rate, and `systemctl list-timers` for what
  fired in the same bucket. Round 388 pinned 76 % of an unexplained swap event
  to the bucket containing `apt-daily.service`. Any A/B on such a box must
  record whether a housekeeping timer straddled the measurement window.
- **A stable reading is the reason a lesson gets recorded too narrowly.** The
  round that first noticed this cache's flat line wrote "the flat line was the
  reason not to look, and it was exactly the wrong reason" — about that one
  number. Two rounds later the same number was published as unchanged three
  more times, because the lesson had been filed under the number rather than
  under flat lines.

## Verification

Run against the real system and paste the output into the record:

```
# 1. the allocator's own arithmetic
python3 nuc/expert_cache.py geometry     # entry bytes from raw dims
# 2. does the configured capacity even fit?
python3 nuc/expert_cache.py plan         # -> max_cap per safety margin
# 3. where is it actually
python3 nuc/expert_cache.py fill --current <observed>
# 4. how far to the wall, in requests -- on the ALLOCATION observable
python3 nuc/expert_cache.py wall --current <memory.current> --anon <anon> \
                                 --swap-current <swap.current>
# 5. residency vs allocation for one reading, incl. the monotonicity verdict
python3 nuc/expert_cache.py snapshot --current <c> --anon <a> --swap-current <s>
# 6. is this cap sound at BOTH ends?
python3 nuc/expert_cache.py bound --cap <n>     # -> in_sound_band, bounded_by
```

Expected shape: `plan` names a cap strictly below the configured one whenever
`terminal_bytes(configured) > limit`; `fill` reports a fraction well under
100 % for any live process that has not been killed.

- [ ] `entry_bytes` recomputed by hand from raw dimensions, matching the code
- [ ] fill path confirmed lazy and capped (quote the miss-path branch)
- [ ] the observable inverted is allocation (`anon + swap.current`), not RSS
- [ ] two consecutive readings run through the monotonicity witness
- [ ] the reclaim source identified as cgroup-limit vs global (`pgscan_direct`
      / `allocstall_*` vs `pgscan_kswapd`)
- [ ] the cap band is closed at BOTH ends, with the floor's source quoted
- [ ] `baseline` is a pre-first-entry reading, not a mid-fill one
- [ ] every historical anchor classified sound / mid-fill / impossible
- [ ] downstream config recommendations re-derived and listed old -> new
- [ ] distance to wall stated in workload units and banked as a prediction

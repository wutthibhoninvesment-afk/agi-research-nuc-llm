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

4. **Invert the live reading into a fill fraction.**
   `entries = (observed - baseline) / entry_bytes`. State the uncertainty in
   entries, not bytes, so nobody reads spurious precision.
   *Outcome:* "the cache is X % full", which is the sentence the snapshot was
   hiding.

5. **Audit every stated anchor for impossibility.** If a recorded figure
   claims to be "measured at full capacity", check `anchor - capacity *
   entry_bytes >= known_fixed_size`. A negative result means the anchor cannot
   hold the cache it claims to, and any model built on it is arithmetic on
   nonsense — make the code raise rather than return a plausible number.
   *Outcome:* each historical anchor labelled sound / mid-fill / impossible.

6. **Report distance to the wall in the units that caused the fill.** Bytes of
   headroom are not actionable; "0.22 of another request like the last two" is.
   Fit the crudest saturating curve to the observations you have, state that it
   is one data point, and give the lower-bound model beside it.
   *Outcome:* a falsifiable prediction the next cycle can score.

7. **Re-derive every downstream recommendation.** A wrong per-entry constant
   does not fail loudly; it produces confident config values. Grep for the
   constant, fix it, and re-run every sizing it feeds.
   *Outcome:* the changed recommendations listed explicitly, old value -> new.

8. **Then fix the constant's PROVENANCE, not just its value, and do the same
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

9. **Distrust the transform claim for models you have not read the loader
   for.** "int8 in the container" does not establish "int8 in the slot" — that
   is exactly the inference round 376 falsified. If a second model's geometry
   comes from a README rather than from its allocator, say so in the code
   beside it; that is the pre-bug state, not a fixed one.
   *Outcome:* each geometry record labelled allocator-read or document-read.

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

## Verification

Run against the real system and paste the output into the record:

```
# 1. the allocator's own arithmetic
python3 nuc/expert_cache.py geometry     # entry bytes from raw dims
# 2. does the configured capacity even fit?
python3 nuc/expert_cache.py plan         # -> max_cap per safety margin
# 3. where is it actually
python3 nuc/expert_cache.py fill --current <observed>
# 4. how far to the wall, in requests
python3 nuc/expert_cache.py wall --current <observed> --requests <n>
```

Expected shape: `plan` names a cap strictly below the configured one whenever
`terminal_bytes(configured) > limit`; `fill` reports a fraction well under
100 % for any live process that has not been killed.

- [ ] `entry_bytes` recomputed by hand from raw dimensions, matching the code
- [ ] fill path confirmed lazy and capped (quote the miss-path branch)
- [ ] `baseline` is a pre-first-entry reading, not a mid-fill one
- [ ] every historical anchor classified sound / mid-fill / impossible
- [ ] downstream config recommendations re-derived and listed old -> new
- [ ] distance to wall stated in workload units and banked as a prediction

---
name: residency-is-not-allocation
description: Use when a model inverts an observed memory figure into "how much of X is loaded" — cache slots, arena entries, buffer pool pages — and the figure is a RESIDENCY reading (RSS, cgroup memory.current, top's RES, container "memory usage") rather than an allocation one. Symptoms: a monotone-by-construction quantity appears to shrink; a long-flat number moves with no workload; a fill percentage disagrees with what the allocator's source says can happen; two readings taken days apart differ and nobody can name a cause. Also covers the harder half — the BASELINE you subtract must be the same quantity as the reading you subtract it from, and a baseline is where the unit mismatch hides, because it was measured once, long ago, and never re-derived.
---

# Residency is what the kernel is currently willing to keep. Allocation is what you asked for.

Every OS exposes memory usage as residency, because residency is what it has to
manage. Almost every question people ask of that number — *how full is the
cache, how many entries are loaded, how much room is left* — is a question
about allocation. The two agree only while nothing reclaims, and the day they
diverge, the model reports something the allocator's own source code forbids.

    residency  = RSS, cgroup `memory.current`, `top` RES, container "usage"
                 -> falls under reclaim, includes page cache and kernel charge
    allocation = anon + swap.current, VmData, malloc'd-and-not-freed
                 -> monotone for an append-only cache, wherever the pages live

## Trigger conditions

- You are dividing `(observed - baseline) / entry_size` to get "entries
  loaded", and `observed` is an RSS-like number.
- A quantity your source says is monotone (allocated once, reused in place,
  never returned to the allocator) appears to **decrease**.
- A number was flat across several samples and someone recorded the flatness
  as a *property of the system* rather than of the observation window.
- A fill fraction, headroom, or capacity plan is being published from a single
  reading of a residency figure.
- Someone fixed the numerator of an inversion and did not re-derive the
  baseline. **This is the common case and it is invisible in review**, because
  the baseline is usually a constant with a comment saying where it came from.

**When NOT to use:** you genuinely want residency — you are sizing a machine
for *working set*, or asking "will this page-fault", or tuning a watermark.
Residency is the right observable for those, and swapped-out pages really are
not resident. The failure is only in reading it as allocation.

## Steps

1. **Name the observable in the model, out loud, before doing arithmetic.**
   Write down which of the two each input is. Most of these bugs survive
   because nobody ever wrote "this is residency" next to a variable called
   `observed` or `current`.

2. **Get the allocation-faithful figure.** On cgroup v2 that is
   `anon + memory.swap.current` from `memory.stat` / `memory.swap.current`, not
   `memory.current`:
   ```bash
   # CG = the unit's cgroup-v2 directory, from `cat /proc/<pid>/cgroup`
   grep -m1 '^anon ' "$CG/memory.stat"      # resident anonymous bytes
   cat "$CG/memory.swap.current"            # the rest of the allocation
   ```
   Per process it is `VmData` (commitment) and `RssAnon + VmSwap`
   (allocated-and-touched) from `/proc/<pid>/status` — never `VmRSS` alone.

3. **Check the baseline is the SAME quantity.** Subtracting a residency
   baseline from an allocation figure understates the result by exactly the
   non-anon charge the baseline carried — page cache, slab, mapped files. Ask
   what the process was *doing* when the baseline was taken. If it had been
   reading a large file, the baseline is inflated by page cache and the answer
   is wrong by that much, silently and in a plausible-looking direction.

4. **Derive the baseline at least two independent ways and publish it as a
   band.** For a model server: (a) on-disk size of the artefact minus the part
   the cache holds, (b) system-wide commitment before the first request less
   everything that is not the process, (c) the same for anonymous+slab. Routes
   that share no input are what turn "I trust this number" into evidence.

5. **Build a monotonicity witness.** If the source says the quantity cannot
   decrease, assert it, and grade a decrease `instrument_error` rather than
   absorbing it into a tolerance. The tempting fix is a bigger epsilon; write
   the test that says a generous tolerance still does not launder the observed
   drop.

6. **Prefer a DIFFERENCE of two observations to an inversion of one.** An
   inversion needs a correct baseline; a difference does not. If any sampler
   recorded the quantity across the event that changed it, the step it left is
   the measurement, and it costs no model at all. (See
   `instruments-already-running` for finding those samplers.)

7. **Cross-check the corrected model against something it did not use.**
   Recompute the config ceiling, or compare the fill against what the system
   is currently surviving. A corrected model that now says the live
   configuration is impossible is not corrected.

## Pitfalls

- **A flat line is not a state.** Repeated identical readings mean nothing
  perturbed the *instrument*, which is a weaker claim than "nothing changed"
  and a much weaker one than "this is the value". Three consecutive rounds
  published a byte-identical `memory.current` on one box as a property of the
  deployment; it was a property of a box that nothing else had allocated
  against yet.
- **`memory.current` falling is not the cache shrinking.** Reclaim moves anon
  pages to swap: residency falls, allocation does not. `anon +
  swap.current` is invariant across the move, and that invariance is the check.
- **Fixing the numerator and not the denominator is the majority failure
  mode.** One round replaced `memory.current` with `anon + swap.current`
  throughout an inversion and left the zero-point as a `memory.current`
  reading, with a docstring arguing it "serves for both" because
  `swap.current` was 0 at the time. `swap.current == 0` makes
  `anon + swap == anon`; it does not make `memory.current == anon`. The
  baseline was ~2x too large and the fill was understated by 14 points.
- **`Committed_AS` / `VmData` can step up permanently while RSS falls back.**
  glibc returns freed pages with `MADV_DONTNEED`: the mapping and its
  commitment survive, the residency does not. A process that ballooned and
  deflated leaves a trace in commitment and none in RSS.
- **Do not read the last digits.** These inversions are good to a few slots
  per few MB of unmodelled drift. Publish the band.

## Verification

Run all of these; each fails loudly on the bug it targets.

```bash
# 1. the invariant: allocation is unchanged across a reclaim event
#    (anon falls by exactly what swap.current gains). CG is the unit's
#    cgroup-v2 directory on the target host, from `cat /proc/<pid>/cgroup`.
grep -m1 '^anon ' "$CG/memory.stat"; cat "$CG/memory.swap.current"

# 2. the monotonicity witness, on two real readings
python3 -c "from nuc import expert_cache as e; import json; print(json.dumps(
  e.check_monotone(e.fill_from_current(e.R382_MEMORY_CURRENT),
                   e.fill_from_current(e.R388_MEMORY_CURRENT))))"
#    -> verdict "instrument_error" (residency); "ok" via fill_from_snapshot

# 3. the baseline witness: candidates vs a measured growth
python3 -m nuc.expert_cache baseline
#    -> the residency baseline errs 19.1%; three allocation routes err <0.7%

# 4. the tests that pin all of the above
python3 -m pytest -q nuc/tests/test_expert_cache.py
```

A model is verified when the corrected fill agrees with a *measured*
difference to within the baseline band's own width, and when the config the
box is actually running is inside what the corrected model calls survivable.

## Provenance

Round 388 found the numerator half on `pgain-nuc` (a 458 MB `memory.current`
swing with zero requests served) and **announced this skill without creating
it**. Round 394 found the denominator half — the baseline was a
`memory.current` reading taken while the cgroup held several GB of model page
cache — and wrote the file. Two instances, one pattern; the second is the one
that changed a published capacity recommendation.

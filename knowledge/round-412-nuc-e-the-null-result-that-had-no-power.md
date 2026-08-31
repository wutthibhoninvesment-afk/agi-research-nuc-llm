# Round 412 (NUC-integration E) — the null result that had no power

**Date:** 2026-08-31 · **Box:** `pgain-nuc` **DOWN the whole round** ·
**Track:** E · **Predecessor:** round 406 (also down) · **Predictions:**
`nuc/predictions-e-round412.md`, written before any measurement (D-013).

---

## 0. Reachability, and why this is an offline round

`python3 nuc/reachability_check.py check --round 412` at
**2026-08-31T22:11:08Z**:

```
verdict: down   ssh_returncode: 255   "connect to host 100.78.44.111 port 22: Connection timed out"
tailscale_online: false   tailscale_last_seen_utc: 2026-08-31T16:30:00.1Z
```

That last-seen timestamp is **byte-identical to round 406's**, so this is the
same continuous outage, not a second one — the box has not been up between the
two rounds. A second confirming ssh probe also timed out (rc 255). Two
consecutive failures ⇒ probing stopped, per CLAUDE.md. Logged as record **46**
of `state/nuc-reachability-log.jsonl`.

Round 406's handoff item 1 ("if UP, run `capture_manifest plan`") therefore
does not fire and carries forward unchanged. **Item 4 — explicitly marked
*"runnable offline on the next DOWN round"* — is this round's work**, and it
turned out to contain more than it advertised.

---

## 1. The question, and the sentence that provoked it

Round 406 built `attribution_evidence`, ran it over the whole boot, and
published:

> Over the whole boot: 16 units tested, **`supported: []`** — this instrument,
> over this record, licenses no causal claim at all.

Its own handoff doubted it: *"`supported: []` may mean the 10-minute `sar`
window is too coarse to attribute anything here."*

The doubt is the right one but it is aimed slightly off. The problem is not
the window. It is that **`attribution_evidence` never asked whether
`supported` was reachable**, so its output cannot distinguish

* the box did nothing attributable, from
* the arithmetic could not have detected it if it had.

Those are different claims and only one of them is about the NUC. A null
result with no power floor attached is unpublishable, and round 406 published
one.

---

## 2. The power floor

For a unit occupying `d` of `N` buckets against `K` costly ones, the smallest
`p_chance` it can attain is the one where it covers `min(K, d)` of them —
`best_case_p(N, K, d)`. Bonferroni over `n_units_tested` puts the bar at
`max_family_p / n_units_tested`. If `best_case_p × n_tested > max_family_p`,
**no arrangement of that unit's fires could have been supported**.

```python
def best_case_p(N, K, d):
    return _hypergeom_atleast(N, K, d, min(K, d))
```

`power_floor(N, K, n_units_tested, max_family_p)` runs that over every
occupancy `1..N` and reports the testable band. It needs **no data** — only
the record's shape — which is the point: you can ask whether a capture could
support anything *before* you go and take it.

### 2a. The record round 406 actually ran

`power_floor(218, 3, 16)`:

```
per_unit_bar            0.003125
min_testable_occupancy  2
max_testable_occupancy  32
testable_fraction_of_N  0.1422
why                     "occupancies 2..32 can clear the bar (contiguous)"
```

**8 of the 16 units are untestable.** Seven of those eight because their
occupancy is **too LOW** — they fired once, `d = 1`, and covering one costly
bucket out of three by chance has `p = 3/218 = 0.0138`, which × 16 = 0.22.
The eighth is `fwupd-refresh`, `d = 36`, too HIGH.

### 2b. The counterintuitive half: too-low occupancy is as fatal as too-high

The testable set **does not start at 1**. `d = 1` is untestable while `d = 2`
is testable, a hundredfold drop in `p_best` from one extra bucket, because
covering *one* of K by chance is common and covering *two* is rare. Every
instinct here says "the unit that fired once is the cleanest case"; the
arithmetic says it is the one case that can never be decided.

### 2c. The vacuity case, exactly

If `K = 1`, then `p_best(d) = d/N`, minimised at `d = 1`:
`1/218 × 16 = 0.0734 > 0.05`. **No occupancy clears the bar at any `d`.** A
record with a single costly bucket cannot support any attribution *whatever it
contains*.

This is not hypothetical on this box. **`sa30` alone has `N = 139, K = 1`.**
Round 406 pooled the two day-files with the justification "sa30 contributes 23
free `fwupd-refresh` fires that sa31 alone cannot see". That was right, and
here is the quantitative reason it was *necessary*: pooling took the record
from `any_testable: False` to a band of `2..32`. **Run per-day, round 406's
whole instrument returns `supported: []` from a day with zero power.**

### 2d. `untestable` cannot steal from `supported`

The new verdict sits between `shared-only` and `coincidence`. Anything it
captures already had `p_family > max_family_p`, so it was already
`coincidence`. **Round 406's `supported: []` headline is unchanged**, and
pinned as such. What changes is what "not supported" *meant* for eight units.

### 2e. `fwupd-refresh`'s verdict was fixed before the data was read

`d = 36`, `K = 3`, `N = 218`: `p_best = 0.00419`, × 16 = **0.067 > 0.05**.
**Even if `fwupd-refresh` had hit all three costly buckets, it would still
have read `coincidence`.** Round 406's refutation of the fwupd attribution is
correct and its consistency argument (33 of 36 fires moved zero bytes) is
independent and stands — but on the swap channel the chance test it also
reported had no power to have said otherwise.

---

## 3. Round 406's own test suite was in the vacuous regime

`test_a_unit_whose_own_fires_are_mostly_free_is_a_coincidence` was written to
demonstrate the consistency rule. Its fixture is `N = 79, K = 1`, one unit,
`d = 18`. So `p_chance = 18/79 = 0.228 > 0.05`, **the chance branch fires
first and the consistency branch is unreachable behind it.** The test asserted
the string `"coincidence"`, which was right for the wrong reason, and it went
red the moment `untestable` was inserted — which is how it was found.

Split into two: `test_round_406s_consistency_fixture_never_reached_the_
consistency_rule` (pins the discovery, including
`_hypergeom_atleast(79,1,18,1) > 0.05` — the branch that actually fired), and
a rewritten consistency test on a fixture that reaches the rule (`K = 4`, unit
covers all four costly buckets so chance is excluded at `p ≈ 1e-5`, and it is
still rejected because 6 of its 10 fires cost nothing).

**A verdict string can be correct while the branch that produced it is not the
one the test is named after.** Asserting the string is not asserting the
mechanism.

---

## 4. Testability is a property of the RUN, not of the unit

Bonferroni's uncomfortable corollary, found by writing a fixture that refused
to fail. The identical 36 fires with the identical best-case outcome are

* **testable** in a one-unit family (bar 0.05) — and then lose the test on
  consistency, which is a real result about the unit;
* **untestable** in a sixteen-unit family (bar 0.003125).

Same evidence, same `p_chance`, different verdict. **Widening the family can
retract a claim without a single new observation.** The correction is still
right — the unit under test was chosen by having been noticed — but a ledger
that reports `untestable` without reporting the family it was graded against
is not reproducible. `n_units_tested` now rides in every unit's record and in
the `power` block.

---

## 5. The second channel

Item 4's remedy: run the same fires against `Committed_AS`. `cost_ledger` was
channel-locked — it read the literal string `pswpout/s` — so this needed an
abstraction, and the abstraction is not cosmetic:

| | `pswpout/s` | `kbcommit` |
|---|---|---|
| shape | **RATE** — self-contained per bucket | **LEVEL** — a delta against the previous row |
| cost | `rate × interval × page_bytes` | `value[i] − value[i−1]`, rises only |
| undefined buckets | none | the table's first row, and any post-restart row |

`bucket_costs` returns **`None`, not `0`**, for an undefined bucket, and
`cost_ledger` routes fires there to `unclassified` and drops them from `N`.
That is round 400's own rule — *a fire whose cost is unknown is not a fire
that cost nothing* — applied to the buckets themselves.

### 5a. A parser that drops a marker makes the marker undiscoverable

`parse_sar` **silently discarded `LINUX RESTART`**. Harmless for a rate
column; corrupting for a level one, where the delta across a reboot spans two
different address spaces — on `sa30` that is an 18.4 GB step that would have
been booked as some housekeeping unit's cost. `sysstat_archive.parse_day` has
always kept restarts. **Two parsers over the same bytes disagreeing about
whether a marker is representable is a defect that only appears when a new
consumer needs the marker.** `SarRow.restart_before` now carries it;
`sa30`'s `00:50:05` row is the one marked, and `139 + 79 = 218` reproduces
round 400's N exactly.

### 5b. The commit channel gives fwupd the powered test swap could not

At `min_bytes = 4,825,700` (the swap channel's derived threshold, reused so
the two are comparable), the commit channel has `N = 216`, `K = 9`, 13 units.
`fwupd-refresh` at `d = 36` is now **inside** the testable band. The test
genuinely runs — and fwupd fails it: it covered 1 of the 9 costly buckets,
which a unit of its occupancy does by chance with `p = 0.813`.

**Round 406's DROP verdict on fwupd now rests on a powered test rather than on
a consistency argument alone.** That is item 4, answered.

### 5c. The threshold sweep — and an inversion I had backwards

`channel_sweep` re-grades the whole record at every threshold, because a
verdict that moves with an unpinned constant is a setting, not a verdict.
Nine thresholds × two channels:

```
                swap                              commit
min_bytes    K   d-band  testable  reach      K    d-band  testable  reach
      4096   4    2..52     9/16    True      27   3..178    4/13    True
    524288   3    2..32     8/16    True      22   3..170    4/13    True
   4825700   3    2..32     8/16    True       9   2..118    8/13    True
   8388608   2    2..12     8/16    True       6    2..87    8/13    True
  33554432   2    2..12     8/16    True       4    2..54    8/13    True
 134217728   1     none     0/16   FALSE       3    2..34    7/13    True
1073741824   0     none     0/16   FALSE       2    2..13    7/13    True
```

I predicted the swap channel would be the threshold-insensitive one (B7). It
is the opposite. **Above ~134 MB the swap channel has no testable unit at any
occupancy** — `supported: []` there is pure arithmetic. The commit channel
never enters that regime, because it still has costly buckets left to be
improbably covered. The robust instrument is the one with more events in it,
which in hindsight is obvious and was not obvious enough to predict.

**`supported` is `[]` in all 18 configurations.** Round 406's headline
survives everything, which is what makes it a result rather than a setting.

### 5d. The largest swap event of the boot committed nothing

The finding I did not go looking for. `sa31`, two buckets:

| bucket | swap-out | commit rise | raw `kbcommit` move |
|---|---|---|---|
| `02:00:05` | 67.68 MB | **+150.62 MB** | +147.1 MB |
| `04:00:03` | **220.89 MB** | **0** | **−1.6 MB** |

Rounds 388, 394 and 400 circled `04:00:03` — 220.9 MB out, five named units in
it — as the largest perturbation this deployment has seen. **On the
commitment channel that bucket does not rise at all; `Committed_AS` FALLS
across it.** No new address space was promised there, so whatever drove
220 MB to swap was **reclaim against memory already committed**, not a
housekeeping unit allocating. The apt cluster the record keeps circling did
not allocate.

Stated carefully, because `kbcommit` is committed address space and not RSS:
this rules out *"a housekeeping unit allocated 220 MB"*, which is exactly the
story a costly-bucket ledger invites. It does not identify what did drive the
reclaim.

By contrast `02:00:05` — fwupd's bucket — **is** a real allocation, +150.6 MB
committed alongside 67.7 MB out. The two events the record treats as the same
kind of thing are not the same kind of thing, and the bigger one is the one
with nothing behind it.

---

## 6. A latent defect: `bucket_shared_by` counted fires, not units

`share[name] = share.get(name, 0) + 1` per placed **fire**. So two fires of
the *same* unit in one bucket set `bucket_shared_by = 2` and
`sole_attributable = False` — the flag reporting "nothing here is separable"
about a bucket in which **exactly one unit is implicated**.

Fixed: `share` counts distinct units; `bucket_fires` is a new, separate field.

**Predicted this would be reachable in the banked record (A9). It is not** —
zero buckets on either day hold same-unit repeats, so every published number
is unchanged and the defect was latent, never active. Pinned as both: a
synthetic test that the fix works, and a test that round 400's `62 / 6 / 1`
headline did not move.

---

## 7. What the journal bounds

Item 4 says the `Committed_AS` channel is banked "for all nine days". True of
the **channel**; false of the **analysis**. `unit-starts.txt` runs
**2026-08-30T00:32:32 → 2026-08-31T13:16:41** — one boot, two days. There are
no unit fires banked for `sa23`–`sa29`, so attribution cannot use them, and no
amount of `sar` data changes that. The nine days are an availability witness
(round 400's use), not an attribution corpus.

A related, fixable loss: a level channel cannot see a day-file's **first**
bucket, and three units (`dpkg-db-backup`, `logrotate`, `sysstat-summary`)
fire at 00:00:05/00:07:05 on `sa31` and vanish from the commit family
entirely — 16 units → 13. They are reported as `unclassified` with the reason,
not silently dropped. **Stitching consecutive day-files would recover them,
and the data to do it is already in git.**

---

## 8. Verification

```
nuc/tests/test_perturbation.py     65 -> 96 passed
nuc/tests/  (whole suite)         638 -> 669 passed, 68.6 s, exit 0
nuc/constant_audit.py audit nuc/   23 constants, 18 derived, 0.783, 0 transform risks  (unchanged)
skills/run_checks_fast.sh          skill_lint 61/0/0 · claim_check 134 resolved, 0 stale
                                   xref_check 0 dangling authoritative · state_claim_check 0 stale
```

`carryforward` reported **ERROR K001** mid-round — *"round 412 banked
predictions and `state/prediction-bank-ledger.json` has no entry for it"* —
i.e. the checker catching D-013's second half being outstanding, exactly as
designed. Cleared by §9 below.

### CLI

```bash
# could a record of this shape support ANYTHING? no data required
python3 -m nuc.perturbation power --n-buckets 218 --n-costly-buckets 1 --n-units-tested 16
# -> any_testable: false

# the verdict as a function of the threshold
python3 -m nuc.perturbation sweep --day sa30.txt:2026-08-30 --day sa31.txt:2026-08-31 \
    --journal state/nuc-capture-r400/unit-starts.txt --channel commit

# the commit channel refuses to invent a threshold
python3 -m nuc.perturbation ledger --sar-w sa31-r.txt --journal ... --date 2026-08-31 --channel commit
# -> PerturbationError: channel 'commit' has no derived costly-threshold ... or use channel_sweep
```

`LEDGER_MIN_BYTES` is derived from two **labelled** swap events. The commit
channel has no such pair on this record, so `CHANNEL_MIN_BYTES["commit"] is
None` and `cost_ledger` **raises** rather than shipping a number with a
derivation-shaped comment and no derivation.

---

## 9. Predictions scored — 14 HIT / 2 PARTIAL / 3 MISS of 19

| # | Verdict | Note |
|---|---|---|
| A1 | **HIT** | N = 218, 16 units |
| A2 | **HIT** | K = 3 ≤ 4 |
| A3 | **HIT** | testable fraction 14.2 % < 20 % |
| A4 | **HIT** | 8 of 16 untestable (predicted ≥ 6) |
| A5 | **HIT** | fwupd untestable; `d_max` 32, predicted ≤ 33 |
| A6 | **HIT** | K=1 ⇒ zero power, exactly `1/218 × 16 = 0.0734` |
| A7 | **HIT** | sa30 alone: N=139, K=1, `any_testable: False` |
| A8 | **HIT** | `shared_by` counted fires; confirmed synthetically |
| A9 | **MISS** | predicted the defect was reachable in the record — **zero** buckets hold same-unit repeats. It is latent |
| A10 | **HIT** | `supported: []` survives verbatim |
| A11 | **HIT** | `coincidence` count was 1 (predicted ≤ 4) |
| B1 | **HIT** | channel-locked on the literal `pswpout/s` |
| B2 | **HIT** | level vs rate needs `kind`, not a column name |
| B3 | **PARTIAL** | 6.75× at 4 kB, only **3×** at the threshold that matters |
| B4 | **PARTIAL** | `d_max` larger (118 vs 32) ✓, but testable units **8 vs 8**, not "strictly more" |
| B5 | **HIT** | commit still `supported: []`, all 9 thresholds |
| B6 | **MISS** | predicted ≥ 5 units of movement; measured **4** |
| B7 | **MISS** | predicted swap was the insensitive channel. **Backwards** — swap moves 9→0 and collapses to zero power; commit never does |
| B8 | **HIT** | journal = 2026-08-30 → 08-31 only |

The three worst-scored predictions (A9, B6, B7) are all about **how much the
instrument would move**, and B7 being backwards produced §5c, the best result
in the round. I was accurate about the arithmetic I could do on paper (A1–A8,
A10, A11, B1, B2, B8 — 11 of 11) and wrong about every empirical magnitude I
guessed at (B3, B4, B6, B7 — 0 of 4 clean). **The predictions I could have
computed instead of guessed, I got right; the ones I guessed, I got wrong**,
which is an argument for computing the power floor before the capture rather
than after.

---

## 10. Hygiene

- **Box unreachable all round.** Two ssh attempts, both timed out, then
  stopped per CLAUDE.md. No scp, no writes on the box, no unit restarted.
- **Port 8001 never contacted; no engine request of any kind.** Every module
  touched is pure text-in/dict-out and opens no socket.
- READ-ONLY on `/work/**` — not reachable anyway.
- `languages/whence/SECURITY.md` was already modified on arrival (Hermes
  gateway). Untouched, not reverted, not committed. **64 rounds carried.**
- No worktrees created. No background job left running.

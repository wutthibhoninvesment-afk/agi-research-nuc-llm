# Round 457 (harness A) — predictions, banked BEFORE measuring (D-013)

**Question.** Round 456's next-step 4: *"Six consecutive rounds have now landed
a predecessor's slow-tier ledger orphan… The fix is in the driver, not in the
next round's part 0. harness(A)."* This round owns that. Before fixing it I am
sizing the whole mechanism: what the per-round slice has COST since round 439
wired it, and what the program has actually GOT for that cost.

## Baselines — already in front of me, NOT predictions

Read from `logs/driver.log` and `git log` before writing this file. Recorded
here so nothing below can be mistaken for a guess.

* `harness/run_slowtier_slice.sh` was added round 439 and has logged a
  `slowtier-slice OK` line every round from 440 to 456 — **17 lines**.
* The per-round recall those 17 lines report, in order (440→456):
  `19, 22, 25, 12, 3, 6, 3, 6, 9, 3, 3, 6, 3, 6, 9, 12, 3` %.
  It is a sawtooth. It has never exceeded 25%.
* 13 commit subjects in this repo match `land round <N>'s … orphan`; the
  chain 444→456 is unbroken except at 451.
* `slowtier.checkout_digest` digests every `.py` and `.lang` file under
  `languages/whence/` (source read at `harness/swe/slowtier.py:124`).
* The driver runs the slice at `run_driver.sh:647-661`, AFTER the round's
  Claude session has exited — so the round that pays for the row is gone
  before the row exists.

## Predictions

**P1 (orphan rate).** Of the 17 driver-written slice rows for rounds 440-456,
**17 were left uncommitted by the round that produced them** — a 100% orphan
rate, no exceptions. *Basis:* the append happens after the session exits;
there is no code path by which the round could commit it. This is close to a
deduction, and I bank it because it is the claim the fix rests on: if even one
row landed inside its own round, the ordering story is wrong.
**Confidence: very high.**

**P2 (what the orphan cost).** Between 10 and 15 of those 17 rows were landed
by a LATER round spending its own part-0/part-1 on it, and the rest are
accounted for by a round that folded the file into another commit or by a row
still uncommitted at the time. *Basis:* 13 matching subjects, and rounds 451
and 456 are visibly irregular. **Confidence: moderate.**

**P3 (slice wall-clock paid).** The driver has spent between **2 000 and
4 000 seconds** of wall clock on slices across rounds 440-456 (sum of
`seconds` over driver-written rows). *Basis:* budget is 240 s/round and
`plan()` returns whole units that FIT, so the mean row should sit well under
240 s; 17 rounds × ~150 s ≈ 2 600 s. **Confidence: moderate.**

**P4 (the waste, and this is the number I care about).** The ledger contains
substantially more rows than distinct units, because a digest reset forces
already-run units to be re-run. I predict **at least 40% of all slice rows
re-run a unit that some earlier row had already run**, and that the repeat
fraction restricted to the driver-written era (440-456) is HIGHER than over
the whole ledger. *Basis:* the sawtooth. Each reset drops recall to 3% and
`plan()` orders worst-evidence-first, so after a reset every unit is equally
worst-evidence and the planner re-runs from scratch. **Confidence: moderate —
the direction is near-certain, the 40% is the guess.**

**P5 (cause attribution).** Every drop in the recall sequence above is
immediately preceded by a round that committed at least one `.py` or `.lang`
file under `languages/whence/`, and every rise is a round that did not. I
predict this holds for **all 17** transitions with **zero** exceptions.
*Basis:* `checkout_digest`'s definition. A single exception would mean
something else moves the digest — an untracked write by the Hermes gateway is
the obvious candidate, and it would change the fix. **Confidence: moderate;
I expect 1-2 exceptions from gateway writes.**

**P6 (scoped recall is not the escape hatch).** Round 361 built
`fresh_pass_scoped` precisely so a whence change outside a unit's measured
read-scope would not invalidate it. I predict it rescues **almost nothing**:
fewer than 25% of ledger rows are narrowable under
`readscope.scope_is_narrowable`, because the ones I have read carry
`opaque: ["subprocess.Popen"]`. Concretely: `n_scoped` at HEAD is **≤ 2**.
*Basis:* four rows read by hand, three of them opaque. **Confidence:
moderate-high on the direction, low on the exact number.**

**P7 (the arithmetic ceiling).** Under the current rotation (language(C) at
rounds ≡ 2 and ≡ 0 mod 6, i.e. a reset at worst every 3rd round), a 240 s
budget cannot cover the tier before the next reset. I predict the tier's
total measured cost is **> 3 000 s**, so ≥ 13 consecutive non-resetting
rounds would be needed, and the rotation never supplies more than 4.
Therefore the observed 25% maximum is not bad luck — it is the ceiling.
**Confidence: high on the structure, this is arithmetic; the 3 000 s is the
part that could be wrong.**

**P8 (the fix works).** After the driver commits the ledger append itself,
round 458's `record-check` line will NOT list
`state/slow-tier-ledger.jsonl` among its unattributed dirty paths. This is
the falsifiable end-to-end claim and it is checkable in one line of
`logs/driver.log` next round. **Confidence: high.**

**P9 (the fix's blast radius).** Adding a `git commit` to `run_driver.sh` will
not break any existing `harness/tests/test_run_driver_*.py`, because those
tests run the driver in a `tmp_path` workspace that is not a git repository —
so the commit must be written to no-op safely there. I predict at least one
of the 12 existing driver tests would FAIL if the commit were written
naively (unscoped `git add -A`), and that the guarded form passes all of
them. **Confidence: moderate.**

## What would make me wrong in a way that changes the round

If P1 is false, the ordering diagnosis (round 452's, carried by 453-456) is
wrong and the fix belongs somewhere else. If P5 is false — resets are NOT
explained by whence source commits — then committing the ledger is still
right but the recall story has a second cause I have not found.

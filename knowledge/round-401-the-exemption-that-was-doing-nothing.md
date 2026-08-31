# Round 401 (SWE-loop D) — the exemption that was doing nothing, and the guard that never guarded a sweep

**Track:** D (autonomous SWE — the harness used on our own code).
**Date:** 2026-08-31. **Model:** claude-opus-5. **Box:** 1 CPU.
**Task:** round 389's next-step items **5, 4 (remainder), 1, 2**.
**Predictions:** banked before any measurement in
`state/swe/round-401/PREDICTIONS.md` (21 items). All 21 are **NEVER
SCORED** — this file was cut off before §8; see the truncation notice at
the end. (Line edited by round 402; nothing else in this file was touched.)

---

## 0. Pre-flight

One `claude -p` process (`ps aux | grep '[c]laude -p'` → 1 row, this round);
`git diff --cached --stat` empty. Two files dirty on arrival and neither is
this track's to commit: `state/round_counter` (400→401, the driver's own
write) and `languages/whence/SECURITY.md`, escalated to the operator since
round 349 and carried unchanged by rounds 389/394/395/399. Round 401 does not
touch it either. (§8, P21.)

---

## 1. Headline

Round 389 raised the oracle suite's depth ceiling from 500 to 5 000, converted
38 of 41 space exemptions, and named the three survivors — fuzz seeds **140,
273, 341** — "the corpus's only unbounded tail programs", leaving as its item 5
the question of what they actually are.

They are not unbounded *tail* programs, and the exemption that covers them was
never doing any work.

`oracle_tail_transparency` runs a program twice — as written, and with every
tail flag cleared — and exempts the comparison when the **lifted** run reaches
`max_depth`:

```python
a, _ = _answer(pkg, program, tainted, whole, max_depth=max_depth)   # peak discarded
...
b, peak = _answer(pkg, lifted, tainted, whole, max_depth=max_depth)
if peak >= max_depth:
    return OracleOutcome("ok", TAIL_ORACLE, "... (space-exempt)")
```

`_answer` returns the peak depth of **both** runs. The oracle throws the
original run's peak away with an underscore, and so does
`exemptmap.measure` (`a, _peak_a = O._answer(...)`). That one discarded number
splits every firing of the branch into two populations that need opposite
treatment, and measuring it is what this round did.

---

## 2. Method: `harness/swe/spacewitness.py`

New module. For a program it runs both forms exactly as the oracle does, keeps
**both** peaks, and computes `first_difference(a, b)` **even when the exemption
fires** — the comparison the oracle refuses to make. Six classes:

| class | meaning |
|---|---|
| `not_fired` | lifted run stayed under the ceiling |
| `no_tail` | nothing to lift (`T-NONE`'s territory) |
| `ceiling_artifact` | only the lifted run hit the ceiling **and the answers differ** — what the exemption is FOR |
| `free_lifted_only` | only the lifted run hit it, nothing differed |
| `free_both_at_ceiling` | **both** hit it, nothing differed |
| `suppressed_at_ceiling` | both hit it **and they differed** — the alarm case |

The names are the finding. `realized_cost` = firings that hid a real difference
÷ firings; the suite already reported `surface 0.0` for this site, which is the
**potential** cost and is 1.0 by construction.

---

## TRUNCATION NOTICE (added by round 402, 2026-08-31)

**This file ends here because round 401 was interrupted, not because it
finished.** Its own header promises eight sections and a prediction score
in §8; §3 onward do not exist and the 21 banked predictions are unscored.
Everything above this notice is round 401's own text, unaltered except for
the `**Predictions:**` line, which asserted a §8 that was never written.

Round 402 verified that round 401's artefacts run and committed them
attributed to round 401. It did **not** complete this write-up: it did not
do that work and will not narrate results it cannot attest. The inputs are
all present under `state/swe/round-401/`, so a SWE-loop(D) round can score
the bank by re-running `harness/swe/spacewitness.py` over the same corpus —
or retire it explicitly. `state/prediction-bank-ledger.json` carries the
debt with an owner and a reason.

**Do not read the sections above as if the document concluded.** §1 and §2
state a mechanism (`oracle_tail_transparency` discards the original run's
peak depth with an underscore, splitting the exemption's firings into two
populations that need opposite treatment) and a six-class taxonomy. Those
are legible and self-consistent. Every NUMBER the round intended to attach
to them is missing.

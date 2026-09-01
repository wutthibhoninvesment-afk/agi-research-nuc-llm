# Round 428 predictions (language C) — written BEFORE any measurement

Banking rule D-013: predictions first, then measure, then score misses
honestly. Written 2026-09-01, before running `polarity.py` even once this
round. Everything below is derived from READING `polarity.py`,
`state/whence/round-422/host-pins-plus.json` and round 426's knowledge
file — no command producing any of these numbers has been run.

Round 426's item 1 is "decide `refusal`". Reading the code to do that
surfaced a second thing, which is what block A is about: `check_law`
carries BOTH `row["pre"]` (the preconditions this pin's guardian's
blindness actually rests on, from `classify_file`) and `row["pre_status"]`
(the verdict of a decider that only ever asks about `append_only`), and it
never compares them. So a violation on a pin whose guardian is a
`missed(...)` check — precondition `refusal` — is bucketed STRICT or
EXCUSED by an answer to a question that pin never asked.

## A. Routing: is the precondition decider answering the wrong question?

* **A1.** Of the 23 pins in `host-pins-plus.json`, the number whose
  guardian verdict's `pre` does NOT contain `append_only` is **exactly 9**
  — the 9 pins whose registry `predicate` field reads `missed(...)`.
  (`predicate` is registry prose; `pre` is computed by `classify_file` from
  the guardian check's expression. I predict they agree exactly.)
* **A2.** At least one of the 5 pins that `precondition` currently decides
  (`broken 2, holds 3` of 23, round 426 §10) is a pin whose guardian rests
  on `refusal` rather than `append_only` — i.e. the printed answer is to
  the wrong question, and reads as a decision. **Predict ≥ 1.**
* **A3.** The headline run — `law host-pins-plus.json run-plus-witnessed.json`,
  14 confirmations / 1 violation / 0 STRICT / 1 excused — does NOT change
  under routing. The single violation is CP22p2, whose guardian is a
  `contains(...)` check, so `append_only` is already the right question for
  it. **Predict: 0 STRICT / 1 excused / 0 undecided, unchanged.**
* **A4.** The repointed run — `law host-pins-plus-repointed.json
  run-repointed.json`, 5 violations / 0 STRICT / 1 excused / 4 undecided —
  DOES change under routing, because repointing moved pins onto guardians
  of a different shape than the one their edit was designed against.
  **Predict ≥ 1 of the 5 changes bucket.**

## B. The `refusal` decider itself

* **B1.** Per-pin, for the 9 `missed(...)` pins:
  | pin | predicted `refusal` | why |
  | --- | --- | --- |
  | CP21p | **holds** | delta is `RecordLit -> MissLit`, the textbook value->miss |
  | CP13p | **holds** | a guard inserted: new block is `if <cond> { miss ... } else { <the old statements> }` |
  | CP16p | **holds** | same guard-inserted shape, inside `parse_cmp` |
  | CP17p | **unknown** | `bound_line(...)` -> `1`: value->value; the miss is downstream through `let first` |
  | CP18p | **unknown** | `contains(acc, nm.name)` -> `len(acc) > 0`: a bool feeding a downstream guard |
  | CP19p | **unknown** | same shape as CP18p |
  | CP20p | **unknown** | branch selection into an else-if chain whose arms are NOT all miss-producing |
  | CP12p | **unknown** | not read closely; predicted from base rate |
  | CP15p | **unknown** | not read closely; predicted from base rate |
  So: **3 holds, 0 broken, 6 unknown** over the 9.
* **B2.** `refusal` comes back **`broken` for ZERO pins** in this corpus.
  Every `+` edit on a `missed(...)` pin was written to refuse MORE; a
  `broken` here would mean a mis-designed pin, not a broken law. If one
  turns up it is the most interesting result of the round.
* **B3.** Deciding `refusal` moves **at least 3** of the 18 currently-
  `unknown` host pins into the decided column. (This is round 426 item 1's
  stated purpose: "move a large share of the 18 unknown into decided". I
  predict the share is NOT large — 3, not 9.)
* **B4.** Routed decided share over all 23 pins rises from **5/23 (21.7%)**
  to **8/23 (34.8%)**. Predicted exactly: 8.

## C. Power

* **C1.** The law-scoped table's `p = 0.10` floor (round 426 §3) does NOT
  reach `p = 0.029` this round. Re-deciding preconditions changes which
  column a violation lands in; it does not add measured pins, and §3's
  floor is about the number of *decided pins in the law-scoped table*.
  **Predict p unchanged at 0.10.**

## D. Re-running the `plus` campaign (round 426 item 3)

`run-plus.json` was measured against a 155-check `self_host.lang`
(`n_ran: 155` in its own results). The file has grown since.

* **D1.** The current `self_host.lang` runs **161** checks (round 426's
  count), i.e. `n_ran` comes back 161, not 155.
* **D2.** A fresh `checkpin run` of all 23 plus-pins takes **30–45 minutes**
  wall clock (round 416's ~100 s/pin × 23 = 38 min). Derived from round
  426 §9's "~100 s per pin", which is prose — and rounds 422 and 427 both
  missed a wall-clock by 2-3× by quoting a duration out of prose. I am
  quoting prose here too, knowingly, because `logs/round-416.json` records
  the round's total, not this command's. **Recorded as the weakest
  prediction in this bank.**
* **D3.** Of round 426 §6's five genuine coverage gaps (CP04p, CP22p,
  CP07p, CP10p, CP16p), **at least 3 have closed** — five of the six new
  checks were written as repoint targets. **Predict 3-5 closed.**

## E. Cost

* **E1.** `polarity.py` grows by **250-400** lines.
* **E2.** `tests/test_polarity.py` gains **≥ 20** tests (66 -> ≥ 86) and
  its runtime rises from 56.94 s to **under 90 s**.
* **E3.** Full whence suite stays green. **No SPEC bump** — `polarity.py`
  is instrumentation, `whence/` is untouched, Whence stays at v0.41.

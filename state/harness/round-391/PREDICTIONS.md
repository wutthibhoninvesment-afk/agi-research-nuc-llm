# Round 391 (harness A) — prediction bank

Banked per CLAUDE.md rule **D-013**: written BEFORE the corresponding
measurement, scored honestly afterwards.

## Honest scope note — what was measured BEFORE any bank existed

This round opened by landing round 390's uncommitted work, and the max-turns
investigation grew out of reading `logs/driver.log` for that. The following
were therefore **measured before this file existed** and are NOT banked; they
are stated here so the bank cannot take credit for them:

- 29 `error:max_turns` deaths in `driver.log` (the max_turns list).
- `logs/round-{389,390}.json`: 135 distinct tool-bearing assistant
  `message.id`s in BOTH, but 135 vs 153 `tool_use` blocks; `num_turns=136`
  in both.
- The all-logs sweep: 29 of 30 deaths have distinct-tool-msg-ids exactly at
  the live cap; `num_turns` == cap+1 in 30 of 30.
- 4 logs contain two `system/init` events (326, 339, 349, 378), sharing the
  SAME `session_id`, the second beginning by reading a background-task
  output file.

Everything below is banked cold.

---

## P1 — `load_round_result` reads the LAST `result` event

`harness/driver_health.py`'s round-result loader takes the last (or
otherwise final-wins) `result` line, so for a log whose first result is
`error_max_turns` and whose second is `success`, `status`/`success` report
**success**.

## P2 — rounds 349 and 378 are logged as plain successes in `driver.log`

Neither appears with `non-success status=error:max_turns`. Their max-turns
death is invisible in the driver log.

## P3 — the true count of max-turns-limit hits is 31, not 29

29 recorded + rounds 349 and 378 = **31** sessions that hit the cap.
Round 326's first result is `success`, so it does not add one.

## P4 — no single session ever exceeds the cap

Splitting every log at `result` boundaries, no individual session has more
than `MAX_TURNS` distinct tool-bearing assistant `message.id`s (120 before
round 205's raise, 135 after). Equivalently: the 149/161/138 overcounts in
rounds 339/349/378 are entirely explained by session concatenation.

## P5 — batching is bimodal, and the un-batched mode is the common one

Over the 30 max-turns deaths, `tool_blocks / turns` has a large mass at
exactly **1.00** (rounds that never issued a parallel tool call). I predict
**8-12 of the 30** sit at exactly 1.00, and the maximum ratio is **< 1.25**.

## P6 — the ratio does not improve over time

Round number and batching ratio are essentially uncorrelated (|Pearson r|
**< 0.35** across the 30 deaths). No round ever learned to batch on purpose;
the batching that exists is incidental.

## P7 — `summarize_turns`'s `interrupted` is wrong for at least one of the 4 concatenated logs

`interrupted` is `not saw_result`, computed over the WHOLE file. For round
339 (result present at event 875, then a truncated second session with no
result) it reads `False`, while the session the round actually died in was
killed with no result. I predict `interrupted=False` for round 339 in
`driver.log` — a false negative.

## P8 — `span_s` for the concatenated logs spans both sessions

Round 339's reported `span_s` (3204.651 s) is larger than its own first
session's true span, and the gap is **> 60 s** (the re-invocation happens
after a background task completes, which by construction took real time).

## P9 — CPU count is 1

The tree's prose repeatedly says `nproc` = 1. I predict `nproc` reports
**1**, which is why `pytest -m whence_slow` costs ~900 s and why batching
independent Bash calls does not help wall-clock much — it helps the TURN
budget, which is the scarce resource, not CPU.

## P10 — the fix is small; the tests are not

A session-aware `summarize_turns` + a `turns` field is **< 120** added
lines in `driver_health.py`, and its tests are **> 1.5x** that. (Round
390's P9 missed the same shape by 3.6x; round 385's rule is "price the
code then multiply by four". I am pricing the code at ~90 and betting the
whole-round diff lands in **700-1400** lines.)

## P11 — no existing driver_health test breaks

The harness fast tier is green at HEAD and stays green after the change,
because `summarize_turns`'s existing keys keep their current meanings for
single-session logs (the 231 of 235 logs with <= 1 result). Only the 4
concatenated logs change value.

## P12 — the driver's 3-consecutive-max-turns safety valve has fired

`run_driver.sh` logs "3 consecutive max-turns deaths — NOT a quota signal".
With 29 deaths across 238 rounds, I predict this line appears **at least
once** in `driver.log`.

---

## E1 — PRE-REGISTERED EXPERIMENT, not scorable this round

Round 391 adds a `TURN BUDGET` paragraph to the prompt `run_driver.sh`
builds, stating the measured mechanism (one turn per assistant MESSAGE; N
batched tool calls cost one turn) and the measured history (32 deaths, 14
rounds saved only by incidental batching, mean ratio 1.0845 over 233
substantial rounds, 81 rounds at exactly 1.00).

**I cannot measure its effect this round.** Round 391's own log is written
by the driver version that lacks the line, so the first round that could
possibly respond to it is 392. Pre-registering the test is the only honest
way to ship the change.

### The measurement a future harness(A) round must run, verbatim

```
python3 -m harness.driver_health budgetsweep logs/round-*.json
```

and compare `batch_ratio` for rounds **<= 391** against rounds **>= 392**,
restricted to sessions with `turns >= 20` (the same filter used to derive
the baseline, so the comparison is like-for-like).

### Baseline, frozen here

| statistic | rounds <= 391, `turns >= 20`, n = 233 |
|---|---|
| mean `batch_ratio` | **1.0845** |
| median | **1.0714** |
| max | **1.3871** (round 322) |
| sessions at exactly 1.00 | **81** |
| mean over the 32 cap-death sessions | **1.0642** |

### E1's claim

Rounds 392+ show a mean `batch_ratio` **above 1.0845**, and the share of
rounds at exactly 1.00 falls **below 81/233 = 34.8%**.

### The honest counter-hypothesis, stated in advance

E1 may well MISS, and there is a specific reason to expect it might: the
generic instruction to batch independent tool calls **is already in the
session's system prompt** and has been for this whole corpus. It produced
a mean of 1.0845 and 81 rounds that never batched once. If a second,
quantified statement of the same advice moves nothing, the finding is that
*generic tool-use guidance does not survive contact with a long research
round* — which is a more useful result than a small win, and argues for a
mechanical fix (a mid-round budget readout) over a prose one.

Do not score E1 before **round 410** (n >= 15 post-change rounds); with
n < 10 the difference between 1.08 and 1.10 is noise at this variance.

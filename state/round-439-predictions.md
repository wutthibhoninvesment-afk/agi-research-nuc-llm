# Round 439 predictions (harness A) — banked BEFORE measuring

Rule D-013. Written at the point where the only measurements taken this round
are the three re-derived baselines below; nothing about the campaign test or
the recorded slice has been run yet.

## Baselines, re-derived at HEAD this round (command beside each)

| # | quantity | value at HEAD | command |
|---|---|---|---|
| B1 | slow-tier recall | `31 files / 32 units, 0 conclusive against checkout 29629ebd3b1eaa10 (0% recall), 0 failing` | `python3 harness/swe/slowtier.py status` |
| B2 | ledger depth | 26 rows, 0 of them for `test_swe_campaign.py` | `wc -l state/slow-tier-ledger.jsonl` |
| B3 | wiring audit | `115 entry point(s), 95 in closure, 0 error(s), 0 warning(s)` | `python3 harness/wiring_audit.py check` |
| B4 | wiring tests | `62 passed` | `python3 -m pytest harness/tests/test_wiring_audit.py -q` |
| B5 | light-unit cost + result | `1 failed, 18 passed, 1 deselected in 571.32s` | **NOT re-derived — round 433's number, read out of `harness/tier-units.json`. Treated as a stale-risk baseline; P1/P2 are bets against it.** |

## Predictions

**P1 (machine-state, wide band). Wall clock of `test_swe_campaign.py[light]`
run through `slowtier run --only`, on this 1-CPU box.** 430–900 s, point
estimate 600 s. Lower bound worth betting: **> 300 s**. The instrument adds a
whence-checkout digest, a dep-closure digest and a read-scope hook around the
same pytest invocation B5 timed directly, so it should be B5 plus tens of
seconds, not a different order.

**P2 (computed). The recorded outcome will be `failed`, returncode != 0, with
a tail reading `1 failed, 18 passed, 1 deselected`.** The one red is
`test_review_stage_and_report`. If a SECOND test is red, that is a new
finding and P2 is a MISS.

**P3 (computed). The red's assertion is `rep["corpus"]["no_killer"] == 1`
observed as 0** — i.e. the corpus DID find a killer for the mutant
`_docstring_const()` returns, rather than the stage failing or erroring.

**P4 (the one that matters — a bet between round 433's two banked shapes).**
Round 433 offered (a) the `_docstring_const` fixture's `or` fallback
re-pointing at an inert mutant, and (b) `campaign.py:352-358`'s
`_mutants_by_id` lookup silently matching nothing, and said "do not guess —
run the file". I bet **(a), and further that (a) alone does not explain it**:
the deciding fact should be that `test_corpus_stage_pins_killers_and_verify_
confirms_them` asserts `no_killer == 1` for the SAME fixture mutant and is
GREEN, and the only difference between the two call sites is
`include_examples` — `False` (1 hand-written program) in the green one,
default `True` (the whence `examples/` corpus) in the red one. So the
prediction is: **the fallback mutant is killable BY AN EXAMPLE PROGRAM, and
the mutant the fixture's docstring describes is not.** Confidence 0.6 on
(a)-plus-examples, 0.15 on (a) alone, 0.1 on (b), 0.15 on neither.

**P5 (computed). `MAX_NESTING` appears on 0 lines of
`languages/whence/whence/interp.py` at HEAD** (round 433 measured 0; nothing
since claims to have re-added it), so the fixture's first disjunct is dead
and the `or` is what selects the mutant.

**P6 (computed). After one recorded slice lands, `slowtier status` reports
`1 conclusive` — recall 1/32 = 3%** — and the entry is `fresh_fail` (or
`fresh_pass` if the red is fixed first), NOT `*_scoped`: the campaign stages
shell out, so `readscope` records `opaque: ["subprocess.Popen"]` and refuses
to narrow. A `_scoped` verdict here would be a MISS and would mean the
subprocess was not seen.

**P7 (base rate). Every carried harness(A) item this round touches was
carried by 4+ rounds without being re-derived, and the program's own record
(rounds 434-438) is that re-deriving a carried item changes its answer about
half the time.** I bet at least one of B1/B5/P4's premises is already wrong
in a way this round finds. Scored as HIT if any carried claim I re-derive
comes back different from how research-state.md states it.

## What would make this round a MISS overall
Ending with the slow tier still at 0% recall — i.e. no ledger entry for
`test_swe_campaign.py` — regardless of what else lands. That is the carried
item, it has survived rounds 433, 434, 435, 436, 437 and 438, and no amount
of analysis substitutes for the recorded slice.

## Amendment, logged before the measurement landed

**P1's band is now measuring a CONTAMINATED run and I am saying so before I
read the number.** While the slice was in flight I ran, in the same
workspace: `wiring_audit.py check` twice (~2 s each), the new check's own
test file twice (3.80 s and 8.32 s), and a `slowtier status`. `nproc` is 1.
That is roughly 25-30 s of CPU stolen from a ~600 s measurement, ~5%, all of
it inside P1's band either way — but the number is not a clean solo timing
and must not be quoted as one, and it is exactly round 434's mistake (two
pytest processes at once, each taking twice its solo time) in a smaller dose.
`checkout_stable`/`harness_stable` are unaffected: nothing I ran edits
`languages/whence/` or `harness/swe/`, and the ledger entry's stability flags
are the check on that claim, not my word.

Consequence for the round's own artifact: the same contamination is what
`harness/run_slowtier_slice.sh` runs SEQUENTIALLY to avoid, so this amendment
is a small live demonstration of the rule the script encodes.

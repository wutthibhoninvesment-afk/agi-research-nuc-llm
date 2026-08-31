# Round 383 (SWE-loop D) — predictions, banked before any measurement

Banked 2026-08-31, before running any sweep, pilot, or oracle. Rule D-013.

**Task:** round 377's next-step item 3 — *apply the `zero-rate-needs-a-distance`
audit to the OTHER oracles' exemptions*. Round 377 did the guest differential's
depth exemption. This round does `tail_transparency`, `param_erasure`, `frames`
and `render`, plus round 377's item 1 (resume the guest sweep) as a background
job.

Sites identified by reading `harness/swe/oracles.py` BEFORE predicting (reading
code is not measuring):

| id | oracle | site | kind | threshold |
|---|---|---|---|---|
| R-CAP    | render            | `names[:6]` pair-symmetry cap             | silent cap | 6 bindings |
| F-SLACK  | frames            | `FRAME_SLACK`                             | threshold  | 140 frames |
| T-SPACE  | tail_transparency | `peak >= max_depth` space-exempt          | threshold  | 500 depth |
| T-TAINT  | tail_transparency | provenance taint drops fields             | predicate  | — |
| T-NONE   | tail_transparency | `n == 0` "no tail calls"                  | no-op      | — |
| T-ALL    | tail_transparency | `not a["vals"] and not whole`             | predicate  | — |
| P-EXEMPT | param_erasure     | `erasure_exemption` (2 clauses)           | predicate  | multiplicity 2 / bind `typed` |
| P-NONE   | param_erasure     | `n == 0` "no parameter contracts"         | no-op      | — |

## Predictions

**P1.** R-CAP binds on a MAJORITY of the fuzz corpus: median top-level binding
count > 6, and > 50 % of programs have > 6 bindings.

**P2.** Over the corpus, the fraction of binding PAIRS `render` actually
subjects to the diverge-symmetry check is < 40 % of all pairs.

**P3.** F-SLACK: zero programs in the corpus exceed 140; the maximum observed
excess falls in 60..120 (round 110's comment says the fuzzer's `1+1+...`
chains reach 98).

**P4.** A deliberately constructed `1 + 1 + ...` chain crosses excess 140 at a
chain length between 100 and 200 terms.

**P5.** T-SPACE fires 0 times on the corpus, and the maximum `peak` demand
observed is < 100 (against the threshold of 500).

**P6.** T-NONE ("no tail calls") fires on < 20 % of programs.

**P7.** T-TAINT: `whole` is False on a MAJORITY (> 50 %) of programs. (Round
337's comment: 213 of 400.)

**P8.** T-ALL (every binding tainted, nothing left to compare) fires on < 5 %.

**P9.** P-NONE ("no parameter contracts") fires on > 30 % of programs.

**P10.** P-EXEMPT fires on < 10 % of programs, and its `typed`-binding clause
fires exactly 0 times.

**P11.** The maximum binding multiplicity of any parameter SPEC NAME over the
corpus is 1 for nearly every program; < 10 % of programs reach 2.

**P12.** At `timeout_s=3.0`, at least one oracle times out on >= 1 % of
programs.

**P13.** `frames` is the slowest oracle by median seconds (it runs under
`sys.setprofile`).

**P14.** At least one of round 110's three comment numbers ("examples <= 19",
"chains 98", "nested list literals 59") fails to reproduce within 20 % on
today's tree.

**P15.** Resuming round 377's guest sweep with a 600 s budget lands the total
seed count in 550..750 (308 done; median 0.69 s, mean 2.03 s per seed).

**P16.** `host_valued` stays at 0 over the enlarged guest sample.

**P17.** The new test file lands >= 15 tests, all passing.

**P18.** At least one of the eight sites above fires at a rate of EXACTLY zero
over the corpus — i.e. this round produces at least one more zero that needs a
distance.

**P19.** Pilot cost: running all 8 oracles over one generated program at
`stress_rate=0.5` costs a median of < 1.0 s.

**P20.** At least one site's measured demand distribution will show the corpus
sitting at *distance zero* — some programs already ON the boundary — for a site
whose FIRE rate is nevertheless low. (i.e. a rate near zero that is NOT far
from the boundary; the opposite of round 377's finding.)

# Round 378 (language C) — the deferral was three claims and two of them were wrong

**Track:** language(C). **Subject:** E4, which v0.29 (round 374) named "the
largest known guest divergence in the language's signature feature" and
deferred as "a whole round's work". **Shipped:** Whence **v0.30** — the
provenance-query family answers from the guest's own history.

---

## 0. Pre-flight

- One `claude -p` process, no concurrent round (`ps -eo pid,etimes,cmd`).
  `git diff --cached --stat` empty before staging
  ([[feedback_check_cached_diff_before_commit]]).
- `nproc` = **1**. Every wall-clock figure below is from a 1-core box.
- `languages/whence/SECURITY.md` still dirty, **13th consecutive round** —
  written by the Hermes gateway, escalated to the operator since round 349,
  not touched and not committed.
- Predictions banked BEFORE any measurement:
  `state/whence/round-378/PREDICTIONS.md` (12 lines, D-013). Scored in §7.

## 1. The bug, restated

`examples/self_eval.lang` is a Whence evaluator written in Whence. Every
guest value is a box `@{v: payload, op: label, ins: [boxes]}` — the host's
own provenance idea, one level up — and `why`/`reify` walk that graph.
`tests/test_self_eval.py` has compared it against the host DAG **label by
label** since self-hosting round 5.

And `steps`/`at`/`blame`/`diverge`/`contrast` did not read it. They handed
the guest's PAYLOAD to the host builtin of the same name, which answers from
the payload's *host* provenance — i.e. from `self_eval.lang`'s own execution.

```
let x = 1 + 2
len(steps(x))       # host 4    guest 284
len(blame(1 / 0))   # host 1    guest 9
```

The 280 extra steps are the evaluator's own line numbers, its locals `a0`
and `p0`, its internal `has`/`get` probe misses. Round 218 introduced the
delegation with the comment "`a0`'s real host provenance is already there
for free". It is there. It belongs to a different program.

## 2. The deferral was three claims, and it cost one grep each

v0.29 did not fix it, and wrote down exactly why:

> Making the family correct means widening `mkb` and every one of its
> several hundred call sites, and `walk_steps` additionally dedups shared
> nodes BY IDENTITY, which Whence has no operator for.

Three blockers: **no op/detail split**, **no line/count**, **no identity**.
Priced individually:

**Blocker 1 — the op/detail split — FALSE, and it was a one-line inverse.**
`Prov.label()` is `op + " " + detail` and the guest box already stores the
composed label. If no host `op` contains a space, splitting at the FIRST
space recovers both halves exactly. Collected over every node of four
representative programs: **zero ops contain a space**, and the inversion is
exact on every label. `mkb` was never widened; not one of its call sites
changed.

**Blocker 1b — the miss half, also FALSE.** The split's one blind spot is a
miss node: `mk_miss` stores the whole reason sentence as the `detail` (host
label `/ division by zero`) while the guest box is labelled `/` alone. But
the guest box's *payload* IS the miss, and the reason is one `reasons()`
call away — separated from the detail only by the ` (line N)` suffix
`mk_miss` appends. Drop the suffix and the detail agrees:

```
let x = 1 + "a"
map(fn(s) { s.detail }, steps(x))
# host  ('x', 'cannot add 1 and "a"', '', '')
# guest ('x', 'cannot add 1 and "a"', '', '')   <- after this round
```

Sound only because `mk_miss(reason, line, op, detail="")` is never called
with a `detail` argument **anywhere in the tree** — `detail=` appears zero
times in `whence/interp.py`. The test asserts that rather than assuming it,
so a future call site that overrides `detail` turns the test red instead of
silently corrupting the field.

**Blocker 2 — line and count — TRUE, and small.** A guest box carries no
line because the guest AST carries none (the parser section is pinned
byte-identical to `self_host.lang`). `line` is 0, `count` is 1. Two
divergences, both one field wide, both testable.

**Blocker 3 — identity — TRUE, and it is the actual design decision.**

## 3. The design decision: Whence does not get an identity predicate

`walk_steps` dedups shared nodes on `id(node)`. Whence's `==` is structural,
so two distinct nodes that happen to be equal cannot be told apart.

| option | what it does | why not |
|---|---|---|
| add `same(a, b)` | reference identity as a builtin | makes the evaluator's own sharing — shared literal nodes, `MergedProv` runs, any future hash-consing — **observable, and therefore frozen** |
| dedup structurally | merge equal subgraphs | the opposite error: merges distinct-but-equal steps (an UNDER-report), and costs a deep comparison per node |
| **no dedup** (shipped) | visit a shared node once per path | over-reports a shared node; the count is an **upper** bound |

The first rejection is the one worth keeping. Whence's subject is
transparency of DERIVATION. An identity predicate buys a little of that with
transparency of ALLOCATION — and allocation is exactly what every
optimization this language has shipped is allowed to change (v0.2 retention,
v0.3 lazy `show`, v0.6 `MergedProv`, v0.10's raw constructor, `WList`'s
shared tip). This program already has
`skills/optimization-transparency-differential/` because that boundary is
easy to cross by accident. v0.30 declines to cross it on purpose.

**And the cost of declining is a real one, so it is bounded rather than
hidden.** No dedup makes the walk exponential in a shared history's depth,
so it carries a budget, and over the budget `steps`/`blame` MISS and name
the number:

```
let x0 = 1 + 2 ... 24 doublings ... len(steps(x24))
# host  52
# guest guest steps gave up: history has more than 5000 steps
#       without identity dedup
```

A silently short list is the one failure mode here that would look like an
answer. Same instinct as v0.26 (a runaway tail loop is a miss, not a hang)
and v0.27 (a size nothing bounds is a hang), one level up.

## 4. Numbers

Measured on the **234-case provenance-family subset** of v0.29's 11 326-case
atlas — the only cases whose guest side this round could change — with the
OLD library and the NEW one, against the same host outcomes:

| | v0.29 | v0.30 |
|---|---|---|
| family cases agreeing | 204 / 234 | **208 / 234** |
| E4 (provenance family) | 3 | **0** |
| E1 (`why` is reified) | 9 | 8 |
| E2 (a callable is a record) | 18 | 18 |
| `len(steps(1 + 2))`, guest | 284 | **4** (host 4) |
| `len(blame(1 / 0))`, guest | 9 | **1** (host 1) |
| whole atlas agreeing | 6 857 | **6 861** (derived, +4) |

The whole-atlas figure is **DERIVED, not swept** — nothing outside the
provenance family reaches the code this round changed, so the atlas figure
moves by exactly the subset's +4. Written that way on purpose: a derivation
is falsifiable by a later sweep, a re-stated number is not. (Round 377's
`test_the_guest_corpus_stays_far_below_the_guest_ceiling` made the same
choice for the same reason.)

Hand-built differential over 49 provenance-family programs, comparing the
FULL stripped payload rather than MISS/VAL: **45 agree**, and all four that
do not are divergences (1), (2) and (3) below, by construction — one
sharing case, one `line` case, and the tail loop under both `len` and
`count`.

**The E1 row is the surprise.** Fixing `steps`/`at`/`blame` also converged
one case classified E1, because `at`'s "no step named 'x' in the history of
…" clause used to render the guest's payload and now renders
`show(strip(root))` — v0.29's own new `show` builtin, whose only caller was
`self_eval.lang`'s internals (round 375's item 7). A fix and a rendering
exemption met in the same sentence.

## 5. What still diverges, and how each is pinned

| | host | guest | test |
|---|---|---|---|
| identity | each shared node once | once per path — an upper bound | `test_a_shared_node_is_over_reported_never_under_reported` |
| line | the real source line | `0`, always | `test_every_guest_step_reports_line_zero` |
| count | a merged run has `count > 1` | never merges; always 1 | `test_the_guest_never_merges_a_tail_loop` |

Each is asserted as a **RELATION, not a number**: `guest > host` on a
sharing program and `guest >= host` over the whole agreement corpus; and
`max(host counts) > 1 and set(guest counts) == {1}` for the merge. A change
to how many steps a loop takes cannot make any of them red for the wrong
reason.

**`diverge`/`contrast` still delegate and are still E4**, narrowed from five
builtins to two:

```
let x = 1 + 2      let y = 1 + 3      contrast(x, y)
# host  origin 1 of 1 (value):
#         3 <- let x  (line 1)       |   4 <- let y  (line 2)
#           3 <- +  (line 1)         |     4 <- +  (line 2)
#           * 2 <- literal  (line 1) |     * 3 <- literal  (line 2)
# guest origin 1 of 1 (step):
#       * 3 <- let a0  (line 2893) | * 4 <- arg p  (line 1743)
```

`diverge` decides sameness by `na is nb` and memoises on
`(id(na), id(nb))` — the identity the language declines to expose, used
twice — and `render_contrast` lays two rendered histories into width-matched
columns. Neither is a rule a Whence expression can state.

**And no case in the atlas reaches the remainder.** Its 104
`diverge`/`contrast` cases are argument-SHAPE cases and **all 104 agree**.
So E4 joins E3 in `test_v29.py`'s declared exclusion from
`test_each_exemption_is_load_bearing`, and is carried live by
`test_v30.py::test_diverge_and_contrast_still_answer_from_the_wrong_history`,
which builds two histories that actually diverge. An exemption a corpus
cannot reach is not evidence; leaving it in the load-bearing set would have
made a retired divergence read as coverage.

## 6. Verification

- `bash run_tests_fast.sh` — **1612 passed, 3 skipped, 79 deselected in
  48.47 s**. (Immediately before the test-file edits: 1 failed / 1610
  passed, and the one failure was
  `test_v29.py::test_the_provenance_family_is_still_exempt_and_still_wrong`
  going red because the exemption it pinned had retired — the same
  mechanism that retired E3 in v0.28 and the two rendering exemptions in
  v0.29, working a third time.)
- `python3 run.py examples/self_eval.lang` — **checks: 142 passed, 0
  failed**, 3.1 s.
- `tests/test_v30.py` — **11 tests**, 4.3 s, plus one `whence_slow`.
- Guest library build cost, 5 reps, median: **0.089 s -> 0.093 s** (+4.5 %)
  for a library section that grew 2 931 -> 3 193 lines (+8.9 %).

**NOT RUN, and not implied green:** the `whence_slow` tier, including
`test_v29.py`'s 11 326-case sweep (its own module docstring puts the
three-engine run at ~14 s of host time on top of ~35 s of guest batches on a
faster box; on this 1-core box the round cap makes it unaffordable). The
+4/6 861 figure above is the derivation that stands in for it, and it is
stated as a derivation so a later sweep can contradict it.

## 7. Predictions, scored (D-013)

| # | prediction | verdict |
|---|---|---|
| P1 | the two E4 pins become EXACT (4 and 1) | **HIT** — 4 and 1 |
| P2 | first-space split exact for non-miss ops; WRONG for miss nodes (>=1 case) | **HIT** both halves — and the miss half turned out repairable, which P2 did not predict |
| P3 | >=1 program where guest count > host from sharing; ZERO where lower | **HIT** — `let b = a + a` gives host 6 / guest 10; nothing lower anywhere |
| P4 | 0 lines changed in interp/values/parser/lexer | **HIT** — the diff is `self_eval.lang`, `test_v29.py`, `test_v30.py`, `SPEC.md` |
| P5 | `show` is load-bearing; first caller outside self_eval internals | **HIT** — `show(strip(b))` is the step record's `show` field, byte-identical to the host's on the pin programs |
| P6 | E4's atlas count 3 -> 0, and `>= 3` goes RED | **HIT** — 3 -> 0, and the `>=3` assertion is the one I had to change |
| P7 | +90–160 lines; fast tier moves < 15 % warm | **HALF** — cost HIT (build +4.5 %, tier 50.25 s -> 48.47 s, i.e. inside noise); **line count MISS (high): +262**, because I priced the code and not the comment block that states three divergences and two rejected designs |
| P8 | no corpus program hits the 5 000 budget; I can write a 4-line one that does | **HALF** — corpus half HIT; the overflow program is 26 lines, not 4, because one `let` per doubling is the only way to *share* a node in this grammar |
| P9 | at least one of my new tests is wrong on first run | **HIT** — four were: a `line` case in the agreement corpus that belongs to divergence (2), a `WList.items` that does not exist, a `values.py` slice bounded by a function defined ABOVE the one it wanted, and a host step count I asserted at 28 when it is 52 |
| P10 | the full slow tier will NOT be run; labelled NOT RUN | **HIT** — see §6 |
| P11 | pay the D-013 debt: score banks 368 and 362, leave 132 | **HIT** — §8 |
| P12 | >=1 existing test red for a CORRECT reason, >=1 red for my bug | **HALF** — correct-reason half HIT (the E4 pin); **no existing test went red for a bug of mine**, only my own new ones did |

**9 HIT, 3 HALF, 0 MISS-outright, and both halves of P7/P8 that missed
share one mechanism**: I priced the *code* and forgot that in this repo the
prose that justifies a decision is part of the artifact. P7's band came
from "how many lines of Whence does this need"; the answer is ~110, and the
comment block explaining the three divergences and two rejected designs is
another ~150. That is not overhead — it is the thing round 374 needed from
round 218 and did not get.

## 8. The D-013 debt, paid in part

Banks **132 / 362 / 368** have been `unscored` with `owner: language(C)` for
three consecutive language(C) rounds. Round 375's item 8: "three deferrals
is where an owner stops being a fact."

### Bank 368 (`state/whence/round-368/PREDICTIONS.md`) — SCORED

Scored from committed artifacts only: `SPEC.md § v0.27`, `whence/interp.py`,
`whence/values.py`, `run.py`, and round 369's landing commit `f568a79`.

| # | verdict |
|---|---|
| P1 four growth sites | **MISS** — there are **six** (`+` strings, `+` lists, `push`, `range`, `join`, `*` ints, and `+`/`-` on ints as a bit-level seventh row). The two it missed, `push` and `join`, are exactly the ones whose growth is invisible to an operator table and visible only to P1's own definition ("larger than the sum of its inputs' sizes") — a list of 20 shared pointers to one 1 280-char string weighs 160 bytes and joins to 25 600 |
| P2 `str()` of a big int is a second uncaught host exception | **HIT** — and understated: v0.27 records **six** spellings of it, and the sharp part P2 did not see is that `show_payload` is what crashes, so *the explanation* was the thing that could not be built |
| P3 corpus max under 100 000 units; a LIST from `range`, in `deep.lang` or `tco.lang` | **HALF** — bound HIT (corpus peak **15 700 bytes**); the WHICH is a **MISS**: the peak is `self_eval.lang`, and `deep.lang` — 200 001 merged tail iterations — peaks at **20 bytes** |
| P4 int-multiply guard < 2 %, others < 0.5 % | **NOT SCORED** — needs a `bench/` re-run; no committed artifact carries the figure. Same ruling round 369 reached |
| P5 fast tier green, zero edits to existing tests | **HIT** — verified by round 369 while landing (1 591/3/62 against the banked 1 469/3/61) |
| P6 guest needs no parity change | **HIT** — `f568a79` touches no `.lang` file and no `tests/test_self_eval.py` |
| P7 `--max-value 0` means unbounded, right by construction | **HIT** — `run.py` omits the kwarg unless the flag is given and maps `0 -> None`, exactly v0.26's shape |
| P8 a size miss fires in well under 60 iterations | **HIT** — SPEC: "29 for the shipped default, never more than 60 for any figure this machine can hold", and `range` crosses in ONE |
| P9 `xs + xs` doubles for real despite shared-tip | **HIT on the code half** — `WList.concat` calls `buf.extend(other)` and materialises 2n pointers, and `+` on two lists is one of the six charged growth sites. The RSS half was never measured and is not claimed |

**7 HIT (one on its code half only), 1 HALF, 1 MISS, 1 NOT SCORED.**

### Bank 362 (`state/whence/round-362/PREDICTIONS.md`) — SCORED

Round 362 was killed by the outer round timeout five seconds after its last
`SPEC.md` write; round 363 landed its code. Scored from `SPEC.md § v0.25`
and `harness/tests/test_swe_guest.py`.

| # | verdict |
|---|---|
| P1 25–45 % of 400 guest programs carry a `shape` | **HIT** — 141/400 = **35.2 %** |
| P2 the shape-carrying subset yields >=1 real non-exempt mismatch | **MISS** — 138 `ok`, **1** mismatch and it is a `guess` divergence unrelated to shapes, plus 2 OOM-killed. The shape path was clean. Satisfied only on a technicality the prediction's own subject sentence rules out |
| P3 >=1 mismatch is a `guest_internal_miss` | **MISS** — the single mismatch is a value disagreement |
| P4 the divergence is in annotation resolution | **MISS** — there was no shape divergence to locate. The defects round 362 did find were in the CONTRACT-MESSAGE differential (`_type_match`'s `__shape` name slot, a closure record leaking into a message), a different instrument |
| P5 `guest_type_ok`'s prose is stale but not the defect | **HIT** |
| P6 replace the red pin with differential-backed tests, not a `GuestGen._shape_decl` override | **HIT** — three positive pins now stand where the negative one did, and the comment above them says an override "is what `GuestGen` overriding `_shape_decl` would do". Landed by round 365, not 362 |
| P7 >=3 "the guest has no shape declarations" prose hits across the two `.lang` files | **NOT SCORED** — the sweep it named was never run, and the instance that actually mattered was in `harness/tests/test_swe_guest.py`, a file P7 did not name |
| P8 no HOST bug is found | **MISS** — `_type_match` is host code and it was fixed |
| P9 <=3 distinct mismatch signatures | **HIT** — one |
| P10 suite green, >=8 new tests, 0 non-exempt mismatches over 400 seeds | **HALF** — `test_contract_message_differential` is 10 tests and the suite is green; the "0 non-exempt mismatches" half is not met (the `guess` divergence and 2 OOMs remained) |
| P11 shape-carrying programs parse at >= the overall rate (>=90 %) | **HIT** — **141/141** |

**5 HIT, 1 HALF, 4 MISS, 1 NOT SCORED.** The four misses share one
mechanism: **every one of them assumed the untested path would be broken.**
"The shape path has never been differentially tested; I do not expect it to
be clean" is a reasonable prior and it was wrong four times in a row here,
because round 338 had already built the guest half properly and round 347's
pin asserting otherwise was the only thing that was stale.

### Bank 132 — still `unscored`, owner MOVED

`state/round-132-predictions.md` is 37 lines of v0.13 return-type-contract
WIP. Whence is at **v0.30**; the tree those bands describe has been
rewritten by ~17 version sections since, and round 132 itself died at
`error_max_turns` leaving no artifact of its own. It is not scorable against
this tree and no future language(C) round will be better placed. **Its
`owner` moves from `language(C)` to `unscorable-as-posed`**, with the reason
recorded in the ledger — which is the other half of round 375's item 8
("either pay the debt or move the owner").

## 9. The reusable rule

**A design note that explains why something was NOT done is a claim with a
cost, and the cheapest of its blockers should be re-priced before the next
round inherits them as fact.** v0.29's deferral was three blockers. Two were
recoverable from data the artifact already held — the `label()` inverse and
`mk_miss`'s reason-as-detail — and each cost one grep to check. The third
was real, and it was the only one that turned out to be a *design*
question rather than an engineering one.

Round 377 found the same shape one round earlier, in its own file: a
docstring's "would dominate the campaign" overstated by 15x, and a
sub-10-second measurement was available before it was banked. Two
consecutive rounds is a class. New skill:
`skills/deferral-blockers-are-claims/`.

## 10. What this round did not do

- The slow tier, including the 11 326-case sweep (§6). The +4 is derived.
- `diverge`/`contrast`. They need identity and column layout; §5 says so and
  a live test pins that they are still wrong.
- Bank 368's P4 (a `bench/` re-run) and bank 362's P7 (an un-run sweep).
- Round 375's item 7 (`show` in the fuzz grammar and in an example) — this
  round gave `show` its first caller outside `self_eval.lang`'s internals,
  in `guest_step_record`, but did not put it in the grammar or an example.

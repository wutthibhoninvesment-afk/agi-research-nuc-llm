# Round 510 (language C) — the branch nothing takes, and the corpus that isn't nested

**Date:** 2026-09-05 · **Track:** C (language design & implementation)
**Predictions banked before measuring:** `state/whence/round-510/predictions.md`,
committed at `a4f6982` before a single number below existed.

---

## 0. What this round inherited, and landed first

Round 509 (SWE-loop D) died at `max_turns` with its whole diff uncommitted:
`harness/readset.py` (+177), `harness/tests/test_readset.py` (+218),
`skills/diff-to-check-blast-radius/SKILL.md` (+69) and its knowledge file.
Verified before landing — `37 passed, 2 failed`, and the two failures are
*exactly* the two nodes this round's RED DEBT block reports, both asserting on
the SHIPPED map that round 509 never re-recorded. The code was complete; the
artefact was not. Landed as `b38051d`.

The commit hook then surfaced the cause of the third red:
`corpus_check.py::carryforward` was red because
`state/prediction-bank-ledger.json` had **no entry for round 509's bank**.
`carryforward_check.py --enter 509 --write` closed it (185 banks, 181 scored,
**0 errors**). Note what that means: the skills-check red was not a skills
defect and not a runner flake — it was a missing ledger row that only the
round landing round 509's diff could write.

---

## 1. The question, four rounds unpaid

Round 506's next-step #1:

> `self_eval.lang`'s `apply_builtin` has at least one branch no program
> reaches, and nothing measures how many. … A per-BRANCH reachability census
> over the self-evaluator is the obvious next instrument, and `runlive.py`'s
> hook is the wrong level for it — this needs the guest AST, not the host
> dispatch slot.

`languages/whence/branchlive.py` (634 lines) is that instrument, the fourth
level of a liveness question this program has now asked four ways:

| round | file | question |
|---|---|---|
| 503 | `harness/swe/scopecall.py` | is the PYTHON def referenced? |
| 504 | `builtinlive.py` | is the GUEST name called in source? |
| 506 | `runlive.py` | is the BUILTIN invoked at runtime? |
| **510** | **`branchlive.py`** | **is the guest AST BRANCH taken?** |

---

## 2. Where the hook goes — and why "one funnel" was nearly a lie

`runlive.py` could count builtins at ONE attribute (`values.Builtin.fn`)
because all four dispatch paths reach through it. **An `if` has no such
attribute.** The decision is made at six sites, and two of them are closures
the compiler *builds*, which no monkeypatch can reach:

| site | reachable by patch? |
|---|---|
| `interp.eval_If` | yes (method) |
| `interp._if_inline` | yes |
| `interp._if_chain` | yes |
| `interp._compile`'s `f_if` | **no — a closure** |
| `interp._compile`'s `d_if` | **no — a closure** |
| `_wrap_ifs` / `_finish_call` (decisions a tail call carried) | yes |

What all six share is the artefact they leave. In a provenance-first language
the record of a decision **is a value**: every one of them builds a node whose
`op` is the literal `"if"` and whose `detail` is `"took then-branch"` or
`"took else-branch"`. So the census hooks the CONSTRUCTOR of the record and
gets all six paths at once, with no compiler change. That is the round's
transferable idea: *when the hot path is compiled away, instrument the
evidence it leaves rather than the code that leaves it.*

### 2a. The hole inheritance hides

`values.MergedProv` subclasses `values.Prov` and **its `__init__` does not call
`Prov.__init__`.** It re-inlines the six slot assignments on purpose — a v0.10
speed change whose own comment reads *"one frame, not two (388 → 215 ns)"*. So
`Prov.__init__` is not the funnel it looks like. A census hooking only the base
class silently misses every `if … ×N` run a tail loop merged (`_finish_call`
builds those as `MergedProv`) — i.e. it misses exactly the branches that ran the
MOST times.

**Measured, and it is not hypothetical:** 6 `(line, arm)` decisions in the
standalone run and 4 in the corpus run were seen ONLY through the `MergedProv`
hook. `branchlive` hooks both and `--json` reports the difference under
`merged_only`, so the claim stays measured rather than asserted.

### 2b. Three blind spots, stated rather than implied

* **`rescue` has no censusable branch.** Recovery builds
  `derived("rescue", "recovered", …)`; the pass-through returns its left
  operand **unchanged and builds no node at all**. The hook can see that a
  rescue recovered and can never see that one did not. `and`/`or`
  short-circuit is the same shape. Asserted by a test, not just documented,
  so the limitation cannot quietly become false.
* **A provenance node carries a LINE, not a node identity.** Two `A.If` nodes
  on one source line are one bucket and nothing the hook records can separate
  them. 8 of `self_eval.lang`'s 478 nodes are on such lines; they are marked
  `ambiguous` and **excluded** from every "unreached" number below.
* **A count is a lower bound.** `_merge_ifs` folds a run of identical
  consecutive decisions into one node carrying `count`. REACHABILITY — the
  question — is exact either way; frequency is not.

---

## 3. The two corpora, and the finding nobody predicted

`self_eval.lang` is a Whence evaluator written in Whence. There are two ways to
drive it and this round measured both at the same 478 `if` nodes / 940 written
arms (8 ambiguous nodes excluded from the arm counts):

| driver | both arms | then-only | else-only | undecided | **never evaluated** | arms taken |
|---|---|---|---|---|---|---|
| `run.py examples/self_eval.lang` (its own 172 in-language checks) | 254 | 26 | 137 | 1 | **52** | 671 / 940 (71.4 %) |
| `test_self_eval.py`'s corpus — library + 133 `run_src(<case>)` | 229 | 23 | 106 | 1 | **111** | 587 / 940 (62.4 %) |
| **union** | — | — | — | — | **39** | **719 / 940 (76.5 %)** |

**The two corpora are complementary, not nested.** 132 arms are reached only by
the standalone run; 48 only by the corpus. On `apply_builtin` specifically the
symmetry is exact:

```
apply_builtin: 49 if-nodes, 98 written arms
  standalone reaches 71   corpus reaches 71   union 76
  standalone-only 5       corpus-only 5       unreached by BOTH: 22
```

I predicted (P9) that the Python test corpus would reach *strictly more*
`apply_builtin` branches than the standalone run, by ≥20. It reaches **the same
number**, and each finds five the other cannot. **The file's own in-language
self-tests are as strong an exerciser as the whole Python suite's corpus, and
neither is a superset.** Any coverage claim made from one of them is wrong by
about 5 % of `apply_builtin` and by 14 % (132/940) of the file.

### 3a. Round 506's branch, found by measurement instead of elimination

Round 506 identified the `typed` propagation branch by *running out of other
explanations*. Named exactly, it is the `propagated` guard in `apply_builtin`:

```
self_eval.lang:3555   let ins2 = if propagated { pargs }
self_eval.lang:3559   let o = if propagated { "builtin" } else { name }
```

Both are `else_only` in **both** corpora: `then` 0 against `else` 98
(standalone) and 0 against 83 (corpus). Round 506's conclusion holds, and it is
now a number rather than an inference. **P11 HIT.**

### 3b. …and its two "same shape" cases are NOT the same shape

Round 506 named `abs` (1 run / 2 written) and `shapeof` (5/6) as the same shape,
unchased. At branch level they are not:

| line | builtin | standalone | corpus |
|---|---|---|---|
| 3225 | `typed` dispatch | both arms | both arms |
| 3618 | `abs` | else-only (`then` 0) | **both** (`then` 1) |
| 3745 | `shapeof` | **never evaluated** | then-only (`then` 1) |
| 3555/3559 | `propagated` | else-only | else-only |

`abs` and `shapeof` are *unexercised by one driver and exercised by the other*.
The `propagated` branch is dead in both. A source-level ratio does not predict
branch reachability, and the two questions have different answers for the same
three names. **P12 HIT.**

### 3c. Whole functions nothing calls

Ranked by arms unreached by BOTH runs:

| function | unreached / written |
|---|---|
| `apply_builtin` | 22 / 98 |
| `lex_str_body` | 17 / 22 |
| **`quote_body`** | **12 / 12** |
| `apply_host_builtin` | 9 / 66 |
| **`guest_steps`** | **8 / 8** |
| `raw_deep_eq` | 8 / 26 |
| `show_tok` | 7 / 8 |
| **`guest_at`** | **6 / 6** |
| `eval_if` | 7 / 12 |

`guest_steps` and `guest_at` are 0/8 and 0/6 because their dispatch arms are
themselves unreached: `apply_builtin:3460` (`name == "steps"`) and `:3461`
(`name == "at"`) never take their then-branch in either corpus. The guest
evaluator implements `steps` and `at` and **no program in this repo has ever
asked it to**. That is a real, addressable gap in the differential: two builtins
whose guest implementation has never once been compared against the host's.

---

## 4. Predictions, scored (15 banked at `a4f6982`, before any measurement)

| # | prediction | verdict |
|---|---|---|
| P1 | the funnel is the `Prov` constructor, not a dispatch slot; six sites, all materialising `op == "if"` | **HIT** — and two of the six are unpatchable closures, so it is the only funnel |
| P2 | `MergedProv.__init__` does not call `Prov.__init__`; merged-only decisions ≥1 and ≤40 | **HIT** — 6 standalone, 4 corpus |
| P3 | `rescue` is not censusable at this hook | **HIT** — pass-through builds no node; pinned by a test |
| P4 | hook overhead factor between 1.2× and 2.5× | **MISS**, narrowly and in the informative direction — **1.19×** (6.51 s → 7.74 s). Cheaper than the band's floor |
| P5 | `self_eval.lang` parses to 380–520 `A.If` nodes | **HIT** — 478 |
| P6 | an `if` with no `else` yields a synthesised empty arm, and "else never taken" is noise for guards | **MISS** — since v0.19 an else-less `if` **does not parse at all**. There is no synthesised arm to discount, so every "else never taken" is a fact about written code. The `else_synth` field this prediction motivated was deleted rather than shipped dead |
| P7 | one standalone run reaches both arms of <60 % of nodes | **HIT** — 254/478 = 53.1 % |
| P8 | ≥30 nodes with NEITHER arm taken, standalone | **HIT** — 52 |
| P9 | the corpus reaches strictly more `apply_builtin` branches than standalone, by ≥20 | **MISS on both halves** — 71 vs 71, and 5 each way. The headline finding of the round is this miss |
| P10 | `apply_builtin` holds ≥60 `A.If` nodes; ≥8 arms unreached by both | **HALF** — 49 nodes (MISS), 22 unreached by both (HIT) |
| P11 | round 506's `typed` propagation branch is unreached | **HIT** — `propagated` then-arm 0/98 and 0/83 |
| P12 | `abs`/`shapeof` are NOT the same shape as it | **HIT** — both reached, by the corpus only |
| P13 | ≥1 branch is unreachable *as written* (dead), not merely unexercised | **MISS AS POSED** — this census measures EXERCISE, not reachability. `quote_body` 12/12, `guest_steps` 8/8 and `guest_at` 6/6 are entirely unexercised and `guest_steps`/`guest_at` are unexercised *because their dispatch arm is*, but nothing here proves any of them unreachable. The instrument cannot answer the question I asked it |
| P14 | no existing whence fast-tier node reddens; copyparity stays at 0 escapes | see §6 |
| P15 | `blast` on this round's own new file names ≥1 `languages/whence/tests/` node | **HIT** — and see §5 |

**The misses have one shape.** P6, P9, P10 and P13 all assume the *shipped
description* of a thing is its behaviour: that an else-less `if` exists because
other languages have one; that a bigger corpus is a superset of a smaller one;
that a 400-line dispatch chain is bigger than it is; that a reachability census
measures reachability. Three of the four were settled by running the instrument
for ten seconds. P4 is the other shape and the opposite error — I priced a
Python-level wrapper on the hottest constructor in the interpreter at up to
2.5× and it is 1.19×, because `Prov.__init__` is already six slot stores and one
extra frame is not the cost I imagined.

---

## 5. This round used round 509's instrument on itself, and it worked

`branchlive.py` ships with `tests/test_branchlive.py`, **two of whose nodes are
`whence_slow`-marked** — the exact shape that has reddened
`harness/tests/test_whenceslow.py` five times before (rounds 504, 506, …), each
time discovered a round later by `reddebt` because a language round does not run
the harness suite.

Before committing, this round ran round 509's `blast` against the whence map it
had just recorded:

```
$ readset blast --map <fresh whence map> languages/whence/branchlive.py
  IMPLICATED  languages/whence/tests/test_field_corpus_selector.py  2 key(s) [scan]
  IMPLICATED  languages/whence/tests/test_specreg.py                7 key(s) [scan]
  IMPLICATED  languages/whence/tests/test_v31.py                    1 key(s) [scan]
```

**P15 HIT** — three nodes in a tree the SHIPPED map has zero rows for. And the
measurement that matters more is what it did **not** name: `test_whenceslow.py`,
which the diff really does redden. The whence map cannot name it because the
whence map has no `harness/tests/` rows. `harness/whenceslow.py status` said
`32 units / 122 marked` against pins of `31` and `120`, so this round re-pinned
`test_whenceslow.py` **in the same commit that opened the red** — the SIXTH
occurrence and the first closed by its opener.

That is round 509's `merge` argument, measured a second time from the other
side: *the tree that predicts your red is not the tree your diff is in.*

---

## 6. What was NOT done, named rather than implied

* **The merged three-tree map.** Round 509 recorded whence (367.8 s) and nuc but
  never merged them into the shipped map, which is why two of its own tests are
  red. This round re-recorded all three at ONE commit so `merge` can keep a
  shared `head`; the whence leg finished (2960 passed, rc 0, 367.8 s, 350 keys)
  and the harness leg was still running when the round's 3300 s wall clock ran
  out. **The two red `test_readset.py` nodes are therefore still red**, and the
  reason is wall clock, not a defect: see §7 item 1 for the exact command.
* **Branch coverage is not path coverage.** Two arms of one `if` reached says
  nothing about the pair of arms of the next one.
* **`branchlive` has no ratchet and that is deliberate.** Round 507's
  next-step #3 is that this tree already has "a fourth ratchet nothing
  schedules"; a fifth would not be scheduled either. It reports; it does not
  gate.
* **Only `self_eval.lang` was censused.** `file` runs any program, and
  `self_host.lang` (1651 lines) was not censused for want of time.
* **No mutation testing** of this round's own new code.

## 7. What the next round should take

1. **FINISH THE MERGE — it is three commands and it turns two reds green.**
   All three recordings must be at ONE commit or `merge` drops the `head` and
   `test_the_shipped_map_covers_the_harness_fast_tier` (which asserts a truthy
   head) goes red in exchange. `/tmp/r510-whence.json` is already recorded at
   `b38051d`; if HEAD has moved, re-record all three:
   ```
   python3 harness/readset.py record --out /tmp/w.json -- \
       -c languages/whence/pytest.ini -m "not whence_slow" languages/whence/tests/
   python3 harness/readset.py record --out /tmp/h.json
   python3 harness/readset.py record --out /tmp/n.json -- nuc/tests/
   python3 harness/readset.py merge --out harness/readset-map.json \
       /tmp/w.json /tmp/h.json /tmp/n.json
   ```
   Budget: whence 368 s, nuc ~120 s, harness >900 s under the hook on this box.
   Plan it as the round's long pole, first, not as a step. harness(A).
2. **`steps` and `at` have a guest implementation nothing has ever run.**
   `apply_builtin:3460-3461` never take their then-branch, so `guest_steps`
   (8/8 arms) and `guest_at` (6/6) are entirely unexercised. Two cases in
   `test_self_eval.py`'s `CORPUS` would fix it and would be the first
   host-vs-guest differential either builtin has had. language(C).
3. **The two corpora are complementary and nobody knew.** 132 arms reached only
   by the standalone run, 48 only by the Python corpus. Either the corpus grows
   the 48 into `CORPUS` or the suite runs both and unions them; today every
   coverage statement about the self-evaluator is made from one of the two.
   language(C).
4. **P13's question is still open and this instrument cannot answer it.**
   Distinguishing *unreachable* from *unexercised* needs the guest's own
   condition, not its outcome — a constant-folding pass over `A.If` conditions,
   or a satisfiability argument. `quote_body` (12/12 unreached) is the cheapest
   place to start. language(C).
5. **`branchlive file` has been run on exactly one program.** The corpus of
   34 `examples/*.lang` is one loop away and would give the first whole-corpus
   branch number for the language. language(C).
6. **Round 486's and round 492's prediction banks are STILL unscored**, at 24
   and 18 rounds owed, both owned by language(C) and both scorable from
   committed artefacts. This round read the ledger entries and did not pay
   them; that is now three language(C) rounds in a row. language(C).
7. **`nproc` is 1.** Every measurement here was serialised and the round still
   lost its last item to a background recording it had launched first. The
   whence fast tier under the audit hook is 367.8 s; the harness tier is
   longer than 900 s and has never been timed to completion.
8. **Standing and untouched by this round:** the NUC `retention --strict`
   deadline; `case_coverage`'s disagreeing verdicts; `claim_check` executing 0
   of its commands; round 507's next-steps #1-#5; and CLAUDE.md's
   `CRITICAL MISSION` and `MASTER MISSION` blocks, still a one-block deletion
   for the operator. `languages/whence/SECURITY.md` remains the operator's
   decision.

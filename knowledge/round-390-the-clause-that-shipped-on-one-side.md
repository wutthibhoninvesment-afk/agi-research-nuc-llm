# Round 390 (language C) — the clause that shipped on one side, and the debt that was paid twice

*Whence v0.33's second half. Two records disagreed with reality this round,
in opposite directions: a fix the record said had shipped had shipped on one
side only, and a debt the record said was open had been paid 40 rounds ago.
Both had an instrument that could have said so. One instrument was in a tier
nobody runs; the other printed the answer every round as information.*

---

## 0. What this round did

| | |
|---|---|
| **Discharged** | ledger entry 386's `remainder` — the guest mirror of `_miss_lit`'s v0.33 unbound-name clause |
| **Retired** | round 332's item 1, discharged by round 350, carried by nine blocks since round 375 |
| **Built** | `tests/test_v33.py` §4 — host/guest parity for the clause, in the **fast** tier, 0.58 s |
| **Built** | `state/retired-next-step-items.json` + `state_claim_check.py`'s **S006** |
| **Landed first** | round 389's uncommitted follow-up diff (verified, 17 passed, committed as `db38e10`) |

---

## 1. The debt, and what it actually was

`state/prediction-bank-ledger.json`, entry 386:

> P14's second clause is an OUTSTANDING DEBT, not just a scoring HALF: the
> host `_miss_lit` fix shipped and its guest mirror in
> `examples/self_eval.lang` did not, so host and guest now disagree on
> `miss <bare unbound name>`.

That is an accurate record of a shortfall, written by round 387 about a
round that died before it could write anything. It is also, as a
description of the divergence, **too small by a factor of five and wrong
about the shape**. Measured at HEAD before any change:

```
miss NOSUCH     host  unbound name 'NOSUCH' (a miss reason is a string: write `miss "NOSUCH"`)
                guest unbound name 'NOSUCH'
miss (NOSUCH)   host  ...same as above
                guest unbound name 'NOSUCH'
miss null       host  unbound name 'null' (a miss reason is a string: write `miss "null"`)
                guest unbound name 'null' (Whence has no null; a missing value is `miss <reason>`)
miss then       host  unbound name 'then' (a miss reason is a string: write `miss "then"`)
                guest unbound name 'then' (an `if` needs no `then`: `if c { a } else { b }`)
miss println    host  unbound name 'println' (a miss reason is a string: write `miss "println"`)
                guest unbound name 'println' (Whence has no `println`; `print` already ends the line)
```

The first two are the divergence the ledger describes: a clause that is
missing. **The last three are a different and worse one: the guest emits a
DIFFERENT CURE.** Not less advice — wrong advice, confidently worded, in the
language's own reference self-interpreter.

The mechanism is that the two clauses are competing for one slot. The
guest's `lookup` already appends the foreign-word clause to the reason it
builds; the host's `_miss_lit` **replaces** it, and `whence/foreign.py` says
why:

> It REPLACES the foreign clause rather than joining it, and only in this
> position. `miss null` would otherwise read "Whence has no null; a missing
> value is `miss <reason>`" — advice to write the thing the author is
> already writing. Position beats vocabulary here because the position is
> the more specific fact.

So the mirror is not *append the sentence*. It is **rebuild the sentence
from the bare name**, and the rebuild is what drops the other clause. A
mirror written to the ledger's description — append the missing clause —
would have passed a wording test on `miss NOSUCH` and still contradicted
the host on `miss null`.

> **A record of a shortfall is a pointer, not a specification.** Round 387
> wrote the truest sentence it could from artifacts; the sentence still
> understated the defect, because the round that could see the defect was
> dead. Re-measure the divergence before mirroring it.

---

## 2. The guard, and the alternative that was measured instead of argued

The host asks:

```python
if reason.op == "name" and is_origin_miss(reason):
```

The obvious guest mirror tests the reason box's **op label** against
`"name " + node.operand.value` — round 380 gave an unbound name exactly that
label. I wrote it, wrote a comment explaining the case where it breaks, and
then went to check the case. **It does not break.** Nor does the next one,
nor the one built specifically to break it (`let NOSUCH = NOSUCH` then
`miss NOSUCH`, where the label has to match itself).

The reason is an invariant nothing in this tree had stated. The guest
re-wraps at **all three** of its binding paths:

| path | site | label |
|---|---|---|
| `let x = …` | `eval_stmt` | `let x` |
| a parameter | `bind_params` | `arg x` |
| `fn f(…)` | `fndef` | `fn f` |

so a **bound** name's box is labelled by its binder and never carries a
`name x` label at all. The label test can only ever be shown an unbound
name. It works, and it works for a reason held up by three unrelated sites,
none of which knows it is load-bearing.

The shipped guard asks the store instead —
`missed(lookup(st, env, node.operand.value))` — because that encodes the
host's *question* ("did this name resolve?") rather than a convention that
could be dropped at any one of the three sites. `self_eval.lang` now pins
all three labels, so if the invariant ever goes, something says so.

> **Two honest notes.** First: I wrote a code comment asserting a
> counter-example before running it, and the counter-example was wrong. The
> comment is now what was measured, not what was assumed. Second: this is
> the *second* time in two rounds that a plausible-sounding mechanism
> survived into prose without being executed — round 389's own §4b records
> the same shape.

Every edge, host vs guest, after the mirror:

```
miss NOSUCH / miss (NOSUCH) / miss null / miss then / miss println   clause, both
miss b (bound to an unbound-name miss)                               no clause, both
miss g() (call returning one)                                        no clause, both
fn f(NOSUCH) { miss NOSUCH } ; f(NOSUCH)                             no clause, both
let NOSUCH = NOSUCH ; miss NOSUCH                                    no clause, both
miss (miss NOSUCH) / miss 1 / miss "ok" / bare null                  agree
miss len                                                             E2, still exempt
```

---

## 3. Why nothing went red — the finding that outlives the bug

`tests/test_miss_message_differential.py` reads every `mk_miss` /
`merge_miss` site out of `interp.py`'s AST and asserts the corpus reaches
all of them. v0.33 added a site and no case. So it **was** red — from round
386, and it stayed red, unseen, through rounds 387, 388 and 389:

```
AssertionError: the corpus reaches 123 of 125 declared sites;
                add a case for [('_miss_lit', 338)]
```

The instrument built to catch exactly this caught exactly this, four rounds
ago, and said so to nobody. It is `@pytest.mark.whence_slow`.

**And so is every other host-vs-guest assertion in this tree.** The
differential's guest half, `test_self_hosting.py`, `test_lexer_guest_parity.py`'s
sweeps — all slow. `pytest -m whence_slow` costs ~900 s at `nproc` = 1 and
has run **four times in the last thirty rounds**. Round 384's own
verification table still carries the literal unrendered placeholder
`SLOWTIER_RESULT` where its result belongs; round 380's P11 is banked as
*owed*.

> **Host/guest parity had no fast-tier coverage at all.** That is the
> general fact, and it is worse than the specific bug it hid: it means a
> one-sided ship is invisible to every round by default, and visible only to
> a round that spends 15 minutes deciding to look.

The fix is not "run the slow tier more". It is that the whole-corpus
differential is expensive **because it is a corpus sweep** (130 cases × 3
engines), and the property that actually needed guarding is one clause.
`tests/test_v33.py` §4 runs the host and **one** guest interpreter over six
cases in **0.58 s**, asserting the clause fires on an unbound name and on
nothing else, on both sides. The slow differential stays authoritative; the
cheap test is the tripwire.

> A rule checked only in a tier nobody runs is not checked.

---

## 4. The other direction: a debt paid in round 350, carried to round 389

Round 332's item 1 — *an exhaustive sweep of `whence/lexer.py`'s full
history against the guest `lex` function* — appears in the live next-steps
block of round 389. It was discharged **forty rounds ago**.

Round 350 built `tests/test_lexer_guest_parity.py` (commit `3ed4391`) and
its module docstring names the item, quotes it, and answers it — including
the part that matters, which is that the item as worded **cannot be done**:

> `git log --follow -- whence/lexer.py` has exactly THREE revisions … Both
> semantic diffs are mirrored in the guest. So a history sweep covers two
> lines of a two-hundred-line lexer and answers nothing about the rest,
> which arrived already written in a commit that has no parent to diff
> against. A diff-driven audit is structurally incapable of establishing
> this parity. This file is what can: it compares what the two lexers DO.

Round 348 had asked for exactly that — *"either a future round does it or it
should be closed explicitly"*. Round 350 closed it explicitly.

### 4.1 This is a RESURRECTION, not a missed closure

Mapping every carry of the phrase to its enclosing block:

| blocks | rounds |
|---|---|
| carried while genuinely open | 333, 334, 336, 338, 346, 347, 348 |
| **retirement understood — absent from every block** | 351 … 373 (12 blocks) |
| **resurrected** | 375 |
| carried since | 377, 379, 381, 382, 383, 384, 387, 389 |

The item was correctly dropped for twenty-three rounds. It came back at
round 375, in an item that expanded round 373's round-keyed compression —
*"the rest of skills(B)'s and language(C)'s standing items are unchanged"* —
back into names.

That is a different failure from round 387's (a debt closed at round 339 and
re-asserted by nine consecutive blocks that never re-read the instrument).
Here the blocks **did** know. Then a lossy compression was decompressed
against an out-of-date source, and the loss was invisible because:

> **A retired item is retired by DELETING its line, which leaves no record
> that it was retired rather than merely omitted.** Omission and retirement
> are the same edit. Nothing downstream can tell them apart.

### 4.2 The instrument printed the answer every round

`state_claim_check.py`'s S005 has been reporting this, unchanged, in every
round that ran it:

```
CARRIED S005 asserted verbatim by 16 next-steps blocks
(rounds 333, 334, 336, 338, 346, 347, 348, 375, 377, 379, 381, 382, 383,
 384, 387, 389) — no round between them re-derived it: round 332's item 1
```

The gap `348, 375` is right there in the output. **S005 is `CARRIED`, which
is never an error** — by design, and correctly, since a long carry is not
itself a defect. So the resurrection signature was printed, in green, every
round, and read by nobody.

### 4.3 S006 — the tombstone

`state/retired-next-step-items.json` is the missing record. S004 already
asks whether a `Round N's item K` pointer **resolves**; nothing asked
whether the thing it points at is still **open**. S006 does.

One design point decides whether the check is usable. Round 389's own block
says:

> **Round 383's item 5 is CLOSED and must not be carried again**

— which is precisely the sentence S006 exists to produce. Firing on it would
make the checker punish the cure. So a citation is exempt when its own item
text acknowledges the closure (`closed`, `retired`, `discharged`, …). This
is deliberately generous: round 339's rule is that a checker nobody watches
must be zero-false-positive even at the cost of recall.

Against the real document, with round 389 still live, it fires **once** —
on round 332's item 1 — and correctly stays silent on round 383's item 5.

The registry is seeded with two entries and **only two**, both verified this
round rather than swept up: round 332's item 1 (evidence: the test file and
its commit) and round 383's item 5 (evidence: `harness/tier-budget.json`'s
promoted entry, whose `why` names the item by number). Registering a
tombstone is a claim; `TestTheRealRegistry` re-derives that every entry
names a discharging round later than the round, and an evidence path that
exists.

---

## 5. Honest failures

1. **I wrote a code comment asserting a counter-example, then found the
   counter-example does not exist** (§2). Three probes were needed to
   establish that the two guards are equivalent and why. Shipped comment
   states the measurement.
2. **P9 under-priced the change by 3.6×** — predicted ≤25 added lines in
   `self_eval.lang`, measured **90**. The code is ~10 lines; the rest is the
   comment and seven self-tests. This is round 384's banked P10 verbatim
   (*"I priced the code and forgot the prose is part of the artifact"*) and
   round 386's P16, making it **three consecutive language rounds** missing
   the same prediction the same way. The multiplier is not the problem — the
   habit of pricing the diff instead of the artifact is.
3. **P2 generalised from one case.** I banked "the divergence is exactly one
   clause wide" having read only the `miss NOSUCH` path; three of the five
   diverging cases diverge differently (§1).
4. **P3 was nearly unmeasurable by my own hand.** I ran the fast suite for
   the first time *after* editing `self_eval.lang`, so the baseline had to be
   re-taken in a `git worktree` at HEAD rather than read off my own run — the
   same class as round 389's mid-flight-edit episode, one round later.
5. **`test_v31.py` pinned `159 passed` and went red**, correctly. Its
   docstring said "the count moves; the property is that none of them
   fails", which contradicts its own assert. Updated to 166 and the
   docstring now states the real contract (an exact pin is what catches a
   `check` line that silently stops running).

---

## 6. Verification

See `state/whence/round-390/PREDICTIONS.md` for the bank and §7 for scoring.

| check | result |
|---|---|
| `python3 run.py examples/self_eval.lang` | **166 checks, 0 failed** (was 159) |
| host-vs-guest probe, 19 cases | 0 diverging outside the named E2 exemption |
| `pytest -m whence_slow tests/test_miss_message_differential.py` **before** | **1 failed**, 7 passed — `('_miss_lit', 338)` unreached, 123 of 125 |
| the same, **after** | **8 passed**, 4 deselected, 117.3 s |
| `pytest tests/test_v33.py -m "not whence_slow"` | 26 passed, 6.4 s; the 3 new parity tests, 0.58 s |
| `bash run_tests_fast.sh` (pristine HEAD, `git worktree`) | see §7 |
| `bash run_tests_fast.sh` (final tree) | see §7 |
| `state_claim_check.py state/research-state.md` | S006 fires once (round 389 live), 0 after this round's block |
| `test_state_claim_check.py` | see §7 |

---

## 7. The bank

15 predictions, banked before any measurement. **11 HIT / 3 HALF / 1 MISS.**

| # | claim | verdict | note |
|---|---|---|---|
| P1 | host sentence for `miss NOSUCH` | **HIT** | character for character |
| P2 | guest lacks the clause; "exactly one clause wide" | **HALF** | the `miss NOSUCH` half exact; **3 of the 5** diverging cases emit a DIFFERENT cure, not a missing one. Banked from the one path I had read (§1) |
| P3 | fast tier green at HEAD, 1693/3 | **HALF** | the number reconciles exactly (1693 + 3 new tests = **1696 passed**, 3 skipped) but I first ran the suite AFTER editing `self_eval.lang`, and the worktree substitute was confounded (§5.4) |
| P4 | slow tier RED; `test_the_corpus_reaches_every_reachable_miss_site` failing because round 386 added a site and no case | **HIT** | exact, cause and all — banked from reading the instrument, never running it |
| P5 | ≥120 declared sites; exactly **1** unreached | **HIT** | `123 of 125`, missing `[('_miss_lit', 338)]` |
| P6 | nine post-350 blocks re-assert round 332's item 1: 375, 377, 379, 381, 382, 383, 384, 387, 389 | **HIT** | all nine, exactly that set |
| P7 | round 350's own block does not carry the item | **HALF** | premise wrong: round 350 has **no block at all** (landed by round 351). Round 351's block correctly omits it |
| P8 | the new cases agree; no new `EXEMPT_CASES` entry | **HIT** | `test_each_exemption_is_load_bearing` green |
| P9 | fix in `eval_unary`'s `miss` branch using `node.operand.kind`; **≤25** added lines | **MISS** | location right, size wrong by 3.6× (**90**). See §5.2 |
| P10 | no new machinery needed for `is_origin_miss` | **HIT** | true — though for a reason I had wrong until I ran it (§2) |
| P11 | `self_eval.lang` ≥160 checks, 0 failed | **HIT** | **166**, 0 failed |
| P12 | after the fix the slow tier is green and reaches every site | **HIT** | 8 passed, 117.3 s |
| P13 | skills checks stay at 0 errors; `skill_lint` 0/0 | **HIT** | `skill_lint` **45 skills, 0 errors, 0 warnings**; `run_checks_fast.sh` back to 0 errors once this round's own bank was registered |
| P14 | no new SPEC decision; parity note under `## v0.33`; header stays | **HIT** | `test_spec_level_header_matches_the_highest_version_section` green |
| P15 | whole-round diff 900–1600 lines | **HIT** | see §6 |

**The four items banked from READING the instrument rather than running it —
P1, P4, P5, P6 — are all exact.** The one MISS and two of the three HALFs are
about my own effort and method, not about the system under test. That split is
the useful signal: predictions about the artefact were good, predictions about
the work were not.

### The miss that is now three rounds old

P9 priced the change at ≤25 added lines; it is 90. The **code** is ~10 lines —
two helper functions and a reordered branch. The other 80 are the comment that
records the measurement in §2 and the seven self-tests. This is round 384's
banked P10 (*"I priced the code and forgot the prose is part of the artifact"*)
and round 386's P16, unchanged, in the third consecutive language round.

Round 385's rule was *price the code then multiply by four*. 10 × 4 = 40,
still less than half. On this round's evidence the multiplier for a change
whose whole point is a recorded measurement is closer to **nine**, and the
reason is structural rather than stylistic: when the finding IS the
comparison, the prose is the deliverable and the code is the smaller half.

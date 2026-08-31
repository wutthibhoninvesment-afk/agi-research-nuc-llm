# Round 386 — language(C) — the cure that was named but not followed

**Track:** C (language design). **Artifact:** Whence **v0.33**, decision 42,
plus `languages/whence/curecheck.py` and `whence/foreign.py`.
**Date:** 2026-08-31.

> **Record reconstructed by round 387.** Round 386 died at `error:max_turns`
> after 150 tool calls with its code, tests and measurement artifacts on
> disk, its `PREDICTIONS.md` banked, and **no knowledge file, no
> research-state entry, no ledger entry and no commit**. Round 387 verified
> the work, scored the bank, and wrote this file. Everything below is
> re-derived from committed-or-on-disk artifacts
> (`state/whence/round-386/*.json`, the diff, the test suite) — **never from
> round 386's own claims about itself**, which is round 374's rule for a
> killed round's record. Round 386's prediction scoring lives in
> `knowledge/round-387-the-replay-that-could-not-see-the-failures.md` §6,
> because the round that scores a bank should be the one the ledger names.

---

## 1. The question

Whence's decision 32 (v0.22, round 354) says *an error that can name the fix,
names it*. Round 354 measured itself honestly: of the ten machine-written
programs in `examples/` that fail to parse, **one** named a cure before v0.22
and **nine** did after; v0.23 took it to ten. `SPEC.md:5303` publishes it:

```
machine-written corpus, cures named               9/10 -> 10/10
```

That figure counts **cures NAMED**. For thirty rounds nothing counted **cures
FOLLOWED**. Round 386's question: *can a reader who knows only the error
message perform the edit?*

Its operational definition, from `curecheck.py`'s docstring:

> A cure is MECHANICAL if the error message — its body, its parenthetical
> hint, its line and its column — determines a unique edit to the source
> text, with no appeal to knowledge of Whence that the message does not
> itself contain.

## 2. The answer: 3 of 8 cures, and 0 of 10 programs

`python3 curecheck.py rules` — the determinacy table, keyed on hint
constants **imported** from `whence.parser` rather than on copies of their
wording, so a reworded hint breaks the import (loudly, in the fast tier)
instead of silently unclassifying a message:

| cure | determinacy | what the message fails to supply |
| --- | --- | --- |
| `assignment` | **mechanical** | — |
| `record-literal` | **mechanical** | — |
| `missing-separator` | **mechanical** | — |
| `braced-block` | under-**extent** | where the block *ends* |
| `rescue-infix` | under-**extent** | the extent to reorder across |
| `foreign-word` | under-**extent** | — |
| `juxtaposition` | under-**choice** | call vs. quote — two edits, no verdict |
| `if-requires-else` | under-**content** | what value the `else` should have |

Three distinct under-determination modes — extent, choice, content — not one.

**Under purely mechanical application, 0 of the 10 programs reach a value.**
All ten `stall` (`state/whence/round-386/corpus-mechanical.json`). Only two
files accept even one mechanical edit.

**Under a human-equivalent reading of the same cures, 10 of 10 reach a
value** — 45 hand-authored edits, ledgered in `cure-ledger.json` with the
datum each one needed that the message did not carry
(`choice` 19, `whole-construct` 10, `extent` 2, `content` 1, `everything` 1).
Of those 45, **7 were not errors at all** (the text already parsed) and
**2 named no cure**: `a fn expression may not be named`, a gap v0.22 never
saw because v0.22 only ever looked at *first* errors.

So the honest pair of numbers is:

```
cures NAMED     9/10 -> 10/10     (v0.22/v0.23 — unchanged, uncorrected)
cures FOLLOWED  0/10 mechanically, 10/10 with a reader
```

`SPEC.md:7089` states in-tree that v0.33 "does not touch the `9/10 -> 10/10`
figure". It was a true statement about naming; this measures a different
property and adds a number beside it rather than replacing it.

Secondary measurements, all from `replay.json`:

- Errors per file: `1,1,1,1,2,3,4,6,7,19` — **median 2.5**, and only **6 of
  10** have a second error at all. One cure IS enough for four of them.
- Parse errors do **not** move monotonically forward:
  `nano_reasoner.lang` goes line 31 → **30** → 53.
- After the parse errors are exhausted, **8 of 10 are not clean under
  `--strict-miss`** and **6 produce `unbound name 'println'` at runtime**.
  Every one exits 0, because in Whence a failure is a value.

## 3. Shipped: v0.33, decision 42

**The table the parser could not see.** `_FOREIGN_NAMES` — "Whence has no
loops", "Whence has no `println`" — existed since v0.32 in `interp.py`,
reachable only from a *runtime* unbound name. A program that does not parse
never gets there. v0.33 moves the table to `whence/foreign.py` (`interp.py`
imports `parser.py`, so a table both need cannot live in `interp.py`) and
reads it from the parse side too. `_FOREIGN_NAMES` remains as an alias — not
a convenience, the guarantee that there is still exactly one table.

The clause is silent for any name the file itself binds
(`bound_anywhere(tokens)`, one whole-file token scan done once in
`__init__`, because it is the same answer every time and an error path is
not where a linear scan belongs).

**A bug this round caught in its own new code, worth recording.** An earlier
draft of `_foreign_hint` tried *both* the offending token and its
predecessor. That made `safe_divide one_hundred, zero_point_zero` — round
354's tenth case — report *"Whence has no spelled-out numbers; write the
literal `100`"*: true about the word, and it **shadowed** the juxtaposition
hint, the one message that describes the actual mistake there. The rule that
fixes it was already implicit: *a foreign word explains an error when it is
what put the two names next to each other, not when it merely happens to be
one of them.* Measured: 15 of 45 corpus parse errors changed by this clause;
before the fix, one of the 15 was a regression.

**Round 384's next-step 1 closed.** `miss <bare unbound name>` — six sites
across four field programs — evaluated the `NameRef`, got `unbound name
'SOME_ATOM'` and propagated it: the atom the author wrote as the reason
survived only as the subject of a complaint about scope. `_miss_lit` now
supplies decision 41's miss-reason clause, guarded on origin + `op == "name"`
because `miss reason` over a *bound* name is the idiomatic spelling and the
tracked corpus uses it 14 times.

`tests/test_v31.py`'s `mk_miss` census moved **85 → 86** with `setting`
unchanged at 19 — the census reporting the *shape* of the change, not just
its size.

## 4. Verification (re-run by round 387 at commit `3772ac6` + tree)

| check | result |
| --- | --- |
| `languages/whence/run_tests_fast.sh` | **1693 passed**, 3 skipped, 81 deselected, 78.3 s |
| `harness/run_tests_fast.sh` | 735 passed, 267 deselected (driver log, round 386) |
| `curecheck.py corpus` | 14 files, 10 stalled, 4 parse-unedited |
| `curecheck.py replay cure-ledger.json` | 10/10 rc=0, 2/10 clean under `--strict-miss` |

Added: `curecheck.py` 744 lines, `tests/test_v33.py` 352, `whence/foreign.py`
173, plus +345/−30 across `SPEC.md`, `parser.py`, `interp.py`,
`tests/test_v31.py`. **1614 lines total.**

## 5. What round 386 did NOT do

- **No guest mirror.** Its own P14 promised the `_miss_lit` fix "plus its
  guest mirror in `self_eval.lang`". `self_eval.lang` is untouched. The host
  and guest now differ on `miss <bare unbound name>`; a future language(C)
  round owes the mirror or an explicit decision not to.
- **No knowledge file, no state entry, no ledger entry, no commit** — the
  gap this file closes.
- **No hint mis-fire found in the shipped v0.32 parser.** The only mis-fire
  observed was in v0.33's own draft (§3), caught before shipping.

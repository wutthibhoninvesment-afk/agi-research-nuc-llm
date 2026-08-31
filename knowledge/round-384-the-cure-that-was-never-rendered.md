# Round 384 — language(C) — the cure that was never rendered

**Track:** C (language design). **Artifact:** Whence **v0.32**, decisions 40
and 41. **Date:** 2026-08-31.

---

## 0. Pre-flight

- One `claude -p` process (`ps aux | grep -c "[c]laude -p"` = 1), no
  concurrent round. `git diff --cached` empty before any staging. `nproc` = 1.
- `languages/whence/SECURITY.md` dirty for the **14th consecutive round**
  (round 383's count; 30 rounds carried per the registry), md5 `f55e3ab7…`,
  unchanged content, escalation pin intact. mtime 2026-08-30 17:58:31Z — the
  same mtime round 383 recorded, so the gateway did not rewrite it this
  round.
- `CLAUDE.md`'s standing 🔴 CRITICAL MISSION names two operator complaints
  against v0.19 — `fold()` returning a miss, and the braces rule. Both were
  answered as documentation by round 349 and as language by v0.22 (round
  354). **This round is about why the second answer never reached the person
  who filed the first.**

## 1. The finding, in one paragraph

Fourteen machine-written Whence programs sit untracked in
`languages/whence/examples/` — the output of a system that is not this
research program. They are the only field data this language has. Ten do not
parse. Of the four that run, **three are silently wrong and all four exit
0**: `expense_tracker.lang` prints nothing at all, `mini_agi_guardian.lang`
prints its banner and stops, `prod_showcase_final.lang` prints four labels
with empty values. One mechanism explains all three — `println` is not a
Whence builtin, an unbound name is a miss, a miss is a first-class value,
and a value that is a whole statement is **discarded without being
rendered**. And inside the value `expense_tracker.lang` throws away is

```
fold needs a list, got <fn add_item> (arguments fit fold(fn, acc, xs))
```

— the clause **v0.22 wrote thirty rounds ago for exactly this program's
bug**. The language had the cure, had it in the right words, attached it to
the right value, and never once printed it.

## 2. What HEAD does with the field corpus (measured first)

| program | rc | printed |
| --- | --- | --- |
| `cognitive_verifier.lang` | 2 | `expected '{', got '\n' (blocks are always braced…)` |
| `cognitive_verifier_v2.lang` | 2 | `'if' requires 'else' (every expression has a value)` |
| `cognitive_verifier_v3.lang` | 2 | `expected '{', got 'VERIFIED: ' (blocks are always braced…)` |
| `nano_reasoner.lang` | 2 | `unexpected '=' (Whence has no assignment; a name binds once…)` |
| `prod_demo_v1.lang` / `_v5` | 2 | ``unexpected 'rescue' (`rescue` is infix…)`` |
| `prod_demo_v3.lang` / `_v4`, `whenceguard_v2.lang` | 2 | `two names in a row: Whence has no juxtaposition…` |
| `whenceguard_auditor.lang` | 2 | ``records are written `@{a: 1}`, not `{a: 1}``` |
| **`expense_tracker.lang`** | **0** | **nothing** |
| **`mini_agi_guardian.lang`** | **0** | **31 bytes: the banner** |
| **`prod_showcase_final.lang`** | **0** | **six lines, four with empty values** |
| `test_simple.lang` | 0 | `Result: 150` |

Every one of the ten parse errors names a cure. That is v0.22 working, on
the surface v0.22 measured. The four that RUN were never measured by
anything, because "it parsed and exited 0" is what a test suite calls a
pass.

A lexical census of all 14 (frozen in
`state/whence/round-384/field-names.json`) says what a real user reaches for
that this language does not have:

| identifier | uses | files |
| --- | --- | --- |
| `println` | **34** | **9 of 14** |
| `catch` | 6 | 4 |
| `Miss` | 6 | 4 |
| `return` | 4 | 3 |
| `for` / `in` | 2 / 2 | 2 |
| `then` | 1 | 1 |

**There is not one typo of a builtin in the corpus.** Every name that needs
help is a foreign idiom. That single fact decides decision 41 below.

## 3. Decision 40 — an unobserved miss

A miss is **observable** when it reaches a name, a `check`, an operand, or
`print`. It is **dropped** when it is the value of an expression statement
whose value is discarded — `Interpreter.run`'s top level (the last statement
included: `run` returns the `Env`, not a value), `eval_Block`'s non-tail
statements, and the compiled `f_block`'s. The interpreter now records those,
keyed on `(reasons, birth line, op, death line)` with a count, capped at
`DROP_CAP = 100` distinct sites with `dropped_total` counting past the cap.
`run.py` prints them:

```
$ python3 run.py examples/expense_tracker.lang
dropped: 1 miss value computed and discarded — nothing can ask it why
  line 35 (let final_total, from line 20) — fold needs a list, got
  <fn add_item> (arguments fit fold(fn, acc, xs)) (line 15)
```

Two lines because they are two facts: where the value was made, and where it
stopped being anybody's. The exit contract (0/1/2) is **unchanged** — 1 has
meant "a check failed" since v0.1 — so `--strict-miss` is the opt-in that
makes a dropped miss exit 1, pinned by a test asserting the two runs' stdout
is byte-identical.

`exec_stmt` deliberately does not record, which is what keeps the REPL
correct with **no REPL change at all**: the REPL prints every expression
statement's value, and it drives statements through `exec_stmt`.

### 3.1 The corpus wrote the observation rule, not me

The recorder's FIRST run over the 17 tracked examples reported four drops.
All four were the same shape:

```whence
let runaway = loop(0)
print(runaway)          # deep.lang — the miss IS the subject of the example
```

`print(x) is x` (a pass-through, so provenance is undisturbed), so
`print(<a miss>)` is a statement whose value is a miss — and it is the one
statement in the language where that is the point. `b_print` now remembers
the node when its payload is a `Miss`; `_note_drop` skips it. After the rule
the tracked corpus drops **0**, which is the property that makes the report
readable: *a green corpus is a silent one.*

Two edges kept on purpose and pinned:

- `1 + print(y)` still reports the SUM. `print` showed `y`, not the sum, and
  crediting it with observing a value it never saw is the false negative
  this feature exists to prevent.
- The observed set is capped like the record; past 100 printed misses the
  recorder errs toward **reporting**, because a false drop is visible and
  arguable and a silent one is not.

### 3.2 What it deliberately does not report

- **A `let` bound and never read.** `expense_tracker.lang` binds
  `division_result = safe_divide(100, 0)` to demonstrate a first-class error
  and never uses it. That value has a name, so it is observable; reporting it
  would make this a style checker.
- **A miss inside a list or record nothing reads.** The container was
  observed, the element was not; reaching it needs a traversal and a depth
  policy the field corpus does not ask for.
- **Any observer but `print`.** It is the only builtin whose purpose is to
  show a value to a human.

## 4. Decision 41 — the cure clause, and its entry rule

```
unbound name 'println' (Whence has no `println`; `print` already ends the line)
unbound name 'return' (Whence has no `return`; a block's value is its last expression)
```

`_FOREIGN_NAMES` has 13 entries and an **executable entry rule**: a name
qualifies only if (a) the frozen field census attests it, or (b) it is the
keyword of a construct a numbered decision names as deliberately absent
(decision 2 "No exceptions, no null"; decision 3 "All iteration is recursion
/ `map` / `filter` / `fold`") — and the sentence must name what to write in
Whence instead. `test_every_foreign_name_is_attested_or_rejected_by_a_
decision` runs the rule, and asserts that `printf`, `def`, `lambda`, `elif`,
`size` and `length` are **absent**, which is the half that proves the rule
bites.

### 4.1 The rule that was built, measured, and deleted

A nearest-builtin "did you mean" by edit distance was written first. Three
measurements killed it:

1. **No population.** The field corpus contains no typo of a builtin (§2).
   `length` is not even reachable: `length`→`len` is distance 3.
2. **Suggesting from names in scope is wrong in THIS language.** 17 of 31
   programs in `examples/` (**54.8 %**) bind two names within distance 2 of
   each other — `a`/`b`, `d1`/`d2`, `q1_status`/`q2_status` — because a
   single-assignment language names a **series** where an imperative one
   reassigns one variable. In fuzz-generated programs it is 19 of 62 name
   pairs (30.6 %). A near-miss between user names is evidence of a series.
3. **The builtin set is ambiguous with itself.** **18 of its 666 pairs** are
   within distance 2 (`at`/`put`, `str`/`sure`, `find`/`fold`,
   `rand`/`range`, `sqrt`/`sure`), and `add` is distance 2 from three at
   once.

And it needed four tuning constants to stop lying. Fire rates on a 20-name
probe corpus:

| rule | fires | what it proposes |
| --- | --- | --- |
| A: `d<=2`, unique nearest | 12/20 | …and `q`→`at`, `x`→`at`, `v1`→`at`, `f6`→`at` |
| B: A + `d < len(name)` | 8/20 | …and `odd`→`fold` |
| C: B + `len>=3 and d <= len-2` | 7/20 | `println`→`print`, `printf`→`print`, `fliter`→`filter`, `fodl`→`fold`, `pirnt`→`print`, `strr`→`str`, `nope`→`note` |

Even at C the only true positives are hypothetical typos, and `nope`→`note`
is a confident wrong answer. **A hint that needs four constants to stop
lying is not a hint.** Deleted in favour of the table.

The fourth cost settles it: `examples/self_eval.lang` re-implements name
lookup, so it would have had to **re-implement Levenshtein in Whence** to
keep wording the message the same way — round 380's divergence class,
repeated. The table it mirrors in four lines:

```whence
fn name_hint(n) {
  if has(foreign_names, n) { " (" + get(foreign_names, n) + ")" } else { "" }
}
```

*If a second implementation must say what you say, the cheapest hint to
MIRROR is a data structure, not an algorithm.*

### 4.2 Host/guest parity, verified

`pytest tests/test_miss_message_differential.py` (39 tests, **135.7 s**,
including the slow 125-case host-vs-guest sweep) is green with the clause on
both sides, and `test_v32.py::test_host_and_guest_word_the_foreign_clause_
identically` pins the two sentences against each other, allowing only the
`(line N)` difference that is the language's oldest documented divergence.

## 5. The structural change, and the two pins that caught it

`unbound name '%s'` was **three copies of one literal** — the compiled
`f_name`, `eval_NameRef`, and `f_bcall`'s dead `fnv is None` floor. A clause
added by hand would have been added to one of them. `_unbound(name, line)`
is now the single constructor, and that moved round 380's own census:

| pin | was | now |
| --- | --- | --- |
| `test_v31.py` `mk_miss` sites | 87 | **85** |
| `test_v31.py` detail-setting `name` sites | 3 | **1** |
| `test_miss_message_differential.py` unreachable-site probe | found 2 | found 1 → widened to accept `_unbound(` |

All three went red on the first run and all three were **right to**. The
property they guard (a `detail` passed positionally says nothing about
itself; the dead site still exists) is unchanged, and each pin was updated
with the reason rather than the number.

## 6. Cost

`bench/minof.py -n 3`, this tree vs a `git archive` of HEAD, fresh
processes, min of 3, `PYTHONDONTWRITEBYTECODE=1`:

| bench | HEAD (v0.31) | v0.32 | Δ |
| --- | --- | --- | --- |
| `meta direct` | 4.924 s | 4.754 s | −3.5 % |
| `fib20 direct` | 0.285 s | 0.272 s | −4.6 % |
| `fib20 fast` | 0.182 s | 0.147 s | −19 % |
| `tail100k direct` | 0.629 s | 0.599 s | −4.8 % |
| `self_eval direct` | 2.620 s | 2.643 s | **+0.9 %** |

Four of five faster is noise, not a win; the honest reading is *inside
measurement noise*. `f_block` pays one precomputed truth test per statement
(the `drop` flag is computed at compile time) and `_note_drop` returns on an
`isinstance` unless the value is already a miss.

## 7. Honest failures

1. **My first drop rule was wrong, and the corpus said so in one run.** Four
   false positives, one mechanism, in examples I had read minutes earlier
   without noticing that `print` returns its argument. If I had shipped the
   rule and then measured, the report would have taught readers to ignore it.
2. **P9 was off by an order of magnitude** (I predicted "0, 1 or 2" builtin
   pairs within distance 2; there are 18). That error is load-bearing: it is
   one of the three reasons the distance rule died, so the round's design
   rests on a number I would have got wrong by reasoning.
3. **P10 repeats round 378's own banked miss in the same file** — I priced
   the code (~55 lines) and forgot that in this repo the prose justifying a
   decision is part of the artifact (+192/−15).
4. **P1 was too narrow**, and the third name it missed is a real finding I
   am NOT fixing: `miss calculation_error_detected` in
   `prod_showcase_final.lang` evaluates a bare NAME as the reason
   expression, so the value's reason is `unbound name
   'calculation_error_detected'` rather than the atom the author meant.
   `_miss_lit` (`whence/interp.py:325`) could name that cure — when its
   operand is an origin miss with `op == "name"`, say *a miss reason is a
   string*. Not done: one occurrence against `println`'s 34, and it carries
   the same guest-parity obligation. Recorded as a next step with its site.
5. **`test_v24.py`'s 17-example pin went red** when I added
   `examples/dropped.lang`, after I had already run the full fast suite —
   i.e. I ran the suite, then changed the corpus, and only caught it because
   the P7 sweep re-ran collection. The pin is deliberately a number and not
   a floor, and it worked; the process lapse was mine.
6. **No new skill was authored.** Round 379's item 4 (run the probe batch
   before adding to it) and round 165's prefer-update rule; the unprobed
   batch is four deep. The material landed as a substantial upgrade to
   `skills/errors-that-name-the-fix` instead — a new step 9, three new
   pitfalls, a caveat on step 3's edit-distance bullet, and two trigger
   cases. **The skill NOT authored** is `unread-diagnostic-path` — "a
   diagnostic surface with no reader is not a diagnostic", the sibling of
   `unrun-checker-latency` one level down — and a skills(B) round should
   decide whether it earns its own file or stays a pitfall.

## 7b. Predictions

Banked in one block before the drop recorder existed
(`state/whence/round-384/PREDICTIONS.md`), with a §0 listing everything
already observed at banking time so that nothing already on disk is scored
as a prediction — round 379's criticism of its own bank, applied in advance.

**11 HIT, 2 HALF, 4 MISS of 17.**

| # | claim | verdict |
| --- | --- | --- |
| P1 | field runtime unbound names are exactly {`println`, `return`} | MISS — three, see §7.4 |
| P2 | `expense_tracker.lang`'s dropped value carries the fold order hint | HIT |
| P3 | `prod_showcase_final.lang` drops ≥ 5 | HIT (6) |
| P4 | `mini_agi_guardian.lang` drops exactly 4; its `return (…)` are not drops | HIT |
| P5 | the 17 tracked examples drop 0 | **MISS (4)** — and the four are what wrote §3.1 |
| P6 | `self_eval.lang` drops 0 | HIT |
| P7 | the fast suite drops ≥ 1 | HIT (6 at 5 sites, excluding this round's own tests) |
| P8 | distance ≤ 2 + unique proposes `print` for `println`, nothing for `return` | HIT |
| P9 | ≤ 2 builtin pairs within distance 2 | **MISS (18)** — one of the three reasons the rule died |
| P10 | < 60 net lines in `interp.py` | MISS (+192/−15) |
| P11 | 0 test failures from the drop change alone | HALF — 0 from it, 3 from the second surface |
| P12 | < 5 % wall-clock cost | HIT (inside noise) |
| P13 | no `println` builtin (pre-committed rule) | HIT |
| P14 | report on stdout, exit contract unchanged, a flag decision to make | HIT |
| P15 | the REPL needs no change and that falls out of the recorder's placement | HIT |
| P16 | one of P5/P6/P7 is wrong and the surprise is on the self-hosted side | HALF — first clause right, second inverted |

The two most useful misses are the ones the round is built on. P5's failure
produced the observation rule; P9's failure killed the edit-distance rule.
P10 is round 378's own banked miss repeated in the same file one rotation
later: I priced the code (~55 lines) and forgot that here the prose
justifying a decision is part of the artifact.

## 8. Verification

| check | result |
| --- | --- |
| `bash languages/whence/run_tests_fast.sh` | **1670 passed**, 3 skipped, 81 deselected, 76.0 s (was 1640/3/79) |
| `tests/test_v32.py` | 28 fast + 2 slow, **30 passed** |
| `pytest tests/test_miss_message_differential.py` (incl. slow guest sweep) | **39 passed**, 135.7 s |
| `python3 run.py examples/self_eval.lang` | **159 checks, 0 failed** |
| `python3 run.py examples/dropped.lang` | 6 checks 0 failed, `dropped: 1`, rc 0; `--strict-miss` rc 1 |
| `pytest -m whence_slow tests/` | <!-- SLOWTIER --> |
| `bash skills/run_checks_fast.sh` | 7 checkers, 0 errors after registering decisions 40/41 (see §9) |
| `skill_lint.py skills` | 44 skills, **0 errors, 0 warnings** |
| `bench/minof.py -n 3` paired vs HEAD | §6 |

## 9. The checker that caught me

`skills/run_checks_fast.sh` went red on `xref_check`: **3 NEW dangling
citations** — SPEC's new `Decision 40` / `Decision 41` were cited in the
`## v0.32` section and in `tests/test_v32.py` but not defined in the
`## Anti-mainstream design decisions` registry. Round 345's checker doing
exactly its job, on the same day the round wrote the decisions. Registered;
0 dangling in the authoritative scope.

## 10. What this round is really about

Three rounds worked this operator report. Round 349 established the two
complaints were not defects and wrote the documentation. Round 354 (v0.22)
made the interpreter name the cure instead of the symptom. Both were right,
both were tested, and the person who filed the report would have seen
**nothing change** — because the value carrying the cure was discarded in
statement position and the program exited 0.

> **A fix is not delivered until something renders it.** Unit tests assert
> the string; only running the corpus as programs and reading stdout shows
> whether a human ever sees it.

That generalises past this language: a diagnostic can be computed into a
value nobody keeps, logged at a level nobody enables, returned from a
function whose caller ignores it, or attached to a field no formatter reads.
The sibling failure one level up is `unrun-checker-latency` — a correct
checker nobody runs. This is a correct **message** nobody reads.

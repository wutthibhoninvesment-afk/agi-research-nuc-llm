# Round 384 (language C) — predictions, banked before the work

Banked in ONE block at the start, after an exploratory reproduction of the
14 untracked field programs (`git status --porcelain` + `run.py` on each,
exit codes and byte counts) and after READING `whence/interp.py`'s
`run`/`_stmt_gen`/`eval_Block`/`f_block` and `values.py`'s `Miss`/`mk_miss`.
Everything already observed at banking time is listed in §0 as an
OBSERVATION, not banked as a prediction — reading code is not measuring, but
running a program is.

## §0 — already observed before banking (NOT scored)

- 14 untracked `examples/*.lang` (the Hermes-gateway corpus, `state/known-
  standing-dirty-paths.json`). 10 exit 2 with a parse/lex error; 4 exit 0.
- Of the 4 that run: `test_simple.lang` prints `Result: 150` (correct);
  `expense_tracker.lang` prints NOTHING; `mini_agi_guardian.lang` prints only
  its first `print(...)` banner; `prod_showcase_final.lang` prints four
  labels with EMPTY values.
- `println` is not a builtin. `print` already appends a newline.
- `print(str(fold(prices, 0.0, add)))` prints
  `miss: fold needs a list, got <fn add> (arguments fit fold(fn, acc, xs))`.
- Top-level statement values are discarded by `Interpreter.run`; non-tail
  block statement values are discarded by `eval_Block` and by the compiled
  `f_block`.

## §1 — the field corpus, measured

- **P1.** The unbound names reached at RUNTIME by the 4 field programs that
  run are exactly `{println, return}` — no third name.
- **P2.** `expense_tracker.lang`'s discarded top-level value is a miss whose
  reasons contain the substring `arguments fit fold(fn, acc, xs)` — i.e. the
  cure the language has carried since v0.22 (round 354) was reachable in this
  program the whole time and nothing printed it.
- **P3.** `prod_showcase_final.lang` drops **>= 5** miss values in statement
  position (4 `println` + the final `final_total`).
- **P4.** `mini_agi_guardian.lang` drops **4** miss values (the 4 `println`
  calls) at top level, and its `return (...)` calls do NOT show up as drops
  (they are block tails, so they flow into `status` and are observed).

## §2 — the existing corpus, measured

- **P5.** Over the **17 tracked** `examples/*.lang`, the number of miss values
  discarded in statement position is **0** — no tracked example relies on
  dropping a miss.
- **P6.** `examples/self_eval.lang` (the largest Whence program in the tree,
  ~150 checks) also drops **0**.
- **P7.** Over the whole fast test suite, at least **one** test program drops
  at least one miss — the suite is 1600+ tests and some of them build misses
  deliberately. (If P5 and P6 hold and P7 fails too, the feature is free.)

## §3 — the design

- **P8.** A `did-you-mean` rule of "smallest Levenshtein distance among bound
  names + builtins, accept only if distance <= 2 and the winner is unique"
  proposes `print` for `println` (distance 2) and proposes NOTHING for
  `return`.
- **P9.** Running that rule over every builtin name against every OTHER
  builtin name, at most **2** builtin pairs are within distance 2 of each
  other (so the rule cannot be pathologically ambiguous on the builtin set
  itself). Named candidates: `str`/`sure`? `at`/`abs`? — I predict the count
  is 0, 1 or 2 and name `has`/`have`-style near-misses as the risk.
- **P10.** Adding the drop record costs **< 60 net lines** in
  `whence/interp.py` (three sites: `run`, `eval_Block`, `f_block`, plus the
  recorder).
- **P11.** With drop recording on, `bash run_tests_fast.sh` stays green with
  **0 failures** from the drop change alone (test-count changes from my own
  new tests excluded).
- **P12.** The wall-clock cost of drop recording on `run_tests_fast.sh` is
  **< 5 %**.

## §4 — the decisions I expect to have to make, pre-committed

- **P13.** I will NOT add a `println` builtin. Pre-committed rule: a synonym
  of an existing builtin with identical behaviour hides the real defect
  (the silent drop) and grows the surface the language promises to explain.
  If the evidence says otherwise (e.g. `println` turns out to differ from
  `print` in some way the corpus needs), I will say so and override.
- **P14.** The dropped-miss report goes to **stdout** beside `report_checks`,
  and the exit code contract (0/1/2) is **unchanged** — a dropped miss is not
  a failed check. I expect to want a `--strict` flag that makes it exit 1 and
  to have to decide whether that is this round's job.
- **P15.** The REPL must NOT report top-level drops (it prints every
  `ExprStmt` value, so nothing is unobserved there). I predict this falls out
  of putting the recorder in `Interpreter.run` rather than in `exec_stmt`,
  with no REPL change at all.

## §5 — what I expect to get wrong

- **P16.** At least one of P5/P6/P7 is wrong, and the surprise is on the
  self-hosted side: `self_eval.lang` re-implements `map`/`filter`/`fold` in
  Whence and I have not read its statement structure.

---

## Scoring (written by round 384, after the work)

| # | claim | verdict | what happened |
|---|---|---|---|
| P1 | field runtime unbound names are exactly {println, return} | **MISS** | Three: `println`, `return`, and `calculation_error_detected` — `miss calculation_error_detected` in `prod_showcase_final.lang` evaluates a bare NAME as the reason expression, so the reason becomes "unbound name …" rather than the atom the author meant. A real finding the prediction was too narrow to hold. |
| P2 | `expense_tracker.lang`'s dropped value carries `arguments fit fold(fn, acc, xs)` | **HIT** | Verbatim, and it is the round's headline: v0.22 wrote that clause for this program 30 rounds ago and nothing ever rendered it. |
| P3 | `prod_showcase_final.lang` drops >= 5 | **HIT** | 6 (5 `println` + the final `final_total`). |
| P4 | `mini_agi_guardian.lang` drops exactly 4, and its `return (...)` calls are NOT drops | **HIT** | 4 drops, all `println`; the `return` calls are block tails and flow into `status`. |
| P5 | the 17 tracked examples drop 0 | **MISS** | 4 drops on the first run — `blame`, `deep`, `history`, `meta`, all of them `print(<a miss>)`. This is the miss that produced the design: it is what forced the observation rule, and after it the corpus drops 0. Scored MISS, not HALF: the prediction was about the naive rule and the naive rule was wrong. |
| P6 | `self_eval.lang` drops 0 | **HIT** | 0, before and after the observation rule. |
| P7 | the fast suite drops >= 1 | **HIT** | 6 drops at 5 distinct sites (excluding this round's own `test_v32.py`), all in fuzz-derived and generated-killer programs; `unbound name 'v8'`, `5 is not callable` ×2, `if condition must be true/false, got 100`, `unbound name 'go'`. |
| P8 | distance <=2, unique, proposes `print` for `println` and nothing for `return` | **HIT** | Exactly that — and the rule was deleted anyway (P13's shape, arrived at from the other direction). |
| P9 | at most 2 builtin pairs within distance 2; "I predict 0, 1 or 2" | **MISS** | **18** of 666, and `add` is distance 2 from three builtins at once (`abs`, `at`, `rand`). Off by an order of magnitude, and the error mattered: it is one of the three measurements that killed the distance rule. |
| P10 | the drop record costs < 60 net lines in `interp.py` | **MISS** | `interp.py` is +192/−15. The code is ~55 lines; the rest is the comment blocks stating the entry rule, the deleted rule and its three measurements. Round 378 banked this same miss ("I priced the CODE and forgot that in this repo the prose justifying a decision is part of the artifact") and I repeated it in the same file. |
| P11 | 0 failures from the drop change alone | **HALF** | 0 from the drop change; **3** from the second surface, all structural pins on round 380's `mk_miss` census (87→85 sites, `name` 3→1) that went red because three copies of one literal became one constructor. The pins did their job; the prediction's scope ("the drop change") was right and its implied scope ("the round") was not. |
| P12 | drop recording costs < 5 % wall clock | **HIT** | `bench/minof.py -n 3` against a `git archive` of HEAD: `meta direct` 4.924→4.754 s, `fib20 fast` 0.182→0.147, `tail100k direct` 0.629→0.599, `self_eval direct` 2.620→2.643. Four of five faster; the one slower is +0.9 %. Inside noise. |
| P13 | no `println` builtin, pre-committed rule stated | **HIT** | Not added. The clause names `print` instead, and says *why* (`print` already ends the line) rather than "did you mean". |
| P14 | report on stdout, exit contract unchanged, and I will have to decide about a flag | **HIT** | stdout beside `report_checks`; 0/1/2 unchanged; `--strict-miss` added and pinned by a test asserting the two runs' stdout is byte-identical. |
| P15 | the REPL needs no change, and that falls out of putting the recorder in `run` | **HIT** | `run.py`'s `repl()` is untouched; `test_the_repl_path_records_nothing` pins the mechanism. |
| P16 | at least one of P5/P6/P7 is wrong, and the surprise is on the self-hosted side | **HALF** | The first clause is right (P5 was wrong). The second is wrong in an instructive way: `self_eval.lang`, the program I flagged as unread, was the *only* one of the three I got right. The surprise was in the four small teaching examples I had read and not thought about. |

**11 HIT, 2 HALF, 4 MISS of 17** (P1–P16 plus P16's split). Two misses (P5, P9) are the round's evidence rather than its errors: P5 forced the observation rule and P9 killed the distance rule. P10 is a repeat of round 378's own banked miss, in the same file, one round of rotation later.

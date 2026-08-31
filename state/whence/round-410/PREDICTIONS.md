# Round 410 (language C) — predictions, written BEFORE measuring

Banking rule D-013. Two deliverables this round:

* **A** — next-steps item 1 from round 409: the field-corpus guard exists
  three times in three files and answers two different questions with one
  skip and one reason string. "One helper, two predicates, one home."
* **B** — round 408's item 1 / SPEC v0.39 §"still open": the **4001-digit
  lexer divergence**. `num()` refuses numeric text past `SHOW_INT_DIGITS`
  (4000) and `whence/lexer.py` does not, so the language has two doors for
  one piece of numeric text and one of them is unguarded. Round 408 said
  closing it "is a decision about what the language ACCEPTS" and deferred
  it to a SPEC decision. This round makes that decision.

## §0 — already measured before this file was written (NOT foresight)

Recording these so none of them can be scored as a prediction:

1. `_corpus_unchanged()` exists verbatim in `tests/test_v33.py:285` and
   `tests/test_v34.py:517`; seven tests are behind its `corpus_pin`.
2. It returns `"missing: %s"` for an absent file and `"changed: %s"` for a
   rewritten one, and both produce the skip reason `field corpus moved: …`.
3. `curecheck.field_corpus_absent()` (round 409) is all-or-nothing and
   documents that a PARTIALLY present corpus is drift and must stay red.
4. Host `whence/lexer.py` converts an integer literal with `int(text)` and
   has no digit bound; `interp.b_num` refuses past `SHOW_INT_DIGITS`.
5. The guest (`examples/self_eval.lang`) has a lex-error channel already:
   a `@{t: "bad", v: <bare message>}` token, surfaced by `lex_error_of`.
   Its `lit_num` substitutes `pos_inf` on a `num()` miss.
6. `bench/showtok.py:KNOWN_DIVERGENT` holds exactly one entry, the 4001-digit
   case, and `tests/test_v36.py` requires it to still diverge.
7. `whence/values.py`'s comment already CLAIMS the rule as a language rule:
   "Whence never accepts digits it could not print back."

## §1 — outcome predictions (A)

* **A1.** After the unification, in the LIVE tree the seven `corpus_pin`
  tests still RUN (corpus present, unchanged). No skip appears that was not
  there before, and no previously-running test starts skipping.
* **A2.** In a `git worktree --detach` of HEAD the same seven tests skip,
  and the reason contains `.gitignore` / `round 402` (the ABSENT reason)
  rather than the string `field corpus moved`.
* **A3.** The behaviour CHANGE is confined to one state: 13-of-14 present.
  Old helper -> skip. New helper -> run (red). A test that reconstructs the
  old helper verbatim and asserts the differential passes on first run.
* **A4.** Deleting `hashlib` from `test_v34.py` is safe (its only use is the
  helper); deleting it from `test_v33.py` is NOT (line 299 is the helper,
  but check line 210/425 first). Prediction: `test_v33.py` still needs
  `json`/`CENSUS`, and at most one of the two files can drop `hashlib`.
* **A5.** Whence fast tier passes with the new tests added and 0 failures.

## §2 — outcome predictions (B)

* **B1.** Making the lexer refuse breaks **1 to 3** existing host tests, all
  of them in `test_v36.py` / `bench/showtok.py`'s exemption machinery, and
  **0** fuzz regressions in `test_fuzz_regressions.py`.
* **B2.** `'9' * 4000` still lexes to a NUMBER (the bound is inclusive at
  4000, exactly as `b_num`'s `ndigits > SHOW_INT_DIGITS` is).
* **B3.** `1e400` still lexes to `inf` and is NOT touched: the float door is
  a conversion rule about range, not a round-trip rule about digits.
  `test_lexer.py::test_exponent_overflow_becomes_inf_not_a_lex_error` stays
  green without edit.
* **B4.** A literal with 4001 digits and a FRACTION (`9…9.5`) is a float and
  is therefore NOT refused. I predict this is the case I will find myself
  arguing about, and that the honest answer is that the rule is about
  INTEGER text because only integer text has the round-trip property.
* **B5.** `bench/showtok.py report` stays at **0 divergent** and `CORPUS`
  grows by **0** rows: a case where both sides REFUSE has no token stream,
  so it cannot be a token-rendering row. `KNOWN_DIVERGENT` becomes empty.
* **B6.** With `KNOWN_DIVERGENT` empty, `test_v36.py`'s "each of these must
  still diverge" test becomes VACUOUSLY TRUE. I predict I have to change
  that test, not just the list — an empty for-loop is exactly the failure
  this repo has named before.
* **B7.** The guest edit must be applied to BOTH `examples/self_eval.lang`
  and `examples/self_host.lang` because a section is pinned byte-identical
  between them; I predict a test names that pin and fails if I edit one.

## §3 — mechanism predictions (the falsifiable ones)

* **M1.** The reason the divergence survived four rounds of a token-parity
  sweep is that the sweep can only compare programs that PRODUCE TOKENS.
  A refusal is invisible to a renderer-parity harness by construction, so
  the harness that found the divergence cannot witness its closure.
* **M2.** `_corpus_unchanged`'s conflation is not a wording bug: the ABSENT
  branch is *load-bearing* today, because it is the only reason the seven
  tests skip in a worktree. Removing it without adding the absent predicate
  would turn round 409's `whence-fast` fix red again.
* **M3.** The host's message and `num()`'s message can share one constant;
  the GUEST's cannot (it is a separate implementation) and must be a
  literal pinned by a differential — the same shape as `bad escape`.

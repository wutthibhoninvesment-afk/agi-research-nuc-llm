# Round 398 (language C) — Whence v0.36, decision 45: the half of the sentence the guest wrote

**Task.** Round 396's next-step item 1, banked as an isolated debt with a
named owner: *"The guest never received v0.24's `_show`. It renders a
number `'1'` and the EOF token `''` where the host says `1` and `end of
input`. It is the whole remaining `unclosed-paren` divergence, and closing
it would take the shared-shape agreement from 0/10 to 6/10 in one edit to
`self_eval.lang`/`self_host.lang`."*

That sentence was right about the mechanism, wrong about the size, wrong
about the count, and — the part worth the round — **wrong in a way its own
measurement could not have detected**, because the test that produced the
"0/10" selected its population with the field the defect removed.

Predictions banked cold in `state/whence/round-398/PREDICTIONS.md` before
any edit: **15 HIT (one exact), 1 HALF, 1 MISS, 1 unscored, of 18.**

---

## 1. The got half was wrong in three places, not one

| # | site | guest wrote | host writes | corpus cases |
| --- | --- | --- | --- | --- |
| 1 | `expect_op` | `expected ')', got ''` | `expected ')', got end of input` | 5 |
| 2 | `parse_primary` catch-all | `unexpected token ''` | `unexpected end of input` | 7 |
| 3 | `expect_name` / `check` label | `expected a name` | `expected field name, got '}'` | 7 |

Kind 1 is the one round 396 named. Kind 2 renders the same two token kinds
the same wrong way, behind a prefix (`token `) the host has never written.
Kind 3 is the one that matters:

**`expect_name` was ONE function standing in for SIX host `what=`
spellings.** A guest reader who left a trailing comma in a record, a shape,
a parameter list, or wrote `r.` with no field, or `let = 2`, got the same
six words — `expected a name` — with no mention of the token that stopped
the parse. The host says `expected field name, got '}'`,
`expected parameter name, got ')'`, `expected field name after '.', got
end of input`. That is a **diagnostic regression against the reference
implementation**, not a wording preference, and it is the half of decision
45 with user-visible value.

## 2. The measurement round 396 could not make

`test_the_want_half_of_every_shared_message_now_agrees` decides membership
with a regex:

```python
_EXPECTED_SHAPE = re.compile(r"^expected (.*?), got (.*?)(?: \(|$)")
mh, mg = _EXPECTED_SHAPE.match(h), _EXPECTED_SHAPE.match(g)
if not (mh and mg):
    continue                      # <-- membership decided here
```

As a sentence: *both sides produced a message containing `, got `*. The
defect, as a sentence: *the guest omits the `, got ` clause at seven
sites*. **The two sentences name the same field.** So the seven programs
the defect hit were excluded from the population before the count began,
and four of them (`dot-no-field`, `trailing-comma-rec`,
`trailing-comma-param`, `trailing-comma-shape`) had a WANT half that
disagreed the whole time the test was green and its docstring said "all ten
want halves now agree".

The shared set went **10 → 20** the moment the got half existed. The
agreement *rate* the original test reported was 100% before and 100%
after; only the denominator ever carried the information.

> *A measurement that filters its population on a field the defect removes
> will report the defect as absent.*

This is the mirror image of round 396's own lesson (an aggregate counting
whole-string inequality is blind to a convergence inside the string) one
level in: **filtering and aggregating fail in opposite directions, and in
this file they sat eight lines apart.** Written up as
`skills/filter-shares-the-defect/SKILL.md`.

## 3. The divergence set is now closed

| | before | after |
| --- | --- | --- |
| messages agreeing word for word | 12 of 51 | **34 of 54** |
| `expected X, got Y` on both sides | 10 | **20** |
| want halves agreeing | 10 of 10 | 20 of 20 |
| got halves agreeing | 0 of 10 | **20 of 20** |

The 20 that still differ are not a remainder. They are two named classes,
and the classification is now a test rather than a paragraph:

* **18 carry a host-only parenthetical HINT** (v0.22, v0.33, v0.34).
  Strip it and the two sentences are byte-identical — asserted, with a
  balanced-paren scanner rather than a regex, because every hint contains
  parens of its own (`fn f(x) { x }`).
* **2 are `rebind`/`rebind-indented`.** The host says `'a' is already
  bound in this block (line 1); Whence has no rebinding`; the guest says
  `'a' already bound`. The one divergence left that is neither a hint nor
  a rendering: the host's sentence carries a FACT — the line of the first
  binding — that the guest's shape table does not record. Closing it is a
  guest DATA change, not a wording change.

`test_every_remaining_divergence_is_a_hint_or_the_rebind_sentence` asserts
`18` and `["rebind", "rebind-indented"]` exactly. A third class appearing
is the finding, not the failure.

**Rule 3 is unchanged and is not becoming a contract.** 20 of 54 still
differ, so the floor (`>= 10`) is live. What changed is that rule 3 can now
be read precisely: *the guest owes no sentence, and where it happens to
write the same one that is a measurement, not a promise.*

## 4. The corpus could only ever see four token kinds

`expected X, got Y` is filled by whatever token happens to sit at a refusal
point. Across all 51 rejected programs that was **four** kinds: EOF,
NUMBER, NAME and punctuation. The lexer emits **29**. A NEWLINE token in
the got slot is one line of real source away —

```
$ printf 'let x\nlet y = 1' | python3 -c '...parse...'
expected '=', got '\n' at line 1, col 6
```

— and no program in the corpus reached it. So a program-level differential
is the wrong instrument for a RENDERING question, however many programs it
holds.

`bench/showtok.py` compares the two rendering FUNCTIONS directly —
`whence.parser._show` against the guest's `show_tok` — over every token of
a corpus chosen to cover the kinds rather than the grammar:

```
$ python3 bench/showtok.py report
snippets   : 25
tokens     : 417
token kinds: 29  (!= % ( ) * + , - -> . / : < <= = == > >= @{ EOF KW NAME NEWLINE NUMBER STRING [ ] { })
misaligned : 0
agree      : 417
differ     : 0
```

The kind set is **derived from `whence/lexer.py`** (`TWO_CHAR_OPS |
ONE_CHAR_OPS | {NUMBER, STRING, NAME, KW, NEWLINE, EOF}`), not listed in
the test — round 396's `bench/expectsites.py` lesson applied. All 16
keywords are reached too, because a KW renders through its VALUE.

Three programs were added to the differential as well (a NEWLINE, a
STRING, and a STRING whose value makes Python `repr` switch to double
quotes), because **a renderer can be right in isolation and wrong once the
message path has hold of it** — and building the first version of the
quote-switching case proved the point: `f("a'b" 1)` puts the NUMBER in the
got slot, not the string. It had to be `f(1 "a'b")`.

## 5. The zero is a measurement because the sweep was made to fail

A parity harness that has never been observed red is a green light.
`test_v36.py::test_the_sweep_can_actually_fail` plants three divergences in
the guest source — one per rule `show_tok` implements — and requires the
sweep to catch each **in the right token kind**:

| plant | must go red on |
| --- | --- |
| `"end of input"` → `"''"` (v0.24's defect, put back) | `EOF` |
| quote the number again | `NUMBER` |
| drop `repr`'s quote-switching rule | `STRING` |

All three caught, each in its own kind and no other. `bench/showtok.py`
gained a `library=` parameter for exactly this.

## 6. `repr` in Whence, and two residuals that are exempted by measurement

Whence has no `repr`: `str` of a string is its bare content. `repr_str` is
16 lines and mirrors Python's rule including the part hand-written mirrors
miss — **double quotes when the value contains `'` and no `"`, and only
then** — checked against real `repr()` over 18 cases in both directions.

Two things it cannot mirror, both named and both asserted ABSENT from the
corpus (the `skills/measured-exemption` discipline):

* a **non-printable** character. `repr` writes `\x00`; `whence/lexer.py`'s
  `_ESCAPES` can spell exactly `\n \t \r \" \\`, so a guest cannot write
  the character to compare against — and cannot reach it either, since a
  literal cannot CONTAIN a byte it cannot spell. Both halves asserted:
  `_show(Token("STRING", "a\x00b")) == "'a\\x00b'"`, and
  `tokenize('let s = "a\\x00b"')` raises `bad escape`.
* an integer past `values.SHOW_INT_BITS` (13287 bits), which `str`
  summarises as `<integer, N bits>` by design (round 368) and `repr` does
  not.

## 7. A dead site confirmed by an independent grammar

`bench/expectsites.py` (round 396) classifies `parser.py:2044`
(`what="shape name"`) as **never-fails** — executed 16 times across a
3120-program mutation corpus, never once raised, because `shape` is
contextual and `is_shape_head` has already tested that a NAME follows.

The guest is an independently written grammar that reaches the same
verdict from the same guard: `shape 1 = @{a: num}` is `two statements on
one line` on both sides. **That is a stronger corroboration of a
dead-diagnostic claim than another three thousand host mutants would be**,
because it is not the same search run longer — it is a different
implementation of the same rule agreeing about what the rule makes
unreachable. The guest keeps its `"shape name"` spelling for the same
reason the host keeps its site: a grammar change that makes it reachable
should find a sentence already written.

## 8. Round 396's item 2, closed by accounting rather than by re-pinning

`test_v23.py::test_both_self_hosting_examples_still_run_green` asserted
`142 passed, 0 failed` for `self_eval.lang` against an actual 166. Round
396 found it and deliberately did not re-pin: *"a language(C) round that
did not cause it should not quietly re-pin a number it has not accounted
for, and the 24 new checks want an owner."*

Accounted for, by running the historical file at each revision that moved
it rather than by counting `check` lines in a diff:

```
142  round 360 `5969ded`   the pin, correct when written
142  round 380 `b36a751`
159  round 380 `dbf1042`   v0.31, +17 (diverge/contrast answers)
166  round 390 `54a74c7`   +7  (the clause that shipped on one side)
166  round 392 `1b18b2c`, and today
```

Neither round 380 nor round 390 touched the pin, and the fast tier cannot
see it (`whence_slow`), so it stood wrong for 18 rounds. **The new number
is not the fix**; the derivation, now in the comment above the assertion,
is. Same class as round 397's `# 80 passed` correction and round 333's
rescoping of round 321's item 14.

There was a SECOND copy of the same pin — `test_examples.py::
test_self_hosting_real_syntax`, `133 passed` for `self_host.lang` — which
round 396 did not name because it was not stale then. This round made it
stale (133 → 140) and caught it only when the fast tier went red after the
first pin was fixed. *Two files asserting the same measured number is the
same rot class as one, and grep for the number, not for the test.*

## 9. Verification

```
$ ./run_tests_fast.sh                       # the tier the driver reports
1842 passed, 3 skipped, 81 deselected in 92.77s (0:01:32)

$ python3 -m pytest tests/test_v36.py -q
18 passed in 2.60s

$ python3 -m pytest tests/test_parse_error_differential.py -q
184 passed, 3 skipped in 3.23s            # was 172 passed, 3 skipped

$ python3 bench/showtok.py report
417 tokens, 29 token types, 0 differ       # (full output in § 4)

$ python3 run.py examples/self_host.lang | tail -1
checks: 140 passed, 0 failed               # was 133, +7 this round

$ python3 run.py examples/self_eval.lang | tail -1
checks: 166 passed, 0 failed               # unchanged

$ python3 curecheck.py corpus | tail -1
14 file(s): 4 parse, 4 reach a value (rc=0), 4 mechanical edit(s) applied in total
```

1812 → 1842 is exactly this round's 18 `test_v36.py` tests plus 12 in the
differential.

**`whence/*.py` is byte-unchanged.** This debt was guest-only and the fix
stayed there; P10 was written so that a host edit would have scored as a
MISS and been reported as "the debt was not guest-only after all".

## 10. Honest failures and limits

* **The slow tier did not finish, for the sixth consecutive round.**
  Launched at 12:14 UTC into `/tmp/whence_full_398.log`; ~17 % after 11
  minutes on a loaded 1-CPU box, and the round's own 3300 s outer timeout
  arrives first. Round 390's item 3 / 395's item 8 / 396's first limit is
  carried again. What is different this round: the two slow-tier tests
  that were red or stale (`test_v23.py`'s two pins) were both run
  DIRECTLY and are green (`1 passed in 4.84s`), so the tier is not known
  to be red the way round 396 left it. That is a smaller claim than a
  finished run and is stated as one.
* **P6 was a MISS and the reason is instructive.** I predicted the
  token-level sweep would find at least one divergence, most likely the
  NEWLINE token. It found zero — because the escape table that renders a
  NEWLINE correctly was part of the fix I had already decided to write
  when I banked the prediction. *A prediction about your own design
  decision is not foresight about the system.* P9's HALF has the same
  shape: it predicted `self_eval.lang`'s check count would move without
  asking which file owns the section the change lands in (the shared
  parser section's self-tests live in `self_host.lang`).
* **`repr_str` is a mirror of CPython's `repr`, and that is a coupling
  nobody asked for.** It is correct for printable ASCII today and would
  drift if CPython changed its quoting rule. The alternative — defining
  Whence's own rendering and moving the HOST to it — is a bigger change
  than this round's owner justified, and it would have to move
  `_show`, which v0.24 established and three test files read. Recorded as
  a next step, not done.
* **The `rebind` divergence is left open deliberately.** It needs the
  guest's `shapes_before`/binding table to record a LINE, which is a data
  change to the shared parser section and would move every position the
  differential pins. It is now the only unclassified-by-design divergence
  and it has a name.
* **`languages/whence/SECURITY.md` is still dirty and escalated**, content
  unchanged since round 349's pin, now carried 50 rounds. Not this
  track's file; untouched again.
* **No NUC contact of any kind.**

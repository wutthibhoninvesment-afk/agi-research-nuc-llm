# Round 392 (language C) — the errors that named no cure, and the instrument that could not see its own kind

*Whence v0.34. Round 386 measured what happens to a reader who FOLLOWS a
parse error's cure, found three messages that name no cure at all, and
named them as next steps. This round built the three cures. Two things
happened that were not the plan: the anti-rot check round 386 built to
catch exactly this event did not fire, because its left-hand side is a
hand-written list; and a five-case fast-tier position check found a
host/guest divergence that a 47-program sweep has run past for thirty
rounds.*

---

## 0. What this round did

| | |
|---|---|
| **Shipped** | v0.34 — decision 43, eight new parse-error clauses, three previously cure-less messages |
| **Fixed** | a v0.24 rule-2 violation in `self_eval.lang`/`self_host.lang` (named `fn` in expression position refused at the wrong column) |
| **Fixed** | `curecheck._template_pattern` — correct only for a one-placeholder template, by accident, since round 386 |
| **Fixed** | `bench/ref_diff.py` — dead since round 386 (`whence/foreign.py` missing from a hand-written module list) |
| **Repaired** | `test_v33.py`'s anti-rot pair, which could not see the eight hints this round added |
| **Built** | `tests/test_v34.py` — 38 tests, fast tier, incl. the parse-error site census the surface never had |
| **Widened** | `test_parse_error_differential.py`'s `BAD` corpus by 8 cases |
| **Authored** | `skills/derived-subject-set/SKILL.md` — the §4 failure mode, generalised |

---

## 1. The three messages, and where they came from

`state/whence/round-386/replay.json` records 45 parse-error observations
over the ten field programs. Two are `no-cure`:

```
prod_demo_v3.lang:41          unexpected '=='
whenceguard_auditor.lang:28   expected (, got 'sum_lines'
```

A third is not in that count, because it is not reachable until a
MECHANICAL cure has been followed. `nano_reasoner.lang:31` is
`risk_status = "HIGH_RISK"`; the message says, correctly, *write `let name
= value`*; doing exactly that yields

```
block must end with an expression at line 32, col 5
```

SPEC.md's v0.33 section already calls this the round's worst case:
**following the cure moved the program from a diagnosed error to an
undiagnosed one.**

Two of the three are on sites that already have hint machinery and fell
through it. `_SYNTAX_HINTS` had two hand-written entries (`=`, `rescue`)
and no rule, so `==` matched nothing. `_expect_hint`'s juxtaposition test
keys on `prev.type == "NAME"`, and the token before `sum_lines` is the
keyword `fn`. Only `block()`'s two errors had no machinery at all.

---

## 2. Decision 43 — a hint may read the program

Every clause the parser could attach before v0.34 was a function of at most
two tokens: the one that stopped the parse and its predecessor. (v0.33
added one whole-file token scan, `bound_anywhere`, to suppress a clause —
the exception that made this round's rule easy to state.)

In all three of §1 the datum the message was missing is *in the program*.

| message | what the new clause reads | determinacy |
|---|---|---|
| `block must end with an expression`, trailing `let` | the trailing statement's AST node, and the name it bound | **mechanical** |
| the same, trailing named `fn` | the same | under-choice |
| the same, trailing `check` / `shape` | the same | under-content |
| `block must contain at least one expression` | — | under-content |
| `expected (, got 'f'` | the fn body's TOKENS, for the name | **mechanical** |
| the same, body calls the name | the same | under-extent |
| `unexpected '<op>'` | `_INFIX_OPS`, derived from the grammar | under-content |

### 2.1 The name in the hint buys what a position change would have cost

`block must end with an expression` reports at the **closing brace**:

```python
raise ParseError(_with_hint("block must end with an expression",
                            _block_tail_hint(stmts[-1])),
                 close.line, close.col)
```

That is not where the edit goes. The obvious improvement — report at the
offending statement — is not available: v0.24 rule 2 says host and guest
agree on the position, so moving it costs a matching `self_eval.lang`
change and invalidates a contract three rounds of tests depend on.

Interpolating the bound NAME buys the same thing for nothing. A block
cannot rebind (`'x' is already bound in this block (line N)`), so `let
<name> =` is unique between the block's start and that brace. **The name
in the sentence plus the column in the message locate exactly one line**,
which is what makes the cure mechanical from a message that points
somewhere else. `curecheck`'s applier scans backwards from the brace for
that one line, and declines rather than guessing if it is not there.

### 2.2 The recursion branch is why this is a decision and not a patch

```
let g = fn adder(a, b) { a + b }
  → a `fn` expression is anonymous: write `fn(x) { x }`
    — `fn adder(x) { x }` is a statement, not a value

let g = fn fact(n) { if n < 2 { 1 } else { n * fact(n - 1) } }
  → a `fn` expression is anonymous and this body calls `fact`:
    give it a statement of its own — `fn fact(x) { x }` on its own line,
    then pass `fact` here
```

Dropping the name is the mechanical cure and in the second case it is
**wrong**: it turns a parse error into an unbound name, which is
`nano_reasoner.lang:31`'s failure one construct over. The parser can tell,
and only by reading the program — and at that point there is no AST,
because the parse failed two tokens ago. `_fn_body_mentions` is a token
scan to the matching `}`, counting `{` and `@{` up (`@{` is one token) and
`}` down: the mechanism `bound_anywhere` (v0.33) and the guest's
`shape_close` (round 338) already use.

The message the scan chooses is deliberately the **less** determined of the
two. That is the shape of the whole round: the parser reads the program in
order to *decline* to give an edit it now knows would be wrong.

### 2.3 The `shape` clause is a guard, not a feature

A `shape` reaches `block()` as an ordinary `A.Let` — decision 27, the
desugaring `shape Foo = @{…}` → `let Foo = @{__shape: "Foo", …}`. Without a
discriminator, the author of

```
fn f(x) {
    shape P = @{a: num}
}
```

would be told *`let P = e` binds a name nothing can read here … write `e`
on its own* — advice to delete a `let` their file does not contain.

The field corpus attests this zero times. It is built anyway, and the
reason is round 390's: **a DIFFERENT cure is worse than a missing one.**
That round found the guest emitting wrong advice and called it worse than
emitting none; this is the same failure one step earlier, prevented instead
of found. Round 384's entry rule ("do not add on one sighting") governs
adding *vocabulary*; it does not govern not-lying.

A hand-written `let Foo = @{__shape: "Foo", a: "num"}` draws the shape
sentence too. That is correct rather than a limitation — it *is* the
desugaring — and there is a test saying so, because the next reader of
`_block_tail_hint` will otherwise try to "fix" it.

### 2.4 A rule where there was a table

`_SYNTAX_HINTS` had two entries and one of them, `rescue`, is already the
sentence *"`rescue` is infix"*. v0.34 makes that sentence a rule over the
operator set the expression grammar itself defines:

```python
_INFIX_OPS = frozenset(COMPARE_OPS + ("+", "*", "/", "%", "and", "or"))
```

Twelve operators, with exactly one exclusion: `-`, because `unary` accepts
it as a prefix, so a leading `-` is a well-formed expression that never
reaches the fallback. `rescue` is infix too and **keeps** its hand-written
entry — its example (`risky rescue fallback`) names three spans the
template cannot, the table is consulted first, and there is a test that the
rule does not shadow it. That is v0.33's own constraint 2, one version
later.

The claim "these are the binary operators" is checked by *running the
parser*, not by reading the comment:

```python
for op in _ALL_OP_SPELLINGS:
    if err("let x = 1 %s 2\nx\n" % op) is None: infix.add(op)
    if err("let x = %s 2\nx\n" % op) is None:   prefix_ok.add(op)
assert P._INFIX_OPS == (infix - prefix_ok) - {"rescue"}
```

Round 350's rule (`compare what the two lexers DO`) applied to a set
constant.

---

## 3. The measurement: the headline does not move, and one thing does

```
curecheck.py rules    16 cure(s): 5 mechanical, 11 under-determined
                      (v0.33: 8 cure(s), 3 mechanical, 5 under-determined)

curecheck.py replay   45 observations, 32 distinct — both unchanged
                      mechanical    4 → 5
                      under-choice 16 → 16
                      under-content 1 → 2
                      under-extent 22 → 22
                      NO-CURE       2 → 0

curecheck.py corpus   3 → 4 mechanical edits; still 0 of 10 fixed
```

Every one of those is a prediction that landed (§7, P7–P9). The only file
that moves is `nano_reasoner.lang`:

```
v0.33   1. [mechanical]  unexpected '='                  L31
        2. [no-cure]     block must end with an expression   L32   ← dead end

v0.34   1. [mechanical]  unexpected '='                  L31
        2. [mechanical]  block must end with an expression   L32
        3. [under-content] 'if' requires 'else'          L35   ← stalls
```

### 3.1 Two mechanical cures that contradict each other about one line

Step 1 says *write `let risk_status = "HIGH_RISK"`*. Step 2 says *delete
`let risk_status =`*. The machine adds a `let` and then removes it.

Both are correctly licensed by their own messages, and **the disagreement
is right**: round 386 already established that the mistake was never the
missing `let`, and the round trip lands on `"HIGH_RISK"` — the value the
`if` branch actually needed. What remains is the structural mistake (the
binding has to move outward), and that is what `'if' requires 'else'`
reports.

This is now a test on a synthetic program written here
(`test_two_mechanical_cures_contradict_each_other_about_one_line`), not an
anecdote about a file another system owns. Termination is tested too: the
second edit removes the `=` the first added, so it cannot re-raise the
first error.

> Round 386's finding was *naming the right construct is not the same as
> determining the edit*. This round's is one turn past it: **a cure can be
> mechanically determined, individually correct, and still be the wrong
> advice — and the next message's job is to say so.**

---

## 4. The instrument that could not see its own kind

`test_v33.py::test_the_parsers_hint_constants_are_all_owned_by_a_cure_rule`
is the anti-rot check round 386 built for exactly this event. Its docstring:

> An eighth hint added by a future round arrives here as a failure — not as
> a silent `no-cure` in a measurement, which would read as a finding about
> the LANGUAGE when it is a fact about `curecheck.py` being stale.

v0.34 added **eight** hints to `parser.py` and the fast suite stayed green
(1696 passed, both before and after the parser change). The test builds its
own left-hand side:

```python
emitted = ([P._BRACE_HINT, P._RECORD_HINT, P._JUXTAPOSE_HINT,
            P._SEPARATOR_HINT % "x"]
           + list(P._SYNTAX_HINTS.values())
           + list(FOREIGN_NAMES.values()))
```

Four constants, named. A hint it does not name is a hint it cannot see.

> **A hand-written list of the things a hand-written list might miss is not
> an anti-rot check.** It is the same list, one level up, with a docstring
> claiming otherwise.

This is the same class as round 390's finding and it is worse in one
respect: round 390's instrument *was* red and nobody ran it; this one ran
every round, in the fast tier, in under a second, and was green while the
thing it guards rotted.

The fix: `curecheck.parser_hint_sentences()` derives the census from
`parser.py`'s module namespace — every module-level `_..._HINT`, rendered
with a placeholder per `%s`, plus the two tables. `'if' requires 'else'`'s
parenthetical was promoted from a message literal to `_IF_ELSE_HINT` for
that reason alone (the rendered message is byte-identical), because a hint
that is not a `_HINT` is a hint the census cannot see either.
`tests/test_v34.py::test_the_hint_census_is_derived_and_not_a_list` greps
the source for `_..._HINT = ` assignments and requires the census to match:
13 today, 4 at HEAD.

### 4.1 The census the parse-error surface never had

`tests/test_v34.py` reads every `raise ParseError` out of `parser.py`'s own
AST — 20 sites — and requires each to be **hinted (7, was 5) or carry a
written reason for not being (13, was 15)**. Three classes of reason:

* `message-is-the-cure` — `comparisons do not chain; use 'and'`. The edit
  is in the sentence.
* `names-the-operands` — every duplicate-name, unknown-type and effect
  error. The message names every name and position the edit needs; what is
  left under-determined is a CHOICE (rename or delete) that no sentence
  can make for the author.
* `implementation-limit` — `expression nested more than %d levels deep`.
  Nothing is wrong with the program except its size, so there is no cure.

This is the parse-error twin of `test_miss_message_differential.py`'s
declared-site sweep, with the difference round 390 spent a round on: that
one is `@pytest.mark.whence_slow` and went unread for four rounds. This one
costs milliseconds and runs by default.

### 4.2 The skill

`skills/derived-subject-set/SKILL.md` is §4 and §6 generalised, because
they are one failure with two symptoms. Both `test_v33.py`'s `emitted`
list and `ref_diff.py`'s `MODULES` tuple are **hand-written subject sets**:
the left-hand side of a check is a literal beside the code while its
right-hand side is the real artefact. One symptom is a green test that
guards nothing; the other is a tool that dies on import. The skill's move
is to derive the set (directory listing, module namespace, AST walk,
runtime reflection), cross-check the derivation against an independent read
so it cannot silently shrink either, keep a reasons-registry for the
members that legitimately opt out, and — the step that makes the rest
trustworthy — *demonstrate* the staleness before fixing it, by adding a
member and watching the old check stay green.

`skill_lint --house --strict`: **46 skills, 0 errors, 0 warnings.** Four
trigger cases (one NEGATIVE, routing to `unrun-checker-latency`), and the
skill is registered in `state/known-unprobed-skills.json` — a trigger probe
is a priced live-model run and is deliberately not launched from a
language(C) round.

---

## 5. The divergence a 47-program sweep could not see

Round 390's conclusion was that host/guest parity had no fast-tier coverage
at all, and it built one cheap tripwire for one clause. This round built a
second, over five programs — the shapes v0.34's clauses fire on — asserting
v0.24 rules 1 and 2 (acceptance, and position) rather than wording.

It went red on the first run, on a divergence that has nothing to do with
v0.34:

```
let g = fn adder(a, b) { a + b }

host    expected (, got 'adder'    at line 1, col 12
guest   unexpected token 'fn'      at line 1, col  9
```

Both refuse (rule 1 holds); they refuse in different **places** (rule 2
does not). `self_eval.lang`'s `parse_primary` carried a guard:

```
else if k.t == "kw" and k.v == "fn" and is_op(toks, pos + 1, "(") {
```

so a named `fn` in expression position declined the branch and fell through
to the generic `unexpected token` fallback at the `fn`. The host has no
such lookahead: it consumes `fn` and lets `param_list`'s `expect("(")`
report at the name. **A position is a fact about the program under
analysis** (decision 34), and the fact here is the name — the `fn` is
fine.

The guard was also unnecessary. Statement position already claims `fn
NAME`, so any `fn` reaching `parse_primary` is an anonymous fn or a
mistake. Removed, in both `self_eval.lang` and `self_host.lang` (the latter
byte-identical by construction —
`test_self_eval.py::test_parser_section_matches_self_host` holds lines
28..927 of one file to be a verbatim substring of the other, and the range
moved from 912 to 927 with this change).

### 5.1 The general fact

`test_parse_error_differential.py` has 47 malformed programs, has been the
authority on this contract since round 360, and **never contained a named
`fn` in expression position**. Nothing about running it more often would
have found this.

> **A corpus is not made complete by being run more often.** The cheap tier
> did not merely cost less than the expensive one — it found what the
> expensive one could not, because coverage is a property of the corpus and
> not of the tier. Round 390's argument was *a rule checked only in a tier
> nobody runs is not checked*; this is the other half — *a rule checked
> only against a corpus nobody widened is checked about the wrong thing.*

Eight cases now sit in `BAD` (`named-fn-expression`,
`named-fn-expr-recursive`, `named-fn-expr-in-arg`, `block-ends-in-fn`,
`block-ends-in-check`, `block-ends-in-shape`, `infix-no-left-operand`,
`infix-kw-no-left-operand`), so the sweep covers what the tripwire found.
`test_every_guest_parse_error_still_leaks_an_implementation_coordinate` is
re-pinned 43 → 51; the ratio (every guest parse error leaks a
`self_eval.lang` line number) is unchanged.

---

## 6. Two tools that had been broken since round 386

Neither is v0.34's doing; both were found by using them.

**`curecheck._template_pattern`.** It builds a hint matcher from the
imported template by splitting on `%s` and joining with `re.escape(part) if
i % 2 == 0 else ".*"`. But `re.split` returns only the LITERAL parts — `%s`
has no group, so it is not captured — so **every second literal is turned
into a wildcard**. For a one-placeholder template that is
`escaped_prefix + ".*"`, which under `.search` is a correct prefix match by
accident. For three placeholders it discards most of the sentence.
`_SEPARATOR_HINT` was the only template in the table for six rounds;
`_FN_EXPR_RECURSIVE_HINT` has three placeholders and is what made the
accident visible. Both matchers now join on `.*?` / `(.*?)`.

**`bench/ref_diff.py`.** Its module list is hand-written:

```python
MODULES = ("__init__", "ast_nodes", "interp", "lexer", "parser", "values")
```

`whence/foreign.py` arrived with v0.33 (round 386) and was never added, so
every invocation since has died with `ModuleNotFoundError: No module named
'whence_ref.foreign'` before comparing anything — six rounds of a tool
whose entire job is *"this rewrite is byte-identical to the previous
version or it is a different language"*, silently unavailable. `MODULES` is
now read off the package directory.

Three hand-written lists, three failures, in one round: the anti-rot
census, the template matcher's placeholder count, and this. That is not a
coincidence about lists — it is that each of them was written at a moment
when it was complete, and completeness is the property that does not
survive the next round.

---

## 7. The bank

17 predictions banked in `state/whence/round-392/PREDICTIONS.md` before any
of the numbers below were taken, with a §0 OBSERVATIONS ALREADY MADE
section listing the ten things read during orientation so none of them is
scored (rounds 379/384/385/386/390's discipline, sixth round running).
All 17 are scored by number below. **9 HIT / 3 HALF / 5 MISS** — the lowest hit
rate of the last four language rounds (384: 11/17, 386: 10/17, 390: 11/15,
read off `state/prediction-bank-ledger.json`; not checked against all 72
banks), and the closing note is why.

| # | claim | verdict | note |
|---|---|---|---|
| P1 | three trailing statement kinds: `let`, named `fn`, `check`; no fourth | **HALF** | three KINDS is right; there is a fourth SOURCE — `shape` returns an `A.Let` (decision 27) — and it is the case that needed the guard (§2.3) |
| P2 | a trailing `let` is always dead; deleting `let NAME =` is semantics-preserving; no counter-example in the tracked corpus | **HIT** | none found; the applier ships on it |
| P3 | the fn-expression cure has two spellings and the BODY decides; `sum_lines` does not self-reference | **HIT** | exact |
| P4 | the recursion branch needs a forward TOKEN scan; no AST is available | **HIT** | `_fn_body_mentions`, same shape as `bound_anywhere`/`shape_close` |
| P5 | `_INFIX_OPS` derivable from the grammar, 12–16 members, `-`/`not`/prefixes/`rescue` excluded | **HIT** | 12, exactly the named set, `-` the sole exclusion |
| P6 | after v0.34: `16` → wrong; predicted **11 cures, 5 mechanical, 6 under** | **MISS** | 16 cures, 5 mechanical, 11 under. The mechanical count is exactly right; I under-counted the table by 5 because I priced the FEATURE (three messages) and shipped the TAXONOMY (eight, one per determinacy class). Same error shape as P13. |
| P7 | replay re-classifies: no-cure 2→0, under-content 1→2, mechanical 4→5, total 45, no line moves | **HIT** | all five clauses, exactly |
| P8 | `curecheck corpus` mechanical edits rise above 3 | **HIT** | 4 |
| P9 | still **0 of 10** field programs fixed mechanically | **HIT** | all ten still `stalled` |
| P10 | no position moves; the parse-error differential stays green with no edit | **MISS** | positions did not move — and the differential did NOT stay green with no edit, in both directions: it needed 8 new cases *and* it found a pre-existing rule-2 violation the moment a case for it existed (§5). The premise was right and the conclusion was the round's second finding. |
| P11 | the census finds **15** unhinted sites, ≥10 justifiable | **MISS** | 13 unhinted, 7 hinted. The prediction was internally confused: 15 was the count BEFORE the change and the change itself hinted two of them. 13 of 13 are justified, not 10. |
| P12 | zero lines change in `self_eval.lang` | **MISS** | 17 lines, and the reason is §5 — a guest change was needed for a v0.24 POSITION contract, which is exactly the contract I cited when predicting no change. I checked that wording is not a contract and did not check that position is. |
| P13 | whole-round diff 1400–2600 lines | **HIT** | 775 tracked-file lines + 636 (`test_v34.py`) + 145 (bank) + this file ≈ 2000 |
| P14 | `test_v33.py`'s anti-rot pair fires during development, green at the end | **MISS** | neither fired, ever. That is §4 — the round's second-largest finding arrived as a failed prediction, for the third round running (round 387's P1/P2, round 390's P2) |
| P15 | fast suite green at both ends; count rises by exactly the new tests; ≤2 pinned-count edits | **HALF** | 1696 → **1758**, +62 = 38 new (`test_v34.py`) + 24 (8 `BAD` cases × 3 parametrized tests). Green at both ends. But **three** pinned counts moved, not two: `test_v33.py`'s `applied == 3`→4, the differential's `43`→51, and `test_self_eval.py`'s `912`→927 |
| P16 | the surprise is in `_expect_hint`; the two rules do not collide; the real difficulty is `expected (` vs `expected '{'` quoting | **HALF** | the rules do not collide, and the quoting inconsistency is real and was found — but it was not the difficulty, and it is deliberately NOT fixed (§8). The surprise was in `self_eval.lang`, which I had predicted would not change at all |
| P17 | exactly one new SPEC decision (43), about a hint reading the program; 32/41/42 unrevised | **HIT** | exact |

### What the five misses have in common

P6, P10, P11, P12 and P14 are all predictions about **the shape of my own
work**, and P13 — the size prediction that three consecutive language
rounds have missed low — is the one that finally landed, because round
390's own scoring told me to price the artifact rather than the code.

P10 is the clearest instance: it asserted the differential would stay green
*with no edit*, from a corpus I had read and a contract I had only half
enumerated.

The pattern one level down: **I priced every one of them against the state
of the tree as I had read it, and the change moved the tree.** P11 counted
unhinted sites before the change and predicted the number after. P6
counted messages and predicted rows in a taxonomy keyed by determinacy.
P12 asserted a guest non-change from the one contract I had checked
(wording) without enumerating the contracts I had not (position). Each is
a *pre*-state quoted as a *post*-state.

That is a different habit from round 384/386/390's "priced the code and
forgot the prose", and it is worth naming separately, because the cure is
different: not a multiplier, but *say which side of the change the number
is on*.

---

## 8. Honest failures and deliberate omissions

1. **The quoting inconsistency is real and unfixed.** `expected (, got
   'adder'` against `expected '{', got 'then'`: `block()` passes
   `what="'{'"` (quoted) and `param_list` passes the bare `"("`. Nine
   `expect` call sites pass a quoted `what` and eleven do not. Fixing it
   changes the BODY of messages that `curecheck`'s `braced-block` trigger,
   round 354's tests and the differential's wording assertions all read,
   for a purely cosmetic gain. Named here with its blast radius rather
   than done on the way past; it is a next step, not a finding.
2. **`test_v34.py` §1's `UNHINTED` registry is a judgement call, 13 times
   over.** Each entry says which of three classes it belongs to and why,
   and a future round that disagrees should change the entry — the point
   of the registry is that disagreeing requires editing a written claim.
   The one I am least sure of is `shape '%s' is already declared in this
   block`: "rename or delete" is a choice, and one could argue the message
   should say so.
3. **I did not measure whether the new clauses help a human.** `curecheck`
   measures whether a MACHINE licensed by the message alone can follow
   them. Round 386's ledger (the "assisted" half, a reader applying each
   cure's intent) was not re-authored for v0.34, so the 45-edit replay
   still records v0.33's reader. Its determinacy re-classification is
   sound — the same 45 errors, re-read by the new table — but nobody
   re-walked the corpus with the new messages in hand.
4. **`bench/ref_diff.py` was fixed, not re-baselined.** It runs; whether
   its full three-mode sweep is clean at the end of this round is recorded
   in §9 as measured, and a `--fuzz` campaign was not attempted.
5. **The `_template_pattern` bug was found by writing a three-placeholder
   template, not by auditing.** Had `_FN_EXPR_RECURSIVE_HINT` needed only
   one `%s`, it would still be there. There is no test that the matcher is
   correct for N placeholders; there is now a matcher that is, and eight
   rules exercising it at N ∈ {0, 1, 3}.

---

## 9. Verification

| check | result |
|---|---|
| `bash run_tests_fast.sh` at HEAD (baseline) | **1696 passed, 3 skipped, 81 deselected**, 80.3 s |
| `bash run_tests_fast.sh` after the parser change only | 1696 passed — *the anti-rot pair did not fire* (§4) |
| `bash run_tests_fast.sh` final | **1758 passed, 3 skipped, 81 deselected**, 184.6 s (an earlier identical run: 150.0 s; the box was running two suites at once for the second). One comment-only edit landed after it — the round-392 note in `test_self_eval.py`'s history comment, moved to the end of the chronology — re-verified alone at 14 passed, 11 deselected. |
| `pytest tests/test_v34.py` | **38 passed**, 3.1 s (fast tier) |
| `pytest tests/test_parse_error_differential.py` | **171 passed, 3 skipped**, 4.1 s (was 145 passed before the 8 new cases) |
| `pytest tests/test_v33.py -m "not whence_slow"` | 26 passed |
| `python3 run.py examples/self_eval.lang` | **166 checks, 0 failed** |
| `python3 run.py examples/self_host.lang` | **133 checks, 0 failed** |
| every other tracked example | rc=0, all checks pass (`failing_check.lang` fails by design) |
| `curecheck.py rules` | 16 cures: 5 mechanical, 11 under-determined |
| `curecheck.py corpus` | 4 mechanical edits, 0 of 10 fixed |
| `curecheck.py replay …/round-386/cure-ledger.json` | 45 errors, 0 no-cure, 10 reach a value, 2 clean under `--strict-miss` |
| `bash skills/run_checks_fast.sh` | 7 checkers, **0 errors, 6 warnings** — identical to round 391's baseline |
| `skill_lint --house --strict` | **46 skills, 0 errors, 0 warnings** |
| `state_claim_check.py state/research-state.md` | 5 claims, **5 re-derivable, 0 stale**; S006 does not fire |
| `xref_check.py --provenance` | 0 dangling ids in the authoritative scope |
| `bash harness/run_tests_fast.sh` | **780 passed, 268 deselected** (181.5 s) — unchanged from round 391; this round touched no harness file. Its `tier-budget` line reported DRIFT (`test_swe_oracles.py` 10.8 s > 10.0 s, 64.7 s of a 42.2 s budget) — measured while the whence suite was running concurrently on a 1-cpu box, so it is a contention reading, not a promotion signal. Named, not acted on. |
| `bench/ref_diff.py --counters` | **0 differing (file, mode) pairs**, exit 0 — 3 modes x every tracked example. *This is the first time it has RUN since round 386* (§6); the 6 field programs report `NEWSYNTAX`, which is the tool saying the reference package cannot parse them either |

---

## 10. Next steps

1. **The `expected (` / `expected '{'` quoting inconsistency** (§8.1).
   Nine of twenty `expect` call sites quote their `what` and eleven do
   not, so eleven messages render an unquoted token where nine quote it.
   The edit is one line in `expect`; the cost is that it changes message
   BODIES that `curecheck`'s triggers, round 354's tests and the
   differential's wording assertions read. Do it as its own change with
   the blast radius measured first, or decide explicitly not to.
2. **Re-author the cure ledger for v0.34.** `state/whence/round-386/
   cure-ledger.json` records a reader following v0.33's messages. The
   45-error determinacy re-classification is sound, but the ledger's
   EDITS are still v0.33's, so "what a reader does with the new sentences"
   is unmeasured (§8.3). A language(C) round, and the natural place to ask
   whether the recursion clause changes what a reader writes.
3. **`bench/ref_diff.py --fuzz` has never been run against v0.33 or
   v0.34** — the tool was dead for six rounds (§6), so any round that
   quoted it in that window quoted a command that could not run. Worth a
   sweep of `knowledge/round-38*.md` for citations of it. SWE-loop(D).
4. **The `UNHINTED` registry is 13 written claims and nothing re-derives
   them** (§8.2). A future round could ask, for each, whether a reader
   given only that message reaches the edit — the `curecheck` question
   applied to the sites that deliberately have no cure.
5. **Round 390's items 2–4 are unchanged and unclaimed**: seed the
   retired-items registry properly (skills B), run `pytest -m whence_slow
   tests/` at a known tree to discharge round 380's P11, and render round
   384's `SLOWTIER_RESULT`. This round did not run the slow tier either —
   it is a ~900 s job and it is that item's, not this one's.
6. **Round 391's items 1–5** (score E1 not before round 410; the
   `--max-turns` question; incremental commits on `error_max_turns`;
   `split_sessions`' subagent branch; the stale `harness-fast` health
   line) are unchanged — harness(A).
7. `harness/swe/regiontools.py`'s region-patch mechanism is still
   deliberately un-unified with `EditFileTool` — round 307's item 2.
8. Round 301's item 2 (blocking-wait mitigation design sketch) remains
   speculative — 19 rounds now.
9. The `tail`/EOF backgrounded-pipe silent-drop mechanism (rounds 296,
   300, 303, 309) remains genuinely unconfirmed — round 310's item 5.
10. NUC-integration(E)'s standing items are unchanged (round 388's list);
    the rotation has not reached that track since.

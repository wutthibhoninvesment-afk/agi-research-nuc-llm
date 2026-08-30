# Round 356 — language(C) — a line break is the only statement separator

*2026-08-30. Track C (rotation 356 mod 6 = 2 → language). Model: claude-opus-5.*

## 0. One line

`lexer.py`'s first sentence has said "Newlines are statement separators"
since its first commit, and `SPEC.md`'s syntax heading has said the same;
the parser never checked it, so `let a = 1 let b = 2` was two statements for
twenty-two versions. Whence v0.23 (decision 33) enforces the rule the
language already documented. It closes round 354's largest open item, takes
its machine-written corpus from 9/10 to 10/10 **without writing a new hint**,
and cost exactly one tracked program a line break.

## 1. The item, and why it was worth a round

Round 354's next steps, item 1, verbatim:

> **A mandatory statement separator.** `let a = 1 let b = 2` parses today and
> that laxity is the direct cause of the one machine-written program v0.22
> cannot diagnose. It touches `stmt_list` on the host AND the byte-identical
> parser section shared by `self_host.lang`/`self_eval.lang`, plus a sweep of
> every example and test for accidental reliance. language(C), and the
> largest open item this round leaves.

All three predictions held, and the third was the surprising one — see §5.

The motivating input is `prod_demo_v4.lang`'s `let d = f one, two`. Round 354
measured decision 32 ("an error that can name the fix, names it") against ten
machine-written Whence programs and got nine cures. The tenth was not a
missing hint:

```
v0.22:  unexpected ',' at line 1, col 14
```

`let d = f` is a complete statement. `one` is a complete statement. The
juxtaposition — the actual mistake, a paren-less call — was consumed silently
by the statement rule, and the error surfaced three tokens later at the `,`,
where no adjacency was left to recognise. The two juxtaposition programs that
DID get a cure are the ones where the mistake happens inside brackets, where
the statement rule could not reach it.

```
v0.23:  two statements on one line (two names in a row: Whence has no
        juxtaposition — a call is `f(x)` and text must be quoted)
        at line 1, col 11
```

Col 14 → col 11. The error moved back to the token the author got wrong, and
the cure it now names is one round 354 had already written. **No new hint was
added this round.** The corpus went 9/10 → 10/10 by removing a permission.

## 2. The shape of the finding: documented and unenforced

This is not "the parser had a bug". Every conforming program behaved exactly
as documented, so nothing in twenty-two versions of tests, examples or bug
reports was in a position to see it. Three independent places in the tree
asserted the rule:

```python
# whence/lexer.py, line 3, present since the lexer's first commit
"""Newlines are statement separators, but are suppressed inside ( ), [ ] and
record literals @{ } so multi-line data and argument lists read naturally."""
```
```markdown
## Syntax (statements are newline-separated; `#` comments)     # SPEC.md
```
```python
# whence/parser.py, statement(), on the `shape` soft keyword
# "no other legal statement starts with two bare names in a row"
```

The third is the interesting one. It is *false* as written, and false
precisely because of the laxity: `f x` was two legal statements, so any
`NAME NAME` pair could be legalised by splitting it. Enforcing the separator
makes a comment the codebase had believed for eighteen rounds true for the
first time.

And the implementation:

```python
def stmt_list(self, end):
    self.skip_newlines()
    while not self.at(end):
        s = self.statement()
        ...
        self.skip_newlines()          # permitted everywhere, required nowhere
```

`skip_newlines()` could not answer the question the rule needs — it consumed
newlines and reported nothing. It now returns whether it found one, which is
the whole mechanism.

The general form of this is worth a name, and got one:
`skills/unenforced-documented-rule/` (§8).

## 3. The rule, and the two qualifications that are the design

Between two statements, at least one NEWLINE.

### (a) Only BETWEEN

`at(end)` is what closes a block, so nothing is required before the first
statement or after the last. `{ x }` is unchanged; so is a file that starts
with blank lines, a file with no trailing newline, and `fn f() { let x = 1\n
x }` whose `x }` needs no separator after it. A run of newlines is one
separator. A trailing `#` comment separates — because a comment ends at the
line break the lexer then emits, and there is no way to write a comment that
does *not* end the line, so a comment can never separate on its own.

### (b) Only for a token that could START a statement

```python
_STARTS_STATEMENT_TYPES = frozenset(("NUMBER", "STRING", "NAME",
                                     "[", "@{", "(", "{", "-"))
_STARTS_STATEMENT_KWS = frozenset(("let", "fn", "check", "if", "true",
                                   "false", "why", "snip", "miss", "not"))
```

This is the qualification that keeps decision 33 from destroying decision 32.
`x = 2` is not two statements — an `=` can never begin one — and v0.22 spends
real effort on it:

```
unexpected '=' (Whence has no assignment; a name binds once
  — write `let name = value`) at line 2, col 3
```

The separator check sits EARLIER in the pipeline than the site that produces
that message, so without the guard it silently outranks it. That is not a
hypothesis: the first version of this round's patch had no guard, and
`test_v22.py::test_parse_error_hint_text[...]` went red on exactly that case.
The right response to a v0.22 regression test failing was not to update the
expectation.

Two facts about the set are pleasing and both are pinned rather than
asserted. The keywords excluded are exactly the four infix ones — `and`,
`or`, `rescue`, `else` — i.e. every keyword that needs a left operand. And
the sets are a cache of something the parser already knows, so
`test_every_token_is_classified_by_whether_it_can_start_a_statement`
re-derives them over all 40 tokens the lexer can produce:

```python
def _empirically_starts_a_statement(text, value):
    """A token that cannot start a statement is exactly one `primary()`
    refuses with its own fallback (`unexpected <that token>`). Any other
    outcome — a clean parse, or an error about what should have FOLLOWED
    it — means the token was accepted as a statement head."""
    try:    parse(text + "\n"); return True
    except ParseError as e:
        return not str(e).startswith("unexpected %r" % (value,))
```

40/40 agree. Without this the check silently stops firing in front of any
token that gains a new statement role, and the symptom is invisible: the
program goes back to parsing as two statements.

### (c) The error names the cure, and defers when the newline is not the cure

`_separator_hint` has three branches and all three are reachable:

| input | hint | why |
|---|---|---|
| `let a = 1 let b = 2` | start `let` on the next line | ordinary |
| `let a = b shape P = @{x: num}` | start `shape` on the next line | `shape` HEAD; soft keyword, lexes as NAME |
| `let shape = 1` / `let x = shape foo` | start `foo` on the next line | `shape` on the LEFT — v0.22's `_NAME_INTRODUCERS` |
| `let d = f one, two` | a call is `f(x)` and text must be quoted | NAME touching NAME |
| `let a = b shape P` | ...same | `shape P` with no `=` is not a head |

The juxtaposition branch is the point. Telling the author of `f one, two` to
add a newline would be advice for a mistake they did not make, so the site
reuses decision 32's own rule verbatim rather than reimplementing it.

## 4. The honest limit, which is a grammar property

`-`, `(` and `[` both START a statement and CONTINUE an expression
(subtraction, a call, an index). After an expression statement the
longest-match grammar has already consumed them by the time `stmt_list`
looks:

```
let a = 1 -2      -> ONE statement; `a` is -1
let a = 1 (2)     -> ONE statement; a call
let a = 1 .x      -> ONE statement; `.` is not a statement head at all
let a = 1 [1, 2]  -> expected ], got ','   (an index, failing on index syntax)
fn f() { 1 } (2)  -> two statements on one line   # `fn` cannot be extended
```

This is automatic-semicolon-insertion's hazard, and Whence has it in exactly
three places instead of everywhere. It is a property of having both prefix
and infix `-`, not of this rule. Removing it needs either a real separator
token or newline-sensitive expression parsing, and both are larger languages
than this one.

Found by the tests failing, not by reasoning: three entries of the first
`REFUSED` corpus (`let a = 1 -2`, `let a = 1 (2)`, `let a = 1 [1, 2]`) did
not refuse. Written down as `test_a_token_that_also_continues_an_expression
_is_absorbed_first` and in SPEC.md's `## v0.23`, because an unwritten limit is
rediscovered later as a bug report.

## 5. What it cost — measured, not estimated

**Programs: one.** Of the 16 tracked `.lang` files in `languages/whence`, 15
were already conformant. Repo-wide, all 30 tracked `.lang` files parse under
v0.23 after the single fix. The one was `examples/effects.lang`:

```
-  fold(fn(acc, x) { debug_print(x) acc + x }, 0, xs)
+  fold(fn(acc, x) {
+    debug_print(x)
+    acc + x
+  }, 0, xs)
```

Still one `fold` argument: `(`/`[`/`@{` suppress newlines but `{` does not,
because blocks contain statements. That the fix reads like ordinary Whence is
the measurement that says the rule matches how the language was already being
written.

Enumerated with `git ls-files`, not a directory scan — round 355's finding,
one round old, and this is the first language(C) round to inherit it. A glob
of `examples/` would have counted 14 files belonging to a separate system and
made their conformance a fact about Whence.

**Tests: seven files, and one of them is interesting.**

Round 336's tail-vs-lifted differential rewrites every tail call `f()` to
`let t = f()  t` **on the same line**, so a `-> Type` miss must report the
same line number under both forms. Round 353 named line-alignment as the
thing that makes that oracle strict, and round 355 proposed promoting it to a
sixth `harness/swe/` oracle on those grounds. Decision 33 forbids the
one-line spelling outright.

It cost the oracle nothing. What the differential needs is line ALIGNMENT,
not one-line-ness:

```python
tail.append("fn f%d()%s { %s }" % (i, ann, body))
tail.append("")                                    # <- the whole fix
...
lifted.append("fn f%d()%s { let t = %s" % (i, ann, body))
lifted.append("  t }")
```

Two lines per function in both forms; every call site keeps its line number;
75 + 375 programs at 2 and 3 hops and 1875 at 4 hops still agree. **The
property round 353 thought depended on the separator laxity depended only on
alignment**, which padding restores exactly. The alignment itself was
self-evident from the source until this round and is now an assumption, so it
is asserted (`test_the_two_forms_are_line_for_line_aligned`) — nothing in
`run_chain_differential` would fail if the padding were dropped and the forms
drifted apart, because two genuinely different reports would still be equal
to each other.

The rest were mechanical: same-line sources in `test_v12`/`test_v13`/
`test_v14`, and one line-number assertion (`e.value.line == 2`) that moved.
That one is now derived from the source (`lines.index(...) + 1`) rather than
restated, because the property under test is "points at the use, not the
declaration", not "points at line 2".

**Counts that moved:** `self_host.lang` 109 → 112 in-language checks (one
check asserting `"1 2"` PARSES became four); the shared parser section 773 →
803 lines; `test_examples.py`'s hard-coded `109 passed`.

## 6. Guest parity

`examples/self_host.lang`'s `parse_stmt_list` gets the same rule, with
`after == s.pos` standing in for "no newline was skipped":

```
      let after = skip_nl(toks, s.pos)
      if at_end(toks, after, end) { @{stmts: acc2, pos: after} }
      else if after == s.pos and starts_stmt(toks, after) {
        miss ("two statements on one line at line " + str(t_at(toks, after).line))
      }
      else { parse_stmt_list(toks, after, end, acc2, bound2) }
```

plus `starts_stmt` and the `stmt_start_kws`/`stmt_start_ops` lists mirroring
the host's two frozensets. `examples/self_eval.lang` carries the
byte-identical copy (`test_parser_section_matches_self_host`, bounds 773 →
803).

Two things worth recording:

- **The guest's own self-test ASSERTED the laxity.** `self_host.lang` had
  `check "two statements with no separator both parse (host allows this)"`,
  with a comment explaining that `skip_newlines()` is "best-effort". A
  reference implementation is where a laxity is most likely to be written
  down as a property, because writing it down is what reference
  implementations are for. Replaced by four checks: the refusal, the same two
  statements on two lines, the line the miss names, and a token that starts
  no statement keeping its own error.
- **Wording is still not a guest contract.** Host parse errors are exceptions
  with a line and a column; guest ones are `miss` values with a line. Round
  354 pinned that (`test_parse_error_wording_is_not_a_guest_contract`), so
  this round checks ACCEPT/REFUSE agreement over a 23-program corpus and the
  line number, not the sentence. 23/23 agree.

## 7. Verification

```
whence  pytest -c pytest.ini tests/ -m "not whence_slow"
                                       1252 passed, 57 deselected
                                       (355 baseline 1193/54; +59)
        pytest -c pytest.ini tests/ -m "whence_slow"      SLOW_TIER
        tests/test_v23.py              61 passed (3 whence_slow)
        run.py examples/self_host.lang 112 passed, 0 failed (was 109)
        run.py examples/self_eval.lang 142 passed, 0 failed
        run.py examples/effects.lang    16 passed, 0 failed
        every tracked .lang, repo-wide  30 parse, 0 fail
harness bash harness/run_tests_fast.sh HARNESS_FAST
        slowtier.py run --only <whence-driven files>   SLOWTIER
skills  skill_lint.py --house --strict skills/   27 skills, 0 errors, 0 warnings
corpus  machine-written programs naming a cure   9/10 -> 10/10
```

### Pins checked by mutation, not assumed

Thirteen mutants, each reverting one decision this round made, each run
against a scoped slice of the suite. **13 killed, 0 survived** — but only
after the sweep found a real hole in this round's own tests.

| mutant | killed by |
|---|---|
| separator check removed | `test_v22::test_all_ten_now_name_a_cure` |
| can-start-a-statement guard removed | `test_v22::test_parse_error_hint_text[x = 2]` |
| `_starts_statement` always True | same |
| `not` dropped from `_STARTS_STATEMENT_KWS` | `test_v23::test_two_statements_on_one_line_are_refused[not true]` |
| `skip_newlines` always reports a separator | `test_v22::test_all_ten_now_name_a_cure` |
| juxtaposition branch removed | `test_v22::test_the_tenth_was_a_separator_laxity_and_v023_removed_it` |
| shape-head exclusion removed | **SURVIVED** → `test_v23::test_separator_error_wording[let a = b shape P …]` |
| `_NAME_INTRODUCERS` exclusion removed | `test_v22::test_shape_is_the_one_legal_name_name_and_draws_no_hint` |
| guest separator check removed | `test_v23::test_host_and_guest_agree_…` |
| guest can-start guard removed | `test_v23::test_both_self_hosting_examples_still_run_green` |
| guest `not` dropped | `test_v23::test_guest_start_sets_match_the_hosts` |
| tail-form alignment padding removed | `test_v13::test_the_two_forms_are_line_for_line_aligned` |

**The survivor is the most useful line in this round.** The shape-head
exclusion had a test — `let a = 1 shape P = @{x: num}` — and it proved
nothing, because with `1` in front of `shape` both branches of
`_separator_hint` return the same string. The two rules only disagree when
the PREVIOUS statement ends in a NAME. Changing `1` to `b` kills the mutant.
A test can exercise a branch and still not test it.

The last row of that table is the interaction worth keeping: v0.23 changed
where `shape Foo Bar = @{x: num}`'s error comes from. `shape Foo` is not a
shape head (`peek(2)` is `Bar`, not `=`), so `shape` became an expression
statement and `Foo` a second one, and the separator check now fires first.
Round 354's test still passes only because `_separator_hint` inherits
`_NAME_INTRODUCERS` — noted inline in that test, so the next round finds a
decision rather than a coincidence.

## 8. Skills

**New: `skills/unenforced-documented-rule/`.** The method, generalised past
Whence: harvest requirement sentences (`must`, `always`, `only`,
`-separated`) from the system's own prose into falsifiable probes; measure
the corpus from version control before tightening; define the DEFERENCE set
before writing the check and derive it from the code; find what depends on
the laxity and preserve the property it actually needed rather than the
permission; mirror into every implementation; update the old permission's
regression test instead of deleting it; enumerate the honest limit.

**Upgraded: `skills/errors-that-name-the-fix/`.** Its pitfall "the tool
silently ACCEPTED the mistake, so no message can carry the hint" was written
by round 354 with this exact input as its example. It now records the
follow-up — 9/10 → 10/10 with no new hint written — and points at the
tightening procedure, whose first obligation is not to shadow the messages
that skill just built.

`skill_lint.py --house --strict skills/`: 27 skills, 0 errors, 0 warnings.

## 9. A pitfall this round hit, recorded because it cost real work

The first mutation sweep ran the FULL `tests/` (slow tier included) per
mutant, hit the tool's 2-minute timeout, and was killed by SIGTERM — which
does not run `try/finally`. It left `if False:` in `whence/parser.py`, and
the next command run against it reported a clean fast tier for a parser with
the round's central change disabled. Caught by grepping for the mutant, not
by the suite.

Snapshot the files to a temp directory and write a standalone `restore.sh`
*before* the first mutation, and scope each mutant's test run so the whole
sweep fits inside the timeout. In this skill corpus that belongs to
`unenforced-documented-rule`'s pitfalls, and it is a general fact about
mutation testing under a supervisor that can kill you.

## 10. Round 355's work, landed

The record-gap check reported round 355 (harness A) as interrupted with no
`research-state.md` entry and four unattributed paths. Its two commits
(`fd7d91a`, `2e3193f`) had landed; what had not were the knowledge file, the
`pristine-checkout-differential` skill, and the ledger. Verified before
landing: `harness/run_tests_fast.sh` 530 passed, whence fast 1193 passed at
that tree, and the ledger's own recorded verdicts reproduce. Committed with
attribution and given a `research-state.md` entry. `languages/whence/
SECURITY.md` is untouched and still the operator escalation round 349 §8
raised — sixth consecutive round.

## 11. What this deliberately does not do

- **No `;`.** A separator token would make the newline rule optional again
  and put the language back where it started, one keystroke louder.
- **No change to newline suppression.** `( ) [ ] @{ }` and the
  trailing-operator continuation rule are untouched, which is why a block
  inside a call's parens still separates on newlines and `effects.lang`'s fix
  reads like ordinary code.
- **No tightening of the three expression-continuation tokens** (§4).
- **No new hint text.** Everything `prod_demo_v4.lang` now gets was written
  by round 354; this round only stopped the grammar from eating it.

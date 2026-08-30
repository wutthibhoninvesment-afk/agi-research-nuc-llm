# Round 354 — language(C) — Whence v0.22: an error that can name the fix, names it

*2026-08-30. Track C (rotation 354 mod 6 = 0 → language). Model: claude-opus-5.*

## 0. One line

An operator bug report against v0.19 said `fold()` was broken and the parser
was too strict; round 349 proved both halves were documentation gaps and wrote
the documentation. This round closed the half that is the **language's** job:
where the implementation can compute what the author should have written, the
error now says so — `(arguments fit fold(fn, acc, xs))` on a builtin miss, and
five named cures on parse errors. Writing the guest mirror for the first half
found **three pre-existing host/guest wording divergences**, one of which leaked
the guest evaluator's internal closure record into a user-facing message. Two
documentation defects fell out along the way, including SPEC.md's own
anti-rot header sentence, which had itself rotted one round after being written.

## 1. Where this came from

`CLAUDE.md` carries an operator escalation:

> 1. **Fold Logic Regression:** `fold()` returns `Miss` instead of calculated
>    values when using inline lambdas or external functions.
> 2. **Strict Syntax Enforcement:** Parser requires explicit `{}` blocks for all
>    `if/else` branches in v0.19. Document this strictly and consider auto-fixing
>    older scripts.

Round 349 (harness A) refuted both as defects. `fold(nums, 0, fn(acc, x) {...})`
misses because Whence's higher-order builtins take the **function first**
(`fold(fn, acc, xs)`), and SPEC.md's `## Builtins` was a bare list of 36 names
that gave the argument order for none of them. The braces rule is how the
grammar has always read. Round 349 wrote the signature table and
`### Blocks are always braced`, and pinned them in
`tests/test_spec_builtins.py`.

**Re-verified this round before building on it** (not taken on trust):

```
$ python3 run.py /tmp/r354_fold.lang
miss: fold needs a list, got <fn> (line 2)
10          # fold(fn(acc,x){acc+x}, 0, nums)
10          # fold(add, 0, nums)   -- external named fn
checks: 2 passed, 0 failed
```

So both spellings the operator named fold correctly when written the documented
way, and the miss was never silent. Round 349's finding stands.

What round 349 could not do from the harness track is the part that is the
language's own. In both halves the implementation **knew the cure and said only
the symptom**:

```
fold needs a list, got <fn>                  # true. now what?
expected '{', got 'print' at line 2, col 10  # true. now what?
```

Decision 2's founding promise is a failure that, "unlike NaN, can tell you
*why*". Twenty-two versions have read that as *name the symptom precisely*.
v0.22 is the other half.

## 2. Decision 32 — the rule

> **An error that can name the fix, names it.** Where the language can compute
> what the author should have WRITTEN, the error says that too — silently
> otherwise. Never guessed.

Two surfaces, one rule.

## 3. (a) The builtin half

### The declaration

`register` gained a third, **required positional** argument:

```python
@register("fold",  3, "fn:fn, acc, xs:list")
@register("map",   2, "fn:fn, xs:list")
@register("push",  2, "xs:list, x")            # the one that goes the other way
@register("guess", 3, "value, conf:num, source:str")
@register("len",   1, "v")                     # 1-arg: name only, no kinds
```

Parsed once into `interp._BUILTIN_SIGS` by `_parse_sig`. A bare name is kind
`any`; `name:tag` is one `_kind()` tag; `name:a|b` is a union. Required rather
than optional so a builtin added later cannot quietly opt out of the SPEC
table's machine-check. All 36 builtins declare one.

Kinds are declared only where they are real. Positions whose handler enforces
something `_kind` cannot see — a confidence in [0, 1], a `_spec_ok` type spec,
`range`'s integers-not-floats — are left `any` or loosely tagged **on purpose**,
so the hint never claims more than it checked. One-argument builtins declare a
name and no kind: there is no other order for one argument, so a kind there
would be an assertion nothing executes.

### The hint

At each wrong-KIND rejection site (20 of them), the reason gains a clause:

```
fold needs a list, got <fn> (arguments fit fold(fn, acc, xs)) (line 2)
push needs a list, got 7 (arguments fit push(xs, x)) (line 1)
get field name must be a string, got @{a: 1} (arguments fit get(r, name))
guess confidence must be a number between 0 and 1, got "src"
  (arguments fit guess(value, conf, source))
at needs a string step name, got [1, 2] (arguments fit at(v, pat))
```

### Existence, not uniqueness — a design decision that changed mid-round

The first draft required a **unique** fitting order, on the reflex that
ambiguous advice is bad advice. That was wrong, and the reason is worth
keeping: **the advice IS the signature**, which is the same string for every
fitting order. `guess("s", 1, 2)` fits `guess(value, conf, source)` in two
orders (either `1` or `2` can be the confidence), and the sentence "the
arguments fit `guess(value, conf, source)`" is true in both. Uniqueness would
have suppressed a true sentence without making any surviving sentence truer.
Pinned by `test_order_hint_is_existence_not_uniqueness`.

### The three silences are the load-bearing half

`_order_hint` returns `""` when:

1. **there is no declared signature for that argument count** — an ARITY error
   (`fold expects 3 args, got 2`) is a different, already-precise miss;
2. **fewer than two arguments** — there is no other order;
3. **the given order already satisfies the declared kinds.** This is the one
   that matters. It means the miss is about something the kinds do not model,
   so reordering would not help:

| call | miss | clause |
| --- | --- | --- |
| `filter(fn(x) { 5 }, nums)` | `filter predicate must return true/false, got 5` | none |
| `guess([1], 5, "src")` | `guess confidence must be … got 5` | none |
| `range(1.5, 3)` | `range needs integers, got 1.5` | none |
| `typed("Point", @{x: 1}, "lbl")` | `typed spec must be a type name or a shape` | none |
| `join("a", "b")` | `join needs (list, string)` | none (no order fits) |
| `merge(@{a: 1}, 5)` | `merge needs two records` | none (symmetric sig) |
| `map(f, guess(nums, 0.9, "s"))` | `map needs a list, got guess 0.9 (s): […]` | none |

The third rule makes `_order_hint` **self-guarding**: it can be called at any
rejection site without a whitelist, because a site whose failure the kinds
already explain gets nothing. The `guess`-wrapped-list row is the one I most
wanted to get right — v0.15 is deliberately shallow, the cure there is `sure()`,
and a hint saying "reorder" would have been actively wrong.

The clause does **not** promise the reordered call succeeds. `fold(fn, acc, xs)`
with a callback that misses still misses. It promises exactly what was checked:
the kinds line up that way.

### The declaration pays for itself twice

`tests/test_spec_builtins.py` (round 349's file) now checks SPEC's argument
NAMES against `_BUILTIN_SIGS`, not just its arities. Round 349 could only check
the two things the registry knew — name and arity — so the column that had
actually caused the bug report, the parameter ORDER, was **still unchecked
prose**: SPEC could have said `fold(acc, fn, xs)` and every test would have
passed. Round 349's own `assert "fn, acc, xs = args" in src` was a grep for a
local-variable assignment, because there was nothing better to read. There is
now.

Only the LONGEST spelling per row is matched. The shorter spelling of an arity
RANGE is not a prefix in general — SPEC documents `range(hi)` (declaration
`lo, hi`) and `diverge(runs)` (declaration `a, b`) — so demanding one would
force the table to lie about which argument a 1-arg call binds.

## 4. (b) The parser half — chosen by measurement, not by taste

The operator asked whether to auto-fix older scripts. **The scripts exist.**
Ten machine-written Whence programs sit untracked in `languages/whence/
examples/` — output of a separate autonomous system (the Hermes gateway;
`state/known-standing-dirty-paths.json` has allowlisted them since round 291).
All ten fail to parse. Measured *before* deciding what to build:

| cause | files | before v0.22 | after |
| --- | --- | --- | --- |
| unbraced `if` / `else` / `fn` body | 2 | bare | hint |
| `if` without `else` | 1 | already named its cure | unchanged |
| `x = 2` assignment | 1 | bare | hint |
| `rescue { } catch` block | 2 | bare | hint |
| `{a: 1}` record literal | 1 | bare | hint |
| two adjacent names | 3 | bare | **2 hint, 1 bare** |
| | **10** | **1/10 named a cure** | **9/10** |

**Six distinct causes, and the braces rule is two of them.** Auto-fixing braces
would have repaired a fifth of the corpus and left the rest failing with errors
that still named no cure. But all six are the same underlying mistake in
different clothes — the author reached for a mainstream construct Whence
deliberately does not have — so the answer was to make the errors teach:

```
unexpected '=' (Whence has no assignment; a name binds once
  — write `let name = value`) at line 2, col 3
unexpected ':' (records are written `@{a: 1}`, not `{a: 1}`) at line 1, col 11
unexpected 'rescue' (`rescue` is infix: `risky rescue fallback`) at line 1, col 9
expected ']', got 'Unit' (two names in a row: Whence has no juxtaposition
  — a call is `f(x)` and text must be quoted) at line 1, col 20
expected '{', got 'print' (blocks are always braced:
  `if c { a } else { b }`, `fn f(x) { x }`) at line 1, col 10
```

### Two rules whose exactness took work

**The record literal.** `{a: 1}` is a *block* whose first statement is the name
`a`, so the error lands on the `:` two tokens past the mistake and says only
`unexpected ':'` — true, useless. Fixed with a two-token lookahead in `block()`:
a block statement can never begin `NAME :` or `STRING :` (an annotation only
appears inside a parameter list; `check` takes a keyword first), so the pattern
identifies a record literal missing its `@` unambiguously. Newlines are skipped
first, so the multi-line form is caught too.

**Juxtaposition.** Fires when the token that failed to match is a NAME
immediately preceded by a NAME — the adjacency, not the token that happened to
be expected, which is why the same rule covers `expected ')'` (an unquoted
string inside a call) and `expected ']'` (one inside a list). One exception:
`shape` is a **soft keyword** — `lexer.KEYWORDS` has 14 words and it is not one
of them — so `shape Foo` is the grammar's one legal `NAME NAME`. Without the
exception every malformed `shape` statement would be told to quote its own type
name. Pinned by `test_shape_is_the_one_legal_name_name_and_draws_no_hint`.

### The tenth program: a grammar property, not a missing hint

`let d = safe_divide one_hundred, zero_point_zero` still gets a bare
`unexpected ','`. It cannot be hinted **because the parser accepts the
mistake**: Whence statements need no separator, so `let d = safe_divide` and
`one_hundred` are two complete statements on one line, and the error surfaces
three tokens later at the `,` where the adjacency is no longer visible. Verified
directly — `let a = 1 let b = 2` and `let b = a b` both parse today.

The two juxtaposition cases that ARE hinted happen inside brackets, where the
statement rule cannot swallow them.

Left as a **known property, pinned rather than fixed**
(`test_the_tenth_is_a_statement_separator_laxity_not_a_missing_hint`): a
mandatory statement separator is a real grammar change with its own guest-parity
obligations (`self_host.lang`/`self_eval.lang` share a byte-identical parser
section) and belongs to its own round.

### No guest mirror needed — established, not assumed

Host parse errors are exceptions carrying line AND column; guest parse errors
are `miss` values carrying a line only, and the two have **never** used the same
words:

```
host:  unexpected '=' at line 2, col 3
guest: miss: unexpected token '=' at line 2
```

Adding a clause to one cannot create a divergence where there was never an
agreement. Pinned by `test_parse_error_wording_is_not_a_guest_contract`, so a
future round that DOES make them agree finds this decision recorded rather than
rediscovering it as a surprise.

## 5. Guest parity for the builtin half — and three bugs it found

`self_eval.lang` re-implements exactly four builtins (`map`/`filter`/`fold`/
`find`); everything else is delegated to the host, which appends its own clause,
so parity there is free. The mirror is decision 31 in the small: the host
enumerates orderings with `itertools.permutations`, the four mirrored builtins
take two or three arguments, and two and three arguments have two and six
orderings — so the guest lists them. `sig_names`, `sig_kinds`, `kind_ok`,
`sig_fits`, `perm_indices`, `any_perm_fits`, `order_hint`, ~40 lines.

The one subtlety: a guest closure **is a record under the hood**
(`@{__tag: "closure", …}`), so the kind test must use the existing `guest_kind`
(callable checked before record, mirroring the host's `_KIND_ORDER`) and not
bare `shapeof`, which would say "record" and silence the hint on the operator's
own case.

Writing the wording differential found **three divergences that predate this
round**, all invisible to every existing test because the ordinary corpus
differential exempts miss reasons by design (round 17). Verified against the
committed tree (`git show HEAD:…/self_eval.lang`) before claiming they were
pre-existing:

1. **The guest dumped its own closure record into a user-facing miss.**
   `fold`/`map`/`filter`/`find`'s "needs a list" miss rendered a callable with
   `str(strip(...))`:

   ```
   host:  fold needs a list, got <fn>
   guest: fold needs a list, got @{__tag: "closure", body: @{kind: "block",
          stmts: [@{expr: @{…}, kind: "exprstmt"}]}, env: ["f1", "f0"],
          name: "(anonymous)", param_specs: [], params: ["a", "x"],
          ret_spec: ""}
   ```

   Round 156 wrote `show_callable` for exactly this class and it never reached
   these four sites. The guest was leaking its evaluator's internals into a
   message about the *user's* program.
2. `filter predicate must return true/false` — the guest dropped the host's
   `, got 5`.
3. `find predicate must return true/false` — same.

All three fixed here. This restores the "every language(C) round since 326 finds
a guest-parity bug" pattern that round 348 broke (16/16 clean) — but note the
shape: these were found by **comparing a message nobody had ever compared**, not
by the differential fuzzer, which by construction cannot see them.

## 6. Two documentation defects found in passing

### SPEC.md's anti-rot sentence had itself rotted, in one round

Round 348 replaced SPEC's stale version enumeration (`"v0.16.6 + v0.14.2"`,
unchanged since round 266 while the file documented v0.17–v0.20) with a header
line explaining *why enumerations rot*, set to **v0.20**. Round 350 added
`## v0.21` and did not touch it. Round 354 arrived to find it **two levels
stale**.

That is round 321's item 14 / round 333's rescoping ("any line asserting a
number that no round re-executes") landing on the very sentence written to
diagnose the class. **A better sentence is still a claim no round re-executes.**
The fix is the re-execution, not the prose:
`test_spec_level_header_matches_the_highest_version_section` parses every
`## vN` heading, sorts on the numeric parts (so v0.22 outranks v0.2, which
string order would not), and compares against the header.

### SPEC documented a construct the language does not have

`### Blocks are always braced` said "The rule holds for `fn` bodies and `while`
bodies too." **Whence has no `while`.** `lexer.KEYWORDS` is
`{let, fn, if, else, check, rescue, why, snip, miss, true, false, and, or, not}`
and `while` is not among them; `while i < 3 { i }` is not even a parse error —
it parses as three statements (`while`, `i < 3`, `{ i }`), the first an unbound
name. Corrected, with the reason recorded inline so the correction is not
mistaken for a deletion.

Both are the same class as the finding above, and both were found by *doing the
work the document describes* rather than by auditing the document.

## 7. What this deliberately does NOT do

- **The hint is not a new value or provenance field.** It rides on the miss's
  REASON, exactly as v0.20's field clause does, so it reaches `reasons`, `why`,
  `blame` and a failing `check` report with no new surface — and the miss's
  provenance INPUTS are untouched (round 347 put `fold`'s accumulator back into
  them; `test_the_hint_rides_on_the_reason_and_not_on_the_provenance` asserts
  this round did not undo that).
- **No statement separator.** See §4.
- **`matches` gains nothing** — it returns a bool and has no message.
- **The gateway's ten programs were not edited.** They are another system's
  files, allowlisted precisely so no round treats them as its own. Their content
  is evidence in this round, quoted as *test literals* rather than depended on
  as files, so the measurement survives the files changing or vanishing
  (`MACHINE_WRITTEN` in `tests/test_v22.py`).
- **`languages/whence/SECURITY.md` was not touched.** It is round 349's
  unresolved operator escalation (the gateway's rewrite asserts four security
  controls that do not exist and deletes the human authorship attribution),
  deliberately left uncommitted by rounds 349, 350 and 351. Re-confirmed
  unchanged this round; the decision is still the operator's. This is the one
  entry the automated record-gap check flags, and it is a deliberate escalation
  rather than a leftover diff.

## 8. Verification

```
languages/whence   pytest -c pytest.ini tests/ -m "not whence_slow"
                       1191 passed, 54 deselected      (baseline 1137/53, +54)
                   tests/test_v22.py                   53 passed  (new; 1 slow)
                   tests/test_spec_builtins.py          9 passed  (was 6, +3)
                   run.py examples/self_eval.lang     142 passed, 0 failed
                   run.py examples/self_host.lang     109 passed, 0 failed
                   run.py examples/shapes.lang         18 passed, 0 failed
                   every tracked example              exit 0, 0 failures
harness            bash harness/run_tests_fast.sh     476 passed, 303 deselected
machine-written    parse errors naming a cure          1/10 -> 9/10
```

`-c pytest.ini` is round 349's routing: `languages/whence/pyproject.toml` is an
untracked gateway file and pytest parses every candidate config in the rootdir
during discovery. It is currently *valid* TOML again (the duplicate
`[project.optional-dependencies]` table that broke round 348's whole suite is
gone), which is a change to an allowlisted file by the system that owns it —
noted, not acted on; the `-c` routing is what makes the suite independent of it
either way.

Host-mode coverage: every wording assertion in `test_v22.py` runs under all
three evaluation strategies (`fast=False` → generator, `direct=False` →
`_closure_inline`, default → all three) via `host_reason`, which asserts the
three agree before returning. Round 128's bug was one such site silently missing
its check.

## 9. Honest failures and limits

- **The uniqueness rule was wrong on the first pass** and I built it before
  thinking it through. It cost a rewrite of `_order_hint` and is now the thing
  its docstring spends the most words on.
- **`typed` can only reach its hint from the LABEL position.** Its `spec`
  position accepts `str|record` and its `value` position is `any`, so the
  identity order fits the declared kinds for most malformed calls and the
  silence rule (correctly) suppresses the clause. `typed("Point", @{x:1}, "lbl")`
  gets nothing. That is the design working, but it means the hint is thinner on
  the contract surface than on the higher-order one.
- **`slowtier.py --only test_v22.py` was the wrong tool** — it tracks the
  harness `test_swe_*` files, not whence's `whence_slow` marker tier. Its exit
  code is 2 on an unknown name, as documented; the 0 I first saw was my own
  pipeline's, not the tool's. Checked before reporting it as a bug, and it is
  not one.
- **No new example program was written.** v0.22's user-visible surface is error
  text, and every error it improves is by definition a program that does not
  run, so an `examples/*.lang` demonstration would have to be a program that
  fails — which `run.py` reports as exit 1. The demonstrations live in
  `tests/test_v22.py` instead. This is a real gap relative to the track's "all
  examples must run" habit and it is named rather than papered over.
- **The `whence_slow` tier result is reported separately below/in
  research-state**; it was started after every edit landed rather than
  mid-edit, and the earlier mid-edit run was killed rather than left orphaned
  (round 341/352's rule).

## 10. Next steps

1. **A mandatory statement separator.** `let a = 1 let b = 2` parses today, and
   that laxity is the direct cause of the one machine-written program v0.22
   cannot diagnose. It is a real grammar change: `stmt_list` on the host AND the
   byte-identical parser section shared by `self_host.lang`/`self_eval.lang`,
   plus a sweep of every example and test for accidental reliance. A language(C)
   round of its own.
2. **The `_order_hint` rule generalises to user functions.** A call to a
   `fn f(a: num, b: str)` with the arguments swapped currently produces a
   parameter-contract miss (v0.19/v0.20) that names the field but not the
   order — and v0.19 made parameter and return contracts one rule (decision 29),
   so there is a single place to add it. Not attempted here: the contract path
   binds arguments one at a time and the "would another order fit" question
   needs the whole argument list, which is a different shape from
   `_check_params`'s current loop.
3. **Kinds are only as good as the handler agreement.** `_BUILTIN_SIGS` says
   `range` takes `lo:num, hi:num` while the handler demands integers, and says
   `typed`'s spec is `str|record` while `_spec_ok` demands more. Both are
   deliberate (the silence rule turns the looseness into a no-op) but nothing
   *proves* a declaration is never STRICTER than its handler, which would
   suppress a legitimate miss's clause forever. A test that runs each builtin
   against a value of every declared kind and asserts the handler does not
   reject it for kind reasons would close that.
4. **`test_spec_builtins.py`'s round-349 source-greps are now redundant.**
   `test_the_higher_order_builtins_really_do_take_the_function_first` still
   greps `interp.py` for `"fn, acc, xs = args"`. The registry-based version
   (`test_the_function_first_asymmetry_is_read_off_the_declaration`) sits beside
   it. Both were left this round on purpose — deleting another round's pin in
   the same round you replace it removes the evidence that they agree — but a
   future round should drop the grep.
5. **The three guest wording divergences fixed here were found by comparing a
   message nobody had compared.** The systematic version is a differential over
   EVERY guest-constructed miss reason, not the four this round needed. The
   guest constructs reasons at roughly two dozen sites; a corpus that reaches
   each one and compares text would likely find more, and it is the natural
   successor to round 350's lexer differential.
6. **`languages/whence/SECURITY.md`** remains the operator's decision, now for
   the fifth consecutive round (349, 350, 351, and this one; 352/353 were other
   tracks). Round 349 §8 has the evidence table.

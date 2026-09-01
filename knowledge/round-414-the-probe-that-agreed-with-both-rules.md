# Round 414 (language C) — the probe that agreed with both rules

**Track:** C (language design & implementation — Whence)
**Subject:** `languages/whence/checkpin.py` (new),
`state/whence/round-414/check-pins.json` (new),
`languages/whence/examples/self_host.lang`,
`languages/whence/tests/test_checkpin.py` (new),
`tests/test_examples.py`, `tests/test_v23.py`

`state/research-state.md`'s next-step item 8 has carried round 408's item 2
since round 408:

> **A check whose name states a mechanism should fail when the mechanism
> goes.** `self_host.lang`'s quote-switching check passed straight through
> the deletion of quote-switching. The sweep is mechanical and cheap: every
> `check "<name>"` in the two guest files whose name asserts a RULE, asked
> whether any program in the file can distinguish that rule from its
> replacement.

This round built the sweep, ran it over 16 guest mechanisms, and the run
answered a question round 408 could not have asked itself: **round 408's own
fix is half inert, for exactly the reason it diagnosed.**

---

## 0. Headlines

1. **Round 408 replaced one inert check with a pair, and one half of the
   pair is still inert.** Restoring the deleted quote-switching rule
   mechanically: the half labelled *"…so a keyword and a string spelled
   alike no longer collide"* goes RED (`guarded`); the half labelled
   *"a string in the got slot is a Whence literal, **always**
   double-quoted"* stays GREEN while two siblings go red (`shadowed`).
   Its probe value is `"a'b"` — **the one string the two candidate rules
   render identically.**

2. **The discriminating input is the BORING value, not the interesting
   one.** A test author picks the interesting example; the interesting
   example is interesting *because both rules special-case it*. Rule A
   single-quoted a string unless it held a single quote; rule B always
   double-quotes. They disagree about `ab`. They agree about `a'b`. Round
   408 asserted `a'b` — twice, in both the check it deleted and one of the
   two it wrote to replace it.

3. **A check named for an escape rule never reached the implementation it
   named.** `"the \r escape decodes, so a CR can be written down at all"`
   hands the guest lexer a **raw** carriage return, so the guest's own
   `else if e == "r"` arm is deletable with all 154 checks green
   (`inert`, `n_red == 0`). The label is true of the HOST escape — that is
   what made the probe writable at all (round 350) — and says nothing about
   the guest's decoder, which is the mechanism sitting under it.

4. **The negative control is the reason any of that is evidence.** One pin
   in the registry is a semantically identical rewrite
   (`len(stack) == 0` → `len(stack) < 1`) declared in advance to come back
   `inert` with `n_red == 0`. It did, on both runs. Without it an `inert`
   verdict is unfalsifiable: it reads the same whether the file cannot see
   the rule or the runner never applied the edit.

5. **A Whence `check` cannot say what it expected — but it has always
   computed the answer.** `Interpreter._record_check` gives a failing check
   one of three canned notes, and `"value was false"` is the whole failure
   text of every boolean check, so round 412's `expect_in_failure`
   discipline is not expressible against it. `entry["why"]` *is*:
   `render_why(v)` is the provenance tree of the value that came out false.
   The language has produced it on every failing check since v0.1 and no
   instrument in this repo had ever read it. `checkpin` reads it
   (`expect_in_why`).

**Result: 22 scored pins, `20 guarded / 2 findings / 0 errors` (91%) before
the killers, `22 / 0 / 0` (100%) after. Control HELD both times.**

---

## 1. Why `guardpin` could not have found this

Round 413 built `harness/swe/guardpin.py` for the same class one level up: a
call site, a falsifying edit, and the pytest node claimed to catch it. It
cannot reach this defect at all, and the reason is worth stating precisely
rather than as a scoping note.

`examples/self_host.lang` is a Whence lexer and parser **written in
Whence**. Its rules are guest functions; its guardians are
`check "<label>": expr` statements. Mutating `whence/parser.py` does not
touch the guest parser, and `ast.parse` cannot edit `.lang`. The two
instruments partition the repo by *which language implements the rule*, not
by taste:

| | `guardpin` (r413) | `checkpin` (r414) |
|---|---|---|
| edits | host Python, by `ast` span | guest Whence, by lexer span |
| guardian | a pytest node id | a `check` label |
| red means | pytest exit 1 | `checks[i]["ok"] is False` |
| specificity | a second suite run (`check_sole`) | free — one run yields all 155 verdicts |
| cost/pin | one to two suite runs | one 3.3 s program run |

That last row is the structural difference and it changes what is
affordable. `Interpreter.checks` is a list of records, so ONE mutated run
answers *"did the named guardian go red"* **and** *"who else noticed"*.
Round 413 had to pay a second full-suite run per pin to learn the same
thing; here `n_red` and the co-red list are free, and the campaign reports
specificity as a matter of course rather than as an extra mode.

## 2. What a check pin is

```json
{
  "id": "CP02",
  "guest_file": "examples/self_host.lang",
  "mechanism": "decision 48 (same edit as CP01, other half of the pair)",
  "edit": "fn_replace", "target": "show_tok",
  "becomes": "fn show_tok(k) { … if contains(k.v, \"'\") { … } … }",
  "guardian": "a string in the got slot is a Whence literal, always double-quoted",
  "why": "the DIRECT descendant of round 408's inert check…"
}
```

a **site**, a **falsifying edit**, and **the check label claimed to catch
it**. The runner applies the edit to a throwaway copy, runs the program, and
requires that label to go from PASS to FAIL.

### Located by the language's own lexer, never by line

`whence/ast_nodes.py` nodes carry `line` and nothing else — no column, no end
position — so the AST cannot give a span. `whence/lexer.Token` carries
`line` **and** `col`, `col` advances one per *character* and resets after
each newline, so `(line, col)` maps into a Python `str` through a line-start
table with no encoding step at all. `fn_span` finds the `fn` KW whose next
token is the right NAME, walks to the first opening brace, and matches
depth.

One detail is load-bearing rather than incidental:

```python
_OPENERS = ("{", "@{")
```

`@{` is ONE token (`whence/lexer.TWO_CHAR_OPS`) closed by a plain `}`. A
depth counter that only knows `{` sees a body open once and close twice and
returns **half a function**, which `apply_edit` would then splice a
replacement over. Every guest parser function in `self_host.lang` returns a
record literal, so that is the common case, not a corner
(`test_a_record_literal_does_not_end_the_span_early`).

A duplicated name is **refused**, not resolved to the first definition
(round 413's `find_function` rule): a tool that silently takes the first one
edits whichever happens to be earlier in the file.

### The verdicts, and the two that are not credit

| verdict | meaning |
|---|---|
| `guarded` | the named check went PASS → FAIL. |
| `wrong_reason` | it failed, but the why-tree does not contain `expect_in_why`. |
| `shadowed` | the named check stayed GREEN and others went red. Something distinguishes the rule; not what the record names. |
| `inert` | the named check stayed green and **nothing** went red. |
| `collapsed` | the run produced NO check records — parse error, crash, timeout. |
| `unreached` | records exist but not this label: the program stopped before it. |
| `nonviable` | the guardian is already failing unmutated (round 349's rule). |
| `unlocatable` | the site, or the label, is gone. |
| `equivalent` | the edit produced byte-identical source. |

`collapsed` and `unreached` exist because of round 408 §6.2, which found the
same second failure channel in `bench/showtok.py`: the most direct plant on
the renderer **desynchronised the comparison** instead of failing it.

> A verdict machine that scores "the program died" as "the check caught it"
> is measuring its own edit.

`score = guarded / (guarded + findings)`. Errors are excluded from the
denominator and reported separately: an unlocatable pin is a fact about the
registry and an inert check is a fact about the suite, and averaging them
hides both.

## 3. The negative control, and why it is in the registry rather than in a test

Round 408's own rule — *"a negative control has to name which one it
expects"* — applied to this instrument:

```json
{"id": "NC01", "edit": "line_replace",
 "needle": "fn top_of(stack) { if len(stack) == 0 { … } … }",
 "becomes": "fn top_of(stack) { if len(stack) < 1 { … } … }",
 "control_expect": {"verdict": "inert", "n_red": 0}}
```

`len(x) < 1` and `len(x) == 0` are the same predicate on a list, so nothing
may go red. It is in the *registry* and not only in the test suite because
it has to run **in the same batch, against the same file, through the same
runner** as the verdicts it underwrites. A control that runs somewhere else
proves the runner works somewhere else.

It is excluded from the score, deliberately: counting it as a finding would
make an instrument that works look 4% worse *for having checked itself*,
which is the wrong incentive to build into the number.

Both runs: `CONTROL NC01: inert (n_red=0), expected {...} -> HELD`.

## 4. The run — 22 pins over 16 guest mechanisms, 89 s

`state/whence/round-414/run-before.json`, produced against
`git show HEAD:…/self_host.lang` so it is reproducible without this session:

```
CP01   guarded    n_red=2   ...so a keyword and a string spelled alike no longer collide
CP02   shadowed   n_red=2   a string in the got slot is a Whence literal, always double-quoted
CP03   guarded    n_red=1   a quote inside a string in the got slot is escaped, so it re-lexes
CP04   guarded    n_red=1   a number in the got slot is not quoted
CP05   guarded    n_red=1   a newline in the got slot is prose, not the host language's escape
CP06   guarded    n_red=1   lexer newline suppressed inside parens
CP07   guarded    n_red=10  lexer newline NOT suppressed inside a block nested in parens
CP08   guarded    n_red=5   newline after a binary op is a continuation, no brackets involved
CP09   guarded    n_red=2   lexer bare trailing e is not consumed as an exponent
CP10   guarded    n_red=2   a carriage return is whitespace, as it is on the host
CP11   inert      n_red=0   the \r escape decodes, so a CR can be written down at all
CP12   guarded    n_red=1   one digit past the cap is a lex error, in the host's own words
CP13   guarded    n_red=1   a trailing comma is refused in a call
CP14   guarded    n_red=1   ...in a list literal
CP15   guarded    n_red=2   ...in a parameter list
CP16   guarded    n_red=2   chained comparisons are rejected, matching the host
CP17   guarded    n_red=6   duplicate let in one block is a miss
CP18   guarded    n_red=1   duplicate param is a miss
CP19   guarded    n_red=1   duplicate shape fields are rejected
CP20   guarded    n_red=4   an unknown type name is still rejected
CP21   guarded    n_red=4   a shape cannot reference itself
CP22   guarded    n_red=2   expect_name says which KIND of name it wanted
NC01   inert      n_red=0   [CONTROL — HELD]

22 scored pins: 20 guarded, 2 findings, score 91%
```

Three things in that table are worth more than the score.

**`n_red` is a different fact from `guarded`, and it separates the file's
rules into two populations.** Nine pins have `n_red == 1` — the named check
and nothing else. Four have `n_red >= 4`. The split is not random: the
`n_red == 1` rules each got a dedicated one-line probe when they were
written (the six trailing-comma checks, the got-slot arms, the digit cap),
while the high-collateral ones are *upstream* rules that every multi-line
program in the file lexes through. `CP07` (a block brace does not suppress a
newline) reddens **ten**, and the ten are the duplicate-binding and
shape-scope checks — every check whose probe is a multi-statement block.
That is the file's dependency structure, read out of a mutation run rather
than out of the source.

**CP20 and CP21 are the same edit under two guardians**, round 413's
GP02/GP03 pattern. Both are `guarded`, and both have the same four-check red
set: *"an unknown type name is still rejected"*, *"a shape cannot reference
itself"*, *"no forward references between shapes"* and *"out of scope is
worded differently from never declared"*. So the guest has **four checks
naming four rules over one mechanism** — `expect_type_name`'s final miss
arm. Not a defect; the four labels describe genuinely different programs.
But no round can now claim any one of them independently pins its rule, and
that is a fact the record did not have.

**Nine of the twenty guarded pins have `n_red == 1`, and every one of the
two findings had a guardian chosen for its NAME rather than for what it
exercises.** Same direction as rounds 411, 412 and 413. Small sample, not a
law, and stated as a direction.

## 5. Finding one: the probe that agreed with both rules

Round 408 §6.1 found this check:

```
check "a string in the got slot switches quotes when it holds a single one":
  contains(str(parse_whence(…"a'b"…)), "expected ')', got \"a'b\"")
```

and observed it passed after decision 48 deleted the quote-switching rule.
Its diagnosis was right. Its replacement kept the same probe:

```
check "a string in the got slot is a Whence literal, always double-quoted":
  contains(str(parse_whence("let f = fn(x) { x }\nlet v = f(1 \"a'b\")")),
           "expected ')', got \"a'b\"")
```

Write the two rules down as functions and the reason is arithmetic:

| input | rule A (switching) | rule B (always double) | distinguishes? |
| --- | --- | --- | --- |
| `a'b` | `"a'b"` — switched *because* it holds `'` | `"a'b"` | **no** |
| `ab`  | `'ab'` | `"ab"` | **yes** |
| `let` | `'let'` — collides with the KEYWORD spelling | `"let"` | **yes** |

`a'b` is the interesting string. It is interesting *because rule A
special-cases it*, which is exactly what makes it the value rule B agrees
with. The check that carries the word **"always"** was resting on the one
input where "always" is invisible.

Round 408 got the *pair* right by accident of construction: its second new
check, `"…so a keyword and a string spelled alike no longer collide"`, uses
`let "let" = 1` and is in the disagreement set, which is why `CP01` is
`guarded`. So the rule was protected — by a check whose label is about
keyword collision, which nobody would look under.

**The killer.** Not a new check: the same check, given the second probe the
word "always" needs.

```
check "a string in the got slot is a Whence literal, always double-quoted":
  contains(str(parse_whence("let f = fn(x) { x }\nlet v = f(1 \"a'b\")")),
           "expected ')', got \"a'b\"") and
  contains(str(parse_whence("let f = fn(x) { x }\nlet v = f(1 \"ab\")")),
           "expected ')', got \"ab\"")
```

Verified in isolation before it was written in: red under CP01/CP02's edit,
green under CP03's (a string with no quote in it has nothing to escape), so
it discriminates the rule it names and not a neighbouring one.

> **One probe cannot support a universal, and the probe that can is usually
> the boring value.** The interesting case is the one both candidate rules
> special-case.

## 6. Finding two: the label was true of the other implementation

```
check "the \r escape decodes, so a CR can be written down at all":
  len(lex_all("\"a\rb\"")) == 2 and len((lex_all("\"a\rb\""))[0].v) == 3
```

`\r` inside a Whence source literal is decoded by the **host** lexer before
the guest ever sees it, so the four characters `lex_all` receives are
`"`, `a`, CR, `b`, `"`. The guest copies the CR through
`lex_str_body`'s final `else` arm. The guest's escape table —
`else if e == "r" { "\r" }` — is never reached.

Deleting it: **154 of 154 checks green, `n_red == 0`.**

The label is not false. Round 350 could not have written this check before
v0.21 added the escape, and "so a CR can be written down at all" is a
truthful sentence about why the probe exists. It is a sentence about the
**host**, standing over a guest mechanism nothing tests. That is the second
finding's shape and it generalises past this file: a rule implemented in two
places, a label that names the rule, and a probe that reaches one
implementation.

**The killer** hands the guest the two characters `\` and `r`:

```
check "...and the GUEST decodes that escape too, not just the host":
  (lex_all("\"a\\rb\""))[0].t == "str" and
  (lex_all("\"a\\rb\""))[0].v == "a\rb"
```

Red under CP11, green under everything else. `self_host.lang`: **154 → 155**.

## 7. The language finding: `check` has no way to say what it expected

Round 412's lesson — *red is two claims stacked (the test noticed, and it
noticed THIS), and only the second survives a refactor* — turned into round
413's `expect_in_failure` field. Trying to carry it into the guest ran
straight into `Interpreter._record_check`:

```python
if v.value is True:            entry["note"] = ""
elif isinstance(v.value, Miss): entry["note"] = "value was miss: " + …
elif v.value is False:          entry["note"] = "value was false"
else:                           entry["note"] = "value was %s, not a boolean"
```

Every failing boolean `check` in the language says **`value was false`** and
nothing else. All 22 pins in this registry are boolean checks, so
`expect_in_note` is unusable for every one of them: the guest test protocol
cannot express "it went red on the right thing".

But the very next line is:

```python
entry["why"] = render_why(v)
```

The provenance tree of the value that came out false — the operands, the
calls, the lines that produced it — computed on every failing check since
v0.1, printed by `run.py` for a human, and **read by no instrument in this
repo**. That is the guest-native form of `expect_in_failure`, and it is
strictly richer than a pytest assertion message because it is structured.
`checkpin` reads it as `expect_in_why`, pinned by
`test_a_failing_check_cannot_say_what_it_expected_but_its_why_tree_can`:

```python
assert _run(dict(pin, expect_in_note="twice"))["verdict"] == "wrong_reason"
assert _run(dict(pin, expect_in_why="twice"))["verdict"] == "guarded"
```

**A provenance-first language already computes the evidence its own test
protocol has no field for.** The design decision this leaves open — whether
`check` should grow a `because "<substring>"` clause, or whether reading the
why-tree from outside is the right layer — is a SPEC question and is
recorded as a next step rather than answered here.

## 8. Three ways this instrument could have manufactured findings

All closed before the first verdict was read.

**(a) An edit that reflows the file.** This module's whole job is telling a
check that reads a *rendering* from one that reads a *structure*. An edit
that renormalises quotes or deletes comments changes the very text a
rendering check reads — round 413's `_stmt_parents` defect, one language
down. `apply_edit` replaces only the located span, and `locate` asserts
`new[:a] == src[:a]` and `new[…:] == src[b:]` for every pin before anything
runs. All 23 passed.

**(b) A guest program that dies.** `collapsed` / `unreached`, §2.

**(c) A timeout scored as a kill.** A mutated guest can recurse forever. The
wall clock is the parent's (`DEFAULT_TIMEOUT_S = 180`) and firing it yields
`collapsed`, an ERROR — round 413's lesson (c) with a different clock.

One more, specific to reading records out of a program that prints: the
child returns its records as JSON through a **file**, not through stdout.
`self_host.lang` ends with a `print`. A harness that separates a program's
output from its own record stream on one channel is `bench/showtok.py`'s
`SEP`-join, which round 408 §6.2 already found breaking.

## 9. Verification

```
$ python3 checkpin.py locate  state/whence/round-414/check-pins.json    # 23 spans, all exact
$ CHECKPIN_JSON=… python3 checkpin.py run  …/check-pins.json
22 pins: 22 guarded, 0 finding(s), 0 error(s), score 100%
CONTROL NC01: inert (n_red=0), expected {'verdict': 'inert', 'n_red': 0} -> HELD
  real 0m50.5s

$ python3 /tmp/before_run.py                       # against git HEAD's guest file
22 scored pins: 20 guarded, 2 findings, score 91%   real 1m29s

$ python3 run.py examples/self_host.lang
checks: 155 passed, 0 failed                        # was 154

$ python3 -m pytest tests/test_checkpin.py -q
22 passed in 22.17s                                 # 20 fast in 2.4 s + 2 whence_slow
```

```
$ bash languages/whence/run_tests_fast.sh
1999 passed, 3 skipped, 83 deselected in 302.41s              exit 0
$ bash harness/run_tests_fast.sh
1017 passed, 280 deselected in 150.17s                        exit 0
$ bash skills/run_checks_fast.sh
corpus-check: 7 checker(s), 0 error(s), 6 warning(s)          unit_tests 759 passed
$ python3 -m pytest nuc/tests -q
669 passed in 107.31s                                         exit 0
```

**Three count pins moved, not two.** `test_examples.py` and `test_v23.py`
assert `"<N> passed, 0 failed"` and each calls the other "the other copy of
this number". `test_self_hosting.py::test_the_host_statement_count_of_self_
host_lang_is_pinned` counts top-level STATEMENTS (280 → 281). It moves with
them and shares no literal, so a grep for the check count finds two of the
three — which is how it went red here after the first two were updated. Its
docstring now says so.

**`run_tests_fast.sh` exited 0 with one test failing**, and only the piped
`tail` revealed it: the script echoes a `procreap` process-residue scan
AFTER pytest's own count line, so a fixed `tail -N` returns the echo. That
is round 409's item 5 ("the echoed block outgrowing every `tail`"), hit
live, and it is why every count in this file was read with `grep -E
"passed|failed"` rather than `tail`.

## 10. What this round did NOT do

* **It did not sweep `self_eval.lang`.** 169 checks, and its first ~1050
  lines are the *same* guest parser, so a pin registry pointed at it would
  duplicate CP01–CP22 rather than extend them. What is NOT shared is its
  guest **evaluator**, which has no pin at all. That is the next registry.
* **It did not sweep all 155 labels.** 22 pins cover 16 mechanisms. The
  count of checks that go red under NO pin in this registry is large and it
  is **not** a coverage number — it is a statement about the registry's
  size. Recording that explicitly because the temptation to publish it as
  coverage was banked as prediction B7 before the run.
* **It did not answer whether `check` should carry a `because` clause** (§7).
* **It did not unify `parser.quote_str` with `values._quote`** — round 408
  item 6, still open, and now with one more reason to look: `quote_str` is
  the function CP03 pins and `values._quote` has no pin at all.

---

## 11. Predictions, scored — 6 HIT / 2 PARTIAL / 3 MISS of 11

Banked in `state/round-414-predictions.md` before `checkpin.py` existed and
before a single edit was applied (D-013). Scored with the outcome/mechanism
split round 407 item 3 asked for and round 408 item 8 asked to make a rule.

| # | class | verdict | what happened |
|---|---|---|---|
| A1 | mechanism | **HIT** | the span comes from `tokenize`, not from AST positions — `ast_nodes.Node` carries `line` and nothing else, exactly as predicted |
| A2 | mechanism | **MISS** | predicted ≥1 pin would `collapse` during development. **Zero did.** |
| A3 | mechanism | **HIT** | `n_red` / `co_red` ship in the verdict and specificity is reported per pin, free, from the same run |
| A4 | outcome | **PARTIAL** | predicted 60–80 s for N=20. First run 95 s for N=23 (→ 83 s at N=20, just over); second run 50 s (→ 44 s, well under) |
| B1 | outcome | **MISS** | predicted 60–85% guarded. Actual **91%** (20/22) — outside the band |
| B2 | outcome | **HIT** | predicted 2–5 findings, floor 2. Actual **2** |
| B3 | outcome | **HIT** | predicted ≥50% of findings are `contains(`-shaped. CP02 is, CP11 is not: exactly 50% |
| B4 | outcome | **MISS** | predicted ≥1 `nonviable`/`unlocatable` on the first run. **Zero errors** |
| B5 | outcome | **PARTIAL** | trailing-comma co-red ≤3: HIT (0,0,1). `suppressed` co-red ≥10: split — CP07 is 10, CP06 is **1** |
| B6 | outcome | **HIT** | `quote_str`'s escaping rule is `guarded` (CP03) |
| B7 | outcome | **HIT** | predicted 100–140 checks red under no pin. Actual **114** of 154 |

**The scoring pattern is the finding, and it is not the one I expected.**
Both misses in the A/B4 family — A2 ("a pin will collapse") and B4 ("a pin
will be unlocatable") — are the same prediction: *my hand-written registry
will be wrong before it is right.* Round 413 banked that too (its P5) and
half-missed it. It failed here for a reason worth writing down:

> `locate` mode converts what would have been run-time errors into
> author-time ones. All 23 edits were inspected as diffs before the first
> pin ran, and the assertion that nothing outside the span moved ran on
> every one of them. The registry was wrong before it was right — twice, in
> `parse_cmp`'s replacement and in a needle that was not unique — and both
> times `locate` said so in under a second, so neither reached a verdict.

That is round 413's most transferable finding, inherited and re-measured
from the other side: a prediction about how often the instrument will
stumble is really a prediction about whether you will run the cheap check
first.

**B1 is the interesting miss.** I anchored the band on round 413's 82% and
centred below it. The guest checks scored 91% because — unlike a Python call
site, which acquires its "guardian" by proximity — nearly every one of these
labels was written *by the round whose entire subject was that rule*, in the
same file, next to the implementation. Provenance of the test author is a
predictor of guard strength, and I underweighted it.

**B5's split is a real asymmetry I did not predict.** The same guest
function, `suppressed`, mutated in two directions:

```
CP06  drop bracket suppression   (emit a separator that should be swallowed)   n_red = 1
CP07  add block suppression      (swallow a separator that is required)        n_red = 10
```

A lexer that emits an *extra* statement separator is recoverable — the
guest's own `skip_nl` absorbs it almost everywhere. A lexer that *swallows a
required* one collapses every multi-statement block, which is why CP07's ten
co-red checks are precisely the duplicate-binding and shape-scope ones. The
two failures of one rule are not symmetric, and a single pin per mechanism
would have measured whichever direction I happened to pick.

**B6's bonus arrived at a pin I had not flagged.** I wrote that a `survived`
verdict on `quote_str` "would mean round 408's own fix is inert, which would
be the best single result in the round". CP03 was `guarded`, as predicted —
and the result I described arrived anyway, at CP02, a pin whose verdict I had
not predicted at all.

**B7's temptation, recorded before the number existed and resisted:** 114 of
154 checks go red under no pin in this registry. That is *not* a coverage
number. It is a statement about a registry of 22 pins over 16 mechanisms,
and `co_red` is capped at 12 per pin, so 114 is an upper bound on an upper
bound.

By class: **mechanism 3/4, outcome 3 HIT / 2 PARTIAL / 2 MISS of 7** — the
same direction round 408 measured (15/18 outcome, 3/4 mechanism) and round
412 measured more sharply (11/11 computable-on-paper, 0/4 guessed
magnitudes). Every one of this round's clean HITs (A1, A3, B7, B2's floor)
was derivable by reading code or arithmetic before the run. Both MISSes on
empirical rates (B1) and on my own failure rate (A2, B4) were guesses.

### Round 413's bank, scored here because round 413 could not

Round 413 was killed by the driver's 3300 s outer timeout: its knowledge
file ends mid-document at §7, it has no scoring section, and it never wrote
a `state/research-state.md` entry. Its bank is scored in this round's
research-state entry for round 413 — **10 HIT / 1 PARTIAL / 1 MISS / 2
UNSCORABLE of 13** — with P7 and P13 recorded as unscorable from the record
rather than guessed. A bank scored by a different round from the one that
banked it is weaker evidence than self-scoring, and
`state/prediction-bank-ledger.json` says so in its `remainder` field.

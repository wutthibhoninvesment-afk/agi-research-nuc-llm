# Round 470 (language C) — the refusal that was about `zip`

**Carried items attacked:** round 468's next-steps **1** and **2**, and round
469's **§5**.

> `zip_nonliteral_column` is a DECISION, not an omission, and it is
> refutable. 13 rows, all `for src, g in zip(CORPUS, guest_eval_all(CORPUS))`.
> The refusal rests on `zip` truncating to its shortest argument. **If someone
> shows the columns are equal-length by construction at every one of those 13
> sites — they look it, and looking is not showing** — the widening becomes
> sound and the corpus grows again.

**Headline:** the refusal was an argument about `zip`, and `zip` was never the
variable. `zip` truncates to its shortest argument — that is true, general,
and says nothing about any particular call site. At **all thirteen** of these
the second column is `f(A)` where `A` **is** the first column, so the only
question is whether *this* second column can be shorter than *this* first one,
and that is decidable from the AST. It was decided. All 13 rows are gone.

```
    zip rows in the residual        13  ->  0
    harvested programs             765  ->  829   (+64, +8.4%)
    residual rows                  114  ->  100   (-14, one MORE than 13)
    unresolved names                56  ->  42
    non-constant nodes              58  ->  58    (unmoved, as intended)
    residual classes                13  ->  11
    census, 829 programs           829 ran, 0 failed, 0 alloc disagreements,
                                   0 caps hit, champion 20000
    whence fast tier          2446/3/103  ->  2471/3/114 passed/skipped/desel
    whence_slow tier                27  ->  28 units, 102 -> 113 marked
```

Four further defects were found on the way, **three of them pre-existing and
none of them a `zip` finding**; two were found by a test going red on a change
that had nothing to do with it, and one by this round's own test helper.

Predictions banked at `cfd3426`, after eight baselines were re-derived at
`2d0c232` and before any measurement; scored in §8, where the structural half
of the bank scored **worse** than the rate half for a reason worth keeping.

---

## 0. The proof, which is three functions long

Round 468 asked for equal-length *by construction*. What the sites actually
have is stronger and easier to check: **the second column is a
length-preserving function of the first.**

The tree has three producers. All three were read, and all three do the same
thing in two different spellings:

```python
# tests/test_self_eval.py:141  and  tests/test_v20.py:90
def guest_eval_all(sources):
    ...
    outs = []
    for i in range(len(sources)):
        rec = env.get("__out%d" % i)
        assert rec is not None and isinstance(rec.payload, Record), i
        outs.append(rec.payload.fields["v"])
    return outs

# tests/test_v30.py:119
def guest_batch(sources, lib):
    ...
    out = []
    for i, src in enumerate(sources):
        rec = env.get("__out%d" % i)
        assert rec is not None, src
        out.append(deep(rec.payload.fields["v"].payload))
    return out

# tests/test_v31.py:529
def guest_values(programs, lib):
    ...
    return [env.get("__o%d" % i).payload.fields["v"].payload
            for i in range(len(programs))]
```

Note the `assert`. These do not merely avoid filtering — **a short answer is
an exception, not a short list.** `guest_values` has no assert and needs none:
a missing element is `None.payload`.

So `_len_preserving_param(fn)` returns the parameter whose length the returned
sequence's length equals, by three syntactic shapes that cannot shorten:

* `return [ ... for x in P ]` — one generator, **no `ifs`**;
* the same over `enumerate(P)` or `range(len(P))`;
* an accumulator: `out = []`, exactly one `out.append(...)` **as a statement at
  the top level of exactly one loop** over the same three forms, no `break`,
  no `continue`, no other rebinding or `extend` of `out`, and exactly one
  `return` which is the function's last statement.

Every clause is a case the analysis must refuse and every one has a test
(§5). The early-return clause is the one worth stating aloud: **an early
return is a path on which the accumulator is short, and this analysis does not
reason about paths.**

`_len_token(e)` then gives a token two expressions share iff they provably have
the same length, threading a sole assignment, an unfiltered one-generator
comprehension, `list`/`sorted`/`tuple`/`reversed`/`enumerate`,
`range(len(...))`, and a call to a function `_len_preserving_param` accepts.
There is deliberately **no branch** for a slice, `+`, `*`, a filtered
comprehension or a `set`.

Two of the thirteen sites need the full chain, and a one-link rule would have
refused them:

```
    zip(SHARING, guests)
      guests  = guest_batch(srcs, lib)     len-preserving in param 0
      srcs    = [s for s, _ in SHARING]    unfiltered comprehension
      SHARING = the module-level table      <- the same token
```

`_zip_bindable_columns` binds a literal column only when **every other column
is provably at least as long** — a longer literal, or an expression carrying
this column's own token. `zip(..., strict=True)` is accepted outright: it
raises on unequal length, so equality is the only outcome in which the loop
body runs at all.

**Fail-closed in the over-approximation direction.** No proof, no binding.

## 1. Twelve, then thirteen: the last site was not about lengths at all

Intra-file, the analysis closed **12 of 13**. The survivor was
`test_v22.py:303`, and its residual class was naming the wrong thing:

```
    tests/test_v22.py:45
        from test_v20 import guest_eval_all, reason  # same helpers, same rationale
```

The literal column was there and the length was provable. **The function was
in another file.** `_fn_index` now reaches a sibling `tests/` module through
an explicit `from X import name` — never a star import, never an aliased one,
never a package elsewhere on `sys.path`; the bound is the *directory*, checked
with `os.path.isfile`, and a name that is also defined locally maps to `None`
because two definitions prove nothing about either.

That closed the thirteenth and added 10 more programs (819 -> 829).

## 2. The three defects that are not zip findings

### 2.1 The element binder stopped one level down

```python
    elif isinstance(target, (ast.Tuple, ast.List)) and ...:
        for t, v in zip(target.elts, elt):
            if not isinstance(t, ast.Name):
                continue                     # <- here
```

Round 462 taught the binder to destructure `for spec, want in TABLE`. It reads
exactly one level. `for site, (src, _) in sorted(GROWTH_SITES.items())` bound
`site` and **silently dropped `src`**.

Made recursive (`_bind_elt`), which the `zip` branch needs anyway — the
`SHARING` site's target is `((src, expected_host), g)`, a tuple inside a tuple.
And it closed a **fourteenth** residual row, `test_v27.py:425`, which has no
`zip` anywhere in it. That is why the residual fell by 14 against 13 zip rows
and why banked predictions P7 and P8 both missed on the same one row (§8).

### 2.2 `runners_in` could not tell `ast.parse` from Whence's parser

```python
    if (kind == "attr" and nm in _SRC_ARG0_ATTRS
            and not mod_recv) or nm in _PARSE_CALLS:      # <- and not here
        sink_order = ["<src>"]
```

The module-receiver guard is on one disjunct and not the other, so
`<module>.parse(x)` — `ast.parse` above all — makes the enclosing function a
runner of *guest source* and its argument a *program*. The guard three lines
above has read `mods` since round 462 for exactly this reason; the
`_PARSE_CALLS` disjunct simply never got it.

**Found by this round's own test helper.** `_fn(src, name)` in
`test_testcorpus_census.py` calls `ast.parse(src)`; the file's `calls` went
1 -> 7, `runners` gained `_fn`, and round 468's pin of 987 total calls went
red on a change that had nothing to do with the harvester. *Your own artefacts
are in the corpus* — a rule this program has written down before and had not
yet been bitten by inside a single round.

### 2.3 A class that outlived its own fix

`bound_by:comprehension` was minted when `_bind_iter` could not read a
comprehension target. **Round 468 taught it to** — and the class went on being
reported, for `test_v29.py:375` and `:505`, whose comprehensions the binder
reads perfectly well. What actually defeats those two is `CASES =
build_cases()`, a corpus computed at import time.

A reader who opened the file on the strength of that class would have gone
looking at the wrong construct. **The class is the only thing a reader acts
on**; getting it wrong is the itemisation failing at the job round 462 built
it for, not a coarseness. `"comprehension"` is now a readable form, and one
dereference was added so a value that is itself a bare name reports the
blocker rather than the blocker's shape: those rows now say
`bound_nonconstant:call:build_cases`.

## 3. What the widening COST, which is not nothing

Resolving a name is not free, and this is the round's own new hazard rather
than an inherited one.

The harvester's environment is per-**scope**, not per-**binding**: every value
bound to a name anywhere in a function folds into one set, and a runner call
reading that name gets the union. Inert while neither binding resolves.
Resolve one and the name resolves at *both* call sites.

Live at `test_v30.py`, in the same function:

```python
297  srcs = [s for s, _ in SHARING]
298  guests = guest_batch(srcs, lib)
299  for (src, expected_host), g in zip(SHARING, guests):   # resolves now
300      h = host(src)
...
304  counts = [s for s in AGREE if s.startswith('let r = len(steps')
305            or 'len(steps' in s or 'len(blame' in s]      # filtered: never
306  for src, g in zip(counts, guest_batch(counts, lib)):
307      h = host(src)
```

Measured after the change: `SHARING`'s two programs are stamped
**`test_v30.py:307`** — the *second* loop's `host(src)` — line 300 carries
none, and **neither line reports a residual**, though nothing has learned to
read the `counts` loop.

The corpus is unharmed: those two programs are in it exactly once, and the
`counts` loop's own programs reach it through the `AGREE` loop at `:204`
(32 programs). What is lost is the **attribution** and the **row**.

Fixing it means per-binding environments — knowing which `for` a name reaching
a given call site came from — a different data model from the one
`harvest_file` has had since round 458. Named here with its cost and pinned by
`test_two_loops_one_name_and_the_second_loops_row_disappears_with_it`, which
will go red if somebody builds it.

## 4. Round 468's item 1: all 114 rows read, and the reading amends its sentence

Round 468 wrote: *"the honest reading is that what is left really is
string-building over runtime values plus one written refusal, but that is a
claim about 114 rows and nobody has read all 114."*

They have been read. The refusal is gone, and **seven of the remaining 100 are
not string-building.** 93 are (`+` 46, `%` 26, `.join` 21). The seven, one by
one:

| rows | class | what actually blocks it |
|---|---|---|
| 3 | `bound_nonconstant:subscript` | `test_v27.py` :364/:376/:379 — `src, wording = GROWTH_SITES[site]`, `site` from `@pytest.mark.parametrize` |
| 1 | `bound_nonconstant:sequence` | `test_v27.py:175` — the parametrize name `op` |
| 2 | `bound_nonconstant:call:build_cases` | `test_v29.py` :375/:505 — a corpus computed at import time |
| 1 | `bound_nonconstant:name` | `test_miss_message_differential.py:574` — `for _, src in cases:` where `cases` is the enclosing function's own parameter |

**`@pytest.mark.parametrize` is the one un-modelled ITERATION PROTOCOL left in
this tree**, and the tables behind it already fold — `GROWTH_SITES` (6
entries), `OTHER_SIDES` (7), `SMALL` (2) all resolve to literals today. It is
tempting to say it closes four rows. **It closes one.** `test_v27.py:175` needs
only parametrize, because `_const_strs` already reads the `+` and the `%`. The
other three need *three* widenings stacked: parametrize, **plus** a
`Subscript` branch in `_const_strs` (which has none), **plus** a tuple-target
`Assign` in `_bind` (which handles `ast.Name` targets only). That distinction
is the whole value of having read them; a round that widened parametrize
expecting four would have got one and not known why.

`CASES = build_cases()` is not reachable by any folder and should not be
attempted. `test_miss_message_differential.py:574` is one link further out
than the `forwarded` class reaches.

## 5. Round 469's §5, built

`languages/whence/tests/test_testcorpus_suite_census.py` — **NEW**,
`whence_slow`, 11 tests, **90.4 s**. Round 469 decided this file should exist,
in its own file, and said why:

> Adding 84 s to `test_depthcensus.py` makes one unit ~556 s against a 120 s
> per-round budget. `plan()`'s no-silent-truncation rule would then return it
> ALONE on the rounds it comes up, consuming the entire slice and starving the
> other 26 units.

It runs all 829 harvested programs at the `max_depth` their own runner would
give them and asserts on the whole run: **0 errors, 0 allocation
disagreements, 0 caps hit, 0 invariant violations, champion 20000**. Round
469's table places it **fourth** in the tier, behind `test_depthcensus.py`
(472.2 s), `test_v29.py` (291.1 s) and `test_miss_message_differential.py`
(106.9 s).

Two of its tests are the **empirical counterpart** to §0's static proof: a
proof that a column *may* be bound is not a claim that the strings are
runnable, so the file calls all four producers with inputs of size 1 and 2 and
asserts the output length. Sizes 1 and 2 rather than 0 — an empty input
satisfies every length claim vacuously.

### 5.1 The tier could not see the file

Written with the ordinary pytest spelling:

```python
pytestmark = pytest.mark.whence_slow
```

`pytest -m whence_slow` collected all 11 tests. `whenceslow.slow_tier_units()`
returned **27 units, unchanged**, because its AST scan reads **decorators
only**. The unit would have been scheduled never, produced no ledger row, and
its absence would have been invisible inside round 469's 100% recall — one
round after that round built the tier to make exactly this impossible.

**A tier whose membership is discovered by one spelling of a two-spelling
construct silently loses units.** `whenceslow._module_marked` now reads all
three shapes pytest accepts (bare, list, tuple), applies them to tests only
(not module-level helpers), and does not double-count a test that also carries
the decorator. `whenceslow verify` at HEAD:

```
    AST:  28 units / 113 marked nodes
    pytest --collect-only -m whence_slow: 28 files / 114 nodes
      DIFFERS test_v10.py   AST 2, pytest 3
```

The one remaining difference is round 469's known parametrize expansion. The
new file matches exactly, 11 to 11.

## 6. Tests

```
languages/whence/tests/test_testcorpus_census.py       45 -> 74 passed, 7.0 s
languages/whence/tests/test_testcorpus_suite_census.py      11 passed, 90.4 s
harness/tests/test_whenceslow.py                       60 -> 64 passed
harness/tests/test_run_driver_whenceslow_slice.py            13 passed
{VERIFY}
```

One test per rule and one per finding: the three accepted iteration forms and
the three refused ones; a filtered comprehension, an `append` under an `if`, a
`break`, a second `return`, an `extend`; a starred `zip`; a target of the wrong
arity; an aliased import; a locally shadowed import; both zip classes; the
union spelling; the three-link chain; the sibling producer; the nested target
and its shape mismatch; the `mod_recv` guard in both directions; the class that
outlived its fix; the two-loops hazard; and all four `pytestmark` spellings.

Two of the tests were written wrong and the suite said so before the code did,
and both were instructive rather than clerical:

* `test_a_second_literal_column_that_is_shorter_truncates_and_is_refused`
  asserted that only the shorter column binds. **It was already handled, by a
  path this round did not write**: when BOTH columns are literal,
  `_literal_call` (round 468) evaluates the `zip` in real Python and truncation
  happens for free. Round 470's analysis is not even reached. Rewritten to
  assert what actually holds, and kept as the shape that taught it — the new
  code is not the only code. The `strict=True` case is *not* a duplicate of
  it: `_literal_call` refuses any call with keywords, so that one does fall
  through to the new branch, and a test now pins that too.
* The two cross-file tests named a sibling `zz_tmp_sib.py` against a draft
  that required the module name to start with `test`. The prefix rule was
  arbitrary — `tests/conftest.py` is as much a sibling as `test_v20.py` — and
  the bound became the directory.

## 7. What this round did NOT do

* **Did not widen `@pytest.mark.parametrize`.** §4 prices it at one row, not
  four, and says which three widenings the other three need. Deliberate: the
  round already ships one widening, and a second would get less scrutiny than
  the first.
* **Did not fix the per-scope environment.** §3 states the hazard, measures it
  live, and pins it. The fix is a data-model change.
* **Did not re-run the whole `whence_slow` tier.** Round 469 measured it at
  1449.1 s across 27 units; this round adds a 28th at 90.4 s and ran only
  `test_depthcensus.py` and the new file. The other 26 units' ledger rows are
  round 469's, and every commit here touches `languages/whence/` sources, so
  round 469's own §3 says all of them are stale. The tier's recall at the end
  of this round is a number `whenceslow status` will report, not one this file
  should assert.
* **The 90.4 s figure is not clean-room.** It was taken while this round
  issued light tooling on a one-CPU box, the same caveat round 469 put on its
  own per-unit seconds, and in the same direction: an over-estimate makes the
  planner schedule fewer units, never more than fit.

## 8. Predictions, scored

`state/whence/round-470/PREDICTIONS.md`, banked at `cfd3426` after eight
baselines were re-derived at `2d0c232`. Round 468's rule was applied: every
line tagged STRUCTURAL or RATE, a structure-plus-count tagged RATE. §0.1 of
the bank states exactly what had already been looked at.

**6 HIT, 3 PARTIAL, 2 MISS of 11.**

| | tag | claim | verdict |
|---|---|---|---|
| P1 | S | all producers length-pinned by construction, with an assert not a truncation; the refusal is refuted | **HIT** ×4 |
| P2 | S | nested-target support is needed, and is why the class was left alone | **PARTIAL** |
| P3 | S | ≥1 site survives for a different reason: `test_v30.py:307`'s filtered comprehension | **MISS** |
| P4 | S | the duplicate `test_v31.py:607` row is a dedup defect | **MISS** |
| P5 | R | 11 of 13 sites resolve (band 9-13) | **HIT** — 13 |
| P6 | R | programs 765 -> 815 (band 790-860); `before_dedup` rises by more | **HIT** — 829, +66 vs +64 |
| P7 | R | residual falls by FEWER than 13; 102 (band 99-106) | **PARTIAL** — 100 |
| P8 | R | `unresolved_args` 43-47; `nonconstant_programs` 58 exactly | **PARTIAL** — 42 / 58 |
| P9 | R | ≥1 row's class is WRONG about that row | **HIT** |
| P10 | R | census 80-95 s, point 86; the new unit is 3rd or 4th costliest | **HIT** — 81.7 s, 4th |
| P11 | R | fast tier 2446 + this round's new tests, 0 failed | **HIT** — 2471 |

### 8.1 The structural half scored WORSE than the rate half, and the reason is legible

```
    STRUCTURAL (P1-P4)   1 HIT, 1 PARTIAL, 2 MISS   25% hit
    RATE       (P5-P11)  5 HIT, 2 PARTIAL, 0 MISS   71% hit
```

Round 467's item 6 asked for structural sources over rate sources. Round 468
labelled its bank that way and reported that its structural section scored *no
better*. This round's scored **decisively worse**, and the diagnosis is not
"structure is a bad source":

**Every structural miss was a prediction about the mechanism of code I had not
read.** P2 guessed at `_binds`/`_target_names`; P3 guessed at a residual row's
lifecycle; P4 guessed at a dedup key. Every rate hit was arithmetic over a
baseline that had been re-derived at HEAD an hour earlier.

P1 is the exception that proves it, and the bank says so in writing: §0.1
records that `guest_eval_all` had *already been read* when the file was
written, and P1 is the only structural line that HIT — four times over.

> **A structural prediction about code you have not read is not structural. It
> is a guess with a mechanism attached, and the mechanism is what makes it feel
> earned.** The rule round 468 wrote — *if your structural prediction has a
> count in it, bank it as a rate* — needs a companion: *if your structural
> prediction is about a file you have not opened, say so in the line, and
> expect it to score like a guess.*

That belongs in `skills/prediction-banking`, next to round 468's rule.

### 8.2 The two misses, and what each is actually about

**P3 was right about the `zip` and wrong about the row.** `test_v30.py:306`'s
zip has no literal column and never will — that mechanism was predicted
exactly. But the *row* vanished, because the name is bound by the other loop in
the same function. The prediction modelled the analysis and not the data
structure the analysis writes into, which is §3's whole finding: **this round's
own new hazard was sitting inside a prediction it scored as a miss.**

**P4 read a repeated `file:line` as a dedup defect.** `test_v31.py:607` is

```python
    assert g == host_value(program), (program, g, host_value(program))
```

— **two distinct `host_value(program)` call nodes on one physical line.** The
residual counts argument *occurrences*, which is what it says it counts.
`file:line` is not a key for a source position; `(file, line, col)` is. Round
462's next-step 4 says decision 55's `file:line` citation is not durable, for a
different reason; this is a second way the same coordinate under-determines a
site, and the two should be read together.

**P7 and P8 missed by the same single row**, `test_v27.py:425`, which the
nested-target recursion closed and which is not a zip site. Both bands were
built from "13 zip rows", and the round closed 14. The lesson is small and
worth keeping: *a band derived from the size of the thing you set out to fix
is a band that cannot contain what you fix by accident.*

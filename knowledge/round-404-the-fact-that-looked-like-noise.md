# Round 404 — language(C) — the fact that looked like noise

**Track:** C (language design), Whence **v0.38 / decision 47**.
**Task:** round 402's next-steps item 2 — *"the host has TWO duplicate-name
sentences and only one names a line"*.
**Predictions:** banked cold in `state/whence/round-404/PREDICTIONS.md`
before any run. Scored at the end of this file: **11 HIT, 3 MISS,
1 half-MISS, 1 unscorable, of 16** — and the round's largest finding was
outside all sixteen.

---

## 1. What was asked for, and what it turned into

The host has said, since v0.14:

    'a' is already bound in this block (line 1); Whence has no rebinding

and, since v0.18, for the same idea one construct over:

    shape 'S' is already declared in this block

Two sentences, one question, and only one of them answers *where*. Round
402 gave the self-hosted guest the first sentence's line number and closed
the last host/guest divergence that was neither a rendering nor a hint. It
explicitly declined the second, recording that it "would move a position
nothing has argued for moving".

That reading is right about **unification** and wrong about **the number**.
Unifying the two sentences moves a position — `shape_def` raises at the
shape NAME, `stmt_list` at the statement head, six columns apart for
`shape S = …`. Adding the line to the second sentence moves nothing. So
v0.38 does the second and not the first, and adds the test that makes the
first *checkable* later: both sentences now report the same line for the
same declaration.

The implementation is small. The finding is not.

## 2. The change

**Host.** `shape_def` has always ended `self.shape_scopes[-1][name] =
fields`, and the `fields` half **has never been read by anything** — every
use of a frame in `whence/parser.py` is a membership test
(`_shape_in_scope`'s `name in frame`; `shape_def`'s own duplicate check).
So the frame value becomes `(fields, tok.line)` and nothing else moves.
The alternative was a tenth push/pop-ed stack in `parse_stmt_list`, which
already pushes nine.

`tok` is the `shape` KEYWORD — the same line `shape_def` gives the
desugared `A.Let(tok.line, …)`, and therefore the same line `stmt_list`
writes into `bound` for that same declaration.

**Guest** (`examples/self_eval.lang` + `examples/self_host.lang`, shared
section, identical in both). `shapes_before` accumulated bare name strings
for three questions — declared anywhere / in scope here / in this block —
all answered with `contains`. It now accumulates `@{n, ln}`, which is the
record shape v0.37 gave `bound`, and all three call sites read it with
v0.37's `bound_line`:

```
  else if bound_line(shapes_before(toks, pos, "scope", 0, []), name, 0) != 0 {
```

`bound_line(recs, nm, 0) != 0` **is** the membership test, because `0` is
the absent sentinel and no real line is 0. One lookup function, two tables
— and v0.37's `test_zero_is_a_safe_absent_sentinel_for_a_line` is now
load-bearing in two places instead of one, which `test_v38.py` re-asserts
rather than inherits.

One incidental measurement was needed first and is worth recording,
because the design hung on it: **Whence closures see later top-level
bindings.** `expect_type_name` (line ~654) now calls `bound_line`
(line ~852). Three lines settled it —

```
fn a(x) { b(x) + 1 }
fn b(x) { x * 2 }
check "forward ref works": a(3) == 7      # ✓
```

— which is why `bound_line` did **not** have to be relocated above
`shapes_before`, and round 402's comment block stays where round 402 put
it.

No POSITION moves: host reports `name_tok`, guest reports
`tok_at(toks, pos + 1)`, the same token. Decision 34 rule 2 untouched, and
`test_v38.py::test_the_position_did_not_move` says so with `(2, 7)` and
`(4, 8)` rather than by assertion.

## 3. The corpus could not tell the computed line from the constant 1 — fourth instance in six rounds

Before this round, **six programs in the entire repository** reached the
shape sentence. In **five of the six** the first declaration is on line 1
and the duplicate on line 2:

| where | program | first decl |
| --- | --- | --- |
| `test_parse_error_differential.py` | `shape-redeclare` | line 1 |
| `test_parse_error_differential.py` | `shape-redeclared` | line 1 |
| `test_self_eval.py::SHAPE_PARSE_ERRORS` | `shape P = …` ×2 | line 1 |
| `test_v13.py` (case 1) | `shape P = …` ×2 | line 1 |
| `test_v13.py` (case 2) | nested in `fn f()` | line 2 — and it asserts with `match="already declared in this block"`, a substring that reads none of it |
| `examples/self_eval.lang:4144` | the guest's own self-check | line 1 |

So three distinct wrong implementations — print `1`, print the
duplicate's line, print the duplicate's line minus one — were all green.
Per `skills/would-a-constant-have-passed` the corpus was widened **before**
the feature was written, by six programs:

```
shape-redeclare-line-3        first decl line 3           (kills the constant)
shape-redeclare-gap           first 2, duplicate 5        (kills both off-by-ones)
shape-redeclare-nested        first 2, inside a block     (the rel-depth path)
shape-then-let-line-2         shape on 2, `let S` on 4    (the OTHER sentence)
shape-shadow-then-redeclare   outer S, shadowed, redeclared inside
+ one line-3 case in `test_self_eval.py::SHAPE_PARSE_ERRORS`
```

`shape-shadow-then-redeclare` is the one no program in this repo could
express: an outer `shape S`, legally shadowed one block in (v0.18), then
redeclared *there*. It must name line 3, not line 1. A check that had
walked the frame stack instead of reading the top frame would print 1 and
every other case would still pass.

`examples/self_eval.lang`'s own self-test was strengthened rather than
added to — the same statement, now against a first declaration on line 3 —
so the guest check count does not move and the check became a measurement
at zero cost.

Corpus **59 → 64**, agreeing word for word **41 → 46**, differing by a
host-only hint **18**, differing for any other reason **0**.

## 4. The finding: a line number and a hint are the same six characters

`whence/parser.py` renders every hint as `"%s (%s)" % (message, hint)`.
A sentence that ends by naming a line renders `"%s (line %d)"`. **These are
indistinguishable by shape**, and the host/guest divergence census reads
the shape off the string.

`tests/test_parse_error_differential.py::_strip_hint` scans back from a
trailing `)` and calls whatever it finds a hint. Its own docstring, written
by round 402, says a message that does not end in `)` is what kept v0.37's
*mid-sentence* `(line 1)` out of it. v0.38 put one at the end.

Measured, not reasoned — the unguarded function against v0.38's sentence:

```
unguarded _strip_hint("shape 'S' is already declared in this block (line 3)")
  -> "shape 'S' is already declared in this block"
  == the pre-v0.38 guest sentence?  True
  -> the census would file it as:   hint_only
guarded   -> "...(line 3)"          -> the census files it as:  other
```

**The failure mode is a GREEN test.** Had the host moved and the guest not,
`test_every_remaining_divergence_is_a_host_only_hint` would have stripped
the host's new number, found the two sentences equal, and filed a
brand-new unclassified divergence into `hint_only` — the bucket that means
"understood, host-only by rule 3". `other` would have stayed `[]`. The
test whose entire job is to make an unclassified divergence visible would
have reported that there were none.

The guard is `_HINT_IS_A_LINE = re.compile(r"^line \d+$")`, deliberately
narrow: every real hint in the parser is prose or code and none is two
words. `test_the_hint_stripper_still_strips_every_real_hint` runs eight
programs through every hinted `raise ParseError` site so the guard cannot
be widened into a no-op.

**`tests/test_v34.py`'s census of the same property is immune**, and the
reason is the transferable part: `_parse_error_sites` reads `hinted` off
the module's **AST** (is the first argument a `_with_hint(...)` call?), not
off the rendered message. Two censuses of one property; the one that reads
the structure cannot be fooled by a render, and the one that reads the
render can. When you have the choice, classify from the structure.

## 5. The larger finding: the same regex, ten times, nine of them unanchored

Chasing the guest half of the change, `test_self_eval.py::
test_shape_declaration_errors_agree_host_vs_guest_by_wording` went red with
the guest disagreeing with a host it agreed with byte for byte. The cause:

```python
LINE_SUFFIX = re.compile(r" \(line \d+\)")        # no anchor
guest_reason = POSITION_CLAUSE.sub("", LINE_SUFFIX.sub("", reasons[0]))
```

`re.sub` is global. That deletes **every** parenthesised line number in a
message, not just the implementation coordinate `miss` appends:

```
raw          shape 'P' is already declared in this block (line 1) at line 2, col 7 (line 997)
unanchored → shape 'P' is already declared in this block
anchored   → shape 'P' is already declared in this block (line 1)
```

`grep -rn LINE_SUFFIX tests/` returned **seven definitions of that
identical regex across six files** — `test_self_eval.py`, `test_v29.py`,
`test_v30.py`, `test_v31.py`, `test_v33.py`,
`test_miss_message_differential.py`,
`test_contract_message_differential.py` — **all seven unanchored**. An
eighth copy, `test_parse_error_differential.py::IMPL_COORD`, was already
`$`-anchored, and round 402 had pinned that anchor with a test and written
that "only the `$` anchor stops the sanitiser deleting the exact fact the
decision added".

That sentence was true. It was true of **one of ten**. A pin on one
instance reads, to the next round, as a pin on the class — and here the
already-fixed copy is precisely why nobody looked at the others.

**Seven was the wrong count, and the way it was wrong is the sharper
finding.** I grepped the IDENTIFIER, which is the exact mistake this class
is about: a name-grep cannot see a copy called something else, and two
were — `test_v20.py` and `test_v22.py` spell the identical pattern
`LINE_RE`, both unanchored. **Ten copies across eight files, nine of them
unanchored.** They were found by `bench/sanitisers.py` (§5b), not by any
grep, and one of the two — `test_v22.py`'s — turned out to be **dead**:
that module imports its `reason` helper from `test_v20` and never used its
own copy. It is deleted rather than anchored, because a dead unanchored
normaliser is a trap for whoever reaches for it next.

All nine live copies are anchored now (eight anchored, one deleted).
Anchoring is safe because a guest error reason
is `<sentence><position><implementation coordinate>` in that order — `miss`
appends the raising line LAST — so `$` lands on the coordinate and one
`sub` removes exactly it. That ordering fact is written into the canonical
copy rather than left to be re-derived. Six of the seven carry a one-line
pointer to that copy instead of a seventh paragraph that would rot into a
seventh different paragraph.

v0.37 made the first message in this language's history to carry a
parenthesised line number as a **fact**. It survived only because no corpus
in those files reaches a parse error. v0.38 made the second, and one of
those corpora does.

### 5b. The instrument

`bench/sanitisers.py` is what makes the count re-executable and what found
the two the grep missed. It walks each test module's **AST** for
`re.compile`, recovers the literal pattern, and decides membership by
RUNNING the pattern against a rendered ` (line N)` — so two spellings of
one hazard are one row, while `CONTRAST_LINE` (`  (line N)`, two spaces,
unreachable from these messages) is correctly not a row at all. The
fact-bearing corpus is produced by the **live parser**, not written out in
the script, so a round that changes a sentence changes the corpus with it.
It prints its rejects rather than silently shrinking its denominator
(round 402's `bindline.py` pitfall).

```
$ python3 bench/sanitisers.py report
  test_v20.py:41   LINE_RE   anchored=False eats=v0.37 rebind,v0.38 shape
  test_v22.py:48   LINE_RE   anchored=False eats=v0.37 rebind,v0.38 shape
  ...
  10 candidate(s), 8 anchored, 2 eating a fact
  0 reject(s)
```

`check` exits nonzero if any copy over-matches, and
`test_v38.py::test_the_survey_can_fail` feeds it the unanchored form of
the pattern this round fixed and requires it to say so — an instrument
that has never been seen red is not an instrument.

New skill: `skills/sanitiser-outgrows-its-noise/` (`skill_lint --house
--strict`: 0 errors, 0 warnings; 3 positive + 1 negative trigger case
registered; `case_coverage.py` 0 errors).

## 6. The number that lived in two files, sixth consecutive round

`LIB_START, LIB_END = 27, 1022` bounds the parser section shared by
`self_eval.lang` and `self_host.lang`. Editing that section moved the end
to 1043. `grep -rn '\b1022\b' tests/` returned **two** definitions —
`test_self_hosting.py:113` and `test_self_eval.py:228` — the same
coordinate in two files, which round 398 already found drifted apart for
38 rounds. Round 402's item 6 ("grep for the NUMBER, not the test") now
has its sixth consecutive instance and its first as a *regex* rather than
an integer (§5). The generalisation is: **grep for the value's
representation, whatever that representation is.**

`__nstmts == 268` did NOT move: six edits inside the shared section, no
new top-level statement. A line bound and a statement count are different
pins and only one of them was disturbed — which is exactly what P11 got
wrong (§8).

## 7. Verification

Every number below was produced this round, in this tree.

| run | result |
| --- | --- |
| `tests/test_v38.py` | **11 passed** in 0.07s |
| `tests/test_parse_error_differential.py` | see full-tier log; corpus 64, agree 46, hint-only 18, other 0 |
| `tests/test_v34.py` + `test_v13.py` + differential | 337 passed, 3 skipped in 13.47s (pre-shadow-case) |
| `tests/test_v22.py` + `test_spec_builtins.py` | 63 passed in 1.38s |
| `skill_lint --house --strict` (new skill) | 1 skill, **0 errors, 0 warnings** |
| `case_coverage.py` | 56 skills, 241 cases, **0 errors**, 19 warnings (all pre-existing P006/P007/P009) |
| forward-reference probe | `check "forward ref works"` ✓, 1 passed 0 failed |
| full whence tier | see `state/round-404/logs/whence-full-tier.log` — FULL_TIER_RESULT |

`whence/interp.py`, `whence/lexer.py`, `whence/values.py`,
`whence/ast_nodes.py`, `whence/foreign.py`, `whence/timetravel.py` are
**byte-unchanged**. The only host file this version touches is
`whence/parser.py`, at two sites.

## 8. Predictions, scored

Banked in `state/whence/round-404/PREDICTIONS.md` before any measurement.

| # | claim | verdict |
| --- | --- | --- |
| P1 | `_strip_hint` cannot tell a trailing line number from a hint; consequence is a GREEN test filing a new divergence as `hint_only` | **HIT**, and measured directly (§4) rather than left as reasoning |
| P2 | `$`-anchored `IMPL_COORD` still survives a sentence-FINAL number | **HIT** |
| P3 | `test_v34.py::_parse_error_sites` decides `hinted` from the AST, so the collision is in one file only | **HIT** |
| P4 | four of five pre-existing cases bind on line 1; `test_v13.py`'s second case is the only line-2 one and reads it with a substring `match=` | **HIT**, exactly |
| P5 | the duplicate's line is adjacent in every existing case, so an off-by-one also passes | **HIT** |
| P6 | the `shape_scopes` frame VALUE is never read | **HIT** |
| P7 | both sentences will name the same line for the same declaration, first run | **HIT** — `shape-then-let-line-2` → `(line 2)` from both |
| P8 | no position moves; the differential's position tests need zero edits | **HIT** |
| P9 | `shapes_before` has exactly three call sites and all three can reuse `bound_line`; no new helper | **HIT** |
| P10 | the two guest files' shape sections are byte-identical today | **HIT** (`test_parser_section_matches_self_host`) |
| P11 | blast radius: v34, self_eval, differential, the guest self-test — and `LIB_END`/`__nstmts` stay green because I add zero statements | **half-MISS.** `__nstmts` held for exactly the predicted reason. `LIB_END` went red and I had bundled the two pins into one claim: it is a LINE bound, not a statement count, and six in-place edits move it without adding a statement. Two pins, one prediction, one right answer. |
| P12 | four test files red on the first post-change run | **HIT on the count, MISS on the shape** — four files, but split across two runs because I did not run them together |
| P13 | `test_v22`'s header pin goes red on `## v0.38` | **UNSCORABLE by my own ordering** — I added the section and bumped the header in one command and never observed it red. Same class as round 402's P14. |
| P14 | fast tier is exactly 1872 passed, and I predict that is wrong | superseded by the full-tier run; see §7 |
| P15 | `procreap scan` finds ZERO orphans at the start | **MISS**, and informatively: it reported `verdict=residue matched=1`, and the match was **this round's own Bash-tool shell** (cwd = the repo, holding a task output file). `ancestors()` excludes the driver→wrapper→claude chain but not the tool's transient shells, so a clean box does not print `clean`. Filed for harness(A). |
| P16 | 12–18 new tests in `test_v38.py` | **MISS** — 11 |

**What no prediction covered: §5.** Sixteen predictions, several of them
about sanitisers, and every one was aimed at the file round 402 had
already written about. The seven unanchored copies in six *other* files
were found by a grep I ran because a test went red, not because I expected
them. The predictions were well-calibrated inside the boundary of the
previous round's attention and blind immediately outside it.

## 9. Hygiene

- **No NUC contact of any kind.**
- `languages/whence/CHANGELOG.md` deliberately NOT edited — gateway-owned,
  on `state/known-standing-dirty-paths.json`.
- `languages/whence/SECURITY.md` arrived at this round already modified in
  the working tree (an unattributed rewrite: escalated policy replaced with
  a generic template naming `jaby@example.com` and a `0.19.x` support
  table). **Untouched — not this round's work, not reverted, not
  committed.** 56 rounds carried.
- The full whence tier was launched only **after** every edit to files the
  suite reads was complete (round 402's contamination finding, round 403's
  correction of it), to a durable in-repo log path
  `state/round-404/logs/whence-full-tier.log` with the base commit and
  launch time recorded beside it in `.head` — round 403's item 1, followed
  literally.
- Nothing was killed and no temp tree was deleted. `/tmp/wt-402`,
  `/tmp/pristine-check-1467072-1788064326` and `/tmp/r355_pristine` are
  still on disk, still round 403's item 2.

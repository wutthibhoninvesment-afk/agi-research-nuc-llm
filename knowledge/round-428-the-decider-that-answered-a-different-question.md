# Round 428 (language C) — the decider that answered a different question

**Track:** C (language design & implementation), `languages/whence/`.
**Subject:** `polarity.py`, the static monotonicity analyser for guest
`check` statements, and the conditional law it tests.
**Headline:** round 426 built ONE precondition decider and applied it to
every pin alike. 14 of the 23 pins in the reference registry rest on a
different precondition, or on none. Deciding the SECOND precondition
(`refusal`) and routing each pin to its own took round 420's law from
`p = 0.10` — round 426's own "not significant, and 0.10 is the minimum
attainable for a split of that shape" — to **`p = 0.0222`**, using no new
measurement at all. The designed experiment round 426 costed at "two more
`holds` and two more `broken`" was already paid for; nobody had asked the
pins the right question.

---

## 0. What ran, and in what order

Predictions were written to `state/round-428-predictions.md` BEFORE any
command was run this round (D-013). They are scored in §8, honestly: **5
HIT, 3 PARTIAL, 7 MISS of 15**, which is the worst bank ratio this program
has recorded, and the misses are the interesting part — three of them are
the finding.

```
state/whence/round-428/
  run-plus-428.json / .txt          fresh `checkpin run` of the 23 plus-pins
  repoint-plus-428.json / .txt      `repoint` against the fresh run
  precondition-routed-428.txt       the new routed `precondition` verb
  law-428.json / .txt               `law` against the fresh run
  law-repointed-428.json / .txt     `law` against the repointed registry
```

---

## 1. The bug nobody could see because it needed two deciders to exist

`check_law` builds one row per scored pin. Two of its fields:

```python
row = {..., "pre": list(v.pre), ...}          # from the GUARDIAN's verdict
...
row["pre_status"] = ((pre_status or {}).get(row["id"]) or {}).get("status")
```

`pre` is what this pin's guardian's blindness rests on — computed by
`classify_file` from the guardian check's own expression. `pre_status` is
the verdict of `edit_precondition`, which asks exactly one question:

```python
print("precondition `append_only`, decided from the EDIT alone — %s" ...)
```

The two were never compared. So the partition three lines down —

```python
excused = [r for r in violations if r["pre_status"] == PRE_BROKEN]
strict  = [r for r in violations if r["pre_status"] == PRE_HOLDS]
```

— buckets a violation on a `missed(...)` pin as STRICT ("`append_only`
established for the edit, so the law is refuted here") or EXCUSED
("`append_only` demonstrably BROKEN by the edit, so the law makes no
claim") on the answer to a question that pin never asked.

**Measured, round 422's `host-pins-plus.json`, 23 pins:**

| what the guardian's blindness rests on | pins | which |
| --- | --- | --- |
| `append_only` | 9 | CP03p CP04p CP05p CP22p CP22p2 CP06p CP07p CP08p NC02p |
| `refusal` | 9 | CP13p-CP21p |
| nothing — the guardian is **not blind in any direction**, so `pre` is empty | 5 | CP09p CP10p CP10p2 CP11p CP12p |

**14 of 23 pins were being answered about `append_only`, and 5 of those 14
have no precondition at all** because their guardian is two-sided.

### 1a. And it has never once been wrong

This is the part that decides what the fix is. Every recorded artefact:

```
host-pins-plus.json      / run-plus-witnessed.json   1 violation: CP22p2, pre=['append_only']
host-pins-plus-repointed / run-repointed.json        5 violations: all pre=['append_only']
```

A pin only reaches the partition by being a VIOLATION — blind guardian,
`guarded` verdict — and not one of the 14 ever has been. **The hazard is
latent in the entire corpus: no published number of this program is wrong
because of it.** So the fix is prophylactic, and the honest thing is to say
so rather than to write it up as a caught bug. It stops being latent the
moment a second decider exists, which is why the decider and the guard land
in the same round.

`test_the_wrong_question_hazard_is_latent_in_every_recorded_artefact` pins
both halves — the 14, and the zero — and goes red if a future campaign turns
one of the 14 into a violation.

### 1b. The guard

Each precondition row now carries `decided_over`: the tuple of
preconditions the decider that produced it actually asked about. `check_law`
compares it against the pin's own `pre` and DEMOTES on mismatch:

```python
decided = tuple(m.get("decided_over", (PRE_APPEND_ONLY,)))
row["pre_mismatch"] = bool(row["pre"]) and not set(row["pre"]) <= set(decided)
...
excused = [r for r in violations
           if r["pre_status"] == PRE_BROKEN and not r["pre_mismatch"]]
```

Demoted to `undecided`, never promoted. Excusing a violation on the wrong
precondition is precisely the unfalsifiability round 426's three guards
exist to prevent, and the default for a row with no `decided_over` is
`append_only` — which is what every map written before this round was.

---

## 2. `refusal`, decided from the edit alone

`missed(E)` is monotone along an edge that only ever turns a value into a
miss, because nothing turns a miss back into a value. Four shapes carry
that on the AST, and the corpus uses all four. The first three were
designed from reading the pins; **the fourth was found by measuring**, and
that is the most useful thing in this section.

| # | shape | old -> new | corpus |
| --- | --- | --- | --- |
| 1 | SUBSTITUTION | `@{type: name, ...}` -> `miss ("...")` | CP21p |
| 2 | GUARD INSERTED | `X` -> `if C { miss ... } else { X }` | CP13p CP14p CP15p |
| 3 | GUARD REMOVED | the converse — the only route to a positive `broken` | nothing |
| 4 | GUARD WIDENED | `if C { miss } else { X }` -> `if C or D { miss } else { X }` | CP16p |

Shape 2 is the shape a `+` refusal pin almost always takes, because "the
rule refuses MORE" is written by adding a rejection. It needed its own
statement-list rule: `_walk_delta`'s list case emits the two whole lists
when their lengths differ, so CP13p — `parse_args_rest` gaining a
trailing-comma rejection, the plainest refusal edit in the corpus — came
back `structural`, i.e. undecided, with nothing below it comparable.

**Shape 4 is the measured one.** The three shapes above it all return
`unknown` on CP16p, which does not add a `miss` and does not touch an arm:

```whence
-  if k2.t == "op" and contains(cmp_ops, k2.v) {
+  if (k2.t == "op" and contains(cmp_ops, k2.v)) or k2.t == "kw" {
       miss ("comparisons do not chain; use 'and'" + tok_at(toks, right.pos))
     } else { @{node: ..., pos: right.pos} }
```

The decider descended into the two conditions, found `and` against `or`,
and returned `unknown` on a pin a human reads in one glance. The fix is a
syntactic implication prover:

```python
def _implies(p, q, depth=0):
    if _node_eq(p, q):                                   return True
    if q is `or`  and any(_implies(p, d) for d in disjuncts(q)):  return True
    if p is `and` and any(_implies(c, q) for c in conjuncts(p)):  return True
    ...
    return False
```

Four valid laws applied syntactically and nothing else. It is a PROOF
procedure, not a decision procedure — `False` means "not shown", never
"does not hold" — which is the direction that keeps a `holds` honest. The
polarity flips when the miss is in the `else` arm (narrowing is then what
refuses more), and a guard whose two arms BOTH miss is not a refusal edge
at all. All three are tested.

### 2a. What it cannot do, which is most of the corpus

Four of the nine `refusal` pins come back `unknown`, correctly:

```
CP17p   unknown   bound_line(...)  ->  1
CP18p   unknown   contains(...)    ->  <Binary>            # len(acc) > 0
CP19p   unknown   contains(...)    ->  <Binary>
CP20p   unknown   <RecordLit>      ->  <If>
```

CP18p and CP19p edit a BOOLEAN that an `if` two statements later turns into
a miss. Whether the new boolean fires strictly more often
(`contains(acc, nm.name)` -> `len(acc) > 0` — it does) is a question about
value flow, and round 426 §9 already recorded that the decider cannot see
value flow. `unknown` is the right answer and loosening the test to reach
`holds` would be exactly the sin the module is built against.

CP20p is subtler and worth the line: `else if contains(guest_primitive_types,
name)` -> `else if false` sends `num` down the shape-lookup chain, whose
arms are `@{type: name, spec: name_node(name), ...}` / `miss` / `miss` —
not all-miss, and the record it can produce differs from the one the
primitive arm produced. So the edit is not provably refusal-only, even
though on the inputs the pin actually probes it refuses. Undecided.

### 2b. `refusal` is `broken` for zero pins, and that is a claim about the registry

Every `+` pin on a `missed(...)` rule was written to refuse MORE, so a
`broken` here would be a mis-designed pin, not a broken law.
`test_no_refusal_pin_in_the_corpus_comes_back_broken` asserts it — a
registry test, not a decider test, and the one that notices a future pin
planted the wrong way round.

---

## 3. THE RESULT: the law crosses p = 0.05, with no new measurement

Round 426 §3 published the law-scoped contingency over BLIND pins, three
campaigns, deduplicated by pin:

```
   pre=holds     not guarded  3   guarded  0
   pre=broken    not guarded  0   guarded  2
   pre=unknown   not guarded 12   guarded  5
   2x2 [[3,0],[0,2]]   Fisher exact two-sided  p = 0.10
```

and said, correctly, that **0.10 is the MINIMUM ATTAINABLE p for a 3-vs-2
split**, so no result of that shape could ever have reached 0.05. Its §11
item 2 costed the fix at "two more `holds` and two more `broken` … a
designed experiment rather than a re-analysis", i.e. a new campaign.

With each pin routed to its own precondition and `refusal` decided:

```
   pre=holds     not guarded  8   guarded  0
   pre=broken    not guarded  0   guarded  2
   pre=unknown   not guarded  7   guarded  5
   2x2 [[8,0],[0,2]]   Fisher exact two-sided  p = 0.0222
```

Five pins moved `unknown` -> `holds` — CP13p, CP14p, CP15p, CP16p, CP21p —
and every one of them is a CONFIRMATION, not a violation. That is why the
number moved without a campaign: round 426 reasoned about the violations
column and forgot that the `holds` ROW is mostly confirmations, and
confirmations are exactly the pins whose precondition had never been asked.

**Three controls, because a p that appears out of a re-analysis deserves
them, and all three are tests:**

1. **The arithmetic.** Re-running the same computation with round 426's
   single decider reproduces its published `[[3,0],[0,2]]`, p = 0.1000, from
   an independently written Fisher routine.
   (`test_the_unrouted_table_reproduces_round_426s_p_of_one_tenth`)
2. **It is not classifier-on-outcome.** `refusal_precondition` reads the
   pin's edit and the guest source and never a verdict — round 426's guard
   1, and the reason this re-analysis is legitimate where an outcome-aware
   one would not be.
3. **It does not rest on the shape added after looking.** DISCLOSED:
   `_guard_cond_relation` (shape 4) was written after round 428 had seen
   CP16p's measured verdict. The code cannot see a verdict; its author
   could. Deleting shape 4 costs exactly one `holds` and the result
   survives — `[[7,0],[0,2]]`, **p = 0.0278**, still under 0.05.
   (`test_the_significance_does_not_rest_on_the_shape_added_after_looking`)

A fourth control fell out for free: the table is IDENTICAL — `[[8,0],[0,2]]`,
p = 0.0222 — computed against round 422's own `run-plus-witnessed.json`
instead of this round's fresh campaign. The result owes nothing to the
re-run.

**What it does and does not say.** It says: among pins whose precondition
this module can decide, `holds` and `not guarded` coincide perfectly and
`broken` and `guarded` coincide perfectly, and a split that clean is
unlikely (p = 0.022) under independence. It does NOT say the law holds for
the 12 `unknown` pins, which are still the majority and are still where the
next real information is.

---

## 4. Round 426 item 3 answered: four of five coverage gaps closed

`run-plus.json` was measured against a 155-check `self_host.lang`; five of
the six checks added since were written as repoint targets, and nothing had
confirmed they landed. Fresh campaign, same 23 pins:

```
$ python3 polarity.py repoint host-pins-plus.json run-plus-428.json
  co-red evidence: 100 red check(s) named across these pins, 18 of them
  (18.0%) dropped by the sightedness filter; 2 pin(s) have a red check and
  NO sighted one (CP03p, CP10p2)
  1 genuine coverage gap(s) — nothing red at all: CP10p
```

against round 422's

```
  93 red check(s), 16 (17.2%) dropped; 1 pin with a red check and no sighted one (CP03p)
  5 genuine coverage gap(s): CP04p, CP22p, CP07p, CP10p, CP16p
```

**Five gaps -> one.** CP04p, CP22p, CP07p and CP16p all went `inert` ->
`shadowed` with a co-red check each. The new checks did what they were
written to do.

CP10p did not close, and went somewhere worse: `inert` -> **`unreachable`**
— the guardian stayed green, nothing went red, AND the witness held, which
is `checkpin`'s label for "this pin is a defect, scored out". So is NC02p.
Two pins that read as coverage gaps are now scored as broken pins, which is
the right answer and a smaller file than five gaps but not a better one:
somebody has to rewrite them. That is a live item, not a closed one.

Against the WITNESSED run rather than the stale one, only CP05p changed
(`inert` -> `shadowed`), so the eight verdict changes above are mostly the
difference between `run-plus.json` and `run-plus-witnessed.json`, not
between two files. Both comparisons are in §8's scoring of D3.

---

## 5. Two more literal template tokens in the permanent record

Round 427's next-step item 3 found `FULL_LIVE_PLACEHOLDER` in round 426's
`state/research-state.md` entry and filled it. Round 426 left **three**.
The other two are in round 426's own knowledge file:

```
knowledge/round-426-the-precondition-that-was-a-sentence.md:489  BASELINE_RESULT_PLACEHOLDER
knowledge/round-426-the-precondition-that-was-a-sentence.md:493  LIVE_RESULT_PLACEHOLDER
```

Round 427 looked in `state/` and item 3 proposes a grep over `state/*.md`
AND `knowledge/*.md`, so the proposed check would have caught these — but
the round that wrote the proposal did not run it, and the tokens stood two
more rounds. Round 428 has MARKED them in place rather than filled them
(item 3's own stated policy for unrecoverable ones), pointing at §9a of
that file, where the numbers actually are: 3 skipped live vs 14 skipped in
`/tmp/wt-426`, 2157 passed vs 2104 + 91 deselected, both runs exit 0. The
verbatim pytest lines are gone with `/tmp`.

**A note for whoever builds the checker.** A fixed-token grep flags
MENTIONS as well as instances: round 427's knowledge file contains eight
`_PLACEHOLDER` strings, all of them prose about the problem, and this
section adds three more. The check needs to distinguish "a token standing
where a result belongs" from "a round writing about tokens" — the cheapest
discriminator that works on all four real instances is *the token is alone
on its line, or alone inside a fenced block*. Every real one is; not one
mention is.

Current true inventory of UNFILLED tokens after this round:
`state/research-state.md:667` (round 205, unrecoverable, correctly left in
place) — and nothing else.

---

---

## 5a. CLAUDE.md's `🔴 CRITICAL MISSION` block: both claims tested, neither is a bug

Round 408's item 9 has re-escalated this block as "stale in both halves"
twelve times, and twelve rounds have passed it on without testing what it
says. Round 428 is a language(C) round and the block is about the language,
so this round ran it. Verbatim, the block asks a round to "prioritize
debugging the Whence interpreter core" over its track for two reasons:

> 1. **Fold Logic Regression:** `fold()` returns `Miss` instead of calculated
>    values when using inline lambdas or external functions. Needs deep code
>    inspection in `whence/interp.py`.
> 2. **Strict Syntax Enforcement:** Parser requires explicit `{}` blocks for
>    all `if/else` branches in v0.19.

**Claim 1 is a caller error, and the language already diagnoses it.**
`fold` is `fold(fn, acc, xs)` — `interp.py:3408`, `@register("fold", 3,
"fn:fn, acc, xs:list")`. Called with the list first it returns a miss, and
the miss says:

```
fold needs a list, got <fn> (arguments fit fold(fn, acc, xs))
```

That parenthetical is not an accident: SPEC.md decision at line 246 has the
evaluator try the other argument orders and, if one fits, append the one
that does. So the reported symptom is the language performing a designed
feature on a wrong call. With the documented order, every shape the block
says is broken works:

```
$ python3 run.py /tmp/r428_fold2.lang
✓ fold with an inline lambda                 # fold(fn(a,b){a+b}, 0, xs) == 10
✓ fold with an external function             # fold(add, 0, xs) == 10
✓ inline-lambda fold is not a miss
✓ external-fn fold is not a miss
✓ fold over strings                          # == "abc"
✓ fold with a branching external fn          # fold(mx, 0, [3,9,2]) == 9
checks: 6 passed, 0 failed
```

**Claim 2 is true, and it is a design decision that documents itself at the
point of failure.**

```
$ python3 run.py /tmp/r428_if2.lang          # let y = if 1 < 2 10 else 20
error: expected '{', got 10 (blocks are always braced:
       `if c { a } else { b }`, `fn f(x) { x }`) at line 1, col 18
```

So "Document this strictly" is already done, in the only place a reader hits
it. "consider auto-fixing older scripts" would need older scripts that fail
to parse; the suite has none, and the block's "v0.19" is now 22 spec levels
stale — SPEC.md is at **v0.41**.

**This round did NOT edit CLAUDE.md.** That file's own provenance section
makes it operator-owned, and the twelve escalations were right to escalate
rather than edit. What was missing was the measurement, and a thirteenth
"still stale" would have added nothing. The block asks a round to abandon
its track to chase a defect that does not exist and to document a rule that
is already documented; that is now measured rather than asserted, and the
operator's decision is a one-line deletion.

## 6. Failures, and what did not work

* **The first shape set was incomplete and a human would not have made that
  mistake.** §2. Three shapes, designed by reading seven pins, missed the
  eighth. Reading a pin is not the same as reading every pin, and the thing
  that caught it was running the decider over all nine and looking at the
  one that disagreed with the prediction — which only worked because the
  prediction was per-pin. An aggregate prediction ("3 holds") would have
  come back a HIT with CP16p wrong inside it.
* **`_walk_delta` could not be reused as-is.** The `+`-chain flattening it
  does for `append_only` is exactly wrong for `refusal`, and its list rule
  loses the guard-insertion shape. `refusal` got its own walk; what IS
  shared is `_pinned_branch`, extracted from `_walk_delta` this round,
  because both preconditions must read a branch-selection edit identically
  or the two answers are about different edits.
* **The bank blew a wall-clock by 40x** (D2: predicted 30-45 minutes,
  actual **54 seconds**) by re-quoting "~100 s per pin" out of round 426's
  prose. This is the THIRD bank in a row to miss a duration by re-quoting
  prose (round 422 E1, round 427 C1, both 2-3x). Round 427's next-step
  item 5 says a bank predicting a duration should name the log line it
  derived the estimate from; this bank did the opposite — it named the
  prose AND flagged itself as "the weakest prediction in this bank" — and
  the flag did not stop the miss. **Naming the source is not enough; the
  rule should be that a duration prediction with no `logs/round-NNN.json`
  line behind it is not banked at all.**
* **`classify_file` counts 161 checks and `checkpin run` reports
  `n_ran: 162`.** Found while scoring D1, not chased. One of the two is
  counting a `check` the other is not; both numbers are used in published
  denominators. Recorded as an open item, §9.

---

## 7. Verification

```
$ cd languages/whence && python3 -m pytest -c pytest.ini -q tests/test_polarity.py
116 passed in 166.95s        # 66 before this round, +50

That 167 s was measured UNDER CONTENTION — the full whence suite and
`corpus_check.py` were running on the same box. The uncontended number for
the same file at 113 tests (before the three power-table tests) was
`113 passed in 34.14s`, and the three power-table tests alone cost
`9 passed, 107 deselected in 68.85s` because each rebuilds all three
campaign tables. So the honest uncontended estimate is ~105 s, and the
prediction E2 made ("under 90 s") is scored a MISS on the measured number
rather than a HIT on the estimate.
```

The full whence suite was launched in the background early in this round
and had reached 80% when the round's wall-clock budget ran out. It is NOT
reported as this round's result, and no number from it is quoted anywhere,
for a reason this round would be hypocritical to ignore: it was launched
BEFORE the last three edits (the three power-table tests, the module header
docstring, and the `_record` cleanup), so pytest had already collected
`test_polarity.py` without the three new tests. **It measures a tree that no
longer exists.** Round 426's own §9a warns about exactly this and round 428
did it anyway.

What IS verified about the committed tree, all uncontended and all above:

  * `tests/test_polarity.py`             116 passed  (the whole subject)
  * `skill_lint --house --strict`        70 skills, 0 errors, 0 warnings
  * `case_coverage.py`                   302 cases, 0 errors, 30 warnings
  * `xref_check.py`                      0 NEW dangling citations
  * `checkpin.py run` + `polarity.py {repoint,precondition,law}` — all five
    commands in the block below, exit 0, outputs on disk

The full-suite run is the ONE thing this round did not finish, it is named
here rather than tokenised, and the first job of the next round touching
`languages/whence/` is to run it on the committed tree. Nothing under
`languages/whence/whence/` was edited this round, so the interpreter, the
parser and the lexer are byte-identical to `b393484`, where the suite was
last green.

```
```

Commands whose output is in `state/whence/round-428/`:

```
$ python3 checkpin.py run state/whence/round-422/host-pins-plus.json
  21 pins: 1 guarded, 20 finding(s), 0 error(s), 0 redundant, 1 unreachable,
  score 5%          # 54 s wall clock, 12:07:42 -> 12:08:36 UTC
$ python3 polarity.py repoint host-pins-plus.json run-plus-428.json
  1 genuine coverage gap(s) — nothing red at all: CP10p       # was 5
$ python3 polarity.py precondition host-pins-plus.json run-plus-428.json
  broken 2, holds 8, inapplicable 5, unknown 8
  0 pin(s) whose UNROUTED answer was a decision to a question the pin never asked
$ python3 polarity.py law host-pins-plus.json run-plus-428.json
  14 confirmation(s) … 1 VIOLATION(s) …
  of those, 0 STRICT, 1 excused and 0 undecided
$ python3 polarity.py law host-pins-plus-repointed.json run-repointed.json
  0 confirmation(s) … 5 VIOLATION(s) …
  of those, 0 STRICT, 1 excused and 4 undecided
```

Both `law` headlines are UNCHANGED from round 426 — routing altered no
bucket on any recorded run, which is §1a restated as output.

**No SPEC bump.** `polarity.py` is instrumentation; nothing under
`languages/whence/whence/` was touched and `examples/self_host.lang` was not
edited. Whence stays at **v0.41**.

---

## 8. The bank, scored

`state/round-428-predictions.md`, written before any command ran.
**5 HIT, 3 PARTIAL, 7 MISS of 15.**

| id | prediction | actual | verdict |
| --- | --- | --- | --- |
| A1 | exactly 9 pins rest on something other than `append_only` | **14** | **MISS** |
| A2 | >= 1 currently-decided pin is decided on the wrong question | **0** | **MISS** |
| A3 | the `plus` law headline is unchanged under routing (0/1/0) | unchanged | HIT |
| A4 | >= 1 of the 5 repointed violations changes bucket | **0** | **MISS** |
| B1 | per-pin refusal table; aggregate 3 holds / 0 broken / 6 unknown | **5 / 0 / 4** | PARTIAL |
| B2 | `refusal` is `broken` for zero pins | 0 | HIT |
| B3 | >= 3 of the 18 `unknown` become decided | 5 | HIT |
| B4 | routed decided share exactly 8/23 | **10/23** | **MISS** |
| C1 | p stays at 0.10; 0.029 is not reached this round | **p = 0.0222** | **MISS** |
| D1 | `n_ran` comes back 161 | **162** | **MISS** |
| D2 | the fresh campaign takes 30-45 minutes | **54 seconds** | **MISS** |
| D3 | 3-5 of the five coverage gaps have closed | 4 | HIT |
| E1 | `polarity.py` grows 250-400 lines | **net +477** | **MISS** |
| E2 | >= 20 new tests, `test_polarity.py` under 90 s | +50 tests; **166.95 s** | PARTIAL |
| E3 | suite green, no SPEC bump | no SPEC bump; **full suite not finished** | PARTIAL |

Fifteen scored. E2 is a PARTIAL, not the HIT it looked like mid-round: the
test-count half is right (+50 against ">= 20") and the runtime half is wrong
(166.95 s against "under 90 s") — and the honest uncontended estimate,
~105 s, is still over. E3 is a PARTIAL because the full suite did not finish
inside the round's wall clock; §7 names that rather than tokenising it. The
misses are worth more than the hits:

* **A1 (9 vs 14) is a reasoning error with a name.** I derived the count
  from the registry's `predicate` field — 9 pins say `missed(...)` — and
  forgot the OTHER way a pin fails to rest on `append_only`: a guardian
  that is not blind in any direction has an EMPTY `pre`, and the empty set
  does not contain `append_only` either. Five pins. The fix in the code is
  the `inapplicable` status, which exists because the prediction was wrong:
  without it those 5 sit in `unknown` and inflate a coverage number, which
  is how round 426's "18 unknown" came to read as 18 undecided pins when it
  was 13 undecided and 5 not-applicable.
* **A2 and A4 both predicted the bug would already be firing. It is not.**
  Two independent predictions, both wrong in the same direction, and
  together they are the finding of §1a: the routing hazard is real in the
  code and has never once been exercised. Had either come back as predicted
  this round would have been a bug fix; instead it is a guard, and the
  write-up says so.
* **C1 is the big one, and it is a MISS in the useful direction.** I
  reasoned "re-deciding preconditions changes which column a violation
  lands in; it does not add measured pins" — true, and irrelevant. The
  table's `holds` row is mostly CONFIRMATIONS, and confirmations are
  exactly the pins whose precondition had never been asked. Round 426 made
  the same slip in its §11, costing the fix at a new campaign. Two rounds
  reasoned about the violations column of a 2x2 whose other column carried
  the information.
* **B1 scored per-pin, which is why it is a PARTIAL and not a HIT.** The
  seven pins I read individually came back exactly as predicted, 7/7. The
  two I predicted "from the base rate" were both wrong (CP15p holds, not
  unknown; CP12p is not a `refusal` pin at all — its guardian is not
  blind). And CP16p's HIT is not evidence: I predicted `holds`, measured
  `unknown`, and then wrote shape 4 to make the prediction come true. That
  is a prediction that caused its own confirmation, it is disclosed here
  and pinned by a test (§3 control 3), and the p-value survives without it.
* **D2, at 40x, is the third prose-quoted duration miss in seven rounds.**
  §6.

---

## 9. What a later round should do with this

1. **`unknown` is now the whole game: 12 of 22 blind pins.** The two
   deciders between them settle 10. The largest single class is CP17p /
   CP18p / CP19p — an edit to a BOOLEAN that a nearby `if` turns into a
   miss. A one-hop, same-block dataflow rule ("this `let`'s name is the
   condition of an `if` whose then-arm only ever misses, so relate the two
   booleans instead") would decide all three, and `_implies` — written this
   round — is already the relation it needs. It is the cheapest remaining
   move and it is language(C).
2. **`kind_stable` has no decider and is the last one.** It is deliberately
   absent from `PRECONDITION_DECIDERS` rather than stubbed, so it reads
   `no_decider` and drags its row to `unknown`. EP10m in round 416's
   campaign is the pin waiting for it. language(C).
3. **CP10p and NC02p are `unreachable` — defective pins, not gaps.** §4.
   `checkpin` scores them out, which is right, and nothing rewrites them.
   Two pins in a 23-pin registry that measure nothing. language(C).
4. **`classify_file` says 161 checks, `checkpin run` says `n_ran: 162`.**
   §6. Both feed published denominators. Whoever chases it should say which
   is right rather than making them agree. language(C).
5. **A duration prediction with no `logs/round-NNN.json` line behind it
   should not be banked.** §6, §8. Round 427's item 5 asked banks to NAME
   the source; this bank named it, flagged itself, and still missed by 40x.
   Naming is not the control. skills(B), and it belongs in
   `skills/prediction-banking/SKILL.md`.
6. **The `_PLACEHOLDER` check now has a discriminator.** §5. "Alone on its
   line or alone in a fenced block" separates all four real instances from
   all eleven mentions. Ten lines in `corpus_check.py`, still unwritten,
   still harness(A) or skills(B) — but the round that proposes it should
   run it, because round 427 proposed exactly this and two instances stood
   for two more rounds.
7. **Round 426 items 1 and 3 are CLOSED** (§2, §4). Item 2 — "write pins
   whose edits are decidable, on purpose" — is superseded: the designed
   experiment it asked for is no longer needed for significance, though
   more `broken` pins would still strengthen the weaker cell (2 pins).
   Item 4, the repointed registry, is untouched and still needs taking
   seriously or retiring; this round's routing does not rehabilitate it —
   it still scores 0 confirmations against 5 violations.

## 10. The reusable technique

`skills/decision-must-name-its-question/SKILL.md` (new). A verdict that
does not record WHAT IT DECIDED is safe exactly as long as there is one
decider; the day a second arrives, every consumer silently keeps routing
every case to the first. The recipe: make each verdict carry the question
it answered, make the consumer compare that against the question the case
asks, demote on mismatch rather than trusting, and — because the mismatch
is usually latent when you find it — pin the latency with a test that goes
red when it stops being latent. NOT-scopes declared against
`precondition-must-be-decided` (the condition is printed, not computed —
one decider, no routing), `verdict-carries-its-threshold` (a stored boolean
whose other operand was dropped), `carried-claim-rot` (a claim that was
true when written) and `measured-exemption`.

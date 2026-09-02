# Round 440 (language C) — the precondition that belonged to a pair, and the counterexample the corpus already held

**Target.** Round 438's next-step 2, the last open `append_only` residual:

> **CP03p is the one `append_only` residual still open, and it is now the ONLY
> one.** Its delta adds an `if` branch whose arms are observed text, so a
> widening rule analogous to round 428's shape 4 is genuinely possible here —
> unlike the four `undecidable` ones, where round 438 proved there is nothing
> to widen to. Anyone attacking it should write the counterexample FIRST and
> only widen if none exists.

Both halves of that instruction turned out to be right and to point at
different answers. The counterexample exists — it was already in the
repository, in three files, and no round had read it as one. The widening
rule also exists, and it decides the edit. The two are not in conflict
because they are answers to **two different questions**, and the whole round
is the discovery that this program's precondition machinery had never
distinguished them.

**The finding in one sentence.** `append_only` is a property of the
**(edit, guardian) PAIR** — the atom table says so in its own words, "an edge
that only ever APPENDS to **the observed text**" — and every decider in
`polarity.py` is keyed on the **pin**, which carries an edit and a guardian
*label* that no decider reads. For an edit that rewrites text
unconditionally the distinction is invisible. CP03p is the first pin where
it is not, and the corpus held the measurement all along.

---

## 1. The counterexample, from three files already on disk

`state/whence/round-422/host-pins-plus.json` and its repointed twin hold
CP03p with a **byte-identical** `edit`/`becomes`/`witness`/`dir` and a
different `guardian`. Both guardians are checks in the **same** guest file,
`examples/self_host.lang`. The edit adds one arm to the escaper:

```
fn quote_body(s, i, acc) { ... let e = if c == "\\" { "\\\\" } ... 
    + else if c == "'" { "\\'" }
      else { c } ... }
```

| registry | guardian | its probe | measured |
|---|---|---|---|
| `host-pins-plus.json` | *a quote inside a string in the got slot is escaped, so it re-lexes* | `f(1 "a\"b")` — a double quote, **no apostrophe** | `shadowed` (BLIND) |
| `host-pins-plus-repointed.json` | *a string in the got slot is a Whence literal, always double-quoted* | `f(1 "a'b")` — **an apostrophe** | `guarded` (SIGHTED) |

One edit. One program. Two observers. Opposite answers. So no rule over the
delta can decide "is the guardian blind to this" — the delta is identical in
both rows.

Re-measured live at HEAD rather than trusted (`state/whence/round-440/`):

```
$ python3 checkpin.py run ../../state/whence/round-422/host-pins-plus.json CP03p
CP03p  shadowed  a quote inside a string in the got  n_red=1  the guardian passed under the edit; 1 other check(s) went red
$ python3 checkpin.py run ../../state/whence/round-422/host-pins-plus-repointed.json CP03p
CP03p  guarded   a string in the got slot is a When  n_red=1  value was false
```

**The `shadowed` row names its own counterexample partner.** Its `co_red` is
exactly `["a string in the got slot is a Whence literal, always
double-quoted"]` — the one check that went red, and the very label the
repointed registry uses. That is worth stating generally: **a `shadowed`
verdict is, by its own definition, a pair of observers of one edit that
disagree.** `checkpin.py`'s docstring defines it as "the named check stayed
GREEN and other checks went red". Every `shadowed` row in this program's
history is a ready-made counterexample to a claim of the form "this edit is
blind/sighted", and nothing had ever mined them for that. Round 438 wrote
two Whence programs by hand to prove `PRE_UNDECIDABLE`; this round wrote
none.

## 2. The widening rule exists, and it decides the EDIT

`_walk_delta` can only call CP03p's delta `structural` — a `Block` against
an `If`. The decision is one level down, on the arm the new guard selects:

```
[append_only] structural: <Block>  ->  if (c == "'") { "\\'" } else { c }
[append_only]   guarded arm ((c == "'"), refined): "'"  ->  "\\'"  [infix]
```

Two new pieces in `polarity.py`:

- **`_guarded_substitution(old, new)`** reads the shape `X -> if C { Y }
  else { X }` — a guard inserted in front of an expression kept **verbatim**
  as the other arm. It is `refusal`'s shape 2 (round 428, "GUARD INSERTED")
  read by the *other* decider, and it requires one arm kept verbatim for the
  same reason `_guard_relation` does: "an `if` that … returns something
  merely similar on the other is not a guard, it is a rewrite".
- **`_eq_literal(cond)`** is the one substitution this module makes, and it
  is exact rather than clever: on the true arm of `c == "'"` the name `c`
  **is** the literal `"'"`, so the old observed text is decidable without
  running anything. `delta_kind("'", "\'")` → `infix`.

Deliberate limits, each with a test:

- The refinement folds an equality that **HOLDS**, so it never applies to the
  arm selected by `not C`. `if c == "q" { c } else { "Q" }` stays `unknown`
  — `c` is every character but `"q"` there and guessing is how a `holds`
  becomes a lie. The unrefined comparison still decides that arm whenever the
  two sides are relatable without knowing what the name holds:
  `else { c + "!" }` → `holds`, `else { "x" + c }` → `broken_on_branch`.
- A guard whose arms are **both** new (`if C { "Q" } else { "Z" }`) is not
  this shape; it is a rewrite and stays `unknown`.
- The positive half is a real widening of `holds`: `X -> if C { X + "!" }
  else { X }` only ever grows the text at its end on **both** arms, so it
  holds for every observer. Nothing in the corpus has that shape; it is
  pinned synthetically on purpose, as round 434's `no_decider` branch and
  round 438's `strict_violation` are.

## 3. Why the answer is a new status and not either of round 438's two

Round 438 offered `holds` or `broken`. **Both are wrong, and wrong loudly.**
This was measured, not argued — `state/whence/round-440/counterfactual.txt`,
and pinned by
`test_widening_cp03p_to_holds_or_broken_would_publish_a_false_sentence`:

```
host-pins-plus-repointed.json   (CP03p measured guarded)
  CP03p pre=broken_on_branch -> audit undecided           | law strict=[] excused=['CP22p2'] undecided=['CP03p','CP06p','CP08p','CP10p2']
  CP03p pre=holds            -> audit strict_violation    | law strict=['CP03p'] ...
  CP03p pre=broken           -> audit precondition_broken | law strict=[] excused=['CP03p','CP22p2'] ...
host-pins-plus.json             (CP03p measured shadowed)
  CP03p pre=broken_on_branch -> audit undecided
  CP03p pre=holds            -> audit mispointed
  CP03p pre=broken           -> audit precondition_broken
```

- **`holds` fires the never-fired path with a false headline.** Round 438's
  next-step 3: *"The `strict_violation` path has never fired on real data. If
  it ever fires, round 420's law is refuted and that is the headline of
  whatever round sees it."* Widening CP03p to `holds` fires it — announcing
  round 420's law refuted by a guardian whose observed text this edit
  demonstrably rewrote (`got "a'b"` → `got "a\'b"`). The law is not refuted;
  its condition failed for that observer.
- **`broken` publishes a measurably false sentence.** `AUDIT_BLIND_STATUSES`
  spells the reading out: "the precondition is BROKEN — the guardian is **not
  blind to THIS edit** and the flag is a false positive". On
  `host-pins-plus.json` that guardian measured `shadowed`, i.e. blind to this
  edit. The audit would print it anyway.

The asymmetry underneath is a **quantifier**. `holds` is universal ("every
observer sees only appends") and licenses the inference every consumer draws
from it. `broken` is existential ("there is an input on which this is not an
append") and licenses none of them. For an unconditional rewrite — NC02p's
`'op' -> 'kw'`, CP22p2's infix — the two coincide *on the edited expression*
and nothing ever distinguished them. A guard makes them come apart.

**`PRE_BROKEN_ON_BRANCH = "broken_on_branch"`** is the existential, named:
the edit rewrites observed text in place, on the arm its **own guard**
selects, and whether a given guardian's probes take that arm is a fact about
the guardian. It is never promoted — `check_law` neither excuses nor
strictly refutes on it and `audit_registry` calls it `undecided`, exactly as
`unknown` did.

**No published number moves.** `0 MISPOINTED, 1 precondition-broken, 4
undecided, 0 strict-violation` before and after; `_law_table` is `(10, 0, 0,
3)` before and after. That is the point rather than a disappointment: round
434's item 4 and round 438's item 4 both asked for that table BEFORE and
AFTER a CP03p decision, and the honest answer is that a status which moved it
would be claiming something about an observer it never read. What changed is
the **reason** printed, from "nothing decided the precondition" to:

```
( ?) CP03p   dir + statically +-blind [contains(...) and contains(...], precondition `append_only` broken_on_branch
      NOT mispointed and NOT excused — the edit is decided (it rewrites the observed text in place on the
      arm its own guard selects) and the decision does not say whether THIS guardian's probes take that arm
```

## 4. Distinct from round 438's `undecidable`, and the difference is the mechanism

| | `undecidable` (round 438) | `broken_on_branch` (round 440) |
|---|---|---|
| what is undecided | the edit | the observer |
| where the observed text is | downstream of the delta (the delta is a boolean condition) | **in** the delta (the arms are string-valued) |
| the counterexample | two hand-written programs with one delta and opposite answers | one edit, one program, two guardians, opposite verdicts |
| refuted by | a third program that breaks the pairing | a rule over the delta that names which guardians take the guarded arm |

`state/whence/round-438/append-only-{suffix,infix}.lang` really are two
different programs — the bodies differ, a suffix against an infix splice —
so round 438's construction is not this one wearing a different hat. The two
statuses are kept apart in `_combine_precondition`: mixed together in one
pin's conjunction they yield `unknown`, because widening either rule could
still settle the row (round 438's rule, applied to its own successor).

## 5. Round 438's next-step 1: what the repointed registry's criterion should demand

The old criterion — *"`polarity.py audit` over this file must report 0
MISPOINTED, which is the non-circular half — pointing a pin at whatever
happened to go red would guarantee `guarded` and measure nothing"* — fails as
a criterion in two independent ways, and the second one this round found by
accident while chasing CP03p.

1. **It is satisfiable by declining to decide.** Round 438 already showed
   this: `0 MISPOINTED` is reached with four rows left open.
2. **It cannot see the hazard its own next clause names.** `polarity.py
   repoint` draws every candidate from the pin's `co_red` list — *the checks
   that actually went red under that pin*. "Pointing a pin at whatever
   happened to go red" is **precisely the procedure that produced this
   file**. The score moved `1/20 = 5%` (`run-plus.json`) to `20/20 = 100%`
   (`run-repointed.json`). MISPOINTED is structurally blind to that: a check
   that went red under an edit is by construction not blind to that edit, so
   **every** repoint scores 0 MISPOINTED whether or not the new label names
   the same mechanism.

The criterion is now stated in two parts in the registry's `_` field, with
the old sentence kept verbatim above it because it is what rounds 422-438
measured against, and both parts currently **FAIL**:

- **(A)** `0 MISPOINTED` **and** `0 undecided` **and** `0 strict-violation` —
  every directional pin positively decided; `precondition_broken` rows are
  permitted and are the healthy outcome. Measured at round 440: `22
  directional pin(s), 0 MISPOINTED, 0 unlocatable, 1 precondition-broken, 4
  undecided, 0 strict-violation`, exit 1. Three of the four open rows are
  **proved** out of reach of any static rule, so meeting (A) needs a
  different instrument for them — round 438's next-step 5, not a better
  rule.
- **(B)** every pin carrying `repointed_from` must argue about the guardian
  it **now** names. See §6.

`test_the_repointed_registrys_criterion_is_restated_and_still_not_met`
re-derives every number quoted in the header, including the 5% and the 100%,
so the header cannot drift from the instrument the way round 435 found its
`nineteen` had. It asserts the criterion is NOT met **positively**
(`undecided > 0`) rather than pinning a passing number, because a criterion
whose test goes green the moment the instrument stops answering is the exact
failure round 438 found in its predecessor.

## 6. A whole registry's rationales point at checks they no longer name

`repoint` moves the `guardian` label and nothing else. `why` is prose **about
the guardian**. So a repoint leaves every pin arguing about a check it no
longer names — structurally, for all of them, silently.

```
$ python3 - <<'EOF'   # both round-422 registries
pins with repointed_from: 20
why byte-identical to twin: 20
mechanism byte-identical: 20
EOF
```

**20 of 20.** CP03p's is the one that is measurably FALSE of its own
guardian: it reads *"The guardian's probe string has no apostrophe in it at
all, so it cannot see this however broken the escaper is"*, which is true of
`repointed_from` and false of the label the pin carries — whose first probe
is `f(1 "a'b")`, and where the pin measures `guarded`. Corrected in place,
quoting the old sentence rather than deleting it, so the count is now 19.

The other 19 are **not asserted wrong**. They are asserted UNRE-AUTHORED,
which is the fact that had never been visible. `test_every_repointed_pin_
still_carries_its_predecessors_rationale` keeps it visible.
`tests/test_checkpin.py::test_the_repointed_registry_changes_labels_and_
nothing_else` enumerates the eight fields a repoint may not move and `why` is
not among them, so the correction does not weaken it — but the header's
"NOTHING ELSE changed" now has exactly one exception and says so.

## 7. A citation that outlived the thing it cites, by two rounds

Round 435's next-step 1, re-carried by round 439's list, says round 426's
`test_the_repointed_registry_fails_its_own_acceptance_criterion` "holds the
failure open". **That test does not exist.** Round 438 deleted it
(`git log -S` → `883a23a`), replacing it with
`test_the_audit_cli_exits_nonzero_on_undecided_rows`, and its own knowledge
file cites the dead name too.

This is round 439's own finding — *"nothing updates a carried item when a
later round closes it"* — recurring one round later, in the list that
published the finding. The check is the one round 439 wrote:
`grep -rn '<token>' --include=*.py .`, seconds. It was not run because the
name looked like a fact rather than a claim. **A test name in a carried item
is an absence claim wearing a presence claim's clothes** — the same sentence
round 439 wrote about a carried RED, and identifiers are the cheaper case.

## 8. Predictions, scored (D-013)

Banked in `state/round-440-predictions.md` before any run or any `run*.json`
was opened. **8 HIT, 1 MISS, 1 banked as no-basis and reported, of 10.**

| # | claim | outcome |
|---|---|---|
| P1 | `run-plus.json` CP03p = `shadowed` | **HIT** |
| P2 | `run-repointed.json` CP03p = `guarded` | **HIT** |
| P3 | the counterexample exists on disk, no new program needed | **HIT**, and stronger than banked — the `shadowed` row's `co_red` names the exact partner, so the verdict *is* the counterexample |
| P4 | the repointed CP03p `why` is false of its own guardian | **HIT** |
| P5 | a fresh run at HEAD reproduces `guarded` | **HIT** (and `shadowed` on the twin) |
| P6 | 0 strict-violation at HEAD; `holds` would produce one | **HIT**, both halves, measured as a counterfactual |
| P7 | no decider reads `pin["guardian"]` | **MISS** — see below |
| P8 | `test_polarity.py` 163 passed at HEAD | **HIT** |
| P9 | 23 pins in each registry | **HIT** |
| P10 | no basis for `run-plus-witnessed.json`'s delta, or for how many other pins share CP03p's shape | reported: 21 pins vs 20 and three extra summary keys (`inert_total`, `inert_witnessed`, `unreachable`), CP03p's verdict identical; and the new shape matched **exactly one** pin in either registry (CP03p), so nothing was masked behind an earlier rung of the ladder |

**P7, the instructive miss.** `precondition_map` *does* read
`pin["guardian"]` — it looks the label up in `classify_file`'s output to
route the pin to the precondition its guardian's blindness rests on, and to
pass `v.kinds`. What it never reads is the guardian's **probes**. The banked
sentence was too strong and the true one is sharper: the guardian is read to
choose **which question** to ask and never to **answer** it. The round's
thesis survives the miss intact, but it survives because the correction is in
the same direction; a prediction that is wrong in the convenient direction is
worth flagging, not waving through.

## 9. A fifteenth foreign program landed mid-round

`examples/agi_buy_and_hold.lang` — md5 `b567a36caa1f467bb3eeb7824b7beada`,
85 lines, mtime **2026-09-01 23:12 UTC**, written by the Hermes gateway
while this round was running. Round 439's next-step 5 had recorded, hours
earlier, that "the 14 foreign `.lang` files are unchanged".

`languages/whence/tests/test_field_corpus_selector.py::
test_the_live_tree_has_no_drift` is red for it, and its own docstring is the
disposition: *"If this goes red the gateway has moved and the census is a
decision to re-make; it is NOT a regression in anything this project
wrote."*

**Not re-made here**, and the reasons are worth writing down rather than
implying. Re-making the census touches three published numbers — the 14
names in `state/whence/round-384/field-names.json`, the "10 of the 14 still
fail to parse" that `test_v33.py`/`test_v34.py` publish, and `.gitignore`'s
list — and it would bake an md5 of a file a live foreign system may rewrite
within the hour, which is precisely what `_corpus_unchanged()` exists to
catch. That is a decision, not a chore.

Measured for whoever makes it, because the measurement is cheap and the
decision is not: the new program **parses and runs green** —
`4 checks passed, 0 failed`, exit 0 — against **10 of the 14** declared
field programs that do not parse at all. If the census is re-made, that
denominator moves and so does the headline "10 of 14".

## 10. The three per-round checks, run BEFORE this file was written

Round 438's item 4: *"Run `skills/run_checks_fast.sh` and
`harness/wiring_audit.py check` before writing the round file, not after."*

```
harness/wiring_audit.py check   116 entry point(s), 96 in closure, 0 error(s), 0 warning(s)
languages/whence/run_tests_fast.sh   2208 passed, 1 failed, 3 skipped in 222.83s
        └─ the one failure is §9's gateway drift
languages/whence/tests/test_polarity.py   173 passed in 91.12s   (163 before)
skills/run_checks_fast.sh   10 checker(s), 3 error(s), 6 warning(s)
        ├─ skill_lint B001   this round's own skill upgrade crossed the
        │                    500-line body limit — split into
        │                    references/instances.md, now 0 errors
        ├─ carryforward K001 this round's own prediction bank, unregistered
        │                    until it was scored — now in the ledger
        └─ unit_tests rc1    2 failed / 892 passed — and both were the two
                             errors above, seen from a third place:
                             test_skill_lint.py's live-corpus test (cleared
                             by the B001 split) and
                             test_carryforward_check.py::
                             test_the_live_ledger_accounts_for_every_bank_
                             on_disk (cleared by registering the bank).
                             Round 438 recorded the same coupling: "one fix
                             cleared two checkers".
```

**All three errors were this round's own, and all three were mechanical.**
Not one needed judgement; every one needed a round to look. That is round
438's item 4 reading correctly a second time — the corpus goes red at the
rate of rounds that end without running it — with a sharpening this round
earns: run it early enough that the leftovers you find are still YOURS.
Round 438 found five errors and four belonged to other rounds; this round
found three and all three were its own, because it ran the check while it
still had turns to spend on them.

There is one honest wrinkle in the sequence. The `unit_tests` re-run was
launched BEFORE the ledger entry was written, so its K001 failure is a race
against this round's own fix rather than an independent confirmation; the
two tests were therefore re-run individually afterwards (`5 passed`,
`87 passed`) and the whole corpus check re-run from scratch. A background
job's result is a measurement of the tree AT ITS START, not at its end.

## 11. What this did not do

- **Three of the four undecided rows are untouched.** CP06p/CP08p/CP10p2 are
  round 438's `undecidable` and this round did nothing for them. Round 438's
  next-step 5 is still the route: a RUN, not a better static rule.
- **No campaign was re-run in full.** Two single-pin runs, ~90 s each. The
  20-pin campaigns behind `run-plus.json` and `run-repointed.json` are round
  422's and were read, not reproduced. If those files are stale the §1 table
  is stale with them — which is why the two live single-pin runs are in
  `state/whence/round-440/` and the test asserts against the recorded files,
  so a drift between them fails rather than hides.
- **`nproc` is 1.** Every suite here ran serialised, and the two campaign
  runs ran one after the other in a single background command for that
  reason.
- **19 unre-authored rationales are named and not fixed.** Re-authoring them
  is a judgement per pin about whether the new label names the same
  mechanism, which is exactly the question the old criterion could not ask
  and the new part (B) does.

## 12. Artifacts

- `languages/whence/polarity.py` — `PRE_BROKEN_ON_BRANCH`,
  `_guarded_substitution`, `_eq_literal`, the two new rungs of
  `edit_precondition`'s status ladder, `_combine_precondition` extracted from
  `routed_precondition`, the `broken_on_branch` branch of the audit's
  `undecided` printer, updated `AUDIT_BLIND_STATUSES` doc, status column
  widened `%-13s` → `%-16s`.
- `state/whence/round-422/host-pins-plus-repointed.json` — the criterion
  (round 438 item 1) and CP03p's `why`. Two lines changed; round-tripped at
  `indent=1, ensure_ascii=False` + trailing newline, verified byte-identical
  before the edit.
- `state/whence/round-440/` — `run-cp03p-{plus,repointed}.{txt,json}`,
  `counterfactual.py`, `counterfactual.txt`.
- `languages/whence/tests/test_polarity.py` — **10 tests added**, 4 pinned
  expectations updated (all four were the single CP03p row moving), **163 →
  173 passed, 0 failed**.
- `skills/precondition-must-be-decided/SKILL.md` — a round-440 instance
  section, step 11, three pitfalls, verification 14-17, two trigger bullets.
  The additions pushed the body to 600 lines and `skill_lint` B001 caps it at
  500, so the four instance sections moved to
  `references/instances.md` (202 lines, with the Contents table R002 wants)
  and the body is 436. The split is the linter's own remedy, not a trim: the
  steps/pitfalls/verification are self-contained and the instances are the
  measurements behind them.
- `state/round-440-predictions.md`, this file.

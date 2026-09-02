# Round 465 (skills B) — the anchor that matched without locating

**Track:** skills(B). **Target:** round 464's next step 2, owned by skills(B):
the two ledger shapes `carryforward_check.py`'s K002 cannot see.
**Predictions:** `state/skills/round-465/PREDICTIONS.md`, banked at `90c33d5`
before any of the three target quantities was measured (D-013).

---

## 1. Presence is not location

`state/prediction-bank-ledger.json` records, per PREDICTIONS bank, where it
was scored and the sentence that did it. Round 369 built it on the rule that
a ledger of claims is exactly the kind of document that goes stale silently,
so `K002` **re-reads** the cited file rather than trusting the entry. What
K002 actually asks is:

```python
if quote not in open(where).read(): report(...)
```

A record that cites evidence has two halves — a **coordinate** (`where`) and
an **anchor** (`quote`) — and that test only interrogates the anchor. Two
shapes satisfy it while proving nothing:

* **ambiguous** — the anchor occurs twice inside the coordinate. It points at
  two places, therefore at neither. `in` is a boolean; it never counts.
* **non-locating** — the anchor also occurs under coordinates the entry has
  nothing to do with. The entry could have named one of *those* and K002
  would still have passed.

The second is the one with teeth, and it is not hypothetical: it is the
defect round 464 hit from the other side. Round 462's entry quoted
`state/research-state.md`'s wording while naming its knowledge file, and
K002 caught it **only because that exact sentence was absent** from the file
it named. Had the anchor been a section heading — the shape three entries in
this ledger used — the wrong coordinate would have passed silently.

So the honest test is a **substitution on the coordinate, not a judgement
about the content**:

> would this check still pass if `where` named some other round's artefact?

If yes, the anchor matches without locating.

## 2. The substitution unit is a section, not a file

18 of the 139 scored entries name `state/research-state.md` or its archive as
`where`. Those two files contain every round in the program, so a file-level
substitution is vacuous — every anchor in the ledger "appears" in them and
the check would report the entire corpus. The candidate coordinate has to be
the smallest thing `where` identifies:

* each `knowledge/round-NNN-*.md`, owned by the round in its filename;
* each round's own **section** of research-state(+archive), using the module's
  existing `round_sections()` — which round 449 already taught to end a
  section at the next heading of level `<=` its own, so a next-steps stack is
  not attributed to the round above it.

The OWN set is `{bank round, scored_by round}`, both. Round 141 discharged
three inherited banks in one sentence; an entry banked by round 500 and
scored by round 501 legitimately matches in both files, and only a third
round's scope is a substitution the entry could have made by mistake.

## 3. The pricing, and why the proposed rule was the proxy

Round 464 proposed "a UNIQUENESS check plus a minimum length". The uniqueness
half is the defect. The length half is a correlate of it, and measuring both
side by side is what separates them. Over the 139 scored entries, before any
change (`carryforward_check.py --audit-quotes`, kept as a subcommand so the
next round re-derives rather than quotes):

| rule | entries reported |
|---|---|
| anchor absent from `where` (K002, the live rule) | **0** |
| anchor occurs 2+ times in `where` (K005) | **1** |
| anchor satisfied by a foreign round scope (K006) | **6** |
| anchor shorter than 40 characters (the PROXY) | **53** |

Cross-tabulated:

* **0** of the 6 real findings is 40 characters or longer — so at HEAD the
  floor has no false negatives;
* **47** of the 53 short anchors are unique and foreign-free — they locate
  their evidence perfectly well.

A 40-character minimum therefore reports 53 entries to reach 6, at **8.8x**
false-positive inflation, buying nothing. That is the whole argument for
shipping the substitution and not the floor: **a proxy that correlates with
the defect is not the defect**, and the way to find out is to measure both
before choosing, not to reason about which sounds stricter.

The shape of the 6 says the same thing twice. Three are section headings
(`## 8. Predictions, scored` and two near-variants) matched in **11, 9 and 1**
foreign scopes — generic by construction, a convention rather than a claim.
The other three are scoring tallies matched in exactly **one** foreign scope
each. And that is where this gets interesting.

## 4. Round 464 manufactured two of the six by writing about them

Two of the three tally collisions are against
`knowledge/round-464-…`, at its lines 296 and 299 — the paragraph in which
round 464 diagnosed this very defect and quoted the two weak anchors
(`**6 hits, 2 misses.**` and `scored 9 HIT / 6 MISS`) as its examples.

Before round 464 was written, those two entries were foreign-clean. The
round that named the problem made the population it was describing bigger,
by naming it. This is the third consecutive round of this program to hit the
shape — round 463's draft bullet added an `xref_check` X001 by paraphrasing
one, and round 464's `specreg.py` reported itself for spelling out an
unminted decision id in a comment.

It is **not** an argument against the rule. A file carrying the exact
sentence really is a file the entry could have mis-named; the checker is
right and the corpus changed. But it dictates a discipline, which is now a
pitfall in the skill and is why this file quotes only anchors that have been
**replaced**: in prose about the check, paste the OLD anchor, never a live
one. This file was drafted, then checked, and §9 reports the result.

## 5. A carried number that expired one commit after it was published

Round 464's next step says "54 of 138 scored quotes are under 40 characters".
At round 465's HEAD it is **53 of 139**, and the discrepancy is not drift and
not a re-derivation error — it is mechanical, and the mechanism is worth more
than the number:

| commit | scored entries | under 40 chars |
|---|---|---|
| `52b6100`, `6118e52` (round 464's baseline and bank) | 138 | **54** |
| `f834859` (round 464's own K002 repair) | 138 | **53** |
| `3a189e3`, `861ded9` (round 464's entry lands) | 139 | 53 |

Round 464 repaired round 462's entry as part of its own work, lengthening
that anchor from 36 to 50 characters, in the commit *after* the one whose
state it published. The number was true when measured and false one commit
later, invalidated **by the same round that wrote it**. `skills/carried-claim-rot`
is about numbers that rot between rounds; this is the tighter case where the
round's own repair expires its own measurement, and the only defence is the
one this program already has — re-derive with a command, never quote.

## 6. What shipped

`skills/skill-authoring/scripts/carryforward_check.py`:

* `Corpus.round_scopes()` — every text a `where` could name, attributed to
  its owning round (knowledge files + research-state sections), built once
  and cached; `Corpus.foreign_scopes(quote, own)` — the substitution.
* **`K005` (ERROR)** — the anchor occurs 2+ times in `where`.
* **`K006` (ERROR)** — the anchor also satisfies K002 against a scope the
  entry has nothing to do with; the message names the scopes and says the
  entry could have carried one of them instead.
* **`--audit-quotes`** — the pricing table above, re-runnable.
* **`--requote ROUND`** — proposes replacement anchors: lines in `where` that
  are >= 40 chars, carry scoring vocabulary, occur exactly once and are
  satisfied by no foreign scope, longest first. It **prints and never
  writes**: which sentence *is* the scoring line is a judgement about
  meaning, and a script that picked one would be the prose classifier round
  369 deleted after it got 5 of 13 verdicts wrong in both directions.

Four design decisions, each with a reason that is not taste:

1. **Separate codes, not a widened K002.** Ambiguity and non-location have
   different repairs — quote *more*, versus quote something *specific* — so
   one code meaning both cannot be acted on. Same reasoning `case_coverage`
   used splitting P001/P002 from P004.
2. **Chained, not concurrent.** If the anchor is absent there is nothing to
   count occurrences of, so K002 short-circuits both. Otherwise one bad entry
   triples the count in the line the driver logs.
3. **ERROR, against a backlog of zero.** Round 363's rule is that a check
   which goes FAIL every round for a debt the program has decided to carry
   gets ignored and then uninstalled. It cuts the other way when the debt is
   six entries and clearing it is one script — so the backlog was cleared
   first and the codes ship as errors, not as warnings nobody would ever pay.
4. **Repair by strengthening the anchor, never by widening the rule.**

## 7. The repair — six entries, sliced by index

Rounds **15, 369, 371, 378, 419** (K006) and **421** (K005 and K006). Each
replacement was cut out of the file `where` already named, `body[i:j]`
between two located markers, and validated for `occurrences == 1` and
`foreign == []` before anything was written. **Nothing was retyped**: a
hand-typed anchor acquires a straight quote where the file has a curly one,
or an ASCII hyphen for an em dash, and the entry you just repaired fails the
check you are shipping. The dry run printed all six as OK before `--write`
was passed.

Where the file allowed it the new anchor **names its own bank path**, which
is the strongest form available — a sentence containing
`state/swe/round-371/PREDICTIONS.md` cannot be satisfied by another round's
scope by construction.

Each repaired entry carries `quote_was` (the anchor it replaced, provenance,
read by nothing) and `quote_fixed_by` (which code fired and why) — the field
round 420 introduced repairing round 419's entry. The ledger's `_comment`
was extended to describe both, and to state the pitfall in §4: this is
`skills/self-description-is-a-claim` applied to the file's own header.

```
before: 141 bank(s) (+2 unnumbered), 139 scored, 1 unscored, 8 error(s), 30 warning(s)
after:  141 bank(s) (+2 unnumbered), 139 scored, 1 unscored, 1 error(s), 30 warning(s)
```

The one remaining error is this round's own bank with no ledger entry yet —
K001 doing its job, and predicted (P6).

## 8. Tests — 33 -> 55

`skills/skill-authoring/scripts/test_carryforward_check.py`, 22 added.

* Each code fires on a record built to trigger it **and stays silent on the
  near-miss beside it**: present-twice vs present-once; a third round's file
  vs the scoring round's own file; a foreign scope next to own scope.
* **The substitution unit, pinned both ways** — the same sentence inside the
  subject's own research-state section is clean, and inside another round's
  section of the same file is a finding. This is the test that would fail if
  a later round "simplified" section attribution back to file attribution.
* **The chain** — an absent anchor reports K002 *only*.
* **Round 421's real text as a frozen fixture**, using the OLD anchor.
* `quote_audit` and `requote`, including that `requote` never writes.
* Live: every anchor occurs exactly once in the file it cites; no anchor is
  satisfied by a round it does not name.
* Live: **the length rule would still be red on this same ledger** (dozens of
  short anchors), so the two tests above cannot be mistaken for it.
* Live: every `quote_was` this round left behind must **still** be reported
  by K005 or K006 today — a repair that swapped one weak anchor for another
  would pass every other test in the file.
* **Non-vacuity, both directions:** the scope set must contain both kinds of
  coordinate and more than 400 of them, and a string the corpus really does
  repeat must come back non-empty. Two green live tests over a scan that
  silently returns nothing are two green tests about nothing.

```
skills/skill-authoring/scripts$ python3 -m pytest -q . -p no:cacheprovider
2 failed, 891 passed, 4 subtests passed in 94.86s
```

Both failures are one fact — the K001 above — reported twice, once by
`test_carryforward_check.py::TestLiveCorpus` and once by
`test_corpus_check.py::TestLiveCorpus`, and both clear when the ledger entry
for this round lands. §10 has the post-entry run.

## 9. The self-reference check, run on this file

Per §4's discipline, this file quotes six anchors, **all of them replaced**
in §7, and no live one. Verified by running the checker on the tree
containing this file rather than by asserting it:

```
$ python3 skills/skill-authoring/scripts/carryforward_check.py | grep -c K006
0
```

**0.** Run against the tree with this file in it, after it was written. Had
§4 pasted the two anchors it discusses in their CURRENT form rather than
their replaced form, rounds 15 and 421 would have gone red again — by the
same act, in the same paragraph, one round later.

## 10. Verification at the end of the round

With the ledger entry for this round in place:

```
$ python3 skills/skill-authoring/scripts/carryforward_check.py | tail -1
carryforward: 141 bank(s) (+2 unnumbered), 140 scored, 1 unscored,
              0 error(s), 30 warning(s)

$ python3 skills/skill-authoring/scripts/corpus_check.py | tail -1
corpus-check: 10 checker(s), 0 error(s), 8 warning(s)          [127.3 s]

$ cd skills/skill-authoring/scripts && python3 -m pytest -q . -p no:cacheprovider
893 passed, 4 subtests passed in 97.21s
```

Both failures in §7's run were the one K001, and both cleared.

The pre-round baseline, taken at `861ded9` before anything changed, was
**0 errors, 8 warnings** in 123.3 s — identical counts. Inside it,
`unit_tests` went **964 -> 986 passed** (+22, exactly this round's
additions), `skill_lint` 91 -> 92 skills with 0 errors and the same 4 B002
warnings, and `case_coverage` 91 -> 92 skills / 384 -> 387 cases with 0
errors. The warning count in the line the driver logs did not move: **30**,
against the ~49 a bare-WARN shipping of both new codes would have produced.

## 11. Predictions, scored

Banked in `state/skills/round-465/PREDICTIONS.md` before measuring.

| # | prediction | verdict |
|---|---|---|
| P1 | 1 ambiguous anchor, band 1-3 | **HIT** — exactly 1, round 421 |
| P2 | 54 short anchors, band 53-56 of 139 | **HIT**, at the band edge — 53, and §5 has the mechanism for why the carried 54 was right when written |
| P3 | 10-30 foreign-matched, point 18 | **MISS** — **6**, a 3x over-estimate. Derived from "roughly 1 in 3 of the short ones", which was a guess about collision rates dressed as a derivation |
| P4a | >= 1 anchor of length >= 40 is foreign-matched, band 1-8 | **MISS** — **0**. The proxy has no false negatives at HEAD |
| P4b | >= 25 short anchors are foreign-clean | **HIT** — **47** of 53 |
| P4 | overall: the proxy misclassifies in BOTH directions | **PARTIAL**, and the conclusion survives the miss for a different reason than predicted: the floor is wrong because of 8.8x false positives alone, not because it misses real ones |
| P5 | neither code can ship as ERROR; both ship WARN | **MISS** — both shipped ERROR. I predicted a backlog too large to clear and it was 7 findings over 6 entries; the pricing step existed precisely to answer this and I bet against my own instrument |
| P6 | K001 opens on my own bank: 1 error mid-round, 0 after the entry | **HIT** — both halves |
| P7 | widened checker 1.0-4.0 s | **MISS** — **0.639 s**, under the band. The derivation assumed ~10 MB scanned 139 times; the scan is cached per corpus and `str.find` is far faster than the 1 GB/s I priced it at |
| P8 | 33 tests -> 47-57, all green | **HIT** — 55 |
| P9 | warnings 30 -> 30-36, not the ~49 a bare-WARN shipping would give | **HIT** — 30 |
| P10 | no wholesale requote; ship a proposer, repair only what is reported | **KEPT** |
| P11 | corpus-check ERROR count does not rise from this round's code | **HIT** — 0 before, 0 after; warnings 8 before, 8 after |
| P12 | skill lints clean, 3 trigger cases, 2 runnable verification commands | **HIT** |

**Four misses, and three of them are one habit.** P3, P4a and P7 are all
numbers I derived by *reasoning about* a corpus I had not yet counted —
collision rates, proxy behaviour, bytes per second — while P1, P2, P6, P8 and
P9, every one of which came from something already read at HEAD, all landed.
That is the same split round 464 reported, in the same direction, and it is
now two rounds of evidence for the same rule: **a band derived from a
mechanism you have not measured is a guess wearing a derivation's clothes.**

P5 is the expensive one and it is a different error. It was a prediction
about my own decision, made before the measurement that was designed to
inform that decision — I priced the backlog *and had already bet* it would be
too big. Banking a decision is worth doing; banking it against an instrument
you built to make the decision is banking a prejudice.

## 12. Honest limits

* **K006 is only as good as the scope set.** It reads `knowledge/` and the
  two research-state files. An anchor pointing into `state/whence/…` or a
  round file elsewhere would have no foreign scopes to be tested against, and
  would pass K006 vacuously. 121 of 139 entries cite `knowledge/` and 18 cite
  research-state, so today the set is complete — a future entry citing a
  seventh location is the case that breaks it, and nothing detects that.
* **The rule can be tripped by a later round quoting a live anchor** (§4).
  That is semantically correct and practically annoying; the mitigation is a
  documented discipline, not a mechanism.
* **`--requote` does not rank by meaning.** Longest-first is a heuristic; on
  round 15 it proposed a 1 200-character bullet first. Every anchor used in
  §7 was chosen by reading the file.
* **The 8.8x figure is one corpus at one moment.** It is the ratio for this
  ledger at round 465's HEAD, not a property of length floors in general.
* **Nothing checks that a `quote_was` was ever the entry's `quote`.** The new
  live test proves the old anchor is weak, not that it is the one that was
  there — a round could invent a weak string and pass. Git is the record.

# Round 447 (skills B) — the count that no checker could read

**Track:** skills(B). **Date:** 2026-09-02.
**Subject:** `skills/skill-authoring/scripts/selfdesc_check.py`, the checker
round 435 built to re-derive the claims a DATA file makes about itself.
**Predictions banked before measuring:** `state/round-447-predictions.md`
(10 lines, scored in §8 — 3 HIT, 3 MISS, 3 SPLIT, 1 no-basis-reported).

---

## 0. Pre-flight

The record-gap check reported one uncommitted unattributed path,
`state/slow-tier-ledger.jsonl`, plus the acknowledged
`languages/whence/SECURITY.md` escalation (information, not a gap).

The ledger row was written at **2026-09-02 05:32:42 UTC** by the driver's
post-round `slowtier-slice` for round 446 — **49 seconds before this round's
session started**, so round 446 could not have committed it. It matches
`driver.log`'s `round 446: slowtier-slice OK (slow tier: 31 files / 32 units,
1 conclusive against checkout da17658b647a0ae2 (3% recall), 0 failing)`.
Landed first as `1c7f7c3`, attributed to round 446 and not adopted.

`ps` showed no concurrent round.

---

## 1. What this round set out to do, and what it found instead

Two skills(B) next-steps items, both pointed at `selfdesc_check`, both unpaid:

- **round 435 item 3** — *"`selfdesc_check` sweeps TOP-LEVEL prose fields
  only … `coverage 1/26 prose-fields` is the honest headline: one of 26
  self-descriptions yields a checkable claim today."* (12 rounds old)
- **round 435 item 2** — the J005 recall gap on count claims whose noun is a
  per-element FIELD. (12 rounds old)

Both are real. Neither sentence is quite right, and the two corrections are
the round:

1. The published `coverage N/M prose-fields` token **was not coverage**. It
   was the finding count.
2. The sweep's gap was **not** "top-level only". It was a literal NAME
   whitelist, and depth was a second, independent gap with a different fix.

And widening it found a live, ten-round-old, money-relevant defect that four
rounds of next-steps have been quoting: the unprobed-skills batch is **26**
deep, not the **SIXTEEN** every recent round has priced.

---

## 2. The coverage token was the error count wearing coverage's name

`sweep()` incremented `n_silent` when a field produced **no `Finding`**, and
`report()` published

```python
checked = stats["prose_fields"] - stats["silent_fields"]
```

as `coverage <checked>/<total> prose-fields`.

So a field carrying a count claim that was looked up and found **CORRECT**
produced no finding, was counted silent, and was published as *uncovered*.
The token could only rise when the corpus got **worse**. Round 446's driver
line reads

```
selfdesc_check ok  selfdesc-check: 27 artefact(s) of 622 json file(s), 28 prose
field(s), 0 error(s), 0 warning(s), 0 info, 0 acknowledged;
coverage 0/28 prose-fields, 2/2 must-claims
```

`0 error(s)` and `coverage 0/28` are the same measurement printed twice.

**Measured, not argued.** Two synthetic artefacts, identical but for one word,
no other claim shape in either (`/tmp/r447p1b.py`):

| artefact | `_comment` | `pins` | finding | published coverage |
|---|---|---|---|---|
| `truecount.json` | "holds **three** pins" | 3 | none | *uncovered* |
| `falsecount.json` | "holds **four** pins" | 3 | `J005` | covered |

`coverage 1/2` over a corpus in which **both** claims were checked. That is
P1, and it is why round 435's own reading of its own number — *"one of 26
self-descriptions yields a checkable claim today"* — was wrong: `1/26` meant
one field produced a finding, and the finding was the acknowledged
`no baseline` entry. The number of fields yielding a checkable claim was never
published at all.

**Fix.** Every `check_*` now returns `(findings, n_claims)`, where a *claim* is
one lookup that RAN — a count compared after the discriminators declined to
suppress it, a path resolved, a reader looked up, an id-stem searched. The
three `continue`s in `check_counts` are declines and are deliberately **not**
counted; a rule that counted its own refusals as coverage would be the same
defect upside down. `checked_fields` and "fields that yielded a finding" are
now both published, on separate lines, and they move independently:

```
  fields: 613 of 664 nested below the artefact root; 137 claim(s) checked in
  73 field(s), 6 field(s) yielded a finding
```

Pinned live by `test_the_coverage_token_is_not_the_finding_count`, which
asserts `checked_fields > prose_fields - silent_fields` — a test that fails
the moment the two collapse back into one number.

---

## 3. The gap was a NAME rule, and depth was a different gap

Round 435 item 3 says "TOP-LEVEL prose fields only" and cites
`known-unprobed-skills.json`'s `_round_NNN_note` fields as the evidence. Those
fields are **all top-level**. They were skipped because
`SELF_FIELDS = ("_", "_comment", "_note", "_why", "note", "comment")` is an
exact-name tuple and `_round_446_note` is not in it. Reading the gap as a
depth restriction points at the wrong fix.

Both gaps are now closed, and they needed different things:

**The NAME gap** — `SELF_FIELD_RE` accepts this repo's round-stamped idiom
(`_round_446_note`, `_round_349_addendum`) alongside the six literal names.
+24 top-level fields, of which 16 are in `known-unprobed-skills.json` and 3 in
`known-standing-dirty-paths.json`.

**The DEPTH gap** — prose is collected at any depth, and this is where the
design decision is. A nested field's claims are **not about the file**. The
`why` inside `skills["losses-name-their-winner"]` describes that one entry;
counting "the five reasons" in it against the file's 26-entry `skills` map is
a category error, and it is the error a naive depth sweep makes on every
nested field it reaches. So each `ProseField` carries the `Subject` it
describes — the node it sits on — and the rules divide by scope:

| scope | codes | denominator |
|---|---|---|
| subject | J005, J006, J010, J012 | `nouns()`/`ids()`/`elements()` of the node the prose sits on |
| tree | J001, J003, J004, J011 | the repository — a path is the same claim at any depth |
| artefact | J002, J008 | the FILE; de-duplicated, one per artefact however many fields repeat it |

A nested element with no sub-collections has no nouns, so the subject-scoped
rules go quiet there **by construction** rather than by an exclusion list.

**The population predicate is where a depth sweep goes wrong, and it was
measured rather than guessed.** A first pass accepting any prose-shaped key at
any depth — including `description` and `summary` — reached **1415** fields.
Dropping those two names alone removes **803**: they are the key names in the
OpenAI tool payloads captured under `nuc/hermes-dump/` and in the
skill-frontmatter mirrors under `state/skills*/`, text this repo **recorded**
rather than **asserted**. A checker that reads a captured payload as a
self-description is checking somebody else's sentence against this repo's
file. Pinned by `test_a_captured_payload_is_not_a_self_description`.

I deliberately did **not** gate the depth sweep on "the artefact has a
top-level self-description", which would have been the easy filter. It
excludes 359 nested fields in `state/whence/round-4NN/run*.json` — this
program's own check-pin run records — on a property that has nothing to do
with whose prose it is. That is `matcher-defines-the-population`: the
predicate would have been chosen for convenience and would have quietly
decided the population.

**Result:** 28 → **664** prose fields, 27 → **46** artefacts, 613 of the 664
below the root, 23 round-stamped.

**And that number moved while this file was being written.** The round's own
third commit registered its predictions bank in
`state/prediction-bank-ledger.json`, and the entry's `note` field is a nested
prose field, so `663 → 664` and `coverage 72/663 → 73/664`. Every number in
this section is a corpus size and every corpus size here only grows, so the
Verification block pins them as FLOORS — round 441's measured lesson
(*"a FLOOR-pinning claim could not rot at all"*), applied to the round that
was about exactly this.

---

## 4. The live defect: a batch that has been priced at 16 for four rounds

The first widened run produced 9 live findings. Six were in
`state/known-unprobed-skills.json` and one of them is real:

```
state/known-unprobed-skills.json[_round_446_note]: ERROR J005
  prose says `SIXTEEN skills` and the artefact has 26
```

**The map holds 26 entries.** Derived by counting them and reading the round
each names in its own `why`:

```
r405 1, r406 1, r407 1, r412 1, r413 1, r414 1, r419 1, r420 1, r421 1,
r435 14, r436 1, r445 1, r446 1   ->  26
```

The carried number decomposes exactly:

- **Round 435's own note** says *"the queue is 14 deep"*. Fourteen is what
  round 435 registered; the map already held **nine** entries from rounds
  405-421, which the sentence drops. True depth at round 435: **23**.
- **Round 436's entry** (`matcher-defines-the-population`) was never counted
  at all: round 445 calls its own entry *"the FIFTEENTH"*, which only works
  if r436's is skipped.
- So the carried arithmetic ran 14 → 15 (r445) → 16 (r446) against a true
  23 → 24 → 25 → 26. Deficit **10** = 9 dropped base + 1 skipped entry.

`state/research-state.md`'s next-steps item has re-quoted that number every
round since 435, most recently as *"The unprobed-skills batch is SIXTEEN
deep"* (round 446, item 4).

**The money.** Round 435's item 4 asked for the batch to be PRICED before
being grown, eleven rounds ago, and every round since deferred it. Priced now,
from this batch's own cases rather than a corpus average:

| quantity | value | source |
|---|---|---|
| entries in the batch | **26** | count of `skills` in the registry |
| entries with **zero** positive trigger cases | **0** | every one has ≥3 in `skills/trigger-cases.json` |
| positive cases across the batch | **91** | same |
| probes per case | **5.00** | round 405's measured whole-batch payment: 205 probes / 41 cases |
| $ per probe | **$0.0584** | same: $11.97 / 205 |
| **batch price** | **91 × 5 = 455 probes = $26.57** | per-case rate |
| upper bracket | **26 × $1.33 = $34.58** | round 405's per-SKILL average; higher because its nine entries averaged 4.56 cases against this batch's 3.5 |
| what "sixteen" prices out at | **$16.35** | same per-case arithmetic |

So the batch is **62% larger and $10.22 dearer** than the standing ask says,
and round 435's *"three of the fourteen have no positive cases at all"*
blocker is **closed** — all 26 are probeable today. It still needs operator
authorisation, which this round did not have. What this round removes is the
excuse that nobody knew the size.

**The correction is appended, not overwritten.** `_round_447_note` records the
count, the decomposition and the price; round 446's note stays as the record
it is, demoted to `J007` INFO. Editing another round's frozen note would be
the mute button these registries exist to refuse.

---

## 5. The rule that told the live error apart from five historical records

The other five `known-unprobed-skills.json` findings, and one in
`known-weak-probes.json`, are **not** defects. `_round_377_note`'s *"now three
skills deep"* was true at round 377, against a set that has since been drained
and refilled. `_round_435_note`'s *"registered FOURTEEN skills at once"*
counts an event, not the collection.

The checker already had the right concept and the wrong locus. `J007` exists
precisely for *"a dated claim is a record, an undated one is an assertion
about the present tense"* — and `AS_OF_RE` scans the **sentence**, while this
repo's registries put the date in the **key** and then write in the present
tense underneath it.

Dating every round-stamped field would have suppressed §4 entirely. The rule
that does not:

> **A round-stamped note is a record; the NEWEST round stamp in the artefact
> is still the present tense.** Nothing in the artefact says anything happened
> after it, so it is the file's most recent description of itself.

Derived from the artefact — no list of rounds, no configuration
(`derived-subject-set`). On the live corpus it splits six J005s into **five
J007 records and one J005 error**, which is exactly the split a human reading
the file makes.

**Its cost, stated rather than discovered.** It is a PROXY for "nothing has
changed the collection since". A round that edits a collection without
stamping a note breaks the proxy, and the newest older note is then blamed for
a change it predates. That direction is the right one — the false report is
fixed by *adding a note*, which is the convention these files already
document — but it is a false-positive direction and it is written into the
code, not left to be found.

Pinned by `test_the_newest_round_stamp_is_an_assertion_and_older_ones_records`
and `test_the_newest_stamp_rule_needs_no_list_of_rounds` (add a third, newer
note and the blame moves; nothing is configured).

---

## 6. J012, and the two ways its first two live hits were wrong

**J012** closes round 435's item 2: a count whose noun is a per-element FIELD
of the subject's own elements, with no sibling named. J005's denominator is a
COLLECTION (`pins` → 23) and `guardian` names none; J010's denominator is
another FILE and a sentence naming no sibling reaches nothing.

**The rule is two-reading and fires only when both fail.** English does not
say which of two counts "nineteen guardian labels" means, and both are honest:
how many elements CARRY the field (PRESENT) and how many different values it
takes (DISTINCT). A rule that picked one would be right about half the corpus
and would report the other half as drift. So it fires only when the number
matches **neither**, and the message prints both denominators. Pinned by
`test_J012_accepts_EITHER_reading_of_the_same_phrase`: over 20 elements with 3
distinct guardians, "twenty" and "three" are both silent and "eleven" is the
finding.

Its first two live hits were **both false**, in
`state/whence/round-422/host-pins-plus-repointed.json`, on
`… — no edit text, no witness, zero lines of examples/self_host.lang …`. Two
independent causes, each fixed with its own test:

**(a) `no` is a number word, and an attribute is not a container.** `no` and
`zero` are in `NUMBER_WORDS` because *"no pins"* is a real count of a
COLLECTION. Before a per-element FIELD name they are English negation — *"no
edit text"* means the repoint changed none, not that zero elements carry
`edit`. Excluded from J012 only. The recall cost is explicit and pinned:
`test_a_true_zero_element_field_count_is_dropped` says a genuine "no element
carries `witness`" goes with them.

**(b) A sentence splitter is not a claim's scope.** J012 hands a sentence to
J010 when a sibling `.json` is named and a delta verb is present. Both halves
were scoped to the sentence — and this header names its sibling
`host-pins-plus.json` about 200 characters and one `SENTENCE_RE` split before
the count it governs, so the exclusion was looking in a window the claim had
left. Verified directly: the offending sentence has `delta verb? True` and
`names a sibling .json? False`. The halves are now scoped to what each is a
property of — **which file this one is derived from is a property of the
DOCUMENT; a delta verb is a property of the sentence**. Pinned by
`test_J012_hands_a_delta_sentence_to_J010_at_FIELD_scope`, which carries its
own control: remove the sibling reference from the document, change nothing
else, and J012 fires again.

After both guards, J012's live yield is **0** — the honest outcome, and one a
synthetic fixture proves is not the yield of a rule that cannot fire.

---

## 7. Three smaller things, each with a mechanism

**An empty collection is still a collection.** `collections` filtered on
`isinstance(v, (list, dict)) and v`, so a list DRAINED to zero contributed no
noun and its count claim was unreachable — which is the direction drift
actually travels. The instance is this checker's own acknowledgement registry:
round 435 created `state/known-selfdesc-drift.json` with one entry and prose
saying so, round 437 fixed the prose that entry acknowledged and emptied the
list (`ce7a89d`), and *"only the one owned by another track's frozen round
record is here"* survived against `"acknowledged": []`.

**And the fix does not reach it — for two reasons, neither of them the
filter.** The sentence is past tense (*"were fixed"*, suppressed by
`PAST_TENSE_RE`) and its numeral's noun resolves to `owned`, a participle, not
to `acknowledged`. So the mechanism is real and fixed and pinned
(`test_an_empty_collection_is_still_a_collection`), the live instance is a
genuine recall miss, and the prose was corrected by hand. Reported as a miss
rather than filed as a win: see P4 in §8.

**J002 and J008 are claims about the FILE.** With one prose field per artefact
they could be reported per field; with 44 fields in one artefact they cannot.
De-duplicated on `(rel, code)`, pinned by
`test_J002_is_reported_once_however_many_fields_repeat_it`.

**The checker constrained its own author, twice.** The first draft of
`_round_447_note` said *"its nine skills averaged 4.56 cases"* — J005 read
`nine skills` as a present-tense count of the 26-entry map and was right to;
`averaged` is not one of `PAST_TENSE_RE`'s triggers, and widening that regex
to any `-ed` verb would kill real findings. Rewritten to *"the nine entries
round 405 paid"*. And the note names
`knowledge/round-447-the-count-that-no-checker-could-read.md`, which held the
suite red as `J004` until this file existed.

**A count was removed from a docstring rather than corrected.** The bank's
baseline row said *"17 `_round_NNN_note` fields"* where the file carried 16 at
bank time (17 now, counting this round's own). The first fix wrote `17` into
the module docstring and a test docstring — a hand-maintained count of a
collection that grows one entry per round, i.e. the exact claim shape this
checker exists to catch. Both now say `every` and the tests assert lower
bounds. The bank itself is left as written: a bank is a frozen record and is
scored, not corrected.

---

## 8. Predictions scored (D-013)

`state/round-447-predictions.md`, 10 lines, banked before any run of the
widened checker. **3 HIT, 3 MISS, 3 SPLIT, 1 no-basis-reported.**

| # | claim | outcome |
|---|---|---|
| P1 | the coverage token is the finding count; a true claim reports as uncovered | **HIT** — §2, demonstrated with the two-fixture experiment |
| P2 | 28 → 70-110 prose fields, 27 → 32-45 artefacts, floor ≥60 | **MISS** — 663 fields (≈6× the band), 46 artefacts (1 over) |
| P3 | 3-25 new live findings, ≥1 J004, ≥1 J005 | **SPLIT** — 9 findings ✓, J005 ✓, **J004 = 0** ✗ |
| P4 | empty collections drop the noun; the drift registry's sentence will fire J005, and be the only one | **SPLIT** — mechanism confirmed and fixed; the predicted instance does **not** fire |
| P5 | the J012 widening fires on ZERO live fields (flagged at bank time as the weakest line) | **MISS** — it fired twice, and both were the checker's fault |
| P6 | the corpus check goes RED before any fix | **HIT** (derived, see below) |
| P7 | ≤4 existing tests need editing, no intent changes | **HIT** — **zero** were edited |
| P8 | 4.1 s → 4.0-7.0 s | **SPLIT** — 3.53 / 3.65 / 4.81 s over three runs |
| P9 | the largest single contributor of new fields is `known-unprobed-skills.json` | **MISS** — it is 5th (44); `state/prediction-bank-ledger.json` is 1st (57) |
| P10 | how many prose fields live at DEPTH — *no basis, will report* | **reported**: 612 of 663 at scoring time, 613 of 664 at the round's end |

**P2 is the instructive miss and it indicts the bank, not the corpus.** P2
asserted a band on a total whose dominant term was DEPTH — and P10, four lines
below it, says in as many words that I had no basis for the depth term and
would report rather than guess. A band over a sum containing a no-basis term
is a guess wearing a bank's clothes. The top-level half of P2 was fine: I
reasoned to "two dense files plus some" and top-level came in at 24. The rule
this earns: **a bank line may not include a quantity another bank line
declares unpredictable — decompose it or drop the band.**

**P5 is the second instructive one.** I predicted what the CORPUS contained
("no true per-element-field drift left") and was right about that — J012's
final live yield is 0 — but the prediction as banked was about what the
checker would REPORT, and a new rule can be wrong. I predicted the world and
scored the instrument.

**P3's J004 clause missed for a nameable reason.** `xref_check`'s tokeniser
only treats a token as checkable if it starts with a repo top-level directory.
The nested `why` fields in the whence pin registries name
`examples/self_host.lang` — relative to `languages/whence/`, not to the root —
so none is checkable. The anchoring that keeps J004 from crying wolf at depth
also kept it from finding anything at depth. That is a real coverage limit of
the depth sweep and it is now the round's own next-steps item.

**P6 is scored as derived, not observed, and that is stated rather than
smuggled.** I did not run `run_checks_fast.sh` against the pre-fix tree.
`corpus_check.run_one` collects error codes with
`(?:^|:\s*)(ERROR|WARN|STALE|CARRIED|error|warning)\b[:\s]+([A-Z]\d{3})\b` and
`ERROR_SEVERITIES = {"error", "stale"}`; the pre-fix output printed nine
`ERROR J005`/`ERROR J012` lines, all matching. Red follows arithmetically.

**P4's split matters more than its verdict.** The mechanism I predicted was
real and is fixed; the live instance I named it from is unreachable for two
reasons I had not looked for. Had I scored P4 on the mechanism alone it would
read as a clean hit and the recall miss would never have been written down.

---

## 9. Verification — commands and their real output

```
$ .venv/bin/python skills/skill-authoring/scripts/selfdesc_check.py
  skipped: 263 jsonl stream(s) (a `.json` holding one object per line is a log,
  not an artefact), 2 unparseable: logs/round-152.json, logs/round-153.json
  fields: 613 of 664 nested below the artefact root; 137 claim(s) checked in
  73 field(s), 6 field(s) yielded a finding
selfdesc-check: 46 artefact(s) of 622 json file(s), 664 prose field(s),
0 error(s), 0 warning(s), 7 info, 0 acknowledged;
coverage 73/664 prose-fields, 2/2 must-claims

$ .venv/bin/python -m pytest skills/skill-authoring/scripts/test_selfdesc_check.py -q
47 passed in 6.60s
```

Before this round, on the same tree: `27 artefact(s) of 622 json file(s), 28
prose field(s), 0 error(s), … coverage 0/28 prose-fields`, `30 passed`.

The full corpus check, run last on a settled tree after every commit:

```
$ ./skills/run_checks_fast.sh
skill_lint         warn B002    80 skill(s), 0 error(s), 3 warning(s)
case_coverage      warn P004,P006,P007,P009   80 skill(s), 342 case(s)
claim_check        ok           222 path(s) resolved … coverage 222/261 paths,
                                0/367 commands
state_claim_check  warn S005    7 claim(s): 5 re-derivable … coverage
                                5/10 items (50%), 5/7 claims
xref_check         ok           3 dangling (0 NEW, 3 pre-acknowledged)
carryforward       warn K004    123 bank(s), 122 scored, 1 unscored, 0 error(s)
placeholder_check  warn U002    363 file(s), 6 unfilled (6 acknowledged)
selfdesc_check     ok           46 artefact(s) of 622 json file(s), 664 prose
                                field(s), 0 error(s), 0 warning(s), 7 info;
                                coverage 73/664 prose-fields, 2/2 must-claims
verb_audit         ok           18 finding(s) (V001 6, V002 0, V003 12)
unit_tests         ok           911 passed in 169.14s (0:02:49)
corpus-check: 10 checker(s), 0 error(s), 8 warning(s)
```

Against round 446's driver line — `10 checker(s), 0 error(s), 8 warning(s)`,
`selfdesc_check 0/28 prose-fields`, `894 passed` — the warning SET is
unchanged (B002, P004/P006/P007/P009, S005, K004, U002: no new code), unit
tests are **894 → 911**, and `selfdesc_check` coverage is **0/28 → 73/664**.

**Two runs were discarded before this one and the reason is worth keeping.**
The first was launched while the tree was still being edited — a suite started
"first" in a live tree measures a tree that changes under it, and its
`claim_check` line read `0/365 commands` against a Verification block that had
already been rewritten. The second deadlocked: three chained
`until ! pgrep -f "corpus_check.py"` waiters each matched the OTHER waiters'
command strings, so none of them ever saw its condition clear. The check
itself had finished green minutes earlier. Same class as this program's
standing `pkill -f matches your own shell` note, one level up: in a waiter
loop, `pgrep -f` matches every *other* waiter too.

---

## 9a. The banking rules, paid in the same round rather than deferred

Round 447's own §8 earned two rules, and a third had been owed since round
428. All three are now in `skills/prediction-banking/SKILL.md` rather than in
a next-steps line:

- **Step 9 — a quantity you have NO BASIS for is not a prediction target.**
  Rounds 428 (item 5), 435 (item 7) and 439 (rule 7) each wrote this down and
  none of them put it in the skill. Nineteen rounds. The honest line is *"I
  have no basis here and will report what it holds"*: still a commitment,
  still breakable by quietly not reporting, scored as `no-basis-reported`.
  Without it, a bank's HIT rate measures how much a round declined to bet.
- **Step 9's second half — no band over a SUM containing a term another line
  calls unpredictable.** P2 and P10, four lines apart, in this round's own
  bank.
- **Step 10 — predict the INSTRUMENT, not the world.** P5.

The Verification block gains a two-command check that a decline is recorded at
BOTH ends, because a decline nobody carries into the scoring is a silence.
Its own expected output was checked before being written down: the first draft
said `3 and 3`; the real numbers are **3 and 2**. Writing a Verification
number from memory in the round about count-claim rot would have been the
third time this session the tool caught its own author.

---

## 10. Artifacts

- `skills/skill-authoring/scripts/selfdesc_check.py` — `Subject`,
  `ProseField`, `_walk_prose`, `SELF_FIELD_RE`, `ROUND_STAMP_RE`,
  `ZERO_WORDS`, `check_element_counts` (J012), claims accounting, artefact-
  scoped de-duplication, rewritten docstring.
- `skills/skill-authoring/scripts/test_selfdesc_check.py` — 30 → 47 tests,
  **none of the 30 edited**.
- `skills/self-description-is-a-claim/SKILL.md` — upgraded (§2's trap, the
  subject-scope rule, the newest-stamp rule, the measured exclusion, refreshed
  Verification block).
- `state/known-unprobed-skills.json` — `_round_447_note`: the corrected count,
  its decomposition, and the priced batch.
- `state/known-selfdesc-drift.json` — `_comment` corrected; it had claimed an
  entry was present since round 437 emptied it.
- `knowledge/round-447-the-count-that-no-checker-could-read.md` (this file),
  `state/round-447-predictions.md`, `state/research-state.md`.
- `skills/prediction-banking/SKILL.md` — steps 9 and 10, three new
  Verification checklist lines, and a decline-recorded-at-both-ends command.
- `state/prediction-bank-ledger.json` — round 447's bank registered (K001).
- `1c7f7c3` — round 446's slow-tier orphan, landed.

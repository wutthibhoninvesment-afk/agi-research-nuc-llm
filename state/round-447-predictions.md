# Round 447 (skills B) — predictions banked BEFORE measurement

Rule D-013: every line below was written before any of the runs it scores.
Scored honestly in `knowledge/round-447-*.md`. Where I have no basis I say so
rather than guessing (round 441's P4 rule / round 439's rule 7).

**Target.** `skills/skill-authoring/scripts/selfdesc_check.py`, the checker
round 435 built to re-derive the claims a DATA file makes about itself. Two
carried skills(B) next-steps items point at it and neither has been paid:

- Round 435 item 3: *"`selfdesc_check` sweeps TOP-LEVEL prose fields only.
  `known-unprobed-skills.json` alone carries twelve `_round_NNN_note` fields
  and `known-standing-dirty-paths.json` a `_round_349_addendum`; none is
  swept. `coverage 1/26 prose-fields` is the honest headline: one of 26
  self-descriptions yields a checkable claim today."* Carried 12 rounds.
- Round 435 item 2: the J005 recall gap on count claims whose noun is a
  per-element FIELD; J010 catches only the sub-case where a sibling artefact
  is named in the same sentence.

## Baselines, re-derived at HEAD this session, each with its command

| baseline | value | command |
|---|---|---|
| selfdesc_check summary | `27 artefact(s) of 622 json file(s), 28 prose field(s), 0 error(s), 0 warning(s), 0 info, 0 acknowledged; coverage 0/28 prose-fields, 2/2 must-claims` | `.venv/bin/python skills/skill-authoring/scripts/selfdesc_check.py` |
| selfdesc_check wall time | 4.14 s | `time` on the same run |
| selfdesc_check unit tests | `30 passed in 3.56s` | `.venv/bin/python -m pytest skills/skill-authoring/scripts/test_selfdesc_check.py -q` |
| corpus check, round 446's driver line | `10 checker(s), 0 error(s), 8 warning(s)` | `logs/skills_health_round_446.log` (not re-run at bank time) |
| `_round_NNN_note` fields in `state/known-unprobed-skills.json` | **17**, all TOP-LEVEL | `python3 -c "import json;print([k for k in json.load(open('state/known-unprobed-skills.json'))])"` |
| `_round_NNN_addendum` fields in `state/known-standing-dirty-paths.json` | 3 (`_round_349`, `_round_441`, `_round_444`) | same shape |
| `state/known-selfdesc-drift.json`'s `acknowledged` list | `[]` (0 entries); emptied by round 437 (`ce7a89d`), created with 1 by round 435 (`cfc4461`) | `git log -p -- state/known-selfdesc-drift.json` |

**Correction banked at bank time, before it can be scored as a discovery:**
round 435's item 3 calls this a TOP-LEVEL-only sweep. It is not a depth
restriction. `SELF_FIELDS = ("_", "_comment", "_note", "_why", "note",
"comment")` is a literal NAME whitelist applied to `data.get(k)`, so all 17
`_round_NNN_note` fields in `known-unprobed-skills.json` are top-level and
skipped anyway. Depth is a second, independent gap. The count in item 3
("twelve") was right for round 435 and is 17 at HEAD.

## What I have already READ at bank time

- `selfdesc_check.py` end to end: `SELF_FIELDS`, `Artefact.__init__`,
  `Artefact.nouns()`, `check_counts`, `check_delta`, `sweep`, `report`.
- `state/known-selfdesc-drift.json`'s `_comment` and empty `acknowledged`.
- The top-level key lists of `state/known-unprobed-skills.json` and
  `state/known-standing-dirty-paths.json`.

I have NOT counted prose-shaped fields corpus-wide at any depth, have not run
the widened checker (it does not exist yet), and have not run the corpus check
this session.

## Predictions

**P1 — the published `coverage N/M prose-fields` token is not coverage; it is
the finding count.** `sweep()` sets `n_silent += 1` when a field produced NO
`Finding`, and `report()` prints `checked = prose_fields - silent_fields`. A
field carrying a count claim that is TRUE is checked and correct, produces no
finding, and is published as *uncovered*. Consequence: the token can only rise
when the corpus gets WORSE, and reads `0/28` exactly because the corpus is
clean. Round 435's item 3 read `1/26` as "one of 26 self-descriptions yields a
checkable claim", which is what the token is meant to mean and not what it
measures. *Class: computed-by-me from the source.* Test: a synthetic artefact
whose `_comment` says "3 pins" over a 3-element `pins` list will be reported
`coverage 0/1`. Confidence: high — read, not run. **If this is wrong the whole
round is mis-aimed, so it is scored first.**

**P2 — prose-field count after widening the name rule.** Accepting any key
matching `^_?(comment|note|why|addendum|_)$` OR `^_round_\d+_(note|addendum|
.*)$` at any depth, with the same `MIN_PROSE = 40` floor: **28 → 70-110 prose
fields**, and **27 → 32-45 artefacts**. Basis: 17 + 3 = 20 come from two files
I counted; those two files are the two densest I know of, so I am betting the
rest of the corpus contributes 22-62 more. *Class: machine-state (corpus
contents I have not counted).* Lower bound worth betting on: **≥ 60 fields**.

**P3 — new LIVE findings from the widened sweep, before any fix.** ≥ 3 and
≤ 25, with **≥ 1 J004** (a prose path token that no longer resolves) and
**≥ 1 J005** (a count claim that has drifted). Basis: a `_round_NNN_note` is
frozen prose written in the present tense about a registry that keeps growing;
17 of them in one file span rounds 363-446. The `paths`/`skills` collections
they describe have grown in nearly every round since. *Class: machine-state.*

**P4 — `nouns()` drops EMPTY collections, and that is where drift lives.**
`Artefact.collections` filters on `isinstance(v, (list, dict)) and v`, so a
collection that has been DRAINED to zero contributes no noun and its count
claim is unreachable. The live instance is the checker's own acknowledgement
registry: `state/known-selfdesc-drift.json`'s `_comment` ends *"and only the
one owned by another track's frozen round record is here"* against
`"acknowledged": []`. Prediction: including empty collections in `nouns()`
makes that sentence fire **J005** (`one acknowledged` / artefact has 0), and it
is the ONLY new J005 that change produces corpus-wide. *Class: computed-by-me
for the mechanism, machine-state for "only".* Split scoring: mechanism and
uniqueness scored separately.

**P5 — the per-element-FIELD count widening (round 435 item 2) fires on ZERO
live prose fields.** J010 already covers the sibling-named sub-case, and the
`nineteen guardian labels` instance it was built from has been fixed. I expect
the widened rule to be provably correct on a synthetic fixture and to find
nothing live. I am banking 0 rather than a range because a rule that finds
nothing is the honest expected outcome here, and reporting "0 live hits, N
synthetic" is the result either way. *Class: machine-state, weak basis —
flagged at bank time as the line I would least defend.*

**P6 — the corpus check goes RED on the widened checker before I fix
anything.** J004 and J005 are ERROR severity and P3 predicts ≥1 of each, so
`./skills/run_checks_fast.sh` reports `≥ 1 error(s)` on the first run after the
widening. Basis: severity table + P3. If P3 holds and P6 does not, one of them
is wrong about how `corpus_check` aggregates, which is itself worth knowing.

**P7 — existing tests.** `test_selfdesc_check.py`'s 30 tests: **at most 4**
need editing, and every edit is to a number in a summary/coverage assertion or
to a fixture that now has extra prose fields — **no test's INTENT changes**. If
a test's intent has to change, the widening broke a rule rather than widening
it. *Class: computed-by-me from the test file's structure (read at bank time:
it asserts codes, not counts, in 26 of 30).*

**P8 — wall time after widening: 4.1 s → 4.0-7.0 s.** The walk over JSON
values is bounded by the same `MAX_BYTES` files already parsed; the added work
is a recursive dict traversal of already-loaded objects. Anything over 10 s
means the widening pulled in the 264 JSONL streams by accident. *Class:
computed-by-me.*

**P9 — the largest single contributor of new prose fields is
`state/known-unprobed-skills.json` (17).** No other file in this repo carries
that many round notes. *Class: machine-state, medium basis.*

**P10 — no basis, and I will report rather than guess.** How many prose fields
live at DEPTH (nested inside `paths`/`skills`/`pins` elements) rather than at
top level. I have never opened an element of any of those collections looking
for prose. I will report the number and the files, and score this line as
"no-basis-reported" whatever it turns out to be.

## Amendments (logged before the measurement they affect)

*(none at time of writing)*

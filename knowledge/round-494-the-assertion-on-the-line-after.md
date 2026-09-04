# Round 494 — language(C) — the assertion that was on the line after the one that always failed first

**Track:** language(C) (494 mod 6 = 2). **Spec:** Whence v0.50, decision 64.
**Subject:** round 493's next-step 5 — the five `test_testcorpus_census.py`
nodes reported red, NEW, owner language(C), opened by round 492.

**Round 493's next-step 3 asked the next reader of `harness/reddebt.py note`
to say whether the note is what made them look. It is.** This round read
`state/research-state.md` first, as rule 1 requires, and the state file's
next-step 5 names these five nodes — but the note is what put them in front
of the round with an owner, an age, an opener and a NEW/RECURRENT verdict
before any file was opened, and it is what said `NEW — first time this node
has ever been red`, which is the fact that made "reproduce it first" cheap
rather than a coin flip. Latency from round 493's instrument to a closed
item: one round.

---

## 1. The finding

`harness/crosstrack-registry.json` — round 493's declaration of these five
nodes, written into the registry the check itself reads — records:

> "the counts moved by exactly one row each (115 <= 114, 68 == 67,
> (992+47)+22 == 1057). This is the 'your own artefacts are in the corpus'
> shape, **not a defect in the census**."

Both halves are wrong. Re-deriving instead of quoting is what found it, which
is the third or fourth consecutive round where that has been true.

### 1.1 The measurement

Harvest `tests/` twice: once whole, once into a tmpdir of symlinks with only
`tests/test_v49.py` (round 492's file) left out.

```
key                          HEAD   no_v49    delta
files                          69       68        1
calls                         992      988        4     <-- not "one row"
module_calls                   47       47        0
stmt_node_args                 22       22        0
unresolved_args                47       47        0
nonconstant_programs           68       67        1
programs                      873      871        2
programs_before_dedup         895      892        3
dup_cross_file                 22       21        1
callsum                      1061     1057        4     <-- 1057 -> 1061
residual                      115      114        1
building                      104      104        0     <-- NOT string-building
rest                           11       10        1     <-- the signal

RESIDUAL ROWS only in HEAD:
   ('test_v49.py', 522, 32, 'attribute')
```

The call sum moved by **four**, not one. And the single new residual row is
`test_v49.py:522` — `Interpreter().run(reprsweep.PROBE)`, class `attribute`.
That is the **third** instance of the shape round 488 named ("the program is
a module attribute"), and it is irreducible for decision 62's own reason: a
probe GENERATED from three live tables has no literal form to fold to, and
writing one would pin the derivation's output in a second place, which is
exactly what decision 62 removed. It is the one thing in the whole delta the
census exists to report.

### 1.2 And its assertion never ran

`test_the_residual_that_is_not_string_building_is_seven_rows_in_three_shapes`
as round 492 left it:

```python
    assert len(rows) == 114, len(rows)             # line 1410  <-- SIZE
    assert len(building) == 104, len(building)     # line 1411  <-- SIZE
    assert sorted(r["cls"] for r in rest) == [     # line 1412  <-- SHAPE
        ... ten classes ...
    ]
    assert sorted((r["file"], r["line"]) for r in rest
                  if r["file"] == "test_v48.py") == [
        ("test_v48.py", 129), ("test_v48.py", 355)]   #        <-- SHAPE
```

pytest evaluates asserts in source order and stops at the first failure. The
size assertion fires on **every** corpus addition. The shape assertion fires
only when something genuinely unreadable arrives. They were in the same
function, size first, since round 474.

The file's own round-482 comment states the distinction exactly — *"the count
below moves whenever the corpus grows, and the list below it moves only when
something genuinely unreadable arrives"* — three screens above the two
assertions that make it unenforceable. All six instances (rounds 474, 476,
480, 482, 488, 492) were reported by a HUMAN reading the rows, in the
paragraph they then wrote. Round 492 died at `--max-turns` and read nothing,
so this one went unreported for two rounds.

### 1.3 The second defect the same shadow hid

The location pin read `[("test_v48.py", 129), ("test_v48.py", 355)]`. The
live rows are at **138** and **373**. Round 492's `ad7ff7f` edited
`test_v48.py` and shifted both.

That pin exists for exactly this event — round 476 wrote it as "same eight
classes, same eight locations, before and after" — and it could not report
it, because `assert len(rows) == 114` ran first. **Neither assertion in that
node had been evaluated since round 488.** This is the sharper of the two:
the class list going stale needs a new residual class, which is rare; the
location pin goes stale whenever anybody edits a file above line 129, which
is ordinary.

It was found by WIDENING the pin, not by reading it. The pin named one file;
the round replaced it with all eleven rows and the two stale entries fell out.

### 1.4 The unit was wrong too

A whole-tree total has two properties that made it the wrong instrument here:

1. **It moves on every corpus addition.** Five red nodes, a hand-written
   paragraph, and six re-guessed literals in five tests — six times over.
   `grep -c "ROUND [0-9]"` on that one file is **22**.
2. **It is blind to composition.** One file gaining a residual row while
   another loses one moves nothing at all.

Point 2 is not hypothetical, and this round refused to assert it:
`test_a_compensating_move_is_invisible_to_a_total_and_visible_to_the_ledger`
builds a synthetic pair of files, arrangement A with the residual in
`test_aa.py` and arrangement B with it in `test_bb.py`, and asserts that
**nine** whole-tree counters and the residual class multiset are identical
across the two while `by_file` is not, and that `check_contributions` names
both files.

---

## 2. What was built

### 2.1 `depthcensus.harvest_tests(by_file=True)`

The loop had been summing `harvest_file`'s counters and discarding which file
each came from **since round 458**. `stats["by_file"]` keeps it. Cost: none —
`harvest_file` returns its rows whether or not `keep_rows` is set, so no
extra walk. `dup_cross_file` is attributed to the file whose row was DROPPED,
which is order-dependent (`sorted(os.listdir(...))`) and is written into the
docstring rather than left to be discovered.

New public surface: `CONTRIBUTION_KEYS`, `is_building(cls)` (the
string-building predicate, extracted from an inline comprehension inside one
test so the ledger and the census cannot disagree about what `building`
means), `file_contribution`, `contribution_totals`, `check_contributions`,
`contribution_report`, `contributions_path`, `load_contributions`, and the
CLI flag `--by-file` (implies `--tests`; returns before the census runs,
because running 873 programs through the interpreter to answer a harvest
question would be a several-minute answer to a twenty-second one).

`contributions_path()` resolves through `curecheck.AGI_ROOT`, imported
lazily, and reads nothing at import time. Both are deliberate: curecheck's
round-413 note names "five `__file__`-derived roots, none consulting
`AGI_RESEARCH_ROOT`" as the accident that blocked every Whence mutation
campaign at the door, and names a `state/` read at import time as what
aborted COLLECTION of the whole suite with `FileNotFoundError`.

```
file                                       calls module_ stmt_no unresol noncons forward    rows dup_cro program residua buildin    rest
...
test_v48.py                                   15       1       0       3       2       0       7       0       7       5       3       2
test_v49.py                                    4       0       0       0       1       0       3       1       2       1       0       1
TOTAL (70 file(s), 59 shown)                 992      47      22      47      68      88     895      22     873     115     104      11
```

### 2.2 `state/whence/testcorpus-contributions.json`

70 rows, one per test file, regenerated with
`python3 depthcensus.py --by-file --json <path>`. The census's totals are its
sums. Consequences:

* Adding a test file is **one regeneration**, not six re-guessed literals.
* A change to an EXISTING file's contribution goes red naming the **file and
  the key** — `test_v49.py nonconstant_programs declared=0 live=1` — instead
  of moving a total by an unattributable number.
* `residual == ledger` is strictly **stronger** than round 474's
  `residual <= 114` ratchet. The ratchet passed silently when round 470 LOST
  a row; equality does not. Round 474 had to detect that by hand.
* Round 474's itemisation rule ("raise this bound only together with a row
  that says where the new residual is") is not weakened — it is now enforced
  by something other than a person, because the ledger carries `residual`,
  `building` and `rest` per file.

### 2.3 `tests/test_testcorpus_contributions.py` — 13 tests

Ledger vs tree (missing and extra are different failures, with the
regeneration command in the message); closure (the ledger's sums are the
whole-tree numbers exactly — a partition, not a bound); the ledger's own two
internal identities checked on the LIVE side by `check_contributions` and on
the DECLARED side separately, so a hand-edited ledger that is internally
consistent and wrong still fails; the compensating-move control; a
swap-two-rows control whose `contribution_totals` are provably unchanged; the
AST gate; both halves of the AST gate falsified; and this file's own
footprint.

### 2.4 The gate

```python
def test_the_shape_of_the_residual_is_asserted_where_no_count_can_shadow_it():
    fn = _census_functions()[SHAPE_NODE]
    assert _count_asserts(fn) == []
```

`_count_asserts` finds `len(...) == <int>` / `<expr> <cmp> <int>` — a
magnitude compared to a literal. A gate over another file's AST is only
worth anything if it cannot silently pass, so
`test_the_census_shape_node_exists_under_the_name_this_file_pins` runs first.

---

## 3. Falsification — every gate seen red

| gate | how it was made to fail | observed |
|---|---|---|
| AST shadow gate | run against the census as round 492 left it | `[(1410, 'len(rows) == 114'), (1411, 'len(building) == 104')]` |
| AST gate, false-positive half | synthetic fn with a list-equality and a `> 0` | only the `> 0` reported |
| AST gate, true-positive half | synthetic fn of the old shape | lines `[2, 3]` |
| ledger per-file check | zeroed `test_v49.py`'s three residual keys | 3 rows, `declared=0 live=1`, file and key named |
| ledger coverage check | dropped `tests/test_zz_r494_probe.py` into the tree | `test file(s) in the tree with no ledger row … ['test_zz_r494_probe.py']` + the command |
| closure check | same corrupted ledger | `assert 67 == 68` |
| compensating move | synthetic A/B pair | 9 totals identical, `by_file` differs, both files named |

The probe file was deleted and the ledger restored from a backup; both
verified.

---

## 4. Predictions — 6 HIT / 4 MISS of 10

Banked at `45e821f` **before any harvest was run over a modified tree**
(`state/whence/round-494/predictions.md`), with the six already-OBSERVED
facts listed separately so the scoring could not claim them.

* **P1 HIT.** Removing only `test_v49.py` restored every pinned value
  exactly — 1057, 47, 22, 114, 114, 104, 67, and `rest` back to ten.
* **P2 HIT, exactly.** `calls` +4, `nonconstant_programs` +1,
  `unresolved_args` +0, `module_calls` +0, `stmt_node_args` +0.
* **P3 MISS — and it is the round's finding.** I predicted the new row would
  be string-building and `rest` unchanged. It is `attribute`; `building` +0
  and `rest` 10 → 11. I predicted it because that is what five of the six
  previous corpus additions did, which is a base rate, not a mechanism —
  round 493's own P10 miss ("I predicted a RATE from a MECHANISM") one round
  later, from the other direction. Had I been right, four of the five reds
  would have been pure size and this round would have been a bump.
* **P4 HIT.** The compensating move is real and is now a test.
* **P5 HIT.** Nothing could print per-file; the loop discarded it.
* **P6 MISS.** I predicted greening the five nodes takes exactly 6 numeric
  literals. It takes **8** (1057; 114 in three tests; 104; and 129 → 138,
  355 → 373) plus an eleventh entry in the class list. I counted the
  assertions that were FAILING and forgot that greening them makes two more
  assertions reachable — which is the shadowing, in my own arithmetic about
  the shadowing.
* **P7 MISS.** `programs` is **873**; I banked [830, 860]. The floor in the
  test (`>= 829`) is round 474's and I anchored on it.
* **P8 HIT.** No checker in this repo reports the stale test NAME. Verified
  by running every one of them and grepping their output for the string:
  `verb_audit` (30 findings, none), `claim_check` (344 paths, 0 stale),
  `xref_check` (5 dangling, neither about it), `selfdesc_check` (1 error,
  round 493's), `specreg audit` (0 errors), `polarity audit`, `reprsweep
  --inputs`. The reason is structural rather than accidental: every
  count-claim checker in this tree reads PROSE — markdown, docstrings, JSON
  string fields — and a test's `def` name is in none of those scopes. J005's
  known recall gap (round 435 item 2) is about a count claim whose noun is a
  per-element FIELD; this is a count claim whose noun is an IDENTIFIER, which
  is a second gap nobody has named.
* **P9 MISS.** `git log -- tests/test_testcorpus_census.py` is **10**
  commits, not ≥ 14. The file is edited once per corpus addition, not more.
* **P10 HIT, and stronger than banked.** I predicted 0 residual rows from my
  own new test file. It contributes **0 to every counter** — it defines no
  runner and never calls `Interpreter().run`, so the census totals did not
  move for it at all, and the ledger's totals are unchanged from HEAD's.

---

## 5. Honest failures and things left open

* **I broke the serialisation rule twice**, on a box whose `nproc` is 1 —
  round 434's mistake and round 493's, committed again.
  1. The tree was edited under the running fast tier. It was launched after
     the census work and before the SPEC.md / research-state.md / registry
     edits, and `test_v22.py::test_research_state_track_c_names_the_same_
     version_as_spec_md` reads both of those at test time, so its pass in
     that run cannot be attributed to either state. **The settled-tree
     re-run is the number to quote: `196 passed in 33.58 s`**, solo, over
     `test_v22.py`, both census files, `test_depthcensus.py` and
     `test_testcorpus_suite_census.py`.
  2. `corpus_check.py` was then launched while that tier was still running.
     Its `unit_tests 234.00s` is therefore a two-way contended number and
     must not be quoted as a runtime, and neither must the tier's own
     **2841 passed, 3 skipped, 116 deselected in 637.90 s, exit 0**. Both
     results are reported here as what they are: correct verdicts at
     uncertain cost.
* **The stale test NAME was not fixed.** The node still says "seven rows in
  three shapes" and guards eleven rows in seven classes. It is kept because
  it is cited by a sibling's docstring and by
  `harness/crosstrack-registry.json`, and round 474 set the precedent for
  keeping a stale name so its citations keep landing. A count in a test's
  NAME is the same defect one level up as a count in its assertion, and this
  round recorded it rather than renaming a node mid-episode.
* **The gate is one node deep.** `_count_asserts` is applied to exactly one
  function, named by a constant. Every other shape assertion in this tree —
  `test_polarity.py`'s registries, `reprsweep.py`'s manifests — is unswept,
  and the same shadow could exist in any of them. Nothing here measured that.
* **`dup_cross_file` attribution is order-dependent** and documented rather
  than fixed. A file that duplicates an earlier file's program is charged the
  drop; reversing `sorted()` would move the charge. It does not affect any
  total.
* **The ledger is a second place the numbers live.** It is regenerable in one
  command and checked against the live harvest in two directions, which is
  the best this round could do, but it is not zero cost and should not be
  described as if it were.

---

## 6. Test evidence

All commands run from `~/agi-research-nuc-llm` unless shown otherwise.

```
# the five red nodes, REPRODUCED before anything was touched
$ cd languages/whence && python3 -m pytest -c pytest.ini -q -m "not whence_slow" \
      tests/test_testcorpus_census.py
5 failed, 79 passed in 20.19s

# after the round — census + the new suite, solo
97 passed in 27.45s

# the settled-tree re-run, solo, over everything this round touched or that
# reads a file this round edited
$ python3 -m pytest -c pytest.ini -q -m "not whence_slow" -p no:cacheprovider \
      tests/test_v22.py tests/test_testcorpus_census.py \
      tests/test_testcorpus_contributions.py tests/test_depthcensus.py \
      tests/test_testcorpus_suite_census.py
196 passed, 16 deselected in 33.58s

# the whole whence fast tier (CONTENDED — see §5)
$ ./run_tests_fast.sh
2841 passed, 3 skipped, 116 deselected in 637.90s (0:10:37)   [exit 0]

# registries and pins, after the round
$ python3 harness/wiring_audit.py check
wiring-audit: 139 entry point(s), 119 in closure, 0 error(s), 0 warning(s)
$ python3 harness/viapin.py audit
via-pins: 116 pin(s), 35 held, 0 drifted, 0 lost, 0 absent, 81 unpinned
$ cd languages/whence && python3 specreg.py audit
specreg: 51 registry entr(ies), 17 prose section(s), 76 version heading(s), next free is 65
specreg: 66 version level(s), highest v0.50; header says v0.50
specreg: 0 error(s), 4 warning(s)

# the round's own obligations to the skills corpus
$ python3 skills/skill-authoring/scripts/corpus_check.py --only skill_lint
skill-lint: 106 skill(s), 0 error(s), 7 warning(s)        # +1 skill, no error
$ python3 skills/skill-authoring/scripts/corpus_check.py --only case_coverage
case-coverage: 106 skill(s), 450 case(s) (80 negative)    # +4 cases, no P001
$ python3 skills/skill-authoring/scripts/corpus_check.py --only carryforward
carryforward: 170 bank(s), 165 scored, 2 unscored, 3 error(s), 32 warning(s)
                                            # 4 errors -> 3; this round's bank
$ python3 skills/skill-authoring/scripts/corpus_check.py --only xref_check
xref_check: 5 dangling (2 NEW, 3 pre-acknowledged)        # UNCHANGED, none mine
$ python3 skills/skill-authoring/scripts/corpus_check.py --only selfdesc_check
selfdesc-check: 837 prose field(s), 1 error(s)   # 836 -> 837, error is r493's
```

**What the round left red and why.** `redattrib audit` reports one R001
(`corpus_check.py::selfdesc_check` went red in round 493's log with no
registry entry) — harness(A)'s registry, harness(A)'s declaration, and round
493 set that precedent explicitly. The J004 behind it is one prose field in
`state/prediction-bank-ledger.json[banks.493.note]` citing the path round 493
`git mv`d away from; that note is a note ABOUT the move, so it wants an
acknowledgement rather than an edit, and rewriting it would erase the
evidence. `carryforward`'s three remaining K001s are rounds 490, 491 and 492's
unregistered banks. None of the four is this round's, and none was touched.

**Registry edits made, and their size.** `harness/crosstrack-registry.json`:
the five census entries' `why` fields corrected in place — appended, not
rewritten, with `indent=2` matched against the file's own encoding —
**5 changed, 5 inserted**. `skills/trigger-cases.json`: `indent=1,
ensure_ascii=True`, **32 inserted, 0 changed**.
`state/prediction-bank-ledger.json`: **9 inserted, 0 changed**. The reformat
hazard this program paid twice in round 493 (42 lines, then 1 027) did not
recur, because each file's own encoding was measured by round-tripping it
before anything was written.

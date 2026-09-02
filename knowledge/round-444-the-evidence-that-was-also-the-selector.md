# Round 444 (language C) — the evidence that was also the selector

**Target.** Round 440's next-step 4 ("whoever re-makes the census…"), round
441's addendum in `state/known-standing-dirty-paths.json`, and the one RED
check the driver has been logging since round 441:

```
[2026-09-02 02:44:55] round 443: whence-health-check FAIL — 1 failed, 2208 passed,
  3 skipped, 95 deselected in 799.14s — tests/test_field_corpus_selector.py::test_the_live_tree_has_no_drift
```

A fifteenth machine-written Whence program, `examples/agi_buy_and_hold.lang`,
arrived from the Hermes gateway at 2026-09-01 23:12:22 UTC. The census that
declares the field corpus names fourteen. That is the whole of the visible
defect and it is not the finding.

**The finding in one sentence.** `state/whence/round-384/field-names.json` had
been answering two questions with **opposite freshness requirements** —
*which bytes attested `println`?* (must be FROZEN; it is the reason each key
of `whence/foreign.py`'s `FOREIGN_NAMES` is allowed to exist) and *which files
ARE the field corpus?* (must be LIVE; it is the subject set of every
corpus-derived test) — and the fifteenth program is the first event that
cannot satisfy both, because it belongs in the subject set and **attests
nothing**.

Round 410 had already written this defect's name, about a different pair, in
`curecheck.py`'s own comments: *"being three copies was not the defect —
answering two different questions with one answer was."* It was true of
`_corpus_unchanged()` in round 410 and it was true of the census in the same
file at the same moment; nobody looked one function up.

---

## 1. Why "just add the fifteenth name" is editing evidence

`whence/foreign.py`'s entry rule, in the module's own words:

> A name enters only if: **(a)** the FROZEN field census
> `state/whence/round-384/field-names.json` attests it — the count is in the
> comment; or **(b)** a numbered SPEC decision rejects the construct it names.

`FOREIGN_NAMES["println"]` exists because *34 occurrences across 9 of 14
files*. `test_v32.py::test_the_frozen_census_says_what_it_censused` pins
`round == 384`, `n_files == 14`, `counts["println"] == 34`,
`len(files["println"]) == 9`. Bumping `n_files` to 15 to fix a selector
would make the evidence file a file that gets edited when the corpus
changes — which is exactly what a *frozen* census is defined not to be, in
its own `_comment`:

> Frozen on purpose — the source files are owned by another system and can
> change or vanish at any time, so a test that re-derived this census would
> be pinning a live file.

So the census cannot move. And the selector *must*, or `field_programs()`
returns a subject set that is missing a member and every "for all" assertion
over it is quietly about the wrong population — round 395's exact lesson,
one level up.

## 2. The census had no producer, and its reason for that had expired

```
$ git stash && grep -rn "unbound_identifier_counts" --include=*.py .     # at 34ac527, before this round
tests/test_v32.py:201    tests/test_v32.py:221    tests/test_v33.py:214
```

Three read sites in two files. **No writer.** (At HEAD the same grep also
hits `curecheck.py`, which is the point of the round; the reading above is
reproducible against commit `34ac527` or earlier.) For sixty rounds the numbers behind every
rule-(a) entry in `FOREIGN_NAMES` could be quoted and could not be
re-derived, and round 440's instruction "re-make the census" had no command
behind it.

Round 384's reason for that was sound *when it was written* — "a test that
re-derived this census would be pinning a live file". **It expired fifteen
rounds later.** Round 410 built `curecheck.field_corpus_skip_reason`, which
is precisely the machine for reading a live foreign file safely: skip when
it is absent, skip when it was rewritten and say which file, run and go RED
on drift, never edit the number to be quiet. From round 410 the generator
was safe to have. Nobody re-read the reason after its premise changed —
the same shape as round 443's item 1 (a carried claim nobody re-derives),
except the carried thing here is an *absence*.

`curecheck.unbound_identifier_census(paths)` is that generator, and the
acceptance test is exact reproduction rather than agreement:

```
tests/test_field_corpus_selector.py::test_the_reconstructed_census_reproduces_round_384_exactly
    got["unbound_identifier_counts"] == frozen["unbound_identifier_counts"]   # 80 keys
    got["unbound_identifier_files"]  == frozen["unbound_identifier_files"]
    got["file_md5"] == frozen["file_md5"]   and   n_files == 14
```

It reproduced on the first run, with no tuning. That matters for what it
licenses: a generator that merely *agreed on `println`* would also have
been produced by a rule that mis-binds `fn` parameters, and the census would
have silently become a different measurement the next time anyone re-took it.

The rule the data forced, and it is a language fact rather than a coding
choice: **binding is lexical and file-wide, not scoped.** A use above its
own `let` still counts as bound. Ten of the fifteen programs do not parse,
so there is no AST and no scope to ask — the question the census asks is
"does this program mean a *Whence* name here", not "is this program
well-scoped". The three binder shapes are `let NAME`, `fn NAME(params)` and
anonymous `fn(params)`, and a parameter is a NAME whose predecessor token is
`(` or `,` — which is what correctly leaves a type annotation's `T` in
`fn f(p: T)` foreign.

## 3. The split

| | `state/whence/round-384/field-names.json` | `state/whence/round-444/field-roster.json` |
|---|---|---|
| answers | which bytes attested which name | which files are the corpus |
| freshness | FROZEN — `FOREIGN_NAMES` cites it by path | LIVE — re-declarable by any round |
| read by | `curecheck.frozen_census()`, `test_v32.py` | `curecheck._roster_md5()` → `field_roster_names()` → `field_programs()` |
| n_files | 14, forever | 15 today |

`field_corpus_changed()`'s md5 comparison moved to the roster — "have these
bytes been rewritten since we declared them" is a membership question. The
md5s the two files share are identical, so this changed no verdict; it
changed which file a future re-declaration is allowed to touch.

The seam gets a test rather than a paragraph.
`test_a_roster_member_outside_the_frozen_census_attests_nothing_new` runs
the generator over every roster member the census never saw and fails if it
produces an unbound identifier the census does not already name. Today it
holds because the answer is the empty set. When a sixteenth program reaches
for `foreach`, it goes red **and names the word**, and the response is a new
census captured deliberately and cited by round number — one command now.

## 4. The order of the two edits is the whole of round 441's rule

`field_corpus_drift()` computes `untracked - declared` from
`git ls-files --others --exclude-standard examples`. There are therefore two
ways to turn the red test green, and only one of them is a fact:

```
before:                                       (['agi_buy_and_hold.lang'], [])
after DECLARING it in the roster:             ([], [])      <- measured, no .gitignore line yet
after ALSO adding the .gitignore line:        ([], [])
```

Round 441 measured the second path and refused to take it ("that is a live
finding silenced, not attributed"). This round declared first and ignored
second, in one commit, and the middle line above is the evidence that the
green came from the declaration. The ignore line still earns its place —
it is what stops the next `git add -A` re-tracking the file, round 402's
reason — and the detector keeps working for the sixteenth program, which
will be neither declared nor ignored and will therefore be named.

## 5. The corpus, measured whole for the first time since round 384

`curecheck.survey` + the new generator + `run.py`, over all fifteen
(`python3 run.py` per parsing program; the "run" column's parenthetical is
its last stdout line):

| program | in census | parses | run rc | distinct unbound names |
|---|---|---|---|---|
| `agi_buy_and_hold.lang` | **no (round 444)** | yes | 0 (`checks: 4 passed, 0 failed`) | 0 |
| `cognitive_verifier.lang` | yes | no | — | 0 |
| `cognitive_verifier_v2.lang` | yes | no | — | 0 |
| `cognitive_verifier_v3.lang` | yes | no | — | 1 |
| `expense_tracker.lang` | yes | yes | 0 (`dropped: 1 miss …`) | 0 |
| `mini_agi_guardian.lang` | yes | yes | 0 (`dropped: 4 miss …`) | 2 |
| `nano_reasoner.lang` | yes | no | — | 3 |
| `prod_demo_v1.lang` | yes | no | — | 17 |
| `prod_demo_v3.lang` | yes | no | — | 26 |
| `prod_demo_v4.lang` | yes | no | — | 4 |
| `prod_demo_v5.lang` | yes | no | — | 7 |
| `prod_showcase_final.lang` | yes | yes | 0 (`dropped: 6 miss …`) | 2 |
| `test_simple.lang` | yes | yes | 0 (`Result: 150`) | 0 |
| `whenceguard_auditor.lang` | yes | no | — | 13 |
| `whenceguard_v2.lang` | yes | no | — | 39 |

**5 of 15 parse. 10 do not — the same 10, and the published number did not
move when the denominator did.** That is the whole reason a corpus change
has to be visible: `test_ten_field_programs_still_fail_to_parse` would have
read identically if the fifteenth had failed to parse *and* one of the
fourteen had started to.

Distinct unbound names over 15 = **80**. Over the frozen 14 = **80**. That
equality is the licence for the whole split.

### 5.1 What the fifteenth program actually is

```
program                        check=  println=  lines=
agi_buy_and_hold.lang          4       0         85
…every other one of the 14     0       0-5       2-75
```

`agi_buy_and_hold.lang` is the **only program in the field corpus that uses
Whence's `check` at all**, it uses four, and all four pass. It is the
largest program in the corpus that parses, by 37 lines. It has no `println`,
where 10 of the other 14 do.

The claim it is tempting to make here — "the first gateway program that runs
clean" — is **false and I made it before measuring**: `test_simple.lang` also
exits 0 with nothing dropped, and it is two lines long. The true statement is
narrower and more interesting: of the five programs that parse, three run
only by DISCARDING misses (`dropped: 1`, `4`, `6` — round 384's recorder
saying so on stdout while the exit code stays 0), and the two that drop
nothing are a 2-line arithmetic demo and this one.

That is a fact about the corpus's producer, and it is a fact this round got
for free from a measurement it took for a different reason. It is also a
standing caution about the exit contract: `rc=0` is not "the program worked"
for three of the five, and `--strict-miss` (round 384) is the flag that says
so.

## 6. Predictions, scored

`state/whence/round-444/PREDICTIONS.md`, written before any measurement.

| # | prediction | result |
|---|---|---|
| P1 | reconstructed extractor reproduces `unbound_identifier_counts` exactly | **HIT** — 80 keys, all counts, first run, no tuning |
| P2 | …and `unbound_identifier_files` exactly | **HIT** (and `file_md5` too, which I did not predict) |
| P3 | the fifteenth contributes **zero** new unbound identifiers | **HIT** — `{}` |
| P4 | so the census payload is unchanged | **HIT** — 80 = 80 |
| P5 | `10 fail`, `broken=10`, `applied=4`, `stalled_on_first=8` all unchanged | **HIT** — all four |
| P6 | drift `(['agi_buy_and_hold.lang'], [])` → `([], [])` on declaration | **HIT**, and measured before the `.gitignore` line existed |
| P7 | `builtins_at_capture` still equals the live builtin set | **HIT** — 37 names, identical |
| P8 | the tier goes green and nothing else breaks | **HIT** — `2212 passed, 3 skipped, 95 deselected in 236.70s`, rc 0 |

**8 HIT, 0 MISS of 8.** And that is a **warning about this bank, not a boast** — round
443's next-step 2 said exactly this after scoring 11 of 12. Seven of these
eight were predictions about whether an instrument I was about to build
would agree with a file I had already read; only P3 was about the world. The
one band that could have missed and did not is P1, and it is the one worth
keeping: an extractor that got `println` right and `Miss` wrong would have
been indistinguishable from a correct one under any weaker assertion.

The prediction I did NOT write down and should have is the one that turned
out false in §5.1. I formed "it is the first that runs clean" while reading
the file, put it in a test docstring, and only then ran the other four.
Unbanked, it would have shipped.
## 7. Tests and checks

```
$ bash languages/whence/run_tests_fast.sh          # .venv/bin/python3
2218 passed, 3 skipped, 95 deselected in 237.14s (0:03:57)      rc=0
```

Before this round the same command was `1 failed, 2208 passed, 3 skipped,
95 deselected` (driver log, rounds 442 and 443). The arithmetic, because a
count that only goes up proves nothing: **2208 + 1 red now green = 2209**;
+3 for §3's split tests = 2212; +6 for §9's `test_critical_mission_claims.py`
= **2218**. The intermediate 2212 was measured before §9 existed, and it was
measured TWICE — `.venv/bin/python3` **236.70 s** and `/usr/bin/python3`
**231.80 s**, identical pass counts. That second run is not ceremony: the
driver's health checks call bare `python3` while a round's own commands
resolve to the `.venv` (round 442's finding, still open as its item 2), so
"passes for me" is not evidence about what the driver will log.

Every figure above is from a run with nothing else on this 1-core box.

The three new tests, all in `tests/test_field_corpus_selector.py`:

| test | what fails it |
|---|---|
| `test_the_reconstructed_census_reproduces_round_384_exactly` | any change to the generator's binder rule, or to the fourteen files (it skips on a rewrite and says which file) |
| `test_a_roster_member_outside_the_frozen_census_attests_nothing_new` | a future gateway program that reaches for a foreign idiom — and it names the word |
| `test_the_generator_binds_the_three_things_whence_binds` | a binder-rule regression, in a fresh checkout with no corpus at all |

Renamed/retargeted, not deleted: `test_the_roster_declares_fifteen_names_and_the_census_still_declares_14`
asserts BOTH numbers and that the roster is a superset, which is the split
as a single assertion. `test_v32.py::test_the_frozen_census_says_what_it_censused`
is **untouched** and still asserts `round == 384`, `n_files == 14`,
`counts["println"] == 34`. If that test had needed an edit, the split would
not have happened.

`skills/run_checks_fast.sh`: `10 checker(s), 0 error(s), 7 warning(s)` after
the round-444 row landed in `state/prediction-bank-ledger.json`. It read
`2 error(s)` first — both were one cause, `carryforward K001` (a bank on disk
with no ledger entry) surfacing once directly and once through
`test_corpus_check.py::test_live_corpus_is_clean`. Worth recording because
the check found MY omission within the same round, which is what it is for.

## 8. What this round did not do

- **It did not re-take the census.** The measurement says it did not need to.
  A round that adds a member which DOES attest something must take a new one
  and cite it by round number; `curecheck.unbound_identifier_census` is now
  the command, and the seam test is what will demand it.
- **It did not look at the other frozen artefacts in `state/whence/`** for
  the same double duty. `round-422/host-pins-plus.json`, the repointed
  registries, `round-384/field-names.json` — only the last was examined.
  Round 434's next-step 6 already asked for a sweep comparing each artefact
  against the prose that describes it; this round is a positive instance of
  that sweep finding something, on one file, by accident.
- **It did not touch `FOREIGN_NAMES` itself.** The entry rule is unchanged,
  no key was added or removed, and the evidence behind every key is the same
  bytes it was in round 384. That is deliberate: the round's claim is that
  membership moved and evidence did not, and adding an entry would have made
  that claim untestable.
- **It did not re-derive the harness-side carried items.** Per round 443's
  item 1 the carry-check grep was run first —
  `grep -ln "test_swe_campaign.py\[light\]\|748\|requirements.txt" knowledge/round-44[0-3]*.md`
  — and the only hits are the rounds that CARRIED them, not a round that
  closed one. They are carried below with that stated.
## 9. CLAUDE.md's CRITICAL MISSION, executed rather than escalated

`CLAUDE.md` carries a block headed **🔴 CRITICAL MISSION: PRODUCTION FIX
(Round ~350 Focus)** telling every round to prioritise two Whence defects.
Every next-steps list from round ~350 to round 443 re-escalated it to the
operator as "a one-line deletion" — **twenty-three times**. It is a claim
about *this repo's own interpreter*, and in twenty-three rounds nobody ran
the four lines that answer it.

```
$ python3 run.py /tmp/fold_probe.lang
inline lambda: 10
named fn:      10
fold(f, xs, acc): miss: fold needs a list, got 0 (arguments fit fold(fn, acc, xs)) (line 12)
✓ inline lambda folds
✓ named fn folds
checks: 2 passed, 0 failed
```

**Claim 1 — "`fold()` returns `Miss` instead of calculated values when using
inline lambdas or external functions" — is FALSE**, in both of the forms it
names. `fold` returns a miss when the ARGUMENTS ARE IN THE WRONG ORDER, and
the miss names the signature that would have worked. That is decision 32 (an
error that can name the fix, names it) working, not a regression.

And the true statement next to it explains the false one. Two field-corpus
programs hit exactly this miss:

```
expense_tracker.lang     line 35 (let final_total, from line 20)
  — fold needs a list, got <fn add_item> (arguments fit fold(fn, acc, xs))
prod_showcase_final.lang line 42 (let final_total, from line 22)
  — fold needs a list, got <fn add_items> (arguments fit fold(fn, acc, xs))
```

Both exit **0** while printing that. So the most likely origin of the block
is a reader who ran a gateway program, saw `Miss` in the output, and read a
diagnosed argument-order error as an interpreter fault — which is also §5.1's
point about `rc=0` not meaning "it worked".

**Claim 2 — "document [the braced-block rule] strictly" — asks for something
that already exists, twice.** `SPEC.md` has a section `### Blocks are always
braced`, and `whence/parser.py`'s `_BRACE_HINT` makes the parse error itself
name the spelling: ``blocks are always braced: `if c { a } else { b }` ``.
The block also dates itself to "v0.19"; `SPEC.md`'s newest numbered section
is **v0.41**.

`tests/test_critical_mission_claims.py` (6 tests) pins all of this, including
the two corpus programs, and is written to **expire correctly**: it reads
`CLAUDE.md` and skips if the block is gone. Deleting the block stays the
operator's call — this round does not touch it — but the escalation is no
longer "unactionable", it is "refuted, with the refutation in the fast tier".

### 9.1 Why twenty-three rounds did not do this

The block says *"prioritize debugging the Whence interpreter core"*, which
sounds like a large job, and it names a version (`v0.19`) that is 22 numbered
SPEC sections old. Both signals point at "stale, and expensive to check".
Neither is a reason, and the actual cost was one `.lang` file. The pattern is
this round's §2 in a different register: an item carried as *blocked on
someone else* was never re-derived, and re-deriving it took less time than
one round spent re-writing the sentence that carries it.

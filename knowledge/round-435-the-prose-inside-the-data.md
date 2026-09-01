# Round 435 (skills B) — the prose inside the data

Track B. Two next-step items were open against skills(B): item 6 (run round
434's artefact-vs-prose comparison against the rest of `state/whence/`) and
item 9 (round 433's baseline rule belongs in `prediction-banking`). Both are
closed. Before either could start, the round found something neither item
mentions: **the corpus health check has been ERROR-red for four consecutive
rounds**, its error count growing by one per round, and this was the first
skills(B) round since it went red.

## 0. The finding in one paragraph

Every checker this program runs divides the tree by FILE TYPE. `xref_check`
reads the markdown, Python, `.lang` and shell; `claim_check` reads SKILL.md
Verification blocks; `state_claim_check` reads one block of one markdown file;
`carryforward_check` reads a ledger's STRUCTURE. The constant that says so is
one line:

```python
xref_check.py:126   SCANNED_EXTS = (".md", ".py", ".lang", ".sh")
```

`.json` is not in it. So for ninety rounds nothing has read the **~26 000
characters of present-tense assertion that this repo's data files make about
themselves** — the `_comment` at the top of every registry, the `_` at the top
of every pin file. That prose is not a comment. It is the file's
specification, its provenance, its usage note and, in one case, its acceptance
criterion; it is the only description any human reads; and nothing re-derives
it. Round 435 built `selfdesc_check.py`, swept 26 artefacts out of 607 JSON
files, and found four defects on the first run. The most instructive one had
been **contradicted by an assertion in this same tree since round 423** — the
correction landed in the test and never reached the sentence 590 lines above
it in the same file.

## 1. The red that was there before the round started

`logs/driver.log`, rounds 431-434, `skills-check`:

| round | verdict | carryforward | unit_tests |
| --- | --- | --- | --- |
| 430 | PASS | — | — |
| 431 | ERROR (a checker could not run) | ERROR K001 ×1 | TIMEOUT 600 s |
| 432 | FAIL | ERROR K001 ×2 | ERROR P001, 4 failed |
| 433 | FAIL | ERROR K001 ×3 | ERROR P001, 4 failed |
| 434 | FAIL | ERROR K001 ×4 | ERROR P001, 4 failed |

The K001 column is the shape: **one new error per round, and the same one**.
Every round banks predictions; `carryforward_check`'s K001 says a bank on disk
with no entry in `state/prediction-bank-ledger.json` is an error; and rounds
431, 432, 433 and 434 each scored their bank properly in their own knowledge
file and then never wrote the ledger line. Nothing was missing except
bookkeeping — all four scorings exist and are quotable — but the check cannot
know that, which is exactly what it is for.

Round 429 measured the cost of a checker nobody watches as *latency bounded by
the rotation, up to six rounds*. This is that number, realised: four rounds,
closed by the next skills(B) round because there was no earlier one.

### 1a. Three root causes, not four failures (round 429's rule, applied)

The tier reported four red tests. Classified before eliminating:

```
test_carryforward_check.py::test_the_live_ledger_accounts_for_every_bank_on_disk   ROOT (K001 ×4)
test_case_coverage.py::test_live_corpus_has_no_coverage_errors                     ROOT (P001 ×3)
test_claim_check.py::test_only_the_known_prose_only_skills_parse_to_zero_commands   ROOT
test_corpus_check.py::test_live_corpus_is_clean                                     DERIVED (asserts the whole run is PASS)
```

- **K001 ×4** — banks 431-434 registered, each `scored` with a quote K002
  re-reads from the round's own knowledge file. Round 433's has no aggregate
  tally (it scores A1-A10 inline at the point of each measurement), so its
  entry quotes a section heading and records `A8` as a `remainder`: that
  prediction was banked and deliberately not tested, and round 433 says so.
- **P001 ×3** — `evidence-unit-smaller-than-the-item` (r433),
  `running-minimum-not-endpoint` (r431) and `unknown-names-its-residual`
  (r432) had **zero** positive cases in `skills/trigger-cases.json`. Three
  each written, `near`/`mid`/`far`, in the corpus's own idiom.
- **claim_check** — two of those same three skills had a `## Verification`
  section containing no runnable command, so `commands_for()` returned an
  empty list and the "prose-only" allowlist no longer matched the corpus. The
  fix is not to widen the allowlist: both got real fenced commands.
  `unknown-names-its-residual` now runs the two counterexample programs round
  432 banked (`checks: 4 passed, 0 failed` from each) and the `precondition`
  verb that re-derives its residual line;
  `running-minimum-not-endpoint` now runs `copyparity.py escapes` and the
  23-test file that pins the `(net, floor)` pair.

All three root causes are the same event wearing different clothes: **a
non-skills round authored a skill and could not pay its corpus obligations.**
`state/known-unprobed-skills.json` exists precisely so that debt can be
declared, and none of the three rounds wrote an entry — because the entry
silences P004 (a warning) and says nothing about P001 (an error).

## 2. Item 6: the comparison, run by a machine

`skills/skill-authoring/scripts/selfdesc_check.py`. 26 artefacts carrying a
top-level prose field of ≥40 chars, out of 607 `.json` files (252 are JSONL
streams — `logs/round-*.json` — classified as logs rather than lumped into an
"unparseable" number that reads as breakage).

The claim shapes were **derived from that prose by reading all of it once**,
not invented:

| code | sev | shape |
| --- | --- | --- |
| J001 | ERROR | `read by <path>` naming a path that does not exist |
| J002 | ERROR | the artefact's basename appears in NO source file — nothing reads it |
| J003 | WARN | the named reader exists and never mentions the artefact |
| J004 | ERROR | a repo-relative path token that does not resolve (X004's exact semantics, reused by import) |
| J005 | ERROR | a count whose noun names one of the artefact's own collections |
| J006 | ERROR | an absence claim over an id the artefact contains |
| J007 | INFO | a count/absence claim carrying its own `as of round N` |
| J008 | ERROR | `regenerate, do not hand-edit` with no producer in the tree |
| J009 | ERROR | an acknowledgement matching nothing (dead) or whose pin expired |
| J010 | ERROR | `<sibling>.json with N <field>s changed`, diffed against the sibling |
| J011 | WARN | an executable acceptance criterion no test names |

### 2.1 The four findings

**J010 — the count that was corrected twelve rounds ago in the same file.**
`state/whence/round-422/host-pins-plus-repointed.json`'s `_` said
*"`host-pins-plus.json` with **nineteen** guardian labels repointed and
NOTHING ELSE changed"*. Measured: **20**, and the file says so itself —
`repointed_from` is present on exactly twenty pins. It is not a close call and
it was not unknown:

```python
# languages/whence/tests/test_checkpin.py, since round 423
    # Round 422 repointed 20 guardians, not the 19 its own in-flight pin
    # update said; the twentieth is CP22p2 ...
    assert moved == 20, moved
```

That assertion is 590 lines **below** a comment in the same file which read
*"the repointed copy differs from the as-written copy in nineteen guardian
LABELS and nothing else"*. Green every run, for twelve rounds, with the
correction sitting inside it.

Three `nineteen`s in the tree, and **only one is wrong** — which is why a
blind grep-and-replace would have made things worse. Measured:

```
distinct mechanisms in host-pins-plus.json (directional)      20
...of those, matching a check-pins.json mechanism verbatim    19   <- correct
guardian labels differing between plus and repointed          20   <- the prose said 19
```

`test_v23.py:458` and `test_examples.py:169` say "nineteen rules in the `+`
direction" and are RIGHT: 19 of the 20 `+` mechanisms match a `-` mechanism
word-for-word, the twentieth (`a shape cannot reference itself`) differing only
by the parenthetical `(SAME edit as CP20)`. Both were left alone.

**J006 — the header that denied a pin eleven entries below it.**
`host-pins-plus.json`'s `_` said *"Round 414's CP01/CP02/CP05 are LATERAL …
and have no mirror"*. `CP05p` is a pin in that file, and its own `why` field is
a paragraph arguing the opposite:

> Round 420 marked CP05 LATERAL (`~`) because its minus edit swaps one
> rendering for another of the same size. Restated as a quantity — *the
> newline is DESCRIBED, not spelled* — the rule does have an order … So one of
> the three lateral pins was not lateral.

CP01 and CP02 genuinely have no mirror, and the same sentence says so
correctly. **One clause, three ids, one right answer** — which is what makes
this the fixture for the rule: the check is a STEM lookup against ids derived
from the artefact, `CP05p` starts with `CP05`, and nothing starts with `CP01`
or `CP02`. Both halves of the discrimination come out of one sentence.

**J008 — an instruction naming a producer that cannot exist.**
`state/whence/round-420/check-pins-dir.json` said *"Derived from
…check-pins.json; regenerate, do not hand-edit"* for fifteen rounds. Nothing
in the tree has ever regenerated it, and nothing can: the file is round 414's
registry plus a `dir` column, and `dir` is a per-pin JUDGEMENT that is in no
derivation. Verified:

```
ids equal                                   True (23)
every non-`dir` field byte-identical        22 of 22 fields, all 23 pins
`dir` present                               22 pins;  absent on NC01 (the control)
```

The repair is not a generator. The instruction was replaced with the part that
IS re-derivable, and
`test_checkpin.py::test_the_dir_registry_is_round_414s_registry_plus_one_authored_column`
now re-derives it.

**J005 — two nouns spelled the same.**
`state/swe/round-431/evaporating-test-kills-nothing.json` says *"it has no
baseline, no score and no denominator over a file's mutation sites"*, and the
artefact has a top-level `baseline` key holding the worktree's green baseline.
The sentence is true in its own frame (`scoreaudit.py`'s campaign-discovery
predicate) and false in the checker's. This is the one finding **not** fixed:
it is round 431's frozen record of a measurement, SWE-loop(D) owns it, and the
honest repair renames either the key or the sentence. Content-pinned in
`state/known-selfdesc-drift.json` on the sha256 of the prose, so editing the
sentence expires the acknowledgement rather than muting the file.

### 2.2 The claim that is false, and has been for nine rounds

`host-pins-plus-repointed.json` carries the corpus's only executable
self-claim:

> `polarity.py audit` over this file must report 0 MISPOINTED, which is the
> non-circular half — pointing a pin at whatever happened to go red would
> guarantee `guarded` and measure nothing.

Run at HEAD:

```
audit: examples/self_host.lang — 22 directional pin(s), 5 MISPOINTED, 0 unlocatable, 0 precondition-broken
```

And `state/whence/round-426/audit-repointed-r426.txt`, four directories away,
records the identical line. The acceptance criterion has been violated since at
least round 426 and the violation was saved to disk beside it.

**This is also where the checker was nearly wrong.** J011's first draft said
"nothing in the tree runs it". False: round 426 wrote
`test_the_repointed_registry_fails_its_own_acceptance_criterion`, in the
whence slow tier, which asserts the exact five ids and exists to "hold the
failure open rather than letting it be inherited again as a green result". A
checker that reported this as unwatched would have been crying wolf at the one
place the discipline worked. J011 now fires only when no `test_*.py` names the
artefact, and reports `watched/total must-claims` as a coverage token. Today:
`1/1`.

### 2.3 What the checker got wrong first, and what fixed it

Three false positives on the first live run, each forcing a discriminator that
is now a named test:

| false positive | why it is false | discriminator |
| --- | --- | --- |
| "Five banks had been silently dropped" (ledger has 111) | counts a historical SUBSET | past tense anywhere in the sentence |
| "27 skills in the corpus" (`skills` map has 9) | counts a DIFFERENT container | a prepositional phrase right after the noun |
| "…present on exactly 20 pins" (registry has 23) — **my own correction, on its first draft** | partitive | `of` binding to the numeral |

The past-tense window is the interesting one. Written as a look-BEHIND it
suppressed nothing, because the corpus's instance opens with its numeral
("Five banks had been…") and the text before the count is the empty string.
Widening it to the whole sentence costs recall — a true count phrased in the
past is now dropped — and that loss is pinned as
`test_a_past_tense_true_count_is_dropped` rather than left to be discovered.

A fourth near-miss never fired and is the rule's real test:
`state/known-absent-paths.json` says *"Two kinds so far: (1) … (2) …"* over a
three-entry `paths` map. `kinds` names nothing in the artefact; `paths` does.
A count-checker that reports that is broken, not observant.

**And the fix that quoted the rot.** My first correction to the CP05 sentence
included the words it was correcting — a fresh absence clause, which re-tripped
J006 on the repaired file. Rewritten to *describe* the old sentence instead of
reproducing it. This is the blind spot `xref_check` already carries a standing
exemption for ("the checkers themselves quote the rot they detect"), met from
the other side.

## 3. What the machine could not see, and the honest denominator

`coverage 1/26 prose-fields`. **One** of 26 self-descriptions yields a
checkable claim today (the acknowledged J005); the other 25 are silent. That
number is on the summary line on purpose: "0 errors over 26 artefacts" must
not read as "26 artefacts verified". Claims like *"this is the third
acknowledgement registry in `state/`"*, *"THE DIRECTION IS FAIL-CLOSED"*,
*"a stale entry costs wall-clock; it cannot cost coverage"* are about MEANING
and are left alone.

Two further limits, stated rather than discovered later:

- **J005 cannot see a count whose noun is a per-element FIELD.** The
  `nineteen guardian labels` defect was found by hand-diffing after J005 came
  back silent, and only then did J010 exist. A checker written from
  imagination would not have had J010; a checker written from a hand
  comparison did.
- **The sweep is top-level fields only.** `known-unprobed-skills.json` alone
  carries twelve `_round_NNN_note` fields, all prose, none swept. Counted, not
  claimed as covered.

The summary line goes LAST, above nothing — round 417's rule, because
`corpus_check.run_one` keeps `lines[-1]`, and the first draft printed the
skipped-file accounting after the summary and was duly quoted by the
aggregator as `ok  skipped: 252 jsonl stream(s)…`.

## 4. Item 9: the baseline rule, banked into `prediction-banking`

Round 433's item 10 and research-state item 9. `prediction-banking/SKILL.md`
step 1 now carries:

> **Every BASELINE in the bank is re-derived at HEAD, with the command that
> produced it printed beside it.** … a stale one moves every verdict under it
> and does so invisibly.

with round 434's instance (its first re-derived baseline was already stale by
one round), a pitfall (*"a baseline quoted from the status file … more
dangerous than a re-quoted duration, because a duration miss shows up as a
miss while a stale baseline silently re-centres every band and the bank still
scores well"*), a checklist line, and a Verification command that counts the
baseline rows carrying a runnable command.

This round's own bank has a five-row baseline table, every row with its
command, and it paid immediately: the round-duration prior it quotes
(`median 21.6 min, p25-p75 11.5-35.1` over 238 recorded rounds, but **41.3 min
median over the last 20**) is the reason C5's band is 25-52 min and not the
14.1-minute skills(B) historical median.

## 5. Tests

| suite | before | after |
| --- | --- | --- |
| `skills/*/scripts` (the corpus tier) | 4 failed, 860 passed | **894 passed** |
| `corpus_check.py` aggregate | 9 checkers, 3 errors, 11 warnings | **10 checkers, 0 errors, 5 warnings** |
| whence fast tier | 2189 passed, 3 skipped, 91 deselected | **2190 passed, 3 skipped, 91 deselected** |
| `skill_lint --house --strict` | 75 skills, 0/0 | **76 skills, 0 errors, 0 warnings** |

31 tests added: 30 in `test_selfdesc_check.py`, 1 in `test_checkpin.py`. The
tier arithmetic is exact — 860 + 4 + 30 = 894 — so nothing else moved.

`test_selfdesc_check.py` splits deliberately. Six of the eleven codes produce
NOTHING on the live corpus, so each gets a synthetic repo that makes it fire
AND a near-miss that keeps it quiet; a rule that has never fired is
indistinguishable from a rule that cannot. `TestLiveCorpus` asserts the
DISCRIMINATIONS by name rather than a total — the CP05 sentence must yield at
most one finding and it must not name CP01 or CP02 — because a count stays
green while two errors swap places.

## 6. Predictions, scored

`state/round-435-predictions.md`. **9 HIT, 2 PARTIAL, 6 MISS of 17 scored**, with C5
(wall clock) scored in `state/research-state.md` because it cannot be known
until the round ends, and three facts recorded as measured-before-banking
and deliberately not scored (F1-F3 in the bank).

| # | claim | verdict |
|---|---|---|
| A1 | 14-20 of 25 artefacts name a reader | **MISS (high)** — 13 of 26. Off by one at the bottom of the band, and the denominator moved because this round's own acknowledgement registry became the 26th artefact. |
| A2 | 0 named reader paths missing | HIT |
| A3 | 1-3 J003 (reader exists, never mentions the artefact) | **MISS (high)** — 0. Every "read by X" in this corpus is exact. I bet on indirection and there is none. |
| A4 | 1-4 unresolvable path tokens in the prose | **MISS (high)** — 0. I priced this off X004's 91/6504 corpus rate and bet above it because the prose had never been swept; the artefacts are better written than the markdown. |
| A5 | 0-2 unresolved symbol claims | HIT — 8 checked, 0 unresolved |
| A6 | 3-8 count claims found, 1-2 wrong | **PARTIAL** — 3 found (in band), 0 truly wrong (below band). All three were false positives or dated, which is why J005 needed three discriminators and why the "Two kinds" near-miss is the rule's real test. |
| A7 | 2-6 ERROR findings on the live corpus | HIT — 4 |
| B1 | "nineteen guardian labels" HOLDS | **MISS** — 20, and this miss is the round's headline |
| B2 | "must report 0 MISPOINTED" HOLDS | **MISS** — 5, and false since at least round 426 |
| B3 | "the five pins round 416 measured `shadowed`" HOLDS | HIT — same 5 ids, both directions |
| B4 | derivation holds; 0 producers exist | HIT, both clauses |
| B5 | the mirror claim misses on 2-5 pins | **MISS (high)** — 1 at string level, 0 semantically (CP21p's mechanism differs only by `(SAME edit as CP20)`). I predicted the `p2` pins would break it; they do not, because a second `+` mirrors the same `-`. |
| C1 | at least one new test wrong on first run | HIT — `test_J001` expected one code and got two, because a nonexistent reader is also a nonexistent path |
| C2 | at least one false positive forcing a discriminator | HIT — three |
| C3 | skill_lint 0/0 at 76 skills | HIT |
| C4 | the tier grows by exactly the tests added | HIT — 864 → 894 |
| C6 | corpus_check gains a ninth checker and reports 0 errors | **PARTIAL** — the second clause holds (`10 checker(s), 0 error(s), 5 warning(s)`, green for the first time since round 430; the warning count fell from 11 because this round's research-state edit also discharged the S005 carried-claim warning), the first is off by one: it is the TENTH. Scored PARTIAL rather than HIT because the count was in the sentence I wrote. |
| C5 | wall clock 25-52 min | scored in research-state |

**The miss pattern is one shape, and it is not optimism.** A1, A3, A4 and B5
are four bets that the corpus would be *worse* than it is, each priced off a
rate measured somewhere else (X004's path-rot rate, "indirection is how this
rots"). The two bets I made about specific sentences in specific files — B1
and B2 — are the two that found real defects, and both were HOLDS predictions
that failed. **The band-shaped predictions were wrong in the safe direction;
the named predictions were wrong in the useful one.** The rule that follows,
added to `prediction-banking` in spirit if not yet in text: when a bank can
name a specific artefact's specific sentence, predict THAT rather than a rate
over a population — a rate has nowhere to be surprising.

## 7. Debts declared, not paid

`state/known-unprobed-skills.json` gained **fourteen** entries, the largest
single batch it has taken, and this round paid none of them. A trigger probe
is a priced live-model run (~$0.05 each; `trigger_eval.py` is deliberately
never invoked from `corpus_check`), and this round had no operator
authorisation to spend. The map was EMPTIED by round 405 and has grown in
every round since without a skills(B) round paying a batch. Every entry names
`skills(B)` as owner and a `why`; `_round_435_note` records the growth rate
and the fact that three of the fourteen were P001 **errors** until this round
wrote their cases — registering them without the cases would have been a mute
button over an error, not a declared debt.

## 8. What a later round should do with this

1. **`polarity.py audit` reports 5 MISPOINTED against a registry that says 0.**
   Round 426 measured that the sightedness filter behind MISPOINTED discards 16
   of 93 checks that actually went red and calls CP03p a coverage gap on that
   basis. So the honest question is not "repoint five pins" — it is whether
   MISPOINTED is the right predicate at all. language(C).
2. **The J005 recall gap is real and named.** A count whose noun is a
   per-element field is invisible to it; J010 catches the sub-case where a
   sibling artefact is named in the same sentence, and nothing catches the
   rest. The next instance will be found by hand again unless somebody widens
   it. skills(B).
3. **The sweep is top-level fields only.** `known-unprobed-skills.json` has
   twelve `_round_NNN_note` fields and `known-standing-dirty-paths.json` has a
   `_round_349_addendum`; none is swept. Counted, not covered.
4. **The 14-deep probe batch.** Price it before adding to it.
5. **`state/swe/round-431/evaporating-test-kills-nothing.json`'s `baseline`
   key.** The acknowledgement is pinned to the sentence, so renaming either
   the key or the sentence expires it. SWE-loop(D).

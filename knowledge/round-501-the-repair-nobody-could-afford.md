# Round 501 (skills B) — the repair nobody could afford

**Track:** skills(B). **Subject:** the three skills-check reds carried into
this round, and the recurrence behind them.

**Predictions banked before measuring:** `state/round-501/predictions.md`,
written after reproducing all three reds and reading the two checkers, and
before one line of new code. Scored in §9 — a table with a verdict per line,
including the two that were wrong about my own approach.

---

## 1. What was handed over, and what it actually was

Three nodes, red since round 498, opened by language(C) (who does not run this
suite), owner skills(B), all flagged RECURRENT:

    corpus_check.py::carryforward     3 x ERROR K001
    corpus_check.py::selfdesc_check   1 x ERROR J004
    corpus_check.py::unit_tests       3 failed, 1144 passed

**Reproduced solo first, as the briefing asks.** All three are deterministic
and off-driver:

```
$ .venv/bin/python skills/skill-authoring/scripts/carryforward_check.py
state/whence/round-498/predictions.md: ERROR K001 round 498 banked predictions and … has no entry for it
state/round-499/predictions.md:        ERROR K001 …
state/round-500/predictions.md:        ERROR K001 …
carryforward: 176 bank(s) (+2 unnumbered), 170 scored, 3 unscored, 3 error(s), 33 warning(s)

$ .venv/bin/python skills/skill-authoring/scripts/selfdesc_check.py
harness/crosstrack-registry.json[nodes.…corpus_check.py::selfdesc_check.why]:
  ERROR J004 prose names `languages/whence/state/harness/round-493/predictions.md`, which does not exist

$ .venv/bin/python -m pytest <the three named nodes> -x -q     →  1 failed in 1.92 s
```

So the `RECURRENT` / "may be the runner" reading does not apply to any of the
three. They are assertions over parsed data with no timeout. That is the same
conclusion round 498 reached for the `selfdesc_check` node alone; it now holds
for the whole trio, re-derived rather than carried.

The `unit_tests` red is not independent: its three failing nodes are the
`TestLiveCorpus` assertions of the other two checkers plus
`test_corpus_check.py::test_live_corpus_is_clean`, which aggregates them. One
red, three faces.

### The thing the error message gets wrong

K001 says *"nobody can tell whether D-013's second half was ever done"*. For
all three instances currently making it red, that sentence is **false**:

| bank | scored where | verdict published |
|---|---|---|
| round 498 | `knowledge/round-498-…md` §8 | 9 HIT / 7 MISS of 16, plus 1 pre-registered |
| round 499 | `knowledge/round-499-…md` §6 | per-row, P1–P8 |
| round 500 | `knowledge/round-500-…md` §6 | per-row, P1–P10 |

Every one scored its own bank, honestly, in its own knowledge file, in its own
commit. The missing thing is the **ledger entry** — the record that the
scoring happened, at a coordinate a later reader can re-derive. K001 cannot
tell the two apart, and its message asserts the worse one.

## 2. The arithmetic, which is the whole finding

`state/prediction-bank-ledger.json` is round 369's answer to the *other* half
of D-013. It works. What has never worked is its maintenance rate.

Measured over the 41 health logs from round 460 to round 500
(`logs/skills_health_round_*.log`, the driver's own record):

    carryforward ERROR-red in   19 of 41 rounds
    K001 specifically           13 of 41 rounds

And measured over the same window, per bank, by asking git which commit first
wrote each entry (`git log -S '"NNN": {" -- state/prediction-bank-ledger.json`,
last commit, subject's leading round number):

    entries written by the round that banked   32
    entries written by a LATER round            6   (472, 473 → 474; 486 → 489; 490, 491, 492 → 495)
    not yet written                             3   (498, 499, 500 — this round's job)

**78% of rounds already register their own bank.** That is high enough that
the red reads as a discipline problem and gets closed by hand; it is also low
enough that arithmetic makes the red inevitable. A miss lands roughly every
four or five rounds, and a miss is not repaired until the next skills(B)
round — up to five rounds later — because skills(B) is the only track that
runs this checker. So:

    banks ARRIVE  ~1 per round
    entries are WRITTEN by the owner ~1 batch per 6-round rotation
    P(a whole rotation is clean) = 0.78^6 ≈ 0.22

The signature is visible in the logs and it is exact. Within an episode the
error count grows by precisely the number of rounds that failed to self-enter:

    round  490  491  492  493  494  |  495
    K001     1    2    3    3    3  |  closed
                                ^^ 493 and 494 DID self-enter, so the
                                   backlog stopped growing while staying red

    round  498  499  500  |  501
    K001     1    2    3  |  closed by this round

That is not a defect anyone can fix by reading it, and the briefing is right
to say so — but not for the reason it gives. It is not the runner. It is that
the repair is a hand-written record and the only hand that writes it comes
round once in six.

### Why four rounds diagnosed it and none built anything

Writing one entry by hand is a **four-clause job**. The entry must carry a
quote that is

- present in the file it names (K002),
- present there exactly **once** (K005),
- matched by **no other round's scope** (K006),
- and a scoring rather than a promise of one (round 495's `POINTER_RE`).

Nobody does a four-clause job for bookkeeping at the end of a round that has
spent its budget elsewhere. The rule was written down and re-written; the
cost was never removed.

## 3. What was built: the checker's own predicates, run forwards

`carryforward_check.py --enter NNN` (+ `--write`, `--entered-by`, `--owner`,
`--note`, `--force`).

The insight is small and it generalises: **a checker that ERRORs on an invalid
record is a specification with the arrows pointing the wrong way.** The same
four clauses that reject a bad anchor, applied forwards over the round's own
knowledge file, *select* a good one. `anchor_candidates()` is literally that
list:

```python
if len(line) < MIN_ANCHOR:            continue   # the K005/K006 proxy
if not VERDICT_ON_LINE_RE.search(line): continue # a scoring, not a promise
if NEGATION_RE.search(line):          continue   # "never scored" is not a scoring
if unkept_pointer(line, body):        continue   # round 495's rule
if not _attributable(line, n):        continue   # not another round's verdict
if body.count(line) != 1:             continue   # K005 forwards
if corpus.foreign_scopes(line, own):  continue   # K006 forwards
```

It is deliberately **not** `--suggest`. `--suggest` runs `scan`, the prose
classifier round 369 demoted for getting 5 of 13 verdicts wrong, and it emits
`"where": "?"`, `"scored_by": null` — an entry nobody can commit without doing
the whole job again.

Live result, one command per bank:

| round | file searched | candidates | verdict | wall |
|---|---|---|---|---|
| 498 | `knowledge/round-498-…md` | 17 | scored | 1.91 s |
| 499 | `knowledge/round-499-…md` | 8 | scored | 1.87 s |
| 500 | `knowledge/round-500-…md` | 10 | scored | 3.04 s |
| **492** | `knowledge/round-492-…md` | **0** | **unscored/no-anchor** | 2.05 s |

### The refusal is the safety property, and round 492 is its test

Round 492 is the bank round 495 proved is a laundering trap: its knowledge
file opens `(state/whence/round-492/predictions.md). Scored in §10.` and then
ends at `## 9. Tests and gates`. There is no §10, no HIT and no MISS anywhere
in it, and `--suggest` proposed a `"status": "scored"` entry quoting the
promise. Accepting it would have closed K001 while the debt stayed open.

`--enter 492` finds **zero** candidates and proposes `unscored`, with a `why`
that names what it searched and what it failed to find. This is pinned twice:
as a fixture (`test_a_promise_of_a_scoring_yields_unscored`) and, more
importantly, against the **real file**
(`test_the_generator_refuses_the_live_round_492_bank`), which also asserts the
live ledger still says `unscored` — so the generator and the ledger have to
agree that the one genuinely outstanding debt in this corpus is still owed.

A generator that always produces a satisfying record is a mute button with a
CLI. The refusal path was written before the happy path.

### Two things it deliberately will not do

- **It will not invent a judgement.** An `unscored` proposal carries
  `"owner": ""`, and `write_entry` refuses to write it — because an
  ownerless `unscored` entry is a K003 the moment it lands, and naming who
  owes a scoring is a decision, not a derivation.
- **It only derives the self-scoring case** — round n's bank, scored by round
  n, in round n's own knowledge file. That is 146 of the 173 entries the
  ledger already held. Cross-round discharge (round 371 scoring round 23's
  bank) is a judgement about somebody else's work and stays manual, with
  `--suggest` beside it as a hint.

### The write path

Pinned to the file's own serialisation, verified before anything was written:
`json.dumps(doc, indent=1) + "\n"`, `ensure_ascii` left at True, reproduces
the untouched ledger **byte for byte**. `indent=2` or `ensure_ascii=False`
rewrites all ~3000 lines. The three entries landed as **27 added, 0 deleted**
(`git diff --numstat`), and the file still round-trips identically.

## 4. Removing the cost is half of it — something still has to ask

The generator makes the entry cheap. It does not make anyone write one. The
check that finds the gap runs **after** the agent process exits, into `logs/`,
which is not in git — round 499's finding about W001, true here for the same
reason.

So: a third **advisory** step in the pre-commit hook, alongside round 475's
escalation guard and round 499's wiring warning.

```
$ time python3 skills/skill-authoring/scripts/carryforward_check.py --staged-check --quiet
real 0m0.096s
```

`staged_gaps()` fires when the commit stages `knowledge/round-NNN-*.md` while
round NNN's bank has no ledger entry, and prints the exact `--enter NNN
--write` command, plus the sentence that it refuses when the round has no
verdict of its own.

**It triggers on the knowledge file, never on the bank**, and that is the
design decision worth stating: a bank is committed *early*, before measuring.
Warning there would fire at the one round doing D-013 correctly. The knowledge
file is the end-of-round artefact; when it is in the commit, the round has
scored.

It **warns and exits 0**, for round 499's stated reason — a gate here can
refuse the commit of a round with no turns left to debug it, and losing an
uncommitted round is strictly worse than one more red line. It reads the
ledger JSON and the staged list only; no `Corpus`, which is what the 1.9 s
full run spends its time on. Fails open on any infrastructure trouble.

This step is `skills/finding-must-reach-an-actor` applied, **not new**, and
the new skill says so rather than claiming it.

## 5. The J004: fixed, not acknowledged — and this reverses my own prediction

The dangling path is `languages/whence/state/harness/round-493/predictions.md`,
which round 493 created from a stale `cd` and then `git mv`d to
`state/harness/round-493/`. **Two** prose fields cite it:

1. `state/prediction-bank-ledger.json[banks.493.note]` — round 493's own
   record of the mistake. Content-pin **acknowledged** by round 495, correctly:
   the note is a note *about* the move, so rewriting it deletes the evidence.
2. `harness/crosstrack-registry.json[nodes.…selfdesc_check.why]` — round 498's
   node declaration, which quoted the path **in full while diagnosing it** and
   thereby created a second instance of the error it was describing. This is
   the one that has been red from round 498 to now.

I banked (P7) that I would acknowledge #2 as well. **I did not, and the
prediction is a MISS on its mechanism.** The reason is round 495's own rule,
written into the ack it created: an acknowledgement is for the field that IS
the evidence; a field *describing* the mistake should name the **coordinate**
and let the reader take one hop. Round 495 applied that to its own `why`
("it deliberately does NOT spell the dangling path… The path is one hop away
and fully determined"). `harness/crosstrack-registry.json`'s `why` is a
describing field. And `state/known-selfdesc-drift.json`'s own `_comment` says
**"Prefer FIXING the prose"** — a second acknowledgement would have been the
mute button that file exists to refuse.

So the fix is one field, one line of diff, no information lost: the sentence
now names `state/prediction-bank-ledger.json[banks.493.note]` as the citing
field, says the path is quoted inside it and is deliberately not repeated,
and records that spelling it out is what made the declaration red for four
rounds. Errors: **1 → 0**, acknowledgements still **1**.

While there, one more self-description in the same family:
`state/known-selfdesc-drift.json`'s `_comment` still said *"this file has been
EMPTY since round 437"* — false since round 495 added the entry directly
below it. Six rounds stale, in the registry whose entire job is recording that
other artefacts' self-descriptions have drifted. Corrected, with what changed
and why stated in the sentence.

## 5b. A next-steps item that re-derives itself

`state_claim_check` has reported **`0/N items, 0/0 claims`** for rounds 497,
498, 499 and 500 — four consecutive next-steps blocks with nothing in them a
machine could re-run. Round 501's item 1 asks the next rotation to watch
whether K001 stays at zero, and the honest way to ask that is to state it as
a claim the checker executes:

    `python3 skills/skill-authoring/scripts/carryforward_check.py` -> exit 0.

`exit 0` and not a test count, deliberately: the exit code is 1 if and only if
some bank on disk is unaccounted for, so the claim goes stale exactly when the
recurrence returns and for no other reason. A `125 passed` claim would go
stale the next time anybody adds a test, which is a false alarm dressed as a
signal.

That required one allowlist entry — `claim_check.AUTO_RULES` had no line for
`carryforward_check.py`, so the claim extracted and was then skipped as
`unknown program (fails closed)`. Added **with `--write` and `--force`
forbidden by name**. Both are already caught by the existing `mutating` rule,
so the `forbid` clause is redundant today; it is there for the reason the
`pristine_check.py` entry above it names its four read-only verbs explicitly
— an entry that names only its program hands an `auto` verdict to every flag
added later, and an executor that ran `--enter NNN --write` while re-deriving
a sentence would edit the ledger as a side effect of checking a claim about
it. Pinned by
`test_carryforward_check_is_auto_but_never_when_it_writes`.

Result: `state_claim_check state/research-state.md --run` →
**1 claim, 1 re-derivable, 0 stale, coverage 1/8 items (12%), 1/1 claims**.

## 6. Tests

`skills/skill-authoring/scripts/test_carryforward_check.py`: **107 → 125**
collected nodes. Eighteen new, in three classes plus two live-corpus tests:

- `TestEnterGeneratesAnEntryTheCheckerAccepts` — a verdict line becomes the
  anchor; a promise yields `unscored`; no knowledge file yields `unscored`
  naming which; K005 forwards (anchor occurring twice refused); K006 forwards
  (anchor another round also carries refused); under the length floor
  refused; a negated line refused; a line crediting another round refused;
  and **the round trip** — generate, write, re-run `findings()`, zero errors.
- `TestWriteEntryIsByteStableAndRefusesToGuess` — the write reproduces the
  file's own serialisation (asserting the `—` escape survives, i.e.
  `ensure_ascii` was not flipped); an existing entry is not overwritten
  without `--force`; an `unscored` entry with no owner is refused and the
  ledger is left untouched.
- `TestStagedCheckFiresWhereTheAuthorStillIs` — the knowledge file fires and
  the bank alone does **not**; a round already in the ledger is silent; a
  knowledge file for a round that banked nothing is silent; the hook text
  carries the step, ends `|| true`, and the file's last line is `exit 0`.
- `TestLiveCorpus::test_the_generator_refuses_the_live_round_492_bank` and
  `::test_every_entry_this_round_generated_is_re_derivable` (each of the three
  new anchors: unique in `where`, zero foreign scopes).

**The suite, solo, through the driver's own runner** (`bash skills/run_checks_fast.sh`,
system `python3`, the interpreter the driver uses — not `.venv`):

```
skill_lint         warn B002    108 skill(s), 0 error(s), 7 warning(s)
case_coverage      warn P004…   108 skill(s), 457 case(s); 50 probed, 30 replicated
claim_check        ok           358 path(s) resolved, 0 stale of 358
state_claim_check  ok           0 claim(s)
xref_check         ERROR rc1    1 NEW dangling citation      <- see below
carryforward       ERROR K001   177 bank(s), 173 scored, 3 unscored, 1 error(s), 33 warning(s)
placeholder_check  warn U002    417 file(s), 6 unfilled (6 acknowledged)
selfdesc_check     ok           853 prose field(s), 0 error(s), 0 warning(s), 8 info, 1 acknowledged
verb_audit         ok           30 finding(s) (V001 7, V002 0, V003 23) — all WARN
unit_tests         ERROR rc1    2 failed, 1163 passed, 4 subtests passed in 185.30s
```

Against the round-500 baseline: `selfdesc_check` **1 error → 0**;
`carryforward` **3 errors → 1**; `unit_tests` **3 failed → 2**. The remaining
error in each is one thing — round 501's *own* bank, unentered at the moment
that suite ran, which §9's P5 discusses and which `--enter 501 --write`
closed at the end of the round. Collected nodes in
`skills/skill-authoring/scripts/`: **973 → 992** (991 at the time that
suite ran; §5b added one more).

**I reddened `xref_check`, and it is my own timing.** The new
`SKILL.md`'s last line cites this knowledge file, and the suite was launched
before this file was written, so `X004` reported the citation as dangling. It
is a real finding about a real ordering mistake — write the artefact you cite
before running the checker that resolves citations — and it is not a defect
in the skill. Re-verified after this file landed: see the final
`carryforward`/`xref_check` block in §11.

`unit_tests` at **185.30 s solo** against **646 s** for the same stage under
the driver's four concurrent suites on the same one-core box: a **3.5x**
contention penalty, which is round 435's number holding and my P11 losing.

## 7. What this round did not do

- **Did not pay the probe batch.** The new skill is entry **50** in
  `state/known-unprobed-skills.json`. A probe is ~$0.05 per invocation and
  needs operator authorisation this round did not have. Recorded in a
  `_round_501_note` that says explicitly this is a *skills(B)* round adding to
  the batch rather than a non-skills round deferring to one — which is the
  shape the earlier notes in that file were complaining about. The new
  description has never been tested against a model.
- **Did not touch the fourth red** in the briefing
  (`test_swe_mutation.py::test_the_grandchild_pid_survives…`, owner
  harness(A)). Out of track and a live-timing test.
- **Did not widen `--enter` to cross-round discharge**, on purpose (§3).
- **Did not add the count of unentered banks to the summary line.** The
  summary already carries `%d error(s)`; a second counter for the same thing
  would be the duplication this corpus keeps finding.

## 8. Honest failures and near-misses

- **The generator's own output shape was nearly wrong.** Longest-first
  ranking picks a 200-character table row, not the canonical tally line. That
  looked like a defect until I listed the candidates: rounds 499 and 500 have
  **no tally line at all** in their scoring sections. A generator that
  preferred summaries would have failed on two of the three banks it was
  built for. Kept, and the reason is in the round-500 ledger note.
- **`--help` did not mutate state, and I checked before running it** — the
  argparse path exits before `main`'s body. This program has been bitten by
  the opposite.
- **The `nohup … &` completion notification fired while the suite was still
  running.** Confirmed by `pgrep` that pid 4039150 was still alive; the exit
  code belonged to the wrapper.

## 9. Predictions scored (D-013) — `state/round-501/predictions.md`

| # | banked | outcome |
|---|---|---|
| P1 | 3 of 3 rounds yield ≥ 1 usable anchor | **HIT** — 17, 8, 10 |
| P2 | 3–40 candidates each, point estimate 8–15 | **HIT** — 17 / 8 / 10; the point estimate held for two of three |
| P3 | **the falsifier**: round 492 refused | **HIT** — 0 candidates, `unscored/no-anchor`, pinned against the live file |
| P4 | ≤ 30 added, 0 deleted; still byte-stable | **HIT** — 27 / 0, round-trips identically |
| P5 | errors 3 → 0, warnings unchanged at 33 | **SPLIT** — warnings held at 33; errors went 3 → **1**, and the 1 is *this round's own bank*, which P14 then closed. The prediction failed to anticipate that banking under D-013 creates a fourth K001 the moment it is written. That is the mechanism working, not a defect, and I did not see it coming. |
| P6 | `--enter` 0.5–20 s, point estimate 3–8 | **HIT on the band, MISS on the estimate** — 1.87–3.04 s, faster than estimated |
| P7 | acknowledge #2 → 0 errors, 2 acknowledged | **MISS on mechanism** — 0 errors reached by FIXING the prose, acknowledgements still 1. See §5: the corpus's own rules pointed the other way and I had not read `known-selfdesc-drift.json`'s `_comment` closely enough when banking. |
| P8 | the ack-registry recursion is real | **HIT on substance, VOID as posed** — the recursion is real and round 498's field is the standing proof of it; but since I wrote no acknowledgement, my own `why` never risked it. Scored from the corpus, not from my writing. |
| P9 | the 3 red nodes go green, nothing else reddens | **SPLIT** — `selfdesc_check`'s node is green and the two `carryforward` nodes are green except for this round's own bank (closed at the end of the round). But I **reddened `xref_check`**, which the prediction said would not happen: the skill cites this file and the suite ran before this file existed. MISS on the second clause, and the cause is ordering, not content. |
| P10 | test file 107 → 112–125; suite 973 → 978–991 | **HIT** — 125, and 991 at the moment the suite ran (992 at the final commit, one over the band, because §5b's test came after the measurement). Note the two denominators are different populations: 991 is `--collect-only` over `skills/skill-authoring/scripts/`, while the corpus check's `unit_tests` stage collects 1165. Both moved by exactly 18. |
| P11 | whole scripts suite solo, 400–800 s | **MISS, by 2.2x low** — **185.30 s**. I bet explicitly AGAINST round 435's ~3x solo-vs-concurrent ratio and it held almost exactly (646 / 185.3 = 3.5x). The lesson is the one round 433 already banked: re-derive the baseline, and prefer a measured ratio to a hunch about today's load. |
| P12 | ≥ 100 of 173 entries self-scored | **HIT** — 146 |
| P13 | base rate: I break ≥ 1 of my own new tests on first run | **MISS** — 16 of 16 passed first run, then 18 of 18. Betting on the base rate lost this time; the reason is that every new test was written against a predicate I had already run by hand against the live corpus. |
| P14 | round 501 enters its own bank inside round 501 | **HIT — but the framing was wrong.** I implied this would be a first. It is not: 32 of the 41 banks from round 460 to 500 were self-entered, including five consecutive rounds 493–497. The finding is not that self-entry is impossible, it is that 78% is not enough. Corrected in §2. |

## 10. Next steps

1. **The generator exists; the practice does not yet, and one round is not
   evidence.** `--enter NNN --write` closed three K001s and this round's own,
   and the pre-commit step now asks for it — but the step has fired exactly
   once, in this round, on this round's commit. The measurement that would
   settle it is the K001 column of `logs/skills_health_round_*.log` over
   rounds 502-507: if the arithmetic in §2 is right, that column should read
   `0 error(s)` for the whole rotation for the first time since round 460.
   If it does not, read WHICH round's bank is missing and whether the hook
   fired for it — the failure mode to look for is a round committing its
   knowledge file in the same `git commit` as something that made the hook
   fail open. **skills(B) at round 507, and nobody before then needs to act.**

2. **`--enter` only derives the SELF-scoring case, and that is a declared
   limit rather than a finished job.** 27 of the ledger's entries are
   cross-round discharges, and every future one is still a four-clause hand
   job with only `--suggest` (the demoted prose classifier) beside it. The
   honest next move is NOT to widen `--enter` — the predicates cannot verify
   an attribution — but to decide whether cross-round discharge should be
   recorded at all, or whether an unscored bank should simply stay unscored
   with an owner. Round 492 is the live instance to decide it against.
   skills(B) or language(C).

3. **Round 492's bank is still the one genuinely outstanding debt in this
   ledger, and it is now pinned by two tests rather than one.** It is
   `unscored`, owner language(C), owed for nine rounds, and both the ledger
   and the generator agree. It cannot be closed by scoring it now — a bank
   scored after the results are known is not scored — so the only honest
   moves are a written decision that it is unscorable, or a nearest-
   instantiation scoring of the kind round 371 did for round 23, done
   explicitly and labelled. language(C).

4. **`state/known-selfdesc-drift.json` and `state/known-unprobed-skills.json`
   are both artefacts whose own prose has now gone stale once.** This round
   found and fixed the first (`"EMPTY since round 437"`, false for six
   rounds). The second carries eleven `_round_NNN_note` fields and
   `selfdesc_check` sweeps **top-level prose fields only** — round 435's
   next-step #3, still open, still `coverage 157/853 prose-fields`. The
   nested-field sweep is the single largest coverage gap in that checker and
   nobody has costed it. skills(B).

5. **The probe batch is 50 skills deep and this round added to it.** A probe
   is ~$0.05 per invocation and needs operator authorisation. The new
   skill's `why` names a scorable prediction (that `gwca-far` is the case
   that misfires, most likely toward `unenforced-documented-rule` or
   `errors-that-name-the-fix`) so that whoever eventually pays the batch has
   something to score rather than a bare entry. skills(B), with
   authorisation.

6. **The fourth red in this round's briefing is untouched and still
   harness(A)'s:** `harness/tests/test_swe_mutation.py::test_the_grandchild_
   pid_survives_a_grandchild_slower_than_the_cap`, red since round 500,
   RECURRENT with 3 earlier episodes. It is a live-timing test on a one-core
   box, which is exactly the class the briefing warns may be the runner —
   and this round's trio turned out NOT to be that class, so the distinction
   is worth making rather than assuming. harness(A).

7. **Standing and untouched by this round:** `case_coverage`'s 47-of-99
   disagreeing cross-report verdicts; `claim_check` executing **0 of 548**
   commands; the operator-blocked `--cap 196`; the NUC `retention --strict`
   deadline; and CLAUDE.md's `CRITICAL MISSION` and `MASTER MISSION` blocks,
   still a deletion for the operator. `languages/whence/SECURITY.md` remains
   the operator's decision and the checker's own line is the only source for
   its carry count.

## 11. Final verification, at the round's last commit

Run after the knowledge file existed and after `--enter 501 --write` closed
this round's own bank. `.venv/bin/python` except where noted.

```
$ carryforward_check.py
carryforward: 177 bank(s) (+2 unnumbered), 174 scored, 3 unscored, 0 error(s), 33 warning(s)

$ selfdesc_check.py
selfdesc-check: 59 artefact(s) of 727 json file(s), 854 prose field(s),
  0 error(s), 0 warning(s), 8 info, 1 acknowledged

$ xref_check.py
xref_check: 9 dangling citation(s) in the authoritative scope (0 NEW,
  9 pre-acknowledged), 113 in the historical scope

$ placeholder_check.py
placeholder-check: 418 file(s), 6 unfilled (6 acknowledged), 0 error(s), 6 warning(s)

$ skill_lint.py skills/generate-what-the-checker-accepts --house --strict
skill-lint: 1 skill(s), 0 error(s), 0 warning(s)

$ case_coverage.py
case-coverage: 108 skill(s), 457 case(s); 0 error(s), 30 warning(s)

$ pytest skills/skill-authoring/scripts/ -q
992 passed, 4 subtests passed          # 991 in 160.38 s before §5b's test

$ state_claim_check.py state/research-state.md --run
state_claim_check: 1 claim(s): 1 re-derivable, 0 skipped; 0 stale of 1 checked;
  coverage 1/8 items (12%), 1/1 claims

$ pytest harness/tests/test_escalationguard.py -q
39 passed in 2.38s

$ pytest harness/tests/test_wiring_audit.py -q -k hook
2 passed, 87 deselected

$ python3 harness/wiring_audit.py undeclared        # system python, as the hook runs it
wiring-audit: no undeclared entry point in the whole tree
```

And the whole check, as the driver runs it, at the final commit:

```
$ bash skills/run_checks_fast.sh
skill_lint         warn B002    108 skill(s), 0 error(s), 7 warning(s)
case_coverage      warn P004…   108 skill(s), 457 case(s)
claim_check        ok           358 path(s) resolved, 0 stale of 358
state_claim_check  ok           1 claim(s): 1 re-derivable; 1 command claim needs --run
xref_check         ok           9 dangling (0 NEW, 9 pre-acknowledged)
carryforward       warn K004    177 bank(s), 174 scored, 3 unscored, 0 error(s), 33 warning(s)
placeholder_check  warn U002    418 file(s), 6 unfilled (6 acknowledged), 0 error(s)
selfdesc_check     ok           854 prose field(s), 0 error(s), 0 warning(s), 1 acknowledged
verb_audit         ok           30 finding(s) — all WARN
unit_tests         ok           1166 passed, 4 subtests passed in 178.22s
corpus-check: 10 checker(s), 0 error(s), 7 warning(s)          rc=0
```

All three inherited reds are closed. `carryforward` **3 errors → 0**,
`selfdesc_check` **1 → 0**, `unit_tests` **3 failed → 0**, and the check as a
whole goes from `3 error(s)` to **`0 error(s)`, rc 0** — the first clean
skills-check since round 497. The seven warnings are the same seven round 500
carried (B002's long body, `case_coverage`'s P004/P006/P007/P009,
`placeholder_check`'s U002, and now `carryforward`'s K004 age warnings, which
never set the exit code by round 363's rule).

The commit-time step, derived live against the real bank set and the real
ledger rather than a fixture — the third line is the trigger discipline, and
it is the one that matters:

```
with round 501 in the ledger : []
with round 501 removed       : [(501, 'knowledge/round-501-…md', 'state/round-501/predictions.md')]
the BANK staged instead      : []
```

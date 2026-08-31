# Round 397 — harness(A) — the entry that was there all along

**Task as handed over:** the pre-round record-gap check reported
`round 396 track=language(C) status=success knowledge_file=True
interrupted=False git_committed=True` — shape 1, "a round ran per the
driver log with NO research-state.md entry." That report was the entire
NOTE injected into this round's prompt.

**It was false.** Round 396's entry is at `state/research-state.md:14222`,
committed in `a7f2add`, and has been there since round 396 wrote it:

```
## Round 396 (language C) — v0.35, decision 44: the sentence that was three divergences
```

The detector could not see it. `check_round_recorded.py`'s
`STATE_ENTRY_RE = ^### Round (\d+) [—-]` requires exactly three hashes AND
a dash immediately after the number. Round 396 used two hashes and a
parenthesised track. Both differences are individually fatal to the match.

So the round's work was: not to reconcile round 396, but to fix the thing
that said round 396 needed reconciling — and then to find out why nobody
had, in ninety-four rounds.

---

## 1. It had happened before, and the diagnosis went the wrong way

`git log -S` over all 205 revisions of `state/research-state.md`, matching
every `^#{1,6}\s*Rounds?\s+\d` heading that the strict pattern rejects,
returns exactly six lines. Four are the archive's span headings (§3). The
other two are round 396's and this one:

```
### Round 302 (language C) — Whence v0.14.10 — 2026-08-29
```

Three hashes — what broke that one was the `(` alone. Its history, from
`git log --format="%h %ci %s"` and `logs/driver.log`:

| time (2026-08-29) | event |
|---|---|
| 03:44:55 | round 303's pre-round check: `record-check FOUND gap(s) — ... round 302 ... NO research-state.md entry` |
| 03:46:34 | `1979708` "Round 302 (language C, reconciled by round 303): add research-state.md entry" — **adds the heading above** |
| 03:55:58 | `b2e5425` "Round 303 (skills B): ... close round 302's record gap" — **rewrites it to `### Round 302 — language(C) — 2026-08-29`** |

Round 303 wrote a correct entry, re-ran the detector, was still told
round 302 was missing, and **edited the document until the regex was
satisfied** — nine minutes and twenty-four seconds later, in a commit whose
subject calls that "closing the gap". Nothing anywhere records that the
regex was the thing that was wrong. So the bug survived the encounter
completely intact and fired again 94 rounds later, this time consuming a
round's whole prompt NOTE.

This is the finding, more than the regex is: **when a reader and a writer
disagree about a format that nothing mechanically enforces, fixing the
writer fixes one document. The next writer has not read the regex either.**
Round 303's fix was correct, local, and had a half-life of 94 rounds.

## 2. Nothing on the writing side enforces the format — and four readers disagree

`CLAUDE.md` ground rule 4 says "Update `state/research-state.md` — append a
round entry". The driver prompt says "update research-state.md". Neither
mentions `### Round N — <track> — <date>`. That shape exists nowhere except
inside the regexes that consume it, and as of this round no two of them
accepted the same set of headings:

| parser | pattern | r396 | r302 | `### Rounds A-B` |
|---|---|---|---|---|
| `check_round_recorded.STATE_ENTRY_RE` | `^### Round (\d+) [—-]` | **blind** | **blind** | **blind** |
| `carryforward_check._HEADING_RE` | `^###\s+Round\s+(\d{1,4})\b` | **blind** | ok | **blind** |
| `swe.toolliveness._STATE_HEAD` | `^#{2,3} Round (\d+)\b` | ok | ok | **blind** |
| `state_claim_check` block-stop | `^#{1,3}\s` | ok | ok | ok |

An entry can therefore be simultaneously visible to one tool and invisible
to three, with no error raised anywhere. The way that surfaces is as a
*phantom missing round* — output shaped exactly like a real total record
loss, which is the most expensive false positive this program has, because
the standing cross-track convention is that the next round stops and lands
the predecessor's work before starting its own.

Measured cost of `carryforward_check`'s blindness today: it sees 210 of the
211 rounds in the live file, missing 396. **No scoring is lost right now**,
because round 396 banked no predictions — recorded honestly: the mechanism
is live, the loss is zero this week, and it becomes real the first time a
drifted-heading round writes a prediction bank.

## 3. A third form the strict pattern never matched at all

`state/research-state-archive.md` uses a **span** heading four times, and
they are legitimate — this is how the record accounts for rounds that never
individually ran:

```
### Rounds 12–13 — did not run — (discovered 2026-08-24, round 14; CORRECTED round 19)
### Rounds 114-126 — driver-level, mostly did not run — 2026-08-25/26
### Rounds 128-129 — unrecorded, flagged not chased — 2026-08-26
### Rounds 131-135 — mostly did not finish — 2026-08-26
```

Plural `Rounds`, so `Round (\d+)` matches none of them. They account for
**22 round numbers**; the strict reader saw 62 rounds in that file where 83
are accounted for. This is latent rather than live — `driver.log`'s oldest
round is 152, so none of these are ever adjudicated — but it is the same
defect and it is now read correctly.

## 4. The fix: one definition, and drift reported rather than silenced

New `harness/roundheadings.py` — the single definition, shared:

```python
_LEVEL   = r"(#{2,5})"
SINGLE_RE = re.compile(_LEVEL + r"[ \t]*Round[ \t]+(\d{1,4})(?![\d.])")
SPAN_RE   = re.compile(_LEVEL + r"[ \t]*Rounds[ \t]+(\d{1,4})[ \t]*[-‒–—][ \t]*(\d{1,4})(?![\d.])")
CANONICAL_RE = re.compile(r"### Round (\d{1,4}) [—-]")
MAX_SPAN_WIDTH = 64
```

API: `parse_heading(line)` → `Heading(rounds, level, is_span, canonical,
path, line)`; `headings(text)`; `heading_rounds(text)`;
`nonstandard_headings(text, only_rounds=None)`; plus
`python3 -m harness.roundheadings FILE...`.

Four design choices that are the actual engineering, each with a test:

- **Monotonicity is pinned, not asserted.** Widening a detector is only
  safe if it never loses a round the old pattern found. A test re-derives
  the old pattern's round set from the *live* corpus and asserts
  `was <= now` for both state files. Without that, "we made it more
  tolerant" is a claim, not a property.
- **A span is bounded.** `### Rounds 1-400 — summary` is **refused**, not
  expanded. One heading that can mark four hundred rounds recorded would
  mask every real gap underneath it — a detector that fails open is worse
  than the false positive it replaced.
- **The span form requires the plural.** Otherwise `### Round 400 —
  2026-09-01` parses as the span 400..2026. The plural requirement is what
  makes the date unambiguous, and it is why `MAX_SPAN_WIDTH` is a second
  belt rather than the only one.
- **Level 1 and level 6 are excluded, `## Round log` stays excluded.**
  `Round[ \t]+\d` is the whole trick: "log" is not a digit. Pinned by eight
  negative cases including `## Round log (rounds 1-136)`, which the span
  regex would otherwise love.

`check_round_recorded.py` now reads through it, and gained
`nonstandard_state_headings` — **the half that matters more than the
widening**:

```
check_round_recorded: 1 round entr(ies) are recorded but their heading has
drifted from `### Round N — <track> — <date>`. NOT a gap and NOT part of the
exit code — every round below IS in the record. [...] a drifted heading is
visible to some [tools] and invisible to others, and that surfaces as a
PHANTOM missing round (rounds 302, 396). Fix the heading if you like, but
do not record the round as a gap:
  state/research-state.md:14222  ## Round 396 (language C) — v0.35, ...
```

Tolerance without a report is exactly how round 303's misdiagnosis went
unrecorded for 94 rounds. Naming the heading is what stops the next round
doing what round 303 did.

The report is **scoped to the rounds the run actually adjudicates**
(`only_rounds=` the driver-log set). Unscoped, the archive's four span
headings — real, correct, and permanently non-canonical — would print on
every run forever. That is precisely the unactionable-noise failure the
round-373 escalation registry exists to stop reproducing; building a new
instance of it in the same file would have been a poor trade.

**Degradation is announced, not silent.** The guarded import mirrors the
file's existing `harness.driver_health` idiom, but the stakes differ: a
missing `driver_health` costs a `None` column, whereas a missing
`roundheadings` falls back to the strict pattern — i.e. to the bug. So
`main()` prints a `DEGRADED` banner naming rounds 302 and 396 and telling
the reader not to trust the gap list. Tested by copying the script alone
into a tmp dir far from the repo, which is the real
`~/.hermes/skills/`-promotion case from CURRICULUM.md's endgame.

## 5. Verification (all run this round, output above/below)

| suite | result |
|---|---|
| `harness/tests/test_roundheadings.py` (new) | **43 passed** |
| `skills/.../test_check_round_recorded.py` | **93 passed** (was 80; +13) |
| `harness/tests/test_run_driver_record_gap_check.py` | **7 passed**, unmodified |
| `pytest harness/tests/ -m "not swe_slow"` | **844 passed**, 268 deselected, 95.65s |
| `skills/run_checks_fast.sh` | 7 checkers, **0 errors, 6 warnings** — unchanged from round 395's baseline; `unit_tests 708 passed` |
| `skill_lint.py --house --strict skills/session-inheritance-audit/` | 0 errors, 0 warnings (SKILL.md 280 → 295 lines) |

Live detector before / after, same tree:

```
before:  round 396 track=language(C) ... NO research-state.md entry   <-- FALSE
after:   (no round-396 line; drift reported instead)
```

Remaining flags on the live run are this round's own in-flight diff and
round 397 itself, both expected pre-commit.

**Honest limitation.** Only `check_round_recorded.py` was migrated to the
shared definition. `carryforward_check.py` and `state_claim_check.py` are
skills(B)'s files and are not driver-wired; harness(A)'s precedent for
touching the detector is round 373 (which added gap shape 5 to the same
file) and does not extend to them. `toolliveness.py` already accepts `##`
and needs no change for r396, though it is still blind to span headings.
The adoption patch is one line each and is written out in the next-steps.

## 6. What generalizes

- **A detector's pattern is a contract. If only the detector knows it, it
  is not a contract — it is a trap.** Every consumer of a hand-written
  document should either enforce the format at write time or accept what a
  reasonable writer produces. This repo does neither, in four places.
- **"The document was wrong" is the tempting diagnosis and was the wrong
  one.** Round 303 had all the evidence — it had just written the entry
  itself — and still concluded the entry was malformed rather than the
  reader over-strict. A false positive that is *cheap to work around* is
  more durable than one that blocks you: the workaround gets applied and
  the bug never gets attributed.
- **Widen a detector only with a monotonicity test against the live
  corpus, and a hard bound on what any single input can claim.** Otherwise
  fixing a false positive quietly manufactures false negatives, which this
  program has no way to notice at all.
- **Duplicated parsers of one document drift silently and pairwise.** The
  divergence here was never visible as a failure; it was visible only when
  someone cross-tabulated four regexes against four real headings. That
  cross-tabulation cost one tool call and should be routine whenever more
  than one tool reads the same hand-maintained file.

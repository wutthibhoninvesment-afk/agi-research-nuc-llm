# Round 501 (skills B) — predictions, banked BEFORE any measurement (D-013)

**Subject:** the three skills-check reds carried into this round
(`corpus_check.py::carryforward`, `::selfdesc_check`, `::unit_tests`, red since
round 498, owner skills(B), RECURRENT), and the recurrence behind them that the
red-debt briefing says has been "diagnosed in prose four times since round 473
without anything ever being built from it".

Banked after REPRODUCING all three reds and reading `carryforward_check.py`,
`selfdesc_check.py`, `state/prediction-bank-ledger.json`,
`state/known-selfdesc-drift.json` and `harness/crosstrack-registry.json`.
Banked BEFORE: writing one line of new code, running `--enter` (which does not
exist yet), touching the ledger, or touching the acknowledgement registry.

## Read-set

`skills/skill-authoring/scripts/carryforward_check.py` (1136 lines, in full),
`skills/skill-authoring/scripts/selfdesc_check.py` (grep + the ack machinery at
975-1115), `state/prediction-bank-ledger.json` (`_comment`, `_bootstrap`, the
first ~12 entries), `state/known-selfdesc-drift.json` (whole),
`harness/crosstrack-registry.json` (the `selfdesc_check` node, whole),
`logs/skills_health_round_{495,497,498,499,500}.log`,
`logs/corpus-evidence/round-500/{carryforward,selfdesc_check}.out`,
`state/research-state.md` §"Next steps (as of round 500)", the head of each of
the three unentered banks, and the scoring section of each of the three
corresponding knowledge files.

## Already OBSERVED before banking (so scoring cannot claim them)

- **O1.** All three reds reproduce SOLO, deterministically, off the driver:
  `carryforward_check.py` prints 3 `ERROR K001` lines (rounds 498, 499, 500)
  and exits 0 (its `main` returns 1, but the shell reported 0 through the
  pipe); `selfdesc_check.py` prints exactly 1 `ERROR J004`; the three named
  pytest nodes fail in 1.92 s. So the `RECURRENT`/"may be the runner" reading
  in the red-debt briefing **does not apply to this trio** — same conclusion
  round 498 reached for the `selfdesc_check` node, now re-derived for all three.
- **O2.** Baselines at HEAD, each with the command that produced it:
  - `.venv/bin/python skills/skill-authoring/scripts/carryforward_check.py`
    -> `176 bank(s) (+2 unnumbered), 170 scored, 3 unscored, 3 error(s), 33 warning(s)`
  - `.venv/bin/python skills/skill-authoring/scripts/selfdesc_check.py`
    -> `59 artefact(s) of 727 json file(s), 848 prose field(s), 1 error(s), 0 warning(s), 8 info, 1 acknowledged`
  - `.venv/bin/python -m pytest skills/skill-authoring/scripts/ -q --collect-only`
    -> `973 tests collected`; `test_carryforward_check.py` alone -> `107`.
  - `python3 -c "json.dumps(json.load(open(LEDGER)), indent=1)+chr(10)"` is
    **byte-identical** to the file on disk. `ensure_ascii` is left at True and
    `indent=2` is NOT the format. 173 entries under `banks`.
- **O3.** The three unentered banks were each **scored by their own round in
  their own knowledge file**: round 498 §8 (`9 HIT / 7 MISS of 16`), round 499
  §6, round 500 §6. So K001's message — "nobody can tell whether D-013's second
  half was ever done" — is FALSE for all three instances currently making it
  red. The debt is the ledger ENTRY, not the scoring.
- **O4.** `harness/crosstrack-registry.json`'s `selfdesc_check` node `why`
  field spells the moved path `languages/whence/state/harness/round-493/…`,
  which is a SECOND instance of the same J004 the ledger's `banks.493.note`
  raises; `banks.493.note` is already acknowledged in
  `state/known-selfdesc-drift.json` and the registry `why` is not. Round 494's
  next-step #7 and round 495's ack `why` both assign the acknowledgement to
  skills(B).

Everything below this line is unmeasured.

---

## Part A — the generator (`carryforward_check.py --enter NNN`)

**P1 (STRUCTURAL).** For each of rounds 498, 499 and 500, the anchor search
finds **>= 1** line in that round's own `knowledge/round-NNN-*.md` that is
simultaneously (a) >= 40 chars, (b) unique in that file, (c) carrying a literal
`HIT`/`MISS`/`PARTIAL` verdict, and (d) matched by **zero** foreign round
scopes. Band: **3 of 3** rounds yield a usable anchor.
*Why it could be wrong:* round 500's scoring rows are short table cells
(`| P3 | ... | **HIT** |`), and knowledge files in this program quote each
other constantly, so (d) is the clause most likely to zero out.

**P2 (RATE).** Candidate anchors per round, after all four filters:
between **3 and 40** for each of the three. Point estimate 8-15.
*Why it could be wrong:* the >= 40-char floor plus uniqueness is harsh on
table rows; I have not counted table rows in any of the three files.

**P3 (STRUCTURAL — the falsifier).** Run against **round 492** — the bank round
495 proved is a laundering trap, whose knowledge file promises `Scored in §10.`
and has no §10, no HIT and no MISS — the generator **refuses** to propose a
`scored` entry and proposes `unscored` instead. If it proposes `scored` for 492,
the tool has re-introduced exactly the bug round 495 built `POINTER_RE` to stop
and must not ship.
*Why it could be wrong:* my verdict filter may match a stray capitalised `MISS`
elsewhere in round 492's file (e.g. in prose about some other round's misses).

**P4 (STRUCTURAL).** Writing all three entries changes
`state/prediction-bank-ledger.json` by **<= 30 added lines and 0 deleted
lines** (`git diff --numstat`), i.e. it is an APPEND of three entries and not a
whole-file reformat; and the file still round-trips byte-identically under
`indent=1`.
*Why it could be wrong:* `json.dump` re-serialises the whole file; if I pass
`ensure_ascii=False` or `indent=2` the diff becomes ~3000 lines. This is the
failure this program has already recorded once as a memory.

**P5 (STRUCTURAL).** After the three entries land,
`carryforward_check.py` reports **0 error(s)** and **33 warning(s)** — the
warning count is UNCHANGED, because a `scored` entry with no `remainder` and a
`scored_by` equal to its own round contributes to neither K004 branch.
*Why it could be wrong:* if any of my three anchors is non-unique in `where`
(K005) or foreign-matched (K006) the error count lands at 1-3, not 0; if I
write a `remainder` field for a partially-scored bank (round 499's P4 and P6
are MISSes, round 500's P5 is a SPLIT — none of which is an OUTSTANDING
prediction, but I could misread the field's meaning) the warnings go to 34-36.

**P6 (RATE).** `--enter` for one round completes in **0.5-20 s** wall clock,
solo, on this `nproc`=1 box. Point estimate 3-8 s.
*Why it could be wrong:* `Corpus.foreign_scopes` walks every round scope
(~500 knowledge files + ~300 state sections) per candidate line; at 40
candidates that is 40 full passes over the corpus and could exceed 60 s.

## Part B — the acknowledgement (J004)

**P7 (STRUCTURAL).** Adding one content-pinned entry for
`harness/crosstrack-registry.json[nodes.…selfdesc_check.why]` takes
`selfdesc_check.py` to **0 error(s)** and **2 acknowledged**, with **0** J009
("acknowledgement matches no finding").
*Why it could be wrong:* the pin is `sha256[:16]` of the WHOLE prose field
(`prose_hash`); computing it over a trimmed or re-encoded copy of the field
yields a hash that matches nothing and fires J009 immediately.

**P8 (STRUCTURAL).** If the new acknowledgement's own `why` field spells the
dangling path literally, `selfdesc_check` raises a **third** J004 — against the
acknowledgement registry itself. I predict this recursion is REAL (round 495
recorded hitting it) and that naming the coordinate instead of the path avoids
it, so the final error count is 0 and not 1.
*Why it could be wrong:* the registry's `acknowledged` list is a nested
collection; `selfdesc_check` may not sweep `why` fields inside it at all, in
which case the recursion is a non-event and this prediction is vacuous. I have
not checked which fields it sweeps in that file.

## Part C — the suite, and the recurrence

**P9 (STRUCTURAL).** All three red pytest nodes
(`test_carryforward_check.py::TestLiveCorpus::test_the_live_ledger_accounts_for_every_bank_on_disk`,
`test_corpus_check.py::TestLiveCorpus::test_live_corpus_is_clean`,
`test_selfdesc_check.py::TestLiveCorpus::test_the_live_corpus_has_no_unacknowledged_errors`)
go green, and **no other node in `skills/skill-authoring/scripts/` goes red**.

**P10 (RATE).** New tests for `--enter` take
`test_carryforward_check.py` from 107 to between **112 and 125** collected
nodes, and the whole `skills/skill-authoring/scripts/` suite from 973 to
between **978 and 991**.

**P11 (RATE).** The whole `skills/skill-authoring/scripts/` suite, run SOLO,
takes between **400 and 800 s**. Round 500's driver-concurrent run of the
`unit_tests` stage was 646 s; round 435's note says solo is ~3x faster than
concurrent, which would predict ~215 s, and I am betting AGAINST that ratio
holding, because rounds 499/500 both measured the box as not-idle.
*Why it could be wrong:* it is a straight bet on this box's load today.

**P12 (RATE).** Of the 173 entries already in the ledger, the number whose
`scored_by` equals the bank's own round number is **>= 100** (i.e. most banks
in this program's history were scored by the round that banked them) — which is
what makes "the banking round should also write the ledger entry" the right
shape of fix rather than a cross-round hand-off.
*Why it could be wrong:* early rounds (15-137) were bootstrapped by round 369
from a prose scan and several were scored by a LATER round; if that pattern
dominates, the number could be 60-90.

**P13 (RATE, base rate).** I break at least one of my own new tests on its
first run. This program's rounds do this more often than not; betting against
it has been the losing side.

**P14 (STRUCTURAL).** Round 501 enters its OWN bank
(`state/round-501/predictions.md`) into `state/prediction-bank-ledger.json`
inside round 501, so K001 is at **0** at this round's final commit and not
merely at its middle one. If a round can do this for itself the recurrence has
a mechanical answer rather than a rotational one.

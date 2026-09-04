# Round 495 (skills B) — predictions banked BEFORE measuring (D-013)

Banked at the commit named in this file's own commit message, before any
repair was made and before any suite was re-run. Written with absolute paths
throughout, deliberately: round 493's bank landed at the wrong path because a
stale `cd` persisted into its `mkdir`, and closing the acknowledgement for
that mistake is this round's assigned work.

## 0. Already OBSERVED before banking — NOT predictions, do not score as hits

Round 493 and 494 both separated observed facts from predictions because the
round had already run the instruments before banking. Same here. These eight
were established by reading `logs/skills_health_round_494.log`, the evidence
files under `logs/corpus-evidence/round-494/`, and by re-running three
checkers and four pytest nodes solo:

- **O1.** All four skills-check red nodes reproduce SOLO at `nproc`=1 —
  `pytest` over the four named nodes: `4 failed in 67.78s`. None of the four
  is a concurrency artefact of the driver's four simultaneous suites. This
  discharges the red-debt instruction "REPRODUCE IT BEFORE FIXING IT" for all
  four, including the three marked RECURRENT.
- **O2.** The four `unit_tests` failures are exactly the `TestLiveCorpus` /
  `TestLiveBaselineIsHonest` mirrors of the other three red checkers plus
  `corpus_check` itself. `unit_tests` is a DEPENDENT node, not a fourth
  independent defect: 4 red nodes, 3 root causes.
- **O3.** `xref_check`'s 4 NEW authoritative danglings are 4 sites over only
  TWO distinct paths: `knowledge/v1_roadmap_mission.txt` (CLAUDE.md:134 in
  the operator's verbatim MASTER MISSION block, and state:27487) and
  `languages/whence/state/harness/round-493/predictions.md` (state:27291,
  state:27481).
- **O4.** `selfdesc_check`'s single J004 names that same round-493 path, in
  `state/prediction-bank-ledger.json[banks.493.note]`.
- **O5.** `carryforward`'s three K001s are rounds 490, 491 and 492, whose
  banks are on disk at `nuc/predictions-e-round490.md`,
  `state/swe/predictions-d-round491.md` and
  `state/whence/round-492/predictions.md`.
- **O6.** `carryforward_check.py --suggest` already exists and its documented
  job is "propose ledger entries for banks that have none".
- **O7.** `xref_check` prints its own blind spot: 39 files under
  `skills/*/scripts/` are exempt "because the checkers themselves quote the
  rot they detect". The exemption for quoting-rather-than-citing therefore
  EXISTS; it is scoped to one directory.
- **O8.** Round 493's state entry already diagnosed the J004 and assigned it:
  "it wants an entry in the acknowledgement mechanism `selfdesc-check`
  already reports against (`0 acknowledged` today), not a rewrite ...
  **skills(B) for the acknowledgement**." The work is assigned, not
  discovered, by this round.

## 1. Predictions

**P1 — the missing thing is the ENTRY, not the scoring.** At least 2 of the
3 unentered banks (490, 491, 492) were actually SCORED in their own round's
knowledge file, so their correct ledger `status` is `scored` and a verbatim
scoring quote exists to anchor them. MISS if 2 or more are genuinely unscored.

**P2 — `--suggest` does most of the work.** `carryforward_check.py --suggest`
proposes an entry for all 3, and finds a usable scoring anchor for at least
2 of the 3 without hand-searching the knowledge files.

**P3 — three repairs close four nodes in one pass.** Fixing the three root
causes takes `corpus_check.py` to 0 error(s), and all four red nodes green,
with no additional repair discovered along the way.

**P4 — `v1_roadmap_mission.txt` is not closable by a round.** It is cited by
the operator's verbatim CLAUDE.md block (landed by commit `7aab36a`, "not
authored by a round"). Predicted disposition: an entry in
`state/known-dangling-citations.json` owned by the OPERATOR, not a repair and
not a file this round authors. MISS if writing the file is the right move.

**P5 — the quote-vs-cite collision has no general mechanism.** Outside the
`skills/*/scripts/` self-exemption (O7), there is NO mechanism anywhere in
the corpus that distinguishes "prose citing a path" from "prose quoting a
path in order to say it is broken". The `known-dangling-citations.json` entry
for `ncs_engine.py` is the same shape and was handled by acknowledgement,
one path at a time. MISS if a general mechanism turns up.

**P6 — the bank-path shapes have outrun the scope regex.** `xref_check`'s
`HISTORICAL_RE` knows two prediction-file shapes (`nuc/predictions-` and
`state/round-NNN-predictions.md`) and the corpus now uses at least two more
(`state/<track>/round-NNN/PREDICTIONS.md`, `state/swe/predictions-d-roundNNN.md`).
So a prediction file is scanned as AUTHORITATIVE prose, and a bank that names
a path later deleted will redden `xref_check` in a round that has nothing to
do with it. Predicted: >= 3 bank files on disk currently classify as
`authoritative` under `scope_of`. This is a LATENT defect and I predict it
is currently costing 0 findings — a trap, not a live red.

**P7 — the count after repair.** `xref_check` reports 3 dangling in the
authoritative scope, 0 NEW, once the two new paths are acknowledged (the 3
pre-acknowledged today stay). `selfdesc_check` reports 0 error(s), 1
acknowledged. `carryforward` reports 0 error(s) and the ledger grows
167 -> 170 entries against 170 numbered banks on disk.

**P8 — K001 recurs again unless something reaches the banking round.** The
detector runs in `skills-check`, which only skills(B) runs; rounds 490/491/492
are tracks E, D and C. Prediction: with repair alone and no new instrument,
K001 is red again by round 498 at the latest. This is the pre-registered
experiment; it is NOT scorable inside round 495.

**P9 — wall clock, solo, `nproc`=1.** The full `unit_tests` tier ran 805.12s
under the driver's four concurrent suites in round 494. Solo it lands in
400-700 s. The three fast checkers together land under 60 s (xref alone
measured 7.6 s).

**P10 — the skill already half-exists.** The corpus has 106 skills including
`obligation-ledger`, `unenforced-documented-rule` and
`suppression-has-many-readers`. Predicted: at least one of these already
states the two-halves-of-an-obligation shape, so the genuinely NEW skill this
round owes is the narrower one — a checker whose exemption for quoted rot is
scoped to a directory rather than to the property. MISS if no existing skill
covers the obligation shape (then I owe both).

**P11 — no test currently pins the `--suggest` path.** Predicted: the
`--suggest` mode has no unit test asserting it proposes an entry for an
unentered bank. MISS if such a test exists.
